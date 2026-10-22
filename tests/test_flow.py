"""Real progress, preview geometry and partial failures, without model requests."""

from __future__ import annotations

import json
import threading
from io import BytesIO
from urllib.error import HTTPError
from urllib.request import urlopen

import pymupdf
import pytest
from PIL import Image

from sce_af import jobs, pipeline
from sce_af.app import serve
from sce_af.slice import SliceTask, plan_pdf


def drawing_pdf(path, *, notes=False):
    doc = pymupdf.open()
    for _ in range(2):
        page = doc.new_page(width=400, height=300)
        page.draw_rect(pymupdf.Rect(40, 50, 140, 120), color=(.9, .05, .05), width=4)
        page.insert_text((55, 85), "25 +/-0.1")
    if notes:
        page = doc.new_page(width=400, height=300)
        for y in range(30, 260, 10):
            page.insert_text((25, y), "Technical requirement - remove burrs and sharp edges", fontsize=10)
    doc.save(path)
    doc.close()
    return path


def test_page_previews_match_actual_crop_geometry(tmp_path):
    seen = []
    tasks = plan_pdf(drawing_pdf(tmp_path / "drawing.pdf", notes=True), on_progress=seen.append)
    pages = [p for p in seen if p["stage"] == "slice"]
    assert [p["page"] for p in pages] == [1, 2, 3]
    assert {task.kind for task in tasks} == {"title", "bubble", "notes"}
    for page in pages:
        assert page["page_count"] == 3
        preview = Image.open(BytesIO(page["page_preview"]["png"]))
        assert max(preview.size) <= 900
        page_tasks = [task for task in tasks if task.page == page["page"]]
        assert len(page["page_info"]["regions"]) == len(page_tasks)
        for task, region in zip(page_tasks, page["page_info"]["regions"]):
            x0, y0, x1, y1 = region["box"]
            assert 0 <= x0 < x1 <= 1
            assert 0 <= y0 < y1 <= 1
            crop = Image.open(BytesIO(task.png))
            bx0, by0, bx1, by1 = task.box
            assert crop.size == (bx1 - bx0, by1 - by0)


def test_parallel_counts_and_failures_do_not_cancel_other_slices(monkeypatch, tmp_path):
    tasks = [SliceTask("title", 1, b"title"), SliceTask("bubble", 1, b"fail", extra={"index": 1}),
             SliceTask("bubble", 1, b"ok", extra={"index": 2}), SliceTask("notes", 2, b"notes")]
    monkeypatch.setattr(pipeline, "plan_pdf", lambda *args, **kwargs: tasks)
    gate = threading.Barrier(2)

    def vision(kind, png):
        if png in (b"title", b"fail"):
            gate.wait(timeout=3)
        if png == b"fail":
            raise RuntimeError("test failure")
        if kind == "title":
            return {"customer": "Test", "part_name": "Part", "part_no": "P123"}
        if kind == "bubble":
            return {"num": "2", "description": "25 ±0.1", "special": "NA"}
        return {"notes": [{"no": "1", "text": "Test requirement"}]}

    seen, timing = [], {}
    result = pipeline.run_pipeline(tmp_path / "unused.pdf", "LG-TEST.pdf", vision=vision,
                                   workers=2, on_progress=seen.append, timing_out=timing)
    snapshots = [p for p in seen if p["stage"] == "vision"]
    assert any(sum(c["running"] for c in p["channels"].values()) == 2 for p in snapshots)
    assert [p["done"] for p in snapshots] == sorted(p["done"] for p in snapshots)
    for p in snapshots:
        for c in p["channels"].values():
            assert min(c.values()) >= 0
            assert c["total"] == c["queued"] + c["running"] + c["succeeded"] + c["failed"]
    final = seen[-1]
    assert final["channels"]["bubble"] == {"total": 2, "queued": 0, "running": 0, "succeeded": 1, "failed": 1}
    assert result["bubbles"][0]["num"] == "2"
    assert result["requirements"]["notes"][0]["text"] == "Test requirement"
    assert len([issue for issue in result["issues"] if issue["code"] == "slice_failed"]) == 1
    assert len(timing["vision"]["slices"]) == 4
    assert any(p.get("partial_header", {}).get("customer") == "Test" for p in seen)


def test_preview_http_and_flow_survive_completion(tmp_path, monkeypatch):
    storage = tmp_path / "jobs"
    storage.mkdir()
    monkeypatch.setattr(jobs, "jobs_dir", lambda: storage)
    monkeypatch.setattr(jobs, "REQUIRE_KEY", False)
    entered, release, finished = threading.Event(), threading.Event(), threading.Event()

    def vision(kind, png):
        entered.set()
        assert release.wait(timeout=5)
        if kind == "title":
            return {"part_no": "P123"}
        raise RuntimeError("unreadable bubble")

    def runner(*args, **kwargs):
        try:
            return pipeline.run_pipeline(*args, vision=vision, **kwargs)
        finally:
            finished.set()

    monkeypatch.setattr(jobs, "RUNNER", runner)
    httpd = serve(port=0, scan_max=1)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    pdf = drawing_pdf(tmp_path / "LG-TEST.pdf")
    try:
        created = jobs.create_job(pdf.name, pdf.read_bytes())
        assert entered.wait(timeout=3)
        job_id = created["id"]
        with urlopen(f"{base}/api/jobs/{job_id}") as resp:
            job = json.load(resp)
        assert job["status"] == "running"
        assert len(job["flow"]["pages"]) == 2
        assert '"png":' not in json.dumps(job)
        assert "page_preview" not in job["progress"]
        assert job["result"]["header"]["mold_no"] == "LG-TEST"
        with urlopen(f"{base}/api/jobs/{job_id}/crops/page-001.png") as resp:
            assert resp.headers["Content-Type"] == "image/png"
            assert resp.read().startswith(b"\x89PNG")
        with pytest.raises(ValueError, match="未完成"):
            jobs.export_job(job_id)
        with pytest.raises(HTTPError) as exc:
            urlopen(f"{base}/api/jobs/{job_id}/crops/..%2Fsource.pdf")
        assert exc.value.code == 404
        release.set()
        assert finished.wait(timeout=3)
        # Wait for the job writer after the pipeline returns.
        import time

        for _ in range(100):
            job = jobs.get_job(job_id)
            if job["status"] == "done":
                break
            time.sleep(.01)
        assert job["status"] == "done"
        assert len(job["flow"]["pages"]) == 2
        assert job["flow"]["channels"]["bubble"]["failed"] == 2
        assert job["flow"]["channels"]["bubble"]["running"] == 0
        assert "flow" not in job["result"]
    finally:
        release.set()
        finished.wait(timeout=5)
        httpd.shutdown()
        httpd.server_close()
