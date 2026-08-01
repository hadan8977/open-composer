from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Any

from open_composer.adapters.data.alpaca import AlpacaDataError
from open_composer.adapters.data.alpaca_snapshot import (
    AlpacaSnapshotContract,
    materialize_alpaca_contract_snapshot,
    verify_alpaca_contract_snapshot,
)
from open_composer.market_calendar import NEW_YORK, us_equity_session_close
from open_composer.research.multiasset_paper_control_r7 import SPEC_PATHS, verify_r7_lock

ITER_ID = "mom_multiasset_paper_control_r7"
FORWARD_EPOCH = date(2026, 8, 3)
TEMPLATE_PATH = Path(
    "reports/research/iterations/mom_multiasset_paper_control_r7/snapshot-contract.json"
)
FORWARD_FAMILY_DIR = Path("reports/forward/us_multiasset_paper_control_r7_family")
FORWARD_CONTRACT_DIR = FORWARD_FAMILY_DIR / "snapshot-contracts"
FORWARD_SNAPSHOT_DIR = Path("data/forward/alpaca_multiasset_paper_control_r7")
MIN_SNAPSHOT_AFTER_CLOSE_LAG = timedelta(minutes=15)


@dataclass(frozen=True)
class R7ForwardSnapshotResult:
    market_session: date
    contract_path: Path
    manifest_path: Path
    reused_snapshot: bool


@dataclass(frozen=True)
class R7ForwardObservationCycleResult:
    snapshot: R7ForwardSnapshotResult
    observation: Any


def build_r7_forward_snapshot_contract(root: Path, session: date) -> dict[str, Any]:
    base = root.resolve()
    if session < FORWARD_EPOCH or us_equity_session_close(session) is None:
        raise ValueError("R7 forward snapshot requires an eligible US trading session")

    template_path = _resolve_regular_root_file(base, TEMPLATE_PATH, "R7 snapshot template")
    template = _load_json(template_path)
    try:
        validated_template = AlpacaSnapshotContract.model_validate(template)
    except ValueError as exc:
        raise ValueError(f"R7 snapshot template is invalid: {exc}") from exc
    if validated_template.iter_id != ITER_ID:
        raise ValueError("R7 snapshot template iteration identity mismatch")

    payload = json.loads(json.dumps(template))
    payload["latest_frozen_session"] = session.isoformat()
    payload["immutable_output_root"] = _snapshot_relative_dir(session).as_posix()
    daily = payload.get("timeframes", {}).get("daily")
    if not isinstance(daily, dict):
        raise ValueError("R7 snapshot template requires one daily timeframe")
    daily["requested_end_exclusive"] = datetime.combine(
        session + timedelta(days=1), time.min, tzinfo=NEW_YORK
    ).isoformat()
    try:
        AlpacaSnapshotContract.model_validate(payload)
    except ValueError as exc:
        raise ValueError(f"derived R7 forward snapshot contract is invalid: {exc}") from exc
    return payload


def prepare_r7_forward_snapshot_contract(root: Path, session: date) -> Path:
    base = root.resolve()
    verify_r7_lock(base)
    payload = build_r7_forward_snapshot_contract(base, session)
    path = base / _contract_relative_path(session)
    _write_immutable_json(base, path, payload)
    return path


def validate_r7_forward_snapshot_contract(
    root: Path,
    manifest: dict[str, Any],
    session: date,
) -> Path:
    base = root.resolve()
    expected_relative = _contract_relative_path(session)
    if manifest.get("contract_path") != expected_relative.as_posix():
        raise ValueError("R7 forward snapshot contract path mismatch")
    if manifest.get("output_root") != _snapshot_relative_dir(session).as_posix():
        raise ValueError("R7 forward snapshot output root mismatch")

    contract_path = _resolve_regular_root_file(base, expected_relative, "R7 forward contract")
    contract_bytes = contract_path.read_bytes()
    if hashlib.sha256(contract_bytes).hexdigest() != manifest.get("contract_sha256"):
        raise ValueError("R7 forward snapshot contract SHA-256 mismatch")
    actual = _load_json(contract_path)
    expected = build_r7_forward_snapshot_contract(base, session)
    if _canonical_json_bytes(actual) != _canonical_json_bytes(expected):
        raise ValueError("R7 forward snapshot contract changed outside allowed session fields")
    return contract_path


def materialize_r7_forward_snapshot(
    root: Path,
    *,
    as_of: datetime,
    client: Any | None = None,
) -> R7ForwardSnapshotResult:
    base = root.resolve()
    observed_at = _as_utc(as_of)
    session = latest_available_r7_session(observed_at)
    contract_path = prepare_r7_forward_snapshot_contract(base, session)
    manifest_path = base / _snapshot_relative_dir(session) / "snapshot-manifest.json"
    reused = manifest_path.exists()
    if reused:
        manifest = verify_alpaca_contract_snapshot(base, manifest_path)
    else:
        if manifest_path.parent.exists():
            raise AlpacaDataError("incomplete R7 forward snapshot directory already exists")
        manifest_path = materialize_alpaca_contract_snapshot(
            base,
            contract_path,
            client=client,
            retrieved_at=observed_at,
        )
        manifest = verify_alpaca_contract_snapshot(base, manifest_path)
    validate_r7_forward_snapshot_contract(base, manifest, session)
    return R7ForwardSnapshotResult(
        market_session=session,
        contract_path=contract_path,
        manifest_path=manifest_path,
        reused_snapshot=reused,
    )


def run_r7_forward_observation_cycle(
    root: Path,
    *,
    client: Any | None = None,
    clock: Callable[[], datetime] | None = None,
) -> R7ForwardObservationCycleResult:
    from open_composer.adapters.execution.multiasset_paper_control_r7_target_weights import (
        run_multiasset_paper_control_r7_target_weight_mapping,
    )

    now = clock or (lambda: datetime.now(UTC))
    snapshot = materialize_r7_forward_snapshot(root, as_of=now(), client=client)
    observation = run_multiasset_paper_control_r7_target_weight_mapping(
        root.resolve() / SPEC_PATHS["R7D01"],
        root,
        snapshot_manifest_path=snapshot.manifest_path,
        as_of=now(),
    )
    return R7ForwardObservationCycleResult(snapshot=snapshot, observation=observation)


def latest_available_r7_session(as_of: datetime) -> date:
    observed_at = _as_utc(as_of)
    candidate = observed_at.astimezone(NEW_YORK).date()
    while True:
        close = us_equity_session_close(candidate)
        if close is not None:
            available_at = (
                datetime.combine(candidate, close, tzinfo=NEW_YORK).astimezone(UTC)
                + MIN_SNAPSHOT_AFTER_CLOSE_LAG
            )
            if observed_at >= available_at:
                break
        candidate -= timedelta(days=1)
    if candidate < FORWARD_EPOCH:
        raise ValueError("R7 forward snapshot cannot begin before 2026-08-03")
    return candidate


def _contract_relative_path(session: date) -> Path:
    return FORWARD_CONTRACT_DIR / f"{session.isoformat()}.json"


def _snapshot_relative_dir(session: date) -> Path:
    return FORWARD_SNAPSHOT_DIR / session.isoformat()


def _write_immutable_json(root: Path, path: Path, payload: dict[str, Any]) -> None:
    content = json.dumps(payload, indent=2, sort_keys=True, allow_nan=False).encode("utf-8") + b"\n"
    safe_path = _resolve_new_root_path(root, path, "R7 forward contract")
    if safe_path.exists():
        if safe_path.is_symlink() or not safe_path.is_file() or safe_path.read_bytes() != content:
            raise ValueError("R7 forward snapshot contract already exists with different bytes")
        return
    safe_path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(safe_path, flags, 0o400)
    try:
        view = memoryview(content)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise OSError("short write while publishing R7 forward contract")
            view = view[written:]
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _resolve_new_root_path(root: Path, path: Path, label: str) -> Path:
    base = root.resolve()
    candidate = path if path.is_absolute() else base / path
    try:
        relative = candidate.relative_to(base)
    except ValueError as exc:
        raise ValueError(f"{label} escapes the repository") from exc
    current = base
    for part in relative.parts[:-1]:
        current /= part
        if current.is_symlink():
            raise ValueError(f"{label} has a symlinked parent")
    return candidate


def _resolve_regular_root_file(root: Path, relative: Path, label: str) -> Path:
    candidate = root / relative
    resolved = candidate.resolve(strict=True)
    try:
        resolved.relative_to(root.resolve())
    except ValueError as exc:
        raise ValueError(f"{label} escapes the repository") from exc
    if candidate.is_symlink() or not resolved.is_file():
        raise ValueError(f"{label} must be a regular file")
    return resolved


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"R7 JSON artifact must be an object: {path}")
    return payload


def _canonical_json_bytes(payload: dict[str, Any]) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("R7 forward snapshot time must be timezone-aware")
    return value.astimezone(UTC)
