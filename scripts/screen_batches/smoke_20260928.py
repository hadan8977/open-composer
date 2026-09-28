"""Smoke batch for the screening lane (2026-09-28): three deliberately trivial
benchmark candidates, no strategy claims. Exercises the harness end to end
before any published-rule batch is preregistered.

Deliberately excludes TLT/GLD/DBC/UUP trend rules and Defense First -- those
are preregistered for a separate round and running them here would
contaminate that preregistration.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from screen_lane import ScreenCandidate  # noqa: E402


def _spy_bh(_close: pd.DataFrame, _asof: pd.Timestamp) -> dict[str, float]:
    return {"SPY": 1.0}


def _gld_bh(_close: pd.DataFrame, _asof: pd.Timestamp) -> dict[str, float]:
    return {"GLD": 1.0}


def _spy_tlt_6040(_close: pd.DataFrame, _asof: pd.Timestamp) -> dict[str, float]:
    return {"SPY": 0.6, "TLT": 0.4}


CANDIDATES: list[ScreenCandidate] = [
    ScreenCandidate(
        id="SPY_BH",
        name="100% SPY buy and hold",
        source_card="smoke/no_card_trivial_benchmark",
        universe=("SPY",),
        freq="M",
        weights_fn=_spy_bh,
    ),
    ScreenCandidate(
        id="SPY_TLT_6040",
        name="60/40 SPY/TLT, rebalanced monthly",
        source_card="smoke/no_card_trivial_benchmark",
        universe=("SPY", "TLT"),
        freq="M",
        weights_fn=_spy_tlt_6040,
    ),
    ScreenCandidate(
        id="GLD_BH",
        name="100% GLD buy and hold",
        source_card="smoke/no_card_trivial_benchmark",
        universe=("GLD",),
        freq="M",
        weights_fn=_gld_bh,
    ),
]
