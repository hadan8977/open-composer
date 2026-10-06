"""T-20260929-11 batch: `scripts/screen_batch.py --batch h20260929_11_multiq_sue
--iteration h20260929_11_multiq_sue`.

Multi-quarter SUE history elastic net (Kaczmarek & Zaremba 2025, Finance
Research Letters) on the point-in-time S&P 500 pool. Scores come from
`scripts/build_h20260929_11_multiq_sue_scores.py` (one ElasticNet per test year,
expanding window, hyperparameters by time-series CV, `scores.parquet`), stock
prices from `extend_panel` (listed + delisted SIP daily archives, then
`sanitize_price_matrices` defaults; columns are prefixed `Z_` so nothing clashes
with the S3 panel).

8 candidates (freq="M", 21 monthly offsets, positions only from 2019-01-02, the
first out-of-sample score date, so every candidate shares the same windows):

  ENET_TOP50       model score top 50, equal weight (keep-eligible)
  ENET_TOP20       model score top 20 (keep-eligible)
  ENET_MOM_TOP50   rank(score) + rank(12-1 momentum), top 50 (keep-eligible)
  SUE1_TOP50       latest-quarter sue_eps top 50 (baseline)
  MOM12_1_TOP50    12-1 momentum top 50 (baseline)
  EW_POOL          equal weight over all eligible pool members (benchmark)
  RAND_TOP50       50 random eligible names, default_rng([20260929, yyyymm])
  ENET_SHUF_TOP50  same pipeline trained on within-month shuffled labels (placebo)

Tie rule (implementation detail, fixed before the batch ran): when a year's
elastic net has all-zero coefficients its score is constant; ranking then breaks
ties with the same per-month random key RAND_TOP50 uses, i.e. an uninformative
model behaves like a random pick, not like an alphabetical one.

Every weights_fn reads only scores dated on or before `asof`, the close panel up
to `asof`, and nothing else -- no look-ahead.
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))

import build_h20260929_11_multiq_sue_scores as sc  # noqa: E402
import screen_lane as lane  # noqa: E402

SCORES_PATH = sc.OUT_DIR / "scores.parquet"
PREFIX = "Z_"
SEED = sc.SEED
START = pd.Timestamp("2019-01-02")

_SCORES = pd.read_parquet(SCORES_PATH)
_SCORES["date"] = pd.to_datetime(_SCORES["date"])
_SCORES = _SCORES.sort_values(["date", "symbol"])
POOL_SYMBOLS: tuple[str, ...] = tuple(sorted(_SCORES["symbol"].unique()))
UNIVERSE: tuple[str, ...] = tuple(f"{PREFIX}{s}" for s in POOL_SYMBOLS)
_BY_DATE: dict[pd.Timestamp, pd.DataFrame] = {d: g for d, g in _SCORES.groupby("date")}
_DATES = sorted(_BY_DATE)


def extend_panel(close: pd.DataFrame, open_: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Pool prices (sanitized with `sanitize_price_matrices` defaults, cached by the
    scores script) as `Z_<ticker>` columns."""
    pc, po, _report = sc.load_pool_prices()
    cols = [s for s in POOL_SYMBOLS if s in pc.columns]
    ec = pc[cols].reindex(close.index)
    eo = po[cols].reindex(open_.index)
    ec.columns = [f"{PREFIX}{c}" for c in cols]
    eo.columns = [f"{PREFIX}{c}" for c in cols]
    return ec, eo


_MOM_CACHE: dict[int, pd.DataFrame] = {}


def _mom12_1(close: pd.DataFrame) -> pd.DataFrame:
    key = lane.frame_key(close)
    if key not in _MOM_CACHE:
        pool_cols = [c for c in close.columns if c.startswith(PREFIX)]
        px = close[pool_cols]
        _MOM_CACHE[key] = px.shift(21) / px.shift(252) - 1.0
    return _MOM_CACHE[key]


def _snapshot(close: pd.DataFrame, asof: pd.Timestamp) -> pd.DataFrame | None:
    """Eligible names on `asof` (a row in scores.parquet with a live close)."""
    if asof < START or asof not in close.index:
        return None
    frame = _BY_DATE.get(asof)
    if frame is None:
        return None
    cols = PREFIX + frame["symbol"]
    live = cols.isin(close.columns).to_numpy()
    frame = frame.loc[live].copy()
    frame["col"] = PREFIX + frame["symbol"]
    px = close.loc[asof, frame["col"]].to_numpy()
    frame = frame.loc[np.isfinite(px)]
    return frame if len(frame) else None


def _tie_key(n: int, asof: pd.Timestamp) -> np.ndarray:
    return np.random.default_rng([SEED, asof.year * 100 + asof.month]).random(n)


def _rank_desc(values: np.ndarray, asof: pd.Timestamp) -> np.ndarray:
    """Rank 1 = highest value, ties broken by the per-month random key."""
    key = _tie_key(len(values), asof)
    order = np.lexsort((key, -np.nan_to_num(values, nan=-np.inf)))
    rank = np.empty(len(values))
    rank[order] = np.arange(1, len(values) + 1)
    return rank


def _equal(cols: list[str]) -> dict[str, float]:
    return {c: 1.0 / len(cols) for c in cols} if cols else {}


def _top_by(column: str, top_n: int) -> Callable[[pd.DataFrame, pd.Timestamp], dict[str, float]]:
    def fn(close: pd.DataFrame, asof: pd.Timestamp) -> dict[str, float]:
        snap = _snapshot(close, asof)
        if snap is None:
            return {}
        if column == "sue1":
            snap = snap[np.isfinite(snap["sue1"])]
            if snap.empty:
                return {}
        rank = _rank_desc(snap[column].to_numpy(), asof)
        chosen = snap["col"].to_numpy()[np.argsort(rank)[:top_n]]
        return _equal(list(chosen))

    return fn


def _mom_top(top_n: int) -> Callable[[pd.DataFrame, pd.Timestamp], dict[str, float]]:
    def fn(close: pd.DataFrame, asof: pd.Timestamp) -> dict[str, float]:
        snap = _snapshot(close, asof)
        if snap is None:
            return {}
        mom = _mom12_1(close).loc[asof, snap["col"]].to_numpy()
        ok = np.isfinite(mom)
        if not ok.any():
            return {}
        rank = _rank_desc(mom[ok], asof)
        chosen = snap["col"].to_numpy()[ok][np.argsort(rank)[:top_n]]
        return _equal(list(chosen))

    return fn


def _enet_mom_top(top_n: int) -> Callable[[pd.DataFrame, pd.Timestamp], dict[str, float]]:
    def fn(close: pd.DataFrame, asof: pd.Timestamp) -> dict[str, float]:
        snap = _snapshot(close, asof)
        if snap is None:
            return {}
        mom = _mom12_1(close).loc[asof, snap["col"]].to_numpy()
        ok = np.isfinite(mom)
        if not ok.any():
            return {}
        snap = snap.loc[ok]
        r_score = _rank_desc(snap["score"].to_numpy(), asof)
        r_mom = _rank_desc(mom[ok], asof)
        total = r_score + r_mom
        # tie-break the rank sum with the same per-month key
        key = _tie_key(len(total), asof)
        order = np.lexsort((key, total))
        chosen = snap["col"].to_numpy()[order[:top_n]]
        return _equal(list(chosen))

    return fn


def _ew_pool(close: pd.DataFrame, asof: pd.Timestamp) -> dict[str, float]:
    snap = _snapshot(close, asof)
    return {} if snap is None else _equal(list(snap["col"]))


def _rand_top(top_n: int) -> Callable[[pd.DataFrame, pd.Timestamp], dict[str, float]]:
    def fn(close: pd.DataFrame, asof: pd.Timestamp) -> dict[str, float]:
        snap = _snapshot(close, asof)
        if snap is None:
            return {}
        cols = sorted(snap["col"])
        rng = np.random.default_rng([SEED, asof.year * 100 + asof.month])
        n = min(top_n, len(cols))
        return _equal(sorted(rng.choice(cols, size=n, replace=False).tolist()))

    return fn


def _cand(cid: str, name: str, fn: Callable) -> lane.ScreenCandidate:
    return lane.ScreenCandidate(
        id=cid,
        name=name,
        source_card="reports/harness/source_cards/h20260929_11_multiq_sue.jsonl",
        universe=UNIVERSE,
        freq="M",
        weights_fn=fn,
    )


CANDIDATES: list[lane.ScreenCandidate] = [
    _cand("ENET_TOP50", "Elastic net multi-quarter SUE score, top 50", _top_by("score", 50)),
    _cand("ENET_TOP20", "Elastic net multi-quarter SUE score, top 20", _top_by("score", 20)),
    _cand(
        "ENET_MOM_TOP50",
        "Rank sum of elastic net score and 12-1 momentum, top 50",
        _enet_mom_top(50),
    ),
    _cand("SUE1_TOP50", "Latest-quarter sue_eps, top 50 (baseline)", _top_by("sue1", 50)),
    _cand("MOM12_1_TOP50", "12-1 momentum, top 50 (baseline)", _mom_top(50)),
    _cand("EW_POOL", "Equal weight all eligible S&P 500 members (benchmark)", _ew_pool),
    _cand("RAND_TOP50", "Random 50 eligible names, seed 20260929 (placebo)", _rand_top(50)),
    _cand(
        "ENET_SHUF_TOP50",
        "Elastic net trained on shuffled labels, top 50 (placebo)",
        _top_by("score_shuf", 50),
    ),
]
