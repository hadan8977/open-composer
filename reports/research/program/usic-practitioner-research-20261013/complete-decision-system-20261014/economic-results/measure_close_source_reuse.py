"""Future gated fixedMarch reference/reuse clock test, not a strategy result."""

# ruff: noqa: E402
import gzip
import json
import sys
import time
from dataclasses import asdict
from pathlib import Path

P = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(P / "code"))
from consumer_admission import (
    ROOT,
    bind,
    claim_launch,
    empirical_limit,
    empirical_remaining,
    native_admission,
    phase_admission,
    receipt,
    settle,
    verify_bindings,
)


def main(job):
    claim_launch(job, "consumer")
    outcome = "fixedMarch_source_close_probe_failed_or_partial"
    try:
        review_path = P / "economic-results/source-close-independent-review.json"
        proof = json.loads(review_path.read_text())
        assert proof["verdict"] == "approve_implementation"
        assert proof["actual_March_source_probe_admitted"] is True
        assert proof["author"] != proof["reviewer"]
        assert receipt(job)["source_close_review"] == bind(review_path)
        assert receipt(job)["combined_CPU_upper"] <= min(
            220, proof["allocation"]["fixed_March_CPU"]
        )
        verify_bindings(proof["bindings"])
        native_admission(job)
        phase_admission(job, "empirical")
        empirical_limit(job)  # Subtract actual native childCPU before imports.
        import msgspec
        import native_engine
        import native_shared_feed
        import nautilus_policy_adapter
        from decision_system import read_parameters
        from native_events import source_intervals
        from profile_native_feed import normalized_policy
        from verify_isolated_close_candidate import load
        from verify_shared_feed import snapshot

        def interpreted(engine, strategy):
            result = snapshot(strategy)
            result["policy_audit"] = normalized_policy(strategy)
            result["states"] = {
                s: {k: v for k, v in asdict(state).items() if k not in {"audit", "report_ids"}}
                for s, state in strategy.policy.states.items()
            }
            result["epoch_attempts"] = sorted(
                (symbol, epoch, count)
                for (symbol, epoch), count in strategy.policy.epoch_attempts.items()
            )
            result["native_orders"] = sorted(
                [
                    dict(
                        id=str(o.client_order_id),
                        status=str(o.status),
                        quantity=str(o.quantity),
                        filled_qty=str(o.filled_qty),
                        leaves_qty=str(o.leaves_qty),
                        ts_init=o.ts_init,
                        ts_last=o.ts_last,
                    )
                    for o in engine.cache.orders()
                ],
                key=lambda o: o["id"],
            )
            result["controller"] = dict(
                month=strategy.book.month,
                month_start=strategy.book.month_start,
                month_peak=strategy.book.month_peak,
                month_new_risk=strategy.book.month_new_risk,
                pause_session=strategy.book.pause_session,
                closed_at_pause=strategy.book.closed_at_pause,
                resume_session=strategy.book.resume_session,
                resume_peak=strategy.book.resume_peak,
                unsettled=strategy.book.unsettled,
                reserved=strategy.book.reserved,
            )
            # Nondeterministic report/position UUIDs excluded only; all economic
            # state, intentIDs, quantities/prices/clocks and quotas retained.
            return msgspec.json.decode(msgspec.json.encode(result))

        frames = json.loads((P / "frame-preparation-result.json").read_text())
        source = proof["bindings"]["March_source"]
        assert source in frames["outputs"] and Path(source["path"]).name == "2024-03.jsonl.gz"
        verify_bindings(source)
        read_start = time.process_time()
        with gzip.open(ROOT / source["path"], "rb") as f:
            packets = [msgspec.json.decode(line) for line in f]
        read_cpu = time.process_time() - read_start
        assert len(packets) == 7800
        folder = P / "economic-results" / ("source-close-March-" + job)
        folder.mkdir(exist_ok=False)
        candidate_folder = P / "economic-results/source-close-prototype/candidate"
        load("shared_close_frames", candidate_folder / "shared_close_frames.py")
        candidate = load(
            "isolated_martin_source_adapter",
            candidate_folder / "nautilus_policy_adapter.py",
            existing_boundary=nautilus_policy_adapter.MartinBoundaryData,
        )
        paired = load("isolated_martin_source_feed", candidate_folder / "native_shared_feed.py")
        factory_strategy, factory_config = (
            native_engine.MartinNativeStrategy,
            native_engine.MartinAdapterConfig,
        )
        parameters = read_parameters(
            ROOT / "strategy_specs/drafts/martin_complete_system_20261014.yaml"
        )
        execution_bindings = dict(
            spec=bind(ROOT / "strategy_specs/drafts/martin_complete_system_20261014.yaml")[
                "sha256"
            ],
            input=source["sha256"],
            contract=bind(P / "revisions/r1/event-book-contract.json")["sha256"],
        )
        results, metrics = {}, []
        for reuse in (False, True):
            native_engine.MartinNativeStrategy = (
                candidate.MartinNativeStrategy if reuse else factory_strategy
            )
            native_engine.MartinAdapterConfig = (
                candidate.MartinAdapterConfig if reuse else factory_config
            )
            accounts = [
                native_engine.make_engine(
                    parameters, policy, "market", 20, execution_bindings, {"SMCI": 0.1}
                )
                for policy in ("P_SYSTEM", "P_EMA")
            ]
            factors, events, count, maximum_interval = {"SMCI": 0.1}, {}, 0, 0
            complete = True
            start = time.process_time()
            try:
                for interval, afternoon in source_intervals(packets, 120):
                    if empirical_remaining(job) < max(25, 2 * maximum_interval + 12):
                        complete = False
                        break
                    before = time.process_time()
                    if reuse:
                        factors, event = paired.feed(
                            accounts,
                            interval,
                            "O-H-L-C",
                            factors,
                            frames["trigger_masks"],
                            afternoon=afternoon,
                            reuse_close_frames=True,
                        )
                    else:
                        factors, event = native_shared_feed.feed(
                            accounts,
                            interval,
                            "O-H-L-C",
                            factors,
                            frames["trigger_masks"],
                            afternoon=afternoon,
                        )
                    maximum_interval = max(maximum_interval, time.process_time() - before)
                    count += len(interval)
                    for key, value in event.items():
                        events[key] = events.get(key, 0) + value
                known = all(not s.book.path_unknown for e, s in accounts)
                for (engine, strategy), policy in zip(accounts, ("P_SYSTEM", "P_EMA"), strict=True):
                    engine.end()
                    result = interpreted(engine, strategy)
                    result["full_month_clock_executed"] = complete and count == 7800
                    result["known_complete_month"] = complete and count == 7800 and known
                    label = ("reuse" if reuse else "reference") + "__" + policy
                    results[label] = result
                    with gzip.open(folder / (label + ".json.gz"), "wb", compresslevel=1) as f:
                        f.write(msgspec.json.encode(result))
                metrics.append(
                    dict(
                        reuse=reuse,
                        CPU=time.process_time() - start,
                        minutes=count,
                        complete=complete,
                        known=known,
                        events=events,
                        maximum_interval_CPU=maximum_interval,
                    )
                )
                (folder / "metrics-partial.json").write_text(
                    json.dumps(
                        dict(
                            source=source,
                            source_read_CPU=read_cpu,
                            variants=metrics,
                            native_engines_started=2 * len(metrics),
                            full_strategy_returns=0,
                        ),
                        indent=2,
                    )
                    + "\n"
                )
                if not complete or count != 7800 or not known:
                    raise RuntimeError("partial_or_unknown_month_not_a_throughput_gate")
            finally:
                for engine, _strategy in accounts:
                    engine.dispose()
        assert all(
            results["reference__" + p] == results["reuse__" + p] for p in ("P_SYSTEM", "P_EMA")
        )
        assert metrics[0]["events"] == metrics[1]["events"]
        acceptance = dict(
            exact_two_independent_accounts=True,
            all_state_order_controller_fields_equal=True,
            full_fixed_clock_per_account_minutes=7800,
            source_read_CPU=read_cpu,
            variants=metrics,
            input=source,
            code_and_input_review=bind(review_path),
            full_strategy_returns=0,
            parent_complete=False,
        )
        (folder / "acceptance.json").write_text(json.dumps(acceptance, indent=2) + "\n")
        outcome = "fixedMarch_fullclock_source_close_parity_measured_not_economic_result"
        print(json.dumps(dict(outcome=outcome, metrics=metrics)))
    finally:
        settle(job, outcome)


if __name__ == "__main__":
    main(sys.argv[1])
