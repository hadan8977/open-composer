"""Stage-1 IC gate for SEC FTD signals (T-20260929-72): Newey-West t of the daily rank IC.

Companion to the ``signal_card`` rank cards in
``reports/research/iterations/h20260929_72_sec_ftd/signal-card-manifest.json``. Sign is
preregistered: high FTD -> lower return, so the tested signal is ``-FTD``; a positive IC
is the preregistered direction. Same pool (universe_broad ADV top 1500, close >= 5),
forward returns (close signal -> next open -> open after h sessions) and price hygiene
as ``signal_card``. ``t_nw`` is the Newey-West (Bartlett, lag = horizon) t of the mean of
the overlapping daily IC series. Writes ``ic_table.json`` next to the manifest.

    flock /tmp/oc-heavy-r2207.lock scripts/run_capped.sh --mem 1.8G -- \
        uv run python scripts/ftd_ic_test.py
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from open_composer.research.signal_card import (  # noqa: E402
    RECENT_START,
    load_market,
    load_signal,
    masked_ranks,
    rank_corr,
)

ITER = ROOT / "reports" / "research" / "iterations" / "h20260929_72_sec_ftd"
FTD = ROOT / "data" / "features" / "ftd" / "ftd.parquet"
HORIZONS = (20, 60)
TOP_N = 1500
SIGNALS = ("ftdsh", "ftdadv", "ftd_dummy")


def newey_west_t(x: np.ndarray, lag: int) -> float | None:
    """t-stat of the mean with a Bartlett-kernel long-run variance."""
    x = x[np.isfinite(x)]
    n = len(x)
    if n < lag + 10:
        return None
    d = x - x.mean()
    lrv = float(d @ d) / n
    for k in range(1, lag + 1):
        lrv += 2 * (1 - k / (lag + 1)) * float(d[k:] @ d[:-k]) / n
    if lrv <= 0:
        return None
    return float(x.mean() / math.sqrt(lrv / n))


def summarize(series: np.ndarray, dates: pd.DatetimeIndex, h: int) -> dict:
    s = pd.Series(series, index=dates).dropna()
    recent = s[s.index >= RECENT_START]
    pre = s[s.index < RECENT_START]
    return {
        "full": {"mean": float(s.mean()), "t_nw": newey_west_t(s.to_numpy(), h), "days": len(s)},
        "recent_2024": {
            "mean": float(recent.mean()) if len(recent) else None,
            "t_nw": newey_west_t(recent.to_numpy(), h),
            "days": int(len(recent)),
        },
        "pre_2024": {"mean": float(pre.mean()), "t_nw": newey_west_t(pre.to_numpy(), h)},
        "by_year": {str(y): float(v) for y, v in s.groupby(s.index.year).mean().items()},
    }


def main() -> None:
    market = load_market(top_n=TOP_N)
    member = market.member()
    ranks: dict[str, np.ndarray] = {}
    coverage: dict[str, float] = {}
    for col in SIGNALS:
        sql = (
            "SELECT symbol, CAST(trade_date AS TIMESTAMP) AS trade_date, "
            f"{col} AS value FROM read_parquet('{FTD}') WHERE {col} IS NOT NULL"
        )
        sig = -load_signal(market, sql=sql)  # preregistered sign: high FTD -> lower return
        coverage[col] = float(np.nanmean(np.isfinite(sig * member).sum(axis=1)))
        ranks[col] = masked_ranks(sig, member)
        del sig
    result: dict = {
        "iter_id": "h20260929_72_sec_ftd",
        "sign": "signal = -FTD; positive IC = preregistered direction (high FTD -> lower return)",
        "pool": f"universe_broad ADV top {TOP_N}, close >= 5",
        "coverage_mean_names_per_day_in_pool": coverage,
        "horizons": {},
    }
    for h in HORIZONS:
        rf = masked_ranks(market.forward_returns(h), member)
        blk = {}
        for col in SIGNALS:
            blk[col] = summarize(rank_corr(ranks[col], rf, member), market.dates, h)
        result["horizons"][f"h{h}"] = blk
        print(h, {c: (blk[c]["recent_2024"], blk[c]["full"]["mean"]) for c in SIGNALS}, flush=True)
    (ITER / "ic_table.json").write_text(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
