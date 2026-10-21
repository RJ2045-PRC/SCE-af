"""Source-zip pack helpers: version, whitelist, forbidden entries, venv copy."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import pytest

from sce_af import __version__

ROOT = Path(__file__).resolve().parents[1]
RELEASE = ROOT / "release"
if str(RELEASE) not in sys.path:
    sys.path.insert(0, str(RELEASE))

from pack import (  # noqa: E402
    COPY_DIRS,
    DISPLAY_NAME,
    DOC_MAP,
    NEVER_IN_DEST,
    OPEN_BAT,
    OPEN_COMMAND,
    PACKAGE,
    ROOT_FILES,
    assert_clean_dest,
    assert_readme_mentions_version,
    copy_local_venv,
    copy_tree,
    create_runtime_venv,
    folder_name_for,
    ignore_venv,
    install_packed_venv,
    is_skipped_venv_pkg,
    is_unc_path,
    needs_local_stage,
    read_version,
    rewrite_venv_scripts,
    venv_python,
)


def test_read_version_from_init() -> None:
    assert read_version(ROOT) == __version__
    assert PACKAGE == "sce_af"
    assert DISPLAY_NAME == "SCE-af"


def test_read_version_missing_exits() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / PACKAGE).mkdir()
        (root / PACKAGE / "__init__.py").write_text("# no version\n", encoding="utf-8")
        with pytest.raises(SystemExit) as ctx:
            read_version(root)
        assert "__version__" in str(ctx.value)


def test_doc_map_targets() -> None:
    assert DOC_MAP == (
        ("README.md", "README.md"),
        ("docs/03-log.md", "log.md"),
    )


def test_assert_clean_dest_rejects_forbidden() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        dest = Path(tmp)
        (dest / "tests").mkdir()
        with pytest.raises(SystemExit) as ctx:
            assert_clean_dest(dest)
        assert "tests" in str(ctx.value)


def test_assert_clean_dest_allows_venv() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        dest = Path(tmp)
        (dest / ".venv" / "__pycache__").mkdir(parents=True)
        (dest / ".venv" / "x.pyc").write_bytes(b"")
        assert_clean_dest(dest)


def test_copy_tree_whitelist_and_empty_output() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        dest = Path(tmp) / "out"
        copy_tree(ROOT, dest)
        assert (dest / "run.py").is_file()
        assert (dest / OPEN_COMMAND).is_file()
        assert (dest / OPEN_BAT).is_file()
        assert (dest / "README.md").is_file()
        assert (dest / "log.md").is_file()
        assert (dest / "web" / "app.js").is_file()
        assert (dest / PACKAGE).is_dir()
        assert (dest / "output").is_dir()
        assert not any((dest / "output").iterdir())
        assert not (dest / ".venv").exists()
        assert not (dest / "docs").exists()
        assert not (dest / "release").exists()
        assert not (dest / "tests").exists()
        assert not (dest / "AGENTS.md").exists()
        assert not (dest / "requirements-dev.txt").exists()
        assert not (dest / "pyproject.toml").exists()
        assert (dest / PACKAGE / "__init__.py").is_file()
        assert read_version(dest) == __version__
        assert "SC_VERSION" not in (dest / "web" / "app.js").read_text(encoding="utf-8")
        assert 'id="app_version"' in (dest / "web" / "index.html").read_text(
            encoding="utf-8"
        )
        assert f"v{__version__}" in (dest / "README.md").read_text(encoding="utf-8")
        assert COPY_DIRS == ("web", PACKAGE)


def test_assert_readme_mentions_version() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        dest = Path(tmp)
        (dest / "README.md").write_text("hello\n", encoding="utf-8")
        with pytest.raises(SystemExit) as ctx:
            assert_readme_mentions_version(dest, "0.1.0")
        assert "v0.1.0" in str(ctx.value)
        (dest / "README.md").write_text(f"# {DISPLAY_NAME} v0.1.0\n", encoding="utf-8")
        assert_readme_mentions_version(dest, "0.1.0")


def test_venv_not_in_never_list() -> None:
    assert ".venv" not in NEVER_IN_DEST
    assert OPEN_COMMAND in ROOT_FILES
    assert OPEN_BAT in ROOT_FILES
    assert "requirements.txt" in ROOT_FILES
    assert "requirements-dev.txt" not in ROOT_FILES
    assert "tests" in NEVER_IN_DEST


def test_runtime_requirements_exclude_pytest() -> None:
    runtime = (ROOT / "requirements.txt").read_text(encoding="utf-8")
    dev = (ROOT / "requirements-dev.txt").read_text(encoding="utf-8")
    assert "pytest" not in runtime.lower()
    assert "-r requirements.txt" in dev
    assert "pytest" in dev.lower()


def test_folder_name_suffix(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("pack.sys.platform", "darwin")
    assert folder_name_for("0.1.0") == f"{DISPLAY_NAME} v0.1.0"
    monkeypatch.setattr("pack.sys.platform", "win32")
    assert folder_name_for("0.1.0") == f"{DISPLAY_NAME} v0.1.0-win64"


def test_unc_and_stage_detection() -> None:
    assert is_unc_path(Path(r"\\Mac\Home\proj"))
    assert not is_unc_path(Path(r"C:\proj"))


def test_needs_local_stage_windows_unc(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("pack.sys.platform", "win32")
    assert needs_local_stage(Path(r"\\Mac\Home\proj"), cwd=Path(r"C:\Users\me"))
    monkeypatch.setattr("pack.sys.platform", "darwin")
    assert not needs_local_stage(Path(r"\\Mac\Home\proj"))


def test_create_runtime_venv(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []

    def fake_run(cmd, check=True):  # noqa: ARG001
        calls.append([str(c) for c in cmd])
        if "-m" in cmd:
            idx = cmd.index("-m")
            if idx + 2 < len(cmd) and cmd[idx + 1] == "venv":
                dest = Path(cmd[idx + 2])
                py = venv_python(dest)
                py.parent.mkdir(parents=True, exist_ok=True)
                py.write_text("", encoding="utf-8")

        class Result:
            returncode = 0

        return Result()

    monkeypatch.setattr("pack.subprocess.run", fake_run)
    with tempfile.TemporaryDirectory() as tmp:
        dest = Path(tmp)
        (dest / "requirements.txt").write_text("# runtime\n", encoding="utf-8")
        created = create_runtime_venv(dest, python_exe="/usr/bin/python3")
        assert created == dest / ".venv"
    assert any(len(c) >= 3 and c[1] == "-m" and c[2] == "venv" for c in calls)
    assert any("pip" in c and "-r" in c for c in calls)
    assert not any(len(c) >= 6 and c[3:6] == ["install", "-U", "pip"] for c in calls)


def test_create_runtime_venv_missing_requirements() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        with pytest.raises(SystemExit) as ctx:
            create_runtime_venv(Path(tmp))
        assert "requirements.txt" in str(ctx.value)


def test_is_skipped_venv_pkg() -> None:
    assert is_skipped_venv_pkg("pytest")
    assert is_skipped_venv_pkg("_pytest")
    assert is_skipped_venv_pkg("pytest-8.0.0.dist-info")
    assert is_skipped_venv_pkg("PyInstaller")
    assert not is_skipped_venv_pkg("openpyxl")
    assert not is_skipped_venv_pkg("pygments")


def test_ignore_venv_skips_pytest_in_site_packages() -> None:
    skipped = ignore_venv(
        "/tmp/lib/python3.9/site-packages",
        ["flask", "pytest", "pytest-8.0.0.dist-info", "PyInstaller"],
    )
    assert "pytest" in skipped
    assert "pytest-8.0.0.dist-info" in skipped
    assert "PyInstaller" in skipped
    assert "flask" not in skipped


def test_copy_local_venv_skips_extras_and_rewrites_shebang(tmp_path: Path) -> None:
    # pack.py only rewrites shebangs under bin/ (POSIX) or Scripts/ (Windows);
    # the fixture must use the same name the product uses on this platform.
    script_dir = "Scripts" if sys.platform == "win32" else "bin"
    src = tmp_path / "src" / ".venv"
    site = src / "lib" / "python3.9" / "site-packages"
    (site / "demo").mkdir(parents=True)
    (site / "demo" / "__init__.py").write_text("ok\n", encoding="utf-8")
    (site / "pytest").mkdir()
    (site / "pytest" / "__init__.py").write_text("no\n", encoding="utf-8")
    (site / "pytest-8.0.0.dist-info").mkdir()
    (site / "PyInstaller").mkdir()
    bindir = src / script_dir
    bindir.mkdir()
    (bindir / "python").write_text("", encoding="utf-8")
    (bindir / "pip").write_text(f"#!{src.resolve()}/{script_dir}/python\n", encoding="utf-8")
    dest = tmp_path / "out"
    dest.mkdir()
    copied = copy_local_venv(src, dest, verify=False)
    assert copied == dest / ".venv"
    dest_site = dest / ".venv" / "lib" / "python3.9" / "site-packages"
    assert (dest_site / "demo" / "__init__.py").is_file()
    assert not (dest_site / "pytest").exists()
    assert not (dest_site / "pytest-8.0.0.dist-info").exists()
    assert not (dest_site / "PyInstaller").exists()
    pip_text = (dest / ".venv" / script_dir / "pip").read_text(encoding="utf-8")
    assert str((dest / ".venv").resolve()) in pip_text
    assert str(src.resolve()) not in pip_text


def test_rewrite_venv_scripts_only_shebang_text(tmp_path: Path) -> None:
    script_dir = "Scripts" if sys.platform == "win32" else "bin"
    src = tmp_path / "old" / ".venv"
    dest = tmp_path / "new" / ".venv"
    (dest / script_dir).mkdir(parents=True)
    script = dest / script_dir / "tool"
    script.write_text(f"#!{src}/{script_dir}/python\nprint(1)\n", encoding="utf-8")
    rewrite_venv_scripts(src, dest)
    text = script.read_text(encoding="utf-8")
    assert str(dest.resolve()) in text
    assert str(src) not in text


def test_install_packed_venv_copies_local(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    copied: list[Path] = []

    def fake_copy(src_venv: Path, dest: Path, *, verify: bool = True):  # noqa: ARG001
        copied.append(src_venv)
        out = dest / ".venv"
        out.mkdir()
        return out

    monkeypatch.setattr("pack.copy_local_venv", fake_copy)
    monkeypatch.setattr(
        "pack.create_runtime_venv",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("pip should not run")),
    )
    src_root = tmp_path / "root"
    py = venv_python(src_root / ".venv")
    py.parent.mkdir(parents=True)
    py.write_text("", encoding="utf-8")
    dest = tmp_path / "out"
    dest.mkdir()
    result = install_packed_venv(dest, src_root=src_root)
    assert result == dest / ".venv"
    assert copied == [src_root / ".venv"]


def test_install_packed_venv_fresh_uses_pip(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    pip_dests: list[Path] = []

    def fake_create(dest: Path, python_exe=None):  # noqa: ARG001
        pip_dests.append(dest)
        return dest / ".venv"

    monkeypatch.setattr("pack.create_runtime_venv", fake_create)
    monkeypatch.setattr(
        "pack.copy_local_venv",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("copy should not run")),
    )
    src_root = tmp_path / "root"
    py = venv_python(src_root / ".venv")
    py.parent.mkdir(parents=True)
    py.write_text("", encoding="utf-8")
    dest = tmp_path / "out"
    dest.mkdir()
    install_packed_venv(dest, src_root=src_root, fresh=True)
    assert pip_dests == [dest]


def test_install_packed_venv_without_local_uses_pip(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    pip_dests: list[Path] = []

    def fake_create(dest: Path, python_exe=None):  # noqa: ARG001
        pip_dests.append(dest)
        return dest / ".venv"

    monkeypatch.setattr("pack.create_runtime_venv", fake_create)
    dest = tmp_path / "out"
    dest.mkdir()
    install_packed_venv(dest, src_root=tmp_path / "empty")
    assert pip_dests == [dest]
