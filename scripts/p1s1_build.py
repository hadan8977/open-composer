"""Build the point-in-time calendar and universe for T-20261008-31.

This stage deliberately does not calculate returns or publish performance.  It
freezes the date-indexed trading universe and rolling test blocks used by the
later PCA/IPCA residual builders.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_STORE = ROOT / "data/research/t22_streversal"
DEFAULT_OUT = ROOT / "data/research/p1s1_dlsa"


@dataclass(frozen=True)
class PanelStore:
    dates: pd.DatetimeIndex
    symbols: pd.Index
    close: np.ndarray
    adv_rank: np.ndarray
    is_tradeable: np.ndarray
    short_elig: np.ndarray


def daily_returns(close: np.ndarray) -> np.ndarray:
    prices = np.asarray(close, dtype="float64")
    if prices.ndim != 2:
        raise ValueError("close must be a 2-D time x symbol array")
    out = np.full_like(prices, np.nan)
    with np.errstate(divide="ignore", invalid="ignore"):
        out[1:] = prices[1:] / prices[:-1] - 1.0
    return out


def project_residuals(returns: np.ndarray, beta: np.ndarray, weights: np.ndarray) -> np.ndarray:
    """Apply ``Phi = I - beta @ weights`` row-wise without forming an N x N matrix."""
    r = np.asarray(returns, dtype="float64")
    b = np.asarray(beta, dtype="float64")
    w = np.asarray(weights, dtype="float64")
    if r.ndim != 1 or b.ndim != 2 or w.ndim != 2 or b.shape[1] != w.shape[0]:
        raise ValueError("expected r[N], beta[N,K], weights[K,N]")
    if b.shape[0] != r.size or w.shape[1] != r.size:
        raise ValueError("projection dimensions do not agree")
    return r - b @ (w @ r)


def composition_identity_error(
    returns: np.ndarray, residuals: np.ndarray, beta: np.ndarray, weights: np.ndarray
) -> float:
    """Return max absolute error in ``eps = Phi r`` and ``(Phi'w)'r = w'eps``."""
    r = np.asarray(returns, dtype="float64")
    eps = np.asarray(residuals, dtype="float64")
    expected = project_residuals(r, beta, weights)
    first = float(np.nanmax(np.abs(eps - expected)))
    rng = np.random.default_rng(20261008)
    trial = rng.normal(size=r.size)
    left = float((trial - weights.T @ (beta.T @ trial)).dot(r))
    right = float(trial.dot(eps))
    return max(first, abs(left - right))


def load_store(path: Path = DEFAULT_STORE) -> PanelStore:
    meta = json.loads((path / "meta.json").read_text(encoding="utf-8"))
    dates = pd.DatetimeIndex(meta["dates"])
    symbols = pd.Index(meta["symbols"])
    shape = tuple(meta["shape"])
    arrays = {
        name: np.load(path / f"{name}.npy", mmap_mode="r")
        for name in ("close", "adv_rank", "is_tradeable", "short_elig")
    }
    if any(tuple(value.shape) != shape for value in arrays.values()):
        raise ValueError(f"store shape mismatch: expected {shape}")
    return PanelStore(dates, symbols, **arrays)


def _last_index_by_month(dates: pd.DatetimeIndex) -> dict[tuple[int, int], int]:
    out: dict[tuple[int, int], int] = {}
    for i, date in enumerate(dates):
        out[(date.year, date.month)] = i
    return out


def monthly_universes(
    store: PanelStore,
    *,
    trade_rank: int = 500,
    residual_rank: int = 1000,
    lookback: int = 252,
) -> tuple[list[dict], np.ndarray, np.ndarray]:
    """Return the PIT universe effective on each session.

    Membership is selected from the previous month-end and requires complete
    prior returns.  The returned masks have shape ``(T, N)`` and remain false
    before the first eligible session.
    """
    close = np.asarray(store.close, dtype="float64")
    returns = daily_returns(close)
    complete = np.zeros_like(close, dtype=bool)
    if lookback < len(store.dates):
        finite = np.isfinite(returns)
        rolling = np.lib.stride_tricks.sliding_window_view(finite, lookback, axis=0)
        complete[lookback:] = rolling[1:].all(axis=-1)

    month_end = _last_index_by_month(store.dates)
    m_mask = np.zeros(close.shape, dtype=bool)
    e_mask = np.zeros(close.shape, dtype=bool)
    rows: list[dict] = []
    previous_end: int | None = None
    for i, date in enumerate(store.dates):
        key = (date.year, date.month)
        if i == 0 or (i and (store.dates[i - 1].year, store.dates[i - 1].month) == key):
            continue
        if previous_end is None:
            previous_end = month_end[(store.dates[i - 1].year, store.dates[i - 1].month)]
        if i == 0 or previous_end is None:
            continue
        eligible = (
            (store.adv_rank[previous_end] <= trade_rank)
            & (store.is_tradeable[previous_end] > 0)
            & (store.short_elig[previous_end] > 0)
            & complete[previous_end]
        )
        residual = (store.adv_rank[previous_end] <= residual_rank) & complete[previous_end]
        if not residual.any():
            previous_end = None
            continue
        m_mask[i:] = eligible
        e_mask[i:] = residual
        rows.append(
            {
                "effective_date": str(date.date()),
                "source_date": str(store.dates[previous_end].date()),
                "trade_count": int(eligible.sum()),
                "residual_count": int(residual.sum()),
                "trade_symbols": store.symbols[eligible].tolist(),
                "residual_symbols": store.symbols[residual].tolist(),
            }
        )
        previous_end = None
    return rows, m_mask, e_mask


def build_test_blocks(
    dates: pd.DatetimeIndex,
    *,
    first_test: str = "2020-02-13",
    block_size: int = 125,
    embargo: int = 2,
) -> list[dict]:
    """Create frozen 125-session test blocks with the contract's embargo."""
    start = int(dates.searchsorted(pd.Timestamp(first_test)))
    blocks: list[dict] = []
    block_id = 0
    for begin in range(start, len(dates), block_size):
        end = min(begin + block_size, len(dates))
        if end - begin < 2:
            break
        blocks.append(
            {
                "block": block_id,
                "start_index": begin,
                "end_index_exclusive": end,
                "start": str(dates[begin].date()),
                "end": str(dates[end - 1].date()),
                "train_end_index_exclusive": begin - embargo,
                "train_end": str(dates[max(begin - embargo - 1, 0)].date()),
                "sessions": end - begin,
            }
        )
        block_id += 1
    return blocks


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--store", type=Path, default=DEFAULT_STORE)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    store = load_store(args.store)
    universes, m_mask, e_mask = monthly_universes(store)
    blocks = build_test_blocks(store.dates)
    args.out.mkdir(parents=True, exist_ok=True)
    np.save(args.out / "trade_universe.npy", m_mask)
    np.save(args.out / "residual_universe.npy", e_mask)
    (args.out / "build.json").write_text(
        json.dumps(
            {
                "stage": "calendar_only",
                "source": str(args.store),
                "dates": [str(x.date()) for x in store.dates],
                "symbols": store.symbols.tolist(),
                "trade_rank": 500,
                "residual_rank": 1000,
                "lookback": 252,
                "monthly_universes": universes,
                "tests": {"future_membership_used": False},
            },
            indent=2,
        )
    )
    (args.out / "blocks.json").write_text(json.dumps(blocks, indent=2))
    print(json.dumps({"months": len(universes), "blocks": len(blocks), "out": str(args.out)}))


if __name__ == "__main__":
    main()
