#!/usr/bin/env python3
"""Copy a colleague-ready tree into release/ and zip it with a runtime .venv."""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

# --- CONFIG: fill when scaffolding. Do not rewrite copy/venv logic. ---
APP_SLUG = "sce-af"
DISPLAY_NAME = "SCE-af"
PACKAGE = "sce_af"
RUNTIME_IMPORTS = "import sce_af, pymupdf, PIL"
# --- end CONFIG ---

RELEASE_DIR = Path(__file__).resolve().parent
ROOT = RELEASE_DIR.parent

OPEN_COMMAND = f"打开{DISPLAY_NAME}.command"
OPEN_BAT = f"打开{DISPLAY_NAME}.bat"

ROOT_FILES = (
    "run.py",
    "requirements.txt",
    "setup_env.py",
    "setup.bat",
    "setup.command",
    OPEN_COMMAND,
    OPEN_BAT,
    ".gitignore",
)
DOC_MAP = (
    ("README.md", "README.md"),
    ("docs/03-log.md", "log.md"),
)
COPY_DIRS = ("web", PACKAGE)
SKIP_NAMES = {"__pycache__", ".DS_Store"}
NEVER_IN_DEST = (
    "testing_files",
    ".cursor",
    "release",
    "docs",
    "AGENTS.md",
    "api-key.md",
    "Raw",
    "tests",
    "requirements-dev.txt",
    "pyproject.toml",
)


def read_version(root: Path) -> str:
    init_py = root / PACKAGE / "__init__.py"
    if not init_py.is_file():
        sys.exit(f"cannot read __version__ from {PACKAGE}/__init__.py")
    text = init_py.read_text(encoding="utf-8")
    match = re.search(r'^__version__\s*=\s*[\'"]([^\'"]+)[\'"]', text, re.M)
    if not match:
        sys.exit(f"cannot read __version__ from {PACKAGE}/__init__.py")
    return match.group(1)


def ignore_junk(_dir: str, names: list[str]) -> list[str]:
    skipped = []
    for name in names:
        if name in SKIP_NAMES or name.endswith(".pyc"):
            skipped.append(name)
    return skipped


def fmt_size(nbytes: int) -> str:
    if nbytes < 1024:
        return f"{nbytes} B"
    if nbytes < 1024 * 1024:
        return f"{nbytes / 1024:.1f} KB"
    return f"{nbytes / (1024 * 1024):.1f} MB"


def assert_clean_dest(dest: Path) -> None:
    for name in NEVER_IN_DEST:
        if (dest / name).exists():
            sys.exit(f"refusing to pack {name}")
    for path in dest.rglob("*"):
        if ".venv" in path.parts:
            continue
        if path.name in SKIP_NAMES or path.suffix == ".pyc":
            sys.exit(f"refusing to pack {path.relative_to(dest).as_posix()}")


def venv_python(venv_dir: Path) -> Path:
    if sys.platform == "win32":
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"


def venv_usable(venv_dir: Path) -> bool:
    py = venv_python(venv_dir)
    return py.is_file() or py.is_symlink()


SKIP_VENV_PKG_KEYS = frozenset(
    {
        "pytest",
        "py",
        "pyinstaller",
        "pyinstaller-hooks-contrib",
        "altgraph",
        "macholib",
        "pefile",
        "pywin32-ctypes",
    }
)
UNINSTALL_PACKAGES = (
    "pytest",
    "py",
    "pyinstaller",
    "pyinstaller-hooks-contrib",
    "altgraph",
    "macholib",
    "pefile",
    "pywin32-ctypes",
)


def is_skipped_venv_pkg(name: str) -> bool:
    """True for pytest / PyInstaller (and their dist-info) so packed .venv stays runtime-only."""
    lower = name.lower()
    if lower.endswith(".dist-info"):
        lower = lower[: -len(".dist-info")].split("-", 1)[0]
    elif lower.endswith(".egg-info"):
        lower = lower[: -len(".egg-info")].split("-", 1)[0]
    key = lower.replace("_", "-").lstrip("-")
    return key in SKIP_VENV_PKG_KEYS


def ignore_venv(dirpath: str, names: list[str]) -> list[str]:
    skipped = ignore_junk(dirpath, names)
    parent = Path(dirpath)
    if parent.name != "site-packages" and "site-packages" not in parent.parts:
        return skipped
    for name in names:
        if is_skipped_venv_pkg(name) and name not in skipped:
            skipped.append(name)
    return skipped


def rewrite_venv_scripts(src_venv: Path, dest_venv: Path) -> None:
    """Point copied bin/Scripts shebangs at the packed venv, not the developer tree."""
    olds = {str(src_venv), str(src_venv.resolve())}
    new = str(dest_venv.resolve())
    bin_dir = dest_venv / ("Scripts" if sys.platform == "win32" else "bin")
    if not bin_dir.is_dir():
        return
    for path in bin_dir.iterdir():
        if path.is_symlink() or not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if not text.startswith("#!"):
            continue
        updated = text
        for old in sorted(olds, key=len, reverse=True):
            updated = updated.replace(old, new)
        if updated != text:
            path.write_text(updated, encoding="utf-8")


def strip_extra_packages(venv_dir: Path) -> None:
    py = venv_python(venv_dir)
    subprocess.run(
        [str(py), "-m", "pip", "uninstall", "-y", *UNINSTALL_PACKAGES],
        check=False,
    )


def verify_runtime_imports(venv_dir: Path) -> None:
    py = venv_python(venv_dir)
    subprocess.run([str(py), "-c", RUNTIME_IMPORTS], check=True)


def copy_local_venv(src_venv: Path, dest: Path, *, verify: bool = True) -> Path:
    """Copy the project .venv into the pack, omitting pytest / PyInstaller."""
    dest_venv = dest / ".venv"
    if dest_venv.exists():
        shutil.rmtree(dest_venv)
    print(f"venv:    copy {src_venv} -> {dest_venv}", flush=True)
    try:
        shutil.copytree(src_venv, dest_venv, symlinks=True, ignore=ignore_venv)
        rewrite_venv_scripts(src_venv, dest_venv)
        if verify:
            strip_extra_packages(dest_venv)
            verify_runtime_imports(dest_venv)
    except Exception:
        if dest_venv.exists():
            shutil.rmtree(dest_venv)
        raise
    _print_venv_ok()
    return dest_venv


def create_runtime_venv(dest: Path, python_exe: str | None = None) -> Path:
    """Build a runtime .venv from requirements.txt (no pip self-upgrade)."""
    req = dest / "requirements.txt"
    if not req.is_file():
        sys.exit("missing requirements.txt for runtime venv")
    venv_dir = dest / ".venv"
    if venv_dir.exists():
        shutil.rmtree(venv_dir)
    print(f"venv:    pip install -r {req.name}", flush=True)
    exe = python_exe or sys.executable
    try:
        subprocess.run([exe, "-m", "venv", str(venv_dir)], check=True)
    except subprocess.CalledProcessError as exc:
        sys.exit(f"venv create failed: {exc}")
    py = venv_python(venv_dir)
    if not py.is_file() and not py.is_symlink():
        sys.exit(f"venv python missing: {py}")
    try:
        subprocess.run(
            [str(py), "-m", "pip", "install", "-r", str(req)],
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        sys.exit(f"pip install into packed .venv failed: {exc}")
    _print_venv_ok()
    return venv_dir


def install_packed_venv(
    dest: Path,
    *,
    src_root: Path | None = None,
    python_exe: str | None = None,
    fresh: bool = False,
) -> Path:
    """Prefer copying ROOT/.venv; --fresh or missing/broken env falls back to pip."""
    src_venv = (src_root or ROOT) / ".venv"
    if not fresh and venv_usable(src_venv):
        try:
            return copy_local_venv(src_venv, dest)
        except Exception as exc:  # noqa: BLE001
            print(f"venv copy failed ({exc}); falling back to pip install", flush=True)
    return create_runtime_venv(dest, python_exe=python_exe)


def _print_venv_ok() -> None:
    print(
        f"venv ok: {sys.platform} / Python {sys.version.split()[0]}",
        flush=True,
    )
    print(
        "note:    this .venv matches the pack machine OS/arch. "
        "Pack the Windows zip on Windows; pack the Mac zip on a Mac.",
        flush=True,
    )


def copy_tree(src: Path, dest: Path) -> None:
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)

    missing = [name for name in ROOT_FILES if not (src / name).is_file()]
    missing += [src_rel for src_rel, _ in DOC_MAP if not (src / src_rel).is_file()]
    if missing:
        sys.exit("missing files: " + ", ".join(missing))

    for name in ROOT_FILES:
        shutil.copy2(src / name, dest / name)
    for src_rel, dest_name in DOC_MAP:
        shutil.copy2(src / src_rel, dest / dest_name)

    for name in COPY_DIRS:
        src_dir = src / name
        if not src_dir.is_dir():
            sys.exit(f"missing directory: {name}")
        shutil.copytree(src_dir, dest / name, ignore=ignore_junk)

    (dest / "output").mkdir()
    assert_clean_dest(dest)
    packed = read_version(dest)
    expected = read_version(src)
    if packed != expected:
        sys.exit(f"packed version {packed!r} != source {expected!r}")
    assert_readme_mentions_version(dest, expected)


def assert_readme_mentions_version(dest: Path, version: str) -> None:
    readme = dest / "README.md"
    if not readme.is_file():
        sys.exit("missing packed README.md")
    marker = f"v{version}"
    if marker not in readme.read_text(encoding="utf-8"):
        sys.exit(f"packed README.md does not mention {marker}")


def zip_tree(folder: Path, zip_path: Path) -> int:
    if zip_path.exists():
        zip_path.unlink()
    root_name = folder.name
    file_count = 0
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(root_name + "/", "")
        for path in sorted(folder.rglob("*")):
            if path.name in SKIP_NAMES or path.suffix == ".pyc":
                continue
            rel = path.relative_to(folder).as_posix()
            arc = f"{root_name}/{rel}"
            if path.is_dir():
                zf.writestr(arc + "/", "")
            else:
                zf.write(path, arc)
                file_count += 1
    return file_count


def is_unc_path(path: Path) -> bool:
    text = str(path)
    return text.startswith("\\\\") or text.startswith("//")


def needs_local_stage(root: Path, cwd: Path | None = None) -> bool:
    if sys.platform != "win32":
        return False
    if is_unc_path(root):
        return True
    here = Path(cwd) if cwd is not None else Path.cwd()
    text = str(here).replace("/", "\\").rstrip("\\").lower()
    win_dir = "c:\\windows"
    return text == win_dir or text.startswith(win_dir + "\\")


def choose_stage_dir() -> Path:
    candidates = [Path(rf"C:\{APP_SLUG}-pack")]
    local = os.environ.get("LOCALAPPDATA", "").strip()
    if local:
        candidates.append(Path(local) / f"{APP_SLUG}-build")
    last_err: OSError | None = None
    for path in candidates:
        try:
            path.mkdir(parents=True, exist_ok=True)
            probe = path / ".pp_write"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink(missing_ok=True)
            return path
        except OSError as exc:
            last_err = exc
    sys.exit(f"cannot create staging dir: {last_err}")


def folder_name_for(version: str) -> str:
    suffix = "-win64" if sys.platform == "win32" else ""
    return f"{DISPLAY_NAME} v{version}{suffix}"


def pack_into(src: Path, dest_dir: Path, *, fresh: bool) -> tuple[Path, Path]:
    version = read_version(src)
    name = folder_name_for(version)
    dest = dest_dir / name
    zip_path = dest_dir / f"{name}.zip"
    print(f"version: {version}")
    print(f"source:  {src}")
    copy_tree(src, dest)
    install_packed_venv(dest, src_root=src, fresh=fresh)
    nfiles = zip_tree(dest, zip_path)
    print(f"folder:  {dest}")
    print(f"zip:     {zip_path} ({fmt_size(zip_path.stat().st_size)}, {nfiles} files)")
    return dest, zip_path


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description=f"Pack {DISPLAY_NAME} source zip with a runtime .venv"
    )
    parser.add_argument(
        "--fresh",
        action="store_true",
        help="Rebuild packed .venv with pip instead of copying the local environment",
    )
    args = parser.parse_args(argv)
    origin = ROOT
    stage: Path | None = None
    try:
        if needs_local_stage(origin):
            print(
                "UNC or System32 cwd: pack on a local disk, then copy the zip back.",
                flush=True,
            )
            stage = choose_stage_dir()
            print(f"staging: {stage}", flush=True)
            _, zip_path = pack_into(origin, stage, fresh=args.fresh)
            RELEASE_DIR.mkdir(parents=True, exist_ok=True)
            shipped = RELEASE_DIR / zip_path.name
            shutil.copy2(zip_path, shipped)
            print(f"copied:  {shipped}", flush=True)
            return
        pack_into(origin, RELEASE_DIR, fresh=args.fresh)
    finally:
        if stage is not None and stage.exists():
            shutil.rmtree(stage, ignore_errors=True)


if __name__ == "__main__":
    main()
