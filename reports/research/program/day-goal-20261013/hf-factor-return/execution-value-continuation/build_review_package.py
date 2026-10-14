"""Create a reviewable frozen proposal from verified local evidence, without economics."""

import hashlib
import itertools
import json
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path.cwd()
P = Path(__file__).resolve().parent
OLD = P.parent
ITER = "t20261014_hf_execution_value"
OWNER = "66ebc2b7-c533-4992-82fe-cece4f3e2b12"


def binding(path):
    data = path.read_bytes()
    return {
        "path": str(path.relative_to(ROOT)),
        "sha256": hashlib.sha256(data).hexdigest(),
        "bytes": len(data),
    }


def save(name, value):
    (P / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


at = datetime.now(UTC).isoformat()
old_direction = json.loads(
    (
        ROOT
        / "reports/research/iterations/t20261013_hf_factor_conditional_method/direction-review.json"
    ).read_text()
)
old_cards = [
    json.loads(line)
    for line in (ROOT / "reports/harness/source_cards/day20261013_hf_factor_method.jsonl")
    .read_text()
    .splitlines()
    if line.strip()
]
cards = [card for card in old_cards if card["claim_id"] in {"hf_main", "hf_construct"}]
local_cards_path = P / "policy-source-cards.jsonl"
sources = [
    dict(source, source_card_path=str(local_cards_path.relative_to(ROOT)))
    for source in old_direction["sources"]
    if source["claim_id"] in {"hf_main", "hf_construct"}
]
new = [
    {
        "claim_id": "hf_OA_continuity_multihorizon",
        "claim": (
            "HF OA5.2 discusses amortizing decision costs; OA5.3.1 uses separa"
            "tely formed multi-horizon 5-minute forecasts with linear trading "
            "costs, while OA7.5 studies maintaining the prior overnight positi"
            "on. These do not establish the same value for a delayed single 15"
            "-minute forecast and a funded 20bp cash account."
        ),
        "url": "https://public.econ.duke.edu/~boller/Papers/HFML_Sup_App.pdf",
        "source_type": "paper",
        "published_or_updated_at": "2024-07-18",
        "market_and_period": (
            "US factor/market forecasts 2004-2020; author 5-minute and 15-minute studies"
        ),
        "applicability": (
            "Source-led finite-horizon linear-cost policy adaptation; forecast"
            " horizon and overnight definitions must stay explicit"
        ),
        "limitations": (
            "The current archive has one 15-minute forecast, not the three ind"
            "ependently trained author forecasts. Source phi optimum is ex pos"
            "t. Source mathematical/quoted-spread performance is not funded 20"
            "bp performance."
        ),
        "independent_replication": (
            "No independent exact source replication established; inherited fu"
            "ll local application is negative"
        ),
        "fetched_at": "2026-10-13T14:12:15.125900+00:00",
        "snapshot": OLD / "sources/hf-zoo-appendix.txt",
        "quote": (
            "the first intraday position of each day must rebalance against the overnight position"
        ),
        "location": "OA5.2 pp38-39; OA5.3.1 pp41-43; OA7.5 pp61-62",
    },
    {
        "claim_id": "GP2013_cost_and_decay_limits",
        "claim": (
            "Gârleanu and Pedersen link dynamic trading to alpha decay and exi"
            "sting positions; their principal closed-form and commodity-future"
            "s analysis uses quadratic trading costs, and they distinguish pro"
            "portional-cost no-trade behavior. The result is an economic ratio"
            "nale, not a validated 20bp linear-cost SPY policy."
        ),
        "url": "https://w4.stern.nyu.edu/facdir/lpederse/papers/DynamicTrading.pdf",
        "source_type": "paper",
        "published_or_updated_at": "2013-12-01",
        "market_and_period": (
            "General quadratic-cost predictable-return model and commodity-fut"
            "ures empirical application"
        ),
        "applicability": (
            "Explicit fast/slow alpha-decay hypotheses and existing-position-a"
            "ware controls, with local linear-cost solver"
        ),
        "limitations": (
            "Do not import quadratic-cost partial-adjustment formulas or the c"
            "ommodity empirical gain as SPY economic evidence; no newly traine"
            "d decay model."
        ),
        "independent_replication": "None claimed for this funded SPY adaptation",
        "fetched_at": "2026-10-14T07:05:11.927308+00:00",
        "snapshot": P / "GP2013-author.txt",
        "quote": (
            "Like Heaton and Lucas (1996) and Grinold (2006), we also rely on "
            "quadratic trading costs."
        ),
        "location": "Printed pp2312-2315; equations1-4",
    },
]
for row in new:
    normalized = " ".join(row["snapshot"].read_text().split())
    assert " ".join(row["quote"].split()) in normalized
    snap = binding(row["snapshot"])
    card = {
        "claim_id": row["claim_id"],
        "claim": row["claim"],
        "source_url": row["url"],
        "source_type": row["source_type"],
        "accessed_at": at[:10],
        "fetched_at": row["fetched_at"],
        "verification_status": "source_verified",
        "source_sha256": snap["sha256"],
        "snapshot_path": snap["path"],
        "quote": row["quote"],
        "location": row["location"],
        "limitations": row["limitations"],
        "verified_from": (
            "Existing downloaded original bytes; local extraction/read, no new request"
        ),
    }
    cards.append(card)
    sources.append(
        {
            **{
                key: value
                for key, value in row.items()
                if key not in {"snapshot", "quote", "location"}
            },
            "snapshot_path": snap["path"],
            "sha256": snap["sha256"],
            "source_card_path": str(local_cards_path.relative_to(ROOT)),
        }
    )
local_cards_path.write_text("".join(json.dumps(card, ensure_ascii=False) + "\n" for card in cards))
queries = list(old_direction["queries"]) + [
    {
        "query": (
            "Inherited actual author-PDF open/find and direct download: Dynami"
            "c Trading with Predictable Returns and Transaction Costs; quadrat"
            "ic versus proportional costs and alpha decay"
        ),
        "searched_at": "2026-10-14T07:05:10.285510+00:00",
        "opened_urls": ["https://w4.stern.nyu.edu/facdir/lpederse/papers/DynamicTrading.pdf"],
        "receipt": binding(P / "source-ledger.json"),
        "kind": (
            "Reuse original author-source navigation; no claim of a new search query or new request"
        ),
    }
]
save(
    "query-manifest.json",
    {
        "schema_version": 1,
        "iter_id": ITER,
        "queries": queries,
        "reused_native_query_receipt": binding(
            ROOT
            / (
                "reports/research/iterations/t20261013_hf_factor_conditional_metho"
                "d/direction-review.json"
            )
        ),
        "additional_requests_this_turn": 0,
    },
)
save(
    "pre-iteration-knowledge-baseline.json",
    {
        "schema_version": 1,
        "iter_id": ITER,
        "captured_at_utc": at,
        "knowledge_index": binding(ROOT / "reports/research/knowledge/index.json"),
        "inherited_native_baseline": binding(OLD / "native-knowledge-baseline.json"),
        "negative_complete_result": binding(OLD / "complete-costed-completion-receipt.json"),
        "received_existing_attribution": binding(P / "existing-path-attribution.json"),
        "new_economic_results_seen": False,
        "old_all_windows_seen": True,
        "new_training_or_model_inference": 0,
    },
)
direction = {
    "schema_version": 3,
    "iter_id": ITER,
    "reviewed_at": at,
    "decision": "proceed",
    "decision_scope": (
        "Source-led direction proposal and evidence completeness only; not"
        " independent plan approval or economic allocation"
    ),
    "objective": (
        "Can continuous, linear-cost, alpha-decay-aware use of existing HF"
        " forecasts add executable net SPY value under the original 20bp/s"
        "trict settled-cash conditions?"
    ),
    "target_regime_and_horizon": (
        "Already-seen 2016-2020 funded SPY, continuous 15-minute decisions"
        " with original one-window delay; market-component diagnosis, not "
        "unseen validation or 2026 readiness."
    ),
    "existing_solution_comparison": (
        "Reuse all immutable 20-pipeline fits, 800 diagnostics and 100 fun"
        "ded books. Frozen forced-night/open policy erases most model effe"
        "cts; compare a small horizon/decay set, matching market/zero/pass"
        "ive/risk controls rather than new models."
    ),
    "remaining_evidence_gap": (
        "Source multi-horizon training is unavailable without prohibited r"
        "efits; actual delayed signal lifetime, linear costs, real shares "
        "and risk-matched incremental value remain untested. Original fact"
        "or/PIT and fills are conditional."
    ),
    "negative_experiments_checked": (
        "All 20 original 20bp books lost; 18 match overnight-only; 5bp fra"
        "ctional diagnostics also lose; IDX/INV and stale counterevidence "
        "retained. Weak width/HGB tests are not a global HF refutation."
    ),
    "cost_and_execution_assumptions": (
        "20bp each side primary, 40bp stress; original delayed cash, whole"
        " shares, known sizing and single next reference attempt; no fundi"
        "ng relaxation, overnight Maintain with zero predicted overnight a"
        "lpha; no brokers or new market data."
    ),
    "stop_condition": (
        "Stop this adaptation allocation if signal expires before executio"
        "n, cumulative net benefit cannot pay original fees, or gains redu"
        "ce to passive/overnight risk. Preserve unresolved broader mechani"
        "sm and power limits; no post-result tuning or OOS reset."
    ),
    "queries": queries,
    "sources": sources,
    "cheapest_decisive_test": {
        "action": (
            "Following independent review and real native admissions, verify m"
            "atured delayed score-to-return horizons, then execute the fixed m"
            "atched policy set with real settled-cash events and paired net/ri"
            "sk inference."
        ),
        "pass_condition": (
            "Source lifetime is empirically credible and broad forecasts add j"
            "oint-family net value over matched market/zero and causal exposur"
            "e controls, under unchanged primary costs and physical funding."
        ),
        "falsification_condition": (
            "Signal information only concerns the expired label, remains too s"
            "mall/short-lived to pay costs, or apparent gain comes from additi"
            "onal passive risk; diagnose power before interpreting a null."
        ),
        "max_compute_minutes": 84,
    },
    "source_evidence_bindings": [
        {
            "claim_id": row["claim_id"],
            "source_card_path": row["source_card_path"],
            "snapshot_path": row["snapshot_path"],
            "snapshot_sha256": row["sha256"],
            "source_url": row["url"],
        }
        for row in sources
    ],
    "query_manifest": binding(P / "query-manifest.json"),
    "pre_iteration_knowledge_baseline": binding(P / "pre-iteration-knowledge-baseline.json"),
}
save("direction-review.json", direction)
policies = [
    {"policy_id": "CONT_H1_SLOW", "horizon": 1, "rho": 2 ** (-1 / 4)},
    {"policy_id": "DP_H16_FAST", "horizon": 16, "rho": 0.5},
    {"policy_id": "DP_H16_SLOW", "horizon": 16, "rho": 2 ** (-1 / 4)},
]
streams = [
    "PLS_IDX_CTS",
    "PLS_IDX_MKT",
    "PLS_IDX_STALE",
    "PLS_INV_CTS",
    "HGB_IDX_CTS",
    "AR26_CTS",
    "ZERO",
    "NEG_PLS",
]
rows = []
for policy, stream, anchor in itertools.product(policies, streams, [0, 1]):
    rows.append(
        {
            "candidate_id": f"{policy['policy_id']}__{stream}__B{anchor}",
            "policy": policy,
            "stream": stream,
            "anchor": anchor,
            "kind": "fixed_policy_information_configuration",
            "primary_cost_bps_each_side": 20,
            "stress_cost_bps_each_side": 40,
            "primary_capital_USD": 20000,
            "planned_funded_views": 2,
            "optional_independent_4k_views": 2
            if stream in {"PLS_IDX_CTS", "PLS_IDX_MKT", "ZERO"}
            else 0,
            "modality_role": "existing_return_forecast_to_deterministic_position_policy",
            "research_role": "market_component_method",
            "promotion_eligible": False,
        }
    )
for policy, stream, anchor in itertools.product(policies, ["PLS_IDX_CTS", "PLS_IDX_MKT"], [0, 1]):
    rows.append(
        {
            "candidate_id": f"{policy['policy_id']}__NEUTRAL_{stream}__B{anchor}",
            "policy": policy,
            "stream": stream,
            "anchor": anchor,
            "kind": "causal_prior63session_exposure_control",
            "primary_cost_bps_each_side": 20,
            "stress_cost_bps_each_side": 40,
            "primary_capital_USD": 20000,
            "planned_funded_views": 2,
            "optional_independent_4k_views": 0,
            "modality_role": "no_direction_forecast_prior_exposure_only",
            "research_role": "market_component_method",
            "promotion_eligible": False,
        }
    )
assert len(rows) == 60 and len({row["candidate_id"] for row in rows}) == 60
assert sum(row["planned_funded_views"] for row in rows) == 120
assert sum(row["optional_independent_4k_views"] for row in rows) == 36
plan_bind = binding(P / "scientific-plan-v1.md")
save(
    "candidate-manifest-proposed.json",
    {
        "schema_version": 3,
        "iter_id": ITER,
        "parent_task": "DAY3-HF-FACTOR-RETURN",
        "continuation_task": "HF-EXECUTION-VALUE-CONTINUATION-20261014",
        "author": OWNER,
        "status": "proposed_pending_independent_review_no_economic_trials",
        "scientific_plan": plan_bind,
        "input_bindings": binding(P / "local-source-and-preparation-bindings.json"),
        "research_role": "market_component_method",
        "candidate_count": 60,
        "policy_information_configurations": 48,
        "causal_risk_controls": 12,
        "maximum_new20k_books": 120,
        "maximum_conditional4k_books": 36,
        "completed_new_books": 0,
        "new_model_fits": 0,
        "actual_economic_trial_rows": 0,
        "candidates": rows,
        "primary_validation": "seen conditional diagnostics only, no selectable promotion cohort",
        "policy_parameters": {
            "gamma": 10,
            "risk_history_sessions": 63,
            "risk_min_history_sessions": 30,
            "risk_fallback_simple_step_sigma": 0.004,
            "position_grid": [0, 0.25, 0.5, 0.75, 1],
            "additional_state": "actual held weight",
            "execution_delay_windows": 1,
            "forecast_transform": "expm1(rho**(L+s-1)*existing_log_score)",
            "terminal_planning_liability": "-c*abs(w-anchor), never cash",
            "overnight": "Maintain; no forecast alpha extrapolation",
            "missing_mature_packets": (
                "no added risk, hold; four consecutive then next reference risk reduction to anchor"
            ),
        },
        "cost_contract": "original actual one-way 20bp; 40bp stress independently cash-feasible",
        "funding_contract": (
            "strict original delayed settled sale cash, dividends/actions, fro"
            "zen whole lots and single scheduled reference attempt"
        ),
        "fallback_contract": (
            "structural first-hour missing holds state; explicit mature missin"
            "g policy; unfilled attempts never earn shadow PnL"
        ),
        "selection": (
            "none; all fixed policies/roles reported, no winner promotion or neighboring tuning"
        ),
        "planned_native_location": f"reports/research/iterations/{ITER}/candidate-manifest.json",
        "native_canonical_manifest_not_created_or_approved": True,
    },
)
save(
    "scientific-plan.json",
    {
        "schema_version": 3,
        "iter_id": ITER,
        "author": OWNER,
        "parent_task": "DAY3-HF-FACTOR-RETURN",
        "continuation_task": "HF-EXECUTION-VALUE-CONTINUATION-20261014",
        "status": "ready_for_independent_deep_plan_review",
        "economic_execution_admitted": False,
        "parent_question_complete": False,
        "full_definition": plan_bind,
        "candidate_manifest": binding(P / "candidate-manifest-proposed.json"),
        "direction_evidence": binding(P / "direction-review.json"),
        "authority_resource_reconciliation": binding(
            P / "authority-and-resource-reconciliation.json"
        ),
        "policies": policies,
        "information_streams": streams,
        "capital_anchors": [0, 1],
        "role_matrix": {
            "factor_generation": (
                "not applicable; reuse frozen current-vintage factors/negative evidence"
            ),
            "return_forecasting": (
                "already completed HF predictions; no refits, optimizer or new inference"
            ),
            "return_ranking": "not applicable to single asset",
            "risk_prediction": "no model; causal fixed prior-price second moment",
            "regime_or_meta_gating": "no trained gate or result-selected regime",
            "sizing": "fixed finite-state linear-cost policy with integer physical execution",
            "uncertainty": "day/block paired uncertainty and MDE, no fitted uncertainty model",
            "fallback": "fixed mature/missing/strict-cash execution policy",
            "new_modalities": "none; no news, events, LLM or DS contribution",
        },
        "validation": {
            "physical_window": ["2016-01-04", "2020-12-31"],
            "all_windows_seen": True,
            "untouched_OOS": False,
            "primary_comparison_family_size": 12,
            "comparison": "3 policies x 2 anchors x {wide-market,wide-zero}",
            "HAC_lag_sessions": 20,
            "block_sessions": 5,
            "bootstrap_replicates": 1999,
            "seed": 20261014,
            "family_inference": "joint maxT 95pct intervals; 80pct MDE",
            "source_label_or_current_vintage_readiness_does_not_establish_paper_readiness": True,
            "PBO_SPA_promotion_evidence": None,
            "inherited_effective_exposure": 4453,
        },
        "native_gates": {
            "direction": "current preparation check; not economic admission",
            "independent_plan": "pending Root capacity after P0",
            "Root_economic_allocation": "pending",
            "independent_implementation": "pending actual code and synthetic checks",
            "knowledge_build_scout_assess": "not run for proposed iteration",
            "iteration_validate": "not run for proposed iteration",
            "fresh_memory": "required immediately before every actual computation",
        },
        "proposed_same_pool_package_limit_CPU": 5000,
        "current_source_or_funding_permission_expanded": False,
        "review_route": (
            "Independent review after Root P0; bind this JSON and full_definit"
            "ion MD, then return to same owner for complete execution"
        ),
        "native_finish_notification_only": True,
    },
)
print(
    "60 fixed proposal identities, exact budgets and verified source s"
    "napshots prepared; economics=0."
)
