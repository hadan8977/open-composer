"""Stage-1 IC gate for NSI252 (T-20260929-70): Newey-West t, residual IC, NSI126.

Companion to the ``signal_card`` rank cards in
``reports/research/iterations/h20260929_70_net_share_issuance/signal-card-manifest.json``.
Sign is preregistered: low issuance is long, so the tested signal is ``-NSI``.
Daily Spearman rank IC over the ADV top-1500 point-in-time pool (same universe,
forward returns and price hygiene as ``signal_card``); horizons 20 and 60 sessions,
entry at the next open. ``t_nw`` is the Newey-West (Bartlett, lag = horizon) t of the
mean of the overlapping daily IC series. Residual IC: per day the percentile rank of
the signal is regressed on the percentile ranks of log dollar ADV (63d, size proxy;
cover-page shares are unadjusted so price x shares is not a clean market cap) and
12-1 momentum, and the residual is rank-correlated with the forward return.

    scripts/run_capped.sh --mem 1.8G -- uv run python scripts/nsi_ic_test.py
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
    FEATURES,
    RECENT_START,
    load_market,
    load_signal,
    masked_ranks,
    rank_corr,
)

ITER = ROOT / "reports" / "research" / "iterations" / "h20260929_70_net_share_issuance"
NSI = ROOT / "data" / "features" / "nsi" / "nsi.parquet"
HORIZONS = (20, 60)
TOP_N = 1500


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
    return {
        "full": {
            "mean": float(s.mean()),
            "t_nw": newey_west_t(s.to_numpy(), h),
            "days": int(len(s)),
        },
        "recent_2024": {
            "mean": float(recent.mean()) if len(recent) else None,
            "t_nw": newey_west_t(recent.to_numpy(), h),
            "days": int(len(recent)),
        },
        "pre_2024": {
            "mean": float(s[s.index < RECENT_START].mean()),
            "t_nw": newey_west_t(s[s.index < RECENT_START].to_numpy(), h),
        },
        "by_year": {str(y): float(v) for y, v in s.groupby(s.index.year).mean().items()},
    }


def residual_ranks(y: np.ndarray, xs: list[np.ndarray], mask: np.ndarray) -> np.ndarray:
    """Per day OLS residual of ``y`` on ``xs`` (all percentile ranks) over ``mask``."""
    out = np.full(y.shape, np.nan, dtype=np.float32)
    ok = mask & np.isfinite(y)
    for x in xs:
        ok &= np.isfinite(x)
    for t in np.nonzero(ok.sum(axis=1) >= 30)[0]:
        m = ok[t]
        X = np.column_stack([np.ones(m.sum())] + [x[t, m] for x in xs]).astype(np.float64)
        beta, *_ = np.linalg.lstsq(X, y[t, m].astype(np.float64), rcond=None)
        out[t, m] = (y[t, m] - X @ beta).astype(np.float32)
    return out


def _pct(x: np.ndarray, mask: np.ndarray) -> np.ndarray:
    r = masked_ranks(x, mask)
    n = np.isfinite(r).sum(axis=1, keepdims=True)
    return np.where(n > 0, r / np.maximum(n, 1), np.nan).astype(np.float32)


def main() -> None:
    market = load_market(top_n=TOP_N)
    member = market.member()

    def sig(col: str) -> np.ndarray:
        sql = (
            "SELECT symbol, CAST(trade_date AS TIMESTAMP) AS trade_date, "
            f"{col} AS value FROM read_parquet('{NSI}') WHERE {col} IS NOT NULL"
        )
        return -load_signal(market, sql=sql)  # preregistered sign: low issuance is long

    s252, s126 = sig("nsi252"), sig("nsi126")
    mom = load_signal(market, source=str(FEATURES / "daily_broad"), column="momentum_252_21")
    adv = load_signal(market, source=str(FEATURES / "daily_broad"), column="dollar_adv_63")
    logadv = np.where(adv > 0, np.log(np.where(adv > 0, adv, 1.0)), np.nan).astype(np.float32)
    p_size, p_mom = _pct(logadv, member), _pct(mom, member)
    p252 = _pct(s252, member)
    resid = residual_ranks(p252, [p_size, p_mom], member)
    r252, r126, rres = (masked_ranks(x, member) for x in (s252, s126, resid))
    corr_ctrl = {
        "size_logadv": float(np.nanmean(rank_corr(r252, masked_ranks(logadv, member), member))),
        "mom_12_1": float(np.nanmean(rank_corr(r252, masked_ranks(mom, member), member))),
        "nsi126": float(np.nanmean(rank_corr(r252, r126, member))),
    }
    result: dict = {
        "iter_id": "h20260929_70_net_share_issuance",
        "sign": "signal = -NSI (low issuance long); positive IC = preregistered direction",
        "pool": f"universe_broad ADV top {TOP_N}, close >= 5",
        "coverage_mean_names_per_day": float(np.nanmean(np.isfinite(s252 * member).sum(axis=1))),
        "mean_rank_corr_with_controls": corr_ctrl,
        "horizons": {},
    }
    for h in HORIZONS:
        fwd = market.forward_returns(h)
        rf = masked_ranks(fwd, member)
        blk = {}
        for name, rs in (("nsi252", r252), ("nsi126_control", r126), ("nsi252_residual", rres)):
            blk[name] = summarize(rank_corr(rs, rf, member), market.dates, h)
        raw_r, res_r = (
            blk["nsi252"]["recent_2024"]["mean"],
            blk["nsi252_residual"]["recent_2024"]["mean"],
        )
        raw_f, res_f = blk["nsi252"]["full"]["mean"], blk["nsi252_residual"]["full"]["mean"]
        blk["residual_retention_2024"] = (res_r / raw_r) if raw_r else None
        blk["residual_retention_full"] = (res_f / raw_f) if raw_f else None
        result["horizons"][f"h{h}"] = blk
        print(
            h, json.dumps(blk["nsi252"]["recent_2024"]), blk["residual_retention_2024"], flush=True
        )
    (ITER / "ic_table.json").write_text(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
