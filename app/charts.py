"""Altair charts for the dashboard. Bars and lines only: no pie charts."""

import altair as alt
import pandas as pd

from common import STATUS_COLORS, STATUS_LABELS

HEIGHT = 215
BLUE = "#1f77b4"
status_scale = alt.Scale(domain=list(STATUS_COLORS), range=list(STATUS_COLORS.values()))


def sales_vs_last_year(months: pd.DataFrame, months_ly: pd.DataFrame) -> alt.Chart:
    """Monthly sales for the last 12 months, with the same months last year dashed."""
    data = pd.concat([
        pd.DataFrame({"Month": pd.PeriodIndex(months.index).to_timestamp(), "Sales": months.Sales.values,
                      "Series": "This year"}),
        pd.DataFrame({"Month": pd.PeriodIndex(months.index).to_timestamp(), "Sales": months_ly.Sales.values,
                      "Series": "Last year"}),
    ])
    return alt.Chart(data, height=HEIGHT).mark_line(point=alt.OverlayMarkDef(size=64), strokeWidth=2).encode(
        x=alt.X("Month:T", title=None, axis=alt.Axis(format="%b")),
        y=alt.Y("Sales:Q", title=None, axis=alt.Axis(format="$,.2s")),
        color=alt.Color("Series:N", legend=None,
                        scale=alt.Scale(domain=["This year", "Last year"], range=[BLUE, "#9e9e9e"])),
        strokeDash=alt.StrokeDash("Series:N", legend=None,
                                  scale=alt.Scale(domain=["This year", "Last year"], range=[[1, 0], [4, 3]])),
        tooltip=[alt.Tooltip("Month:T", format="%b %Y"), "Series:N", alt.Tooltip("Sales:Q", format="$,.0f")],
    )


def margin_trend(margin: pd.Series, target: float) -> alt.Chart:
    """Rolling profit margin by month against the target."""
    data = pd.DataFrame({"Month": pd.PeriodIndex(margin.index).to_timestamp(), "Margin": margin.values})
    line = alt.Chart(data).mark_line(point=alt.OverlayMarkDef(size=64), strokeWidth=2, color=BLUE).encode(
        x=alt.X("Month:T", title=None, axis=alt.Axis(format="%b")),
        y=alt.Y("Margin:Q", title=None, scale=alt.Scale(zero=False),
                axis=alt.Axis(format=".0f", labelExpr="datum.label + '%'", tickMinStep=1)),
        tooltip=[alt.Tooltip("Month:T", format="%b %Y"), alt.Tooltip("Margin:Q", format=".1f", title="Margin %")],
    )
    return (line + target_rule(target, "y")).properties(height=HEIGHT)


def margin_by(breakdown: pd.DataFrame, dim: str, target: float, step: int = 24) -> alt.Chart:
    """Horizontal profit-margin bars per group, colored by status against the target."""
    data = breakdown.reset_index()
    data["Label"] = data["Status"].map(STATUS_LABELS)
    bars = alt.Chart(data).mark_bar(cornerRadiusEnd=4).encode(
        y=alt.Y(f"{dim}:N", title=None, sort=alt.SortField("Sales", order="descending"),
                axis=alt.Axis(labelOverlap=False)),
        x=alt.X("Profit Margin:Q", title=None, axis=alt.Axis(labelExpr="datum.label + '%'")),
        color=alt.Color("Status:N", scale=status_scale, legend=None),
        tooltip=[f"{dim}:N", alt.Tooltip("Sales:Q", format="$,.0f"),
                 alt.Tooltip("Profit Margin:Q", format=".1f", title="Margin %"),
                 alt.Tooltip("Label:N", title="Status")],
    )
    return (bars + target_rule(target, "x")).properties(height=alt.Step(step))


def segment_sales(segments: pd.DataFrame, at_risk: list[str], step: int = 17) -> alt.Chart:
    """Share of lifetime sales by RFM segment; the at-risk segments are red."""
    data = segments.reset_index()
    data["Status"] = data["Segment"].isin(at_risk).map({True: "red", False: "gray"})
    return alt.Chart(data, height=alt.Step(step)).mark_bar(cornerRadiusEnd=4).encode(
        y=alt.Y("Segment:N", title=None, sort="-x", axis=alt.Axis(labelOverlap=False)),
        x=alt.X("% Sales:Q", title=None, axis=alt.Axis(labelExpr="datum.label + '%'")),
        color=alt.Color("Status:N", scale=status_scale, legend=None),
        tooltip=["Segment:N", "Customers:Q", alt.Tooltip("% Sales:Q", format=".1f")],
    )


def profit_gap(breakdown: pd.DataFrame, dim: str, target: float, step: int = 24) -> alt.Chart:
    """Diverging bars: profit above or below what the margin target would earn on each group's sales."""
    data = breakdown.reset_index()
    data["Gap"] = (data["Profit Margin"] - target) / 100 * data.Sales
    data["Label"] = data["Status"].map(STATUS_LABELS)
    bars = alt.Chart(data).mark_bar(cornerRadiusEnd=4).encode(
        y=alt.Y(f"{dim}:N", title=None, sort="-x", axis=alt.Axis(labelOverlap=False)),
        x=alt.X("Gap:Q", title=None, axis=alt.Axis(format="$,.2s")),
        color=alt.Color("Status:N", scale=status_scale, legend=None),
        tooltip=[f"{dim}:N", alt.Tooltip("Gap:Q", format="$,.0f", title="Profit vs target"),
                 alt.Tooltip("Profit Margin:Q", format=".1f", title="Margin %"),
                 alt.Tooltip("Sales:Q", format="$,.0f"), alt.Tooltip("Label:N", title="Status")],
    )
    zero = alt.Chart(pd.DataFrame({"x": [0]})).mark_rule(color="#9e9e9e").encode(x="x:Q")
    return (bars + zero).properties(height=alt.Step(step))


def discount_vs_margin(breakdown: pd.DataFrame, dim: str, target: float, n: int = 8) -> alt.HConcatChart:
    """Lowest-margin groups: average discount and margin side by side (two charts, not a dual axis)."""
    data = breakdown.nsmallest(n, "Profit Margin").reset_index()
    data["Label"] = data["Status"].map(STATUS_LABELS)
    order = data[dim].tolist()
    tooltip = [f"{dim}:N", alt.Tooltip("Avg Discount:Q", format=".1f", title="Avg discount %"),
               alt.Tooltip("Profit Margin:Q", format=".1f", title="Margin %"), alt.Tooltip("Label:N", title="Status")]
    pct = alt.Axis(labelExpr="datum.label + '%'", tickCount=3)
    base = alt.Chart(data, width=82, height=alt.Step(22))
    discount = base.mark_bar(cornerRadiusEnd=4, color=BLUE).encode(
        y=alt.Y(f"{dim}:N", title=None, sort=order, axis=alt.Axis(labelOverlap=False)),
        x=alt.X("Avg Discount:Q", title="Discount", axis=pct),
        tooltip=tooltip,
    )
    margin = base.mark_bar(cornerRadiusEnd=4).encode(
        y=alt.Y(f"{dim}:N", title=None, sort=order, axis=None),
        x=alt.X("Profit Margin:Q", title="Margin", axis=pct),
        color=alt.Color("Status:N", scale=status_scale, legend=None),
        tooltip=tooltip,
    )
    return alt.hconcat(discount, margin + target_rule(target, "x"), spacing=8)


def target_rule(target: float, axis: str) -> alt.Chart:
    rule = alt.Chart(pd.DataFrame({"Target": [target]})).mark_rule(strokeDash=[4, 3], color="#c62828")
    return rule.encode(**{axis: "Target:Q"}, tooltip=[alt.Tooltip("Target:Q", format=".1f")])
