# ruff: noqa: E501
"""Write ``postmortem/run-manifest.json`` for T-20261001-19: sha256, rows and first/last dates of every
raw output file of the 30 preregistered paths ``PM_{L1|L2c|L2a}_{M0_A|M1_C}_o{k}``."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PM_DIR = ROOT / "reports/research/iterations/t20261001_book_v1/postmortem"
CACHE = PM_DIR / "cache"
DATE_COL = {
    "daily.parquet": "trade_date",
    "targets.parquet": "decision_date",
    "records.parquet": "date",
}


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    expected = [
        f"PM_{r}_{v}_o{k}" for r in ("L1", "L2c", "L2a") for v in ("M0_A", "M1_C") for k in range(5)
    ]
    found = {d.name: d for d in CACHE.glob("shard_*/PM_*")}
    missing = [p for p in expected if p not in found]
    files: dict[str, dict] = {}
    incomplete: list[str] = []
    for pid in expected:
        if pid not in found:
            continue
        d = found[pid]
        for f in sorted(d.iterdir()):
            rel = str(f.relative_to(PM_DIR))
            ent: dict = {"sha256": sha256(f), "bytes": f.stat().st_size}
            if f.suffix == ".parquet":
                df = pd.read_parquet(f)
                ent["rows"] = int(len(df))
                col = DATE_COL.get(f.name)
                if col and len(df):
                    s = pd.to_datetime(df[col])
                    ent["first_date"], ent["last_date"] = str(s.min().date()), str(s.max().date())
            files[rel] = ent
        meta = json.loads((d / "meta.json").read_text())
        dd = files[str((d / "daily.parquet").relative_to(PM_DIR))]
        if dd.get("last_date") != "2026-09-17" or dd.get("first_date") != "2017-10-02":
            incomplete.append(pid)
        files[str((d / "meta.json").relative_to(PM_DIR))]["n_rebalances"] = meta["n_rebalances"]
        files[str((d / "meta.json").relative_to(PM_DIR))]["n_failed_final"] = meta["n_failed_final"]
    when = subprocess.check_output(["date", "-u", "+%Y-%m-%dT%H:%M:%SZ"], text=True).strip()
    doc = {
        "task": "T-20261001-19",
        "written_at_utc": when,
        "expected_paths": len(expected),
        "found_paths": len(expected) - len(missing),
        "missing": missing,
        "incomplete": incomplete,
        "files": files,
    }
    (PM_DIR / "run-manifest.json").write_text(json.dumps(doc, indent=1) + "\n")
    print(
        f"found {doc['found_paths']}/30 missing={missing} incomplete={incomplete} files={len(files)}"
    )
    return 0 if not missing and not incomplete else 1


if __name__ == "__main__":
    raise SystemExit(main())
