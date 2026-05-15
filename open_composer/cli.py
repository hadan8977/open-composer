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
from open_composer.adapters.data.longbridge import (
    DEFAULT_LONGBRIDGE_TRADE_SESSIONS,
    MAX_LONGBRIDGE_CANDLESTICKS,
    LongbridgeDataError,
    fetch_longbridge_bars,
    fetch_longbridge_quotes,
    longbridge_credentials_status,
    longbridge_quote_status,
)
from open_composer.adapters.events import fetch_capability_events
from open_composer.adapters.execution import build_nautilus_trader_plan, write_nautilus_trader_plan
from open_composer.agent_requests import (
    AgentRequestCreate,
    complete_agent_request,
    create_agent_request,
    list_agent_requests,
)
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
from open_composer.remote import RemoteJobManager, build_remote_doctor_report, serve_remote
from open_composer.remote.bootstrap import (
    VpsBootstrapError,
    apply_vps_bootstrap,
    build_vps_bootstrap_config,
    detect_public_ip,
    write_system_templates,
    write_vps_bootstrap_report,
)
from open_composer.remote.server import RemoteServerError
from open_composer.repo_check import build_repo_check_report, write_repo_check_report
from open_composer.research import (
    build_promotion_report,
    draft_strategy_from_idea,
    optimize_option_overlays,
    optimize_strategy,
    optimize_strategy_horizons,
    optimize_strategy_universe,
    parse_sweep_parameters,
    run_blind_test,
    run_cost_grid,
    run_exposure_switch_research,
    run_leverage_research,
    run_llm_exposure_switch_meta_selection,
    run_llm_rotation_meta_selection,
    run_market_timing_research,
    run_parameter_sweep,
    run_rotation_research,
    run_skill_attribution,
    search_similar_regimes,
)
from open_composer.research.llm_exposure_switch import LLMExposureSwitchChoice
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
repo_app = typer.Typer(no_args_is_help=True)
remote_app = typer.Typer(no_args_is_help=True)
agent_app = typer.Typer(no_args_is_help=True)
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
app.add_typer(repo_app, name="repo")
app.add_typer(remote_app, name="remote")
app.add_typer(agent_app, name="agent")


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
    table.add_row(
        "LONGBRIDGE_ACCESS_TOKEN",
        optional_env_status("LONGBRIDGE_ACCESS_TOKEN"),
        "required for Longbridge live API Key auth",
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


@repo_app.command("check")
def repo_check_command(
    strict: Annotated[
        bool,
        typer.Option("--strict", help="Exit with code 1 when repository checks are blocked."),
    ] = False,
    output: Annotated[
        Path | None,
        typer.Option("--output", help="Path for the repository check JSON report."),
    ] = None,
) -> None:
    """Check repository docs, control surface, and sample workflow anchors."""
    root = project_root()
    report = build_repo_check_report(root)
    json_path, md_path = write_repo_check_report(report, root, output)
    table = Table(title="Open Composer Repository Check")
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
    strict: Annotated[
        bool,
        typer.Option("--strict", help="Exit with code 1 when feature packets are incomplete."),
    ] = False,
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
    if strict and any(packet.point_in_time_status != "complete" for packet in packets):
        raise typer.Exit(1)


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
    table.add_row("Research reports", str(catalog.summary.research_report_count))
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
    output_path = output or root / "reports" / "dashboard" / "review.md"
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


@remote_app.command("serve")
def remote_serve_command(
    host: Annotated[
        str,
        typer.Option("--host", help="Host interface for the remote command daemon."),
    ] = "127.0.0.1",
    port: Annotated[
        int,
        typer.Option("--port", help="Port for the remote command daemon."),
    ] = 8787,
    shared_secret: Annotated[
        str | None,
        typer.Option(
            "--shared-secret",
            help="HMAC shared secret. Defaults to OC_REMOTE_SHARED_SECRET.",
        ),
    ] = None,
    allowed_actor: Annotated[
        str | None,
        typer.Option("--allowed-actor", help="Allowed HMAC actor. Defaults to OC_DASHBOARD_OWNER."),
    ] = None,
) -> None:
    """Serve the HMAC-protected remote Dashboard command daemon."""
    try:
        serve_remote(
            project_root(),
            host=host,
            port=port,
            shared_secret=shared_secret,
            allowed_actor=allowed_actor,
        )
    except RemoteServerError as exc:
        raise typer.BadParameter(str(exc)) from exc


@remote_app.command("job-list")
def remote_job_list_command() -> None:
    """List remote Dashboard command jobs."""
    manager = RemoteJobManager(project_root(), autostart=False)
    table = Table(title="Open Composer Remote Jobs")
    table.add_column("Job")
    table.add_column("Status")
    table.add_column("Action")
    table.add_column("Actor")
    table.add_column("Created")
    for job in manager.list_jobs():
        table.add_row(
            job.job_id,
            job.status,
            job.action,
            job.actor,
            job.created_at.isoformat(),
        )
    console.print(table)


@remote_app.command("job-status")
def remote_job_status_command(job_id: str) -> None:
    """Show a remote Dashboard command job record."""
    manager = RemoteJobManager(project_root(), autostart=False)
    try:
        job = manager.load_job(job_id)
    except Exception as exc:
        raise typer.BadParameter(str(exc)) from exc
    print(json.dumps(job.model_dump(mode="json"), indent=2, sort_keys=True))


@remote_app.command("doctor")
def remote_doctor_command(
    strict: Annotated[
        bool,
        typer.Option("--strict", help="Exit with code 1 when remote readiness is blocked."),
    ] = False,
) -> None:
    """Check local prerequisites for the remote Dashboard command daemon."""
    report = build_remote_doctor_report(project_root())
    table = Table(title="Open Composer Remote Doctor")
    table.add_column("Check")
    table.add_column("Status")
    table.add_column("Message")
    for check in report.checks:
        table.add_row(check.name, check.status, check.message)
    console.print(table)
    if strict and report.status == "blocked":
        raise typer.Exit(code=1)


@remote_app.command("bootstrap-vps")
def remote_bootstrap_vps_command(
    apply: Annotated[
        bool,
        typer.Option("--apply", help="Write files and run Vercel/system service commands."),
    ] = False,
    vercel_token: Annotated[
        str | None,
        typer.Option(
            "--vercel-token",
            envvar="VERCEL_TOKEN",
            help="Vercel API token. Defaults to VERCEL_TOKEN.",
        ),
    ] = None,
    vercel_project: Annotated[
        str,
        typer.Option("--vercel-project", help="Vercel project name for the Dashboard BFF."),
    ] = "open-composer-dashboard",
    vercel_scope: Annotated[
        str | None,
        typer.Option("--vercel-scope", help="Optional Vercel team/user scope."),
    ] = None,
    vercel_command: Annotated[
        str | None,
        typer.Option(
            "--vercel-command",
            help="Vercel command to run, e.g. 'vercel' or 'npx --yes vercel@latest'.",
        ),
    ] = None,
    daemon_url: Annotated[
        str | None,
        typer.Option("--daemon-url", help="Public HTTPS URL for the VPS remote daemon."),
    ] = None,
    public_ip: Annotated[
        str | None,
        typer.Option("--public-ip", help="VPS public IPv4; creates https://<ip>.sslip.io."),
    ] = None,
    detect_ip: Annotated[
        bool,
        typer.Option(
            "--detect-ip/--no-detect-ip",
            help="Detect public IPv4 during --apply when daemon URL is not provided.",
        ),
    ] = True,
    vercel_origin: Annotated[
        str | None,
        typer.Option(
            "--vercel-origin", help="Allowed browser origin; defaults to project.vercel.app."
        ),
    ] = None,
    dashboard_password: Annotated[
        str | None,
        typer.Option("--dashboard-password", help="Dashboard login password to hash."),
    ] = None,
    generate_password: Annotated[
        bool,
        typer.Option(
            "--generate-password/--no-generate-password",
            help="Generate a dashboard password when none exists.",
        ),
    ] = True,
    rotate_secrets: Annotated[
        bool,
        typer.Option(
            "--rotate-secrets", help="Generate new remote/session secrets and password hash."
        ),
    ] = False,
    owner: Annotated[
        str,
        typer.Option("--owner", help="Remote actor owner used in HMAC requests."),
    ] = "owner",
    skip_system: Annotated[
        bool,
        typer.Option("--skip-system", help="Do not install systemd or Caddy files."),
    ] = False,
    skip_vercel: Annotated[
        bool,
        typer.Option("--skip-vercel", help="Do not configure or deploy Vercel."),
    ] = False,
    skip_prepare: Annotated[
        bool,
        typer.Option("--skip-prepare", help="Do not run make deploy-prepare during apply."),
    ] = False,
    verify: Annotated[
        bool,
        typer.Option(
            "--verify/--no-verify",
            help="Run daemon, Vercel session, and BFF checks after apply.",
        ),
    ] = True,
    use_sudo: Annotated[
        bool,
        typer.Option("--sudo", help="Prefix systemctl commands with sudo."),
    ] = False,
) -> None:
    """Bootstrap Remote Dashboard from a VPS using Vercel as the password-session BFF."""
    resolved_public_ip = public_ip
    if apply and not daemon_url and not resolved_public_ip and detect_ip:
        resolved_public_ip = detect_public_ip()
    try:
        config = build_vps_bootstrap_config(
            project_root(),
            apply=apply,
            vercel_token=vercel_token,
            vercel_project=vercel_project,
            vercel_scope=vercel_scope,
            vercel_command=vercel_command,
            daemon_url=daemon_url,
            public_ip=resolved_public_ip,
            vercel_origin=vercel_origin,
            dashboard_password=dashboard_password,
            generate_password=generate_password,
            rotate_secrets=rotate_secrets,
            owner=owner,
            skip_system=skip_system,
            skip_vercel=skip_vercel,
            skip_prepare=skip_prepare,
            verify=verify,
            use_sudo=use_sudo,
        )
        if apply:
            plan = apply_vps_bootstrap(config)
        else:
            if config.daemon_url:
                write_system_templates(config)
            plan = config.plan
            write_vps_bootstrap_report(plan, config.root)
    except VpsBootstrapError as exc:
        raise typer.BadParameter(str(exc)) from exc

    table = Table(title="Open Composer VPS Bootstrap")
    table.add_column("Item")
    table.add_column("Value")
    table.add_row("Status", plan.status)
    table.add_row("Apply", str(plan.apply))
    table.add_row("Daemon URL", plan.daemon_url or "missing")
    table.add_row("Dashboard URL", plan.dashboard_url or plan.vercel_origin or "missing")
    table.add_row("Vercel origin", plan.vercel_origin or "missing")
    table.add_row("Vercel project", plan.vercel_project)
    table.add_row("Report", plan.report_markdown_path or "")
    if plan.deployment_url:
        table.add_row("Deployment URL", plan.deployment_url)
    if plan.generated_password_path:
        table.add_row("Password path", plan.generated_password_path)
    table.add_row("Verify", "enabled" if plan.verify_enabled else "skipped")
    console.print(table)
    if config.generated_dashboard_password and apply and plan.generated_password_path:
        console.print(
            "[yellow]generated dashboard password written to[/yellow] "
            f"{plan.generated_password_path}"
        )
    if not apply:
        console.print("[yellow]dry run only[/yellow] rerun with --apply to deploy.")
    if plan.status == "blocked":
        raise typer.Exit(code=1)


@agent_app.command("request-create")
def agent_request_create_command(
    title: Annotated[str, typer.Option("--title", help="Short request title.")],
    prompt: Annotated[str, typer.Option("--prompt", help="Task prompt for Codex or Claude Code.")],
    task_type: Annotated[
        str,
        typer.Option(
            "--task-type",
            help="research, review, parameter_scan, or strategy_optimization.",
        ),
    ] = "research",
    related_path: Annotated[
        list[str] | None,
        typer.Option("--related-path", help="Workspace-relative path to link to the request."),
    ] = None,
    requested_by: Annotated[
        str,
        typer.Option("--requested-by", help="Actor recorded on the request."),
    ] = "dashboard",
) -> None:
    """Create a file-backed agent request for Codex or Claude Code follow-up."""
    try:
        request = create_agent_request(
            AgentRequestCreate(
                requested_by=requested_by,
                task_type=task_type,  # type: ignore[arg-type]
                title=title,
                prompt=prompt,
                related_paths=related_path or [],
            ),
            project_root(),
        )
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    console.print(
        f"[green]agent request written[/green] reports/agent_requests/{request.request_id}.json"
    )


@agent_app.command("request-list")
def agent_request_list_command() -> None:
    """List file-backed agent requests."""
    table = Table(title="Open Composer Agent Requests")
    table.add_column("Request")
    table.add_column("Status")
    table.add_column("Type")
    table.add_column("Title")
    for request in list_agent_requests(project_root()):
        table.add_row(request.request_id, request.status, request.task_type, request.title)
    console.print(table)


@agent_app.command("request-complete")
def agent_request_complete_command(
    request_id: str,
    result_link: Annotated[
        list[str],
        typer.Option("--result-link", help="Workspace-relative result path to link."),
    ],
) -> None:
    """Mark an agent request completed and attach result links."""
    try:
        request = complete_agent_request(
            request_id,
            result_links=result_link,
            root=project_root(),
        )
    except (FileNotFoundError, ValueError) as exc:
        raise typer.BadParameter(str(exc)) from exc
    console.print(f"[green]agent request completed[/green] {request.request_id}")


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
    strict_live: bool = typer.Option(
        False,
        "--strict-live",
        help="Fail instead of falling back to local fixture/sample data.",
    ),
    count: int = typer.Option(
        MAX_LONGBRIDGE_CANDLESTICKS,
        "--count",
        help="Longbridge candlestick count when no start/end is supplied.",
    ),
    trade_sessions: str = typer.Option(
        DEFAULT_LONGBRIDGE_TRADE_SESSIONS,
        "--trade-sessions",
        help="Longbridge trade sessions: intraday or all.",
    ),
) -> None:
    """Fetch OHLCV bars into data/cache."""
    root = project_root()
    selected_symbol = symbol.upper()
    selected_start = _parse_datetime(start)
    selected_end = _parse_datetime(end)
    try:
        if strict_live and source == "longbridge":
            frame = fetch_longbridge_bars(
                root=root,
                symbol=selected_symbol,
                timeframe=timeframe,
                start=selected_start,
                end=selected_end,
                feed=feed,
                use_cache=False,
                count=count,
                trade_sessions=trade_sessions,
            )
        else:
            frame = fetch_ohlcv(
                root=root,
                symbol=selected_symbol,
                timeframe=timeframe,
                start=selected_start,
                end=selected_end,
                source=source,
                feed=feed,
                use_cache=not strict_live,
                allow_fallback=not strict_live,
            )
    except LongbridgeDataError as exc:
        console.print(f"[red]Longbridge fetch failed[/red] {exc}")
        raise typer.Exit(1) from exc
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


@data_app.command("longbridge-check")
def data_longbridge_check(
    symbol: str = typer.Option("QQQ", "--symbol"),
    timeframe: str = typer.Option("15m", "--timeframe"),
    count: int = typer.Option(5, "--count", min=1, max=MAX_LONGBRIDGE_CANDLESTICKS),
    trade_sessions: str = typer.Option(
        DEFAULT_LONGBRIDGE_TRADE_SESSIONS,
        "--trade-sessions",
        help="Longbridge trade sessions: intraday or all.",
    ),
) -> None:
    """Validate Longbridge credentials, quote permission, and live bars."""
    root = project_root()
    credentials = longbridge_credentials_status(root)
    table = Table(title="Longbridge Live Check")
    table.add_column("Check")
    table.add_column("Status")
    table.add_column("Detail")
    for name, status in credentials.items():
        table.add_row(name, status, "presence only")
    missing = [name for name, status in credentials.items() if status == "missing"]
    if missing:
        console.print(table)
        raise typer.Exit(1)

    try:
        status = longbridge_quote_status(root)
        quotes = fetch_longbridge_quotes(root, [symbol])
        bars = fetch_longbridge_bars(
            root=root,
            symbol=symbol.upper(),
            timeframe=timeframe,
            start=None,
            end=None,
            feed=None,
            use_cache=False,
            count=count,
            trade_sessions=trade_sessions,
        )
    except LongbridgeDataError as exc:
        table.add_row("Live API", "failed", str(exc))
        console.print(table)
        raise typer.Exit(1) from exc

    quote_packages = status.get("quote_packages", [])
    package_names = [
        str(item.get("name") or item.get("key"))
        for item in quote_packages
        if item.get("name") or item.get("key")
    ]
    latest = bars.iloc[-1] if not bars.empty else None
    latest_timestamp = latest["timestamp"].isoformat() if latest is not None else "n/a"
    table.add_row("Quote level", str(status.get("quote_level") or "unknown"), "")
    table.add_row(
        "Quote packages",
        str(len(package_names)),
        ", ".join(package_names[:5]) or "none reported",
    )
    table.add_row("Quote", "ok" if quotes else "empty", str(quotes[0]) if quotes else "n/a")
    table.add_row(
        "Candlesticks",
        "ok" if len(bars) else "empty",
        f"{len(bars)} bars latest={latest_timestamp}",
    )
    console.print(table)


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


@strategy_app.command("promotion-report")
def strategy_promotion_report(
    spec: Path,
    oos_ratio: Annotated[
        float,
        typer.Option("--oos-ratio", help="Out-of-sample trailing slice ratio."),
    ] = 0.3,
    walk_forward_folds: Annotated[
        int,
        typer.Option("--walk-forward-folds", help="Number of walk-forward slices."),
    ] = 3,
    cost_slippage_bps: Annotated[
        list[int] | None,
        typer.Option(
            "--cost-slippage-bps",
            help="Repeatable slippage scenarios for cost sensitivity.",
        ),
    ] = None,
) -> None:
    """Build a promotion gate report with OOS, walk-forward, and cost sensitivity evidence."""
    result = build_promotion_report(
        spec,
        project_root(),
        out_of_sample_ratio=oos_ratio,
        walk_forward_folds=walk_forward_folds,
        cost_slippage_bps=cost_slippage_bps,
    )
    table = Table(title=f"Promotion Report: {result.strategy_name}")
    table.add_column("Field")
    table.add_column("Value")
    table.add_row("Status", result.status)
    table.add_row("Ready", "yes" if result.ready else "no")
    table.add_row("Report", result.report_path)
    table.add_row("JSON", result.json_path)
    table.add_row("Checks", str(len(result.checks)))
    console.print(table)


@strategy_app.command("blind-test")
def strategy_blind_test(
    spec: Path,
    seed: int = typer.Option(42, "--seed", help="Deterministic remap seed."),
) -> None:
    """Run a BlindTrade-style counterfactual evaluation over remapped ticker identities."""
    report = run_blind_test(spec, project_root(), seed=seed)
    table = Table(title=f"Blind Test: {report.strategy_name}")
    for column in ("Mode", "Return %", "Sharpe", "Signals", "Corr w/ real"):
        table.add_column(column)
    for result in report.results:
        table.add_row(
            result.mode,
            f"{result.return_pct:.2f}",
            f"{result.sharpe:.2f}",
            str(result.signal_count),
            f"{result.correlation_with_real:.2f}"
            if result.correlation_with_real is not None
            else "n/a",
        )
    console.print(table)
    console.print(f"interpretation: {report.interpretation}")


@strategy_app.command("cost-grid")
def strategy_cost_grid(
    spec: Path,
    commission: Annotated[list[float] | None, typer.Option("--commission")] = None,
    slippage: Annotated[list[float] | None, typer.Option("--slippage")] = None,
    impact_model: Annotated[list[str] | None, typer.Option("--impact-model")] = None,
) -> None:
    """Run a cost sensitivity grid across commission, slippage, and impact model."""
    report = run_cost_grid(
        spec,
        commission_grid=commission or [0.0, 0.01],
        slippage_grid=slippage or [0.0, 5.0, 10.0],
        impact_models=impact_model or ["linear", "sqrt", "almgren_chriss"],
        root=project_root(),
    )
    table = Table(title=f"Cost Grid: {report.strategy_name}")
    for column in ("Commission %", "Slippage bps", "Impact", "Return %", "Sharpe"):
        table.add_column(column)
    for result in report.results:
        table.add_row(
            f"{result.commission_pct:.4f}",
            f"{result.slippage_bps:.1f}",
            result.impact_model,
            f"{result.return_pct:.2f}",
            f"{result.sharpe:.2f}",
        )
    console.print(table)
    console.print(f"spread={report.ranking_spread:.2f} warning={report.warning}")


@strategy_app.command("regime-search")
def strategy_regime_search(
    spec: Path,
    top_k: int = typer.Option(5, "--top-k"),
    lookback_months: int = typer.Option(6, "--lookback-months"),
) -> None:
    """Search historical macro/news regimes similar to the latest available window."""
    report = search_similar_regimes(
        spec,
        root=project_root(),
        top_k=top_k,
        lookback_months=lookback_months,
    )
    table = Table(title=f"Regime Search: {report.strategy_name}")
    for column in ("Window", "Similarity", "Macro", "News", "Note"):
        table.add_column(column)
    for match in report.matches:
        table.add_row(
            match.window_end,
            f"{match.similarity:.3f}",
            str(match.macro_count),
            str(match.news_count),
            match.market_note,
        )
    console.print(table)


@strategy_app.command("skill-attribution")
def strategy_skill_attribution(
    sample_size: int = typer.Option(20, "--sample-size"),
) -> None:
    """Estimate offline contribution of repo skills using recent promotion reports."""
    report = run_skill_attribution(project_root(), sample_size=sample_size)
    table = Table(title="Skill Attribution")
    for column in ("Skill", "Shapley", "Tokens", "Value/token", "Recommendation"):
        table.add_column(column)
    for row in report.rows:
        table.add_row(
            row.skill_name,
            f"{row.shapley_value:.4f}",
            str(row.avg_token_cost_per_invocation),
            f"{row.contribution_per_token:.6f}",
            row.recommendation,
        )
    console.print(table)


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


@strategy_app.command("rotate-universe")
def strategy_rotate_universe(
    spec: Path,
    symbols: str = typer.Option(..., "--symbols"),
    data_source: str = typer.Option("alpaca", "--data-source"),
    start: str | None = typer.Option(None, "--start"),
    end: str | None = typer.Option(None, "--end"),
    objective: str = typer.Option(
        "equal-weight-alpha",
        "--objective",
        help="Selection objective: equal-weight-alpha or primary-alpha.",
    ),
    lookback: Annotated[list[int] | None, typer.Option("--lookback")] = None,
    rebalance_bars: Annotated[
        list[int] | None,
        typer.Option("--rebalance-bars"),
    ] = None,
    top_n: Annotated[list[int] | None, typer.Option("--top-n")] = None,
    min_momentum_pct: Annotated[
        list[float] | None,
        typer.Option("--min-momentum-pct"),
    ] = None,
    primary_hold_margin_pct: Annotated[
        list[float] | None,
        typer.Option("--primary-hold-margin-pct"),
    ] = None,
    primary_min_momentum_pct: Annotated[
        list[float] | None,
        typer.Option("--primary-min-momentum-pct"),
    ] = None,
    oos_ratio: float = typer.Option(0.3, "--oos-ratio"),
    walk_forward_folds: int = typer.Option(3, "--walk-forward-folds"),
    walk_forward_top_k: int | None = typer.Option(
        None,
        "--walk-forward-top-k",
        help="Only re-score the top K training candidates inside walk-forward folds.",
    ),
    max_candidates: int = typer.Option(200, "--max-candidates"),
    refresh_data: bool = typer.Option(False, "--refresh-data/--use-cache"),
    feature_gate: bool = typer.Option(
        False,
        "--feature-gate",
        help="Apply replayable point-in-time llm_feature/feature_packet entry gates.",
    ),
) -> None:
    """Research a point-in-time momentum rotation grid across a symbol universe."""
    if data_source not in {"alpaca", "longbridge"}:
        raise typer.BadParameter("--data-source currently supports alpaca or longbridge")
    objective_key = _rotation_objective(objective)
    result = run_rotation_research(
        spec,
        project_root(),
        symbols=[item.strip().upper() for item in symbols.split(",") if item.strip()],
        data_source=data_source,
        lookback_bars=lookback,
        rebalance_bars=rebalance_bars,
        top_n_values=top_n,
        min_momentum_pct=min_momentum_pct,
        out_of_sample_ratio=oos_ratio,
        walk_forward_folds=walk_forward_folds,
        max_candidates=max_candidates,
        refresh_data=refresh_data,
        feature_gate=feature_gate,
        start=start,
        end=end,
        objective=objective_key,
        primary_hold_margin_pct=primary_hold_margin_pct,
        primary_min_momentum_pct=primary_min_momentum_pct,
        walk_forward_top_k=walk_forward_top_k,
    )
    best = result.best
    console.print(f"[green]rotation research complete[/green] report: {result.report_path}")
    console.print(
        f"best={best.params.label} "
        f"train_primary_alpha={best.train.alpha_vs_primary_pct:.2f}% "
        f"oos_primary_alpha={best.out_of_sample.alpha_vs_primary_pct:.2f}% "
        f"oos_equal_weight_alpha={best.out_of_sample.alpha_vs_equal_weight_pct:.2f}% "
        f"oos_sharpe={best.out_of_sample.sharpe_ratio or 0.0:.2f} "
        f"flags={','.join(best.quality_flags) if best.quality_flags else 'none'}"
    )
    console.print(
        f"candidates={result.research_cost['candidate_count']} "
        f"walk_forward_candidates={result.research_cost['walk_forward_candidate_count']} "
        f"estimated_passes={result.research_cost['estimated_total_backtest_passes']} "
        f"runtime={result.runtime_seconds['total']:.2f}s"
    )


@strategy_app.command("llm-rotate-universe")
def strategy_llm_rotate_universe(
    spec: Path,
    symbols: str = typer.Option(..., "--symbols"),
    data_source: str = typer.Option("alpaca", "--data-source"),
    start: str | None = typer.Option(None, "--start"),
    end: str | None = typer.Option(None, "--end"),
    objective: str = typer.Option(
        "equal-weight-alpha",
        "--objective",
        help="Selection objective: equal-weight-alpha or primary-alpha.",
    ),
    lookback: Annotated[list[int] | None, typer.Option("--lookback")] = None,
    rebalance_bars: Annotated[
        list[int] | None,
        typer.Option("--rebalance-bars"),
    ] = None,
    top_n: Annotated[list[int] | None, typer.Option("--top-n")] = None,
    min_momentum_pct: Annotated[
        list[float] | None,
        typer.Option("--min-momentum-pct"),
    ] = None,
    validation_ratio: float = typer.Option(0.3, "--validation-ratio"),
    validation_folds: int = typer.Option(3, "--validation-folds"),
    oos_ratio: float = typer.Option(0.3, "--oos-ratio"),
    max_candidates: int = typer.Option(200, "--max-candidates"),
    refresh_data: bool = typer.Option(False, "--refresh-data/--use-cache"),
) -> None:
    """Use an LLM to select a rotation method from training-only evidence, then validate OOS."""
    if data_source not in {"alpaca", "longbridge"}:
        raise typer.BadParameter("--data-source currently supports alpaca or longbridge")
    objective_key = _rotation_objective(objective)
    result = run_llm_rotation_meta_selection(
        spec,
        project_root(),
        symbols=[item.strip().upper() for item in symbols.split(",") if item.strip()],
        data_source=data_source,
        lookback_bars=lookback,
        rebalance_bars=rebalance_bars,
        top_n_values=top_n,
        min_momentum_pct=min_momentum_pct,
        validation_ratio=validation_ratio,
        validation_folds=validation_folds,
        out_of_sample_ratio=oos_ratio,
        max_candidates=max_candidates,
        refresh_data=refresh_data,
        start=start,
        end=end,
        objective=objective_key,
    )
    selected = result.selected
    console.print(f"[green]LLM rotation selection complete[/green] report: {result.report_path}")
    console.print(
        f"selected={selected.params.label} "
        f"oos_primary_alpha={selected.out_of_sample.alpha_vs_primary_pct:.2f}% "
        f"oos_equal_weight_alpha={selected.out_of_sample.alpha_vs_equal_weight_pct:.2f}% "
        f"oos_sharpe={selected.out_of_sample.sharpe_ratio or 0.0:.2f} "
        f"status={result.status} "
        f"flags={','.join(selected.quality_flags) if selected.quality_flags else 'none'}"
    )


def _rotation_objective(value: str) -> str:
    normalized = value.strip().lower().replace("_", "-")
    if normalized == "equal-weight-alpha":
        return "equal_weight_alpha"
    if normalized == "primary-alpha":
        return "primary_alpha"
    raise typer.BadParameter("--objective must be equal-weight-alpha or primary-alpha")


@strategy_app.command("market-time")
def strategy_market_time(
    spec: Path,
    symbol: str | None = typer.Option(None, "--symbol"),
    data_source: str = typer.Option("alpaca", "--data-source"),
    start: str | None = typer.Option(None, "--start"),
    end: str | None = typer.Option(None, "--end"),
    profile: Annotated[list[str] | None, typer.Option("--profile")] = None,
    fast: Annotated[list[int] | None, typer.Option("--fast")] = None,
    slow: Annotated[list[int] | None, typer.Option("--slow")] = None,
    exit_bars: Annotated[list[int] | None, typer.Option("--exit-bars")] = None,
    momentum_bars: Annotated[list[int] | None, typer.Option("--momentum-bars")] = None,
    min_momentum_pct: Annotated[
        list[float] | None,
        typer.Option("--min-momentum-pct"),
    ] = None,
    breakout_bars: Annotated[list[int] | None, typer.Option("--breakout-bars")] = None,
    volume_bars: Annotated[list[int] | None, typer.Option("--volume-bars")] = None,
    stop_loss_pct: Annotated[list[float] | None, typer.Option("--stop-loss-pct")] = None,
    take_profit_pct: Annotated[
        list[str] | None,
        typer.Option("--take-profit-pct"),
    ] = None,
    oos_ratio: float = typer.Option(0.3, "--oos-ratio"),
    walk_forward_folds: int = typer.Option(3, "--walk-forward-folds"),
    walk_forward_top_k: int | None = typer.Option(
        None,
        "--walk-forward-top-k",
        help="Only re-score the top K training candidates inside walk-forward folds.",
    ),
    max_candidates: int = typer.Option(300, "--max-candidates"),
    refresh_data: bool = typer.Option(False, "--refresh-data/--use-cache"),
    write_best_spec: bool = typer.Option(True, "--write-best-spec/--no-write-best-spec"),
) -> None:
    """Research same-symbol timing grids against buy-and-hold."""
    if data_source not in {"alpaca", "longbridge"}:
        raise typer.BadParameter("--data-source currently supports alpaca or longbridge")
    result = run_market_timing_research(
        spec,
        project_root(),
        symbol=symbol,
        data_source=data_source,
        profiles=_timing_profiles(profile),
        fast_bars=fast,
        slow_bars=slow,
        exit_bars=exit_bars,
        momentum_bars=momentum_bars,
        min_momentum_pct=min_momentum_pct,
        breakout_bars=breakout_bars,
        volume_bars=volume_bars,
        stop_loss_pct=stop_loss_pct,
        take_profit_pct=_take_profit_values(take_profit_pct),
        out_of_sample_ratio=oos_ratio,
        walk_forward_folds=walk_forward_folds,
        max_candidates=max_candidates,
        refresh_data=refresh_data,
        start=start,
        end=end,
        write_best_spec=write_best_spec,
        walk_forward_top_k=walk_forward_top_k,
    )
    best = result.best
    run = best.out_of_sample.run
    console.print(f"[green]market timing research complete[/green] report: {result.report_path}")
    if result.selected_spec_path:
        console.print(f"selected spec: {result.selected_spec_path}")
    console.print(
        f"best={best.params.label} "
        f"oos_alpha={run.alpha_vs_buy_hold_pct or 0.0:.2f}% "
        f"oos_return={run.total_return_pct:.2f}% "
        f"oos_buy_hold={run.buy_hold_return_pct or 0.0:.2f}% "
        f"oos_sharpe={run.sharpe_ratio or 0.0:.2f} "
        f"flags={','.join(best.quality_flags) if best.quality_flags else 'none'}"
    )
    console.print(
        f"candidates={result.research_cost['candidate_count']} "
        f"walk_forward_candidates={result.research_cost['walk_forward_candidate_count']} "
        f"estimated_passes={result.research_cost['estimated_total_backtest_passes']} "
        f"runtime={result.runtime_seconds['total']:.2f}s"
    )


def _timing_profiles(values: list[str] | None) -> list[str] | None:
    if values is None:
        return None
    allowed = {"risk_control_hold", "trend_pullback", "breakout_hold", "macd_trend"}
    normalized = [item.strip().lower().replace("-", "_") for item in values if item.strip()]
    unknown = sorted(set(normalized) - allowed)
    if unknown:
        raise typer.BadParameter(f"unsupported --profile values: {', '.join(unknown)}")
    return normalized


def _take_profit_values(values: list[str] | None) -> list[float | None] | None:
    if values is None:
        return None
    parsed: list[float | None] = []
    for value in values:
        normalized = value.strip().lower()
        if normalized in {"none", "null", "off"}:
            parsed.append(None)
        else:
            parsed.append(float(value))
    return parsed


@strategy_app.command("leverage-research")
def strategy_leverage_research(
    spec: Path,
    symbol: str | None = typer.Option(None, "--symbol"),
    data_source: str = typer.Option("alpaca", "--data-source"),
    start: str | None = typer.Option(None, "--start"),
    end: str | None = typer.Option(None, "--end"),
    leverage: Annotated[list[float] | None, typer.Option("--leverage")] = None,
    financing_rate_pct: Annotated[
        list[float] | None,
        typer.Option("--financing-rate-pct"),
    ] = None,
    oos_ratio: float = typer.Option(0.3, "--oos-ratio"),
    walk_forward_folds: int = typer.Option(3, "--walk-forward-folds"),
    max_candidates: int = typer.Option(100, "--max-candidates"),
    refresh_data: bool = typer.Option(False, "--refresh-data/--use-cache"),
) -> None:
    """Research levered same-symbol exposure against unlevered buy-and-hold."""
    if data_source not in {"alpaca", "longbridge"}:
        raise typer.BadParameter("--data-source currently supports alpaca or longbridge")
    result = run_leverage_research(
        spec,
        project_root(),
        symbol=symbol,
        data_source=data_source,
        leverage_values=leverage,
        financing_rate_pct=financing_rate_pct,
        out_of_sample_ratio=oos_ratio,
        walk_forward_folds=walk_forward_folds,
        max_candidates=max_candidates,
        refresh_data=refresh_data,
        start=start,
        end=end,
    )
    best = result.best
    console.print(f"[green]leverage research complete[/green] report: {result.report_path}")
    console.print(
        f"best={best.params.label} "
        f"oos_alpha={best.out_of_sample.alpha_vs_buy_hold_pct:.2f}% "
        f"oos_return={best.out_of_sample.total_return_pct:.2f}% "
        f"oos_buy_hold={best.out_of_sample.buy_hold_return_pct:.2f}% "
        f"oos_sharpe={best.out_of_sample.sharpe_ratio or 0.0:.2f} "
        f"flags={','.join(best.quality_flags) if best.quality_flags else 'none'}"
    )


@strategy_app.command("exposure-switch")
def strategy_exposure_switch(
    spec: Path,
    symbol: str | None = typer.Option(None, "--symbol"),
    data_source: str = typer.Option("alpaca", "--data-source"),
    start: str | None = typer.Option(None, "--start"),
    end: str | None = typer.Option(None, "--end"),
    fast: Annotated[list[int] | None, typer.Option("--fast")] = None,
    slow: Annotated[list[int] | None, typer.Option("--slow")] = None,
    momentum_bars: Annotated[list[int] | None, typer.Option("--momentum-bars")] = None,
    min_momentum_pct: Annotated[
        list[float] | None,
        typer.Option("--min-momentum-pct"),
    ] = None,
    volatility_bars: Annotated[list[int] | None, typer.Option("--volatility-bars")] = None,
    max_volatility_pct: Annotated[
        list[str] | None,
        typer.Option("--max-volatility-pct"),
    ] = None,
    drawdown_bars: Annotated[list[int] | None, typer.Option("--drawdown-bars")] = None,
    max_drawdown_pct: Annotated[
        list[str] | None,
        typer.Option("--max-drawdown-pct"),
    ] = None,
    base_exposure: Annotated[list[float] | None, typer.Option("--base-exposure")] = None,
    risk_on_exposure: Annotated[list[float] | None, typer.Option("--risk-on-exposure")] = None,
    risk_off_exposure: Annotated[
        list[float] | None,
        typer.Option("--risk-off-exposure"),
    ] = None,
    financing_rate_pct: Annotated[
        list[float] | None,
        typer.Option("--financing-rate-pct"),
    ] = None,
    oos_ratio: float = typer.Option(0.3, "--oos-ratio"),
    walk_forward_folds: int = typer.Option(3, "--walk-forward-folds"),
    walk_forward_top_k: int | None = typer.Option(
        None,
        "--walk-forward-top-k",
        help="Only re-score the top K training candidates inside walk-forward folds.",
    ),
    max_candidates: int = typer.Option(200, "--max-candidates"),
    refresh_data: bool = typer.Option(False, "--refresh-data/--use-cache"),
) -> None:
    """Research point-in-time dynamic exposure switching against buy-and-hold."""
    if data_source not in {"alpaca", "longbridge"}:
        raise typer.BadParameter("--data-source currently supports alpaca or longbridge")
    result = run_exposure_switch_research(
        spec,
        project_root(),
        symbol=symbol,
        data_source=data_source,
        fast_bars=fast,
        slow_bars=slow,
        momentum_bars=momentum_bars,
        min_momentum_pct=min_momentum_pct,
        volatility_bars=volatility_bars,
        max_volatility_pct=_optional_float_values(max_volatility_pct),
        drawdown_bars=drawdown_bars,
        max_drawdown_pct=_optional_float_values(max_drawdown_pct),
        base_exposure=base_exposure,
        risk_on_exposure=risk_on_exposure,
        risk_off_exposure=risk_off_exposure,
        financing_rate_pct=financing_rate_pct,
        out_of_sample_ratio=oos_ratio,
        walk_forward_folds=walk_forward_folds,
        walk_forward_top_k=walk_forward_top_k,
        max_candidates=max_candidates,
        refresh_data=refresh_data,
        start=start,
        end=end,
    )
    best = result.best
    console.print(f"[green]exposure switch research complete[/green] report: {result.report_path}")
    console.print(
        f"best={best.params.label} "
        f"oos_alpha={best.out_of_sample.alpha_vs_buy_hold_pct:.2f}% "
        f"oos_return={best.out_of_sample.total_return_pct:.2f}% "
        f"oos_buy_hold={best.out_of_sample.buy_hold_return_pct:.2f}% "
        f"oos_sharpe={best.out_of_sample.sharpe_ratio or 0.0:.2f} "
        f"flags={','.join(best.quality_flags) if best.quality_flags else 'none'}"
    )
    console.print(
        f"candidates={result.research_cost.candidate_count} "
        f"walk_forward_candidates={result.research_cost.walk_forward_candidate_count} "
        f"estimated_passes={result.research_cost.estimated_total_backtest_passes} "
        f"runtime={result.runtime_seconds['total']:.2f}s"
    )


@strategy_app.command("llm-exposure-switch")
def strategy_llm_exposure_switch(
    spec: Path,
    symbol: str | None = typer.Option(None, "--symbol"),
    data_source: str = typer.Option("alpaca", "--data-source"),
    start: str | None = typer.Option(None, "--start"),
    end: str | None = typer.Option(None, "--end"),
    fast: Annotated[list[int] | None, typer.Option("--fast")] = None,
    slow: Annotated[list[int] | None, typer.Option("--slow")] = None,
    momentum_bars: Annotated[list[int] | None, typer.Option("--momentum-bars")] = None,
    min_momentum_pct: Annotated[
        list[float] | None,
        typer.Option("--min-momentum-pct"),
    ] = None,
    volatility_bars: Annotated[list[int] | None, typer.Option("--volatility-bars")] = None,
    max_volatility_pct: Annotated[
        list[str] | None,
        typer.Option("--max-volatility-pct"),
    ] = None,
    drawdown_bars: Annotated[list[int] | None, typer.Option("--drawdown-bars")] = None,
    max_drawdown_pct: Annotated[
        list[str] | None,
        typer.Option("--max-drawdown-pct"),
    ] = None,
    base_exposure: Annotated[list[float] | None, typer.Option("--base-exposure")] = None,
    risk_on_exposure: Annotated[list[float] | None, typer.Option("--risk-on-exposure")] = None,
    risk_off_exposure: Annotated[
        list[float] | None,
        typer.Option("--risk-off-exposure"),
    ] = None,
    financing_rate_pct: Annotated[
        list[float] | None,
        typer.Option("--financing-rate-pct"),
    ] = None,
    validation_ratio: float = typer.Option(0.3, "--validation-ratio"),
    validation_folds: int = typer.Option(3, "--validation-folds"),
    oos_ratio: float = typer.Option(0.3, "--oos-ratio"),
    max_candidates: int = typer.Option(200, "--max-candidates"),
    refresh_data: bool = typer.Option(False, "--refresh-data/--use-cache"),
    local_choice_label: str | None = typer.Option(
        None,
        "--local-choice-label",
        help="Use a local Codex/operator choice from the prompt artifact instead of an API call.",
    ),
    local_choice_rationale: str = typer.Option(
        "Local Codex/operator selected from training-only prompt evidence.",
        "--local-choice-rationale",
    ),
) -> None:
    """Use an LLM to select an exposure switch from training-only evidence."""
    if data_source not in {"alpaca", "longbridge"}:
        raise typer.BadParameter("--data-source currently supports alpaca or longbridge")
    result = run_llm_exposure_switch_meta_selection(
        spec,
        project_root(),
        symbol=symbol,
        data_source=data_source,
        fast_bars=fast,
        slow_bars=slow,
        momentum_bars=momentum_bars,
        min_momentum_pct=min_momentum_pct,
        volatility_bars=volatility_bars,
        max_volatility_pct=_optional_float_values(max_volatility_pct),
        drawdown_bars=drawdown_bars,
        max_drawdown_pct=_optional_float_values(max_drawdown_pct),
        base_exposure=base_exposure,
        risk_on_exposure=risk_on_exposure,
        risk_off_exposure=risk_off_exposure,
        financing_rate_pct=financing_rate_pct,
        validation_ratio=validation_ratio,
        validation_folds=validation_folds,
        out_of_sample_ratio=oos_ratio,
        max_candidates=max_candidates,
        refresh_data=refresh_data,
        local_choice=_local_exposure_choice(local_choice_label, local_choice_rationale),
        start=start,
        end=end,
    )
    selected = result.selected
    console.print(
        f"[green]LLM exposure switch selection complete[/green] report: {result.report_path}"
    )
    console.print(
        f"selected={selected.params.label} "
        f"oos_alpha={selected.out_of_sample.alpha_vs_buy_hold_pct:.2f}% "
        f"oos_return={selected.out_of_sample.total_return_pct:.2f}% "
        f"oos_buy_hold={selected.out_of_sample.buy_hold_return_pct:.2f}% "
        f"oos_sharpe={selected.out_of_sample.sharpe_ratio or 0.0:.2f} "
        f"status={result.status} "
        f"flags={','.join(selected.quality_flags) if selected.quality_flags else 'none'}"
    )


def _local_exposure_choice(
    label: str | None,
    rationale: str,
) -> LLMExposureSwitchChoice | None:
    if label is None:
        return None
    return LLMExposureSwitchChoice(
        selected_label=label,
        confidence=0.5,
        rationale=rationale,
        expected_risks=[
            "Local choice is based only on prompt artifact evidence and must still pass OOS gates."
        ],
        rejected_labels=[],
    )


def _optional_float_values(values: list[str] | None) -> list[float | None] | None:
    if values is None:
        return None
    parsed: list[float | None] = []
    for value in values:
        normalized = value.strip().lower()
        if normalized in {"none", "null", "off"}:
            parsed.append(None)
        else:
            parsed.append(float(value))
    return parsed


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
