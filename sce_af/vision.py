"""One-slice DeepSeek vision calls. Each request carries a small PNG, not a PDF."""

from __future__ import annotations

import base64
import json
import re
import urllib.error
import urllib.request
from typing import Any, Callable

from sce_af.gdt_types import ALLOWED_TYPES, LINEAR_TYPE, SPECIALS
from sce_af.secrets import read_deepseek_key

DEEPSEEK_URL = "https://api.deepseek.com/chat/completions"
DEEPSEEK_MODEL = "deepseek-flash"

TITLE_PROMPT = (
    "这是2D图纸标题栏截图。只输出一个 JSON Object，不要 Markdown。"
    '字段：{"customer":"客户/公司","part_name":"品名","mold_no":"模号LG-…",'
    '"part_no":"料号P加数字","drawing_no":"图号","revision":"版本"}。'
    "看不清就写空字符串。模号必须是 LG- 后接字母或数字；料号必须是 P 后接数字。"
)

NOTES_PROMPT = (
    "这是图纸技术要求或 CC/SC 特性表的一块截图。只输出一个 JSON Object。"
    '格式：{"notes":[{"no":"条文号","text":"原文","special":"NA或SC或CC",'
    '"special_no":"特性号数字或空"}],'
    '"characteristics":[{"cc_no":"","sc_no":"","name":"特性名称",'
    '"params":"特性参数","view":"视图","zone":"区域","location":"位置"}]}。'
    "表里没有的字段写空字符串。不要编造看不清的字。"
)

BUBBLE_PROMPT = (
    "看图提取一个尺寸或形位公差气泡。只输出一个 JSON Object。"
    '格式：{"num":"气泡号","special":"NA或SC或CC","special_no":"特性号数字或空",'
    '"type":"类型","description":"描述"}。'
    "type 仅限：尺寸、直线度、平面度、圆度、圆柱度、线轮廓度、面轮廓度、"
    "平行度、垂直度、倾斜度、位置度、同轴度、对称度、圆跳动、全跳动。"
    "形位公差：类型名+数值（含 UZ）；第二格确有 φ/Ø/⌀ 才写φ（如位置度φ0.5），否则位置度0.8；"
    "不写基准格与 MMC/LMC/RFS；勿把圈M或小数点当φ。"
    "线性尺寸：type=尺寸，描述不写类型名；角度保留°。"
    "nX/n× 是处数，写在最前。同号上下差照抄（-0.2/-0.4），勿改成 ±。"
    "气泡旁的 SC 21 / CC 04 写入 special 与 special_no。没有则 special=NA。"
    "气泡号是红色圆圈或方框里的数字。"
)

VisionFn = Callable[[str, bytes], dict[str, Any]]


def _png_data_url(png: bytes) -> str:
    b64 = base64.b64encode(png).decode("ascii")
    return f"data:image/png;base64,{b64}"


def _strip_fence(text: str) -> str:
    t = (text or "").strip()
    if t.startswith("```"):
        t = re.sub(r"^```(?:json)?\s*", "", t)
        t = re.sub(r"\s*```$", "", t)
    return t.strip()


def parse_json_object(text: str) -> dict[str, Any]:
    blob = _strip_fence(text)
    data = json.loads(blob)
    if not isinstance(data, dict):
        raise ValueError("model did not return a JSON object")
    return data


def complete_vision(
    kind: str,
    png: bytes,
    *,
    api_key: str | None = None,
    thinking: bool | None = None,
) -> dict[str, Any]:
    prompt = {
        "title": TITLE_PROMPT,
        "notes": NOTES_PROMPT,
        "bubble": BUBBLE_PROMPT,
    }.get(kind)
    if prompt is None:
        raise ValueError(f"unknown slice kind {kind}")
    key = api_key if api_key is not None else read_deepseek_key()
    body = {
        "model": DEEPSEEK_MODEL,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": _png_data_url(png)}},
                ],
            }
        ],
        "response_format": {"type": "json_object"},
    }
    if thinking is False:
        body["thinking"] = {"type": "disabled"}
    elif thinking is True:
        body["thinking"] = {"type": "enabled"}
    req = urllib.request.Request(
        DEEPSEEK_URL,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {key}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        # Do not include request body (image + key live there).
        detail = exc.read()[:240].decode("utf-8", "replace")
        raise RuntimeError(f"DeepSeek HTTP {exc.code}: {detail}") from None
    try:
        text = payload["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError("DeepSeek 返回无法解析") from exc
    return parse_json_object(text)


def normalize_special(raw: str) -> str:
    text = str(raw or "NA").strip().upper()
    if text in SPECIALS:
        return text
    if text.startswith("SC"):
        return "SC"
    if text.startswith("CC"):
        return "CC"
    return "NA"


def normalize_special_no(raw: str, special: str) -> str:
    digits = re.sub(r"\D+", "", str(raw or ""))
    if special in ("SC", "CC"):
        return digits
    return digits


def normalize_type(raw: str) -> str:
    text = str(raw or "").strip()
    if text in ALLOWED_TYPES:
        return text
    if text in ("尺寸公差", "线性尺寸", "线性"):
        return LINEAR_TYPE
    return LINEAR_TYPE


def normalize_bubble(raw: dict[str, Any], page: int) -> dict[str, Any]:
    special = normalize_special(raw.get("special"))
    return {
        "num": str(raw.get("num") or "").strip(),
        "special": special,
        "special_no": normalize_special_no(raw.get("special_no"), special),
        "type": normalize_type(raw.get("type")),
        "description": str(raw.get("description") or raw.get("desc") or "").strip(),
        "page": page,
    }


def normalize_notes(raw: dict[str, Any], page: int) -> dict[str, list]:
    notes = []
    for item in raw.get("notes") or []:
        if not isinstance(item, dict):
            continue
        special = normalize_special(item.get("special"))
        text = str(item.get("text") or "").strip()
        if not text:
            continue
        notes.append(
            {
                "no": str(item.get("no") or "").strip(),
                "text": text,
                "special": special,
                "special_no": normalize_special_no(item.get("special_no"), special),
                "page": page,
            }
        )
    chars = []
    for item in raw.get("characteristics") or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        params = str(item.get("params") or "").strip()
        if not name and not params:
            continue
        chars.append(
            {
                "cc_no": str(item.get("cc_no") or "").strip(),
                "sc_no": str(item.get("sc_no") or "").strip(),
                "name": name,
                "params": params,
                "view": str(item.get("view") or "").strip(),
                "zone": str(item.get("zone") or "").strip(),
                "location": str(item.get("location") or "").strip(),
                "page": page,
            }
        )
    return {"notes": notes, "characteristics": chars}
