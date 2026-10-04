# Hypotheses: h20261004_pm_earnings_beat_odds

Polymarket "Will X beat quarterly earnings?" prices and the stock's announcement-window return.

Written 2026-10-04 01:25 UTC by the interactive lead (Opus). The design below is frozen before any equity return conditional on the signal is computed. Fetching contract prices and mapping events to tickers and announcement times does not reveal returns and may run first. Nobody computes returns grouped by the signal until `candidate-manifest.json` is committed and `oc research iteration validate --stage pre-backtest` passes.

## Why this, why now

- **Owner, 2026-10-02 12:45 UTC:** iterate on Polymarket odds; build a model, strategy or factor.
- **Round 1** (`h20261002_pm_macro_uncertainty`) was inconclusive because 79 release days are too few. It is parked, with a forward shadow log running.
- **Round-2 intel:** `reports/research/intel/prediction-markets-round2-2026-10-04.md` (a75be10). Company-level earnings contracts are the only prediction-market source with hundreds of independent events per quarter: 1354 resolved from 2025-09 to 2026-10, about 450 per quarter. No registry row uses prediction-market prices for earnings.
- **Evidence (both secondary, unpublished, 2–6 month samples):**
  - Gómez-Cram, Guo, Jensen, Kung (SSRN 5933475): the contracts are more accurate than analysts and carry incremental information for announcement returns. Coefficients unread; SSRN returned 403.
  - Rabetti, Shao, Zhang (SSRN 6649938): 78.5% correct against a 75.9% beat base rate. This is weak discrimination.
- **Our test** is the first larger, partly post-publication check: events after 2026-03 come after both papers.
- **Mechanism:** contract traders aggregate information about the coming print (channel checks, alternative data, management tone). If the stock price does not fully reflect it, a higher P(beat) predicts a higher announcement-window return relative to other names reporting the same week.
- **Expected failure:**
  - the stock market already prices this information;
  - the contracts are thin (median volume $6.3k), so their prices are noise around a base rate;
  - returns depend on guidance and surprise size, not on the binary beat.

## Definitions (frozen)

- **Events:** resolved Polymarket earnings events, as listed in the intel snapshot `polymarket-earnings-events-closed-gamma-2026-10-04.json`, refreshed from Gamma at build time.
  - Rule: consensus non-GAAP EPS; strictly greater counts as Yes.
  - Ticker: from the title "(TICKER)", checked against the slug.
  - Kept if the ticker has SIP daily bars and the close on the signal day is at least $5.
- **Announcement time:** the 8-K item 2.02 `acceptance_utc` from `data/features/earnings_events/`, refreshed through the latest SIP date, within ±2 calendar days of the slug date. Treat it as US/Eastern wall-clock time; the T-03 finding applies.
  - Before 09:30 ET → pre-market: the reaction day R is that session.
  - At or after 16:00 ET → after close: R is the next session.
  - Between 09:30 and 16:00 ET → R is that session, but entry must be the previous close.
  - Events without a matching 8-K are excluded from the primary sample and counted. Secondary: the slug date plus the contract's end time as a timing proxy, reported only.
- **Signal day S:** the last NYSE session that closes before the announcement.
  - Pre-market or intraday announcement on day D: S = the session before D.
  - After-close announcement on D: S = D.
- **Signal P:** the last CLOB price of the Yes token at or before 15:00 ET on S, from `/prices-history` hourly, or finer fidelity in a window.
  - If the last print is more than 24 h old, mark the event stale and exclude it from the primary sample.
  - Also record P7, the last price at or before 15:00 ET seven calendar days earlier. Used for the stale placebo and for A3.
- **Window return:** close(R) / close(S) - 1 for the stock, minus the same for SPY. This is MOC entry on S and exit at the close of R.
  - Secondary: exit at the open of the session after R, reported only.
- **Liquidity (frozen):**
  - primary sample: contract volume at least $5,000;
  - secondary: all with a valid P.
- **Week:** the ISO week of R. Cross-sectional ranks are taken within the week, among primary events of that week.
  - Weeks with fewer than 6 events are pooled with the next week of the same reporting season.

## H-A (primary): the within-week rank of P predicts the window excess return

- **A1 signal:** the within-week percentile rank of P.
- **Primary statistic:** the mean of weekly Spearman ICs between A1 and the window excess return, over weeks with at least 6 events.
  - Its t uses the weekly IC series (number of weeks as the sample).
  - Also report a pooled IC with week-clustered standard errors.
- **Tercile spread:** each week, mean excess return of the top tercile minus the bottom tercile, equal weight. Net of 10 bp per side per leg, i.e. 40 bp round trip for a long-short pair. Stress: 20 bp per side.
- **Continue rule (all must hold):**
  1. mean weekly IC > 0 with t >= 2.0;
  2. net tercile spread per event-pair > 0;
  3. the real mean IC is above the 95th percentile of 1000 within-week shuffles (seed 20261004).
- **Stop rule:** mean weekly IC <= 0, or t < 1.0, means H-A is refuted for effects of the size we can detect. Write the minimum detectable effect next to the verdict.
- **Inconclusive** (between the two rules): forward shadow only, collected from the hourly collector's watchlist, then re-test after 450 new events under a new contract.

## Secondary (reported, no decision)

- **A3:** within-week rank of P - P7, the last week's change in odds. This is the same IC and spread test. Multiple testing: A1 is primary; A3 is reported with its raw p and a Holm adjustment over A1 and A3.
- **Calibration:** P against the realized beat, in deciles, plus the base rate in the sample. This checks that the contract data are real.
- **Positive control:** the realized outcome (beat = 1, miss = 0) against the window excess return. Expected large and positive. If its t is below 3, the return or timing pipeline is suspected broken: stop and report before any verdict.
- **Sub-periods:**
  - before 2026-03-01, which overlaps the papers;
  - from 2026-03-01, which is post-publication.
  - Also report the sector-adjusted return (stock minus its SPDR sector ETF) instead of SPY.

## Placebos

1. Within-week shuffle of P, 1000 times (gate 3 above).
2. Stale signal: P7 in place of P. No gate; this is evidence about timing.
3. Signal applied to the session after R (exit R+1 close, entry R close). It should not work.

## Costs, trading and scope

- Long the top tercile and short the bottom tercile, each event held one window. Shorts only on easy-to-borrow large caps, with 1% a year borrow pro rata.
- 10 bp per side primary, 20 bp per side stress. Announcement-day spread widening is covered by the stress.
- **Scored only if the continue rule passes:**
  - the event-level Sharpe of the weekly long-short series, annualized by active weeks per year;
  - the change in program Sharpe and max drawdown when the sleeve is added at 0.10x equity notional to the 2026-10-02 program allocation.
- No paper order. A pass leads to a forward shadow log first.

## Validator index

- Hypothesis: H-A above.
- Failure mode: "Expected failure" above.
- Measurement: primary statistic, tercile spread, the secondary items and placebos above.
- Stop/Pivot criterion: the continue, stop and inconclusive rules above.
