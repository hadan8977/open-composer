# Leveraged ETF Risk: us_mom_minute_p1_003_frozen

TQQQ targets daily leveraged Nasdaq-100 exposure. Multi-day returns are
path-dependent and can diverge materially from three times the index over the
holding period because leverage is reset daily and compounding interacts with
volatility. The strategy can also experience amplified overnight gaps, spread
widening, volatility interruption, and partial-fill risk.

Mitigations before paper orders:

- preserve the 100% gross and single-symbol caps in the frozen spec;
- diagnose the -48.47% local gap observation before calibrating any filter;
- collect separate opening and intraday shadow fill evidence;
- enforce a 1% conservative-volume participation cap;
- keep stale, missing, misaligned, or IEX-only cross-source evidence blocked;
- retain a manual kill switch and explicit order authorization in any future
  paper spec.

This note acknowledges risk; it does not make the strategy paper ready.
