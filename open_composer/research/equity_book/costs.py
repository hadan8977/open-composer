"""D4: transaction-cost model for the multi-signal equity book (design section 7).

Components, all in basis points of traded notional unless stated:

* **half spread** -- ``half_spread_bp``: a log-linear model calibrated on Alpaca SIP NBBO
  samples (``scripts/sample_equity_book_spreads.py``), one coefficient set per snapshot
  (``open`` 09:35-09:45 ET median, ``mid`` 12:00 ET, ``close`` 15:45 ET)::

      log(hs_bp) = a + b*log(price) + c*log(dollar_adv_21) + d*log(vol_21) + year effect

  The target ``(ask - bid) / 2 / mid * 1e4`` is scale free, so no raw/adjusted price
  rescaling is needed on the *target*.  The ``price`` regressor is the ``daily_broad`` close
  of the prior session (the same field the backtest panel carries).
* **impact** -- ``impact_bp``: square-root law ``Y * sigma_daily * sqrt(Q / V)``.
* **fees** -- ``FEES_BP_PER_SIDE``.
* **borrow** -- ``borrow_bp_per_year``.

``trade_cost_dollars`` plugs into the backtest as ``cost_fn(trades, state)``.  The expected
``trades`` columns (documented because the backtest signature is owned by ``backtest.py``):

``symbol``, ``dollar_trade`` (signed dollars, buy > 0; ``abs`` is what is costed), ``price``,
``dollar_adv_21``, ``vol_21`` (daily return std, e.g. 0.02), ``trade_date``.  Column names
can be remapped through ``columns=``.  Extra columns are ignored.

Costs are charged per side on the traded notional (half spread + impact + fees), so a round
trip pays them twice.  Borrow is a carry cost on short exposure, not a trade cost; use
``borrow_cost_dollars_per_day``.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

MODEL_PATH = Path(__file__).with_name("cost_model_v1.json")
SNAPSHOTS = ("open", "mid", "close")
FEES_BP_PER_SIDE = 0.5
IMPACT_Y = 0.5
BORROW_BP_PER_YEAR_BASE = 25.0
BORROW_BP_PER_YEAR_STRESS = 100.0
TRADING_DAYS_PER_YEAR = 252
HS_BP_FLOOR = 0.25  # numerical floor / cap guard on the predicted half spread
HS_BP_CAP = 500.0

DEFAULT_COLUMNS = {
    "dollar_trade": "dollar_trade",
    "price": "price",
    "dollar_adv_21": "dollar_adv_21",
    "vol_21": "vol_21",
    "trade_date": "trade_date",
}


# --------------------------------------------------------------------------
# quote arithmetic (used by the sampler; tested)
# --------------------------------------------------------------------------


def quote_half_spread_bp(bid: Any, ask: Any) -> np.ndarray:
    """Half spread in bp, ``(ask - bid) / 2 / mid * 1e4`` with ``mid = (ask + bid) / 2``.

    The valid-quote rule of ``scripts/run_t20260930_15_quote_check.py`` applies: ``bid > 0``
    and ``ask > bid`` (zero, crossed, locked and non-finite quotes give NaN)."""
    b = np.asarray(bid, dtype="float64")
    a = np.asarray(ask, dtype="float64")
    ok = np.isfinite(b) & np.isfinite(a) & (b > 0) & (a > b)
    with np.errstate(invalid="ignore", divide="ignore"):
        mid = (a + b) / 2.0
        hs = (a - b) / 2.0 / mid * 1e4
    return np.where(ok, hs, np.nan)


# --------------------------------------------------------------------------
# fitted model
# --------------------------------------------------------------------------


def design_matrix(
    price: Any, dollar_adv_21: Any, vol_21: Any, year: Any, years: list[int] | None = None
) -> np.ndarray:
    """Columns: const, log price, log dollar_adv_21, log vol_21, then year dummies for
    ``years[1:]`` (the first year is the baseline).  ``years=None`` omits the dummies."""
    p = np.asarray(price, dtype="float64")
    v = np.asarray(dollar_adv_21, dtype="float64")
    s = np.asarray(vol_21, dtype="float64")
    y = np.asarray(year)
    p, v, s, y = np.broadcast_arrays(p, v, s, y)
    with np.errstate(invalid="ignore", divide="ignore"):
        cols = [np.ones(p.shape), np.log(p), np.log(v), np.log(s)]
    for yr in (years or [])[1:]:
        cols.append((y == yr).astype("float64"))
    return np.column_stack([c.reshape(-1) for c in cols])


def fit_log_linear(
    hs_bp: Any, price: Any, dollar_adv_21: Any, vol_21: Any, year: Any
) -> dict[str, Any]:
    """OLS by ``numpy.linalg.lstsq``.  Returns the coefficient dict stored in the JSON."""
    hs = np.asarray(hs_bp, dtype="float64")
    yr = np.asarray(year).astype(int)
    years = sorted({int(v) for v in yr})
    x = design_matrix(price, dollar_adv_21, vol_21, yr, years)
    y = np.log(hs)
    ok = np.isfinite(y) & np.isfinite(x).all(axis=1)
    beta, *_ = np.linalg.lstsq(x[ok], y[ok], rcond=None)
    resid = y[ok] - x[ok] @ beta
    return {
        "a": float(beta[0]),
        "b_log_price": float(beta[1]),
        "c_log_dollar_adv_21": float(beta[2]),
        "d_log_vol_21": float(beta[3]),
        "year_effects": {str(yr_): float(b) for yr_, b in zip(years[1:], beta[4:], strict=True)},
        "baseline_year": years[0],
        "n": int(ok.sum()),
        "smearing_factor": float(np.mean(np.exp(resid))),
        "resid_sd": float(resid.std(ddof=x.shape[1])) if ok.sum() > x.shape[1] else None,
        "r2": float(1.0 - resid.var() / y[ok].var()) if ok.sum() > 1 else None,
    }


def load_model(path: Path | str | None = None) -> dict[str, Any]:
    with open(path or MODEL_PATH, encoding="utf-8") as fh:
        return json.load(fh)


def predict_half_spread_bp(
    coef: Mapping[str, Any],
    price: Any,
    dollar_adv_21: Any,
    vol_21: Any,
    year: Any,
    *,
    smear: bool = True,
) -> np.ndarray:
    """exp(linear predictor), times the Duan smearing factor ``mean(exp(residual))`` when
    ``smear`` (default: the conditional *mean* spread, which is what a cost model charges;
    ``smear=False`` gives the conditional median).

    Years before the first fitted year use the baseline-year effect; years after the last
    fitted year use the last fitted year's effect (no extrapolated trend)."""
    p = np.asarray(price, dtype="float64")
    shape = np.broadcast(p, np.asarray(dollar_adv_21), np.asarray(vol_21), np.asarray(year)).shape
    eta = (
        coef["a"]
        + coef["b_log_price"] * np.log(p)
        + coef["c_log_dollar_adv_21"] * np.log(np.asarray(dollar_adv_21, dtype="float64"))
        + coef["d_log_vol_21"] * np.log(np.asarray(vol_21, dtype="float64"))
    )
    effects = {int(k): float(v) for k, v in coef.get("year_effects", {}).items()}
    base = int(coef.get("baseline_year", min(effects) if effects else 0))
    effects[base] = 0.0
    fitted = sorted(effects)
    yr = np.clip(np.asarray(year).astype(int), fitted[0], fitted[-1])
    eff = np.zeros(np.shape(yr), dtype="float64")
    for k in fitted:
        eff = np.where(yr == k, effects[k], eff)
    eta = np.asarray(eta + eff, dtype="float64")
    out = np.exp(eta) * (float(coef.get("smearing_factor", 1.0)) if smear else 1.0)
    return np.clip(out, HS_BP_FLOOR, HS_BP_CAP).reshape(shape)


def half_spread_bp(
    price: Any,
    dollar_adv_21: Any,
    vol_21: Any,
    year: Any,
    snapshot: str = "open",
    model: Mapping[str, Any] | None = None,
    price_basis: str = "adjusted",
) -> np.ndarray:
    """Vectorised predicted mean half spread in bp for ``snapshot`` in ``open|mid|close``.

    ``price_basis="adjusted"`` (default) expects the split/dividend-adjusted ``daily_broad``
    close the model was fitted on; ``"printed"`` selects the sensitivity fit on the as-printed
    price (better fit, but only valid when the panel carries unadjusted prices).
    Fills (``nan`` inputs) propagate as NaN; callers decide how to treat untradable rows."""
    if snapshot not in SNAPSHOTS:
        raise ValueError(f"snapshot must be one of {SNAPSHOTS}, got {snapshot!r}")
    if price_basis not in ("adjusted", "printed"):
        raise ValueError("price_basis must be 'adjusted' or 'printed'")
    m = model if model is not None else load_model()
    key = "snapshots" if price_basis == "adjusted" else "snapshots_printed_price"
    return predict_half_spread_bp(m[key][snapshot], price, dollar_adv_21, vol_21, year)


# --------------------------------------------------------------------------
# impact, fees, borrow
# --------------------------------------------------------------------------


def impact_bp(trade_dollars: Any, dollar_adv: Any, daily_vol: Any, Y: float = IMPACT_Y) -> Any:
    """Square-root law: ``Y * sigma_daily * sqrt(Q / V)`` in bp (sigma as a return fraction,
    Q and V in dollars).  Zero when the trade or ADV is zero/non-positive."""
    q = np.abs(np.asarray(trade_dollars, dtype="float64"))
    v = np.asarray(dollar_adv, dtype="float64")
    s = np.asarray(daily_vol, dtype="float64")
    with np.errstate(invalid="ignore", divide="ignore"):
        out = Y * s * np.sqrt(np.where(v > 0, q / v, 0.0)) * 1e4
    return out


def borrow_bp_per_year(is_short_eligible: Any, stress: bool = False) -> Any:
    """Borrow carry in bp per year.  Base 25 bp for short-eligible names, 100 bp in stress
    mode.  Names outside the short-eligible set must not be shorted: NaN is returned for
    them so a stray short position poisons the P&L loudly instead of being cheap."""
    rate = BORROW_BP_PER_YEAR_STRESS if stress else BORROW_BP_PER_YEAR_BASE
    elig = np.asarray(is_short_eligible, dtype=bool)
    out = np.where(elig, rate, np.nan)
    return float(out) if out.ndim == 0 else out


def borrow_cost_dollars_per_day(
    short_dollars: Any, is_short_eligible: Any, stress: bool = False
) -> np.ndarray:
    """Daily borrow carry in dollars: ``|short| * bp_per_year / 1e4 / 252``."""
    bp = borrow_bp_per_year(is_short_eligible, stress)
    return np.abs(np.asarray(short_dollars, dtype="float64")) * bp / 1e4 / TRADING_DAYS_PER_YEAR


# --------------------------------------------------------------------------
# backtest hook
# --------------------------------------------------------------------------


def trade_cost_bp(
    trades: pd.DataFrame,
    *,
    snapshot: str = "open",
    model: Mapping[str, Any] | None = None,
    columns: Mapping[str, str] | None = None,
    include_impact: bool = True,
    fees_bp: float = FEES_BP_PER_SIDE,
    impact_y: float = IMPACT_Y,
    price_basis: str = "adjusted",
) -> pd.Series:
    """Per-row one-side cost in bp: half spread + impact + fees."""
    col = {**DEFAULT_COLUMNS, **(columns or {})}
    year = pd.to_datetime(trades[col["trade_date"]]).dt.year.to_numpy()
    hs = half_spread_bp(
        trades[col["price"]].to_numpy(dtype="float64"),
        trades[col["dollar_adv_21"]].to_numpy(dtype="float64"),
        trades[col["vol_21"]].to_numpy(dtype="float64"),
        year,
        snapshot,
        model,
        price_basis,
    )
    total = hs + fees_bp
    if include_impact:
        total = total + impact_bp(
            trades[col["dollar_trade"]].to_numpy(dtype="float64"),
            trades[col["dollar_adv_21"]].to_numpy(dtype="float64"),
            trades[col["vol_21"]].to_numpy(dtype="float64"),
            impact_y,
        )
    return pd.Series(total, index=trades.index, name="cost_bp")


def trade_cost_dollars(
    trades: pd.DataFrame,
    state: Any = None,
    *,
    snapshot: str = "open",
    model: Mapping[str, Any] | None = None,
    columns: Mapping[str, str] | None = None,
    include_impact: bool = True,
    fees_bp: float = FEES_BP_PER_SIDE,
    impact_y: float = IMPACT_Y,
    price_basis: str = "adjusted",
) -> float:
    """Total one-side cost in dollars of ``trades`` (a ``cost_fn(trades, state)`` hook;
    ``state`` is accepted and ignored).  Rows with a non-finite cost input are costed at the
    worst (capped) half spread rather than dropped, so missing data never makes trading free."""
    if len(trades) == 0:
        return 0.0
    col = {**DEFAULT_COLUMNS, **(columns or {})}
    bp = trade_cost_bp(
        trades,
        snapshot=snapshot,
        model=model,
        columns=columns,
        include_impact=include_impact,
        fees_bp=fees_bp,
        impact_y=impact_y,
        price_basis=price_basis,
    ).to_numpy()
    bp = np.where(np.isfinite(bp), bp, HS_BP_CAP + fees_bp)
    notional = np.abs(trades[col["dollar_trade"]].to_numpy(dtype="float64"))
    return float(np.nansum(notional * bp / 1e4))


def flat_cost_bp(bp_per_side: float, n: int) -> np.ndarray:
    """Comparison helper: the frozen flat per-side cost."""
    return np.full(n, float(bp_per_side))


def tiered_cost_bp(adv_rank: Any) -> np.ndarray:
    """Tiers of ``scripts/run_h20260929_21_lockup_books.py`` (``SPREAD_BPS_TIERS``):
    3 bp for adv_rank <= 500, 6 to 1000, 12 to 1500, 25 beyond (and for NaN)."""
    r = np.asarray(adv_rank, dtype="float64")
    out = np.where(r <= 500, 3.0, np.where(r <= 1000, 6.0, np.where(r <= 1500, 12.0, 25.0)))
    return np.where(np.isfinite(r), out, 25.0)
