"""Orchestrate slice → vision → merge. Vision is injected so tests never hit the API."""

from __future__ import annotations

import statistics
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Callable

from sce_af.merge import merge_job
from sce_af.limits import enrich_bubble
from sce_af.slice import SliceTask, plan_pdf
from sce_af.vision import VisionFn, complete_vision, normalize_bubble

ProgressFn = Callable[[dict[str, Any]], None]


def _default_vision(kind: str, png: bytes) -> dict[str, Any]:
    return complete_vision(kind, png)


def _seconds(elapsed: float) -> float:
    return round(elapsed, 4)


def _empty_vision(workers: int) -> dict[str, Any]:
    return {
        "wall_s": 0.0,
        "sum_s": 0.0,
        "count": 0,
        "title": 0,
        "bubble": 0,
        "notes": 0,
        "median_s": 0.0,
        "max_s": 0.0,
        "workers": workers,
        "slowest": [],
        "slices": [],
    }


def _summarize_vision(records: list[dict[str, Any]], wall_s: float, workers: int) -> dict[str, Any]:
    times = [float(item["s"]) for item in records]
    counts = Counter(str(item["kind"]) for item in records)
    slowest = sorted(records, key=lambda item: float(item["s"]), reverse=True)[:5]
    return {
        "wall_s": _seconds(wall_s),
        "sum_s": _seconds(sum(times)),
        "count": len(records),
        "title": int(counts.get("title", 0)),
        "bubble": int(counts.get("bubble", 0)),
        "notes": int(counts.get("notes", 0)),
        "median_s": _seconds(statistics.median(times)) if times else 0.0,
        "max_s": _seconds(max(times)) if times else 0.0,
        "workers": workers,
        "slowest": slowest,
        "slices": records,
    }


def _fill_timing(
    timing_out: dict[str, Any] | None,
    *,
    workers: int,
    slice_timing: dict[str, Any],
    vision_timing: dict[str, Any],
) -> None:
    if timing_out is None:
        return
    timing_out["workers"] = workers
    timing_out["slice"] = slice_timing
    timing_out["vision"] = vision_timing


def run_pipeline(
    pdf_path: Path,
    filename: str,
    *,
    vision: VisionFn | None = None,
    workers: int = 100,
    on_progress: ProgressFn | None = None,
    timing_out: dict[str, Any] | None = None,
) -> dict[str, Any]:
    vision_fn = vision or _default_vision
    slice_timing: dict[str, Any] = {}
    tasks = plan_pdf(pdf_path, timing_out=slice_timing)
    total = len(tasks)
    if on_progress:
        on_progress({"stage": "planned", "done": 0, "total": total, "message": f"切出 {total} 块"})
    if not tasks:
        _fill_timing(
            timing_out,
            workers=workers,
            slice_timing=slice_timing,
            vision_timing=_empty_vision(workers),
        )
        return merge_job(filename, None, [], [])

    title_raw: dict | None = None
    bubble_raws: list[tuple[int, dict]] = []
    notes_raws: list[tuple[int, dict]] = []
    done = 0
    records: list[dict[str, Any]] = []
    lock = threading.Lock()
    vision_started = time.perf_counter()

    def _one(task: SliceTask) -> tuple[SliceTask, dict[str, Any]]:
        started = time.perf_counter()
        error = ""
        ok = True
        try:
            raw = vision_fn(task.kind, task.png)
            return task, raw
        except Exception as exc:
            ok = False
            error = str(exc)
            raise
        finally:
            rec = {
                "kind": task.kind,
                "page": task.page,
                "png_bytes": len(task.png),
                "s": _seconds(time.perf_counter() - started),
                "ok": ok,
                "error": error,
            }
            with lock:
                records.append(rec)

    try:
        with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
            futures = [pool.submit(_one, task) for task in tasks]
            for fut in as_completed(futures):
                task, raw = fut.result()
                crop_payload = None
                if task.kind == "title":
                    title_raw = raw
                elif task.kind == "bubble":
                    payload = dict(raw)
                    idx = int(task.extra.get("index") or 0)
                    crop = f"p{task.page:02d}-{idx:03d}.png"
                    payload["crop"] = crop
                    bubble_raws.append((task.page, payload))
                    item = enrich_bubble(normalize_bubble(payload, task.page))
                    item["crop"] = crop
                    crop_payload = {"name": crop, "png": task.png, "item": item}
                elif task.kind == "notes":
                    notes_raws.append((task.page, raw))
                done += 1
                if on_progress:
                    info = {
                        "stage": "vision",
                        "done": done,
                        "total": total,
                        "message": f"识图 {done}/{total}（{task.kind} p{task.page}）",
                    }
                    if crop_payload:
                        info["crop"] = crop_payload
                    on_progress(info)
    except Exception:
        _fill_timing(
            timing_out,
            workers=workers,
            slice_timing=slice_timing,
            vision_timing=_summarize_vision(records, time.perf_counter() - vision_started, workers),
        )
        raise

    vision_timing = _summarize_vision(records, time.perf_counter() - vision_started, workers)
    _fill_timing(
        timing_out,
        workers=workers,
        slice_timing=slice_timing,
        vision_timing=vision_timing,
    )
    if on_progress:
        on_progress({"stage": "merge", "done": total, "total": total, "message": "汇总 JSON"})
    return merge_job(filename, title_raw, bubble_raws, notes_raws)
