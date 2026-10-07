# Search Space: t20261007_02_pm_event_study

Single-mechanism lightweight path (no campaign contract), one path `pm_odds_event_study` with 24 preregistered trading variants sharing spec
`strategy_specs/drafts/t20261007_02_pm_event_study.yaml`: part R (scheduled releases, 2 signals x 3 horizons = 6 variants, TLT, pooled classes) and
part J (Polymarket odds jumps, 3 thresholds x 3 horizons x 2 modes = 18 variants, theme primary ETF). All 24 are counted trials for DSR; report-only
breakdowns (per class, per theme, other ETFs) never enter selection. Benchmark family: random-direction timing placebo (100 seeds), realised-surprise
positive control, buy and hold of the same exposure. Costs: `reports/research/iterations/t20261007_02_pm_event_study/cost-table.json`.
Rules, theme tables, release classes and cost function are frozen in `scripts/t0702_pm_grid.py` (sha256 in the candidate manifest);
candidate manifest `reports/research/iterations/t20261007_02_pm_event_study/candidate-manifest.json` is the authoritative binding.
