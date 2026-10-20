"""Sanity checks for the Superstore order table."""

import pandas as pd

REQUIRED = ["Order ID", "Customer ID", "Customer Name", "Order Week", "Market", "Region",
            "Category", "Sub-Category", "Segment", "Ship Mode", "Sales", "Profit", "Discount",
            "Quantity"]
NOT_NULL = ["Order ID", "Customer ID", "Order Week", "Sales", "Profit", "Discount", "Market",
            "Category", "Sub-Category"]
NUMERIC = ["Sales", "Profit", "Discount", "Quantity"]
EARLIEST_WEEK = pd.Timestamp("2000-01-01")


class DataValidationError(ValueError):
    """The order table failed one or more sanity checks."""


def validate(df: pd.DataFrame) -> pd.DataFrame:
    """Return `df` unchanged if it passes all checks, else raise DataValidationError."""
    if df.empty:
        raise DataValidationError("Dataset has no rows.")
    missing = [c for c in REQUIRED if c not in df.columns]
    if missing:
        raise DataValidationError(f"Missing required columns: {', '.join(missing)}.")

    problems = []
    wrong_type = [c for c in NUMERIC if not pd.api.types.is_numeric_dtype(df[c])]
    if not pd.api.types.is_datetime64_any_dtype(df["Order Week"]):
        wrong_type.append("Order Week")
    if wrong_type:
        problems.append(f"unexpected dtype in {', '.join(wrong_type)} "
                        f"(expected numeric, and datetime for Order Week)")
    for col in NOT_NULL:
        if n := int(df[col].isna().sum()):
            problems.append(f"{n:,} rows with null {col}")
    if problems:  # range checks below assume clean, correctly typed columns
        raise _error(problems, len(df))

    latest_ok = pd.Timestamp.now() + pd.Timedelta(days=366)
    checks = {
        "negative Sales": df["Sales"] < 0,
        "Discount outside 0-1": ~df["Discount"].between(0, 1),
        f"Order Week outside {EARLIEST_WEEK:%Y-%m-%d} to {latest_ok:%Y-%m-%d}":
            ~df["Order Week"].between(EARLIEST_WEEK, latest_ok),
    }
    problems = [f"{n:,} rows with {label}" for label, mask in checks.items()
                if (n := int(mask.sum()))]
    if problems:
        raise _error(problems, len(df))
    return df


def _error(problems: list[str], total: int) -> DataValidationError:
    return DataValidationError(f"Data validation failed ({total:,} rows checked): "
                               + "; ".join(problems) + ".")
