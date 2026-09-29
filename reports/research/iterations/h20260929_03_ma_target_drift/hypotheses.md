# Hypotheses: h20260929_03_ma_target_drift

## H1: US merger targets earn a cost-surviving excess return over 20 sessions after a next-open entry following the 8-K

- Hypothesis: after the 8-K announcing a definitive merger agreement, the target trades at a discount to the offer and drifts towards it; a next-open entry and 20 session hold earns a positive excess return over the universe that survives 10/20 bp per side.
- Failure mode: (a) the premium and most of the spread are in the price by the open after the filing (Jetley-Ji spread compression; Big Moves Small Gains for small caps); (b) high price-to-offer targets under-perform (Bessembinder-Zhang -3.5% over two months); (c) deal breaks; (d) rule errors dilute the event set.
- Measurement: signal_card event mode, date-averaged CAR t-stat, calendar-time book at 10/20 bp, recent window from 2024-01-01.
- Benchmark family: universe equal weight, 20 seeds of redated events (+-126 sessions).
- Stop/Pivot criterion: admit only if car_t_ge_3, beats_redated, book_positive_20bp and book_positive_20bp_recent are all true at the primary horizon; otherwise the card's admit/reject/evidence_too_weak. Nothing is relaxed after results.

## H2 (information only): the small/illiquid tier (t3) has a larger post-announcement drift than the all-target set

- Hypothesis: lower analyst coverage delays information incorporation, so the tail may retain drift after the 8-K.
- Failure mode: small targets already ran up before the 8-K (Big Moves Small Gains); wider spreads consume the drift.
- Measurement: ma_target_t3 versus ma_target_all cards; pre-announcement CAR [-5,-1] reported.
- Stop/Pivot criterion: same flags; both horizons count as trials.
