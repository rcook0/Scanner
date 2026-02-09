# EU Hotel Scanner – v0.8

This iteration adds a **search optimiser for country choice** on top of the
v0.7 multi-vendor + caching pipeline.

The 3-step logic stays the same:

1. Static **country cost index** (prior belief).
2. Observed **hotel prices** per country/date (from one or more vendors).
3. Logging + aggregation to see where reality diverges from the prior.

v0.8 makes step 2 smarter by deciding **which countries to scan and how deep**
based on both the prior and historical mispricing.

## Intuition

For each country we maintain:

- `cost_index` – prior "expensiveness".
- Historical `normalized_median` – roughly:

  `normalized_median ≈ (median price per night) / cost_index`

  via `get_historical_country_summary()`.

A country that is systematically cheaper than its cost index will have a
**low normalized_median**. Those are the places we want to spend more scan
budget on.

The optimiser computes a per-country **scan weight** and feeds it into the
core scan engine to:

- Skip low-priority countries entirely (weight = 0).
- Allocate **more cities and offers** to high-priority countries.

## Key additions

### 1. Optimiser core

`hotel_scanner/optimizer.py`:

- `build_country_scan_weights(cost_index_by_country, historical_summary, top_k=None, min_weight=0.5, max_weight=2.0)`

  Heuristic:

  - Prior cheapness: `1 / cost_index`.
  - If historical `normalized_median` is available:
    - Adjust by `1 / normalized_median`.
    - So `raw_weight ~ 1 / (cost_index * normalized_median)`.
  - If no history: fall back to `1 / cost_index`.

  Then:

  - Sort countries by `raw_weight` (higher = more attractive).
  - If `top_k` is set, only the top-k keep non-zero weight; others get 0.
  - Scale non-zero weights into `[min_weight, max_weight]` around the median.

  Return value: `country_code -> scan_weight` (0 means "do not scan").

- `summarize_country_weights(...)` – helper to show the scan plan in CLI/UI.

### 2. Aggregator: country_scan_weights

`hotel_scanner/aggregator.py`:

- `scan_destinations(...)` now accepts:

  ```python
  country_scan_weights: Optional[Dict[str, float]] = None
  ```

- For each `country_code`:

  - Look up `weight = country_scan_weights.get(code, 1.0)`.
  - If `weight <= 0`, the country is **skipped entirely**.
  - Otherwise:

    ```python
    target_cities = round(base_cities_per_country * weight / cost_index)
    max_offers_per_dest = round(base_offers_per_destination * weight / cost_index)
    ```

  - `scan_mode == "cheap_only"` and `max_cost_index_for_scan` still apply as
    an additional safety filter.

The rest of the engine is unchanged:

- Multi-vendor aggregation.
- Soft dedupe across vendors.
- FX normalization.
- Quality filters.
- Country metrics + logging.

### 3. CLI: optimiser flags

`scripts/scan_eu.py` gains:

- `--use-optimizer` – enable the country optimiser.
- `--optimizer-top-k` – scan only the top K countries (others get weight 0).
- `--optimizer-min-weight` / `--optimizer-max-weight` – bounds for scaling.

Flow:

1. Load destinations, cost index, scanner config, vendors.
2. Open DB via `get_connection` and fetch `historical_summary`.
3. If `--use-optimizer`:

   ```python
   country_scan_weights = build_country_scan_weights(
       cost_index_by_country,
       historical_summary,
       top_k=args.optimizer_top_k,
       min_weight=args.optimizer_min_weight,
       max_weight=args.optimizer_max_weight,
   )
   ```

4. Pass `country_scan_weights` into `scan_destinations(...)`.
5. Print an "Optimiser scan plan" table to stdout before the usual rankings.

### 4. UI: optimiser controls + plan

`ui/streamlit_app.py`:

- New sidebar block:

  - Checkbox: **"Use historical optimiser for country choice"**.
  - Slider: **"Max countries to scan (0 = all)"** (top_k).

- The app:

  - Loads `historical_summary` once from SQLite.
  - If optimiser is enabled, builds `country_scan_weights` and passes them to
    `scan_destinations`.
  - Shows an **"Optimiser scan plan (this run)"** table:

    - Country code & name.
    - Cost index.
    - Historical avg median €/night.
    - Historical normalized median.
    - Current scan weight.

- The existing panels remain:

  - Static cost-index table.
  - Current run rankings (raw vs effective).
  - Cheapest offers per country.
  - Historical mispricing vs cost index.

## Layout

Same overall layout as v0.7, plus the optimiser module and updated CLI/UI:

- `config/`
  - `destinations.yaml`
  - `country_cost_index.yaml`
  - `scanner.yaml`
  - `fx_rates.yaml`
  - `vendors.yaml`
- `.env.example`
- `hotel_scanner/`
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
- `scripts/`
  - `scan_eu.py`
- `ui/`
  - `streamlit_app.py`
- `data/`
  - `hotel_scanner.db` (created on first logged run)
- `cache/`
  - `booking/` (created automatically when caching is used)

## Quick examples

Mock-only run with optimiser disabled:

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt

export PYTHONPATH=.

python scripts/scan_eu.py --checkin 2025-07-10 --checkout 2025-07-15
```

Mock-only run with optimiser focusing on top 5 countries:

```bash
python scripts/scan_eu.py --checkin 2025-07-10 --checkout 2025-07-15 \
  --use-optimizer --optimizer-top-k 5
```

UI:

```bash
streamlit run ui/streamlit_app.py
```

Toggle the optimiser in the sidebar and watch how the "Optimiser scan plan"
and country rankings react as you accumulate historical runs.
