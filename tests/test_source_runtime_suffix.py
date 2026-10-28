"""Invented offline runtime/SDK-boundary fixtures, never an activation certificate."""

import copy
import hashlib
import json
import socket
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest
import requests

from open_composer.intraday_runner import source_bounded_gateway as g
from open_composer.intraday_runner import source_cash_observation as c
from open_composer.intraday_runner.source_dispatch_journal import SourceDispatchJournal
from tests.source_method_fixtures import source_reference

NOW = datetime(2026, 11, 3, 14, 35, tzinfo=UTC)
START = datetime(2026, 10, 19, tzinfo=UTC)
END = datetime(2026, 11, 14, tzinfo=UTC)
CID = "dia-base-2026-11-03-sell-AAPL"


def binding(path):
    raw = path.read_bytes()
    return dict(path=str(path), bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def deny(*a, **k):
        raise AssertionError("no real network in fixture")

    monkeypatch.setattr(socket.socket, "connect", deny)
    monkeypatch.setattr(socket.socket, "connect_ex", deny)


@pytest.fixture
def gateway(tmp_path, monkeypatch):
    # Verified factory/credential path is unchanged and NOT exercised here.
    monkeypatch.setattr(g, "_require_verified_paper_client", lambda client: None)
    calls = []
    current = [NOW]
    guards = []

    class Client:
        def __init__(self):
            self._session = requests.Session()
            self._retry = 3
            self._session.request = lambda method, url, **kwargs: (
                calls.append((method, url, copy.deepcopy(kwargs))) or {"id": "own", "status": "new"}
            )
            self.delay = 0
            self.mutate = False
            self.twice = False

        def submit_order(self, order):
            current[0] += timedelta(seconds=self.delay)
            body = order.to_request_fields()
            if self.mutate:
                body["qty"] = 99
            result = self._session.request(
                "POST", "https://paper-api.alpaca.markets/v2/orders", json=body
            )
            if self.twice:
                self._session.request(
                    "POST", "https://paper-api.alpaca.markets/v2/orders", json=body
                )
            return result

        def cancel_order_by_id(self, bid):
            return self._session.request(
                "DELETE", "https://paper-api.alpaca.markets/v2/orders/" + bid, params=None
            )

    client = Client()
    journal = SourceDispatchJournal(tmp_path / "journal")
    request = dict(
        client_order_id=CID,
        symbol="AAPL",
        side="sell",
        qty=2,
        type="limit",
        time_in_force="day",
        limit_price=10.0,
        execution_day="2026-11-03",
        reservation=dict(side="sell", symbol="AAPL", quantity=2, filled=0, limit_price=10.0),
        quote=dict(
            valid=True,
            timestamp_ns=int(NOW.timestamp()) * 10**9,
            bid=10.0,
            ask=10.1,
            bid_shares=2,
            ask_shares=2,
        ),
    )
    snap = dict(pending={CID: request["reservation"]}, consumed_ids=[CID], account_hash="a" * 64)
    signal = tmp_path / "signal.json"
    signal.write_text('{"invented":true}')
    gateway = g.SourceBoundedGateway(
        client,
        journal=journal,
        account_hash="a" * 64,
        authorized_at=START,
        expires_at=END,
        guard=lambda request, **kw: guards.append((request, kw)),
        read_guard=lambda: None,
        clock=lambda: current[0],
    )
    args = dict(
        prepared=request,
        reservation_snapshot=snap,
        signal_binding=binding(signal),
        execution_day=date(2026, 11, 3),
        authorized_at=START,
        expires_at=END,
        submit=gateway.submit,
        revalidate=lambda row: None,
        clock=lambda: NOW,
    )
    return client, journal, gateway, args, calls, current, guards


def test_exact_final_transport_one_call_no_retries(gateway):
    client, journal, gw, args, calls, _, guards = gateway
    journal.dispatch_once(**args)
    assert len(calls) == 1 and client._retry == 0 and len(guards) == 2
    assert calls[0][2]["timeout"] == 10 and calls[0][2]["allow_redirects"] is False
    with pytest.raises(FileExistsError):
        journal.dispatch_once(**args)
    assert len(calls) == 1


@pytest.mark.parametrize("fault", ["delay", "payload", "retry", "account", "unarmed"])
def test_final_boundary_refuses_after_sdk_latency_or_drift(gateway, fault):
    client, journal, gw, args, calls, _, _ = gateway
    if fault == "delay":
        client.delay = 6
    elif fault == "payload":
        client.mutate = True
    elif fault == "retry":
        client._retry = 3
    elif fault == "account":
        args["reservation_snapshot"]["account_hash"] = "b" * 64
    else:
        with pytest.raises(ValueError):
            client._session.request("POST", "https://paper-api.alpaca.markets/v2/orders", json={})
        assert not calls
        return
    with pytest.raises(ValueError):
        journal.dispatch_once(**args)
    assert not calls and journal.receive(CID)["stage"] == "dispatch_boundary_consumed_ack_unknown"


def test_second_physical_attempt_rejected_even_inside_sdk(gateway):
    client, journal, gw, args, calls, _, _ = gateway
    client.twice = True
    with pytest.raises(ValueError):
        journal.dispatch_once(**args)
    assert (
        len(calls) == 1
        and journal.receive(CID)["stage"] == "dispatch_boundary_consumed_ack_unknown"
    )


@pytest.mark.parametrize(
    "method,url",
    [
        ("GET", "https://api.alpaca.markets/v2/account"),
        ("POST", "https://paper-api.alpaca.markets/v2/orders"),
        ("PATCH", "https://paper-api.alpaca.markets/v2/orders/x"),
        ("GET", "https://paper-api.alpaca.markets/v2/portfolio/history"),
    ],
)
def test_outside_route_refuses(gateway, method, url):
    client, _, _, _, calls, _, _ = gateway
    with pytest.raises(ValueError):
        client._session.request(method, url)
    assert calls == []


@pytest.fixture
def cash_auth(tmp_path, monkeypatch):
    monkeypatch.setattr(c, "_require_kill_switch_clear", lambda root: None)
    code = binding(Path(c.__file__))

    def artifact(name, value):
        p = tmp_path / (name + ".json")
        p.write_text(json.dumps(value))
        return binding(p)

    auth = dict(
        kind=c.KIND,
        account="quant2",
        paper_only=True,
        orders_permitted=False,
        capital_usd=20000,
        state_directory=str(tmp_path / "state"),
        policy="DIA_BASE",
        active=True,
        authorized_at=START.isoformat(),
        expires_at=END.isoformat(),
        account_authority_expires_at=END.isoformat(),
        account_hash="a" * 64,
        own_initial_cash_verified=True,
        scope_conflicts_verified=True,
        other_reserved_cash_usd=0,
        foreign_positions={},
        code_bindings=[code],
        bindings={
            k: artifact(k, {"fixture": True})
            for k in ("spec", "scientific_contract", "account_scope", "implementation_review")
        },
    )
    auth["bindings"]["account_scope"] = artifact(
        "account-scope-accepted",
        dict(
            status="accepted_account_sleeve_scope",
            account_hash="a" * 64,
            capital_usd=20000,
            foreign_positions={},
        ),
    )
    auth["bindings"]["native_cash_acceptance"] = artifact(
        "native", dict(accepted=True, scope=c.KIND, orders_permitted=False, code_bindings=[code])
    )
    return tmp_path, auth


@pytest.mark.parametrize(
    "change",
    [
        {"active": False},
        {"orders_permitted": True},
        {"account": "quant1"},
        {"capital_usd": 20001},
        {"own_initial_cash_verified": "unknown"},
        {"scope_conflicts_verified": None},
        {"expires_at": "2026-11-03T14:35:00+00:00"},
    ],
)
def test_cash_preclient_scope_rejects(cash_auth, change):
    root, auth = cash_auth
    auth.update(change)
    with pytest.raises(ValueError):
        c.validate_authority(root, auth, NOW)


def test_cash_same_account_no_order_route_does_not_need_SIP(cash_auth):
    root, auth = cash_auth
    c.validate_authority(root, auth, NOW)
    assert not auth.get("current_SIP_verified", False)


def test_cash_missing_checkpoint_never_constructs_client(cash_auth):
    root, auth = cash_auth
    p = root / "auth.json"
    p.write_text(json.dumps(auth))
    calls = []
    with pytest.raises(ValueError, match="checkpoint absent"):
        c.observe(
            root,
            p,
            root / "state",
            root / "result.json",
            expected_authority_binding=binding(p),
            client_factory=lambda: calls.append(1),
            clock=lambda: NOW,
        )
    assert calls == [] and not (root / "result.json").exists()


@pytest.fixture
def funded_sales(tmp_path):

    from open_composer.intraday_runner.source_method_bindings import source_module
    from open_composer.intraday_runner.source_reservations import SourceReservations
    from open_composer.intraday_runner.source_state_checkpoint import SourceStateCheckpoint

    root = source_reference(tmp_path / "reference")
    state = SourceReservations(
        source_module(root, "cash").CashState(
            cash=20,
            lots={"AAPL": [dict(quantity=10, funded="2026-10-19")]},
            dividends=[dict(id="unknown-right", amount=2.55, due="2026-11-04")],
        )
    )
    store = SourceStateCheckpoint(tmp_path / "state", account_hash="a" * 64, sleeve_id="dia-base")
    return root, state, store


def make_two_sales(funded_sales, fee_rate):
    from open_composer.intraday_runner.source_dispatch_journal import _hash
    from open_composer.intraday_runner.source_funding_clock import application_path
    from open_composer.intraday_runner.source_state_checkpoint import snapshot

    root, state, store = funded_sales
    fills, evidence = {}, {"sale_origins": {}, "fixture_only": True}
    revision = None
    for label, stamp in [
        ("early", "2026-11-03T14:39:59+00:00"),
        ("late", "2026-11-03T14:40:00.000001+00:00"),
    ]:
        cid, fid = "sell-" + label, "fill-" + label
        state.reserve_sell(cid, "AAPL", 2, 10, "2026-11-03", "2026-11-04", fee_buffer_rate=fee_rate)
        state.confirmed_fill(cid, fid, 2, 10, "2026-11-03")
        fills[fid] = dict(
            client_order_id=cid,
            account_hash="a" * 64,
            received_at="2026-11-03T14:39:58+00:00",
            fixture_only=True,
        )
        sale = state.cashbook.sales[-1]
        generation = 0 if revision is None else revision["generation"] + 1
        evidence["sale_origins"][sale["id"]] = dict(fill_id=fid, generation=generation)
        revision = store.commit(
            snapshot(state, fills, {}, evidence=evidence),
            expected_head_sha256=None if revision is None else _hash(revision),
        )
        p = application_path(store.directory, fid)
        p.parent.mkdir(exist_ok=True)
        p.write_text(
            json.dumps(
                dict(
                    fill_id=fid,
                    sale_id=sale["id"],
                    revision_sha256=_hash(revision),
                    receipt_record_sha256=_hash(fills[fid]),
                    checkpoint_completed_at=stamp,
                )
            )
        )
    return root, state, store, revision


@pytest.mark.parametrize("fee_rate", [0.0, 0.01])
def test_late_sell_fee_hold_and_eligible_reservations_conserved(funded_sales, fee_rate):
    from open_composer.intraday_runner.source_funding_clock import (
        eligible_reservation_copy,
        restore_excluded_proceeds,
    )

    root, before, store, revision = make_two_sales(funded_sales, fee_rate)
    original = copy.deepcopy(before)
    cutoff = NOW + timedelta(minutes=5)
    working, _, _, _, excluded = eligible_reservation_copy(root, store, revision, cutoff)
    early, late = [s["id"] for s in before.cashbook.sales]
    assert excluded == {late: 20 - 20 * fee_rate}
    assert before.pending["sell-late"]["remaining_funding"] == [
        dict(source=late, amount=20 * fee_rate, funded="2026-11-04")
    ]
    working.reserve_buy("buy", "MSFT", 5, 6, 0, "2026-11-03", "2026-11-04")
    result = restore_excluded_proceeds(before, working, excluded)
    assert before == original
    assert result.pending["sell-late"] == before.pending["sell-late"]
    assert result.pending["sell-early"] == before.pending["sell-early"]
    assert result.pending["buy"]["remaining_funding"] == [
        dict(source="cash", amount=20, funded="2026-11-03"),
        dict(source=early, amount=10, funded="2026-11-04"),
    ]
    assert result.cashbook.sales[0]["unreserved"] == 10 - 20 * fee_rate
    assert result.cashbook.sales[1] == before.cashbook.sales[1]
    assert result.cashbook.cash == before.cashbook.cash
    assert result.cashbook.purchases == before.cashbook.purchases
    assert result.cashbook.lots == before.cashbook.lots
    assert result.cashbook.dividends == before.cashbook.dividends
    assert result.cash_reserved() == 20
    assert before.cash_reserved() == 0


@pytest.mark.parametrize(
    "fault",
    [
        "drop_old_fee",
        "change_old_fee",
        "late_buy",
        "restore_eligible",
        "new_late_hold",
        "bad_restore",
    ],
)
def test_funding_restoration_cannot_erase_or_reuse_reservations(funded_sales, fault):
    from open_composer.intraday_runner.source_funding_clock import (
        eligible_reservation_copy,
        restore_excluded_proceeds,
    )

    root, before, store, revision = make_two_sales(funded_sales, 0.01)
    working, _, _, _, excluded = eligible_reservation_copy(
        root, store, revision, NOW + timedelta(minutes=5)
    )
    working.reserve_buy("buy", "MSFT", 5, 6, 0, "2026-11-03", "2026-11-04")
    late = before.cashbook.sales[1]["id"]
    if fault == "drop_old_fee":
        del working.pending["sell-late"]
    elif fault == "change_old_fee":
        working.pending["sell-late"]["remaining_funding"][0]["amount"] = 0
    elif fault == "late_buy":
        working.pending["buy"]["remaining_funding"][1]["source"] = late
    elif fault == "restore_eligible":
        working.cashbook.sales[0]["unreserved"] = before.cashbook.sales[0]["unreserved"]
    elif fault == "new_late_hold":
        working.pending["new-hold"] = copy.deepcopy(working.pending["sell-late"])
    else:
        excluded[late] += 1
    with pytest.raises(ValueError):
        restore_excluded_proceeds(before, working, excluded)


@pytest.mark.parametrize("fault", ["missing_origin", "missing_fill", "changed_proof"])
def test_unresolved_actual_sale_is_hold_not_just_zero_proceeds(funded_sales, fault):
    from open_composer.intraday_runner.source_funding_clock import (
        application_path,
        eligible_reservation_copy,
    )

    root, before, store, revision = make_two_sales(funded_sales, 0)
    late = before.cashbook.sales[-1]["id"]
    changed = copy.deepcopy(revision)
    if fault == "missing_origin":
        del changed["snapshot"]["evidence"]["sale_origins"][late]
    elif fault == "missing_fill":
        del changed["snapshot"]["fills"]["fill-late"]
    else:
        p = application_path(store.directory, "fill-late")
        proof = json.loads(p.read_text())
        proof["receipt_record_sha256"] = "0" * 64
        p.write_text(json.dumps(proof))
    with pytest.raises(ValueError):
        eligible_reservation_copy(root, store, changed, NOW + timedelta(minutes=5))
    assert store.load() == revision  # No reconciliation or real cash mutation.


def test_missing_post_checkpoint_proof_excludes_known_sale_without_erasing_it(funded_sales):
    from open_composer.intraday_runner.source_funding_clock import (
        application_path,
        eligible_reservation_copy,
    )

    root, before, store, revision = make_two_sales(funded_sales, 0.01)
    application_path(store.directory, "fill-early").unlink()
    working, _, _, _, excluded = eligible_reservation_copy(
        root, store, revision, NOW + timedelta(minutes=5)
    )
    assert set(excluded) == {s["id"] for s in before.cashbook.sales}
    assert working.pending == before.pending
    assert working.cashbook.lots == before.cashbook.lots
    assert [s["amount"] for s in working.cashbook.sales] == [20, 20]
    assert [s["unreserved"] for s in working.cashbook.sales] == [0, 0]


def make_cash_state(root, directory, account):

    from open_composer.intraday_runner.source_method_bindings import source_module
    from open_composer.intraday_runner.source_reservations import SourceReservations
    from open_composer.intraday_runner.source_state_checkpoint import (
        SourceStateCheckpoint,
        snapshot,
    )

    source_root = root
    state = SourceReservations(source_module(source_root, "cash").CashState(cash=20000))
    store = SourceStateCheckpoint(directory, account_hash=account, sleeve_id="dia-base")
    store.commit(
        snapshot(state, {}, {}, evidence={"fixture_only": True}), expected_head_sha256=None
    )
    return store


@pytest.mark.parametrize(
    "fault",
    [
        None,
        "401",
        "identity",
        "inactive",
        "foreign_position",
        "own_order",
        "encumbered",
        "unknown_buy",
        "truncated",
    ],
)
@pytest.mark.native_resource
def test_complete_cash_branch_current_reconciliation_without_writes(cash_auth, fault):
    from open_composer.adapters.broker.alpaca_paper import _optional_broker_account_hash

    root, auth = cash_auth
    identity = "fixture-account-not-real"
    auth["account_hash"] = _optional_broker_account_hash(identity)
    scopepath = Path(auth["bindings"]["account_scope"]["path"])
    scope = json.loads(scopepath.read_text())
    scope["account_hash"] = auth["account_hash"]
    scopepath.write_text(json.dumps(scope))
    auth["bindings"]["account_scope"] = binding(scopepath)
    authority = root / "authority.json"
    authority.write_text(json.dumps(auth))
    make_cash_state(root, root / "state", auth["account_hash"])
    calls = []

    class Client:
        def __init__(self):
            self._session = self

        def close(self):
            calls.append("close")

        def get_account(self):
            calls.append("account")
            if fault == "401":
                raise RuntimeError("invented unauthorized response")
            return dict(
                id="wrong" if fault == "identity" else identity,
                status="inactive" if fault == "inactive" else "ACTIVE",
                account_blocked=False,
                trading_blocked=False,
                cash="25000",
                equity="25000",
                buying_power="25000",
                non_marginable_buying_power="25000",
            )

        def get_all_positions(self):
            calls.append("positions")
            return [dict(symbol="AAPL", qty=1)] if fault == "foreign_position" else []

        def get_orders(self, request):
            calls.append("orders")
            if fault == "truncated":
                return [{}] * 500
            if fault in {"own_order", "encumbered", "unknown_buy"}:
                return [
                    dict(
                        client_order_id="dia-base-own" if fault == "own_order" else "other",
                        side="buy",
                        qty="1000",
                        filled_qty="0",
                        status="new",
                        limit_price=None if fault == "unknown_buy" else "10",
                    )
                ]
            return []

    if fault is None:
        result = c.observe(
            root,
            authority,
            root / "state",
            root / "out.json",
            expected_authority_binding=binding(authority),
            client_factory=Client,
            clock=lambda: NOW,
        )
        assert result["status"] == "actual_cash_only_no_trade" and result["order_writes"] == 0
        assert calls == ["account", "positions", "orders", "close"]
    else:
        with pytest.raises((ValueError, RuntimeError, TypeError)):
            c.observe(
                root,
                authority,
                root / "state",
                root / "out.json",
                expected_authority_binding=binding(authority),
                client_factory=Client,
                clock=lambda: NOW,
            )
        assert not (root / "out.json").exists() and calls[-1] == "close"


def test_cash_http_boundary_has_no_write_or_retry(monkeypatch):
    class Client:
        def __init__(self):
            self._session = requests.Session()
            self._retry = 3

    client = Client()
    sent = []
    client._session.request = lambda method, url, **kw: sent.append((method, url, kw))
    monkeypatch.setattr(c, "make_trading_client", lambda account: client)
    monkeypatch.setattr(c, "_require_verified_paper_client", lambda client: None)
    actual = c._read_only_client(read_guard=lambda: None)
    for method in ("POST", "DELETE", "PATCH"):
        with pytest.raises(ValueError):
            actual._session.request(method, "https://paper-api.alpaca.markets/v2/orders")
    assert not sent
    actual._session.request("GET", "https://paper-api.alpaca.markets/v2/account")
    assert sent[0][2]["allow_redirects"] is False and client._retry == 0
    client._retry = 1
    with pytest.raises(ValueError):
        actual._session.request("GET", "https://paper-api.alpaca.markets/v2/account")
    assert len(sent) == 1


@pytest.fixture
def quantity_case(tmp_path):

    from open_composer.intraday_runner.source_dispatch_journal import _hash
    from open_composer.intraday_runner.source_method_bindings import source_module
    from open_composer.intraday_runner.source_reservations import SourceReservations
    from open_composer.intraday_runner.source_state_checkpoint import (
        SourceStateCheckpoint,
        snapshot,
    )

    root = source_reference(tmp_path / "reference")
    contract = root / (
        "reports/research/program/owner-profit-delivery-plan-20261017/"
        "candidate-contribution/future-input-receiver/accepted-integration-contract.json"
    )
    symbols = json.loads(contract.read_text())["output_identity"]
    state = SourceReservations(source_module(root, "cash").CashState(cash=20000))
    store = SourceStateCheckpoint(tmp_path / "state", account_hash="a" * 64, sleeve_id="dia-base")
    revision = store.commit(snapshot(state, {}, {}, evidence={}), expected_head_sha256=None)
    forecast = dict(
        accepted=True,
        completed_at="2026-11-02T15:00:00-05:00",
        forecast=dict(
            formation_month="2026-10",
            policy="DIA28_BASE_SEQUENTIAL_ORIGINAL",
            symbols=symbols,
            weights=[0.2] * 5 + [0.0] * 23,
        ),
    )
    q = dict(
        accepted=True,
        formation_month="2026-10",
        scientific_contract=binding(contract),
        account_hash="a" * 64,
        state_sha256=_hash(revision),
        received_at="2026-11-02T16:05:00-05:00",
        held_rights_complete=True,
        price_basis="raw_completed_decision_close",
        price_session="2026-11-02",
        own_nav=20000,
        prices={s: 100 for s in symbols},
        hygiene_valid={s: True for s in symbols},
        split_trigger={s: False for s in symbols},
    )
    fp, qp = tmp_path / "forecast.json", tmp_path / "quantity.json"
    fp.write_text(json.dumps(forecast))
    qp.write_text(json.dumps(q))
    return root, revision, fp, qp, tmp_path / "commit.json"


def test_original_quantity_sizing_and_actual_clocks(quantity_case):
    from open_composer.intraday_runner.source_quantity_commit import (
        confirm_continuity,
        prepare_commit,
    )

    root, revision, fp, qp, output = quantity_case
    now = datetime(2026, 11, 2, 21, 10, tzinfo=UTC)
    result = prepare_commit(
        root,
        forecast_reception=binding(fp),
        quantity_input=binding(qp),
        revision=revision,
        account_hash="a" * 64,
        output=output,
        now=lambda: now,
    )
    assert result["committed_at"] == "2026-11-02T16:15:00-05:00"
    assert result["actual_created_at"] == now.isoformat()
    assert [r["max_quantity"] for r in result["buy"][:5]] == [39] * 5
    proof = dict(
        accepted=True,
        complete_own_state=True,
        state_sha256=result["state_sha256"],
        account_hash="a" * 64,
        observed_at="2026-11-02T21:15:01+00:00",
        reconciled_through="2026-11-02T21:15:00+00:00",
    )
    confirm_continuity(result, proof, actual_sealed_at="2026-11-02T21:14:59.999999+00:00")
    for sealed in ["2026-11-02T21:15:00.000001+00:00", "2026-11-02T21:15:00.000000001+00:00"]:
        with pytest.raises(ValueError):
            confirm_continuity(result, proof, actual_sealed_at=sealed)
    proof["state_sha256"] = "b" * 64
    with pytest.raises(ValueError):
        confirm_continuity(result, proof, actual_sealed_at=now.isoformat())


def test_late_durable_quantity_file_is_retained_without_success(quantity_case, monkeypatch):
    from open_composer.intraday_runner import source_quantity_commit as qmod

    root, revision, fp, qp, output = quantity_case
    now = [datetime(2026, 11, 2, 21, 14, 59, tzinfo=UTC)]
    real = qmod._atomic_write_text

    def delayed(path, text):
        real(path, text)
        now[0] = datetime(2026, 11, 2, 21, 15, 0, 1, tzinfo=UTC)

    monkeypatch.setattr(qmod, "_atomic_write_text", delayed)
    with pytest.raises(ValueError, match="completed late"):
        qmod.prepare_commit(
            root,
            forecast_reception=binding(fp),
            quantity_input=binding(qp),
            revision=revision,
            account_hash="a" * 64,
            output=output,
            now=lambda: now[0],
        )
    assert output.exists() and not output.with_suffix(".json.completed.json").exists()


@pytest.mark.parametrize(
    "fault", ["future_close", "wrong_roster", "nontrue_hygiene", "state", "rights"]
)
def test_quantity_actual_input_refuses_before_publication(quantity_case, fault):
    from open_composer.intraday_runner.source_quantity_commit import prepare_commit

    root, revision, fp, qp, output = quantity_case
    q, f = json.loads(qp.read_text()), json.loads(fp.read_text())
    if fault == "future_close":
        q["received_at"] = "2026-11-02T21:11:00+00:00"
    elif fault == "wrong_roster":
        f["forecast"]["symbols"][0] = "OTHER"
    elif fault == "nontrue_hygiene":
        q["hygiene_valid"][f["forecast"]["symbols"][0]] = "unknown"
    elif fault == "state":
        q["state_sha256"] = "b" * 64
    else:
        q["held_rights_complete"] = None
    fp.write_text(json.dumps(f))
    qp.write_text(json.dumps(q))
    with pytest.raises(ValueError):
        prepare_commit(
            root,
            forecast_reception=binding(fp),
            quantity_input=binding(qp),
            revision=revision,
            account_hash="a" * 64,
            output=output,
            now=lambda: datetime(2026, 11, 2, 21, 10, tzinfo=UTC),
        )
    assert not output.exists()


@pytest.mark.parametrize("late", [False, True])
def test_actual_reception_checkpoint_clock_and_terminal_fee_hold(tmp_path, monkeypatch, late):
    from types import SimpleNamespace

    from open_composer.adapters.broker.alpaca_paper import _optional_broker_account_hash
    from open_composer.intraday_runner import source_method_runtime as runtime_module
    from open_composer.intraday_runner.source_activity_reception import receive_actual
    from open_composer.intraday_runner.source_dispatch_journal import _hash
    from open_composer.intraday_runner.source_funding_clock import (
        application_path,
        eligible_reservation_copy,
    )
    from open_composer.intraday_runner.source_method_bindings import source_module
    from open_composer.intraday_runner.source_reservations import SourceReservations
    from open_composer.intraday_runner.source_state_checkpoint import (
        SourceStateCheckpoint,
        restore,
        snapshot,
    )

    reference = source_reference(tmp_path / "reference")
    account_id = "invented-account"
    ah = _optional_broker_account_hash(account_id)
    state = SourceReservations(
        source_module(reference, "cash").CashState(
            cash=20, lots={"AAPL": [dict(quantity=10, funded="2026-10-19")]}
        )
    )
    reservation = state.reserve_sell(
        CID, "AAPL", 2, 10, "2026-11-03", "2026-11-04", fee_buffer_rate=0.01
    )
    store = SourceStateCheckpoint(tmp_path / "state", account_hash=ah, sleeve_id="dia-base")
    store.commit(snapshot(state, {}, {}, evidence={}), expected_head_sha256=None)
    journal = SourceDispatchJournal(tmp_path / "journal")
    order = dict(
        id="invented-broker-order",
        client_order_id=CID,
        symbol="AAPL",
        side="sell",
        type="limit",
        time_in_force="day",
        qty="2",
        limit_price="10",
        status="filled",
        filled_qty="2",
    )
    request = dict(
        client_order_id=CID,
        symbol="AAPL",
        side="sell",
        qty=2,
        type="limit",
        time_in_force="day",
        limit_price=10.0,
        reservation=reservation,
        quote=dict(
            valid=True,
            timestamp_ns=int(NOW.timestamp()) * 10**9,
            bid=10.0,
            ask=10.1,
            bid_shares=2,
            ask_shares=2,
        ),
    )
    sig = tmp_path / "signal.json"
    sig.write_text('{"invented":true}')
    journal.dispatch_once(
        request,
        reservation_snapshot={**store.load()["snapshot"], "account_hash": ah},
        signal_binding=binding(sig),
        execution_day=NOW.date(),
        authorized_at=START,
        expires_at=END,
        submit=lambda req: dict(order, status="new", filled_qty="0"),
        revalidate=lambda row: None,
        clock=lambda: NOW,
    )
    now = [NOW + timedelta(minutes=4, seconds=58)]
    calls = []

    class Client:
        def get_account(self):
            calls.append("GET account")
            return {"id": account_id}

        def get_order_by_client_id(self, cid):
            calls.append("GET owned order")
            return copy.deepcopy(order)

        def get(self, endpoint, params):
            calls.append("GET FILL")
            return [
                dict(
                    id="fill-1",
                    activity_type="FILL",
                    type="fill",
                    order_id=order["id"],
                    symbol="AAPL",
                    side="sell",
                    qty="2",
                    cum_qty="2",
                    price="10",
                    transaction_time=(NOW + timedelta(seconds=1)).isoformat(),
                )
            ]

    runtime = object.__new__(runtime_module.SourceMethodRuntime)
    runtime.root, runtime.store, runtime.journal = tmp_path, store, journal
    runtime._operation_held = True
    runtime.authority = {"fixture": True}
    runtime.auth = dict(
        account_hash=ah, authorized_at=START.isoformat(), expires_at=END.isoformat()
    )
    runtime.clock = lambda: now[0]
    runtime.gateway = SimpleNamespace(client=Client(), last_read_status=200)
    runtime.connect = lambda: runtime.gateway
    monkeypatch.setattr(runtime_module, "load_scope", lambda *a: runtime.auth)
    real_commit = store.commit

    def commit_then_clock(*a, **k):
        result = real_commit(*a, **k)
        if late:
            now[0] = NOW + timedelta(minutes=5, microseconds=1)
        return result

    monkeypatch.setattr(store, "commit", commit_then_clock)
    result = receive_actual(runtime, tmp_path / "reception", clock=runtime.clock)
    final = store.load()
    got, fills, fees, evidence = restore(tmp_path, final["snapshot"])
    assert result["order_writes"] == 0 and calls == ["GET account", "GET owned order", "GET FILL"]
    assert got.cashbook.quantity("AAPL") == 8 and got.cashbook.cash == 20
    hold = got.pending["liability-" + CID]
    assert hold["side"] == "liability_hold" and hold["remaining_funding"][0]["amount"] == 0.2
    assert got.cashbook.sales[0]["amount"] == 20 and got.cashbook.sales[0]["unreserved"] == 19.8
    assert got.cashbook.purchases == [] and not fees and len(fills) == 1
    proof = json.loads(application_path(store.directory, "fill-1").read_text())
    assert datetime.fromisoformat(proof["checkpoint_completed_at"]) == now[0]
    _, _, _, _, excluded = eligible_reservation_copy(
        tmp_path, store, final, NOW + timedelta(minutes=5)
    )
    assert bool(excluded) is late
    assert _hash(final) == _hash(store.load())  # No eligibility-side economic mutation.


def test_native_entry_refuses_before_kernel_client_or_source(tmp_path, monkeypatch):
    from open_composer.intraday_runner import source_runtime_entry as entry

    called = []
    monkeypatch.setattr(entry, "kernel_evidence", lambda: called.append("kernel"))
    bad = tmp_path / "job.json"
    bad.write_text(json.dumps(dict(phase="buy", active=False)))
    with pytest.raises(ValueError, match="scoped"):
        entry.entry_gate(tmp_path, binding(bad), NOW, requested_output=tmp_path / "out")
    assert not called


@pytest.mark.parametrize("fault", [None, "late", "403", "partial", "split", "unknown_liability"])
def test_actual_close_reception_boundary_without_any_real_source(quantity_case, tmp_path, fault):
    from types import SimpleNamespace

    from open_composer.intraday_runner.source_dispatch_journal import _hash
    from open_composer.intraday_runner.source_initial_commit import receive_close
    from open_composer.intraday_runner.source_state_checkpoint import SourceStateCheckpoint

    root, revision, fp, qp, _ = quantity_case
    q = json.loads(qp.read_text())
    symbols = json.loads(fp.read_text())["forecast"]["symbols"]
    store = SourceStateCheckpoint(tmp_path / "state", account_hash="a" * 64, sleeve_id="dia-base")
    value = copy.deepcopy(revision["snapshot"])
    value["evidence"]["held_rights_complete"] = True
    current = store.commit(value, expected_head_sha256=_hash(revision))
    now = [datetime(2026, 11, 2, 21, 10, tzinfo=UTC)]

    def observation(**kwargs):
        p = tmp_path / "fake-observation.json"
        p.write_text(json.dumps(dict(unborrowed_new_capacity=20000, own_gross=0)))
        return binding(p)

    runtime = SimpleNamespace(
        root=root,
        store=store,
        auth=dict(
            universe=symbols,
            account_hash="a" * 64,
            bindings={"scientific_contract": q["scientific_contract"]},
        ),
        capture_observation=observation,
    )
    calls = []

    def fetch(endpoint, params, timeout):
        calls.append((endpoint, params))
        body = dict(
            bars={
                s: [
                    dict(t="2026-10-30T04:00:00Z", o=100, c=100, v=100),
                    dict(t="2026-11-02T05:00:00Z", o=100, c=100, v=100),
                ]
                for s in symbols
            },
            next_page_token=None,
        )
        if fault == "late":
            now[0] = datetime(2026, 11, 2, 21, 15, 0, 1, tzinfo=UTC)
        if fault == "partial":
            body["next_page_token"] = "not-complete"
        if fault == "split":
            body["bars"][symbols[0]][1].update(o=1, c=1)
        return SimpleNamespace(
            entity_bytes=json.dumps(body).encode(),
            status_code=403 if fault == "403" else 200,
            headers={},
        )

    if fault == "unknown_liability":
        value = copy.deepcopy(current["snapshot"])
        value["cashbook"]["dividends"] = [dict(id="unknown", amount=1, due="2026-11-04")]
        store.commit(value, expected_head_sha256=_hash(current))
    if fault in {"late", "403", "partial", "unknown_liability"}:
        with pytest.raises(ValueError):
            receive_close(
                runtime,
                SimpleNamespace(fetch=fetch),
                directory=tmp_path / "capture",
                clock=lambda: now[0],
            )
        if fault == "unknown_liability":
            assert not calls
    else:
        result = receive_close(
            runtime,
            SimpleNamespace(fetch=fetch),
            directory=tmp_path / "capture",
            clock=lambda: now[0],
        )
        item = json.loads(Path(result["path"]).read_text())
        assert (
            len(calls) == 1 and calls[0][1]["adjustment"] == "raw" and calls[0][1]["feed"] == "sip"
        )
        assert item["state_sha256"] == _hash(current) and item["own_nav"] == 20000
        assert item["split_trigger"][symbols[0]] is (fault == "split")
        if fault == "split":
            assert not item["hygiene_valid"][symbols[0]]
        assert len(item["source_pointers"]) == 56


@pytest.mark.parametrize("fault", [None, "403", "late", "repeating_token", "withdrawal"])
def test_exact_sip_capture_preserves_failed_packets_and_fixed_cutoff(tmp_path, fault):
    from types import SimpleNamespace

    from open_composer.intraday_runner.source_quote_reception import receive_window

    root = source_reference(tmp_path / "reference")
    meta = json.loads(
        (
            root
            / (
                "reports/research/program/owner-profit-delivery-plan-20261017/"
                "paper-delivery/runtime-reader-bindings.json"
            )
        ).read_text()
    )["bindings"]
    now = [NOW]
    calls = []
    quote = dict(
        t="2026-11-03T14:35:00Z",
        bp=10.0,
        ap=10.1,
        bs=10,
        **{"as": 10},
        bx="Q",
        ax="Q",
        z="C",
        c=["R", "R"],
    )

    def fetch(url, params, timeout):
        calls.append(copy.deepcopy(params))
        rows = [quote]
        if fault == "withdrawal":
            rows = [dict(quote, bp=0, bs=0)]
        if fault == "late":
            now[0] = NOW + timedelta(seconds=6)
        return SimpleNamespace(
            status_code=403 if fault == "403" else 200,
            headers={},
            entity_bytes=json.dumps(
                dict(
                    quotes={"AAPL": rows},
                    next_page_token="same" if fault == "repeating_token" else None,
                )
            ).encode(),
        )

    args = dict(
        symbols=["AAPL"],
        universe=["AAPL"],
        cutoff=NOW,
        metadata_bindings=meta,
        prior_references={"AAPL": dict(close=10, hygiene_valid=True, split_session=False)},
        directory=tmp_path / "capture",
        clock=lambda: now[0],
    )
    if fault in {"403", "late", "repeating_token"}:
        with pytest.raises(ValueError):
            receive_window(root, SimpleNamespace(fetch=fetch), **args)
        assert (tmp_path / "capture/page-000.raw").exists()
    else:
        _, parsed, pages = receive_window(root, SimpleNamespace(fetch=fetch), **args)
        assert parsed["AAPL"]["valid"] is (fault is None) and len(pages) == 1
    assert calls[0]["end"] == "2026-11-03T14:35:00.000000001Z"
    assert calls[0]["feed"] == "sip" and calls[0]["asof"] == "-"
    assert len(calls) == (2 if fault == "repeating_token" else 1)


@pytest.mark.parametrize(
    "fault",
    [None, "missing_open", "drawdown", "unknown_liability", "unmatched_position", "unknown_status"],
)
def test_account_observation_risk_basis_and_unresolved_hold(funded_sales, tmp_path, fault):
    from types import SimpleNamespace

    from open_composer.adapters.broker.alpaca_paper import _optional_broker_account_hash
    from open_composer.intraday_runner import source_account_observation as account
    from open_composer.intraday_runner.source_dispatch_journal import _hash
    from open_composer.intraday_runner.source_state_checkpoint import snapshot

    root, state, store = funded_sales
    state.cashbook.dividends = []  # This risk fixture has no receivable.
    equity = 20 + 10 * 10
    evidence = dict(
        held_rights_complete=True,
        unresolved_actual_liabilities=False,
        risk_session="2026-11-03",
        day_open_nav=equity,
        high_water=equity,
        daily_halt=False,
        kill=False,
    )
    if fault == "missing_open":
        evidence["risk_session"] = "2026-11-02"
    if fault == "drawdown":
        evidence.update(risk_session="2026-11-02", high_water=200)
    if fault == "unknown_liability":
        evidence["unresolved_actual_liabilities"] = "unknown"
    revision = store.commit(snapshot(state, {}, {}, evidence=evidence), expected_head_sha256=None)
    actual_id = "invented-account"
    native = tmp_path / "native.json"
    native.write_text(
        json.dumps(dict(accepted=True, code_bindings=[binding(Path(account.__file__))]))
    )
    auth = dict(
        account_hash=_optional_broker_account_hash(actual_id),
        foreign_positions={},
        authorized_at=START.isoformat(),
        allocated_usd=20000,
        account_gross_cap=100000,
        other_reserved_cash_excluding_open_buys=0,
        bindings={"native_acceptance": binding(native)},
    )

    class Client:
        def get_account(self):
            return dict(
                id=actual_id,
                account_blocked=False,
                trading_blocked=False,
                status="ACTIVE",
                cash=20000,
                non_marginable_buying_power=20000,
                equity=20100,
            )

        def get_all_positions(self):
            return [
                dict(
                    symbol="AAPL", qty=11 if fault == "unmatched_position" else 10, market_value=100
                )
            ]

        def get_orders(self, request):
            return []

        def get_asset(self, symbol):
            return dict(
                symbol=symbol, status="active", tradable=None if fault == "unknown_status" else True
            )

    quotes = {"AAPL": dict(valid=True, bid=10, timestamp_ns=int(NOW.timestamp()) * 10**9)}
    if fault in {"unknown_liability", "unmatched_position"}:
        with pytest.raises(ValueError):
            account.capture_current(
                root,
                Client(),
                auth,
                revision,
                quotes=quotes,
                journal=SimpleNamespace(),
                directory=tmp_path / "observation",
                clock=lambda: NOW,
            )
    else:
        received = account.capture_current(
            root,
            Client(),
            auth,
            revision,
            quotes=quotes,
            journal=SimpleNamespace(),
            directory=tmp_path / "observation",
            clock=lambda: NOW,
        )
        row = json.loads(Path(received["path"]).read_text())
        assert row["owned_state_sha256"] == _hash(revision) and row["own_nav"] == 120
        assert row["tradable"]["AAPL"] is (fault != "unknown_status")
        assert row["risk"]["kill"] is (fault == "drawdown")
        assert row["new_risk_allowed"] is (fault in {None, "unknown_status"})
        assert row["method_invocations"] == 5


@pytest.mark.native_resource
def test_native_gate_uses_actual_cgroup_and_exact_code_before_any_factory(tmp_path):
    from open_composer.intraday_runner import source_runtime_entry as entry

    codes = [binding(p) for p in sorted(Path(entry.__file__).parent.glob("source_*.py"))]
    authpath = tmp_path / "authority.json"
    authpath.write_text("{}")
    authority = binding(authpath)
    native = tmp_path / "native.json"
    native.write_text(
        json.dumps(
            dict(
                accepted=True,
                scope="dia_base_complete_entry_v1",
                allowed_phases=["cash"],
                code_bindings=codes,
                authority=authority,
                output=str(tmp_path / "out"),
                invocation_id="invented-offline",
            )
        )
    )
    disk = tmp_path / "disk.json"
    disk.write_text(
        json.dumps(dict(accepted=True, invocation_id="invented-offline", required_free_bytes=65536))
    )
    job = tmp_path / "job.json"
    value = dict(
        phase="cash",
        active=True,
        not_before=START.isoformat(),
        expires_at=END.isoformat(),
        native_acceptance=binding(native),
        code_bindings=codes,
        authority=authority,
        disk_admission=binding(disk),
        invocation_id="invented-offline",
        output=str(tmp_path / "out"),
    )
    job.write_text(json.dumps(value))
    _, observed = entry.entry_gate(tmp_path, binding(job), NOW, requested_output=tmp_path / "out")
    assert observed["kernel"]["CPU_affinity"] == [0]
    assert 0 < observed["kernel"]["memory_max_bytes"] <= 400 * 1024**2
    assert observed["kernel"]["available_KiB"] >= 500 * 1024
    # This metadata fixture passes its local gate, but the actual active authority is
    # deliberately absent and cannot create a client or become paper readiness.
    value["code_bindings"] = codes[:-1]
    job.write_text(json.dumps(value))
    with pytest.raises(ValueError):
        entry.entry_gate(tmp_path, binding(job), NOW, requested_output=tmp_path / "out")


def test_cleanup_has_separate_owned_exit_identity_and_no_normal_wave_bypass(gateway):
    _, journal, gw, args, calls, current, _ = gateway
    # Explicit controlled kill exit during RTH, separate from consumed sell intent.
    current[0] = NOW + timedelta(hours=1)
    exit_cid = CID.replace("-sell-", "-exit-")
    request = args["prepared"]
    request.update(
        client_order_id=exit_cid,
        cleanup=True,
        own_exit_allowed=True,
        killed=True,
        quote_cutoff=current[0].isoformat(),
    )
    request["quote"]["timestamp_ns"] = int(current[0].timestamp()) * 10**9
    snap = args["reservation_snapshot"]
    snap["pending"][exit_cid] = snap["pending"].pop(CID)
    snap["consumed_ids"] = [CID, exit_cid]
    args["clock"] = lambda: current[0]
    journal.dispatch_once(**args)
    assert len(calls) == 1
    with pytest.raises(FileExistsError):
        journal.dispatch_once(**args)
    assert len(calls) == 1


def test_exit_identity_cannot_be_used_as_normal_wave(gateway):
    _, journal, _, args, calls, _, _ = gateway
    args["prepared"]["client_order_id"] = CID.replace("-sell-", "-exit-")
    with pytest.raises(ValueError, match="identity"):
        journal.dispatch_once(**args)
    assert not calls


@pytest.mark.parametrize("fault", [None, "partial", "wrong_day"])
def test_prior_reference_is_current_completed_session_packet(quantity_case, tmp_path, fault):
    from types import SimpleNamespace

    from open_composer.intraday_runner.source_initial_commit import receive_prior

    root, _, fp, _, _ = quantity_case
    symbols = json.loads(fp.read_text())["forecast"]["symbols"]
    calls = []

    def fetch(endpoint, params, timeout):
        calls.append(params)
        body = dict(
            bars={
                s: [
                    dict(t="2026-10-30T04:00:00Z", o=100, c=100, v=10),
                    dict(t="2026-11-02T05:00:00Z", o=100, c=100, v=10),
                ]
                for s in symbols
            },
            next_page_token="more" if fault == "partial" else None,
        )
        return SimpleNamespace(entity_bytes=json.dumps(body).encode(), status_code=200, headers={})

    args = dict(
        day=date(2026, 11, 3),
        symbols=symbols,
        directory=tmp_path / "prior",
        clock=lambda: NOW - timedelta(days=1) if fault == "wrong_day" else NOW,
    )
    if fault:
        with pytest.raises(ValueError):
            receive_prior(root, SimpleNamespace(fetch=fetch), **args)
        if fault == "wrong_day":
            assert not calls
    else:
        b = receive_prior(root, SimpleNamespace(fetch=fetch), **args)
        refs = json.loads(Path(b["path"]).read_text())
        assert all(
            r["session_date"] == "2026-11-02" and r["close"] == 100 and r["hygiene_valid"]
            for r in refs.values()
        )
        assert calls[0]["adjustment"] == "raw" and calls[0]["end"] == "2026-11-03T00:00:00-05:00"


@pytest.mark.parametrize("fault", [None, "unknown_units", "wrong_day", "expired", "source_drift"])
def test_current_operating_input_is_required_before_client(tmp_path, monkeypatch, fault):
    from open_composer.intraday_runner import source_method_runtime as runtime

    monkeypatch.setattr(runtime, "_require_kill_switch_clear", lambda root: None)

    def artifact(name, value):
        p = tmp_path / (name + ".json")
        p.write_text(json.dumps(value))
        return binding(p)

    source = artifact("source", {"invented": True})
    codes = [binding(Path(runtime.__file__))]
    current = dict(
        accepted=True,
        execution_units_checked=True,
        account_hash="a" * 64,
        session_date="2026-11-03",
        received_at=(NOW - timedelta(seconds=1)).isoformat(),
        valid_until=(NOW + timedelta(seconds=15)).isoformat(),
        source_bindings=[source],
    )
    if fault == "unknown_units":
        current["execution_units_checked"] = "unknown"
    if fault == "wrong_day":
        current["session_date"] = "2026-11-02"
    if fault == "expired":
        current["valid_until"] = NOW.isoformat()
    auth = dict(
        kind=runtime.KIND,
        account="quant2",
        paper_only=True,
        active=True,
        orders_permitted=True,
        allocated_usd=20000,
        policy="DIA_BASE",
        long_cash_only=True,
        daily_loss_halt=0.05,
        drawdown_kill=0.25,
        authorized_at=START.isoformat(),
        expires_at=END.isoformat(),
        account_authority_expires_at=END.isoformat(),
        account_hash="a" * 64,
        foreign_positions={},
        universe=["AAPL"],
        code_bindings=codes,
        bindings=dict(
            account_scope=artifact(
                "account",
                dict(
                    status="accepted_account_sleeve_scope",
                    account_hash="a" * 64,
                    capital_usd=20000,
                    foreign_positions={},
                    scope_conflicts_verified=True,
                ),
            ),
            spec=artifact("spec", {}),
            scientific_contract=artifact("contract", dict(output_identity=["AAPL"])),
            source_acceptance=artifact("sip", dict(current_SIP_verified=True, feed="sip")),
            current_operating_input=artifact("current", current),
            implementation_review=artifact("review", {}),
            native_acceptance=artifact(
                "native", dict(accepted=True, scope=runtime.KIND, code_bindings=codes)
            ),
        ),
    )
    packet = artifact("authority", auth)
    if fault == "source_drift":
        Path(source["path"]).write_text("{}")
    if fault:
        with pytest.raises(ValueError):
            runtime.load_scope(tmp_path, packet, NOW)
    else:
        assert runtime.load_scope(tmp_path, packet, NOW) == auth


def test_repair_cash_expected_authority_digest_before_client(cash_auth):
    root, auth = cash_auth
    p = root / "auth.json"
    p.write_text(json.dumps(auth))
    expected = binding(p)
    p.write_text(json.dumps(dict(auth, harmless_but_unbound_change=True)))
    called = []
    with pytest.raises(ValueError, match="hash"):
        c.observe(
            root,
            p,
            root / "state",
            root / "out.json",
            expected_authority_binding=expected,
            client_factory=lambda: called.append(1),
            clock=lambda: NOW,
        )
    assert not called


def test_repair_cash_scope_rechecked_at_each_actual_get(monkeypatch):
    client = type("Client", (), {})()
    client._session = requests.Session()
    client._retry = 3
    calls = []
    allowed = [True]
    client._session.request = lambda *a, **k: calls.append(a)
    monkeypatch.setattr(c, "make_trading_client", lambda account: client)
    monkeypatch.setattr(c, "_require_verified_paper_client", lambda client: None)

    def guard():
        if not allowed[0]:
            raise ValueError("expired/changed scope after SDK latency")

    guarded = c._read_only_client(read_guard=guard)
    guarded._session.request("GET", "https://paper-api.alpaca.markets/v2/account")
    allowed[0] = False
    with pytest.raises(ValueError):
        guarded._session.request("GET", "https://paper-api.alpaca.markets/v2/positions")
    assert len(calls) == 1


def test_repair_full_get_expiry_and_scope_at_final_boundary(gateway):
    client, _, gw, _, calls, current, _ = gateway
    current[0] = END
    with pytest.raises(ValueError, match="expired"):
        client._session.request("GET", "https://paper-api.alpaca.markets/v2/account")
    assert not calls
    current[0] = NOW

    def deny():
        raise ValueError("changed read scope")

    gw.read_guard = deny
    with pytest.raises(ValueError, match="scope"):
        client._session.request("GET", "https://paper-api.alpaca.markets/v2/account")
    assert not calls


@pytest.mark.parametrize(
    "age,expected",
    [(0, True), (4_999_999_999, True), (5_000_000_000, True), (5_000_000_001, False), (-1, False)],
)
def test_repair_held_nanoseconds_exact(age, expected):
    from open_composer.intraday_runner.source_account_observation import held_quote_fresh

    now = NOW.replace(microsecond=2)
    exact = int(now.timestamp()) * 10**9 + 2000
    assert held_quote_fresh(exact - age, now) is expected


@pytest.mark.parametrize("fault", ["deadline", "scope", None])
def test_repair_source_pacing_rechecks_absolute_deadline_and_grant(tmp_path, monkeypatch, fault):
    from types import SimpleNamespace

    from open_composer.intraday_runner import source_input_transport as source

    ticks = [10.1]
    allowed = [True]
    calls = []

    def sleep(delay):
        ticks[0] += delay
        if fault == "scope":
            allowed[0] = False

    monkeypatch.setattr(source, "time", SimpleNamespace(monotonic=lambda: ticks[0], sleep=sleep))

    def guard():
        if not allowed[0]:
            raise ValueError("source scope changed during pacing")

    transport = source.ExistingSourceTransport(
        tmp_path,
        {},
        allowed_ciks=set(),
        read_guard=guard,
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    transport.last = 10.0
    transport.data = SimpleNamespace(
        session=SimpleNamespace(
            get=lambda *a, **k: (
                calls.append((a, k)) or SimpleNamespace(content=b"{}", status_code=200, headers={})
            )
        )
    )
    args = ("https://data.alpaca.markets/v2/stocks/bars", {}, 0.1 if fault == "deadline" else 1.0)
    if fault:
        with pytest.raises(ValueError):
            transport.fetch(*args)
        assert not calls
    else:
        assert transport.fetch(*args).status_code == 200
        assert len(calls) == 1 and 0 < calls[0][1]["timeout"] < 1


@pytest.mark.native_resource
def test_repair_bound_output_and_consumed_failure_cannot_be_retargeted(tmp_path, monkeypatch):
    import sys
    from types import SimpleNamespace

    from open_composer.intraday_runner import source_runtime_entry as entry
    from open_composer.intraday_runner import source_runtime_launcher as launcher

    codes = [binding(p) for p in sorted(Path(entry.__file__).parent.glob("source_*.py"))]
    authority = tmp_path / "authority.json"
    authority.write_text("{}")
    output = tmp_path / "owned-output"
    native = tmp_path / "native.json"
    native.write_text(
        json.dumps(
            dict(
                accepted=True,
                scope="dia_base_complete_entry_v1",
                allowed_phases=["cash"],
                code_bindings=codes,
                authority=binding(authority),
                output=str(output),
                invocation_id="fixed-invocation",
            )
        )
    )
    disk = tmp_path / "disk.json"
    disk.write_text(
        json.dumps(dict(accepted=True, invocation_id="fixed-invocation", required_free_bytes=65536))
    )
    now = datetime.now(UTC)
    job = tmp_path / "job.json"
    job.write_text(
        json.dumps(
            dict(
                active=True,
                phase="cash",
                not_before=(now - timedelta(minutes=1)).isoformat(),
                expires_at=(now + timedelta(minutes=1)).isoformat(),
                native_acceptance=binding(native),
                authority=binding(authority),
                code_bindings=codes,
                invocation_id="fixed-invocation",
                output=str(output),
                disk_admission=binding(disk),
                timeout_seconds=10,
            )
        )
    )
    pointer = tmp_path / "binding.json"
    pointer.write_text(json.dumps(binding(job)))
    argv = [
        "launcher",
        "--root",
        str(tmp_path),
        "--job-binding",
        str(pointer),
        "--output",
        str(output),
    ]
    called = []
    monkeypatch.setattr(
        launcher.subprocess,
        "run",
        lambda *a, **k: called.append(a) or SimpleNamespace(returncode=7),
    )
    monkeypatch.setattr(sys, "argv", argv)
    with pytest.raises(SystemExit) as exc:
        launcher.main()
    assert exc.value.code == 7 and len(called) == 1
    with pytest.raises(FileExistsError):
        launcher.main()
    monkeypatch.setattr(sys, "argv", argv[:-1] + [str(tmp_path / "different-output")])
    with pytest.raises(ValueError, match="identity"):
        launcher.main()
    assert len(called) == 1
    assert json.loads(output.with_suffix(".completion.json").read_text())["exit_code"] == 7
    # Digest change is rejected even if native path and all other metadata remain.
    authority.write_text('{"changed":true}')
    with pytest.raises(ValueError, match="hash"):
        entry.entry_gate(tmp_path, binding(job), now, requested_output=output)


@pytest.mark.parametrize(
    "fault", [None, "attempted", "marker", "dangling_marker", "filled", "old_without_witness"]
)
def test_repair_positive_local_abandonment_preserves_unknown_attempts(funded_sales, fault):
    from types import SimpleNamespace

    from open_composer.intraday_runner.source_method_runtime import SourceMethodRuntime
    from open_composer.intraday_runner.source_terminal_holds import abandon_never_attempted

    root, state, store = funded_sales
    cid = "dia-base-2026-11-03-buy-MSFT"
    state.reserve_buy(cid, "MSFT", 3, 5, 0, "2026-11-03", "2026-11-04")
    journal = SourceDispatchJournal(store.directory.parent / "journal")
    runtime = SimpleNamespace(journal=journal)
    evidence = {}
    SourceMethodRuntime._record_intents(runtime, state, evidence, [dict(client_order_id=cid)])
    before = copy.deepcopy(state)
    if fault == "attempted":
        evidence["dispatch_intents"][cid]["attempted"] = True
    if fault == "marker":
        journal._path(cid).write_text("")
    if fault == "dangling_marker":
        journal._path(cid).symlink_to("absent-file")
    if fault == "filled":
        state.pending[cid]["filled"] = 1
    if fault == "old_without_witness":
        evidence = {}
    if fault:
        with pytest.raises(ValueError):
            abandon_never_attempted(
                state, {}, {}, evidence, cid=cid, journal=journal, observed_at=NOW.isoformat()
            )
        assert cid in state.pending
    else:
        got, audit = abandon_never_attempted(
            state, {}, {}, evidence, cid=cid, journal=journal, observed_at=NOW.isoformat()
        )
        assert got.cashbook == before.cashbook and got.cash_reserved() == 0
        assert cid in got.consumed_ids and cid not in got.pending
        assert audit["abandoned_local_intents"][cid]["broker_terminal_claim"] is False
        assert before.cash_reserved() == 15


@pytest.mark.parametrize("fail_publication", [False, True])
def test_repair_attempt_witness_is_durable_before_callback(
    funded_sales, monkeypatch, fail_publication
):
    from types import SimpleNamespace

    from open_composer.intraday_runner.source_dispatch_journal import _hash
    from open_composer.intraday_runner.source_method_runtime import SourceMethodRuntime
    from open_composer.intraday_runner.source_state_checkpoint import restore, snapshot
    from open_composer.intraday_runner.source_terminal_holds import abandon_never_attempted

    root, state, store = funded_sales
    cid = "dia-base-2026-11-03-buy-MSFT"
    state.reserve_buy(cid, "MSFT", 3, 5, 0, "2026-11-03", "2026-11-04")
    journal = SourceDispatchJournal(store.directory.parent / "journal")
    runtime = SimpleNamespace(root=root, store=store, journal=journal, current={})
    evidence = {}
    SourceMethodRuntime._record_intents(runtime, state, evidence, [{"client_order_id": cid}])
    before = store.commit(snapshot(state, {}, {}, evidence=evidence), expected_head_sha256=None)
    if fail_publication:

        def fail(*a):
            raise OSError("injected before publication")

        monkeypatch.setattr(store, "_publish", fail)
        with pytest.raises(OSError):
            SourceMethodRuntime._mark_attempt(runtime, cid)
        assert not journal._path(cid).exists()
        with pytest.raises(ValueError):
            store.load()  # Unknown/orphan is never an absence proof.
    else:
        after = SourceMethodRuntime._mark_attempt(runtime, cid)
        assert after["generation"] == before["generation"] + 1 and runtime.current["head"] == _hash(
            after
        )
        got, fills, fees, e = restore(root, after["snapshot"])
        assert e["dispatch_intents"][cid]["attempted"] is True
        with pytest.raises(ValueError):
            abandon_never_attempted(
                got, fills, fees, e, cid=cid, journal=journal, observed_at=NOW.isoformat()
            )


def test_repair_source_utc_expiry_after_pacing(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from open_composer.intraday_runner import source_input_transport as source

    ticks = [10.1]
    base = datetime(2026, 11, 3, 14, 35, tzinfo=UTC)
    calls = []

    class Clock:
        @staticmethod
        def now(tz):
            return base + timedelta(seconds=ticks[0] - 10)

    monkeypatch.setattr(source, "datetime", Clock)
    monkeypatch.setattr(
        source,
        "time",
        SimpleNamespace(
            monotonic=lambda: ticks[0], sleep=lambda delay: ticks.__setitem__(0, ticks[0] + delay)
        ),
    )
    t = source.ExistingSourceTransport(
        tmp_path,
        {},
        allowed_ciks=set(),
        read_guard=lambda: None,
        expires_at=base + timedelta(seconds=0.2),
    )
    t.last = 10.0
    t.data = SimpleNamespace(session=SimpleNamespace(get=lambda *a, **k: calls.append(1)))
    with pytest.raises(ValueError, match="expired"):
        t.fetch("https://data.alpaca.markets/v2/stocks/bars", {}, 1)
    assert not calls
