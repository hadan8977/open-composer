# Brief B-7: S3's remainder in a Defense First rotation vs an equal-weight and random-rank control (candidate H-20260923-12)

Executor: Claude (Sonnet 5). One session, one deliverable: build and pass the pre-registration
dossier only. Read this file, `docs/research-mission.zh.md`, `AGENTS.md`,
`reports/paper/renewal/2026-09-23-s3-stress-2016-2023.md`,
`reports/research/hypotheses/H-20260923-11-s3-bear-guard.md`, and the
`dir:defense_first_taa_carlson_concretum` / `dir:s3_bear_regime_guard` / `dir:s1_sector_rotation_voltarget`
/ `dir:giants_sweep_published_etf_rules` / `dir:recent_window_etf_menu_rotation` rows in
`reports/research/harvest/directions.jsonl`. Do not read other history.

Giants: Moreira and Muir (2017) and Man Group (2017) -- volatility scaling raises Sharpe for risk
assets, already verified in H-20260922-02 and reused unchanged here to ground why the S3
vt40+boost overlay (and the remainder it produces) is trustworthy. Thomas Carlson (2025, SSRN
5334772, "Defense First: A Multi-Asset Tactical Model for Adaptive Downside Protection") -- rank
TLT/GLD/DBC/UUP monthly by blended 1/3/6/12-month momentum, weight 40/30/20/10 by rank, screen
each against a T-bill cash hurdle, fallback to SPY on failure; already read once at the
Quantitativo blog level before this task was scoped (registry row
dir:defense_first_taa_carlson_concretum), now cross-checked against AllocateSmartly's independent
rule-by-rule replication (tested from 1971) and the author's own LinkedIn confirmation of the
asset menu. Local: the 2026-09-23 pre-window stress replay found S3's mean risk exposure over
2016-2023 is about 0.61, so ~39% of the book sits idle in SHY on average -- the remainder this
round asks whether to hold better; the same-day sibling iteration (h20260923_11,
dir:s3_bear_regime_guard) refuted four bear-regime gates on S3's *risk* sleeve, a different,
timing-layer question from this round's composition-layer question about the remainder.

Question: if the part of S3's book that now sits in SHY is held in a Defense First rotation
instead, does S3's design-window Sharpe rise and its drawdown fall, beyond what momentum-free
diversification or random rankings give, without breaking the anchor-window return bar?
Candidates: DF00 reference (S3 as renewed, remainder in SHY), DF01 (remainder in Defense First,
published SPY fallback), DF02 (remainder in Defense First, SHY fallback instead) -- exactly these,
no additions.

First step: open the primary source (search SSRN / the web for Carlson's paper), save a snapshot,
and pin the exact rules -- momentum score definition, cash-hurdle instrument and test, rebalance
timing, failing-slot handling. If the paper's full text cannot be fetched, preregister the best
available independent replication's description instead (not just Quantitativo's) and say so
explicitly, noting any discrepancy between replicators.

Preregistered grid (written to candidate-manifest.json before any return is computed): 3
candidates, one path, no ranking. The S3 overlay machine itself (63-session absolute momentum vs
SHY, 21-session realized-volatility target 0.40/0.60 boost, QQQ dip trigger, 1.0 leverage cap,
monthly rebalance) is copied unchanged from the live S3 renewal and is not searched -- only the
remainder it produces is redirected. Costs 10/20 bp per side over the full expanded weight vector;
next-open fills. Controls (not candidates): EW (1, shared: static 25/25/25/25 TLT/GLD/DBC/UUP,
monthly rebalance, no ranking); RR-k (40 per candidate, 80 total: same weights/cash-hurdle/
fallback as the real candidate, rank-to-asset assignment replaced by a seeded random permutation
each month). Adoption rule: design window (a) Sharpe >= DF00 Sharpe + 0.10, (b) max drawdown no
worse than DF00's, (c) Sharpe beats >=36/40 RR-k, (d) Sharpe > EW's; anchor window at 10 and 20 bp
(e) CAGR >=50%, max drawdown >=-35% (G1), do-no-harm only, no holdout claim (2026 already spent on
S3 itself). Fixed budget: 83 simulations (2 candidates + 1 EW + 80 RR-k); DF00 needs none (reuse
existing stress-replay and renewal numbers).

Process and gates:
1. Open the primary source and pin the exact rules (see above); save source snapshots with
   sha256 and new verified source cards in
   `reports/harness/source_cards/h20260923_12_s3_defense_first.jsonl`.
2. Write the hypothesis card `reports/research/hypotheses/H-20260923-12-s3-defense-first.md`
   (why/design/gates/placebos/stop condition; status at writing: preregistered, not executed (executed 2026-09-23: keep SHY, see H-20260923-12); results left
   empty; `previous: H-20260923-11`).
3. Build the iteration dossier `h20260923_12_s3_defense_first` (direction-review, external-brief,
   hypotheses.md, search-space, candidate-manifest, cost-contract, data-feasibility,
   decision-record placeholder, sources/ snapshots). `oc research direction-check` and
   `oc research iteration validate --stage pre-backtest` must both pass before any evaluation run.
4. Write the source spec `strategy_specs/drafts/s3_defense_first_h20260923_12.yaml` (research
   only, lifecycle draft, execution broker none, `research_design` block bound to the iteration)
   and check it with `oc spec validate`.
5. Register the direction: append one row to `reports/research/harvest/directions.jsonl` for
   `dir:s3_defense_first_remainder` after checking `oc research directions check`, then
   `oc research directions validate`.
6. Do not run the historical evaluation in this pass. A later pass runs the 83 preregistered
   simulations, writes `reports/research/iterations/h20260923_12_s3_defense_first/report.md` and
   `trial-ledger.jsonl` with the per-candidate adoption-rule table, and a result brief
   `reports/research/briefs/B-7-result.md` (<= 40 lines): one-line conclusion, per-candidate
   pass/fail, refuted-or-not, next step. A lesson card `reports/research/lessons/L-20260923-12.md`
   if refuted.

Constraints: no backtest and no design/anchor-window return or metric computation in this pass;
do not touch `reports/paper`, other iterations' files (especially h20260923_11's, which is running
concurrently), or the live specs `strategy_specs/drafts/us_etf_*.yaml`; do not modify Python code,
tests, docs, or crontab; do not read `.env` or `/root/.config`; do not commit.
