"""Reconstruct independently owned paper sleeves from broker FILLs and raw closes."""
from __future__ import annotations

import csv
import hashlib
import json
import sys
from collections import Counter, defaultdict
from datetime import UTC, date, datetime
from decimal import Decimal as D
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from open_composer.market_sessions import NEW_YORK, us_equity_session_dates
from scripts.reconcile_paper_history import LEGACY, historical_book, legacy_executions
from scripts.reconcile_six_paper_performance import clean, receive_executions

OUT = ROOT / "reports/owner/paper-recovery-20261103"
E = OUT / "evidence"
END = date(2026, 11, 2)
START = date(2026, 10, 1)
BASE = date(2026, 9, 30)
CONSUMED = {}


def load(path):
    p = Path(path)
    b = p.read_bytes()
    CONSUMED[str(p.relative_to(ROOT))] = {"bytes": len(b), "sha256": hashlib.sha256(b).hexdigest()}
    return json.loads(b, parse_float=D)


def save(path, obj):
    path.write_text(json.dumps(clean(obj), ensure_ascii=False, indent=2) + "\n")


def day(stamp):
    return datetime.fromisoformat(stamp.replace("Z", "+00:00")).astimezone(NEW_YORK).date().isoformat()


def metrics(points, baseline):
    valid = [p for p in points if p.get("nav_before_unverified_items_usd") is not None]
    if not valid or baseline is None:
        return {"profit_before_unattributed_costs_usd": None, "return_pct": None}
    peak = baseline
    dd = D(0)
    for p in valid:
        nav = D(str(p["nav_before_unverified_items_usd"]))
        peak = max(peak, nav)
        dd = min(dd, nav / peak - 1)
    last = D(str(valid[-1]["nav_before_unverified_items_usd"]))
    return {"profit_before_unattributed_costs_usd": last - baseline, "return_pct": (last / baseline - 1) * 100, "max_drawdown_pct": dd * 100}


def main():
    prices = {}
    for p in sorted((E / "market").glob("raw-*.json")):
        if p.name.endswith("receipt.json"):
            continue
        for symbol, bars in load(p).get("bars", {}).items():
            for bar in bars:
                prices[symbol, date.fromisoformat(day(bar["t"]))] = {"price": D(str(bar["c"])), "at": bar["t"], "source": str(p.relative_to(ROOT))}
    activities = {a: load(E / a / "activities-all.json") for a in ("legacy", "six", "quant1")}
    ownership = {}
    for name in LEGACY:
        for suffix in ("orders", "fills"):
            path = ROOT / f"reports/paper/rehearsal/{name}-{suffix}.jsonl"
            if path.exists():
                raw = path.read_bytes()
                CONSUMED[str(path.relative_to(ROOT))] = {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
                for line in raw.decode().splitlines():
                    x = json.loads(line)
                    if x.get("broker_order_id"):
                        oid = x["broker_order_id"]
                        assert oid not in ownership or ownership[oid] == name
                        ownership[oid] = name
    legacy = defaultdict(list)
    unknown = []
    for x in activities["legacy"]:
        if x["activity_type"] != "FILL":
            continue
        name = ownership.get(x["order_id"])
        if name is None:
            unknown.append(x)
            continue
        legacy[name].append({"id": x["id"], "order_id": x["order_id"], "symbol": x["symbol"], "side": x["side"], "quantity": D(x["qty"]), "price": D(x["price"]), "time": x["transaction_time"], "session": day(x["transaction_time"]), "basis": "broker_FILL"})
    state = load(E / "runtime-state.json")
    six, order_detail, six_owners = receive_executions(state, {"account_hash": state["account"]["account_hash"], "activities": [x for x in activities["six"] if x["activity_type"] == "FILL"]}, CONSUMED)
    for rows in six.values():
        for x in rows:
            x["session"] = day(x["time"])
    histories = []
    for name, (label, initial) in LEGACY.items():
        h = historical_book("legacy/" + name, label, legacy[name], initial, [], prices, END)
        h["executions"] = legacy[name]
        h["initial"] = initial
        histories.append(h)
    for name, rows in six.items():
        risk = state["books"][name]["evidence"]["risk"]
        flows = state["books"][name]["evidence"].get("allocation_flows", [])
        h = historical_book("six/" + name, name, rows, D(str(risk["initial_capital"])), flows, prices, END)
        h["executions"] = rows
        h["initial"] = D(str(risk["initial_capital"]))
        h["risk"] = risk
        histories.append(h)
    for parent in ["MULTI_EQUAL", "MULTI_HIERARCHICAL"]:
        children = [h for h in histories if h["id"].startswith("six/" + parent + "/")]
        rows = []
        for session in us_equity_session_dates(date(2026, 10, 21), END):
            ds = session.isoformat()
            ps = [next((p for p in h["points"] if p["day"] == ds), None) for h in children]
            row = {"day": ds, "missing": []}
            for field in ["capital_usd", "cash_from_principal_usd", "holdings_value_usd", "nav_before_unverified_items_usd", "trading_pnl_usd"]:
                vals = [p.get(field) if p else None for p in ps]
                row[field] = None if any(v is None for v in vals) else sum(vals, D(0))
            if row["nav_before_unverified_items_usd"] is None:
                row["missing"] = ["One or more child same-day marks unavailable"]
            rows.append(row)
        histories.append({"id": "six/" + parent, "label": parent, "kind": "composite_parent", "points": rows, "initial": D(20000), "executions": [x for h in children for x in h["executions"]]})
    summaries = []
    for h in histories:
        points = [p for p in h["points"] if p["day"] >= START.isoformat()]
        baseline = next((p for p in h["points"] if p["day"] == BASE.isoformat()), None)
        if baseline:
            basis = baseline["nav_before_unverified_items_usd"]
            basis_day = BASE.isoformat()
        else:
            basis_day = min((x["session"] for x in h["executions"]), default=None)
            # BASE's extra $10k was assigned before its first genuine fill.
            basis = points[0]["capital_usd"] if points and basis_day else h["initial"]
        valid = [p for p in points if p["nav_before_unverified_items_usd"] is not None]
        trades = h["executions"]
        in_window = [x for x in trades if x["session"] >= START.isoformat()]
        summaries.append({"id": h["id"], "label": h["label"], "initial_allocation_usd": h["initial"], "first_FILL_day": min((x["session"] for x in trades), default=None), "last_FILL_day": max((x["session"] for x in trades), default=None), "window_FILL_count": len(in_window), "window_order_count": len({x.get("order_id",x.get("CID")) for x in in_window}), "window_FILL_days": sorted({x["session"] for x in in_window}), "baseline_day": basis_day, "baseline_nav_usd": basis, "latest_valid_day": valid[-1]["day"] if valid else None, "latest_nav_usd": valid[-1]["nav_before_unverified_items_usd"] if valid else None, "covered_valuation_sessions": len(valid), "missing_valuation_days": [p["day"] for p in points if p["nav_before_unverified_items_usd"] is None], "recorded_allocation_flows_usd": sum((D(str(f["amount_USD"])) for f in h.get("allocation_flows",[])),D(0)), **metrics(points,basis)})
    # All book quantities must match the actual broker position inventory before interpretation.
    checks = {}
    for alias, prefix in [("legacy", "legacy/"), ("six", "six/")]:
        expected = defaultdict(lambda:D(0))
        cash = D(0)
        for h in histories:
            if h["id"].startswith(prefix) and h["kind"] != "composite_parent" and h["points"]:
                for s,q in h["points"][-1].get("quantity",{}).items():
                    expected[s] += q
        observed = {p["symbol"]:D(p["qty"]) for p in load(E / alias / "positions.json")}
        mismatch = {s:{"owned":expected.get(s,D(0)),"broker":observed.get(s,D(0))} for s in set(expected)|set(observed) if expected.get(s,D(0))!=observed.get(s,D(0))}
        checks[alias] = {"quantity_mismatch":mismatch,"unknown_FILL_count":len(unknown) if alias == "legacy" else sum(x["order_id"] not in six_owners for x in activities["six"] if x["activity_type"]=="FILL")}
    accounts = []
    for alias in activities:
        history = load(E/alias/"history.json")
        observations = []
        for t, equity in zip(history["timestamp"], history["equity"],strict=True):
            at = datetime.fromtimestamp(t,UTC)
            observations.append({"day":at.astimezone(NEW_YORK).date().isoformat(), "equity_usd":D(str(equity)), "at":at.isoformat(), "kind":"broker_daily_history"})
        account = load(E/alias/"account.json")
        pp = load(E/alias/"positions.json")
        mv = D(0)
        missing = []
        for p in pp:
            raw = prices.get((p["symbol"],END))
            if raw is None:
                missing.append({"symbol":p["symbol"],"quantity":p["qty"],"saved_market_value_usd":p["market_value"]})
            else:
                mv += D(p["qty"])*raw["price"]
        close_nav = None if missing else D(account["cash"])+mv
        last = {"day":END.isoformat(),"equity_usd":close_nav,"kind":"observed_cash_plus_positions_marked_same_day_raw_close","missing":missing}
        observations.append(last)
        funding = [x for x in activities[alias] if x["activity_type"] in {"JNLC","CSD","CSW","ACATC"}]
        nontrade = defaultdict(lambda:D(0))
        for x in activities[alias]:
            if x["activity_type"] != "FILL" and START.isoformat() <= x.get("date","") <= END.isoformat():
                nontrade[x["activity_type"]]+=D(x["net_amount"])
        initial = observations[0]["equity_usd"] if alias=="legacy" else D(1000000)
        peak,dd = initial,D(0)
        for p in observations:
            if p["equity_usd"] is not None:
                peak=max(peak,p["equity_usd"]);dd=min(dd,p["equity_usd"]/peak-1)
        accounts.append({"account":alias,"observations":observations,"baseline_usd":initial,"funding":funding,"posted_nontrade_usd":dict(nontrade),"current_broker_observed_equity_usd":account["equity"],"current_broker_observed_cash_usd":account["cash"],"reconstructed_close_equity_usd":close_nav,"raw_close_coverage_missing":missing,"profit_from_baseline_usd":None if close_nav is None else close_nav-initial,"return_pct":None if close_nav is None else (close_nav/initial-1)*100,"max_drawdown_pct":dd*100})
    payload = {"generated_at":datetime.now(UTC).isoformat(),"window":[str(START),str(END)],"trading_sessions":len(us_equity_session_dates(START,END)),"summaries":summaries,"accounts":accounts,"reconciliation":checks,"unknown_legacy_FILLs":unknown,"six_order_evidence":order_detail,"histories":histories,"source_bindings":CONSUMED}
    save(OUT/"actual.json",payload)
    with (OUT/"actual_daily.csv").open("w") as f:
        fields=["id","day","capital_usd","cash_from_principal_usd","holdings_value_usd","nav_before_unverified_items_usd","trading_pnl_usd","missing"]
        w=csv.DictWriter(f,fields);w.writeheader()
        for h in histories:
            for p in h["points"]:
                if p["day"]>=str(BASE):w.writerow({**{k:p.get(k) for k in fields},"id":h["id"]})
    print(json.dumps(clean({"summaries":[s for s in summaries if s["id"].count("/")<2],"checks":checks,"accounts":[{k:v for k,v in a.items() if k not in ['observations','funding','raw_close_coverage_missing']} for a in accounts]}),ensure_ascii=False,indent=2))


if __name__ == "__main__":main()
