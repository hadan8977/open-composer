from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from open_composer.adapters.broker.alpaca_paper import (
    PaperOrderError,
    sync_paper_account,
    sync_paper_orders,
)
from open_composer.config import ensure_dir, project_root
from open_composer.engines.backtest_engine import run_backtest
from open_composer.engines.scanner_engine import run_scan
from open_composer.models.dashboard_command import (
    DashboardCommandAction,
    DashboardCommandEvent,
    DashboardCommandPlan,
    DashboardCommandResult,
    DashboardCommandStrategyBinding,
)
from open_composer.models.strategy_spec import load_strategy_spec
from open_composer.paper_controls import (
    clear_paper_kill_switch,
    enable_paper_kill_switch,
    refresh_paper_monitor,
    write_paper_status,
)
from open_composer.paper_readiness import (
    assess_paper_strategy_readiness,
    write_paper_readiness_report,
)
from open_composer.research import draft_strategy_from_idea
from open_composer.storage import append_jsonl, write_json
from open_composer.strategy_capabilities import (
    StrategyCapabilityReport,
    assess_strategy_capabilities,
)
from open_composer.strategy_lifecycle import (
    activate_strategy,
    approve_strategy,
    disable_strategy,
    list_strategies,
    resolve_strategy_path,
)
from open_composer.strategy_versions import strategy_content_hash


class DashboardCommandError(ValueError):
    pass


def build_dashboard_command_plan(
    action: DashboardCommandAction,
    root: Path | None = None,
    *,
    reason: str = "",
    requested_by: str = "dashboard",
    strategy_path: str | Path | None = None,
    data_source: str = "keep",
    idea: str = "",
    use_llm: bool = False,
) -> DashboardCommandPlan:
    base = root or project_root()
    clean_reason = reason.strip()
    clean_data_source = _normalize_data_source(data_source, action)
    clean_idea = idea.strip()
    warnings: list[str] = []
    preconditions = [
        "Dashboard commands are local-only and audit logged.",
        "Real-money broker writes are not available through this service.",
        "Execution requires the exact confirmation phrase.",
    ]

    if action in {"paper.kill_switch.enable", "paper.kill_switch.clear"} and not clean_reason:
        warnings.append("A reason should be provided for kill-switch changes.")

    if action == "strategy.draft":
        if not clean_idea:
            raise DashboardCommandError("idea is required for strategy.draft")
        bindings = []
        preconditions = [
            "Dashboard commands are local-only and audit logged.",
            "Strategy drafts are created under strategy_specs/drafts.",
            "Execution requires the exact confirmation phrase.",
        ]
        if use_llm:
            warnings.append(
                "LLM drafting falls back to deterministic drafting when API config is absent."
            )
    elif _requires_strategy_binding(action):
        binding = _strategy_binding(base, strategy_path)
        bindings = [binding]
        warnings.extend(_strategy_transition_warnings(action, binding, clean_data_source))
    elif _is_system_action(action):
        bindings = []
        preconditions = [
            "Dashboard commands are local-only and audit logged.",
            "System maintenance rewrites local deployment artifacts only.",
            "Execution requires the exact confirmation phrase.",
        ]
    else:
        bindings = _paper_strategy_bindings(base)
        if not bindings:
            warnings.append(
                "No active paper_auto Alpaca Paper strategies are currently checked in."
            )

    command_id = _command_id(action)
    plan = DashboardCommandPlan(
        command_id=command_id,
        action=action,
        requested_by=requested_by,
        requested_at=datetime.now(UTC),
        reason=clean_reason,
        paper_only=_is_paper_action(action),
        confirmation_phrase=_confirmation_phrase(action),
        data_source=clean_data_source,
        idea=clean_idea,
        use_llm=use_llm,
        cli_args=_cli_args(action, clean_reason, bindings, clean_data_source, clean_idea, use_llm),
        target_strategy_bindings=bindings,
        preconditions=preconditions,
        warnings=warnings,
    )
    return plan


def write_dashboard_command_plan(
    plan: DashboardCommandPlan,
    root: Path | None = None,
    output_path: Path | None = None,
) -> Path:
    base = root or project_root()
    path = output_path or _plan_path(base, plan.command_id)
    ensure_dir(path.parent)
    plan.plan_path = _relpath(path, base)
    write_json(path, plan)
    _append_command_event(
        base,
        DashboardCommandEvent(
            command_id=plan.command_id,
            action=plan.action,
            status=plan.status,
            actor=plan.requested_by,
            reason=plan.reason,
            plan_path=plan.plan_path,
            message="Dashboard command plan created.",
        ),
    )
    return path


def load_dashboard_command_plan(path: Path) -> DashboardCommandPlan:
    return DashboardCommandPlan.model_validate_json(path.read_text(encoding="utf-8"))


def resolve_dashboard_serve_root(root: Path | None = None) -> Path | None:
    base = root or project_root()
    dist_root = base / "dashboard" / "dist"
    html_root = base / "reports" / "dashboard"
    candidate = dist_root if (dist_root / "index.html").exists() else html_root
    return candidate if (candidate / "index.html").exists() else None


def execute_dashboard_command_plan(
    plan: DashboardCommandPlan,
    root: Path | None = None,
    *,
    confirmation: str,
    executed_by: str = "dashboard",
) -> DashboardCommandResult:
    base = root or project_root()
    if confirmation != plan.confirmation_phrase:
        result = DashboardCommandResult(
            command_id=plan.command_id,
            action=plan.action,
            status="blocked",
            executed_by=executed_by,
            message="Confirmation phrase did not match; command was not executed.",
        )
        _write_result_and_event(base, plan, result)
        raise DashboardCommandError(result.message)

    output_paths: list[str] = []
    if plan.action == "paper.status.refresh":
        output_paths.append(_relpath(write_paper_status(base), base))
        message = "Paper status refreshed."
    elif plan.action == "paper.monitor.refresh":
        report = refresh_paper_monitor(base)
        output_paths.extend(
            path
            for path in [
                report.status_path,
                report.reconciliation_report_path,
                report.alert_report_path,
                report.report_json_path,
                report.report_markdown_path,
            ]
            if path
        )
        message = "Paper monitor refreshed."
    elif plan.action == "system.prepare_workspace":
        from open_composer.deployment import prepare_workspace

        report = prepare_workspace(base)
        output_paths.extend(report.output_paths)
        message = "Workspace preparation completed."
    elif plan.action == "system.readiness.refresh":
        from open_composer.readiness import build_readiness_report, write_readiness_report

        readiness_report = build_readiness_report(base)
        json_path, md_path = write_readiness_report(readiness_report, base)
        output_paths.extend([_relpath(json_path, base), _relpath(md_path, base)])
        message = "Deployment readiness refreshed."
    elif plan.action == "paper.sync.orders":
        try:
            path = sync_paper_orders(base)
        except PaperOrderError as exc:
            raise DashboardCommandError(str(exc)) from exc
        output_paths.append(_relpath(path, base))
        message = "Paper orders synced."
    elif plan.action == "paper.sync.account":
        try:
            account_path, positions_path = sync_paper_account(base)
        except PaperOrderError as exc:
            raise DashboardCommandError(str(exc)) from exc
        output_paths.extend(_relpath(path, base) for path in [account_path, positions_path])
        message = "Paper account and positions synced."
    elif plan.action == "paper.kill_switch.enable":
        enable_paper_kill_switch(base, reason=plan.reason, updated_by=executed_by)
        output_paths.append(_relpath(write_paper_status(base), base))
        message = "Paper kill switch enabled."
    elif plan.action == "paper.kill_switch.clear":
        clear_paper_kill_switch(base, reason=plan.reason, updated_by=executed_by)
        output_paths.append(_relpath(write_paper_status(base), base))
        message = "Paper kill switch cleared."
    elif _is_strategy_action(plan.action):
        try:
            output_paths, message = _execute_strategy_command(plan, base)
        except (FileNotFoundError, ValueError) as exc:
            output_paths = _strategy_blocked_output_paths(plan, base)
            result = DashboardCommandResult(
                command_id=plan.command_id,
                action=plan.action,
                status="blocked",
                executed_by=executed_by,
                message=str(exc),
                output_paths=output_paths,
            )
            _write_result_and_event(base, plan, result)
            raise DashboardCommandError(result.message) from exc
    else:  # pragma: no cover - the Literal type keeps this unreachable.
        raise DashboardCommandError(f"Unsupported dashboard command action: {plan.action}")

    result = DashboardCommandResult(
        command_id=plan.command_id,
        action=plan.action,
        status="executed",
        executed_by=executed_by,
        message=message,
        output_paths=output_paths,
    )
    _write_result_and_event(base, plan, result)
    return result


def _paper_strategy_bindings(base: Path) -> list[DashboardCommandStrategyBinding]:
    bindings: list[DashboardCommandStrategyBinding] = []
    for item in list_strategies(base):
        if not (
            item.lifecycle == "active"
            and item.execution_mode == "paper_auto"
            and item.broker == "alpaca_paper"
        ):
            continue
        spec_path = item.path
        spec = load_strategy_spec(spec_path)
        bindings.append(
            DashboardCommandStrategyBinding(
                strategy_name=item.name,
                lifecycle=item.lifecycle,
                execution_mode=item.execution_mode,
                broker=item.broker,
                source_path=_relpath(spec_path, base),
                spec_hash=strategy_content_hash(spec),
            )
        )
    return bindings


def _strategy_binding(
    base: Path,
    strategy_path: str | Path | None,
) -> DashboardCommandStrategyBinding:
    if not strategy_path:
        raise DashboardCommandError("strategy_path is required for strategy lifecycle commands")
    raw_path = Path(strategy_path)
    candidate = raw_path if raw_path.is_absolute() else base / raw_path
    path = candidate if candidate.exists() else resolve_strategy_path(strategy_path, base)
    path = path.resolve()
    resolved_base = base.resolve()
    if path != resolved_base and not path.is_relative_to(resolved_base):
        raise DashboardCommandError("strategy_path must stay within the current workspace")
    spec = load_strategy_spec(path)
    return DashboardCommandStrategyBinding(
        strategy_name=spec.name,
        lifecycle=spec.lifecycle,
        execution_mode=spec.execution.mode,
        broker=spec.execution.broker,
        source_path=_relpath(path, base),
        spec_hash=strategy_content_hash(spec),
    )


def _target_binding(plan: DashboardCommandPlan) -> DashboardCommandStrategyBinding:
    if not plan.target_strategy_bindings:
        raise DashboardCommandError("strategy lifecycle command has no target strategy binding")
    return plan.target_strategy_bindings[0]


def _execute_strategy_command(
    plan: DashboardCommandPlan,
    base: Path,
) -> tuple[list[str], str]:
    if plan.action == "strategy.draft":
        if not plan.idea.strip():
            raise DashboardCommandError("idea is required for strategy.draft")
        path = draft_strategy_from_idea(plan.idea, base, use_llm=plan.use_llm)
        return [_relpath(path, base)], "Strategy draft created."
    binding = _target_binding(plan)
    target_path = base / binding.source_path
    if plan.action == "strategy.workflow.verify":
        paths = _run_strategy_workflow_verification(target_path, base)
        return [_relpath(path, base) for path in paths], "Strategy workflow verification completed."
    if plan.action == "strategy.validate":
        path = _write_strategy_validation_report(target_path, base)
        return [
            _relpath(path, base),
            _relpath(path.with_suffix(".md"), base),
        ], "Strategy validated."
    if plan.action == "strategy.capabilities.refresh":
        paths = _write_strategy_capability_report(target_path, base)
        return [_relpath(path, base) for path in paths], "Strategy capability report refreshed."
    if plan.action == "strategy.approve":
        path = approve_strategy(target_path, base)
        return [_relpath(path, base)], "Strategy approved."
    if plan.action == "strategy.activate.manual":
        path = activate_strategy(target_path, base, data_source=plan.data_source)
        return [_relpath(path, base)], "Strategy activated in manual signal mode."
    if plan.action == "strategy.activate.paper_auto":
        path = activate_strategy(
            target_path,
            base,
            paper_auto=True,
            allow_paper_auto=True,
            data_source=plan.data_source,
            enforce_paper_readiness=True,
        )
        return [_relpath(path, base)], "Strategy activated for Alpaca Paper automation."
    if plan.action == "strategy.backtest.rerun":
        artifacts = run_backtest(target_path, base)
        outputs = [
            artifacts.run.report_path,
            artifacts.run.signal_log_path,
            artifacts.backend_plan_path,
        ]
        return (
            [_relpath(Path(path), base) for path in outputs if path],
            "Strategy backtest rerun completed.",
        )
    if plan.action == "strategy.scan.rerun":
        signals = run_scan(target_path, base, refresh_data=False)
        outputs = [
            _latest_matching_file(base / "signal_logs", f"scan-{binding.strategy_name}-*.jsonl"),
            _latest_matching_file(base / "reports" / "scans", f"scan-{binding.strategy_name}-*.md"),
        ]
        return (
            [_relpath(path, base) for path in outputs if path.exists()],
            f"Strategy scan rerun completed with {len(signals)} signal(s).",
        )
    if plan.action == "strategy.disable":
        path = disable_strategy(binding.strategy_name, base)
        return [_relpath(path, base)], "Strategy disabled."
    raise DashboardCommandError(f"Unsupported strategy lifecycle action: {plan.action}")


def _write_strategy_validation_report(spec_path: Path, base: Path) -> Path:
    spec = load_strategy_spec(spec_path)
    path = base / "reports" / "specs" / f"{spec.name}.validation.json"
    payload = {
        "strategy_name": spec.name,
        "source_path": _relpath(spec_path, base),
        "spec_hash": strategy_content_hash(spec),
        "status": "ok",
        "message": "StrategySpec is valid.",
    }
    write_json(path, payload)
    md_path = path.with_suffix(".md")
    ensure_dir(md_path.parent)
    md_path.write_text(
        "\n".join(
            [
                f"# StrategySpec Validation: {spec.name}",
                "",
                "- Status: `ok`",
                f"- Source path: `{payload['source_path']}`",
                f"- Spec hash: `{payload['spec_hash']}`",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return path


def _write_strategy_capability_report(spec_path: Path, base: Path) -> list[Path]:
    report = assess_strategy_capabilities(spec_path)
    path = base / "reports" / "capabilities" / f"{report.strategy_name}.json"
    payload = _strategy_capability_payload(report)
    write_json(path, payload)
    md_path = path.with_suffix(".md")
    ensure_dir(md_path.parent)
    md_path.write_text(_render_strategy_capability_markdown(report), encoding="utf-8")
    return [path, md_path]


def _run_strategy_workflow_verification(spec_path: Path, base: Path) -> list[Path]:
    spec = load_strategy_spec(spec_path)
    output_paths: list[Path] = []

    validation_path = _write_strategy_validation_report(spec_path, base)
    output_paths.extend([validation_path, validation_path.with_suffix(".md")])

    output_paths.extend(_write_strategy_capability_report(spec_path, base))

    backtest_artifacts = run_backtest(spec_path, base)
    output_paths.extend(
        Path(path)
        for path in [
            backtest_artifacts.run.report_path,
            backtest_artifacts.run.signal_log_path,
            backtest_artifacts.backend_plan_path,
        ]
        if path
    )

    signals = run_scan(spec_path, base, refresh_data=False)
    scan_outputs = [
        _latest_matching_file(base / "signal_logs", f"scan-{spec.name}-*.jsonl"),
        _latest_matching_file(base / "reports" / "scans", f"scan-{spec.name}-*.md"),
    ]
    output_paths.extend(path for path in scan_outputs if path.exists())

    readiness = assess_paper_strategy_readiness(spec_path, base)
    readiness_json_path, readiness_md_path = write_paper_readiness_report(readiness, base)
    output_paths.extend([readiness_json_path, readiness_md_path])

    workflow_path = base / "reports" / "workflows" / f"{spec.name}.verify.json"
    workflow_md_path = workflow_path.with_suffix(".md")
    payload = {
        "strategy_name": spec.name,
        "source_path": _relpath(spec_path, base),
        "spec_hash": strategy_content_hash(spec),
        "status": "ok" if readiness.ready else "warning",
        "backtest_run_id": backtest_artifacts.run.run_id,
        "scan_signal_count": len(signals),
        "paper_readiness_status": readiness.status,
        "paper_ready": readiness.ready,
        "output_paths": [_relpath(path, base) for path in output_paths],
    }
    write_json(workflow_path, payload)
    ensure_dir(workflow_md_path.parent)
    workflow_md_path.write_text(_render_strategy_workflow_markdown(payload), encoding="utf-8")
    output_paths.extend([workflow_path, workflow_md_path])
    return list(dict.fromkeys(output_paths))


def _strategy_capability_payload(report: StrategyCapabilityReport) -> dict[str, object]:
    return {
        "strategy_name": report.strategy_name,
        "lifecycle": report.lifecycle,
        "expression_functions": report.expression_functions,
        "expression_names": report.expression_names,
        "backend_plan": report.backend_plan.model_dump(mode="json"),
        "findings": [
            {
                "capability": finding.capability,
                "status": finding.status,
                "reasons": finding.reasons,
            }
            for finding in report.findings
        ],
    }


def _render_strategy_capability_markdown(report: StrategyCapabilityReport) -> str:
    lines = [
        f"# Strategy Capabilities: {report.strategy_name}",
        "",
        f"- Lifecycle: `{report.lifecycle}`",
        f"- Backend selected: `{report.backend_plan.selected_backend}`",
        f"- Backend status: `{report.backend_plan.status}`",
        "",
        "| Capability | Status | Reasons |",
        "|---|---|---|",
    ]
    for finding in report.findings:
        reasons = "<br>".join(finding.reasons) if finding.reasons else "none"
        lines.append(f"| {finding.capability} | {finding.status} | {reasons} |")
    lines.append("")
    return "\n".join(lines)


def _render_strategy_workflow_markdown(payload: dict[str, object]) -> str:
    lines = [
        f"# Strategy Workflow Verification: {payload['strategy_name']}",
        "",
        f"- Source path: `{payload['source_path']}`",
        f"- Status: `{payload['status']}`",
        f"- Backtest run: `{payload['backtest_run_id']}`",
        f"- Scan signals: `{payload['scan_signal_count']}`",
        f"- Paper readiness: `{payload['paper_readiness_status']}`",
        f"- Paper ready: `{'yes' if payload['paper_ready'] else 'no'}`",
        "",
        "## Outputs",
        "",
    ]
    output_paths = payload.get("output_paths", [])
    if isinstance(output_paths, list):
        lines.extend(f"- `{path}`" for path in output_paths)
    return "\n".join(lines) + "\n"


def _strategy_blocked_output_paths(plan: DashboardCommandPlan, base: Path) -> list[str]:
    if plan.action != "strategy.activate.paper_auto" or not plan.target_strategy_bindings:
        return []
    strategy_name = plan.target_strategy_bindings[0].strategy_name
    json_path = (
        base / "reports" / "paper" / "readiness" / f"{strategy_name}.activation_candidate.json"
    )
    paths = [json_path, json_path.with_suffix(".md")]
    return [_relpath(path, base) for path in paths if path.exists()]


def _latest_matching_file(root: Path, pattern: str) -> Path:
    candidates = [path for path in root.glob(pattern) if path.is_file()]
    if not candidates:
        return root / pattern
    return max(candidates, key=lambda path: path.stat().st_mtime)


def _strategy_transition_warnings(
    action: DashboardCommandAction,
    binding: DashboardCommandStrategyBinding,
    data_source: str,
) -> list[str]:
    warnings: list[str] = []
    if action == "strategy.approve" and binding.lifecycle != "draft":
        warnings.append(f"Approving a non-draft strategy currently in {binding.lifecycle}.")
    if action.startswith("strategy.activate") and binding.lifecycle == "retired":
        warnings.append("Activating a retired strategy will create a new active copy.")
    if action == "strategy.activate.paper_auto":
        warnings.append(
            "Paper automation activation enforces paper readiness before writing active spec."
        )
        if data_source == "sample":
            warnings.append("data_source=sample will block paper readiness.")
    if action == "strategy.disable" and binding.lifecycle != "active":
        warnings.append(f"Disabling a non-active strategy currently in {binding.lifecycle}.")
    return warnings


def _normalize_data_source(action_data_source: str, action: DashboardCommandAction) -> str:
    data_source = str(action_data_source or "keep").strip() or "keep"
    allowed = {"keep", "sample", "alpaca", "longbridge"}
    if data_source not in allowed:
        raise DashboardCommandError(f"data_source must be one of: {', '.join(sorted(allowed))}")
    if not _requires_strategy_binding(action):
        return "keep"
    return data_source


def _is_strategy_action(action: DashboardCommandAction) -> bool:
    return action.startswith("strategy.")


def _requires_strategy_binding(action: DashboardCommandAction) -> bool:
    return _is_strategy_action(action) and action != "strategy.draft"


def _is_system_action(action: DashboardCommandAction) -> bool:
    return action.startswith("system.")


def _is_paper_action(action: DashboardCommandAction) -> bool:
    return action.startswith("paper.")


def _confirmation_phrase(action: DashboardCommandAction) -> str:
    if _is_system_action(action):
        return "CONFIRM SYSTEM COMMAND"
    if _is_strategy_action(action):
        return "CONFIRM STRATEGY COMMAND"
    return "CONFIRM PAPER COMMAND"


def _cli_args(
    action: DashboardCommandAction,
    reason: str,
    bindings: list[DashboardCommandStrategyBinding],
    data_source: str,
    idea: str,
    use_llm: bool,
) -> list[str]:
    if action == "paper.status.refresh":
        return ["uv", "run", "oc", "paper", "status"]
    if action == "paper.monitor.refresh":
        return ["uv", "run", "oc", "paper", "monitor"]
    if action == "paper.sync.orders":
        return ["uv", "run", "oc", "paper", "sync"]
    if action == "paper.sync.account":
        return ["uv", "run", "oc", "paper", "sync-account"]
    if action == "paper.kill_switch.enable":
        return ["uv", "run", "oc", "paper", "kill-switch", "--enable", "--reason", reason]
    if action == "paper.kill_switch.clear":
        return ["uv", "run", "oc", "paper", "kill-switch", "--disable", "--reason", reason]
    if action == "system.prepare_workspace":
        return ["uv", "run", "oc", "deploy", "prepare"]
    if action == "system.readiness.refresh":
        return ["uv", "run", "oc", "readiness"]
    if action == "strategy.draft":
        args = ["uv", "run", "oc", "strategy", "draft", "--idea", idea]
        if use_llm:
            args.append("--use-llm")
        return args
    if not bindings:
        return ["uv", "run", "oc", "dashboard", "command-run"]
    strategy_path = bindings[0].source_path
    if action == "strategy.workflow.verify":
        return ["uv", "run", "oc", "dashboard", "command-run"]
    if action == "strategy.validate":
        return ["uv", "run", "oc", "spec", "validate", strategy_path]
    if action == "strategy.capabilities.refresh":
        return ["uv", "run", "oc", "spec", "capabilities", strategy_path]
    if action == "strategy.approve":
        return ["uv", "run", "oc", "strategy", "approve", strategy_path]
    if action == "strategy.activate.manual":
        args = ["uv", "run", "oc", "strategy", "activate", strategy_path]
        if data_source != "keep":
            args.extend(["--data-source", data_source])
        return args
    if action == "strategy.activate.paper_auto":
        return [
            "uv",
            "run",
            "oc",
            "strategy",
            "activate",
            strategy_path,
            "--paper-auto",
            "--allow-paper-auto",
            "--data-source",
            data_source,
            "--enforce-paper-readiness",
        ]
    if action == "strategy.backtest.rerun":
        return ["uv", "run", "oc", "backtest", strategy_path]
    if action == "strategy.scan.rerun":
        return ["uv", "run", "oc", "scan", strategy_path]
    return ["uv", "run", "oc", "strategy", "disable", bindings[0].strategy_name]


def _command_id(action: DashboardCommandAction) -> str:
    now = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    normalized = action.replace(".", "_")
    return f"dashcmd_{normalized}_{now}"


def _plan_path(base: Path, command_id: str) -> Path:
    return base / "reports" / "dashboard" / "commands" / f"{command_id}.json"


def _result_path(base: Path, command_id: str) -> Path:
    return base / "reports" / "dashboard" / "commands" / f"{command_id}.result.json"


def _events_path(base: Path) -> Path:
    return base / "reports" / "dashboard" / "commands" / "events.jsonl"


def _write_result_and_event(
    base: Path,
    plan: DashboardCommandPlan,
    result: DashboardCommandResult,
) -> Path:
    path = _result_path(base, plan.command_id)
    result.result_path = _relpath(path, base)
    write_json(path, result)
    _append_command_event(
        base,
        DashboardCommandEvent(
            command_id=plan.command_id,
            action=plan.action,
            status=result.status,
            actor=result.executed_by,
            reason=plan.reason,
            plan_path=plan.plan_path,
            result_path=result.result_path,
            message=result.message,
        ),
    )
    return path


def _append_command_event(base: Path, event: DashboardCommandEvent) -> Path:
    path = _events_path(base)
    append_jsonl(path, [event])
    return path


def _relpath(path: Path, base: Path) -> str:
    try:
        return path.relative_to(base).as_posix()
    except ValueError:
        return path.as_posix()
