from datetime import date
from typing import List, Optional

import requests

from hotel_scanner.cache import FileResponseCache
from hotel_scanner.clients.base import HotelVendorClient
from hotel_scanner.models import Destination, Offer


class BookingApiClient(HotelVendorClient):
    """HTTP client for a Booking.com-like public API with simple caching.

    This is intentionally conservative:
    - It does NOT assume any specific proprietary endpoint or parameter names.
    - You MUST fill in the real endpoint path and JSON mapping based on the
      official documentation of whatever API you are using.

    Caching:
    - Uses FileResponseCache to store raw JSON responses keyed by
      (destination, date range, price filters).
    - This reduces the pressure on the external API and smooths over retries.
    """

    def __init__(
        self,
        api_key: str,
        base_url: str,
        timeout_seconds: int = 10,
        name: str = "booking_api",
        cache: Optional[FileResponseCache] = None,
        cache_enabled: bool = True,
    ):
        self.name = name
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.cache = cache
        self.cache_enabled = cache_enabled

    def _cache_key(
        self,
        dest_id: str,
        checkin: date,
        checkout: date,
        min_price: Optional[float],
        max_price: Optional[float],
    ) -> str:
        return (
            f"{self.name}|dest={dest_id}|"
            f"in={checkin.isoformat()}|out={checkout.isoformat()}|"
            f"min={min_price if min_price is not None else ''}|"
            f"max={max_price if max_price is not None else ''}"
        )

    def search_offers(
        self,
        destination: Destination,
        checkin: date,
        checkout: date,
        min_price: Optional[float] = None,
        max_price: Optional[float] = None,
        limit: int = 50,
    ) -> List[Offer]:
        dest_id = destination.vendor_ref.get("booking")
        if not dest_id:
            # No mapping for this vendor/destination yet
            return []

        cache_key = self._cache_key(dest_id, checkin, checkout, min_price, max_price)
        data = None
        if self.cache_enabled and self.cache is not None:
            data = self.cache.get(cache_key)

        if data is None:
            # --- You must replace these with real parameter names from the API docs ---
            params = {
                "destination_id": dest_id,
                "checkin": checkin.isoformat(),
                "checkout": checkout.isoformat(),
                "currency": "EUR",
                "page_size": limit,
            }
            if min_price is not None:
                params["min_price"] = min_price
            if max_price is not None:
                params["max_price"] = max_price
            # ---------------------------------------------------------------------------

            headers = {
                # Replace with the correct auth scheme (e.g. header name) for your API
                "Authorization": f"Bearer {self.api_key}",
                "Accept": "application/json",
            }

            url = f"{self.base_url}/YOUR_SEARCH_ENDPOINT"  # TODO: fill real path
            try:
                resp = requests.get(
                    url,
                    params=params,
                    headers=headers,
                    timeout=self.timeout_seconds,
                )
                resp.raise_for_status()
            except requests.RequestException as exc:
                print(f"[{self.name}] HTTP error for {destination.city_name}: {exc}")
                return []

            try:
                data = resp.json()
            except ValueError:
                print(f"[{self.name}] Non-JSON response for {destination.city_name}")
                return []

            if self.cache_enabled and self.cache is not None:
                try:
                    self.cache.set(cache_key, data)
                except Exception as exc:
                    print(f"[{self.name}] Failed to write cache: {exc}")

        # --- Map JSON -> Offer list ---
        # The structure below is a placeholder. Adapt it to match your API.
        results = data.get("results") or data.get("hotels") or []
        offers: List[Offer] = []

        for item in results:
            try:
                # Replace these keys with real response fields
                hotel_name = item.get("hotel_name") or item.get("name") or "Unknown hotel"
                total_price = float(
                    item.get("total_price")
                    or item.get("price_total")
                    or item.get("price", 0.0)
                )
                currency = (
                    item.get("currency")
                    or item.get("currency_code")
                    or "EUR"
                )
                nights = (checkout - checkin).days
                if nights <= 0:
                    continue
                price_per_night = total_price / nights

                rating = item.get("review_score") or item.get("rating")
                stars = item.get("stars") or item.get("star_rating")

                deeplink = item.get("url") or item.get("deeplink")

                offers.append(
                    Offer(
                        vendor=self.name,
                        country_code=destination.country_code,
                        country_name=destination.country_name,
                        city_name=destination.city_name,
                        checkin=checkin,
                        checkout=checkout,
                        hotel_name=hotel_name,
                        total_price=total_price,
                        currency=str(currency),
                        price_per_night=price_per_night,
                        rating=float(rating) if rating is not None else None,
                        stars=int(stars) if stars is not None else None,
                        deeplink=deeplink,
                    )
                )
            except Exception as exc:
                # Skip malformed entries
                print(f"[{self.name}] Skipping malformed result: {exc}")
                continue

        return offers
