"""Enforce the local retention policy on the SIP parquet archive.

The user's storage split is: Drive (5 TiB) holds the cold backup, this 217GB box
holds only the working set -- 10 years of daily bars and 3.5 years of minute bars.
Minute data grows at roughly 11GB per year of full-market coverage, so without a
prune step the box fills up and the fetch stalls.

Deletion is guarded three ways: it is dry-run by default, it only ever drops
directories that fall *entirely* outside the retention window, and it refuses to
delete anything that is not already present in the Drive cold backup.
"""

from __future__ import annotations

import argparse
import json
import logging
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

LOG = logging.getLogger("prune_sip")
DEFAULT_ROOT = Path("data/sip")
DEFAULT_REMOTE_ROOT = "datasets/sip"

# Retention in days. 3.5 years of minute bars and 10 years of daily bars is the
# split the user asked for; the Drive copy keeps 10 years of both.
RETENTION_DAYS = {"daily": 3653, "minute": 1278}


@dataclass(frozen=True)
class PruneUnit:
    """One prunable directory: a whole year (daily) or one year-month (minute)."""

    kind: str
    year: int
    month: int | None
    path: Path
    bytes_used: int

    @property
    def label(self) -> str:
        return f"{self.kind}/{self.year}" + (f"/{self.month:02d}" if self.month else "")

    @property
    def remote_suffix(self) -> str:
        return self.label


def _dir_bytes(path: Path) -> int:
    return sum(p.stat().st_size for p in path.rglob("*") if p.is_file())


def _covered_end(year: int, month: int | None) -> datetime:
    """The first instant *after* the data this unit contains."""
    if month is None:
        return datetime(year + 1, 1, 1, tzinfo=UTC)
    if month == 12:
        return datetime(year + 1, 1, 1, tzinfo=UTC)
    return datetime(year, month + 1, 1, tzinfo=UTC)


def discover_units(root: Path, kind: str) -> list[PruneUnit]:
    base = root / kind
    if not base.is_dir():
        return []
    units: list[PruneUnit] = []
    for year_dir in sorted(base.iterdir()):
        if not year_dir.is_dir() or not year_dir.name.isdigit():
            continue
        year = int(year_dir.name)
        month_dirs = [d for d in sorted(year_dir.iterdir()) if d.is_dir() and d.name.isdigit()]
        if month_dirs:
            for month_dir in month_dirs:
                units.append(
                    PruneUnit(kind, year, int(month_dir.name), month_dir, _dir_bytes(month_dir))
                )
        else:
            # Whole-year layout: only prunable as a unit, so it survives until the
            # entire year has aged out of the window.
            units.append(PruneUnit(kind, year, None, year_dir, _dir_bytes(year_dir)))
    return units


def select_expired(units: list[PruneUnit], *, now: datetime) -> list[PruneUnit]:
    expired = []
    for unit in units:
        horizon_days = RETENTION_DAYS[unit.kind]
        age_days = (now - _covered_end(unit.year, unit.month)).days
        if age_days > horizon_days:
            expired.append(unit)
    return expired


def remote_has(remote_root: str, suffix: str) -> bool:
    """Ask the gdrive service whether the cold backup already holds this unit."""
    path = f"{remote_root}/{suffix}"
    try:
        proc = subprocess.run(
            ["gdrive", "ls", "--json", path],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        LOG.warning("remote check failed for %s (%s); treating as absent", path, exc)
        return False
    if proc.returncode != 0:
        return False
    try:
        payload = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError:
        return False
    return int(payload.get("count", 0)) > 0


def run(
    *,
    root: Path,
    remote_root: str,
    now: datetime,
    apply: bool,
    require_remote: bool,
) -> int:
    units = [u for kind in RETENTION_DAYS for u in discover_units(root, kind)]
    expired = select_expired(units, now=now)

    plan = []
    freed = 0
    for unit in expired:
        backed_up = remote_has(remote_root, unit.remote_suffix) if require_remote else None
        deletable = backed_up is not False
        plan.append(
            {
                "unit": unit.label,
                "path": str(unit.path),
                "bytes": unit.bytes_used,
                "remote_backup": backed_up,
                "deletable": deletable,
            }
        )
        if deletable:
            freed += unit.bytes_used

    for entry in plan:
        verb = "DELETE" if entry["deletable"] else "KEEP (no remote backup)"
        LOG.info("%-28s %8.1f MiB  %s", entry["unit"], entry["bytes"] / 1048576, verb)

    if apply:
        for entry in plan:
            if entry["deletable"]:
                shutil.rmtree(entry["path"], ignore_errors=True)
        LOG.info(
            "deleted %d units, freed %.1f MiB", sum(e["deletable"] for e in plan), freed / 1048576
        )
    else:
        LOG.info(
            "dry run: %d/%d expired units deletable, would free %.1f MiB (pass --apply to delete)",
            sum(e["deletable"] for e in plan),
            len(plan),
            freed / 1048576,
        )

    print(json.dumps({"retention_days": RETENTION_DAYS, "applied": apply, "plan": plan}, indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--remote-root", default=DEFAULT_REMOTE_ROOT)
    parser.add_argument("--apply", action="store_true", help="Actually delete; default is dry run.")
    parser.add_argument(
        "--no-remote-check",
        action="store_true",
        help="Skip the Drive cold-backup precondition. Only for archives you know are disposable.",
    )
    parser.add_argument("--now", default=None, help="Override the reference date (ISO-8601).")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s", stream=sys.stdout)
    now = datetime.fromisoformat(args.now).replace(tzinfo=UTC) if args.now else datetime.now(UTC)
    return run(
        root=args.root,
        remote_root=args.remote_root,
        now=now,
        apply=args.apply,
        require_remote=not args.no_remote_check,
    )


if __name__ == "__main__":
    raise SystemExit(main())
