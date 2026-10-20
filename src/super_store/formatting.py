"""Plain-text number and date formatting shared by the dashboard and the digest."""

import pandas as pd

SHORT_PERIOD = {"Month to date": "MTD", "Quarter to date": "QTD", "Year to date": "YTD",
                "Trailing 12 months": "T12M"}


def fmt(value: float, kind: str) -> str:
    """e.g. "11.7%" for kind "pct"; "$4.30M", "$504.2K", "$950" for kind "money"."""
    if kind == "pct":
        return f"{value:.1f}%"
    for divisor, suffix, decimals in ((1e6, "M", 2), (1e3, "K", 1)):
        if abs(value) >= divisor:
            return f"${value / divisor:.{decimals}f}{suffix}"
    return f"${value:,.0f}"


def change(value: float, last_year: float, kind: str) -> str:
    """Year-over-year change: points for percentages, % for money; "n/a" without a prior value."""
    if pd.isna(value) or pd.isna(last_year) or (kind == "money" and last_year == 0):
        return "n/a"
    if kind == "pct":
        return f"{value - last_year:+.1f} pts"
    return f"{(value / last_year - 1) * 100:+.1f}%"


def day(d: pd.Timestamp) -> str:
    return f"{d.day} {d:%b %Y}"


def period_caption(start: pd.Timestamp, end: pd.Timestamp, period: str) -> str:
    """e.g. "YTD · 1 Jan – 31 Dec 2014 vs last year"."""
    first = f"{start.day} {start:%b}" if start.year == end.year else day(start)
    return f"{SHORT_PERIOD[period]} · {first} – {day(end)} vs last year"
