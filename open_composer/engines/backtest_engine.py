from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from open_composer.adapters.data import load_ohlcv_for_spec
from open_composer.config import project_root, run_id
from open_composer.engines.signal_engine import build_signal, signal_masks
from open_composer.models.backtest import BacktestRun, Trade
from open_composer.models.signal import Signal
from open_composer.models.strategy_spec import StrategySpec, load_strategy_spec
from open_composer.reports.writer import write_backtest_report
from open_composer.storage import append_jsonl


@dataclass
class BacktestArtifacts:
    run: BacktestRun
    signals: list[Signal]
    trades: list[Trade]


def run_backtest(
    spec_path: Path,
    root: Path | None = None,
    start_equity: float = 100_000.0,
) -> BacktestArtifacts:
    base = root or project_root()
    spec = load_strategy_spec(spec_path)
    frame = load_ohlcv_for_spec(spec, base)
    artifacts = backtest_frame(spec, frame, start_equity=start_equity)

    report_path = base / "reports" / "backtests" / f"{artifacts.run.run_id}.md"
    signal_log_path = base / "signal_logs" / f"{artifacts.run.run_id}.jsonl"
    append_jsonl(signal_log_path, artifacts.signals)
    write_backtest_report(report_path, artifacts.run, artifacts.signals, artifacts.trades, spec)
    artifacts.run.report_path = str(report_path)
    artifacts.run.signal_log_path = str(signal_log_path)
    return artifacts


def backtest_frame(
    spec: StrategySpec,
    frame: pd.DataFrame,
    start_equity: float = 100_000.0,
    run_id_value: str | None = None,
) -> BacktestArtifacts:
    entry_mask, exit_mask = signal_masks(spec, frame)
    current_run_id = run_id_value or run_id(spec.name)
    equity = start_equity
    in_position = False
    entry_price = 0.0
    shares = 0.0
    trade: Trade | None = None
    signals: list[Signal] = []
    trades: list[Trade] = []
    trades_by_day: dict[str, int] = {}

    for idx in range(len(frame) - 1):
        row = frame.iloc[idx]
        next_row = frame.iloc[idx + 1]
        timestamp = row["timestamp"].to_pydatetime()
        day_key = timestamp.date().isoformat()
        close_price = float(row["close"])
        next_open = float(next_row["open"])

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
                    )
                )
                entry_price = next_open
                shares = (equity * spec.risk.max_position_weight) / entry_price
                trade = Trade(
                    entry_time=next_row["timestamp"].to_pydatetime(),
                    entry_price=entry_price,
                    shares=shares,
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
                )
            )
            pnl = shares * (next_open - entry_price)
            equity += pnl
            if trade is not None:
                trade.exit_time = next_row["timestamp"].to_pydatetime()
                trade.exit_price = next_open
                trade.pnl = pnl
                trade.return_pct = (next_open / entry_price - 1) * 100
                trades.append(trade)
            in_position = False
            entry_price = 0.0
            shares = 0.0
            trade = None

    if in_position and shares:
        equity += shares * (float(frame.iloc[-1]["close"]) - entry_price)

    total_return_pct = (equity / start_equity - 1) * 100
    run = BacktestRun(
        run_id=current_run_id,
        strategy_name=spec.name,
        symbol=spec.primary_symbol,
        timeframe=spec.timeframe,
        bars=len(frame),
        signals=len(signals),
        trades=len(trades),
        start_equity=start_equity,
        end_equity=equity,
        total_return_pct=total_return_pct,
        assumptions=[
            "Signals are confirmed on bar close.",
            "Backtest fills use next bar open.",
            "Total return is period account-level return, not annualized.",
            "Position size uses max_position_weight; it is not all-in unless configured.",
            "Open positions are marked to the final close and not counted as closed trades.",
            "MVP examples are long-only and do not model commissions or slippage.",
        ],
    )
    return BacktestArtifacts(run=run, signals=signals, trades=trades)
