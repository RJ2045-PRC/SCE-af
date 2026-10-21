"""In-memory jobs with a JSON snapshot on disk."""

from __future__ import annotations

import json
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from sce_af.export_docs import write_export_zip
from sce_af.merge import apply_bubble_edits, apply_header_edits
from sce_af.paths import repo_root
from sce_af.pipeline import run_pipeline
from sce_af.secrets import MissingApiKey, has_deepseek_key

# Tests replace this so HTTP jobs never call DeepSeek.
RUNNER = run_pipeline
REQUIRE_KEY = True

_LOCK = threading.Lock()
_JOBS: dict[str, dict[str, Any]] = {}


def jobs_dir() -> Path:
    path = repo_root() / "output" / "jobs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _job_dir(job_id: str) -> Path:
    path = jobs_dir() / job_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def _crops_dir(job_id: str) -> Path:
    path = _job_dir(job_id) / "crops"
    path.mkdir(parents=True, exist_ok=True)
    return path


def crop_path(job_id: str, name: str) -> Path | None:
    if not name or "/" in name or "\\" in name or ".." in name:
        return None
    if not name.endswith(".png"):
        return None
    path = _crops_dir(job_id) / name
    if not path.is_file():
        return None
    return path


def _empty_result(filename: str) -> dict[str, Any]:
    return {
        "header": {
            "filename": filename,
            "customer": "",
            "part_name": "",
            "mold_no": "",
            "part_no": "",
            "drawing_no": "",
            "revision": "",
        },
        "bubbles": [],
        "requirements": {"notes": [], "characteristics": []},
        "issues": [],
    }


def get_job(job_id: str) -> dict[str, Any] | None:
    with _LOCK:
        job = _JOBS.get(job_id)
        return json.loads(json.dumps(job)) if job else None


def public_job(job: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": job["id"],
        "status": job["status"],
        "filename": job.get("filename") or "",
        "progress": job.get("progress") or {},
        "error": job.get("error") or "",
        "result": job.get("result"),
    }


def create_job(filename: str, pdf_bytes: bytes) -> dict[str, Any]:
    job_id = uuid.uuid4().hex[:12]
    folder = _job_dir(job_id)
    pdf_path = folder / "source.pdf"
    pdf_path.write_bytes(pdf_bytes)
    job = {
        "id": job_id,
        "status": "queued",
        "filename": filename,
        "pdf_path": str(pdf_path),
        "progress": {"stage": "queued", "done": 0, "total": 0, "message": "排队"},
        "error": "",
        "result": _empty_result(filename),
    }
    with _LOCK:
        _JOBS[job_id] = job
    thread = threading.Thread(target=_run, args=(job_id,), daemon=True)
    thread.start()
    return public_job(job)


def _update(job_id: str, **fields: Any) -> None:
    with _LOCK:
        job = _JOBS.get(job_id)
        if job is None:
            return
        job.update(fields)


def _write_timing(job_id: str, timing: dict[str, Any]) -> None:
    path = _job_dir(job_id) / "timing.json"
    path.write_text(json.dumps(timing, ensure_ascii=False, indent=2), encoding="utf-8")


def _invoke_runner(
    pdf_path: Path,
    filename: str,
    on_progress: Any,
    timing: dict[str, Any],
) -> dict[str, Any]:
    try:
        return RUNNER(pdf_path, filename, on_progress=on_progress, timing_out=timing)
    except TypeError as exc:
        if "timing_out" not in str(exc):
            raise
        return RUNNER(pdf_path, filename, on_progress=on_progress)


def _run(job_id: str) -> None:
    job = get_job(job_id)
    if job is None:
        return
    timing: dict[str, Any] = {"filename": job["filename"], "ok": False, "error": ""}
    started = time.perf_counter()
    _update(job_id, status="running", progress={"stage": "start", "done": 0, "total": 0, "message": "开始"})
    try:
        if REQUIRE_KEY and not has_deepseek_key():
            raise MissingApiKey("缺少 DeepSeek 密钥。请把 sk-… 写进项目根 api-key.md。")

        def on_progress(info: dict[str, Any]) -> None:
            payload = dict(info)
            crop = payload.pop("crop", None)
            if crop:
                _save_crop(job_id, crop)
            _update(job_id, progress=payload)

        result = _invoke_runner(Path(job["pdf_path"]), job["filename"], on_progress, timing)
        out = _job_dir(job_id) / "result.json"
        out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        timing["ok"] = True
        timing["wall_s"] = round(time.perf_counter() - started, 4)
        _write_timing(job_id, timing)
        _update(
            job_id,
            status="done",
            result=result,
            progress={"stage": "done", "done": 1, "total": 1, "message": "完成"},
        )
    except Exception as exc:  # noqa: BLE001 — surface any worker failure to the UI
        timing["ok"] = False
        timing["error"] = str(exc)
        timing["wall_s"] = round(time.perf_counter() - started, 4)
        _write_timing(job_id, timing)
        _update(
            job_id,
            status="error",
            error=str(exc),
            progress={"stage": "error", "done": 0, "total": 0, "message": "失败"},
        )


def _save_crop(job_id: str, crop: dict[str, Any]) -> None:
    name = str(crop.get("name") or "").strip()
    png = crop.get("png")
    item = crop.get("item")
    if not name or not isinstance(png, (bytes, bytearray)) or not isinstance(item, dict):
        return
    if "/" in name or "\\" in name or ".." in name or not name.endswith(".png"):
        return
    (_crops_dir(job_id) / name).write_bytes(bytes(png))
    with _LOCK:
        job = _JOBS.get(job_id)
        if job is None:
            return
        result = dict(job.get("result") or _empty_result(job.get("filename") or ""))
        bubbles = list(result.get("bubbles") or [])
        if any(row.get("crop") == name for row in bubbles):
            return
        row = dict(item)
        row["crop"] = name
        bubbles.append(row)
        result["bubbles"] = bubbles
        job["result"] = result


def patch_header(job_id: str, edits: dict[str, Any]) -> dict[str, Any] | None:
    with _LOCK:
        job = _JOBS.get(job_id)
        if job is None or not job.get("result"):
            return None
        if job.get("status") != "done" and "bubbles" in (edits or {}):
            return None
        result = apply_header_edits(job["result"], edits or {})
        if "bubbles" in (edits or {}):
            result = apply_bubble_edits(result, edits.get("bubbles") or [])
        job["result"] = result
        out = _job_dir(job_id) / "result.json"
        out.write_text(json.dumps(job["result"], ensure_ascii=False, indent=2), encoding="utf-8")
        return public_job(job)


def export_job(job_id: str, edits: dict[str, Any] | None = None) -> dict[str, Any] | None:
    job = get_job(job_id)
    if job is None:
        return None
    if job.get("status") != "done":
        raise ValueError("识图未完成，不能导出")
    patched = patch_header(job_id, edits or {})
    if patched is None:
        return None
    folder = _job_dir(job_id)
    zip_path = folder / "docs.zip"
    filename = write_export_zip(patched["result"], zip_path, fallback=job_id)
    return {"path": zip_path, "filename": filename, "job": patched}
