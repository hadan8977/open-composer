"""Freeze a bounded diagnostic inventory before prototype generation."""

import json
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path.cwd()
P = Path(__file__).resolve().parents[1]
CID = "martin_complete_system_20261014"
IID = CID + "_dev"


def main():
    old = ROOT / (
        "reports/research/campaigns/usic_pullback_feedback_20261013_v2/resear"
        "ch-campaign-contract.json"
    )
    campaign = json.loads(old.read_text())
    campaign.update(
        campaign_id=CID,
        created_at=datetime.now(UTC).isoformat(),
        title="Martin complete long decision system: causal geometry, holding and feedback",
        objective=(
            "Convert public method into executable decisions. First seen source-u"
            "niverse diagnostics are controls, never population Alpha. Preserve o"
            "riginal budgets and all seen windows. Independent plan/input/native/"
            "resource admission before economics."
        ),
        parent_iteration_ids=["usic_public_decision_replay_20261014"],
        child_iteration_ids=[IID],
    )
    definitions = {
        "H_CONTEXT": (
            "Leader observation separated from trigger; mature base, higher lows,"
            " multiple known support levels and conditional intraday reversal"
        ),
        "H_PATH": (
            "Re-entry, early failure, partial realization and sustained right-tai"
            "l holding in one account"
        ),
        "H_POLICY": (
            "Causal exposure feedback and executable friction policy including missed fills"
        ),
    }
    common = dict(
        universe_or_asset_class=(
            "Six predetermined public 2024 long-example names, continuous 2024/20"
            "25 controls; no stock selection deployment claim"
        ),
        horizon="Intraday decisions plus complete multi-session holding",
        data_modality=(
            "Retained actual SIP bars, raw/action reconciliation when admitted; no news/ML"
        ),
        portfolio_construction=(
            "20k research account, whole shares, gross<=1, <=35% per name, modele"
            "d costs; no broker writes"
        ),
        execution_style=(
            "Completed-bar causal intent then next observation; compare market an"
            "d capped price intents, conditional OHLC fill bounds"
        ),
        universe_selection="static_hotspot_control",
        role="control",
        promotion_eligible=False,
    )
    campaign["hypotheses"] = [
        dict(
            hypothesis_id="H_ROOT",
            parent_hypothesis_id=None,
            economic_mechanism=(
                "Public complete-system adaptation, not reconstruction of private cha"
                "mpionship account"
            ),
            **common,
        )
    ]
    campaign["hypotheses"] += [
        dict(hypothesis_id=k, parent_hypothesis_id="H_ROOT", economic_mechanism=v, **common)
        for k, v in definitions.items()
    ]
    inventory = [
        (
            "B_BREAK",
            "H_CONTEXT",
            (
                "Same leader/context tape, base/ORH breakout comparator; full common "
                "holding/risk; no hindsight entry"
            ),
        ),
        (
            "P_EMA",
            "H_CONTEXT",
            (
                "Daily rising EMA touch plus source clock trigger, no shape/AVWAP gat"
                "e; diagnostic baseline"
            ),
        ),
        (
            "P_SHAPE",
            "H_CONTEXT",
            "P_EMA plus known base maturity, confirmed higher lows and first retest; no AVWAP",
        ),
        (
            "P_ANCHOR",
            "H_CONTEXT",
            (
                "P_SHAPE plus one causally confirmed base-high/impulse anchor; conflu"
                "ence; no post-trigger anchor movement"
            ),
        ),
        (
            "P_REENTRY",
            "H_PATH",
            (
                "P_ANCHOR with new-confirmation re-entry, <=3 attempts/session and <="
                "8/base epoch; cumulative costs"
            ),
        ),
        (
            "P_HOLD",
            "H_PATH",
            (
                "P_REENTRY plus 15% trim at3R in neutral market, full trend hold in s"
                "trong market; weak followthrough exits; initial stop immutable in R "
                "accounting"
            ),
        ),
        (
            "P_FEEDBACK",
            "H_POLICY",
            (
                "P_HOLD plus closed-trade feedback; 0.125%-0.5% risk, 2% aggregate in"
                "itial-risk cap, causal monthly risk room; drawdowns never clipped"
            ),
        ),
        (
            "P_SYSTEM",
            "H_POLICY",
            (
                "P_FEEDBACK plus deterministic predecision anchor-respect ranking amo"
                "ng <=3 source-supported anchors and capped entry price; no model fit"
            ),
        ),
    ]
    campaign["branch_quotas"] = [
        dict(branch_id=k, hypothesis_id=k, min_candidates=n, max_candidates=n)
        for k, n in [("H_CONTEXT", 4), ("H_PATH", 2), ("H_POLICY", 2)]
    ]
    campaign["candidate_blueprints"] = [
        dict(
            candidate_id=i,
            hypothesis_id=h,
            branch_id=h,
            child_iteration_id=IID,
            method_variant=m,
            factor_variant=(
                "Same causal leadership/structure/market inputs; component ablations above"
            ),
            archive_descriptors=dict(mechanism_family=h),
            model_training=False,
            promotion_eligible=False,
        )
        for i, h, m in inventory
    ]
    campaign["exposure_budgets"].update(
        candidate_budget=8, cumulative_trial_exposure_budget=96, prior_effective_trial_count=16
    )  # Legacy8147 is unverified;16 prior accepted paths added conservatively.
    campaign["qd_archive"]["quality_metric"] = (
        "development_diagnostic_net_contribution_not_selectable"
    )
    out = ROOT / "reports/research/campaigns" / CID
    out.mkdir(exist_ok=False)
    (out / "research-campaign-contract.json").write_text(json.dumps(campaign, indent=2) + "\n")
    accounting = dict(
        original_preparation_used_CPU=550.49,
        original_preparation_cap_CPU=2000,
        original_review_used_CPU=335.64,
        original_review_cap_CPU=1000,
        original_economic_used_CPU=23.27,
        original_economic_cap_CPU=7200,
        original_public_logical_used=83,
        original_public_logical_cap=104,
        new_public_logical=7,
        public_remaining=14,
        original_public_direct_entity_bytes=8089944,
        original_public_entity_cap_bytes=201326592,
        unknown_web_wire_bytes=None,
        original_market_requests_used=80,
        original_market_request_cap=96,
        original_market_entity_bytes_used=55315470,
        original_market_entity_byte_cap=134217728,
        accepted_prior_trajectories=16,
        original_max_stream_envelope=120,
        new_diagnostic_ceiling=96,
        legacy8147_verified=False,
        new_candidate_definitions=8,
        new_economic_execution=0,
        new_fits=0,
        new_orders=0,
        startup_unmeasured_preparation_CPU_allowance=5,
        no_reset=True,
        Root_separate_source_rereads=2,
        root_unknown_wire_preserved=True,
    )
    (P / "cumulative-accounting.json").write_text(json.dumps(accounting, indent=2) + "\n")
    print(str(out / "research-campaign-contract.json"))


if __name__ == "__main__":
    main()
