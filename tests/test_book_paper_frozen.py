"""T-20261002-40: held names that stopped trading are frozen, not plan blockers (fake client)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from test_book_paper import (
    EXECUTION,
    NOW,
    FakeClient,
    all_etb_client,
    etb,
    failed_checks,
    make_target,
    plan_for,
)

from open_composer.book_paper.plan import (
    AccountState,
    AssetInfo,
    RiskLimits,
    build_plan,
    make_asset_lookup,
    read_account_state,
)
from open_composer.book_paper.targets import NameExposure, seal_target

HELD_AT_TARGET = (
    {f"L{i}": 200 for i in range(1, 6)} | {f"S{i}": -200 for i in range(1, 6)} | {"SGOV": 10_000}
)


def lookup_from(assets: dict[str, AssetInfo | None]):
    return lambda symbol: assets.get(symbol, etb_info(symbol))


DEAD = AssetInfo("ACQ", easy_to_borrow=False, shortable=False, tradable=False, status="inactive")
LIVE = AssetInfo("OLD", easy_to_borrow=False, shortable=False, tradable=True, status="active")


def plan_with(
    extra_positions: dict[str, float],
    extra_prices: dict[str, float | None],
    assets: dict[str, AssetInfo | None],
    *,
    target=None,
    **kw,
):
    target = target or make_target()
    held = HELD_AT_TARGET | extra_positions
    prices = {s: 50.0 if s != "SGOV" else 100.0 for s in HELD_AT_TARGET}
    prices.update({s: p for s, p in extra_prices.items() if p is not None})
    state = AccountState(equity=1_000_000.0, positions=held, position_prices=prices)
    args = {
        "as_of": EXECUTION,
        "now": NOW,
        "asset_lookup": lookup_from(assets),
        "kill_switch_check": None,
    }
    args.update(kw)
    return build_plan(target, state, **args)


def check(plan, name: str) -> dict:
    return next(c for c in plan.payload["checks"] if c["name"] == name)


def test_frozen_long_and_short_under_limit_make_no_order_and_pass() -> None:
    plan = plan_with(
        {"ACQ": 100, "GONE": -100},
        {"ACQ": 40.0, "GONE": 30.0},
        {"ACQ": DEAD, "GONE": None},
    )
    assert plan.status == "ok", plan.payload["blocked_by"]
    assert plan.orders == []
    frozen = {row["symbol"]: row for row in plan.payload["frozen"]}
    assert frozen["ACQ"]["reason"] == "asset_not_active"
    assert frozen["GONE"]["reason"] == "asset_not_found"
    assert frozen["ACQ"]["value"] == 4000.0 and frozen["GONE"]["value"] == 3000.0
    assert plan.payload["post_trade_qty"]["ACQ"] == 100
    assert plan.payload["post_trade_qty"]["GONE"] == -100


def test_large_or_unvalued_frozen_name_leaves_other_orders_available() -> None:
    for price in (40.0, None):
        plan = plan_with({"ACQ": 1000}, {"ACQ": price}, {"ACQ": DEAD})
        assert plan.status == "ok"
        assert plan.payload["post_trade_qty"]["ACQ"] == 1000
        assert plan.payload["frozen"][0]["price"] == price


def test_tradable_held_name_with_target_zero_gets_full_closeout_at_broker_price() -> None:
    plan = plan_with({"OLD": 300}, {"OLD": 25.0}, {"OLD": LIVE})
    assert plan.status == "ok", plan.payload["blocked_by"]
    (order,) = plan.orders
    assert order["symbol"] == "OLD" and order["side"] == "sell" and order["qty"] == 300
    assert order["reference_price"] == 25.0 and order["notional"] == 7500.0
    assert order["reference_price_source"] == "broker_position"
    assert order["time_in_force"] == "cls" and order["opens_or_increases_short"] is False
    assert order["post_qty"] == 0
    assert "frozen" not in plan.payload
    assert "OLD" not in plan.payload["post_trade_qty"]


def test_closeout_of_a_short_is_a_buy_to_cover_that_skips_the_borrow_rule() -> None:
    plan = plan_with({"OLD": -300}, {"OLD": 25.0}, {"OLD": LIVE})  # not shortable, not ETB
    (order,) = plan.orders
    assert order["side"] == "buy" and order["qty"] == 300
    assert plan.payload["etb_rejections"] == []
    assert plan.status == "ok", plan.payload["blocked_by"]


def test_closeout_under_minimum_notional_is_dropped_like_any_other() -> None:
    plan = plan_with({"OLD": 3}, {"OLD": 20.0}, {"OLD": LIVE})  # $60
    assert plan.orders == []
    assert plan.payload["dropped_min_notional"] == [
        {"symbol": "OLD", "delta": -3, "notional": 60.0}
    ]
    assert plan.status == "ok", plan.payload["blocked_by"]
    assert plan.payload["post_trade_qty"]["OLD"] == 3


def test_closeout_without_broker_price_is_frozen() -> None:
    plan = plan_with({"OLD": 300}, {"OLD": None}, {"OLD": LIVE})
    assert not failed_checks(plan)
    assert plan.payload["frozen"][0]["reason"] == "missing_reference_price"
    assert plan.orders == []


def test_explicit_unit_freeze_preserves_held_shares_even_with_a_reference_price() -> None:
    target = make_target(frozen_symbols={"L1": "unexplained_execution_units"})
    plan = plan_with({"L1": 5.0, "L2": 10.0}, {}, {}, target=target)
    assert not failed_checks(plan)
    assert plan.payload["post_trade_qty"]["L1"] == 5
    assert plan.payload["frozen"][0]["reason"] == "unexplained_execution_units"
    assert {o["symbol"] for o in plan.orders} == {"L2"}


def test_frozen_names_are_excluded_from_overlay_checks_but_count_in_gross_leverage() -> None:
    base = plan_with({}, {}, {})
    # 375 sh x $40 = 1.5% of the basis: above max_name_weight 1.25%, long-only drift in net
    frozen = plan_with({"ACQ": 375}, {"ACQ": 40.0}, {"ACQ": DEAD})
    assert frozen.status == "ok", frozen.payload["blocked_by"]
    for name in ("net_dollar", "gross_stock", "max_name_weight", "beta_neutral"):
        assert check(frozen, name)["value"] == check(base, name)["value"], name
        assert check(frozen, name)["passed"]
    assert check(frozen, "gross_leverage")["value"] == pytest.approx(
        check(base, "gross_leverage")["value"] + 0.015
    )
    assert "frozen_positions" not in {c["name"] for c in base.payload["checks"]}
    summary = frozen.payload["summary"]
    assert (
        summary["post_trade_long_notional"] == base.payload["summary"]["post_trade_long_notional"]
    )


def test_frozen_gross_pushes_gross_leverage_over_its_limit() -> None:
    limits = RiskLimits(max_gross_leverage=1.115)  # base leverage is 1.1
    ok = plan_with({"ACQ": 300}, {"ACQ": 40.0}, {"ACQ": DEAD}, limits=limits)  # +0.012
    over = plan_with({"ACQ": 500}, {"ACQ": 40.0}, {"ACQ": DEAD}, limits=limits)  # +0.020
    assert check(ok, "gross_leverage")["passed"]
    assert not check(over, "gross_leverage")["passed"]


def test_frozen_name_with_fractional_quantity_is_only_frozen() -> None:
    plan = plan_with({"ACQ": 12.5}, {"ACQ": 40.0}, {"ACQ": DEAD})
    assert plan.status == "ok" and "fractional_held" not in plan.payload


def test_inactive_status_freezes_even_when_tradable_flag_is_true() -> None:
    odd = AssetInfo("ACQ", easy_to_borrow=True, shortable=True, tradable=True, status="inactive")
    plan = plan_with({"ACQ": 100}, {"ACQ": 40.0}, {"ACQ": odd})
    assert plan.payload["frozen"][0]["reason"] == "asset_not_active"
    assert plan.orders == []


def test_artl_like_name_missing_on_decision_date_but_tradable_is_a_closeout() -> None:
    plan = plan_with({"ARTL": 500}, {"ARTL": 12.0}, {"ARTL": etb_info("ARTL")})
    (order,) = plan.orders
    assert order["symbol"] == "ARTL" and order["side"] == "sell" and order["qty"] == 500
    assert order["reference_price_source"] == "broker_position"
    assert "frozen" not in plan.payload
    assert "frozen_positions" not in {c["name"] for c in plan.payload["checks"]}


def etb_info(symbol: str) -> AssetInfo:
    return AssetInfo(symbol, easy_to_borrow=True, shortable=True, tradable=True, status="active")


class PositionsClient(FakeClient):
    def __init__(self, rows, **kw):
        super().__init__(**kw)
        self.rows = rows

    def get_all_positions(self):
        return self.rows


def test_read_account_state_fills_position_prices_with_market_value_fallback() -> None:
    rows = [
        SimpleNamespace(symbol="A", qty="10", side="long", current_price="12.5"),
        SimpleNamespace(symbol="B", qty="-20", side="short", market_value="-600"),
        SimpleNamespace(symbol="C", qty="5", side="long", current_price=None, market_value="75"),
        SimpleNamespace(symbol="D", qty="5", side="long"),  # neither: skipped
        SimpleNamespace(symbol="E", qty="5", side="long", current_price="0", market_value=None),
    ]
    state = read_account_state(PositionsClient(rows))
    assert state.positions == {"A": 10.0, "B": -20.0, "C": 5.0, "D": 5.0, "E": 5.0}
    assert state.position_prices == {"A": 12.5, "B": 30.0, "C": 15.0}


def test_account_state_position_prices_default_is_empty() -> None:
    assert AccountState(equity=1.0, positions={}).position_prices == {}


def test_end_to_end_with_fake_client_freezes_an_acquired_name() -> None:
    client = PositionsClient(
        [
            SimpleNamespace(symbol=s, qty=str(q), side="short" if q < 0 else "long")
            for s, q in HELD_AT_TARGET.items()
        ]
        + [
            SimpleNamespace(
                symbol="ACQ", qty="100", side="long", current_price="40.0", market_value="4000"
            )
        ],
        assets={s: etb(s) for s in HELD_AT_TARGET} | {"ACQ": etb("ACQ", tradable=False)},
    )
    plan = plan_for(make_target(), client)
    assert plan.status == "ok", plan.payload["blocked_by"]
    assert [row["symbol"] for row in plan.payload["frozen"]] == ["ACQ"]
    assert make_asset_lookup(client)("ACQ").tradable is False


def test_plan_without_frozen_names_has_no_frozen_fields() -> None:
    target = make_target()
    target = seal_target(
        target.model_copy(
            update={
                "reference_prices": {**target.reference_prices, "X9": 25.0},
                "exposures": {**target.exposures, "X9": NameExposure(beta=1, industry="a", size=1)},
            }
        )
    )
    client = all_etb_client(positions={"L1": 150, "S1": -250, "X9": 40})
    client.assets["X9"] = etb("X9")
    held = plan_for(target, client)
    assert "frozen" not in held.payload
    assert all("reference_price_source" not in o for o in held.orders)


def test_reconcile_labels_frozen_names_and_leaves_other_plans_unchanged() -> None:
    from open_composer.book_paper.post_close import reconcile

    target = make_target()
    plan = plan_with({"ACQ": 100}, {"ACQ": 40.0}, {"ACQ": DEAD})
    positions = {s: float(q) for s, q in HELD_AT_TARGET.items()}  # the broker already cashed ACQ
    result = reconcile(plan, target, [], positions, {})
    assert result["frozen_names"] == ["ACQ"]
    (row,) = result["position_drift_vs_plan"]
    assert row["symbol"] == "ACQ" and row["frozen"] is True and row["drift_qty"] == -100
    clean = reconcile(plan_with({}, {}, {}), target, [], positions, {})
    assert "frozen_names" not in clean and clean["position_drift_vs_plan"] == []
