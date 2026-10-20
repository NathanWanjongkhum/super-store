"""Smoke tests: every dashboard page renders on the real dataset without exceptions."""

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from super_store import metrics

APP = str(Path(__file__).resolve().parents[1] / "app" / "dashboard.py")
DIMENSIONS = ["Market", "Region", "Category", "Sub-Category", "Segment", "Ship Mode", "RFM Segment"]

pytestmark = pytest.mark.slow


def run(at: AppTest) -> AppTest:
    at.run()
    assert not at.exception, [e.message for e in at.exception]
    return at


@pytest.fixture
def at() -> AppTest:
    return run(AppTest.from_file(APP, default_timeout=120))


@pytest.mark.parametrize("period", metrics.PERIODS)
def test_summary_each_period(at, period):
    at.radio(key="period").set_value(period)
    run(at)
    assert at.session_state.period == period


def test_summary_earliest_as_of(at):
    latest = at.session_state.as_of
    at.selectbox(key="as_of").select_index(0)
    run(at)
    assert at.session_state.as_of < latest


@pytest.mark.parametrize("dim", DIMENSIONS)
def test_drilldown_each_dimension(at, dim):
    at.query_params["by"] = dim
    at.switch_page("drilldown.py")
    run(at)
    assert at.title[0].value == "Drill-down"
    assert at.button_group[0].value == dim
