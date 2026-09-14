#!/usr/bin/env python3
"""Step 14: timeframe-agnostic bar-cycle runner (``BarCycleRunner``).

Plan: ``docs/plan-step-14-timeframe-agnostic-bar-cycle-runner-2026-09-11.zh.md``
section 1 (item 3). One runner for every StrategySpec timeframe
(1m/5m/15m/30m/1h/4h/daily) -- no more one-off script per cadence: fixed
steps, ``BarSource`` supplies bars, ``SignalEngine`` decides what to do with
them (``open_composer.execution.bar_source``/``.signal_engine``).

    sync-account (read-only)
      -> fetch bars (ArchiveBarSource or AlpacaBarSource)
      -> engine.compute() [idempotent: a bar already reflected in state is a
         harmless no-op]
      -> write signal log + target weights (unless the engine already did,
         e.g. ModelRankingSignalEngine)
      -> persist engine state
      -> STOP (observation mode only)

**Observation mode only.** This script never authorizes or submits a broker
order -- it refuses to run against anything but a ``manual_signal``/
``broker=none`` spec, and there is no code path here that calls the existing
paper-order-authorization machinery (``open_composer.paper_readiness``,
``oc run paper``, ...) at all. A spec that wants paper_auto execution is out
of scope for this script by construction, not by a runtime flag.

Idempotency is what makes one runner correct for every cadence: the same
``bar_close_ts`` is processed exactly once (tracked in the engine's own
persisted state), so invoking this script for a bar already processed is a
harmless no-op -- daily cron can fire once/day, hourly cron every 30 minutes
during the session, and ``--follow`` polls in a loop, all through this same
code path.

Usage::

    uv run python scripts/run_bar_cycle.py \\
        --spec strategy_specs/drafts/us_reversal_trend_1h_h26.yaml
    uv run python scripts/run_bar_cycle.py --spec <spec.yaml> --as-of 2026-09-11T20:00:00Z
    uv run python scripts/run_bar_cycle.py --spec <spec.yaml> --follow --max-follow-cycles 3
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd
from dotenv import load_dotenv

from open_composer.adapters.execution.router_target_weights import (
    infer_acquisition_tier,
    write_router_execution_artifacts,
)
from open_composer.config import ensure_dir, project_root
from open_composer.execution.bar_source import AlpacaBarSource, ArchiveBarSource, BarSource
from open_composer.execution.signal_engine import (
    ComputeResult,
    EngineState,
    ModelRankingSignalEngine,
    ReversalTrendSignalEngine,
    SignalEngine,
    TargetWeights,
)
from open_composer.models.strategy_spec import StrategySpec, load_strategy_spec
from open_composer.storage import append_jsonl, model_to_record

#: A rolling lookback, not a fixed calendar floor: ReversalTrendSignalEngine
#: recomputes indicators from the *entire* fetched window every call (see
#: its docstring), so a fixed floor (e.g. the Step 13-P evaluation's own
#: "2024-01-02" start) would make this script's own memory/CPU cost grow
#: without bound as real time passes -- exactly the kind of unbounded-growth
#: job this box's 3.9GB RAM cannot absorb (see scripts/run_capped.sh's own
#: docstring). 550 calendar days (~380 trading days, ~2500 1h bars) is
#: comfortably past every indicator's warm-up horizon here (EMA200's slowest
#: decay reaches <1e-6 residual seed weight by ~210 trading days; RSI/ADX/
#: MACD/dwell-cooldown windows are all <=35 bars), so indicator values at
#: any bar this many days after history-start are indistinguishable from
#: what an unbounded lookback would produce -- shortening the window changes
#: nothing about correctness for any bar far enough past its own start.
DEFAULT_HISTORY_LOOKBACK_DAYS = 550

SUPPORTED_PORTFOLIO_MODES = ("model_ranking_portfolio", "event_driven_capacity_book")


class BarCycleError(RuntimeError):
    pass


def resolve_engine(spec_path: Path, spec: StrategySpec) -> SignalEngine:
    mode = spec.portfolio.mode
    if mode == "model_ranking_portfolio":
        return ModelRankingSignalEngine(spec_path=spec_path)
    if mode == "event_driven_capacity_book":
        engine_name = spec.portfolio.event_signal_engine
        if engine_name == "reversal_trend_engine":
            return ReversalTrendSignalEngine()
        raise BarCycleError(f"unknown portfolio.event_signal_engine: {engine_name!r}")
    raise BarCycleError(
        f"run_bar_cycle.py has no SignalEngine for portfolio.mode={mode!r}; supported: "
        + ", ".join(SUPPORTED_PORTFOLIO_MODES)
    )


def resolve_bar_source(data_source: str) -> BarSource:
    if data_source == "archive":
        return ArchiveBarSource()
    if data_source == "alpaca":
        return AlpacaBarSource()
    raise BarCycleError(f"unsupported --data-source {data_source!r}; expected archive|alpaca")


def _require_observation_mode(spec: StrategySpec) -> None:
    if spec.execution.mode != "manual_signal" or spec.execution.broker != "none":
        raise BarCycleError(
            "run_bar_cycle.py is observation-mode only and refuses "
            f"execution.mode={spec.execution.mode!r} execution.broker={spec.execution.broker!r} "
            "-- a paper_auto/broker-enabled spec must use the existing, unchanged order-"
            "authorization path (oc run paper), never this script"
        )


def _state_path(root: Path, strategy_name: str) -> Path:
    return root / "reports" / "execution" / f"{strategy_name}-state.json"


def _target_weights_path(root: Path, strategy_name: str) -> Path:
    return root / "reports" / "execution" / f"{strategy_name}-target-weights.json"


def _signal_log_path(root: Path, strategy_name: str) -> Path:
    return root / "signal_logs" / f"{strategy_name}.jsonl"


def _bar_cycle_log_path(
    root: Path, strategy_name: str, timeframe: str, as_of: pd.Timestamp
) -> Path:
    day = as_of.tz_convert("UTC").strftime("%Y%m%d")
    return root / "reports" / "paper" / "bar_cycle" / f"{strategy_name}-{timeframe}-{day}.json"


def _engine_state_tag(spec: StrategySpec) -> str:
    """The canonical ``EngineState.engine`` tag each SignalEngine sets on
    its own ``new_state`` (see ModelRankingSignalEngine/ReversalTrendSignalEngine),
    used as the fallback tag when no state file exists yet.
    """
    if spec.portfolio.mode == "model_ranking_portfolio":
        return "model_ranking_portfolio"
    return str(spec.portfolio.event_signal_engine or spec.portfolio.mode)


def _load_state(root: Path, strategy_name: str, *, engine_name: str) -> EngineState:
    path = _state_path(root, strategy_name)
    if not path.is_file():
        return EngineState(engine=engine_name)
    try:
        data = _read_json(path)
    except (OSError, ValueError):
        return EngineState(engine=engine_name)
    return EngineState.from_json(data, engine=engine_name)


def _read_json(path: Path) -> dict[str, Any]:
    import json

    return json.loads(path.read_text(encoding="utf-8"))


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    import json
    import tempfile

    ensure_dir(path.parent)
    encoded = json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n"
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        temp_path = Path(handle.name)
        handle.write(encoded)
    temp_path.replace(path)


def _sync_account(oc_cmd: list[str], root: Path) -> dict[str, Any]:
    started = datetime.now(UTC).isoformat()
    result = subprocess.run(  # noqa: S603
        [*oc_cmd, "paper", "sync-account"], cwd=root, text=True, capture_output=True
    )
    return {
        "step": "sync_account",
        "command": [*oc_cmd, "paper", "sync-account"],
        "started_at": started,
        "ended_at": datetime.now(UTC).isoformat(),
        "exit_code": result.returncode,
        "stdout_tail": (result.stdout or "")[-2000:],
        "stderr_tail": (result.stderr or "")[-2000:],
    }


def _previous_target_weights(root: Path, strategy_name: str) -> tuple[dict[str, float], str | None]:
    path = _target_weights_path(root, strategy_name)
    if not path.is_file():
        return {}, None
    try:
        payload = _read_json(path)
    except (OSError, ValueError):
        return {}, None
    rows = payload.get("target_weights") or []
    if not rows:
        return {}, None
    sessions = sorted({str(row["rebalance_session"]) for row in rows})
    latest_session = sessions[-1]
    latest_rows = [row for row in rows if str(row.get("rebalance_session")) == latest_session]
    weights = {str(row["symbol"]): float(row.get("target_weight") or 0.0) for row in latest_rows}
    return weights, latest_session


def _build_target_rows(
    *,
    strategy_name: str,
    weights: dict[str, float],
    previous_weights: dict[str, float],
    rebalance_session: str,
    signal_session: str | None,
) -> list[dict[str, Any]]:
    rebalance_id = f"{strategy_name}:{rebalance_session}"
    all_symbols = sorted(set(weights) | set(previous_weights))
    rows = []
    for symbol in all_symbols:
        target_weight = float(weights.get(symbol, 0.0))
        rows.append(
            {
                "rebalance_id": rebalance_id,
                "rebalance_session": rebalance_session,
                "signal_session": signal_session,
                "time_rule": "next_bar_open",
                "symbol": symbol,
                "target_weight": target_weight,
                "selected": abs(target_weight) > 1e-12,
                "state": "signal",
                "source": "bar_cycle_runner",
            }
        )
    return rows


def _write_target_weights(
    *,
    root: Path,
    spec_path: Path,
    spec: StrategySpec,
    target_weights: TargetWeights,
    bars_panel: pd.DataFrame,
    data_source: str,
    bootstrap: bool,
) -> Path:
    previous_weights, _ = _previous_target_weights(root, spec.name)
    target_rows = _build_target_rows(
        strategy_name=spec.name,
        weights=target_weights.weights,
        previous_weights=previous_weights,
        rebalance_session=target_weights.rebalance_session,
        signal_session=target_weights.signal_session,
    )
    feed = (
        str(bars_panel["feed"].iloc[0])
        if not bars_panel.empty and "feed" in bars_panel.columns
        else (spec.data.feed or "")
    )
    data_profile = {
        "source_mode": "live_fetch" if data_source == "alpaca" else "cache",
        "provider": "alpaca_live_tail" if data_source == "alpaca" else "sip_archive",
        "feed": feed,
        "timeframe": spec.timeframe,
        "bar_count": int(len(bars_panel)),
    }
    acquisition_tier = infer_acquisition_tier(
        data_source=spec.data.source,
        data_profile=data_profile,
        explicit=spec.data_assumptions.acquisition_tier,
        refresh_data=(data_source == "alpaca"),
    )
    mapping_summary = {
        "mapping_mode": "bar_cycle_runner_target_weight_mapping",
        **target_weights.metadata,
        "bootstrap": bootstrap,
        "paper_order_authorization": False,
        "broker_writes": False,
    }
    artifacts = write_router_execution_artifacts(
        root=root,
        spec_path=spec_path,
        spec=spec,
        target_rows=target_rows,
        rebalance_intents=[],
        data_profile=data_profile,
        route_label=None,
        mapping_summary=mapping_summary,
        acquisition_tier=acquisition_tier,
        parity_check={"status": "ok", "blockers": [], "warnings": []},
        target_backend="python_reference",
    )
    return artifacts["router_target_weights"]


def run_one_cycle(
    *,
    spec_path: Path,
    root: Path,
    as_of: pd.Timestamp,
    data_source: str,
    history_lookback_days: int,
    oc_cmd: list[str],
    skip_sync_account: bool = False,
) -> dict[str, Any]:
    """One observation-mode bar cycle for ``spec_path``. Returns the record
    this call appends to ``reports/paper/bar_cycle/<strategy>-<timeframe>-
    <YYYYMMDD>.json``.
    """
    started_at = datetime.now(UTC).isoformat()
    spec = load_strategy_spec(spec_path)
    _require_observation_mode(spec)
    engine = resolve_engine(spec_path, spec)
    bar_source = resolve_bar_source(data_source)

    sync_record = None if skip_sync_account else _sync_account(oc_cmd, root)

    state = _load_state(root, spec.name, engine_name=_engine_state_tag(spec))
    start_ts = as_of - pd.Timedelta(days=history_lookback_days)
    try:
        bars_panel = bar_source.get_bars(
            spec.universe, spec.timeframe, start_ts, as_of, as_of=as_of
        )
    except Exception as exc:  # noqa: BLE001 - always recorded, never silently swallowed
        record = {
            "report_type": "bar_cycle",
            "strategy": spec.name,
            "timeframe": spec.timeframe,
            "started_at": started_at,
            "ended_at": datetime.now(UTC).isoformat(),
            "as_of": as_of.isoformat(),
            "data_source": data_source,
            "status": "failed",
            "error": f"{type(exc).__name__}: {exc}",
            "sync_account": sync_record,
            "paper_order_authorization": False,
            "broker_writes": False,
        }
        _append_bar_cycle_record(root, spec.name, spec.timeframe, as_of, record)
        raise

    result: ComputeResult = engine.compute(bars_panel, spec, state, as_of, root=root)

    target_weights_path: str | None = None
    if result.target_weights is not None and not result.artifacts_written_by_engine:
        path = _write_target_weights(
            root=root,
            spec_path=spec_path,
            spec=spec,
            target_weights=result.target_weights,
            bars_panel=bars_panel,
            data_source=data_source,
            bootstrap=bool(result.target_weights.metadata.get("bootstrap", False)),
        )
        target_weights_path = str(path)
    elif result.artifacts_written_by_engine:
        target_weights_path = (
            result.target_weights.metadata.get("json_path") if result.target_weights else None
        )

    signal_count = 0
    if result.signals:
        append_jsonl(
            _signal_log_path(root, spec.name),
            [model_to_record(signal) for signal in result.signals],
        )
        signal_count = len(result.signals)

    _write_json_atomic(_state_path(root, spec.name), result.new_state.to_json())

    record = {
        "report_type": "bar_cycle",
        "strategy": spec.name,
        "timeframe": spec.timeframe,
        "started_at": started_at,
        "ended_at": datetime.now(UTC).isoformat(),
        "as_of": as_of.isoformat(),
        "data_source": data_source,
        "bar_count": int(len(bars_panel)),
        "latest_bar_close_ts": (
            bars_panel["bar_close_ts"].max().isoformat() if not bars_panel.empty else None
        ),
        "status": "ok",
        "notes": result.notes,
        "signals_logged": signal_count,
        "target_weights_written": target_weights_path is not None
        and not result.artifacts_written_by_engine,
        "artifact_paths": {
            "state": str(_state_path(root, spec.name)),
            "signal_log": str(_signal_log_path(root, spec.name)) if signal_count else None,
            "target_weights": target_weights_path,
        },
        "sync_account": sync_record,
        "paper_order_authorization": False,
        "broker_writes": False,
        "safety_note": (
            "Observation-only bar cycle: never calls oc run paper and never submits broker orders."
        ),
    }
    _append_bar_cycle_record(root, spec.name, spec.timeframe, as_of, record)
    return record


def _append_bar_cycle_record(
    root: Path, strategy_name: str, timeframe: str, as_of: pd.Timestamp, record: dict[str, Any]
) -> None:
    path = _bar_cycle_log_path(root, strategy_name, timeframe, as_of)
    payload: dict[str, Any] = {
        "report_type": "bar_cycle_day",
        "strategy": strategy_name,
        "timeframe": timeframe,
        "date": as_of.strftime("%Y-%m-%d"),
        "records": [],
    }
    if path.is_file():
        try:
            payload = _read_json(path)
        except (OSError, ValueError):
            pass
    payload.setdefault("records", []).append(record)
    _write_json_atomic(path, payload)


def _parse_as_of(value: str | None) -> pd.Timestamp:
    if value is None:
        return pd.Timestamp.now(tz="UTC")
    timestamp = pd.Timestamp(value)
    return timestamp.tz_localize("UTC") if timestamp.tzinfo is None else timestamp.tz_convert("UTC")


def _default_data_source(follow: bool, explicit: str | None) -> str:
    if explicit is not None:
        return explicit
    return "alpaca" if follow else "archive"


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    root = args.root.resolve()
    load_dotenv(root / ".env", override=False)
    spec_path = args.spec if args.spec.is_absolute() else root / args.spec
    oc_cmd = args.oc_cmd.split()
    data_source = _default_data_source(args.follow, args.data_source)

    if not args.follow:
        as_of = _parse_as_of(args.as_of)
        record = run_one_cycle(
            spec_path=spec_path,
            root=root,
            as_of=as_of,
            data_source=data_source,
            history_lookback_days=args.history_lookback_days,
            oc_cmd=oc_cmd,
            skip_sync_account=args.skip_sync_account,
        )
        print(f"bar cycle {record['status']}: notes={record.get('notes')}")
        return 0 if record["status"] == "ok" else 1

    cycles = 0
    while args.max_follow_cycles is None or cycles < args.max_follow_cycles:
        as_of = _parse_as_of(args.as_of)
        record = run_one_cycle(
            spec_path=spec_path,
            root=root,
            as_of=as_of,
            data_source=data_source,
            history_lookback_days=args.history_lookback_days,
            oc_cmd=oc_cmd,
            skip_sync_account=args.skip_sync_account,
        )
        print(f"[{as_of.isoformat()}] bar cycle {record['status']}: notes={record.get('notes')}")
        cycles += 1
        if args.max_follow_cycles is not None and cycles >= args.max_follow_cycles:
            break
        time.sleep(args.poll_seconds)
    return 0


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the timeframe-agnostic observation-only bar cycle."
    )
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--as-of", default=None, help="UTC timestamp (ISO8601); defaults to now.")
    parser.add_argument(
        "--follow", action="store_true", help="Long-lived polling loop (1m cadence)."
    )
    parser.add_argument("--poll-seconds", type=float, default=60.0)
    parser.add_argument(
        "--max-follow-cycles", type=int, default=None, help="Bound --follow (tests/finite runs)."
    )
    parser.add_argument("--root", type=Path, default=project_root())
    parser.add_argument(
        "--data-source",
        choices=["archive", "alpaca"],
        default=None,
        help="Default: archive (or alpaca when --follow, the live tail case).",
    )
    parser.add_argument("--history-lookback-days", type=int, default=DEFAULT_HISTORY_LOOKBACK_DAYS)
    parser.add_argument("--oc-cmd", default="uv run oc")
    parser.add_argument(
        "--skip-sync-account",
        action="store_true",
        help="Skip the read-only `oc paper sync-account` step (tests; no network/credentials).",
    )
    return parser.parse_args(argv)


if __name__ == "__main__":
    sys.exit(main())
