from pathlib import Path
from typing import Dict

import yaml


def load_fx_rates(path: Path) -> Dict[str, float]:
    """Load FX table mapping currency -> EUR per 1 unit of that currency.

    Example:
        EUR: 1.0
        USD: 0.92   # 1 USD = 0.92 EUR
    """
    with path.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    rates: Dict[str, float] = {}
    for code, value in raw.items():
        code_u = str(code).upper()
        rates[code_u] = float(value)
    return rates


def convert_amount(
    amount: float,
    from_currency: str,
    to_currency: str,
    fx_rates: Dict[str, float],
) -> float:
    """Convert amount from from_currency to to_currency using fx_rates.

    fx_rates: mapping currency -> EUR per 1 unit.
    Conversion is done via EUR as an intermediate.
    """
    from_cur = from_currency.upper()
    to_cur = to_currency.upper()
    if from_cur == to_cur:
        return amount

    if from_cur not in fx_rates or to_cur not in fx_rates:
        # Fallback: no conversion, treat as already in target
        return amount

    # Convert to EUR, then to target
    eur_amount = amount * fx_rates[from_cur]
    if to_cur == "EUR":
        return eur_amount
    return eur_amount / fx_rates[to_cur]
