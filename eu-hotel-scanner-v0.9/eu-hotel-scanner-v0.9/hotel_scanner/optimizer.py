from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass
class CountryScanWeight:
    country_code: str
    country_name: str
    cost_index: float
    normalized_median: Optional[float]
    raw_weight: float
    scaled_weight: float


def build_country_scan_weights(
    cost_index_by_country: Dict[str, float],
    historical_summary: List[dict],
    top_k: Optional[int] = None,
    min_weight: float = 0.5,
    max_weight: float = 2.0,
) -> Dict[str, float]:
    """Build per-country scan weights from cost index and historical mispricing.

    Heuristic:
    - Start with prior cheapness ~ 1 / cost_index.
    - If we have normalized_median (median_price / cost_index) from history,
      adjust by 1 / normalized_median.
      => raw_weight ~ 1 / (cost_index * normalized_median).
    - If no history, fall back to 1 / cost_index.

    Then:
    - Optionally keep only top_k countries (others get weight 0).
    - Scale non-zero weights into [min_weight, max_weight] around the median.

    Returned dict maps country_code -> scaled_weight (0 means "do not scan").
    """
    eps = 1e-6
    if not cost_index_by_country:
        return {}

    summary_by_code = {row["country_code"]: row for row in (historical_summary or [])}
    entries: List[CountryScanWeight] = []

    for code, ci in cost_index_by_country.items():
        ci = float(ci)
        hist = summary_by_code.get(code)
        normalized_median = None
        if hist is not None:
            try:
                normalized_median = float(hist.get("normalized_median"))
            except (TypeError, ValueError):
                normalized_median = None

        base = 1.0 / max(ci, eps)
        if normalized_median is not None and normalized_median > 0:
            raw = base * (1.0 / max(normalized_median, eps))
        else:
            raw = base

        entries.append(
            CountryScanWeight(
                country_code=code,
                country_name=str(hist["country_name"]) if hist and "country_name" in hist else code,
                cost_index=ci,
                normalized_median=normalized_median,
                raw_weight=raw,
                scaled_weight=1.0,
            )
        )

    # Sort by raw_weight (higher = more attractive)
    entries.sort(key=lambda e: e.raw_weight, reverse=True)

    # Apply top_k: weights beyond top_k become 0
    if top_k is not None and top_k > 0:
        non_zero_entries = entries[:top_k]
        zero_entries = entries[top_k:]
    else:
        non_zero_entries = entries
        zero_entries = []

    raw_non_zero = [e.raw_weight for e in non_zero_entries if e.raw_weight > 0]
    if not raw_non_zero:
        weights = {e.country_code: 0.0 for e in zero_entries}
        weights.update({e.country_code: 1.0 for e in non_zero_entries})
        return weights

    raw_sorted = sorted(raw_non_zero)
    median_idx = len(raw_sorted) // 2
    median_val = raw_sorted[median_idx] if raw_sorted else 1.0
    if median_val <= 0:
        median_val = max(raw_non_zero)

    for e in non_zero_entries:
        rel = e.raw_weight / median_val if median_val > 0 else 1.0
        e.scaled_weight = max(min_weight, min(max_weight, rel))

    for e in zero_entries:
        e.scaled_weight = 0.0

    weights: Dict[str, float] = {}
    for e in entries:
        weights[e.country_code] = float(e.scaled_weight)
    return weights


def summarize_country_weights(
    cost_index_by_country: Dict[str, float],
    historical_summary: List[dict],
    weights: Dict[str, float],
    country_name_by_code: Optional[Dict[str, str]] = None,
) -> List[dict]:
    """Return a tabular view of the scan plan for UI/CLI introspection."""
    summary_by_code = {row["country_code"]: row for row in (historical_summary or [])}
    rows: List[dict] = []

    for code, ci in cost_index_by_country.items():
        w = float(weights.get(code, 1.0)) if weights is not None else 1.0
        hist = summary_by_code.get(code)
        avg_median = hist.get("avg_median_price") if hist else None
        normalized_median = hist.get("normalized_median") if hist else None
        name = None
        if country_name_by_code is not None:
            name = country_name_by_code.get(code)
        if not name and hist:
            name = hist.get("country_name", code)
        if not name:
            name = code

        rows.append(
            {
                "Country code": code,
                "Country": name,
                "Cost index": float(ci),
                "Avg median €/night (hist)": float(avg_median) if avg_median is not None else None,
                "Normalized median (hist)": float(normalized_median) if normalized_median is not None else None,
                "Scan weight": round(w, 2),
            }
        )

    rows.sort(key=lambda r: r["Scan weight"], reverse=True)
    return rows
