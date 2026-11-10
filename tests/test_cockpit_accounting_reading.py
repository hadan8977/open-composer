"""Financial display boundaries: capital, observations and matching sessions."""

import json
from datetime import UTC, date, datetime

from open_composer.cockpit.data.paper import (
    account_equity_reading,
    build_account_equity_history,
)
from open_composer.cockpit.data.paper_trials import _trial


def test_account_change_is_not_claimed_as_profit_and_missing_sessions_remain(tmp_path):
    directory = tmp_path / "reports/paper/rehearsal"
    directory.mkdir(parents=True)
    for filename, at, equity in [
        ("x-2026-10-20-235000.json", "2026-10-20T23:50:00Z", 100000),
        ("x-2026-10-26-235000.json", "2026-10-23T23:50:00Z", 110000),
    ]:
        (directory / filename).write_text(json.dumps({"generated_at": at, "equity": equity}))
    # A million-dollar independent account must not enter the legacy chart.
    other = tmp_path / "reports/paper/book/quant1/daily"
    other.mkdir(parents=True)
    (other / "2026-10-23.json").write_text(json.dumps({"pnl": {"equity": 1020000}}))
    history = build_account_equity_history(tmp_path, strategy_names=("x",))
    reading = account_equity_reading(history, now=datetime(2026, 10, 27, 2, tzinfo=UTC))
    assert history.latest.equity == 110000
    assert reading["change_usd"] == 10000 and reading["change_pct"] == 10
    assert reading["net_pnl_usd"] is None  # even an injection looks like equity change
    assert reading["missing_sessions"] == (
        date(2026, 10, 21),
        date(2026, 10, 22),
        date(2026, 10, 26),
    )
    assert reading["market_as_of"] == date(2026, 10, 23)
    assert [day.point for day in history.days][1:3] == [None, None]


def test_received_marks_have_no_invented_market_date_or_net_profit(tmp_path):
    path = tmp_path / "reports/paper/validation/BASE.json"
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "task_id": "BASE",
                "mode": "paper",
                "status": "starting",
                "observed_at_utc": "2026-10-27T02:00:00Z",
                "capital_usd": 10000,
                "net_pnl_status": "unknown",
            }
        )
    )
    component = {
        "allocated_capital_usd": 20000,
        "initial_allocation_usd": 10000,
        "internal_allocation_flows_usd": 10000,
        "trading_PnL_before_unverified_items_usd": -100,
        "tracking_return_on_assigned_capital_pct": -0.5,
    }
    row = _trial(
        tmp_path,
        {"task_id": "BASE", "policy": "BASE", "snapshot": str(path.relative_to(tmp_path))},
        datetime(2026, 10, 27, 2, tzinfo=UTC),
        (
            {},
            {
                "sleeves": {"BASE": component},
                "shared_account_context": {"equity": 999900},
                "broker_account_observed_at": "2026-10-27T01:59:00Z",
                "executions": {"BASE": [{"time": "2026-10-20T13:00:00Z"}]},
            },
            "",
        ),
    )
    assert row.capital_usd == 20000
    assert row.initial_capital_usd + row.allocation_flows_usd == row.capital_usd
    assert row.component_pnl_usd == -100 and row.component_return_on_capital_pct == -0.5
    assert row.net_pnl_usd is None and row.market_as_of is None
    assert row.component_start_at == datetime(2026, 10, 20, 13, tzinfo=UTC)


def test_api_preserves_account_reading_and_account_page_owns_legacy_chart(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from open_composer.cockpit import api, app

    rehearsal = tmp_path / "reports/paper/rehearsal"
    rehearsal.mkdir(parents=True)
    (rehearsal / "x-authorization.json").write_text("{}")
    (rehearsal / "x-2026-10-20-235000.json").write_text(
        json.dumps({"equity": 100000, "generated_at": "2026-10-20T23:50:00Z"})
    )
    (tmp_path / "reports/paper/account.json").write_text(
        json.dumps({"equity": 100500, "generated_at": "2026-10-23T23:50:00Z"})
    )
    monkeypatch.setattr(api, "project_root", lambda: tmp_path)
    monkeypatch.setattr(app, "project_root", lambda: tmp_path)
    client = TestClient(app.create_app(warm=False))
    response = client.get("/api/paper.json")
    assert response.status_code == 200
    reading = response.json()["account_equity"]
    assert reading["history"]["latest"]["equity"] == 100500
    assert reading["change_usd"] == 500 and reading["net_pnl_usd"] is None
    assert reading["missing_sessions"][:2] == ["2026-10-21", "2026-10-22"]
    strategy_page = client.get("/paper")
    assert strategy_page.status_code == 200
    assert 'href="/paper/accounts"' in strategy_page.text
    assert "ETF 账户权益" not in strategy_page.text
    account_page = client.get("/paper/accounts")
    assert account_page.status_code == 200
    assert "ETF 账户权益" in account_page.text
    assert "$100,500<small>.00</small>" in account_page.text
    assert "is-gap" in account_page.text and "no snapshot" in account_page.text
    assert 'href="/paper/history"' in account_page.text


def test_history_route_keeps_dated_values_and_missing_sessions_accessible(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from open_composer.cockpit import app

    history = {
        "available": True,
        "through_session": "2026-10-26",
        "histories": [
            {
                "id": "legacy/historical_sleeve",
                "label": "Historical sleeve",
                "kind": "trading_component",
                "chart": None,
                "latest": {"day": "2026-10-23", "trading_pnl_usd": 25},
                "points": [
                    {
                        "day": "2026-10-23",
                        "capital_usd": 15000,
                        "trading_pnl_usd": 25,
                        "missing": [],
                    },
                    {
                        "day": "2026-10-26",
                        "capital_usd": 15000,
                        "trading_pnl_usd": None,
                        "missing": ["missing market valuation"],
                    },
                ],
            }
        ],
    }
    monkeypatch.setattr(app, "project_root", lambda: tmp_path)
    monkeypatch.setattr(app, "load_paper_history", lambda root: history)
    client = TestClient(app.create_app(warm=False))
    response = client.get("/paper/history")
    assert response.status_code == 200
    assert "Historical sleeve" in response.text
    assert "2026-10-23" in response.text and "2026-10-26" in response.text
    assert "$25.00" in response.text and "缺少估值" in response.text
    assert 'href="/paper/history" aria-current="page"' in response.text
    # The home strategy table links to a separate history view instead of
    # duplicating every dated valuation under one collapsed mega-section.
    strategy_page = client.get("/paper")
    assert strategy_page.status_code == 200
    assert "Historical sleeve" not in strategy_page.text
    assert 'href="/paper/history"' in strategy_page.text
