from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from open_composer.config import ensure_dir, project_root
from open_composer.models.strategy_spec import StrategySpec, load_strategy_spec
from open_composer.research.hybrid_router_core import (
    _effective_lookback,
    hybrid_params_from_label,
    hybrid_target_weight_snapshot,
)
from open_composer.research.pdr_attribution import (
    DEFAULT_END,
    DEFAULT_FOLDS,
    DEFAULT_OUT_DIR,
    DEFAULT_START,
    simulate_daily_rows,
)
from open_composer.research.post_drawdown_reentry_router import (
    PostDrawdownReentryParams,
    _features,
    _safe,
    _score_symbol,
    _selected_asset_blocked,
    post_drawdown_reentry_params_from_label,
)
from open_composer.research.router_common import (
    RouterFrameDataset,
    TargetSnapshot,
    backtest_router_params,
    load_daily_dataset,
    symbol_holding_return,
)
from open_composer.storage import write_json

DEFAULT_REVIEW_DATE_TAG = "20260704"
DEFAULT_SPEC_PATH = Path(
    "strategy_specs/drafts/nasdaq_tqqq_post_drawdown_reentry_router_delayed30_offensive.yaml"
)
VARIANT_NAMES = (
    "actual_ranked",
    "fixed_TQQQ",
    "fixed_QLD",
    "fixed_QQQ",
    "smooth_k3",
    "smooth_k5",
    "tie_bias_TQQQ_eps2",
)


@dataclass(frozen=True)
class RiskOnDecision:
    index: int
    date: str
    actual_symbol: str
    weight: float
    leader: str
    scores: dict[str, float]


def run_risk_on_ranked_rule_review(
    spec_path: Path = DEFAULT_SPEC_PATH,
    *,
    root: Path | None = None,
    label: str | None = None,
    data_source: str = "longbridge",
    feed: str | None = None,
    start: str = DEFAULT_START,
    end: str = DEFAULT_END,
    folds: tuple[tuple[str, str, str], ...] = DEFAULT_FOLDS,
    out_dir: Path = DEFAULT_OUT_DIR,
    date_tag: str = DEFAULT_REVIEW_DATE_TAG,
) -> dict[str, Any]:
    base = root or project_root()
    resolved_spec = spec_path if spec_path.is_absolute() else base / spec_path
    spec = load_strategy_spec(resolved_spec)
    route_label = label or spec.portfolio.selected_route_label
    if not route_label:
        raise ValueError("risk_on_ranked review requires a selected route label")
    params = hybrid_params_from_label(route_label)
    base_params = _base_pdr_params(params)
    dataset = load_daily_dataset(
        spec=spec,
        root=base,
        symbols=[item.upper() for item in spec.universe],
        data_source=data_source,
        feed=feed,
        start=start,
        end=end,
        market_symbol="QQQ",
        benchmark_symbol="TQQQ",
    )
    lookback = _effective_lookback(params)
    end_index = len(dataset.dates) - 1
    rows = simulate_daily_rows(spec, dataset, params, lookback, end_index)
    decisions = risk_on_ranked_decisions(spec, dataset, params, base_params, lookback, end_index)
    variant_symbols = build_variant_symbol_series(decisions)
    same_day = same_day_variant_review(
        spec=spec,
        dataset=dataset,
        rows=rows,
        decisions=decisions,
        variant_symbols=variant_symbols,
        folds=folds,
    )
    replay_candidates = select_full_replay_candidates(same_day)
    full_route_replays = [
        full_route_replay(
            spec=spec,
            dataset=dataset,
            params=params,
            variant_name=name,
            variant_symbols=variant_symbols[name],
            start_index=lookback,
            end_index=end_index,
        )
        for name in replay_candidates
    ]
    payload = {
        "report_type": "pdr_risk_on_ranked_rule_review",
        "strategy_name": spec.name,
        "source_spec_path": str(resolved_spec),
        "route_label": route_label,
        "data_profile": dataset.data_profile,
        "method": {
            "same_day_substitution": (
                "risk_on_ranked days are isolated; candidate symbols replace only the same "
                "day holding return without replaying the whole route"
            ),
            "full_route_replay": (
                "only variants that improved fold2 and fold3 without broad same-day "
                "degradation were replayed as validation, not parameter search"
            ),
            "variants": list(VARIANT_NAMES),
        },
        "risk_on_ranked_days": len(decisions),
        "same_day_review": same_day,
        "full_route_replays": full_route_replays,
        "conclusion": conclusion_payload(same_day, full_route_replays),
    }
    out_root = ensure_dir(out_dir if out_dir.is_absolute() else base / out_dir)
    json_path = out_root / f"risk-on-ranked-rule-review-{date_tag}.json"
    md_path = json_path.with_suffix(".md")
    payload["artifact_paths"] = {"json": str(json_path), "markdown": str(md_path)}
    write_json(json_path, payload)
    md_path.write_text(render_markdown(payload), encoding="utf-8")
    return payload


def risk_on_ranked_decisions(
    spec: StrategySpec,
    dataset: RouterFrameDataset,
    params: object,
    base_params: PostDrawdownReentryParams,
    start_index: int,
    end_index: int,
) -> list[RiskOnDecision]:
    decisions: list[RiskOnDecision] = []
    for index in range(start_index, end_index):
        snap = hybrid_target_weight_snapshot(spec, dataset, params, index)
        if snap.state != "risk_on_ranked" or not snap.weights:
            continue
        actual_symbol, weight = next(iter(snap.weights.items()))
        scores = risk_on_candidate_scores(dataset, base_params, index)
        leader = max(scores, key=scores.get) if scores else actual_symbol
        decisions.append(
            RiskOnDecision(
                index=index,
                date=dataset.dates[index],
                actual_symbol=actual_symbol,
                weight=float(weight),
                leader=leader,
                scores=scores,
            )
        )
    return decisions


def risk_on_candidate_scores(
    dataset: RouterFrameDataset,
    params: PostDrawdownReentryParams,
    index: int,
) -> dict[str, float]:
    features = _features(dataset)
    candidates = (
        ["TQQQ", "QLD"] if params.risk_universe == "tqqq_qld" else ["TQQQ", "QLD", "SOXL", "USD"]
    )
    semi_ok = (
        _safe(features["prior"]["SMH"].iloc[index], default=float("nan"))
        > _safe(features["symbol_sma"][200]["SMH"].iloc[index], default=float("nan"))
        and _safe(features["mom252"]["SMH"].iloc[index], default=-999.0) >= 100.0
    )
    scores: dict[str, float] = {}
    for symbol in candidates:
        if symbol not in dataset.symbols:
            continue
        if symbol == "SOXL" and not semi_ok:
            continue
        prior = _safe(features["prior"][symbol].iloc[index], default=float("nan"))
        sma200 = _safe(features["symbol_sma"][200][symbol].iloc[index], default=float("nan"))
        if not pd.notna(prior) or not pd.notna(sma200) or prior <= sma200:
            continue
        mom120 = _safe(features["momentum"][120][symbol].iloc[index], default=-999.0)
        if mom120 < 0.0:
            continue
        if _selected_asset_blocked(params, features, symbol, index):
            continue
        mom20 = _safe(features["momentum"][20][symbol].iloc[index], default=-999.0)
        mom60 = _safe(features["momentum"][60][symbol].iloc[index], default=-999.0)
        vol60 = max(_safe(features["vol60"][symbol].iloc[index], default=999.0), 1.0)
        dd20 = _safe(features["dd20"][symbol].iloc[index], default=-100.0)
        dd60 = _safe(features["dd60"][symbol].iloc[index], default=-100.0)
        scores[symbol] = _score_symbol(mom20, mom60, mom120, vol60, dd20, dd60)
    return scores


def build_variant_symbol_series(
    decisions: list[RiskOnDecision],
) -> dict[str, dict[int, str]]:
    leaders = {decision.index: decision.leader for decision in decisions}
    variants: dict[str, dict[int, str]] = {
        "actual_ranked": {item.index: item.actual_symbol for item in decisions},
        "fixed_TQQQ": {item.index: "TQQQ" for item in decisions},
        "fixed_QLD": {item.index: "QLD" for item in decisions},
        "fixed_QQQ": {item.index: "QQQ" for item in decisions},
        "smooth_k3": _smoothed_symbols(decisions, leaders, required_days=3),
        "smooth_k5": _smoothed_symbols(decisions, leaders, required_days=5),
        "tie_bias_TQQQ_eps2": _tie_bias_symbols(decisions, leaders, epsilon_score=2.0),
    }
    return variants


def same_day_variant_review(
    *,
    spec: StrategySpec,
    dataset: RouterFrameDataset,
    rows: list[dict[str, Any]],
    decisions: list[RiskOnDecision],
    variant_symbols: dict[str, dict[int, str]],
    folds: tuple[tuple[str, str, str], ...],
) -> dict[str, Any]:
    rows_by_date = {row["date"]: row for row in rows}
    actual_returns = {
        item.index: rows_by_date[item.date]["raw_return"]
        for item in decisions
        if item.date in rows_by_date
    }
    variant_returns = {
        name: {
            item.index: item.weight
            * symbol_holding_return(dataset, symbols[item.index], item.index, "open_to_open", spec)
            for item in decisions
            if item.index in symbols
        }
        for name, symbols in variant_symbols.items()
    }
    return {
        "full_window": _review_window(decisions, actual_returns, variant_returns),
        "folds": {
            name: _review_window(
                [item for item in decisions if start_date <= item.date <= end_date],
                actual_returns,
                variant_returns,
            )
            for name, start_date, end_date in folds
        },
    }


def full_route_replay(
    *,
    spec: StrategySpec,
    dataset: RouterFrameDataset,
    params: object,
    variant_name: str,
    variant_symbols: dict[int, str],
    start_index: int,
    end_index: int,
) -> dict[str, Any]:
    baseline = backtest_router_params(
        spec,
        dataset,
        params,
        snapshot=hybrid_target_weight_snapshot,
        start_index=start_index,
        end_index=end_index,
    )
    variant = backtest_router_params(
        spec,
        dataset,
        params,
        snapshot=_variant_snapshot(variant_symbols),
        start_index=start_index,
        end_index=end_index,
    )
    return {
        "variant": variant_name,
        "baseline_total_return_pct": baseline.total_return_pct,
        "variant_total_return_pct": variant.total_return_pct,
        "delta_total_return_pct_points": variant.total_return_pct - baseline.total_return_pct,
        "baseline_sharpe": baseline.sharpe_ratio,
        "variant_sharpe": variant.sharpe_ratio,
        "baseline_max_drawdown_pct": baseline.max_drawdown_pct,
        "variant_max_drawdown_pct": variant.max_drawdown_pct,
    }


def select_full_replay_candidates(same_day: dict[str, Any]) -> list[str]:
    candidates = []
    for variant in VARIANT_NAMES:
        if variant == "actual_ranked":
            continue
        folds = same_day["folds"]
        fold2 = folds.get("fold2", {}).get("variants", {}).get(variant, {})
        fold3 = folds.get("fold3", {}).get("variants", {}).get(variant, {})
        if fold2.get("arithmetic_delta_pct_points", 0.0) <= 5.0:
            continue
        if fold3.get("arithmetic_delta_pct_points", 0.0) <= 5.0:
            continue
        other_folds = [
            payload["variants"][variant]["arithmetic_delta_pct_points"]
            for name, payload in folds.items()
            if name not in {"fold2", "fold3"} and variant in payload["variants"]
        ]
        if any(delta < -2.0 for delta in other_folds):
            continue
        candidates.append(variant)
    candidates.sort(
        key=lambda name: same_day["full_window"]["variants"][name]["arithmetic_delta_pct_points"],
        reverse=True,
    )
    return candidates[:2]


def conclusion_payload(
    same_day: dict[str, Any],
    full_route_replays: list[dict[str, Any]],
) -> dict[str, Any]:
    if full_route_replays:
        best = max(full_route_replays, key=lambda row: row["delta_total_return_pct_points"])
        if best["delta_total_return_pct_points"] > 0 and (
            best["variant_max_drawdown_pct"] >= best["baseline_max_drawdown_pct"] - 2.0
        ):
            return {
                "decision": "future_independent_rule_iteration",
                "variant": best["variant"],
                "rationale": (
                    "same-day substitution improved fold2/fold3 and the validation replay "
                    "improved total return without materially worsening max drawdown"
                ),
            }
    full = same_day["full_window"]["variants"]
    best_name = max(
        (name for name in full if name != "actual_ranked"),
        key=lambda name: full[name]["arithmetic_delta_pct_points"],
    )
    best = full[best_name]
    if best["arithmetic_delta_pct_points"] <= 2.0:
        return {
            "decision": "current_rule_near_best",
            "variant": best_name,
            "rationale": "no tested same-day replacement produced meaningful full-window lift",
        }
    return {
        "decision": "evidence_insufficient",
        "variant": best_name,
        "rationale": (
            "same-day substitution found some lift, but it did not meet the fold2/fold3 "
            "and no-broad-degradation threshold for route replay"
        ),
    }


def render_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# PDR risk_on_ranked Rule Review",
        "",
        f"- Strategy: `{payload['strategy_name']}`",
        f"- Route: `{payload['route_label']}`",
        f"- risk_on_ranked days: `{payload['risk_on_ranked_days']}`",
        f"- Decision: `{payload['conclusion']['decision']}`",
        f"- Variant: `{payload['conclusion']['variant']}`",
        f"- Rationale: {payload['conclusion']['rationale']}",
        "",
        "## Same-Day Substitution",
        "",
        "| window | variant | days | arithmetic delta pp | segment compound delta pp |",
        "| --- | --- | ---: | ---: | ---: |",
    ]
    _append_window_table(lines, "full_window", payload["same_day_review"]["full_window"])
    for fold, window in payload["same_day_review"]["folds"].items():
        _append_window_table(lines, fold, window)
    lines.extend(
        [
            "",
            "## Full Route Replays",
            "",
            "| variant | total delta pp | baseline % | variant % | "
            "baseline max dd % | variant max dd % |",
            "| --- | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    if not payload["full_route_replays"]:
        lines.append("| none | n/a | n/a | n/a | n/a | n/a |")
    for row in payload["full_route_replays"]:
        lines.append(
            f"| {row['variant']} | {row['delta_total_return_pct_points']:.3f} | "
            f"{row['baseline_total_return_pct']:.3f} | {row['variant_total_return_pct']:.3f} | "
            f"{row['baseline_max_drawdown_pct']:.3f} | {row['variant_max_drawdown_pct']:.3f} |"
        )
    lines.extend(
        [
            "",
            "## Boundaries",
            "",
            "- This review did not modify any StrategySpec.",
            "- This review did not modify `post_drawdown_reentry_router.py` behavior.",
            "- Full route replay, if present, is validation of at most two variants, not search.",
            "",
        ]
    )
    return "\n".join(lines)


def _review_window(
    decisions: list[RiskOnDecision],
    actual_returns: dict[int, float],
    variant_returns: dict[str, dict[int, float]],
) -> dict[str, Any]:
    indices = [item.index for item in decisions if item.index in actual_returns]
    actual = [actual_returns[index] for index in indices]
    variants = {}
    for name, by_index in variant_returns.items():
        values = [by_index[index] for index in indices if index in by_index]
        aligned_actual = [actual_returns[index] for index in indices if index in by_index]
        variants[name] = {
            "days": len(values),
            "arithmetic_return_pct": sum(values) * 100,
            "arithmetic_delta_pct_points": (sum(values) - sum(aligned_actual)) * 100,
            "segment_compound_pct": _segment_compound_pct(decisions, by_index),
            "segment_compound_delta_pct_points": _segment_compound_pct(decisions, by_index)
            - _segment_compound_pct(decisions, actual_returns),
        }
    return {
        "days": len(indices),
        "actual_arithmetic_return_pct": sum(actual) * 100,
        "actual_segment_compound_pct": _segment_compound_pct(decisions, actual_returns),
        "variants": variants,
    }


def _segment_compound_pct(
    decisions: list[RiskOnDecision],
    returns: dict[int, float],
) -> float:
    total = 0.0
    current = 1.0
    previous_index: int | None = None
    for decision in decisions:
        if decision.index not in returns:
            continue
        if previous_index is not None and decision.index != previous_index + 1:
            total += current - 1.0
            current = 1.0
        current *= 1 + returns[decision.index]
        previous_index = decision.index
    total += current - 1.0
    return total * 100


def _smoothed_symbols(
    decisions: list[RiskOnDecision],
    leaders: dict[int, str],
    *,
    required_days: int,
) -> dict[int, str]:
    output: dict[int, str] = {}
    current: str | None = None
    pending: str | None = None
    pending_days = 0
    for decision in decisions:
        leader = leaders[decision.index]
        if current is None:
            current = leader
        elif leader != current:
            if leader == pending:
                pending_days += 1
            else:
                pending = leader
                pending_days = 1
            if pending_days >= required_days:
                current = leader
                pending = None
                pending_days = 0
        else:
            pending = None
            pending_days = 0
        output[decision.index] = current
    return output


def _tie_bias_symbols(
    decisions: list[RiskOnDecision],
    leaders: dict[int, str],
    *,
    epsilon_score: float,
) -> dict[int, str]:
    output = {}
    for decision in decisions:
        leader = leaders[decision.index]
        tqqq_score = decision.scores.get("TQQQ")
        leader_score = decision.scores.get(leader)
        if (
            leader != "TQQQ"
            and tqqq_score is not None
            and leader_score is not None
            and leader_score - tqqq_score < epsilon_score
        ):
            output[decision.index] = "TQQQ"
        else:
            output[decision.index] = leader
    return output


def _variant_snapshot(variant_symbols: dict[int, str]):
    def snapshot(
        spec: StrategySpec,
        dataset: RouterFrameDataset,
        params: object,
        index: int,
    ) -> TargetSnapshot:
        base = hybrid_target_weight_snapshot(spec, dataset, params, index)
        if base.state != "risk_on_ranked" or index not in variant_symbols or not base.weights:
            return base
        symbol = variant_symbols[index]
        if symbol not in dataset.symbols:
            return base
        weight = sum(float(value) for value in base.weights.values())
        return TargetSnapshot(
            selected=[symbol],
            weights={symbol: weight},
            volatility_scale=base.volatility_scale,
            market_regime_scale=base.market_regime_scale,
            market_drawdown_scale=base.market_drawdown_scale,
            state=f"{base.state}_review_{symbol}",
            qqq_trend_ok=base.qqq_trend_ok,
            qqq_momentum_ok=base.qqq_momentum_ok,
            qqq_drawdown_ok=base.qqq_drawdown_ok,
            leverage_trend_ok=base.leverage_trend_ok,
            leverage_volatility_ok=base.leverage_volatility_ok,
            leverage_drawdown_ok=base.leverage_drawdown_ok,
            core_gross=base.core_gross,
            satellite_gross=base.satellite_gross,
            satellite_scale=base.satellite_scale,
            theme_gate_ok=base.theme_gate_ok,
        )

    return snapshot


def _base_pdr_params(params: object) -> PostDrawdownReentryParams:
    base_label = getattr(params, "base_route_label", None)
    if base_label is None:
        base_label = params.label
    return post_drawdown_reentry_params_from_label(str(base_label))


def _append_window_table(lines: list[str], window_name: str, payload: dict[str, Any]) -> None:
    for name, item in payload["variants"].items():
        if name == "actual_ranked":
            continue
        lines.append(
            f"| {window_name} | {name} | {item['days']} | "
            f"{item['arithmetic_delta_pct_points']:.3f} | "
            f"{item['segment_compound_delta_pct_points']:.3f} |"
        )
