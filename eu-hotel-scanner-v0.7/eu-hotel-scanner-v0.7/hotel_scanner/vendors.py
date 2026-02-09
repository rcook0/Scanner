import os
from pathlib import Path
from typing import List

import yaml

from hotel_scanner.cache import FileResponseCache
from hotel_scanner.clients.booking_api import BookingApiClient
from hotel_scanner.clients.mock_vendor import MockVendorClient
from hotel_scanner.clients.base import HotelVendorClient


def load_vendor_config(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def build_vendors(cfg_path: Path) -> List[HotelVendorClient]:
    cfg = load_vendor_config(cfg_path)

    mode = cfg.get("mode", "mock")
    vendors: List[HotelVendorClient] = []

    mock_cfg = cfg.get("mock", {}) or {}
    booking_cfg = cfg.get("booking", {}) or {}

    # Determine project root (two levels up from this file)
    root = Path(__file__).resolve().parents[1]

    if mode in ("mock", "mixed") and mock_cfg.get("enabled", True):
        vendors.append(MockVendorClient())

    if mode in ("live", "mixed") and booking_cfg.get("enabled", False):
        base_url = booking_cfg.get("base_url")
        api_key_env = booking_cfg.get("api_key_env", "BOOKING_API_KEY")
        timeout_seconds = int(booking_cfg.get("timeout_seconds", 10))

        cache_cfg = booking_cfg.get("cache", {}) or {}
        cache_enabled = bool(cache_cfg.get("enabled", True))
        cache_ttl = int(cache_cfg.get("ttl_seconds", 43200))
        cache_dir = cache_cfg.get("dir", "cache/booking")
        cache = None
        if cache_enabled:
            cache = FileResponseCache(root / cache_dir, ttl_seconds=cache_ttl)

        api_key = os.environ.get(api_key_env)
        if not api_key:
            print(
                f"[vendors] Env var {api_key_env} not set, BookingApiClient will be skipped."
            )
        elif not base_url:
            print("[vendors] booking.base_url not configured, BookingApiClient skipped.")
        else:
            vendors.append(
                BookingApiClient(
                    api_key=api_key,
                    base_url=base_url,
                    timeout_seconds=timeout_seconds,
                    cache=cache,
                    cache_enabled=cache_enabled,
                )
            )

    if not vendors:
        # Always ensure at least one vendor so the rest of the pipeline works
        print("[vendors] No vendors configured/enabled, falling back to MockVendorClient.")
        vendors.append(MockVendorClient())

    return vendors
