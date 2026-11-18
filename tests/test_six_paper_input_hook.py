from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from open_composer.intraday_runner import six_paper_service as service


def fake_service(tmp_path, trace):
    calls = iter((True, True, False))

    def tick():
        trace.append("protective_tick")
        return next(calls)

    return SimpleNamespace(
        root=tmp_path,
        tick=tick,
        clock=lambda: datetime(2026, 10, 22, 19, tzinfo=UTC),
        event=lambda kind, **kw: trace.append((kind, kw)),
    )


def test_refresh_only_after_protection_and_retains_one_worker(tmp_path, monkeypatch):
    trace = []
    worker = object()
    seen = []

    def refresh(job, *, now):
        trace.append("input_step")
        seen.append(job)
        return worker

    monkeypatch.setattr(service, "_load_input_refresh", lambda root: refresh)
    service.service_loop(fake_service(tmp_path, trace), sleep=lambda seconds: trace.append(seconds))
    assert seen == [None, worker]
    assert trace == [
        "protective_tick",
        "input_step",
        15,
        "protective_tick",
        "input_step",
        15,
        "protective_tick",
    ]


@pytest.mark.parametrize("fail_load", [False, True])
def test_input_failure_never_prevents_next_protective_tick(tmp_path, monkeypatch, fail_load):
    trace = []

    def fail(*args, **kwargs):
        raise ValueError("unavailable input")

    monkeypatch.setattr(service, "_load_input_refresh", fail if fail_load else lambda root: fail)
    service.service_loop(fake_service(tmp_path, trace), sleep=lambda seconds: None)
    assert trace.count("protective_tick") == 3
    assert trace.count(("input_refresh_blocked", {"error_type": "ValueError"})) == 2


def test_once_never_loads_or_launches_input_work(tmp_path, monkeypatch):
    trace = []

    def unexpected(root):
        pytest.fail("--once must not load input worker")

    monkeypatch.setattr(service, "_load_input_refresh", unexpected)
    service.service_loop(fake_service(tmp_path, trace), once=True)
    assert trace == ["protective_tick"]
