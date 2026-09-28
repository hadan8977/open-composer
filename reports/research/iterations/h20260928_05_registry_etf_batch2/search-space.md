# Search Space: h20260928_05_registry_etf_batch2

One path, `registry_etf_batch2_screen`, with exactly 7 preregistered
candidates (well under the 24-combination-per-path cap and the round's
80-candidate budget): HFEA_UPRO_TMF (fixed 55/45 UPRO/TMF, monthly), TOM_SPY
(calendar, daily-frequency signal dates), EOM_REVERSAL_SPY (monthly),
FRONT_RUN_SECTOR_TOP2 (monthly, 9-sector universe), FOMC_DRIFT_SPY and
FOMC_DRIFT_TQQQ (calendar, daily-frequency signal dates, hard-coded FOMC
meeting dates), and XYLD_COVERED_CALL_PROXY (fixed buy-and-hold, monthly).
No parameter is swept -- every candidate's parameters are copied verbatim
from its cited primary source (see `candidate-manifest.json`'s per-candidate
`parameters`), so there is no grid beyond the 7 discrete mechanisms
themselves.

Cost assumption: 10bp per side primary, 20bp per side stress, next-open fill,
per `cost-contract.json`. Benchmark family: the S3 incumbent (date-neutral
median-offset reference), a vol-matched k*S3+(1-k)*SHY control for the K2
diversifier test, and SPY/QQQ/SHY buy-and-hold. This round uses the owner's
2026-09-28 relaxed keep rule (K1 or K2, see `candidate-manifest.json`'s
`adoption_rule`) rather than the earlier campaign-era 20bp-Sharpe-excess-over-
BIL gate, since this is routine registry triage, not a new campaign.
