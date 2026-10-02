# ruff: noqa: E501
"""Historical replay of the book v1.2 production targets through the order engine (T-20261002-28).

For the last ``--sessions`` sessions of the research snapshot, both accounts:

* the target of decision date D (``open_composer.book_paper.v12_targets``, production mode: the
  newest tranche keeps every name, it cannot know the close of D+1);
* a fake ``AccountState``: the previous day's holdings (the post-trade quantities of the previous
  replay plan, whole shares, the first day starts from the plan of the day before, built with
  ``min_notional = 0``), equity fixed at the $1M basis, every name easy to borrow and shortable;
* ``build_plan`` with ``as_of`` = the execution date and ``now`` = 14:00 ET of that day.

Every day is executed whatever the checks say (the point is to see which checks would block a
normal day, not to let one failure cascade).  No broker client is created.

    scripts/run_capped.sh --mem 1.2G -- uv run python scripts/book_v12_engine_replay.py
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from open_composer.book_paper import v12_targets as v12  # noqa: E402
from open_composer.book_paper.plan import AccountState, AssetInfo, build_plan  # noqa: E402
from open_composer.market_sessions import NEW_YORK  # noqa: E402

OUT = ROOT / "reports/research/iterations/t20261002_book_v12/engine-replay.json"
EQUITY = 1_000_000.0
KEY_CHECKS = (
    "net_dollar",
    "gross_stock",
    "max_name_weight",
    "gross_leverage",
    "beta_neutral",
    "core_leg",
)
# Written after the first run, from its failing rows (data/research/book_v12_t28/ and
# engine-replay.json "failure_events").  Both are real findings, not replay artefacts.
EXPLANATIONS: dict[str, str] = {
    "reference_prices_complete": (
        "REAL ENGINE ISSUE (lead decides). A name held from earlier days has no close on D, and the "
        "engine blocks the whole plan while any held or target name lacks a reference price. Checked "
        "against prices/2026.parquet for the M0_U3000 run: of 23 name-events 22 stop trading "
        "(last close = D-1: cash acquisitions, mergers, delistings) and 1 (ARTL) has a missing close "
        "on D but trades later (halt or data gap). The replay assumes the broker removes the "
        "position the day after it first blocks the plan; the real removal date is unknown, so an "
        "event may block 1 or more sessions. Not a generator error: a name without a close cannot "
        "be sized or ordered (the generator drops it and logs it)."
    ),
    "beta_neutral": (
        "REAL CONTRACT ISSUE (lead decides). The hedge is held in fixed SPY shares per tranche "
        "(T-25 R6), while the stock legs drift with prices. After a market move the residual "
        "sum(beta x weight) + hedge leaves +-0.03..0.05 (limit 0.05, not loosened). Decomposition "
        "on 2026-07-29 (data/research/book_v12_t28/diag_beta.py): stock beta at the sizing prices "
        "-0.511, at D -0.456, hedge value at D +0.505, SPY -1.3% over the week."
    ),
}


def fake_assets(symbol: str) -> AssetInfo:
    return AssetInfo(symbol=symbol, easy_to_borrow=True, shortable=True, tradable=True)


def pct(values: list[float], q: float) -> float:
    return float(np.percentile(values, q)) if values else float("nan")


def run(
    variant: str, sessions: int, data_root: Path | None, out: Path, *, diagnostics: bool = True
) -> dict:
    root = Path(data_root) if data_root else v12.default_data_root()
    cal = pd.read_parquet(root / "panel/_calendar.parquet")
    dates = pd.DatetimeIndex(cal["trade_date"])
    last = len(dates) - 1  # last session: the final execution date
    exec_positions = list(range(last - sessions + 1, last + 1))
    dec_positions = [p - 1 for p in exec_positions]
    init_pos = dec_positions[0] - 1
    ctx = v12.V12Context.open(root, first_date=dates[init_pos], last_date=dates[dec_positions[-1]])
    state: dict[str, dict[str, float]] = {"quant1": {}, "quant2": {}}
    rows: dict[str, list[dict]] = {"quant1": [], "quant2": []}
    lookahead_rows: list[dict] = []
    # initial holdings: the plan of the day before the window, no minimum notional
    init = v12.build_v12_bundle(
        dates[init_pos], variant=variant, context=ctx, logged_at_utc="replay"
    )
    for account, target in init.targets.items():
        plan = build_plan(
            target,
            AccountState(equity=EQUITY, positions={}),
            as_of=target.execution_date,
            now=datetime.combine(target.execution_date, time(14, 0), NEW_YORK),
            asset_lookup=fake_assets,
            min_notional=0.0,
        )
        state[account] = {s: float(q) for s, q in plan.payload["post_trade_qty"].items()}
    for p_d in dec_positions:
        t_d = dates[p_d]
        bundle = v12.build_v12_bundle(
            t_d, variant=variant, context=ctx, logged_at_utc="replay", fill_lookahead=False
        )
        la_diff = None
        if diagnostics:
            la = v12.build_v12_bundle(
                t_d, variant=variant, context=ctx, logged_at_utc="replay", fill_lookahead=True
            )
            la_diff = {
                form: {
                    "n_names_differ": int(
                        (bundle.books[form].stock_shares != la.books[form].stock_shares).sum()
                    ),
                    "abs_dollar_diff_over_equity": float(
                        np.abs(
                            (bundle.books[form].stock_shares - la.books[form].stock_shares)
                            * np.where(np.isfinite(bundle.close_d), bundle.close_d, 0.0)
                        ).sum()
                        / EQUITY
                    ),
                }
                for form in ("F1", "F2")
            }
            lookahead_rows.append({"decision_date": str(t_d.date()), **la_diff})
        for account, target in bundle.targets.items():
            held = state[account]
            plan = build_plan(
                target,
                AccountState(equity=EQUITY, positions=dict(held)),
                as_of=target.execution_date,
                now=datetime.combine(target.execution_date, time(14, 0), NEW_YORK),
                asset_lookup=fake_assets,
                min_notional=100.0,
            )
            p = plan.payload
            checks = {c["name"]: c for c in p["checks"]}
            held_unpriced = sorted(s for s in held if s not in target.reference_prices)
            rows[account].append(
                {
                    "decision_date": p["decision_date"],
                    "execution_date": p["execution_date"],
                    "status": p["status"],
                    "blocked_by": p["blocked_by"],
                    "n_orders": p["summary"]["n_orders"],
                    "n_buy": p["summary"]["n_buy"],
                    "n_sell": p["summary"]["n_sell"],
                    "buy_notional": p["summary"]["buy_notional"],
                    "sell_notional": p["summary"]["sell_notional"],
                    "n_dropped_min_notional": p["summary"]["n_dropped_min_notional"],
                    "rounding_drift_one_sided": p["summary"]["rounding_drift_one_sided"],
                    "final_drift_one_sided": p["summary"]["final_drift_one_sided"],
                    "n_target_names": p["summary"]["n_target_names"],
                    "vix": bundle.vix,
                    "scale_event": bool(bundle.books[target.form].scale_event),
                    "tbill_symbol": target.core_symbol if target.form == "F1" else None,
                    "unpriced_in_target": bundle.unpriced[target.form],
                    "held_without_price": held_unpriced,
                    "key_checks": {
                        n: {
                            "passed": checks[n]["passed"],
                            "value": checks[n]["value"],
                            "limit": checks[n]["limit"],
                        }
                        for n in KEY_CHECKS
                        if n in checks
                    },
                    "failed_checks": [
                        {
                            "name": c["name"],
                            "value": c["value"],
                            "limit": c["limit"],
                            "detail": c["detail"],
                        }
                        for c in p["checks"]
                        if not c["passed"]
                    ],
                }
            )
            # execute whatever the checks say; a held name that vanished (acquisition) is closed by
            # the broker the day after it first blocks the plan
            new_state = {s: float(q) for s, q in p["post_trade_qty"].items()}
            for s in held_unpriced:
                new_state.pop(s, None)
            state[account] = new_state
    summary = {}
    for account, rs in rows.items():
        fail_days: Counter[str] = Counter()
        for r in rs:
            for name in {c["name"] for c in r["failed_checks"]}:
                fail_days[name] += 1
        orders = [r["n_orders"] for r in rs]
        summary[account] = {
            "days": len(rs),
            "days_blocked": sum(r["status"] != "ok" for r in rs),
            "days_ok": sum(r["status"] == "ok" for r in rs),
            "check_fail_days": dict(sorted(fail_days.items())),
            "orders_per_day": {
                "median": pct(orders, 50),
                "p95": pct(orders, 95),
                "max": max(orders),
                "min": min(orders),
            },
            "dropped_min_notional_median": pct([r["n_dropped_min_notional"] for r in rs], 50),
            "final_drift_p95": pct([r["final_drift_one_sided"] for r in rs], 95),
            "scale_event_days": sum(r["scale_event"] for r in rs),
            "days_with_unpriced_in_target": sum(bool(r["unpriced_in_target"]) for r in rs),
            "days_with_held_without_price": sum(bool(r["held_without_price"]) for r in rs),
            "tbill_symbols": sorted({r["tbill_symbol"] for r in rs if r["tbill_symbol"]}),
        }
    unexplained = sorted(
        {n for s in summary.values() for n in s["check_fail_days"] if n not in EXPLANATIONS}
    )
    events = [
        {
            "account": account,
            "decision_date": r["decision_date"],
            "check": c["name"],
            "value": c["value"],
            "limit": c["limit"],
            "detail": c["detail"][:200],
        }
        for account, rs in rows.items()
        for r in rs
        for c in r["failed_checks"]
    ]
    result = {
        "task": "T-20261002-28",
        "variant": variant,
        "data_root": str(root),
        "first_execution_date": str(dates[exec_positions[0]].date()),
        "last_execution_date": str(dates[exec_positions[-1]].date()),
        "sessions": sessions,
        "fake_state": (
            "previous day's post-trade whole-share holdings of the replay (day 0: plan of the "
            "previous session with min_notional 0), equity fixed at the $1M basis, all names easy "
            "to borrow; plans executed whatever the checks say; a held name that lost its price "
            "is removed after the day it first appears in the plan"
        ),
        "limits": "RiskLimits defaults of open_composer/book_paper/plan.py, not loosened",
        "summary": summary,
        "explanations": {k: v for k, v in EXPLANATIONS.items()},
        "unexplained_failing_checks": unexplained,
        "newest_tranche_fill_mask_effect": {
            "mean_names_differ": {
                f: float(np.mean([r[f]["n_names_differ"] for r in lookahead_rows]))
                for f in ("F1", "F2")
            }
            if lookahead_rows
            else None,
            "max_abs_dollar_diff_over_equity": {
                f: float(np.max([r[f]["abs_dollar_diff_over_equity"] for r in lookahead_rows]))
                for f in ("F1", "F2")
            }
            if lookahead_rows
            else None,
        },
        "failure_events": events,
        "days": rows,
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=1, default=float) + "\n", encoding="utf-8")
    return result


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--variant", default=None)
    ap.add_argument("--sessions", type=int, default=60)
    ap.add_argument("--data-root", default=None)
    ap.add_argument("--out", default=str(OUT))
    ap.add_argument("--no-diagnostics", action="store_true")
    ap.add_argument("--also", default=None, help="comma list of other variants (summary only)")
    a = ap.parse_args()
    variant = a.variant or v12.primary_variant()
    res = run(
        variant,
        a.sessions,
        Path(a.data_root) if a.data_root else None,
        Path(a.out),
        diagnostics=not a.no_diagnostics,
    )
    others = [v for v in (a.also.split(",") if a.also else []) if v and v != variant]
    if others:
        res["other_variants_summary"] = {}
        for other in others:
            scratch = ROOT / f"data/research/book_v12_t28/engine-replay-{other}.json"
            r2 = run(
                other,
                a.sessions,
                Path(a.data_root) if a.data_root else None,
                scratch,
                diagnostics=False,
            )
            res["other_variants_summary"][other] = {
                "summary": r2["summary"],
                "failure_events": [
                    {k: e[k] for k in ("account", "decision_date", "check", "value")}
                    for e in r2["failure_events"]
                ],
                "unexplained_failing_checks": r2["unexplained_failing_checks"],
            }
        Path(a.out).write_text(json.dumps(res, indent=1, default=float) + "\n", encoding="utf-8")
    print(json.dumps(res["summary"], indent=1, default=float))
    if res["unexplained_failing_checks"]:
        print("UNEXPLAINED failing checks:", res["unexplained_failing_checks"])


if __name__ == "__main__":
    main()
