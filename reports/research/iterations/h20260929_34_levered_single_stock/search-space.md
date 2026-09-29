# Search Space: h20260929_34_levered_single_stock

One path, `levered_single_stock_screen`, 14 candidates, budget 14 (<=24,
single-mechanism lightweight exemption, no separate campaign contract).

Grid (12 mechanism cells): menu size N in {20, 50} x concentration k in
{1, 2, 3} x leverage in {1x, 2x}. All 12 use: 63-session momentum ranking
within the point-in-time megacap-by-liquidity menu (`menu.parquet`),
absolute-momentum filter (momentum_63 <= 0 -> no slot, falls to SHY via the
harness's own remainder), monthly rebalance, vt40 (40% target) volatility
overlay (single-pass proxy, see cost-contract.json).

Plus 2 controls (never keep-tier eligible):
- `LSS_N20_EW_2X`: all 20 top-20-menu names, equal weight, 2x leverage,
  vt40 -- isolates "does leverage + vt40 alone look good" from stock-picking.
- `LSS_RAND_K2_2X`: 2 random names from the top-20 menu each month
  (deterministic, seed 20260929), 2x leverage, vt40 -- isolates "does
  concentration alone (regardless of which names) look good".

Cost: 10bp primary / 20bp stress per side, frozen screen_lane contract.
Benchmark family: S3 (K1/K2 reference), the two controls above, SHY cash.
Wave 9.2 band: not applicable (single-mechanism screen_lane batch, not a
Wave-9.2-gated campaign).
