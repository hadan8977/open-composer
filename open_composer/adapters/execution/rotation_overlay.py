"""Volatility-target overlay and sleeve-equity helpers for ``etf_rotation_portfolio``.

The overlay is a port of the research engine that froze the 2026-09-23
renewal rules (``scripts/run_h20260922_05_salvage.py``: ``wilder_rsi``,
``dip_signal``, ``boost_window``, ``simulate`` and ``vol_scale``). The paper
sleeve and the backtest therefore compute the multiplier the same way from
the same book:

- the book's *unscaled*, cost-free daily return uses two legs per session,
  previous-close -> open on the weights held overnight and open -> close on
  the weights live from that open;
- realized volatility is the sample standard deviation of those returns
  over ``realized_vol_sessions``, annualized by sqrt(252);
- the multiplier is ``min(1, target / realized)``, recomputed only at the
  open after a rebalance close and, with a dip boost, at the open after the
  boost turns on or off; it reads realized volatility through the previous
  close and stays constant between updates.

``tests/test_rotation_overlay.py`` checks these functions against the
research ones. The sleeve-equity helpers mark a paper sleeve's own fills
ledger at daily closes; the adapter uses them for ``sizing_basis=
sleeve_equity`` and ``drawdown_exit_pct``.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd

ANNUALIZATION = 252.0


def wilder_rsi(series: pd.Series, window: int) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)
    avg_gain = gain.ewm(alpha=1.0 / window, adjust=False, min_periods=window).mean()
    avg_loss = loss.ewm(alpha=1.0 / window, adjust=False, min_periods=window).mean()
    rs = avg_gain / avg_loss.replace(0.0, np.nan)
    out = 100.0 - 100.0 / (1.0 + rs)
    return out.where(avg_loss > 0, 100.0)


def dip_signal(
    close: pd.Series, *, sma_sessions: int, rsi_sessions: int, rsi_below: float
) -> pd.Series:
    """True on a close above its ``sma_sessions`` average with Wilder
    RSI(``rsi_sessions``) below ``rsi_below``. Computed on the symbol's own
    bars so one missing bar cannot blank the moving average."""
    px = close.dropna()
    above = px > px.rolling(sma_sessions).mean()
    oversold = wilder_rsi(px, rsi_sessions) < rsi_below
    return (above & oversold).fillna(False).astype(bool)


def boost_window(sig: np.ndarray, hold: int) -> np.ndarray:
    """The boost is live from the session after a firing close, for ``hold`` sessions."""
    n = len(sig)
    on = np.zeros(n, dtype=bool)
    for i in np.flatnonzero(sig):
        on[i + 1 : min(n, i + 1 + hold)] = True
    return on


def leg_returns(close: pd.DataFrame, open_: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    prev_close = close.shift(1)
    return (open_ / prev_close - 1.0).fillna(0.0), (close / open_ - 1.0).fillna(0.0)


def book_gross_returns(
    weights: pd.DataFrame, leg_open: pd.DataFrame, leg_close: pd.DataFrame
) -> pd.Series:
    """Unscaled, cost-free daily return of a book whose row ``i`` is live
    from the open of session ``i`` (row ``i - 1`` is held overnight into it)."""
    cols = list(weights.columns)
    live = weights.to_numpy(dtype=float)
    held = np.vstack([np.zeros((1, live.shape[1])), live[:-1]])
    lo = leg_open[cols].to_numpy(dtype=float)
    lc = leg_close[cols].to_numpy(dtype=float)
    return pd.Series((held * lo).sum(axis=1) + (live * lc).sum(axis=1), index=weights.index)


def realized_annual_vol(returns: pd.Series, window: int) -> np.ndarray:
    return (returns.rolling(window).std(ddof=1) * np.sqrt(ANNUALIZATION)).to_numpy()


def vol_scale_schedule(
    n: int,
    signal_positions: Sequence[int],
    realized: np.ndarray,
    base_target: float | None,
    boost: np.ndarray | None = None,
    boost_target: float | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """``(multiplier, update_position)`` per session. ``update_position[i]``
    is the session whose open last recomputed the multiplier in force at
    ``i`` (-1 before the first update). ``realized[i]`` must use returns
    through the close of session ``i``; the update at ``i`` reads
    ``realized[i - 1]``."""
    sched = np.ones(n)
    last_update = np.full(n, -1, dtype=int)
    if base_target is None and boost is None:
        return sched, last_update
    target = np.full(n, np.nan if base_target is None else base_target)
    if boost is not None and boost_target is not None:
        target = np.where(boost, boost_target, target)
    updates = {int(p) + 1 for p in signal_positions if int(p) + 1 < n}
    if boost is not None:
        changed = np.flatnonzero(np.diff(boost.astype(int)) != 0) + 1
        updates.update(int(i) for i in changed if i < n)
    current = 1.0
    current_update = -1
    for i in range(n):
        if i in updates:
            t = target[i]
            v = realized[i - 1] if i > 0 else np.nan
            if np.isnan(t) or not np.isfinite(v) or v <= 0:
                current = 1.0
            else:
                current = min(1.0, float(t) / float(v))
            current_update = i
        sched[i] = current
        last_update[i] = current_update
    return sched, last_update


def apply_multiplier(
    weights: Mapping[str, float], multiplier: float, cash_symbol: str
) -> dict[str, float]:
    """Scale every non-cash weight by ``multiplier``; the removed weight goes to cash."""
    risk_total = sum(float(w) for s, w in weights.items() if s != cash_symbol)
    scaled = {s: float(w) * multiplier for s, w in weights.items() if s != cash_symbol}
    scaled[cash_symbol] = float(weights.get(cash_symbol, 0.0)) + (1.0 - multiplier) * risk_total
    return scaled


@dataclass(frozen=True)
class OverlayDecision:
    """The multiplier for the next session and where it came from."""

    multiplier: float
    target_annual_vol: float
    realized_annual_vol: float | None
    boost_active: bool
    #: Close whose data set the multiplier in force (the decision close of
    #: the latest update); ``None`` when no update has happened yet.
    decision_session: date | None
    #: True when the next session's open is itself an update.
    updates_next_session: bool
    boost_fired_sessions: tuple[date, ...]


def decide_overlay(
    sessions: Sequence[date],
    book_weights: pd.DataFrame,
    close: pd.DataFrame,
    open_: pd.DataFrame,
    signal_sessions: Sequence[date],
    *,
    base_target: float,
    realized_vol_sessions: int,
    dip_close: pd.Series | None = None,
    sma_sessions: int = 200,
    rsi_sessions: int = 10,
    rsi_below: float = 30.0,
    boost_target: float | None = None,
    hold_sessions: int | None = None,
) -> OverlayDecision:
    """Multiplier for the session after ``sessions[-1]``.

    ``book_weights`` (rows = ``sessions``) is the unscaled book live from each
    session's open; ``close``/``open_`` are aligned on the same rows. The
    schedule is evaluated on ``sessions`` plus one slot for the next session,
    which is exactly the research engine's schedule one step ahead."""
    n_hist = len(sessions)
    leg_open, leg_close = leg_returns(close, open_)
    gross = book_gross_returns(book_weights, leg_open, leg_close)
    realized = np.append(realized_annual_vol(gross, realized_vol_sessions), np.nan)
    pos = {day: i for i, day in enumerate(sessions)}
    signal_positions = [pos[d] for d in signal_sessions if d in pos]
    boost = None
    fired: tuple[date, ...] = ()
    if dip_close is not None and boost_target is not None and hold_sessions is not None:
        sig_series = dip_signal(
            dip_close, sma_sessions=sma_sessions, rsi_sessions=rsi_sessions, rsi_below=rsi_below
        )
        sig = np.append(
            sig_series.reindex(list(sessions), fill_value=False).to_numpy(dtype=bool), False
        )
        boost = boost_window(sig, hold_sessions)
        fired = tuple(sessions[i] for i in np.flatnonzero(sig[:n_hist]))
    sched, last_update = vol_scale_schedule(
        n_hist + 1, signal_positions, realized, base_target, boost, boost_target
    )
    nxt = n_hist
    update = int(last_update[nxt])
    boost_on = bool(boost[nxt]) if boost is not None else False
    target = boost_target if boost_on and boost_target is not None else base_target
    realized_used = float(realized[update - 1]) if update > 0 else None
    return OverlayDecision(
        multiplier=float(sched[nxt]),
        target_annual_vol=float(target),
        realized_annual_vol=realized_used
        if realized_used is not None and np.isfinite(realized_used)
        else None,
        boost_active=boost_on,
        decision_session=sessions[update - 1] if update > 0 else None,
        updates_next_session=update == nxt,
        boost_fired_sessions=fired[-5:],
    )


# ---------------------------------------------------------------------------
# sleeve equity from a paper sleeve's own fills ledger


def sleeve_equity_curve(
    fills: Sequence[Mapping[str, object]], closes: pd.DataFrame, starting_equity: float
) -> pd.Series:
    """Close-marked equity of a paper sleeve, one value per ``closes`` row
    from the first filled session on: ``starting_equity`` plus the cash flows
    of every filled order plus the net position at that close. A fill counts
    from the close of the session it was ordered for (it filled at that
    session's open). Returns an empty series when nothing has filled.
    Raises ``ValueError`` when a held symbol has no close to mark it with."""
    flows: dict[date, float] = {}
    deltas: dict[date, dict[str, float]] = {}
    for row in fills:
        qty = float(row.get("filled_qty") or 0.0)  # type: ignore[arg-type]
        price = row.get("filled_avg_price")
        if qty <= 0 or price in (None, ""):
            continue
        session = date.fromisoformat(str(row.get("session")))
        symbol = str(row.get("symbol") or "").upper()
        signed = qty if str(row.get("side") or "").lower() == "buy" else -qty
        flows[session] = flows.get(session, 0.0) - signed * float(price)  # type: ignore[arg-type]
        book = deltas.setdefault(session, {})
        book[symbol] = book.get(symbol, 0.0) + signed
    if not flows:
        return pd.Series(dtype=float)
    first = min(flows)
    marks = closes.sort_index().ffill()
    cash = float(starting_equity)
    position: dict[str, float] = {}
    applied: set[date] = set()
    values: dict[date, float] = {}
    for day in marks.index:
        if day < first:
            continue
        for session in sorted(s for s in flows if s <= day and s not in applied):
            cash += flows[session]
            for symbol, change in deltas[session].items():
                position[symbol] = position.get(symbol, 0.0) + change
            applied.add(session)
        value = cash
        for symbol, qty in position.items():
            if abs(qty) < 1e-9:
                continue
            mark = marks.at[day, symbol] if symbol in marks.columns else np.nan
            if not np.isfinite(mark):
                raise ValueError(f"no close to mark sleeve position {symbol} on {day}")
            value += qty * float(mark)
        values[day] = value
    return pd.Series(values, dtype=float)


def held_symbols(fills: Sequence[Mapping[str, object]]) -> set[str]:
    """Every symbol that ever filled in the ledger (a superset of what is held now)."""
    return {
        str(row.get("symbol") or "").upper()
        for row in fills
        if float(row.get("filled_qty") or 0.0) > 0  # type: ignore[arg-type]
    } - {""}
