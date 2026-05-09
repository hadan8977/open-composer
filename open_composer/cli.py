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
    sync_paper_orders,
)
from open_composer.adapters.data import fetch_ohlcv
from open_composer.adapters.events import fetch_capability_events
from open_composer.capabilities import evaluate_capabilities, load_registry
from open_composer.compiler.spec_to_pine import compile_pine, compile_pine_strategy
from open_composer.config import (
    alpaca_api_base_url,
    data_feed,
    default_openai_model,
    ensure_dir,
    openai_base_url,
    openai_base_url_source,
    optional_env_status,
    project_root,
)
from open_composer.context import build_signal_context
from open_composer.engines.backtest_engine import run_backtest
from open_composer.engines.scanner_engine import run_scan
from open_composer.journal.writer import add_journal_entry
from open_composer.models.strategy_spec import load_strategy_spec
from open_composer.research import (
    draft_strategy_from_idea,
    optimize_option_overlays,
    optimize_strategy,
    optimize_strategy_horizons,
    optimize_strategy_universe,
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
        "ALPHA_VANTAGE_API_KEY", optional_env_status("ALPHA_VANTAGE_API_KEY"), "optional news"
    )
    table.add_row("FRED_API_KEY", optional_env_status("FRED_API_KEY"), "optional macro")
    console.print(table)


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
    console.print(
        "expressions: "
        f"names={','.join(report.expression_names) or 'none'} "
        f"functions={','.join(report.expression_functions) or 'none'}"
    )


def _strategy_capability_payload(report: StrategyCapabilityReport) -> dict[str, object]:
    return {
        "strategy_name": report.strategy_name,
        "lifecycle": report.lifecycle,
        "expression_functions": report.expression_functions,
        "expression_names": report.expression_names,
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
    start: str | None = typer.Option(None, "--start"),
    end: str | None = typer.Option(None, "--end"),
    feed: str | None = typer.Option(None, "--feed"),
) -> None:
    """Fetch Alpaca historical bars into data/cache."""
    root = project_root()
    frame = fetch_ohlcv(
        root=root,
        symbol=symbol.upper(),
        timeframe=timeframe,
        start=_parse_datetime(start),
        end=_parse_datetime(end),
        feed=feed,
    )
    console.print(f"[green]fetched[/green] {len(frame)} bars for {symbol.upper()} {timeframe}")


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
) -> None:
    """Generate candidate rule variants and select the best deterministic backtest result."""
    result = optimize_strategy(spec, project_root(), min_return_pct, min_signals)
    console.print(
        f"[green]optimized[/green] {result.best_spec_path} "
        f"return={result.best_artifacts.run.total_return_pct:.2f}% "
        f"signals={result.best_artifacts.run.signals}"
    )
    console.print(f"report: {result.report_path}")


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
    if data_source != "alpaca":
        raise typer.BadParameter("--data-source currently supports alpaca")
    result = optimize_strategy_universe(
        spec,
        project_root(),
        symbols=[item.strip().upper() for item in symbols.split(",") if item.strip()],
        data_source="alpaca",
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
    min_trades: int = typer.Option(1, "--min-trades"),
    max_preferred_trades: int = typer.Option(18, "--max-preferred-trades"),
    refresh_data: bool = typer.Option(True, "--refresh-data/--use-cache"),
) -> None:
    """Compare 5m scan speed, 15m lower-turnover, and 1h trend-hold variants."""
    if data_source != "alpaca":
        raise typer.BadParameter("--data-source currently supports alpaca")
    result = optimize_strategy_horizons(
        spec,
        project_root(),
        symbols=[item.strip().upper() for item in symbols.split(",") if item.strip()],
        data_source="alpaca",
        min_return_pct=min_return_pct,
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
) -> None:
    """Activate a StrategySpec for manual signals or Alpaca Paper automation."""
    if data_source not in {"keep", "sample", "alpaca"}:
        raise typer.BadParameter("--data-source must be keep, sample, or alpaca")
    root = project_root()
    path = activate_strategy(
        resolve_strategy_path(spec, root),
        root,
        paper_auto=paper_auto,
        allow_paper_auto=allow_paper_auto,
        data_source=data_source,  # type: ignore[arg-type]
    )
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


@paper_app.command("sync")
def paper_sync() -> None:
    """Sync Alpaca Paper orders to reports/paper/sync.jsonl."""
    try:
        path = sync_paper_orders(project_root())
    except PaperOrderError as exc:
        raise typer.BadParameter(str(exc)) from exc
    console.print(f"[green]paper sync written[/green] {path}")


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


def _ensure_runtime_dirs(root: Path) -> None:
    for relative in [
        "data/cache",
        "reports/backtests",
        "reports/parity",
        "reports/scans",
        "reports/reviews",
        "reports/weekly",
        "reports/paper",
        "reports/runs",
        "reports/capabilities",
        "reports/context",
        "reports/research",
        "reports/options",
        "data/raw/events",
        "data/raw/macro",
        "event_logs",
        "signal_logs",
        "journal",
        "strategies_pine/generated",
    ]:
        ensure_dir(root / relative)


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
