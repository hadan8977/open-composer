# External Brief: h20260928_14b_uncertainty_gate

Queue task T-20260928-14, registry row `dir:regime_trust_uncertainty_gate_momentum_ranker`.
Eight sourced findings (three paper-level), full detail in `external-brief.json`.

1. **arXiv 2603.13252 "When Alpha Breaks"** (paper, 2026-03-01, opened directly this
   session) -- two-level DEUP-style uncertainty framework: a strategy-level
   regime-trust gate G(t) (AUROC ~0.72 overall, ~0.75 in the paper's own 2024
   AI-rally holdout) and a position-level epistemic tail-risk cap using an
   ensemble-disagreement signal ehat (correlation ~0.6 with absolute rank
   error). The paper's own headline finding -- a LightGBM ranker's 20-day
   signal breaking in the 2024 AI-rally regime -- independently corroborates
   this repo's own already-diagnosed T1 momentum-book 2024+ drawdown problem.
2. **Daniel & Moskowitz 2016 (NBER w20439 / JFE)** (paper) -- momentum crashes
   as 24-month-bear plus high-126-day-variance "panic" states, concentrated in
   the short leg; already operationalized as a rule and refuted on this exact
   book (H-20260924-02) since it never triggers in 2024-2026.
3. **Barroso & Santa-Clara 2015 (JFE)** (paper) -- 126-day realized-variance
   scaling toward a constant target vol; already operationalized as a daily
   rule and refuted on this exact book (H-20260924-02, reduces to sliding
   along the risk-return line, fails its own calendar-shift placebo).
4. **I-20260928-03 local intel note** (internal) -- surveyed five 2024-2026
   trainable-model candidates; only this DEUP/regime-trust direction was
   queued as feasible on free local data and directly relevant to our own
   diagnosed problem.
5. **Queue block T-20260928-14** (internal) -- the literal task contract:
   trained confidence gate, Sharpe-not-just-drawdown owner rule, stage-1/
   stage-2 stop conditions.
6. **Direction registry row** `dir:regime_trust_uncertainty_gate_momentum_ranker`
   (internal) -- confirms via `oc research directions check` and a targeted
   grep that no prior local test of this exact mechanism exists.
7. **h20260924_02 decision-record.md** (internal) -- 0/5 rule-based crash
   guards passed G2/G3 on this same book; direct negative-evidence baseline
   and the source of the reused `load_book`/`settle_market`/`calendar_shift`
   helpers.
8. **docs/current-view.zh.md, 2026-09-24 (12:30) section** (internal) --
   corrected T1 book anchor numbers (CAGR 63.1%, max DD -41.5%, Sharpe 1.09;
   best rule-based guard's holdout Sharpe only 0.87 against a required 1.0),
   confirming the target problem is current.

**Topic coverage**: regime-trust gate definition/AUROC, DEUP epistemic
uncertainty via ensemble disagreement, local prior-art check, rule-based
crash-guard negative evidence on the same book, vol-scaling negative evidence
on the same book, the T1 book's current drawdown problem statement, and
Modal budget/LightGBM hyperparameter reuse.

**Candidate matrix revisions**: none after the initial preregistration (U1
z>0.80 half-exposure, U2 z>0.90 zero-exposure, U3 top-20%-uncertainty cohort
exclusion) -- see `candidate-matrix-revisions` in `external-brief.json`.
