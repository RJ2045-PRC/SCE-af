"""Turn pages into small image tasks. The model never sees a whole PDF."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

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


def _band_crops(img: Image.Image, bands: int = 3, overlap: float = 0.12) -> list[Image.Image]:
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
            out.append(crop)
    return out


def plan_page(img: Image.Image, page: int, *, is_first: bool) -> list[SliceTask]:
    tasks: list[SliceTask] = []
    boxes = find_red_boxes(img)
    if is_first:
        crop = title_crop(img)
        tasks.append(
            SliceTask(
                kind="title",
                page=page,
                png=image_png_bytes(crop),
                box=(int(img.width * 0.42), int(img.height * 0.62), img.width, img.height),
            )
        )
    if len(boxes) >= 1:
        for idx, box in enumerate(boxes, start=1):
            crop = crop_box(img, box, pad=24)
            tasks.append(
                SliceTask(
                    kind="bubble",
                    page=page,
                    png=image_png_bytes(crop),
                    box=(box.x, box.y, box.w, box.h),
                    extra={"index": idx},
                )
            )
        return tasks
    ratio = fill_ratio(img)
    if ratio < EMPTY_FILL:
        return tasks
    if is_first:
        return tasks
    # Sparse isometric / empty revision sheets are not technical-requirement pages.
    if ratio < 0.03:
        return tasks
    for idx, crop in enumerate(_band_crops(img), start=1):
        tasks.append(
            SliceTask(
                kind="notes",
                page=page,
                png=image_png_bytes(crop),
                extra={"band": idx},
            )
        )
    return tasks


def plan_pdf(pdf_path: Path, dpi: int = 140) -> list[SliceTask]:
    n = page_count(pdf_path)
    tasks: list[SliceTask] = []
    for page in range(1, n + 1):
        img = render_page(pdf_path, page, dpi=dpi)
        tasks.extend(plan_page(img, page, is_first=(page == 1)))
    return tasks
