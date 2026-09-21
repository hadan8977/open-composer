from __future__ import annotations

import json
import os
import shutil
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from open_composer.cockpit.app import create_app
from open_composer.cockpit.data import quota as Q

_SAMPLE_PAYLOAD = {
    "five_hour": {"utilization": 0.42, "resets_at": 1_800_000_000},
    "seven_day": {"utilization": 0.85, "resets_at": 1_800_000_000},
    "seven_day_opus": {"utilization": 0.95, "resets_at": 1_800_000_000},
    "seven_day_sonnet": {"utilization": 0.10, "resets_at": 1_800_000_000},
    "extra_usage": {"isUsingOverage": False, "overageStatus": "not_enrolled"},
}


def _write_credentials(
    tmp_path: Path, token: str = "sk-ant-oat01-testtoken0000000000000000000"
) -> Path:
    path = tmp_path / "credentials.json"
    path.write_text(json.dumps({"claudeAiOauth": {"accessToken": token}}), encoding="utf-8")
    return path


def _client_for(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app(warm=False))


# --------------------------------------------------------------------------
# CLI version discovery -- local file reads only, no subprocess
# --------------------------------------------------------------------------


def test_discover_claude_cli_version_reads_real_installed_version() -> None:
    which = shutil.which("claude")
    if which is None:
        pytest.skip("claude CLI not installed on this box")
    binary = Path(which).resolve()
    expected = None
    for parent in (binary.parent, binary.parent.parent, binary.parent.parent.parent):
        package_json = parent / "package.json"
        if package_json.is_file():
            data = json.loads(package_json.read_text(encoding="utf-8"))
            if data.get("name") == "@anthropic-ai/claude-code":
                expected = data.get("version")
                break
    assert expected, "expected to find an @anthropic-ai/claude-code package.json on this box"
    assert Q.discover_claude_cli_version() == expected


def test_discover_claude_cli_version_falls_back_when_claude_not_on_path() -> None:
    version = Q.discover_claude_cli_version(which_fn=lambda name: None)
    assert version == Q._FALLBACK_CLAUDE_CLI_VERSION


def test_discover_claude_cli_version_falls_back_when_binary_has_no_package_json(
    tmp_path: Path,
) -> None:
    fake_binary = tmp_path / "bin" / "claude"
    fake_binary.parent.mkdir(parents=True)
    fake_binary.write_text("#!/bin/sh\n", encoding="utf-8")
    version = Q.discover_claude_cli_version(which_fn=lambda name: str(fake_binary))
    assert version == Q._FALLBACK_CLAUDE_CLI_VERSION


# --------------------------------------------------------------------------
# Claude usage payload parsing
# --------------------------------------------------------------------------


def test_successful_payload_parses_all_four_windows_and_thresholds(tmp_path: Path) -> None:
    creds = _write_credentials(tmp_path)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_SAMPLE_PAYLOAD)

    cache = Q.ClaudeQuotaCache()
    report = cache.get(credentials_path=creds, client=_client_for(handler))

    assert report.snapshot.available is True
    by_key = {w.key: w for w in report.snapshot.windows}
    assert set(by_key) == {"five_hour", "seven_day", "seven_day_opus", "seven_day_sonnet"}
    assert by_key["five_hour"].percent_used == pytest.approx(42.0)
    assert by_key["five_hour"].status == "ok"
    assert by_key["seven_day"].status == "warn"  # 85% -> warn (>=80)
    assert by_key["seven_day_opus"].status == "stale"  # 95% -> stale (>=92)
    assert by_key["seven_day_sonnet"].status == "ok"
    assert report.snapshot.extra_usage is not None
    assert report.snapshot.extra_usage.present is True


def test_extra_usage_values_are_scrubbed_and_capped(tmp_path: Path) -> None:
    creds = _write_credentials(tmp_path)
    payload = dict(_SAMPLE_PAYLOAD)
    payload["extra_usage"] = {"note": "token=sk-ant-oat01-shouldnotleak0000000000"}

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    cache = Q.ClaudeQuotaCache()
    report = cache.get(credentials_path=creds, client=_client_for(handler))

    assert "sk-ant-oat01-shouldnotleak0000000000" not in repr(report)
    assert "REDACTED" in report.snapshot.extra_usage.summary["note"]


def test_malformed_top_level_payload_degrades_to_invalid_response(tmp_path: Path) -> None:
    creds = _write_credentials(tmp_path)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=["not", "an", "object"])

    cache = Q.ClaudeQuotaCache()
    report = cache.get(credentials_path=creds, client=_client_for(handler))

    assert report.snapshot.available is False
    assert report.snapshot.unavailable_reason == "invalid response"


def test_one_malformed_window_degrades_only_that_window(tmp_path: Path) -> None:
    creds = _write_credentials(tmp_path)
    payload = dict(_SAMPLE_PAYLOAD)
    payload["five_hour"] = "not-an-object"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    cache = Q.ClaudeQuotaCache()
    report = cache.get(credentials_path=creds, client=_client_for(handler))

    assert report.snapshot.available is True
    by_key = {w.key: w for w in report.snapshot.windows}
    assert by_key["five_hour"].status == "unknown"
    assert by_key["five_hour"].percent_used is None
    assert by_key["seven_day"].percent_used is not None


# --------------------------------------------------------------------------
# Cache / circuit breaker / timeout
# --------------------------------------------------------------------------


def test_cache_hit_within_ttl_does_not_call_handler_again(tmp_path: Path) -> None:
    creds = _write_credentials(tmp_path)
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(200, json=_SAMPLE_PAYLOAD)

    cache = Q.ClaudeQuotaCache()
    base = datetime(2026, 9, 20, tzinfo=UTC)
    r1 = cache.get(now=base, credentials_path=creds, client=_client_for(handler))
    r2 = cache.get(
        now=base + timedelta(seconds=30), credentials_path=creds, client=_client_for(handler)
    )

    assert len(calls) == 1
    assert r1.served_from_cache is False
    assert r2.served_from_cache is True


def test_cache_expires_after_ttl(tmp_path: Path) -> None:
    creds = _write_credentials(tmp_path)
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(200, json=_SAMPLE_PAYLOAD)

    cache = Q.ClaudeQuotaCache()
    base = datetime(2026, 9, 20, tzinfo=UTC)
    cache.get(now=base, credentials_path=creds, client=_client_for(handler))
    cache.get(
        now=base + timedelta(seconds=Q.CACHE_TTL_SECONDS + 1),
        credentials_path=creds,
        client=_client_for(handler),
    )

    assert len(calls) == 2


def test_breaker_opens_after_three_consecutive_failures_and_stops_calling(tmp_path: Path) -> None:
    creds = _write_credentials(tmp_path)
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(500, text="boom")

    cache = Q.ClaudeQuotaCache()
    base = datetime(2026, 9, 20, tzinfo=UTC)
    step = timedelta(seconds=Q.CACHE_TTL_SECONDS + 1)
    cache.get(now=base, credentials_path=creds, client=_client_for(handler))
    cache.get(now=base + step, credentials_path=creds, client=_client_for(handler))
    r3 = cache.get(now=base + 2 * step, credentials_path=creds, client=_client_for(handler))

    assert len(calls) == 3
    assert r3.breaker_open is True
    assert r3.consecutive_failures == 3

    r4 = cache.get(now=base + 3 * step, credentials_path=creds, client=_client_for(handler))
    assert len(calls) == 3, "breaker must stop calling the handler while open"
    assert r4.snapshot.unavailable_reason == "breaker open"


def test_breaker_closes_after_cooldown_and_retries(tmp_path: Path) -> None:
    creds = _write_credentials(tmp_path)
    calls: list[str] = []

    def failing_handler(request: httpx.Request) -> httpx.Response:
        calls.append("fail")
        return httpx.Response(500, text="boom")

    cache = Q.ClaudeQuotaCache()
    base = datetime(2026, 9, 20, tzinfo=UTC)
    step = timedelta(seconds=Q.CACHE_TTL_SECONDS + 1)
    for i in range(3):
        cache.get(now=base + i * step, credentials_path=creds, client=_client_for(failing_handler))
    assert len(calls) == 3

    def success_handler(request: httpx.Request) -> httpx.Response:
        calls.append("ok")
        return httpx.Response(200, json=_SAMPLE_PAYLOAD)

    after_cooldown = base + 3 * step + timedelta(seconds=Q.BREAKER_COOLDOWN_SECONDS + 1)
    report = cache.get(
        now=after_cooldown, credentials_path=creds, client=_client_for(success_handler)
    )

    assert calls[-1] == "ok"
    assert report.snapshot.available is True
    assert report.breaker_open is False
    assert report.consecutive_failures == 0


def test_no_credentials_short_circuits_without_network_attempt(tmp_path: Path) -> None:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(200, json=_SAMPLE_PAYLOAD)

    cache = Q.ClaudeQuotaCache()
    missing = tmp_path / "nope.json"
    report = cache.get(credentials_path=missing, client=_client_for(handler))

    assert report.snapshot.available is False
    assert report.snapshot.unavailable_reason == "no credentials"
    assert calls == []


def test_http_error_status_maps_to_http_4xx_5xx_reason(tmp_path: Path) -> None:
    creds = _write_credentials(tmp_path)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, text="rate limited")

    cache = Q.ClaudeQuotaCache()
    report = cache.get(credentials_path=creds, client=_client_for(handler))

    assert report.snapshot.unavailable_reason == "http 4xx/5xx"
    assert report.snapshot.http_status == 429


def test_timeout_exception_from_transport_maps_to_timeout_reason(tmp_path: Path) -> None:
    creds = _write_credentials(tmp_path)

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("simulated timeout", request=request)

    cache = Q.ClaudeQuotaCache()
    report = cache.get(credentials_path=creds, client=_client_for(handler))

    assert report.snapshot.unavailable_reason == "timeout"


def test_connection_error_from_transport_maps_to_network_error_reason(tmp_path: Path) -> None:
    creds = _write_credentials(tmp_path)

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("simulated refusal", request=request)

    cache = Q.ClaudeQuotaCache()
    report = cache.get(credentials_path=creds, client=_client_for(handler))

    assert report.snapshot.unavailable_reason == "network error"


def test_real_client_degrades_within_timeout_against_unroutable_address(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The one sanctioned real-network attempt in this suite (task brief).

    Points the *real* fetch path (no injected client, no mocked transport)
    at a reserved, never-routable address (TEST-NET-1, RFC 5737) with a
    short timeout, and confirms the real code degrades to an unavailable
    state within a bounded time instead of hanging or raising -- this is
    what proves the 5-second timeout policy is real, not just documented.
    """
    creds = _write_credentials(tmp_path)
    monkeypatch.setattr(Q, "CLAUDE_USAGE_URL", "http://192.0.2.1/api/oauth/usage")

    cache = Q.ClaudeQuotaCache()
    started = time.monotonic()
    report = cache.get(credentials_path=creds, timeout=1.5)
    elapsed = time.monotonic() - started

    assert report.snapshot.available is False
    assert report.snapshot.unavailable_reason in ("timeout", "network error")
    assert elapsed < 5.0


# --------------------------------------------------------------------------
# Multi-source ordered credential resolution (T6b)
# --------------------------------------------------------------------------


def _handler_by_bearer_token(mapping: dict[str, httpx.Response]):
    """Route a mock response by which literal bearer token the request carries.

    Lets one test give the env-var token, the paseo token, and the
    credentials-file token three different simulated server responses, the
    way three real, differently-broken credentials would.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        auth = request.headers.get("authorization", "")
        token = auth.removeprefix("Bearer ").strip()
        return mapping[token]

    return handler


def test_env_token_present_succeeds_without_probing_other_sources(tmp_path: Path) -> None:
    env_token = "sk-ant-oat01-envtoken00000000000000000000000000"
    file_token = "sk-ant-oat01-filetoken0000000000000000000000000"
    creds = _write_credentials(tmp_path, token=file_token)
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.headers.get("authorization", ""))
        return httpx.Response(200, json=_SAMPLE_PAYLOAD)

    cache = Q.ClaudeQuotaCache()
    report = cache.get(
        credentials_path=creds,
        env={"CLAUDE_CODE_OAUTH_TOKEN": env_token},
        client=_client_for(handler),
    )

    assert report.snapshot.available is True
    assert len(calls) == 1, "the credentials-file source must not be probed once env succeeds"
    probes = {p.source: p for p in report.snapshot.credential_probes}
    assert probes["env"].outcome == "ok"
    assert probes["env"].token_found is True
    assert "credentials_file" not in probes, "round stops at the first success"


def test_all_sources_absent_reports_no_credentials_with_full_probe_list(tmp_path: Path) -> None:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(200, json=_SAMPLE_PAYLOAD)

    cache = Q.ClaudeQuotaCache()
    report = cache.get(
        credentials_path=tmp_path / "nope.json",
        paseo_config_path=tmp_path / "nope-paseo.json",
        env={},
        client=_client_for(handler),
    )

    assert report.snapshot.available is False
    assert report.snapshot.unavailable_reason == "no credentials"
    assert calls == []
    assert len(report.snapshot.credential_probes) == 3
    assert {p.outcome for p in report.snapshot.credential_probes} == {"absent"}
    assert all(p.token_found is False for p in report.snapshot.credential_probes)


def test_paseo_scope_failure_and_credentials_file_expiry_are_both_diagnosed(
    tmp_path: Path,
) -> None:
    """The exact two-source, two-failure-mode scenario this box hit 2026-09-20.

    Both present sources are attempted (neither short-circuits the other),
    both real outcomes show up in `credential_probes`, and the headline
    `unavailable_reason` picks the expired-token wording ahead of the
    scope-failure wording because re-login is the fix that actually restores
    live reads (module docstring's "Credential handling", last paragraph).
    """
    paseo_token = "sk-ant-oat01-paseotoken00000000000000000000000"
    file_token = "sk-ant-oat01-filetoken0000000000000000000000000"
    paseo_path = tmp_path / "paseo-config.json"
    paseo_path.write_text(
        json.dumps(
            {"agents": {"providers": {"claude": {"env": {"CLAUDE_CODE_OAUTH_TOKEN": paseo_token}}}}}
        ),
        encoding="utf-8",
    )
    creds = _write_credentials(tmp_path, token=file_token)

    handler = _handler_by_bearer_token(
        {
            paseo_token: httpx.Response(403, json={"type": "permission_error"}),
            file_token: httpx.Response(401, json={"type": "authentication_error"}),
        }
    )

    cache = Q.ClaudeQuotaCache()
    report = cache.get(
        credentials_path=creds,
        paseo_config_path=paseo_path,
        env={},
        client=_client_for(handler),
    )

    assert report.snapshot.available is False
    assert report.snapshot.unavailable_reason == "token expired -- re-login"
    probes = {p.source: p for p in report.snapshot.credential_probes}
    assert probes["env"].outcome == "absent"
    assert probes["paseo"].outcome == "insufficient scope (403)"
    assert probes["credentials_file"].outcome == "expired (401)"


def test_breaker_open_round_reports_token_found_without_any_http_attempt(tmp_path: Path) -> None:
    creds = _write_credentials(tmp_path)
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(500, text="boom")

    cache = Q.ClaudeQuotaCache()
    base = datetime(2026, 9, 20, tzinfo=UTC)
    step = timedelta(seconds=Q.CACHE_TTL_SECONDS + 1)
    for i in range(3):
        cache.get(
            now=base + i * step,
            credentials_path=creds,
            paseo_config_path=tmp_path / "nope-paseo.json",
            env={},
            client=_client_for(handler),
        )
    assert len(calls) == 3

    report = cache.get(
        now=base + 3 * step,
        credentials_path=creds,
        paseo_config_path=tmp_path / "nope-paseo.json",
        env={},
        client=_client_for(handler),
    )

    assert len(calls) == 3, "breaker must stop calling the handler while open"
    assert report.breaker_open is True
    probes = {p.source: p for p in report.snapshot.credential_probes}
    assert probes["credentials_file"].token_found is True
    assert probes["credentials_file"].outcome == "breaker open"
    assert probes["paseo"].token_found is False
    assert probes["paseo"].outcome == "absent"


# --------------------------------------------------------------------------
# The token must never reach a rendered page, even via a leaking response body
# --------------------------------------------------------------------------


def test_http_error_body_with_token_shaped_string_is_scrubbed_before_storage(
    tmp_path: Path,
) -> None:
    real_token = "sk-ant-oat01-REALSECRETTOKENVALUE0000000000000000"
    leaked_from_body = "sk-ant-oat01-LEAKEDFROMBODYVALUE1111111111111111"
    creds = tmp_path / "creds.json"
    creds.write_text(json.dumps({"claudeAiOauth": {"accessToken": real_token}}), encoding="utf-8")

    def handler(request: httpx.Request) -> httpx.Response:
        # Simulates a misbehaving upstream/proxy that echoes request headers
        # back into an error body -- the exact risk the module docstring
        # calls out.
        return httpx.Response(
            502, text=f"upstream error, saw Authorization: Bearer {leaked_from_body}"
        )

    cache = Q.ClaudeQuotaCache()
    report = cache.get(credentials_path=creds, client=_client_for(handler))

    dump = repr(report)
    assert report.snapshot.available is False
    assert real_token not in dump
    assert leaked_from_body not in dump
    # `secret_scrub`'s guarantee (see `tests/test_cockpit_app.py`'s own
    # `SECRET_SCRUB_CASES`) is that the secret *value* never survives, not
    # that the literal word "Bearer" disappears -- the `sk-...` pattern runs
    # first and eats just the token, leaving a harmless "Bearer ***REDACTED***".
    assert "REDACTED" in dump


def test_quota_route_scrubs_leaked_token_shaped_body(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """End-to-end: the real `/quota` route, a poisoned response body, and a
    live (fresh, unpolluted) cache -- confirms the leak protection holds
    through the whole pipeline, not just at the data-layer unit level.
    """
    real_token = "sk-ant-oat01-REALSECRETTOKENVALUE0000000000000000"
    leaked = "sk-ant-oat01-LEAKEDFROMBODYVALUE1111111111111111"
    creds = tmp_path / "creds.json"
    creds.write_text(json.dumps({"claudeAiOauth": {"accessToken": real_token}}), encoding="utf-8")

    monkeypatch.setattr(Q, "CLAUDE_CREDENTIALS_PATH", creds)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text=f"error, saw Authorization: Bearer {leaked}")

    monkeypatch.setattr(
        Q, "_build_http_client", lambda: httpx.Client(transport=httpx.MockTransport(handler))
    )
    monkeypatch.setattr(
        "open_composer.cockpit.app.get_default_claude_cache", lambda: Q.ClaudeQuotaCache()
    )

    response = TestClient(create_app(warm=False)).get("/quota")

    assert response.status_code == 200
    assert real_token not in response.text
    assert leaked not in response.text
    assert "unavailable" in response.text


# --------------------------------------------------------------------------
# Burn rate
# --------------------------------------------------------------------------


def test_burn_rate_single_sample_never_projects() -> None:
    now = datetime(2026, 9, 20, tzinfo=UTC)
    samples = [Q.BurnRateSample(at=now, five_hour_percent=10.0)]
    projection = Q.compute_burn_rate_projection(samples, now=now)
    assert projection.available is False
    assert projection.label == "projection: not enough samples"


def test_burn_rate_requires_minimum_span() -> None:
    now = datetime(2026, 9, 20, tzinfo=UTC)
    samples = [
        Q.BurnRateSample(at=now - timedelta(seconds=60), five_hour_percent=10.0),
        Q.BurnRateSample(at=now, five_hour_percent=20.0),
    ]
    projection = Q.compute_burn_rate_projection(samples, now=now)
    assert projection.available is False


def test_burn_rate_requires_rising_utilization() -> None:
    now = datetime(2026, 9, 20, tzinfo=UTC)
    samples = [
        Q.BurnRateSample(at=now - timedelta(minutes=10), five_hour_percent=30.0),
        Q.BurnRateSample(at=now, five_hour_percent=20.0),
    ]
    projection = Q.compute_burn_rate_projection(samples, now=now)
    assert projection.available is False


def test_burn_rate_computes_eta_when_rising() -> None:
    now = datetime(2026, 9, 20, tzinfo=UTC)
    samples = [
        Q.BurnRateSample(at=now - timedelta(minutes=10), five_hour_percent=20.0),
        Q.BurnRateSample(at=now, five_hour_percent=30.0),
    ]
    projection = Q.compute_burn_rate_projection(samples, now=now)
    assert projection.available is True
    assert projection.eta is not None
    assert projection.eta > now
    assert projection.rate_percent_per_hour == pytest.approx(60.0, rel=0.01)


def test_cache_projects_only_after_two_rising_samples(tmp_path: Path) -> None:
    creds = _write_credentials(tmp_path)

    def make_handler(percent: float):
        def handler(request: httpx.Request) -> httpx.Response:
            payload = dict(_SAMPLE_PAYLOAD)
            payload["five_hour"] = {"utilization": percent / 100.0, "resets_at": 1_800_000_000}
            return httpx.Response(200, json=payload)

        return handler

    cache = Q.ClaudeQuotaCache()
    base = datetime(2026, 9, 20, tzinfo=UTC)
    r1 = cache.get(now=base, credentials_path=creds, client=_client_for(make_handler(10)))
    assert r1.projection.available is False

    r2 = cache.get(
        now=base + timedelta(minutes=10),
        credentials_path=creds,
        client=_client_for(make_handler(20)),
    )
    assert r2.projection.available is True


# --------------------------------------------------------------------------
# Fallback layer: last `quotaLimits` event from local transcripts
# --------------------------------------------------------------------------


def test_find_last_throttle_event_returns_none_when_dir_missing(tmp_path: Path) -> None:
    assert Q.find_last_throttle_event(tmp_path / "does-not-exist") is None


def test_find_last_throttle_event_parses_most_recent_matching_line(tmp_path: Path) -> None:
    project_dir = tmp_path / "proj1"
    project_dir.mkdir()
    transcript = project_dir / "session1.jsonl"
    lines = [
        json.dumps({"type": "assistant", "timestamp": "2026-09-18T08:00:00.000Z", "message": {}}),
        json.dumps(
            {
                "type": "assistant",
                "timestamp": "2026-09-18T08:19:17.850Z",
                "message": {},
                "quotaLimits": {
                    "status": "rejected",
                    "resetsAt": 1_788_329_400,
                    "rateLimitType": "five_hour",
                    "overageStatus": "rejected",
                },
            }
        ),
        json.dumps({"type": "assistant", "timestamp": "2026-09-18T08:20:00.000Z", "message": {}}),
    ]
    transcript.write_text("\n".join(lines) + "\n", encoding="utf-8")

    event = Q.find_last_throttle_event(tmp_path)
    assert event is not None
    assert event.kind == "event"
    assert event.status == "rejected"
    assert event.rate_limit_type == "five_hour"
    assert event.at is not None
    assert event.resets_at is not None


def test_find_last_throttle_event_skips_files_without_a_match(tmp_path: Path) -> None:
    project_dir = tmp_path / "proj1"
    project_dir.mkdir()
    (project_dir / "session1.jsonl").write_text(
        json.dumps({"type": "assistant", "message": {}}) + "\n", encoding="utf-8"
    )
    assert Q.find_last_throttle_event(tmp_path) is None


# --------------------------------------------------------------------------
# Usage estimate: absolute tokens from local transcripts, never a percentage (T6b)
# --------------------------------------------------------------------------


def _write_transcript(path: Path, lines: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(line) for line in lines) + "\n", encoding="utf-8")


def _usage(input_tokens=0, output_tokens=0, cache_creation=0, cache_read=0) -> dict:
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cache_creation_input_tokens": cache_creation,
        "cache_read_input_tokens": cache_read,
    }


def _assistant_line(ts: datetime, msg_id: str, model: str = "m", **usage_kwargs) -> dict:
    return {
        "type": "assistant",
        "timestamp": ts.isoformat().replace("+00:00", "Z"),
        "sessionId": "sess-1",
        "message": {"id": msg_id, "model": model, "usage": _usage(**usage_kwargs)},
    }


def _user_brief_line(ts: datetime, brief: str) -> dict:
    return {
        "type": "user",
        "timestamp": ts.isoformat().replace("+00:00", "Z"),
        "sessionId": "sess-1",
        "message": {"role": "user", "content": brief},
    }


def _subagent_task_path(root: Path, stem: str = "agent1") -> Path:
    return root / "proj1" / "sess1" / "tasks" / f"{stem}.output"


def test_usage_estimate_dedups_repeated_lines_by_message_id_in_main_transcripts(
    tmp_path: Path,
) -> None:
    """The real 2026-09-20 finding this module exists to avoid: a session can
    log the same assistant turn's `usage` object on several jsonl lines
    (376 lines, 24 distinct `message.id` values, observed on this box).
    Summing every line instead of every distinct id overcounts by ~2x.
    """
    now = datetime(2026, 9, 20, 12, 0, 0, tzinfo=UTC)
    project_dir = tmp_path / "proj1"
    project_dir.mkdir()
    transcript = project_dir / "session1.jsonl"
    ts = now - timedelta(minutes=10)
    line = _assistant_line(
        ts,
        "msg-1",
        model="claude-opus-5",
        input_tokens=10,
        output_tokens=20,
        cache_creation=5,
        cache_read=100,
    )
    _write_transcript(transcript, [line, line, line])  # same message logged 3x
    os.utime(transcript, (now.timestamp(), now.timestamp()))

    estimate = Q.build_usage_estimate(tmp_path, now=now)

    # T6c: fresh (input + output + cache_creation) never includes cache_read.
    assert estimate.fresh_main == 10 + 20 + 5
    assert estimate.fresh_total == estimate.fresh_main
    assert estimate.cache_read_main == 100
    assert estimate.distinct_session_count == 1
    assert len(estimate.by_role_model) == 1
    row = estimate.by_role_model[0]
    assert row.role == "main"
    assert row.model == "claude-opus-5"
    assert row.input_tokens == 10
    assert row.fresh_tokens == 35
    assert row.cache_read_tokens == 100


def test_usage_estimate_dedups_repeated_lines_by_message_id_in_subagent_tasks(
    tmp_path: Path,
) -> None:
    """Same overcounting trap as the main-transcript scan, but for a
    subagent task file (T6c's second source) -- a repeated line must not
    inflate `turns` or the task's fresh/cache-read totals.
    """
    now = datetime(2026, 9, 20, 12, 0, 0, tzinfo=UTC)
    ts = now - timedelta(minutes=5)
    task_file = _subagent_task_path(tmp_path)
    line = _assistant_line(
        ts,
        "msg-a",
        model="claude-sonnet-5",
        input_tokens=3,
        output_tokens=4,
        cache_creation=1,
        cache_read=50,
    )
    _write_transcript(task_file, [_user_brief_line(ts, "brief"), line, line])
    os.utime(task_file, (now.timestamp(), now.timestamp()))

    estimate = Q.build_usage_estimate(tmp_path / "no-main-here", now=now, subagent_root=tmp_path)

    assert len(estimate.subagent_tasks) == 1
    task = estimate.subagent_tasks[0]
    assert task.turns == 1
    assert task.fresh_tokens == 3 + 4 + 1
    assert task.cache_read_tokens == 50


def test_usage_estimate_role_attribution_keeps_main_and_subagent_separate(
    tmp_path: Path,
) -> None:
    """T6c: main-session and subagent-task usage must land in distinct
    `(role, model)` buckets and distinct `fresh_main`/`fresh_subagent`
    totals -- never merged into one undifferentiated figure.
    """
    now = datetime(2026, 9, 20, 12, 0, 0, tzinfo=UTC)
    ts = now - timedelta(minutes=10)

    main_root = tmp_path / "main"
    main_root.mkdir()
    _write_transcript(
        main_root / "proj1" / "session1.jsonl",
        [
            _assistant_line(
                ts, "msg-main", model="claude-opus-5", input_tokens=100, output_tokens=50
            )
        ],
    )
    os.utime(main_root / "proj1" / "session1.jsonl", (now.timestamp(), now.timestamp()))

    subagent_root = tmp_path / "subagent"
    task_file = _subagent_task_path(subagent_root)
    _write_transcript(
        task_file,
        [
            _user_brief_line(ts, "brief"),
            _assistant_line(
                ts, "msg-sub", model="claude-sonnet-5", input_tokens=7, output_tokens=8
            ),
        ],
    )
    os.utime(task_file, (now.timestamp(), now.timestamp()))

    estimate = Q.build_usage_estimate(main_root, now=now, subagent_root=subagent_root)

    assert estimate.fresh_main == 150
    assert estimate.fresh_subagent == 15
    assert estimate.fresh_total == 165
    roles_by_model = {(r.role, r.model) for r in estimate.by_role_model}
    assert ("main", "claude-opus-5") in roles_by_model
    assert ("subagent", "claude-sonnet-5") in roles_by_model
    assert len(estimate.subagent_tasks) == 1


def test_usage_estimate_fresh_never_includes_cache_read(tmp_path: Path) -> None:
    """T6c's core honesty invariant: a cache read is billed at a fraction of
    a fresh token, so it must never be folded into `fresh_tokens` at any
    level -- per-row, per-task, or the window totals.
    """
    now = datetime(2026, 9, 20, 12, 0, 0, tzinfo=UTC)
    ts = now - timedelta(minutes=1)
    main_root = tmp_path / "main"
    main_root.mkdir()
    transcript = main_root / "proj1" / "session1.jsonl"
    _write_transcript(
        transcript,
        [
            _assistant_line(
                ts,
                "msg-1",
                model="m",
                input_tokens=1,
                output_tokens=1,
                cache_creation=1,
                cache_read=999_999,
            )
        ],
    )
    os.utime(transcript, (now.timestamp(), now.timestamp()))

    estimate = Q.build_usage_estimate(main_root, now=now, subagent_root=tmp_path / "no-subagent")

    assert estimate.fresh_main == 3
    assert estimate.fresh_total == 3
    assert estimate.cache_read_main == 999_999
    assert estimate.cache_read_total == 999_999
    assert estimate.fresh_main != estimate.fresh_main + estimate.cache_read_main  # sanity
    for row in estimate.by_role_model:
        assert row.fresh_tokens < row.cache_read_tokens or row.cache_read_tokens == 999_999
        assert row.fresh_tokens == row.input_tokens + row.output_tokens + row.cache_creation_tokens


def test_usage_estimate_subagent_task_turn_counting(tmp_path: Path) -> None:
    """`turns` counts distinct `message.id`s, matching the main-transcript
    dedupe discipline -- three distinct turns plus one repeated line must
    still report 3, not 4.
    """
    now = datetime(2026, 9, 20, 12, 0, 0, tzinfo=UTC)
    base_ts = now - timedelta(minutes=30)
    task_file = _subagent_task_path(tmp_path)
    turn_1 = _assistant_line(base_ts, "msg-1", input_tokens=1)
    turn_2 = _assistant_line(base_ts + timedelta(minutes=1), "msg-2", input_tokens=1)
    turn_3 = _assistant_line(base_ts + timedelta(minutes=2), "msg-3", input_tokens=1)
    _write_transcript(
        task_file, [_user_brief_line(base_ts, "brief"), turn_1, turn_2, turn_2, turn_3]
    )
    os.utime(task_file, (now.timestamp(), now.timestamp()))

    estimate = Q.build_usage_estimate(tmp_path / "no-main", now=now, subagent_root=tmp_path)

    assert len(estimate.subagent_tasks) == 1
    assert estimate.subagent_tasks[0].turns == 3
    assert estimate.subagent_tasks[0].first_activity == base_ts
    assert estimate.subagent_tasks[0].last_activity == base_ts + timedelta(minutes=2)


def test_usage_estimate_subagent_task_label_uses_scrubbed_brief(tmp_path: Path) -> None:
    """The label is `<file stem>: <~60 char, secret_scrub'd brief>` (T6c),
    taken from the *first* user-role line, not the tail.
    """
    now = datetime(2026, 9, 20, 12, 0, 0, tzinfo=UTC)
    ts = now - timedelta(minutes=1)
    task_file = _subagent_task_path(tmp_path, stem="bxyz123")
    secret_bearing_brief = "do the thing sk-ant-oat01-supersecrettoken0000000000000000"
    _write_transcript(
        task_file,
        [_user_brief_line(ts, secret_bearing_brief), _assistant_line(ts, "msg-1", input_tokens=1)],
    )
    os.utime(task_file, (now.timestamp(), now.timestamp()))

    estimate = Q.build_usage_estimate(tmp_path / "no-main", now=now, subagent_root=tmp_path)

    assert len(estimate.subagent_tasks) == 1
    label = estimate.subagent_tasks[0].label
    assert label.startswith("bxyz123: ")
    assert "sk-ant" not in label
    assert "REDACTED" in label


def test_usage_estimate_subagent_tree_absent_degrades_cleanly(tmp_path: Path) -> None:
    now = datetime(2026, 9, 20, 12, 0, 0, tzinfo=UTC)
    estimate = Q.build_usage_estimate(
        tmp_path / "no-main", now=now, subagent_root=tmp_path / "no-subagent-tree"
    )
    assert estimate.subagent_tree_found is False
    assert estimate.subagent_tasks == ()
    assert estimate.fresh_subagent == 0


def test_subagent_task_marked_partial_when_tail_scan_hits_the_cap(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A task file bigger than `_USAGE_SCAN_MAX_TAIL_BYTES` whose window is
    never fully covered by the capped tail read must be reported
    `truncated=True` -- rendered on `/quota` as `partial` rather than
    silently understating that one task's numbers.
    """
    monkeypatch.setattr(Q, "_USAGE_SCAN_INITIAL_TAIL_BYTES", 50)
    # Big enough to contain one whole assistant JSON line (~242 bytes here),
    # small enough to stay well short of the file's total size below.
    monkeypatch.setattr(Q, "_USAGE_SCAN_MAX_TAIL_BYTES", 400)

    now = datetime(2026, 9, 20, 12, 0, 0, tzinfo=UTC)
    window_start = now - timedelta(hours=Q.USAGE_ESTIMATE_WINDOW_HOURS)
    task_file = _subagent_task_path(tmp_path, stem="bigtask")

    filler_lines = [
        {
            "type": "user",
            "timestamp": (window_start + timedelta(minutes=i + 1))
            .isoformat()
            .replace("+00:00", "Z"),
            "sessionId": "sess-1",
            "message": {},
        }
        for i in range(60)
    ]
    target_line = _assistant_line(now - timedelta(minutes=1), "msg-target", input_tokens=9)
    _write_transcript(
        task_file,
        [
            _user_brief_line(window_start + timedelta(seconds=1), "brief"),
            *filler_lines,
            target_line,
        ],
    )
    os.utime(task_file, (now.timestamp(), now.timestamp()))
    assert task_file.stat().st_size > 400 * 3, "test setup must exceed the small tail cap"

    estimate = Q.build_usage_estimate(tmp_path / "no-main", now=now, subagent_root=tmp_path)

    assert len(estimate.subagent_tasks) == 1
    task = estimate.subagent_tasks[0]
    assert task.truncated is True
    assert task.fresh_tokens == 9


def test_usage_estimate_skips_files_older_than_window_by_mtime(tmp_path: Path) -> None:
    now = datetime(2026, 9, 20, 12, 0, 0, tzinfo=UTC)
    project_dir = tmp_path / "proj1"
    project_dir.mkdir()
    old_file = project_dir / "old.jsonl"
    recent_file = project_dir / "recent.jsonl"
    _write_transcript(old_file, [_assistant_line(now, "msg-old", input_tokens=1)])
    _write_transcript(recent_file, [_assistant_line(now, "msg-recent", input_tokens=2)])
    old_mtime = (now - timedelta(hours=10)).timestamp()
    os.utime(old_file, (old_mtime, old_mtime))
    os.utime(recent_file, (now.timestamp(), now.timestamp()))

    estimate = Q.build_usage_estimate(tmp_path, now=now)

    assert estimate.main_files_scanned == 1
    assert estimate.distinct_session_count == 1
    assert estimate.fresh_main == 2


def test_usage_estimate_missing_directory_degrades_to_zero(tmp_path: Path) -> None:
    now = datetime(2026, 9, 20, 12, 0, 0, tzinfo=UTC)
    estimate = Q.build_usage_estimate(tmp_path / "does-not-exist", now=now)
    assert estimate.fresh_total == 0
    assert estimate.cache_read_total == 0
    assert estimate.distinct_session_count == 0
    assert estimate.main_files_scanned == 0
    assert estimate.by_role_model == ()
    assert estimate.subagent_tasks == ()


def test_usage_estimate_tail_scan_grows_to_cover_a_deeply_buried_line(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A small initial tail read must not silently lose an in-window line
    that sits far from the end of the file -- the doubling-by-4 growth
    (`_USAGE_SCAN_INITIAL_TAIL_BYTES` up to `_USAGE_SCAN_MAX_TAIL_BYTES`)
    must keep reading until the window is actually covered.
    """
    monkeypatch.setattr(Q, "_USAGE_SCAN_INITIAL_TAIL_BYTES", 50)
    monkeypatch.setattr(Q, "_USAGE_SCAN_MAX_TAIL_BYTES", 1_000_000)

    now = datetime(2026, 9, 20, 12, 0, 0, tzinfo=UTC)
    project_dir = tmp_path / "proj1"
    project_dir.mkdir()
    transcript = project_dir / "session1.jsonl"

    window_start = now - timedelta(hours=Q.USAGE_ESTIMATE_WINDOW_HOURS)
    target_line = _assistant_line(window_start + timedelta(seconds=1), "msg-target", input_tokens=7)
    filler_lines = [
        {
            "type": "user",
            "timestamp": (window_start + timedelta(minutes=i + 1))
            .isoformat()
            .replace("+00:00", "Z"),
            "sessionId": "sess-1",
            "message": {},
        }
        for i in range(40)
    ]
    _write_transcript(transcript, [target_line, *filler_lines])
    os.utime(transcript, (now.timestamp(), now.timestamp()))
    assert transcript.stat().st_size > 50 * 4, "test setup must exceed a few growth doublings"

    estimate = Q.build_usage_estimate(tmp_path, now=now)

    assert estimate.fresh_main == 7
    assert estimate.distinct_session_count == 1


def test_usage_estimate_cache_reuses_within_ttl_and_refreshes_after(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[int] = []
    stub = Q.UsageEstimate(
        window_start=datetime(2026, 9, 20, tzinfo=UTC),
        window_end=datetime(2026, 9, 20, tzinfo=UTC),
        by_role_model=(),
        subagent_tasks=(),
        fresh_main=0,
        fresh_subagent=0,
        fresh_total=0,
        cache_read_main=0,
        cache_read_subagent=0,
        cache_read_total=0,
        distinct_session_count=0,
        main_files_scanned=0,
        subagent_files_scanned=0,
        subagent_tree_found=False,
        topbar_label="fresh 0 (main 0, subagents 0) . 5h window",
        generated_at=datetime(2026, 9, 20, tzinfo=UTC),
    )

    def fake_build(
        root,
        *,
        now=None,
        max_files=Q._MAX_USAGE_TRANSCRIPT_FILES,
        subagent_root=None,
        max_subagent_files=Q._MAX_SUBAGENT_TASK_FILES,
    ):
        calls.append(1)
        return stub

    monkeypatch.setattr(Q, "build_usage_estimate", fake_build)
    cache = Q.UsageEstimateCache()
    base = datetime(2026, 9, 20, tzinfo=UTC)

    cache.get(now=base)
    cache.get(now=base + timedelta(seconds=30))
    assert len(calls) == 1, "a request within the 60s TTL must not re-scan"

    cache.get(now=base + timedelta(seconds=Q.USAGE_ESTIMATE_CACHE_TTL_SECONDS + 1))
    assert len(calls) == 2


# --------------------------------------------------------------------------
# 429 calibration (T6c): empirical window capacity from observed throttles
# --------------------------------------------------------------------------


def test_find_all_throttle_events_returns_empty_when_dir_missing(tmp_path: Path) -> None:
    assert Q.find_all_throttle_events(tmp_path / "does-not-exist") == ()


def test_find_all_throttle_events_collects_every_rejected_event(tmp_path: Path) -> None:
    project_dir = tmp_path / "proj1"
    project_dir.mkdir()
    transcript = project_dir / "session1.jsonl"
    lines = [
        json.dumps(
            {
                "type": "assistant",
                "timestamp": "2026-09-07T09:28:44.887Z",
                "message": {},
                "quotaLimits": {
                    "status": "rejected",
                    "resetsAt": 1_788_000_000,
                    "rateLimitType": "five_hour",
                },
            }
        ),
        json.dumps({"type": "assistant", "timestamp": "2026-09-07T10:00:00.000Z", "message": {}}),
        json.dumps(
            {
                "type": "assistant",
                "timestamp": "2026-09-07T14:00:00.000Z",
                "message": {},
                "quotaLimits": {
                    "status": "rejected",
                    "resetsAt": 1_788_100_000,
                    "rateLimitType": "five_hour",
                },
            }
        ),
    ]
    transcript.write_text("\n".join(lines) + "\n", encoding="utf-8")

    events = Q.find_all_throttle_events(tmp_path)
    assert len(events) == 2
    assert {e.status for e in events} == {"rejected"}


def test_compute_throttle_calibration_no_events_reports_not_observed(tmp_path: Path) -> None:
    now = datetime(2026, 9, 20, 12, 0, 0, tzinfo=UTC)
    calibration = Q.compute_throttle_calibration(
        now=now,
        current_fresh_total=1000,
        main_root=tmp_path / "does-not-exist",
        subagent_root=tmp_path / "does-not-exist-either",
    )
    assert calibration.available is False
    assert calibration.event_count == 0
    assert calibration.last_event is None
    assert calibration.last_fresh_at_event is None
    assert calibration.min_fresh_at_event is None
    assert calibration.median_fresh_at_event is None
    assert calibration.vs_last_throttle_ratio is None


def test_compute_throttle_calibration_computes_fresh_at_a_synthetic_event(
    tmp_path: Path,
) -> None:
    """For a synthetic 429, the calibration must sum fresh tokens (both
    sources, never cache_read) in the 5h window ending at the event's own
    timestamp, not "now" -- and report a ratio (never a percentage) against
    the caller-supplied current fresh total.
    """
    event_at = datetime(2026, 9, 18, 8, 19, 17, 850000, tzinfo=UTC)
    now = event_at + timedelta(hours=2)

    main_root = tmp_path / "main"
    project_dir = main_root / "proj1"
    project_dir.mkdir(parents=True)
    transcript = project_dir / "session1.jsonl"
    lines = [
        _assistant_line(
            event_at - timedelta(hours=1),
            "msg-main",
            input_tokens=100,
            output_tokens=50,
            cache_creation=25,
            cache_read=10,
        ),
        {
            "type": "assistant",
            "timestamp": event_at.isoformat().replace("+00:00", "Z"),
            "message": {},
            "quotaLimits": {
                "status": "rejected",
                "resetsAt": 1_788_329_400,
                "rateLimitType": "five_hour",
            },
        },
    ]
    _write_transcript(transcript, lines)
    os.utime(transcript, (event_at.timestamp(), event_at.timestamp()))

    subagent_root = tmp_path / "subagent"
    task_file = _subagent_task_path(subagent_root)
    _write_transcript(
        task_file,
        [
            _user_brief_line(event_at - timedelta(minutes=30), "brief"),
            _assistant_line(
                event_at - timedelta(minutes=30),
                "msg-sub",
                input_tokens=10,
                output_tokens=5,
                cache_read=1000,
            ),
        ],
    )
    os.utime(task_file, (event_at.timestamp(), event_at.timestamp()))

    calibration = Q.compute_throttle_calibration(
        now=now,
        current_fresh_total=500,
        main_root=main_root,
        subagent_root=subagent_root,
    )

    assert calibration.available is True
    assert calibration.event_count == 1
    # main fresh (100+50+25=175) + subagent fresh (10+5=15) = 190, cache_read excluded.
    assert calibration.last_fresh_at_event == 190
    assert calibration.min_fresh_at_event == 190
    assert calibration.median_fresh_at_event == 190
    assert calibration.vs_last_throttle_ratio == pytest.approx(500 / 190)
    assert calibration.last_event is not None
    assert calibration.last_event.at == event_at


def _write_throttle_event_fixture(tmp_path: Path, event_at: datetime) -> tuple[Path, Path]:
    """A main transcript with one `quotaLimits{status: "rejected"}` line at
    `event_at`, plus a subagent task tree old enough that
    `_throttle_window_coverage` reports `"full"` for that event (so a
    `vs_last_throttle_ratio` gets computed) -- shared by the T10 memoization
    tests below. Returns `(main_root, subagent_root)`.
    """
    main_root = tmp_path / "main"
    project_dir = main_root / "proj1"
    project_dir.mkdir(parents=True)
    transcript = project_dir / "session1.jsonl"
    _write_transcript(
        transcript,
        [
            _assistant_line(
                event_at - timedelta(hours=1),
                "msg-main",
                input_tokens=100,
                output_tokens=50,
                cache_creation=25,
                cache_read=10,
            ),
            {
                "type": "assistant",
                "timestamp": event_at.isoformat().replace("+00:00", "Z"),
                "message": {},
                "quotaLimits": {
                    "status": "rejected",
                    "resetsAt": 1_788_329_400,
                    "rateLimitType": "five_hour",
                },
            },
        ],
    )
    os.utime(transcript, (event_at.timestamp(), event_at.timestamp()))

    subagent_root = tmp_path / "subagent"
    old_enough = event_at - timedelta(days=1)
    task_file = _subagent_task_path(subagent_root)
    _write_transcript(task_file, [_user_brief_line(old_enough, "brief")])
    os.utime(task_file, (old_enough.timestamp(), old_enough.timestamp()))
    return main_root, subagent_root


def test_throttle_calibration_cache_memoizes_per_event_and_never_rescans_it(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """T10: a throttle event is immutable history. Once
    `ThrottleCalibrationCache` has computed a fresh-token figure for a given
    `(event.at, event.resets_at)`, a later `get()` call that sees the same
    event again must not re-invoke the expensive per-event scan
    (`_fresh_tokens_in_window`) -- only the cheap `find_all_throttle_events`
    discovery and an O(1) ratio recompute against the new
    `current_fresh_total` should run.
    """
    event_at = datetime(2026, 9, 18, 8, 0, 0, tzinfo=UTC)
    main_root, subagent_root = _write_throttle_event_fixture(tmp_path, event_at)
    now = event_at + timedelta(hours=1)

    calls: list[int] = []
    real_fresh_tokens_in_window = Q._fresh_tokens_in_window

    def counting_fresh_tokens_in_window(*args, **kwargs):
        calls.append(1)
        return real_fresh_tokens_in_window(*args, **kwargs)

    monkeypatch.setattr(Q, "_fresh_tokens_in_window", counting_fresh_tokens_in_window)

    cache = Q.ThrottleCalibrationCache()

    first = cache.get(
        now=now, current_fresh_total=100, main_root=main_root, subagent_root=subagent_root
    )
    assert first.available is True
    assert first.coverage == "full"
    assert len(calls) == 1

    second = cache.get(
        now=now, current_fresh_total=250, main_root=main_root, subagent_root=subagent_root
    )
    assert len(calls) == 1, "the same event must not be re-scanned on a repeat get()"
    assert second.last_fresh_at_event == first.last_fresh_at_event
    # The ratio is still recomputed fresh against the caller's own total.
    assert second.vs_last_throttle_ratio == pytest.approx(250 / first.last_fresh_at_event)
    assert second.state == "ready"


def test_compute_throttle_calibration_event_memo_skips_a_seen_event(tmp_path: Path) -> None:
    """The lower-level contract `ThrottleCalibrationCache` relies on: passing
    the same `event_memo` dict across two direct `compute_throttle_calibration`
    calls skips the scan for an event already in it, keyed by
    `(event.at, event.resets_at)`.
    """
    event_at = datetime(2026, 9, 18, 8, 0, 0, tzinfo=UTC)
    main_root, subagent_root = _write_throttle_event_fixture(tmp_path, event_at)
    now = event_at + timedelta(hours=1)
    memo: dict = {}

    first = Q.compute_throttle_calibration(
        now=now,
        current_fresh_total=100,
        main_root=main_root,
        subagent_root=subagent_root,
        event_memo=memo,
    )
    assert len(memo) == 1

    # A stale/wrong value planted directly into the memo proves the second
    # call reused it instead of recomputing (a real recompute would find the
    # fixture's actual 175 fresh tokens, not 999).
    (key,) = memo.keys()
    memo[key] = Q._EventCalibrationMemo(fresh=999, coverage="full")

    second = Q.compute_throttle_calibration(
        now=now,
        current_fresh_total=100,
        main_root=main_root,
        subagent_root=subagent_root,
        event_memo=memo,
    )
    assert second.last_fresh_at_event == 999
    assert first.event_count == second.event_count == 1


def test_throttle_calibration_cache_reports_computing_when_nothing_computed_yet_and_contended() -> (
    None
):
    """A request that arrives while a scan is already in flight (e.g. the
    T10 warm thread's first pass) must get the fixed `state="computing"`
    result immediately rather than wait for the lock (plan item 1: "must
    not block on the scan").
    """
    cache = Q.ThrottleCalibrationCache()
    acquired = cache._lock.acquire(blocking=False)
    assert acquired
    try:
        result = cache.get(now=datetime(2026, 9, 20, tzinfo=UTC), current_fresh_total=100)
    finally:
        cache._lock.release()

    assert result.state == "computing"
    assert result.available is False


def test_throttle_calibration_cache_serves_the_previous_result_once_warm_even_if_contended() -> (
    None
):
    """`computing` is only for "nothing computed yet" -- once at least one
    scan has completed, a contended `get()` serves that previous result
    instead, never the `computing` sentinel.
    """
    cache = Q.ThrottleCalibrationCache()
    stub = Q.ThrottleCalibration(
        available=True,
        last_event=None,
        last_fresh_at_event=123,
        event_count=1,
        min_fresh_at_event=123,
        median_fresh_at_event=123,
        vs_last_throttle_ratio=2.0,
    )
    cache._latest = stub

    acquired = cache._lock.acquire(blocking=False)
    assert acquired
    try:
        result = cache.get(now=datetime(2026, 9, 20, tzinfo=UTC), current_fresh_total=100)
    finally:
        cache._lock.release()

    assert result is stub
    assert result.state == "ready"


def test_quota_page_renders_computing_when_calibration_has_not_finished_its_first_scan(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cache = Q.ThrottleCalibrationCache()
    acquired = cache._lock.acquire(blocking=False)
    assert acquired  # left locked for the duration of this test: an in-flight scan
    monkeypatch.setattr(Q, "get_default_throttle_calibration_cache", lambda: cache)

    try:
        response = TestClient(create_app(warm=False)).get("/quota")
    finally:
        cache._lock.release()

    assert response.status_code == 200
    assert "computing" in response.text


# --------------------------------------------------------------------------
# Codex: first-class api-key state, dead subscription path
# --------------------------------------------------------------------------


def test_codex_apikey_state_label_is_exact(tmp_path: Path) -> None:
    auth_path = tmp_path / "auth.json"
    auth_path.write_text(
        json.dumps({"auth_mode": "apikey", "OPENAI_API_KEY": "sk-should-not-appear"}),
        encoding="utf-8",
    )
    state = Q.build_codex_quota_state(auth_path=auth_path)
    assert state.label == "api key billing -- no subscription quota"
    assert state.subscription_capable is False
    assert state.available is False
    assert "sk-should-not-appear" not in repr(state)


def test_codex_unknown_when_auth_json_missing(tmp_path: Path) -> None:
    state = Q.build_codex_quota_state(auth_path=tmp_path / "nope.json")
    assert state.auth_mode is None
    assert state.available is False


def test_codex_subscription_without_rpc_client_is_dead_code_state(tmp_path: Path) -> None:
    auth_path = tmp_path / "auth.json"
    auth_path.write_text(json.dumps({"auth_mode": "chatgpt"}), encoding="utf-8")
    state = Q.build_codex_quota_state(auth_path=auth_path)
    assert state.subscription_capable is True
    assert state.available is False
    assert "not wired" in state.label


class _FakeCodexRpcClient:
    def __init__(self, payload: object) -> None:
        self._payload = payload

    def read_rate_limits(self) -> object:
        return self._payload


def test_codex_subscription_with_rpc_client_parses_windows(tmp_path: Path) -> None:
    auth_path = tmp_path / "auth.json"
    auth_path.write_text(json.dumps({"auth_mode": "chatgpt"}), encoding="utf-8")
    payload = {
        "rateLimits": {
            "primary": {"usedPercent": 42, "resetsAt": 1_800_000_000, "windowDurationMins": 300},
            "secondary": {
                "usedPercent": 10,
                "resetsAt": 1_800_000_000,
                "windowDurationMins": 10080,
            },
        }
    }
    state = Q.build_codex_quota_state(auth_path=auth_path, rpc_client=_FakeCodexRpcClient(payload))
    assert state.available is True
    assert len(state.windows) == 2
    primary = next(w for w in state.windows if w.limit_id == "primary")
    assert primary.used_percent == 42
    assert primary.window_duration_mins == 300


def test_codex_rpc_client_exception_degrades_gracefully(tmp_path: Path) -> None:
    auth_path = tmp_path / "auth.json"
    auth_path.write_text(json.dumps({"auth_mode": "chatgpt"}), encoding="utf-8")

    class _Boom:
        def read_rate_limits(self) -> object:
            raise RuntimeError("boom, token=sk-ant-should-not-leak-anywhere-000000")

    state = Q.build_codex_quota_state(auth_path=auth_path, rpc_client=_Boom())
    assert state.available is False
    assert "sk-ant-should-not-leak" not in state.note


def test_parse_codex_rate_limits_response_schema() -> None:
    payload = {
        "rateLimits": {"primary": {"usedPercent": 5, "resetsAt": None, "windowDurationMins": None}}
    }
    windows = Q.parse_codex_rate_limits_response(payload)
    assert len(windows) == 1
    assert windows[0].limit_id == "primary"
    assert windows[0].used_percent == 5
    assert windows[0].resets_at is None


def test_parse_codex_rate_limits_response_malformed_returns_empty() -> None:
    assert Q.parse_codex_rate_limits_response("not a dict") == ()
    assert Q.parse_codex_rate_limits_response({"rateLimits": "nope"}) == ()


# --------------------------------------------------------------------------
# Topbar transform (pure)
# --------------------------------------------------------------------------


def test_to_topbar_quota_unavailable() -> None:
    now = datetime(2026, 9, 20, tzinfo=UTC)
    snapshot = Q.ClaudeQuotaSnapshot(
        fetched_at=now,
        available=False,
        windows=(),
        extra_usage=None,
        unavailable_reason="timeout",
        diagnostic=None,
    )
    report = Q.ClaudeQuotaReport(
        snapshot=snapshot,
        served_from_cache=False,
        cache_age_seconds=0.0,
        breaker_open=False,
        breaker_open_until=None,
        consecutive_failures=0,
        projection=Q.compute_burn_rate_projection((), now=now),
    )
    topbar = Q.to_topbar_quota(report, now=now)
    assert topbar.available is False
    assert topbar.unavailable_reason == "timeout"
    assert topbar.bars == ()


def test_to_topbar_quota_available_bars_and_projection() -> None:
    now = datetime(2026, 9, 20, tzinfo=UTC)
    windows = (
        Q.ClaudeWindow(
            key="five_hour",
            label="5h",
            percent_used=42.0,
            resets_at=now + timedelta(hours=2),
            status="ok",
        ),
        Q.ClaudeWindow(
            key="seven_day",
            label="7d",
            percent_used=85.0,
            resets_at=now + timedelta(days=3),
            status="warn",
        ),
        Q.ClaudeWindow(
            key="seven_day_opus", label="7d opus", percent_used=10.0, resets_at=None, status="ok"
        ),
    )
    snapshot = Q.ClaudeQuotaSnapshot(
        fetched_at=now,
        available=True,
        windows=windows,
        extra_usage=None,
        unavailable_reason=None,
        diagnostic=None,
        http_status=200,
    )
    projection = Q.BurnRateProjection(
        available=False,
        eta=None,
        rate_percent_per_hour=None,
        label="projection: not enough samples",
    )
    report = Q.ClaudeQuotaReport(
        snapshot=snapshot,
        served_from_cache=True,
        cache_age_seconds=5.0,
        breaker_open=False,
        breaker_open_until=None,
        consecutive_failures=0,
        projection=projection,
    )
    topbar = Q.to_topbar_quota(report, now=now)
    assert topbar.available is True
    # seven_day_opus is a `/quota`-only detail, not one of the topbar's two bars.
    assert {bar.key for bar in topbar.bars} == {"five_hour", "seven_day"}
    five_hour_bar = next(b for b in topbar.bars if b.key == "five_hour")
    assert five_hour_bar.percent_display == "42%"
    assert five_hour_bar.projection_label == "projection: not enough samples"
    seven_day_bar = next(b for b in topbar.bars if b.key == "seven_day")
    assert seven_day_bar.projection_label is None


# --------------------------------------------------------------------------
# App wiring
# --------------------------------------------------------------------------


def test_quota_route_returns_200(client: TestClient) -> None:
    response = client.get("/quota")
    assert response.status_code == 200


def test_quota_route_shows_no_credentials_state_by_default(client: TestClient) -> None:
    # The autouse fixture in tests/conftest.py points CLAUDE_CREDENTIALS_PATH
    # at a file that does not exist, for every test in this repo.
    response = client.get("/quota")
    assert "no credentials" in response.text


def test_quota_route_rejects_post(client: TestClient) -> None:
    response = client.post("/quota")
    assert response.status_code == 405


def test_quota_route_renders_credential_table_and_usage_estimate(client: TestClient) -> None:
    response = client.get("/quota")
    text = response.text.lower()
    assert "credential sources" in text
    assert "usage estimate" in text
    # The autouse fixture in tests/conftest.py neutralizes all three sources,
    # so every row in this round's table is "absent" -- see
    # test_quota_route_shows_no_credentials_state_by_default above.
    assert "absent" in text


def test_index_page_renders_codex_quota_state(client: TestClient) -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "Codex quota" in response.text


def test_compute_throttle_calibration_marks_partial_coverage_when_subagent_files_postdate_event(
    tmp_path: Path,
) -> None:
    """A throttle from before the oldest surviving subagent transcript can only
    be calibrated against main-session tokens: the figure is a lower bound,
    rendered with a >= sign, and no `vs last throttle` ratio is derived from
    it. Guards against the 2026-09-20 reading where a 2026-09-07 event (669k)
    was shown as "5.49x vs last throttle" although every /tmp task file
    dated from 2026-09-19."""
    event_at = datetime(2026, 9, 7, 9, 31, 0, tzinfo=UTC)
    subagent_root = tmp_path / "subagent"
    task_file = _subagent_task_path(subagent_root)
    task_file.parent.mkdir(parents=True)
    task_file.write_text(
        json.dumps(_user_brief_line(event_at + timedelta(days=12), "brief")) + "\n"
    )
    later = (event_at + timedelta(days=12)).timestamp()
    os.utime(task_file, (later, later))

    assert Q._throttle_window_coverage(event_at, subagent_root) == "partial"
    assert Q._throttle_window_coverage(event_at, tmp_path / "missing") == "main only"
    assert Q._throttle_window_coverage(event_at + timedelta(days=13), subagent_root) == "full"
