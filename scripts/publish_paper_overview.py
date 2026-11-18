"""Validate and atomically publish a caller-reconciled v1 paper overview.

This adapter preserves the input bytes and economic values. It does not acquire
broker data, recalculate a strategy, or expand the producer's accounting scope.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import tempfile
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

MAX_BYTES = 2_097_152
MONEY_TOLERANCE = Decimal("0.000001")
RETURN_TOLERANCE = Decimal("0.000001")  # Percentage points, not a fraction.
ROW_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]*(?:/[A-Za-z0-9][A-Za-z0-9_.:-]*)*\Z")


def _object(value: Any, name: str) -> dict:
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be an object")
    return value


def _number(value: Any, name: str, *, nullable: bool = False) -> Decimal | None:
    if value is None and nullable:
        return None
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"{name} must be a finite number" + (" or null" if nullable else ""))
    try:
        finite = math.isfinite(value)
    except OverflowError:
        finite = False
    if not finite:
        raise ValueError(f"{name} must be finite")
    return Decimal(str(value))


def _field(row: dict, key: str, name: str, *, nullable: bool = False) -> Decimal | None:
    if key not in row:
        raise ValueError(f"{name}.{key} is required")
    return _number(row[key], f"{name}.{key}", nullable=nullable)


def _strings(value: Any, name: str) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(x, str) or not x for x in value):
        raise ValueError(f"{name} must be a list of nonempty strings")
    return value


def _date(value: Any, name: str) -> date:
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ValueError(f"{name} must be YYYY-MM-DD")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be a valid date") from exc


def _timestamp(value: Any, name: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except (ValueError, TypeError) as exc:
        raise ValueError(f"{name} must be an aware timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{name} must be an aware timestamp")
    return parsed


def _same(actual: Decimal, expected: Decimal, name: str, tolerance=MONEY_TOLERANCE):
    if abs(actual - expected) > tolerance:
        raise ValueError(f"{name} does not reconcile")


def _return(row: dict, name: str, *, precise: bool = False):
    capital = _field(row, "capital_usd", name, nullable=True)
    pnl = _field(row, "pnl_usd", name, nullable=True)
    if capital is not None and capital < 0:
        raise ValueError(f"{name}.capital_usd must be nonnegative")
    if precise and "precise_pnl_usd" in row:
        precise_pnl = _field(row, "precise_pnl_usd", name, nullable=True)
        if (pnl is None) != (precise_pnl is None):
            raise ValueError(f"{name} has inconsistent missing PnL")
        if pnl is not None:
            _same(pnl, precise_pnl, f"{name}.rounded_pnl", Decimal("0.005001"))
        pnl = precise_pnl
    percent = _field(row, "return_pct", name, nullable=True)
    if pnl is None or capital is None or capital == 0:
        if percent is not None:
            raise ValueError(f"{name}.return_pct requires PnL and positive capital")
    elif percent is None:
        raise ValueError(f"{name}.return_pct is missing despite known PnL and capital")
    else:
        _same(percent, pnl / capital * 100, f"{name}.return_pct", RETURN_TOLERANCE)


def _coverage(row: dict, name: str):
    missing = _strings(row.get("missing"), f"{name}.missing")
    if bool(missing) != (row["pnl_usd"] is None):
        raise ValueError(f"{name}.missing must describe exactly a missing PnL")
    _strings(row.get("pools"), f"{name}.pools")
    if row["capital_usd"] is None:
        if not _strings(row.get("capital_missing"), f"{name}.capital_missing"):
            raise ValueError(f"{name}.capital_missing must describe missing capital")


def validate(data: Any) -> None:
    """Check publication invariants without changing or filling supplied values."""
    data = _object(data, "overview")
    if type(data.get("schema_version")) is not int or data["schema_version"] != 1:
        raise ValueError("schema_version must be 1")
    _timestamp(data.get("generated_at"), "generated_at")
    through = _date(data.get("through_session"), "through_session")
    snapshot = _object(data.get("snapshot"), "snapshot")
    for start, end in (("at_start", "at_end"), ("marks_start", "marks_end")):
        if _timestamp(snapshot.get(start), start) > _timestamp(snapshot.get(end), end):
            raise ValueError(f"{start} must not follow {end}")
    _return(snapshot, "snapshot")
    _coverage(snapshot, "snapshot")
    rows = snapshot.get("rows")
    if not isinstance(rows, list) or not rows:
        raise ValueError("snapshot.rows must be a nonempty list")
    ids = set()
    row_capital = Decimal(0)
    row_pnl = Decimal(0)
    missing_pnl = False
    for index, raw in enumerate(rows):
        name = f"snapshot.rows[{index}]"
        row = _object(raw, name)
        identity = row.get("id")
        if (
            not isinstance(identity, str)
            or len(identity) > 240
            or not ROW_ID.fullmatch(identity)
            or identity in ids
        ):
            raise ValueError(f"{name}.id must be a safe unique strategy ID")
        ids.add(identity)
        for field in ("label", "status", "pool"):
            if not isinstance(row.get(field), str) or not row[field].strip():
                raise ValueError(f"{name}.{field} must be a nonempty string")
        _date(row.get("first_day"), f"{name}.first_day")
        _return(row, name, precise=True)
        row_capital += _field(row, "capital_usd", name, nullable=True) or Decimal(0)
        pnl = _field(row, "pnl_usd", name, nullable=True)
        missing_pnl |= pnl is None
        row_pnl += pnl or Decimal(0)
    adjustment = _field(snapshot, "adjustment_usd", "snapshot", nullable=True)
    unassigned = _field(snapshot, "unassigned_capital_usd", "snapshot", nullable=True)
    total_pnl = _field(snapshot, "pnl_usd", "snapshot", nullable=True)
    capital = _field(snapshot, "capital_usd", "snapshot", nullable=True)
    if total_pnl is not None:
        if missing_pnl or adjustment is None:
            raise ValueError("snapshot PnL requires every row and the adjustment")
        _same(total_pnl, row_pnl + adjustment, "snapshot.pnl_usd")
    if unassigned is not None and unassigned < 0:
        raise ValueError("snapshot.unassigned_capital_usd must be nonnegative")
    if capital is not None:
        if unassigned is None:
            raise ValueError("snapshot capital requires unassigned capital")
        _same(capital, row_capital + unassigned, "snapshot.capital_usd")
    daily = data.get("daily")
    if not isinstance(daily, list) or not daily:
        raise ValueError("daily must be a nonempty list")
    previous = None
    for index, raw in enumerate(daily):
        name = f"daily[{index}]"
        point = _object(raw, name)
        day = _date(point.get("day"), f"{name}.day")
        if (previous is not None and day <= previous) or day > through:
            raise ValueError("daily dates must increase uniquely through through_session")
        previous = day
        _return(point, name)
        _coverage(point, name)


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _finite_tree(value):
    if isinstance(value, dict):
        for child in value.values():
            _finite_tree(child)
    elif isinstance(value, list):
        for child in value:
            _finite_tree(child)
    elif isinstance(value, int | float) and not isinstance(value, bool):
        _number(value, "JSON number")


def _read(path: Path) -> bytes:
    with path.open("rb") as stream:
        raw = stream.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError("overview exceeds 2 MiB")
    return raw


def _directory(root: Path, relative: str) -> Path:
    directory = root / relative
    if not directory.resolve().is_relative_to(root):
        raise ValueError("publication directory is outside the project root")
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _temporary(directory: Path, raw: bytes) -> Path:
    fd, name = tempfile.mkstemp(prefix=".paper-overview-", dir=directory)
    path = Path(name)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fchmod(stream.fileno(), 0o644)
            os.fsync(stream.fileno())
        return path
    except BaseException:
        path.unlink(missing_ok=True)
        raise


def publish(root: Path, input_path: Path) -> dict[str, str]:
    """Publish immutable bytes, then atomically switch the existing v1 binding."""
    root = root.resolve()
    raw = _read(input_path)
    try:
        data = json.loads(raw, object_pairs_hook=_unique_object)
        _finite_tree(data)
        validate(data)
    except (RecursionError, UnicodeDecodeError) as exc:
        raise ValueError("overview JSON is invalid or excessively nested") from exc
    digest = hashlib.sha256(raw).hexdigest()
    relative = f"reports/paper/overview/{digest}.json"
    artifacts = _directory(root, "reports/paper/overview")
    config = _directory(root, "config")
    artifact = root / relative
    temporary = _temporary(artifacts, raw)
    try:
        try:
            os.link(temporary, artifact)
        except FileExistsError:
            if artifact.is_symlink() or _read(artifact) != raw:
                raise ValueError("existing immutable overview does not match its digest") from None
    finally:
        temporary.unlink(missing_ok=True)
    binding = {"path": relative, "sha256": digest}
    temporary = _temporary(config, (json.dumps(binding, indent=2) + "\n").encode())
    try:
        os.replace(temporary, config / "paper-overview-dashboard.json")
    finally:
        temporary.unlink(missing_ok=True)
    return binding


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--input", type=Path, required=True, help="Caller-reconciled v1 overview")
    args = parser.parse_args()
    try:
        result = publish(args.root, args.input)
    except (OSError, ValueError) as exc:
        parser.exit(2, f"Publication failed: {exc}\n")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
