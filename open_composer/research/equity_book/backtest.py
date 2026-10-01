"""Backtest core for the equity book (design sections 1 and 3).

``run_book(panel, decide, config) -> BookResult``

* ``panel`` -- :class:`~open_composer.research.equity_book.panel.PricePanel` (wide open/close of
  stocks and hedge ETFs).
* ``decide(t, state) -> dict[str, float] | None`` -- called at the close of each rebalance session
  ``t`` with a :class:`BookState` (everything known at that close).  It returns the *complete*
  target book as signed **fractions of equity** (``+0.5`` = long 50% of E, ``-0.5`` = short); any
  held symbol missing from the dict is closed.  The key ``"TBILL"`` is the T-bill sleeve
  (SGOV once it has prices, else BIL).  ``None`` means "no trade".  The fractions are applied to the
  equity at the trade, after the old holdings earned their overnight leg and before costs.
* ``config`` -- :class:`BookConfig`: rebalance schedule (weekly offset 0-4, monthly offset 0-20,
  daily), execution price, pluggable ``cost_fn``, borrow, margin, T-bill sleeve, delisting haircut.

Accounting (design section 1).  Holdings are kept in dollars per symbol; ``E`` is the account
equity.  With ``L`` = long market value (stocks and ETFs, not the sleeve), ``S`` = short market
value (absolute), ``Q`` = T-bill sleeve market value::

    cash   C = E - L - Q + S

``C`` earns nothing (short proceeds and credit cash pay no interest).  A negative ``C`` is debt and
pays ``margin_rate / 360`` per calendar day.  Short notional ``S`` pays ``borrow_bp_per_year / 1e4
/ 360`` per calendar day.  Both are booked on the first session after the balance existed, on the
*closing* balance of the previous session (``days`` = calendar days since that close).  The sleeve
earns its own price return.  Costs, borrow and margin reduce ``E``.

Daily returns follow :mod:`~open_composer.research.equity_book.returns`: ``net_i = E_close_i /
E_close_{i-1} - 1``; ``gross_i`` adds back every cost booked that day.  ``equity_open_pre`` /
``equity_open_post`` record E at the trade open before / after trade costs on trade days, so a
holding period between two entry opens is ``equity_open_pre[exit] / equity_open_post[entry] - 1``
(:meth:`BookResult.period_return`).

Not modelled: intraday financing on trade days, locate failures, fractional-share limits
(handled by the optimizer, D5).  Reg T (``L + S + Q <= 2E``) is not enforced; the daily frame
reports the exposures so the caller can count violations.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

import numpy as np
import pandas as pd

from open_composer.research.equity_book.panel import PricePanel
from open_composer.research.equity_book.returns import ExecPrice, day_legs, delist_positions

TBILL = "TBILL"
CostFn = Callable[[pd.DataFrame, "BookState"], "float | Mapping[str, float]"]
DecideFn = Callable[[pd.Timestamp, "BookState"], "Mapping[str, float] | None"]
TradeAttrs = Callable[[pd.Timestamp, Sequence[str]], pd.DataFrame]
COST_COMPONENTS = ("spread", "impact", "fees")
CASH_NOISE = 1e-9  # |C| below this fraction of E is rounding noise, not a margin loan


def signal_positions(dates: pd.DatetimeIndex, freq: str, offset: int = 0) -> list[int]:
    """Positions of the sessions at whose close ``decide`` is called.

    ``"M"``: last session of each calendar month, shifted ``offset`` sessions later; ``"W"``: last
    session of each calendar week (Mon-Sun), shifted ``offset`` sessions later; ``"D"``: every
    session.  Identical to ``screen_lane.signal_dates`` (tested)."""
    dates = pd.DatetimeIndex(dates)
    if freq == "D":
        return list(range(len(dates)))
    if freq not in ("M", "W"):
        raise ValueError(f"freq must be 'M', 'W' or 'D', got {freq!r}")
    key = dates.to_period("M" if freq == "M" else "W")
    s = pd.Series(dates, index=dates)
    last = s.groupby(key).transform("max")
    pos = np.flatnonzero((s == last).to_numpy()) + int(offset)
    return [int(p) for p in pos if p < len(dates)]


def flat_cost(bp_per_side: float) -> CostFn:
    """The default cost: ``bp_per_side`` basis points of traded notional, booked as ``spread``."""

    def fn(trades: pd.DataFrame, state: BookState) -> dict[str, float]:
        return {"spread": float(trades["dollar_trade"].abs().sum()) * bp_per_side / 1e4}

    return fn


@dataclass(frozen=True)
class BookConfig:
    """Run configuration.  Costs, borrow and margin are all optional and default to the frozen
    contract (10 bp per side, no borrow, 6.5%/360 margin)."""

    freq: Literal["W", "M", "D"] = "W"
    offset: int = 0
    exec_price: ExecPrice = "open"
    cost_fn: CostFn | None = None
    cost_bp_per_side: float = 10.0  # used when cost_fn is None
    borrow_bp_per_year: float = 0.0
    margin_rate: float = 0.065
    tbill_symbols: tuple[str, ...] = ("SGOV", "BIL")  # first one with a price that session
    delist_long_haircut: float = 0.0  # e.g. -0.30; applied to longs only
    initial_equity: float = 1.0
    initial_weights: Mapping[str, float] | None = None  # held at the first close of the run
    start: str | None = None
    end: str | None = None
    signal_dates: Sequence[pd.Timestamp] | None = None  # overrides freq/offset
    trade_attrs: TradeAttrs | None = None  # (decision_date, symbols) -> frame indexed by symbol
    snapshots: bool = True


@dataclass
class BookState:
    """What ``decide`` / ``cost_fn`` can see.  ``date`` is the decision close for ``decide`` and the
    trade session for ``cost_fn``; ``holdings`` are dollars, ``weights`` fractions of ``equity``
    (drifted, post-close for ``decide``)."""

    date: pd.Timestamp
    pos: int
    equity: float
    holdings: pd.Series
    weights: pd.Series
    cash: float
    long_value: float
    short_value: float
    tbill_value: float
    panel: PricePanel
    decision_date: pd.Timestamp | None = None
    exec_price: str = "open"


@dataclass
class BookResult:
    """Output of :func:`run_book`.  ``daily`` has one row per session in the run window with
    columns: ``net``, ``gross``, ``turnover`` (one-sided, fraction of E at the trade),
    ``cost_spread``,
    ``cost_impact``, ``cost_fees``, ``cost_borrow``, ``cost_margin`` (all fractions of the previous
    close equity), ``long_exp``, ``short_exp``, ``tbill_exp``, ``cash_exp`` (fractions of the
    closing
    equity), ``equity`` (close), ``equity_open_pre``, ``equity_open_post`` (trade days),
    ``is_trade_day``, ``n_long``, ``n_short``.  ``holdings`` maps the trade session to the
    post-trade
    weights (fractions of E).  ``info`` carries counters (delist exits, frozen halts, unknown
    symbols)."""

    daily: pd.DataFrame
    holdings: dict[pd.Timestamp, pd.Series]
    config: BookConfig
    info: dict[str, Any] = field(default_factory=dict)

    @property
    def net(self) -> pd.Series:
        return self.daily["net"]

    @property
    def gross(self) -> pd.Series:
        return self.daily["gross"]

    @property
    def turnover(self) -> pd.Series:
        return self.daily["turnover"]

    @property
    def costs(self) -> pd.DataFrame:
        cols = ["cost_spread", "cost_impact", "cost_fees", "cost_borrow", "cost_margin"]
        return self.daily[cols]

    def period_return(self, entry: pd.Timestamp, exit_: pd.Timestamp) -> float:
        """Holding return from the entry open (after costs) to the exit open (before costs)."""
        d = self.daily
        return float(d.loc[exit_, "equity_open_pre"] / d.loc[entry, "equity_open_post"] - 1.0)


def _resolve_sleeve(panel: PricePanel, symbols: Sequence[str], i: int, priced: np.ndarray) -> int:
    """Column of the T-bill sleeve on session ``i`` (first listed symbol with a price), or -1."""
    for s in symbols:
        if panel.has(s) and priced[i, panel.col(s)]:
            return panel.col(s)
    return -1


def run_book(panel: PricePanel, decide: DecideFn, config: BookConfig | None = None) -> BookResult:
    """Run a decision function through the daily accounting.  See the module docstring."""
    cfg = config or BookConfig()
    dates = panel.dates
    t_n, n_sym = panel.close.shape
    priced = np.isfinite(panel.close) & (panel.close > 0)
    delist_pos = delist_positions(priced)
    start_pos = 0 if cfg.start is None else int(dates.searchsorted(pd.Timestamp(cfg.start)))
    end_pos = (
        t_n - 1 if cfg.end is None else int(dates.searchsorted(pd.Timestamp(cfg.end), "right")) - 1
    )
    last_close = np.full(n_sym, np.nan)
    if start_pos > 0:  # last valid close before the run window, for the first overnight leg
        pre = priced[:start_pos]
        idx = start_pos - 1 - np.argmax(pre[::-1], axis=0)
        last_close = np.where(pre.any(axis=0), panel.close[idx, np.arange(n_sym)], np.nan)
    cost_fn = cfg.cost_fn or flat_cost(cfg.cost_bp_per_side)

    if cfg.signal_dates is not None:
        pos_of = {d: i for i, d in enumerate(dates)}
        sig = {pos_of[pd.Timestamp(d)] for d in cfg.signal_dates if pd.Timestamp(d) in pos_of}
    else:
        sig = set(signal_positions(dates, cfg.freq, cfg.offset))
    tbill_cols = {panel.col(s) for s in cfg.tbill_symbols if panel.has(s)}
    tbill_mask = np.zeros(n_sym, dtype=bool)
    for j in tbill_cols:
        tbill_mask[j] = True
    syms = panel.symbols

    h = np.zeros(n_sym)  # dollar holdings
    equity = float(cfg.initial_equity)
    if cfg.initial_weights:
        for s, w in cfg.initial_weights.items():
            sc = (
                _resolve_sleeve(panel, cfg.tbill_symbols, start_pos, priced) if s == TBILL else None
            )
            j = sc if sc is not None else (panel.col(s) if panel.has(s) else -1)
            if j >= 0:
                h[j] = w * equity

    n_days = end_pos - start_pos + 1
    cols = [
        "net",
        "gross",
        "turnover",
        "cost_spread",
        "cost_impact",
        "cost_fees",
        "cost_borrow",
        "cost_margin",
        "long_exp",
        "short_exp",
        "tbill_exp",
        "cash_exp",
        "equity",
        "equity_open_pre",
        "equity_open_post",
        "is_trade_day",
        "n_long",
        "n_short",
    ]
    out = np.full((n_days, len(cols)), np.nan)
    ci = {c: k for k, c in enumerate(cols)}
    snaps: dict[pd.Timestamp, pd.Series] = {}
    info = {
        "delist_exits": 0,
        "delist_haircut_dollars": 0.0,
        "frozen_halted_trades": 0,
        "unknown_symbols": 0,
        "nonfinite_weights": 0,
        "n_rebalances": 0,
        "reg_t_violation_days": 0,
        "bankrupt": False,
    }
    pending: dict[str, float] | None = None
    pending_decision: pd.Timestamp | None = None
    prev_date: pd.Timestamp | None = None
    e_prev = equity
    c_prev = 0.0
    s_prev = 0.0
    if np.any(h):
        long_v = float(h[(h > 0) & ~tbill_mask].sum())
        short_v = float(-h[(h < 0) & ~tbill_mask].sum())
        q_v = float(h[tbill_mask].sum())
        c_prev, s_prev = equity - long_v - q_v + short_v, short_v

    def exposures(hh: np.ndarray, e: float) -> tuple[float, float, float, float]:
        long_v = float(hh[(hh > 0) & ~tbill_mask].sum())
        short_v = float(-hh[(hh < 0) & ~tbill_mask].sum())
        q_v = float(hh[tbill_mask].sum())
        return long_v, short_v, q_v, e - long_v - q_v + short_v

    def make_state(i: int, e: float, decision: pd.Timestamp | None = None) -> BookState:
        nz = np.flatnonzero(h)
        long_v, short_v, q_v, c_v = exposures(h, e)
        hold = pd.Series(h[nz], index=syms[nz], dtype="float64")
        return BookState(
            date=dates[i],
            pos=i,
            equity=e,
            holdings=hold,
            weights=hold / e if e else hold,
            cash=c_v,
            long_value=long_v,
            short_value=short_v,
            tbill_value=q_v,
            panel=panel,
            decision_date=decision,
            exec_price=cfg.exec_price,
        )

    def trade(
        i: int, e_pre: float, decision: pd.Timestamp | None
    ) -> tuple[float, float, dict[str, float]]:
        """Move holdings to the pending target at ``exec_price``.  Returns (turnover, cost dollars,
        cost components)."""
        nonlocal h
        tgt = pending or {}
        px_row = eo if cfg.exec_price == "open" else panel.close[i]
        sleeve_col = _resolve_sleeve(panel, cfg.tbill_symbols, i, priced)
        target = np.zeros(n_sym)
        for s, w in tgt.items():
            if s == TBILL:
                j = sleeve_col
            elif panel.has(s):
                j = panel.col(s)
            else:
                info["unknown_symbols"] += 1
                continue
            if j < 0:
                info["unknown_symbols"] += 1
                continue
            if not np.isfinite(w):
                info["nonfinite_weights"] += 1
                continue
            target[j] += w * e_pre
        can = priced[i] & np.isfinite(px_row)
        # a symbol that cannot be priced today keeps its holding (halted / not yet listed)
        frozen = ~can & ((h != 0) | (target != 0))
        info["frozen_halted_trades"] += int((frozen & (target != h)).sum())
        target = np.where(~can, h, target)
        trades = target - h
        nz = np.flatnonzero(trades)
        turnover = float(np.abs(trades[nz]).sum() / e_pre) if e_pre else 0.0
        comps = {k: 0.0 for k in COST_COMPONENTS}
        if len(nz):
            tdf = pd.DataFrame(
                {
                    "symbol": syms[nz],
                    "dollar_trade": trades[nz],
                    "price": px_row[nz],
                    "trade_date": dates[i],
                }
            )
            if cfg.trade_attrs is not None and decision is not None:
                att = cfg.trade_attrs(decision, list(tdf["symbol"]))
                for c in att.columns:
                    if c not in tdf.columns:
                        tdf[c] = att[c].to_numpy()
            st = make_state(i, e_pre, decision)
            res = cost_fn(tdf, st)
            if isinstance(res, Mapping):
                for k, v in res.items():
                    comps[k if k in comps else "spread"] += float(v)
            else:
                comps["spread"] += float(res)
        h = target
        return turnover, float(sum(comps.values())), comps

    def snapshot(date: pd.Timestamp, e: float) -> None:
        if cfg.snapshots:
            nz = np.flatnonzero(h)
            snaps[date] = pd.Series(h[nz] / e if e > 0 else h[nz], index=syms[nz])

    for i in range(start_pos, end_pos + 1):
        date = dates[i]
        k = i - start_pos
        cost_borrow = cost_margin = 0.0
        if prev_date is not None:
            days = (date - prev_date).days
            debt = -c_prev if -c_prev > CASH_NOISE * abs(e_prev) else 0.0  # float noise is not debt
            cost_margin = debt * cfg.margin_rate / 360.0 * days
            cost_borrow = s_prev * cfg.borrow_bp_per_year / 1e4 / 360.0 * days
        elif np.any(h):
            cost_margin = cost_borrow = 0.0
        equity -= cost_margin + cost_borrow

        # delistings: leave at the last valid close, longs take the optional haircut
        dl = np.flatnonzero((delist_pos == i) & (h != 0))
        for j in dl:
            info["delist_exits"] += 1
            if h[j] > 0 and cfg.delist_long_haircut != 0.0:
                hit = cfg.delist_long_haircut * h[j]  # negative number
                equity += hit
                info["delist_haircut_dollars"] += float(hit)
            h[j] = 0.0

        turnover = 0.0
        comps = {kk: 0.0 for kk in COST_COMPONENTS}
        is_trade = pending is not None
        e_open_pre = e_open_post = np.nan

        ov_i, intra_i, eo, _pr = day_legs(panel.open[i], panel.close[i], last_close)
        # overnight leg
        equity += float(h @ ov_i)
        h = h * (1.0 + ov_i)
        if is_trade and cfg.exec_price == "open":
            e_open_pre = equity
            turnover, cost, comps = trade(i, equity, pending_decision)
            equity -= cost
            e_open_post = equity
            info["n_rebalances"] += 1
            snapshot(date, equity)
        # intraday leg
        equity += float(h @ intra_i)
        h = h * (1.0 + intra_i)
        if is_trade and cfg.exec_price == "close":
            e_open_pre = equity
            turnover, cost, comps = trade(i, equity, pending_decision)
            equity -= cost
            e_open_post = equity
            info["n_rebalances"] += 1
            snapshot(date, equity)
        pending = None
        pending_decision = None
        last_close = np.where(priced[i], panel.close[i], last_close)

        long_v, short_v, q_v, c_v = exposures(h, equity)
        c_prev, s_prev = c_v, short_v
        trade_costs = sum(comps.values())
        total_costs = trade_costs + cost_margin + cost_borrow
        row = out[k]
        row[ci["net"]] = equity / e_prev - 1.0
        row[ci["gross"]] = (equity + total_costs) / e_prev - 1.0
        row[ci["turnover"]] = turnover
        row[ci["cost_spread"]] = comps["spread"] / e_prev
        row[ci["cost_impact"]] = comps["impact"] / e_prev
        row[ci["cost_fees"]] = comps["fees"] / e_prev
        row[ci["cost_borrow"]] = cost_borrow / e_prev
        row[ci["cost_margin"]] = cost_margin / e_prev
        row[ci["equity"]] = equity
        row[ci["equity_open_pre"]] = e_open_pre
        row[ci["equity_open_post"]] = e_open_post
        row[ci["is_trade_day"]] = float(is_trade)
        if equity > 0:
            row[ci["long_exp"]] = long_v / equity
            row[ci["short_exp"]] = short_v / equity
            row[ci["tbill_exp"]] = q_v / equity
            row[ci["cash_exp"]] = c_v / equity
            if long_v + short_v + q_v > 2.02 * equity:  # 1% drift tolerance on the Reg T cap
                info["reg_t_violation_days"] += 1
        row[ci["n_long"]] = int(((h > 0) & ~tbill_mask).sum())
        row[ci["n_short"]] = int(((h < 0) & ~tbill_mask).sum())
        prev_date = date
        e_prev = equity
        if equity <= 0:
            info["bankrupt"] = True
            out[k + 1 :, ci["net"]] = 0.0
            break
        if i in sig and i < end_pos:
            raw = decide(date, make_state(i, equity))
            if raw is not None:
                pending = dict(raw)
                pending_decision = date

    daily = pd.DataFrame(out, index=dates[start_pos : end_pos + 1], columns=cols)
    daily["is_trade_day"] = daily["is_trade_day"].fillna(0.0).astype(bool)
    return BookResult(daily=daily, holdings=snaps, config=cfg, info=info)
