"""Backtest engine parity vs an independent pandas reference.

Runs six classic strategy specs against the 1000-bar synthetic daily fixture
and compares oc's BacktestRun output to a ground-truth reference implementation
written from scratch in pure numpy / pandas. All scalar metrics must match to
six significant figures.

This locks in:
  - signal_on=bar_close + fill_assumption=next_bar_open semantics
  - commission_pct and slippage_bps cost model
  - stop_loss_pct + take_profit_pct (close-vs-entry-price)
  - Sharpe / max drawdown / win rate / profit factor / annualized return
  - trade ledger (entry_price, exit_price, pnl)
  - Bollinger Bands, RSI (Wilder), SMA indicators

If this file fails, suspect a backtest engine, indicator, or cost-model regression.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from open_composer.adapters.data import load_ohlcv_for_spec
from open_composer.engines.backtest_engine import backtest_frame
from open_composer.models.strategy_spec import load_strategy_spec

ROOT = Path(__file__).resolve().parents[1]
AUDIT_SPECS = ROOT / "tests" / "fixtures" / "strategy_specs" / "audit"


def _rsi_wilder(series: pd.Series, period: int) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return (100 - 100 / (1 + rs)).fillna(100)


def _reference_run(
    df: pd.DataFrame,
    entry_rule,
    exit_rule,
    *,
    max_position_weight: float = 1.0,
    commission_pct: float = 0.0,
    slippage_bps: float = 0.0,
    stop_loss_pct: float | None = None,
    take_profit_pct: float | None = None,
    bars_per_year: int = 252,
    start_equity: float = 100_000.0,
) -> dict[str, float | int]:
    df = df.reset_index(drop=True).copy()
    df["entry"] = entry_rule(df).astype(bool)
    df["exit"] = exit_rule(df).astype(bool)
    commission_rate = commission_pct / 100.0
    slippage_rate = slippage_bps / 10_000.0

    equity = start_equity
    position = None
    entry_price = 0.0
    shares = 0.0
    trades = []
    total_fees = 0.0
    equity_curve = [start_equity]
    cur_trade = None

    for t in range(len(df) - 1):
        close = float(df["close"].iloc[t])
        nopen = float(df["open"].iloc[t + 1])
        if position == "long":
            mtm = equity + shares * (close - entry_price)
        else:
            mtm = equity
        equity_curve.append(mtm)

        entry_sig = bool(df["entry"].iloc[t])
        exit_sig = bool(df["exit"].iloc[t])
        stop_hit = (
            position == "long"
            and stop_loss_pct is not None
            and close <= entry_price * (1 - stop_loss_pct / 100)
        )
        take_hit = (
            position == "long"
            and take_profit_pct is not None
            and close >= entry_price * (1 + take_profit_pct / 100)
        )

        if position is None and entry_sig:
            fill = nopen * (1 + slippage_rate)
            shares = (equity * max_position_weight) / (fill * (1 + commission_rate))
            fee = shares * fill * commission_rate
            total_fees += fee
            equity -= fee
            entry_price = fill
            position = "long"
            cur_trade = {"entry_price": fill, "shares": shares}
        elif position == "long" and (exit_sig or stop_hit or take_hit):
            fill = nopen * (1 - slippage_rate)
            gross = shares * (fill - entry_price)
            fee = shares * fill * commission_rate
            total_fees += fee
            pnl = gross - fee
            equity += pnl
            cur_trade["exit_price"] = fill
            cur_trade["pnl"] = pnl
            trades.append(cur_trade)
            cur_trade = None
            position = None
            shares = 0.0
            entry_price = 0.0

    if position == "long" and shares > 0:
        equity += shares * (float(df["close"].iloc[-1]) - entry_price)
    equity_curve.append(equity)

    arr = np.array(equity_curve, dtype=float)
    rets = np.diff(arr) / arr[:-1]
    rets = rets[~np.isnan(rets)]
    if len(rets) >= 2 and rets.std(ddof=1) > 0:
        sharpe = rets.mean() / rets.std(ddof=1) * np.sqrt(bars_per_year)
    else:
        sharpe = None
    if equity > 0:
        ann_pct = ((equity / start_equity) ** (bars_per_year / (len(equity_curve) - 1)) - 1) * 100
    else:
        ann_pct = None
    running_max = np.maximum.accumulate(arr)
    max_dd_pct = (arr / running_max - 1).min() * 100
    pnls = [t["pnl"] for t in trades]
    if pnls:
        win_rate = sum(1 for p in pnls if p > 0) / len(pnls) * 100
        gp = sum(p for p in pnls if p > 0)
        gl = abs(sum(p for p in pnls if p < 0))
        pf = (gp / gl) if (gp > 0 and gl > 0) else None
    else:
        win_rate, pf = None, None

    return {
        "trades": len(trades),
        "end_equity": equity,
        "total_return_pct": (equity / start_equity - 1) * 100,
        "annualized_return_pct": ann_pct,
        "sharpe_ratio": sharpe,
        "max_drawdown_pct": max_dd_pct,
        "win_rate_pct": win_rate,
        "profit_factor": pf,
        "total_fees": total_fees,
        "first_trade": trades[0] if trades else None,
    }


def _bnh(d):
    return d["close"] > 0


def _never(d):
    return d["close"] < 0


def _sma_cross_entry(d):
    return d["close"].rolling(50).mean() > d["close"].rolling(200).mean()


def _sma_cross_exit(d):
    return d["close"].rolling(50).mean() < d["close"].rolling(200).mean()


def _rsi_entry(d):
    return _rsi_wilder(d["close"], 2) < 10


def _rsi_exit(d):
    return _rsi_wilder(d["close"], 2) > 70


def _bollinger_entry(d):
    sma = d["close"].rolling(window=20, min_periods=20).mean()
    std = d["close"].rolling(window=20, min_periods=20).std(ddof=0)
    return d["close"] < sma - std * 2.0


def _bollinger_exit(d):
    sma = d["close"].rolling(window=20, min_periods=20).mean()
    return d["close"] > sma


SCENARIOS = [
    pytest.param(
        "audit_buy_and_hold_daily",
        _bnh,
        _never,
        dict(),
        id="buy_and_hold_zero_costs",
    ),
    pytest.param(
        "audit_buy_and_hold_costs_daily",
        _bnh,
        _never,
        dict(commission_pct=0.05, slippage_bps=10.0),
        id="buy_and_hold_with_costs",
    ),
    pytest.param(
        "audit_sma_cross_daily",
        _sma_cross_entry,
        _sma_cross_exit,
        dict(),
        id="sma_50_200_cross",
    ),
    pytest.param(
        "audit_rsi_reversion_daily",
        _rsi_entry,
        _rsi_exit,
        dict(),
        id="rsi_2_mean_reversion",
    ),
    pytest.param(
        "audit_stop_take_daily",
        _rsi_entry,
        _rsi_exit,
        dict(stop_loss_pct=2.0, take_profit_pct=4.0),
        id="rsi_with_stop_take",
    ),
    pytest.param(
        "audit_bollinger_daily",
        _bollinger_entry,
        _bollinger_exit,
        dict(),
        id="bollinger_20_2sigma_reversion",
    ),
]


@pytest.mark.parametrize("spec_stem, entry_rule, exit_rule, kwargs", SCENARIOS)
def test_oc_backtest_matches_reference(spec_stem: str, entry_rule, exit_rule, kwargs: dict) -> None:
    """oc engine must match the independent reference to six significant figures."""
    spec_path = AUDIT_SPECS / f"{spec_stem}.yaml"
    spec = load_strategy_spec(spec_path)
    frame = load_ohlcv_for_spec(spec, ROOT, refresh=False)
    oc = backtest_frame(spec, frame, root=ROOT, run_id_value=f"parity-{spec_stem}")
    ref = _reference_run(
        frame[["timestamp", "open", "high", "low", "close", "volume"]],
        entry_rule,
        exit_rule,
        **kwargs,
    )

    def assert_close(name: str, oc_val, ref_val) -> None:
        if oc_val is None and ref_val is None:
            return
        assert oc_val is not None and ref_val is not None, (
            f"{spec_stem}: {name} mismatch (oc={oc_val} ref={ref_val})"
        )
        oc_f = float(oc_val)
        ref_f = float(ref_val)
        tol = max(abs(ref_f) * 1e-6, 1e-9)
        assert abs(oc_f - ref_f) <= tol, (
            f"{spec_stem}: {name} oc={oc_f:.10g} ref={ref_f:.10g} delta={oc_f - ref_f:.3e}"
        )

    assert oc.run.trades == ref["trades"], (
        f"{spec_stem}: trade count {oc.run.trades} != {ref['trades']}"
    )
    assert_close("end_equity", oc.run.end_equity, ref["end_equity"])
    assert_close("total_return_pct", oc.run.total_return_pct, ref["total_return_pct"])
    assert_close(
        "annualized_return_pct", oc.run.annualized_return_pct, ref["annualized_return_pct"]
    )
    assert_close("sharpe_ratio", oc.run.sharpe_ratio, ref["sharpe_ratio"])
    assert_close("max_drawdown_pct", oc.run.max_drawdown_pct, ref["max_drawdown_pct"])
    assert_close("win_rate_pct", oc.run.win_rate_pct, ref["win_rate_pct"])
    assert_close("profit_factor", oc.run.profit_factor, ref["profit_factor"])
    assert_close("total_fees", oc.run.total_fees, ref["total_fees"])

    if ref["first_trade"] is not None and oc.trades:
        oc_first = oc.trades[0]
        ref_first = ref["first_trade"]
        assert_close("first_trade.entry_price", oc_first.entry_price, ref_first["entry_price"])
        assert_close("first_trade.exit_price", oc_first.exit_price, ref_first["exit_price"])
        assert_close("first_trade.pnl", oc_first.pnl, ref_first["pnl"])
