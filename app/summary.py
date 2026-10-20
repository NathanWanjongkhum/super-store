"""Executive summary: KPI cards, trend charts, then action items (inverted pyramid)."""

import pandas as pd
import streamlit as st

import charts
from common import CONFIG, SHORT_PERIOD, STATUS_LABELS, Kpi, breakdown, data, fmt, kpis, period_caption, targets, window
from super_store import actions as action_items
from super_store import metrics
from super_store.formatting import change as yoy_change

STATUS_ICONS = {"green": ":material/check_circle:", "yellow": ":material/warning:",
                "red": ":material/error:", "gray": ":material/remove:"}

s = st.session_state
df = data()
w = window()
all_kpis = kpis()

# Customer KPIs ignore the period selector: retention compares two 12-month windows,
# revenue at risk scores all order history up to the as-of date
KPI_HELP = {
    "Customer Retention": "Share of customers from the prior 12 months who ordered again in the last 12.",
    "Revenue at Risk": "Share of lifetime sales from At Risk and Can't Lose RFM segments.",
}


st.header("Executive Summary")
st.caption(period_caption(w))


# --- Top: KPI cards ---------------------------------------------------------

def change(k: Kpi) -> str | None:
    # None hides the delta, e.g. retention a year before the data has two full years
    text = yoy_change(k.value, k.last_year, k.kind)
    return None if text == "n/a" else text


def target_text(k: Kpi) -> str:
    """Compact target, e.g. "≥ 80%" or "≤ $4.26M", so it fits beside the status badge."""
    if k.target is None:
        return "No target"
    value = fmt(k.target, k.kind)
    if k.kind == "pct" and k.target == int(k.target):
        value = f"{k.target:.0f}%"
    return f"{'≥' if k.higher_is_better else '≤'} {value}"


for col, k in zip(st.columns(len(all_kpis)), all_kpis, strict=True):
    # Months without enough history (NaN) are left out of the sparkline
    trend = [v for v in k.trend if pd.notna(v)]
    with col.container(border=True, height="stretch"):
        st.metric(k.name, fmt(k.value, k.kind), change(k), help=KPI_HELP.get(k.name),
                  delta_color="normal" if k.higher_is_better else "inverse", delta_description="YoY",
                  chart_data=trend if len(trend) > 1 else None, chart_type="line")
        # Status and target share a line; wraps only if the card is too narrow
        with st.container(horizontal=True, vertical_alignment="center", gap="xsmall"):
            st.badge(STATUS_LABELS[k.status], icon=STATUS_ICONS[k.status], color=k.status)
            st.caption(target_text(k), width="content")
        st.page_link("drilldown.py", label=f"By {k.drill}", icon=":material/arrow_forward:",
                     query_params={"by": k.drill})


# --- Middle: trends ---------------------------------------------------------

months = metrics.monthly(df)
last12 = months.loc[s.as_of - 11:s.as_of]
last12_ly = months.loc[s.as_of - 23:s.as_of - 12]
markets = breakdown(df, "Market", w, s.t_margin)
sub_categories = breakdown(df, "Sub-Category", w, s.t_margin)
margin_3m = metrics.rolling_margin(months).loc[s.as_of - 11:s.as_of]

sales_col, margin_col, market_col, health_col = st.columns(4)
with sales_col.container(border=True, height="stretch"):
    st.markdown("**Monthly sales**", help="Last 12 months. Dashed gray line = same months last year.")
    st.altair_chart(charts.sales_vs_last_year(last12, last12_ly), alt="Monthly sales vs last year")
with margin_col.container(border=True, height="stretch"):
    st.markdown("**Margin, 3-month rolling**",
                help="Profit margin over the trailing 3 months, last 12 months. Dashed red line = target.")
    st.altair_chart(charts.margin_trend(margin_3m, s.t_margin), alt="Rolling 3-month profit margin vs target")
with market_col.container(border=True, height="stretch"):
    st.markdown(f"**Profit gap by market**, {SHORT_PERIOD[s.period]}",
                help="Profit above or below what the margin target would earn on each market's sales.")
    st.altair_chart(charts.profit_gap(markets, "Market", s.t_margin), alt="Profit vs margin target by market")
with health_col.container(border=True, height="stretch"):
    st.markdown(f"**Discount vs margin**, {SHORT_PERIOD[s.period]}",
                help="The 8 lowest-margin sub-categories: average discount (left) and profit margin "
                     "(right; dashed red line = target).")
    st.altair_chart(charts.discount_vs_margin(sub_categories, "Sub-Category", s.t_margin),
                    alt="Average discount and profit margin for the lowest-margin sub-categories")


# --- Bottom: action items ---------------------------------------------------
# Each item: what is off track, why it matters, who owns it, when to check in.
# Rules live in super_store.actions; targets, owners and cadence in config/targets.toml.

actions = action_items.build_actions(
    all_kpis, markets, sub_categories, action_items.category_map(df), targets(),
    CONFIG.owners, action_items.review_text(w.end, CONFIG.review))


def show(action: action_items.Action) -> None:
    # One line per item; fixed column ratios keep who/when aligned across rows
    status_col, what_col, who_col, when_col = st.columns([1.3, 7, 2.4, 1.6], vertical_alignment="center")
    status_col.badge(STATUS_LABELS[action.status], icon=STATUS_ICONS[action.status],
                     color=action.status)
    # Escape $ so markdown doesn't read "$30K ... $243K" as a LaTeX formula
    what, why = (text.replace("$", r"\$") for text in (action.what, action.why))
    what_col.markdown(f"**{what}** · {why}")
    who_col.caption(f":material/person: {action.who}")
    when_col.caption(f":material/event: {action.when}")


if not actions:
    st.success("Every KPI is on track. No action needed this week.")
else:
    with st.container(border=True):
        for action in actions[:3]:
            show(action)
        if len(actions) > 3:
            with st.expander(f"{len(actions) - 3} more items"):
                for action in actions[3:]:
                    show(action)
st.caption("Owners are role placeholders: set them in `config/targets.toml`.")
