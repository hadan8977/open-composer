"""Parity of the paper volatility-target overlay with the research engine.

For every session ``t`` in the comparison window this rebuilds what the paper
adapter would decide after the ``t`` close -- the unscaled book and the
multiplier for session ``t + 1`` -- from the adapter's own panel loader and
selection rule, seeing only the three calendar years of data the live adapter
loads. It then compares that decision with the research engine that froze
the renewal rules (``scripts/run_h20260922_05_salvage.py``: ``sleeve_weights``,
``simulate``, ``vol_scale``, ``dip_signal``, ``boost_window``) at ``t + 1``.

Usage::

    uv run python scripts/check_rotation_overlay_parity.py
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import run_h20260922_05_salvage as research  # noqa: E402

from open_composer.adapters.execution.rotation_overlay import (  # noqa: E402
    apply_multiplier,
    decide_overlay,
)
from open_composer.adapters.execution.rotation_target_weights import (  # noqa: E402
    _symbol_series,
    load_price_panel,
    replay_books,
)
from open_composer.models.strategy_spec import load_strategy_spec  # noqa: E402

SLEEVES = {
    "s3": "strategy_specs/drafts/us_etf_levered_rotation_63_top2_monthly.yaml",
    "s2": "strategy_specs/drafts/us_etf_growth_rotation_blend_top2_monthly.yaml",
}
OUT_DIR = ROOT / "reports" / "paper" / "renewal"


def research_schedule(close, open_, key: str, cfg) -> tuple[pd.DataFrame, np.ndarray]:
    leg_open, leg_close = research.legs(close, open_)
    weights, signal_dates = research.sleeve_weights(close, key)
    gross, _ = research.simulate(weights, leg_open, leg_close, np.ones(len(close.index)), 0.0)
    vol = cfg.vol_target
    boost = None
    boost_target = None
    if vol.dip_boost is not None:
        boost = research.boost_window(research.dip_signal(close), vol.dip_boost.hold_sessions)
        boost_target = vol.dip_boost.target_annual_vol
    sched = research.vol_scale(
        close.index, signal_dates, gross, vol.target_annual_vol, boost, boost_target
    )
    return weights, sched


def compare(key: str, start: str, end: str) -> dict:
    spec = load_strategy_spec(ROOT / SLEEVES[key])
    cfg = spec.portfolio.etf_rotation
    vol = cfg.vol_target
    close, open_ = research.base.load_panel(research.symbols())
    r_weights, r_sched = research_schedule(close, open_, key, cfg)
    cash = cfg.cash_symbol
    book_cols = sorted({*cfg.menu, cash})
    symbols = sorted({*book_cols, *([vol.dip_boost.signal_symbol] if vol.dip_boost else [])})
    panel = load_price_panel(ROOT, symbols, [2022, 2023, 2024, 2025, 2026])
    series_all = {s: _symbol_series(panel, s) for s in symbols}
    idx = [d.date() for d in close.index]
    rows = []
    for i, t in enumerate(idx[:-1]):
        if not (date.fromisoformat(start) <= t <= date.fromisoformat(end)):
            continue
        lo = date(t.year - 2, 1, 1)
        view = panel.loc[(panel["trade_date"] >= lo) & (panel["trade_date"] <= t)]
        series = {
            s: ([d for d in ds if lo <= d <= t], {d: c for d, c in cs.items() if lo <= d <= t})
            for s, (ds, cs) in series_all.items()
        }
        book_view = view.loc[view["symbol"].isin(book_cols)]
        sessions = sorted(set(book_view["trade_date"]))
        kwargs = dict(
            menu=cfg.menu,
            cash_symbol=cash,
            lookbacks=cfg.lookbacks,
            top_n=cfg.top_n,
            rebalance=cfg.rebalance,
            absolute_momentum_filter=cfg.absolute_momentum_filter,
            min_history_sessions=cfg.min_history_sessions,
            unfilled_slot_policy=cfg.unfilled_slot_policy,
        )
        weights, signals = replay_books(series, sessions, **kwargs)
        ext, _ = replay_books(series, [*sessions, idx[i + 1]], **kwargs)
        book_next = {s: float(w) for s, w in ext.iloc[-1].items() if w > 0}
        c = book_view.pivot(index="trade_date", columns="symbol", values="close")
        o = book_view.pivot(index="trade_date", columns="symbol", values="open")
        dip = None
        if vol.dip_boost is not None:
            ds, cs = series[vol.dip_boost.signal_symbol]
            dip = pd.Series([cs[d] for d in ds], index=ds, dtype=float)
        boost = vol.dip_boost
        decision = decide_overlay(
            sessions,
            weights,
            c.reindex(index=sessions, columns=book_cols),
            o.reindex(index=sessions, columns=book_cols),
            signals,
            base_target=vol.target_annual_vol,
            realized_vol_sessions=vol.realized_vol_sessions,
            dip_close=dip,
            sma_sessions=boost.sma_sessions if boost else 200,
            rsi_sessions=boost.rsi_sessions if boost else 10,
            rsi_below=boost.rsi_below if boost else 30.0,
            boost_target=boost.target_annual_vol if boost else None,
            hold_sessions=boost.hold_sessions if boost else None,
        )
        research_book = {
            s: float(w) for s, w in r_weights.iloc[i + 1].items() if w > 0 and s in book_cols
        }
        live_final = apply_multiplier(
            {**{s: 0.0 for s in book_cols}, **book_next}, decision.multiplier, cash
        )
        research_final = apply_multiplier(
            {**{s: 0.0 for s in book_cols}, **research_book}, float(r_sched[i + 1]), cash
        )
        rows.append(
            {
                "decision_close": t.isoformat(),
                "session": idx[i + 1].isoformat(),
                "live_multiplier": decision.multiplier,
                "research_multiplier": float(r_sched[i + 1]),
                "multiplier_abs_diff": abs(decision.multiplier - float(r_sched[i + 1])),
                "book_match": book_next == research_book,
                "max_weight_abs_diff": max(
                    abs(live_final.get(s, 0.0) - research_final.get(s, 0.0)) for s in book_cols
                ),
                "boost_active": decision.boost_active,
            }
        )
    frame = pd.DataFrame(rows)
    worst = frame.sort_values("max_weight_abs_diff", ascending=False).head(5)
    return {
        "sleeve": key,
        "spec": SLEEVES[key],
        "window": [start, end],
        "sessions_compared": len(frame),
        "book_mismatches": int((~frame["book_match"]).sum()),
        "multiplier_max_abs_diff": float(frame["multiplier_abs_diff"].max()),
        "weight_max_abs_diff": float(frame["max_weight_abs_diff"].max()),
        "sessions_with_weight_diff_over_1e-6": int((frame["max_weight_abs_diff"] > 1e-6).sum()),
        "boost_sessions": int(frame["boost_active"].sum()),
        "multiplier_range": [float(frame["live_multiplier"].min()), 1.0],
        "worst_sessions": worst.to_dict(orient="records"),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", default="2025-03-03")
    parser.add_argument("--end", default="2026-09-16")
    parser.add_argument("--sleeve", choices=sorted(SLEEVES), action="append")
    args = parser.parse_args(argv)
    results = [compare(key, args.start, args.end) for key in (args.sleeve or ["s3", "s2"])]
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / "2026-09-23-overlay-parity.json"
    out.write_text(json.dumps(results, indent=2, default=str) + "\n", encoding="utf-8")
    for result in results:
        print(
            f"{result['sleeve']}: {result['sessions_compared']} sessions, book mismatches "
            f"{result['book_mismatches']}, multiplier max diff "
            f"{result['multiplier_max_abs_diff']:.2e}, weight max diff "
            f"{result['weight_max_abs_diff']:.2e}, boost sessions {result['boost_sessions']}"
        )
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
