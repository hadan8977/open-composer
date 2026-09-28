"""H-20260928-40 batch screening: factor-style and narrow-industry ETF menus
under the exact same cross-sectional momentum rotation mechanism S1-S3 already
use (`scripts/run_h20260918_05_recent_menu.py:rotation_cell`), for
`scripts/screen_batch.py --batch h20260928_40_equity_etf_menus --iteration
h20260928_40_equity_etf_menus`.

Reuses, unedited: `run_h20260918_05_recent_menu.momentum_score` --
`close.pct_change(lookback, fill_method=None)` -- the exact same lookback-return
definition S1-S3's `rotation_cell` uses for every candidate's ranking score. No
new momentum formula, absolute-momentum rule or weighting scheme is
introduced; only the menu (ticker list) changes.

Two new menus (12 grid cells each = 24 candidates total), both long-only and
Alpaca-tradable:
  FACTOR   MTUM, QUAL, USMV, VLUE, SIZE (5 single-factor style ETFs). Source:
           Quantpedia "Momentum Factor and Style Rotation Effect"
           (https://quantpedia.com/strategies/momentum-factor-and-style-rotation-effect,
           12-1-month cross-sectional momentum long-short across 6 Russell
           style ETFs, 1972-2005, 9.25%/yr, Sharpe 0.33) -- old, long-short,
           pre-2006 sample; only the *mechanism* (cross-sectional momentum
           rotation across style ETFs) is reused, not this number, which is
           why K1/K2 are tested fresh rather than assumed.
  INDUSTRY SMH, XBI, KRE, ITB, IGV, XOP, XRT, IHI (8 narrow industry ETFs).
           Source: S1's own live/backtested record (the same engine, 11
           broad SPDR sectors, median-offset anchor Sharpe 1.33-1.35).
           Counter-evidence considered: Molchanov & Stangl, "The Myth of
           Sector Rotation" (PDF blocked by Cloudflare in every fetch
           attempt this session, see the source card) refutes
           macro-economic-cycle-based sector *prediction*, a different
           mechanism from the price-trend cross-sectional momentum used
           here -- it does not refute this candidate set, but is recorded
           as the negative-evidence check performed before testing anyway.

Grid: lookback in {63, 126, 252} trading days x top_n in {1, 2} x rebalance
in {monthly ("M"), weekly ("W")}. Candidate id:
`{MENU}_L{lookback}_N{top_n}_{MO|WK}`.

Rule per candidate (identical mechanism to `rotation_cell`, only the menu
differs): at each rebalance date, rank the available menu tickers by
`momentum_score(close, str(lookback))`; take the top `top_n`; apply the
absolute-momentum filter -- a pick is kept only if its score beats SHY's own
score over the same lookback at that date, exactly like `rotation_cell`'s
`chosen = [s for s in chosen if row[s] > cs]`; equal-weight the survivors.
A candidate never returns SHY itself -- the screening lane's own
`ScreenCandidate.weights_fn` remainder convention puts any unallocated
weight into SHY automatically, matching `rotation_cell`'s own "leave the
slot to CASH" behavior for a rejected pick.
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import run_h20260918_05_recent_menu as base  # noqa: E402

CASH = base.CASH  # "SHY"

FACTOR_MENU: tuple[str, ...] = ("MTUM", "QUAL", "USMV", "VLUE", "SIZE")
INDUSTRY_MENU: tuple[str, ...] = ("SMH", "XBI", "KRE", "ITB", "IGV", "XOP", "XRT", "IHI")

LOOKBACKS: tuple[int, ...] = (63, 126, 252)
TOP_NS: tuple[int, ...] = (1, 2)
REBAL_FREQ: dict[str, str] = {"MO": "M", "WK": "W"}

_MENUS: dict[str, tuple[str, ...]] = {"FACTOR": FACTOR_MENU, "INDUSTRY": INDUSTRY_MENU}
_SOURCE_CARDS: dict[str, str] = {
    "FACTOR": "quantpedia_momentum_factor_style_rotation_2026",
    "INDUSTRY": "s1_live_record_and_molchanov_stangl_placebo_check_2026",
}


def make_rotation_fn(
    menu: tuple[str, ...], lookback: int, top_n: int
) -> Callable[[pd.DataFrame, pd.Timestamp], dict[str, float]]:
    """Cross-sectional momentum rotation, identical mechanism to
    `run_h20260918_05_recent_menu.rotation_cell`'s per-date pick loop: rank
    `menu` by `base.momentum_score(hist, str(lookback))` (imported unedited),
    take the top `top_n`, keep only picks whose score beats SHY's own score
    over the same lookback (absolute-momentum filter), equal-weight the
    survivors. Reads only `close.loc[:asof]` -- never a later row."""

    def fn(close: pd.DataFrame, asof: pd.Timestamp) -> dict[str, float]:
        hist = close.loc[:asof]
        cols = [s for s in menu if s in hist.columns]
        if not cols or CASH not in hist.columns:
            return {}
        score = base.momentum_score(hist, str(lookback))
        if asof not in score.index:
            return {}
        row = score.loc[asof, cols].dropna()
        if row.empty:
            return {}
        cash_score = score.loc[asof, CASH]
        if pd.isna(cash_score):
            return {}
        chosen = list(row.sort_values(ascending=False).index[:top_n])
        chosen = [s for s in chosen if row[s] > cash_score]
        if not chosen:
            return {}
        w = 1.0 / len(chosen)
        return {s: w for s in chosen}

    return fn


SPECS: list[dict] = []
for _menu_name, _menu in _MENUS.items():
    for _lb in LOOKBACKS:
        for _tn in TOP_NS:
            for _rebal_id, _freq in REBAL_FREQ.items():
                _cand_id = f"{_menu_name}_L{_lb}_N{_tn}_{_rebal_id}"
                SPECS.append(
                    {
                        "id": _cand_id,
                        "name": (
                            f"{_menu_name} menu cross-sectional momentum rotation, "
                            f"lookback={_lb}d, top_n={_tn}, rebal={_rebal_id}"
                        ),
                        "source_card": _SOURCE_CARDS[_menu_name],
                        "universe": _menu,
                        "freq": _freq,
                        "fn": make_rotation_fn(_menu, _lb, _tn),
                    }
                )

assert len(SPECS) == 24
assert len({spec["id"] for spec in SPECS}) == 24
