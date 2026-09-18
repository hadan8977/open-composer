"""Re-partition the backfilled delisted-symbol daily bars into the archive's
``{root}/{year}/*.parquet`` layout so the universe and daily-feature builders
can take ``data/sip-delisted/by_year`` as a second bars root next to
``data/sip/daily``.

Inputs (both optional, whichever exist):
  data/sip-delisted/daily/*.parquet        2026-09-03 S&P-removed batch (243 symbols)
  data/sip-delisted/broad/daily/*.parquet  scripts/backfill_delisted_daily_bars.py output
Output:
  data/sip-delisted/by_year/{year}/delisted-{source}-{batch}.parquet
  data/sip-delisted/by_year/_MANIFEST.json  (symbols, rows, span per source/year)
Symbols already present in the survivors' archive are dropped defensively (the
backfill already excludes them, but the older S&P batch does not). Re-running
rewrites the tree from scratch; it is small (a few million rows).
"""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE_LAYOUT = ROOT / "data" / "sip" / "daily" / "_LAYOUT.json"
SOURCES = {
    "sp500removed": ROOT / "data" / "sip-delisted" / "daily",
    "broad": ROOT / "data" / "sip-delisted" / "broad" / "daily",
}
OUT = ROOT / "data" / "sip-delisted" / "by_year"
EXCLUSIONS = ROOT / "data" / "sip-delisted" / "broad" / "_alias_exclusions.parquet"
COLUMNS = ["symbol", "timestamp", "open", "high", "low", "close", "volume", "trade_count", "vwap"]


def archive_symbols() -> set[str]:
    layout = json.loads(ARCHIVE_LAYOUT.read_text())
    return {s for shard in layout["shard_symbols"].values() for s in shard}


def load_exclusions(path: Path | None) -> tuple[set[str], pd.DataFrame]:
    """Alias table from ``scripts/detect_delisted_aliases.py``: symbols to drop
    entirely and (symbol, span) rows to blank out."""
    if path is None or not path.exists():
        return set(), pd.DataFrame(columns=["symbol", "drop_from", "drop_to"])
    table = pd.read_parquet(path)
    drop_all = set(table.loc[table["drop_all"], "symbol"])
    spans = table.loc[~table["drop_all"] & ~table["symbol"].isin(drop_all)].copy()
    spans["drop_from"] = pd.to_datetime(spans["drop_from"], utc=True)
    spans["drop_to"] = pd.to_datetime(spans["drop_to"], utc=True) + pd.Timedelta(days=1)
    return drop_all, spans[["symbol", "drop_from", "drop_to"]]


def apply_exclusions(frame: pd.DataFrame, drop_all: set[str], spans: pd.DataFrame) -> pd.DataFrame:
    frame = frame.loc[~frame["symbol"].isin(drop_all)]
    if spans.empty or frame.empty:
        return frame
    keep = pd.Series(True, index=frame.index)
    for symbol, sub in spans.groupby("symbol"):
        mask = frame["symbol"] == symbol
        if not mask.any():
            continue
        ts = frame.loc[mask, "timestamp"]
        inside = pd.Series(False, index=ts.index)
        for start, end in zip(sub["drop_from"], sub["drop_to"], strict=True):
            inside |= (ts >= start) & (ts < end)
        keep.loc[inside[inside].index] = False
    return frame.loc[keep]


def run(out: Path, exclusions: Path | None = EXCLUSIONS) -> dict:
    survivors = archive_symbols()
    drop_all, spans = load_exclusions(exclusions)
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    manifest: dict = {
        "built_at": datetime.now(UTC).isoformat(),
        "sources": {},
        "years": {},
        "alias_exclusions": {
            "table": str(exclusions) if exclusions is not None and exclusions.exists() else None,
            "symbols_dropped_entirely": len(drop_all),
            "symbols_with_spans_dropped": int(spans["symbol"].nunique()),
            "rows_dropped": 0,
        },
    }
    seen_symbols: set[str] = set()
    for source, root in SOURCES.items():
        paths = sorted(root.glob("*.parquet"))
        if not paths:
            continue
        src_summary = {"files": len(paths), "rows": 0, "symbols": 0, "dropped_survivors": 0}
        src_symbols: set[str] = set()
        for path in paths:
            frame = pd.read_parquet(path)
            if frame.empty:
                continue
            for column in COLUMNS:
                if column not in frame.columns:
                    frame[column] = pd.NA
            frame = frame[COLUMNS]
            before = frame["symbol"].nunique()
            frame = frame.loc[
                ~frame["symbol"].isin(survivors) & ~frame["symbol"].isin(seen_symbols)
            ]
            src_summary["dropped_survivors"] += before - frame["symbol"].nunique()
            if frame.empty:
                continue
            frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
            rows_before = len(frame)
            frame = apply_exclusions(frame, drop_all, spans)
            manifest["alias_exclusions"]["rows_dropped"] += rows_before - len(frame)
            if frame.empty:
                continue
            for year, year_frame in frame.groupby(frame["timestamp"].dt.year):
                year_dir = out / str(int(year))
                year_dir.mkdir(exist_ok=True)
                target = year_dir / f"delisted-{source}-{path.stem}.parquet"
                year_frame.sort_values(["symbol", "timestamp"]).to_parquet(target, index=False)
                ys = manifest["years"].setdefault(str(int(year)), {"rows": 0, "symbols": set()})
                ys["rows"] += int(len(year_frame))
                ys["symbols"] |= set(year_frame["symbol"].unique())
            src_summary["rows"] += int(len(frame))
            src_symbols |= set(frame["symbol"].unique())
        # symbols in the S&P batch must not be duplicated by the broad batch
        seen_symbols |= src_symbols
        src_summary["symbols"] = len(src_symbols)
        manifest["sources"][source] = src_summary
    for _year, ys in manifest["years"].items():
        ys["symbols"] = len(ys["symbols"])
    manifest["total_symbols"] = len(seen_symbols)
    (out / "_MANIFEST.json").write_text(json.dumps(manifest, indent=1, sort_keys=True))
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--out", type=Path, default=OUT)
    parser.add_argument(
        "--exclusions",
        type=Path,
        default=EXCLUSIONS,
        help="alias table from scripts/detect_delisted_aliases.py (skipped if absent)",
    )
    parser.add_argument("--no-exclusions", action="store_true")
    args = parser.parse_args()
    manifest = run(args.out, None if args.no_exclusions else args.exclusions)
    print(json.dumps({k: v for k, v in manifest.items() if k != "years"}, indent=1))
    print("years:", {y: v["symbols"] for y, v in sorted(manifest["years"].items())})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
