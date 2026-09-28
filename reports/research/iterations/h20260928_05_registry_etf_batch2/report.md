# H-20260928-05: registry ETF batch 2 (7 candidates) vs S3

Batch: `scripts/screen_batches/h20260928_05_batch2.py`, run via
`scripts/screen_batch.py --batch h20260928_05_batch2 --iteration h20260928_05_registry_etf_batch2`.
Raw leaderboard: `reports/research/screens/h20260928_05_batch2/leaderboard.json`
(`.md` alongside). This dossier's `results.json` recomputes the K1/K2/watch_recent
tiers field by field from that leaderboard plus S3's own offset-median Sharpe
(`reports/research/iterations/h20260928_01_s3_rebalance_tranching/results.json`
`offset_distribution_net10`; same reference numbers as
`h20260928_02_cross_asset_sleeve/results.json`'s `s3_reference`).

## Freq correction (before any valid result)

Two candidates, EOM_REVERSAL_SPY and FRONT_RUN_SECTOR_TOP2, were originally
declared `freq: "M"` (swept across all 21 monthly rebalance-day offsets). Both
rules only have a signal defined on a specific calendar-anchored date (the
last trading day of the month for EOM_REVERSAL_SPY's 4th-Friday-to-EOM sign
check; the same month-end date for FRONT_RUN_SECTOR_TOP2's one-year-lagged
seasonal score). Declaring them "M" made offsets 1-20 never fire (there is no
signal to shift), so 20 of 21 offsets silently degenerated to pure SHY and the
offset-median was pulled toward the SHY-only value. This was caught and
corrected in an interactive session on 2026-09-28, **before any valid result
was computed for either candidate**: both were re-declared single-version
`freq: "D"` on their calendar-anchored dates only (`n_offsets: 1` in the
leaderboard). The correction is recorded verbatim in
`candidate-manifest.json`'s `parameters.freq_correction` field for each
candidate. All numbers in this report and in `results.json` are from the
corrected single-version run.

## Verdict

**2/7 watch_recent, 5/7 refuted; 0/7 K1, 0/7 K2.**

| id | anchor Sharpe (10bp) | stress Sharpe (10bp) | anchor edge | stress edge | tier | failing criterion |
|---|---:|---:|---:|---:|---|---|
| HFEA_UPRO_TMF | 0.5387 | 0.4549 | -0.4169 | +0.0151 | refuted | K1 anchor 0.5387<1.1882, stress 0.4549<0.6447; K2 both fail |
| TOM_SPY | -0.6876 | -0.1036 | -0.7068 | -0.3602 | refuted | K1 anchor and stress both fail; K2 both fail |
| EOM_REVERSAL_SPY | 1.2406 | 0.5845 | +0.2069 | -0.1732 | **watch_recent** | K1 stress 0.5845<0.6447 (anchor 1.2406>=1.1882 passes); K2 stress -0.1732<0.05 |
| FRONT_RUN_SECTOR_TOP2 | 1.4022 | 0.4517 | +0.2502 | -0.1680 | **watch_recent** | K1 stress 0.4517<0.6447 (anchor 1.4022>=1.1882 passes); K2 stress -0.1680<0.05 |
| FOMC_DRIFT_SPY | -0.8449 | -1.0922 | -0.5998 | -0.7083 | refuted | K1 anchor and stress both fail; K2 both fail |
| FOMC_DRIFT_TQQQ | 0.3125 | -0.0339 | -0.4218 | -0.1558 | refuted | K1 anchor and stress both fail; K2 both fail |
| XYLD_COVERED_CALL_PROXY | 0.8903 | 0.4704 | +0.1237 | -0.0835 | refuted | K1 anchor 0.8903<1.1882, stress 0.4704<0.6447; K2 stress fails |

K1/K2 bars: K1 anchor >=1.1882, stress >=0.6447 (80% of S3's own 1.4853 /
0.8059 median-offset Sharpe), 20bp CAGR>0 both windows; K2 combination edge
>=0.05 both windows. `watch_recent` (runbook section 5, forward-only, not a
keep): anchor Sharpe clears the K1 bar but stress does not.

20bp CAGR for the two watch_recent candidates (context, not gating):
EOM_REVERSAL_SPY anchor +11.01% / stress +6.38%, both positive; FRONT_RUN_SECTOR_TOP2
anchor +27.78% / stress +7.28%, both positive. Neither is used to promote the
tier -- `watch_recent` is defined purely on the anchor/stress Sharpe split per
the runbook.

## Conclusion (5 lines)

1. 2 of 7 candidates (EOM_REVERSAL_SPY, FRONT_RUN_SECTOR_TOP2) clear the K1
   anchor-window Sharpe bar (1.2406 and 1.4022 vs 1.1882) but fall short in
   the stress window (0.5845 and 0.4517 vs 0.6447) -> `watch_recent`,
   forward-tracked only, not kept and not promoted.
2. Both watch_recent candidates were rescued by the freq_correction (declared
   single-version "D" on their calendar-anchored dates instead of a monthly
   offset sweep); before that correction both had silently screened as pure
   SHY and would have shown a flat, uninformative result.
3. Both watch_recent candidates fail K2 in the stress window despite a
   sizeable anchor-window combination edge (+0.207, +0.250) -- the same
   anchor-window-is-not-a-hard-enough-test pattern seen in H-20260928-02 and
   H-20260928-04.
4. The remaining 5 candidates (HFEA, turn-of-month, both pre-FOMC-drift legs,
   the XYLD covered-call proxy) fail K1 on anchor Sharpe alone (all below
   1.1882) and fail K2 in at least one window; none is close to either bar.
5. Per the runbook's watch_recent exit rule, EOM_REVERSAL_SPY and
   FRONT_RUN_SECTOR_TOP2 are logged to `reports/research/screens/kept.jsonl`
   for forward-only tracking (no optimization, no promotion); they drop out
   if 3 forward months show Sharpe <0.5 or a max drawdown >1.5x the
   anchor-window drawdown.
