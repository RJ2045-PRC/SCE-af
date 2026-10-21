"""Local-only HTTP server: static UI + JSON APIs on 127.0.0.1."""

from __future__ import annotations

import errno
import json
import mimetypes
import posixpath
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import unquote, urlparse
from urllib.request import Request, urlopen

from sce_af import __version__ as APP_VERSION
from sce_af.jobs import create_job, get_job, patch_header, public_job
from sce_af.paths import web_dir
from sce_af.secrets import has_deepseek_key

WEB = web_dir()
HOST = "127.0.0.1"
DEFAULT_PORT = 2054
PORT_SCAN_MAX = 10
SERVICE_NAME = "sce-af"
# Response headers are encoded latin-1/strict by BaseHTTPRequestHandler, so the
# Server header must never carry a non-ASCII name. A Chinese SCE-af here
# makes send_header() raise UnicodeEncodeError before any byte is written and the
# browser sees an empty reply (blank page / RemoteDisconnected). Keep this ASCII
# and let SCE-af live in web/index.html only.
SERVER_SOFTWARE = SERVICE_NAME


def health_payload() -> dict:
    return {"ok": True, "service": SERVICE_NAME, "version": APP_VERSION}


def version_payload() -> dict:
    return {"version": APP_VERSION}


def _json_bytes(payload: dict, status: int = 200) -> tuple[int, bytes]:
    return status, json.dumps(payload, ensure_ascii=False).encode("utf-8")


def config_payload() -> dict:
    return {"has_key": has_deepseek_key()}


def parse_multipart(content_type: str, body: bytes) -> dict[str, tuple[str, bytes]]:
    """Parse a single-file multipart body. Returns field -> (filename, bytes)."""
    ctype = content_type or ""
    if "boundary=" not in ctype.lower():
        raise ValueError("multipart 缺少 boundary")
    boundary = ctype.split("boundary=", 1)[1].strip().strip('"').encode("utf-8")
    marker = b"--" + boundary
    parts = body.split(marker)
    out: dict[str, tuple[str, bytes]] = {}
    for part in parts:
        chunk = part
        if chunk.startswith(b"\r\n"):
            chunk = chunk[2:]
        if chunk in (b"", b"--", b"--\r\n"):
            continue
        if chunk.endswith(b"\r\n"):
            chunk = chunk[:-2]
        if chunk.endswith(b"--"):
            chunk = chunk[:-2]
        if b"\r\n\r\n" not in chunk:
            continue
        head, data = chunk.split(b"\r\n\r\n", 1)
        if data.endswith(b"\r\n"):
            data = data[:-2]
        headers = head.decode("utf-8", "replace")
        name = ""
        filename = ""
        for line in headers.split("\r\n"):
            if line.lower().startswith("content-disposition:"):
                for item in line.split(";"):
                    item = item.strip()
                    if item.startswith("name="):
                        name = item.split("=", 1)[1].strip().strip('"')
                    elif item.startswith("filename="):
                        filename = item.split("=", 1)[1].strip().strip('"')
        if name:
            out[name] = (filename, data)
    return out


def _read_json(handler: BaseHTTPRequestHandler) -> dict:
    length = int(handler.headers.get("Content-Length") or "0")
    raw = handler.rfile.read(length) if length else b"{}"
    if not raw:
        return {}
    data = json.loads(raw.decode("utf-8"))
    if not isinstance(data, dict):
        raise ValueError("JSON 必须是对象")
    return data


def _safe_web_path(url_path: str) -> Path | None:
    rel = unquote(url_path).lstrip("/")
    if rel == "" or rel == "index.html":
        return WEB / "index.html"
    candidate = (WEB / rel).resolve()
    try:
        candidate.relative_to(WEB.resolve())
    except ValueError:
        return None
    if candidate.is_file():
        return candidate
    return None


class AlreadyRunning(Exception):
    """Preferred (or scanned) port already serves this app."""

    def __init__(self, url: str) -> None:
        self.url = url
        super().__init__(url)


class _Server(ThreadingHTTPServer):
    """ThreadingHTTPServer that refuses to steal a port already being listened on.

    Windows maps SO_REUSEADDR onto a semantic that lets a *second* process bind a
    socket another process is already listening on. Since
    `socketserver.TCPServer.allow_reuse_address` defaults to 1, a second `run.py`
    binds the port alongside the first: no EADDRINUSE, no "already running"
    message, and requests split between two processes -- one possibly stale. Turn
    it off on Windows so a busy port raises and the probe/scan logic below runs.
    """

    allow_reuse_address = sys.platform != "win32"


class Handler(BaseHTTPRequestHandler):
    server_version = SERVER_SOFTWARE + "/" + APP_VERSION

    def log_message(self, fmt: str, *args) -> None:
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def do_HEAD(self) -> None:
        self.do_GET()

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = posixpath.normpath(parsed.path)

        if path == "/api/health":
            status, body = _json_bytes(health_payload())
            self._send(status, body, "application/json; charset=utf-8")
            return

        if path == "/api/version":
            status, body = _json_bytes(version_payload())
            self._send(status, body, "application/json; charset=utf-8")
            return

        if path == "/api/config":
            status, body = _json_bytes(config_payload())
            self._send(status, body, "application/json; charset=utf-8")
            return

        if path.startswith("/api/jobs/"):
            rest = path[len("/api/jobs/") :]
            if rest.endswith("/json"):
                job_id = rest[: -len("/json")]
                job = get_job(job_id)
                if job is None or not job.get("result"):
                    status, body = _json_bytes({"error": "not found"}, 404)
                    self._send(status, body, "application/json; charset=utf-8")
                    return
                payload = json.dumps(job["result"], ensure_ascii=False, indent=2).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(payload)))
                self.send_header(
                    "Content-Disposition",
                    f'attachment; filename="{job_id}.json"',
                )
                self.send_header("Cache-Control", "no-cache")
                self.end_headers()
                if self.command != "HEAD":
                    self.wfile.write(payload)
                return
            job = get_job(rest)
            if job is None:
                status, body = _json_bytes({"error": "not found"}, 404)
            else:
                status, body = _json_bytes(public_job(job))
            self._send(status, body, "application/json; charset=utf-8")
            return

        file_path = _safe_web_path(path)
        if file_path is None:
            status, body = _json_bytes({"error": "not found"}, 404)
            self._send(status, body, "application/json; charset=utf-8")
            return
        data = file_path.read_bytes()
        ctype = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
        if file_path.suffix == ".js":
            ctype = "application/javascript; charset=utf-8"
        elif file_path.suffix == ".css":
            ctype = "text/css; charset=utf-8"
        elif file_path.suffix == ".html":
            ctype = "text/html; charset=utf-8"
        self._send(200, data, ctype)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        path = posixpath.normpath(parsed.path)
        if path != "/api/jobs":
            status, body = _json_bytes({"error": "not found"}, 404)
            self._send(status, body, "application/json; charset=utf-8")
            return
        length = int(self.headers.get("Content-Length") or "0")
        if length <= 0 or length > 80 * 1024 * 1024:
            status, body = _json_bytes({"error": "请上传 PDF（不超过 80MB）"}, 400)
            self._send(status, body, "application/json; charset=utf-8")
            return
        body_bytes = self.rfile.read(length)
        try:
            fields = parse_multipart(self.headers.get("Content-Type") or "", body_bytes)
        except ValueError as exc:
            status, body = _json_bytes({"error": str(exc)}, 400)
            self._send(status, body, "application/json; charset=utf-8")
            return
        name, data = fields.get("file") or ("", b"")
        if not data:
            status, body = _json_bytes({"error": "缺少 file 字段"}, 400)
            self._send(status, body, "application/json; charset=utf-8")
            return
        filename = name or "drawing.pdf"
        if not filename.lower().endswith(".pdf"):
            status, body = _json_bytes({"error": "只接受 PDF"}, 400)
            self._send(status, body, "application/json; charset=utf-8")
            return
        job = create_job(filename, data)
        status, body = _json_bytes(job, 202)
        self._send(status, body, "application/json; charset=utf-8")

    def do_PATCH(self) -> None:
        parsed = urlparse(self.path)
        path = posixpath.normpath(parsed.path)
        if not path.startswith("/api/jobs/"):
            status, body = _json_bytes({"error": "not found"}, 404)
            self._send(status, body, "application/json; charset=utf-8")
            return
        job_id = path[len("/api/jobs/") :]
        try:
            edits = _read_json(self)
        except (ValueError, json.JSONDecodeError):
            status, body = _json_bytes({"error": "JSON 无效"}, 400)
            self._send(status, body, "application/json; charset=utf-8")
            return
        job = patch_header(job_id, edits)
        if job is None:
            status, body = _json_bytes({"error": "not found"}, 404)
        else:
            status, body = _json_bytes(job)
        self._send(status, body, "application/json; charset=utf-8")


def _is_addr_in_use(exc: OSError) -> bool:
    if exc.errno == errno.EADDRINUSE:
        return True
    wsa = getattr(errno, "WSAEADDRINUSE", None)
    return wsa is not None and exc.errno == wsa


def _probe_self(host: str, port: int, timeout: float = 0.8) -> bool:
    url = f"http://{host}:{port}/api/health"
    try:
        req = Request(url, method="GET")
        with urlopen(req, timeout=timeout) as resp:
            if getattr(resp, "status", 200) != 200:
                return False
            payload = json.loads(resp.read().decode("utf-8"))
    except (URLError, HTTPError, TimeoutError, json.JSONDecodeError, OSError, ValueError):
        return False
    return bool(payload.get("ok")) and payload.get("service") == SERVICE_NAME


def _port_in_use_hint(host: str, port: int, last_port: int) -> str:
    if sys.platform == "win32":
        kill = f"  netstat -ano | findstr :{port}\n  taskkill /PID <PID> /F"
    else:
        kill = f"  lsof -nP -iTCP:{port} -sTCP:LISTEN\n  kill <PID>"
    return (
        f"端口 {port}–{last_port} 均不可用（{host}）。\n"
        f"请结束占用进程后重试：\n"
        f"{kill}"
    )


def serve(
    host: str = HOST,
    port: int = DEFAULT_PORT,
    scan_max: int = PORT_SCAN_MAX,
) -> ThreadingHTTPServer:
    if host not in ("127.0.0.1", "localhost"):
        raise RuntimeError("this server only binds to 127.0.0.1")

    steps = max(1, int(scan_max))
    last_port = port + steps - 1
    for offset in range(steps):
        candidate = port + offset
        try:
            httpd = _Server((host, candidate), Handler)
            httpd.daemon_threads = True
            httpd.block_on_close = False
        except OSError as exc:
            if not _is_addr_in_use(exc):
                raise
            if _probe_self(host, candidate):
                raise AlreadyRunning(f"http://{host}:{candidate}/") from None
            continue
        if offset > 0:
            sys.stderr.write(f"端口 {port} 已被占用，已改用 {candidate}。\n")
        return httpd
    raise SystemExit(_port_in_use_hint(host, port, last_port))
