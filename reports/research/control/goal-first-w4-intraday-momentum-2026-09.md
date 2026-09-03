# W4: Single-ETF Intraday Momentum — Clean Negative, Computationally Feasible

Method: `scripts/search_intraday_momentum_etf.py`, mechanism
`open_composer.research.kernel.mechanisms.intraday_momentum_etf` (causal
simplification of Zarattini/Aziz/Barbon's opening-range momentum, source
card `reports/harness/source_cards/goal_first_w7.jsonl`), evaluated through
the P1b mechanism harness with the git-committed
`config/promotion/kernel-paper-tier-gates.json` gate contract.
Full evidence: `reports/research/search/intraday-momentum-etf-2026-09.json`.

## Feasibility (Q3, first half)

**Yes, comfortably feasible on this machine.** Loading and resampling 3.5
years of full-market SIP minute bars to 5-minute RTH bars for both SPY and
QQQ, then running an 18-combination nested walk-forward evaluation for each,
peaked at **581MB RSS** — well under the ~1GB budget the plan set for this
wave, achieved by loading and resampling one (symbol, year) pair at a time
and discarding the raw minute frame before the next year loads (`gc.collect()`
between iterations kept memory from accumulating across the 8 symbol-year
loads). Wall-clock time was roughly 15 minutes per full run, dominated by
disk I/O contention with the concurrent 2016-2022 background minute backfill
sharing the same disk, not by the computation itself.

## Two bugs found and fixed en route (not part of the original plan scope)

1. **Resampler correctness** — none; `open_composer/research/kernel/resample.py`
   passed its VWAP/RTH-filtering/half-day/anchoring checks against real data on
   the first real backtest use (see `tests/test_kernel_resample.py`, 10 tests).
2. **Benchmark date-index mismatch** — the mechanism's per-session return index
   (built from RTH bar timestamps) and the daily benchmark's return index (SIP's
   native tz-aware time-of-day) used different date representations for the same
   calendar day, so every benchmark reindex returned all-missing rows. This is
   the *same class* of bug independently hit and fixed in W3
   (`scripts/evaluate_champion_route_sip.py`); rather than fix it a second time
   in place, it was extracted into a shared
   `open_composer.research.kernel.benchmark_returns.daily_returns_on_naive_dates`
   helper and both scripts now use it (W3's numbers were re-verified byte-identical
   after the refactor).
3. **Archive freshness skew** — the daily and minute SIP archives are refreshed
   independently and were one session out of sync (minute had 2026-09-01, daily's
   newest bar was 2026-08-31), which surfaced as the same "missing benchmark row"
   symptom at the trailing edge. Fixed by trimming the intraday bars to the
   benchmark's actual common coverage before scoring, which is the right general
   behavior regardless of which archive happens to be ahead on a given day.

## Result (Q3, second half): no signal after costs

**Clean negative for both SPY and QQQ.** 18 parameter combinations per symbol
(noise multiplier x lookback x trailing-stop on/off) cluster to an honest
**effective N of 3** (breadth_ratio 0.167 — confirms most of the 18 combos are
correlated variants of the same few ideas, not independent trials).

| | QQQ best | SPY best |
|---|---:|---:|
| Sharpe excess BIL | -0.466 | -0.914 |
| DSR probability | 0.083 | 0.064 |
| CAGR | 0.21% | 0.52% |
| CAGR excess QQQ | -24.8pp | -24.5pp |
| Positive fold fraction | 2/3 | 2/3 |
| Gates passed | 3/8 | 3/8 |
| Promotion eligible | No | No |

Zero of the 36 candidates (18 x 2 symbols) are promotion-eligible. Both best
candidates also show near-zero upside capture relative to QQQ/TQQQ
(0.001-0.012), consistent with an infrequently-triggered breakout rule that
mostly sits flat and occasionally eats a round-trip cost for no gain, rather
than a rule that is capturing real intraday continuation.

No parameter was retuned to chase a better result; the grid was fixed before
running, per the plan's explicit prohibition.

## Disposition

This specific mechanism, on SPY/QQQ 5-minute bars, 2024-2026 OOS, does not
clear the promotion bar and the effect size is not close (Sharpe-excess-BIL
solidly negative, not a near-miss). Consistent with the literature's own
finding (source-carded: "What survives honest evaluation?", arXiv 2608.27734)
that effective alpha is sparse and this is not grounds to loosen gates or
retune. Does not rule out intraday momentum broadly -- only this specific
causal simplification, these two symbols, and this 3.5-year window. If pursued
further, the next step per the source literature would be exit-rule variants
(Maroy, SSRN 5095349) as a genuinely different mechanism family, not more
points in the same noise-band grid.
