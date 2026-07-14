# Search Space: mom_multiasset_ml_r1

The ML budget is 16 configurations: eight return-ranking models, four downside-risk filters and four derived sizing policies. All ranking models receive the same factor contract and date-grouped folds. The downside task is evaluated separately and cannot qualify by return AUC alone. Sizing is permitted only from a qualified linear or tree ranking family.

The last six monthly decision dates form a one-time lockbox. Development uses four expanding folds with a 21-session label horizon and an additional 21-session embargo. Model or threshold selection cannot use the lockbox. The matched benchmark is the frozen 12-1 top-5 deterministic strategy, with equal-weight universe, SPY and BIL retained as external references.
