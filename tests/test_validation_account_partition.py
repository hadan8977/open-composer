"""Invented shared-account ownership/funding boundaries, with no broker calls."""

import copy
import json
from decimal import Decimal
from pathlib import Path

import pytest

from open_composer.intraday_runner.validation_account_partition import (
    BASE,
    H5,
)
from open_composer.intraday_runner.validation_account_partition import (
    ValidationAccountPartition as Partition,
)


def book(namespace, symbol, qty, cash):
    return dict(
        revision=namespace + "-head",
        namespace=namespace,
        snapshot=dict(
            cashbook=dict(
                cash=cash,
                lots={symbol: [dict(quantity=qty, funded="2026-10-19")]} if qty else {},
                sales=[],
                purchases=[],
                dividends=[],
                next_id=0,
            ),
            pending={},
            consumed_ids=[],
            fills={},
            fees={},
            evidence=dict(allocated_capital="10000", account_initial_cash="1000000"),
        ),
    )


def books():
    return {BASE: book("base", "SPY", 3, 8500), H5: book("h5", "SPY", 7, 6500)}


def positions(qty="10"):
    return [
        dict(
            symbol="SPY",
            qty=qty,
            side="long",
            current_price="500",
            market_value=str(Decimal(qty) * 500),
        )
    ]


def test_overlap_owned_units_and_denominators_are_separate():
    state = books()
    before = copy.deepcopy(state)
    b = Partition.account_view(state, BASE, positions(), {}, [])
    second = Partition.account_view(state, H5, positions(), {}, [])
    assert b["units_complete"] and second["units_complete"]
    assert b["holdings"][0]["quantity"] == 3
    assert second["holdings"][0]["quantity"] == 7
    assert b["holdings"][0]["market_value"] == "1500"
    assert second["holdings"][0]["market_value"] == "3500"
    assert b["totals"]["allocated"] == 20000
    assert state == before


def test_missing_extra_or_short_units_cannot_be_empty_success():
    assert not Partition.account_view(books(), BASE, [], {}, [])["units_complete"]
    assert not Partition.account_view(books(), BASE, positions("11"), {}, [])["units_complete"]
    bad = positions()
    bad[0]["side"] = "short"
    with pytest.raises(ValueError):
        Partition.account_view(books(), BASE, bad, {}, [])


def test_foreign_order_and_cross_book_duplicate_refuse():
    state = books()
    with pytest.raises(ValueError, match="unregistered"):
        Partition.account_view(state, BASE, positions(), {"foreign": dict(id="x")}, [])
    for b in state.values():
        b["snapshot"]["consumed_ids"] = ["same"]
    with pytest.raises(ValueError, match="duplicate"):
        Partition.totals(state)


def test_fill_ownership_and_unknown_activity_are_preserved():
    state = books()
    state[BASE]["snapshot"]["consumed_ids"] = ["base-buy"]
    state[H5]["snapshot"]["consumed_ids"] = ["h5-buy"]
    orders = {"base-buy": dict(id="b"), "h5-buy": dict(id="l")}
    activities = [dict(id="bf", order_id="b"), dict(id="lf", order_id="l"), dict(id="fee")]
    view = Partition.account_view(state, BASE, positions(), orders, activities)
    assert view["own_orders"] == {"base-buy": dict(id="b")}
    assert view["own_activities"] == activities[:1]
    assert view["unassigned_activities"] == activities[2:]
    assert view["all_activities_known"] is False
    assert state[BASE]["snapshot"]["fills"] == {}


def test_conflicting_activity_owner_refuses():
    state = books()
    state[BASE]["snapshot"]["consumed_ids"] = ["base-buy"]
    state[H5]["snapshot"]["fills"] = {"fill": {}}
    with pytest.raises(ValueError, match="ownership conflict"):
        Partition.account_view(
            state, BASE, positions(), {"base-buy": dict(id="b")}, [dict(id="fill", order_id="b")]
        )


@pytest.mark.parametrize(
    "funds,gross,other_head,allowed",
    [
        (1000000, 5000, "h5-head", True),
        (399, 5000, "h5-head", False),
        (1000000, 19700, "h5-head", False),
        (1000000, 5000, "changed", False),
    ],
)
def test_combined_reservations_and_other_head(funds, gross, other_head, allowed):
    state = books()
    for b in state.values():
        b["snapshot"]["pending"] = {
            b["namespace"]: dict(
                side="buy",
                quantity=2,
                filled=0,
                limit_price=100,
                remaining_funding=[dict(source="cash", amount=200)],
            )
        }
    p = Partition.__new__(Partition)
    p.books = lambda: state
    obs = dict(
        account_marked_value=gross,
        account_unborrowed_available=funds,
        other_checkpoint_hashes={H5: other_head},
    )
    before = copy.deepcopy(state)
    if allowed:
        assert p.guard_new_risk(obs, BASE) == state
    else:
        with pytest.raises(ValueError):
            p.guard_new_risk(obs, BASE)
    assert state == before


def test_single_registered_sleeve_does_not_inherit_idle_ten_thousand():
    state = {BASE: book("base", "SPY", 0, 10000)}
    view = Partition.account_view(state, BASE, [], {}, [])
    assert view["totals"]["allocated"] == 10000
    assert view["totals"]["net_cash"] == 10000
    assert state[BASE]["snapshot"]["cashbook"]["cash"] == 10000


def test_actual_local_registration_two_books_orphan_and_binding_drift(tmp_path):
    from open_composer.intraday_runner.source_activity_reception import bind
    from open_composer.intraday_runner.source_method_bindings import source_module
    from open_composer.intraday_runner.source_reservations import SourceReservations
    from open_composer.intraday_runner.source_state_checkpoint import (
        SourceStateCheckpoint,
        snapshot,
    )
    from open_composer.intraday_runner.validation_account_partition import ACCOUNT, slot

    main = tmp_path / "main.json"
    scope = tmp_path / "scope.json"
    scope.write_text(json.dumps(dict(owner_account_scope_bound=True, account_hash=ACCOUNT)))
    main.write_text(
        json.dumps(
            dict(
                selected_task=H5,
                owner_instruction=bind(scope),
                capital=dict(
                    combined_max_USD=20000,
                    BASE_USD=10000,
                    H5_swing_USD=10000,
                    LSTM_USD=0,
                    gross_max=1,
                    no_inter_sleeve_transfer_or_borrowed_idleallocation=True,
                    same_verified_isolated_account=True,
                    long_cash_only=True,
                ),
            )
        )
    )
    partition = Partition(tmp_path, bind(main))
    with pytest.raises(ValueError, match="lock absent"):
        partition.books()
    with partition.locked():
        assert partition.books() == {}
        for task in (BASE, H5):
            directory, namespace = slot(tmp_path, task)
            auth = tmp_path / (task + ".json")
            auth.write_text(
                json.dumps(
                    dict(
                        task_id=task,
                        account_hash=ACCOUNT,
                        capital_usd=10000,
                        namespace=namespace,
                        ledger_root=str(directory),
                        partition=bind(main),
                    )
                )
            )
            partition.register(task, bind(auth))
            with pytest.raises(ValueError, match="no complete checkpoint"):
                partition.books()
            cash = source_module(Path("/root/codex-test/open-composer"), "cash").CashState(
                cash=10000
            )
            state = SourceReservations(cash)
            store = SourceStateCheckpoint(
                directory / "checkpoints", account_hash=ACCOUNT, sleeve_id=task
            )
            store.commit(
                snapshot(
                    state,
                    {},
                    {},
                    evidence=dict(allocated_capital="10000", account_initial_cash="1000000"),
                ),
                expected_head_sha256=None,
            )
        complete = partition.books()
        assert set(complete) == {BASE, H5}
        assert partition.totals(complete)["net_cash"] == 20000
        auth.write_text(auth.read_text() + " ")
        with pytest.raises(ValueError, match="hash changed"):
            partition.books()


def test_unregistered_existing_checkpoint_is_never_inferred_empty(tmp_path):
    from open_composer.intraday_runner.validation_account_partition import slot

    p = Partition.__new__(Partition)
    from open_composer.intraday_runner.source_activity_reception import save

    owner = save(tmp_path / "owner.json", {"invented": True})
    partition = save(
        tmp_path / "partition.json",
        dict(
            selected_task=H5,
            owner_instruction=owner,
            capital=dict(
                BASE_USD=10000,
                H5_swing_USD=10000,
                LSTM_USD=0,
                combined_max_USD=20000,
                gross_max=1,
                long_cash_only=True,
                same_verified_isolated_account=True,
                no_inter_sleeve_transfer_or_borrowed_idleallocation=True,
            ),
        ),
    )
    p.root, p.binding, p.directory, p.held = tmp_path, partition, tmp_path / "registry", True
    directory, _ = slot(tmp_path, BASE)
    (directory / "checkpoints").mkdir(parents=True)
    with pytest.raises(ValueError, match="orphan"):
        p.books()
