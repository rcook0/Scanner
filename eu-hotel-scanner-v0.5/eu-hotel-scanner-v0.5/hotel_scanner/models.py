from dataclasses import dataclass
from datetime import date
from typing import Dict, List, Optional


@dataclass
class Destination:
    country_code: str   # "BG"
    country_name: str   # "Bulgaria"
    city_name: str      # "Sofia"
    vendor_ref: Dict[str, str]  # e.g. {"booking": "12345"}, empty if unused


@dataclass
class Offer:
    vendor: str
    country_code: str
    country_name: str
    city_name: str
    checkin: date
    checkout: date
    hotel_name: str
    total_price: float
    currency: str
    price_per_night: float
    rating: Optional[float] = None
    stars: Optional[int] = None
    deeplink: Optional[str] = None
    # Filled by aggregator when cost-index weighting is applied
    effective_score: Optional[float] = None


@dataclass
class CountryMetrics:
    country_code: str
    country_name: str
    offers: List[Offer]
    min_price_per_night: float
    median_price_per_night: float
    p90_price_per_night: float
    cost_index: float
    effective_min_price: float
    effective_median_price: float
    # v0.5 additions
    currency: str = "EUR"
    offer_count: int = 0
    offer_count_quality_filtered: int = 0
    median_price_high_rating: Optional[float] = None  # rating >= threshold, e.g. 8.0
    median_price_3plus_stars: Optional[float] = None  # stars >= 3
