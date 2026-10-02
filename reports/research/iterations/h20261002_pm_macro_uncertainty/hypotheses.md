# Hypotheses: h20261002_pm_macro_uncertainty

Prediction-market (Kalshi) implied uncertainty about scheduled US macro releases, and the equity announcement premium.

Written 2026-10-02 13:08 UTC by the interactive lead (Opus). The design below is frozen before any return conditional on the signal is computed. Building the prediction-market distributions does not reveal outcomes and may run first. Nobody computes equity returns grouped by the signal until `candidate-manifest.json` is committed and `oc research iteration validate --stage pre-backtest` passes.

## Why this, why now

- **Owner request, 2026-10-02 12:45 UTC:** use real-time Polymarket odds on related events to build a model, strategy or factor, and keep iterating.
- **Existing registry row:** `dir:prediction_market_crypto_as_equity_signal` is `evidence_too_weak` (2026-09-23). It covers odds as a generic lead-lag signal for stock or sector returns. Reopen bar: a specific mechanism backed by credible research.
- **What is new since then:**
  1. **FEDS 2026-010 / NBER w34702** (Diercks, Katz, Wright, Feb 2026). Kalshi's implied distributions for FOMC decisions, CPI, payrolls, unemployment and GDP are well-behaved and react to news. Their variance falls sharply after data releases. The Kalshi mode matched every FOMC decision on the day before since 2022, which beats fed funds futures. Kalshi beat the Bloomberg consensus on headline CPI with statistical significance.
  2. **Announcement-premium literature.** Ai et al. (NBER w31923): FOMC, CPI and payrolls carry the largest abnormal equity premia, which rose sharply between June 2022 and June 2023, and realized variance predicts announcement-day returns. Hu, Pan, Wang, Zhu (JFE 2022): pre-announcement returns compensate for heightened uncertainty and its resolution.
  3. **Data.** The Kalshi public API needs no key. Candlesticks reach back to 2021, routed between the live and historical endpoints via `/historical/cutoff`. The MIT-licensed replication code `WillBtK/macro_kalshi` turns threshold markets into distributions. The full Polymarket on-chain archive (HuggingFace `TimeSeventeen/Polymarket-v1`, CC BY-SA 4.0, 2022-11..2026-04) is available for later steps.
- **Mechanism, which is not lead-lag:**
  - Equity markets pay a premium for bearing announcement risk. That premium should scale with how uncertain the release is.
  - Prediction markets give a direct, release-specific, point-in-time measure of that uncertainty: the standard deviation of the implied distribution the afternoon before.
  - No other free source gives this for payrolls, unemployment or GDP. VIX is a 30-day, all-news measure.
- **Already refuted:** the plain pre-FOMC drift (`dir:pre_fomc_announcement_drift`, H-20260928-05: SPY anchor Sharpe -0.84, TQQQ 0.31). FOMC events are therefore reported separately and are not part of the primary statistic.

## Definitions (frozen)

- **Events:** scheduled release days T of:
  - CPI (Kalshi `KXCPI`, earlier tickers `CPI-*`; headline MoM);
  - payrolls (`KXPAYROLLS`, earlier `PROLLS-*`);
  - GDP advance (`KXGDP`, earlier `GDP-*`);
  - PCE (`KXPCE`, earlier tickers if any, only if the series exists);
  - FOMC decision days (`KXFED`, earlier `FED-*`), reported separately.
  - T is the US Eastern date of the release; data releases come out at 08:30 ET, and the market close_time is 08:25 ET.
  - If two releases share a day, that day's signal is the larger of their U_rel.
- **Signal time:** the last hourly candle whose period ends at or before 15:00 ET on T-1, the previous US equity session. This is known before the 15:50 ET MOC cutoff.
- **Implied distribution:**
  - Threshold markets give P(X > k). Use the yes mid (bid+ask)/2 when both sides exist and the spread is at most 0.10; otherwise use the last trade price in that candle; otherwise the strike is missing.
  - Clean with the macro_kalshi "middle-out" monotone method (anchored at the median strike, monotone outward), then difference into a probability mass function on bin midpoints.
  - U = the standard deviation of that mass function, in the release's own units.
- **U_rel** = U / median(U over the previous 12 events of the same series).
  - Events with fewer than 6 prior events in their series are warm-up: they are reported but excluded from tests.
  - Events with fewer than 4 usable strikes at signal time are excluded and counted.
- **Returns** come from SIP daily bars:
  - R_cc = close(T) / close(T-1) - 1, the primary;
  - R_co = open(T) / close(T-1) - 1, which captures the 08:30 reaction with a MOO exit.
  - Both are measured in excess of BIL over the same interval.
  - Tickers: QQQ (primary), SPY, IWM, TLT; TQQQ for the levered variant.
- **Samples:**
  - full = first event with a valid U_rel .. 2026-09-17;
  - anchor = 2024-01-08 .. 2026-09-17.
  - There is no stress window: Kalshi data start in 2021.

## H0 (descriptive, no gate)

Mean announcement-day R_cc for QQQ, SPY, IWM and TLT versus all other sessions, per series and pooled, with Welch t values. This is context for H1 only and decides nothing.

## H1 (primary): uncertainty scales the announcement premium

- **Hypothesis:** on non-FOMC release days, QQQ R_cc is higher when U_rel > 1 than when U_rel <= 1.
- **Primary statistic:** D = mean(R_cc | U_rel > 1) - mean(R_cc | U_rel <= 1), over non-FOMC release days in the full sample. Its permutation p-value comes from 1000 shuffles of U_rel across events within each series, seed 20261002.
- **Secondary statistics:**
  - the same D for SPY and IWM;
  - the slope b in R_cc = a + b * log(U_rel), with HC1 t;
  - D in the anchor sample;
  - D using R_co;
  - FOMC days on their own.
- **Failure modes:**
  - The announcement premium is absent in 2021-2026.
  - Prediction-market variance is dominated by stale tail strikes, i.e. measuring illiquidity rather than uncertainty.
  - The premium exists but does not scale with U.
  - A few CPI days in 2022 drive the result. Report D without 2022, and the leave-one-year-out range.
- **Continue rule** (all three must hold):
  1. D >= +15 bp;
  2. permutation p <= 0.10 in the full sample;
  3. D > 0 in the anchor sample.
- **Stop rule:** D < +5 bp or wrong-signed in the full sample means H1 is refuted and the candidates below are not scored for adoption. They are still reported, flagged `not_decision_eligible`.

## H2 (conditional on data): expectation gap

- **Hypothesis:** sign(Kalshi implied mean - consensus) at the last pre-release snapshot predicts the sign of the release reaction. A hotter-than-consensus Kalshi forecast predicts lower TLT and QQQ R_co. The basis is FEDS 2026-010's finding that Kalshi beats the consensus on headline CPI.
- **Runs only if** a free consensus history passes the feasibility check below.
  - It must be recorded before each release. Free candidates to probe: Trading Economics guest API, FXStreet calendar data, and the Cleveland Fed inflation nowcast history as a consensus proxy for CPI.
  - The data must be usable within the source's terms. Record the terms in `data-feasibility.json`.
  - Otherwise H2 is `blocked_data` and nothing is run.
- **Continue rule:**
  - CPI and payrolls pooled, events with |gap| at or above the median |gap|;
  - hit rate of sign(gap) against sign(-TLT R_co) >= 0.60;
  - binomial p <= 0.10;
  - the same direction in the anchor sample.

## Candidates (tradable rules, all preregistered; DSR counts all of them)

| id | rule | asset | fill |
|---|---|---|---|
| U1 | long when U_rel > 1, non-FOMC days | QQQ | MOC T-1 -> MOC T |
| U2 | same as U1 | SPY | same |
| U3 | same as U1 | IWM | same |
| U4 | long every non-FOMC release day (unconditional baseline for U1) | QQQ | same |
| U5 | same as U1 | TQQQ | same |
| U6 | weight min(U_rel, 2) / 2, non-FOMC days | QQQ | same |
| U7 | same as U1, FOMC days included | QQQ | same |
| G1 | H2 only: short TLT if gap > 0, long TLT if gap < 0, CPI and payrolls | TLT | MOC T-1 -> MOO T |
| G2 | H2 only: the same sign rule | QQQ | MOC T-1 -> MOO T |

- **Costs per side:**
  - primary: QQQ, SPY and TLT 2 bp; IWM 3 bp; TQQQ 5 bp;
  - stress: double those.
  - TLT shorts add a borrow cost of 0.5%/yr, pro rata (easy to borrow).
- **Scoring, only if the H1 continue rule passes:**
  - These rules are invested on about 6-10% of sessions, so they are judged as a program overlay, not as a standalone sleeve.
  - For each candidate, report:
    - mean and t per event;
    - hit rate;
    - annualized return on the days invested;
    - DSR across all 9 candidates;
    - the change in program Sharpe and max drawdown when the rule is added on top of the 2026-10-02 program allocation (iteration `h20261002_program_dd30_allocation`) at 0.25x equity notional, and at 0.5x when it fits under Reg T.

## Placebos

1. Shuffle U_rel across events within each series, 1000 times. The real D must lie above the 90th percentile.
2. Use the same signal on the session after the release (T+1). This should not work.
3. Random non-release sessions matched by weekday and month, with U_rel drawn from the empirical distribution. This should show no D.

## Out of scope for this iteration

- Polymarket event markets beyond macro releases (tariffs, geopolitics, elections), and lead-lag on equities. The registry row stays `evidence_too_weak` for those.
- Trading on prediction markets themselves.
- Any paper order. A pass leads to a forward shadow log first; the forward collector below supplies the data.

## Forward data (independent of the result)

An hourly point-in-time collector stores snapshots of:

- open Kalshi macro events;
- a short curated Polymarket list: Fed decisions, recession, CPI, tariffs and shutdown.

They go to append-only parquet with `fetched_at_utc`. The lead installs the cron after review. A forward record starts now whatever the backtest says.

## Validator index (added by T-20261002-44; no rule, number or threshold above is changed)

The iteration validator looks for these four markers literally. Each line points at the existing frozen text above.

- Hypothesis: H1 (uncertainty scales the announcement premium) and H2 (expectation gap), stated above.
- Failure mode: the "Failure modes" bullets under H1 above.
- Measurement: the "Primary statistic" and "Secondary statistics" bullets under H1, the H0 table, the H2 continue-rule inputs, the three placebos and the per-candidate statistics above.
- Stop/Pivot criterion: the "Continue rule" and "Stop rule" under H1, the "Continue rule" under H2 and the placebo thresholds above.

## Outcome (appended after the run; preregistration above unchanged)

- H1: not supported, not refuted. D = +13.93 bp, permutation p 0.413, anchor D +26.12 bp: the continue rule fails on the first two conditions and the stop rule is not triggered (D above +5 bp). See `report.md`.
- H2 (CPI days only, Cleveland Fed nowcast as the consensus proxy): not supported; hit rate 0.55 (bar 0.60), binomial p 0.41 (bar 0.10).
