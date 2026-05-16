from __future__ import annotations

from pathlib import Path

from open_composer.config import ensure_dir
from open_composer.feature_packets import inspect_feature_packet
from open_composer.models.backtest import BacktestRun, Trade
from open_composer.models.signal import Signal
from open_composer.models.strategy_spec import StrategySpec
from open_composer.storage import write_json


def write_backtest_report(
    path: Path,
    run: BacktestRun,
    signals: list[Signal],
    trades: list[Trade],
    spec: StrategySpec,
    root: Path | None = None,
) -> Path:
    ensure_dir(path.parent)
    factor_lines = [
        f"- `{name}` ({factor.source}): `{factor.expression or factor.field or ''}`"
        for name, factor in spec.factors.items()
    ]
    if not factor_lines:
        factor_lines = ["- No custom factors."]
    feature_replay_lines = _feature_replay_lines(spec, root)
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
        f"- Buy and hold return: {_optional_pct(run.buy_hold_return_pct)}",
        f"- Alpha vs buy and hold: {_optional_pct(run.alpha_vs_buy_hold_pct)}",
        f"- Annualized return: {run.annualized_return_pct:.2f}%"
        if run.annualized_return_pct is not None
        else "- Annualized return: n/a",
        f"- Sharpe ratio: {run.sharpe_ratio:.2f}"
        if run.sharpe_ratio is not None
        else "- Sharpe ratio: n/a",
        f"- Annualized volatility: {_optional_pct(run.annualized_volatility_pct)}",
        f"- Max drawdown: {_optional_pct(run.max_drawdown_pct)}",
        f"- Downside volatility: {_optional_pct(run.downside_volatility_pct)}",
        f"- Sortino ratio: {_optional_ratio(run.sortino_ratio)}",
        f"- Calmar ratio: {_optional_ratio(run.calmar_ratio)}",
        f"- Win rate: {_optional_pct(run.win_rate_pct)}",
        f"- Profit factor: {_optional_ratio(run.profit_factor)}",
        f"- Average trade return: {_optional_pct(run.average_trade_return_pct)}",
        f"- Exposure: {_optional_pct(run.exposure_pct)}",
        f"- Turnover estimate: {_optional_multiple(run.turnover_ratio)}",
        f"- Total fees: {run.total_fees:.2f}",
        "",
        "## Data Sanity",
        "",
        *_data_sanity_lines(run),
        "",
        "## Execution Reality",
        "",
        *_execution_reality_lines(run),
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
        "## Feature Replay",
        "",
        *feature_replay_lines,
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


def _data_sanity_lines(run: BacktestRun) -> list[str]:
    if run.data_sanity is None:
        return ["- Status: `unknown`", "- Warning: data sanity was not evaluated."]
    sanity = run.data_sanity
    first_timestamp = sanity.first_timestamp.isoformat() if sanity.first_timestamp else "n/a"
    last_timestamp = sanity.last_timestamp.isoformat() if sanity.last_timestamp else "n/a"
    lines = [
        f"- Status: `{sanity.status}`",
        f"- Evidence level: `{sanity.evidence_level}`",
        f"- Source: `{sanity.data_source}`",
        f"- Mode: `{sanity.data_source_mode or 'unknown'}`",
        f"- Feed: `{sanity.data_feed or 'none'}`",
        f"- Path: `{sanity.data_path or 'none'}`",
        f"- Bars: {sanity.bars}",
        f"- Signals: {sanity.signals}",
        f"- Trades: {sanity.trades}",
        f"- First timestamp: `{first_timestamp}`",
        f"- Last timestamp: `{last_timestamp}`",
        f"- Data span days: {_optional_float(sanity.data_span_days)}",
        f"- Average holding days: {_optional_float(sanity.average_holding_days)}",
        f"- Warning count: {len(sanity.warnings)}",
    ]
    if sanity.warnings:
        lines.extend(f"- Warning: {warning}" for warning in sanity.warnings)
    else:
        lines.append("- Warning: none")
    return lines


def _execution_reality_lines(run: BacktestRun) -> list[str]:
    if run.execution_reality is None:
        return ["- Status: `unknown`", "- Warning: execution reality was not evaluated."]
    reality = run.execution_reality
    lines = [
        f"- Status: `{reality.status}`",
        f"- Average dollar volume: {_optional_money(reality.average_dollar_volume)}",
        f"- Median dollar volume: {_optional_money(reality.median_dollar_volume)}",
        f"- Minimum dollar volume: {_optional_money(reality.min_dollar_volume)}",
        f"- Max trade notional: {_optional_money(reality.max_trade_notional)}",
        f"- Max bar participation: {_optional_pct(reality.max_bar_participation_pct)}",
        f"- Average bar participation: {_optional_pct(reality.average_bar_participation_pct)}",
        f"- Max ADV participation: {_optional_pct(reality.max_adv_participation_pct)}",
        f"- Estimated 5% ADV capacity: {_optional_money(reality.estimated_capacity_notional)}",
        f"- Warning count: {len(reality.warnings)}",
    ]
    if reality.warnings:
        lines.extend(f"- Warning: {warning}" for warning in reality.warnings)
    else:
        lines.append("- Warning: none")
    return lines


def _optional_float(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.4f}"


def _optional_pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.2f}%"


def _optional_ratio(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.2f}"


def _optional_multiple(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.2f}x"


def _optional_money(value: float | None) -> str:
    return "n/a" if value is None else f"${value:,.2f}"


def _feature_replay_lines(spec: StrategySpec, root: Path | None) -> list[str]:
    replay_factors = [
        (name, factor)
        for name, factor in spec.factors.items()
        if factor.source in {"llm_feature", "feature_packet"}
    ]
    if not replay_factors:
        return ["- No LLM or feature packet factors."]

    lines = [
        "- Backtest execution reads saved feature packets only; it does not call an LLM inside "
        "the execution loop.",
        "- Replay mode: `point_in_time_last_observation`.",
    ]
    for name, factor in replay_factors:
        path_value = factor.path or ""
        resolved = _resolve_feature_path(path_value, root)
        inspection = inspect_feature_packet(resolved, factor.field) if resolved else None
        if inspection is None:
            lines.append(
                f"- `{name}` source=`{factor.source}` field=`{factor.field or 'n/a'}` "
                "path=`missing` status=`missing` warnings=`missing packet path`"
            )
            continue
        warning_text = "; ".join(inspection.replay_warnings) or "none"
        lines.append(
            f"- `{name}` source=`{factor.source}` field=`{factor.field or 'n/a'}` "
            f"path=`{path_value}` status=`{inspection.point_in_time_status}` "
            f"records=`{inspection.record_count}` first=`{inspection.first_timestamp or 'n/a'}` "
            f"last=`{inspection.last_timestamp or 'n/a'}` sources=`{inspection.sources}` "
            f"schema_versions=`{inspection.schema_versions}` models=`{inspection.models}` "
            f"input_hashes=`{inspection.input_hashes}` prompt_hashes=`{inspection.prompt_hashes}` "
            f"warnings=`{warning_text}`"
        )
    return lines


def _resolve_feature_path(path_value: str, root: Path | None) -> Path | None:
    if not path_value:
        return None
    path = Path(path_value)
    if not path.is_absolute() and root is not None:
        path = root / path
    return path


def write_scan_report(
    path: Path,
    run_id: str,
    spec: StrategySpec,
    signals: list[Signal],
    version_id: str | None = None,
    spec_hash: str | None = None,
    execution_backend: str = "python_reference",
    root: Path | None = None,
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
        "## Feature Replay",
        "",
        *_feature_replay_lines(spec, root),
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


def write_backend_parity_report(
    path: Path,
    *,
    strategy_name: str,
    primary: BacktestRun,
    reference: BacktestRun,
) -> tuple[Path, Path]:
    ensure_dir(path.parent)
    signal_diff = primary.signals - reference.signals
    trade_diff = primary.trades - reference.trades
    return_diff = primary.total_return_pct - reference.total_return_pct
    fee_diff = primary.total_fees - reference.total_fees
    status = (
        "ok"
        if signal_diff == 0 and trade_diff == 0 and abs(return_diff) < 1e-9 and abs(fee_diff) < 1e-9
        else "warning"
    )
    payload = {
        "strategy_name": strategy_name,
        "status": status,
        "primary_backend": primary.execution_backend,
        "reference_backend": reference.execution_backend,
        "primary_run_id": primary.run_id,
        "reference_run_id": reference.run_id,
        "signals": {
            "primary": primary.signals,
            "reference": reference.signals,
            "diff": signal_diff,
        },
        "trades": {
            "primary": primary.trades,
            "reference": reference.trades,
            "diff": trade_diff,
        },
        "total_return_pct": {
            "primary": primary.total_return_pct,
            "reference": reference.total_return_pct,
            "diff": return_diff,
        },
        "total_fees": {
            "primary": primary.total_fees,
            "reference": reference.total_fees,
            "diff": fee_diff,
        },
    }
    json_path = path.with_suffix(".json")
    write_json(json_path, payload)
    lines = [
        f"# Backend Parity: {strategy_name}",
        "",
        f"- Status: `{status}`",
        f"- Primary backend: `{primary.execution_backend}` run=`{primary.run_id}`",
        f"- Reference backend: `{reference.execution_backend}` run=`{reference.run_id}`",
        "",
        "## Differences",
        "",
        (
            f"- Signals: primary `{primary.signals}` reference `{reference.signals}` "
            f"diff `{signal_diff}`"
        ),
        f"- Trades: primary `{primary.trades}` reference `{reference.trades}` diff `{trade_diff}`",
        (
            f"- Total return pct: primary `{primary.total_return_pct:.6f}` "
            f"reference `{reference.total_return_pct:.6f}` diff `{return_diff:.6f}`"
        ),
        (
            f"- Total fees: primary `{primary.total_fees:.6f}` "
            f"reference `{reference.total_fees:.6f}` diff `{fee_diff:.6f}`"
        ),
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")
    return path, json_path
