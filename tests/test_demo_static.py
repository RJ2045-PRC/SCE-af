from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_pages_demo_is_static():
    html = (ROOT / "docs" / "index.html").read_text(encoding="utf-8")
    js = (ROOT / "docs" / "demo.js").read_text(encoding="utf-8")
    assert 'href="style.css"' in html
    assert 'src="demo.js"' in html
    assert "/style.css" not in html.replace('href="style.css"', "")
    assert "/api/" not in html
    assert "/api/" not in js
    assert "fetch(" not in js
    assert "HRJ-DWG-2026-0187" in js
    assert "DEMO CUSTOMER" in js
    assert "M-2026-0187" in js
    crops = list((ROOT / "docs" / "crops").glob("*.png"))
    assert crops


def test_pages_demo_avoids_customer_drawings():
    js = (ROOT / "docs" / "demo.js").read_text(encoding="utf-8")
    for needle in ("Huf", "Xiaomi", "LG-26554", "LG-PT26500", "P000005766001"):
        assert needle not in js
