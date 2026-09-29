# Decision Record: h20260929_70_net_share_issuance

## P1 nsi_book_screen

- Path: NSI252 low-issuance cross-section (ADV top 1500, price >= 5), stage 1 IC gate, then 8 books.
- Decision: stop. Verdict refuted; no books built, no ledger entries evaluated.
- Reason: the preregistered gate needs, at 20d or 60d, 2024+ IC positive with Newey-West |t| >= 2.0, same-sign full sample, distinct_from_controls and residual retention >= 50%. At 20d 2024+ IC = +0.0106, NW t 0.81; at 60d +0.0048, NW t 0.25 (`results.json`, `ic_table.json`). Full-sample IC is positive (0.019, NW t 2.06 at 20d; 0.033, t 2.13 at 60d) but comes from 2020-2023 (2021 IC 0.109, 2022 0.052), and 2024 0.009, 2025 -0.012. The distinct_from_controls flag is true and residual retention is 1.00 and 1.30, so the signal is not a size or momentum proxy; it is simply not distinguishable from zero in the recent window. NSI126 control shows the same pattern (2024+ NW t 0.58 / 0.12).
- Next iteration suggestion: stop. Reopen only with dollar repurchase data (no local repurchase amounts) or a corporate-action-adjusted share count that removes the cover-page noise (9% of 252-session pairs were dropped as split-scale, another 0.37% by price break and 0.32% by swing-back).
