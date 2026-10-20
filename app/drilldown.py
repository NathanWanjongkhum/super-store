"""Drill-down: the "why" behind each KPI, broken down by any dimension."""

import pandas as pd
import streamlit as st

import charts
from common import SHORT_PERIOD, breakdown, data, day, period_caption, rfm_table, segment_summary, window
from super_store import metrics

DIMENSIONS = ["Market", "Region", "Category", "Sub-Category", "Segment", "Ship Mode", "RFM Segment"]

s = st.session_state
df = data()
w = window()


def download(table: pd.DataFrame, decimals: dict[str, int], names: dict[str, str], *parts: str) -> None:
    """CSV of the table below with rounded numbers, e.g. superstore_sub-category_ytd_2014-12.csv."""
    whole = [col for col, n in decimals.items() if n == 0]
    out = table.reset_index().round(pd.Series(decimals)).astype({col: "Int64" for col in whole}).rename(columns=names)
    slug = "_".join(p.lower().replace(" ", "-") for p in ("superstore", *parts, s.as_of.strftime("%Y-%m")))
    with st.container(horizontal=True, horizontal_alignment="right"):
        st.download_button("Download CSV", out.to_csv(index=False), file_name=f"{slug}.csv",
                           mime="text/csv", icon=":material/download:", on_click="ignore")


st.title("Drill-down")
requested = st.query_params.get("by")
dim = st.segmented_control("Break down by", DIMENSIONS, required=True,
                           default=requested if requested in DIMENSIONS else "Market")

if dim == "RFM Segment":
    st.caption(f"Customers scored on orders up to {day(w.end)}. "
               "Customer ID is per market, so a person buying in two markets counts twice.")
    segments = segment_summary(rfm_table(s.as_of))
    with st.container(border=True):
        st.altair_chart(charts.segment_sales(segments, metrics.AT_RISK_SEGMENTS, step=28),
                        alt="Lifetime sales by RFM segment, at-risk segments highlighted")
    # RFM uses all orders up to the as-of month, so the period selector doesn't apply
    download(segments, {"Recency": 0, "Frequency": 1, "Sales": 0, "% Customers": 1, "% Sales": 1}, {
        "Recency": "Avg days since last order", "Frequency": "Avg orders", "Sales": "Lifetime sales ($)",
        "% Customers": "% of customers", "% Sales": "% of sales",
    }, dim)
    st.dataframe(segments, alt="RFM segments: customers, recency, frequency and share of sales", column_config={
        "Recency": st.column_config.NumberColumn("Avg days since last order", format="%.0f"),
        "Frequency": st.column_config.NumberColumn("Avg orders", format="%.1f"),
        "Sales": st.column_config.NumberColumn("Lifetime sales", format="dollar"),
        "% Customers": st.column_config.ProgressColumn(format="%.1f%%", min_value=0, max_value=100),
        "% Sales": st.column_config.ProgressColumn(format="%.1f%%", min_value=0, max_value=100),
    })
    st.stop()

left, right = st.columns(2)
markets = left.multiselect("Market", sorted(df.Market.unique()), placeholder="All markets")
categories = right.multiselect("Category", sorted(df.Category.unique()), placeholder="All categories")
if markets:
    df = df[df.Market.isin(markets)]
if categories:
    df = df[df.Category.isin(categories)]

st.caption(period_caption(w))
table = breakdown(df, dim, w, s.t_margin)
with st.container(border=True):
    st.markdown(f"**Profit margin by {dim.lower()}** (dashed line = {s.t_margin:.1f}% target)")
    st.altair_chart(charts.margin_by(table, dim, s.t_margin, step=26),
                    alt=f"Profit margin by {dim.lower()} vs the {s.t_margin:.1f}% target")
download(table.drop(columns="Status").rename_axis(dim), {
    "Sales": 0, "% of Sales": 1, "Growth %": 1, "Profit": 0, "Profit Margin": 1, "Avg Discount": 1,
}, {
    "Sales": "Sales ($)", "% of Sales": "% of sales", "Growth %": "Growth vs last year (%)",
    "Profit": "Profit ($)", "Profit Margin": "Profit margin (%)", "Avg Discount": "Avg discount (%)",
}, dim, SHORT_PERIOD[s.period])
st.dataframe(table.drop(columns="Status").assign(Profit=table.Profit.round().astype(int)),
             alt=f"Sales, growth, profit, margin and discount by {dim.lower()}", column_config={
    "Sales": st.column_config.NumberColumn(format="dollar"),
    "% of Sales": st.column_config.ProgressColumn(format="%.1f%%", min_value=0, max_value=100),
    "Growth %": st.column_config.NumberColumn("Growth vs last year", format="%+.1f%%"),
    "Profit": st.column_config.NumberColumn(format="dollar"),
    "Profit Margin": st.column_config.NumberColumn(format="%.1f%%"),
    "Avg Discount": st.column_config.NumberColumn(format="%.1f%%"),
})
