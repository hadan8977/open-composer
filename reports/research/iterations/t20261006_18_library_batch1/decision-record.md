# Decision Record: t20261006_18_library_batch1

## Path

library_factor_books_batch1

## Decision

stop for this batch: no factor reaches P1 or the preregistered "into the book" rule; the v1.2 book keeps its nine themes. Continue only as follow-ups: IntMom as a shadow inside the momentum theme (not a new theme), and the six data-insufficient ids when the missing items (IBES, Fama-French daily factors, pre-2016 prices, Compustat dc/cshrc) are obtained.

## Reason

19 factors computed, 6 data-insufficient. Best standalone recent net Sharpe 0.92 (roaq, family DSR 0.066); best addition to the composite +0.13 (IntMom, correlation 0.83 with the momentum theme, crash-diagnostic -0.07, below the minimum detectable 0.66). Labels, numbers and power in report.md, results.json and leaderboard.md.

## Next iteration suggestion

Forward shadow for IntMom inside the momentum theme with its stress-period exit rule; obtain the missing data for ConvDebt, ReturnSkew3F, EarningsStreak and the long-lag seasonality ids; the ETF and calendar rules are not at depth (33 anchor months), revisit only with new members and not as the same rules.
