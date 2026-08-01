"""Historical corporate-action accounting and reconciliation, never PIT evidence."""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any, Literal

import numpy as np
import pandas as pd
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SUPPORTED_ACTION_TYPES = frozenset({"forward_split", "reverse_split", "cash_dividend"})
PROHIBITED_ACTION_TYPES = frozenset(
    {
        "unit_split",
        "stock_dividend",
        "spin_off",
        "cash_merger",
        "stock_merger",
        "stock_and_cash_merger",
        "redemption",
        "name_change",
        "worthless_removal",
        "rights_distribution",
        "partial_call",
        "reorganization",
    }
)
ACTION_GROUP_TYPES = {
    "cash_dividends": "cash_dividend",
    "cash_mergers": "cash_merger",
    "forward_splits": "forward_split",
    "name_changes": "name_change",
    "partial_calls": "partial_call",
    "redemptions": "redemption",
    "reorganizations": "reorganization",
    "reverse_splits": "reverse_split",
    "rights_distributions": "rights_distribution",
    "spin_offs": "spin_off",
    "stock_and_cash_mergers": "stock_and_cash_merger",
    "stock_dividends": "stock_dividend",
    "stock_mergers": "stock_merger",
    "unit_splits": "unit_split",
    "worthless_removals": "worthless_removal",
}
REQUIRED_PROVIDER_MODES = ("split", "dividend", "all")
LOCALLY_RECONCILABLE_MODES = ("split", "dividend")
SAFE_SYMBOL_RE = re.compile(r"^[A-Z][A-Z0-9.-]{0,14}$")


class CorporateActionEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always")

    schema_version: Literal[1] = 1
    event_id: str = Field(min_length=1)
    action_type: Literal["forward_split", "reverse_split", "cash_dividend"]
    symbol: str
    process_date: date
    ex_date: date
    record_date: date | None = None
    payable_date: date | None = None
    old_rate: float | None = None
    new_rate: float | None = None
    cash_rate: float | None = None
    currency: str | None = None
    foreign: bool | None = None
    sub_type: Literal["interest", "return_of_capital"] | None = None
    due_bill_on_date: date | None = None
    due_bill_off_date: date | None = None
    source: Literal["alpaca_corporate_actions"]
    source_payload_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    retrieved_at: datetime
    asof: datetime
    pit_visibility_status: Literal["unverified"] = "unverified"

    @field_validator("symbol")
    @classmethod
    def validate_symbol(cls, value: str) -> str:
        normalized = value.strip().upper()
        if not SAFE_SYMBOL_RE.fullmatch(normalized):
            raise ValueError("corporate-action symbol is unsafe or unsupported")
        return normalized

    @field_validator("retrieved_at", "asof")
    @classmethod
    def require_utc_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("corporate-action timestamps must include timezone")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def validate_action(self) -> CorporateActionEvent:
        if self.retrieved_at > self.asof:
            raise ValueError("corporate-action retrieval cannot be after asof")
        if self.action_type in {"forward_split", "reverse_split"}:
            if (
                not _positive_finite(self.old_rate)
                or not _positive_finite(self.new_rate)
                or self.cash_rate is not None
                or self.currency is not None
                or self.foreign is not None
                or self.sub_type is not None
                or self.due_bill_on_date is not None
                or self.due_bill_off_date is not None
            ):
                raise ValueError("split action requires only positive old/new rates")
        else:
            if (
                not _positive_finite(self.cash_rate)
                or self.old_rate is not None
                or self.new_rate is not None
                or self.currency != "USD"
                or self.foreign is not False
                or self.payable_date is None
                or self.sub_type is not None
                or self.due_bill_on_date is not None
                or self.due_bill_off_date is not None
            ):
                raise ValueError(
                    "cash dividend requires positive explicit USD non-foreign rate and payable "
                    "date without subtype or due-bill accounting"
                )
            if self.payable_date < self.ex_date:
                raise ValueError("cash-dividend payable date cannot precede ex date")
        return self

    @property
    def split_multiplier(self) -> float:
        if self.action_type not in {"forward_split", "reverse_split"}:
            return 1.0
        assert self.old_rate is not None
        assert self.new_rate is not None
        return self.new_rate / self.old_rate


@dataclass(frozen=True)
class CorporateActionReconciliation:
    local_indices: dict[str, pd.DataFrame]
    wealth_ledger: pd.DataFrame
    event_ledger: list[dict[str, Any]]
    report: dict[str, Any]


def reconcile_corporate_action_panels(
    raw_close: pd.DataFrame,
    provider_adjusted_close: dict[str, pd.DataFrame],
    events: Sequence[CorporateActionEvent],
    *,
    asof: datetime,
    currency: str,
    tolerance_bps: float = 1.0,
) -> CorporateActionReconciliation:
    observed_asof = _require_utc(asof, label="reconciliation asof")
    if currency != "USD":
        raise ValueError("corporate-action reconciliation supports explicit USD only")
    if not math.isfinite(tolerance_bps) or not 0.0 <= tolerance_bps <= 5.0:
        raise ValueError("corporate-action reconciliation tolerance must be within 0..5 bps")

    raw = _validated_close_panel(raw_close, label="raw")
    if set(provider_adjusted_close) != set(REQUIRED_PROVIDER_MODES):
        raise ValueError("provider reconciliation requires split, dividend, and all panels")
    provider = {
        mode: _validated_close_panel(frame, label=f"provider_{mode}")
        for mode, frame in provider_adjusted_close.items()
    }
    for mode, frame in provider.items():
        if not frame.index.equals(raw.index) or list(frame.columns) != list(raw.columns):
            raise ValueError(f"provider {mode} panel axes differ from raw panel")

    normalized_events = _validated_events(
        events,
        symbols=set(raw.columns),
        sessions={timestamp.date() for timestamp in raw.index},
        first_session=raw.index[0].date(),
        asof=observed_asof,
    )
    actions_by_key = {(event.symbol, event.ex_date): event for event in normalized_events}
    local_indices = {
        mode: _build_local_index(raw, actions_by_key, mode=mode)
        for mode in LOCALLY_RECONCILABLE_MODES
    }

    drift_bps: dict[str, dict[str, float]] = {}
    failures: list[str] = []
    for mode in LOCALLY_RECONCILABLE_MODES:
        local_returns = local_indices[mode].pct_change().iloc[1:]
        provider_returns = provider[mode].pct_change().iloc[1:]
        mode_drift: dict[str, float] = {}
        for symbol in raw.columns:
            maximum = float(
                ((local_returns[symbol] - provider_returns[symbol]).abs() * 10_000.0).max()
            )
            mode_drift[symbol] = maximum
            if maximum > tolerance_bps + 1e-12:
                failures.append(f"{mode}:{symbol}:{maximum:.8f}bps")
        drift_bps[mode] = mode_drift
    if failures:
        raise ValueError(
            "provider corporate-action reconciliation residual exceeds tolerance: "
            + ", ".join(failures)
        )

    event_ledger = [
        event.model_dump(mode="json")
        for event in sorted(
            normalized_events,
            key=lambda item: (item.ex_date, item.symbol, item.action_type, item.event_id),
        )
    ]
    wealth_ledger = _build_buy_and_hold_wealth_ledger(raw, normalized_events)
    event_sha256 = hashlib.sha256(_canonical_json_bytes(event_ledger)).hexdigest()
    local_hashes = {mode: _frame_sha256(frame) for mode, frame in local_indices.items()}
    provider_hashes = {mode: _frame_sha256(provider[mode]) for mode in REQUIRED_PROVIDER_MODES}
    report = {
        "schema_version": 1,
        "report_type": "corporate_action_reconciliation",
        "status": "ok",
        "asof": observed_asof.isoformat(),
        "currency": currency,
        "tolerance_bps": float(tolerance_bps),
        "symbols": list(raw.columns),
        "first_session": raw.index[0].date().isoformat(),
        "last_session": raw.index[-1].date().isoformat(),
        "event_count": len(event_ledger),
        "event_ledger_sha256": event_sha256,
        "local_index_sha256": local_hashes,
        "provider_panel_sha256": provider_hashes,
        "maximum_residual_bps": {
            mode: max(values.values(), default=0.0) for mode, values in drift_bps.items()
        },
        "residual_bps_by_symbol": drift_bps,
        "raw_prices_used_for_execution": True,
        "provider_adjusted_panels_used_for_reconciliation_only": True,
        "unsupported_action_policy": "fail_closed",
        "purpose": "historical_corporate_action_accounting_reconciliation",
        "verdict": "historical_reconciliation_only_not_pit_proof",
        "pit_visibility_proven": False,
        "process_date_used_as_visible_at": False,
        "asof_semantics": "retrospective_reconciliation_cutoff_not_provider_visibility",
        "supported_local_adjustments": list(LOCALLY_RECONCILABLE_MODES),
        "provider_adjustment_tokens": ["raw", "split", "dividend", "spin-off", "all"],
        "all_panel_accounting_status": "provider_only_not_locally_reproduced",
        "all_equals_split_plus_dividend": False,
        "limitations": [
            "Alpaca corporate actions do not provide reliable point-in-time visibility.",
            "process_date is an Alpaca processing date and is not treated as visible_at.",
            "The provider all panel may include spin-off adjustments and is not reproduced "
            "from split plus dividend accounting.",
            "Empty or unknown cash-dividend currency is rejected rather than defaulted to USD.",
            "Only forward splits, reverse splits, and ordinary USD cash dividends without "
            "due-bill or subtype accounting are supported.",
        ],
    }
    return CorporateActionReconciliation(
        local_indices=local_indices,
        wealth_ledger=wealth_ledger,
        event_ledger=event_ledger,
        report=report,
    )


def reject_unsupported_corporate_action_groups(payload: dict[str, Any]) -> None:
    unknown = sorted(set(payload) - set(ACTION_GROUP_TYPES))
    if unknown:
        raise ValueError("unknown corporate action response group: " + ", ".join(unknown))
    for group, action_type in ACTION_GROUP_TYPES.items():
        rows = payload.get(group)
        if rows is not None and not isinstance(rows, list):
            raise ValueError(f"corporate action response group must be an array: {group}")
        if action_type in PROHIBITED_ACTION_TYPES and rows:
            raise ValueError(f"unsupported corporate action present: {action_type}")
        if action_type == "cash_dividend":
            for row in rows or []:
                if not isinstance(row, dict):
                    raise ValueError("cash-dividend response row must be an object")
                if row.get("sub_type") is not None:
                    raise ValueError("unsupported cash-dividend subtype present")
                if (
                    row.get("due_bill_on_date") is not None
                    or row.get("due_bill_off_date") is not None
                ):
                    raise ValueError("unsupported cash-dividend due-bill accounting present")


def _validated_events(
    events: Sequence[CorporateActionEvent],
    *,
    symbols: set[str],
    sessions: set[date],
    first_session: date,
    asof: datetime,
) -> list[CorporateActionEvent]:
    normalized: list[CorporateActionEvent] = []
    identities: dict[str, str] = {}
    actions_by_session: dict[tuple[str, date], list[CorporateActionEvent]] = {}
    for raw_event in events:
        event = CorporateActionEvent.model_validate(raw_event)
        if event.action_type not in SUPPORTED_ACTION_TYPES:
            raise ValueError(f"unsupported corporate action present: {event.action_type}")
        if event.symbol not in symbols:
            raise ValueError("corporate-action symbol is outside the raw panel")
        if event.asof != asof:
            raise ValueError("corporate-action event asof differs from reconciliation asof")
        if event.ex_date not in sessions:
            raise ValueError("corporate-action ex date is outside complete raw sessions")
        if event.ex_date == first_session:
            raise ValueError("corporate-action reconciliation requires a prior raw session")
        event_hash = hashlib.sha256(
            _canonical_json_bytes(event.model_dump(mode="json"))
        ).hexdigest()
        previous = identities.setdefault(event.event_id, event_hash)
        if previous != event_hash:
            raise ValueError("corporate-action event revision detected within snapshot")
        if any(item.event_id == event.event_id for item in normalized):
            raise ValueError("duplicate corporate-action event ID")
        actions_by_session.setdefault((event.symbol, event.ex_date), []).append(event)
        normalized.append(event)
    ambiguous = [key for key, items in actions_by_session.items() if len(items) != 1]
    if ambiguous:
        raise ValueError("mixed or repeated same-session corporate actions are ambiguous")
    return normalized


def _build_local_index(
    raw: pd.DataFrame,
    actions_by_key: dict[tuple[str, date], CorporateActionEvent],
    *,
    mode: Literal["split", "dividend"],
) -> pd.DataFrame:
    result = pd.DataFrame(index=raw.index, columns=raw.columns, dtype=float)
    result.iloc[0] = 1.0
    for symbol in raw.columns:
        level = 1.0
        prices = raw[symbol]
        for index in range(1, len(raw.index)):
            session = raw.index[index].date()
            event = actions_by_key.get((symbol, session))
            split_multiplier = 1.0
            dividend = 0.0
            if event is not None:
                if event.action_type in {"forward_split", "reverse_split"} and mode == "split":
                    split_multiplier = event.split_multiplier
                elif event.action_type == "cash_dividend" and mode == "dividend":
                    assert event.cash_rate is not None
                    dividend = event.cash_rate
            gross_return = (float(prices.iloc[index]) * split_multiplier + dividend) / float(
                prices.iloc[index - 1]
            )
            if not math.isfinite(gross_return) or gross_return <= 0.0:
                raise ValueError("corporate-action local return is non-positive or non-finite")
            level *= gross_return
            result.iloc[index, result.columns.get_loc(symbol)] = level
    return result


def _build_buy_and_hold_wealth_ledger(
    raw: pd.DataFrame,
    events: Sequence[CorporateActionEvent],
) -> pd.DataFrame:
    events_by_symbol: dict[str, list[CorporateActionEvent]] = {symbol: [] for symbol in raw.columns}
    for event in events:
        events_by_symbol[event.symbol].append(event)

    rows: list[dict[str, Any]] = []
    for symbol in raw.columns:
        shares = 1.0
        cash = 0.0
        receivables: dict[str, tuple[float, date]] = {}
        by_ex_date = {event.ex_date: event for event in events_by_symbol[symbol]}
        for timestamp, close in raw[symbol].items():
            session = timestamp.date()
            paid = 0.0
            for event_id, (amount, payable_date) in list(receivables.items()):
                if payable_date <= session:
                    paid += amount
                    cash += amount
                    del receivables[event_id]

            split_multiplier = 1.0
            receivable_added = 0.0
            event = by_ex_date.get(session)
            if event is not None and event.action_type in {
                "forward_split",
                "reverse_split",
            }:
                split_multiplier = event.split_multiplier
                shares *= split_multiplier
            elif event is not None and event.action_type == "cash_dividend":
                assert event.cash_rate is not None
                assert event.payable_date is not None
                receivable_added = shares * event.cash_rate
                receivables[event.event_id] = (receivable_added, event.payable_date)
                if event.payable_date <= session:
                    cash += receivable_added
                    paid += receivable_added
                    del receivables[event.event_id]

            receivable = sum(amount for amount, _payable in receivables.values())
            market_value = shares * float(close)
            rows.append(
                {
                    "session": session.isoformat(),
                    "symbol": symbol,
                    "raw_close": float(close),
                    "split_share_multiplier": split_multiplier,
                    "dividend_receivable_added": receivable_added,
                    "dividend_cash_paid": paid,
                    "shares": shares,
                    "cash": cash,
                    "dividend_receivable": receivable,
                    "market_value": market_value,
                    "nav": market_value + cash + receivable,
                }
            )
    return pd.DataFrame(rows)


def _validated_close_panel(frame: pd.DataFrame, *, label: str) -> pd.DataFrame:
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        raise ValueError(f"{label} close panel must be non-empty")
    if not isinstance(frame.index, pd.DatetimeIndex):
        raise ValueError(f"{label} close panel requires a DatetimeIndex")
    if len(frame.index) < 2:
        raise ValueError(f"{label} close panel requires at least two sessions")
    if frame.index.has_duplicates or not frame.index.is_monotonic_increasing:
        raise ValueError(f"{label} close panel index must be unique and increasing")
    normalized_index = pd.DatetimeIndex(frame.index).tz_localize(None).normalize()
    if normalized_index.has_duplicates:
        raise ValueError(f"{label} close panel must contain one row per session")
    columns = [str(column).strip().upper() for column in frame.columns]
    if (
        len(columns) != len(set(columns))
        or not columns
        or any(not SAFE_SYMBOL_RE.fullmatch(symbol) for symbol in columns)
    ):
        raise ValueError(f"{label} close panel symbols are invalid")
    result = frame.copy()
    result.index = normalized_index
    result.columns = columns
    result = result.astype(float)
    values = result.to_numpy(dtype=float)
    if not np.isfinite(values).all() or (values <= 0.0).any():
        raise ValueError(f"{label} close panel contains non-positive or non-finite values")
    return result


def _frame_sha256(frame: pd.DataFrame) -> str:
    payload = {
        "sessions": [timestamp.date().isoformat() for timestamp in frame.index],
        "columns": list(frame.columns),
        "values": [[float(value) for value in row] for row in frame.to_numpy()],
    }
    return hashlib.sha256(_canonical_json_bytes(payload)).hexdigest()


def _canonical_json_bytes(payload: Any) -> bytes:
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("ascii")


def _require_utc(value: datetime, *, label: str) -> datetime:
    if value.tzinfo is None:
        raise ValueError(f"{label} must include timezone")
    return value.astimezone(UTC)


def _positive_finite(value: float | None) -> bool:
    return value is not None and math.isfinite(value) and value > 0.0
