from __future__ import annotations

from pathlib import Path

from open_composer.config import ensure_dir
from open_composer.models.backtest import BacktestRun, Trade
from open_composer.models.signal import Signal
from open_composer.models.strategy_spec import StrategySpec


def write_backtest_report(
    path: Path,
    run: BacktestRun,
    signals: list[Signal],
    trades: list[Trade],
    spec: StrategySpec,
) -> Path:
    ensure_dir(path.parent)
    factor_lines = [
        f"- `{name}` ({factor.source}): `{factor.expression or factor.field or ''}`"
        for name, factor in spec.factors.items()
    ]
    if not factor_lines:
        factor_lines = ["- No custom factors."]
    lines = [
        f"# Backtest Report: {run.strategy_name}",
        "",
        f"- Run ID: `{run.run_id}`",
        f"- Strategy ID: `{run.strategy_id or run.strategy_name}`",
        f"- Version ID: `{run.version_id or 'unregistered'}`",
        f"- Spec hash: `{run.spec_hash or 'unregistered'}`",
        f"- Strategy backend: `{run.strategy_backend}`",
        f"- Execution backend: `{run.execution_backend}`",
        f"- Backend plan path: `{run.backend_plan_path or 'none'}`",
        f"- Symbol: `{run.symbol}`",
        f"- Timeframe: `{run.timeframe}`",
        f"- Bars: {run.bars}",
        f"- Signals: {run.signals}",
        f"- Closed trades: {run.trades}",
        f"- Start equity: {run.start_equity:.2f}",
        f"- End equity: {run.end_equity:.2f}",
        f"- Total return: {run.total_return_pct:.2f}%",
        f"- Annualized return: {run.annualized_return_pct:.2f}%"
        if run.annualized_return_pct is not None
        else "- Annualized return: n/a",
        f"- Sharpe ratio: {run.sharpe_ratio:.2f}"
        if run.sharpe_ratio is not None
        else "- Sharpe ratio: n/a",
        f"- Total fees: {run.total_fees:.2f}",
        "",
        "## Assumptions",
        "",
        *[f"- {assumption}" for assumption in run.assumptions],
        "",
        "## Strategy Rules",
        "",
        "Factors:",
        *factor_lines,
        "",
        "Entry:",
        *[f"- `{rule}`" for rule in [*spec.entry.all, *spec.entry.any]],
        "",
        "Exit:",
        *[f"- `{rule}`" for rule in [*spec.exit.all, *spec.exit.any]],
        "",
        "## Signals",
        "",
    ]
    if signals:
        lines.extend(
            f"- `{signal.id}` {signal.timestamp.isoformat()} {signal.action} "
            f"{signal.symbol} @ {signal.price:.2f}"
            for signal in signals
        )
    else:
        lines.append("- No signals generated.")
    lines.extend(["", "## Trades", ""])
    if trades:
        lines.extend(
            f"- {trade.entry_time.isoformat()} -> "
            f"{trade.exit_time.isoformat() if trade.exit_time else 'open'} "
            f"PnL {trade.pnl:.2f} ({trade.return_pct:.2f}%) "
            f"fees {trade.entry_fee + trade.exit_fee:.2f}"
            for trade in trades
        )
    else:
        lines.append("- No closed trades.")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def write_scan_report(
    path: Path,
    run_id: str,
    spec: StrategySpec,
    signals: list[Signal],
    version_id: str | None = None,
    spec_hash: str | None = None,
    execution_backend: str = "python_reference",
) -> Path:
    ensure_dir(path.parent)
    lines = [
        f"# Scan Report: {spec.name}",
        "",
        f"- Run ID: `{run_id}`",
        f"- Strategy ID: `{spec.name}`",
        f"- Version ID: `{version_id or 'unregistered'}`",
        f"- Spec hash: `{spec_hash or 'unregistered'}`",
        f"- Strategy backend: `{spec.execution.backend}`",
        f"- Execution backend: `{execution_backend}`",
        f"- Symbol: `{spec.primary_symbol}`",
        f"- Timeframe: `{spec.timeframe}`",
        f"- Signals: {len(signals)}",
        "",
    ]
    if signals:
        lines.extend(
            f"- `{signal.id}` {signal.timestamp.isoformat()} {signal.action} @ {signal.price:.2f}"
            for signal in signals
        )
    else:
        lines.append("- No latest-bar signal.")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def write_parity_report(path: Path, spec: StrategySpec, pine_path: Path) -> Path:
    ensure_dir(path.parent)
    lines = [
        f"# Signal Parity Checklist: {spec.name}",
        "",
        f"- Pine file: `{pine_path}`",
        "- Python signal semantics: bar-close confirmation.",
        "- Pine signal semantics: `barstate.isconfirmed`.",
        "- Backtest fill assumption: next bar open.",
        "- Repaint risk: low for supported OHLCV and ta.* expressions without lookahead.",
        "- Manual check: compare TradingView alert timestamps against `signal_logs/*.jsonl`.",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")
    return path
