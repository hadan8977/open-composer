"""``BookConfig.cost_fn`` for the equity book (design section 7), built from ``costs.py``.

``make_cost_fn(snapshot)`` returns ``cost_fn(trades, state) -> {"spread", "impact", "fees"}`` in
dollars.  Per traded row (one side):

* stock: half spread ``half_spread_bp(prior_close, dollar_adv_21, vol_21, year, snapshot)`` (the
  ``price`` regressor is the prior-session close of the panel, as fitted), impact
  ``impact_bp(|trade|, dollar_adv_21, vol_21)``, fees ``FEES_BP_PER_SIDE``;
* hedge ETF and T-bill ETF (``HEDGE_ETFS`` symbols): fixed half spread ``etf_half_spread_bp``
  (default 1 bp), no impact, the same fees;
* a stock row with a missing cost input is charged ``missing_half_spread_bp`` (default 40 bp,
  the top of the U3000 decile means at the open) and no impact, so missing data never makes a
  trade free.

``snapshot_for(exec_price)`` maps the backtest's ``exec_price`` to the matching spread snapshot
("open" -> "open", "close" -> "close").  Borrow is not a trade cost: the backtest charges it daily
from ``BookConfig.borrow_bp_per_year`` on the closing short notional.  Expected ``trades`` columns:
``symbol``, ``dollar_trade``, ``price``, ``trade_date`` plus the attributes of
``PanelAttributes.trade_attrs`` (``dollar_adv_21``, ``vol_21``, ``prior_close``).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

import numpy as np
import pandas as pd

from open_composer.research.equity_book.costs import (
    FEES_BP_PER_SIDE,
    IMPACT_Y,
    half_spread_bp,
    impact_bp,
    load_model,
)
from open_composer.research.equity_book.panel import HEDGE_ETFS

ETF_HALF_SPREAD_BP = 1.0
MISSING_HALF_SPREAD_BP = 40.0


def snapshot_for(exec_price: str) -> str:
    """Spread snapshot that matches the execution price of the backtest."""
    if exec_price not in ("open", "close"):
        raise ValueError(f"exec_price must be 'open' or 'close', got {exec_price!r}")
    return exec_price


def make_cost_fn(
    snapshot: str,
    *,
    model: Mapping[str, Any] | None = None,
    etf_half_spread_bp: float = ETF_HALF_SPREAD_BP,
    missing_half_spread_bp: float = MISSING_HALF_SPREAD_BP,
    fees_bp: float = FEES_BP_PER_SIDE,
    impact_y: float = IMPACT_Y,
    include_impact: bool = True,
    etf_symbols: frozenset[str] | set[str] = frozenset(HEDGE_ETFS),
) -> Callable[[pd.DataFrame, Any], dict[str, float]]:
    """Cost function for ``BookConfig.cost_fn`` using the spread snapshot ``snapshot``."""
    m = model if model is not None else load_model()

    def cost_fn(trades: pd.DataFrame, state: Any = None) -> dict[str, float]:
        if len(trades) == 0:
            return {"spread": 0.0, "impact": 0.0, "fees": 0.0}
        notional = np.abs(trades["dollar_trade"].to_numpy("float64"))
        is_etf = trades["symbol"].isin(etf_symbols).to_numpy()
        n = len(trades)
        adv = _col(trades, "dollar_adv_21", n)
        vol = _col(trades, "vol_21", n)
        price = _col(trades, "prior_close", n)
        price = np.where(np.isfinite(price), price, _col(trades, "price", n))
        year = pd.to_datetime(trades["trade_date"]).dt.year.to_numpy()
        with np.errstate(invalid="ignore", divide="ignore"):
            hs = half_spread_bp(price, adv, vol, year, snapshot, m)
        hs = np.where(np.isfinite(hs), hs, missing_half_spread_bp)
        hs = np.where(is_etf, etf_half_spread_bp, hs)
        imp = np.zeros(n)
        if include_impact:
            raw = impact_bp(notional, adv, vol, impact_y)
            imp = np.where(is_etf | ~np.isfinite(raw), 0.0, raw)
        return {
            "spread": float(np.sum(notional * hs / 1e4)),
            "impact": float(np.sum(notional * imp / 1e4)),
            "fees": float(np.sum(notional) * fees_bp / 1e4),
        }

    return cost_fn


def _col(df: pd.DataFrame, name: str, n: int) -> np.ndarray:
    if name in df.columns:
        return df[name].to_numpy("float64")
    return np.full(n, np.nan)
