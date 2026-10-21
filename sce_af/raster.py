"""Raster a PDF page to a PNG without sending the whole file to a model."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

import pymupdf
from PIL import Image

DEFAULT_DPI = 140


def page_count(pdf_path: Path) -> int:
    with pymupdf.open(pdf_path) as doc:
        return doc.page_count


def render_page(pdf_path: Path, page_index: int, dpi: int = DEFAULT_DPI) -> Image.Image:
    """1-based page_index. Returns RGB PIL image."""
    if page_index < 1:
        raise ValueError("page_index is 1-based")
    zoom = dpi / 72.0
    matrix = pymupdf.Matrix(zoom, zoom)
    with pymupdf.open(pdf_path) as doc:
        if page_index > doc.page_count:
            raise IndexError(f"page {page_index} out of {doc.page_count}")
        page = doc.load_page(page_index - 1)
        pix = page.get_pixmap(matrix=matrix, alpha=False)
        img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    return img


def image_png_bytes(img: Image.Image) -> bytes:
    buf = BytesIO()
    rgb = img.convert("RGB")
    rgb.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def fill_ratio(img: Image.Image, threshold: int = 245) -> float:
    """Share of pixels that are not near-white. Used to skip blank sheets."""
    gray = img.convert("L")
    hist = gray.histogram()
    dark = sum(hist[: threshold + 1])
    total = img.width * img.height
    if total <= 0:
        return 0.0
    return dark / total
