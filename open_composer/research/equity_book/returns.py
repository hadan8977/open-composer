"""The single implementation of the return convention (design section 3).

Rules, shared by the backtest engine, research labels and every test:

* **Decide at the close of session t, trade at the open of t+1** (``exec_price="open"``; the
  sensitivity is ``"close"``: trade at the close of t+1).
* **Daily dollar accounting.**  A position moves close -> close on a non-trade day.  On a trade
  day (t+1) the old holdings first earn ``close_t -> open_{t+1}`` (the *overnight leg*), the book is
  traded at ``open_{t+1}``, and the new holdings earn ``open_{t+1} -> close_{t+1}`` (the
  *intraday leg*).  Costs are taken at the trade.  This is the same session convention as the S3
  engine (``scripts/run_h20260922_05_salvage.py::simulate``), so a daily series can go straight into
  ``screen_lane.diversifier_edge_for_offset``.
* **Missing prices.**  A day on which a name has no valid close is a *hole*: its legs are 0 (the
  position keeps its last mark) and the first valid session afterwards books the whole move from the
  last valid close.  A missing open on a day with a valid close is replaced by the last valid close
  (stale open: overnight leg 0, intraday leg = the whole close-to-close move).
* **Delisting.**  A name whose last valid close is before the end of the calendar leaves the book at
  that last valid close, on the first session without a price (:attr:`Legs.delist_pos`).  The
  optional sensitivity ``delist_long_haircut`` (e.g. ``-0.30``, Shumway 1997) charges longs that
  fraction of their mark; shorts get 0.
* **Forward research label.**  :func:`forward_open_to_open` is ``open_{t+1+h} / open_{t+1} - 1``
  with the last valid close in ``[t+1, t+1+h)`` as the exit price when the exit open is missing.
  :func:`compound_legs` compounds the daily legs over the same span; the two agree exactly
  (tested), which is the point: a label and a held position must give one number for one trade.

All functions are pure numpy on ``(T, N)`` price matrices (``T`` sessions, ``N`` symbols).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np

ExecPrice = Literal["open", "close"]


@dataclass(frozen=True)
class Legs:
    """Per-day, per-symbol return legs and the prices a trade would execute at.

    ``ov[i, n]``      close_{i-1} -> open_i (0 when not priced)
    ``intra[i, n]``   open_i -> close_i     (0 when not priced)
    ``exec_open``     open_i, or the last valid close when the open is missing (NaN: no price)
    ``priced``        the symbol has a valid close on session i
    ``delist_pos``    first session without a price after the last valid close, ``-1`` if the name
                      is still priced on the last session (or never priced)
    """

    ov: np.ndarray
    intra: np.ndarray
    exec_open: np.ndarray
    priced: np.ndarray
    delist_pos: np.ndarray
    close: np.ndarray


def day_legs(
    open_row: np.ndarray, close_row: np.ndarray, last_close: np.ndarray
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """One session of the return legs: ``(ov, intra, exec_open, priced)`` from the open/close rows
    and the last valid close of every symbol before this session (NaN if none).  The only place
    where the leg formulas live; :func:`build_legs` and the backtest engine both call it."""
    c = close_row
    priced = np.isfinite(c) & (c > 0)
    has_open = np.isfinite(open_row) & (open_row > 0)
    with np.errstate(invalid="ignore", divide="ignore"):
        eo = np.where(has_open, open_row, last_close)
        eo = np.where(priced, eo, np.nan)
        ok_ov = priced & np.isfinite(last_close) & np.isfinite(eo)
        ov = np.where(ok_ov, eo / last_close - 1.0, 0.0)
        ok_in = priced & np.isfinite(eo)
        intra = np.where(ok_in, c / eo - 1.0, 0.0)
    return ov, intra, eo, priced


def delist_positions(priced: np.ndarray) -> np.ndarray:
    """First session without a price after a symbol's last valid close; ``-1`` for a symbol that is
    priced on the last session (or never priced)."""
    t_n = priced.shape[0]
    any_p = priced.any(axis=0)
    last_pos = np.where(any_p, t_n - 1 - np.argmax(priced[::-1], axis=0), -1)
    return np.where((last_pos >= 0) & (last_pos < t_n - 1), last_pos + 1, -1)


def build_legs(open_: np.ndarray, close: np.ndarray) -> Legs:
    """Return legs and delisting positions from open/close matrices (see module docstring).
    Materialises ``(T, N)`` arrays; the engine streams :func:`day_legs` instead."""
    o = np.asarray(open_, dtype="float64")
    c = np.asarray(close, dtype="float64")
    if o.shape != c.shape:
        raise ValueError("open and close must have the same shape")
    t_n, n = c.shape
    ov = np.zeros((t_n, n))
    intra = np.zeros((t_n, n))
    exec_open = np.full((t_n, n), np.nan)
    priced = np.zeros((t_n, n), dtype=bool)
    last = np.full(n, np.nan)
    for i in range(t_n):
        ov[i], intra[i], exec_open[i], priced[i] = day_legs(o[i], c[i], last)
        last = np.where(priced[i], c[i], last)
    return Legs(
        ov=ov,
        intra=intra,
        exec_open=exec_open,
        priced=priced,
        delist_pos=delist_positions(priced),
        close=c,
    )


def forward_open_to_open(
    open_: np.ndarray, close: np.ndarray, entry_pos: int, exit_pos: int
) -> np.ndarray:
    """Forward open-to-open return per column: ``open[exit_pos] / open[entry_pos] - 1``.

    The research label (``entry_pos = t + 1``, ``exit_pos = t + 1 + h``).  When the exit open is
    missing the last valid close in ``[entry_pos, exit_pos)`` is the exit price.  A missing or
    non-positive entry open gives NaN.
    """
    o = np.asarray(open_, dtype="float64")
    c = np.asarray(close, dtype="float64")
    entry = o[entry_pos]
    exit_open = o[exit_pos]
    fallback = ~np.isfinite(exit_open)
    exit_px = exit_open
    if fallback.any() and exit_pos > entry_pos:
        blk = c[entry_pos:exit_pos]
        ok = np.isfinite(blk)
        last_idx = np.where(ok, np.arange(blk.shape[0])[:, None], -1).max(axis=0)
        last_close = np.where(
            last_idx >= 0, blk[np.maximum(last_idx, 0), np.arange(blk.shape[1])], np.nan
        )
        exit_px = np.where(fallback, last_close, exit_open)
    ok_entry = np.isfinite(entry) & (entry > 0)
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(
            ok_entry & np.isfinite(exit_px), exit_px / np.where(ok_entry, entry, 1.0) - 1.0, np.nan
        )


def compound_legs(legs: Legs, entry_pos: int, exit_pos: int) -> np.ndarray:
    """Compounded return of a buy-and-hold entered at ``open[entry_pos]`` and valued at
    ``open[exit_pos]`` from the daily legs: ``(1 + intra_e) * prod_{d=e+1}^{x-1}(1 + ov_d)(1 +
    intra_d) * (1 + ov_x) - 1``.  A name that delists inside the span is held flat from its last
    valid close (the engine's exit price).  Equals :func:`forward_open_to_open` where the entry
    open exists."""
    growth = 1.0 + legs.intra[entry_pos]
    for d in range(entry_pos + 1, exit_pos):
        growth = growth * (1.0 + legs.ov[d]) * (1.0 + legs.intra[d])
    if exit_pos > entry_pos:
        growth = growth * (1.0 + legs.ov[exit_pos])
    entry_ok = legs.priced[entry_pos] & np.isfinite(legs.exec_open[entry_pos])
    return np.where(entry_ok, growth - 1.0, np.nan)


def holding_period_return(daily_returns: np.ndarray) -> float:
    """Compounded return of a daily return vector."""
    r = np.asarray(daily_returns, dtype="float64")
    return float(np.prod(1.0 + r) - 1.0)
