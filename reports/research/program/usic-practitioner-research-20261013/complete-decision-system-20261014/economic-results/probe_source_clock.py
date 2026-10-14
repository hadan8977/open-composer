"""Gated later source-window component entry. No allocation exists at authoring."""

# ruff: noqa: E402
import json
import sys
from dataclasses import asdict
from decimal import Decimal
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
from source_clock import StopSetup, parse_source, stop_reference


def main(job):
    outcome = "source_window_probe_failed_or_not_admitted"
    # Shared claim protects owner/hold/unique PID/original grant. The secondary
    # acceptance below separately binds the new code, inputs, fixtures and180.
    claim_launch(job, "consumer")
    try:
        proof_path = P / "economic-results/source-clock-component-independent-review.json"
        proof = json.loads(proof_path.read_text())
        assert proof["verdict"] == "approve_implementation"
        assert proof["real_market_native_probe_admitted"] is True
        assert proof["author"] != proof["reviewer"]
        assert receipt(job)["component_review"] == bind(proof_path)
        assert receipt(job)["combined_CPU_upper"] <= min(
            180, proof["allocation"]["technical_source_window_CPU"]
        )
        verify_bindings(proof["bindings"])
        native_admission(job)  # Actual native CLI/current dossier and fresh900.
        phase_admission(job, "empirical")
        empirical_limit(job)
        from source_clock_native import run_component

        contract = json.loads((ROOT / proof["bindings"]["fixtures"]["path"]).read_text())
        folder = P / "economic-results/source-clock-v1-real-probe"
        folder.mkdir(exist_ok=False)
        partial = []
        for fixture in contract["fixtures"]:
            if empirical_remaining(job) < 25:
                outcome = "budget_partial_component_probe_no_gate_pass"
                break
            data = {}
            for source in fixture["source_versions"]:
                verify_bindings(source)
                kind = "quotes" if "_quotes.bin" in source["path"] else "trades"
                data[kind], metadata = parse_source(
                    (ROOT / source["path"]).read_bytes(), kind, source["sha256"]
                )
                assert metadata["page_token"] is None
            before = repr((data["quotes"], data["trades"]))
            native = run_component(
                data["quotes"],
                fixture,
                ROOT / "strategy_specs/drafts/martin_complete_system_20261014.yaml",
                provenance="separately_admitted_real_source_component",
                admitted_job=job,
            )
            entry = [
                r
                for r in native.get("native_reports", ())
                if r["order_id"] == fixture["id"] + "-entry"
            ]
            protect = [
                r
                for r in native.get("audit", ())
                if r["action"] == "native_submission"
                and r["intent_id"] == fixture["id"] + "-entry-protect"
            ]
            fill_ns = entry[0]["ns"] if entry else None
            active_ns = protect[0]["native_at_ns"] if protect else None
            if entry:
                assert fill_ns == fixture["expected_terminal_fill_ns"]
                assert Decimal(entry[0]["price"]) == Decimal(fixture["expected_initial_fill_price"])
                assert active_ns is not None and active_ns >= fill_ns
                assert int(Decimal(entry[0]["quantity"])) == fixture["quantity"]
            reference = stop_reference(
                data["quotes"],
                data["trades"],
                StopSetup(
                    Decimal(fixture["stop"]),
                    fill_ns,
                    active_ns,
                    fixture["quantity"],
                    fixture["maximum_observed_quote_age_ns"],
                ),
            )
            assert repr((data["quotes"], data["trades"])) == before
            if native.get("unknown"):
                assert native["closed_R"] == native["firstunknown"]["known_prefix_closed_R"]
                assert native["feedback_after"] == native["firstunknown"]["feedback"]
                assert native["R"] is None and native["native_cash"] is None
            result = dict(
                fixture=fixture["id"],
                native_quote_research_proxy=native,
                necessary_observed_price_reference=[asdict(r) for r in reference],
                source_clock_assumption=(
                    "current-vintage event timestamps; no historical arrival proof"
                ),
                broker_stop_election="unknown",
                continuous_price_coverage_certified=False,
                full_strategy_PnL=None,
                parent_complete=False,
            )
            (folder / (fixture["id"] + ".json")).write_text(
                json.dumps(result, default=str, indent=2) + "\n"
            )
            partial.append(
                dict(
                    id=fixture["id"],
                    engines=native["native_engines"],
                    outcome=native["status"],
                    result=bind(folder / (fixture["id"] + ".json")),
                )
            )
            (folder / "partial-inventory.json").write_text(json.dumps(partial, indent=2) + "\n")
        else:
            outcome = "all_frozen_source_window_components_complete_not_economic_gate"
        final = dict(
            outcome=outcome,
            fixtures_completed=len(partial),
            fixtures_expected=12,
            native_engines=sum(r["engines"] for r in partial),
            inventory=partial,
            input_and_implementation_review=bind(proof_path),
            fits=0,
            HTTP=0,
            full_strategy_returns=0,
            no_old_unknown_resurrection=True,
            parent_complete=False,
        )
        (folder / "result.json").write_text(json.dumps(final, indent=2) + "\n")
        print(json.dumps(dict(outcome=outcome, fixtures=len(partial), full_strategy_returns=0)))
    finally:
        settle(job, outcome)


if __name__ == "__main__":
    main(sys.argv[1])
