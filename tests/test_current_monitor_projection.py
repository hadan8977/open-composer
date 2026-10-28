"""Existing-event projections, no broker or new event loop."""

import json
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from open_composer.intraday_runner.current_initialization_monitor import publish
from open_composer.intraday_runner.source_activity_reception import save
from open_composer.intraday_runner.source_state_checkpoint import SourceStateCheckpoint
from open_composer.intraday_runner.validation_account_partition import ACCOUNT, BASE, slot


def test_projection_uses_funded_checkpoint_and_keeps_pnl_unknown(tmp_path):
    ledger, _ = slot(tmp_path, BASE)
    ledger.mkdir(parents=True)
    evidence = dict(
        allocated_capital="20000",
        risk={"killed": False, "halted": False},
        allocation_flows=[dict(amount_USD=10000, profit_USD=0)],
    )
    store = SourceStateCheckpoint(ledger / "checkpoints", account_hash=ACCOUNT, sleeve_id=BASE)
    store.commit(
        dict(
            cashbook=dict(cash=20000, sales=[], purchases=[], dividends=[], lots={}, next_id=0),
            pending={},
            consumed_ids=[],
            applied_fill_ids=[],
            fills={},
            fees={},
            evidence=evidence,
        ),
        expected_head_sha256=None,
    )
    save(ledger / "initial-decision.json", dict(status="current_model_evaluated"))
    result = save(
        ledger / "invocations/example/decision/result.json", dict(status="actual_decision")
    )
    save(
        Path(result["path"]).parent / "account/capture-data.json",
        dict(
            orders={
                "a": dict(id="one", status="partially_filled"),
                "b": dict(id="two", status="rejected"),
            },
            positions=[],
        ),
    )
    auth = save(ledger / "authority.json", {})
    observed = datetime(2026, 10, 19, 10, tzinfo=UTC)
    from open_composer.adapters.broker.alpaca_paper import _atomic_write_text

    rt = SimpleNamespace(
        task=BASE,
        root=tmp_path,
        directory=ledger,
        store=store,
        clock=lambda: observed,
        authority=auth,
        auth=dict(spec=auth, policy=auth),
        write_text=_atomic_write_text,
        ensure_directory=lambda p: p.mkdir(parents=True, exist_ok=True),
    )
    b = publish(rt, "decision", result)
    v = json.loads(Path(b["path"]).read_text())
    assert v["capital_usd"] == 20000 and v["status"] == "running"
    assert v["nav_usd"] is None and v["net_pnl_usd"] is None and v["net_pnl_status"] == "unknown"
    assert v["orders"] == dict(submitted=2, filled=0, rejected=1, pending=1)
    assert v["allocation_flows"][0]["profit_USD"] == 0
    assert v["source_bindings"]["checkpoint"]["path"].startswith("reports/")
    f = publish(rt, "buy", result, failed=True)
    v = json.loads(Path(f["path"]).read_text())
    assert v["status"] == "failed" and v["reconciled_at_utc"] is None
    rt.write_text = lambda *a, **k: (_ for _ in ()).throw(ValueError("storage denied"))
    with pytest.raises(ValueError):
        publish(rt, "decision", result)


@pytest.mark.parametrize("halted", [True, None, "unknown", 1])
def test_daily_or_unknown_halt_is_not_running(tmp_path, halted):
    from open_composer.adapters.broker.alpaca_paper import _atomic_write_text

    ledger, _ = slot(tmp_path, BASE)
    ledger.mkdir(parents=True)
    store = SourceStateCheckpoint(ledger / "checkpoints", account_hash=ACCOUNT, sleeve_id=BASE)
    store.commit(
        dict(
            cashbook=dict(cash=20000, sales=[], purchases=[], dividends=[], lots={}, next_id=0),
            pending={},
            consumed_ids=[],
            applied_fill_ids=[],
            fills={},
            fees={},
            evidence=dict(allocated_capital="20000", risk=dict(halted=halted, killed=False)),
        ),
        expected_head_sha256=None,
    )
    save(ledger / "initial-decision.json", {})
    result = save(ledger / "invocations/test/buy/result.json", dict(status="risk_halt"))
    auth = save(ledger / "authority.json", {})
    rt = SimpleNamespace(
        task=BASE,
        root=tmp_path,
        directory=ledger,
        store=store,
        clock=lambda: datetime(2026, 10, 19, 14, tzinfo=UTC),
        authority=auth,
        auth=dict(spec=auth, policy=auth),
        write_text=_atomic_write_text,
        ensure_directory=lambda p: p.mkdir(parents=True, exist_ok=True),
    )
    v = json.loads(Path(publish(rt, "buy", result)["path"]).read_text())
    assert v["status"] == "halted" and v["net_pnl_usd"] is None
    assert v["risk_latches"] == dict(killed=False, halted=True if halted is True else None)
