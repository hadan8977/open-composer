# Paper Validation Progress

- Progress: `0/20`
- paper_validation_pass: `False`
- Window: `None` -> `None`

## Day Table

| date | counted | passed | reasons |
| --- | --- | --- | --- |
| 2026-07-09 | True | False | state_drift_warning |

## Semantics

- This validates the paper execution workflow, not strategy alpha.
- Skipped non-trading days do not count in the denominator.
- One failed trading day does not clear the window; two consecutive failures reset it.
