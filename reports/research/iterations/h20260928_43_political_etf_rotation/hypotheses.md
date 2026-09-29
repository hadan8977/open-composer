# Hypotheses: h20260928_43_political_etf_rotation

Twenty-four candidates, two hypotheses (12 grid cells each), sharing the same
engine and falsification design: compute the candidate under
`run_h20260918_05_recent_menu.py:rotation_cell`'s unedited mechanism (top-N
cross-sectional momentum by lookback, absolute-momentum-vs-SHY filter,
monthly/weekly rebalance), then check K1/K2 against S3's frozen reference
numbers, judged on **select + anchor windows only** (the stress window
2016-05-02..2023-09-15 is not computed -- NANC/GOP have zero coverage of it,
see `data-feasibility.json`). No backtest is run under this dossier; the
screening lane consumes `candidate-manifest.json` and reports results back
into this iteration.

## H1 -- POLITICAL menu (NANC, GOP, MAGA, DEMZ) clears the select+anchor-only
K1 bar (or K2) on at least one grid cell, and is not dominated by the
PLACEBO_BIGTECH placebo

- Hypothesis: at least one of the 12 lookback/top_n/rebalance combinations on
  the political-trade-replica ETF menu reaches watch_recent or better
  (anchor-window date-neutral Sharpe >= 1.19, the K1 80%-of-S3 bar) with
  positive 20bp CAGR, because these 4 funds have each independently
  outperformed or roughly matched the S&P 500 since their own launch
  (NANC +88.49%, source: 24/7 Wall St), and cross-sectional rotation among a
  small menu of independently trending funds is the same mechanism family
  already live on S1-S3.
- Failure mode: the menu has only 4 members (small cross-section, less
  dispersion to rank than S1's 11 sectors or even h20260928_40's 5/8-member
  menus); GOP has underperformed the index since launch (24/7 Wall St); NANC's
  own outperformance is explicitly attributed by the source itself to
  mega-cap tech concentration rather than a genuine rotation-worthy signal,
  so a top-N rotation across these 4 funds may just be a noisy, thinly-traded
  way to hold tech beta, with the absolute-momentum-vs-SHY filter adding
  whipsaw cost rather than value. GOP/NANC only have lookback history from
  2023-02-07, so L252 candidates lose GOP/NANC from the rotation set for the
  first ~1 month of the anchor window (see data-feasibility.json), a further
  headwind against a clean K1 pass.
- Measurement: date-neutral Sharpe (median over offsets: 0-20 trading days
  monthly, 0-4 trading days weekly) in the select window 2023-09-18..
  2025-12-31 and the anchor window 2024-01-08..2026-09-17, at 10bp cost; CAGR
  at 20bp cost; DSR with n_trials=24 (full batch). For any candidate reaching
  watch_recent or better: 40bp-per-side wide-spread sensitivity (positive
  annualized return required) and the placebo-dominance check against the
  same-grid-cell PLACEBO_BIGTECH candidate's anchor Sharpe.
- Stop/Pivot criterion: if none of the 12 POLITICAL candidates clears K1/K2
  or reaches watch_recent, dir:congressional_political_trade_replica_etf_rotation
  is refuted for this scope. If a candidate reaches watch_recent+ but its
  same-grid-cell PLACEBO_BIGTECH counterpart's anchor Sharpe is equal or
  higher, the direction is downgraded to "not_kept (reproducible by plain
  big-tech momentum)" regardless of the K1/K2 numeric result -- fixed before
  any return is computed, per Eggers & Hainmueller 2013's negative evidence
  on the underlying congressional-edge story.

## H2 -- PLACEBO_BIGTECH menu (QQQ, XLK, SPY, DIA) reproduces (or exceeds) any
POLITICAL-menu edge under the identical mechanism

- Hypothesis: because 24/7 Wall St's own skeptical claim is that NANC's
  outperformance is "a byproduct of tech concentration... rather than any
  genuine informational edge," a menu of plain large-cap/tech ETFs run
  through the identical rotation_cell mechanism and grid should produce a
  comparable or higher Sharpe at the same grid cells, since QQQ/XLK carry
  more concentrated, more liquid tech-momentum exposure than a mixed
  4-fund political menu that also includes broader/defense-tilted funds
  (GOP, MAGA).
- Failure mode: QQQ/XLK/SPY/DIA are highly mutually correlated broad/sector
  benchmarks (much more than NANC/GOP/MAGA/DEMZ, which differ by donor-party
  composition and turnover), so cross-sectional top-N rotation among them may
  have too little dispersion to rank meaningfully, producing a lower Sharpe
  than just buying QQQ -- in which case a POLITICAL-menu edge, if any, would
  NOT be explained away by this placebo and the direction would need a
  different (not tech-concentration) explanation.
- Measurement: identical protocol to H1 (select+anchor windows, 10bp/20bp,
  DSR n_trials=24), reported for all 12 PLACEBO_BIGTECH candidates regardless
  of whether any POLITICAL candidate needs the comparison.
- Stop/Pivot criterion: this hypothesis is a diagnostic/disqualifier for H1,
  not an independent direction to keep or refute on its own -- its role is
  fully discharged by the H1 placebo-dominance rule above.

## Outcome (2026-09-29, after screen_batch run)

H1 refuted: 0/12 POLITICAL candidates reach even the anchor-only
watch_recent bar (best `POLITICAL_L252_N1_MO`, anchor Sharpe 0.9015 vs the
1.1882 bar; DSR 0.308). K2 fails everywhere (anchor edge -0.18 to -0.45).
H2's diagnostic role was not needed as a disqualifier (H1 never cleared the
bar to be disqualified), but is reported anyway: PLACEBO_BIGTECH's anchor
Sharpe is mixed against POLITICAL across the 12 grid cells (5 of 12 higher,
7 of 12 lower, including the best cell), so the failure is not simply
"reproducible by big-tech momentum" -- the rotation_cell mechanism itself
falls short of the bar on both menus. Full numbers:
`reports/research/iterations/h20260928_43_political_etf_rotation/results.json`.
