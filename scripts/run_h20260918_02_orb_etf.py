"""H-20260918-02, ORB-ETF leg only: opening-range breakout on QQQ/TQQQ/SPY/SPXL.

Card: ``reports/research/hypotheses/H-20260918-02-intraday-orb-and-intraday-momentum-etf.md``
(section "ORB-ETF" of the design). The SPY intraday-momentum noise-band leg of
that same card is out of scope here -- another task covers it.

Rule (the card's, restated literally in the task brief this script was written
against)
-------------------------------------------------------------------------------
* Opening candle = the five 1-minute bars 09:30-09:34 ET (open of 09:30, high/low
  across 09:30-09:34 inclusive, close of 09:34).
* Direction = sign(close - open). Skip (doji) if
  ``abs(close - open) <= 0.05 * (high - low)``, or if any of the five opening
  bars or the 09:35 entry bar is missing.
* Entry at the open of the 09:35 bar, in that direction (not a stop-order
  breakout -- the card is explicit that this is a "walk in" entry).
* Initial stop at the opposite extreme of the opening candle. A later bar's
  low (long) / high (short) touching the stop exits there; a "1 bp worse fill"
  variant is reported alongside.
* Target at 10R; a bar's high (long) / low (short) reaching it exits there.
* Otherwise exit at the close of the session's last minute bar (the real
  exchange close via ``open_composer.market_calendar``, so half days exit at
  13:00 ET).
* Sizing: risk 1% of current equity per trade (shares = 0.01 * equity / R),
  notional capped at ``leverage * equity``; leverage in {1, 2, 4} as separate
  rows; equity compounds across days, one independent book per symbol.
* Costs: four per-side bp levels {0.5, 1, 2, 5} on notional; shorts additionally
  pay a 0.3%/year borrow fee prorated by holding minutes.
* Within a single bar, if both the stop and the target are touched, the stop is
  assumed to fire first (conservative tie-break; documented in the report).

Data-location finding that changes the card's own assumption
--------------------------------------------------------------
The card assumed QQQ/TQQQ minute bars exist only from 2023-01, so the
2016-01->2023-02 in-sample check ("QQQ 33% / TQQQ 48% annualized, Sharpe
1.13/1.19, -22%/-28% max drawdown") would only be checkable on SPY. A shard
scan (see ``_SHARD_BY_SOURCE`` below) found QQQ, TQQQ and SPXL *all* present in
``data/sip-hist/minute`` back to 2016-01, at fixed shard numbers stable across
every year checked (2016, 2019, 2022) and every month-dir checked in
``data/sip/minute`` (2023, 2024, 2026). The in-sample check therefore runs on
all four symbols, not just SPY.

Shard evidence (verified by reading each file's ``symbol`` column, not just
footer min/max stats):

======  ==========================  ==========================
symbol  data/sip/minute (2023-2026) data/sip-hist/minute (2016-2022)
======  ==========================  ==========================
SPY     shard-0927                  shard-0927
QQQ     shard-0811                  shard-0812
TQQQ    shard-0986                  shard-0987
SPXL    shard-0926                  shard-0927 (same file as SPY)
======  ==========================  ==========================

Both archives use a month-sharded layout (``{root}/{year}/{month:02d}/
shard-NNNN.parquet``); a whole *year* of one symbol is read with a single
DuckDB query against the glob ``{root}/{year}/*/shard-NNNN.parquet`` -- this
expands to at most 12 files (one per month), never the ~1118-shard/month full
archive glob the card warns is a timeout.

Stages (each resumable from ``reports/research/iterations/h20260918_02_orb_etf/
cache/``)
-------------------------------------------------------------------------------
``load``      per symbol, per calendar year: one DuckDB query against that
              year's fixed shard, minute bars grouped into per-day records for
              all three entry anchors (09:35 real, 10:05 and 10:35 shift
              controls), storing both the long- and the short-outcome so later
              stages can resimulate any direction (real, random, forced-long)
              without touching minute data again. Cached per symbol.
``backtest``  benchmark buy-and-hold stats, the leverage x cost x stop-fill
              grid for all three anchors, and the random-direction /
              long-only-random-day placebo controls. Pure arithmetic over the
              cached day records -- no data re-read.
``report``    ``summary.json`` and the Chinese ``report.md``.

Usage::

    ./scripts/run_capped.sh --mem 1.2G -- \\
        uv run python scripts/run_h20260918_02_orb_etf.py --stage all
"""

from __future__ import annotations

import argparse
import glob as glob_module
import json
import math
import sys
import time
from datetime import date, datetime
from datetime import time as dt_time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import duckdb  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from open_composer.adapters.data.sip_parquet import load_sip_bars  # noqa: E402
from open_composer.market_calendar import (  # noqa: E402
    NEW_YORK,
    us_equity_session_close,
    us_equity_session_dates,
)
from open_composer.research.kernel.mechanism_eval import annualized_cagr, max_drawdown  # noqa: E402

ITERATION_ID = "h20260918_02_orb_etf"
OUT_DIR = ROOT / "reports" / "research" / "iterations" / ITERATION_ID
CACHE_DIR = OUT_DIR / "cache"
DAYS_DIR = CACHE_DIR / "days"
SUMMARY_PATH = OUT_DIR / "summary.json"
REPORT_PATH = OUT_DIR / "report.md"
TRADE_LOG_PATH = CACHE_DIR / "trade_log_primary.parquet"

SYMBOLS: tuple[str, ...] = ("QQQ", "TQQQ", "SPY", "SPXL")
BUILTIN_LEVERAGE: dict[str, int] = {"SPY": 1, "QQQ": 1, "TQQQ": 3, "SPXL": 3}

#: See the module docstring's shard-evidence table. Numbers are the 4-digit
#: shard index (no zero-padding needed here, applied at path-build time).
_SHARD_BY_SOURCE: dict[str, dict[str, Any]] = {
    "sip": {
        "root": ROOT / "data" / "sip" / "minute",
        "years": range(2023, 2027),
        "shards": {"SPY": 927, "QQQ": 811, "TQQQ": 986, "SPXL": 926},
    },
    "sip_hist": {
        "root": ROOT / "data" / "sip-hist" / "minute",
        "years": range(2016, 2023),
        "shards": {"SPY": 927, "QQQ": 812, "TQQQ": 987, "SPXL": 927},
    },
}
ALL_YEARS: tuple[int, ...] = tuple(range(2016, 2027))

IN_SAMPLE_START = date(2016, 1, 4)
IN_SAMPLE_END = date(2023, 2, 28)
OOS_START = date(2024, 1, 2)
OOS_END = date(2026, 9, 17)
WINDOWS: dict[str, tuple[date, date]] = {
    "in_sample": (IN_SAMPLE_START, IN_SAMPLE_END),
    "out_of_sample": (OOS_START, OOS_END),
}
WINDOW_LABELS_ZH = {"in_sample": "样本内（复现检查）", "out_of_sample": "样本外（结论以此为准）"}

#: The published in-sample comparison targets (Zarattini/Barbon/Aziz 2025 ETF
#: ORB, 2016-01->2023-02); SPY and SPXL have no published number, only QQQ and
#: TQQQ do -- see the data-location finding in the module docstring.
PUBLISHED_IN_SAMPLE: dict[str, dict[str, float]] = {
    "QQQ": {"annualized_return": 0.33, "sharpe": 1.13, "max_drawdown": -0.22},
    "TQQQ": {"annualized_return": 0.48, "sharpe": 1.19, "max_drawdown": -0.28},
}

SPMO_REF_START = date(2024, 1, 8)
SPMO_REF_END = date(2026, 9, 16)
SPMO_REF_ANN = 0.347
SPMO_REF_MDD = -0.201

ANCHORS: dict[str, dt_time] = {
    "orb_0935": dt_time(9, 30),
    "shift_1005": dt_time(10, 0),
    "shift_1035": dt_time(10, 30),
}
ANCHOR_LABELS_ZH = {
    "orb_0935": "真实规则（9:30-9:34 开盘区间，9:35 进场）",
    "shift_1005": "占位 (b)：10:00-10:04 区间，10:05 进场",
    "shift_1035": "占位 (b)：10:30-10:34 区间，10:35 进场",
}
PRIMARY_ANCHOR = "orb_0935"

LEVERAGES: tuple[int, ...] = (1, 2, 4)
COST_BPS_LIST: tuple[float, ...] = (0.5, 1.0, 2.0, 5.0)
STOP_VARIANTS: tuple[str, ...] = ("exact", "slip_1bp")
STOP_VARIANT_LABELS_ZH = {"exact": "止损精确成交", "slip_1bp": "止损比止损价差 1bp 成交"}
REFERENCE_LEVERAGE = 1
REFERENCE_COST_BPS = 1.0
REFERENCE_STOP_VARIANT = "exact"

RISK_PER_TRADE = 0.01
TARGET_R_MULTIPLE = 10.0
DOJI_THRESHOLD = 0.05
MIN_BARS_PER_SESSION = 60
BORROW_ANNUAL_RATE = 0.003
STOP_SLIP_FRACTION = 0.0001
RANDOM_SEEDS: tuple[int, ...] = (1, 2, 3, 4, 5)
MINUTES_PER_YEAR = 365.0 * 24.0 * 60.0

BENCHMARK_SYMBOLS: tuple[str, ...] = ("SPY", "QQQ", "SPMO")

_T0 = time.time()


def _log(message: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')} +{time.time() - _T0:7.1f}s] {message}", flush=True)


def _json_default(value: Any) -> Any:
    if isinstance(value, pd.Timestamp | datetime | date):
        return value.isoformat() if hasattr(value, "isoformat") else str(value)
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        return None if not np.isfinite(value) else float(value)
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.bool_):
        return bool(value)
    raise TypeError(f"not JSON serializable: {type(value)}")


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=_json_default) + "\n")


# --------------------------------------------------------------------------
# minute-bar reading (targeted shard paths only, never a whole-archive glob)
# --------------------------------------------------------------------------


def _source_for_year(year: int) -> str:
    for source, cfg in _SHARD_BY_SOURCE.items():
        if year in cfg["years"]:
            return source
    raise ValueError(f"no shard mapping for year {year}")


def _year_glob(symbol: str, year: int) -> str | None:
    source = _source_for_year(year)
    cfg = _SHARD_BY_SOURCE[source]
    root: Path = cfg["root"]
    shard = cfg["shards"][symbol]
    if not (root / str(year)).is_dir():
        return None
    return str(root / str(year) / "*" / f"shard-{shard:04d}.parquet")


def _read_year_minute_bars(symbol: str, year: int) -> pd.DataFrame:
    """One DuckDB query against the (year, symbol)'s fixed shard glob.

    The glob only ever expands to the month-dirs that exist for that year
    (<= 12 files), never the whole per-month shard set -- that's the
    "never a whole-archive glob" rule from the card's engineering section.
    """
    pattern = _year_glob(symbol, year)
    if pattern is None or not glob_module.glob(pattern):
        return pd.DataFrame(columns=["symbol", "timestamp", "open", "high", "low", "close"])
    con = duckdb.connect()
    try:
        con.execute("SET memory_limit='800MB'")
        con.execute("SET threads=2")
        query = """
            SELECT symbol, timestamp, open, high, low, close
            FROM read_parquet(?)
            WHERE symbol = ?
        """
        frame = con.execute(query, [pattern, symbol]).fetchdf()
    finally:
        con.close()
    return frame


# --------------------------------------------------------------------------
# per-day trade skeletons (load stage)
# --------------------------------------------------------------------------


def _add_minutes(value: dt_time, minutes: int) -> dt_time:
    total = value.hour * 60 + value.minute + minutes
    return dt_time(total // 60, total % 60)


def _in_scope(day: date) -> bool:
    return (IN_SAMPLE_START <= day <= IN_SAMPLE_END) or (OOS_START <= day <= OOS_END)


def _simulate_outcome(
    direction: int,
    entry_price: float,
    candle_low: float,
    candle_high: float,
    path_bars: list[tuple[float, float, float]],
) -> dict[str, Any] | None:
    """``path_bars`` is ``[(high, low, close), ...]`` from the entry bar (index 0,
    the same bar whose open was the fill) through the last bar of the session,
    in chronological order. Both stop and target touched in the same bar: the
    stop is assumed to fire first (conservative, documented in the report)."""
    stop_price = candle_low if direction == 1 else candle_high
    r_value = abs(entry_price - stop_price)
    if not (r_value > 0) or not math.isfinite(r_value):
        return None
    target_price = entry_price + direction * TARGET_R_MULTIPLE * r_value
    for index, (high, low, _close) in enumerate(path_bars):
        if direction == 1:
            hit_stop = low <= stop_price
            hit_target = high >= target_price
        else:
            hit_stop = high >= stop_price
            hit_target = low <= target_price
        if hit_stop:
            slip = stop_price * (
                1 - STOP_SLIP_FRACTION if direction == 1 else 1 + STOP_SLIP_FRACTION
            )
            return {
                "stop": stop_price,
                "target": target_price,
                "R": r_value,
                "exit_price": stop_price,
                "exit_price_slip": slip,
                "exit_reason": "stop",
                "holding_min": index + 1,
            }
        if hit_target:
            return {
                "stop": stop_price,
                "target": target_price,
                "R": r_value,
                "exit_price": target_price,
                "exit_price_slip": target_price,
                "exit_reason": "target",
                "holding_min": index + 1,
            }
    last_close = path_bars[-1][2]
    return {
        "stop": stop_price,
        "target": target_price,
        "R": r_value,
        "exit_price": last_close,
        "exit_price_slip": last_close,
        "exit_reason": "close",
        "holding_min": len(path_bars),
    }


def _outcome_fields(prefix: str, outcome: dict[str, Any] | None) -> dict[str, Any]:
    if outcome is None:
        return {
            f"{prefix}_stop": np.nan,
            f"{prefix}_target": np.nan,
            f"{prefix}_R": np.nan,
            f"{prefix}_exit_price": np.nan,
            f"{prefix}_exit_price_slip": np.nan,
            f"{prefix}_exit_reason": None,
            f"{prefix}_holding_min": np.nan,
        }
    return {
        f"{prefix}_stop": outcome["stop"],
        f"{prefix}_target": outcome["target"],
        f"{prefix}_R": outcome["R"],
        f"{prefix}_exit_price": outcome["exit_price"],
        f"{prefix}_exit_price_slip": outcome["exit_price_slip"],
        f"{prefix}_exit_reason": outcome["exit_reason"],
        f"{prefix}_holding_min": outcome["holding_min"],
    }


def build_day_records(session_date: date, day_bars: pd.DataFrame) -> list[dict[str, Any]]:
    """One record per (session_date, anchor) for a single day's RTH minute bars
    (already filtered to ``[09:30, session_close)``). Exposed at module level
    (not prefixed) so tests can call it directly with synthetic bars."""
    close_time = us_equity_session_close(session_date)
    if close_time is None:
        return []
    is_half_day = close_time == dt_time(13, 0)
    session_bars = day_bars.sort_values("ny_time").drop_duplicates("ny_time", keep="last")
    bar_count = int(len(session_bars))
    insufficient = bar_count < MIN_BARS_PER_SESSION
    bars_by_time: dict[dt_time, tuple[float, float, float, float]] = {
        row.ny_time: (row.open, row.high, row.low, row.close) for row in session_bars.itertuples()
    }
    sorted_times = list(session_bars["ny_time"])

    records: list[dict[str, Any]] = []
    for anchor_name, candle_start in ANCHORS.items():
        candle_times = [_add_minutes(candle_start, i) for i in range(5)]
        entry_time = _add_minutes(candle_start, 5)
        base = {
            "date": session_date,
            "anchor": anchor_name,
            "bar_count": bar_count,
            "is_half_day": is_half_day,
            "insufficient_bars": insufficient,
        }
        missing = any(t not in bars_by_time for t in candle_times) or entry_time not in bars_by_time
        if missing:
            records.append(
                {
                    **base,
                    "missing": True,
                    "candle_open": np.nan,
                    "candle_high": np.nan,
                    "candle_low": np.nan,
                    "candle_close": np.nan,
                    "entry_price": np.nan,
                    "direction_real": np.nan,
                    **_outcome_fields("long", None),
                    **_outcome_fields("short", None),
                }
            )
            continue
        candle_open = bars_by_time[candle_times[0]][0]
        candle_close = bars_by_time[candle_times[-1]][3]
        candle_high = max(bars_by_time[t][1] for t in candle_times)
        candle_low = min(bars_by_time[t][2] for t in candle_times)
        entry_price = bars_by_time[entry_time][0]
        candle_range = candle_high - candle_low
        is_doji = (
            candle_range <= 0 or abs(candle_close - candle_open) <= DOJI_THRESHOLD * candle_range
        )
        direction_real = np.nan if is_doji else (1 if candle_close > candle_open else -1)
        entry_idx = sorted_times.index(entry_time)
        path_bars = [
            (bars_by_time[t][1], bars_by_time[t][2], bars_by_time[t][3])
            for t in sorted_times[entry_idx:]
        ]
        long_outcome = _simulate_outcome(1, entry_price, candle_low, candle_high, path_bars)
        short_outcome = _simulate_outcome(-1, entry_price, candle_low, candle_high, path_bars)
        records.append(
            {
                **base,
                "missing": False,
                "candle_open": candle_open,
                "candle_high": candle_high,
                "candle_low": candle_low,
                "candle_close": candle_close,
                "entry_price": entry_price,
                "direction_real": direction_real,
                **_outcome_fields("long", long_outcome),
                **_outcome_fields("short", short_outcome),
            }
        )
    return records


def _day_cache_path(symbol: str) -> Path:
    return DAYS_DIR / f"{symbol}.parquet"


def stage_load(symbols: tuple[str, ...], years: tuple[int, ...], force: bool) -> None:
    DAYS_DIR.mkdir(parents=True, exist_ok=True)
    for symbol in symbols:
        out_path = _day_cache_path(symbol)
        if out_path.exists() and not force:
            _log(f"load: {symbol} cache present ({out_path}) -- reusing (pass --force to rebuild)")
            continue
        all_rows: list[dict[str, Any]] = []
        for year in years:
            t0 = time.time()
            raw = _read_year_minute_bars(symbol, year)
            if raw.empty:
                _log(f"load: {symbol} {year}: no shard data -- skipped")
                continue
            raw["timestamp"] = pd.to_datetime(raw["timestamp"], utc=True)
            ny_ts = raw["timestamp"].dt.tz_convert(NEW_YORK)
            raw = raw.assign(ny_date=ny_ts.dt.date, ny_time=ny_ts.dt.time)
            raw = raw[(raw["ny_time"] >= dt_time(9, 30)) & (raw["ny_time"] <= dt_time(16, 0))]
            year_rows = 0
            days_seen = 0
            for session_date, day_frame in raw.groupby("ny_date", sort=True):
                if not _in_scope(session_date):
                    continue
                close_time = us_equity_session_close(session_date)
                if close_time is None:
                    continue
                day_frame = day_frame[day_frame["ny_time"] < close_time]
                if day_frame.empty:
                    continue
                records = build_day_records(session_date, day_frame)
                all_rows.extend(records)
                year_rows += len(records)
                days_seen += 1
            _log(
                f"load: {symbol} {year}: {days_seen} in-scope sessions, "
                f"{year_rows} day-anchor rows in {time.time() - t0:.1f}s"
            )
            del raw
        frame = pd.DataFrame(all_rows)
        frame.to_parquet(out_path, index=False)
        _log(f"load: {symbol}: wrote {len(frame):,} rows -> {out_path}")


# --------------------------------------------------------------------------
# trade extraction + equity simulation (backtest stage)
# --------------------------------------------------------------------------


def _load_day_frame(symbol: str) -> pd.DataFrame:
    frame = pd.read_parquet(_day_cache_path(symbol))
    frame["date"] = pd.to_datetime(frame["date"]).dt.date
    return frame


def _window_slice(frame: pd.DataFrame, window: str) -> pd.DataFrame:
    start, end = WINDOWS[window]
    return frame[(frame["date"] >= start) & (frame["date"] <= end)]


def _anchor_slice(frame: pd.DataFrame, anchor: str) -> pd.DataFrame:
    return frame[frame["anchor"] == anchor]


def _eligible_rows(frame: pd.DataFrame) -> pd.DataFrame:
    """Rows where a candle+entry could be built and the session had enough bars
    -- the universe controls (a)/(c) sample from, doji days included."""
    return frame[(~frame["missing"]) & (~frame["insufficient_bars"])]


def _trade_from_row(row: pd.Series, direction: int) -> dict[str, Any] | None:
    prefix = "long" if direction == 1 else "short"
    r_value = row[f"{prefix}_R"]
    if pd.isna(r_value):
        return None
    return {
        "date": row["date"],
        "direction": direction,
        "entry_price": float(row["entry_price"]),
        "R": float(r_value),
        "exit_price": float(row[f"{prefix}_exit_price"]),
        "exit_price_slip": float(row[f"{prefix}_exit_price_slip"]),
        "exit_reason": row[f"{prefix}_exit_reason"],
        "holding_min": float(row[f"{prefix}_holding_min"]),
    }


def real_trades(frame: pd.DataFrame) -> list[dict[str, Any]]:
    eligible = _eligible_rows(frame)
    real = eligible[eligible["direction_real"].notna()]
    trades = []
    for _, row in real.iterrows():
        trade = _trade_from_row(row, int(row["direction_real"]))
        if trade is not None:
            trades.append(trade)
    return trades


def random_direction_trades(frame: pd.DataFrame, seed: int) -> list[dict[str, Any]]:
    """Placebo (a): same day set as the real trades, direction re-drawn ±1."""
    eligible = _eligible_rows(frame)
    real_days = eligible[eligible["direction_real"].notna()].sort_values("date")
    rng = np.random.default_rng(seed)
    directions = rng.choice([1, -1], size=len(real_days))
    trades = []
    for direction, (_, row) in zip(directions, real_days.iterrows(), strict=True):
        trade = _trade_from_row(row, int(direction))
        if trade is not None:
            trades.append(trade)
    return trades


def long_only_random_day_trades(
    frame: pd.DataFrame, seed: int, n_days: int
) -> list[dict[str, Any]]:
    """Placebo (c): same *count* of days as the real strategy, drawn randomly
    from every eligible day (doji days included -- direction is forced long
    regardless), to test plain intraday long beta."""
    eligible = _eligible_rows(frame).sort_values("date")
    if n_days <= 0 or eligible.empty:
        return []
    n_days = min(n_days, len(eligible))
    rng = np.random.default_rng(seed)
    chosen_idx = rng.choice(len(eligible), size=n_days, replace=False)
    chosen = eligible.iloc[sorted(chosen_idx)]
    trades = []
    for _, row in chosen.iterrows():
        trade = _trade_from_row(row, 1)
        if trade is not None:
            trades.append(trade)
    return trades


def simulate_equity(
    trades: list[dict[str, Any]],
    session_dates: list[date],
    *,
    leverage: float,
    cost_bps: float,
    stop_variant: str,
) -> tuple[pd.Series, list[dict[str, Any]]]:
    """Compound a single-symbol book across ``session_dates`` (flat return on
    days without a trade). Returns the daily return series and per-trade
    diagnostics (net P&L, day return, price-based R multiple)."""
    equity = 1.0
    daily_return: dict[date, float] = dict.fromkeys(session_dates, 0.0)
    trade_rows: list[dict[str, Any]] = []
    for trade in sorted(trades, key=lambda item: item["date"]):
        r_value = trade["R"]
        if not (r_value > 0) or not math.isfinite(r_value):
            continue
        entry_price = trade["entry_price"]
        direction = trade["direction"]
        exit_price = (
            trade["exit_price_slip"]
            if stop_variant == "slip_1bp" and trade["exit_reason"] == "stop"
            else trade["exit_price"]
        )
        notional = min(RISK_PER_TRADE * equity * entry_price / r_value, leverage * equity)
        if notional <= 0:
            continue
        shares = notional / entry_price
        gross_pnl = shares * (exit_price - entry_price) * direction
        entry_notional = shares * entry_price
        exit_notional = shares * exit_price
        cost = (entry_notional + exit_notional) * (cost_bps / 10_000.0)
        borrow = 0.0
        if direction == -1:
            borrow = entry_notional * BORROW_ANNUAL_RATE * (trade["holding_min"] / MINUTES_PER_YEAR)
        net_pnl = gross_pnl - cost - borrow
        day_return = net_pnl / equity
        equity *= 1.0 + day_return
        daily_return[trade["date"]] = day_return
        trade_rows.append(
            {
                "date": trade["date"],
                "direction": direction,
                "entry_price": entry_price,
                "exit_price": exit_price,
                "exit_reason": trade["exit_reason"],
                "net_pnl": net_pnl,
                "day_return": day_return,
                "r_multiple": direction * (exit_price - entry_price) / r_value,
            }
        )
    dates_sorted = sorted(daily_return)
    returns = pd.Series(
        [daily_return[d] for d in dates_sorted],
        index=pd.to_datetime(dates_sorted),
        dtype="float64",
    )
    return returns, trade_rows


def _metrics(
    returns: pd.Series, trade_rows: list[dict[str, Any]], total_session_days: int
) -> dict[str, Any]:
    if len(returns) == 0 or total_session_days == 0:
        return {
            "annualized_return": None,
            "max_drawdown": None,
            "annualized_vol": None,
            "sharpe": None,
            "win_rate": None,
            "trades": 0,
            "avg_r_multiple": None,
            "share_of_days_in_market": None,
        }
    std = float(returns.std())
    n_trades = len(trade_rows)
    wins = sum(1 for row in trade_rows if row["net_pnl"] > 0)
    return {
        "annualized_return": annualized_cagr(returns),
        "max_drawdown": max_drawdown(returns),
        "annualized_vol": std * math.sqrt(252.0) if std == std else None,
        "sharpe": float(returns.mean() / std * math.sqrt(252.0)) if std > 0 else None,
        "win_rate": wins / n_trades if n_trades else None,
        "trades": n_trades,
        "avg_r_multiple": float(np.mean([row["r_multiple"] for row in trade_rows]))
        if trade_rows
        else None,
        "share_of_days_in_market": n_trades / total_session_days,
    }


def _slice_metrics(returns: pd.Series, start: date, end: date) -> tuple[float | None, float | None]:
    sliced = returns.loc[
        (returns.index >= pd.Timestamp(start)) & (returns.index <= pd.Timestamp(end))
    ]
    if sliced.empty:
        return None, None
    return annualized_cagr(sliced), max_drawdown(sliced)


def _buy_hold_stats(symbol: str, start: date, end: date) -> dict[str, Any] | None:
    try:
        raw = load_sip_bars([symbol], frequency="daily", start=start, end=end)
    except Exception as exc:  # noqa: BLE001 - report a clean "unavailable", not a crash
        _log(f"benchmark: {symbol} {start}..{end}: unavailable ({exc})")
        return None
    raw = raw.sort_values("timestamp")
    ny_date = raw["timestamp"].dt.tz_convert(NEW_YORK).dt.date
    closes = pd.Series(raw["close"].to_numpy(dtype="float64"), index=pd.to_datetime(ny_date))
    closes = closes[~closes.index.duplicated(keep="last")].sort_index()
    returns = closes.pct_change(fill_method=None).dropna()
    if returns.empty:
        return None
    return {
        "annualized_return": annualized_cagr(returns),
        "max_drawdown": max_drawdown(returns),
        "sessions": int(len(returns)),
        "window": [returns.index[0].date().isoformat(), returns.index[-1].date().isoformat()],
    }


# --------------------------------------------------------------------------
# stage: backtest
# --------------------------------------------------------------------------


def stage_backtest(symbols: tuple[str, ...], seeds: tuple[int, ...]) -> dict[str, Any]:
    result: dict[str, Any] = {"grid": [], "controls": [], "benchmarks": {}, "day_counts": {}}
    trade_log_rows: list[dict[str, Any]] = []

    for symbol in symbols:
        frame = _load_day_frame(symbol)
        builtin_leverage = BUILTIN_LEVERAGE[symbol]
        for window in WINDOWS:
            window_start, window_end = WINDOWS[window]
            session_dates = list(us_equity_session_dates(window_start, window_end))
            window_frame = _window_slice(frame, window)

            primary_frame = _anchor_slice(window_frame, PRIMARY_ANCHOR)
            counts = {
                "total_sessions": len(session_dates),
                "rows_present": int(len(primary_frame)),
                "insufficient_bars": int(primary_frame["insufficient_bars"].sum()),
                "missing_candle": int(
                    (primary_frame["missing"] & ~primary_frame["insufficient_bars"]).sum()
                ),
                "doji": int(
                    (
                        ~primary_frame["missing"]
                        & ~primary_frame["insufficient_bars"]
                        & primary_frame["direction_real"].isna()
                    ).sum()
                ),
            }
            result["day_counts"][f"{symbol}__{window}"] = counts

            for anchor in ANCHORS:
                anchor_frame = _anchor_slice(window_frame, anchor)
                trades = real_trades(anchor_frame)
                for leverage in LEVERAGES:
                    for cost_bps in COST_BPS_LIST:
                        for stop_variant in STOP_VARIANTS:
                            returns, trade_rows = simulate_equity(
                                trades,
                                session_dates,
                                leverage=leverage,
                                cost_bps=cost_bps,
                                stop_variant=stop_variant,
                            )
                            metrics = _metrics(returns, trade_rows, len(session_dates))
                            spmo_ann, spmo_mdd = (None, None)
                            beats_spmo = "n/a"
                            if window == "out_of_sample":
                                spmo_ann, spmo_mdd = _slice_metrics(
                                    returns, SPMO_REF_START, SPMO_REF_END
                                )
                                if spmo_ann is not None and spmo_mdd is not None:
                                    beats_spmo = bool(
                                        spmo_ann > SPMO_REF_ANN and spmo_mdd > SPMO_REF_MDD
                                    )
                            row = {
                                "symbol": symbol,
                                "window": window,
                                "anchor": anchor,
                                "leverage": leverage,
                                "true_index_leverage": leverage * builtin_leverage,
                                "cost_bps": cost_bps,
                                "stop_variant": stop_variant,
                                **metrics,
                                "annualized_return_spmo_window": spmo_ann,
                                "max_drawdown_spmo_window": spmo_mdd,
                                "beats_spmo_both_axes": beats_spmo,
                            }
                            result["grid"].append(row)
                            if (
                                anchor == PRIMARY_ANCHOR
                                and leverage == REFERENCE_LEVERAGE
                                and cost_bps == REFERENCE_COST_BPS
                                and stop_variant == REFERENCE_STOP_VARIANT
                            ):
                                for trade_row in trade_rows:
                                    trade_log_rows.append(
                                        {"symbol": symbol, "window": window, **trade_row}
                                    )

            # --- controls, primary anchor only, reference cell ---------------
            real_count = len(real_trades(primary_frame))
            real_returns, real_rows = simulate_equity(
                real_trades(primary_frame),
                session_dates,
                leverage=REFERENCE_LEVERAGE,
                cost_bps=REFERENCE_COST_BPS,
                stop_variant=REFERENCE_STOP_VARIANT,
            )
            real_metrics = _metrics(real_returns, real_rows, len(session_dates))

            for control_name, builder in (
                ("random_direction", random_direction_trades),
                ("long_only_random_days", None),
            ):
                seed_metrics = []
                for seed in seeds:
                    if control_name == "random_direction":
                        control_trades = builder(primary_frame, seed)
                    else:
                        control_trades = long_only_random_day_trades(
                            primary_frame, seed, real_count
                        )
                    control_returns, control_rows = simulate_equity(
                        control_trades,
                        session_dates,
                        leverage=REFERENCE_LEVERAGE,
                        cost_bps=REFERENCE_COST_BPS,
                        stop_variant=REFERENCE_STOP_VARIANT,
                    )
                    seed_metrics.append(
                        {
                            "seed": seed,
                            **_metrics(control_returns, control_rows, len(session_dates)),
                        }
                    )
                ann_values = [
                    m["annualized_return"]
                    for m in seed_metrics
                    if m["annualized_return"] is not None
                ]
                share = None
                if ann_values and real_metrics["annualized_return"] not in (None, 0):
                    share = float(np.mean(ann_values) / real_metrics["annualized_return"])
                result["controls"].append(
                    {
                        "symbol": symbol,
                        "window": window,
                        "control": control_name,
                        "reference_cell": {
                            "anchor": PRIMARY_ANCHOR,
                            "leverage": REFERENCE_LEVERAGE,
                            "cost_bps": REFERENCE_COST_BPS,
                            "stop_variant": REFERENCE_STOP_VARIANT,
                        },
                        "real_annualized_return": real_metrics["annualized_return"],
                        "real_trades": real_metrics["trades"],
                        "seeds": seed_metrics,
                        "mean_of_seeds_annualized_return": float(np.mean(ann_values))
                        if ann_values
                        else None,
                        "share_of_real": share,
                    }
                )

    for symbol in BENCHMARK_SYMBOLS:
        result["benchmarks"][symbol] = {
            window: _buy_hold_stats(symbol, *WINDOWS[window]) for window in WINDOWS
        }
        result["benchmarks"][symbol]["spmo_reference_window"] = _buy_hold_stats(
            symbol, SPMO_REF_START, SPMO_REF_END
        )

    if trade_log_rows:
        TRADE_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(trade_log_rows).to_parquet(TRADE_LOG_PATH, index=False)
        _log(f"backtest: wrote {len(trade_log_rows):,} trade rows -> {TRADE_LOG_PATH}")

    result["latest_signal"] = {
        symbol: _latest_signal(_anchor_slice(_load_day_frame(symbol), PRIMARY_ANCHOR))
        for symbol in symbols
    }
    return result


def _latest_signal(primary_frame: pd.DataFrame) -> dict[str, Any] | None:
    if primary_frame.empty:
        return None
    row = primary_frame.sort_values("date").iloc[-1]
    direction = row["direction_real"]
    direction_label = "多" if direction == 1 else "空" if direction == -1 else "无（十字星/缺失）"
    prefix = "long" if direction == 1 else "short"
    signal = {
        "date": row["date"].isoformat(),
        "missing": bool(row["missing"]),
        "candle_open": _safe_float(row["candle_open"]),
        "candle_high": _safe_float(row["candle_high"]),
        "candle_low": _safe_float(row["candle_low"]),
        "candle_close": _safe_float(row["candle_close"]),
        "entry_price": _safe_float(row["entry_price"]),
        "direction": direction_label,
    }
    if not row["missing"] and not pd.isna(direction):
        signal.update(
            {
                "stop_price": _safe_float(row[f"{prefix}_stop"]),
                "target_price": _safe_float(row[f"{prefix}_target"]),
                "actual_exit_reason": row[f"{prefix}_exit_reason"],
                "actual_exit_price": _safe_float(row[f"{prefix}_exit_price"]),
            }
        )
    return signal


def _safe_float(value: Any) -> float | None:
    if value is None or (isinstance(value, float) and not math.isfinite(value)):
        return None
    return float(value)


# --------------------------------------------------------------------------
# stage: report
# --------------------------------------------------------------------------


def _num(value: Any, digits: int = 2) -> str:
    if value is None or (isinstance(value, float) and not math.isfinite(value)):
        return "n/a"
    return format(value, f".{digits}f")


def _pct(value: Any, digits: int = 1) -> str:
    if value is None or (isinstance(value, float) and not math.isfinite(value)):
        return "n/a"
    return format(value, f".{digits}%")


def _row_key(row: dict[str, Any]) -> tuple:
    return (row["leverage"], row["cost_bps"], row["stop_variant"])


def _find_cell(
    grid: list[dict[str, Any]],
    symbol: str,
    window: str,
    anchor: str,
    *,
    leverage: int = REFERENCE_LEVERAGE,
    cost_bps: float = REFERENCE_COST_BPS,
    stop_variant: str = REFERENCE_STOP_VARIANT,
) -> dict[str, Any] | None:
    return next(
        (
            row
            for row in grid
            if row["symbol"] == symbol
            and row["window"] == window
            and row["anchor"] == anchor
            and row["leverage"] == leverage
            and row["cost_bps"] == cost_bps
            and row["stop_variant"] == stop_variant
        ),
        None,
    )


def render_markdown(summary: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# H-20260918-02 ORB-ETF：开盘区间突破在 QQQ/TQQQ/SPY/SPXL 上的复现")
    lines.append("")
    lines.append(
        "范围：本报告只覆盖卡片里的 ORB-ETF 一段（QQQ/TQQQ/SPY/SPXL 开盘区间突破）。"
        "SPY 盘中动量噪声带那一段由另一个任务负责，这里不涉及。"
    )
    lines.append("")

    # -- data-location finding -------------------------------------------------
    lines.append("## 0. 一个改变卡片假设的发现：QQQ/TQQQ/SPXL 分钟线其实有 2016 年起的数据")
    lines.append("")
    lines.append(
        "卡片写的时候认为 QQQ/TQQQ 分钟线只从 2023-01 起有，所以样本内复现"
        "（2016-01→2023-02，论文报的 QQQ 33%/Sharpe 1.13/-22%，TQQQ 48%/1.19/-28%）"
        "只能在 SPY 上做。实际扫描 `data/sip-hist/minute` 的分片后发现 QQQ（shard-0812）、"
        "TQQQ（shard-0987）、SPXL（与 SPY 同在 shard-0927）在 2016-01 就有数据"
        "（逐年验证了 2016/2019/2022，分片号在验证过的年份里稳定），"
        "所以样本内复现改成对全部四个标的都跑，不再局限于 SPY。"
    )
    lines.append("")

    grid = summary["grid"]
    oos_rows = [r for r in grid if r["window"] == "out_of_sample" and r["anchor"] == PRIMARY_ANCHOR]
    is_rows = [r for r in grid if r["window"] == "in_sample" and r["anchor"] == PRIMARY_ANCHOR]

    # -- headline OOS table -----------------------------------------------------
    lines.append("## 1. 样本外（2024-01-02 → 2026-09-17）—— 结论以这张表为准")
    lines.append("")
    lines.append(
        "规则：9:30-9:34 开盘区间，9:35 进场，止损=开盘区间另一端，目标=10R，收盘平；"
        "1%/笔风险，杠杆封顶；做空另计年化 0.3% 融券费。"
    )
    lines.append("")
    lines.append(
        "| 标的 | 杠杆 | 真实指数敞口 | 成本(bp/边) | 止损成交假设 | 年化收益 | 最大回撤 "
        "| 年化波动 | Sharpe | 胜率 | 交易数 | 平均R倍数 | 在场天数占比 | 打赢SPMO两项? |"
    )
    lines.append("|---|---:|---:|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|:-:|")
    for row in sorted(oos_rows, key=_row_key):
        beat = row["beats_spmo_both_axes"]
        beat_txt = "是" if beat is True else "否" if beat is False else "n/a"
        lines.append(
            f"| {row['symbol']} | {row['leverage']}x | {row['true_index_leverage']}x "
            f"| {_num(row['cost_bps'], 1)} | {STOP_VARIANT_LABELS_ZH[row['stop_variant']]} "
            f"| {_pct(row['annualized_return'])} | {_pct(row['max_drawdown'])} "
            f"| {_pct(row['annualized_vol'])} | {_num(row['sharpe'])} | {_pct(row['win_rate'])} "
            f"| {row['trades']} | {_num(row['avg_r_multiple'])} "
            f"| {_pct(row['share_of_days_in_market'])} | {beat_txt} |"
        )
    lines.append("")
    lines.append(
        "「打赢 SPMO 两项」在这张表里是用策略自己 2024-01-08→2026-09-16 那一段（跟 SPMO 参照窗口"
        "完全对齐）重算的年化/回撤去比较 SPMO 同窗口的真实买入持有表现（不是直接用卡片写的 "
        "34.7%/-20.1%，那两个数只作为交叉核对，见第 4 节的基准表）。"
    )
    lines.append("")

    # -- refutation verdict -------------------------------------------------
    lines.append("## 2. 对照卡片的四条否定条件")
    lines.append("")
    ref_rows = [
        r
        for r in oos_rows
        if r["leverage"] == REFERENCE_LEVERAGE
        and r["cost_bps"] == REFERENCE_COST_BPS
        and r["stop_variant"] == REFERENCE_STOP_VARIANT
    ]
    cond1_fail = [r for r in ref_rows if (r["annualized_return"] or 0) <= 0]
    lines.append(
        f"1. **样本外 1bp/1 倍杠杆年化 ≤ 0**：{len(cond1_fail)}/{len(ref_rows)} 个标的触发"
        f"（{', '.join(r['symbol'] for r in cond1_fail) if cond1_fail else '无'}）。"
    )
    control_rows = [c for c in summary["controls"] if c["window"] == "out_of_sample"]
    rand_fail = []
    for c in control_rows:
        if c["control"] != "random_direction":
            continue
        share = c["share_of_real"]
        if share is not None and share >= 0.5:
            rand_fail.append(c["symbol"])
    lines.append(
        f"2. **随机方向占位达到真实收益的 ≥50%**：{len(rand_fail)} 个标的触发"
        f"（{', '.join(rand_fail) if rand_fail else '无'}，见第 5 节的分布）。"
    )
    shift_effective = []
    for symbol in {r["symbol"] for r in oos_rows}:
        real_cell = _find_cell(grid, symbol, "out_of_sample", PRIMARY_ANCHOR)
        shifted = [
            _find_cell(grid, symbol, "out_of_sample", "shift_1005"),
            _find_cell(grid, symbol, "out_of_sample", "shift_1035"),
        ]
        if real_cell and all(
            s
            and s["annualized_return"] is not None
            and real_cell["annualized_return"] is not None
            and s["annualized_return"] >= real_cell["annualized_return"]
            for s in shifted
            if s
        ):
            shift_effective.append(symbol)
    shift_names = ", ".join(shift_effective) if shift_effective else "无"
    lines.append(
        f"3. **平移进场时间同样有效（说明是日内 beta 而非开盘效应）**："
        f"{len(shift_effective)} 个标的触发（{shift_names}，见第 6 节）。"
    )
    only_lowest = []
    for symbol in {r["symbol"] for r in oos_rows}:
        by_cost = sorted(
            (
                r
                for r in oos_rows
                if r["symbol"] == symbol
                and r["leverage"] == REFERENCE_LEVERAGE
                and r["stop_variant"] == REFERENCE_STOP_VARIANT
            ),
            key=lambda r: r["cost_bps"],
        )
        positive = [r["cost_bps"] for r in by_cost if (r["annualized_return"] or -1) > 0]
        if positive == [COST_BPS_LIST[0]]:
            only_lowest.append(symbol)
    lines.append(
        f"4. **只有最低成本档才为正**：{len(only_lowest)} 个标的触发"
        f"（{', '.join(only_lowest) if only_lowest else '无'}）。"
    )
    lines.append("")
    triggered = bool(cond1_fail) or bool(rand_fail) or bool(shift_effective) or bool(only_lowest)
    verdict_text = (
        "至少一条否定条件被触发，假设不成立或需要收窄范围。"
        if triggered
        else "四条否定条件均未触发，样本外结果站得住脚。"
    )
    lines.append(f"**总体判定**：{verdict_text}")
    lines.append("")

    # -- in-sample check ------------------------------------------------------
    lines.append("## 3. 样本内复现检查（2016-01-04 → 2023-02-28）")
    lines.append("")
    lines.append(
        "只用来确认实现的规则和论文对得上，不作为结论依据；论文假设无滑点、用 "
        "$0.0035/股佣金，这里最接近的是最低成本档（0.5bp/边），仍然不是同一个成本假设，"
        "只能定性对照量级和符号。"
    )
    lines.append("")
    lines.append(
        "| 标的 | 成本(bp/边) | 年化收益 | Sharpe | 最大回撤 "
        "| 论文年化 | 论文Sharpe | 论文最大回撤 |"
    )
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|")
    for row in sorted(is_rows, key=_row_key):
        if row["leverage"] != REFERENCE_LEVERAGE or row["stop_variant"] != REFERENCE_STOP_VARIANT:
            continue
        published = PUBLISHED_IN_SAMPLE.get(row["symbol"])
        pub_ann = _pct(published["annualized_return"]) if published else "无公开数字"
        pub_sharpe = _num(published["sharpe"]) if published else "—"
        pub_mdd = _pct(published["max_drawdown"]) if published else "—"
        lines.append(
            f"| {row['symbol']} | {_num(row['cost_bps'], 1)} | {_pct(row['annualized_return'])} "
            f"| {_num(row['sharpe'])} | {_pct(row['max_drawdown'])} | {pub_ann} | {pub_sharpe} "
            f"| {pub_mdd} |"
        )
    lines.append("")

    # -- benchmark table --------------------------------------------------------
    lines.append("## 4. 基准：SPY/QQQ/SPMO 买入持有")
    lines.append("")
    lines.append("| 标的 | 窗口 | 年化收益 | 最大回撤 | 交易日数 |")
    lines.append("|---|---|---:|---:|---:|")
    for symbol in BENCHMARK_SYMBOLS:
        bench = summary["benchmarks"].get(symbol, {})
        for window_key, label in (
            ("in_sample", "样本内"),
            ("out_of_sample", "样本外"),
            ("spmo_reference_window", "SPMO 参照窗口 2024-01-08→2026-09-16"),
        ):
            stats = bench.get(window_key)
            if stats is None:
                lines.append(f"| {symbol} | {label} | n/a | n/a | n/a |")
            else:
                lines.append(
                    f"| {symbol} | {label} | {_pct(stats['annualized_return'])} "
                    f"| {_pct(stats['max_drawdown'])} | {stats['sessions']} |"
                )
    lines.append("")
    lines.append(
        f"卡片给的 SPMO 参照数字是年化 {_pct(SPMO_REF_ANN)} / 最大回撤 {_pct(SPMO_REF_MDD)}；"
        "上表是本仓库数据自己算的同窗口买入持有，用于交叉核对。"
    )
    lines.append("")

    # -- control (b): shifted entry time ----------------------------------------
    lines.append("## 5. 占位 (b)：把进场时间从 9:35 平移到 10:05 / 10:35")
    lines.append("")
    lines.append(
        f"参照单元：杠杆 {REFERENCE_LEVERAGE}x，成本 {REFERENCE_COST_BPS} bp/边，止损精确成交。"
    )
    lines.append("")
    lines.append("| 标的 | 窗口 | 9:35（真实规则） | 10:05 | 10:35 |")
    lines.append("|---|---|---:|---:|---:|")
    for symbol in {r["symbol"] for r in grid}:
        for window in WINDOWS:
            real_cell = _find_cell(grid, symbol, window, PRIMARY_ANCHOR)
            c1005 = _find_cell(grid, symbol, window, "shift_1005")
            c1035 = _find_cell(grid, symbol, window, "shift_1035")
            lines.append(
                f"| {symbol} | {WINDOW_LABELS_ZH[window]} "
                f"| {_pct(real_cell['annualized_return']) if real_cell else 'n/a'} "
                f"| {_pct(c1005['annualized_return']) if c1005 else 'n/a'} "
                f"| {_pct(c1035['annualized_return']) if c1035 else 'n/a'} |"
            )
    lines.append("")

    # -- controls (a)/(c) distributions ------------------------------------------
    lines.append("## 6. 占位 (a) 随机方向 / (c) 同数量随机交易日只做多")
    lines.append("")
    lines.append(
        "(a) 用与真实交易相同的交易日集合，方向从 ±1 随机抽取（5 个种子）；"
        "(c) 从所有候选交易日（含十字星日）里随机抽与真实交易数相同的天数，强制只做多（5 个种子）。"
        "都在参照单元（杠杆 1x，成本 1bp/边，止损精确成交）上跑。"
    )
    lines.append("")
    lines.append(
        "| 标的 | 窗口 | 对照 | 真实年化 | 5 个种子年化(均值) | 占真实的比例 | 种子分布(min~max) |"
    )
    lines.append("|---|---|---|---:|---:|---:|---|")
    control_label = {
        "random_direction": "(a) 随机方向",
        "long_only_random_days": "(c) 随机日只做多",
    }
    for control in summary["controls"]:
        seed_ann = [
            s["annualized_return"] for s in control["seeds"] if s["annualized_return"] is not None
        ]
        spread = f"{_pct(min(seed_ann))} ~ {_pct(max(seed_ann))}" if seed_ann else "n/a"
        share_of_real = control["share_of_real"]
        share_text = _pct(share_of_real) if share_of_real is not None else "n/a"
        lines.append(
            f"| {control['symbol']} | {WINDOW_LABELS_ZH[control['window']]} "
            f"| {control_label[control['control']]} | {_pct(control['real_annualized_return'])} "
            f"| {_pct(control['mean_of_seeds_annualized_return'])} "
            f"| {share_text} "
            f"| {spread} |"
        )
    lines.append("")

    # -- day counts ---------------------------------------------------------
    lines.append("## 7. 数据质量：每个窗口丢了多少天")
    lines.append("")
    lines.append("| 标的 | 窗口 | 交易日总数 | 分钟线不足60根 | 蜡烛/进场缺失 | 十字星跳过 |")
    lines.append("|---|---|---:|---:|---:|---:|")
    for key, counts in summary["day_counts"].items():
        symbol, window = key.split("__")
        lines.append(
            f"| {symbol} | {WINDOW_LABELS_ZH[window]} | {counts['total_sessions']} "
            f"| {counts['insufficient_bars']} | {counts['missing_candle']} | {counts['doji']} |"
        )
    lines.append("")

    # -- paper section --------------------------------------------------------
    lines.append("## 8. 如果上模拟盘")
    lines.append("")
    lines.append(
        "每天两次动作，走 Alpaca Paper：**9:35 ET** 按当天开盘区间方向、按 "
        "`shares = min(0.01*当前权益/R, 杠杆*当前权益) / entry_price` 下市价单进场，"
        "同时挂一个止损单（开盘区间另一端）和一个止盈限价单（10R）；**收盘前一分钟"
        "（正常日 15:59 ET，半日市 12:59 ET）**：若仍持仓则市价平仓。十字星日"
        "（|收-开| ≤ 5%×(高-低)）或分钟线缺失当天不进场。"
    )
    lines.append("")
    lines.append("最新一个完整交易日的信号（用于对账，不是实时信号）：")
    lines.append("")
    lines.append("| 标的 | 日期 | 开盘区间 O/H/L/C | 方向 | 进场价 | 止损价 | 目标价 | 实际结果 |")
    lines.append("|---|---|---|---|---:|---:|---:|---|")
    for symbol, signal in summary.get("latest_signal", {}).items():
        if signal is None:
            lines.append(f"| {symbol} | n/a | n/a | n/a | n/a | n/a | n/a | 无数据 |")
            continue
        ohlc = (
            f"{_num(signal['candle_open'])}/{_num(signal['candle_high'])}/"
            f"{_num(signal['candle_low'])}/{_num(signal['candle_close'])}"
        )
        actual = (
            f"{signal.get('actual_exit_reason', 'n/a')} @ {_num(signal.get('actual_exit_price'))}"
            if not signal["missing"] and signal["direction"] not in ("无（十字星/缺失）",)
            else "未进场"
        )
        lines.append(
            f"| {symbol} | {signal['date']} | {ohlc} | {signal['direction']} "
            f"| {_num(signal['entry_price'])} | {_num(signal.get('stop_price'))} "
            f"| {_num(signal.get('target_price'))} | {actual} |"
        )
    lines.append("")

    lines.append("## 9. 文件")
    lines.append("")
    lines.append(
        f"- 汇总：`{SUMMARY_PATH.relative_to(ROOT)}`；本报告：`{REPORT_PATH.relative_to(ROOT)}`"
    )
    lines.append(
        f"- 每日交易骨架缓存：`{DAYS_DIR.relative_to(ROOT)}/{{symbol}}.parquet`"
        f"；参照单元逐笔交易：`{TRADE_LOG_PATH.relative_to(ROOT)}`"
    )
    lines.append(
        "- 脚本：`scripts/run_h20260918_02_orb_etf.py`（阶段 load / backtest / report，可断点续跑）"
    )
    lines.append("")
    lines.append("## 10. 未能实现 / 简化之处")
    lines.append("")
    lines.append(
        "- 仓位按连续股数计算，未取整到整股"
        "（现实下单会有小幅取整误差，多头/空头交易均不受影响的量级）。"
    )
    lines.append(
        "- 同一根分钟线内止损和目标同时触及时，保守假设止损先成交（未用逐笔/秒级数据消歧）。"
    )
    lines.append(
        "- 占位 (a)/(c) 和平移进场时间 (b) 只在参照单元（1x 杠杆、1bp 成本、止损精确成交）上跑，"
        "没有覆盖完整的 3x4x2 成本/杠杆网格——网格本身对方向选择和进场时间点是否有效不敏感，"
        "跑参照单元足以回答否定条件里的问题；完整网格只对真实规则（第 1 节）跑。"
    )
    lines.append(
        "- R 倍数用纯价格口径（不含成本、不含杠杆），因为成本对同一笔交易的绝对影响随杠杆缩放，"
        "R 倍数本身在不同杠杆行之间是相同的值（已在网格里按行填充，未去重）。"
    )
    return "\n".join(lines) + "\n"


def stage_report(symbols: tuple[str, ...], seeds: tuple[int, ...]) -> None:
    summary = stage_backtest(symbols, seeds)
    summary["generated_at"] = datetime.now(NEW_YORK).isoformat()
    summary["windows"] = {k: [v[0].isoformat(), v[1].isoformat()] for k, v in WINDOWS.items()}
    _write_json(SUMMARY_PATH, summary)
    REPORT_PATH.write_text(render_markdown(summary), encoding="utf-8")
    _log(f"report: wrote {SUMMARY_PATH} and {REPORT_PATH}")


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--stage", choices=["all", "load", "backtest", "report"], default="all")
    parser.add_argument("--symbols", nargs="*", default=None, choices=list(SYMBOLS))
    parser.add_argument("--years", type=int, nargs="*", default=None)
    parser.add_argument(
        "--seeds", type=int, default=None, help="number of control seeds (default 5)"
    )
    parser.add_argument("--force", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    symbols = tuple(args.symbols) if args.symbols else SYMBOLS
    years = tuple(y for y in (args.years or ALL_YEARS) if y in ALL_YEARS)
    seeds = RANDOM_SEEDS[: args.seeds] if args.seeds else RANDOM_SEEDS
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    if args.stage in ("all", "load"):
        stage_load(symbols, years, args.force)
    if args.stage in ("all", "backtest"):
        # backtest is cheap and always re-derived fresh from the day cache;
        # "report" below re-runs it too so the two stages can be invoked
        # independently without a separate on-disk backtest cache.
        stage_backtest(symbols, seeds)
    if args.stage in ("all", "report"):
        stage_report(symbols, seeds)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
