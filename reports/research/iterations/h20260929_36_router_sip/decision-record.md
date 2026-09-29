# Decision Record: h20260929_36_router_sip

Status at preregistration (before any return is computed). The final section is appended after the backtest.

## Frozen parameter table (decoded from the label, checked against code)

Label: `lb10_entry2_top1_open0_mom0_rv1_qprior_negative_reversal_maxopen0_maxmomnone`, produced by `IntradayDailyParams.label` (open_composer/research/intraday_daily_rotation.py lines 66-82). The runner builds `IntradayDailyParams` from the values below and asserts `.label` equals this string.

| Label token | Parameter | Value | Source lines |
|---|---|---|---|
| lb10 | lookback_days | 10 | label line 68 (f-string `lb{lookback_days}`) |
| entry2 | entry_after_bars | 2 | label line 68 |
| top1 | top_n | 1 | label line 68 |
| open0 | min_opening_return_pct | 0.0 | label line 70; reversal grid fixes it to `[0.0]` at line 574 |
| mom0 | min_prior_momentum_pct | 0.0 | label line 70; reversal grid fixes it to `[0.0]` at line 575 |
| rv1 | min_relative_volume | 1.0 | label line 71 |
| qprior_negative | market_gate | qqq_prior_negative | label line 67 (`qqq_` replaced by `q`); allowed value at line 43; gate test `prior_momentum < 0` at lines 1089-1090 |
| `_reversal_` suffix | selection_style | opening_reversal | label branch at lines 72-81 (base label returned only for opening_momentum) |
| maxopen0 | max_opening_return_pct | 0.0 | label lines 75-80; grid default `[0.0, -0.2]` at line 576; filter `opening_return > max` at lines 1046-1050 |
| maxmomnone | max_prior_momentum_pct | None | label lines 78-81; grid default `[None]` |

Other frozen facts: the archived spec's `selected_route_label` (open_momentum:lb10_entry5_..._rv0.8_..._maxopen-0.2) is a different, older string and is NOT the frozen route; the frozen route is the sweep_001/002 memory "Current best" (score 28.55, memory line 3). Entry uses `day.opens[entry_after_bars]` (line 1144), opening return uses `opens[0]` and `closes[entry_after_bars-1]` (lines 1113-1114), prior momentum uses the previous close and the close `lookback_days` sessions earlier (lines 1115-1116).

## Source of the sentence "Alpaca stayed negative across lookback 5/10/15 on the same gate"

It is line 9 ("Latest validation") of `reports/research/control/nasdaq_long_short_event_router_1m_sweep_002-memory.md` (also sweep_001-memory line 9). It says Longbridge data briefly improved at lookback 5 with the qqq_prior_negative gate, while Alpaca (IEX cache) was negative at lookback 5, 10 and 15 on that gate in a recent-regime sweep; the same memory then says the 2024-2026 full-window Alpaca sweep keeps lookback 10 as the best candidate. The sweep behind the first statement is not retained in the repo, so the two statements cannot be reconciled from files; the retained numbers are sweep_002 (IEX, full window Sharpe 1.41) and sweep_003 (Longbridge, same route, out-of-sample Sharpe -0.19). It means the route's IEX success was already window-dependent before this recheck.

## P1

- Path: router_sip_recheck (7 preregistered candidates: R0, R0_long, R0_short, P1, P2, P3, B_ew)
- Decision: continue to the backtest under the frozen rules in candidate-manifest.json; K1, K2 and G3 decide the registry status
- Reason: the registry blocker for this row is exactly the missing SIP recheck; short authorization no longer blocks. Preregistered code reading predicts the short leg is empty (R0 equals R0_long, R0_short has zero trades).
- Next iteration suggestion: decided after the results (see final section).

## Final (after the backtest; all numbers from results.json in this directory)

Run: `scripts/run_h20260929_36_router_sip.py` under `run_capped.sh --mem 1.2G`, SIP cache 2023-01-03..2026-09-28 (937 common sessions, series from 2023-01-18). The unchanged `_backtest_params` reproduces this run's R0 total return to 1e-13 percent at all three cost tiers (`backtest_params_crosscheck`).

Anchor window 2024-01-08..2026-09-28, R0 (188 trades in 683 sessions): 10 bp per side Sharpe -0.126 (plain, no rf, +0.054), CAGR -1.38 percent, max drawdown -27.4 percent, win rate 51.1 percent, mean +1.79 bp per trade; 20 bp per side Sharpe -0.730, CAGR -14.15 percent, mean -18.2 bp per trade; original draft cost (2.5 bp per side) Sharpe +0.326 (plain +0.506), CAGR +9.44 percent, mean +16.8 bp per trade. The gross edge is about 21.8 bp per trade, so break-even cost is about 10.9 bp per side.

- K1: false (Sharpe -0.126 vs 1.19; 20 bp CAGR -14.15 percent vs > 0) -> `decision.K1`.
- K2: false, combo edge vs vol-matched S3 offset 0 = -0.614 (threshold +0.05; lane 0.10), correlation with S3 0.22 -> `k2_inputs`, `decision.K2`. S3 offset 0 at 10 bp in the same window has Sharpe 1.84, CAGR 118 percent (`s3_offset0_c10_reference`).
- G3: false by one point, R0 beats 178 of 200 placebos (89 percent; threshold 90); placebo Sharpe mean -0.83, p95 +0.15, max +0.67. P1/P2/P3 (anchor, 10 bp) Sharpe -0.289 / -1.417 / -0.670, all below R0. No placebo distribution CAGR at 20 bp is positive.
- Stress 2016-05..2023-08: pending (待补压力期). The 2023-01..2023-08 slice: R0 10 bp Sharpe -0.970, CAGR -12.8 percent, mean -19.4 bp per trade (157 sessions, 39 trades).
- Windows: select 2023-09-18..2025-12-31 R0 10 bp Sharpe -0.106, CAGR -0.22 percent; contaminated holdout 2026-01-02..2026-09-17 Sharpe -0.008, CAGR +0.39 percent; new holdout 2026-09-18..09-28: 7 sessions, 1 trade (report only, Sharpe not meaningful). By calendar year at 10 bp (descriptive, computed from daily_returns.csv after the fact): 2023 -5.4 percent, 2024 -14.5 percent, 2025 +9.3 percent, 2026 (to 09-28) +2.0 percent.
- B_ew (12 names, entry bar 2, exit close, every day): 10 bp Sharpe -2.09, CAGR -35.1 percent; 20 bp Sharpe -4.43; original cost Sharpe -0.339, CAGR -5.3 percent. The route beats the unfiltered basket by a wide margin; that does not make it profitable.
- H3 confirmed: R0 equals R0_long to numerical precision at all tiers and R0_short has 0 trades in 927 sessions (`structure_checks`). The router's short leg never fires for opening_reversal with top_n=1 (intraday_daily_rotation.py lines 1012-1026: the short ranking equals the long ranking and its symbol is already in `used`). The IEX research_pass therefore never tested a short leg; it was a long-only buy-the-opening-dip rule. Not edited (shared module); flagged for the owner.

IEX artifact question (H2): same parameters, same original cost, same window 2024-05-31..2026-05-29: SIP R0 CAGR +10.33 percent, plain Sharpe 0.536, 131 trade days (results.json candidates.R0.orig.iex_comparison) vs the recorded IEX result annualized 35.24 percent, Sharpe 1.41, 153 traded days (sweep_002 Rank 1 full window). The sign survives at the original cost, but about two thirds of the return and Sharpe did not survive the change of tape, and at the frozen 10 bp per side the route loses money. The Longbridge cross-check (sweep_003) already showed out-of-sample Sharpe -0.19 on the same route. The likely mechanism (IEX carries about 2.5 percent of volume, so opening returns and relative volume on IEX prints pick unrepresentative names) is plausible but not tested: no local IEX minute cache exists to replay.

Data handling: the SIP minute archive is already split- and dividend-adjusted (adjustment=all). Open over previous close at NVDA 2024-06-10, AVGO 2024-07-15 and NFLX 2025-11-17 is 0.9957, 0.9984 and 0.9954, no overnight gap outside 0.7-1.4 anywhere, so no rescaling was applied (`audit.split`, `audit.split_handling`). Entry bars are clock-aligned (first bar 09:30 on 100 percent of sessions, bar 2 = 09:32 on 100 percent except AVGO 99.5 percent). Minute last close vs SIP daily close differs by more than 0.5 percent on 11 of 12,181 symbol-days (max 1.43 percent, AMD); these are closing-auction differences and were not removed.

Reporting change after seeing results (recorded): the first run printed a rf-excess Sharpe of about -14 for R0_short, an artifact of a zero-return series; `metric_block` now reports null Sharpe when a window has no trades. No decision number changed.

## P1

- Path: router_sip_recheck
- Decision: stop (refuted)
- Reason: K1 fails at every cost that meets the frozen contract (10 bp Sharpe -0.126, 20 bp CAGR -14.15 percent), K2 fails (-0.614) and G3 misses by one point; the route's gross edge of about 22 bp per trade is smaller than the 20 bp round-trip contract cost plus noise, and about two thirds of the IEX-era result was a tape effect. The short leg was never active.
- Next iteration suggestion: do not paper-trade or tune this route. If short-side intraday reversal is wanted, preregister a new direction with a real short ranking (a short leg that is not the same list as the long leg) on SIP data; treat entry-cost realism (actual 09:32 spreads for mega-caps, possibly below 10 bp) as a separate cost-contract question and do not reuse the contaminated windows.
