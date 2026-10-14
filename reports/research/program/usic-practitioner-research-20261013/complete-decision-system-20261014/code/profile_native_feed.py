"""Admitted, bounded technical feed parity on already-seen inputs.

These incomplete calendar components are not selectable strategy tests or
economic estimates. Both branches use the exact frozen P_SYSTEM market20bps
O-H-L-C policy, separate native cash accounts and the same source packets.
"""

import cProfile
import gzip
import json
import pstats
import time
from collections import Counter
from dataclasses import asdict

import msgspec
from consumer_admission import ROOT, P, bind, empirical_remaining
from decision_system import read_parameters
from native_engine import make_engine
from native_events import causal_activity, native_month, source_intervals
from nautilus_trader.model.identifiers import ClientId


def normalized_policy(strategy):
    # Native UUIDs differ between independent engines; retain deterministic
    # intent/order IDs, all quantities/prices/clocks and terminal transitions.
    return {
        s: [{k: v for k, v in r.items() if k != "report_id"} for r in st.audit]
        for s, st in strategy.policy.states.items()
    }


def execute(packets, optimized, frames, bindings, *, remaining):
    engine, strategy = make_engine(
        read_parameters(ROOT / "strategy_specs/drafts/martin_complete_system_20261014.yaml"),
        "P_SYSTEM",
        "market",
        20,
        bindings,
        {"SMCI": 0.1},
        optimize_runtime=optimized,
    )
    timings = Counter()
    event_counts = Counter()
    factors = {"SMCI": 0.1}
    complete = True
    try:
        # The full-feed reference streams bounded days. It retains every
        # original price/order/boundary, without the former month-sized838MiB
        # transient. Streaming is not a cash/strategy reset.
        from itertools import groupby

        intervals = (
            source_intervals(packets, 120)
            if optimized
            else [(list(day), False) for _, day in groupby(packets, key=lambda p: p["session"])]
        )
        for interval, afternoon in intervals:
            if remaining() <= 25:
                complete = False
                break
            active = (
                causal_activity(strategy, interval[0], afternoon=afternoon) if optimized else None
            )
            strategy.runtime_active_symbols = active
            t = time.process_time()
            books, quotes, boundaries, factors = native_month(
                interval, "O-H-L-C", factors, frames["trigger_masks"], active_symbols=active
            )
            timings["source_to_native_objects_CPU"] += time.process_time() - t
            event_counts.update(
                dict(books=len(books), quotes=len(quotes), boundaries=len(boundaries))
            )
            t = time.process_time()
            if books:
                engine.add_data(books)
            if quotes:
                engine.add_data(quotes)
            engine.add_data(boundaries, client_id=ClientId("MARTIN"))
            del books, quotes, boundaries
            timings["add_sort_CPU"] += time.process_time() - t
            t = time.process_time()
            engine.run(streaming=True)
            engine.clear_data()
            timings["native_run_CPU"] += time.process_time() - t
            if strategy.book.path_unknown:
                break
        engine.end()
        audit = [
            {k: v for k, v in r.items() if k not in {"event_id", "event_at_ns"}}
            for r in strategy.audit
            if r["action"] != "uninterpretable_native_event"
        ]
        economics = dict(
            audit=audit,
            policy=normalized_policy(strategy),
            snapshots=strategy.snapshots,
            closed_R=list(strategy.book.closed_R),
            cash=None if strategy.book.path_unknown else strategy._cash(),
            first_unknown=strategy.book.first_unknown,
            quantities={s: st.quantity for s, st in strategy.policy.states.items()},
            lots={s: asdict(lot) for s, lot in strategy.book.lots.items()},
            marks=dict(strategy.marks),
            unit_factors=strategy.unit_factors,
            component_clock_complete=complete,
            full_month_clock_executed=complete and not strategy.book.path_unknown,
        )
        return economics, dict(timings), dict(event_counts)
    finally:
        engine.dispose()


def probe(job_id, frames, bindings):
    folder = P / "economic-results" / ("technical-feed-" + job_id)
    folder.mkdir(exist_ok=False)
    ledger = P / "economic-results" / "technical-exposure.jsonl"
    results = []
    # First Jan session gives a cheap profiled flat witness. Full March is a
    # fixed seen component containing actual entries/exits; it is not a new
    # complete2024-25 result or a fresh selection/evaluation window.
    # Reuse the completed actual January witness; no rerun of that source
    # session. March's prior numerical reference was only volatile memory and
    # is unavailable, so its necessary same-definition replay is explicit.
    prior = P / "economic-results/technical-feed-martin-feed-probe-20261014/result.json"
    prior_result = json.loads(prior.read_text())
    jan = prior_result["components"][0]
    assert jan["month"] == "2024-01" and jan["exact_interpreted_parity"] is True
    results.append(dict(jan, inherited_actual_witness=bind(prior), rerun=False))
    for month in ("2024-03",):
        binding = next(b for b in frames["outputs"] if b["path"].split("/")[-1].startswith(month))
        path = ROOT / binding["path"]
        assert bind(path) == binding
        t = time.process_time()
        with gzip.open(path, "rb") as f:
            packets = [msgspec.json.decode(line) for line in f]
        parsing_cpu = time.process_time() - t
        outputs = []
        for optimized in (False, True):
            with ledger.open("a") as f:
                f.write(
                    json.dumps(
                        dict(
                            job_id=job_id,
                            month=month,
                            optimized=optimized,
                            status="started",
                            source=binding,
                            selectable=False,
                            complete_strategy_cell=False,
                        )
                    )
                    + "\n"
                )
            artifact = folder / (
                month + ("-optimized" if optimized else "-reference") + "-interpreted.json.gz"
            )
            metrics = artifact.with_suffix(".metrics.json")
            profiler = cProfile.Profile(timer=time.process_time)
            t = time.process_time()
            if month == "2024-01":
                profiler.enable()
            result, timings, counts = execute(
                packets, optimized, frames, bindings, remaining=lambda: empirical_remaining(job_id)
            )
            if month == "2024-01":
                profiler.disable()
            cpu = time.process_time() - t
            io_started = time.process_time()
            with gzip.open(artifact, "wb", compresslevel=1) as out:
                out.write(msgspec.json.encode(result))
            serialization_cpu = time.process_time() - io_started
            stats = []
            if month == "2024-01":
                profiler.dump_stats(
                    str(folder / (month + ("-optimized" if optimized else "-reference") + ".prof"))
                )
                for (file, line, name), (cc, nc, tt, ct, _callers) in sorted(
                    pstats.Stats(profiler).stats.items(), key=lambda r: -r[1][3]
                )[:40]:
                    stats.append(
                        dict(
                            file=file,
                            line=line,
                            function=name,
                            primitive_calls=cc,
                            calls=nc,
                            self_CPU=tt,
                            cumulative_CPU=ct,
                        )
                    )
            variant_metrics = dict(
                optimized=optimized,
                CPU=cpu,
                timings=timings,
                event_counts=counts,
                profiled=False,
                serialization_CPU=serialization_cpu,
                interpreted_witness=bind(artifact),
                component_clock_complete=result["component_clock_complete"],
                source_clock_is_incomplete_strategy_component=True,
            )
            metrics.write_text(json.dumps(variant_metrics, indent=2) + "\n")
            outputs.append(
                (
                    result,
                    dict(
                        optimized=optimized,
                        CPU=cpu,
                        timings=timings,
                        event_counts=counts,
                        profiled=month == "2024-01",
                        profile_top=stats,
                        interpreted_witness=bind(artifact),
                        serialization_CPU=serialization_cpu,
                    ),
                )
            )
            if not result["component_clock_complete"]:
                raise RuntimeError(
                    "technical component budget-incomplete; durable prefix retained, "
                    "gate not passed"
                )
            with ledger.open("a") as f:
                f.write(
                    json.dumps(
                        dict(
                            job_id=job_id,
                            month=month,
                            optimized=optimized,
                            status="component_complete",
                            CPU=cpu,
                            selectable=False,
                            complete_strategy_cell=False,
                        )
                    )
                    + "\n"
                )
        assert outputs[0][0] == outputs[1][0], [
            k for k in outputs[0][0] if outputs[0][0][k] != outputs[1][0][k]
        ]
        row = dict(
            month=month,
            source=binding,
            input_minutes=len(packets),
            source_read_CPU=parsing_cpu,
            exact_interpreted_parity=True,
            variants=[o[1] for o in outputs],
            native_fill_count=sum(
                r["action"] == "native_full_fill" for r in outputs[0][0]["audit"]
            ),
            promotable=False,
            economic_conclusion=False,
        )
        results.append(row)
        (folder / "result.json").write_text(
            json.dumps(
                dict(
                    components=results,
                    full_continuous_result=False,
                    definition_count_added=0,
                    physical_components_completed_this_job=2,
                    January_actual_witness_reused=True,
                ),
                indent=2,
            )
            + "\n"
        )
        print(json.dumps({k: v for k, v in row.items() if k != "variants"}), flush=True)
    return results
