"""Orchestrate slice → vision → merge. Vision is injected so tests never hit the API."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Callable

from sce_af.slice import SliceTask, plan_pdf
from sce_af.vision import VisionFn, complete_vision
from sce_af.merge import merge_job

ProgressFn = Callable[[dict[str, Any]], None]


def _default_vision(kind: str, png: bytes) -> dict[str, Any]:
    return complete_vision(kind, png)


def run_pipeline(
    pdf_path: Path,
    filename: str,
    *,
    vision: VisionFn | None = None,
    workers: int = 3,
    on_progress: ProgressFn | None = None,
) -> dict[str, Any]:
    vision_fn = vision or _default_vision
    tasks = plan_pdf(pdf_path)
    total = len(tasks)
    if on_progress:
        on_progress({"stage": "planned", "done": 0, "total": total, "message": f"切出 {total} 块"})
    if not tasks:
        return merge_job(filename, None, [], [])

    title_raw: dict | None = None
    bubble_raws: list[tuple[int, dict]] = []
    notes_raws: list[tuple[int, dict]] = []
    done = 0

    def _one(task: SliceTask) -> tuple[SliceTask, dict[str, Any]]:
        return task, vision_fn(task.kind, task.png)

    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = [pool.submit(_one, task) for task in tasks]
        for fut in as_completed(futures):
            task, raw = fut.result()
            if task.kind == "title":
                title_raw = raw
            elif task.kind == "bubble":
                bubble_raws.append((task.page, raw))
            elif task.kind == "notes":
                notes_raws.append((task.page, raw))
            done += 1
            if on_progress:
                on_progress(
                    {
                        "stage": "vision",
                        "done": done,
                        "total": total,
                        "message": f"识图 {done}/{total}（{task.kind} p{task.page}）",
                    }
                )

    if on_progress:
        on_progress({"stage": "merge", "done": total, "total": total, "message": "汇总 JSON"})
    return merge_job(filename, title_raw, bubble_raws, notes_raws)
