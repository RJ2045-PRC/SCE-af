"""In-memory jobs with a JSON snapshot on disk."""

from __future__ import annotations

import json
import threading
import uuid
from pathlib import Path
from typing import Any

from sce_af.merge import apply_header_edits
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
        "result": None,
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


def _run(job_id: str) -> None:
    job = get_job(job_id)
    if job is None:
        return
    _update(job_id, status="running", progress={"stage": "start", "done": 0, "total": 0, "message": "开始"})
    try:
        if REQUIRE_KEY and not has_deepseek_key():
            raise MissingApiKey("缺少 DeepSeek 密钥。请把 sk-… 写进项目根 api-key.md。")

        def on_progress(info: dict[str, Any]) -> None:
            _update(job_id, progress=info)

        result = RUNNER(Path(job["pdf_path"]), job["filename"], on_progress=on_progress)
        out = _job_dir(job_id) / "result.json"
        out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        _update(
            job_id,
            status="done",
            result=result,
            progress={"stage": "done", "done": 1, "total": 1, "message": "完成"},
        )
    except Exception as exc:  # noqa: BLE001 — surface any worker failure to the UI
        _update(
            job_id,
            status="error",
            error=str(exc),
            progress={"stage": "error", "done": 0, "total": 0, "message": "失败"},
        )


def patch_header(job_id: str, edits: dict[str, Any]) -> dict[str, Any] | None:
    with _LOCK:
        job = _JOBS.get(job_id)
        if job is None or not job.get("result"):
            return None
        job["result"] = apply_header_edits(job["result"], edits)
        out = _job_dir(job_id) / "result.json"
        out.write_text(json.dumps(job["result"], ensure_ascii=False, indent=2), encoding="utf-8")
        return public_job(job)
