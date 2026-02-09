import argparse
from datetime import datetime
from pathlib import Path
from typing import Dict

import yaml

from hotel_scanner.aggregator import ScanConfig, scan_destinations
from hotel_scanner.clients.mock_vendor import MockVendorClient
from hotel_scanner.models import Destination


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

    return ScanConfig(
        scan_mode=raw.get("scan_mode", "cheap_only"),
        max_cost_index_for_scan=float(raw.get("max_cost_index_for_scan", 1.8)),
        base_cities_per_country=int(raw.get("base_cities_per_country", 3)),
        base_offers_per_destination=int(raw.get("base_offers_per_destination", 50)),
        delay_seconds=(delay_min, delay_max),
        alpha=float(raw.get("alpha", 1.0)),
    )


def main():
    parser = argparse.ArgumentParser(
        description="EU Hotel Scanner v0.2 – cost-guided scanning (mock vendor)"
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
    parser.add_argument("--destinations-file", default="config/destinations.yaml")
    parser.add_argument("--cost-index-file", default="config/country_cost_index.yaml")
    parser.add_argument("--scanner-config-file", default="config/scanner.yaml")
    args = parser.parse_args()

    checkin = datetime.strptime(args.checkin, "%Y-%m-%d").date()
    checkout = datetime.strptime(args.checkout, "%Y-%m-%d").date()

    destinations = load_destinations(Path(args.destinations_file))
    cost_index_by_country = load_country_cost_index(Path(args.cost_index_file))
    scan_cfg = load_scanner_config(Path(args.scanner_config_file))

    if args.alpha is not None:
        scan_cfg.alpha = args.alpha

    vendors = [
        MockVendorClient(),
        # Later: BookingApiClient(...), ExpediaApiClient(...), etc.
    ]

    metrics_by_country = scan_destinations(
        destinations=destinations,
        vendors=vendors,
        checkin=checkin,
        checkout=checkout,
        min_price=args.min_price,
        max_price=args.max_price,
        cost_index_by_country=cost_index_by_country,
        scan_config=scan_cfg,
    )

    sorted_by_min = sorted(
        metrics_by_country.values(),
        key=lambda m: m.min_price_per_night,
    )

    sorted_by_effective = sorted(
        metrics_by_country.values(),
        key=lambda m: m.effective_min_price,
    )

    print(f"\nScan results for {checkin} → {checkout}")
    print("=" * 80)
    print("Sorted by RAW min EUR/night:")
    for m in sorted_by_min:
        print(
            f"{m.country_code:3} {m.country_name:15} "
            f"min={m.min_price_per_night:6.1f}  "
            f"median={m.median_price_per_night:6.1f}  "
            f"p90={m.p90_price_per_night:6.1f}  "
            f"cost_idx={m.cost_index:.2f}"
        )

    print("\nSorted by EFFECTIVE min (price * cost_index^alpha):")
    print(f"(alpha={scan_cfg.alpha})")
    for m in sorted_by_effective:
        print(
            f"{m.country_code:3} {m.country_name:15} "
            f"eff_min={m.effective_min_price:6.1f}  "
            f"raw_min={m.min_price_per_night:6.1f}  "
            f"cost_idx={m.cost_index:.2f}"
        )

    print("\nDone.\n")


if __name__ == "__main__":
    main()
