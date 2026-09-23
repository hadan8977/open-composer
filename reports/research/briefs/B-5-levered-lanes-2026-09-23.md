# Brief B-5: A second levered-industry lane beyond semiconductors (candidate H-20260923-10)

Executor: Claude (Sonnet 5). One session, one deliverable: build and pass the pre-registration
dossier only. Read this file, `docs/research-mission.zh.md`, `AGENTS.md`,
`reports/research/hypotheses/H-20260923-09-s3-attribution.md`,
`reports/research/hypotheses/H-20260918-06-pooled-etf-relative-strength.md`, and
`reports/research/intel/I-20260923-01-factor-library-result-mining.md`. Do not read other history.

Giants: Moskowitz & Grinblatt 1999 (Journal of Finance), "Do Industries Explain Momentum?" --
industry return continuation explains much of individual-stock momentum and is itself highly
profitable after controls. Hsieh et al., arXiv 2504.20116 (2025) -- leveraged-ETF compounding
depends on return autocorrelation, not only volatility drag. Local: H-20260923-09 found the live
S3 book's 116.3% anchor return is concentrated in trending SOXL+USD (58.5% anchor / 69.4%
holdout average weight), i.e. a semiconductor trend trade, not a diversified menu; I-20260923-01
ranks Ken French's 49 value-weighted industries and finds Gold, Chips, Banks and Aero as the top
four select-window performers, with Chips already the live book.

Question: does any of five single-ETF levered sector lanes -- NUGT (gold miners), JNUG (junior
gold miners), FAS (financials), DPST (regional banks), DFEN (aerospace/defense) -- clear the
frozen S3-machine gates (G1-G5) while staying weakly correlated (<=0.5 anchor daily-return
correlation) with the live S3 book, so it could run as a genuinely diversifying second sleeve.

Preregistered grid (written to candidate-manifest.json before any return is computed): 5
candidates, one path, no ranking. The overlay machine itself (63-session absolute momentum vs
SHY, 21-session realized-volatility target 0.40/0.60 boost, QQQ dip trigger, 1.0 leverage cap,
monthly rebalance) is copied unchanged from the live S3 renewal and is not searched. Costs 10/20
bp per side; next-open fills. Placebos: 24-ETF pool-rank and 20-offset dip-signal calendar-shift,
both <=10% (2% strict family-wise reported alongside).

Process and gates:
1. Write the hypothesis card `reports/research/hypotheses/H-20260923-10-levered-lanes.md`
   (why/design/gates/placebos/stop condition; status: preregistered, not executed; results left
   empty; `previous: H-20260923-09`).
2. Build the iteration dossier `h20260923_10_levered_lanes` (direction-review, external-brief,
   hypotheses.md, search-space, candidate-manifest, cost-contract, data-feasibility,
   decision-record placeholder, sources/ snapshots with sha256, new verified source cards in
   `reports/harness/source_cards/h20260923_10_levered_lanes.jsonl`, reusing the 8 verified
   h20260922_02 volatility-target cards where they still apply). `oc research direction-check`
   and `oc research iteration validate --stage pre-backtest` must both pass before any
   evaluation run.
3. Write the source spec `strategy_specs/drafts/levered_lanes_h20260923_10.yaml` (research only,
   lifecycle draft, execution broker none, `research_design` block bound to the iteration) and
   check it with `oc spec validate`.
4. Do not run the historical evaluation in this pass. A later pass runs the five candidates plus
   the three diagnostics (each lane raw, each lane vt40-only, the live S3 book as correlation
   reference), writes `reports/research/iterations/h20260923_10_levered_lanes/report.md` with the
   G1-G5 table and the correlation check per lane, and a result brief
   `reports/research/briefs/B-5-result.md` (<= 40 lines): one-line conclusion, per-lane
   pass/fail, refuted-or-not, next step. A lesson card
   `reports/research/lessons/L-20260923-10.md` if refuted.

Constraints: no backtest and no 2026 return/metric computation in this pass; do not touch
`reports/paper` or the live specs `strategy_specs/drafts/us_etf_*.yaml`; do not modify Python
code; do not read `.env` or `/root/.config`; do not commit.
