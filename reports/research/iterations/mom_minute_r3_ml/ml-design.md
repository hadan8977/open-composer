# Momentum ML Design: us_mom_minute_p1_003_frozen

- Decision: `train_bounded_challengers`
- Role: `entry_meta_label_advisory`
- Scope: `accept_or_skip_frozen_rule_entry`
- Execution behavior changed: `false`

| Gate | Actual | Result |
|---|---:|---|
| frozen_strategy_identity | us_mom_minute_p1_003_frozen | PASS |
| entry_events | 138 | PASS |
| positive_events | 50 | PASS |
| negative_events | 88 | PASS |
| feature_completeness | 138 | PASS |
| purge_and_embargo | {'method': 'episode_end_before_test_start_minus_embargo', 'embargo_bars': 13} | PASS |
| valid_walk_forward_folds | 3 | PASS |
| ml_family_holdout | 102 | PASS |
