from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd

from open_composer.adapters.data import load_ohlcv_for_spec
from open_composer.adapters.execution.router_target_weights import (
    infer_acquisition_tier,
    write_router_execution_artifacts,
)
from open_composer.config import project_root
from open_composer.engines.signal_engine import required_signal_history_bars, signal_masks
from open_composer.market_calendar import next_us_equity_session
from open_composer.models.strategy_spec import StrategySpec, load_strategy_spec


@dataclass(frozen=True)
class SingleSymbolTargetState:
    signal_session: str
    rebalance_session: str
    target_weight: float
    previous_target_weight: float
    state: str
    requires_order: bool


@dataclass(frozen=True)
class SingleSymbolTargetWeightResult:
    report_path: Path
    json_path: Path
    target_weight_count: int
    rebalance_sessions: int
    nonzero_target_rows: int
    parity_status: str


def build_single_symbol_target_states(
    spec: StrategySpec,
    frame: pd.DataFrame,
    *,
    root: Path | None = None,
) -> list[SingleSymbolTargetState]:
    if spec.portfolio.mode != "single_symbol" or len(spec.universe) != 1:
        raise ValueError("single-symbol target mapping requires one-symbol single_symbol spec")
    entry, exit_ = signal_masks(spec, frame, root=root)
    start_index = required_signal_history_bars(spec) - 1
    target = 0.0
    states: list[SingleSymbolTargetState] = []
    for index in range(start_index, len(frame)):
        entry_now = bool(entry.iloc[index])
        exit_now = bool(exit_.iloc[index])
        if entry_now and exit_now:
            raise ValueError(f"entry and exit are both true at frame index {index}")
        previous = target
        if entry_now:
            target = float(spec.risk.max_position_weight)
        elif exit_now:
            target = 0.0
        signal_session = _session_date(frame.iloc[index]["timestamp"], spec)
        if index + 1 < len(frame):
            rebalance_session = _session_date(frame.iloc[index + 1]["timestamp"], spec)
        else:
            rebalance_session = next_us_equity_session(
                pd.Timestamp(signal_session).date()
            ).isoformat()
        states.append(
            SingleSymbolTargetState(
                signal_session=signal_session,
                rebalance_session=rebalance_session,
                target_weight=target,
                previous_target_weight=previous,
                state="risk_on" if target > 0 else "cash",
                requires_order=abs(target - previous) > 1e-12,
            )
        )
    return states


def latest_single_symbol_target_state(
    spec: StrategySpec,
    frame: pd.DataFrame,
    *,
    root: Path | None = None,
) -> SingleSymbolTargetState:
    states = build_single_symbol_target_states(spec, frame, root=root)
    if not states:
        raise ValueError("single-symbol target mapping produced no eligible state")
    return states[-1]


def run_single_symbol_target_weight_mapping(
    spec_path: Path,
    root: Path | None = None,
    *,
    data_source: str | None = None,
    refresh_data: bool = False,
) -> SingleSymbolTargetWeightResult:
    base = root or project_root()
    spec = load_strategy_spec(spec_path)
    frame = load_ohlcv_for_spec(spec, base, refresh=refresh_data)
    states = build_single_symbol_target_states(spec, frame, root=base)
    target_rows: list[dict[str, object]] = []
    intents: list[dict[str, object]] = []
    for state in states:
        rebalance_id = f"{spec.name}:{state.rebalance_session}"
        target_rows.append(
            {
                "rebalance_id": rebalance_id,
                "rebalance_session": state.rebalance_session,
                "signal_session": state.signal_session,
                "time_rule": "next_regular_session_open",
                "symbol": spec.primary_symbol,
                "target_weight": state.target_weight,
                "state": state.state,
                "position_weight_enforcement": spec.portfolio.position_weight_enforcement,
                "source": "single_symbol_python_reference",
            }
        )
        delta = state.target_weight - state.previous_target_weight
        intents.append(
            {
                "rebalance_id": rebalance_id,
                "rebalance_session": state.rebalance_session,
                "time_rule": "next_regular_session_open",
                "symbol": spec.primary_symbol,
                "from_weight": state.previous_target_weight,
                "to_weight": state.target_weight,
                "delta_weight": delta,
                "side": "buy" if delta > 0 else "sell" if delta < 0 else "hold",
                "intent_type": "set_entry_or_exit_target_weight",
                "requires_order": state.requires_order,
            }
        )
    data_profile = _data_profile(frame, spec)
    parity = _parity_check(spec, states)
    artifacts = write_router_execution_artifacts(
        root=base,
        spec_path=spec_path,
        spec=spec,
        target_rows=target_rows,
        rebalance_intents=intents,
        data_profile=data_profile,
        route_label=None,
        mapping_summary={
            "mapping_mode": "single_symbol_target_weight_mapping",
            "position_weight_enforcement": spec.portfolio.position_weight_enforcement,
        },
        acquisition_tier=infer_acquisition_tier(
            data_source=data_source or spec.data.source,
            data_profile=data_profile,
            explicit=spec.data_assumptions.acquisition_tier,
            refresh_data=refresh_data,
        ),
        parity_check=parity,
    )
    json_path = artifacts["router_target_weights"]
    report_path = json_path.with_suffix(".md")
    _write_report(report_path, spec, states, parity, json_path)
    return SingleSymbolTargetWeightResult(
        report_path=report_path,
        json_path=json_path,
        target_weight_count=len(target_rows),
        rebalance_sessions=len({row["rebalance_session"] for row in target_rows}),
        nonzero_target_rows=sum(float(row["target_weight"]) > 0 for row in target_rows),
        parity_status=str(parity["status"]),
    )


def _session_date(value: Any, spec: StrategySpec) -> str:
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        timestamp = timestamp.tz_localize("UTC")
    return timestamp.tz_convert(ZoneInfo(spec.data_assumptions.timezone)).date().isoformat()


def _data_profile(frame: pd.DataFrame, spec: StrategySpec) -> dict[str, object]:
    return {
        "source_mode": str(frame.attrs.get("data_source_mode") or "cache"),
        "provider": str(frame.attrs.get("data_source_provider") or spec.data.source),
        "feed": str(spec.data.feed or ""),
        "rows": len(frame),
        "first_timestamp": pd.Timestamp(frame.iloc[0]["timestamp"]).isoformat(),
        "last_timestamp": pd.Timestamp(frame.iloc[-1]["timestamp"]).isoformat(),
    }


def _parity_check(
    spec: StrategySpec,
    states: list[SingleSymbolTargetState],
) -> dict[str, object]:
    blockers: list[str] = []
    allowed = {0.0, float(spec.risk.max_position_weight)}
    invalid = sorted(
        {state.target_weight for state in states if state.target_weight not in allowed}
    )
    if invalid:
        blockers.append(f"unexpected target weights: {invalid}")
    if spec.portfolio.position_weight_enforcement != "entry_only":
        blockers.append("continuous single-symbol target enforcement is not implemented")
    return {
        "status": "blocked" if blockers else "pass",
        "blockers": blockers,
        "warnings": [
            "Target rows express entry/exit state; natural weight drift is not a daily rebalance."
        ],
    }


def _write_report(
    path: Path,
    spec: StrategySpec,
    states: list[SingleSymbolTargetState],
    parity: dict[str, object],
    json_path: Path,
) -> None:
    transitions = sum(state.requires_order for state in states)
    path.write_text(
        "\n".join(
            [
                f"# Single-Symbol Target Weights: {spec.name}",
                "",
                f"- JSON: `{json_path}`",
                f"- Status: `{parity['status']}`",
                f"- Sessions: `{len(states)}`",
                f"- State transitions: `{transitions}`",
                f"- Position enforcement: `{spec.portfolio.position_weight_enforcement}`",
                "- Broker writes: `false`",
                "",
                (
                    "Targets describe entry/exit state. Entry-only sizing permits natural "
                    "drift until the next state transition."
                ),
                "",
            ]
        ),
        encoding="utf-8",
    )
