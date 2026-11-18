"""History must preserve identity, raw units, cash flows and genuine gaps."""

import hashlib
import json
from datetime import date
from decimal import Decimal as D

import pytest

from open_composer.cockpit.data.paper_history import load_paper_history
from scripts.reconcile_paper_history import (
    NY26_UNSUPPORTED_TAILS,
    aggregate_parent,
    historical_book,
    legacy_executions,
    portfolio_points,
    quarantine_reviewed_NY26_tail,
    raw_sources,
    receive_activities,
    receive_full_fills,
    recovered_account_reconciliation,
)


def execution(day, quantity=2, price=100):
    return dict(
        id="buy",
        symbol="XYZ",
        side="buy",
        quantity=D(quantity),
        price=D(price),
        time=day + "T14:00:00Z",
        basis="saved_broker_FILL",
    )


def test_cumulative_order_rows_are_not_added_to_each_other(tmp_path):
    path = tmp_path / "fills.jsonl"
    rows = [
        dict(
            broker_order_id="one",
            session="2026-10-20",
            symbol="XYZ",
            side="buy",
            filled_qty=q,
            filled_avg_price=10,
            filled_at="2026-10-20 14:00:00",
        )
        for q in (2, 5, 5, 0)
    ]
    path.write_text("\n".join(json.dumps(row) for row in rows))
    events, conflicts = legacy_executions(path, {})
    assert len(events) == 1 and events[0]["quantity"] == 5 and conflicts == []


def test_actual_partial_fills_replace_the_average_summary_exactly_once():
    event = dict(order_id="order", symbol="XYZ", side="buy", quantity=D(3), price=D(10))
    rows = [
        dict(
            activity_type="FILL",
            id=str(i),
            order_id="order",
            symbol="XYZ",
            side="buy",
            qty=q,
            price=p,
            transaction_time="2026-10-20T14:00:00Z",
        )
        for i, q, p in [(1, "1", "9.9"), (2, "2", "10.1")]
    ]
    received = receive_full_fills([event], rows)
    assert len(received) == 2
    assert sum(x["quantity"] * x["price"] for x in received) == D("30.1")
    with pytest.raises(ValueError, match="cumulative quantity"):
        receive_full_fills([event], rows[:1])


def test_account_reconciliation_preserves_short_positions_and_unallocated_income():
    received = dict(
        account_hash="identity",
        positions_observed_at="2026-10-20T20:00:01Z",
        portfolio_base_value="100000",
        activity_coverage_complete=True,
        current_account=dict(
            cash="101002",
            equity="100052",
            created_at="2026-10-19T00:00:00Z",
            observed_at="2026-10-20T20:00:00Z",
        ),
        positions=[dict(symbol="XYZ", qty="-10", market_value="-950")],
        activities=[
            dict(activity_type="FILL", id="sell", side="sell", symbol="XYZ", qty="10", price="100"),
            dict(activity_type="DIV", id="div", net_amount="2", status="executed"),
            dict(activity_type="CSD", id="pending", net_amount="10000", status="pending"),
        ],
    )
    result = recovered_account_reconciliation(received)
    assert result["quantity_mismatches"] == {}
    assert result["account_equity_identity_residual_usd"] == 0
    assert result["implied_opening_cash_usd"] == 100000
    assert result["nontrade_signed_cash_change_usd"] == 2
    assert result["nontrade_unverified_cash_effect"][0]["id"] == "pending"


def test_actual_MA_units_and_cash_are_separate_and_not_duplicate_fills():
    received = dict(
        account_hash="identity",
        positions_observed_at="2026-10-21T20:00:01Z",
        portfolio_base_value=100000,
        activity_coverage_complete=True,
        positions=[],
        current_account=dict(
            cash="99950",
            equity="99950",
            created_at="2026-10-19T00:00:00Z",
            observed_at="2026-10-21T20:00:00Z",
        ),
        activities=[
            dict(
                activity_type="FILL", id="short", side="sell", symbol="XYZ", qty="10", price="100"
            ),
            dict(
                activity_type="MA",
                id="units",
                status="executed",
                symbol="XYZ",
                qty="10",
                price="101",
                net_amount="0",
            ),
            dict(
                activity_type="MA", id="cash", status="executed", symbol="XYZ", net_amount="-1050"
            ),
        ],
    )
    result = recovered_account_reconciliation(received)
    assert result["quantity_mismatches"] == {}
    assert result["quantity_mismatches_before_recorded_MA"]["XYZ"]["signed_fills"] == -10
    assert result["implied_opening_cash_usd"] == 100000
    assert result["fill_principal_cash_change_usd"] == 1000
    assert result["nontrade_signed_cash_change_usd"] == -1050


def test_broker_daily_midnight_UTC_is_previous_NY_trading_day():
    from datetime import UTC, datetime

    ticks = [
        int(datetime(2026, 10, 23, tzinfo=UTC).timestamp()),
        int(datetime(2026, 10, 24, tzinfo=UTC).timestamp()),
    ]
    rows = portfolio_points(
        dict(timestamp=ticks, equity=[104110.8, 104279.14]),
        dict(body=dict(path="raw"), received_at="2026-10-27T04:20:00Z"),
        "identity",
        date(2026, 10, 26),
    )
    assert [r["day"] for r in rows] == ["2026-10-22", "2026-10-23"]
    assert rows[-1]["at"].startswith("2026-10-24T00:00:00")
    assert all(r["day"] != "2026-10-26" for r in rows)


def test_exact_reviewed_source_anomaly_is_a_gap_without_filtering_real_zero_losses():
    raw = dict(
        timestamp=[1793059200],
        equity=[0],
        profit_loss=[-100000],
        profit_loss_pct=[-1],
        base_value=100000,
    )
    point = dict(day="2026-10-26", equity_usd=0, at="2026-10-27T00:00:00Z")
    reviewed = dict(body=dict(sha256=NY26_UNSUPPORTED_TAILS["legacy"]))
    received = quarantine_reviewed_NY26_tail("legacy", raw, reviewed, [point])
    assert received[0]["equity_usd"] is None and received[0]["raw_equity_usd"] == 0
    assert received[0]["separate_tail_base_value_usd"] == 100000
    assert received[0]["missing"]
    genuine_other_source = dict(body=dict(sha256="b" * 64))
    assert (
        quarantine_reviewed_NY26_tail("legacy", raw, genuine_other_source, [point])[0]["equity_usd"]
        == 0
    )
    with pytest.raises(AssertionError):
        quarantine_reviewed_NY26_tail(
            "legacy", {**raw, "timestamp": [1793145600]}, reviewed, [point]
        )


def test_all_type_activity_coverage_requires_closed_intervals_and_exact_cursor(tmp_path):
    index = dict(
        source_interval=["2026-10-19T00:00:00Z", "2026-10-26T23:59:59Z"],
        objects=dict(
            activities=dict(
                complete=True,
                actual_entry_cutoff="2026-10-27T03:00:00Z",
                acquisitions=[
                    dict(
                        complete=True,
                        creation_time_interval=["2026-10-19T00:00:00Z", "2026-10-27T03:00:00Z"],
                        pages=[
                            dict(receipt="one", terminal=False),
                            dict(receipt="two", terminal=True),
                        ],
                    )
                ],
            )
        ),
    )
    receipts = {
        "one": (
            dict(
                request=dict(
                    params=dict(
                        after="2026-10-19T00:00:00Z", until="2026-10-27T03:00:00Z", direction="asc"
                    )
                )
            ),
            [dict(id="one", activity_type="CFEE", net_amount="-0.5")],
        ),
        "two": (
            dict(
                request=dict(
                    params=dict(
                        after="2026-10-19T00:00:00Z",
                        until="2026-10-27T03:00:00Z",
                        direction="asc",
                        page_token="one",
                    )
                )
            ),
            [],
        ),
    }
    for receipt, _ in receipts.values():
        receipt["request"]["endpoint"] = "https://paper-api.alpaca.markets/v2/account/activities"
    rows, complete = receive_activities(
        tmp_path, index, "identity", {}, lambda binding, _: receipts[binding]
    )
    assert complete and len(rows) == 1
    receipts["two"][0]["request"]["params"]["page_token"] = "wrong"
    with pytest.raises(ValueError, match="cursor mismatch"):
        receive_activities(tmp_path, index, "identity", {}, lambda binding, _: receipts[binding])


def test_allocation_is_not_profit_and_missing_price_is_not_carried():
    day = date(2026, 10, 20)
    prices = {("XYZ", day): dict(price=D(110))}
    result = historical_book(
        "BASE",
        "BASE",
        [execution(str(day))],
        D(10000),
        [dict(amount_USD="10000", observed_at="2026-10-20T13:00:00Z")],
        prices,
        date(2026, 10, 21),
    )
    first, missing = result["points"]
    assert first["capital_usd"] == 20000 and first["trading_pnl_usd"] == 20
    assert first["tracking_return_pct"] == D("0.1")
    assert first["net_pnl_usd"] is None
    assert missing["trading_pnl_usd"] is None and missing["holdings_value_usd"] is None
    assert missing["missing"]


def test_adjusted_prices_cannot_value_raw_executed_shares(tmp_path):
    source = tmp_path / "reports/research/program/paper-launch-20min-20261021/source"
    source.mkdir(parents=True)
    for kind, adjustment, close in (("adjusted", "all", 50), ("actual", "raw", 100)):
        (source / (kind + ".json")).write_text(
            json.dumps(
                dict(
                    status_code=200,
                    params=dict(adjustment=adjustment, timeframe="1Day"),
                    received_at="2026-10-21T01:00:00Z",
                )
            )
        )
        (source / (kind + ".raw")).write_text(
            json.dumps(dict(bars={"XYZ": [dict(t="2026-10-20T04:00:00Z", c=close)]}))
        )
    prices, _, _ = raw_sources(tmp_path, {})
    assert prices[("XYZ", date(2026, 10, 20))]["price"] == 100
    result = historical_book(
        "x", "x", [execution("2026-10-20")], D(1000), [], prices, date(2026, 10, 20)
    )
    assert result["points"][0]["holdings_value_usd"] == 200


def test_held_split_without_unit_bridge_is_a_gap_not_invented_quantity():
    prices = {("XYZ", date(2026, 10, 21)): dict(price=D(50))}
    action = dict(symbol="XYZ", day="2026-10-21", kind="forward_splits")
    row = historical_book(
        "x", "x", [execution("2026-10-20")], D(1000), [], prices, date(2026, 10, 21), [action]
    )
    assert row["points"][-1]["trading_pnl_usd"] is None
    assert "unit/basis bridge" in row["points"][-1]["missing"][-1]


def test_composite_requires_same_day_children_and_counts_each_once():
    def child(identity, day, capital):
        return dict(
            id=identity,
            points=[
                dict(
                    day=day,
                    capital_usd=D(capital),
                    cash_from_principal_usd=D(capital) - 100,
                    holdings_value_usd=D(120),
                    nav_before_unverified_items_usd=D(capital) + 20,
                    trading_pnl_usd=D(20),
                    missing=[],
                )
            ],
        )

    a, b = child("a", "2026-10-20", "10000"), child("b", "2026-10-21", "10000")
    parent = aggregate_parent("parent", ["a", "b"], [a, b])
    assert all(p["trading_pnl_usd"] is None for p in parent["points"])
    b = child("b", "2026-10-20", "10000")
    parent = aggregate_parent("parent", ["a", "b"], [a, b])
    assert parent["points"][0]["capital_usd"] == 20000
    assert parent["points"][0]["trading_pnl_usd"] == 40


def test_original_account_observations_keep_gaps_and_later_planless_valuation(tmp_path):
    artifact = tmp_path / "reports/paper/history/derived.json"
    artifact.parent.mkdir(parents=True)
    artifact.write_text(
        json.dumps(
            dict(
                schema_version=1,
                through_session="2026-10-26",
                histories=[
                    dict(
                        id="account/quant1",
                        kind="account",
                        label="quant1",
                        order_ownership=dict(probe_realized_trading_pnl_before_fees_usd="4.49"),
                        points=[
                            dict(
                                day="2026-10-20",
                                at="2026-10-20T23:30:00Z",
                                equity_usd=1020246.18,
                                valuation="original_account_observation_without_strategy_plan",
                            )
                        ],
                    )
                ],
            )
        )
    )
    config = tmp_path / "config/paper-history-dashboard.json"
    config.parent.mkdir()
    config.write_text(
        json.dumps(
            dict(
                path="reports/paper/history/derived.json",
                sha256=hashlib.sha256(artifact.read_bytes()).hexdigest(),
            )
        )
    )
    reading = load_paper_history(tmp_path)
    row = reading["histories"][0]
    assert row["order_ownership"]["probe_realized_trading_pnl_before_fees_usd"] == 4.49
    assert row["latest"]["day"] == "2026-10-20" and row["latest"]["equity_usd"] == 1020246.18
    assert [p["day"] for p in row["points"] if p["equity_usd"] is None] == [
        "2026-10-21",
        "2026-10-22",
        "2026-10-23",
        "2026-10-26",
    ]
    artifact.write_text(artifact.read_text() + " ")
    assert not load_paper_history(tmp_path)["available"]


def test_existing_sleeve_card_uses_published_raw_marks_and_never_adjusted_fallback(
    tmp_path, monkeypatch
):
    from open_composer.cockpit.data.paper import build_sleeve_performance

    spec = tmp_path / "strategy_specs/drafts/owned.yaml"
    spec.parent.mkdir(parents=True)
    spec.write_text("notional_budget_usd: 15000\n")
    fills = tmp_path / "reports/paper/rehearsal/owned-fills.jsonl"
    fills.parent.mkdir(parents=True)
    fills.write_text(
        json.dumps(
            dict(
                broker_order_id="one",
                symbol="XYZ",
                side="buy",
                filled_qty=1,
                filled_avg_price=100,
                session="2026-10-20",
            )
        )
    )
    artifact = tmp_path / "reports/paper/rebuilt.json"
    artifact.write_text(
        json.dumps(
            dict(
                schema_version=1,
                through_session="2026-10-22",
                histories=[
                    dict(
                        id="legacy/owned",
                        kind="trading_component",
                        label="owned",
                        points=[
                            dict(day=day, nav_before_unverified_items_usd=value)
                            for day, value in [
                                ("2026-10-20", 15100),
                                ("2026-10-21", None),
                                ("2026-10-22", 14950),
                            ]
                        ],
                    )
                ],
            )
        )
    )
    config = tmp_path / "config/paper-history-dashboard.json"
    config.parent.mkdir()
    config.write_text(
        json.dumps(
            dict(
                path="reports/paper/rebuilt.json",
                sha256=hashlib.sha256(artifact.read_bytes()).hexdigest(),
            )
        )
    )

    def adjusted_archive_forbidden(*args):
        raise AssertionError("adjusted research marks must not re-enter the corrected sleeve")

    monkeypatch.setattr(
        "open_composer.cockpit.data.paper.load_session_prices", adjusted_archive_forbidden
    )
    result = build_sleeve_performance(tmp_path, "owned")
    assert result.nav == 14950 and abs(result.return_pct - (-50 / 15000 * 100)) < 1e-12
    assert result.history.days[1].point is None
    artifact.write_text(artifact.read_text() + " ")
    assert build_sleeve_performance(tmp_path, "owned").nav is None


def test_external_deposit_is_removed_and_return_uses_named_flow_timing():
    from open_composer.cockpit.data.paper_history import account_performance

    points = [
        dict(day="2026-10-20", at="2026-10-20T20:00:00Z", equity_usd=100000),
        dict(day="2026-10-22", at="2026-10-22T20:00:00Z", equity_usd=111000),
    ]
    flow = dict(day="2026-10-21", at="2026-10-21T20:00:00Z", amount_usd=10000)
    result = account_performance(points, [flow], flow_coverage_complete=True)
    assert result["net_change_ex_external_flows_usd"] == 1000
    assert abs(result["return_pct"] - 1000 / 105000 * 100) < 1e-12
    assert result["return_method"].startswith("Modified Dietz")
    result = account_performance(points, [flow], flow_coverage_complete=False)
    assert result["observation_change_usd"] == 11000 and result["return_pct"] is None
    assert result["net_change_ex_external_flows_usd"] is None


def test_unfunded_zero_prefix_cannot_turn_million_virtual_cash_into_profit():
    from open_composer.cockpit.data.paper_history import account_performance

    points = [
        dict(day="2026-10-19", at="2026-10-19T20:00:00Z", equity_usd=0),
        dict(day="2026-10-20", at="2026-10-20T20:00:00Z", equity_usd=1000000),
        dict(day="2026-10-21", at="2026-10-21T20:00:00Z", equity_usd=1000100),
    ]
    result = account_performance(points, [], flow_coverage_complete=True)
    assert result["net_change_ex_external_flows_usd"] == 100
    assert result["return_pct"] == 0.01


def test_date_only_transfer_at_closing_boundary_does_not_certify_profit():
    from open_composer.cockpit.data.paper_history import account_performance

    points = [
        dict(day="2026-10-20", at="2026-10-20T20:00:00Z", equity_usd=100000),
        dict(day="2026-10-21", at="2026-10-21T20:00:00Z", equity_usd=110100),
    ]
    result = account_performance(
        points, [dict(day="2026-10-21", amount_usd=10000)], flow_coverage_complete=True
    )
    assert result["observation_change_usd"] == 10100
    assert result["net_change_ex_external_flows_usd"] is None
    assert result["return_pct"] is None


@pytest.mark.parametrize(
    "received_identity,expected_missing", [("a" * 64, []), ("b" * 64, ["2026-10-21", "2026-10-22"])]
)
def test_only_bound_original_account_history_restores_its_gaps(
    tmp_path, received_identity, expected_missing
):
    from datetime import UTC, datetime

    from open_composer.cockpit.data.paper import (
        account_equity_reading,
        build_account_equity_history,
    )

    rehearsal = tmp_path / "reports/paper/rehearsal"
    rehearsal.mkdir(parents=True)
    (rehearsal / "x-2026-10-20-235000.json").write_text(
        json.dumps(dict(generated_at="2026-10-20T23:50:00Z", equity=100000))
    )
    (tmp_path / "reports/paper/account.json").write_text(
        json.dumps(
            dict(
                generated_at="2026-10-23T23:50:00Z", equity=100500, broker_account_id_hash="a" * 64
            )
        )
    )
    artifact = tmp_path / "reports/paper/history/derived.json"
    artifact.parent.mkdir()
    artifact.write_text(
        json.dumps(
            dict(
                schema_version=1,
                through_session="2026-10-23",
                histories=[
                    dict(
                        id="account/legacy/broker-daily",
                        label="Legacy broker",
                        kind="account",
                        account_hash=received_identity,
                        points=[
                            dict(
                                day=day,
                                at=day + "T20:00:00Z",
                                equity_usd=value,
                                valuation="recovered_broker_1D_account_equity",
                            )
                            for day, value in [("2026-10-21", 100100), ("2026-10-22", 100200)]
                        ],
                    )
                ],
            )
        )
    )
    config = tmp_path / "config/paper-history-dashboard.json"
    config.parent.mkdir()
    config.write_text(
        json.dumps(
            dict(
                path="reports/paper/history/derived.json",
                sha256=hashlib.sha256(artifact.read_bytes()).hexdigest(),
            )
        )
    )
    history = build_account_equity_history(tmp_path, strategy_names=("x",))
    reading = account_equity_reading(history, now=datetime(2026, 10, 24, 2, tzinfo=UTC))
    assert [str(day) for day in reading["missing_sessions"]] == expected_missing
    assert history.latest.equity == 100500 and reading["net_pnl_usd"] is None
    if received_identity == "a" * 64:
        assert [str(day) for day in reading["recovered_sessions"]] == ["2026-10-21", "2026-10-22"]
