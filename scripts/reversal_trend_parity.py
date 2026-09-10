"""Print Reversal Trend signal timestamps for eyeballing against the user's
TradingView screenshots of the original (unported, closed-source) indicator.

Plan: docs/plan-step-13p-reversal-trend-pine-factor-and-strategy-2026-09-09.zh.md
section 4/5 -- "reversal_trend_parity.py <symbol> <1h|1D> <start> <end>
（打印信号日期时间，用来与用户提供的 TradingView 截图逐点比对，差异写进报告）".
This script only prints; it does not itself judge parity -- differences go in
the report once the coordinator/user compares this output against the
screenshots.

Usage::

    uv run python scripts/reversal_trend_parity.py SPY 1D 2025-01-01 2025-06-30
    uv run python scripts/reversal_trend_parity.py NVDA 1h 2025-01-01 2025-06-30

Fetches extra history before ``start`` (default 500 calendar days for 1D, 120
for 1h) so EMA200/ADX/RSI are already warmed up by the time the requested
window begins -- matching a TradingView chart loaded with a long history --
then prints only the signals whose bar timestamp falls inside [start, end].
Indicator parameters are always the script's defaults (``ReversalTrendParams()``);
this tool never tunes them.

1D bars come from the local SIP daily archive (``data/sip/daily``). 1h bars
come from ``data/bars/hourly/{year}.parquet`` (plan section A3); that archive
does not exist until ``scripts/build_hourly_bars.py`` has been run, so ``1h``
raises a clear error until then rather than silently falling back to daily.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

from open_composer.adapters.data.sip_parquet import load_sip_bars
from open_composer.research.pine_port.reversal_trend import (
    ReversalTrendParams,
    compute_reversal_trend,
)

_DEFAULT_LOOKBACK_DAYS = {"1D": 500, "1h": 120}
_SIGNAL_COLUMNS = ("f_bull", "f_bear", "f_recl", "f_recs")
_SIGNAL_LABELS = {
    "f_bull": "BULL (fBull)",
    "f_bear": "BEAR (fBear)",
    "f_recl": "RECL (fRecL, RSI recovery long)",
    "f_recs": "RECS (fRecS, RSI recovery short)",
}

HOURLY_BARS_ROOT = Path(__file__).resolve().parents[1] / "data" / "bars" / "hourly"


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("symbol", help="ticker, e.g. SPY")
    parser.add_argument("period", choices=["1h", "1D"], help="bar period")
    parser.add_argument("start", help="window start date, YYYY-MM-DD (inclusive)")
    parser.add_argument("end", help="window end date, YYYY-MM-DD (inclusive)")
    parser.add_argument(
        "--lookback-days",
        type=int,
        default=None,
        help=(
            "calendar days of history fetched before `start` to warm up "
            "EMA200/ADX (default: 500 for 1D, 120 for 1h)"
        ),
    )
    return parser.parse_args(argv)


def _load_daily(symbol: str, lookback_start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    return load_sip_bars(symbol, frequency="daily", start=lookback_start, end=end)


def _load_hourly(symbol: str, lookback_start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    if not HOURLY_BARS_ROOT.is_dir():
        raise SystemExit(
            f"{HOURLY_BARS_ROOT} does not exist yet -- run scripts/build_hourly_bars.py "
            "first (plan section A3 / Step 13-P step 3)."
        )
    parts = []
    for year in range(lookback_start.year, end.year + 1):
        path = HOURLY_BARS_ROOT / f"{year}.parquet"
        if not path.is_file():
            continue
        frame = pd.read_parquet(path)
        parts.append(frame[frame["symbol"] == symbol])
    if not parts or sum(len(p) for p in parts) == 0:
        raise SystemExit(f"no hourly bars found for {symbol} under {HOURLY_BARS_ROOT}")
    combined = pd.concat(parts, axis=0, ignore_index=True)
    combined["timestamp"] = pd.to_datetime(combined["timestamp"], utc=True)
    combined = combined[(combined["timestamp"] >= lookback_start) & (combined["timestamp"] <= end)]
    return combined.sort_values("timestamp").reset_index(drop=True)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    symbol = args.symbol.upper()
    start = pd.Timestamp(args.start, tz="UTC")
    end = pd.Timestamp(args.end, tz="UTC")
    if start > end:
        print(f"error: start {args.start} is after end {args.end}", file=sys.stderr)
        return 2

    lookback_days = args.lookback_days or _DEFAULT_LOOKBACK_DAYS[args.period]
    lookback_start = start - pd.Timedelta(days=lookback_days)

    bars = (
        _load_daily(symbol, lookback_start, end)
        if args.period == "1D"
        else _load_hourly(symbol, lookback_start, end)
    )
    if bars.empty:
        print(f"no bars for {symbol} in {lookback_start.date()}..{end.date()}", file=sys.stderr)
        return 1

    params = ReversalTrendParams()
    result = compute_reversal_trend(bars, params)
    window = result[(result["timestamp"] >= start) & (result["timestamp"] <= end)]

    print(f"Reversal Trend parity check: {symbol} {args.period} {args.start}..{args.end}")
    print(
        f"  source={'SIP daily archive' if args.period == '1D' else 'data/bars/hourly'} "
        f"lookback_start={lookback_start.date()} ({lookback_days}d warmup) "
        f"bars_fetched={len(bars)} bars_in_window={len(window)}"
    )
    print(f"  params: {params}")
    print()

    total = 0
    for column in _SIGNAL_COLUMNS:
        fired = window[window[column]]
        total += len(fired)
        print(f"{_SIGNAL_LABELS[column]}: {len(fired)} signal(s)")
        if fired.empty:
            print("    (none)")
        for _, row in fired.iterrows():
            ts = row["timestamp"]
            print(
                f"    {ts.isoformat()}  (date={ts.date()})  close={row['close']:.2f}  "
                f"rsi={row['rsi']:.1f}  adx={row['adx']:.1f}  "
                f"ema20={row['ema_fast']:.2f}  ema50={row['ema_mid']:.2f}"
            )
    print()
    print(f"total signals in window: {total}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
