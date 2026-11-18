"""Backtest the four live ETF sleeves over 2026 YTD and 2026-09-01..now.

Reuses the production selection engine (``rotation_target_weights.replay_*``)
and the research lane's frozen accounting/overlay helpers
(``run_h20260922_05_salvage``), so the numbers come from the same code the
paper sleeves and the cards' screens used. Prices are the local SIP archive;
costs are the spec's own 10 bp per unit traded. No broker access, no order.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import run_h20260918_05_recent_menu as base  # noqa: E402
import run_h20260922_05_salvage as salvage  # noqa: E402

from open_composer.adapters.execution.rotation_target_weights import (  # noqa: E402
    _symbol_series,
    load_price_panel,
    replay_books,
    replay_eom_sector_blend_books,
)
from open_composer.models.strategy_spec import load_strategy_spec  # noqa: E402

COST_BPS = 10.0
WINDOWS = {
    "2026 YTD": ("2026-01-02", "2026-11-06"),
    "2026-09-01 至今": ("2026-09-01", "2026-11-06"),
}
# Card reference windows, used only to prove this harness reproduces the numbers
# the sleeves were accepted on.
REFERENCE = {"C2 anchor 2024-01-08..2026-09-17": ("2024-01-08", "2026-09-17")}


def rotate_frame(panel: pd.DataFrame, symbols: list[str]) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows = panel.loc[panel["symbol"].isin(symbols)]
    close = rows.pivot(index="trade_date", columns="symbol", values="close").sort_index()
    open_ = rows.pivot(index="trade_date", columns="symbol", values="open").sort_index()
    close.index = pd.to_datetime(close.index)
    open_.index = pd.to_datetime(open_.index)
    return close, open_


def sleeve_returns(spec_path: Path, last_session: date):
    spec = load_strategy_spec(spec_path)
    rot = spec.portfolio.etf_rotation
    menu = [s.upper() for s in rot.menu]
    cash = rot.cash_symbol.upper()
    extra = [str(rot.vol_target.dip_boost.signal_symbol).upper()] if rot.vol_target and (
        rot.vol_target.dip_boost
    ) else []
    symbols = sorted({*menu, cash, "BIL", *extra})
    panel = load_price_panel(ROOT, symbols, list(range(2016, 2027)))
    panel = panel.loc[panel["trade_date"] <= last_session]
    close, open_ = rotate_frame(panel, symbols)
    close = close[[c for c in close.columns if c in symbols]]
    open_ = open_[close.columns]
    columns = sorted({*menu, cash})
    close = close.reindex(columns=columns)
    open_ = open_.reindex(columns=columns)
    sessions = close.index
    risk_free = (close_risk_free(panel, sessions))
    days = [d.date() for d in close.index]
    series = {
        symbol: (
            days,
            dict(zip(days, close[symbol].to_numpy(float), strict=True)),
        )
        for symbol in columns
    }
    if rot.selection_rule and "eom_reversal" in str(rot.selection_rule):
        weights, signals = replay_eom_sector_blend_books(
            series,
            [d.date() for d in sessions],
            menu=menu,
            cash_symbol=cash,
            reversal_symbol=rot.eom_sector_blend.reversal_symbol.upper(),
            reversal_weight=float(rot.eom_sector_blend.reversal_weight),
            top_n=int(rot.top_n),
        )
    else:
        weights, signals = replay_books(
            series,
            [d.date() for d in sessions],
            menu=menu,
            cash_symbol=cash,
            lookbacks=[int(x) for x in rot.lookbacks],
            top_n=int(rot.top_n),
            rebalance=str(rot.rebalance),
            absolute_momentum_filter=bool(rot.absolute_momentum_filter),
            min_history_sessions=int(rot.min_history_sessions),
            unfilled_slot_policy=str(rot.unfilled_slot_policy),
        )
    weights.index = pd.to_datetime(weights.index)
    weights = weights.reindex(index=sessions, columns=columns).fillna(0.0)
    signal_dates = [pd.Timestamp(day) for day in signals]
    leg_open = (open_ / close.shift(1) - 1.0).fillna(0.0)
    leg_close = (close / open_ - 1.0).fillna(0.0)
    gross, _ = salvage.simulate(weights, leg_open, leg_close, np.ones(len(sessions)), 0.0)
    scale = np.ones(len(sessions))
    overlay = None
    if rot.vol_target is not None:
        boost = None
        boost_target = None
        if rot.vol_target.dip_boost is not None:
            dip = rot.vol_target.dip_boost
            qqq = panel.loc[panel["symbol"] == str(dip.signal_symbol).upper()]
            qqq_close = pd.Series(qqq["close"].to_numpy(float), index=pd.to_datetime(qqq["trade_date"]))
            qqq_close = qqq_close.reindex(sessions).ffill()
            saved = (
                salvage.DIP_ASSET,
                salvage.DIP_SMA,
                salvage.DIP_RSI_WINDOW,
                salvage.DIP_RSI_LEVEL,
            )
            salvage.DIP_ASSET = str(dip.signal_symbol).upper()
            salvage.DIP_SMA = int(dip.sma_sessions)
            salvage.DIP_RSI_WINDOW = int(dip.rsi_sessions)
            salvage.DIP_RSI_LEVEL = float(dip.rsi_below)
            frame = pd.DataFrame({salvage.DIP_ASSET: qqq_close})
            signal = salvage.dip_signal(frame)
            salvage.DIP_ASSET, salvage.DIP_SMA, salvage.DIP_RSI_WINDOW, salvage.DIP_RSI_LEVEL = saved
            boost = salvage.boost_window(signal, int(dip.hold_sessions))
            boost_target = float(dip.target_annual_vol)
        scale = salvage.vol_scale(
            sessions,
            signal_dates,
            gross,
            float(rot.vol_target.target_annual_vol),
            boost,
            boost_target,
        )
        overlay = dict(
            target=float(rot.vol_target.target_annual_vol),
            boost_target=boost_target,
            share_scaled=float((scale < 0.999).mean()),
            min_scale=float(np.min(scale)),
            mean_scale=float(np.mean(scale)),
        )
    ret, turnover = salvage.simulate(weights, leg_open, leg_close, scale, COST_BPS)
    return dict(
        spec=spec_path.name,
        name=spec.name,
        menu=menu,
        cash=cash,
        rebalances=len(signal_dates),
        overlay=overlay,
        returns=ret,
        turnover=turnover,
        risk_free=risk_free,
        weights=weights,
        scale=pd.Series(scale, index=sessions),
    )


def close_risk_free(panel: pd.DataFrame, sessions: pd.DatetimeIndex) -> pd.Series:
    """BIL daily return as the risk-free leg; the local archive lags a little,
    so a missing session contributes 0 rather than dropping the session."""
    rows = panel.loc[panel["symbol"] == "BIL"]
    series = pd.Series(rows["close"].to_numpy(float), index=pd.to_datetime(rows["trade_date"]))
    series = series.reindex(sessions).ffill()
    return (series / series.shift(1) - 1.0).fillna(0.0)


def window_stats(ret: pd.Series, turnover: pd.Series, start: str, end: str, rf=None) -> dict:
    rf = pd.Series(0.0, index=ret.index) if rf is None else rf.reindex(ret.index).fillna(0.0)
    mask = (ret.index >= pd.Timestamp(start)) & (ret.index <= pd.Timestamp(end))
    m = base.metrics(ret.loc[mask], rf.loc[mask], turnover.loc[mask])
    window = ret.loc[mask]
    equity = (1.0 + window).cumprod()
    return dict(
        sessions=int(len(window)),
        net_return_pct=float((equity.iloc[-1] - 1.0) * 100) if len(window) else None,
        cagr_pct=None if not np.isfinite(m.cagr) else float(m.cagr * 100),
        sharpe=None if not np.isfinite(m.sharpe) else float(m.sharpe),
        vol_pct=None if not np.isfinite(m.vol) else float(m.vol * 100),
        max_dd_pct=None if not np.isfinite(m.max_dd) else float(m.max_dd * 100),
        turnover_x_year=float(m.turnover_yr),
        hit_month=float(m.hit_month),
        best_day_pct=float(window.max() * 100) if len(window) else None,
        worst_day_pct=float(window.min() * 100) if len(window) else None,
        peak_equity=float(equity.max()),
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--last-session", default="2026-11-06")
    parser.add_argument("--out", type=Path, default=ROOT / "reports/backtests/running-sleeves-20261109.json")
    args = parser.parse_args()
    last = date.fromisoformat(args.last_session)
    specs = [
        "us_etf_sector_rotation_252_top2_weekly",
        "us_etf_growth_rotation_blend_top2_monthly",
        "us_etf_levered_rotation_63_top2_monthly",
        "us_etf_eom_sector_blend_monthly",
    ]
    results, out = {}, {}
    for name in specs:
        path = ROOT / "strategy_specs/drafts" / f"{name}.yaml"
        result = sleeve_returns(path, last)
        results[name] = result
        windows = {
            label: window_stats(
                result["returns"], result["turnover"], *span, rf=result["risk_free"]
            )
            for label, span in WINDOWS.items()
        }
        reference = {
            label: window_stats(
                result["returns"], result["turnover"], *span, rf=result["risk_free"]
            )
            for label, span in REFERENCE.items()
            if name == "us_etf_eom_sector_blend_monthly"
        }
        out[name] = dict(
            spec=str(path.relative_to(ROOT)),
            menu=result["menu"],
            cash=result["cash"],
            rebalances=result["rebalances"],
            overlay=result["overlay"],
            cost_bps=COST_BPS,
            last_session=str(last),
            windows=windows,
            reference_windows=reference,
        )
        print(f"\n=== {name}")
        print(f"  menu={result['menu']} cash={result['cash']} rebalances={result['rebalances']}")
        if result["overlay"]:
            print(f"  overlay={result['overlay']}")
        for label, stats in windows.items():
            print(
                f"  {label:16s} net={stats['net_return_pct']:+7.2f}%  sharpe={stats['sharpe']:5.2f}  "
                f"vol={stats['vol_pct']:5.1f}%  maxDD={stats['max_dd_pct']:6.2f}%  "
                f"sessions={stats['sessions']}  turn={stats['turnover_x_year']:.1f}x/y"
            )
        for label, stats in reference.items():
            print(
                f"  [{label}] net={stats['net_return_pct']:+7.2f}% sharpe={stats['sharpe']:.2f} "
                f"maxDD={stats['max_dd_pct']:.2f}% (expect Sharpe 1.60, 21.1%/yr, -6.6% max DD)"
            )
    # Monthly detail for the live sleeves, YTD only.
    months = {}
    for name, result in results.items():
        ret = result["returns"]
        ytd = ret.loc[ret.index >= pd.Timestamp("2026-01-01")]
        months[name] = {
            str(period): float((1.0 + group).prod() - 1.0) * 100
            for period, group in ytd.groupby(ytd.index.to_period("M"))
        }
    out["_monthly_2026_pct"] = months
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(out, indent=1) + "\n")
    print(f"\nwritten {args.out}")
    print("\n月份       " + "".join(f"{n.split('us_etf_')[1][:14]:>16s}" for n in specs))
    for period in sorted({p for m in months.values() for p in m}):
        print(
            f"{period} "
            + "".join(f"{months[n].get(period, float('nan')):>16.2f}" for n in specs)
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
