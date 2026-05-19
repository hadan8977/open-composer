from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from open_composer.adapters.execution.nautilus_trader import nautilus_trader_available
from open_composer.config import (
    alpaca_api_base_url,
    alpaca_api_key_id,
    alpaca_api_secret_key,
    alpaca_paper_enabled,
    ensure_dir,
    project_root,
)
from open_composer.feature_packets import inspect_feature_packet
from open_composer.models.paper import PaperAccountSnapshot, PaperKillSwitch
from open_composer.models.strategy_spec import StrategySpec, load_strategy_spec
from open_composer.storage import write_json
from open_composer.strategy_capabilities import (
    assess_strategy_capabilities_for_spec,
)
from open_composer.timeframes import require_paper_ready_timeframe

PaperReadinessStatus = Literal["ok", "warning", "blocked"]


class PaperStrategyReadinessCheck(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    status: PaperReadinessStatus
    message: str
    details: dict[str, object] = Field(default_factory=dict)
    suggested_actions: list[str] = Field(default_factory=list)


class PaperStrategyReadinessReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    strategy_name: str
    strategy_path: str | None = None
    status: PaperReadinessStatus
    ready: bool
    gate_summary: dict[str, object] = Field(default_factory=dict)
    checks: list[PaperStrategyReadinessCheck] = Field(default_factory=list)
    report_json_path: str | None = None
    report_markdown_path: str | None = None

    @property
    def blocking_checks(self) -> list[PaperStrategyReadinessCheck]:
        return [check for check in self.checks if check.status == "blocked"]


def assess_paper_strategy_readiness(
    spec_ref: str | Path,
    root: Path | None = None,
) -> PaperStrategyReadinessReport:
    base = root or project_root()
    path = Path(spec_ref)
    if not path.exists():
        for folder in ["active", "approved", "drafts", "retired"]:
            candidate = base / "strategy_specs" / folder / f"{spec_ref}.yaml"
            if candidate.exists():
                path = candidate
                break
    spec = load_strategy_spec(path)
    return assess_paper_strategy_readiness_for_spec(spec, base, spec_path=path)


def assess_paper_strategy_readiness_for_spec(
    spec: StrategySpec,
    root: Path | None = None,
    *,
    spec_path: Path | None = None,
) -> PaperStrategyReadinessReport:
    base = root or project_root()
    checks = [
        _lifecycle_check(spec),
        _execution_check(spec),
        _data_source_check(spec),
        _alpaca_env_check(spec),
        _kill_switch_check(base),
        _account_snapshot_check(base),
        _backend_check(spec),
        _portfolio_routing_check(spec),
        _portfolio_risk_check(spec),
        _feature_packet_binding_check(spec, base),
        _promotion_report_check(spec, base, spec_path),
    ]
    if spec_path is not None and spec_path.exists():
        checks.append(_capability_check(spec, spec_path))
    status = _overall_status(checks)
    return PaperStrategyReadinessReport(
        strategy_name=spec.name,
        strategy_path=_relpath(spec_path, base) if spec_path else None,
        status=status,
        ready=status != "blocked",
        gate_summary=_gate_summary(checks, status),
        checks=checks,
    )


def write_paper_readiness_report(
    report: PaperStrategyReadinessReport,
    root: Path | None = None,
    output_path: Path | None = None,
    markdown_path: Path | None = None,
) -> tuple[Path, Path]:
    base = root or project_root()
    json_path = output_path or (
        base / "reports" / "paper" / "readiness" / f"{report.strategy_name}.json"
    )
    md_path = markdown_path or json_path.with_suffix(".md")
    ensure_dir(json_path.parent)
    report.report_json_path = _relpath(json_path, base)
    report.report_markdown_path = _relpath(md_path, base)
    write_json(json_path, report)
    md_path.write_text(_render_markdown(report), encoding="utf-8")
    return json_path, md_path


def format_paper_readiness_blockers(report: PaperStrategyReadinessReport) -> str:
    if report.ready:
        return "paper strategy readiness passed"
    blockers = "; ".join(f"{check.name}: {check.message}" for check in report.blocking_checks)
    return f"paper strategy readiness blocked: {blockers}"


def _lifecycle_check(spec: StrategySpec) -> PaperStrategyReadinessCheck:
    if spec.lifecycle == "active":
        return PaperStrategyReadinessCheck(
            name="lifecycle",
            status="ok",
            message="Strategy is active.",
            details={"lifecycle": spec.lifecycle},
        )
    return PaperStrategyReadinessCheck(
        name="lifecycle",
        status="blocked",
        message="Paper automation requires lifecycle=active.",
        details={"lifecycle": spec.lifecycle},
        suggested_actions=[
            f"uv run oc strategy approve {spec.name}",
            (
                f"uv run oc strategy activate {spec.name} --paper-auto --allow-paper-auto "
                "--data-source alpaca --enforce-paper-readiness"
            ),
        ],
    )


def _execution_check(spec: StrategySpec) -> PaperStrategyReadinessCheck:
    problems: list[str] = []
    if spec.execution.mode != "paper_auto":
        problems.append("execution.mode must be paper_auto")
    if spec.execution.broker != "alpaca_paper":
        problems.append("execution.broker must be alpaca_paper")
    if problems:
        return PaperStrategyReadinessCheck(
            name="execution",
            status="blocked",
            message="; ".join(problems),
            details={
                "mode": spec.execution.mode,
                "broker": spec.execution.broker,
                "backend": spec.execution.backend,
            },
            suggested_actions=[
                (
                    f"uv run oc strategy activate {spec.name} --paper-auto --allow-paper-auto "
                    "--data-source alpaca --enforce-paper-readiness"
                )
            ],
        )
    if spec.execution.backend != "nautilus_trader":
        return PaperStrategyReadinessCheck(
            name="execution",
            status="warning",
            message="paper_auto is configured but backend is not nautilus_trader.",
            details={
                "mode": spec.execution.mode,
                "broker": spec.execution.broker,
                "backend": spec.execution.backend,
            },
            suggested_actions=[
                (
                    f"uv run oc strategy activate {spec.name} --paper-auto --allow-paper-auto "
                    "--data-source alpaca --enforce-paper-readiness"
                )
            ],
        )
    return PaperStrategyReadinessCheck(
        name="execution",
        status="ok",
        message="Execution mode, broker, and backend are paper-ready.",
        details={
            "mode": spec.execution.mode,
            "broker": spec.execution.broker,
            "backend": spec.execution.backend,
        },
    )


def _data_source_check(spec: StrategySpec) -> PaperStrategyReadinessCheck:
    if spec.data.source in {"alpaca", "longbridge"}:
        try:
            require_paper_ready_timeframe(spec.data.source, spec.timeframe)
        except ValueError as exc:
            return PaperStrategyReadinessCheck(
                name="data_source",
                status="blocked",
                message=str(exc),
                details={
                    "source": spec.data.source,
                    "symbol": spec.primary_symbol,
                    "timeframe": spec.timeframe,
                },
                suggested_actions=[
                    "Choose a provider-supported timeframe or change data.source before paper."
                ],
            )
        return PaperStrategyReadinessCheck(
            name="data_source",
            status="ok",
            message="Paper automation uses a live/cache market data source.",
            details={
                "source": spec.data.source,
                "symbol": spec.primary_symbol,
                "timeframe": spec.timeframe,
                "data_mode": "paper_ready",
            },
        )
    return PaperStrategyReadinessCheck(
        name="data_source",
        status="blocked",
        message="paper_auto orders require data.source=alpaca or longbridge, not sample.",
        details={"source": spec.data.source, "symbol": spec.primary_symbol},
        suggested_actions=[
            (
                f"uv run oc strategy activate {spec.name} --paper-auto --allow-paper-auto "
                "--data-source alpaca --enforce-paper-readiness"
            ),
            (
                f"uv run oc strategy activate {spec.name} --paper-auto --allow-paper-auto "
                "--data-source longbridge --enforce-paper-readiness"
            ),
        ],
    )


def _alpaca_env_check(spec: StrategySpec) -> PaperStrategyReadinessCheck:
    if spec.execution.broker != "alpaca_paper":
        return PaperStrategyReadinessCheck(
            name="alpaca_env",
            status="blocked",
            message="Paper readiness currently targets broker=alpaca_paper.",
            details={"broker": spec.execution.broker},
            suggested_actions=[
                (
                    f"uv run oc strategy activate {spec.name} --paper-auto --allow-paper-auto "
                    "--data-source alpaca --enforce-paper-readiness"
                )
            ],
        )
    missing = [
        name
        for name, value in {
            "ALPACA_API_KEY_ID": alpaca_api_key_id(),
            "ALPACA_API_SECRET_KEY": alpaca_api_secret_key(),
        }.items()
        if not value
    ]
    if not alpaca_paper_enabled():
        missing.append("ALPACA_PAPER=true")
    if missing:
        return PaperStrategyReadinessCheck(
            name="alpaca_env",
            status="blocked",
            message="Missing Alpaca Paper environment: " + ", ".join(missing),
            details={
                "missing": missing,
                "paper_enabled": alpaca_paper_enabled(),
                "base_url": alpaca_api_base_url(),
            },
            suggested_actions=[
                "Set ALPACA_API_KEY_ID and ALPACA_API_SECRET_KEY in .env.",
                "Set ALPACA_PAPER=true before enabling paper automation.",
                "uv run oc doctor",
                "uv run oc deploy prepare",
            ],
        )
    return PaperStrategyReadinessCheck(
        name="alpaca_env",
        status="ok",
        message="Alpaca Paper environment is configured.",
        details={"paper_enabled": alpaca_paper_enabled(), "base_url": alpaca_api_base_url()},
    )


def _kill_switch_check(root: Path) -> PaperStrategyReadinessCheck:
    kill_switch = _load_kill_switch(root)
    if kill_switch.enabled:
        return PaperStrategyReadinessCheck(
            name="kill_switch",
            status="blocked",
            message="Paper kill switch is enabled.",
            details={
                "reason": kill_switch.reason,
                "updated_at": kill_switch.updated_at.isoformat(),
            },
            suggested_actions=[
                'uv run oc paper kill-switch --disable --reason "ready to resume paper automation"'
            ],
        )
    return PaperStrategyReadinessCheck(
        name="kill_switch",
        status="ok",
        message="Paper kill switch is clear.",
    )


def _account_snapshot_check(root: Path) -> PaperStrategyReadinessCheck:
    account = _load_account_snapshot(root)
    if account is None:
        return PaperStrategyReadinessCheck(
            name="account_snapshot",
            status="warning",
            message="No paper account snapshot found; run oc paper sync-account before automation.",
            details={"path": "reports/paper/account.json"},
            suggested_actions=["uv run oc paper sync-account"],
        )
    return PaperStrategyReadinessCheck(
        name="account_snapshot",
        status="ok",
        message="Paper account snapshot is available.",
        details={
            "generated_at": account.generated_at.isoformat(),
            "equity": account.equity,
            "cash": account.cash,
            "buying_power": account.buying_power,
        },
    )


def _backend_check(spec: StrategySpec) -> PaperStrategyReadinessCheck:
    installed = nautilus_trader_available()
    if spec.execution.backend == "nautilus_trader" and not installed:
        return PaperStrategyReadinessCheck(
            name="nautilus_backend",
            status="blocked",
            message="nautilus_trader package is required for the target paper backend.",
            details={"backend": spec.execution.backend, "nautilus_installed": installed},
            suggested_actions=["uv sync", "uv run oc doctor", "uv run oc deploy prepare"],
        )
    return PaperStrategyReadinessCheck(
        name="nautilus_backend",
        status="ok" if installed else "warning",
        message=(
            "NautilusTrader package is available."
            if installed
            else "NautilusTrader is unavailable; paper runner will not have backend parity."
        ),
        details={"backend": spec.execution.backend, "nautilus_installed": installed},
    )


def _portfolio_routing_check(spec: StrategySpec) -> PaperStrategyReadinessCheck:
    if len(spec.universe) <= 1:
        return PaperStrategyReadinessCheck(
            name="portfolio_routing",
            status="ok",
            message="Single-symbol paper routing is supported.",
            details={"universe": spec.universe},
        )
    if spec.portfolio.mode in {"adaptive_intraday_internal_router", "hybrid_adaptive_router"}:
        missing: list[str] = []
        if not spec.portfolio.selected_route_label:
            missing.append("selected_route_label")
        if not spec.portfolio.max_symbols_per_day:
            missing.append("max_symbols_per_day")
        if not spec.portfolio.gross_exposure_limit:
            missing.append("gross_exposure_limit")
        if missing:
            return PaperStrategyReadinessCheck(
                name="portfolio_routing",
                status="blocked",
                message=f"{spec.portfolio.mode} portfolio routing is missing: "
                + ", ".join(missing),
                details=spec.portfolio.model_dump(mode="json"),
                suggested_actions=[
                    "Set portfolio.selected_route_label, max_symbols_per_day, and "
                    "gross_exposure_limit before paper review."
                ],
            )
        return PaperStrategyReadinessCheck(
            name="portfolio_routing",
            status="ok",
            message=f"{spec.portfolio.mode} portfolio routing is declared inside StrategySpec.",
            details=spec.portfolio.model_dump(mode="json") | {"universe": spec.universe},
        )
    return PaperStrategyReadinessCheck(
        name="portfolio_routing",
        status="blocked",
        message="Multi-symbol paper automation needs portfolio or target-weight routing first.",
        details={"universe": spec.universe},
        suggested_actions=[
            (
                "Use a single-symbol StrategySpec for paper_auto until portfolio routing "
                "is implemented."
            )
        ],
    )


def _portfolio_risk_check(spec: StrategySpec) -> PaperStrategyReadinessCheck:
    portfolio = spec.portfolio
    if portfolio.mode in {"adaptive_intraday_internal_router", "hybrid_adaptive_router"}:
        gross_limit = portfolio.gross_exposure_limit or (
            (portfolio.max_symbols_per_day or 0)
            * (portfolio.max_symbol_weight or spec.risk.max_position_weight)
        )
        max_symbol_weight = portfolio.max_symbol_weight or spec.risk.max_position_weight
        details = {
            "universe": spec.universe,
            "mode": portfolio.mode,
            "gross_exposure_limit_pct": round(gross_limit * 100, 4),
            "single_name_weight_limit_pct": round(max_symbol_weight * 100, 4),
            "max_symbols_per_day": portfolio.max_symbols_per_day,
            "same_day_flatten": portfolio.same_day_flatten,
            "duplicate_signal_policy": portfolio.duplicate_signal_policy,
            "sector_concentration": "bounded_by_max_symbols_and_weight; sector map not registered",
            "borrow_short_caveat": "long-only paper routing; borrow is out of scope",
        }
        problems: list[str] = []
        if gross_limit <= 0 or gross_limit > 1:
            problems.append("gross_exposure_limit must be within (0, 1]")
        if max_symbol_weight <= 0 or max_symbol_weight > spec.risk.max_position_weight:
            problems.append("max_symbol_weight must not exceed risk.max_position_weight")
        if portfolio.mode == "adaptive_intraday_internal_router" and not portfolio.same_day_flatten:
            problems.append("same_day_flatten must be true for intraday router paper review")
        if (
            portfolio.max_symbols_per_day
            and gross_limit < portfolio.max_symbols_per_day * max_symbol_weight
        ):
            details["effective_weight_note"] = (
                "gross limit is tighter than max_symbols_per_day * max_symbol_weight; "
                "scanner will equalize down to the gross limit"
            )
        if problems:
            return PaperStrategyReadinessCheck(
                name="portfolio_risk",
                status="blocked",
                message="; ".join(problems),
                details=details,
                suggested_actions=["Tighten StrategySpec portfolio risk before activation."],
            )
        return PaperStrategyReadinessCheck(
            name="portfolio_risk",
            status="ok",
            message=f"{portfolio.mode} gross exposure and concentration limits are explicit.",
            details=details,
        )
    details = {
        "universe": spec.universe,
        "gross_exposure_limit_pct": round(
            spec.risk.max_position_weight * len(spec.universe) * 100, 4
        ),
        "single_name_weight_limit_pct": round(spec.risk.max_position_weight * 100, 4),
        "sector_concentration": "unknown_until_sector_map_is_registered",
        "turnover_limit": "not_declared",
        "capacity_limit": "not_declared",
        "borrow_short_caveat": "long-only paper routing; borrow is out of scope",
    }
    if len(spec.universe) <= 1:
        return PaperStrategyReadinessCheck(
            name="portfolio_risk",
            status="ok",
            message="Single-symbol portfolio risk envelope is explicit.",
            details=details,
        )
    return PaperStrategyReadinessCheck(
        name="portfolio_risk",
        status="blocked",
        message="Multi-symbol paper requires gross/net exposure and concentration limits.",
        details=details,
        suggested_actions=[
            "Keep paper_auto single-symbol or add a portfolio risk policy before activation."
        ],
    )


def _feature_packet_binding_check(
    spec: StrategySpec,
    root: Path,
) -> PaperStrategyReadinessCheck:
    missing: list[str] = []
    incomplete: list[str] = []
    missing_evidence: list[str] = []
    inspected: list[dict[str, object]] = []
    for name, factor in spec.factors.items():
        if factor.source not in {"llm_feature", "feature_packet"}:
            continue
        if not factor.path:
            missing.append(f"{name}: missing packet path")
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
        if not inspection.exists:
            missing.append(f"{name}: packet not found at {factor.path}")
        elif inspection.point_in_time_status != "complete":
            warning_text = "; ".join(inspection.replay_warnings[:3]) or "not PIT complete"
            incomplete.append(
                f"{name}: {inspection.point_in_time_status} at {factor.path}: {warning_text}"
            )
        elif inspection.missing_evidence_count:
            missing_evidence.append(
                f"{name}: {inspection.missing_evidence_count} packet row(s) at "
                f"{factor.path} lack marginal-lift evidence"
            )
    if missing:
        return PaperStrategyReadinessCheck(
            name="feature_packets",
            status="blocked",
            message="Paper feature factors require saved replay packets: " + "; ".join(missing),
            details={"missing": missing, "inspected": inspected},
            suggested_actions=[
                (
                    "Write point-in-time packets with uv run oc feature write or "
                    "uv run oc feature from-context."
                )
            ],
        )
    if incomplete:
        return PaperStrategyReadinessCheck(
            name="feature_packets",
            status="blocked",
            message="Paper feature factors require PIT-complete replay packets: "
            + "; ".join(incomplete),
            details={"incomplete": incomplete, "inspected": inspected},
            suggested_actions=["uv run oc feature validate"],
        )
    if missing_evidence:
        return PaperStrategyReadinessCheck(
            name="feature_packets",
            status="blocked",
            message="Paper feature factors require single-modality baseline, marginal lift, "
            "and missing-modality robustness evidence: " + "; ".join(missing_evidence),
            details={"missing_evidence": missing_evidence, "inspected": inspected},
            suggested_actions=[
                "Add feature packet evidence before promotion or paper_auto activation."
            ],
        )
    return PaperStrategyReadinessCheck(
        name="feature_packets",
        status="ok",
        message="Feature packet bindings are point-in-time complete.",
        details={"inspected": inspected},
    )


def _promotion_report_check(
    spec: StrategySpec,
    root: Path,
    spec_path: Path | None,
) -> PaperStrategyReadinessCheck:
    report_path = root / "reports" / "research" / f"{spec.name}-promotion.json"
    suggested_spec = str(spec_path) if spec_path is not None else spec.name
    if not report_path.exists():
        return PaperStrategyReadinessCheck(
            name="promotion_report",
            status="blocked",
            message="Paper automation requires a promotion report before activation.",
            details={"path": str(report_path)},
            suggested_actions=[
                (
                    f"uv run oc strategy promotion-report {suggested_spec} "
                    "--oos-ratio 0.3 --walk-forward-folds 3"
                )
            ],
        )
    try:
        raw = json.loads(report_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return PaperStrategyReadinessCheck(
            name="promotion_report",
            status="blocked",
            message="Promotion report exists but is not valid JSON.",
            details={"path": str(report_path)},
            suggested_actions=[f"uv run oc strategy promotion-report {suggested_spec}"],
        )
    if not isinstance(raw, dict):
        return PaperStrategyReadinessCheck(
            name="promotion_report",
            status="blocked",
            message="Promotion report is malformed.",
            details={"path": str(report_path)},
        )
    ready = bool(raw.get("ready", False))
    status = str(raw.get("status", "warning"))
    checks = raw.get("checks", []) if isinstance(raw.get("checks"), list) else []
    checks_by_name = {
        str(check.get("name")): str(check.get("status"))
        for check in checks
        if isinstance(check, dict)
    }
    gate_summary = raw.get("gate_summary", {}) if isinstance(raw.get("gate_summary"), dict) else {}
    benchmark_family = (
        raw.get("benchmark_family", {}) if isinstance(raw.get("benchmark_family"), dict) else {}
    )
    research_manifest = (
        raw.get("research_manifest", {}) if isinstance(raw.get("research_manifest"), dict) else {}
    )
    missing_requirements = _promotion_missing_requirements(
        ready=ready,
        status=status,
        checks_by_name=checks_by_name,
        gate_summary=gate_summary,
        benchmark_family=benchmark_family,
        research_manifest=research_manifest,
    )
    if not missing_requirements:
        return PaperStrategyReadinessCheck(
            name="promotion_report",
            status="ok",
            message="Promotion report is present and ready for paper review.",
            details={
                "path": str(report_path),
                "status": status,
                "ready": ready,
                "check_count": len(checks),
                "gate_summary": gate_summary,
                "benchmark_family_complete": benchmark_family.get("complete"),
            },
        )
    return PaperStrategyReadinessCheck(
        name="promotion_report",
        status="blocked",
        message="Promotion report is present but not ready for paper: "
        + "; ".join(missing_requirements),
        details={
            "path": str(report_path),
            "status": status,
            "ready": ready,
            "missing_requirements": missing_requirements,
            "gate_summary": gate_summary,
            "benchmark_family_complete": benchmark_family.get("complete"),
        },
        suggested_actions=[f"uv run oc strategy promotion-report {suggested_spec}"],
    )


def _promotion_missing_requirements(
    *,
    ready: bool,
    status: str,
    checks_by_name: dict[str, str],
    gate_summary: dict[str, object],
    benchmark_family: dict[str, object],
    research_manifest: dict[str, object],
) -> list[str]:
    missing: list[str] = []
    if not ready:
        missing.append("ready=false")
    if status != "ok":
        missing.append(f"status={status}")
    if gate_summary.get("paper_ready_pass") is not True:
        missing.append("gate_summary.paper_ready_pass is not true")
    for check_name in [
        "strict_data",
        "feature_packets",
        "benchmark_family",
        "factor_lab",
        "execution_reality",
        "alternative_data",
    ]:
        if checks_by_name.get(check_name) != "ok":
            missing.append(f"{check_name} check is not ok")
    if not research_manifest.get("research_contract_path"):
        missing.append("research contract path is missing")
    if benchmark_family.get("complete") is not True:
        missing.append("benchmark_family.complete is not true")
    return missing


def _capability_check(spec: StrategySpec, spec_path: Path) -> PaperStrategyReadinessCheck:
    report = assess_strategy_capabilities_for_spec(spec, spec_path)
    finding = report.finding("alpaca_paper_execution")
    status: PaperReadinessStatus
    if finding.status == "supported":
        status = "ok"
    elif finding.status == "partial":
        status = "warning"
    else:
        status = "blocked"
    return PaperStrategyReadinessCheck(
        name="capability_report",
        status=status,
        message="; ".join(finding.reasons),
        details={"capability": finding.capability, "status": finding.status},
        suggested_actions=[f"uv run oc spec capabilities {spec_path}"],
    )


def _overall_status(checks: list[PaperStrategyReadinessCheck]) -> PaperReadinessStatus:
    if any(check.status == "blocked" for check in checks):
        return "blocked"
    if any(check.status == "warning" for check in checks):
        return "warning"
    return "ok"


def _gate_summary(
    checks: list[PaperStrategyReadinessCheck],
    status: PaperReadinessStatus,
) -> dict[str, object]:
    blocked = [check.name for check in checks if check.status == "blocked"]
    warning = [check.name for check in checks if check.status == "warning"]
    return {
        "workflow_pass": "lifecycle" not in blocked and "execution" not in blocked,
        "research_pass": "promotion_report" not in blocked,
        "llm_contribution_pass": None,
        "paper_ready_pass": status != "blocked",
        "blocked_checks": blocked,
        "warning_checks": warning,
    }


def _render_markdown(report: PaperStrategyReadinessReport) -> str:
    lines = [
        f"# Paper Strategy Readiness: {report.strategy_name}",
        "",
        f"- Generated at: `{report.generated_at.isoformat()}`",
        f"- Strategy path: `{report.strategy_path or 'candidate'}`",
        f"- Status: `{report.status}`",
        f"- Ready: `{'yes' if report.ready else 'no'}`",
        "- Gate taxonomy: workflow_pass, research_pass, llm_contribution_pass, paper_ready_pass.",
        f"- Gate summary: `{report.gate_summary}`",
        "- Safety note: paper readiness is a control gate for Alpaca Paper only, not live trading.",
        "",
        "## Checks",
        "",
    ]
    for check in report.checks:
        lines.append(f"### {check.name}")
        lines.append("")
        lines.append(f"- Status: `{check.status}`")
        lines.append(f"- Message: {check.message}")
        if check.details:
            lines.append(f"- Details: `{check.details}`")
        if check.suggested_actions:
            lines.append("- Suggested actions:")
            lines.extend(f"  - `{action}`" for action in check.suggested_actions)
        lines.append("")
    return "\n".join(lines)


def _load_kill_switch(root: Path) -> PaperKillSwitch:
    path = root / "reports" / "paper" / "kill_switch.json"
    if not path.exists():
        return PaperKillSwitch()
    return PaperKillSwitch.model_validate_json(path.read_text(encoding="utf-8"))


def _load_account_snapshot(root: Path) -> PaperAccountSnapshot | None:
    path = root / "reports" / "paper" / "account.json"
    if not path.exists():
        return None
    return PaperAccountSnapshot.model_validate_json(path.read_text(encoding="utf-8"))


def _resolve_path(root: Path, value: str) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return root / path


def _relpath(path: Path | None, base: Path) -> str | None:
    if path is None:
        return None
    try:
        return path.relative_to(base).as_posix()
    except ValueError:
        return path.as_posix()
