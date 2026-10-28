"""Current capture preparation/receipt boundaries, only invented HTTP replies."""

import ast
import json
import socket
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pytest
import requests

from open_composer.intraday_runner import current_initialization_account as account
from open_composer.intraday_runner import current_initialization_entry as entry
from open_composer.intraday_runner import current_initialization_runtime as runtime
from open_composer.intraday_runner import source_bounded_gateway as gateway


@pytest.fixture
def rig(tmp_path, monkeypatch):
    def deny(*a, **k):
        raise AssertionError("no actual network/factory in this fixture")

    monkeypatch.setattr(socket.socket, "connect", deny)
    monkeypatch.setattr(socket, "create_connection", deny)
    from open_composer.book_paper import accounts

    monkeypatch.setattr(accounts, "make_trading_client", deny)
    calls, guards = [], []

    class Client:
        def __init__(self):
            self._session = requests.Session()
            self._session.request = self.reply
            self.body = b'{"invented":true}'

        def reply(self, method, url, **kw):
            assert method == "GET" and guards[-1] == {}
            calls.append((method, url, kw))
            response = requests.Response()
            response.status_code = 200
            response._content = self.body
            response._content_consumed = True
            return response

        def get(self, endpoint, params):
            return self._session.request(
                "GET", "https://paper-api.alpaca.markets/v2" + endpoint, params=params
            ).json()

    def only_fixture(client):
        assert type(client) is Client

    monkeypatch.setattr(gateway, "_require_verified_paper_client", only_fixture)
    monkeypatch.setattr(runtime, "secure_identity", lambda: ("invented",))
    r = runtime.CurrentInitializationRuntime.__new__(runtime.CurrentInitializationRuntime)
    r.root = tmp_path
    r.auth = dict(
        account_hash="a" * 64,
        authorized_at="2026-10-19T00:00:00Z",
        expires_at="2026-11-14T00:00:00Z",
        reconciliation_after="2026-10-19T00:00:00Z",
    )
    r.authority = {"invented": True}
    monkeypatch.setattr(runtime, "load_authority", lambda *a: r.auth)
    r.clock = lambda: datetime(2026, 10, 19, 6, tzinfo=UTC)
    r.monotonic = lambda: 100.0
    r.entry_guard = lambda **kw: guards.append(kw)
    r._operation_held = True
    r.gateway = None
    r.client_factory = Client
    r.secure_snapshot = None
    r.trace_directory = tmp_path / "trace"
    r.trace_directory_identity = None
    r.current_request = None
    r.current_response = None
    r.current_phase = "decision"
    r.transport_count = r.transport_bytes = 0
    r.journal = None
    r.order_guard = r.cancel_window = lambda *a, **k: None
    return r, calls, guards


def get_one(r):
    r.current_request = dict(
        name="account",
        endpoint="/account",
        params={},
        at=r.clock().isoformat(),
        monotonic=r.monotonic(),
    )
    return r.gateway.client.get("/account", {})


def test_directory_preparation_and_final_physical_guard(rig):
    r, calls, guards = rig
    r.connect()
    identity = r.trace_directory_identity
    assert identity and identity[-1][0] == "/"
    get_one(r)
    assert len(calls) == 1
    prepared = json.loads((r.trace_directory / "0000.prepared.json").read_text())
    assert prepared["capture_request"] == r.current_request
    assert r.current_response["request"] == r.current_request
    assert r.current_response["response"]["status"] == 200
    assert not (r.trace_directory / "0000.response.json").exists()
    # Full final resource check follows the actual guarded durable publication.
    assert guards[-1] == {}
    assert guards[-2]["local_only"] is True
    assert r.trace_directory_identity == identity


def test_preparation_barrier_failure_before_fixture_factory(rig, monkeypatch):
    r, calls, guards = rig
    created = []
    r.client_factory = lambda: created.append(True)

    def fail(fd):
        raise OSError("invented barrier failure")

    monkeypatch.setattr(runtime.os, "fsync", fail)
    with pytest.raises(OSError):
        r.connect()
    assert created == calls == []


def test_prepared_write_refusal_has_no_physical_call(rig):
    r, calls, guards = rig
    r.connect()
    old = r.entry_guard

    def guard(**kw):
        if str(kw.get("write_path", "")).endswith(".prepared.json"):
            raise ValueError("budget refusal")
        return old(**kw)

    r.entry_guard = guard
    with pytest.raises(ValueError, match="budget"):
        get_one(r)
    assert calls == [] and not list(r.trace_directory.glob("*.json"))


@pytest.mark.parametrize("mutation", ["directory", "request", "expiry"])
def test_after_publication_drift_refuses_before_physical_call(rig, mutation):
    r, calls, guards = rig
    r.connect()
    old = r.save_capture

    def save(path, value):
        result = old(path, value)
        if path.name.endswith(".prepared.json"):
            if mutation == "directory":
                r.trace_directory.rename(r.trace_directory.with_name("retained-old-trace"))
                r.trace_directory.mkdir()
            elif mutation == "request":
                r.current_request["params"]["changed"] = True
            else:
                r.clock = lambda: datetime(2026, 11, 15, tzinfo=UTC)
        return result

    r.save_capture = save
    with pytest.raises(ValueError):
        get_one(r)
    assert calls == []


def test_unusable_sdk_reply_retains_response_metadata(rig, tmp_path):
    r, calls, guards = rig
    r.connect()
    r.gateway.client.body = b"not JSON"
    with pytest.raises(requests.exceptions.JSONDecodeError):
        account.capture(r, tmp_path / "account", clock=r.clock, monotonic=r.monotonic)
    receipt = json.loads((tmp_path / "account/account.unusable-response.json").read_text())
    assert receipt["usable"] is False and receipt["decoded_body"] is None
    assert receipt["response"]["status"] == 200 and len(calls) == 1
    assert r.current_request is r.current_response is None


def test_body_budget_refusal_retains_unusable_metadata(rig, tmp_path):
    r, calls, guards = rig
    r.connect()
    old = r.entry_guard

    def guard(**kw):
        if str(kw.get("write_path", "")).endswith("account/account.json"):
            raise ValueError("body budget refused")
        return old(**kw)

    r.entry_guard = guard
    with pytest.raises(ValueError, match="body budget"):
        account.capture(r, tmp_path / "account", clock=r.clock, monotonic=r.monotonic)
    receipt = json.loads((tmp_path / "account/account.unusable-response.json").read_text())
    assert receipt["usable"] is False and len(calls) == 1
    assert not (tmp_path / "account/account.json").exists()
    assert r.current_request is r.current_response is None


def test_financial_methods_and_limits_are_unchanged():
    path = "open_composer/intraday_runner/current_initialization_runtime.py"
    old = ast.parse(subprocess.check_output(["git", "show", "0752864d:" + path], text=True))
    new = ast.parse(Path(runtime.__file__).read_text())
    names = {
        "load_authority",
        "initialize",
        "observe",
        "receive_science",
        "decide",
        "order_guard",
        "buy",
        "reconcile",
        "cancel",
        "closeout",
        "abandon",
        "guard_write",
    }

    def selected(tree):
        return {
            n.name: ast.dump(n, include_attributes=False)
            for n in ast.walk(tree)
            if isinstance(n, ast.FunctionDef) and n.name in names
        }

    assert selected(old) == selected(new) and set(selected(old)) == names


@pytest.mark.parametrize(
    "kwargs",
    [
        {"preparation_only": None},
        {"preparation_only": 1},
        {"preparation_only": True, "extra_write_bytes": 1},
        {"preparation_only": True, "extra_write_bytes": False},
        {"preparation_only": True, "write_path": "/invented"},
        {"preparation_only": True, "write_method": "GET"},
        {"preparation_only": True, "local_only": True},
        {"preparation_only": True, "phase": "decision"},
    ],
)
def test_preparation_cannot_grant_publication_or_physical_request(kwargs):
    tree = ast.parse(Path(entry.__file__).read_text())
    run = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "run")
    check = next(n for n in run.body if isinstance(n, ast.FunctionDef) and n.name == "check")
    ns = {}
    exec(compile(ast.Module(body=[check], type_ignores=[]), "<exact-check>", "exec"), ns)
    # No gate/capacity/I/O globals exist: rejection must precede their use.
    with pytest.raises(ValueError, match="preparation"):
        ns["check"](**kwargs)


def test_full_final_guard_refusal_after_prepared_receipt(rig):
    r, calls, guards = rig
    r.connect()
    old = r.entry_guard

    def guard(**kwargs):
        if kwargs == {}:
            raise ValueError("fresh physical capacity refused")
        return old(**kwargs)

    r.entry_guard = guard
    with pytest.raises(ValueError, match="physical capacity"):
        get_one(r)
    assert (r.trace_directory / "0000.prepared.json").exists()
    assert not calls and r.current_response is None
