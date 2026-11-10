"""Offline T03 repair tests: all extraction calls and credentials are fixtures."""

from __future__ import annotations

import ast
import json
import socket
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import t03_llm_extract as extract  # noqa: E402
import t03_retry as policy  # noqa: E402
from score_earnings_text import ChatCallResult  # noqa: E402

NOW = datetime(2026, 10, 11, 10, 0, tzinfo=UTC)
PERIOD_MESSAGE = "period request limit: window=720h requests=18002 effective_max=18000"


def limited(headers=None, *, code="rate_limit_exceeded", message="limited"):
    return ChatCallResult(
        429,
        None,
        raw_body=json.dumps({"error": {"code": code, "message": message}}),
        headers=headers or {},
    )


def detail(result):
    return policy.diagnostics(result, now=NOW, limited=extract.st.is_rate_limited(result))


def test_real_period_quota_blocks_even_with_retry_header(tmp_path):
    d = detail(limited({"Retry-After": "60"}, code="429", message=PERIOD_MESSAGE))
    assert d["reason"] == "period_quota_exhausted"
    assert d["error_code"] == "429"
    assert d["quota_window_hours"] == 720
    assert d["requests_used"] == 18002
    assert d["requests_limit"] == 18000
    assert d["recovery_at"] is None
    state = policy.record_failure(tmp_path / "state.json", {}, d, now=NOW)
    assert state["blocked"] and state["next_action"] == policy.BLOCK_ACTION
    assert "message" not in state and "raw_body" not in state


@pytest.mark.parametrize(
    "headers,seconds",
    [
        ({"rEtRy-AfTeR": "120"}, 120),
        ({"Retry-After": "Sun, 11 Oct 2026 10:03:00 GMT"}, 180),
        ({"Retry-After": "120", "X-RateLimit-Reset-Tokens": "2m30s"}, 150),
        ({"X-RateLimit-Reset": str(int((NOW + timedelta(seconds=240)).timestamp()))}, 240),
        ({"X-RateLimit-Reset": str(int((NOW + timedelta(seconds=240)).timestamp() * 1000))}, 240),
        ({"RateLimit-Reset": "1h2m3s"}, 3723),
    ],
)
def test_retry_headers_use_latest_safe_recovery(headers, seconds):
    d = detail(limited(headers))
    assert d["reason"] == "rate_limit_with_recovery"
    assert datetime.fromisoformat(d["recovery_at"]) == NOW + timedelta(seconds=seconds)


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"Retry-After": "nonsense"},
        {"Retry-After": "0"},
        {"Retry-After": "Sun, 11 Oct 2026 09:00:00 GMT"},
        {"Retry-After": "9" * 500},
        {"X-RateLimit-Reset": "Bearer sk-secret"},
    ],
)
def test_no_recovery_never_invents_30_minute_wait(headers):
    d = detail(limited(headers))
    assert d["reason"] == "rate_limit_without_recovery"
    assert d["recovery_at"] is None


def test_secrets_never_leave_structured_diagnostics(tmp_path):
    secret = "sk-fixture-secret-012345"
    result = limited(
        {
            "Authorization": "Bearer " + secret,
            "Set-Cookie": secret,
            "Cookie": secret,
            "X-Api-Key": secret,
            "X-Request-Id": secret,
            "Retry-After": secret,
            "Request-Id": "req_0123456789abcdef",
        },
        code=secret,
        message="Authorization: " + secret,
    )
    result.raw_body = json.dumps(
        {"error": {"code": secret, "type": secret, "message": secret}, "token": secret}
    )
    result.error = "Cookie=" + secret
    d = detail(result)
    assert d["error_code"] == d["error_type"] == "unrecognized"
    assert d["headers"] == {"request-id": "req_0123456789abcdef"}
    state = policy.record_failure(tmp_path / "state.json", {}, d, now=NOW)
    text = json.dumps(state)
    for value in (secret, "Authorization", "Cookie", "raw_body", "message"):
        assert value not in text


@pytest.mark.parametrize(
    "result,reason",
    [
        (
            ChatCallResult(400, None, raw_body='{"error":{"code":"insufficient_quota"}}'),
            "hard_quota",
        ),
        (ChatCallResult(500, None, raw_body="internal error"), "http_error"),
        (ChatCallResult(0, None, error="secret transport text"), "transport_error"),
    ],
)
def test_error_classification(result, reason):
    assert detail(result)["reason"] == reason


def test_failures_persist_until_threshold_across_process_reads(tmp_path):
    path, ledger = tmp_path / "state.json", tmp_path / "ledger.jsonl"
    d = detail(limited({"Retry-After": "120"}))
    for expected in range(1, 4):
        state = policy.record_failure(path, policy.read_state(path, ledger), d, now=NOW)
        assert state["consecutive_failures"] == expected
        assert state["blocked"] is (expected == 3)
    again = policy.record_failure(path, policy.read_state(path, ledger), d, now=NOW)
    assert again["blocked"] and again["consecutive_failures"] == 4


def test_initializer_adopts_existing_103_calls_without_ledger_or_marker_changes(tmp_path):
    ledger, state, marker = (
        tmp_path / name for name in ("ledger.jsonl", "state.json", "next_try_at.json")
    )
    rows = [{"t": NOW.isoformat(), "status": 200}]
    rows += [{"t": NOW.isoformat(), "status": 429} for _ in range(102)]
    rows += [{"t": NOW.isoformat(), "status": 429, "purpose": "owner_requested_fault_diagnostic"}]
    ledger.write_text("".join(json.dumps(row) + "\n" for row in rows))
    marker.write_text('{"next_try_at":"legacy-marker"}')
    before = ledger.read_bytes(), marker.read_bytes()
    diagnostic = {
        "finished_at_utc": NOW.isoformat(),
        "http_status": 429,
        "error": {"code": "429", "message": PERIOD_MESSAGE},
        "response_headers": {},
    }
    first = policy.initialize_hard_block(diagnostic, state, ledger)
    second = policy.initialize_hard_block(diagnostic, state, ledger)
    assert first == second and first["consecutive_failures"] == 103 and first["blocked"]
    assert first["reason"] == "period_quota_exhausted"
    assert before == (ledger.read_bytes(), marker.read_bytes())


@pytest.fixture
def sandbox(monkeypatch, tmp_path):
    out, snippets = tmp_path / "out", tmp_path / "snippets"
    out.mkdir()
    snippets.mkdir()
    for name, value in {
        "OUT": out,
        "SNIP": snippets,
        "LEDGER": out / "ledger.jsonl",
        "NEXT_TRY": out / "next_try_at.json",
        "LOCK": out / ".lock",
        "FAILURE_STATE": out / "failure_state.json",
    }.items():
        monkeypatch.setattr(extract, name, value)
    monkeypatch.setattr(sys, "argv", ["t03_llm_extract.py"])
    monkeypatch.setattr(extract.time, "sleep", lambda _: None)
    monkeypatch.setattr(
        socket, "create_connection", lambda *a, **k: pytest.fail("network forbidden")
    )
    calls, credential_reads = [], []
    results = []

    def credentials(_):
        credential_reads.append(True)
        return {
            "OC_TEXT_SCORER_BASE_URL": "fixture",
            "OC_TEXT_SCORER_API_KEY": "fixture",
            "OC_TEXT_SCORER_MODEL": "fixture",
        }

    def call(messages):
        calls.append(messages)
        assert results, "unexpected model call"
        return results.pop(0)

    monkeypatch.setattr(extract.st, "load_credentials", credentials)
    monkeypatch.setattr(extract.st, "make_requests_chat_call_fn", lambda **_: call)
    filings = [
        {
            "accession": "a",
            "cik": "1",
            "filing_date": "2026-10-01",
            "acceptance_datetime": "2026-10-01T10:00:00Z",
            "status": "ok",
            "snippets": ["Customer Acme purchased 15% of revenue."],
        }
    ]
    (snippets / "part_main_1.jsonl").write_text(json.dumps(filings[0]) + "\n")
    return out, results, calls, credential_reads


def good():
    return ChatCallResult(200, '{"no_major_customer":false,"customers":[{"name":"Acme"}]}')


def test_429_is_not_success_and_creates_no_empty_part(sandbox, capsys):
    out, results, calls, _ = sandbox
    results.append(limited(code="429", message=PERIOD_MESSAGE))
    assert extract.main() == policy.EXIT_BLOCKED
    assert len(calls) == 1 and not list(out.glob("part_*.jsonl"))
    assert json.loads(extract.FAILURE_STATE.read_text())["blocked"]
    assert extract.main() == policy.EXIT_BLOCKED and len(calls) == 1
    assert "no progress" in capsys.readouterr().out


def test_retry_header_429_circuit_counts_across_extractor_restarts(sandbox):
    _, results, calls, _ = sandbox
    for count in range(1, 4):
        if extract.NEXT_TRY.exists():
            marker = json.loads(extract.NEXT_TRY.read_text())
            marker["next_try_at"] = (datetime.now(UTC) - timedelta(seconds=1)).isoformat()
            policy.write_json(extract.NEXT_TRY, marker)
        results.append(limited({"Retry-After": "120"}))
        assert extract.main() == (policy.EXIT_WAIT if count < 3 else policy.EXIT_BLOCKED)
        assert json.loads(extract.FAILURE_STATE.read_text())["consecutive_failures"] == count
    assert extract.main() == policy.EXIT_BLOCKED and len(calls) == 3


def test_error_body_and_request_text_do_not_enter_ledger_or_stdout(sandbox, capsys):
    _, results, _, _ = sandbox
    secret = "sk-fixture-should-never-be-stored"
    result = limited({"Authorization": secret, "Set-Cookie": secret}, message=secret)
    result.error = secret
    results.append(result)
    assert extract.main() == policy.EXIT_BLOCKED
    files = (
        extract.LEDGER.read_text()
        + extract.FAILURE_STATE.read_text()
        + extract.NEXT_TRY.read_text()
    )
    output = capsys.readouterr()
    for forbidden in (
        secret,
        "Authorization",
        "Set-Cookie",
        "raw_body",
        "Customer Acme",
        extract.INSTRUCTION,
    ):
        assert forbidden not in files + output.out + output.err


def test_second_json_call_429_is_blocked_and_does_not_finish_accession(sandbox):
    out, results, calls, _ = sandbox
    results.extend([ChatCallResult(200, "bad JSON"), limited(code="429", message=PERIOD_MESSAGE)])
    assert extract.main() == policy.EXIT_BLOCKED and len(calls) == 2
    assert not extract.done_accessions() and not list(out.glob("part_*.jsonl"))
    assert json.loads(extract.FAILURE_STATE.read_text())["reason"] == "period_quota_exhausted"


def test_unparsable_200_does_not_clear_failure_or_mark_accession_done(sandbox):
    _, results, _, _ = sandbox
    policy.write_json(extract.FAILURE_STATE, {"consecutive_failures": 1, "blocked": False})
    results.extend([ChatCallResult(200, "bad JSON"), ChatCallResult(200, "still bad JSON")])
    assert extract.main() == policy.EXIT_NO_PROGRESS
    assert json.loads(extract.FAILURE_STATE.read_text())["consecutive_failures"] == 2
    assert not extract.done_accessions()


def test_fully_used_880_cap_prevents_credentials_and_calls(sandbox):
    _, _, calls, credential_reads = sandbox
    now = datetime.now(UTC)
    extract.LEDGER.write_text(
        "".join(json.dumps({"t": now.isoformat(), "status": 200}) + "\n" for _ in range(880))
    )
    assert extract.main() == policy.EXIT_WAIT
    assert not calls and not credential_reads


def test_http_200_content_with_limit_word_is_not_rate_limited(sandbox):
    _, results, calls, _ = sandbox
    results.append(
        ChatCallResult(
            200, '{"customers":[{"name":"Limited Company"}]}', raw_body="limitations quota"
        )
    )
    assert extract.main() == 0 and len(calls) == 1
    assert not extract.FAILURE_STATE.exists()


def test_success_clears_failure_and_preserves_done_accession_boundary(sandbox):
    out, results, calls, credential_reads = sandbox
    policy.write_json(extract.FAILURE_STATE, {"consecutive_failures": 2, "blocked": False})
    policy.write_json(extract.NEXT_TRY, {"next_try_at": (NOW - timedelta(days=1)).isoformat()})
    results.append(good())
    assert extract.main() == 0
    assert not extract.FAILURE_STATE.exists() and not extract.NEXT_TRY.exists()
    assert extract.done_accessions() == {"a"}
    assert extract.main() == 0
    assert len(calls) == len(credential_reads) == 1 and len(list(out.glob("part_*.jsonl"))) == 1
    assert calls[0][0]["content"] == extract.SYSTEM
    assert calls[0][1]["content"].startswith(extract.INSTRUCTION)


def test_json_retry_failure_status_is_not_written_as_success(sandbox):
    out, results, calls, _ = sandbox
    results.extend([ChatCallResult(200, "bad JSON"), ChatCallResult(500, None, raw_body="error")])
    assert extract.main() == policy.EXIT_NO_PROGRESS
    assert len(calls) == 2 and not extract.done_accessions()
    assert not list(out.glob("part_*.jsonl"))
    assert json.loads(extract.FAILURE_STATE.read_text())["consecutive_failures"] == 1


def test_local_cap_includes_json_retry(sandbox, monkeypatch):
    out, results, calls, _ = sandbox
    now = datetime.now(UTC)
    extract.LEDGER.write_text(
        "".join(json.dumps({"t": now.isoformat(), "status": 200}) + "\n" for _ in range(879))
    )
    results.append(ChatCallResult(200, "bad JSON"))
    assert extract.main() == policy.EXIT_WAIT and len(calls) == 1
    assert not list(out.glob("part_*.jsonl"))
    marker = json.loads(extract.NEXT_TRY.read_text())
    assert marker["reason"] == "local cap"
    assert datetime.fromisoformat(marker["next_try_at"]) >= now + timedelta(hours=5)


def test_wait_and_legacy_block_never_load_credentials(sandbox):
    _, _, calls, credential_reads = sandbox
    policy.write_json(
        extract.NEXT_TRY, {"next_try_at": (datetime.now(UTC) + timedelta(hours=1)).isoformat()}
    )
    assert extract.main() == policy.EXIT_WAIT
    extract.LEDGER.write_text(
        "".join(json.dumps({"t": NOW.isoformat(), "status": 429}) + "\n" for _ in range(3))
    )
    assert extract.main() == policy.EXIT_BLOCKED
    assert calls == credential_reads == []


def test_probe_requires_evidence_and_does_not_clear_on_failure(sandbox, monkeypatch):
    _, results, calls, _ = sandbox
    policy.write_json(extract.FAILURE_STATE, {"blocked": True, "consecutive_failures": 103})
    monkeypatch.setattr(sys, "argv", ["t03_llm_extract.py", "--recovery-probe"])
    assert extract.main() == policy.EXIT_BLOCKED and not calls
    evidence = extract.OUT / "reviewed-evidence.json"
    policy.write_json(evidence, {"recovery_confirmed": True, "basis": "provider_quota_recovered"})
    monkeypatch.setattr(
        sys,
        "argv",
        ["t03_llm_extract.py", "--recovery-probe", "--recovery-evidence", str(evidence)],
    )
    results.append(limited(code="429", message=PERIOD_MESSAGE))
    assert extract.main() == policy.EXIT_BLOCKED and len(calls) == 1
    assert json.loads(extract.FAILURE_STATE.read_text())["consecutive_failures"] == 104
    results.append(good())
    assert extract.main() == 0 and len(calls) == 2
    assert not extract.FAILURE_STATE.exists()


def test_frozen_extraction_constants_and_functions_match_before():
    before = (
        ROOT / "reports/research/program/autonomy-repair-20261011/before/scripts/t03_llm_extract.py"
    )
    names = {
        "SYSTEM",
        "INSTRUCTION",
        "NEG",
        "PCT_RE",
        "MAX_TOKENS",
        "CAP_PER_5H",
        "WINDOW",
        "is_negative",
        "parse_reply",
        "prompt_hash",
        "done_accessions",
        "load_filings",
    }

    def nodes(path):
        values = {}
        for node in ast.parse(path.read_text()).body:
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id in names:
                        values[target.id] = ast.dump(node.value)
            elif isinstance(node, ast.FunctionDef) and node.name in names:
                values[node.name] = ast.dump(node)
        return values

    assert nodes(before) == nodes(ROOT / "scripts/t03_llm_extract.py")


@pytest.mark.parametrize("rc", [20, 21, 37])
def test_supervisor_preserves_real_failure_exit_and_stops_without_sleep(tmp_path, rc):
    scripts, venv = tmp_path / "scripts", tmp_path / ".venv/bin"
    scripts.mkdir()
    venv.mkdir(parents=True)
    driver = scripts / "t03_run_llm.sh"
    driver.write_text((ROOT / "scripts/t03_run_llm.sh").read_text())
    fake = venv / "python"
    fake.write_text(
        f"#!/bin/bash\necho 'to extract 1;'\necho 'no progress; fixture failure'\nexit {rc}\n"
    )
    fake.chmod(0o755)
    result = subprocess.run(["bash", str(driver)], capture_output=True, text=True, timeout=3)
    assert result.returncode == rc
    log = (tmp_path / "logs/t03_llm.log").read_text()
    assert f"exit={rc}" in log and "stopped" in log and "no progress" in log
    assert "uv run" not in driver.read_text()
