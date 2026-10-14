"""Verify persisted accounts/diagnostics; never generates a policy or replays trades."""
import json
import math
import os
import resource
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

resource.setrlimit(resource.RLIMIT_CPU, (80, 85))
assert os.sched_getaffinity(0) == {0}
P = Path(__file__).resolve().parent
E = P / "economic"
O = E / "results"
checks = 0


def read(p):
    return json.loads(Path(p).read_text())


def ck(ok, label):
    global checks
    checks += 1
    assert ok, label


def eq(a, b, label, atol=2e-7):
    def scalar(x, y):
        return abs(x - y) <= atol + 2e-9 * abs(y) or (math.isnan(x) and math.isnan(y))
    if isinstance(a, (int, float, np.number)) and isinstance(b, (int, float, np.number)):
        ck(scalar(a, b), label)
    elif isinstance(a, list) and isinstance(b, list) and len(a) <= 8:
        ck(len(a) == len(b) and all(scalar(x, y) for x, y in zip(a, b)), label)
    else:
        ck(np.allclose(a, b, rtol=2e-9, atol=atol, equal_nan=True), label)


def metric(v, dates, given, bil=None):
    v = np.asarray(v, float)
    valid = np.isfinite(v).all() and (v > 0).all()
    ck(given["continuous_NAV_ready"] == bool(valid), "ready status")
    if not valid:
        ck(given["terminal_NAV"] is None and given["CAGR"] is None, "NA metrics")
        return
    r = np.diff(v) / v[:-1]
    eq(given["terminal_NAV"], v[-1], "terminal")
    elapsed = (pd.Timestamp(dates[-1]) - pd.Timestamp(dates[0])).days / 365.25
    eq(given["CAGR"], (v[-1] / v[0]) ** (1 / elapsed) - 1, "CAGR")
    vol = np.std(r, ddof=1)
    if vol > 1e-18:
        eq(given["Sharpe_netstd"], r.mean() / vol * np.sqrt(252), "net Sharpe")
    else:
        ck(given["Sharpe_netstd"] is None, "constant Sharpe")
    dd = v / np.maximum.accumulate(v) - 1
    eq(given["max_drawdown"], dd.min(), "drawdown")
    longest = run = 0
    for flag in dd < 0:
        run = run + 1 if flag else 0
        longest = max(longest, run)
    ck(given["longest_underwater_sessions"] == longest, "underwater duration")
    if bil is not None:
        bil = np.asarray(bil, float)
        if np.isfinite(bil).all() and (bil > 0).all():
            ex = r - np.diff(bil) / bil[:-1]
            ev = np.std(ex, ddof=1)
            if ev > 1e-18:
                eq(given["primary_physical_Sharpe_ex_BIL"], ex.mean() / ev * np.sqrt(252), "exBIL Sharpe")
        else:
            ck(given["primary_physical_Sharpe_ex_BIL"] is None, "BIL unavailable")


funded = read(O / "funded-results.json")
matrix = pd.read_parquet(O / "continuous-funded-NAV.parquet")
hostmatrix = pd.read_parquet(O / "continuous-host-NAV.parquet")
host = read(O / "host-results.json")
ck(matrix.shape == (1259, 120), "standalone matrix")
ck(hostmatrix.shape == (817, 92), "host matrix")
paths = sorted(O.glob("*-ledger.json"))
ck(len(paths) == 159, "physical inventory")
host_sleeves = {}
orders_count = daily_count = 0
cil_books = []
for fi, path in enumerate(paths):
    book = read(path)
    name = path.name.removesuffix("-ledger.json")
    cost = book["cost_each_side"]
    cash = float(book["initial"])
    unsettled = dividend = fee_total = 0.0
    q = 0
    events = defaultdict(list)
    orders = defaultdict(list)
    for event in book["events"]:
        events[event["at"][:10]].append(event)
    for order in book["orders"]:
        orders[order["day"]].append(order)
    for row in book["daily"]:
        day = row["date"]
        for event in events[day]:
            kind = event["event"]
            if kind == "proxy_cash_available":
                cash += event["amount"]
                if "sale_date" in event:
                    unsettled -= event["amount"]
                else:
                    dividend -= event["amount"]
                ck(event["due"] <= day, "cash availability")
            elif kind == "actual_exdate_entitlement":
                ck(event["quantity"] == q, "priorclose entitlement q")
                dividend += event["amount"]
            elif kind == "actual_split":
                ck(event["old_quantity"] == q, "split quantity")
                eq(q * event["ratio"], event["whole_quantity"] + event["fractional_entitlement"], "split rights")
                q = event["whole_quantity"]
            else:
                raise AssertionError(kind)
        for order in orders[day]:
            ck(order["q_before"] == q, "preorder actual holding")
            eq(order["cash_before"], cash, "preorder actual cash")
            n = order["quantity"]
            price = order["actual_reference"]
            ck(isinstance(n, int) and n >= 0, "whole frozen q")
            if order["status"] == "reference_filled":
                ck(order["first_price_age_minutes"] == 0, "no late fill")
                fee = n * price * cost
                eq(order["fee"], fee, "filled cost")
                if order["side"] == "buy":
                    ck(q == 0 and n * price + fee <= cash + 1e-8, "buy cash constraint")
                    cash -= n * price + fee
                    q = n
                else:
                    ck(q == n, "sell actual q")
                    unsettled += n * price - fee
                    q = 0
                fee_total += fee
            else:
                eq(order["fee"], 0, "no fill fee")
                if order["status"] == "no_fill_cash_gap_whole_buy_skip":
                    ck(n * price * (1 + cost) > cash - 1e-8, "cash gap is actual")
            eq(order["cash_after"], cash, "postorder cash")
            ck(order["q_after"] == q, "postorder holdings")
            orders_count += 1
        eq([row["cash"], row["unsettled"], row["dividend_receivable"], row["fees"]], [cash, unsettled, dividend, fee_total], "cash/receivable ledger conservation")
        ck(row["q"] == q and cash >= -1e-8 and row["pending"] is None, "daily holdings/pending")
        if row["unknown_fractional_CIL"]:
            ck(row["nav"] is None, "CIL NAV unknown")
        else:
            eq(row["nav"], cash + unsettled + dividend + q * row["raw_daily_closing_mark"], "raw close NAV equation")
        daily_count += 1
    nav = np.array([x["nav"] for x in book["daily"]], float)
    if name.startswith("host4k-"):
        host_sleeves[name.removeprefix("host4k-")] = nav
        ck(book["initial"] == 4000 and len(nav) == 817 and book["daily"][0]["date"] == "2017-10-04", "independent4k initialization")
    else:
        eq(nav, matrix[name].to_numpy(), "ledger matches120-column matrix")
        ck(book["initial"] == 20000 and len(nav) == 1259, "independent20k initialization")
        if "fees" in funded[name]:
            eq(funded[name]["fees"], fee_total, "reported fees")
            ck(funded[name]["order_attempts"] == len(book["orders"]), "attempt count")
            ck(funded[name]["filled"] == sum(x["status"] == "reference_filled" for x in book["orders"]), "fills count")
    if not np.isfinite(nav).all():
        cil_books.append(name)
    if fi % 40 == 0:
        print("ledgers", fi, flush=True)
for name in matrix:
    bps = name.rsplit("__", 1)[1]
    metric(matrix[name].to_numpy(), matrix.index, funded[name]["full"], matrix[f"BIL_BH__{bps}"].to_numpy())
hist = pd.read_parquet("data/research/account_review_2026_10/returns.parquet").loc[hostmatrix.index]
cols = ["S1__net10", "S2__net10", "S3__net10", "C2__net10", "F1__net10"]
growth = np.vstack([np.ones(5), np.cumprod(1 + hist[cols].to_numpy()[1:], axis=0)])
bases = {"HOST_F1_net10": 16000 * growth[:, 4], "HOST_EW_net10": 3200 * growth.sum(axis=1)}
comparisons = defaultdict(Counter)
for name in hostmatrix:
    hn, sn, cost = name.split("__")
    sleeve = np.full(817, 4000.0) if sn == "CASH" else host_sleeves[f"{sn}{'-BH' if sn in ('SPY','BIL') else ''}__{cost}"]
    eq(hostmatrix[name].to_numpy(), bases[hn] + sleeve, "drifting host + independent4k")
    metric(hostmatrix[name].to_numpy(), hostmatrix.index, host["results"][name]["metrics"], hostmatrix[f"{hn}__BIL__{cost}"].to_numpy())
    for control, report in host["results"][name]["controls"].items():
        reference = hostmatrix[f"{hn}__{control}__{cost}"].to_numpy()
        values = hostmatrix[name].to_numpy()
        if not np.isfinite(reference).all():
            ck(report["terminal_dollar_difference"] is None, "host control N/A")
            comparisons[cost + "__" + control]["NA"] += 1
        else:
            delta = values[-1] - reference[-1]
            eq(report["terminal_dollar_difference"], delta, "host dollar delta")
            comparisons[cost + "__" + control]["higher" if delta > 1e-7 else "lower" if delta < -1e-7 else "equal"] += 1
            sr_delta = host["results"][name]["metrics"]["Sharpe_netstd"] - host["results"][f"{hn}__{control}__{cost}"]["metrics"]["Sharpe_netstd"]
            comparisons[cost + "__" + control]["SRhigher" if sr_delta > 1e-9 else "SRlower" if sr_delta < -1e-9 else "SRequal"] += 1
diag = read(O / "fractional-diagnostic-results.json")
ck(len(diag) == 800, "800 diagnostics")
diag_summary = defaultdict(Counter)
for i, (name, report) in enumerate(diag.items()):
    with np.load(O / f"diagnostic-{name}.npz") as d:
        v = d["nav"]
        metric(v, matrix.index, report)
        eq(d["gross_daily"][1:], (np.diff(v) + d["fees"][1:] + d["borrow"][1:]) / v[:-1], "diagnostic gross/net cost identity")
        eq(d["overnight_gross_daily"][1:] + d["intraday_gross_daily"][1:], d["gross_daily"][1:], "intraday overnight additive")
        eq(d["overnight_gross_daily"][1:] + d["intraday_net_daily"][1:], np.diff(v) / v[:-1], "samebook net attribution")
        eq(report["fees_fraction_initial"], d["fees"].sum(), "diagnostic total fees")
        eq(report["borrow_fraction_initial"], d["borrow"].sum(), "diagnostic total borrow")
        ck(report["order_attempts"] == len(d["events"]), "diagnostic event count")
        ck(report["no_fill_attempts"] == int((d["events"]["status"] == 0).sum()), "diagnostic nonfill count")
        parts = name.split("__")
        key = parts[1] + "__" + parts[-1]
        diag_summary[key]["count"] += 1
        diag_summary[key]["terminal_above1"] += int(v[-1] > 1)
    if i % 200 == 0:
        print("diagnostics", i, flush=True)
report = read(P / "complete-costed-result.json")
ids = read(E / "linear-model-manifest.json")["candidate_ids"] + read(E / "HGB-model-manifest.json")["candidate_ids"]
for cost in (0, 1, 5, 20, 40):
    count = sum(matrix[f"{i}__{cost}"].iloc[-1] > 20000 for i in ids)
    ck(report["fee_panels"][str(cost)]["positive_terminal_profit"] == count, "profit count")
trials = [json.loads(x) for x in (E / "model-trial-ledger.jsonl").read_text().splitlines()]
trial_count = len({t["logical_trial_id"] for t in trials})
states = Counter(t.get("state", t.get("status")) for t in trials)
ck(trial_count == 3513 and len(trials) == 3610, "logical trials/ledger")
ck(dict(states) == report["inventory"]["trial_status_counts"], "trial states")
out = {"status": "pass", "checks": checks, "all_physical_ledgers": 159, "daily_rows_checked": daily_count, "orders_checked": orders_count, "funded_matrix_shape": list(matrix.shape), "host_matrix_shape": list(hostmatrix.shape), "all_diagnostic_npz": 800, "diagnostic_summary": {k: dict(v) for k, v in diag_summary.items()}, "host_comparisons": {k: dict(v) for k, v in comparisons.items()}, "CIL_unknown_books": cil_books, "trial_count": trial_count, "trial_rows": len(trials), "trial_states": dict(states), "report_primary_best_terminal": max((float(matrix[f'{i}__20'].iloc[-1]), i) for i in ids), "no_new_fit_prediction_or_account_replay": True, "CPU_affinity": list(os.sched_getaffinity(0))}
(P / "independent-final-accounts-verification.json").write_text(json.dumps(out, indent=2) + "\n")
print(json.dumps(out))
