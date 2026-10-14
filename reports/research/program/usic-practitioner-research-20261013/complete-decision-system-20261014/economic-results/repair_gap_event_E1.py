"""One admitted offline edit and inert main-loop check, never network/native CLI."""
import ast
import json
import resource
import subprocess
import sys
import types
from contextlib import nullcontext
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))
from consumer_admission import P, ROOT, bind, claim_launch, receipt, settle, verify_bindings

job = sys.argv[1]
proof_path = P / "economic-results/gap-events-independent-review.json"
proof = json.loads(proof_path.read_text())
assert proof["verdict"] == "revise_bounded_gap_microstructure_entry"
verify_bindings(proof["bindings"])
assert proof["offline_repair_allocation"]["prospective_input_implementation_CPU"] == 10
assert receipt(job)["input_scope_review"]["sha256"] == bind(proof_path)["sha256"]
claim_launch(job, "consumer")
resource.setrlimit(resource.RLIMIT_CPU, (4, 5))  # Remaining5 plus one launcher5 inside10.
outcome = "failed_offline_E1"
try:
    fresh = subprocess.run(
        ["python3", str(ROOT / "scripts/memory_budget.py"), "admit", "--kind", "job", "--mem", "200"],
        capture_output=True, text=True, check=True,
    )
    path = P / "economic-results/check_gap_events.py"
    old = path.read_text()
    new = old.replace("complete_requested_interval=", "page_no_token_and_valid_timestamp_parse=")
    needle = "            results.append(\n"
    replacement = "            summary = summarize(rows, query, token)\n            results.append(\n"
    assert needle in new
    new = new.replace(needle, replacement, 1)
    assert "**summarize(rows, query, token)," in new
    new = new.replace("**summarize(rows, query, token),", "**summary,", 1)
    needle = "            save(folder / \"results-partial.json\", partial)\n            if token:"
    replacement = "            save(folder / \"results-partial.json\", partial)\n            if summary[\"invalid_timestamp_rows\"]:\n                attempt[\"status\"] = \"unresolved_clock_no_followup\"\n                ledger[\"stop_reason\"] = \"unresolved_clock\"\n                save(ledger_path, ledger)\n                break\n            if token:"
    assert needle in new
    new = new.replace(needle, replacement, 1)
    path.write_text(new)
    compile(new, str(path), "exec")
    for arguments in (["format", str(path)], ["check", str(path)]):
        completed = subprocess.run([str(ROOT / ".venv/bin/ruff"), *arguments], capture_output=True, text=True)
        assert completed.returncode == 0, completed.stdout + completed.stderr
    # Execute actual edited main/control flow with inert transports and isolated
    # fixture metadata. No fixture is an execution permission or real ledger.
    source = path.read_text()
    tree = ast.parse(source)
    nodes = [n for n in tree.body if isinstance(n, (ast.Import, ast.ImportFrom)) and
             not (isinstance(n, ast.ImportFrom) and n.module in {"consumer_admission", "acquire_components"})]
    nodes += [n for n in tree.body if isinstance(n, ast.FunctionDef)]
    module = ast.Module(body=nodes, type_ignores=[])
    cli = types.ModuleType("open_composer.cli")
    cli._load_env = lambda: None
    transport_module = types.ModuleType("open_composer.adapters.data.alpaca_snapshot")
    transport_module._stock_data_client = lambda: types.SimpleNamespace(_client=None, close=lambda: None)
    sys.modules[cli.__name__] = cli
    sys.modules[transport_module.__name__] = transport_module
    base_scope = json.loads((P / "economic-results/gap-events-scope.json").read_text())
    results = []
    for invalid in (True, False):
        fixture = P / "economic-results" / ("E1-inert-invalid" if invalid else "E1-inert-valid")
        (fixture / "economic-results").mkdir(parents=True, exist_ok=False)
        fixture_bind = lambda q: dict(path=str(q), sha256="INERT_FIXTURE_NOT_PERMISSION")
        fake_review = dict(verdict="approve_bounded_gap_microstructure_witness", author="A", reviewer="R",
                           economic_execution_admitted=False,
                           bindings=dict(code=fixture_bind(path), scope=fixture_bind(fixture / "economic-results/gap-events-scope.json")),
                           allocation=dict(requests=4, entity_bytes=2500000, prospective_input_CPU=80))
        (fixture / "economic-results/gap-events-independent-review.json").write_text(json.dumps(fake_review))
        (fixture / "economic-results/gap-events-scope.json").write_text(json.dumps(base_scope))
        (fixture / "cumulative-accounting.json").write_text(json.dumps(dict(original_market_requests_used=0, original_market_entity_bytes_used=0)))
        calls = []
        def fake_get(client, route, params, cap):
            calls.append(route)
            query = next(q for q in base_scope["requests"] if q["path"] == route and q["params"] == params)
            timestamp = query["gap_start"].replace("Z", ".000000002Z")
            if query["kind"] == "quotes":
                rows = [dict(t="INVALID" if invalid else timestamp, bp=18, ap=18.02, bs=1, **{"as": 2}, c=[]),
                        dict(t=timestamp, bp=18.01, ap=18.03, bs=2, **{"as": 1}, c=[])]
            else:
                rows = [dict(t=timestamp, p=18, s=1, c=["I"], i=1), dict(t=timestamp, p=18.01, s=2, c=["I"], i=2)]
            body = json.dumps({query["kind"]: {"LMND": rows}, "next_page_token": None}).encode()
            return body, dict(entity_complete=True, http_status=200)
        def fake_save(q, value):
            q.write_text(json.dumps(value))
        namespace = dict(P=fixture, HERE=path, AUTHOR="A", REVIEWER="R", bind=fixture_bind,
                         verify_bindings=lambda v: None, claim_launch=lambda j, e: dict(empirical_CPU_upper=10),
                         native_admission=lambda j: None, phase_admission=lambda j, p: None,
                         empirical_limit=lambda j: None, empirical_remaining=lambda j: 50,
                         locked_ledger=lambda: nullcontext(), save=fake_save, bounded_get=fake_get,
                         settle=lambda j, o: None)
        exec(compile(module, str(path), "exec"), namespace)
        namespace["main"]("INERT_FIXTURE")
        folder = fixture / "economic-results/gap-events"
        ledger = json.loads((folder / "request-ledger.json").read_text())
        partial = json.loads((folder / "results-partial.json").read_text())
        if invalid:
            assert len(calls) == 1 and ledger["stop_reason"] == "unresolved_clock"
            assert ledger["attempts"][0]["status"] == "unresolved_clock_no_followup"
            assert len(partial[0]["invalid_timestamp_rows"]) == 1
            assert list(folder.glob("*.bin")) and not partial[0]["page_no_token_and_valid_timestamp_parse"]
        else:
            assert len(calls) == 4 and len(partial) == 4
            assert all(r["shared_timestamp_extra_rows"] == 1 and r["exact_duplicate_message_extra_rows"] == 0 for r in partial)
        results.append(dict(invalid_clock=invalid, transport_calls=len(calls), raw_and_partial_preserved=True,
                            real_HTTP=0, native_engines=0))
    (P / "economic-results/gap-events-E1-author-verification.json").write_text(json.dumps(dict(
        actual_edited_main_branch_checks=results, code=bind(path), no_parser_science_change=True,
        field_renamed="page_no_token_and_valid_timestamp_parse; no source coverage inference",
        fresh_memory=fresh.stdout.strip(), fits=0, real_HTTP=0, nativeCLI=0, native_engines=0,
    ), indent=2) + "\n")
    outcome = "offline_E1_repair_and_inert_checks_complete"
finally:
    settle(job, outcome)
