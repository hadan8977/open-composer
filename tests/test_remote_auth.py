from __future__ import annotations

import time

import pytest

from open_composer.remote.auth import (
    HMACAuthError,
    NonceStore,
    sign_request_headers,
    verify_signed_request,
)


def test_hmac_request_verification_accepts_valid_request(tmp_path) -> None:
    secret = "test-secret"
    body = b'{"ok":true}'
    now = int(time.time())
    headers = sign_request_headers(
        "POST",
        "/dashboard/command-plan",
        body,
        secret,
        actor="owner",
        nonce="nonce-valid-1",
        timestamp=now,
    )

    actor = verify_signed_request(
        method="POST",
        path="/dashboard/command-plan",
        body=body,
        headers=headers,
        secret=secret,
        nonce_store=NonceStore(tmp_path / "nonces.json"),
        allowed_actor="owner",
        now=now,
    )

    assert actor == "owner"


def test_hmac_request_verification_rejects_nonce_replay(tmp_path) -> None:
    secret = "test-secret"
    body = b"{}"
    now = int(time.time())
    headers = sign_request_headers(
        "GET",
        "/dashboard/catalog",
        body,
        secret,
        actor="owner",
        nonce="nonce-replay-1",
        timestamp=now,
    )
    store = NonceStore(tmp_path / "nonces.json")
    verify_signed_request(
        method="GET",
        path="/dashboard/catalog",
        body=body,
        headers=headers,
        secret=secret,
        nonce_store=store,
        allowed_actor="owner",
        now=now,
    )

    with pytest.raises(HMACAuthError, match="replay"):
        verify_signed_request(
            method="GET",
            path="/dashboard/catalog",
            body=body,
            headers=headers,
            secret=secret,
            nonce_store=store,
            allowed_actor="owner",
            now=now,
        )


def test_hmac_request_verification_rejects_bad_hash_and_old_timestamp(tmp_path) -> None:
    secret = "test-secret"
    now = int(time.time())
    headers = sign_request_headers(
        "POST",
        "/dashboard/command-run",
        b'{"a":1}',
        secret,
        actor="owner",
        nonce="nonce-hash-1",
        timestamp=now,
    )
    with pytest.raises(HMACAuthError, match="body hash"):
        verify_signed_request(
            method="POST",
            path="/dashboard/command-run",
            body=b'{"a":2}',
            headers=headers,
            secret=secret,
            nonce_store=NonceStore(tmp_path / "nonces.json"),
            allowed_actor="owner",
            now=now,
        )

    old_headers = sign_request_headers(
        "GET",
        "/dashboard/catalog",
        b"",
        secret,
        actor="owner",
        nonce="nonce-old-1",
        timestamp=now - 1000,
    )
    with pytest.raises(HMACAuthError, match="timestamp"):
        verify_signed_request(
            method="GET",
            path="/dashboard/catalog",
            body=b"",
            headers=old_headers,
            secret=secret,
            nonce_store=NonceStore(tmp_path / "nonces.json"),
            allowed_actor="owner",
            now=now,
        )
