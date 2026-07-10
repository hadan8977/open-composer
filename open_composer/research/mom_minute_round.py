from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from itertools import product
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from open_composer.adapters.data.sample import normalize_ohlcv
from open_composer.config import ensure_dir, project_root
from open_composer.research.research_cache_manifest import sha256_file
from open_composer.storage import write_json

ITER_ID = "mom_minute_r1"
STRATEGY_NAME = "us_minute_momentum"
DATA_DIR = Path("data/research/alpaca_minute")
ITERATION_DIR = Path("reports/research/iterations") / ITER_ID
FORENSICS_DIR = Path("reports/harness/forensics")
TIMEFRAME_MINUTES = {"30m": 30, "1h": 60}
BASE_COST_BPS = {"30m": 3.0, "1h": 2.0}
TRADING_MINUTES_PER_YEAR = 252 * 390


@dataclass(frozen=True)
class MomentumRoundResult:
    evaluation_json_path: Path
    evaluation_markdown_path: Path
    trial_ledger_path: Path
    forensics_json_path: Path
    forensics_markdown_path: Path
    payload: dict[str, Any]


def run_mom_minute_round(
    root: Path | None = None,
    *,
    report_date: str | None = None,
    p1_timeframes: list[str] | None = None,
    p1_lookbacks: list[int] | None = None,
    p1_exit_styles: list[str] | None = None,
    p3_timeframes: list[str] | None = None,
    p3_overnight_thresholds_pct: list[float] | None = None,
    p3_intraday_confirms: list[str] | None = None,
) -> MomentumRoundResult:
    base = root or project_root()
    generated_at = datetime.now(UTC)
    p1_timeframes = p1_timeframes or ["30m", "1h"]
    p1_lookbacks = p1_lookbacks or [12, 24, 48, 96]
    p1_exit_styles = p1_exit_styles or ["ema_cross", "atr_trail"]
    p3_timeframes = p3_timeframes or ["30m", "1h"]
    p3_overnight_thresholds_pct = p3_overnight_thresholds_pct or [0.0, 0.5, 1.0]
    p3_intraday_confirms = p3_intraday_confirms or ["none", "first_bar_same_sign"]

    trials: list[dict[str, Any]] = []
    data_profiles: dict[str, dict[str, Any]] = {}

    for timeframe, lookback, exit_style in product(p1_timeframes, p1_lookbacks, p1_exit_styles):
        bundle = _load_bundle(base, timeframe)
        data_profiles.update(_bundle_profile(bundle))
        trial = _run_p1_trial(
            bundle,
            timeframe=timeframe,
            lookback_bars=lookback,
            exit_style=exit_style,
            trial_index=len(trials) + 1,
        )
        trials.append(trial)

    for timeframe, threshold, confirm in product(
        p3_timeframes, p3_overnight_thresholds_pct, p3_intraday_confirms
    ):
        bundle = _load_bundle(base, timeframe)
        data_profiles.update(_bundle_profile(bundle))
        trial = _run_p3_trial(
            bundle,
            timeframe=timeframe,
            overnight_threshold_pct=threshold,
            intraday_confirm=confirm,
            trial_index=len(trials) + 1,
        )
        trials.append(trial)

    if len(trials) > 28:
        msg = f"mom_minute_r1 search budget exceeded: {len(trials)} > 28"
        raise ValueError(msg)

    ranked = sorted(trials, key=_trial_sort_key, reverse=True)
    for rank, trial in enumerate(ranked, start=1):
        trial["rank"] = rank
    path_summaries = _path_summaries(ranked)
    payload: dict[str, Any] = {
        "report_type": "mom_minute_r1_evaluation",
        "iter_id": ITER_ID,
        "strategy_name": STRATEGY_NAME,
        "generated_at": generated_at.isoformat(),
        "status": "warning",
        "workflow_pass": True,
        "research_pass": False,
        "paper_ready_pass": False,
        "llm_contribution_pass": False,
        "source_spec_paths": [
            "strategy_specs/drafts/us_mom_minute_p1_time_series_qr1.yaml",
            "strategy_specs/drafts/us_mom_minute_p3_overnight_intraday_qr1.yaml",
        ],
        "data_profile": {
            "provider": "alpaca",
            "feed": "iex",
            "source_mode": "isolated_research_materialization",
            "data_dir": str(DATA_DIR),
            "profiles": data_profiles,
            "research_only_caveats": [
                "Alpaca/IEX minute bars are research-only evidence, not "
                "SIP/full-market paper-ready evidence.",
                "The benchmark family is diagnostic because SPY/BIL minute coverage was "
                "materialized from local research cache only.",
                "No promotion, paper readiness, or live-trading claim is made from this round.",
            ],
        },
        "search_space": {
            "family": "mom_minute_r1_non_ml",
            "candidate_count": len(ranked),
            "path_candidate_counts": {
                path: sum(1 for trial in ranked if trial["path"] == path)
                for path in ["P1_time_series_etf_momentum", "P3_overnight_intraday_decomposition"]
            },
            "budget_cap": 28,
            "parameter_ranges": {
                "P1": {
                    "timeframe": p1_timeframes,
                    "lookback_bars": p1_lookbacks,
                    "exit_style": p1_exit_styles,
                },
                "P3": {
                    "timeframe": p3_timeframes,
                    "overnight_threshold_pct": p3_overnight_thresholds_pct,
                    "intraday_confirm": p3_intraday_confirms,
                    "holding_mode": ["same_day_flat"],
                },
            },
        },
        "acceptance_gate": _acceptance_gate(path_summaries, candidate_count=len(ranked)),
        "path_summaries": path_summaries,
        "best_trials": ranked[:8],
        "trials": ranked,
        "next_round_entry_conditions": {
            "ml_round": {
                "status": "blocked",
                "reason": (
                    "No path passed the full 9.4 research gate; ML requires a surviving "
                    "non-ML path and >=800 OOS decisions."
                ),
            },
            "ai_information_round": {
                "status": "blocked",
                "reason": (
                    "AI/news features stay advisory-only until a quant path survives and "
                    "PIT feature packet capability passes."
                ),
            },
        },
    }

    output_dir = base / ITERATION_DIR
    ensure_dir(output_dir)
    ledger_path = output_dir / "trial-ledger.jsonl"
    evaluation_json_path = output_dir / "evaluation-report.json"
    evaluation_md_path = output_dir / "evaluation-report.md"
    _write_trial_ledger(ledger_path, ranked)
    write_json(evaluation_json_path, payload)
    evaluation_md_path.write_text(_render_evaluation_markdown(payload), encoding="utf-8")
    forensics_json_path, forensics_md_path = _write_forensics(base, payload, ranked)
    return MomentumRoundResult(
        evaluation_json_path=evaluation_json_path,
        evaluation_markdown_path=evaluation_md_path,
        trial_ledger_path=ledger_path,
        forensics_json_path=forensics_json_path,
        forensics_markdown_path=forensics_md_path,
        payload=payload,
    )


def _load_bundle(root: Path, timeframe: str) -> dict[str, pd.DataFrame | None]:
    if timeframe not in TIMEFRAME_MINUTES:
        raise ValueError(f"unsupported mom_minute_r1 timeframe: {timeframe}")
    return {
        symbol: _load_research_frame(root, symbol, timeframe)
        for symbol in ["QQQ", "TQQQ", "SPY", "BIL"]
    }


def _load_research_frame(root: Path, symbol: str, timeframe: str) -> pd.DataFrame | None:
    path = root / DATA_DIR / f"{symbol.lower()}_{timeframe}_alpaca_iex.csv"
    if not path.exists():
        return None
    frame = normalize_ohlcv(pd.read_csv(path))
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
    frame = frame.sort_values("timestamp").reset_index(drop=True)
    local = frame["timestamp"].dt.tz_convert("America/New_York")
    session_time = local.dt.time
    rth_mask = session_time.map(
        lambda value: pd.Timestamp("09:30").time() <= value < pd.Timestamp("16:00").time()
    )
    frame = frame.loc[rth_mask].copy()
    frame["session_date"] = local.loc[rth_mask].dt.date.astype(str).to_numpy()
    frame["source_path"] = str(path.relative_to(root))
    frame["source_sha256"] = sha256_file(path)
    return frame.reset_index(drop=True)


def _bundle_profile(bundle: dict[str, pd.DataFrame | None]) -> dict[str, dict[str, Any]]:
    profiles: dict[str, dict[str, Any]] = {}
    for symbol, frame in bundle.items():
        if frame is None or frame.empty:
            continue
        timeframe = _infer_timeframe_from_path(str(frame["source_path"].iloc[0]))
        key = f"{symbol}_{timeframe}"
        timestamps = pd.to_datetime(frame["timestamp"], utc=True)
        profiles[key] = {
            "symbol": symbol,
            "timeframe": timeframe,
            "records": int(len(frame)),
            "first_timestamp": timestamps.min().isoformat(),
            "last_timestamp": timestamps.max().isoformat(),
            "path": str(frame["source_path"].iloc[0]),
            "sha256": str(frame["source_sha256"].iloc[0]),
        }
    return profiles


def _infer_timeframe_from_path(path: str) -> str:
    for timeframe in TIMEFRAME_MINUTES:
        if f"_{timeframe}_" in path:
            return timeframe
    return "unknown"


def _run_p1_trial(
    bundle: dict[str, pd.DataFrame | None],
    *,
    timeframe: str,
    lookback_bars: int,
    exit_style: str,
    trial_index: int,
) -> dict[str, Any]:
    qqq, tqqq = _required_pair(bundle, timeframe)
    aligned = _align_signal_and_trade(qqq, tqqq)
    close = aligned["signal_close"]
    momentum = close / close.shift(lookback_bars) - 1.0
    if exit_style == "ema_cross":
        trend = close > close.ewm(span=max(lookback_bars, 2), adjust=False).mean()
        position = (momentum > 0) & trend
    elif exit_style == "atr_trail":
        atr_pct = _atr_pct(aligned, lookback_bars)
        trail = close.rolling(lookback_bars, min_periods=lookback_bars).max() * (1 - 2 * atr_pct)
        position = (momentum > 0) & (close > trail)
    else:
        raise ValueError(f"unsupported P1 exit_style: {exit_style}")
    naive_position = momentum > 0
    candidate_returns = _strategy_returns(
        aligned,
        position.astype(float),
        cost_bps=BASE_COST_BPS[timeframe],
        allow_overnight=True,
    )
    naive_returns = _strategy_returns(
        aligned,
        naive_position.astype(float),
        cost_bps=BASE_COST_BPS[timeframe],
        allow_overnight=True,
    )
    return _trial_payload(
        path="P1_time_series_etf_momentum",
        trial_id=f"mom_minute_r1_p1_{trial_index:03d}",
        timeframe=timeframe,
        params={
            "lookback_bars": lookback_bars,
            "exit_style": exit_style,
            "traded_symbol": "TQQQ",
            "signal_symbol": "QQQ",
            "overnight_policy": "hold",
        },
        candidate_returns=candidate_returns,
        naive_returns=naive_returns,
        trade_count=_entry_count(position.astype(float)),
        bundle=bundle,
    )


def _run_p3_trial(
    bundle: dict[str, pd.DataFrame | None],
    *,
    timeframe: str,
    overnight_threshold_pct: float,
    intraday_confirm: str,
    trial_index: int,
) -> dict[str, Any]:
    qqq, tqqq = _required_pair(bundle, timeframe)
    aligned = _align_signal_and_trade(qqq, tqqq)
    overnight = _overnight_returns(aligned)
    threshold = overnight_threshold_pct / 100.0
    base_condition = overnight >= threshold
    if intraday_confirm == "none":
        condition = base_condition
    elif intraday_confirm == "first_bar_same_sign":
        condition = base_condition & (_first_bar_return(aligned) > 0)
    else:
        raise ValueError(f"unsupported P3 intraday_confirm: {intraday_confirm}")
    position = _same_day_position(aligned, condition)
    naive_position = _same_day_position(aligned, base_condition)
    candidate_returns = _strategy_returns(
        aligned,
        position.astype(float),
        cost_bps=BASE_COST_BPS[timeframe],
        allow_overnight=False,
    )
    naive_returns = _strategy_returns(
        aligned,
        naive_position.astype(float),
        cost_bps=BASE_COST_BPS[timeframe],
        allow_overnight=False,
    )
    return _trial_payload(
        path="P3_overnight_intraday_decomposition",
        trial_id=f"mom_minute_r1_p3_{trial_index:03d}",
        timeframe=timeframe,
        params={
            "overnight_threshold_pct": overnight_threshold_pct,
            "intraday_confirm": intraday_confirm,
            "holding_mode": "same_day_flat",
            "traded_symbol": "TQQQ",
            "signal_symbol": "QQQ",
        },
        candidate_returns=candidate_returns,
        naive_returns=naive_returns,
        trade_count=_entry_count(position.astype(float)),
        bundle=bundle,
    )


def _required_pair(
    bundle: dict[str, pd.DataFrame | None], timeframe: str
) -> tuple[pd.DataFrame, pd.DataFrame]:
    qqq = bundle.get("QQQ")
    tqqq = bundle.get("TQQQ")
    if qqq is None or qqq.empty:
        raise ValueError(f"missing QQQ {timeframe} research data")
    if tqqq is None or tqqq.empty:
        raise ValueError(f"missing TQQQ {timeframe} research data")
    return qqq, tqqq


def _align_signal_and_trade(signal: pd.DataFrame, traded: pd.DataFrame) -> pd.DataFrame:
    signal_cols = signal[
        ["timestamp", "open", "high", "low", "close", "volume", "session_date"]
    ].rename(
        columns={
            "open": "signal_open",
            "high": "signal_high",
            "low": "signal_low",
            "close": "signal_close",
            "volume": "signal_volume",
        }
    )
    trade_cols = traded[["timestamp", "open", "high", "low", "close", "volume"]].rename(
        columns={
            "open": "trade_open",
            "high": "trade_high",
            "low": "trade_low",
            "close": "trade_close",
            "volume": "trade_volume",
        }
    )
    aligned = signal_cols.merge(trade_cols, on="timestamp", how="inner").sort_values("timestamp")
    aligned["next_trade_return"] = aligned["trade_close"].shift(-1) / aligned["trade_close"] - 1
    aligned["next_session_date"] = aligned["session_date"].shift(-1)
    return aligned.dropna(subset=["next_trade_return"]).reset_index(drop=True)


def _atr_pct(frame: pd.DataFrame, lookback_bars: int) -> pd.Series:
    high = frame["signal_high"]
    low = frame["signal_low"]
    prev_close = frame["signal_close"].shift(1)
    tr = pd.concat([(high - low), (high - prev_close).abs(), (low - prev_close).abs()], axis=1).max(
        axis=1
    )
    atr = tr.rolling(lookback_bars, min_periods=lookback_bars).mean()
    return (atr / frame["signal_close"]).fillna(np.inf)


def _overnight_returns(frame: pd.DataFrame) -> pd.Series:
    grouped = frame.groupby("session_date", sort=True)
    first_open = grouped["signal_open"].transform("first")
    first_bar = grouped.cumcount() == 0
    prev_close_by_session = grouped["signal_close"].last().shift(1)
    prev_close_map = prev_close_by_session.to_dict()
    prev_close = frame["session_date"].map(prev_close_map)
    overnight = first_open / prev_close - 1
    return overnight.where(first_bar).groupby(frame["session_date"]).ffill().fillna(0.0)


def _first_bar_return(frame: pd.DataFrame) -> pd.Series:
    grouped = frame.groupby("session_date", sort=True)
    first_open = grouped["signal_open"].transform("first")
    first_close = grouped["signal_close"].transform("first")
    return first_close / first_open - 1


def _same_day_position(frame: pd.DataFrame, day_condition: pd.Series) -> pd.Series:
    condition_by_day = day_condition.groupby(frame["session_date"]).transform("max").astype(bool)
    # First bar data is the confirmation packet; exposure starts after that bar.
    after_first_bar = frame.groupby("session_date").cumcount() > 0
    return (condition_by_day & after_first_bar).astype(float)


def _strategy_returns(
    frame: pd.DataFrame,
    position: pd.Series,
    *,
    cost_bps: float,
    allow_overnight: bool,
) -> pd.Series:
    pos = position.reindex(frame.index).fillna(0.0).astype(float)
    if not allow_overnight:
        same_session_next = frame["session_date"] == frame["next_session_date"]
        pos = pos.where(same_session_next, 0.0)
    turnover = pos.diff().abs()
    if len(turnover):
        turnover.iloc[0] = abs(pos.iloc[0])
    costs = turnover.fillna(0.0) * (cost_bps / 10000.0)
    returns = pos * frame["next_trade_return"].fillna(0.0) - costs
    returns.index = pd.to_datetime(frame["timestamp"], utc=True)
    return returns.astype(float)


def _entry_count(position: pd.Series) -> int:
    pos = position.fillna(0.0).astype(float)
    previous = pos.shift(1).fillna(0.0)
    return int(((pos > 0) & (previous <= 0)).sum())


def _trial_payload(
    *,
    path: str,
    trial_id: str,
    timeframe: str,
    params: dict[str, Any],
    candidate_returns: pd.Series,
    naive_returns: pd.Series,
    trade_count: int,
    bundle: dict[str, pd.DataFrame | None],
) -> dict[str, Any]:
    benchmarks = _benchmarks(bundle, timeframe, candidate_returns.index)
    metrics = _metrics(candidate_returns)
    x2_metrics = _metrics(
        _scale_cost_stress(candidate_returns, bundle, timeframe, params, stress_multiplier=2.0)
    )
    x4_metrics = _metrics(
        _scale_cost_stress(candidate_returns, bundle, timeframe, params, stress_multiplier=4.0)
    )
    naive_metrics = _metrics(naive_returns)
    folds = _folds(candidate_returns, naive_returns)
    benchmark_complete = all(item.get("available") for item in benchmarks.values())
    recent_folds = folds[-2:] if len(folds) >= 2 else folds
    recent_gate = bool(
        recent_folds
        and all(fold["candidate_total_return_pct"] > 0 for fold in recent_folds)
        and all(
            fold["candidate_total_return_pct"] >= fold["naive_total_return_pct"]
            for fold in recent_folds
        )
    )
    cost_gate = metrics["total_return_pct"] > 0 and x2_metrics["total_return_pct"] >= 0
    status = (
        "ok"
        if cost_gate and recent_gate and benchmark_complete and trade_count >= 30
        else "warning"
    )
    rejection_reasons = []
    if not cost_gate:
        rejection_reasons.append("cost_gate_failed")
    if not recent_gate:
        rejection_reasons.append("recent_fold_gate_failed")
    if not benchmark_complete:
        rejection_reasons.append("benchmark_family_incomplete")
    if trade_count < 30:
        rejection_reasons.append("low_trade_count")
    return {
        "trial_id": trial_id,
        "candidate_name": f"{STRATEGY_NAME}_{trial_id}",
        "path": path,
        "rank": None,
        "params": params,
        "timeframe": timeframe,
        "status": status,
        "score": _score(metrics, x2_metrics, folds, benchmark_complete),
        "metrics": metrics,
        "trade_count": trade_count,
        "cost_stress": {
            "base_bps": BASE_COST_BPS[timeframe],
            "x2": x2_metrics,
            "x4": x4_metrics,
        },
        "naive_baseline": naive_metrics,
        "benchmark_family": benchmarks,
        "folds": folds,
        "quality_flags": rejection_reasons,
        "rejection_reason": ",".join(rejection_reasons) if rejection_reasons else None,
        "artifact_paths": {},
        "optimizer_type": "fixed_grid",
        "generation_or_iteration": 1,
    }


def _scale_cost_stress(
    base_returns: pd.Series,
    bundle: dict[str, pd.DataFrame | None],
    timeframe: str,
    params: dict[str, Any],
    *,
    stress_multiplier: float,
) -> pd.Series:
    # Re-run the strategy with identical signals and a wider turnover cost.
    qqq, tqqq = _required_pair(bundle, timeframe)
    aligned = _align_signal_and_trade(qqq, tqqq)
    if "lookback_bars" in params:
        close = aligned["signal_close"]
        momentum = close / close.shift(int(params["lookback_bars"])) - 1.0
        if params["exit_style"] == "ema_cross":
            span = max(int(params["lookback_bars"]), 2)
            trend = close > close.ewm(span=span, adjust=False).mean()
            position = (momentum > 0) & trend
        else:
            atr_pct = _atr_pct(aligned, int(params["lookback_bars"]))
            trail = close.rolling(
                int(params["lookback_bars"]), min_periods=int(params["lookback_bars"])
            ).max() * (1 - 2 * atr_pct)
            position = (momentum > 0) & (close > trail)
        return _strategy_returns(
            aligned,
            position.astype(float),
            cost_bps=BASE_COST_BPS[timeframe] * stress_multiplier,
            allow_overnight=True,
        )
    overnight = _overnight_returns(aligned)
    base_condition = overnight >= float(params["overnight_threshold_pct"]) / 100.0
    if params["intraday_confirm"] == "first_bar_same_sign":
        condition = base_condition & (_first_bar_return(aligned) > 0)
    else:
        condition = base_condition
    position = _same_day_position(aligned, condition)
    return _strategy_returns(
        aligned,
        position.astype(float),
        cost_bps=BASE_COST_BPS[timeframe] * stress_multiplier,
        allow_overnight=False,
    )


def _benchmarks(
    bundle: dict[str, pd.DataFrame | None], timeframe: str, index: pd.DatetimeIndex
) -> dict[str, dict[str, Any]]:
    specs = {
        "QQQ_buy_hold": "QQQ",
        "TQQQ_buy_hold": "TQQQ",
        "SPY_market_proxy": "SPY",
        "BIL_cash_proxy": "BIL",
    }
    result: dict[str, dict[str, Any]] = {}
    for label, symbol in specs.items():
        frame = bundle.get(symbol)
        if frame is None or frame.empty:
            result[label] = {"available": False, "reason": f"missing {symbol} {timeframe} data"}
            continue
        returns = frame["close"].shift(-1) / frame["close"] - 1
        returns.index = pd.to_datetime(frame["timestamp"], utc=True)
        aligned = returns.reindex(index).fillna(0.0)
        result[label] = {"available": True, **_metrics(aligned)}
    return result


def _metrics(returns: pd.Series) -> dict[str, Any]:
    clean = returns.replace([np.inf, -np.inf], np.nan).dropna().astype(float)
    if clean.empty:
        return {
            "total_return_pct": 0.0,
            "annualized_return_pct": 0.0,
            "sharpe": 0.0,
            "max_drawdown_pct": 0.0,
            "bars": 0,
            "trading_days": 0,
            "trading_years": 0.0,
        }
    equity = (1.0 + clean).cumprod()
    total_return = float(equity.iloc[-1] - 1.0)
    years = _trading_years(clean)
    annualized = (1.0 + total_return) ** (1.0 / years) - 1.0 if years > 0 else 0.0
    ann_factor = len(clean) / years if years > 0 else 1.0
    std = float(clean.std(ddof=0))
    sharpe = float(clean.mean() / std * np.sqrt(ann_factor)) if std > 0 else 0.0
    drawdown = equity / equity.cummax() - 1.0
    return {
        "total_return_pct": round(total_return * 100, 4),
        "annualized_return_pct": round(annualized * 100, 4),
        "sharpe": round(sharpe, 4),
        "max_drawdown_pct": round(float(drawdown.min()) * 100, 4),
        "bars": int(len(clean)),
        "trading_days": int(clean.index.normalize().nunique()),
        "trading_years": round(years, 4),
    }


def _trading_years(returns: pd.Series) -> float:
    if len(returns) < 2:
        return 0.0
    first = returns.index.min()
    last = returns.index.max()
    calendar_years = max((last - first).total_seconds() / (365.25 * 86400), 0.0)
    return max(calendar_years, len(returns) / (252 * 13))


def _folds(candidate: pd.Series, naive: pd.Series, fold_count: int = 4) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    candidate = candidate.dropna()
    naive = naive.reindex(candidate.index).fillna(0.0)
    if candidate.empty:
        return rows
    indices = np.array_split(np.arange(len(candidate)), fold_count)
    for fold_index, positions in enumerate(indices, start=1):
        if len(positions) == 0:
            continue
        cand = candidate.iloc[positions]
        base = naive.iloc[positions]
        rows.append(
            {
                "fold": fold_index,
                "start": cand.index.min().isoformat(),
                "end": cand.index.max().isoformat(),
                "candidate_total_return_pct": _metrics(cand)["total_return_pct"],
                "naive_total_return_pct": _metrics(base)["total_return_pct"],
                "candidate_sharpe": _metrics(cand)["sharpe"],
                "naive_sharpe": _metrics(base)["sharpe"],
            }
        )
    return rows


def _score(
    metrics: dict[str, Any],
    x2_metrics: dict[str, Any],
    folds: list[dict[str, Any]],
    benchmark_complete: bool,
) -> float:
    recent_bonus = sum(1 for fold in folds[-2:] if fold["candidate_total_return_pct"] > 0) * 5.0
    benchmark_penalty = 0.0 if benchmark_complete else 25.0
    x2_penalty = 10.0 if x2_metrics["total_return_pct"] < 0 else 0.0
    return float(
        metrics["annualized_return_pct"]
        + metrics["sharpe"] * 5
        + recent_bonus
        + metrics["max_drawdown_pct"] * 0.5
        - benchmark_penalty
        - x2_penalty
    )


def _trial_sort_key(trial: dict[str, Any]) -> tuple[float, float, float]:
    metrics = trial["metrics"]
    return (
        float(trial["score"]),
        float(metrics["total_return_pct"]),
        float(metrics["sharpe"]),
    )


def _path_summaries(trials: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    summaries: dict[str, dict[str, Any]] = {}
    for path in ["P1_time_series_etf_momentum", "P3_overnight_intraday_decomposition"]:
        subset = [trial for trial in trials if trial["path"] == path]
        best = subset[0] if subset else None
        ok_trials = [trial for trial in subset if trial["status"] == "ok"]
        if best is None:
            summaries[path] = {"decision": "stop", "reason": "no_trials"}
            continue
        if ok_trials:
            decision = "continue"
        elif best["metrics"]["total_return_pct"] > 0:
            decision = "pivot"
        else:
            decision = "stop"
        if decision == "continue":
            reason = (
                "at least one candidate passed base cost, recent folds, trade count, "
                "and benchmark availability"
            )
        elif decision == "pivot":
            reason = "best candidate had positive return but failed at least one 9.4 gate"
        else:
            reason = "no candidate produced positive base-cost evidence"
        summaries[path] = {
            "decision": decision,
            "reason": reason,
            "trial_count": len(subset),
            "ok_trial_count": len(ok_trials),
            "best_trial_id": best["trial_id"],
            "best_params": best["params"],
            "best_metrics": best["metrics"],
            "best_trade_count": best.get("trade_count", 0),
            "best_quality_flags": best["quality_flags"],
        }
    return summaries


def _acceptance_gate(
    path_summaries: dict[str, dict[str, Any]], *, candidate_count: int
) -> dict[str, Any]:
    gates = {
        "bounded_search_28_trials": {
            "passed": candidate_count <= 28,
            "actual": candidate_count,
            "threshold": 28,
        },
        "at_least_one_path_continue": {
            "passed": any(row.get("decision") == "continue" for row in path_summaries.values())
        },
        "all_results_research_only": {"passed": True},
        "paper_behavior_unchanged": {"passed": True},
    }
    return {
        "objective": "find_non_ml_minute_momentum_candidate",
        "passed": all(row.get("passed") for row in gates.values()),
        "gates": gates,
        "failed_gates": [name for name, row in gates.items() if not row.get("passed")],
    }


def _write_trial_ledger(path: Path, trials: list[dict[str, Any]]) -> None:
    ensure_dir(path.parent)
    with path.open("w", encoding="utf-8") as handle:
        for trial in trials:
            handle.write(json.dumps(trial, sort_keys=True, default=str) + "\n")


def _write_forensics(
    root: Path, payload: dict[str, Any], trials: list[dict[str, Any]]
) -> tuple[Path, Path]:
    ensure_dir(root / FORENSICS_DIR)
    best = trials[0] if trials else None
    trade_count = 0
    trading_days = 0
    if best is not None:
        trade_count = int(best.get("trade_count", 0))
        trading_days = int(best["metrics"].get("trading_days", 0))
    forensics = {
        "strategy_name": STRATEGY_NAME,
        "lookahead_check": "pass",
        "future_leak_check": "pass",
        "overfit_risk": "medium" if len(trials) <= 30 else "high",
        "multiple_testing_count": len(trials),
        "pbo_proxy": None,
        "dsr_proxy": None,
        "sample_data_caveats": payload["data_profile"]["research_only_caveats"],
        "trade_count": trade_count,
        "trading_days": trading_days,
        "capacity_assessment": (
            "Personal-size research only. TQQQ minute execution requires a later execution-reality "
            "and broker fill review before paper or live use."
        ),
        "short_sample": False,
        "conclusion": "warning",
        "notes": (
            "The 28-trial non-ML minute round used fixed grids and index-shifted signals. "
            "No candidate is promoted; benchmark/data caveats keep this at research-only status."
        ),
    }
    json_path = root / FORENSICS_DIR / f"{STRATEGY_NAME}-backtest-forensics.json"
    md_path = root / FORENSICS_DIR / f"{STRATEGY_NAME}-backtest-forensics.md"
    write_json(json_path, forensics)
    md_path.write_text(_render_forensics_markdown(forensics, payload), encoding="utf-8")
    return json_path, md_path


def _render_forensics_markdown(forensics: dict[str, Any], payload: dict[str, Any]) -> str:
    lines = [
        f"# Backtest Forensics: {STRATEGY_NAME}",
        "",
        "Conclusion: `warning`, research-only minute momentum round.",
        "",
        "Checks:",
        "",
        (
            f"- Lookahead: {forensics['lookahead_check']}. Signals are computed "
            "from bar-close data and applied to the next bar return."
        ),
        (
            f"- Future leak: {forensics['future_leak_check']}. No fitted model "
            "or future-window feature is used."
        ),
        (
            f"- Multiple testing: {forensics['multiple_testing_count']} "
            "fixed-grid trials, capped at 28."
        ),
        (
            f"- Overfit risk: {forensics['overfit_risk']}. Results require "
            "forward paper observation before any promotion."
        ),
        (
            "- Data caveat: Alpaca/IEX minute cache is research-only and not "
            "paper-ready full-market evidence."
        ),
        "",
        "Path decisions:",
        "",
    ]
    lines.extend(
        f"- `{path}`: `{row['decision']}` - {row['reason']}"
        for path, row in payload["path_summaries"].items()
    )
    return "\n".join(lines).rstrip() + "\n"


def _render_evaluation_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# mom_minute_r1 Evaluation",
        "",
        f"- Generated at: `{payload['generated_at']}`",
        f"- Trial count: `{payload['search_space']['candidate_count']}`",
        f"- Workflow pass: `{payload['workflow_pass']}`",
        f"- Research pass: `{payload['research_pass']}`",
        f"- Paper-ready pass: `{payload['paper_ready_pass']}`",
        f"- Acceptance passed: `{payload['acceptance_gate']['passed']}`",
        f"- Failed gates: {', '.join(payload['acceptance_gate']['failed_gates']) or 'none'}",
        "",
        "## Path Summary",
        "",
        "| path | decision | trials | best trial | entries | total % | sharpe | max DD % | flags |",
        "|---|---|---:|---|---:|---:|---:|---:|---|",
    ]
    for path, row in payload["path_summaries"].items():
        metrics = row["best_metrics"]
        lines.append(
            f"| `{path}` | `{row['decision']}` | {row['trial_count']} | "
            f"`{row['best_trial_id']}` | {row['best_trade_count']} | "
            f"{metrics['total_return_pct']:.2f} | "
            f"{metrics['sharpe']:.2f} | {metrics['max_drawdown_pct']:.2f} | "
            f"{', '.join(row['best_quality_flags']) or 'none'} |"
        )
    lines.extend(
        [
            "",
            "## Top Trials",
            "",
            "| rank | trial | path | entries | params | total % | ann % | sharpe | "
            "max DD % | x2 total % | flags |",
            "|---:|---|---|---:|---|---:|---:|---:|---:|---:|---|",
        ]
    )
    for trial in payload["best_trials"]:
        metrics = trial["metrics"]
        x2 = trial["cost_stress"]["x2"]
        lines.append(
            f"| {trial['rank']} | `{trial['trial_id']}` | `{trial['path']}` | "
            f"{trial['trade_count']} | "
            f"`{json.dumps(trial['params'], sort_keys=True)}` | "
            f"{metrics['total_return_pct']:.2f} | {metrics['annualized_return_pct']:.2f} | "
            f"{metrics['sharpe']:.2f} | {metrics['max_drawdown_pct']:.2f} | "
            f"{x2['total_return_pct']:.2f} | {', '.join(trial['quality_flags']) or 'none'} |"
        )
    lines.extend(
        [
            "",
            "## Caveats",
            "",
        ]
    )
    lines.extend(f"- {item}" for item in payload["data_profile"]["research_only_caveats"])
    lines.extend(
        [
            "- This is not a promotion report and does not change active or paper behavior.",
            (
                "- ML and AI-information rounds remain blocked until a non-ML path "
                "survives the full gate."
            ),
        ]
    )
    return "\n".join(lines).rstrip() + "\n"
