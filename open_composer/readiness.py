from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from open_composer.adapters.execution.nautilus_trader import nautilus_trader_available
from open_composer.config import dashboard_api_token, ensure_dir, project_root
from open_composer.dashboard.catalog import build_dashboard_catalog, build_feature_packet_records
from open_composer.paper_controls import build_paper_status
from open_composer.paper_readiness import assess_paper_strategy_readiness
from open_composer.storage import write_json

ReadinessStatus = Literal["ok", "warning", "blocked"]


class ReadinessCheck(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    status: ReadinessStatus
    message: str
    suggested_actions: list[str] = Field(default_factory=list)
    details: dict[str, object] = Field(default_factory=dict)


class ReadinessReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    source_root: str
    status: ReadinessStatus
    ready: bool
    checks: list[ReadinessCheck] = Field(default_factory=list)
    report_json_path: str | None = None
    report_markdown_path: str | None = None


def build_readiness_report(root: Path | None = None) -> ReadinessReport:
    base = root or project_root()
    checks: list[ReadinessCheck] = []

    sample_data_path = base / "data" / "sample" / "qqq_15m.csv"
    checks.append(
        ReadinessCheck(
            name="sample_data",
            status="ok" if sample_data_path.exists() else "blocked",
            message=(
                "Sample data is available for credential-free smoke tests."
                if sample_data_path.exists()
                else "Sample data is missing; bootstrap the repository before using workflows."
            ),
            suggested_actions=[] if sample_data_path.exists() else ["uv run oc doctor"],
            details={"path": str(sample_data_path)},
        )
    )

    catalog = None
    try:
        catalog = build_dashboard_catalog(base)
    except Exception as exc:
        checks.append(
            ReadinessCheck(
                name="dashboard_catalog",
                status="blocked",
                message=f"Dashboard catalog cannot be built: {exc}",
                suggested_actions=["uv run oc dashboard catalog", "make verify"],
            )
        )
    else:
        checks.append(
            ReadinessCheck(
                name="dashboard_catalog",
                status="ok",
                message="Dashboard catalog can be rebuilt from repository artifacts.",
                suggested_actions=[],
                details={
                    "strategies": catalog.summary.strategy_count,
                    "versions": catalog.summary.version_count,
                    "runs": catalog.summary.run_count,
                },
            )
        )

    serve_root = _resolve_dashboard_serve_root(base)
    checks.append(
        ReadinessCheck(
            name="dashboard_bundle",
            status="ok" if serve_root else "warning",
            message=(
                f"Dashboard bundle is available at {serve_root}."
                if serve_root
                else "Dashboard bundle is missing; run make dashboard-build or oc dashboard html."
            ),
            suggested_actions=[]
            if serve_root
            else ["make dashboard-build", "uv run oc dashboard html"],
            details={"serve_root": str(serve_root) if serve_root else None},
        )
    )

    token = dashboard_api_token()
    checks.append(
        ReadinessCheck(
            name="dashboard_api_auth",
            status="ok",
            message=(
                "Dashboard API token gate is configured."
                if token
                else (
                    "Dashboard API token gate is disabled; keep dashboard serve bound to localhost."
                )
            ),
            suggested_actions=[]
            if token
            else ["export OPEN_COMPOSER_DASHBOARD_TOKEN=<local-token>"],
            details={"token_configured": bool(token)},
        )
    )

    feature_packets = build_feature_packet_records(base)
    incomplete_packets = [
        packet for packet in feature_packets if packet.point_in_time_status != "complete"
    ]
    checks.append(
        ReadinessCheck(
            name="feature_packets",
            status="warning" if incomplete_packets else "ok",
            message=(
                f"{len(incomplete_packets)} feature packet file(s) need PIT metadata."
                if incomplete_packets
                else "Feature packets are absent or point-in-time complete."
            ),
            suggested_actions=["uv run oc feature validate"] if incomplete_packets else [],
            details={
                "packet_count": len(feature_packets),
                "incomplete_count": len(incomplete_packets),
                "incomplete_paths": [packet.path for packet in incomplete_packets],
            },
        )
    )

    paper_status = build_paper_status(base)
    paper_warnings: list[str] = []
    if paper_status.kill_switch.enabled:
        paper_warnings.append("paper kill switch is enabled")
    if paper_status.active_paper_auto_strategies and paper_status.account_equity is None:
        paper_warnings.append("active paper_auto strategies have no account snapshot")
    checks.append(
        ReadinessCheck(
            name="paper_monitor",
            status="warning" if paper_warnings else "ok",
            message=(
                "; ".join(paper_warnings)
                if paper_warnings
                else "Paper monitor artifacts are readable."
            ),
            suggested_actions=_paper_monitor_suggested_actions(paper_warnings),
            details={
                "active_paper_auto": paper_status.active_paper_auto_strategies,
                "kill_switch_enabled": paper_status.kill_switch.enabled,
                "open_orders": paper_status.open_order_count,
                "positions": paper_status.position_count,
                "alert_status": paper_status.alert_status,
            },
        )
    )

    if catalog is not None:
        paper_strategy_reports = []
        for strategy in catalog.strategies:
            if not (
                strategy.lifecycle == "active"
                and strategy.execution_mode == "paper_auto"
                and strategy.broker == "alpaca_paper"
                and strategy.source_paths
            ):
                continue
            report = assess_paper_strategy_readiness(base / strategy.source_paths[0], base)
            paper_strategy_reports.append(report)
        paper_strategy_status = _overall_status(
            [
                ReadinessCheck(
                    name=report.strategy_name,
                    status=report.status,
                    message=(
                        "paper strategy readiness passed"
                        if report.ready
                        else "; ".join(
                            f"{check.name}: {check.message}" for check in report.blocking_checks
                        )
                    ),
                    suggested_actions=[
                        action
                        for check in report.checks
                        if check.status in {"blocked", "warning"}
                        for action in check.suggested_actions
                    ],
                )
                for report in paper_strategy_reports
            ]
        )
        checks.append(
            ReadinessCheck(
                name="paper_strategy_readiness",
                status=paper_strategy_status,
                message=(
                    "No active paper_auto strategies are checked in."
                    if not paper_strategy_reports
                    else f"{len(paper_strategy_reports)} active paper_auto strategy readiness "
                    f"report(s) checked."
                ),
                suggested_actions=[],
                details={
                    "strategy_count": len(paper_strategy_reports),
                    "reports": [
                        {
                            "strategy_name": report.strategy_name,
                            "status": report.status,
                            "ready": report.ready,
                            "blocking_checks": [check.name for check in report.blocking_checks],
                        }
                        for report in paper_strategy_reports
                    ],
                },
            )
        )

        checked_strategies = [
            strategy
            for strategy in catalog.strategies
            if strategy.lifecycle in {"active", "approved"}
        ]
        backend_counts = {
            status: sum(1 for strategy in checked_strategies if strategy.backend_status == status)
            for status in sorted({strategy.backend_status for strategy in checked_strategies})
        }
        draft_backend_counts = {
            status: sum(
                1
                for strategy in catalog.strategies
                if strategy.lifecycle == "draft" and strategy.backend_status == status
            )
            for status in sorted(
                {
                    strategy.backend_status
                    for strategy in catalog.strategies
                    if strategy.lifecycle == "draft"
                }
            )
        }
        degraded = {
            key: value
            for key, value in backend_counts.items()
            if key in {"partial", "blocked", "unavailable"} and value
        }
        checks.append(
            ReadinessCheck(
                name="strategy_capabilities",
                status="warning" if degraded else "ok",
                message=(
                    f"Some strategies have degraded backend capability: {degraded}."
                    if degraded
                    else "Active and approved strategies have supported backend capability."
                ),
                suggested_actions=_strategy_capability_suggested_actions(degraded),
                details={
                    "backend_status_counts": backend_counts,
                    "draft_backend_status_counts": draft_backend_counts,
                    "compatibility_counts": catalog.summary.compatibility_counts,
                    "nautilus_installed": nautilus_trader_available(),
                },
            )
        )

    status = _overall_status(checks)
    return ReadinessReport(
        source_root=str(base),
        status=status,
        ready=status != "blocked",
        checks=checks,
    )


def write_readiness_report(
    report: ReadinessReport,
    root: Path | None = None,
    output_path: Path | None = None,
    markdown_path: Path | None = None,
) -> tuple[Path, Path]:
    base = root or project_root()
    json_path = output_path or base / "reports" / "readiness" / "readiness.json"
    md_path = markdown_path or json_path.with_suffix(".md")
    ensure_dir(json_path.parent)
    report.report_json_path = _relpath(json_path, base)
    report.report_markdown_path = _relpath(md_path, base)
    write_json(json_path, report)
    md_path.write_text(_render_readiness_markdown(report), encoding="utf-8")
    return json_path, md_path


def _overall_status(checks: list[ReadinessCheck]) -> ReadinessStatus:
    if any(check.status == "blocked" for check in checks):
        return "blocked"
    if any(check.status == "warning" for check in checks):
        return "warning"
    return "ok"


def _paper_monitor_suggested_actions(warnings: list[str]) -> list[str]:
    actions: list[str] = []
    if any("kill switch" in warning for warning in warnings):
        actions.append("uv run oc dashboard command-plan paper.kill_switch.clear")
    if any("account snapshot" in warning for warning in warnings):
        actions.append("uv run oc paper sync-account")
    return actions


def _strategy_capability_suggested_actions(degraded: dict[str, int]) -> list[str]:
    if not degraded:
        return []
    return [
        "uv run oc spec capabilities <strategy-spec.yaml>",
        (
            "uv run oc dashboard command-plan strategy.workflow.verify "
            "--strategy-path <strategy-spec.yaml>"
        ),
    ]


def _resolve_dashboard_serve_root(base: Path) -> Path | None:
    dist_root = base / "dashboard" / "dist"
    html_root = base / "reports" / "dashboard"
    candidate = dist_root if (dist_root / "index.html").exists() else html_root
    return candidate if (candidate / "index.html").exists() else None


def _relpath(path: Path, base: Path) -> str:
    try:
        return path.relative_to(base).as_posix()
    except ValueError:
        return path.as_posix()


def _render_readiness_markdown(report: ReadinessReport) -> str:
    lines = [
        "# Open Composer Readiness",
        "",
        f"- Generated at: `{report.generated_at.isoformat()}`",
        f"- Source root: `{report.source_root}`",
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
        if check.suggested_actions:
            lines.append("- Suggested actions:")
            lines.extend(f"  - `{action}`" for action in check.suggested_actions)
        if check.details:
            lines.append(f"- Details: `{check.details}`")
        lines.append("")
    return "\n".join(lines)
