"""SIP recheck of the frozen NASDAQ long/short intraday router route (T-20260929-36).

Iteration: reports/research/iterations/h20260929_36_router_sip. Registry direction:
dir:nasdaq_long_short_event_router_1m.

The route (lb10, entry after 2 bars, top 1, QQQ-prior-negative gate, opening_reversal,
max opening return 0) is run through the UNCHANGED functions of
open_composer/research/intraday_daily_rotation.py (`_selected_positions`,
`_symbol_intraday_return`, `_market_gate_passes`, `_backtest_params`). The only new pieces are
a SIP-cache loader (`build_dataset`), a split audit, seeded random-pick placebos, and the
K1/K2/G3 bookkeeping frozen in the iteration's candidate-manifest.json.

Run (heavy: reads the minute cache, S3 daily panel):
    scripts/run_capped.sh --mem 1.2G -- uv run python scripts/run_h20260929_36_router_sip.py
"""

from __future__ import annotations

import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from open_composer.research import intraday_daily_rotation as idr  # noqa: E402

ITER = "h20260929_36_router_sip"
ITER_DIR = ROOT / "reports" / "research" / "iterations" / ITER
CACHE_DIR = ROOT / "data" / "features" / "t20260929_36_router_minute"
SPEC_PATH = ROOT / "strategy_specs" / "drafts" / "h20260929_36_router_sip.yaml"
ARCHIVED_SPEC = (
    ROOT
    / "strategy_specs"
    / "archived"
    / "curation-20260525"
    / "nasdaq_long_short_event_router_1m_sweep_001.yaml"
)

UNIVERSE = [
    "AAPL",
    "MSFT",
    "NVDA",
    "AMZN",
    "META",
    "GOOGL",
    "AVGO",
    "AMD",
    "QCOM",
    "AMAT",
    "NFLX",
    "TSLA",
]
MARKET = "QQQ"
FROZEN_LABEL = "lb10_entry2_top1_open0_mom0_rv1_qprior_negative_reversal_maxopen0_maxmomnone"
FROZEN_PARAMS = idr.IntradayDailyParams(
    selection_style="opening_reversal",
    lookback_days=10,
    entry_after_bars=2,
    top_n=1,
    min_opening_return_pct=0.0,
    min_prior_momentum_pct=0.0,
    min_relative_volume=1.0,
    max_opening_return_pct=0.0,
    max_prior_momentum_pct=None,
    market_gate="qqq_prior_negative",
)

# cost tiers: (commission_pct, slippage_bps) -> per-side cost = commission_pct/100 + bps/10000
COST_TIERS: dict[str, tuple[float, float]] = {
    "c10": (0.0, 10.0),
    "c20": (0.0, 20.0),
    "orig": (0.005, 2.0),
}
BORROW_ANNUAL = 0.005
BORROW_FRAC_PER_SHORT_DAY = BORROW_ANNUAL / 252.0

WINDOWS: dict[str, tuple[str, str | None]] = {
    "anchor": ("2024-01-08", None),
    "select": ("2023-09-18", "2025-12-31"),
    "holdout_contaminated": ("2026-01-02", "2026-09-17"),
    "new_holdout": ("2026-09-18", None),
    "partial_stress_2023_01_08": ("2023-01-01", "2023-08-31"),
    "iex_comparison": ("2024-05-31", "2026-05-29"),
}

PLACEBO_SEEDS = {"P1": 20260929, "P2": 20260930, "P3": 20261001}
DIST_SEEDS = list(range(100000, 100200))

KNOWN_SPLITS = [
    ("NVDA", "2024-06-10", 10.0),
    ("AVGO", "2024-07-15", 10.0),
    ("NFLX", "2025-11-17", 10.0),
]

# Recorded IEX-era numbers (read, not recomputed): full-window entry of the "Rank 1" block.
IEX_RECORD = {
    "source": (
        "reports/research/nasdaq_long_short_event_router_1m_sweep_002-"
        "intraday-daily-rotation.md (Rank 1 block)"
    ),
    "window": "2024-05-31..2026-05-29 (Alpaca IEX cache)",
    "cost": "0.005 percent commission + 2 bp slippage per fill",
    "full_window_annualized_pct": 35.24,
    "full_window_total_return_pct": 79.41,
    "full_window_sharpe_plain": 1.41,
    "full_window_max_drawdown_pct": -16.74,
    "full_window_traded_days": 153,
    "full_window_win_day_pct": 19.26,
    "oos_sharpe": 2.40,
    "oos_traded_days": 52,
    "longbridge_crosscheck_source": (
        "reports/research/nasdaq_long_short_event_router_1m_sweep_003-"
        "fixed-route-longbridge-crosscheck.md (Rank 1 block)"
    ),
    "longbridge_train_sharpe": 1.46,
    "longbridge_oos_sharpe": -0.19,
    "longbridge_oos_annualized_pct": -6.57,
}


# ---------------------------------------------------------------- data adapter
def daily_bars_for_frame(frame: pd.DataFrame) -> dict[str, idr._DailyBars]:
    """Group one symbol's minute bars by New York session date.

    Same rules as `idr._regular_session_days` (09:30 <= time < 16:00, at least 4 bars, sorted by
    timestamp) but stores timestamps as compact datetime64 instead of Python objects: the
    reused router functions only read opens, closes and volumes.
    """
    if frame.empty:
        return {}
    data = frame[["timestamp", "open", "close", "volume"]].copy()
    data["timestamp"] = pd.to_datetime(data["timestamp"], utc=True)
    local = data["timestamp"].dt.tz_convert("America/New_York")
    minutes = local.dt.hour * 60 + local.dt.minute
    keep = (minutes >= 9 * 60 + 30) & (minutes < 16 * 60)
    data = data.loc[keep].copy()
    data["session_date"] = local.loc[keep].dt.date.astype(str)
    data = data.sort_values("timestamp").reset_index(drop=True)
    days: dict[str, idr._DailyBars] = {}
    for date, group in data.groupby("session_date", sort=True):
        if len(group) < 4:
            continue
        days[str(date)] = idr._DailyBars(
            timestamps=group["timestamp"].to_numpy(dtype="datetime64[ns]"),
            opens=group["open"].to_numpy(dtype=float, copy=True),
            closes=group["close"].to_numpy(dtype=float, copy=True),
            volumes=group["volume"].to_numpy(dtype=float, copy=True),
        )
    return days


def apply_split_factor(
    days: dict[str, idr._DailyBars], split_date: str, ratio: float
) -> dict[str, idr._DailyBars]:
    """Rescale sessions strictly before `split_date` by 1/ratio (prices) and ratio (volume)."""
    out: dict[str, idr._DailyBars] = {}
    for date, bars in days.items():
        if date < split_date:
            out[date] = idr._DailyBars(
                timestamps=bars.timestamps,
                opens=bars.opens / ratio,
                closes=bars.closes / ratio,
                volumes=bars.volumes * ratio,
            )
        else:
            out[date] = bars
    return out


def build_dataset(
    cache_dir: Path = CACHE_DIR,
    symbols: list[str] | None = None,
    market: str = MARKET,
    split_factors: dict[str, list[tuple[str, float]]] | None = None,
) -> idr._IntradayDataset:
    """Feed the SIP regular-session cache into the router's `_IntradayDataset`."""
    universe = list(symbols or UNIVERSE)
    all_symbols = list(dict.fromkeys([*universe, market]))
    bars: dict[str, dict[str, idr._DailyBars]] = {s: {} for s in all_symbols}
    for path in sorted(cache_dir.glob("[0-9][0-9][0-9][0-9]-[0-9][0-9].parquet")):
        month = pd.read_parquet(path)
        for symbol, group in month.groupby("symbol"):
            if symbol in bars:
                bars[str(symbol)].update(daily_bars_for_frame(group))
        del month
    for symbol, factors in (split_factors or {}).items():
        for split_date, ratio in factors:
            bars[symbol] = apply_split_factor(bars[symbol], split_date, ratio)
    dates = idr._common_dates(bars, all_symbols)
    if len(dates) < 30:
        raise ValueError("fewer than 30 common regular-session days")
    return idr._IntradayDataset(
        symbols=universe,
        benchmark_symbol=market,
        market_symbol=market,
        dates=dates,
        bars=bars,
        profiles=[],
    )


def overnight_gap_flags(dataset: idr._IntradayDataset, lo: float = 0.7, hi: float = 1.4) -> list:
    """Sessions whose first open is outside [lo, hi] x the previous close (possible split)."""
    flags = []
    for symbol in dataset.bars:
        prev = None
        for date in dataset.dates:
            bars = dataset.bars[symbol].get(date)
            if bars is None:
                continue
            if prev is not None:
                ratio = float(bars.opens[0] / prev)
                if ratio < lo or ratio > hi:
                    flags.append({"symbol": symbol, "date": date, "open_over_prev_close": ratio})
            prev = float(bars.closes[-1])
    return flags


def split_audit(dataset: idr._IntradayDataset) -> dict:
    """Check the known splits inside the window and any large overnight gap."""
    rows = []
    for symbol, split_date, ratio in KNOWN_SPLITS:
        dates = [d for d in dataset.dates if d in dataset.bars[symbol]]
        if split_date not in dates:
            rows.append({"symbol": symbol, "split_date": split_date, "status": "date_not_in_data"})
            continue
        i = dates.index(split_date)
        prev_close = float(dataset.bars[symbol][dates[i - 1]].closes[-1])
        first_open = float(dataset.bars[symbol][split_date].opens[0])
        gap = first_open / prev_close
        rows.append(
            {
                "symbol": symbol,
                "split_date": split_date,
                "ratio": ratio,
                "prev_close": prev_close,
                "first_open": first_open,
                "open_over_prev_close": gap,
                "adjusted_in_data": bool(0.7 < gap < 1.4),
            }
        )
    return {"known_splits": rows, "large_overnight_gaps": overnight_gap_flags(dataset)}


def completeness_audit(dataset: idr._IntradayDataset) -> dict:
    """Bar counts and clock alignment of the entry bars per symbol."""
    out = {}
    for symbol in dataset.bars:
        counts, first_ok, third_ok = [], 0, 0
        n = 0
        for date in dataset.dates:
            bars = dataset.bars[symbol].get(date)
            if bars is None:
                continue
            n += 1
            counts.append(len(bars.closes))
            ts = pd.DatetimeIndex(bars.timestamps).tz_localize("UTC").tz_convert("America/New_York")
            first_ok += int(ts[0].hour == 9 and ts[0].minute == 30)
            third_ok += int(len(ts) > 2 and ts[2].hour == 9 and ts[2].minute == 32)
        arr = np.array(counts)
        out[symbol] = {
            "days": n,
            "median_bars": float(np.median(arr)),
            "days_lt_385_bars": int((arr < 385).sum()),
            "share_first_bar_0930": first_ok / max(n, 1),
            "share_bar2_is_0932": third_ok / max(n, 1),
        }
    return out


def close_vs_daily_audit(dataset: idr._IntradayDataset) -> dict:
    """Last regular-session minute close vs the SIP daily close, per symbol and date."""
    from open_composer.adapters.data.sip_parquet import load_sip_bars

    start = pd.Timestamp(dataset.dates[0], tz="UTC") - pd.Timedelta(days=3)
    daily = load_sip_bars(
        [*dataset.symbols, dataset.market_symbol],
        frequency="daily",
        start=start,
        allow_missing=True,
    )
    daily["d"] = (
        pd.to_datetime(daily["timestamp"], utc=True)
        .dt.tz_convert("America/New_York")
        .dt.date.astype(str)
    )
    daily_close = {(r.symbol, r.d): float(r.close) for r in daily.itertuples()}
    bad, n = [], 0
    worst: dict[str, float] = {}
    for symbol in dataset.bars:
        for date in dataset.dates:
            bars = dataset.bars[symbol].get(date)
            ref = daily_close.get((symbol, date))
            if bars is None or ref is None or ref <= 0:
                continue
            n += 1
            rel = float(bars.closes[-1] / ref - 1.0)
            worst[symbol] = max(worst.get(symbol, 0.0), abs(rel))
            if abs(rel) > 0.005:
                bad.append(
                    {"symbol": symbol, "date": date, "minute_last_close_over_daily_close": 1 + rel}
                )
    return {
        "compared_symbol_days": n,
        "days_over_0p5pct": len(bad),
        "share_over_0p5pct": len(bad) / max(n, 1),
        "worst_abs_rel_by_symbol": worst,
        "listed": bad[:200],
        "listed_truncated": len(bad) > 200,
    }


# ---------------------------------------------------------------- backtest pieces
def tier_specs(spec):
    out = {}
    for tier, (commission, bps) in COST_TIERS.items():
        out[tier] = spec.model_copy(
            update={
                "costs": spec.costs.model_copy(
                    update={"commission_pct": commission, "slippage_bps": bps}
                )
            }
        )
    return out


@dataclass
class Series:
    dates: pd.DatetimeIndex
    index: list[int]
    gate: np.ndarray
    ret: dict[str, dict[str, np.ndarray]]  # variant -> tier -> daily return
    n_trades: dict[str, np.ndarray]  # variant -> trades per day
    trades: list[dict]
    long_mat: dict[str, np.ndarray]  # tier -> [days, symbols], nan when missing
    short_mat: dict[str, np.ndarray]


def build_series(dataset: idr._IntradayDataset, params, spec, specs_by_tier) -> Series:
    """Per-day selections and returns via the router's own functions."""
    start = params.lookback_days
    index = list(range(start, len(dataset.dates)))
    dates = pd.DatetimeIndex([pd.Timestamp(dataset.dates[i]) for i in index])
    variants = ("R0", "R0_long", "R0_short", "B_ew")
    ret = {v: {t: np.zeros(len(index)) for t in COST_TIERS} for v in variants}
    n_trades = {v: np.zeros(len(index), dtype=int) for v in variants}
    gate = np.zeros(len(index), dtype=bool)
    long_mat = {t: np.full((len(index), len(dataset.symbols)), np.nan) for t in COST_TIERS}
    short_mat = {t: np.full((len(index), len(dataset.symbols)), np.nan) for t in COST_TIERS}
    trades: list[dict] = []
    for k, i in enumerate(index):
        gate[k] = idr._market_gate_passes(dataset, i, params)
        selected = idr._selected_positions(dataset, i, params, spec)
        day_rows: dict[tuple[str, str], dict] = {}
        for tier, tspec in specs_by_tier.items():
            per_side = {"long": [], "short": []}
            for item in selected:
                value = idr._symbol_intraday_return(
                    dataset, item.symbol, i, params, tspec, side=item.side
                )
                if value is None:
                    continue
                if item.side == "short":
                    value -= BORROW_FRAC_PER_SHORT_DAY
                per_side[item.side].append(value)
                row = day_rows.setdefault(
                    (item.symbol, item.side),
                    {"date": dataset.dates[i], "symbol": item.symbol, "side": item.side},
                )
                row[f"ret_{tier}"] = value
            both = per_side["long"] + per_side["short"]
            ret["R0"][tier][k] = float(np.mean(both)) if both else 0.0
            ret["R0_long"][tier][k] = float(np.mean(per_side["long"])) if per_side["long"] else 0.0
            ret["R0_short"][tier][k] = (
                float(np.mean(per_side["short"])) if per_side["short"] else 0.0
            )
            if tier == "c10":
                n_trades["R0"][k] = len(both)
                n_trades["R0_long"][k] = len(per_side["long"])
                n_trades["R0_short"][k] = len(per_side["short"])
            longs = []
            for j, symbol in enumerate(dataset.symbols):
                lv = idr._symbol_intraday_return(dataset, symbol, i, params, tspec, side="long")
                sv = idr._symbol_intraday_return(dataset, symbol, i, params, tspec, side="short")
                if lv is not None:
                    long_mat[tier][k, j] = lv
                    longs.append(lv)
                if sv is not None:
                    short_mat[tier][k, j] = sv - BORROW_FRAC_PER_SHORT_DAY
            ret["B_ew"][tier][k] = float(np.mean(longs)) if longs else 0.0
            if tier == "c10":
                n_trades["B_ew"][k] = len(longs)
        trades.extend(day_rows.values())
    return Series(dates, index, gate, ret, n_trades, trades, long_mat, short_mat)


def placebo_returns(series: Series, seed: int) -> dict[str, np.ndarray]:
    """One random symbol and one random side per session, traded only on QQQ-gate days.

    Draw order is fixed: for each session (in date order) `symbol = rng.integers(12)` then
    `side = rng.integers(2)` (0 long, 1 short), independent of the gate, so the stream does not
    depend on data availability.
    """
    rng = np.random.default_rng(seed)
    n_days, n_sym = series.long_mat["c10"].shape
    picks = np.empty(n_days, dtype=int)
    sides = np.empty(n_days, dtype=int)
    for k in range(n_days):
        picks[k] = rng.integers(n_sym)
        sides[k] = rng.integers(2)
    out = {}
    for tier in COST_TIERS:
        vals = np.where(
            sides == 0,
            series.long_mat[tier][np.arange(n_days), picks],
            series.short_mat[tier][np.arange(n_days), picks],
        )
        vals = np.where(series.gate & np.isfinite(vals), vals, 0.0)
        out[tier] = vals
    out["traded"] = series.gate & np.isfinite(
        np.where(
            sides == 0,
            series.long_mat["c10"][np.arange(n_days), picks],
            series.short_mat["c10"][np.arange(n_days), picks],
        )
    )
    return out


def window_mask(dates: pd.DatetimeIndex, window: tuple[str, str | None], data_end: pd.Timestamp):
    start, end = window
    end_ts = pd.Timestamp(end) if end else data_end
    return (dates >= pd.Timestamp(start)) & (dates <= end_ts)


def fast_sharpe(ret: np.ndarray, rf: np.ndarray) -> float:
    if len(ret) < 3:
        return float("nan")
    ex = ret - rf
    sd = ex.std(ddof=1)
    return float(ex.mean() / sd * np.sqrt(252.0)) if sd > 0 else float("nan")


def metric_block(
    ret: np.ndarray, rf: np.ndarray, trade_rets: np.ndarray | None, traded: np.ndarray
):
    """Sharpe (rf-excess, ddof=1), plain Sharpe (as idr._daily_sharpe), CAGR, drawdown, trades."""
    n = len(ret)
    if n == 0:
        return {"n_days": 0}
    equity = np.cumprod(1.0 + ret)
    years = n / 252.0
    cagr = float(equity[-1] ** (1.0 / years) - 1.0) if equity[-1] > 0 else -1.0
    peak = np.maximum.accumulate(np.concatenate([[1.0], equity]))[1:]
    plain_sd = ret.std(ddof=0)
    block = {
        "n_days": int(n),
        "n_trade_days": int(traded.sum()),
        "sharpe": fast_sharpe(ret, rf),
        "sharpe_plain": float(ret.mean() / plain_sd * np.sqrt(252.0)) if plain_sd > 0 else None,
        "cagr": cagr,
        "total_return": float(equity[-1] - 1.0),
        "vol": float(ret.std(ddof=1) * np.sqrt(252.0)) if n > 1 else None,
        "max_dd": float((equity / peak - 1.0).min()),
        "win_day_pct": float((ret > 0).mean() * 100.0),
    }
    if not traded.any():
        # a zero-return series has no Sharpe; the rf-excess number would be a cash artifact
        block["sharpe"] = None
        block["sharpe_plain"] = None
        block["note"] = "no trades in this window"
    if trade_rets is not None:
        block["n_trades"] = int(len(trade_rets))
        block["win_rate_trade_pct"] = (
            float((trade_rets > 0).mean() * 100.0) if len(trade_rets) else None
        )
        block["mean_trade_bp"] = float(trade_rets.mean() * 1e4) if len(trade_rets) else None
    return block


def s3_inputs():
    import screen_lane as lane

    close, _open, leg_open, leg_close, rf = lane.load_batch_panel([], None)
    shy_ret = (close[lane.CASH] / close[lane.CASH].shift(1) - 1.0).fillna(0.0)
    s3_ret10, _ = lane.s3_incumbent(close, leg_open, leg_close, lane.COST_BPS_PRIMARY)
    return lane, s3_ret10, shy_ret, rf


def main() -> int:
    t0 = time.time()
    from open_composer.models.strategy_spec import load_strategy_spec

    spec = load_strategy_spec(SPEC_PATH)
    archived = load_strategy_spec(ARCHIVED_SPEC)
    assert spec.position_direction == archived.position_direction == "long_short"
    assert FROZEN_PARAMS.label == FROZEN_LABEL, FROZEN_PARAMS.label
    specs_by_tier = tier_specs(spec)
    orig = archived.costs
    assert (orig.commission_pct, orig.slippage_bps) == COST_TIERS["orig"]

    dataset = build_dataset()
    audit = {"split": split_audit(dataset)}
    unadjusted = [r for r in audit["split"]["known_splits"] if r.get("adjusted_in_data") is False]
    split_handling = "data already split-adjusted (adjustment=all); no rescaling applied"
    if unadjusted:
        factors: dict[str, list[tuple[str, float]]] = {}
        for row in unadjusted:
            factors.setdefault(row["symbol"], []).append((row["split_date"], row["ratio"]))
        dataset = build_dataset(split_factors=factors)
        split_handling = f"unadjusted splits rescaled: {factors}"
        audit["split_after_adjustment"] = split_audit(dataset)
    audit["split_handling"] = split_handling
    audit["completeness"] = completeness_audit(dataset)
    audit["close_vs_daily"] = close_vs_daily_audit(dataset)
    print(
        f"dataset {dataset.dates[0]}..{dataset.dates[-1]} n={len(dataset.dates)} "
        f"{time.time() - t0:.0f}s",
        flush=True,
    )

    series = build_series(dataset, FROZEN_PARAMS, spec, specs_by_tier)
    print(f"series built {time.time() - t0:.0f}s", flush=True)

    # cross-check against the unchanged _backtest_params (both legs, borrow adds nothing when
    # no short trades exist)
    check = {}
    for tier, tspec in specs_by_tier.items():
        metrics = idr._backtest_params(
            tspec, dataset, FROZEN_PARAMS, start_index=0, end_index=len(dataset.dates)
        )
        mine = float(np.prod(1.0 + series.ret["R0"][tier]) - 1.0) * 100.0
        check[tier] = {
            "backtest_params_total_return_pct": metrics.total_return_pct,
            "this_run_total_return_pct": mine,
            "abs_diff": abs(metrics.total_return_pct - mine),
            "backtest_params_sharpe_plain": metrics.sharpe_ratio,
            "backtest_params_traded_days": metrics.traded_days,
            "backtest_params_round_trips": metrics.round_trips,
            "backtest_params_ew_intraday_return_pct": metrics.equal_weight_intraday_return_pct,
            "this_run_ew_return_pct": float(np.prod(1.0 + series.ret["B_ew"][tier]) - 1.0) * 100.0,
        }

    lane, s3_ret10, shy_ret, rf_series = s3_inputs()
    data_end = series.dates[-1]
    rf = rf_series.reindex(series.dates).fillna(0.0).to_numpy()

    def frame(name: str, tier: str, arr: np.ndarray) -> pd.Series:
        return pd.Series(arr, index=series.dates, name=f"{name}_{tier}")

    placebos = {name: placebo_returns(series, seed) for name, seed in PLACEBO_SEEDS.items()}
    trades_df = pd.DataFrame(series.trades)
    results: dict = {
        "iter_id": ITER,
        "generated_at": pd.Timestamp.now(tz="UTC").isoformat(),
        "frozen_label": FROZEN_LABEL,
        "params": {
            "selection_style": FROZEN_PARAMS.selection_style,
            "lookback_days": FROZEN_PARAMS.lookback_days,
            "entry_after_bars": FROZEN_PARAMS.entry_after_bars,
            "top_n": FROZEN_PARAMS.top_n,
            "min_opening_return_pct": FROZEN_PARAMS.min_opening_return_pct,
            "min_prior_momentum_pct": FROZEN_PARAMS.min_prior_momentum_pct,
            "min_relative_volume": FROZEN_PARAMS.min_relative_volume,
            "max_opening_return_pct": FROZEN_PARAMS.max_opening_return_pct,
            "max_prior_momentum_pct": FROZEN_PARAMS.max_prior_momentum_pct,
            "market_gate": FROZEN_PARAMS.market_gate,
        },
        "data": {
            "first_session": dataset.dates[0],
            "last_session": dataset.dates[-1],
            "n_common_sessions": len(dataset.dates),
            "series_first": str(series.dates[0].date()),
            "series_last": str(data_end.date()),
            "note": "series starts lookback_days sessions after the first session",
        },
        "audit": audit,
        "backtest_params_crosscheck": check,
        "iex_record": IEX_RECORD,
        "windows": {k: list(v) for k, v in WINDOWS.items()},
        "candidates": {},
    }

    # candidate metrics
    if not trades_df.empty:
        trades_df["ts"] = pd.to_datetime(trades_df["date"])
    for cand, side_filter in (
        ("R0", None),
        ("R0_long", "long"),
        ("R0_short", "short"),
        ("B_ew", "ew"),
    ):
        results["candidates"][cand] = {}
        for tier in COST_TIERS:
            arr = series.ret[cand][tier]
            results["candidates"][cand][tier] = {}
            for wname, window in WINDOWS.items():
                mask = window_mask(series.dates, window, data_end)
                traded = series.n_trades[cand][mask] > 0
                block = metric_block(arr[mask], rf[mask], None, traded)
                if side_filter != "ew":
                    sub = np.array([])
                    if not trades_df.empty and mask.any():
                        lo, hi = series.dates[mask].min(), series.dates[mask].max()
                        sel = (trades_df["ts"] >= lo) & (trades_df["ts"] <= hi)
                        if side_filter:
                            sel &= trades_df["side"] == side_filter
                        sub = trades_df.loc[sel, f"ret_{tier}"].to_numpy()
                    block["n_trades"] = int(len(sub))
                    block["win_rate_trade_pct"] = (
                        float((sub > 0).mean() * 100.0) if len(sub) else None
                    )
                    block["mean_trade_bp"] = float(sub.mean() * 1e4) if len(sub) else None
                results["candidates"][cand][tier][wname] = block
    # placebos P1-P3
    results["placebos"] = {}
    for name, pl in placebos.items():
        results["placebos"][name] = {"seed": PLACEBO_SEEDS[name]}
        for tier in COST_TIERS:
            results["placebos"][name][tier] = {}
            for wname, window in WINDOWS.items():
                mask = window_mask(series.dates, window, data_end)
                results["placebos"][name][tier][wname] = metric_block(
                    pl[tier][mask], rf[mask], None, pl["traded"][mask]
                )
    # placebo distribution (200 seeds)
    dist = {t: {w: [] for w in WINDOWS} for t in ("c10",)}
    dist_cagr20 = {w: [] for w in WINDOWS}
    for seed in DIST_SEEDS:
        pl = placebo_returns(series, seed)
        for wname, window in WINDOWS.items():
            mask = window_mask(series.dates, window, data_end)
            dist["c10"][wname].append(fast_sharpe(pl["c10"][mask], rf[mask]))
            r20 = pl["c20"][mask]
            eq = float(np.prod(1.0 + r20))
            dist_cagr20[wname].append(eq ** (252.0 / max(len(r20), 1)) - 1.0)
    results["placebo_distribution"] = {
        "n_seeds": len(DIST_SEEDS),
        "seeds": "100000..100199",
        "by_window": {},
    }
    for wname in WINDOWS:
        vals = np.array(dist["c10"][wname], dtype=float)
        r0 = results["candidates"]["R0"]["c10"][wname].get("sharpe")
        finite = vals[np.isfinite(vals)]
        results["placebo_distribution"]["by_window"][wname] = {
            "placebo_sharpe_c10_mean": float(finite.mean()) if len(finite) else None,
            "placebo_sharpe_c10_std": float(finite.std(ddof=1)) if len(finite) > 1 else None,
            "placebo_sharpe_c10_p05": float(np.percentile(finite, 5)) if len(finite) else None,
            "placebo_sharpe_c10_p50": float(np.percentile(finite, 50)) if len(finite) else None,
            "placebo_sharpe_c10_p90": float(np.percentile(finite, 90)) if len(finite) else None,
            "placebo_sharpe_c10_p95": float(np.percentile(finite, 95)) if len(finite) else None,
            "placebo_sharpe_c10_max": float(finite.max()) if len(finite) else None,
            "r0_sharpe_c10": r0,
            "share_of_placebos_below_r0": float((finite < r0).mean())
            if (len(finite) and r0 is not None and np.isfinite(r0))
            else None,
            "placebo_cagr_c20_median": float(np.median(dist_cagr20[wname])),
            "share_of_placebos_cagr_c20_positive": float((np.array(dist_cagr20[wname]) > 0).mean()),
        }
    p_share = {}
    r0_anchor = results["candidates"]["R0"]["c10"]["anchor"]["sharpe"]
    for name in placebos:
        p_share[name] = {
            "placebo_anchor_sharpe_c10": results["placebos"][name]["c10"]["anchor"]["sharpe"],
            "r0_beats": bool(r0_anchor > results["placebos"][name]["c10"]["anchor"]["sharpe"]),
        }
    results["placebo_p1_p3_anchor"] = p_share

    # ---- S3 and K1/K2
    anchor_s3_end = min(data_end, pd.Timestamp("2026-09-17"))
    anchor_win_s3 = ("2024-01-08", str(anchor_s3_end.date()))
    r0_c10 = frame("R0", "c10", series.ret["R0"]["c10"])
    s3_win_metrics = {}
    for wname, window in WINDOWS.items():
        end = window[1] or str(anchor_s3_end.date())
        if pd.Timestamp(end) > anchor_s3_end:
            end = str(anchor_s3_end.date())
        w = (window[0], end)
        mask = (s3_ret10.index >= w[0]) & (s3_ret10.index <= w[1])
        if mask.sum() < 3:
            s3_win_metrics[wname] = {"n_days": int(mask.sum())}
            continue
        m = lane.base.metrics(
            s3_ret10.loc[mask], rf_series, pd.Series(0.0, index=s3_ret10.index[mask])
        )
        s3_win_metrics[wname] = {
            "n_days": m.days,
            "sharpe": m.sharpe,
            "cagr": m.cagr,
            "max_dd": m.max_dd,
        }
    results["s3_offset0_c10_reference"] = {
        "windows": s3_win_metrics,
        "note": "S3 series ends 2026-09-17 (HOLD_END in run_h20260918_05_recent_menu.py)",
    }
    edges, corrs = {}, {}
    for wname in ("anchor", "select", "holdout_contaminated"):
        window = WINDOWS[wname]
        end = window[1] or str(anchor_s3_end.date())
        end = min(pd.Timestamp(end), anchor_s3_end)
        w = (window[0], str(end.date()))
        edges[wname] = float(
            lane.diversifier_edge_for_offset(s3_ret10, r0_c10, shy_ret, rf_series, w)
        )
        corrs[wname] = float(lane.correlation_with_s3(r0_c10, s3_ret10, w))
    results["k2_inputs"] = {
        "edge_by_window": edges,
        "correlation_with_s3_by_window": corrs,
        "window_used_for_k2": list(anchor_win_s3),
        "s3_offset": 0,
        "offset_note": (
            "R0 trades every day; only S3 offset 0 is reported "
            "(no rebalance-date offset for the candidate)"
        ),
        "lane_threshold": lane.DIVERSIFIER_SHARPE_EDGE_MIN,
    }

    r0a10 = results["candidates"]["R0"]["c10"]["anchor"]
    r0a20 = results["candidates"]["R0"]["c20"]["anchor"]
    k1_sharpe = r0a10["sharpe"]
    k1_cagr20 = r0a20["cagr"]
    k1 = bool(k1_sharpe >= 1.19 and k1_cagr20 > 0)
    k2_edge = edges["anchor"]
    k2 = bool(k2_edge >= 0.05)
    share = results["placebo_distribution"]["by_window"]["anchor"]["share_of_placebos_below_r0"]
    g3 = bool(share is not None and share >= 0.90)
    if k1 and k2 and g3:
        status = "kept"
    elif k1:
        status = "partial"
    else:
        status = "refuted"
    results["decision"] = {
        "K1": {
            "pass": k1,
            "anchor_sharpe_c10": k1_sharpe,
            "anchor_sharpe_plain_c10": r0a10["sharpe_plain"],
            "threshold_sharpe": 1.19,
            "anchor_cagr_c20": k1_cagr20,
            "source": "candidates.R0.c10.anchor.sharpe and candidates.R0.c20.anchor.cagr",
        },
        "K2": {
            "pass": k2,
            "combo_edge_vs_s3": k2_edge,
            "threshold": 0.05,
            "lane_threshold_0p10_pass": bool(k2_edge >= lane.DIVERSIFIER_SHARPE_EDGE_MIN),
            "window": list(anchor_win_s3),
            "source": "k2_inputs.edge_by_window.anchor",
        },
        "G3": {
            "pass": g3,
            "share_of_200_placebos_below_r0_anchor_sharpe_c10": share,
            "threshold": 0.90,
            "source": "placebo_distribution.by_window.anchor",
        },
        "stress": (
            "pending (待补压力期): no minute data before 2023-01; "
            "partial_stress_2023_01_08 is reported only"
        ),
        "registry_status": status,
        "workflow_pass": True,
        "research_pass": bool(status == "kept"),
        "llm_contribution_pass": False,
        "paper_ready_pass": False,
    }
    results["structure_checks"] = {
        "r0_equals_r0_long_all_tiers": bool(
            all(np.allclose(series.ret["R0"][t], series.ret["R0_long"][t]) for t in COST_TIERS)
        ),
        "r0_short_total_trades": int(series.n_trades["R0_short"].sum()),
        "r0_total_trades": int(series.n_trades["R0"].sum()),
        "gate_days": int(series.gate.sum()),
        "session_days_in_series": int(len(series.dates)),
    }
    results["runtime_seconds"] = time.time() - t0

    # ---- write
    ITER_DIR.mkdir(parents=True, exist_ok=True)
    out = pd.DataFrame(index=series.dates)
    for cand in ("R0", "R0_long", "R0_short", "B_ew"):
        for tier in COST_TIERS:
            out[f"{cand}_{tier}"] = series.ret[cand][tier]
    for name, pl in placebos.items():
        for tier in COST_TIERS:
            out[f"{name}_{tier}"] = pl[tier]
    out["qqq_gate"] = series.gate
    out.index.name = "date"
    out.to_csv(ITER_DIR / "daily_returns.csv", float_format="%.8f")
    if not trades_df.empty:
        trades_df.drop(columns=["ts"], errors="ignore").to_csv(
            ITER_DIR / "r0_trades.csv", index=False, float_format="%.8f"
        )
    (ITER_DIR / "results.json").write_text(
        json.dumps(results, indent=2, default=float), encoding="utf-8"
    )
    ledger = ITER_DIR / "trial-ledger.jsonl"
    with ledger.open("w", encoding="utf-8") as handle:
        for cand in ("R0", "R0_long", "R0_short", "B_ew"):
            handle.write(
                json.dumps(
                    {
                        "candidate_id": cand,
                        "anchor_c10": results["candidates"][cand]["c10"]["anchor"],
                        "anchor_c20": results["candidates"][cand]["c20"]["anchor"],
                    },
                    default=float,
                )
                + "\n"
            )
        for name in placebos:
            handle.write(
                json.dumps(
                    {
                        "candidate_id": name,
                        "anchor_c10": results["placebos"][name]["c10"]["anchor"],
                    },
                    default=float,
                )
                + "\n"
            )
    print(json.dumps(results["decision"], indent=2, default=float), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
