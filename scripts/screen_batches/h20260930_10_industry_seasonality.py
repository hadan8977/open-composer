"""Plan A1 (2026-09-30): front-running seasonality on 23 industry ETFs, for
`scripts/screen_batch.py --batch h20260930_10_industry_seasonality
--iteration h20260930_10_industry_seasonality`.

The rule is `make_sector_seasonality_fn` from
`scripts/screen_batches/h20260928_20_recent_opt.py`, unchanged (shift=1); only
the universe (23 industry ETFs, frozen in hypotheses.md) and the grid
(top_n in {2, 3, 5} x avg_years in {1, 5}) differ. Month-end signal, next-open
fill, freq 'D' with `month_end_signal_dates`, same as S0.

`make_shift_placebo_fn` is the preregistered control (not a candidate): the same
top_n/avg_years, but the score window shift is drawn per holding month from
PLACEBO_SHIFTS = {2..9} with an RNG seeded by (seed, holding_year,
holding_month), so a seed is reproducible whatever the call order. Shift 1 is the
real rule, 0 is true seasonality, 10-11 are the latest 1-2 months (momentum) and
12 is the holding month itself (look-ahead), hence the exclusions.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "screen_batches"))

import h20260928_05_batch2 as b2  # noqa: E402
import h20260928_20_recent_opt as opt  # noqa: E402

INDUSTRY_ETFS: tuple[str, ...] = (
    "XBI",
    "IBB",
    "XPH",
    "IHI",
    "IHF",
    "SMH",
    "IGV",
    "FDN",
    "SKYY",
    "XTL",
    "KRE",
    "KIE",
    "IAI",
    "XOP",
    "OIH",
    "XME",
    "ITA",
    "IYT",
    "ITB",
    "XRT",
    "PBJ",
    "PEJ",
    "PBW",
)
GRID: tuple[tuple[str, int, int], ...] = (
    ("I_K2_Y1", 2, 1),
    ("I_K3_Y1", 3, 1),
    ("I_K5_Y1", 5, 1),
    ("I_K2_Y5", 2, 5),
    ("I_K3_Y5", 3, 5),
    ("I_K5_Y5", 5, 5),
)
PLACEBO_SHIFTS: tuple[int, ...] = tuple(range(2, 10))
SOURCE_CARD = "quantpedia_front_running_sector_seasonality_industry_extension"


def make_shift_placebo_fn(
    *,
    universe: tuple[str, ...] = INDUSTRY_ETFS,
    top_n: int,
    avg_years: int,
    seed: int,
):
    """Random-shift placebo: same selection rule as `make_sector_seasonality_fn`
    but the score-window shift is drawn per holding month from PLACEBO_SHIFTS."""

    def fn(close: pd.DataFrame, asof: pd.Timestamp) -> dict[str, float]:
        if not b2._is_month_end(close.index, asof):
            return {}
        hist = close.loc[:asof]
        holding_month, holding_year = b2._holding_month_and_year(asof)
        rng = np.random.default_rng([seed, holding_year, holding_month])
        shift = int(rng.choice(PLACEBO_SHIFTS))
        scores = opt._compute_scores(
            hist, universe, holding_month, holding_year, shift=shift, avg_years=avg_years
        )
        if len(scores) < top_n:
            return {}
        picks = sorted(scores, key=lambda sym: scores[sym], reverse=True)[:top_n]
        w = 1.0 / len(picks)
        return {sym: w for sym in picks}

    return fn


SPECS: list[dict[str, object]] = [
    {
        "id": cid,
        "name": f"Front-run seasonality, 23 industry ETFs, top-{k}, {y}-year average",
        "source_card": SOURCE_CARD,
        "universe": INDUSTRY_ETFS,
        "freq": "D",
        "signal_dates_fn": b2.month_end_signal_dates,
        "fn": opt.make_sector_seasonality_fn(universe=INDUSTRY_ETFS, top_n=k, avg_years=y),
    }
    for cid, k, y in GRID
]
