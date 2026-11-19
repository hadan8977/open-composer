"""Material stale-data and destructive-replacement boundaries for ETF resume."""

import importlib.util
import json
import sys
from datetime import UTC, date, datetime
from pathlib import Path

import pandas as pd
import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/refresh_etf_paper_inputs.py"
sys.path.insert(0, str(Path.cwd() / "scripts"))
spec = importlib.util.spec_from_file_location("etf_resume", SCRIPT)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def received():
    return pd.DataFrame(
        [
            dict(
                symbol="SPY",
                timestamp=pd.Timestamp(d, tz="UTC"),
                open=10.0,
                high=11.0,
                low=9.0,
                close=10.0,
                volume=100,
                trade_count=10,
            )
            for d in ("2026-10-19", "2026-10-20", "2026-10-21", "2026-10-22")
        ]
    )


def test_per_symbol_daily_history_freezes_leave_healthy_etfs():
    valid = received().assign(symbol="QQQ")
    start = datetime(2026, 10, 19, tzinfo=UTC)
    expected = date(2026, 10, 22)
    assert m.validate_received(received(), ["SPY"], start, expected) == {}
    for bad, reason in [
        (received().drop(index=1), "incomplete_daily_history"),
        (received().assign(low=12), "invalid_daily_bar"),
        (pd.concat([received(), received().iloc[:1]]), "incomplete_daily_history"),
    ]:
        assert m.validate_received(pd.concat([valid, bad]), ["QQQ", "SPY"], start, expected) == {
            "SPY": reason,
        }
        with pytest.raises(RuntimeError, match="No usable ETF"):
            m.validate_received(bad, ["SPY"], start, expected)


def test_prior_month_signal_is_valid_but_stale_stop_marks_reject(tmp_path):
    name = m.archive.SLEEVE_SPEC_NAMES[0]
    p = tmp_path / f"reports/execution/{name}-target-weights.json"
    p.parent.mkdir(parents=True)
    payload = dict(
        strategy_name=name,
        summary=dict(
            latest_session="2026-10-22",
            signal_session="2026-09-30",
            sleeve_guard=dict(marked_through="2026-10-22"),
        ),
    )
    p.write_text(json.dumps(payload))
    m.check_target(tmp_path, name, date(2026, 10, 22))
    payload["summary"]["sleeve_guard"]["marked_through"] = "2026-10-21"
    p.write_text(json.dumps(payload))
    with pytest.raises(RuntimeError, match="stale"):
        m.check_target(tmp_path, name, date(2026, 10, 22))


def test_completed_session_uses_exchange_close_and_weekend():
    assert m.completed_session(datetime(2026, 10, 23, 5, tzinfo=UTC)) == date(2026, 10, 22)
    assert m.completed_session(datetime(2026, 10, 23, 21, tzinfo=UTC)) == date(2026, 10, 23)
    assert m.completed_session(datetime(2026, 10, 25, 5, tzinfo=UTC)) == date(2026, 10, 23)


def test_revoked_sleeve_does_not_block_other_sleeves(tmp_path, monkeypatch):
    p = tmp_path / "reports/research/control/owner-compute-hold.json"
    p.parent.mkdir(parents=True)
    p.write_text(
        json.dumps(
            dict(
                existing_paper_operations_allowed=True,
                old_etf_paper_resume_20261023=dict(allowed=True),
            )
        )
    )
    first = m.archive.SLEEVE_SPEC_NAMES[0]

    def auth(root, name):
        if name == first:
            raise m.RehearsalError("revoked")
        return object()

    monkeypatch.setattr(m, "authorization", auth)
    m.permission(tmp_path)
    with pytest.raises(m.RehearsalError, match="revoked"):
        m.permission(tmp_path, first)


def test_friday_evening_cannot_queue_after_sunday_expiry(tmp_path, monkeypatch):
    from types import SimpleNamespace

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 10, 30, 23, 45, tzinfo=UTC)

    monkeypatch.setattr(m, "datetime", Clock)
    monkeypatch.setattr(
        m,
        "load_strategy_spec",
        lambda p: SimpleNamespace(data_assumptions=SimpleNamespace(timezone="America/New_York")),
    )
    monkeypatch.setattr(
        m,
        "load_rehearsal_authorization",
        lambda *a: SimpleNamespace(expires_at="2026-11-01T07:15:53+00:00"),
    )
    with pytest.raises(m.RehearsalError, match="exceeds original"):
        m.authorization(tmp_path, m.archive.SLEEVE_SPEC_NAMES[0])
