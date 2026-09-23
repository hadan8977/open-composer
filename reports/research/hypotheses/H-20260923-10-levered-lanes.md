---
card_id: H-20260923-10
status: executed 2026-09-23, refuted
lane: preregistered
previous: H-20260923-09
direction_id: dir:levered_industry_trend_second_bet
iteration: h20260923_10_levered_lanes
brief: reports/research/briefs/B-5-levered-lanes-2026-09-23.md
criteria:
  - name: anchor_cagr
    threshold: 0.50
    direction: ">="
  - name: anchor_max_drawdown
    threshold: -0.35
    direction: ">="
  - name: anchor_sharpe_alt
    threshold: 2.0
    direction: ">="
  - name: anchor_cagr_alt
    threshold: 0.30
    direction: ">="
  - name: holdout_sharpe
    threshold: 1.0
    direction: ">="
  - name: holdout_return
    threshold: 0.0
    direction: ">"
  - name: placebo_pool_rank_beat_fraction
    threshold: 0.10
    direction: "<="
  - name: placebo_calendar_shift_beat_fraction
    threshold: 0.10
    direction: "<="
  - name: stress_20bp_cagr_or_sharpe
    threshold: 0.50
    direction: ">="
  - name: anchor_correlation_with_live_s3_book
    threshold: 0.5
    direction: "<="
---
# H-20260923-10 A second levered-industry lane beyond semiconductors

- Status: **preregistered, not executed** (round 1) -- hypothesis family: levered_industry_trend_second_bet
  -- layer: instrument/lane selection under a frozen risk overlay (overlay itself not re-tested) --
  data tier: **tier 3** (OHLCV-derived quantities only for the machine; industry evidence comes from
  Ken French's official files)
- Previous link: H-20260923-09 (attribution of the live S3 book: 116.3% anchor return / -32.3% max
  drawdown / Sharpe 1.82 anchor, holdout Sharpe 2.21; concentrated in SOXL+USD at 58.5% anchor / 69.4%
  holdout average weight, i.e. a trending semiconductor position, not a diversified menu)
- Iteration dossier: `reports/research/iterations/h20260923_10_levered_lanes/` (direction-review,
  external-brief, candidate-manifest with 5 candidates, search-space, cost-contract, data-feasibility;
  must pass `oc research direction-check` and `oc research iteration validate --stage pre-backtest`
  before any evaluation)
- One-line hypothesis: is there a second levered sector lane, beyond semiconductors, that under the
  frozen S3 overlay machine clears the frozen gates and is weakly correlated with the live S3 book, so
  it could run as a separate diversifying sleeve?

## Why

The only mechanism that has cleared our bar so far is a trending sector held with leverage under a
volatility target (S3-vt40+boost: 116.3% anchor return / -32.3% max drawdown / Sharpe 1.82 anchor,
holdout Sharpe 2.21), and H-20260923-09 showed it is concentrated in semiconductors (SOXL+USD 58.5%
anchor / 69.4% holdout average weight) -- it is a leveraged semiconductor trend trade wearing a
"5-ETF menu" label, not a diversified sleeve. Moskowitz and Grinblatt (1999, Journal of Finance)
give the economic reason a *second* trending industry is a defensible next step rather than an ad hoc
ETF pick: industry return continuation is a decades-old, independently replicated effect, stronger
than individual-stock momentum. Locally, I-20260923-01 (a first-party computation on Ken French's
official 49 value-weighted industry files, construction methodology verified in this round) ranks
Gold 66.2%/-28.8% (Sharpe 1.47), Chips 45.9%/-16.0% (Sharpe 1.71, already the live book), Banks
36.5%/-10.1% (Sharpe 1.55) and Aero 35.7%/-3.8% (Sharpe 1.91) as the top four select-window
(2023-09-18..2025-12-31) industries. Leveraged-ETF select-window records for the mapped instruments
(NUGT 115%, JNUG 132%, FAS 55%, DFEN 98%) correlate with SOXL at only 0.19-0.49, suggesting real
diversification potential if the gates hold. Hsieh et al. (arXiv 2504.20116, April 2025) explain the
mechanism directly: leveraged-ETF compounding depends on return autocorrelation, not only volatility
drag, so a lane needs its *own* trend driver, not just any leveraged sector wrapper.

Negative evidence and priors that bound this round: H-20260918-06 refuted pooled ETF relative
strength without a hand-picked, risk-homogeneous menu (0/8 preregistered families beat SPMO's 1.46
selection-window Sharpe); the 2026-09-22 giants sweep found 0/24 public momentum/trend rules survived
G1 or G1' on the anchor window; single-name priors under this exact machine (TQQQ 38.5%, UPRO 36.9%,
TECL 45.8% anchor return, from the H-20260923-09 leave-one-out decomposition) are all below the 50%
G1 bar, ruling out "just add more S&P/Nasdaq single names." Selection bias must be named explicitly:
the five lanes were chosen after seeing select-window results, so only the untouched 2026 holdout can
confirm them, and our delisted-ETF archive has zero closed leveraged funds, so every leveraged-ETF
number in this family carries unquantified survivorship bias.

## Design

Machine (frozen, not searched, copied unchanged from the live S3 vt40+boost renewal): single-ETF
lane; 63-session total-return lookback; rebalance on the last session of each month; absolute-momentum
filter against SHY (hold the lane ETF at 100% when its 63-session return exceeds SHY's, else 100%
SHY); down-only volatility target min(1, 0.40 / 21-session realized volatility of the unscaled book),
recomputed at the open after a rebalance close and when the boost toggles; dip boost raising the
target to 0.60 for 10 sessions after QQQ closes above its 200-session SMA with Wilder RSI(10) below
30; leverage cap 1.0; removed weight to SHY. Signal on a completed close, fill at the next open. Cost
model: 10 bp per side primary / 20 bp per side stress, `sum(|delta w|) x slippage`, reused contract id
`cost_v1_10_20bps_next_open`. Data: local SIP daily adjusted archive (`data/sip/daily`); risk-free BIL.

Candidates (5, each an independent comparison, no selection among them): LN01 NUGT (2x gold miners),
LN02 JNUG (2x junior gold miners), LN03 FAS (3x financials), LN04 DPST (3x regional banks), LN05 DFEN
(3x aerospace and defense). Diagnostics, not candidates and never ranked: each lane raw (no overlay)
and with vt40 only (no boost); the live S3 book (A4 menu TQQQ/SOXL/UPRO/USD/TECL, 63d, top 2,
renormalize survivors, vt40+boost) as the correlation reference.

Windows: selection 2023-09-18..2025-12-31 (feeds only the placebo distributions, not a ranking --
there is no ranking step in this design), holdout 2026-01-02..2026-09-17 (scored once), anchor
2024-01-08..2026-09-16 (carries G1/G1'/G4).

Each candidate ETF's own daily-reset leverage objective (verified in this round's Direxion source
cards for DPST and NUGT/DUST: the fund resets to its stated multiple every single day and should not
be expected to hold that multiple over any multi-day period) is the tradable reality the momentum and
volatility-target inputs are computed on -- there is no synthetic "ideal" unlevered-index proxy in
this design.

## Gates

- **G1**: anchor annualized return >= 50% with max drawdown no worse than -35%, OR
- **G1'**: anchor Sharpe >= 2.0 with annualized return >= 30%.
- **G2**: holdout Sharpe >= 1.0 and holdout return > 0.
- **G3(a) pool-rank placebo**: run the identical frozen machine on each ETF of the 24-ETF levered
  pool (TQQQ SOXL SPXL TNA UPRO SSO QLD NUGT UDOW LABU FAS TECL JNUG ERX BOIL YINN GUSH TMF URTY BULZ
  AGQ DPST UWM NAIL); the fraction of pool ETFs other than the lane whose holdout Sharpe >= the lane's
  must be <= 10%.
- **G3(b) dip-signal calendar-shift placebo**: shift the dip-boost trigger over 20 fixed offsets;
  fraction beating the lane must be <= 10%. The strict family-wise read (10% / 5 comparisons = 2%) is
  reported alongside both G3 placebos.
- **G4**: G1 or G1' still holds at 20 bp per side.
- **G5**: the long spot ETF is executable on Alpaca Paper.
- **Second-bet criterion**: anchor-window daily-return correlation with the live S3 book <= 0.5.

Pass = all of the above, per lane, independently. No cross-lane ranking or selection step exists in
this design.

## Placebos

See G3(a) and G3(b) above. Both are computed per lane against the fixed 10% threshold, with the
strict family-wise 2% (10% / 5 comparisons) read reported alongside as a secondary, non-blocking view.

## Stop condition

No lane passes -> the direction is refuted. Reopen only with a new mechanism (for example a regime
model that forecasts which industry will trend next) or new data (for example an options-implied or
news-driven industry signal), not by re-tuning the frozen overlay's own parameters or widening the
candidate list to more ETFs inside the same five industries. Compute budget for the decisive test: 15
minutes. This is round 1.

## Results

Executed 2026-09-23 under the preregistered manifest (`scripts/run_h20260923_10_levered_lanes.py`;
report `reports/research/iterations/h20260923_10_levered_lanes/report.md`, cells and trial ledger
beside it). **Refuted: no lane passes.**

| lane | anchor CAGR / Sharpe / maxDD | holdout Sharpe | pool-placebo beat | corr with S3 | failed |
|---|---|---|---|---|---|
| NUGT | 54.2% / 1.16 / -26.4% | 0.53 | 43.5% | 0.20 | G2, G3 |
| JNUG | 57.6% / 1.19 / -30.1% | 0.57 | 39.1% | 0.21 | G2, G3 |
| FAS | 11.1% / 0.36 / -38.3% | -0.74 | 82.6% | 0.20 | G1-G4 |
| DPST | 2.4% / 0.19 / -41.2% | 0.61 | 34.8% | 0.21 | G1-G4 |
| DFEN | 30.5% / 0.60 / -63.6% | -0.13 | 79.2% | 0.09 | G1-G4 |

The gold-miner lanes do what the selection window promised on the anchor window (G1 and G4 pass,
correlation with S3 only 0.2), but the untouched 2026 holdout does not hold (Sharpe 0.53 / 0.57), and
39-44% of the 24 pool ETFs under the identical machine do as well there -- generic leverage, not the
industry choice. Banks and defense fail every gate. The machine itself is not the problem: the live S3
book scores 116.3% / 1.82 / -32.3% with holdout Sharpe 2.21 in the same run.

**Lesson.** Industry momentum chosen from the selection window did not carry into 2026; under this
machine the 2026 leaders were SOXL (2.16), TECL (1.86), LABU (1.36), GUSH (1.12), which cannot be
picked from the holdout. A second bet needs a mechanism that says *which* sector will trend next
(stop condition, as preregistered): a regime or sector-forecast model, or new data (options-implied
or news-driven industry signals) -- not more ETFs from the same five industries.
