"""Prefix interpretation over saved source component results; no engine/replay."""

# ruff: noqa: E402
import json
import resource
import sys
from pathlib import Path

P = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(P / "code"))
from consumer_admission import ROOT, bind, claim_launch, receipt, settle


def interpretation(native, reference):
    unknown = native.get("firstunknown")
    first_ns = unknown.get("at_ns") if unknown else None
    if native["native_engines"] == 0:
        reason = "invalid_R0_no_native_protection"
    elif first_ns is not None and reference["event_ns"] >= first_ns:
        reason = "at_or_after_native_firstunknown"
    else:
        reason = "conditional_controlled_component_prefix_only"
    known = reason == "conditional_controlled_component_prefix_only"
    return dict(
        event_ns=reference["event_ns"],
        source_ordinal=reference["source_ordinal"],
        observed_price_reference=reference["observed_price_reference"] if known else None,
        known_component_prefix=known,
        interpretation_reason=reason,
        firstunknown_ns=first_ns,
        firstunknown_reason=unknown["reason"] if unknown else None,
        native_protective_acceptance_explicitly_reported=False,
        broker_stop_election="unknown",
        certified_then_nbbo_necessary_condition=None,
        raw_source_counterfactual_annotation=dict(reference),
    )


def main(job):
    claim_launch(job, "consumer")
    resource.setrlimit(resource.RLIMIT_CPU, (5, 6))
    outcome = "prefix_annotation_failed"
    try:
        assert receipt(job)["source_science_review"] == bind(
            P / "economic-results/source-clock-independent-review.json"
        )
        # Pure actual function tests: original source and native state unchanged.
        native = dict(native_engines=1, firstunknown=dict(at_ns=100, reason="rejected"))
        before = dict(event_ns=99, source_ordinal=1, observed_price_reference=True)
        after = dict(event_ns=100, source_ordinal=2, observed_price_reference=True)
        old = repr((native, before, after))
        assert interpretation(native, before)["observed_price_reference"] is True
        assert interpretation(native, after)["observed_price_reference"] is None
        invalid = interpretation(dict(native_engines=0), before)
        assert invalid["observed_price_reference"] is None
        assert repr((native, before, after)) == old
        folder = P / "economic-results/source-clock-real-probe-martin-source-window-v2-20261014"
        original = json.loads((folder / "result.json").read_text())
        rows = []
        for entry in original["inventory"]:
            result = json.loads((ROOT / entry["result"]["path"]).read_text())
            native = result["native_quote_research_proxy"]
            rows.append(
                dict(
                    fixture=entry["id"],
                    original_result=entry["result"],
                    firstunknown=native.get("firstunknown"),
                    native_engines=native["native_engines"],
                    original_known_closed_R=native.get("closed_R"),
                    known_account_price_reference=[
                        interpretation(native, r)
                        for r in result["necessary_observed_price_reference"]
                    ],
                    full_strategy_R=None,
                )
            )
        output = dict(
            version="V2_saved_result_prefix_interpretation_v3",
            original_fixture_versions_unchanged=True,
            original_result=bind(folder / "result.json"),
            code=bind(Path(__file__)),
            native_engines_rerun=0,
            actual_market_chronological_replay=0,
            no_source_BBO_or_broker_certification=True,
            protective_submission_not_acceptance=True,
            no_native_R_feedback_or_price_state_mutation=True,
            rows=rows,
            full_strategy_returns=0,
            parent_complete=False,
        )
        path = P / "economic-results/source-v2-known-prefix-interpretation.json"
        path.write_text(json.dumps(output, indent=2) + "\n")
        outcome = "saved_component_prefix_annotations_complete"
        print(json.dumps(dict(outcome=outcome, result=bind(path))))
    finally:
        settle(job, outcome)


if __name__ == "__main__":
    main(sys.argv[1])
