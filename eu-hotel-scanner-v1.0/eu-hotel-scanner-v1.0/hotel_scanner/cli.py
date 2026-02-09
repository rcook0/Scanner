import argparse
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, Tuple

import yaml
from dotenv import load_dotenv

from hotel_scanner.aggregator import ScanConfig, scan_destinations
from hotel_scanner.models import Destination
from hotel_scanner.pricing import load_fx_rates
from hotel_scanner.storage import (
    get_connection,
    get_historical_country_summary,
    log_country_metrics,
    log_run,
)
from hotel_scanner.vendors import build_vendors
from hotel_scanner.optimizer import build_country_scan_weights, summarize_country_weights


def load_destinations(path: Path):
    with path.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    destinations = []
    for entry in raw:
        country_code = entry["country_code"]
        country_name = entry["country_name"]
        for city in entry["cities"]:
            if isinstance(city, str):
                city_name = city
                vendor_ref = {}
            else:
                city_name = city["name"]
                vendor_ref = city.get("vendor_ref", {}) or {}

            destinations.append(
                Destination(
                    country_code=country_code,
                    country_name=country_name,
                    city_name=city_name,
                    vendor_ref=vendor_ref,
                )
            )
    return destinations


def load_country_cost_index(path: Path) -> Dict[str, float]:
    with path.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    mapping: Dict[str, float] = {}
    for entry in raw:
        mapping[entry["country_code"]] = float(entry["cost_index"])
    return mapping


def load_scanner_config(path: Path) -> ScanConfig:
    with path.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    delay_cfg = raw.get("delay_seconds", {}) or {}
    delay_min = float(delay_cfg.get("min", 5.0))
    delay_max = float(delay_cfg.get("max", 20.0))

    min_rating = raw.get("min_rating", None)
    min_stars = raw.get("min_stars", None)

    return ScanConfig(
        scan_mode=raw.get("scan_mode", "cheap_only"),
        max_cost_index_for_scan=float(raw.get("max_cost_index_for_scan", 1.8)),
        base_cities_per_country=int(raw.get("base_cities_per_country", 3)),
        base_offers_per_destination=int(raw.get("base_offers_per_destination", 50)),
        delay_seconds=(delay_min, delay_max),
        alpha=float(raw.get("alpha", 1.0)),
        min_rating=float(min_rating) if min_rating is not None else None,
        min_stars=int(min_stars) if min_stars is not None else None,
    )


def run_scan(
    checkin_str: str,
    checkout_str: str,
    min_price: Optional[float],
    max_price: Optional[float],
    alpha_override: Optional[float],
    min_rating_override: Optional[float],
    min_stars_override: Optional[int],
    base_currency: str,
    destinations_file: Path,
    cost_index_file: Path,
    scanner_config_file: Path,
    fx_rates_file: Path,
    vendors_file: Path,
    db_path: Optional[Path],
    use_optimizer: bool,
    optimizer_top_k: Optional[int],
    optimizer_min_weight: float,
    optimizer_max_weight: float,
) -> Tuple[int, Dict[str, object]]:
    """Core scan runner used by both CLI and service layer.

    Returns:
        (run_id, context_dict)
    """
    load_dotenv()

    checkin = datetime.strptime(checkin_str, "%Y-%m-%d").date()
    checkout = datetime.strptime(checkout_str, "%Y-%m-%d").date()

    destinations = load_destinations(destinations_file)
    cost_index_by_country = load_country_cost_index(cost_index_file)
    scan_cfg = load_scanner_config(scanner_config_file)

    # Overrides
    if alpha_override is not None:
        scan_cfg.alpha = alpha_override
    if min_rating_override is not None:
        scan_cfg.min_rating = min_rating_override
    if min_stars_override is not None:
        scan_cfg.min_stars = min_stars_override

    fx_rates = load_fx_rates(fx_rates_file)
    vendors = build_vendors(vendors_file)

    conn = get_connection(db_path)
    historical_summary = get_historical_country_summary(conn)

    country_scan_weights = None
    if use_optimizer:
        country_scan_weights = build_country_scan_weights(
            cost_index_by_country=cost_index_by_country,
            historical_summary=historical_summary,
            top_k=optimizer_top_k,
            min_weight=optimizer_min_weight,
            max_weight=optimizer_max_weight,
        )

    metrics_by_country = scan_destinations(
        destinations=destinations,
        vendors=vendors,
        checkin=checkin,
        checkout=checkout,
        min_price=min_price,
        max_price=max_price,
        cost_index_by_country=cost_index_by_country,
        scan_config=scan_cfg,
        fx_rates=fx_rates,
        base_currency=base_currency,
        country_scan_weights=country_scan_weights,
    )

    if not metrics_by_country:
        return -1, {
            "checkin": checkin,
            "checkout": checkout,
            "vendors": vendors,
            "metrics_by_country": metrics_by_country,
            "historical_summary": historical_summary,
            "country_scan_weights": country_scan_weights,
            "scan_cfg": scan_cfg,
            "base_currency": base_currency,
        }

    run_id = log_run(
        conn,
        checkin=checkin,
        checkout=checkout,
        scan_mode=scan_cfg.scan_mode,
        alpha=scan_cfg.alpha,
        min_price=min_price,
        max_price=max_price,
    )
    log_country_metrics(conn, run_id, metrics_by_country)

    context = {
        "checkin": checkin,
        "checkout": checkout,
        "vendors": vendors,
        "metrics_by_country": metrics_by_country,
        "historical_summary": historical_summary,
        "country_scan_weights": country_scan_weights,
        "scan_cfg": scan_cfg,
        "base_currency": base_currency,
    }
    return run_id, context


def main():
    parser = argparse.ArgumentParser(
        description="EU Hotel Scanner v0.9 – packaged CLI with optimiser and multi-vendor support"
    )
    parser.add_argument("--checkin", required=True, help="YYYY-MM-DD")
    parser.add_argument("--checkout", required=True, help="YYYY-MM-DD")
    parser.add_argument("--min-price", type=float, default=None)
    parser.add_argument("--max-price", type=float, default=None)
    parser.add_argument(
        "--alpha",
        type=float,
        default=None,
        help="override alpha (cost index exponent)",
    )
    parser.add_argument("--min-rating", type=float, default=None,
                        help="minimum hotel rating to include (overrides config)")
    parser.add_argument("--min-stars", type=int, default=None,
                        help="minimum star rating to include (overrides config)")
    parser.add_argument("--base-currency", default="EUR",
                        help="base currency for metrics (default: EUR)")
    parser.add_argument("--destinations-file", default="config/destinations.yaml")
    parser.add_argument("--cost-index-file", default="config/country_cost_index.yaml")
    parser.add_argument("--scanner-config-file", default="config/scanner.yaml")
    parser.add_argument("--fx-rates-file", default="config/fx_rates.yaml")
    parser.add_argument("--vendors-file", default="config/vendors.yaml")
    parser.add_argument(
        "--db-path",
        default=None,
        help="Optional path to SQLite DB (default: ./data/hotel_scanner.db)",
    )

    # Optimiser-specific arguments
    parser.add_argument(
        "--use-optimizer",
        action="store_true",
        help="Use a historical search optimiser to focus scan on best-value countries.",
    )
    parser.add_argument(
        "--optimizer-top-k",
        type=int,
        default=None,
        help="If set, scan only the top K countries according to the optimiser (others get weight 0).",
    )
    parser.add_argument(
        "--optimizer-min-weight",
        type=float,
        default=0.5,
        help="Minimum per-country weight after scaling.",
    )
    parser.add_argument(
        "--optimizer-max-weight",
        type=float,
        default=2.0,
        help="Maximum per-country weight after scaling.",
    )

    args = parser.parse_args()

    db_path = Path(args.db_path) if args.db_path else None

    run_id, ctx = run_scan(
        checkin_str=args.checkin,
        checkout_str=args.checkout,
        min_price=args.min_price,
        max_price=args.max_price,
        alpha_override=args.alpha,
        min_rating_override=args.min_rating,
        min_stars_override=args.min_stars,
        base_currency=args.base_currency,
        destinations_file=Path(args.destinations_file),
        cost_index_file=Path(args.cost_index_file),
        scanner_config_file=Path(args.scanner_config_file),
        fx_rates_file=Path(args.fx_rates_file),
        vendors_file=Path(args.vendors_file),
        db_path=db_path,
        use_optimizer=args.use_optimizer,
        optimizer_top_k=args.optimizer_top_k,
        optimizer_min_weight=args.optimizer_min_weight,
        optimizer_max_weight=args.optimizer_max_weight,
    )

    checkin = ctx["checkin"]
    checkout = ctx["checkout"]
    vendors = ctx["vendors"]
    metrics_by_country = ctx["metrics_by_country"]
    historical_summary = ctx["historical_summary"]
    country_scan_weights = ctx["country_scan_weights"]
    scan_cfg = ctx["scan_cfg"]
    base_currency = ctx["base_currency"]

    if run_id == -1:
        print("No metrics computed (no offers). Nothing to log.")
        return

    print(f"\nScan results for {checkin} → {checkout} (run id {run_id})")
    print("=" * 90)
    print(f"Base currency: {base_currency}")
    print(f"Alpha (cost bias): {scan_cfg.alpha}")
    if scan_cfg.min_rating is not None:
        print(f"Min rating filter: {scan_cfg.min_rating}")
    if scan_cfg.min_stars is not None:
        print(f"Min stars filter: {scan_cfg.min_stars}")
    print(f"Vendors: {[v.name for v in vendors]}")

    if args.use_optimizer and country_scan_weights:
        print("\nOptimiser scan plan (country -> weight):")
        plan_rows = summarize_country_weights(
            load_country_cost_index(Path(args.cost_index_file)),
            historical_summary,
            country_scan_weights,
            country_name_by_code=None,
        )
        for row in plan_rows:
            print(
                f"  {row['Country code']:3} "
                f"w={row['Scan weight']:4.2f} "
                f"idx={row['Cost index']:4.2f} "
                f"normMed={row['Normalized median (hist)'] if row['Normalized median (hist)'] is not None else 'NA'}"
            )

    sorted_by_min = sorted(
        metrics_by_country.values(),
        key=lambda m: m.min_price_per_night,
    )

    sorted_by_effective = sorted(
        metrics_by_country.values(),
        key=lambda m: m.effective_min_price,
    )

    print("\nSorted by RAW min price in base currency:")
    for m in sorted_by_min:
        print(
            f"{m.country_code:3} {m.country_name:15} "
            f"min={m.min_price_per_night:6.1f}  "
            f"median={m.median_price_per_night:6.1f}  "
            f"p90={m.p90_price_per_night:6.1f}  "
            f"cost_idx={m.cost_index:.2f}  "
            f"offers={m.offer_count:3d}"
        )

    print("\nSorted by EFFECTIVE min (price * cost_index^alpha):")
    for m in sorted_by_effective:
        print(
            f"{m.country_code:3} {m.country_name:15} "
            f"eff_min={m.effective_min_price:6.1f}  "
            f"raw_min={m.min_price_per_night:6.1f}  "
            f"cost_idx={m.cost_index:.2f}"
        )

    print("\nResults logged to SQLite.\n")
