"""Reporting completion and result checks; never generates or selects a policy."""

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path.cwd()
P = Path(__file__).parent
R = P / "results"


def bind(path):
    path = Path(path)
    return {
        "path": str(path.resolve().relative_to(ROOT)),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "bytes": path.stat().st_size,
    }


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def main():
    report = json.loads((R / "empirical-report.json").read_text())
    matrix = pd.read_csv(R / "daily-return-matrix.csv", index_col=0, parse_dates=True)
    nav = pd.read_csv(R / "full-NAV-matrix.csv", index_col=0, parse_dates=True)
    payload = json.loads((P / "inputs/bars_all-01.json").read_text())
    bars = payload["bars"]
    # Read the already accepted current-vintage adjusted input, without new intake.
    price = {}
    for symbol in ["SPY", "BIL"]:
        rows = bars[symbol]
        price[symbol] = pd.Series(
            {
                pd.Timestamp(row["t"])
                .tz_convert("America/New_York")
                .tz_localize(None)
                .normalize(): row["c"]
                for row in rows
            }
        ).sort_index()
    market = price["SPY"].pct_change(fill_method=None).reindex(matrix.index)
    bil = price["BIL"].pct_change(fill_method=None).reindex(matrix.index)
    assert market.notna().all() and bil.notna().all()
    beta = {}
    for candidate in report["fixed_primary_ids"]:
        beta[candidate] = {}
        for bps in [20, 40]:
            y = matrix[candidate + "__" + str(bps)]
            x = market
            xe, ye = x - bil, y - bil
            beta[candidate][str(bps)] = {
                "beta_ex_BIL": float(np.cov(xe, ye, ddof=1)[0, 1] / xe.var(ddof=1)),
                "beta_raw_return": float(np.cov(x, y, ddof=1)[0, 1] / x.var(ddof=1)),
                "correlation_raw_SPY": float(x.corr(y)),
                "observations": len(y),
                "first_return_date": str(y.index[0].date()),
                "last_return_date": str(y.index[-1].date()),
            }
    save(
        R / "descriptive-beta.json",
        {
            "schema_version": 1,
            "as_of_utc": datetime.now(UTC).isoformat(),
            "purpose": (
                "Complete preregistered descriptive beta attribution at final result acceptance; "
                "no new policy, threshold, candidate, selection or economic run."
            ),
            "formula": (
                "OLS with intercept: cov(candidate daily return minus BIL total return, "
                "SPY adjusted daily total return minus BIL total return) / var(SPY excess return). "
                "Raw-return beta also disclosed; same complete daily calendar, "
                "initial close excluded."
            ),
            "scope": (
                "Full approved 2020-01-02 initialization to 2026-10-12, all seen, "
                "current-vintage input; descriptive only and never used to trade or claim Alpha."
            ),
            "bindings": {
                "report": bind(R / "empirical-report.json"),
                "return_matrix": bind(R / "daily-return-matrix.csv"),
                "adjusted_input": bind(P / "inputs/bars_all-01.json"),
                "code": bind(Path(__file__)),
            },
            "rows": beta,
        },
    )

    checks = []
    files = sorted(R.glob("*-cash-ledger.csv"))
    for f in files:
        book = pd.read_csv(f, index_col=0, parse_dates=True)
        assert book.index.is_unique and book.index.is_monotonic_increasing, f.name
        assert book.notna().all().all(), f.name
        components = book[
            [
                "proxy_available_cash",
                "unavailable_sales_credit",
                "dividend_receivable",
                "position_value",
            ]
        ].sum(axis=1)
        error = float((book.nav - components).abs().max())
        assert error < 1e-7 and book.proxy_available_cash.min() >= -1e-7, f.name
        assert book.shares.min() >= 0, f.name
        label = f.name.removesuffix("-cash-ledger.csv")
        if label in nav:
            assert book.index.equals(nav.index), f.name
            assert float((book.nav - nav[label]).abs().max()) < 1e-7, f.name
        checks.append({"ledger": f.name, "rows": len(book), "max_NAV_component_error_USD": error})
    orders = json.loads((R / "orders.json").read_text())
    for label, account in report["primary_and_control_accounts"].items():
        if label.endswith("__20") or label.endswith("__40"):
            name, bps = label.rsplit("__", 1)
            selected = [o for o in orders if o["candidate"] == name and o["cost_bps"] == int(bps)]
            fees = sum(o.get("cost", 0) for o in selected if o["accepted"])
            assert abs(fees - account["funding"]["side_cost_dollars"]) < 1e-7, label
            assert (
                sum(o["accepted"] and o["side"] == "buy" for o in selected)
                == account["funding"]["entries"]
            ), label
    assert matrix.index.equals(nav.index[1:])
    assert float((matrix - nav.pct_change(fill_method=None).iloc[1:]).abs().max().max()) < 1e-12
    save(
        R / "result-accounting-checks.json",
        {
            "schema_version": 1,
            "status": "pass",
            "checks": (
                "Every persisted 20k, 10k EW component and independently initialized "
                "4k host ledger "
                "balances NAV components and nonnegative cash/holdings; complete matrix "
                "equals ledgers; actual modeled fees and entry counts equal report/order records; "
                "daily returns include exactly the post-initialization continuous calendar."
            ),
            "persisted_ledger_count": len(files),
            "ledger_checks": checks,
            "orders_checked": len(orders),
            "bindings": {
                "report": bind(R / "empirical-report.json"),
                "orders": bind(R / "orders.json"),
                "NAV_matrix": bind(R / "full-NAV-matrix.csv"),
                "daily_matrix": bind(R / "daily-return-matrix.csv"),
            },
            "no_new_economic_policy_or_source": True,
        },
    )
    print(json.dumps({"beta": beta, "balanced_cash_ledgers": len(files)}, indent=2))


if __name__ == "__main__":
    main()
