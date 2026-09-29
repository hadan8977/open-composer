"""Shared helper: load SIP daily OHLC rows for a small set of tickers.

data/sip/daily/{year}/shard-NNNN.parquet is sharded by a fixed symbol group
(see data/sip/daily/_LAYOUT.json's shard_symbols), not by date, so loading a
handful of tickers only requires reading their shards, not the whole year --
important for staying inside the box's memory cap (run via
scripts/run_capped.sh) when only a small pilot universe is needed.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SIP_DAILY_DIR = ROOT / "data/sip/daily"


def _symbol_to_shard_map() -> dict[str, str]:
    layout = json.loads((SIP_DAILY_DIR / "_LAYOUT.json").read_text())
    mapping: dict[str, str] = {}
    for shard, symbols in layout["shard_symbols"].items():
        for symbol in symbols:
            mapping.setdefault(symbol, shard)
    return mapping


def load_daily_ohlc(tickers: list[str], years: list[int]) -> pd.DataFrame:
    """Return columns [symbol, timestamp, open, close] for the given tickers
    and years, reading only the shards those tickers actually live in."""
    sym_to_shard = _symbol_to_shard_map()
    shards_needed = sorted({sym_to_shard[t] for t in tickers if t in sym_to_shard})
    missing = sorted(set(tickers) - set(sym_to_shard))
    if missing:
        raise ValueError(f"tickers not found in SIP daily shard layout: {missing}")

    frames = []
    for year in years:
        year_dir = SIP_DAILY_DIR / str(year)
        if not year_dir.is_dir():
            continue
        for shard in shards_needed:
            path = year_dir / f"shard-{shard}.parquet"
            if not path.is_file():
                continue
            df = pd.read_parquet(path, columns=["symbol", "timestamp", "open", "close"])
            df = df[df["symbol"].isin(tickers)]
            if len(df):
                frames.append(df)
    if not frames:
        return pd.DataFrame(columns=["symbol", "timestamp", "open", "close"])
    out = pd.concat(frames, ignore_index=True)
    out["timestamp"] = pd.to_datetime(out["timestamp"], utc=True)
    out = out.drop_duplicates(subset=["symbol", "timestamp"]).sort_values(["symbol", "timestamp"])
    return out.reset_index(drop=True)
