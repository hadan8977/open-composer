"""Collect full accepted-scope output; no fitting, policy selection or repricing."""

import json
from datetime import UTC, datetime

from hf_completion_resources import snapshot
from hf_features import P, bind, save

R = P / "economic/results"


def compare(values, reference, field):
    available = [(k, v[field]) for k, v in values.items() if v.get(field) is not None]
    baseline = reference.get(field)
    return dict(
        ready=baseline is not None,
        compared=len(available) if baseline is not None else 0,
        higher=[k for k, v in available if baseline is not None and v > baseline],
        equal=[k for k, v in available if baseline is not None and v == baseline],
        lower=[k for k, v in available if baseline is not None and v < baseline],
        reference_value=baseline,
    )


def main():
    plan = json.loads((P / "scientific-plan.json").read_text())
    ids = [r["candidate_id"] for r in plan["candidates"]]
    assert len(ids) == 20
    names = [
        "statistical-results.json",
        "paired-results.json",
        "funded-results.json",
        "fractional-diagnostic-results.json",
        "host-results.json",
        "descriptive-DSR.json",
    ]
    data = {n: json.loads((R / n).read_text()) for n in names}
    funded = data["funded-results.json"]
    diagnostic = data["fractional-diagnostic-results.json"]
    host = data["host-results.json"]
    assert len(data["statistical-results.json"]) == 20 and len(diagnostic) == 800
    fee_panels = {}
    for bps in [0, 1, 5, 20, 40]:
        candidates = {k: funded[f"{k}__{bps}"]["full"] for k in ids}
        references = {
            k: funded[f"{k}__{bps}"]["full"]
            for k in ["CASH", "BIL_BH", "SPY_BH", "SPY_OVERNIGHT_ONLY"]
        }
        fee_panels[str(bps)] = dict(
            candidates=candidates,
            references=references,
            comparisons={
                name: {
                    field: compare(candidates, reference, field)
                    for field in ["terminal_NAV", "CAGR", "Sharpe_netstd"]
                }
                for name, reference in references.items()
            },
            positive_terminal_profit=[
                k
                for k, v in candidates.items()
                if v.get("terminal_NAV") is not None and v["terminal_NAV"] > 20000
            ],
            sorted_terminal_diagnostic_only=sorted(
                ids,
                key=lambda k: (
                    candidates[k].get("terminal_NAV")
                    if candidates[k].get("terminal_NAV") is not None
                    else float("-inf")
                ),
                reverse=True,
            ),
            ranking_is_expost_description_not_a_new_selected_policy=True,
        )
    host_comparisons = {}
    if host.get("ready"):
        for bps in [20, 40]:
            relevant = {
                k: v
                for k, v in host["results"].items()
                if k.endswith(f"__{bps}") and k.split("__")[1] in ids
            }
            for control in ["CASH", "BIL", "SPY", "PLS_IDX_MKT"]:
                valid = {
                    k: v["controls"][control]
                    for k, v in relevant.items()
                    if v["controls"][control].get("terminal_dollar_difference") is not None
                }
                host_comparisons[f"{bps}__{control}"] = dict(
                    compared=len(valid),
                    unknown=len(relevant) - len(valid),
                    positive_terminal_difference={
                        k: v["terminal_dollar_difference"]
                        for k, v in valid.items()
                        if v["terminal_dollar_difference"] > 0
                    },
                    negative_terminal_difference={
                        k: v["terminal_dollar_difference"]
                        for k, v in valid.items()
                        if v["terminal_dollar_difference"] < 0
                    },
                    zero_terminal_difference=[
                        k for k, v in valid.items() if v["terminal_dollar_difference"] == 0
                    ],
                    HAC_is_pairwise_descriptive_not_family_adjusted=True,
                )
    trials = [
        json.loads(x) for x in (P / "economic/model-trial-ledger.jsonl").read_text().splitlines()
    ]
    output = dict(
        schema_version=1,
        task_id="DAY3-HF-FACTOR-RETURN",
        as_of_utc=datetime.now(UTC).isoformat(),
        scope=(
            "Full frozen current-vintage conditional source method and costed raw-reference "
            "cash-proxy application; not true fills/PIT/source-original15m/OOS"
        ),
        complete_numeric_output_collected=True,
        author_interpretation_pending=True,
        independent_result_acceptance_pending=True,
        inputs={
            "plan": bind(P / "scientific-plan.json"),
            "implementation": bind(P / "implementation-manifest.json"),
            "implementation_review": bind(P / "independent-implementation-review.json"),
            "complete350": bind(P / "economic/full-resource-projection.json"),
        },
        output_bindings={n: bind(R / n) for n in names},
        capital_initial_USD=20000,
        host_initial_USD=16000,
        independent_sleeve_initial_USD=4000,
        inventory=dict(
            pipelines=20,
            model_trials_unique=len({r["logical_trial_id"] for r in trials}),
            model_trial_rows=len(trials),
            diagnostics=800,
            funded20k_model_books=100,
            independent4k_model_books=40,
            host_forms=2,
            old_incomplete350_exposure_and_all_failures_retained=True,
        ),
        fee_panels=fee_panels,
        six_primary_common_All_target_contrasts=data["paired-results.json"],
        host_ready=host.get("ready"),
        host_clock={k: host.get(k) for k in ["first_common_close", "last_common_close", "rows"]},
        matched_host_terminal_comparisons=host_comparisons,
        economic_decision_rule=plan["decision_rule"],
        resources_asof_before_this_report_job_settles=snapshot(),
        performance_source_denominator_not_standard_netstd=True,
        no_source_cleaning_PIT_fill_settlement_or_borrow_certification=True,
        all_history_seen=True,
        workflow_pass=False,
        research_pass=False,
        ml_contribution_pass=False,
        paper_ready_pass=False,
        promotion_eligible=False,
        new_broker_orders=0,
        new_paid_USD=0,
    )
    save(P / "complete-costed-result.json", output)
    print(
        json.dumps(
            dict(status="full_numeric_collected", result=bind(P / "complete-costed-result.json"))
        )
    )


if __name__ == "__main__":
    main()
