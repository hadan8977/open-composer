---
card_id: H-20260928-31
status: refuted -- 0/3 candidates pass stage 1 (2026-09-28, see report.md and decision-record.md)
lane: preregistered
previous: H-20260924-02
direction_id: dir:regime_trust_uncertainty_gate_momentum_ranker
iteration: h20260928_14b_uncertainty_gate
brief: reports/research/hypotheses/H-20260928-31-uncertainty-gate.md
criteria:
  - name: stage1_auroc
    threshold: 0.60
    direction: ">="
  - name: stage1_placebo_dd_improvement_pp
    threshold: 5.0
    direction: ">="
  - name: stage1_placebo_sharpe_percentile
    threshold: 0.90
    direction: "<"
  - name: stage1_owner_rule_sharpe_gap
    threshold: 0.10
    direction: ">="
  - name: stage2_owner_rule_sharpe_gap_stress
    threshold: 0.10
    direction: ">="
---

# H-20260928-31 Trained ensemble-disagreement (DEUP-style) uncertainty gate for the T1 12-1 momentum book

- Status: **Final, round 1, closed 2026-09-28: refuted.** 0 of 3 candidates
  pass stage 1. U1/U2 (book-level gates, z(s-1)>0.80/0.90) both score AUROC
  0.522 for flagging above-median-future-drawdown days -- indistinguishable
  from a 0.50 coin flip -- both make the anchor-window (2024-01-08..
  2026-09-16) max drawdown *worse* than unguarded (-37.2%/-35.2% vs -41.5%
  unguarded is a smaller number, but the *forward-looking* drawdown-flag
  improvement used for stop condition (b1) is -4.3pp/-6.3pp, i.e. negative,
  against a ~0 placebo median) and fail the owner's Sharpe-vs-vol-matched-
  control rule (gap +0.050 and -0.219, both below the required 0.10). U3
  (exclude the top-20%-most-uncertain names at cohort formation) scores
  worse than its own 200-seed random-quintile-drop placebo (real Sharpe
  0.755 vs. placebo 90th percentile 1.039) and fails the owner rule
  (gap -0.324). See `reports/research/iterations/h20260928_14b_uncertainty_gate/report.md`
  and `decision-record.md` (continue/pivot/stop call and `reopen_if`).
  hypothesis family: regime_trust_uncertainty_gate --
  data tier: **tier 1+model** (OHLCV-derived price-volume features, trained
  LightGBM ensemble, no new external data source)
- Iteration dossier: `reports/research/iterations/h20260928_14b_uncertainty_gate/`
  (direction-review, external-brief, candidate-manifest with 3 candidates,
  search-space; passed `oc research direction-check` and
  `oc research iteration validate --stage pre-backtest`)
- One-line hypothesis: does a TRAINED ensemble-disagreement (DEUP-style
  epistemic uncertainty, per arXiv 2603.13252 "When Alpha Breaks") signal,
  applied as either a book-level regime-trust gate (U1, U2) or an
  individual-name tail-risk cap (U3) on the unchanged T1 top-30-of-500
  12-1 momentum book, raise anchor-window Sharpe by >=0.10 over a
  same-realized-vol-matched unguarded control -- not just cut drawdown --
  and survive a placebo that reproduces the same on/off share or exclusion
  count by chance?
- Prior art / negative evidence directly informing this card's design:
  `H-20260924-02` (0/5 rule-based crash guards passed G2/G3 on this same
  book -- every fixed-rule exposure guard tested so far reduces to sliding
  along the risk-return line or an arbitrary on/off schedule
  indistinguishable from a calendar shift); `dir:meta_labeling_position_tiers`
  (refuted -- a position-size-tiering meta-label reduced to plain
  de-leveraging under a label-time-shift placebo). This card's stage-1 stop
  conditions are explicitly designed to catch both of those failure modes on
  a TRAINED (not rule-based) candidate family before any stage-2 compute is
  spent.
- Candidates (all counted toward trial exposure, DSR n=3): U1 (book-level
  exposure to 0.5 when the uncertainty quantile z(s-1) exceeds 0.80), U2
  (book-level exposure to 0.0 when z(s-1) exceeds 0.90), U3 (individual-name
  DEUP-style cap: exclude the top 20% most-uncertain names at cohort
  formation, backfill by momentum rank).
- Stage-1 stop conditions (any one hit stops that candidate, refuted, no
  stage 2): (a) AUROC<0.60 for z(t) flagging above-median-future-drawdown
  days, 2024-01-08..latest (U1/U2 only); (b) a >=200-seed placebo where the
  real candidate's drawdown improvement beats the placebo median by <5pp or
  its anchor Sharpe is below the placebo distribution's 90th percentile;
  (c) the owner's rule -- anchor-window Sharpe improvement over a
  same-realized-vol-matched unguarded control is <0.10.
- Stage-2 (only for a candidate clearing all of stage 1): the same >=0.10
  Sharpe-vs-matched-control bar on the stress window
  (2016-05..2023-08, truncated to the actual walk-forward out-of-sample
  start), G1-G5, K1/K2 tiering, DSR at 3 trials.
- Next: see `decision-record.md` for the continue/pivot/stop call once
  results are computed.
