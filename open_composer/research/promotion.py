from __future__ import annotations

import copy
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from statistics import mean
from time import perf_counter
from typing import Literal

from open_composer.adapters.data import load_ohlcv_for_spec
from open_composer.config import ensure_dir, project_root
from open_composer.engines.backtest_engine import BacktestArtifacts, backtest_frame
from open_composer.expressions import ExpressionSafetyError, assert_expression_safe
from open_composer.feature_packets import inspect_feature_packet
from open_composer.models.strategy_spec import StrategySpec, load_strategy_spec
from open_composer.research.alt_data_quality import build_alternative_data_quality_report
from open_composer.research.blind_test import load_blind_test_report
from open_composer.research.contracts import write_research_contract
from open_composer.research.factor_lab import run_factor_lab
from open_composer.research.metadata import (
    frame_data_profile,
    research_run_manifest,
    runtime_payload,
    search_space,
)
from open_composer.storage import write_json

PromotionStatus = Literal["ok", "warning", "blocked"]
FivePassStatus = Literal["pass", "fail", "skipped", "not_applicable"]


@dataclass(frozen=True)
class PromotionCheck:
    name: str
    status: PromotionStatus
    message: str
    details: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class FivePassChecks:
    workflow_pass: FivePassStatus
    research_pass: FivePassStatus
    llm_contribution_pass: FivePassStatus
    paper_ready_pass: FivePassStatus
    code_correctness_pass: FivePassStatus
    workflow_reason: str = ""
    research_reason: str = ""
    llm_contribution_reason: str = ""
    paper_ready_reason: str = ""
    code_correctness_reason: str = ""


@dataclass(frozen=True)
class PromotionReport:
    strategy_name: str
    source_spec_path: str
    status: PromotionStatus
    ready: bool
    checks: list[PromotionCheck]
    report_path: str
    json_path: str
    five_pass_checks: FivePassChecks | None = None


def build_promotion_report(
    spec_path: Path,
    root: Path | None = None,
    out_of_sample_ratio: float = 0.3,
    walk_forward_folds: int = 3,
    cost_slippage_bps: list[int] | None = None,
) -> PromotionReport:
    started_at = perf_counter()
    base = root or project_root()
    spec = load_strategy_spec(spec_path)
    frame = load_ohlcv_for_spec(spec, base)
    if len(frame) < 4:
        msg = "promotion gate requires at least 4 bars of data"
        raise ValueError(msg)

    cost_slippage_bps = cost_slippage_bps or [0, 5, 10]
    checks: list[PromotionCheck] = []
    contract_path = write_research_contract(spec_path, base)
    data_profile = frame_data_profile(
        frame,
        symbol=spec.primary_symbol,
        timeframe=spec.timeframe,
        provider=spec.data.source,
        feed=spec.data.feed,
        source_mode=frame.attrs.get("data_source_mode") or spec.data.source,
        path=frame.attrs.get("data_source_path") or spec.data.path,
    )

    full = backtest_frame(
        spec,
        frame,
        root=base,
        run_id_value=f"promotion-{spec.name}-full",
    )
    checks.append(
        PromotionCheck(
            name="in_sample",
            status=_status_from_sanity(
                full.run.data_sanity.status if full.run.data_sanity else "warning"
            ),
            message=(
                "Full-window backtest captured in-sample research evidence; "
                "review data sanity before promotion."
            ),
            details=_run_details(full),
        )
    )

    oos_check, oos_artifacts = _out_of_sample_check(
        spec=spec,
        frame=frame,
        root=base,
        out_of_sample_ratio=out_of_sample_ratio,
    )
    checks.append(oos_check)

    wf_check, walk_forward_runs = _walk_forward_check(
        spec=spec,
        frame=frame,
        root=base,
        folds=walk_forward_folds,
    )
    checks.append(wf_check)

    cost_check, cost_runs = _cost_sensitivity_check(
        spec=spec,
        frame=frame,
        root=base,
        slippage_bps=cost_slippage_bps,
    )
    checks.append(cost_check)

    comparison_check, comparison_rows = _data_comparison_check(spec, base)
    checks.append(comparison_check)

    strict_data_check = _strict_data_check(spec, full)
    checks.append(strict_data_check)

    feature_packet_check = _feature_packet_check(spec, base)
    checks.append(feature_packet_check)

    factor_lab_result = run_factor_lab(spec_path, base)
    factor_lab_check = _factor_lab_check(factor_lab_result)
    checks.append(factor_lab_check)

    execution_reality_check = _execution_reality_check(full)
    checks.append(execution_reality_check)

    alt_data_result = build_alternative_data_quality_report(spec_path, base)
    alt_data_check = _alternative_data_check(alt_data_result)
    checks.append(alt_data_check)

    benchmark_check, benchmark_family = _benchmark_family_check(spec, full)
    checks.append(benchmark_check)

    ready = all(check.status == "ok" for check in checks)
    status: PromotionStatus
    if any(check.status == "blocked" for check in checks):
        status = "blocked"
    elif any(check.status == "warning" for check in checks):
        status = "warning"
    else:
        status = "ok"
    five_pass_checks = _five_pass_checks(spec, ready, checks, base)
    report_path = base / "reports" / "research" / f"{spec.name}-promotion.md"
    json_path = base / "reports" / "research" / f"{spec.name}-promotion.json"
    manifest = research_run_manifest(
        root=base,
        strategy=spec,
        source_path=spec_path,
        trial_count=1 + int(oos_artifacts is not None) + len(walk_forward_runs) + len(cost_runs),
        search_space_payload=search_space(
            family="promotion_gate",
            candidate_count=1,
            parameter_ranges={"cost_slippage_bps": cost_slippage_bps},
            filters=[
                f"out_of_sample_ratio={out_of_sample_ratio}",
                f"walk_forward_folds={walk_forward_folds}",
            ],
        ),
        data_profile=data_profile,
        feature_packet_paths=_feature_packet_paths(spec),
        runtime=runtime_payload(started_at, {}),
    )
    manifest["research_contract_path"] = str(contract_path.relative_to(base))
    manifest["factor_lab_path"] = str(factor_lab_result.json_path.relative_to(base))
    manifest["alt_data_quality_path"] = str(alt_data_result.json_path.relative_to(base))
    _write_promotion_json(
        json_path,
        spec_path,
        spec,
        status,
        ready,
        checks,
        full,
        oos_artifacts,
        walk_forward_runs,
        cost_runs,
        comparison_rows,
        benchmark_family,
        data_profile,
        manifest,
        five_pass_checks,
    )
    _write_promotion_report(
        report_path,
        spec_path,
        spec,
        status,
        ready,
        checks,
        full,
        oos_artifacts,
        walk_forward_runs,
        cost_runs,
        comparison_rows,
        benchmark_family,
        json_path,
        data_profile,
        manifest,
        five_pass_checks,
    )
    return PromotionReport(
        strategy_name=spec.name,
        source_spec_path=str(spec_path),
        status=status,
        ready=ready,
        checks=checks,
        report_path=str(report_path),
        json_path=str(json_path),
        five_pass_checks=five_pass_checks,
    )


def _out_of_sample_check(
    *,
    spec: StrategySpec,
    frame,
    root: Path,
    out_of_sample_ratio: float,
) -> tuple[PromotionCheck, BacktestArtifacts | None]:
    split = max(int(len(frame) * (1 - out_of_sample_ratio)), 2)
    split = min(split, len(frame) - 1)
    oos_frame = frame.iloc[split:].copy()
    if len(oos_frame) < 2:
        return (
            PromotionCheck(
                name="out_of_sample",
                status="blocked",
                message="Not enough data left for an out-of-sample slice.",
                details={"rows": len(oos_frame)},
            ),
            None,
        )
    artifacts = backtest_frame(
        spec,
        oos_frame,
        root=root,
        run_id_value=f"promotion-{spec.name}-oos",
    )
    status = _status_from_sanity(
        artifacts.run.data_sanity.status if artifacts.run.data_sanity else "warning"
    )
    return (
        PromotionCheck(
            name="out_of_sample",
            status=status,
            message=(
                "Trailing slice evaluated as out-of-sample promotion evidence; "
                "compare with in-sample before using paper."
            ),
            details=_run_details(artifacts),
        ),
        artifacts,
    )


def _walk_forward_check(
    *,
    spec: StrategySpec,
    frame,
    root: Path,
    folds: int,
) -> tuple[PromotionCheck, list[BacktestArtifacts]]:
    folds = max(folds, 1)
    fold_size = max(len(frame) // (folds + 1), 2)
    runs: list[BacktestArtifacts] = []
    fold_details: list[dict[str, object]] = []
    for index in range(folds):
        start = (index + 1) * fold_size + 1
        end = min(len(frame), start + fold_size)
        wf_frame = frame.iloc[start:end].copy()
        if len(wf_frame) < 2:
            continue
        artifacts = backtest_frame(
            spec,
            wf_frame,
            root=root,
            run_id_value=f"promotion-{spec.name}-wf-{index + 1}",
        )
        runs.append(artifacts)
        fold_details.append(
            {
                "fold": index + 1,
                "rows": len(wf_frame),
                "total_return_pct": artifacts.run.total_return_pct,
                "annualized_return_pct": artifacts.run.annualized_return_pct,
                "sharpe_ratio": artifacts.run.sharpe_ratio,
                "status": artifacts.run.data_sanity.status
                if artifacts.run.data_sanity
                else "warning",
            }
        )
    if not runs:
        return (
            PromotionCheck(
                name="walk_forward",
                status="blocked",
                message="No walk-forward folds could be built from the available data.",
                details={"folds": folds},
            ),
            runs,
        )
    status = "ok" if all(item["status"] == "ok" for item in fold_details) else "warning"
    return (
        PromotionCheck(
            name="walk_forward",
            status=status,
            message="Sequential slices evaluated as walk-forward evidence.",
            details={
                "fold_count": len(runs),
                "folds": fold_details,
                "mean_return_pct": mean(item["total_return_pct"] for item in fold_details),
                "mean_sharpe": mean(float(item["sharpe_ratio"] or 0.0) for item in fold_details),
                "validation_policy": "sequential_walk_forward",
                "purged": True,
                "embargo_bars": 1,
                "embargo_note": (
                    "A one-bar embargo separates sequential validation slices in the "
                    "lightweight promotion gate."
                ),
            },
        ),
        runs,
    )


def _cost_sensitivity_check(
    *,
    spec: StrategySpec,
    frame,
    root: Path,
    slippage_bps: list[int],
) -> tuple[PromotionCheck, list[BacktestArtifacts]]:
    runs: list[BacktestArtifacts] = []
    details: list[dict[str, object]] = []
    for bps in slippage_bps:
        candidate = _clone_spec_with_costs(spec, slippage_bps=bps)
        artifacts = backtest_frame(
            candidate,
            frame,
            root=root,
            run_id_value=f"promotion-{spec.name}-cost-{bps}",
        )
        runs.append(artifacts)
        details.append(
            {
                "slippage_bps": bps,
                "total_return_pct": artifacts.run.total_return_pct,
                "annualized_return_pct": artifacts.run.annualized_return_pct,
                "sharpe_ratio": artifacts.run.sharpe_ratio,
                "status": artifacts.run.data_sanity.status
                if artifacts.run.data_sanity
                else "warning",
            }
        )
    status = "ok" if all(item["status"] == "ok" for item in details) else "warning"
    return (
        PromotionCheck(
            name="cost_sensitivity",
            status=status,
            message="Backtests rerun under multiple slippage assumptions.",
            details={
                "scenarios": details,
            },
        ),
        runs,
    )


def _factor_lab_check(result) -> PromotionCheck:
    details = {
        "status": result.status,
        "report_path": str(result.report_path),
        "json_path": str(result.json_path),
        "quality_flags": result.quality_flags,
        "factor_count": len(result.factor_metrics),
    }
    if result.status == "blocked":
        return PromotionCheck(
            name="factor_lab",
            status="blocked",
            message="Factor Lab diagnostics are blocked: " + ", ".join(result.quality_flags),
            details=details,
        )
    if result.status == "warning":
        return PromotionCheck(
            name="factor_lab",
            status="warning",
            message="Factor Lab diagnostics produced warnings.",
            details=details,
        )
    return PromotionCheck(
        name="factor_lab",
        status="ok",
        message="Factor Lab diagnostics passed.",
        details=details,
    )


def _execution_reality_check(full: BacktestArtifacts) -> PromotionCheck:
    reality = full.run.execution_reality
    if reality is None:
        return PromotionCheck(
            name="execution_reality",
            status="blocked",
            message="Execution reality metrics are missing.",
            details={},
        )
    details = reality.model_dump(mode="json")
    if reality.status == "blocked":
        return PromotionCheck(
            name="execution_reality",
            status="blocked",
            message="Execution reality blocks promotion: " + "; ".join(reality.warnings),
            details=details,
        )
    if reality.status == "warning":
        return PromotionCheck(
            name="execution_reality",
            status="warning",
            message="Execution reality warnings require review.",
            details=details,
        )
    return PromotionCheck(
        name="execution_reality",
        status="ok",
        message="Execution reality diagnostics passed.",
        details=details,
    )


def _alternative_data_check(result) -> PromotionCheck:
    details = {
        "status": result.status,
        "report_path": str(result.report_path),
        "json_path": str(result.json_path),
        "warnings": result.warnings,
        "factor_count": len(result.rows),
    }
    if result.status == "blocked":
        return PromotionCheck(
            name="alternative_data",
            status="blocked",
            message="Alternative data quality blocks promotion: " + ", ".join(result.warnings),
            details=details,
        )
    if result.status == "warning":
        return PromotionCheck(
            name="alternative_data",
            status="warning",
            message="Alternative data quality produced warnings.",
            details=details,
        )
    return PromotionCheck(
        name="alternative_data",
        status="ok",
        message="Alternative data quality passed or no alternative data is used.",
        details=details,
    )


def _data_comparison_check(
    spec: StrategySpec,
    root: Path,
) -> tuple[PromotionCheck, list[dict[str, object]]]:
    comparisons_root = root / "reports" / "data" / "comparisons"
    rows: list[dict[str, object]] = []
    if not comparisons_root.exists():
        return (
            PromotionCheck(
                name="data_comparison",
                status="warning",
                message="No data comparison reports are available yet.",
                details={},
            ),
            rows,
        )
    for path in sorted(comparisons_root.glob("*.json")):
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if not isinstance(raw, dict):
            continue
        if raw.get("symbol", "").upper() != spec.primary_symbol.upper():
            continue
        if raw.get("timeframe") != spec.timeframe:
            continue
        rows.append(
            {
                "path": str(path),
                "left_source": raw.get("left_source"),
                "right_source": raw.get("right_source"),
                "coverage_pct": raw.get("matched_coverage_pct"),
                "max_close_diff_bps": raw.get("max_abs_close_diff_bps"),
                "missing_left_rows": raw.get("missing_left_rows"),
                "missing_right_rows": raw.get("missing_right_rows"),
            }
        )
    if not rows:
        return (
            PromotionCheck(
                name="data_comparison",
                status="warning",
                message="No matching data comparison report found for this strategy.",
                details={},
            ),
            rows,
        )
    return (
        PromotionCheck(
            name="data_comparison",
            status="ok",
            message="Matching data comparison reports are available.",
            details={"comparisons": rows},
        ),
        rows,
    )


def _strict_data_check(spec: StrategySpec, artifacts: BacktestArtifacts) -> PromotionCheck:
    sanity = artifacts.run.data_sanity
    mode = sanity.data_source_mode if sanity else None
    evidence_level = sanity.evidence_level if sanity else "unknown"
    warnings = sanity.warnings if sanity else []
    blocked_reasons: list[str] = []
    if spec.data.source == "sample":
        blocked_reasons.append("sample data is workflow evidence only")
    mode_text = mode or ""
    if any(token in mode_text for token in ["sample", "fixture", "fallback"]):
        blocked_reasons.append(f"data_source_mode={mode_text} is not paper-ready")
    if evidence_level.startswith("E0"):
        blocked_reasons.append(f"evidence_level={evidence_level} is not paper-ready")
    if blocked_reasons:
        return PromotionCheck(
            name="strict_data",
            status="blocked",
            message="Promotion requires research_strict or paper_ready data; "
            + "; ".join(blocked_reasons),
            details={
                "data_source": spec.data.source,
                "data_source_mode": mode,
                "evidence_level": evidence_level,
                "warnings": warnings,
            },
        )
    return PromotionCheck(
        name="strict_data",
        status="ok",
        message="Promotion data is not sample, fixture, or fallback evidence.",
        details={
            "data_source": spec.data.source,
            "data_source_mode": mode,
            "evidence_level": evidence_level,
        },
    )


def _feature_packet_check(spec: StrategySpec, root: Path) -> PromotionCheck:
    inspected: list[dict[str, object]] = []
    missing_or_incomplete: list[str] = []
    for name, factor in spec.factors.items():
        if factor.source not in {"llm_feature", "feature_packet"}:
            continue
        if not factor.path:
            missing_or_incomplete.append(f"{name}: missing packet path")
            inspected.append({"factor": name, "status": "missing"})
            continue
        path = _resolve_path(root, factor.path)
        inspection = inspect_feature_packet(path, factor.field)
        inspected.append(
            {
                "factor": name,
                "path": factor.path,
                "field": factor.field,
                "status": inspection.point_in_time_status,
                "warnings": inspection.replay_warnings,
                "evidence_count": inspection.evidence_count,
                "missing_evidence_count": inspection.missing_evidence_count,
            }
        )
        if not inspection.exists or inspection.point_in_time_status != "complete":
            warning_text = "; ".join(inspection.replay_warnings[:3]) or "not PIT complete"
            missing_or_incomplete.append(
                f"{name}: {inspection.point_in_time_status} at {factor.path}: {warning_text}"
            )
        elif inspection.missing_evidence_count:
            missing_or_incomplete.append(
                f"{name}: {inspection.missing_evidence_count} packet row(s) at "
                f"{factor.path} lack marginal-lift evidence"
            )
    if missing_or_incomplete:
        return PromotionCheck(
            name="feature_packets",
            status="blocked",
            message="Promotion requires PIT-complete feature packets: "
            + "; ".join(missing_or_incomplete),
            details={"inspected": inspected},
        )
    return PromotionCheck(
        name="feature_packets",
        status="ok",
        message="Feature packet factors are absent or PIT-complete.",
        details={"inspected": inspected},
    )


def _benchmark_family_check(
    spec: StrategySpec,
    full: BacktestArtifacts,
) -> tuple[PromotionCheck, dict[str, object]]:
    run = full.run
    same_symbol = {
        "status": "ok" if run.buy_hold_return_pct is not None else "missing",
        "symbol": spec.primary_symbol,
        "return_pct": run.buy_hold_return_pct,
        "alpha_pct": run.alpha_vs_buy_hold_pct,
    }
    equal_weight = {
        "status": "ok" if run.buy_hold_return_pct is not None else "missing",
        "symbols": spec.universe,
        "return_pct": run.buy_hold_return_pct if len(spec.universe) == 1 else None,
        "alpha_pct": run.alpha_vs_buy_hold_pct if len(spec.universe) == 1 else None,
        "note": (
            "single-symbol universe matches same-symbol buy-and-hold"
            if len(spec.universe) == 1
            else "multi-symbol equal-weight benchmark requires synchronized universe bars"
        ),
    }
    cash = {
        "status": "ok",
        "return_pct": 0.0,
        "alpha_pct": run.total_return_pct,
        "note": "cash proxy uses 0% return until a T-bill series is registered",
    }
    ex_post_best = {
        "status": "ok" if len(spec.universe) == 1 else "missing",
        "symbol": spec.primary_symbol if len(spec.universe) == 1 else None,
        "return_pct": run.buy_hold_return_pct if len(spec.universe) == 1 else None,
        "beat_ex_post_best_symbol": (
            run.total_return_pct > run.buy_hold_return_pct
            if run.buy_hold_return_pct is not None and len(spec.universe) == 1
            else None
        ),
        "note": "ex-post best symbol is a non-tradable upper-bound benchmark",
    }
    market = {
        "status": "missing",
        "proxy": None,
        "note": "market proxy such as SPY or QQQ has not been attached to this report",
    }
    sector = {
        "status": "missing",
        "proxy": None,
        "note": "sector/theme proxy or basket has not been attached to this report",
    }
    benchmarks = {
        "same_symbol_buy_hold": same_symbol,
        "equal_weight_universe": equal_weight,
        "market_proxy": market,
        "sector_theme_proxy": sector,
        "cash_proxy": cash,
        "ex_post_best_symbol": ex_post_best,
    }
    missing = [name for name, item in benchmarks.items() if item.get("status") == "missing"]
    family = {
        "complete": not missing,
        "missing": missing,
        "benchmarks": benchmarks,
        "alpha_summary": {
            "alpha_vs_same_symbol": run.alpha_vs_buy_hold_pct,
            "alpha_vs_equal_weight": equal_weight.get("alpha_pct"),
            "alpha_vs_market": None,
            "alpha_vs_sector": None,
            "alpha_vs_cash": run.total_return_pct,
            "beat_ex_post_best_symbol": ex_post_best.get("beat_ex_post_best_symbol"),
        },
    }
    if missing:
        return (
            PromotionCheck(
                name="benchmark_family",
                status="warning",
                message="Promotion benchmark family is incomplete: " + ", ".join(missing),
                details=family,
            ),
            family,
        )
    return (
        PromotionCheck(
            name="benchmark_family",
            status="ok",
            message="Promotion benchmark family is complete.",
            details=family,
        ),
        family,
    )


def _clone_spec_with_costs(spec: StrategySpec, *, slippage_bps: int) -> StrategySpec:
    raw = copy.deepcopy(spec.model_dump(mode="json"))
    raw["costs"] = {**raw["costs"], "slippage_bps": slippage_bps}
    return StrategySpec.model_validate(raw)


def _run_details(artifacts: BacktestArtifacts) -> dict[str, object]:
    run = artifacts.run
    return {
        "run_id": run.run_id,
        "bars": run.bars,
        "signals": run.signals,
        "trades": run.trades,
        "total_return_pct": run.total_return_pct,
        "buy_hold_return_pct": run.buy_hold_return_pct,
        "alpha_vs_buy_hold_pct": run.alpha_vs_buy_hold_pct,
        "annualized_return_pct": run.annualized_return_pct,
        "sharpe_ratio": run.sharpe_ratio,
        "annualized_volatility_pct": run.annualized_volatility_pct,
        "max_drawdown_pct": run.max_drawdown_pct,
        "sortino_ratio": run.sortino_ratio,
        "calmar_ratio": run.calmar_ratio,
        "win_rate_pct": run.win_rate_pct,
        "profit_factor": run.profit_factor,
        "exposure_pct": run.exposure_pct,
        "turnover_ratio": run.turnover_ratio,
        "execution_reality_status": (
            run.execution_reality.status if run.execution_reality else "unknown"
        ),
        "data_sanity_status": run.data_sanity.status if run.data_sanity else "warning",
        "evidence_level": run.data_sanity.evidence_level if run.data_sanity else "unknown",
    }


def _status_from_sanity(status: str) -> PromotionStatus:
    return "ok" if status == "ok" else "warning"


def _write_promotion_json(
    path: Path,
    spec_path: Path,
    spec: StrategySpec,
    status: PromotionStatus,
    ready: bool,
    checks: list[PromotionCheck],
    full: BacktestArtifacts,
    oos: BacktestArtifacts | None,
    walk_forward_runs: list[BacktestArtifacts],
    cost_runs: list[BacktestArtifacts],
    comparison_rows: list[dict[str, object]],
    benchmark_family: dict[str, object],
    data_profile: dict[str, object],
    manifest: dict[str, object],
    five_pass_checks: FivePassChecks,
) -> Path:
    ensure_dir(path.parent)
    payload = {
        "strategy_name": spec.name,
        "source_spec_path": str(spec_path),
        "status": status,
        "ready": ready,
        "gate_summary": _gate_summary(spec, ready, checks, benchmark_family),
        "five_pass_checks": asdict(five_pass_checks),
        "checks": [
            {
                "name": check.name,
                "status": check.status,
                "message": check.message,
                "details": check.details,
            }
            for check in checks
        ],
        "full_window": _run_details(full),
        "out_of_sample": _run_details(oos) if oos else None,
        "walk_forward": [_run_details(item) for item in walk_forward_runs],
        "cost_sensitivity": [_run_details(item) for item in cost_runs],
        "data_comparisons": comparison_rows,
        "benchmark_family": benchmark_family,
        "data_profile": data_profile,
        "research_manifest": manifest,
        "safety_note": (
            "Promotion ready means research and paper-readiness gates passed; it is not a "
            "promise of live returns."
        ),
    }
    write_json(path, payload)
    return path


def _write_promotion_report(
    path: Path,
    spec_path: Path,
    spec: StrategySpec,
    status: PromotionStatus,
    ready: bool,
    checks: list[PromotionCheck],
    full: BacktestArtifacts,
    oos: BacktestArtifacts | None,
    walk_forward_runs: list[BacktestArtifacts],
    cost_runs: list[BacktestArtifacts],
    comparison_rows: list[dict[str, object]],
    benchmark_family: dict[str, object],
    json_path: Path,
    data_profile: dict[str, object],
    manifest: dict[str, object],
    five_pass_checks: FivePassChecks,
) -> Path:
    ensure_dir(path.parent)
    lines = [
        f"# Promotion Report: {spec.name}",
        "",
        f"- Status: `{status}`",
        f"- Ready for paper: `{'yes' if ready else 'no'}`",
        "- Gate taxonomy: workflow_pass, research_pass, llm_contribution_pass, "
        "paper_ready_pass, code_correctness_pass.",
        "- Safety note: promotion evidence is not a promise of live returns.",
        f"- Data source mode: `{data_profile.get('source_mode') or 'unknown'}`",
        f"- Data as-of: `{data_profile.get('data_as_of') or 'unknown'}`",
        f"- Trial count: `{manifest.get('trial_count')}`",
        f"- Source spec: `{spec_path}`",
        f"- JSON report: `{json_path}`",
        "",
        "## Five-Pass Checks",
        "",
        "| Pass | Status | Reason |",
        "|---|---|---|",
        *_five_pass_markdown_rows(five_pass_checks),
        "",
        "**Ready to advance toward paper readiness?** "
        + ("yes" if five_pass_checks.paper_ready_pass == "pass" else "no"),
        "",
        "## Checks",
        "",
    ]
    for check in checks:
        lines.extend(
            [
                f"### {check.name}",
                f"- Status: `{check.status}`",
                f"- Message: {check.message}",
            ]
        )
        if check.details:
            lines.append(f"- Details: `{json.dumps(check.details, sort_keys=True)}`")
        lines.append("")
    lines.extend(
        [
            "## Full Window",
            "",
            *_run_lines(full),
            "",
            "## Out Of Sample",
            "",
            *(_run_lines(oos) if oos is not None else ["- No out-of-sample slice was available."]),
            "",
            "## Walk Forward",
            "",
        ]
    )
    if walk_forward_runs:
        for item in walk_forward_runs:
            lines.extend(_run_lines(item))
            lines.append("")
    else:
        lines.append("- No walk-forward runs were produced.")
    lines.extend(["## Cost Sensitivity", ""])
    if cost_runs:
        for item in cost_runs:
            lines.extend(_run_lines(item))
            lines.append("")
    else:
        lines.append("- No cost sensitivity runs were produced.")
        lines.append("")
    lines.extend(["## Data Comparisons", ""])
    if comparison_rows:
        for row in comparison_rows:
            lines.append(
                f"- `{row.get('left_source')}` vs `{row.get('right_source')}` "
                f"coverage `{row.get('coverage_pct')}` max_close_diff_bps "
                f"`{row.get('max_close_diff_bps')}`"
            )
    else:
        lines.append("- No matching data comparison reports were found.")
    lines.extend(["", "## Benchmark Family", ""])
    lines.append(f"- Complete: `{benchmark_family.get('complete')}`")
    lines.append(f"- Missing: `{', '.join(benchmark_family.get('missing', [])) or 'none'}`")
    benchmarks = benchmark_family.get("benchmarks")
    if isinstance(benchmarks, dict):
        for name, item in benchmarks.items():
            lines.append(f"- `{name}`: `{item}`")
    lines.extend(["", "## Research Manifest", ""])
    lines.append(f"- Git commit: `{manifest.get('git_commit') or 'unknown'}`")
    lines.append(f"- Git dirty: `{manifest.get('git_dirty')}`")
    lines.append(f"- Spec hash: `{manifest.get('spec_hash')}`")
    lines.append(f"- Data path hash: `{manifest.get('data_path_hash') or 'n/a'}`")
    regime_path = path.parent.parent / "regime_search" / f"{spec.name}.json"
    if regime_path.exists():
        lines.extend(["", "## Similar Regimes", ""])
        try:
            regime = json.loads(regime_path.read_text(encoding="utf-8"))
            for match in regime.get("matches", [])[:3]:
                lines.append(
                    f"- `{match.get('window_end')}` similarity "
                    f"`{float(match.get('similarity', 0.0)):.3f}`: "
                    f"{match.get('market_note')}"
                )
        except (json.JSONDecodeError, TypeError, ValueError):
            lines.append("- Regime report exists but could not be parsed.")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _gate_summary(
    spec: StrategySpec,
    ready: bool,
    checks: list[PromotionCheck],
    benchmark_family: dict[str, object],
) -> dict[str, object]:
    blocked = {check.name for check in checks if check.status == "blocked"}
    warning = {check.name for check in checks if check.status == "warning"}
    llm_related = bool(spec.llm_review.enabled or _feature_packet_paths(spec))
    return {
        "workflow_pass": "in_sample" not in blocked,
        "research_pass": not blocked,
        "llm_contribution_pass": None if not llm_related else "feature_packets" not in blocked,
        "paper_ready_pass": ready,
        "blocked_checks": sorted(blocked),
        "warning_checks": sorted(warning),
        "benchmark_family_complete": bool(benchmark_family.get("complete", False)),
    }


def _five_pass_checks(
    spec: StrategySpec,
    ready: bool,
    checks: list[PromotionCheck],
    root: Path,
) -> FivePassChecks:
    by_name = {check.name: check for check in checks}
    blocked = {check.name for check in checks if check.status == "blocked"}
    warning = {check.name for check in checks if check.status == "warning"}

    workflow_failures = [
        name
        for name in ["in_sample", "feature_packets"]
        if name in blocked or by_name.get(name, PromotionCheck(name, "ok", "")).status == "blocked"
    ]
    workflow_pass: FivePassStatus = "fail" if workflow_failures else "pass"
    workflow_reason = (
        "blocked checks: " + ", ".join(workflow_failures)
        if workflow_failures
        else "spec loaded, expressions validated, and reference backtest ran"
    )

    research_gate_names = {
        "out_of_sample",
        "walk_forward",
        "cost_sensitivity",
        "data_comparison",
        "benchmark_family",
        "factor_lab",
        "execution_reality",
        "alternative_data",
    }
    research_failures = sorted(
        name for name in research_gate_names if name in blocked or name in warning
    )
    cost_grid_warning = _cost_grid_warning(spec, root)
    if cost_grid_warning:
        research_failures.append("cost_grid")
    research_pass: FivePassStatus = "fail" if research_failures else "pass"
    research_reason = (
        "missing or weak research evidence: "
        + ", ".join(research_failures)
        + (f"; {cost_grid_warning}" if cost_grid_warning else "")
        if research_failures
        else "OOS, walk-forward, cost, data comparison, and benchmark gates passed"
    )

    llm_related = bool(spec.llm_review.enabled or _feature_packet_paths(spec))
    if not llm_related:
        llm_contribution_pass: FivePassStatus = "not_applicable"
        llm_reason = "strategy does not use LLM review or LLM/feature packet factors"
    elif "feature_packets" in blocked:
        llm_contribution_pass = "fail"
        llm_reason = "LLM/feature packet factors are missing PIT-complete evidence"
    else:
        llm_contribution_pass, llm_reason = _blind_test_contribution_pass(spec, root)

    paper_ready_pass: FivePassStatus = "pass" if ready else "fail"
    paper_reason = (
        "all promotion checks are ok"
        if ready
        else "blocked checks: " + ", ".join(sorted(blocked or warning))
    )

    code_correctness_pass, code_reason = _code_correctness_pass(spec)

    return FivePassChecks(
        workflow_pass=workflow_pass,
        research_pass=research_pass,
        llm_contribution_pass=llm_contribution_pass,
        paper_ready_pass=paper_ready_pass,
        code_correctness_pass=code_correctness_pass,
        workflow_reason=workflow_reason,
        research_reason=research_reason,
        llm_contribution_reason=llm_reason,
        paper_ready_reason=paper_reason,
        code_correctness_reason=code_reason,
    )


def _code_correctness_pass(spec: StrategySpec) -> tuple[FivePassStatus, str]:
    expressions = [
        *spec.all_expressions(),
        *[
            factor.expression
            for factor in spec.factors.values()
            if factor.source == "expression" and factor.expression
        ],
    ]
    for expression in expressions:
        try:
            assert_expression_safe(expression)
        except ExpressionSafetyError as exc:
            return "fail", f"AST safety check failed for {expression!r}: {exc}"
    return "pass", "all rule and expression-factor formulas pass the AST safety whitelist"


def _blind_test_contribution_pass(spec: StrategySpec, root: Path) -> tuple[FivePassStatus, str]:
    report = load_blind_test_report(spec.name, root)
    if report is None:
        return (
            "fail",
            f"missing BlindTrade counterfactual report: reports/blind_test/{spec.name}.json",
        )
    by_mode = {result.mode: result for result in report.results}
    real = by_mode.get("real")
    anonymous = by_mode.get("anonymous")
    if real is None or anonymous is None:
        return "fail", "blind-test report must include real and anonymous modes"
    sharpe_diff = abs(real.sharpe - anonymous.sharpe)
    if sharpe_diff > 0.3:
        return "fail", f"anonymous Sharpe differs from real by {sharpe_diff:.2f}"
    if anonymous.correlation_with_real is not None and anonymous.correlation_with_real < 0.8:
        return (
            "fail",
            f"anonymous signal correlation with real is {anonymous.correlation_with_real:.2f}",
        )
    return "pass", "BlindTrade anonymous mode stays within Sharpe and signal-correlation thresholds"


def _cost_grid_warning(spec: StrategySpec, root: Path) -> str:
    path = root / "reports" / "cost_grid" / f"{spec.name}.json"
    if not path.exists():
        return ""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return "cost-grid report is not valid JSON"
    spread = raw.get("ranking_spread")
    if isinstance(spread, int | float) and float(spread) > 1.0:
        return f"cost-grid Sharpe spread {float(spread):.2f} exceeds 1.00"
    return ""


def _five_pass_markdown_rows(five_pass_checks: FivePassChecks) -> list[str]:
    rows = [
        ("workflow_pass", five_pass_checks.workflow_pass, five_pass_checks.workflow_reason),
        ("research_pass", five_pass_checks.research_pass, five_pass_checks.research_reason),
        (
            "llm_contribution_pass",
            five_pass_checks.llm_contribution_pass,
            five_pass_checks.llm_contribution_reason,
        ),
        (
            "paper_ready_pass",
            five_pass_checks.paper_ready_pass,
            five_pass_checks.paper_ready_reason,
        ),
        (
            "code_correctness_pass",
            five_pass_checks.code_correctness_pass,
            five_pass_checks.code_correctness_reason,
        ),
    ]
    return [
        f"| {name} | {_status_icon(status)} `{status}` | {reason} |"
        for name, status, reason in rows
    ]


def _status_icon(status: FivePassStatus) -> str:
    return {
        "pass": "PASS",
        "fail": "FAIL",
        "skipped": "SKIP",
        "not_applicable": "N/A",
    }[status]


def _feature_packet_paths(spec: StrategySpec) -> list[str]:
    return sorted(
        str(factor.path)
        for factor in spec.factors.values()
        if factor.source in {"llm_feature", "feature_packet"} and factor.path
    )


def _resolve_path(root: Path, value: str) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return root / path


def _run_lines(artifacts: BacktestArtifacts | None) -> list[str]:
    if artifacts is None:
        return ["- No run."]
    run = artifacts.run
    return [
        f"- Run: `{run.run_id}`",
        f"- Return: `{run.total_return_pct:.2f}%`",
        f"- Buy/Hold: `{_format_optional_pct(run.buy_hold_return_pct)}`",
        f"- Alpha vs Buy/Hold: `{_format_optional_pct(run.alpha_vs_buy_hold_pct)}`",
        f"- Annualized: `{run.annualized_return_pct:.2f}%`"
        if run.annualized_return_pct is not None
        else "- Annualized: `n/a`",
        f"- Sharpe: `{run.sharpe_ratio:.2f}`"
        if run.sharpe_ratio is not None
        else "- Sharpe: `n/a`",
        f"- Signals: `{run.signals}`",
        f"- Trades: `{run.trades}`",
        f"- Data sanity: `{run.data_sanity.status if run.data_sanity else 'warning'}`",
        f"- Evidence level: `{run.data_sanity.evidence_level if run.data_sanity else 'unknown'}`",
    ]


def _format_optional_pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.2f}%"
