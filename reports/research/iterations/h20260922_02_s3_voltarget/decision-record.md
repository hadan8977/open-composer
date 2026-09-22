# Decision record: h20260922_02_s3_voltarget

## Path
levered_rotation_volatility_overlay, twelve preregistered cells over the frozen S3 sleeve.

## Decision
Proceed with the historical evaluation of all twelve cells. Filled in with the verdict
(continue, pivot or stop) once report.md exists; the gates G1 to G5 in
docs/plan-strategy-factory-2026-09-22.zh.md section 1 decide it, and no threshold may be moved
after the run.

## Reason
The overlay is published and replicated as a mechanism but repeatedly refuted as a real-time
money maker, and it has never been tested on this particular sleeve, window, cost model or
instrument class. The cheapest decisive test reuses the existing daily panel and the existing
engine from H-20260918-05, so the marginal compute is minutes, and the untouched 2026 holdout
gives an honest read.

## Next iteration suggestion
If the brake carries the result but the volatility target does not, round 2 should test the
brake alone at a preregistered trigger grid rather than widen the volatility target. If neither
helps, stop the S3 risk-overlay line and spend the budget on the earnings-text track
(H-20260922-01) instead of iterating on a levered beta sleeve.
