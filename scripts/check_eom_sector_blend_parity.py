"""Parity: the paper engine's calendar-blend books vs the screen lane's C2.

Replays :func:`replay_eom_sector_blend_books` for a
``selection_rule=eom_reversal_sector_front_run_blend`` spec over the screen
lane's own session index, then checks three things against candidate C2 of
batch ``h20260928_20_recent_opt`` (card H-20260928-20):

1. the month-end signal sessions are the same;
2. the daily target-weight frame equals ``screen_lane.weights_frame``;
3. the engine frame, run through the lane's frozen simulator at 10 and 20 bp,
   reproduces the lane's stored ``C2__o00__net10``/``net20`` daily returns and
   its anchor/holdout/stress Sharpe ratios.

The engine reads prices through its own loader
(:func:`load_price_panel`), not the lane's, so the check also covers the two
data paths. Writes a JSON verdict; exit code 1 on any mismatch.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts" / "screen_batches"))

import h20260928_20_recent_opt as batch  # noqa: E402
import screen_batch  # noqa: E402
import screen_lane as lane  # noqa: E402

from open_composer.adapters.execution.rotation_target_weights import (  # noqa: E402
    _symbol_series,
    load_price_panel,
    replay_eom_sector_blend_books,
)
from open_composer.models.strategy_spec import load_strategy_spec  # noqa: E402

DEFAULT_SPEC = "strategy_specs/drafts/us_etf_eom_sector_blend_monthly.yaml"
DEFAULT_OUT = "reports/paper/launch/2026-09-30-us_etf_eom_sector_blend_monthly-parity.json"
LANE_RETURNS = "reports/research/screens/h20260928_20_recent_opt/returns.parquet"
LANE_LEADERBOARD = "reports/research/screens/h20260928_20_recent_opt/leaderboard.json"
TOLERANCE = 1e-12


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--spec", default=DEFAULT_SPEC)
    parser.add_argument("--out", default=DEFAULT_OUT)
    args = parser.parse_args(argv)

    spec = load_strategy_spec(ROOT / args.spec)
    cfg = spec.portfolio.etf_rotation
    if cfg is None or cfg.eom_sector_blend is None:
        raise SystemExit(f"{args.spec} is not an eom sector blend spec")
    candidates = screen_batch.candidates_from_module(batch)
    c2 = next(c for c in candidates if c.id == "C2")
    close, _open, leg_open, leg_close, rf = lane.load_batch_panel(
        candidates, getattr(batch, "extend_panel", None)
    )
    lane_frame, lane_dates = lane.weights_frame(close, c2, 0)

    symbols = sorted({*cfg.menu, cfg.cash_symbol})
    years = range(int(close.index[0].year), int(close.index[-1].year) + 1)
    panel = load_price_panel(ROOT, symbols, list(years))
    panel = panel.loc[panel["trade_date"] <= close.index[-1].date()]
    series = {symbol: _symbol_series(panel, symbol) for symbol in symbols}
    sessions = [stamp.date() for stamp in close.index]
    engine_frame, engine_dates = replay_eom_sector_blend_books(
        series,
        sessions,
        menu=cfg.menu,
        cash_symbol=cfg.cash_symbol,
        reversal_symbol=cfg.eom_sector_blend.reversal_symbol,
        reversal_weight=cfg.eom_sector_blend.reversal_weight,
        top_n=cfg.top_n,
    )
    engine_frame.index = close.index

    # The lane treats the panel's last row as a month end; the engine asks the
    # market calendar. Neither can act on the last row, so compare the rest.
    lane_signals = {stamp.date() for stamp in lane_dates if stamp < close.index[-1]}
    engine_signals = {day for day in engine_dates if day < sessions[-1]}
    columns_match = sorted(engine_frame.columns) == sorted(lane_frame.columns)
    aligned = engine_frame.reindex(columns=lane_frame.columns, fill_value=0.0)
    weight_diff = (aligned - lane_frame).abs()
    bad_sessions = weight_diff.index[weight_diff.max(axis=1) > TOLERANCE]

    stored = pd.read_parquet(ROOT / LANE_RETURNS)
    leaderboard = json.loads((ROOT / LANE_LEADERBOARD).read_text(encoding="utf-8"))
    judged = next(row for row in leaderboard["candidates"] if row["id"] == "C2")["judged"]
    first_valid = lane.first_valid_signal_date(close, c2)
    scale = np.ones(len(close.index))
    ret10, turn10 = lane.salvage.simulate(aligned, leg_open, leg_close, scale, 10.0)
    ret20, turn20 = lane.salvage.simulate(aligned, leg_open, leg_close, scale, 20.0)
    returns: dict[str, dict[str, object]] = {}
    for column, ret in (("C2__o00__net10", ret10), ("C2__o00__net20", ret20)):
        common = stored.index.intersection(ret.index)
        returns[column] = {
            "sessions_compared": len(common),
            "max_abs_diff": float((ret.loc[common] - stored[column].loc[common]).abs().max()),
        }
    sharpe: dict[str, dict[str, float]] = {}
    for window_name in ("select", "anchor", "holdout", "stress"):
        window = lane.WINDOWS[window_name]
        metrics, _start = lane.evaluate_offset_window(
            ret10, turn10, ret20, turn20, rf, window, first_valid
        )
        sharpe[window_name] = {
            "engine_net10": float(metrics["net10"]["sharpe"]),
            "lane_net10": float(judged[window_name]["sharpe"]),
        }

    sharpe_ok = all(abs(row["engine_net10"] - row["lane_net10"]) <= 1e-9 for row in sharpe.values())
    returns_ok = all(row["max_abs_diff"] <= TOLERANCE for row in returns.values())
    passed = (
        columns_match
        and lane_signals == engine_signals
        and len(bad_sessions) == 0
        and returns_ok
        and sharpe_ok
    )
    verdict = {
        "generated_at": datetime.now(UTC).isoformat(),
        "spec": args.spec,
        "lane_candidate": "h20260928_20_recent_opt:C2",
        "sessions": [sessions[0].isoformat(), sessions[-1].isoformat(), len(sessions)],
        "signal_sessions_compared": len(lane_signals),
        "signal_sessions_only_in_lane": sorted(
            d.isoformat() for d in lane_signals - engine_signals
        ),
        "signal_sessions_only_in_engine": sorted(
            d.isoformat() for d in engine_signals - lane_signals
        ),
        "weight_columns_match": columns_match,
        "weight_max_abs_diff": float(weight_diff.to_numpy().max()),
        "weight_mismatch_sessions": [stamp.date().isoformat() for stamp in bad_sessions[:50]],
        "weight_mismatch_session_count": len(bad_sessions),
        "returns": returns,
        "sharpe_by_window": sharpe,
        "tolerance": TOLERANCE,
        "passed": passed,
    }
    out = ROOT / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(verdict, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(verdict, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
