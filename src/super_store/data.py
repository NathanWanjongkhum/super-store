from functools import cache
from pathlib import Path

import kagglehub
import pandas as pd

DATASET = "abbas829/global-superstore-sales-dataset"


@cache
def raw_path() -> Path:
    return Path(kagglehub.dataset_download(DATASET)) / "Global Superstore.csv"


def load() -> pd.DataFrame:
    df = pd.read_csv(raw_path())
    jan1 = pd.to_datetime(df["Year"].astype(str) + "-01-01")
    df["Order Week"] = jan1 + pd.to_timedelta((df["weeknum"] - 1) * 7, unit="D")
    return df
