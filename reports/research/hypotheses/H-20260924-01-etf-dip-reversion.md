---
card_id: H-20260924-01
status: partial -- sleeve refuted (0/24 pass G1-G5 at T0/T2, unreachable at T1); D1 signal-level real effect, research admission pending T1 by decision
lane: preregistered
previous: null
direction_id: dir:etf_dip_reversion_ibs_connors
iteration: h20260924_01_etf_dip_reversion
brief: reports/research/hypotheses/H-20260924-01-etf-dip-reversion.md
criteria:
  - name: g1_anchor_cagr
    threshold: 0.50
    direction: ">="
  - name: g1_anchor_max_drawdown
    threshold: -0.35
    direction: ">="
  - name: g2_holdout_sharpe
    threshold: 1.0
    direction: ">="
  - name: g3_placebo_beat_frac
    threshold: 0.10
    direction: "<="
  - name: research_admission_trade_t_stat
    threshold: 2.0
    direction: ">="
  - name: research_admission_t1_over_t0_gross_fraction
    threshold: 0.60
    direction: ">="
---

# H-20260924-01 Short-term index-ETF dip reversion (IBS and Connors/turtle RSI(2))

- Status: **Final, partial (round 1), closed 2026-09-24 on Stage A evidence.
  Sleeve-level: refuted (0/24 candidates pass G1-G5 at T0 or T2, and T1
  cannot pass G1/G1'/G4 either, since T0 is an unexecutable upper bound for
  T1 and already falls short). Signal-level: D1 (IBS-Algotradekit) shows a
  real effect at T0/T2; its research-admission verdict stays formally
  pending T1 by decision (Stage B deferred, not skipped silently -- see
  decision-record.md's `reopen_if`).** -- hypothesis family:
  short_term_etf_dip_reversion -- data tier: **tier 3** (OHLCV-derived:
  daily bars for T0/T2 and the persistence table; QQQ/SPY minute bars would
  be needed for T1 if reopened)
- Iteration dossier: `reports/research/iterations/h20260924_01_etf_dip_reversion/`
  (direction-review, external-brief, candidate-manifest with 24 candidates,
  search-space, cost-contract, data-feasibility; passed
  `oc research direction-check` and
  `oc research iteration validate --stage pre-backtest`)
- One-line hypothesis: do published IBS and Connors/turtle RSI(2)/3-day-
  pattern rules, run on QQQ/SPY signals with 1x/3x execution, clear this
  repo's frozen recent-window G1-G5 gates and a trade-level research-
  admission rule at realistic T1 (15:50 ET proxy, market-on-close) timing?

## Why

The owner asked on 2026-09-24 to evaluate the US-stock strategies inside
github.com/fmzquant/strategies. The corpus review and its 2026-09-24
addendum (`reports/research/intel/I-20260923-10-fmzquant-strategies.md`)
found the repo is a content-marketing mirror of TradingView ports with no
attached out-of-sample or live evidence (82% crypto, median backtest window
30 days), except for one US-equity family with both a published mechanism
and a multi-year post-publication public record: short-term index-ETF dip
reversion. Pagonidis (2014, NAAIM) documents that Internal Bar Strength
(IBS) forecasts next-day close-to-close equity ETF returns and attributes
this to intraday overreaction corrected the next day, a mechanism with
independent academic grounding going back to Lehmann (1990) and Kloßner,
Becker & Friedmann (2012), both cited in Pagonidis's own literature review.
Three of the repo's files are direct TradingView ports of published rules
(Algotradekit's IBS strategy; Connors & Alvarez's 2009 "R3" and "3-Day
High/Low"); StockCharts' ChartSchool and Pagonidis's own text supply the
classic RSI(2) and IBS-filtered-RSI(2) variants. See
`reports/research/hypotheses/H-20260924-01-etf-dip-reversion.md`'s sibling
`external-brief.md`/`hypotheses.md` for the full source list and mechanism
discussion, and `search-space.md` for the T0/T1/T2 timing derivation
(including the finding that D1's published Pine source measures IBS from
the prior completed bar, an extra-lag idiom this engine deliberately does
not reproduce, and that D5's own Pine source backtests at an unexecutable
same-close fill).

Negative evidence bounds this round. `dir:giants_sweep_published_etf_rules`
(refuted): 0/24 published ETF rules cleared the identical frozen G1-G5 bar;
its closest cell (`f1_tqqq_rsi_no_hedge_ablation`, a Composer-style RSI(10)
trend/hedge branch on TQQQ, anchor Sharpe 1.37, failed G1) is a structurally
different rule from this round's IBS/RSI(2)/3-day-pattern family and did not
test QQQ/SPY-signal 1x/3x execution, so it sets an honest prior rather than
a direct refutation. The repo's signal-card library v1 rejected generic
technical indicators as cross-sectional stock-ranking signals -- a different
claim (broad-universe ranking) from this round's single-instrument,
timing-based test on index ETFs, consistent with the owner's tier framework
(pure technical indicators ranked low, not excluded) and this task's
explicit instruction to justify the family by mechanism.

## Design

Six rules, parameters exactly as published (see candidate-manifest.json for
the full per-candidate detail): D1 IBS-Algotradekit (IBS<=0.09/0.11 with
EMA(220)/EMA(200) trend filter on QQQ/SPY, exit IBS>=0.985/0.995 or 14
sessions); D2 IBS-Pagonidis raw (IBS<0.20, one-session hold, no trend
filter); D3 Connors R3 (close>EMA(200), RSI(2) falling 3 sessions with
RSI(2)[3 sessions ago]<60 and RSI(2)[today]<10, exit RSI(2)>70); D4 Connors
RSI(2) classic (close>SMA(200) and RSI(2)<=5, exit close>SMA(5)); D5 Connors
3-Day High/Low (close>EMA(200), close<EMA(5), three consecutive lower highs
and lows, exit close crosses above EMA(5)); D6 IBS-filtered RSI(2) (D4 entry
plus IBS<0.20 at the entry close). Each rule x 2 signal underlyings (QQQ,
SPY) x 2 execution instruments (1x = same ETF, 3x = TQQQ for QQQ / UPRO for
SPY) = 24 candidates, the single-mechanism lightweight-path cap. Frozen
giants-sweep protocol, unchanged: warmup 2022-06-01..2023-09-15, select
2023-09-18..2025-12-31, holdout 2026-01-02..2026-09-17, anchor
2024-01-08..2026-09-16; costs 10 bp primary / 20 bp stress per side. Primary
timing T1 (15:50 ET minute-bar proxy, MOC fill at the same session's
official close); T0 (same-close) and T2 (next-open) are report-only
diagnostics, never candidates.

## Gates (adoption rule)

Per candidate, independently: **G1-G5** exactly as defined in
`scripts/run_giants_sweep.py` (G1 anchor CAGR>=50% and max DD>=-35%; G1'
anchor Sharpe>=2.0 and CAGR>=30%; G2 holdout Sharpe>=1.0 and holdout CAGR>0;
G3 every declared placebo beats the true cell on select Sharpe <=10% of
seeds; G4 G1 or G1' still holds at 20 bp; G5 long-only spot US ETFs on the
existing Alpaca daily cron). For the 12 1x T1 cells only, **research
admission**: mean net return per trade > 0 in both select and holdout;
trade-level t>=2.0 over select+holdout; real mean-per-trade >= the 95th
percentile of the random-entry-timing placebo over select+holdout; T1 keeps
>=60% of T0's gross mean per trade. Multiple comparisons: 24 candidates, all
reported regardless of outcome; deflated Sharpe of the best cell reported
given 24 trials.

## Placebos

Random entry timing matched to the real candidate's trade count and
holding-period distribution, sampled only from days that pass the rule's
own trend filter where it has one, 60 seeds. The frozen calendar-shift
placebo from `scripts/run_h20260918_05_recent_menu.py`, 20 seeds.

## Stop condition

A candidate that fails any of G1-G5 (or, for the 12 1x T1 cells, research
admission) is refuted for this parameterization. If none of the 24
candidates passes, the direction is refuted; reopening requires a new
published rule, new disclosed data, or new evidence of a mechanism/regime
shift, not re-tuning the frozen thresholds. Fixed budget: 24 preregistered
candidates, no added cells; T0/T2 are diagnostics on the same 24 candidates,
not additional candidates. This is round 1 of this direction. A
supplementary 2016-2026 per-calendar-year persistence table (daily T0/T2,
QQQ/SPY/IWM/DIA) is reported as context, not as an admission criterion.

## Results

**Sleeve-level: refuted.** Stage A (daily-bar T0/T2 diagnostics) executed
2026-09-24: 0 of 24 candidates pass all_gates at either T0 (unexecutable
upper bound) or T2. G1 (anchor CAGR>=50%, maxDD>=-35%) and G1' (Sharpe>=2.0,
CAGR>=30%) fail on every cell at 10bp: best anchor CAGR is 47.1%
(d1_spy_3x, maxDD -30.6%, Sharpe 1.42), best anchor Sharpe is 1.50
(d4_spy_3x, CAGR 20.9%, maxDD -6.2%), third-best CAGR is d1_qqq_3x at 36.0%
(maxDD -27.0%, Sharpe 0.88); deflated Sharpe of the best T0 cell given 24
trials is 0.92. Since G4 needs G1/G1' to also hold at 20bp and neither
holds at 10bp, no cell can pass all_gates at T1 either -- T0 is an
unexecutable upper bound for T1, so this is a valid closure without running
Stage B, not a skipped step.

**Signal-level: D1 (IBS-Algotradekit) shows a real effect at T0/T2,
formally pending T1.** D1's 1x research-admission diagnostics (mean net
return per trade at 10bp, trade-level t-stat, 60-seed random-entry placebo
percentile -- computed 2026-09-24 specifically for this verdict, using the
preregistered definitions but at T0/T2 rather than the preregistered T1):

| cell | timing | mean/trade select | mean/trade holdout | trade t-stat | placebo pct |
|---|---|---:|---:|---:|---:|
| d1_qqq_1x | T0 | +1.91% | +0.27% | 2.12 | 58.3 |
| d1_qqq_1x | T2 | +1.54% | -1.02% | 1.45 | 63.3 |
| d1_spy_1x | T0 | +2.13% | +0.96% | 2.99 | 91.7 |
| d1_spy_1x | T2 | +2.11% | +0.59% | 2.93 | 86.7 |

D1-SPY is positive in both windows at both timings with t-stats near 3.0,
but neither D1 cell clears the strict 95th-percentile placebo bar even at
the more favorable timing (T0). D1's own research-admission verdict is
therefore left formally pending T1 (never evaluated at the only
preregistered/counted timing), not asserted as passed or failed. 2016-2026
daily persistence (T0, context only): D1 is positive on all four symbols
(QQQ +12.5%/yr, SPY +9.7%/yr, DIA +6.2%/yr, IWM +7.6%/yr) with 82-91% of
years positive; D2 (raw IBS, no trend filter) is negative on 3 of 4 symbols.

Stage B (T1 minute-bar timing) is **deferred by decision, not run and not
implemented** -- it cannot change the sleeve verdict above, and is only
needed if D1 is later used as a component (see decision-record.md's
`reopen_if`). Full detail, split/dividend review, and the resume plan:
`reports/research/iterations/h20260924_01_etf_dip_reversion/decision-record.md`;
raw output in the same directory's `stage_a_summary.parquet`,
`trial-ledger.jsonl`, `persistence-2016-2026.parquet`,
`d1-research-admission-t0-t2.json`.
