"""Action items: what is off track, why it matters, who owns it and when to review it.

Pure functions over KPIs and breakdowns. Text is plain (unescaped `$`); markdown
escaping belongs to the rendering layer.
"""

from dataclasses import dataclass
from typing import cast

import pandas as pd

from super_store import metrics
from super_store.config import Owners, Review, Targets
from super_store.formatting import change, day, fmt
from super_store.kpis import Kpi

ACTION_STATUSES = ("red", "yellow")  # KPI statuses that raise an action item


@dataclass(frozen=True)
class Action:
    status: metrics.Status
    what: str
    why: str
    who: str
    when: str
    impact: float  # estimated dollars, used only for ranking


def next_review(end: pd.Timestamp, review: Review) -> pd.Timestamp:
    """The first review weekday after the window end (weekly cadence)."""
    return end + pd.offsets.Week(weekday=review.weekday_index)


def review_text(end: pd.Timestamp, review: Review) -> str:
    """e.g. "Mon 5 Jan 2015"."""
    return f"{review.weekday[:3]} {day(next_review(end, review))}"


def kpi_action(k: Kpi, kpis: dict[str, Kpi], targets: Targets, owners: Owners, when: str) -> Action:
    sales = kpis["Sales"]
    # Only off-track KPIs get here, and a KPI without a target is always gray
    assert k.target is not None, f"{k.name} has no target"
    gap = k.target - k.value if k.higher_is_better else k.value - k.target
    if k.kind == "money":
        what = f"{k.name} {fmt(k.value, 'money')}, {fmt(gap, 'money')} under target"
    else:
        what = f"{k.name} {k.value:.1f}% vs {k.target:.1f}% {'target' if k.higher_is_better else 'max'}"
    yoy = change(k.value, k.last_year, k.kind)
    trend = "up" if k.value > k.last_year else "down"
    why = {
        "Sales": f"{yoy} YoY vs {targets.sales_growth:+.0f}% plan.",
        "Profit": f"{yoy} YoY, slower than sales ({change(sales.value, sales.last_year, sales.kind)}).",
        "Profit Margin": f"Each point ≈ {fmt(sales.value / 100, 'money')} profit.",
        "Avg Discount": "Heavy discounts drive the loss-making products.",
        "Customer Retention": f"{100 - k.value:.0f}% of last year's customers haven't reordered.",
        "Revenue at Risk": f"Lapsed frequent buyers, {trend} {abs(k.value - k.last_year):.1f} pts YoY.",
    }[k.name]
    impact = {"money": gap, "pct": gap / 100 * sales.value}[k.kind]
    return Action(k.status, what, why, owners.kpi[k.name], when, impact)


def market_action(market: str, row: pd.Series, targets: Targets, owners: Owners, when: str) -> Action:
    uplift = (targets.profit_margin - row["Profit Margin"]) / 100 * row.Sales
    return Action(
        status=row.Status,
        what=f"{market} margin {row['Profit Margin']:.1f}% vs {targets.profit_margin:.1f}% target",
        why=f"{row['% of Sales']:.0f}% of sales; target adds ≈ {fmt(uplift, 'money')} profit.",
        who=owners.for_market(market), when=when, impact=uplift)


def loss_action(sub_category: str, row: pd.Series, category: str, avg_discount: float,
                owners: Owners, when: str) -> Action:
    return Action(
        status="red",
        what=f"{sub_category} lost {fmt(-row.Profit, 'money')} on {fmt(row.Sales, 'money')} sales",
        why=f"Avg discount {row['Avg Discount']:.0f}% vs {avg_discount:.0f}% overall.",
        who=owners.for_category(category), when=when, impact=-row.Profit)


def rank(actions: list[Action]) -> list[Action]:
    """Red items first, then by estimated impact, largest first."""
    return sorted(actions, key=lambda a: (a.status != "red", -a.impact))


def build_actions(kpis: list[Kpi], markets: pd.DataFrame, sub_categories: pd.DataFrame,
                  category_of: pd.Series, targets: Targets, owners: Owners, when: str) -> list[Action]:
    """Ranked action items for off-track KPIs, red markets and loss-making sub-categories.

    `markets`/`sub_categories` are kpis.breakdown() tables; `category_of` maps
    sub-category to category.
    """
    by_name = {k.name: k for k in kpis}
    actions = [kpi_action(k, by_name, targets, owners, when) for k in kpis
               if k.status in ACTION_STATUSES]
    actions += [market_action(str(m), row, targets, owners, when) for m, row in markets.iterrows()
                if row.Status == "red"]
    actions += [loss_action(str(sc), row, category_of[sc], by_name["Avg Discount"].value, owners, when)
                for sc, row in sub_categories.iterrows() if row.Profit < 0]
    return rank(actions)


def category_map(df: pd.DataFrame) -> pd.Series:
    return cast(pd.Series, df.groupby("Sub-Category")["Category"].first())
