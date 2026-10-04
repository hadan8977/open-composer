# Hypotheses: h20261004_pm_midterm_odds_leadlag

Out-of-sample test of Goldstein, Li, Wang (2026-09-03), "Learning from Prediction Markets", on the 2026 US midterm control markets.

Written 2026-10-04 08:25 UTC by the interactive lead (Opus). Frozen before any return conditional on the signal is computed. Fetching market prices and asset bars does not reveal the result and may run first. Nobody computes strategy returns until `candidate-manifest.json` is committed and `oc research iteration validate --stage pre-backtest` passes.

## Why this, why now

- **Owner, 2026-10-02:** iterate on Polymarket odds.
- **Earlier rounds:**
  - Round 1 (`h20261002_pm_macro_uncertainty`) is parked, with a forward shadow log.
  - Round 2A (`h20261004_pm_earnings_beat_odds`) is refuted. The odds predict the beat (AUC 0.81), but stock prices had already absorbed them by 15:00 ET.
- **The claim under test** (intel `prediction-markets-round2-2026-10-04.md`; paper snapshot `wang-learning-from-prediction-markets.txt`, read in full by the lead for section 3.2):
  - On the 2024 election, the daily change in Polymarket's Trump-win probability predicts next-day returns of "Trump trades" (+13 bp per 1 pp, partly reversing on day 2).
  - Their strategy: 5-day EMA of the 4pm-to-4pm ΔP, then a 60-day rolling percentile, then a position in [-1, 1], lagged one day, times each asset's direction, averaged across assets.
  - Result: Sharpe 1.95, 2024-04-01 to 11-05, in-sample, before costs, with no replication.
- **This test:**
  - It is the cleanest out-of-sample check: same mechanism, same transformation, same assets and directions, a different election and a different period. The only new choice is the signal market.
  - The final month before 2026-11-03 should carry the largest odds swings, which is when the paper's effect was strongest. So a forward shadow runs now as well.
- **Mechanism:**
  - Retail traders learn from prediction-market prices with a lag. Informed flow persists for about 3 days, noise reverses within 2 days.
  - Republican control of Congress raises the odds of the Trump agenda, which is the same exposure as the paper's Trump-win probability.
- **Expected failure:**
  - midterm odds move far less and draw less attention than presidential odds;
  - the effect was specific to 2024;
  - the in-sample Sharpe was luck.

## Definitions (frozen)

- **Signal markets:**
  - Polymarket's 2026 House control market and Senate control market. Take the "Republicans" outcome probability: the Yes price of the Republican outcome, or 1 minus the Democratic price if only that exists.
  - Kalshi's equivalent control markets are a robustness check only.
  - If either Polymarket market does not exist or has fewer than 120 daily observations before 2026-10-02, the signal is the other one alone; this is recorded.
- **Daily probability:** the last CLOB trade or price at or before 16:00 ET on each NYSE session, from `/prices-history` hourly or finer.
- **ΔP:**
  - 4pm-to-4pm change, the mean of the House and Senate changes in percentage points.
  - A missing session carries the last price, so ΔP = 0.
  - If both markets are missing, the session is excluded.
- **Transformation, exactly the paper's:**
  1. EMA with span 5 of daily ΔP;
  2. its percentile rank within the preceding 60 sessions (the current value included);
  3. linear map to [-1, 1];
  4. lag one session.
  - The first 60 sessions of the signal are burn-in.
- **Assets:** the paper's Table 1 tickers that Alpaca can trade as US-listed stocks or ETFs, with SIP daily bars:
  - stock ETFs: SPY, QQQ, IWM, MAGS, DIA, XLF, KRE, XLI, XLE, XAR;
  - bonds: SHY, IEI, IEF, TLH, TLT, GOVT, TIP;
  - banks: GS, MS, JPM, C, BAC, WFC;
  - UUP;
  - connected: DJT, PHUN, TSLA.
  - Excluded: FX pairs, XAU, BTC and ETH. They are not tradable as stocks on Alpaca, and crypto has a separate cost contract.
  - An asset without bars for at least 80% of sessions is dropped and counted.
- **Directions:**
  - Use the paper's Internet Appendix Table A.1 verbatim if it can be found and read. Record the URL and snapshot.
  - Otherwise use this fallback, fixed now: stock ETFs +1, banks +1, connected +1, UUP +1, bonds -1. This follows the paper's stated rationale: deregulation and pro-growth policy; fiscal expansion means higher yields.
- **Strategy return:** the equal-weighted mean over assets of position(t) times close-to-close return(t). Executed as MOC at the close of t-1.
  - Costs: 2 bp per side per unit change in each asset's position (ETFs and large banks); 10 bp per side for DJT and PHUN.
- **Window:**
  - Backtest (out of sample for the paper): first session with a valid signal after burn-in, through 2026-10-02.
  - Forward: daily shadow log from 2026-10-05 through 2026-11-04, the session after the election.

## H-M (primary)

- **Statistics:**
  - net annualized Sharpe of the strategy over the backtest window;
  - Newey-West (5 lags) t of the mean daily net return;
  - the paper's predictive regression: the next-session direction-signed basket return on ΔP(t), with Driscoll-Kraay or Newey-West t.
- **Continue rule (backtest window, all must hold):**
  1. net Sharpe >= 0.5;
  2. NW t >= 2.0;
  3. the strategy's mean net return is above the 95th percentile of 1000 circular shifts of the signal series. Shifts are uniformly distributed between 20 and N-20 sessions, seed 20261004.
- **Stop rule:** net Sharpe <= 0 on the backtest window means refuted for the midterm setting. The forward shadow still runs to 11-04 because it is already preregistered here, but it cannot revive a refuted line on its own.
- **Inconclusive** (between the two rules): the final verdict uses the backtest plus the forward shadow (through 11-04) as one sample, with the same three rules, computed on 2026-11-05.
- **Power, stated before the run:** about 1.4 years of daily data after burn-in. With a true Sharpe of 1.0, the expected t is about 1.2; with the paper's 1.95, about 2.3. Only effects of the paper's size are detectable.

## Secondary (reported, no decision)

- Category strategies: stock ETFs, bonds, banks, connected. Same rules, reported separately.
- Day-2 reversal: the coefficient of the basket return at t+2 on ΔP(t).
- Same-day relation: the basket return on day t against ΔP(t), measured 4pm-to-4pm. Descriptive only, because it is not tradable.
- Kalshi signal in place of Polymarket.
- Gross Sharpe, and Sharpe with costs doubled.

## Placebos

1. Circular shifts (gate 3 above).
2. Sign flip: directions multiplied by -1. Expected to mirror the result, as a check of the code.
3. Signal from an unrelated, liquid Polymarket market over the same window (a sports or crypto market chosen by the executor from a fixed rule: the highest-volume non-political market with daily prices for at least 80% of the window), with the same transformation. Expected to fail.

## Out of scope

- Paper or real orders. A pass leads to a forward shadow, which already runs, and then a lead decision.
- Policy markets other than congressional control (tariffs, recession, shutdown). Mapping them to assets needs choices made after looking, so they are excluded here.

## Validator index

- Hypothesis: H-M above.
- Failure mode: "Expected failure" above.
- Measurement: the statistics, secondary items and placebos above.
- Stop/Pivot criterion: the continue, stop and inconclusive rules above.
