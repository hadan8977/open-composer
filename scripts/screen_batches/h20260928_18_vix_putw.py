"""T-20260928-18 batch: `scripts/screen_batch.py --batch h20260928_18_vix_putw
--iteration h20260928_18_vix_putw_batch`.

Single candidate: PUTW_HOLD (buy-and-hold WisdomTree CBOE S&P 500 PutWrite
Strategy Fund, ticker PUTW), an honest proxy for the registry's
`dir:put_credit_spread_income` weekly SPY cash-secured put-writing claim.
Fixed weight 1.0 PUTW once PUTW has any price history, monthly frequency
(matching the fund's own monthly option-roll cadence), following the same
pattern as `scripts/screen_batches/h20260928_05_batch2.py`'s
`w_hfea_upro_tmf` / `w_xyld_covered_call_proxy`.

Unlike batch 2, this module DOES import `screen_lane` (`CANDIDATES: list[
ScreenCandidate]`), since there is exactly one trivial fixed-weight
candidate and no calendar-boundary helper is needed.

VIX_REGIME_SPY_SSO_TLT is deliberately NOT a candidate here: dropped by the
owner's 2026-09-28 cross-asset scope decision (its bear leg holds TLT) --
see `reports/research/iterations/h20260928_18_vix_putw_batch/direction-
review.json`. VIX data itself (`data/research/vix/VIXCLS.csv`) was still
added this round and remains available for a future equity-only VIX rule;
it is not read by this module.

Expected outcome of an actual `scripts/screen_batch.py` run: PUTW is not
served by Alpaca at all (confirmed 2026-09-28 via direct
`TradingClient.get_asset('PUTW')` and `StockHistoricalDataClient.
get_stock_bars` probes -- see `data-feasibility.json`), so PUTW never
appears as a column in the panel `scripts/screen_lane.py`'s `load_batch_
panel` loads from `data/sip/daily/*/*.parquet`. `screen_lane.
missing_symbols()` therefore reports PUTW_HOLD's single required symbol as
missing, and `screen_lane.evaluate_candidate()` marks it `skipped: True`
with `skip_reason: "missing from local panel: ['PUTW']"` -- the harness's
own, already-tested handling for this case, not a special case coded here.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import screen_lane as lane  # noqa: E402


def w_putw_hold(close: pd.DataFrame, asof: pd.Timestamp) -> dict[str, float]:
    """Fixed weight 1.0 PUTW once PUTW has any price history at or before
    `asof`. Reads only `close.loc[:asof]` -- no look-ahead. Long-only,
    sum(weights) <= 1 by construction (single symbol, weight 1.0)."""
    hist = close.loc[:asof]
    if "PUTW" not in hist.columns or hist["PUTW"].dropna().empty:
        return {}
    return {"PUTW": 1.0}


CANDIDATES: list[lane.ScreenCandidate] = [
    lane.ScreenCandidate(
        id="PUTW_HOLD",
        name="Buy-and-hold PUTW (WisdomTree CBOE S&P 500 PutWrite Strategy Fund)",
        source_card="wisdomtree_putw_launch_2016",
        universe=("PUTW",),
        freq="M",
        weights_fn=w_putw_hold,
    ),
]
