"""Driver helpers for T-20261002-02 (price-based feature tables rebuilt on the repaired archive).

Subcommands (all read-only on ``data/features/<table>``; they write under the stage dir):

* ``universe-compose``: new 2026 universe partition = existing rows with
  ``month_end <= 2026-08-31`` plus staged rows with ``month_end >= 2026-09-30``;
  writes ``<stage>/<name>_composed/2026.parquet``, Jaccard diagnostics and the
  09-30 new-entrant list.
* ``key-diff``: key-set differences of two tables per zone (strict <= 2026-08-21,
  window 2026-08-24..<last old date>, new dates), split into rows explained by the
  archive one-sided (symbol, date) rows, by 09-30 new entrants, and the rest.
* ``swap``: back the current file up under ``data/live/backup-features-20261002/<table>/``
  and move the staged file into place; the sha256 before and after go to ``--record``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from datetime import datetime
from pathlib import Path

import polars as pl

KEEP_UNTIL = datetime(2026, 8, 31)
APPEND_FROM = datetime(2026, 9, 30)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 22), b""):
            digest.update(chunk)
    return digest.hexdigest()


def universe_compose(existing_root: Path, staged_root: Path, out_root: Path, label: str) -> dict:
    """Compose the 2026 partition and report membership diagnostics."""
    existing = pl.read_parquet(existing_root / "2026.parquet")
    staged = pl.read_parquet(staged_root / "2026.parquet")
    keep = existing.filter(pl.col("month_end") <= KEEP_UNTIL)
    append = staged.filter(pl.col("month_end") >= APPEND_FROM)
    composed = pl.concat([keep, append.select(keep.columns)]).sort(["month_end", "symbol"])
    out_dir = out_root
    out_dir.mkdir(parents=True, exist_ok=True)
    composed.write_parquet(out_dir / "2026.parquet")

    jaccard = {}
    for month_end in sorted(keep["month_end"].unique().to_list()):
        a = set(existing.filter(pl.col("month_end") == month_end)["symbol"].to_list())
        b = set(staged.filter(pl.col("month_end") == month_end)["symbol"].to_list())
        jaccard[str(month_end)[:10]] = {
            "existing": len(a),
            "staged": len(b),
            "jaccard": (len(a & b) / len(a | b)) if (a | b) else 1.0,
            "only_existing": len(a - b),
            "only_staged": len(b - a),
        }
    prior = set()
    for path in sorted(existing_root.glob("*.parquet")):
        if path.name[:4].isdigit():
            frame = pl.read_parquet(path, columns=["month_end", "symbol"])
            prior |= set(frame.filter(pl.col("month_end") <= KEEP_UNTIL)["symbol"].to_list())
    new_symbols = set(append["symbol"].to_list())
    entrants = sorted(new_symbols - prior)
    last_months = sorted(keep["month_end"].unique().to_list())[-3:]
    base = [
        keep.filter(pl.col("month_end") == m).height for m in last_months
    ]  # members in the last three kept month-ends
    return {
        "label": label,
        "kept_rows": keep.height,
        "appended_rows": append.height,
        "appended_month_ends": [
            str(m)[:10] for m in sorted(append["month_end"].unique().to_list())
        ],
        "composed_rows": composed.height,
        "members_0930": append.height,
        "baseline_members_last3": base,
        "coverage_ratio": append.height / (sum(base) / len(base)) if base else None,
        "jaccard_by_month_end": jaccard,
        "new_entrants_0930": entrants,
        "n_new_entrants_0930": len(entrants),
    }


ZONES = (
    ("strict_le_0821", datetime(1900, 1, 1), datetime(2026, 8, 21)),
    ("window_0824_to_old_last", datetime(2026, 8, 24), None),
)


def _keys(path: Path, date_col: str, key_col: str) -> pl.DataFrame:
    frame = pl.read_parquet(path, columns=[key_col, date_col])
    return frame.with_columns(pl.col(date_col).cast(pl.Datetime("us")).alias(date_col)).unique()


def key_diff(
    old: Path,
    new: Path,
    stage: Path,
    label: str,
    date_col: str = "trade_date",
    key_col: str = "symbol",
) -> dict:
    """Key-set differences between ``old`` and ``new`` per zone, attributed to known causes."""

    def pairs(name: str) -> set[tuple[str, str]]:
        out = set()
        for line in (stage / name).read_text().split():
            sym, day = line.split(",")
            out.add((sym, day))
        return out

    arch_new = pairs("archive_only_new_keys.txt")
    arch_old = pairs("archive_only_old_keys.txt")
    entrants = set()
    for name in ("new_entrants_0930_broad.txt", "new_entrants_0930_narrow.txt"):
        entrants |= set((stage / name).read_text().split())
    o = _keys(old, date_col, key_col)
    n = _keys(new, date_col, key_col)
    last_old = o[date_col].max()
    only_new = n.join(o, on=[key_col, date_col], how="anti")
    only_old = o.join(n, on=[key_col, date_col], how="anti")
    out: dict = {
        "table": label,
        "old": str(old),
        "new": str(new),
        "last_old_date": str(last_old)[:10],
        "zones": {},
    }
    for name, lo, hi in (*ZONES[:1], (ZONES[1][0], ZONES[1][1], last_old)):

        def in_zone(frame: pl.DataFrame, lo=lo, hi=hi) -> pl.DataFrame:
            cond = pl.col(date_col) >= lo
            if hi is not None:
                cond &= pl.col(date_col) <= hi
            return frame.filter(cond)

        zone: dict = {}
        for side, frame, arch in (
            ("only_new", in_zone(only_new), arch_new),
            ("only_old", in_zone(only_old), arch_old),
        ):
            rows = [(r[key_col], str(r[date_col])[:10]) for r in frame.to_dicts()]
            in_arch = [r for r in rows if r in arch]
            ent = [r for r in rows if r not in arch and r[0] in entrants]
            rest = [r for r in rows if r not in arch and r[0] not in entrants]
            by_symbol: dict[str, int] = {}
            for sym, _ in rest:
                by_symbol[sym] = by_symbol.get(sym, 0) + 1
            zone[side] = {
                "rows": len(rows),
                "in_archive_one_sided_rows": len(in_arch),
                "archive_one_sided_symbols": sorted({r[0] for r in in_arch}),
                "new_entrants_0930_rows": len(ent),
                "new_entrants_0930_symbols": len({r[0] for r in ent}),
                "unexplained_rows": len(rest),
                "unexplained_by_symbol": dict(
                    sorted(by_symbol.items(), key=lambda kv: -kv[1])[:10]
                ),
                "examples_archive": in_arch[:3],
                "examples_entrant": ent[:3],
                "examples_unexplained": rest[:3],
            }
        out["zones"][name] = zone
    n_dates = n.filter(pl.col(date_col) > last_old)[date_col].n_unique()
    out["new_dates_after_old_last"] = int(n_dates)
    return out


def swap(table: str, staged: Path, dest: Path, backup_root: Path, record: Path, note: str) -> dict:
    """Back ``dest`` up, move ``staged`` onto it, append the sha256 pair to ``record``."""
    backup = backup_root / table / dest.name
    backup.parent.mkdir(parents=True, exist_ok=True)
    if backup.exists():
        raise SystemExit(f"backup {backup} already exists; refusing to overwrite")
    sha_before = sha256_file(dest)
    shutil.copy2(dest, backup)
    if sha256_file(backup) != sha_before:
        raise SystemExit(f"backup of {dest} does not match")
    sha_staged = sha256_file(staged)
    staged.replace(dest)
    entry = {
        "table": table,
        "dest": str(dest),
        "backup": str(backup),
        "sha256_before": sha_before,
        "sha256_after": sha256_file(dest),
        "sha256_staged": sha_staged,
        "swapped_utc": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "note": note,
    }
    data = json.loads(record.read_text()) if record.exists() else {"swaps": []}
    data["swaps"].append(entry)
    record.write_text(json.dumps(data, indent=2) + "\n")
    return entry


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    comp = sub.add_parser("universe-compose")
    comp.add_argument("--existing", type=Path, required=True)
    comp.add_argument("--staged", type=Path, required=True)
    comp.add_argument("--out", type=Path, required=True)
    comp.add_argument("--label", required=True)
    comp.add_argument("--entrants-out", type=Path, required=True)
    comp.add_argument("--json-out", type=Path, required=True)
    kd = sub.add_parser("key-diff")
    kd.add_argument("--old", type=Path, required=True)
    kd.add_argument("--new", type=Path, required=True)
    kd.add_argument("--stage", type=Path, required=True)
    kd.add_argument("--label", required=True)
    kd.add_argument("--key-col", default="symbol")
    kd.add_argument("--json-out", type=Path, required=True)
    sw = sub.add_parser("swap")
    sw.add_argument("--table", required=True)
    sw.add_argument("--staged", type=Path, required=True)
    sw.add_argument("--dest", type=Path, required=True)
    sw.add_argument("--backup-root", type=Path, default=Path("data/live/backup-features-20261002"))
    sw.add_argument("--record", type=Path, required=True)
    sw.add_argument("--note", default="")
    args = parser.parse_args()
    if args.cmd == "key-diff":
        result = key_diff(args.old, args.new, args.stage, args.label, key_col=args.key_col)
        args.json_out.write_text(json.dumps(result, indent=2, default=str) + "\n")
        print(json.dumps(result["zones"], default=str)[:600])
        return 0
    if args.cmd == "swap":
        print(
            json.dumps(
                swap(args.table, args.staged, args.dest, args.backup_root, args.record, args.note)
            )
        )
        return 0
    if args.cmd == "universe-compose":
        result = universe_compose(args.existing, args.staged, args.out, args.label)
        args.entrants_out.write_text("\n".join(result["new_entrants_0930"]) + "\n")
        args.json_out.write_text(json.dumps(result, indent=2, default=str) + "\n")
        print(
            json.dumps(
                {
                    k: v
                    for k, v in result.items()
                    if k not in ("jaccard_by_month_end", "new_entrants_0930")
                }
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
