"""Cross-sectional diagnostics on independently opened cohorts, without account compounding."""

from dataclasses import dataclass

import numpy as np
import polars as pl
from scipy.stats import rankdata

HORIZONS = (1, 5, 21, 63)


@dataclass
class Formation:
    ix: int
    session: object
    weekly: bool
    monthly: bool
    ids: np.ndarray
    returns: np.ndarray
    price: np.ndarray
    minute_capacity: np.ndarray
    half_spread: np.ndarray
    pool: np.ndarray


def groups(frame):
    from open_composer.research.equity_book.minute_screen import _spread_table, PARTICIPATION

    table = _spread_table()
    opening = np.array([[cell["half_spread_bp"][0] for cell in row] for row in table["rows"]])
    price = frame["raw_close"].to_numpy()
    adv = frame["median_dollar_volume_20"].to_numpy()
    spread = np.maximum(
        50 / price,
        opening[
            np.searchsorted(table["median_dollar_volume_20_edges"], adv, side="right"),
            np.searchsorted(table["printed_price_edges"], price, side="right"),
        ],
    )
    # Prior session's same-version 09:30 minute. Missing prints fund zero.
    cap = PARTICIPATION * frame["minute_dollars"].to_numpy()
    ids = frame["sid"].to_numpy()
    ret = frame.select([f"fwd_{h}" for h in HORIZONS]).to_numpy().astype("float64")
    dates = frame.select("ix", "session", "weekly", "monthly").unique(maintain_order=True)
    cuts = np.r_[0, np.flatnonzero(np.diff(frame["ix"].to_numpy())) + 1, len(ids)]
    result = []
    for (ix, session, weekly, monthly), lo, hi in zip(
        dates.iter_rows(), cuts[:-1], cuts[1:], strict=True
    ):
        s = slice(lo, hi)
        v = ret[s]
        n = np.isfinite(v).sum(axis=0)
        pool = np.nansum(v, axis=0) / np.where(n, n, np.nan)
        result.append(
            (
                s,
                Formation(
                    ix, session, weekly, monthly, ids[s], v, price[s], cap[s], spread[s], pool
                ),
            )
        )
    labels = frame.select("ix", *[f"fwd_{h}" for h in HORIZONS]).fill_nan(None)
    return result, labels


def turnover(old, ids, weights):
    # Absolute target changes in units of capital (overlap at constant marks).
    if old is None:
        return weights.sum()
    old_ids, old_weights = old
    _, left, right = np.intersect1d(old_ids, ids, return_indices=True, assume_unique=True)
    return (
        old_weights.sum() + weights.sum() - 2 * np.minimum(old_weights[left], weights[right]).sum()
    )


def cohort(r, weight):
    observed = np.isfinite(r)
    funded = weight.sum()
    if funded == 0 or not (weight[observed].sum() > 0):
        return np.nan
    return np.average(r[observed], weights=weight[observed]) * funded


def measure(scores, formations, tier, capital):
    """Positions depend solely on scores and information before the decision."""
    rows, prior, monthly_scores = [], {}, []
    small = tier == "small"
    dates, labels = formations
    calculations = [
        pl.corr("x", f"fwd_{h}", method=method).alias(f"{method}_{h}")
        for h in HORIZONS
        for method in ("pearson", "spearman")
    ]
    ics = (
        labels.with_columns(pl.Series("x", scores).fill_nan(None))
        .group_by("ix", maintain_order=True)
        .agg(calculations)
    )
    values = ics.drop("ix").to_numpy().reshape(len(ics), len(HORIZONS), 2)
    for (section, g), date_ic in zip(dates, values, strict=True):
        raw = scores[section]
        valid = np.isfinite(raw)
        x = raw[valid].astype("float64")
        ranks = rankdata(x)
        # Average tied ranks keep all members of a block together. A constant or
        # sparse signal can consequently have an empty leg; never split by ticker.
        hi = ranks > len(x) * 0.9 + 0.5
        lo = ranks < len(x) * 0.1 + 0.5
        good_ids = g.ids[valid]
        if g.monthly and tier == "liquid":
            monthly_scores.append(
                pl.DataFrame(
                    {
                        "ix": np.full(len(good_ids),g.ix,dtype=np.int64),
                        "sid": good_ids,
                        "score": (ranks / max(len(ranks), 1)).astype("float32"),
                    }
                )
            )
        positions = []
        for chosen in (hi, lo):
            if small and chosen is lo:
                chosen = np.zeros_like(lo)
            selected = np.flatnonzero(valid)[chosen]
            weight = np.full(len(selected), 1 / max(len(selected), 1))
            if small and len(selected):
                shares = np.floor(
                    np.minimum(capital * weight, g.minute_capacity[selected]) / g.price[selected]
                )
                weight = shares * g.price[selected] / capital
            positions.append((selected, weight))
        changes = {}
        for freq, active in (("weekly", g.weekly), ("monthly", g.monthly)):
            if active:
                changes[freq] = []
                for side, (sel, weight) in enumerate(positions):
                    ids = g.ids[sel]
                    changes[freq].append(turnover(prior.get((freq, side)), ids, weight))
                    prior[freq, side] = ids, weight
        for i, h in enumerate(HORIZONS):
            y = g.returns[valid, i]
            paired = np.isfinite(y)
            ic, ric = date_ic[i] if paired.sum() >= 3 else (np.nan, np.nan)
            (long, wl), (short, ws) = positions
            gross_l = cohort(g.returns[long, i], wl)
            gross_s = cohort(g.returns[short, i], ws)
            # Independent horizon cohorts: full entry and exit per side. The
            # liquidity proxy uses opening spread at entry for both transactions.
            spread_cost = (2e-4 * (wl @ g.half_spread[long])) if small else 0.0
            for freq, (tl, ts) in changes.items():
                row = dict(
                    session=g.session,
                    ix=g.ix,
                    year=g.session.year,
                    tier=tier,
                    frequency=freq,
                    horizon=h,
                    eligible=len(raw),
                    coverage=len(x) / len(raw),
                    pairs=int(paired.sum()),
                    long_label_coverage=np.isfinite(g.returns[long, i]).mean()
                    if len(long)
                    else np.nan,
                    ic=ic,
                    rank_ic=ric,
                    long_turnover=tl,
                    short_turnover=ts if not small else np.nan,
                    long_funded=wl.sum(),
                    pool=g.pool[i],
                    long_gross=gross_l,
                )
                for bp in (10, 20):
                    row[f"long_excess_{bp}"] = (
                        gross_l - 2e-4 * bp * wl.sum() - spread_cost - g.pool[i]
                    )
                    row[f"spread_{bp}"] = gross_l - gross_s - 2e-4 * bp * (wl.sum() + ws.sum())
                rows.append(row)
    return pl.DataFrame(rows).fill_nan(None), monthly_scores
