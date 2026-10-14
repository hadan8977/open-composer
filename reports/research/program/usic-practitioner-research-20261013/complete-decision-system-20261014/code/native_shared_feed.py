"""Read-only source/native data reuse across two independent native accounts.

Every order book, cash account, fee instrument, policy and feedback controller
belongs to its own BacktestEngine. Only immutable source data are shared.
"""

import gzip
import json
import time
from collections import Counter

import msgspec
from consumer_admission import ROOT, bind
from decision_system import read_parameters
from native_engine import make_engine
from native_events import causal_activity, native_month, source_intervals
from nautilus_trader.model.identifiers import ClientId


def feed(accounts, packets, scenario, factors, trigger_masks, *, afternoon):
    active = set()
    for _engine, strategy in accounts:
        active.update(causal_activity(strategy, packets[0], afternoon=afternoon))
    books, quotes, boundaries, next_factors = native_month(
        packets, scenario, factors, trigger_masks, active_symbols=active
    )
    # These data objects have no account state. Native engines independently
    # copy their L2 book state and maintain their own cache/matching/fees.
    for engine, strategy in accounts:
        strategy.runtime_active_symbols = active
        if books:
            engine.add_data(books)
        if quotes:
            engine.add_data(quotes)
        engine.add_data(boundaries, client_id=ClientId("MARTIN"))
        engine.run(streaming=True)
        engine.clear_data()
    return next_factors, dict(books=len(books), quotes=len(quotes), boundaries=len(boundaries))


def run_block(cells, frames, folders, bindings, *, remaining):
    from run_native_consumer import account_report, flush

    assert 1 < len(cells) <= 2
    scenarios = {c["scenario"] for c in cells}
    assert len(scenarios) == 1
    parameters = read_parameters(
        ROOT / "strategy_specs/drafts/martin_complete_system_20261014.yaml"
    )
    accounts = []
    counts = {c["cell_id"]: Counter() for c in cells}
    minutes = {c["cell_id"]: 0 for c in cells}
    reports = {}
    factors = {"SMCI": 0.1}
    complete = True
    started = time.process_time()
    maximum_interval = 0
    last_boundary = None
    try:
        for c in cells:
            accounts.append(
                (
                    c,
                    *make_engine(
                        parameters,
                        c["candidate"],
                        c["route"],
                        c["cost_bps_per_side"],
                        dict(bindings, cell=c["cell_id"]),
                        factors,
                    ),
                )
            )
        for b in frames["outputs"]:
            path = ROOT / b["path"]
            if path.name.startswith("2023-"):
                continue
            if not accounts:
                break
            assert bind(path) == b
            with gzip.open(path, "rb") as f:
                packets = [msgspec.json.decode(line) for line in f]
            for interval, afternoon in source_intervals(packets, parameters["entry_cutoff_minute"]):
                if remaining() < max(25, 2 * maximum_interval + 12):
                    complete = False
                    break
                t = time.process_time()
                factors, _ = feed(
                    [(e, s) for c, e, s in accounts],
                    interval,
                    next(iter(scenarios)),
                    factors,
                    frames["trigger_masks"],
                    afternoon=afternoon,
                )
                maximum_interval = max(maximum_interval, time.process_time() - t)
                last_boundary = dict(session=interval[-1]["session"], minute=interval[-1]["minute"])
                for c, _e, _s in accounts:
                    minutes[c["cell_id"]] += len(interval)
                unknown = [(c, e, s) for c, e, s in accounts if s.book.path_unknown]
                for c, e, s in unknown:
                    cid = c["cell_id"]
                    e.end()
                    flush(s, folders[cid], path.name[:7], counts[cid])
                    reports[cid] = account_report(
                        c,
                        e,
                        s,
                        counts[cid],
                        minutes[cid],
                        True,
                        None,
                        last_boundary,
                        maximum_interval,
                    )
                    reports[cid]["CPU"] = None  # Shared workload is not an additive per-case claim.
                    e.dispose()
                    accounts.remove((c, e, s))
                if not accounts:
                    break
            del packets
            for c, _e, s in accounts:
                flush(s, folders[c["cell_id"]], path.name[:7], counts[c["cell_id"]])
            print(
                json.dumps(
                    dict(
                        shared_cells=[c["cell_id"] for c, e, s in accounts],
                        month=path.name[:7],
                        block_CPU=time.process_time() - started,
                    )
                ),
                flush=True,
            )
            if not complete:
                break
        for c, e, s in accounts:
            e.end()
            reports[c["cell_id"]] = account_report(
                c,
                e,
                s,
                counts[c["cell_id"]],
                minutes[c["cell_id"]],
                complete,
                None,
                last_boundary,
                maximum_interval,
            )
        for cid, r in reports.items():
            r.update(
                shared_block=dict(
                    cell_ids=[c["cell_id"] for c in cells],
                    inclusive_work_CPU=time.process_time() - started,
                    per_case_CPU_not_additive=True,
                    independent_native_accounts=True,
                )
            )
            (folders[cid] / "result.json").write_text(json.dumps(r, indent=2) + "\n")
        return reports
    finally:
        for _c, e, _s in accounts:
            e.dispose()
