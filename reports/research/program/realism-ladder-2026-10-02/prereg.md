# T-20261002-25 preregistration: realism ladder for the total-return M0/M1 long-short

Written 2026-10-02 04:35 UTC, before any R1a-R6 number. The only number computed before this file is the R0
identity reproduction (`r0_identity.json`: max abs difference 0.0 against
`reports/research/program/regimes-2026-10-01/results.json`, all four windows; tolerance 1e-9).
Brief: `reports/research/control/briefs/T-20261002-25.md` (coordinator code R1002-0430-T25).
Nothing below is changed after a result is seen. Where the brief left a construction detail open,
it is fixed here.

## Question
Does a simple, implementable construction (rank-weighted, industry- and beta-neutral, weekly,
easy-to-borrow shorts, real spreads and borrow, book-level beta hedge, VIX crash control) keep most
of the signal-level gross Sharpe of the total-return composite (regime analysis: 1.68 in A, 3.06 in B)?
Decision: write a v1.2 simple-construction contract only if the mechanical rule below passes.

## Variants (4)
composite {M0, M1} x universe {U3000, P1000}: `M0_U3000, M0_P1000, M1_U3000, M1_P1000`.
Built as `AlphaSource` (scripts/run_book_v1_stage2.py): themes from
`alpha/book_v1/themes_<year>.parquet` (members: `in_u3000` / `in_p1000` at the decision date),
M0 equal theme weights, M1 weights from `FormationIC`/`formation_ic.parquet` re-set at the first
decision date of each calendar month of that offset, then `op.rank_normal` within the universe.
`AlphaSource` and `FormationIC` are used unchanged (calendar = `panel/_calendar.parquet`).

## Timing and returns (all rungs)
- Calendar: sessions of `panel/_calendar.parquet`; decision date D = close of D; first decision
  on or after 2017-10-02; last decision 2026-09-15 (needs a price at D+2; data end 2026-09-17).
- Return label t = decision-date label (as the regime analysis): r_t = F(t+2)/F(t+1) - 1 with
  F = open (R0, R1a, R1) or close (R2-R6). Weights decided at D act on labels D .. D+4
  (weekly) or D (daily, R1a). Positions drift between rebalances (fixed shares); equity is a
  constant USD 1,000,000 (no compounding), weights are fractions of equity.
- Weekly offsets: decision sessions with calendar position % 5 == o, o = 0..4; the offset blend
  is the equal-weight mean of the 5 daily series on dates where all 5 exist (scorecard_v2
  `blend_offsets`). R1a is daily (one series, no offsets).
- A name without a fill price at F(D+1) gets weight 0 (not renormalised); a later missing return
  counts as 0 (the position is held at the last price; no delisting return: same simplification
  as the regime analysis, stated in the report).

## Weights (R1a-R6)
Rank-normal score s over the universe (names with a finite score). Industry-demean s within
`ind_code` (signals/<year>.parquet, the risk-model industry used by R0); w = 2 s_dm / sum|s_dm|
(long 1, short 1, industry-neutral by construction). Note that for industry-neutral weights R0's
industry-demeaned return equals the plain return, so no demeaning of returns is needed.

## Rungs
- **R0** identity: regime-analysis M0 U3000 long-short (`year_returns`, `ls_returns`, `stats`),
  net = gross - 8 bp x sum|dw|; reproduces results.json to 1e-9 (done: 0.0).
- **R1a** (diagnostic bridge, not a trial of the decision rule, but counted in the trial count):
  daily rebalance with the weights above, open fills, per-stock beta_252_spy hedge as in R0,
  8 bp per side on sum|dw| (drifted weights -> new target).
- **R1**: R1a with weekly rebalancing, 5 offsets. Open fills, 8 bp per side.
- **R2**: R1 with close fills (F = close; costs still 8 bp per side).
- **R3**: R2 with shorts restricted to the ETB proxy set SE_t: short scores (s_dm < 0) outside
  SE_t get weight 0 and the short leg is rescaled to -1; long leg unchanged. SE_t = `borrow.short_eligible`
  rule v1 (adv_rank <= 2000, close >= 10, no reverse split in the past 252 sessions) with
  `detect_reverse_splits`; identity-checked against `op.ShortEligibility` on sample dates.
  Costs still 8 bp.
- **R4**: R3 with realistic costs: per rebalance, the cost function `make_cost_fn("close")`
  (spread from `cost_model_v1.json` at the close snapshot, square-root impact, 0.5 bp fees)
  on |trade| = |new weight - drifted weight| x USD 1,000,000, attributes (prior close, dollar_adv_21,
  vol_21) of the panel at D; missing inputs charged 40 bp as in the function; borrow 25 bp per year
  on the drifted short notional, accrued daily (/252). Impact is included (the function is called
  vectorised per rebalance, no approximation).
- **R5**: R4 with the book-level hedge: no per-stock hedge; at each rebalance SPY position
  h = -sum_i w_i beta_ewma_i with beta_ewma from `risk/exposures_<year>.parquet`
  (`RiskModel.predicted_beta` "ewma", the saved date <= D; missing -> 1.0), held in fixed shares to the
  next rebalance; the SPY trade is costed through the same cost function (ETF branch, 1 bp + fees).
- **R6**: R5 with the VIX crash control: if FRED VIXCLS at D (forward-filled <= 3 sessions) > 20.60
  every weight, including the SPY hedge, is multiplied by 0.5 at that rebalance (missing after the
  fill: no halving, counted and reported).

## Metrics
Per rung x variant x offset and for the offset blend, in windows A (2024-01-08..2026-06-30),
B (2026-07-01..end), stress (2017-10-02..2023-08-31) and recent (2024-01-08..data end, last label
2026-09-15): gross and net Sharpe (mean/std x sqrt(252), no risk-free subtracted), annualised return
and volatility, max drawdown (peak-to-trough of the cumulative sum), realised beta to SPY (daily OLS
with intercept, and `dimson_beta` from scripts/eval_book_v1_stage2.py; SPY return on the same F
basis), one-sided turnover (annual sum|dw| / 2, in multiples of equity) and cost in bp per year
(trade costs and borrow separately). R4-R6 also: `scorecard_v2.score_family` on the 4 variants of
the rung (n_trials = 4, bil = 0 because the long-short is self-financing, cost2x = gross - 2 x
(trade cost + borrow), phases and state from the regime analysis): DSR (N_eff over the four
variants), V4 on the stress window, recent-consistency z (check e value).

## Decision rule (mechanical)
**Proceed** to a v1.2 simple-construction contract only if, for at least one of the 4 variants,
all hold: (1) R6 recent-window net Sharpe of the offset blend >= 0.90; (2) R6 recent realised beta,
both OLS and Dimson, within +-0.15; (3) R6 V4 not triggered; (4) R6 recent-consistency z >= -2.
Otherwise **stop**: the book line pauses until new signals arrive.

## Trials
4 variants x 6 rungs (R1-R6) = 24 new trials, plus the R1a diagnostic = 28 series. Rungs are a
nested ladder of the same signal, not independent hypotheses; N_eff for DSR is computed over the
4 variants of the rung as above. The program-level running count is not kept in a ledger that
this task could find; this task adds 28.

## Limits written in advance
Sharpe over windows of 2-3 years has a standard error near 0.6 (A) and 1.4+ (B); the stress and
recent windows were seen by earlier tasks, so the result is a construction-realism measurement,
not out-of-sample evidence. Borrow is the 25 bp base rate (no hard-to-borrow fees); the ETB set
lacks the short-interest clause; no financing cost on the long leg; delisting returns are 0.
Costs use the fitted cost model, not realised paper fills.
