from pathlib import Path

from hotel_scanner.cli import run_scan


def test_run_scan_smoke(tmp_path: Path):
    root = Path(__file__).resolve().parents[1]

    checkin = "2025-07-10"
    checkout = "2025-07-12"

    run_id, ctx = run_scan(
        checkin_str=checkin,
        checkout_str=checkout,
        min_price=None,
        max_price=None,
        alpha_override=None,
        min_rating_override=None,
        min_stars_override=None,
        base_currency="EUR",
        destinations_file=root / "config" / "destinations.yaml",
        cost_index_file=root / "config" / "country_cost_index.yaml",
        scanner_config_file=root / "config" / "scanner.yaml",
        fx_rates_file=root / "config" / "fx_rates.yaml",
        vendors_file=root / "config" / "vendors.yaml",
        db_path=tmp_path / "hotel_scanner_test.db",
        use_optimizer=False,
        optimizer_top_k=None,
        optimizer_min_weight=0.5,
        optimizer_max_weight=2.0,
    )

    assert run_id != -1
    metrics_by_country = ctx["metrics_by_country"]
    assert isinstance(metrics_by_country, dict)
    # With mock vendor we expect at least one country to have offers
    assert len(metrics_by_country) > 0
