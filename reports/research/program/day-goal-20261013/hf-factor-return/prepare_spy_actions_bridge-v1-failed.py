"""Reparse bound issuer cash fields for the frozen funded scope; no returns."""

import hashlib
import json
import os
import re
import resource
import xml.etree.ElementTree as ET
import zipfile
from datetime import UTC, datetime
from pathlib import Path

os.sched_setaffinity(0, {min(os.sched_getaffinity(0))})
resource.setrlimit(resource.RLIMIT_CPU, (30, 30))
os.environ.update(OMP_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1", MKL_NUM_THREADS="1")

import numpy as np
import pandas as pd

P = Path(__file__).parent
OLD = P.parent / "primary-return-breadth"
OUT = P / "market-input/cache-bridge"


def bind(path):
    path = Path(path)
    return dict(path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest(), bytes=path.stat().st_size)


def save(name, data):
    (OUT / name).write_text(json.dumps(data, indent=2, ensure_ascii=False, allow_nan=False) + "\n")


def main():
    workbook = Path("reports/research/program/day-goal-20261011/root-source-support/ssga-historical-distributions.xlsx")
    receipt = workbook.with_name("ssga-fetch.json")
    assert bind(workbook)["sha256"] == json.loads(receipt.read_text())["sha256"]
    ns = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    with zipfile.ZipFile(workbook) as z:
        strings = ["".join(e.itertext()) for e in ET.fromstring(z.read("xl/sharedStrings.xml")).findall("m:si", ns)]
        sheet = ET.fromstring(z.read("xl/worksheets/sheet1.xml"))
    issuer = []
    for row in sheet.findall(".//m:row", ns):
        vals = {}
        for cell in row.findall("m:c", ns):
            v = cell.find("m:v", ns)
            text = "" if v is None else v.text
            vals[re.sub(r"\d", "", cell.get("r"))] = strings[int(text)] if text and cell.get("t") == "s" else text
        if vals.get("B") not in {"SPY", "BIL"}:
            continue
        ex = datetime.strptime(vals["D"].strip(), "%m/%d/%Y").date().isoformat()
        if not "2016-01-04" <= ex <= "2020-12-31":
            continue
        assert not vals.get("H", "").strip() or float(vals["H"]) == 0
        assert not vals.get("I", "").strip() or float(vals["I"]) == 0
        issuer.append(dict(symbol=vals["B"], ex_date=ex,
            record_date=datetime.strptime(vals["E"].strip(), "%m/%d/%Y").date().isoformat(),
            payable_date=datetime.strptime(vals["F"].strip(), "%m/%d/%Y").date().isoformat(),
            issuer_income=float(vals["G"]), raw_cells=vals, issuer_row=int(row.get("r")),
            issuer_source=bind(workbook), blank_gains_unverified=True))
    assert len({(r["symbol"],r["ex_date"]) for r in issuer}) == len(issuer)
    provider_path = OLD / "inputs/actions-01.json"
    groups = json.loads(provider_path.read_text())["corporate_actions"]
    provider = {(r["symbol"],r["ex_date"]):r for r in groups["cash_dividends"]
                if r["symbol"] in {"SPY","BIL"} and "2016-01-04" <= r["ex_date"] <= "2020-12-31"}
    actions = []
    for r in issuer:
        a = provider.get((r["symbol"],r["ex_date"]))
        if a:
            assert abs(a["rate"]-r["issuer_income"]) <= .000000500001
            assert not a.get("record_date") or a["record_date"] == r["record_date"]
            assert not a.get("payable_date") or a["payable_date"] == r["payable_date"]
        actions.append(dict(r, id=a["id"] if a else "ssga_"+r["symbol"]+"_"+r["ex_date"],
                           type="cash_dividends", currency="USD",
                           amount=float(a["rate"]) if a else r["issuer_income"],
                           provider_source=bind(provider_path) if a else None,
                           provider_row=a, amount_from="provider_actual_full_precision" if a else "issuer_actual_display_precision"))
    assert set(provider) <= {(r["symbol"],r["ex_date"]) for r in issuer}
    split_events = []
    for name, rows in groups.items():
        if name == "cash_dividends":
            continue
        for a in rows:
            if a.get("symbol") in {"SPY","BIL"} and "2016-01-04" <= a.get("ex_date","") <= "2020-12-31":
                split_events.append(dict(group=name, row=a))
    assert not split_events, "Actual additional action requires explicitly bound conversion"
    raw_path, all_path = OLD / "inputs/bars_raw-01.json", OLD / "inputs/bars_all-01.json"
    raw, adjusted = [json.loads(p.read_text())["bars"] for p in [raw_path,all_path]]
    qa = {}
    for symbol in ["SPY","BIL"]:
        def close_series(rows):
            return pd.Series([r["c"] for r in rows], index=pd.to_datetime([r["t"][:10] for r in rows])).sort_index()
        c, ac = close_series(raw[symbol]), close_series(adjusted[symbol])
        assert c.index.equals(ac.index) and c.gt(0).all() and ac.gt(0).all()
        use = c.loc["2016-01-04":"2020-12-31"].index
        dates = {pd.Timestamp(r["ex_date"]) for r in actions if r["symbol"] == symbol}
        factor = ac/c
        large_unexplained = (factor/factor.shift()-1).loc[use]
        large_unexplained = large_unexplained[(large_unexplained.abs()>.001) & ~large_unexplained.index.isin(dates)]
        assert large_unexplained.empty
        low, high = (ac.loc[use]-.005)/c.loc[use], (ac.loc[use]+.005)/c.loc[use]
        boundaries = sorted({use[0]} | (dates & set(use)))
        segments = []
        for j, start in enumerate(boundaries):
            end = boundaries[j+1] if j+1<len(boundaries) else use[-1]+pd.Timedelta(days=1)
            ix = use[(use>=start)&(use<end)]
            lo, hi = float(low.loc[ix].max()), float(high.loc[ix].min())
            segments.append(dict(start=str(start.date()), end=str(ix[-1].date()), lower=lo, upper=hi,
                                 sessions=len(ix), passes=lo<=hi+1e-12))
        transitions = []
        for j in range(1,len(segments)):
            day = pd.Timestamp(segments[j]["start"])
            div = sum(r["amount"] for r in actions if r["symbol"]==symbol and r["ex_date"]==str(day.date()))
            previous, current = segments[j-1],segments[j]
            observed = [current["lower"]/previous["upper"],current["upper"]/previous["lower"]]
            prev = c.shift().loc[day]
            bracket = sorted([float(prev/(prev-div)),float(1+div/c.loc[day])])
            transitions.append(dict(date=str(day.date()), observed=observed, physical_convention_bracket=bracket,
                                    passes=observed[0]<=bracket[1]+1e-6 and observed[1]>=bracket[0]-1e-6))
        qa[symbol] = dict(action_count=sum(r["symbol"]==symbol for r in actions),
                          daily_raw_rows=len(use), all_known_action_free_intervals_pass=all(r["passes"] for r in segments),
                          segments=segments, transitions=transitions,
                          known_transition_warnings=[r for r in transitions if not r["passes"]])
    # Save warnings and failures as actual evidence, not an eligibility screen.
    save("SPY-BIL-bound-actions.json",dict(actions=actions, splits=split_events,
         issuer_source=bind(workbook), provider_source=bind(provider_path), issuer_receipt=bind(receipt),
         full_2016_2020_scope=True, actual_payable_fields=True, unknown_blank_gain_cells_retained=True))
    used = resource.getrusage(resource.RUSAGE_SELF)
    save("SPY-BIL-action-QA.json",dict(as_of_utc=datetime.now(UTC).isoformat(), qa=qa,
         actions=bind(OUT/"SPY-BIL-bound-actions.json"), raw_daily=bind(raw_path), adjusted_daily=bind(all_path),
         cash_availability_calendar=bind(OLD/"cash-calendar.json"), new_source_requests=0,new_market_requests=0,
         fits=0, strategy_returns_computed=False, resource_CPU=used.ru_utime+used.ru_stime,max_RSS_KiB=used.ru_maxrss,
         limits="Conditional actual issuer/provider cash fields. No PIT/full corporate-action certification. Adjusted factor audit is retrospective input consistency, never entry/quantity/eligibility/funding; blank capital gains and exact vendor conventions remain unverified."))
    print(json.dumps({s:{k:v for k,v in q.items() if k not in {"segments","transitions"}} for s,q in qa.items()}))


if __name__ == "__main__":
    main()
