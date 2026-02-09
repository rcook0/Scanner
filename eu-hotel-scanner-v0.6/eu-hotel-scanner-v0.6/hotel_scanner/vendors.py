import os
from pathlib import Path
from typing import List

import yaml

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

    if mode in ("mock", "mixed") and mock_cfg.get("enabled", True):
        vendors.append(MockVendorClient())

    if mode in ("live", "mixed") and booking_cfg.get("enabled", False):
        base_url = booking_cfg.get("base_url")
        api_key_env = booking_cfg.get("api_key_env", "BOOKING_API_KEY")
        timeout_seconds = int(booking_cfg.get("timeout_seconds", 10))

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
                )
            )

    if not vendors:
        # Always ensure at least one vendor so the rest of the pipeline works
        print("[vendors] No vendors configured/enabled, falling back to MockVendorClient.")
        vendors.append(MockVendorClient())

    return vendors
