"""Action-item rules, config loading and the dry-run alert senders (no data download, no network)."""

import smtplib
import socket
import subprocess
import sys
import urllib.request

import pandas as pd
import pytest

from super_store.actions import Action, build_actions, rank, review_text
from super_store.alerts import DryRunEmailSender, DryRunSlackSender
from super_store.config import DEFAULT_PATH, ConfigError, Owners, Review, Targets, load_config
from super_store.kpis import Kpi

TARGETS = Targets(sales_growth=25, profit_margin=12, max_discount=15, retention=80,
                  max_revenue_at_risk=15)
OWNERS = Owners(
    kpi={"Sales": "VP of Sales", "Profit": "CFO", "Profit Margin": "CFO",
         "Avg Discount": "VP of Sales", "Customer Retention": "Head of Customer Success",
         "Revenue at Risk": "Head of Customer Success"},
    market="{market} Market Lead", category="{category} Category Manager")
WHEN = "Mon 5 Jan 2015"


def kpi(name, value, last_year, target, higher=True, kind="pct"):
    return Kpi(name, value, last_year, target, higher, kind, [], "")


def dec_2014_kpis():
    """Dec 2014 YTD values, as on the dashboard."""
    return [
        kpi("Sales", 4_299_866, 3_405_747, 3_405_747 * 1.25, kind="money"),  # green
        kpi("Profit", 504_166, 406_935, 406_935 * 1.25, kind="money"),  # yellow, $4.5K under
        kpi("Profit Margin", 11.73, 11.95, 12.0),  # yellow
        kpi("Avg Discount", 14.3, 14.0, 15.0, higher=False),  # green
        kpi("Customer Retention", 82.0, 75.8, 80.0),  # green
        kpi("Revenue at Risk", 19.1, 18.7, 15.0, higher=False),  # red
    ]


def breakdown_frame(rows: dict[str, dict]) -> pd.DataFrame:
    return pd.DataFrame.from_dict(rows, orient="index")


MARKETS = breakdown_frame({
    "APAC": {"Sales": 1.2e6, "% of Sales": 28.0, "Profit": 160e3, "Profit Margin": 13.3, "Status": "green"},
    "LATAM": {"Sales": 719e3, "% of Sales": 16.7, "Profit": 75e3, "Profit Margin": 10.4, "Status": "yellow"},
    "EMEA": {"Sales": 302e3, "% of Sales": 7.0, "Profit": 22.7e3, "Profit Margin": 7.5, "Status": "red"},
})
SUB_CATEGORIES = breakdown_frame({
    "Phones": {"Sales": 500e3, "Profit": 60e3, "Avg Discount": 12.0},
    "Tables": {"Sales": 243_500, "Profit": -30_500, "Avg Discount": 29.0},
})
CATEGORY_OF = pd.Series({"Phones": "Technology", "Tables": "Furniture"})


def build(kpis=None, markets=MARKETS, subs=SUB_CATEGORIES):
    return build_actions(kpis or dec_2014_kpis(), markets, subs, CATEGORY_OF, TARGETS, OWNERS, WHEN)


# --- Ranking and filtering ---------------------------------------------------

def test_rank_red_first_then_impact():
    items = [Action("yellow", "y-big", "", "", "", 1e6), Action("red", "r-small", "", "", "", 1),
             Action("red", "r-big", "", "", "", 100), Action("yellow", "y-small", "", "", "", 5)]
    assert [a.what for a in rank(items)] == ["r-big", "r-small", "y-big", "y-small"]


def test_dec_2014_order():
    whats = [a.what for a in build()]
    assert whats == [
        "Revenue at Risk 19.1% vs 15.0% max",
        "Tables lost $30.5K on $243.5K sales",
        "EMEA margin 7.5% vs 12.0% target",
        "Profit Margin 11.7% vs 12.0% target",
        "Profit $504.2K, $4.5K under target",
    ]


def test_only_off_track_items():
    items = build()
    assert {a.status for a in items} <= {"red", "yellow"}
    names = " ".join(a.what for a in items)
    for on_track in ("Sales $", "Avg Discount", "Customer Retention", "APAC", "LATAM", "Phones"):
        assert on_track not in names


def test_all_on_track_means_no_actions():
    green = [kpi("Profit Margin", 13, 12, 12), kpi("Sales", 10, 8, 9, kind="money"),
             kpi("Avg Discount", 10, 10, 15, higher=False)]
    assert build(green, MARKETS.iloc[:1], SUB_CATEGORIES.iloc[:1]) == []


# --- Wording -------------------------------------------------------------------

def by_what(prefix):
    return next(a for a in build() if a.what.startswith(prefix))


def test_loss_wording():
    a = by_what("Tables")
    assert (a.status, a.why, a.who, a.when) == (
        "red", "Avg discount 29% vs 14% overall.", "Furniture Category Manager", WHEN)
    assert a.impact == pytest.approx(30_500)


def test_market_wording():
    a = by_what("EMEA")
    assert a.why == "7% of sales; target adds ≈ $13.6K profit."
    assert a.who == "EMEA Market Lead"


def test_kpi_wording():
    assert by_what("Revenue at Risk").why == "Lapsed frequent buyers, up 0.4 pts YoY."
    assert by_what("Revenue at Risk").who == "Head of Customer Success"
    assert by_what("Profit Margin").why == "Each point ≈ $43.0K profit."
    assert by_what("Profit $").why == "+23.9% YoY, slower than sales (+26.3%)."


def test_other_kpi_wording():
    kpis = [kpi("Sales", 90, 80, 100, kind="money"), kpi("Avg Discount", 18, 16, 15, higher=False),
            kpi("Customer Retention", 70, 75, 80)]
    whys = {a.what: a.why for a in build(kpis, MARKETS.iloc[:1], SUB_CATEGORIES.iloc[:1])}
    assert whys == {
        "Sales $90, $10 under target": "+12.5% YoY vs +25% plan.",
        "Avg Discount 18.0% vs 15.0% max": "Heavy discounts drive the loss-making products.",
        "Customer Retention 70.0% vs 80.0% target": "30% of last year's customers haven't reordered.",
    }


def test_review_text_is_next_review_weekday():
    assert review_text(pd.Timestamp("2014-12-31"), Review(cadence="weekly", weekday="Monday")) == "Mon 5 Jan 2015"
    assert review_text(pd.Timestamp("2014-12-29"), Review(cadence="weekly", weekday="Monday")) == "Mon 5 Jan 2015"
    assert review_text(pd.Timestamp("2014-12-31"), Review(cadence="weekly", weekday="Friday")) == "Fri 2 Jan 2015"


# --- Config ----------------------------------------------------------------------

def test_default_config_loads():
    config = load_config(DEFAULT_PATH)
    assert config.targets == TARGETS
    assert config.owners == OWNERS
    assert config.owners.for_market("EMEA") == "EMEA Market Lead"
    assert config.review == Review(cadence="weekly", weekday="Monday")


def test_env_var_overrides_path(tmp_path, monkeypatch):
    path = tmp_path / "custom.toml"
    path.write_text(DEFAULT_PATH.read_text().replace("profit_margin = 12.0", "profit_margin = 9"))
    monkeypatch.setenv("SUPER_STORE_CONFIG", str(path))
    assert load_config().targets.profit_margin == 9.0


@pytest.mark.parametrize("old, message", [
    ("profit_margin = 12.0", "[targets] is missing profit_margin"),
    ('"Profit" = "CFO"', "[owners.kpi] is missing Profit"),
    ('market = "{market} Market Lead"', "[owners] is missing market"),
    ('weekday = "Monday"', "[review] is missing weekday"),
])
def test_missing_key_errors(tmp_path, old, message):
    path = tmp_path / "targets.toml"
    path.write_text(DEFAULT_PATH.read_text().replace(old, ""))
    with pytest.raises(ConfigError, match=message.replace("[", r"\[").replace("]", r"\]")):
        load_config(path)


@pytest.mark.parametrize("old, new, message", [
    ("retention = 80.0", "retention = 180.0", "[targets] retention: Input should be less than or equal to 100"),
    ("max_discount = 15.0", "max_discount = true", "[targets] max_discount must be a number"),
    ('market = "{market} Market Lead"', 'market = "Market Lead"', "[owners] market must contain {market}"),
    ('weekday = "Monday"', 'weekday = "Funday"', "[review] weekday: Input should be"),
    ("[review]", "[review]\nmonthly = true", "[review] unknown key monthly"),
])
def test_pydantic_rules(tmp_path, old, new, message):
    path = tmp_path / "targets.toml"
    path.write_text(DEFAULT_PATH.read_text().replace(old, new))
    with pytest.raises(ConfigError) as error:
        load_config(path)
    assert message in str(error.value)


def test_target_bounds_for_sidebar():
    assert Targets.bounds("retention") == (0.0, 100.0)
    assert Targets.bounds("sales_growth") == (-100.0, 1000.0)


def test_invalid_values_and_missing_file(tmp_path):
    path = tmp_path / "targets.toml"
    path.write_text(DEFAULT_PATH.read_text().replace("retention = 80.0", 'retention = "high"'))
    with pytest.raises(ConfigError, match="retention must be a number"):
        load_config(path)
    with pytest.raises(ConfigError, match="not found"):
        load_config(tmp_path / "nope.toml")


# --- Dry-run senders ----------------------------------------------------------------

@pytest.fixture
def no_network(monkeypatch):
    def boom(*args, **kwargs):
        raise AssertionError("network access attempted")
    monkeypatch.setattr(socket, "socket", boom)
    monkeypatch.setattr(socket, "create_connection", boom)
    monkeypatch.setattr(smtplib, "SMTP", boom)
    monkeypatch.setattr(smtplib, "SMTP_SSL", boom)
    monkeypatch.setattr(urllib.request, "urlopen", boom)


def test_email_dry_run(no_network):
    items = build()
    payload = DryRunEmailSender().send("Digest", ["Sales: $4.30M"], items)
    assert payload["subject"] == "Digest: 5 action items (3 need action)"
    assert "1. [Off track] Revenue at Risk 19.1% vs 15.0% max" in payload["body"]
    assert "Tables lost $30.5K on $243.5K sales · Avg discount 29% vs 14% overall." in payload["body"]
    assert payload["to"].endswith("@example.com")


def test_slack_dry_run(no_network):
    items = build()
    payload = DryRunSlackSender().send("Digest", ["Sales: $4.30M"], items)
    assert payload["blocks"][0] == {"type": "header", "text": {"type": "plain_text", "text": "Digest"}}
    sections = [b["text"]["text"] for b in payload["blocks"][3:]]
    assert len(sections) == len(items)
    assert sections[1].startswith(":red_circle: *Tables lost $30.5K on $243.5K sales*")


def test_dry_run_with_no_actions(no_network):
    assert "every KPI is on track" in DryRunEmailSender().send("Digest", [], [])["body"]
    blocks = DryRunSlackSender().send("Digest", [], [])["blocks"]
    assert blocks[-1]["text"]["text"] == "Every KPI is on track."


def test_package_does_not_import_streamlit():
    code = ("import sys, super_store.actions, super_store.alerts, super_store.kpis; "
            "assert 'streamlit' not in sys.modules")
    subprocess.run([sys.executable, "-c", code], check=True)
