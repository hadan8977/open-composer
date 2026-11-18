"""Account coverage must not turn old/modelled records into current profit."""

import json
from datetime import UTC, datetime

from open_composer.cockpit.data.paper_books import (
    latest_completed_session,
    load_account_books,
    load_intraday_configurations,
)

NOW = datetime(2026, 10, 20, 7, tzinfo=UTC)


def write_book(root, account="quant1", day="2026-10-16", submitted=True, **changes):
    base = root / "reports/paper/book" / account
    (base / "daily").mkdir(parents=True)
    data = {
        "account": account,
        "book_id": "example:F1",
        "execution_date": day,
        "generated_at_utc": day + "T22:40:00Z",
        "plan_sha256": "plan-proof",
        "pnl": {"equity": 1020000, "net_pnl": 5000, "net_return": 0.005},
        "reconciliation": {
            "n_orders": 3,
            "n_filled": 3 if submitted else 0,
            "n_missing": 0,
            "n_position_drift_names": 0,
            "n_submission_rejected": 0,
        },
    }
    data.update(changes)
    (base / "daily" / f"{day}.json").write_text(json.dumps(data))
    (base / "plans").mkdir()
    (base / "plans" / f"{day}.json").write_text(
        json.dumps(
            {
                "plan_sha256": "plan-proof",
                "post_trade_qty": {"SPY": 2, "QQQ": 0, "IBM": -1},
            }
        )
    )
    if submitted:
        (base / "orders").mkdir()
        (base / "orders" / f"{day}.json").write_text("{}")
    return base


def test_f1_is_discovered_without_any_rehearsal_or_projection(tmp_path):
    write_book(tmp_path)
    (row,) = load_account_books(tmp_path, now=NOW)
    assert row.account == "quant1" and row.book_id == "example:F1"
    assert row.status == "stale"
    assert row.market_as_of.isoformat() == "2026-10-16"
    assert row.expected_session.isoformat() == "2026-10-19"
    assert row.equity_usd == 1020000 and row.position_count == 2
    assert row.net_pnl_usd is None  # Old net_pnl is a model-cost view, not certified profit.


def test_latest_valid_account_ledger_is_current_without_calling_it_running(tmp_path):
    write_book(tmp_path, day="2026-10-19")
    (row,) = load_account_books(tmp_path, now=NOW)
    assert row.status == "current" and row.filled == 3


def test_never_submitted_book_is_visible_as_observation(tmp_path):
    write_book(tmp_path, account="quant2", submitted=False)
    (row,) = load_account_books(tmp_path, now=NOW)
    assert row.account == "quant2" and row.status == "observation_only"


def test_wrong_account_or_future_ledger_does_not_supply_an_equity(tmp_path):
    base = write_book(tmp_path, account="quant1", day="2026-10-20")
    (row,) = load_account_books(tmp_path, now=NOW)
    assert row.status == "needs_attention" and row.equity_usd is None
    path = base / "daily/2026-10-20.json"
    data = json.loads(path.read_text())
    data["account"] = "wrong-account"
    path.write_text(json.dumps(data))
    (row,) = load_account_books(tmp_path, now=NOW)
    assert row.equity_usd is None and row.warnings


def test_market_close_weekend_and_early_close_dates():
    assert (
        latest_completed_session(datetime(2026, 10, 19, 13, tzinfo=UTC)).isoformat() == "2026-10-16"
    )
    assert (
        latest_completed_session(datetime(2026, 10, 19, 21, tzinfo=UTC)).isoformat() == "2026-10-19"
    )
    assert (
        latest_completed_session(datetime(2026, 10, 18, 21, tzinfo=UTC)).isoformat() == "2026-10-16"
    )
    assert (
        latest_completed_session(datetime(2026, 11, 27, 19, tzinfo=UTC)).isoformat() == "2026-11-27"
    )


def test_intraday_configuration_is_not_evidence_of_operation(tmp_path):
    directory = tmp_path / "config/intraday"
    directory.mkdir(parents=True)
    (directory / "runner-quant2.yaml").write_text(
        "account: quant2\nstrategies:\n  - name: noiseband_qqq_obs\n    symbols: [QQQ]\n"
    )
    (directory / "runner-dryrun.yaml").write_text(
        "account: fixture\nstrategies:\n  - name: fixture\n"
    )
    (row,) = load_intraday_configurations(tmp_path)
    assert row.name == "noiseband_qqq_obs" and row.status == "configuration_only"


def test_missing_reconciliation_and_plan_proof_are_not_healthy_records(tmp_path):
    base = write_book(
        tmp_path,
        day="2026-10-19",
        reconciliation={
            "n_orders": 3,
            "n_filled": 2,
            "n_missing": 1,
            "n_position_drift_names": 1,
        },
    )
    (row,) = load_account_books(tmp_path, now=NOW)
    assert row.status == "needs_attention" and row.position_count is None
    assert any("missing" in w for w in row.warnings)
    (base / "daily/2026-10-19.json").write_text("{partial atomic write")
    (row,) = load_account_books(tmp_path, now=NOW)
    assert row.equity_usd is None and row.warnings
