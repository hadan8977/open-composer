# Decision record -- h20260924_01_etf_dip_reversion

Status: **Final -- partial verdict, closed on Stage A evidence (2026-09-24).
Stage B (T1, QQQ/SPY minute bars) is deferred by decision, not run and not
implemented.** Everything below is real, executed output (Stage A), not a
projection. See "Decision" for why Stage A alone is sufficient to close the
sleeve-level question without T1.

## Path

`etf_dip_reversion_screen` -- the single preregistered path, 24 candidates
(6 published dip-reversion rules x 2 signal underlyings x 2 execution
instruments), reusing the frozen giants-sweep protocol (windows, costs,
placebos, G1-G5) unchanged, plus a trade-level research-admission rule for
the 12 1x T1 cells and a supplementary 2016-2026 persistence table.

## Decision

**Partial: stop the sleeve-level path; hold the D1 signal-level thread
pending a reopening trigger (see `reopen_if` below), rather than continue
either one on the current evidence.**

- **Sleeve-level: refuted under the frozen giants-sweep protocol -- stop.** T0
  (same-close fill at the official close) is an unexecutable upper bound for
  T1 (MOC fill at the same official close, decided from an earlier, noisier
  15:50 ET proxy) -- T1 can only be equal to or worse than T0 on execution
  quality for any given trade, and cannot manufacture the ~3-18 points of
  CAGR or ~0.5-1.3 points of Sharpe every one of the 24 candidates is short
  of G1/G1' at T0. 0/24 candidates pass G1 or G1' at T0: best anchor CAGR is
  47.1% (d1_spy_3x) against the 50% G1 bar, best anchor Sharpe is 1.50
  (d4_spy_3x) against the 2.0 G1' bar, and the deflated Sharpe of that best
  T0 cell given 24 trials is 0.92. Since G4 requires G1/G1' to also hold at
  20bp stress, and neither holds at the lighter 10bp cost, G4 fails
  everywhere too, so no candidate can pass all_gates at T1 regardless of
  what T1 shows -- Stage B cannot change the sleeve verdict, only refine how
  large the shortfall is. This is a valid inference from Stage A alone, not
  a skipped step: running Stage B to re-confirm a bar that is already
  mathematically unreachable would spend a memory-constrained capped-job
  slot on a foregone conclusion.
- **Signal-level: D1 (IBS-Algotradekit, with the EMA trend filter) shows a
  real effect at T0/T2**, distinct from the sleeve-level gate failure --
  see "D1 signal-level evidence" below. **D1's formal research-admission
  verdict stays pending T1**, since research admission was preregistered
  specifically at T1 (the only realistic/executable timing) and was never
  evaluated at T0/T2 in the original design; the T0/T2 numbers below are a
  new, explicitly-labeled diagnostic computation, not a substitute for the
  preregistered T1 test.
- Best cells by anchor CAGR/DD/Sharpe (T0, all short of G1/G1'): **d1_spy_3x
  CAGR 47.1%, maxDD -30.6%, Sharpe 1.42** (best anchor CAGR of all 24, still
  under the 50% G1 bar); **d4_spy_3x CAGR 20.9%, maxDD -6.2%, Sharpe 1.50**
  (best anchor Sharpe of all 24, still under the 2.0 G1' bar); d1_qqq_3x
  CAGR 36.0%, maxDD -27.0%, Sharpe 0.88 (third-best CAGR, same 3x-leverage
  pattern as d1_spy_3x). All other 20 cells score lower on both axes.

Pre-backtest dossier (direction-review, external-brief, hypotheses,
search-space, candidate-manifest, cost-contract, data-feasibility, source
cards) is complete and passed `oc research direction-check` and
`oc research iteration validate --stage pre-backtest`. The dedicated engine
(`scripts/run_h20260924_01_etf_dip_reversion.py`) and its test suite
(`tests/test_run_h20260924_01_etf_dip_reversion_script.py`, 34 tests) are
written, and pass (`uv run ruff format`, `uv run ruff check`,
`uv run pytest -q`, all clean).

### Stage A results (executed 2026-09-24, `--stage a`, under
`scripts/run_capped.sh --mem 1.3G`)

24/24 candidates ran clean for both T0 (same-close, unexecutable upper
bound) and T2 (next-open) diagnostic timings. Full detail:
`stage_a_summary.parquet` (per-cell metrics/gates), `trial-ledger.jsonl`
(every trade), `stage_a_placebo.parquet` (all placebo-seed Sharpes),
`persistence-2016-2026.parquet`, `split-dividend-check.json`, `stage_a.json`.

- **0 of 24 candidates pass all_gates at T0; 0 of 24 pass at T2.** G1
  (anchor CAGR>=50%, maxDD>=-35%) and G1' (Sharpe>=2.0, CAGR>=30%) fail on
  every cell at the primary 10bp cost -- best anchor CAGR is 47.1%
  (d1_spy_3x, just under the 50% G1 bar) and best anchor Sharpe is 1.50
  (d4_spy_3x, well under G1''s 2.0 bar) -- so G4 (the same test at 20bp
  stress) is trivially false everywhere too, since it can only pass where
  G1/G1' already passed at 10bp. This matches
  `dir:giants_sweep_published_etf_rules`'s prior (0/24 published ETF rules
  cleared this identical bar), now confirmed for the IBS/Connors family
  specifically, at both diagnostic timings, before Stage B is even run.
- G2 (holdout Sharpe>=1.0, holdout CAGR>0) passes on 8/24 cells at T0 (D3/
  D4/D5/D6's 3x QQQ variants and several SPY variants), showing decent
  recent-window (2026 Jan-Sep) risk-adjusted performance despite failing the
  CAGR-based G1 bar -- expected for low-time-in-market mean-reversion rules.
- G3 (placebo beat frac <=10%) passes reliably on D1 (all 4 D1 cells) but
  is inconsistent-to-failing on D2-D6 -- D1 (IBS with an EMA trend filter)
  is the only rule that clearly beats its own random-entry and
  calendar-shift placebos; the others' apparent edge is not clearly
  distinguishable from generic trend/seasonal placebo behavior at T0.
- **Deflated Sharpe of the best T0 cell given 24 trials: 0.92**
  (d4_spy_3x, raw anchor Sharpe 1.50). This is the *unexecutable upper
  bound*'s own multiple-comparisons-adjusted confidence, before Stage B's
  realistic T1 timing (which the research-admission rule requires retain
  >=60% of T0's gross edge) is even applied -- not a passing bar by itself
  (no threshold was preregistered for it; it is context, per the brief),
  but it does not leave much room for T1 to look better than T0.
- **Split/dividend check: 5 flags, all TQQQ/UPRO overnight jumps of
  -20% to -31% in March 2020 (2020-03-09/12/16/16/18).** Reviewed: these
  land exactly on the COVID-crash volatility spike and are consistent with
  ordinary (if extreme) 3x-leveraged-ETF daily moves during that week, not
  an unadjusted split/dividend artifact. No corporate-action adjustment
  issue found for QQQ/SPY/TQQQ/UPRO over 2022-2026, the window this
  iteration's windows actually span.
- **2016-2026 persistence table (daily T0, context only, not an admission
  criterion):** D1 is the standout for cross-symbol consistency -- positive
  mean annual return on all four symbols (QQQ +12.5%/yr, SPY +9.7%/yr,
  DIA +6.2%/yr, IWM +7.6%/yr) with 82-91% of the 11 years positive, at a
  low 7-9 trades/year. D2 (no trend filter) is negative on 3 of 4 symbols
  (DIA -5.6%, IWM -4.1%, SPY -5.2%/yr; only QQQ positive at +3.6%/yr) with
  as few as 0% of years positive (SPY) at a much higher 36-41 trades/year --
  consistent with Pagonidis's own point that the raw IBS effect needs a
  trend filter or selective use, not blind application. D3-D6 show small
  (1-3%/yr) average returns with mixed year-positive rates (36-82%) at low
  trade counts (2.5-5.4/year) -- economically marginal at this frequency
  even before costs are stressed further.

### D1 signal-level evidence (T0/T2 diagnostic research-admission statistics)

Computed 2026-09-24 specifically for this verdict, using the preregistered
research-admission definitions (mean net return per trade in select and
holdout at the 10bp primary cost, trade-level t-statistic over select+
holdout, and the 60-seed random-entry-timing placebo) applied to D1's two
1x cells at T0 and T2 -- the two timings Stage A actually ran. This is a new
diagnostic computation, not part of the original Stage A script output; raw
numbers are in `d1-research-admission-t0-t2.json` in this directory (all 4
D1 cells, 1x and 3x, both timings).

| cell | timing | mean/trade select | mean/trade holdout | trade t-stat | placebo percentile | beats p95 |
|---|---|---:|---:|---:|---:|---|
| d1_qqq_1x | T0 | +1.91% | +0.27% | 2.12 | 58.3 | no |
| d1_qqq_1x | T2 | +1.54% | -1.02% | 1.45 | 63.3 | no |
| d1_spy_1x | T0 | +2.13% | +0.96% | 2.99 | 91.7 | no |
| d1_spy_1x | T2 | +2.11% | +0.59% | 2.93 | 86.7 | no |

D1-SPY (1x) is the strongest cell: positive mean net return per trade in
*both* select and holdout at *both* T0 and T2, trade-level t-statistics of
2.9-3.0 (comfortably over the 2.0 admission threshold), and a placebo
percentile of 87-92 -- close to, but short of, the strict 95th-percentile
admission bar. D1-QQQ (1x) is weaker and less stable: its T2 holdout mean
turns negative (-1.02%/trade) and its T2 t-stat drops to 1.45, under the
2.0 bar; only its T0 numbers pass the mean-positive and t-stat legs. Neither
cell clears the placebo-percentile leg at either diagnostic timing, so
neither would be admitted even if T0/T2 were the counted timing (they are
not; T1 is). This is the concrete basis for calling D1 "a real effect" (a
positive, trade-level-significant, cross-timing-consistent-on-SPY signal,
distinct from the other five rules, none of which show this combination)
while keeping its formal research-admission verdict pending T1: the
strictest leg of the preregistered test (placebo percentile) is not yet won
even at the more favorable of the two available diagnostic timings, and T1
adds proxy-based entry/exit noise on top of T0/T2's already-marginal margin
on that specific leg.

### Stage B status

**Deferred by decision, not run and not implemented.** The main session's
2026-09-24 finalization decision is to close this iteration on Stage A
evidence rather than spend a `run_capped.sh` slot confirming an
already-unreachable sleeve-level bar (see "Decision" above). Stage B's own
implementation (T1 minute-bar loading and proxy construction) remains
unwritten in `scripts/run_h20260924_01_etf_dip_reversion.py` --
`main(--stage b)` is still a stub. This is a deliberate deferral, not a
silent skip: Stage B is only needed if D1 is later used as a component
(see the registry entry's `reopen_if`). Research note for whoever
eventually implements it: `open_composer/adapters/data/sip_parquet.py::
load_sip_bars(["QQQ","SPY"], frequency="minute", start=..., end=...,
root=...)` already handles shard selection and the whole-year-vs-month-
sharded overlap (by de-duplicating on `(symbol, timestamp)`, not by
excluding the whole-year shards outright), and returns UTC timestamps --
call it once with `root="data/sip-hist"` for dates through 2022 and once
with `root="data/sip"` (its default) for 2023+, concatenate, then
`.dt.tz_convert("America/New_York")` (never a fixed EDT/EST offset) before
taking each session's 09:30-15:50 window for the proxy bar. This avoids
re-deriving shard/layout handling that already exists and is exercised
elsewhere in this repo (e.g. `scripts/run_h20260918_02_orb_etf.py`,
`scripts/cache_minute_panel.py`).

### Trial ledger note

The 24 T1 trials that the preregistered design calls for are recorded in
`trial-ledger.jsonl` as `"timing": "T1", "status": "not_run", "reason":
"dominated: T0 upper bound fails G1/G1'"` entries (one per candidate) rather
than left silently absent, so a reader of the ledger sees an explicit,
reasoned non-execution instead of an unexplained gap.

## Reason

This dossier exists because the owner asked for an evaluation of
fmzquant/strategies' US-equity content, and the only family in it with a
published mechanism and a multi-year post-publication record is short-term
ETF dip reversion (see external-brief.md and hypotheses.md for the full
mechanism and prior-evidence discussion). The decision to preregister all 24
candidates now, before any backtest, follows this repo's standing rule that
parameterized/multi-candidate rounds must preregister a machine-readable
candidate manifest and pass the iteration validator before any backtest,
including diagnostics.

## Next iteration suggestion

**Closed for the sleeve question; not reopened by default.** Do not
re-run this iteration to re-confirm the sleeve-level G1/G1' shortfall --
that is a settled mathematical consequence of T0 being an unexecutable
upper bound, not something Stage B could reverse. `reopen_if`: a
portfolio-combination test wants D1 as a component (e.g. IBS entries while
a sleeve otherwise sits in cash) -- in that case, implement and run Stage B
(the 15:50 ET proxy + MOC timing) first, since D1's own research-admission
verdict is formally pending T1 and a component-level use is exactly the
case where the placebo-percentile shortfall at T0/T2 (87-92%, short of the
95th-percentile bar) matters enough to resolve properly rather than
diagnostically. D1 is the only one of the six rules that separates itself
from the pack on the G3 placebo test, the 2016-2026 cross-symbol
persistence table, and the T0/T2 research-admission diagnostic above; if
this direction is ever revisited, D1-SPY is the specific cell to start
from, not the family as a whole.
