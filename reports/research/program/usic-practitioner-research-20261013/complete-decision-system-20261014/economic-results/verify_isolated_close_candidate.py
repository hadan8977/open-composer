"""Isolated source-cache candidate: fully synthetic native parity, no core edit."""

# ruff: noqa: E402
import ast
import importlib.util
import json
import resource
import subprocess
import sys
from pathlib import Path

P = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(P / "code"))
from consumer_admission import bind, claim_launch, receipt, settle, verify_bindings


def load(name, path, existing_boundary=None):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    if existing_boundary is None:
        spec.loader.exec_module(module)
    else:
        # The unchanged CustomData schema reuses its original registered class.
        # Nautilus registers by class name, so a second declaration would fail.
        tree = ast.parse(path.read_text())
        tree.body = [
            n
            for n in tree.body
            if not (isinstance(n, ast.ClassDef) and n.name == "MartinBoundaryData")
            and not (
                isinstance(n, ast.Assign)
                and any(isinstance(t, ast.Name) and t.id == "MartinBoundaryData" for t in n.targets)
            )
        ]
        module.MartinBoundaryData = existing_boundary
        exec(compile(tree, str(path), "exec"), module.__dict__)
    return module


def main(job):
    claim_launch(job, "consumer")
    resource.setrlimit(resource.RLIMIT_CPU, (32, 34))
    outcome = "isolated_close_inert_failed"
    try:
        science = P / "economic-results/source-clock-independent-review.json"
        assert receipt(job)["input_scope_review"] == bind(science)
        verify_bindings(json.loads(science.read_text())["bindings"])
        for args in (["format", __file__], ["check", "--fix", __file__]):
            r = subprocess.run(
                [str(P.parents[4] / ".venv/bin/ruff"), *args], capture_output=True, text=True
            )
            assert r.returncode == 0, r.stdout + r.stderr
        import native_engine
        import native_shared_feed
        import nautilus_policy_adapter
        from decision_system import read_parameters
        from native_events import source_intervals
        from test_decision_system import SPEC
        from verify_feed_reuse import source
        from verify_shared_feed import snapshot

        candidate_folder = P / "economic-results/source-close-prototype/candidate"
        helper = load("shared_close_frames", candidate_folder / "shared_close_frames.py")
        candidate = load(
            "isolated_martin_source_adapter",
            candidate_folder / "nautilus_policy_adapter.py",
            existing_boundary=nautilus_policy_adapter.MartinBoundaryData,
        )
        # Identical native custom-data schema uses the existing registered type;
        # this is an isolated module test, not another product execution path.
        candidate.MartinBoundaryData = nautilus_policy_adapter.MartinBoundaryData
        paired = load("isolated_martin_source_feed", candidate_folder / "native_shared_feed.py")
        factory_strategy, factory_config = (
            native_engine.MartinNativeStrategy,
            native_engine.MartinAdapterConfig,
        )
        counters = []

        class ObservedCache(helper.SharedCloseFrames):
            def clear_interval(self):
                counters.append(
                    dict(
                        payload_decodes=self.payload_decodes,
                        frame_decodes=self.frame_decodes,
                        cache_hits=self.cache_hits,
                    )
                )
                super().clear_interval()

        paired.SharedCloseFrames = ObservedCache
        cases = [
            ({}, "O-H-L-C"),
            ({"partial": True}, "O-L-H-C"),
            ({"missing": True, "split": True}, "O-H-L-C"),
            ({"shape_false": True}, "O-L-H-C"),
        ]
        results = []
        for case, scenario in cases:
            input_case = {k: v for k, v in case.items() if k != "shape_false"}
            packets = source(**input_case)
            if case.get("shape_false"):
                for packet in packets:
                    for row in packet["frames"]:
                        row["frame"]["shape_ok"] = False
            input_before = json.dumps(packets, sort_keys=True)
            variants = []
            for reuse in (False, True):
                native_engine.MartinNativeStrategy = (
                    candidate.MartinNativeStrategy if reuse else factory_strategy
                )
                native_engine.MartinAdapterConfig = (
                    candidate.MartinAdapterConfig if reuse else factory_config
                )
                accounts = [
                    native_engine.make_engine(
                        read_parameters(SPEC),
                        policy,
                        route,
                        20,
                        dict(spec="inert", input="fullysynthetic", contract="inert"),
                        {"SMCI": 0.1},
                    )
                    for policy, route in (("P_SYSTEM", "market"), ("P_EMA", "capped"))
                ]
                factors = {"SMCI": 0.1}
                try:
                    for interval, afternoon in source_intervals(packets, 120):
                        if reuse:
                            factors, _ = paired.feed(
                                accounts,
                                interval,
                                scenario,
                                factors,
                                None,
                                afternoon=afternoon,
                                reuse_close_frames=True,
                            )
                        else:
                            factors, _ = native_shared_feed.feed(
                                accounts, interval, scenario, factors, None, afternoon=afternoon
                            )
                    observed = []
                    for engine, strategy in accounts:
                        engine.end()
                        observed.append(snapshot(strategy))
                    assert accounts[0][1].book is not accounts[1][1].book
                    assert accounts[0][1].policy is not accounts[1][1].policy
                    assert accounts[0][0].cache is not accounts[1][0].cache
                    if reuse:
                        assert all(s.shared_close_source is None for e, s in accounts)
                    variants.append(observed)
                finally:
                    for engine, _strategy in accounts:
                        engine.dispose()
            assert variants[0] == variants[1], (case, scenario)
            assert input_before == json.dumps(packets, sort_keys=True)
            results.append(
                dict(
                    case=case,
                    scenario=scenario,
                    exact_account_fields=True,
                    source_unchanged=True,
                    accounts_independent=True,
                    native_engines=4,
                    reference=variants[0],
                    reuse=variants[1],
                )
            )
        assert sum(c["cache_hits"] for c in counters) > 0
        output = dict(
            candidate_manifest=bind(
                P / "economic-results/source-close-prototype/integration-manifest.json"
            ),
            tests=results,
            source_cache_counts=counters,
            native_engines=16,
            actual_market_native=0,
            full_strategy_returns=0,
            core_modified=False,
            real_month_throughput_measured=False,
            speedup_credit=None,
            actual_market_Frame_reads=0,
            HTTP=0,
            nativeCLI=0,
            parent_complete=False,
        )
        (P / "economic-results/source-close-prototype/native-inert-verification.json").write_text(
            json.dumps(output, default=str, indent=2) + "\n"
        )
        outcome = "isolated_source_close_candidate_16synthetic_engines_exact_parity"
        print(outcome)
    finally:
        settle(job, outcome)


if __name__ == "__main__":
    main(sys.argv[1])
