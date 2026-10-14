"""T03-only offline retry policy. Never persist free-form upstream text."""

from __future__ import annotations

import argparse
import fcntl
import json
import math
import re
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path
from types import SimpleNamespace

MAX_FAILURES = 3
EXIT_WAIT = 75
EXIT_BLOCKED = 20
EXIT_NO_PROGRESS = 21
KNOWN_ERRORS = frozenset(
    {
        "insufficient_quota",
        "billing_hard_limit_reached",
        "credit_balance_too_low",
        "quota_exceeded",
        "rate_limit_exceeded",
        "rate_limit_error",
        "tokens_limit_exceeded",
        "requests_limit_exceeded",
        "invalid_request_error",
        "authentication_error",
        "permission_error",
        "server_error",
        "api_error",
        "overloaded_error",
        "429",
    }
)
HARD_QUOTA = frozenset(
    {"insufficient_quota", "billing_hard_limit_reached", "credit_balance_too_low"}
)
RESET_HEADERS = frozenset(
    {
        "x-ratelimit-reset",
        "x-ratelimit-reset-requests",
        "x-ratelimit-reset-tokens",
        "ratelimit-reset",
    }
)
REQUEST_ID = re.compile(
    r"(?:[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
    r"|(?:req_)?[0-9a-fA-F]{8,64})\Z"
)
PERIOD_QUOTA = re.compile(
    r"period request limit:\s*window=(\d{1,8})h\s+requests=(\d{1,16})"
    r"\s+effective_max=(\d{1,16})(?:\s|$)"
)
BLOCK_ACTION = "require_verified_quota_recovery_or_owner_authorized_existing_alternative"


def write_json(path: Path, value: dict) -> None:
    """Atomic replacement; caller holds the extraction flock."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value) + "\n")
    tmp.replace(path)


def read_state(path: Path, ledger: Path) -> dict:
    if path.exists():
        return json.loads(path.read_text())
    # Adopt historical failures without rewriting the old ledger or guessing quota causes.
    failures = 0
    if ledger.exists():
        for line in reversed(ledger.read_text().splitlines()):
            if not line.strip():
                continue
            if json.loads(line)["status"] == 200:
                break
            failures += 1
    if not failures:
        return {}
    state = {
        "consecutive_failures": failures,
        "blocked": failures >= MAX_FAILURES,
        "reason": "historical_failed_calls",
        "next_action": BLOCK_ACTION,
    }
    write_json(path, state)
    return state


def _header_time(value: str, now: datetime, *, reset: bool) -> datetime | None:
    """Accept numeric delay, HTTP date, or conventional reset epoch/duration."""
    value = value.strip()
    try:
        if re.fullmatch(r"\d+(?:\.\d+)?", value):
            n = float(value)
            if not math.isfinite(n):
                return None
            if reset and n >= 1_000_000_000:
                return datetime.fromtimestamp(n / 1000 if n >= 1_000_000_000_000 else n, UTC)
            return now + timedelta(seconds=n)
        if reset and re.fullmatch(r"(?:\d+(?:\.\d+)?(?:ms|s|m|h))+", value):
            seconds = sum(
                float(n) * {"ms": 0.001, "s": 1, "m": 60, "h": 3600}[unit]
                for n, unit in re.findall(r"(\d+(?:\.\d+)?)(ms|s|m|h)", value)
            )
            return now + timedelta(seconds=seconds)
        dt = parsedate_to_datetime(value)
        return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt.astimezone(UTC)
    except (ValueError, TypeError, IndexError, OverflowError, OSError):
        return None


def diagnostics(result, *, now: datetime, limited: bool) -> dict:
    """Only fixed reason tags, known error identifiers and validated headers leave memory.

    Unknown codes/types are marked unrecognized: even those fields can echo secrets.
    Request IDs are limited to hex/UUID forms; arbitrary IDs are deliberately dropped.
    Neither request messages, error messages, raw_body nor transport exception text is logged.
    """
    try:
        body = json.loads(result.raw_body)
    except (ValueError, TypeError):
        body = {}
    error = body.get("error", {}) if isinstance(body, dict) else {}
    if not isinstance(error, dict):
        error = {}
    fields = {
        f"error_{name}": value
        if isinstance(value, str) and value in KNOWN_ERRORS
        else "unrecognized"
        for name in ("code", "type")
        if (value := error.get(name)) is not None
    }
    # This exact upstream format is observed evidence, not a guessed calendar reset.
    message = error.get("message")
    match = PERIOD_QUOTA.search(message) if isinstance(message, str) else None
    quota = {}
    if match:
        window, used, limit = map(int, match.groups())
        if window > 0 and limit > 0 and used >= limit:
            quota = {"quota_window_hours": window, "requests_used": used, "requests_limit": limit}
    headers, recovery = {}, []
    for name, value in result.headers.items():
        name = name.lower()
        if not isinstance(value, str):
            continue
        if name == "retry-after" or name in RESET_HEADERS:
            dt = _header_time(value, now, reset=name in RESET_HEADERS)
            if dt is not None:
                headers[name] = dt.isoformat()
                if dt > now:
                    recovery.append(dt)
        elif name in {"x-request-id", "request-id"} and REQUEST_ID.fullmatch(value):
            headers[name] = value
    hard = bool(quota or HARD_QUOTA.intersection(fields.values()))
    reason = (
        "period_quota_exhausted"
        if quota
        else "hard_quota"
        if hard
        else "rate_limit_with_recovery"
        if limited and recovery
        else "rate_limit_without_recovery"
        if limited
        else "transport_error"
        if result.status_code == 0
        else "http_error"
    )
    return {
        **fields,
        **quota,
        "reason": reason,
        "headers": headers,
        "recovery_at": max(recovery).isoformat() if recovery and not hard else None,
    }


def record_failure(path: Path, state: dict, detail: dict, *, now: datetime) -> dict:
    count = int(state.get("consecutive_failures", 0)) + 1
    blocked = (
        bool(state.get("blocked"))
        or count >= MAX_FAILURES
        or detail["reason"]
        in {"hard_quota", "period_quota_exhausted", "rate_limit_without_recovery"}
    )
    state = {
        "consecutive_failures": count,
        "blocked": blocked,
        "last_failure_at": now.isoformat(),
        **detail,
        "next_action": (
            BLOCK_ACTION
            if blocked
            else "wait_until_recovery_at"
            if detail.get("recovery_at")
            else "inspect_failed_response_before_restart"
        ),
    }
    write_json(path, state)
    return state


def clear_success(state_path: Path, next_try: Path) -> None:
    """Called only after a parsed output row is durably flushed."""
    state_path.unlink(missing_ok=True)
    next_try.unlink(missing_ok=True)


def valid_recovery_evidence(path: Path) -> bool:
    evidence = json.loads(path.read_text())
    return evidence.get("recovery_confirmed") is True and evidence.get("basis") in {
        "provider_quota_recovered",
        "owner_authorized_existing_alternative",
    }


def initialize_hard_block(diagnostic: dict, state_path: Path, ledger: Path) -> dict:
    """Adopt an already recorded diagnostic without adding another call/trial."""
    now = datetime.fromisoformat(diagnostic["finished_at_utc"])
    result = SimpleNamespace(
        status_code=diagnostic["http_status"],
        raw_body=json.dumps({"error": diagnostic.get("error", {})}),
        headers=diagnostic.get("response_headers", {}),
    )
    detail = diagnostics(result, now=now, limited=result.status_code == 429)
    if detail["reason"] not in {
        "period_quota_exhausted",
        "hard_quota",
        "rate_limit_without_recovery",
    }:
        raise ValueError("diagnostic does not establish an upstream hard block")
    prior = read_state(state_path, ledger)
    state = {
        **detail,
        "consecutive_failures": max(1, int(prior.get("consecutive_failures", 0))),
        "blocked": True,
        "last_failure_at": now.isoformat(),
        "next_action": BLOCK_ACTION,
        "diagnostic_already_recorded": True,
    }
    write_json(state_path, state)
    return state


def main() -> int:
    ap = argparse.ArgumentParser(description="Offline T03 hard-block initialization; no model call")
    ap.add_argument("--initialize-from-diagnostic", type=Path, required=True)
    ap.add_argument("--state", type=Path, required=True)
    ap.add_argument("--ledger", type=Path, required=True)
    args = ap.parse_args()
    args.state.parent.mkdir(parents=True, exist_ok=True)
    with (args.state.parent / ".lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        state = initialize_hard_block(
            json.loads(args.initialize_from_diagnostic.read_text()), args.state, args.ledger
        )
    print(json.dumps(state))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
