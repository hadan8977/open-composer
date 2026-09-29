# Search Space: h20260929_01_dip_rejudge

Single path (lightweight single-mechanism exemption, no campaign contract):
`dip_rejudge_screen`, 12 candidates total, all preregistered in
`candidate-manifest.json` before any return is computed.

- 12 candidates `DIP_{D1..D6}_{SPY,QQQ}`: rule in {D1,D2,D3,D4,D5,D6} x
  ticker in {SPY, QQQ} = 6 x 2 = 12. Rule formulas copied verbatim from
  `scripts/run_h20260924_01_etf_dip_reversion.py` -- none re-tuned.

Total candidate budget: 12 (<=24, single path, lightweight exemption valid).
Companion to `h20260929_01_letf_flow_reversal` (15 candidates) -- together
the two iterations cover the queue task's full 27-candidate family; see
this iteration's own `candidate-manifest.json`'s `trial_count_and_dsr_note`
for why the split (a single non-campaign-bound path is capped at 24
candidates by `open_composer/research/iteration_dossier.py`'s validator).

Cost assumptions: 10bp per side primary, 20bp per side stress, close signal
-> next session's open fill (both entry and exit, equivalent in substance to
H-20260924-01's own "T2" timing) -- see `cost-contract.json`.

Benchmark family: SPY/QQQ/SHY buy-and-hold plus the S3 incumbent
(`benchmark_v1_letf_vs_s3_k1_k2`) -- K1/K2/strong_keep/watch_recent against
S3's own frozen reference Sharpe (anchor 1.4853, stress 0.8059), a
materially different bar than H-20260924-01's own absolute giants-sweep
G1/G1' bar. No Wave 9.2 go/no-go band applies to this batch-screening lane.
