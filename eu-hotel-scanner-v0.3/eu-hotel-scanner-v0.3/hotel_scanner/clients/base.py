from abc import ABC, abstractmethod
from datetime import date
from typing import List, Optional

from hotel_scanner.models import Destination, Offer


class HotelVendorClient(ABC):
    name: str

    @abstractmethod
    def search_offers(
        self,
        destination: Destination,
        checkin: date,
        checkout: date,
        min_price: Optional[float] = None,
        max_price: Optional[float] = None,
        limit: int = 50,
    ) -> List[Offer]:
        """Return a list of offers for a destination and date range."""
        raise NotImplementedError
