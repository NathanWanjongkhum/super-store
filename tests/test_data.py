"""Validation and snapshot fallback for super_store.data; no network access."""

import pickle

import pandas as pd
import pytest

from super_store import data
from super_store.validation import DataValidationError, validate


def frame(n: int = 3) -> pd.DataFrame:
    return pd.DataFrame({
        "Order ID": [f"O-{i}" for i in range(n)],
        "Customer ID": [f"C-{i}" for i in range(n)],
        "Customer Name": ["Ann"] * n,
        "Year": [2014] * n,
        "weeknum": list(range(1, n + 1)),
        "Market": ["EU"] * n,
        "Region": ["North"] * n,
        "Category": ["Technology"] * n,
        "Sub-Category": ["Phones"] * n,
        "Segment": ["Consumer"] * n,
        "Ship Mode": ["Standard Class"] * n,
        "Sales": [100] * n,
        "Profit": [-5.0] + [10.0] * (n - 1),
        "Discount": [0.0, 0.2, 1.0][:n] + [0.1] * max(n - 3, 0),
        "Quantity": [1] * n,
        "Order Week": pd.date_range("2014-01-01", periods=n, freq="7D"),
    })


def test_valid_frame_passes():
    df = frame()
    assert validate(df) is df


@pytest.mark.parametrize("mutate, message", [
    (lambda df: df.iloc[0:0], "no rows"),
    (lambda df: df.drop(columns=["Market", "Profit"]), "Missing required columns: Market, Profit"),
    (lambda df: df.assign(Sales=df.Sales.astype(str)), "unexpected dtype in Sales"),
    (lambda df: df.assign(**{"Order Week": df["Order Week"].astype(str)}),
     "unexpected dtype in Order Week"),
    (lambda df: df.assign(**{"Customer ID": [None, "C-1", None]}), "2 rows with null Customer ID"),
    (lambda df: df.assign(Profit=[None, 1.0, 2.0]), "1 rows with null Profit"),
    (lambda df: df.assign(Sales=[-1, 5, 5]), "1 rows with negative Sales"),
    (lambda df: df.assign(Discount=[-0.1, 0.5, 1.5]), "2 rows with Discount outside 0-1"),
    (lambda df: df.assign(**{"Order Week": pd.to_datetime(["1999-12-31", "2014-01-01",
                                                           "2200-01-01"])}),
     "2 rows with Order Week outside"),
])
def test_invalid_frame_fails_with_message(mutate, message):
    with pytest.raises(DataValidationError, match=message):
        validate(mutate(frame()))


def test_multiple_problems_reported_together():
    df = frame().assign(Sales=[-1, -2, 5], Discount=[0.1, 0.1, 2.0])
    with pytest.raises(DataValidationError) as e:
        validate(df)
    assert "3 rows checked" in str(e.value)
    assert "2 rows with negative Sales" in str(e.value)
    assert "1 rows with Discount outside 0-1" in str(e.value)


def offline(monkeypatch):
    def fail(*_):
        raise ConnectionError("no network")
    monkeypatch.setattr(data.kagglehub, "dataset_download", fail)
    data.raw_path.cache_clear()


def online(monkeypatch, tmp_path, df: pd.DataFrame):
    csv = tmp_path / "kaggle"
    csv.mkdir()
    # Mirror the real upload: corrupted date columns that load() drops
    raw = df.drop(columns=["Order Week"]).assign(**{"Order Date": "00:00.0", "Ship Date": "00:00.0"})
    raw.to_csv(csv / "Global Superstore.csv", index=False)
    monkeypatch.setattr(data.kagglehub, "dataset_download", lambda *_: str(csv))
    data.raw_path.cache_clear()


def test_kaggle_load_writes_snapshot(monkeypatch, tmp_path):
    snapshot = tmp_path / "data" / "superstore.parquet"
    online(monkeypatch, tmp_path, frame())
    df = data.load(snapshot)
    info = data.load_info(df)
    assert info is not None
    assert info.source == "Kaggle"
    assert info.rows == 3
    assert info.latest_week == pd.Timestamp("2014-01-15")
    assert snapshot.exists()
    data.raw_path.cache_clear()


def test_falls_back_to_snapshot(monkeypatch, tmp_path):
    snapshot = tmp_path / "superstore.parquet"
    frame().to_parquet(snapshot, index=False)
    offline(monkeypatch)
    df = data.load(snapshot)
    assert len(df) == 3
    info = data.load_info(df)
    assert info is not None
    assert info.source == "snapshot"
    assert info.latest_week == pd.Timestamp("2014-01-15")


def test_default_snapshot_path_is_used(monkeypatch, tmp_path):
    snapshot = tmp_path / "superstore.parquet"
    frame().to_parquet(snapshot, index=False)
    monkeypatch.setattr(data, "SNAPSHOT", snapshot)
    offline(monkeypatch)
    info = data.load_info(data.load())
    assert info is not None and info.source == "snapshot"


def test_bad_snapshot_is_validated(monkeypatch, tmp_path):
    snapshot = tmp_path / "superstore.parquet"
    frame().assign(Sales=[-1, 1, 1]).to_parquet(snapshot, index=False)
    offline(monkeypatch)
    with pytest.raises(DataValidationError, match="negative Sales"):
        data.load(snapshot)


def test_no_source_raises_clear_error(monkeypatch, tmp_path):
    offline(monkeypatch)
    with pytest.raises(data.DataUnavailableError, match="no network.*no local snapshot"):
        data.load(tmp_path / "missing.parquet")


def test_load_info_survives_pickling(monkeypatch, tmp_path):
    snapshot = tmp_path / "superstore.parquet"
    frame().to_parquet(snapshot, index=False)
    offline(monkeypatch)
    df = pickle.loads(pickle.dumps(data.load(snapshot)))
    info = data.load_info(df)
    assert info is not None and info.source == "snapshot"
