# EU Hotel Scanner – v1.0

This version is the first **stable, packaged release** with service layer and smoke tests on top of the v0.8
engine (cost index, optimiser, multi-vendor, caching).

You now get:

- A proper **Python package** (`pyproject.toml`).
- An installable **CLI** (`eu-hotel-scan`).
- A FastAPI-based **HTTP service** (`eu-hotel-api` / `service.api:app`).
- A Dockerfile suitable for containerising the API.

The underlying behaviour – country cost index + historical optimiser + multi
vendor – is unchanged.

---

## 1. Packaging

### Install in editable mode

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

pip install -r requirements.txt          # or: pip install -e .
pip install -e .
```

This installs the `eu-hotel-scanner` package with two console scripts:

- `eu-hotel-scan` – CLI wrapper around the scan engine.
- `eu-hotel-api` – starts the FastAPI service on port 8000.

The core package layout:

- `hotel_scanner/`
  - `__init__.py`
  - `models.py`
  - `aggregator.py`
  - `pricing.py`
  - `storage.py`
  - `cache.py`
  - `optimizer.py`
  - `vendors.py`
  - `clients/`
    - `base.py`
    - `mock_vendor.py`
    - `booking_api.py`
  - `cli.py` – shared CLI logic and `run_scan()` used by both CLI and API.
- `service/`
  - `__init__.py`
  - `api.py` – FastAPI app with `/health`, `/historical-summary`, `/scan`.
- `config/` – destinations, cost index, scanner settings, FX, vendors.
- `ui/` – `streamlit_app.py` (v0.9 UI).
- `scripts/` – `scan_eu.py` thin wrapper calling `hotel_scanner.cli.main()`.
- `data/` – `hotel_scanner.db` (created at first logged run).
- `cache/` – file-based cache for HTTP vendors (created on first use).

---

## 2. CLI: `eu-hotel-scan`

Once installed:

```bash
eu-hotel-scan \
  --checkin 2025-07-10 \
  --checkout 2025-07-15 \
  --use-optimizer \
  --optimizer-top-k 8
```

Key flags (same semantics as v0.8):

- `--checkin`, `--checkout` (required).
- `--min-price`, `--max-price` (vendor currency).
- `--alpha` (override cost-index exponent).
- `--min-rating`, `--min-stars`.
- `--base-currency` (default: EUR).
- `--use-optimizer` – turn on historical optimiser.
- `--optimizer-top-k N` – only scan top N countries by optimiser weight.
- `--optimizer-min-weight / --optimizer-max-weight`.

The CLI prints:

- Vendors used.
- Optimiser scan plan (if enabled).
- Country rankings by:
  - RAW min price (normalized to base currency).
  - EFFECTIVE min (price × cost_index^alpha).
- Logs results to SQLite (`data/hotel_scanner.db`).

`scripts/scan_eu.py` remains available for direct `python scripts/scan_eu.py`
use, but effectively just calls the same `main()`.

---

## 3. HTTP service: FastAPI

### Start via console script

```bash
eu-hotel-api
```

This runs:

- Host: `0.0.0.0`
- Port: `8000`
- App: `service.api:app`

Alternatively:

```bash
uvicorn service.api:app --host 0.0.0.0 --port 8000
```

### Key endpoints

- `GET /health`  
  Simple health check: `{"status": "ok"}`.

- `GET /historical-summary`  
  Returns the same aggregated mispricing table as the UI:

  ```json
  [
    {
      "country_code": "BG",
      "country_name": "Bulgaria",
      "cost_index": 1.0,
      "avg_median_price": 45.0,
      "avg_effective_median": 45.0,
      "normalized_median": 45.0
    },
    ...
  ]
  ```

- `POST /scan` – main entry point

  Request body (`ScanRequest`):

  ```json
  {
    "checkin": "2025-07-10",
    "checkout": "2025-07-15",
    "min_price": null,
    "max_price": null,
    "alpha": null,
    "min_rating": null,
    "min_stars": null,
    "base_currency": "EUR",
    "use_optimizer": true,
    "optimizer_top_k": 10,
    "optimizer_min_weight": 0.5,
    "optimizer_max_weight": 2.0,
    "log_results": true
  }
  ```

  Response (`ScanResponse`):

  ```json
  {
    "run_id": 42,
    "checkin": "2025-07-10",
    "checkout": "2025-07-15",
    "base_currency": "EUR",
    "alpha": 1.0,
    "vendors": ["mock_vendor"],
    "countries": [
      {
        "country_code": "BG",
        "country_name": "Bulgaria",
        "cost_index": 1.0,
        "min_price_per_night": 25.1,
        "median_price_per_night": 37.5,
        "p90_price_per_night": 80.2,
        "effective_min_price": 25.1,
        "effective_median_price": 37.5,
        "offer_count": 120,
        "offers": [
          {
            "vendor": "mock_vendor",
            "city": "Sofia",
            "hotel": "Sofia Hotel 123",
            "price_per_night": 25.1,
            "currency": "EUR",
            "rating": 8.4,
            "stars": 3,
            "deeplink": null,
            "effective_score": 25.1
          }
        ]
      }
    ]
  }
  ```

- If `log_results` is `false`, the API still uses SQLite for optimiser
  history, but returns `run_id = -1` to indicate "not persisted".

---

## 4. Docker image

Build and run:

```bash
docker build -t eu-hotel-scanner:1.0 .
docker run --rm -p 8000:8000 eu-hotel-scanner:1.0
```

You then have the FastAPI service on `http://localhost:8000`.

You can mount a volume for `data/` and `cache/` if you want persistence:

```bash
docker run --rm -p 8000:8000 \
  -v $(pwd)/data:/app/data \
  -v $(pwd)/cache:/app/cache \
  eu-hotel-scanner:1.0
```

---

## 5. Streamlit UI (unchanged in spirit)

For interactive exploration:

```bash
streamlit run ui/streamlit_app.py
```

You still get:

- Static cost index table.
- Country optimiser plan (with weights).
- Current run rankings (RAW vs EFFECTIVE).
- Cheapest offers per country.
- Historical mispricing table.

---

## 6. Real vendor integration reminder

The Booking-like HTTP client is still conservative and requires:

1. Real `base_url` and key in `.env` + `config/vendors.yaml`.
2. Filling in the actual endpoint path and field names in
   `hotel_scanner/clients/booking_api.py`.

Once wired, the same engine, CLI, UI, and API all operate on real data, with
multi-vendor aggregation, caching, and optimiser-driven country choice.


---

## 7. Tests (smoke-level)

Basic tests are included under `tests/`:

- `test_pricing.py` – sanity checks for FX conversion.
- `test_optimizer.py` – checks optimiser weights behave sensibly.
- `test_scan_smoke.py` – runs a short mock scan and asserts we get some country metrics.

To run them:

```bash
pip install pytest
pytest
```
