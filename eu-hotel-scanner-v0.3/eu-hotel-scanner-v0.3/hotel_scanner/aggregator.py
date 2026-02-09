import random
import time
from collections import defaultdict
from datetime import date
from statistics import median
from typing import Dict, Iterable, List, Optional, Tuple

from hotel_scanner.clients.base import HotelVendorClient
from hotel_scanner.models import CountryMetrics, Destination, Offer


class ScanConfig:
    def __init__(
        self,
        scan_mode: str = "cheap_only",
        max_cost_index_for_scan: float = 1.8,
        base_cities_per_country: int = 3,
        base_offers_per_destination: int = 50,
        delay_seconds: Tuple[float, float] = (5.0, 20.0),
        alpha: float = 1.0,
    ):
        self.scan_mode = scan_mode
        self.max_cost_index_for_scan = max_cost_index_for_scan
        self.base_cities_per_country = base_cities_per_country
        self.base_offers_per_destination = base_offers_per_destination
        self.delay_seconds = delay_seconds
        self.alpha = alpha


def scan_destinations(
    destinations: Iterable[Destination],
    vendors: Iterable[HotelVendorClient],
    checkin: date,
    checkout: date,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    cost_index_by_country: Optional[Dict[str, float]] = None,
    scan_config: Optional[ScanConfig] = None,
) -> Dict[str, CountryMetrics]:
    """v0.2 core engine (reused in v0.3).

    - Group destinations by country
    - Use cost_index to:
        * optionally skip expensive countries (scan_mode = 'cheap_only')
        * control number of cities per country
        * control max offers per destination
    - Add random delay between vendor searches
    - Compute raw + cost-adjusted metrics per country
    """

    if cost_index_by_country is None:
        cost_index_by_country = {}

    if scan_config is None:
        scan_config = ScanConfig()

    alpha = scan_config.alpha
    delay_min, delay_max = scan_config.delay_seconds

    # Group destinations by country
    by_country: Dict[str, List[Destination]] = defaultdict(list)
    country_name_lookup: Dict[str, str] = {}
    for dest in destinations:
        by_country[dest.country_code].append(dest)
        country_name_lookup[dest.country_code] = dest.country_name

    offers_by_country: Dict[str, List[Offer]] = defaultdict(list)

    for country_code, dests in by_country.items():
        cost_index = cost_index_by_country.get(country_code, 1.0)

        # Optional skip if too expensive
        if (
            scan_config.scan_mode == "cheap_only"
            and cost_index > scan_config.max_cost_index_for_scan
        ):
            continue

        # Decide how many cities to scan in this country
        target_cities = max(
            1,
            min(
                len(dests),
                round(scan_config.base_cities_per_country / cost_index),
            ),
        )

        dests_to_scan = sorted(dests, key=lambda d: d.city_name)[:target_cities]

        # Offers per destination, scaled by cost_index
        max_offers_per_dest = max(
            10,
            round(scan_config.base_offers_per_destination / cost_index),
        )

        for dest in dests_to_scan:
            for vendor in vendors:
                delay = random.uniform(delay_min, delay_max)
                time.sleep(delay)

                vendor_offers = vendor.search_offers(
                    destination=dest,
                    checkin=checkin,
                    checkout=checkout,
                    min_price=min_price,
                    max_price=max_price,
                    limit=max_offers_per_dest,
                )

                offers_by_country[country_code].extend(vendor_offers)

    metrics_by_country: Dict[str, CountryMetrics] = {}

    for country_code, offers in offers_by_country.items():
        if not offers:
            continue

        cost_index = cost_index_by_country.get(country_code, 1.0)

        # compute effective_score for each offer
        for o in offers:
            o.effective_score = o.price_per_night * (cost_index ** alpha)

        offers_sorted = sorted(offers, key=lambda o: o.price_per_night)
        prices = [o.price_per_night for o in offers_sorted]
        n = len(prices)
        p90_idx = max(0, int(n * 0.9) - 1)

        min_price_per_night = prices[0]
        median_price_per_night = median(prices)
        p90_price_per_night = prices[p90_idx]

        effective_min_price = min_price_per_night * (cost_index ** alpha)
        effective_median_price = median_price_per_night * (cost_index ** alpha)

        metrics_by_country[country_code] = CountryMetrics(
            country_code=country_code,
            country_name=country_name_lookup.get(country_code, country_code),
            offers=offers_sorted,
            min_price_per_night=min_price_per_night,
            median_price_per_night=median_price_per_night,
            p90_price_per_night=p90_price_per_night,
            cost_index=cost_index,
            effective_min_price=effective_min_price,
            effective_median_price=effective_median_price,
        )

    return metrics_by_country
