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
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from update_sip_archive import load_sleeve_symbols  # noqa: E402

COLUMNS = ["symbol", "timestamp", "open", "high", "low", "close", "volume", "trade_count", "vwap"]
V1_START = pd.Timestamp("2016-01-04")
V1_END = pd.Timestamp("2026-08-24")
ROUNDING_ABS = 2.5e-4
RET_TOL = 1e-6
VOLUME_RATIO_TOL = 1e-4
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
