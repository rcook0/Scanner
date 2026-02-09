import random
from datetime import date
from typing import List, Optional

from hotel_scanner.clients.base import HotelVendorClient
from hotel_scanner.models import Destination, Offer


class MockVendorClient(HotelVendorClient):
    """Synthetic vendor used for development and testing.

    Generates random prices per-night in EUR for each destination.
    """

    def __init__(self, name: str = "mock_vendor", currency: str = "EUR"):
        self.name = name
        self.currency = currency

    def search_offers(
        self,
        destination: Destination,
        checkin: date,
        checkout: date,
        min_price: Optional[float] = None,
        max_price: Optional[float] = None,
        limit: int = 50,
    ) -> List[Offer]:
        nights = (checkout - checkin).days
        if nights <= 0:
            return []

        offers: List[Offer] = []
        for _ in range(limit):
            base = random.uniform(20, 200)  # price per night in EUR
            total = base * nights

            if min_price is not None and base < min_price:
                continue
            if max_price is not None and base > max_price:
                continue

            offers.append(
                Offer(
                    vendor=self.name,
                    country_code=destination.country_code,
                    country_name=destination.country_name,
                    city_name=destination.city_name,
                    checkin=checkin,
                    checkout=checkout,
                    hotel_name=f"{destination.city_name} Hotel {random.randint(1, 999)}",
                    total_price=total,
                    currency=self.currency,
                    price_per_night=base,
                    rating=round(random.uniform(6.5, 9.5), 1),
                    stars=random.randint(1, 5),
                    deeplink=None,
                )
            )

        return offers
