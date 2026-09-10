# Step 13: recent-window high-return strategies (M track: quant+ML, L track: quant+LLM)

Status: **DRAFT / ACCUMULATING** -- results are appended here as they land
(coordinator instruction, 2026-09-10), not written up after the fact on
Friday. Plan: `docs/plan-step-13-recent-high-return-ml-and-llm-tracks-2026-09-09.zh.md`.
Gate contract: `config/promotion/recent-regime-high-return-gates-v2.json`
(`step13_recent_high_return`). Ledger: `reports/research/ledger/experiments.jsonl`.
Live progress log (checkpoint-level detail, commits, crash/fix cycles):
`reports/research/control/step13-2026-09-09-progress.md`.

**Known, disclosed defect affecting every number in this file computed
before commit `30879b4`** (2026-09-10): `returns_from_weight_schedule`
recomputed each day's return with a constant, never-updated target weight
for the whole holding window -- mathematically daily-rebalance-to-target,
not buy-and-hold. Fixed in `30879b4`; every M0/M0b/M1/two-stage number
below is post-fix unless explicitly marked otherwise.

## Track M (traditional quant + ML)

### M0 -- six static rule cells (top-20 of the ADV-liquidity universe table)

All 6 cells fail `all_gates_pass`. Best: `momentum_252_21_gate_off`
(cagr_recent_net=0.3374, mdd=-0.4722, hit=0.5725) -- clears CAGR/activity/
DSR/stress-cost, fails `cagr_excess_vol_matched_spy` (-0.34) and
`max_drawdown_recent` badly. `ret_126_rel`/`ret_63_rel` cells are flat to
negative (small/micro-cap dilution in a 1500-name universe, not a bug).

### M0b -- 16-cell grid (universe_top_n {500,200} x score {momentum_252_21,
momentum_252_21/vol_63} x top_k {20,50} x trend_gate {on,off})

All 16 cells fail `all_gates_pass` -- every cell fails
`cagr_excess_vol_matched_spy`. Least-bad region: risk-adjusted momentum
(momentum_252_21/vol_63), top-50 of top-500, gate on --
`mom_over_vol63_uni500_k50_gate_on`: cagr=0.2425, mdd=-0.2704, hit=0.6032,
excess_vs_spy=-0.1637. Full 16-row table in the progress log
(2026-09-10 entries) and the ledger.

### M1 single-cell -- daily27 (universe_top_n=500, top_k=50, gate on)

Real cell: validation IC mean 0.063 (all 11 quarterly refits positive),
cagr_recent_net=0.035, mdd=-0.185, hit_rate_weekly=0.548, vs. rule baseline
(best M0 cell) 0.337 -- fails `ml_must_beat_rule_baseline` badly (the
LightGBM model's return is roughly a tenth of the simple momentum rule's,
though its drawdown is much smaller). Placebo (label-shuffled): mean
validation IC = 0.0011 (clean, |IC| << 0.02 -- no leakage).

### M1 single-cell -- alpha158 (universe_top_n=500, top_k=50, gate on)

**Blocked on memory, not yet run for real.** First attempt (chained with
its placebo, both under `run_capped.sh --mem 1.8G`) was OOM-killed by the
kernel memcg at 08:47:20 UTC while loading the 154-column alpha158+regime5
feature panel (anon-rss 1.83GB at the 1.8G cap, `CONSTRAINT_MEMCG`) --
alpha158 is ~6x daily27's 26 columns. Fix (commits `07051aa`, `f511772`):
years-scoped feature load (2022-2026 instead of all 2016-2026),
`LightGBMRankStrategy` gained optional `num_threads`/`max_bin` (Track M's
`ValidationSelectedLightGBMStrategy` now always passes `num_threads=2,
max_bin=63`), `build_weight_schedule` now frees each period's panel
slice/fitted model explicitly, and a new `max_periods` dry-run mode to
measure peak RSS on one quarter before committing to the full 11-quarter
run. Dry-run result and (if it fits) the real cell's numbers: **to be
appended once they land.**

### Two-stage cell -- pre-filter top-100 of top-500 by momentum_252_21/vol_63,
daily27 LightGBM model ranks those 100, holds top 50, gate on

Rule twin: M0b's `mom_over_vol63_uni500_k50_gate_on` (cagr=0.2425).

Real cell: 11 quarterly refits, validation IC mean 0.0633 (all 11 quarters
positive: 0.0639, 0.0697, 0.028, 0.1001, 0.0424, 0.0411, 0.1171, 0.0055,
0.104, 0.0793, 0.045), cagr_recent_net=0.1038, mdd=-0.2217,
hit_rate_weekly=0.6032, vs_rule_baseline=0.2425 -- fails
`ml_must_beat_rule_baseline` (about 43% of the rule twin's return) but the
IC is meaningfully higher and more consistent than the plain daily27 M1
cell above, and drawdown is much smaller than the rule twin's. Placebo
(label-shuffled): mean validation IC = 0.0011 (clean).

### Honest read so far

No Track M candidate clears `all_gates_pass`. Every ML cell's validation
IC is real (placebos clean at ~0.001, nowhere near the pre-fix leaked
0.21), but none beats its rule baseline on realized CAGR -- the rule
cells' raw momentum has more return but far worse drawdown/vol-matched-SPY
excess; the ML cells cut drawdown substantially but at a large cost in
CAGR. `cagr_excess_vol_matched_spy` is the binding gate across every cell
tried so far, rule or ML.
