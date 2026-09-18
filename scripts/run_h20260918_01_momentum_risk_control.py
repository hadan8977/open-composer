"""H-20260918-01: can pure portfolio-construction changes on the M0B momentum
score make a cell beat SPMO on *both* CAGR and max drawdown in the ledger's
own contract window (2024-01-08 .. 2026-09-16)?

Card: ``reports/research/hypotheses/H-20260918-01-risk-controlled-momentum-vs-spmo.md``
Existing momentum grid this reuses cell construction / metric helpers from:
``scripts/run_step13_m_grid.py`` (M0B: score column, ``adv_rank <= 500``,
top-50 equal weight, ``next_open`` execution, 10bp/side) and
``open_composer.research.kernel.loop`` (``returns_from_weight_schedule``,
price hygiene, ``universe_as_of_calendar_month``). Stage/cache/report shape
and the benchmark + random-control helper style are copied from
``scripts/run_h20260917_01_insider_independent.py``.

Design (the card's grid, with two disclosed implementation choices below)
---------------------------------------------------------------------------
* Selection is fixed and untouched: score = ``momentum_252_21 / vol_63`` (the
  same ratio M0B's ``momentum_252_21_over_vol_63`` cells use), universe
  ``adv_rank <= 500`` of the PIT monthly cohort (``universe_as_of_calendar_month``),
  top 50, equal weight (2% each), **monthly** formation (month-end signal,
  next-open execution, 10bp/side) -- the card's own spec. This is a real,
  disclosed methodology difference from M0B's own *weekly* Friday-signal
  cadence (``build_weight_schedule`` only ever rebalances on
  ``weekly_rebalance_dates``, so it cannot produce a monthly schedule without
  modifying a file this round is not allowed to touch); the "no risk control
  at all" cell of this grid (``none`` x ``gate_off``) is therefore a
  monthly-cadence *reconstruction* of the same rule, not a byte-for-byte
  reproduction of the ledger's ``step13_m0b_mom_over_vol63_uni500_k50_gate_off``
  row, and the two are expected to differ somewhat.
* Knob 1, volatility targeting -- {none, 20%/21d, 20%/63d, 25%/21d, 25%/63d}.
  Realized volatility is estimated from the **raw, unscaled, gate-off**
  monthly momentum book's own trailing daily returns (not the gated book):
  the card says "the book's own trailing daily returns" without saying which
  book, and estimating off the ungated raw signal avoids a circularity where
  cash months (from a closed gate) would otherwise flatter the trailing
  vol estimate right when the gate reopens. Only information available at
  the formation date is used (rolling window ending at, and including, that
  date's close); a formation date with fewer than ``window`` trading days of
  book history gets no scaling (``scale = 1.0``), which only affects the
  first few 2016 months, well outside both reported windows' bulk of
  observations. Exposure is capped at 1.0 (never leveraged); the unused
  fraction sits in BIL.
* Knob 2, trend gate -- {off, SPY > its 200sma, SPY and QQQ both > their
  200sma}; cash leg BIL. SPY's ``spy_gap_200sma`` is the same PIT column
  ``build_step13_regime_daily_features.py`` builds and M0/M0b's own gate
  reads (``data/features/regime_daily``). That table has no QQQ column, so
  QQQ's own 200-day SMA gap is computed locally here, by the exact same
  convention (``close / close.rolling(200, min_periods=200).mean() - 1``,
  gate open iff > 0) from ``data/sip/daily`` -- never a different rule for
  the two legs.
* Knob 3, concentration -- **skipped**. The card's fallback ("if no usable
  sector field exists, skip this knob entirely and say so, rather than
  inventing one") applies: the only local classification table,
  ``data/features/universe/_asset_metadata.parquet``, has columns
  ``symbol, name, exchange, tradable, fractionable, status,
  is_probable_fund_or_etf`` -- no sector/SIC/industry field anywhere in it,
  and no such field exists on the Alpaca asset objects this repo ingests
  either. Per-name 2% is already satisfied by equal-weight top-50 and is not
  re-parametrized. The grid is therefore **5 x 3 = 15 cells**, not 30.
* Placebo: the trend-gate boolean series (SPY-only and SPY+QQQ) is shifted
  by a random nonzero offset in [-21, 21] trading days, 5 seeds, applied
  (vol target = none) to isolate the gate's own effect from vol targeting.

Reference-only round: nothing here writes ``reports/research/ledger/experiments.jsonl``.

Stages (each resumable from ``reports/research/iterations/<id>/cache/``)
--------------------------------------------------------------------------
``weights``  universe/price/benchmark loading, raw top-50 tranches, the raw
             book's own trailing realized vol, SPY/QQQ trend-gate series,
             the 15 real + 10 placebo weight schedules (cached as JSON).
``returns``  prices every cached schedule (10bp; the 15 real cells also at
             25bp stress) via ``returns_from_weight_schedule``.
``report``   metrics, BH-FDR, the SPMO/benchmark comparison, the gate
             placebo check, ``summary.json`` and ``report.md``.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import pyarrow.parquet as pq  # noqa: E402

from open_composer.adapters.data.sip_parquet import load_sip_bars  # noqa: E402
from open_composer.research.features.panel import load_price_panel  # noqa: E402
from open_composer.research.features.universe import load_universe_panel  # noqa: E402
from open_composer.research.kernel.loop import (  # noqa: E402
    DEFAULT_MIN_COHORT_SYMBOLS,
    RebalanceEvent,
    returns_from_weight_schedule,
    universe_as_of_calendar_month,
)
from open_composer.research.kernel.mechanism_eval import annualized_cagr, max_drawdown  # noqa: E402
from open_composer.research.kernel.pick_export import turnover_per_rebalance  # noqa: E402
from open_composer.research.kernel.vol_matched import (  # noqa: E402
    cagr_excess_vol_matched,
    vol_match_weight,
)

ITERATION_ID = "h20260918_01_momentum_risk_control"
OUT_DIR = ROOT / "reports" / "research" / "iterations" / ITERATION_ID
CACHE_DIR = OUT_DIR / "cache"
SUMMARY_PATH = OUT_DIR / "summary.json"
REPORT_PATH = OUT_DIR / "report.md"

UNIVERSE_ROOT = ROOT / "data" / "features" / "universe"
DAILY_ROOT = ROOT / "data" / "features" / "daily"

PRIMARY_COST_BPS = 10.0
STRESS_COST_BPS = 25.0
EXECUTION = "next_open"
CASH_SYMBOL = "BIL"
UNIVERSE_TOP_N = 500
TOP_K = 50
SMA_WINDOW = 200
DATA_START = "2016-01-04"
YEARS: tuple[int, ...] = tuple(range(2016, 2027))

HEADLINE_START = "2024-01-08"
HEADLINE_END = "2026-09-16"
DISCLOSURE_END = "2023-12-31"

BENCHMARK_SYMBOLS: tuple[str, ...] = ("SPY", "SPMO", "MTUM", "IWM", "QQQ", "RSP")
GATE_SOURCE_SYMBOLS: tuple[str, ...] = ("SPY", "QQQ")

VOL_TARGET_ORDER: tuple[str, ...] = ("none", "t20_w21", "t20_w63", "t25_w21", "t25_w63")
VOL_TARGET_DEFS: dict[str, tuple[float, int] | None] = {
    "none": None,
    "t20_w21": (0.20, 21),
    "t20_w63": (0.20, 63),
    "t25_w21": (0.25, 21),
    "t25_w63": (0.25, 63),
}
VOL_TARGET_LABELS = {
    "none": "不控制",
    "t20_w21": "20%（21日窗）",
    "t20_w63": "20%（63日窗）",
    "t25_w21": "25%（21日窗）",
    "t25_w63": "25%（63日窗）",
}

GATE_ORDER: tuple[str, ...] = ("gate_off", "gate_spy", "gate_spy_qqq")
GATE_DEFS: dict[str, tuple[str, ...]] = {
    "gate_off": (),
    "gate_spy": ("SPY",),
    "gate_spy_qqq": ("SPY", "QQQ"),
}
GATE_LABELS = {
    "gate_off": "关",
    "gate_spy": "SPY > 200日均线",
    "gate_spy_qqq": "SPY 和 QQQ 都 > 200日均线",
}

CONCENTRATION_OPTIONS: tuple[str, ...] = ("per_name_2pct",)
CONCENTRATION_SKIP_NOTE = (
    "集中度第二档（单只 2% + 单行业 ≤ 20%）本轮跳过：本地唯一的资产分类表 "
    "data/features/universe/_asset_metadata.parquet 只有 symbol / name / exchange / "
    "tradable / fractionable / status / is_probable_fund_or_etf 七个字段，没有行业或 "
    "SIC 分类；摄取的 Alpaca 资产字段里也没有行业。按卡片的兜底规则，跳过这个子开关，"
    "不发明一个分类；单只 2% 已经由等权 top50 满足，不再单独参数化。"
    "网格因此是 5 x 3 = 15 个单元，不是 30 个。"
)
CADENCE_CAVEAT = (
    "方法学披露：本轮按卡片要求用月频形成（月末信号→次月开盘成交），"
    "而 M0B 账本自己的单元用的是 build_weight_schedule 内置的周频（周五信号→"
    "周一开盘）；build_weight_schedule 不支持月频且本轮不允许改动它，"
    "所以本网格的 none/gate_off 单元是同一条选股规则的月频重建，"
    "不是账本 step13_m0b_mom_over_vol63_uni500_k50_gate_off 那一行的逐字节复现，"
    "两者数字预期不完全相同。"
)

PLACEBO_SEEDS: tuple[int, ...] = (1, 2, 3, 4, 5)
PLACEBO_SHIFT_DAYS = 21
PLACEBO_GATES: tuple[str, ...] = ("gate_spy", "gate_spy_qqq")

_T0 = time.time()


def _log(message: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')} +{time.time() - _T0:7.1f}s] {message}", flush=True)


def _json_default(value: Any) -> Any:
    if isinstance(value, pd.Timestamp):
        return value.date().isoformat()
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


def cell_key(vol_key: str, gate_key: str) -> str:
    return f"{vol_key}__{gate_key}"


# --------------------------------------------------------------------------
# shared small helpers (pattern copied from run_h20260917_01_insider_independent.py)
# --------------------------------------------------------------------------


def monthly_returns(series: pd.Series) -> pd.Series:
    return (1.0 + series).groupby(series.index.to_period("M")).prod() - 1.0


def nw_tstat(values: np.ndarray, lag: int) -> float:
    """Newey-West (Bartlett) t-statistic of the mean. ``lag = 0`` for this
    round's plain (non-overlapping) monthly rebalance -- one formation date
    per calendar month, so calendar-month excess returns carry no
    construction-induced overlap the way a multi-month overlapping-tranche
    book would.
    """
    clean = np.asarray(values, dtype="float64")
    clean = clean[np.isfinite(clean)]
    n = len(clean)
    if n < 6:
        return float("nan")
    mean = clean.mean()
    resid = clean - mean
    variance = float(resid @ resid) / n
    for lag_ in range(1, min(lag, n - 1) + 1):
        weight = 1.0 - lag_ / (lag + 1.0)
        variance += 2.0 * weight * float(resid[lag_:] @ resid[:-lag_]) / n
    if variance <= 0:
        return float("nan")
    return float(mean / math.sqrt(variance / n))


def excess_block(strategy: pd.Series, benchmark: pd.Series, lag: int = 0) -> dict[str, Any]:
    aligned = benchmark.reindex(strategy.index).fillna(0.0)
    ex = monthly_returns(strategy) - monthly_returns(aligned)
    values = ex.to_numpy(dtype="float64")
    return {
        "mean_monthly_excess": float(np.nanmean(values)) if len(values) else None,
        "t_nw": nw_tstat(values, lag),
        "months": int(len(values)),
    }


def _one_sided_p(t: float | None) -> float | None:
    if t is None or not math.isfinite(t):
        return None
    return float(0.5 * math.erfc(t / math.sqrt(2.0)))


def bh_fdr_pass_count(pvalues: list[float | None], q: float = 0.10) -> int:
    clean = sorted(p for p in pvalues if p is not None and math.isfinite(p))
    m = len(clean)
    if m == 0:
        return 0
    passed = 0
    for i, p in enumerate(clean, start=1):
        if p <= q * i / m:
            passed = i
    return passed


def window_metrics(
    series: pd.Series | None,
    window_start: str | None,
    window_end: str | None,
    bench: pd.DataFrame,
) -> dict[str, Any] | None:
    if series is None or series.empty:
        return None
    sliced = series
    if window_start is not None:
        sliced = sliced.loc[sliced.index >= pd.Timestamp(window_start)]
    if window_end is not None:
        sliced = sliced.loc[sliced.index <= pd.Timestamp(window_end)]
    if sliced.empty:
        return None
    out: dict[str, Any] = {
        "cagr": annualized_cagr(sliced),
        "max_drawdown": max_drawdown(sliced),
        "vol": float(sliced.std() * math.sqrt(252.0)),
        "sessions": int(len(sliced)),
        "window": [sliced.index[0].date().isoformat(), sliced.index[-1].date().isoformat()],
    }
    try:
        out["vol_matched_excess_spy"] = cagr_excess_vol_matched(
            sliced, bench["SPY"].fillna(0.0), bench[CASH_SYMBOL].fillna(0.0)
        )
        out["vol_match_weight_vs_spy"] = vol_match_weight(sliced, bench["SPY"].fillna(0.0))
    except ValueError:
        out["vol_matched_excess_spy"] = None
        out["vol_match_weight_vs_spy"] = None
    out["excess"] = {sym: excess_block(sliced, bench[sym].fillna(0.0)) for sym in BENCHMARK_SYMBOLS}
    return out


# --------------------------------------------------------------------------
# stage: weights
# --------------------------------------------------------------------------


def _benchmark_prices(symbols: tuple[str, ...]) -> tuple[pd.DataFrame, pd.DataFrame]:
    raw = load_sip_bars(list(symbols), frequency="daily", start=DATA_START)
    raw["timestamp"] = pd.to_datetime(raw["timestamp"], utc=True)
    raw["trade_date"] = pd.to_datetime(raw["timestamp"].dt.date)
    raw = raw.sort_values(["symbol", "timestamp"]).drop_duplicates(
        ["symbol", "trade_date"], keep="last"
    )
    close = raw.pivot(index="trade_date", columns="symbol", values="close").astype("float64")
    open_ = raw.pivot(index="trade_date", columns="symbol", values="open").astype("float64")
    return close.sort_index(), open_.sort_index()


def _sma200_gap(close: pd.Series) -> pd.Series:
    sma = close.rolling(SMA_WINDOW, min_periods=SMA_WINDOW).mean()
    return close / sma - 1.0


def _load_scores(years: tuple[int, ...], wanted_dates: set[pd.Timestamp]) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for year in years:
        path = DAILY_ROOT / f"{year}.parquet"
        if not path.exists():
            continue
        table = pq.read_table(path, columns=["symbol", "trade_date", "momentum_252_21", "vol_63"])
        frame = table.to_pandas()
        del table
        frame["trade_date"] = pd.to_datetime(frame["trade_date"])
        frame = frame.loc[frame["trade_date"].isin(wanted_dates)]
        if frame.empty:
            continue
        frame["symbol"] = frame["symbol"].astype(str)
        frames.append(frame.copy())
    if not frames:
        raise SystemExit("weights: no momentum_252_21/vol_63 rows found at any formation date")
    out = pd.concat(frames, ignore_index=True)
    out["momentum_252_21"] = pd.to_numeric(out["momentum_252_21"], errors="coerce")
    out["vol_63"] = pd.to_numeric(out["vol_63"], errors="coerce")
    return out


Tranches = dict[pd.Timestamp, dict[str, float]]


def _build_raw_tranches(
    score_frame: pd.DataFrame, universe: pd.DataFrame, formation_dates: list[pd.Timestamp]
) -> Tranches:
    tranches: Tranches = {}
    for date in formation_dates:
        cohort = universe_as_of_calendar_month(universe, date, top_n=UNIVERSE_TOP_N)
        rows = score_frame.loc[
            (score_frame["trade_date"] == date) & score_frame["symbol"].isin(cohort)
        ].dropna(subset=["score"])
        if rows.empty:
            tranches[date] = {}
            continue
        top = rows.sort_values(["score", "symbol"], ascending=[False, True]).head(TOP_K)
        weight = 1.0 / len(top)
        tranches[date] = {str(s): weight for s in top["symbol"]}
    return tranches


def _events_from_tranches(tranches: Tranches, dates: list[pd.Timestamp]) -> list[RebalanceEvent]:
    events = []
    for date in dates:
        tranche = tranches.get(date, {})
        weights = dict(tranche) if tranche else {CASH_SYMBOL: 1.0}
        events.append(
            RebalanceEvent(
                date=date.isoformat(),
                universe_size=len(tranche),
                selected=weights,
                portfolio_beta=None,
            )
        )
    return events


def _price_events(
    events: list[RebalanceEvent],
    close_wide: pd.DataFrame,
    open_wide: pd.DataFrame,
    spy_returns: pd.Series,
    cost_bps: float,
) -> tuple[pd.Series, int]:
    held = sorted({s for e in events for s in e.selected})
    columns = [s for s in held if s in close_wide.columns]
    missing = len(held) - len(columns)
    if CASH_SYMBOL not in columns:
        columns.append(CASH_SYMBOL)
    returns = returns_from_weight_schedule(
        events,
        close_wide[columns],
        spy_returns,
        cost_bps_per_side=cost_bps,
        include_hedge=False,
        execution=EXECUTION,
        open_wide=open_wide[columns],
    )
    return returns, missing


def _build_cell_schedule(
    raw_tranches: Tranches,
    formation_dates: list[pd.Timestamp],
    gate_series: pd.Series,
    realized_vol: dict[int, pd.Series],
    vol_target: tuple[float, int] | None,
) -> tuple[list[RebalanceEvent], list[dict[str, Any]]]:
    events: list[RebalanceEvent] = []
    diagnostics: list[dict[str, Any]] = []
    for date in formation_dates:
        tranche = raw_tranches.get(date, {})
        gate_value = gate_series.get(date, False)
        gate_open = bool(gate_value) if pd.notna(gate_value) else False
        scale = 1.0
        if vol_target is not None and tranche and gate_open:
            target, window = vol_target
            realized = realized_vol[window].get(date, float("nan"))
            if realized is not None and math.isfinite(realized) and realized > 0:
                scale = min(1.0, target / realized)
        if not gate_open or not tranche:
            weights = {CASH_SYMBOL: 1.0}
        else:
            weights = {symbol: w * scale for symbol, w in tranche.items()}
            if scale < 1.0 - 1e-9:
                weights[CASH_SYMBOL] = weights.get(CASH_SYMBOL, 0.0) + (1.0 - scale)
        events.append(
            RebalanceEvent(
                date=date.isoformat(),
                universe_size=len(tranche),
                selected=weights,
                portfolio_beta=None,
            )
        )
        diagnostics.append(
            {
                "date": date.date().isoformat(),
                "gate_open": gate_open,
                "scale": scale,
                "tranche_size": len(tranche),
            }
        )
    return events, diagnostics


def _events_to_json(events: list[RebalanceEvent]) -> list[dict[str, Any]]:
    return [
        {"date": e.date, "universe_size": e.universe_size, "selected": e.selected} for e in events
    ]


def _events_from_json(data: list[dict[str, Any]]) -> list[RebalanceEvent]:
    return [
        RebalanceEvent(
            date=row["date"],
            universe_size=row["universe_size"],
            selected=row["selected"],
            portfolio_beta=None,
        )
        for row in data
    ]


def stage_weights(args: argparse.Namespace) -> None:
    manifest_path = CACHE_DIR / "manifest.json"
    if manifest_path.exists() and not args.force:
        _log(f"weights: {manifest_path} exists -- reusing (pass --force to rebuild)")
        return
    _log(CONCENTRATION_SKIP_NOTE)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    (CACHE_DIR / "schedules").mkdir(parents=True, exist_ok=True)
    (CACHE_DIR / "diagnostics").mkdir(parents=True, exist_ok=True)

    _log("weights: loading universe panel ...")
    universe = load_universe_panel(UNIVERSE_ROOT, years=list(YEARS))
    universe["month_end"] = pd.to_datetime(universe["month_end"])
    universe["symbol"] = universe["symbol"].astype(str)
    cohort_sizes = universe.groupby("month_end").size()
    formation_dates = sorted(
        pd.Timestamp(d) for d, n in cohort_sizes.items() if n >= DEFAULT_MIN_COHORT_SYMBOLS
    )
    _log(
        f"weights: {len(formation_dates)} monthly formation dates "
        f"{formation_dates[0].date()}..{formation_dates[-1].date()}"
    )

    _log("weights: loading equity price panel (DuckDB memory_limit=700MB) ...")
    price_long = load_price_panel(years=list(YEARS), memory_limit="700MB")
    close_wide = price_long.pivot(index="trade_date", columns="symbol", values="close")
    open_wide = price_long.pivot(index="trade_date", columns="symbol", values="open")
    del price_long
    close_wide = close_wide.sort_index()
    open_wide = open_wide.reindex(close_wide.index)
    close_wide.columns = close_wide.columns.astype(str)
    open_wide.columns = open_wide.columns.astype(str)

    _log("weights: loading benchmark/cash prices ...")
    bench_symbols = tuple(dict.fromkeys((*BENCHMARK_SYMBOLS, CASH_SYMBOL)))
    bench_close, bench_open = _benchmark_prices(bench_symbols)
    bench_close = bench_close.reindex(close_wide.index)
    bench_open = bench_open.reindex(close_wide.index)
    close_wide[CASH_SYMBOL] = bench_close[CASH_SYMBOL]
    open_wide[CASH_SYMBOL] = bench_open[CASH_SYMBOL]
    bench_returns = bench_close.pct_change(fill_method=None)
    bench_returns.index.name = "trade_date"

    price_index = close_wide.index
    price_index_set = set(price_index)
    formation_dates = [
        d
        for d in formation_dates
        if d in price_index_set and price_index.searchsorted(d, side="right") + 1 < len(price_index)
    ]
    _log(
        f"weights: {len(formation_dates)} formation dates usable after price-coverage filter, "
        f"last price date {price_index[-1].date()}"
    )

    _log("weights: loading momentum_252_21 / vol_63 scores at formation dates ...")
    score_frame = _load_scores(YEARS, set(formation_dates))
    score_frame["score"] = (score_frame["momentum_252_21"] / score_frame["vol_63"]).replace(
        [np.inf, -np.inf], np.nan
    )

    _log("weights: building raw top-50 momentum tranches ...")
    raw_tranches = _build_raw_tranches(score_frame, universe, formation_dates)
    raw_events = _events_from_tranches(raw_tranches, formation_dates)
    spy_returns = bench_returns["SPY"].fillna(0.0)
    raw_returns, raw_missing = _price_events(
        raw_events, close_wide, open_wide, spy_returns, PRIMARY_COST_BPS
    )
    _log(
        f"weights: raw (none/gate_off) book priced -- {len(raw_returns)} sessions, "
        f"missing_symbols={raw_missing}"
    )

    # No fillna here: pre-inception days must stay NaN so rolling(..., min_periods=window)
    # correctly refuses to produce a realized-vol estimate until `window` *real* trading
    # days of the book's own history exist (a fillna(0.0) would silently mix in
    # zero-variance pre-inception days and understate the earliest windows' realized vol).
    raw_full = raw_returns.reindex(price_index)
    realized_vol = {
        window: raw_full.rolling(window, min_periods=window).std() * math.sqrt(252.0)
        for window in (21, 63)
    }

    _log("weights: computing SPY / QQQ 200-day SMA trend-gate series ...")
    gap = {sym: _sma200_gap(bench_close[sym]) for sym in GATE_SOURCE_SYMBOLS}
    daily_gate: dict[str, pd.Series] = {}
    for gate_key, syms in GATE_DEFS.items():
        if not syms:
            daily_gate[gate_key] = pd.Series(True, index=price_index)
            continue
        gate_open = pd.Series(True, index=price_index)
        for sym in syms:
            aligned = gap[sym].reindex(price_index)
            gate_open &= (aligned > 0.0).fillna(False)
        daily_gate[gate_key] = gate_open

    wanted_vol = args.vol_targets or list(VOL_TARGET_ORDER)
    wanted_gates = args.gates or list(GATE_ORDER)
    cells_built = []
    for vol_key in VOL_TARGET_ORDER:
        if vol_key not in wanted_vol:
            continue
        for gate_key in GATE_ORDER:
            if gate_key not in wanted_gates:
                continue
            events, diagnostics = _build_cell_schedule(
                raw_tranches,
                formation_dates,
                daily_gate[gate_key],
                realized_vol,
                VOL_TARGET_DEFS[vol_key],
            )
            key = cell_key(vol_key, gate_key)
            _write_json(CACHE_DIR / "schedules" / f"{key}.json", _events_to_json(events))
            _write_json(CACHE_DIR / "diagnostics" / f"{key}.json", diagnostics)
            cells_built.append(key)
    _log(f"weights: built {len(cells_built)} real cell schedules: {cells_built}")

    _log("weights: building gate placebo schedules (vol_target=none) ...")
    seeds = PLACEBO_SEEDS[: args.seeds] if args.seeds else PLACEBO_SEEDS
    placebo_built = []
    for gate_key in PLACEBO_GATES:
        for seed in seeds:
            rng = np.random.default_rng([int(seed), list(GATE_DEFS).index(gate_key)])
            choices = [d for d in range(-PLACEBO_SHIFT_DAYS, PLACEBO_SHIFT_DAYS + 1) if d != 0]
            shift = int(rng.choice(choices))
            shifted_gate = daily_gate[gate_key].shift(shift, fill_value=False)
            events, diagnostics = _build_cell_schedule(
                raw_tranches, formation_dates, shifted_gate, realized_vol, None
            )
            key = f"placebo__{gate_key}__seed{seed}"
            _write_json(CACHE_DIR / "schedules" / f"{key}.json", _events_to_json(events))
            _write_json(
                CACHE_DIR / "diagnostics" / f"{key}.json",
                {"shift_days": shift, "events": diagnostics},
            )
            placebo_built.append((key, shift))
    _log(f"weights: built {len(placebo_built)} placebo schedules: {placebo_built}")

    close_wide.to_parquet(CACHE_DIR / "close_wide.parquet")
    open_wide.to_parquet(CACHE_DIR / "open_wide.parquet")
    bench_returns.to_parquet(CACHE_DIR / "bench_returns.parquet")

    manifest = {
        "iteration_id": ITERATION_ID,
        "universe_top_n": UNIVERSE_TOP_N,
        "top_k": TOP_K,
        "score_column": "momentum_252_21 / vol_63",
        "execution": EXECUTION,
        "cost_bps_per_side": PRIMARY_COST_BPS,
        "stress_cost_bps_per_side": STRESS_COST_BPS,
        "formation_dates": [d.date().isoformat() for d in formation_dates],
        "price_last_date": price_index[-1].date().isoformat(),
        "raw_book_missing_symbols": raw_missing,
        "vol_target_defs": {k: v for k, v in VOL_TARGET_DEFS.items()},
        "gate_defs": {k: list(v) for k, v in GATE_DEFS.items()},
        "concentration_options": list(CONCENTRATION_OPTIONS),
        "concentration_skip_note": CONCENTRATION_SKIP_NOTE,
        "cadence_caveat": CADENCE_CAVEAT,
        "cells_built": cells_built,
        "placebo_built": [{"key": k, "shift_days": s} for k, s in placebo_built],
    }
    _write_json(manifest_path, manifest)
    _log("weights: done")


# --------------------------------------------------------------------------
# stage: returns
# --------------------------------------------------------------------------


def _save_returns(path: Path, series: pd.Series) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame({"trade_date": series.index, "ret": series.to_numpy(dtype="float64")})
    frame.to_parquet(path, index=False)


def _load_returns(path: Path) -> pd.Series | None:
    if not path.exists():
        return None
    frame = pd.read_parquet(path)
    series = pd.Series(
        frame["ret"].to_numpy(dtype="float64"), index=pd.to_datetime(frame["trade_date"])
    )
    return series.sort_index()


def stage_returns(args: argparse.Namespace) -> None:
    schedules_dir = CACHE_DIR / "schedules"
    if not schedules_dir.exists():
        raise SystemExit("returns: run --stage weights first")
    close_wide = pd.read_parquet(CACHE_DIR / "close_wide.parquet")
    open_wide = pd.read_parquet(CACHE_DIR / "open_wide.parquet")
    bench_returns = pd.read_parquet(CACHE_DIR / "bench_returns.parquet")
    spy_returns = bench_returns["SPY"].fillna(0.0)

    returns_dir = CACHE_DIR / "returns"
    stress_dir = CACHE_DIR / "returns_stress"
    returns_dir.mkdir(parents=True, exist_ok=True)
    stress_dir.mkdir(parents=True, exist_ok=True)

    done, skipped = 0, 0
    for schedule_path in sorted(schedules_dir.glob("*.json")):
        key = schedule_path.stem
        out_path = returns_dir / f"{key}.parquet"
        is_real_cell = not key.startswith("placebo__")
        stress_path = stress_dir / f"{key}.parquet"
        already_done = out_path.exists() and (not is_real_cell or stress_path.exists())
        if already_done and not args.force:
            skipped += 1
            continue
        events = _events_from_json(json.loads(schedule_path.read_text()))
        returns, missing = _price_events(
            events, close_wide, open_wide, spy_returns, PRIMARY_COST_BPS
        )
        _save_returns(out_path, returns)
        if is_real_cell:
            stress_returns, _ = _price_events(
                events, close_wide, open_wide, spy_returns, STRESS_COST_BPS
            )
            _save_returns(stress_path, stress_returns)
        done += 1
        _log(f"returns: {key} done (missing_symbols={missing})")
    _log(f"returns: finished -- {done} priced, {skipped} reused")


# --------------------------------------------------------------------------
# stage: report
# --------------------------------------------------------------------------


def _turnover_series(events: list[RebalanceEvent]) -> pd.Series:
    active = [e for e in events if e.selected]
    values = turnover_per_rebalance(events)
    dates = [pd.Timestamp(e.date) for e in active]
    return pd.Series(values, index=pd.DatetimeIndex(dates))


def _reduced_months(diagnostics: list[dict[str, Any]], start: str, end: str) -> dict[str, int]:
    start_ts, end_ts = pd.Timestamp(start), pd.Timestamp(end)
    in_window = [d for d in diagnostics if start_ts <= pd.Timestamp(d["date"]) <= end_ts]
    gate_closed = sum(1 for d in in_window if not d["gate_open"])
    vol_scaled = sum(1 for d in in_window if d["scale"] < 1.0 - 1e-9)
    either = sum(1 for d in in_window if (not d["gate_open"]) or d["scale"] < 1.0 - 1e-9)
    return {
        "gate_closed": gate_closed,
        "vol_scaled": vol_scaled,
        "either": either,
        "total": len(in_window),
    }


def _cell_report(
    key: str, vol_key: str, gate_key: str, bench_returns: pd.DataFrame
) -> dict[str, Any] | None:
    series = _load_returns(CACHE_DIR / "returns" / f"{key}.parquet")
    if series is None:
        return None
    stress = _load_returns(CACHE_DIR / "returns_stress" / f"{key}.parquet")
    diagnostics = json.loads((CACHE_DIR / "diagnostics" / f"{key}.json").read_text())
    events = _events_from_json(json.loads((CACHE_DIR / "schedules" / f"{key}.json").read_text()))
    headline = window_metrics(series, HEADLINE_START, HEADLINE_END, bench_returns)
    disclosure = window_metrics(series, None, DISCLOSURE_END, bench_returns)
    stress_headline = (
        window_metrics(stress, HEADLINE_START, HEADLINE_END, bench_returns)
        if stress is not None
        else None
    )
    turnover = _turnover_series(events)
    turnover_headline = turnover.loc[HEADLINE_START:HEADLINE_END]
    turnover_disclosure = turnover.loc[:DISCLOSURE_END]
    reduced = _reduced_months(diagnostics, HEADLINE_START, HEADLINE_END)
    return {
        "vol_target": vol_key,
        "gate": gate_key,
        "headline": headline,
        "disclosure": disclosure,
        "stress_headline_cagr": stress_headline["cagr"] if stress_headline else None,
        "turnover_monthly_headline": (
            float(turnover_headline.mean()) if not turnover_headline.empty else None
        ),
        "turnover_monthly_disclosure": (
            float(turnover_disclosure.mean()) if not turnover_disclosure.empty else None
        ),
        "months_gate_closed_headline": reduced["gate_closed"],
        "months_vol_scaled_headline": reduced["vol_scaled"],
        "months_reduced_headline": reduced["either"],
        "months_total_headline": reduced["total"],
    }


def stage_report(args: argparse.Namespace) -> dict[str, Any]:  # noqa: ARG001
    manifest = json.loads((CACHE_DIR / "manifest.json").read_text())
    bench_returns = pd.read_parquet(CACHE_DIR / "bench_returns.parquet")
    bench_returns.index = pd.to_datetime(bench_returns.index)

    cells: dict[str, Any] = {}
    for vol_key in VOL_TARGET_ORDER:
        for gate_key in GATE_ORDER:
            key = cell_key(vol_key, gate_key)
            report = _cell_report(key, vol_key, gate_key, bench_returns)
            if report is not None:
                cells[key] = report
    if not cells:
        raise SystemExit("report: no priced cells found -- run --stage returns first")

    bench_stats = {}
    for sym in BENCHMARK_SYMBOLS:
        series = bench_returns[sym].dropna()
        bench_stats[sym] = {
            "headline": window_metrics(series, HEADLINE_START, HEADLINE_END, bench_returns),
            "disclosure": window_metrics(series, None, DISCLOSURE_END, bench_returns),
        }
    spmo_headline = bench_stats["SPMO"]["headline"]

    winners = []
    for key, cell in cells.items():
        h = cell["headline"]
        if h is None or spmo_headline is None:
            continue
        if (
            h["cagr"] >= spmo_headline["cagr"]
            and h["max_drawdown"] >= spmo_headline["max_drawdown"]
        ):
            winners.append(key)

    pvals = [
        _one_sided_p(c["headline"]["excess"]["SPY"]["t_nw"]) if c["headline"] else None
        for c in cells.values()
    ]
    fdr_pass = bh_fdr_pass_count(pvals, q=0.10)

    placebo_summary: dict[str, Any] = {}
    base_key = cell_key("none", "gate_off")
    base_mdd = cells[base_key]["headline"]["max_drawdown"] if cells.get(base_key) else None
    for gate_key in PLACEBO_GATES:
        real_key = cell_key("none", gate_key)
        real_cell = cells.get(real_key)
        if real_cell is None or base_mdd is None:
            continue
        real_mdd = real_cell["headline"]["max_drawdown"]
        real_improvement = real_mdd - base_mdd
        seed_improvements = []
        seed_shifts = []
        for seed_path in sorted(
            (CACHE_DIR / "returns").glob(f"placebo__{gate_key}__seed*.parquet")
        ):
            series = _load_returns(seed_path)
            metrics = window_metrics(series, HEADLINE_START, HEADLINE_END, bench_returns)
            diag_path = CACHE_DIR / "diagnostics" / f"{seed_path.stem}.json"
            shift_days = None
            if diag_path.exists():
                shift_days = json.loads(diag_path.read_text()).get("shift_days")
            if metrics is not None:
                seed_improvements.append(metrics["max_drawdown"] - base_mdd)
                seed_shifts.append(shift_days)
        share_ge_real = (
            float(np.mean([1.0 if v >= real_improvement else 0.0 for v in seed_improvements]))
            if seed_improvements
            else None
        )
        placebo_summary[gate_key] = {
            "base_mdd_headline": base_mdd,
            "real_mdd_headline": real_mdd,
            "real_improvement": real_improvement,
            "placebo_shifts_days": seed_shifts,
            "placebo_improvements": seed_improvements,
            "share_placebo_ge_real": share_ge_real,
            "gate_survives_placebo": (share_ge_real is not None and share_ge_real < 0.5),
        }

    summary = {
        "iteration_id": ITERATION_ID,
        "generated_at": pd.Timestamp.utcnow().isoformat(),
        "reference_only": True,
        "manifest": manifest,
        "windows": {
            "headline": [HEADLINE_START, HEADLINE_END],
            "disclosure": ["data_start", DISCLOSURE_END],
        },
        "cells": cells,
        "benchmarks": bench_stats,
        "card_criterion": "cagr_headline >= SPMO and max_drawdown_headline >= SPMO (less negative)",
        "cells_beating_spmo_both_axes": winners,
        "bh_fdr": {"q": 0.10, "pass_count": fdr_pass, "n_cells": len(cells)},
        "gate_placebo": placebo_summary,
        "concentration_skip_note": CONCENTRATION_SKIP_NOTE,
        "cadence_caveat": CADENCE_CAVEAT,
    }
    _write_json(SUMMARY_PATH, summary)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(render_markdown(summary))
    _log(f"report: wrote {REPORT_PATH} and {SUMMARY_PATH} ({len(cells)} cells, winners={winners})")
    return summary


# --------------------------------------------------------------------------
# markdown
# --------------------------------------------------------------------------


def _pct(value: float | None, digits: int = 1) -> str:
    if value is None or not math.isfinite(value):
        return "n/a"
    return f"{value * 100:.{digits}f}%"


def _num(value: float | None, digits: int = 2) -> str:
    if value is None or not math.isfinite(value):
        return "n/a"
    return f"{value:.{digits}f}"


def render_markdown(summary: dict[str, Any]) -> str:
    cells = summary["cells"]
    bench = summary["benchmarks"]
    lines: list[str] = []
    lines.append("# H-20260918-01 风险控制后的动量账本 vs SPMO — 报告")
    lines.append("")
    lines.append(
        f"- 生成时间：{summary['generated_at'][:16]} UTC · **本轮 reference_only：不写 "
        "`reports/research/ledger/experiments.jsonl`**"
    )
    lines.append(
        f"- 数据：`data/features/universe`、`data/features/daily`（窄表，与 M0B 账本同源）；"
        f"选股不动：`{summary['manifest']['score_column']}`，"
        f"`adv_rank <= {summary['manifest']['universe_top_n']}`，top "
        f"{summary['manifest']['top_k']} 等权，月末信号→次月开盘成交，"
        f"{summary['manifest']['cost_bps_per_side']:.0f}bp/边成本"
    )
    lines.append(f"- {CONCENTRATION_SKIP_NOTE}")
    lines.append(f"- {CADENCE_CAVEAT}")
    lines.append("")

    winners = summary["cells_beating_spmo_both_axes"]
    lines.append("## 0. 结论")
    lines.append("")
    if winners:
        lines.append(
            f"**supported** —— 有 {len(winners)} 个单元在 {HEADLINE_START}..{HEADLINE_END} "
            f"窗口同时满足「年化 ≥ SPMO 且最大回撤 ≤ SPMO」：{winners}"
        )
    else:
        lines.append(
            "**refuted** —— 15 个单元里没有一个在这个窗口同时满足"
            "「年化 ≥ SPMO 且最大回撤 ≤ SPMO」；纯组合构建（波动目标 + 趋势门）"
            "改不动这条选股规则相对 SPMO 的位置。"
        )
    placebo = summary["gate_placebo"]
    for gate_key, p in placebo.items():
        survive = "没有被随机平移复现" if p["gate_survives_placebo"] else "能被随机平移复现"
        share = p["share_placebo_ge_real"]
        share_text = _pct(share, 0) if share is not None else "n/a"
        n_seeds = len([v for v in p["placebo_improvements"] if v is not None])
        gate_label = GATE_LABELS[gate_key]
        lines.append(
            f"- 占位检验（{gate_label}，5 个种子，±{PLACEBO_SHIFT_DAYS} 个交易日随机平移）："
            f"真实门的回撤改善 {_pct(p['real_improvement'])}，"
            f"{n_seeds} 个占位种子里有 {share_text} "
            f"达到或超过这个改善幅度 —— 这个门的回撤改善{survive}。"
        )
    lines.append("")

    lines.append("## 1. SPMO / 基准对照（主表，" + f"{HEADLINE_START}..{HEADLINE_END}）")
    lines.append("")
    lines.append("| 标的 | 年化 CAGR | 最大回撤 | 年化波动 |")
    lines.append("|---|---:|---:|---:|")
    for sym in BENCHMARK_SYMBOLS:
        h = bench[sym]["headline"]
        if h is None:
            lines.append(f"| {sym} | n/a | n/a | n/a |")
            continue
        lines.append(
            f"| {sym} | {_pct(h['cagr'])} | {_pct(h['max_drawdown'])} | {_pct(h['vol'])} |"
        )
    lines.append("")

    ranked = sorted(
        ((key, c) for key, c in cells.items() if c["headline"] is not None),
        key=lambda kv: kv[1]["headline"]["cagr"],
        reverse=True,
    )
    lines.append("### 表现最好的 5 个单元 vs SPMO")
    lines.append("")
    lines.append("| 单元 | 波动目标 | 趋势门 | CAGR | 最大回撤 | 是否双维赢 SPMO |")
    lines.append("|---|---|---|---:|---:|---|")
    spmo_h = bench["SPMO"]["headline"]
    for key, c in ranked[:5]:
        h = c["headline"]
        beats = (
            "是"
            if spmo_h
            and h["cagr"] >= spmo_h["cagr"]
            and h["max_drawdown"] >= spmo_h["max_drawdown"]
            else "否"
        )
        lines.append(
            f"| `{key}` | {VOL_TARGET_LABELS[c['vol_target']]} | {GATE_LABELS[c['gate']]} | "
            f"{_pct(h['cagr'])} | {_pct(h['max_drawdown'])} | {beats} |"
        )
    lines.append("")

    lines.append(f"## 2. 全部 15 个单元（{HEADLINE_START}..{HEADLINE_END} 窗口）")
    lines.append("")
    header = (
        "| 波动目标 | 趋势门 | CAGR | 最大回撤 | 年化波动 | t(SPY) | t(SPMO) | t(MTUM) | "
        "t(IWM) | t(QQQ) | t(RSP) | 同波动SPY超额 | 月换手 | 25bp压力CAGR | 减仓月/总月 |"
    )
    lines.append(header)
    lines.append("|" + "---|" * 15)
    for gate_key in GATE_ORDER:
        for vol_key in VOL_TARGET_ORDER:
            key = cell_key(vol_key, gate_key)
            c = cells.get(key)
            if c is None or c["headline"] is None:
                continue
            h = c["headline"]
            ex = h["excess"]
            row = (
                f"| {VOL_TARGET_LABELS[vol_key]} | {GATE_LABELS[gate_key]} | {_pct(h['cagr'])} | "
                f"{_pct(h['max_drawdown'])} | {_pct(h['vol'])} | "
                f"{_num(ex['SPY']['t_nw'], 1)} | {_num(ex['SPMO']['t_nw'], 1)} | "
                f"{_num(ex['MTUM']['t_nw'], 1)} | {_num(ex['IWM']['t_nw'], 1)} | "
                f"{_num(ex['QQQ']['t_nw'], 1)} | {_num(ex['RSP']['t_nw'], 1)} | "
                f"{_pct(h['vol_matched_excess_spy'])} | "
                f"{_pct(c['turnover_monthly_headline'], 0)} | "
                f"{_pct(c['stress_headline_cagr'])} | "
                f"{c['months_reduced_headline']}/{c['months_total_headline']} |"
            )
            lines.append(row)
    lines.append("")
    lines.append(
        f"- BH-FDR（q=0.10，15 个单元对 SPY 月超额 t 值的单边 p 值）：通过 "
        f"{summary['bh_fdr']['pass_count']} / {summary['bh_fdr']['n_cells']} 个。"
    )
    lines.append("- t 统计量：Newey-West（Bartlett，lag=0，月度、非重叠调仓）。")
    lines.append("")

    lines.append("## 3. 2016–2023 披露窗口（样本外对照，不用于选单元）")
    lines.append("")
    lines.append("| 波动目标 | 趋势门 | CAGR | 最大回撤 | 年化波动 | 月换手 |")
    lines.append("|---|---|---:|---:|---:|---:|")
    for gate_key in GATE_ORDER:
        for vol_key in VOL_TARGET_ORDER:
            key = cell_key(vol_key, gate_key)
            c = cells.get(key)
            if c is None or c["disclosure"] is None:
                continue
            d = c["disclosure"]
            lines.append(
                f"| {VOL_TARGET_LABELS[vol_key]} | {GATE_LABELS[gate_key]} | {_pct(d['cagr'])} | "
                f"{_pct(d['max_drawdown'])} | {_pct(d['vol'])} | "
                f"{_pct(c['turnover_monthly_disclosure'], 0)} |"
            )
    lines.append("")
    for sym in BENCHMARK_SYMBOLS:
        d = bench[sym]["disclosure"]
        if d is None:
            continue
        cagr_text, mdd_text = _pct(d["cagr"]), _pct(d["max_drawdown"])
        lines.append(f"- {sym}（2016 起至 2023-12-31）：CAGR {cagr_text}，MDD {mdd_text}")
    lines.append("")

    lines.append("## 4. 趋势门占位检验明细")
    lines.append("")
    for gate_key, p in placebo.items():
        lines.append(f"### {GATE_LABELS[gate_key]}")
        lines.append("")
        lines.append(
            f"- 基线（none/gate_off）最大回撤 {_pct(p['base_mdd_headline'])}；"
            f"真实门（none/{gate_key}）最大回撤 {_pct(p['real_mdd_headline'])}；"
            f"改善 {_pct(p['real_improvement'])}"
        )
        shifts = p["placebo_shifts_days"]
        improvements = p["placebo_improvements"]
        for shift, improvement in zip(shifts, improvements, strict=True):
            lines.append(f"  - 占位平移 {shift:+d} 个交易日：回撤改善 {_pct(improvement)}")
        share = p["share_placebo_ge_real"]
        share_text = _pct(share, 0) if share is not None else "n/a"
        survive_text = (
            "门的效果没有被随机平移复现"
            if p["gate_survives_placebo"]
            else "门的效果能被随机平移复现，不能确认是门本身的作用"
        )
        lines.append(f"- 占位种子达到/超过真实改善的比例：{share_text}（阈值 50%）→ {survive_text}")
        lines.append("")

    lines.append("## 5. 跳过的项目与说明")
    lines.append("")
    lines.append(f"- {CONCENTRATION_SKIP_NOTE}")
    lines.append(f"- {CADENCE_CAVEAT}")
    lines.append(
        "- 波动率目标口径：已实现波动率一律用无风控裸账本（vol_target=none, gate=off）"
        "自己的历史日收益滚动估计（21/63 日窗），不用被同一单元自身的趋势门/目标波动率"
        "影响过的收益序列，避免用现金月的低波动反推出虚高的目标暴露。"
    )
    lines.append(
        "- QQQ 的 200 日均线门本地计算（`data/features/regime_daily` 只有 SPY 列），"
        "口径与 `build_step13_regime_daily_features.py` 的 `spy_gap_200sma` 完全一致："
        "`close / close.rolling(200, min_periods=200).mean() - 1 > 0`。"
    )
    lines.append("")

    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=["all", "weights", "returns", "report"], default="all")
    parser.add_argument("--vol-targets", nargs="*", choices=list(VOL_TARGET_ORDER), default=None)
    parser.add_argument("--gates", nargs="*", choices=list(GATE_ORDER), default=None)
    parser.add_argument(
        "--concentration", nargs="*", choices=list(CONCENTRATION_OPTIONS), default=None
    )
    parser.add_argument("--seeds", type=int, default=len(PLACEBO_SEEDS))
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    if args.stage in ("all", "weights"):
        stage_weights(args)
    if args.stage in ("all", "returns"):
        stage_returns(args)
    if args.stage in ("all", "report"):
        stage_report(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
