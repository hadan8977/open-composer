from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from open_composer.config import ensure_dir, project_root
from open_composer.models.dashboard import (
    DashboardAuditEvent,
    DashboardCapabilityFinding,
    DashboardCatalog,
    DashboardContext,
    DashboardCustomDataBinding,
    DashboardDataComparison,
    DashboardDeploymentReport,
    DashboardDeploymentStep,
    DashboardFeaturePacket,
    DashboardGroup,
    DashboardJournalEntry,
    DashboardOperationalCheck,
    DashboardOrder,
    DashboardPaperPosition,
    DashboardPaperReadinessCheck,
    DashboardPaperReadinessReport,
    DashboardReadinessReport,
    DashboardReview,
    DashboardRun,
    DashboardSignal,
    DashboardStrategy,
    DashboardSummary,
    DashboardVersion,
    DashboardWorkflowReport,
)
from open_composer.models.journal import TradeJournalEntry
from open_composer.models.review_card import ReviewCard
from open_composer.models.strategy_spec import StrategySpec, load_strategy_spec
from open_composer.paper_controls import build_paper_status
from open_composer.storage import write_json
from open_composer.strategy_capabilities import assess_strategy_capabilities
from open_composer.strategy_versions import load_strategy_versions, strategy_content_hash

LIFECYCLE_PRIORITY = {"active": 3, "approved": 2, "draft": 1, "retired": 0}
MODEL_ROLE_ORDER = ("pure_quant", "quant_review", "quant_scan", "quant_orchestrator")
RISK_ORDER = ("stable", "moderate", "high")
RUN_KIND_ORDER = ("backtest", "scan", "paper", "unknown")


@dataclass(frozen=True)
class DashboardCatalogArtifacts:
    catalog_path: Path
    markdown_path: Path
    review_path: Path


def build_dashboard_catalog(root: Path | None = None) -> DashboardCatalog:
    base = root or project_root()
    generated_at = datetime.now(UTC)
    spec_paths = _strategy_spec_paths(base)

    version_records = _build_version_records(base, spec_paths)
    strategy_records = _build_strategy_records(version_records)
    run_records, signal_records = _build_run_and_signal_records(base, strategy_records)
    review_records = _build_review_records(base, signal_records, strategy_records)
    context_records = _build_context_records(base, signal_records)
    journal_records = _build_journal_records(base)
    order_records = _build_order_records(base)
    paper_position_records = _build_paper_position_records(base)
    paper_readiness_records = _build_paper_readiness_records(base)
    audit_records = _build_audit_records(base, journal_records, order_records)
    group_records = _build_group_records(strategy_records)
    data_comparison_records = _build_data_comparison_records(base)
    feature_packet_records = build_feature_packet_records(base)
    workflow_records = _build_workflow_records(base)
    readiness_report = _build_readiness_record(base)
    deployment_report = _build_deployment_record(base)

    summary = _build_summary(
        base=base,
        generated_at=generated_at,
        strategies=strategy_records,
        versions=version_records,
        runs=run_records,
        signals=signal_records,
        reviews=review_records,
        contexts=context_records,
        journals=journal_records,
        orders=order_records,
        audits=audit_records,
        data_comparisons=data_comparison_records,
        feature_packets=feature_packet_records,
        workflow_reports=workflow_records,
        readiness_report=readiness_report,
        deployment_report=deployment_report,
        paper_readiness_reports=paper_readiness_records,
    )

    return DashboardCatalog(
        generated_at=generated_at,
        source_root=str(base),
        summary=summary,
        strategies=strategy_records,
        versions=version_records,
        runs=run_records,
        signals=signal_records,
        reviews=review_records,
        contexts=context_records,
        journals=journal_records,
        orders=order_records,
        paper_positions=paper_position_records,
        paper_readiness_reports=paper_readiness_records,
        audits=audit_records,
        groups=group_records,
        data_comparisons=data_comparison_records,
        feature_packets=feature_packet_records,
        workflow_reports=workflow_records,
        readiness_report=readiness_report,
        deployment_report=deployment_report,
    )


def write_dashboard_catalog(
    catalog: DashboardCatalog,
    root: Path | None = None,
    output_path: Path | None = None,
    markdown_path: Path | None = None,
) -> DashboardCatalogArtifacts:
    base = root or project_root()
    json_path = output_path or (base / "reports" / "dashboard" / "catalog.json")
    md_path = markdown_path or (base / "reports" / "dashboard" / "catalog.md")
    ensure_dir(json_path.parent)
    ensure_dir(md_path.parent)
    write_json(json_path, catalog)
    md_path.write_text(_render_catalog_markdown(catalog), encoding="utf-8")
    return DashboardCatalogArtifacts(
        catalog_path=json_path,
        markdown_path=md_path,
        review_path=base / "docs" / "dashboard-d0-review.zh.md",
    )


def write_dashboard_review_markdown(
    catalog: DashboardCatalog,
    path: Path | None = None,
    root: Path | None = None,
) -> Path:
    base = root or project_root()
    target = path or (base / "docs" / "dashboard-d0-review.zh.md")
    ensure_dir(target.parent)
    target.write_text(_render_review_markdown(catalog), encoding="utf-8")
    return target


def _strategy_spec_paths(base: Path) -> list[Path]:
    paths: list[Path] = []
    for folder in ["drafts", "approved", "active", "retired"]:
        paths.extend(sorted((base / "strategy_specs" / folder).glob("*.yaml")))
    return paths


def _build_version_records(base: Path, spec_paths: list[Path]) -> list[DashboardVersion]:
    grouped: dict[tuple[str, str], dict[str, Any]] = {}
    registered_versions = load_strategy_versions(base)
    registered_by_version = {
        (version.strategy_name, version.version_id): version for version in registered_versions
    }
    for path in spec_paths:
        spec = load_strategy_spec(path)
        content_hash = strategy_content_hash(spec)
        version_id = f"ver_{content_hash[:12]}"
        registered = registered_by_version.get((spec.name, version_id))
        key = (spec.name, content_hash)
        capability_report = assess_strategy_capabilities(path)
        model_role, model_role_reasons = _infer_model_role(spec)
        risk_tier, risk_reasons = _infer_risk_tier(spec)
        modified_at = _file_mtime(path)
        raw = grouped.setdefault(
            key,
            {
                "strategy_id": spec.name,
                "strategy_name": spec.name,
                "version_id": version_id,
                "primary_lifecycle": spec.lifecycle,
                "lifecycles": [],
                "source_paths": list(registered.source_paths) if registered else [],
                "primary_path": "",
                "primary_priority": -1,
                "primary_mtime": datetime.min.replace(tzinfo=UTC),
                "content_hash": content_hash,
                "parent_version_id": registered.parent_version_id if registered else None,
                "created_by": registered.created_by if registered else "file_scan",
                "created_at": registered.created_at if registered else modified_at,
                "modified_at": modified_at,
                "first_seen_at": registered.first_seen_at if registered else modified_at,
                "symbol": spec.primary_symbol,
                "timeframe": spec.timeframe,
                "universe": list(spec.universe),
                "factor_names": sorted(spec.factors),
                "llm_feature_factor_names": sorted(
                    name for name, factor in spec.factors.items() if factor.source == "llm_feature"
                ),
                "feature_packet_factor_names": sorted(
                    name
                    for name, factor in spec.factors.items()
                    if factor.source == "feature_packet"
                ),
                "backend": spec.execution.backend,
                "backend_status": capability_report.backend_plan.status,
                "backend_reasons": list(capability_report.backend_plan.reasons),
                "execution_mode": spec.execution.mode,
                "broker": spec.execution.broker,
                "data_source": spec.data.source,
                "llm_review_enabled": spec.llm_review.enabled,
                "llm_review_model": spec.llm_review.model,
                "model_role": model_role,
                "model_role_reasons": model_role_reasons,
                "risk_tier": risk_tier,
                "risk_reasons": risk_reasons,
                "required_capabilities": list(spec.required_capabilities),
                "compatibility": [],
                "note": _spec_note(spec),
            },
        )
        raw["lifecycles"].append(spec.lifecycle)
        raw["source_paths"].append(_relpath(path, base))
        priority = LIFECYCLE_PRIORITY[spec.lifecycle]
        if priority > raw["primary_priority"] or (
            priority == raw["primary_priority"] and modified_at > raw["primary_mtime"]
        ):
            raw["primary_priority"] = priority
            raw["primary_mtime"] = modified_at
            raw["primary_lifecycle"] = spec.lifecycle
            raw["primary_path"] = _relpath(path, base)
        raw["modified_at"] = max(raw["modified_at"], modified_at)
        raw["first_seen_at"] = min(raw["first_seen_at"], modified_at)
        raw["compatibility"] = [
            DashboardCapabilityFinding(
                capability=finding.capability,
                status=finding.status,
                reasons=list(finding.reasons),
            )
            for finding in capability_report.findings
        ]

    for registered in registered_versions:
        key = (registered.strategy_name, registered.content_hash)
        if key in grouped:
            continue
        snapshot_path = base / registered.snapshot_path
        if not snapshot_path.exists():
            continue
        spec = load_strategy_spec(snapshot_path)
        capability_report = assess_strategy_capabilities(snapshot_path)
        model_role, model_role_reasons = _infer_model_role(spec)
        risk_tier, risk_reasons = _infer_risk_tier(spec)
        grouped[key] = {
            "strategy_id": registered.strategy_id,
            "strategy_name": registered.strategy_name,
            "version_id": registered.version_id,
            "primary_lifecycle": registered.lifecycle,
            "lifecycles": [registered.lifecycle],
            "source_paths": sorted(set(registered.source_paths)),
            "primary_path": registered.snapshot_path,
            "primary_priority": LIFECYCLE_PRIORITY.get(registered.lifecycle, 0),
            "primary_mtime": registered.last_seen_at,
            "content_hash": registered.content_hash,
            "parent_version_id": registered.parent_version_id,
            "created_by": registered.created_by,
            "created_at": registered.created_at,
            "modified_at": registered.last_seen_at,
            "first_seen_at": registered.first_seen_at,
            "symbol": registered.symbol,
            "timeframe": registered.timeframe,
            "universe": list(registered.universe),
            "factor_names": list(registered.factor_names),
            "llm_feature_factor_names": list(registered.llm_feature_factor_names),
            "feature_packet_factor_names": list(registered.feature_packet_factor_names),
            "backend": registered.backend,
            "backend_status": capability_report.backend_plan.status,
            "backend_reasons": list(capability_report.backend_plan.reasons),
            "execution_mode": registered.execution_mode,
            "broker": registered.broker,
            "data_source": registered.data_source,
            "llm_review_enabled": registered.llm_review_enabled,
            "llm_review_model": spec.llm_review.model,
            "model_role": model_role,
            "model_role_reasons": model_role_reasons,
            "risk_tier": risk_tier,
            "risk_reasons": risk_reasons,
            "required_capabilities": list(registered.required_capabilities),
            "compatibility": [
                DashboardCapabilityFinding(
                    capability=finding.capability,
                    status=finding.status,
                    reasons=list(finding.reasons),
                )
                for finding in capability_report.findings
            ],
            "note": _spec_note(spec),
        }

    versions: list[DashboardVersion] = []
    for raw in grouped.values():
        raw["lifecycles"] = _ordered_unique(raw["lifecycles"], order=list(LIFECYCLE_PRIORITY))
        raw["source_paths"] = sorted(set(raw["source_paths"]))
        payload = {
            key: raw[key]
            for key in [
                "strategy_id",
                "strategy_name",
                "version_id",
                "primary_lifecycle",
                "lifecycles",
                "source_paths",
                "primary_path",
                "content_hash",
                "parent_version_id",
                "created_by",
                "created_at",
                "modified_at",
                "first_seen_at",
                "symbol",
                "timeframe",
                "universe",
                "factor_names",
                "llm_feature_factor_names",
                "feature_packet_factor_names",
                "backend",
                "backend_status",
                "backend_reasons",
                "execution_mode",
                "broker",
                "data_source",
                "llm_review_enabled",
                "llm_review_model",
                "model_role",
                "model_role_reasons",
                "risk_tier",
                "risk_reasons",
                "required_capabilities",
                "compatibility",
                "note",
            ]
        }
        payload["created_at"] = raw["created_at"].isoformat()
        payload["modified_at"] = raw["modified_at"].isoformat()
        payload["first_seen_at"] = raw["first_seen_at"].isoformat()
        versions.append(DashboardVersion.model_validate(payload))
    versions.sort(
        key=lambda item: (
            item.strategy_id,
            -LIFECYCLE_PRIORITY[item.primary_lifecycle],
            item.modified_at,
            item.version_id,
        )
    )
    return versions


def _build_strategy_records(version_records: list[DashboardVersion]) -> list[DashboardStrategy]:
    grouped: dict[str, list[DashboardVersion]] = defaultdict(list)
    for version in version_records:
        grouped[version.strategy_id].append(version)

    strategies: list[DashboardStrategy] = []
    for strategy_id, versions in grouped.items():
        selected = max(
            versions,
            key=lambda item: (
                LIFECYCLE_PRIORITY[item.primary_lifecycle],
                item.modified_at,
                item.version_id,
            ),
        )
        lifecycle_counts = Counter(version.primary_lifecycle for version in versions)
        compatibility = {finding.capability: finding.status for finding in selected.compatibility}
        compatibility_reasons = {
            finding.capability: list(finding.reasons) for finding in selected.compatibility
        }
        strategies.append(
            DashboardStrategy(
                strategy_id=strategy_id,
                strategy_name=selected.strategy_name,
                current_version_id=selected.version_id,
                version_ids=[version.version_id for version in versions],
                version_count=len(versions),
                source_paths=_union_paths(version.source_paths for version in versions),
                lifecycle=selected.primary_lifecycle,
                lifecycle_counts=dict(sorted(lifecycle_counts.items())),
                symbol=selected.symbol,
                timeframe=selected.timeframe,
                universe=list(selected.universe),
                universe_size=len(selected.universe),
                factor_names=list(selected.factor_names),
                factor_count=len(selected.factor_names),
                llm_feature_factor_names=list(selected.llm_feature_factor_names),
                feature_packet_factor_names=list(selected.feature_packet_factor_names),
                backend=selected.backend,
                backend_status=selected.backend_status,
                backend_reasons=list(selected.backend_reasons),
                execution_mode=selected.execution_mode,
                broker=selected.broker,
                data_source=selected.data_source,
                llm_review_enabled=selected.llm_review_enabled,
                llm_review_model=selected.llm_review_model,
                model_role=selected.model_role,
                model_role_reasons=selected.model_role_reasons,
                risk_tier=selected.risk_tier,
                risk_reasons=selected.risk_reasons,
                required_capabilities=list(selected.required_capabilities),
                compatibility=compatibility,
                compatibility_reasons=compatibility_reasons,
            )
        )
    strategies.sort(
        key=lambda item: (
            -LIFECYCLE_PRIORITY[item.lifecycle],
            MODEL_ROLE_ORDER.index(item.model_role),
            RISK_ORDER.index(item.risk_tier),
            item.strategy_name.lower(),
        )
    )
    return strategies


def _build_run_and_signal_records(
    base: Path,
    strategies: list[DashboardStrategy],
) -> tuple[list[DashboardRun], list[DashboardSignal]]:
    strategy_map = {item.strategy_id: item for item in strategies}
    signal_log_paths = sorted((base / "signal_logs").glob("*.jsonl"))
    report_paths = sorted((base / "reports" / "backtests").glob("*.md")) + sorted(
        (base / "reports" / "scans").glob("*.md")
    )

    runs: dict[str, DashboardRun] = {}
    signals: list[DashboardSignal] = []

    for report_path in report_paths:
        report = _parse_report(report_path)
        run_id = report["run_id"]
        strategy_name = report["strategy_name"]
        strategy_id = strategy_name
        selected_version = strategy_map.get(strategy_id)
        report_version_id = _registered_value(report.get("version_id"))
        report_spec_hash = _registered_value(report.get("spec_hash"))
        report_strategy_backend = _registered_value(report.get("strategy_backend"))
        report_execution_backend = _registered_value(report.get("execution_backend"))
        report_backend_plan_path = _registered_value(report.get("backend_plan_path"))
        custom_data_bindings = _backend_plan_custom_data_bindings(
            base,
            report_backend_plan_path,
        )
        if run_id.startswith("scan-") or report_path.parent.name == "scans":
            kind = "scan"
        else:
            kind = "backtest"
        runs[run_id] = DashboardRun(
            run_id=run_id,
            strategy_id=strategy_id,
            strategy_name=strategy_name,
            version_id=(
                report_version_id
                or (selected_version.current_version_id if selected_version else None)
            ),
            spec_hash=report_spec_hash,
            strategy_backend=report_strategy_backend
            or (selected_version.backend if selected_version else "python_reference"),
            execution_backend=report_execution_backend or "python_reference",
            kind=kind,
            source_path=_relpath(report_path, base),
            report_path=_relpath(report_path, base),
            signal_log_path=None,
            backend_plan_path=report_backend_plan_path,
            custom_data_bindings=custom_data_bindings,
            symbol=report["symbol"],
            timeframe=report["timeframe"],
            bars=report.get("bars"),
            signals=report.get("signals", 0),
            trades=report.get("trades"),
            start_equity=report.get("start_equity"),
            end_equity=report.get("end_equity"),
            total_return_pct=report.get("total_return_pct"),
            annualized_return_pct=report.get("annualized_return_pct"),
            sharpe_ratio=report.get("sharpe_ratio"),
            total_fees=report.get("total_fees"),
            data_sanity_status=report.get("data_sanity_status"),
            evidence_level=report.get("evidence_level"),
            data_sanity_source=report.get("data_sanity_source"),
            data_sanity_mode=report.get("data_sanity_mode"),
            data_sanity_feed=report.get("data_sanity_feed"),
            data_sanity_path=report.get("data_sanity_path"),
            data_sanity_warnings=report.get("data_sanity_warnings", []),
            assumptions=report.get("assumptions", []),
        )

    for log_path in signal_log_paths:
        records = _load_jsonl(log_path)
        if not records:
            continue
        run_id = str(records[0].get("run_id", log_path.stem))
        strategy_name = str(records[0].get("strategy_name", run_id))
        strategy_id = strategy_name
        selected_version = strategy_map.get(strategy_id)
        signal_version_id = _registered_value(records[0].get("version_id"))
        signal_spec_hash = _registered_value(records[0].get("spec_hash"))
        signal_strategy_backend = _registered_value(records[0].get("strategy_backend"))
        signal_execution_backend = _registered_value(records[0].get("execution_backend"))
        run = runs.get(run_id)
        if run is None:
            kind = "scan" if run_id.startswith("scan-") else "unknown"
            run = DashboardRun(
                run_id=run_id,
                strategy_id=strategy_id,
                strategy_name=strategy_name,
                version_id=(
                    signal_version_id
                    or (selected_version.current_version_id if selected_version else None)
                ),
                spec_hash=signal_spec_hash,
                strategy_backend=signal_strategy_backend
                or (selected_version.backend if selected_version else "python_reference"),
                execution_backend=signal_execution_backend or "python_reference",
                kind=kind,
                source_path=_relpath(log_path, base),
                report_path=None,
                signal_log_path=_relpath(log_path, base),
                backend_plan_path=None,
                symbol=str(records[0].get("symbol", "")),
                timeframe=str(records[0].get("timeframe", "")),
                signals=len(records),
            )
            runs[run_id] = run
        else:
            run.signal_log_path = _relpath(log_path, base)
            run.signals = max(run.signals, len(records))
            if not run.version_id:
                run.version_id = signal_version_id or (
                    selected_version.current_version_id if selected_version else None
                )
            if not run.spec_hash:
                run.spec_hash = signal_spec_hash
        timestamps: list[datetime] = []
        for record in records:
            timestamp = _parse_datetime(record["timestamp"])
            record_version_id = _registered_value(record.get("version_id"))
            record_spec_hash = _registered_value(record.get("spec_hash"))
            timestamps.append(timestamp)
            signal = DashboardSignal(
                signal_id=str(record["id"]),
                run_id=str(record["run_id"]),
                strategy_id=str(record.get("strategy_id") or record["strategy_name"]),
                strategy_name=str(record["strategy_name"]),
                version_id=(
                    record_version_id
                    or (selected_version.current_version_id if selected_version else None)
                ),
                spec_hash=record_spec_hash,
                strategy_backend=_registered_value(record.get("strategy_backend"))
                or (selected_version.backend if selected_version else "python_reference"),
                execution_backend=_registered_value(record.get("execution_backend"))
                or "python_reference",
                symbol=str(record["symbol"]),
                timeframe=str(record["timeframe"]),
                timestamp=timestamp,
                action=str(record["action"]),
                side=str(record["side"]),
                source=str(record["source"]),
                price=float(record["price"]),
                execution_mode=str(record["execution_mode"]),
                fill_assumption=str(record["fill_assumption"]),
                lifecycle=str(record["lifecycle"]),
                conditions=list(record.get("conditions", [])),
                log_path=_relpath(log_path, base),
            )
            signals.append(signal)
        if timestamps:
            run.first_signal_at = min(timestamps)
            run.last_signal_at = max(timestamps)
            if run.signals == 0:
                run.signals = len(records)

    for cycle_path in sorted((base / "reports" / "runs").glob("paper_cycles.jsonl")):
        for row in _load_jsonl(cycle_path):
            run_id = str(row.get("run_id", "paper-cycle"))
            strategy_name = str(row.get("strategy_name", run_id))
            strategy_id = str(row.get("strategy_id") or strategy_name)
            selected_version = strategy_map.get(strategy_id)
            signals_payload = list(row.get("signals", []))
            first_signal = signals_payload[0] if signals_payload else {}
            report_path = base / "reports" / "runs" / f"{run_id}.md"
            backend_plan_path = _registered_value(row.get("backend_plan_path"))
            paper_readiness_report_path = _registered_value(row.get("paper_readiness_report_path"))
            runs[run_id] = DashboardRun(
                run_id=run_id,
                strategy_id=strategy_id,
                strategy_name=strategy_name,
                version_id=_registered_value(row.get("version_id"))
                or (selected_version.current_version_id if selected_version else None),
                spec_hash=_registered_value(row.get("spec_hash")),
                strategy_backend=_registered_value(row.get("strategy_backend"))
                or (selected_version.backend if selected_version else "python_reference"),
                execution_backend=_registered_value(row.get("execution_backend"))
                or "python_reference",
                kind="paper",
                source_path=_relpath(cycle_path, base),
                report_path=_relpath(report_path, base) if report_path.exists() else None,
                signal_log_path=None,
                backend_plan_path=backend_plan_path,
                paper_readiness_report_path=paper_readiness_report_path,
                custom_data_bindings=_backend_plan_custom_data_bindings(
                    base,
                    backend_plan_path,
                ),
                symbol=str(first_signal.get("symbol", "")),
                timeframe=selected_version.timeframe if selected_version else "",
                signals=len(signals_payload),
                assumptions=[str(note) for note in row.get("notes", [])],
                first_signal_at=_parse_datetime(row.get("started_at"))
                if row.get("started_at")
                else None,
                last_signal_at=_parse_datetime(row.get("finished_at"))
                if row.get("finished_at")
                else None,
            )

    runs_list = sorted(
        runs.values(),
        key=lambda item: (
            RUN_KIND_ORDER.index(item.kind),
            item.strategy_name.lower(),
            item.run_id,
        ),
    )
    signals.sort(key=lambda item: (item.run_id, item.timestamp, item.signal_id))
    return runs_list, signals


def _build_review_records(
    base: Path,
    signal_records: list[DashboardSignal],
    strategies: list[DashboardStrategy],
) -> list[DashboardReview]:
    signal_map = {signal.signal_id: signal for signal in signal_records}
    strategy_map = {item.strategy_id: item for item in strategies}
    review_paths = sorted((base / "reports" / "reviews").glob("*.json"))
    reviews: list[DashboardReview] = []
    for path in review_paths:
        review = ReviewCard.model_validate_json(path.read_text(encoding="utf-8"))
        strategy_id = review.strategy_name
        selected_version = strategy_map.get(strategy_id)
        reviews.append(
            DashboardReview(
                signal_id=review.signal_id,
                strategy_id=strategy_id,
                strategy_name=review.strategy_name,
                verdict=review.verdict,
                confidence=review.confidence,
                model=review.model,
                created_at=review.created_at,
                timestamp=review.timestamp,
                action_suggestion=review.action_suggestion,
                path=_relpath(path, base),
                context_path=_context_path(base, review.signal_id),
            )
        )
        if review.signal_id in signal_map and selected_version:
            signal_map[review.signal_id].review_path = _relpath(path, base)
            signal_map[review.signal_id].version_id = selected_version.current_version_id
    reviews.sort(key=lambda item: (item.strategy_name.lower(), item.signal_id))
    return reviews


def _build_context_records(
    base: Path,
    signal_records: list[DashboardSignal],
) -> list[DashboardContext]:
    signal_map = {signal.signal_id: signal for signal in signal_records}
    context_paths = sorted((base / "reports" / "context").glob("*.json"))
    contexts: list[DashboardContext] = []
    for path in context_paths:
        raw = json.loads(path.read_text(encoding="utf-8"))
        signal_id = str(raw.get("signal_id", path.stem))
        event_count = len(raw.get("events", []))
        macro_count = len(raw.get("macro", []))
        news_count = len(raw.get("news", []))
        if raw.get("generated_at"):
            generated_at = _parse_datetime(raw.get("generated_at"))
        else:
            generated_at = _file_mtime(path)
        context = DashboardContext(
            signal_id=signal_id,
            symbol=str(raw.get("symbol", "")),
            generated_at=generated_at,
            event_count=event_count,
            macro_count=macro_count,
            news_count=news_count,
            notes=[str(item) for item in raw.get("notes", [])],
            path=_relpath(path, base),
        )
        contexts.append(context)
        if signal_id in signal_map:
            signal_map[signal_id].context_path = _relpath(path, base)
    contexts.sort(key=lambda item: (item.signal_id, item.generated_at))
    return contexts


def _build_journal_records(base: Path) -> list[DashboardJournalEntry]:
    journal_paths = sorted((base / "journal").glob("*.json"))
    entries: list[DashboardJournalEntry] = []
    for path in journal_paths:
        entry = TradeJournalEntry.model_validate_json(path.read_text(encoding="utf-8"))
        entries.append(
            DashboardJournalEntry(
                id=entry.id,
                signal_id=entry.signal_id,
                action=entry.action,
                notes=entry.notes,
                outcome=entry.outcome,
                created_at=entry.created_at,
                path=_relpath(path, base),
            )
        )
    entries.sort(key=lambda item: (item.created_at, item.id))
    return entries


def _build_order_records(base: Path) -> list[DashboardOrder]:
    order_records: list[DashboardOrder] = []
    paper_root = base / "reports" / "paper"
    for path in sorted(paper_root.glob("*.jsonl")):
        for row in _load_jsonl(path):
            required_keys = {
                "id",
                "signal_id",
                "strategy_name",
                "symbol",
                "side",
                "qty",
                "status",
            }
            if required_keys.issubset(row):
                order_records.append(
                    DashboardOrder(
                        id=str(row["id"]),
                        signal_id=str(row["signal_id"]),
                        strategy_name=str(row["strategy_name"]),
                        strategy_id=row.get("strategy_id"),
                        version_id=_registered_value(row.get("version_id")),
                        spec_hash=_registered_value(row.get("spec_hash")),
                        strategy_backend=_registered_value(row.get("strategy_backend"))
                        or "python_reference",
                        execution_backend=_registered_value(row.get("execution_backend"))
                        or "python_reference",
                        symbol=str(row["symbol"]),
                        side=str(row["side"]),
                        qty=float(row["qty"]),
                        status=str(row["status"]),
                        paper=bool(row.get("paper", True)),
                        submitted_at=_parse_datetime(row["submitted_at"]),
                        path=_relpath(path, base),
                    )
                )
    order_records.sort(key=lambda item: (item.submitted_at, item.id))
    return order_records


def _build_paper_position_records(base: Path) -> list[DashboardPaperPosition]:
    path = base / "reports" / "paper" / "positions.json"
    if not path.exists():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    rows = raw.get("positions", []) if isinstance(raw, dict) else []
    positions: list[DashboardPaperPosition] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        positions.append(
            DashboardPaperPosition(
                symbol=str(row.get("symbol", "")),
                qty=float(row.get("qty", 0) or 0),
                market_value=_optional_float(row.get("market_value")),
                cost_basis=_optional_float(row.get("cost_basis")),
                unrealized_pl=_optional_float(row.get("unrealized_pl")),
                unrealized_plpc=_optional_float(row.get("unrealized_plpc")),
                current_price=_optional_float(row.get("current_price")),
                side=str(row.get("side", "")),
                updated_at=_parse_datetime(str(row.get("updated_at"))),
                paper=bool(row.get("paper", True)),
                path=_relpath(path, base),
            )
        )
    positions.sort(key=lambda item: (item.symbol, item.side))
    return positions


def _build_paper_readiness_records(base: Path) -> list[DashboardPaperReadinessReport]:
    records: list[DashboardPaperReadinessReport] = []
    root = base / "reports" / "paper" / "readiness"
    if not root.exists():
        return records
    for path in sorted(root.glob("*.json")):
        raw = json.loads(path.read_text(encoding="utf-8"))
        checks = [
            DashboardPaperReadinessCheck(
                name=str(check.get("name", "")),
                status=str(check.get("status", "blocked")),  # type: ignore[arg-type]
                message=str(check.get("message", "")),
                suggested_actions=[str(action) for action in check.get("suggested_actions", [])],
            )
            for check in raw.get("checks", [])
            if isinstance(check, dict)
        ]
        records.append(
            DashboardPaperReadinessReport(
                strategy_name=str(raw.get("strategy_name", path.stem)),
                strategy_id=str(raw.get("strategy_name", path.stem)),
                status=str(raw.get("status", "blocked")),  # type: ignore[arg-type]
                ready=bool(raw.get("ready", False)),
                generated_at=_parse_datetime(raw.get("generated_at") or _file_mtime(path)),
                path=_relpath(path, base),
                report_markdown_path=_registered_value(raw.get("report_markdown_path")),
                blocking_checks=[check.name for check in checks if check.status == "blocked"],
                warning_checks=[check.name for check in checks if check.status == "warning"],
                checks=checks,
            )
        )
    return records


def _build_audit_records(
    base: Path,
    journal_records: list[DashboardJournalEntry],
    order_records: list[DashboardOrder],
) -> list[DashboardAuditEvent]:
    audit_records: list[DashboardAuditEvent] = []
    for entry in journal_records:
        audit_records.append(
            DashboardAuditEvent(
                id=entry.id,
                kind="journal",
                signal_id=entry.signal_id,
                created_at=entry.created_at,
                action=entry.action,
                target=entry.signal_id,
                source_path=entry.path,
                details={"notes": entry.notes, "outcome": entry.outcome},
            )
        )
    for order in order_records:
        audit_records.append(
            DashboardAuditEvent(
                id=order.id,
                kind="paper_order",
                signal_id=order.signal_id,
                created_at=order.submitted_at,
                action="paper_order",
                target=f"{order.symbol} {order.side} x{order.qty:g}",
                source_path=order.path,
                details={
                    "status": order.status,
                    "paper": order.paper,
                    "strategy_name": order.strategy_name,
                },
            )
        )
    for index, row in enumerate(_load_paper_kill_switch_events(base), start=1):
        enabled = bool(row.get("enabled", False))
        updated_at = _parse_datetime(str(row.get("updated_at")))
        audit_records.append(
            DashboardAuditEvent(
                id=f"paper_kill_switch_{index}",
                kind="paper_kill_switch",
                signal_id=None,
                created_at=updated_at,
                action="enable" if enabled else "clear",
                target="paper_execution",
                source_path="reports/paper/kill_switch_events.jsonl",
                details={
                    "enabled": enabled,
                    "reason": str(row.get("reason", "")),
                    "updated_by": str(row.get("updated_by", "system")),
                },
            )
        )
    for index, row in enumerate(_load_dashboard_command_events(base), start=1):
        created_at = _parse_datetime(str(row.get("created_at")))
        audit_records.append(
            DashboardAuditEvent(
                id=f"dashboard_command_{index}",
                kind="dashboard_command",
                signal_id=None,
                created_at=created_at,
                action=str(row.get("status", "unknown")),
                target=str(row.get("action", "dashboard_command")),
                source_path="reports/dashboard/commands/events.jsonl",
                details={
                    "command_id": str(row.get("command_id", "")),
                    "actor": str(row.get("actor", "")),
                    "reason": str(row.get("reason", "")),
                    "plan_path": row.get("plan_path"),
                    "result_path": row.get("result_path"),
                    "message": str(row.get("message", "")),
                },
            )
        )
    audit_records.sort(key=lambda item: (item.created_at, item.id))
    return audit_records


def _load_paper_kill_switch_events(base: Path) -> list[dict[str, Any]]:
    path = base / "reports" / "paper" / "kill_switch_events.jsonl"
    if not path.exists():
        return []
    return _load_jsonl(path)


def _load_dashboard_command_events(base: Path) -> list[dict[str, Any]]:
    path = base / "reports" / "dashboard" / "commands" / "events.jsonl"
    if not path.exists():
        return []
    return _load_jsonl(path)


def _build_group_records(strategies: list[DashboardStrategy]) -> list[DashboardGroup]:
    groups: list[DashboardGroup] = []
    dimensions = {
        "model_role": lambda item: item.model_role,
        "risk_tier": lambda item: item.risk_tier,
        "lifecycle": lambda item: item.lifecycle,
        "timeframe": lambda item: item.timeframe,
        "execution_mode": lambda item: item.execution_mode,
        "data_source": lambda item: item.data_source,
        "backend": lambda item: item.backend,
    }
    for category, extractor in dimensions.items():
        buckets: dict[str, list[DashboardStrategy]] = defaultdict(list)
        for item in strategies:
            buckets[extractor(item)].append(item)
        for value, members in buckets.items():
            groups.append(
                DashboardGroup(
                    group_id=f"{category}:{value}",
                    category=category,
                    label=value,
                    strategy_ids=sorted(member.strategy_id for member in members),
                    strategy_count=len(members),
                    active_strategy_count=sum(
                        1 for member in members if member.lifecycle == "active"
                    ),
                    model_roles=sorted({member.model_role for member in members}),
                    risk_tiers=sorted({member.risk_tier for member in members}),
                    lifecycles=sorted({member.lifecycle for member in members}),
                    timeframes=sorted({member.timeframe for member in members}),
                    execution_modes=sorted({member.execution_mode for member in members}),
                    backends=sorted({member.backend for member in members}),
                )
            )
    groups.sort(key=lambda item: (item.category, item.label))
    return groups


def _build_data_comparison_records(base: Path) -> list[DashboardDataComparison]:
    records: list[DashboardDataComparison] = []
    for path in sorted((base / "reports" / "data" / "comparisons").glob("*.json")):
        raw = json.loads(path.read_text(encoding="utf-8"))
        raw.setdefault("report_json_path", _relpath(path, base))
        raw.setdefault("report_markdown_path", _relpath(path.with_suffix(".md"), base))
        records.append(DashboardDataComparison.model_validate(raw))
    records.sort(
        key=lambda item: (
            item.symbol,
            item.timeframe,
            item.left_source,
            item.right_source,
        )
    )
    return records


def _build_workflow_records(base: Path) -> list[DashboardWorkflowReport]:
    records: list[DashboardWorkflowReport] = []
    root = base / "reports" / "workflows"
    if not root.exists():
        return records
    for path in sorted(root.glob("*.verify.json")):
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if not isinstance(raw, dict):
            continue
        status = str(raw.get("status", "warning"))
        if status not in {"ok", "warning", "blocked"}:
            status = "warning"
        paper_status = _registered_value(raw.get("paper_readiness_status"))
        if paper_status not in {"ok", "warning", "blocked"}:
            paper_status = None
        markdown_path = path.with_suffix(".md")
        strategy_name = str(raw.get("strategy_name") or path.name.removesuffix(".verify.json"))
        records.append(
            DashboardWorkflowReport(
                strategy_name=strategy_name,
                strategy_id=str(raw.get("strategy_id") or strategy_name),
                status=status,  # type: ignore[arg-type]
                source_path=str(raw.get("source_path") or ""),
                spec_hash=_registered_value(raw.get("spec_hash")),
                backtest_run_id=_registered_value(raw.get("backtest_run_id")),
                scan_signal_count=int(raw.get("scan_signal_count", 0) or 0),
                paper_readiness_status=paper_status,  # type: ignore[arg-type]
                paper_ready=bool(raw.get("paper_ready", False)),
                output_paths=[
                    str(output_path) for output_path in raw.get("output_paths", []) if output_path
                ],
                path=_relpath(path, base),
                report_markdown_path=_relpath(markdown_path, base)
                if markdown_path.exists()
                else None,
            )
        )
    records.sort(key=lambda item: (item.strategy_name.lower(), item.path))
    return records


def _build_readiness_record(base: Path) -> DashboardReadinessReport | None:
    path = base / "reports" / "readiness" / "readiness.json"
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    if not isinstance(raw, dict):
        return None
    markdown_path = path.with_suffix(".md")
    return DashboardReadinessReport(
        status=_operational_status(raw.get("status")),
        ready=bool(raw.get("ready", False)),
        generated_at=_optional_datetime(raw.get("generated_at")),
        path=_relpath(path, base),
        report_markdown_path=_relpath(markdown_path, base) if markdown_path.exists() else None,
        checks=[
            _operational_check(check) for check in raw.get("checks", []) if isinstance(check, dict)
        ],
    )


def _build_deployment_record(base: Path) -> DashboardDeploymentReport | None:
    path = base / "reports" / "deployment" / "prepare.json"
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    if not isinstance(raw, dict):
        return None
    markdown_path = path.with_suffix(".md")
    return DashboardDeploymentReport(
        status=_operational_status(raw.get("status")),
        ready=bool(raw.get("ready", False)),
        generated_at=_optional_datetime(raw.get("generated_at")),
        path=_relpath(path, base),
        report_markdown_path=_relpath(markdown_path, base) if markdown_path.exists() else None,
        steps=[_deployment_step(step) for step in raw.get("steps", []) if isinstance(step, dict)],
    )


def _operational_check(raw: dict[str, Any]) -> DashboardOperationalCheck:
    return DashboardOperationalCheck(
        name=str(raw.get("name", "")),
        status=_operational_status(raw.get("status")),
        message=str(raw.get("message", "")),
        suggested_actions=[str(action) for action in raw.get("suggested_actions", []) if action],
        details=raw.get("details", {}) if isinstance(raw.get("details", {}), dict) else {},
    )


def _deployment_step(raw: dict[str, Any]) -> DashboardDeploymentStep:
    return DashboardDeploymentStep(
        name=str(raw.get("name", "")),
        status=_operational_status(raw.get("status")),
        message=str(raw.get("message", "")),
        suggested_actions=[str(action) for action in raw.get("suggested_actions", []) if action],
        details=raw.get("details", {}) if isinstance(raw.get("details", {}), dict) else {},
        output_paths=[str(path) for path in raw.get("output_paths", []) if path],
    )


def _operational_status(value: object) -> Literal["ok", "warning", "blocked"]:
    text = str(value or "warning")
    if text in {"ok", "warning", "blocked"}:
        return text  # type: ignore[return-value]
    return "warning"


def _backend_plan_custom_data_bindings(
    base: Path,
    backend_plan_path: str | None,
) -> list[DashboardCustomDataBinding]:
    if not backend_plan_path:
        return []
    path = Path(backend_plan_path)
    if not path.is_absolute():
        path = base / path
    if not path.exists():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    bindings = raw.get("custom_data_bindings", []) if isinstance(raw, dict) else []
    records: list[DashboardCustomDataBinding] = []
    for item in bindings:
        if not isinstance(item, dict):
            continue
        status = str(item.get("point_in_time_status") or "missing")
        if status not in {"complete", "partial", "missing"}:
            status = "missing"
        records.append(
            DashboardCustomDataBinding(
                factor_name=str(item.get("factor_name", "")),
                source=str(item.get("source", "")),
                path=str(item.get("path", "")),
                field=str(item.get("field", "")),
                record_count=int(item.get("record_count", 0) or 0),
                first_timestamp=_registered_value(item.get("first_timestamp")),
                last_timestamp=_registered_value(item.get("last_timestamp")),
                point_in_time_status=status,  # type: ignore[arg-type]
                replay_warnings=[str(value) for value in item.get("replay_warnings", [])],
            )
        )
    return records


def build_feature_packet_records(base: Path | None = None) -> list[DashboardFeaturePacket]:
    base = base or project_root()
    records: list[DashboardFeaturePacket] = []
    for path in sorted((base / "feature_logs").glob("*.jsonl")):
        rows = _load_jsonl(path)
        dict_rows = [row for row in rows if isinstance(row, dict)]
        timestamps: list[datetime] = []
        invalid_timestamps = 0
        for row in dict_rows:
            if not row.get("timestamp"):
                continue
            try:
                timestamps.append(_parse_datetime(str(row["timestamp"])))
            except ValueError:
                invalid_timestamps += 1
        field_names = sorted({key for row in dict_rows for key in row.keys() if key != "timestamp"})
        key_sets = [set(row) for row in dict_rows]
        has_timestamp = bool(dict_rows) and all("timestamp" in keys for keys in key_sets)
        has_published_at = bool(dict_rows) and all("published_at" in keys for keys in key_sets)
        has_fetched_at = bool(dict_rows) and all("fetched_at" in keys for keys in key_sets)
        has_dedupe_key = bool(dict_rows) and all("dedupe_key" in keys for keys in key_sets)
        has_schema_version = bool(dict_rows) and all("schema_version" in keys for keys in key_sets)
        dedupe_keys = [str(row["dedupe_key"]) for row in dict_rows if row.get("dedupe_key")]
        duplicate_dedupe_keys = sorted(
            {dedupe_key for dedupe_key in dedupe_keys if dedupe_keys.count(dedupe_key) > 1}
        )
        warnings: list[str] = []
        if not has_timestamp:
            warnings.append("feature packet rows must include timestamp for replay")
        if invalid_timestamps:
            warnings.append(f"{invalid_timestamps} timestamp value(s) are not ISO-8601 parseable")
        if not has_published_at:
            warnings.append("published_at is missing for at least one row")
        if not has_fetched_at:
            warnings.append("fetched_at is missing for at least one row")
        if not has_dedupe_key:
            warnings.append("dedupe_key is missing for at least one row")
        if not has_schema_version:
            warnings.append("schema_version is missing for at least one row")
        if duplicate_dedupe_keys:
            warnings.append(
                "duplicate dedupe_key value(s): " + ", ".join(duplicate_dedupe_keys[:5])
            )
        if (
            has_timestamp
            and not invalid_timestamps
            and has_published_at
            and has_fetched_at
            and has_dedupe_key
            and has_schema_version
            and not duplicate_dedupe_keys
        ):
            point_in_time_status = "complete"
        elif has_timestamp:
            point_in_time_status = "partial"
        else:
            point_in_time_status = "missing"
        records.append(
            DashboardFeaturePacket(
                path=_relpath(path, base),
                record_count=len(rows),
                field_names=field_names,
                first_timestamp=min(timestamps).isoformat() if timestamps else None,
                last_timestamp=max(timestamps).isoformat() if timestamps else None,
                has_timestamp=has_timestamp,
                has_published_at=has_published_at,
                has_fetched_at=has_fetched_at,
                has_dedupe_key=has_dedupe_key,
                has_schema_version=has_schema_version,
                point_in_time_status=point_in_time_status,
                replay_warnings=warnings,
            )
        )
    return records


def _build_summary(
    *,
    base: Path,
    generated_at: datetime,
    strategies: list[DashboardStrategy],
    versions: list[DashboardVersion],
    runs: list[DashboardRun],
    signals: list[DashboardSignal],
    reviews: list[DashboardReview],
    contexts: list[DashboardContext],
    journals: list[DashboardJournalEntry],
    orders: list[DashboardOrder],
    audits: list[DashboardAuditEvent],
    data_comparisons: list[DashboardDataComparison],
    feature_packets: list[DashboardFeaturePacket],
    workflow_reports: list[DashboardWorkflowReport],
    readiness_report: DashboardReadinessReport | None,
    deployment_report: DashboardDeploymentReport | None,
    paper_readiness_reports: list[DashboardPaperReadinessReport],
) -> DashboardSummary:
    lifecycle_counts = Counter(strategy.lifecycle for strategy in strategies)
    model_role_counts = Counter(strategy.model_role for strategy in strategies)
    risk_counts = Counter(strategy.risk_tier for strategy in strategies)
    backend_counts = Counter(strategy.backend for strategy in strategies)
    backend_status_counts = Counter(strategy.backend_status for strategy in strategies)
    run_kind_counts = Counter(run.kind for run in runs)
    paper_readiness_counts = Counter(report.status for report in paper_readiness_reports)
    paper_status = build_paper_status(base)
    compatibility_counts: dict[str, dict[str, int]] = {}
    capabilities_to_report = [
        "python_mvp_backtest",
        "tradingview_pine_strategy",
        "nautilus_trader_backend",
        "alpaca_paper_execution",
        "llm_quant_workflow",
    ]
    for capability in capabilities_to_report:
        statuses = Counter(
            finding.status
            for version in versions
            for finding in version.compatibility
            if finding.capability == capability
        )
        compatibility_counts[capability] = {
            status: statuses.get(status, 0) for status in sorted(statuses)
        }
    notes = [
        (
            "Version binding is derived from current file snapshots until immutable historical "
            "version records are added."
        ),
        "Dashboard catalog is read-only and rebuildable from repo artifacts.",
    ]
    if not orders:
        notes.append("No paper order records were found under reports/paper.")
    return DashboardSummary(
        source_root=str(base),
        generated_at=generated_at,
        strategy_count=len(strategies),
        version_count=len(versions),
        run_count=len(runs),
        signal_count=len(signals),
        review_count=len(reviews),
        context_count=len(contexts),
        journal_count=len(journals),
        order_count=len(orders),
        audit_count=len(audits),
        data_comparison_count=len(data_comparisons),
        feature_packet_count=len(feature_packets),
        workflow_report_count=len(workflow_reports),
        readiness_status=readiness_report.status if readiness_report else "missing",
        readiness_ready=readiness_report.ready if readiness_report else False,
        readiness_warning_count=_operational_count(readiness_report.checks, "warning")
        if readiness_report
        else 0,
        readiness_blocked_count=_operational_count(readiness_report.checks, "blocked")
        if readiness_report
        else 0,
        deployment_status=deployment_report.status if deployment_report else "missing",
        deployment_ready=deployment_report.ready if deployment_report else False,
        deployment_warning_count=_operational_count(deployment_report.steps, "warning")
        if deployment_report
        else 0,
        deployment_blocked_count=_operational_count(deployment_report.steps, "blocked")
        if deployment_report
        else 0,
        active_strategy_count=sum(1 for item in strategies if item.lifecycle == "active"),
        paper_auto_strategy_count=sum(
            1
            for item in strategies
            if item.lifecycle == "active"
            and item.execution_mode == "paper_auto"
            and item.broker == "alpaca_paper"
        ),
        paper_kill_switch_enabled=paper_status.kill_switch.enabled,
        paper_open_order_count=paper_status.open_order_count,
        paper_order_status_counts=dict(sorted(paper_status.order_status_counts.items())),
        paper_account_equity=paper_status.account_equity,
        paper_account_cash=paper_status.account_cash,
        paper_account_buying_power=paper_status.account_buying_power,
        paper_account_portfolio_value=paper_status.account_portfolio_value,
        paper_account_snapshot_at=paper_status.account_snapshot_at,
        paper_position_count=paper_status.position_count,
        paper_total_position_market_value=paper_status.total_position_market_value,
        paper_total_unrealized_pl=paper_status.total_unrealized_pl,
        paper_positions_snapshot_at=paper_status.positions_snapshot_at,
        paper_reconciliation_status=paper_status.reconciliation_status,
        paper_reconciliation_issue_count=paper_status.reconciliation_issue_count,
        paper_reconciliation_report_path=paper_status.reconciliation_report_path,
        paper_alert_status=paper_status.alert_status,
        paper_alert_count=paper_status.alert_count,
        paper_alert_report_path=paper_status.alert_report_path,
        paper_readiness_count=len(paper_readiness_reports),
        paper_readiness_status_counts=dict(sorted(paper_readiness_counts.items())),
        strategy_backend_counts=dict(sorted(backend_counts.items())),
        backend_status_counts=dict(sorted(backend_status_counts.items())),
        pure_quant_count=model_role_counts.get("pure_quant", 0),
        quant_review_count=model_role_counts.get("quant_review", 0),
        quant_scan_count=model_role_counts.get("quant_scan", 0),
        quant_orchestrator_count=model_role_counts.get("quant_orchestrator", 0),
        stable_count=risk_counts.get("stable", 0),
        moderate_count=risk_counts.get("moderate", 0),
        high_count=risk_counts.get("high", 0),
        lifecycle_counts=dict(sorted(lifecycle_counts.items())),
        model_role_counts=dict(sorted(model_role_counts.items())),
        risk_counts=dict(sorted(risk_counts.items())),
        run_kind_counts=dict(sorted(run_kind_counts.items())),
        compatibility_counts=compatibility_counts,
        notes=notes,
    )


def _render_catalog_markdown(catalog: DashboardCatalog) -> str:
    summary = catalog.summary
    lines = [
        "# Open Composer Dashboard Catalog",
        "",
        f"- Generated at: `{catalog.generated_at.isoformat()}`",
        f"- Source root: `{catalog.source_root}`",
        f"- Version binding: `{summary.version_binding_mode}`",
        "",
        "## Summary",
        "",
        "| Metric | Value |",
        "|---|---:|",
        f"| Strategies | {summary.strategy_count} |",
        f"| Versions | {summary.version_count} |",
        f"| Runs | {summary.run_count} |",
        f"| Signals | {summary.signal_count} |",
        f"| Reviews | {summary.review_count} |",
        f"| Context packets | {summary.context_count} |",
        f"| Journal entries | {summary.journal_count} |",
        f"| Paper orders | {summary.order_count} |",
        f"| Audit events | {summary.audit_count} |",
        f"| Data comparisons | {summary.data_comparison_count} |",
        f"| Feature packets | {summary.feature_packet_count} |",
        f"| Workflow reports | {summary.workflow_report_count} |",
        f"| Readiness | {summary.readiness_status} |",
        f"| Deployment prepare | {summary.deployment_status} |",
        f"| Active strategies | {summary.active_strategy_count} |",
        f"| Active paper_auto strategies | {summary.paper_auto_strategy_count} |",
        f"| Paper kill switch | {'on' if summary.paper_kill_switch_enabled else 'off'} |",
        f"| Open paper orders | {summary.paper_open_order_count} |",
        f"| Paper account equity | {_money(summary.paper_account_equity)} |",
        f"| Paper account snapshot | {_format_optional_dt(summary.paper_account_snapshot_at)} |",
        f"| Paper positions | {summary.paper_position_count} |",
        (
            "| Paper positions snapshot | "
            f"{_format_optional_dt(summary.paper_positions_snapshot_at)} |"
        ),
        f"| Paper unrealized PnL | {_money(summary.paper_total_unrealized_pl)} |",
        f"| Paper reconciliation | {summary.paper_reconciliation_status} "
        f"({summary.paper_reconciliation_issue_count} issues) |",
        f"| Paper alerts | {summary.paper_alert_status} ({summary.paper_alert_count} alerts) |",
        "",
        "## Capability Mix",
        "",
        "| Class | Count |",
        "|---|---:|",
        f"| pure_quant | {summary.pure_quant_count} |",
        f"| quant_review | {summary.quant_review_count} |",
        f"| quant_scan | {summary.quant_scan_count} |",
        f"| quant_orchestrator | {summary.quant_orchestrator_count} |",
        "",
        "## Backend Mix",
        "",
        "| Backend | Count |",
        "|---|---:|",
        *[
            f"| {backend} | {count} |"
            for backend, count in (
                summary.strategy_backend_counts or {"python_reference": 0}
            ).items()
        ],
        "",
        "## Backend Readiness",
        "",
        "| Status | Count |",
        "|---|---:|",
        *[
            f"| {status} | {count} |"
            for status, count in (summary.backend_status_counts or {"supported": 0}).items()
        ],
        "",
        "## Risk Mix",
        "",
        "| Tier | Count |",
        "|---|---:|",
        f"| stable | {summary.stable_count} |",
        f"| moderate | {summary.moderate_count} |",
        f"| high | {summary.high_count} |",
        "",
        "## Notes",
        "",
        *[f"- {note}" for note in summary.notes],
        "",
        "## Data Comparisons",
        "",
        "| Pair | Coverage | Max Close Diff bps | Missing Left | Missing Right |",
        "|---|---:|---:|---:|---:|",
        *[
            (
                f"| {item.symbol} {item.timeframe} {item.left_source}/{item.right_source} "
                f"| {item.matched_coverage_pct:.2f}% "
                f"| {item.max_abs_close_diff_bps:.2f} "
                f"| {item.missing_left_rows} "
                f"| {item.missing_right_rows} |"
            )
            for item in catalog.data_comparisons
        ],
        "",
        "## Run Evidence",
        "",
        "| Run | Strategy | Evidence | Sanity | Warnings |",
        "|---|---|---|---|---:|",
        *[
            (
                f"| {run.run_id} | {run.strategy_name} | "
                f"{run.evidence_level or 'unknown'} | "
                f"{run.data_sanity_status or 'unknown'} | "
                f"{len(run.data_sanity_warnings)} |"
            )
            for run in catalog.runs
        ],
        "",
        "## Derived Facets",
        "",
        *[f"- `{group.group_id}` -> {group.strategy_count} strategies" for group in catalog.groups],
    ]
    return "\n".join(lines) + "\n"


def _render_review_markdown(catalog: DashboardCatalog) -> str:
    summary = catalog.summary
    active_strategies = [
        strategy for strategy in catalog.strategies if strategy.lifecycle == "active"
    ]
    paper_auto_ready = [
        strategy
        for strategy in catalog.strategies
        if strategy.lifecycle == "active"
        and strategy.execution_mode == "paper_auto"
        and strategy.broker == "alpaca_paper"
    ]
    lines = [
        "# Dashboard D0 Review",
        "",
        f"- Generated at: `{catalog.generated_at.isoformat()}`",
        f"- Source root: `{catalog.source_root}`",
        "",
        "## Current Capability Baseline",
        "",
        f"- Strategies indexed: `{summary.strategy_count}`",
        f"- Versions indexed: `{summary.version_count}`",
        f"- Runs indexed: `{summary.run_count}`",
        f"- Signals indexed: `{summary.signal_count}`",
        f"- Reviews indexed: `{summary.review_count}`",
        f"- Context packets indexed: `{summary.context_count}`",
        f"- Journal entries indexed: `{summary.journal_count}`",
        f"- Data comparisons indexed: `{summary.data_comparison_count}`",
        f"- Feature packets indexed: `{summary.feature_packet_count}`",
        f"- Workflow reports indexed: `{summary.workflow_report_count}`",
        f"- Readiness status: `{summary.readiness_status}` ready=`{summary.readiness_ready}`",
        f"- Deployment status: `{summary.deployment_status}` ready=`{summary.deployment_ready}`",
        "",
        "## Backend Snapshot",
        "",
        f"- Strategy backends: `{summary.strategy_backend_counts}`",
        f"- Backend readiness: `{summary.backend_status_counts}`",
        f"- Paper kill switch: `{'on' if summary.paper_kill_switch_enabled else 'off'}`",
        f"- Paper order status counts: `{summary.paper_order_status_counts}`",
        f"- Paper account equity: `{_money(summary.paper_account_equity)}`",
        f"- Paper account snapshot: `{_format_optional_dt(summary.paper_account_snapshot_at)}`",
        f"- Paper positions: `{summary.paper_position_count}`",
        f"- Paper positions snapshot: `{_format_optional_dt(summary.paper_positions_snapshot_at)}`",
        f"- Paper unrealized PnL: `{_money(summary.paper_total_unrealized_pl)}`",
        f"- Paper reconciliation: `{summary.paper_reconciliation_status}` "
        f"issues=`{summary.paper_reconciliation_issue_count}`",
        f"- Paper alerts: `{summary.paper_alert_status}` alerts=`{summary.paper_alert_count}`",
        "",
        "## What The Dashboard Can Trust Now",
        "",
        "- Strategy catalog can be rebuilt from repo files and report artifacts.",
        (
            "- Capability badges can come from `StrategySpec` and "
            "`assess_strategy_capabilities` instead of mock data."
        ),
        "- Version views can show current file snapshots and file provenance.",
        "- Signal, review, context, and journal pages can be populated from existing artifacts.",
        "- Paper status and kill switch events can be read from local paper artifacts.",
        "- Data comparison reports can show latest low-cost source coverage and caveats.",
        "- Feature packet logs can show replay inputs for llm_feature and feature_packet factors.",
        (
            "- Backtest rows can show `data_sanity` evidence levels and warning counts, so "
            "sample/fallback/short-window results are not presented as benchmark evidence."
        ),
        (
            "- A static read-only Dashboard can now be generated at "
            "`reports/dashboard/index.html` and `reports/dashboard/strategies/*.html` "
            "from this catalog."
        ),
        "",
        "## What The Dashboard Should Not Pretend Yet",
        "",
        "- Historical version lineage is now partially available from version manifests, but a "
        "full immutable event log is still not present.",
        (
            "- Remote paper write actions must stay disabled until the Dashboard calls the "
            "existing command gate and confirmation flow."
        ),
        (
            "- LLM pages must stay advisory until their prompts, model refs, and replay caches "
            "are wired through the backend."
        ),
        "- Warning-level backtests must not be promoted from Dashboard metrics alone.",
        "",
        "## Strategy Mix",
        "",
        f"- Active strategies: `{summary.active_strategy_count}`",
        f"- Active paper_auto strategies: `{summary.paper_auto_strategy_count}`",
        f"- Paper kill switch: `{'on' if summary.paper_kill_switch_enabled else 'off'}`",
        f"- Open paper orders: `{summary.paper_open_order_count}`",
        f"- Paper positions: `{summary.paper_position_count}`",
        f"- Paper reconciliation issues: `{summary.paper_reconciliation_issue_count}`",
        f"- Paper alerts: `{summary.paper_alert_count}`",
        f"- Pure quant strategies: `{summary.pure_quant_count}`",
        f"- Quant + review strategies: `{summary.quant_review_count}`",
        f"- Quant + scan strategies: `{summary.quant_scan_count}`",
        f"- Quant + orchestrator strategies: `{summary.quant_orchestrator_count}`",
        "",
        "## Review Verdict",
        "",
        (
            "- The current Figma dashboard can be turned into a real control plane, but only "
            "after it reads from this catalog instead of hard-coded mock arrays."
        ),
        "- The first production version should be read-only, capability-aware, and source-linked.",
        (
            "- Paper kill switch/status can be displayed now; Dashboard write controls still "
            "need a command-service wrapper and explicit confirmation."
        ),
        "",
        "## Recommended Next Steps",
        "",
        (
            "1. Keep the static read-only HTML Dashboard as the first real product surface "
            "for Dashboard review, including per-strategy detail pages."
        ),
        (
            "2. If the Figma frontend is restored, wire it to "
            "`reports/dashboard/catalog.json` instead of mock arrays."
        ),
        (
            "3. Render the read-only pages first: overview, strategy library, strategy detail, "
            "versions, context, review, and audit."
        ),
        (
            "4. Add write buttons only after command service, confirmation flow, and audit "
            "records exist."
        ),
        "",
        "## Active Strategy Snapshot",
        "",
        *[
            (
                f"- `{strategy.strategy_name}` (`{strategy.lifecycle}`, "
                f"`{strategy.model_role}`, `{strategy.risk_tier}`, `{strategy.backend}`)"
            )
            for strategy in active_strategies
        ],
    ]
    if not active_strategies:
        lines.append("- No active strategies were indexed.")
    lines.extend(
        [
            "",
            "## Paper Auto Snapshot",
            "",
            *[
                f"- `{strategy.strategy_name}` -> `{strategy.current_version_id}` "
                f"[{strategy.backend}]"
                for strategy in paper_auto_ready
            ],
        ]
    )
    if not paper_auto_ready:
        lines.append("- No active paper_auto strategies were indexed.")
    return "\n".join(lines) + "\n"


def _parse_report(path: Path) -> dict[str, Any]:
    lines = path.read_text(encoding="utf-8").splitlines()
    data: dict[str, Any] = {"assumptions": [], "data_sanity_warnings": []}
    section = ""
    for line in lines:
        if line.startswith("## "):
            section = line[3:].strip().lower()
            continue
        if section == "assumptions" and line.startswith("- "):
            data.setdefault("assumptions", []).append(line[2:].strip())
            continue
        if section == "data sanity" and line.startswith("- ") and ": " in line:
            label, value = line[2:].split(": ", 1)
            key = label.lower().replace(" ", "_")
            value = _strip_backticks(value)
            if key == "warning":
                if value != "none":
                    data.setdefault("data_sanity_warnings", []).append(value)
                continue
            if key == "status":
                data["data_sanity_status"] = value
                continue
            if key in {"source", "mode", "feed", "path"}:
                data[f"data_sanity_{key}"] = value
                continue
            if key in {"bars", "signals", "trades", "warning_count"}:
                data[f"data_sanity_{key}"] = value
                continue
            data[key] = value
            continue
        if line.startswith("- ") and ": " in line:
            label, value = line[2:].split(": ", 1)
            key = label.lower().replace(" ", "_")
            if key == "closed_trades":
                key = "trades"
            if key == "total_return":
                key = "total_return_pct"
            if key == "annualized_return":
                key = "annualized_return_pct"
            data[key] = _strip_backticks(value)
    data["run_id"] = _strip_backticks(str(data.get("run_id", path.stem)))
    data["strategy_name"] = _title_from_report(path)
    if "symbol" not in data:
        data["symbol"] = ""
    if "timeframe" not in data:
        data["timeframe"] = ""
    for field in ["bars", "signals", "trades"]:
        if field in data:
            data[field] = int(str(data[field]).replace(",", "").strip())
    for field in [
        "data_sanity_bars",
        "data_sanity_signals",
        "data_sanity_trades",
        "data_sanity_warning_count",
    ]:
        if field in data:
            data[field] = int(str(data[field]).replace(",", "").strip())
    for field in [
        "start_equity",
        "end_equity",
        "total_fees",
        "annualized_return_pct",
        "sharpe_ratio",
    ]:
        if field in data:
            value = str(data[field]).replace("%", "").strip()
            data[field] = None if value == "n/a" else float(value)
    if "total_return_pct" in data:
        data["total_return_pct"] = float(str(data["total_return_pct"]).replace("%", "").strip())
    return data


def _title_from_report(path: Path) -> str:
    first = path.read_text(encoding="utf-8").splitlines()[0]
    if ": " in first:
        return first.split(": ", 1)[1].strip()
    return path.stem


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def _file_mtime(path: Path) -> datetime:
    return datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)


def _parse_datetime(value: str | datetime) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _optional_datetime(value: object) -> datetime | None:
    if value is None:
        return None
    try:
        return _parse_datetime(value if isinstance(value, datetime) else str(value))
    except ValueError:
        return None


def _operational_count(
    checks: list[DashboardOperationalCheck] | list[DashboardDeploymentStep],
    status: str,
) -> int:
    return sum(1 for check in checks if check.status == status)


def _strip_backticks(value: str) -> str:
    stripped = value.strip()
    if stripped.startswith("`") and stripped.endswith("`"):
        return stripped[1:-1]
    return stripped


def _registered_value(value: object) -> str | None:
    if value is None:
        return None
    text = str(value)
    if not text or text == "unregistered":
        return None
    return text


def _money(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"${value:,.2f}"


def _format_optional_dt(value: datetime | None) -> str:
    return value.isoformat() if value else "n/a"


def _relpath(path: Path, base: Path) -> str:
    try:
        return str(path.relative_to(base))
    except ValueError:
        return str(path)


def _ordered_unique(values: list[str], order: list[str]) -> list[str]:
    seen = set()
    ordered = []
    for item in values:
        if item not in seen:
            seen.add(item)
            ordered.append(item)
    ordered.sort(key=lambda item: order.index(item) if item in order else len(order))
    return ordered


def _union_paths(paths: Any) -> list[str]:
    flattened: list[str] = []
    for value in paths:
        flattened.extend(value)
    return sorted(set(flattened))


def _spec_note(spec: StrategySpec) -> str:
    notes = [spec.description.strip()]
    if spec.notes.intent:
        notes.append(spec.notes.intent.strip())
    if spec.notes.open_questions:
        notes.append("Questions: " + "; ".join(spec.notes.open_questions))
    return " ".join(part for part in notes if part)


def _infer_model_role(spec: StrategySpec) -> tuple[str, list[str]]:
    text = " ".join(
        part
        for part in [
            spec.description,
            spec.notes.intent,
            *spec.notes.open_questions,
        ]
        if part
    ).lower()
    non_market_caps = [
        capability
        for capability in spec.required_capabilities
        if not capability.startswith("market.")
    ]
    context_caps = [
        capability
        for capability in non_market_caps
        if capability.startswith(("events.", "news.", "macro."))
    ]
    if any(
        keyword in text
        for keyword in [
            "portfolio.",
            "strategy group",
            "strategy_group",
            "orchestrator",
            "regime selector",
            "capital allocation",
        ]
    ):
        return "quant_orchestrator", ["strategy text points to group-level orchestration"]
    if spec.llm_review.enabled:
        if any(
            keyword in text
            for keyword in ["scan", "feature", "extract", "factor", "sentiment", "rank"]
        ):
            return "quant_scan", ["LLM appears to transform context into features or signals"]
        if len(context_caps) >= 2 and "filter" not in text:
            return "quant_scan", ["multiple context capabilities suggest feature extraction"]
        reasons = ["LLM is enabled only as a review or gating layer"]
        if context_caps:
            reasons.append("context capabilities are present but framed as review input")
        return "quant_review", reasons
    if context_caps and any(
        keyword in text for keyword in ["scan", "feature", "extract", "factor"]
    ):
        return "quant_scan", ["context capabilities are used as explicit derived factors"]
    return "pure_quant", ["no LLM review role is enabled"]


def _infer_risk_tier(spec: StrategySpec) -> tuple[str, list[str]]:
    reasons: list[str] = []
    context_caps = [
        capability
        for capability in spec.required_capabilities
        if capability.startswith(("events.", "news.", "macro."))
    ]
    if (
        spec.risk.max_position_weight <= 0.1
        and spec.risk.max_trades_per_day <= 2
        and not spec.llm_review.enabled
        and len(spec.universe) == 1
    ):
        return "stable", ["single-asset, low-turnover, deterministic spec"]
    if spec.llm_review.enabled and context_caps:
        reasons.append("LLM and contextual data raise operational and replay risk")
        if len(spec.universe) > 1:
            reasons.append("multi-symbol universe raises coordination complexity")
        return "high", reasons
    if spec.risk.max_position_weight >= 0.25 or spec.risk.max_trades_per_day >= 4:
        return "high", ["position sizing or turnover is high enough to require stricter gating"]
    if len(spec.universe) > 1:
        reasons.append("multi-symbol universe but no explicit LLM gating")
    if spec.execution.mode == "paper_auto":
        reasons.append("paper_auto requires stricter monitoring even when deterministic")
    if not reasons:
        reasons.append("defaulting to moderate risk for non-trivial MVP strategies")
    return "moderate", reasons


def _context_path(base: Path, signal_id: str) -> str | None:
    path = base / "reports" / "context" / f"{signal_id}.json"
    return _relpath(path, base) if path.exists() else None
