"""Daily long/short screening through the native next-open equity book."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from collections.abc import Callable, Mapping
from datetime import time, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter
from uuid import uuid4

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from open_composer.adapters.data.sip_parquet import MARKET_DATA, OOS_START
from open_composer.lab.accounting import turnover_cost
from open_composer.lab.ledger import TrialLedger
from open_composer.lab.metrics import return_metrics
from open_composer.market_sessions import NEW_YORK, next_us_equity_session
from open_composer.research.equity_book.backtest import BookConfig, run_book, signal_positions
from open_composer.research.equity_book.borrow import short_eligible
from open_composer.research.equity_book.costs import borrow_bp_per_year
from open_composer.research.equity_book.panel import PricePanel
from open_composer.research.features.panel import _connect
from open_composer.research.features.security_type import STOCK_TYPES

UNIVERSE = MARKET_DATA / "derived/daily-us-stock-universe.parquet"
WINDOWS = {
    "2016-2023": ("2016-01-04", "2023-12-31"),
    "2024-2025 test": ("2024-01-01", "2025-12-31"),
    "2026-01..08": ("2026-01-01", "2026-08-31"),
    "2026-09+ OOS evaluation only": (OOS_START.isoformat(), None),
}
FIELDS = [
    "symbol", "known_at", "close", "dollar_volume", "median_dollar_volume_20",
    "listing_date", "reverse_split_252", "security_type", "security_type_known_at",
]
Decide = Callable[[pd.Timestamp, pd.DataFrame], Mapping[str, float] | None]


class ScreenData:
    """Load marks once, with completed feature slices paged by calendar month."""

    def __init__(self, path: Path = UNIVERSE, *, stock_only: bool = True) -> None:
        self.path = path
        self.stock_only = stock_only
        with _connect("300MB") as con:
            sql = f"read_parquet({path.as_posix()!r})"
            dates = pd.DatetimeIndex(con.sql(f"""
                SELECT DISTINCT trade_date FROM {sql} ORDER BY 1
            """).fetchnumpy()["trade_date"])
            ids = pd.Index(con.sql(
                f"SELECT DISTINCT security_id FROM {sql} ORDER BY 1"
            ).fetchnumpy()["security_id"])
        shape = (len(dates), len(ids))
        opens = np.full(shape, np.nan, dtype="float32")
        closes = np.full(shape, np.nan, dtype="float32")
        self.delists = defaultdict(list)
        parquet = pq.ParquetFile(path)
        for batch in parquet.iter_batches(
            batch_size=131072,
            columns=["trade_date", "session", "security_id", "adjusted_open", "adjusted_close", "is_member"],
        ):
            rows = batch.to_pandas()
            active = rows.loc[rows.is_member]
            index = dates.get_indexer(active.trade_date), ids.get_indexer(active.security_id)
            opens[index] = active.adjusted_open
            closes[index] = active.adjusted_close
            for row in rows.loc[~rows.is_member & (rows.session <= dates[-1])].itertuples():
                self.delists[row.session].append(row.security_id)
        self.panel = PricePanel(dates, ids, opens, closes)
        self._month = None

    def after_close(self, date: pd.Timestamp) -> pd.DataFrame:
        month = date.to_period("M")
        if month != self._month:
            filters = [
                ("trade_date", ">=", month.start_time),
                ("trade_date", "<", (month + 1).start_time),
                ("is_member", "=", True),
            ]
            if self.stock_only:
                filters.append(("security_type", "in", STOCK_TYPES))
            self._rows = pd.read_parquet(
                self.path, columns=["trade_date", "security_id", *FIELDS], filters=filters,
            ).set_index(["trade_date", "security_id"])
            self._month = month
        f = self._rows.loc[date:date].droplevel("trade_date").copy()
        decision_at = pd.Timestamp.combine(next_us_equity_session(date.date()), time(9, 30)).tz_localize(
            NEW_YORK
        )
        assert (f["known_at"] < decision_at).all()
        assert (f["security_type_known_at"].dropna() < decision_at).all()
        f["adv_rank"] = f["median_dollar_volume_20"].rank(ascending=False, method="min")
        f["short_eligible"] = short_eligible(f.rename(columns={"close": "price"}))
        return f


def run_daily_screen(
    data: ScreenData, decide: Decide, *, name: str, ledger: TrialLedger,
    batch: str, frequency: str = "D", calibration: bool = False, oos: bool = False,
) -> dict:
    """Pass completed daily observations keyed by security_id to a pre-open decision.

    The date argument is the observation session. A deterministic callback returns
    complete signed target weights for the following session's open,
    or None to skip that rebalance. The callback can use short_eligible to
    apply the borrow proxy. The book charges borrow on every open short.
    The windows are reports from one continuous account per cost setting.
    Development runs stop before 2026-09-01; pass oos=True only for a frozen
    candidate's single out-of-sample evaluation (plan section I).
    """
    def target(date, state):
        rows = data.after_close(date)
        weights = decide(date, rows)
        if weights is None:
            return None
        if set(weights).difference(rows.index):
            raise ValueError(f"Target outside the {date.date()} close universe")
        return weights

    dates = data.panel.dates
    signals = [dates[i] for i in signal_positions(dates, frequency)
               if next_us_equity_session(dates[i].date()) == (dates[i + 1].date() if i + 1 < len(dates) else None)]
    if not oos:
        signals = [d for d in signals if d.date() < OOS_START]
    results = {}
    for bp in (10, 20):
        trial = f"{batch}-{name}-{bp}-{uuid4().hex[:8]}"
        ledger.start(
            trial, batch=batch, candidate=name, counts_as_trial=not calibration,
            parameters={
                "bp_per_side": bp, "borrow_bp_per_year": borrow_bp_per_year(True),
                "frequency": frequency, "windows": WINDOWS, "universe": str(data.path),
                "stock_only": data.stock_only,
            },
            note=("Fixed calibration rule; assumed short availability; OOS evaluation only"
                  if calibration else "OOS evaluation only"),
        )
        started = perf_counter()
        fills = defaultdict(int)
        winners = defaultdict(list)
        basis = {}

        def record(trades, state, costs):
            fills[state.date] += len(trades)
            for s, value, price in zip(trades.symbol, trades.dollar_trade, trades.price, strict=True):
                before = state.holdings.get(s, 0.0) / price
                change = value / price
                after = before + change
                old_basis = basis.get(s, price)
                fee = turnover_cost(price, bp)
                if before * change < 0:
                    closed = min(abs(before), abs(change))
                    pnl = closed * (np.sign(before) * (price - old_basis) - fee)
                    if pnl > 0:
                        winners[state.date].append(float(pnl))
                if abs(after) < 1e-12:
                    basis.pop(s, None)
                elif before * after <= 0:
                    basis[s] = price + np.sign(after) * fee
                elif before * change > 0:
                    basis[s] = (
                        abs(before) * old_basis + abs(change) * (price + np.sign(after) * fee)
                    ) / abs(after)

        def summarize(daily):
            m = return_metrics(daily.net, 1.0)
            gains = [profit for date in daily.index for profit in winners[date]]
            return {
                "after_cost_return": m["total_return"],
                "drawdown": m["max_drawdown"],
                "turnover": float(daily.turnover.sum()),
                "trade_count": sum(fills[date] for date in daily.index),
                "top_5_trade_share": sum(sorted(gains)[-5:]) / sum(gains) if gains else None,
            }

        try:
            book = run_book(data.panel, target, BookConfig(
                freq=frequency, signal_dates=signals, cost_bp_per_side=bp,
                end=None if oos else str(OOS_START - timedelta(days=1)),
                borrow_bp_per_year=borrow_bp_per_year(True),
                snapshots=False, delist_dates=data.delists, require_observed_open=True,
                trade_observer=record,
            ))
            daily = book.daily
            result = {
                "seconds": perf_counter() - started,
                "by_year": {str(y): summarize(f) for y, f in daily.groupby(daily.index.year)},
                "by_window": {label: summarize(daily.loc[lo:hi]) for label, (lo, hi) in WINDOWS.items()
                              if len(daily.loc[lo:hi])},
                "synthetic_exits": book.info["delist_exits"],
                "last_session": str(daily.index[-1].date()),
            }
            evidence = ledger.path.parent / f"{trial}.json"
            evidence.write_text(json.dumps(result, indent=2, allow_nan=False), encoding="utf-8")
        except Exception as exc:
            ledger.finish(trial, status="failed", evidence=[], note=f"{type(exc).__name__}: {exc}")
            raise
        ledger.finish(trial, status="complete", evidence=[str(evidence)])
        results[bp] = result
    return results


def calibrate(universe: Path, ledger: TrialLedger, *, stock_only: bool = True) -> dict:
    started = perf_counter()
    data = ScreenData(universe, stock_only=stock_only)
    load_seconds = perf_counter() - started
    panel = data.panel
    month_ends = signal_positions(panel.dates, "M")
    months = {panel.dates[p]: m for m, p in enumerate(month_ends)}

    def deciles(date, rows, *, momentum):
        month = months[date]
        lag = 12 if momentum else 1
        if month < lag:
            return None
        cols = panel.symbols.get_indexer(rows.index)
        recent = month - 1 if momentum else month
        returns = panel.close[month_ends[recent], cols] / panel.close[month_ends[month - lag], cols] - 1
        scores = pd.Series(returns if momentum else -returns, index=rows.index).dropna()
        scores = scores.sort_values(kind="stable")
        n = len(scores) // 10
        if n == 0:
            return None
        longs, shorts = scores.index[-n:], scores.index[:n]
        return dict.fromkeys(longs, 0.5 / n) | dict.fromkeys(shorts, -0.5 / n)

    batch = "calibration-" + uuid4().hex[:8]
    runs = {}
    for name, momentum in (("momentum-12-1", True), ("reversal-1", False)):
        runs[name] = run_daily_screen(
            data, lambda d, rows: deciles(d, rows, momentum=momentum),
            name=name, ledger=ledger, batch=batch, frequency="M", calibration=True, oos=True,
        )
    return {
        "stock_only": stock_only, "load_seconds": load_seconds,
        "seconds": perf_counter() - started, "runs": runs,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["build", "calibrate"])
    parser.add_argument("--universe", type=Path, default=UNIVERSE)
    parser.add_argument("--all-securities", action="store_true", help="Calibrate the full SIP universe")
    args = parser.parse_args()
    if args.action == "build":
        from open_composer.research.features.universe import build_daily_sip_universe

        args.universe.parent.mkdir(parents=True, exist_ok=True)
        with TemporaryDirectory(dir=args.universe.parent) as stage:
            report = build_daily_sip_universe(Path(stage), args.universe)
    else:
        report = calibrate(
            args.universe, TrialLedger(args.universe.parent / "daily-screen/trials.jsonl"),
            stock_only=not args.all_securities,
        )
    print(json.dumps(report, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
