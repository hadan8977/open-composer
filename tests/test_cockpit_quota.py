from __future__ import annotations

import json
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
    return TestClient(create_app())


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

    response = TestClient(create_app()).get("/quota")

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


def test_index_page_renders_codex_quota_state(client: TestClient) -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "Codex quota" in response.text
