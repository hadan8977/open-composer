---
card_id: H-20260928-04
status: executed, refuted (19/19; 0 K1, 0 K2, 0 watch_recent) (round 1, 2026-09-28)
lane: preregistered, batch screen
previous: H-20260928-02
direction_id: dir:managed_futures_etf_hold_batch1_2026, dir:keller_antonacci_faber_taa_batch1_2026, dir:alt_diversifier_etf_hold_batch1_2026
iteration: h20260928_04_s3_alt_div_batch1
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
---
# H-20260928-04 S3 alt-diversifier batch 1 (19 candidates) vs S3

- Status: **executed, refuted** (round 1) -- hypothesis family: three published-rule
  families (managed-futures ETFs held outright, Keller/Antonacci/Faber TAA rules, other
  alt-diversifier ETFs held outright) -- layer: standalone or S3-combination sleeve --
  data tier: **tier 3** (OHLCV-derived quantities / fund NAV only)
- Previous link: H-20260928-02 (cross-asset defensive-trend sleeve: D1 kept via K1, D2
  refuted; 0/2 K2) -- this round is a much larger batch screen of the same K1/K2 keep
  rule over 19 additional published rules
- Iteration dossier: `reports/research/iterations/h20260928_04_s3_alt_div_batch1/`
  (direction-review, external-brief, candidate-manifest with 19 candidates, search-space,
  cost-contract, data-feasibility, trial-ledger, results.json, report.md; passed
  `oc research direction-check` and `oc research iteration validate --stage pre-backtest`
  and `--stage final`)
- One-line hypothesis: does at least one of 19 published, long-only, US-listed-ETF rules
  (5 managed-futures ETFs held outright; 9 Keller/Antonacci/Faber tactical-allocation
  rules; 5 other alt-diversifier ETFs held outright) clear K1 (standalone Sharpe >=80% of
  S3's own median in both anchor and stress windows, positive 20bp CAGR) or K2 (a
  63-session inverse-vol blend with S3 beating a vol-matched delevered-S3 control by
  >=0.05 Sharpe in both windows)?

## Why

S3 is currently the only sleeve passing all frozen gates; H-20260928-02 found that a
narrow, hand-picked cross-asset sleeve (Defense First TAA) could clear K1 standalone but
not K2. This round widens the search to the broadest set of already-published,
already-live-tracked or SEC-registered diversifier/TAA rules available, rather than
inventing a new mechanism, per the mission's "search first, reuse before build" rule.
`oc research directions check` was run for every family keyword before this dossier was
built (managed futures ETF, Keller/Antonacci/Faber TAA family names); no local prior test
of any of these 19 exact rules against S3's K1/K2 keep rule was found (BAA-Balanced and
ADM had a prior test under the old frozen-gate criterion in `giants_sweep_20260922`, both
failing there too, and are re-included here only because the keep rule itself changed).

Mechanism is not invented for any of the 19: F1 candidates are each fund's own live NAV
(DBMF/KMLM/CTA/WTMF/FMF, no local re-derivation); F2 candidates reuse Keller & Keuning's
VAA/DAA/PAA/HAA/GPM papers, Antonacci's GEM (2012 NAAIM Wagner Award), Faber's GTAA (SSRN
962461) and the Engineered Portfolio blog's ADM, cross-checked against AllocateSmartly's
or TuringTrader's independent replications; F3 candidates (RPAR/UPAR/NTSX/QAI/TRTY) are
each fund's own SEC-registered methodology.

## Design

Machine (frozen, not searched): each of the 19 candidates runs its own published rule
(or, for F1/F3, simply holds the fund outright) over its own already-local SIP daily
data, swept across all 21 monthly rebalance-day offsets where the rule has monthly
turnover (F2 family) and judged by the offset median; F1/F3 hold-only candidates are
turnover-invariant so the offset sweep changes only the stress-window start date for
funds with partial history. Cost 10bp/side primary, 20bp/side stress. No parameter
search, no model training, no mutation -- this is a pure replication-and-screen round.

Candidates (19, no ranking between them -- each judged independently against K1/K2): see
`candidate-manifest.json` for the full list (F1_DBMF, F1_KMLM, F1_CTA, F1_WTMF, F1_FMF,
F2_VAA_G4, F2_DAA_G12, F2_PAA, F2_HAA, F2_GPM, F2_GEM, F2_GTAA, F2_ADM, F2_BAA_BAL,
F3_RPAR, F3_UPAR, F3_NTSX, F3_QAI, F3_TRTY).

Windows: select 2023-09-18..2025-12-31, anchor 2024-01-08..2026-09-17 (frozen gate),
stress 2016-05-02..2023-09-15, 2026-01-02..2026-09-17 holdout reported but contaminated.

## Gates (adoption rule)

Per candidate, either tier clears it:
- **K1**: standalone judged (median-offset) 10bp Sharpe >=80% of S3's own median Sharpe in
  both windows (anchor bar 1.1882, stress bar 0.6447), AND 20bp CAGR positive in both
  windows.
- **K2**: judged (median-offset) combination Sharpe (S3+candidate, inverse-63-session-vol
  weighted) minus vol-matched delevered-S3 control Sharpe >=0.05 in **both** the anchor
  window and the stress period.
- Forward-only `watch_recent` (not a keep): anchor-window Sharpe clears the K1 bar but
  stress does not.

G3 (placebo) does not apply: every candidate's rule is fully deterministic (published
weights or a hold-only NAV), no discretionary pick or gate-timing signal to randomize.

## Results

Executed 2026-09-28 (`scripts/screen_batch.py --batch h20260928_04_batch1 --iteration
h20260928_04_s3_alt_div_batch1`; report
`reports/research/iterations/h20260928_04_s3_alt_div_batch1/report.md`, `results.json`;
raw leaderboard `reports/research/screens/h20260928_04_batch1/leaderboard.json`).
**Refuted: 19/19 (0 K1, 0 K2, 0 watch_recent).**

No candidate reaches the K1 anchor-Sharpe bar (1.1882); the closest are F2_GEM (0.9570),
F3_TRTY (0.9203) and F2_GTAA (0.9019). No candidate clears K2 in both windows -- the
largest positive anchor-window combination edges (F1_DBMF +0.091, F1_CTA +0.204, F1_FMF
+0.081, F2_GTAA +0.145, F3_TRTY +0.136) all turn negative in the stress window
(2016-05..2023-09), the same anchor-window-is-not-a-hard-enough-test pattern
H-20260928-02 found for D1/D2. F1_CTA (1.46yr) and F3_UPAR (1.62yr) have under 2 years of
stress-window coverage (marked "待补压力期" per the runbook rule) but both already fail on
anchor Sharpe alone, so this data gap is not decisive for their verdict.

Lesson: neither a longer-established fund-of-record (WTMF/FMF/QAI, full stress-window
coverage since 2016) nor a shorter, more-recent one (CTA, KMLM, UPAR) clears the bar --
the shortfall is a genuine Sharpe/correlation gap versus S3's levered momentum profile,
not a data-recency artifact. Reopen only with a new mechanism (documented negative
correlation specifically in the 2022 rate-shock regime, or a longer/cleaner live trend
record), not by re-tuning these 19 rules' published/round-number parameters.
