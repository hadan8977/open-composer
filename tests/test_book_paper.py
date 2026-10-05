"""T-20261001-16: short-capable book order engine (dry-run first; fake broker client only)."""

from __future__ import annotations

import json
import re
from datetime import UTC, date, datetime
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import numpy as np
import pytest

from open_composer.adapters.broker.alpaca_paper import (
    _is_verified_paper_client,
    _mark_verified_paper_client,
    _require_kill_switch_clear,
)
from open_composer.book_paper.accounts import (
    BookAccountError,
    credential_variable_names,
    load_account_credentials,
    make_trading_client,
    present_variables,
    require_paper_origin,
)
from open_composer.book_paper.exit_rules import evaluate_exit_rules, rolling_sharpe
from open_composer.book_paper.plan import (
    AccountState,
    BookEngineError,
    OrderLookup,
    OrderPlan,
    RiskLimits,
    broker_error_text,
    build_plan,
    client_order_id,
    freshness_ok,
    load_plan_file,
    make_asset_lookup,
    next_orders_receipt_path,
    orders_receipt_path,
    read_account_state,
    require_submission_window,
    round_half_away,
    submit_plan,
    write_json_atomic,
    write_plan_file,
)
from open_composer.book_paper.post_close import (
    build_daily_record,
    daily_path,
    normalize_broker_order,
    reconcile,
    shadow_costs,
    tca,
    write_daily_file,
)
from open_composer.book_paper.targets import (
    BookTarget,
    BookTargetError,
    NameExposure,
    convert_f1_target_to_f2,
    f1_to_f2_weights,
    load_target_file,
    seal_target,
    target_path,
    write_target_file,
)
from open_composer.paper_controls import set_paper_kill_switch
from open_composer.research.equity_book.costs import half_spread_bp, impact_bp

ET = ZoneInfo("America/New_York")
DECISION = date(2026, 9, 17)
EXECUTION = date(2026, 9, 18)
FAKE_KEY = "PKTESTFAKEKEYID1234"
FAKE_SECRET = "fakeSecretValueZZ9876543210abcdefghijklmn"


# --------------------------------------------------------------------------------------
# fakes and builders
# --------------------------------------------------------------------------------------


class FakeClient:
    """Alpaca-like paper client; records submissions, never touches the network."""

    def __init__(self, *, equity=1_000_000.0, positions=None, assets=None, orders=None):
        self._base_url = "https://paper-api.alpaca.markets"
        self._sandbox = True
        self.equity = equity
        self.positions = positions or {}
        self.assets = assets or {}
        self.orders = list(orders or [])
        self.submitted = []
        _mark_verified_paper_client(self)

    def get_account(self):
        return SimpleNamespace(
            equity=str(self.equity),
            last_equity=str(self.equity),
            buying_power="2000000",
            status="ACTIVE",
            shorting_enabled=True,
            trading_blocked=False,
        )

    def get_all_positions(self):
        return [
            SimpleNamespace(symbol=s, qty=str(q), side="short" if q < 0 else "long")
            for s, q in self.positions.items()
        ]

    def get_orders(self, filter=None):
        status = getattr(filter, "status", None)
        if str(getattr(status, "value", status)).lower() == "open":
            return [o for o in self.orders if o.status in ("new", "accepted")]
        return list(self.orders)

    def get_asset(self, symbol):
        if symbol not in self.assets:
            error = RuntimeError("not found")
            error.status_code = 404
            raise error
        return self.assets[symbol]

    def submit_order(self, request):
        order = SimpleNamespace(
            id=f"id-{len(self.submitted)}",
            client_order_id=request.client_order_id,
            symbol=request.symbol,
            qty=str(request.qty),
            side=request.side,
            time_in_force=request.time_in_force,
            status="accepted",
            filled_qty="0",
            filled_avg_price=None,
        )
        self.submitted.append(request)
        self.orders.append(order)
        return order


def etb(symbol: str, **kw) -> SimpleNamespace:
    base = {"easy_to_borrow": True, "shortable": True, "tradable": True, "status": "active"}
    return SimpleNamespace(symbol=symbol, **{**base, **kw})


NAMES_LONG = ["L1", "L2", "L3", "L4", "L5"]
NAMES_SHORT = ["S1", "S2", "S3", "S4", "S5"]


def make_target(**overrides) -> BookTarget:
    weights = {s: 0.01 for s in NAMES_LONG} | {s: -0.01 for s in NAMES_SHORT} | {"SGOV": 1.0}
    prices = {s: 50.0 for s in NAMES_LONG + NAMES_SHORT} | {"SGOV": 100.0}
    exposures = {
        s: NameExposure(beta=1.0, industry="ind_a", size=9.0, dollar_adv_21=5e7, vol_21=0.02)
        for s in NAMES_LONG + NAMES_SHORT
    } | {"SGOV": NameExposure(beta=0.0, industry="tbill", size=0.0)}
    fields = {
        "book_id": "t20261001_book_rf1:RF_M0_A",
        "account": "quant1",
        "form": "F1",
        "decision_date": DECISION,
        "execution_date": EXECUTION,
        "equity_basis": 1_000_000.0,
        "core_symbol": "SGOV",
        "weights": weights,
        "reference_prices": prices,
        "exposures": exposures,
        "logged_at_utc": "2026-09-17T21:00:00Z",
    }
    fields.update(overrides)
    return seal_target(BookTarget(**fields))


def asset_lookup_for(client: FakeClient):
    return make_asset_lookup(client)


def all_etb_client(**kw) -> FakeClient:
    return FakeClient(assets={s: etb(s) for s in NAMES_LONG + NAMES_SHORT + ["SGOV"]}, **kw)


NOW = datetime(2026, 9, 18, 18, 0, tzinfo=UTC)  # 14:00 ET


def plan_for(target=None, client=None, **kw):
    target = target or make_target()
    client = client or all_etb_client()
    state = read_account_state(client)
    args = {
        "as_of": EXECUTION,
        "now": NOW,
        "asset_lookup": make_asset_lookup(client),
        "kill_switch_check": None,
    }
    args.update(kw)
    return build_plan(target, state, **args)


def failed_checks(plan) -> set[str]:
    return {c["name"] for c in plan.payload["checks"] if not c["passed"]}


# --------------------------------------------------------------------------------------
# rounding, minimum notional, plan shape
# --------------------------------------------------------------------------------------


def test_round_half_away_longs_and_shorts() -> None:
    assert [round_half_away(x) for x in (1.5, -1.5, 2.4, -2.4, 0.49, -0.49, 0.0)] == [
        2,
        -2,
        2,
        -2,
        0,
        0,
        0,
    ]


def test_whole_share_orders_and_rounding_drift() -> None:
    # 0.0105 * 1e6 / 50 = 210 sh; -0.0095 * 1e6 / 50 = -190 sh; 0.01 * 1e6 / 33.3 = 300.3 -> 300
    target = make_target(
        weights={"L1": 0.0105, "S1": -0.0095, "L2": 0.01, "S2": -0.01, "SGOV": 1.0},
        reference_prices={"L1": 50.0, "S1": 50.0, "L2": 33.3, "S2": 50.0, "SGOV": 100.0},
        exposures={
            s: NameExposure(beta=1.0, industry="a", size=1.0)
            for s in ("L1", "S1", "L2", "S2", "SGOV")
        },
    )
    client = FakeClient(assets={s: etb(s) for s in ("L1", "S1", "L2", "S2", "SGOV")})
    plan = plan_for(target, client)
    by_symbol = {o["symbol"]: o for o in plan.orders}
    assert by_symbol["L1"]["qty"] == 210 and by_symbol["L1"]["side"] == "buy"
    assert by_symbol["S1"]["qty"] == 190 and by_symbol["S1"]["side"] == "sell"
    assert by_symbol["L2"]["qty"] == 300
    assert by_symbol["SGOV"]["qty"] == 10_000
    assert all(isinstance(o["qty"], int) for o in plan.orders)
    assert all(o["time_in_force"] == "cls" and o["type"] == "market" for o in plan.orders)
    # drift: only L2 is off target: realized 300*33.3/1e6 = 0.00999 vs 0.01
    assert plan.payload["summary"]["rounding_drift_one_sided"] == pytest.approx(
        0.5 * abs(300 * 33.3 / 1e6 - 0.01), abs=1e-8
    )


def test_minimum_notional_drop_and_drift_report() -> None:
    target = make_target(
        weights={"L1": 0.01, "S1": -0.01, "T1": 0.00005, "SGOV": 1.0},
        reference_prices={"L1": 50.0, "S1": 50.0, "T1": 10.0, "SGOV": 100.0},
        exposures={
            s: NameExposure(beta=1.0, industry="a", size=1.0) for s in ("L1", "S1", "T1", "SGOV")
        },
    )
    client = FakeClient(assets={s: etb(s) for s in ("L1", "S1", "T1", "SGOV")})
    plan = plan_for(target, client, min_notional=100.0)
    assert [o["symbol"] for o in plan.orders if o["symbol"] == "T1"] == []
    assert plan.payload["dropped_min_notional"] == [{"symbol": "T1", "delta": 5, "notional": 50.0}]
    summary = plan.payload["summary"]
    assert summary["n_dropped_min_notional"] == 1
    assert summary["final_drift_one_sided"] > summary["rounding_drift_one_sided"]
    assert summary["final_drift_one_sided"] == pytest.approx(0.5 * 5 * 10.0 / 1e6, abs=1e-9)


def test_existing_positions_produce_deltas_and_closing_orders() -> None:
    client = all_etb_client(positions={"L1": 200, "S1": -200, "X9": 40})
    target = make_target()
    target = seal_target(
        target.model_copy(
            update={
                "reference_prices": {**target.reference_prices, "X9": 25.0},
                "exposures": {**target.exposures, "X9": NameExposure(beta=1, industry="a", size=1)},
            }
        )
    )
    plan = plan_for(target, client)
    by_symbol = {o["symbol"]: o for o in plan.orders}
    assert "L1" not in by_symbol  # already at target
    assert "S1" not in by_symbol
    assert by_symbol["X9"]["side"] == "sell" and by_symbol["X9"]["qty"] == 40
    assert by_symbol["X9"]["opens_or_increases_short"] is False


def test_client_order_id_is_deterministic_and_input_sensitive() -> None:
    a = client_order_id("b", "quant1", EXECUTION, "L1", "buy", 10)
    assert a == client_order_id("b", "quant1", EXECUTION, "L1", "buy", 10)
    assert a != client_order_id("b", "quant1", EXECUTION, "L1", "buy", 11)
    assert a != client_order_id("b", "quant2", EXECUTION, "L1", "buy", 10)
    assert a.startswith("bk1-") and len(a) <= 128


# --------------------------------------------------------------------------------------
# easy-to-borrow filter
# --------------------------------------------------------------------------------------


def test_etb_filter_removes_names_and_reports_residual() -> None:
    client = all_etb_client()
    client.assets["S1"] = etb("S1", easy_to_borrow=False)
    client.assets["S2"] = etb("S2", shortable=False)
    del client.assets["S3"]  # unknown to the broker
    plan = plan_for(make_target(), client)
    rejected = {r["symbol"]: r for r in plan.payload["etb_rejections"]}
    assert rejected["S1"]["reason"] == "not_easy_to_borrow"
    assert rejected["S2"]["reason"] == "not_shortable"
    assert rejected["S3"]["reason"] == "asset_not_found"
    assert rejected["S1"]["intended_qty"] == -200
    assert rejected["S1"]["residual_weight_vs_target"] == pytest.approx(0.01)
    assert not {"S1", "S2", "S3"} & {o["symbol"] for o in plan.orders}
    assert plan.payload["summary"]["n_etb_rejections"] == 3
    # the residual exposure is re-checked: net is now +3% of equity, inside the 5% limit
    net = next(c for c in plan.payload["checks"] if c["name"] == "net_dollar")
    assert net["value"] == pytest.approx(0.03) and net["passed"]


def test_etb_residual_can_block_the_plan_instead_of_being_replaced() -> None:
    client = all_etb_client()
    for s in NAMES_SHORT:
        client.assets[s] = etb(s, easy_to_borrow=False)
    weights = {s: 0.0125 for s in NAMES_LONG} | {s: -0.0125 for s in NAMES_SHORT} | {"SGOV": 1.0}
    plan = plan_for(make_target(weights=weights), client)
    assert plan.status == "blocked"
    assert "net_dollar" in failed_checks(plan)
    assert not set(NAMES_SHORT) & {o["symbol"] for o in plan.orders}  # no replacement name


def test_covering_a_short_does_not_need_borrow() -> None:
    client = FakeClient(
        positions={"S1": -400},
        assets={"S1": etb("S1", easy_to_borrow=False), "SGOV": etb("SGOV")},
    )
    target = make_target(
        weights={"S1": -0.01, "SGOV": 1.0},
        reference_prices={"S1": 50.0, "SGOV": 100.0},
        exposures={
            "S1": NameExposure(beta=1, industry="a", size=1),
            "SGOV": NameExposure(beta=0, industry="t", size=0),
        },
    )
    plan = plan_for(target, client)
    order = next(o for o in plan.orders if o["symbol"] == "S1")
    assert order["side"] == "buy" and order["qty"] == 200
    assert plan.payload["etb_rejections"] == []


# --------------------------------------------------------------------------------------
# risk checks block, never trim
# --------------------------------------------------------------------------------------


def test_clean_plan_passes_all_checks() -> None:
    plan = plan_for()
    assert plan.status == "ok", failed_checks(plan)
    names = {c["name"] for c in plan.payload["checks"]}
    assert {
        "data_freshness",
        "kill_switch_clear",
        "net_dollar",
        "gross_stock",
        "max_name_weight",
        "gross_leverage",
        "beta_neutral",
    } <= names
    assert plan.payload["summary"]["post_trade_long_notional"] == pytest.approx(50_000.0)
    assert plan.payload["summary"]["post_trade_short_notional"] == pytest.approx(50_000.0)


def test_net_dollar_check_blocks() -> None:
    weights = {s: 0.0125 for s in NAMES_LONG} | {s: -0.002 for s in NAMES_SHORT} | {"SGOV": 1.0}
    plan = plan_for(make_target(weights=weights))
    assert plan.status == "blocked" and "net_dollar" in failed_checks(plan)
    assert len(plan.orders) == 11  # blocked whole, not silently trimmed


def test_gross_stock_check_blocks_when_book_exceeds_target_gross() -> None:
    client = all_etb_client(positions={"Z1": 8000})
    target = make_target()
    target = seal_target(
        target.model_copy(
            update={
                "reference_prices": {**target.reference_prices, "Z1": 25.0},
                "exposures": {**target.exposures, "Z1": NameExposure(beta=0, industry="a", size=1)},
            }
        )
    )
    # Z1 is closed by an order, so gross stays at target; with the min-notional drop it would not
    plan = plan_for(target, client, min_notional=1e9)
    assert "gross_stock" in failed_checks(plan)


def test_max_name_weight_check_blocks() -> None:
    weights = {"L1": 0.02, "S1": -0.02, "SGOV": 1.0}
    target = make_target(
        weights=weights,
        reference_prices={"L1": 50.0, "S1": 50.0, "SGOV": 100.0},
        exposures={s: NameExposure(beta=1.0, industry="a", size=1.0) for s in ("L1", "S1", "SGOV")},
    )
    plan = plan_for(target, FakeClient(assets={s: etb(s) for s in ("L1", "S1", "SGOV")}))
    assert "max_name_weight" in failed_checks(plan) and plan.status == "blocked"


def test_gross_leverage_check_blocks_two_x_book() -> None:
    # +-0.5 around a 1.0 T-bill leg is exactly 2.0x: above the 1.98 buffer
    names = [f"N{i}" for i in range(80)]
    weights = {n: (0.00625 if i % 2 == 0 else -0.00625) for i, n in enumerate(names)}
    weights["SGOV"] = 1.0
    target = make_target(
        weights=weights,
        reference_prices=dict.fromkeys(weights, 50.0) | {"SGOV": 100.0},
        exposures={n: NameExposure(beta=1.0, industry="a", size=1.0) for n in weights},
    )
    client = FakeClient(assets={n: etb(n) for n in weights})
    plan = plan_for(target, client, limits=RiskLimits(max_gross_leverage=0.99))
    assert "gross_leverage" in failed_checks(plan)
    ok = plan_for(target, client)  # 1.5x with the default limit
    assert "gross_leverage" not in failed_checks(ok)
    real = [c for c in ok.payload["checks"] if c["name"] == "gross_leverage"][0]
    assert real["value"] == pytest.approx(1.5, abs=1e-3)


def test_beta_check_blocks() -> None:
    exposures = {
        s: NameExposure(beta=1.5 if s in NAMES_LONG else 0.2, industry="a", size=1.0)
        for s in NAMES_LONG + NAMES_SHORT
    } | {"SGOV": NameExposure(beta=0.0, industry="t", size=0.0)}
    plan = plan_for(make_target(exposures=exposures))
    assert "beta_neutral" in failed_checks(plan)  # 0.05 * 1.5 - 0.05 * 0.2 = 0.065


def test_exposures_complete_check_blocks() -> None:
    target = make_target()
    exposures = {k: v for k, v in target.exposures.items() if k != "L1"}
    plan = plan_for(make_target(exposures=exposures))
    assert "exposures_complete" in failed_checks(plan)


def test_freshness_requires_previous_session_and_execution_day() -> None:
    assert freshness_ok(DECISION, EXECUTION, EXECUTION)[0]
    assert freshness_ok(DECISION, EXECUTION, DECISION)[0]  # evening-before dry-run
    assert not freshness_ok(DECISION, EXECUTION, date(2026, 10, 1))[0]
    assert not freshness_ok(date(2026, 9, 16), EXECUTION, EXECUTION)[0]
    assert not freshness_ok(DECISION, date(2026, 9, 19), date(2026, 9, 19))[0]  # Saturday
    plan = plan_for(as_of=date(2026, 10, 1))
    assert plan.status == "blocked" and "data_freshness" in failed_checks(plan)


def test_kill_switch_check_blocks_plan_and_submit() -> None:
    def tripped() -> None:
        raise RuntimeError("paper kill switch is enabled: test")

    plan = plan_for(kill_switch_check=tripped)
    assert "kill_switch_clear" in failed_checks(plan)
    ok = plan_for()
    client = all_etb_client()
    with pytest.raises(BookEngineError, match="kill switch"):
        submit_plan(client, ok, now=NOW, kill_switch_check=tripped)
    assert client.submitted == []


def test_real_kill_switch_file_semantics(sample_workspace: Path, tmp_path: Path) -> None:
    with pytest.raises(Exception, match="missing"):
        _require_kill_switch_clear(tmp_path / "empty")
    set_paper_kill_switch(sample_workspace, enabled=False, reason="clear", updated_by="pytest")
    _require_kill_switch_clear(sample_workspace)
    plan = plan_for(kill_switch_check=lambda: _require_kill_switch_clear(sample_workspace))
    assert plan.status == "ok"
    set_paper_kill_switch(sample_workspace, enabled=True, reason="hold", updated_by="pytest")
    plan = plan_for(kill_switch_check=lambda: _require_kill_switch_clear(sample_workspace))
    assert "kill_switch_clear" in failed_checks(plan)


def test_account_ready_and_conflicting_open_orders_block() -> None:
    client = all_etb_client()
    state = read_account_state(client)
    blocked_state = AccountState(**{**state.__dict__, "trading_blocked": True})
    plan = build_plan(
        make_target(),
        blocked_state,
        as_of=EXECUTION,
        now=NOW,
        asset_lookup=make_asset_lookup(client),
    )
    assert "account_ready" in failed_checks(plan)
    foreign = AccountState(**{**state.__dict__, "open_orders": (("L1", "someone-elses-order"),)})
    plan = build_plan(
        make_target(),
        foreign,
        as_of=EXECUTION,
        now=NOW,
        asset_lookup=make_asset_lookup(client),
    )
    assert "no_conflicting_open_orders" in failed_checks(plan)


def test_fractional_held_position_blocks() -> None:
    client = all_etb_client(positions={"L1": 10.5})
    assert "whole_share_positions" in failed_checks(plan_for(client=client))


# --------------------------------------------------------------------------------------
# submission window
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("local", "ok"),
    [
        (datetime(2026, 9, 18, 9, 29, tzinfo=ET), False),
        (datetime(2026, 9, 18, 9, 30, tzinfo=ET), True),
        (datetime(2026, 9, 18, 15, 44, 59, tzinfo=ET), True),
        (datetime(2026, 9, 18, 15, 45, tzinfo=ET), False),
        (datetime(2026, 9, 18, 15, 50, tzinfo=ET), False),
        (datetime(2026, 9, 17, 14, 0, tzinfo=ET), False),  # wrong day
    ],
)
def test_submission_window(local: datetime, ok: bool) -> None:
    if ok:
        require_submission_window(local, EXECUTION)
    else:
        with pytest.raises(BookEngineError):
            require_submission_window(local, EXECUTION)


def test_submission_window_early_close_day() -> None:
    day = date(2026, 11, 27)  # day after Thanksgiving, 13:00 ET close
    require_submission_window(datetime(2026, 11, 27, 12, 44, tzinfo=ET), day)
    with pytest.raises(BookEngineError):
        require_submission_window(datetime(2026, 11, 27, 12, 45, tzinfo=ET), day)
    with pytest.raises(BookEngineError):
        require_submission_window(datetime(2026, 11, 27, 12, 0), day)  # naive time


def test_submit_refuses_outside_window_and_when_blocked() -> None:
    client = all_etb_client()
    plan = plan_for(client=client)
    with pytest.raises(BookEngineError, match="15:45"):
        submit_plan(client, plan, now=datetime(2026, 9, 18, 19, 46, tzinfo=UTC))
    blocked = plan_for(as_of=date(2026, 10, 1), client=client)
    with pytest.raises(BookEngineError, match="blocked"):
        submit_plan(client, blocked, now=NOW)
    assert client.submitted == []


# --------------------------------------------------------------------------------------
# submit code path (fake client only) and idempotency
# --------------------------------------------------------------------------------------


def test_submit_sends_cls_orders_once_and_rerun_is_idempotent() -> None:
    client = all_etb_client()
    plan = plan_for(client=client)
    first = submit_plan(client, plan, now=NOW)
    assert len(first["sent"]) == len(plan.orders) == 11 and first["failed"] == []
    assert all(str(r.time_in_force.value).lower() == "cls" for r in client.submitted)
    assert all(
        isinstance(r.qty, int | float) and float(r.qty) == int(r.qty) for r in client.submitted
    )
    sides = [r.side.value for r in client.submitted]
    assert sides.index("buy") > max(i for i, s in enumerate(sides) if s == "sell")  # sells first
    n_sent = len(client.submitted)
    # re-run: a new plan sees the existing client order ids, and the submit path skips them
    plan2 = plan_for(client=client, existing_client_order_ids=OrderLookup(client, EXECUTION).ids())
    assert all(o["already_submitted"] for o in plan2.orders)
    second = submit_plan(client, plan2, now=NOW)
    assert second["sent"] == [] and len(second["skipped_existing"]) == len(plan2.orders)
    assert len(client.submitted) == n_sent


def test_submit_refuses_unverified_client_and_synthetic_book() -> None:
    plan = plan_for()
    plain = SimpleNamespace(submit_order=lambda r: None, get_orders=lambda filter=None: [])
    with pytest.raises(BookEngineError, match="strict Alpaca Paper factory"):
        submit_plan(plain, plan, now=NOW)
    synthetic = plan_for(make_target(book_id="synthetic_dryrun:F1"))
    with pytest.raises(BookEngineError, match="synthetic"):
        submit_plan(all_etb_client(), synthetic, now=NOW)


def test_failed_order_is_reported_and_others_continue() -> None:
    client = all_etb_client()
    original = client.submit_order

    def flaky(request):
        if request.symbol == "L1":
            raise RuntimeError("rejected")
        return original(request)

    client.submit_order = flaky
    report = submit_plan(client, plan_for(client=client), now=NOW)
    assert [f["symbol"] for f in report["failed"]] == ["L1"]
    assert report["failed"][0]["message"] == "rejected"  # the broker's reason, not only the type
    assert len(report["sent"]) == 10


def test_broker_error_text_is_one_line_masked_and_truncated() -> None:
    token = "PK" + "A" * 38
    text = broker_error_text(RuntimeError(f"forbidden\n key {token} for this account"))
    assert "\n" not in text and token not in text and "<masked>" in text
    assert len(broker_error_text(RuntimeError("word " * 200))) == 300


def test_rerun_receipt_never_overwrites_the_first(tmp_path: Path) -> None:
    first = next_orders_receipt_path(tmp_path, "quant1", EXECUTION, NOW)
    assert first == orders_receipt_path(tmp_path, "quant1", EXECUTION)
    write_json_atomic(first, {"sent": [{"symbol": "L1"}]})
    rerun = next_orders_receipt_path(tmp_path, "quant1", EXECUTION, NOW)
    assert rerun != first and rerun.name.startswith(f"{EXECUTION.isoformat()}.rerun-")
    assert json.loads(first.read_text())["sent"] == [{"symbol": "L1"}]


def test_plan_file_kept_for_same_orders_and_never_replaced_after_submission(
    tmp_path: Path,
) -> None:
    plan = plan_for()
    path = write_plan_file(tmp_path, plan)
    original = path.read_text()
    rebuilt = OrderPlan({**plan.payload, "created_at_utc": "2026-09-18T18:45:00Z"})
    assert write_plan_file(tmp_path, rebuilt) == path and path.read_text() == original
    changed = OrderPlan({**plan.payload, "orders": plan.payload["orders"][:-1]})
    write_plan_file(tmp_path, changed)  # no receipt yet: a pre-submission re-plan may replace it
    assert json.loads(path.read_text())["orders"] == changed.payload["orders"]
    account = plan.payload["account"]
    write_json_atomic(orders_receipt_path(tmp_path, account, plan.execution_date), {"sent": []})
    with pytest.raises(BookEngineError, match="already has an orders receipt"):
        write_plan_file(tmp_path, plan)
    assert json.loads(path.read_text())["orders"] == changed.payload["orders"]


def test_cli_submit_fails_loudly_when_an_order_is_not_accepted(monkeypatch, tmp_path) -> None:
    from typer.testing import CliRunner

    from open_composer.book_paper import cli as bp_cli
    from open_composer.book_paper import plan as bp_plan

    client = all_etb_client()
    plan = plan_for(client=client)
    account = plan.payload["account"]
    monkeypatch.setattr(bp_cli, "_build", lambda *a: (tmp_path, client, None, plan))
    monkeypatch.setattr(bp_cli, "_kill_switch_check", lambda root: lambda: None)
    rejected = {
        "submitted_at_utc": "2026-09-18T18:00:00Z",
        "plan_sha256": plan.payload["plan_sha256"],
        "sent": [],
        "skipped_existing": [],
        "failed": [
            {"symbol": "L1", "client_order_id": "c1", "error": "APIError", "message": "no cls"}
        ],
    }
    monkeypatch.setattr(bp_plan, "submit_plan", lambda *a, **k: rejected)
    runner = CliRunner()
    args = ["submit", "--account", account, "--submit"]
    result = runner.invoke(bp_cli.book_paper_app, args)
    assert result.exit_code == 2, result.output
    assert "ERROR: 1 order(s) were not accepted" in result.output
    receipt = orders_receipt_path(tmp_path, account, plan.execution_date)
    assert json.loads(receipt.read_text())["failed"][0]["message"] == "no cls"
    # a clean run exits 0 and prints nothing the cron health check reads as an error
    clean = {**rejected, "failed": [], "sent": [{"symbol": "L1"}]}
    monkeypatch.setattr(bp_plan, "submit_plan", lambda *a, **k: clean)
    ok = runner.invoke(bp_cli.book_paper_app, args)
    assert ok.exit_code == 0, ok.output
    assert not re.search(r"(?i)\b(traceback|error|exception|failed|fatal)\b", ok.output)
    assert json.loads(receipt.read_text())["failed"][0]["message"] == "no cls"  # first kept


# --------------------------------------------------------------------------------------
# targets and F1 -> F2
# --------------------------------------------------------------------------------------


def test_f1_to_f2_weights_pure() -> None:
    f1 = {"A": 0.01, "B": -0.01, "SGOV": 1.0}
    f2 = f1_to_f2_weights(f1)
    assert f2 == {"A": 0.01, "B": -0.01, "SPY": 1.0}
    assert f1 == {"A": 0.01, "B": -0.01, "SGOV": 1.0}  # input untouched
    assert f1_to_f2_weights({"A": 0.01, "BIL": 1.0}) == {"A": 0.01, "SPY": 1.0}
    with pytest.raises(BookTargetError):
        f1_to_f2_weights({"A": 0.01})
    with pytest.raises(BookTargetError):
        f1_to_f2_weights({"A": 0.01, "SGOV": 1.0, "SPY": 0.5})


def test_f1_target_converts_to_f2_target() -> None:
    f2 = convert_f1_target_to_f2(make_target(), spy_price=600.0)
    assert f2.form == "F2" and f2.account == "quant2" and f2.core_symbol == "SPY"
    assert f2.weights["SPY"] == 1.0 and "SGOV" not in f2.weights
    assert f2.stock_weights == make_target().stock_weights
    assert f2.reference_prices["SPY"] == 600.0 and f2.exposures["SPY"].beta == 1.0
    assert f2.payload_sha256 and f2.payload_sha256 != make_target().payload_sha256
    with pytest.raises(BookTargetError):
        convert_f1_target_to_f2(f2, spy_price=600.0)


def test_f2_book_core_leg_and_beta_exclude_spy() -> None:
    f2 = convert_f1_target_to_f2(make_target(), spy_price=600.0)
    client = FakeClient(assets={s: etb(s) for s in NAMES_LONG + NAMES_SHORT + ["SPY"]})
    plan = plan_for(f2, client)
    spy = next(o for o in plan.orders if o["symbol"] == "SPY")
    assert spy["qty"] == round(1_000_000 / 600.0)
    beta = next(c for c in plan.payload["checks"] if c["name"] == "beta_neutral")
    assert beta["value"] == pytest.approx(0.0)  # overlay only; SPY core excluded


def test_target_file_write_hash_and_immutability(tmp_path: Path) -> None:
    target = make_target()
    path = write_target_file(tmp_path, target)
    assert path == target_path(tmp_path, "quant1", DECISION)
    assert load_target_file(path).payload_sha256 == target.payload_sha256
    assert write_target_file(tmp_path, target) == path  # same payload: idempotent
    changed = make_target(equity_basis=2_000_000.0)
    with pytest.raises(BookTargetError, match="different payload"):
        write_target_file(tmp_path, changed)
    payload = json.loads(path.read_text())
    payload["weights"]["L1"] = 0.011
    path.write_text(json.dumps(payload))
    with pytest.raises(BookTargetError, match="hash mismatch"):
        load_target_file(path)


def test_target_validation_rejects_bad_core_and_missing_price() -> None:
    with pytest.raises(ValueError, match="core leg"):
        make_target(weights={"L1": 0.01, "SGOV": 0.5})
    with pytest.raises(ValueError, match="reference price"):
        make_target(reference_prices={"L1": 50.0, "SGOV": 100.0})
    with pytest.raises(ValueError, match="after decision_date"):
        make_target(execution_date=DECISION)
    with pytest.raises(ValueError, match="unknown book account"):
        make_target(account="paper1")


# --------------------------------------------------------------------------------------
# reconcile, TCA, shadow costs, daily record
# --------------------------------------------------------------------------------------


def _planned_with_fills(partial_symbol="L2"):
    client = all_etb_client()
    plan = plan_for(client=client)
    broker_orders = []
    for order in plan.orders:
        filled = order["qty"]
        if order["symbol"] == partial_symbol:
            filled = order["qty"] // 2
        if order["symbol"] == "S5":
            continue  # never reached the broker
        sign = 1 if order["side"] == "buy" else -1
        px = order["reference_price"] * (1 + sign * 0.001)  # 10 bp worse than the close
        broker_orders.append(
            {
                "client_order_id": order["client_order_id"],
                "symbol": order["symbol"],
                "side": order["side"],
                "qty": float(order["qty"]),
                "filled_qty": float(filled),
                "filled_avg_price": px,
                "status": "filled" if filled == order["qty"] else "partially_filled",
            }
        )
    return plan, broker_orders


def test_reconcile_with_partial_fill_and_missing_order() -> None:
    plan, broker_orders = _planned_with_fills()
    target = make_target()
    positions = {"L1": 200.0, "L2": 100.0, "L3": 200.0, "L4": 200.0, "L5": 200.0, "SGOV": 10_000.0}
    positions |= {"S1": -200.0, "S2": -200.0, "S3": -200.0, "S4": -200.0}
    prices = dict(target.reference_prices)
    rec = reconcile(plan, target, broker_orders, positions, prices)
    assert (rec["n_filled"], rec["n_partial"], rec["n_missing"]) == (9, 1, 1)
    assert rec["partial_fills"][0]["symbol"] == "L2"
    assert rec["partial_fills"][0]["unfilled_qty"] == 100
    assert [r["symbol"] for r in rec["unfilled_orders"]] == ["S5"]
    drift = {d["symbol"]: d for d in rec["position_drift_vs_plan"]}
    assert drift["L2"]["drift_qty"] == -100 and drift["S5"]["drift_qty"] == 200
    assert drift["L2"]["drift_weight"] == pytest.approx(-100 * 50 / 1e6)
    assert rec["realized_vs_target_one_sided_drift"] == pytest.approx(
        0.5 * (100 * 50 + 200 * 50) / 1e6
    )


def test_tca_arithmetic() -> None:
    fills = [
        {"symbol": "A", "side": "buy", "filled_qty": 100.0, "filled_avg_price": 100.10},
        {"symbol": "B", "side": "sell", "filled_qty": 200.0, "filled_avg_price": 49.95},
        {"symbol": "C", "side": "buy", "filled_qty": 0.0, "filled_avg_price": None},
    ]
    out = tca(fills, {"A": 100.0, "B": 50.0}, {"A": 100.05, "B": 50.05})
    rows = {r["symbol"]: r for r in out["fills"]}
    assert rows["A"]["vs_official_close_bp"] == pytest.approx(10.0)
    assert rows["B"]["vs_official_close_bp"] == pytest.approx(10.0)  # sold 10 bp below the close
    assert rows["A"]["vs_snapshot_1545_bp"] == pytest.approx((100.10 - 100.05) / 100.05 * 1e4)
    assert rows["B"]["vs_snapshot_1545_bp"] == pytest.approx((50.05 - 49.95) / 50.05 * 1e4)
    assert out["n_fills"] == 2
    notional_a, notional_b = 100 * 100.10, 200 * 49.95
    expected = (notional_a * 10.0 + notional_b * 10.0) / (notional_a + notional_b)
    assert out["mean_vs_official_close_bp"] == pytest.approx(expected)


def test_shadow_cost_arithmetic() -> None:
    target = make_target()
    fills = [
        {"symbol": "L1", "side": "buy", "filled_qty": 200.0, "filled_avg_price": 50.0},
        {"symbol": "S1", "side": "sell", "filled_qty": 200.0, "filled_avg_price": 50.0},
    ]
    close_positions = {"L1": 200.0, "S1": -200.0}
    close_prices = {"L1": 50.0, "S1": 50.0}
    out = shadow_costs(fills, target, close_positions, close_prices, trade_date=EXECUTION)
    hs = float(half_spread_bp(50.0, 5e7, 0.02, 2026, "close"))
    imp = float(impact_bp(10_000.0, 5e7, 0.02))
    assert out["half_spread"] == pytest.approx(2 * 10_000.0 * hs / 1e4)
    assert out["impact"] == pytest.approx(2 * 10_000.0 * imp / 1e4)
    assert out["fees"] == pytest.approx(20_000.0 * 0.5 / 1e4)
    assert out["borrow"] == pytest.approx(10_000.0 * 25.0 / 1e4 / 252)
    assert out["total"] == pytest.approx(
        out["half_spread"] + out["impact"] + out["fees"] + out["borrow"]
    )


def test_daily_record_net_is_gross_minus_shadow_costs(tmp_path: Path) -> None:
    plan, broker_orders = _planned_with_fills()
    target = make_target()
    positions = {
        s: float(plan.payload["post_trade_qty"][s]) for s in plan.payload["post_trade_qty"]
    }
    record = build_daily_record(
        plan,
        target,
        broker_orders=broker_orders,
        positions=positions,
        equity=1_000_500.0,
        last_equity=1_000_000.0,
        official_close=dict(target.reference_prices),
        snapshot_1545=dict(target.reference_prices),
        generated_at_utc="2026-09-18T21:00:00Z",
    )
    pnl = record["pnl"]
    assert pnl["gross_pnl_broker"] == pytest.approx(500.0)
    assert pnl["net_pnl"] == pytest.approx(500.0 - record["shadow_costs"]["total"])
    exposures = record["realized_exposures"]
    assert exposures["beta"] == pytest.approx(0.0, abs=1e-9)
    assert exposures["industry_net"]["ind_a"] == pytest.approx(0.0, abs=1e-9)
    path = write_daily_file(tmp_path, record)
    assert path == daily_path(tmp_path, "quant1", EXECUTION)
    assert json.loads(path.read_text())["pnl"]["net_pnl"] == pnl["net_pnl"]


def test_normalize_broker_order_and_account_state() -> None:
    order = SimpleNamespace(
        client_order_id="c1",
        symbol="L1",
        side=SimpleNamespace(value="buy"),
        qty="10",
        filled_qty="4",
        filled_avg_price="12.5",
        status=SimpleNamespace(value="partially_filled"),
    )
    assert normalize_broker_order(order) == {
        "client_order_id": "c1",
        "symbol": "L1",
        "side": "buy",
        "qty": 10.0,
        "filled_qty": 4.0,
        "filled_avg_price": 12.5,
        "status": "partially_filled",
    }
    state = read_account_state(FakeClient(positions={"A": 5, "B": -7}))
    assert state.positions == {"A": 5.0, "B": -7.0}
    assert state.status == "ACTIVE" and state.shorting_enabled and state.equity == 1_000_000.0


# --------------------------------------------------------------------------------------
# exit rules
# --------------------------------------------------------------------------------------


def _series(n=100, daily=0.0004, noise=0.002, seed=3):
    return list(np.random.default_rng(seed).normal(daily, noise, n))


def test_exit_rule_continue_on_healthy_record() -> None:
    market = list(np.random.default_rng(9).normal(0.0003, 0.01, 100))
    decision = evaluate_exit_rules(_series(), market)
    assert decision.action == "continue" and decision.signals == ()
    assert decision.metrics["rolling_63_net_sharpe"] > 0


def test_exit_rule_halve_on_drawdown_between_4_3_and_8_pct() -> None:
    returns = [0.001] * 30 + [-0.0012] * 40  # peak then slow bleed of about 4.6%
    decision = evaluate_exit_rules(returns)
    assert 0.043 < decision.metrics["drawdown_from_high"] < 0.08
    assert decision.action == "halve" and "drawdown_above_4.3pct" in decision.signals
    assert "realized_beta_21" in decision.not_evaluated


def test_exit_rule_stop_on_drawdown_above_8_pct() -> None:
    returns = [0.0] * 5 + [-0.0016] * 55
    decision = evaluate_exit_rules(returns)
    assert decision.metrics["drawdown_from_high"] > 0.08
    assert decision.action == "stop" and "drawdown_above_8pct" in decision.stop_reasons


def test_exit_rule_halve_on_rolling_sharpe() -> None:
    rng = np.random.default_rng(1)
    returns = list(rng.normal(-0.0004, 0.001, 80))  # tiny losses: drawdown small, Sharpe < -1
    decision = evaluate_exit_rules(returns)
    assert rolling_sharpe(returns) < -1.0
    assert "rolling_63_net_sharpe_below_-1.0" in decision.signals
    assert decision.metrics["drawdown_from_high"] < 0.043 and decision.action == "halve"
    assert evaluate_exit_rules(returns[:40]).not_evaluated == (
        "rolling_63_net_sharpe",
        "realized_beta_21",
    )


def test_exit_rule_beta_signal_halves_then_stops_after_five_sessions() -> None:
    rng = np.random.default_rng(5)
    market = list(rng.normal(0.0, 0.01, 60))
    quiet = list(rng.normal(0.0004, 0.001, 30))
    beta_run = [0.5 * m for m in market[30:]]  # beta 0.5 from session 31 on
    returns = quiet + beta_run
    halve = evaluate_exit_rules(returns[:34], market[:34])
    assert halve.action in {"halve", "continue"}
    final = evaluate_exit_rules(returns, market)
    assert final.metrics["realized_beta_21"] == pytest.approx(0.5, abs=1e-6)
    assert final.metrics["beta_breach_run_sessions"] > 5
    assert final.action == "stop" and "beta_breach_more_than_5_sessions" in final.stop_reasons
    one_day = evaluate_exit_rules(returns[:51], market[:51])
    assert one_day.metrics["beta_breach_run_sessions"] >= 1
    with pytest.raises(ValueError):
        evaluate_exit_rules(returns, market[:-1])


# --------------------------------------------------------------------------------------
# accounts: paper-origin guard and credential non-leak
# --------------------------------------------------------------------------------------


def _write_env(path: Path, *, base="https://paper-api.alpaca.markets/v2") -> Path:
    path.write_text(
        "\n".join(
            [
                f"ALPACA_BOOK_BASE_URL={base}",
                f"ALPACA_QUANT1_API_KEY_ID={FAKE_KEY}",
                f"ALPACA_QUANT1_API_SECRET_KEY={FAKE_SECRET}",
                "ALPACA_QUANT2_API_KEY_ID=PKTESTFAKEKEYID5678",
                "ALPACA_QUANT2_API_SECRET_KEY=otherFakeSecretValue0000000000000000000",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    path.chmod(0o600)
    return path


@pytest.mark.parametrize(
    "url",
    [
        "https://api.alpaca.markets",
        "https://paper-api.alpaca.markets.evil.example",
        "http://paper-api.alpaca.markets",
        "https://user:pw@paper-api.alpaca.markets",
        "https://evil.example/paper-api.alpaca.markets",
        "https://paper-api.alpaca.markets:8443",
        "",
    ],
)
def test_paper_origin_guard_rejects_non_paper_urls(url: str) -> None:
    with pytest.raises(BookAccountError):
        require_paper_origin(url)


def test_paper_origin_guard_accepts_paper_urls() -> None:
    for url in ("https://paper-api.alpaca.markets", "https://paper-api.alpaca.markets/v2/"):
        assert require_paper_origin(url) == "https://paper-api.alpaca.markets"


def test_load_credentials_guard_and_variable_names(tmp_path: Path, monkeypatch) -> None:
    env = _write_env(tmp_path / "book.env")
    creds = load_account_credentials("quant1", env)
    assert creds.base_url == "https://paper-api.alpaca.markets"
    assert creds.key_id == FAKE_KEY and creds.secret_key == FAKE_SECRET
    assert FAKE_KEY not in repr(creds) and FAKE_SECRET not in repr(creds)
    assert credential_variable_names("quant2") == (
        "ALPACA_BOOK_BASE_URL",
        "ALPACA_QUANT2_API_KEY_ID",
        "ALPACA_QUANT2_API_SECRET_KEY",
    )
    assert present_variables("quant1", env) == dict.fromkeys(
        credential_variable_names("quant1"), True
    )
    bad = _write_env(tmp_path / "bad.env", base="https://api.alpaca.markets")
    with pytest.raises(BookAccountError) as info:
        load_account_credentials("quant1", bad)
    assert FAKE_KEY not in str(info.value) and FAKE_SECRET not in str(info.value)
    with pytest.raises(BookAccountError, match="unknown book account"):
        load_account_credentials("paper1", env)
    with pytest.raises(BookAccountError, match="missing"):
        load_account_credentials("quant1", tmp_path / "nope.env")
    monkeypatch.setenv("OC_BOOK_ACCOUNTS_ENV", str(env))
    assert present_variables("quant2")["ALPACA_QUANT2_API_KEY_ID"] is True


def test_factory_builds_verified_paper_client(tmp_path: Path) -> None:
    client = make_trading_client("quant1", _write_env(tmp_path / "book.env"))
    assert _is_verified_paper_client(client)
    assert str(client._base_url).rstrip("/") == "https://paper-api.alpaca.markets"
    with pytest.raises(BookAccountError):
        make_trading_client(
            "quant1", _write_env(tmp_path / "x.env", base="https://api.alpaca.markets")
        )


def test_written_artifacts_never_contain_credentials(tmp_path: Path) -> None:
    env = _write_env(tmp_path / "book.env")
    creds = load_account_credentials("quant1", env)
    root = tmp_path / "repo"
    target = make_target()
    write_target_file(root, target)
    client = all_etb_client()
    plan = plan_for(target, client)
    write_plan_file(root, plan)
    report = submit_plan(client, plan, now=NOW)
    write_json_atomic(orders_receipt_path(root, "quant1", EXECUTION), report)
    plan2, broker_orders = _planned_with_fills()
    record = build_daily_record(
        plan2,
        target,
        broker_orders=broker_orders,
        positions={},
        equity=1_000_000.0,
        last_equity=1_000_000.0,
        official_close=dict(target.reference_prices),
        snapshot_1545={},
        generated_at_utc="2026-09-18T21:00:00Z",
    )
    write_daily_file(root, record)
    files = [p for p in root.rglob("*") if p.is_file()]
    assert len(files) == 4
    pattern = re.compile(r"PK[A-Z0-9]{12,}")
    for path in files:
        text = path.read_text(encoding="utf-8")
        assert creds.key_id not in text and creds.secret_key not in text, path.name
        assert not pattern.search(text), path.name
    assert load_plan_file(root / "reports/paper/book/quant1/plans/2026-09-18.json").status == "ok"


def test_submit_paces_orders_when_asked(monkeypatch) -> None:
    import time as time_module

    naps: list[float] = []
    monkeypatch.setattr(time_module, "sleep", lambda s: naps.append(s))
    client = all_etb_client()
    plan = plan_for(client=client)
    report = submit_plan(client, plan, now=NOW, pace_seconds=0.34)
    assert len(report["sent"]) == len(plan.orders)
    assert naps == [0.34] * (len(plan.orders) - 1)  # no pause before the first order


def test_submit_market_mode_sends_day_orders_and_rejects_unknown_modes() -> None:
    client = all_etb_client()
    plan = plan_for(client=client)
    report = submit_plan(client, plan, now=NOW, tif_mode="market")
    assert report["time_in_force"] == "day"
    assert all(str(r.time_in_force.value).lower() == "day" for r in client.submitted)
    with pytest.raises(BookEngineError):
        submit_plan(all_etb_client(), plan_for(client=all_etb_client()), now=NOW, tif_mode="opg")
