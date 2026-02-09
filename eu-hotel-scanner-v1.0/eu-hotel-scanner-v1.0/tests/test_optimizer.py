from hotel_scanner.optimizer import build_country_scan_weights


def test_cheaper_country_gets_higher_weight():
    cost_index_by_country = {
        "BG": 1.0,
        "DK": 2.0,
    }

    historical_summary = [
        {
            "country_code": "BG",
            "country_name": "Bulgaria",
            "cost_index": 1.0,
            "avg_median_price": 50.0,
            "avg_effective_median": 50.0,
            "normalized_median": 50.0,
        },
        {
            "country_code": "DK",
            "country_name": "Denmark",
            "cost_index": 2.0,
            "avg_median_price": 200.0,
            "avg_effective_median": 400.0,
            "normalized_median": 100.0,
        },
    ]

    weights = build_country_scan_weights(cost_index_by_country, historical_summary)
    assert weights["BG"] > weights["DK"]


def test_top_k_limits_non_zero_countries():
    cost_index_by_country = {
        "BG": 1.0,
        "RO": 1.1,
        "PT": 1.3,
        "DK": 2.2,
    }

    historical_summary = []
    weights = build_country_scan_weights(
        cost_index_by_country,
        historical_summary,
        top_k=2,
    )
    non_zero = [c for c, w in weights.items() if w > 0]
    assert len(non_zero) == 2
