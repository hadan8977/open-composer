from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from open_composer.adapters.data import load_ohlcv_for_spec
from open_composer.adapters.execution import (
    build_nautilus_backtest_plan,
    write_nautilus_backtest_plan,
)
from open_composer.analytics import (
    build_performance_metrics,
    evaluate_execution_reality,
    exposure_pct_from_trades,
    trade_pnls,
    trade_return_pcts,
    turnover_ratio_from_trades,
)
from open_composer.analytics.benchmark import build_buy_hold_benchmark
from open_composer.analytics.data_sanity import evaluate_backtest_data_sanity
from open_composer.config import project_root, run_id
from open_composer.engines.signal_engine import build_signal, signal_masks
from open_composer.feature_packets import (
    should_auto_emit_context_features,
    write_context_feature_packet,
)
from open_composer.models.backtest import BacktestRun, Trade
from open_composer.models.signal import Signal
from open_composer.models.strategy_spec import StrategySpec, load_strategy_spec
from open_composer.reports.writer import write_backend_parity_report, write_backtest_report
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

        reference_artifacts = backtest_frame(
            spec,
            frame,
            root=base,
            start_equity=start_equity,
            run_id_value=f"{current_run_id}-python-reference",
            version_id=version.version_id,
            spec_hash=version.content_hash,
            backend_plan_path=str(backend_plan_path) if backend_plan_path else None,
            execution_backend="python_reference",
        )
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
        parity_md_path, parity_json_path = write_backend_parity_report(
            base / "reports" / "parity" / f"{current_run_id}-backend-parity.md",
            strategy_name=spec.name,
            primary=nautilus_artifacts.run,
            reference=reference_artifacts.run,
        )
        artifacts.run.assumptions.append(
            "Python reference / NautilusTrader backend parity report: "
            f"{parity_md_path} ({parity_json_path})."
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
    write_backtest_report(
        report_path,
        artifacts.run,
        artifacts.signals,
        artifacts.trades,
        spec,
        root=base,
    )
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
    evaluation_start_index: int = 0,
) -> BacktestArtifacts:
    frame = frame.copy()
    frame.attrs.update({"strategy_name": spec.name})
    entry_mask, exit_mask = signal_masks(spec, frame, root=root)
    evaluation_start_index = max(0, min(evaluation_start_index, max(len(frame) - 1, 0)))
    evaluation_frame = frame.iloc[evaluation_start_index:].copy()
    current_run_id = run_id_value or run_id(spec.name)
    data_provenance = frame.attrs.get("data_source_mode")
    data_provider = frame.attrs.get("data_source_provider")
    equity = start_equity
    position_direction: str | None = None
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
    impact_rate = _impact_rate(
        spec.costs.impact_model, spec.costs.impact_eta, spec.costs.impact_gamma
    )
    equity_curve = [start_equity]
    entry_fill_by_direction = {
        "long": lambda open_price: open_price * (1 + slippage_rate + impact_rate),
        "short": lambda open_price: open_price * (1 - slippage_rate - impact_rate),
    }
    exit_fill_by_direction = {
        "long": lambda open_price: open_price * (1 - slippage_rate - impact_rate),
        "short": lambda open_price: open_price * (1 + slippage_rate + impact_rate),
    }

    loop_start = max(0, evaluation_start_index - 1)
    for idx in range(loop_start, len(frame) - 1):
        row = frame.iloc[idx]
        next_row = frame.iloc[idx + 1]
        timestamp = row["timestamp"].to_pydatetime()
        next_timestamp = next_row["timestamp"].to_pydatetime()
        fill_is_in_evaluation = idx + 1 >= evaluation_start_index
        signal_is_in_evaluation = idx >= evaluation_start_index
        close_price = float(row["close"])
        next_open = float(next_row["open"])
        if signal_is_in_evaluation:
            marked_equity = equity
            if position_direction and shares:
                marked_equity += (
                    _direction_multiplier(position_direction) * shares * (close_price - entry_price)
                )
            equity_curve.append(marked_equity)

        target_direction = _target_direction(
            spec,
            entry=bool(entry_mask.iloc[idx]),
            exit_=bool(exit_mask.iloc[idx]),
        )

        if position_direction is None:
            fill_day_key = next_timestamp.date().isoformat()
            day_count = trades_by_day.get(fill_day_key, 0)
            if target_direction and day_count < spec.risk.max_trades_per_day:
                if fill_is_in_evaluation:
                    entry_fill_price = entry_fill_by_direction[target_direction](next_open)
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
                            side_override=_entry_side(target_direction),
                        )
                    )
                    entry_price = entry_fill_price
                    max_notional = equity * spec.risk.max_position_weight
                    shares = max_notional / (entry_price * (1 + commission_rate))
                    entry_fee = shares * entry_price * commission_rate
                    total_fees += entry_fee
                    equity -= entry_fee
                    trade = Trade(
                        direction=target_direction,
                        entry_time=next_timestamp,
                        entry_price=entry_price,
                        shares=shares,
                        entry_fee=entry_fee,
                    )
                    position_direction = target_direction
                    trades_by_day[fill_day_key] = day_count + 1
            continue

        if not signal_is_in_evaluation:
            continue
        stop_hit = _stop_hit(
            position_direction,
            close_price,
            entry_price,
            spec.risk.stop_loss_pct,
        )
        take_hit = _take_hit(
            position_direction,
            close_price,
            entry_price,
            spec.risk.take_profit_pct,
        )
        should_exit = (
            stop_hit
            or take_hit
            or (bool(exit_mask.iloc[idx]) if spec.position_direction != "long_short" else False)
        )
        should_reverse = (
            spec.position_direction == "long_short"
            and target_direction is not None
            and target_direction != position_direction
        )
        if should_exit or should_reverse:
            exit_fill_price = exit_fill_by_direction[position_direction](next_open)
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
                    side_override=_exit_side(position_direction),
                )
            )
            direction = _direction_multiplier(position_direction)
            gross_pnl = direction * shares * (exit_fill_price - entry_price)
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
            position_direction = None
            entry_price = 0.0
            entry_fee = 0.0
            shares = 0.0
            trade = None
            if should_reverse:
                fill_day_key = next_timestamp.date().isoformat()
                day_count = trades_by_day.get(fill_day_key, 0)
                if day_count < spec.risk.max_trades_per_day and target_direction:
                    entry_fill_price = entry_fill_by_direction[target_direction](next_open)
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
                            side_override=_entry_side(target_direction),
                        )
                    )
                    max_notional = equity * spec.risk.max_position_weight
                    shares = max_notional / (entry_fill_price * (1 + commission_rate))
                    entry_fee = shares * entry_fill_price * commission_rate
                    total_fees += entry_fee
                    equity -= entry_fee
                    trade = Trade(
                        direction=target_direction,
                        entry_time=next_timestamp,
                        entry_price=entry_fill_price,
                        shares=shares,
                        entry_fee=entry_fee,
                    )
                    entry_price = entry_fill_price
                    position_direction = target_direction
                    trades_by_day[fill_day_key] = day_count + 1

    if position_direction and shares:
        direction = _direction_multiplier(position_direction)
        equity += direction * shares * (float(frame.iloc[-1]["close"]) - entry_price)

    total_return_pct = (equity / start_equity - 1) * 100
    equity_curve.append(equity)
    metrics = build_performance_metrics(
        equity_curve,
        spec.timeframe,
        trade_pnls=trade_pnls(trades),
        trade_return_pcts=trade_return_pcts(trades),
        exposure_pct=exposure_pct_from_trades(trades, evaluation_frame),
        turnover_ratio=turnover_ratio_from_trades(trades, start_equity),
    )
    execution_reality = evaluate_execution_reality(evaluation_frame, trades)
    benchmark = build_buy_hold_benchmark(evaluation_frame, total_return_pct)
    assumptions = [
        "Signals are confirmed on bar close.",
        "Backtest fills use next bar open.",
        "Total return is period account-level return, not annualized.",
        (
            "Buy-and-hold benchmark uses first available open to final close over the same "
            "data window."
        ),
        "Position size uses max_position_weight; it is not all-in unless configured.",
        "Open positions are marked to the final close and not counted as closed trades.",
        f"Commission is {spec.costs.commission_pct:.4g}% per fill.",
        f"Slippage is {spec.costs.slippage_bps:.4g} bps per fill.",
        "Execution reality uses conservative OHLCV-only liquidity proxies.",
        "NautilusTrader-compatible strategies may also emit a backend plan artifact.",
        "This backtest does not model dividends or corporate actions.",
    ]
    if spec.position_direction == "short_only":
        assumptions.append(
            "Short-only backtest reverses entry/exit PnL direction but does not model borrow "
            "availability, borrow fees, buy-in risk, or dividend liability."
        )
    if spec.position_direction == "long_short":
        assumptions.append(
            "Long-short backtest treats entry rules as target-long signals and exit rules as "
            "target-short signals. It flips the single active leg on the next bar open and does "
            "not model borrow availability, borrow fees, buy-in risk, or dividend liability."
        )
    if data_provenance:
        provider_label = str(data_provider or spec.data.source)
        assumptions.insert(
            0,
            f"Data provenance: {provider_label} {data_provenance.replace('_', ' ')}.",
        )
    if evaluation_start_index > 0:
        assumptions.append(
            f"Indicators were warmed with {evaluation_start_index} prior bars before scoring."
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
        bars=len(evaluation_frame),
        signals=len(signals),
        trades=len(trades),
        start_equity=start_equity,
        end_equity=equity,
        total_return_pct=total_return_pct,
        buy_hold_return_pct=benchmark.return_pct,
        alpha_vs_buy_hold_pct=benchmark.alpha_pct,
        annualized_return_pct=metrics.annualized_return_pct,
        sharpe_ratio=metrics.sharpe_ratio,
        annualized_volatility_pct=metrics.annualized_volatility_pct,
        max_drawdown_pct=metrics.max_drawdown_pct,
        downside_volatility_pct=metrics.downside_volatility_pct,
        sortino_ratio=metrics.sortino_ratio,
        calmar_ratio=metrics.calmar_ratio,
        win_rate_pct=metrics.win_rate_pct,
        profit_factor=metrics.profit_factor,
        average_trade_return_pct=metrics.average_trade_return_pct,
        exposure_pct=metrics.exposure_pct,
        turnover_ratio=metrics.turnover_ratio,
        total_fees=total_fees,
        backend_plan_path=backend_plan_path,
        execution_reality=execution_reality,
        assumptions=assumptions,
    )
    run.data_sanity = evaluate_backtest_data_sanity(
        spec=spec,
        frame=evaluation_frame,
        run=run,
        trades=trades,
    )
    return BacktestArtifacts(
        run=run, signals=signals, trades=trades, backend_plan_path=backend_plan_path
    )


def _impact_rate(impact_model: str, impact_eta: float, impact_gamma: float) -> float:
    if impact_model == "linear":
        return 0.0
    if impact_model == "sqrt":
        return impact_eta / 10_000
    if impact_model == "almgren_chriss":
        return (impact_eta + impact_gamma) / 10_000
    raise ValueError(f"unsupported impact model: {impact_model}")


def _target_direction(
    spec: StrategySpec,
    *,
    entry: bool,
    exit_: bool,
) -> str | None:
    if spec.position_direction == "short_only":
        return "short" if entry else None
    if spec.position_direction == "long_short":
        if entry:
            return "long"
        if exit_:
            return "short"
        return None
    return "long" if entry else None


def _direction_multiplier(direction: str) -> float:
    return -1.0 if direction == "short" else 1.0


def _entry_side(direction: str) -> str:
    return "sell" if direction == "short" else "buy"


def _exit_side(direction: str) -> str:
    return "buy" if direction == "short" else "sell"


def _stop_hit(
    direction: str,
    close_price: float,
    entry_price: float,
    stop_loss_pct: float | None,
) -> bool:
    if stop_loss_pct is None:
        return False
    if direction == "short":
        return close_price >= entry_price * (1 + stop_loss_pct / 100)
    return close_price <= entry_price * (1 - stop_loss_pct / 100)


def _take_hit(
    direction: str,
    close_price: float,
    entry_price: float,
    take_profit_pct: float | None,
) -> bool:
    if take_profit_pct is None:
        return False
    if direction == "short":
        return close_price <= entry_price * (1 - take_profit_pct / 100)
    return close_price >= entry_price * (1 + take_profit_pct / 100)
