# EU Hotel Scanner – v0.6

This iteration wires in a **real vendor integration harness**, while still
remaining conservative about actual proprietary API details.

v0.6 is shaped around three ideas:

1. Keep the cost-index + FX + quality-filter pipeline from v0.5.
2. Introduce a clean way to add **live HTTP vendors** alongside the mock vendor.
3. Use config + env vars so that credentials and endpoints live outside code.

## Key additions

### 1. Vendor configuration

`config/vendors.yaml` controls which vendors are active:

```yaml
mode: "mock"   # "mock" | "live" | "mixed"

mock:
  enabled: true

booking:
  enabled: false
  base_url: "https://YOUR-BOOKING-API-BASE"      # fill from official docs
  api_key_env: "BOOKING_API_KEY"
  timeout_seconds: 10
```

- `mode="mock"` – use only `MockVendorClient`.
- `mode="live"` – use only live vendors (e.g. `BookingApiClient`) that are enabled.
- `mode="mixed"` – combine mock + live vendors.

Credentials are pulled from environment variables, typically loaded from `.env`
via `python-dotenv`. A `.env.example` is provided.

### 2. BookingApiClient harness

`hotel_scanner/clients/booking_api.py` implements:

- HTTP GET with:
  - Configurable `base_url`.
  - API key injected via header (you may need to change the header name).
  - Placeholder query parameters for destination, dates, currency, etc.
- Error handling:
  - HTTP errors and JSON decode issues are caught and logged to stdout.
  - Malformed entries in the JSON are skipped.
- A **clearly marked TODO section** where you must map the real JSON schema
  from your chosen API into the internal `Offer` model.

It is intentionally generic and does not assume any particular proprietary
Booking.com or Expedia schema.

### 3. Vendor builder

`hotel_scanner/vendors.py` exposes:

- `build_vendors(config/vendors.yaml)` → `List[HotelVendorClient]`

It:

- Reads `mode` and per-vendor blocks.
- Instantiates `MockVendorClient` and/or `BookingApiClient` if enabled and
  correctly configured.
- Falls back to `MockVendorClient` if nothing is usable.

Both the CLI and Streamlit UI now use this builder.

## Layout

- `config/`
  - `destinations.yaml`
  - `country_cost_index.yaml`
  - `scanner.yaml`
  - `fx_rates.yaml`
  - `vendors.yaml`
- `.env.example` – template for API keys.
- `hotel_scanner/`
  - `models.py`
  - `aggregator.py`
  - `pricing.py`
  - `storage.py`
  - `vendors.py`
  - `clients/`
    - `base.py`
    - `mock_vendor.py`
    - `booking_api.py`
- `scripts/`
  - `scan_eu.py` – CLI entrypoint that now:
    - loads `.env`,
    - builds vendors from `vendors.yaml`,
    - runs the scan,
    - logs to SQLite.
- `ui/`
  - `streamlit_app.py` – UI that:
    - uses the same vendor builder,
    - shows which vendors are active for the current run.
- `data/`
  - `hotel_scanner.db` – created on first logged run.

## Quick start (mock-only, as before)

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt

export PYTHONPATH=.

# Ensure config/vendors.yaml has mode: "mock"
python scripts/scan_eu.py --checkin 2025-07-10 --checkout 2025-07-15
```

## Enabling a live vendor

1. Copy `.env.example` to `.env` and fill in your key:

```env
BOOKING_API_KEY=YOUR_REAL_API_KEY_HERE
```

2. Edit `config/vendors.yaml`:

```yaml
mode: "live"
booking:
  enabled: true
  base_url: "https://YOUR-BOOKING-API-BASE"
  api_key_env: "BOOKING_API_KEY"
  timeout_seconds: 10
```

3. Open `hotel_scanner/clients/booking_api.py` and replace:

- `YOUR_SEARCH_ENDPOINT` with the correct search path.
- The placeholder parameter names and JSON field accesses with real ones,
  based on the official docs of your chosen API.

After that, the rest of the pipeline (cost index, FX, filters, logging, and
historical mispricing analysis) works unchanged with live data.
