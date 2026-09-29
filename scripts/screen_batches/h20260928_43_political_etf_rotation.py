"""H-20260928-43 batch screening: political/congressional-trade-replica ETFs
vs. a matched big-tech placebo, under the exact same cross-sectional momentum
rotation mechanism S1-S3 already use
(`scripts/run_h20260918_05_recent_menu.py:rotation_cell`), for
`scripts/screen_batch.py --batch h20260928_43_political_etf_rotation
--iteration h20260928_43_political_etf_rotation`.

Reuses, unedited: `run_h20260918_05_recent_menu.momentum_score` --
`close.pct_change(lookback, fill_method=None)` -- the exact same lookback-return
definition S1-S3's `rotation_cell` uses for every candidate's ranking score. No
new momentum formula, absolute-momentum rule or weighting scheme is
introduced; only the menu (ticker list) changes.

Two menus (12 grid cells each = 24 candidates total), both long-only and
Alpaca-tradable:
  POLITICAL        NANC, GOP, MAGA, DEMZ -- publicly-disclosed political/
                    congressional-trade-replica ETFs (STOCK Act Periodic
                    Transaction Report replicas). Source: bit.com knowledge
                    hub (congressional-trade-tracking) and 24/7 Wall St
                    (2026-04-20, since-launch NANC/GOP performance). NANC and
                    GOP launched 2023-02-07 and have zero coverage of the
                    2016-2023 stress window used elsewhere in this repo -- see
                    data-feasibility.json; this batch judges POLITICAL/
                    PLACEBO_BIGTECH on the select+anchor windows only.
  PLACEBO_BIGTECH   QQQ, XLK, SPY, DIA -- non-political large-cap/tech ETFs,
                    preregistered specifically because 24/7 Wall St's own
                    skeptical claim is that NANC's outperformance is "a
                    byproduct of tech concentration... rather than any
                    genuine informational edge from tracking lawmakers." This
                    menu is a placebo-dominance disqualifier, not a
                    direction to keep on its own: see
                    candidate-manifest.json's keep_rule.placebo_dominance_disqualifier.

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

POLITICAL_MENU: tuple[str, ...] = ("NANC", "GOP", "MAGA", "DEMZ")
PLACEBO_BIGTECH_MENU: tuple[str, ...] = ("QQQ", "XLK", "SPY", "DIA")

LOOKBACKS: tuple[int, ...] = (63, 126, 252)
TOP_NS: tuple[int, ...] = (1, 2)
REBAL_FREQ: dict[str, str] = {"MO": "M", "WK": "W"}

_MENUS: dict[str, tuple[str, ...]] = {
    "POLITICAL": POLITICAL_MENU,
    "PLACEBO_BIGTECH": PLACEBO_BIGTECH_MENU,
}
_SOURCE_CARDS: dict[str, str] = {
    "POLITICAL": "bit_com_congressional_trade_tracking_2026",
    "PLACEBO_BIGTECH": "247wallst_nanc_gop_since_launch_2026",
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
