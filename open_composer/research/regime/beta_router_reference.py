"""F5: QQQ/TQQQ/QLD/BIL discrete beta-exposure-router reference (Step 12
Group B).

docs/plan-step-12-groupb-recent-regime-high-hit-rate-2026-09-09.zh.md
section 2, F5: "参考项（不参与晋级）...让用户看到'近期年化最高但回撤最大'
的对照，杠杆ETF不作为B组推荐". Re-hosts (does not reinvent) the already-
preregistered VOL02 rule
(``discrete_beta_ladder_to_volatility_target``, from
``scripts/evaluate_vol02_recalibrated.py``, tagged benchmark family
``beta_exposure_router`` in
``config/promotion/unlevered-family-paper-tier-gates.json``) verbatim in
rule and parameter values -- same trend/vol thresholds, same sleeve
selection logic, same weekly re-evaluation cadence -- just re-evaluated
here against Group B's own recent-regime metrics/disclosure instead of
Group A's rolling-origin promotion gates. This is a faithful reuse of an
already-committed, already-preregistered rule (chosen before this
evaluation existed, at Step 10), not a new rule picked after seeing Group
B's numbers. Only the cost-parameter plumbing differs (a plain keyword
here, Group B's own 10bp/25bp base/stress convention, instead of being
folded into a ``params["cost_bps"]`` key as the original script did for
its own 20bp/40bp convention).

Rule (verbatim thresholds from ``evaluate_vol02_recalibrated.SIGNAL_PARAMETERS``):
    trend_gap_200 = QQQ close / QQQ SMA200 - 1, lagged 1 session
    realized_vol_20 = 20-session annualized realized vol of QQQ returns, lagged 1
    Re-evaluated weekly (ISO calendar week boundary):
        trend_gap_200 <= 0      -> BIL  (risk-off)
        realized_vol_20 <= 12%  -> TQQQ (3x)
        realized_vol_20 <= 20%  -> QLD  (2x)
        otherwise               -> QQQ  (1x)

Leverage means this is never a Group B promotion candidate: F5 is not
scored against ``config/promotion/recent-regime-high-hit-rate-gates.json``'s
gates for a pass/fail verdict at all -- it is reported for side-by-side
comparison only, via ``reference_only=True`` when passed through
``open_composer.research.regime.gates.evaluate_regime_candidate``.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

import pandas as pd

SYMBOLS: tuple[str, ...] = ("QQQ", "TQQQ", "QLD", "BIL")
FALLBACK_SYMBOL = "BIL"
COST_BPS_PER_SIDE = 10.0
STRESS_COST_BPS_PER_SIDE = 25.0

#: Verbatim from scripts/evaluate_vol02_recalibrated.py's SIGNAL_PARAMETERS
#: (VOL02 / discrete_beta_ladder_to_volatility_target), preregistered
#: before this Group B evaluation existed -- see module docstring.
SIGNAL_PARAMETERS: dict[str, Any] = {
    "annualization_sessions": 252,
    "otherwise": "QQQ",
    "qld_when_annualized_vol_lte": 0.2,
    "risk_off_when_trend_gap_200_lte": 0.0,
    "tqqq_when_annualized_vol_lte": 0.12,
}


def _is_week_end(decision: pd.Timestamp, execution: pd.Timestamp) -> bool:
    return tuple(decision.isocalendar()[:2]) != tuple(execution.isocalendar()[:2])


def _select_sleeve(trend: float, annualized_vol: float, params: Mapping[str, Any]) -> str:
    if not math.isfinite(trend) or trend <= params["risk_off_when_trend_gap_200_lte"]:
        return "BIL"
    if annualized_vol <= params["tqqq_when_annualized_vol_lte"]:
        return "TQQQ"
    if annualized_vol <= params["qld_when_annualized_vol_lte"]:
        return "QLD"
    return str(params["otherwise"])


def simulate_beta_router(
    closes: Mapping[str, pd.Series],
    opens: Mapping[str, pd.Series],
    cost_bps_per_side: float,
    params: Mapping[str, Any] = SIGNAL_PARAMETERS,
) -> pd.Series:
    """Reimplements ``evaluate_vol02_recalibrated.simulate_vol02``'s rule
    (see module docstring) -- same trend/vol computation, same weekly
    switch logic, same "enter at execution's open, hold to execution's
    close when unchanged" convention.
    """
    common_index = closes["QQQ"].index
    for symbol in ("TQQQ", "QLD", "BIL"):
        common_index = common_index.intersection(closes[symbol].index)
    common_index = common_index.sort_values()

    qqq_close = closes["QQQ"].reindex(common_index)
    qqq_return = qqq_close.pct_change()
    trend_gap_200 = qqq_close / qqq_close.rolling(200, min_periods=200).mean() - 1.0
    realized_vol_20 = qqq_return.rolling(20, min_periods=20).std(ddof=1) * math.sqrt(
        params["annualization_sessions"]
    )
    # feature_lag_sessions=1, verbatim: the feature "as of" session T uses
    # only sessions strictly before T.
    trend_gap_200 = trend_gap_200.shift(1)
    realized_vol_20 = realized_vol_20.shift(1)

    sleeve_closes = {symbol: closes[symbol].reindex(common_index) for symbol in closes}
    sleeve_opens = {symbol: opens[symbol].reindex(common_index) for symbol in opens}

    dates = list(common_index)
    first_valid = max(trend_gap_200.first_valid_index(), realized_vol_20.first_valid_index())
    start_index = dates.index(first_valid) + 1

    current_sleeve = FALLBACK_SYMBOL
    returns: list[float] = []
    return_dates: list[pd.Timestamp] = []
    pending_switch_to: str | None = None
    cost_rate_per_switch = 2.0 * cost_bps_per_side / 10_000.0

    for i in range(start_index, len(dates) - 1):
        decision = dates[i]
        execution = dates[i + 1]
        if _is_week_end(decision, execution):
            trend = float(trend_gap_200.loc[decision])
            vol = float(realized_vol_20.loc[decision])
            if math.isfinite(trend) and math.isfinite(vol):
                pending_switch_to = _select_sleeve(trend, vol, params)

        target_sleeve = pending_switch_to if pending_switch_to is not None else current_sleeve
        switched = target_sleeve != current_sleeve
        if switched:
            # Enter at execution's open; hold to execution's close.
            day_return = float(
                sleeve_closes[target_sleeve].loc[execution]
                / sleeve_opens[target_sleeve].loc[execution]
                - 1.0
            )
            day_return -= cost_rate_per_switch
            current_sleeve = target_sleeve
        else:
            day_return = float(
                sleeve_closes[current_sleeve].loc[execution]
                / sleeve_closes[current_sleeve].loc[decision]
                - 1.0
            )
        returns.append(day_return)
        return_dates.append(execution)

    series = pd.Series(returns, index=pd.DatetimeIndex(return_dates), name="beta_router_reference")
    if series.isna().any():
        raise ValueError("beta router reconstructed return series contains non-finite values")
    return series
