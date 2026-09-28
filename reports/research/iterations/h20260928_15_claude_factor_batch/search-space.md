# Search Space: h20260928_15_claude_factor_batch

One path, `claude_factor_batch_screen`: 8 Round-1 candidates (F01-F08, see
candidate-manifest.json and hypotheses.md for formulas, sources, expected
sign and confidence), plus up to 4 Round-2 candidates preregistered after
SELECT-only feedback, before the TEST window is ever computed. Total budget
12, well under the 24-per-path / 80-per-round caps. No parameters are tuned
within a factor (each factor is a single fixed formula); the only "search"
is which of the 12 factors is picked by SELECT-window |rank ICIR|, exactly
mirroring how the symmetric zoo baseline (every numeric column of
alpha101_broad/alpha191_broad/osap_price_broad plus the 24 existing rank
cards) is screened. Cost assumptions: signal-level (no strategy cost gate);
the two SELECT-chosen winners get a costed 10bp/20bp top-50 monthly book via
signal_card.rank_card, unmodified. Benchmark family: the zoo's own
SELECT-chosen best factor (the queue task's own decision rule), plus each
set's TEST-window oracle-best with DSR deflated by set size for information.
This is Wave 9.2's "single mechanism, no campaign" band: one economically
distinct question (does the LLM-loop method add IC over the zoo), not a
strategy-family discovery campaign, so no `research-campaign-contract.json`
is opened (see data-feasibility.json for the explicit lightweight-exemption
declaration).
