import datetime
from pathlib import Path
from typing import Dict, List

import streamlit as st
import yaml

from hotel_scanner.aggregator import ScanConfig, scan_destinations
from hotel_scanner.clients.mock_vendor import MockVendorClient
from hotel_scanner.models import Destination


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
        page_title="EU Hotel Scanner – v0.3",
        layout="wide",
    )

    st.title("EU Hotel Scanner – v0.3")
    st.caption(
        "Mock-powered prototype. Uses a country cost index + alpha to bias rankings "
        "towards structurally cheaper countries."
    )

    # Sidebar config
    with st.sidebar:
        st.header("Scan parameters")

        today = datetime.date.today()
        default_checkin = today + datetime.timedelta(days=30)
        default_checkout = default_checkin + datetime.timedelta(days=5)

        checkin = st.date_input("Check-in", value=default_checkin)
        checkout = st.date_input("Check-out", value=default_checkout)

        min_price = st.number_input(
            "Min price per night (EUR)",
            value=0.0,
            min_value=0.0,
            step=5.0,
        )
        max_price = st.number_input(
            "Max price per night (EUR)",
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

        run_btn = st.button("Run scan")

    # Load config / data once per run
    destinations = load_destinations(CONFIG_DIR / "destinations.yaml")
    cost_index_by_country = load_country_cost_index(CONFIG_DIR / "country_cost_index.yaml")

    if not run_btn:
        st.info("Adjust the parameters in the sidebar and click **Run scan**.")
        st.subheader("Current country cost index")
        idx_rows = []
        for d in sorted({(d.country_code, d.country_name) for d in destinations}):
            code, name = d
            idx = cost_index_by_country.get(code, 1.0)
            idx_rows.append({"Country code": code, "Country": name, "Cost index": idx})
        st.table(idx_rows)
        return

    if checkin >= checkout:
        st.error("Check-out date must be after check-in.")
        return

    # For interactive UI, we use very small delays
    scan_cfg = ScanConfig(
        scan_mode=scan_mode,
        max_cost_index_for_scan=max_cost_idx,
        base_cities_per_country=base_cities,
        base_offers_per_destination=base_offers,
        delay_seconds=(0.05, 0.15),
        alpha=alpha,
    )

    vendors = [
        MockVendorClient(),
    ]

    with st.spinner("Running scan (mock vendor, synthetic prices)..."):
        metrics_by_country = scan_destinations(
            destinations=destinations,
            vendors=vendors,
            checkin=checkin,
            checkout=checkout,
            min_price=min_price,
            max_price=max_price,
            cost_index_by_country=cost_index_by_country,
            scan_config=scan_cfg,
        )

    if not metrics_by_country:
        st.warning("No offers found with the current filters (mock world).")
        return

    # Prepare tables
    sorted_by_min = sorted(
        metrics_by_country.values(),
        key=lambda m: m.min_price_per_night,
    )
    sorted_by_effective = sorted(
        metrics_by_country.values(),
        key=lambda m: m.effective_min_price,
    )

    st.subheader("Country rankings")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("**Sorted by RAW min EUR/night**")
        rows = []
        for m in sorted_by_min:
            rows.append(
                {
                    "Country code": m.country_code,
                    "Country": m.country_name,
                    "Min €/night": round(m.min_price_per_night, 1),
                    "Median €/night": round(m.median_price_per_night, 1),
                    "P90 €/night": round(m.p90_price_per_night, 1),
                    "Cost index": round(m.cost_index, 2),
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
                    "Raw min €/night": round(m.min_price_per_night, 1),
                    "Cost index": round(m.cost_index, 2),
                }
            )
        st.dataframe(rows_eff, use_container_width=True)

    # Optional: show cheap sample per selected country
    st.subheader("Sample cheapest offers per country (mock)")

    selected_country = st.selectbox(
        "Choose a country to inspect",
        options=[m.country_code for m in sorted_by_effective],
        format_func=lambda code: next(
            (m.country_name for m in sorted_by_effective if m.country_code == code),
            code,
        ),
    )

    selected = metrics_by_country[selected_country]
    top_offers = sorted(selected.offers, key=lambda o: o.price_per_night)[:20]

    offer_rows = []
    for o in top_offers:
        offer_rows.append(
            {
                "Vendor": o.vendor,
                "City": o.city_name,
                "Hotel": o.hotel_name,
                "Price €/night": round(o.price_per_night, 1),
                "Rating": o.rating,
                "Stars": o.stars,
                "Effective score": round(o.effective_score or o.price_per_night, 1),
            }
        )
    st.dataframe(offer_rows, use_container_width=True)


if __name__ == "__main__":
    main()
