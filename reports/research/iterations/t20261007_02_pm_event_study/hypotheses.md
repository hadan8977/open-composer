# Hypotheses: t20261007_02_pm_event_study (task T-20261007-02)

Frozen before any ETF return is read. Odds-side data (event lists, odds paths) were downloaded before this file was finalised; no ETF return was
computed for any event. Rules live in `scripts/t0702_pm_grid.py` (sha256 recorded in `candidate-manifest.json`) and are quoted here.

## Question
Do changes in prediction-market odds carry tradable information about US ETF returns over the next minutes to hours, net of costs, in 2024-01-08..2026-10-06?
Owner mandate: test hundreds of events at once, anything worth testing must reach paper within two weeks (owner 2026-10-06 evening, 2026-10-02, 2026-10-07).

## What is different from the three earlier tests
- h20261002_pm_macro_uncertainty: daily close-to-close, one question (uncertainty U vs announcement-day return), 79 days, Kalshi only. Verdict "not supported, not refuted" (D 13.9 bp, p 0.41).
- h20261004_pm_earnings_beat_odds: stock cross-section, earnings windows, Polymarket earnings markets. Refuted at depth (IC 0.019, t 0.43).
- h20261004_pm_midterm_odds_leadlag: daily, one signal (House/Senate control, Goldstein-Li-Wang transform), 27 assets. Refuted (Sharpe -1.2).
- This task: minute-level ETF returns (5 to 240 minutes) after (R) scheduled macro releases, direction taken from the pre-release odds, and (J) one-hour odds jumps in policy, Fed, shutdown, recession and election markets, with the direction mapping fixed by theme before looking at returns. New: intraday horizon, release-time entry, jump episodes, up to ten Kalshi release classes, 179 Polymarket markets, a positive control that uses the realised surprise.

## Part R: scheduled releases (Kalshi hourly candles, local from T-20261002-44; new series fetched the same way)
- Classes: CPI, NFP, GDP, FOMC (core four) plus CLAIMS (weekly jobless claims), PCE (core), ISM_MFG, ISM_SVC, ADP, JOLTS. A class enters the pooled set only if it has >= 20 valid events (>= 3 usable strikes, median candle age <= 48 h) with release >= 2024-01-08. Release times ET: 08:30 (CPI, NFP, GDP, CLAIMS, PCE), 08:15 ADP, 10:00 (ISM, JOLTS), 14:00 FOMC; release day = ET date of the Kalshi market close.
- Implied expectation E(t): the volume-free bin-midpoint mean of the cleaned strike curve of the event (functions of `scripts/build_kalshi_release_uncertainty.py`, middle-out monotone cleaning), from candles that ended at or before t.
- Pre-release clock: T_pre = last full UTC hour boundary at or before T-5 minutes. R1 = E(T_pre) - E(T_pre - 24 h). R2 = E(T_pre) - previous settled value of the same series. Both use only data visible before T.
- Direction: s = hawkish sign of the class (table in the grid file; CLAIMS is -1). Hawkish iff s x sign(signal) > 0. Position at T: short TLT if hawkish, long TLT otherwise. Trade only if |signal| >= the expanding median of |signal| over earlier valid events of the same class (first 6 events of a class are warm-up and not traded). Entry at the open of the 1-minute bar stamped T (decision on the close of bar T-1), exit at the open of bar T+h, h in {5, 30, 120}. 1x notional, no leverage.
- Main grid R: 2 signals x 3 horizons = 6 variants, pooled over qualifying classes, asset TLT. Report only (not in the grid, Holm over the report-only family): per class, and with SPY, QQQ, IWM as the traded asset (short on hawkish for classes with s=+1 as for TLT).
- Positive control (not tradable): the realised surprise sign(actual - E(T_pre)) x s predicts the TLT return over [T, T+30] with the same sign convention. Control passes if the pooled event t (SE clustered by date) is >= 2. If it fails, R cannot be refuted at this resolution and is called "not at depth" whatever the grid says.

## Part J: Polymarket odds jumps (public Gamma and CLOB APIs, hourly YES prices)
- Universe: events from the tags tariffs, trade-war, fed, fed-rates, economy, economic-policy, macro-indicators, inflation, jobs-report, recession, government-shutdown, debt-ceiling, house, senate, us-politics, trump-presidency, politics, trump, elections (tag geopolitics excluded: no mapping). Market volume >= 300,000 USD, theme regex match (table in the grid file), alive after 2024-01-01, at most 700 markets by volume (179 qualified).
- Themes and the economic sign of a rise in the YES price, with one primary ETF each: tariff escalation (-1, SPY), tariff de-escalation or trade deal (+1, SPY), Fed cut (+1, TLT), Fed hike (-1, TLT), recession (-1, SPY), government shutdown (-1, SPY), Republican or Trump control/win in national election markets (+1, IWM), Democratic (-1, IWM).
- Jump: two consecutive hourly price points 50-75 minutes apart with |dP| >= theta, theta in {3, 5, 8} percentage points; both prices within [0.02, 0.98]; market not within 24 h of its end date; decision time (the later point, floored to the minute) on a weekday between 08:00 and 19:30 ET. Jumps outside those hours are counted as untradable and reported.
- Episode: per theme, jumps within 4 hours collapse into the one with the largest |dP|. One position per ETF at a time: a jump that arrives while an earlier trade in the same ETF is open is skipped.
- Trade: direction d = sign(dP) x theme sign on the primary ETF ("continue"), or -d ("reverse"). Fill at the open of the bar after the decision bar close, exit at the open of the bar h minutes later, h in {15, 60, 240}, capped at the 19:55 ET bar. 1x notional.
- Main grid J: 3 thetas x 3 horizons x 2 modes = 18 variants. Report only: per theme, other ETFs (QQQ, IWM, XL sectors), 12-hour-lagged placebo odds.

## Costs and execution
- Signal on the close of minute t, fill at the open of t+1 (R: fill at the open of the release minute, decision on the close of the minute before). Costs per side reuse T-20261006-15: half spread = 0.5 x tick cents / price (1 cent for SPY QQQ IWM TLT XLF XLE XLK XLV XLY XLP XLI XLU, 2 cents for XLB XLRE XLC) + 0.02 bp, sells + 0.206 bp, fills before 09:45 ET + 1 bp. Extension for this task (unmeasured priors, stress covers them): fills before 09:30 ET or at/after 15:55 ET add 3 bp (SPY QQQ IWM TLT) or 6 bp (sector SPDRs). Reported at x1 and x2 (x2 = V3 veto test).
- Sector SPDR minute bars are sparse in extended hours: a trade needs a bar within 2 minutes of the fill and exit minute, otherwise it is skipped and counted.

## Evaluation (evaluation-standard v2.1, section 5b)
- Daily net series: sum of trade returns per ET date, zero on other sessions, 2024-01-08 to the last data day; annualised Sharpe on all sessions (sqrt 252). Same series feeds PSR/DSR (N = 24 trades variants; N_eff from the mean pairwise correlation of the 24 daily series; skew and kurtosis corrected), Newey-West t, phase and last-63-session z.
- Placebo (5b.2, timing): same entry times, horizon, size and cost, direction random per trade, 100 seeds, gross and net. Report the percentile of the real net and gross Sharpe.
- Spec rule (5b.6): within each part (R, J), take the three variants with the highest recent net Sharpe and use the median one. Variants outside the main grid never take part in selection.
- Robustness a, b, c, e, f as in `scripts/t15_stats.py`; d replaced by phase-shifted checks: decision/fill shifted by 0, +1, +2 minutes, at least 2 positive.
- V4 (5b.4): R events from 2023-01 are in the Kalshi data; the crash test runs on R 2023-01..2023-08 with the same rule (sparse by construction: events only). J has no odds data before 2024. Not run on J: stated, not hidden.
- Decision: P1 (DSR >= 0.70, net placebo >= 0.90, robustness >= 3, no veto). A part is called "does not hold" only with: reproduction of a published or positive-control result, rules as written, three scale points (theta or class sets), the registered budget used, and enough power; otherwise "not at depth" with what is missing.
- Power (written into `power.json` at registration): minimum detectable per-trade net mean at 80 percent power, one-sided 5 percent, = 2.487 x sd / sqrt(n), for sd 10, 20, 40 bp and n = 30, 60, 120, 300, 600; and the minimum detectable annual Sharpe given the number of trade days. The realised sd comes from the placebo direction trades at run time and is printed in results.json.
- Multiple testing: report-only families use Holm over their own family; they never promote a variant.

## Budget and stop rules
- Compute: this box, at most 2 hours of CPU in the allowed window; Modal not planned (cost 0 USD, limit 1 USD). Deadline: first batch (R) 2026-10-09, everything 2026-10-12 22:00 UTC.
- Stop: if the R positive control fails and J has fewer than 100 tradable episodes at theta = 3, both are reported "not at depth" with the missing piece named; no rules are changed after results.
- Paper: a part that reaches P1 gets `paper-sleeve-<name>.md` (signal interface, position cap, stop rule, live data); it still needs the v2.2 experiment file frozen on 2026-10-08 and the live-feed consistency check of 5b.8 (IEX versus SIP, at least 20 sessions) before orders. No orders from this task.

## H1 (R)
- Hypothesis: when Kalshi odds before a scheduled release lean hawkish by more than their own median size, TLT falls over the next 5-120 minutes relative to a random direction.
- Failure mode: Kalshi expectations equal consensus (Diercks, Katz, Wright 2026 find Kalshi about equal to Bloomberg for core CPI and unemployment, better only for headline CPI and the fed funds rate); a pre-release lean has no information about the surprise.
- Measurement: variants R1/R2 x 5/30/120, net Sharpe, placebo, DSR, positive control.
- Stop/Pivot criterion: positive control fails -> not at depth; passes and best three median net Sharpe <= 0 or placebo < 0.9 -> does not hold for TLT-pooled; report-only per-class numbers are leads for the next iteration.

## H2 (J)
- Hypothesis: one-hour jumps in policy odds are followed by continuation or reversal of the mapped ETF over 15-240 minutes (Tsang-Yang 2026: a debate jump largely reversed, an assassination-attempt jump persisted, so the sign depends on how anticipated the news was and cannot be assumed).
- Failure mode: odds jumps follow the ETF move (the same news hits both), so the ETF has already moved; the 1-hour sampling and extended-hours spreads absorb any residual drift.
- Measurement: 18 variants, net Sharpe, timing placebo, DSR. Continue and reverse are both counted trials.
- Stop/Pivot criterion: best-three-median net Sharpe <= 0 or placebo < 0.9 at three theta points with >= 100 episodes at theta 3 -> does not hold; fewer episodes -> not at depth.
