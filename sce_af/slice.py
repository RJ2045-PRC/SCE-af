"""Turn pages into small image tasks. The model never sees a whole PDF."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from PIL import Image

from sce_af.detect import crop_box, find_red_boxes
from sce_af.raster import fill_ratio, image_png_bytes, page_count, render_page

EMPTY_FILL = 0.012


@dataclass
class SliceTask:
    kind: str  # title | notes | bubble
    page: int
    png: bytes
    box: tuple[int, int, int, int] | None = None
    extra: dict = field(default_factory=dict)


def title_crop(img: Image.Image) -> Image.Image:
    """Bottom-right title block plus a strip of the bottom frame."""
    w, h = img.size
    x0 = int(w * 0.42)
    y0 = int(h * 0.62)
    return img.crop((x0, y0, w, h))


def _band_crops(img: Image.Image, bands: int = 3, overlap: float = 0.12) -> list[tuple[Image.Image, tuple[int, int, int, int]]]:
    w, h = img.size
    # Inner drawing area, drop the outer frame letters.
    x0, y0 = int(w * 0.04), int(h * 0.07)
    x1, y1 = int(w * 0.96), int(h * 0.90)
    inner_h = y1 - y0
    step = inner_h / bands
    overlap_px = int(inner_h * overlap)
    out = []
    for i in range(bands):
        top = max(y0, int(y0 + i * step) - (overlap_px if i else 0))
        bot = min(y1, int(y0 + (i + 1) * step) + (overlap_px if i < bands - 1 else 0))
        crop = img.crop((x0, top, x1, bot))
        if fill_ratio(crop) >= EMPTY_FILL:
            out.append((crop, (x0, top, x1, bot)))
    return out


def _seconds(elapsed: float) -> float:
    return round(elapsed, 4)


def _page_meta(page: int, detect_s: float, encode_s: float, tasks: int) -> dict[str, Any]:
    return {
        "page": page,
        "detect_s": _seconds(detect_s),
        "encode_s": _seconds(encode_s),
        "tasks": tasks,
    }


def _plan_page(img: Image.Image, page: int, *, is_first: bool) -> tuple[list[SliceTask], dict[str, Any]]:
    tasks: list[SliceTask] = []
    detect_s = 0.0
    encode_s = 0.0

    t0 = time.perf_counter()
    boxes = find_red_boxes(img)
    detect_s += time.perf_counter() - t0

    def encode(crop: Image.Image) -> bytes:
        nonlocal encode_s
        started = time.perf_counter()
        png = image_png_bytes(crop)
        encode_s += time.perf_counter() - started
        return png

    if is_first:
        crop = title_crop(img)
        tasks.append(
            SliceTask(
                kind="title",
                page=page,
                png=encode(crop),
                box=(int(img.width * 0.42), int(img.height * 0.62), img.width, img.height),
            )
        )
    if len(boxes) >= 1:
        for idx, box in enumerate(boxes, start=1):
            crop = crop_box(img, box, pad=24)
            padded = box.padded(24, img.width, img.height)
            tasks.append(
                SliceTask(
                    kind="bubble",
                    page=page,
                    png=encode(crop),
                    box=(padded.x, padded.y, padded.x + padded.w, padded.y + padded.h),
                    extra={"index": idx},
                )
            )
        return tasks, _page_meta(page, detect_s, encode_s, len(tasks))

    t0 = time.perf_counter()
    ratio = fill_ratio(img)
    detect_s += time.perf_counter() - t0
    if ratio < EMPTY_FILL or is_first or ratio < 0.03:
        return tasks, _page_meta(page, detect_s, encode_s, len(tasks))
    for idx, (crop, box) in enumerate(_band_crops(img), start=1):
        tasks.append(
            SliceTask(
                kind="notes",
                page=page,
                png=encode(crop),
                box=box,
                extra={"band": idx},
            )
        )
    return tasks, _page_meta(page, detect_s, encode_s, len(tasks))


def plan_page(img: Image.Image, page: int, *, is_first: bool) -> list[SliceTask]:
    tasks, _meta = _plan_page(img, page, is_first=is_first)
    return tasks


def plan_pdf(
    pdf_path: Path,
    dpi: int = 140,
    timing_out: dict[str, Any] | None = None,
    on_progress: Callable[[dict[str, Any]], None] | None = None,
) -> list[SliceTask]:
    n = page_count(pdf_path)
    tasks: list[SliceTask] = []
    pages: list[dict[str, Any]] = []
    started = time.perf_counter()
    for page in range(1, n + 1):
        if on_progress:
            on_progress({"stage": "raster", "page": page, "page_count": n,
                         "done": len(tasks), "total": 0, "message": f"转图 {page}/{n} 页"})
        t0 = time.perf_counter()
        img = render_page(pdf_path, page, dpi=dpi)
        raster_s = time.perf_counter() - t0
        page_tasks, page_meta = _plan_page(img, page, is_first=(page == 1))
        page_meta["raster_s"] = _seconds(raster_s)
        pages.append(page_meta)
        tasks.extend(page_tasks)
        if on_progress:
            preview = img.copy()
            preview.thumbnail((900, 900))
            regions = []
            for task in page_tasks:
                if task.box:
                    x0, y0, x1, y1 = task.box
                    regions.append({"kind": task.kind, "box": [
                        x0 / img.width, y0 / img.height, x1 / img.width, y1 / img.height,
                    ]})
            on_progress({
                "stage": "slice", "page": page, "page_count": n,
                "done": len(tasks), "total": 0, "message": f"已切块 {page}/{n} 页，共 {len(tasks)} 块",
                "page_preview": {"name": f"page-{page:03d}.png", "png": image_png_bytes(preview)},
                "page_info": {"page": page, "preview": f"page-{page:03d}.png", "regions": regions},
            })
    if timing_out is not None:
        timing_out.clear()
        timing_out.update(
            {
                "s": _seconds(time.perf_counter() - started),
                "page_count": n,
                "task_count": len(tasks),
                "pages": pages,
            }
        )
    return tasks
