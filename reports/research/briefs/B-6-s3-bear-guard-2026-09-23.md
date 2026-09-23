# Brief B-6: S3 bear-regime gate vs an exposure-matched control (candidate H-20260923-11)

Executor: Claude (Sonnet 5). One session, one deliverable: build and pass the pre-registration
dossier only. Read this file, `docs/research-mission.zh.md`, `AGENTS.md`,
`reports/paper/renewal/2026-09-23-s3-stress-2016-2023.md`,
`reports/research/hypotheses/H-20260922-02-s3-voltarget-drawdown-brake.md`, and the
`dir:drawdown_brake_overlay` / `dir:levered_single_asset_sma_trend_gate` /
`dir:letf_multi_signal_regime_vote` / `dir:macro_credit_drawdown_probability_gate` rows in
`reports/research/harvest/directions.jsonl`. Do not read other history.

Giants: Gayed and Bilello (2016, SSRN 2741701, "Leverage for the Long Run") -- leverage above a
Moving Average, deleverage to bills below it, beats buy-and-hold and constant leverage across
windows and cycles. Faber (2007/2013, SSRN 962461, "A Quantitative Approach to Tactical Asset
Allocation") -- a second, independent giant for the same moving-average timing mechanism class
across unlevered asset classes. Gehrman (r/LETFs, Sep 2026 update) -- an independent, currently
live, real-money replication of the identical 200-day-SMA/cash rule on SSO, running since March
2024. Local: the 2026-09-23 pre-window stress replay found the frozen, already-renewed S3 book
loses -48.0% max drawdown on 2016-01..2023-09 (2018 -22.0%, 2022 -33.6%), a window no earlier test
ever covered; the earlier drawdown-brake experiment (H-20260922-02) was refuted because it lost to
its own calendar-shift placebo, with its own stated reopen condition: "a drawdown signal validated
with an exposure-matched control."

Question: does a bear-regime gate on S3 (move S3's risk weight to SHY while the gate is on; signal
on a completed close, applied at the next open; gate state checked daily) cut the pre-window
drawdown by more than an exposure-matched lower volatility target would, without breaking the
frozen anchor-window return bar? Candidates: BG00 reference (no gate), BG01 (QQQ<SMA200), BG02
(SMH<SMA200), BG03 (HYG/IEF ratio<SMA100), BG04 (unscaled S3 equity curve<SMA200) -- exactly
these, no additions.

Preregistered grid (written to candidate-manifest.json before any return is computed): 5
candidates, one path, no ranking. The overlay machine itself (63-session absolute momentum vs SHY,
21-session realized-volatility target 0.40/0.60 boost, QQQ dip trigger, 1.0 leverage cap, monthly
rebalance) is copied unchanged from the live S3 renewal and is not searched. Costs 10/20 bp per
side; next-open fills. Controls (not candidates): EM-k per gate (bisect one scale factor c in
(0, 1] applied to both the 0.40 base and 0.60 boost targets so mean daily gross exposure matches
gate k's, on the design window only); CS-k per gate (20 within-design-window circular shifts of
the gate's own on/off series by `round(N * j / 21)` sessions, j = 1..20 -- not a short 1-20 session
shift, which is too weak a placebo for a slow 100/200-session trend gate). Adoption rule: design
window (a) drawdown improvement >=10pp vs BG00, (b) Sharpe >= BG00 Sharpe + 0.10, (c) Sharpe >
EM-k, (d) Sharpe beats >=18/20 CS-k; anchor window at 10 and 20 bp (e) CAGR >=50%, max drawdown
>=-35% (G1), do-no-harm only, no holdout claim (2026 already spent on S3 itself). Fixed budget: 88
simulations (4 gates + 4 EM-k + 80 CS-k); BG00 needs none (reuse existing stress-replay and
renewal numbers).

Process and gates:
1. Write the hypothesis card `reports/research/hypotheses/H-20260923-11-s3-bear-guard.md`
   (why/design/gates/placebos/stop condition; status: preregistered, not executed; results left
   empty; `previous: H-20260922-02`).
2. Build the iteration dossier `h20260923_11_s3_bear_guard` (direction-review, external-brief,
   hypotheses.md, search-space, candidate-manifest, cost-contract, data-feasibility,
   decision-record placeholder, sources/ snapshots with sha256, new verified source cards in
   `reports/harness/source_cards/h20260923_11_s3_bear_guard.jsonl`, reusing the 8 verified
   h20260922_02 volatility-target cards where they still apply). `oc research direction-check`
   and `oc research iteration validate --stage pre-backtest` must both pass before any evaluation
   run.
3. Write the source spec `strategy_specs/drafts/s3_bear_guard_h20260923_11.yaml` (research only,
   lifecycle draft, execution broker none, `research_design` block bound to the iteration) and
   check it with `oc spec validate`.
4. Register the direction: append one row to `reports/research/harvest/directions.jsonl` for
   `dir:s3_bear_regime_guard` after checking `oc research directions check`, then
   `oc research directions validate`.
5. Do not run the historical evaluation in this pass. A later pass runs the 88 preregistered
   simulations, writes `reports/research/iterations/h20260923_11_s3_bear_guard/report.md` and
   `trial-ledger.jsonl` with the per-gate adoption-rule table, and a result brief
   `reports/research/briefs/B-6-result.md` (<= 40 lines): one-line conclusion, per-gate
   pass/fail, refuted-or-not, next step. A lesson card `reports/research/lessons/L-20260923-11.md`
   if refuted.

Constraints: no backtest and no design/anchor-window return or metric computation in this pass;
do not touch `reports/paper` or the live specs `strategy_specs/drafts/us_etf_*.yaml`; do not
modify Python code, tests, docs, or crontab; do not read `.env` or `/root/.config`; do not commit.
