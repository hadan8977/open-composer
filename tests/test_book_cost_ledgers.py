import json

import pytest

from open_composer.book_paper.cost_ledgers import profit_ledgers
from open_composer.reports.owner_digest import collect_book

SHADOW = {"impact": 1.0, "fees": 3.0, "borrow": 4.0, "half_spread": 20.0, "total": 28.0}


def test_unknown_flow_and_fee_do_not_certify_incremental_net():
    out = profit_ledgers(1100, 1000, SHADOW)
    assert out["broker_paper"]["equity_delta"] == 100
    assert out["broker_paper"]["flow_adjusted_pnl"] is None
    assert out["broker_plus_incremental_model"]["net_pnl"] is None
    assert out["legacy_full_shadow"]["net_pnl"] == 72
    assert out["historical_simulation"] is None


def test_transfer_and_already_booked_fee_are_not_profit_or_double_cost():
    out = profit_ledgers(
        1100,
        1000,
        SHADOW,
        external_net_flow=50,
        fees_already_in_equity=2,
        holdings_valuation_complete=True,
        borrow_already_in_equity=0,
        impact_already_in_equity=0,
    )
    assert out["broker_paper"]["flow_adjusted_pnl"] == 50
    adj = out["broker_plus_incremental_model"]
    assert adj["fee_topup_to_model"] == 1
    assert adj["incremental_cost"] == 6
    assert adj["additional_full_spread"] == 0
    assert adj["net_pnl"] == 44


def test_actual_fee_above_model_never_creates_a_rebate():
    adj = profit_ledgers(
        1100,
        1000,
        SHADOW,
        external_net_flow=0,
        fees_already_in_equity=5,
        holdings_valuation_complete=True,
        borrow_already_in_equity=0,
        impact_already_in_equity=0,
    )["broker_plus_incremental_model"]
    assert adj["fee_topup_to_model"] == 0
    assert adj["net_pnl"] == 95


def test_missing_held_mark_keeps_adjusted_net_unknown():
    out = profit_ledgers(
        1100,
        1000,
        SHADOW,
        external_net_flow=0,
        fees_already_in_equity=0,
        borrow_already_in_equity=0,
        impact_already_in_equity=0,
    )
    assert out["broker_plus_incremental_model"]["net_pnl"] is None


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), -1])
def test_invalid_expense_is_rejected(bad):
    with pytest.raises(ValueError):
        profit_ledgers(1100, 1000, {**SHADOW, "fees": bad})


def test_report_does_not_label_legacy_full_spread_stress_as_incremental_net(tmp_path):
    base = tmp_path / "reports/paper/book/quant1/daily"
    base.mkdir(parents=True)
    p = base / "2026-10-16.json"
    record = {
        "pnl": {
            "equity": 1100,
            "last_equity": 1000,
            "gross_pnl_broker": 100,
            "net_pnl": 72,
            "net_return": 0.072,
        }
    }
    p.write_text(json.dumps(record))
    account = next(a for a in collect_book(tmp_path) if a.account == "quant1")
    assert account.net_pnl == 100
    assert "券商权益变动" in account.pnl_basis
    assert "未核齐" in account.pnl_basis
    assert json.loads(p.read_text()) == record


def test_report_selects_only_explicit_complete_incremental_ledger(tmp_path):
    base = tmp_path / "reports/paper/book/quant1/daily"
    base.mkdir(parents=True)
    ledgers = profit_ledgers(
        1100,
        1000,
        SHADOW,
        external_net_flow=50,
        fees_already_in_equity=2,
        holdings_valuation_complete=True,
        borrow_already_in_equity=0,
        impact_already_in_equity=0,
    )
    (base / "2026-10-16.json").write_text(
        json.dumps(
            {
                "pnl": {"last_equity": 1000, "gross_pnl_broker": 100},
                "profit_ledgers": ledgers,
            }
        )
    )
    account = next(a for a in collect_book(tmp_path) if a.account == "quant1")
    assert account.net_pnl == 44
    assert account.net_return == 0.044
    assert "增量模型" in account.pnl_basis


def test_unknown_borrow_overlap_cannot_be_treated_as_zero():
    out = profit_ledgers(
        1100,
        1000,
        SHADOW,
        external_net_flow=0,
        fees_already_in_equity=0,
        holdings_valuation_complete=True,
        impact_already_in_equity=0,
    )
    assert out["broker_plus_incremental_model"]["net_pnl"] is None


def test_already_included_borrow_and_impact_are_not_charged_again():
    adj = profit_ledgers(
        1100,
        1000,
        SHADOW,
        external_net_flow=0,
        fees_already_in_equity=3,
        holdings_valuation_complete=True,
        borrow_already_in_equity=5,
        impact_already_in_equity=1,
    )["broker_plus_incremental_model"]
    assert adj["complete"] is True
    assert adj["incremental_cost"] == 0
    assert adj["net_pnl"] == 100
