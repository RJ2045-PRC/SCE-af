"""Mold / part numbers from a filename or a title-block string."""

from __future__ import annotations

import re
from pathlib import Path

# LG- then digits or letters, e.g. LG-26554 / LG-PT26500
MOLD_RE = re.compile(r"LG-[A-Z0-9]+", re.IGNORECASE)
# P then digits, e.g. P000005766001
PART_RE = re.compile(r"\bP\d+\b")


def mold_from_text(text: str) -> str:
    match = MOLD_RE.search(text or "")
    if not match:
        return ""
    return match.group(0).upper().replace("LG-", "LG-", 1)


def part_from_text(text: str) -> str:
    match = PART_RE.search(text or "")
    return match.group(0).upper() if match else ""


def ids_from_filename(name: str) -> dict[str, str]:
    stem = Path(name or "").name
    return {
        "filename": Path(name or "").name,
        "mold_no": mold_from_text(stem),
        "part_no": part_from_text(stem),
    }


def merge_header(filename: str, vision: dict | None = None) -> dict[str, str]:
    """Filename wins for mold/part when it matches the rules; vision fills the rest."""
    file_ids = ids_from_filename(filename)
    seen = vision or {}
    mold = file_ids["mold_no"] or mold_from_text(str(seen.get("mold_no") or ""))
    part = file_ids["part_no"] or part_from_text(str(seen.get("part_no") or seen.get("drawing_no") or ""))
    drawing = str(seen.get("drawing_no") or "").strip()
    if not drawing and part:
        drawing = part
    return {
        "filename": file_ids["filename"],
        "customer": str(seen.get("customer") or "").strip(),
        "part_name": str(seen.get("part_name") or "").strip(),
        "mold_no": mold,
        "part_no": part,
        "drawing_no": drawing,
        "revision": str(seen.get("revision") or "").strip(),
    }
