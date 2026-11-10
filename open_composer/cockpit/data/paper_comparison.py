"""Equal-weight display comparisons from published paper valuation evidence.

The reference account is a presentation metric, not an account ledger or a
daily rebalancing simulation. Missing selected observations never reduce N.
"""

from __future__ import annotations

import math
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from open_composer.market_sessions import NEW_YORK, us_equity_session_dates

REFERENCE_CAPITAL = 100_000
D = Decimal


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def _day(value: Any) -> str | None:
    try:
        return date.fromisoformat(str(value)[:10]).isoformat()
    except ValueError:
        return None


def _stamp(value: str) -> datetime:
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("valuation timestamp has no timezone")
    return result


def _decimal(value: Any) -> Decimal:
    result = D(str(value))
    if not result.is_finite():
        raise ValueError("nonfinite financial value")
    return result


def _f1_activities(root: Path, history: dict, account: dict) -> list[dict]:
    """Reuse the existing receipt/coverage validator within the sealed scope."""
    from scripts.reconcile_paper_history import bound_json, receive_activities

    sealed = {str(Path(b["path"]).resolve()): b for b in history["source_bindings"]}
    indexes = [b for p, b in sealed.items() if Path(p).parts[-2:] == ("accounts", "F1.json")]
    if len(indexes) != 1:
        raise ValueError("F1 activity index unavailable")
    consumed: dict = {}

    def read(binding):
        expected = sealed.get(str(Path(binding["path"]).resolve()))
        if expected is None or expected["sha256"] != binding["sha256"]:
            raise ValueError("activity source is outside the sealed history")
        return bound_json(root, binding, consumed)

    index = read(indexes[0])
    identity = account["account_hash"]
    if index["account_hash"] != identity or index["alias"] != "F1":
        raise ValueError("F1 activity identity mismatch")

    def page(binding, expected_identity):
        receipt = read(binding)
        if (
            receipt.get("status_code") != 200
            or receipt.get("complete") is not True
            or receipt["request"].get("method") != "GET"
            or receipt["request"].get("identity") != expected_identity
        ):
            raise ValueError("activity receipt identity or completeness mismatch")
        return receipt, read(receipt["body"])

    activities, complete = receive_activities(root, index, identity, consumed, page)
    if not complete:
        raise ValueError("activity intervals are incomplete")
    # The reused reader also opens saved prefix receipts. They must belong to
    # the published history, in addition to passing their own hash bindings.
    if any(sealed.get(path, {}).get("sha256") != b["sha256"] for path, b in consumed.items()):
        raise ValueError("saved activity prefix is outside the sealed history")
    summary = history["recovery_summary"]["F1"]
    if len(activities) != summary["activity_count"] or summary.get("ambiguous_flow_ids"):
        raise ValueError("activity scope differs from reconciled F1")
    return activities


def _f1_points(history: dict, overview: dict, root: Path | None) -> dict[str, dict]:
    """Remove dated nontrade cash from the same adopted F1 account baseline.

    Broker daily history incorporates postings on their economic ``date``;
    ``created_at`` can be after the daily cutoff (including pre-baseline probe
    fees). Probe P&L already absorbed by the adopted baseline is not subtracted
    a second time. Unsupported open/post-baseline probes withhold this series.
    """
    if root is None:
        return {}
    try:
        account = next(h for h in history["histories"] if h["id"] == "account/quant1/broker-daily")
        ownership = account["order_ownership"]
        baseline = ownership["last_account_observation_before_first_native_FILL"]
        published_baseline = overview["F1_observed_adopted_baseline"]
        if (
            not account["activity_coverage_complete"]
            or not ownership["complete_order_interval"]
            or ownership["filled_orders_without_original_strategy_or_probe_receipt"]
            or any(_decimal(q) != 0 for q in ownership["probe_remaining_quantities"].values())
            or _stamp(baseline["at"]) >= _stamp(ownership["first_native_strategy_FILL_at"])
            or baseline["day"] != published_baseline["day"]
            or _decimal(baseline["equity_usd"]) != _decimal(published_baseline["equity_usd"])
            or any(
                _stamp(p["time"]) > _stamp(baseline["at"]) for p in ownership["probe_executions"]
            )
        ):
            return {}
        activities = _f1_activities(root.resolve(), history, account)
        initial = _decimal(baseline["equity_usd"])
        baseline_day = baseline["day"]
        cash = []
        totals: dict[str, Decimal] = {}
        external = {f["id"]: f for f in account["external_flows"]}
        external_ids = set()
        for entry in activities:
            kind = entry["activity_type"]
            if kind == "FILL":
                continue
            day = _day(entry.get("date"))
            if entry.get("status") != "executed" or day is None:
                raise ValueError("unresolved nontrade cash")
            amount = _decimal(entry["net_amount"])
            totals[kind] = totals.get(kind, D(0)) + amount
            is_external = kind in {"CSD", "CSW", "ACATC"}
            if is_external:
                flow = external[entry["id"]]
                if flow["day"] != day or _decimal(flow["amount_usd"]) != amount:
                    raise ValueError("external funding date or amount differs")
                external_ids.add(entry["id"])
            cash.append((day, amount, is_external))
        summary = history["recovery_summary"]["F1"]
        expected = {k: _decimal(v) for k, v in summary["nontrade_signed_amounts_by_type"].items()}
        if totals != expected or external_ids != external.keys():
            raise ValueError("dated cash does not reconcile to sealed summary")
        start = _stamp(ownership["first_native_strategy_FILL_at"]).astimezone(NEW_YORK).date()
        points = {}
        for point in account["points"]:
            day = point["day"]
            if day < start.isoformat():
                continue
            value = _number(point.get("equity_usd"))
            selected = [
                (amount, is_external) for d, amount, is_external in cash if baseline_day < d <= day
            ]
            flows = sum((v for v, external in selected if external), D(0))
            postings = sum((v for v, external in selected if not external), D(0))
            capital = initial + flows
            pnl = (
                None
                if value is None
                else _decimal(point["equity_usd"]) - initial - flows - postings
            )
            percent = float(pnl / capital * 100) if pnl is not None and capital > 0 else None
            if point.get("missing"):
                percent = None
            points[day] = dict(
                day=day,
                return_pct=percent,
                state="observed" if percent is not None else "missing",
                source_at=point.get("at"),
            )
        return points
    except (OSError, ValueError, TypeError, KeyError, StopIteration, ArithmeticError):
        return {}


def build_paper_comparison(
    history: dict,
    overview: dict,
    dashboard: dict,
    *,
    root: Path | None = None,
) -> dict:
    """Prepare top-level cumulative percentage series for an equal mean view."""
    series = {s["id"]: s for s in history.get("histories", [])} if history.get("available") else {}
    children = {child for s in series.values() for child in s.get("children", [])}
    rows = [r for r in dashboard.get("rows", []) if r["id"] not in children]
    through = _day(history.get("through_session") or overview.get("through_session"))
    f1 = _f1_points(history, overview, root) if any(r["id"] == "F1" for r in rows) else {}
    prepared = []
    for row in rows:
        source = series.get(row["id"], {})
        start = _day(source.get("first_fill") or row.get("first_day"))
        if start is None and source.get("children"):
            starts = [_day(series.get(c, {}).get("first_fill")) for c in source["children"]]
            start = min((d for d in starts if d), default=None)
        points = {}
        if row["id"] == "F1":
            points = f1
            if start is None:
                start = _day(overview.get("pool_starts", {}).get("F1"))
        elif source.get("kind") in {"trading_component", "composite_parent"}:
            for point in source.get("points", []):
                capital, pnl = (
                    _number(point.get("capital_usd")),
                    _number(point.get("trading_pnl_usd")),
                )
                percent = (
                    pnl / capital * 100 if capital and capital > 0 and pnl is not None else None
                )
                if point.get("missing"):
                    percent = None
                points[point["day"]] = dict(
                    day=point["day"],
                    return_pct=percent,
                    state="observed" if percent is not None else "missing",
                    source_at=point.get("at"),
                )
        if start is None:
            start = min(points, default=None)
        capital = _number(row.get("capital_usd"))
        latest = _number(row.get("return_pct")) if capital and capital > 0 else None
        selectable = bool(
            capital
            and capital > 0
            and (latest is not None or any(p["return_pct"] is not None for p in points.values()))
        )
        archived = row.get("status") == "已退出" or row.get("status_label") == "已退出"
        prepared.append(
            dict(
                id=row["id"],
                label=row["label"],
                href=row["href"],
                start_day=start,
                latest_return_pct=latest,
                latest_at=row.get("observed_at") or dashboard.get("snapshot_at"),
                selectable=selectable,
                default_selected=selectable and not archived,
                archived=archived,
                disabled_reason=None if selectable else "本金待确认" if not capital else "等待估值",
                history_basis="broker_daily_ex_posted_cash"
                if row["id"] == "F1"
                else "session_close_trading",
                _points=points,
            )
        )
    starts = [s["start_day"] for s in prepared if s["start_day"]]
    days = (
        [
            str(d)
            for d in us_equity_session_dates(
                date.fromisoformat(min(starts)), date.fromisoformat(through)
            )
        ]
        if starts and through
        else []
    )
    for strategy in prepared:
        known = strategy.pop("_points")
        points = []
        for day in days:
            if strategy["start_day"] and day < strategy["start_day"]:
                point = dict(day=day, return_pct=0.0, state="not_started", source_at=None)
            else:
                point = known.get(
                    day, dict(day=day, return_pct=None, state="missing", source_at=None)
                )
            points.append(point)
        observed = sum(p["state"] == "observed" for p in points)
        missing = any(p["state"] == "missing" for p in points)
        strategy.update(
            points=points,
            history_status="partial"
            if observed and missing
            else "available"
            if observed
            else "unavailable",
        )
    return dict(
        schema_version=1,
        initial_capital_usd=REFERENCE_CAPITAL,
        through_session=through,
        snapshot_at=dashboard.get("snapshot_at"),
        strategies=prepared,
        days=days,
    )


def compare_paper_strategies(comparison: dict, selected_ids: list[str] | None = None) -> dict:
    """Reference implementation of the browser's fixed-N cumulative mean."""
    choices = {s["id"]: s for s in comparison["strategies"]}
    ids = (
        list(dict.fromkeys(selected_ids))
        if selected_ids is not None
        else [s["id"] for s in choices.values() if s["default_selected"]]
    )
    if any(identity not in choices or not choices[identity]["selectable"] for identity in ids):
        raise ValueError("selection contains an unavailable strategy")
    capital = comparison["initial_capital_usd"]

    def aggregate(values):
        mean = sum(values) / len(ids) if ids and all(v is not None for v in values) else None
        return dict(
            return_pct=mean,
            equity_usd=capital * (1 + mean / 100) if mean is not None else None,
            pnl_usd=capital * mean / 100 if mean is not None else None,
        )

    snapshot = dict(
        at=comparison["snapshot_at"], **aggregate([choices[i]["latest_return_pct"] for i in ids])
    )
    indexed = {identity: {p["day"]: p for p in choices[identity]["points"]} for identity in ids}
    starts = [choices[identity]["start_day"] for identity in ids if choices[identity]["start_day"]]
    first_day = min(starts) if starts else None
    days = [day for day in comparison["days"] if day >= first_day] if ids and first_day else []
    daily, previous = [], None
    for day in days:
        values = [indexed[i].get(day, {}).get("return_pct") for i in ids]
        point = dict(day=day, **aggregate(values))
        equity = point["equity_usd"]
        point.update(
            change_usd=equity - previous if equity is not None and previous is not None else None,
            change_pct=(equity / previous - 1) * 100
            if equity is not None and previous is not None and previous > 0
            else None,
            missing=[
                identity for identity, value in zip(ids, values, strict=True) if value is None
            ],
        )
        daily.append(point)
        previous = equity
    return dict(selected_ids=ids, snapshot=snapshot, daily=daily)
