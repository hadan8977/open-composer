"""Reuse source engines. No fill, fee, or portfolio simulation lives here."""

from __future__ import annotations

import importlib
import math
import sys
from collections.abc import Callable
from dataclasses import asdict
from pathlib import Path
from typing import Any, Literal

import numpy as np
import pandas as pd

from open_composer.engines.backtest_engine import backtest_frame
from open_composer.lab.accounting import turnover_cost
from open_composer.lab.metrics import session_returns
from open_composer.lab.models import EngineResult
from open_composer.models.strategy_spec import StrategySpec
from open_composer.research.equity_book.backtest import BookConfig, DecideFn, run_book
from open_composer.research.equity_book.panel import PricePanel
from open_composer.research.features.price_hygiene import sanitize_price_matrices
from open_composer.research.iteration_dossier import require_iteration_execution_gate


def spec_engine(
    spec: StrategySpec,
    frame: pd.DataFrame,
    *,
    root: Path,
    run_id: str,
    initial_equity_usd: float = 100_000.0,
    backend: Literal["python_reference", "nautilus_trader"] = "python_reference",
    evaluation_start_index: int = 0,
    session_timezone: str = "America/New_York",
) -> EngineResult:
    """Single-symbol daily/minute adapter; native design gates and fills are unchanged.

    Frame input is offline; no data refresh or provider calls. Nautilus selection is
    strict, without the generic run_backtest function's optional fallback.
    """
    spec = StrategySpec.model_validate(spec.model_dump())
    require_iteration_execution_gate(spec, root, enforce_unbound_design=True)
    if len(spec.universe) != 1 or spec.portfolio.mode != "single_symbol":
        raise ValueError("Use the native portfolio adapter for non-single-symbol policies")
    if spec.timeframe not in ("daily", "1m", "5m", "15m", "30m", "1h", "4h"):
        raise ValueError("Lab session metrics currently support daily or intraday bars")
    if not 0 <= evaluation_start_index < len(frame):
        raise ValueError("Evaluation start must identify an existing bar")
    if not math.isfinite(initial_equity_usd) or initial_equity_usd <= 0:
        raise ValueError("Initial equity must be positive finite USD")
    timestamps = pd.DatetimeIndex(frame["timestamp"])
    if timestamps.has_duplicates or not timestamps.is_monotonic_increasing:
        raise ValueError("Bars need unique increasing timestamps")
    if "data/sip/daily" in str(frame.attrs.get("data_path", spec.data.path or "")):
        raise ValueError(
            "Stock SIP daily input requires the matrix book adapter's hygiene and "
            "split-trigger exclusion, or its admitted source-native consumer"
        )
    if backend == "python_reference":
        artifacts = backtest_frame(
            spec,
            frame,
            root=root,
            start_equity=initial_equity_usd,
            run_id_value=run_id,
            evaluation_start_index=evaluation_start_index,
        )
    elif backend == "nautilus_trader":
        if evaluation_start_index:
            raise ValueError("Native Nautilus adapter has no warmup scoring boundary")
        if spec.position_direction != "long_only":
            raise ValueError("Native Nautilus strategy currently implements the long leg only")
        from open_composer.adapters.execution.nautilus_runtime import run_nautilus_backtest

        artifacts = run_nautilus_backtest(
            spec, frame, root, run_id_value=run_id, start_equity=initial_equity_usd
        )
    else:
        raise ValueError("Unsupported execution backend")
    curve = np.asarray(artifacts.equity_curve, dtype=float)
    scored_index = timestamps[evaluation_start_index:]
    if len(curve) != len(scored_index) + 1:
        raise ValueError("Native equity marks do not match the scored bar calendar")
    if (curve[:-1] <= 0).any() or not np.isfinite(curve).all():
        raise ValueError("Insolvent native curve needs its own return interpretation")
    bar_returns = pd.Series(curve[1:] / curve[:-1] - 1, index=scored_index, name="net")
    daily = (
        bar_returns
        if spec.timeframe == "daily"
        else session_returns(bar_returns, timezone=session_timezone)
    )
    ledger = pd.DataFrame({"equity_usd": curve[1:], "net_bar": bar_returns}, index=scored_index)
    return EngineResult(
        engine=f"{backend}:native_single_symbol",
        initial_equity_usd=artifacts.run.start_equity,
        end_equity_usd=artifacts.run.end_equity,
        native={
            "run": artifacts.run.model_dump(mode="json"),
            "signals": [s.model_dump(mode="json") for s in artifacts.signals],
            "trades": [t.model_dump(mode="json") for t in artifacts.trades],
            "equity_curve": list(artifacts.equity_curve),
            "spec": spec.model_dump(mode="json"),
        },
        ledger=ledger,
        net_returns=daily,
        limitations=list(artifacts.run.assumptions),
        metadata={
            "native_costs": spec.costs.model_dump(),
            "scoring_start": str(scored_index[0]),
            "scoring_end": str(scored_index[-1]),
            "session_timezone": session_timezone if spec.timeframe != "daily" else None,
            "curve_clock": "native marks; initial account equity precedes first scored mark",
        },
    )


def book_engine(
    close: pd.DataFrame,
    open_: pd.DataFrame,
    decide: DecideFn,
    *,
    config: BookConfig,
) -> EngineResult:
    """Native daily book costs/borrow/margin, with required matrix hygiene defaults.

    Any split-like trigger session suppresses a new decision. It does not use the
    subsequent holding return to decide eligibility. Historical source engines must
    instead be adapted explicitly if this hygiene changes their frozen definition.
    """
    if not close.index.equals(open_.index) or not close.columns.equals(open_.columns):
        raise ValueError("Close/open matrices must share the same calendar and symbols")
    if close.empty or close.index.has_duplicates or not close.index.is_monotonic_increasing:
        raise ValueError("Price matrices need unique increasing sessions")
    clean_close, clean_open, hygiene = sanitize_price_matrices(close, open_)
    assert clean_open is not None
    excluded = {b.first_session_after for b in hygiene.breaks if b.kind == "jump"}

    def clean_decide(date, state):
        return None if date in excluded else decide(date, state)

    result = run_book(PricePanel.from_frames(clean_open, clean_close), clean_decide, config)
    native_config = {k: v for k, v in asdict(config).items()
                     if k not in ("cost_fn", "trade_attrs", "trade_funding", "trade_observer")}
    native_config["cost_fn"] = "native flat_cost" if config.cost_fn is None else "custom callable"
    native_config["trade_attrs"] = config.trade_attrs is not None
    native_config["trade_funding"] = config.trade_funding is not None
    native_config["trade_observer"] = config.trade_observer is not None
    return EngineResult(
        engine="equity_book.run_book",
        initial_equity_usd=config.initial_equity,
        end_equity_usd=float(result.daily["equity"].iloc[-1]),
        native={
            "config": native_config,
            "info": result.info,
            "holdings": {str(k): v.to_dict() for k, v in result.holdings.items()},
            "price_hygiene": hygiene.manifest(),
            "excluded_trigger_sessions": sorted(str(x) for x in excluded),
        },
        ledger=result.daily,
        net_returns=result.net,
        metadata={
            "costs": "Native spread/impact/fees/borrow/margin components in ledger",
            "cost_component_units": "fraction of previous close equity",
            "scoring_start": str(result.daily.index[0]),
            "scoring_end": str(result.daily.index[-1]),
        },
        limitations=["Synthetic fixtures validate accounting only"]
        if close.attrs.get("data_source_mode") == "fixture"
        else [],
    )


def screen_modules(root: Path):
    """Load the original script entry points, retaining their own frozen imports."""
    scripts = str(root.resolve() / "scripts")
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    return importlib.import_module("screen_batch"), importlib.import_module("screen_lane")


def screen_engine(
    root: Path,
    candidate: Any,
    *,
    panel: dict[str, Any],
    n_trials: int,
    initial_equity_usd: float,
) -> EngineResult:
    """One screen candidate under its unedited original windows and 10/20bp costs.

    ``panel`` has the native evaluate_candidate keyword arguments. The source's
    contaminated holdout stays contaminated. Anchor PnL is a declared USD scaling
    of its native judged-offset return series, not a forecast or new simulator.
    """
    _, lane = screen_modules(root)
    native = lane.evaluate_candidate(candidate, n_trials=n_trials, include_accounting=True, **panel)
    if native.get("skipped"):
        raise ValueError(native["skip_reason"])
    primary = native.pop("_returns_net10_by_offset")
    stress = native.pop("_returns_net20_by_offset")
    turnover = native.pop("_turnover_by_offset")
    offset = native["judged"]["anchor"]["offset"]
    start = native["per_window"]["anchor"]["actual_start"]
    end = lane.WINDOWS["anchor"][1]
    returns = primary[offset].loc[start:end].copy()
    ledger = pd.DataFrame(
        {f"net10_offset_{key}": values for key, values in primary.items()}
        | {f"net20_offset_{key}": values for key, values in stress.items()}
        | {f"turnover_offset_{key}": values for key, values in turnover.items()}
        | {
            f"cost10_offset_{key}": turnover_cost(values, lane.COST_BPS_PRIMARY)
            for key, values in turnover.items()
        }
        | {
            f"cost20_offset_{key}": turnover_cost(values, lane.COST_BPS_STRESS)
            for key, values in turnover.items()
        }
    )
    return EngineResult(
        engine="screen_lane.evaluate_candidate",
        initial_equity_usd=initial_equity_usd,
        end_equity_usd=initial_equity_usd * float((1 + returns).prod()),
        native=native,
        ledger=ledger,
        net_returns=returns,
        metadata={
            "windows": lane.WINDOWS,
            "contaminated_windows": sorted(lane.CONTAMINATED_WINDOWS),
            "cost_bps_primary": lane.COST_BPS_PRIMARY,
            "cost_bps_stress": lane.COST_BPS_STRESS,
            "anchor_judged_offset": offset,
            "source_n_trials_at_evaluation": n_trials,
        },
        limitations=[
            "Frozen ETF long-only screen assumptions; no universal daily engine claim",
            "Legacy sleeve combination applies new allocation to whole-session returns; "
            "its next-open combination statistics require clock correction. "
            "Use book_engine asset-level targets for new contribution studies.",
            "Source holdout is contaminated and reference-only",
            "Native source DSR retains its evaluation count; summary records cumulative count",
        ],
    )


def screen_variants(
    root: Path,
    batch_name: str,
    *,
    iteration: str,
    panel: dict[str, Any],
    trial_count: Callable[[], int],
    initial_equity_usd: float,
):
    """Reuse the existing batch module/manifest guard and the cumulative lab runner."""
    from open_composer.lab.batch import Variant

    batch, _ = screen_modules(root)
    candidates = batch.candidates_from_module(batch.load_batch_module(batch_name))
    batch.load_manifest_guard(batch.ITERATIONS_DIR / iteration, [c.id for c in candidates])
    problems = batch.calendar_anchor_problems(panel["close"], candidates)
    if problems:
        raise ValueError("; ".join(problems))
    return [
        Variant(
            id=c.id,
            parameters={"screen_batch": batch_name, "source_card": c.source_card},
            evaluate=lambda c=c: screen_engine(
                root,
                c,
                panel=panel,
                n_trials=trial_count(),
                initial_equity_usd=initial_equity_usd,
            ),
        )
        for c in candidates
    ]
