# Search Space: t20261006_15_intraday_rules

Single-mechanism lightweight path (no campaign contract), one path `intraday_rules_scale_curve`
with 17 preregistered anchor candidates (paper-spec cells at each depth point) sharing spec
`strategy_specs/drafts/t20261006_15_intraday_rules.yaml`. Benchmark family: random-direction placebo (100 seeds),
band-shift placebo, same-exposure buy and hold, same-count random-entry placebo.
Costs: `reports/research/iterations/t20261006_15_intraday_rules/cost-table.json`. The candidate manifest at
`reports/research/iterations/t20261006_15_intraday_rules/candidate-manifest.json` is the authoritative anchor binding;
the full registered grid (A 3,672, B 153, C 162, D 216 = 4,203 versions, each a counted trial) is
`reports/research/iterations/t20261006_15_intraday_rules/grid-registry.json` (sha256 recorded in the manifest).
