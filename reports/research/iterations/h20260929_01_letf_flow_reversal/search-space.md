# Search Space: h20260929_01_letf_flow_reversal

Single path (lightweight single-mechanism exemption, no campaign contract):
`letf_flow_reversal_screen`, 15 candidates total, all preregistered in
`candidate-manifest.json` before any return is computed.

- 12 primary `LETF_{SPY,QQQ,SMH}_D{2,3}_H{1,3}`: ticker in {SPY, QQQ, SMH} x
  drop threshold in {2%, 3%} x hold in {1, 3} trading days = 3 x 2 x 2 = 12.
- 3 internal placebo `LETF_{SPY,QQQ,SMH}_RAND`: one per ticker, deterministic
  pseudo-random entry day frequency-matched to the D2_H1 trigger rate, hold
  1 day. Never eligible for a keep tier -- internal falsification control
  only (see `candidate-manifest.json`'s `placebo_internal_falsification`).

Total candidate budget: 15 (<=24, single path, lightweight exemption valid).
The queue task's full 27-candidate family additionally includes the sibling
`h20260929_01_dip_rejudge` iteration's 12 `DIP_*` candidates -- see this
iteration's own `candidate-manifest.json`'s `trial_count_and_dsr_note` for
why the two are separate iterations (a single non-campaign-bound path is
capped at 24 candidates by `open_composer/research/iteration_dossier.py`'s
validator).

Cost assumptions: 10bp per side primary, 20bp per side stress, close signal
-> next session's open fill (both entry and exit) -- the frozen project
contract, see `cost-contract.json`.

Benchmark family: SPY/QQQ/SMH/SHY buy-and-hold plus the S3 incumbent
(`benchmark_v1_letf_vs_s3_k1_k2`) -- K1/K2/strong_keep/watch_recent against
S3's own frozen reference Sharpe (anchor 1.4853, stress 0.8059), per the
owner's 2026-09-28 "Sharpe first, not sizing" rule. No Wave 9.2 go/no-go band
applies to this batch-screening lane (that banding is for a different,
older research track).
