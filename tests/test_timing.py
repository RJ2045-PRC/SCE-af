from __future__ import annotations

import inspect
import json
import threading
import time
from io import BytesIO
from pathlib import Path

import pymupdf
from PIL import Image

from sce_af import jobs
from sce_af.pipeline import run_pipeline


def _png() -> bytes:
    buf = BytesIO()
    Image.new("RGB", (8, 8), (210, 20, 20)).save(buf, format="PNG")
    return buf.getvalue()


def _tiny_pdf(path: Path) -> Path:
    doc = pymupdf.open()
    page = doc.new_page(width=300, height=200)
    shape = page.new_shape()
    shape.draw_rect(pymupdf.Rect(20, 20, 90, 80))
    shape.finish(color=(0.85, 0.1, 0.1), width=3)
    shape.commit()
    doc.save(path)
    doc.close()
    return path


def _fake_vision(kind, png):
    assert png.startswith(b"\x89PNG")
    if kind == "title":
        return {"customer": "Xiaomi", "part_name": "CCS", "part_no": "P9"}
    if kind == "bubble":
        return {"num": "1", "special": "NA", "type": "尺寸", "description": "2.2 ±0.1"}
    return {"notes": [], "characteristics": []}


def test_default_workers_is_100():
    assert inspect.signature(run_pipeline).parameters["workers"].default == 100


def test_pipeline_timing_not_in_result(tmp_path):
    pdf = _tiny_pdf(tmp_path / "LG-26554.pdf")
    timing: dict = {}
    result = run_pipeline(pdf, "LG-26554.pdf", vision=_fake_vision, workers=1, timing_out=timing)
    assert "timing" not in result
    assert "slice" not in result
    assert "vision" not in result
    assert "wall_s" not in result
    assert "median_s" not in result
    assert timing["workers"] == 1
    assert timing["slice"]["page_count"] == 1
    assert timing["slice"]["task_count"] == timing["vision"]["count"]
    assert {"raster_s", "detect_s", "encode_s", "page", "tasks"} <= set(timing["slice"]["pages"][0])
    vision = timing["vision"]
    for key in ("wall_s", "sum_s", "count", "title", "bubble", "notes", "median_s", "max_s", "slowest"):
        assert key in vision
    assert vision["count"] >= 1
    assert len(vision["slices"]) == vision["count"]
    rec = vision["slices"][0]
    assert {"kind", "page", "png_bytes", "s", "ok", "error"} <= set(rec)
    assert rec["ok"] is True


def test_pipeline_keeps_timing_when_vision_fails(tmp_path):
    pdf = _tiny_pdf(tmp_path / "LG-26554.pdf")

    def boom(kind, png):
        raise RuntimeError("vision-fail")

    timing: dict = {}
    result = run_pipeline(pdf, "LG-26554.pdf", vision=boom, workers=1, timing_out=timing)
    failures = [issue for issue in result["issues"] if issue["code"] == "slice_failed"]
    assert len(failures) == timing["vision"]["count"]
    assert result["bubbles"] == []
    assert timing["slice"]["s"] >= 0
    assert timing["vision"]["slices"]
    assert timing["vision"]["slices"][0]["ok"] is False
    assert "vision-fail" in timing["vision"]["slices"][0]["error"]


def test_job_writes_timing_json_not_result(tmp_path, monkeypatch):
    monkeypatch.setattr(jobs, "jobs_dir", lambda: tmp_path)
    jobs.REQUIRE_KEY = False

    def runner(path: Path, filename: str, on_progress=None, timing_out=None):
        if timing_out is not None:
            timing_out["workers"] = 3
            timing_out["slice"] = {"s": 0.1, "page_count": 1, "task_count": 1, "pages": []}
            timing_out["vision"] = {
                "wall_s": 0.2,
                "sum_s": 0.2,
                "count": 1,
                "title": 1,
                "bubble": 0,
                "notes": 0,
                "median_s": 0.2,
                "max_s": 0.2,
                "slowest": [],
                "slices": [],
            }
        if on_progress:
            on_progress({"stage": "vision", "done": 1, "total": 1, "message": "stub"})
        return {
            "header": {"filename": filename, "mold_no": "LG-26554"},
            "bubbles": [],
            "requirements": {"notes": [], "characteristics": []},
            "issues": [],
        }

    jobs.RUNNER = runner
    try:
        created = jobs.create_job("LG-26554.pdf", b"%PDF-1.4 stub")
        job = None
        for _ in range(50):
            job = jobs.get_job(created["id"])
            if job and job["status"] in ("done", "error"):
                break
            time.sleep(0.05)
        assert job is not None
        assert job["status"] == "done"
        folder = tmp_path / created["id"]
        timing = json.loads((folder / "timing.json").read_text(encoding="utf-8"))
        result = json.loads((folder / "result.json").read_text(encoding="utf-8"))
        assert "slice" in timing
        assert "vision" in timing
        assert timing["ok"] is True
        assert "timing" not in result
        assert "slice" not in result
        assert "vision" not in result
        assert "median_s" not in result
    finally:
        jobs.REQUIRE_KEY = True
        from sce_af.pipeline import run_pipeline as real_runner

        jobs.RUNNER = real_runner


def test_job_keeps_timing_on_error(tmp_path, monkeypatch):
    monkeypatch.setattr(jobs, "jobs_dir", lambda: tmp_path)
    jobs.REQUIRE_KEY = False

    def runner(path: Path, filename: str, on_progress=None, timing_out=None):
        if timing_out is not None:
            timing_out["slice"] = {"s": 0.5, "pages": []}
            timing_out["vision"] = {
                "slices": [{"kind": "bubble", "ok": False, "error": "boom", "s": 0.1}]
            }
        raise RuntimeError("boom")

    jobs.RUNNER = runner
    try:
        created = jobs.create_job("fail.pdf", b"%PDF-1.4 stub")
        job = None
        for _ in range(50):
            job = jobs.get_job(created["id"])
            if job and job["status"] in ("done", "error"):
                break
            time.sleep(0.05)
        assert job is not None
        assert job["status"] == "error"
        folder = tmp_path / created["id"]
        timing = json.loads((folder / "timing.json").read_text(encoding="utf-8"))
        assert (folder / "result.json").exists() is False
        assert timing["ok"] is False
        assert "boom" in timing["error"]
        assert timing["slice"]["s"] == 0.5
    finally:
        jobs.REQUIRE_KEY = True
        from sce_af.pipeline import run_pipeline as real_runner

        jobs.RUNNER = real_runner


def test_pipeline_crop_name_not_image_bytes(tmp_path):
    pdf = _tiny_pdf(tmp_path / "LG-26554.pdf")
    seen = []

    def on_progress(info):
        seen.append(info)

    result = run_pipeline(pdf, "LG-26554.pdf", vision=_fake_vision, workers=1, on_progress=on_progress)
    blob = json.dumps(result)
    assert "\\u0089PNG" not in blob
    if result["bubbles"]:
        assert result["bubbles"][0]["crop"].endswith(".png")
        crops = [info["crop"] for info in seen if info.get("crop")]
        assert crops
        assert crops[0]["name"].endswith(".png")
        assert crops[0]["png"].startswith(b"\x89PNG")


def test_job_shows_bubbles_before_done_and_blocks_export(tmp_path, monkeypatch):
    monkeypatch.setattr(jobs, "jobs_dir", lambda: tmp_path)
    jobs.REQUIRE_KEY = False
    gate = threading.Event()
    png = _png()
    item = {
        "num": "1",
        "special": "NA",
        "description": "2.2 ±0.1",
        "type": "尺寸",
        "page": 1,
        "min_val": 2.1,
        "std_val": 2.2,
        "max_val": 2.3,
        "crop": "p01-001.png",
    }

    def runner(path: Path, filename: str, on_progress=None, timing_out=None):
        if on_progress:
            on_progress(
                {
                    "stage": "vision",
                    "done": 1,
                    "total": 2,
                    "message": "bubble",
                    "crop": {"name": "p01-001.png", "png": png, "item": item},
                }
            )
        gate.wait(timeout=3)
        return {
            "header": {"filename": filename, "mold_no": "LG-26554"},
            "bubbles": [item],
            "requirements": {"notes": [], "characteristics": []},
            "issues": [],
        }

    jobs.RUNNER = runner
    try:
        created = jobs.create_job("LG-26554.pdf", b"%PDF-1.4 stub")
        job = None
        for _ in range(40):
            job = jobs.get_job(created["id"])
            if job and job.get("result") and job["result"].get("bubbles"):
                break
            time.sleep(0.05)
        assert job is not None
        assert job["status"] == "running"
        assert job["result"]["bubbles"][0]["crop"] == "p01-001.png"
        packed = json.dumps(job)
        assert "\\u0089PNG" not in packed
        assert (tmp_path / created["id"] / "crops" / "p01-001.png").is_file()
        try:
            jobs.export_job(created["id"])
            raise AssertionError("export should wait until done")
        except ValueError as exc:
            assert "未完成" in str(exc)
        gate.set()
        for _ in range(50):
            job = jobs.get_job(created["id"])
            if job and job["status"] in ("done", "error"):
                break
            time.sleep(0.05)
        assert job["status"] == "done"
        dumped = json.dumps(job["result"])
        assert "p01-001.png" in dumped
        assert "\\u0089PNG" not in dumped
    finally:
        gate.set()
        jobs.REQUIRE_KEY = True
        from sce_af.pipeline import run_pipeline as real_runner

        jobs.RUNNER = real_runner

