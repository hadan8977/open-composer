"""Execution-policy generator and comparison helper.

The execution-reality-reviewer skill compares at least two execution alternatives
(per roadmap design principle #3). This module provides deterministic scaffolding
for that comparison: given a StrategySpec, it produces a candidate set of
execution policies and writes the `execution_policy` and `execution_reality_report`
artifacts that the harness verifier expects.

This module does not call brokers, fetch market data, or run backtests. It writes
draft artifacts that the reviewer (human or skill-driven agent) refines with
source-card-backed broker support and stress evidence.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from open_composer.config import project_root
from open_composer.models.strategy_spec import StrategySpec, load_strategy_spec

# ---------------------------------------------------------------------------
# Candidate execution alternatives
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ExecutionAlternative:
    """One execution method alternative considered by the reviewer."""

    order_style: str
    time_in_force: str
    description: str
    price_protection: str
    fill_certainty: str  # high | medium | low
    slippage_risk: str  # low | medium | high
    when_to_prefer: str


DEFAULT_ALTERNATIVES: list[ExecutionAlternative] = [
    ExecutionAlternative(
        order_style="day_market",
        time_in_force="day",
        description="Immediate market order during regular session at first available price.",
        price_protection="none",
        fill_certainty="high",
        slippage_risk="medium",
        when_to_prefer=("Highest liquidity, willing to accept opening volatility and spread."),
    ),
    ExecutionAlternative(
        order_style="opg_limit",
        time_in_force="opg",
        description="Limit-on-open routed to exchange opening auction.",
        price_protection="limit_price",
        fill_certainty="medium",
        slippage_risk="low",
        when_to_prefer=(
            "Price discovery via opening auction; avoids paying spread for first prints."
        ),
    ),
    ExecutionAlternative(
        order_style="loo_limit",
        time_in_force="opg",
        description="Limit-on-open with explicit limit offset; cancel if not filled.",
        price_protection="limit_offset_bps",
        fill_certainty="low",
        slippage_risk="low",
        when_to_prefer=("Strong price protection requirement; missed fill is acceptable."),
    ),
    ExecutionAlternative(
        order_style="delayed_open_5m",
        time_in_force="day",
        description="Wait 5 minutes after open before submitting market order.",
        price_protection="gap_filter",
        fill_certainty="high",
        slippage_risk="low",
        when_to_prefer=("Reduces opening-auction volatility; loses opening-momentum signal."),
    ),
    ExecutionAlternative(
        order_style="twap",
        time_in_force="day",
        description="Time-weighted average over a 5-30 minute window after open.",
        price_protection="participation_cap",
        fill_certainty="high",
        slippage_risk="low",
        when_to_prefer=("Large orders relative to ADV; controls market impact."),
    ),
]


# ---------------------------------------------------------------------------
# Stress scenarios
# ---------------------------------------------------------------------------


def default_slippage_scenarios() -> list[dict[str, float | str]]:
    """Standard slippage stress test set (low/medium/high)."""
    return [
        {"name": "low", "slippage_bps": 5.0, "open_gap_pct": 0.2},
        {"name": "medium", "slippage_bps": 15.0, "open_gap_pct": 0.8},
        {"name": "high", "slippage_bps": 35.0, "open_gap_pct": 2.5},
    ]


def default_tca_plan() -> dict[str, object]:
    """Reference-price comparison set written into every execution_policy."""
    return {
        "enabled": True,
        "reference_prices": ["decision_price", "official_open", "arrival_price"],
        "record_submitted_at": True,
        "record_fill_price": True,
        "record_slippage_vs_reference": True,
        "review_frequency": "weekly",
    }


# ---------------------------------------------------------------------------
# Recommendation logic
# ---------------------------------------------------------------------------


@dataclass
class RecommendationContext:
    is_leveraged_etf: bool = False
    is_daily_open: bool = False
    is_paper_auto: bool = False
    universe_symbols: list[str] = field(default_factory=list)


LEVERAGED_ETF_SYMBOLS = {
    "TQQQ",
    "SQQQ",
    "UPRO",
    "SPXL",
    "SPXS",
    "SOXL",
    "SOXS",
    "TECL",
    "TECS",
    "LABU",
    "LABD",
    "NUGT",
    "DUST",
    "JNUG",
    "JDST",
    "FAS",
    "FAZ",
    "ERX",
    "ERY",
}


def detect_context(spec: StrategySpec) -> RecommendationContext:
    universe = list(spec.universe)
    has_lev = any(sym.upper() in LEVERAGED_ETF_SYMBOLS for sym in universe)
    is_daily = spec.timeframe == "daily" and spec.execution.fill_assumption == "next_bar_open"
    is_paper = spec.execution.mode == "paper_auto"
    return RecommendationContext(
        is_leveraged_etf=has_lev,
        is_daily_open=is_daily,
        is_paper_auto=is_paper,
        universe_symbols=universe,
    )


def recommend_alternative(context: RecommendationContext) -> ExecutionAlternative:
    """Pick a recommended execution alternative based on detected risk context.

    Leveraged ETFs + daily open: LOO limit (price protection + cancel on gap).
    Daily open without leveraged ETF: OPG limit.
    Otherwise: day_market.
    """
    if context.is_leveraged_etf and context.is_daily_open:
        return next(a for a in DEFAULT_ALTERNATIVES if a.order_style == "loo_limit")
    if context.is_daily_open:
        return next(a for a in DEFAULT_ALTERNATIVES if a.order_style == "opg_limit")
    return next(a for a in DEFAULT_ALTERNATIVES if a.order_style == "day_market")


# ---------------------------------------------------------------------------
# Artifact generation
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ExecutionPolicyArtifacts:
    policy_path: Path
    reality_path: Path
    markdown_path: Path
    recommended_order_style: str
    alternatives: list[str]


def generate_execution_policy_artifacts(
    spec_path: Path,
    root: Path | None = None,
    *,
    overwrite: bool = False,
    source_card_ids: list[str] | None = None,
) -> ExecutionPolicyArtifacts:
    """Generate execution_policy + execution_reality_report draft artifacts.

    The artifacts conform to the schemas in `harness/artifact_contracts.yaml` so
    that `oc harness verify` recognises them. Source card IDs must be provided
    by the source-researcher skill; this generator emits placeholders only when
    none are passed, and source-researcher remains the gate for broker claims.
    """
    base = root or project_root()
    spec = load_strategy_spec(spec_path)
    context = detect_context(spec)
    recommended = _recommended_for_spec(spec, context)
    alternatives = (
        list(spec.execution_policy.alternatives_compared)
        if spec.execution_policy is not None
        else [
            a.order_style for a in DEFAULT_ALTERNATIVES if a.order_style != recommended.order_style
        ][:2]
    )

    policy_id = (
        spec.execution_policy.policy_id
        if spec.execution_policy is not None
        else f"{recommended.order_style}_{spec.name}_v1"
    )
    today = _dt.date.today().isoformat()
    if spec.execution_policy is not None:
        policy_payload = _inline_policy_payload(
            spec,
            recommended,
            generated_at=today,
            requested_source_card_ids=source_card_ids,
        )
        reality_payload = _inline_reality_payload(
            spec,
            recommended,
            generated_at=today,
        )
    else:
        policy_payload = {
            "strategy_name": spec.name,
            "policy_id": policy_id,
            "generated_at": today,
            "order_style": recommended.order_style,
            "time_in_force": recommended.time_in_force,
            "price_protection": _price_protection_payload(recommended, context),
            "gap_filter": _gap_filter_payload(context),
            "spread_filter": _spread_filter_payload(),
            "participation_cap": _participation_cap_payload(context),
            "fallback_behavior": _fallback_behavior_payload(),
            "tca_plan": default_tca_plan(),
            "source_card_ids": list(source_card_ids or []),
            "alternatives_compared": [recommended.order_style, *alternatives],
            "naked_market_justification": _naked_market_justification(recommended, context),
            "alternatives_detail": [asdict(a) for a in DEFAULT_ALTERNATIVES],
            "recommendation_rationale": _rationale(recommended, context),
        }
        reality_payload = {
            "strategy_name": spec.name,
            "policy_id": policy_id,
            "generated_at": today,
            "slippage_scenarios": default_slippage_scenarios(),
            "gap_stress": _gap_stress_payload(context),
            "capacity_assessment": _capacity_assessment_payload(spec),
            "tca_reference_prices": default_tca_plan()["reference_prices"],
            "fill_model": _fill_model_for(recommended),
        }

    policy_path = base / "reports" / "harness" / "execution" / f"{spec.name}-execution-policy.json"
    reality_path = (
        base / "reports" / "harness" / "execution" / f"{spec.name}-execution-reality.json"
    )
    md_path = base / "reports" / "harness" / "execution" / f"{spec.name}-execution-reality.md"
    policy_path.parent.mkdir(parents=True, exist_ok=True)

    for path, payload in [(policy_path, policy_payload), (reality_path, reality_payload)]:
        if path.exists() and not overwrite:
            continue
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False))

    if not md_path.exists() or overwrite:
        md_path.write_text(_render_markdown(spec, recommended, context, alternatives))

    if context.is_leveraged_etf:
        _write_leveraged_etf_artifacts(spec, base, context, overwrite=overwrite)

    return ExecutionPolicyArtifacts(
        policy_path=policy_path,
        reality_path=reality_path,
        markdown_path=md_path,
        recommended_order_style=recommended.order_style,
        alternatives=alternatives,
    )


def _recommended_for_spec(
    spec: StrategySpec,
    context: RecommendationContext,
) -> ExecutionAlternative:
    if spec.execution_policy is None:
        return recommend_alternative(context)
    style = spec.execution_policy.order_style
    match = next((item for item in DEFAULT_ALTERNATIVES if item.order_style == style), None)
    if match is not None:
        return ExecutionAlternative(
            order_style=style,
            time_in_force=spec.execution_policy.time_in_force,
            description=match.description,
            price_protection=match.price_protection,
            fill_certainty=match.fill_certainty,
            slippage_risk=match.slippage_risk,
            when_to_prefer=match.when_to_prefer,
        )
    return ExecutionAlternative(
        order_style=style,
        time_in_force=spec.execution_policy.time_in_force,
        description="Explicit StrategySpec execution policy.",
        price_protection="as_declared_in_strategy_spec",
        fill_certainty="medium",
        slippage_risk="medium",
        when_to_prefer="When the frozen StrategySpec contract selects this method.",
    )


def _inline_policy_payload(
    spec: StrategySpec,
    recommended: ExecutionAlternative,
    *,
    generated_at: str,
    requested_source_card_ids: list[str] | None,
) -> dict[str, object]:
    policy = spec.execution_policy
    if policy is None:
        raise AssertionError("inline execution policy is missing")
    inline_source_ids = list(policy.source_card_ids)
    if requested_source_card_ids is not None and list(requested_source_card_ids) != (
        inline_source_ids
    ):
        raise ValueError(
            "source_card_ids must match the inline StrategySpec execution_policy exactly"
        )
    protection = policy.price_protection.model_dump(mode="json")
    fallback = policy.fallback_behavior.model_dump(mode="json")
    tca = policy.tca.model_dump(mode="json")
    canonical = policy.model_dump(mode="json")
    canonical_hash = hashlib.sha256(
        json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return {
        "strategy_name": spec.name,
        "policy_id": policy.policy_id,
        "generated_at": generated_at,
        "generated_from_inline_strategy_spec": True,
        "inline_policy_sha256": canonical_hash,
        "order_style": policy.order_style,
        "time_in_force": policy.time_in_force,
        "price_protection": {
            "type": "none" if all(value is None for value in protection.values()) else "limit",
            **protection,
        },
        "gap_filter": {
            "enabled": protection["max_open_gap_pct"] is not None,
            "max_open_gap_pct": protection["max_open_gap_pct"],
            "action_on_exceed": fallback["if_gap_exceeds_limit"],
        },
        "spread_filter": {
            "enabled": protection["max_spread_bps"] is not None,
            "max_spread_bps": protection["max_spread_bps"],
            "action_on_exceed": fallback["if_spread_exceeds_limit"],
        },
        "participation_cap": policy.participation_cap.model_dump(mode="json"),
        "fallback_behavior": fallback,
        "tca_plan": {
            "enabled": tca["enabled"],
            "reference_prices": tca["compare_to"],
            "record_submitted_at": tca["record_submitted_at"],
            "record_fill_price": tca["record_fill_price"],
            "record_slippage_vs_reference": bool(tca["record_fill_price"] and tca["compare_to"]),
            "review_frequency": tca["review_frequency"],
        },
        "source_card_ids": inline_source_ids,
        "alternatives_compared": list(policy.alternatives_compared),
        "naked_market_justification": policy.naked_market_justification,
        "alternatives_detail": [asdict(item) for item in DEFAULT_ALTERNATIVES],
        "recommendation_rationale": (
            "Generated from the frozen inline StrategySpec execution_policy; "
            + _rationale(recommended, detect_context(spec))
        ),
    }


def _inline_reality_payload(
    spec: StrategySpec,
    recommended: ExecutionAlternative,
    *,
    generated_at: str,
) -> dict[str, object]:
    policy = spec.execution_policy
    if policy is None:
        raise AssertionError("inline execution policy is missing")
    scenarios = (
        [item.model_dump(mode="json") for item in spec.reality_model.stress_scenarios]
        if spec.reality_model is not None and spec.reality_model.stress_scenarios
        else default_slippage_scenarios()
    )
    protection = policy.price_protection
    max_gap = protection.max_open_gap_pct
    return {
        "strategy_name": spec.name,
        "policy_id": policy.policy_id,
        "generated_at": generated_at,
        "generated_from_inline_strategy_spec": True,
        "slippage_scenarios": scenarios,
        "gap_stress": {
            "max_adverse_gap_pct": max_gap,
            "fill_model_gap_handling": (
                spec.reality_model.fill_model
                if spec.reality_model is not None
                else _fill_model_for(recommended)
            ),
            "recommended_gap_filter": (
                f"{policy.fallback_behavior.if_gap_exceeds_limit} when abs(gap_pct) > {max_gap}"
                if max_gap is not None
                else "no frozen gap threshold"
            ),
            "scenarios": scenarios,
        },
        "capacity_assessment": _capacity_assessment_payload(spec),
        "tca_reference_prices": list(policy.tca.compare_to),
        "fill_model": (
            spec.reality_model.fill_model
            if spec.reality_model is not None
            else _fill_model_for(recommended)
        ),
    }


def _write_leveraged_etf_artifacts(
    spec: StrategySpec,
    base: Path,
    context: RecommendationContext,
    *,
    overwrite: bool,
) -> None:
    """Emit gap_stress_report.json and leveraged_etf_risk_note.md for leveraged ETF specs."""
    exec_dir = base / "reports" / "harness" / "execution"
    exec_dir.mkdir(parents=True, exist_ok=True)

    gap_path = exec_dir / f"{spec.name}-gap-stress.json"
    if overwrite or not gap_path.exists():
        gap_payload = {
            "strategy_name": spec.name,
            "scenarios": default_slippage_scenarios(),
            "max_adverse_gap_pct": 5.0,
            "fill_model_gap_handling": (
                "next_bar_open assumption fills at official open price; a "
                ">2.5% adverse gap is treated as an execution failure."
            ),
            "recommended_gap_filter": "skip trade if abs(open_gap_pct) > 2.5",
            "leveraged_symbols": [
                s for s in context.universe_symbols if s in LEVERAGED_ETF_SYMBOLS
            ],
        }
        gap_path.write_text(json.dumps(gap_payload, indent=2, ensure_ascii=False))

    note_path = exec_dir / f"{spec.name}-leveraged-etf-risk.md"
    if overwrite or not note_path.exists():
        levs = [s for s in context.universe_symbols if s in LEVERAGED_ETF_SYMBOLS]
        note_path.write_text(
            "\n".join(
                [
                    f"# Leveraged ETF Risk Note — {spec.name}",
                    f"\nGenerated: {_dt.date.today().isoformat()}",
                    "",
                    "## Instruments",
                    *[f"- {s}" for s in levs],
                    "",
                    "## Path-Dependency",
                    (
                        "Daily-rebalanced leveraged ETFs compound the underlying's "
                        "daily returns. Multi-day holding periods diverge from the "
                        "advertised leverage factor in volatile regimes — this is "
                        "rebalance decay, not tracking error."
                    ),
                    "",
                    "## Gap Risk",
                    (
                        "Opening gaps are amplified by the leverage factor. A 2% "
                        "underlying gap maps to ~6% on a 3× ETF. The execution "
                        "policy must include a gap filter; see gap_stress_report."
                    ),
                    "",
                    "## Capacity",
                    (
                        "Leveraged ETFs often have thinner opening-auction liquidity "
                        "than the underlying. Participation cap should be tightened "
                        "(see execution_policy.participation_cap)."
                    ),
                    "",
                    "## Mitigations",
                    "- Use price-protected order types (LOO/OPG limit) instead of naked market.",
                    "- Apply the gap filter from execution_policy.gap_filter.",
                    "- Recompute %ADV impact using the ETF's own ADV, not the underlying's.",
                    "- Review weekly via TCA against the official open price.",
                    "",
                ]
            )
        )


# ---------------------------------------------------------------------------
# Payload helpers
# ---------------------------------------------------------------------------


def _price_protection_payload(alt: ExecutionAlternative, context: RecommendationContext) -> dict:
    if alt.order_style == "day_market":
        return {"type": "none"}
    if alt.order_style in {"opg_limit", "loo_limit"}:
        return {
            "type": "limit",
            "limit_offset_bps": 25.0,
            "max_open_gap_pct": 2.5 if context.is_leveraged_etf else 4.0,
            "max_spread_bps": 20.0,
        }
    if alt.order_style.startswith("delayed_open"):
        return {"type": "gap_filter", "max_open_gap_pct": 1.5}
    return {"type": "participation_cap", "max_adv_pct": 2.5}


def _gap_filter_payload(context: RecommendationContext) -> dict:
    return {
        "enabled": True,
        "max_open_gap_pct": 2.5 if context.is_leveraged_etf else 4.0,
        "action_on_exceed": "skip",
    }


def _spread_filter_payload() -> dict:
    return {"enabled": True, "max_spread_bps": 20.0, "action_on_exceed": "delay_to_5m"}


def _participation_cap_payload(context: RecommendationContext) -> dict:
    return {
        "max_adv_pct": 2.5,
        "max_open_bar_volume_pct": 5.0 if context.is_leveraged_etf else 10.0,
    }


def _fallback_behavior_payload() -> dict:
    return {
        "if_not_filled": "skip",
        "if_gap_exceeds_limit": "skip",
        "if_spread_exceeds_limit": "delay_to_5m",
    }


def _gap_stress_payload(context: RecommendationContext) -> dict:
    return {
        "max_adverse_gap_pct": 5.0 if context.is_leveraged_etf else 2.5,
        "fill_model_gap_handling": "next_bar_open assumes fill at official open",
        "recommended_gap_filter": "skip trade if abs(gap_pct) > threshold",
        "scenarios": default_slippage_scenarios(),
    }


def _capacity_assessment_payload(spec: StrategySpec) -> dict:
    return {
        "max_position_weight": spec.risk.max_position_weight,
        "max_trades_per_day": spec.risk.max_trades_per_day,
        "notes": (
            "Capacity is bounded by max_position_weight and max_trades_per_day. "
            "Estimated order size as %ADV must be reviewed before paper_auto."
        ),
    }


def _naked_market_justification(
    alt: ExecutionAlternative, context: RecommendationContext
) -> str | None:
    if alt.order_style != "day_market":
        return None
    if not context.is_paper_auto:
        return None
    return (
        "MANUAL REVIEW REQUIRED: This generated draft selected day_market for a "
        "paper_auto strategy without an active leveraged_etf or daily_open risk "
        "domain. Replace this string with a written justification or re-run "
        "with price_protection alternatives."
    )


def _rationale(alt: ExecutionAlternative, context: RecommendationContext) -> str:
    parts = [f"Recommended {alt.order_style} ({alt.description})."]
    if context.is_leveraged_etf:
        parts.append("Leveraged ETF universe → price protection prioritised over fill certainty.")
    if context.is_daily_open:
        parts.append("Daily next-bar-open execution → opening-auction routing preferred.")
    if context.is_paper_auto:
        parts.append("paper_auto mode → must compare at least two methods.")
    return " ".join(parts)


def _fill_model_for(alt: ExecutionAlternative) -> str:
    if alt.order_style in {"opg_limit", "loo_limit"}:
        return "next_regular_open_with_policy"
    if alt.order_style.startswith("delayed_open"):
        return "delayed_open_with_policy"
    if alt.order_style == "twap":
        return "twap"
    return "next_bar_open"


def _render_markdown(
    spec: StrategySpec,
    recommended: ExecutionAlternative,
    context: RecommendationContext,
    alternatives: list[str],
) -> str:
    lines = [
        f"# Execution Reality — {spec.name}",
        f"\nGenerated: {_dt.date.today().isoformat()}",
        "",
        "## Context",
        f"- timeframe: {spec.timeframe}",
        f"- execution.mode: {spec.execution.mode}",
        f"- execution.fill_assumption: {spec.execution.fill_assumption}",
        f"- execution.broker: {spec.execution.broker}",
        f"- leveraged_etf: {context.is_leveraged_etf}",
        f"- daily_open: {context.is_daily_open}",
        f"- paper_auto: {context.is_paper_auto}",
        "",
        "## Recommended Policy",
        f"- order_style: {recommended.order_style}",
        f"- time_in_force: {recommended.time_in_force}",
        f"- price_protection: {recommended.price_protection}",
        f"- fill_certainty: {recommended.fill_certainty}",
        f"- slippage_risk: {recommended.slippage_risk}",
        f"- description: {recommended.description}",
        "",
        "## Alternatives Compared",
        *[f"- {a}" for a in alternatives],
        "",
        "## Rationale",
        _rationale(recommended, context),
        "",
        "## Reviewer Notes",
        "- Source cards for broker support of the chosen `time_in_force` must be present "
        "before paper_auto activation.",
        "- Slippage scenarios use deterministic defaults; replace with strategy-specific stress.",
        "- `gap_stress.max_adverse_gap_pct` is a placeholder — replace with empirically "
        "observed worst case.",
    ]
    return "\n".join(lines) + "\n"
