"""Find split-like price seams in the SIP daily archive.

A seam is a one-day close ratio near an integer split ratio whose dollar volume is
continuous (price ratio x volume ratio ~ 1): an unadjusted split or a re-based
history, not a real move. Output is JSON: seams per month, seam details since a
date, and the largest single-day |ln ratio| per requested symbol since that date.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

DEFAULT_ROOT = Path("data/sip/daily")
RATIO_KS = (2, 3, 4, 5, 8, 10, 15, 20, 25, 30, 40, 50, 100)
CANDIDATE_HIGH = 1.8
CANDIDATE_LOW = 0.55
RATIO_TOL = 0.03
DOLLAR_VOLUME_TOL = 0.7


def load_closes(root: Path, years: list[int]) -> pd.DataFrame:
    frames = []
    for year in years:
        for shard in sorted((root / str(year)).glob("shard-*.parquet")):
            frame = pq.read_table(shard, columns=["symbol", "timestamp", "close", "volume"])
            frames.append(frame.to_pandas())
    if not frames:
        return pd.DataFrame(columns=["symbol", "date", "close", "volume"])
    data = pd.concat(frames, ignore_index=True)
    data["symbol"] = data["symbol"].astype(str).str.upper()
    data["date"] = pd.to_datetime(data["timestamp"], utc=True).dt.tz_localize(None).dt.normalize()
    data = data.drop(columns=["timestamp"])
    return data.drop_duplicates(subset=["symbol", "date"], keep="last")


def day_ratios(data: pd.DataFrame) -> pd.DataFrame:
    data = data.sort_values(["symbol", "date"], kind="stable").reset_index(drop=True)
    grouped = data.groupby("symbol", sort=False)
    data["prev_date"] = grouped["date"].shift(1)
    data["prev_close"] = grouped["close"].shift(1)
    data["prev_volume"] = grouped["volume"].shift(1)
    data = data.dropna(subset=["prev_close"])
    data = data[(data["volume"] > 0) & (data["prev_volume"] > 0)]
    data = data[(data["close"] > 0) & (data["prev_close"] > 0)].copy()
    data["pr"] = data["close"] / data["prev_close"]
    data["vr"] = data["volume"] / data["prev_volume"]
    return data


def integer_ratio(pr: float) -> int | None:
    for k in RATIO_KS:
        if abs(pr / k - 1) < RATIO_TOL or abs(pr * k - 1) < RATIO_TOL:
            return k
    return None


def find_seams(ratios: pd.DataFrame) -> pd.DataFrame:
    candidates = ratios[(ratios["pr"] > CANDIDATE_HIGH) | (ratios["pr"] < CANDIDATE_LOW)].copy()
    if candidates.empty:
        return candidates.assign(k=pd.Series(dtype="float"))
    candidates["k"] = [integer_ratio(float(pr)) for pr in candidates["pr"]]
    candidates = candidates[candidates["k"].notna()]
    keep = np.abs(np.log(candidates["pr"] * candidates["vr"])) < DOLLAR_VOLUME_TOL
    return candidates[keep]


def build_report(
    root: Path, years: list[int], since: str | None, symbols: list[str]
) -> dict[str, object]:
    ratios = day_ratios(load_closes(root, years))
    seams = find_seams(ratios)
    months = seams["date"].dt.strftime("%Y-%m").value_counts().sort_index()
    since_ts = pd.Timestamp(since) if since else None
    detail = seams if since_ts is None else seams[seams["date"] >= since_ts]
    detail_rows = [
        {
            "symbol": row.symbol,
            "prev_date": row.prev_date.strftime("%Y-%m-%d"),
            "date": row.date.strftime("%Y-%m-%d"),
            "pr": float(row.pr),
            "vr": float(row.vr),
            "k": int(row.k),
        }
        for row in detail.sort_values(["date", "symbol"]).itertuples()
    ]
    window = ratios if since_ts is None else ratios[ratios["date"] >= since_ts]
    spot: dict[str, float | None] = {}
    for symbol in symbols:
        part = window[window["symbol"] == symbol]
        spot[symbol] = float(np.abs(np.log(part["pr"])).max()) if len(part) else None
    return {
        "root": str(root),
        "years": years,
        "since": since,
        "seams_by_month": {month: int(count) for month, count in months.items()},
        "seams_since": detail_rows,
        "n_seams_since": len(detail_rows),
        "spot_max_abs_ln_pr_since": spot,
        "rules": {
            "candidate": f"pr>{CANDIDATE_HIGH} or pr<{CANDIDATE_LOW}",
            "ks": list(RATIO_KS),
            "ratio_tol": RATIO_TOL,
            "dollar_volume_tol_abs_ln": DOLLAR_VOLUME_TOL,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--year", type=int, action="append", help="Repeatable; default 2026.")
    parser.add_argument("--since", default=None, help="YYYY-MM-DD; seam details and spot start.")
    parser.add_argument("--symbols", default="", help="Comma-separated spot-check symbols.")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    report = build_report(args.root, args.year or [2026], args.since, symbols)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"{report['n_seams_since']} seam(s) since {args.since}; wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
