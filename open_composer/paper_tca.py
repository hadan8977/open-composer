from __future__ import annotations

import fcntl
import hashlib
import json
import math
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from open_composer.config import project_root
from open_composer.market_calendar import us_equity_session_close

DEFAULT_MIN_OBSERVATIONS = 30
DEFAULT_MIN_SESSIONS = 10
MAX_WEIGHTED_MEAN_ARRIVAL_SLIPPAGE_BPS = 20.0
MAX_P95_ARRIVAL_SLIPPAGE_BPS = 35.0
MAX_SINGLE_ARRIVAL_SLIPPAGE_BPS = 100.0
MAX_P95_FILL_LATENCY_MS = 15 * 60 * 1000.0
OBSERVATION_SCHEMA_VERSION = 1
LOCAL_HASH_AUTHENTICITY_CAVEAT = (
    "Local SHA-256 bindings detect changes to the referenced repository files, but they do "
    "not independently attest broker origin, exchange truth, or external authenticity."
)

_STRATEGY_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_REQUIRED_INPUT_FIELDS = {
    "strategy_name",
    "spec_hash",
    "execution_policy_id",
    "execution_policy_hash",
    "authorization_id",
    "authorization_hash",
    "broker_account_id_hash",
    "paper",
    "order_id",
    "fill_id",
    "client_order_id",
    "symbol",
    "side",
    "qty",
    "order_style",
    "time_in_force",
    "decision_price",
    "arrival_price",
    "fill_price",
    "decision_at",
    "submitted_at",
    "filled_at",
    "observed_at",
    "source_packet_path",
    "source_packet_sha256",
    "broker_receipt_path",
    "broker_receipt_sha256",
}
_OPTIONAL_INPUT_FIELDS = {
    "schema_version",
    "observation_id",
    "accepted_at",
    "official_open_price",
    "vwap_price",
    "signal_id",
    "currency",
    "venue",
    "metadata",
}
_INPUT_FIELDS = _REQUIRED_INPUT_FIELDS | _OPTIONAL_INPUT_FIELDS
_TIMESTAMP_FIELDS = ("decision_at", "submitted_at", "accepted_at", "filled_at", "observed_at")
_PRICE_FIELDS = (
    "decision_price",
    "arrival_price",
    "official_open_price",
    "vwap_price",
    "fill_price",
)
_SOURCE_PACKET_BINDINGS = (
    "strategy_name",
    "spec_hash",
    "execution_policy_id",
    "execution_policy_hash",
    "authorization_id",
    "authorization_hash",
    "broker_account_id_hash",
    "paper",
    "order_id",
    "client_order_id",
    "symbol",
    "side",
    "qty",
    "order_style",
    "time_in_force",
    "decision_price",
    "arrival_price",
    "decision_at",
    "submitted_at",
)
_BROKER_RECEIPT_BINDINGS = (
    "paper",
    "order_id",
    "fill_id",
    "symbol",
    "side",
    "qty",
    "fill_price",
    "submitted_at",
    "filled_at",
    "observed_at",
    "authorization_id",
    "authorization_hash",
    "broker_account_id_hash",
    "client_order_id",
    "order_style",
    "time_in_force",
)


class PaperTCAValidationError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code


@dataclass(frozen=True)
class PaperTCAIngestResult:
    ledger_path: Path
    observation_id: str
    appended: bool
    record: dict[str, Any]


def paper_tca_ledger_path(root: Path, strategy_name: str) -> Path:
    strategy = _require_strategy_name(strategy_name)
    return Path(root) / "reports" / "paper" / "tca" / f"{strategy}-observations.jsonl"


def ingest_paper_tca_observation(
    observation: Mapping[str, Any],
    *,
    root: Path | None = None,
    strategy_name: str,
    spec_hash: str,
    execution_policy_id: str,
    execution_policy_hash: str,
    as_of: datetime | None = None,
) -> PaperTCAIngestResult:
    base = Path(root or project_root()).resolve()
    cutoff = _as_utc(as_of or datetime.now(UTC), field="as_of")
    expected = _binding(
        strategy_name=strategy_name,
        spec_hash=spec_hash,
        execution_policy_id=execution_policy_id,
        execution_policy_hash=execution_policy_hash,
    )
    record = _normalize_observation(observation, root=base, expected=expected, as_of=cutoff)
    path = paper_tca_ledger_path(base, expected["strategy_name"])
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            handle.seek(0)
            existing_text = handle.read()
            existing = _parse_ledger_text(existing_text, fail_closed=True)
            _validate_existing_records(
                existing,
                root=base,
                ledger_strategy=expected["strategy_name"],
                as_of=cutoff,
            )
            _require_unique_existing_ids(existing)
            duplicate = _matching_existing_record(existing, record)
            if duplicate is not None:
                return PaperTCAIngestResult(
                    ledger_path=path,
                    observation_id=str(duplicate["observation_id"]),
                    appended=False,
                    record=duplicate,
                )
            if existing_text and not existing_text.endswith("\n"):
                raise PaperTCAValidationError(
                    "ledger_truncated", "existing observation ledger lacks a final newline"
                )
            handle.seek(0, os.SEEK_END)
            handle.write(_canonical_json(record) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    return PaperTCAIngestResult(
        ledger_path=path,
        observation_id=str(record["observation_id"]),
        appended=True,
        record=record,
    )


def append_paper_tca_observation(
    observation: Mapping[str, Any],
    **kwargs: Any,
) -> PaperTCAIngestResult:
    return ingest_paper_tca_observation(observation, **kwargs)


def build_paper_tca_report(
    *,
    root: Path | None = None,
    strategy_name: str,
    spec_hash: str,
    execution_policy_id: str,
    execution_policy_hash: str,
    epoch: datetime | str,
    as_of: datetime | None = None,
    minimum_observations: int = DEFAULT_MIN_OBSERVATIONS,
    min_observations: int | None = None,
) -> dict[str, Any]:
    base = Path(root or project_root()).resolve()
    cutoff = _as_utc(as_of or datetime.now(UTC), field="as_of")
    epoch_at = _parse_timestamp(epoch, field="epoch")
    if epoch_at > cutoff:
        raise PaperTCAValidationError("epoch_after_as_of", "epoch must not be after as_of")
    if min_observations is not None:
        minimum_observations = min_observations
    if (
        isinstance(minimum_observations, bool)
        or not isinstance(minimum_observations, int)
        or minimum_observations <= 0
    ):
        raise PaperTCAValidationError(
            "minimum_observations_invalid", "minimum observations must be a positive integer"
        )
    effective_minimum = max(DEFAULT_MIN_OBSERVATIONS, minimum_observations)
    expected = _binding(
        strategy_name=strategy_name,
        spec_hash=spec_hash,
        execution_policy_id=execution_policy_id,
        execution_policy_hash=execution_policy_hash,
    )
    path = paper_tca_ledger_path(base, expected["strategy_name"])
    entries = _read_ledger_for_report(path)
    seen_orders: set[str] = set()
    seen_fills: set[str] = set()
    valid: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []

    for line_number, raw, parse_reason in entries:
        reasons: list[str] = []
        if parse_reason is not None:
            reasons.append(parse_reason)
        order_id = str(raw.get("order_id") or "") if raw is not None else ""
        fill_id = str(raw.get("fill_id") or "") if raw is not None else ""
        if order_id and order_id in seen_orders:
            reasons.append("duplicate_order_id")
        if fill_id and fill_id in seen_fills:
            reasons.append("duplicate_fill_id")
        if order_id:
            seen_orders.add(order_id)
        if fill_id:
            seen_fills.add(fill_id)

        normalized: dict[str, Any] | None = None
        if raw is not None and parse_reason is None:
            try:
                normalized = _normalize_observation(
                    {key: raw[key] for key in _INPUT_FIELDS if key in raw},
                    root=base,
                    expected=expected,
                    as_of=cutoff,
                )
                _verify_stored_identity(raw, normalized, as_of=cutoff)
                decision_at = _parse_timestamp(normalized["decision_at"], field="decision_at")
                if decision_at < epoch_at:
                    reasons.append("before_epoch")
            except PaperTCAValidationError as exc:
                reasons.append(exc.code)

        if reasons:
            excluded.append(
                {
                    "line_number": line_number,
                    "observation_id": str((raw or {}).get("observation_id") or ""),
                    "order_id": order_id,
                    "fill_id": fill_id,
                    "reasons": sorted(set(reasons)),
                }
            )
            continue
        assert normalized is not None
        valid.append(_report_observation(normalized, line_number=line_number))

    metrics = _aggregate_metrics(valid)
    sessions = sorted(
        {
            _parse_timestamp(row["filled_at"], field="filled_at")
            .astimezone(ZoneInfo("America/New_York"))
            .date()
            .isoformat()
            for row in valid
        }
    )
    non_session_dates = [
        session
        for session in sessions
        if us_equity_session_close(datetime.fromisoformat(session).date()) is None
    ]
    eligible_orders, invalid_receipt_count = _eligible_matched_fill_orders(
        base,
        expected,
        epoch_at=epoch_at,
        as_of=cutoff,
    )
    observed_orders = {str(row["order_id"]) for row in valid}
    missing_orders = sorted(eligible_orders - observed_orders)
    unexpected_orders = sorted(observed_orders - eligible_orders)
    coverage_pass = not missing_orders and not unexpected_orders and invalid_receipt_count == 0
    blocking_exclusions = [row for row in excluded if set(row["reasons"]) != {"before_epoch"}]
    quality_checks = {
        "minimum_observations": len(valid) >= effective_minimum,
        "minimum_distinct_sessions": len(sessions) >= DEFAULT_MIN_SESSIONS,
        "valid_market_sessions": not non_session_dates,
        "complete_fill_coverage": coverage_pass,
        "no_invalid_in_epoch_observations": not blocking_exclusions,
        "weighted_mean_arrival_slippage": (
            metrics["notional_weighted_mean_slippage_vs_arrival_bps"] is not None
            and metrics["notional_weighted_mean_slippage_vs_arrival_bps"]
            <= MAX_WEIGHTED_MEAN_ARRIVAL_SLIPPAGE_BPS
        ),
        "p95_arrival_slippage": (
            metrics["p95_slippage_vs_arrival_bps"] is not None
            and metrics["p95_slippage_vs_arrival_bps"] <= MAX_P95_ARRIVAL_SLIPPAGE_BPS
        ),
        "maximum_arrival_slippage": (
            metrics["max_slippage_vs_arrival_bps"] is not None
            and metrics["max_slippage_vs_arrival_bps"] <= MAX_SINGLE_ARRIVAL_SLIPPAGE_BPS
        ),
        "p95_fill_latency": (
            metrics["p95_fill_latency_ms"] is not None
            and metrics["p95_fill_latency_ms"] <= MAX_P95_FILL_LATENCY_MS
        ),
        "single_broker_account": len({row["broker_account_id_hash"] for row in valid}) == 1,
    }
    passed = all(quality_checks.values())
    return {
        "schema_version": 1,
        "report_type": "matched_paper_tca",
        "generated_at": datetime.now(UTC).isoformat(),
        "strategy_name": expected["strategy_name"],
        "binding": {
            "spec_hash": expected["spec_hash"],
            "execution_policy_id": expected["execution_policy_id"],
            "execution_policy_hash": expected["execution_policy_hash"],
        },
        "epoch": epoch_at.isoformat(),
        "as_of": cutoff.isoformat(),
        "requested_minimum_observations": minimum_observations,
        "minimum_observations": effective_minimum,
        "minimum_distinct_sessions": DEFAULT_MIN_SESSIONS,
        "distinct_session_count": len(sessions),
        "distinct_sessions": sessions,
        "non_session_dates": non_session_dates,
        "valid_observation_count": len(valid),
        "excluded_observation_count": len(excluded),
        "valid_observations": valid,
        "excluded_observations": excluded,
        "blocking_excluded_observation_count": len(blocking_exclusions),
        "eligible_filled_order_count": len(eligible_orders),
        "covered_filled_order_count": len(observed_orders & eligible_orders),
        "missing_filled_order_ids": missing_orders,
        "unexpected_order_ids": unexpected_orders,
        "invalid_broker_receipt_count": invalid_receipt_count,
        "quality_checks": quality_checks,
        "quality_thresholds": {
            "max_notional_weighted_mean_arrival_slippage_bps": (
                MAX_WEIGHTED_MEAN_ARRIVAL_SLIPPAGE_BPS
            ),
            "max_p95_arrival_slippage_bps": MAX_P95_ARRIVAL_SLIPPAGE_BPS,
            "max_single_arrival_slippage_bps": MAX_SINGLE_ARRIVAL_SLIPPAGE_BPS,
            "max_p95_fill_latency_ms": MAX_P95_FILL_LATENCY_MS,
        },
        "matched_paper_tca_pass": passed,
        "paper_tca_pass": passed,
        "status": "pass" if passed else "paper_tca_gates_failed",
        "metrics": metrics,
        "ledger_path": _repo_relative(path, base),
        "local_hash_authenticity_caveat": LOCAL_HASH_AUTHENTICITY_CAVEAT,
        "semantics": [
            "Only paper fills fully contained between epoch and as_of count.",
            "Order and fill identifiers must be unique within the strategy ledger.",
            LOCAL_HASH_AUTHENTICITY_CAVEAT,
        ],
    }


def write_paper_tca_report(**kwargs: Any) -> dict[str, Any]:
    payload = build_paper_tca_report(**kwargs)
    root = Path(kwargs.get("root") or project_root()).resolve()
    strategy_name = str(payload["strategy_name"])
    path = root / "reports" / "paper" / "tca" / f"{strategy_name}-report.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    payload["report_path"] = _repo_relative(path, root)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def _normalize_observation(
    observation: Mapping[str, Any],
    *,
    root: Path,
    expected: dict[str, str],
    as_of: datetime,
) -> dict[str, Any]:
    if not isinstance(observation, Mapping):
        raise PaperTCAValidationError("observation_invalid", "observation must be an object")
    missing = sorted(_REQUIRED_INPUT_FIELDS - observation.keys())
    if missing:
        raise PaperTCAValidationError(
            "observation_fields_missing", f"missing required fields: {', '.join(missing)}"
        )
    extra = sorted(set(observation) - _INPUT_FIELDS)
    if extra:
        raise PaperTCAValidationError(
            "observation_fields_unknown", f"unknown fields: {', '.join(extra)}"
        )
    if observation.get("schema_version", OBSERVATION_SCHEMA_VERSION) != OBSERVATION_SCHEMA_VERSION:
        raise PaperTCAValidationError(
            "schema_version_invalid", f"schema_version must be {OBSERVATION_SCHEMA_VERSION}"
        )
    if observation.get("paper") is not True:
        raise PaperTCAValidationError("paper_required", "observation must set paper=true")

    strategy = _require_strategy_name(observation.get("strategy_name"))
    spec_hash = _require_hash(observation.get("spec_hash"), field="spec_hash")
    policy_id = _require_text(observation.get("execution_policy_id"), field="execution_policy_id")
    policy_hash = _require_hash(
        observation.get("execution_policy_hash"), field="execution_policy_hash"
    )
    actual_binding = {
        "strategy_name": strategy,
        "spec_hash": spec_hash,
        "execution_policy_id": policy_id,
        "execution_policy_hash": policy_hash,
    }
    for field, expected_value in expected.items():
        if actual_binding[field] != expected_value:
            raise PaperTCAValidationError(
                f"{field}_mismatch",
                f"{field} does not match the requested report or ingestion binding",
            )

    record: dict[str, Any] = {
        "schema_version": OBSERVATION_SCHEMA_VERSION,
        **actual_binding,
        "authorization_id": _require_text(
            observation.get("authorization_id"), field="authorization_id"
        ),
        "authorization_hash": _require_hash(
            observation.get("authorization_hash"), field="authorization_hash"
        ),
        "broker_account_id_hash": _require_hash(
            observation.get("broker_account_id_hash"), field="broker_account_id_hash"
        ),
        "paper": True,
        "order_id": _require_text(observation.get("order_id"), field="order_id"),
        "fill_id": _require_text(observation.get("fill_id"), field="fill_id"),
        "client_order_id": _require_text(
            observation.get("client_order_id"), field="client_order_id"
        ),
        "symbol": _require_text(observation.get("symbol"), field="symbol").upper(),
        "side": _require_side(observation.get("side")),
        "qty": _positive_number(observation.get("qty"), field="qty"),
        "order_style": _require_text(observation.get("order_style"), field="order_style").lower(),
        "time_in_force": _require_text(
            observation.get("time_in_force"), field="time_in_force"
        ).lower(),
    }
    for field in _PRICE_FIELDS:
        value = observation.get(field)
        if value is not None:
            record[field] = _positive_number(value, field=field)
    for field in ("decision_price", "arrival_price", "fill_price"):
        if field not in record:
            raise PaperTCAValidationError(f"{field}_missing", f"{field} is required")

    parsed_times: dict[str, datetime] = {}
    for field in _TIMESTAMP_FIELDS:
        value = observation.get(field)
        if value is None:
            if field == "accepted_at":
                continue
            raise PaperTCAValidationError(f"{field}_missing", f"{field} is required")
        parsed = _parse_timestamp(value, field=field)
        if parsed > as_of:
            raise PaperTCAValidationError("timestamp_in_future", f"{field} is after as_of")
        parsed_times[field] = parsed
        record[field] = parsed.isoformat()
    ordered = [parsed_times["decision_at"], parsed_times["submitted_at"]]
    if "accepted_at" in parsed_times:
        ordered.append(parsed_times["accepted_at"])
    ordered.extend([parsed_times["filled_at"], parsed_times["observed_at"]])
    if any(right < left for left, right in zip(ordered, ordered[1:], strict=False)):
        raise PaperTCAValidationError(
            "timestamp_order_invalid",
            "timestamps must satisfy decision <= submitted <= accepted <= filled <= observed",
        )

    for field in sorted(
        _OPTIONAL_INPUT_FIELDS - {"schema_version", "observation_id", "accepted_at"}
    ):
        if field in observation and observation[field] is not None:
            value = observation[field]
            if field in {"official_open_price", "vwap_price"}:
                continue
            if field == "metadata":
                if not isinstance(value, Mapping):
                    raise PaperTCAValidationError("metadata_invalid", "metadata must be an object")
                _canonical_json(value)
                record[field] = dict(value)
            else:
                record[field] = _require_text(value, field=field)

    source_path, source_hash, source_payload = _bound_json_artifact(
        root,
        observation.get("source_packet_path"),
        observation.get("source_packet_sha256"),
        role="source_packet",
    )
    receipt_path, receipt_hash, receipt_payload = _bound_json_artifact(
        root,
        observation.get("broker_receipt_path"),
        observation.get("broker_receipt_sha256"),
        role="broker_receipt",
    )
    if source_path == receipt_path:
        raise PaperTCAValidationError(
            "evidence_paths_not_distinct", "source packet and broker receipt must be distinct"
        )
    record.update(
        {
            "source_packet_path": _repo_relative(source_path, root),
            "source_packet_sha256": source_hash,
            "broker_receipt_path": _repo_relative(receipt_path, root),
            "broker_receipt_sha256": receipt_hash,
        }
    )
    _require_artifact_bindings(
        source_payload,
        record,
        fields=_SOURCE_PACKET_BINDINGS,
        role="source_packet",
    )
    _require_artifact_bindings(
        source_payload,
        record,
        fields=tuple(field for field in ("official_open_price", "vwap_price") if field in record),
        role="source_packet",
    )
    _require_artifact_bindings(
        receipt_payload,
        record,
        fields=_BROKER_RECEIPT_BINDINGS,
        role="broker_receipt",
    )
    sync_path, sync_hash = _require_broker_receipt_sync_membership(
        root,
        receipt_path,
        receipt_hash,
        receipt_payload,
    )
    record["broker_sync_receipt_path"] = _repo_relative(sync_path, root)
    record["broker_sync_receipt_sha256"] = sync_hash
    _require_broker_receipt_provenance(receipt_payload, record, root=root)
    if "accepted_at" in record:
        _require_artifact_bindings(
            receipt_payload,
            record,
            fields=("accepted_at",),
            role="broker_receipt",
        )

    record.update(_derived_metrics(record, parsed_times))
    fingerprint = _record_fingerprint(record)
    observation_id = f"tca_{fingerprint[:24]}"
    supplied_id = observation.get("observation_id")
    if supplied_id is not None and supplied_id != observation_id:
        raise PaperTCAValidationError(
            "observation_id_mismatch", "observation_id does not match canonical contents"
        )
    record["observation_id"] = observation_id
    record["record_sha256"] = fingerprint
    record["ingested_at"] = as_of.isoformat()
    return record


def _binding(
    *,
    strategy_name: str,
    spec_hash: str,
    execution_policy_id: str,
    execution_policy_hash: str,
) -> dict[str, str]:
    return {
        "strategy_name": _require_strategy_name(strategy_name),
        "spec_hash": _require_hash(spec_hash, field="spec_hash"),
        "execution_policy_id": _require_text(execution_policy_id, field="execution_policy_id"),
        "execution_policy_hash": _require_hash(
            execution_policy_hash, field="execution_policy_hash"
        ),
    }


def _bound_json_artifact(
    root: Path,
    path_value: Any,
    expected_hash: Any,
    *,
    role: str,
) -> tuple[Path, str, dict[str, Any]]:
    path = Path(_require_text(path_value, field=f"{role}_path"))
    candidate = path if path.is_absolute() else root / path
    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(root)
    except (FileNotFoundError, OSError, ValueError) as exc:
        raise PaperTCAValidationError(
            f"{role}_path_invalid", f"{role} must be a repository-contained file"
        ) from exc
    if not resolved.is_file():
        raise PaperTCAValidationError(f"{role}_path_invalid", f"{role} is not a file")
    claimed = _require_hash(expected_hash, field=f"{role}_sha256")
    actual = _sha256_file(resolved)
    if actual != claimed:
        raise PaperTCAValidationError(
            f"{role}_hash_mismatch", f"{role} SHA-256 does not match local bytes"
        )
    try:
        payload = json.loads(resolved.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PaperTCAValidationError(
            f"{role}_json_invalid", f"{role} must contain one JSON object"
        ) from exc
    if not isinstance(payload, dict):
        raise PaperTCAValidationError(
            f"{role}_json_invalid", f"{role} must contain one JSON object"
        )
    return resolved, claimed, payload


def _require_artifact_bindings(
    payload: dict[str, Any],
    record: dict[str, Any],
    *,
    fields: tuple[str, ...],
    role: str,
) -> None:
    for field in fields:
        if field not in payload:
            raise PaperTCAValidationError(f"{role}_binding_missing", f"{role} is missing {field}")
        actual = payload[field]
        expected = record[field]
        if field == "paper" and actual is not True:
            raise PaperTCAValidationError(f"{role}_binding_mismatch", f"{role} must set paper=true")
        if field in _PRICE_FIELDS or field == "qty":
            try:
                actual = _positive_number(actual, field=field)
            except PaperTCAValidationError as exc:
                raise PaperTCAValidationError(
                    f"{role}_binding_mismatch", f"{role} has invalid {field}"
                ) from exc
        elif field in _TIMESTAMP_FIELDS:
            try:
                actual = _parse_timestamp(actual, field=field).isoformat()
            except PaperTCAValidationError as exc:
                raise PaperTCAValidationError(
                    f"{role}_binding_mismatch", f"{role} has invalid {field}"
                ) from exc
        elif field.endswith("_hash"):
            try:
                actual = _require_hash(actual, field=field)
            except PaperTCAValidationError as exc:
                raise PaperTCAValidationError(
                    f"{role}_binding_mismatch", f"{role} has invalid {field}"
                ) from exc
        if actual != expected:
            raise PaperTCAValidationError(
                f"{role}_binding_mismatch", f"{role} {field} does not match observation"
            )


def _require_broker_receipt_sync_membership(
    root: Path,
    receipt_path: Path,
    receipt_hash: str,
    receipt: dict[str, Any],
) -> tuple[Path, str]:
    _validate_generated_broker_receipt(receipt_path, receipt)
    current_path = receipt_path
    current = receipt
    while int(current["sequence"]) > 1:
        previous_state = str(current.get("previous_state_sha256") or "")
        previous_hash = str(current.get("previous_receipt_sha256") or "")
        if not _SHA256.fullmatch(previous_state) or not _SHA256.fullmatch(previous_hash):
            raise PaperTCAValidationError(
                "broker_receipt_chain_invalid",
                "broker receipt predecessor bindings are missing",
            )
        previous_path = current_path.parent / f"{previous_state}.json"
        if not previous_path.is_file() or _sha256_file(previous_path) != previous_hash:
            raise PaperTCAValidationError(
                "broker_receipt_chain_invalid",
                "broker receipt predecessor is missing or changed",
            )
        try:
            previous = json.loads(previous_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise PaperTCAValidationError(
                "broker_receipt_chain_invalid",
                "broker receipt predecessor is malformed",
            ) from exc
        if not isinstance(previous, dict):
            raise PaperTCAValidationError(
                "broker_receipt_chain_invalid",
                "broker receipt predecessor is not an object",
            )
        _validate_generated_broker_receipt(previous_path, previous)
        if int(previous["sequence"]) != int(current["sequence"]) - 1 or previous.get(
            "order_id"
        ) != current.get("order_id"):
            raise PaperTCAValidationError(
                "broker_receipt_chain_invalid",
                "broker receipt sequence is discontinuous",
            )
        current_path, current = previous_path, previous
    if (
        current.get("previous_state_sha256") is not None
        or current.get("previous_receipt_sha256") is not None
    ):
        raise PaperTCAValidationError(
            "broker_receipt_chain_invalid",
            "first broker receipt must not claim a predecessor",
        )

    sync_directory = root / "reports" / "paper" / "broker_receipts" / "syncs"
    relative_receipt = _repo_relative(receipt_path, root)
    matches: list[tuple[datetime, Path, str]] = []
    for sync_path in sorted(sync_directory.glob("sync_*.json")):
        try:
            sync = json.loads(sync_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise PaperTCAValidationError(
                "broker_sync_receipt_invalid",
                "immutable broker sync receipt is malformed",
            ) from exc
        if not isinstance(sync, dict):
            raise PaperTCAValidationError(
                "broker_sync_receipt_invalid",
                "immutable broker sync receipt is not an object",
            )
        without_id = {key: value for key, value in sync.items() if key != "sync_id"}
        expected_sync_id = "sync_" + _mapping_hash(without_id)[:24]
        refs = sync.get("order_receipts")
        valid_sync = (
            sync.get("sync_id") == expected_sync_id
            and sync_path.name == f"{expected_sync_id}.json"
            and sync.get("receipt_version") == 1
            and sync.get("receipt_source") == "alpaca_paper_sync"
            and sync.get("paper") is True
            and sync.get("complete_local_order_reconciliation") is True
            and sync.get("broker_account_id_hash") == receipt.get("broker_account_id_hash")
            and isinstance(refs, list)
            and sync.get("order_count") == len(refs)
            and isinstance(sync.get("local_order_count"), int)
            and 0 <= int(sync["local_order_count"]) <= len(refs)
        )
        if not valid_sync:
            raise PaperTCAValidationError(
                "broker_sync_receipt_invalid",
                "immutable broker sync receipt is internally inconsistent",
            )
        expected_ref = {
            "order_id": receipt["order_id"],
            "path": relative_receipt,
            "sha256": receipt_hash,
            "state_sha256": receipt["state_sha256"],
        }
        if expected_ref in refs:
            matches.append(
                (
                    _parse_timestamp(sync.get("captured_at"), field="captured_at"),
                    sync_path,
                    _sha256_file(sync_path),
                )
            )
    if not matches:
        raise PaperTCAValidationError(
            "broker_receipt_not_in_sync",
            "broker receipt is not a member of an immutable complete sync receipt",
        )
    _, sync_path, sync_hash = min(matches, key=lambda item: (item[0], item[1].as_posix()))
    return sync_path, sync_hash


def _validate_generated_broker_receipt(path: Path, receipt: dict[str, Any]) -> None:
    broker_order = receipt.get("broker_order")
    local_order = receipt.get("local_order_record")
    if not isinstance(broker_order, dict) or not isinstance(local_order, dict):
        raise PaperTCAValidationError(
            "broker_receipt_provenance_invalid",
            "matched broker receipt must contain broker and local order objects",
        )
    broker_hash = _mapping_hash(broker_order)
    local_hash = _mapping_hash(local_order)
    state = {
        "broker": "alpaca_paper",
        "paper": True,
        "broker_account_id_hash": receipt.get("broker_account_id_hash"),
        "broker_order": broker_order,
        "local_order_binding_status": receipt.get("local_order_binding_status"),
        "local_order_record_sha256": local_hash,
    }
    state_hash = _mapping_hash(state)
    order_id = str(receipt.get("order_id") or "")
    order_key = hashlib.sha256(order_id.encode("utf-8")).hexdigest()[:16]
    relative_parts = path.parts
    expected_tail = ("reports", "paper", "broker_receipts", "orders", order_key)
    valid = (
        receipt.get("broker_order_sha256") == broker_hash
        and receipt.get("local_order_record_sha256") == local_hash
        and receipt.get("state_sha256") == state_hash
        and receipt.get("receipt_id") == "receipt_" + state_hash[:24]
        and path.name == f"{state_hash}.json"
        and tuple(relative_parts[-6:-1]) == expected_tail
        and broker_order.get("id") == order_id
        and broker_order.get("client_order_id") == receipt.get("client_order_id")
        and broker_order.get("symbol") == receipt.get("symbol")
        and broker_order.get("side") == receipt.get("side")
        and broker_order.get("status") == receipt.get("status")
        and receipt.get("local_order_binding_status") == "matched"
    )
    sequence = receipt.get("sequence")
    if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 1:
        valid = False
    if not valid:
        raise PaperTCAValidationError(
            "broker_receipt_provenance_invalid",
            "broker receipt state, identity, or storage path is inconsistent",
        )


def _require_broker_receipt_provenance(
    receipt: dict[str, Any],
    record: dict[str, Any],
    *,
    root: Path,
) -> None:
    required_values = {
        "receipt_version": 1,
        "receipt_source": "alpaca_paper_sync",
        "immutable": True,
        "paper": True,
        "status": "filled",
        "local_order_binding_status": "matched",
        "strategy_name": record["strategy_name"],
        "spec_hash": record["spec_hash"],
        "execution_policy_id": record["execution_policy_id"],
        "execution_policy_hash": record["execution_policy_hash"],
        "authorization_id": record["authorization_id"],
        "authorization_hash": record["authorization_hash"],
        "broker_account_id_hash": record["broker_account_id_hash"],
        "client_order_id": record["client_order_id"],
        "order_style": record["order_style"],
        "time_in_force": record["time_in_force"],
    }
    mismatches = [
        field for field, expected in required_values.items() if receipt.get(field) != expected
    ]
    for field in (
        "broker_account_id_hash",
        "broker_order_sha256",
        "local_order_record_sha256",
        "state_sha256",
    ):
        if not _SHA256.fullmatch(str(receipt.get(field) or "")):
            mismatches.append(field)
    if receipt.get("fill_id_source") not in {
        "alpaca_broker_fill_activity",
        "derived_from_broker_order_aggregate",
    }:
        mismatches.append("fill_id_source")
    broker_order = receipt.get("broker_order")
    local_order = receipt.get("local_order_record")
    if not isinstance(broker_order, dict):
        mismatches.append("broker_order")
    elif _record_fingerprint(broker_order) != receipt.get("broker_order_sha256"):
        mismatches.append("broker_order_sha256")
    if not isinstance(local_order, dict):
        mismatches.append("local_order_record")
    elif _record_fingerprint(local_order) != receipt.get("local_order_record_sha256"):
        mismatches.append("local_order_record_sha256")
    else:
        local_expected = {
            "id": record["order_id"],
            "strategy_name": record["strategy_name"],
            "spec_hash": record["spec_hash"],
            "execution_policy_id": record["execution_policy_id"],
            "execution_policy_hash": record["execution_policy_hash"],
            "client_order_id": record["client_order_id"],
            "authorization_id": record["authorization_id"],
            "authorization_hash": record["authorization_hash"],
            "order_style": record["order_style"],
            "time_in_force": record["time_in_force"],
            "symbol": record["symbol"],
            "side": record["side"],
            "paper": True,
        }
        for field, expected in local_expected.items():
            if local_order.get(field) != expected:
                mismatches.append(f"local_order_record.{field}")
        try:
            local_qty = _positive_number(local_order.get("qty"), field="qty")
        except PaperTCAValidationError:
            mismatches.append("local_order_record.qty")
        else:
            if local_qty != record["qty"]:
                mismatches.append("local_order_record.qty")
        for field in ("signal_id", "order_intent_id", "order_intent_hash"):
            if not str(local_order.get(field) or "").strip():
                mismatches.append(f"local_order_record.{field}")
    if receipt.get("authorization_id") != (
        local_order.get("authorization_id") if isinstance(local_order, dict) else None
    ):
        mismatches.append("authorization_id")
    if receipt.get("signal_id") != (
        local_order.get("signal_id") if isinstance(local_order, dict) else None
    ):
        mismatches.append("signal_id")
    if isinstance(local_order, dict):
        ledger_path = root / "reports" / "paper" / "orders.jsonl"
        try:
            ledger_rows = [
                json.loads(line)
                for line in ledger_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
        except (OSError, json.JSONDecodeError):
            mismatches.append("local_order_ledger")
        else:
            matches = [
                row
                for row in ledger_rows
                if isinstance(row, dict) and row.get("client_order_id") == record["client_order_id"]
            ]
            if len(matches) != 1 or matches[0] != local_order:
                mismatches.append("local_order_ledger")
    if mismatches:
        raise PaperTCAValidationError(
            "broker_receipt_provenance_invalid",
            "broker receipt provenance is incomplete or inconsistent: "
            + ", ".join(sorted(set(mismatches))),
        )


def _derived_metrics(record: dict[str, Any], timestamps: dict[str, datetime]) -> dict[str, float]:
    direction = 1.0 if record["side"] == "buy" else -1.0
    fill = float(record["fill_price"])
    metrics = {
        "slippage_vs_decision_bps": direction
        * (fill / float(record["decision_price"]) - 1.0)
        * 10_000.0,
        "slippage_vs_arrival_bps": direction
        * (fill / float(record["arrival_price"]) - 1.0)
        * 10_000.0,
        "fill_latency_ms": (timestamps["filled_at"] - timestamps["submitted_at"]).total_seconds()
        * 1_000.0,
    }
    if "official_open_price" in record:
        metrics["slippage_vs_official_open_bps"] = (
            direction * (fill / float(record["official_open_price"]) - 1.0) * 10_000.0
        )
    if "vwap_price" in record:
        metrics["slippage_vs_vwap_bps"] = (
            direction * (fill / float(record["vwap_price"]) - 1.0) * 10_000.0
        )
    if not all(math.isfinite(value) for value in metrics.values()):
        raise PaperTCAValidationError("derived_metric_invalid", "derived TCA metric is nonfinite")
    return metrics


def _record_fingerprint(record: Mapping[str, Any]) -> str:
    payload = {
        key: value
        for key, value in record.items()
        if key not in {"observation_id", "record_sha256", "ingested_at"}
    }
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def _mapping_hash(payload: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def _matching_existing_record(
    existing: list[dict[str, Any]], new_record: dict[str, Any]
) -> dict[str, Any] | None:
    for row in existing:
        same_order = row.get("order_id") == new_record["order_id"]
        same_fill = row.get("fill_id") == new_record["fill_id"]
        if not same_order and not same_fill:
            continue
        if (
            same_order
            and same_fill
            and row.get("record_sha256") == new_record["record_sha256"]
            and row.get("observation_id") == new_record["observation_id"]
        ):
            return row
        code = "duplicate_order_id" if same_order else "duplicate_fill_id"
        raise PaperTCAValidationError(code, "order and fill identifiers must be globally unique")
    return None


def _require_unique_existing_ids(rows: list[dict[str, Any]]) -> None:
    orders: set[str] = set()
    fills: set[str] = set()
    for row in rows:
        order_id = _require_text(row.get("order_id"), field="order_id")
        fill_id = _require_text(row.get("fill_id"), field="fill_id")
        if order_id in orders:
            raise PaperTCAValidationError(
                "ledger_duplicate_order_id", "existing ledger contains duplicate order_id"
            )
        if fill_id in fills:
            raise PaperTCAValidationError(
                "ledger_duplicate_fill_id", "existing ledger contains duplicate fill_id"
            )
        orders.add(order_id)
        fills.add(fill_id)


def _validate_existing_records(
    rows: list[dict[str, Any]], *, root: Path, ledger_strategy: str, as_of: datetime
) -> None:
    for line_number, row in enumerate(rows, start=1):
        try:
            row_binding = _binding(
                strategy_name=row.get("strategy_name"),
                spec_hash=row.get("spec_hash"),
                execution_policy_id=row.get("execution_policy_id"),
                execution_policy_hash=row.get("execution_policy_hash"),
            )
            if row_binding["strategy_name"] != ledger_strategy:
                raise PaperTCAValidationError(
                    "strategy_name_mismatch", "row belongs to another strategy ledger"
                )
            normalized = _normalize_observation(
                {key: row[key] for key in _INPUT_FIELDS if key in row},
                root=root,
                expected=row_binding,
                as_of=as_of,
            )
            _verify_stored_identity(row, normalized, as_of=as_of)
        except PaperTCAValidationError as exc:
            raise PaperTCAValidationError(
                "ledger_record_invalid", f"ledger line {line_number} failed {exc.code}"
            ) from exc


def _parse_ledger_text(text: str, *, fail_closed: bool) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            if fail_closed:
                raise PaperTCAValidationError(
                    "ledger_json_invalid", f"ledger line {line_number} is invalid JSON"
                ) from exc
            continue
        if not isinstance(payload, dict):
            if fail_closed:
                raise PaperTCAValidationError(
                    "ledger_record_invalid", f"ledger line {line_number} is not an object"
                )
            continue
        rows.append(payload)
    return rows


def _read_ledger_for_report(
    path: Path,
) -> list[tuple[int, dict[str, Any] | None, str | None]]:
    if not path.exists():
        return []
    entries: list[tuple[int, dict[str, Any] | None, str | None]] = []
    with path.open("r", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_SH)
        try:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    entries.append((line_number, None, "ledger_json_invalid"))
                    continue
                if not isinstance(payload, dict):
                    entries.append((line_number, None, "ledger_record_invalid"))
                    continue
                entries.append((line_number, payload, None))
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    return entries


def _verify_stored_identity(
    raw: dict[str, Any], normalized: dict[str, Any], *, as_of: datetime
) -> None:
    if set(raw) != set(normalized):
        raise PaperTCAValidationError(
            "stored_record_fields_mismatch", "stored record fields are not canonical"
        )
    if raw.get("observation_id") != normalized["observation_id"]:
        raise PaperTCAValidationError(
            "stored_observation_id_mismatch", "stored observation ID is not canonical"
        )
    if raw.get("record_sha256") != normalized["record_sha256"]:
        raise PaperTCAValidationError(
            "stored_record_hash_mismatch", "stored record hash is not canonical"
        )
    for field, expected in normalized.items():
        if field == "ingested_at":
            continue
        if raw.get(field) != expected:
            raise PaperTCAValidationError(
                "stored_record_content_mismatch", f"stored {field} is not canonical"
            )
    ingested_at = _parse_timestamp(raw.get("ingested_at"), field="ingested_at")
    observed_at = _parse_timestamp(raw.get("observed_at"), field="observed_at")
    if ingested_at < observed_at:
        raise PaperTCAValidationError(
            "stored_ingestion_order_invalid", "ingested_at must not precede observed_at"
        )
    if ingested_at > as_of:
        raise PaperTCAValidationError("timestamp_in_future", "ingested_at is after report as_of")


def _report_observation(record: dict[str, Any], *, line_number: int) -> dict[str, Any]:
    fields = (
        "observation_id",
        "order_id",
        "fill_id",
        "authorization_id",
        "broker_account_id_hash",
        "client_order_id",
        "symbol",
        "side",
        "qty",
        "fill_price",
        "filled_at",
        "observed_at",
        "slippage_vs_decision_bps",
        "slippage_vs_arrival_bps",
        "fill_latency_ms",
    )
    return {"line_number": line_number, **{field: record[field] for field in fields}}


def _aggregate_metrics(valid: list[dict[str, Any]]) -> dict[str, float | None]:
    if not valid:
        return {
            "mean_slippage_vs_decision_bps": None,
            "mean_slippage_vs_arrival_bps": None,
            "notional_weighted_mean_slippage_vs_arrival_bps": None,
            "p95_slippage_vs_arrival_bps": None,
            "max_slippage_vs_arrival_bps": None,
            "mean_fill_latency_ms": None,
            "p95_fill_latency_ms": None,
        }
    count = float(len(valid))
    notionals = [float(row["qty"]) * float(row["fill_price"]) for row in valid]
    total_notional = sum(notionals)
    arrival_slippage = [float(row["slippage_vs_arrival_bps"]) for row in valid]
    latencies = [float(row["fill_latency_ms"]) for row in valid]
    return {
        "mean_slippage_vs_decision_bps": sum(
            float(row["slippage_vs_decision_bps"]) for row in valid
        )
        / count,
        "mean_slippage_vs_arrival_bps": sum(float(row["slippage_vs_arrival_bps"]) for row in valid)
        / count,
        "notional_weighted_mean_slippage_vs_arrival_bps": sum(
            slippage * notional
            for slippage, notional in zip(arrival_slippage, notionals, strict=True)
        )
        / total_notional,
        "p95_slippage_vs_arrival_bps": _percentile(arrival_slippage, 0.95),
        "max_slippage_vs_arrival_bps": max(arrival_slippage),
        "mean_fill_latency_ms": sum(float(row["fill_latency_ms"]) for row in valid) / count,
        "p95_fill_latency_ms": _percentile(latencies, 0.95),
    }


def _eligible_matched_fill_orders(
    root: Path,
    expected: dict[str, str],
    *,
    epoch_at: datetime,
    as_of: datetime,
) -> tuple[set[str], int]:
    orders_root = root / "reports" / "paper" / "broker_receipts" / "orders"
    eligible: set[str] = set()
    invalid = 0
    for path in sorted(orders_root.glob("*/*.json")):
        try:
            receipt = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(receipt, dict):
                raise ValueError("receipt is not an object")
            _validate_generated_broker_receipt(path, receipt)
        except (OSError, ValueError, PaperTCAValidationError):
            invalid += 1
            continue
        if (
            receipt.get("local_order_binding_status") != "matched"
            or receipt.get("status") != "filled"
        ):
            continue
        local = receipt.get("local_order_record")
        if not isinstance(local, dict):
            invalid += 1
            continue
        if any(
            local.get(field) != expected[value_field]
            for field, value_field in (
                ("strategy_name", "strategy_name"),
                ("spec_hash", "spec_hash"),
                ("execution_policy_id", "execution_policy_id"),
                ("execution_policy_hash", "execution_policy_hash"),
            )
        ):
            continue
        try:
            filled_at = _parse_timestamp(receipt.get("filled_at"), field="filled_at")
            _require_broker_receipt_sync_membership(
                root,
                path,
                _sha256_file(path),
                receipt,
            )
        except PaperTCAValidationError:
            invalid += 1
            continue
        if epoch_at <= filled_at <= as_of:
            eligible.add(str(receipt["order_id"]))
    return eligible, invalid


def _percentile(values: list[float], quantile: float) -> float:
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * quantile
    lower = int(math.floor(position))
    upper = int(math.ceil(position))
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def _require_strategy_name(value: Any) -> str:
    text = _require_text(value, field="strategy_name")
    if not _STRATEGY_NAME.fullmatch(text) or text in {".", ".."}:
        raise PaperTCAValidationError(
            "strategy_name_invalid", "strategy name is not safe for an artifact path"
        )
    return text


def _require_text(value: Any, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PaperTCAValidationError(f"{field}_invalid", f"{field} must be a non-empty string")
    return value.strip()


def _require_hash(value: Any, *, field: str) -> str:
    text = str(value or "").removeprefix("sha256:").strip().lower()
    if not _SHA256.fullmatch(text):
        raise PaperTCAValidationError(f"{field}_invalid", f"{field} must be a SHA-256 digest")
    return text


def _require_side(value: Any) -> str:
    side = str(value or "").strip().lower()
    if side not in {"buy", "sell"}:
        raise PaperTCAValidationError("side_invalid", "side must be buy or sell")
    return side


def _positive_number(value: Any, *, field: str) -> float:
    if isinstance(value, bool):
        raise PaperTCAValidationError(f"{field}_invalid", f"{field} must be numeric")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise PaperTCAValidationError(f"{field}_invalid", f"{field} must be numeric") from exc
    if not math.isfinite(number) or number <= 0:
        raise PaperTCAValidationError(f"{field}_invalid", f"{field} must be finite and positive")
    return number


def _parse_timestamp(value: Any, *, field: str) -> datetime:
    if isinstance(value, datetime):
        return _as_utc(value, field=field)
    if not isinstance(value, str):
        raise PaperTCAValidationError(f"{field}_invalid", f"{field} must be an ISO-8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise PaperTCAValidationError(
            f"{field}_invalid", f"{field} must be an ISO-8601 timestamp"
        ) from exc
    return _as_utc(parsed, field=field)


def _as_utc(value: datetime, *, field: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise PaperTCAValidationError(
            f"{field}_timezone_missing", f"{field} must include a timezone"
        )
    return value.astimezone(UTC)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_json(payload: Mapping[str, Any]) -> str:
    try:
        return json.dumps(
            payload,
            allow_nan=False,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        )
    except (TypeError, ValueError) as exc:
        raise PaperTCAValidationError(
            "observation_not_json_serializable", "observation must contain strict JSON values"
        ) from exc


def _repo_relative(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError as exc:
        raise PaperTCAValidationError(
            "path_outside_repository", "artifact path is outside the repository"
        ) from exc
