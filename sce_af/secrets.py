"""Read the DeepSeek key from a local api-key.md. Never log the value."""

from __future__ import annotations

import re
from pathlib import Path

from sce_af.paths import repo_root

_SK_RE = re.compile(r"sk-[A-Za-z0-9]+")


class MissingApiKey(RuntimeError):
    """api-key.md is missing or has no DeepSeek key."""


def api_key_path() -> Path:
    return repo_root() / "api-key.md"


def read_deepseek_key(path: Path | None = None) -> str:
    target = path or api_key_path()
    if not target.is_file():
        raise MissingApiKey("缺少 api-key.md。请在项目根放 DeepSeek 密钥，不要提交到 git。")
    text = target.read_text(encoding="utf-8")
    match = _SK_RE.search(text)
    if not match:
        raise MissingApiKey("api-key.md 里没有 DeepSeek 密钥（sk-…）。")
    return match.group(0)


def has_deepseek_key(path: Path | None = None) -> bool:
    try:
        read_deepseek_key(path)
        return True
    except MissingApiKey:
        return False
