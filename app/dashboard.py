"""Superstore executive dashboard. Run with: uv run streamlit run app/dashboard.py"""

import pandas as pd
import streamlit as st

from common import data, sidebar_controls
from super_store.data import DataUnavailableError, DataValidationError, load_info

st.set_page_config(page_title="Superstore Executive Summary", page_icon=":material/monitoring:",
                   layout="wide")

try:
    df = data()
except (DataUnavailableError, DataValidationError) as e:
    st.error(f"**Couldn't load the sales data**\n\n{e}", icon=":material/error:")
    st.stop()


def freshness_caption(df: pd.DataFrame) -> str | None:
    """e.g. "Data through 31 Dec 2014 · loaded 07:43 from Kaggle"."""
    if (info := load_info(df)) is None:
        return None
    at = info.loaded_at
    when = f"{at:%H:%M}" if at.date() == pd.Timestamp.now().date() else f"{at.day} {at:%b %Y}"
    week = info.latest_week
    return f"Data through {week.day} {week:%b %Y} · loaded {when} from {info.source}"


# Controls live here so they apply to, and persist across, every page
sidebar_controls()
if caption := freshness_caption(df):
    st.sidebar.caption(caption)

st.navigation([
    st.Page("summary.py", title="Executive Summary", icon=":material/dashboard:", default=True),
    st.Page("drilldown.py", title="Drill-down", icon=":material/search:"),
]).run()
