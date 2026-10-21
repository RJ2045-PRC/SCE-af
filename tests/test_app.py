"""HTTP contract: loopback only, health, version, static index."""

from __future__ import annotations

import json
import threading
from urllib.request import urlopen

import pytest

from sce_af import __version__
from sce_af.app import (
    DEFAULT_PORT,
    SERVICE_NAME,
    AlreadyRunning,
    Handler,
    _Server,
    health_payload,
    serve,
    version_payload,
)


def test_server_refuses_to_steal_a_busy_port() -> None:
    """Regression: on Windows SO_REUSEADDR let a 2nd run.py bind the same port.

    With allow_reuse_address on, the second instance never sees EADDRINUSE, so
    the "already running" / next-free-port logic never fires and two processes
    end up fighting over the port — one possibly running stale code.
    """
    import sys as _sys

    assert _Server.allow_reuse_address is (_sys.platform != "win32")


def test_second_instance_detects_already_running() -> None:
    """Only reachable if the second bind actually fails; with a stolen port the
    bind would succeed and no AlreadyRunning would ever be raised."""
    first = serve(port=0, scan_max=1)
    host, port = first.server_address[:2]
    thread = threading.Thread(target=first.serve_forever, daemon=True)
    thread.start()
    try:
        with pytest.raises(AlreadyRunning) as ctx:
            serve(host=host, port=port, scan_max=1)
        assert f":{port}" in ctx.value.url
    finally:
        first.shutdown()
        first.server_close()


def test_server_header_is_latin1_safe() -> None:
    """Regression: a non-ASCII display name in server_version kills every response.

    BaseHTTPRequestHandler.send_header() encodes values with latin-1/strict, so a
    Chinese server_version raises UnicodeEncodeError before a single byte is
    written and the browser just sees an empty reply.
    """
    raw = f"{Handler.server_version} {Handler.sys_version}"
    assert raw.encode("latin-1")  # must not raise


def test_version_matches_package() -> None:
    assert health_payload()["version"] == __version__
    assert version_payload()["version"] == __version__
    assert health_payload()["service"] == SERVICE_NAME
    assert SERVICE_NAME == "sce-af"
    assert DEFAULT_PORT == 2054


def test_serve_rejects_non_loopback() -> None:
    with pytest.raises(RuntimeError, match="127.0.0.1"):
        serve(host="0.0.0.0")


def test_health_and_index_http() -> None:
    httpd = serve(port=0, scan_max=1)
    host, port = httpd.server_address[:2]
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        with urlopen(f"http://{host}:{port}/api/health") as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        assert payload["ok"] is True
        assert payload["service"] == "sce-af"
        assert payload["version"] == __version__
        with urlopen(f"http://{host}:{port}/api/version") as resp:
            ver = json.loads(resp.read().decode("utf-8"))
        assert ver["version"] == __version__
        with urlopen(f"http://{host}:{port}/") as resp:
            html = resp.read().decode("utf-8")
        assert 'id="app_version"' in html
        assert "SC_VERSION" not in html
    finally:
        httpd.shutdown()
        httpd.server_close()
