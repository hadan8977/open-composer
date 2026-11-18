"""Economic ownership, capital, clocks and displayed totals must agree."""

import copy
import hashlib
import json
import os
from datetime import date
from decimal import Decimal as D
from pathlib import Path

import pytest

from open_composer.cockpit.data.paper_overview import load_paper_overview
from scripts.build_paper_overview import (
    build,
    combine,
    effective_capital,
    funded_result,
    marked_component,
)
from scripts.reconcile_paper_history import recovered_evidence


def test_deposit_and_internal_transfer_are_capital_not_return():
    one = funded_result(160, 100, [dict(amount_usd=50)])
    assert one["pnl_usd"] == 10 and one["return_pct"] == D(10) / 150 * 100
    a = funded_result(130, 100, [dict(amount_usd=20)])
    b = funded_result(170, 200, [dict(amount_usd=-20)])
    result = combine([dict(id="a", **a), dict(id="b", **b)])
    assert result["capital_usd"] == 300 and result["pnl_usd"] == 0
    # A dollar-weighted return differs from the simple average of sleeve returns.
    assert result["return_pct"] != (a["return_pct"] + b["return_pct"]) / 2


def test_missing_capital_does_not_invent_percent():
    assert funded_result(10, 0)["return_pct"] is None


def test_missing_or_different_clock_makes_total_missing():
    a = dict(id="a", at="2026-10-24T00:00:00Z", **funded_result(110, 100))
    b = dict(id="b", at="2026-10-23T20:00:00Z", **funded_result(120, 100))
    assert combine([a, b])["pnl_usd"] is None
    b.update(at=a["at"], pnl_usd=None)
    assert combine([a, b])["missing"] == ["b"]


def test_component_uses_saved_position_clock_not_raw_close():
    series = dict(
        points=[
            dict(
                quantity={"X": "2"},
                realized_fifo_usd="3",
                remaining_fifo_cost_usd="20",
                trading_pnl_usd="999",
            )
        ]
    )
    assert marked_component(series, {"X": dict(qty="10", market_value="150")}) == 13
    assert marked_component(series, {}) is None


@pytest.fixture(scope="module")
def actual():
    root = Path(os.environ.get("OPEN_COMPOSER_ROOT", Path(__file__).parents[1]))
    directory = root / "reports/paper/diagnostics/fresh-dashboard-owner-audit-20261027/history-v1"
    if not (directory / "reconciled-history-v2.json").exists():
        pytest.skip("retained owner accounting receipts not in sample checkout")
    history = json.loads((directory / "reconciled-history-v2.json").read_text())
    received = recovered_evidence(root, {}, date(2026, 10, 26))
    state = json.loads((directory / "runtime-state-received.json").read_text())
    funding = json.loads(
        (directory.parent / "overview-v1/capital-clock-v2/funding-witnesses.json").read_text()
    )
    return history, received, state, funding


def test_actual_complete_batch_rows_adjustments_and_capital_reconcile(actual):
    output = build(*actual)
    s = output["snapshot"]
    assert {r["label"] for r in s["rows"]} == {
        "BASE",
        "H5",
        "LSTM",
        "STATE",
        "MULTI_EQUAL",
        "MULTI_HIERARCHICAL",
        "S1",
        "S2",
        "S3",
        "C2",
        "F1",
        "Retired top50",
    }
    assert len(s["rows"]) == 12
    assert s["pnl_usd"] == D("30077.41")
    assert s["capital_usd"] == D("1220004.45")
    assert sum(r["pnl_usd"] for r in s["rows"]) + s["adjustment_usd"] == s["pnl_usd"]
    assert (
        sum(r["capital_usd"] or D(0) for r in s["rows"]) + s["unassigned_capital_usd"]
        == s["capital_usd"]
    )
    assert s["return_pct"] == s["pnl_usd"] / s["capital_usd"] * 100
    pools = {p["id"]: p for p in s["pool_readings"]}
    assert pools["legacy"]["pnl_usd"] == D("5200.31")
    assert pools["six"]["pnl_usd"] == D("-488.46")
    assert pools["F1"]["pnl_usd"] == D("25365.56")
    assert output["six_unassigned_cash_usd"] == 880000
    assert output["F1_strategy_FILL_count"] == 4272
    assert len(output["probe_executions"]) == 2
    assert len(output["F1_canonical_plan_mismatches"]) == 2
    assert next(r for r in s["rows"] if r["label"] == "LSTM")["pnl_usd"] > 0
    assert next(r for r in s["rows"] if r["label"] == "S3")["pnl_usd"] < 0
    retired = next(r for r in s["rows"] if r["label"] == "Retired top50")
    assert retired["pnl_usd"] == D("6133.04") and retired["return_pct"] is None


def test_actual_daily_clocks_starts_and_three_anomalies(actual):
    output = build(*actual)
    daily = {p["day"]: p for p in output["daily"]}
    assert daily["2026-10-06"]["pools"] == ["legacy"]
    assert daily["2026-10-07"]["pools"] == ["legacy", "F1"]
    assert daily["2026-10-19"]["capital_usd"] == D("1100004.45")
    assert daily["2026-10-20"]["capital_usd"] is None
    assert daily["2026-10-20"]["return_pct"] is None
    assert daily["2026-10-20"]["pnl_usd"] == D("27010.92")
    assert daily["2026-10-20"]["known_capital_usd"] == D("1180004.45")
    assert daily["2026-10-20"]["capital_missing_details"] == [
        "six/MULTI_EQUAL",
        "six/MULTI_HIERARCHICAL",
    ]
    assert daily["2026-10-21"]["capital_usd"] == D("1220004.45")
    assert daily["2026-10-23"]["pnl_usd"] == D("22062.58")
    assert daily["2026-10-26"]["pnl_usd"] is None
    assert len(daily["2026-10-26"]["missing"]) == 3
    assert "2026-10-24" not in daily  # Saturday UTC points belong to Friday NY.
    assert len(output["quarantined_account_points"]) == 3
    assert output["snapshot"]["pnl_usd"] != daily["2026-10-23"]["pnl_usd"]


def test_actual_missing_mark_retains_supported_rows_but_no_total(actual):
    history, received, state, funding = actual
    received = copy.deepcopy(received)
    received["accounts"]["six"]["positions"][0]["market_value"] = None
    output = build(history, received, state, funding)
    assert output["snapshot"]["pnl_usd"] is None
    assert output["snapshot"]["return_pct"] is None
    assert next(r for r in output["snapshot"]["rows"] if r["id"] == "F1")["pnl_usd"] > 0


def test_actual_missing_required_daily_session_is_not_carried(actual):
    history, received, state, funding = actual
    received = copy.deepcopy(received)
    received["accounts"]["F1"]["points"] = [
        p for p in received["accounts"]["F1"]["points"] if p["day"] != "2026-10-22"
    ]
    daily = {p["day"]: p for p in build(history, received, state, funding)["daily"]}
    assert daily["2026-10-22"]["pnl_usd"] is None
    assert daily["2026-10-21"]["pnl_usd"] is not None


def test_actual_quantity_only_MA_not_extra_cash_and_probe_not_F1(actual):
    output = build(*actual)
    a = next(a for a in output["snapshot"]["adjustments"] if a["pool"] == "F1")
    assert a["entries"]["MA"] == 555
    assert a["entries"]["FEE"] == D("-11.86")  # Pre-baseline probe fees excluded.
    assert a["posted_usd"] == D("540.60")


def test_bound_reader_changed_artifact_is_unavailable(tmp_path):
    (tmp_path / "config").mkdir()
    p = tmp_path / "reports/paper/overview.json"
    p.parent.mkdir(parents=True)
    data = dict(
        schema_version=1,
        daily=[
            dict(
                day="2026-10-26",
                pnl_usd=None,
                return_pct=None,
                pools=["legacy"],
                missing=["legacy"],
            )
        ],
    )
    p.write_text(json.dumps(data))
    binding = dict(
        path="reports/paper/overview.json", sha256=hashlib.sha256(p.read_bytes()).hexdigest()
    )
    (tmp_path / "config/paper-overview-dashboard.json").write_text(json.dumps(binding))
    assert load_paper_overview(tmp_path)["available"]
    p.write_text(p.read_text() + " ")
    assert not load_paper_overview(tmp_path)["available"]


def test_funding_known_by_and_exact_BASE_flow_clock_are_independent():
    witness = dict(
        known_by="2026-10-20T12:00:00+00:00",
        initial_capital_usd="10000",
        flow_records=[dict(observed_at="2026-10-20T13:26:19.660111+00:00", amount_USD="10000")],
    )
    assert effective_capital(witness, "2026-10-20T11:59:59Z") is None
    assert effective_capital(witness, "2026-10-20T13:26:19.660110Z") == 10000
    assert effective_capital(witness, "2026-10-20T13:26:19.660111Z") == 20000
    composite = dict(known_by="2026-10-21T01:18:45.195142+00:00", initial_capital_usd="20000")
    assert effective_capital(composite, "2026-10-21T00:00:00Z") is None
    assert effective_capital(composite, "2026-10-22T00:00:00Z") == 20000


def test_unknown_denominator_preserves_supported_dollar_pnl():
    result = combine(
        [
            dict(id="known", capital_usd=D(100), pnl_usd=D(10)),
            dict(id="unknown", capital_usd=None, pnl_usd=D(3)),
        ]
    )
    assert result["pnl_usd"] == 13 and result["return_pct"] is None
    assert result["missing"] == [] and result["capital_missing"] == ["unknown"]


def test_missing_policy_witness_cannot_reuse_another_book_minimum(actual):
    history, received, state, funding = actual
    funding = copy.deepcopy(funding)
    del funding["policy_funding"]["MULTI_EQUAL"]
    with pytest.raises(ValueError, match="each top-level policy"):
        build(history, received, state, funding)
