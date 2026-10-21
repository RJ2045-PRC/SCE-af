from sce_af.merge import apply_header_edits, merge_job
from sce_af.pipeline import run_pipeline


def test_merge_links_specials_and_parses_limits():
    doc = merge_job(
        "LG-26554-demo.pdf",
        {"customer": "Xiaomi EV", "part_name": "CCS-CMU", "drawing_no": "P000005766001"},
        [
            (11, {"num": "37", "special": "SC", "special_no": "27", "type": "位置度", "description": "位置度φ0.4"}),
            (11, {"num": "37", "special": "SC", "special_no": "27", "type": "位置度", "description": "位置度φ0.4"}),
        ],
        [
            (
                5,
                {
                    "notes": [],
                    "characteristics": [
                        {"sc_no": "27", "name": "位置度", "params": "φ0.4", "view": "11", "zone": "/", "location": "A"}
                    ],
                },
            )
        ],
    )
    assert doc["header"]["mold_no"] == "LG-26554"
    assert doc["header"]["part_no"] == "P000005766001"
    assert doc["bubbles"][0]["upper"] == 0.4
    codes = {item["code"] for item in doc["issues"]}
    assert "duplicate_num" in codes


def test_apply_header_edits():
    doc = {"header": {"mold_no": "", "part_no": ""}, "bubbles": []}
    out = apply_header_edits(doc, {"mold_no": "LG-PT26500", "part_no": "P1"})
    assert out["header"]["mold_no"] == "LG-PT26500"
    assert out["header"]["part_no"] == "P1"


def test_pipeline_uses_injected_vision(tmp_path):
    import pymupdf

    pdf = tmp_path / "LG-26554.pdf"
    doc = pymupdf.open()
    page = doc.new_page(width=300, height=200)
    shape = page.new_shape()
    shape.draw_rect(pymupdf.Rect(20, 20, 90, 80))
    shape.finish(color=(0.85, 0.1, 0.1), width=3)
    shape.commit()
    doc.save(pdf)
    doc.close()

    def vision(kind, png):
        assert png.startswith(b"\x89PNG")
        if kind == "title":
            return {"customer": "Xiaomi", "part_name": "CCS", "part_no": "P9"}
        if kind == "bubble":
            return {"num": "1", "special": "NA", "type": "尺寸", "description": "2.2 ±0.1"}
        return {"notes": [], "characteristics": []}

    result = run_pipeline(pdf, "LG-26554.pdf", vision=vision, workers=1)
    assert result["header"]["mold_no"] == "LG-26554"
    assert result["header"]["customer"] == "Xiaomi"
    if result["bubbles"]:
        assert result["bubbles"][0]["nominal"] == 2.2
