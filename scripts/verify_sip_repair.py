"""Verify the SIP daily archive repair against the pre-repair backup (T-20261002-01).

Reads only the restated symbols (list taken from ``_restatements.jsonl``) plus a
seeded random sample of symbols that were not restated, in the backup tree and in
the repaired tree, and checks:

V1  returns unchanged: close-to-close and open-open log returns of every restated
    symbol over 2016-01-04..2026-08-24 differ by at most
    ``max(1e-6, 2.5e-4 / min(price_t-1, price_t before))`` (vendor 4-decimal
    rounding); days where the vendor changed the bar (volume ratio differs from the
    symbol's usual ratio) are listed separately as vendor-bar corrections.
V2  year boundary: the same comparison on the last 2025 / first 2026 session.
V3  seams gone: APH 2026-08-26 -> 08-27 close ratio, seam counts, named symbols.
V4  no collateral damage: sampled unrestated symbols are row-identical.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pickle
import random
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from update_sip_archive import (  # noqa: E402
    REFETCH_LOOKBACK_SESSIONS,
    _sessions_back,
    load_sleeve_symbols,
)

COLUMNS = ["symbol", "timestamp", "open", "high", "low", "close", "volume", "trade_count", "vwap"]
V1_START = pd.Timestamp("2016-01-04")
V1_END = pd.Timestamp("2026-08-24")
ROUNDING_ABS = 2.5e-4
RET_TOL = 1e-6
VOLUME_RATIO_TOL = 1e-4
PRECISION_BASE_TOL = 1e-6
PRECISION_DECIMALS = (2, 3, 4)
PRECISION_CLASSES = ("date_set", "bar_correction", "factor_revision", "unexplained")
SPOT = ["APH", "VRME", "KUST", "ZCSH", "UNX", "TANH", "FRO", "WHF", "DX", "UHT", "ESP"]
SEAM_FREE = ["VRME", "KUST", "ZCSH", "UNX", "TANH"]


def load_shard(root: Path, name: str) -> pd.DataFrame:
    """One shard file name across every year directory of ``root``."""
    frames = []
    for year_dir in sorted(root.iterdir()):
        path = year_dir / name
        if year_dir.is_dir() and year_dir.name.isdigit() and path.is_file():
            frames.append(pd.read_parquet(path, columns=COLUMNS))
    if not frames:
        return pd.DataFrame(columns=COLUMNS)
    frame = pd.concat(frames, ignore_index=True)
    frame["symbol"] = frame["symbol"].astype(str).str.upper()
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
    frame = frame.drop_duplicates(subset=["symbol", "timestamp"], keep="last")
    return frame.sort_values(["symbol", "timestamp"], kind="stable").reset_index(drop=True)


def read_restatements(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def compare_symbol(before: pd.DataFrame, after: pd.DataFrame) -> dict[str, object]:
    """V1/V2 statistics for one symbol (frames sorted by timestamp, one symbol)."""
    joined = before.merge(after, on="timestamp", suffixes=("_b", "_a"))
    joined["date"] = joined["timestamp"].dt.tz_localize(None).dt.normalize()
    window = joined[(joined["date"] >= V1_START) & (joined["date"] <= V1_END)].reset_index(
        drop=True
    )
    b_dates = set(before["timestamp"])
    a_dates = set(after["timestamp"])
    out: dict[str, object] = {
        "missing_after": len(b_dates - a_dates),
        "added_after": len(a_dates - b_dates),
        "violations": [],
        "vendor_bar": [],
        "v2": [],
    }
    if len(window) < 2:
        return out
    ratio = (window["volume_a"] / window["volume_b"]).replace([np.inf, -np.inf], np.nan)
    usual = ratio.median()
    vol_changed = ((ratio / usual - 1).abs() > VOLUME_RATIO_TOL).fillna(False).to_numpy()
    for field in ("close", "open"):
        pb = window[f"{field}_b"].to_numpy(dtype=float)
        pa = window[f"{field}_a"].to_numpy(dtype=float)
        with np.errstate(divide="ignore", invalid="ignore"):
            rb = np.log(pb[1:] / pb[:-1])
            ra = np.log(pa[1:] / pa[:-1])
        delta = ra - rb
        tol = np.maximum(RET_TOL, ROUNDING_ABS / np.minimum(pb[1:], pb[:-1]))
        bad = np.where(~(np.abs(delta) <= tol))[0]
        for i in bad:
            item = {
                "field": field,
                "date": window["date"].iloc[i + 1].strftime("%Y-%m-%d"),
                "ret_before": float(rb[i]),
                "ret_after": float(ra[i]),
                "delta": float(delta[i]),
                "tol": float(tol[i]),
            }
            if vol_changed[i] or vol_changed[i + 1]:
                out["vendor_bar"].append(item)  # type: ignore[union-attr]
            else:
                out["violations"].append(item)  # type: ignore[union-attr]
    # V2: last 2025 session -> first 2026 session
    y25 = window[window["date"].dt.year == 2025]
    y26 = window[window["date"].dt.year == 2026]
    if len(y25) and len(y26):
        rows = pd.concat([y25.iloc[[-1]], y26.iloc[[0]]])
        for field in ("close", "open"):
            pb = rows[f"{field}_b"].to_numpy(dtype=float)
            pa = rows[f"{field}_a"].to_numpy(dtype=float)
            delta = float(np.log(pa[1] / pa[0]) - np.log(pb[1] / pb[0]))
            tol = max(RET_TOL, ROUNDING_ABS / float(min(pb)))
            out["v2"].append(  # type: ignore[union-attr]
                {
                    "field": field,
                    "delta": delta,
                    "tol": tol,
                    "strict_bad": abs(delta) > RET_TOL,
                    "bad": abs(delta) > tol,
                }
            )
    return out


def price_decimals(prices: np.ndarray) -> np.ndarray:
    """Decimal places of each price: the smallest d in {2, 3, 4} that fits, else 4."""
    values = np.asarray(prices, dtype=float)
    result = np.full(values.shape, PRECISION_DECIMALS[-1], dtype=int)
    for places in sorted(PRECISION_DECIMALS, reverse=True):
        scaled = values * 10.0**places
        fits = np.abs(scaled - np.round(scaled)) < 1e-4
        result = np.where(fits, places, result)
    return result


def precision_tolerance(*prices: np.ndarray) -> np.ndarray:
    """1e-6 plus the sum of 0.5 * 10**-d(p) / p over every price that enters a return."""
    tol = np.full(np.asarray(prices[0]).shape, PRECISION_BASE_TOL, dtype=float)
    for price in prices:
        values = np.asarray(price, dtype=float)
        with np.errstate(divide="ignore", invalid="ignore"):
            tol = tol + 0.5 * 10.0 ** (-price_decimals(values).astype(float)) / values
    return tol


def classify_precision(
    window: pd.DataFrame, before_dates: set, after_dates: set
) -> list[dict[str, object]]:
    """V1'/V2' events for one symbol: (date, class) for every day outside the tolerance.

    ``window`` is the inner join of the two archives (``*_b`` / ``*_a`` columns, sorted,
    with a ``date`` column). Each event gets exactly one class, tested in this order:
    date_set, bar_correction, factor_revision, unexplained.
    """
    if len(window) < 2:
        return []
    ratio = (window["volume_a"] / window["volume_b"]).replace([np.inf, -np.inf], np.nan)
    usual = ratio.median()
    vol_changed = ((ratio / usual - 1).abs() > VOLUME_RATIO_TOL).fillna(False).to_numpy()
    deltas: dict[str, np.ndarray] = {}
    tols: dict[str, np.ndarray] = {}
    bads: dict[str, np.ndarray] = {}
    for field in ("close", "open"):
        pb = window[f"{field}_b"].to_numpy(dtype=float)
        pa = window[f"{field}_a"].to_numpy(dtype=float)
        with np.errstate(divide="ignore", invalid="ignore"):
            rb = np.log(pb[1:] / pb[:-1])
            ra = np.log(pa[1:] / pa[:-1])
        delta = ra - rb
        tol = precision_tolerance(pb[1:], pb[:-1], pa[1:], pa[:-1])
        both_missing = ~np.isfinite(rb) & ~np.isfinite(ra)
        deltas[field], tols[field] = delta, tol
        bads[field] = ~(np.abs(delta) <= tol) & ~both_missing
    bad_idx = np.where(bads["close"] | bads["open"])[0]
    if not len(bad_idx):
        return []
    one_sided = _to_ns(pd.DatetimeIndex(sorted(before_dates ^ after_dates)))
    stamps = _to_ns(pd.DatetimeIndex(window["timestamp"]))
    events: list[dict[str, object]] = []
    for i in bad_idx:
        gap = int(
            np.searchsorted(one_sided, stamps[i + 1], side="left")
            - np.searchsorted(one_sided, stamps[i], side="right")
        )
        cd, od = deltas["close"][i], deltas["open"][i]
        if gap > 0:
            kind = "date_set"
        elif vol_changed[i] or vol_changed[i + 1]:
            kind = "bar_correction"
        elif (
            np.isfinite(cd)
            and np.isfinite(od)
            and abs(cd - od) <= tols["close"][i] + tols["open"][i]
        ):
            kind = "factor_revision"
        else:
            kind = "unexplained"
        events.append(
            {
                "class": kind,
                "date": window["date"].iloc[i + 1].strftime("%Y-%m-%d"),
                "prev_date": window["date"].iloc[i].strftime("%Y-%m-%d"),
                "delta_close": float(cd),
                "delta_open": float(od),
                "tol_close": float(tols["close"][i]),
                "tol_open": float(tols["open"][i]),
                "year_boundary": bool(
                    window["date"].iloc[i].year == 2025 and window["date"].iloc[i + 1].year == 2026
                ),
            }
        )
    return events


def _to_ns(index: pd.DatetimeIndex) -> np.ndarray:
    """UTC nanosecond integers of a datetime index (naive values are taken as UTC)."""
    if index.tz is not None:
        index = index.tz_convert("UTC").tz_localize(None)
    return index.to_numpy().astype("datetime64[ns]").astype(np.int64)


def compare_symbol_precision(before: pd.DataFrame, after: pd.DataFrame) -> dict[str, object]:
    """V1'/V2' statistics for one symbol under ``--tol-mode precision``."""
    joined = before.merge(after, on="timestamp", suffixes=("_b", "_a"))
    joined["date"] = joined["timestamp"].dt.tz_localize(None).dt.normalize()
    window = joined[(joined["date"] >= V1_START) & (joined["date"] <= V1_END)].reset_index(
        drop=True
    )
    b_dates = set(before["timestamp"])
    a_dates = set(after["timestamp"])
    events = classify_precision(window, b_dates, a_dates)
    return {
        "missing_after": len(b_dates - a_dates),
        "added_after": len(a_dates - b_dates),
        "events": events,
    }


def compare_sample_precision(
    before: pd.DataFrame, after: pd.DataFrame, window_start: pd.Timestamp
) -> dict[str, object]:
    """V4': rows before the routine re-fetch window must be bit-identical in every column."""

    def split(frame: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
        dates = frame["timestamp"].dt.tz_localize(None).dt.normalize()
        return (
            frame[dates < window_start].reset_index(drop=True),
            frame[dates >= window_start].reset_index(drop=True),
        )

    b_old, b_win = split(before)
    a_old, a_win = split(after)
    merged = b_win.merge(a_win, on="timestamp", how="outer", suffixes=("_b", "_a"), indicator=True)
    both = merged[merged["_merge"] == "both"]
    window_diff: dict[str, int] = {}
    for column in COLUMNS:
        if column in ("symbol", "timestamp"):
            continue
        left, right = both[f"{column}_b"], both[f"{column}_a"]
        differs = ~((left == right) | (left.isna() & right.isna()))
        window_diff[column] = int(differs.sum())
    return {
        "identical_before_window": bool(b_old.equals(a_old)),
        "window_diff": window_diff,
        "window_one_sided_rows": int((merged["_merge"] != "both").sum()),
    }


def archive_window_start(root: Path) -> tuple[pd.Timestamp, pd.Timestamp]:
    """(last archive date, start of the routine re-fetch window) for the newest year."""
    year_dirs = [p for p in root.iterdir() if p.is_dir() and p.name.isdigit()]
    newest = max(year_dirs, key=lambda p: int(p.name))
    last = None
    for path in sorted(newest.glob("shard-*.parquet")):
        stamps = pd.read_parquet(path, columns=["timestamp"])["timestamp"]
        if len(stamps):
            top = pd.to_datetime(stamps, utc=True).max().tz_localize(None).normalize()
            last = top if last is None else max(last, top)
    if last is None:
        raise SystemExit(f"no rows found under {newest}")
    start = _sessions_back(last.date(), sessions=REFETCH_LOOKBACK_SESSIONS)
    return last, pd.Timestamp(start)


def seam_date(before: pd.DataFrame, after: pd.DataFrame) -> pd.Timestamp | None:
    joined = before.merge(after, on="timestamp", suffixes=("_b", "_a"))
    if joined.empty:
        return None
    diff = (joined["close_a"] / joined["close_b"] - 1).abs() > RET_TOL
    if not diff.any():
        return None
    return joined.loc[diff, "timestamp"].max().tz_localize(None).normalize()


def window_return(frame: pd.DataFrame, end: str, n: int) -> float | None:
    series = frame.set_index("timestamp")["close"]
    series = series[series.index.tz_localize(None).normalize() <= pd.Timestamp(end)]
    if len(series) <= n:
        return None
    return float(series.iloc[-1] / series.iloc[-1 - n] - 1)


def sha_ok(manifest: Path, root: Path) -> bool:
    expected = json.loads(manifest.read_text())["sha256"]
    for rel, digest in expected.items():
        path = root / rel
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            return False
    return True


def parse_log(path: Path) -> dict[str, object]:
    info: dict[str, object] = {}
    if not path.exists():
        return info
    stamp = re.compile(r"^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d),\d+ ")
    found_at = rewritten_at = first = last = None
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        match = stamp.match(line)
        if not match:
            continue
        when = datetime.strptime(match.group(1), "%Y-%m-%d %H:%M:%S")
        first = first or when
        last = when
        found = re.search(r"repair-full-window: (\d+) restated symbol", line)
        if found:
            found_at = when
            info["repair_found"] = int(found.group(1))
        done = re.search(r"repair-full-window: (\d+) symbol\(s\) rewritten", line)
        if done:
            rewritten_at = when
            info["repair_rewritten"] = int(done.group(1))
        calls = re.search(r"(\d+) api call", line)
        if calls:
            info["api_calls"] = int(calls.group(1))
    if first and last:
        info["elapsed_min"] = (last - first).total_seconds() / 60
    if found_at and rewritten_at and info.get("repair_rewritten"):
        info["rewrite_seconds_per_symbol"] = (rewritten_at - found_at).total_seconds() / int(
            info["repair_rewritten"]  # type: ignore[arg-type]
        )
    return info


def scan_shards(
    args, names: list[str], *, restated: set[str], sample: set[str], named: set[str]
) -> dict[str, object]:
    """Compare backup and repaired tree shard by shard (one shard name across all years)."""
    empty = pd.DataFrame(columns=COLUMNS)
    scan: dict[str, object] = {
        "violations_n": 0,
        "violations_samples": [],
        "vendor_bar_n": 0,
        "vendor_bar_samples": [],
        "v2_bad": 0,
        "v2_strict": 0,
        "missing_after": 0,
        "added_after": 0,
        "seam_dates": {},
        "sample_eq": {},
        "before_named": {},
        "after_named": {},
    }
    for position, name in enumerate(names):
        before_groups = dict(tuple(load_shard(args.before, name).groupby("symbol")))
        after_groups = dict(tuple(load_shard(args.after, name).groupby("symbol")))
        for symbol in sorted(set(before_groups) | set(after_groups)):
            b = before_groups.get(symbol, empty)
            a = after_groups.get(symbol, empty)
            if symbol in named:
                scan["before_named"][symbol] = b  # type: ignore[index]
                scan["after_named"][symbol] = a  # type: ignore[index]
            if symbol in sample and len(b):
                scan["sample_eq"][symbol] = b.reset_index(drop=True).equals(  # type: ignore[index]
                    a.reset_index(drop=True)
                )
            if symbol not in restated:
                continue
            stats = compare_symbol(b, a)
            scan["violations_n"] += len(stats["violations"])  # type: ignore[operator, arg-type]
            scan["vendor_bar_n"] += len(stats["vendor_bar"])  # type: ignore[operator, arg-type]
            if len(scan["violations_samples"]) < 20:  # type: ignore[arg-type]
                scan["violations_samples"] += [  # type: ignore[operator]
                    {"symbol": symbol, **v}
                    for v in stats["violations"][:20]  # type: ignore[index]
                ]
            if len(scan["vendor_bar_samples"]) < 20:  # type: ignore[arg-type]
                scan["vendor_bar_samples"] += [  # type: ignore[operator]
                    {"symbol": symbol, **v}
                    for v in stats["vendor_bar"][:20]  # type: ignore[index]
                ]
            scan["missing_after"] += int(stats["missing_after"])  # type: ignore[operator, arg-type]
            scan["added_after"] += int(stats["added_after"])  # type: ignore[operator, arg-type]
            scan["v2_bad"] += sum(1 for item in stats["v2"] if item["bad"])  # type: ignore[operator, union-attr]
            scan["v2_strict"] += sum(1 for item in stats["v2"] if item["strict_bad"])  # type: ignore[operator, union-attr]
            day = seam_date(b, a)
            if day is not None:
                scan["seam_dates"][symbol] = day.strftime("%Y-%m-%d")  # type: ignore[index]
        if position % 20 == 0:
            print(f"shard {position}/{len(names)} compared", flush=True)
    return scan


def scan_shards_precision(
    args, names: list[str], *, restated: set[str], sample: set[str], window_start: pd.Timestamp
) -> dict[str, object]:
    """``--tol-mode precision`` scan: V1'/V2' classes for restated symbols, V4' for the sample."""
    empty = pd.DataFrame(columns=COLUMNS)
    scan: dict[str, object] = {
        "tol_mode": "precision",
        "window_start": str(window_start.date()),
        "rows": {kind: 0 for kind in PRECISION_CLASSES},
        "symbols": {kind: set() for kind in PRECISION_CLASSES},
        "unexplained_by_symbol": {},
        "samples": {kind: [] for kind in PRECISION_CLASSES},
        "v2p_rows": {kind: 0 for kind in PRECISION_CLASSES},
        "v2p_unexplained_symbols": [],
        "restated_checked": 0,
        "missing_after": 0,
        "added_after": 0,
        "sample_v4": {},
    }
    for position, name in enumerate(names):
        before_groups = dict(tuple(load_shard(args.before, name).groupby("symbol")))
        after_groups = dict(tuple(load_shard(args.after, name).groupby("symbol")))
        for symbol in sorted(set(before_groups) | set(after_groups)):
            b = before_groups.get(symbol, empty)
            a = after_groups.get(symbol, empty)
            if symbol in sample and len(b):
                scan["sample_v4"][symbol] = compare_sample_precision(  # type: ignore[index]
                    b.reset_index(drop=True), a.reset_index(drop=True), window_start
                )
            if symbol not in restated:
                continue
            stats = compare_symbol_precision(b, a)
            scan["restated_checked"] += 1  # type: ignore[operator]
            scan["missing_after"] += int(stats["missing_after"])  # type: ignore[operator, arg-type]
            scan["added_after"] += int(stats["added_after"])  # type: ignore[operator, arg-type]
            for event in stats["events"]:  # type: ignore[union-attr]
                kind = event["class"]
                scan["rows"][kind] += 1  # type: ignore[index]
                scan["symbols"][kind].add(symbol)  # type: ignore[index]
                if kind == "unexplained":
                    by_symbol = scan["unexplained_by_symbol"]
                    by_symbol[symbol] = by_symbol.get(symbol, 0) + 1  # type: ignore[attr-defined]
                if len(scan["samples"][kind]) < 20:  # type: ignore[index, arg-type]
                    scan["samples"][kind].append({"symbol": symbol, **event})  # type: ignore[index]
                if event["year_boundary"]:
                    scan["v2p_rows"][kind] += 1  # type: ignore[index]
                    if kind == "unexplained":
                        scan["v2p_unexplained_symbols"].append(symbol)  # type: ignore[attr-defined]
        if position % 20 == 0:
            print(f"shard {position}/{len(names)} compared (precision)", flush=True)
    return scan


def merge_precision_scans(scans: list[dict[str, object]]) -> dict[str, object]:
    """Combine the per-segment precision scans into one set of totals."""
    starts = {str(x["window_start"]) for x in scans}
    if len(starts) != 1:
        raise SystemExit(f"scan segments disagree on the V4 window start: {sorted(starts)}")
    merged: dict[str, object] = {
        "window_start": starts.pop(),
        "rows": {kind: sum(x["rows"][kind] for x in scans) for kind in PRECISION_CLASSES},  # type: ignore[index]
        "symbols": {
            kind: sorted(set().union(*(x["symbols"][kind] for x in scans)))  # type: ignore[index]
            for kind in PRECISION_CLASSES
        },
        "v2p_rows": {kind: sum(x["v2p_rows"][kind] for x in scans) for kind in PRECISION_CLASSES},  # type: ignore[index]
        "v2p_unexplained_symbols": sorted(
            {s for x in scans for s in x["v2p_unexplained_symbols"]}  # type: ignore[union-attr]
        ),
        "restated_checked": sum(x["restated_checked"] for x in scans),  # type: ignore[misc]
        "missing_after": sum(x["missing_after"] for x in scans),  # type: ignore[misc]
        "added_after": sum(x["added_after"] for x in scans),  # type: ignore[misc]
    }
    by_symbol: dict[str, int] = {}
    sample_v4: dict[str, dict[str, object]] = {}
    samples: dict[str, list] = {kind: [] for kind in PRECISION_CLASSES}
    for x in scans:
        for symbol, count in x["unexplained_by_symbol"].items():  # type: ignore[attr-defined]
            by_symbol[symbol] = by_symbol.get(symbol, 0) + count
        sample_v4.update(x["sample_v4"])  # type: ignore[arg-type]
        for kind in PRECISION_CLASSES:
            samples[kind] += x["samples"][kind]  # type: ignore[index]
    merged["unexplained_by_symbol"] = by_symbol
    merged["sample_v4"] = sample_v4
    merged["samples"] = {kind: samples[kind][:20] for kind in PRECISION_CLASSES}
    return merged


def precision_result(
    merged: dict[str, object], *, restated_n: int, sample: list[str], sample_size: int
) -> dict[str, object]:
    """New archive-repair.json fields for ``--tol-mode precision`` (acceptance, step 4)."""
    rows = merged["rows"]
    symbols = merged["symbols"]
    by_symbol = merged["unexplained_by_symbol"]
    sample_v4 = merged["sample_v4"]
    checked = [s for s in sample if s in sample_v4][:sample_size]  # type: ignore[operator]
    window_diff: dict[str, int] = {}
    one_sided = 0
    for symbol in checked:
        item = sample_v4[symbol]  # type: ignore[index]
        one_sided += int(item["window_one_sided_rows"])
        for column, count in item["window_diff"].items():
            window_diff[column] = window_diff.get(column, 0) + int(count)
    differing = [s for s in checked if not sample_v4[s]["identical_before_window"]]  # type: ignore[index]
    unexplained_symbols = len(symbols["unexplained"])  # type: ignore[index]
    revision_symbols = len(symbols["factor_revision"])  # type: ignore[index]
    v2p_unexplained = int(merged["v2p_rows"]["unexplained"])  # type: ignore[index]
    v4p = not differing and len(checked) >= sample_size
    limit_unexplained = int(0.01 * restated_n)
    limit_revision = int(0.10 * restated_n)
    passed = (
        unexplained_symbols <= limit_unexplained
        and revision_symbols <= limit_revision
        and v2p_unexplained == 0
        and v4p
    )
    return {
        "tol_mode": "precision",
        "v1p_counts": {
            kind: {"rows": int(rows[kind]), "symbols": len(symbols[kind])}  # type: ignore[index]
            for kind in PRECISION_CLASSES
        },
        "v1p_unexplained_symbols": unexplained_symbols,
        "v1p_unexplained_symbols_limit": limit_unexplained,
        "v1p_factor_revision_symbols": revision_symbols,
        "v1p_factor_revision_symbols_limit": limit_revision,
        "v1p_top_unexplained": [
            {"symbol": s, "rows": c}
            for s, c in sorted(by_symbol.items(), key=lambda kv: (-kv[1], kv[0]))[:20]  # type: ignore[attr-defined]
        ],
        "v1p_samples": merged["samples"],
        "v1p_restated_symbols_checked": merged["restated_checked"],
        "v1p_dates_missing_after": merged["missing_after"],
        "v1p_dates_added_after": merged["added_after"],
        "v2p_rows": merged["v2p_rows"],
        "v2p_unexplained": v2p_unexplained,
        "v2p_unexplained_symbols": merged["v2p_unexplained_symbols"],
        "v4p_window_start": merged["window_start"],
        "v4p_checked_symbols": len(checked),
        "v4p_identical_before_window": v4p,
        "v4p_differing_symbols": differing[:20],
        "v4p_window_field_diff_rows": window_diff,
        "v4p_window_one_sided_rows": one_sided,
        "verify_v2_pass": passed,
    }


def run_precision(args, restated: list[str], sample: list[str]) -> int:
    """Segment scan or merge for ``--tol-mode precision``; the merge writes the new fields."""
    if args.merge_scans:
        merged = merge_precision_scans([pickle.loads(p.read_bytes()) for p in args.merge_scans])
        result = precision_result(
            merged, restated_n=len(restated), sample=sample, sample_size=args.sample
        )
        target = args.report_dir / "archive-repair.json"
        existing = json.loads(target.read_text(encoding="utf-8")) if target.exists() else {}
        existing.update(result)
        existing["tests_passed"] = args.tests_passed == "true"
        existing["precision_verified_at"] = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        existing["backup_sha256_ok"] = sha_ok(
            args.report_dir / "sip-daily-backup-sha256.json", args.before
        )
        target.write_text(
            json.dumps(existing, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8"
        )
        print(json.dumps({k: v for k, v in result.items() if k != "v1p_samples"}, default=str))
        return 0
    last, window_start = archive_window_start(args.after)
    names = sorted({p.name for p in args.after.glob("*/shard-*.parquet")})
    first, stop = (int(x) for x in args.shards.split(":")) if args.shards else (0, len(names))
    scan = scan_shards_precision(
        args,
        names[first:stop],
        restated=set(restated),
        sample=set(sample),
        window_start=window_start,
    )
    if not args.scan_out:
        raise SystemExit("--tol-mode precision needs --scan-out (segment) or --merge-scans")
    args.scan_out.write_bytes(pickle.dumps(scan))
    print(
        f"scan {args.shards} written to {args.scan_out}; "
        f"last date {last.date()}, window {window_start.date()}"
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--before", type=Path, required=True)
    parser.add_argument("--after", type=Path, default=Path("data/sip/daily"))
    parser.add_argument("--report-dir", type=Path, required=True)
    parser.add_argument("--log", type=Path, required=True)
    parser.add_argument("--tests-passed", choices=["true", "false"], required=True)
    parser.add_argument("--sample", type=int, default=200)
    parser.add_argument("--seed", type=int, default=20261002)
    parser.add_argument("--shards", default=None, help="first:last slice of shard file names.")
    parser.add_argument("--scan-out", type=Path, default=None, help="Write the scan and stop.")
    parser.add_argument("--merge-scans", type=Path, nargs="*", default=None)
    parser.add_argument(
        "--rounding-abs",
        type=float,
        default=ROUNDING_ABS,
        help="Absolute price rounding allowance in the V1 tolerance (default 2.5e-4).",
    )
    parser.add_argument(
        "--tol-mode",
        choices=["rounding-abs", "precision"],
        default="rounding-abs",
        help=(
            "rounding-abs: legacy 2.5e-4/price tolerance (reproduces the first run). "
            "precision: per-price decimals tolerance with date_set/bar_correction/"
            "factor_revision/unexplained classes (V1', V2', V4')."
        ),
    )
    parser.add_argument("--budget-min", type=float, default=25.0)
    args = parser.parse_args()
    report_dir = args.report_dir

    lines = read_restatements(args.after / "_restatements.jsonl")
    restated = sorted({line["symbol"] for line in lines})
    layout = json.loads((args.after / "_LAYOUT.json").read_text(encoding="utf-8"))
    universe = sorted({s for symbols in layout["shard_symbols"].values() for s in symbols})
    candidates = [s for s in universe if s not in set(restated)]
    random.Random(args.seed).shuffle(candidates)
    sample = candidates[: args.sample + 60]

    if args.tol_mode == "precision":
        return run_precision(args, restated, sample)
    sleeve = load_sleeve_symbols()
    globals()["ROUNDING_ABS"] = args.rounding_abs
    if args.merge_scans:
        scans = [pickle.loads(path.read_bytes()) for path in args.merge_scans]
    else:
        names = sorted({p.name for p in args.after.glob("*/shard-*.parquet")})
        first, last = (int(x) for x in args.shards.split(":")) if args.shards else (0, len(names))
        scans = [
            scan_shards(
                args,
                names[first:last],
                restated=set(restated),
                sample=set(sample),
                named=set(sleeve) | {"APH"},
            )
        ]
        if args.scan_out:
            args.scan_out.write_bytes(pickle.dumps(scans[0]))
            print(f"scan {args.shards} written to {args.scan_out}")
            return 0
    violations_n = sum(x["violations_n"] for x in scans)
    violations = [item for x in scans for item in x["violations_samples"]][:20]
    vendor_bar_n = sum(x["vendor_bar_n"] for x in scans)
    vendor_bar = [item for x in scans for item in x["vendor_bar_samples"]][:20]
    v2_bad = sum(x["v2_bad"] for x in scans)
    v2_strict = sum(x["v2_strict"] for x in scans)
    missing_after = sum(x["missing_after"] for x in scans)
    added_after = sum(x["added_after"] for x in scans)
    seam_dates: dict[str, str] = {}
    sample_eq: dict[str, bool] = {}
    before_groups: dict[str, pd.DataFrame] = {}
    after_groups: dict[str, pd.DataFrame] = {}
    for x in scans:
        seam_dates.update(x["seam_dates"])
        sample_eq.update(x["sample_eq"])
        before_groups.update(x["before_named"])
        after_groups.update(x["after_named"])
    checked = [s for s in sample if s in sample_eq][: args.sample]
    identical = sum(1 for s in checked if sample_eq[s])
    diff_symbols = [s for s in checked if not sample_eq[s]]

    sb = json.loads((report_dir / "seams-before.json").read_text())
    sa = json.loads((report_dir / "seams-after.json").read_text())
    aph_b = before_groups.get("APH")
    aph_a = after_groups.get("APH")

    def pair_ratio(frame: pd.DataFrame | None) -> float | None:
        if frame is None:
            return None
        dates = frame["timestamp"].dt.tz_localize(None).dt.normalize()
        prev = frame.loc[dates == pd.Timestamp("2026-08-26"), "close"]
        cur = frame.loc[dates == pd.Timestamp("2026-08-27"), "close"]
        return float(cur.iloc[0] / prev.iloc[0]) if len(prev) and len(cur) else None

    after_detail = {item["symbol"] for item in sa["seams_since"]}
    still_seam = sorted(after_detail & set(SEAM_FREE))
    reasons = {
        s: [
            {k: line.get(k) for k in ("mode", "refetch_empty", "years_rewritten", "max_rel_diff")}
            for line in lines
            if line["symbol"] == s
        ]
        for s in still_seam
    }

    max_diff: dict[str, float] = {}
    for line in lines:
        max_diff[line["symbol"]] = max(
            float(line.get("max_rel_diff", 0.0)), max_diff.get(line["symbol"], 0.0)
        )
    sleeve_restated = {s: max_diff[s] for s in sleeve if s in max_diff}
    shift: dict[str, dict[str, object]] = {}
    for symbol in sleeve_restated:
        entry: dict[str, object] = {}
        for horizon in (63, 252):
            rb = window_return(before_groups[symbol], "2026-10-01", horizon)
            ra = window_return(after_groups[symbol], "2026-10-01", horizon)
            entry[f"ret{horizon}_before"] = rb
            entry[f"ret{horizon}_after"] = ra
            entry[f"shift_pp_{horizon}"] = None if rb is None or ra is None else (ra - rb) * 100.0
        shift[symbol] = entry

    log_info = parse_log(args.log)
    per_symbol_min = float(log_info.get("rewrite_seconds_per_symbol", 0.0)) / 60.0
    sessions = 19  # nightly runs 2026-09-04 .. 2026-10-01 (20 weekdays, Labor Day excluded)
    n_seam = len(seam_dates)
    avg_daily = n_seam / sessions
    peak_week = sorted(s for s, d in seam_dates.items() if "2026-09-24" <= d <= "2026-09-30")
    peak_min = len(peak_week) * per_symbol_min
    fit = int(args.budget_min / per_symbol_min) if per_symbol_min > 0 else len(peak_week)
    ordering = sorted(peak_week, key=lambda s: (0 if s in set(sleeve) else 1, s))
    result = {
        "restated_symbols": len(restated),
        "years_rewritten_total": sum(len(line["years_rewritten"]) for line in lines),
        "rows_without_shard_total": sum(int(line["rows_without_shard"]) for line in lines),
        "refetch_empty_count": sum(1 for line in lines if line["refetch_empty"]),
        "restatement_modes": sorted({line["mode"] for line in lines}),
        "seams_by_month_before": sb["seams_by_month"],
        "seams_by_month_after": sa["seams_by_month"],
        "v1_violations": violations_n,
        "v1_samples": violations[:20],
        "v1_vendor_bar_corrections": vendor_bar_n,
        "v1_vendor_bar_samples": vendor_bar[:20],
        "v1_vendor_bar_within_1pct_of_restated": vendor_bar_n <= 0.01 * max(1, len(restated)),
        "v1_dates_missing_after": missing_after,
        "v1_dates_added_after": added_after,
        "v2_year_boundary_violations": v2_bad,
        "v2_year_boundary_violations_strict_1e-6": v2_strict,
        "aph_0827_ratio_before": pair_ratio(aph_b),
        "aph_0827_ratio_after": pair_ratio(aph_a),
        "spot": {
            "before": {s: sb["spot_max_abs_ln_pr_since"].get(s) for s in SPOT},
            "after": {s: sa["spot_max_abs_ln_pr_since"].get(s) for s in SPOT},
        },
        "v3_seam_free_symbols_still_listed": still_seam,
        "v3_seam_free_reasons": reasons,
        "v3_sept_seams_after": sa["seams_by_month"].get("2026-09", 0),
        "v3_max_month_jan_aug_after": max(
            [v for k, v in sa["seams_by_month"].items() if k < "2026-09"] or [0]
        ),
        "v4_unrestated_identical": not diff_symbols and len(checked) >= args.sample,
        "v4_checked_symbols": len(checked),
        "v4_identical_symbols": identical,
        "v4_differing_symbols": diff_symbols[:20],
        "sleeve_symbols_restated": sleeve_restated,
        "sleeve_symbols_all": sleeve,
        "sleeve_return_shift": shift,
        "tests_passed": args.tests_passed == "true",
        "backup_sha256_ok": sha_ok(report_dir / "sip-daily-backup-sha256.json", args.before),
        "api_calls": log_info.get("api_calls"),
        "elapsed_min": log_info.get("elapsed_min"),
        "rewrite_seconds_per_symbol": log_info.get("rewrite_seconds_per_symbol"),
        "seam_dates_restated_count": n_seam,
        "nightly_rewrite_min_est": avg_daily * per_symbol_min,
        "nightly_rewrite_min_est_t21_23_per_day": 23 * per_symbol_min,
        "nightly_rewrite_min_peak": peak_min,
        "peak_week_symbols": len(peak_week),
        "peak_week_symbols_over_budget": ordering[fit:] if peak_min > args.budget_min else [],
        "notes": "result is pending main-agent review (待主审)",
    }
    out = report_dir / "archive-repair.json"
    out.write_text(
        json.dumps(result, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                k: result[k]
                for k in (
                    "restated_symbols",
                    "v1_violations",
                    "v1_vendor_bar_corrections",
                    "v2_year_boundary_violations",
                    "v4_unrestated_identical",
                    "aph_0827_ratio_after",
                    "backup_sha256_ok",
                )
            },
            default=str,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
