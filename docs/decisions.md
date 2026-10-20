# Design decisions

Architecture notes and the reasoning behind them, for anyone recreating the project. Metric formulas
are in [metrics.md](metrics.md).

## Data

Source: Kaggle [`abbas829/global-superstore-sales-dataset`](https://www.kaggle.com/datasets/abbas829/global-superstore-sales-dataset),
file `Global Superstore.csv`, downloaded with `kagglehub` (no account needed). 51,290 order lines,
28 columns after loading, 2011-2014.

### Quirks and how they are handled

| Quirk | Evidence | Handling |
|---|---|---|
| <a id="dates"></a>**Order Date and Ship Date are corrupted** | Every row is the string `00:00.0` in both columns. | `data.load()` rebuilds `Order Week = Jan 1 of Year + (weeknum − 1) × 7 days` from the intact `Year` and `weeknum` (1-53) columns. Every date window, retention and RFM recency are therefore week-accurate, not day-accurate. Ship dates are unrecoverable and unused. |
| <a id="customers"></a>**Customer ID is per market** | 4,873 distinct `Customer ID`s but 795 distinct `Customer Name`s. The same person has a separate ID in each market they buy in. | Each ID is treated as its own customer (in `metrics.rfm` and `metrics.retention`). Merging by name would be a guess, since names are not guaranteed unique. Captions on the RFM view say so. |
| **Row ID is a surrogate key** | `Row ID` is unique on every row. | Duplicate checks ignore it (`df.duplicated(subset=df.columns.drop("Row ID"))`): 0 duplicates. |
| **`ji_lu-shu` is constant** | Value is `1` on every row (a "record count" column). | Dropped in the notebook. The app loads but never reads it. |
| `Market2` | Maps US and Canada to `North America`; other markets unchanged. | Unused; the dashboard uses `Market` (7 values). |
| `Sales` is whole dollars | `int64` in this upload. | No handling needed; `Profit` is a float. |

### Loading, validation and offline fallback

- `data.load()` downloads from Kaggle, validates (`validation.validate()`: required columns, dtypes,
  nulls, non-negative sales, discount in 0-1, plausible `Order Week` range) and writes a Parquet
  snapshot to `data/superstore.parquet` (gitignored).
- If Kaggle is unreachable it falls back to that snapshot. If there is no snapshot it raises
  `DataUnavailableError`; bad data raises `DataValidationError`. `app/dashboard.py` shows either as
  an `st.error` and stops.
- Provenance (`source`, `loaded_at`, latest week, rows) is attached as `df.attrs["load_info"]` and
  shown in the sidebar as "Data through ... · loaded ... from Kaggle/snapshot".

## Targets and owners are illustrative

The dataset has no targets or org chart, so both are placeholders, kept in `config/targets.toml`
(path overridable with `SUPER_STORE_CONFIG`) and loaded by `super_store.config.load_config()`.

| Target | Default | Rationale |
|---|---|---|
| Profit margin | 12% | Historical margin was 11.0% (2011), 11.5% (2012), 11.9% (2013), 11.7% (2014). Set just above, so it is a stretch but reachable. |
| Sales growth | 25% vs last year | Close to recent growth (2014 YTD: +26%). Also used for the profit target. |
| Avg discount | ≤ 15% | Just above the 14.0-14.3% average of 2013-2014; see the discount analysis below. |
| Retention | 80% | Between Dec 2013 (75.8%) and Dec 2014 (82.0%). |
| Revenue at risk | ≤ 15% | Below the observed ~19%, to flag it. |

Owner roles (`VP of Sales`, `CFO`, `Head of Customer Success`, `{market} Market Lead`,
`{category} Category Manager`) are role names, not people. The sidebar target inputs are a per-session
what-if; they do not write back to the config.

## Dashboard layout

**Inverted pyramid**: the most important information first, detail on demand.

1. **KPI cards** (top): value, change vs last year, 12-month sparkline, status badge, target, and a
   link to the drill-down dimension that explains it.
2. **Trends** (middle): monthly sales vs last year, rolling 3-month margin, profit gap by market,
   discount vs margin.
3. **Action items** (bottom): generated from the data, each with what, why, who and when. Top 3
   shown, the rest in an expander.
4. **Drill-down page**: any KPI by Market, Region, Category, Sub-Category, Segment, Ship Mode or RFM
   segment, with Market/Category filters and CSV export.

Chart rules (Altair, `app/charts.py`):

- **Bars and lines only, no pie charts.** Comparing lengths on a common baseline is more accurate
  than comparing angles, and bars sort.
- **No dual axes.** Discount vs margin is two side-by-side bar charts sharing the y (sub-category)
  axis (`charts.discount_vs_margin`, `alt.hconcat`), not one chart with two scales. Dual axes invite
  false correlations because the two scales are arbitrary.
- One status palette (green/yellow/red/gray) shared by cards, bars and action items. Target shown as a
  dashed red rule.

### Why a rolling 3-month margin

Monthly margin is noisy. In 2013-2014 it ranged from 8.8% to 14.4% and moved 1.8 points a month on
average, so a single month crossing the 12% target says little. The 3-month rolling margin ranged
10.7-13.1% and moved 0.75 points a month, and still shows a turn within a quarter. It is computed as rolling summed
profit / rolling summed sales (`metrics.rolling_margin`), so large months weigh more, matching how
the period margin is computed.

### Why profit gap in dollars by market

Margin % alone hides scale: a small market can miss the target by 5 points and matter less than a
large one missing by 1. `Gap = (margin − target) × sales` puts every market in the same unit
(dollars of profit above or below target), so the bars rank by business impact. The same number,
negated, is the impact used to rank market action items.

## Worked analysis: discounts and margin

All 51,290 lines, 2011-2014, bucketed by `Discount` with right-inclusive edges
(`pd.cut(Discount, [-0.001, 0, 0.10, 0.20, 0.30, 0.50, 1])`). Recomputed from `data.load()`.

| Discount band | Lines | % of lines | Sales | Profit | Margin |
|---|---|---|---|---|---|
| None (0%) | 29,009 | 56.6% | $6,992,734 | $1,770,695 | 25.3% |
| 1-10% | 4,679 | 9.1% | $1,962,633 | $338,189 | 17.2% |
| 11-20% | 6,274 | 12.2% | $1,757,296 | $173,255 | 9.9% |
| 21-30% | 967 | 1.9% | $382,540 | −$21,156 | −5.5% |
| 31-50% | 6,189 | 12.1% | $1,176,078 | −$380,945 | −32.4% |
| > 50% | 4,172 | 8.1% | $371,624 | −$412,582 | −111.0% |

Margin falls steadily with discount and turns negative above about 20%. Lines discounted more than
50% lose more than they sell for. This motivates the discount ceiling KPI and the discount vs margin
chart.

**Caveat: this is observational.** Discounts are not randomly assigned. They may be applied to
products that were already low-margin, to clear stock, or in markets with different cost bases. The
table shows association, not the margin a given order would have earned without the discount. A
causal claim would need a controlled price test or at least a comparison within product and market.

## Code layout

| Location | Role | Streamlit? |
|---|---|---|
| `src/super_store/data.py` | Download, rebuild dates, validate, snapshot fallback | No |
| `src/super_store/validation.py` | Data sanity checks | No |
| `src/super_store/metrics.py` | Windows, KPI formulas, retention, RFM, status | No |
| `src/super_store/kpis.py` | KPI assembly (`build_kpis`), breakdown tables | No |
| `src/super_store/actions.py` | Action items: what, why, who, when, ranking | No |
| `src/super_store/config.py` + `config/targets.toml` | Targets, owners, review cadence | No |
| `src/super_store/formatting.py` | Number, date and period labels | No |
| `src/super_store/alerts.py`, `scripts/weekly_digest.py` | Dry-run weekly digest (email/Slack) | No |
| `app/dashboard.py` | Entry point: page config, data load errors, sidebar, navigation | Yes |
| `app/common.py` | Cached data, sidebar controls, session-state glue | Yes |
| `app/summary.py`, `app/drilldown.py` | Pages | Yes |
| `app/charts.py` | Altair chart builders | No (Altair only) |
| `notebooks/01-eda.ipynb` | EDA, cleaning checks, RFM exploration | No |
| `tests/`, `.github/workflows/ci.yml` | pytest + ruff, run on push and PR | No |

**Why the split:** everything under `src/super_store` is pure pandas and can be imported by the
notebook, the digest script and tests without a Streamlit runtime. `app/` only reads session state,
caches and renders. A recreation can swap the UI layer without touching the logic.

### Caching

- `common.data()` is `@st.cache_data` with no TTL: the dataset is a static 2011-2014 snapshot.
  Filters (market, category, period) are applied to the cached frame on every rerun; they are cheap.
- The expensive part is customer health: retention and a full RFM table for each of 12 months.
  `common.customer_health(as_of)` and `common.rfm_table(as_of)` are cached per as-of month with
  bounded `max_entries` (about 24 as-of options, plus the prior year for customer health).

### Hot reload

Run with `PYTHONPATH=src uv run streamlit run app/dashboard.py`. Streamlit's file watcher only watches
modules in the main script's folder (`app/`) or on `PYTHONPATH`. The package is installed editable
(`-e .`, via a `.pth` file), which is not on `PYTHONPATH`, so without the variable edits to
`src/super_store/` need a server restart.

## Alerting is dry-run only

`scripts/weekly_digest.py --as-of 2014-12 --period YTD` builds the same action items as the dashboard
and passes them to `DryRunEmailSender` and `DryRunSlackSender` (`src/super_store/alerts.py`).

- **Nothing is ever sent.** The senders build the payload (email subject/body, Slack Block Kit
  JSON), log it, and return it. They make no network calls and read no credentials.
- **Where a real sender plugs in:** each sender's `send()` method. Replace the log call with
  `smtplib.SMTP(...).send_message()` or an HTTPS POST to a Slack incoming webhook, with secrets from
  the environment or a secrets manager. Keep `build()` as is so the payload stays testable.
- Scheduling (cron, GitHub Actions `schedule`) is not set up.

## Deployment

- **Streamlit Community Cloud**, main file `app/dashboard.py`.
- Cloud installs from `requirements.txt`, exported from the lockfile so versions match local:
  `uv export --no-dev --no-hashes --format requirements-txt -o requirements.txt`. The export includes
  `-e .`, which installs the `super_store` package from the repo root (so `from super_store import ...`
  works without `PYTHONPATH`). Re-export after changing dependencies.
- `pyproject.toml` has `requires-python = ">=3.12"`; pick 3.12 or later in the app's advanced
  settings (CI tests 3.12 and 3.14; `.python-version` is 3.14 locally).
- The dataset downloads from Kaggle on the first cold start. `data/` is gitignored, so the Parquet
  fallback snapshot only exists after a successful download on that instance.
