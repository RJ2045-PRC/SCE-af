"""GD&T type names. Copied from SCE; keep the same Chinese labels."""

from __future__ import annotations

GDT_TYPES: list[str] = [
    "直线度",
    "平面度",
    "圆度",
    "圆柱度",
    "线轮廓度",
    "面轮廓度",
    "平行度",
    "垂直度",
    "倾斜度",
    "位置度",
    "同轴度",
    "对称度",
    "圆跳动",
    "全跳动",
]

LINEAR_TYPE = "尺寸"
ALLOWED_TYPES = [LINEAR_TYPE, *GDT_TYPES]
SPECIALS = ("NA", "SC", "CC")
