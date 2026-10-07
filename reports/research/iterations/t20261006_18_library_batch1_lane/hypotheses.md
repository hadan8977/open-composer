# Hypotheses and preregistration: t20261006_18_library_batch1_lane (T-20261006-18)

Written by the T-20261006-18 executor on 2026-10-06T23:23:25Z, before any lane return of this batch. Companion of
`t20261006_18_library_batch1` (same task). Code: `scripts/t18_lane.py` sha256 `888435091809dbc3785748cdb572c9b1692236be36179cf290dc32de8cad45aa`,
`scripts/screen_batches/t20261006_18_library_lane.py` sha256 `c26b2787282a0f4e1b1dde9597d8a23def0e1f536f50f55374f08c0f11369e63`; existing batches
`h20260928_42_opex_week` and `h20260929_02_pre_holiday_etf` are imported unchanged.

## 1. Rules (eight first-batch ids; primary member per id frozen)

| first-batch id | members (all counted as trials) | primary | source and deviations |
|---|---|---|---|
| qc-option-expiration-week-effect | OPEX_{SPY,QQQ,DIA,IWM}_{WEEK,WEEKMON} + 12 non-expiration placebo weeks | OPEX_SPY_WEEK | existing batch, unchanged |
| qc-pre-holiday-effect | PREHOL_{IWM,IJR,IWC,VB,SPY,QQQ}_H{1,2} + 6 random-day placebos | PREHOL_SPY_H1 | existing batch, unchanged |
| qc-turn-of-the-month-in-equity-indexes | TOM_{SPY,QQQ,IWM,DIA}_H{3,4} | TOM_SPY_H4 | QC buys SPY at the month-end open and sells after 3 sessions; here signal at the close before the last session, exit signal at the close of session k of the next month (fill next open) |
| qc-the-dynamic-breakout-ii-strategy | DYNBRK_{SPY,QQQ,IWM,DIA,GLD,TLT} | DYNBRK_SPY | QC trades EURUSD/GBPUSD long and short with intraday asks; here long-only on daily closes of Alpaca ETFs: lookback N (start 20, N = round(N(1 + dvol)), dvol from the 30-session close std, clipped 20-60); long when the close is above the EMA_N + 2 sd_N band and above the highest close of the previous N sessions; exit below the N-session mean |
| qc-ichimoku-clouds-in-the-energy-sector | ICHI_{XLE,VDE,XOP,OIH} | ICHI_XLE | QC trades the ten largest energy stocks long and short, default Ichimoku periods unspecified; here energy ETFs, long-only, close-only lines with the standard 9/26/52 and shift 26: long after the Chikou (close drawn 26 sessions back) crosses above the cloud, cash after it crosses below |
| qc-capm-alpha-ranking-strategy-on-dow-30-companies | CAPM_TOP2, CAPM_TOP3 | CAPM_TOP2 | QC uses the current Dow 30 (survivorship); here the 30 largest names by 21-day dollar volume rank at the signal date (point in time, `panel.adv_rank <= 30`), alpha = intercept of 21-session daily returns on SPY, long the top 2 (3), equal weight, monthly (21 offsets) |
| qc-january-barometer | JANBAR_{SPY,QQQ,IWM} | JANBAR_SPY | as QC: long in January; February-December long only if the January return > 0, else SHY (QC: BIL) |
| qc-can-crude-oil-predict-equity-returns | OILEQ_{USO,DBO} | OILEQ_USO | QC uses the OPEC basket price and Treasury bill rates; here USO / DBO monthly returns, 24 monthly observations of SPY(t) on oil(t-1), hold SPY when the forecast exceeds the BIL monthly return |

Long-only everywhere (lane protocol). 63 candidates in total = `n_trials` of every DSR.

## 2. Contract

`scripts/screen_lane.py`: next-open fill, 10 bp per side (20 bp stress), excess over BIL, windows anchor
2024-01-08..2026-09-17 (decides), stress 2016-05-02..2023-09-15 (diagnostic), `select` and `holdout` reported;
calendar rules are one version (freq D), month rules 21 offsets with the median offset judged. Control: vol-matched S3.
Placebo for every member: 200 circular shifts (>= 126 sessions) of the weight path against the returns through the
same simulator and costs; real anchor Sharpe is compared with the shifted ones.

## 3. Fixed decision rule

* **Own paper sleeve (incubation proxy, P1-style; robustness items not scored)**: the *primary* member has
  judged anchor edge over the vol-matched S3 control >= 0.10, anchor net-20bp Sharpe > 0, anchor DSR over the 63
  trials >= 0.70, circular-shift placebo percentile >= 0.90, and no crash veto (stress 21-session loss <= 5x monthly
  vol). A non-primary member that passes is reported as "needs confirmation" and is not promoted.
* **Unfounded in the recent window**: primary anchor net-10bp Sharpe <= 0 and every member of the id <= 0.3.
* **Not at depth**: everything else (single rules on 33 months cannot refute a calendar class).
* Power: anchor 33 months; the minimum detectable Sharpe at 80% power is reported from the Lo (2002) standard error.

## 4. Budget

Local, `flock /tmp/oc-heavy.lock ./scripts/run_capped.sh --mem 1.2G`, no Modal. Deadline 2026-10-10 22:00 UTC.

## 5. Hypothesis, failure mode, measurement, stop/pivot (validator headings)

* **Hypothesis**: at least one primary lane member meets the incubation proxy of section 3 under the lane contract.
* **Failure mode**: calendar effects weakened after publication, 33 months of anchor data, long-only versions drop the
  original short legs, ETF substitutes for the QuantConnect instruments (forex, single stocks, OPEC price).
* **Measurement**: lane leaderboard fields (anchor edge, DSR with 63 trials, net 20 bp Sharpe), circular-shift placebo
  percentile, V4 crash check on the stress window.
* **Stop/Pivot criterion**: section 3; a passing non-primary member is "needs confirmation" only; unfounded only under
  the recent-window rule of section 3.
