# Metric dictionary

Every number on the dashboard, with the exact formula as implemented. Use this to recreate the
metrics or to check a reimplementation against the reference values.

- Formulas live in `src/super_store/metrics.py` (pure pandas, no Streamlit). KPI assembly (targets,
  last-year values, sparklines) is in `src/super_store/kpis.py` (`build_kpis`, `breakdown`).
- Default targets and owner roles are in `config/targets.toml`, loaded by
  `super_store.config.load_config()`. The sidebar "Targets" expander overrides them per session.
- Percentages are stored as 0-100 (not 0-1). `Discount` in the source is 0-1 and is multiplied by 100.
- Reference values are for **as of Dec 2014, period Year to date** unless noted.

## Common building blocks

| Name | Implementation | Rule |
|---|---|---|
| Order date | `data.load()` → column `Order Week` | `Jan 1 of Year + (weeknum - 1) × 7 days`. The only usable date; see [decisions.md](decisions.md#dates). |
| As-of month | sidebar `As of` | Any month from Dec 2012 to Dec 2014. Starts 24 months in so retention has two full 12-month windows. |
| Period window | `metrics.period_window(as_of, period)` → `Window(start, end)` | `end` = last day of the as-of month. `start` = first day of the as-of month (MTD), quarter (QTD), year (YTD), or of the month 11 months earlier (T12M). |
| Last-year window | `Window.prior_year()` | Same window shifted back 1 year (`pd.DateOffset(years=1)` on both ends). |
| Window filter | `metrics.in_window(df, w)` | `Order Week` between `start` and `end`, both inclusive. |
| Monthly series | `metrics.monthly(df)` | Group by calendar month of `Order Week`: `sum(Sales)`, `sum(Profit)`, `mean(Discount) × 100`, margin = profit / sales × 100. |
| Sparkline | `kpis.build_kpis` | Last 12 monthly values ending at the as-of month (sales KPIs from `monthly`, customer KPIs from `kpis.customer_health`). Independent of the period selector. |

**Time windows differ by KPI type.** The four sales KPIs follow the period selector. The two
customer KPIs never do: retention compares two fixed 12-month windows ending at the as-of date, and
revenue at risk scores all order history up to the as-of date.

## KPIs

### Sales

| | |
|---|---|
| Definition | Total order-line revenue in the period. |
| Formula | `sum(Sales)` over `in_window(df, w)` |
| Implemented in | `metrics.sales_kpis` |
| Source columns | `Sales` (whole dollars in this upload), `Order Week` |
| Time window | Period selector |
| Default target | Last year's sales for the same window × (1 + `targets.sales_growth` / 100); `sales_growth = 25.0` |
| Direction | Higher is better |
| Owner role | VP of Sales |
| Drill-down | Market |
| Reference value | $4,300,041 vs target $4,257,325 (LY $3,405,860 × 1.25) → green |

### Profit

| | |
|---|---|
| Definition | Total order-line profit in the period. |
| Formula | `sum(Profit)` over `in_window(df, w)` |
| Implemented in | `metrics.sales_kpis` |
| Source columns | `Profit`, `Order Week` |
| Time window | Period selector |
| Default target | Last year's profit for the same window × (1 + `targets.sales_growth` / 100). Profit uses the **sales** growth target. |
| Direction | Higher is better |
| Owner role | CFO |
| Drill-down | Category |
| Reference value | $504,166 vs target $508,669 → yellow (99% of target) |

### Profit Margin

| | |
|---|---|
| Definition | Profit as a share of sales. |
| Formula | `sum(Profit) / sum(Sales) × 100` (ratio of sums, not the mean of line margins); `NaN` if sales = 0 |
| Implemented in | `metrics.sales_kpis` |
| Source columns | `Profit`, `Sales`, `Order Week` |
| Time window | Period selector |
| Default target | `targets.profit_margin = 12.0` % |
| Direction | Higher is better |
| Owner role | CFO |
| Drill-down | Sub-Category |
| Reference value | 11.7% (LY 11.9%) → yellow |

### Avg Discount

| | |
|---|---|
| Definition | Average discount per order line. |
| Formula | `mean(Discount) × 100`, unweighted (each line counts once, regardless of its sales) |
| Implemented in | `metrics.sales_kpis` |
| Source columns | `Discount` (0-1), `Order Week` |
| Time window | Period selector |
| Default target | `targets.max_discount = 15.0` % (a ceiling) |
| Direction | Lower is better |
| Owner role | VP of Sales |
| Drill-down | Sub-Category |
| Reference value | 14.3% (LY 14.0%) → green |

### Customer Retention

| | |
|---|---|
| Definition | Share of customers who ordered in the 12 months before last year and ordered again in the last 12 months. |
| Formula | `prior` = customer IDs with an order in `(end − 2y, end − 1y]`; `current` = IDs with an order in `(end − 1y, end]`; `len(prior ∩ current) / len(prior) × 100`; `NaN` if `prior` is empty |
| Implemented in | `metrics.retention(df, end)`, `end` = last day of the as-of month |
| Source columns | `Customer ID`, `Order Week` |
| Time window | Always 12 + 12 months to the as-of date; ignores the period selector |
| Default target | `targets.retention = 80.0` % |
| Direction | Higher is better |
| Owner role | Head of Customer Success |
| Drill-down | RFM Segment |
| Reference value | 82.0% (Dec 2013: 75.8%) → green |

`Customer ID` is per market, so a person who buys in two markets is two customers here (see
[decisions.md](decisions.md#customers)).

### Revenue at Risk

| | |
|---|---|
| Definition | Share of customers' lifetime sales held by lapsed frequent buyers (RFM segments **At Risk** and **Can't Lose**). |
| Formula | `sum(Monetary where Segment in AT_RISK_SEGMENTS) / sum(Monetary) × 100` over the RFM table |
| Implemented in | `metrics.revenue_at_risk(metrics.rfm(df, end))`; `metrics.AT_RISK_SEGMENTS = ["At Risk", "Can't Lose"]` |
| Source columns | `Customer ID`, `Order ID`, `Sales`, `Order Week` |
| Time window | All orders up to the as-of date (lifetime), scored relative to the as-of date; ignores the period selector |
| Default target | `targets.max_revenue_at_risk = 15.0` % (a ceiling) |
| Direction | Lower is better |
| Owner role | Head of Customer Success |
| Drill-down | RFM Segment |
| Reference value | 19.1% (Dec 2013: 18.7%) → red |

## Derived measures

### Rolling 3-month margin (summary trend chart)

| | |
|---|---|
| Formula | `rolling_sum(Profit, 3) / rolling_sum(Sales, 3) × 100` over the monthly series (ratio of rolling sums, not a rolling mean of monthly margins) |
| Implemented in | `metrics.rolling_margin(metrics.monthly(df), window=3)` |
| Shown | The 12 months ending at the as-of month, against the margin target line |
| Time window | Fixed 12 months; ignores the period selector |
| Reference values | Jan-Dec 2014: 12.2, 11.7, 12.2, 11.4, 12.0, 11.1, 11.6, 11.2, 12.3, 13.1, 13.0, 11.4 |

### Profit gap vs target (summary chart, by market)

| | |
|---|---|
| Formula | `Gap = (Profit Margin − target margin) / 100 × Sales`, i.e. `Profit − target × Sales / 100`, per market |
| Implemented in | `charts.profit_gap` (`app/charts.py`) over `breakdown(df, "Market", w, target)` |
| Time window | Period selector |
| Bar color | `metrics.status(Profit Margin, target margin)` per market |
| Related | A red market becomes an action item whose impact is `−Gap` (`actions.market_action`). |

### Breakdown table (drill-down page)

`kpis.breakdown(df, dim, w, margin_target)`, grouped by `dim`, sorted by sales descending:

| Column | Formula |
|---|---|
| Sales | `sum(Sales)` in `w` |
| % of Sales | group sales / total sales in `w` × 100 (after the page's Market/Category filters) |
| Growth % | `(sales in w / sales in w.prior_year() − 1) × 100`; `NaN` if the group had no sales last year |
| Profit | `sum(Profit)` in `w` |
| Profit Margin | `sum(Profit) / sum(Sales) × 100` |
| Avg Discount | `mean(Discount) × 100` |
| Status | `metrics.status(Profit Margin, margin_target)` (colors the bars; not exported) |

The **Download CSV** button exports the same columns, rounded (dollars to whole numbers,
percentages to 1 decimal), as `superstore_<dimension>_<period>_<as-of>.csv`, e.g.
`superstore_sub-category_ytd_2014-12.csv`. The RFM table exports as
`superstore_rfm-segment_<as-of>.csv` (no period: RFM ignores it).

### RFM scores

`metrics.rfm(df, end)`: one row per `Customer ID`, using orders with `Order Week <= end`.

| Score | Raw measure | Scoring |
|---|---|---|
| R (recency) | `Recency` = days from the customer's last `Order Week` to `end + 1 day` | Quintile of `Recency.rank(method="first")`; **5 = most recent** (labels reversed) |
| F (frequency) | `Frequency` = count of distinct `Order ID` | Quintile of `rank(method="first")`; 5 = most orders |
| M (monetary) | `Monetary` = `sum(Sales)` | Quintile of `rank(method="first")`; 5 = highest sales |

- `pd.qcut(..., 5)` on the rank, not the raw value: ranking first breaks ties (many customers share
  the same frequency) so every quintile has the same number of customers.
- Scores are relative to the customer base at `end`, so a customer's scores change with the as-of month.
- Segments use **R and F only**. M is computed but not used for segmenting; `Monetary` is used for
  revenue at risk and lifetime sales.
- The notebook uses `snapshot = max(Order Week) + 7 days`; the app uses `end + 1 day`. Recency values
  differ by a constant, scores do not.

### RFM segments

`metrics.SEGMENT_MAP`: regexes on the two-character string `f"{R}{F}"`, applied with
`Series.replace(SEGMENT_MAP, regex=True)`. The 10 segments cover all 25 R×F cells exactly once.

| Segment | R | F | Regex | Customers (Dec 2014) |
|---|---|---|---|---|
| Champions | 5 | 4-5 | `5[4-5]` | 572 |
| Loyal Customers | 3-4 | 4-5 | `[3-4][4-5]` | 980 |
| Potential Loyalists | 4-5 | 2-3 | `[4-5][2-3]` | 698 |
| New Customers | 5 | 1 | `51` | 67 |
| Promising | 4 | 1 | `41` | 88 |
| Need Attention | 3 | 3 | `33` | 222 |
| About to Sleep | 3 | 1-2 | `3[1-2]` | 297 |
| At Risk | 1-2 | 3-4 | `[1-2][3-4]` | 590 |
| Can't Lose | 1-2 | 5 | `[1-2]5` | 151 |
| Hibernating | 1-2 | 1-2 | `[1-2][1-2]` | 1,208 |

Total 4,873 customer IDs. **At Risk** and **Can't Lose** (frequent buyers who have gone quiet) feed
Revenue at Risk.

The drill-down segment table is `segment_summary()` (`app/common.py`): per segment, customer count,
mean `Recency` (days), mean `Frequency` (orders), `sum(Monetary)` (lifetime sales), and each
segment's % of customers and % of sales.

### Status thresholds

`metrics.status(actual, target, higher_is_better=True)`:

| Status | Label | Rule |
|---|---|---|
| gray | No target | `target` is None/NaN, `actual` is NaN, or `actual == 0` |
| green | On track | `ratio >= 1` |
| yellow | Monitor | `0.9 <= ratio < 1` |
| red | Off track | `ratio < 0.9` |

`ratio = actual / target` when higher is better, `target / actual` when lower is better.

- "Within 10%" is a ratio, not percentage points. For a 12% margin target, yellow is 10.8-12%.
  For a 15% ceiling, yellow is 15-16.7% (`15 / 0.9`), not 15-16.5%.
- KPI cards, breakdown bars and the profit-gap bars all use this function. Breakdown and profit-gap
  rows are always scored against the **margin** target.
- Labels and colors are in `app/common.py` (`STATUS_LABELS`, `STATUS_COLORS`).

### Action items (how metrics become actions)

`actions.build_actions`, ranked red first, then by estimated dollar impact:

| Trigger | Impact used for ranking | Owner |
|---|---|---|
| KPI status red or yellow | Money KPI: target − value. % KPI: points off target / 100 × period sales | `[owners.kpi]` role |
| Market with red margin status | `(target margin − margin) / 100 × market sales` | `"{market} Market Lead"` |
| Sub-category with negative profit | `−Profit` | `"{category} Category Manager"` |

Review date: the next `[review] weekday` (default Monday) after the window end.
