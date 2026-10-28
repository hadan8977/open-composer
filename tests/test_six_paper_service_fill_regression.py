"""Replay the authenticated saved fill receipts without any broker writes."""

import copy
import json
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from open_composer.intraday_runner import six_paper_service as service

ROOT = Path("/root/codex-test/open-composer")
EVIDENCE = ROOT / "reports/paper/diagnostics/resume-20261022"
DBC = "six-693c7f1ffc99d024bb4bdbbea91eb1093112"
TLT = "six-8f4d7df8f23373b8139855287fab17cfa8b5"


def replay_runtime(tmp_path, *, bad_tlt=False):
    state = json.loads((EVIDENCE / "repair-runtime-before.json").read_text())
    rows = json.loads((EVIDENCE / "read-only-account-orders.json").read_text())
    receipts = {r["client_order_id"]: r for r in rows["own_order_receipts"]}
    if bad_tlt:
        receipts[TLT] = dict(receipts[TLT], filled_avg_price="80.14")

    def get_order(cid):
        return copy.deepcopy(receipts[cid])

    path = tmp_path / "state.json"
    path.write_text(json.dumps(state))
    runtime = service.SixPaperService(
        ROOT,
        {},
        path,
        SimpleNamespace(get_order_by_client_id=get_order),
        clock=lambda: datetime(2026, 10, 22, 17, 57, tzinfo=UTC),
    )
    runtime.limiter.acquire = lambda: None
    return runtime


def test_saved_partial_and_multifill_limits_reconcile_once(tmp_path):
    runtime = replay_runtime(tmp_path)
    runtime.sync_orders()
    for cid, quantity, price in ((DBC, 4, 33.41), (TLT, 26, 80.13)):
        record = runtime.state["orders"][cid]
        receipt = f"{cid}:cumulative:{record['qty']}"
        actual = runtime.state["books"][record["book"]]["fills"][receipt]
        assert actual["quantity"] == quantity
        assert actual["price"] == price
        assert record["status"] == "filled"
        # Sell fee holds remain unresolved under the existing accounting policy.
        assert record["terminal_disposition"] is (cid == TLT)
        assert isinstance(record["applied_notional"], str)
    before = copy.deepcopy(runtime.state)
    runtime.sync_orders()
    after = copy.deepcopy(runtime.state)
    # Repeated failed lookups append observation counts, not financial activity.
    for cid in after["orders"]:
        previous = before["orders"][cid].pop("last_query_failure", None)
        observed = after["orders"][cid].pop("last_query_failure", None)
        if previous:
            assert observed["signature"] == previous["signature"]
            assert observed["matching_observations"] == previous["matching_observations"] + 1
    assert after == before


def test_real_limit_breach_still_halts_before_bad_fill_applied(tmp_path):
    runtime = replay_runtime(tmp_path, bad_tlt=True)
    before = copy.deepcopy(runtime.state["books"]["LSTM"])
    with pytest.raises(ValueError, match="actual price breached limit"):
        runtime.sync_orders()
    fills = runtime.state["books"]["LSTM"]["fills"]
    assert not any(f["client_order_id"] == TLT for f in fills.values())
    assert runtime.state["books"]["LSTM"]["cashbook"]["lots"].get("TLT") == (
        before["cashbook"]["lots"].get("TLT")
    )
