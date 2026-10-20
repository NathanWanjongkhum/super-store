"""Print the weekly action-item digest and "send" it via the dry-run email/Slack senders.

Nothing is sent: see super_store.alerts. Usage:
    PYTHONPATH=src python scripts/weekly_digest.py --as-of 2014-12 [--period YTD]
"""

import argparse
import json
import logging

import pandas as pd

from super_store import actions, metrics
from super_store.alerts import DryRunEmailSender, DryRunSlackSender
from super_store.config import load_config
from super_store.data import load
from super_store.formatting import SHORT_PERIOD, change, fmt, period_caption
from super_store.kpis import breakdown, build_kpis

PERIOD_BY_SHORT = {short: name for name, short in SHORT_PERIOD.items()}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--as-of", type=pd.Period, help="as-of month, YYYY-MM (default: latest)")
    parser.add_argument("--period", default="YTD", choices=list(PERIOD_BY_SHORT),
                        help="reporting period (default: YTD)")
    parser.add_argument("--config", help="path to targets TOML (default: $SUPER_STORE_CONFIG "
                                         "or config/targets.toml)")
    parser.add_argument("--channel", choices=["email", "slack", "both"], default="both")
    parser.add_argument("-v", "--verbose", action="store_true", help="log the full payloads")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING,
                        format="%(levelname)s %(name)s: %(message)s")
    config = load_config(args.config)
    df = load()
    last = df["Order Week"].dt.to_period("M").max()
    as_of = pd.Period(args.as_of or last, "M")
    if not isinstance(as_of, pd.Period):  # pd.Period can return NaT
        raise SystemExit(f"--as-of must be a month like 2014-12, got {args.as_of!r}")
    period = PERIOD_BY_SHORT[args.period]
    w = metrics.period_window(as_of, period)

    kpis = build_kpis(df, as_of, period, config.targets)
    margin = config.targets.profit_margin
    items = actions.build_actions(
        kpis, breakdown(df, "Market", w, margin), breakdown(df, "Sub-Category", w, margin),
        actions.category_map(df), config.targets, config.owners,
        actions.review_text(w.end, config.review))

    title = f"Superstore weekly digest, {period_caption(w.start, w.end, period)}"
    summary = [f"{k.name}: {fmt(k.value, k.kind)} ({change(k.value, k.last_year, k.kind)} YoY)"
               for k in kpis]
    senders = {"email": DryRunEmailSender(), "slack": DryRunSlackSender()}
    channels = list(senders) if args.channel == "both" else [args.channel]
    for name in channels:
        payload = senders[name].send(title, summary, items)
        print(f"=== DRY RUN: {name} (not sent) ===")
        if name == "email":
            print(f"To: {payload['to']}\nSubject: {payload['subject']}\n\n{payload['body']}\n")
        else:
            print(json.dumps(payload, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
