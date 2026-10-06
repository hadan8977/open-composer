"""T-20261005-44 review (lead round 2026-10-06 07:07 UTC): why did F3 autocorr miss 0.90?

Data-only diagnostic. Reads the T-44 cache (iv/hv levels on sessions) and the 8-K 2.02
earnings events; computes no signal and reads no stock returns. Window 2024-10-01..2026-09-15,
the same as F3. Output: f3-diagnostic.json next to this file (new path, nothing overwritten).
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import p6_iv_data_gate as gate  # noqa: E402

NY = ZoneInfo("America/New_York")
OUT = HERE / "f3-diagnostic.json"


def per_symbol_corr(cur: np.ndarray, prev: np.ndarray, min_pairs: int) -> np.ndarray:
    ok = np.isfinite(cur) & np.isfinite(prev)
    n = ok.sum(axis=0)
    with np.errstate(invalid="ignore", divide="ignore"):
        mx = np.where(ok, cur, 0.0).sum(axis=0) / n
        my = np.where(ok, prev, 0.0).sum(axis=0) / n
        dx = np.where(ok, cur - mx, 0.0)
        dy = np.where(ok, prev - my, 0.0)
        c = (dx * dy).sum(axis=0) / np.sqrt((dx**2).sum(axis=0) * (dy**2).sum(axis=0))
    return np.where((n >= min_pairs) & np.isfinite(c), c, np.nan)


def lag1(wide: pd.DataFrame, min_pairs: int = gate.AUTOCORR_MIN_PAIRS) -> np.ndarray:
    a = wide.to_numpy(dtype="float64")
    return per_symbol_corr(a[1:], a[:-1], min_pairs)


def rank_lag1(wide: pd.DataFrame) -> np.ndarray:
    a = wide.to_numpy(dtype="float64")
    cur, prev = a[1:], a[:-1]
    ok = np.isfinite(cur) & np.isfinite(prev)
    out = np.full(a.shape[1], np.nan)
    for j in range(a.shape[1]):
        m = ok[:, j]
        if m.sum() >= gate.AUTOCORR_MIN_PAIRS:
            x = pd.Series(cur[m, j]).rank().to_numpy()
            y = pd.Series(prev[m, j]).rank().to_numpy()
            out[j] = np.corrcoef(x, y)[0, 1]
    return out


def diff_lag1(wide: pd.DataFrame) -> np.ndarray:
    a = wide.to_numpy(dtype="float64")
    d = a[1:] - a[:-1]
    return per_symbol_corr(d[1:], d[:-1], gate.AUTOCORR_MIN_PAIRS)


def q(v: np.ndarray) -> dict[str, float | int]:
    v = v[np.isfinite(v)]
    if not len(v):
        return {"n": 0}
    p = np.percentile(v, [10, 25, 50, 75, 90])
    return {"n": int(len(v)), "p10": p[0], "p25": p[1], "median": p[2], "p75": p[3], "p90": p[4]}


def reaction_sessions(sessions: pd.DatetimeIndex) -> pd.DataFrame:
    """First session whose close-to-close return contains each 8-K 2.02 earnings release."""
    frames = []
    for year in (2024, 2025, 2026):
        p = ROOT / "data" / "features" / "earnings_events" / f"{year}.parquet"
        frames.append(pd.read_parquet(p, columns=["ticker", "acceptance_utc"]))
    ev = pd.concat(frames, ignore_index=True).dropna()
    ts = pd.to_datetime(ev["acceptance_utc"], utc=True, errors="coerce")
    ev = ev.assign(ts=ts).dropna(subset=["ts"])
    local = ev["ts"].dt.tz_convert(NY)
    day = local.dt.tz_localize(None).dt.normalize()
    after_close = local.dt.hour * 60 + local.dt.minute >= 16 * 60
    pos = sessions.searchsorted(day)  # first session >= release day
    is_session = np.isin(day.to_numpy(), sessions.to_numpy())
    pos = np.where(is_session & after_close.to_numpy(), pos + 1, pos)
    keep = pos < len(sessions)
    out = pd.DataFrame(
        {"symbol": ev["ticker"].to_numpy()[keep], "r": sessions[pos[keep]]}
    ).drop_duplicates()
    return out


def main() -> int:
    cache = pd.read_parquet(HERE / "cache" / "volhist_sessions.parquet")
    sessions = gate.load_sessions()
    late = sessions[(sessions >= gate.LATE_START) & (sessions <= gate.WIN_END)]
    sub = cache[(cache["t"] >= gate.LATE_START) & (cache["t"] <= gate.WIN_END)]
    iv = sub.pivot(index="t", columns="symbol", values="iv_current").reindex(late)
    hv = sub.pivot(index="t", columns="symbol", values="hv_current").reindex(late)
    cols = iv.columns

    base = lag1(iv)
    res: dict = {
        "task": "T-20261005-44 lead review diagnostic",
        "computed_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "window": [str(gate.LATE_START.date()), str(gate.WIN_END.date())],
        "reads_returns": False,
        "D0_replicate_F3_all_symbols": q(base),
    }

    # D1: decision universe (symbols in L12 on at least half of the late dates they have data)
    l12 = gate.load_l12()
    l12 = l12[(l12["date"] >= gate.LATE_START) & (l12["date"] <= gate.WIN_END)]
    l12_days = l12.groupby("symbol")["date"].nunique()
    have_days = iv.notna().sum()
    share = (l12_days.reindex(cols).fillna(0) / have_days.replace(0, np.nan)).to_numpy()
    in_l12 = share >= 0.5
    res["D1_L12_symbols"] = q(base[in_l12])
    res["D1_non_L12_symbols"] = q(base[~in_l12])

    # D2: mask earnings reaction session and the next one
    rs = reaction_sessions(sessions)
    rs = rs[rs["symbol"].isin(cols)]
    masked = iv.copy()
    pos = {s: i for i, s in enumerate(late)}
    n_masked = 0
    for sym, grp in rs.groupby("symbol"):
        j = masked.columns.get_loc(sym)
        for r in grp["r"]:
            i = pos.get(r)
            if i is None:
                continue
            for k in (i, i + 1):
                if k < len(late):
                    masked.iat[k, j] = np.nan
                    n_masked += 1
    has_earn = np.isin(cols, rs["symbol"].unique())
    ex = lag1(masked)
    res["D2_earnings_masked"] = {
        "symbols_with_events": int(has_earn.sum()),
        "cells_masked": n_masked,
        "all_symbols": q(ex),
        "symbols_with_events_only_before": q(base[has_earn]),
        "symbols_with_events_only_after": q(ex[has_earn]),
        "symbols_without_events": q(base[~has_earn]),
        "L12_after": q(ex[in_l12]),
    }

    # D3: rank autocorrelation (robust to jumps); D4: autocorrelation of first differences
    res["D3_rank_lag1_all"] = q(rank_lag1(iv))
    dl = diff_lag1(iv)
    res["D4_diff_lag1_all"] = q(dl)
    res["D4_diff_lag1_earnings_masked"] = q(diff_lag1(masked))
    res["D4_note"] = (
        "white measurement noise on a persistent level drives the first-difference "
        "autocorrelation toward -0.5; a persistent series with rare jumps keeps it near 0"
    )

    # D5: provider self-consistency of iv_week_ago against our own lagged iv_current
    a = iv.to_numpy()
    wk = sub.pivot(index="t", columns="symbol", values="iv_week_ago").reindex(late).to_numpy()
    lag5 = np.vstack([np.full((5, a.shape[1]), np.nan), a[:-5]])
    ok = np.isfinite(wk) & np.isfinite(lag5)
    diff = np.abs(wk[ok] - lag5[ok])
    res["D5_iv_week_ago_vs_lag5_iv_current"] = {
        "pairs": int(ok.sum()),
        "share_abs_diff_le_1e-4": float((diff <= 1e-4).mean()),
        "share_abs_diff_le_0.01": float((diff <= 0.01).mean()),
        "median_abs_diff": float(np.median(diff)),
    }

    # D6: realised vol from the same source, same method (scale reference)
    res["D6_hv_lag1_all"] = q(lag1(hv))

    OUT.write_text(json.dumps(res, indent=1, default=float) + "\n")
    print(json.dumps(res, indent=1, default=float))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
