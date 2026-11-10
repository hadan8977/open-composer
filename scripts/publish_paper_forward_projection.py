"""Publish the forward-extended paper history and its matching v1 overview.

The extended history comes from ``scripts/extend_paper_projection_forward.py``;
this adapter keeps the sealed overview's definitions (assigned capital, the
unassigned six-account cash, carried pool adjustments) and replaces only the
numbers the new sessions changed. The overview goes through the existing
validating publisher, the history through an identical atomic binding switch.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo
from decimal import Decimal
from pathlib import Path

D = Decimal
CENT = D("0.01")
SIX = ("BASE", "H5", "LSTM", "BASE_STATE_BUDGET", "MULTI_EQUAL", "MULTI_HIERARCHICAL")
EXTERNAL = {"CSD", "CSW", "ACATC"}


def num(value):
    return None if value is None else D(str(value))


def session_day(iso: str) -> str:
    return (
        datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
        .astimezone(ZoneInfo("America/New_York"))
        .date()
        .isoformat()
    )


def equity_by_day(capture: dict) -> dict[str, D]:
    """Broker daily equity plus the post-close live snapshot the series lacks.

    Alpaca's paper ``portfolio_history`` trails a session and can answer a 0.0
    placeholder; the account endpoint carries the real current equity. Mirrors
    ``extend_paper_projection_forward.extend_account`` exactly, including the
    degenerate-value guard.
    """
    from open_composer.cockpit.data.paper_books import latest_completed_session

    history = capture["portfolio_history"]
    result = {}
    for stamp, equity in zip(history["timestamp"], history["equity"], strict=True):
        if equity is None or float(equity) <= 0:
            continue
        day = session_day(datetime.fromtimestamp(stamp, UTC).isoformat())
        result[day] = D(str(equity))
    captured_at = datetime.fromisoformat(str(capture["captured_at"]).replace("Z", "+00:00"))
    snapshot_day = str(latest_completed_session(captured_at))
    live = D(str((capture.get("account") or {}).get("equity") or 0))
    if snapshot_day not in result and live > 0:
        previous = result[max(result)] if result else None
        if previous is None or live > previous * D("0.1"):
            result[snapshot_day] = live
    return result


def stamp_by_day(capture: dict) -> dict[str, str]:
    history = capture["portfolio_history"]
    result = {}
    for stamp, _ in zip(history["timestamp"], history["equity"], strict=True):
        at = datetime.fromtimestamp(stamp, UTC)
        result[session_day(at.isoformat())] = at.isoformat()
    return result


def cash_at(capture: dict, rows: list, day: str) -> D:
    """Live cash rolled back over the fills and postings dated after ``day``."""
    effect = D(0)
    for row in rows:
        when = str(row.get("transaction_time") or row.get("date") or "")
        if when[:10] <= day:
            continue
        if row["activity_type"] == "FILL":
            amount = D(str(row["price"])) * D(str(row["qty"]))
            effect += -amount if row["side"] in {"buy", "buy_to_cover"} else amount
        else:
            effect += D(str(row.get("net_amount") or 0))
    return D(str(capture["account"]["cash"])) - effect


def postings(capture: dict, after: str, through: str) -> tuple[dict[str, D], D]:
    """Non-trade cash by activity type after ``after`` plus the external total."""
    by_kind: dict[str, D] = {}
    external = D(0)
    for row in capture["rows"]:
        if row.get("activity_type") == "FILL":
            continue
        if row.get("status") != "executed":
            raise SystemExit(f"unresolved nontrade cash: {row}")
        day = str(row.get("date"))[:10]
        if day <= after or day > through:
            continue
        amount = D(str(row.get("net_amount") or 0))
        by_kind[row["activity_type"]] = by_kind.get(row["activity_type"], D(0)) + amount
        if row["activity_type"] in EXTERNAL:
            external += amount
    return by_kind, external


def atomic_write(path: Path, raw: bytes) -> None:
    fd, name = tempfile.mkstemp(prefix=".paper-binding-", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--history", type=Path, required=True)
    parser.add_argument("--inputs", type=Path, required=True)
    parser.add_argument(
        "--overview-output", type=Path, required=True, help="Reconciled v1 overview to publish"
    )
    parser.add_argument(
        "--sealed-overview",
        type=Path,
        required=True,
        help="The sealed 2026-10-27 overview; the live binding would double-count on a re-run",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    root = args.root.resolve()
    inputs = args.inputs.resolve()
    history = json.loads(args.history.read_text())
    sealed_overview = json.loads(args.sealed_overview.read_text())
    through = history["through_session"]
    accounts = {
        alias: json.loads((inputs / f"account-{alias}.json").read_text())
        for alias in ("legacy", "quant1", "six")
    }
    activities = {
        alias: json.loads((inputs / f"activities-{alias}.json").read_text())
        for alias in ("legacy", "quant1", "six")
    }
    equity = {alias: equity_by_day(capture) for alias, capture in accounts.items()}
    posted, external = {}, {}
    for alias, capture in activities.items():
        posted[alias], external[alias] = postings(
            capture, history["forward_extension"]["from_session"], through
        )

    initial = {k: D(str(v)) for k, v in sealed_overview["initial_pool_capital"].items()}
    six_assigned = D(str(sealed_overview["six_assigned_capital_usd"]))
    six_unassigned = D(str(sealed_overview["six_unassigned_cash_usd"]))

    def pool_value(alias: str, day: str):
        value = equity[alias].get(day)
        if value is None:
            return None
        if alias == "six":
            return value - six_unassigned
        return value

    def pool_pnl(alias: str, day: str):
        """``alias`` is the published pool id (legacy/six/F1), not the account."""
        key = "quant1" if alias == "F1" else alias
        value = pool_value(key, day)
        if value is None:
            return None
        capital = six_assigned if alias == "six" else initial[alias]
        return value - capital - flows_before(key, day)

    def flows_before(alias: str, day: str) -> D:
        total = D(0)
        for row in activities[alias]["rows"]:
            if row.get("activity_type") not in EXTERNAL:
                continue
            if str(row.get("date"))[:10] <= day:
                total += D(str(row.get("net_amount") or 0))
        return total

    # --- rows -------------------------------------------------------------
    histories = {row["id"]: row for row in history["histories"]}
    rows = []
    for row in sealed_overview["snapshot"]["rows"]:
        updated = dict(row)
        if row["id"] == "F1" or row["pool"] == "F1":
            value = equity["quant1"].get(through)
            pnl = None if value is None else value - initial["F1"] - flows_before("quant1", through)
            capital = initial["F1"]
        else:
            last = histories[row["id"]]["points"][-1]
            pnl = num(last.get("trading_pnl_usd"))
            capital = num(last.get("capital_usd"))
        updated["capital_usd"] = None if capital is None else float(capital)
        updated["precise_pnl_usd"] = None if pnl is None else float(pnl)
        updated["pnl_usd"] = None if pnl is None else float(pnl.quantize(CENT))
        updated["return_pct"] = (
            None if pnl is None or not capital else float(pnl / capital * 100)
        )
        updated["missing"] = [] if pnl is not None else [row["id"] + ": no value"]
        rows.append(updated)

    # --- pool readings ----------------------------------------------------
    readings = []
    for alias in ("legacy", "six", "F1"):
        key = "quant1" if alias == "F1" else alias
        value = pool_value(key, through)
        flows = flows_before(key, through)
        capital = initial[alias] if alias != "six" else six_assigned
        pnl = None if value is None else value - capital - flows
        readings.append(
            dict(
                id=alias,
                capital_usd=float(capital),
                pnl_usd=None if pnl is None else float(pnl),
                return_pct=None if pnl is None or not capital else float(pnl / capital * 100),
            )
        )

    # --- daily ------------------------------------------------------------
    daily = list(sealed_overview["daily"])
    sealed_days = {point["day"] for point in daily}
    sessions = [
        day
        for day in sorted({*equity["legacy"], *equity["six"], *equity["quant1"]})
        if day > sealed_overview["through_session"] and day <= through
    ]
    for day in sessions:
        if day in sealed_days:
            continue
        pools, missing = [], []
        for alias in ("legacy", "six", "F1"):
            key = "quant1" if alias == "F1" else alias
            pnl = pool_pnl(alias, day)
            capital = six_assigned if alias == "six" else initial[alias]
            pools.append(dict(id=alias, capital_usd=capital, pnl_usd=pnl))
            if pnl is None:
                missing.append(alias)
        total_capital = sum((p["capital_usd"] for p in pools), D(0))
        total_pnl = None if missing else sum((p["pnl_usd"] for p in pools), D(0))
        daily.append(
            dict(
                day=day,
                capital_missing_details=[],
                capital_usd=float(total_capital),
                known_capital_usd=float(total_capital),
                capital_missing=[],
                pnl_usd=None if total_pnl is None else float(total_pnl),
                return_pct=None
                if total_pnl is None
                else float(total_pnl / total_capital * 100),
                missing=missing,
                pools=[p["id"] for p in pools],
            )
        )

    # --- adjustments and totals -------------------------------------------
    adjustments = []
    for entry in sealed_overview["snapshot"]["adjustments"]:
        key = "quant1" if entry["pool"] == "F1" else entry["pool"]
        entries = dict(entry.get("entries") or {})
        for kind, amount in posted[key].items():
            entries[kind] = float(D(str(entries.get(kind, 0))) + amount)
        adjustments.append(
            dict(
                pool=entry["pool"],
                entries=entries,
                posted_usd=float(sum((D(str(v)) for v in entries.values()), D(0))),
                quote_precision_usd=entry.get("quote_precision_usd"),
            )
        )
    missing_readings = [r["id"] for r in readings if r["pnl_usd"] is None]
    total_pnl = sum((D(str(r["pnl_usd"])) for r in readings if r["pnl_usd"] is not None), D(0))
    if missing_readings:
        raise SystemExit(f"pool readings missing for {missing_readings} at {through}")
    row_total = sum((D(str(r["pnl_usd"])) for r in rows if r["pnl_usd"] is not None), D(0))
    adjustment = total_pnl - row_total
    posted_total = sum(
        (D(str(a["posted_usd"])) + D(str(a.get("quote_precision_usd") or 0)) for a in adjustments),
        D(0),
    )
    # The publisher's identity: assigned per-strategy capital plus the cash no
    # strategy owns (the sleeves' spare 40k) is the account total.
    capital = sum(
        (D(str(r["capital_usd"])) for r in rows if r["capital_usd"] is not None), D(0)
    ) + D(str(sealed_overview["snapshot"]["unassigned_capital_usd"]))
    from open_composer.market_sessions import us_equity_session_close

    close = us_equity_session_close(date.fromisoformat(through))
    close_stamp = datetime.combine(
        date.fromisoformat(through), close, tzinfo=ZoneInfo("America/New_York")
    ).astimezone(UTC).isoformat()
    at = [close_stamp]
    overview = dict(sealed_overview)
    overview.update(
        generated_at=datetime.now(UTC).isoformat(),
        through_session=through,
    )
    overview["snapshot"] = dict(
        sealed_overview["snapshot"],
        capital_usd=float(capital),
        known_capital_usd=float(capital),
        capital_missing=[],
        pnl_usd=float(total_pnl),
        return_pct=float(total_pnl / capital * 100),
        missing=[],
        pools=[r["id"] for r in readings],
        at_start=at[0],
        at_end=at[-1],
        marks_start=at[0],
        marks_end=at[-1],
        rows=rows,
        adjustment_usd=float(adjustment),
        display_rounding_usd=float(adjustment - posted_total),
        unassigned_capital_usd=sealed_overview["snapshot"]["unassigned_capital_usd"],
        adjustments=adjustments,
        pool_readings=readings,
    )
    summary = dict(history.get("recovery_summary") or {})
    for alias in summary:
        key = "quant1" if alias == "F1" else alias
        value = pool_value(key, through)
        if value is None:
            continue
        cash = cash_at(accounts[key], activities[key]["rows"], through)
        whole = equity[key][through]
        summary[alias] = dict(
            summary[alias],
            current_account=dict(
                summary[alias].get("current_account") or {},
                equity=str(whole),
                cash=str(cash),
                long_market_value=str(whole - cash),
                observed_at=close_stamp,
            ),
        )
    history["recovery_summary"] = summary
    overview["daily"] = daily
    overview["forward_extension"] = history["forward_extension"]
    overview["source_bindings"] = list(sealed_overview.get("source_bindings") or []) + [
        dict(
            path=str(path),
            bytes=len(path.read_bytes()),
            sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        )
        for path in sorted(inputs.glob("*.json"))
    ]

    from scripts.publish_paper_overview import validate

    validate(overview)
    args.overview_output.parent.mkdir(parents=True, exist_ok=True)
    args.overview_output.write_text(
        json.dumps(overview, indent=1, ensure_ascii=False, allow_nan=False) + "\n"
    )
    print(
        json.dumps(
            dict(
                through=through,
                total_pnl=float(total_pnl),
                row_total=float(row_total),
                adjustment=float(adjustment),
                capital=float(capital),
                days_added=len(sessions),
                readings=readings,
            ),
            indent=1,
            default=str,
        )
    )

    if args.dry_run:
        return 0
    from scripts.publish_paper_overview import publish

    binding = publish(root, args.overview_output)
    print("overview published:", binding)
    raw = (
        json.dumps(history, indent=2, ensure_ascii=False, allow_nan=False, default=str) + "\n"
    ).encode()
    digest = hashlib.sha256(raw).hexdigest()
    artifact = root / "reports/paper/overview" / f"history-{digest}.json"
    artifact.parent.mkdir(parents=True, exist_ok=True)
    if not artifact.exists():
        artifact.write_bytes(raw)
    binding_path = root / "config/paper-history-dashboard.json"
    atomic_write(
        binding_path,
        (json.dumps({"path": str(artifact.relative_to(root)), "sha256": digest}, indent=2) + "\n").encode(),
    )
    print("history published:", artifact, digest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
