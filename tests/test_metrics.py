"""Unit tests for super_store.metrics on small hand-built frames."""

import math

import pandas as pd
import pytest

from super_store import metrics
from super_store.metrics import Window

T = pd.Timestamp


def orders(rows: list[tuple]) -> pd.DataFrame:
    """Frame from (Customer ID, Order ID, Order Week, Sales, Profit, Discount) rows."""
    df = pd.DataFrame(rows, columns=["Customer ID", "Order ID", "Order Week", "Sales", "Profit", "Discount"])
    df["Order Week"] = pd.to_datetime(df["Order Week"])
    return df


@pytest.mark.parametrize(("as_of", "period", "start", "end"), [
    ("2014-05", "Month to date", "2014-05-01", "2014-05-31"),
    ("2014-05", "Quarter to date", "2014-04-01", "2014-05-31"),
    ("2014-04", "Quarter to date", "2014-04-01", "2014-04-30"),
    ("2014-12", "Quarter to date", "2014-10-01", "2014-12-31"),
    ("2014-05", "Year to date", "2014-01-01", "2014-05-31"),
    ("2014-05", "Trailing 12 months", "2013-06-01", "2014-05-31"),
    ("2014-12", "Trailing 12 months", "2014-01-01", "2014-12-31"),
    ("2012-02", "Month to date", "2012-02-01", "2012-02-29"),
])
def test_period_window(as_of, period, start, end):
    assert metrics.period_window(pd.Period(as_of, "M"), period) == Window(T(start), T(end))


def test_period_window_covers_every_period():
    as_of = pd.Period("2014-05", "M")
    for period in metrics.PERIODS:
        w = metrics.period_window(as_of, period)
        assert w.end == T("2014-05-31") and w.start <= T("2014-05-01")


@pytest.mark.parametrize(("start", "end", "prior_start", "prior_end"), [
    ("2014-01-01", "2014-05-31", "2013-01-01", "2013-05-31"),
    ("2012-02-01", "2012-02-29", "2011-02-01", "2011-02-28"),
])
def test_prior_year(start, end, prior_start, prior_end):
    assert Window(T(start), T(end)).prior_year() == Window(T(prior_start), T(prior_end))


def test_in_window_is_inclusive():
    df = orders([("a", 1, d, 1, 0, 0) for d in ["2013-12-31", "2014-01-01", "2014-01-31", "2014-02-01"]])
    got = metrics.in_window(df, Window(T("2014-01-01"), T("2014-01-31")))
    assert list(got["Order Week"]) == [T("2014-01-01"), T("2014-01-31")]


def test_sales_kpis():
    df = orders([("a", 1, "2014-01-06", 100, 10, 0.1), ("b", 2, "2014-01-13", 300, 50, 0.3)])
    assert metrics.sales_kpis(df) == pytest.approx(
        {"Sales": 400, "Profit": 60, "Profit Margin": 15.0, "Avg Discount": 20.0})


def test_sales_kpis_empty_margin_is_nan():
    assert math.isnan(metrics.sales_kpis(orders([]))["Profit Margin"])


def test_retention():
    df = orders([
        ("old", 1, "2012-06-04", 1, 0, 0),   # outside both windows
        ("a", 2, "2013-01-01", 1, 0, 0),     # prior window start
        ("b", 3, "2013-12-31", 1, 0, 0),     # prior window end
        ("c", 4, "2013-06-03", 1, 0, 0),
        ("d", 5, "2013-07-01", 1, 0, 0),
        ("a", 6, "2014-01-01", 1, 0, 0),     # current window start
        ("b", 7, "2014-12-31", 1, 0, 0),     # current window end
        ("c", 8, "2015-01-05", 1, 0, 0),     # after end: does not count
        ("new", 9, "2014-03-03", 1, 0, 0),   # not in the prior window
    ])
    assert metrics.retention(df, T("2014-12-31")) == pytest.approx(50.0)


def test_retention_without_prior_customers_is_nan():
    df = orders([("a", 1, "2014-03-03", 1, 0, 0)])
    assert math.isnan(metrics.retention(df, T("2014-12-31")))


def test_retention_is_nan_when_prior_window_predates_data():
    # Data starts 2013-01-01: retention at 2014-12-31 has a full prior year,
    # at 2014-11-30 the prior window would start 2012-12-01 and be partial
    df = orders([("a", 1, "2013-01-01", 1, 0, 0), ("a", 2, "2014-06-02", 1, 0, 0)])
    assert metrics.retention(df, T("2014-12-31")) == pytest.approx(100.0)
    assert math.isnan(metrics.retention(df, T("2014-11-30")))


# (customer, last order date, order count, lifetime sales) -> expected R, F, M and segment
RFM_CASE = {
    "A": ("2014-12-29", 1, 100, (5, 1, 1, "New Customers")),
    "B": ("2014-12-01", 2, 150, (4, 2, 2, "Potential Loyalists")),
    "C": ("2014-10-06", 3, 250, (3, 3, 4, "Need Attention")),
    "D": ("2014-06-02", 4, 200, (2, 4, 3, "At Risk")),
    "E": ("2014-01-06", 5, 300, (1, 5, 5, "Can't Lose")),
}


@pytest.fixture
def rfm_orders() -> pd.DataFrame:
    rows, order_id = [], 0
    for cust, (last, n, sales, _) in RFM_CASE.items():
        dates = [*pd.date_range("2013-01-07", periods=n - 1, freq="7D").strftime("%Y-%m-%d"), last]
        for d in dates:
            order_id += 1
            # Two lines per order: frequency counts orders, monetary sums lines
            rows += [(cust, order_id, d, sales / n / 2, 0, 0)] * 2
    rows.append(("A", 999, "2015-01-05", 10_000, 0, 0))  # after `end`: ignored
    return orders(rows)


def test_rfm_scores_and_segments(rfm_orders):
    table = metrics.rfm(rfm_orders, T("2014-12-31"))
    assert table.loc["A", "Recency"] == 3  # snapshot is the day after `end`
    assert table.loc["E", "Frequency"] == 5
    assert table.loc["A", "Monetary"] == pytest.approx(100)
    for cust, (*_, expected) in RFM_CASE.items():
        assert tuple(table.loc[cust, ["R", "F", "M", "Segment"]]) == expected, cust


def test_segment_map_covers_every_score_pair():
    pairs = pd.Series([f"{r}{f}" for r in range(1, 6) for f in range(1, 6)])
    segments = pairs.replace(metrics.SEGMENT_MAP, regex=True)
    assert set(segments) <= set(metrics.SEGMENT_MAP.values())
    expected = {"11": "Hibernating", "15": "Can't Lose", "24": "At Risk", "32": "About to Sleep",
                "45": "Loyal Customers", "55": "Champions"}
    assert {k: v for k, v in zip(pairs, segments, strict=True) if k in expected} == expected


def test_revenue_at_risk(rfm_orders):
    table = metrics.rfm(rfm_orders, T("2014-12-31"))
    assert metrics.revenue_at_risk(table) == pytest.approx(50.0)  # (D 200 + E 300) / 1000


def test_revenue_at_risk_from_table():
    table = pd.DataFrame({"Monetary": [10, 30, 60], "Segment": ["Champions", "At Risk", "Hibernating"]})
    assert metrics.revenue_at_risk(table) == pytest.approx(30.0)


def test_monthly():
    df = orders([
        ("a", 1, "2014-01-06", 100, 20, 0.1),
        ("b", 2, "2014-01-27", 300, 20, 0.3),
        ("a", 3, "2014-03-03", 200, -10, 0.0),
    ])
    got = metrics.monthly(df)
    assert list(got.index) == [pd.Period("2014-01", "M"), pd.Period("2014-03", "M")]
    assert list(got.columns) == ["Sales", "Profit", "Profit Margin", "Avg Discount"]
    assert got.loc[pd.Period("2014-01", "M")].tolist() == pytest.approx([400, 40, 10.0, 20.0])
    assert got.loc[pd.Period("2014-03", "M")].tolist() == pytest.approx([200, -10, -5.0, 0.0])


def test_rolling_margin_sums_profit_and_sales():
    months = pd.DataFrame({"Sales": [100, 100, 800, 1000], "Profit": [50, 0, 80, 100]})
    got = metrics.rolling_margin(months)
    assert got.iloc[:2].isna().all()
    # Mean of the monthly margins (50, 0, 10) would be 20; the pooled margin is 130 / 1000
    assert got.iloc[2:].tolist() == pytest.approx([13.0, 180 / 1900 * 100])


@pytest.mark.parametrize(("actual", "target", "higher_is_better", "expected"), [
    (110, 100, True, "green"),
    (100, 100, True, "green"),
    (95, 100, True, "yellow"),
    (90, 100, True, "yellow"),
    (89, 100, True, "red"),
    (-5, 12, True, "red"),
    (8, 10, False, "green"),
    (10, 10, False, "green"),
    (11, 10, False, "yellow"),  # 10 / 11 = 0.91
    (12, 10, False, "red"),
    (100, None, True, "gray"),
    (100, float("nan"), True, "gray"),
    (float("nan"), 100, True, "gray"),
    (0, 100, True, "gray"),
    (0, 10, False, "gray"),
])
def test_status(actual, target, higher_is_better, expected):
    assert metrics.status(actual, target, higher_is_better) == expected
