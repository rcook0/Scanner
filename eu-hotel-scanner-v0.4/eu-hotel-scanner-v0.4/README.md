# EU Hotel Scanner – v0.4

Prototype project for scanning EU destinations using API-capable hotel vendors,
ranking countries by hotel cost and a country-level cost index.

v0.4 focuses on the third step of the mechanism:

1. **Static prior** – a country cost index (cheapest = 1.0, others ≥ 1).
2. **Observed data** – for each scan, compute per-country hotel price metrics
   (min / median / p90) and cost-adjusted metrics using the index + alpha.
3. **Comparison & logging** – log each run to SQLite and aggregate across runs
   to see which countries are systematically cheaper or more expensive than
   their cost index suggests.

## Layout

- `config/`
  - `destinations.yaml` – list of countries and cities (with optional vendor IDs).
  - `country_cost_index.yaml` – static cost index per country.
  - `scanner.yaml` – knobs for CLI scan strategy.
- `hotel_scanner/`
  - `models.py` – core dataclasses (Destination, Offer, CountryMetrics).
  - `aggregator.py` – cost-guided scan engine (macro index → micro offers).
  - `storage.py` – SQLite logging + historical aggregation.
  - `clients/`
    - `base.py` – vendor interface.
    - `mock_vendor.py` – synthetic data generator for development.
    - `booking_api.py` – skeleton for a real Booking.com API client.
- `scripts/`
  - `scan_eu.py` – CLI entrypoint with logging (v0.4).
- `ui/`
  - `streamlit_app.py` – interactive UI for running scans and viewing historical
    mispricing vs the cost index.
- `data/`
  - `hotel_scanner.db` – created on first run; stores runs + per-country metrics.

## Quick start (CLI)

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt

export PYTHONPATH=.

python scripts/scan_eu.py --checkin 2025-07-10 --checkout 2025-07-15
```

This logs a run into `data/hotel_scanner.db` and prints raw vs cost-adjusted
rankings.

## Quick start (UI)

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt

export PYTHONPATH=.

streamlit run ui/streamlit_app.py
```

### The 3-step mechanism

- The **cost index** encodes your prior belief about which countries are
  structurally cheap or expensive.
- Each scan produces **observed hotel prices** per country for specific dates.
- v0.4 logs those observations and computes a **normalized median**:
  `normalized_median = median_price / cost_index`.

Countries with a **low normalized median** are coming in cheaper than their
index would suggest (potential bargains). Countries with a **high normalized
median** are consistently pricier than their nominal cost index. Over multiple
runs (different date ranges), this builds a simple, data-backed view of where
your prior is under- or over-estimating reality.
