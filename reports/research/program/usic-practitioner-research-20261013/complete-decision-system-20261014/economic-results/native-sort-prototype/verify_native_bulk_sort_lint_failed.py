"""Isolated native input sort batching: validation and final event order retained."""

# ruff: noqa: E402
import hashlib
import importlib.util
import json
import resource
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path

P = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(P / "code"))
from consumer_admission import ROOT, bind, claim_launch, receipt, settle


def main(job):
    claim_launch(job, "consumer")
    resource.setrlimit(resource.RLIMIT_CPU, (27, 29))
    outcome = "native_sort_synthetic_failed"
    try:
        assert receipt(job)["source_science_review"] == bind(
            P / "economic-results/source-clock-independent-review.json"
        )
        folder = P / "economic-results/native-sort-prototype"
        folder.mkdir(exist_ok=False)
        old = P / "code/native_shared_feed.py"
        candidate_path = folder / "native_shared_feed.py"
        candidate = (
            old.read_text()
            .replace("engine.add_data(books)", "engine.add_data(books, sort=False)", 1)
            .replace("engine.add_data(quotes)", "engine.add_data(quotes, sort=False)", 1)
        )
        assert candidate != old.read_text()
        candidate_path.write_text(candidate)
        for path in (Path(__file__), candidate_path):
            result = subprocess.run(
                [str(ROOT / ".venv/bin/ruff"), "format", str(path)],
                capture_output=True,
                text=True,
            )
            assert result.returncode == 0, result.stdout + result.stderr
            result = subprocess.run(
                [str(ROOT / ".venv/bin/ruff"), "check", str(path)],
                capture_output=True,
                text=True,
            )
            assert result.returncode == 0, result.stdout + result.stderr
        # General stable-sort equivalence for distinct identities at tied times.
        # Validation/subscription registrations stay in the same three calls.
        import random

        randomizer = random.Random(914)
        for _ in range(128):
            groups = [
                [(randomizer.randrange(4), group, i) for i in range(17)] for group in range(3)
            ]
            original = []
            for group in groups:
                original = sorted(original + group, key=lambda x: x[0])
            batched = sorted(sum(groups, []), key=lambda x: x[0])
            assert original == batched
        import native_shared_feed
        from decision_system import read_parameters
        from native_engine import make_engine
        from native_events import source_intervals
        from profile_native_feed import normalized_policy
        from test_decision_system import SPEC
        from verify_feed_reuse import source
        from verify_shared_feed import snapshot

        spec = importlib.util.spec_from_file_location("isolated_bulk_sort", candidate_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        rows = []
        for case, scenario in [
            ({}, "O-H-L-C"),
            ({"partial": True}, "O-L-H-C"),
            ({"missing": True, "split": True}, "O-H-L-C"),
            ({"shape_false": True}, "O-L-H-C"),
        ]:
            packets = source(**{k: v for k, v in case.items() if k != "shape_false"})
            if case.get("shape_false"):
                for packet in packets:
                    for row in packet["frames"]:
                        row["frame"]["shape_ok"] = False
            before = json.dumps(packets, sort_keys=True)
            variants, event_counts = [], []
            for feed in (native_shared_feed.feed, module.feed):
                accounts = [
                    make_engine(
                        read_parameters(SPEC),
                        policy,
                        route,
                        20,
                        dict(spec="inert", input="fullysynthetic", contract="inert"),
                        {"SMCI": 0.1},
                    )
                    for policy, route in (("P_SYSTEM", "market"), ("P_EMA", "capped"))
                ]
                factors, counts = {"SMCI": 0.1}, {}
                try:
                    for interval, afternoon in source_intervals(packets, 120):
                        factors, event = feed(
                            accounts, interval, scenario, factors, None, afternoon=afternoon
                        )
                        for k, v in event.items():
                            counts[k] = counts.get(k, 0) + v
                    interpreted = []
                    for engine, strategy in accounts:
                        engine.end()
                        report = snapshot(strategy)
                        report["policy"] = normalized_policy(strategy)
                        report["states"] = {
                            s: {
                                k: v
                                for k, v in asdict(st).items()
                                if k not in {"audit", "report_ids"}
                            }
                            for s, st in strategy.policy.states.items()
                        }
                        report["epoch_attempts"] = sorted(strategy.policy.epoch_attempts.items())
                        report["native_orders"] = sorted(
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
                            key=lambda x: x["id"],
                        )
                        report["controller"] = {
                            k: getattr(strategy.book, k)
                            for k in (
                                "month",
                                "month_start",
                                "month_peak",
                                "month_new_risk",
                                "pause_session",
                                "closed_at_pause",
                                "resume_session",
                                "resume_peak",
                                "unsettled",
                                "reserved",
                            )
                        }
                        interpreted.append(report)
                    variants.append(interpreted)
                    event_counts.append(counts)
                finally:
                    for engine, _strategy in accounts:
                        engine.dispose()
            assert variants[0] == variants[1], (case, scenario)
            assert event_counts[0] == event_counts[1]
            assert before == json.dumps(packets, sort_keys=True)
            rows.append(
                dict(
                    case=case,
                    scenario=scenario,
                    events=event_counts,
                    reference=variants[0],
                    bulk=variants[1],
                    all_fields_equal=True,
                    source_immutable=True,
                    native_engines=4,
                )
            )
        result = dict(
            candidate=bind(candidate_path),
            old=bind(old),
            author_check=bind(Path(__file__)),
            tests=rows,
            stable_tied_timestamp_sequences=128,
            native_engines=16,
            actual_market_native=0,
            actual_Frame_rows=0,
            native_CLI=0,
            HTTP=0,
            no_validation_or_stream_or_account_change=True,
            core_modified=False,
            real_speedup_measured=False,
            parent_complete=False,
        )
        path = folder / "native-inert-verification.json"
        path.write_text(json.dumps(result, default=str, indent=2) + "\n")
        outcome = "native_bulk_sort_16synthetic_engines_all_fields_equal"
        print(json.dumps(dict(outcome=outcome, result=bind(path))))
    finally:
        settle(job, outcome)


if __name__ == "__main__":
    main(sys.argv[1])
