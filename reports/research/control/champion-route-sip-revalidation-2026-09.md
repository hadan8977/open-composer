# Champion Route Re-Evaluation on Clean SIP Data (2026-09)

Candidate: `nasdaq_tqqq_post_drawdown_reentry_router_delayed30_offensive_paper_auto_candidate`
Method: `scripts/evaluate_champion_route_sip.py` (P1b mechanism-eval harness, `open_composer.research.kernel.mechanism_eval`)
Full evidence: `champion-route-sip-revalidation-2026-09.json`
Gate contract: `config/promotion/kernel-paper-tier-gates.json` (git blob `28e4196ae7e6b5175b8c62eb0543d0eac0268ca6`)

## Why this run exists

`docs/finding-iex-cache-price-adjustment-defect-2026-09-01.zh.md` section 6.1 found this
candidate's 11-symbol universe (QQQ/TQQQ/QLD/SOXL/USD/SMH/SOXX/XLK/IGV/GLD/BIL) carried 20
phantom single-day price jumps over 30% in the retired IEX cache -- unadjusted leveraged-ETF
splits recorded as if they were real market moves. The spec's own `data_assumptions.adjusted`
field is `false`. Every piece of evidence this candidate's paper-auto activation case rests on
was built on that data. This run rebuilds the evidence on the full SIP daily archive
(`adjustment=all`, 2016-01-04 .. 2026-08-31) with the frozen route parameters and costs read
verbatim from the spec -- no search, no retuning.

## Verdict

**Not promotion-eligible.** 7 of 8 preregistered paper-tier gates pass; `qqq_capture_ratio`
fails at 0.506 against a `>= 1.0` requirement.

| Gate | Value | Threshold | Result |
|---|---:|---:|---|
| CAGR excess QQQ | +34.3pp | >= 5pp | pass |
| Sharpe excess BIL | 1.086 | > 1.0 | pass |
| DSR probability | 0.5006 | >= 0.50 | pass (by 0.06pp) |
| Max drawdown | -35.6% | >= -65% | pass |
| MAR | 1.36 | >= 0.60 | pass |
| Positive fold fraction | 4/5 (0.80) | >= 0.60 | pass |
| QQQ capture ratio | 0.506 | >= 1.0 | **fail** |
| QQQ downside capture | 0.985 | <= 1.0 | pass |

Window: 2022-01-03 .. 2026-08-28, 1168 sessions, 5 rolling-origin calendar-year folds,
`dsr_trial_count=32` (conservative stand-in -- see rationale in the script and JSON; this
route's real search history, 936 + 25 candidates, predates SIP migration with no clusterable
return artifact left).

## What "fails one gate" actually means here

`qqq_upside_capture = 0.499`, `qqq_downside_capture = 0.985`. The route captures essentially
all of QQQ's downside (0.985, barely better than just holding QQQ through the drop) while
capturing only half its upside. That is a materially worse risk/reward shape than "247% annualized
return" headlines suggest -- most of the outperformance is concentrated, not defensively earned.

## Post-selection collapse (the more urgent finding)

The 37 sessions since 2026-07-09 (when Step 7.R last certified this route's current-OOS numbers):

| | Route | QQQ |
|---|---:|---:|
| CAGR (annualized from 37 sessions -- noisy, read the sign not the precision) | -58.6% | +4.9% |
| Sharpe | -2.34 | -- |
| Max drawdown | -12.1% | -- |

The spec's recorded `current_oos_annualized_return_pct: 246.7` has not held up going forward.
Anyone reading this candidate's review cards as "the number that's currently working" should not.

## Side-by-side against the retired IEX-era baseline

Source: `reports/research/control/pdr-router-ml-gate-eval-20260703.json`,
`windows.full_window.baseline` (fixed route, no ML gate, 2013-01-08 .. 2026-05-20, 3342 sessions).

| Metric | IEX baseline (2013-2026) | SIP full window (2017-2026, 2427 sessions) |
|---|---:|---:|
| Sharpe | 1.014 | 1.033 |
| Max drawdown | -43.24% | -42.55% |
| Annualized return | 35.72% | 38.47% |

Crisis windows (Sharpe, IEX baseline vs SIP):

| Window | IEX baseline | SIP |
|---|---:|---:|
| q4_2018 | -3.22 | -3.10 |
| covid_crash | -3.96 | -1.33 |
| calendar_2022 | -0.45 | -0.78 |

The base route's shape survived the data correction with only small shifts in most windows --
unlike the ML-gate overlay evaluated in Step 7.R/7.T, where the identical IEX-to-SIP correction
produced large divergences (documented in `docs/finding-iex-cache-price-adjustment-defect-2026-09-01.zh.md`
section 6.1's own table). This is evidence the underlying deterministic route is not itself an
artifact of the price-adjustment defect, even though its supporting evidence file was built on
defective data.

## Disposition

- Not promotion-eligible on clean data. Genuine negative result, not a data-defect artifact.
- No retuning was attempted to clear the failing gate.
- This run does **not** change `strategy_specs/active/*.yaml` lifecycle or
  `scripts/run_daily_paper_cycle.py`'s default strategy. Whether the paper/live pipeline should
  keep pointing at a non-promotion-eligible candidate is a product decision, deferred to the
  goal-first conclusion document.
- Negative result logged in
  `reports/research/control/strategy-iteration-progress-2026-07-01.md` ("goal-first W3" section).
