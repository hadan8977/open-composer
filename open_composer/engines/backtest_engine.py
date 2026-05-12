from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from open_composer.adapters.data import load_ohlcv_for_spec
from open_composer.adapters.execution import (
    build_nautilus_backtest_plan,
    write_nautilus_backtest_plan,
)
from open_composer.analytics import build_performance_metrics
from open_composer.config import project_root, run_id
from open_composer.engines.signal_engine import build_signal, signal_masks
from open_composer.feature_packets import (
    should_auto_emit_context_features,
    write_context_feature_packet,
)
from open_composer.models.backtest import BacktestRun, Trade
from open_composer.models.signal import Signal
from open_composer.models.strategy_spec import StrategySpec, load_strategy_spec
from open_composer.reports.writer import write_backtest_report
from open_composer.storage import append_jsonl
from open_composer.strategy_versions import register_strategy_version


@dataclass
class BacktestArtifacts:
    run: BacktestRun
    signals: list[Signal]
    trades: list[Trade]
    backend_plan_path: str | None = None


def run_backtest(
    spec_path: Path,
    root: Path | None = None,
    start_equity: float = 100_000.0,
) -> BacktestArtifacts:
    base = root or project_root()
    spec = load_strategy_spec(spec_path)
    version = register_strategy_version(spec_path, base, created_by="backtest")
    current_run_id = run_id(spec.name)
    backend_plan_path: Path | None = None
    use_nautilus_backtest = False
    if spec.execution.backend == "nautilus_trader":
        backend_plan = build_nautilus_backtest_plan(
            spec_path,
            base,
            run_id_value=current_run_id,
            version_id=version.version_id,
            spec_hash=version.content_hash,
        )
        backend_plan_path = base / "reports" / "runs" / "nautilus" / f"{current_run_id}.json"
        write_nautilus_backtest_plan(backend_plan_path, backend_plan)
        use_nautilus_backtest = (
            backend_plan.selected_backend == "nautilus_trader"
            and backend_plan.nautilus_installed
            and len(spec.universe) == 1
        )
    frame = load_ohlcv_for_spec(spec, base)
    if use_nautilus_backtest:
        from open_composer.adapters.execution.nautilus_runtime import run_nautilus_backtest

        nautilus_artifacts = run_nautilus_backtest(
            spec,
            frame,
            base,
            start_equity=start_equity,
            run_id_value=current_run_id,
            version_id=version.version_id,
            spec_hash=version.content_hash,
            backend_plan_path=str(backend_plan_path) if backend_plan_path else None,
        )
        artifacts = BacktestArtifacts(
            run=nautilus_artifacts.run,
            signals=nautilus_artifacts.signals,
            trades=nautilus_artifacts.trades,
            backend_plan_path=str(backend_plan_path) if backend_plan_path else None,
        )
    else:
        artifacts = backtest_frame(
            spec,
            frame,
            root=base,
            start_equity=start_equity,
            run_id_value=current_run_id,
            version_id=version.version_id,
            spec_hash=version.content_hash,
            backend_plan_path=str(backend_plan_path) if backend_plan_path else None,
        )

    report_path = base / "reports" / "backtests" / f"{artifacts.run.run_id}.md"
    signal_log_path = base / "signal_logs" / f"{artifacts.run.run_id}.jsonl"
    append_jsonl(signal_log_path, artifacts.signals)
    if should_auto_emit_context_features(spec):
        for signal in artifacts.signals:
            write_context_feature_packet(signal.id, base)
        artifacts.run.assumptions.append(
            "Context-derived feature packets were auto-written for context-capable signals."
        )
    write_backtest_report(report_path, artifacts.run, artifacts.signals, artifacts.trades, spec)
    artifacts.run.report_path = str(report_path)
    artifacts.run.signal_log_path = str(signal_log_path)
    artifacts.backend_plan_path = str(backend_plan_path) if backend_plan_path else None
    return artifacts


def backtest_frame(
    spec: StrategySpec,
    frame: pd.DataFrame,
    root: Path | None = None,
    start_equity: float = 100_000.0,
    run_id_value: str | None = None,
    version_id: str | None = None,
    spec_hash: str | None = None,
    backend_plan_path: str | None = None,
    execution_backend: str = "python_reference",
) -> BacktestArtifacts:
    entry_mask, exit_mask = signal_masks(spec, frame, root=root)
    current_run_id = run_id_value or run_id(spec.name)
    data_provenance = frame.attrs.get("data_source_mode")
    data_provider = frame.attrs.get("data_source_provider")
    equity = start_equity
    in_position = False
    entry_price = 0.0
    entry_fee = 0.0
    shares = 0.0
    trade: Trade | None = None
    signals: list[Signal] = []
    trades: list[Trade] = []
    trades_by_day: dict[str, int] = {}
    total_fees = 0.0
    commission_rate = spec.costs.commission_pct / 100
    slippage_rate = spec.costs.slippage_bps / 10_000
    equity_curve = [start_equity]

    for idx in range(len(frame) - 1):
        row = frame.iloc[idx]
        next_row = frame.iloc[idx + 1]
        timestamp = row["timestamp"].to_pydatetime()
        day_key = timestamp.date().isoformat()
        close_price = float(row["close"])
        next_open = float(next_row["open"])
        entry_fill_price = next_open * (1 + slippage_rate)
        exit_fill_price = next_open * (1 - slippage_rate)
        marked_equity = equity
        if in_position and shares:
            marked_equity += shares * (close_price - entry_price)
        equity_curve.append(marked_equity)

        if not in_position:
            day_count = trades_by_day.get(day_key, 0)
            if bool(entry_mask.iloc[idx]) and day_count < spec.risk.max_trades_per_day:
                signals.append(
                    build_signal(
                        spec=spec,
                        run_id=current_run_id,
                        timestamp=timestamp,
                        action="entry",
                        source="backtest",
                        price=close_price,
                        version_id=version_id,
                        spec_hash=spec_hash,
                    )
                )
                entry_price = entry_fill_price
                max_notional = equity * spec.risk.max_position_weight
                shares = max_notional / (entry_price * (1 + commission_rate))
                entry_fee = shares * entry_price * commission_rate
                total_fees += entry_fee
                equity -= entry_fee
                trade = Trade(
                    entry_time=next_row["timestamp"].to_pydatetime(),
                    entry_price=entry_price,
                    shares=shares,
                    entry_fee=entry_fee,
                )
                in_position = True
                trades_by_day[day_key] = day_count + 1
            continue

        stop_hit = spec.risk.stop_loss_pct is not None and close_price <= entry_price * (
            1 - spec.risk.stop_loss_pct / 100
        )
        take_hit = spec.risk.take_profit_pct is not None and close_price >= entry_price * (
            1 + spec.risk.take_profit_pct / 100
        )
        if bool(exit_mask.iloc[idx]) or stop_hit or take_hit:
            signals.append(
                build_signal(
                    spec=spec,
                    run_id=current_run_id,
                    timestamp=timestamp,
                    action="exit",
                    source="backtest",
                    price=close_price,
                    version_id=version_id,
                    spec_hash=spec_hash,
                )
            )
            gross_pnl = shares * (exit_fill_price - entry_price)
            exit_fee = shares * exit_fill_price * commission_rate
            total_fees += exit_fee
            pnl = gross_pnl - exit_fee
            equity += pnl
            if trade is not None:
                trade.exit_time = next_row["timestamp"].to_pydatetime()
                trade.exit_price = exit_fill_price
                trade.exit_fee = exit_fee
                trade.gross_pnl = gross_pnl
                trade.pnl = pnl
                trade.return_pct = (pnl / (shares * entry_price + entry_fee)) * 100
                trades.append(trade)
            in_position = False
            entry_price = 0.0
            entry_fee = 0.0
            shares = 0.0
            trade = None

    if in_position and shares:
        equity += shares * (float(frame.iloc[-1]["close"]) - entry_price)

    total_return_pct = (equity / start_equity - 1) * 100
    equity_curve.append(equity)
    metrics = build_performance_metrics(equity_curve, spec.timeframe)
    assumptions = [
        "Signals are confirmed on bar close.",
        "Backtest fills use next bar open.",
        "Total return is period account-level return, not annualized.",
        "Position size uses max_position_weight; it is not all-in unless configured.",
        "Open positions are marked to the final close and not counted as closed trades.",
        f"Commission is {spec.costs.commission_pct:.4g}% per fill.",
        f"Slippage is {spec.costs.slippage_bps:.4g} bps per fill.",
        "NautilusTrader-compatible strategies may also emit a backend plan artifact.",
        "MVP examples are long-only and do not model dividends or corporate actions.",
    ]
    if data_provenance:
        provider_label = str(data_provider or spec.data.source)
        assumptions.insert(
            0,
            f"Data provenance: {provider_label} {data_provenance.replace('_', ' ')}.",
        )
    run = BacktestRun(
        run_id=current_run_id,
        strategy_name=spec.name,
        strategy_id=spec.name,
        version_id=version_id,
        spec_hash=spec_hash,
        strategy_backend=spec.execution.backend,
        execution_backend=execution_backend,
        symbol=spec.primary_symbol,
        timeframe=spec.timeframe,
        bars=len(frame),
        signals=len(signals),
        trades=len(trades),
        start_equity=start_equity,
        end_equity=equity,
        total_return_pct=total_return_pct,
        annualized_return_pct=metrics.annualized_return_pct,
        sharpe_ratio=metrics.sharpe_ratio,
        total_fees=total_fees,
        backend_plan_path=backend_plan_path,
        assumptions=assumptions,
    )
    return BacktestArtifacts(
        run=run, signals=signals, trades=trades, backend_plan_path=backend_plan_path
    )
