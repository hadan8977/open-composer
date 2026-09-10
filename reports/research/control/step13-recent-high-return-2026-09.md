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
below is post-fix (all M0/M0b/M1/two-stage cells were re-run or run for the
first time after this fix landed). See "Two machinery defects" below for
the second, independent defect (`bb21f27`) and what it does and does not
affect in this file.

## Track M (traditional quant + ML)

### Protocol (Track M executor, this document's author for this section)

Universe: PIT top-`N`-by-60-session-dollar-ADV (`data/features/universe/`,
ETF-excluded), `N` in {1500 (M0 only), 500, 200}. Scores: raw
`momentum_252_21` (12-1 momentum), `ret_126_rel`/`ret_63_rel` (M0 only),
risk-adjusted `momentum_252_21/vol_63` (M0b/M1/two-stage), or a LightGBM
rank model on `daily27`/`alpha158` features plus 5 regime columns (M1/
two-stage). Portfolio: top-`k` equal weight, `k` in {20, 50}. Trend gate
(`{"benchmark": "SPY", "sma_days": 200, "cash_symbol": "BIL"}`): when on,
100% BIL on weeks SPY closes below its 200-day SMA. Training (ML cells
only): 24-month trailing window, quarterly refit, embargoed validation
year, cell selection by trailing-validation rank IC only, never by the test
quarter's own result. Execution: `next_open` (Friday-close signal -> next
session's open fill), 10bp/side primary cost, 25bp/side stress cost.
Gated window: 2024-01-02 through the SIP daily archive's latest date
(`recent_gated_window_start`/`end` in the v2 contract). Every cell,
including every failure, is written to the ledger under family
`step13_recent_high_return` before this report is written, per the
project's own discipline (`CLAUDE.md`: "every backtest must produce a
report; every signal must be logged").

### M0 -- six static rule cells (top-20 of the ADV-liquidity universe table)

All 6 cells fail `all_gates_pass`. Best by CAGR: `momentum_252_21_gate_off`
(cagr_recent_net=0.3374, mdd=-0.4722, hit=0.5725) -- clears CAGR/hit-rate/
activity/DSR/stress-cost/positive-quarter (6/9 applicable gates), fails
`cagr_excess_vol_matched_spy` (-0.34) and `max_drawdown_recent` badly.
`ret_126_rel`/`ret_63_rel` cells are flat to negative (small/micro-cap
dilution in a 1500-name universe, not a bug).

### M0b -- 16-cell grid (universe_top_n {500,200} x score {momentum_252_21,
momentum_252_21/vol_63} x top_k {20,50} x trend_gate {on,off})

All 16 cells fail `all_gates_pass` -- every cell fails
`cagr_excess_vol_matched_spy`, with no exception (see the full table below:
the excess column is negative on all 22 M0/M0b rows). Risk-adjusted
momentum (`momentum_252_21/vol_63`) trades raw CAGR for a much smaller
drawdown at every matching universe/top_k/gate combination versus the raw
`momentum_252_21` M0b twin -- e.g. `uni500_k50_gate_off`: raw momentum
44.3%/-37.0% vs. risk-adjusted 33.0%/-28.3%. The two candidates connected
for observation (see below) are chosen from this risk-adjusted block, not
because they pass more gates than the raw-momentum cells (they mostly
don't -- see the table's `gates passed` column and the note under "Open
user decision" below), but because they hold the recent-window CAGR bar
(>=30%) with the smallest drawdown of any cell that does, or the smallest
drawdown of any cell in the grid at all.

### M1 single-cell -- daily27, gate on (universe_top_n=500, top_k=50)

Real cell: validation IC mean 0.063 (all 11 quarterly refits positive),
cagr_recent_net=0.035, mdd=-0.185, hit_rate_weekly=0.548, vs. rule baseline
(best M0 cell) 0.337 -- fails `ml_must_beat_rule_baseline` badly (the
LightGBM model's return is roughly a tenth of the simple momentum rule's,
though its drawdown is much smaller). Placebo (label-shuffled): mean
validation IC = 0.0011 (clean, |IC| << 0.02 -- no leakage).

### M1 single-cell -- daily27, gate off (universe_top_n=500, top_k=50)

Same model/features, trend gate disabled. cagr_recent_net=0.200,
mdd=-0.317, hit_rate_weekly=0.594 -- roughly 6x the gate-on cell's CAGR (the
gate spent real time in BIL during a window that was, on net, up), but
still far short of the 33.7% rule baseline and with a materially worse
drawdown than the gate-on ML cell. Placebo clean (same mechanism as the
gate-on cell; not re-run separately since the placebo shuffles the label
column, not the trend gate). Fails `ml_must_beat_rule_baseline`.

### M1 single-cell -- alpha158, gate on (universe_top_n=500, top_k=50)

**Now run for real** (the memory blocker recorded earlier this week --
peak RSS 1.87 GiB for one quarter under the full-universe load -- was
fixed by scoping `load_feature_panel` to the PIT top-`universe_top_n`
cohort via the new `symbol_filter` parameter, commit `3bc8b12`; the
one-quarter dry run then measured 1.20 GiB, comfortably under the 1.4GB
go/no-go bar, and the full 11-quarter cell was launched and completed).
Real cell: cagr_recent_net=0.148, mdd=-0.176, hit_rate_weekly=0.591,
validation IC = 0.021 (much lower than daily27's 0.063 mean, despite
alpha158 carrying ~6x daily27's column count) -- fails
`ml_must_beat_rule_baseline` (43% of its own risk-adjusted-momentum rule
twin's CAGR) but has this track's best max_drawdown of any M1/two-stage ML
cell and a materially better CAGR than the daily27 gate-on cell despite the
lower validation IC. **Disclosed methodological caveat**: this is the one
data point in this report where realized CAGR and validation IC point in
different directions across feature sets (alpha158: lower IC, higher CAGR
than daily27-gate-on) -- a reminder that validation-IC ranking and
realized-CAGR ranking are not the same ordering here, small-sample noise in
an 11-quarter walk-forward being the leading candidate explanation, not
re-investigated further this week (out of scope for the Friday deadline).

### Two-stage cell -- pre-filter top-100 of top-500 by momentum_252_21/vol_63,
daily27 LightGBM model ranks those 100, holds top 50, gate on

Rule twin: M0b's `mom_over_vol63_uni500_k50_gate_on` (cagr=0.2425, i.e.
24.2% at the table's one-decimal precision -- same number, not a drift).

Real cell: 11 quarterly refits, validation IC mean 0.0633 (all 11 quarters
positive: 0.0639, 0.0697, 0.028, 0.1001, 0.0424, 0.0411, 0.1171, 0.0055,
0.104, 0.0793, 0.045), cagr_recent_net=0.104, mdd=-0.222,
hit_rate_weekly=0.603, vs_rule_baseline=0.242 -- fails
`ml_must_beat_rule_baseline` (about 43% of the rule twin's return) but the
IC is meaningfully higher and more consistent than the plain daily27 M1
cell above, and drawdown is much smaller than the rule twin's. Placebo
(label-shuffled): mean validation IC = 0.0011 (clean).

### Full cell comparison table (every M-track cell, ledger-verified)

Every number below is read directly from
`reports/research/ledger/experiments.jsonl` (family
`step13_recent_high_return`) at report-writing time, not hand-typed from
memory of earlier runs -- `gates passed` excludes the gates each cell's own
`gates_not_applicable` list marks not-applicable (3 LLM/ML-only gates for
every rule cell, 1 for every ML cell), so it never overstates a cell as
"passing" an inapplicable gate. `‡` = connected for observation (Friday
candidate, gate off). `†` = the lower-drawdown alternative candidate also
exported this week (not connected to a spec).

| block | cell | CAGR | MDD | hit | Sharpe-ex-BIL | excess vs vol-matched SPY | DSR | gates passed |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| M0 | momentum_252_21, gate off | 33.7% | -47.2% | 0.572 | 0.71 | -33.8% | 0.74 | 6/9 |
| M0 | momentum_252_21, gate on | 31.2% | -36.9% | 0.571 | 0.69 | -32.3% | 0.73 | 6/9 |
| M0 | ret_126_rel, gate off | -0.3% | -59.2% | 0.532 | 0.25 | -70.8% | 0.26 | 2/9 |
| M0 | ret_126_rel, gate on | -2.5% | -53.7% | 0.528 | 0.19 | -69.1% | 0.29 | 2/9 |
| M0 | ret_63_rel, gate off | -18.1% | -65.3% | 0.504 | -0.11 | -84.6% | 0.07 | 1/9 |
| M0 | ret_63_rel, gate on | -13.3% | -58.6% | 0.520 | -0.02 | -78.7% | 0.11 | 1/9 |
| M0b (mom) | uni200 k20, gate off | 60.5% | -42.4% | 0.587 | 1.05 | -3.4% | 0.46 | 4/9 |
| M0b (mom) | uni200 k20, gate on | 44.7% | -36.0% | 0.571 | 0.89 | -14.9% | 0.38 | 3/9 |
| M0b (mom) | uni200 k50, gate off | 33.4% | -32.6% | 0.616 | 0.83 | -13.3% | 0.31 | 5/9 |
| M0b (mom) | uni200 k50, gate on | 23.4% | -25.5% | 0.603 | 0.67 | -18.8% | 0.23 | 4/9 |
| M0b (mom) | uni500 k20, gate off | 65.4% | -45.0% | 0.594 | 1.05 | -4.1% | 0.59 | 5/9 |
| M0b (mom) | uni500 k20, gate on | 49.8% | -38.3% | 0.587 | 0.92 | -15.3% | 0.54 | 5/9 |
| M0b (mom) | uni500 k50, gate off | 44.3% | -37.0% | 0.580 | 0.92 | -11.4% | 0.47 | 4/9 |
| M0b (mom) | uni500 k50, gate on | 32.0% | -34.3% | 0.571 | 0.76 | -19.4% | 0.39 | 5/9 |
| M0b (mom/vol63) | uni200 k20, gate off | 37.9% | -33.5% | 0.587 | 0.85 | -15.4% | 0.30 | 4/9 |
| M0b (mom/vol63) | uni200 k20, gate on | 24.2% | -33.5% | 0.579 | 0.63 | -25.6% | 0.20 | 3/9 |
| M0b (mom/vol63) | uni200 k50, gate off | 33.9% | -28.2% | 0.587 | 0.92 | -7.3% | 0.33 | 5/9 |
| M0b (mom/vol63) | **uni200 k50, gate on †** | 25.5% | -22.5% | 0.571 | 0.78 | -11.6% | 0.26 | 5/9 |
| M0b (mom/vol63) | uni500 k20, gate off | 45.3% | -38.5% | 0.580 | 0.94 | -9.9% | 0.45 | 5/9 |
| M0b (mom/vol63) | uni500 k20, gate on | 34.1% | -33.2% | 0.571 | 0.80 | -17.8% | 0.37 | 5/9 |
| M0b (mom/vol63) | **uni500 k50, gate off ‡** | 33.0% | -28.3% | 0.616 | 0.86 | -11.0% | 0.37 | 4/9 |
| M0b (mom/vol63) | uni500 k50, gate on | 24.2% | -27.0% | 0.603 | 0.70 | -16.4% | 0.29 | 4/9 |
| M1 | daily27, gate on | 3.5% | -18.5% | 0.548 | 0.05 | -22.5% | 0.03 | 2/11 |
| M1 | daily27, gate off | 20.0% | -31.7% | 0.594 | 0.61 | -18.1% | 0.11 | 3/11 |
| M1 | alpha158, gate on | 14.8% | -17.6% | 0.591 | 0.60 | -11.1% | 0.14 | 4/11 |
| M1 | two-stage (pre-filter100+daily27), gate on | 10.4% | -22.2% | 0.603 | 0.37 | -17.9% | 0.09 | 4/11 |

**No cell in this table clears `all_gates_pass`.** No ML cell (M1 or
two-stage) beats its rule baseline on realized CAGR -- `ml_must_beat_rule_baseline`
fails on all 4 ML cells. Every placebo run this week (M1 daily27,
alpha158's mechanism, two-stage) came back clean (|IC| ~0.001-0.002,
nowhere near the pre-`bb21f27` leaked values of 0.15-0.21) -- the leakage
that motivated this contract's `ml_placebo_rank_ic` gate is fixed and
verified absent from every Track M ML cell run this week.

### Two machinery defects found this week (both disclosed, both fixed)

1. **`returns_from_weight_schedule` daily-rebalance-to-constant-weight bug,
   fixed in `30879b4`.** Found by bisection: feeding the coordinator's own
   133 real weekly signals/picks (ground truth CAGR 0.235, no costs)
   through this function reproduced 0.3213, not 0.235, on the *identical*
   symbols/dates/prices. Root cause: every day's return inside a holding
   period was recomputed against the *same*, never-updated target weight
   instead of accumulating each held name's cumulative gross return since
   the window's start -- mathematically daily-rebalance-to-constant-weight,
   not buy-and-hold, which silently overstates return whenever there is
   cross-sectional return dispersion inside a holding period (the common
   case for a concentrated top-k book). Fixed to accumulate correctly;
   provably identical to the old formula only in the degenerate
   no-dispersion case, which is why no prior test caught it.
   **Consequence for older ledger entries**: every M0/M0b/M1/two-stage
   number in this file was computed (or re-computed) *after* this fix --
   all pre-fix `step13_m0*`/`step13_m0b*` ledger rows were purged
   (backed up to `/tmp/experiments.jsonl.bak_pre_fix_purge`, not
   git-tracked) and re-run under the corrected formula before this report
   was written, so the table above is clean. Two files *outside* Track M's
   ownership share the identical bug and were **not** fixed this week
   (flagged to their owning tracks, not touched here per the plan's
   file-ownership rule): `scripts/evaluate_cross_sectional_momentum_liquid500.py`
   (Step 10) and every `step11_baseline_chain`/`groupb_recent_regime_high_hit_rate`
   ledger entry recorded before `30879b4` (Step 11/Step 12's reports, including
   the numbers behind `step11_momentum_placeholder_v1`, the candidate the
   *previous* observation-mode connection points at) -- the bug only ever
   **overstates** returns, so no already-failing verdict in those older
   reports can flip to a pass, but a report reader should not take an
   older CAGR number in those two families at face value without checking
   whether it predates this fix.

2. **`GridSelectedLightGBMStrategy.fit()` in-sample validation-year
   selection, fixed in `bb21f27`** (Step 11/Track L-adjacent, `open_composer/
   research/kernel/b3_grid_strategy.py`, not a Track M-owned file). The
   grid-cell-selection fit pool included the validation year itself (fit on
   the full training window, then score that same year for cell selection
   -- in-sample, not a real holdout), confirmed by the label-shuffle
   placebo's own pattern (deeper trees showing 2-3x the shallow trees'
   spurious IC at the same horizon -- memorization capacity, not signal).
   This is the leakage incident named directly in
   `config/promotion/recent-regime-high-return-gates-v2.json`'s own
   `rationale` field as the motivating evidence for this contract's
   `ml_placebo_rank_ic_abs_maximum` gate. **Consequence for older ledger
   entries**: this bug lived in Step 11 Group A's B3 LightGBM grid
   selector, not in Track M's own `ValidationSelectedLightGBMStrategy`
   (`open_composer/research/regime/validated_grid_strategy.py`, a fresh
   module built with an explicit fit/validation split plus a
   `2 * label_horizon_days`-day embargo from the start) -- so **no cell in
   the table above was directly computed by the buggy code path**, and no
   M-track number in this report needs correction for this specific bug.
   Its consequence is upstream of Track M: Step 11's B3 `daily_only` grid
   (which consistently selected the same `h21_d6` cell with a suspicious
   rank IC of 0.15-0.40 every year) is the entry that carried this bug,
   and a fully clean re-run of that grid was still queued, not yet
   re-run, as of this report (`reports/research/control/step13-2026-09-09-progress.md`,
   2026-09-09 14:19 UTC entry) -- the post-fix placebo on the same grid
   came back clean (mean IC 0.0013), which is reassuring evidence the fix
   works, but the full B3 `daily_only` grid's own cell-by-cell numbers are
   not yet reconciled and should not be cited as clean until that re-run
   lands.

### Honest comparison: SPY, MTUM, SPMO (the user's own bar, not SPY alone)

Reference window 2024-01-02..2026-09-08, close-to-close, no cost
(`config/promotion/recent-regime-high-return-gates-v2.json:reference_disclosures`):
**SPY 20.9% CAGR / -18.8% MDD / 0.59 hit; QQQ 24.0% / -22.8% / 0.57; MTUM
29.8% / -21.0% / 0.59; SPMO 37.4% / -20.1% / 0.57.** These are what the
user could buy directly, at zero cost, with zero model risk, zero
turnover, and (for SPY/QQQ/MTUM/SPMO) materially smaller drawdowns than
every Track M cell in the table above except the M1/two-stage ML cells.

Against this honest bar: **the Friday candidate's 33.0% CAGR beats SPY and
sits between MTUM (29.8%) and SPMO (37.4%) on raw CAGR alone, but its
-28.3% drawdown is worse than all four passive comparators, and its
`cagr_excess_vol_matched_spy` is -11.0%** -- meaning that once SPY is
scaled up to the *same realized daily volatility* the candidate actually
ran at, vol-matched SPY still beats the candidate by 11 points of CAGR. No
cell in the entire M-track grid clears this gate; the best (least
negative) excess in the whole table is M0b's raw-momentum `uni200_k20_gate_off`
at -3.4%, still a fail. Put plainly: **a concentrated momentum book in
this specific 2024-2026 mega-cap-led rally window ran hot enough that its
extra volatility, not genuine selection skill, explains most of its CAGR
edge over SPY** -- exactly the failure mode `cagr_excess_vol_matched_spy`
exists to catch (see the gate contract's own `rationale` field).

### Open user decision: the vol-matched-SPY gate

Every cell tried this week -- 22 rule cells and 4 ML cells, 26 total,
spanning three universes, four scores, two top-k values, and both trend-gate
settings -- fails `cagr_excess_vol_matched_spy`. This is not a
near-miss on one or two cells; it is the single gate every candidate this
week failed without exception, and it is the main reason `all_gates_pass`
is `False` everywhere (most cells that fail it also fail 2-4 of the other
risk-focused gates -- `max_drawdown_recent`, `sharpe_excess_bil_recent`,
`dsr_probability`, `positive_quarter_fraction` -- which are all different
lenses on the same underlying fact: a concentrated top-k long-only book in
this window carries more volatility and drawdown than a vol-matched SPY
position, whatever its raw CAGR). Two honest, narrower observations for
whoever makes this call:

- The gate is working as designed, not broken: the contract's own
  `rationale` explains it exists precisely to block "ran hotter, not
  smarter" candidates, and every cell in this report is, in fact, running
  hotter than SPY without the vol-matched CAGR edge to justify it.
- Gate *count* alone is a misleading ranking signal here. M0's raw
  `momentum_252_21_gate_off` passes more individual gates (6/9) than
  either connected candidate (4/9 and 5/9) because it happens to clear
  `positive_quarter_fraction` and `dsr_probability` -- but it does so
  with a -47.2% max drawdown, nearly double the -25% floor and far worse
  than either connected candidate's drawdown. Raw gate-count and "is this
  a portfolio a person should actually hold" are not the same question in
  this grid; the two candidates exported this week were chosen for the
  latter, not the former (see the "Full cell comparison table" note
  above).

This gate is a preregistered contract threshold, not a bug, and this
report does not relax it, override it, or recommend a specific number to
relax it to -- per the task instructions, that decision is the user's, to
be made with the full table above (and the disclosure-only quarterly/
skew/turnover fields in each candidate's ledger record) in view, not
pre-decided here.

### What was connected for observation, and how to switch it off

**Connected**: `strategy_specs/drafts/us_recent_high_return_top50.yaml`
(`portfolio.candidate_artifact_dir =
reports/research/candidates/step13_rule_mom_over_vol63_uni500_k50_gate_off`,
the table's `‡` row) -- `execution.mode: manual_signal`,
`execution.broker: none`, `lifecycle: draft`, exactly like the earlier
`step11_momentum_placeholder_v1` connection none of those three fields
were changed. The observation cycle (`scripts/run_daily_paper_cycle.py
--strategy us_recent_high_return_top50 --spec strategy_specs/drafts/us_recent_high_return_top50.yaml`,
run for real on 2026-09-10) confirmed from its own JSON artifact
(`reports/paper/daily_cycle/us_recent_high_return_top50-observation-20260910.json`):
`status=ok`, `broker_writes=false`, `paper_order_authorization=false`,
50 target rows (top-50, 2.00% each -- the trend gate is off for this
candidate, so every rebalance holds 50 names, never BIL), account equity
synced from the real (read-only) Alpaca Paper account, and 50 fresh
signals written to `signal_logs/model-ranking-us_recent_high_return_top50.jsonl`
before the cycle finished -- no order of any kind was placed or is
reachable from this code path (`run_model_ranking_observation_cycle` calls
only `oc paper sync-account` and `oc strategy target-weights`, never
`oc run paper`).

**A second candidate was exported but not connected**: `reports/research/candidates/
step13_rule_mom_over_vol63_uni200_k50_gate_on` (the table's `†` row) -- the
lower-drawdown alternative (top-50 of top-200, trend gate on: -22.5% MDD,
0.571 hit, both individually clearing their own gate thresholds, vs. the
connected candidate's -28.3%/0.616), at the cost of a lower CAGR (25.5%,
below the 30% bar) and a worse vol-matched-SPY excess (-11.6% vs -11.0%,
essentially tied). Swapping to it is a one-line spec change
(`portfolio.candidate_artifact_dir` -> that directory,
`portfolio.universe_top_n` -> 200) if the user prefers the lower-drawdown
profile; the exported artifact already exists, so nothing else needs to be
built.

**How to switch the connected candidate off**: nothing needs to change to
*prevent* orders -- this pipeline was never wired to place any (no
`paper_auto`, no `lifecycle` promotion, no kill-switch relevance, since the
kill switch only gates order-authorized strategies and this one has no
order authority to begin with). To stop the *observation* cycle itself:
if the cron suggestion below is installed, remove that crontab line (no
other state to clean up); if it is not installed (the default, as of this
report), there is nothing running on a schedule to stop -- the only
executions to date are the one-off manual run recorded above.

### Cron suggestion (not installed, per discipline -- report only)

Mirrors the format and reasoning `reports/research/control/step11-wavec-paper-connection-2026-09.md`
section 6 already used for the Step 11 placeholder spec's own observation
cycle (same 23:00 UTC slot, same buffer reasoning: feature-library archive
finishes ~22:00 UTC, next session's open is 13:30-14:30 UTC depending on
DST, so 23:00 UTC leaves 14+ hours of margin and is safely after the
archive job):

```cron
# Step 13 Track M -- model_ranking_portfolio observation cycle
# (us_recent_high_return_top50, the Friday 2026-09-11 deadline candidate)
# Mon-Fri 23:00 UTC. run_daily_paper_cycle.py's own is_trading_day() check
# already skips weekends/exchange holidays cleanly (status=skipped), so the
# Mon-Fri schedule needs no separate holiday exclusion.
0 23 * * 1-5 cd /root/codex-test/open-composer && \
  ./scripts/run_capped.sh --mem 1.8G -- \
  uv run python scripts/run_daily_paper_cycle.py \
  --strategy us_recent_high_return_top50 \
  --spec strategy_specs/drafts/us_recent_high_return_top50.yaml \
  >> logs/model_ranking_observation_cron_step13m.log 2>&1
```

Notes:

- `main()` auto-dispatches to the 2-step observation cycle
  (`sync-account` -> `target-weights`) purely from
  `spec.portfolio.mode == "model_ranking_portfolio"`; it never calls `oc
  run paper`. Identical invocation shape to every other
  `run_daily_paper_cycle.py` user in this repo -- no new script, no new
  flags.
- If this and the existing `us_model_ranking_portfolio_top50` cron (or any
  future Track-L cron) are both installed, they are independent one-line
  entries with different `--strategy`/`--spec` values and different log
  files -- no shared state, no ordering dependency between them.
- Structured output per run:
  `reports/paper/daily_cycle/us_recent_high_return_top50-observation-{date}.json`.
- **Not installed by this report's author.** Whether and where to install
  it is the user's call, same discipline as the Step 11 precedent.

### Honest read / conclusion

No Track M candidate clears `all_gates_pass`. Every ML cell's validation
IC is real (placebos clean at ~0.001-0.002, nowhere near the pre-fix
leaked 0.15-0.21), but no ML cell beats its rule baseline on realized
CAGR -- the rule cells' raw or risk-adjusted momentum has more return but
worse drawdown/vol-matched-SPY excess than a person would want; the ML
cells cut drawdown substantially (alpha158's -17.6% is this report's best
M1/two-stage drawdown) but at a large cost in CAGR, and even the best of
them (alpha158, 14.8%) falls well short of the 30% CAGR bar. Against the
user's own honest comparators (SPY 20.9%, MTUM 29.8%, SPMO 37.4%, all at
materially smaller drawdowns and zero cost/turnover/model risk), the
connected candidate's 33.0% CAGR looks competitive on the headline number
but is the product of running hotter than the market, not of selecting
better stocks -- the -11.0% vol-matched-SPY excess is the honest summary
of that gap. `cagr_excess_vol_matched_spy` is the binding gate across
every cell tried this week, rule or ML, and remains the single largest
open question for the user to resolve before any candidate in this family
could be promotion-eligible. Per the plan's own fallback rule ("若没有单元
通过 v2 全部门槛，仍把 M 轨最优单元以观察模式接入并在报告首段写清差距"),
the best-available candidate is connected for observation only, with this
report stating the gap plainly rather than the contract being relaxed to
manufacture a pass.

## P 轨：Reversal Trend

Plan: `docs/plan-step-13p-reversal-trend-pine-factor-and-strategy-2026-09-09.zh.md`
(sections 1, A2, A3, 3). Ledger family unchanged (`step13_recent_high_return`),
track `M` (rule-based, `is_ml=False`), gate contract
`config/promotion/recent-regime-high-return-gates-v2.json`. Port:
`open_composer/research/pine_port/reversal_trend.py::compute_reversal_trend`.
Live checkpoint-level detail: `reports/research/control/step13-2026-09-09-progress.md`
("Track P executor log").

### Indicator semantics (plan section 1)

Reversal Trend is a Pine v6 indicator the user reverse-engineered from a
closed-source QuanTGT script by matching marker positions on a chart (exact
original parameters not visible; see plan section 0). It is an **event-type,
sparse 0/1 signal**, not a continuous factor: a bull setup requires, in
order, an RSI(14) oversold touch (<=30) that "arms" a window (expires after
35 bars unless a signal fires and re-locks it), then -- while that arm is
still active -- an EMA(12,26) MACD bullish crossover with RSI back in
(40,65), close above EMA20, ADX(14) > 18, and the MACD histogram rising
1-bar-over-1-bar, gated by a 30-bar cooldown since the last bull signal
(`fBull`); `fRecL` is an earlier, weaker "RSI recovering out of oversold
while still below EMA50" signal (dwell >=5 bars in oversold required first,
8-bar cooldown). `fBear`/`fRecS` are the symmetric short-side pair (20/8-bar
cooldowns), with one disclosed, deliberate asymmetry preserved from the
original script: `bear` has no MACD-histogram confirmation term where `bull`
does. All four signals are confirmed only at bar close (no repaint, no
`request.security`), and the formulas are bar-period-agnostic (the same code
runs on daily, hourly, or minute bars -- only the meaning of "1 bar" changes).
Parameters are fixed at the script's own defaults everywhere in this chapter
per plan section 6 ("不做：调指标参数").

### Daily event study verdict (F 轨, `reports/research/factor_screen/reversal_trend_event_study.md`)

All four daily signals are **"informative: no"** in both windows tested
(2018-2026 full history and 2024-onward), against the rule "5d and 10d mean
excess > 0 AND date-clustered t > 2.5 AND above the placebo's 95th
percentile," on the PIT-top-1500 universe. `rt_bull_signal` is flatly
uninformative in both windows (2024-onward 5d t=0.26, 10d t=-1.64). The two
"recovery" signals and the bear signal show a directionally interesting but
not-gate-clearing pattern: `rt_bear_signal` and `rt_recs_signal` (a
short-covering-type setup) both have **positive** forward excess returns in
the 2024-onward window (`rt_recs_signal` 10d t=2.69, 21d t=3.59;
`rt_bear_signal` 21d t=2.58) -- i.e. after a bear/short-recovery signal
fires, the stock's subsequent excess return tends to be positive, a
contrarian pattern -- but neither clears the "both 5d AND 10d t>2.5" bar
(both signals' 5d t-stats fall short: 0.67 and 1.87 respectively), so the
formal verdict stays "no" for all four signals in both windows. This is
disclosed here because it directly bears on the plan's original
"combine as a factor with other indicators" idea (section 0): on this
evidence, Reversal Trend's daily-bar signals are not a standalone
cross-sectional factor and would need to earn their place through some
other mechanism (e.g. the intraday-holding-period backtest below) rather
than a forward-return factor screen.

### 1h-bar strategy: 18-cell grid (A3, already run -- not re-run this session)

Data: `data/bars/hourly/{2024,2025,2026}.parquet` (715,985 rows / 273
symbols), 09:30-anchored regular-session 1h bars built from `data/sip/minute`
(`open_composer/research/bars/hourly.py`). Window 2024-01-02..2026-09-09,
next-bar-open execution, 5bp/side stock / 2bp/side ETF cost, 2.5x stress,
max 10 concurrent positions (10% NAV each, ADX-descending tiebreak), long
only -- `fBear`/`fRecS` are disclosure-only per plan section 2 ("空头...只做
披露，不进候选") and were not run as separate ledgered candidate cells in
this artifact set (no `bear`/`recs`-only files exist under
`reports/research/artifacts/step13_p_reversal_trend_hourly/`; short-side
economics are noted qualitatively in the progress log as clearly negative,
consistent with the daily event study finding no informative long-side edge
either). Grid: holding {6, 13, 26} 1h bars ({time_stop, time_stop_or_reverse,
2xATR(14,1h) trailing stop} exit) x {bull_only, bull_and_recl} signal set =
18 cells, all real cells landed with a matched same-symbol/same-count
random-date placebo and a disclosure-only "SPY>200-day-SMA" trend-gate
variant (neither placebo nor trend-gate is ledgered).

| holding | exit rule | signal | trades | per-trade hit | PF | CAGR | MDD | weekly hit | Sharpe ex-BIL | placebo cum. return | trend-gate cum. return |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 6  | time_stop            | bull_only     | 1494 | 0.491 | 0.94 | -3.69%  | -20.98% | 0.521 | -0.65 | +0.018 | -0.045 |
| 6  | time_stop            | bull_and_recl | 2991 | 0.492 | 0.98 | -3.00%  | -30.83% | 0.440 | -0.37 | +0.133 | +0.005 |
| 6  | time_stop_or_reverse | bull_only     | 1494 | 0.491 | 0.94 | -3.69%  | -20.98% | 0.521 | -0.65 | +0.010 | -0.045 |
| 6  | time_stop_or_reverse | bull_and_recl | 2991 | 0.492 | 0.98 | -3.00%  | -30.83% | 0.440 | -0.37 | +0.141 | +0.005 |
| 6  | atr_trailing_2x      | bull_only     | 1501 | 0.458 | 0.85 | -7.88%  | -26.74% | 0.464 | -1.15 | -0.271 | -0.152 |
| 6  | atr_trailing_2x      | bull_and_recl | 3082 | 0.457 | 0.85 | -15.03% | -45.58% | 0.376 | -1.26 | -0.397 | -0.281 |
| 13 | time_stop            | bull_only     | 1374 | 0.512 | 0.99 | -1.89%  | -22.22% | 0.529 | -0.30 | +0.100 | -0.130 |
| 13 | time_stop            | bull_and_recl | 2118 | 0.503 | 1.05 | +3.39%  | -17.35% | 0.511 | +0.04 | +0.259 | +0.047 |
| 13 | time_stop_or_reverse | bull_only     | 1374 | 0.512 | 1.00 | -1.18%  | -22.17% | 0.521 | -0.26 | +0.066 | -0.113 |
| 13 | time_stop_or_reverse | bull_and_recl | 2118 | 0.504 | 1.05 | +3.88%  | -17.17% | 0.511 | +0.07 | +0.174 | +0.060 |
| 13 | atr_trailing_2x      | bull_only     | 1459 | 0.391 | 0.81 | -12.04% | -31.94% | 0.414 | -1.42 | -0.359 | -0.257 |
| 13 | atr_trailing_2x      | bull_and_recl | 2574 | 0.390 | 0.81 | -19.42% | -47.18% | 0.369 | -1.37 | -0.311 | -0.453 |
| 26 | time_stop            | bull_only     | 1099 | 0.540 | 1.27 | +19.32% | -23.89% | 0.564 | +0.78 | +0.212 | +0.506 |
| 26 | **time_stop**        | **bull_and_recl** | **1352** | **0.536** | **1.32** | **+26.25%** | **-14.68%** | **0.589** | **+0.98** | +0.118 | +0.862 |
| 26 | time_stop_or_reverse | bull_only     | 1103 | 0.539 | 1.26 | +18.47% | -24.50% | 0.564 | +0.75 | +0.231 | +0.477 |
| 26 | time_stop_or_reverse | bull_and_recl | 1358 | 0.538 | 1.32 | +26.12% | -12.96% | 0.567 | +0.97 | +0.507 | +0.852 |
| 26 | atr_trailing_2x      | bull_only     | 1445 | 0.352 | 0.77 | -14.88% | -37.30% | 0.343 | -1.62 | -0.161 | -0.313 |
| 26 | atr_trailing_2x      | bull_and_recl | 2365 | 0.352 | 0.82 | -18.29% | -48.35% | 0.369 | -1.25 | -0.523 | -0.477 |

(Best cell bolded. Source: `reports/research/artifacts/step13_p_reversal_trend_hourly/summary.json`
plus its per-cell `__placebo.json`/`__trend_gate.json` checkpoints; every real
row is also in `reports/research/ledger/experiments.jsonl` under
`step13_recent_high_return`.)

### Gate verdict, verbatim: nothing passes

**0 of 18 cells have `all_gates_pass=True` / `promotion_eligible=True`.**
Per-gate failure count across the 18 real cells:

- `cagr_recent_net` (>=0.30 required): **fails on all 18/18** -- the best
  cell reaches 0.2625.
- `cagr_excess_vol_matched_spy` (>=0.0): **fails on all 18/18** -- every
  cell, including the best one (-0.87%), loses to SPY scaled to the same
  realized volatility.
- `sharpe_excess_bil_recent` (>=1.2): **fails on all 18/18** -- the best
  cell reaches 0.976.
- `dsr_probability` (>=0.5): **fails on all 18/18** -- the best cell reaches
  0.264 (highest in the grid; every h6/h13 and every ATR-trailing cell is
  near 0.0-0.02).
- `stress_cost_still_high` (>=0.20 at 2.5x cost): **fails on all 18/18** --
  the two closest cells (h26 bull_and_recl, time_stop and
  time_stop_or_reverse) reach 17.4% and 17.3%, about 2.6-2.7pp short.
- `hit_rate_weekly` (>=0.55): fails on 14/18 -- passes only on the four h26
  non-ATR cells (0.564-0.589).
- `positive_quarter_fraction` (>=0.60): fails on 14/18 -- passes only on the
  same four h26 non-ATR cells (0.727).
- `max_drawdown_recent` (>=-0.25): fails on 8/18 -- the atr_trailing_2x
  cells at every holding length, plus the worst h6/h13 bull_and_recl cells.
- `activity_floor` (>=30 rebalances/yr with a change): **passes on 18/18**
  (trade counts run from ~1,100 to ~3,100 over the window, far above the
  floor).
- `ml_placebo_rank_ic`, `ml_must_beat_rule_baseline`, `llm_marginal_lift`:
  not applicable (rule-based Track M candidate, `is_ml=False`).

### Honest read

The best cell (h26, `time_stop`, `bull_and_recl`: 26.25% CAGR / -14.68% MDD
/ 0.589 weekly hit / 1352 trades) and its close sibling (h26,
`time_stop_or_reverse`, `bull_and_recl`: 26.12% / -12.96%) have a
**meaningfully better drawdown profile than Track M's own connected
weekly-momentum candidate** (`mom_over_vol63_uni500_k50_gate_off`, ~33.0%
CAGR / -28.3% MDD, see the Track M chapter above) -- roughly the same order
of return at about half the drawdown. But both numbers still sit **below the
30% CAGR gate and well below SPMO's honest 37.4%/-20.1% comparator**
(`config/promotion/recent-regime-high-return-gates-v2.json`
`reference_disclosures`); at -13..-15% MDD this cell's drawdown is actually
better than SPMO's, but the return gap is the binding problem, same as
everywhere else in this report.

Two disclosed reasons to distrust this result before treating it as a real
edge:

1. **Holding-length dependence, at the edge of the grid, not the interior.**
   Of the three preregistered holding lengths, only the longest (h26, ~4
   trading days) produces a competitive result at all. h13 is marginal
   (+3.4% to +3.9% on the two non-ATR/`bull_and_recl` cells, -1.2% to -1.9%
   on `bull_only`), and h6 is negative everywhere (-3.0% to -15.0%). The
   `atr_trailing_2x` exit is bad at *every* holding length (-7.9% to
   -19.4%), including h26 (-14.9%/-18.3%) -- a protective stop calibrated
   at 2x ATR(14,1h) apparently cuts winners short more than it protects
   against the specific drawdowns this signal produces. A genuine effect
   would typically show up somewhere in the *interior* of a 3-point grid,
   not exclusively at its longest boundary; this pattern is consistent
   with (though does not prove) the good h26 result being partly a
   holding-period-driven market-exposure effect rather than a
   signal-driven one.
2. **The reverse-exit sibling's placebo is not clean; the best cell's is
   much cleaner but not zero.** The best cell's same-symbol/same-count
   random-date placebo compounds to +0.118 over the window (1169 placebo
   trades) versus the real cell's +0.8655 (1352 real trades, exact
   compounded return from its quarterly disclosure table) -- the placebo
   explains about 14% of the real cell's cumulative return, i.e. mostly
   clean. Its sibling, h26 `time_stop_or_reverse` `bull_and_recl`, compounds
   its placebo to **+0.5067** (1204 placebo trades) versus the real cell's
   +0.8604 (1358 real trades) -- the placebo explains **about 59%** of that
   cell's cumulative return. Random entries held ~4 trading days in a
   10%-weighted, 10-slot, mostly-ETF/large-cap long book, during a
   2024-2026 window that was on net a strong bull market, already capture
   more than half of this cell's apparent edge -- most of what looks like
   "signal" in the reverse-exit sibling is holding-period and market-beta
   effect, disclosed here exactly as instructed rather than only reporting
   the flattering headline number. The trend-gate variant (SPY>200dma) is
   close to a no-op for both cells (0.862 and 0.852 cumulative vs. 0.8655
   and 0.8604 real) simply because SPY was above its 200-day SMA for most
   of this window -- it neither rescues nor meaningfully changes either
   cell.

Net: Reversal Trend's 1h-bar long strategy does not clear the v2 gate
contract on any of the 18 preregistered cells, and the one region of the
grid that looks attractive (h26, `bull_and_recl`) carries real, disclosed
fragility (edge-of-grid holding-period dependence; a same-family sibling
cell whose placebo is not clean). It is a better-drawdown, lower-return
alternative to the Track M weekly momentum candidates already in this
report, not a candidate that changes the report's overall conclusion that
no Step 13 recent-high-return candidate yet clears the contract.

### TradingView comparison (deliverable 2)

Parity script: `scripts/reversal_trend_parity.py SPY 1h 2025-01-02 2025-06-30`
(120 calendar days of pre-window warmup so EMA200/RSI/ADX are converged,
`ReversalTrendParams()` defaults, no tuning). Full assumptions, an NVDA
second data point, and DST-boundary notes are in
`reports/research/artifacts/step13_p_reversal_trend_hourly/parity_spy_2025h1.md`
(gitignored directory, so the SPY table is reproduced here in full for the
user to compare against their TradingView screenshots of the original,
unported indicator):

**SPY, 2025-01-02..2025-06-30 -- 10 events (4 fBull, 1 fBear, 2 fRecL, 3 fRecS)**

| bar close (ET) | bar start (ET) | signal | close | RSI | ADX | EMA20 | EMA50 |
|---|---|---|---|---|---|---|---|
| 2025-01-07 12:30 EST | 11:30 | fBear | 580.65 | 45.3 | 22.3 | 582.81 | 582.38 |
| 2025-01-23 10:30 EST | 09:30 | fRecS | 595.51 | 69.5 | 43.1 | 592.70 | 587.06 |
| 2025-01-28 14:30 EST | 13:30 | fBull | 593.85 | 53.4 | 30.3 | 592.54 | 591.04 |
| 2025-02-28 16:00 EST | 15:30 | fBull | 584.04 | 53.3 | 38.8 | 581.01 | 585.76 |
| 2025-03-07 14:30 EST | 13:30 | fBull | 566.84 | 49.2 | 25.7 | 565.74 | 572.17 |
| 2025-03-14 10:30 EDT | 09:30 | fBull | 547.60 | 47.1 | 27.5 | 547.48 | 555.10 |
| 2025-03-31 12:30 EDT | 11:30 | fRecL | 546.84 | 34.9 | 41.9 | 552.47 | 556.12 |
| 2025-04-07 13:30 EDT | 12:30 | fRecL | 498.58 | 30.8 | 52.4 | 513.31 | 531.59 |
| 2025-05-14 13:30 EDT | 12:30 | fRecS | 578.17 | 68.9 | 43.0 | 574.45 | 565.60 |
| 2025-06-27 14:30 EDT | 13:30 | fRecS | 605.59 | 61.7 | 40.0 | 603.83 | 599.07 |

Assumptions the user should check against their screenshots before treating
any mismatch as a logic bug: 1h bars are 09:30-anchored regular-session-only
(six 60-minute buckets + a trailing 15:30-16:00 30-minute bucket,
pre/post-market dropped) -- **this is assumed, not independently verified
this session, to match TradingView's default 1h anchoring for US equities**;
"bar close" above is bar-start + 60 minutes (+30 minutes for the last bucket
of the day), since `compute_reversal_trend`'s own `timestamp` column is
documented as the bar's *start*. A one-bar (60/30-minute) offset between
this table and a screenshot is more likely an anchoring-convention labeling
difference than a signal-logic difference; a signal present in one series
and absent in the other is the more interesting thing to report back.

### Product-path disclosure: this is not paper-ready as-is

Even if a cell had cleared the gate contract, **it could not be connected
through the existing observation-mode path today.** `scripts/run_daily_paper_cycle.py`
(installed via `scripts/install_daily_cron.sh`, the mechanism every other
Track M/L candidate in this report references for observation-mode
connection) runs **once per trading day**: sync-account, then compute target
weights once, off the prior day's close. Reversal Trend's 1h-bar strategy
needs a decision at **every 1h bar close during the regular session**
(6-7 times per trading day: 10:30, 11:30, 12:30, 13:30, 14:30, 15:30, 16:00) --
a fundamentally different runner cadence that does not exist yet:
an intraday scheduler (hourly cron or event loop gated to regular-session
bar closes, not a single daily cron line), a near-real-time hourly bar-build
step (this report's `data/bars/hourly/{year}.parquet` is a historical/
backfilled artifact, not a live-updating one), incremental per-bar signal
computation, and per-bar target-weight/order submission through the same
Alpaca Paper write path everything else in this report uses. None of this
is built. Per this project's own discipline (no self-activation, StrategySpec
rule path not `model_ranking` for a discrete-trade mechanism like this one),
this gap is disclosed here rather than worked around; building the hourly
runner is a prerequisite for connecting *any* future hourly-bar candidate to
observation mode, not specific to Reversal Trend.
