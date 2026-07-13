# Decision Record: mom_minute_r3_ml

- Path: regularized_logistic and lightgbm_challenger
- Decision: stop promotion; continue forward diagnostic shadow observation only.
- Reason: each selected family won only one of three validation folds. The corrected workflow therefore does not open the reserved holdout. Both models are frozen from development data with hashes so their future behavior can be compared without retuning.
- Next iteration suggestion: collect new chronological shadow observations. Do not reuse the invalidly opened historical holdout, expand the eight-trial matrix, or connect either model to broker writes.

This dossier was completed after the initial training command as a remediation
for a workflow violation. It must not be interpreted as a pre-training gate.
