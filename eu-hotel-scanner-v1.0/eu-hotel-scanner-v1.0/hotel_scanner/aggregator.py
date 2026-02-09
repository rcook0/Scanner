import random
import time
from collections import defaultdict
from datetime import date
from statistics import median
from typing import Dict, Iterable, List, Optional, Tuple

from hotel_scanner.clients.base import HotelVendorClient
from hotel_scanner.models import CountryMetrics, Destination, Offer
from hotel_scanner.pricing import convert_amount


class ScanConfig:
    def __init__(
        self,
        scan_mode: str = "cheap_only",
        max_cost_index_for_scan: float = 1.8,
        base_cities_per_country: int = 3,
        base_offers_per_destination: int = 50,
        delay_seconds: Tuple[float, float] = (5.0, 20.0),
        alpha: float = 1.0,
        min_rating: Optional[float] = None,
        min_stars: Optional[int] = None,
    ):
        self.scan_mode = scan_mode
        self.max_cost_index_for_scan = max_cost_index_for_scan
        self.base_cities_per_country = base_cities_per_country
        self.base_offers_per_destination = base_offers_per_destination
        self.delay_seconds = delay_seconds
        self.alpha = alpha
        self.min_rating = min_rating
        self.min_stars = min_stars


def _dedupe_offers(offers: List[Offer]) -> List[Offer]:
    """Soft dedupe across vendors by (city, hotel_name).

    For each (city_name, hotel_name) pair we keep only the cheapest offer
    (based on price_per_night in vendor currency).

    This is not perfect (different hotels can share a name), but it's usually
    good enough for aggregate country-level stats.
    """
    best_by_key: Dict[tuple, Offer] = {}
    for o in offers:
        key = (o.city_name.strip().lower(), o.hotel_name.strip().lower())
        existing = best_by_key.get(key)
        if existing is None or o.price_per_night < existing.price_per_night:
            best_by_key[key] = o
    return list(best_by_key.values())


def scan_destinations(
    destinations: Iterable[Destination],
    vendors: Iterable[HotelVendorClient],
    checkin: date,
    checkout: date,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    cost_index_by_country: Optional[Dict[str, float]] = None,
    scan_config: Optional[ScanConfig] = None,
    fx_rates: Optional[Dict[str, float]] = None,
    base_currency: str = "EUR",
    country_scan_weights: Optional[Dict[str, float]] = None,
) -> Dict[str, CountryMetrics]:
    """Cost-guided scan engine with multi-vendor aggregation, basic data quality
    controls, and optional per-country scan weights.

    - Group destinations by country.
    - Use cost_index to:
        * optionally skip expensive countries (scan_mode = 'cheap_only')
        * control number of cities per country
        * control max offers per destination
    - Use country_scan_weights (if provided) to bias scan depth and optionally
      skip some countries entirely (weight <= 0).
    - For each destination, query all configured vendors.
    - Soft-dedupe offers across vendors by (city, hotel_name), keeping the
      cheapest price_per_night.
    - Apply per-offer filters (min_rating, min_stars).
    - Normalize prices into a base currency using fx_rates.
    - Compute raw + cost-adjusted metrics per country, plus richer stats.
    """

    if cost_index_by_country is None:
        cost_index_by_country = {}

    if scan_config is None:
        scan_config = ScanConfig()

    if fx_rates is None:
        fx_rates = {}

    if country_scan_weights is None:
        country_scan_weights = {}

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
        weight = float(country_scan_weights.get(country_code, 1.0))

        # If optimizer marked this country as "do not scan", skip entirely.
        if weight <= 0:
            continue

        # Optional skip if too expensive under the basic prior
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
                round(scan_config.base_cities_per_country * weight / cost_index),
            ),
        )

        dests_to_scan = sorted(dests, key=lambda d: d.city_name)[:target_cities]

        # Offers per destination, scaled by cost_index and optimizer weight
        max_offers_per_dest = max(
            10,
            round(scan_config.base_offers_per_destination * weight / cost_index),
        )

        for dest in dests_to_scan:
            # Gather offers from all vendors for this destination
            dest_offers: List[Offer] = []
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

                # Apply quality filters
                filtered: List[Offer] = []
                for o in vendor_offers:
                    if scan_config.min_rating is not None:
                        if o.rating is None or o.rating < scan_config.min_rating:
                            continue
                    if scan_config.min_stars is not None:
                        if o.stars is None or o.stars < scan_config.min_stars:
                            continue
                    filtered.append(o)

                dest_offers.extend(filtered)

            # Soft dedupe across vendors for this destination
            dest_offers = _dedupe_offers(dest_offers)
            offers_by_country[country_code].extend(dest_offers)

    metrics_by_country: Dict[str, CountryMetrics] = {}

    for country_code, offers in offers_by_country.items():
        if not offers:
            continue

        cost_index = cost_index_by_country.get(country_code, 1.0)

        # Normalize prices to base currency and attach effective_score
        pairs = []  # (offer, price_in_base)
        for o in offers:
            price_base = convert_amount(
                o.price_per_night,
                from_currency=o.currency,
                to_currency=base_currency,
                fx_rates=fx_rates,
            )
            o.effective_score = price_base * (cost_index ** alpha)
            pairs.append((o, price_base))

        if not pairs:
            continue

        pairs_sorted = sorted(pairs, key=lambda p: p[1])
        offers_sorted = [p[0] for p in pairs_sorted]
        prices_base = [p[1] for p in pairs_sorted]
        n = len(prices_base)
        p90_idx = max(0, int(n * 0.9) - 1)

        min_price_per_night = prices_base[0]
        median_price_per_night = median(prices_base)
        p90_price_per_night = prices_base[p90_idx]

        effective_min_price = min_price_per_night * (cost_index ** alpha)
        effective_median_price = median_price_per_night * (cost_index ** alpha)

        # Extra quality-aware metrics
        high_rating_prices = [
            convert_amount(o.price_per_night, o.currency, base_currency, fx_rates)
            for o in offers_sorted
            if o.rating is not None and o.rating >= 8.0
        ]
        stars3_prices = [
            convert_amount(o.price_per_night, o.currency, base_currency, fx_rates)
            for o in offers_sorted
            if o.stars is not None and o.stars >= 3
        ]

        median_high_rating = median(high_rating_prices) if high_rating_prices else None
        median_3plus_stars = median(stars3_prices) if stars3_prices else None

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
            currency=base_currency,
            offer_count=len(offers_sorted),
            offer_count_quality_filtered=len(high_rating_prices),
            median_price_high_rating=median_high_rating,
            median_price_3plus_stars=median_3plus_stars,
        )

    return metrics_by_country
