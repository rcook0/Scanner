# EU Hotel Scanner – v0.2

Toy / prototype project for scanning EU destinations using API-capable hotel vendors,
ranking countries by hotel cost and a country-level cost index.

## Layout

- `config/`
  - `destinations.yaml` – list of countries and cities (with optional vendor IDs).
  - `country_cost_index.yaml` – static cost index per country (cheapest = 1.0).
  - `scanner.yaml` – knobs for scan strategy (cheap_only vs all, delays, etc.).
- `hotel_scanner/`
  - `models.py` – core dataclasses (Destination, Offer, CountryMetrics).
  - `aggregator.py` – cost-guided scan engine.
  - `clients/`
    - `base.py` – vendor interface.
    - `mock_vendor.py` – synthetic data generator for development.
    - `booking_api.py` – skeleton for a real Booking.com API client.
- `scripts/`
  - `scan_eu.py` – CLI entrypoint.

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# Ensure Python can find the package
export PYTHONPATH=.

python scripts/scan_eu.py --checkin 2025-07-10 --checkout 2025-07-15
```

The current implementation uses `MockVendorClient` only and generates synthetic
prices in EUR. Once you have real API credentials you can implement and plug in
`BookingApiClient` / other vendor clients without changing the aggregator logic.
