# EU Hotel Scanner – v0.7

This iteration adds **multi-vendor aggregation** and a simple **file-based
response cache** for HTTP vendors, on top of the v0.6 real-vendor harness.

The core 3-step mechanism is unchanged:

1. Static **country cost index** (prior belief).
2. Observed **hotel prices** per country/date (from one or more vendors).
3. Logging + aggregation to see where reality diverges from the prior.

v0.7 focuses on making step 2 more efficient and robust:

- **Multi-vendor**: query several vendors for the same destination.
- **Soft dedupe**: merge offers per (city, hotel_name), keeping the cheapest.
- **Caching**: avoid re-hitting HTTP APIs for identical queries.

## Key additions

### 1. FileResponseCache

`hotel_scanner/cache.py` defines:

```python
@dataclass
class FileResponseCache:
    root: Path
    ttl_seconds: int = 43200  # 12 hours

    def get(self, key: str) -> Optional[Any]:
        ...
    def set(self, key: str, payload: Any) -> None:
        ...
```

- Stores arbitrary JSON-serialisable payloads under a SHA-256 key.
- Uses file modification time to enforce a TTL.
- Used by HTTP vendors (e.g. `BookingApiClient`) to cache raw JSON responses.

### 2. BookingApiClient + caching

`hotel_scanner/clients/booking_api.py` now:

- Accepts `cache: FileResponseCache | None` and `cache_enabled: bool`.
- Builds a cache key from `(vendor, dest_id, checkin, checkout, min/max price)`.
- On each search:
  - Tries to fetch from cache first.
  - On miss, calls the external API and then writes to the cache.

The JSON → `Offer` mapping is still intentionally generic and must be adapted to
your actual API schema.

### 3. Vendor builder with cache configuration

`config/vendors.yaml` gains a `cache` block:

```yaml
booking:
  enabled: false
  base_url: "https://YOUR-BOOKING-API-BASE"
  api_key_env: "BOOKING_API_KEY"
  timeout_seconds: 10
  cache:
    enabled: true
    ttl_seconds: 43200   # 12h
    dir: "cache/booking"
```

`hotel_scanner/vendors.py`:

- Computes the project root.
- Instantiates `FileResponseCache(root / dir, ttl_seconds)` when enabled.
- Passes the cache into `BookingApiClient`.

### 4. Multi-vendor aggregation + soft dedupe

`hotel_scanner/aggregator.py`:

- For each destination:
  - Iterates over **all vendors**.
  - Collects offers, applies quality filters (rating/stars).
  - Then applies `_dedupe_offers(dest_offers)`:

```python
def _dedupe_offers(offers: List[Offer]) -> List[Offer]:
    # key = (city_name, hotel_name), keep cheapest price_per_night
```

- This keeps one “best” price per hotel per city across vendors, reducing
  double-counting in country-level stats.

Country metrics and logging remain the same, but:

- `offer_count` now counts **deduped** offers.
- You still get:
  - min / median / p90 (in base currency),
  - effective prices (× cost_index^alpha),
  - median prices for high-rating and ≥3★ hotels.

## Layout

Same overall layout as v0.6, plus `hotel_scanner/cache.py` and updated vendors
config:

- `config/`
  - `destinations.yaml`
  - `country_cost_index.yaml`
  - `scanner.yaml`
  - `fx_rates.yaml`
  - `vendors.yaml` (with cache section)
- `.env.example`
- `hotel_scanner/`
  - `models.py`
  - `aggregator.py`
  - `pricing.py`
  - `storage.py`
  - `cache.py`
  - `vendors.py`
  - `clients/`
    - `base.py`
    - `mock_vendor.py`
    - `booking_api.py`
- `scripts/`
  - `scan_eu.py`
- `ui/`
  - `streamlit_app.py`
- `data/`
  - `hotel_scanner.db` (created on first logged run)
- `cache/`
  - `booking/` (created automatically when caching is used)

## Quick start (mock-only, multi-vendor shape)

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt

export PYTHONPATH=.

# Ensure config/vendors.yaml has mode: "mock"
python scripts/scan_eu.py --checkin 2025-07-10 --checkout 2025-07-15
```

To enable a live vendor, follow the v0.6 instructions (fill `.env`, configure
`booking` block, and finish the JSON mapping in `BookingApiClient`). The cache
then kicks in automatically based on `config/vendors.yaml`.
