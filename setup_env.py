#!/usr/bin/env python3
"""Create or update the project's virtual environment."""

from __future__ import annotations

import subprocess
import sys
import venv
from pathlib import Path


ROOT = Path(__file__).resolve().parent
VENV = ROOT / ".venv"


def venv_python() -> Path:
    if sys.platform == "win32":
        return VENV / "Scripts" / "python.exe"
    return VENV / "bin" / "python"


def _newer_python() -> str | None:
    from shutil import which

    for name in ("python3.13", "python3.12", "python3.11", "python3.10"):
        found = which(name)
        if found:
            return found
    return None


def main() -> int:
    if sys.version_info < (3, 10):
        newer = _newer_python()
        if newer and Path(newer).resolve() != Path(sys.executable).resolve():
            return subprocess.call([newer, str(Path(__file__).resolve()), *sys.argv[1:]])
        sys.stderr.write("Need Python 3.10+.\n")
        return 1
    print(f"Creating virtual environment: {VENV}")
    venv.EnvBuilder(with_pip=True).create(VENV)
    python = venv_python()
    subprocess.run([str(python), "-m", "pip", "install", "-U", "pip"], check=True)
    subprocess.run(
        [str(python), "-m", "pip", "install", "-r", str(ROOT / "requirements.txt")],
        check=True,
    )
    print(f"Ready. Run: {python} run.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
