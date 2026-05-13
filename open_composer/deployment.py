from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from open_composer.config import ensure_dir, project_root
from open_composer.dashboard.catalog import (
    build_dashboard_catalog,
    build_feature_packet_records,
    write_dashboard_catalog,
    write_dashboard_review_markdown,
)
from open_composer.dashboard.html import write_dashboard_html
from open_composer.paper_controls import refresh_paper_monitor, write_paper_status
from open_composer.readiness import ReadinessStatus, build_readiness_report, write_readiness_report
from open_composer.storage import write_json


class DeploymentStep(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    status: ReadinessStatus
    message: str
    output_paths: list[str] = Field(default_factory=list)
    suggested_actions: list[str] = Field(default_factory=list)
    details: dict[str, object] = Field(default_factory=dict)


class DeploymentReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    source_root: str
    status: ReadinessStatus
    ready: bool
    steps: list[DeploymentStep] = Field(default_factory=list)
    report_json_path: str | None = None
    report_markdown_path: str | None = None

    @property
    def output_paths(self) -> list[str]:
        paths = [path for step in self.steps for path in step.output_paths]
        if self.report_json_path:
            paths.append(self.report_json_path)
        if self.report_markdown_path:
            paths.append(self.report_markdown_path)
        return list(dict.fromkeys(paths))


def ensure_runtime_dirs(root: Path | None = None) -> list[Path]:
    base = root or project_root()
    created: list[Path] = []
    for relative in [
        "data/cache",
        "reports/backtests",
        "reports/parity",
        "reports/scans",
        "reports/reviews",
        "reports/weekly",
        "reports/paper",
        "reports/runs",
        "reports/workflows",
        "reports/capabilities",
        "reports/specs",
        "reports/context",
        "reports/research",
        "reports/options",
        "reports/dashboard",
        "reports/features",
        "reports/deployment",
        "data/raw/events",
        "data/raw/macro",
        "event_logs",
        "feature_logs",
        "signal_logs",
        "journal",
        "strategies_pine/generated",
        "strategy_versions",
    ]:
        created.append(ensure_dir(base / relative))
    return created


def write_feature_validation_report(
    root: Path | None = None,
    *,
    packets: list[object] | None = None,
    output_path: Path | None = None,
) -> tuple[Path, Path, Path]:
    base = root or project_root()
    packet_records = packets if packets is not None else build_feature_packet_records(base)
    report_path = output_path or base / "reports" / "features" / "validation.json"
    generated_at = datetime.now(UTC)
    manifest_path = write_feature_manifest(
        base,
        packets=packet_records,
        output_path=report_path.parent / "manifest.json",
        generated_at=generated_at,
    )
    payload = {
        "generated_at": generated_at.isoformat(),
        "source_root": str(base),
        "feature_packet_count": len(packet_records),
        "manifest_path": _relpath(manifest_path, base),
        "packets": [
            packet.model_dump(mode="json") if hasattr(packet, "model_dump") else packet
            for packet in packet_records
        ],
    }
    write_json(report_path, payload)
    md_path = report_path.with_suffix(".md")
    ensure_dir(md_path.parent)
    md_path.write_text(_render_feature_validation_markdown(payload), encoding="utf-8")
    return report_path, md_path, manifest_path


def write_feature_manifest(
    root: Path | None = None,
    *,
    packets: list[object] | None = None,
    output_path: Path | None = None,
    generated_at: datetime | None = None,
) -> Path:
    base = root or project_root()
    packet_records = packets if packets is not None else build_feature_packet_records(base)
    timestamp = generated_at or datetime.now(UTC)
    manifest_path = output_path or base / "reports" / "features" / "manifest.json"
    payload = _build_feature_manifest_payload(base, packet_records, timestamp)
    write_json(manifest_path, payload)
    return manifest_path


def prepare_workspace(
    root: Path | None = None,
    *,
    sync_broker: bool = False,
) -> DeploymentReport:
    base = root or project_root()
    steps: list[DeploymentStep] = []

    created_dirs = ensure_runtime_dirs(base)
    steps.append(
        DeploymentStep(
            name="runtime_dirs",
            status="ok",
            message="Runtime directories are available.",
            details={"count": len(created_dirs)},
        )
    )

    feature_validation_path, feature_validation_md_path, feature_manifest_path = (
        write_feature_validation_report(base)
    )
    packet_records = build_feature_packet_records(base)
    incomplete_packets = [
        packet for packet in packet_records if packet.point_in_time_status != "complete"
    ]
    steps.append(
        DeploymentStep(
            name="feature_validation",
            status="warning" if incomplete_packets else "ok",
            message=(
                f"{len(incomplete_packets)} feature packet file(s) need PIT metadata."
                if incomplete_packets
                else "Feature packets are absent or point-in-time complete."
            ),
            suggested_actions=["uv run oc feature validate"] if incomplete_packets else [],
            output_paths=[
                _relpath(feature_validation_path, base),
                _relpath(feature_validation_md_path, base),
                _relpath(feature_manifest_path, base),
            ],
            details={
                "packet_count": len(packet_records),
                "incomplete_count": len(incomplete_packets),
                "incomplete_paths": [packet.path for packet in incomplete_packets],
            },
        )
    )

    status_path = write_paper_status(base)
    paper_monitor = refresh_paper_monitor(base, sync_broker=sync_broker)
    monitor_outputs = [
        status_path,
        paper_monitor.reconciliation_report_path,
        paper_monitor.alert_report_path,
        paper_monitor.report_json_path,
        paper_monitor.report_markdown_path,
        *paper_monitor.sync_output_paths,
    ]
    paper_monitor_status: ReadinessStatus = (
        "blocked" if paper_monitor.status == "error" else paper_monitor.status
    )
    steps.append(
        DeploymentStep(
            name="paper_monitor",
            status=paper_monitor_status,
            message=(
                "Paper monitor refreshed."
                if paper_monitor.sync_status != "error"
                else f"Paper monitor sync failed: {paper_monitor.sync_error}"
            ),
            suggested_actions=_paper_monitor_suggested_actions(
                paper_monitor_status,
                paper_monitor.alert_status,
                paper_monitor.reconciliation_status,
                paper_monitor.sync_status,
            ),
            output_paths=[
                path for path in (_relpath(item, base) for item in monitor_outputs) if path
            ],
            details={
                "sync_broker": sync_broker,
                "sync_status": paper_monitor.sync_status,
                "alert_status": paper_monitor.alert_status,
                "reconciliation_status": paper_monitor.reconciliation_status,
            },
        )
    )

    readiness_report = build_readiness_report(base)
    readiness_json_path, readiness_md_path = write_readiness_report(readiness_report, base)
    steps.append(
        DeploymentStep(
            name="readiness",
            status=readiness_report.status,
            message="Deployment readiness report rebuilt.",
            suggested_actions=[
                action
                for check in readiness_report.checks
                if check.status != "ok"
                for action in check.suggested_actions
            ],
            output_paths=[
                _relpath(readiness_json_path, base),
                _relpath(readiness_md_path, base),
            ],
            details={
                "ready": readiness_report.ready,
                "check_count": len(readiness_report.checks),
            },
        )
    )

    status = _overall_status(steps)
    report = DeploymentReport(
        source_root=str(base),
        status=status,
        ready=status != "blocked",
        steps=steps,
    )
    json_path = base / "reports" / "deployment" / "prepare.json"
    md_path = base / "reports" / "deployment" / "prepare.md"
    report.report_json_path = _relpath(json_path, base)
    report.report_markdown_path = _relpath(md_path, base)
    write_json(json_path, report)
    ensure_dir(md_path.parent)
    md_path.write_text(_render_deployment_markdown(report), encoding="utf-8")

    catalog = build_dashboard_catalog(base)
    catalog_artifacts = write_dashboard_catalog(catalog, base)
    write_dashboard_review_markdown(catalog, root=base)
    dashboard_html_path = write_dashboard_html(catalog, base)
    dashboard_step = DeploymentStep(
        name="dashboard_artifacts",
        status="ok",
        message="Dashboard catalog, review, and static HTML were rebuilt.",
        output_paths=[
            _relpath(catalog_artifacts.catalog_path, base),
            _relpath(catalog_artifacts.markdown_path, base),
            _relpath(catalog_artifacts.review_path, base),
            _relpath(dashboard_html_path, base),
        ],
        details={
            "strategies": catalog.summary.strategy_count,
            "versions": catalog.summary.version_count,
            "runs": catalog.summary.run_count,
            "readiness_status": catalog.summary.readiness_status,
            "deployment_status": catalog.summary.deployment_status,
        },
    )
    report.steps.append(dashboard_step)
    status = _overall_status(report.steps)
    report.status = status
    report.ready = status != "blocked"
    write_json(json_path, report)
    md_path.write_text(_render_deployment_markdown(report), encoding="utf-8")
    return report


def _overall_status(steps: list[DeploymentStep]) -> ReadinessStatus:
    if any(step.status == "blocked" for step in steps):
        return "blocked"
    if any(step.status == "warning" for step in steps):
        return "warning"
    return "ok"


def _render_feature_validation_markdown(payload: dict[str, object]) -> str:
    packets = payload.get("packets", [])
    packet_count = payload.get("feature_packet_count", 0)
    lines = [
        "# Feature Packet Validation",
        "",
        f"- Generated at: `{payload.get('generated_at')}`",
        f"- Source root: `{payload.get('source_root')}`",
        f"- Feature packet count: `{packet_count}`",
        f"- Manifest: `{payload.get('manifest_path', 'n/a')}`",
        "",
        "## Packets",
        "",
    ]
    if not packets:
        lines.append("- No feature packets were found.")
        return "\n".join(lines) + "\n"
    for packet in packets:
        if not isinstance(packet, dict):
            continue
        lines.append(f"### {packet.get('path', 'unknown')}")
        lines.append("")
        lines.append(f"- Source: `{packet.get('source', 'n/a')}`")
        lines.append(f"- Point-in-time status: `{packet.get('point_in_time_status', 'n/a')}`")
        lines.append(f"- Records: `{packet.get('record_count', 0)}`")
        warnings = packet.get("replay_warnings", [])
        if warnings:
            lines.append(f"- Warnings: `{warnings}`")
        lines.append("")
    return "\n".join(lines)


def _build_feature_manifest_payload(
    base: Path,
    packet_records: list[object],
    generated_at: datetime,
) -> dict[str, object]:
    packet_payloads = [
        packet.model_dump(mode="json") if hasattr(packet, "model_dump") else dict(packet)
        for packet in packet_records
    ]
    indexed_packets = [
        _feature_packet_manifest_entry(base, packet)
        for packet in packet_payloads
        if isinstance(packet, dict)
    ]
    status_counts: dict[str, int] = {}
    for packet in indexed_packets:
        status = str(packet.get("point_in_time_status", "missing"))
        status_counts[status] = status_counts.get(status, 0) + 1
    return {
        "generated_at": generated_at.isoformat(),
        "source_root": str(base),
        "packet_count": len(indexed_packets),
        "complete_count": status_counts.get("complete", 0),
        "partial_count": status_counts.get("partial", 0),
        "missing_count": status_counts.get("missing", 0),
        "packets": indexed_packets,
    }


def _feature_packet_manifest_entry(base: Path, packet: dict[str, object]) -> dict[str, object]:
    relative_path = str(packet.get("path", ""))
    row_index = _feature_packet_row_index(base / relative_path)
    rows = row_index["rows"]
    return {
        **packet,
        "sources": _sorted_values(row.get("source") for row in rows),
        "symbols": _sorted_values(row.get("symbol") for row in rows),
        "schema_versions": _sorted_values(row.get("schema_version") for row in rows),
        "models": _sorted_values(row.get("model") for row in rows),
        "input_hashes": _sorted_values(row.get("input_hash") for row in rows),
        "prompt_hashes": _sorted_values(row.get("prompt_hash") for row in rows),
        "dedupe_key_count": len(_sorted_values(row.get("dedupe_key") for row in rows)),
        "duplicate_dedupe_keys": row_index["duplicate_dedupe_keys"],
        "rows": rows,
    }


def _feature_packet_row_index(path: Path) -> dict[str, object]:
    rows: list[dict[str, object]] = []
    seen_dedupe_keys: set[str] = set()
    duplicate_dedupe_keys: set[str] = set()
    if not path.exists():
        return {"rows": rows, "duplicate_dedupe_keys": []}
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                raw = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(raw, dict):
                continue
            dedupe_key = raw.get("dedupe_key")
            if isinstance(dedupe_key, str):
                if dedupe_key in seen_dedupe_keys:
                    duplicate_dedupe_keys.add(dedupe_key)
                seen_dedupe_keys.add(dedupe_key)
            rows.append(
                {
                    "line_number": line_number,
                    "timestamp": raw.get("timestamp"),
                    "published_at": raw.get("published_at"),
                    "fetched_at": raw.get("fetched_at"),
                    "source": raw.get("source"),
                    "symbol": raw.get("symbol"),
                    "dedupe_key": raw.get("dedupe_key"),
                    "schema_version": raw.get("schema_version"),
                    "model": raw.get("model"),
                    "input_hash": raw.get("input_hash"),
                    "prompt_hash": raw.get("prompt_hash"),
                    "feature_fields": _feature_fields(raw),
                }
            )
    return {
        "rows": rows,
        "duplicate_dedupe_keys": sorted(duplicate_dedupe_keys),
    }


def _feature_fields(row: dict[str, object]) -> list[str]:
    metadata_fields = {
        "timestamp",
        "published_at",
        "fetched_at",
        "source",
        "symbol",
        "dedupe_key",
        "schema_version",
        "summary",
        "sentiment",
        "model",
        "input_hash",
        "prompt_hash",
        "features",
    }
    fields = {key for key in row if key not in metadata_fields}
    nested = row.get("features")
    if isinstance(nested, dict):
        fields.update(str(key) for key in nested)
    return sorted(fields)


def _sorted_values(values) -> list[str]:
    return sorted({str(value) for value in values if value not in {None, ""}})


def _render_deployment_markdown(report: DeploymentReport) -> str:
    lines = [
        "# Open Composer Deployment Prepare",
        "",
        f"- Generated at: `{report.generated_at.isoformat()}`",
        f"- Source root: `{report.source_root}`",
        f"- Status: `{report.status}`",
        f"- Ready: `{'yes' if report.ready else 'no'}`",
        "",
        "## Steps",
        "",
    ]
    for step in report.steps:
        lines.append(f"### {step.name}")
        lines.append("")
        lines.append(f"- Status: `{step.status}`")
        lines.append(f"- Message: {step.message}")
        if step.suggested_actions:
            lines.append("- Suggested actions:")
            lines.extend(f"  - `{action}`" for action in step.suggested_actions)
        if step.details:
            lines.append(f"- Details: `{step.details}`")
        if step.output_paths:
            lines.append(f"- Outputs: `{step.output_paths}`")
        lines.append("")
    return "\n".join(lines)


def _paper_monitor_suggested_actions(
    status: ReadinessStatus,
    alert_status: str,
    reconciliation_status: str,
    sync_status: str,
) -> list[str]:
    actions: list[str] = []
    if sync_status == "skipped":
        actions.append("uv run oc paper monitor --sync-broker")
    if alert_status == "warning" or reconciliation_status == "warning":
        actions.append("uv run oc paper alerts")
        actions.append("uv run oc paper reconcile")
    if status == "blocked":
        actions.append("uv run oc paper status")
    return list(dict.fromkeys(actions))


def _relpath(path: Path | str | None, base: Path) -> str | None:
    if path is None:
        return None
    candidate = Path(path)
    try:
        return str(candidate.relative_to(base))
    except ValueError:
        return str(candidate)
