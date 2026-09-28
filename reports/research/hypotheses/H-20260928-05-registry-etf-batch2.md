---
card_id: H-20260928-05
status: executed, mixed (2/7 watch_recent, 5/7 refuted; 0 K1, 0 K2) (round 1, 2026-09-28)
lane: preregistered, batch screen
previous: H-20260928-04
direction_id: dir:letf_published_rules_live_tracked, dir:turn_of_month_equity_seasonality, dir:end_of_month_reversal_effect, dir:front_running_sector_seasonality, dir:pre_fomc_announcement_drift, dir:covered_call_cef_income_pwb
iteration: h20260928_05_registry_etf_batch2
criteria:
  - name: k1_standalone_offset_median_sharpe_anchor
    threshold: 1.1882247485942519
    direction: ">="
  - name: k1_standalone_offset_median_sharpe_stress
    threshold: 0.6447464886503398
    direction: ">="
  - name: k1_net20_cagr_positive_both_windows
    threshold: 0
    direction: ">"
  - name: k2_combination_sharpe_edge_anchor
    threshold: 0.05
    direction: ">="
  - name: k2_combination_sharpe_edge_stress
    threshold: 0.05
    direction: ">="
  - name: watch_recent_anchor_only
    threshold: 1.1882247485942519
    direction: ">="
---
# H-20260928-05 registry ETF batch 2 (7 candidates) vs S3

- Status: **executed, mixed** (round 1) -- hypothesis family: six routine registry-triage
  directions (leveraged-ETF published rule, four calendar/event anomalies, one
  covered-call CEF proxy) -- layer: standalone or S3-combination sleeve -- data tier:
  **tier 3** (OHLCV-derived quantities only)
- Previous link: H-20260928-04 (S3 alt-diversifier batch 1: 19/19 refuted, 0 K1/K2/watch)
- Iteration dossier: `reports/research/iterations/h20260928_05_registry_etf_batch2/`
  (direction-review, external-brief, candidate-manifest with 7 candidates, search-space,
  cost-contract, data-feasibility, trial-ledger, results.json, report.md; passed
  `oc research direction-check` and `oc research iteration validate --stage pre-backtest`
  and `--stage final`)
- One-line hypothesis: does at least one of 7 published-rule replications (HFEA fixed
  55/45 UPRO/TMF; turn-of-month SPY; end-of-month reversal SPY; front-running sector
  seasonality; pre-FOMC drift on SPY and TQQQ; an XYLD covered-call proxy) clear K1 or K2
  against S3, drawn from the batch-2 registry triage's remaining untested directions?

## Why

This batch clears the routine registry-triage backlog (24 batch-2-assigned directions;
17 were already resolved at triage as not_executable/evidence_too_weak/triaged-to-
stock-agent) rather than leaving queued directions unexecuted. `oc research directions
check` for each mechanism (hfea, turn of month, front running, fomc drift, covered call)
found no local prior test under the current K1/K2 keep rule. Each of the 7 rules is
published with an independent primary or secondary source (Bogleheads HFEA thread;
etftrends.com/hulltactical.com turn-of-month; Graziani 2024 SSRN via harbourfrontquant
for end-of-month reversal; Quantpedia for front-running sector seasonality; Lucca & Moench
2015 JF via quantseeker.com for pre-FOMC drift; paperswithbacktest.com for the
covered-call CEF, proxied by XYLD since the original fund BEP liquidated in 2010).

## Design

Machine (frozen, not searched): each candidate runs its own published rule over local SIP
daily data. Two candidates (EOM_REVERSAL_SPY, FRONT_RUN_SECTOR_TOP2) were originally
declared `freq: "M"` (21-offset monthly sweep); both rules are only defined on a specific
calendar-anchored date (last trading day of the month), so declaring them "M" made
offsets 1-20 never fire and the offset-median silently degenerated to pure SHY. This was
caught and corrected **before any valid result was computed for either candidate**:
re-declared single-version `freq: "D"` on the calendar-anchored date only, recorded
verbatim in `candidate-manifest.json`'s `parameters.freq_correction`. Cost 10bp/side
primary, 20bp/side stress. No parameter search, no model training, no mutation.

Candidates (7): HFEA_UPRO_TMF, TOM_SPY, EOM_REVERSAL_SPY, FRONT_RUN_SECTOR_TOP2,
FOMC_DRIFT_SPY, FOMC_DRIFT_TQQQ, XYLD_COVERED_CALL_PROXY.

Windows: select 2023-09-18..2025-12-31, anchor 2024-01-08..2026-09-17 (frozen gate),
stress 2016-05-02..2023-09-15, 2026-01-02..2026-09-17 holdout reported but contaminated.

## Gates (adoption rule)

Same K1/K2 keep rule as H-20260928-04, plus the runbook's forward-only `watch_recent`
tier: anchor-window judged Sharpe clears the K1 bar (>=1.1882) but the stress-window
Sharpe does not (<0.6447). `watch_recent` is not a keep and not a promotion -- forward
tracking only, logged to `reports/research/screens/kept.jsonl`.

## Results

Executed 2026-09-28 (`scripts/screen_batch.py --batch h20260928_05_batch2 --iteration
h20260928_05_registry_etf_batch2`; report
`reports/research/iterations/h20260928_05_registry_etf_batch2/report.md`, `results.json`;
raw leaderboard `reports/research/screens/h20260928_05_batch2/leaderboard.json`).
**Mixed: 2/7 watch_recent, 5/7 refuted; 0/7 K1, 0/7 K2.**

EOM_REVERSAL_SPY: judged 10bp Sharpe 1.2406 anchor (>=1.1882 bar) / 0.5845 stress (<0.6447
bar) -> **watch_recent**. Combination edge +0.2069 anchor / -0.1732 stress -> K2 fail.
FRONT_RUN_SECTOR_TOP2: judged 10bp Sharpe 1.4022 anchor (>=1.1882 bar) / 0.4517 stress
(<0.6447 bar) -> **watch_recent**. Combination edge +0.2502 anchor / -0.1680 stress -> K2
fail. Both cleared only after the freq_correction; before it, both had silently screened
as pure SHY.

The other 5 fail K1 on anchor Sharpe alone (HFEA_UPRO_TMF 0.5387, TOM_SPY -0.6876,
FOMC_DRIFT_SPY -0.8449, FOMC_DRIFT_TQQQ 0.3125, XYLD_COVERED_CALL_PROXY 0.8903, all below
1.1882) and fail K2 in at least one window -- **refuted**.

Lesson: this batch's two watch_recent candidates repeat the H-20260928-02/H-20260928-04
pattern -- a real anchor-window (2024-2026, calm bull market) combination edge that does
not survive the harder stress period (2016-05..2023-09). Per the runbook's forward-only
rule, EOM_REVERSAL_SPY and FRONT_RUN_SECTOR_TOP2 are logged to `kept.jsonl` for
observation only (no optimization, no promotion); drop either on 3 forward months with
Sharpe <0.5 or a max drawdown >1.5x its anchor-window drawdown. The other 5 are
refuted-in-this-form; do not retry with new parameters inside this manifest without a new
mechanism or new disclosed data.
