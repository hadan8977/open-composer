"""Existing offline200: G1 resource placement only; fake child CPU, no native."""

# ruff: noqa: E402
import ast
import json
import math
import resource
import subprocess
import sys
import types
from pathlib import Path

P = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(P / "code"))
from consumer_admission import bind, claim_launch, receipt, settle


def main(job):
    proof_path = P / "economic-results/source-clock-component-independent-review.json"
    proof = json.loads(proof_path.read_text())
    assert proof["verdict"] == "revise_implementation"
    assert [c["id"] for c in proof["required_corrections"]] == ["G1"]
    assert receipt(job)["implementation_repair_review"] == bind(proof_path)
    claim_launch(job, "consumer")
    resource.setrlimit(resource.RLIMIT_CPU, (14, 16))
    outcome = "G1_offline_failed"
    try:
        folder = P / "economic-results/source-clock-v1-G1"
        archive = folder / "old"
        recovery = len(sys.argv) > 2 and sys.argv[2] == "--resume-after-lint"
        archive.mkdir(parents=True, exist_ok=recovery)
        names = (
            "probe_source_clock.py",
            "source_clock_native.py",
            "source-clock-implementation-manifest.json",
            "source-clock-component-independent-review.json",
        )
        if not recovery:
            for name in names:
                source = P / "economic-results" / name
                (archive / name).write_bytes(source.read_bytes())
        driver = P / "economic-results/probe_source_clock.py"
        library = P / "economic-results/source_clock_native.py"
        assert bind(archive / names[0])["sha256"] == proof["bindings"]["driver"]["sha256"]
        assert (
            bind(archive / names[1])["sha256"] == proof["bindings"]["component_files"][1]["sha256"]
        )
        old_driver = (archive / names[0]).read_text()
        old_library = (archive / names[1]).read_text()
        new_driver = old_driver.replace(
            "    empirical_remaining,\n", "    empirical_limit,\n    empirical_remaining,\n", 1
        )
        new_driver = new_driver.replace("from source_clock_native import run_component\n", "", 1)
        needle = '        phase_admission(job, "empirical")\n'
        assert needle in new_driver
        new_driver = new_driver.replace(
            needle,
            needle
            + "        empirical_limit(job)\n"
            + "        from source_clock_native import run_component\n",
            1,
        )
        new_library = old_library.replace(
            (
                "from consumer_admission import ROOT, P, bind, phase_admission, "
                "receipt, verify_bindings"
            ),
            (
                "from consumer_admission import ROOT, P, bind, empirical_limit, "
                "phase_admission, receipt, verify_bindings"
            ),
            1,
        )
        needle = (
            '    phase_admission(job, "empirical")  # current owner/hold/PID/native dossier/pool\n'
        )
        assert needle in new_library
        new_library = new_library.replace(needle, needle + "    empirical_limit(job)\n", 1)
        driver.write_text(new_driver)
        library.write_text(new_library)
        for arguments in (
            ["format", str(driver), str(library), __file__],
            ["check", "--fix", str(driver), str(library), __file__],
        ):
            r = subprocess.run(
                [str(P.parents[4] / ".venv/bin/ruff"), *arguments], capture_output=True, text=True
            )
            assert r.returncode == 0, r.stdout + r.stderr
        # Actual helper executed with simulated child usage and OS-limit recorder.
        admitted = dict(empirical_CPU_upper=180, launcher_unknown_CPU=5, runtime_actual_CPU=0)
        child_cpu = [0]
        calls, limits = [], []
        fake_resource = types.SimpleNamespace(
            RLIMIT_CPU=0, setrlimit=lambda kind, value: limits.append(value)
        )
        fake_signal = types.SimpleNamespace(SIGXCPU=24, signal=lambda *args: None)
        helper_tree = ast.parse((P / "code/consumer_admission.py").read_text())
        helper = next(
            n
            for n in helper_tree.body
            if isinstance(n, ast.FunctionDef) and n.name == "empirical_limit"
        )
        namespace = dict(
            receipt=lambda job: admitted,
            usage=lambda: (1, child_cpu[0]),
            resource=fake_resource,
            signal=fake_signal,
            math=math,
        )
        exec(
            compile(ast.Module(body=[helper], type_ignores=[]), "actual_empirical_limit", "exec"),
            namespace,
        )
        namespace["empirical_limit"]("INERT")
        assert limits[-1] == (165, 173)

        def rearm(job):
            calls.append("rearm_after_child")
            namespace["empirical_limit"](job)
            assert limits[-1] == (135, 143)

        fake = folder / ("INERT_NOT_PERMISSION_" + job)
        (fake / "economic-results").mkdir(parents=True)
        review = dict(
            verdict="approve_implementation",
            real_market_native_probe_admitted=True,
            author="INERT_A",
            reviewer="INERT_R",
            allocation=dict(technical_source_window_CPU=180),
            bindings=dict(fixtures=dict(path="fixtures.json", sha256="INERT_NOT_PERMISSION")),
        )
        (fake / "economic-results/source-clock-component-independent-review.json").write_text(
            json.dumps(review)
        )
        (fake / "fixtures.json").write_text(json.dumps(dict(fixtures=[])))

        def fake_bind(path):
            return dict(path=str(path), sha256="INERT_NOT_PERMISSION")

        fake_row = dict(
            component_review=fake_bind(
                fake / "economic-results/source-clock-component-independent-review.json"
            ),
            combined_CPU_upper=180,
        )

        class FakeHeavyModule(types.ModuleType):
            def __getattr__(self, name):
                if name == "run_component":
                    calls.append("heavy_import_after_rearm")
                    return lambda *args, **kwargs: (_ for _ in ()).throw(
                        AssertionError("inert fixture never creates engine")
                    )
                raise AttributeError(name)

        sys.modules["source_clock_native"] = FakeHeavyModule("source_clock_native")

        def simulated_native(job):
            calls.append("simulated_native_child30")
            child_cpu[0] = 30

        tree = ast.parse(driver.read_text())
        fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "main")
        globals_driver = dict(
            P=fake,
            ROOT=fake,
            json=json,
            sys=sys,
            bind=fake_bind,
            claim_launch=lambda *args: calls.append("claim"),
            receipt=lambda *args: fake_row,
            verify_bindings=lambda *args: calls.append("verify"),
            native_admission=simulated_native,
            phase_admission=lambda *args: calls.append("phase"),
            empirical_limit=rearm,
            empirical_remaining=lambda *args: 100,
            settle=lambda *args: calls.append("inert_settle"),
        )
        exec(
            compile(ast.Module(body=[fn], type_ignores=[]), "actual_edited_driver", "exec"),
            globals_driver,
        )
        globals_driver["main"]("INERT_NOT_PERMISSION")
        assert (
            calls.index("simulated_native_child30")
            < calls.index("phase")
            < calls.index("rearm_after_child")
            < calls.index("heavy_import_after_rearm")
        )
        driver_calls = list(calls)
        # Actual edited library guard, again using only isolated fake metadata.
        calls.clear()
        fixture = dict(
            id="INERT_ONLY",
            source_versions=[dict(path="LMND_INERT_quotes.bin", sha256="INERT_NOT_PERMISSION")],
        )
        (fake / "fixtures.json").write_text(json.dumps(dict(fixtures=[fixture])))
        (fake / "LMND_INERT_quotes.bin").write_bytes(b"INERT_NOT_MARKET")
        fake_source = types.ModuleType("source_clock")
        fake_source.parse_source = lambda *args: (("INERT_QUOTE",), dict())
        sys.modules["source_clock"] = fake_source
        fn = next(
            n
            for n in ast.parse(library.read_text()).body
            if isinstance(n, ast.FunctionDef) and n.name == "real_source_admission"
        )
        globals_library = dict(
            P=fake,
            ROOT=fake,
            json=json,
            bind=fake_bind,
            receipt=lambda *args: fake_row,
            verify_bindings=lambda *args: calls.append("verify"),
            phase_admission=lambda *args: calls.append("phase"),
            empirical_limit=rearm,
        )
        exec(
            compile(ast.Module(body=[fn], type_ignores=[]), "actual_edited_library_guard", "exec"),
            globals_library,
        )
        globals_library["real_source_admission"]("INERT_NOT_PERMISSION", ("INERT_QUOTE",), fixture)
        assert calls.index("phase") < calls.index("rearm_after_child")
        # Semantics of every non-admission library function are unchanged AST.
        old_functions = {
            n.name: ast.dump(n)
            for n in ast.parse(old_library).body
            if isinstance(n, ast.FunctionDef)
        }
        new_functions = {
            n.name: ast.dump(n)
            for n in ast.parse(library.read_text()).body
            if isinstance(n, ast.FunctionDef)
        }
        assert all(
            old_functions[k] == new_functions[k]
            for k in old_functions
            if k != "real_source_admission"
        )
        manifest_path = P / "economic-results/source-clock-implementation-manifest.json"
        manifest = json.loads(manifest_path.read_text())
        manifest["driver"] = bind(driver)
        manifest["component_files"] = [
            bind(P / "economic-results" / Path(b["path"]).name) for b in manifest["component_files"]
        ]
        verification = dict(
            existing_semantics_acceptance=bind(archive / names[3]),
            original_code=[bind(archive / names[0]), bind(archive / names[1])],
            current_driver=bind(driver),
            current_library=bind(library),
            driver_call_order=driver_calls,
            library_call_order=calls,
            before_child_own_RLIMIT=[165, 173],
            after_child30_own_RLIMIT=[135, 143],
            actual_original_empirical_limit_AST_executed=True,
            non_admission_library_functions_AST_identical=True,
            fake_fixture="INERT_NOT_PERMISSION",
            actual_native_CLI=0,
            native_engines=0,
            actual_market_native=0,
            new_HTTP=0,
            parent_complete=False,
        )
        (folder / "author-verification.json").write_text(json.dumps(verification, indent=2) + "\n")
        manifest["G1_affected_proof"] = bind(folder / "author-verification.json")
        manifest["prior_component_semantics_review"] = bind(archive / names[3])
        manifest["old_code_preservation"] = verification["original_code"]
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
        outcome = "G1_driver_library_childinclusive_rearm_and_late_import_inert_pass"
        print(outcome)
    finally:
        settle(job, outcome)


if __name__ == "__main__":
    main(sys.argv[1])
