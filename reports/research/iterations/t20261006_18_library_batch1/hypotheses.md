# Hypotheses and preregistration: t20261006_18_library_batch1 (T-20261006-18)

Written by the T-20261006-18 executor on 2026-10-06T23:23:25Z (from `date -u`), before any return, IC or Sharpe of this
batch was computed. Frozen code: `scripts/t18_factors.py` sha256 `d4a04faaf7a6e08b02e324a92fa44bb8fcd3101381c388b19a63f7fe5e18c826`,
`scripts/t18_engine.py` sha256 `d51eb4757088ad882122c7c467c779b504ed5059935b8843d526c6c6d181bdc6`, `scripts/t18_extra_xbrl.py` sha256 `2cc49341fd79970c7b14c5a3a81769556a36dcef967994ff28777aa157d26331`,
`scripts/t18_lane.py` sha256 `888435091809dbc3785748cdb572c9b1692236be36179cf290dc32de8cad45aa`, `scripts/screen_batches/t20261006_18_library_lane.py` sha256
`c26b2787282a0f4e1b1dde9597d8a23def0e1f536f50f55374f08c0f11369e63`. Later changes are only bug fixes recorded in the report with their effect; nothing below is
edited after a result is seen. Sibling iteration for the eight ETF / calendar ids:
`t20261006_18_library_batch1_lane` (the lightweight path allows 24 candidates per iteration, so the 33 ids are
split 19 + 8, and 6 ids are data-insufficient and are not candidates).

## 1. Aim and owner rules applied

The 33 `book` / `lane` ids of `reports/research/strategy-library/first-batch.json` are run once under one contract.
The question is not whether a factor earns money alone but (a) whether adding it to the existing nine-theme stock
long/short book (v1.2, M0 composite) raises the recent net Sharpe at equal volatility, and (b) which factors or
rules deserve their own paper sleeve. Owner rules: Sharpe up, not sizing down (compare at equal volatility = compare
Sharpe); recent window decides (2024-01-08..2026-09-17), 2017-10..2023-08 is a crash diagnostic; cheap tests only
speed up, they do not refute (the label "unfounded" is used only inside the rule of section 5).

Decision rule for the whole batch (section 5) is mechanical and fixed now.

## 2. The 25 `book` ids: definition, data, deviations (audit against OSAP SignalDoc, snapshot 2026-10-06)

OSAP text: `reports/research/intel/sources/strategy-library-2026-10-06/osap_SignalDoc.csv`. Orientation = OSAP `Sign`
(higher oriented value = expected higher return). Accounting values: first-filed SEC XBRL facts, usable from the first
session after the filing (`usable_session`), no restated values. Extra concepts come from the local
`data/raw/sec_xbrl/companyfacts.zip` (downloaded 2026-10-05 by the existing builder; `scripts/t18_extra_xbrl.py`
re-parses it with the builder's own cleaning, no new download). Price items: `data/research/equity_book/prices`
(Alpaca adjusted closes), universe grid = the book's U3000 members.

| id | sign | status | definition used / missing item |
|---|---|---|---|
| ReturnSkew | -1 | ok | skewness of 21 daily returns, >=15 obs (OSAP: previous month) |
| ReturnSkew3F | -1 | insufficient | Fama-French daily factors mktrf/smb/hml (only monthly FF5 and industry files are local) |
| BetaTailRisk | +1 | ok | Kelly-Jiang tail beta; tailEX from all local stocks with prior close >= 5, monthly beta over up to 120 months, min 60 (local history starts 2016-02) |
| GrAdExp | -1 | ok | ln(adv_FY) - ln(adv_FY-1), both >= $0.1M, exclude lowest mcap decile |
| RDAbility | +1 | ok | mean slope of ln(sale growth) on ln(1+xrd/sale) lags 1..5 over 8 FYs, >=6 pairs, top tercile of xrd/sale, rd>0 |
| OrgCap | +1 | ok | 0.85*OrgCap + sga, init 4*sga, / assets; no GNP deflator, all fiscal year ends, history from 2009 (XBRL) |
| EarningsStreak | +1 | insufficient | IBES analyst consensus mean estimate and announcement dates (no analyst-estimate data local) |
| IntMom | +1 | ok | close[t-126]/close[t-252]-1 |
| InvGrowth | -1 | ok | FY inventory growth (no deflator: common factor in the cross-section), SIC 1-digit 4/6 and at/ppent<=0 dropped |
| Cash | +1 | ok | cash and short-term investments / total assets, latest quarter |
| PctAcc | -1 | ok | (ib - oancf)/|ib| annual, ib=0 -> 0.01; ib = income from continuing operations else net income |
| ChTax | +1 | ok | 4-quarter change in quarterly income tax expense / assets 4 quarters earlier |
| OPLeverage | +1 | ok | (sga + cogs)/assets, latest FY, sga missing -> 0 |
| ChEQ | -1 | ok | book equity / book equity 1y earlier - 1 (latest quarter vs same quarter a year before), both > 0 |
| roaq | +1 | ok | quarterly net income / total assets of the previous quarter |
| MomOffSeason06YrPlus | -1 | ok | mean monthly return of the non-same calendar months, lags 61..120 months; needs >=30 months; local history starts 2016-02 so valid only from about 2025 |
| MomOffSeason16YrPlus | -1 | insufficient | monthly returns 16-20 years back (need prices from 1996-2010; local history starts 2016) |
| MomSeason06YrPlus | +1 | ok | mean return of the same calendar month in years 6..10 back, >=3 of 5 years; valid from about 2025 |
| MomSeason11YrPlus | +1 | insufficient | monthly returns 11-15 years back (need prices from 2001-2015; local history starts 2016) |
| MomSeason16YrPlus | +1 | insufficient | monthly returns 16-20 years back (need prices from 1996-2010; local history starts 2016) |
| CompositeDebtIssuance | -1 | ok | ln(dltt+dlc) - ln(same 5 years earlier); LongTermDebtNoncurrent (fallback LongTermDebt) + current debt |
| BPEBM | -1 | ok | BP - EBM, dc and dvpa set to 0 (no XBRL equivalent), latest quarter balance sheet, mve = panel market cap |
| EBM | +1 | ok | enterprise book-to-market, dc and dvpa set to 0, latest quarter balance sheet, mve = panel market cap |
| ConvDebt | -1 | insufficient | Compustat dc (deferred charges) and cshrc (shares reserved for conversion); no comparable XBRL tag, a convertible-note tag would be a different signal |
| SUE | +1 | ok | book column sue_eps_raw (EPS seasonal-difference SUE, 8-quarter std); same definition as the book's earnings theme member, so overlap is expected |

Data-insufficient (not tested, not trials): ConvDebt (Compustat dc, cshrc), ReturnSkew3F (Fama-French daily
factors), EarningsStreak (IBES analyst consensus), MomSeason11YrPlus, MomSeason16YrPlus, MomOffSeason16YrPlus
(returns 11-20 years back; local prices start 2016). The two 6-10-year seasonality factors are computed with a
minimum of 3 of 5 same-month years and are therefore valid only from about 2025: they get a short-sample caveat and
cannot reach the full-depth label.

Common deviations from OSAP: no CRSP share-code / NYSE-breakpoint filters (universe = U3000 members with price >= 5,
already microcap-free), no GNP deflator (a common cross-sectional factor), Compustat items replaced by the XBRL tags
listed in `scripts/t18_extra_xbrl.py` (missing optional items count as 0 only where stated), calendar-month signals
are daily rolling windows evaluated on every session.

## 3. Construction (frozen)

All books are the strategy-level (k = 1) T-25 R6 / book v1.2 rules through `book_v12.tranche_target`: score ->
rank-normal -> industry-demeaned weights `w = 2 s_dm / sum|s_dm|` (long 1 / short 1) -> shorts only in the
easy-to-borrow proxy (rescaled) -> book-level EWMA SPY beta hedge -> VIX > 20.60 halves the book -> fill at the close
of t+1 -> fitted real costs (`make_cost_fn("close")`) -> 25 bp a year borrow. Series are daily net returns; Sharpe is
on the excess over BIL, 252 sessions.

**Tier 1, alone.** 19 factors x universe {U3000, P1000} x processing {raw = winsorise 1/99 + rank-normal, global
demeaning only; dm = additionally FF-industry demeaned (`process_signal`)} = 76 books, monthly, decision at the
last session of each month, 2017-10 start. Reported: rank IC (Spearman of the processed score against the
21-session forward return close(t+1) -> close(t+22)), plain and Newey-West (lag 2) t, share positive; net and gross
Sharpe, NW t of daily excess, vol, max drawdown, turnover; windows recent and diagnostic. Main spec of a factor
(frozen): U3000, `dm` for accounting factors and `raw` for price factors (mirrors the book's theme processing).
Placebo (gross, vectorised, no costs): 200 within-date permutations of the main-spec score, long-short rank-normal
weights on 21-session forward returns, monthly; reported as the share of placebo Sharpes below the real one.

**Tier 2, overlap.** Nine theme books and M0 (U3000, monthly, same construction, score = the stored theme score).
For each factor main spec: monthly gross block returns regressed on the nine theme books (OLS, intercept = alpha,
annualised, t), R-squared, correlation with each theme and with M0; windows recent (33 months) and full. Closest
theme = highest mean absolute cross-sectional Spearman correlation between the factor main-spec score and the theme
score at month-ends 2017-10..2023-08 (feature statistic, no returns; stored in `merge_map.json` before tier 3).

**Tier 3, added to the composite.** Base = v1.2 M0_U3000: mean of the nine theme scores (rank-normalised) in
the weekly 5-offset book. Variants: (add) composite = mean of the nine themes + (w/9) x f, f = the factor's U3000
processed score (dm for accounting, raw for price factors) rescaled to the average cross-sectional dispersion of
the nine themes, w in {0.5, 1, 2}; (merge) the factor processed score merged into its closest theme as one more
signal, `(n_j theme_j + f)/(n_j + 1)`. Then rank-normal and the same weights. Weekly decisions at positions with
`pos % 5 = offset`, offsets 0-4 (5 offsets blended with equal weights), start 2023-12-01 (burn-in, the book is rebuilt
at every decision), recent window 2024-01-08..2026-09-17. Identity check first: base rebuilt this way must equal the
saved R6 series `data/research/equity_book/realism_ladder/R6_M0_U3000_o*.parquet` to 1e-9 from 2024-01-08 (offsets 0
and 3). Delta = blended net Sharpe of the variant minus the base, same dates. Paired block bootstrap (21-session
blocks, 2000 draws) for P(Delta > 0) and a 90% interval. Crash diagnostic (2017-10..2023-08, same variants, weekly)
is run only for factors that meet the recent conditions of the "into the book" rule. Order of factor processing in
tier 3 = the order of `first-batch.json` ranks; factors not reached within the time budget are "not at depth".

## 4. Statistics, trials, power

Trials counted: tier 1 = 76; tier 3 = 19 x 4 = 76 plus the base; data-insufficient ids are not trials. DSR per series
= `scorecard_v2.dsr` with N_eff = 1 + (N - 1)(1 - mean pairwise daily correlation) over the family (tier-1 family
of 76 books, tier-3 family of 77 series) and var_SR = variance of the family's annual Sharpes; the family
trial count, not the single book, is used (standard v2.1 section 3). Program-level DSR (N from the book v1.2
programme record, 111 + this batch) is reported next to it. Power: for every tier-3 comparison the minimum detectable
Sharpe improvement at 80% power and 5% one-sided = 2.49 x SE(Delta), SE from the Memmel (2003) formula with the
realised correlation, written beside the result; 33 monthly points of the tier-1 books give the minimum detectable
Sharpe of a single book analogously. A result below the minimum detectable effect is reported as "within noise", not
as evidence of absence.

## 5. Fixed decision rules (mechanical)

* **Into the book** (all): Delta(w = 1) >= +0.10 and at least 2 of the 4 variants have Delta >= +0.10 and none has
  Delta <= -0.10; P(Delta(w = 1) > 0) >= 0.75; tier-1 main spec oriented IC mean > 0 and gross Sharpe > 0 in the
  recent window; max |correlation| of the factor book with any theme book < 0.8 (monthly, recent or full); average
  coverage of U3000 >= 50%; tier-1 gross placebo percentile >= 0.80; crash diagnostic Delta(w = 1) >= -0.10.
* **Own paper sleeve** (all; a P1-style proxy because robustness is not scored here): tier-1 main-spec family DSR
  >= 0.70; gross placebo percentile >= 0.90; recent IC NW t >= 2.0; 2x-cost recent excess return > 0; crash
  diagnostic of the tier-1 main spec without the veto of standard v2.1 section 2 (V4); tier-2 alpha t >= 1.0.
* **Unfounded in the recent window** (all): tier-1 recent net Sharpe <= 0 in both universes (main processing) and
  recent oriented IC <= 0 or NW t < 1 in both; Delta <= 0 at w = 0.5, 1, 2 and merge; tier 3 run in full. This label
  is a recent-window statement, not a refutation of the long-sample anomaly.
* **Not at depth**: everything else, including every factor whose tier 3 did not run.
* **Data-insufficient**: the six ids above.

## 6. Budget, stops

Compute only on this box under `flock /tmp/oc-heavy.lock ./scripts/run_capped.sh --mem 1.2G`; Modal is not planned
(spend $0; ceiling $4). Deadline 2026-10-10 22:00 UTC. Stop rules: a stage whose identity check fails stops the
batch; tier 3 stops at the deadline and unreached factors are "not at depth"; no result changes any rule above.

## 7. Failure modes

Fundamentals proxied from XBRL differ from Compustat; many factors overlap the value / quality / investment themes
(expected, measured by tier 2); published factors decay after publication (McLean-Pontiff 58%); 33 monthly points
are a low-power window; the two long-lag seasonality factors have under two years of valid values.

## 8. Hypothesis, failure mode, measurement, stop/pivot (validator headings)

* **Hypothesis**: at least one of the 19 factors, added to the v1.2 M0 composite as a tenth category, raises the recent
  five-offset blended net Sharpe at equal volatility by the margin of section 5 without a crash-diagnostic
  deterioration; factors with a standalone case qualify for their own paper sleeve under the section 5 rule.
* **Failure mode**: post-publication decay, XBRL proxies differing from Compustat items, overlap with the value /
  quality / investment themes, a 33-month window with low power, the short valid history of the 6-10-year seasonality
  factors.
* **Measurement**: Delta Sharpe of the blended net series versus the base (weights 0.5 / 1 / 2 and merge), paired
  block bootstrap, minimum detectable improvement, family DSR, within-date permutation placebo, tier-2 spanning
  regression, tier-1 IC and net Sharpe in both universes.
* **Stop/Pivot criterion**: section 6 (identity failure stops; deadline stops tier 3; unreached factors are labelled not
  at depth); no factor is labelled unfounded outside the section 5 rule; a factor that fails the book rule but meets
  the sleeve rule pivots to a paper sleeve proposal.
