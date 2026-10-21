"""Merge slice JSON, parse tolerances in code, collect issues."""

from __future__ import annotations

from collections import Counter
from typing import Any

from sce_af.ids import merge_header
from sce_af.limits import enrich_bubble
from sce_af.vision import normalize_bubble, normalize_notes, normalize_special


def _issue(code: str, message: str, **extra: Any) -> dict[str, Any]:
    payload = {"code": code, "message": message}
    payload.update(extra)
    return payload


def merge_job(
    filename: str,
    title_raw: dict | None,
    bubble_raws: list[tuple[int, dict]],
    notes_raws: list[tuple[int, dict]],
) -> dict[str, Any]:
    header = merge_header(filename, title_raw)
    issues: list[dict[str, Any]] = []
    if not header["mold_no"]:
        issues.append(_issue("missing_mold_no", "没有读到模号（LG- 后接字母或数字）。"))
    if not header["part_no"]:
        issues.append(_issue("missing_part_no", "没有读到料号（P 后接数字）。"))
    if not header["customer"]:
        issues.append(_issue("missing_customer", "标题栏没有客户名称，请手改。"))
    if not header["part_name"]:
        issues.append(_issue("missing_part_name", "标题栏没有品名，请手改。"))

    bubbles = []
    for page, raw in bubble_raws:
        item = enrich_bubble(normalize_bubble(raw, page))
        crop = str((raw or {}).get("crop") or "").strip()
        if crop:
            item["crop"] = crop
        if not item["num"]:
            issues.append(_issue("bubble_missing_num", "有气泡没有读到编号。", page=page))
        if not item["description"]:
            issues.append(
                _issue("bubble_missing_desc", f"气泡 {item['num'] or '?'} 没有描述。", page=page)
            )
        elif item["nominal"] is None and item["upper"] is None:
            issues.append(
                _issue(
                    "bubble_parse_fail",
                    f"气泡 {item['num'] or '?'} 的公差没能从描述解析。",
                    page=page,
                    description=item["description"],
                )
            )
        bubbles.append(item)

    nums = [b["num"] for b in bubbles if b["num"]]
    counts = Counter(nums)
    for num, n in sorted(counts.items()):
        if n > 1:
            issues.append(_issue("duplicate_num", f"气泡号 {num} 出现了 {n} 次。"))

    notes: list[dict] = []
    characteristics: list[dict] = []
    for page, raw in notes_raws:
        chunk = normalize_notes(raw, page)
        notes.extend(chunk["notes"])
        characteristics.extend(chunk["characteristics"])

    char_keys = set()
    for row in characteristics:
        if row.get("sc_no"):
            char_keys.add(("SC", str(row["sc_no"]).lstrip("0") or "0"))
        if row.get("cc_no"):
            char_keys.add(("CC", str(row["cc_no"]).lstrip("0") or "0"))

    for bubble in bubbles:
        if bubble["special"] not in ("SC", "CC"):
            continue
        key = (bubble["special"], str(bubble["special_no"]).lstrip("0") or "0")
        if not bubble["special_no"]:
            issues.append(
                _issue(
                    "special_no_missing",
                    f"气泡 {bubble['num']} 标了 {bubble['special']} 但没有特性号。",
                    page=bubble.get("page"),
                )
            )
            continue
        if char_keys and key not in char_keys:
            issues.append(
                _issue(
                    "special_unmatched",
                    f"气泡 {bubble['num']} 的 {bubble['special']} {bubble['special_no']} 在特性表里对不上。",
                    page=bubble.get("page"),
                )
            )

    bubbles.sort(key=lambda b: _num_key(b["num"]))
    return {
        "header": header,
        "bubbles": bubbles,
        "requirements": {"notes": notes, "characteristics": characteristics},
        "issues": issues,
    }


def _num_key(num: str) -> tuple:
    text = str(num or "")
    digits = "".join(ch for ch in text if ch.isdigit())
    return (0, int(digits), text) if digits else (1, 0, text)


def apply_header_edits(doc: dict, edits: dict) -> dict:
    header = dict(doc.get("header") or {})
    for key in ("customer", "part_name", "mold_no", "part_no", "drawing_no", "revision"):
        if key in edits and edits[key] is not None:
            header[key] = str(edits[key]).strip()
    out = dict(doc)
    out["header"] = header
    return out


def _as_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def apply_bubble_edits(doc: dict, rows: list[dict] | None) -> dict:
    """Apply row edits. Description changes recompute bounds unless the three numbers also changed."""
    bubbles = [dict(item) for item in doc.get("bubbles") or []]
    for index, edit in enumerate(rows or []):
        if index >= len(bubbles) or not isinstance(edit, dict):
            continue
        old = bubbles[index]
        new = dict(old)
        if "num" in edit and edit["num"] is not None:
            new["num"] = str(edit["num"]).strip()
        if "special" in edit and edit["special"] is not None:
            new["special"] = normalize_special(edit["special"])
            if new["special"] == "NA":
                new["special_no"] = ""
        if "description" in edit and edit["description"] is not None:
            new["description"] = str(edit["description"]).strip()
        desc_changed = new.get("description") != old.get("description")
        bounds_changed = False
        incoming = {}
        for key in ("min_val", "std_val", "max_val"):
            if key in edit:
                incoming[key] = _as_float(edit[key])
                if incoming[key] != _as_float(old.get(key)):
                    bounds_changed = True
        crop = old.get("crop") or ""
        if desc_changed and not bounds_changed:
            new = enrich_bubble(new)
        elif bounds_changed:
            new.update(incoming)
        if crop:
            new["crop"] = crop
        bubbles[index] = new
    out = dict(doc)
    out["bubbles"] = bubbles
    return out
