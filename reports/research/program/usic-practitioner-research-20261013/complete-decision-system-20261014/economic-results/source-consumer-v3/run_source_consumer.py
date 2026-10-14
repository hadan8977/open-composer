"""Gated complete continuous native block; separate cash/feedback per cell.

Shared inputs are read-only. No result-selected source, cost, path or mechanism.
No account checkpoint is claimed; monthly outputs preserve interpretable prefixes.
"""

# ruff: noqa: E402
import argparse
import gzip
import json
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

P = Path(__file__).resolve().parents[2]
F = Path(__file__).resolve().parent
sys.path.insert(0, str(P / "code"))
sys.path.insert(0, str(F))
from consumer_admission import ROOT, bind, receipt, save, verified_frames, verify_bindings
from continuation_admission import claim, native_admission, rearm, remaining

REVIEW = F / "independent-review.json"


def run(job, cell_ids):
    claim(job, "matched_block")
    proof = json.loads(REVIEW.read_text())
    assert proof["verdict"] == "approve_implementation" and proof["matched_blocks_admitted"] is True
    assert proof["affected_science_accepted"] is True
    assert proof["actual_input_route_accepted"] is True
    native_admission(job, REVIEW, "matched_blocks_admitted")
    rearm(job)
    import msgspec
    from compact_output import flush
    from decision_system import read_parameters
    from gap_events import gap_minute, holding_phase
    from gap_native_engine import make_engine
    from gap_source import integer_ns, parse_quotes, qualify_gap
    from native_events import causal_activity, source_intervals
    from native_feed5 import feed as reference_feed
    from nautilus_trader.model.identifiers import ClientId
    from run_native_consumer import account_report
    from source_entry import request_window

    frames = verified_frames()  # Fresh output SHA check, one per whole block.
    matrix = json.loads((P / "consumer-cases.json").read_text())
    cells = [c for c in matrix["cells"] if c["cell_id"] in cell_ids]
    assert 1 <= len(cells) <= 2 and set(cell_ids) == {c["cell_id"] for c in cells}
    assert len(cell_ids) == len(set(cell_ids))
    assert len({c["scenario"] for c in cells}) == 1
    stage = receipt(job)["continuation_stage"]
    if stage == "first8":
        assert all(
            c["candidate"] in {"P_SYSTEM", "P_EMA"} and c["cost_bps_per_side"] == 20 for c in cells
        )
    assert set(cell_ids) <= set(proof["allowed_cell_ids"])
    scenario = cells[0]["scenario"]
    parameters = read_parameters(F / "StrategySpec.yaml")
    contexts = json.loads((F / "holding-daily-context.json").read_text())
    assert contexts["status"] == "complete_causal_official_holding_prefixes"
    verify_bindings(
        {k: contexts[k] for k in ("daily_basis", "actions", "hygiene", "calendar_inventory")}
    )
    daily = defaultdict(list)
    for row in contexts["rows"]:
        daily[row["day"]].append(row)
    scope = json.loads((F / "source-scope.json").read_text())
    windows = {}
    for query in scope["requests"]:
        for minute in query["gap_minutes"]:
            key = (query["session"], query["symbol"], minute)
            assert key not in windows
            windows[key] = query
    root = F / ("matched-" + job)
    root.mkdir(exist_ok=False)
    accounts = []
    folders = {}
    counters = {c["cell_id"]: Counter() for c in cells}
    minutes = {c["cell_id"]: 0 for c in cells}
    factors = {"SMCI": 0.1}
    parsed_cache = {}
    complete = True
    execution_error = None
    max_interval = 0
    reports = {}
    last_boundary = None
    bindings = dict(
        spec=bind(F / "StrategySpec.yaml")["sha256"],
        input=bind(F / "implementation-manifest.json")["sha256"],
        contract=bind(F / "affected-plan.json")["sha256"],
    )

    def active_risk(symbol):
        risk = []
        for cell, engine, strategy in accounts:
            state = strategy.policy.states.get(symbol)
            ids = []
            for intent in (
                list(strategy.staged_entries.values())
                + list(strategy.staged_exits.values())
                + list(strategy.cancel_then_sell.values())
            ):
                if intent.symbol == symbol:
                    ids.append(intent.id)
            if state:
                ids.extend(i.id for i in (state.pending, state.pending_exit, state.protective) if i)
            ids.extend(
                str(o.client_order_id)
                for o in engine.cache.orders_open()
                if o.instrument_id.symbol.value == symbol
            )
            if (state and state.quantity) or ids:
                risk.append(
                    dict(
                        cell=cell["cell_id"],
                        quantity=state.quantity if state else 0,
                        order_ids=sorted(set(ids)),
                        at_ns=strategy.clock.timestamp_ns(),
                    )
                )
        return risk

    def consume(packets, afternoon=False):
        nonlocal factors, max_interval, last_boundary
        if not accounts:
            return
        before = time.process_time()
        if remaining(job) < max(30, 2 * max_interval + 15):
            raise TimeoutError("inclusive_budget_prefix_not_complete")
        if len(packets) == 1 and packets[0]["missing"]:
            packet = packets[0]
            qualified = {}
            at = integer_ns(packet["start"])
            for symbol in packet["missing"]:
                risks = active_risk(symbol)
                if not risks:
                    continue
                query = windows[(packet["session"], symbol, packet["minute"])]
                if query["id"] not in parsed_cache:
                    release = dict(
                        kind="active_native_risk",
                        symbol=symbol,
                        at_ns=max(r["at_ns"] for r in risks),
                        required_gap_ns=at,
                        quantity=sum(r["quantity"] for r in risks),
                        order_ids=sorted({i for r in risks for i in r["order_ids"]}),
                        accounts=risks,
                    )
                    try:
                        result = request_window(job, query["id"], causal_release=release)
                        observations = []
                        for page in result["pages"]:
                            raw = (ROOT / page["entity"]["path"]).read_bytes()
                            q, _ = parse_quotes(raw, symbol)
                            observations.extend(q)
                        # Bound RAM to the current two windows; raw sources are
                        # retained/reused on disk, not copied into each account.
                        if len(parsed_cache) >= 2:
                            parsed_cache.pop(next(iter(parsed_cache)))
                        parsed_cache[query["id"]] = (tuple(observations), result["QA"])
                    except Exception as exc:
                        save(
                            root / ("source-unresolved-" + query["id"] + ".json"),
                            dict(
                                window=query,
                                at_ns=at,
                                exception_type=type(exc).__name__,
                                reason=str(exc),
                                old_paths_unchanged=True,
                            ),
                        )
                        continue  # Original missing event freezes actual affected accounts.
                obs, qa = parsed_cache[query["id"]]
                qualified[symbol] = qualify_gap(symbol, at, at + 60 * 10**9, obs, qa)
            active = set()
            for _cell, _engine, strategy in accounts:
                active.update(causal_activity(strategy, packet, afternoon=afternoon))
            books, quotes, boundaries, next_factors = gap_minute(
                packet,
                scenario,
                factors,
                frames["trigger_masks"],
                qualified,
                active_symbols=active,
                admitted_job=job,
            )
            if packet["minute"] == 0:
                boundaries.append(holding_phase(packet, daily))
            for _cell, engine, strategy in accounts:
                strategy.runtime_active_symbols = active
                if books:
                    engine.add_data(books)
                if quotes:
                    engine.add_data(quotes)
                engine.add_data(boundaries, client_id=ClientId("MARTIN"))
                engine.run(streaming=True)
                engine.clear_data()
            factors = next_factors
        elif packets[0]["minute"] == 0:
            # One opening minute gets the independent causal holding event.
            from native_events import native_month

            active = set()
            for _cell, _engine, strategy in accounts:
                active.update(causal_activity(strategy, packets[0], afternoon=afternoon))
            b, q, c, factors = native_month(
                packets, scenario, factors, frames["trigger_masks"], active_symbols=active
            )
            c.append(holding_phase(packets[0], daily))
            for _cell, e, s in accounts:
                s.runtime_active_symbols = active
                if b:
                    e.add_data(b)
                if q:
                    e.add_data(q)
                e.add_data(c, client_id=ClientId("MARTIN"))
                e.run(streaming=True)
                e.clear_data()
        else:
            factors, _ = reference_feed(
                [(e, s) for cell, e, s in accounts],
                packets,
                scenario,
                factors,
                frames["trigger_masks"],
                afternoon=afternoon,
            )
        max_interval = max(max_interval, time.process_time() - before)
        last_boundary = dict(session=packets[-1]["session"], minute=packets[-1]["minute"])
        for cell, _e, _s in accounts:
            minutes[cell["cell_id"]] += len(packets)
        unknown = [a for a in accounts if a[2].book.path_unknown]
        for cell, e, s in unknown:
            cid = cell["cell_id"]
            e.end()
            flush(s, folders[cid], packets[-1]["session"][:7], counters[cid])
            reports[cid] = account_report(
                cell, e, s, counters[cid], minutes[cid], True, None, last_boundary, max_interval
            )
            e.dispose()
            accounts.remove((cell, e, s))

    try:
        for cell in cells:
            cid = cell["cell_id"]
            folder = root / cid
            folder.mkdir()
            folders[cid] = folder
            accounts.append(
                (
                    cell,
                    *make_engine(
                        parameters,
                        cell["candidate"],
                        cell["route"],
                        cell["cost_bps_per_side"],
                        dict(bindings, cell="source_clock_v3__" + cid),
                        factors,
                    ),
                )
            )
        for source in frames["outputs"]:
            path = ROOT / source["path"]
            if path.name.startswith("2023-"):
                continue
            if not accounts:
                break
            with gzip.open(path, "rb") as f:
                packets = [msgspec.json.decode(line) for line in f]
            for interval, afternoon in source_intervals(packets, parameters["entry_cutoff_minute"]):
                normal = []
                for packet in interval:
                    # Split only at source-needed clock boundaries. An earlier
                    # stop/exit may remove the need before the next actual gap.
                    if packet["missing"] or packet["minute"] == 0:
                        if normal:
                            consume(normal, afternoon)
                            normal = []
                        consume([packet], afternoon)
                    else:
                        normal.append(packet)
                    if not accounts:
                        break
                if normal and accounts:
                    consume(normal, afternoon)
                if not accounts:
                    break
            del packets
            for cell, _e, s in accounts:
                flush(s, folders[cell["cell_id"]], path.name[:7], counters[cell["cell_id"]])
            print(
                json.dumps(
                    dict(
                        month=path.name[:7],
                        active_cells=[c["cell_id"] for c, e, s in accounts],
                        remaining_CPU=remaining(job),
                    )
                ),
                flush=True,
            )
    except TimeoutError as exc:
        complete = False
        execution_error = dict(
            kind="budget_incomplete", exception_type=type(exc).__name__, reason=str(exc)
        )
    except Exception as exc:
        complete = False
        execution_error = dict(
            kind="implementation_or_input_incomplete",
            exception_type=type(exc).__name__,
            reason=str(exc),
        )
        save(
            root / "failed-execution-prefix.json",
            dict(
                error=execution_error,
                last_source_boundary=last_boundary,
                complete=False,
                full_returns=None,
                native_checkpoint_available=False,
            ),
        )
    finally:
        for cell, e, s in accounts:
            cid = cell["cell_id"]
            e.end()
            if last_boundary:
                flush(s, folders[cid], last_boundary["session"][:7] + "-terminal", counters[cid])
            reports[cid] = account_report(
                cell, e, s, counters[cid], minutes[cid], complete, None, last_boundary, max_interval
            )
            e.dispose()
        for cid, report in reports.items():
            report.update(
                version="source_clock_v3",
                old_paths_immutable=True,
                source_conditional=True,
                original_grid_cell_id=cid,
                distinct_version_execution=True,
                modeled_fee_bps=next(c["cost_bps_per_side"] for c in cells if c["cell_id"] == cid),
                fee_interpretation=(
                    "0/20/40 per filled side named diagnostics/stress;20 not "
                    "universal actual cost. Gap BBO spread exists in all three."
                ),
                source_and_holding_plan=bind(F / "affected-plan.json"),
                initial_capital=20000,
                continuous_year_views_not_new_capital=True,
                broker_stop_election="unknown",
                firm_NBBO=False,
                raw_quote_depth_units_unmapped=True,
                synthetic_gap_depth_shares=100,
                shared_block_CPU_not_additive=True,
                execution_error=execution_error,
            )
            save(folders[cid] / "result.json", report)
    if execution_error and execution_error["kind"] != "budget_incomplete":
        raise RuntimeError(execution_error)
    return reports


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--job", required=True)
    p.add_argument("--cells", nargs="+", required=True)
    args = p.parse_args()
    run(args.job, args.cells)
