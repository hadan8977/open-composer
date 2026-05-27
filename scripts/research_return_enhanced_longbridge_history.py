from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from time import perf_counter
from typing import Any

import numpy as np
import pandas as pd

from open_composer.adapters.data.longbridge import (
    DEFAULT_LONGBRIDGE_TRADE_SESSIONS,
    MAX_LONGBRIDGE_CANDLESTICKS,
    _fetch_live_longbridge_bars,
)
from open_composer.config import ensure_dir, project_root
from open_composer.models.strategy_spec import load_strategy_spec
from open_composer.storage import write_json

STRATEGY = "nasdaq_tqqq_return_enhanced_router_daily_long_inverse_iter5"
REPORT_STEM = f"{STRATEGY}-long-history-longbridge"
SPEC_PATH = Path("strategy_specs/drafts/nasdaq_tqqq_return_enhanced_router_daily_cycle_iter3.yaml")
START_DATE = "2010-02-11"
END_DATE = "2026-05-22"
MARKET_SYMBOL = "QQQ"
BENCHMARK_SYMBOL = "TQQQ"
UNIVERSE = [
    "QQQ",
    "TQQQ",
    "SQQQ",
    "SOXL",
    "SOXS",
    "TECL",
    "TECS",
    "ROM",
    "USD",
    "QLD",
    "PSQ",
    "SMH",
    "NVDA",
    "AVGO",
    "AMD",
    "TSLA",
    "META",
    "AMZN",
    "GOOGL",
    "AAPL",
    "MSFT",
    "NFLX",
    "MU",
    "ORCL",
    "CRM",
    "ADBE",
    "ASML",
    "INTU",
    "PANW",
    "NOW",
    "LRCX",
    "AMAT",
    "KLAC",
    "SNPS",
    "CDNS",
    "ANET",
    "MSTR",
]
INVERSE_SYMBOLS = {"SQQQ", "SOXS", "TECS", "PSQ"}
BENCHMARK_PROXIES = ["XLK", "IGV", "SOXX", "SPY"]
DATA_DIR = Path("data/research/longbridge_adjusted_daily")
REFERENCE_ROUTE_LABEL = "beta_override:baseiter2_lb30_min10_adv-5_sma100_exTQQQ_gateq200ormom120"


@dataclass(frozen=True)
class BetaOverrideParams:
    momentum_lookback_days: int
    min_momentum_pct: float
    override_advantage_pct: float
    confirmation_sma_days: int | None
    exclude_tqqq: bool
    cycle_gate: str = "none"
    symbol_drawdown_lookback_days: int | None = None
    max_symbol_drawdown_pct: float | None = None
    market_drawdown_lookback_days: int | None = None
    max_market_drawdown_pct: float | None = None
    gross_exposure_scale: float = 1.0
    risk_off_hedge_weight: float = 0.0
    inverse_mode: str = "exclude"
    base_mode: str = "iter2"

    @property
    def label(self) -> str:
        sma = "none" if self.confirmation_sma_days is None else str(self.confirmation_sma_days)
        suffix = "_exTQQQ" if self.exclude_tqqq else ""
        gate = "" if self.cycle_gate == "none" else f"_gate{self.cycle_gate}"
        label = (
            "beta_override:"
            f"baseiter2_lb{self.momentum_lookback_days}_min{self.min_momentum_pct:g}_"
            f"adv{self.override_advantage_pct:g}_sma{sma}{suffix}{gate}"
        )
        if self.symbol_drawdown_lookback_days and self.max_symbol_drawdown_pct is not None:
            label += f"_sdd{self.symbol_drawdown_lookback_days}p{self.max_symbol_drawdown_pct:g}"
        if self.market_drawdown_lookback_days and self.max_market_drawdown_pct is not None:
            label += f"_mdd{self.market_drawdown_lookback_days}p{self.max_market_drawdown_pct:g}"
        if self.gross_exposure_scale < 0.999999:
            label += f"_g{self.gross_exposure_scale:g}"
        if self.risk_off_hedge_weight > 0:
            label += f"_offSQQQ{self.risk_off_hedge_weight:g}"
        if self.inverse_mode != "exclude":
            label += f"_inv{self.inverse_mode}"
        if self.base_mode != "iter2":
            label += f"_{self.base_mode}"
        return label


@dataclass(frozen=True)
class IndicatorCache:
    momentum: dict[int, np.ndarray]
    sma: dict[int, np.ndarray]
    drawdown: dict[int, np.ndarray]
    gates: dict[str, np.ndarray]


def main() -> None:
    started = perf_counter()
    root = project_root()
    spec = load_strategy_spec(root / SPEC_PATH)
    symbols = list(dict.fromkeys([*UNIVERSE, *BENCHMARK_PROXIES]))
    fetch_manifest = _ensure_longbridge_history(root, symbols)
    dates, opens, closes, availability = _load_history_arrays(root, UNIVERSE)
    date_index = {date: index for index, date in enumerate(dates)}
    cost_rate = spec.costs.commission_pct / 100 + spec.costs.slippage_bps / 10_000
    open_to_open = _open_to_open_returns(opens, cost_rate=cost_rate)
    raw_open_to_open = _open_to_open_returns(opens, cost_rate=0.0)
    first_tradable = max(251, date_index.get("2011-02-11", 251))
    end_index = date_index[END_DATE]

    grid = _candidate_grid()
    cache = _build_indicator_cache(closes, grid)
    iter2_weights = _iter2_base_weights(closes, cache)
    iter2_returns = _portfolio_returns(iter2_weights, open_to_open)
    candidate_rows = _evaluate_candidates(
        dates=dates,
        closes=closes,
        open_to_open_returns=open_to_open,
        raw_open_to_open=raw_open_to_open,
        baseline_returns=iter2_returns,
        base_weights=iter2_weights,
        cache=cache,
        grid=grid,
        first_tradable=first_tradable,
        end_index=end_index,
    )
    best_row = candidate_rows[0]
    best_standard_row = _best_standard_candidate(candidate_rows)
    selected_row = best_standard_row or best_row
    selected_returns = selected_row["returns"]
    selected_weights = selected_row["weights"]
    reference_row = next(
        (row for row in candidate_rows if row["params"].label == REFERENCE_ROUTE_LABEL),
        None,
    )
    walk_forward = _anchored_yearly_walk_forward(
        dates=dates,
        candidate_rows=candidate_rows,
        baseline_returns=iter2_returns,
        first_tradable=first_tradable,
    )

    full_start = first_tradable
    periods = _period_results(
        dates=dates,
        selected_returns=selected_returns,
        selected_weights=selected_weights,
        iter2_returns=iter2_returns,
        iter2_weights=iter2_weights,
        raw_open_to_open=raw_open_to_open,
        first_tradable=full_start,
        end_index=end_index,
    )
    annual = _annual_results(
        dates=dates,
        selected_returns=selected_returns,
        selected_weights=selected_weights,
        iter2_returns=iter2_returns,
        iter2_weights=iter2_weights,
        raw_open_to_open=raw_open_to_open,
        first_tradable=full_start,
        end_index=end_index,
    )
    benchmarks = _benchmark_family(
        root=root,
        dates=dates,
        raw_open_to_open=raw_open_to_open,
        first_tradable=full_start,
        end_index=end_index,
    )
    pass_status = _pass_status(
        selected=selected_row,
        best=best_row,
        best_standard=best_standard_row,
        walk_forward=walk_forward,
        annual=annual,
    )
    payload = {
        "strategy_name": STRATEGY,
        "report_type": "long_history_longbridge_adjusted_research",
        "generated_at": datetime.now(UTC).isoformat(),
        "data_profile": {
            "provider": "longbridge",
            "feed": "nasdaq_basic",
            "source_mode": "live_fetch_chunked",
            "adjusted": True,
            "requested_start": START_DATE,
            "requested_end": END_DATE,
            "symbols": symbols,
            "fetch_manifest_path": str(
                root / "reports/research" / f"{REPORT_STEM}-data-fetch.json"
            ),
            "availability": availability,
            "caveats": [
                "Longbridge Nasdaq Basic is not consolidated SIP data.",
                "History is fetched in <=1000-bar date chunks and merged locally.",
                "The universe is current-symbol biased until PIT membership evidence exists.",
                "Longbridge-adjusted prices differ from the prior raw Alpaca IEX cache.",
                (
                    "Expanded high-beta symbols are an opportunity-scan universe, "
                    "not PIT historical index membership."
                ),
            ],
        },
        "cost_model": {
            "commission_pct": spec.costs.commission_pct,
            "slippage_bps": spec.costs.slippage_bps,
            "fill_assumption": spec.execution.fill_assumption,
        },
        "reference_route_label": REFERENCE_ROUTE_LABEL,
        "reference_candidate": _candidate_payload(reference_row) if reference_row else None,
        "selected_route_label": selected_row["params"].label,
        "selected_candidate": _candidate_payload(
            selected_row, selected_label=selected_row["params"].label
        ),
        "best_long_history_candidate": _candidate_payload(best_row),
        "best_standard_candidate": (
            _candidate_payload(best_standard_row, selected_label=selected_row["params"].label)
            if best_standard_row is not None
            else None
        ),
        "search_space": {
            "candidate_count": len(grid),
            "families": [
                "iter2_beta_with_high_beta_override_cycle_gate",
                "risk_off_inverse_etf_rotation",
                "expanded_high_beta_technology_scan",
            ],
            "parameters": _grid_ranges(grid),
            "selection_note": (
                "Candidates are ranked on full long-history diagnostics for research only; "
                "yearly anchored walk-forward is the anti-overfit evidence. "
                "True short selling is not enabled; inverse ETFs are tested "
                "as long-only instruments."
            ),
        },
        "acceptance_standard": _acceptance_standard(),
        "pass_status": pass_status,
        "periods": periods,
        "annual_results": annual,
        "benchmark_family": benchmarks,
        "walk_forward": walk_forward,
        "top_candidates": [
            _candidate_payload(row, selected_label=selected_row["params"].label)
            for row in candidate_rows[:20]
        ],
        "candidate_ledger_path": str(
            root / "reports/research" / f"{REPORT_STEM}-candidate-ledger.json"
        ),
        "fetch_manifest": fetch_manifest,
        "anti_leakage": [
            "Signals at index t use confirmed closes through index t-1 only.",
            "Trades are evaluated from the next regular-session open.",
            "Chunked data fetch does not use return outcomes for parameter selection.",
            "Yearly walk-forward selects parameters using only dates before each test year.",
        ],
        "runtime_seconds": round(perf_counter() - started, 4),
    }
    reports = ensure_dir(root / "reports" / "research")
    json_path = reports / f"{REPORT_STEM}.json"
    md_path = reports / f"{REPORT_STEM}.md"
    write_json(json_path, payload)
    write_json(
        reports / f"{REPORT_STEM}-candidate-ledger.json",
        {
            "strategy_name": STRATEGY,
            "candidate_count": len(candidate_rows),
            "candidates": [_candidate_payload(row) for row in candidate_rows],
        },
    )
    write_json(reports / f"{REPORT_STEM}-data-fetch.json", fetch_manifest)
    _write_markdown(md_path, payload)
    print(
        json.dumps(
            {
                "json": str(json_path),
                "markdown": str(md_path),
                "selected_research_pass": pass_status["selected_research_pass"],
                "best_research_pass": pass_status["best_research_pass"],
                "selected_total_return_pct": selected_row["full_window"]["total_return_pct"],
                "selected_annualized_return_pct": selected_row["full_window"][
                    "annualized_return_pct"
                ],
                "selected_max_drawdown_pct": selected_row["full_window"]["max_drawdown_pct"],
                "best_label": best_row["params"].label,
                "best_total_return_pct": best_row["full_window"]["total_return_pct"],
                "best_standard_label": (
                    best_standard_row["params"].label if best_standard_row is not None else None
                ),
                "best_standard_total_return_pct": (
                    best_standard_row["full_window"]["total_return_pct"]
                    if best_standard_row is not None
                    else None
                ),
            },
            indent=2,
        )
    )


def _ensure_longbridge_history(root: Path, symbols: list[str]) -> dict[str, Any]:
    out_dir = ensure_dir(root / DATA_DIR)
    start = _timestamp(START_DATE)
    end = _timestamp(END_DATE)
    rows = []
    for symbol in symbols:
        path = out_dir / f"{symbol.lower()}_daily_longbridge_adjusted.csv"
        frame: pd.DataFrame | None = None
        if path.exists():
            cached = _read_price_csv(path)
            if _covers(cached, start, end):
                frame = cached
        source_mode = "cache"
        chunks: list[dict[str, Any]] = []
        if frame is None:
            frame, chunks = _fetch_symbol_history(root, symbol, start, end)
            frame.to_csv(path, index=False)
            source_mode = "live_fetch_chunked"
        rows.append(
            {
                "symbol": symbol,
                "path": str(path),
                "source_mode": source_mode,
                "records": int(len(frame)),
                "first_timestamp": _iso(frame["timestamp"].min()) if not frame.empty else None,
                "last_timestamp": _iso(frame["timestamp"].max()) if not frame.empty else None,
                "chunks": chunks,
            }
        )
    return {
        "provider": "longbridge",
        "feed": "nasdaq_basic",
        "adjusted": True,
        "trade_sessions": DEFAULT_LONGBRIDGE_TRADE_SESSIONS,
        "max_request_bars": MAX_LONGBRIDGE_CANDLESTICKS,
        "requested_start": START_DATE,
        "requested_end": END_DATE,
        "symbols": rows,
    }


def _fetch_symbol_history(
    root: Path,
    symbol: str,
    start: datetime,
    end: datetime,
) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    frames = []
    chunks = []
    cursor_end = end
    previous_first: pd.Timestamp | None = None
    while cursor_end >= start:
        try:
            frame = _fetch_live_longbridge_bars(
                root=root,
                symbol=symbol,
                timeframe="daily",
                start=start,
                end=cursor_end,
                adjusted=True,
                count=MAX_LONGBRIDGE_CANDLESTICKS,
                trade_sessions=DEFAULT_LONGBRIDGE_TRADE_SESSIONS,
            )
        except ValueError as exc:
            chunks.append(
                {
                    "requested_end": cursor_end.date().isoformat(),
                    "records": 0,
                    "error": str(exc),
                }
            )
            break
        frame = _normalize_frame(frame)
        if frame.empty:
            break
        frames.append(frame)
        first = frame["timestamp"].min()
        last = frame["timestamp"].max()
        chunks.append(
            {
                "requested_end": cursor_end.date().isoformat(),
                "records": int(len(frame)),
                "first_timestamp": _iso(first),
                "last_timestamp": _iso(last),
            }
        )
        if first <= pd.Timestamp(start):
            break
        if previous_first is not None and first >= previous_first:
            break
        previous_first = first
        cursor_end = first.to_pydatetime() - timedelta(days=1)
    if not frames:
        return _empty_frame(), chunks
    merged = pd.concat(frames, ignore_index=True)
    merged = _normalize_frame(merged)
    merged["_date"] = merged["timestamp"].dt.date
    merged = merged[(merged["_date"] >= start.date()) & (merged["_date"] <= end.date())]
    merged = merged.drop(columns=["_date"])
    return merged.reset_index(drop=True), chunks


def _load_history_arrays(
    root: Path,
    symbols: list[str],
) -> tuple[list[str], np.ndarray, np.ndarray, dict[str, Any]]:
    frames = {}
    availability = {}
    calendar = None
    for symbol in symbols:
        path = root / DATA_DIR / f"{symbol.lower()}_daily_longbridge_adjusted.csv"
        frame = _read_price_csv(path)
        frame["date"] = frame["timestamp"].dt.date.astype(str)
        frame = frame[(frame["date"] >= START_DATE) & (frame["date"] <= END_DATE)]
        frame = frame.sort_values("timestamp").drop_duplicates("date", keep="last")
        frames[symbol] = frame.set_index("date")
        availability[symbol] = {
            "records": int(len(frame)),
            "first_date": str(frame["date"].min()) if not frame.empty else None,
            "last_date": str(frame["date"].max()) if not frame.empty else None,
        }
        if symbol == MARKET_SYMBOL:
            calendar = list(frame["date"])
    if calendar is None:
        raise ValueError(f"missing market symbol calendar: {MARKET_SYMBOL}")
    dates = [date for date in calendar if START_DATE <= date <= END_DATE]
    opens = np.full((len(dates), len(symbols)), np.nan)
    closes = np.full_like(opens, np.nan)
    for symbol_index, symbol in enumerate(symbols):
        frame = frames[symbol]
        for row_index, date in enumerate(dates):
            if date not in frame.index:
                continue
            opens[row_index, symbol_index] = float(frame.loc[date, "open"])
            closes[row_index, symbol_index] = float(frame.loc[date, "close"])
    return dates, opens, closes, availability


def _candidate_grid() -> list[BetaOverrideParams]:
    rows: list[BetaOverrideParams] = []
    for lookback in [20, 30, 40]:
        for advantage in [-5.0, 0.0]:
            for cycle_gate in ["q200ormom120", "mom120"]:
                for symbol_dd, max_symbol_dd in [(None, None), (120, 25.0)]:
                    for market_dd, max_market_dd in [(None, None), (252, 25.0), (252, 35.0)]:
                        for scale in [0.75, 0.85, 0.95, 1.0]:
                            for inverse_mode in ["exclude", "riskoff"]:
                                rows.append(
                                    BetaOverrideParams(
                                        momentum_lookback_days=lookback,
                                        min_momentum_pct=5.0,
                                        override_advantage_pct=advantage,
                                        confirmation_sma_days=150,
                                        exclude_tqqq=True,
                                        cycle_gate=cycle_gate,
                                        symbol_drawdown_lookback_days=symbol_dd,
                                        max_symbol_drawdown_pct=max_symbol_dd,
                                        market_drawdown_lookback_days=market_dd,
                                        max_market_drawdown_pct=max_market_dd,
                                        gross_exposure_scale=scale,
                                        inverse_mode=inverse_mode,
                                    )
                                )
    for lookback in [20, 30, 40, 60]:
        for min_momentum in [5.0, 10.0, 15.0]:
            for advantage in [-5.0, 0.0]:
                for confirmation_sma in [50, 100, 150]:
                    for cycle_gate in ["none", "q200ormom120", "q200", "mom120", "q200andmom120"]:
                        for inverse_mode in ["exclude", "riskoff"]:
                            params = BetaOverrideParams(
                                momentum_lookback_days=lookback,
                                min_momentum_pct=min_momentum,
                                override_advantage_pct=advantage,
                                confirmation_sma_days=confirmation_sma,
                                exclude_tqqq=True,
                                cycle_gate=cycle_gate,
                                inverse_mode=inverse_mode,
                            )
                            if params not in rows:
                                rows.append(params)
    for lookback in [90, 120, 180, 252]:
        for min_momentum in [10.0, 20.0, 30.0, 50.0]:
            for advantage in [-20.0, -5.0, 0.0]:
                for confirmation_sma in [100, 150, 200]:
                    for cycle_gate in ["none", "q200ormom120", "mom120"]:
                        for scale in [0.85, 1.0]:
                            params = BetaOverrideParams(
                                momentum_lookback_days=lookback,
                                min_momentum_pct=min_momentum,
                                override_advantage_pct=advantage,
                                confirmation_sma_days=confirmation_sma,
                                exclude_tqqq=True,
                                cycle_gate=cycle_gate,
                                gross_exposure_scale=scale,
                            )
                            if params not in rows:
                                rows.append(params)
    for lookback in [20, 60, 90, 120, 180, 252]:
        for min_momentum in [5.0, 10.0, 20.0, 30.0]:
            for confirmation_sma in [50, 100, 150, 200]:
                for cycle_gate in ["none", "q200ormom120", "mom120"]:
                    for scale in [0.85, 1.0]:
                        params = BetaOverrideParams(
                            momentum_lookback_days=lookback,
                            min_momentum_pct=min_momentum,
                            override_advantage_pct=0.0,
                            confirmation_sma_days=confirmation_sma,
                            exclude_tqqq=True,
                            cycle_gate=cycle_gate,
                            gross_exposure_scale=scale,
                            base_mode="pure",
                        )
                        if params not in rows:
                            rows.append(params)
    for base_mode in ["tqqq_cycle", "tqqq_always"]:
        for lookback in [20, 60, 120, 180]:
            for min_momentum in [5.0, 10.0, 20.0, 30.0]:
                for advantage in [-20.0, -5.0, 0.0]:
                    for confirmation_sma in [50, 100, 150, 200]:
                        cycle_gates = (
                            ["q200ormom120", "mom120", "none"]
                            if base_mode == "tqqq_cycle"
                            else ["none"]
                        )
                        for cycle_gate in cycle_gates:
                            params = BetaOverrideParams(
                                momentum_lookback_days=lookback,
                                min_momentum_pct=min_momentum,
                                override_advantage_pct=advantage,
                                confirmation_sma_days=confirmation_sma,
                                exclude_tqqq=True,
                                cycle_gate=cycle_gate,
                                gross_exposure_scale=1.0,
                                base_mode=base_mode,
                            )
                            if params not in rows:
                                rows.append(params)
    selected = BetaOverrideParams(30, 10.0, -5.0, 100, True, "q200ormom120")
    if selected not in rows:
        rows.append(selected)
    return rows


def _build_indicator_cache(closes: np.ndarray, grid: list[BetaOverrideParams]) -> IndicatorCache:
    momentum_days = {120, *(item.momentum_lookback_days for item in grid)}
    sma_days = {50, 200, 250, *(item.confirmation_sma_days or 0 for item in grid)}
    sma_days.discard(0)
    drawdown_days = {
        60,
        *(item.symbol_drawdown_lookback_days or 0 for item in grid),
        *(item.market_drawdown_lookback_days or 0 for item in grid),
    }
    drawdown_days.discard(0)
    momentum = {
        lookback: _rolling_momentum_for_index(closes, lookback) for lookback in momentum_days
    }
    sma = {lookback: _rolling_mean_for_index(closes, lookback) for lookback in sma_days}
    drawdown = {
        lookback: _rolling_drawdown_for_index(closes, lookback) for lookback in drawdown_days
    }
    qqq_index = UNIVERSE.index(MARKET_SYMBOL)
    q200 = closes_shifted(closes)[:, qqq_index] > sma[200][:, qqq_index]
    mom120 = momentum[120][:, qqq_index] > 0
    gates = {
        "none": np.ones(closes.shape[0], dtype=bool),
        "q200": np.nan_to_num(q200, nan=False).astype(bool),
        "mom120": np.nan_to_num(mom120, nan=False).astype(bool),
        "q200ormom120": np.nan_to_num(q200 | mom120, nan=False).astype(bool),
        "q200andmom120": np.nan_to_num(q200 & mom120, nan=False).astype(bool),
    }
    return IndicatorCache(momentum=momentum, sma=sma, drawdown=drawdown, gates=gates)


def _rolling_momentum_for_index(closes: np.ndarray, lookback: int) -> np.ndarray:
    output = np.full_like(closes, np.nan)
    if lookback + 1 >= len(closes):
        return output
    current = closes[lookback:-1]
    previous = closes[: -lookback - 1]
    valid = np.isfinite(current) & np.isfinite(previous) & (previous > 0)
    values = np.full_like(current, np.nan)
    values[valid] = (current[valid] / previous[valid] - 1) * 100
    output[lookback + 1 :] = values
    return output


def _rolling_mean_for_index(closes: np.ndarray, lookback: int) -> np.ndarray:
    rolling = (
        pd.DataFrame(closes).rolling(lookback, min_periods=lookback).mean().to_numpy(dtype=float)
    )
    output = np.full_like(closes, np.nan)
    output[1:] = rolling[:-1]
    return output


def _rolling_drawdown_for_index(closes: np.ndarray, lookback: int) -> np.ndarray:
    rolling_max = (
        pd.DataFrame(closes).rolling(lookback, min_periods=lookback).max().to_numpy(dtype=float)
    )
    rolling_for_index = np.full_like(closes, np.nan)
    rolling_for_index[1:] = rolling_max[:-1]
    prior_close = closes_shifted(closes)
    output = np.full_like(closes, np.nan)
    valid = np.isfinite(prior_close) & np.isfinite(rolling_for_index) & (rolling_for_index > 0)
    output[valid] = (prior_close[valid] / rolling_for_index[valid] - 1) * 100
    return output


def closes_shifted(closes: np.ndarray) -> np.ndarray:
    output = np.full_like(closes, np.nan)
    output[1:] = closes[:-1]
    return output


def _evaluate_candidates(
    *,
    dates: list[str],
    closes: np.ndarray,
    open_to_open_returns: np.ndarray,
    raw_open_to_open: np.ndarray,
    baseline_returns: np.ndarray,
    base_weights: np.ndarray,
    cache: IndicatorCache,
    grid: list[BetaOverrideParams],
    first_tradable: int,
    end_index: int,
) -> list[dict[str, Any]]:
    baseline_metrics = _metrics(
        dates,
        baseline_returns,
        np.zeros_like(open_to_open_returns),
        first_tradable,
        end_index,
    )
    tqqq_metrics = _return_metrics(
        dates,
        raw_open_to_open[:, UNIVERSE.index(BENCHMARK_SYMBOL)],
        first_tradable,
        end_index,
    )
    rows = []
    for trial_id, params in enumerate(grid, start=1):
        returns, weights = _run_beta_override(
            closes=closes,
            open_to_open_returns=open_to_open_returns,
            params=params,
            base_weights=base_weights,
            cache=cache,
        )
        full = _metrics(dates, returns, weights, first_tradable, end_index)
        full["beats_iter2_total_return"] = (
            full["total_return_pct"] > baseline_metrics["total_return_pct"]
        )
        full["return_delta_vs_iter2_pct"] = (
            full["total_return_pct"] - baseline_metrics["total_return_pct"]
        )
        full["beats_tqqq_buy_hold_total_return"] = (
            full["total_return_pct"] > tqqq_metrics["total_return_pct"]
        )
        full["return_delta_vs_tqqq_buy_hold_pct"] = (
            full["total_return_pct"] - tqqq_metrics["total_return_pct"]
        )
        years = _calendar_metrics(dates, returns, weights, first_tradable, end_index)
        row = {
            "trial_id": f"lb_long_{trial_id:04d}",
            "params": params,
            "full_window": full,
            "annual": years,
            "score": _score_candidate(full, years, baseline_metrics),
            "returns": returns,
            "weights": weights,
        }
        rows.append(row)
    rows.sort(key=lambda item: item["score"], reverse=True)
    return rows


def _run_beta_override(
    *,
    closes: np.ndarray,
    open_to_open_returns: np.ndarray,
    params: BetaOverrideParams,
    base_weights: np.ndarray,
    cache: IndicatorCache,
) -> tuple[np.ndarray, np.ndarray]:
    tqqq_index = UNIVERSE.index(BENCHMARK_SYMBOL)
    if params.base_mode == "iter2":
        weights = base_weights.copy() * params.gross_exposure_scale
    elif params.base_mode == "pure":
        weights = np.zeros_like(base_weights)
    elif params.base_mode == "tqqq_always":
        weights = np.zeros_like(base_weights)
        weights[251 : len(closes) - 1, tqqq_index] = params.gross_exposure_scale
    elif params.base_mode == "tqqq_cycle":
        weights = np.zeros_like(base_weights)
        cycle = cache.gates["q200ormom120"]
        weights[251 : len(closes) - 1, tqqq_index] = (
            cycle[251 : len(closes) - 1].astype(float) * params.gross_exposure_scale
        )
    else:
        raise ValueError(f"unsupported base mode: {params.base_mode}")
    sqqq_index = UNIVERSE.index("SQQQ")
    inverse_mask = np.array([symbol in INVERSE_SYMBOLS for symbol in UNIVERSE], dtype=bool)
    min_index = max(
        251,
        params.momentum_lookback_days + 1,
        params.confirmation_sma_days or 0,
        _cycle_gate_lookback(params.cycle_gate),
        params.symbol_drawdown_lookback_days or 0,
        params.market_drawdown_lookback_days or 0,
    )
    momentum = cache.momentum[params.momentum_lookback_days]
    confirmation = cache.sma.get(params.confirmation_sma_days or 0)
    gate = cache.gates[params.cycle_gate]
    qqq_index = UNIVERSE.index(MARKET_SYMBOL)
    symbol_drawdown = (
        cache.drawdown[params.symbol_drawdown_lookback_days]
        if params.symbol_drawdown_lookback_days
        else None
    )
    market_drawdown = (
        cache.drawdown[params.market_drawdown_lookback_days][:, qqq_index]
        if params.market_drawdown_lookback_days
        else None
    )
    qqq_prior_close = closes_shifted(closes)[:, qqq_index]
    qqq_sma200 = cache.sma[200][:, qqq_index]
    qqq_mom120 = cache.momentum[120][:, qqq_index]
    for index in range(min_index, len(closes) - 1):
        risk_off = _risk_off_hedge_gate(
            qqq_prior_close,
            qqq_sma200,
            qqq_mom120,
            index,
        )
        if params.risk_off_hedge_weight > 0 and risk_off:
            weights[index, :] = 0.0
            weights[index, sqqq_index] = params.risk_off_hedge_weight * params.gross_exposure_scale
            continue
        if not bool(gate[index]) and not (params.inverse_mode == "riskoff" and risk_off):
            continue
        if market_drawdown is not None and params.max_market_drawdown_pct is not None:
            if not np.isfinite(market_drawdown[index]):
                continue
            if market_drawdown[index] <= -abs(params.max_market_drawdown_pct):
                continue
        raw = momentum[index].copy()
        eligible = np.isfinite(raw) & (raw >= params.min_momentum_pct)
        if params.exclude_tqqq:
            eligible[tqqq_index] = False
        if params.inverse_mode == "exclude":
            eligible &= ~inverse_mask
        elif params.inverse_mode == "riskoff":
            eligible &= inverse_mask if risk_off else ~inverse_mask
        elif params.inverse_mode != "include":
            raise ValueError(f"unsupported inverse mode: {params.inverse_mode}")
        if confirmation is not None:
            current = closes[index - 1]
            eligible &= np.isfinite(confirmation[index])
            eligible &= np.isfinite(current)
            eligible &= current > confirmation[index]
        if symbol_drawdown is not None and params.max_symbol_drawdown_pct is not None:
            drawdown = symbol_drawdown[index]
            eligible &= np.isfinite(drawdown)
            eligible &= drawdown > -abs(params.max_symbol_drawdown_pct)
        if not bool(eligible.any()):
            continue
        ranked = np.where(eligible, raw, -np.inf)
        selected = int(np.argmax(ranked))
        top_momentum = float(ranked[selected])
        if params.base_mode != "pure":
            tqqq_momentum = float(momentum[index, tqqq_index])
            if not np.isfinite(tqqq_momentum):
                continue
            if top_momentum < tqqq_momentum + params.override_advantage_pct:
                continue
        weights[index, :] = 0.0
        weights[index, selected] = params.gross_exposure_scale
    return _portfolio_returns(weights, open_to_open_returns), weights


def _risk_off_hedge_gate(
    qqq_prior_close: np.ndarray,
    qqq_sma200: np.ndarray,
    qqq_mom120: np.ndarray,
    index: int,
) -> bool:
    return bool(
        np.isfinite(qqq_prior_close[index])
        and np.isfinite(qqq_sma200[index])
        and np.isfinite(qqq_mom120[index])
        and qqq_prior_close[index] < qqq_sma200[index]
        and qqq_mom120[index] < 0
    )


def _iter2_base_weights(closes: np.ndarray, cache: IndicatorCache) -> np.ndarray:
    weights = np.zeros_like(closes)
    qqq_index = UNIVERSE.index(MARKET_SYMBOL)
    tqqq_index = UNIVERSE.index(BENCHMARK_SYMBOL)
    qqq_sma250 = cache.sma[250][:, qqq_index]
    qqq_mom120 = cache.momentum[120][:, qqq_index]
    tqqq_sma50 = cache.sma[50][:, tqqq_index]
    tqqq_dd60 = cache.drawdown[60][:, tqqq_index]
    for index in range(251, len(closes) - 1):
        qqq_current = closes[index - 1, qqq_index]
        tqqq_current = closes[index - 1, tqqq_index]
        if (
            np.isfinite(qqq_current)
            and np.isfinite(tqqq_current)
            and qqq_current > qqq_sma250[index]
            and qqq_mom120[index] >= 0
            and tqqq_current > tqqq_sma50[index]
            and tqqq_dd60[index] > -20
        ):
            weights[index, tqqq_index] = 1.0
        elif np.isfinite(qqq_current) and qqq_current > qqq_sma250[index]:
            weights[index, qqq_index] = 0.75
    return weights


def _cycle_gate_passes(closes: np.ndarray, index: int, gate: str) -> bool:
    if gate == "none":
        return True
    qqq_index = UNIVERSE.index(MARKET_SYMBOL)
    checks = {
        "q200": _price_above_sma(closes, qqq_index, index, 200),
        "mom120": (_momentum_pct(closes, qqq_index, index, 120) or -100.0) > 0,
    }
    if gate == "q200":
        return checks["q200"]
    if gate == "mom120":
        return checks["mom120"]
    if gate == "q200ormom120":
        return checks["q200"] or checks["mom120"]
    if gate == "q200andmom120":
        return checks["q200"] and checks["mom120"]
    raise ValueError(f"unsupported cycle gate: {gate}")


def _cycle_gate_lookback(gate: str) -> int:
    if gate == "none":
        return 0
    if gate in {"q200", "q200ormom120", "q200andmom120"}:
        return 200
    if gate == "mom120":
        return 121
    raise ValueError(f"unsupported cycle gate: {gate}")


def _portfolio_returns(weights: np.ndarray, returns: np.ndarray) -> np.ndarray:
    clean_returns = np.nan_to_num(returns, nan=0.0, posinf=0.0, neginf=0.0)
    return (weights * clean_returns).sum(axis=1)


def _open_to_open_returns(opens: np.ndarray, *, cost_rate: float) -> np.ndarray:
    output = np.full_like(opens, np.nan)
    entry = opens[:-1]
    exit_price = opens[1:]
    valid = np.isfinite(entry) & np.isfinite(exit_price) & (entry > 0) & (exit_price > 0)
    values = np.full_like(entry, np.nan)
    values[valid] = exit_price[valid] * (1 - cost_rate) / (entry[valid] * (1 + cost_rate)) - 1
    output[:-1] = values
    return output


def _period_results(
    *,
    dates: list[str],
    selected_returns: np.ndarray,
    selected_weights: np.ndarray,
    iter2_returns: np.ndarray,
    iter2_weights: np.ndarray,
    raw_open_to_open: np.ndarray,
    first_tradable: int,
    end_index: int,
) -> list[dict[str, Any]]:
    windows = [
        ("full_long_history", dates[first_tradable], END_DATE),
        ("pre_2018_cycle", dates[first_tradable], "2017-12-29"),
        ("q4_2018", "2018-10-01", "2018-12-31"),
        ("covid_crash", "2020-02-19", "2020-03-23"),
        ("calendar_2022_bear", "2022-01-03", "2022-12-30"),
        ("post_2023_bull", "2023-01-03", END_DATE),
        ("current_oos_proxy", "2024-11-04", END_DATE),
    ]
    tqqq_returns = raw_open_to_open[:, UNIVERSE.index(BENCHMARK_SYMBOL)]
    qqq_returns = raw_open_to_open[:, UNIVERSE.index(MARKET_SYMBOL)]
    rows = []
    date_index = {date: index for index, date in enumerate(dates)}
    for label, start_date, end_date in windows:
        if start_date not in date_index or end_date not in date_index:
            continue
        start = max(date_index[start_date], first_tradable)
        end = min(date_index[end_date] + 1, end_index)
        if end <= start:
            continue
        rows.append(
            {
                "label": label,
                "start_date": dates[start],
                "end_date": dates[end - 1],
                "strategy": _metrics(dates, selected_returns, selected_weights, start, end),
                "reconstructed_iter2": _metrics(dates, iter2_returns, iter2_weights, start, end),
                "tqqq_buy_hold": _return_metrics(dates, tqqq_returns, start, end),
                "qqq_buy_hold": _return_metrics(dates, qqq_returns, start, end),
            }
        )
    return rows


def _annual_results(
    *,
    dates: list[str],
    selected_returns: np.ndarray,
    selected_weights: np.ndarray,
    iter2_returns: np.ndarray,
    iter2_weights: np.ndarray,
    raw_open_to_open: np.ndarray,
    first_tradable: int,
    end_index: int,
) -> list[dict[str, Any]]:
    tqqq_returns = raw_open_to_open[:, UNIVERSE.index(BENCHMARK_SYMBOL)]
    qqq_returns = raw_open_to_open[:, UNIVERSE.index(MARKET_SYMBOL)]
    rows = []
    for year in sorted({int(date[:4]) for date in dates[first_tradable:end_index]}):
        indices = [
            index
            for index, date in enumerate(dates)
            if first_tradable <= index < end_index and int(date[:4]) == year
        ]
        if not indices:
            continue
        start = min(indices)
        end = max(indices) + 1
        rows.append(
            {
                "year": year,
                "strategy": _metrics(dates, selected_returns, selected_weights, start, end),
                "reconstructed_iter2": _metrics(dates, iter2_returns, iter2_weights, start, end),
                "tqqq_buy_hold": _return_metrics(dates, tqqq_returns, start, end),
                "qqq_buy_hold": _return_metrics(dates, qqq_returns, start, end),
            }
        )
    return rows


def _calendar_metrics(
    dates: list[str],
    returns: np.ndarray,
    weights: np.ndarray,
    start_index: int,
    end_index: int,
) -> list[dict[str, Any]]:
    rows = []
    for year in sorted({int(date[:4]) for date in dates[start_index:end_index]}):
        indices = [
            index
            for index, date in enumerate(dates)
            if start_index <= index < end_index and int(date[:4]) == year
        ]
        if not indices:
            continue
        start = min(indices)
        end = max(indices) + 1
        rows.append({"year": year, "metrics": _metrics(dates, returns, weights, start, end)})
    return rows


def _benchmark_family(
    *,
    root: Path,
    dates: list[str],
    raw_open_to_open: np.ndarray,
    first_tradable: int,
    end_index: int,
) -> dict[str, Any]:
    rows = {}
    for symbol in [BENCHMARK_SYMBOL, MARKET_SYMBOL, "SMH"]:
        index = UNIVERSE.index(symbol)
        rows[f"{symbol.lower()}_buy_hold"] = _return_metrics(
            dates, raw_open_to_open[:, index], first_tradable, end_index
        )
    rows["equal_weight_universe"] = _return_metrics(
        dates, _equal_weight_returns(raw_open_to_open), first_tradable, end_index
    )
    rows["cash_proxy"] = _return_metrics(dates, np.zeros(len(dates)), first_tradable, end_index)
    proxy_rows = {}
    for symbol in BENCHMARK_PROXIES:
        path = root / DATA_DIR / f"{symbol.lower()}_daily_longbridge_adjusted.csv"
        frame = _read_price_csv(path)
        frame["date"] = frame["timestamp"].dt.date.astype(str)
        aligned = frame.set_index("date").reindex(dates)
        opens = aligned["open"].to_numpy(dtype=float)
        proxy_returns = _open_to_open_returns(opens.reshape(-1, 1), cost_rate=0.0)[:, 0]
        proxy_rows[f"{symbol.lower()}_buy_hold"] = _return_metrics(
            dates, proxy_returns, first_tradable, end_index
        )
    rows["sector_theme_proxies"] = proxy_rows
    best_symbol = None
    best_return = -math.inf
    for symbol in UNIVERSE:
        returns = raw_open_to_open[:, UNIVERSE.index(symbol)]
        metrics = _return_metrics(dates, returns, first_tradable, end_index)
        if metrics["days"] > 0 and metrics["total_return_pct"] > best_return:
            best_symbol = symbol
            best_return = metrics["total_return_pct"]
    rows["ex_post_best_symbol"] = {"symbol": best_symbol, "total_return_pct": best_return}
    return rows


def _anchored_yearly_walk_forward(
    *,
    dates: list[str],
    candidate_rows: list[dict[str, Any]],
    baseline_returns: np.ndarray,
    first_tradable: int,
) -> dict[str, Any]:
    rows = []
    years = sorted({int(date[:4]) for date in dates[first_tradable:]})
    for year in years[2:]:
        train_start = first_tradable
        train_end = next((i for i, date in enumerate(dates) if int(date[:4]) == year), None)
        if train_end is None or train_end - train_start < 252:
            continue
        test_indices = [i for i, date in enumerate(dates) if int(date[:4]) == year]
        if len(test_indices) < 20:
            continue
        test_start = min(test_indices)
        test_end = max(test_indices) + 1
        scored = []
        for row in candidate_rows:
            train = _metrics(dates, row["returns"], row["weights"], train_start, train_end)
            score = _score_candidate(train, [], None)
            scored.append((score, row, train))
        scored.sort(key=lambda item: item[0], reverse=True)
        _, selected, train = scored[0]
        test = _metrics(dates, selected["returns"], selected["weights"], test_start, test_end)
        baseline = _return_metrics(dates, baseline_returns, test_start, test_end)
        rows.append(
            {
                "year": year,
                "selected_route_label": selected["params"].label,
                "train": train,
                "test": test,
                "baseline_test": baseline,
                "positive_test": test["total_return_pct"] > 0,
                "beats_baseline_test": test["total_return_pct"] > baseline["total_return_pct"],
            }
        )
    return {
        "method": "anchored yearly walk-forward; each test year selects from prior dates only",
        "candidate_count": len(candidate_rows),
        "folds": rows,
        "fold_count": len(rows),
        "positive_folds": sum(row["positive_test"] for row in rows),
        "beats_baseline_folds": sum(row["beats_baseline_test"] for row in rows),
    }


def _best_standard_candidate(candidate_rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    eligible = [row for row in candidate_rows if _candidate_full_standard_pass(row)]
    if not eligible:
        return None
    eligible.sort(key=lambda row: row["full_window"]["total_return_pct"], reverse=True)
    return eligible[0]


def _candidate_full_standard_pass(row: dict[str, Any]) -> bool:
    full = row["full_window"]
    negative_years = sum(item["metrics"]["total_return_pct"] < 0 for item in row["annual"])
    return bool(
        full["beats_iter2_total_return"]
        and full["beats_tqqq_buy_hold_total_return"]
        and full["max_drawdown_pct"] > -65
        and full["sharpe_ratio"] is not None
        and full["sharpe_ratio"] >= 0.85
        and negative_years <= 4
        and full["max_symbol_exposure_share_pct"] <= 60
    )


def _pass_status(
    *,
    selected: dict[str, Any],
    best: dict[str, Any],
    best_standard: dict[str, Any] | None,
    walk_forward: dict[str, Any],
    annual: list[dict[str, Any]],
) -> dict[str, Any]:
    selected_full = selected["full_window"]
    best_standard_negative_years = (
        [row["year"] for row in best_standard["annual"] if row["metrics"]["total_return_pct"] < 0]
        if best_standard is not None
        else []
    )
    selected_negative_years = [
        row["year"] for row in annual if row["strategy"]["total_return_pct"] < 0
    ]
    selected_wf_rate = (
        walk_forward["positive_folds"] / walk_forward["fold_count"]
        if walk_forward["fold_count"]
        else 0.0
    )
    selected_research = (
        selected_full["beats_iter2_total_return"]
        and selected_full["beats_tqqq_buy_hold_total_return"]
        and selected_full["max_drawdown_pct"] > -65
        and selected_full["sharpe_ratio"] is not None
        and selected_full["sharpe_ratio"] >= 0.85
        and len(selected_negative_years) <= 4
        and selected_full["max_symbol_exposure_share_pct"] <= 60
        and selected_wf_rate >= 0.6
    )
    best_research = best_standard is not None and selected_wf_rate >= 0.6
    return {
        "workflow_pass": True,
        "selected_research_pass": bool(selected_research),
        "best_research_pass": bool(best_research),
        "llm_contribution_pass": False,
        "paper_ready_pass": False,
        "selected_negative_calendar_years": selected_negative_years,
        "best_score_candidate_label": best["params"].label,
        "best_score_candidate_blocker": None
        if _candidate_full_standard_pass(best)
        else "best score candidate fails full-window risk/Sharpe standard",
        "best_standard_candidate_label": (
            best_standard["params"].label if best_standard is not None else None
        ),
        "best_standard_negative_calendar_years": best_standard_negative_years,
        "walk_forward_positive_rate": selected_wf_rate,
        "paper_ready_blockers": [
            "Longbridge-adjusted long-history research is new evidence and needs forensics review.",
            "Current-symbol universe remains survivorship-biased without PIT membership evidence.",
            (
                "Source cards and promotion report must be refreshed before "
                "simulation/paper readiness."
            ),
            "No LLM/news/macro signal is enabled or paper-ready.",
        ],
    }


def _acceptance_standard() -> dict[str, Any]:
    return {
        "data_window": f"must test adjusted daily history from {START_DATE} through {END_DATE}",
        "return_gate": "full-window total return must beat reconstructed iter2 baseline",
        "stretch_return_gate": (
            "strict research pass requires beating TQQQ buy-and-hold total return"
        ),
        "risk_gate": "full-window max drawdown should remain better than -65%",
        "sharpe_gate": "full-window Sharpe should be >= 0.85",
        "calendar_gate": "target <= 4 negative calendar years; zero is the aspirational target",
        "concentration_gate": "max symbol exposure share should be <= 60%",
        "walk_forward_gate": ">= 60% anchored yearly folds should be positive",
        "paper_gate": (
            "paper_ready remains false until forensics, source cards, promotion, and readiness pass"
        ),
    }


def _score_candidate(
    full: dict[str, Any],
    years: list[dict[str, Any]],
    baseline: dict[str, Any] | None,
) -> float:
    annualized = full["annualized_return_pct"]
    sharpe = full["sharpe_ratio"] or 0.0
    drawdown = abs(full["max_drawdown_pct"])
    negative_years = sum(row["metrics"]["total_return_pct"] < 0 for row in years)
    positive_years = sum(row["metrics"]["total_return_pct"] > 0 for row in years)
    baseline_bonus = 0.0
    if baseline is not None:
        baseline_bonus = (full["total_return_pct"] - baseline["total_return_pct"]) / 20
    return (
        annualized
        + 15 * sharpe
        - 0.7 * drawdown
        + 2.0 * positive_years
        - 5.0 * negative_years
        + baseline_bonus
    )


def _metrics(
    dates: list[str],
    returns: np.ndarray,
    weights: np.ndarray,
    start: int,
    end: int,
) -> dict[str, Any]:
    result = _return_metrics(dates, returns, start, end)
    period_weights = weights[start:end]
    gross = np.nansum(np.abs(period_weights), axis=1) if period_weights.size else np.array([])
    symbol_exposure = (
        np.nansum(np.abs(period_weights), axis=0) if period_weights.size else np.array([])
    )
    total_exposure = float(np.nansum(symbol_exposure))
    exposure_by_symbol = {
        symbol: (
            float(symbol_exposure[index] / total_exposure * 100) if total_exposure > 0 else 0.0
        )
        for index, symbol in enumerate(UNIVERSE)
    }
    result.update(
        {
            "exposure_pct": float((gross > 1e-12).mean() * 100) if len(gross) else 0.0,
            "average_gross_exposure_pct": float(gross.mean() * 100) if len(gross) else 0.0,
            "max_symbol_weight_pct": float(np.nanmax(period_weights) * 100)
            if period_weights.size
            else 0.0,
            "max_symbol_exposure_share_pct": max(exposure_by_symbol.values())
            if exposure_by_symbol
            else 0.0,
            "selected_exposure_by_symbol_pct": exposure_by_symbol,
        }
    )
    return result


def _return_metrics(
    dates: list[str],
    returns: np.ndarray,
    start: int,
    end: int,
) -> dict[str, Any]:
    period = np.nan_to_num(returns[start:end].astype(float), nan=0.0, posinf=0.0, neginf=0.0)
    equity = np.cumprod(1 + period) if len(period) else np.array([])
    total = (float(equity[-1]) - 1) * 100 if len(equity) else 0.0
    annualized = (
        (float(equity[-1]) ** (252 / len(period)) - 1) * 100
        if len(period) and equity[-1] > 0
        else -100.0
    )
    sigma = float(period.std(ddof=0)) if len(period) else 0.0
    sharpe = (
        float(period.mean() / sigma * math.sqrt(252)) if len(period) > 1 and sigma > 0 else None
    )
    curve = np.r_[1.0, equity]
    drawdown = float((curve / np.maximum.accumulate(curve) - 1).min() * 100) if len(curve) else 0.0
    return {
        "start_date": dates[start] if start < len(dates) else None,
        "end_date": dates[end - 1] if end > start and end - 1 < len(dates) else None,
        "days": int(len(period)),
        "total_return_pct": total,
        "annualized_return_pct": annualized,
        "sharpe_ratio": sharpe,
        "max_drawdown_pct": drawdown,
    }


def _equal_weight_returns(raw_open_to_open: np.ndarray) -> np.ndarray:
    returns = np.zeros(raw_open_to_open.shape[0])
    for index in range(raw_open_to_open.shape[0]):
        row = raw_open_to_open[index]
        valid = np.isfinite(row)
        returns[index] = float(row[valid].mean()) if bool(valid.any()) else 0.0
    return returns


def _candidate_payload(row: dict[str, Any], *, selected_label: str | None = None) -> dict[str, Any]:
    payload = {
        "trial_id": row["trial_id"],
        "params": asdict(row["params"]) | {"label": row["params"].label},
        "score": row["score"],
        "full_window": row["full_window"],
        "annual": row["annual"],
        "negative_calendar_years": [
            item["year"] for item in row["annual"] if item["metrics"]["total_return_pct"] < 0
        ],
        "selected": row["params"].label == selected_label,
    }
    payload["full_window"]["beats_iter2_total_return"] = row["full_window"].get(
        "beats_iter2_total_return", False
    )
    return payload


def _grid_ranges(grid: list[BetaOverrideParams]) -> dict[str, list[Any]]:
    output: dict[str, set[Any]] = {}
    for params in grid:
        for key, value in asdict(params).items():
            output.setdefault(key, set()).add(value)
    return {key: sorted(values, key=str) for key, values in output.items()}


def _write_markdown(path: Path, payload: dict[str, Any]) -> None:
    selected = payload["selected_candidate"]
    best = payload["best_long_history_candidate"]
    best_standard = payload["best_standard_candidate"]
    reference = payload.get("reference_candidate")
    lines = [
        "# Long History Longbridge Research",
        "",
        f"- Strategy: `{payload['strategy_name']}`",
        f"- Data: Longbridge adjusted daily `{START_DATE}` to `{END_DATE}`",
        f"- Selected route: `{payload['selected_route_label']}`",
        f"- Selected research pass: `{payload['pass_status']['selected_research_pass']}`",
        f"- Best research pass: `{payload['pass_status']['best_research_pass']}`",
        "",
        "## Selected Candidate",
        "",
        f"- Route: `{selected['params']['label']}`",
        _metrics_line(selected["full_window"]),
        f"- Negative years: `{selected['negative_calendar_years']}`",
        (
            "- Beats TQQQ buy-and-hold total: "
            f"`{selected['full_window']['beats_tqqq_buy_hold_total_return']}`"
        ),
        "",
        "## Best Long-History Candidate",
        "",
        f"- Route: `{best['params']['label']}`",
        _metrics_line(best["full_window"]),
        "",
        "## Best Standard Candidate",
        "",
        (
            f"- Route: `{best_standard['params']['label']}`"
            if best_standard is not None
            else "- Route: `none`"
        ),
        (
            _metrics_line(best_standard["full_window"])
            if best_standard is not None
            else "- No candidate passed the strict full-window standard."
        ),
        (
            f"- Negative years: `{best_standard['negative_calendar_years']}`"
            if best_standard is not None
            else ""
        ),
        "",
        "## Reference Iter4 Route",
        "",
        (
            f"- Route: `{reference['params']['label']}`"
            if reference is not None
            else f"- Route: `{payload['reference_route_label']}` not present in this grid"
        ),
        _metrics_line(reference["full_window"]) if reference is not None else "",
        "",
        "## Benchmark Family",
        "",
        _benchmark_line(payload, "TQQQ buy-and-hold", "tqqq_buy_hold"),
        _benchmark_line(payload, "QQQ buy-and-hold", "qqq_buy_hold"),
        _benchmark_line(payload, "SMH buy-and-hold", "smh_buy_hold"),
        _benchmark_line(payload, "Equal-weight universe", "equal_weight_universe"),
        f"- Ex-post best symbol: `{payload['benchmark_family']['ex_post_best_symbol']['symbol']}` "
        f"total `{_fmt(payload['benchmark_family']['ex_post_best_symbol']['total_return_pct'])}%`",
        "",
        "## Period Results",
        "",
        (
            "| Period | Strategy Total | Strategy Ann. | Strategy DD | Iter2 Total | "
            "TQQQ B&H | QQQ B&H |"
        ),
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in payload["periods"]:
        lines.append(
            f"| {row['label']} | {_fmt(row['strategy']['total_return_pct'])}% | "
            f"{_fmt(row['strategy']['annualized_return_pct'])}% | "
            f"{_fmt(row['strategy']['max_drawdown_pct'])}% | "
            f"{_fmt(row['reconstructed_iter2']['total_return_pct'])}% | "
            f"{_fmt(row['tqqq_buy_hold']['total_return_pct'])}% | "
            f"{_fmt(row['qqq_buy_hold']['total_return_pct'])}% |"
        )
    lines.extend(
        [
            "",
            "## Annual Results",
            "",
            "| Year | Strategy | Iter2 | TQQQ B&H | QQQ B&H |",
            "|---:|---:|---:|---:|---:|",
        ]
    )
    for row in payload["annual_results"]:
        lines.append(
            f"| {row['year']} | {_fmt(row['strategy']['total_return_pct'])}% | "
            f"{_fmt(row['reconstructed_iter2']['total_return_pct'])}% | "
            f"{_fmt(row['tqqq_buy_hold']['total_return_pct'])}% | "
            f"{_fmt(row['qqq_buy_hold']['total_return_pct'])}% |"
        )
    lines.extend(
        [
            "",
            "## Walk-Forward",
            "",
            f"- Method: {payload['walk_forward']['method']}",
            f"- Positive folds: `{payload['walk_forward']['positive_folds']}/"
            f"{payload['walk_forward']['fold_count']}`",
            f"- Beats baseline folds: `{payload['walk_forward']['beats_baseline_folds']}/"
            f"{payload['walk_forward']['fold_count']}`",
            "",
            "## Caveats",
            "",
            *[f"- {item}" for item in payload["data_profile"]["caveats"]],
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _metrics_line(metrics: dict[str, Any]) -> str:
    return (
        f"- Total `{_fmt(metrics['total_return_pct'])}%`, annualized "
        f"`{_fmt(metrics['annualized_return_pct'])}%`, Sharpe "
        f"`{_fmt(metrics['sharpe_ratio'])}`, max DD "
        f"`{_fmt(metrics['max_drawdown_pct'])}%`"
    )


def _benchmark_line(payload: dict[str, Any], label: str, key: str) -> str:
    metrics = payload["benchmark_family"][key]
    return f"- {label}: {_metrics_line(metrics).removeprefix('- ')}"


def _mean_window(closes: np.ndarray, symbol_index: int, index: int, lookback: int) -> float | None:
    if index < lookback:
        return None
    window = closes[index - lookback : index, symbol_index]
    if len(window) < lookback or not bool(np.isfinite(window).all()):
        return None
    return float(window.mean())


def _momentum_pct(
    closes: np.ndarray,
    symbol_index: int,
    index: int,
    lookback: int,
) -> float | None:
    previous_index = index - lookback - 1
    current_index = index - 1
    if previous_index < 0 or current_index < 0:
        return None
    previous = closes[previous_index, symbol_index]
    current = closes[current_index, symbol_index]
    if not np.isfinite(previous) or not np.isfinite(current) or previous <= 0:
        return None
    return float((current / previous - 1) * 100)


def _drawdown_pct(
    closes: np.ndarray,
    symbol_index: int,
    index: int,
    lookback: int,
) -> float | None:
    if index < lookback:
        return None
    window = closes[index - lookback : index, symbol_index]
    if len(window) < lookback or not bool(np.isfinite(window).all()):
        return None
    peak = float(window.max())
    if peak <= 0:
        return None
    return float((window[-1] / peak - 1) * 100)


def _price_above_sma(closes: np.ndarray, symbol_index: int, index: int, lookback: int) -> bool:
    sma = _mean_window(closes, symbol_index, index, lookback)
    current = closes[index - 1, symbol_index]
    return sma is not None and np.isfinite(current) and current > sma


def _normalize_frame(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return _empty_frame()
    output = frame[["timestamp", "open", "high", "low", "close", "volume"]].copy()
    output["timestamp"] = pd.to_datetime(output["timestamp"], utc=True)
    output = output.sort_values("timestamp").drop_duplicates("timestamp", keep="last")
    for column in ["open", "high", "low", "close", "volume"]:
        output[column] = pd.to_numeric(output[column], errors="coerce")
    return output.reset_index(drop=True)


def _read_price_csv(path: Path) -> pd.DataFrame:
    return _normalize_frame(pd.read_csv(path))


def _empty_frame() -> pd.DataFrame:
    return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])


def _covers(frame: pd.DataFrame, start: datetime, end: datetime) -> bool:
    if frame.empty:
        return False
    timestamps = pd.to_datetime(frame["timestamp"], utc=True)
    dates = timestamps.dt.date
    return bool(dates.min() <= end.date() and dates.max() >= end.date())


def _timestamp(value: str) -> datetime:
    return pd.Timestamp(value, tz=UTC).to_pydatetime()


def _iso(value: Any) -> str:
    return pd.Timestamp(value).isoformat()


def _fmt(value: Any) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float) and math.isnan(value):
        return "n/a"
    return f"{float(value):.2f}"


if __name__ == "__main__":
    main()
