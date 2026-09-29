# Search Space: h20260929_71_wikipedia_pageviews

Single-mechanism lightweight path (no campaign contract; see
docs/plan-step-10-mechanism-supplementation-2026-09-03.zh.md section 3.1).
One path, `wikipedia_pageview_weekly_attention`, with 4 preregistered candidates
sharing spec `strategy_specs/drafts/h20260929_71_wikipedia_pageviews.yaml`. Benchmark family: spy_market_proxy, title_shuffle_placebo_500, mirror_control_long_decliners, VC28_90_slow_signal_control.
Costs: `reports/research/iterations/h20260929_71_wikipedia_pageviews/cost-table.json`. The candidate manifest at
`reports/research/iterations/h20260929_71_wikipedia_pageviews/candidate-manifest.json` is the authoritative per-candidate parameter
binding; this file is descriptive only.

Outcome: the IC gate failed, so the 4 candidates were not evaluated (ledger rows `not_evaluated_ic_gate_failed`). Results: `results.json`.
