from datetime import date
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI
from pydantic import BaseModel, Field
from dotenv import load_dotenv

from hotel_scanner.cli import (
    run_scan,
    load_country_cost_index,
)
from hotel_scanner.storage import get_historical_country_summary


app = FastAPI(title="EU Hotel Scanner API", version="0.9.0")


class ScanRequest(BaseModel):
    checkin: date = Field(..., description="Check-in date (YYYY-MM-DD)")
    checkout: date = Field(..., description="Check-out date (YYYY-MM-DD)")
    min_price: Optional[float] = Field(None, description="Min price per night in vendor currency")
    max_price: Optional[float] = Field(None, description="Max price per night in vendor currency")
    alpha: Optional[float] = Field(
        None,
        description="Override alpha (cost index exponent). If omitted, uses config/scanner.yaml.",
    )
    min_rating: Optional[float] = Field(None, description="Min hotel rating to include")
    min_stars: Optional[int] = Field(None, description="Min star rating to include")
    base_currency: str = Field("EUR", description="Base currency for metrics")
    use_optimizer: bool = Field(
        True,
        description="Whether to use historical optimiser for country choice.",
    )
    optimizer_top_k: Optional[int] = Field(
        10,
        description="Max number of countries to scan; None or 0 means all.",
    )
    optimizer_min_weight: float = Field(
        0.5,
        description="Minimum per-country scan weight after scaling.",
    )
    optimizer_max_weight: float = Field(
        2.0,
        description="Maximum per-country scan weight after scaling.",
    )
    log_results: bool = Field(
        True,
        description="If false, run_id will be -1 and results are not logged.",
    )


class OfferResponse(BaseModel):
    vendor: str
    city: str
    hotel: str
    price_per_night: float
    currency: str
    rating: Optional[float]
    stars: Optional[int]
    deeplink: Optional[str]
    effective_score: Optional[float]


class CountryResponse(BaseModel):
    country_code: str
    country_name: str
    cost_index: float
    min_price_per_night: float
    median_price_per_night: float
    p90_price_per_night: float
    effective_min_price: float
    effective_median_price: float
    offer_count: int
    offers: List[OfferResponse]


class ScanResponse(BaseModel):
    run_id: int
    checkin: date
    checkout: date
    base_currency: str
    alpha: float
    vendors: List[str]
    countries: List[CountryResponse]


@app.on_event("startup")
def startup_event():
    # Load .env for API keys etc.
    load_dotenv()


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/historical-summary")
def historical_summary():
    """Expose the historical mispricing table used by the optimiser."""
    from hotel_scanner.storage import get_connection, DEFAULT_DB_PATH

    conn = get_connection(DEFAULT_DB_PATH)
    summary = get_historical_country_summary(conn)
    return summary


@app.post("/scan", response_model=ScanResponse)
def scan(req: ScanRequest):
    """Run a scan for the given date range and filters.

    This is the HTTP equivalent of the CLI, returning a JSON structure with
    per-country metrics and a few cheapest offers per country.
    """
    root = Path(__file__).resolve().parents[1]

    destinations_file = root / "config" / "destinations.yaml"
    cost_index_file = root / "config" / "country_cost_index.yaml"
    scanner_config_file = root / "config" / "scanner.yaml"
    fx_rates_file = root / "config" / "fx_rates.yaml"
    vendors_file = root / "config" / "vendors.yaml"

    db_path = root / "data" / "hotel_scanner.db"

    top_k = req.optimizer_top_k if (req.use_optimizer and req.optimizer_top_k and req.optimizer_top_k > 0) else None

    # When log_results is False, we still use SQLite for the optimiser, but
    # pretend run_id = -1 for the response.
    use_optimizer = req.use_optimizer

    run_id, ctx = run_scan(
        checkin_str=req.checkin.isoformat(),
        checkout_str=req.checkout.isoformat(),
        min_price=req.min_price,
        max_price=req.max_price,
        alpha_override=req.alpha,
        min_rating_override=req.min_rating,
        min_stars_override=req.min_stars,
        base_currency=req.base_currency,
        destinations_file=destinations_file,
        cost_index_file=cost_index_file,
        scanner_config_file=scanner_config_file,
        fx_rates_file=fx_rates_file,
        vendors_file=vendors_file,
        db_path=db_path,
        use_optimizer=use_optimizer,
        optimizer_top_k=top_k,
        optimizer_min_weight=req.optimizer_min_weight,
        optimizer_max_weight=req.optimizer_max_weight,
    )

    # If user chose not to log, mask run_id in response
    effective_run_id = run_id if req.log_results else -1

    metrics_by_country = ctx["metrics_by_country"]
    scan_cfg = ctx["scan_cfg"]
    base_currency = ctx["base_currency"]
    vendors = ctx["vendors"]
    checkin = ctx["checkin"]
    checkout = ctx["checkout"]

    if run_id == -1 and not metrics_by_country:
        # No data
        return ScanResponse(
            run_id=-1,
            checkin=checkin,
            checkout=checkout,
            base_currency=base_currency,
            alpha=scan_cfg.alpha,
            vendors=[v.name for v in vendors],
            countries=[],
        )

    # Load cost index for the response
    cost_index_by_country = load_country_cost_index(cost_index_file)

    countries: List[CountryResponse] = []
    for code, m in metrics_by_country.items():
        offers_sorted = sorted(m.offers, key=lambda o: o.effective_score or 1e9)[:20]
        offers_resp = [
            OfferResponse(
                vendor=o.vendor,
                city=o.city_name,
                hotel=o.hotel_name,
                price_per_night=o.price_per_night,
                currency=o.currency,
                rating=o.rating,
                stars=o.stars,
                deeplink=o.deeplink,
                effective_score=o.effective_score,
            )
            for o in offers_sorted
        ]
        countries.append(
            CountryResponse(
                country_code=m.country_code,
                country_name=m.country_name,
                cost_index=cost_index_by_country.get(m.country_code, m.cost_index),
                min_price_per_night=m.min_price_per_night,
                median_price_per_night=m.median_price_per_night,
                p90_price_per_night=m.p90_price_per_night,
                effective_min_price=m.effective_min_price,
                effective_median_price=m.effective_median_price,
                offer_count=m.offer_count,
                offers=offers_resp,
            )
        )

    countries.sort(key=lambda c: c.effective_min_price)

    return ScanResponse(
        run_id=effective_run_id,
        checkin=checkin,
        checkout=checkout,
        base_currency=base_currency,
        alpha=scan_cfg.alpha,
        vendors=[v.name for v in vendors],
        countries=countries,
    )


def run():
    """Entry point for `eu-hotel-api` console script."""
    import uvicorn

    uvicorn.run("service.api:app", host="0.0.0.0", port=8000, reload=False)
