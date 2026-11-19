"""Expanding, embargoed weekly ridge forecasts for relative ETF wealth."""

import numpy as np
import pandas as pd

from open_composer.lab.exposure_inputs import FEATURES, midnight
from open_composer.market_sessions import next_us_equity_session


def formations(state):
    # A dataset ending midweek must not manufacture an extra formation.
    dates = state.index
    following = pd.DatetimeIndex([next_us_equity_session(day.date()) for day in dates])
    weekly = dates.to_period("W-FRI") != following.to_period("W-FRI")
    visible = (
        state[["breadth_known_at", "cboe_known_at", "bar_known_at"]]
        .le(pd.Series(midnight(dates), index=dates), axis=0)
        .all(axis=1)
    )
    return state.loc[weekly & visible].dropna(subset=FEATURES)


def fit_models(state, closes, *, horizon, embargo, half_life, penalty, sealed_start):
    sample = formations(state).copy()
    dates = closes.index
    ratio = (closes.TQQQ / closes.BIL).to_numpy()
    pos = dates.get_indexer(sample.index)
    pos = pos[pos + 1 + horizon < len(dates)]
    paths = ratio[pos[:, None] + 1 + np.arange(horizon + 1)]
    sample = sample.loc[dates[pos]].assign(
        relative_log=np.log(paths[:, -1] / paths[:, 0]),
        relative_dd=(paths / np.maximum.accumulate(paths, axis=1)).min(axis=1) - 1,
        entry=dates[pos + 1],
        maturity=dates[pos + 1 + horizon],
        pos=pos,
    )
    fits = []
    for cutoff in [
        *(f"{y}-01-01" for y in range(2019, pd.Timestamp(sealed_start).year + 1)),
        sealed_start,
    ]:
        first = dates.searchsorted(pd.Timestamp(cutoff))
        train = sample.loc[sample.pos + 1 + horizon + embargo < first]
        weights = np.exp2(-(first - train.pos.to_numpy()) / half_life)
        weights /= weights.sum()
        for policy, features, outcome in [
            ("model", FEATURES, "relative_log"),
            ("price", FEATURES[:2], "relative_log"),
            ("drawdown", FEATURES, "relative_dd"),
        ]:
            x = train[features].to_numpy()
            y = train[outcome].to_numpy()
            center = weights @ x
            scale = np.sqrt(weights @ ((x - center) ** 2))
            z = (x - center) / scale
            intercept = weights @ y
            slopes = np.linalg.solve(
                (z.T * weights) @ z + penalty * np.eye(len(features)),
                (z.T * weights) @ (y - intercept),
            )
            fits.append(
                dict(
                    cutoff=cutoff,
                    policy=policy,
                    features=features,
                    n=len(y),
                    last_maturity=str(train.maturity.max().date()),
                    intercept=intercept,
                    center=center.tolist(),
                    scale=scale.tolist(),
                    slopes=slopes.tolist(),
                )
            )
    return fits, sample


def score(state, fits):
    weekly = formations(state)
    scored = weekly[["decision_at", *FEATURES]].copy()
    for fit in fits:
        rows = scored.index >= fit["cutoff"]
        z = (scored.loc[rows, fit["features"]] - fit["center"]) / fit["scale"]
        scored.loc[rows, fit["policy"]] = fit["intercept"] + z.to_numpy() @ fit["slopes"]
    return scored


def weekly_gate(index, series, hurdle):
    values = series.reindex(index)
    return values.where(values.gt(hurdle) | values.lt(-hurdle)).ffill().gt(hurdle)
