# Search space: h20260923_10_levered_lanes

One mechanism, five frozen candidates, written to candidate-manifest.json before any return
was computed. The overlay machine is not re-searched: 63-session absolute momentum vs SHY,
21-session realized-volatility target (0.40 base, 0.60 dip boost, 1.0 leverage cap, remainder
to SHY), QQQ-oversold dip trigger (close above 200-session SMA and Wilder RSI(10) below 30 for
10 sessions), monthly rebalance on the last session, next-open fills -- all inherited unchanged
from the live S3 vt40+boost renewal (H-20260923-09).

| axis | values |
|---|---|
| lane symbol | NUGT, JNUG, FAS, DPST, DFEN (fixed set, one path, no ranking) |
| momentum lookback | 63 sessions vs SHY (fixed) |
| realized volatility window | 21 sessions (fixed) |
| volatility target | 0.40 base / 0.60 dip boost (fixed) |
| dip boost trigger | QQQ > 200-session SMA and Wilder RSI(10) < 30, 10-session duration (fixed) |
| leverage cap | 1.0, down-only, remainder to SHY (fixed) |
| holdings | 1 lane ETF or SHY (fixed) |
| rebalance | last session of month (fixed) |
| cost view | 10 bp and 20 bp per side, both reported for every candidate |

5 candidates, LN01..LN05, one path (`levered_industry_second_bet_lane_screen`). No model
training, no mutation, no adaptive expansion, and -- unlike a typical search space -- no
selection rule at all: every lane is scored against the same fixed gates independently, and none
is picked over the others. The only thing that varies across candidates is `lane_symbol`.

Diagnostics (not candidates, never ranked, declared as benchmark-family members rather than
manifest rows): each lane's raw return with no overlay, each lane with the 0.40 volatility
target only (no dip boost), and the live S3 book (A4 menu, vt40+boost) as the correlation
reference for the second-bet criterion.

Placebos: a pool-rank placebo running the identical frozen machine on each of the 24 ETFs in
the levered pool (TQQQ SOXL SPXL TNA UPRO SSO QLD NUGT UDOW LABU FAS TECL JNUG ERX BOIL YINN
GUSH TMF URTY BULZ AGQ DPST UWM NAIL), and a dip-signal calendar-shift placebo over 20 fixed
offsets. Both must show a beat-fraction of 10% or less against each lane; the strict
family-wise read (10% / 5 comparisons = 2%) is reported alongside.
