"""Lead-only receipt arithmetic. Never generates signals, orders or accounts."""
from collections import Counter
from datetime import datetime, timezone
from itertools import combinations
from pathlib import Path
import json
import math
import statistics
import time

import numpy as np
import pandas as pd
from scipy.stats import kurtosis, rankdata, skew

ROOT = Path(__file__).resolve().parents[5]
RUN = Path(__file__).resolve().parents[1]
SRC = RUN / "worker/evidence"
CAPITAL = 20000.0
started = time.monotonic()

def read(path):
    return json.loads(Path(path).read_text())

close = pd.read_parquet(SRC / "close.parquet")
opens = pd.read_parquet(SRC / "open.parquet")
close.index = close.index.as_unit("ns")
opens.index = opens.index.as_unit("ns")
marks = close.ffill()
columns = list(close.columns)
position = {s: i for i, s in enumerate(columns)}
calendar = {d: i for i, d in enumerate(close.index)}
metrics, returns, checks = {}, {}, []
for receipt in sorted((SRC / "accounts").glob("*/complete.json")):
    meta = read(receipt)
    native = read(receipt.parent / "native.json")
    daily = pd.read_csv(receipt.parent / "ledger.csv", index_col=0, parse_dates=True)
    by_day = {}
    for order in native["orders"]:
        day = pd.Timestamp(order["trade_date"])
        decision = pd.Timestamp(order["decision_date"])
        assert calendar[day] == calendar[decision] + 1, (receipt, order)
        by_day.setdefault(day, []).append(order)
    shares = np.zeros(len(columns))
    cash = CAPITAL
    end_curve = []
    cost_spread = cost_margin = 0.0
    max_fill_error = 0.0
    prior_day = close.index[calendar[daily.index[0]] - 1]
    for day, mark in zip(daily.index, marks.reindex(daily.index).to_numpy(), strict=True):
        # Independent cash/debt and holdings reconstruction from recorded fills.
        funding = max(-cash, 0.0) * .065 / 360 * (day - prior_day).days
        cash -= funding
        cost_margin += funding
        orders = by_day.get(day, [])
        for order in orders:
            j = position[order["symbol"]]
            fill = order["price"]
            quoted_open = opens.at[day, order["symbol"]]
            if np.isfinite(quoted_open):
                max_fill_error = max(max_fill_error, abs(fill - quoted_open))
            shares[j] += order["dollar_trade"] / fill
            cash -= order["dollar_trade"]
        charge = sum(abs(o["dollar_trade"]) for o in orders) * meta["cost_bp_per_side"] / 10000
        cash -= charge
        cost_spread += charge
        end_curve.append(cash + np.nansum(shares * mark))
        prior_day = day
    equity = np.asarray(end_curve)
    net = equity / np.r_[CAPITAL, equity[:-1]] - 1
    peak = np.maximum.accumulate(np.r_[CAPITAL, equity])[1:]
    underwater = longest = 0
    for flag in equity < peak - 1e-8:
        underwater = underwater + 1 if flag else 0
        longest = max(longest, underwater)
    prev = np.r_[CAPITAL, daily.equity.to_numpy()[:-1]]
    errors = {
        "equity_max_error_usd": float(np.max(np.abs(equity - daily.equity))),
        "return_max_error": float(np.max(np.abs(net - daily.net))),
        "receipt_end_error_usd": float(equity[-1] - meta["end_equity_usd"]),
        "spread_error_usd": float(cost_spread - np.dot(prev, daily.cost_spread)),
        "margin_error_usd": float(cost_margin - np.dot(prev, daily.cost_margin)),
        "open_fill_error_usd_per_share": max_fill_error,
    }
    assert all(abs(v) < 1e-5 for v in errors.values()), (receipt, errors)
    assert not any(native["info"][k] for k in ["bankrupt", "unknown_symbols", "delist_exits"])
    name = receipt.parent.name
    checks.append({"account": name, "frozen_halted_trades": native["info"]["frozen_halted_trades"], **errors})
    returns[name] = pd.Series(net, index=daily.index)
    metrics[name] = {
        "net_profit_usd": float(equity[-1] - CAPITAL),
        "volatility_annual": float(net.std(ddof=1) * np.sqrt(252)),
        "max_drawdown": float(np.min(equity / peak - 1)),
        "longest_underwater_sessions": longest,
        "cagr_252": float((equity[-1] / CAPITAL) ** (252 / len(net)) - 1),
        "spread_usd": cost_spread, "margin_usd": cost_margin,
        "orders": len(native["orders"]), "trade_sessions": len(by_day),
    }

rows, pairs = read(SRC / "comparisons.json"), []
for row in rows:
    a_name = Path(row["candidate_metrics"]["account"]).name
    b_name = Path(row["matched_control_metrics"]["account"]).name
    a, b = returns[a_name], returns[b_name]
    assert a.index.equals(b.index)
    for key, name in [("candidate_metrics", a_name), ("matched_control_metrics", b_name)]:
        for metric in ["net_profit_usd", "volatility_annual", "max_drawdown", "cagr_252", "longest_underwater_sessions"]:
            assert abs(metrics[name][metric] - row[key][metric]) < 1e-6, (name, metric)
    increment = metrics[a_name]["net_profit_usd"] - metrics[b_name]["net_profit_usd"]
    assert abs(increment - row["increment_matched_usd"]) < 1e-6
    rng = np.random.default_rng(20261102)
    block_starts = rng.integers(0, len(a) - 21 + 1, size=(1000, math.ceil(len(a) / 21)))
    indices = (block_starts[:, :, None] + np.arange(21)).reshape(1000, -1)[:, :len(a)]
    delta = CAPITAL * (np.prod(1 + a.to_numpy()[indices], axis=1) - np.prod(1 + b.to_numpy()[indices], axis=1))
    ci = np.quantile(delta, [.025, .975]).tolist()
    assert np.max(np.abs(np.array(ci) - row["paired_uncertainty"]["usd_increment_95pct"])) < 1e-5
    pairs.append({"candidate": row["candidate"], "cost": row["cost_bp_per_side"],
                  "increment_usd": increment, "ci95_usd": ci,
                  "candidate_metrics": metrics[a_name], "control_metrics": metrics[b_name]})

events = [json.loads(line) for line in (RUN.parents[1] / "trials.jsonl").read_text().splitlines()]
starts = [e for e in events if e["event"] == "started"]
finishes = [e for e in events if e["event"] == "finished"]
unresolved = sorted({e["trial_id"] for e in starts} - {e["trial_id"] for e in finishes})
assert not unresolved
trials = sum(e["count"] for e in events if e["event"] in ("prior_exposure", "started") and e["counts_as_trial"])

selection = max([r for r in pairs if r["cost"] == 10], key=lambda r: r["increment_usd"])
assert selection["candidate"] == "A4"
a4 = returns["candidate-A4-10"]
rf = close.BIL.pct_change(fill_method=None).reindex(a4.index)
x = (a4 - rf).to_numpy()
daily_sr = x.mean() / x.std(ddof=1)
centered = x - x.mean()
inflation = max(1.0, 1 + 2 * sum((1 - lag / 22) * np.dot(centered[lag:], centered[:-lag]) / np.dot(centered, centered) for lag in range(1, 22)))
denominator = math.sqrt(1 - skew(x, bias=False) * daily_sr + (kurtosis(x, fisher=False, bias=False) - 1) / 4 * daily_sr**2)
normal = statistics.NormalDist()
gamma = 0.5772156649015329
expected_max = (1 - gamma) * normal.inv_cdf(1 - 1 / trials) + gamma * normal.inv_cdf(1 - 1 / (trials * math.e))
dsr = min(normal.cdf((daily_sr * math.sqrt(n - 1) - expected_max) / denominator) for n in [len(x), len(x) / inflation])
assert abs(dsr - read(SRC / "dsr-detail.json")["dsr"]) < 1e-10
matrix = pd.read_csv(SRC / "candidate-bil-excess-matrix.csv", index_col=0, parse_dates=True)
for candidate in matrix.columns:
    assert np.max(np.abs(matrix[candidate] - (returns[f"candidate-{candidate}-10"] - rf))) < 1e-10
blocks = np.array_split(np.arange(len(matrix)), 8)
contributions = []
for group in combinations(range(8), 4):
    train = matrix.iloc[np.concatenate([blocks[i] for i in group])].to_numpy()
    test = matrix.iloc[np.concatenate([blocks[i] for i in range(8) if i not in group])].to_numpy()
    train_sr = train.mean(axis=0) / train.std(axis=0, ddof=1)
    test_sr = test.mean(axis=0) / test.std(axis=0, ddof=1)
    winners = np.flatnonzero(np.isclose(train_sr, train_sr.max(), atol=1e-12 / np.sqrt(252), rtol=0))
    omega = (rankdata(test_sr, method="average")[winners] - .5) / matrix.shape[1]
    contributions.append(float(np.mean(np.where(omega < .5, 1.0, np.where(omega > .5, 0.0, .5)))))
pbo = float(np.mean(contributions))
assert abs(pbo - read(SRC / "pbo.json")["pbo"]) < 1e-12

# Allocation diagnostics from saved costed histories only: no new accounts.
vd = returns["warmup-d1-10"].reindex(close.index).rolling(63).std(ddof=1)
vs = returns["warmup-s3-10"].reindex(close.index).rolling(63).std(ddof=1)
month_end = pd.Series(close.index.to_period("M"), index=close.index).ne(pd.Series(close.index.to_period("M"), index=close.index).shift(-1))
alpha = (vs / (vd + vs)).where((vd > 0) & (vs > 0), .5).where(month_end).ffill().fillna(.5).clip(.25, .75)
alpha_dev = alpha.reindex(a4.index)
allocation = {"mean_daily_target_D1_share": float(alpha_dev.mean()),
              "min_D1_share": float(alpha_dev.min()), "max_D1_share": float(alpha_dev.max()),
              "sessions_at_75pct": int(np.isclose(alpha_dev, .75).sum()),
              "sessions": len(alpha_dev), "monthly_decisions": int(month_end.reindex(a4.index).sum()),
              "interpretation": "Known close-target allocation; observed shares drift. Mean is post-hoc descriptive, never a historical forecast."}
counts = read(SRC / "counts-with-forensics.json")
assert counts["counts"]["financial_accounts"] == len(checks) == 301
assert counts["counts"]["economic_comparisons"] == 23 * 2 * 2 + 4 + 2 == 98
assert len(list((SRC / "accounts").glob("*/started.json"))) == 301
assert trials == 52 and len(starts) == len(finishes) == 48
result = {
    "observed_at": datetime.now(timezone.utc).isoformat(),
    "scope": "Independent read-only arithmetic from existing prices/fills; no backtest, signal search or new numerical account",
    "accounts_checked": len(checks), "comparisons_recomputed": len(pairs),
    "account_errors": checks, "pairs": pairs,
    "controls": {k:v for k,v in metrics.items() if k.startswith("control-")},
    "trial_count": trials, "failed_starts": sum(e["status"] == "failed" for e in finishes),
    "completed_starts": sum(e["status"] == "complete" for e in finishes), "unresolved_trials": unresolved,
    "dsr": dsr, "bil_excess_sharpe": float(daily_sr * np.sqrt(252)), "hac_inflation": inflation,
    "pbo": pbo, "pbo_scope": "Sharpe ranking diagnostic, not dollar-increment selection or complete ancestry",
    "allocation": allocation,
    "native_account_seconds": sum(read(p)["elapsed_seconds"] for p in (SRC / "accounts").glob("*/complete.json")),
    "receipt_audit_elapsed_seconds": time.monotonic() - started,
}
(RUN / "lead/raw-audit.json").write_text(json.dumps(result, indent=2) + "\n")
print(json.dumps({k:result[k] for k in ["accounts_checked","comparisons_recomputed","trial_count","dsr","pbo","allocation","receipt_audit_elapsed_seconds"]}, indent=2))
