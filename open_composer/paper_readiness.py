from __future__ import annotations

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
from open_composer.models.paper import PaperAccountSnapshot, PaperKillSwitch
from open_composer.models.strategy_spec import StrategySpec, load_strategy_spec
from open_composer.storage import write_json
from open_composer.strategy_capabilities import assess_strategy_capabilities

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
        _feature_packet_binding_check(spec, base),
    ]
    if spec_path is not None and spec_path.exists():
        checks.append(_capability_check(spec_path))
    status = _overall_status(checks)
    return PaperStrategyReadinessReport(
        strategy_name=spec.name,
        strategy_path=_relpath(spec_path, base) if spec_path else None,
        status=status,
        ready=status != "blocked",
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
    report.report_json_path = str(json_path)
    report.report_markdown_path = str(md_path)
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
        return PaperStrategyReadinessCheck(
            name="data_source",
            status="ok",
            message="Paper automation uses a live/cache market data source.",
            details={"source": spec.data.source, "symbol": spec.primary_symbol},
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


def _feature_packet_binding_check(
    spec: StrategySpec,
    root: Path,
) -> PaperStrategyReadinessCheck:
    missing: list[str] = []
    for name, factor in spec.factors.items():
        if factor.source not in {"llm_feature", "feature_packet"}:
            continue
        if not factor.path:
            missing.append(f"{name}: missing packet path")
            continue
        path = _resolve_path(root, factor.path)
        if not path.exists():
            missing.append(f"{name}: packet not found at {factor.path}")
    if missing:
        return PaperStrategyReadinessCheck(
            name="feature_packets",
            status="blocked",
            message="Paper feature factors require saved replay packets: " + "; ".join(missing),
            details={"missing": missing},
            suggested_actions=[
                (
                    "Write point-in-time packets with uv run oc feature write or "
                    "uv run oc feature from-context."
                )
            ],
        )
    return PaperStrategyReadinessCheck(
        name="feature_packets",
        status="ok",
        message="No missing feature packet bindings.",
    )


def _capability_check(spec_path: Path) -> PaperStrategyReadinessCheck:
    report = assess_strategy_capabilities(spec_path)
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


def _render_markdown(report: PaperStrategyReadinessReport) -> str:
    lines = [
        f"# Paper Strategy Readiness: {report.strategy_name}",
        "",
        f"- Generated at: `{report.generated_at.isoformat()}`",
        f"- Strategy path: `{report.strategy_path or 'candidate'}`",
        f"- Status: `{report.status}`",
        f"- Ready: `{'yes' if report.ready else 'no'}`",
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
        return str(path.relative_to(base))
    except ValueError:
        return str(path)
