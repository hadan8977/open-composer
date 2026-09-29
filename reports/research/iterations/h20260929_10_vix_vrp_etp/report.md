# Report: h20260929_10_vix_vrp_etp

T-20260929-10 (owner research-list item 3): long-only-ETP version of
Zarattini/Aziz/Mele (2025, SSRN 5316487 / SFI RP 25-91)'s dual-VIX-signal
volatility risk premium strategy, reopening `dir:vix_term_structure_short_vol`.

## Source signal and position definitions (what was actually read)

Read via the independent QuantConnect replication (`quantconnect_dual_vix_signal_replication`,
code-level, quote-verified against the raw snapshot) -- the paywalled SSRN
full text itself was **not** read (curl and WebFetch both blocked/403; only
a WebSearch snippet of the abstract page was available, `ssrn_5316487_abstract_via_search_snippet`).

- Signal 1 (eVRP): `eVRP_t = VIX_t - eRV_t`, `eRV_t = std(trailing N daily
  SPY close-to-close returns ending at t, ddof=1) * sqrt(252) * 100`. QC's
  own default is N=10 (with an extra same-day intraday-implied return this
  project's close-only contract does not add); this iteration also tests
  N=5 and N=20.
- Signal 2 (term structure): `VIX_t` vs `VIX3M_t` (FRED VXVCLS, newly
  fetched this round). `VIX<VIX3M` = contango (favors short-vol);
  `VIX>VIX3M` = backwardation (favors long-vol).
- Source's own 4-case table (on VIXY): (1) eVRP>0 & VIX<VIX3M -> full
  short-vol, `target_weight=-VIX/100`; (2) eVRP<0 & VIX<VIX3M -> half
  short-vol, `target_weight=-0.5*VIX/100`; (3) eVRP<0 & VIX>VIX3M -> full
  long-vol, `target_weight=+VIX/100`; (4) else -> cash.
- This iteration's long-only-ETP simplification (brief: no shorting, no
  long-vol ETP leg): cases 3+4 collapse into one "not short-vol" state,
  held as SPY (`_SPY` candidates) or SHY (`_SHY` candidates, via the
  harness's automatic cash remainder). The short-vol leg is SVXY at 1x
  weight = VIX/100 (or half), **not** QC's suggested 2x SVXY-beta-matching
  correction for SVXY's post-2018 -0.5x multiplier -- a preregistered
  simplification, not a post-hoc choice.

## Results (all figures from `reports/research/screens/h20260929_10_vix_vrp_etp/leaderboard.json`, cross-checked against `results.json`)

K1 bar: anchor Sharpe >=1.1882, stress Sharpe >=0.6447, positive 20bp CAGR
both windows. K2 bar: diversifier judged_edge >=0.05 both windows. S3
reference: anchor 1.4853, stress 0.8059 (`h20260928_01_s3_rebalance_tranching/results.json`).

| candidate | anchor Sharpe (10bp) | stress Sharpe (10bp) | edge anchor | edge stress | K1 | K2 | DSR (n=12) |
|---|---|---|---|---|---|---|---|
| VVRP_COMBO_RV5_SPY | 0.22 | 0.37 | -0.29 | -0.14 | no | no | 0.09 |
| VVRP_COMBO_RV5_SHY | -0.07 | 0.86 | -0.31 | 0.07 | no | no | 0.04 |
| VVRP_COMBO_RV10_SPY | 0.24 | 0.38 | -0.27 | -0.15 | no | no | 0.10 |
| VVRP_COMBO_RV10_SHY | -0.04 | 0.87 | -0.29 | 0.05 | no | no | 0.04 |
| VVRP_COMBO_RV20_SPY | 0.19 | 0.38 | -0.32 | -0.15 | no | no | 0.08 |
| VVRP_COMBO_RV20_SHY | -0.14 | 0.85 | -0.41 | 0.05 | no | no | 0.03 |
| VVRP_SIG1ONLY_SPY | 0.39 | -0.13 | -0.24 | -0.41 | no | no | 0.15 |
| VVRP_SIG1ONLY_SHY | 0.42 | 0.20 | -0.06 | -0.32 | no | no | 0.16 |
| VVRP_SIG2ONLY_SPY | 0.23 | 0.42 | -0.31 | -0.12 | no | no | 0.09 |
| VVRP_SIG2ONLY_SHY | -0.05 | 0.90 | -0.37 | 0.09 | no | no | 0.04 |
| VVRP_RAND_PLACEBO (control) | 0.07 | 0.21 | -0.32 | -0.25 | n/a | n/a | 0.06 |
| STATIC5050_SMH_QQQ (control) | **1.20** | **0.89** | -0.20 | 0.14 | **yes** | no | 0.62 |

**0/10 primary candidates clear K1 or K2.** Best anchor-window Sharpe among
primaries: 0.42 (`VVRP_SIG1ONLY_SHY`), far below the 1.19 bar. Best
stress-window Sharpe: 0.90 (`VVRP_SIG2ONLY_SHY`), which clears the 0.65
stress bar in isolation but that same candidate's own anchor Sharpe is
-0.05 -- no candidate clears both windows simultaneously. K2's diversifier
edge is negative in the anchor window for every primary (-0.41 to -0.06)
and only marginally positive in the stress window for the SHY variants
(+0.05 to +0.09, still below the 0.05 bar for the anchor side), so K2 also
fails for all 10. No `watch_recent` either (needs anchor Sharpe >=1.19).
No strong_keep.

**Placebo/benchmark comparison:** `VVRP_RAND_PLACEBO` (a deterministic
pseudo-random short-vol day, frequency-matched to `VVRP_COMBO_RV10_SHY`'s
own real trigger rate, same VIX/100 sizing on trigger days) scored anchor
Sharpe 0.07 / stress 0.21. Several primaries nominally beat this placebo on
anchor Sharpe (e.g. `VVRP_SIG1ONLY_SHY` 0.42 vs 0.07), so the eVRP/term-
structure conditioning is not *purely* noise relative to a random short-vol
day -- but since no primary clears K1 or K2 regardless, this comparison
does not change the overall verdict (the manifest's demotion rule only
matters for a candidate that would otherwise be kept).

`STATIC5050_SMH_QQQ` (a fixed monthly 50/50 SMH/QQQ blend, no VIX signal at
all) scored anchor Sharpe 1.20 and stress Sharpe 0.89 -- clearing K1 on its
own (as an external, non-keep-eligible benchmark) and **beating every
VVRP_\* candidate by 0.8-1.3 Sharpe points in the anchor window alone**.
The dual-VIX-signal mechanism adds no value versus simply holding a
diversified tech/semiconductor ETF pair.

**Manual 10-candidate-only DSR** (excluding the placebo and the static
control, `trial_count=10`, `hac_lag=21`, computed directly via
`open_composer.research.campaign_statistics.deflated_sharpe_probability`
on each candidate's own judged-anchor-offset net10 excess-return series --
see `results.json`'s `dsr_anchor_family_n10_non_placebo` field): 0.25-0.51
across the 10 primaries, essentially the same conclusion as the harness's
own 12-candidate DSR (0.03-0.16) -- neither is remotely close to a
publishable threshold (e.g. 0.95), consistent with the decisive Sharpe/K1/K2
failure above.

## QuantConnect reconciliation

QC's own replication reports Sharpe 0.729 (vs SPY buy-and-hold 0.582) over
2016-01 through 2026-07. The closest faithful-parameter analog here,
`VVRP_COMBO_RV10_SPY`, computed over the full local panel history
(2016-01-04 through 2026-09-17, from `returns.parquet`'s
`VVRP_COMBO_RV10_SPY__o00__net10` column) gives a **naive** (no
risk-free subtraction, simple annualized mean/vol ratio) Sharpe of
**~0.59** over the same 2016-01..2026-07 span (0.591) and ~0.59 over the
full available range through 2026-09 (0.593). This is in the same
ballpark as 0.729 but noticeably below it. Methodology differences that
plausibly explain the gap, none of which this iteration adjusted for:

1. **Instrument**: SVXY (this iteration) vs VIXY (QC's replication) --
   different products, different embedded costs/tracking, and SVXY's own
   -1x-to-0.5x multiplier change on 2018-02-27 sits inside this window.
2. **Trading frequency/cost**: this project's frozen contract rebalances
   on every signal day and charges 10bp per side each time; QC's own live
   implementation only trades when the target weight changes sign or
   moves by more than 2% (a no-trade band this iteration's harness does
   not support), so QC's own live turnover and cost drag are lower.
3. **Idle-capital handling**: QC's replication holds idle capital in SPY
   *only* while short-vol; case 3/4 (its own "long-vol" and "cash" states)
   are fully cash. This iteration's `_SPY` variant holds SPY in the
   collapsed not-short-vol state too (a deliberate simplification, not an
   attempt to match QC's own idle-capital rule exactly).

The 0.59-vs-0.729 gap is modest and directionally explainable, not a red
flag that the reconciliation itself is broken -- but it is also far short
of the >=1.19 anchor-window bar this project's own frozen contract requires
for a keep, which is judged over a much shorter, much more recent window
(2024-01..2026-09) than QC's full 2016-2026 span.

## Verdict

**Refuted.** 0/10 primary candidates clear K1 or K2; every primary is
decisively beaten by a static 50/50 SMH/QQQ external control; DSR is far
below any publishable threshold for every primary. See
`decision-record.md` and the updated `dir:vix_term_structure_short_vol`
registry row (`reports/research/harvest/directions.jsonl`, status
`refuted`) for the full reopen-and-refute record.

`workflow_pass=true`, `research_pass=false`, `llm_contribution_pass=false`,
`paper_ready_pass=false`. No paper orders, broker writes, or simulation
activity occurred.
