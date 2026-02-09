from hotel_scanner.pricing import convert_amount


def test_convert_amount_symmetry():
    fx_rates = {
        "EUR": 1.0,
        "USD": 0.5,  # 1 USD = 0.5 EUR
    }

    # 10 USD -> 5 EUR
    eur = convert_amount(10.0, "USD", "EUR", fx_rates)
    assert abs(eur - 5.0) < 1e-6

    # 5 EUR -> 10 USD
    usd = convert_amount(5.0, "EUR", "USD", fx_rates)
    assert abs(usd - 10.0) < 1e-6
