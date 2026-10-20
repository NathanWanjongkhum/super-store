"""Targets, owners and review cadence, loaded from config/targets.toml and validated with pydantic."""

import os
import tomllib
from pathlib import Path
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, ValidationError, field_validator
from pydantic_core import ErrorDetails

ENV_VAR = "SUPER_STORE_CONFIG"
DEFAULT_PATH = Path(__file__).resolve().parents[2] / "config" / "targets.toml"
KPI_NAMES = ("Sales", "Profit", "Profit Margin", "Avg Discount", "Customer Retention",
             "Revenue at Risk")
WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
Weekday = Literal["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

# Strict: TOML ints are fine, but "high" or true are not silently coerced
Percent = Annotated[float, Field(strict=True, ge=0, le=100)]


class ConfigError(ValueError):
    """The config file is missing or has missing/invalid keys."""


class _Model(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Targets(_Model):
    """All values are percentages; the bounds also limit the dashboard's sidebar inputs."""
    sales_growth: Annotated[float, Field(strict=True, ge=-100, le=1000)]
    profit_margin: Annotated[float, Field(strict=True, ge=-100, le=100)]
    max_discount: Percent
    retention: Percent
    max_revenue_at_risk: Percent

    @classmethod
    def bounds(cls, name: str) -> tuple[float, float]:
        """(min, max) allowed for a target, e.g. for st.number_input."""
        meta = cls.model_fields[name].metadata
        return (next(float(m.ge) for m in meta if hasattr(m, "ge")),
                next(float(m.le) for m in meta if hasattr(m, "le")))


def _template(field: str):
    def check(value: str) -> str:
        if f"{{{field}}}" not in value:
            raise ValueError(f"must contain {{{field}}}")
        return value
    return AfterValidator(check)


class Owners(_Model):
    kpi: dict[str, Annotated[str, Field(strict=True)]]
    market: Annotated[str, Field(strict=True), _template("market")]
    category: Annotated[str, Field(strict=True), _template("category")]

    @field_validator("kpi")
    @classmethod
    def _every_kpi_has_an_owner(cls, kpi: dict[str, str]) -> dict[str, str]:
        if missing := [name for name in KPI_NAMES if name not in kpi]:
            raise ValueError(f"is missing {', '.join(missing)}")
        return kpi

    def for_market(self, market: str) -> str:
        return self.market.format(market=market)

    def for_category(self, category: str) -> str:
        return self.category.format(category=category)


class Review(_Model):
    cadence: Literal["weekly"]
    weekday: Weekday

    @property
    def weekday_index(self) -> int:
        return WEEKDAYS.index(self.weekday)


class Config(_Model):
    targets: Targets
    owners: Owners
    review: Review


def config_path() -> Path:
    return Path(os.environ.get(ENV_VAR) or DEFAULT_PATH)


def _describe(error: ErrorDetails) -> str:
    """One pydantic error as "[section] key problem", matching the TOML layout."""
    loc = [str(part) for part in error["loc"]]
    kind = error["type"]
    if kind == "missing":
        return f"missing table [{loc[0]}]" if len(loc) == 1 else f"[{'.'.join(loc[:-1])}] is missing {loc[-1]}"
    if kind == "value_error":  # our own validators: the message already names the problem
        message = error["msg"].removeprefix("Value error, ")
        if loc[-1] == "kpi":
            return f"[{'.'.join(loc)}] {message}"
        return f"[{'.'.join(loc[:-1])}] {loc[-1]} {message}"
    section, key = ".".join(loc[:-1]), loc[-1]
    if kind.startswith(("float", "int")):
        return f"[{section}] {key} must be a number"
    if kind.startswith("string"):
        return f"[{section}] {key} must be a string"
    if kind == "extra_forbidden":
        return f"[{section}] unknown key {key}"
    return f"[{section}] {key}: {error['msg']}"


def load_config(path: str | Path | None = None) -> Config:
    """Load and validate the config; `path` defaults to $SUPER_STORE_CONFIG or config/targets.toml."""
    path = Path(path) if path else config_path()
    try:
        raw = tomllib.loads(path.read_text())
    except FileNotFoundError:
        raise ConfigError(f"Config file not found: {path}") from None
    except tomllib.TOMLDecodeError as e:
        raise ConfigError(f"{path}: invalid TOML ({e})") from None
    try:
        return Config.model_validate(raw)
    except ValidationError as e:
        problems = "; ".join(_describe(err) for err in e.errors())
        raise ConfigError(f"{path}: {problems}") from None
