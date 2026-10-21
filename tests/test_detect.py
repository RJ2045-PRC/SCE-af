from PIL import Image, ImageDraw

from sce_af.detect import crop_box, find_red_boxes
from sce_af.slice import plan_page


def _page_with_red_box() -> Image.Image:
    img = Image.new("RGB", (400, 280), (255, 255, 255))
    draw = ImageDraw.Draw(img)
    draw.rectangle((40, 50, 160, 140), outline=(210, 20, 20), width=8)
    draw.rectangle((48, 58, 152, 132), outline=(220, 40, 40), width=4)
    return img


def test_finds_red_bubble_frame():
    boxes = find_red_boxes(_page_with_red_box(), scale=1, min_area=400)
    assert boxes, "should find the red rectangle"
    box = boxes[0]
    crop = crop_box(_page_with_red_box(), box, pad=4)
    assert crop.width >= 40
    assert crop.height >= 40


def test_plan_page_emits_bubble_not_full_page():
    img = _page_with_red_box()
    tasks = plan_page(img, page=7, is_first=False)
    kinds = [t.kind for t in tasks]
    assert kinds == ["bubble"]
    assert all(t.png.startswith(b"\x89PNG") for t in tasks)
