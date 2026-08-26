from __future__ import annotations

import hashlib
import json
import math
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
from open_composer.execution_policy import resolve_execution_policy
from open_composer.feature_packets import (
    feature_packet_path_for_factor,
    feature_packet_path_label,
    inspect_feature_packet,
)
from open_composer.models.paper import PaperAccountSnapshot
from open_composer.models.strategy_spec import StrategySpec, load_strategy_spec
from open_composer.paper_authorization import (
    assess_paper_canary_authorization,
    assess_paper_order_authorization,
)
from open_composer.paper_freshness import PAPER_SNAPSHOT_STALE_SECONDS
from open_composer.paper_tca import PaperTCAValidationError, build_paper_tca_report
from open_composer.paper_validation import build_paper_validation_report
from open_composer.storage import write_json
from open_composer.strategy_capabilities import (
    assess_strategy_capabilities_for_spec,
)
from open_composer.strategy_versions import strategy_content_hash
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
    execution_substate: Literal[
        "blocked", "observation_only", "canary_authorized", "order_authorized"
    ] = "blocked"
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
        _universe_audit_check(spec, base),
        _alpaca_env_check(spec),
        _kill_switch_check(base),
        _account_snapshot_check(base),
        _positions_snapshot_check(base),
        _backend_check(spec),
        _portfolio_routing_check(spec),
        _portfolio_risk_check(spec),
        _feature_packet_binding_check(spec, base),
        _promotion_report_check(spec, base, spec_path),
        _harness_artifacts_check(spec, base),
        _paper_validation_check(spec, base),
        _paper_tca_check(spec, base),
        _canary_authorization_check(spec, base),
        _order_authorization_check(spec, base),
    ]
    if spec_path is not None and spec_path.exists():
        checks.append(_capability_check(spec, spec_path))
    status = _overall_status(checks)
    execution_substate = _execution_substate(spec, checks, status)
    ready = status == "ok" and execution_substate == "order_authorized"
    return PaperStrategyReadinessReport(
        strategy_name=spec.name,
        strategy_path=_relpath(spec_path, base) if spec_path else None,
        status=status,
        ready=ready,
        execution_substate=execution_substate,
        gate_summary=_gate_summary(checks, status, execution_substate),
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
    failed = report.blocking_checks or [
        check for check in report.checks if check.status == "warning"
    ]
    details = "; ".join(f"{check.name}: {check.message}" for check in failed)
    return f"paper strategy readiness not order-authorized: {details}"


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


def _execution_substate(
    spec: StrategySpec,
    checks: list[PaperStrategyReadinessCheck],
    status: PaperReadinessStatus,
) -> Literal["blocked", "observation_only", "canary_authorized", "order_authorized"]:
    if spec.position_direction in {"short_only", "long_short"} and status == "blocked":
        return "blocked"
    if spec.position_direction in {"short_only", "long_short"}:
        short_check = next((check for check in checks if check.name == "harness_artifacts"), None)
        if short_check is None or short_check.status != "ok":
            return "blocked"
    if status == "blocked":
        return "blocked"
    authorization = next(
        (check for check in checks if check.name == "order_authorization"),
        None,
    )
    if status == "ok" and authorization and authorization.status == "ok":
        return "order_authorized"
    canary = next((check for check in checks if check.name == "canary_authorization"), None)
    permitted_canary_warnings = {
        "matched_paper_tca",
        "order_authorization",
        "paper_validation",
    }
    non_canary_gaps = [
        check.name
        for check in checks
        if check.status != "ok"
        and check.name not in permitted_canary_warnings
        and not _authorization_only_capability_warning(check)
    ]
    if canary is not None and canary.details.get("authorized") is True and not non_canary_gaps:
        return "canary_authorized"
    return "observation_only"


def _authorization_only_capability_warning(check: PaperStrategyReadinessCheck) -> bool:
    return (
        check.name == "capability_report"
        and check.status == "warning"
        and check.details.get("capability") == "alpaca_paper_execution"
        and check.details.get("status") == "partial"
        and check.message
        == (
            "router strategies may run observation-only target-weight cycles before "
            "order authorization"
        )
    )


def _paper_validation_check(
    spec: StrategySpec,
    root: Path,
) -> PaperStrategyReadinessCheck:
    try:
        policy = resolve_execution_policy(spec, root)
    except ValueError as exc:
        return PaperStrategyReadinessCheck(
            name="paper_validation",
            status="blocked",
            message=str(exc),
        )
    notes = spec.notes.model_dump(mode="json")
    not_before = notes.get("paper_validation_start")
    raw_target_days = notes.get("minimum_bound_forward_sessions", 20)
    target_days = (
        raw_target_days
        if isinstance(raw_target_days, int) and not isinstance(raw_target_days, bool)
        else 20
    )
    payload = build_paper_validation_report(
        root=root,
        target_days=target_days,
        strategy_name=spec.name,
        spec_hash=strategy_content_hash(spec),
        execution_policy_id=policy.policy_id if policy else None,
        execution_policy_hash=policy.content_hash if policy else None,
        not_before=str(not_before) if not_before else None,
    )
    details = {
        "progress_days": payload["progress_days"],
        "target_days": payload["target_days"],
        "window_start": payload["window_start"],
        "window_end": payload["window_end"],
        "binding": payload["binding"],
        "excluded_log_count": len(payload["excluded_logs"]),
        "forward_observation_progress_days": payload["forward_observation_progress_days"],
        "forward_observation_pass": payload["forward_observation_pass"],
    }
    if payload["paper_validation_pass"]:
        return PaperStrategyReadinessCheck(
            name="paper_validation",
            status="ok",
            message=(
                f"Strategy-specific {payload['target_days']}-trading-day paper workflow "
                "validation passed."
            ),
            details=details,
        )
    return PaperStrategyReadinessCheck(
        name="paper_validation",
        status="warning",
        message=(
            "Strategy-specific paper workflow validation is incomplete: "
            f"{payload['progress_days']}/{payload['target_days']} trading days."
        ),
        details=details,
        suggested_actions=[
            f"uv run oc paper validation-report --strategy {spec.name} "
            f"--target-days {payload['target_days']}"
        ],
    )


def _paper_tca_check(
    spec: StrategySpec,
    root: Path,
) -> PaperStrategyReadinessCheck:
    notes = spec.notes.model_dump(mode="json")
    raw_minimum = notes.get("minimum_matched_tca_observations")
    if raw_minimum is None:
        return PaperStrategyReadinessCheck(
            name="matched_paper_tca",
            status="warning",
            message="Paper automation requires at least 30 matched TCA observations.",
            details={"required": True, "minimum_observations": 30},
        )
    if isinstance(raw_minimum, bool) or not isinstance(raw_minimum, int) or raw_minimum < 30:
        return PaperStrategyReadinessCheck(
            name="matched_paper_tca",
            status="blocked",
            message="minimum_matched_tca_observations must be an integer of at least 30.",
        )
    try:
        policy = resolve_execution_policy(spec, root)
    except ValueError as exc:
        return PaperStrategyReadinessCheck(
            name="matched_paper_tca",
            status="blocked",
            message=str(exc),
        )
    if policy is None:
        return PaperStrategyReadinessCheck(
            name="matched_paper_tca",
            status="blocked",
            message="Matched paper TCA requires a bound execution policy.",
        )
    epoch_value = notes.get("paper_validation_start")
    if not epoch_value:
        return PaperStrategyReadinessCheck(
            name="matched_paper_tca",
            status="blocked",
            message="Matched paper TCA requires notes.paper_validation_start.",
        )
    epoch = str(epoch_value)
    if "T" not in epoch:
        epoch += "T00:00:00+00:00"
    try:
        payload = build_paper_tca_report(
            root=root,
            strategy_name=spec.name,
            spec_hash=strategy_content_hash(spec),
            execution_policy_id=policy.policy_id,
            execution_policy_hash=policy.content_hash,
            epoch=epoch,
            minimum_observations=raw_minimum,
        )
    except PaperTCAValidationError as exc:
        return PaperStrategyReadinessCheck(
            name="matched_paper_tca",
            status="blocked",
            message=str(exc),
        )
    details = {
        "valid_observation_count": payload["valid_observation_count"],
        "excluded_observation_count": payload["excluded_observation_count"],
        "minimum_observations": payload["minimum_observations"],
        "epoch": payload["epoch"],
        "binding": payload["binding"],
        "distinct_session_count": payload["distinct_session_count"],
        "minimum_distinct_sessions": payload["minimum_distinct_sessions"],
        "eligible_filled_order_count": payload["eligible_filled_order_count"],
        "quality_checks": payload["quality_checks"],
        "quality_thresholds": payload["quality_thresholds"],
        "local_hash_authenticity_caveat": payload["local_hash_authenticity_caveat"],
    }
    if payload["matched_paper_tca_pass"]:
        return PaperStrategyReadinessCheck(
            name="matched_paper_tca",
            status="ok",
            message="Strategy-specific matched Alpaca Paper TCA threshold passed.",
            details=details,
        )
    return PaperStrategyReadinessCheck(
        name="matched_paper_tca",
        status="warning",
        message=(
            "Matched paper TCA is incomplete: "
            f"{payload['valid_observation_count']}/{payload['minimum_observations']} fills."
        ),
        details=details,
        suggested_actions=[f"uv run oc paper tca-report --strategy {spec.name}"],
    )


def _data_source_check(spec: StrategySpec) -> PaperStrategyReadinessCheck:
    tier = spec.data_assumptions.acquisition_tier
    if tier in {"sample_smoke", "fixture_replay", "research_cross_check"}:
        return PaperStrategyReadinessCheck(
            name="data_source",
            status="blocked",
            message=f"acquisition_tier={tier} is not paper-ready market evidence.",
            details={
                "source": spec.data.source,
                "symbol": spec.primary_symbol,
                "timeframe": spec.timeframe,
                "acquisition_tier": tier,
            },
            suggested_actions=[
                "Use paper_ready_live or cross_source_verified evidence before paper."
            ],
        )
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


def _canary_authorization_check(
    spec: StrategySpec,
    root: Path,
) -> PaperStrategyReadinessCheck:
    full = assess_paper_order_authorization(spec, root)
    if full.authorized:
        return PaperStrategyReadinessCheck(
            name="canary_authorization",
            status="ok",
            message="Full paper authorization supersedes the bounded canary phase.",
            details={"authorized": False, "superseded_by_full": True},
        )
    status = assess_paper_canary_authorization(spec, root)
    details = {
        "authorized": status.authorized,
        "path": _relpath(status.path, root),
        **status.details,
    }
    if status.authorized:
        return PaperStrategyReadinessCheck(
            name="canary_authorization",
            status="ok",
            message=status.message,
            details=details,
        )
    return PaperStrategyReadinessCheck(
        name="canary_authorization",
        status="ok",
        message="No valid bounded paper canary authorization is active.",
        details=details,
        suggested_actions=[
            (
                f"uv run oc paper authorize-canary {spec.name} --confirm-paper-only "
                "--confirm-canary-risk --authorized-by <operator>"
            )
        ],
    )


def _order_authorization_check(
    spec: StrategySpec,
    root: Path,
) -> PaperStrategyReadinessCheck:
    status = assess_paper_order_authorization(spec, root)
    details = {"path": _relpath(status.path, root), **status.details}
    if status.authorized:
        return PaperStrategyReadinessCheck(
            name="order_authorization",
            status="ok",
            message=status.message,
            details=details,
        )
    return PaperStrategyReadinessCheck(
        name="order_authorization",
        status="warning",
        message=status.message + " Strategy remains observation_only.",
        details=details,
        suggested_actions=[
            (
                f"uv run oc paper authorize-canary {spec.name} --confirm-paper-only "
                "--confirm-canary-risk --authorized-by <operator>"
            ),
        ],
    )


def _universe_audit_check(spec: StrategySpec, root: Path) -> PaperStrategyReadinessCheck:
    from open_composer.research.universe_audit import assess_universe_audit

    result = assess_universe_audit(spec, root)
    findings = [
        {
            "code": item.code,
            "severity": item.severity,
            "message": item.message,
            "evidence": item.evidence,
        }
        for item in result.findings
    ]
    details = {
        "status": result.status,
        "json_path": _relpath(result.json_path, root),
        "report_path": _relpath(result.report_path, root),
        "findings": findings,
    }
    if result.status == "blocked":
        return PaperStrategyReadinessCheck(
            name="universe_audit",
            status="blocked",
            message=(
                "Paper automation requires point-in-time universe membership or explicit "
                "fixed-universe evidence."
            ),
            details=details,
            suggested_actions=[
                "Add notes.universe_audit point_in_time_membership evidence, or reduce the "
                "strategy to an explicitly fixed instrument universe before paper_auto."
            ],
        )
    if result.status == "warning":
        return PaperStrategyReadinessCheck(
            name="universe_audit",
            status="warning",
            message="Universe audit warnings should be reviewed before paper automation.",
            details=details,
        )
    return PaperStrategyReadinessCheck(
        name="universe_audit",
        status="ok",
        message="Universe audit passed.",
        details=details,
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
    from open_composer.paper_controls import load_paper_kill_switch

    path = root / "reports" / "paper" / "kill_switch.json"
    try:
        kill_switch = load_paper_kill_switch(root, require_control_file=True)
    except FileNotFoundError:
        return PaperStrategyReadinessCheck(
            name="kill_switch",
            status="blocked",
            message="Paper kill-switch control file is missing; submissions fail closed.",
            details={"path": _relpath(path, root), "control_file_present": False},
            suggested_actions=[
                'uv run oc paper kill-switch --disable --reason "initialize paper control"'
            ],
        )
    except (OSError, ValueError) as exc:
        return PaperStrategyReadinessCheck(
            name="kill_switch",
            status="blocked",
            message="Paper kill-switch control file is invalid; submissions fail closed.",
            details={"path": _relpath(path, root), "error": str(exc)},
            suggested_actions=[
                'uv run oc paper kill-switch --disable --reason "repair paper control"'
            ],
        )
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
    path = root / "reports" / "paper" / "account.json"
    account = _load_account_snapshot(root)
    if account is None:
        return PaperStrategyReadinessCheck(
            name="account_snapshot",
            status="warning",
            message="No paper account snapshot found; run oc paper sync-account before automation.",
            details={"path": "reports/paper/account.json"},
            suggested_actions=["uv run oc paper sync-account"],
        )
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        raw = {}
    age_seconds = (datetime.now(UTC) - account.generated_at.astimezone(UTC)).total_seconds()
    account_status = str(account.status).rsplit(".", 1)[-1].upper()
    values = [account.equity, account.cash, account.buying_power, account.portfolio_value]
    invalid = (
        not isinstance(raw, dict)
        or not raw.get("generated_at")
        or account.paper is not True
        or account_status != "ACTIVE"
        or account.equity is None
        or account.equity <= 0
        or account.cash is None
        or account.buying_power is None
        or account.portfolio_value is None
        or any(value is not None and not math.isfinite(value) for value in values)
        or age_seconds < 0
        or age_seconds > PAPER_SNAPSHOT_STALE_SECONDS
    )
    if invalid:
        return PaperStrategyReadinessCheck(
            name="account_snapshot",
            status="blocked",
            message="Paper account snapshot is stale or invalid.",
            details={
                "path": _relpath(path, root),
                "generated_at": account.generated_at.isoformat(),
                "age_seconds": age_seconds,
                "paper": account.paper,
                "account_status": account.status,
            },
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
            "age_seconds": age_seconds,
        },
    )


def _positions_snapshot_check(root: Path) -> PaperStrategyReadinessCheck:
    path = root / "reports" / "paper" / "positions.json"
    if not path.is_file():
        return PaperStrategyReadinessCheck(
            name="positions_snapshot",
            status="warning",
            message="No paper positions snapshot found; run oc paper sync-account.",
            details={"path": _relpath(path, root)},
            suggested_actions=["uv run oc paper sync-account"],
        )
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        generated_at = datetime.fromisoformat(
            str(raw.get("generated_at", "")).replace("Z", "+00:00")
        )
        positions = raw.get("positions")
    except (AttributeError, json.JSONDecodeError, ValueError):
        raw = {}
        generated_at = None
        positions = None
    if generated_at is not None:
        if generated_at.tzinfo is None:
            generated_at = generated_at.replace(tzinfo=UTC)
        generated_at = generated_at.astimezone(UTC)
    age_seconds = (
        (datetime.now(UTC) - generated_at).total_seconds() if generated_at is not None else None
    )
    invalid_rows = []
    if isinstance(positions, list):
        for index, row in enumerate(positions):
            if not isinstance(row, dict) or row.get("paper") is not True:
                invalid_rows.append(index)
                continue
            try:
                quantity = float(row.get("qty"))
            except (TypeError, ValueError):
                invalid_rows.append(index)
                continue
            if not math.isfinite(quantity):
                invalid_rows.append(index)
    invalid = (
        generated_at is None
        or not isinstance(positions, list)
        or raw.get("paper") is not True
        or age_seconds is None
        or age_seconds < 0
        or age_seconds > PAPER_SNAPSHOT_STALE_SECONDS
        or bool(invalid_rows)
    )
    if invalid:
        return PaperStrategyReadinessCheck(
            name="positions_snapshot",
            status="blocked",
            message="Paper positions snapshot is stale or invalid.",
            details={
                "path": _relpath(path, root),
                "generated_at": generated_at.isoformat() if generated_at else None,
                "age_seconds": age_seconds,
                "invalid_rows": invalid_rows,
            },
            suggested_actions=["uv run oc paper sync-account"],
        )
    return PaperStrategyReadinessCheck(
        name="positions_snapshot",
        status="ok",
        message="Paper positions snapshot is current.",
        details={
            "path": _relpath(path, root),
            "generated_at": generated_at.isoformat(),
            "age_seconds": age_seconds,
            "position_count": len(positions),
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
    if spec.portfolio.mode in {
        "adaptive_intraday_internal_router",
        "hybrid_adaptive_router",
        "beta_exposure_router",
        "core_beta_satellite_router",
        "cross_sectional_momentum",
    }:
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
    if portfolio.mode in {
        "adaptive_intraday_internal_router",
        "hybrid_adaptive_router",
        "beta_exposure_router",
        "core_beta_satellite_router",
        "cross_sectional_momentum",
    }:
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
        path = feature_packet_path_for_factor(root, spec.name, name, factor)
        path_label = feature_packet_path_label(spec.name, name, factor)
        if path is None or path_label is None:
            missing.append(f"{name}: missing packet path")
            continue
        inspection = inspect_feature_packet(path, factor.field)
        inspected.append(
            {
                "factor": name,
                "path": path_label,
                "field": factor.field,
                "status": inspection.point_in_time_status,
                "warnings": inspection.replay_warnings,
                "evidence_count": inspection.evidence_count,
                "missing_evidence_count": inspection.missing_evidence_count,
            }
        )
        if not inspection.exists:
            missing.append(f"{name}: packet not found at {path_label}")
        elif inspection.point_in_time_status != "complete":
            warning_text = "; ".join(inspection.replay_warnings[:3]) or "not PIT complete"
            incomplete.append(
                f"{name}: {inspection.point_in_time_status} at {path_label}: {warning_text}"
            )
        elif inspection.missing_evidence_count:
            missing_evidence.append(
                f"{name}: {inspection.missing_evidence_count} packet row(s) at "
                f"{path_label} lack marginal-lift evidence"
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
    missing_requirements.extend(
        _promotion_binding_missing_requirements(
            spec=spec,
            root=root,
            raw=raw,
            research_manifest=research_manifest,
        )
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


def _promotion_binding_missing_requirements(
    *,
    spec: StrategySpec,
    root: Path,
    raw: dict[str, object],
    research_manifest: dict[str, object],
) -> list[str]:
    missing: list[str] = []
    expected_spec_hash = strategy_content_hash(spec)
    if raw.get("strategy_name") != spec.name:
        missing.append("promotion strategy_name does not match current StrategySpec")
    if _normalize_hash(research_manifest.get("spec_hash")) != expected_spec_hash:
        missing.append("promotion spec_hash does not match current StrategySpec")

    contract_ref = research_manifest.get("research_contract_path")
    contract_hash = _normalize_hash(research_manifest.get("research_contract_hash"))
    if not isinstance(contract_ref, str) or not contract_ref:
        missing.append("research contract path is missing")
    else:
        contract_path = _resolve_path(root, contract_ref)
        if not contract_path.is_file():
            missing.append("research contract file is missing")
        elif not contract_hash or contract_hash != _sha256_file(contract_path):
            missing.append("research contract hash is missing or stale")

    data_path_value = next(
        (
            research_manifest.get(name)
            for name in (
                "data_snapshot_manifest_path",
                "data_snapshot_binding_path",
                "data_manifest_path",
            )
            if isinstance(research_manifest.get(name), str) and research_manifest.get(name)
        ),
        None,
    )
    data_hash = next(
        (
            _normalize_hash(research_manifest.get(name))
            for name in (
                "data_snapshot_manifest_hash",
                "data_snapshot_binding_hash",
                "data_manifest_hash",
                "data_path_hash",
            )
            if _normalize_hash(research_manifest.get(name))
        ),
        "",
    )
    if not isinstance(data_path_value, str):
        missing.append("immutable data manifest path is missing")
    else:
        data_path = _resolve_path(root, data_path_value)
        if not data_path.is_file():
            missing.append("immutable data manifest file is missing")
        elif not data_hash or data_hash != _sha256_file(data_path):
            missing.append("immutable data manifest hash is missing or stale")
    return missing


def _harness_artifacts_check(spec: StrategySpec, root: Path) -> PaperStrategyReadinessCheck:
    """Block paper readiness when required harness artifacts are missing or incomplete.

    Reads harness/risk_domains.yaml to detect active domains and checks each required
    artifact via artifact_contracts.yaml. Strategies with no active risk domains pass.
    """
    from open_composer.harness.policy import (
        blocking_rules_for_domains,
        check_artifact,
        detect_risk_domains,
        required_artifacts_for_domains,
    )

    active = detect_risk_domains(spec, root)
    required = sorted(required_artifacts_for_domains(active))
    if not required:
        return PaperStrategyReadinessCheck(
            name="harness_artifacts",
            status="ok",
            message="No risk domains active for this spec; no harness artifacts required.",
            details={"risk_domains": active},
        )

    statuses = [check_artifact(name, spec.name, root) for name in required]
    missing = [s.name for s in statuses if not s.present]
    incomplete = [
        {"name": s.name, "missing_fields": s.missing_fields}
        for s in statuses
        if s.present and not s.schema_ok
    ]
    rules = [
        {"domain": r.domain_id, "rule_id": r.rule_id, "blocks": r.blocks}
        for r in blocking_rules_for_domains(active)
        if r.blocks == "paper_ready_pass"
    ]

    if missing or incomplete:
        # Paper automation cannot be considered ready while required safety-chain
        # artifacts are absent. Older non-paper flows can still surface the
        # migration warning unless OC_HARNESS_STRICT is enabled.
        import os

        strict = os.environ.get("OC_HARNESS_STRICT", "0") == "1"
        paper_auto = spec.execution.mode == "paper_auto"
        strict = strict or paper_auto
        check_status: PaperReadinessStatus = "blocked" if strict else "warning"
        prefix = "blocked" if strict else "legacy_harness_review_required"
        return PaperStrategyReadinessCheck(
            name="harness_artifacts",
            status=check_status,
            message=(
                f"Paper readiness {prefix} for harness artifacts: "
                f"missing={missing or '-'}, "
                f"incomplete={[c['name'] for c in incomplete] or '-'}"
            ),
            details={
                "risk_domains": active,
                "required_artifacts": required,
                "missing": missing,
                "incomplete": incomplete,
                "paper_ready_blocking_rules": rules,
                "strict_mode": strict,
            },
            suggested_actions=[
                f"uv run oc harness verify strategy_specs/active/{spec.name}.yaml",
                f"uv run oc harness plan strategy_specs/active/{spec.name}.yaml",
            ],
        )
    return PaperStrategyReadinessCheck(
        name="harness_artifacts",
        status="ok",
        message=f"All {len(required)} harness artifacts present for domains {active}.",
        details={"risk_domains": active, "required_artifacts": required},
    )


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
    execution_substate: str,
) -> dict[str, object]:
    blocked = [check.name for check in checks if check.status == "blocked"]
    warning = [check.name for check in checks if check.status == "warning"]
    return {
        "workflow_pass": "lifecycle" not in blocked and "execution" not in blocked,
        "research_pass": any(
            check.name == "promotion_report" and check.status == "ok" for check in checks
        ),
        "llm_contribution_pass": None,
        "paper_canary_pass": execution_substate == "canary_authorized",
        "paper_ready_pass": status == "ok" and execution_substate == "order_authorized",
        "execution_substate": execution_substate,
        "blocked_checks": blocked,
        "warning_checks": warning,
        "paper_change_cadence": {
            "status": "manual_review_required",
            "policy": (
                "paper-stage spec changes require a linked decision record and at least "
                "10 trading days since the prior paper-stage change unless the change is "
                "a documented risk-reduction kill-rule exception"
            ),
            "automation_limit": (
                "current StrategyVersion metadata does not yet prove iteration_id, "
                "decision_record_path, change_reason, or risk_reduction_only"
            ),
        },
    }


def _render_markdown(report: PaperStrategyReadinessReport) -> str:
    lines = [
        f"# Paper Strategy Readiness: {report.strategy_name}",
        "",
        f"- Generated at: `{report.generated_at.isoformat()}`",
        f"- Strategy path: `{report.strategy_path or 'candidate'}`",
        f"- Status: `{report.status}`",
        f"- Ready: `{'yes' if report.ready else 'no'}`",
        f"- Execution substate: `{report.execution_substate}`",
        "- Gate taxonomy: workflow_pass, research_pass, llm_contribution_pass, paper_ready_pass.",
        f"- Gate summary: `{report.gate_summary}`",
        (
            "- Paper change cadence: paper-stage spec changes require a linked decision "
            "record and >=10 trading days unless a documented de-risk exception applies."
        ),
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


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _normalize_hash(value: object) -> str:
    return str(value or "").removeprefix("sha256:").strip()


def _relpath(path: Path | None, base: Path) -> str | None:
    if path is None:
        return None
    try:
        return path.relative_to(base).as_posix()
    except ValueError:
        return path.as_posix()
