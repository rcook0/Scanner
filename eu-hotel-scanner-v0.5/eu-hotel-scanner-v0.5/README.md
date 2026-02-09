# EU Hotel Scanner – v0.5

This iteration focuses on **data quality and richer metrics** while keeping the
same 3-step mechanism:

1. A static **country cost index** as a prior.
2. Observed **hotel prices per country/date** (from vendors or mock).
3. Logging + aggregation to see where reality diverges from the prior.

v0.5 adds:

- A simple **FX layer** so all per-country metrics are computed in a chosen
  base currency (default: EUR).
- **Quality filters**:
  - Min hotel rating.
  - Min star rating.
- Extra metrics per country:
  - `offer_count`
  - `median_price_high_rating` (rating ≥ 8.0)
  - `median_price_3plus_stars` (stars ≥ 3)

These make comparisons cleaner (e.g. “3★+ hotels with rating ≥ 8”) and reduce
noise from very low-quality inventory.

## Layout

- `config/`
  - `destinations.yaml` – list of countries and cities (with optional vendor IDs).
  - `country_cost_index.yaml` – static cost index per country.
  - `scanner.yaml` – knobs for CLI scan strategy + optional quality filters.
  - `fx_rates.yaml` – static FX table used to normalize prices.
- `hotel_scanner/`
  - `models.py` – core dataclasses (Destination, Offer, CountryMetrics).
  - `aggregator.py` – cost-guided scan engine with filters + FX.
  - `pricing.py` – FX loading and amount conversion.
  - `storage.py` – SQLite logging + historical aggregation.
  - `clients/`
    - `base.py` – vendor interface.
    - `mock_vendor.py` – synthetic data generator for development.
    - `booking_api.py` – skeleton for a real Booking.com API client.
- `scripts/`
  - `scan_eu.py` – CLI entrypoint with quality filters + logging.
- `ui/`
  - `streamlit_app.py` – interactive UI showcasing:
    - rating/star filters,
    - base currency selection,
    - richer per-country metrics.
- `data/`
  - `hotel_scanner.db` – created on first logged run.

## Quick start (CLI)

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt

export PYTHONPATH=.

python scripts/scan_eu.py --checkin 2025-07-10 --checkout 2025-07-15 \
  --min-rating 7.5 --min-stars 3 --base-currency EUR
```

## Quick start (UI)

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt

export PYTHONPATH=.

streamlit run ui/streamlit_app.py
```

Under the hood it still uses `MockVendorClient`, but the pipeline is now ready
for real multi-currency vendors without changing the core logic.
