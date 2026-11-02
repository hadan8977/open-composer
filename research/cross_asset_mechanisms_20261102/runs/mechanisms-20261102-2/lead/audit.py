"""Independent receipt arithmetic; no engine replay or new economic trial."""
from datetime import datetime, timezone
from pathlib import Path
import json
import math
import statistics
import time

import numpy as np
import pandas as pd
from scipy.stats import skew, kurtosis

ROOT = Path(__file__).resolve().parents[5]
RUN = Path(__file__).resolve().parents[1]
BASE = RUN.parents[1]
SRC = RUN / "worker/evidence"
OLD = BASE / "runs/mechanisms-20261102-1/worker/evidence"
CAPITAL = 20000.
started = time.monotonic()

def read(path):
    return json.loads(Path(path).read_text())

close, opens = [pd.read_parquet(OLD / f"{name}.parquet") for name in ["close", "open"]]
close.index, opens.index = close.index.as_unit("ns"), opens.index.as_unit("ns")
symbols = list(close.columns)
position = {s: i for i, s in enumerate(symbols)}
calendar = {d: i for i, d in enumerate(close.index)}
common = pd.read_csv(SRC / "common-close-events.csv", index_col=0, parse_dates=True).iloc[:, 0]
d1, s3 = [pd.read_parquet(SRC / f"source-{s}-close-targets.parquet").reindex(columns=symbols) for s in ["d1", "s3"]]
for frame in [d1, s3]:
    frame.index = frame.index.as_unit("ns")
allocations, allocation_checks = {}, []
for cost in [10, 20]:
    saved = pd.read_csv(SRC / f"allocation-close-history-{cost}.csv", index_col=0, parse_dates=True)
    histories = [pd.read_csv(OLD / f"accounts/warmup-{s}-{cost}/ledger.csv", index_col=0, parse_dates=True).net.reindex(close.index) for s in ["d1", "s3"]]
    vd, vs = [x.rolling(63).std(ddof=1) for x in histories]
    valid = (vd > 0) & (vs > 0)
    raw = (vs / (vd + vs)).where(valid, .5).clip(.25, .75)
    months = close.index.to_period("M")
    monthly = np.r_[months[:-1] != months[1:], True]
    assert np.array_equal(monthly, saved.monthly)
    a4 = l1 = h1 = .5
    previous_decision, eligible = None, []
    records = []
    # Explicit sequential loop excludes current H1 observation before appending it.
    for i, day in enumerate(close.index):
        if monthly[i]:
            a4 = float(raw.iloc[i])
            l1 = .5 if previous_decision is None else previous_decision
            h1 = float(np.mean(eligible)) if eligible else .5
            previous_decision = a4
            if valid.iloc[i]:
                eligible.append(a4)
        records.append([a4, l1, h1])
    rules = pd.DataFrame(records, index=close.index, columns=["A4", "L1", "H1"])
    error = float(np.max(np.abs(rules.to_numpy() - saved[rules.columns].to_numpy())))
    assert error < 1e-12
    allocations[cost] = rules
    effective = rules.A4.shift(1).loc["2023-09-18":"2025-12-31"]
    row = next(r for r in read(SRC / "allocation-summary.json") if r["cost"] == cost)
    assert abs(effective.mean() - row["open_effective_mean"]) < 1e-12
    assert effective.eq(.75).sum() == row["effective_sessions_at_cap"] == 471
    assert int(pd.Series(monthly, index=close.index).shift(1).reindex(effective.index).sum()) == 27
    assert int((valid & pd.Series(monthly, index=close.index) & (close.index < "2023-09-18")).sum()) == 89
    allocation_checks.append({"cost": cost, "maximum_rule_error": error, "effective_mean": float(effective.mean()),
                              "effective_updates": 27, "sessions_at_cap": 471, "valid_prehistory_decisions": 89})

diagnostics = read(SRC / "account-diagnostics.json")
metrics, returns, yearly, checks = {}, {}, {}, []
for diagnostic in diagnostics:
    folder = ROOT / diagnostic["account"]
    meta, native = read(folder / "complete.json"), read(folder / "native.json")
    daily = pd.read_csv(folder / "ledger.csv", index_col=0, parse_dates=True)
    name, cost = folder.name, meta["cost_bp_per_side"]
    alpha = None
    if name.startswith("fixed-"):
        alpha = float(name.split("-", 2)[2])
    elif name.startswith("candidate-A1-"): alpha = .25
    elif name.startswith("candidate-A2-"): alpha = .75
    elif name.startswith("control-original50-"): alpha = .5
    elif name.startswith("candidate-A4-"): alpha = allocations[cost].A4
    elif name.startswith("attribution-"): alpha = allocations[cost][name.split("-")[1]]
    assert alpha is not None or name.startswith("control-s3-")
    targets = None if alpha is None else d1.mul(alpha, axis=0) + s3.mul(1 - alpha, axis=0)
    by_day = {}
    for order in native["orders"]:
        day, decision = pd.Timestamp(order["trade_date"]), pd.Timestamp(order["decision_date"])
        assert calendar[day] == calendar[decision] + 1
        by_day.setdefault(day, []).append(order)
    if targets is not None:
        expected = common.loc[meta["first_fill_decision"]:meta["window"][1]]
        expected_dates = set(expected.index[expected]) | {pd.Timestamp(meta["first_fill_decision"])}
        assert set(pd.to_datetime(native["config"]["signal_dates"])) == expected_dates
    shares, cash = np.zeros(len(symbols)), CAPITAL
    equity, margin, fees, turnover, maximum_orders = [], 0., 0., [], 0.
    error_fill = error_target = 0.
    previous_day = close.index[calendar[daily.index[0]] - 1]
    for day in daily.index:
        funding = max(-cash, 0.) * .065 / 360 * (day - previous_day).days
        cash -= funding
        margin += funding
        px = opens.loc[day].to_numpy()
        held_open = np.where(shares != 0, shares * px, 0.)
        e_open = cash + np.nansum(held_open)
        orders = by_day.get(day, [])
        for order in orders:
            j = position[order["symbol"]]
            error_fill = max(error_fill, abs(order["price"] - px[j]))
            shares[j] += order["dollar_trade"] / order["price"]
            cash -= order["dollar_trade"]
        if orders and targets is not None:
            decision = pd.Timestamp(orders[0]["decision_date"])
            held_after = np.where(shares != 0, shares * px, 0.)
            error_target = max(error_target, float(np.nanmax(np.abs(held_after - targets.loc[decision].to_numpy() * e_open))))
        amount = sum(abs(o["dollar_trade"]) for o in orders)
        turnover.append(amount / e_open)
        charge = amount * cost / 10000
        fees += charge
        cash -= charge
        maximum_orders = max(maximum_orders, max((abs(o["dollar_trade"]) for o in orders), default=0))
        equity.append(cash + np.nansum(np.where(shares != 0, shares * close.loc[day].to_numpy(), 0.)))
        previous_day = day
    curve = np.array(equity)
    previous = np.r_[CAPITAL, curve[:-1]]
    net = curve / previous - 1
    peak = np.maximum.accumulate(np.r_[CAPITAL, curve])[1:]
    longest = streak = 0
    for flag in curve < peak - 1e-8:
        streak = streak + 1 if flag else 0
        longest = max(longest, streak)
    errors = {"equity_max_error_usd": float(np.max(np.abs(curve - daily.equity))),
              "return_max_error": float(np.max(np.abs(net - daily.net))),
              "receipt_end_error_usd": float(curve[-1] - meta["end_equity_usd"]),
              "spread_error_usd": float(fees - np.dot(previous, daily.cost_spread)),
              "margin_error_usd": float(margin - np.dot(previous, daily.cost_margin)),
              "fill_error": error_fill, "prescribed_target_error_usd": error_target,
              "turnover_error": float(np.max(np.abs(np.array(turnover) - daily.turnover)))}
    assert all(abs(v) < 1e-5 for v in errors.values()), (name, errors)
    assert not any(native["info"][k] for k in ["bankrupt", "unknown_symbols", "delist_exits", "frozen_halted_trades"])
    returns[name] = pd.Series(net, index=daily.index)
    yearly[name] = pd.Series(curve - previous, index=daily.index).groupby(daily.index.year).sum().to_dict()
    metrics[name] = {"net_profit_usd": float(curve[-1] - CAPITAL), "volatility_annual": float(net.std(ddof=1) * np.sqrt(252)),
        "max_drawdown": float(np.min(curve / peak - 1)), "cagr_252": float((curve[-1] / CAPITAL) ** (252 / len(curve)) - 1),
        "longest_underwater_sessions": longest, "spread_usd": fees, "margin_usd": margin,
        "turnover_annual": float(np.mean(turnover) * 252), "max_order_usd": maximum_orders,
        "order_count": len(native["orders"]), "trade_sessions": len(by_day)}
    checks.append({"account": name, **errors})

pairs = []
for row in read(SRC / "comparisons.json"):
    an, bn = [Path(row[k]["account"]).name for k in ["candidate_metrics", "control_metrics"]]
    a, b = returns[an], returns[bn]
    assert a.index.equals(b.index)
    for name, key in [(an, "candidate_metrics"), (bn, "control_metrics")]:
        for metric in ["net_profit_usd", "volatility_annual", "max_drawdown", "cagr_252", "longest_underwater_sessions", "turnover_annual", "max_order_usd", "trade_sessions"]:
            assert abs(metrics[name][metric] - row[key][metric]) < 1e-6, (name, metric)
    increment = metrics[an]["net_profit_usd"] - metrics[bn]["net_profit_usd"]
    assert abs(increment - row["increment_usd"]) < 1e-6
    rng = np.random.default_rng(20261102)
    starts = rng.integers(0, len(a) - 20, size=(1000, math.ceil(len(a) / 21)))
    take = (starts[:, :, None] + np.arange(21)).reshape(1000, -1)[:, :len(a)]
    difference = CAPITAL * (np.prod(1 + a.to_numpy()[take], axis=1) - np.prod(1 + b.to_numpy()[take], axis=1))
    ci = np.quantile(difference, [.025, .975]).tolist()
    assert np.max(np.abs(np.array(ci) - row["paired_uncertainty"]["usd_increment_95pct"])) < 1e-5
    if row["control"] == "same_risk_fixed_D1":
        assert abs(metrics[bn]["volatility_annual"] - metrics[an]["volatility_annual"]) < 1e-6
        for e in row["match"]["evaluations"]:
            assert abs(metrics[Path(e["account"]).name]["volatility_annual"] - e["volatility"]) < 1e-10
        assert len(row["match"]["roots"]) == 1 and row["match"]["monotone_on_frozen_grid"]
    pairs.append({"candidate": row["candidate"], "cost": row["cost"], "control": row["control"],
                  "increment_usd": increment, "ci95_usd": ci,
                  "yearly_difference_usd": {y: yearly[an][y] - yearly[bn][y] for y in yearly[an]}})

events = [json.loads(line) for line in (BASE / "trials.jsonl").read_text().splitlines()]
starts, ends = [[e for e in events if e["event"] == kind] for kind in ["started", "finished"]]
assert {e["trial_id"] for e in starts} == {e["trial_id"] for e in ends}
n_trials = sum(e["count"] for e in events if e["event"] in ["prior_exposure", "started"] and e["counts_as_trial"])
assert n_trials == 54 and sum(e["status"] == "failed" for e in ends) == 24
normal = statistics.NormalDist()
gamma = .5772156649015329
expected_max = (1 - gamma) * normal.inv_cdf(1 - 1 / n_trials) + gamma * normal.inv_cdf(1 - 1 / (math.e * n_trials))
statistics_checked = {}
for key, expected in read(SRC / "dsr-detail.json").items():
    name = ("candidate-" if key.startswith("A4") else "attribution-") + key
    r = returns[name]
    x = (r - close.BIL.pct_change(fill_method=None).reindex(r.index)).to_numpy()
    sr = x.mean() / x.std(ddof=1)
    centered = x - x.mean()
    inflation = max(1., 1 + 2 * sum((1 - lag / 22) * np.dot(centered[lag:], centered[:-lag]) / np.dot(centered, centered) for lag in range(1, 22)))
    denominator = math.sqrt(1 - skew(x, bias=False) * sr + (kurtosis(x, fisher=False, bias=False) - 1) * sr**2 / 4)
    dsr = min(normal.cdf((sr * math.sqrt(n - 1) - expected_max) / denominator) for n in [len(x), len(x) / inflation])
    assert abs(dsr - expected["dsr"]) < 1e-10
    statistics_checked[key] = {"dsr": dsr, "bil_excess_sharpe": sr * math.sqrt(252), "hac_inflation": inflation}
assert len(checks) == 50 and len(pairs) == 46
assert len(list((SRC / "accounts").glob("*/complete.json"))) == len(list((SRC / "accounts").glob("*/started.json"))) == 40
output = {"observed_at": datetime.now(timezone.utc).isoformat(), "scope": "Independent receipt and allocation arithmetic; no account replay or selection",
          "accounts_checked": len(checks), "comparisons_recomputed": len(pairs), "account_errors": checks,
          "allocation_checks": allocation_checks, "pairs": pairs, "account_metrics": metrics,
          "trial_count": n_trials, "failed_starts": 24, "unresolved_trials": [], "statistics": statistics_checked,
          "receipt_audit_elapsed_seconds": time.monotonic() - started}
(RUN / "lead/raw-audit.json").write_text(json.dumps(output, indent=2) + "\n")
print(json.dumps({k: output[k] for k in ["accounts_checked", "comparisons_recomputed", "trial_count", "allocation_checks", "receipt_audit_elapsed_seconds"]}, indent=2))
