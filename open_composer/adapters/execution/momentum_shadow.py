from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from open_composer.adapters.execution.router_target_weights import (
    write_router_execution_artifacts,
)
from open_composer.engines.signal_engine import build_signal
from open_composer.models.strategy_spec import load_strategy_spec
from open_composer.research.mom_minute_round import (
    _align_signal_and_trade,
    _load_research_frame,
)
from open_composer.research.momentum_signal_router import (
    momentum_route_from_label,
    momentum_target_position,
)
from open_composer.storage import model_to_record, write_json
from open_composer.strategy_versions import strategy_content_hash


@dataclass(frozen=True)
class MomentumShadowResult:
    target_weights_path: Path
    observation_path: Path
    signal_log_path: Path
    review_json_path: Path
    review_markdown_path: Path
    status: str
    latest_target_weight: float
    signal_count: int


def run_momentum_shadow_observation(
    spec_path: Path,
    root: Path,
    *,
    as_of: datetime | None = None,
) -> MomentumShadowResult:
    spec = load_strategy_spec(spec_path)
    if spec.portfolio.mode != "momentum_signal_router":
        raise ValueError("shadow observation requires portfolio.mode=momentum_signal_router")
    if spec.lifecycle != "draft" or spec.execution.mode != "manual_signal":
        raise ValueError("shadow observation requires draft manual_signal strategy")
    if spec.execution.broker != "none":
        raise ValueError("shadow observation forbids broker access")
    if not spec.portfolio.selected_route_label:
        raise ValueError("momentum shadow route label is required")
    route = momentum_route_from_label(spec.portfolio.selected_route_label)
    if route.timeframe != spec.timeframe:
        raise ValueError("momentum route timeframe does not match StrategySpec")

    signal_frame = _load_research_frame(root, route.signal_symbol, route.timeframe)
    target_frame = _load_research_frame(root, route.target_symbol, route.timeframe)
    if signal_frame is None or target_frame is None:
        raise ValueError("momentum shadow requires strict materialized signal and target data")
    _require_expected_hashes(spec, signal_frame, target_frame, route)
    alignment = _timestamp_alignment(signal_frame, target_frame)
    aligned = _align_signal_and_trade(signal_frame, target_frame)
    position = momentum_target_position(
        aligned,
        lookback_bars=route.lookback_bars,
        atr_filter_multiplier=route.atr_filter_multiplier,
    )
    target = position * route.target_weight
    spec_hash = strategy_content_hash(spec)
    target_rows, intents, signals = _build_rows(
        spec=spec,
        route=route,
        frame=aligned,
        target=target,
        spec_hash=spec_hash,
    )
    latest_effective = pd.to_datetime(target_rows[-1]["effective_timestamp"], utc=True)
    now = pd.Timestamp(as_of or datetime.now(UTC))
    if now.tzinfo is None:
        now = now.tz_localize("UTC")
    else:
        now = now.tz_convert("UTC")
    age_hours = max((now - latest_effective).total_seconds() / 3600, 0.0)
    stale = age_hours > 24
    parity = {
        "status": "blocked" if stale else "ok",
        "blockers": [f"latest_effective_bar_stale_hours={age_hours:.2f}"] if stale else [],
        "warnings": ["alpaca_iex_research_only", *alignment["warnings"]],
        "position_rows": len(target_rows),
        "research_position_parity": True,
    }
    artifacts = write_router_execution_artifacts(
        root=root,
        spec_path=spec_path,
        spec=spec,
        target_rows=target_rows,
        rebalance_intents=intents,
        data_profile={
            "source_mode": "strict_research_materialization",
            "feed": spec.data.feed,
            "signal_symbol": route.signal_symbol,
            "target_symbol": route.target_symbol,
            "signal_sha256": str(signal_frame["source_sha256"].iloc[0]),
            "target_sha256": str(target_frame["source_sha256"].iloc[0]),
            "latest_effective_timestamp": latest_effective.isoformat(),
            "age_hours": round(age_hours, 4),
            "timestamp_alignment": alignment,
        },
        route_label=route.label,
        mapping_summary={
            "signal_count": len(signals),
            "paper_order_authorization": False,
            "broker_writes": False,
            "selected_trial_id": "mom_minute_r2_p1_003",
        },
        acquisition_tier="research_cross_check",
        parity_check=parity,
    )
    signal_log_path = root / "signal_logs" / f"shadow-{spec.name}.jsonl"
    signal_log_path.parent.mkdir(parents=True, exist_ok=True)
    signal_log_path.write_text(
        "".join(json.dumps(model_to_record(signal), sort_keys=True) + "\n" for signal in signals),
        encoding="utf-8",
    )
    review_dir = root / "reports" / "shadow" / spec.name
    review_dir.mkdir(parents=True, exist_ok=True)
    review_json_path = review_dir / "latest-review-card.json"
    review_markdown_path = review_dir / "latest-review-card.md"
    review = _review_payload(
        spec=spec,
        route=route,
        latest_row=target_rows[-1],
        previous_weight=float(target_rows[-2]["target_weight"]) if len(target_rows) > 1 else 0.0,
        status="blocked" if stale else "observation_only",
        blockers=parity["blockers"],
        spec_hash=spec_hash,
    )
    write_json(review_json_path, review)
    review_markdown_path.write_text(_render_review(review), encoding="utf-8")
    return MomentumShadowResult(
        target_weights_path=artifacts["router_target_weights"],
        observation_path=artifacts["router_execution_observation"],
        signal_log_path=signal_log_path,
        review_json_path=review_json_path,
        review_markdown_path=review_markdown_path,
        status=str(review["execution_substate"]),
        latest_target_weight=float(target_rows[-1]["target_weight"]),
        signal_count=len(signals),
    )


def _build_rows(*, spec, route, frame, target, spec_hash):
    target_rows: list[dict[str, object]] = []
    intents: list[dict[str, object]] = []
    signals = []
    previous = 0.0
    for index, weight in enumerate(target.astype(float)):
        if pd.isna(frame.iloc[index]["execution_open"]):
            continue
        decision_timestamp = pd.Timestamp(frame.iloc[index]["timestamp"])
        effective_timestamp = pd.Timestamp(frame.iloc[index]["execution_timestamp"])
        current = float(weight)
        changed = abs(current - previous) > 1e-12
        rebalance_id = f"{spec.name}:{effective_timestamp.isoformat()}"
        target_rows.append(
            {
                "rebalance_id": rebalance_id,
                "rebalance_session": effective_timestamp.isoformat(),
                "signal_session": decision_timestamp.isoformat(),
                "effective_timestamp": effective_timestamp.isoformat(),
                "time_rule": "next_aligned_30m_open",
                "symbol": route.target_symbol,
                "target_weight": current,
                "signal_symbol": route.signal_symbol,
                "decision_price": float(frame.iloc[index]["signal_close"]),
                "expected_execution_open": float(frame.iloc[index]["execution_open"]),
                "source": "momentum_shadow_reference",
            }
        )
        if changed:
            delta = current - previous
            action = "entry" if delta > 0 else "exit"
            signal = build_signal(
                spec,
                run_id=f"shadow-{spec.name}",
                timestamp=decision_timestamp.to_pydatetime(),
                action=action,
                source="shadow_observation",
                price=float(frame.iloc[index]["signal_close"]),
                spec_hash=spec_hash,
                symbol=route.target_symbol,
                target_weight=current,
                conditions=[
                    f"signal_symbol={route.signal_symbol}",
                    f"decision_timestamp={decision_timestamp.isoformat()}",
                    f"effective_timestamp={effective_timestamp.isoformat()}",
                    f"lookback_bars={route.lookback_bars}",
                    f"atr_filter_multiplier={route.atr_filter_multiplier}",
                ],
            ).model_copy(update={"created_at": decision_timestamp.to_pydatetime()})
            signals.append(signal)
            intents.append(
                {
                    "rebalance_id": rebalance_id,
                    "rebalance_session": effective_timestamp.isoformat(),
                    "time_rule": "next_aligned_30m_open",
                    "symbol": route.target_symbol,
                    "from_weight": previous,
                    "to_weight": current,
                    "delta_weight": delta,
                    "side": "buy" if delta > 0 else "sell",
                    "intent_type": "shadow_set_target_weight",
                    "requires_order": True,
                    "signal_id": signal.id,
                    "broker_writes": False,
                }
            )
        previous = current
    if not target_rows:
        raise ValueError("momentum shadow produced no target rows")
    return target_rows, intents, signals


def _require_expected_hashes(spec, signal_frame, target_frame, route) -> None:
    design = spec.notes.research_design
    expected = design.get("source_hashes", {}) if isinstance(design, dict) else {}
    actual = {
        route.signal_symbol: str(signal_frame["source_sha256"].iloc[0]),
        route.target_symbol: str(target_frame["source_sha256"].iloc[0]),
    }
    for symbol, actual_hash in actual.items():
        if expected.get(symbol) != actual_hash:
            raise ValueError(f"frozen source hash mismatch for {symbol}")


def _timestamp_alignment(signal_frame, target_frame) -> dict[str, Any]:
    signal_ts = pd.DatetimeIndex(pd.to_datetime(signal_frame["timestamp"], utc=True))
    target_ts = pd.DatetimeIndex(pd.to_datetime(target_frame["timestamp"], utc=True))
    common = signal_ts.intersection(target_ts)
    signal_coverage = len(common) / max(len(signal_ts), 1)
    target_coverage = len(common) / max(len(target_ts), 1)
    if signal_ts.max() != target_ts.max():
        raise ValueError("latest QQQ/TQQQ timestamps are not aligned")
    if min(signal_coverage, target_coverage) < 0.95:
        raise ValueError(
            "QQQ/TQQQ common timestamp coverage below 95%: "
            f"signal={signal_coverage:.4f} target={target_coverage:.4f}"
        )
    warnings: list[str] = []
    if not signal_ts.equals(target_ts):
        warnings.append(
            f"partial_history_alignment:signal={signal_coverage:.4f},target={target_coverage:.4f}"
        )
    return {
        "status": "warning" if warnings else "ok",
        "common_rows": len(common),
        "signal_rows": len(signal_ts),
        "target_rows": len(target_ts),
        "signal_coverage": round(signal_coverage, 6),
        "target_coverage": round(target_coverage, 6),
        "latest_timestamp": signal_ts.max().isoformat(),
        "warnings": warnings,
    }


def _review_payload(*, spec, route, latest_row, previous_weight, status, blockers, spec_hash):
    return {
        "strategy_name": spec.name,
        "selected_trial_id": "mom_minute_r2_p1_003",
        "spec_hash": spec_hash,
        "execution_substate": status,
        "signal_symbol": route.signal_symbol,
        "target_symbol": route.target_symbol,
        "signal_timestamp": latest_row["signal_session"],
        "effective_timestamp": latest_row["effective_timestamp"],
        "target_weight": latest_row["target_weight"],
        "previous_target_weight": previous_weight,
        "delta_weight": float(latest_row["target_weight"]) - previous_weight,
        "data_tier": "research_only_alpaca_iex",
        "selection_used_lockbox": False,
        "paper_order_authorization": False,
        "broker_writes": False,
        "blockers": blockers,
        "safety_note": "Observation-only. No broker client, account sync, or order submission.",
    }


def _render_review(review: dict[str, Any]) -> str:
    return (
        f"# Shadow Review: {review['strategy_name']}\n\n"
        f"- Status: `{review['execution_substate']}`\n"
        f"- Signal: `{review['signal_symbol']}` at `{review['signal_timestamp']}`\n"
        f"- Target: `{review['target_symbol']}` weight `{review['target_weight']}` "
        f"effective `{review['effective_timestamp']}`\n"
        f"- Previous weight: `{review['previous_target_weight']}`\n"
        "- Paper order authorization: `false`\n"
        "- Broker writes: `false`\n"
        f"- Blockers: `{', '.join(review['blockers']) or 'none'}`\n"
    )
