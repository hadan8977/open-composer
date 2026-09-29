# Decision Record: h20260929_12_hedged_factor_ensemble

## Implementation bug found and fixed (2026-09-29, pre-final): void first Stage 1 result

A first run of `scripts/run_h20260929_12_hedged_books.py` (2026-09-29, before
this record was completed) produced a `results.json` with `stage1_pass=True`
(driven by E20D forms b/bp). That result is **void** and was never reported
as a verdict. Root cause, found by the coordinator's review and independently
verified against source (`run_h20260922_05_salvage.legs`/`.simulate`,
`open_composer.research.signal_card.shift_rows`):

- `market.next_open_returns()` (the stock leg) labels row t with the return
  STARTING at open(t): `open[t+1]/open[t]-1` (forward convention).
- The hedge/underlying legs (`spy_ret_oo` etc., built with `.shift(1)`) and
  S3 (via `salvage.simulate`'s `w_prev @ leg_open[i] + w @ leg_close[i]`)
  label row t with the return ENDING at open(t) (backward/ending
  convention).
- The stock leg was combined with the hedge/underlying legs, and the
  combined series compared against S3, without reconciling these two
  conventions -- a one-session misalignment. Symptoms matched the
  coordinator's diagnosis exactly once reproduced: form (a)'s correlation
  with SPY/S3 was near zero, hedged Sharpe barely differed from unhedged,
  and the diversifier edge swung sign across offsets while the ensembles'
  own test rank IC was ~0.01 (not a real signal collapse -- an alignment
  bug).

Fix (implemented in both `run_h20260929_12_hedged_books.py` and
`build_h20260929_12_stage2_e20d.py`, same day): every internal leg (stock,
hedge, underlying) is now computed in the SAME forward convention
(`forward_open_returns`); the final combined per-form return series is
relabeled to the ending convention via `signal_card.shift_rows(net, 1)`
once, at the end, before any comparison with S3/SPY. `hedge_weight_series`'s
trailing-beta lookback was also corrected to exclude the current
(not-yet-fully-realized) signal-date row. Three hard sanity checks
(corr(a,SPY)>0.5, corr(a,S3)>0.3, beta(b,SPY) in [-0.25,0.25], all over the
Stage 1 window) now abort the run if the alignment is still broken; see
`results.json`'s `sanity_checks` block and the final message for the
realized values. A new regression test
(`test_book_holding_only_spy_reproduces_spy_return_series_exactly`) checks
this end-to-end for a synthetic single-asset book.

No design change: the preregistered candidates (5 ensembles x 4 forms), the
Stage 1 pass rule (edge>=+0.05, standalone Sharpe>0, correlation with
S3<0.30), and the thresholds are unchanged from `direction-review.json`.
This was an implementation bug in the evaluation script, not a
result-driven relaxation or a new selection choice -- so no additional
preregistration or look-ahead issue arises from fixing it and rerunning
Stage 1 once.

## Corrected Stage 1 rerun (2026-09-29): blocked on the coordinator's own sanity gate, not a residual bug

`scripts/run_h20260929_12_hedged_books.py` was fixed per the coordinator's
instructions (forward-convention internal legs, `shift_rows(net, 1)`
relabel at the end, corrected trailing-beta lookback) and rerun under
`scripts/run_capped.sh --mem 1.8G`. Full sanity report, all 5 ensembles,
Stage 1 window (2024-01-02..2026-09-08), from `logs/h20260929_12_books.log`:

| Ensemble | corr(a, SPY) | beta(b, SPY) | corr(a, S3) |
|---|---|---|---|
| E10  | 0.8035 | 0.0640 | 0.1311 |
| E20  | 0.7834 | 0.0409 | 0.1173 |
| E40  | 0.6919 | 0.0312 | 0.0977 |
| E20D | 0.7944 | 0.0264 | 0.1302 |
| R40  | 0.8424 | 0.0298 | 0.1837 |

Diagnostic (not one of the three named checks, added to explain the third
row): `corr(SPY, S3)` over the same window = **0.2340**.

Two of the three hard checks pass decisively and in the direction that
confirms the alignment fix worked: `corr(a,SPY)` jumped from the
(voided) buggy run's near-zero (0.07-0.09, per the coordinator's bug
report) to 0.69-0.84 -- exactly what a long-only, ~50-name US-equity book
should show once the stock leg and the SPY leg share the same realization
date. `beta(b,SPY)` is 0.03-0.06, comfortably inside
[-0.25, 0.25] -- the hedge overlay is neutralizing market beta correctly.

The third check, `corr(a,S3) > 0.3`, fails for all 5 ensembles (0.098-0.184).
The diagnostic line shows why: S3 itself only correlates 0.234 with SPY
over this same 2024-2026 window, i.e. S3 is evidently not a
high-market-beta strategy right now. A long-only book that correctly
tracks SPY at 0.7-0.84 is then mechanically capped to correlate with S3 at
roughly `corr(a,SPY) x corr(SPY,S3) ~ 0.16-0.20` if S3's own residual
(non-SPY) variance is uncorrelated with the stock book's own residual --
which matches the observed 0.098-0.184 closely. This looks like a real,
freshly-measured property of S3 in the current regime, not a residual
alignment bug: the two checks that directly probe alignment (SPY
correlation and hedge beta) both pass cleanly, and the one that fails does
so through a channel (S3's own low market correlation) that has nothing to
do with date labeling.

**The run aborts by design when any of the three checks fails** (per the
coordinator's explicit instruction to add hard aborting checks), so
`results.json` was NOT written and Stage 1's actual pass/fail verdict
(edge>=+0.05, standalone Sharpe>0, correlation with S3<0.30 for some
hedged form) was never computed on this rerun. I am not unilaterally
loosening or dropping the coordinator's `corr(a,S3)>0.3` sanity threshold
-- that would be relaxing a gate I was told to add and enforce, based on my
own judgment call about why it fails, without the coordinator's sign-off.

**Decision: BLOCKED, pending coordinator input.** Options for the
coordinator to choose from (not decided here): (a) accept that
`corr(a,S3)>0.3` was calibrated on a wrong assumption about S3's current
beta and drop/replace it with a check on `corr(a,SPY)` and `beta(b,SPY)`
only (both of which already demonstrate the fix works), then let Stage 1's
own preregistered pass rule run to completion and report its numbers; (b)
supply a different sanity threshold informed by the measured
`corr(SPY,S3)=0.234`; (c) treat this as evidence Stage 1's own
`correlation_with_s3<0.30` pass condition for forms b/bp needs
re-examination given S3's low current market correlation (a book barely
correlated with SPY will almost automatically clear `<0.30` regardless of
whether it says anything about diversification). No results.json,
registry row, or Stage 1 verdict is produced until this is resolved.

## Second, deeper convention bug found by the coordinator (2026-09-29): open-to-open vs close-to-close

My own diagnosis in the section above -- "S3 has a genuinely low ~0.23
correlation to SPY in this window, so a long-only book correctly capped at
0.10-0.18 correlation with S3 is not a bug" -- was **itself wrong**, and is
superseded by this section. The coordinator measured
`corr(SPY, S3)` directly at lags -1/0/+1 for BOTH an open-to-open and a
close-to-close SPY/QQQ series and found: SPY/QQQ **close-to-close** at lag 0
correlates with S3 at 0.58/0.70, while SPY **open-to-open** correlates at
only 0.23 -- i.e. my "diagnostic" number (0.234) was itself computed on the
wrong (open-to-open) convention, and the low value it produced was a
symptom of the SAME convention bug, not a real property of S3.

Root cause: `salvage.legs()`/`salvage.simulate()` (which
`screen_lane.s3_incumbent` is built from) split every rebalance day AT THE
OPEN -- old weights earn the overnight gap `open(t)/close(t-1)-1`, new
weights earn the intraday move `close(t)/open(t)-1` -- so row t of S3's own
return series is a **close-to-close** realized return (close(t-1) ->
close(t)), never an open-to-open one. My fix 1 (forward labeling + a
trailing `shift_rows`) reconciled the STOCK and HEDGE legs' labeling with
each other, but both were still open-to-open in substance, one session off
from what S3 actually is.

Fix 2 (supersedes fix 1's forward/shift approach; see
`run_h20260929_12_hedged_books.py`'s module docstring for the full
derivation): every book (a, b, bp, c) is now built with `simulate_book`, an
exact reimplementation of `salvage.simulate()`'s own overnight/intraday
leg-mixing formula, applied to the stock panel (`stock_legs`, the same
formula as `salvage.legs()`) and to the hedge instrument's existing
`leg_open`/`leg_close` columns (`salvage.legs()`, reused unmodified). Row t
of every book's output is now realized entirely within calendar day t,
matching S3's own convention exactly -- no relabeling step is needed at
all, and `shift_rows`/the forward-open-returns helpers from fix 1 are
removed. `hedge_weight_series`'s trailing-beta lookback now correctly
INCLUDES the current signal-date row (a close-to-close return realized at
the close of day i is fully known at that instant, unlike fix 1's
forward-labeled return which needed the next day's open).
`tests/test_h20260929_12_hedged_ensemble.py` now checks
`simulate_book`/`stock_legs` directly against
`run_h20260922_05_salvage.simulate`/`.legs()` (the actual frozen lane
engine) for a synthetic single-asset book, per the coordinator's
requirement -- a stronger test than comparing against a hand-derived
"expected" series.

No design change (second time): the preregistered candidates, the Stage 1
pass rule, and the thresholds are unchanged. This is the second
implementation-bug fix in the evaluation script's date/return-convention
plumbing, not a new selection choice.

## Close-to-close rerun (2026-09-29): convention fix confirmed correct; still blocked, per the coordinator's own stop condition

Rerun under `scripts/run_capped.sh --mem 1.8G` (70s), from
`logs/h20260929_12_books.log`:

`corr(SPY_cc, S3)` over the Stage 1 window = **0.5784**; `corr(QQQ_cc, S3)` =
**0.6985**. These match the coordinator's own independently-measured
0.58/0.70 to two decimal places, confirming `simulate_book`/`stock_legs`
now reproduce S3's actual close-to-close convention correctly -- the second
fix is verified, not just plausible.

| Ensemble | corr(a, SPY_cc) | beta(b, SPY_cc) | corr(a, S3) |
|---|---|---|---|
| E10  | 0.7814 | 0.0538 | 0.2113 |
| E20  | 0.7690 | 0.0292 | 0.1842 |
| E40  | 0.6899 | 0.0157 | 0.0994 |
| E20D | 0.7798 | 0.0170 | 0.2166 |
| R40  | 0.8381 | 0.0490 | **0.3856** |

`corr(a,SPY_cc)` (all >0.5) and `beta(b,SPY_cc)` (all within [-0.25,0.25])
pass cleanly for all 5 ensembles. `corr(a,S3)>0.3` passes for R40 only;
E10/E20/E40/E20D still fall short (0.099-0.217).

The coordinator's own message set the stop condition for exactly this
outcome: "Given corr(S3, SPY cc) = 0.58 and corr(S3, QQQ cc) = 0.70, a
long-only 50-stock book should clear 0.3. If it still doesn't, stop and
report the numbers." Since the diagnostic correlations match the
coordinator's own measurement almost exactly (confirming the convention
fix, not a residual bug) yet 4 of 5 ensembles still don't clear 0.3, this
run stops here per that explicit instruction rather than attempting a
third self-directed fix.

## `corr(a,S3) > 0.3` sanity heuristic dropped (2026-09-29, coordinator decision)

The coordinator reviewed the close-to-close rerun's numbers (table above)
and decided to drop `corr(a,S3) > 0.3` as a hard gate. Rationale (verbatim
reasoning, condensed): it was always a heuristic for catching a residual
misalignment bug, not a preregistered Stage 1 criterion -- and alignment is
now proven three independent ways: (1) `simulate_book`/`stock_legs` match
the actual frozen `salvage.simulate`/`.legs()` exactly in
`tests/test_h20260929_12_hedged_ensemble.py`; (2) `corr(a,SPY_cc)` is
0.69-0.84 and `beta(b,SPY_cc)` is 0.02-0.05, both cleanly inside their own
thresholds; (3) `corr(SPY_cc,S3)=0.578` and `corr(QQQ_cc,S3)=0.699` match
the coordinator's own independently-measured 0.58/0.70. A low `corr(a,S3)`
is feasible given those values alone (the bound from `corr(a,SPY)=0.78` and
`corr(SPY,S3)=0.58` runs roughly -0.06 to 0.96) and likely reflects the
factor ensembles tilting away from the levered tech/semis S3's own sleeves
hold, not a bug. The two SPY-based checks remain hard gates;
`screen_lane.assert_same_session_convention` (frozen lane code, now called
internally by `diversifier_edge_for_offset`/`correlation_with_s3`) is an
additional, independent alignment check that raises on a one-session
misalignment. `run_h20260929_12_hedged_books.py`'s `run_sanity_checks` was
updated to drop the gate (keeps computing/reporting `corr(a,S3)` as
`corr_a_s3_info_only`); see its docstring for the full reasoning.

Stage 1 is rerun below with the corr(a,S3) gate dropped, the ORIGINAL
preregistered pass rule (edge>=+0.05, standalone Sharpe>0, correlation with
S3<0.30 for forms b/bp) unchanged from `direction-review.json`.
