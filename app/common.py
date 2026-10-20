"""Data, controls and KPI definitions shared by the dashboard pages."""

import pandas as pd
import streamlit as st

from super_store import formatting, metrics
from super_store import kpis as kpi_calc
from super_store.config import Targets, load_config
from super_store.data import load
from super_store.formatting import SHORT_PERIOD, day, fmt  # noqa: F401 (re-exported for pages)
from super_store.kpis import Kpi, breakdown  # noqa: F401 (re-exported for pages)

STATUS_LABELS = {
    "green": "On track",
    "yellow": "Monitor",
    "red": "Off track",
    "gray": "No target",
}
STATUS_COLORS = {"green": "#2e7d32", "yellow": "#f9a825", "red": "#c62828", "gray": "#9e9e9e"}

# Default targets, owner roles and review cadence: config/targets.toml
CONFIG = load_config()
# Sidebar what-if inputs: (label, Targets field, step, session-state key)
TARGET_INPUTS = [
    ("Sales growth vs last year (%)", "sales_growth", 1.0, "t_growth"),
    ("Profit margin (%)", "profit_margin", 0.5, "t_margin"),
    ("Avg discount, max (%)", "max_discount", 0.5, "t_discount"),
    ("Customer retention (%)", "retention", 1.0, "t_retention"),
    ("Revenue at risk, max (%)", "max_revenue_at_risk", 0.5, "t_risk"),
]
OWNERS = CONFIG.owners.kpi


# No ttl: the dataset is a static 2011-2014 snapshot, so it never goes stale
@st.cache_data
def data() -> pd.DataFrame:
    return load()


def as_of_options() -> list[pd.Period]:
    # Retention compares two full 12-month windows, so start 24 months in
    months = data()["Order Week"].dt.to_period("M")
    return list(pd.period_range(months.min() + 23, months.max(), freq="M"))


def sidebar_controls() -> None:
    """Period and target controls; values are read back through st.session_state."""
    options = as_of_options()
    st.sidebar.selectbox("As of", options, index=len(options) - 1, key="as_of",
                         format_func=lambda p: p.strftime("%b %Y"))
    st.sidebar.radio("Period", metrics.PERIODS, index=2, key="period")
    t = CONFIG.targets
    # Defaults from config; editing them here is a what-if for this session only
    with st.sidebar.expander("Targets"):
        for label, field, step, key in TARGET_INPUTS:
            low, high = Targets.bounds(field)  # same limits the config file is validated against
            st.number_input(label, min_value=low, max_value=high, value=getattr(t, field), step=step, key=key)


# Bounded caches, one entry per as-of month (~24 options, plus the year before for
# customer_health). No ttl: results depend only on the static dataset.
@st.cache_data(max_entries=48)
def customer_health(as_of: pd.Period) -> pd.DataFrame:
    """Retention and revenue at risk for the 12 months ending at `as_of`."""
    return kpi_calc.customer_health(data(), as_of)


@st.cache_data(max_entries=24)
def rfm_table(as_of: pd.Period) -> pd.DataFrame:
    return metrics.rfm(data(), as_of.end_time.normalize())


def segment_summary(table: pd.DataFrame) -> pd.DataFrame:
    out = table.groupby("Segment").agg(
        Customers=("Segment", "size"),
        Recency=("Recency", "mean"),
        Frequency=("Frequency", "mean"),
        Sales=("Monetary", "sum"),
    )
    out["% Customers"] = out.Customers / out.Customers.sum() * 100
    out["% Sales"] = out.Sales / out.Sales.sum() * 100
    return out.sort_values("Sales", ascending=False)


def period_caption(w: metrics.Window) -> str:
    """e.g. "YTD · 1 Jan – 31 Dec 2014 vs last year"."""
    return formatting.period_caption(w.start, w.end, st.session_state.period)


def window() -> metrics.Window:
    return metrics.period_window(st.session_state.as_of, st.session_state.period)


def targets() -> Targets:
    """Targets as currently set in the sidebar."""
    return Targets(**{field: st.session_state[key] for _, field, _, key in TARGET_INPUTS})


def kpis() -> list[Kpi]:
    as_of = st.session_state.as_of
    return kpi_calc.build_kpis(data(), as_of, st.session_state.period, targets(),
                               customer_health(as_of), customer_health(as_of - 12))
