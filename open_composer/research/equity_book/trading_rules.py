"""Cost-aware trading rules of book v1.3 (``t20261004_book_v13_tc``, hypotheses.md section 3).

Pure functions, no data access.  One tranche refreshes at a decision date: ``x_old`` is the drifted
weight vector left by the previous block, ``w_tgt`` the R6 target
(``book_v12.tranche_target(...).w``), ``w_unit`` the same target before the VIX scale, ``s_t`` the
VIX scale now and ``s_prev`` the one used at this tranche's previous refresh.  ``eligible`` is a
dense bool vector of easy-to-borrow names.

Rules (parameters are frozen, nothing is searched):
``B0`` full rebalance (identity), ``P2`` / ``P3`` partial adjustment at rate 1/2 / 1/3,
``P2V`` partial adjustment of the unit book with the VIX scale applied at once,
``N25`` / ``N50`` no-trade band of 0.25 / 0.50 cross-sectional standard deviations of the target.
"""

from __future__ import annotations

import numpy as np

RULES = ("B0", "P2", "P3", "P2V", "N25", "N50")
RATES = {"P2": 0.5, "P3": 1.0 / 3.0}
P2V_RATE = 0.5
BANDS = {"N25": 0.25, "N50": 0.50}


def apply_rule(
    rule: str,
    x_old: np.ndarray,
    w_tgt: np.ndarray,
    w_unit: np.ndarray,
    s_t: float,
    s_prev: float,
    eligible: np.ndarray,
) -> np.ndarray:
    """New tranche weights after the rule.  Dense float arrays of one length; ``B0`` returns a copy
    of ``w_tgt``.  Non-members (``w_tgt == 0``) go to zero, names outside ``eligible`` are never
    short."""
    if rule not in RULES:
        raise ValueError(f"unknown rule {rule!r}")
    if rule == "B0":
        return np.array(w_tgt, dtype="float64", copy=True)
    x_old = np.asarray(x_old, dtype="float64")
    w_tgt = np.asarray(w_tgt, dtype="float64")
    members = w_tgt != 0
    x_new = np.zeros_like(w_tgt)
    if members.any():
        if rule in RATES:
            tau = RATES[rule]
            x_new[members] = x_old[members] + tau * (w_tgt[members] - x_old[members])
        elif rule == "P2V":
            u_old = x_old[members] / s_prev
            u_new = u_old + P2V_RATE * (np.asarray(w_unit, dtype="float64")[members] - u_old)
            x_new[members] = s_t * u_new
        else:
            delta = BANDS[rule] * float(np.std(w_tgt[members]))  # ddof 0, members only
            x_new[members] = np.clip(x_old[members], w_tgt[members] - delta, w_tgt[members] + delta)
    not_eligible = ~np.asarray(eligible, dtype=bool)
    x_new[not_eligible] = np.maximum(x_new[not_eligible], 0.0)
    return x_new
