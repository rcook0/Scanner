import datetime
from pathlib import Path
from typing import Dict, List

import streamlit as st
import yaml
from dotenv import load_dotenv

from hotel_scanner.aggregator import ScanConfig, scan_destinations
from hotel_scanner.models import Destination
from hotel_scanner.pricing import load_fx_rates
from hotel_scanner.storage import (
    DEFAULT_DB_PATH,
    get_connection,
    get_historical_country_summary,
    log_country_metrics,
    log_run,
)
from hotel_scanner.vendors import build_vendors
from hotel_scanner.optimizer import build_country_scan_weights, summarize_country_weights


ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = ROOT / "config"


def load_destinations(path: Path) -> List[Destination]:
    with path.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    destinations: List[Destination] = []
    for entry in raw:
        country_code = entry["country_code"]
        country_name = entry["country_name"]
        for city in entry["cities"]:
            if isinstance(city, str):
                city_name = city
                vendor_ref = {}
            else:
                city_name = city["name"]
                vendor_ref = city.get("vendor_ref", {}) or {}

            destinations.append(
                Destination(
                    country_code=country_code,
                    country_name=country_name,
                    city_name=city_name,
                    vendor_ref=vendor_ref,
                )
            )
    return destinations


def load_country_cost_index(path: Path) -> Dict[str, float]:
    with path.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    mapping: Dict[str, float] = {}
    for entry in raw:
        mapping[entry["country_code"]] = float(entry["cost_index"])
    return mapping


def main():
    st.set_page_config(
        page_title="EU Hotel Scanner – v1.0",
        layout="wide",
    )

    st.title("EU Hotel Scanner – v1.0")
    st.caption(
        "Search optimiser for country choice + service-ready packaging. "
        "Same core engine as v0.8, now wrapped as a Python package with CLI and API."
    )

    # Load .env for any keys
    load_dotenv()

    # Core config and static data
    destinations = load_destinations(CONFIG_DIR / "destinations.yaml")
    cost_index_by_country = load_country_cost_index(CONFIG_DIR / "country_cost_index.yaml")
    country_codes = sorted({d.country_code for d in destinations})
    country_name_by_code = {d.country_code: d.country_name for d in destinations}

    # Sidebar config
    with st.sidebar:
        st.header("Scan parameters")

        today = datetime.date.today()
        default_checkin = today + datetime.timedelta(days=30)
        default_checkout = default_checkin + datetime.timedelta(days=5)

        checkin = st.date_input("Check-in", value=default_checkin)
        checkout = st.date_input("Check-out", value=default_checkout)

        min_price = st.number_input(
            "Min price per night (vendor currency)",
            value=0.0,
            min_value=0.0,
            step=5.0,
        )
        max_price = st.number_input(
            "Max price per night (vendor currency)",
            value=0.0,
            min_value=0.0,
            step=5.0,
            help="0 = no upper bound",
        )
        if max_price <= 0:
            max_price = None
        if min_price <= 0:
            min_price = None

        scan_mode = st.selectbox(
            "Scan mode",
            options=["cheap_only", "all"],
            help="cheap_only: skip countries above max cost index.",
        )

        max_cost_idx = st.slider(
            "Max cost index for scan (cheap_only)",
            min_value=1.0,
            max_value=3.0,
            value=1.8,
            step=0.1,
        )

        base_cities = st.slider(
            "Base cities per country",
            min_value=1,
            max_value=10,
            value=3,
        )
        base_offers = st.slider(
            "Base offers per destination",
            min_value=10,
            max_value=200,
            value=50,
            step=10,
        )

        alpha = st.slider(
            "Alpha (cost bias exponent)",
            min_value=0.0,
            max_value=3.0,
            value=1.0,
            step=0.1,
            help="0 = ignore country cost index, higher = stronger bias to cheap countries.",
        )

        min_rating = st.slider(
            "Min hotel rating (filter)",
            min_value=0.0,
            max_value=10.0,
            value=0.0,
            step=0.1,
        )
        min_stars = st.slider(
            "Min hotel stars (filter)",
            min_value=0,
            max_value=5,
            value=0,
            step=1,
        )

        fx_rates = load_fx_rates(CONFIG_DIR / "fx_rates.yaml")
        base_currency = st.selectbox(
            "Base currency for metrics",
            options=sorted(fx_rates.keys()),
            index=sorted(fx_rates.keys()).index("EUR") if "EUR" in fx_rates else 0,
        )

        st.markdown("---")
        st.subheader("Country optimiser")

        use_optimizer = st.checkbox(
            "Use historical optimiser for country choice",
            value=True,
            help="When enabled, the scanner focuses its budget on countries that "
                 "look systematically cheap vs the cost index.",
        )
        max_countries_slider_max = max(1, len(country_codes))
        optimizer_top_k = st.slider(
            "Max countries to scan (0 = all)",
            min_value=0,
            max_value=max_countries_slider_max,
            value=min(10, max_countries_slider_max),
        )

        log_enabled = st.checkbox(
            "Log results to SQLite (data/hotel_scanner.db)",
            value=True,
        )

        run_btn = st.button("Run scan")

    st.subheader("Static country cost index (prior belief)")
    idx_rows = []
    for code in country_codes:
        name = country_name_by_code.get(code, code)
        idx = cost_index_by_country.get(code, 1.0)
        idx_rows.append({"Country code": code, "Country": name, "Cost index": idx})
    st.table(idx_rows)

    # Historical DB summary (for optimiser + mispricing view)
    conn_hist = get_connection(DEFAULT_DB_PATH)
    historical_summary = get_historical_country_summary(conn_hist)

    if not run_btn:
        st.info(
            "Adjust parameters in the sidebar and click **Run scan**. "
            "The optimiser uses historical runs to focus on best-value countries."
        )
    else:
        if checkin >= checkout:
            st.error("Check-out date must be after check-in.")
            return

        scan_cfg = ScanConfig(
            scan_mode=scan_mode,
            max_cost_index_for_scan=max_cost_idx,
            base_cities_per_country=base_cities,
            base_offers_per_destination=base_offers,
            delay_seconds=(0.02, 0.05),  # very small delays in UI mock
            alpha=alpha,
            min_rating=min_rating if min_rating > 0 else None,
            min_stars=min_stars if min_stars > 0 else None,
        )

        vendors = build_vendors(CONFIG_DIR / "vendors.yaml")

        # Build optimiser weights if enabled
        country_scan_weights = None
        if use_optimizer:
            top_k = optimizer_top_k if optimizer_top_k > 0 else None
            country_scan_weights = build_country_scan_weights(
                cost_index_by_country=cost_index_by_country,
                historical_summary=historical_summary,
                top_k=top_k,
                min_weight=0.5,
                max_weight=2.0,
            )

        with st.spinner("Running scan (multi-vendor, optimiser-guided)..."):
            metrics_by_country = scan_destinations(
                destinations=destinations,
                vendors=vendors,
                checkin=checkin,
                checkout=checkout,
                min_price=min_price,
                max_price=max_price,
                cost_index_by_country=cost_index_by_country,
                scan_config=scan_cfg,
                fx_rates=fx_rates,
                base_currency=base_currency,
                country_scan_weights=country_scan_weights,
            )

        st.caption(f"Active vendors: {[v.name for v in vendors]}")

        if not metrics_by_country:
            st.warning("No offers found with the current filters.")
        else:
            st.success("Scan complete.")

            if log_enabled:
                run_id = log_run(
                    conn_hist,
                    checkin=checkin,
                    checkout=checkout,
                    scan_mode=scan_cfg.scan_mode,
                    alpha=scan_cfg.alpha,
                    min_price=min_price,
                    max_price=max_price,
                )
                log_country_metrics(conn_hist, run_id, metrics_by_country)
                st.caption(f"Logged run id: {run_id} → {DEFAULT_DB_PATH}")

            # Optimiser plan table
            if use_optimizer and country_scan_weights:
                st.subheader("Optimiser scan plan (this run)")
                plan_rows = summarize_country_weights(
                    cost_index_by_country,
                    historical_summary,
                    country_scan_weights,
                    country_name_by_code=country_name_by_code,
                )
                st.dataframe(plan_rows, use_container_width=True)

            sorted_by_min = sorted(
                metrics_by_country.values(),
                key=lambda m: m.min_price_per_night,
            )
            sorted_by_effective = sorted(
                metrics_by_country.values(),
                key=lambda m: m.effective_min_price,
            )

            st.subheader("Current run – country rankings (normalized to base currency)")

            col1, col2 = st.columns(2)

            with col1:
                st.markdown("**Sorted by RAW min price (base currency)**")
                rows = []
                for m in sorted_by_min:
                    rows.append(
                        {
                            "Country code": m.country_code,
                            "Country": m.country_name,
                            f"Min {base_currency}/night": round(m.min_price_per_night, 1),
                            f"Median {base_currency}/night": round(m.median_price_per_night, 1),
                            f"P90 {base_currency}/night": round(m.p90_price_per_night, 1),
                            "Cost index": round(m.cost_index, 2),
                            "Offers (deduped)": m.offer_count,
                            "Median high-rating": (
                                round(m.median_price_high_rating, 1)
                                if m.median_price_high_rating is not None
                                else None
                            ),
                            "Median ≥3★": (
                                round(m.median_price_3plus_stars, 1)
                                if m.median_price_3plus_stars is not None
                                else None
                            ),
                        }
                    )
                st.dataframe(rows, use_container_width=True)

            with col2:
                st.markdown("**Sorted by EFFECTIVE min (price × cost_index^alpha)**")
                rows_eff = []
                for m in sorted_by_effective:
                    rows_eff.append(
                        {
                            "Country code": m.country_code,
                            "Country": m.country_name,
                            "Effective min": round(m.effective_min_price, 1),
                            f"Raw min {base_currency}/night": round(m.min_price_per_night, 1),
                            "Cost index": round(m.cost_index, 2),
                        }
                    )
                st.dataframe(rows_eff, use_container_width=True)

            st.subheader("Sample cheapest offers per country (current run, post-dedupe)")

            selected_country = st.selectbox(
                "Choose a country to inspect",
                options=[m.country_code for m in sorted_by_effective],
                format_func=lambda code: next(
                    (m.country_name for m in sorted_by_effective if m.country_code == code),
                    code,
                ),
            )

            selected = metrics_by_country[selected_country]
            top_offers = sorted(selected.offers, key=lambda o: o.effective_score or 1e9)[:20]

            offer_rows = []
            for o in top_offers:
                offer_rows.append(
                    {
                        "Vendor": o.vendor,
                        "City": o.city_name,
                        "Hotel": o.hotel_name,
                        "Price (vendor currency)/night": round(o.price_per_night, 1),
                        "Currency": o.currency,
                        "Rating": o.rating,
                        "Stars": o.stars,
                        "Effective score": round(o.effective_score or o.price_per_night, 1),
                    }
                )
            st.dataframe(offer_rows, use_container_width=True)

    st.subheader("Historical mispricing vs cost index (median / cost_index)")

    if not historical_summary:
        st.info("No historical data yet. Run at least one scan with logging enabled.")
        return

    cheaper = sorted(historical_summary, key=lambda r: r["normalized_median"])
    more_expensive = sorted(historical_summary, key=lambda r: r["normalized_median"], reverse=True)

    col_left, col_right = st.columns(2)

    with col_left:
        st.markdown("**Consistently cheaper than index** (lowest normalized median first)")
        rows = []
        for r in cheaper:
            rows.append(
                {
                    "Country": f"{r['country_code']} {r['country_name']}",
                    "Cost index": round(r["cost_index"], 2),
                    "Avg median €/night": round(r["avg_median_price"], 1),
                    "Normalized median (median / cost_index)": round(r["normalized_median"], 1),
                }
            )
        st.dataframe(rows, use_container_width=True)

    with col_right:
        st.markdown("**Consistently pricier than index** (highest normalized median first)")
        rows2 = []
        for r in more_expensive:
            rows2.append(
                {
                    "Country": f"{r['country_code']} {r['country_name']}",
                    "Cost index": round(r["cost_index"], 2),
                    "Avg median €/night": round(r["avg_median_price"], 1),
                    "Normalized median (median / cost_index)": round(r["normalized_median"], 1),
                }
            )
        st.dataframe(rows2, use_container_width=True)


if __name__ == "__main__":
    main()
