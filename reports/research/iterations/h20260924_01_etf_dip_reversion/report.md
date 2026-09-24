# h20260924_01_etf_dip_reversion -- short-term index-ETF dip reversion (IBS, Connors/turtle RSI(2))

Card: `H-20260924-01` | direction: `dir:etf_dip_reversion_ibs_connors` | brief: `reports/research/hypotheses/H-20260924-01-etf-dip-reversion.md`
Gates: `oc research direction-check` = ok; `oc research iteration validate --stage pre-backtest` = ok (warning: `lightweight_single_mechanism_exemption_used`).
Preregistration: 24 cells frozen in `candidate-manifest.json` before any backtest (6 published rules x {QQQ, SPY} signal x {1x, 3x} execution).

**Verdict: partial.** Sleeve-level: **refuted** -- 0 of 24 candidates pass
G1-G5 at T0 (same-close, the unexecutable upper bound for T1) or T2
(next-open); since T0 already fails G1/G1' and G4 needs G1/G1' to hold at
higher stress cost, T1 cannot pass either, so Stage B was not run (decision,
not an omission -- see "Why Stage B was not run" below). Signal-level: **D1
(IBS-Algotradekit) shows a real, trade-level-significant effect at T0/T2**,
distinguishable from the other five rules on the placebo test and 2016-2026
persistence; its formal research-admission verdict stays **pending T1**,
since that test was preregistered specifically at the realistic T1 timing
and has not been run there.

## 1. Why Stage B (T1) was not run

T0 fills every trade at the same session's official close that T1's
market-on-close order also targets; T1 only replaces the *decision* inputs
(same-bar official close, EMA/SMA/RSI state) with a 15:50 ET minute-bar
proxy and a one-step-ahead indicator update. T1 cannot manufacture return
or reduce drawdown beyond what T0 already shows for the same fill -- it can
only add proxy-driven entry/exit-date noise on top of T0's numbers. Since
**0 of 24 candidates clear G1 (anchor CAGR>=50%, maxDD>=-35%) or G1'
(anchor Sharpe>=2.0, CAGR>=30%) at T0**, and G4 (the same test at 20bp
stress) can only pass where G1/G1' already passed at 10bp, no T1 cell can
pass `all_gates` regardless of what Stage B would show. Running Stage B
would have spent a memory-constrained `run_capped.sh` slot confirming an
already-unreachable bar. The 24 T1 rows in `trial-ledger.jsonl` are marked
explicitly: `{"timing": "T1", "status": "not_run", "reason": "dominated:
T0 upper bound fails G1/G1'"}` -- a recorded, reasoned non-execution, not a
silent gap.

## 2. Candidate table (T0, primary 10bp cost, anchor window 2024-01-08..2026-09-16, sorted by anchor Sharpe)

| cell | anchor CAGR | anchor DD | anchor Sharpe | select Sharpe | holdout Sharpe | G1 | G1' | G2 | G3 | G4 | G5 | placebo beat % (random-entry) | placebo beat % (calendar-shift) |
|---|---:|---:|---:|---:|---:|---|---|---|---|---|---|---:|---:|
| d4_spy_3x | 20.9% | -6.2% | 1.50 | 0.63 | 2.28 | N | N | Y | Y | N | Y | 0% | 10% |
| d1_spy_3x | **47.1%** | -30.6% | 1.42 | 1.72 | 0.83 | N | N | N | Y | N | Y | 0% | 0% |
| d1_spy_1x | 15.5% | -10.7% | 1.18 | 1.47 | 0.66 | N | N | N | Y | N | Y | 0% | 0% |
| d6_spy_3x | 12.8% | -6.2% | 1.02 | 0.17 | 1.95 | N | N | Y | N | N | Y | 5% | 20% |
| d1_qqq_3x | 36.0% | -27.0% | 0.88 | 1.18 | 0.14 | N | N | N | Y | N | Y | 0% | 0% |
| d1_qqq_1x | 13.5% | -9.6% | 0.71 | 0.98 | 0.04 | N | N | N | Y | N | Y | 0% | 0% |
| d4_spy_1x | 6.1% | -2.1% | 0.55 | -0.31 | 1.57 | N | N | Y | Y | N | Y | 0% | 10% |
| d4_qqq_3x | 12.7% | -17.1% | 0.52 | 0.04 | 1.32 | N | N | Y | N | N | Y | 12% | 30% |
| d2_qqq_3x | 17.5% | -22.1% | 0.51 | 0.37 | 0.70 | N | N | N | N | N | Y | 0% | 25% |
| d5_spy_3x | 9.5% | -6.2% | 0.50 | -0.06 | 0.60 | N | N | N | N | N | Y | 7% | 45% |
| d3_qqq_3x | 9.3% | -26.1% | 0.34 | -0.19 | 1.69 | N | N | Y | N | N | Y | 10% | 45% |
| d6_qqq_3x | 7.9% | -17.4% | 0.29 | -0.21 | 1.40 | N | N | Y | N | N | Y | 12% | 65% |
| d3_spy_3x | 3.7% | -21.2% | 0.04 | 0.27 | -0.61 | N | N | N | Y | N | Y | 5% | 5% |
| d4_qqq_1x | 4.0% | -6.0% | -0.01 | -0.63 | 0.98 | N | N | N | N | N | Y | 3% | 30% |
| d5_qqq_3x | 0.9% | -29.2% | -0.04 | -0.67 | 1.08 | N | N | Y | N | N | Y | 30% | 100% |
| d2_qqq_1x | 2.8% | -10.0% | -0.07 | -0.23 | -0.02 | N | N | N | Y | N | Y | 0% | 5% |
| d2_spy_3x | 0.8% | -27.6% | -0.07 | 0.04 | -0.66 | N | N | N | N | N | Y | 0% | 40% |
| d3_qqq_1x | 3.3% | -9.0% | -0.10 | -0.65 | 1.26 | N | N | Y | N | N | Y | 5% | 45% |
| d6_spy_1x | 3.8% | -2.1% | -0.15 | -0.90 | 1.04 | N | N | Y | N | N | Y | 0% | 20% |
| d6_qqq_1x | 2.6% | -6.1% | -0.29 | -0.95 | 1.03 | N | N | Y | N | N | Y | 2% | 55% |
| d5_spy_1x | 2.7% | -2.1% | -0.39 | -0.88 | -0.27 | N | N | N | N | N | Y | 0% | 40% |
| d5_qqq_1x | 0.6% | -10.2% | -0.45 | -1.08 | 0.62 | N | N | N | N | N | Y | 8% | 100% |
| d3_spy_1x | 1.2% | -7.3% | -0.55 | -0.40 | -1.02 | N | N | N | Y | N | Y | 0% | 0% |
| d2_spy_1x | -2.9% | -11.3% | -1.07 | -0.98 | -1.83 | N | N | N | N | N | Y | 0% | 30% |

**all_gates (G1-or-G1', G2, G3, G4 all true) = 0/24 at T0, 0/24 at T2, not
evaluated at T1 (see section 1).** Best anchor CAGR: d1_spy_3x at 47.1%,
short of the 50% G1 bar. Best anchor Sharpe: d4_spy_3x at 1.50, short of
the 2.0 G1' bar. G4 is N on every cell because G1/G1' are N on every cell
at 10bp already. Deflated Sharpe of the best T0 cell (d4_spy_3x, raw anchor
Sharpe 1.50) given 24 trials: **0.92** -- not a preregistered pass bar, but
context showing even the unexecutable upper bound's best cell does not
clear a strong bar once the 24-way search is priced in.

T2 (next-open) all_gates is also 0/24; T2 anchor Sharpes are directionally
similar to T0 for D1 (e.g. d1_spy_3x: 1.09 at T2 vs 1.42 at T0) and weaker
or sign-flipped for several D2-D6 cells (raw numbers in
`stage_a_summary.parquet`, columns prefixed `t2_`).

## 3. D1 research-admission diagnostics (T0/T2, not the preregistered T1 test)

Preregistered research admission (mean net return per trade > 0 in select
and holdout at 10bp; trade-level t>=2.0 over select+holdout; real
mean-per-trade >= the 95th percentile of a 60-seed random-entry-timing
placebo) was defined for the 12 1x cells **at T1 only**. Since Stage B was
not run, no cell has a real research-admission verdict. The table below is
a diagnostic re-application of the identical test definitions at T0 and T2
for D1's two 1x cells specifically, computed to characterize "a real
effect" for the partial verdict -- explicitly not a substitute for the T1
test itself.

| cell | timing | mean/trade select | mean/trade holdout | trade t-stat | placebo 95th pct | real vs pct | beats p95 |
|---|---|---:|---:|---:|---:|---:|---|
| d1_qqq_1x | T0 | +1.91% | +0.27% | 2.12 | +3.53% | 58.3th pct | N |
| d1_qqq_1x | T2 | +1.54% | -1.02% | 1.45 | +3.00% | 63.3th pct | N |
| d1_spy_1x | T0 | +2.13% | +0.96% | 2.99 | +2.05% | 91.7th pct | N |
| d1_spy_1x | T2 | +2.11% | +0.59% | 2.93 | +2.22% | 86.7th pct | N |

D1-SPY (1x) passes the mean-positive and t-stat legs at both T0 and T2 with
comfortable margin (t = 2.9-3.0), and its trade-level mean sits in the
high-80s/low-90s percentile of its own random-entry placebo distribution --
close to, but short of, the strict 95th-percentile bar. D1-QQQ (1x) is
weaker: its T2 holdout mean turns negative and its T2 t-stat (1.45) misses
the 2.0 bar. Neither cell would be admitted under the full rule even at the
more favorable diagnostic timing (T0); T1 -- the actually-preregistered
timing -- adds proxy-based entry/exit-date noise on top of this
already-marginal placebo-percentile leg. Raw numbers (all 4 D1 cells, both
timings): `d1-research-admission-t0-t2.json` in this directory.

## 4. T0 vs T2 sensitivity (T1 not run)

Only two of the three preregistered timings have real numbers this round.
Comparing them where D1 is concerned: anchor Sharpe drops modestly from T0
to T2 on the SPY legs (d1_spy_3x 1.42 -> 1.09; d1_spy_1x 1.18 -> 0.85,
computed from `stage_a_summary.parquet`'s `t2_anchor_sharpe` column) and
more sharply on the QQQ legs, consistent with T2's extra overnight-gap
exposure (T2 buys/sells at the next session's open, so it owns one more
gap than T0/T1's same-close fills). Since T1 sits closer to T0 than to T2
on execution mechanics (same close, only the decision inputs are proxied),
T0's numbers are the more informative diagnostic bound for what T1 would
show, and they still fail G1/G1' by a wide margin on every cell except
d1_spy_3x (close on CAGR, still short) and d4_spy_3x (close on Sharpe,
still short). No T1 row exists in this comparison; see section 1 for why.

## 5. 2016-2026 persistence table (daily T0, context only, not an admission criterion)

Mean annual return (% of the 11 years positive), by rule and symbol:

| rule | QQQ | SPY | DIA | IWM |
|---|---:|---:|---:|---:|
| D1 | 12.5% (91%) | 9.7% (82%) | 6.2% (82%) | 7.6% (82%) |
| D2 | 3.6% (64%) | -5.2% (0%) | -5.6% (9%) | -4.1% (27%) |
| D3 | 1.4% (64%) | 1.0% (82%) | 0.1% (55%) | 2.0% (64%) |
| D4 | 2.5% (73%) | 2.0% (73%) | 1.0% (64%) | 1.1% (36%) |
| D5 | 2.0% (64%) | 1.8% (73%) | 0.7% (64%) | -1.1% (45%) |
| D6 | 2.9% (82%) | 1.2% (55%) | 0.2% (55%) | -0.4% (36%) |

D1 is the only rule positive on all four symbols with a high (82-91%) share
of positive years, at a low 7-9 trades/year. D2 (the raw IBS<0.20 rule with
no trend filter) is negative on three of four symbols, including 0% of
years positive on SPY, at a much higher 36-41 trades/year -- consistent
with Pagonidis's own point that the raw IBS effect needs a trend filter or
selective application rather than blind use every time IBS is low. D3-D6
are economically marginal (1-3%/year, mixed 36-82% year-positive rates,
2.5-5.4 trades/year) -- too small and infrequent to place much weight on
either way at this sample size.

## 6. Split/dividend check

5 flags, all TQQQ/UPRO overnight open-vs-prior-close jumps of -20% to -31%,
all in March 2020 (2020-03-09, 03-12, 03-16 x2, 03-18). Reviewed: these
land exactly on the COVID-crash volatility spike and are explained by
ordinary (if extreme) daily moves in 3x-leveraged ETFs that week, not an
unadjusted split/dividend artifact. No adjustment issue found for
QQQ/SPY/TQQQ/UPRO over 2022-2026, the window this iteration's four windows
actually span. Full detail: `split-dividend-check.json`.

## 7. Caveats

- **T1, the only preregistered candidate timing, was never run.** Every
  number in this report is a T0 (unexecutable upper bound) or T2
  (next-open) diagnostic. The sleeve-level refutation follows from T0
  dominance logic (section 1), not from a directly-measured T1 failure.
- D1's "real effect" characterization rests on T0/T2 diagnostics computed
  specifically for this verdict, using the preregistered research-admission
  definitions but not at the preregistered timing; treat it as suggestive
  for prioritizing a future Stage B, not as a passed test.
- The 2016-2026 persistence table reuses each rule's SPY parameterization
  for IWM/DIA (D1's IBS thresholds and EMA window are only defined for
  QQQ/SPY in the published sources); disclosed via the
  `parameterization_source` field in `persistence-2016-2026.parquet`.
- Trade counts are modest for several cells (as low as 22 select-window
  trades for D1's 1x legs, down to single digits in the 9-month holdout
  window), so t-statistics and placebo percentiles for the smaller cells
  carry wide uncertainty even where computed.
- G3's "beats own placebo" test is a select-window-Sharpe comparison (the
  frozen giants-sweep G3 definition); the D1 research-admission table in
  section 3 uses a different, stricter test (trade-level mean-return
  percentile over select+holdout) -- the two are not the same statistic and
  should not be conflated when reading "D1 passes G3" alongside "D1 does
  not beat its placebo's 95th percentile."

## 8. `workflow_pass` / `research_pass` / `llm_contribution_pass` / `paper_ready_pass`

`workflow_pass` = **true** (dossier complete, pre-backtest gates passed,
Stage A ran clean, all artifacts produced, final validator blockers
resolved). `research_pass` = **false** for the sleeve (0/24 pass G1-G5);
D1's signal-level finding is real but not a passed research-admission test.
`llm_contribution_pass` = not applicable (no LLM/news/event/macro inputs in
this rule-based iteration). `paper_ready_pass` = **false** (no candidate
cleared gates; nothing here is proposed for paper trading).

## Files

- Dossier: `reports/research/iterations/h20260924_01_etf_dip_reversion/`
  (`direction-review.json`, `external-brief.json`/`.md`, `hypotheses.md`,
  `search-space.json`/`.md`, `candidate-manifest.json`, `cost-contract.json`,
  `data-feasibility.json`, `sources/`, `decision-record.md`, this file,
  `summary.json`)
- Engine: `scripts/run_h20260924_01_etf_dip_reversion.py`; tests:
  `tests/test_run_h20260924_01_etf_dip_reversion_script.py` (34 tests, all
  passing)
- Stage A raw output: `stage_a_summary.parquet`, `stage_a_placebo.parquet`,
  `trial-ledger.jsonl`, `persistence-2016-2026.parquet`,
  `split-dividend-check.json`, `stage_a.json`
- D1 diagnostic: `d1-research-admission-t0-t2.json`
- H-card: `reports/research/hypotheses/H-20260924-01-etf-dip-reversion.md`
- Source cards: `reports/harness/source_cards/h20260924_01_etf_dip_reversion.jsonl`
