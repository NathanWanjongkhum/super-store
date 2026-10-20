"""KPI values, targets and breakdowns for a period, without any Streamlit dependency."""

from dataclasses import dataclass

import pandas as pd

from super_store import metrics
from super_store.config import Targets


@dataclass(frozen=True)
class Kpi:
    name: str
    value: float
    last_year: float
    target: float | None
    higher_is_better: bool
    kind: str  # "money" or "pct"
    trend: list[float]  # last 12 months, for the sparkline
    drill: str  # drill-down dimension

    @property
    def status(self) -> metrics.Status:
        return metrics.status(self.value, self.target, self.higher_is_better)


def customer_health(df: pd.DataFrame, as_of: pd.Period) -> pd.DataFrame:
    """Retention and revenue at risk for the 12 months ending at `as_of`."""
    rows = {}
    for month in pd.period_range(as_of - 11, as_of, freq="M"):
        end = month.end_time.normalize()
        rows[month] = {
            "Customer Retention": metrics.retention(df, end),
            "Revenue at Risk": metrics.revenue_at_risk(metrics.rfm(df, end)),
        }
    return pd.DataFrame.from_dict(rows, orient="index")


def build_kpis(df: pd.DataFrame, as_of: pd.Period, period: str, targets: Targets,
               health: pd.DataFrame | None = None, health_ly: pd.DataFrame | None = None) -> list[Kpi]:
    """The six headline KPIs; pass `health`/`health_ly` to reuse cached customer_health()."""
    w = metrics.period_window(as_of, period)
    current = metrics.sales_kpis(metrics.in_window(df, w))
    last_year = metrics.sales_kpis(metrics.in_window(df, w.prior_year()))
    months = metrics.monthly(df).loc[as_of - 11:as_of]
    health = customer_health(df, as_of) if health is None else health
    health_ly = customer_health(df, as_of - 12) if health_ly is None else health_ly  # ty: ignore[invalid-argument-type]  # stubs: Period | offset
    growth = 1 + targets.sales_growth / 100

    def money(name: str, drill: str) -> Kpi:
        return Kpi(name, current[name], last_year[name], last_year[name] * growth,
                   True, "money", months[name].tolist(), drill)

    return [
        money("Sales", "Market"),
        money("Profit", "Category"),
        Kpi("Profit Margin", current["Profit Margin"], last_year["Profit Margin"],
            targets.profit_margin, True, "pct", months["Profit Margin"].tolist(), "Sub-Category"),
        Kpi("Avg Discount", current["Avg Discount"], last_year["Avg Discount"],
            targets.max_discount, False, "pct", months["Avg Discount"].tolist(), "Sub-Category"),
        Kpi("Customer Retention", health["Customer Retention"].iloc[-1],
            health_ly["Customer Retention"].iloc[-1], targets.retention,
            True, "pct", health["Customer Retention"].tolist(), "RFM Segment"),
        Kpi("Revenue at Risk", health["Revenue at Risk"].iloc[-1],
            health_ly["Revenue at Risk"].iloc[-1], targets.max_revenue_at_risk,
            False, "pct", health["Revenue at Risk"].tolist(), "RFM Segment"),
    ]


def breakdown(df: pd.DataFrame, dim: str, w: metrics.Window, margin_target: float) -> pd.DataFrame:
    """Sales, growth, profit, margin and discount per group for the window vs last year."""
    def agg(frame: pd.DataFrame) -> pd.DataFrame:
        return frame.groupby(dim).agg(Sales=("Sales", "sum"), Profit=("Profit", "sum"),
                                      Discount=("Discount", "mean"))

    current = agg(metrics.in_window(df, w))
    last_year = agg(metrics.in_window(df, w.prior_year()))
    out = current[["Sales"]].assign(**{
        "% of Sales": current.Sales / current.Sales.sum() * 100,
        "Growth %": (current.Sales / last_year.Sales.reindex(current.index) - 1) * 100,
        "Profit": current.Profit,
        "Profit Margin": current.Profit / current.Sales * 100,
        "Avg Discount": current.Discount * 100,
    })
    out["Status"] = [metrics.status(m, margin_target) for m in out["Profit Margin"]]
    return out.sort_values("Sales", ascending=False)
