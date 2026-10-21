#!/usr/bin/env python3
"""Start the local SCE-af web UI on 127.0.0.1."""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sce_af.app import DEFAULT_PORT, HOST, AlreadyRunning, serve
from sce_af.open_page import open_app_page


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="SCE-af local web UI")
    parser.add_argument("--host", default=HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="do not open the system browser",
    )
    args = parser.parse_args(argv)

    try:
        httpd = serve(host=args.host, port=args.port)
    except AlreadyRunning as exc:
        print(f"已在运行。切到已打开的页面 {exc.url}", flush=True)
        if not args.no_browser:
            open_app_page(exc.url, delay=False)
            time.sleep(1.8)
        return 0

    host, port = httpd.server_address[:2]
    url = f"http://{host}:{port}/"
    print(f"SCE-af: {url}")
    print("按 Ctrl+C 结束。")
    if not args.no_browser:
        open_app_page(url, delay=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止")
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
