from __future__ import annotations

import importlib.util
import json
import os
import sys
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any, get_args

import typer
import yaml
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
from open_composer.adapters.execution.adaptive_intraday_target_weights import (
    run_adaptive_intraday_target_weight_mapping,
)
from open_composer.adapters.execution.beta_target_weights import run_beta_target_weight_mapping
from open_composer.adapters.execution.core_beta_satellite_target_weights import (
    run_core_beta_satellite_target_weight_mapping,
)
from open_composer.adapters.execution.hybrid_target_weights import (
    run_hybrid_target_weight_mapping,
)
from open_composer.cache import (
    build_cache_inventory,
    clean_cache_targets,
    resolve_clean_target_keys,
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
from open_composer.dashboard.vps_deploy import (
    VpsDashboardDeployError,
    apply_vps_dashboard_deploy,
    build_vps_dashboard_deploy_config,
    write_vps_dashboard_deploy_report,
)
from open_composer.dashboard.vps_deploy import (
    detect_public_ip as detect_dashboard_public_ip,
)
from open_composer.dashboard.vps_deploy import (
    write_system_templates as write_dashboard_system_templates,
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
from open_composer.models.notification import NotificationKind, NotificationSeverity
from open_composer.models.project import StrategyProjectCreate, StrategyProjectRun
from open_composer.models.strategy_spec import load_strategy_spec
from open_composer.notifications import (
    notification_config_status,
    read_notification_log,
    send_test_notification,
)
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
from open_composer.paper_validation import write_paper_validation_report
from open_composer.projects import (
    create_project,
    list_projects,
    load_project,
    load_project_run_summary,
    update_gate_state,
    update_project_state,
)
from open_composer.readiness import build_readiness_report, write_readiness_report
from open_composer.repo_check import build_repo_check_report, write_repo_check_report
from open_composer.research import (
    build_alternative_data_evidence,
    build_geometry_feature_report,
    build_hybrid_paper_plan,
    build_options_overlay_report,
    build_options_research_report,
    build_overfit_risk_report,
    build_promotion_report,
    build_short_risk_report,
    build_strategy_evidence,
    draft_strategy_from_idea_with_status,
    optimize_option_overlays,
    optimize_strategy,
    optimize_strategy_horizons,
    optimize_strategy_universe,
    parse_sweep_parameters,
    run_adaptive_intraday_router_research,
    run_adaptive_intraday_router_scan,
    run_aggressive_theme_router_research,
    run_beta_exposure_router_research,
    run_blind_test,
    run_core_beta_satellite_router_research,
    run_core_satellite_router_research,
    run_cost_grid,
    run_exposure_switch_research,
    run_factor_lab,
    run_hybrid_adaptive_router_research,
    run_hybrid_factor_attribution,
    run_hybrid_news_marginal_lift_research,
    run_intraday_daily_rotation_research,
    run_leverage_research,
    run_llm_adaptive_intraday_router_selection,
    run_llm_exposure_switch_meta_selection,
    run_llm_intraday_daily_rotation_selection,
    run_llm_rotation_meta_selection,
    run_market_timing_research,
    run_parameter_sweep,
    run_rotation_research,
    run_skill_attribution,
    run_theme_intraday_rotation_router_research,
    run_universe_audit,
    run_wide_router_research,
    search_similar_regimes,
    sweep_parameters_from_spec,
    update_research_control,
    validate_strategy_dag,
    write_intraday_product_reflection,
    write_strategy_dag_validation,
)
from open_composer.research.llm_exposure_switch import LLMExposureSwitchChoice
from open_composer.research.pdr_attribution import (
    DEFAULT_DATE_TAG as PDR_ATTRIBUTION_DEFAULT_DATE_TAG,
)
from open_composer.research.pdr_attribution import (
    DEFAULT_END as PDR_ATTRIBUTION_DEFAULT_END,
)
from open_composer.research.pdr_attribution import (
    DEFAULT_OUT_DIR as PDR_ATTRIBUTION_DEFAULT_OUT_DIR,
)
from open_composer.research.pdr_attribution import (
    DEFAULT_SPEC_PATH as PDR_ATTRIBUTION_DEFAULT_SPEC_PATH,
)
from open_composer.research.pdr_attribution import (
    DEFAULT_START as PDR_ATTRIBUTION_DEFAULT_START,
)
from open_composer.research.pdr_attribution import (
    parse_fold_windows,
    run_pdr_router_attribution,
)
from open_composer.research.pdr_ml_gate_evaluation import (
    DEFAULT_END as PDR_ML_GATE_DEFAULT_END,
)
from open_composer.research.pdr_ml_gate_evaluation import (
    DEFAULT_START as PDR_ML_GATE_DEFAULT_START,
)
from open_composer.research.pdr_ml_gate_evaluation import (
    evaluate_pdr_router_ml_gate,
)
from open_composer.research.research_brief import init_research_brief, validate_research_brief
from open_composer.research.research_cache_manifest import (
    DEFAULT_RESEARCH_CACHE_DIR,
    verify_longbridge_research_cache_manifest,
)
from open_composer.research.route_cross_source import (
    DEFAULT_ALT_DIR as ROUTE_CROSS_SOURCE_DEFAULT_ALT_DIR,
)
from open_composer.research.route_cross_source import (
    DEFAULT_ALT_FEED as ROUTE_CROSS_SOURCE_DEFAULT_ALT_FEED,
)
from open_composer.research.route_cross_source import (
    DEFAULT_ALT_SOURCE as ROUTE_CROSS_SOURCE_DEFAULT_ALT_SOURCE,
)
from open_composer.research.route_cross_source import (
    DEFAULT_END as ROUTE_CROSS_SOURCE_DEFAULT_END,
)
from open_composer.research.route_cross_source import (
    DEFAULT_OUT_DIR as ROUTE_CROSS_SOURCE_DEFAULT_OUT_DIR,
)
from open_composer.research.route_cross_source import (
    DEFAULT_REPORT_DATE as ROUTE_CROSS_SOURCE_DEFAULT_REPORT_DATE,
)
from open_composer.research.route_cross_source import (
    DEFAULT_SPEC_PATH as ROUTE_CROSS_SOURCE_DEFAULT_SPEC_PATH,
)
from open_composer.research.route_cross_source import (
    DEFAULT_START as ROUTE_CROSS_SOURCE_DEFAULT_START,
)
from open_composer.research.route_cross_source import (
    evaluate_route_cross_source_validation,
    materialize_alt_daily_source,
)
from open_composer.research.router_replay_audit import (
    DEFAULT_AUDIT_DATE as ROUTER_REPLAY_AUDIT_DEFAULT_DATE,
)
from open_composer.research.router_replay_audit import (
    DEFAULT_BASELINE as ROUTER_REPLAY_AUDIT_DEFAULT_BASELINE,
)
from open_composer.research.router_replay_audit import (
    DEFAULT_OUT_DIR as ROUTER_REPLAY_AUDIT_DEFAULT_OUT_DIR,
)
from open_composer.research.router_replay_audit import (
    run_router_replay_audit,
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
repo_app = typer.Typer(no_args_is_help=True)
notify_app = typer.Typer(no_args_is_help=True)
cache_app = typer.Typer(no_args_is_help=True)
harness_app = typer.Typer(no_args_is_help=True)
project_app = typer.Typer(no_args_is_help=True)
agent_app = typer.Typer(no_args_is_help=True)
research_brief_app = typer.Typer(no_args_is_help=True)
factor_app = typer.Typer(no_args_is_help=True)
research_app = typer.Typer(no_args_is_help=True)
research_iteration_app = typer.Typer(no_args_is_help=True)
console = Console()
PDR_ML_GATE_DEFAULT_SPEC_PATH = Path(
    "strategy_specs/drafts/nasdaq_tqqq_pdr_router_mlgate_iter1.yaml"
)

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
strategy_app.add_typer(research_brief_app, name="research-brief")
app.add_typer(run_app, name="run")
app.add_typer(options_app, name="options")
app.add_typer(feature_app, name="feature")
app.add_typer(deploy_app, name="deploy")
app.add_typer(dashboard_app, name="dashboard")
app.add_typer(repo_app, name="repo")
app.add_typer(notify_app, name="notify")
app.add_typer(cache_app, name="cache")
app.add_typer(harness_app, name="harness")
app.add_typer(project_app, name="project")
app.add_typer(agent_app, name="agent")
app.add_typer(factor_app, name="factor")
app.add_typer(research_app, name="research")
research_app.add_typer(research_iteration_app, name="iteration")


@app.callback()
def _load_env() -> None:
    root = project_root()
    load_dotenv(root / ".env")


@factor_app.command("list")
def factor_list_command(
    family: Annotated[str | None, typer.Option("--family")] = None,
    inputs: Annotated[
        str | None, typer.Option("--inputs", help="Comma-separated OHLCV inputs")
    ] = None,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """List factor catalog entries."""
    from open_composer.research.factor_library import list_factors

    inputs_set = {item.strip() for item in inputs.split(",") if item.strip()} if inputs else None
    factors = list_factors(family=family, inputs=inputs_set)
    if json_output:
        sys.stdout.write(json.dumps([asdict(factor) for factor in factors], indent=2) + "\n")
        return
    table = Table(title=f"Factor Catalog ({len(factors)} factors)")
    table.add_column("id")
    table.add_column("family")
    table.add_column("inputs")
    table.add_column("expression")
    table.add_column("label")
    for factor in factors:
        table.add_row(
            factor.id,
            factor.family,
            ",".join(factor.inputs),
            "yes" if factor.expression else "no",
            factor.label,
        )
    console.print(table)


@factor_app.command("show")
def factor_show_command(factor_id: str) -> None:
    """Show one factor definition."""
    from open_composer.research.factor_library import get_factor, materialize_expression

    try:
        factor = get_factor(factor_id)
    except KeyError as exc:
        raise typer.BadParameter(str(exc)) from exc
    console.print(f"[bold]{factor.id}[/bold] - {factor.label}")
    console.print(f"family: {factor.family}")
    console.print(f"inputs: {', '.join(factor.inputs)}")
    console.print(f"output: {factor.output}")
    console.print(f"\n[bold]description[/bold]\n{factor.description}")
    if factor.expression:
        console.print(f"\n[bold]expression (defaults)[/bold]\n{materialize_expression(factor, {})}")
    else:
        console.print("\n[yellow]no expression template[/yellow]")
    if factor.default_parameter_space:
        console.print("\n[bold]parameter space[/bold]")
        for key, value in factor.default_parameter_space.items():
            console.print(f"- {key}: {value}")
    if factor.source_card_ids:
        console.print("\n[bold]source cards[/bold]")
        for source_card_id in factor.source_card_ids:
            console.print(f"- {source_card_id}")
    lineage_path = project_root() / "reports" / "factors" / factor.id / "lineage.json"
    if lineage_path.exists():
        payload = json.loads(lineage_path.read_text(encoding="utf-8"))
        used = payload.get("used_in_specs", [])
        if isinstance(used, list) and used:
            console.print(f"\n[bold]used in specs[/bold] ({len(used)})")
            for item in used[:10]:
                if isinstance(item, dict):
                    console.print(f"- {item.get('spec_path')}")


@factor_app.command("use-in")
def factor_use_in_command(
    spec_path: Path,
    factor_id: str,
    name: Annotated[str, typer.Option("--name", help="Factor key to add to the spec")] = "",
    params: Annotated[
        str | None, typer.Option("--params", help="Comma-separated k=v pairs")
    ] = None,
) -> None:
    """Add a catalog factor to a StrategySpec in place."""
    from open_composer.models.strategy_spec import load_strategy_spec
    from open_composer.research.factor_library import get_factor
    from open_composer.research.factor_lineage import append_lineage

    try:
        factor = get_factor(factor_id)
    except KeyError as exc:
        raise typer.BadParameter(str(exc)) from exc
    if not factor.expression:
        raise typer.BadParameter(f"factor {factor_id} has no expression template")
    params_dict = _parse_kv_pairs(params or "")
    raw = yaml.safe_load(spec_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise typer.BadParameter(f"{spec_path} must contain a YAML mapping")
    factor_name = name or factor.id
    raw.setdefault("factors", {})
    if not isinstance(raw["factors"], dict):
        raise typer.BadParameter("spec factors field must be a mapping")
    raw["factors"][factor_name] = {
        "source": "factor_library",
        "factor_id": factor.id,
        "params": params_dict,
    }
    spec_path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
    try:
        load_strategy_spec(spec_path)
    except Exception as exc:
        raise typer.BadParameter(f"updated spec failed validation: {exc}") from exc
    lineage = append_lineage(factor.id, spec_path, added_by="cli", root=project_root())
    console.print(f"[green]factor added[/green] {factor.id} -> {spec_path} as {factor_name}")
    console.print(f"lineage: {lineage}")


@factor_app.command("catalog-status")
def factor_catalog_status_command(
    strict: Annotated[bool, typer.Option("--strict")] = False,
) -> None:
    """Validate catalog expression templates and parameter defaults."""
    from open_composer.expressions import ExpressionSafetyError, assert_expression_safe
    from open_composer.research.factor_library import ALL_FACTORS, materialize_expression

    errors: list[str] = []
    warnings: list[str] = []
    for factor in ALL_FACTORS:
        if not factor.expression:
            warnings.append(f"{factor.id}: no expression template")
            continue
        try:
            rendered = materialize_expression(factor, {})
            assert_expression_safe(rendered)
        except (ValueError, ExpressionSafetyError) as exc:
            errors.append(f"{factor.id}: {exc}")
    console.print(f"catalog size: {len(ALL_FACTORS)}")
    console.print(f"expressionable: {len([factor for factor in ALL_FACTORS if factor.expression])}")
    console.print(f"errors: {len(errors)}")
    console.print(f"warnings: {len(warnings)}")
    for error in errors:
        console.print(f"[red]error[/red] {error}")
    for warning in warnings:
        console.print(f"[yellow]warning[/yellow] {warning}")
    if strict and errors:
        raise typer.Exit(1)


@factor_app.command("decay-monitor")
def factor_decay_monitor_command(
    factor_id: Annotated[str | None, typer.Option("--factor-id")] = None,
    active_only: Annotated[
        bool,
        typer.Option("--active-only", help="Only monitor factors used by active specs."),
    ] = False,
    no_notify: Annotated[
        bool,
        typer.Option("--no-notify", help="Do not dispatch decay alert notifications."),
    ] = False,
) -> None:
    """Run one factor decay-monitor cycle."""
    from open_composer.research.factor_decay import (
        monitor_all_active_factors,
        monitor_factor_decay,
    )

    try:
        if factor_id:
            results = [
                monitor_factor_decay(
                    factor_id,
                    root=project_root(),
                    dispatch_alert=not no_notify,
                )
            ]
        else:
            results = monitor_all_active_factors(
                project_root(),
                active_only=active_only,
                dispatch_alert=not no_notify,
            )
    except (FileNotFoundError, ValueError) as exc:
        raise typer.BadParameter(str(exc)) from exc
    table = Table(title=f"Factor Decay Monitor ({len(results)} factors)")
    table.add_column("factor")
    table.add_column("status")
    table.add_column("3m IC", justify="right")
    table.add_column("12m IR", justify="right")
    table.add_column("alert")
    for row in results:
        status = str(row.get("status", "unknown"))
        alert = "yes" if row.get("decay_alert") else "no"
        table.add_row(
            str(row.get("factor_id", "n/a")),
            status,
            _fmt_optional(row.get("rolling_3m_rank_ic")),
            _fmt_optional(row.get("rolling_12m_ir")),
            alert,
        )
    console.print(table)
    console.print("artifacts: reports/factors/*/decay-monitor.jsonl")


@factor_app.command("decay-report")
def factor_decay_report_command(
    days: Annotated[int, typer.Option("--days", help="Lookback window in calendar days.")] = 90,
) -> None:
    """Show recent factor decay-monitor history."""
    from open_composer.research.factor_decay import build_decay_report

    rows = build_decay_report(project_root(), days=days)
    table = Table(title=f"Factor Decay Report ({days} days)")
    table.add_column("factor")
    table.add_column("checks", justify="right")
    table.add_column("alerts", justify="right")
    table.add_column("latest 3m IC", justify="right")
    table.add_column("latest 12m IR", justify="right")
    table.add_column("recommendation")
    for row in rows:
        table.add_row(
            str(row.get("factor_id", "n/a")),
            str(row.get("checks", 0)),
            str(row.get("alerts", 0)),
            _fmt_optional(row.get("latest_3m_rank_ic")),
            _fmt_optional(row.get("latest_12m_ir")),
            str(row.get("recommendation", "unknown")),
        )
    console.print(table)


@factor_app.command("retire")
def factor_retire_command(
    factor_id: str,
    reason: Annotated[str, typer.Option("--reason")] = "",
) -> None:
    """Mark a factor lineage artifact as retired."""
    from open_composer.research.factor_decay import retire_factor

    try:
        payload = retire_factor(factor_id, reason=reason, root=project_root())
    except FileNotFoundError as exc:
        raise typer.BadParameter(str(exc)) from exc
    console.print(f"[yellow]factor retired[/yellow] {factor_id}")
    used = payload.get("used_in_specs", [])
    if isinstance(used, list) and used:
        console.print("affected specs:")
        for item in used:
            if isinstance(item, dict):
                console.print(f"  - {item.get('spec_path')}")


@factor_app.command("propose")
def factor_propose_command(
    thesis: str,
    base_factors: Annotated[
        list[str] | None,
        typer.Option("--base-factor", help="Catalog factor id used for correlation screening."),
    ] = None,
    max_candidates: Annotated[int, typer.Option("--max-candidates")] = 5,
    data_path: Annotated[str, typer.Option("--data-path")] = "data/sample/syn_daily.csv",
    min_abs_rank_ic: Annotated[float, typer.Option("--min-abs-rank-ic")] = 0.01,
    min_abs_ir: Annotated[float, typer.Option("--min-abs-ir")] = 0.0,
    max_abs_correlation: Annotated[float, typer.Option("--max-abs-correlation")] = 0.70,
    use_llm: Annotated[bool, typer.Option("--llm/--no-llm")] = False,
) -> None:
    """Propose research-only factor expressions without mutating the catalog."""
    from open_composer.research.factor_propose import propose_factors

    try:
        payload = propose_factors(
            thesis,
            root=project_root(),
            data_path=data_path,
            base_factors=base_factors or [],
            max_candidates=max_candidates,
            min_abs_rank_ic=min_abs_rank_ic,
            min_abs_ir=min_abs_ir,
            max_abs_correlation=max_abs_correlation,
            use_llm=use_llm,
        )
    except (FileNotFoundError, ValueError) as exc:
        raise typer.BadParameter(str(exc)) from exc
    console.print(
        f"[green]factor proposal written[/green] {payload['proposal_id']} "
        f"status={payload['status']} pending={payload['pending_candidate_count']}"
    )
    console.print(f"json: {payload['path']}")


@factor_app.command("approve")
def factor_approve_command(
    proposal_id: str,
    reason: Annotated[str, typer.Option("--reason")] = "",
) -> None:
    """Approve a factor proposal artifact without editing factor_library.py."""
    from open_composer.research.factor_propose import approve_factor_proposal

    try:
        payload = approve_factor_proposal(proposal_id, root=project_root(), reason=reason)
    except (FileNotFoundError, ValueError) as exc:
        raise typer.BadParameter(str(exc)) from exc
    console.print(f"[green]factor proposal approved[/green] {proposal_id}")
    console.print(f"json: {payload['path']}")


@factor_app.command("reject")
def factor_reject_command(
    proposal_id: str,
    reason: Annotated[str, typer.Option("--reason")] = "",
) -> None:
    """Reject a factor proposal artifact without deleting evidence."""
    from open_composer.research.factor_propose import reject_factor_proposal

    try:
        payload = reject_factor_proposal(proposal_id, root=project_root(), reason=reason)
    except (FileNotFoundError, ValueError) as exc:
        raise typer.BadParameter(str(exc)) from exc
    console.print(f"[yellow]factor proposal rejected[/yellow] {proposal_id}")
    console.print(f"json: {payload['path']}")


@research_app.command("auto")
def research_auto_command(
    thesis: str,
    universe: Annotated[str, typer.Option("--universe")] = "QQQ",
    timeframe: Annotated[str, typer.Option("--timeframe")] = "daily",
    data_source: Annotated[str, typer.Option("--data-source")] = "alpaca",
    data_path: Annotated[str | None, typer.Option("--data-path")] = None,
    max_factors: Annotated[int, typer.Option("--max-factors")] = 5,
    use_llm: Annotated[bool, typer.Option("--use-llm/--no-llm")] = False,
    refresh_data: Annotated[bool, typer.Option("--refresh-data/--use-cache")] = False,
    zero_cost_smoke: Annotated[bool, typer.Option("--zero-cost-smoke")] = False,
    model: Annotated[str | None, typer.Option("--model")] = None,
) -> None:
    """Run thesis -> catalog factors -> IC -> draft spec -> evidence."""
    from open_composer.research.auto_research import run_auto_research

    universe_list = [item.strip().upper() for item in universe.split(",") if item.strip()]
    try:
        result = run_auto_research(
            thesis,
            universe_list,
            timeframe=timeframe,
            data_source=data_source,
            data_path=data_path,
            max_factors=max_factors,
            use_llm=use_llm,
            refresh_data=refresh_data,
            zero_cost_smoke=zero_cost_smoke,
            model_kind=model,
        )
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    console.print(f"[green]auto research complete[/green] {result.run_id}")
    console.print(f"selected factors: {', '.join(result.selected_factors) or 'none'}")
    console.print(f"spec: {result.spec_path}")
    console.print(f"evidence status: {result.evidence_status}")
    if result.fallback_message:
        console.print(f"[yellow]{result.fallback_message}[/yellow]")
    if result.blockers:
        console.print("blockers: " + "; ".join(result.blockers))
    console.print(f"report: {result.report_path}")


@research_app.command("compare")
def research_compare_command() -> None:
    """Aggregate ic_scores.json across all auto research runs."""
    from open_composer.research.auto_compare import write_cross_thesis_compare

    json_path, md_path = write_cross_thesis_compare(project_root())
    console.print("[green]cross-thesis compare written[/green]")
    console.print(f"json: {json_path}")
    console.print(f"markdown: {md_path}")


@research_app.command("mom-minute-r1")
def research_mom_minute_r1_command(
    report_date: Annotated[str | None, typer.Option("--report-date")] = None,
    smoke: Annotated[
        bool,
        typer.Option("--smoke", help="Run a two-trial smoke matrix for tests."),
    ] = False,
) -> None:
    """Run the bounded Step 9.4 mom_minute_r1 research matrix."""
    from open_composer.research.mom_minute_round import run_mom_minute_round

    kwargs: dict[str, Any] = {}
    if smoke:
        kwargs = {
            "p1_timeframes": ["30m"],
            "p1_lookbacks": [3],
            "p1_exit_styles": ["ema_cross"],
            "p3_timeframes": ["30m"],
            "p3_overnight_thresholds_pct": [0.0],
            "p3_intraday_confirms": ["none"],
        }
    result = run_mom_minute_round(project_root(), report_date=report_date, **kwargs)
    console.print("[green]mom_minute_r1 evaluation written[/green]")
    console.print(f"json: {result.evaluation_json_path}")
    console.print(f"markdown: {result.evaluation_markdown_path}")
    console.print(f"trial ledger: {result.trial_ledger_path}")
    console.print(f"forensics: {result.forensics_markdown_path}")


@research_app.command("mom-minute-r2")
def research_mom_minute_r2_command(
    report_date: Annotated[str | None, typer.Option("--report-date")] = None,
) -> None:
    """Run the fixed Step 9.R development/validation/lockbox round."""
    from open_composer.research.mom_minute_lockbox import run_mom_minute_lockbox

    result = run_mom_minute_lockbox(project_root(), report_date=report_date)
    console.print(f"[green]mom_minute_r2 verdict[/green] {result.payload['verdict']}")
    console.print(f"json: {result.evaluation_json_path}")
    console.print(f"markdown: {result.evaluation_markdown_path}")
    console.print(f"trial ledger: {result.trial_ledger_path}")


@research_iteration_app.command("init")
def research_iteration_init_command(
    iter_id: str,
    overwrite: Annotated[bool, typer.Option("--overwrite")] = False,
) -> None:
    """Create a research iteration dossier skeleton."""
    from open_composer.research.iteration_dossier import init_iteration_dossier

    try:
        paths = init_iteration_dossier(iter_id, project_root(), overwrite=overwrite)
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    console.print(f"[green]iteration dossier initialized[/green] {iter_id}")
    console.print(f"root: {paths.root}")
    console.print(f"external brief: {paths.external_brief_json}")
    console.print(f"decision record: {paths.decision_record_md}")


@research_iteration_app.command("validate")
def research_iteration_validate_command(
    iter_id: str,
    json_output: Annotated[bool, typer.Option("--json")] = False,
    stage: Annotated[
        str,
        typer.Option(
            "--stage",
            help="Validation stage: pre-backtest or final.",
        ),
    ] = "pre-backtest",
) -> None:
    """Validate a research iteration dossier before optimization."""
    from open_composer.research.iteration_dossier import (
        render_validation_markdown,
        validate_iteration_dossier,
    )

    try:
        result = validate_iteration_dossier(iter_id, project_root(), stage=stage)
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    if json_output:
        sys.stdout.write(json.dumps(result.to_dict(project_root()), indent=2) + "\n")
    else:
        console.print(render_validation_markdown(result))
    if not result.ok:
        raise typer.Exit(1)


def _parse_kv_pairs(raw: str) -> dict[str, Any]:
    result: dict[str, Any] = {}
    if not raw.strip():
        return result
    for item in raw.split(","):
        if "=" not in item:
            raise typer.BadParameter(f"parameter must use k=v syntax: {item}")
        key, value = item.split("=", 1)
        key = key.strip()
        if not key:
            raise typer.BadParameter("parameter key cannot be empty")
        result[key] = _parse_scalar(value.strip())
    return result


def _csv_list(raw: str | None) -> list[str] | None:
    if raw is None:
        return None
    return [item.strip() for item in raw.split(",") if item.strip()]


def _csv_upper(raw: str | None) -> list[str] | None:
    values = _csv_list(raw)
    if values is None:
        return None
    return [item.upper() for item in values]


def _parse_scalar(raw: str) -> Any:
    lowered = raw.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    if lowered in {"none", "null"}:
        return None
    try:
        return int(raw)
    except ValueError:
        pass
    try:
        return float(raw)
    except ValueError:
        return raw
    extra_env = os.getenv("OC_EXTRA_ENV_FILE")
    if extra_env:
        load_dotenv(Path(extra_env).expanduser(), override=False)


@app.command()
def doctor(
    plain: Annotated[
        bool,
        typer.Option(
            "--plain",
            help="Emit grep-friendly NAME\\tSTATUS\\tDETAIL lines instead of a Rich table.",
        ),
    ] = False,
) -> None:
    """Check local Open Composer environment status.

    Use --plain for shell-parseable output (one row per line, tab-separated).
    """
    root = project_root()
    _ensure_runtime_dirs(root)
    sample_path = root / "data" / "sample" / "qqq_15m.csv"
    rows: list[tuple[str, str, str]] = [("Python", "ok", sys.version.split()[0])]
    for package in ["pydantic", "pandas", "numpy", "yaml", "typer", "rich"]:
        status = "ok" if importlib.util.find_spec(package) else "missing"
        rows.append((f"Package {package}", status, ""))
    rows.append(("Sample data", "ok" if sample_path.exists() else "missing", str(sample_path)))
    rows.extend(
        [
            (
                "OPENAI_API_KEY",
                optional_env_status("OPENAI_API_KEY"),
                "optional for review cards; presence only",
            ),
            (
                "OPENAI_BASE_URL",
                openai_base_url_source(),
                openai_base_url() or "optional OpenAI-compatible gateway",
            ),
            ("OPENAI_MODEL", default_openai_model(), "default review model"),
            (
                "ALPACA_API_KEY_ID",
                optional_env_status("ALPACA_API_KEY_ID"),
                "optional for Alpaca",
            ),
            (
                "ALPACA_API_SECRET_KEY",
                optional_env_status("ALPACA_API_SECRET_KEY"),
                "optional for Alpaca",
            ),
            ("ALPACA_PAPER", os.getenv("ALPACA_PAPER", "true"), "must remain true for orders"),
            ("ALPACA_API_BASE_URL", alpaca_api_base_url(), "paper trading endpoint"),
            ("ALPACA_DATA_FEED", data_feed(), "default feed"),
            (
                "OPEN_COMPOSER_DASHBOARD_TOKEN",
                optional_env_status("OPEN_COMPOSER_DASHBOARD_TOKEN"),
                "optional token for dashboard API",
            ),
            (
                "ALPHA_VANTAGE_API_KEY",
                optional_env_status("ALPHA_VANTAGE_API_KEY"),
                "optional news",
            ),
            ("FRED_API_KEY", optional_env_status("FRED_API_KEY"), "optional macro"),
            (
                "LONGBRIDGE_APP_KEY",
                optional_env_status("LONGBRIDGE_APP_KEY"),
                "optional for Longbridge",
            ),
            (
                "LONGBRIDGE_APP_SECRET",
                optional_env_status("LONGBRIDGE_APP_SECRET"),
                "optional for Longbridge",
            ),
            (
                "LONGBRIDGE_ACCESS_TOKEN",
                optional_env_status("LONGBRIDGE_ACCESS_TOKEN"),
                "required for Longbridge live API Key auth",
            ),
        ]
    )
    if plain:
        for name, status, detail in rows:
            sys.stdout.write(f"{name}\t{status}\t{detail}\n")
        return
    table = Table(title="Open Composer Doctor")
    table.add_column("Check")
    table.add_column("Status")
    table.add_column("Detail")
    for name, status, detail in rows:
        table.add_row(name, status, detail)
    console.print(table)


@cache_app.command("status")
def cache_status_command(
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Print machine-readable cache inventory."),
    ] = False,
) -> None:
    """Show local dependency, cache, and runtime artifact sizes."""
    root = project_root()
    inventory = build_cache_inventory(root)
    payload = {
        "root": str(root),
        "targets": [item.to_dict() for item in inventory],
    }
    if json_output:
        sys.stdout.write(json.dumps(payload, indent=2) + "\n")
        return

    table = Table(title="Open Composer Cache Status")
    table.add_column("Target")
    table.add_column("Path")
    table.add_column("Size")
    table.add_column("Files")
    table.add_column("Cleanable")
    table.add_column("Protected")
    table.add_column("Note")
    for item in inventory:
        data = item.to_dict()
        cleanable = data["cleanable_size"] if data["cleanable"] else "status only"
        table.add_row(
            data["label"],
            data["path"],
            data["size"],
            str(data["file_count"]),
            cleanable,
            str(data["protected_files"]),
            data["note"],
        )
    console.print(table)


@cache_app.command("clean")
def cache_clean_command(
    data_cache: Annotated[
        bool,
        typer.Option("--data-cache", help="Select data/cache."),
    ] = False,
    reports: Annotated[
        bool,
        typer.Option("--reports", help="Select generated reports."),
    ] = False,
    signal_logs: Annotated[
        bool,
        typer.Option("--signal-logs", help="Select signal_logs."),
    ] = False,
    feature_logs: Annotated[
        bool,
        typer.Option("--feature-logs", help="Select feature_logs."),
    ] = False,
    event_logs: Annotated[
        bool,
        typer.Option("--event-logs", help="Select event_logs."),
    ] = False,
    all_runtime: Annotated[
        bool,
        typer.Option("--all-runtime", help="Select all cleanable runtime targets."),
    ] = False,
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run/--apply",
            help="Preview by default; pass --apply to delete selected artifacts.",
        ),
    ] = True,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Print machine-readable clean result."),
    ] = False,
) -> None:
    """Preview or clean ignored local cache and runtime artifacts."""
    root = project_root()
    selected = resolve_clean_target_keys(
        data_cache=data_cache,
        reports=reports,
        signal_logs=signal_logs,
        feature_logs=feature_logs,
        event_logs=event_logs,
        all_runtime=all_runtime,
    )
    try:
        result = clean_cache_targets(root, selected, dry_run=dry_run)
    except (FileNotFoundError, ValueError) as exc:
        raise typer.BadParameter(str(exc)) from exc

    payload = result.to_dict()
    payload["root"] = str(root)
    payload["selected"] = list(selected)
    if json_output:
        sys.stdout.write(json.dumps(payload, indent=2) + "\n")
        return

    table = Table(title=f"Open Composer Cache Clean ({'dry run' if dry_run else 'applied'})")
    table.add_column("Target")
    table.add_column("Files")
    table.add_column("Dirs")
    table.add_column("Size")
    table.add_column("Protected")
    for item in result.targets:
        table.add_row(
            item.path,
            str(item.files),
            str(item.dirs),
            item.to_dict()["size"],
            str(item.protected_files),
        )
    console.print(table)
    if dry_run:
        console.print("dry_run=yes; pass --apply to delete selected artifacts")
    else:
        console.print("dry_run=no; selected unprotected artifacts were removed")


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


@feature_app.command("materialize")
def feature_materialize_command(
    spec: Path,
    factor: Annotated[
        str | None,
        typer.Option("--factor", help="Single llm_feature factor; omit for all."),
    ] = None,
    symbols: Annotated[
        str | None,
        typer.Option("--symbols", help="Optional comma-separated symbol subset to materialize."),
    ] = None,
    backend: Annotated[
        str,
        typer.Option("--backend", help="openai or local_test_stub."),
    ] = "openai",
    refresh: Annotated[
        bool,
        typer.Option("--refresh", help="Ignore cache and recompute feature packets."),
    ] = False,
    window_bars: Annotated[
        int | None,
        typer.Option(
            "--window-bars",
            help="Materialize only the latest N bars; omit for full history.",
        ),
    ] = None,
) -> None:
    """Materialize llm_feature factors into PIT replay packets."""
    from open_composer.research.llm_materialize import materialize_factor

    root = project_root()
    spec_obj = load_strategy_spec(spec)
    targets = (
        [factor]
        if factor
        else [name for name, config in spec_obj.factors.items() if config.source == "llm_feature"]
    )
    selected_symbols = (
        [item.strip().upper() for item in symbols.split(",") if item.strip()] if symbols else None
    )
    if not targets:
        raise typer.BadParameter("spec has no source=llm_feature factors")
    for name in targets:
        result = materialize_factor(
            spec,
            name,
            root=root,
            backend=backend,
            refresh=refresh,
            symbols=selected_symbols,
            window_bars=window_bars,
        )
        console.print(
            f"[green]{name}[/green] packets={result.packet_count} "
            f"hits={result.cache_hits} misses={result.cache_misses} "
            f"errors={result.errors} path={result.packets_path.relative_to(root)}"
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


@dashboard_app.command("deploy-vps")
def dashboard_deploy_vps_command(
    apply: Annotated[
        bool,
        typer.Option("--apply", help="Write files and start the VPS Dashboard service."),
    ] = False,
    dashboard_url: Annotated[
        str | None,
        typer.Option("--dashboard-url", help="Public HTTPS URL for the VPS Dashboard."),
    ] = None,
    public_ip: Annotated[
        str | None,
        typer.Option("--public-ip", help="VPS public IPv4; creates https://<ip>.nip.io."),
    ] = None,
    cloudflare_access: Annotated[
        bool,
        typer.Option(
            "--cloudflare-access",
            help="Use Cloudflare Tunnel + Access; install systemd only and skip Caddy.",
        ),
    ] = False,
    cloudflare_team_domain: Annotated[
        str | None,
        typer.Option(
            "--cloudflare-team-domain",
            envvar="OC_CLOUDFLARE_ACCESS_TEAM_DOMAIN",
            help="Cloudflare Access team domain, e.g. https://team.cloudflareaccess.com.",
        ),
    ] = None,
    cloudflare_aud: Annotated[
        str | None,
        typer.Option(
            "--cloudflare-aud",
            envvar="OC_CLOUDFLARE_ACCESS_AUD",
            help="Cloudflare Access application AUD tag.",
        ),
    ] = None,
    allowed_emails: Annotated[
        str | None,
        typer.Option(
            "--allowed-emails",
            envvar="OC_DASHBOARD_ALLOWED_EMAILS",
            help="Comma-separated Dashboard email allowlist for Cloudflare Access.",
        ),
    ] = None,
    detect_ip: Annotated[
        bool,
        typer.Option(
            "--detect-ip/--no-detect-ip",
            help="Detect public IPv4 during --apply when Dashboard URL is not provided.",
        ),
    ] = True,
    dashboard_token: Annotated[
        str | None,
        typer.Option(
            "--dashboard-token",
            envvar="OPEN_COMPOSER_DASHBOARD_TOKEN",
            help="Dashboard API token. Defaults to OPEN_COMPOSER_DASHBOARD_TOKEN.",
        ),
    ] = None,
    rotate_token: Annotated[
        bool,
        typer.Option("--rotate-token", help="Generate a new Dashboard API token."),
    ] = False,
    dashboard_host: Annotated[
        str,
        typer.Option("--host", help="Local host interface for the Dashboard service."),
    ] = "127.0.0.1",
    dashboard_port: Annotated[
        int,
        typer.Option("--port", help="Local port for the Dashboard service."),
    ] = 8000,
    skip_system: Annotated[
        bool,
        typer.Option("--skip-system", help="Do not install systemd or Caddy files."),
    ] = False,
    skip_prepare: Annotated[
        bool,
        typer.Option("--skip-prepare", help="Do not run deployment prepare/build during apply."),
    ] = False,
    verify: Annotated[
        bool,
        typer.Option("--verify/--no-verify", help="Run Dashboard health check after apply."),
    ] = True,
    use_sudo: Annotated[
        bool,
        typer.Option("--sudo", help="Prefix systemctl/install commands with sudo."),
    ] = False,
) -> None:
    """Deploy the canonical VPS-hosted Dashboard without Vercel."""
    resolved_public_ip = public_ip
    if apply and not dashboard_url and not resolved_public_ip and detect_ip:
        resolved_public_ip = detect_dashboard_public_ip()
    try:
        config = build_vps_dashboard_deploy_config(
            project_root(),
            apply=apply,
            remote_access_mode="cloudflare_tunnel" if cloudflare_access else "token_caddy",
            dashboard_auth_mode="cloudflare_access" if cloudflare_access else None,
            dashboard_url=dashboard_url,
            public_ip=resolved_public_ip,
            cloudflare_access_team_domain=cloudflare_team_domain,
            cloudflare_access_audience=cloudflare_aud,
            dashboard_allowed_emails=allowed_emails,
            dashboard_token=dashboard_token,
            rotate_token=rotate_token,
            dashboard_host=dashboard_host,
            dashboard_port=dashboard_port,
            skip_system=skip_system,
            skip_prepare=skip_prepare,
            verify=verify,
            use_sudo=use_sudo,
        )
        if apply:
            plan = apply_vps_dashboard_deploy(config)
        else:
            if config.dashboard_url:
                write_dashboard_system_templates(config)
            plan = config.plan
            write_vps_dashboard_deploy_report(plan, config.root)
    except VpsDashboardDeployError as exc:
        raise typer.BadParameter(str(exc)) from exc

    table = Table(title="Open Composer VPS Dashboard Deploy")
    table.add_column("Item")
    table.add_column("Value")
    table.add_row("Status", plan.status)
    table.add_row("Apply", str(plan.apply))
    table.add_row("Mode", plan.mode)
    table.add_row("Remote access", plan.remote_access_mode)
    table.add_row("Dashboard URL", plan.dashboard_url or "missing")
    table.add_row("Dashboard bind", plan.dashboard_bind)
    table.add_row("Report", plan.report_markdown_path or "")
    if plan.generated_token_path:
        table.add_row("Token path", plan.generated_token_path)
    table.add_row("Verify", "enabled" if plan.verify_enabled else "skipped")
    console.print(table)
    if config.generated_dashboard_token and apply and plan.generated_token_path:
        console.print(
            f"[yellow]generated Dashboard token written to[/yellow] {plan.generated_token_path}"
        )
    if not apply:
        console.print("[yellow]dry run only[/yellow] rerun with --apply to deploy.")
    if plan.status == "blocked":
        raise typer.Exit(code=1)


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


@project_app.command("create")
def project_create_command(
    name: Annotated[str, typer.Option("--name", help="StrategyProject display name.")],
    thesis: Annotated[str, typer.Option("--thesis", help="User-facing strategy thesis.")],
    idea: Annotated[str, typer.Option("--idea", help="Natural-language build request.")],
    template_id: Annotated[str | None, typer.Option("--template-id")] = None,
    max_rounds: Annotated[int, typer.Option("--max-rounds")] = 5,
    requested_by: Annotated[str, typer.Option("--requested-by")] = "cli",
    use_llm: Annotated[bool, typer.Option("--use-llm/--no-llm")] = False,
) -> None:
    """Create a lightweight StrategyProject."""
    try:
        project, command = create_project(
            StrategyProjectCreate(
                name=name,
                thesis=thesis,
                idea=idea,
                template_id=template_id,
                max_rounds=max_rounds,
                requested_by=requested_by,
                use_llm=use_llm,
            ),
            project_root(),
        )
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    console.print(f"[green]project written[/green] projects/{project.project_id}/project.yaml")
    console.print(f"context: projects/{project.project_id}/context.md")
    if command:
        console.print(f"queue_command: {command.id}")


@project_app.command("list")
def project_list_command() -> None:
    """List StrategyProject records."""
    table = Table(title="Open Composer Strategy Projects")
    table.add_column("Project")
    table.add_column("State")
    table.add_column("Round")
    table.add_column("Spec")
    table.add_column("Next action")
    for project in list_projects(project_root()):
        table.add_row(
            project.project_id,
            project.state,
            f"{project.iteration.current_round}/{project.iteration.max_rounds}",
            project.current_spec_path or "",
            project.next_action,
        )
    console.print(table)


@project_app.command("state")
def project_state_command(
    project_id: str,
    state: Annotated[str, typer.Option("--state", help="New project state.")],
    next_action: Annotated[str | None, typer.Option("--next-action")] = None,
) -> None:
    """Update lightweight StrategyProject state."""
    try:
        project = update_project_state(
            project_id,
            state,  # type: ignore[arg-type]
            project_root(),
            next_action=next_action,
        )
    except (FileNotFoundError, ValueError) as exc:
        raise typer.BadParameter(str(exc)) from exc
    console.print(f"[green]project updated[/green] {project.project_id} state={project.state}")


@project_app.command("gate-state")
def project_gate_state_command(
    project_id: str,
    gate: Annotated[str, typer.Option("--gate", help="Gate name, e.g. research_pass.")],
    status: Annotated[str, typer.Option("--status", help="Gate status/value.")],
    reason: Annotated[
        list[str] | None,
        typer.Option("--reason", help="Repeatable reason recorded in gate_summary and trace."),
    ] = None,
) -> None:
    """Update project gate_summary through the single gate-state writer."""
    try:
        project = update_gate_state(
            project_id,
            gate,
            _parse_gate_status(status),
            project_root(),
            reasons=reason or [],
            agent="cli",
        )
    except (FileNotFoundError, ValueError) as exc:
        raise typer.BadParameter(str(exc)) from exc
    console.print(
        f"[green]gate updated[/green] {project.project_id} {gate}={project.gate_summary.get(gate)}"
    )


@project_app.command("show")
def project_show_command(project_id: str) -> None:
    """Show a StrategyProject as JSON."""
    try:
        project = load_project(project_id, project_root())
    except FileNotFoundError as exc:
        raise typer.BadParameter(str(exc)) from exc
    print(json.dumps(project.model_dump(mode="json"), indent=2, sort_keys=True))


@project_app.command("run-append")
def project_run_append_command(
    project_id: str,
    round_number: Annotated[
        int | None, typer.Option("--round", help="Iteration round number.")
    ] = None,
    status: Annotated[
        str,
        typer.Option("--status", help="ok, warning, blocked, or failed."),
    ] = "warning",
    changed_path: Annotated[
        list[str] | None,
        typer.Option("--changed-path", help="Workspace-relative artifact path changed by worker."),
    ] = None,
    blocker: Annotated[
        list[str] | None,
        typer.Option("--blocker", help="Project blocker recorded for this round."),
    ] = None,
    next_action: Annotated[str, typer.Option("--next-action")] = "",
    summary_json: Annotated[
        Path | None,
        typer.Option(
            "--summary-json",
            help="JSON/YAML StrategyProjectRun summary with step_events and blocker_summary.",
        ),
    ] = None,
) -> None:
    """Append a lightweight worker run summary and run deterministic path/spec checks."""
    from open_composer.projects import append_project_run, verify_project_run

    root = project_root()
    project = load_project(project_id, root)
    if summary_json is not None:
        run = load_project_run_summary(summary_json)
    else:
        if round_number is None:
            raise typer.BadParameter("--round is required unless --summary-json is provided")
        run = StrategyProjectRun(
            round=round_number,
            status=status,  # type: ignore[arg-type]
            changed_paths=changed_path or [],
            blockers=blocker or [],
            next_action=next_action,
        )
    verified_run = verify_project_run(project, run, root)
    updated, run_path = append_project_run(project_id, verified_run, root)
    console.print(f"[green]project run written[/green] {run_path.relative_to(root)}")
    console.print(f"project={updated.project_id} state={updated.state} blockers={updated.blockers}")


@project_app.command("continue")
def project_continue_command(
    project_id: str,
    rounds: Annotated[
        int, typer.Option("--rounds", help="Number of bounded rounds to request.")
    ] = 1,
    advice: Annotated[
        str | None,
        typer.Option("--advice", help="Inline user advice for the next iteration."),
    ] = None,
    advice_file: Annotated[
        Path | None,
        typer.Option("--advice-file", help="Markdown/text file with user advice."),
    ] = None,
    requested_by: Annotated[str, typer.Option("--requested-by")] = "cli",
    kind: Annotated[
        str,
        typer.Option("--kind", help="continue, advice, stop, llm_factor_eval, or materialize."),
    ] = "continue",
    via_backend: Annotated[
        bool,
        typer.Option("--via-backend/--queue-only", help="Send through configured AgentBackend."),
    ] = True,
) -> None:
    """Append a durable queue command and refresh context for a StrategyProject."""
    from open_composer.agent_backend import get_agent_backend
    from open_composer.research.iteration_controller import continue_project

    advice_text = advice or ""
    if advice_file is not None:
        advice_text = advice_file.read_text(encoding="utf-8")
    result = continue_project(
        project_id,
        root=project_root(),
        kind=kind,  # type: ignore[arg-type]
        body=advice_text,
        via="cli",
        rounds=rounds,
        requested_by=requested_by,
    )
    if via_backend:
        backend = get_agent_backend()
        backend.send_command(
            project_id,
            kind=kind,
            body=advice_text,
            root=project_root(),
            existing_command_id=result.queue_command.id,
        )
    console.print(f"[green]queue command written[/green] {result.queue_command.id}")
    console.print(f"context={result.context_path} ({result.context_bytes} bytes)")
    console.print(f"queue={result.queue_path} trace={result.trace_path} intent={result.intent}")
    console.print(f"artifact_state={result.artifact_state_path}")


@project_app.command("iterate", hidden=True)
def project_iterate_command(
    project_id: str,
    rounds: Annotated[int, typer.Option("--rounds")] = 1,
    advice: Annotated[str | None, typer.Option("--advice")] = None,
    advice_file: Annotated[Path | None, typer.Option("--advice-file")] = None,
    requested_by: Annotated[str, typer.Option("--requested-by")] = "cli",
) -> None:
    """[DEPRECATED] Use `oc project continue`."""
    console.print("[yellow][DEPRECATED][/yellow] Use `oc project continue`.")
    project_continue_command(
        project_id=project_id,
        rounds=rounds,
        advice=advice,
        advice_file=advice_file,
        requested_by=requested_by,
        kind="continue",
        via_backend=False,
    )


@agent_app.command("status")
def agent_status_command(project_id: str) -> None:
    """Show the configured agent backend status for a StrategyProject."""
    from open_composer.agent_backend import get_agent_backend

    backend = get_agent_backend()
    status = backend.status(project_id, project_root())
    console.print(
        f"backend={status.backend} status={status.status} "
        f"session={status.session_id or 'n/a'} queue_pending={status.queue_pending}"
    )


@agent_app.command("use")
def agent_use_command(
    backend: Annotated[str, typer.Option("--backend", help="codex_sdk or file_queue")],
) -> None:
    """Persist the default agent backend in .env."""
    if backend not in {"codex_sdk", "file_queue"}:
        raise typer.BadParameter("--backend must be codex_sdk or file_queue")
    root = project_root()
    env_path = root / ".env"
    lines = env_path.read_text(encoding="utf-8").splitlines() if env_path.exists() else []
    updated = False
    for index, line in enumerate(lines):
        if line.startswith("OPEN_COMPOSER_AGENT_BACKEND="):
            lines[index] = f"OPEN_COMPOSER_AGENT_BACKEND={backend}"
            updated = True
            break
    if not updated:
        lines.append(f"OPEN_COMPOSER_AGENT_BACKEND={backend}")
    env_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    console.print(f"[green]agent backend set[/green] {backend} in {env_path}")


@agent_app.command("stop")
def agent_stop_command(project_id: str) -> None:
    """Request stop/cancel through the configured agent backend."""
    from open_composer.agent_backend import get_agent_backend

    backend = get_agent_backend()
    backend.stop(project_id, project_root())
    console.print(f"[green]stop requested[/green] backend={backend.name} project={project_id}")


@notify_app.command("status")
def notify_status_command(
    limit: Annotated[int, typer.Option("--limit", help="Recent notification log rows.")] = 10,
) -> None:
    """Show outbound notification configuration without exposing secrets."""
    root = project_root()
    status = notification_config_status(root)
    table = Table(title="Open Composer Notifications")
    table.add_column("Item")
    table.add_column("Value")
    table.add_row("Config", status.config_path)
    table.add_row("Config exists", str(status.config_exists))
    table.add_row("Log", status.log_path)
    table.add_row("Telegram enabled", str(status.telegram_enabled))
    table.add_row(
        status.telegram_bot_token_env, "set" if status.telegram_bot_token_present else "missing"
    )
    table.add_row(
        status.telegram_chat_id_env, "set" if status.telegram_chat_id_present else "missing"
    )
    table.add_row("Parse mode", status.telegram_parse_mode)
    console.print(table)

    policy_table = Table(title="Notification Policies")
    policy_table.add_column("Kind")
    policy_table.add_column("Min severity")
    policy_table.add_column("Channels")
    for policy in status.policies:
        policy_table.add_row(policy.kind, policy.min_severity, ", ".join(policy.channels))
    console.print(policy_table)

    rows = read_notification_log(root, limit=limit)
    if rows:
        log_table = Table(title="Recent Notifications")
        log_table.add_column("Created")
        log_table.add_column("Kind")
        log_table.add_column("Severity")
        log_table.add_column("Title")
        for row in rows:
            log_table.add_row(
                str(row.get("created_at", "")),
                str(row.get("kind", "")),
                str(row.get("severity", "")),
                str(row.get("title", "")),
            )
        console.print(log_table)


@notify_app.command("test")
def notify_test_command(
    kind: Annotated[
        str, typer.Option("--kind", help="Notification kind to test.")
    ] = "signal_actionable",
    severity: Annotated[str, typer.Option("--severity", help="info, warn, or red.")] = "info",
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Do not send to outbound channels."),
    ] = False,
) -> None:
    """Send or dry-run a test outbound notification."""
    allowed_kinds = set(get_args(NotificationKind))
    allowed_severities = set(get_args(NotificationSeverity))
    if kind not in allowed_kinds:
        raise typer.BadParameter(f"kind must be one of: {', '.join(sorted(allowed_kinds))}")
    if severity not in allowed_severities:
        raise typer.BadParameter(
            f"severity must be one of: {', '.join(sorted(allowed_severities))}"
        )
    record = send_test_notification(
        project_root(),
        kind=kind,  # type: ignore[arg-type]
        severity=severity,  # type: ignore[arg-type]
        dry_run=dry_run,
    )
    console.print(
        f"[green]notification recorded[/green] {record.id} "
        f"deliveries={[(item.channel, item.status) for item in record.deliveries]}"
    )


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


def _parse_gate_status(value: str) -> object:
    normalized = value.strip().lower()
    if normalized in {"true", "pass", "passed", "ok"}:
        return True if normalized == "true" else normalized
    if normalized in {"false", "fail", "failed", "blocked"}:
        return False if normalized == "false" else normalized
    if normalized in {"none", "null", "not_applicable", "n/a"}:
        return None if normalized in {"none", "null"} else "not_applicable"
    return value


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


@data_app.command("verify-research-cache")
def data_verify_research_cache(
    manifest: Annotated[
        Path | None,
        typer.Option(
            "--manifest",
            help=(
                "Research cache manifest path; defaults to "
                f"{DEFAULT_RESEARCH_CACHE_DIR / 'manifest.json'}."
            ),
        ),
    ] = None,
) -> None:
    """Verify Longbridge adjusted research cache against its manifest."""
    try:
        report = verify_longbridge_research_cache_manifest(
            project_root(),
            manifest_path=manifest,
        )
    except (FileNotFoundError, ValueError, KeyError, json.JSONDecodeError) as exc:
        console.print(f"[red]research cache verification failed[/red] {exc}")
        raise typer.Exit(1) from exc
    status = "passed" if report["passed"] else "drift"
    console.print(
        f"[green]research cache {status}[/green] "
        f"manifest={report['manifest_path']} checked={len(report['checked_symbols'])}"
    )
    if report["drift"]:
        table = Table(title="Research Cache Drift")
        table.add_column("Symbol")
        table.add_column("Field")
        table.add_column("Expected")
        table.add_column("Actual")
        for item in report["drift"]:
            table.add_row(
                str(item["symbol"]),
                str(item["field"]),
                str(item["expected"]),
                str(item["actual"]),
            )
        console.print(table)
        raise typer.Exit(1)


@data_app.command("minute-momentum-feasibility")
def data_minute_momentum_feasibility(
    symbols: Annotated[
        str | None,
        typer.Option("--symbols", help="Comma-separated symbols; defaults to Step 9 ETF set."),
    ] = None,
    representative_symbols: Annotated[
        str | None,
        typer.Option(
            "--representative-symbols",
            help="Comma-separated representative symbols for 1m/5m sampling.",
        ),
    ] = None,
    timeframes: Annotated[
        str | None,
        typer.Option(
            "--timeframes", help="Comma-separated timeframes; defaults to 1m,5m,15m,30m,1h."
        ),
    ] = None,
    start: Annotated[str | None, typer.Option("--start")] = None,
    end: Annotated[str | None, typer.Option("--end")] = None,
    feed: Annotated[str | None, typer.Option("--feed")] = None,
    fetch_missing: Annotated[bool, typer.Option("--fetch-missing/--cache-only")] = False,
    report_date: Annotated[str | None, typer.Option("--report-date")] = None,
) -> None:
    """Materialize isolated Alpaca minute-data feasibility artifacts."""
    from open_composer.research.minute_momentum_feasibility import (
        run_minute_momentum_feasibility,
    )

    try:
        result = run_minute_momentum_feasibility(
            project_root(),
            symbols=_csv_upper(symbols),
            representative_symbols=_csv_upper(representative_symbols),
            timeframes=_csv_list(timeframes),
            start=start,
            end=end,
            feed=feed,
            fetch_missing=fetch_missing,
            report_date=report_date,
        )
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    console.print("[green]minute momentum feasibility written[/green]")
    console.print(f"json: {result.json_path}")
    console.print(f"markdown: {result.markdown_path}")
    console.print(f"manifest: {result.manifest_path}")


@data_app.command("fetch-alt-daily")
def data_fetch_alt_daily(
    source: str = typer.Option(ROUTE_CROSS_SOURCE_DEFAULT_ALT_SOURCE, "--source"),
    feed: str | None = typer.Option(ROUTE_CROSS_SOURCE_DEFAULT_ALT_FEED, "--feed"),
    start: str = typer.Option(ROUTE_CROSS_SOURCE_DEFAULT_START, "--start"),
    end: str = typer.Option(ROUTE_CROSS_SOURCE_DEFAULT_END, "--end"),
    output_dir: Annotated[Path | None, typer.Option("--output-dir")] = None,
    symbols: str | None = typer.Option(
        None,
        "--symbols",
        help="Comma-separated symbols; defaults to the primary research cache manifest.",
    ),
    refresh_data: bool = typer.Option(False, "--refresh-data/--use-cache"),
) -> None:
    """Materialize an alternate daily source for fixed-route cross-source replay."""
    parsed_symbols = (
        [item.strip().upper() for item in symbols.split(",") if item.strip()] if symbols else None
    )
    try:
        manifest = materialize_alt_daily_source(
            root=project_root(),
            source=source,
            feed=feed,
            symbols=parsed_symbols,
            start=start,
            end=end,
            output_dir=output_dir,
            refresh_data=refresh_data,
        )
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    manifest_path = Path(manifest["output_dir"]) / "manifest.json"
    console.print(
        f"[green]alternate daily source materialized[/green] "
        f"source={source} symbols={len(manifest['symbols'])} errors={len(manifest['errors'])}"
    )
    console.print(f"manifest={manifest_path}")
    if manifest["errors"]:
        raise typer.Exit(1)


@events_app.command("fetch")
def events_fetch(
    source: str = typer.Option("sec", "--source"),
    symbols: str = typer.Option("QQQ", "--symbols"),
    offline: bool = typer.Option(True, "--offline/--live"),
    limit: int | None = typer.Option(None, "--limit"),
    time_from: str | None = typer.Option(None, "--time-from"),
    time_to: str | None = typer.Option(None, "--time-to"),
    sort: str | None = typer.Option(None, "--sort"),
) -> None:
    """Fetch or replay event/news records into raw event logs."""
    selected_symbols = [symbol.strip().upper() for symbol in symbols.split(",") if symbol.strip()]
    events = fetch_capability_events(
        source,
        project_root(),
        selected_symbols,
        offline=offline,
        limit=limit,
        time_from=time_from,
        time_to=time_to,
        sort=sort,
    )
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
def review_signal(
    signal_id: str,
    force: Annotated[
        bool,
        typer.Option(
            "--force",
            help="Run review even when the strategy has llm_review.enabled=false.",
        ),
    ] = False,
) -> None:
    """Generate an optional OpenAI structured review card for a signal.

    By default, respects the strategy's llm_review.enabled flag. Use --force to
    override and request a review for strategies that have it disabled.
    """
    root = project_root()
    signal = find_signal(signal_id, root)
    spec_path = _find_strategy_spec(signal.strategy_name, root)
    spec = load_strategy_spec(spec_path)
    result = review_signal_with_status(signal, spec, root, force=force)
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
    """Draft a StrategySpec from a natural-language idea using registered capabilities.

    If --use-llm is set but the LLM call fails (network error, auth, 502, etc.),
    falls back to the deterministic drafter and records the fallback reason in
    the draft research plan.
    """
    result = draft_strategy_from_idea_with_status(idea, project_root(), use_llm=use_llm)
    spec = load_strategy_spec(result.path)
    if result.fallback_reason:
        console.print(
            f"[yellow]LLM draft failed[/yellow]: {result.fallback_reason}; "
            "fell back to deterministic draft"
        )
    mode = "llm" if result.used_llm else "deterministic"
    console.print(f"[green]draft written[/green] {result.path} ({spec.name}) [mode={mode}]")


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
    search_strategy: str = typer.Option("grid", "--search-strategy"),
    random_seed: int | None = typer.Option(None, "--random-seed"),
    from_spec: bool = typer.Option(
        False,
        "--from-spec",
        help="Use StrategySpec.research_design.parameter_space as sweep parameters.",
    ),
) -> None:
    """Run a bounded parameter grid over a StrategySpec and write ranked reports."""
    try:
        parsed = sweep_parameters_from_spec(spec, project_root()) if from_spec else {}
        parsed.update(parse_sweep_parameters(params or []))
        if from_spec and not parsed:
            raise ValueError(
                "StrategySpec research_design has no executable sweep paths; "
                "use paths rooted at entry, exit, risk, costs, or factors."
            )
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
            search_strategy=search_strategy,
            random_seed=random_seed,
        )
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    console.print(
        f"[green]parameter sweep complete[/green] candidates={len(result.candidates)} "
        f"best={result.best.spec.name} score={result.best.score:.2f}"
    )
    console.print(f"report: {result.report_path}")
    console.print(f"json: {result.json_path}")
    control = update_research_control(spec, project_root())
    console.print(f"memory: {control.memory_path}")


@research_brief_app.command("init")
def strategy_research_brief_init(
    spec: Path,
    search_budget: int | None = typer.Option(None, "--search-budget"),
    overwrite: bool = typer.Option(False, "--overwrite"),
) -> None:
    """Create or refresh the research brief required before optimization."""
    json_path, md_path = init_research_brief(
        spec,
        project_root(),
        search_budget=search_budget,
        overwrite=overwrite,
    )
    console.print(f"[green]research brief ready[/green] json: {json_path}")
    console.print(f"markdown: {md_path}")


@research_brief_app.command("validate")
def strategy_research_brief_validate(spec: Path) -> None:
    """Validate a research brief against the current StrategySpec hash."""
    result = validate_research_brief(spec, project_root(), require_for_optimization=True)
    if not result.ok:
        raise typer.BadParameter("research brief invalid: " + ", ".join(result.blocked))
    console.print(f"[green]research brief valid[/green] {result.path}")


@strategy_app.command("factor-lab")
def strategy_factor_lab(
    spec: Path,
    forward_bars: int = typer.Option(1, "--forward-bars"),
    quantiles: int = typer.Option(5, "--quantiles"),
) -> None:
    """Run a lightweight factor diagnostic report for a StrategySpec."""
    result = run_factor_lab(
        spec,
        project_root(),
        forward_bars=forward_bars,
        quantiles=quantiles,
    )
    console.print(
        f"[green]factor lab complete[/green] status={result.status} "
        f"factors={len(result.factor_metrics)}"
    )
    console.print(f"report: {result.report_path}")
    console.print(f"json: {result.json_path}")


@strategy_app.command("train")
def strategy_train(spec: Path) -> None:
    """Train a StrategySpec.model using purged walk-forward OOS folds."""
    from open_composer.research.ml_backend.evaluation import train_strategy_model

    try:
        training, paths = train_strategy_model(spec, project_root())
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    console.print(
        f"[green]ML training complete[/green] folds={len(training.folds)} "
        f"predictions={int(training.full_predictions.notna().sum())}"
    )
    console.print(f"json: {paths.training_json}")
    console.print(f"report: {paths.training_md}")


@strategy_app.command("backtest-walk-forward")
def strategy_backtest_walk_forward(spec: Path) -> None:
    """Backtest ML OOS predictions and compare with the linear baseline."""
    from open_composer.research.ml_backend.evaluation import compare_ml_to_baseline

    try:
        payload, paths = compare_ml_to_baseline(spec, project_root())
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    console.print(f"[green]ML walk-forward comparison complete[/green] status={payload['status']}")
    ml_sharpe = payload["ml"].get("sharpe_ratio")
    baseline_sharpe = payload["baseline"].get("sharpe_ratio")
    console.print(f"ml_sharpe={ml_sharpe} baseline_sharpe={baseline_sharpe}")
    console.print(f"json: {paths.comparison_json}")
    console.print(f"report: {paths.comparison_md}")


@strategy_app.command("explain")
def strategy_explain(
    spec: Path,
    top_n: int = typer.Option(10, "--top-n"),
    use_llm: bool = typer.Option(False, "--llm/--no-llm"),
) -> None:
    """Write a structured advisory ML explanation."""
    from open_composer.research.ml_backend.evaluation import explain_strategy_model

    try:
        path = explain_strategy_model(spec, project_root(), top_n=top_n, use_llm=use_llm)
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    console.print(f"[green]ML explanation written[/green] {path}")


@strategy_app.command("geometry-features")
def strategy_geometry_features(
    spec: Path,
    window_bars: int = typer.Option(20, "--window-bars"),
) -> None:
    """Build a research-only geometry/topology feature sandbox report."""
    try:
        result = build_geometry_feature_report(
            spec,
            project_root(),
            window_bars=window_bars,
        )
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    console.print(
        f"[green]geometry features complete[/green] status={result.status} "
        f"research_only={result.research_only}"
    )
    console.print(f"report: {result.report_path}")
    console.print(f"json: {result.json_path}")


@strategy_app.command("evidence")
def strategy_evidence(spec: Path) -> None:
    """Run the consolidated research evidence pipeline for a StrategySpec."""
    _print_strategy_evidence(spec)


def _print_strategy_evidence(spec: Path) -> None:
    result = build_strategy_evidence(spec, project_root())
    console.print(f"[green]strategy evidence complete[/green] status={result.status}")
    console.print(f"contract: {result.research_report.contract_path}")
    console.print(f"report: {result.research_report.report_path}")
    console.print(f"json: {result.research_report.json_path}")
    console.print(f"state: {result.control.state_path}")
    console.print(f"memory: {result.control.memory_path}")


@strategy_app.command("universe-audit")
def strategy_universe_audit(spec: Path) -> None:
    """Audit PIT universe, current-symbol, and survivorship risks."""
    result = run_universe_audit(spec, project_root())
    console.print(f"[green]universe audit complete[/green] status={result.status}")
    console.print(f"report: {result.report_path}")
    console.print(f"json: {result.json_path}")


@strategy_app.command("overfit-risk")
def strategy_overfit_risk(spec: Path) -> None:
    """Write the lightweight PBO/DSR proxy report for a parameter-sweep run."""
    result = build_overfit_risk_report(spec, project_root())
    console.print(f"[green]overfit risk complete[/green] status={result.status}")
    console.print(f"trials={result.trial_count} dsr={result.dsr_proxy} pbo={result.pbo_proxy}")
    if result.report_path:
        console.print(f"report: {result.report_path}")
    if result.json_path:
        console.print(f"json: {result.json_path}")


@strategy_app.command("research-report", hidden=True)
def strategy_research_report(spec: Path) -> None:
    """[DEPRECATED] Use `oc strategy evidence`."""
    console.print("[yellow][DEPRECATED][/yellow] Use `oc strategy evidence`.")
    _print_strategy_evidence(spec)


@strategy_app.command("research-control", hidden=True)
def strategy_research_control(spec: Path) -> None:
    """[DEPRECATED] Use `oc strategy evidence`."""
    console.print("[yellow][DEPRECATED][/yellow] Use `oc strategy evidence`.")
    _print_strategy_evidence(spec)


@strategy_app.command("dag-validate")
def strategy_dag_validate(path: Path) -> None:
    """Validate a replay-only StrategyDAG file."""
    result = validate_strategy_dag(path, project_root())
    json_path, md_path = write_strategy_dag_validation(result, project_root())
    console.print(f"[green]dag validation complete[/green] status={result.status}")
    console.print(f"json: {json_path}")
    console.print(f"report: {md_path}")


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
    refresh_data: Annotated[
        bool,
        typer.Option(
            "--refresh-data/--use-cache",
            help="Refresh provider data before building the promotion report.",
        ),
    ] = False,
) -> None:
    """Build a promotion gate report with OOS, walk-forward, and cost sensitivity evidence."""
    result = build_promotion_report(
        spec,
        project_root(),
        out_of_sample_ratio=oos_ratio,
        walk_forward_folds=walk_forward_folds,
        cost_slippage_bps=cost_slippage_bps,
        refresh_data=refresh_data,
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


@strategy_app.command("execution-policy")
def strategy_execution_policy(
    spec: Path,
    overwrite: Annotated[
        bool,
        typer.Option(
            "--overwrite/--no-overwrite",
            help="Overwrite existing execution_policy/reality artifacts.",
        ),
    ] = False,
    source_cards: Annotated[
        list[str] | None,
        typer.Option(
            "--source-card",
            help=(
                "Source card IDs that back this execution policy (repeatable). "
                "Required for paper_auto: see source-researcher skill."
            ),
        ),
    ] = None,
) -> None:
    """Generate execution_policy and execution_reality_report draft artifacts.

    Compares at least two execution alternatives, picks a recommended policy
    based on detected risk context (leveraged_etf, daily_open, paper_auto),
    and writes the artifacts under ``reports/harness/execution/``. The artifacts
    conform to ``harness/artifact_contracts.yaml`` and unblock ``oc harness verify``.

    Source cards (from the source-researcher skill) should be passed via
    ``--source-card`` so the policy artifact references official broker docs.
    """
    from open_composer.research.execution_policy import generate_execution_policy_artifacts

    root = project_root()
    artifacts = generate_execution_policy_artifacts(
        spec,
        root=root,
        overwrite=overwrite,
        source_card_ids=source_cards,
    )
    console.print(
        f"[bold]execution-policy[/bold] recommended={artifacts.recommended_order_style!r}"
    )
    console.print(f"  policy   → {artifacts.policy_path.relative_to(root)}")
    console.print(f"  reality  → {artifacts.reality_path.relative_to(root)}")
    console.print(f"  markdown → {artifacts.markdown_path.relative_to(root)}")
    if not source_cards:
        console.print(
            "[yellow]warning[/yellow] no --source-card ids provided; "
            "broker_specific risk domain will block research_pass."
        )


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


@strategy_app.command("intraday-daily-rotation")
def strategy_intraday_daily_rotation(
    spec: Path,
    symbols: str = typer.Option(..., "--symbols"),
    data_source: str = typer.Option("alpaca", "--data-source"),
    start: str | None = typer.Option(None, "--start"),
    end: str | None = typer.Option(None, "--end"),
    benchmark_symbol: str = typer.Option("TQQQ", "--benchmark-symbol"),
    market_symbol: str = typer.Option("QQQ", "--market-symbol"),
    objective: str = typer.Option(
        "equal-weight-alpha",
        "--objective",
        help="Selection objective: equal-weight-alpha or benchmark-intraday-alpha.",
    ),
    lookback_days: Annotated[list[int] | None, typer.Option("--lookback-days")] = None,
    entry_after_bars: Annotated[
        list[int] | None,
        typer.Option("--entry-after-bars"),
    ] = None,
    top_n: Annotated[list[int] | None, typer.Option("--top-n")] = None,
    min_opening_return_pct: Annotated[
        list[float] | None,
        typer.Option("--min-opening-return-pct"),
    ] = None,
    min_prior_momentum_pct: Annotated[
        list[float] | None,
        typer.Option("--min-prior-momentum-pct"),
    ] = None,
    min_relative_volume: Annotated[
        list[float] | None,
        typer.Option("--min-relative-volume"),
    ] = None,
    selection_style: Annotated[list[str] | None, typer.Option("--selection-style")] = None,
    max_opening_return_pct: Annotated[
        list[float] | None,
        typer.Option("--max-opening-return-pct"),
    ] = None,
    max_prior_momentum_pct: Annotated[
        list[float] | None,
        typer.Option("--max-prior-momentum-pct"),
    ] = None,
    market_gate: Annotated[list[str] | None, typer.Option("--market-gate")] = None,
    oos_ratio: float = typer.Option(0.3, "--oos-ratio"),
    validation_ratio: float = typer.Option(0.3, "--validation-ratio"),
    walk_forward_folds: int = typer.Option(3, "--walk-forward-folds"),
    walk_forward_top_k: int | None = typer.Option(None, "--walk-forward-top-k"),
    max_candidates: int = typer.Option(240, "--max-candidates"),
    refresh_data: bool = typer.Option(False, "--refresh-data/--use-cache"),
) -> None:
    """Research daily selected, same-day-exit NASDAQ intraday stock rotation."""
    if data_source not in {"alpaca", "longbridge"}:
        raise typer.BadParameter("--data-source currently supports alpaca or longbridge")
    try:
        result = run_intraday_daily_rotation_research(
            spec,
            project_root(),
            symbols=[item.strip().upper() for item in symbols.split(",") if item.strip()],
            data_source=data_source,
            start=start,
            end=end,
            benchmark_symbol=benchmark_symbol.upper(),
            market_symbol=market_symbol.upper(),
            lookback_days=lookback_days,
            entry_after_bars=entry_after_bars,
            top_n_values=top_n,
            min_opening_return_pct=min_opening_return_pct,
            min_prior_momentum_pct=min_prior_momentum_pct,
            min_relative_volume=min_relative_volume,
            selection_styles=_intraday_selection_styles(selection_style),
            max_opening_return_pct=max_opening_return_pct,
            max_prior_momentum_pct=max_prior_momentum_pct,
            market_gates=_intraday_market_gates(market_gate),
            objective=_intraday_objective(objective),
            out_of_sample_ratio=oos_ratio,
            walk_forward_folds=walk_forward_folds,
            walk_forward_top_k=walk_forward_top_k,
            max_candidates=max_candidates,
            refresh_data=refresh_data,
        )
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    best = result.best
    console.print(f"[green]intraday daily rotation complete[/green] report: {result.report_path}")
    console.print(
        f"best={best.params.label} "
        f"oos_ann={best.out_of_sample.annualized_return_pct or 0.0:.2f}% "
        f"oos_equal_weight_alpha_ann="
        f"{best.out_of_sample.alpha_vs_equal_weight_annualized_pct or 0.0:.2f}% "
        f"oos_benchmark_intraday_alpha_ann="
        f"{best.out_of_sample.alpha_vs_benchmark_intraday_annualized_pct or 0.0:.2f}% "
        f"oos_sharpe={best.out_of_sample.sharpe_ratio or 0.0:.2f} "
        f"flags={','.join(best.quality_flags) if best.quality_flags else 'none'}"
    )
    console.print(
        f"candidates={result.research_cost['candidate_count']} "
        f"walk_forward_candidates={result.research_cost['walk_forward_candidate_count']} "
        f"estimated_passes={result.research_cost['estimated_total_backtest_passes']} "
        f"runtime={result.runtime_seconds['total']:.2f}s"
    )


@strategy_app.command("llm-intraday-daily-rotation")
def strategy_llm_intraday_daily_rotation(
    spec: Path,
    symbols: str = typer.Option(..., "--symbols"),
    data_source: str = typer.Option("alpaca", "--data-source"),
    start: str | None = typer.Option(None, "--start"),
    end: str | None = typer.Option(None, "--end"),
    benchmark_symbol: str = typer.Option("TQQQ", "--benchmark-symbol"),
    market_symbol: str = typer.Option("QQQ", "--market-symbol"),
    objective: str = typer.Option(
        "equal-weight-alpha",
        "--objective",
        help="Selection objective: equal-weight-alpha or benchmark-intraday-alpha.",
    ),
    lookback_days: Annotated[list[int] | None, typer.Option("--lookback-days")] = None,
    entry_after_bars: Annotated[
        list[int] | None,
        typer.Option("--entry-after-bars"),
    ] = None,
    top_n: Annotated[list[int] | None, typer.Option("--top-n")] = None,
    min_opening_return_pct: Annotated[
        list[float] | None,
        typer.Option("--min-opening-return-pct"),
    ] = None,
    min_prior_momentum_pct: Annotated[
        list[float] | None,
        typer.Option("--min-prior-momentum-pct"),
    ] = None,
    min_relative_volume: Annotated[
        list[float] | None,
        typer.Option("--min-relative-volume"),
    ] = None,
    selection_style: Annotated[list[str] | None, typer.Option("--selection-style")] = None,
    max_opening_return_pct: Annotated[
        list[float] | None,
        typer.Option("--max-opening-return-pct"),
    ] = None,
    max_prior_momentum_pct: Annotated[
        list[float] | None,
        typer.Option("--max-prior-momentum-pct"),
    ] = None,
    market_gate: Annotated[list[str] | None, typer.Option("--market-gate")] = None,
    validation_ratio: float = typer.Option(0.3, "--validation-ratio"),
    validation_folds: int = typer.Option(3, "--validation-folds"),
    oos_ratio: float = typer.Option(0.3, "--oos-ratio"),
    max_candidates: int = typer.Option(240, "--max-candidates"),
    refresh_data: bool = typer.Option(False, "--refresh-data/--use-cache"),
    local_choice_label: str | None = typer.Option(None, "--local-choice-label"),
) -> None:
    """Use an LLM to select an intraday daily rotation method from training evidence."""
    if data_source not in {"alpaca", "longbridge"}:
        raise typer.BadParameter("--data-source currently supports alpaca or longbridge")
    try:
        result = run_llm_intraday_daily_rotation_selection(
            spec,
            project_root(),
            symbols=[item.strip().upper() for item in symbols.split(",") if item.strip()],
            data_source=data_source,
            start=start,
            end=end,
            benchmark_symbol=benchmark_symbol.upper(),
            market_symbol=market_symbol.upper(),
            lookback_days=lookback_days,
            entry_after_bars=entry_after_bars,
            top_n_values=top_n,
            min_opening_return_pct=min_opening_return_pct,
            min_prior_momentum_pct=min_prior_momentum_pct,
            min_relative_volume=min_relative_volume,
            selection_styles=_intraday_selection_styles(selection_style),
            max_opening_return_pct=max_opening_return_pct,
            max_prior_momentum_pct=max_prior_momentum_pct,
            market_gates=_intraday_market_gates(market_gate),
            objective=_intraday_objective(objective),
            validation_ratio=validation_ratio,
            validation_folds=validation_folds,
            out_of_sample_ratio=oos_ratio,
            max_candidates=max_candidates,
            refresh_data=refresh_data,
            local_choice_label=local_choice_label,
        )
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    selected = result.selected
    pure_report_stem = spec.stem.removesuffix("_llm")
    reflection_path = write_intraday_product_reflection(
        project_root(),
        pure_report=project_root()
        / "reports"
        / "research"
        / f"{pure_report_stem}-intraday-daily-rotation.md",
        llm_report=result.report_path,
    )
    console.print(f"[green]LLM intraday selection complete[/green] report: {result.report_path}")
    console.print(f"[green]product reflection written[/green] {reflection_path}")
    console.print(
        f"selected={result.choice.selected_label} "
        f"status={result.status} "
        f"oos_ann={selected.out_of_sample.annualized_return_pct or 0.0:.2f}% "
        f"oos_equal_weight_alpha_ann="
        f"{selected.out_of_sample.alpha_vs_equal_weight_annualized_pct or 0.0:.2f}% "
        f"oos_benchmark_intraday_alpha_ann="
        f"{selected.out_of_sample.alpha_vs_benchmark_intraday_annualized_pct or 0.0:.2f}% "
        f"oos_sharpe={selected.out_of_sample.sharpe_ratio or 0.0:.2f} "
        f"flags={','.join(selected.quality_flags) if selected.quality_flags else 'none'}"
    )


@strategy_app.command("adaptive-intraday-router")
def strategy_adaptive_intraday_router(
    spec: Path,
    symbols: str = typer.Option(..., "--symbols"),
    data_source: str = typer.Option("alpaca", "--data-source"),
    start: str | None = typer.Option(None, "--start"),
    end: str | None = typer.Option(None, "--end"),
    benchmark_symbol: str = typer.Option("TQQQ", "--benchmark-symbol"),
    market_symbol: str = typer.Option("QQQ", "--market-symbol"),
    objective: str = typer.Option(
        "equal-weight-alpha",
        "--objective",
        help="Selection objective: equal-weight-alpha or benchmark-intraday-alpha.",
    ),
    lookback_days: Annotated[list[int] | None, typer.Option("--lookback-days")] = None,
    entry_after_bars: Annotated[
        list[int] | None,
        typer.Option("--entry-after-bars"),
    ] = None,
    top_n: Annotated[list[int] | None, typer.Option("--top-n")] = None,
    min_opening_return_pct: Annotated[
        list[float] | None,
        typer.Option("--min-opening-return-pct"),
    ] = None,
    min_prior_momentum_pct: Annotated[
        list[float] | None,
        typer.Option("--min-prior-momentum-pct"),
    ] = None,
    min_relative_volume: Annotated[
        list[float] | None,
        typer.Option("--min-relative-volume"),
    ] = None,
    selection_style: Annotated[list[str] | None, typer.Option("--selection-style")] = None,
    max_opening_return_pct: Annotated[
        list[float] | None,
        typer.Option("--max-opening-return-pct"),
    ] = None,
    max_prior_momentum_pct: Annotated[
        list[float] | None,
        typer.Option("--max-prior-momentum-pct"),
    ] = None,
    market_gate: Annotated[list[str] | None, typer.Option("--market-gate")] = None,
    oos_ratio: float = typer.Option(0.3, "--oos-ratio"),
    walk_forward_folds: int = typer.Option(3, "--walk-forward-folds"),
    top_per_family: int = typer.Option(3, "--top-per-family"),
    max_route_candidates: int = typer.Option(180, "--max-route-candidates"),
    max_base_candidates: int = typer.Option(720, "--max-base-candidates"),
    refresh_data: bool = typer.Option(False, "--refresh-data/--use-cache"),
) -> None:
    """Research one StrategySpec with internal market scanning and sub-strategy routing."""
    if data_source not in {"alpaca", "longbridge"}:
        raise typer.BadParameter("--data-source currently supports alpaca or longbridge")
    try:
        result = run_adaptive_intraday_router_research(
            spec,
            project_root(),
            symbols=[item.strip().upper() for item in symbols.split(",") if item.strip()],
            data_source=data_source,
            start=start,
            end=end,
            benchmark_symbol=benchmark_symbol.upper(),
            market_symbol=market_symbol.upper(),
            lookback_days=lookback_days,
            entry_after_bars=entry_after_bars,
            top_n_values=top_n,
            min_opening_return_pct=min_opening_return_pct,
            min_prior_momentum_pct=min_prior_momentum_pct,
            min_relative_volume=min_relative_volume,
            selection_styles=_intraday_selection_styles(selection_style),
            max_opening_return_pct=max_opening_return_pct,
            max_prior_momentum_pct=max_prior_momentum_pct,
            market_gates=_intraday_market_gates(market_gate),
            objective=_intraday_objective(objective),
            out_of_sample_ratio=oos_ratio,
            walk_forward_folds=walk_forward_folds,
            top_per_family=top_per_family,
            max_route_candidates=max_route_candidates,
            max_base_candidates=max_base_candidates,
            refresh_data=refresh_data,
        )
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    best = result.best
    console.print(f"[green]adaptive intraday router complete[/green] report: {result.report_path}")
    console.print(
        f"best_rank={best.rank} "
        f"oos_ann={best.out_of_sample.base.annualized_return_pct or 0.0:.2f}% "
        f"oos_equal_weight_alpha_ann="
        f"{best.out_of_sample.base.alpha_vs_equal_weight_annualized_pct or 0.0:.2f}% "
        f"oos_benchmark_intraday_alpha_ann="
        f"{best.out_of_sample.base.alpha_vs_benchmark_intraday_annualized_pct or 0.0:.2f}% "
        f"oos_sharpe={best.out_of_sample.base.sharpe_ratio or 0.0:.2f} "
        f"flags={','.join(best.quality_flags) if best.quality_flags else 'none'}"
    )
    console.print(
        f"candidates={result.research_cost.get('candidate_count', 0)} "
        f"walk_forward_candidates="
        f"{result.research_cost.get('walk_forward_candidate_count', 0)} "
        f"estimated_passes={result.research_cost.get('estimated_total_backtest_passes', 0)} "
        f"runtime={result.runtime_seconds['total']:.2f}s"
    )


@strategy_app.command("adaptive-intraday-router-scan")
def strategy_adaptive_intraday_router_scan(
    spec: Path,
    symbols: str = typer.Option(..., "--symbols"),
    data_source: str = typer.Option("alpaca", "--data-source"),
    start: str | None = typer.Option(None, "--start"),
    end: str | None = typer.Option(None, "--end"),
    benchmark_symbol: str = typer.Option("TQQQ", "--benchmark-symbol"),
    market_symbol: str = typer.Option("QQQ", "--market-symbol"),
    route_label: str | None = typer.Option(None, "--route-label"),
    scan_date: str | None = typer.Option(None, "--scan-date"),
    refresh_data: bool = typer.Option(False, "--refresh-data/--use-cache"),
    emit_context_packets: bool = typer.Option(
        True,
        "--emit-context-packets/--no-context-packets",
    ),
    emit_news_packet: bool = typer.Option(True, "--emit-news-packet/--no-news-packet"),
    news_lookback_hours: int = typer.Option(72, "--news-lookback-hours"),
) -> None:
    """Scan the adaptive router and write standard signals plus replayable feature packets."""
    if data_source not in {"alpaca", "longbridge"}:
        raise typer.BadParameter("--data-source currently supports alpaca or longbridge")
    try:
        result = run_adaptive_intraday_router_scan(
            spec,
            project_root(),
            symbols=[item.strip().upper() for item in symbols.split(",") if item.strip()],
            data_source=data_source,
            start=start,
            end=end,
            benchmark_symbol=benchmark_symbol.upper(),
            market_symbol=market_symbol.upper(),
            route_label=route_label,
            scan_date=scan_date,
            refresh_data=refresh_data,
            emit_context_packets=emit_context_packets,
            emit_news_packet=emit_news_packet,
            news_lookback_hours=news_lookback_hours,
        )
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    console.print(f"[green]adaptive router scan complete[/green] report: {result.report_path}")
    console.print(f"signals={len(result.signals)} log={result.signal_log_path}")
    console.print(f"json={result.json_path}")
    if result.feature_packet_path:
        console.print(f"news_features={result.feature_packet_path}")
    for signal in result.signals:
        console.print(f"{signal.id} {signal.action} {signal.symbol} @ {signal.price:.2f}")


@strategy_app.command("llm-adaptive-intraday-router")
def strategy_llm_adaptive_intraday_router(
    spec: Path,
    symbols: str = typer.Option(..., "--symbols"),
    data_source: str = typer.Option("alpaca", "--data-source"),
    start: str | None = typer.Option(None, "--start"),
    end: str | None = typer.Option(None, "--end"),
    benchmark_symbol: str = typer.Option("TQQQ", "--benchmark-symbol"),
    market_symbol: str = typer.Option("QQQ", "--market-symbol"),
    objective: str = typer.Option(
        "equal-weight-alpha",
        "--objective",
        help="Selection objective: equal-weight-alpha or benchmark-intraday-alpha.",
    ),
    lookback_days: Annotated[list[int] | None, typer.Option("--lookback-days")] = None,
    entry_after_bars: Annotated[
        list[int] | None,
        typer.Option("--entry-after-bars"),
    ] = None,
    top_n: Annotated[list[int] | None, typer.Option("--top-n")] = None,
    min_opening_return_pct: Annotated[
        list[float] | None,
        typer.Option("--min-opening-return-pct"),
    ] = None,
    min_prior_momentum_pct: Annotated[
        list[float] | None,
        typer.Option("--min-prior-momentum-pct"),
    ] = None,
    min_relative_volume: Annotated[
        list[float] | None,
        typer.Option("--min-relative-volume"),
    ] = None,
    selection_style: Annotated[list[str] | None, typer.Option("--selection-style")] = None,
    max_opening_return_pct: Annotated[
        list[float] | None,
        typer.Option("--max-opening-return-pct"),
    ] = None,
    max_prior_momentum_pct: Annotated[
        list[float] | None,
        typer.Option("--max-prior-momentum-pct"),
    ] = None,
    market_gate: Annotated[list[str] | None, typer.Option("--market-gate")] = None,
    validation_ratio: float = typer.Option(0.3, "--validation-ratio"),
    oos_ratio: float = typer.Option(0.3, "--oos-ratio"),
    top_per_family: int = typer.Option(3, "--top-per-family"),
    max_route_candidates: int = typer.Option(120, "--max-route-candidates"),
    max_base_candidates: int = typer.Option(720, "--max-base-candidates"),
    refresh_data: bool = typer.Option(False, "--refresh-data/--use-cache"),
    local_choice_label: str | None = typer.Option(None, "--local-choice-label"),
) -> None:
    """Use an LLM to select an internal adaptive intraday route from training evidence."""
    if data_source not in {"alpaca", "longbridge"}:
        raise typer.BadParameter("--data-source currently supports alpaca or longbridge")
    try:
        result = run_llm_adaptive_intraday_router_selection(
            spec,
            project_root(),
            symbols=[item.strip().upper() for item in symbols.split(",") if item.strip()],
            data_source=data_source,
            start=start,
            end=end,
            benchmark_symbol=benchmark_symbol.upper(),
            market_symbol=market_symbol.upper(),
            lookback_days=lookback_days,
            entry_after_bars=entry_after_bars,
            top_n_values=top_n,
            min_opening_return_pct=min_opening_return_pct,
            min_prior_momentum_pct=min_prior_momentum_pct,
            min_relative_volume=min_relative_volume,
            selection_styles=_intraday_selection_styles(selection_style),
            max_opening_return_pct=max_opening_return_pct,
            max_prior_momentum_pct=max_prior_momentum_pct,
            market_gates=_intraday_market_gates(market_gate),
            objective=_intraday_objective(objective),
            validation_ratio=validation_ratio,
            out_of_sample_ratio=oos_ratio,
            top_per_family=top_per_family,
            max_route_candidates=max_route_candidates,
            max_base_candidates=max_base_candidates,
            refresh_data=refresh_data,
            local_choice_label=local_choice_label,
        )
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    selected = result.selected
    console.print(f"[green]LLM adaptive router complete[/green] report: {result.report_path}")
    console.print(
        f"selected_rank={selected.rank} status={result.status} "
        f"oos_ann={selected.out_of_sample.base.annualized_return_pct or 0.0:.2f}% "
        f"oos_equal_weight_alpha_ann="
        f"{selected.out_of_sample.base.alpha_vs_equal_weight_annualized_pct or 0.0:.2f}% "
        f"oos_benchmark_intraday_alpha_ann="
        f"{selected.out_of_sample.base.alpha_vs_benchmark_intraday_annualized_pct or 0.0:.2f}% "
        f"oos_sharpe={selected.out_of_sample.base.sharpe_ratio or 0.0:.2f} "
        f"flags={','.join(selected.quality_flags) if selected.quality_flags else 'none'}"
    )


@strategy_app.command("hybrid-adaptive-router")
def strategy_hybrid_adaptive_router(
    spec: Path,
    symbols: str = typer.Option(..., "--symbols"),
    data_source: str = typer.Option("alpaca", "--data-source"),
    feed: str | None = typer.Option(None, "--feed"),
    start: str | None = typer.Option(None, "--start"),
    end: str | None = typer.Option(None, "--end"),
    benchmark_symbol: str = typer.Option("TQQQ", "--benchmark-symbol"),
    market_symbol: str = typer.Option("QQQ", "--market-symbol"),
    objective: str = typer.Option(
        "benchmark-buy-hold-alpha",
        "--objective",
        help=(
            "Selection objective: benchmark-buy-hold-alpha, risk-adjusted-benchmark-alpha, "
            "or absolute-return-risk."
        ),
    ),
    holding_mode: Annotated[list[str] | None, typer.Option("--holding-mode")] = None,
    momentum_lookback_days: Annotated[
        list[int] | None,
        typer.Option("--momentum-lookback-days"),
    ] = None,
    top_n: Annotated[list[int] | None, typer.Option("--top-n")] = None,
    market_sma_days: Annotated[list[str] | None, typer.Option("--market-sma-days")] = None,
    min_momentum_pct: Annotated[list[float] | None, typer.Option("--min-momentum-pct")] = None,
    max_position_weight: Annotated[
        list[float] | None,
        typer.Option("--max-position-weight"),
    ] = None,
    gross_exposure_limit: Annotated[
        list[float] | None,
        typer.Option("--gross-exposure-limit"),
    ] = None,
    momentum_score_mode: Annotated[
        list[str] | None,
        typer.Option("--momentum-score-mode"),
    ] = None,
    risk_adjustment_lookback_days: Annotated[
        list[str] | None,
        typer.Option("--risk-adjustment-lookback-days"),
    ] = None,
    market_below_sma_scale: Annotated[
        list[float] | None,
        typer.Option("--market-below-sma-scale"),
    ] = None,
    volatility_lookback_days: Annotated[
        list[str] | None,
        typer.Option("--volatility-lookback-days"),
    ] = None,
    target_volatility_annual_pct: Annotated[
        list[str] | None,
        typer.Option("--target-volatility-annual-pct"),
    ] = None,
    market_drawdown_lookback_days: Annotated[
        list[str] | None,
        typer.Option("--market-drawdown-lookback-days"),
    ] = None,
    market_drawdown_brake_pct: Annotated[
        list[str] | None,
        typer.Option("--market-drawdown-brake-pct"),
    ] = None,
    brake_exposure_scale: Annotated[
        list[float] | None,
        typer.Option("--brake-exposure-scale"),
    ] = None,
    beta_override_base_mode: Annotated[
        list[str] | None,
        typer.Option("--beta-override-base-mode"),
    ] = None,
    beta_override_advantage_pct: Annotated[
        list[float] | None,
        typer.Option("--beta-override-advantage-pct"),
    ] = None,
    beta_override_confirmation_sma_days: Annotated[
        list[str] | None,
        typer.Option("--beta-override-confirmation-sma-days"),
    ] = None,
    beta_override_exclude_tqqq: bool = typer.Option(
        True,
        "--beta-override-exclude-tqqq/--beta-override-include-tqqq",
    ),
    beta_override_weight_scale: Annotated[
        list[float] | None,
        typer.Option("--beta-override-weight-scale"),
    ] = None,
    beta_override_target_volatility_annual_pct: Annotated[
        list[str] | None,
        typer.Option("--beta-override-target-volatility-annual-pct"),
    ] = None,
    beta_override_cycle_gate: Annotated[
        list[str] | None,
        typer.Option("--beta-override-cycle-gate"),
    ] = None,
    beta_override_symbol_drawdown_lookback_days: Annotated[
        list[str] | None,
        typer.Option("--beta-override-symbol-drawdown-lookback-days"),
    ] = None,
    beta_override_max_symbol_drawdown_pct: Annotated[
        list[str] | None,
        typer.Option("--beta-override-max-symbol-drawdown-pct"),
    ] = None,
    beta_override_short_momentum_lookback_days: Annotated[
        list[str] | None,
        typer.Option("--beta-override-short-momentum-lookback-days"),
    ] = None,
    beta_override_min_short_momentum_pct: Annotated[
        list[str] | None,
        typer.Option("--beta-override-min-short-momentum-pct"),
    ] = None,
    beta_override_bear_inverse_symbol: Annotated[
        list[str] | None,
        typer.Option("--beta-override-bear-inverse-symbol"),
    ] = None,
    beta_override_bear_inverse_lookback_days: Annotated[
        list[int] | None,
        typer.Option("--beta-override-bear-inverse-lookback-days"),
    ] = None,
    beta_override_bear_inverse_min_momentum_pct: Annotated[
        list[float] | None,
        typer.Option("--beta-override-bear-inverse-min-momentum-pct"),
    ] = None,
    beta_override_bear_inverse_confirmation_sma_days: Annotated[
        list[str] | None,
        typer.Option("--beta-override-bear-inverse-confirmation-sma-days"),
    ] = None,
    beta_override_bear_inverse_weight: Annotated[
        list[float] | None,
        typer.Option("--beta-override-bear-inverse-weight"),
    ] = None,
    beta_override_leadership_breadth_lookback_days: Annotated[
        list[str] | None,
        typer.Option("--beta-override-leadership-breadth-lookback-days"),
    ] = None,
    beta_override_min_leadership_breadth_count: Annotated[
        list[str] | None,
        typer.Option("--beta-override-min-leadership-breadth-count"),
    ] = None,
    beta_override_min_leadership_breadth_momentum_pct: Annotated[
        list[float] | None,
        typer.Option("--beta-override-min-leadership-breadth-momentum-pct"),
    ] = None,
    beta_override_leadership_breadth_scale: Annotated[
        list[float] | None,
        typer.Option("--beta-override-leadership-breadth-scale"),
    ] = None,
    beta_override_market_reentry_momentum_lookback_days: Annotated[
        list[str] | None,
        typer.Option("--beta-override-market-reentry-momentum-lookback-days"),
    ] = None,
    beta_override_min_market_reentry_momentum_pct: Annotated[
        list[str] | None,
        typer.Option("--beta-override-min-market-reentry-momentum-pct"),
    ] = None,
    oos_ratio: float = typer.Option(0.3, "--oos-ratio"),
    walk_forward_folds: int = typer.Option(3, "--walk-forward-folds"),
    walk_forward_top_k: int | None = typer.Option(20, "--walk-forward-top-k"),
    max_candidates: int = typer.Option(240, "--max-candidates"),
    refresh_data: bool = typer.Option(False, "--refresh-data/--use-cache"),
) -> None:
    """Research a hybrid intraday/swing NASDAQ router against TQQQ buy-hold."""
    if data_source not in {"alpaca", "longbridge"}:
        raise typer.BadParameter("--data-source currently supports alpaca or longbridge")
    try:
        result = run_hybrid_adaptive_router_research(
            spec,
            project_root(),
            symbols=[item.strip().upper() for item in symbols.split(",") if item.strip()],
            data_source=data_source,
            feed=feed,
            start=start,
            end=end,
            benchmark_symbol=benchmark_symbol.upper(),
            market_symbol=market_symbol.upper(),
            holding_modes=_hybrid_holding_modes(holding_mode),
            momentum_lookback_days=momentum_lookback_days,
            top_n_values=top_n,
            market_sma_days=_hybrid_market_sma_days(market_sma_days),
            min_momentum_pct=min_momentum_pct,
            max_position_weight=max_position_weight,
            gross_exposure_limit=gross_exposure_limit,
            momentum_score_mode=_hybrid_momentum_score_modes(momentum_score_mode),
            risk_adjustment_lookback_days=_optional_int_values(risk_adjustment_lookback_days),
            market_below_sma_scale=market_below_sma_scale,
            volatility_lookback_days=_optional_int_values(volatility_lookback_days),
            target_volatility_annual_pct=_optional_float_values(target_volatility_annual_pct),
            market_drawdown_lookback_days=_optional_int_values(market_drawdown_lookback_days),
            market_drawdown_brake_pct=_optional_float_values(market_drawdown_brake_pct),
            brake_exposure_scale=brake_exposure_scale,
            beta_override_base_modes=_hybrid_beta_override_base_modes(beta_override_base_mode),
            beta_override_advantage_pct=beta_override_advantage_pct,
            beta_override_confirmation_sma_days=_optional_int_values(
                beta_override_confirmation_sma_days
            ),
            beta_override_exclude_tqqq=beta_override_exclude_tqqq,
            beta_override_weight_scale=beta_override_weight_scale,
            beta_override_target_volatility_annual_pct=_optional_float_values(
                beta_override_target_volatility_annual_pct
            ),
            beta_override_cycle_gates=_hybrid_beta_override_cycle_gates(beta_override_cycle_gate),
            beta_override_symbol_drawdown_lookback_days=_optional_int_values(
                beta_override_symbol_drawdown_lookback_days
            ),
            beta_override_max_symbol_drawdown_pct=_optional_float_values(
                beta_override_max_symbol_drawdown_pct
            ),
            beta_override_short_momentum_lookback_days=_optional_int_values(
                beta_override_short_momentum_lookback_days
            ),
            beta_override_min_short_momentum_pct=_optional_float_values(
                beta_override_min_short_momentum_pct
            ),
            beta_override_bear_inverse_symbols=(
                _optional_symbol_values(beta_override_bear_inverse_symbol)
                if beta_override_bear_inverse_symbol
                else None
            ),
            beta_override_bear_inverse_lookback_days=(beta_override_bear_inverse_lookback_days),
            beta_override_bear_inverse_min_momentum_pct=(
                beta_override_bear_inverse_min_momentum_pct
            ),
            beta_override_bear_inverse_confirmation_sma_days=_optional_int_values(
                beta_override_bear_inverse_confirmation_sma_days
            ),
            beta_override_bear_inverse_weight=beta_override_bear_inverse_weight,
            beta_override_leadership_breadth_lookback_days=_optional_int_values(
                beta_override_leadership_breadth_lookback_days
            ),
            beta_override_min_leadership_breadth_count=_optional_int_values(
                beta_override_min_leadership_breadth_count
            ),
            beta_override_min_leadership_breadth_momentum_pct=(
                beta_override_min_leadership_breadth_momentum_pct
            ),
            beta_override_leadership_breadth_scale=beta_override_leadership_breadth_scale,
            beta_override_market_reentry_momentum_lookback_days=_optional_int_values(
                beta_override_market_reentry_momentum_lookback_days
            ),
            beta_override_min_market_reentry_momentum_pct=_optional_float_values(
                beta_override_min_market_reentry_momentum_pct
            ),
            beta_override_market_drawdown_brake_scale=brake_exposure_scale,
            out_of_sample_ratio=oos_ratio,
            walk_forward_folds=walk_forward_folds,
            walk_forward_top_k=walk_forward_top_k,
            max_candidates=max_candidates,
            refresh_data=refresh_data,
            objective=_hybrid_objective(objective),
        )
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    best = result.best
    console.print(f"[green]hybrid adaptive router complete[/green] report: {result.report_path}")
    console.print(
        f"best={best.params.label} "
        f"train_alpha_vs_tqqq_ann="
        f"{best.train.alpha_vs_benchmark_buy_hold_annualized_pct or 0.0:.2f}% "
        f"oos_alpha_vs_tqqq_ann="
        f"{best.out_of_sample.alpha_vs_benchmark_buy_hold_annualized_pct or 0.0:.2f}% "
        f"full_alpha_vs_tqqq_ann="
        f"{best.full_window.alpha_vs_benchmark_buy_hold_annualized_pct or 0.0:.2f}% "
        f"oos_ann={best.out_of_sample.annualized_return_pct or 0.0:.2f}% "
        f"oos_sharpe={best.out_of_sample.sharpe_ratio or 0.0:.2f} "
        f"flags={','.join(best.quality_flags) if best.quality_flags else 'none'}"
    )
    console.print(
        f"candidates={result.research_cost['candidate_count']} "
        f"walk_forward_candidates={result.research_cost['walk_forward_candidate_count']} "
        f"estimated_passes={result.research_cost['estimated_total_backtest_passes']} "
        f"runtime={result.runtime_seconds['total']:.2f}s"
    )


@strategy_app.command("wide-router-research")
def strategy_wide_router_research(
    spec: Path,
    symbols: str | None = typer.Option(None, "--symbols"),
    data_source: str = typer.Option("alpaca", "--data-source"),
    start: str | None = typer.Option(None, "--start"),
    end: str | None = typer.Option(None, "--end"),
    benchmark_symbol: str = typer.Option("TQQQ", "--benchmark-symbol"),
    market_symbol: str = typer.Option("QQQ", "--market-symbol"),
    refresh_data: bool = typer.Option(False, "--refresh-data/--use-cache"),
) -> None:
    """Run the formal wide NASDAQ daily hybrid-router research contract."""
    if data_source not in {"alpaca", "longbridge"}:
        raise typer.BadParameter("--data-source currently supports alpaca or longbridge")
    symbol_list = None
    if symbols:
        symbol_list = [item.strip().upper() for item in symbols.split(",") if item.strip()]
    try:
        result = run_wide_router_research(
            spec,
            project_root(),
            symbols=symbol_list,
            data_source=data_source,
            start=start,
            end=end,
            benchmark_symbol=benchmark_symbol.upper(),
            market_symbol=market_symbol.upper(),
            refresh_data=refresh_data,
        )
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    console.print(f"[green]wide router research complete[/green] report: {result.report_path}")
    console.print(
        f"route={result.selected_route_label} "
        f"research_pass={result.research_pass} paper_ready={result.paper_ready_pass}"
    )


@strategy_app.command("hybrid-news-marginal-lift")
def strategy_hybrid_news_marginal_lift(
    spec: Path,
    symbols: str = typer.Option(..., "--symbols"),
    data_source: str = typer.Option("alpaca", "--data-source"),
    feed: str | None = typer.Option(None, "--feed"),
    start: str | None = typer.Option(None, "--start"),
    end: str | None = typer.Option(None, "--end"),
    benchmark_symbol: str = typer.Option("TQQQ", "--benchmark-symbol"),
    market_symbol: str = typer.Option("QQQ", "--market-symbol"),
    selected_route_label: str | None = typer.Option(None, "--selected-route-label"),
    lookback_days: int = typer.Option(5, "--lookback-days"),
    sentiment_threshold: float = typer.Option(0.0, "--sentiment-threshold"),
    min_oos_lift_pct: float = typer.Option(1.0, "--min-oos-lift-pct"),
    oos_ratio: float = typer.Option(0.3, "--oos-ratio"),
    refresh_data: bool = typer.Option(False, "--refresh-data/--use-cache"),
) -> None:
    """Measure PIT news/LLM-style marginal lift for the selected hybrid route."""
    if data_source not in {"alpaca", "longbridge"}:
        raise typer.BadParameter("--data-source currently supports alpaca or longbridge")
    try:
        result = run_hybrid_news_marginal_lift_research(
            spec,
            project_root(),
            symbols=[item.strip().upper() for item in symbols.split(",") if item.strip()],
            data_source=data_source,
            feed=feed,
            start=start,
            end=end,
            benchmark_symbol=benchmark_symbol.upper(),
            market_symbol=market_symbol.upper(),
            selected_route_label=selected_route_label,
            lookback_days=lookback_days,
            sentiment_threshold=sentiment_threshold,
            min_oos_lift_pct=min_oos_lift_pct,
            out_of_sample_ratio=oos_ratio,
            refresh_data=refresh_data,
        )
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    console.print(f"[green]hybrid news marginal lift complete[/green] report: {result.report_path}")
    console.print(f"feature_packets={result.feature_packet_path}")
    console.print(
        f"baseline_oos_alpha_vs_tqqq_ann="
        f"{result.baseline.alpha_vs_benchmark_buy_hold_annualized_pct or 0.0:.2f}% "
        f"news_gated_oos_alpha_vs_tqqq_ann="
        f"{result.news_gated.alpha_vs_benchmark_buy_hold_annualized_pct or 0.0:.2f}% "
        f"lift={result.marginal_lift_alpha_annualized_pct or 0.0:.2f}% "
        f"llm_contribution_pass={result.llm_contribution_pass}"
    )


@strategy_app.command("hybrid-factor-attribution")
def strategy_hybrid_factor_attribution(
    spec: Path,
    symbols: str | None = typer.Option(None, "--symbols"),
    data_source: str = typer.Option("alpaca", "--data-source"),
    feed: str | None = typer.Option(None, "--feed"),
    start: str | None = typer.Option(None, "--start"),
    end: str | None = typer.Option(None, "--end"),
    benchmark_symbol: str = typer.Option("TQQQ", "--benchmark-symbol"),
    market_symbol: str = typer.Option("QQQ", "--market-symbol"),
    selected_route_label: str | None = typer.Option(None, "--selected-route-label"),
    refresh_data: bool = typer.Option(False, "--refresh-data/--use-cache"),
) -> None:
    """Run route-level factor attribution for the selected hybrid route."""
    if data_source not in {"alpaca", "longbridge"}:
        raise typer.BadParameter("--data-source currently supports alpaca or longbridge")
    try:
        result = run_hybrid_factor_attribution(
            spec,
            project_root(),
            symbols=(
                [item.strip().upper() for item in symbols.split(",") if item.strip()]
                if symbols
                else None
            ),
            data_source=data_source,
            feed=feed,
            start=start,
            end=end,
            benchmark_symbol=benchmark_symbol.upper(),
            market_symbol=market_symbol.upper(),
            selected_route_label=selected_route_label,
            refresh_data=refresh_data,
        )
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    console.print(f"[green]hybrid factor attribution complete[/green] report: {result.report_path}")
    console.print(
        f"route={result.selected_route_label} status={result.status} "
        f"blockers={','.join(result.blockers) if result.blockers else 'none'}"
    )


@strategy_app.command("beta-router-research")
def strategy_beta_router_research(
    spec: Path,
    data_source: str = typer.Option("alpaca", "--data-source"),
    start: str | None = typer.Option(None, "--start"),
    end: str | None = typer.Option(None, "--end"),
    market_symbol: str = typer.Option("QQQ", "--market-symbol"),
    leverage_symbol: str = typer.Option("TQQQ", "--leverage-symbol"),
    hedge_symbol: str | None = typer.Option("SQQQ", "--hedge-symbol"),
    trend_sma_days: Annotated[list[int] | None, typer.Option("--trend-sma-days")] = None,
    momentum_lookback_days: Annotated[
        list[int] | None,
        typer.Option("--momentum-lookback-days"),
    ] = None,
    min_momentum_pct: Annotated[
        list[float] | None,
        typer.Option("--min-momentum-pct"),
    ] = None,
    volatility_lookback_days: Annotated[
        list[int] | None,
        typer.Option("--volatility-lookback-days"),
    ] = None,
    max_volatility_annual_pct: Annotated[
        list[str] | None,
        typer.Option("--max-volatility-annual-pct"),
    ] = None,
    drawdown_lookback_days: Annotated[
        list[int] | None,
        typer.Option("--drawdown-lookback-days"),
    ] = None,
    max_drawdown_pct: Annotated[
        list[str] | None,
        typer.Option("--max-drawdown-pct"),
    ] = None,
    leverage_trend_sma_days: Annotated[
        list[str] | None,
        typer.Option("--leverage-trend-sma-days"),
    ] = None,
    max_leverage_volatility_annual_pct: Annotated[
        list[str] | None,
        typer.Option("--max-leverage-volatility-annual-pct"),
    ] = None,
    leverage_drawdown_lookback_days: Annotated[
        list[int] | None,
        typer.Option("--leverage-drawdown-lookback-days"),
    ] = None,
    max_leverage_drawdown_pct: Annotated[
        list[str] | None,
        typer.Option("--max-leverage-drawdown-pct"),
    ] = None,
    risk_on_symbol: Annotated[list[str] | None, typer.Option("--risk-on-symbol")] = None,
    risk_on_weight: Annotated[list[float] | None, typer.Option("--risk-on-weight")] = None,
    neutral_weight: Annotated[list[float] | None, typer.Option("--neutral-weight")] = None,
    risk_off_symbol: Annotated[list[str] | None, typer.Option("--risk-off-symbol")] = None,
    risk_off_weight: Annotated[list[float] | None, typer.Option("--risk-off-weight")] = None,
    target_volatility_annual_pct: Annotated[
        list[str] | None,
        typer.Option("--target-volatility-annual-pct"),
    ] = None,
    oos_ratio: float = typer.Option(0.35, "--oos-ratio"),
    walk_forward_folds: int = typer.Option(5, "--walk-forward-folds"),
    walk_forward_top_k: int | None = typer.Option(20, "--walk-forward-top-k"),
    max_candidates: int = typer.Option(600, "--max-candidates"),
    refresh_data: bool = typer.Option(False, "--refresh-data/--use-cache"),
) -> None:
    """Research a QQQ/TQQQ/cash beta target-weight router."""
    if data_source not in {"alpaca", "longbridge"}:
        raise typer.BadParameter("--data-source currently supports alpaca or longbridge")
    try:
        result = run_beta_exposure_router_research(
            spec,
            project_root(),
            data_source=data_source,
            start=start,
            end=end,
            market_symbol=market_symbol,
            leverage_symbol=leverage_symbol,
            hedge_symbol=None
            if hedge_symbol is not None and hedge_symbol.strip().lower() in {"", "none", "cash"}
            else hedge_symbol,
            trend_sma_days=trend_sma_days,
            momentum_lookback_days=momentum_lookback_days,
            min_momentum_pct=min_momentum_pct,
            volatility_lookback_days=volatility_lookback_days,
            max_volatility_annual_pct=_optional_float_values(max_volatility_annual_pct),
            drawdown_lookback_days=drawdown_lookback_days,
            max_drawdown_pct=_optional_float_values(max_drawdown_pct),
            leverage_trend_sma_days=_optional_int_values(leverage_trend_sma_days),
            max_leverage_volatility_annual_pct=_optional_float_values(
                max_leverage_volatility_annual_pct
            ),
            leverage_drawdown_lookback_days=leverage_drawdown_lookback_days,
            max_leverage_drawdown_pct=_optional_float_values(max_leverage_drawdown_pct),
            risk_on_symbol=risk_on_symbol,
            risk_on_weight=risk_on_weight,
            neutral_weight=neutral_weight,
            risk_off_symbol=risk_off_symbol,
            risk_off_weight=risk_off_weight,
            target_volatility_annual_pct=_optional_float_values(target_volatility_annual_pct),
            out_of_sample_ratio=oos_ratio,
            walk_forward_folds=walk_forward_folds,
            walk_forward_top_k=walk_forward_top_k,
            max_candidates=max_candidates,
            refresh_data=refresh_data,
        )
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    console.print(f"[green]beta router research complete[/green] report: {result.report_path}")
    console.print(
        f"selected={result.selected_route_label} "
        f"research_pass={result.research_pass} paper_ready={result.paper_ready_pass}"
    )


@strategy_app.command("core-satellite-router-research")
def strategy_core_satellite_router_research(
    spec: Path,
    data_source: str = typer.Option("alpaca", "--data-source"),
    start: str | None = typer.Option(None, "--start"),
    end: str | None = typer.Option(None, "--end"),
    satellite_symbol: Annotated[list[str] | None, typer.Option("--satellite-symbol")] = None,
    trend_sma_days: Annotated[list[int] | None, typer.Option("--trend-sma-days")] = None,
    momentum_lookback_days: Annotated[
        list[int] | None,
        typer.Option("--momentum-lookback-days"),
    ] = None,
    min_momentum_pct: Annotated[
        list[float] | None,
        typer.Option("--min-momentum-pct"),
    ] = None,
    volatility_lookback_days: Annotated[
        list[int] | None,
        typer.Option("--volatility-lookback-days"),
    ] = None,
    max_volatility_annual_pct: Annotated[
        list[str] | None,
        typer.Option("--max-volatility-annual-pct"),
    ] = None,
    drawdown_lookback_days: Annotated[
        list[int] | None,
        typer.Option("--drawdown-lookback-days"),
    ] = None,
    max_drawdown_pct: Annotated[
        list[str] | None,
        typer.Option("--max-drawdown-pct"),
    ] = None,
    core_weight: Annotated[list[float] | None, typer.Option("--core-weight")] = None,
    satellite_weight: Annotated[list[float] | None, typer.Option("--satellite-weight")] = None,
    risk_off_core_scale: Annotated[
        list[float] | None,
        typer.Option("--risk-off-core-scale"),
    ] = None,
    target_satellite_volatility_pct: Annotated[
        list[str] | None,
        typer.Option("--target-satellite-volatility-pct"),
    ] = None,
    rebalance_threshold_pct: Annotated[
        list[float] | None,
        typer.Option("--rebalance-threshold-pct"),
    ] = None,
    oos_ratio: float = typer.Option(0.35, "--oos-ratio"),
    walk_forward_folds: int = typer.Option(5, "--walk-forward-folds"),
    walk_forward_top_k: int | None = typer.Option(20, "--walk-forward-top-k"),
    max_candidates: int = typer.Option(900, "--max-candidates"),
    refresh_data: bool = typer.Option(False, "--refresh-data/--use-cache"),
) -> None:
    """Research a QQQ core plus bounded leveraged ETF satellite router."""
    if data_source not in {"alpaca", "longbridge"}:
        raise typer.BadParameter("--data-source currently supports alpaca or longbridge")
    try:
        result = run_core_satellite_router_research(
            spec,
            project_root(),
            data_source=data_source,
            start=start,
            end=end,
            satellite_symbols=satellite_symbol,
            trend_sma_days=trend_sma_days,
            momentum_lookback_days=momentum_lookback_days,
            min_momentum_pct=min_momentum_pct,
            volatility_lookback_days=volatility_lookback_days,
            max_volatility_annual_pct=_optional_float_values(max_volatility_annual_pct),
            drawdown_lookback_days=drawdown_lookback_days,
            max_drawdown_pct=_optional_float_values(max_drawdown_pct),
            core_weight=core_weight,
            satellite_weight=satellite_weight,
            risk_off_core_scale=risk_off_core_scale,
            target_satellite_volatility_pct=_optional_float_values(target_satellite_volatility_pct),
            rebalance_threshold_pct=rebalance_threshold_pct,
            out_of_sample_ratio=oos_ratio,
            walk_forward_folds=walk_forward_folds,
            walk_forward_top_k=walk_forward_top_k,
            max_candidates=max_candidates,
            refresh_data=refresh_data,
        )
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    console.print(f"[green]core satellite router complete[/green] report: {result.report_path}")
    console.print(
        f"selected={result.selected_route_label} "
        f"research_pass={result.research_pass} paper_ready={result.paper_ready_pass}"
    )


@strategy_app.command("core-beta-satellite-router-research")
def strategy_core_beta_satellite_router_research(
    spec: Path,
    symbols: str | None = typer.Option(None, "--symbols"),
    data_source: str = typer.Option("alpaca", "--data-source"),
    start: str | None = typer.Option(None, "--start"),
    end: str | None = typer.Option(None, "--end"),
    core_variant: Annotated[list[str] | None, typer.Option("--core-variant")] = None,
    universe_mode: Annotated[list[str] | None, typer.Option("--universe-mode")] = None,
    satellite_budget: Annotated[list[float] | None, typer.Option("--satellite-budget")] = None,
    satellite_momentum_days: Annotated[
        list[int] | None,
        typer.Option("--satellite-momentum-days"),
    ] = None,
    confirmation_days: Annotated[list[int] | None, typer.Option("--confirmation-days")] = None,
    top_n: Annotated[list[int] | None, typer.Option("--top-n")] = None,
    max_symbol_weight: Annotated[list[float] | None, typer.Option("--max-symbol-weight")] = None,
    score_mode: Annotated[list[str] | None, typer.Option("--score-mode")] = None,
    theme_gate_symbol: Annotated[list[str] | None, typer.Option("--theme-gate-symbol")] = None,
    theme_sma_days: Annotated[list[int] | None, typer.Option("--theme-sma-days")] = None,
    theme_momentum_days: Annotated[list[int] | None, typer.Option("--theme-momentum-days")] = None,
    min_theme_momentum_pct: Annotated[
        list[float] | None,
        typer.Option("--min-theme-momentum-pct"),
    ] = None,
    satellite_volatility_lookback_days: Annotated[
        list[int] | None,
        typer.Option("--satellite-volatility-lookback-days"),
    ] = None,
    target_satellite_volatility_pct: Annotated[
        list[str] | None,
        typer.Option("--target-satellite-volatility-pct"),
    ] = None,
    walk_forward_top_k: int | None = typer.Option(30, "--walk-forward-top-k"),
    max_candidates: int = typer.Option(700, "--max-candidates"),
    refresh_data: bool = typer.Option(False, "--refresh-data/--use-cache"),
) -> None:
    """Research a validated beta core plus bounded NASDAQ/theme satellite router."""
    if data_source not in {"alpaca", "longbridge"}:
        raise typer.BadParameter("--data-source currently supports alpaca or longbridge")
    universe = (
        [item.strip().upper() for item in symbols.split(",") if item.strip()] if symbols else None
    )
    try:
        result = run_core_beta_satellite_router_research(
            spec,
            project_root(),
            symbols=universe,
            data_source=data_source,
            start=start,
            end=end,
            core_variant=core_variant,
            universe_mode=universe_mode,
            satellite_budget=satellite_budget,
            satellite_momentum_days=satellite_momentum_days,
            confirmation_days=confirmation_days,
            top_n=top_n,
            max_symbol_weight=max_symbol_weight,
            score_mode=score_mode,
            theme_gate_symbol=theme_gate_symbol,
            theme_sma_days=theme_sma_days,
            theme_momentum_days=theme_momentum_days,
            min_theme_momentum_pct=min_theme_momentum_pct,
            satellite_volatility_lookback_days=satellite_volatility_lookback_days,
            target_satellite_volatility_pct=_optional_float_values(target_satellite_volatility_pct),
            walk_forward_top_k=walk_forward_top_k,
            max_candidates=max_candidates,
            refresh_data=refresh_data,
        )
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    console.print(
        f"[green]core beta satellite router complete[/green] report: {result.report_path}"
    )
    console.print(
        f"selected={result.selected_route_label} "
        f"research_pass={result.research_pass} paper_ready={result.paper_ready_pass}"
    )


@strategy_app.command("aggressive-theme-router-research")
def strategy_aggressive_theme_router_research(
    spec: Path,
    data_source: str = typer.Option("alpaca", "--data-source"),
    start: str | None = typer.Option(None, "--start"),
    end: str | None = typer.Option(None, "--end"),
    trend_sma_days: Annotated[list[int] | None, typer.Option("--trend-sma-days")] = None,
    momentum_lookback_days: Annotated[
        list[int] | None,
        typer.Option("--momentum-lookback-days"),
    ] = None,
    top_n: Annotated[list[int] | None, typer.Option("--top-n")] = None,
    min_theme_momentum_pct: Annotated[
        list[float] | None,
        typer.Option("--min-theme-momentum-pct"),
    ] = None,
    core_weight: Annotated[list[float] | None, typer.Option("--core-weight")] = None,
    theme_gross_weight: Annotated[
        list[float] | None,
        typer.Option("--theme-gross-weight"),
    ] = None,
    levered_symbol: Annotated[list[str] | None, typer.Option("--levered-symbol")] = None,
    levered_weight: Annotated[list[float] | None, typer.Option("--levered-weight")] = None,
    defensive_symbol: Annotated[list[str] | None, typer.Option("--defensive-symbol")] = None,
    defensive_weight: Annotated[list[float] | None, typer.Option("--defensive-weight")] = None,
    volatility_lookback_days: Annotated[
        list[int] | None,
        typer.Option("--volatility-lookback-days"),
    ] = None,
    target_portfolio_volatility_pct: Annotated[
        list[str] | None,
        typer.Option("--target-portfolio-volatility-pct"),
    ] = None,
    max_market_volatility_pct: Annotated[
        list[str] | None,
        typer.Option("--max-market-volatility-pct"),
    ] = None,
    drawdown_lookback_days: Annotated[
        list[int] | None,
        typer.Option("--drawdown-lookback-days"),
    ] = None,
    max_market_drawdown_pct: Annotated[
        list[str] | None,
        typer.Option("--max-market-drawdown-pct"),
    ] = None,
    rebalance_threshold_pct: Annotated[
        list[float] | None,
        typer.Option("--rebalance-threshold-pct"),
    ] = None,
    oos_ratio: float = typer.Option(0.35, "--oos-ratio"),
    walk_forward_folds: int = typer.Option(5, "--walk-forward-folds"),
    walk_forward_top_k: int | None = typer.Option(30, "--walk-forward-top-k"),
    max_candidates: int = typer.Option(1600, "--max-candidates"),
    refresh_data: bool = typer.Option(False, "--refresh-data/--use-cache"),
) -> None:
    """Research a theme-momentum router with bounded leveraged ETF satellite exposure."""
    if data_source not in {"alpaca", "longbridge"}:
        raise typer.BadParameter("--data-source currently supports alpaca or longbridge")
    try:
        result = run_aggressive_theme_router_research(
            spec,
            project_root(),
            data_source=data_source,
            start=start,
            end=end,
            trend_sma_days=trend_sma_days,
            momentum_lookback_days=momentum_lookback_days,
            top_n_values=top_n,
            min_theme_momentum_pct=min_theme_momentum_pct,
            core_weight=core_weight,
            theme_gross_weight=theme_gross_weight,
            levered_symbol=levered_symbol,
            levered_weight=levered_weight,
            defensive_symbol=defensive_symbol,
            defensive_weight=defensive_weight,
            volatility_lookback_days=volatility_lookback_days,
            target_portfolio_volatility_pct=_optional_float_values(target_portfolio_volatility_pct),
            max_market_volatility_pct=_optional_float_values(max_market_volatility_pct),
            drawdown_lookback_days=drawdown_lookback_days,
            max_market_drawdown_pct=_optional_float_values(max_market_drawdown_pct),
            rebalance_threshold_pct=rebalance_threshold_pct,
            out_of_sample_ratio=oos_ratio,
            walk_forward_folds=walk_forward_folds,
            walk_forward_top_k=walk_forward_top_k,
            max_candidates=max_candidates,
            refresh_data=refresh_data,
        )
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    console.print(f"[green]aggressive theme router complete[/green] report: {result.report_path}")
    console.print(
        f"selected={result.selected_route_label} "
        f"research_pass={result.research_pass} paper_ready={result.paper_ready_pass}"
    )


@strategy_app.command("theme-intraday-router-research")
def strategy_theme_intraday_router_research(
    spec: Path,
    symbols: str | None = typer.Option(None, "--symbols"),
    data_source: str = typer.Option("alpaca", "--data-source"),
    start: str | None = typer.Option(None, "--start"),
    end: str | None = typer.Option(None, "--end"),
    market_symbol: str = typer.Option("QQQ", "--market-symbol"),
    benchmark_symbol: str = typer.Option("TQQQ", "--benchmark-symbol"),
    market_sma_days: Annotated[list[int] | None, typer.Option("--market-sma-days")] = None,
    market_momentum_days: Annotated[
        list[int] | None,
        typer.Option("--market-momentum-days"),
    ] = None,
    min_market_momentum_pct: Annotated[
        list[float] | None,
        typer.Option("--min-market-momentum-pct"),
    ] = None,
    signal_momentum_days: Annotated[
        list[int] | None,
        typer.Option("--signal-momentum-days"),
    ] = None,
    confirmation_days: Annotated[list[int] | None, typer.Option("--confirmation-days")] = None,
    top_n: Annotated[list[int] | None, typer.Option("--top-n")] = None,
    beta_symbol: Annotated[list[str] | None, typer.Option("--beta-symbol")] = None,
    beta_weight: Annotated[list[float] | None, typer.Option("--beta-weight")] = None,
    satellite_weight: Annotated[list[float] | None, typer.Option("--satellite-weight")] = None,
    max_symbol_weight: Annotated[list[float] | None, typer.Option("--max-symbol-weight")] = None,
    market_below_sma_scale: Annotated[
        list[float] | None,
        typer.Option("--market-below-sma-scale"),
    ] = None,
    target_market_volatility_pct: Annotated[
        list[str] | None,
        typer.Option("--target-market-volatility-pct"),
    ] = None,
    drawdown_lookback_days: Annotated[
        list[int] | None,
        typer.Option("--drawdown-lookback-days"),
    ] = None,
    max_market_drawdown_pct: Annotated[
        list[str] | None,
        typer.Option("--max-market-drawdown-pct"),
    ] = None,
    score_mode: Annotated[list[str] | None, typer.Option("--score-mode")] = None,
    semiconductor_gate: Annotated[
        list[bool] | None,
        typer.Option("--semiconductor-gate/--no-semiconductor-gate"),
    ] = None,
    oos_ratio: float = typer.Option(0.3, "--oos-ratio"),
    walk_forward_folds: int = typer.Option(5, "--walk-forward-folds"),
    walk_forward_top_k: int | None = typer.Option(30, "--walk-forward-top-k"),
    max_candidates: int = typer.Option(900, "--max-candidates"),
    refresh_data: bool = typer.Option(False, "--refresh-data/--use-cache"),
) -> None:
    """Research a daily-scanned, same-session NASDAQ theme intraday router."""
    if data_source not in {"alpaca", "longbridge"}:
        raise typer.BadParameter("--data-source currently supports alpaca or longbridge")
    universe = (
        [item.strip().upper() for item in symbols.split(",") if item.strip()] if symbols else None
    )
    try:
        result = run_theme_intraday_rotation_router_research(
            spec,
            project_root(),
            symbols=universe,
            data_source=data_source,
            start=start,
            end=end,
            market_symbol=market_symbol.upper(),
            benchmark_symbol=benchmark_symbol.upper(),
            market_sma_days=market_sma_days,
            market_momentum_days=market_momentum_days,
            min_market_momentum_pct=min_market_momentum_pct,
            signal_momentum_days=signal_momentum_days,
            confirmation_days=confirmation_days,
            top_n=top_n,
            beta_symbol=beta_symbol,
            beta_weight=beta_weight,
            satellite_weight=satellite_weight,
            max_symbol_weight=max_symbol_weight,
            market_below_sma_scale=market_below_sma_scale,
            target_market_volatility_pct=_optional_float_values(target_market_volatility_pct),
            drawdown_lookback_days=drawdown_lookback_days,
            max_market_drawdown_pct=_optional_float_values(max_market_drawdown_pct),
            score_mode=score_mode,
            semiconductor_gate=semiconductor_gate,
            out_of_sample_ratio=oos_ratio,
            walk_forward_folds=walk_forward_folds,
            walk_forward_top_k=walk_forward_top_k,
            max_candidates=max_candidates,
            refresh_data=refresh_data,
        )
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    console.print(f"[green]theme intraday router complete[/green] report: {result.report_path}")
    console.print(
        f"selected={result.selected_route_label} "
        f"research_pass={result.research_pass} paper_ready={result.paper_ready_pass}"
    )


@strategy_app.command("hybrid-target-weights")
def strategy_hybrid_target_weights(
    spec: Path,
    symbols: str = typer.Option(..., "--symbols"),
    data_source: str = typer.Option("alpaca", "--data-source"),
    feed: str | None = typer.Option(None, "--feed"),
    start: str | None = typer.Option(None, "--start"),
    end: str | None = typer.Option(None, "--end"),
    benchmark_symbol: str = typer.Option("TQQQ", "--benchmark-symbol"),
    market_symbol: str = typer.Option("QQQ", "--market-symbol"),
    selected_route_label: str | None = typer.Option(None, "--selected-route-label"),
    refresh_data: bool = typer.Option(False, "--refresh-data/--use-cache"),
) -> None:
    """Map the selected hybrid route into Nautilus-compatible target weights."""
    if data_source not in {"alpaca", "longbridge"}:
        raise typer.BadParameter("--data-source currently supports alpaca or longbridge")
    try:
        result = run_hybrid_target_weight_mapping(
            spec,
            project_root(),
            symbols=[item.strip().upper() for item in symbols.split(",") if item.strip()],
            data_source=data_source,
            feed=feed,
            start=start,
            end=end,
            benchmark_symbol=benchmark_symbol.upper(),
            market_symbol=market_symbol.upper(),
            selected_route_label=selected_route_label,
            refresh_data=refresh_data,
        )
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    console.print(f"[green]hybrid target weights complete[/green] report: {result.report_path}")
    console.print(
        f"parity={result.parity_status} "
        f"rebalance_sessions={result.rebalance_sessions} "
        f"target_rows={result.target_weight_count} "
        f"nonzero_targets={result.nonzero_target_rows} "
        f"reference_round_trips={result.reference_metrics.round_trips}"
    )


@strategy_app.command("beta-target-weights")
def strategy_beta_target_weights(
    spec: Path,
    data_source: str = typer.Option("alpaca", "--data-source"),
    start: str | None = typer.Option(None, "--start"),
    end: str | None = typer.Option(None, "--end"),
    market_symbol: str = typer.Option("QQQ", "--market-symbol"),
    leverage_symbol: str = typer.Option("TQQQ", "--leverage-symbol"),
    hedge_symbol: str | None = typer.Option("SQQQ", "--hedge-symbol"),
    selected_route_label: str | None = typer.Option(None, "--selected-route-label"),
    refresh_data: bool = typer.Option(False, "--refresh-data/--use-cache"),
) -> None:
    """Map the selected beta exposure route into Nautilus-compatible target weights."""
    if data_source not in {"alpaca", "longbridge"}:
        raise typer.BadParameter("--data-source currently supports alpaca or longbridge")
    try:
        result = run_beta_target_weight_mapping(
            spec,
            project_root(),
            data_source=data_source,
            start=start,
            end=end,
            market_symbol=market_symbol.upper(),
            leverage_symbol=leverage_symbol.upper(),
            hedge_symbol=hedge_symbol.upper() if hedge_symbol else None,
            selected_route_label=selected_route_label,
            refresh_data=refresh_data,
        )
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    console.print(f"[green]beta target weights complete[/green] report: {result.report_path}")
    console.print(
        f"parity={result.parity_status} "
        f"rebalance_sessions={result.rebalance_sessions} "
        f"target_rows={result.target_weight_count} "
        f"nonzero_targets={result.nonzero_target_rows}"
    )


@strategy_app.command("target-weights")
def strategy_target_weights(
    spec: Path,
    symbols: str | None = typer.Option(None, "--symbols"),
    data_source: str = typer.Option("alpaca", "--data-source"),
    start: str | None = typer.Option(None, "--start"),
    end: str | None = typer.Option(None, "--end"),
    selected_route_label: str | None = typer.Option(None, "--selected-route-label"),
    refresh_data: bool = typer.Option(False, "--refresh-data/--use-cache"),
) -> None:
    """Generate router target weights, rebalance intents, and observation artifacts."""
    spec_obj = load_strategy_spec(spec)
    parsed_symbols = (
        [item.strip().upper() for item in symbols.split(",") if item.strip()] if symbols else None
    )
    try:
        if spec_obj.portfolio.mode == "adaptive_intraday_internal_router":
            result = run_adaptive_intraday_target_weight_mapping(
                spec,
                project_root(),
                symbols=parsed_symbols or spec_obj.universe,
                data_source=data_source,
                start=start,
                end=end,
                selected_route_label=selected_route_label,
                refresh_data=refresh_data,
            )
            status = result.parity_status
        elif spec_obj.portfolio.mode == "hybrid_adaptive_router":
            result = run_hybrid_target_weight_mapping(
                spec,
                project_root(),
                symbols=parsed_symbols or spec_obj.universe,
                data_source=data_source,
                start=start,
                end=end,
                selected_route_label=selected_route_label,
                refresh_data=refresh_data,
            )
            status = result.parity_status
        elif spec_obj.portfolio.mode == "beta_exposure_router":
            result = run_beta_target_weight_mapping(
                spec,
                project_root(),
                data_source=data_source,
                start=start,
                end=end,
                selected_route_label=selected_route_label,
                refresh_data=refresh_data,
            )
            status = result.parity_status
        elif spec_obj.portfolio.mode == "core_beta_satellite_router":
            result = run_core_beta_satellite_target_weight_mapping(
                spec,
                project_root(),
                symbols=parsed_symbols,
                data_source=data_source,
                start=start,
                end=end,
                selected_route_label=selected_route_label,
                refresh_data=refresh_data,
            )
            status = result.validation_status
        else:
            raise typer.BadParameter(
                f"strategy target-weights does not support portfolio.mode={spec_obj.portfolio.mode}"
            )
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    console.print(f"[green]target weights complete[/green] report: {result.report_path}")
    console.print(
        f"status={status} rebalance_sessions={result.rebalance_sessions} "
        f"target_rows={result.target_weight_count} nonzero_targets={result.nonzero_target_rows}"
    )


@strategy_app.command("shadow-observe")
def strategy_shadow_observe(
    spec: Path,
    as_of: str | None = typer.Option(None, "--as-of"),
) -> None:
    """Generate momentum target weights and review artifacts without broker I/O."""
    from datetime import datetime

    from open_composer.adapters.execution.momentum_shadow import (
        run_momentum_shadow_observation,
    )

    try:
        parsed_as_of = datetime.fromisoformat(as_of.replace("Z", "+00:00")) if as_of else None
        result = run_momentum_shadow_observation(spec, project_root(), as_of=parsed_as_of)
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    console.print(f"[green]shadow observation written[/green] status={result.status}")
    console.print(f"target weights: {result.target_weights_path}")
    console.print(f"review: {result.review_markdown_path}")
    console.print(f"forward ledger: {result.forward_ledger_path}")
    console.print(f"signals: {result.signal_count}")


@strategy_app.command("shadow-refresh-data")
def strategy_shadow_refresh_data(
    end: str | None = typer.Option(None, "--end"),
) -> None:
    """Strictly append Alpaca IEX QQQ/TQQQ data for the frozen shadow strategy."""
    from open_composer.research.momentum_data_refresh import refresh_momentum_research_data

    parsed_end = datetime.fromisoformat(end.replace("Z", "+00:00")) if end else None
    result = refresh_momentum_research_data(project_root(), end=parsed_end)
    console.print(f"momentum data refresh status={result.status} receipt={result.receipt_path}")
    if result.status != "ok":
        raise typer.Exit(code=1)


@strategy_app.command("shadow-cycle")
def strategy_shadow_cycle(
    spec: Path,
    as_of: str | None = typer.Option(None, "--as-of"),
    refresh: bool = typer.Option(False, "--refresh"),
    dry_run: bool = typer.Option(False, "--dry-run"),
) -> None:
    """Run one idempotent, broker-free momentum observation slot."""
    from open_composer.research.momentum_observation_cycle import (
        run_momentum_observation_cycle,
    )

    parsed_as_of = datetime.fromisoformat(as_of.replace("Z", "+00:00")) if as_of else None
    result = run_momentum_observation_cycle(
        spec,
        project_root(),
        as_of=parsed_as_of,
        refresh=refresh,
        dry_run=dry_run,
    )
    console.print(f"momentum shadow cycle status={result.status} receipt={result.receipt_path}")


@strategy_app.command("shadow-ml-preflight")
def strategy_shadow_ml_preflight(
    spec: Path,
    search_combinations: int = typer.Option(12, "--search-combinations"),
    purge_bars: int = typer.Option(72, "--purge-bars"),
    embargo_bars: int = typer.Option(72, "--embargo-bars"),
) -> None:
    """Evaluate advisory ML challenger eligibility without training a model."""
    from open_composer.research.momentum_ml_challenger import (
        evaluate_momentum_ml_eligibility,
    )

    root = project_root()
    ledger = root / "reports/shadow" / spec.stem / "forward-decisions.jsonl"
    output = root / "reports/shadow" / spec.stem / "ml-eligibility.json"
    try:
        result = evaluate_momentum_ml_eligibility(
            ledger,
            output,
            spec_path=spec,
            search_combinations=search_combinations,
            purge_bars=purge_bars,
            embargo_bars=embargo_bars,
        )
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    console.print(f"momentum ML preflight status={result.status} report={result.path}")


@strategy_app.command("shadow-status")
def strategy_shadow_status(spec: Path) -> None:
    """Write the consolidated momentum product, shadow, paper, and ML status."""
    from open_composer.research.momentum_ml_challenger import write_momentum_product_status

    root = project_root()
    base = root / "reports/shadow" / spec.stem
    output = base / "final-status.json"
    payload = write_momentum_product_status(
        base / "readiness.json", base / "ml-eligibility.json", output
    )
    console.print(
        f"product_complete={payload['product_capability_complete']} "
        f"shadow={payload['shadow_status']} ml_eligible={payload['ml_eligible']} "
        f"paper_authorized={payload['paper_authorized']} report={output}"
    )


@strategy_app.command("shadow-resolve-remediation")
def strategy_shadow_resolve_remediation(
    spec: Path,
    evidence: Annotated[Path, typer.Option("--evidence")],
    slot: str = typer.Option(..., "--slot"),
    resolved_by: str = typer.Option(..., "--resolved-by"),
    reason: str = typer.Option(..., "--reason"),
) -> None:
    """Resolve a blocked shadow slot with identity, reason, and hashed evidence."""
    from open_composer.research.momentum_observation_cycle import (
        resolve_momentum_remediation,
    )

    try:
        path = resolve_momentum_remediation(
            project_root(),
            spec.stem,
            slot,
            resolved_by=resolved_by,
            reason=reason,
            evidence_path=evidence,
        )
    except (FileNotFoundError, ValueError) as exc:
        raise typer.BadParameter(str(exc)) from exc
    console.print(f"momentum remediation resolved: {path}")


@strategy_app.command("router-attribution")
def strategy_router_attribution(
    spec: Annotated[Path, typer.Option("--spec")] = PDR_ATTRIBUTION_DEFAULT_SPEC_PATH,
    label: str | None = typer.Option(None, "--label"),
    data_source: str = typer.Option("longbridge", "--data-source"),
    feed: str | None = typer.Option(None, "--feed"),
    start: str = typer.Option(PDR_ATTRIBUTION_DEFAULT_START, "--start"),
    end: str = typer.Option(PDR_ATTRIBUTION_DEFAULT_END, "--end"),
    folds: str | None = typer.Option(
        None,
        "--folds",
        help="Comma-separated name:start:end windows; defaults to the six long-window folds.",
    ),
    out_dir: Annotated[Path, typer.Option("--out-dir")] = PDR_ATTRIBUTION_DEFAULT_OUT_DIR,
    date_tag: str = typer.Option(PDR_ATTRIBUTION_DEFAULT_DATE_TAG, "--date-tag"),
) -> None:
    """Attribute PDR router state and asset contributions by fold."""
    if data_source not in {"longbridge", "alpaca", "sample"}:
        raise typer.BadParameter("--data-source supports longbridge, alpaca, or sample")
    try:
        payload = run_pdr_router_attribution(
            spec,
            root=project_root(),
            label=label,
            data_source=data_source,
            feed=feed,
            start=start,
            end=end,
            folds=parse_fold_windows(folds),
            out_dir=out_dir,
            date_tag=date_tag,
        )
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    console.print(
        f"[green]router attribution complete[/green] json={payload['artifact_paths']['json']}"
    )
    console.print(
        f"markdown={payload['artifact_paths']['markdown']} "
        f"golden={payload['artifact_paths']['golden_daily_decisions']}"
    )


@strategy_app.command("router-gate-eval")
def strategy_router_gate_eval(
    spec: Annotated[Path, typer.Option("--spec")] = PDR_ML_GATE_DEFAULT_SPEC_PATH,
    data_source: str = typer.Option("longbridge", "--data-source"),
    feed: str | None = typer.Option(None, "--feed"),
    start: str = typer.Option(PDR_ML_GATE_DEFAULT_START, "--start"),
    end: str = typer.Option(PDR_ML_GATE_DEFAULT_END, "--end"),
    report_date: str | None = typer.Option(None, "--report-date"),
    output_dir: Annotated[Path | None, typer.Option("--output-dir")] = None,
) -> None:
    """Evaluate baseline vs PDR ML-gated route on the same dataset."""
    if data_source not in {"longbridge", "alpaca", "sample"}:
        raise typer.BadParameter("--data-source supports longbridge, alpaca, or sample")
    payload = evaluate_pdr_router_ml_gate(
        spec if spec.is_absolute() else project_root() / spec,
        root=project_root(),
        data_source=data_source,
        feed=feed,
        start=start,
        end=end,
        report_date=report_date,
        output_dir=output_dir,
    )
    accepted = payload["acceptance_gate"]["ml_gate_beats_fixed_route"]
    console.print(
        f"[green]router gate eval written[/green] accepted={accepted} "
        f"json={payload['artifact_paths']['json']}"
    )
    console.print(f"markdown={payload['artifact_paths']['markdown']}")
    if not accepted:
        raise typer.Exit(1)


@strategy_app.command("route-cross-source-validation")
def strategy_route_cross_source_validation(
    spec: Annotated[Path, typer.Option("--spec")] = ROUTE_CROSS_SOURCE_DEFAULT_SPEC_PATH,
    alt_source: str = typer.Option(ROUTE_CROSS_SOURCE_DEFAULT_ALT_SOURCE, "--alt-source"),
    alt_feed: str | None = typer.Option(ROUTE_CROSS_SOURCE_DEFAULT_ALT_FEED, "--alt-feed"),
    alt_dir: Annotated[Path, typer.Option("--alt-dir")] = ROUTE_CROSS_SOURCE_DEFAULT_ALT_DIR,
    start: str = typer.Option(ROUTE_CROSS_SOURCE_DEFAULT_START, "--start"),
    end: str = typer.Option(ROUTE_CROSS_SOURCE_DEFAULT_END, "--end"),
    report_date: str = typer.Option(
        ROUTE_CROSS_SOURCE_DEFAULT_REPORT_DATE,
        "--report-date",
    ),
    output_dir: Annotated[Path, typer.Option("--output-dir")] = ROUTE_CROSS_SOURCE_DEFAULT_OUT_DIR,
) -> None:
    """Replay the fixed PDR route on primary and alternate daily sources."""
    try:
        verify_longbridge_research_cache_manifest(project_root())
        payload = evaluate_route_cross_source_validation(
            root=project_root(),
            spec_path=spec,
            alt_source=alt_source,
            alt_feed=alt_feed,
            alt_dir=alt_dir,
            start=start,
            end=end,
            report_date=report_date,
            out_dir=output_dir,
        )
    except (FileNotFoundError, ValueError, KeyError, json.JSONDecodeError) as exc:
        raise typer.BadParameter(str(exc)) from exc
    console.print(
        f"[green]route cross-source validation written[/green] "
        f"status={payload['status']} pass={payload['route_cross_source_pass']}"
    )
    console.print(f"json={payload['artifact_paths']['json']}")
    console.print(f"markdown={payload['artifact_paths']['markdown']}")


@strategy_app.command("router-replay-audit")
def strategy_router_replay_audit(
    spec: Annotated[Path, typer.Option("--spec")] = PDR_ATTRIBUTION_DEFAULT_SPEC_PATH,
    baseline: Annotated[
        Path,
        typer.Option("--baseline", help="Baseline PDR fold attribution JSON."),
    ] = ROUTER_REPLAY_AUDIT_DEFAULT_BASELINE,
    report_date: str = typer.Option(ROUTER_REPLAY_AUDIT_DEFAULT_DATE, "--report-date"),
    output_dir: Annotated[Path, typer.Option("--output-dir")] = ROUTER_REPLAY_AUDIT_DEFAULT_OUT_DIR,
    start: str = typer.Option(PDR_ATTRIBUTION_DEFAULT_START, "--start"),
    end: str = typer.Option(PDR_ATTRIBUTION_DEFAULT_END, "--end"),
) -> None:
    """Replay the fixed PDR route on the current research cache and compare baseline."""
    try:
        payload = run_router_replay_audit(
            root=project_root(),
            spec_path=spec,
            baseline_path=baseline,
            report_date=report_date,
            out_dir=output_dir,
            start=start,
            end=end,
        )
    except (FileNotFoundError, ValueError, KeyError, json.JSONDecodeError) as exc:
        raise typer.BadParameter(str(exc)) from exc
    console.print(
        f"[green]router replay audit written[/green] "
        f"status={payload['status']} json={payload['artifact_paths']['json']}"
    )
    console.print(f"markdown={payload['artifact_paths']['markdown']}")
    if payload["status"] == "drift":
        raise typer.Exit(1)


@strategy_app.command("router-cost-stress")
def strategy_router_cost_stress(spec: Path) -> None:
    """Print the router cost-stress artifact path for a generated target-weight run."""
    spec_obj = load_strategy_spec(spec)
    path = project_root() / "reports" / "research" / f"{spec_obj.name}-router-cost-stress.json"
    if not path.exists():
        raise typer.BadParameter("router cost stress missing; run oc strategy target-weights first")
    console.print(f"router cost stress: {path}")


@strategy_app.command("data-evidence")
def strategy_data_evidence(spec: Path) -> None:
    """Print the router data-evidence artifact path for a generated target-weight run."""
    spec_obj = load_strategy_spec(spec)
    path = project_root() / "reports" / "research" / f"{spec_obj.name}-router-data-evidence.json"
    if not path.exists():
        raise typer.BadParameter(
            "router data evidence missing; run oc strategy target-weights first"
        )
    console.print(f"router data evidence: {path}")


@strategy_app.command("alt-data-evidence")
def strategy_alt_data_evidence(spec: Path) -> None:
    """Generate PIT replay, marginal lift, and robustness shells for alternative data."""
    result = build_alternative_data_evidence(spec, project_root())
    console.print(f"[green]alternative data evidence complete[/green] report: {result.report_path}")
    console.print(
        f"status={result.status} advisory_only={result.advisory_only} pit={result.pit_replay_path}"
    )


@strategy_app.command("short-risk")
def strategy_short_risk(spec: Path) -> None:
    """Generate short-selling borrow, squeeze, dividend, and exposure artifacts."""
    try:
        result = build_short_risk_report(spec, project_root())
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    console.print(f"[green]short risk complete[/green] report: {result.report_path}")
    console.print(f"status={result.status} exposure_policy={result.exposure_policy_path}")


@strategy_app.command("hybrid-paper-plan")
def strategy_hybrid_paper_plan(spec: Path) -> None:
    """Build a paper_auto candidate plan without activating or submitting orders."""
    result = build_hybrid_paper_plan(spec, project_root())
    console.print(f"[green]hybrid paper plan complete[/green] report: {result.report_path}")
    console.print(
        f"candidate={result.candidate_spec_path} readiness={result.status} ready={result.ready}"
    )


def _hybrid_objective(value: str) -> str:
    normalized = value.strip().lower().replace("_", "-")
    if normalized == "benchmark-buy-hold-alpha":
        return "benchmark_buy_hold_alpha"
    if normalized == "risk-adjusted-benchmark-alpha":
        return "risk_adjusted_benchmark_alpha"
    if normalized == "absolute-return-risk":
        return "absolute_return_risk"
    raise typer.BadParameter(
        "--objective must be benchmark-buy-hold-alpha, risk-adjusted-benchmark-alpha, "
        "or absolute-return-risk"
    )


def _hybrid_holding_modes(values: list[str] | None) -> list[str] | None:
    if not values:
        return None
    allowed = {"open_to_open", "open_to_close"}
    normalized = [item.strip().lower().replace("-", "_") for item in values if item.strip()]
    bad = [item for item in normalized if item not in allowed]
    if bad:
        raise typer.BadParameter("--holding-mode contains unsupported value(s): " + ", ".join(bad))
    return normalized


def _hybrid_momentum_score_modes(values: list[str] | None) -> list[str] | None:
    if not values:
        return None
    aliases = {
        "raw": "raw",
        "risk-adjusted": "risk_adjusted",
        "risk_adjusted": "risk_adjusted",
        "radj": "risk_adjusted",
    }
    normalized = [aliases.get(item.strip().lower().replace("_", "-")) for item in values]
    bad = [value for value, parsed in zip(values, normalized, strict=True) if parsed is None]
    if bad:
        raise typer.BadParameter(
            "--momentum-score-mode contains unsupported value(s): " + ", ".join(bad)
        )
    return [item for item in normalized if item is not None]


def _hybrid_market_sma_days(values: list[str] | None) -> list[int | None] | None:
    if not values:
        return None
    parsed: list[int | None] = []
    for value in values:
        normalized = value.strip().lower()
        if normalized in {"none", "off", "0"}:
            parsed.append(None)
        else:
            parsed.append(int(normalized))
    return parsed


def _hybrid_beta_override_base_modes(values: list[str] | None) -> list[str] | None:
    if not values:
        return None
    allowed = {"iter2", "tqqq_cycle", "tqqq_always"}
    normalized = [item.strip().lower().replace("-", "_") for item in values if item.strip()]
    bad = [item for item in normalized if item not in allowed]
    if bad:
        raise typer.BadParameter(
            "--beta-override-base-mode contains unsupported value(s): " + ", ".join(bad)
        )
    return normalized


def _hybrid_beta_override_cycle_gates(values: list[str] | None) -> list[str] | None:
    if not values:
        return None
    allowed = {"none", "q200", "mom120", "q200ormom120", "q200andmom120"}
    normalized = [item.strip().lower().replace("-", "") for item in values if item.strip()]
    bad = [item for item in normalized if item not in allowed]
    if bad:
        raise typer.BadParameter(
            "--beta-override-cycle-gate contains unsupported value(s): " + ", ".join(bad)
        )
    return normalized


def _intraday_objective(value: str) -> str:
    normalized = value.strip().lower().replace("_", "-")
    if normalized == "equal-weight-alpha":
        return "equal_weight_alpha"
    if normalized == "benchmark-intraday-alpha":
        return "benchmark_intraday_alpha"
    raise typer.BadParameter("--objective must be equal-weight-alpha or benchmark-intraday-alpha")


def _intraday_market_gates(values: list[str] | None) -> list[str] | None:
    if not values:
        return None
    allowed = {
        "none",
        "qqq_open_negative",
        "qqq_open_positive",
        "qqq_prior_negative",
        "qqq_prior_positive",
        "qqq_open_and_prior_positive",
        "qqq_open_positive_prior_negative",
    }
    normalized = [item.strip().lower().replace("-", "_") for item in values if item.strip()]
    bad = [item for item in normalized if item not in allowed]
    if bad:
        raise typer.BadParameter("--market-gate contains unsupported value(s): " + ", ".join(bad))
    return normalized


def _intraday_selection_styles(values: list[str] | None) -> list[str] | None:
    if not values:
        return None
    allowed = {"opening_momentum", "opening_reversal"}
    normalized = [item.strip().lower().replace("-", "_") for item in values if item.strip()]
    bad = [item for item in normalized if item not in allowed]
    if bad:
        raise typer.BadParameter(
            "--selection-style contains unsupported value(s): " + ", ".join(bad)
        )
    return normalized


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
    try:
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
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
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


def _optional_int_values(values: list[str] | None) -> list[int | None] | None:
    if values is None:
        return None
    parsed: list[int | None] = []
    for value in values:
        normalized = value.strip().lower()
        if normalized in {"none", "null", "off", "0"}:
            parsed.append(None)
        else:
            parsed.append(int(value))
    return parsed


def _optional_symbol_values(values: list[str] | None) -> list[str | None] | None:
    if values is None:
        return None
    parsed: list[str | None] = []
    for value in values:
        normalized = value.strip().lower()
        if normalized in {"none", "null", "off", ""}:
            parsed.append(None)
        else:
            parsed.append(value.strip().upper())
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


@strategy_app.command("advance")
def strategy_advance(
    spec: Path,
    apply: Annotated[
        bool,
        typer.Option("--apply", help="Write the run record to the harness JSONL log."),
    ] = False,
    stage: Annotated[
        str,
        typer.Option("--stage", help="Lifecycle stage to check gates for."),
    ] = "research",
) -> None:
    """Check harness gates for a strategy at a given lifecycle stage.

    Use --apply to record the gate run to reports/research/harness-runs.jsonl.
    """
    from open_composer.harness.runs import append_run
    from open_composer.harness.stages import check_stage
    from open_composer.models.strategy_spec import load_strategy_spec
    from open_composer.strategy_versions import strategy_content_hash

    root = project_root()
    status, results = check_stage(stage, spec, root)
    spec_obj = load_strategy_spec(spec)
    spec_hash = strategy_content_hash(spec_obj)

    for result in results:
        color = "yellow" if result.status == "warning" else "red"
        icon = (
            "[green]ok[/green]" if result.status == "ok" else f"[{color}]{result.status}[/{color}]"
        )
        console.print(f"  {icon} {result.name}: {result.message}")

    if apply:
        log_path = append_run(
            strategy_name=spec_obj.name,
            spec_hash=spec_hash,
            stage=stage,
            results=results,
            root=root,
        )
        console.print(f"[green]run recorded[/green] log={log_path}")

    agg_color = "yellow" if status == "warning" else "red"
    aggregate_icon = (
        "[green]ok[/green]" if status == "ok" else f"[{agg_color}]{status}[/{agg_color}]"
    )
    console.print(f"\nstage={stage!r} status={aggregate_icon}")
    if status == "blocked":
        raise typer.Exit(code=1)


@strategy_app.command("diff")
def strategy_diff(
    spec: Path,
    vs: Annotated[
        str,
        typer.Option("--vs", help="Content hash of the spec version to compare against."),
    ],
) -> None:
    """Diff the current spec against a previously recorded version hash."""
    from open_composer.harness.diff import spec_diff

    result = spec_diff(spec, vs, root=project_root())
    console.print(f"current_hash : {result['current_hash']}")
    console.print(f"vs_hash      : {result['vs_hash']}")
    console.print(f"found        : {result['found']}")
    if not result["found"]:
        console.print(f"[yellow]{result['summary']}[/yellow]")
        return
    if result["changed_fields"]:
        console.print(f"changed      : {', '.join(result['changed_fields'])}")
        for field, delta in result["diff"].items():
            console.print(f"  {field}:")
            console.print(f"    before: {delta['before']!r}")
            console.print(f"    after : {delta['after']!r}")
    else:
        console.print("[green]no changes detected[/green]")
    console.print(f"\nsummary: {result['summary']}")


@strategy_app.command("research-workflow", hidden=True)
def strategy_research_workflow(
    spec: Path,
    stage: Annotated[
        str,
        typer.Option("--stage", help="Harness stage to check after research artifacts are built."),
    ] = "promotion",
    record: Annotated[
        bool,
        typer.Option(
            "--record/--no-record",
            help="Append the workflow gate result to reports/research/harness-runs.jsonl.",
        ),
    ] = True,
) -> None:
    """[DEPRECATED] Use `oc strategy evidence`."""
    _ = stage, record
    console.print("[yellow][DEPRECATED][/yellow] Use `oc strategy evidence`.")
    _print_strategy_evidence(spec)


@harness_app.command("check")
def harness_check(
    spec: Path,
    stage: Annotated[
        str,
        typer.Option("--stage", help="Lifecycle stage to check gates for (default: research)."),
    ] = "research",
    record: Annotated[
        bool,
        typer.Option("--record", help="Append the run to the harness JSONL evidence log."),
    ] = False,
) -> None:
    """Run harness gates for a StrategySpec at a given lifecycle stage.

    Exits with code 1 if any gate is blocked. Use --record to persist the result.
    """
    from open_composer.harness.runs import append_run
    from open_composer.harness.stages import check_stage
    from open_composer.models.strategy_spec import load_strategy_spec
    from open_composer.strategy_versions import strategy_content_hash

    root = project_root()
    try:
        status, results = check_stage(stage, spec, root)
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc

    spec_obj = load_strategy_spec(spec)
    spec_hash = strategy_content_hash(spec_obj)

    console.print(
        f"[bold]harness check[/bold] "
        f"strategy={spec_obj.name!r} stage={stage!r} hash={spec_hash[:12]}"
    )
    console.print("")
    for result in results:
        if result.status == "ok":
            icon = "[green]✓[/green]"
        elif result.status == "warning":
            icon = "[yellow]![/yellow]"
        else:
            icon = "[red]✗[/red]"
        console.print(f"  {icon} {result.name}: {result.message}")

    if record:
        log_path = append_run(
            strategy_name=spec_obj.name,
            spec_hash=spec_hash,
            stage=stage,
            results=results,
            root=root,
        )
        console.print(f"\n[green]recorded[/green] log={log_path}")

    console.print(f"\nstatus: {status}")
    if status == "blocked":
        raise typer.Exit(code=1)


@harness_app.command("plan")
def harness_plan(
    spec: Path,
    output: Annotated[
        bool,
        typer.Option(
            "--output/--no-output", help="Write JSON+Markdown plan to reports/harness/plans/."
        ),
    ] = True,
) -> None:
    """Detect risk domains and required skills/artifacts for a StrategySpec.

    Reads harness/risk_domains.yaml and harness/skill_manifest.yaml — no backtest runs.
    Writes reports/harness/plans/{strategy}.json and .md when --output is set.
    """
    import json

    from open_composer.harness.policy import (
        blocking_rules_for_domains,
        detect_risk_domains,
        required_artifacts_for_domains,
        required_skills_for_domains,
    )
    from open_composer.models.strategy_spec import load_strategy_spec

    root = project_root()
    spec_obj = load_strategy_spec(spec)
    active_domains = detect_risk_domains(spec_obj, root)
    artifacts = sorted(required_artifacts_for_domains(active_domains))
    skills = sorted(required_skills_for_domains(active_domains))
    rules = blocking_rules_for_domains(active_domains)

    console.print(f"[bold]harness plan[/bold] strategy={spec_obj.name!r}")
    console.print("")

    if active_domains:
        console.print("[bold]Risk domains detected:[/bold]")
        for d in active_domains:
            console.print(f"  • {d}")
    else:
        console.print("[dim]No risk domains detected (deterministic, non-paper strategy).[/dim]")

    if skills:
        console.print("\n[bold]Required skills:[/bold]")
        for s in skills:
            console.print(f"  • {s}")

    if artifacts:
        console.print("\n[bold]Required artifacts:[/bold]")
        for a in artifacts:
            console.print(f"  • {a}")

    if rules:
        console.print("\n[bold]Blocking rules:[/bold]")
        for r in rules:
            console.print(f"  • [{r.blocks}] {r.rule_id}")

    plan = {
        "strategy_name": spec_obj.name,
        "spec_path": str(spec),
        "risk_domains": active_domains,
        "required_skills": skills,
        "required_artifacts": artifacts,
        "blocking_rules": [
            {
                "domain": r.domain_id,
                "rule_id": r.rule_id,
                "blocks": r.blocks,
                "description": r.description,
            }
            for r in rules
        ],
    }

    if output:
        import datetime

        plans_dir = root / "reports" / "harness" / "plans"
        plans_dir.mkdir(parents=True, exist_ok=True)
        json_path = plans_dir / f"{spec_obj.name}.json"
        md_path = plans_dir / f"{spec_obj.name}.md"

        json_path.write_text(json.dumps(plan, indent=2))

        domain_lines = [f"- {d}" for d in active_domains] or ["- (none)"]
        skill_lines = [f"- {s}" for s in skills] or ["- (none)"]
        artifact_lines = [f"- {a}" for a in artifacts] or ["- (none)"]
        rule_lines = [
            f"- **{r.rule_id}** (blocks `{r.blocks}`): {r.description}" for r in rules
        ] or ["- (none)"]
        md_lines = [
            f"# Harness Plan — {spec_obj.name}",
            f"\nGenerated: {datetime.date.today()}",
            "\n## Risk Domains\n",
            *domain_lines,
            "\n## Required Skills\n",
            *skill_lines,
            "\n## Required Artifacts\n",
            *artifact_lines,
            "\n## Blocking Rules\n",
            *rule_lines,
        ]
        md_path.write_text("\n".join(md_lines) + "\n")

        console.print(f"\n[green]plan written[/green] {json_path.relative_to(root)}")


@harness_app.command("verify")
def harness_verify(
    spec: Path,
    stage: Annotated[
        str,
        typer.Option("--stage", help="Lifecycle stage context (default: research)."),
    ] = "research",
) -> None:
    """Verify that all required harness artifacts exist and are structurally complete.

    Reads harness/risk_domains.yaml and harness/artifact_contracts.yaml.
    Exits with code 1 when any required artifact is missing or fails schema check.
    Writes reports/harness/verify/{strategy}.json.
    """
    import json

    from open_composer.harness.policy import (
        check_artifact,
        detect_risk_domains,
        required_artifacts_for_domains,
    )
    from open_composer.models.strategy_spec import load_strategy_spec

    root = project_root()
    spec_obj = load_strategy_spec(spec)
    active_domains = detect_risk_domains(spec_obj, root)
    required = sorted(required_artifacts_for_domains(active_domains))

    console.print(f"[bold]harness verify[/bold] strategy={spec_obj.name!r} stage={stage!r}")
    console.print("")

    statuses = [check_artifact(a, spec_obj.name, root) for a in required]
    blocked = [s for s in statuses if not s.present or not s.schema_ok]
    warnings: list = []

    for s in statuses:
        if not s.present:
            icon = "[red]✗[/red]"
            detail = "missing"
        elif not s.schema_ok:
            icon = "[yellow]![/yellow]"
            detail = f"missing fields: {', '.join(s.missing_fields)}"
        else:
            icon = "[green]✓[/green]"
            detail = "ok"
        console.print(f"  {icon} {s.name}: {detail}")

    overall = "blocked" if blocked else "warning" if warnings else "ok"
    console.print(f"\nstatus: {overall}")

    verify_dir = root / "reports" / "harness" / "verify"
    verify_dir.mkdir(parents=True, exist_ok=True)
    result = {
        "strategy_name": spec_obj.name,
        "stage": stage,
        "risk_domains": active_domains,
        "required_artifacts": required,
        "artifacts": [
            {
                "name": s.name,
                "present": s.present,
                "schema_ok": s.schema_ok,
                "missing_fields": s.missing_fields,
                "path": str(s.path),
            }
            for s in statuses
        ],
        "overall": overall,
    }
    out_path = verify_dir / f"{spec_obj.name}.json"
    out_path.write_text(json.dumps(result, indent=2))
    console.print(f"[green]verify written[/green] {out_path.relative_to(root)}")

    if overall == "blocked":
        raise typer.Exit(code=1)


@harness_app.command("curate")
def harness_curate(
    strategy: Annotated[
        str | None,
        typer.Option("--strategy", help="Limit curation to one strategy by name."),
    ] = None,
    output: Annotated[
        bool,
        typer.Option(
            "--output/--no-output", help="Write curation report to reports/harness/curation/."
        ),
    ] = True,
) -> None:
    """Audit source cards: flag stale, duplicate, unverified, or expired records.

    Reads every ``reports/harness/source_cards/*.jsonl`` (or just one strategy
    with --strategy), evaluates each card against
    ``harness/source_policy.yaml`` staleness rules, and prints a tabular
    summary. Writes a dated markdown report under
    ``reports/harness/curation/`` so the evidence-curator skill has a baseline.
    """
    import datetime as _dt
    import json as _json

    from open_composer.models.source_card import evaluate_source_cards

    root = project_root()
    cards_dir = root / "reports" / "harness" / "source_cards"

    if strategy:
        strategy_names = [strategy]
    elif cards_dir.exists():
        strategy_names = sorted(p.stem for p in cards_dir.glob("*.jsonl"))
    else:
        strategy_names = []

    if not strategy_names:
        console.print("[dim]No source cards found.[/dim]")
        return

    today = _dt.date.today()
    rows: list[dict[str, object]] = []
    url_index: dict[str, list[tuple[str, str]]] = {}

    for name in strategy_names:
        try:
            statuses = evaluate_source_cards(name, root, today=today)
        except ValueError as exc:
            console.print(f"[red]{name}[/red]: {exc}")
            continue
        for status in statuses:
            card = status.card
            rows.append(
                {
                    "strategy": name,
                    "claim_id": card.claim_id,
                    "source_type": card.source_type,
                    "accessed_at": card.accessed_at,
                    "age_days": status.age_days,
                    "stale": status.stale,
                    "expired": status.expired,
                    "url": card.source_url,
                }
            )
            url_index.setdefault(card.source_url, []).append((name, card.claim_id))

    total = len(rows)
    stale = [r for r in rows if r["stale"]]
    expired = [r for r in rows if r["expired"]]
    unverified = [r for r in rows if r["source_type"] == "unverified"]
    duplicates = {url: refs for url, refs in url_index.items() if len({n for n, _ in refs}) > 1}

    table = Table(title="Source Card Curation")
    table.add_column("Strategy")
    table.add_column("Claim ID")
    table.add_column("Source Type")
    table.add_column("Accessed")
    table.add_column("Age (d)")
    table.add_column("Flags")
    for row in rows:
        flags = []
        if row["expired"]:
            flags.append("expired")
        elif row["stale"]:
            flags.append("stale")
        if row["source_type"] == "unverified":
            flags.append("unverified")
        table.add_row(
            str(row["strategy"]),
            str(row["claim_id"]),
            str(row["source_type"]),
            str(row["accessed_at"]),
            str(row["age_days"]),
            ", ".join(flags) or "ok",
        )
    console.print(table)
    console.print(
        f"\n[bold]Summary[/bold]: total={total}, stale={len(stale)}, "
        f"expired={len(expired)}, unverified={len(unverified)}, "
        f"shared_urls={len(duplicates)}"
    )

    if not output:
        return

    curation_dir = root / "reports" / "harness" / "curation"
    curation_dir.mkdir(parents=True, exist_ok=True)
    md_path = curation_dir / f"{today.isoformat()}-evidence-curation.md"
    json_path = curation_dir / f"{today.isoformat()}-evidence-curation.json"

    md_lines = [
        f"# Evidence Curation — {today.isoformat()}",
        "",
        "## Source Card Status",
        f"- Total cards: {total}",
        f"- Stale: {len(stale)}",
        f"- Expired: {len(expired)}",
        f"- Unverified: {len(unverified)}",
        f"- URLs shared by 2+ strategies: {len(duplicates)}",
        "",
        "## Stale Cards Requiring Refresh",
    ]
    if stale:
        md_lines.append("| Strategy | Claim ID | Source Type | Accessed | Age (d) |")
        md_lines.append("|---|---|---|---|---|")
        for r in stale:
            md_lines.append(
                f"| {r['strategy']} | {r['claim_id']} | {r['source_type']} | "
                f"{r['accessed_at']} | {r['age_days']} |"
            )
    else:
        md_lines.append("- (none)")
    md_lines.extend(["", "## Shared URLs (Candidates for Deduplication)"])
    if duplicates:
        for url, refs in duplicates.items():
            md_lines.append(f"- {url}")
            for n, cid in refs:
                md_lines.append(f"  - {n} / {cid}")
    else:
        md_lines.append("- (none)")
    md_lines.extend(
        [
            "",
            "## Next Curation Due",
            f"{(today + _dt.timedelta(days=7)).isoformat()} (or after 20 strategy research runs)",
        ]
    )
    md_path.write_text("\n".join(md_lines) + "\n", encoding="utf-8")

    json_payload = {
        "generated_at": today.isoformat(),
        "total_cards": total,
        "stale_count": len(stale),
        "expired_count": len(expired),
        "unverified_count": len(unverified),
        "shared_url_count": len(duplicates),
        "rows": rows,
        "shared_urls": {url: refs for url, refs in duplicates.items()},
    }
    json_path.write_text(_json.dumps(json_payload, indent=2, ensure_ascii=False))

    console.print(f"[green]curation written[/green] {md_path.relative_to(root)}")


@harness_app.command("policy-list")
def harness_policy_list() -> None:
    """List all registered risk domains, required skills, and artifact contracts."""
    from open_composer.harness.policy import load_artifact_contracts, load_risk_domains

    domains = load_risk_domains()
    contracts = load_artifact_contracts()

    console.print("[bold]Risk Domains[/bold]")
    for did, domain in domains.items():
        console.print(f"  {did}")
        if domain.required_skills:
            console.print(f"    skills: {', '.join(domain.required_skills)}")
        if domain.required_artifacts:
            console.print(f"    artifacts: {', '.join(domain.required_artifacts)}")

    console.print("\n[bold]Artifact Contracts[/bold]")
    for name in sorted(contracts):
        c = contracts[name]
        console.print(f"  {name} ({c.format}) → {c.path_template}")


def _project_relpath(value: str | None, root: Path) -> str | None:
    if not value:
        return None
    path = Path(value)
    if not path.is_absolute():
        return path.as_posix()
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def _gate_evidence(results: list[object], name: str) -> dict[str, object]:
    for result in results:
        if getattr(result, "name", None) == name:
            evidence = getattr(result, "evidence", None)
            return evidence if isinstance(evidence, dict) else {}
    return {}


def _gate_status(results: list[object], name: str) -> str | None:
    for result in results:
        if getattr(result, "name", None) == name:
            return str(getattr(result, "status", ""))
    return None


def _router_auth_warning(name: str) -> bool:
    return name in {"router_order_authorization", "capability_report"}


def _router_authorization_permitted_readiness_gap(check: object) -> bool:
    status = str(getattr(check, "status", ""))
    name = str(getattr(check, "name", ""))
    if status == "ok":
        return True
    if status == "warning" and _router_auth_warning(name):
        return True
    if status == "blocked" and name == "harness_artifacts":
        details = getattr(check, "details", {})
        if isinstance(details, dict):
            missing = details.get("missing")
            incomplete = details.get("incomplete")
            return missing == ["paper_safety_review"] and not incomplete
    return False


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


@options_app.command("overlay-report")
def options_overlay_report(overlay: Path) -> None:
    """Generate observation-only research report for an OptionsOverlay spec."""
    try:
        result = build_options_overlay_report(overlay, project_root())
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    console.print(f"[green]options overlay report complete[/green] report: {result.report_path}")
    console.print(
        f"execution_substate={result.execution_substate} paper_ready_pass={result.paper_ready_pass}"
    )


@options_app.command("research-report")
def options_research_report(options_spec: Path) -> None:
    """Generate observation-only research report for an independent OptionsSpec."""
    try:
        result = build_options_research_report(options_spec, project_root())
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    console.print(f"[green]options research report complete[/green] report: {result.report_path}")
    console.print(
        f"execution_substate={result.execution_substate} paper_ready_pass={result.paper_ready_pass}"
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
    readiness = assess_paper_strategy_readiness(spec_path, root)
    if readiness.status != "ok" or readiness.execution_substate != "order_authorized":
        raise typer.BadParameter(
            "paper order submission requires paper readiness status=ok and "
            "execution_substate=order_authorized"
        )
    try:
        order = submit_paper_order(signal, spec, root, qty=qty)
    except PaperOrderError as exc:
        raise typer.BadParameter(str(exc)) from exc
    console.print(f"[green]paper order[/green] {order.id} status={order.status} qty={order.qty}")


@paper_app.command("authorize-router")
def paper_authorize_router(
    strategy: str,
    authorized_by: Annotated[
        str,
        typer.Option(
            "--authorized-by",
            help="Audit label for the supervised Alpaca Paper router authorization.",
        ),
    ] = "operator_supervised_paper_alignment",
) -> None:
    """Write the Alpaca Paper router order authorization artifact."""
    from open_composer.router_authorization import write_router_order_authorization

    root = project_root()
    spec_path = _find_strategy_spec(strategy, root)
    spec = load_strategy_spec(spec_path)
    readiness = assess_paper_strategy_readiness(spec_path, root)
    unsafe = [
        check.name
        for check in readiness.checks
        if not _router_authorization_permitted_readiness_gap(check)
    ]
    if unsafe:
        raise typer.BadParameter(
            "router authorization requires all non-authorization readiness checks to pass: "
            + ", ".join(unsafe)
        )
    try:
        path = write_router_order_authorization(
            spec,
            root,
            spec_path=spec_path,
            authorized_by=authorized_by,
        )
    except (FileNotFoundError, ValueError) as exc:
        raise typer.BadParameter(str(exc)) from exc
    console.print(f"[green]router authorization[/green] {path.relative_to(root)}")


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


@paper_app.command("validation-report")
def paper_validation_report(
    target_days: int = typer.Option(20, "--target-days", min=1),
) -> None:
    """Build the 20-trading-day paper workflow validation report."""
    payload = write_paper_validation_report(root=project_root(), target_days=target_days)
    console.print(
        f"[green]paper validation report written[/green] "
        f"progress={payload['progress_days']}/{payload['target_days']} "
        f"pass={payload['paper_validation_pass']}"
    )
    console.print(f"json={payload['artifact_paths']['json']}")
    console.print(f"markdown={payload['artifact_paths']['markdown']}")
    if payload["paper_validation_pass"]:
        console.print(f"final={payload['artifact_paths']['final_markdown']}")


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


def _fmt_optional(value: object) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, int | float):
        return f"{float(value):.4f}"
    return str(value)


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
