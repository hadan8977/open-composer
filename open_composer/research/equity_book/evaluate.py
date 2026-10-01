"""Evaluation of a backtest result against the frozen windows and gates (design sections 9-10).

Windows (frozen, design section 9)::

    stress  2017-10-02 .. 2023-08-31
    gap     2023-09-01 .. 2023-12-31   (reported alone)
    anchor  2024-01-08 .. 2026-09-17

Per-window metrics (:func:`window_metrics`), all on daily series:

* ``ann_excess_return`` -- ``mean(net - rf) * 252`` where ``rf`` is the BIL total return
  (arithmetic annualisation of the daily excess).
* ``vol`` -- ``std(net - rf, ddof=1) * sqrt(252)``; ``sharpe`` -- ``mean/std`` of the daily excess
  times ``sqrt(252)`` (same as ``run_h20260918_05_recent_menu.metrics``).
* ``nw_t`` -- Newey-West t of the daily mean excess, Bartlett weights, lag 5.
* ``max_dd`` -- worst peak-to-trough of the compounded net series.
* ``turnover`` -- annualised one-sided turnover ``mean(daily turnover) * 252`` (fraction of equity).
* ``cost_share`` -- total costs (trade, borrow, margin) over the gross return sum; NaN when the
  gross
  sum is not positive.
* ``beta_spy`` / ``corr_spy`` -- slope / correlation of daily net on daily SPY close-to-close.

K1 / K2 are *not* reimplemented: :func:`k2_edges` calls
``screen_lane.diversifier_edge_for_offset`` (with ``s3_incumbent`` and the screen-lane panel loader,
:func:`load_s3_context`).  K1 is the Sharpe check of the frozen contract (anchor >= 1.19, stress >=
0.65, and positive annualised excess return at 2x cost in both windows); K2 flags edge >= 0.05
(research_pass line) and >= 0.10 (strong keep).
"""

from __future__ import annotations

import math
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from open_composer.research.equity_book.backtest import BookResult
from open_composer.research.equity_book.panel import DEFAULT_DIR

ROOT = Path(__file__).resolve().parents[3]
WINDOWS: dict[str, tuple[str, str]] = {
    "stress": ("2017-10-02", "2023-08-31"),
    "gap": ("2023-09-01", "2023-12-31"),
    "anchor": ("2024-01-08", "2026-09-17"),
}
K1_ANCHOR_SHARPE = 1.19
K1_STRESS_SHARPE = 0.65
K2_EDGE = 0.05
K2_EDGE_STRONG = 0.10
NW_LAGS = 5
TRADING_DAYS = 252
DSR_TRIALS = 77  # 12 grid cells + 65 Stage-0 cells (design section 9)
DSR_HAC_LAG = 21


def newey_west_t(x: np.ndarray, lags: int = NW_LAGS) -> float:
    """t-statistic of the mean with a Bartlett-weighted long-run variance."""
    x = np.asarray(x, dtype="float64")
    x = x[np.isfinite(x)]
    n = len(x)
    if n < lags + 3:
        return float("nan")
    d = x - x.mean()
    s = float(d @ d) / n
    for lag in range(1, lags + 1):
        s += 2.0 * (1.0 - lag / (lags + 1.0)) * float(d[lag:] @ d[:-lag]) / n
    if s <= 0:
        return float("nan")
    return float(x.mean() / math.sqrt(s / n))


def max_drawdown(r: np.ndarray) -> float:
    r = np.asarray(r, dtype="float64")
    r = r[np.isfinite(r)]
    if len(r) == 0:
        return float("nan")
    eq = np.concatenate([[1.0], np.cumprod(1.0 + r)])
    return float((eq / np.maximum.accumulate(eq) - 1.0).min())


def load_rf_spy(base_dir: Path | str = DEFAULT_DIR) -> tuple[pd.Series, pd.Series]:
    """Daily total returns of BIL (``rf``) and SPY from ``etf_daily.parquet``, close to close on the
    ETF calendar (first session 0), the same construction as ``screen_lane.load_batch_panel``."""
    etf = pd.read_parquet(
        Path(base_dir) / "etf_daily.parquet", columns=["trade_date", "symbol", "close"]
    )
    c = etf.pivot(index="trade_date", columns="symbol", values="close").sort_index()
    rf = (c["BIL"] / c["BIL"].shift(1) - 1.0).fillna(0.0)
    spy = (c["SPY"] / c["SPY"].shift(1) - 1.0).fillna(0.0)
    return rf, spy


def window_metrics(
    net: pd.Series,
    rf: pd.Series,
    spy: pd.Series,
    window: tuple[str, str],
    daily: pd.DataFrame | None = None,
) -> dict[str, float]:
    """Metrics of ``net`` in ``window``; ``daily`` (``BookResult.daily``) adds turnover, costs."""
    a, b = window
    sub = net[(net.index >= a) & (net.index <= b)].dropna()
    n = len(sub)
    if n < 20:
        return {"n": n}
    ex = sub - rf.reindex(sub.index).fillna(0.0)
    sd = float(ex.std(ddof=1))
    mu = float(ex.mean())
    sp = spy.reindex(sub.index).fillna(0.0)
    out: dict[str, float] = {
        "n": n,
        "ann_excess_return": mu * TRADING_DAYS,
        "vol": sd * math.sqrt(TRADING_DAYS),
        "sharpe": mu / sd * math.sqrt(TRADING_DAYS) if sd > 0 else float("nan"),
        "nw_t": newey_west_t(ex.to_numpy()),
        "max_dd": max_drawdown(sub.to_numpy()),
        "beta_spy": float(np.cov(sub, sp, ddof=1)[0, 1] / sp.var(ddof=1))
        if sp.var() > 0
        else float("nan"),
        "corr_spy": float(np.corrcoef(sub, sp)[0, 1])
        if sp.std() > 0 and sub.std() > 0
        else float("nan"),
    }
    if daily is not None:
        d = daily.loc[sub.index]
        out["turnover"] = float(d["turnover"].mean() * TRADING_DAYS)
        costs = float(
            d[["cost_spread", "cost_impact", "cost_fees", "cost_borrow", "cost_margin"]].sum().sum()
        )
        gross = float(d["gross"].sum())
        out["cost_share"] = costs / gross if gross > 0 else float("nan")
        out["avg_long_exp"] = float(d["long_exp"].mean())
        out["avg_short_exp"] = float(d["short_exp"].mean())
        out["avg_tbill_exp"] = float(d["tbill_exp"].mean())
    return out


def evaluate_book(
    result: BookResult | pd.Series,
    rf: pd.Series,
    spy: pd.Series,
    windows: Mapping[str, tuple[str, str]] = WINDOWS,
) -> dict[str, dict[str, float]]:
    """:func:`window_metrics` for every window."""
    net = result.net if isinstance(result, BookResult) else result
    daily = result.daily if isinstance(result, BookResult) else None
    return {w: window_metrics(net, rf, spy, win, daily) for w, win in windows.items()}


def k1_check(
    metrics10: Mapping[str, Mapping[str, float]], metrics20: Mapping[str, Mapping[str, float]]
) -> dict[str, Any]:
    """K1 of the frozen contract: anchor Sharpe >= 1.19, stress Sharpe >= 0.65 (model-cost series),
    and annualised excess return > 0 in both windows at 2x cost (``metrics20`` from the same book
    run with doubled costs)."""
    a, s = metrics10["anchor"], metrics10["stress"]
    a2, s2 = metrics20["anchor"], metrics20["stress"]
    parts = {
        "anchor_sharpe_ge_1.19": bool(a.get("sharpe", -np.inf) >= K1_ANCHOR_SHARPE),
        "stress_sharpe_ge_0.65": bool(s.get("sharpe", -np.inf) >= K1_STRESS_SHARPE),
        "anchor_excess_positive_2x_cost": bool(a2.get("ann_excess_return", -np.inf) > 0),
        "stress_excess_positive_2x_cost": bool(s2.get("ann_excess_return", -np.inf) > 0),
    }
    return {
        "pass": all(parts.values()),
        "parts": parts,
        "anchor_sharpe": a.get("sharpe"),
        "stress_sharpe": s.get("sharpe"),
    }


# -------------------------------------------------------------------- K2 via screen_lane


@dataclass
class S3Context:
    """Everything ``screen_lane.diversifier_edge_for_offset`` needs besides the candidate series."""

    s3_ret10: pd.Series
    shy_ret: pd.Series
    rf: pd.Series
    s3_sharpe: dict[str, float]


def _lane():
    sys.path.insert(0, str(ROOT / "scripts"))
    import screen_lane as lane  # noqa: PLC0415

    return lane


def load_s3_context(windows: Mapping[str, tuple[str, str]] = WINDOWS) -> S3Context:
    """Load the screen-lane S3 panel (``screen_lane.load_batch_panel`` with no extra symbols; a few
    SIP ETFs, small) and the live month-end S3 at 10 bp per side (``screen_lane.s3_incumbent``)."""
    lane = _lane()
    close, _open, leg_open, leg_close, rf = lane.load_batch_panel([])
    s3, _turn = lane.s3_incumbent(close, leg_open, leg_close, lane.COST_BPS_PRIMARY)
    shy = (close[lane.CASH] / close[lane.CASH].shift(1) - 1.0).fillna(0.0)
    s3_sharpe = {}
    for name, (a, b) in windows.items():
        sub = s3[(s3.index >= a) & (s3.index <= b)]
        ex = sub - rf.reindex(sub.index).fillna(0.0)
        s3_sharpe[name] = float(ex.mean() / ex.std(ddof=1) * math.sqrt(TRADING_DAYS))
    return S3Context(s3_ret10=s3, shy_ret=shy, rf=rf, s3_sharpe=s3_sharpe)


def assert_session_convention(
    net: pd.Series, ctx: S3Context, window: tuple[str, str] = WINDOWS["anchor"]
) -> None:
    """Raise if ``net`` sits one session off the S3 engine's convention
    (``screen_lane.assert_same_session_convention``; :func:`k2_edges` applies it too)."""
    _lane().assert_same_session_convention(net, ctx.s3_ret10, window)


def k2_edges(
    net10: pd.Series,
    ctx: S3Context,
    windows: Mapping[str, tuple[str, str]] = WINDOWS,
    names: tuple[str, ...] = ("stress", "anchor"),
) -> dict[str, Any]:
    """K2 diversifier edge (Sharpe of S3 + candidate, inverse-vol, minus the vol-matched S3/SHY
    control) in each window, straight from ``screen_lane.diversifier_edge_for_offset``, with the
    0.05 and 0.10 flags."""
    lane = _lane()
    edges = {
        w: float(
            lane.diversifier_edge_for_offset(ctx.s3_ret10, net10, ctx.shy_ret, ctx.rf, windows[w])
        )
        for w in names
    }
    return {
        "edge": edges,
        "pass_0.05": bool(all(v >= K2_EDGE for v in edges.values())),
        "pass_0.10": bool(all(v >= K2_EDGE_STRONG for v in edges.values())),
    }


def median_over_offsets(values: Mapping[int, float]) -> float:
    """The judged value: the median across rebalance offsets."""
    return float(np.median(list(values.values())))


# -------------------------------------------------------------------- placebo / DSR


def permute_within_date(alpha: pd.DataFrame, seed: int) -> pd.DataFrame:
    """Placebo: shuffle ``alpha`` across symbols independently inside every date.

    ``alpha`` is a wide frame (rows = dates, columns = symbols).  NaN cells keep their place, so
    the eligible set of each date is unchanged; only which name carries which score is destroyed.
    The construction (universe, constraints, risk model) is meant to be reused unchanged.
    """
    rng = np.random.default_rng(seed)
    a = alpha.to_numpy(dtype="float64")
    out = a.copy()
    for i in range(a.shape[0]):
        idx = np.flatnonzero(np.isfinite(a[i]))
        if len(idx) > 1:
            out[i, idx] = a[i, rng.permutation(idx)]
    return pd.DataFrame(out, index=alpha.index, columns=alpha.columns)


def permute_within_date_long(
    df: pd.DataFrame, value_col: str, seed: int, date_col: str = "trade_date"
) -> pd.DataFrame:
    """Long-format variant of :func:`permute_within_date` (returns a copy)."""
    rng = np.random.default_rng(seed)
    out = df.copy()
    vals = out[value_col].to_numpy(dtype="float64").copy()
    for _, idx in out.groupby(date_col, sort=True).indices.items():
        ok = idx[np.isfinite(vals[idx])]
        if len(ok) > 1:
            vals[ok] = vals[rng.permutation(ok)]
    out[value_col] = vals
    return out


def deflated_sharpe(
    net: pd.Series,
    rf: pd.Series,
    window: tuple[str, str],
    trial_count: int = DSR_TRIALS,
    hac_lag: int = DSR_HAC_LAG,
) -> float | None:
    """Deflated-Sharpe probability of the daily excess return in ``window`` with
    :func:`open_composer.research.campaign_statistics.deflated_sharpe_probability` (77 trials by
    default)."""
    from open_composer.research.campaign_statistics import deflated_sharpe_probability

    a, b = window
    sub = net[(net.index >= a) & (net.index <= b)].dropna()
    ex = (sub - rf.reindex(sub.index).fillna(0.0)).to_numpy()
    try:
        return float(deflated_sharpe_probability(ex, trial_count=trial_count, hac_lag=hac_lag))
    except ValueError:
        return None
