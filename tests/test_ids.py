from sce_af.ids import ids_from_filename, merge_header, mold_from_text, part_from_text


def test_mold_and_part_from_filename():
    got = ids_from_filename("LG-26554-模组CCS板CMU2-气泡图-20261008.pdf")
    assert got["mold_no"] == "LG-26554"
    assert got["part_no"] == ""


def test_mold_with_letters():
    assert mold_from_text("Huf Groups LG-PT26500 2449201") == "LG-PT26500"


def test_part_number():
    assert part_from_text("图号 P000005766001 版本 A") == "P000005766001"


def test_filename_wins_over_vision():
    header = merge_header(
        "LG-26554-x.pdf",
        {"mold_no": "LG-PT26500", "part_no": "P000005766001", "customer": "Xiaomi"},
    )
    assert header["mold_no"] == "LG-26554"
    assert header["part_no"] == "P000005766001"
    assert header["customer"] == "Xiaomi"
