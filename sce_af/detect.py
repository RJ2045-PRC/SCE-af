"""Find red bubble frames on a rasterized drawing page."""

from __future__ import annotations

from dataclasses import dataclass

from PIL import Image, ImageFilter


@dataclass(frozen=True)
class RedBox:
    x: int
    y: int
    w: int
    h: int

    @property
    def area(self) -> int:
        return self.w * self.h

    def padded(self, pad: int, width: int, height: int) -> "RedBox":
        x0 = max(0, self.x - pad)
        y0 = max(0, self.y - pad)
        x1 = min(width, self.x + self.w + pad)
        y1 = min(height, self.y + self.h + pad)
        return RedBox(x0, y0, max(1, x1 - x0), max(1, y1 - y0))


def _is_red(h: int, s: int, v: int) -> bool:
    """PIL HSV: H 0–255. Annotation ink is a strong red, hue near 0."""
    if s < 50 or v < 60:
        return False
    return h <= 20 or h >= 235


def red_mask(img: Image.Image, scale: int = 2) -> tuple[Image.Image, int]:
    """Downsampled binary mask (0/255) of red ink."""
    if scale < 1:
        scale = 1
    small = img.convert("RGB").resize(
        (max(1, img.width // scale), max(1, img.height // scale)),
        Image.Resampling.BILINEAR,
    )
    hsv = small.convert("HSV")
    pixels = hsv.get_flattened_data() if hasattr(hsv, "get_flattened_data") else hsv.getdata()
    out = []
    for h, s, v in pixels:
        out.append(255 if _is_red(h, s, v) else 0)
    mask = Image.new("L", small.size)
    mask.putdata(out)
    mask = mask.filter(ImageFilter.MaxFilter(3))
    return mask, scale


def _components(mask: Image.Image, min_px: int) -> list[tuple[int, int, int, int]]:
    """4-connected components on a binary mask. Returns boxes in mask coords."""
    width, height = mask.size
    pix = mask.load()
    seen = [[False] * width for _ in range(height)]
    boxes: list[tuple[int, int, int, int]] = []
    for y in range(height):
        for x in range(width):
            if seen[y][x] or pix[x, y] < 128:
                continue
            stack = [(x, y)]
            seen[y][x] = True
            min_x = max_x = x
            min_y = max_y = y
            count = 0
            while stack:
                cx, cy = stack.pop()
                count += 1
                if cx < min_x:
                    min_x = cx
                if cx > max_x:
                    max_x = cx
                if cy < min_y:
                    min_y = cy
                if cy > max_y:
                    max_y = cy
                for nx, ny in ((cx - 1, cy), (cx + 1, cy), (cx, cy - 1), (cx, cy + 1)):
                    if nx < 0 or ny < 0 or nx >= width or ny >= height:
                        continue
                    if seen[ny][nx] or pix[nx, ny] < 128:
                        continue
                    seen[ny][nx] = True
                    stack.append((nx, ny))
            if count < min_px:
                continue
            boxes.append((min_x, min_y, max_x - min_x + 1, max_y - min_y + 1))
    return boxes


def _contains(outer: RedBox, inner: RedBox, margin: int = 10) -> bool:
    return (
        outer.x <= inner.x + margin
        and outer.y <= inner.y + margin
        and outer.x + outer.w >= inner.x + inner.w - margin
        and outer.y + outer.h >= inner.y + inner.h - margin
    )


def find_red_boxes(
    img: Image.Image,
    *,
    scale: int = 2,
    min_area: int = 3500,
    max_frac: float = 0.12,
) -> list[RedBox]:
    """Return red frames in full-image coordinates, reading order."""
    mask, used_scale = red_mask(img, scale=scale)
    min_px = max(4, min_area // (used_scale * used_scale))
    raw = _components(mask, min_px)
    page_area = img.width * img.height
    out: list[RedBox] = []
    for x, y, w, h in raw:
        box = RedBox(x * used_scale, y * used_scale, w * used_scale, h * used_scale)
        if box.area < min_area:
            continue
        if box.area > page_area * max_frac:
            continue
        if box.w < 22 or box.h < 22:
            continue
        ratio = box.w / box.h if box.h else 0
        if ratio > 8 or ratio < 0.12:
            continue
        out.append(box)
    kept: list[RedBox] = []
    for box in out:
        kids = [other for other in out if other is not box and other.area >= 2000 and _contains(box, other)]
        if len(kids) >= 2:
            continue
        kept.append(box)
    kept.sort(key=lambda b: (b.y, b.x))
    return kept


def crop_box(img: Image.Image, box: RedBox, pad: int = 24) -> Image.Image:
    padded = box.padded(pad, img.width, img.height)
    return img.crop(
        (padded.x, padded.y, padded.x + padded.w, padded.y + padded.h)
    )
