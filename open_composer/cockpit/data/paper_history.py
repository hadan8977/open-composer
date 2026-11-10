"""Read one sealed offline accounting projection; no broker or refresh actions."""

from __future__ import annotations

import hashlib
import json
import math
from datetime import date
from pathlib import Path

from open_composer.market_sessions import us_equity_session_dates


def _number(value):
    if isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return result if math.isfinite(result) else None


def _chart(points, account):
    field = "equity_usd" if account else "trading_pnl_usd"
    values = [p.get(field) for p in points if p.get(field) is not None]
    if not values:
        return None
    low = min(values) if account else min(0, *values)
    high = max(values) if account else max(0, *values)
    span = high - low or 1
    baseline = 150 if account else 140 - (0 - low) / span * 130
    step = 800 / len(points)
    bars = []
    for index, point in enumerate(points):
        value = point.get(field)
        y = None if value is None else 140 - (value - low) / span * 130
        bars.append(
            {
                "day": point["day"],
                "value": value,
                "x": index * step + 1,
                "width": max(1, step - 2),
                "y": None if y is None else min(baseline, y),
                "height": None if y is None else max(1, abs(baseline - y)),
            }
        )
    return {"bars": bars, "baseline": baseline}


def load_paper_history(root: Path) -> dict:
    config = root / "config/paper-history-dashboard.json"
    if not config.exists():
        return {
            "available": False,
            "histories": [],
            "warning": "Historical reconciliation not published",
        }
    try:
        binding = json.loads(config.read_text())
        path = (root / binding["path"]).resolve()
        if not path.is_relative_to((root / "reports/paper").resolve()):
            raise ValueError("history outside paper reports")
        with path.open("rb") as stream:
            raw = stream.read(8_388_609)
        if len(raw) > 8_388_608 or hashlib.sha256(raw).hexdigest() != binding["sha256"]:
            raise ValueError("historical projection binding changed")
        data = json.loads(raw)
        if data.get("schema_version") != 1:
            raise ValueError("unsupported history schema")
        date.fromisoformat(data["through_session"])
        histories = []
        for row in data["histories"]:
            # Keep each valuation timestamp and source; select the last original
            # account observation per session, never sum duplicate observations.
            by_day = {}
            for point in sorted(row["points"], key=lambda x: (x["day"], x.get("at") or "")):
                date.fromisoformat(point["day"])
                by_day[point["day"]] = {
                    **point,
                    **{
                        key: _number(point.get(key))
                        for key in (
                            "equity_usd",
                            "capital_usd",
                            "nav_before_unverified_items_usd",
                            "trading_pnl_usd",
                            "tracking_return_pct",
                            "net_pnl_usd",
                            "equity_identity_residual_usd",
                            "account_change_ex_external_flows_usd",
                            "account_return_pct",
                        )
                    },
                }
            if by_day:
                for day in us_equity_session_dates(
                    date.fromisoformat(min(by_day)), date.fromisoformat(data["through_session"])
                ):
                    by_day.setdefault(
                        day.isoformat(),
                        {
                            "day": day.isoformat(),
                            "valuation": "missing_original_account_observation",
                            "equity_usd": None,
                            "capital_usd": None,
                            "nav_before_unverified_items_usd": None,
                            "trading_pnl_usd": None,
                            "net_pnl_usd": None,
                            "account_change_ex_external_flows_usd": None,
                            "account_return_pct": None,
                            "missing": ["No same-session valuation; no stale carry"],
                        },
                    )
            points = [by_day[day] for day in sorted(by_day)]
            latest = next(
                (
                    point
                    for point in reversed(points)
                    if point.get("equity_usd") is not None
                    or point.get("trading_pnl_usd") is not None
                ),
                None,
            )
            histories.append(
                {
                    **row,
                    "order_ownership": {
                        **row["order_ownership"],
                        "probe_realized_trading_pnl_before_fees_usd": _number(
                            row["order_ownership"].get("probe_realized_trading_pnl_before_fees_usd")
                        ),
                    }
                    if row.get("order_ownership")
                    else None,
                    "points": points,
                    "latest": latest,
                    "chart": _chart(points, row["kind"] == "account"),
                }
            )
        from datetime import UTC, datetime

        from open_composer.cockpit.data.paper_books import latest_completed_session

        expected = latest_completed_session(datetime.now(UTC))
        stale = date.fromisoformat(data["through_session"]) < expected
        cash_entries = []
        observations = []
        received_accounts = data.get("recovery_summary", {})
        for alias, account in received_accounts.items():
            cash_entries.extend(
                dict(account=alias, kind=kind, amount_usd=_number(amount))
                for kind, amount in account.get("nontrade_signed_amounts_by_type", {}).items()
            )
            latest = account["current_account"]
            value = _number(latest.get("equity"))
            initial = _number(
                account.get("reconciliation", {}).get("reported_portfolio_history_base_value")
            )
            observations.append(
                dict(
                    account=alias,
                    at=latest.get("observed_at"),
                    equity_usd=value,
                    cash_usd=_number(latest.get("cash")),
                    base_value_usd=initial,
                    change_from_reported_base_usd=None
                    if value is None or initial is None
                    else value - initial,
                )
            )
        if "six" not in received_accounts:
            saved = data.get("account_reconciliations", {}).get("six", {})
            cash_entries.extend(
                dict(account="six", kind=kind, amount_usd=_number(amount))
                for kind, amount in saved.get("saved_posted_nontrade_by_type", {}).items()
            )
        return {
            **data,
            "available": True,
            "histories": histories,
            "artifact_sha256": binding["sha256"],
            "expected_session": str(expected),
            "stale": stale,
            "posted_cash_entries": cash_entries,
            "latest_account_observations": observations,
            "warning": "Dated reconstruction is behind the latest completed session; no stale carry"
            if stale
            else None,
        }
    except (OSError, ValueError, KeyError, TypeError):
        return {
            "available": False,
            "histories": [],
            "warning": "Historical projection unavailable or changed; no zero values inferred",
        }


def account_performance(points, external_flows, *, flow_coverage_complete):
    """Observed account profit after actual external flows, with a named return.

    Cash flows need an exact clock for Modified Dietz. A complete dated flow
    amount can support profit even when a valid return denominator is absent.
    This function never treats broker initial funding as earned income.
    """
    from datetime import datetime
    from decimal import Decimal

    valid = sorted((p for p in points if p.get("equity_usd") is not None), key=lambda p: p["at"])
    # Zero-valued days before virtual funding are not an earned capital gain.
    funded = next((i for i, p in enumerate(valid) if Decimal(str(p["equity_usd"])) != 0), None)
    if funded is not None:
        valid = valid[funded:]
    if len(valid) < 2:
        return {
            "net_change_ex_external_flows_usd": None,
            "return_pct": None,
            "return_method": "insufficient account observations",
        }
    first, last = valid[0], valid[-1]
    beginning, ending = Decimal(str(first["equity_usd"])), Decimal(str(last["equity_usd"]))
    if not flow_coverage_complete:
        return {
            "start": first["at"],
            "end": last["at"],
            "observation_change_usd": float(ending - beginning),
            "net_change_ex_external_flows_usd": None,
            "return_pct": None,
            "return_method": "external flow coverage incomplete",
        }
    start = datetime.fromisoformat(first["at"].replace("Z", "+00:00"))
    end = datetime.fromisoformat(last["at"].replace("Z", "+00:00"))
    flows = []
    exact = True
    boundary_unknown = False
    for flow in external_flows:
        if flow.get("at"):
            at = datetime.fromisoformat(flow["at"].replace("Z", "+00:00"))
            if not start < at <= end:
                continue
            flows.append((Decimal(str(flow["amount_usd"])), at))
        elif first["day"] <= flow["day"] <= last["day"]:
            # A date alone cannot tell whether a boundary-session transfer was
            # included in the opening or closing observed account equity.
            if flow["day"] in (first["day"], last["day"]):
                boundary_unknown = True
            flows.append((Decimal(str(flow["amount_usd"])), None))
            exact = False
    profit = ending - beginning - sum((amount for amount, _ in flows), Decimal(0))
    result = {
        "start": first["at"],
        "end": last["at"],
        "opening_equity_usd": float(beginning),
        "ending_equity_usd": float(ending),
        "external_flow_usd": float(sum((amount for amount, _ in flows), Decimal(0))),
        "observation_change_usd": float(ending - beginning),
        "net_change_ex_external_flows_usd": None if boundary_unknown else float(profit),
        "return_pct": None,
        "return_method": "boundary-date flow timing unknown; account profit unverified"
        if boundary_unknown
        else "flow timing absent; amount-adjusted account profit only",
    }
    duration = Decimal(str((end - start).total_seconds()))
    if exact and duration > 0:
        denominator = beginning + sum(
            (amount * Decimal(str((end - at).total_seconds())) / duration for amount, at in flows),
            Decimal(0),
        )
        if denominator > 0:
            result.update(
                return_denominator_usd=float(denominator),
                return_pct=float(profit / denominator * 100),
                return_method="Modified Dietz (time-weighted cash-flow denominator; approximation)"
                if flows
                else "flow-free observed account holding-period return",
            )
    return result
