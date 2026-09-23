# Search space: h20260923_11_s3_bear_guard

One mechanism (the frozen S3 vt40+boost overlay, unchanged), five frozen candidates, written to
candidate-manifest.json before any return is computed. The overlay itself -- 63-session absolute
momentum vs SHY, 21-session realized-volatility target (0.40 base, 0.60 dip boost, 1.0 leverage
cap, remainder to SHY), QQQ-oversold dip trigger, monthly rebalance on the last session,
next-open fills -- is inherited unchanged from the live S3 vt40+boost renewal (H-20260923-09) and
is not re-searched.

| axis | values |
|---|---|
| gate id | BG00 (reference, no gate), BG01, BG02, BG03, BG04 (fixed set, one path, no ranking) |
| gate asset | none / QQQ / SMH / HYG-IEF ratio / S3's own unscaled equity curve (fixed per id) |
| gate SMA window | n/a / 200 / 200 / 100 / 200 (fixed per id) |
| gate rule | close (or ratio, or equity curve) below its own SMA => move all non-cash weight to SHY |
| gate checked | every session (daily), signal on a completed close, applied at the next open |
| momentum lookback | 63 sessions vs SHY (fixed, unchanged from S3) |
| volatility target | 0.40 base / 0.60 dip boost (fixed, unchanged from S3) |
| leverage cap | 1.0, down-only, remainder to SHY (fixed, unchanged from S3) |
| holdings | up to 2 of the 5-ETF menu, or SHY (fixed, unchanged from S3) |
| rebalance | last session of month for the momentum book (fixed); gate override can fire any day |
| cost view | 10 bp and 20 bp per side, both reported |

5 candidates, BG00..BG04, one path (`s3_bear_regime_guard_screen`). No model training, no
mutation, no adaptive expansion, and no selection rule: every gate is scored against the same
fixed adoption rule independently, and none is picked over the others based on its own result.
The only things that vary across candidates are `gate_asset` and `gate_sma_window`; BG00 has
neither (no gate).

Controls (preregistered, not candidates, not counted in the 5-candidate budget):

- **EM-k** (4, one per gate BG01-BG04): S3 with both the base (0.40) and boost (0.60) volatility
  targets scaled by one factor `c` in (0, 1], found by bisection on the design window only, so
  EM-k's mean daily gross risk exposure (sum of non-cash weights after the multiplier) equals
  gate k's mean daily gross risk exposure over the design window. No gate signal.
- **CS-k** (20 per gate, 80 total): gate k's own design-window daily on/off series, circularly
  shifted by `offset_j = round(N * j / 21)` sessions for `j = 1..20`, where `N` is the number of
  design-window sessions. Preserves on/off duration and time-in-market, breaks alignment with
  actual market states. Design window only.

Fixed simulation budget: 4 gates + 4 EM-k controls + 80 CS-k placebos = 88 simulations. BG00
needs no new simulation -- its numbers are reused from the existing stress replay
(design window) and the authorized 2026-09-23 renewal record (anchor window).

Adoption rule (all must hold, per gate, independently): design window (a) max drawdown
improvement >=10pp vs BG00, (b) Sharpe >= BG00 Sharpe + 0.10, (c) Sharpe > EM-k, (d) Sharpe beats
>=18/20 CS-k placebos; anchor window at 10 and 20 bp (e) CAGR >=50% and max drawdown >=-35% (gate
G1), do-no-harm only, no holdout claim. Multiple comparisons: 4 gates, all reported. If none
pass: "no guard; keep the 25% exit".

Diagnostics (not candidates, never ranked, declared as benchmark-family members rather than
manifest rows): BG00 reference, each gate's own EM-k control, each gate's CS-k placebo
distribution, the unscaled ("s3_no_overlay") book, and SHY/QQQ buy-and-hold.
