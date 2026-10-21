"""Split a compact dimension / GD&T description into nominal / upper / lower.

Logic follows SCE ``parse.parse_limits`` / ``bounds_from_limits``. This copy
does not import the SCE package.
"""

from __future__ import annotations

import re
from typing import Optional

from sce_af.gdt_types import GDT_TYPES, LINEAR_TYPE

_DIA_CHARS = "φΦϕøØ⌀"
_QTY_RE = re.compile(r"^\s*(\d+)\s*[xX×*＊]\s*")
_PLUS_MINUS_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*\+\s*(\d+(?:\.\d+)?)\s*/?\s*[-−]\s*(\d+(?:\.\d+)?)"
)
_SIGNED_NUM = r"[+\-−]\s*\d+(?:\.\d+)?"
_SIGNED_PAIR_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*(" + _SIGNED_NUM + r")\s*/?\s*(" + _SIGNED_NUM + r")"
)
_NOMINAL_UP_MINUS_LO_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s+(\d+(?:\.\d+)?)\s*[-−]\s*(\d+(?:\.\d+)?)\s*$"
)
_PENDING_DESC = "识别中…"


def normalize_ocr(text: str) -> str:
    t = (text or "").replace("\u2212", "-").replace("\uff0b", "+")
    t = t.replace("Ø", "φ").replace("ø", "φ").replace("Φ", "φ").replace("ϕ", "φ")
    t = t.replace("⌀", "φ")
    t = t.replace("º", "°").replace("˚", "°")
    t = t.replace(",", ".")
    t = re.sub(r"^(\s*\d+)\s*[*＊]", r"\1×", t)
    t = re.sub(r"[Oo](?=\d)", "0", t)
    t = re.sub(r"(?<=\d)[Oo](?=\d)", "0", t)
    t = t.replace("l", "1").replace("I", "1").replace("|", "1")
    t = re.sub(r"[^\dφ±+\-.\sA-Za-z°×]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def extract_qty_prefix(text: str) -> tuple[str, str]:
    t = text or ""
    match = _QTY_RE.match(t)
    if not match:
        return "", t
    return f"{match.group(1)}X", t[match.end() :]


def type_from_description(desc: str) -> str:
    _, rest = extract_qty_prefix(desc or "")
    compact = re.sub(r"\s+", "", rest or desc or "")
    best = LINEAR_TYPE
    n = 0
    for name in GDT_TYPES:
        if compact.startswith(name) and len(name) > n:
            best = name
            n = len(name)
    return best


def _to_num(s: str | float | None) -> Optional[float]:
    if s is None or s == "":
        return None
    if isinstance(s, (int, float)):
        return float(s)
    try:
        return float(str(s).strip())
    except (TypeError, ValueError):
        return None


def _ensure_sign(s: str) -> str:
    t = str(s or "").replace("−", "-").replace(" ", "")
    if not t:
        return t
    if t[0] not in "+-":
        return "+" + t
    return t


def _token_float(s: str) -> float:
    return float(_ensure_sign(s))


def _sort_signed_tokens(a: str, b: str) -> tuple[str, str]:
    a = _ensure_sign(a)
    b = _ensure_sign(b)
    if _token_float(a) >= _token_float(b):
        return a, b
    return b, a


def _linear_nominal_plus_minus(a: str, b: str, c: str) -> tuple[str, str, str]:
    nums = [a, b, c]
    try:
        vals = [float(x) for x in nums]
    except (TypeError, ValueError):
        return a, b, c
    max_i = max(range(3), key=lambda i: vals[i])
    nom = nums[max_i]
    rest = [nums[i] for i in range(3) if i != max_i]
    return nom, rest[0], rest[1]


def _linear_nominal_signed(a: str, b: str, c: str) -> tuple[str, str, str]:
    toks = [a, b, c]
    try:
        vals = [_token_float(x) for x in toks]
    except (TypeError, ValueError):
        up, lo = _sort_signed_tokens(b, c)
        return a, up, lo
    max_i = max(range(3), key=lambda i: vals[i])
    nom = _ensure_sign(toks[max_i])
    if nom.startswith("+"):
        nom = nom[1:]
    rest = [_ensure_sign(toks[i]) for i in range(3) if i != max_i]
    up, lo = _sort_signed_tokens(rest[0], rest[1])
    return nom, up, lo


def _limits_plus_minus_mags(
    nom: Optional[float], up_mag: Optional[float], lo_mag: Optional[float]
) -> dict:
    lo = -lo_mag if lo_mag else (0.0 if lo_mag is not None else None)
    return {"nominal": nom, "upper": up_mag, "lower": lo}


def parse_limits(description: str, kind: Optional[str] = None) -> dict:
    empty = {"nominal": None, "upper": None, "lower": None}
    desc = (description or "").strip()
    if not desc or desc == _PENDING_DESC:
        return empty
    kind = (kind or "").strip() or type_from_description(desc)
    is_gdt = kind != LINEAR_TYPE
    compact = re.sub(r"\s+", "", desc)
    if kind and compact.startswith(kind):
        mkind = re.match(re.escape(kind) + r"\s*", desc)
        t = desc[mkind.end() :] if mkind else compact[len(kind) :]
    else:
        t = desc
    t = normalize_ocr(t)
    _, t = extract_qty_prefix(t)
    t = t.replace("φ", "").strip()
    t = re.sub(r"\s+", " ", t)

    match = re.search(r"(\d+(?:\.\d+)?)\s*±\s*(\d+(?:\.\d+)?)", t)
    if match:
        tol = _to_num(match.group(2))
        return {
            "nominal": _to_num(match.group(1)),
            "upper": tol,
            "lower": -tol if tol else 0.0,
        }

    match = _SIGNED_PAIR_RE.search(t)
    if match:
        nom, up, lo = _linear_nominal_signed(match.group(1), match.group(2), match.group(3))
        if is_gdt:
            up, lo = _sort_signed_tokens(match.group(2), match.group(3))
            nom = match.group(1)
        return {
            "nominal": _to_num(nom),
            "upper": _to_num(up),
            "lower": _to_num(lo),
        }

    match = _PLUS_MINUS_RE.search(t)
    if match:
        if is_gdt:
            return _limits_plus_minus_mags(
                _to_num(match.group(1)), _to_num(match.group(2)), _to_num(match.group(3))
            )
        nom, up, lo = _linear_nominal_plus_minus(match.group(1), match.group(2), match.group(3))
        return _limits_plus_minus_mags(_to_num(nom), _to_num(up), _to_num(lo))

    match = re.search(
        r"(\d+(?:\.\d+)?)\s*\+\s*(\d+(?:\.\d+)?)\s+(\d+(?:\.\d+)?)",
        t,
    )
    if match:
        if is_gdt:
            return _limits_plus_minus_mags(
                _to_num(match.group(1)), _to_num(match.group(2)), _to_num(match.group(3))
            )
        nom, up, lo = _linear_nominal_plus_minus(match.group(1), match.group(2), match.group(3))
        return _limits_plus_minus_mags(_to_num(nom), _to_num(up), _to_num(lo))

    match = re.search(r"(\d+(?:\.\d+)?)\s*\+\s*(\d+(?:\.\d+)?)\s*$", t)
    if match:
        return {
            "nominal": _to_num(match.group(1)),
            "upper": _to_num(match.group(2)),
            "lower": 0.0,
        }

    match = _NOMINAL_UP_MINUS_LO_RE.search(t)
    if match:
        return _limits_plus_minus_mags(
            _to_num(match.group(1)), _to_num(match.group(2)), _to_num(match.group(3))
        )

    match = re.search(r"(\d+(?:\.\d+)?)\s*[-−]\s*(\d+(?:\.\d+)?)\s*$", t)
    if match and not is_gdt:
        mag = _to_num(match.group(2))
        return {
            "nominal": _to_num(match.group(1)),
            "upper": 0.0,
            "lower": -mag if mag else 0.0,
        }

    nums = re.findall(r"\d+(?:\.\d+)?", t)
    if not nums:
        return empty
    if is_gdt:
        return {"nominal": 0.0, "upper": _to_num(nums[0]), "lower": 0.0}
    if len(nums) >= 3:
        nom, up, lo = _linear_nominal_plus_minus(nums[0], nums[1], nums[2])
        return _limits_plus_minus_mags(_to_num(nom), _to_num(up), _to_num(lo))
    if len(nums) == 2:
        tol = _to_num(nums[1])
        return {"nominal": _to_num(nums[0]), "upper": tol, "lower": -tol if tol else 0.0}
    return {"nominal": _to_num(nums[0]), "upper": 0.0, "lower": 0.0}


def bounds_from_limits(nominal, upper=None, lower=None) -> dict:
    empty = {"min_val": None, "std_val": None, "max_val": None}
    n = _to_num(nominal)
    if n is None:
        return empty
    u = _to_num(upper)
    l = _to_num(lower)
    if u is None:
        u = 0.0
    if l is None:
        l = 0.0
    return {"min_val": n + l, "std_val": n, "max_val": n + u}


def enrich_bubble(item: dict) -> dict:
    """Add parsed limits onto a bubble dict. Does not trust model-written numbers."""
    kind = str(item.get("type") or LINEAR_TYPE).strip() or LINEAR_TYPE
    desc = str(item.get("description") or "").strip()
    limits = parse_limits(desc, kind)
    bounds = bounds_from_limits(limits["nominal"], limits["upper"], limits["lower"])
    if kind != LINEAR_TYPE:
        # GD&T: std is the spec value (upper), min stays 0 unless signed pair.
        bounds = {
            "min_val": limits["lower"],
            "std_val": limits["nominal"],
            "max_val": limits["upper"],
        }
    out = dict(item)
    out["type"] = kind
    out["description"] = desc
    out["nominal"] = limits["nominal"]
    out["upper"] = limits["upper"]
    out["lower"] = limits["lower"]
    out.update(bounds)
    return out
