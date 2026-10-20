"""KPI, RFM and status logic for the executive summary dashboard."""

from dataclasses import dataclass
from typing import Literal

import pandas as pd

PERIODS = ["Month to date", "Quarter to date", "Year to date", "Trailing 12 months"]

# Standard RFM segment map on the R and F scores (same as notebooks/01-eda.ipynb)
SEGMENT_MAP = {
    r"[1-2][1-2]": "Hibernating",
    r"[1-2][3-4]": "At Risk",
    r"[1-2]5": "Can't Lose",
    r"3[1-2]": "About to Sleep",
    r"33": "Need Attention",
    r"[3-4][4-5]": "Loyal Customers",
    r"41": "Promising",
    r"51": "New Customers",
    r"[4-5][2-3]": "Potential Loyalists",
    r"5[4-5]": "Champions",
}
AT_RISK_SEGMENTS = ["At Risk", "Can't Lose"]
Status = Literal["green", "yellow", "red", "gray"]


@dataclass(frozen=True)
class Window:
    start: pd.Timestamp
    end: pd.Timestamp

    def prior_year(self) -> "Window":
        return Window(self.start - pd.DateOffset(years=1), self.end - pd.DateOffset(years=1))


def period_window(as_of: pd.Period, period: str) -> Window:
    """Date window for a period ending with the as-of month."""
    starts = {
        "Month to date": as_of.start_time,
        "Quarter to date": as_of.asfreq("Q").start_time,
        "Year to date": pd.Period(as_of.year, "Y").start_time,  # ty: ignore[unresolved-attribute]  # stubs: Period | NaT
        "Trailing 12 months": (as_of - 11).start_time,  # ty: ignore[unresolved-attribute]  # stubs: Period | offset
    }
    return Window(starts[period], as_of.end_time.normalize())


def in_window(df: pd.DataFrame, w: Window) -> pd.DataFrame:
    return df[df["Order Week"].between(w.start, w.end)]


def sales_kpis(df: pd.DataFrame) -> dict[str, float]:
    sales = df["Sales"].sum()
    profit = df["Profit"].sum()
    return {
        "Sales": sales,
        "Profit": profit,
        "Profit Margin": profit / sales * 100 if sales else float("nan"),
        "Avg Discount": df["Discount"].mean() * 100,
    }


def retention(df: pd.DataFrame, end: pd.Timestamp) -> float:
    """% of customers who bought in the 12 months before last year and bought again in the last 12 months.

    NaN when the prior window starts before the data does: a partial year would skew it.
    """
    year_ago = end - pd.DateOffset(years=1)
    two_years_ago = year_ago - pd.DateOffset(years=1)
    if df.empty or two_years_ago + pd.Timedelta(days=1) < df["Order Week"].min():
        return float("nan")
    prior = set(in_window(df, Window(two_years_ago + pd.Timedelta(days=1), year_ago))["Customer ID"])  # ty: ignore[invalid-argument-type]  # stubs: Timestamp | NaT
    current = set(in_window(df, Window(year_ago + pd.Timedelta(days=1), end))["Customer ID"])  # ty: ignore[invalid-argument-type]  # stubs: Timestamp | NaT
    return len(prior & current) / len(prior) * 100 if prior else float("nan")


def rfm(df: pd.DataFrame, end: pd.Timestamp) -> pd.DataFrame:
    """RFM scores and segments for every customer, using orders up to `end`.

    Customer ID is per market, so each ID is its own customer. Scores are 1-5
    quintiles (5 = best); ranking first breaks ties so every bin is equal-sized.
    """
    history = df[df["Order Week"] <= end]
    snapshot = end + pd.Timedelta(days=1)
    table = history.groupby("Customer ID").agg(
        Recency=("Order Week", lambda d: (snapshot - d.max()).days),
        Frequency=("Order ID", "nunique"),
        Monetary=("Sales", "sum"),
    )
    table["R"] = pd.qcut(table.Recency.rank(method="first"), 5, labels=[5, 4, 3, 2, 1]).astype(int)
    table["F"] = pd.qcut(table.Frequency.rank(method="first"), 5, labels=[1, 2, 3, 4, 5]).astype(int)
    table["M"] = pd.qcut(table.Monetary.rank(method="first"), 5, labels=[1, 2, 3, 4, 5]).astype(int)
    table["Segment"] = (table.R.astype(str) + table.F.astype(str)).replace(SEGMENT_MAP, regex=True)
    return table


def revenue_at_risk(table: pd.DataFrame) -> float:
    """% of customers' lifetime sales held by the At Risk and Can't Lose segments."""
    return table.Monetary[table.Segment.isin(AT_RISK_SEGMENTS)].sum() / table.Monetary.sum() * 100


def monthly(df: pd.DataFrame) -> pd.DataFrame:
    """Sales, profit, margin and discount per calendar month."""
    out = df.groupby(df["Order Week"].dt.to_period("M")).agg(
        Sales=("Sales", "sum"), Profit=("Profit", "sum"), Discount=("Discount", "mean"))
    out["Profit Margin"] = out.Profit / out.Sales * 100
    out["Avg Discount"] = out.pop("Discount") * 100
    return out


def rolling_margin(months: pd.DataFrame, window: int = 3) -> pd.Series:
    """Profit margin over a rolling window of months (summed profit / summed sales)."""
    return months.Profit.rolling(window).sum() / months.Sales.rolling(window).sum() * 100


def status(actual: float, target: float | None, higher_is_better: bool = True) -> Status:
    """green = on target, yellow = within 10% of target, red = more than 10% off, gray = no target."""
    if target is None or pd.isna(target) or pd.isna(actual) or actual == 0:
        return "gray"
    ratio = actual / target if higher_is_better else target / actual
    if ratio >= 1:
        return "green"
    return "yellow" if ratio >= 0.9 else "red"
