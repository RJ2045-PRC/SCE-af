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
from sce_af.ids import merge_header
from sce_af.limits import enrich_bubble
from sce_af.slice import SliceTask, plan_pdf
from sce_af.vision import VisionFn, complete_vision, normalize_bubble, normalize_notes

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
    tasks = plan_pdf(pdf_path, timing_out=slice_timing, on_progress=on_progress)
    total = len(tasks)
    channels = {
        kind: {"total": sum(task.kind == kind for task in tasks), "succeeded": 0,
               "running": 0, "failed": 0, "queued": sum(task.kind == kind for task in tasks)}
        for kind in ("title", "bubble", "notes")
    }
    if on_progress:
        on_progress({"stage": "planned", "done": 0, "total": total,
                     "channels": {k: dict(v) for k, v in channels.items()}, "message": f"切出 {total} 块"})
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
    failures: list[dict[str, Any]] = []
    done = 0
    records: list[dict[str, Any]] = []
    lock = threading.Lock()
    vision_started = time.perf_counter()

    def emit(message: str, **extra: Any) -> None:
        # Called under lock so snapshots never arrive out of order from workers.
        if on_progress:
            on_progress({"stage": "vision", "done": done, "total": total,
                         "channels": {k: dict(v) for k, v in channels.items()},
                         "message": message, **extra})

    def _one(task: SliceTask) -> tuple[SliceTask, dict[str, Any]]:
        with lock:
            channels[task.kind]["queued"] -= 1
            channels[task.kind]["running"] += 1
            emit(f"识图 {done}/{total}")
        started = time.perf_counter()
        error = ""
        ok = True
        try:
            raw = vision_fn(task.kind, task.png)
            if not isinstance(raw, dict):
                raise ValueError("识图结果必须是 JSON 对象")
            # Detect malformed model fields per slice, before final merge.
            if task.kind == "notes":
                normalize_notes(raw, task.page)
            elif task.kind == "bubble":
                enrich_bubble(normalize_bubble(raw, task.page))
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
            futures = {pool.submit(_one, task): task for task in tasks}
            for fut in as_completed(futures):
                task = futures[fut]
                crop_payload = None
                partial_header = None
                failed = False
                try:
                    _, raw = fut.result()
                    if task.kind == "title":
                        title_raw = raw
                        partial_header = merge_header(filename, raw)
                    elif task.kind == "bubble":
                        payload = dict(raw)
                        idx = int(task.extra.get("index") or 0)
                        crop = f"p{task.page:02d}-{idx:03d}.png"
                        payload["crop"] = crop
                        item = enrich_bubble(normalize_bubble(payload, task.page))
                        item["crop"] = crop
                        crop_payload = {"name": crop, "png": task.png, "item": item}
                        bubble_raws.append((task.page, payload))
                    elif task.kind == "notes":
                        notes_raws.append((task.page, raw))
                except Exception:  # A failed slice must not cancel other futures.
                    failed = True
                    label = {"title": "基本信息", "bubble": "气泡尺寸", "notes": "技术要求"}[task.kind]
                    failures.append({"code": "slice_failed", "kind": task.kind, "page": task.page,
                                     "index": task.extra.get("index") or task.extra.get("band"),
                                     "message": f"{label}第 {task.page} 页切片识别失败，请核对缺失内容。"})
                with lock:
                    done += 1
                    channels[task.kind]["running"] -= 1
                    channels[task.kind]["failed" if failed else "succeeded"] += 1
                    extra: dict[str, Any] = {}
                    if crop_payload:
                        extra["crop"] = crop_payload
                    if partial_header:
                        extra["partial_header"] = partial_header
                    emit(f"识图 {done}/{total}（{task.kind} p{task.page}）", **extra)
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
        on_progress({"stage": "merge", "done": total, "total": total,
                     "channels": channels, "message": "汇总 JSON"})
    result = merge_job(filename, title_raw, bubble_raws, notes_raws)
    result["issues"].extend(failures)
    return result
