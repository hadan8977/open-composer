from __future__ import annotations

from datetime import UTC, date, datetime

import pandas as pd
import pytest
from pydantic import ValidationError

from open_composer.research.corporate_action_reconciliation import (
    CorporateActionEvent,
    reconcile_corporate_action_panels,
    reject_unsupported_corporate_action_groups,
)

ASOF = datetime(2026, 1, 10, tzinfo=UTC)
SOURCE_HASH = "a" * 64


def test_split_and_dividend_reconciliation_builds_local_indices_and_cash_ledger() -> None:
    raw = _panel([100.0, 51.0, 50.0, 52.0])
    split = _split_event()
    dividend = _dividend_event()
    expected = {
        "split": _panel([1.0, 1.02, 1.0, 1.04]),
        "dividend": _panel([1.0, 0.51, 0.51, 0.5304]),
    }
    provider = {
        "split": expected["split"] * 7,
        "dividend": expected["dividend"] * 11,
        "all": _panel([13.0, 15.0, 14.0, 16.0]),
    }

    result = reconcile_corporate_action_panels(
        raw,
        provider,
        [split, dividend],
        asof=ASOF,
        currency="USD",
        tolerance_bps=0.000001,
    )

    for mode, expected_frame in expected.items():
        pd.testing.assert_frame_equal(result.local_indices[mode], expected_frame, check_freq=False)
    assert result.report["status"] == "ok"
    assert result.report["raw_prices_used_for_execution"] is True
    assert result.report["provider_adjusted_panels_used_for_reconciliation_only"] is True
    assert result.report["maximum_residual_bps"] == {
        "split": pytest.approx(0.0, abs=1e-9),
        "dividend": pytest.approx(0.0, abs=1e-9),
    }
    assert result.report["all_panel_accounting_status"] == "provider_only_not_locally_reproduced"
    assert result.report["all_equals_split_plus_dividend"] is False
    assert result.report["pit_visibility_proven"] is False
    assert result.report["process_date_used_as_visible_at"] is False
    assert result.report["verdict"] == "historical_reconciliation_only_not_pit_proof"
    assert "all" not in result.local_indices

    ledger = result.wealth_ledger.set_index(["session", "symbol"])
    split_day = ledger.loc[("2026-01-05", "SPY")]
    ex_day = ledger.loc[("2026-01-06", "SPY")]
    pay_day = ledger.loc[("2026-01-07", "SPY")]
    assert split_day["shares"] == pytest.approx(2.0)
    assert split_day["nav"] == pytest.approx(102.0)
    assert ex_day["dividend_receivable"] == pytest.approx(2.0)
    assert ex_day["cash"] == pytest.approx(0.0)
    assert ex_day["nav"] == pytest.approx(102.0)
    assert pay_day["dividend_receivable"] == pytest.approx(0.0)
    assert pay_day["cash"] == pytest.approx(2.0)
    assert pay_day["nav"] == pytest.approx(106.0)


def test_reverse_split_uses_new_over_old_share_multiplier() -> None:
    raw = _panel([10.0, 102.0, 103.0])
    event = CorporateActionEvent(
        event_id="reverse-1",
        action_type="reverse_split",
        symbol="SPY",
        process_date=date(2026, 1, 5),
        ex_date=date(2026, 1, 5),
        old_rate=10.0,
        new_rate=1.0,
        source="alpaca_corporate_actions",
        source_payload_sha256=SOURCE_HASH,
        retrieved_at=ASOF,
        asof=ASOF,
    )
    local_split = _panel([1.0, 1.02, 1.03])
    local_dividend = _panel([1.0, 10.2, 10.3])
    provider = {
        "split": local_split,
        "dividend": local_dividend,
        "all": local_split,
    }

    result = reconcile_corporate_action_panels(
        raw,
        provider,
        [event],
        asof=ASOF,
        currency="USD",
    )

    assert result.local_indices["split"].iloc[-1, 0] == pytest.approx(1.03)
    ledger = result.wealth_ledger.set_index(["session", "symbol"])
    assert ledger.loc[("2026-01-05", "SPY"), "shares"] == pytest.approx(0.1)
    assert ledger.loc[("2026-01-05", "SPY"), "nav"] == pytest.approx(10.2)


def test_provider_adjustment_residual_fails_closed() -> None:
    raw = _panel([100.0, 51.0, 50.0, 52.0])
    provider = {
        "split": _panel([1.0, 1.02, 1.0, 1.04]),
        "dividend": _panel([1.0, 0.51, 0.51, 0.5304]),
        "all": _panel([1.0, 1.02, 1.01, 1.0608]),
    }
    provider["dividend"].iloc[-1, 0] = 0.6

    with pytest.raises(ValueError, match="residual exceeds tolerance"):
        reconcile_corporate_action_panels(
            raw,
            provider,
            [_split_event(), _dividend_event()],
            asof=ASOF,
            currency="USD",
            tolerance_bps=1.0,
        )


def test_mixed_same_session_actions_fail_closed() -> None:
    raw = _panel([100.0, 51.0, 50.0, 52.0])
    dividend = _dividend_event().model_copy(update={"ex_date": date(2026, 1, 5)})
    provider = {mode: raw.copy() for mode in ("split", "dividend", "all")}

    with pytest.raises(ValueError, match="same-session corporate actions are ambiguous"):
        reconcile_corporate_action_panels(
            raw,
            provider,
            [_split_event(), dividend],
            asof=ASOF,
            currency="USD",
        )


def test_duplicate_event_revision_and_asof_mismatch_fail_closed() -> None:
    raw = _panel([100.0, 51.0, 50.0, 52.0])
    provider = {mode: raw.copy() for mode in ("split", "dividend", "all")}
    revised = _split_event().model_copy(update={"new_rate": 3.0})
    with pytest.raises(ValueError, match="revision detected"):
        reconcile_corporate_action_panels(
            raw,
            provider,
            [_split_event(), revised],
            asof=ASOF,
            currency="USD",
        )

    earlier = datetime(2026, 1, 9, tzinfo=UTC)
    mismatched = _split_event().model_copy(update={"retrieved_at": earlier, "asof": earlier})
    with pytest.raises(ValueError, match="event asof differs"):
        reconcile_corporate_action_panels(
            raw,
            provider,
            [mismatched],
            asof=ASOF,
            currency="USD",
        )


def test_unknown_or_foreign_dividend_currency_is_rejected() -> None:
    common = {
        "event_id": "dividend-1",
        "action_type": "cash_dividend",
        "symbol": "SPY",
        "process_date": date(2026, 1, 6),
        "ex_date": date(2026, 1, 6),
        "payable_date": date(2026, 1, 7),
        "cash_rate": 1.0,
        "source": "alpaca_corporate_actions",
        "source_payload_sha256": SOURCE_HASH,
        "retrieved_at": ASOF,
        "asof": ASOF,
    }
    with pytest.raises(ValidationError, match="positive explicit USD non-foreign"):
        CorporateActionEvent(**common, currency=None, foreign=False)
    with pytest.raises(ValidationError, match="positive explicit USD non-foreign"):
        CorporateActionEvent(**common, currency="", foreign=False)
    with pytest.raises(ValidationError, match="positive explicit USD non-foreign"):
        CorporateActionEvent(**common, currency="USD", foreign=True)
    with pytest.raises(ValueError, match="explicit USD only"):
        reconcile_corporate_action_panels(
            _panel([100.0, 101.0]),
            {mode: _panel([1.0, 1.01]) for mode in ("split", "dividend", "all")},
            [],
            asof=ASOF,
            currency="EUR",
        )


@pytest.mark.parametrize(
    "group",
    [
        "unit_splits",
        "stock_dividends",
        "spin_offs",
        "cash_mergers",
        "stock_mergers",
        "stock_and_cash_mergers",
        "redemptions",
        "name_changes",
        "worthless_removals",
        "rights_distributions",
        "partial_calls",
        "reorganizations",
    ],
)
def test_unsupported_corporate_action_groups_fail_closed(group: str) -> None:
    with pytest.raises(ValueError, match="unsupported corporate action present"):
        reject_unsupported_corporate_action_groups({group: [{"id": "unsupported"}]})


def test_action_group_contract_rejects_unknown_shape_subtypes_and_due_bills() -> None:
    reject_unsupported_corporate_action_groups(
        {
            "forward_splits": [],
            "reverse_splits": [],
            "cash_dividends": [{"id": "ordinary"}],
        }
    )
    with pytest.raises(ValueError, match="unknown corporate action response group"):
        reject_unsupported_corporate_action_groups({"other_actions": []})
    with pytest.raises(ValueError, match="must be an array"):
        reject_unsupported_corporate_action_groups({"cash_dividends": {}})
    with pytest.raises(ValueError, match="unsupported cash-dividend subtype"):
        reject_unsupported_corporate_action_groups(
            {"cash_dividends": [{"sub_type": "return_of_capital"}]}
        )
    with pytest.raises(ValueError, match="unsupported cash-dividend due-bill"):
        reject_unsupported_corporate_action_groups(
            {"cash_dividends": [{"due_bill_on_date": "2026-01-05"}]}
        )


def test_event_ledger_marks_visibility_unverified_and_process_date_is_not_visibility() -> None:
    raw = _panel([100.0, 51.0])
    provider = {
        "split": _panel([1.0, 1.02]),
        "dividend": _panel([1.0, 0.51]),
        "all": _panel([1.0, 9.0]),
    }

    result = reconcile_corporate_action_panels(
        raw,
        provider,
        [_split_event()],
        asof=ASOF,
        currency="USD",
    )

    assert result.event_ledger[0]["pit_visibility_status"] == "unverified"
    assert result.report["asof_semantics"].endswith("not_provider_visibility")
    assert any("process_date" in limitation for limitation in result.report["limitations"])


def test_single_session_panel_fails_closed() -> None:
    single = _panel([100.0])
    with pytest.raises(ValueError, match="at least two sessions"):
        reconcile_corporate_action_panels(
            single,
            {mode: single.copy() for mode in ("split", "dividend", "all")},
            [],
            asof=ASOF,
            currency="USD",
        )


def _panel(values: list[float]) -> pd.DataFrame:
    sessions = pd.DatetimeIndex(
        pd.to_datetime(["2026-01-02", "2026-01-05", "2026-01-06", "2026-01-07"])[: len(values)]
    )
    return pd.DataFrame({"SPY": values}, index=sessions, dtype=float)


def _split_event() -> CorporateActionEvent:
    return CorporateActionEvent(
        event_id="split-1",
        action_type="forward_split",
        symbol="SPY",
        process_date=date(2026, 1, 5),
        ex_date=date(2026, 1, 5),
        old_rate=1.0,
        new_rate=2.0,
        source="alpaca_corporate_actions",
        source_payload_sha256=SOURCE_HASH,
        retrieved_at=ASOF,
        asof=ASOF,
    )


def _dividend_event() -> CorporateActionEvent:
    return CorporateActionEvent(
        event_id="dividend-1",
        action_type="cash_dividend",
        symbol="SPY",
        process_date=date(2026, 1, 6),
        ex_date=date(2026, 1, 6),
        record_date=date(2026, 1, 6),
        payable_date=date(2026, 1, 7),
        cash_rate=1.0,
        currency="USD",
        foreign=False,
        source="alpaca_corporate_actions",
        source_payload_sha256=SOURCE_HASH,
        retrieved_at=ASOF,
        asof=ASOF,
    )
