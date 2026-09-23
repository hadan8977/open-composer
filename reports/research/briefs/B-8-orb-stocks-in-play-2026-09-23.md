# Brief B-8: Individual-stock opening-range breakout on "Stocks in Play" (candidate H-20260923-13)

Executor: Claude (Sonnet 5). One session, one deliverable: build and gate-check the pre-
registration dossier, a data-feasibility check, and an engine-design note only -- no backtest, no
engine code. Read this file, `docs/research-mission.zh.md`, `AGENTS.md`,
`docs/plan-research-coverage-2026-09-23.zh.md` sections 4-6, the `dir:orb_stocks_in_play_relative_
volume` and `dir:orb_etf_opening_range_breakout` rows in `reports/research/harvest/directions.jsonl`,
`reports/research/intel/intel-intraday-and-options-runnable-2026-09-18.md`,
`reports/research/intel/I-20260921-02-near-term-alternatives.md`, and
`reports/research/intel/I-20260923-07-owner-five-directions-wave.md` section 4. Also read
`scripts/run_h20260918_02_orb_etf.py` (the refuted ETF cousin, whose trade mechanics are reused)
and the most recent completed dossiers (`h20260923_12_s3_defense_first`, `h20260923_11_s3_bear_
guard`) to copy the format from.

Giants: Zarattini, Barbon & Aziz, "A Profitable Day Trading Strategy For The U.S. Equity Market"
(SSRN 4729284, first version 2024-02-16) -- individual-stock 5-minute opening-range breakout
filtered by opening relative volume, top 20 by that ratio, long+short combined, author-reported
1,637% total / Sharpe 2.81 / max drawdown 12% over 2016-2023, versus S&P 500's 198%. Read in full
this pass (46KB extracted text, all sections), not just the abstract. Cross-checked against
QuantConnect's independent code replication (`quantconnect.com/research/18444`, confirms the
mechanism's shape on a single year / narrower universe) and the same authors' own 2026-07-08
self-critique of the single-ETF simplification (already refuted locally). Local: this project's
own `dir:orb_etf_opening_range_breakout` (H-20260918-02/L-20260918-02) already refuted the fixed-
symbol ETF version -- a random-direction placebo caught it. This round is scoped, per the registry
row's own `reopen_if` clause, to the individual-stock relative-volume selection layer specifically.

Question: does the paper's exact mechanism, made long-only and run on this project's own minute
data and cost conventions, clear a placebo bar (random direction; random non-in-play liquid
stocks) and a G1/G3-style gate -- and is the minute data itself feasible (survivorship-bias-free
enough, adjustment-consistent enough, indexed enough) to ask that question honestly? Candidates:
SIP01 (long-only, paper's parameters), SIP02 (long-only, stricter liquidity floor), SIP03
(long-short diagnostic, never promotable) -- exactly these, no additions, per the task's "keep the
candidate list small (2-4 cells)" instruction.

First step: open the primary source (the Concretum PDF) and the QuantConnect replication, pin the
universe filters, relative-volume definition and top-N selection, opening-range length, entry
type, stop distance, exit, sizing, leverage, costs, sample, and reported results (with/without
costs, long/short split if reported) with direct quotes. Note every place the paper and the
replication differ. This project already had a 2026-09-21 fetch of both (plus the 2026-07-08
self-critique) on disk with a verified source card; this pass reused those byte-identical snapshots
(re-verified by hash, not re-fetched) and read the full extracted text directly rather than relying
on the prior pass's paraphrase, which surfaced two things the paraphrase had missed: the individual-
stock section has **no profit target**, and the reported results are **long+short combined with no
published split**.

Design constraints (from the task): long-only primary, long-short diagnostic only. Design window on
older years (2016-2022, `data/sip-hist/minute`), frozen select window 2023-09-18..2025-12-31
(`data/sip/minute`, reusing this project's existing H-20260918-05 convention), 2026 reported as
already-seen with no OOS claim. Costs at 5/10/20bp per side plus the paper's commission as a cross-
check; conservative and one-bar-late stop-fill variants, both reported. Controls: RD (random
direction), RL (random non-in-play liquid stocks), plus the ETF-ORB result as a known-negative
reference (no new simulation). Frozen G1-G5 gates not relaxed (see the S3 dossiers and
`docs/plan-strategy-factory-2026-09-22.zh.md` for the exact thresholds); live feasibility (US
pattern-day-trader rule, Alpaca intraday buying power, simultaneous-position count) recorded, not
decided.

Process and gates:
1. Open the primary source and the replication, pin the exact rules with quotes; save source
   snapshots (reused from the 2026-09-21 fetch, re-verified by hash) and new verified source cards
   in `reports/harness/source_cards/h20260923_13_orb_stocks_in_play.jsonl`.
2. Write the hypothesis card `reports/research/hypotheses/H-20260923-13-orb-stocks-in-play.md`
   (why/design/gates/placebos/stop condition; status at writing: preregistered, not executed;
   results left empty; `previous: null`, first round of this direction).
3. Build the iteration dossier `h20260923_13_orb_stocks_in_play` (direction-review, external-brief,
   hypotheses.md, search-space, candidate-manifest with 3 candidates, cost-contract, data-
   feasibility, decision-record placeholder, `engine-design.md`, sources/). `oc research
   direction-check` and `oc research iteration validate --stage pre-backtest` must both pass before
   any evaluation run -- and did, on this pass's own build.
4. Write the source spec `strategy_specs/drafts/orb_stocks_in_play_h20260923_13.yaml` (research
   only, lifecycle draft, execution broker none, `research_design` block bound to the iteration)
   and check it with `oc spec validate` -- passed.
5. Register the direction: append one row to `reports/research/harvest/directions.jsonl` for
   `dir:orb_stocks_in_play_relative_volume`, status `queued`, after checking `oc research
   directions check`, then `oc research directions validate`.
6. Do not run the historical evaluation in this pass. A later pass writes
   `scripts/run_h20260923_13_orb_stocks_in_play.py` per `engine-design.md`, runs the 43
   preregistered simulations, writes `report.md`/`trial-ledger.jsonl`, and a result brief.

Constraints: no backtest and no engine/evaluation code in this pass; do not touch other iterations'
files, `reports/paper/`, or `coverage.json`; do not modify tests, crontab, or docs beyond the
listed deliverables; do not read `.env` or `/root/.config`; do not commit. Budget: about 60
minutes.
