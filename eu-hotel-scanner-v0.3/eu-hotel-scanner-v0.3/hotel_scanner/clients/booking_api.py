from datetime import date
from typing import List, Optional

import requests

from hotel_scanner.clients.base import HotelVendorClient
from hotel_scanner.models import Destination, Offer


class BookingApiClient(HotelVendorClient):
    """Skeleton Booking.com API client.

    You must fill in:
    - base_url and endpoint paths (from official Booking docs)
    - authentication scheme
    - JSON -> Offer mapping
    """

    def __init__(self, api_key: str, base_url: str):
        self.name = "booking_api"
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")

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
            return []

        params = {
            # Placeholder parameter names – replace with real Booking API keys
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

        headers = {
            # Replace with the real auth scheme
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/json",
        }

        resp = requests.get(
            f"{self.base_url}/YOUR_SEARCH_ENDPOINT",  # fill in
            params=params,
            headers=headers,
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()

        # Implement proper JSON -> Offer mapping here once you know the schema
        raise NotImplementedError(
            "Implement BookingApiClient.search_offers based on the real Booking API schema."
        )
