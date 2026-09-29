"""H-20260928-44 batch screening: ETF pair relative-strength switch (long-only
binary rotation between two highly correlated ETFs) versus a static 50/50
blend placebo, for `scripts/screen_batch.py --batch h20260928_44_etf_pair_switch
--iteration h20260928_44_etf_pair_switch`.

Reuses, unedited: `run_h20260918_05_recent_menu.momentum_score` -- the exact
lookback-return definition S1-S3's `rotation_cell` uses for ranking. No new
momentum formula or weighting scheme is introduced; every PAIR candidate is
`rotation_cell`'s own mechanism at the degenerate menu size of 2, top_n=1.

18 candidates: 12 `PAIR_{pair}_L{63,126}_MO` candidates for six highly
correlated ETF pairs (QQQ/SPY, SMH/QQQ, XLE/XOP, KRE/XLF, IWM/SPY, ARKK/QQQ),
each swept over lookback in {63, 126} trading days, monthly rebalance --
rank the pair by lookback momentum, hold the stronger leg only if it beats
SHY's own score over the same lookback (absolute-momentum filter, identical
to `rotation_cell`), else hold 100% SHY. Plus 6 `STATIC5050_{pair}_MO`
placebo candidates (one per pair): a fixed monthly-rebalanced 50/50 blend of
the same two legs, no ranking, no cash filter -- the control for whether
*switching* itself (not merely holding this pair) adds value.

Source: QuantConnect forum post "QQQ/SPY Momentum Rotation System" by Robert
Lemois (https://www.quantconnect.com/forum/discussion/19216/qqq-spy-momentum-
rotation-system/, opened in full via WebFetch): 20-day relative momentum,
+1.0% QQQ bias, 0.5% switch threshold, 5-day rebalance; reported 2010-2024
backtest CAGR 19.02%, Sharpe ~0.8 (author's own estimate), MDD ~30% (COVID).
Weak evidence: single author, unreplicated, platform staff flagged concrete
code bugs in the same thread, no post-fix numbers or OOS/live record --
used only for the mechanism (binary relative-strength switch between two
correlated ETFs), not for its own parameters or numbers, which this batch
does not reuse.
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

PAIRS: dict[str, tuple[str, str]] = {
    "QQQSPY": ("QQQ", "SPY"),
    "SMHQQQ": ("SMH", "QQQ"),
    "XLEXOP": ("XLE", "XOP"),
    "KREXLF": ("KRE", "XLF"),
    "IWMSPY": ("IWM", "SPY"),
    "ARKKQQQ": ("ARKK", "QQQ"),
}
LOOKBACKS: tuple[int, ...] = (63, 126)

SOURCE_CARD_PAIR = "quantconnect_qqq_spy_momentum_rotation_2026"
SOURCE_CARD_STATIC = "robotwealth_dual_momentum_review_whipsaw_2026"


def make_pair_switch_fn(
    leg_a: str, leg_b: str, lookback: int
) -> Callable[[pd.DataFrame, pd.Timestamp], dict[str, float]]:
    """Binary relative-strength switch, identical mechanism to
    `rotation_cell`'s per-date pick loop at menu size 2, top_n=1: rank
    `{leg_a, leg_b}` by `base.momentum_score(hist, str(lookback))` (imported
    unedited), pick the higher-scoring leg, keep it only if its score beats
    SHY's own score over the same lookback (absolute-momentum filter); if
    both legs are weaker than SHY, return `{}` (the lane's own remainder
    convention puts the unallocated weight into SHY). Reads only
    `close.loc[:asof]` -- never a later row."""

    def fn(close: pd.DataFrame, asof: pd.Timestamp) -> dict[str, float]:
        hist = close.loc[:asof]
        cols = [s for s in (leg_a, leg_b) if s in hist.columns]
        if len(cols) < 2 or CASH not in hist.columns:
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
        best = row.sort_values(ascending=False).index[0]
        if row[best] <= cash_score:
            return {}
        return {best: 1.0}

    return fn


def make_static5050_fn(
    leg_a: str, leg_b: str
) -> Callable[[pd.DataFrame, pd.Timestamp], dict[str, float]]:
    """Fixed 50/50 monthly-rebalanced blend of `leg_a`/`leg_b` -- no momentum
    ranking, no absolute-momentum-vs-cash filter. This is the switching
    placebo: it holds the same pair every candidate holds, so any Sharpe gap
    between a `PAIR_*` candidate and this control isolates the value of the
    *switching* decision itself. Reads only `close.loc[:asof]`."""

    def fn(close: pd.DataFrame, asof: pd.Timestamp) -> dict[str, float]:
        hist = close.loc[:asof]
        if leg_a not in hist.columns or leg_b not in hist.columns:
            return {}
        if asof not in hist.index:
            return {}
        if pd.isna(hist.loc[asof, leg_a]) or pd.isna(hist.loc[asof, leg_b]):
            return {}
        return {leg_a: 0.5, leg_b: 0.5}

    return fn


SPECS: list[dict] = []
for _pair_name, (_a, _b) in PAIRS.items():
    for _lb in LOOKBACKS:
        _cand_id = f"PAIR_{_pair_name}_L{_lb}_MO"
        SPECS.append(
            {
                "id": _cand_id,
                "name": f"{_pair_name} relative-strength switch, lookback={_lb}d, rebal=MO",
                "source_card": SOURCE_CARD_PAIR,
                "universe": (_a, _b),
                "freq": "M",
                "fn": make_pair_switch_fn(_a, _b, _lb),
            }
        )
    _static_id = f"STATIC5050_{_pair_name}_MO"
    SPECS.append(
        {
            "id": _static_id,
            "name": f"{_pair_name} static 50/50 blend (switching placebo), rebal=MO",
            "source_card": SOURCE_CARD_STATIC,
            "universe": (_a, _b),
            "freq": "M",
            "fn": make_static5050_fn(_a, _b),
        }
    )

assert len(SPECS) == 18
assert len({spec["id"] for spec in SPECS}) == 18
