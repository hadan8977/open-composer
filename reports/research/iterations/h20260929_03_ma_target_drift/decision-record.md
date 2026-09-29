# Decision Record: h20260929_03_ma_target_drift

## P1: proceed with a free EDGAR pipeline, then a signal_card admission test

Direction check returned only the queued registry row. Published hedged merger arbitrage returns are single-digit percent per year and have compressed since 2002, so the expected outcome for an unhedged fixed-horizon next-open long is weak; the cheapest decisive test is the signal_card event card on a rule-built table, gated by a 25-row hand check (false-positive rate must be at most 15%) before any return is computed.

## P2: event rule and timing

Item 1.01 8-K accepted by EDGAR, not a completion 8-K (Items 2.01 with 5.01), filer is the acquired party by code rule, not a SPAC-named shell, first per CIK in 365 days. trade_date is the last session on or before the Eastern acceptance date; signal_card enters at the next session open. No completion or DEFM14A information is used.

## P3: what is not tested

Hold-to-close, price-to-offer conditioning and long-short hedged versions (no completion status, offer price or hedge leg in the free pipeline).

- Path: `ma_target_drift_signal_card` (4 cards).
- Decision: proceed to the pipeline hand check, then the four cards.
- Reason: cheapest decisive test; published spread capture is small and compressed, so a negative outcome is the base case and is informative.
- Next iteration suggestion: if refuted, reopen only with offer-price/completion data (paid or a deal database) to test hold-to-close or price-to-offer conditioning.

## Final evaluation decision

**Stop.** All four signal cards rejected (ma_target_all: CAR20 -0.75% t -2.36, 20bp book -16.2%/yr; ma_target_t3: CAR20 -0.62% t -1.33). Do not pivot to other holding periods of the same table; reopen only with completion status and offer prices (paid deal database) to test hold-to-close or price-to-offer conditioning.
