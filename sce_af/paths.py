"""Repo root and web dir."""

from __future__ import annotations

from pathlib import Path


def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def web_dir() -> Path:
    return repo_root() / "web"


def data_root() -> Path:
    return repo_root()
