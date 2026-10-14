# ruff: noqa: E501
"""One bounded complete current application; all outputs retain seen/model scope."""

import hashlib
import json
import re
import resource
import time
import zipfile
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd
from evaluator import (
    P,
    hac,
    lagged_wealth_excess,
    load_bars,
    make_signals,
    matrices,
    paired_bootstrap,
    performance,
    save,
    simulate,
)

from open_composer.research.iteration_dossier import validate_iteration_dossier

ROOT = Path.cwd()
IT = "t20261013_conditional_fedput_application"
D = ROOT / "reports/research/iterations" / IT
R = P / "results"


def bind(p):
    p = Path(p)
    return {
        "path": str(p.resolve().relative_to(ROOT)),
        "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
        "bytes": p.stat().st_size,
    }


def returns(nav):
    return nav.pct_change(fill_method=None).iloc[1:]


def view_metrics(nav, bil):
    out = {}
    for name, mask in [
        ("full", np.ones(len(nav), dtype=bool)),
        ("2020_2021", nav.index.year <= 2021),
        ("2022_onward", nav.index.year >= 2022),
        ("2026YTD", nav.index.year == 2026),
    ] + [(str(y), nav.index.year == y) for y in sorted(set(nav.index.year))]:
        positions = np.flatnonzero(mask)
        if len(positions) < 2:
            continue
        # Include preceding close in attribution so the first day's return is not erased.
        first = max(0, positions[0] - 1)
        sub = nav.iloc[first : positions[-1] + 1]
        out[name] = performance(sub, bil)
    for n in [252, 126, 63]:
        if len(nav) > n:
            out["last" + str(n)] = performance(nav.iloc[-n - 1 :], bil)
    return out


def french_descriptive(events):
    path = ROOT / "reports/research/program/regime-french-source-20261010-1917/official-daily.zip"
    with zipfile.ZipFile(path) as z:
        text = z.read("F-F_Research_Data_Factors_daily.csv").decode()
    records = []
    for ln in text.splitlines():
        if not re.match(r"^\d{8},", ln.strip()):
            continue
        fields = ln.strip().split(",")
        date = fields[0]
        if not "20150101" <= date <= "20260831":
            continue
        values = [float(x) / 100 for x in fields[1:5]]
        assert all(np.isfinite(values)) and all(v > -0.9 for v in values)
        records.append([pd.Timestamp(datetime.strptime(date, "%Y%m%d")), values[0], values[3]])
    f = pd.DataFrame(records, columns=["date", "MktRF", "RF"]).set_index("date")
    grid = pd.bdate_range(f.index[0], f.index[-1])
    f = f.reindex(grid)
    f.loc[~grid.isin(pd.DatetimeIndex([r[0] for r in records])), ["MktRF", "RF"]] = 0.0
    assert f.notna().all().all()
    f["Mkt"] = f.MktRF + f.RF
    states = {}
    for n in [5, 21, 63]:
        x = lagged_wealth_excess(f.Mkt, f.RF, n)
        states[n] = x <= x.quantile(0.2)
    f["D1"] = states[5]
    f["D2"] = states[5] & states[21]
    f["D3"] = states[5] & states[21] & states[63]
    anchors = sorted(pd.Timestamp(e["date"]) for e in events)
    phase = []
    import bisect

    for day in grid:
        i = bisect.bisect_right(anchors, day) - 1
        phase.append(int(np.busday_count(anchors[i].date(), day.date())) if i >= 0 else -999)
    f["phase"] = phase
    f["late"] = f.phase.isin(list(range(9, 14)) + list(range(19, 24)) + list(range(29, 34)))
    f["odd"] = f.phase.isin(list(range(4, 9)) + list(range(14, 19)) + list(range(24, 29)))
    out = {}
    for segment, keep in [
        ("full2015_2026Aug", np.ones(len(f), bool)),
        ("2017_2021", (f.index.year >= 2017) & (f.index.year <= 2021)),
        ("2020_2021", (f.index.year >= 2020) & (f.index.year <= 2021)),
        ("2022_2026Aug", f.index.year >= 2022),
    ]:
        out[segment] = {}
        for d in ["D1", "D2", "D3"]:
            sample = f.loc[keep & f[d] & (f.late | f.odd)]
            x = sample.late.to_numpy(dtype=float)
            y = sample.MktRF.to_numpy()
            if len(sample) < 10 or x.min() == x.max():
                out[segment][d] = {"N": len(sample), "contrast": None}
                continue
            X = np.column_stack([np.ones(len(x)), x])
            coef = np.linalg.lstsq(X, y, rcond=None)[0]
            u = y - X @ coef
            bread = np.linalg.inv(X.T @ X)
            xu = X * u[:, None]
            meat = xu.T @ xu
            scores = (
                pd.DataFrame(xu, index=sample.index).reindex(f.index[keep], fill_value=0).to_numpy()
            )
            for k in range(1, 6):
                if k >= len(x):
                    break
                cov = scores[k:].T @ scores[:-k]
                meat += (1 - k / 6) * (cov + cov.T)
            se = float(np.sqrt(max(0, (bread @ meat @ bread)[1, 1])))
            out[segment][d] = {
                "N": len(sample),
                "late_N": int(x.sum()),
                "odd_N": int((1 - x).sum()),
                "late_minus_odd_daily_bp": float(coef[1] * 10000),
                "odd_intercept_bp": float(coef[0] * 10000),
                "HAC5_se_bp": se * 10000,
                "t": float(coef[1] / se) if se else None,
                "note": "OLS on retainedconditionalobservations;HAC5 fullweekdaycalendarlags,not original1994-2016 replication;fullsampleQ descriptive only.",
            }
    f.to_csv(R / "french-descriptive-primitives.csv")
    return {
        "source": bind(path),
        "vintage": "current202608,notoriginalpublicationPIT",
        "exact_source_reproduction": False,
        "source_form": "Mkt=MktRF+RF, cumulativeMktwealth minusRFwealth, full-overlapglobalQ, weekdayholidayzeros,lateeven-vsodd only",
        "results": out,
    }


def quote_audit():
    out = {}
    for day in ["2020-03-16", "2022-06-13", "2025-04-07", "2026-09-30"]:
        data = {s: [] for s in ["SPY", "SSO", "BIL"]}
        for file in sorted((P / "inputs").glob("quote_" + day + "-*.json")):
            for s, rows in json.loads(file.read_text())["quotes"].items():
                data[s] += rows
        out[day] = {}
        for s, qs in data.items():
            valid = [
                q for q in qs if q["bp"] > 0 and q["ap"] >= q["bp"] and q["bs"] > 0 and q["as"] > 0
            ]
            valid.sort(key=lambda q: q["t"])
            if not valid:
                out[day][s] = {"quote": None, "exact_fill": "N/A"}
                continue
            q = valid[0]
            mid = (q["bp"] + q["ap"]) / 2
            out[day][s] = {
                "first_valid_timestamp": q["t"],
                "bid": q["bp"],
                "ask": q["ap"],
                "raw_bid_size": q["bs"],
                "raw_ask_size": q["as"],
                "halfspread_bp": (q["ap"] - q["bp"]) / (2 * mid) * 10000,
                "size_units_verified": False,
                "capacity_pass": False,
                "exact_fill": "N/A;observedquote doesnotproveauction/fill",
            }
    return out


def main():
    gate = validate_iteration_dossier(IT, ROOT, stage="pre-backtest")
    assert gate.ok, gate.blocked
    admission = json.loads((P / "resource-admission.json").read_text())
    assert admission["economic_execution_admitted"] is True
    assert admission["CPU_coreseconds_remaining"] > 0 and admission["local_CPU_cores"] == 1
    resource.setrlimit(
        resource.RLIMIT_CPU,
        (
            min(600, int(admission["CPU_coreseconds_remaining"])),
            min(600, int(admission["CPU_coreseconds_remaining"])),
        ),
    )
    begin = time.process_time()
    R.mkdir(exist_ok=True)
    plan = json.loads((P / "scientific-plan.json").read_text())
    events = json.loads((P / "calendar-packet.json").read_text())["events"]
    actions = json.loads((P / "inputs/normalized-actions.json").read_text())["actions"]
    raw, adj = load_bars("raw"), load_bars("all")
    close, opening, ac, hygiene = matrices(raw, adj, actions)
    assert close.notna().all().all() and opening.notna().all().all() and ac.notna().all().all()
    f = make_signals(ac, events)
    f.to_csv(R / "causal-signal-log.csv")
    ix = close.loc["2020-01-02":"2026-10-12"].index
    assert ix[0] == pd.Timestamp("2020-01-02") and ix[-1] == pd.Timestamp("2026-10-12")
    cash_days = json.loads((P / "cash-calendar.json").read_text())["eligible_dates"]
    bil = ac.BIL.pct_change(fill_method=None)
    policies = {}
    primary = []
    for s in ["SPY", "SSO"]:
        for d in ["D1", "D2", "D3"]:
            name = "FEDPUT_" + s + "_" + d
            policies[name] = (s, (f[d] & f.late_even))
            primary.append(name)
            policies["GENERIC_" + s + "_" + d] = (s, f[d])
            policies["PLACEBO_" + s + "_" + d] = (s, (f[d] & f.shift_even))
        policies["CALENDAR_" + s] = (s, f.late_even)
    for s in ["SPY", "SSO", "BIL"]:
        policies["BH_" + s] = (s, pd.Series(True, index=f.index))
    capital_paths = {}
    reports = {}
    orders_all = []
    events_all = []

    def run(name, cost, index, capital):
        s, target = policies[name]
        a = [x for x in actions if x["symbol"] == s]
        return simulate(
            close.loc[index, s],
            opening.loc[index, s],
            target.loc[index],
            a,
            capital,
            cost,
            cash_days=cash_days,
        )

    for bps in [0, 20, 40]:
        for name in policies:
            account, orders, ev, details = run(name, bps / 10000, ix, 20000)
            label = name + "__" + str(bps)
            capital_paths[label] = account.nav
            account.to_csv(R / (label + "-cash-ledger.csv"))
            reports[label] = {
                "metrics": performance(account.nav, bil),
                "views": view_metrics(account.nav, bil),
                "funding": details,
                "mean_capital_exposure": float((account.position_value / account.nav).mean()),
                "active_sessions": int((account.shares > 0).sum()),
                "activation_cycles": int(
                    f.loc[account.index[account.shares > 0], "anchor"].nunique()
                ),
            }
            if bps in [20, 40]:
                orders_all.extend(
                    dict(candidate=name, cost_bps=bps, capital=20000, **x) for x in orders
                )
                events_all.extend(
                    dict(candidate=name, cost_bps=bps, capital=20000, **x) for x in ev
                )
        capital_paths["CASH__" + str(bps)] = pd.Series(20000.0, index=ix)
        ewbooks = [run("BH_" + symbol, bps / 10000, ix, 10000)[0] for symbol in ["SPY", "SSO"]]
        capital_paths["EW_SPY_SSO__" + str(bps)] = (
            ewbooks[0].nav + ewbooks[1].nav
        )  # actualtwoinitial10kwholebooks,drift
        for symbol, book in zip(["SPY", "SSO"], ewbooks, strict=True):
            book.to_csv(R / ("EW_" + symbol + "__" + str(bps) + "-10k-cash-ledger.csv"))
    for name in primary:
        s, target = policies[name]
        account, o, e, details = simulate(
            close.loc[ix, s],
            opening.loc[ix, s],
            target.loc[ix],
            [a for a in actions if a["symbol"] == s],
            20000,
            0.002,
            settlement=False,
            cash_days=cash_days,
        )
        reports[name + "__immediate_credit_diagnostic"] = {
            "metrics": performance(account.nav, bil),
            "funding": details,
            "qualified_funded_account": False,
        }
    matrix = pd.DataFrame(capital_paths)
    matrix.to_csv(R / "full-NAV-matrix.csv")
    matrix.pct_change(fill_method=None).iloc[1:].to_csv(R / "daily-return-matrix.csv")
    diffs = pd.DataFrame(
        {
            name: returns(matrix[name + "__20"])
            - returns(matrix[name.replace("FEDPUT", "GENERIC") + "__20"])
            for name in primary
        }
    )
    stats = paired_bootstrap(diffs)
    save(R / "paired-inference.json", stats)
    # Separate actual4k account initialization on hostfirstcommonclose; no scaled20kstrategyreturns.
    hosts = pd.read_parquet(ROOT / "data/research/account_review_2026_10/returns.parquet")
    hosts.index = pd.to_datetime(hosts.index).tz_localize(None).normalize()
    columns = ["F1__net10", "S1__net10", "S2__net10", "S3__net10", "C2__net10"]
    hostreports = {}
    for hn, cols in [("F1", ["F1__net10"]), ("HOST_EW", columns)]:
        rawh = hosts[cols]
        valid = rawh.notna().all(axis=1)
        assert valid.any()
        first, last = rawh.index[valid].min(), rawh.index[valid].max()
        common = ix[(ix >= first) & (ix <= last)]
        h = rawh.reindex(common)
        assert len(common) > 252 and h.notna().all().all(), (
            "Hostcommoncontinuouscoverage unready;no hole deletion"
        )
        h = h.copy()
        h.iloc[0] = 0.0
        hw = (1 + h).cumprod()
        base = 16000 * hw.iloc[:, 0] if hn == "F1" else 3200 * hw.sum(axis=1)
        for bps in [20, 40]:
            replacement = {}
            hostreports[hn + "__" + str(bps)] = {}
            for name in (
                primary + [n.replace("FEDPUT", "GENERIC") for n in primary] + ["BH_SPY", "BH_BIL"]
            ):
                book, o, e, details = run(name, bps / 10000, common, 4000)
                book.to_csv(R / (hn + "_" + name + "__" + str(bps) + "-host4k-cash-ledger.csv"))
                replacement[name] = book.nav
            replacement["CASH"] = pd.Series(4000.0, index=common)
            for name in primary:
                nav = base + replacement[name]
                comparisons = {}
                for control in [name.replace("FEDPUT", "GENERIC"), "BH_SPY", "BH_BIL", "CASH"]:
                    other = base + replacement[control]
                    paired = returns(nav) - returns(other)
                    comparisons[control] = {
                        "paired_HAC5": hac(paired),
                        "dollar_gain_increment": float(nav.iloc[-1] - other.iloc[-1]),
                        "control_metrics": performance(other, bil),
                        "strategy_metrics": performance(nav, bil),
                        "initialization_close_excluded_from_inference": str(common[0].date()),
                        "note": "16kunchangedstorednet10host+independent4kwholecashbook;cashproxy/openreferenceassumptions;drift,no daily80/20rebalancing.",
                    }
                hostreports[hn + "__" + str(bps)][name] = comparisons
                capital_paths[hn + "80_" + name + "20__" + str(bps)] = nav
    save(R / "host-comparisons.json", hostreports)
    # A fractional causalvolatility benchmark is a riskdiagnostic, not a cash ledger.
    volmatch = {}
    spyret = ac.SPY.pct_change(fill_method=None)
    for name in primary:
        cr = returns(matrix[name + "__20"])
        w = (
            (cr.rolling(252).std() / spyret.reindex(cr.index).rolling(252).std())
            .shift(1)
            .clip(0, 1)
        )
        valid = w.notna()
        wr = (w * spyret.reindex(cr.index) - 0.002 * w.diff().abs()).loc[valid].dropna()
        if len(wr) > 5:
            volmatch[name] = {
                "comparison_from": str(wr.index[0].date()),
                "mean_weight": float(w.loc[wr.index].mean()),
                "strategy_minus_fractional_volmatch_HAC5": hac(cr.loc[wr.index] - wr),
                "scope": "causalprior252vol,capped1,zero cash,20bpweightturnover;fractionaldiagnosticnotfundedbook;2020warmup remainsinmainaccount",
            }
    save(R / "causal-vol-riskmatch-diagnostic.json", volmatch)
    # Actualgap/ADV observations are modeldiagnostics, withoutverifiedauction/quote-sizecapacity.
    split_basis = pd.DataFrame(1.0, index=close.index, columns=close.columns)
    for event in actions:
        if event["type"] != "cash_dividends":
            split_basis.loc[pd.Timestamp(event["ex_date"]), event["symbol"]] *= event["ratio"]
    gaps = opening / (close.shift() / split_basis) - 1
    adv = (
        raw.assign(dollar_volume=raw.c * raw.v)
        .pivot(index="date", columns="symbol", values="dollar_volume")
        .rolling(20)
        .mean()
        .shift()
    )
    execution = {
        s: {
            "max_positive_overnight_gap": float(gaps.loc[ix, s].max()),
            "max_negative_overnight_gap": float(gaps.loc[ix, s].min()),
            "guard_rejections": sum(
                not o["accepted"] and o["candidate"].endswith(s + "_D1") for o in orders_all
            ),
            "max_20k_fraction_of_prior20ADV": float((20000 / adv.loc[ix, s]).max()),
            "verified_capacity_pass": False,
        }
        for s in ["SPY", "SSO"]
    }
    save(
        R / "execution-diagnostics.json",
        {
            "quote_audit": quote_audit(),
            "gap_ADV": execution,
            "styles": "Frozen5%guardopening-reference model versus delayedNBBO alternative qualitativeonly;no newoptimizedalternativeorders.",
            "TCA_future": "Ifseparatelyauthorizedrecorddecision/arrival/submit/fillprice,quantity,delay,rejects,slippage;no paper activation orbrokerpolicy approved.",
        },
    )
    save(R / "orders.json", orders_all)
    save(R / "accounting-events.json", events_all)
    source = french_descriptive(events)
    save(R / "french-source-form-diagnostic.json", source)
    report = {
        "schema_version": 1,
        "task_id": "DAY3-PRIMARY-RETURN-BREADTH",
        "iter_id": IT,
        "as_of": datetime.now(UTC).isoformat(),
        "question": plan["question"],
        "scope": "Completefixed6stream conditionalcommon2020-2026account study; allseen, price/open/cashavailability researchmodel; original2016 fundedrange N/A; notoriginal1994-2016source reproduction.",
        "plan": bind(P / "scientific-plan.json"),
        "independent_plan": bind(P / "independent-plan-review.json"),
        "implementation": bind(P / "implementation-manifest.json"),
        "input": bind(P / "inputs/input-acceptance.json"),
        "fixed_primary_ids": primary,
        "benchmark_family_summary": {
            name: {
                "metrics": performance(matrix[name + "__20"], bil),
                "scope": "Same20kcostedwholebook/cash/initial10k+10kEWdrift",
            }
            for name in ["BH_SPY", "BH_SSO", "BH_BIL", "CASH", "EW_SPY_SSO"]
        },
        "ex_post_best_fixed_fund_diagnostic": max(
            ["BH_SPY", "BH_SSO", "BH_BIL"], key=lambda name: float(matrix[name + "__20"].iloc[-1])
        ),
        "trial_exposure": {
            "fixed_primary": 6,
            "fixed_policy_controls": 14,
            "benchmark_cash_EW": 5,
            "unique_current_trading_policy_or_benchmark_definitions": 25,
            "cost_views": "0/20/40bp accountingviews,notindependent selectors",
            "immediatecash": 6,
            "fractionalvolmatch": 6,
            "French_source_form_contrasts": 12,
            "latter_views": "Diagnosticnonselectable sensitivities,not counted asnewstrategydefinitions;allresults retained",
            "promotion_eligible": False,
        },
        "primary_and_control_accounts": reports,
        "paired_inference": bind(R / "paired-inference.json"),
        "host": bind(R / "host-comparisons.json"),
        "French_diagnostic": bind(R / "french-source-form-diagnostic.json"),
        "execution": bind(R / "execution-diagnostics.json"),
        "workflow_pass": True,
        "research_pass": False,
        "llm_contribution_pass": False,
        "ml_contribution_pass": False,
        "paper_ready_pass": False,
        "broker_activity": False,
        "core_process_seconds_excluding_imports": time.process_time() - begin,
        "physical_orders_submitted": 0,
        "fees": "20bpactualmodeledside;40bpindependentfundedstress;0bpdiagnostic only",
        "cash": "Exactpublishedex/pay amounts withunverifiedconservative4/3/2eligiblecashavailabilityproxy; notDTC/brokercash andnotinvestmentreturnlowerbound.",
    }
    save(R / "empirical-report.json", report)
    (D / "trial-ledger.jsonl").write_text(
        "".join(
            json.dumps(
                {
                    "iter_id": IT,
                    "candidate_id": name,
                    "status": "evaluated_seen_nonpromotable",
                    "cost_bps": 20,
                    "source_matrix": bind(R / "daily-return-matrix.csv"),
                    "implementation_manifest": bind(P / "implementation-manifest.json"),
                }
            )
            + "\n"
            for name in primary
        )
    )
    save(D / "evaluation-report.json", report)
    print(json.dumps({n: reports[n + "__20"]["metrics"] for n in primary}, indent=2))


if __name__ == "__main__":
    main()
