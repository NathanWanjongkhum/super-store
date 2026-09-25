from functools import cache
from pathlib import Path

import kagglehub
import pandas as pd

DATASET = "abbas829/global-superstore-sales-dataset"


@cache
def raw_path() -> Path:
    return Path(kagglehub.dataset_download(DATASET)) / "Global Superstore.csv"


def load() -> pd.DataFrame:
    return pd.read_csv(raw_path(), parse_dates=["Order Date", "Ship Date"])
