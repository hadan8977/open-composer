from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from open_composer.adapters.data import load_ohlcv_for_spec
from open_composer.config import (
    alpaca_api_key_id,
    alpaca_api_secret_key,
    ensure_dir,
    project_root,
)
from open_composer.expressions import evaluate_raw_expression, prepare_factor_frame
from open_composer.models.strategy_spec import load_strategy_spec
from open_composer.research.factor_lab import run_factor_lab
from open_composer.research.factor_library import (
    ALL_FACTORS,
    FactorDefinition,
    get_factor,
    list_factors,
    materialize_expression,
)
from open_composer.research.factor_lineage import append_lineage
from open_composer.research.metadata import frame_data_profile


@dataclass(frozen=True)
class AutoResearchResult:
    run_id: str
    thesis: str
    selected_factors: list[str]
    spec_path: Path
    evidence_status: str
    report_path: Path
    raw_evidence_status: str = "not_run"
    promotion_status: str | None = None
    paper_readiness_status: str | None = None
    fallback_message: str | None = None
    warnings: list[str] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)
    next_actions: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class _AutoEvidenceSummary:
    research_status: str
    raw_status: str
    promotion_status: str | None = None
    paper_readiness_status: str | None = None
    blockers: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


_FAMILY_KEYWORDS: dict[str, list[str]] = {
    "trend_momentum": ["trend", "uptrend", "momentum", "rally", "continuation"],
    "relative_strength": ["relative", "rs", "leader", "leadership", "ranking"],
    "momentum_short": ["reversal", "mean revert", "mean-revert", "bounce", "oversold"],
    "risk_regime": ["regime", "risk", "risk off", "risk-off", "vix", "calm", "quiet"],
    "volatility_rank": ["volatility", "vol", "quiet", "calm", "range"],
    "drawdown_guard": ["drawdown", "crash", "guard", "protect", "defensive"],
    "overnight_gap": ["overnight", "gap", "open gap"],
    "kline_shape": ["candle", "kbar", "k-bar", "body", "shadow"],
    "breadth_canary": ["breadth", "canary", "participation"],
    "volume_momentum": ["volume", "liquidity", "participation"],
}

_COMPLEMENT_RULES: dict[str, str] = {
    "trend_momentum": "risk_regime",
    "momentum_short": "risk_regime",
    "relative_strength": "risk_regime",
    "overnight_gap": "risk_regime",
    "kline_shape": "risk_regime",
    "volume_momentum": "risk_regime",
    "risk_regime": "trend_momentum",
    "drawdown_guard": "trend_momentum",
    "volatility_rank": "trend_momentum",
    "breadth_canary": "trend_momentum",
}

_THESIS_FAMILY_ASSERTIONS: tuple[tuple[tuple[str, ...], str], ...] = (
    (("overnight", "gap", "open gap"), "overnight_gap"),
    (("drawdown", "crash"), "drawdown_guard"),
    (("volatility", " vol "), "volatility_rank"),
)

_ZSCORE_WINDOW_BY_TIMEFRAME: dict[str, int] = {
    "daily": 60,
    "weekly": 26,
    "4h": 60,
    "1h": 120,
    "30m": 120,
    "15m": 120,
    "5m": 240,
    "1m": 240,
}
_DEFAULT_ZSCORE_WINDOW = 60
_COMPOSITE_ENTRY_THRESHOLD = 0.3
_COMPOSITE_EXIT_THRESHOLD = -0.3
_MIN_ABS_RANK_IC_FOR_SIGNAL = 0.02
_MIN_IR_FOR_SELECTION = 0.3
_AUTO_RESEARCH_SCHEMA_VERSION = "2"
_DEFAULT_COMMISSION_PCT = 0.05


def run_auto_research(
    thesis: str,
    universe: list[str],
    *,
    timeframe: str = "daily",
    data_source: str = "alpaca",
    data_path: str | None = None,
    max_factors: int = 5,
    use_llm: bool = False,
    refresh_data: bool = False,
    zero_cost_smoke: bool = False,
    model_kind: str | None = None,
    root: Path | None = None,
) -> AutoResearchResult:
    base = root or project_root()
    symbols = [symbol.upper().strip() for symbol in universe if symbol.strip()]
    if not symbols:
        raise ValueError("universe must include at least one symbol")
    if max_factors < 1:
        raise ValueError("max_factors must be at least 1")
    if data_source != "sample":
        raise ValueError(
            "market-data auto research requires a preregistered iteration workflow; "
            "use sample data for workflow-only smoke"
        )

    run_id = _make_run_id(thesis)
    fallback_message: str | None = None
    available, reason = _check_data_source_available(data_source)
    if not available:
        fallback_message = (
            f"data_source={data_source} unavailable ({reason}); falling back to sample"
        )
        data_source = "sample"
        data_path = data_path or _sample_data_path_for_symbol(symbols[0], base)
    run_dir = ensure_dir(base / "reports" / "research" / "auto" / run_id)
    (run_dir / "thesis.md").write_text(thesis.rstrip() + "\n", encoding="utf-8")
    if fallback_message:
        (run_dir / "data_source_fallback.txt").write_text(fallback_message + "\n", encoding="utf-8")

    candidates = (
        _select_with_llm(thesis, symbols) if use_llm else _select_with_keyword_heuristic(thesis)
    )
    candidates = [factor for factor in candidates if factor.expression]
    if not candidates:
        candidates = list_factors(family="trend_momentum", expression_only=True)[:5]
    _write_json(run_dir / "candidates.json", [factor.id for factor in candidates])

    ic_scores = _run_single_factor_ic(
        candidates=candidates,
        thesis=thesis,
        universe=symbols,
        timeframe=timeframe,
        data_source=data_source,
        data_path=data_path,
        base=base,
        run_dir=run_dir,
        refresh_data=refresh_data,
    )
    _write_json(run_dir / "ic_scores.json", ic_scores)
    oos_summary = _write_oos_summary(
        candidates=candidates,
        thesis=thesis,
        universe=symbols,
        timeframe=timeframe,
        data_source=data_source,
        data_path=data_path,
        base=base,
        run_dir=run_dir,
        refresh_data=refresh_data,
    )

    selected = _select_top_k(ic_scores, candidates, max_factors)
    usable_selection = bool(selected)
    if not selected:
        selected = candidates[: min(max_factors, max(1, len(candidates)))]
    selected_ids_for_research = [factor.id for factor in selected] if usable_selection else []
    _write_json(run_dir / "selected_factors.json", selected_ids_for_research)

    spec_path = _draft_spec(
        thesis=thesis,
        run_id=run_id,
        selected=selected,
        ic_scores=ic_scores,
        universe=symbols,
        timeframe=timeframe,
        data_source=data_source,
        data_path=data_path,
        base=base,
        zero_cost_smoke=zero_cost_smoke,
        model_kind=model_kind,
    )
    data_profile = _write_auto_data_profile(
        spec_path=spec_path,
        run_dir=run_dir,
        base=base,
        refresh_data=refresh_data,
    )
    _persist_research_strict_tier(spec_path, data_profile)

    evidence_summary = _AutoEvidenceSummary(
        research_status="not_run",
        raw_status="not_run",
    )
    try:
        from open_composer.research.evidence import build_strategy_evidence
        from open_composer.research.research_brief import init_research_brief

        init_research_brief(spec_path, base, search_budget=max(1, len(selected)), overwrite=True)
        evidence = build_strategy_evidence(spec_path, base, refresh_data=refresh_data)
        evidence_summary = _summarize_auto_evidence(evidence)
    except Exception as exc:  # noqa: BLE001
        evidence_summary = _AutoEvidenceSummary(
            research_status="failed",
            raw_status="failed",
            blockers=[str(exc)],
        )

    report_path = _write_final_report(
        run_dir=run_dir,
        thesis=thesis,
        candidates=candidates,
        ic_scores=ic_scores,
        selected=selected,
        usable_selection=usable_selection,
        spec_path=spec_path,
        evidence_summary=evidence_summary,
        data_profile=data_profile,
        oos_summary=oos_summary,
        zero_cost_smoke=zero_cost_smoke,
    )
    _write_run_metadata(
        run_dir=run_dir,
        run_id=run_id,
        thesis=thesis,
        universe=symbols,
        timeframe=timeframe,
        data_source=data_source,
        max_factors=max_factors,
        candidates=candidates,
        selected=selected,
        usable_selection=usable_selection,
        evidence_summary=evidence_summary,
        data_profile=data_profile,
        spec_path=spec_path,
        report_path=report_path,
        base=base,
    )
    return AutoResearchResult(
        run_id=run_id,
        thesis=thesis,
        selected_factors=selected_ids_for_research,
        spec_path=spec_path,
        evidence_status=evidence_summary.research_status,
        raw_evidence_status=evidence_summary.raw_status,
        promotion_status=evidence_summary.promotion_status,
        paper_readiness_status=evidence_summary.paper_readiness_status,
        fallback_message=fallback_message,
        report_path=report_path,
        warnings=evidence_summary.warnings,
        blockers=evidence_summary.blockers,
        next_actions=[
            f"Review {spec_path}",
            f"Read {report_path}",
            f"Run oc strategy evidence {spec_path}",
        ],
    )


def _select_with_keyword_heuristic(thesis: str) -> list[FactorDefinition]:
    text = thesis.lower()
    matched_families: list[str] = []
    for family, triggers in _FAMILY_KEYWORDS.items():
        if any(trigger in text for trigger in triggers):
            matched_families.append(family)
    if not matched_families:
        matched_families = ["trend_momentum", "risk_regime"]

    extended_families = list(matched_families)
    for family in matched_families:
        complement = _COMPLEMENT_RULES.get(family)
        if complement and complement not in extended_families:
            extended_families.append(complement)
    matched_families = extended_families

    candidates: list[FactorDefinition] = []
    seen: set[str] = set()
    for family in matched_families:
        added = 0
        for factor in _factors_for_family_or_alias(family):
            if factor.id not in seen and factor.expression:
                candidates.append(factor)
                seen.add(factor.id)
                added += 1
            if added >= 5:
                break

    for triggers, required_family in _THESIS_FAMILY_ASSERTIONS:
        if not any(trigger in text for trigger in triggers):
            continue
        if any(_factor_matches_required_family(factor, required_family) for factor in candidates):
            continue
        for factor in _factors_for_family_or_alias(required_family)[:3]:
            if factor.id not in seen and factor.expression:
                candidates.append(factor)
                seen.add(factor.id)
        if not any(
            _factor_matches_required_family(factor, required_family) for factor in candidates
        ):
            raise ValueError(
                f"thesis requires {required_family} factors, but no expressionable catalog "
                "factor was available"
            )
    return candidates[:15]


def _select_with_llm(thesis: str, universe: list[str]) -> list[FactorDefinition]:
    from open_composer.config import default_openai_model, openai_api_key, openai_base_url

    if not openai_api_key():
        return _select_with_keyword_heuristic(thesis)
    try:
        from openai import OpenAI
    except ImportError:
        return _select_with_keyword_heuristic(thesis)

    catalog = [
        {"id": factor.id, "family": factor.family, "description": factor.description}
        for factor in ALL_FACTORS
        if factor.expression
    ]
    schema = {
        "type": "object",
        "additionalProperties": False,
        "required": ["selected_factor_ids", "reasoning"],
        "properties": {
            "selected_factor_ids": {
                "type": "array",
                "minItems": 1,
                "maxItems": 15,
                "items": {"type": "string", "enum": [item["id"] for item in catalog]},
            },
            "reasoning": {"type": "string"},
        },
    }
    try:
        client = OpenAI(api_key=openai_api_key(), base_url=openai_base_url())
        response = client.responses.create(
            model=default_openai_model(),
            input=[
                {
                    "role": "system",
                    "content": (
                        "Select factor IDs from the provided catalog for a single-symbol "
                        "research thesis. Return only existing IDs."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "thesis": thesis,
                            "universe": universe,
                            "catalog": catalog,
                        },
                        indent=2,
                    ),
                },
            ],
            text={
                "format": {
                    "type": "json_schema",
                    "name": "factor_selection",
                    "strict": True,
                    "schema": schema,
                }
            },
        )
        payload = json.loads(response.output_text)
        return [get_factor(factor_id) for factor_id in payload["selected_factor_ids"]]
    except Exception:  # noqa: BLE001
        return _select_with_keyword_heuristic(thesis)


def _run_single_factor_ic(
    *,
    candidates: list[FactorDefinition],
    thesis: str,
    universe: list[str],
    timeframe: str,
    data_source: str,
    data_path: str | None,
    base: Path,
    run_dir: Path,
    refresh_data: bool = False,
) -> dict[str, dict[str, Any]]:
    scores: dict[str, dict[str, Any]] = {}
    mini_dir = ensure_dir(run_dir / "mini_specs")
    for factor in candidates:
        if not factor.expression:
            scores[factor.id] = {
                "status": "skipped",
                "reason": "no_expression_template",
                "rank_ic": None,
                "rank_ic_diagnosis": "no_expression_template",
            }
            continue
        spec_path = _mini_spec_path(
            factor=factor,
            thesis=thesis,
            universe=universe,
            timeframe=timeframe,
            data_source=data_source,
            data_path=data_path,
            base=base,
            mini_dir=mini_dir,
        )
        try:
            result = run_factor_lab(
                spec_path,
                base,
                forward_bars=5,
                quantiles=5,
                refresh_data=refresh_data,
            )
            metric = result.factor_metrics[0] if result.factor_metrics else None
            if metric is None:
                scores[factor.id] = {
                    "status": "failed",
                    "reason": "no_metric_returned",
                    "rank_ic": None,
                    "rank_ic_diagnosis": "rank_ic_undefined_unknown_reason",
                    "flags": ["missing_metric"],
                    "spec_path": _relpath(spec_path, base),
                    "json_path": _relpath(result.json_path, base),
                }
                continue
            rank_ic = metric.rank_ic
            rank_ic_diagnosis = (
                _rank_ic_diagnosis(metric.flags, metric.observations, metric.coverage_pct)
                if rank_ic is None
                else None
            )
            scores[factor.id] = {
                "status": result.status if rank_ic is not None else "diagnostic",
                "rank_ic": rank_ic,
                "rank_ic_diagnosis": rank_ic_diagnosis,
                "rolling_rank_ic_mean": metric.rolling_rank_ic_mean,
                "rolling_rank_ic_std": getattr(metric, "rolling_rank_ic_std", None),
                "ir": getattr(metric, "ir", None),
                "stability_score": metric.stability_score,
                "coverage_pct": metric.coverage_pct,
                "observations": metric.observations,
                "top_bottom_spread_pct": metric.top_bottom_spread_pct,
                "flags": metric.flags,
                "spec_path": _relpath(spec_path, base),
                "json_path": _relpath(result.json_path, base),
            }
        except Exception as exc:  # noqa: BLE001
            scores[factor.id] = {
                "status": "failed",
                "reason": "factor_lab_exception",
                "error": str(exc),
                "rank_ic": None,
                "rank_ic_diagnosis": "factor_lab_exception",
            }
    return scores


def _write_oos_summary(
    *,
    candidates: list[FactorDefinition],
    thesis: str,
    universe: list[str],
    timeframe: str,
    data_source: str,
    data_path: str | None,
    base: Path,
    run_dir: Path,
    refresh_data: bool,
) -> dict[str, Any]:
    if not candidates:
        payload = {"status": "blocked", "reason": "no_candidates", "factors": {}}
        _write_json(run_dir / "oos_summary.json", payload)
        return payload
    spec_path = _mini_spec_path(
        factor=candidates[0],
        thesis=thesis,
        universe=universe,
        timeframe=timeframe,
        data_source=data_source,
        data_path=data_path,
        base=base,
        mini_dir=ensure_dir(run_dir / "mini_specs"),
    )
    spec = load_strategy_spec(spec_path)
    frame = load_ohlcv_for_spec(spec, base, refresh=refresh_data)
    prepared = prepare_factor_frame(
        frame,
        {},
        root=base,
        symbol=spec.primary_symbol,
        require_feature_symbol=False,
    )
    forward = prepared["close"].astype(float).pct_change(5).shift(-5)
    split_index = max(1, min(len(prepared) - 1, int(len(prepared) * 0.7)))
    rows: dict[str, dict[str, Any]] = {}
    for factor in candidates:
        try:
            expression = materialize_expression(factor, {})
            signal = evaluate_raw_expression(expression, prepared)
        except Exception as exc:  # noqa: BLE001
            rows[factor.id] = {"status": "failed", "error": str(exc)}
            continue
        series = signal.astype(float)
        train_ic, train_obs = _rank_ic_for_slice(
            series.iloc[:split_index], forward.iloc[:split_index]
        )
        test_ic, test_obs = _rank_ic_for_slice(
            series.iloc[split_index:], forward.iloc[split_index:]
        )
        rows[factor.id] = {
            "status": "ok" if train_ic is not None and test_ic is not None else "diagnostic",
            "train_rank_ic": train_ic,
            "test_rank_ic": test_ic,
            "train_observations": train_obs,
            "test_observations": test_obs,
            "sign_consistent": _sign_consistent(train_ic, test_ic),
        }
    payload = {
        "status": "ok",
        "split": "chronological_70_30",
        "forward_bars": 5,
        "candidate_count": len(candidates),
        "split_index": split_index,
        "records": len(prepared),
        "factors": rows,
    }
    _write_json(run_dir / "oos_summary.json", payload)
    return payload


def _rank_ic_for_slice(signal: Any, forward: Any) -> tuple[float | None, int]:
    import pandas as pd

    frame = pd.DataFrame({"signal": signal, "forward": forward}).dropna()
    observations = len(frame)
    if observations < 30:
        return None, observations
    if frame["signal"].nunique(dropna=True) <= 1 or frame["forward"].nunique(dropna=True) <= 1:
        return None, observations
    value = frame["signal"].rank().corr(frame["forward"].rank())
    if value != value:
        return None, observations
    return float(value), observations


def _sign_consistent(train_ic: float | None, test_ic: float | None) -> bool | None:
    if train_ic is None or test_ic is None:
        return None
    if train_ic == 0 or test_ic == 0:
        return True
    return (train_ic > 0 and test_ic > 0) or (train_ic < 0 and test_ic < 0)


def _rank_ic_diagnosis(flags: list[str], observations: int, coverage_pct: float) -> str:
    flag_set = set(flags)
    if observations < 30 or "insufficient_observations" in flag_set:
        return "insufficient_observations"
    if coverage_pct < 50 or "low_coverage" in flag_set:
        return "low_coverage"
    if "zero_variance" in flag_set or "constant_series" in flag_set:
        return "zero_variance_signal"
    if "all_nan" in flag_set:
        return "all_nan_signal"
    return "rank_ic_undefined_unknown_reason"


def _select_top_k(
    ic_scores: dict[str, dict[str, Any]],
    candidates: list[FactorDefinition],
    k: int,
) -> list[FactorDefinition]:
    scored: list[tuple[FactorDefinition, float]] = []
    for factor in candidates:
        score = ic_scores.get(factor.id, {})
        rank_ic = _float_or_none(score.get("rank_ic"))
        ir = _float_or_none(score.get("ir"))
        coverage = _float_or_none(score.get("coverage_pct")) or 0.0
        observations = int(score.get("observations") or 0)
        stability = _float_or_none(score.get("stability_score")) or 0.0
        if rank_ic is None or ir is None or observations < 30 or coverage < 70:
            continue
        if abs(rank_ic) < _MIN_ABS_RANK_IC_FOR_SIGNAL:
            continue
        if ir < _MIN_IR_FOR_SELECTION:
            continue
        quality = max(ir, 0.1) * max(stability, 0.1)
        scored.append((factor, abs(rank_ic) * quality * (coverage / 100.0)))
    scored.sort(key=lambda item: item[1], reverse=True)
    selected: list[FactorDefinition] = []
    family_counts: dict[str, int] = {}
    risk_filter_count = 0
    risk_families = {"risk_regime", "drawdown_guard", "volatility_rank"}
    for factor, _score in scored:
        family_count = family_counts.get(factor.family, 0)
        if family_count >= 2:
            continue
        if factor.family in risk_families and risk_filter_count >= max(1, min(2, k - 1)):
            continue
        selected.append(factor)
        family_counts[factor.family] = family_count + 1
        if factor.family in risk_families:
            risk_filter_count += 1
        if len(selected) >= k:
            break
    if len(selected) < k:
        selected_ids = {factor.id for factor in selected}
        for factor, _score in scored:
            if factor.id in selected_ids:
                continue
            selected.append(factor)
            selected_ids.add(factor.id)
            if len(selected) >= k:
                break
    return selected


def _draft_spec(
    *,
    thesis: str,
    run_id: str,
    selected: list[FactorDefinition],
    ic_scores: dict[str, dict[str, Any]],
    universe: list[str],
    timeframe: str,
    data_source: str,
    data_path: str | None,
    base: Path,
    zero_cost_smoke: bool = False,
    model_kind: str | None = None,
) -> Path:
    slug = run_id.lower().replace("-", "_")
    spec_name = f"auto_{slug}"
    spec_path = base / "strategy_specs" / "drafts" / f"{spec_name}.yaml"
    ensure_dir(spec_path.parent)
    factor_names = [_factor_signal_name(factor) for factor in selected]
    factors = {
        name: {
            "source": "factor_library",
            "factor_id": factor.id,
            "params": _factor_default_params(factor),
        }
        for name, factor in zip(factor_names, selected, strict=True)
    }
    zscore_window = _ZSCORE_WINDOW_BY_TIMEFRAME.get(timeframe, _DEFAULT_ZSCORE_WINDOW)
    oriented_terms: list[str] = []
    for name, factor in zip(factor_names, selected, strict=True):
        rank_ic = _float_or_none((ic_scores.get(factor.id) or {}).get("rank_ic"))
        if rank_ic is None or abs(rank_ic) < _MIN_ABS_RANK_IC_FOR_SIGNAL:
            continue
        prefix = "" if rank_ic >= 0 else "-1 * "
        oriented_terms.append(f"({prefix}zscore({name}, {zscore_window}))")

    if oriented_terms:
        factors["composite_score"] = {
            "source": "expression",
            "expression": "(" + " + ".join(oriented_terms) + f") / {len(oriented_terms)}",
        }
        entry_all = [f"composite_score > {_COMPOSITE_ENTRY_THRESHOLD}"]
        exit_any = [f"composite_score < {_COMPOSITE_EXIT_THRESHOLD}"]
        signal_construction = (
            f"Oriented composite z-score over {len(oriented_terms)} factors with "
            f"|rank_ic| >= {_MIN_ABS_RANK_IC_FOR_SIGNAL}; window={zscore_window}; "
            f"entry>{_COMPOSITE_ENTRY_THRESHOLD}, exit<{_COMPOSITE_EXIT_THRESHOLD}."
        )
    elif factor_names:
        factors["composite_score"] = {
            "source": "expression",
            "expression": f"zscore({factor_names[0]}, {zscore_window})",
        }
        entry_all = [f"composite_score > {_COMPOSITE_ENTRY_THRESHOLD}"]
        exit_any = [f"composite_score < {_COMPOSITE_EXIT_THRESHOLD}"]
        signal_construction = (
            "Fallback single-factor z-score because no selected factor had usable "
            f"|rank_ic| >= {_MIN_ABS_RANK_IC_FOR_SIGNAL}; window={zscore_window}; "
            f"entry>{_COMPOSITE_ENTRY_THRESHOLD}, exit<{_COMPOSITE_EXIT_THRESHOLD}."
        )
    else:
        entry_all = ["close > sma(close, 20)"]
        exit_any = ["close < sma(close, 20)"]
        signal_construction = (
            "Fallback close-vs-SMA signal because auto research selected no factors."
        )
    parameter_space = {
        f"factors.{name}.params.{param}": values
        for name, factor in zip(factor_names, selected, strict=True)
        for param, values in factor.default_parameter_space.items()
        if values and all(_is_scalar(item) for item in values)
    }
    spec_yaml: dict[str, Any] = {
        "name": spec_name,
        "description": f"Auto-generated by oc research auto. Thesis: {thesis}",
        "timeframe": timeframe,
        "universe": universe,
        "lifecycle": "draft",
        "entry": {"all": entry_all, "any": []},
        "exit": {"all": [], "any": exit_any},
        "risk": {"max_trades_per_day": 1, "max_position_weight": 0.5, "stop_loss_pct": 3.0},
        "costs": {
            "commission_pct": 0.0 if zero_cost_smoke else _DEFAULT_COMMISSION_PCT,
            "slippage_bps": 0.0 if zero_cost_smoke else _default_slippage_bps(timeframe),
            "impact_model": "linear",
            "impact_eta": 0.0,
            "impact_gamma": 0.0,
        },
        "execution": {
            "backend": "python_reference",
            "mode": "manual_signal",
            "signal_on": "bar_close",
            "fill_assumption": "next_bar_open",
            "broker": "none",
        },
        "data": {"source": data_source, "symbol": universe[0], "path": data_path, "feed": None},
        "data_assumptions": {
            "source": data_source,
            "adjusted": True,
            "timezone": "America/New_York",
        },
        "factors": factors,
        "llm_review": {"enabled": False},
        "notes": {
            "intent": f"AI-driven research from thesis: {thesis}",
            "open_questions": [],
            "signal_construction": signal_construction,
        },
        "research_design": {
            "workflow_only_ungated_draft": data_source == "sample" and model_kind is None,
            "parameter_space": parameter_space,
            "candidate_budget": max(1, min(150, len(parameter_space) * 3 or len(selected))),
            "selection_objective": "rank_ic_ir_stability_then_research_evidence",
            "anti_overfit_notes": [
                "Catalog candidates are selected before backtest evidence.",
                "Sample-data evidence is workflow-only and not paper-ready.",
            ],
            "validation_plan": [
                "single-factor IC screen",
                "StrategySpec validation",
                "strategy evidence report",
            ],
        },
        "required_capabilities": [_market_capability(data_source, timeframe)],
    }
    if model_kind:
        if model_kind != "lightgbm":
            raise ValueError("--model currently supports only lightgbm")
        spec_yaml["model"] = {
            "kind": "lightgbm_regressor",
            "features": factor_names,
            "label": {"type": "forward_return", "horizon_bars": 5},
            "training": {
                "window_bars": 378 if timeframe == "daily" else 240,
                "retrain_every_bars": 21 if timeframe == "daily" else 40,
                "test_window_bars": 63 if timeframe == "daily" else 80,
                "embargo_bars": 5,
                "seed": 42,
            },
            "selection": {"method": "threshold", "threshold": 0.0},
            "baseline": "linear_composite",
        }
    spec_path.write_text(yaml.safe_dump(spec_yaml, sort_keys=False), encoding="utf-8")
    load_strategy_spec(spec_path)
    for factor in selected:
        append_lineage(
            factor.id, spec_path, added_by="auto_research", creation_thesis=thesis, root=base
        )
    return spec_path


def _default_slippage_bps(timeframe: str) -> float:
    if timeframe == "daily":
        return 5.0
    return 2.0


def _factor_default_params(factor: FactorDefinition) -> dict[str, Any]:
    params: dict[str, Any] = {}
    for name, values in factor.default_parameter_space.items():
        if not values:
            continue
        params[name] = values[0]
    return params


def _write_auto_data_profile(
    *,
    spec_path: Path,
    run_dir: Path,
    base: Path,
    refresh_data: bool,
) -> dict[str, Any]:
    spec = load_strategy_spec(spec_path)
    frame = load_ohlcv_for_spec(spec, base, refresh=refresh_data)
    profile = frame_data_profile(
        frame,
        symbol=spec.primary_symbol,
        timeframe=spec.timeframe,
        provider=spec.data.source,
        feed=spec.data.feed,
        source_mode=frame.attrs.get("data_source_mode") or spec.data.source,
        path=frame.attrs.get("data_source_path") or spec.data.path,
    )
    profile["refresh_data"] = refresh_data
    _write_json(run_dir / "data_profile.json", profile)
    return profile


def _persist_research_strict_tier(spec_path: Path, data_profile: dict[str, Any]) -> None:
    if data_profile.get("acquisition_tier") != "research_strict":
        return
    raw = yaml.safe_load(spec_path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        return
    data_assumptions = raw.setdefault("data_assumptions", {})
    if not isinstance(data_assumptions, dict):
        data_assumptions = {}
        raw["data_assumptions"] = data_assumptions
    data_assumptions["acquisition_tier"] = "research_strict"
    spec_path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
    load_strategy_spec(spec_path)


def _write_run_metadata(
    *,
    run_dir: Path,
    run_id: str,
    thesis: str,
    universe: list[str],
    timeframe: str,
    data_source: str,
    max_factors: int,
    candidates: list[FactorDefinition],
    selected: list[FactorDefinition],
    usable_selection: bool,
    evidence_summary: _AutoEvidenceSummary,
    data_profile: dict[str, Any],
    spec_path: Path,
    report_path: Path,
    base: Path,
) -> None:
    payload = {
        "schema_version": _AUTO_RESEARCH_SCHEMA_VERSION,
        "run_id": run_id,
        "thesis": thesis,
        "universe": universe,
        "primary_symbol": universe[0] if universe else None,
        "timeframe": timeframe,
        "data_source": data_source,
        "data_source_mode": data_profile.get("source_mode"),
        "data_acquisition_tier": data_profile.get("acquisition_tier"),
        "max_factors": max_factors,
        "candidate_count": len(candidates),
        "selected_count": len(selected) if usable_selection else 0,
        "usable_selection": usable_selection,
        "research_status": evidence_summary.research_status,
        "raw_evidence_status": evidence_summary.raw_status,
        "promotion_status": evidence_summary.promotion_status,
        "paper_readiness_status": evidence_summary.paper_readiness_status,
        "spec_path": _relpath(spec_path, base),
        "report_path": _relpath(report_path, base),
        "generated_at": datetime.now(UTC).isoformat(),
    }
    _write_json(run_dir / "run_metadata.json", payload)


def _mini_spec_path(
    *,
    factor: FactorDefinition,
    thesis: str,
    universe: list[str],
    timeframe: str,
    data_source: str,
    data_path: str | None,
    base: Path,
    mini_dir: Path,
) -> Path:
    factor_name = _factor_signal_name(factor)
    spec_name = f"auto_ic_{factor.id}"
    spec_yaml = {
        "name": spec_name,
        "description": f"Auto-research single-factor IC test. Thesis: {thesis}",
        "timeframe": timeframe,
        "universe": universe,
        "lifecycle": "draft",
        "entry": {"all": [f"{factor_name} > 0"], "any": []},
        "exit": {"all": [], "any": [f"{factor_name} < 0"]},
        "risk": {"max_trades_per_day": 1, "max_position_weight": 0.5},
        "costs": {
            "commission_pct": _DEFAULT_COMMISSION_PCT,
            "slippage_bps": _default_slippage_bps(timeframe),
            "impact_model": "linear",
            "impact_eta": 0.0,
            "impact_gamma": 0.0,
        },
        "execution": {
            "backend": "python_reference",
            "mode": "manual_signal",
            "signal_on": "bar_close",
            "fill_assumption": "next_bar_open",
            "broker": "none",
        },
        "data": {"source": data_source, "symbol": universe[0], "path": data_path, "feed": None},
        "data_assumptions": {
            "source": data_source,
            "adjusted": True,
            "timezone": "America/New_York",
        },
        "factors": {
            factor_name: {
                "source": "factor_library",
                "factor_id": factor.id,
                "params": {},
            }
        },
        "llm_review": {"enabled": False},
        "research_design": {
            "workflow_only_ungated_draft": data_source == "sample",
            "parameter_space": {"factor_id": [factor.id]},
            "candidate_budget": 1,
            "selection_objective": "single_factor_rank_ic_workflow_smoke",
            "anti_overfit_notes": [
                "This mini spec is workflow-only and cannot support promotion or paper readiness."
            ],
            "validation_plan": ["single_factor_ic_smoke"],
        },
        "notes": {
            "intent": f"Single-factor IC screen for {factor.id}",
            "open_questions": [],
        },
        "required_capabilities": [_market_capability(data_source, timeframe)],
    }
    spec_path = mini_dir / f"{spec_name}.yaml"
    spec_path.write_text(yaml.safe_dump(spec_yaml, sort_keys=False), encoding="utf-8")
    load_strategy_spec(spec_path)
    return spec_path


def _write_final_report(
    *,
    run_dir: Path,
    thesis: str,
    candidates: list[FactorDefinition],
    ic_scores: dict[str, dict[str, Any]],
    selected: list[FactorDefinition],
    usable_selection: bool,
    spec_path: Path,
    evidence_summary: _AutoEvidenceSummary,
    data_profile: dict[str, Any],
    oos_summary: dict[str, Any],
    zero_cost_smoke: bool,
) -> Path:
    selected_ids = {factor.id for factor in selected} if usable_selection else set()
    lines = [
        "# AI Auto-Research Report",
        "",
        f"- Thesis: {thesis}",
        f"- Generated: `{datetime.now(UTC).isoformat()}`",
        f"- Spec: `{spec_path}`",
        f"- Research status: `{evidence_summary.research_status}`",
        f"- Raw strategy evidence status: `{evidence_summary.raw_status}`",
        f"- Promotion status: `{evidence_summary.promotion_status or 'not_available'}`",
        f"- Paper readiness status: `{evidence_summary.paper_readiness_status or 'not_available'}`",
        f"- Data tier: `{data_profile.get('acquisition_tier') or 'unknown'}`",
        f"- Data source mode: `{data_profile.get('source_mode') or 'unknown'}`",
        f"- Data feed: `{data_profile.get('feed') or 'unknown'}`",
        f"- Zero-cost smoke: `{zero_cost_smoke}`",
        "",
        "## Data Provenance",
        "",
        f"- Provider: `{data_profile.get('provider') or 'unknown'}`",
        f"- Feed: `{data_profile.get('feed') or 'unknown'}`",
        f"- Source mode: `{data_profile.get('source_mode') or 'unknown'}`",
        f"- Acquisition tier: `{data_profile.get('acquisition_tier') or 'unknown'}`",
        f"- Records: `{data_profile.get('records') or 0}`",
        f"- Window: `{data_profile.get('first_timestamp') or 'unknown'}` -> "
        f"`{data_profile.get('last_timestamp') or 'unknown'}`",
        f"- Refresh data: `{data_profile.get('refresh_data')}`",
        f"- Path: `{data_profile.get('path') or 'unknown'}`",
        "",
        f"## Candidate Factors ({len(candidates)})",
        "",
        "| Factor | Family | Rank IC | IR | Stability | Coverage | Observations | Status |",
        "|---|---|---:|---:|---:|---:|---:|---|",
    ]
    for factor in candidates:
        score = ic_scores.get(factor.id, {})
        status = "selected" if factor.id in selected_ids else str(score.get("status") or "rejected")
        lines.append(
            "| "
            f"`{factor.id}` | {factor.family} | {_fmt(score.get('rank_ic'))} | "
            f"{_fmt(score.get('ir'))} | {_fmt(score.get('stability_score'))} | "
            f"{_fmt(score.get('coverage_pct'))} | {score.get('observations') or 0} | {status} |"
        )
    lines.extend(["", f"## Selected Factors ({len(selected_ids)})", ""])
    if usable_selection:
        for factor in selected:
            lines.append(f"- `{factor.id}` ({factor.family}): {factor.description}")
    else:
        lines.append(
            "- No factor met the usable IC/IR/coverage/observation threshold; the draft spec "
            "uses fallback catalog factors for manual inspection only."
        )
    lines.extend(_oos_summary_lines(selected, oos_summary))
    lines.extend(_thesis_alignment_lines(thesis, candidates, selected, ic_scores))
    lines.extend(_factor_rejection_lines(candidates, selected, ic_scores))
    if evidence_summary.warnings:
        lines.extend(["", "## Warnings", ""])
        lines.extend(f"- {item}" for item in evidence_summary.warnings)
    if evidence_summary.blockers:
        lines.extend(["", "## Blockers", ""])
        lines.extend(f"- {item}" for item in evidence_summary.blockers)
    lines.extend(
        [
            "",
            "## Next Actions",
            "",
            f"- Review `{spec_path}` before promotion.",
            f"- Re-run `oc strategy evidence {spec_path}` after manual edits.",
            "- Treat sample, fixture, fallback, or research replay cache outputs as "
            "workflow evidence only.",
        ]
    )
    report_path = run_dir / "report.md"
    report_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return report_path


def _oos_summary_lines(
    selected: list[FactorDefinition],
    oos_summary: dict[str, Any],
) -> list[str]:
    factors = oos_summary.get("factors")
    if not isinstance(factors, dict):
        return []
    lines = ["", "## OOS Check", ""]
    lines.append(
        f"- Split: `{oos_summary.get('split') or 'unknown'}`, "
        f"forward bars: `{oos_summary.get('forward_bars') or 'unknown'}`"
    )
    lines.append("")
    lines.append("| Factor | Train IC | Test IC | Train Obs | Test Obs | Sign Consistent |")
    lines.append("|---|---:|---:|---:|---:|---|")
    for factor in selected:
        row = factors.get(factor.id, {})
        if not isinstance(row, dict):
            continue
        lines.append(
            "| "
            f"`{factor.id}` | {_fmt(row.get('train_rank_ic'))} | "
            f"{_fmt(row.get('test_rank_ic'))} | {row.get('train_observations') or 0} | "
            f"{row.get('test_observations') or 0} | {row.get('sign_consistent')} |"
        )
    return lines


def _thesis_alignment_lines(
    thesis: str,
    candidates: list[FactorDefinition],
    selected: list[FactorDefinition],
    ic_scores: dict[str, dict[str, Any]],
) -> list[str]:
    required = _required_families_for_thesis(thesis)
    if not required:
        return []
    candidate_families = {factor.family for factor in candidates}
    selected_families = {factor.family for factor in selected}
    lines = ["", "## Thesis Alignment", ""]
    for family in required:
        family_candidates = [factor for factor in candidates if factor.family == family]
        family_selected = [factor for factor in selected if factor.family == family]
        if family not in candidate_families:
            lines.append(f"- `{family}`: no expressionable candidate was available.")
        elif family in selected_families:
            lines.append(
                f"- `{family}`: selected "
                + ", ".join(f"`{factor.id}`" for factor in family_selected)
                + "."
            )
        else:
            reasons = [
                f"`{factor.id}` ({_rejection_reason(ic_scores.get(factor.id, {}))})"
                for factor in family_candidates
            ]
            lines.append(
                f"- `{family}`: candidate present but not selected: " + "; ".join(reasons) + "."
            )
    return lines


def _factor_rejection_lines(
    candidates: list[FactorDefinition],
    selected: list[FactorDefinition],
    ic_scores: dict[str, dict[str, Any]],
) -> list[str]:
    selected_ids = {factor.id for factor in selected}
    rejected = [factor for factor in candidates if factor.id not in selected_ids]
    if not rejected:
        return []
    lines = ["", "## Factor Rejections", ""]
    for factor in rejected:
        score = ic_scores.get(factor.id, {})
        lines.append(f"- `{factor.id}` ({factor.family}): {_rejection_reason(score)}.")
    return lines


def _required_families_for_thesis(thesis: str) -> list[str]:
    text = thesis.lower()
    families: list[str] = []
    for triggers, family in _THESIS_FAMILY_ASSERTIONS:
        if any(trigger in text for trigger in triggers) and family not in families:
            families.append(family)
    return families


def _rejection_reason(score: dict[str, Any]) -> str:
    diagnosis = score.get("rank_ic_diagnosis")
    if diagnosis:
        return f"rank IC unavailable: {diagnosis}"
    rank_ic = _float_or_none(score.get("rank_ic"))
    ir = _float_or_none(score.get("ir"))
    observations = int(score.get("observations") or 0)
    coverage = _float_or_none(score.get("coverage_pct")) or 0.0
    status = str(score.get("status") or "unknown")
    if rank_ic is None:
        return f"rank IC unavailable: {status}"
    if observations < 30:
        return f"insufficient observations ({observations})"
    if coverage < 70:
        return f"low coverage ({coverage:.1f}%)"
    if abs(rank_ic) < _MIN_ABS_RANK_IC_FOR_SIGNAL:
        return (
            f"rank_ic below selection threshold ({rank_ic:.4f} < {_MIN_ABS_RANK_IC_FOR_SIGNAL:.2f})"
        )
    if ir is None:
        return "IR unavailable"
    if ir < _MIN_IR_FOR_SELECTION:
        return f"IR below selection threshold ({ir:.3f} < {_MIN_IR_FOR_SELECTION:.2f})"
    if ir is None:
        return f"weaker selection score; rank_ic={rank_ic:.4f}, coverage={coverage:.1f}%"
    return f"weaker selection score; rank_ic={rank_ic:.4f}, ir={ir:.3f}, coverage={coverage:.1f}%"


def _summarize_auto_evidence(evidence: Any) -> _AutoEvidenceSummary:
    raw_status = str(getattr(evidence, "status", "unknown") or "unknown")
    research_report = getattr(evidence, "research_report", None)
    report_payload = _read_json(getattr(research_report, "json_path", None))
    control = getattr(evidence, "control", None)
    control_state = getattr(control, "state", None)
    control_state = control_state if isinstance(control_state, dict) else {}
    promotion_state = _dict(control_state.get("promotion_state"))
    promotion_status = _optional_str(
        promotion_state.get("status") or _dict(report_payload.get("promotion")).get("status")
    )
    paper_readiness_status = _optional_str(
        _dict(report_payload.get("paper_readiness")).get("status")
    )

    blockers: list[str] = []
    warnings: list[str] = []

    for item in _list(report_payload.get("checklist")):
        if not isinstance(item, dict):
            continue
        status = str(item.get("status") or "unknown")
        name = str(item.get("name") or "unknown_check")
        if status == "ok":
            continue
        message = _auto_check_message(item)
        if status == "warning" or _auto_check_is_exploration_warning(item):
            warnings.append(f"{name}: {message}")
        else:
            blockers.append(f"{name}: {message}")

    strict_data = _dict(promotion_state.get("strict_data"))
    for check_name in [str(item) for item in _list(promotion_state.get("blocked_checks"))]:
        if check_name == "strict_data" and _strict_data_is_workflow_only(strict_data):
            warnings.append(
                "promotion: strict_data is workflow-only sample/fixture/cache evidence; "
                "not paper-ready"
            )
        else:
            blockers.append(f"promotion: {check_name}")
    for item in _list(control_state.get("blocked_items")):
        text = str(item)
        if text.startswith("promotion:strict_data") and _strict_data_is_workflow_only(strict_data):
            warnings.append(_clip(text, 180))
        elif text:
            blockers.append(text)
    warnings.extend(str(item) for item in _list(control_state.get("warning_items")) if item)

    blockers = _dedupe(blockers)
    warnings = _dedupe(warnings)
    if blockers:
        status = "blocked"
    elif warnings or raw_status != "ok":
        status = "warning"
    else:
        status = "ok"
    return _AutoEvidenceSummary(
        research_status=status,
        raw_status=raw_status,
        promotion_status=promotion_status,
        paper_readiness_status=paper_readiness_status,
        blockers=blockers,
        warnings=warnings,
    )


def _auto_check_is_exploration_warning(item: dict[str, Any]) -> bool:
    name = str(item.get("name") or "")
    evidence = item.get("evidence")
    if name == "paper_gap":
        return True
    if name == "data_quality":
        return _data_evidence_is_workflow_only(evidence)
    if name == "factor_diagnostics":
        text = str(evidence or "")
        return "factor_lab_status=warning" in text
    return False


def _auto_check_message(item: dict[str, Any]) -> str:
    evidence = item.get("evidence")
    if isinstance(evidence, dict):
        warnings = [str(value) for value in _list(evidence.get("warnings"))]
        if warnings:
            return "; ".join(warnings[:2])
        status = evidence.get("status")
        if status:
            return f"status={status}"
    return str(evidence or item.get("status") or "no detail")


def _data_evidence_is_workflow_only(evidence: Any) -> bool:
    if not isinstance(evidence, dict):
        return False
    tokens = [
        evidence.get("data_source"),
        evidence.get("data_source_mode"),
        evidence.get("evidence_level"),
        evidence.get("acquisition_tier"),
    ]
    text = " ".join(str(item).lower() for item in tokens if item)
    return any(token in text for token in ["sample", "fixture", "fallback", "cache"])


def _strict_data_is_workflow_only(strict_data: dict[str, Any]) -> bool:
    details = _dict(strict_data.get("details"))
    message = str(strict_data.get("message") or "")
    return _data_evidence_is_workflow_only(details) or any(
        token in message.lower() for token in ["sample", "fixture", "fallback", "cache"]
    )


def _read_json(path: Any) -> dict[str, Any]:
    if path is None:
        return {}
    json_path = Path(path)
    if not json_path.exists():
        return {}
    try:
        payload = json.loads(json_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _optional_str(value: Any) -> str | None:
    return str(value) if value is not None and str(value) else None


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _clip(value: str, limit: int) -> str:
    text = str(value).strip()
    return text if len(text) <= limit else text[: max(limit - 3, 0)].rstrip() + "..."


def _factors_for_family_or_alias(family: str) -> list[FactorDefinition]:
    direct = list_factors(family=family, expression_only=True)
    if direct:
        return direct
    fallbacks = {
        "drawdown_guard": lambda factor: "drawdown" in factor.id or factor.family == "risk_regime",
        "overnight_gap": lambda factor: "overnight" in factor.id or "gap" in factor.id,
        "volatility_rank": lambda factor: (
            "volatility" in factor.id or "atr" in factor.id or "bollinger" in factor.id
        ),
        "breadth_canary": lambda factor: "breadth" in factor.id or "canary" in factor.id,
    }
    predicate = fallbacks.get(family)
    if predicate:
        return [factor for factor in list_factors(expression_only=True) if predicate(factor)]
    return []


def _factor_matches_required_family(factor: FactorDefinition, required_family: str) -> bool:
    if factor.family == required_family:
        return True
    if required_family == "drawdown_guard":
        return "drawdown" in factor.id
    if required_family == "overnight_gap":
        return "overnight" in factor.id or "gap" in factor.id
    if required_family == "volatility_rank":
        return "volatility" in factor.id or "atr" in factor.id or "bollinger" in factor.id
    return False


def _factor_signal_name(factor: FactorDefinition) -> str:
    return re.sub(r"\W+", "_", factor.id).strip("_") + "_signal"


def _market_capability(data_source: str, timeframe: str) -> str:
    if data_source == "sample" and timeframe == "daily":
        return "market.synthetic_daily_long"
    if data_source == "sample":
        return "market.sample_ohlcv"
    if data_source == "alpaca":
        return "market.alpaca_bars"
    if data_source == "longbridge":
        return "market.longbridge_bars"
    return "market.sample_ohlcv"


def _check_data_source_available(data_source: str) -> tuple[bool, str]:
    if data_source == "sample":
        return True, ""
    if data_source == "alpaca":
        if not (alpaca_api_key_id() and alpaca_api_secret_key()):
            return False, "ALPACA_API_KEY_ID / ALPACA_API_SECRET_KEY not configured"
        return True, ""
    if data_source == "longbridge":
        keys = ["LONGBRIDGE_APP_KEY", "LONGBRIDGE_APP_SECRET", "LONGBRIDGE_ACCESS_TOKEN"]
        missing = [key for key in keys if not os.getenv(key)]
        if missing:
            return False, f"Longbridge env missing: {','.join(missing)}"
        return True, ""
    return False, f"unknown data_source: {data_source}"


def _sample_data_path_for_symbol(symbol: str, base: Path) -> str:
    candidate = f"data/sample/{symbol.lower()}_daily.csv"
    if (base / candidate).exists():
        return candidate
    return "data/sample/syn_daily.csv"


def _make_run_id(thesis: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", thesis.lower()).strip("_")[:48] or "research"
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"{stamp}_{slug}"


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _fmt(value: Any) -> str:
    number = _float_or_none(value)
    return "n/a" if number is None else f"{number:.4f}"


def _float_or_none(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number:
        return None
    return number


def _is_scalar(value: Any) -> bool:
    return value is None or isinstance(value, str | int | float | bool)


def _relpath(path: Path, base: Path) -> str:
    try:
        return path.resolve().relative_to(base.resolve()).as_posix()
    except ValueError:
        return path.as_posix()
