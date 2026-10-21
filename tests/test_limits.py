from sce_af.limits import bounds_from_limits, enrich_bubble, parse_limits


def test_plus_minus_linear():
    got = parse_limits("5.000 ± 0.1", "尺寸")
    assert got["nominal"] == 5.0
    assert got["upper"] == 0.1
    assert got["lower"] == -0.1
    bounds = bounds_from_limits(**got)
    assert bounds["min_val"] == 4.9
    assert bounds["std_val"] == 5.0
    assert bounds["max_val"] == 5.1


def test_gdt_position():
    got = parse_limits("位置度φ0.5", "位置度")
    assert got["nominal"] == 0.0
    assert got["upper"] == 0.5
    assert got["lower"] == 0.0


def test_enrich_ignores_model_numbers():
    row = enrich_bubble(
        {
            "num": "37",
            "special": "SC",
            "type": "尺寸",
            "description": "9.02 ±0.2",
            "nominal": 99,
            "upper": 99,
            "lower": 99,
        }
    )
    assert row["nominal"] == 9.02
    assert row["upper"] == 0.2
    assert row["lower"] == -0.2
