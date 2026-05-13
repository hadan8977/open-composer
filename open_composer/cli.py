from __future__ import annotations

import importlib.util
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

import typer
from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table

from open_composer.adapters.broker.alpaca_paper import (
    PaperOrderError,
    submit_paper_order,
    sync_paper_account,
    sync_paper_orders,
)
from open_composer.adapters.data import fetch_ohlcv
from open_composer.adapters.data.comparison import compare_ohlcv_sources
from open_composer.adapters.events import fetch_capability_events
from open_composer.adapters.execution import build_nautilus_trader_plan, write_nautilus_trader_plan
from open_composer.capabilities import evaluate_capabilities, load_registry
from open_composer.compiler.spec_to_pine import compile_pine, compile_pine_strategy
from open_composer.config import (
    alpaca_api_base_url,
    data_feed,
    default_openai_model,
    openai_base_url,
    openai_base_url_source,
    optional_env_status,
    project_root,
)
from open_composer.context import build_signal_context
from open_composer.dashboard import (
    DashboardCommandError,
    DashboardServerError,
    build_dashboard_catalog,
    build_dashboard_command_plan,
    build_feature_packet_records,
    execute_dashboard_command_plan,
    load_dashboard_command_plan,
    serve_dashboard,
    write_dashboard_catalog,
    write_dashboard_command_plan,
    write_dashboard_html,
    write_dashboard_review_markdown,
)
from open_composer.deployment import (
    ensure_runtime_dirs,
    prepare_workspace,
    write_feature_validation_report,
)
from open_composer.engines.backtest_engine import run_backtest
from open_composer.engines.scanner_engine import run_scan
from open_composer.feature_packets import (
    FeaturePacketError,
    build_context_feature_packet,
    build_manual_feature_packet,
    default_context_feature_path,
    parse_datetime,
    parse_feature_pairs,
    write_feature_packet,
)
from open_composer.journal.writer import add_journal_entry
from open_composer.models.strategy_spec import load_strategy_spec
from open_composer.paper_controls import (
    build_paper_alerts,
    build_paper_status,
    clear_paper_kill_switch,
    enable_paper_kill_switch,
    reconcile_paper_state,
    refresh_paper_monitor,
    run_paper_monitor_loop,
    write_paper_status,
)
from open_composer.paper_readiness import (
    assess_paper_strategy_readiness,
    write_paper_readiness_report,
)
from open_composer.readiness import build_readiness_report, write_readiness_report
from open_composer.research import (
    draft_strategy_from_idea,
    optimize_option_overlays,
    optimize_strategy,
    optimize_strategy_horizons,
    optimize_strategy_universe,
    parse_sweep_parameters,
    run_parameter_sweep,
)
from open_composer.review.llm import review_signal_with_status
from open_composer.runner.paper import PaperRunnerError, run_paper_loop
from open_composer.storage import find_signal
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
from open_composer.strategy_versions import (
    diff_strategy_versions,
    load_strategy_versions,
    register_strategy_version,
    rollback_strategy_version,
)

app = typer.Typer(no_args_is_help=True)
spec_app = typer.Typer(no_args_is_help=True)
data_app = typer.Typer(no_args_is_help=True)
compile_app = typer.Typer(no_args_is_help=True)
paper_app = typer.Typer(no_args_is_help=True)
journal_app = typer.Typer(no_args_is_help=True)
capability_app = typer.Typer(no_args_is_help=True)
events_app = typer.Typer(no_args_is_help=True)
macro_app = typer.Typer(no_args_is_help=True)
context_app = typer.Typer(no_args_is_help=True)
strategy_app = typer.Typer(no_args_is_help=True)
run_app = typer.Typer(no_args_is_help=True)
options_app = typer.Typer(no_args_is_help=True)
feature_app = typer.Typer(no_args_is_help=True)
deploy_app = typer.Typer(no_args_is_help=True)
dashboard_app = typer.Typer(no_args_is_help=True)
console = Console()

app.add_typer(spec_app, name="spec")
app.add_typer(data_app, name="data")
app.add_typer(compile_app, name="compile")
app.add_typer(paper_app, name="paper")
app.add_typer(journal_app, name="journal")
app.add_typer(capability_app, name="capability")
app.add_typer(events_app, name="events")
app.add_typer(macro_app, name="macro")
app.add_typer(context_app, name="context")
app.add_typer(strategy_app, name="strategy")
app.add_typer(run_app, name="run")
app.add_typer(options_app, name="options")
app.add_typer(feature_app, name="feature")
app.add_typer(deploy_app, name="deploy")
app.add_typer(dashboard_app, name="dashboard")


@app.callback()
def _load_env() -> None:
    root = project_root()
    load_dotenv(root / ".env")


@app.command()
def doctor() -> None:
    """Check local Open Composer environment status."""
    root = project_root()
    _ensure_runtime_dirs(root)
    table = Table(title="Open Composer Doctor")
    table.add_column("Check")
    table.add_column("Status")
    table.add_column("Detail")
    table.add_row("Python", "ok", sys.version.split()[0])
    for package in ["pydantic", "pandas", "numpy", "yaml", "typer", "rich"]:
        status = "ok" if importlib.util.find_spec(package) else "missing"
        table.add_row(f"Package {package}", status, "")
    sample_path = root / "data" / "sample" / "qqq_15m.csv"
    table.add_row("Sample data", "ok" if sample_path.exists() else "missing", str(sample_path))
    table.add_row(
        "OPENAI_API_KEY",
        optional_env_status("OPENAI_API_KEY"),
        "optional for review cards; presence only",
    )
    table.add_row(
        "OPENAI_BASE_URL",
        openai_base_url_source(),
        openai_base_url() or "optional OpenAI-compatible gateway",
    )
    table.add_row("OPENAI_MODEL", default_openai_model(), "default review model")
    table.add_row(
        "ALPACA_API_KEY_ID", optional_env_status("ALPACA_API_KEY_ID"), "optional for Alpaca"
    )
    table.add_row(
        "ALPACA_API_SECRET_KEY",
        optional_env_status("ALPACA_API_SECRET_KEY"),
        "optional for Alpaca",
    )
    table.add_row("ALPACA_PAPER", os.getenv("ALPACA_PAPER", "true"), "must remain true for orders")
    table.add_row("ALPACA_API_BASE_URL", alpaca_api_base_url(), "paper trading endpoint")
    table.add_row("ALPACA_DATA_FEED", data_feed(), "default feed")
    table.add_row(
        "OPEN_COMPOSER_DASHBOARD_TOKEN",
        optional_env_status("OPEN_COMPOSER_DASHBOARD_TOKEN"),
        "optional token for dashboard API",
    )
    table.add_row(
        "ALPHA_VANTAGE_API_KEY", optional_env_status("ALPHA_VANTAGE_API_KEY"), "optional news"
    )
    table.add_row("FRED_API_KEY", optional_env_status("FRED_API_KEY"), "optional macro")
    table.add_row(
        "LONGBRIDGE_APP_KEY", optional_env_status("LONGBRIDGE_APP_KEY"), "optional for Longbridge"
    )
    table.add_row(
        "LONGBRIDGE_APP_SECRET",
        optional_env_status("LONGBRIDGE_APP_SECRET"),
        "optional for Longbridge",
    )
    console.print(table)


@app.command("readiness")
def readiness_command(
    strict: Annotated[
        bool,
        typer.Option("--strict", help="Exit with code 1 when readiness is blocked."),
    ] = False,
    output: Annotated[
        Path | None,
        typer.Option("--output", help="Path for readiness JSON report."),
    ] = None,
) -> None:
    """Write and print a deployment readiness report."""
    root = project_root()
    report = build_readiness_report(root)
    json_path, md_path = write_readiness_report(report, root, output)
    table = Table(title="Open Composer Readiness")
    table.add_column("Check")
    table.add_column("Status")
    table.add_column("Message")
    table.add_column("Next action")
    for check in report.checks:
        table.add_row(
            check.name,
            check.status,
            check.message,
            check.suggested_actions[0] if check.suggested_actions else "",
        )
    console.print(table)
    console.print(f"status={report.status} ready={'yes' if report.ready else 'no'}")
    console.print(f"json={json_path}")
    console.print(f"markdown={md_path}")
    if strict and report.status == "blocked":
        raise typer.Exit(1)


@deploy_app.command("prepare")
def deploy_prepare_command(
    sync_broker: Annotated[
        bool,
        typer.Option("--sync-broker", help="Pull broker snapshots before refresh."),
    ] = False,
    strict: Annotated[
        bool,
        typer.Option("--strict", help="Exit with code 1 when deployment prepare is blocked."),
    ] = False,
) -> None:
    """Rebuild the local deployment surface for a smooth workspace startup."""
    root = project_root()
    report = prepare_workspace(root, sync_broker=sync_broker)
    table = Table(title="Open Composer Deployment Prepare")
    table.add_column("Step")
    table.add_column("Status")
    table.add_column("Message")
    table.add_column("Next action")
    for step in report.steps:
        table.add_row(
            step.name,
            step.status,
            step.message,
            step.suggested_actions[0] if step.suggested_actions else "",
        )
    console.print(table)
    console.print(f"status={report.status} ready={'yes' if report.ready else 'no'}")
    console.print(f"json={report.report_json_path}")
    console.print(f"markdown={report.report_markdown_path}")
    if strict and report.status == "blocked":
        raise typer.Exit(1)


@feature_app.command("validate")
def feature_validate_command(
    output: Annotated[
        Path | None,
        typer.Option("--output", help="Path for the feature validation report."),
    ] = None,
) -> None:
    """Validate feature packet logs and write a point-in-time report."""
    root = project_root()
    packets = build_feature_packet_records(root)
    report_path = output or root / "reports" / "features" / "validation.json"
    report_path, md_path, manifest_path = write_feature_validation_report(
        root,
        packets=packets,
        output_path=report_path,
    )
    table = Table(title="Feature Packet Validation")
    table.add_column("Packet")
    table.add_column("Status")
    table.add_column("Records")
    table.add_column("Warnings")
    for packet in packets:
        table.add_row(
            packet.path,
            packet.point_in_time_status,
            str(packet.record_count),
            "; ".join(packet.replay_warnings) or "none",
        )
    table.add_row("Report", "written", str(report_path), str(md_path))
    table.add_row("Manifest", "written", str(manifest_path), "")
    console.print(table)


@feature_app.command("write")
def feature_write_command(
    symbol: Annotated[str, typer.Option("--symbol", help="Feature packet symbol.")],
    timestamp: Annotated[str, typer.Option("--timestamp", help="Packet timestamp.")],
    features: Annotated[
        list[str] | None,
        typer.Option("--feature", "-f", help="Feature value as key=value; repeatable."),
    ] = None,
    output: Annotated[
        Path,
        typer.Option("--output", help="JSONL feature packet output path."),
    ] = Path("feature_logs/manual_features.jsonl"),
    source: Annotated[str, typer.Option("--source", help="Feature source label.")] = "manual",
    published_at: Annotated[
        str | None,
        typer.Option("--published-at", help="Point-in-time publication timestamp."),
    ] = None,
    fetched_at: Annotated[
        str | None,
        typer.Option("--fetched-at", help="Fetch timestamp."),
    ] = None,
    dedupe_key: Annotated[
        str | None,
        typer.Option("--dedupe-key", help="Stable feature packet dedupe key."),
    ] = None,
    schema_version: Annotated[
        str,
        typer.Option("--schema-version", help="Feature packet schema version."),
    ] = "1",
    model: Annotated[
        str | None,
        typer.Option("--model", help="Model identifier for LLM-produced features."),
    ] = None,
    input_hash: Annotated[
        str | None,
        typer.Option("--input-hash", help="Stable hash of the LLM feature input packet."),
    ] = None,
    prompt_hash: Annotated[
        str | None,
        typer.Option("--prompt-hash", help="Stable hash of the LLM feature prompt/template."),
    ] = None,
    summary: Annotated[str, typer.Option("--summary", help="Optional packet summary.")] = "",
    sentiment: Annotated[
        str,
        typer.Option("--sentiment", help="positive, neutral, negative, or unknown."),
    ] = "unknown",
) -> None:
    """Append a canonical point-in-time feature packet row."""
    if sentiment not in {"positive", "neutral", "negative", "unknown"}:
        raise typer.BadParameter("--sentiment must be positive, neutral, negative, or unknown")
    try:
        feature_map = parse_feature_pairs(features or [])
        if not feature_map:
            raise FeaturePacketError("pass at least one --feature key=value option")
        packet = build_manual_feature_packet(
            symbol=symbol,
            timestamp=parse_datetime(timestamp),
            source=source,
            features=feature_map,
            published_at=parse_datetime(published_at) if published_at else None,
            fetched_at=parse_datetime(fetched_at) if fetched_at else None,
            dedupe_key=dedupe_key,
            schema_version=schema_version,
            model=model,
            input_hash=input_hash,
            prompt_hash=prompt_hash,
            summary=summary,
            sentiment=sentiment,  # type: ignore[arg-type]
        )
    except FeaturePacketError as exc:
        raise typer.BadParameter(str(exc)) from exc
    root = project_root()
    path = _resolve_output_path(root, output)
    write_feature_packet(path, packet)
    console.print(f"[green]feature packet written[/green] {path} features={len(packet.features)}")


@feature_app.command("from-context")
def feature_from_context_command(
    signal_id: str,
    output: Annotated[
        Path | None,
        typer.Option("--output", help="JSONL feature packet output path."),
    ] = None,
) -> None:
    """Convert a signal context packet into replayable feature values."""
    root = project_root()
    try:
        packet = build_context_feature_packet(signal_id, root)
    except (FeaturePacketError, FileNotFoundError) as exc:
        raise typer.BadParameter(str(exc)) from exc
    path = _resolve_output_path(root, output or default_context_feature_path(root, signal_id))
    write_feature_packet(path, packet)
    console.print(
        f"[green]context feature packet written[/green] {path} features={len(packet.features)}"
    )


@dashboard_app.command("catalog")
def dashboard_catalog_command(
    output: Annotated[
        Path | None,
        typer.Option("--output", help="Path for the JSON dashboard catalog."),
    ] = None,
    markdown: Annotated[
        Path | None,
        typer.Option("--markdown", help="Path for the Markdown dashboard summary."),
    ] = None,
) -> None:
    """Build a rebuildable read model for strategies, runs, signals, reviews, and audits."""
    root = project_root()
    output_path = output or root / "reports" / "dashboard" / "catalog.json"
    markdown_path = markdown or root / "reports" / "dashboard" / "catalog.md"
    catalog = build_dashboard_catalog(root)
    artifacts = write_dashboard_catalog(catalog, root, output_path, markdown_path)
    table = Table(title="Dashboard Catalog")
    table.add_column("Metric")
    table.add_column("Value")
    table.add_row("Strategies", str(catalog.summary.strategy_count))
    table.add_row("Versions", str(catalog.summary.version_count))
    table.add_row("Runs", str(catalog.summary.run_count))
    table.add_row("Signals", str(catalog.summary.signal_count))
    table.add_row("Reviews", str(catalog.summary.review_count))
    table.add_row("Contexts", str(catalog.summary.context_count))
    table.add_row("Journal entries", str(catalog.summary.journal_count))
    table.add_row("Paper orders", str(catalog.summary.order_count))
    table.add_row("Audit events", str(catalog.summary.audit_count))
    table.add_row("Data comparisons", str(catalog.summary.data_comparison_count))
    table.add_row("Readiness", catalog.summary.readiness_status)
    table.add_row("Deployment", catalog.summary.deployment_status)
    table.add_row("Read model", str(artifacts.catalog_path))
    table.add_row("Summary markdown", str(artifacts.markdown_path))
    console.print(table)


@dashboard_app.command("review-plan")
def dashboard_review_plan_command(
    output: Annotated[
        Path | None,
        typer.Option("--output", help="Path for the Dashboard D0 review document."),
    ] = None,
) -> None:
    """Write a strict D0 review of the current Dashboard plan against repo artifacts."""
    root = project_root()
    output_path = output or root / "docs" / "dashboard-d0-review.zh.md"
    catalog = build_dashboard_catalog(root)
    path = write_dashboard_review_markdown(catalog, output_path, root)
    console.print(f"[green]dashboard review written[/green] {path}")


@dashboard_app.command("html")
def dashboard_html_command(
    output: Annotated[
        Path | None,
        typer.Option("--output", help="Path for the read-only static Dashboard HTML."),
    ] = None,
) -> None:
    """Build a read-only static Dashboard page from the dashboard catalog."""
    root = project_root()
    output_path = output or root / "reports" / "dashboard" / "index.html"
    catalog = build_dashboard_catalog(root)
    write_dashboard_catalog(catalog, root)
    path = write_dashboard_html(catalog, root, output_path)
    console.print(f"[green]dashboard html written[/green] {path}")


@dashboard_app.command("serve")
def dashboard_serve_command(
    host: Annotated[
        str,
        typer.Option("--host", help="Host interface for the local dashboard server."),
    ] = "127.0.0.1",
    port: Annotated[
        int,
        typer.Option("--port", help="Port for the local dashboard server."),
    ] = 8000,
    api_token: Annotated[
        str | None,
        typer.Option(
            "--api-token",
            help=(
                "Optional Dashboard API token. Defaults to OPEN_COMPOSER_DASHBOARD_TOKEN when set."
            ),
        ),
    ] = None,
) -> None:
    """Serve the built React dashboard or the static read-only HTML locally."""
    try:
        serve_dashboard(project_root(), host=host, port=port, api_token=api_token)
    except DashboardServerError as exc:
        raise typer.BadParameter(str(exc)) from exc


@dashboard_app.command("command-plan")
def dashboard_command_plan_command(
    action: str,
    reason: Annotated[
        str,
        typer.Option("--reason", help="Reason recorded with the command plan."),
    ] = "",
    requested_by: Annotated[
        str,
        typer.Option("--requested-by", help="Actor recorded on the command plan."),
    ] = "dashboard",
    strategy_path: Annotated[
        str | None,
        typer.Option("--strategy-path", help="Strategy YAML path or name for lifecycle commands."),
    ] = None,
    data_source: Annotated[
        str,
        typer.Option("--data-source", help="Data source used when activating a strategy."),
    ] = "keep",
    idea: Annotated[
        str,
        typer.Option("--idea", help="Natural-language idea for strategy.draft."),
    ] = "",
    use_llm: Annotated[
        bool,
        typer.Option("--use-llm", help="Allow LLM drafting for strategy.draft."),
    ] = False,
    output: Annotated[
        Path | None,
        typer.Option("--output", help="Path for the command plan JSON."),
    ] = None,
) -> None:
    """Create a local Dashboard command plan without executing it."""
    allowed = {
        "paper.status.refresh",
        "paper.monitor.refresh",
        "paper.sync.orders",
        "paper.sync.account",
        "paper.kill_switch.enable",
        "paper.kill_switch.clear",
        "system.prepare_workspace",
        "system.readiness.refresh",
        "strategy.draft",
        "strategy.workflow.verify",
        "strategy.validate",
        "strategy.capabilities.refresh",
        "strategy.approve",
        "strategy.activate.manual",
        "strategy.activate.paper_auto",
        "strategy.backtest.rerun",
        "strategy.scan.rerun",
        "strategy.disable",
    }
    if action not in allowed:
        raise typer.BadParameter(f"action must be one of: {', '.join(sorted(allowed))}")
    root = project_root()
    plan = build_dashboard_command_plan(
        action,  # type: ignore[arg-type]
        root,
        reason=reason,
        requested_by=requested_by,
        strategy_path=strategy_path,
        data_source=data_source,
        idea=idea,
        use_llm=use_llm,
    )
    path = write_dashboard_command_plan(plan, root, output)
    console.print(f"[green]dashboard command plan written[/green] {path}")
    console.print(f"confirmation_phrase={plan.confirmation_phrase!r}")
    console.print("cli=" + " ".join(plan.cli_args))


@dashboard_app.command("command-run")
def dashboard_command_run_command(
    plan: Path,
    confirm: Annotated[
        str,
        typer.Option("--confirm", help="Exact confirmation phrase from the command plan."),
    ],
    executed_by: Annotated[
        str,
        typer.Option("--executed-by", help="Actor recorded on the command result."),
    ] = "dashboard",
) -> None:
    """Execute a paper-only Dashboard command plan after explicit confirmation."""
    root = project_root()
    command_plan = load_dashboard_command_plan(plan)
    try:
        result = execute_dashboard_command_plan(
            command_plan,
            root,
            confirmation=confirm,
            executed_by=executed_by,
        )
    except DashboardCommandError as exc:
        raise typer.BadParameter(str(exc)) from exc
    console.print(f"[green]dashboard command executed[/green] {result.result_path}")
    console.print(result.message)


@capability_app.command("list")
def capability_list() -> None:
    """List registered strategy/data capabilities."""
    registry = load_registry(project_root())
    table = Table(title="Open Composer Capabilities")
    table.add_column("ID")
    table.add_column("Kind")
    table.add_column("Status")
    table.add_column("Reliability")
    table.add_column("Provider")
    for capability in registry.capabilities:
        table.add_row(
            capability.id,
            capability.kind,
            capability.status,
            capability.reliability,
            capability.provider,
        )
    console.print(table)


@capability_app.command("test")
def capability_test() -> None:
    """Evaluate capability fixtures for coverage, validity, and dedupe hygiene."""
    evaluations = evaluate_capabilities(project_root())
    failed = [evaluation for evaluation in evaluations if not evaluation.passed]
    for evaluation in evaluations:
        color = "green" if evaluation.passed else "red"
        console.print(
            f"[{color}]{evaluation.capability_id}[/{color}] "
            f"score={evaluation.score:.2f} records={evaluation.records}"
        )
    if failed:
        raise typer.Exit(code=1)


@spec_app.command("validate")
def spec_validate(path: Path) -> None:
    """Validate a StrategySpec YAML file and supported expressions."""
    spec = load_strategy_spec(path)
    console.print(f"[green]valid[/green] {path} ({spec.name})")


@spec_app.command("capabilities")
def spec_capabilities(
    path: Path,
    json_output: bool = typer.Option(False, "--json", help="Print machine-readable JSON."),
) -> None:
    """Assess StrategySpec compatibility across backtest, Pine, Alpaca, and LLM workflows."""
    report = assess_strategy_capabilities(path)
    if json_output:
        print(
            json.dumps(
                _strategy_capability_payload(report),
                indent=2,
            )
        )
        return

    table = Table(title=f"Strategy Capabilities: {report.strategy_name}")
    table.add_column("Capability")
    table.add_column("Status")
    table.add_column("Reasons")
    for finding in report.findings:
        table.add_row(finding.capability, finding.status, "\n".join(finding.reasons))
    console.print(table)
    backend = report.backend_plan
    backend_table = Table(title=f"NautilusTrader Backend Plan: {report.strategy_name}")
    backend_table.add_column("Field")
    backend_table.add_column("Value")
    backend_table.add_row("Target backend", backend.target_backend)
    backend_table.add_row("Selected backend", backend.selected_backend)
    backend_table.add_row("Status", backend.status)
    backend_table.add_row("Supported", "yes" if backend.supported else "no")
    backend_table.add_row("Installed", "yes" if backend.nautilus_installed else "no")
    backend_table.add_row("Reasons", "\n".join(backend.reasons))
    console.print(backend_table)
    console.print(
        "expressions: "
        f"names={','.join(report.expression_names) or 'none'} "
        f"functions={','.join(report.expression_functions) or 'none'}"
    )


@spec_app.command("backend-plan")
def spec_backend_plan(
    path: Path,
    json_output: bool = typer.Option(False, "--json", help="Print machine-readable JSON."),
    output: Annotated[
        Path | None,
        typer.Option("--output", help="Optional JSON output path."),
    ] = None,
) -> None:
    """Build the NautilusTrader compatibility plan for a StrategySpec."""
    plan = build_nautilus_trader_plan(path, project_root())
    if output is not None:
        write_nautilus_trader_plan(output, plan)
        console.print(f"[green]backend plan written[/green] {output}")
    if json_output:
        print(json.dumps(plan.model_dump(mode="json"), indent=2))
        return
    table = Table(title=f"NautilusTrader Backend Plan: {plan.strategy_name}")
    table.add_column("Field")
    table.add_column("Value")
    table.add_row("Selected backend", plan.selected_backend)
    table.add_row("Target backend", plan.target_backend)
    table.add_row("Status", plan.status)
    table.add_row("Supported", "yes" if plan.supported else "no")
    table.add_row("Installed", "yes" if plan.nautilus_installed else "no")
    table.add_row("Execution mode", plan.execution_mode)
    table.add_row("Broker", plan.broker)
    table.add_row("Data source", plan.data_source)
    table.add_row("Symbol", plan.symbol)
    table.add_row("Timeframe", plan.timeframe)
    table.add_row("Factors", ", ".join(plan.factor_names) or "none")
    table.add_row("LLM feature factors", ", ".join(plan.llm_feature_factor_names) or "none")
    table.add_row(
        "Feature packet factors",
        ", ".join(plan.feature_packet_factor_names) or "none",
    )
    table.add_row("Required capabilities", ", ".join(plan.required_capabilities) or "none")
    table.add_row("Reasons", "\n".join(plan.reasons))
    console.print(table)


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


@data_app.command("fetch")
def data_fetch(
    symbol: str = typer.Option("QQQ", "--symbol"),
    timeframe: str = typer.Option("15m", "--timeframe"),
    source: str = typer.Option("alpaca", "--source"),
    start: str | None = typer.Option(None, "--start"),
    end: str | None = typer.Option(None, "--end"),
    feed: str | None = typer.Option(None, "--feed"),
) -> None:
    """Fetch OHLCV bars into data/cache."""
    root = project_root()
    frame = fetch_ohlcv(
        root=root,
        symbol=symbol.upper(),
        timeframe=timeframe,
        start=_parse_datetime(start),
        end=_parse_datetime(end),
        source=source,
        feed=feed,
    )
    console.print(
        f"[green]fetched[/green] {len(frame)} bars for {symbol.upper()} {timeframe} source={source}"
    )


@data_app.command("compare")
def data_compare(
    symbol: str = typer.Option("QQQ", "--symbol"),
    timeframe: str = typer.Option("15m", "--timeframe"),
    left: str = typer.Option("alpaca", "--left"),
    right: str = typer.Option("longbridge", "--right"),
    left_feed: str | None = typer.Option(None, "--left-feed"),
    right_feed: str | None = typer.Option(None, "--right-feed"),
) -> None:
    """Compare two OHLCV sources and write a diff report."""
    root = project_root()
    comparison = compare_ohlcv_sources(
        root=root,
        symbol=symbol.upper(),
        timeframe=timeframe,
        left_source=left,
        right_source=right,
        left_feed=left_feed,
        right_feed=right_feed,
    )
    console.print(
        "[green]comparison written[/green] "
        f"{comparison.report_markdown_path} close_diff={comparison.max_abs_close_diff:.6f} "
        f"close_diff_bps={comparison.max_abs_close_diff_bps:.2f} "
        f"matched={comparison.matched_rows} coverage={comparison.matched_coverage_pct:.2f}%"
    )


@events_app.command("fetch")
def events_fetch(
    source: str = typer.Option("sec", "--source"),
    symbols: str = typer.Option("QQQ", "--symbols"),
    offline: bool = typer.Option(True, "--offline/--live"),
) -> None:
    """Fetch or replay event/news records into raw event logs."""
    selected_symbols = [symbol.strip().upper() for symbol in symbols.split(",") if symbol.strip()]
    events = fetch_capability_events(source, project_root(), selected_symbols, offline=offline)
    console.print(f"[green]events fetched[/green] source={source} records={len(events)}")


@macro_app.command("fetch")
def macro_fetch(
    source: str = typer.Option("fred", "--source"),
    offline: bool = typer.Option(True, "--offline/--live"),
) -> None:
    """Fetch or replay macro records into raw macro logs."""
    events = fetch_capability_events(source, project_root(), None, offline=offline)
    console.print(f"[green]macro fetched[/green] source={source} records={len(events)}")


@app.command()
def backtest(spec: Path) -> None:
    """Run a deterministic backtest from a StrategySpec."""
    artifacts = run_backtest(spec)
    console.print(
        f"[green]backtest complete[/green] {artifacts.run.run_id} "
        f"return={artifacts.run.total_return_pct:.2f}%"
    )
    console.print(f"report: {artifacts.run.report_path}")
    console.print(f"signals: {artifacts.run.signal_log_path}")


@app.command()
def scan(
    spec: Path,
    with_context: bool = typer.Option(False, "--with-context"),
    refresh_data: bool = typer.Option(False, "--refresh-data"),
) -> None:
    """Scan the latest bar for a StrategySpec."""
    signals = run_scan(spec, refresh_data=refresh_data)
    console.print(f"[green]scan complete[/green] signals={len(signals)}")
    for signal in signals:
        console.print(f"{signal.id} {signal.action} {signal.symbol} @ {signal.price:.2f}")
        if with_context:
            context = build_signal_context(signal.id, project_root())
            console.print(
                f"context: events={len(context.events)} macro={len(context.macro)} "
                f"news={len(context.news)}"
            )


@compile_app.command("pine")
def compile_pine_command(spec: Path) -> None:
    """Compile a StrategySpec to TradingView Pine Script."""
    path = compile_pine(spec)
    console.print(f"[green]pine generated[/green] {path}")


@compile_app.command("pine-strategy")
def compile_pine_strategy_command(spec: Path) -> None:
    """Compile a StrategySpec to a TradingView Strategy Tester Pine Script."""
    path = compile_pine_strategy(spec)
    console.print(f"[green]pine strategy generated[/green] {path}")


@app.command("review-signal")
def review_signal(signal_id: str) -> None:
    """Generate an optional OpenAI structured review card for a signal."""
    root = project_root()
    signal = find_signal(signal_id, root)
    spec_path = _find_strategy_spec(signal.strategy_name, root)
    spec = load_strategy_spec(spec_path)
    result = review_signal_with_status(signal, spec, root)
    if result.review is None:
        console.print(f"[yellow]review skipped[/yellow] {result.message}")
        return
    console.print(f"[green]review written[/green] reports/reviews/{signal.id}.json")


@context_app.command("build")
def context_build(signal_id: str) -> None:
    """Build a deterministic event/macro/news context packet for a signal."""
    context = build_signal_context(signal_id, project_root())
    console.print(
        f"[green]context written[/green] reports/context/{signal_id}.json "
        f"events={len(context.events)} macro={len(context.macro)} news={len(context.news)}"
    )


@strategy_app.command("draft")
def strategy_draft(
    idea: str = typer.Option(..., "--idea"),
    use_llm: bool = typer.Option(False, "--use-llm"),
) -> None:
    """Draft a StrategySpec from a natural-language idea using registered capabilities."""
    path = draft_strategy_from_idea(idea, project_root(), use_llm=use_llm)
    spec = load_strategy_spec(path)
    console.print(f"[green]draft written[/green] {path} ({spec.name})")


@strategy_app.command("optimize")
def strategy_optimize(
    spec: Path,
    min_return_pct: float = typer.Option(1.0, "--min-return-pct"),
    min_signals: int = typer.Option(1, "--min-signals"),
    min_sharpe: float = typer.Option(0.0, "--min-sharpe"),
) -> None:
    """Generate candidate rule variants and select the best deterministic backtest result."""
    result = optimize_strategy(spec, project_root(), min_return_pct, min_signals, min_sharpe)
    console.print(
        f"[green]optimized[/green] {result.best_spec_path} "
        f"return={result.best_artifacts.run.total_return_pct:.2f}% "
        f"signals={result.best_artifacts.run.signals}"
    )
    console.print(f"report: {result.report_path}")


@strategy_app.command("parameter-sweep")
def strategy_parameter_sweep(
    spec: Path,
    params: Annotated[
        list[str] | None,
        typer.Option(
            "--param",
            help=(
                "Sweep PATH=values. Use comma-separated scalar values or pipe-separated "
                "expressions, for example risk.stop_loss_pct=0.8,1.2 or "
                "'entry.all.0=close > ema(close, 5)|close > ema(close, 8)'."
            ),
        ),
    ] = None,
    min_return_pct: float = typer.Option(0.0, "--min-return-pct"),
    min_signals: int = typer.Option(1, "--min-signals"),
    min_sharpe: float = typer.Option(0.0, "--min-sharpe"),
    max_candidates: int = typer.Option(200, "--max-candidates"),
    top_n: int = typer.Option(10, "--top-n"),
    write_top: int = typer.Option(1, "--write-top"),
) -> None:
    """Run a bounded parameter grid over a StrategySpec and write ranked reports."""
    try:
        parsed = parse_sweep_parameters(params or [])
        result = run_parameter_sweep(
            spec,
            parsed,
            project_root(),
            min_return_pct=min_return_pct,
            min_signals=min_signals,
            min_sharpe=min_sharpe,
            max_candidates=max_candidates,
            top_n=top_n,
            write_top=write_top,
        )
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    console.print(
        f"[green]parameter sweep complete[/green] candidates={len(result.candidates)} "
        f"best={result.best.spec.name} score={result.best.score:.2f}"
    )
    console.print(f"report: {result.report_path}")
    console.print(f"json: {result.json_path}")
    for path in result.written_specs:
        console.print(f"spec: {path}")


@strategy_app.command("optimize-universe")
def strategy_optimize_universe(
    spec: Path,
    symbols: str = typer.Option(..., "--symbols"),
    data_source: str = typer.Option("alpaca", "--data-source"),
    min_return_pct: float = typer.Option(1.0, "--min-return-pct"),
    min_signals: int = typer.Option(1, "--min-signals"),
    max_trades: int = typer.Option(45, "--max-trades"),
    refresh_data: bool = typer.Option(True, "--refresh-data/--use-cache"),
) -> None:
    """Optimize one strategy family across a symbol universe."""
    if data_source not in {"alpaca", "longbridge"}:
        raise typer.BadParameter("--data-source currently supports alpaca or longbridge")
    result = optimize_strategy_universe(
        spec,
        project_root(),
        symbols=[item.strip().upper() for item in symbols.split(",") if item.strip()],
        data_source=data_source,  # type: ignore[arg-type]
        min_return_pct=min_return_pct,
        min_signals=min_signals,
        max_trades=max_trades,
        refresh_data=refresh_data,
    )
    console.print(f"[green]universe optimized[/green] report: {result.report_path}")
    for selection in result.selections:
        console.print(
            f"{selection.symbol} {selection.spec.name} "
            f"return={selection.artifacts.run.total_return_pct:.2f}% "
            f"signals={selection.artifacts.run.signals} "
            f"trades={selection.artifacts.run.trades} score={selection.score:.2f}"
        )


@strategy_app.command("optimize-horizons")
def strategy_optimize_horizons(
    spec: Path,
    symbols: str = typer.Option(..., "--symbols"),
    data_source: str = typer.Option("alpaca", "--data-source"),
    min_return_pct: float = typer.Option(1.0, "--min-return-pct"),
    min_sharpe: float = typer.Option(0.0, "--min-sharpe"),
    min_trades: int = typer.Option(1, "--min-trades"),
    max_preferred_trades: int = typer.Option(18, "--max-preferred-trades"),
    refresh_data: bool = typer.Option(True, "--refresh-data/--use-cache"),
) -> None:
    """Compare 5m scan speed, 15m lower-turnover, and 1h trend-hold variants."""
    if data_source not in {"alpaca", "longbridge"}:
        raise typer.BadParameter("--data-source currently supports alpaca or longbridge")
    result = optimize_strategy_horizons(
        spec,
        project_root(),
        symbols=[item.strip().upper() for item in symbols.split(",") if item.strip()],
        data_source=data_source,  # type: ignore[arg-type]
        min_return_pct=min_return_pct,
        min_sharpe=min_sharpe,
        min_trades=min_trades,
        max_preferred_trades=max_preferred_trades,
        refresh_data=refresh_data,
    )
    console.print(f"[green]horizons optimized[/green] report: {result.report_path}")
    for selection in result.selections:
        console.print(
            f"{selection.symbol} {selection.spec.name} "
            f"profile={selection.profile} timeframe={selection.spec.timeframe} "
            f"return={selection.artifacts.run.total_return_pct:.2f}% "
            f"trades={selection.artifacts.run.trades} score={selection.score:.2f}"
        )


@strategy_app.command("list")
def strategy_list() -> None:
    """List StrategySpecs by lifecycle."""
    table = Table(title="Open Composer Strategies")
    table.add_column("Name")
    table.add_column("Lifecycle")
    table.add_column("Execution")
    table.add_column("Broker")
    table.add_column("Data")
    table.add_column("Path")
    for item in list_strategies(project_root()):
        table.add_row(
            item.name,
            item.lifecycle,
            item.execution_mode,
            item.broker,
            item.data_source,
            str(item.path),
        )
    console.print(table)


@strategy_app.command("versions")
def strategy_versions_command(
    strategy: Annotated[
        str | None,
        typer.Option("--strategy", help="Filter versions by strategy name."),
    ] = None,
) -> None:
    """List immutable StrategySpec versions registered from drafts, runs, and lifecycle moves."""
    versions = load_strategy_versions(project_root(), strategy)
    table = Table(title="Open Composer Strategy Versions")
    table.add_column("Strategy")
    table.add_column("Version")
    table.add_column("Lifecycle")
    table.add_column("Symbol")
    table.add_column("Timeframe")
    table.add_column("Execution")
    table.add_column("Created")
    table.add_column("Snapshot")
    for version in versions:
        table.add_row(
            version.strategy_name,
            version.version_id,
            version.lifecycle,
            version.symbol,
            version.timeframe,
            version.execution_mode,
            version.created_at.isoformat(),
            version.snapshot_path,
        )
    console.print(table)


@strategy_app.command("register-version")
def strategy_register_version(spec: str) -> None:
    """Register the current StrategySpec file as an immutable version snapshot."""
    root = project_root()
    version = register_strategy_version(
        resolve_strategy_path(spec, root),
        root,
        created_by="strategy_register_version",
    )
    console.print(f"[green]version registered[/green] {version.strategy_name} {version.version_id}")


@strategy_app.command("diff-versions")
def strategy_diff_versions(
    strategy: str,
    left_version: str,
    right_version: str,
) -> None:
    """Print a unified diff between two immutable StrategySpec versions."""
    try:
        diff = diff_strategy_versions(project_root(), strategy, left_version, right_version)
    except FileNotFoundError as exc:
        raise typer.BadParameter(str(exc)) from exc
    if not diff.changed:
        console.print("[green]no changes[/green]")
        return
    console.print("\n".join(diff.diff_lines))


@strategy_app.command("rollback-version")
def strategy_rollback_version(
    strategy: str,
    version: str,
) -> None:
    """Restore a registered version into drafts/manual mode for review."""
    try:
        result = rollback_strategy_version(project_root(), strategy, version)
    except FileNotFoundError as exc:
        raise typer.BadParameter(str(exc)) from exc
    console.print(
        f"[green]rollback draft written[/green] {result.path} "
        f"version={result.version.version_id} parent={version}"
    )


@strategy_app.command("approve")
def strategy_approve(spec: str) -> None:
    """Promote a StrategySpec to approved/manual mode."""
    root = project_root()
    path = approve_strategy(resolve_strategy_path(spec, root), root)
    console.print(f"[green]approved[/green] {path}")


@strategy_app.command("activate")
def strategy_activate(
    spec: str,
    paper_auto: bool = typer.Option(False, "--paper-auto"),
    allow_paper_auto: bool = typer.Option(False, "--allow-paper-auto"),
    data_source: str = typer.Option("keep", "--data-source"),
    enforce_paper_readiness: bool = typer.Option(False, "--enforce-paper-readiness"),
) -> None:
    """Activate a StrategySpec for manual signals or Alpaca Paper automation."""
    if data_source not in {"keep", "sample", "alpaca", "longbridge"}:
        raise typer.BadParameter("--data-source must be keep, sample, alpaca, or longbridge")
    root = project_root()
    try:
        path = activate_strategy(
            resolve_strategy_path(spec, root),
            root,
            paper_auto=paper_auto,
            allow_paper_auto=allow_paper_auto,
            data_source=data_source,  # type: ignore[arg-type]
            enforce_paper_readiness=enforce_paper_readiness,
        )
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    mode = "paper_auto" if paper_auto else "manual_signal"
    console.print(f"[green]active[/green] {path} mode={mode}")


@strategy_app.command("disable")
def strategy_disable(strategy: str) -> None:
    """Disable an active strategy and move it to retired/manual mode."""
    try:
        path = disable_strategy(strategy, project_root())
    except FileNotFoundError as exc:
        raise typer.BadParameter(str(exc)) from exc
    console.print(f"[yellow]disabled[/yellow] retired={path}")


@run_app.command("paper")
def run_paper(
    strategy: str,
    max_cycles: int = typer.Option(1, "--max-cycles"),
    interval_seconds: float = typer.Option(60.0, "--interval-seconds"),
    allow_paper_orders: bool = typer.Option(False, "--allow-paper-orders"),
    with_review: bool = typer.Option(True, "--with-review/--no-review"),
    require_review_consider: bool = typer.Option(False, "--require-review-consider"),
) -> None:
    """Run an active strategy against scanner/review/Alpaca Paper controls."""
    try:
        cycles = run_paper_loop(
            strategy,
            root=project_root(),
            allow_paper_orders=allow_paper_orders,
            with_review=with_review,
            require_review_consider=require_review_consider,
            interval_seconds=interval_seconds,
            max_cycles=max_cycles,
        )
    except (FileNotFoundError, PaperRunnerError) as exc:
        raise typer.BadParameter(str(exc)) from exc
    for cycle in cycles:
        console.print(
            f"[green]paper cycle[/green] {cycle.run_id} "
            f"signals={len(cycle.signals)} report=reports/runs/{cycle.run_id}.md"
        )
        if cycle.backend_plan_path:
            console.print(f"backend plan: {cycle.backend_plan_path}")
        if cycle.paper_readiness_report_path:
            console.print(f"paper readiness: {cycle.paper_readiness_report_path}")
        for note in cycle.notes:
            console.print(f"note: {note}")
        for item in cycle.signals:
            console.print(
                f"{item.signal_id} {item.action} {item.symbol} @ {item.price:.2f} "
                f"decision={item.decision} review={item.review_verdict or item.review_status}"
            )


@options_app.command("optimize")
def options_optimize(
    specs: Annotated[list[Path], typer.Argument(...)],
    max_premium_weight: float = typer.Option(0.03, "--max-premium-weight"),
    min_trades: int = typer.Option(1, "--min-trades"),
) -> None:
    """Optimize paper-only option overlays for one or more equity StrategySpecs."""
    result = optimize_option_overlays(
        specs,
        project_root(),
        max_premium_weight=max_premium_weight,
        min_trades=min_trades,
    )
    console.print(f"[green]options optimized[/green] report: {result.report_path}")
    for item in result.artifacts:
        console.print(
            f"{item.run.symbol} {item.spec.name} "
            f"return={item.run.total_return_pct:.2f}% "
            f"trades={item.run.trades} score={item.score:.2f}"
        )


@paper_app.command("submit")
def paper_submit(
    signal_id: str,
    allow_paper_orders: bool = typer.Option(False, "--allow-paper-orders"),
    qty: float | None = typer.Option(None, "--qty"),
) -> None:
    """Submit a signal to Alpaca Paper after explicit confirmation."""
    if not allow_paper_orders:
        raise typer.BadParameter("pass --allow-paper-orders to submit a paper order")
    root = project_root()
    signal = find_signal(signal_id, root)
    spec_path = _find_strategy_spec(signal.strategy_name, root)
    spec = load_strategy_spec(spec_path)
    try:
        order = submit_paper_order(signal, spec, root, qty=qty)
    except PaperOrderError as exc:
        raise typer.BadParameter(str(exc)) from exc
    console.print(f"[green]paper order[/green] {order.id} status={order.status} qty={order.qty}")


@paper_app.command("readiness")
def paper_readiness(
    strategy: str,
    strict: Annotated[
        bool,
        typer.Option("--strict", help="Exit with code 1 when paper readiness is blocked."),
    ] = False,
    output: Annotated[
        Path | None,
        typer.Option("--output", help="Path for the paper readiness JSON report."),
    ] = None,
) -> None:
    """Check whether a strategy is ready for Alpaca Paper automation."""
    root = project_root()
    try:
        report = assess_paper_strategy_readiness(resolve_strategy_path(strategy, root), root)
    except (FileNotFoundError, ValueError) as exc:
        raise typer.BadParameter(str(exc)) from exc
    json_path, md_path = write_paper_readiness_report(report, root, output)
    table = Table(title=f"Paper Readiness: {report.strategy_name}")
    table.add_column("Check")
    table.add_column("Status")
    table.add_column("Message")
    for check in report.checks:
        table.add_row(check.name, check.status, check.message)
    console.print(table)
    console.print(f"status={report.status} ready={'yes' if report.ready else 'no'}")
    console.print(f"json={json_path}")
    console.print(f"markdown={md_path}")
    if strict and report.status == "blocked":
        raise typer.Exit(1)


@paper_app.command("sync")
def paper_sync() -> None:
    """Sync Alpaca Paper orders to reports/paper/sync.jsonl."""
    try:
        path = sync_paper_orders(project_root())
    except PaperOrderError as exc:
        raise typer.BadParameter(str(exc)) from exc
    console.print(f"[green]paper sync written[/green] {path}")


@paper_app.command("sync-account")
def paper_sync_account() -> None:
    """Sync Alpaca Paper account and positions to reports/paper."""
    try:
        account_path, positions_path = sync_paper_account(project_root())
    except PaperOrderError as exc:
        raise typer.BadParameter(str(exc)) from exc
    console.print(
        f"[green]paper account sync written[/green] account={account_path} "
        f"positions={positions_path}"
    )


@paper_app.command("status")
def paper_status() -> None:
    """Write and print a local paper status snapshot."""
    snapshot = build_paper_status(project_root())
    path = write_paper_status(project_root())
    console.print(f"[green]paper status written[/green] {path}")
    console.print(
        f"kill_switch={'on' if snapshot.kill_switch.enabled else 'off'} "
        f"open_orders={snapshot.open_order_count} "
        f"positions={snapshot.position_count} "
        f"active_paper_auto={len(snapshot.active_paper_auto_strategies)}"
    )


@paper_app.command("reconcile")
def paper_reconcile() -> None:
    """Check local paper orders against account and positions snapshots."""
    report = reconcile_paper_state(project_root())
    write_paper_status(project_root())
    console.print(
        f"[green]paper reconciliation written[/green] {report.report_markdown_path} "
        f"status={report.status} issues={report.issue_count}"
    )


@paper_app.command("alerts")
def paper_alerts() -> None:
    """Build local paper monitoring alerts from status and reconciliation artifacts."""
    report = build_paper_alerts(project_root())
    write_paper_status(project_root())
    console.print(
        f"[green]paper alerts written[/green] {report.report_markdown_path} "
        f"status={report.status} alerts={report.alert_count}"
    )


@paper_app.command("monitor")
def paper_monitor(
    sync_broker: bool = typer.Option(
        False,
        "--sync-broker",
        help="Sync Alpaca Paper orders, account, and positions before monitoring.",
    ),
) -> None:
    """Refresh local paper reconciliation, alerts, and status artifacts."""
    report = refresh_paper_monitor(project_root(), sync_broker=sync_broker)
    console.print(
        f"[green]paper monitor refreshed[/green] {report.report_markdown_path} "
        f"status={report.status} alerts={report.alert_count} sync={report.sync_status}"
    )


@paper_app.command("monitor-loop")
def paper_monitor_loop(
    interval_seconds: float = typer.Option(60.0, "--interval-seconds"),
    max_cycles: int = typer.Option(1, "--max-cycles"),
    sync_broker: bool = typer.Option(
        False,
        "--sync-broker",
        help="Sync Alpaca Paper orders, account, and positions before each monitor cycle.",
    ),
) -> None:
    """Run repeated local paper monitor refresh cycles."""
    reports = run_paper_monitor_loop(
        project_root(),
        interval_seconds=interval_seconds,
        max_cycles=max_cycles,
        sync_broker=sync_broker,
    )
    latest = reports[-1] if reports else None
    console.print(
        "[green]paper monitor loop complete[/green] "
        f"cycles={len(reports)} "
        f"status={latest.status if latest else 'n/a'}"
    )


@paper_app.command("kill-switch")
def paper_kill_switch(
    enable: bool = typer.Option(False, "--enable/--disable"),
    reason: str = typer.Option("", "--reason"),
) -> None:
    """Enable or clear the paper kill switch."""
    if enable:
        state = enable_paper_kill_switch(project_root(), reason=reason, updated_by="cli")
    else:
        state = clear_paper_kill_switch(project_root(), reason=reason, updated_by="cli")
    path = write_paper_status(project_root())
    console.print(
        f"[green]paper kill switch[/green] {'enabled' if state.enabled else 'cleared'} "
        f"status={path}"
    )


@journal_app.command("add")
def journal_add(
    signal_id: str = typer.Option(..., "--signal"),
    action: str = typer.Option("watched", "--action"),
    notes: str = typer.Option("", "--notes"),
    outcome: str = typer.Option("", "--outcome"),
) -> None:
    """Add a manual journal entry linked to a signal."""
    find_signal(signal_id, project_root())
    entry = add_journal_entry(project_root(), signal_id, action, notes, outcome)
    console.print(f"[green]journal written[/green] {entry.id}")


def _resolve_output_path(root: Path, path: Path) -> Path:
    return path if path.is_absolute() else root / path


def _ensure_runtime_dirs(root: Path) -> None:
    ensure_runtime_dirs(root)


def _parse_datetime(value: str | None) -> datetime | None:
    if value is None:
        return None
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed


def _find_strategy_spec(strategy_name: str, root: Path) -> Path:
    candidates = [
        root / "strategy_specs" / "active" / f"{strategy_name}.yaml",
        root / "strategy_specs" / "approved" / f"{strategy_name}.yaml",
        root / "strategy_specs" / "drafts" / f"{strategy_name}.yaml",
        root / "strategy_specs" / "retired" / f"{strategy_name}.yaml",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise FileNotFoundError(f"StrategySpec not found for {strategy_name}")
