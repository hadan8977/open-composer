from __future__ import annotations

import hashlib
import hmac
import json
import re
import time
from collections.abc import Mapping
from pathlib import Path

from open_composer.config import ensure_dir

HEADER_TIMESTAMP = "X-OC-Timestamp"
HEADER_NONCE = "X-OC-Nonce"
HEADER_ACTOR = "X-OC-Actor"
HEADER_BODY_SHA256 = "X-OC-Body-SHA256"
HEADER_SIGNATURE = "X-OC-Signature"
DEFAULT_TIMESTAMP_WINDOW_SECONDS = 300
NONCE_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{8,128}$")


class HMACAuthError(ValueError):
    pass


class NonceStore:
    def __init__(self, path: Path, *, ttl_seconds: int = DEFAULT_TIMESTAMP_WINDOW_SECONDS) -> None:
        self.path = path
        self.ttl_seconds = ttl_seconds

    def consume(self, nonce: str, timestamp: int, *, now: int | None = None) -> None:
        current = int(time.time()) if now is None else now
        if not NONCE_PATTERN.match(nonce):
            raise HMACAuthError("nonce is missing or malformed")
        data = self._load()
        cutoff = current - self.ttl_seconds
        data = {
            key: value for key, value in data.items() if isinstance(value, int) and value >= cutoff
        }
        if nonce in data:
            self._write(data)
            raise HMACAuthError("nonce replay rejected")
        data[nonce] = timestamp
        self._write(data)

    def _load(self) -> dict[str, int]:
        if not self.path.exists():
            return {}
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        if not isinstance(raw, dict):
            return {}
        result: dict[str, int] = {}
        for key, value in raw.items():
            if isinstance(key, str) and isinstance(value, int):
                result[key] = value
        return result

    def _write(self, data: dict[str, int]) -> None:
        ensure_dir(self.path.parent)
        self.path.write_text(json.dumps(data, sort_keys=True) + "\n", encoding="utf-8")


def body_sha256(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def canonical_string(
    *,
    method: str,
    path: str,
    timestamp: str,
    nonce: str,
    actor: str,
    body_hash: str,
) -> str:
    return "\n".join(
        [
            method.upper(),
            path,
            timestamp,
            nonce,
            actor,
            body_hash,
        ]
    )


def sign_canonical(canonical: str, secret: str) -> str:
    return hmac.new(secret.encode("utf-8"), canonical.encode("utf-8"), hashlib.sha256).hexdigest()


def sign_request_headers(
    method: str,
    path: str,
    body: bytes,
    secret: str,
    *,
    actor: str = "owner",
    nonce: str,
    timestamp: int | None = None,
) -> dict[str, str]:
    ts = str(timestamp if timestamp is not None else int(time.time()))
    digest = body_sha256(body)
    canonical = canonical_string(
        method=method,
        path=path,
        timestamp=ts,
        nonce=nonce,
        actor=actor,
        body_hash=digest,
    )
    return {
        HEADER_TIMESTAMP: ts,
        HEADER_NONCE: nonce,
        HEADER_ACTOR: actor,
        HEADER_BODY_SHA256: digest,
        HEADER_SIGNATURE: sign_canonical(canonical, secret),
    }


def verify_signed_request(
    *,
    method: str,
    path: str,
    body: bytes,
    headers: Mapping[str, str],
    secret: str,
    nonce_store: NonceStore,
    allowed_actor: str = "owner",
    timestamp_window_seconds: int = DEFAULT_TIMESTAMP_WINDOW_SECONDS,
    now: int | None = None,
) -> str:
    if not secret:
        raise HMACAuthError("remote shared secret is not configured")
    timestamp = _required_header(headers, HEADER_TIMESTAMP)
    nonce = _required_header(headers, HEADER_NONCE)
    actor = _required_header(headers, HEADER_ACTOR)
    provided_body_hash = _required_header(headers, HEADER_BODY_SHA256)
    provided_signature = _normalize_signature(_required_header(headers, HEADER_SIGNATURE))

    if actor != allowed_actor:
        raise HMACAuthError("actor is not allowed")
    try:
        timestamp_int = int(timestamp)
    except ValueError as exc:
        raise HMACAuthError("timestamp must be unix seconds") from exc
    current = int(time.time()) if now is None else now
    if abs(current - timestamp_int) > timestamp_window_seconds:
        raise HMACAuthError("timestamp outside allowed window")
    computed_body_hash = body_sha256(body)
    if not hmac.compare_digest(provided_body_hash, computed_body_hash):
        raise HMACAuthError("body hash mismatch")

    canonical = canonical_string(
        method=method,
        path=path,
        timestamp=timestamp,
        nonce=nonce,
        actor=actor,
        body_hash=computed_body_hash,
    )
    expected_signature = sign_canonical(canonical, secret)
    if not hmac.compare_digest(provided_signature, expected_signature):
        raise HMACAuthError("signature mismatch")

    nonce_store.consume(nonce, timestamp_int, now=current)
    return actor


def _required_header(headers: Mapping[str, str], name: str) -> str:
    value = headers.get(name, "")
    if not value:
        lower_name = name.lower()
        for key, candidate in headers.items():
            if key.lower() == lower_name:
                value = candidate
                break
    value = str(value).strip()
    if not value:
        raise HMACAuthError(f"{name} header is required")
    return value


def _normalize_signature(value: str) -> str:
    if value.startswith("sha256="):
        return value[len("sha256=") :]
    return value
