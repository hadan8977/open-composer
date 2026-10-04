"""Strict bench runner: IC + random control + train/test OOS split.

Companion to ``bench_runner.py``. The math in ``run_bench()`` is unchanged
— this module adds a stricter category gate that requires a same-universe
random-control comparison and (optionally) an out-of-sample split before
an alpha is allowed to graduate to ``confirmed_alive``.

Why this exists
---------------

``bench_runner.categorise()`` currently labels an alpha ``alive`` whenever
its raw IC mean exceeds 0.02, the IC-positive ratio exceeds 0.55, and the
single-sample t-stat exceeds 2. That gate accepts factors whose IC is
driven by a shared cross-sectional beta (e.g. market or size) rather than
genuine alpha — the IC and t-stat will both pass even when a random shuffle
of the same factor produces a comparable IC, because the test is
benchmarked against zero, not against a same-universe random control.

The bili_stock A-share study (Soli22de/Bili_Stock, 9-month audit of 12
single factors and 191 GTJA variants) found this gate is the dominant
source of false-positive alphas in A-share research: every factor passed
the raw IC test at some parameter setting, but only 1 of 12 survived a
parallel random-control comparison.

This module makes the random control an explicit, mandatory step. The
heuristic follows Harvey-Liu-Zhu (2016) "...and the Cross-Section of
Expected Returns": once you correct for multiple testing across the
factor zoo, the median |t| threshold for a published factor needs to be
~3.5, not 2.0. We achieve the same effect with a same-universe random
shuffle rather than a multiple-testing correction.

API contract
------------

``run_bench_strict()`` returns the same top-level keys as ``run_bench()``
plus:

- ``train_rows`` / ``test_rows`` (when ``oos_split`` is provided)
- ``random_ic_mean`` / ``alpha_t`` per alpha row
- ``confirmed_alive`` / ``train_only`` / ``reversed_strict`` / ``noise``
  category counts

Existing ``run_bench()`` is untouched. The strict path is opt-in via the
dedicated function; the original behaviour is preserved for any caller
that still wants the cheaper gate.
"""

from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass
from typing import Any, Callable, Literal

import numpy as np
import pandas as pd

from src.factors.factor_analysis_core import compute_ic_series
from src.factors.registry import (
    Registry,
    RegistryError,
    SkipAlpha,
    get_default_registry,
)
from src.tools.alpha_bench_tool import _compute_forward_returns, _load_universe_panel

logger = logging.getLogger(__name__)


ProgressCb = Callable[[int, int, str], None]
"""Signature: ``on_progress(n_done, n_total, current_alpha_id)``."""

StrictCategory = Literal[
    "confirmed_alive",  # signal beats random in full sample AND in OOS (when provided)
    "train_only",        # signal beats random in train, fails in test
    "reversed_strict",   # signal IC < random IC with negative alpha_t < -2
    "noise",             # alpha_t in [-2, 2]; indistinguishable from random
]


@dataclass(frozen=True, slots=True)
class StrictThresholds:
    """Tunable gate parameters for ``categorise_strict()``.

    ``alpha_t_threshold`` defaults to 2.0 to stay backward-comparable with the
    existing ``categorise()`` gate; raising it to 3.5 implements the
    Harvey-Liu-Zhu (2016) multiple-testing recommendation when running the
    full 455-alpha zoo.
    """

    alpha_t_threshold: float = 2.0
    min_ic_count: int = 30  # need enough periods for a meaningful t-stat


# ── Random control helpers ─────────────────────────────────────────────────


def _shuffle_within_rows(
    df: pd.DataFrame, *, seed: int
) -> pd.DataFrame:
    """Cross-sectionally permute finite values within each row.

    This preserves the per-date cross-sectional distribution of the factor
    while destroying the actual signal→instrument mapping. The result is a
    "factor with no information" that has the same statistical envelope as
    the original — which is what makes it a fair null hypothesis baseline
    for IC computation.

    Non-finite cells (``NaN``, ``+inf``, ``-inf``) are pinned in place. We
    treat infinities the same as NaN here even though
    ``Registry._validate_output`` rejects infinities upstream — this keeps
    the shuffle robust against third-party zoo plugins that bypass the
    standard registry path and keeps the IC of the shuffled factor
    insensitive to whether the cell happened to land on the inf or just
    next to it.

    Args:
        df: Factor frame, index=date, columns=instrument codes.
        seed: RNG seed for reproducibility.

    Returns:
        A new DataFrame with the same index/columns but with each row's
        finite values randomly reassigned to other finite positions in
        the same row. Non-finite positions stay non-finite.
    """
    rng = np.random.default_rng(seed)
    values = df.to_numpy(copy=True)
    n_rows, _ = values.shape
    for i in range(n_rows):
        row = values[i]
        mask = np.isfinite(row)
        if mask.sum() < 2:
            continue
        permuted = rng.permutation(row[mask])
        row[mask] = permuted
        values[i] = row
    return pd.DataFrame(values, index=df.index, columns=df.columns)


def compute_random_ic_series(
    factor_df: pd.DataFrame,
    return_df: pd.DataFrame,
    *,
    n_seeds: int = 5,
    base_seed: int = 42,
) -> pd.Series:
    """Mean IC series across ``n_seeds`` row-shuffled random controls.

    Returns one IC value per date, averaged across **all** ``n_seeds``
    seeds on dates where every seed produced a valid IC. Dates where any
    seed dropped out (e.g. fewer than ``_MIN_VALID_PER_DATE=5`` paired
    non-NaN cells) are excluded from the output via an inner join — the
    random control is supposed to be a stable per-date baseline, so a
    "1-seed average on some dates, 5-seed on others" mix would silently
    inflate variance on the borderline dates.

    Empty input or zero common dates yields an empty Series.
    """
    if factor_df.empty or return_df.empty:
        return pd.Series(dtype=float)
    seeds = [base_seed + i for i in range(max(1, n_seeds))]
    ic_frames: list[pd.Series] = []
    for s in seeds:
        shuffled = _shuffle_within_rows(factor_df, seed=s)
        ic = compute_ic_series(shuffled, return_df)
        if not ic.empty:
            ic_frames.append(ic)
    if not ic_frames:
        return pd.Series(dtype=float)
    # Inner join so every retained date is the mean of all available seeds
    # uniformly — see docstring rationale above.
    combined = pd.concat(ic_frames, axis=1, join="inner")
    return combined.mean(axis=1)


def alpha_series_paired(
    signal_ic: pd.Series, random_ic: pd.Series
) -> pd.Series:
    """Per-date paired alpha = signal_IC - random_IC, on the common index."""
    common = signal_ic.index.intersection(random_ic.index)
    if common.empty:
        return pd.Series(dtype=float)
    return (signal_ic.loc[common] - random_ic.loc[common]).dropna()


def t_stat(series: pd.Series) -> float:
    """One-sample t-stat against zero (returns 0.0 if undefined)."""
    n = len(series)
    if n < 2:
        return 0.0
    std = float(series.std(ddof=1))
    if not (std > 0 and math.isfinite(std)):
        return 0.0
    return float(series.mean() / (std / math.sqrt(n)))


# ── Theme breakdown (strict-aware version of bench_runner.theme_breakdown) ──


def _theme_breakdown_strict(rows: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    """Aggregate strict-category counts per theme tag.

    Mirrors ``bench_runner.theme_breakdown`` but with the strict
    ``confirmed_alive`` / ``train_only`` / ``reversed_strict`` / ``noise``
    buckets, plus legacy ``alive`` / ``reversed`` / ``dead`` aliases so
    existing dashboards keep working without code changes.
    """
    by_theme: dict[str, dict[str, int]] = {}
    for row in rows:
        cat = row.get("_category", "noise")
        themes = row.get("theme", []) or ["uncategorised"]
        for theme in themes:
            bucket = by_theme.setdefault(
                theme,
                {
                    "confirmed_alive": 0,
                    "train_only": 0,
                    "reversed_strict": 0,
                    "noise": 0,
                    "alive": 0,
                    "reversed": 0,
                    "dead": 0,
                    "count": 0,
                },
            )
            bucket[cat] = bucket.get(cat, 0) + 1
            bucket["count"] += 1
            # Legacy aliases mirror the bucket aliasing in the entry dict.
            if cat == "confirmed_alive":
                bucket["alive"] += 1
            elif cat == "reversed_strict":
                bucket["reversed"] += 1
            elif cat in ("noise", "train_only"):
                bucket["dead"] += 1
    return 