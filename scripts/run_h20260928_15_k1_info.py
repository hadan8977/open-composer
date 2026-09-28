"""T-20260928-15: K1 info-only check (not part of the decision rule).

Reports the batch's SELECT-chosen factor's (F10, sign fixed from SELECT) top-
50 20bp book Sharpe over the two windows the project's own frozen K1 promotion
bar uses (``docs/runbook-autonomous-round.zh.md`` section 5, mirrored in
``scripts/screen_lane.py``'s ``WINDOWS`` constant, imported unmodified rather
than retyped): anchor 2024-01-08..2026-09-17 (>=1.19) and stress
2016-05-02..2023-09-15 (>=0.65). This is a single-offset lean book (same
primitives as the runner's ``_simple_book_test_window``), not screen_lane's
full multi-offset date-neutral K1 book -- explicitly info-only, never a
promotion decision, and not part of T-20260928-15's own done_when rule (TEST
rank IC + TEST 20bp book Sharpe on the runner's own TEST_WINDOW).

Usage: scripts/run_capped.sh --mem 1.8G -- uv run python \\
    scripts/run_h20260928_15_k1_info.py
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from open_composer.research.signal_card import (  # noqa: E402
    book_returns,
    equal_weight,
    hold,
    load_market,
    load_signal,
    masked_ranks,
    topk_cohorts,
)
from scripts.screen_lane import WINDOWS  # noqa: E402

ITER_ID = "h20260928_15_claude_factor_batch"
OUT_DIR = ROOT / "reports" / "research" / "iterations" / ITER_ID
BATCH_DIR = ROOT / "data" / "features" / "h20260928_15_claude_factors"
BATCH_WINNER = "F10_quality_composite_roe_profitability_accruals"
SIGN_FROM_SELECT = 1  # select-results.json: F10 sign_from_select = 1
TOP_K = 50
BOOK_H = 20
BOOK_COST_BPS = (10.0, 20.0)
K1_ANCHOR_SHARPE_MIN = 1.19
K1_STRESS_SHARPE_MIN = 0.65


def _window_mask(dates: pd.DatetimeIndex, window: tuple[str, str]) -> pd.Series:
    start, end = pd.Timestamp(window[0]), pd.Timestamp(window[1])
    return (dates >= start) & (dates <= end)


def main() -> int:
    market = load_market(top_n=1000, memory_limit="1200MB")
    ret = market.next_open_returns()
    member = market.member()
    signal = load_signal(
        market, source=str(BATCH_DIR / f"{BATCH_WINNER}.parquet"), column=BATCH_WINNER
    )
    sig = signal * SIGN_FROM_SELECT
    rs = masked_ranks(sig, member)
    cohorts = topk_cohorts(rs, member, TOP_K)
    held = hold(cohorts, BOOK_H)
    bench = equal_weight(member, ret)

    out: dict = {
        "iter_id": ITER_ID,
        "check": "K1_info_only_not_a_decision_gate",
        "candidate_id": BATCH_WINNER,
        "sign_from_select": SIGN_FROM_SELECT,
        "k1_anchor_window": list(WINDOWS["anchor"]),
        "k1_stress_window": list(WINDOWS["stress"]),
        "k1_anchor_sharpe_min": K1_ANCHOR_SHARPE_MIN,
        "k1_stress_sharpe_min": K1_STRESS_SHARPE_MIN,
        "windows": {},
    }
    for label, window in (("anchor", WINDOWS["anchor"]), ("stress", WINDOWS["stress"])):
        mask = _window_mask(market.dates, window)
        window_out: dict = {}
        for bps in BOOK_COST_BPS:
            net, _turn = book_returns(held, ret, bps)
            net_s = pd.Series(net, index=market.dates)[mask]
            bench_s = pd.Series(bench, index=market.dates)[mask]
            sd = net_s.std()
            years = len(net_s) / 252.0
            cum = (1.0 + net_s).cumprod()
            window_out[f"{int(bps)}bp"] = {
                "n_days": int(len(net_s)),
                "cagr": float(cum.iloc[-1] ** (1.0 / years) - 1.0)
                if cum.iloc[-1] > 0 and years > 0
                else None,
                "sharpe": float(net_s.mean() / sd * math.sqrt(252.0)) if sd > 0 else None,
                "excess_ann": float((net_s - bench_s).mean() * 252.0),
            }
        out["windows"][label] = window_out

    anchor_20bp = out["windows"]["anchor"]["20bp"]["sharpe"]
    stress_20bp = out["windows"]["stress"]["20bp"]["sharpe"]
    out["k1_anchor_pass"] = anchor_20bp is not None and anchor_20bp >= K1_ANCHOR_SHARPE_MIN
    out["k1_stress_pass"] = stress_20bp is not None and stress_20bp >= K1_STRESS_SHARPE_MIN

    out_path = OUT_DIR / "k1-info.json"
    out_path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"[h20260928_15_k1_info] wrote {out_path}")
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
