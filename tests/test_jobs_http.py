from __future__ import annotations

import json
import threading
import time
from io import BytesIO
from pathlib import Path
from urllib.request import Request, urlopen

from sce_af.app import parse_multipart, serve
from sce_af import jobs


def _multipart(filename: str, data: bytes) -> tuple[bytes, str]:
    boundary = "----sceafboundary"
    buf = BytesIO()
    buf.write(f"--{boundary}\r\n".encode())
    buf.write(
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'.encode()
    )
    buf.write(b"Content-Type: application/pdf\r\n\r\n")
    buf.write(data)
    buf.write(f"\r\n--{boundary}--\r\n".encode())
    return buf.getvalue(), f"multipart/form-data; boundary={boundary}"


def test_parse_multipart_roundtrip():
    body, ctype = _multipart("LG-26554.pdf", b"%PDF-fake")
    fields = parse_multipart(ctype, body)
    name, data = fields["file"]
    assert name == "LG-26554.pdf"
    assert data == b"%PDF-fake"


def test_job_http_with_stub_runner():
    jobs.REQUIRE_KEY = False

    def stub(path: Path, filename: str, on_progress=None):
        if on_progress:
            on_progress({"stage": "vision", "done": 1, "total": 1, "message": "stub"})
        return {
            "header": {
                "filename": filename,
                "customer": "",
                "part_name": "",
                "mold_no": "LG-26554",
                "part_no": "",
                "drawing_no": "",
                "revision": "",
            },
            "bubbles": [
                {
                    "num": "2",
                    "special": "SC",
                    "special_no": "1",
                    "type": "尺寸",
                    "description": "2.2 ±0.1",
                    "page": 1,
                    "min_val": 2.1,
                    "std_val": 2.2,
                    "max_val": 2.3,
                }
            ],
            "requirements": {"notes": [], "characteristics": []},
            "issues": [],
        }

    jobs.RUNNER = stub
    httpd = serve(port=0, scan_max=1)
    host, port = httpd.server_address[:2]
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        body, ctype = _multipart("LG-26554.pdf", b"%PDF-1.4 stub")
        req = Request(
            f"http://{host}:{port}/api/jobs",
            data=body,
            headers={"Content-Type": ctype},
            method="POST",
        )
        with urlopen(req) as resp:
            created = json.loads(resp.read().decode("utf-8"))
        assert created["id"]
        job = None
        for _ in range(50):
            with urlopen(f"http://{host}:{port}/api/jobs/{created['id']}") as resp:
                job = json.loads(resp.read().decode("utf-8"))
            if job["status"] in ("done", "error"):
                break
            time.sleep(0.05)
        assert job["status"] == "done"
        assert job["result"]["header"]["mold_no"] == "LG-26554"

        patch = Request(
            f"http://{host}:{port}/api/jobs/{created['id']}",
            data=json.dumps({"part_no": "P000005766001"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="PATCH",
        )
        with urlopen(patch) as resp:
            updated = json.loads(resp.read().decode("utf-8"))
        assert updated["result"]["header"]["part_no"] == "P000005766001"

        export = Request(
            f"http://{host}:{port}/api/jobs/{created['id']}/export",
            data=json.dumps({"customer": "测试客户", "revision": "A"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(export) as resp:
            payload = resp.read()
            disp = resp.headers.get("Content-Disposition") or ""
        assert payload[:2] == b"PK"
        assert "docs.zip" in disp
    finally:
        jobs.REQUIRE_KEY = True
        from sce_af.pipeline import run_pipeline

        jobs.RUNNER = run_pipeline
        httpd.shutdown()
        httpd.server_close()
