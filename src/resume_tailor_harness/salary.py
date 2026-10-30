"""Comparable annual USD salaries; source amounts remain available for display."""

# Estimates assume 40 paid hours/week and 52 weeks/year. Unknown periods and
# unconverted currencies stay unknown rather than entering USD comparisons.
ANNUAL_FACTORS = {"year": 1, "month": 12, "week": 52, "day": 260, "hour": 2080}


def annual_usd_amount(
    amount: float | None, currency: str | None, period: str | None
) -> float | None:
    if amount is None or (currency or "USD").strip().upper() != "USD":
        return None
    factor = ANNUAL_FACTORS.get((period or "year").strip().lower())
    return amount * factor if factor is not None else None
