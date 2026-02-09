# EU Hotel Scanner – v0.3

Toy / prototype project for scanning EU destinations using API-capable hotel vendors,
ranking countries by hotel cost and a country-level cost index.

v0.3 adds a simple Streamlit UI where you can:

- Tune **alpha** (cost bias exponent) to control how strongly the country cost index
  affects rankings.
- See the **country cost index** table.
- Inspect raw vs cost-adjusted rankings and sample cheapest offers per country
  (mock data).

## Layout

- `config/`
  - `destinations.yaml` – list of countries and cities (with optional vendor IDs).
  - `country_cost_index.yaml` – static cost index per country (cheapest = 1.0).
  - `scanner.yaml` – knobs for CLI scan strategy.
- `hotel_scanner/`
  - `models.py` – core dataclasses (Destination, Offer, CountryMetrics).
  - `aggregator.py` – cost-guided scan engine.
  - `clients/`
    - `base.py` – vendor interface.
    - `mock_vendor.py` – synthetic data generator for development.
    - `booking_api.py` – skeleton for a real Booking.com API client.
- `scripts/`
  - `scan_eu.py` – CLI entrypoint (same logic as v0.2).
- `ui/`
  - `streamlit_app.py` – interactive UI for v0.3.

## Quick start (CLI)

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt

export PYTHONPATH=.

python scripts/scan_eu.py --checkin 2025-07-10 --checkout 2025-07-15
```

## Quick start (UI)

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt

export PYTHONPATH=.

streamlit run ui/streamlit_app.py
```

Current implementation uses `MockVendorClient` only and generates synthetic
prices in EUR. Once you have real API credentials you can implement and plug in
`BookingApiClient` / other vendor clients without changing the aggregator or UI logic.
