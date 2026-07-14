# External Brief: mom_multiasset_ml_r1

The deterministic round retained ETF long-horizon momentum, stock 12-1 momentum and sector-relative momentum as method survivors. This ML round changes both the information set and the task: it uses a date-by-stock panel with grouped market, trend, risk and liquidity features, and it compares return ranking with downside-risk filtering and sizing.

The model family is deliberately bounded. A regularized linear model tests whether stable additive effects are sufficient; LightGBM, Extra Trees and histogram gradient boosting test nonlinear interactions without introducing deep-learning sample demands. Logistic and LightGBM downside classifiers are evaluated by calibration and by their marginal effect on the matched deterministic portfolio.

The final six decision dates remain unopened unless a family beats the deterministic baseline in at least three of four purged development folds. No symbol identifier is exposed, every feature is index-1, and a 21-session label horizon plus 21-session embargo prevents overlapping future information.
