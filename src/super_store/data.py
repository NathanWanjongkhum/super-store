import logging
from dataclasses import dataclass
from functools import cache
from pathlib import Path

import kagglehub
import pandas as pd

from super_store.validation import DataValidationError, validate

__all__ = ["DataUnavailableError", "DataValidationError", "LoadInfo", "load", "load_info",
           "raw_path"]

DATASET = "abbas829/global-superstore-sales-dataset"
# Last good load, used when Kaggle is unreachable. data/ is gitignored.
SNAPSHOT = Path(__file__).resolve().parents[2] / "data" / "superstore.parquet"

log = logging.getLogger(__name__)


class DataUnavailableError(RuntimeError):
    """Neither Kaggle nor the local snapshot could provide the dataset."""


@dataclass(frozen=True)
class LoadInfo:
    """Where and when the data came from; stored in `df.attrs["load_info"]`."""
    source: str  # "Kaggle" or "snapshot"
    loaded_at: pd.Timestamp  # local time of this load (or, for a snapshot, of its file)
    latest_week: pd.Timestamp
    rows: int


@cache
def raw_path() -> Path:
    return Path(kagglehub.dataset_download(DATASET)) / "Global Superstore.csv"


def _read_kaggle() -> pd.DataFrame:
    df = pd.read_csv(raw_path())
    # Order/Ship Date are corrupted in this upload (every value is "00:00.0"),
    # so rebuild a week-accurate order date from Year + weeknum.
    # Ship Date can't be recovered.
    df = df.drop(columns=["Order Date", "Ship Date"])
    jan1 = pd.to_datetime(df["Year"].astype(str) + "-01-01")
    df["Order Week"] = jan1 + pd.to_timedelta((df["weeknum"] - 1) * 7, unit="D")
    return df


def load(snapshot: Path | None = None) -> pd.DataFrame:
    """Orders from Kaggle, falling back to the local Parquet snapshot; validated.

    Provenance is in `load_info(df)`. Raises DataValidationError or DataUnavailableError.
    """
    snapshot = Path(snapshot or SNAPSHOT)
    try:
        df = _read_kaggle()
    except Exception as kaggle_error:
        if not snapshot.exists():
            raise DataUnavailableError(
                f"Could not download '{DATASET}' from Kaggle ({kaggle_error}) and no local "
                f"snapshot exists at {snapshot}. Connect to the internet and reload.") from kaggle_error
        log.warning("Kaggle download failed (%s); using snapshot %s", kaggle_error, snapshot)
        df = validate(pd.read_parquet(snapshot))
        source = "snapshot"
        loaded_at = pd.Timestamp.fromtimestamp(snapshot.stat().st_mtime)
    else:
        validate(df)
        source = "Kaggle"
        loaded_at = pd.Timestamp.now()
        try:
            snapshot.parent.mkdir(parents=True, exist_ok=True)
            df.to_parquet(snapshot, index=False)
        except Exception as e:  # a missing snapshot only matters offline
            log.warning("Could not write snapshot %s: %s", snapshot, e)
    df.attrs["load_info"] = LoadInfo(source, loaded_at.floor("s"), df["Order Week"].max(), len(df))
    return df


def load_info(df: pd.DataFrame) -> LoadInfo | None:
    """Provenance of a frame returned by `load()`, if it still carries it."""
    return df.attrs.get("load_info")
