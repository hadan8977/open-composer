"""A selected strategy keeps its equal share through prelaunch cash and gaps."""

import copy
import json
import os
from pathlib import Path

import pytest

from open_composer.cockpit.data import paper_comparison as module
from open_composer.cockpit.data.paper_comparison import (
    build_paper_comparison,
    compare_paper_strategies,
)


def valuation(day, pnl, capital=100):
    return dict(day=day, trading_pnl_usd=pnl, capital_usd=capital, missing=[])


@pytest.fixture
def comparison():
    history = {
        "available": True,
        "through_session": "2026-10-12",
        "histories": [
            {
                "id": "A",
                "kind": "trading_component",
                "first_fill": "2026-10-06",
                "points": [
                    valuation("2026-10-06", 10),
                    valuation("2026-10-07", 20),
                    valuation("2026-10-08", None),
                    valuation("2026-10-09", 30),
                    valuation("2026-10-12", 40),
                ],
            },
            {
                "id": "B",
                "kind": "trading_component",
                "first_fill": "2026-10-07",
                "points": [
                    valuation("2026-10-07", 10),
                    valuation("2026-10-08", 20),
                    valuation("2026-10-09", 30),
                    valuation("2026-10-12", 20),
                ],
            },
            {
                "id": "parent",
                "kind": "composite_parent",
                "children": ["parent/child"],
                "points": [valuation("2026-10-12", 3)],
            },
            {
                "id": "parent/child",
                "kind": "trading_component",
                "first_fill": "2026-10-12",
                "points": [valuation("2026-10-12", 90)],
            },
        ],
    }
    rows = [
        dict(
            id=identity,
            label=identity,
            href="/paper/ledger/" + identity,
            capital_usd=capital,
            return_pct=percent,
            observed_at="2026-10-13T04:00:00Z",
        )
        for identity, capital, percent in (
            ("A", 10000, 10),
            ("B", 1000000, -10),
            ("parent", 20000, 3),
            ("parent/child", 20000, 90),
            ("retired", None, None),
        )
    ]
    rows[-1].update(status="已退出")
    dashboard = dict(rows=rows, snapshot_at="2026-10-13T04:00:00Z")
    return build_paper_comparison(history, {}, dashboard)


def test_cumulative_mean_has_equal_shares_and_is_not_a_rebalanced_or_money_weighted_return(
    comparison,
):
    result = compare_paper_strategies(comparison, ["A", "B"])
    assert result["snapshot"]["return_pct"] == 0
    assert result["snapshot"]["equity_usd"] == 100000
    daily = {p["day"]: p for p in result["daily"]}
    assert daily["2026-10-06"]["return_pct"] == 5  # B is an allocated cash sleeve.
    assert daily["2026-10-07"]["return_pct"] == 15
    assert daily["2026-10-07"]["equity_usd"] == pytest.approx(115000)
    assert daily["2026-10-07"]["change_usd"] == pytest.approx(10000)
    assert daily["2026-10-07"]["change_pct"] == pytest.approx((115000 / 105000 - 1) * 100)
    assert daily["2026-10-08"]["equity_usd"] is None
    assert daily["2026-10-08"]["missing"] == ["A"]
    assert daily["2026-10-09"]["return_pct"] == 30
    assert daily["2026-10-09"]["change_pct"] is None  # No bridging the missing session.
    assert daily["2026-10-12"]["change_pct"] == 0
    assert "2026-10-10" not in daily  # Friday to Monday are adjacent sessions.
    assert result["snapshot"]["at"] == "2026-10-13T04:00:00Z"
    assert result["daily"][-1]["day"] == "2026-10-12"  # Current values are never appended.


def test_solo_selection_and_archived_or_child_choices(comparison):
    choices = {s["id"]: s for s in comparison["strategies"]}
    assert "parent/child" not in choices and choices["parent"]["selectable"]
    assert not choices["retired"]["selectable"] and not choices["retired"]["default_selected"]
    assert choices["B"]["points"][0] == dict(
        day="2026-10-06", return_pct=0, state="not_started", source_at=None
    )
    result = compare_paper_strategies(comparison, ["B"])
    assert result["snapshot"]["pnl_usd"] == -10000
    assert result["daily"][0]["day"] == "2026-10-07"
    assert next(p for p in result["daily"] if p["day"] == "2026-10-08")["return_pct"] == 20
    with pytest.raises(ValueError, match="unavailable strategy"):
        compare_paper_strategies(comparison, ["A", "retired"])
    with pytest.raises(ValueError, match="unavailable strategy"):
        compare_paper_strategies(comparison, ["unknown"])
    empty = compare_paper_strategies(comparison, [])
    assert empty["snapshot"]["equity_usd"] is None and empty["daily"] == []
    comparison["strategies"].append(dict(choices["B"], id="latest-only", start_day=None, points=[]))
    latest_only = compare_paper_strategies(comparison, ["latest-only"])
    assert latest_only["snapshot"]["pnl_usd"] == -10000
    assert latest_only["daily"] == []
    json.dumps(comparison, allow_nan=False)


@pytest.fixture
def f1_sources(monkeypatch):
    baseline = dict(day="2026-10-05", at="2026-10-06T00:00:00Z", equity_usd="103.8")
    activities = [
        dict(
            id="probe-fee",
            activity_type="FEE",
            status="executed",
            date="2026-10-05",
            created_at="2026-10-06T00:16:00Z",
            net_amount="-0.2",
        ),
        dict(
            id="income", activity_type="DIV", status="executed", date="2026-10-06", net_amount="2"
        ),
        dict(
            id="deposit", activity_type="CSD", status="executed", date="2026-10-07", net_amount="50"
        ),
    ]
    account = dict(
        id="account/quant1/broker-daily",
        kind="account",
        activity_coverage_complete=True,
        order_ownership=dict(
            complete_order_interval=True,
            filled_orders_without_original_strategy_or_probe_receipt=[],
            probe_remaining_quantities={},
            first_native_strategy_FILL_at="2026-10-06T14:00:00Z",
            probe_executions=[dict(time="2026-10-05T19:00:00Z")],
            last_account_observation_before_first_native_FILL=baseline,
        ),
        external_flows=[dict(id="deposit", day="2026-10-07", amount_usd="50")],
        points=[
            dict(day=day, at=at, equity_usd=equity, account_return_pct=9999)
            for day, at, equity in (
                ("2026-10-06", "2026-10-07T00:00:00Z", "115.8"),
                ("2026-10-07", "2026-10-08T00:00:00Z", "165.8"),
                ("2026-10-08", "2026-10-09T00:00:00Z", None),
                ("2026-10-09", "2026-10-10T00:00:00Z", "169.8"),
            )
        ],
    )
    history = dict(
        available=True,
        through_session="2026-10-09",
        histories=[account],
        recovery_summary={
            "F1": {"nontrade_signed_amounts_by_type": {"FEE": "-0.2", "DIV": "2", "CSD": "50"}}
        },
    )
    overview = dict(F1_observed_adopted_baseline=baseline, pool_starts={"F1": "2026-10-06"})
    dashboard = dict(
        snapshot_at="2026-10-10T04:00:00Z",
        rows=[
            dict(
                id="F1",
                label="F1",
                href="/paper/ledger/F1",
                first_day="2026-10-06",
                capital_usd=153.8,
                return_pct=14 / 153.8 * 100,
            )
        ],
    )
    monkeypatch.setattr(module, "_f1_activities", lambda root, history, account: activities)
    return history, overview, dashboard


def test_f1_daily_subtracts_only_dated_cash_and_does_not_subtract_adopted_probe_twice(
    f1_sources, tmp_path
):
    history, overview, dashboard = f1_sources
    output = build_paper_comparison(history, overview, dashboard, root=tmp_path)
    strategy = output["strategies"][0]
    points = {p["day"]: p for p in strategy["points"]}
    assert points["2026-10-06"]["return_pct"] == pytest.approx(10 / 103.8 * 100)
    assert points["2026-10-07"]["return_pct"] == pytest.approx(10 / 153.8 * 100)
    assert points["2026-10-08"]["return_pct"] is None
    assert points["2026-10-09"]["return_pct"] == pytest.approx(14 / 153.8 * 100)
    assert strategy["history_basis"] == "broker_daily_ex_posted_cash"
    assert strategy["history_status"] == "partial"
    assert strategy["selectable"] and strategy["default_selected"]


def test_f1_unsupported_probe_or_missing_evidence_keeps_latest_but_withholds_history(
    f1_sources, tmp_path
):
    history, overview, dashboard = f1_sources
    no_sources = build_paper_comparison(history, overview, dashboard)
    assert no_sources["strategies"][0]["latest_return_pct"] == pytest.approx(14 / 153.8 * 100)
    assert no_sources["strategies"][0]["history_status"] == "unavailable"
    history["histories"][0]["order_ownership"]["probe_remaining_quantities"] = {"SPY": "1"}
    result = build_paper_comparison(history, overview, dashboard, root=tmp_path)
    assert all(p["return_pct"] is None for p in result["strategies"][0]["points"])


@pytest.fixture(scope="module")
def actual():
    from open_composer.cockpit.data.paper_dashboard import build_paper_dashboard
    from open_composer.cockpit.data.paper_history import load_paper_history
    from open_composer.cockpit.data.paper_overview import load_paper_overview

    root = Path(os.environ.get("OPEN_COMPOSER_ROOT", Path(__file__).parents[1]))
    history, overview = load_paper_history(root), load_paper_overview(root)
    if not history.get("available") or not overview.get("available"):
        pytest.skip("published owner accounting evidence not present in sample checkout")
    return root, history, overview, build_paper_dashboard(overview)


def test_actual_eleven_equal_choices_and_f1_cash_reconciliation(actual):
    root, history, overview, dashboard = actual
    result = build_paper_comparison(history, overview, dashboard, root=root)
    assert len(result["strategies"]) == 12
    assert sum(s["default_selected"] for s in result["strategies"]) == 11
    f1 = next(s for s in result["strategies"] if s["id"] == "F1")
    points = {p["day"]: p for p in f1["points"]}
    assert points["2026-10-23"]["return_pct"] == pytest.approx(17793.82 / 1000004.45 * 100)
    assert points["2026-10-26"]["return_pct"] is None
    assert points["2026-10-06"]["state"] == "not_started"
    aggregate = compare_paper_strategies(result)
    assert aggregate["snapshot"]["equity_usd"] == pytest.approx(99437.46718663105)
    assert aggregate["daily"][-1]["equity_usd"] is None
    assert aggregate["daily"][-1]["missing"] == ["F1"]


def test_changed_f1_binding_never_becomes_an_account_return_fallback(actual):
    root, history, overview, dashboard = actual
    history = copy.deepcopy(history)
    binding = next(b for b in history["source_bindings"] if b["path"].endswith("/accounts/F1.json"))
    binding["sha256"] = "0" * 64
    result = build_paper_comparison(history, overview, dashboard, root=root)
    f1 = next(s for s in result["strategies"] if s["id"] == "F1")
    assert f1["history_status"] == "unavailable"
    assert f1["latest_return_pct"] == pytest.approx(2.4824850529415143)
    assert all(p["return_pct"] is None for p in f1["points"] if p["state"] != "not_started")
