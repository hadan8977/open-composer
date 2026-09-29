# Search Space: h20260929_12_hedged_factor_ensemble

One path, `hedged_factor_ensemble_screen`, 20 candidate cells (5 ensembles x 4
forms), within the 24-candidate lightweight-gate limit.

## Ensembles (static, select-window-only: 2016-06-01..2023-12-29)

- **E10 / E20 / E40**: top-K factors by |select-window 21d rank ICIR| from
  T-15's existing scan (`h20260928_15_claude_factor_batch/select-results.json`,
  271 candidates: 259 zoo + 12 batch), sign fixed from `sign_from_select`,
  equal-weight average of daily cross-sectional percentile ranks
  (`signal_card.composite_signal`, reused unmodified).
- **E20D**: greedy top-20 by |ICIR|, skipping a candidate whose select-window
  daily rank correlation (sign-adjusted, `signal_card.rank_corr`) with an
  already-chosen factor exceeds 0.70.
- **R40**: ridge regression on percentile-rank features of the top-40 by
  |ICIR|, alpha chosen by 5-fold blocked time-series CV with a 21-session
  purge on the select window, refit on the full select window at the chosen
  alpha, applied out of sample (fixed linear coefficients, no refitting after
  2023-12-29).

Nested composite zoo cards (`card_comp_c1`..`card_comp_c5`) are excluded from
the candidate pool: `signal_card.composite_signal` only accepts primitive
loadable components, not a composite-of-composites, and their sub-factors
(momentum, ROE, idio-vol, insider flag) already compete individually in the
same ranked pool -- including both would double-count them.

## Forms (per ensemble)

- **(a)** long-only top-50 equal-weight monthly book, no hedge.
- **(b)** (a) + long SH, weight beta/(1+beta) on SH and 1/(1+beta) on stocks;
  beta = trailing 63-session daily beta of (a)'s returns to SPY, capped
  [0, 1.5], recomputed from PAST returns at each monthly rebalance.
- **(bp)** same as (b) with PSQ/QQQ.
- **(c)** INFO ONLY: top-decile minus bottom-decile equal-weight spread,
  costs on both legs, borrow costs not modeled, no decision weight (short
  selling not an authorized execution path for this account).

## Cost / fill convention

Signal at month-end close (`tranche.shifted_signal_dates`, reused unmodified),
fill at next session's open, 10bp/20bp cost per side on turnover, rebalance
offsets {0,5,10,15} sessions after month-end (a documented reduction from the
lane's full 21, median reported).

## Judged benchmark family

`s3_incumbent` (vol-matched control via `combo.solve_k`/`combine_two_sleeves`,
reused unmodified) for the hedged forms' diversifier edge; SHY cash proxy and
the long-only form (a) as additional context; DSR with trial count = 20
(all candidate x form cells, including the info-only (c) row).
