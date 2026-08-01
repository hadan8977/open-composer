# Backtest Forensics: us_robust_momentum_ensemble_r4

The implementation passed the mechanical lookahead review: all factors use `close_t` or earlier, weights become effective at the next observed open, inputs use exact common sessions with no price fill, and the future-feature sentinel was rejected. Outer folds are chronological and both outer and inner stages use a 21-bar label horizon plus a 21-bar embargo.

The research claim is nevertheless blocked. `N01`, trained on shuffled labels, produced Sharpe `2.73`, above deterministic parent `D07` at `2.26`. This means the observed ML gating benefit is not distinguishable from random exposure reduction. No ML candidate may continue. The 13 selectable-candidate DSR proxy also failed: observed maximum Sharpe `2.28` is below expected maximum `2.52`. Four-fold PBO `0.17` is too coarse to override either warning.

`D06` is the report-only leader: `45.56%` total return, `29.14%` annualized return, Sharpe `2.28`, and `-11.19%` maximum drawdown over 370 OOS sessions at 10 bps. It improves equal-sleeve Sharpe from `2.15` and drawdown from `-15.23%`, but equal sleeves return `67.38%`, and D06 loses `-0.85%` in fold 1. It failed the preregistered three-fold return-win rule.

The stock panel is a current-universe snapshot, the common history is only 1,000 sessions, and inactive names, delisting returns, permanent IDs, and action lineage are missing. These defects can inflate every stock-based sleeve and benchmark, including raw 12-1. The result supports workflow learning and design rejection only.

Conclusion: `blocked`. Do not promote, paper trade, or retune against this OOS result.
