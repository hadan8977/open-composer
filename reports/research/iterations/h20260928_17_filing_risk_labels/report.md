# h20260928_17_filing_risk_labels -- report

- Feature: DeepSeek-extracted 8-K risk_score (0-1), fixed-seed 50-ticker x 8-quarter
  (2024Q3..2026Q2) panel, 436 items scored, reduced to 400 (ticker, quarter) rows (all 400 had a
  computable forward 20-trading-day return).
- Standalone rank IC (RISK01), per-quarter Spearman, forward 20-trading-day return:
  - Real: mean IC -0.0565 (t=-1.67, n=8 quarters), 6/8 quarters negative (75% sign-stable).
  - Placebo (filings shuffled across tickers within quarter): mean IC +0.0423 (t=0.77), 6/8
    quarters positive -- OPPOSITE sign from real, and 74.9% of the real IC's magnitude.
- Zoo-lift check: not attempted -- the existing liquid-500 factor-ranking pipeline
  (scripts/run_h20260917_02_ml_ranking.py, 1953 lines, own top-500-ADV panel/feature-root layout)
  is not quick to adapt to this pilot's disjoint 50-ticker sample within budget; standalone IC only,
  per the brief's own escape hatch.
- Preregistered gate (candidate-manifest.json keep_rule): pass requires stable sign (>=60%, met:
  75%) AND placebo |IC| <50% of real |IC| with the SAME sign. The placebo clause fails on both
  counts (different sign, 74.9% not <50%) -- see results.json `preregistered_gate_evaluation` for
  the wording-tension note between direction-review.json's OR-phrased prose and the manifest's
  AND-structured literal gate; the stricter (manifest) reading is applied.
- Verdict: **stop**. Do not scale this construction (this prompt, this 50-ticker sample) beyond the
  400-filing-quarter pilot. n=8 quarters is too small to distinguish the negative real IC from
  placebo noise of similar magnitude and opposite sign.
- Pass flags:
  - workflow_pass true;
  - research_pass false;
  - llm_contribution_pass false (feature did not clear its own preregistered gate);
  - ml_contribution_pass n/a (no ML model trained);
  - paper_ready_pass false.
