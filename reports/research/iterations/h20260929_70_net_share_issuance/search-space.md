# Search Space: h20260929_70_net_share_issuance

One path, `nsi_book_screen`, 8 candidate books (limit 24), built only if the stage-1 IC gate passes.

- Signal: NSI252 = ln(shares_t / shares_(t-252 sessions)) from PIT cover-page shares (`data/features/sec_fundamentals_daily`), cleaned by frozen rules (scripts/build_nsi_signal.py): missing, |dlog| >= ln 1.5, split-like price-break session in the window, swing-and-return excursion >= ln 1.3. NSI126 is the non-candidate control. Sign preregistered: low issuance long.
- Portfolios: bottom quintile long only; bottom quintile long + top quintile short (ADV top 500 only, ETB proxy) with a 252d SPY beta hedge.
- Rebalance: monthly (21 offsets) or quarterly (every third of 63 offsets); median across offsets decides.
- Pool: ADV top 500, or ADV top 1500 with price >= 5.
- Costs: 10/20 bp per side; borrow 0.5%/3% per year on the short leg (sensitivity, not extra candidates).
- Stage-1 IC gate: signal_card rank cards (20d, 60d) + scripts/nsi_ic_test.py (Newey-West t, residual IC on log dollar ADV and 12-1 momentum); the books are skipped if it fails.
- Not tested: dollar-repurchase version (no local repurchase amounts).
