from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import numpy as np
import pandas as pd

from open_composer.market_calendar import us_equity_session_dates
from open_composer.models.strategy_spec import load_strategy_spec
from open_composer.research.campaign import (
    ResearchCampaignContract,
    effective_trial_count_from_ledger,
    load_campaign_contract,
    recompute_candidate_promotion_metrics,
    validate_campaign_contract,
)
from open_composer.research.campaign_statistics import (
    annualized_sharpe,
    deflated_sharpe_probability,
    recompute_campaign_statistics,
)
from open_composer.research.iteration_dossier import (
    candidate_authorization_binding_sha256,
    validate_iteration_dossier,
)
from open_composer.research.quality_diversity import (
    QualityDiversityCandidate,
    append_allocation_entry,
    build_quality_diversity_archive,
    initialize_allocation_ledger,
    quality_diversity_policy_from_campaign,
)
from open_composer.storage import write_json
from open_composer.strategy_versions import strategy_content_hash

CAMPAIGN_ID = "mom_breadth_qd_r1"
CAMPAIGN_ROOT = Path("reports/research/campaigns") / CAMPAIGN_ID
ITERATION_ROOT = Path("reports/research/iterations")
DEVELOPMENT_ATTEMPT_PATH = CAMPAIGN_ROOT / "development-evaluation-attempt.json"
DEVELOPMENT_RECEIPT_PATH = CAMPAIGN_ROOT / "development-evaluation-receipt.json"
DEVELOPMENT_RECOVERY_AMENDMENT_PATH = (
    CAMPAIGN_ROOT / "development-publication-recovery-amendment.json"
)
RUNNER_PATH = Path("open_composer/research/mom_breadth_qd_r1.py")
RUNNER_TEST_PATH = Path("tests/test_mom_breadth_qd_r1.py")
GENERATOR_PATH = Path("scripts/prepare_mom_breadth_qd_r1.py")
INTEGRITY_AMENDMENT_PATH = CAMPAIGN_ROOT / "development-integrity-repair-amendment.json"
LOCKED_IMPLEMENTATION_PATHS = {
    "generator": GENERATOR_PATH,
    "development_runner": RUNNER_PATH,
    "development_runner_tests": RUNNER_TEST_PATH,
    "campaign_implementation": Path("open_composer/research/campaign.py"),
    "campaign_statistics_implementation": Path("open_composer/research/campaign_statistics.py"),
    "iteration_dossier_implementation": Path("open_composer/research/iteration_dossier.py"),
    "market_calendar_implementation": Path("open_composer/market_calendar.py"),
    "quality_diversity_implementation": Path("open_composer/research/quality_diversity.py"),
    "storage_implementation": Path("open_composer/storage.py"),
    "strategy_spec_implementation": Path("open_composer/models/strategy_spec.py"),
    "python_project": Path("pyproject.toml"),
    "python_lock": Path("uv.lock"),
}
BENCHMARK_SNAPSHOT = Path(
    "data/research/mom_breadth_qd_r1_development/leveraged/snapshot-manifest.json"
)
EXCHANGE_CALENDAR_PATH = Path(
    "data/research/mom_breadth_qd_r1_development/us-equity-session-calendar.json"
)
DEVELOPMENT_START = date(2017, 2, 1)
VALIDATION_START = date(2021, 1, 4)
VALIDATION_END = date(2023, 12, 29)
PRIMARY_COST_BPS = 20
COST_VIEWS = (10, 20, 40)
BENCHMARK_SYMBOLS = ("SPY", "QQQ", "XLK", "BIL", "TQQQ")
PORTFOLIO_RETURN_IDENTITY = "open_t_to_open_t_plus_1_simple_return_net_of_turnover_cost"
BENCHMARK_FAMILY_IDS = (
    "same_symbol_buy_and_hold",
    "equal_weight_full_spec_universe",
    "SPY_buy_and_hold_market_proxy",
    "QQQ_buy_and_hold_growth_proxy",
    "XLK_buy_and_hold_sector_theme_proxy",
    "BIL_buy_and_hold_cash_proxy",
    "TQQQ_buy_and_hold_leveraged_growth_proxy",
    "ex_post_best_symbol_report_only",
)
BENCHMARK_ALLOCATION_IDENTITY = "fixed_initial_notional_buy_and_hold_no_rebalance"
EXPECTED_DEVELOPMENT_EFFECTIVE_TRIAL_COUNT = 8195
RECOVERY_MUTABLE_PREREGISTRATION_FILES = (
    "knowledge-baseline.json",
    "knowledge-scout.json",
    "knowledge-assessment.json",
    "knowledge-context.json",
    "model-reuse-decision.json",
    "search-space.json",
    "data-feasibility.json",
    "universe-contract.json",
    "candidate-manifest.json",
)
FEASIBILITY_REFERENCE_LOCK_KEYS = {
    "benchmark_contract": "benchmark_contract",
    "branch_source_evidence": "branch_source_evidence",
    "campaign_contract": "campaign_contract",
    "campaign_source_cards": "campaign_source_cards",
    "candidate_policy_contract": "candidate_policy_contract",
    "capability_registry": "capability_registry",
    "cost_contract": "cost_contract",
    "cumulative_trial_contract": "cumulative_trial_contract",
    "data_contract": "data_contract",
    "development_partition_contract": "development_partition_contract",
    "exchange_calendar_artifact": "exchange_calendar_artifact",
    "factor_library": "factor_library_json",
    "feature_contract": "feature_contract",
    "holdout_contract": "holdout_contract",
    "label_contract": "label_contract",
    "market_data_artifact_1": "market_data_artifact_1",
    "modality_role_matrix": "modality_role_matrix",
    "promotion_benchmark_data_artifact_1": "promotion_benchmark_data_artifact_1",
    "source_cards": "iteration_source_cards",
    "validation_contract": "validation_contract",
}
PIT_DEPENDENCY_BLOCKERS = (
    "point_in_time_US_equity_membership_with_inactive_and_delisted_securities_is_not_configured",
    "permanent_security_identity_corporate_actions_and_delisting_returns_are_unavailable",
    "current_stock_lists_and_static_2026_membership_are_forbidden_substitutes",
)
DEVELOPMENT_STAGE_BLOCKERS = (
    "paper_orders_and_paper_fills_are_outside_this_stage",
    "frozen_OOS_is_unread_until_campaign_archive_and_allocation_ledger_are_sealed",
)
ADAPTIVE_SELECTION_DISCLOSURE = (
    "All earlier momentum research and historical prices are exposed; this campaign's "
    "frozen OOS remains unread until the development archive and allocation ledger are sealed."
)
# Exact fingerprints observed with the reserved failed attempt.  Recovery may
# validate these files but must not regenerate or silently bless changed memory.
RECOVERY_KNOWLEDGE_FILENAMES = (
    "knowledge-baseline.json",
    "knowledge-scout.json",
    "knowledge-assessment.json",
    "knowledge-context.json",
    "model-reuse-decision.json",
)
RECOVERY_KNOWLEDGE_FILE_SHA256 = {
    "mom_breadth_calendar_flow_r1": (
        "cb04386c520487c57d9c389838cff2e991f9bbfe268db6bd5af8a18a0b80e799",
        "fd6bc652a8717868e028de723057ab79147dd852cd6e311695e07c6b2f17f2ba",
        "def15061463c7b53f18ee4437c0ffdb3e41661b3d710aed1d0b8826ac22b8859",
        "a4f9a9c1dabf62833c48c9a3e189be5dd037f12fb77e0efe6b37056c3542f5b5",
        "dd9ce7f6b7305c1d8e82c23078cf3d8d3db37091ccb6fde621e41c5e35b5b5ae",
    ),
    "mom_breadth_cross_session_r1": (
        "cfbd1d81daabaa86f54fd8b195e93aa3547b54a2632346593c84bf70fddc62ad",
        "30dc90e23b061efbe0a5d6e62d5da4300339dbefc8b7bf017e201649d3f36d3b",
        "0a104f61a0a674a86e2ed07fb88a7006502144342e48828f62f049ba7aef6375",
        "0d20bd2128490e294211e38c311da0e06ae73e7f03309e4215cb81f57a7dfa8e",
        "1571e814b0657d1c08f74d3d4bd207bfc03617742e995f019e3cd73267561c2f",
    ),
    "mom_breadth_crossasset_trend_r1": (
        "97286ce9678824491009c061356c3fb26b123e0cb67812517b72d566af5f9343",
        "fff0815d8555e972b02045784e25f27ff66ce7303589ae963603677e86dd6a8c",
        "21f01f35053a5dfa0909eba4edf8d2192796a15a8deb43a9c69e67b9c408aab8",
        "4e98b7efc7d14925148bebdcd64ce446c3f1d206c18967fa0cdb7ebead785ffb",
        "5bcea55f7590ff682b9e1225a8042b6cc6d0425c8388f60cf6778723387e7513",
    ),
    "mom_breadth_pit_xsmom_r1": (
        "aa3e331e178ced9e59690268e7cb0713e7bef07780a7fa730c437985621d7f76",
        "f66b319c61bf7eb96b9898e3ab3e42667b015233ff5c7992018d12c740fbfea2",
        "086ed742a735de1057d22608159319c85d93d46ed1587b659d0b0fe90a8fb919",
        "83dbdaf0dc5fbe87d2b329cb7211f61d98806ea1e68fb4f24803280fec122a39",
        "7169316ed3f16d59708cafc788914d66a9195dcb2052366b63e7d7d8781cced9",
    ),
    "mom_breadth_short_reversal_r1": (
        "d4515e20531ce9d3fd7301fb1b205da36bd76d7082252ce3a083f7ed235e6515",
        "747d36d54146b19c3434c2f4ba6861c7ca988dc2991144b8d8f49e2f78d8f299",
        "22deb3a136070031f49e4277e131839ee65506a92ecbacf404aaba59fc2dc2a7",
        "4e5bca9415f3aebc07818e6ec62345f267d60da3a996c027a9170d3ad40e56ab",
        "4a50b7d194a4932720980740c4dcb506ced08ea41da33e622a17c553a927c7f3",
    ),
    "mom_breadth_static_hotspot_control_r1": (
        "2643cd2c251c5ae081ced6ce96ec8f9beffc71852e8d665a7bbf17f4cc120f28",
        "f4ae0d8ee659dc8ea4de7ca4245643bb9b19c11f1879c4c2d3d360e67380c597",
        "3610c046478ecfee313e0df5e932f1be0b6ee8215e1440c441cee23f3a684a8e",
        "2e80439ef7054bbcd7836dda3288ac5e6819707591f9a2542a370ee3ba10e8bc",
        "5428ca5b3192574f42e001ae720f21eaeda04d4ddedad811b4ea970b6bca252c",
    ),
    "mom_breadth_volatility_beta_r1": (
        "7e0169340892604210554ca48d64fa14f38028a69884ba92a18a867cbc535ab3",
        "655f8f2d988c8575f4a303b927b695e3d39e6fa194901b31a531941a3f7a6ca2",
        "93fa299292705dc536e7ac339bfff1d111fbcfb5ad31df02fdf6ebf1983aa637",
        "ed4354ca9d2910ea16f9fc919b31da7e300f93deb31534c94994f655d6a0a1f2",
        "2b3318125d75eb4a056f55881c22602bece869cd255b288e1b0a5f15bd5b9e12",
    ),
}
RECOVERY_KNOWLEDGE_PAYLOAD_SHA256 = {
    "mom_breadth_pit_xsmom_r1": "69f1b10104ef73fbc1bc55d66a3f72a2ce6f5830aa8c41f3b64ea4cb70e2912c",
    "mom_breadth_crossasset_trend_r1": (
        "701964873a4ae7039970c82e48c2523e8468959d90c2d5098374bdccbd2018ff"
    ),
    "mom_breadth_short_reversal_r1": (
        "c7591ad246c7a0f447a9b2f0a4d2ff112aa0b0e1f2b6724af65495d4a9e79484"
    ),
    "mom_breadth_cross_session_r1": (
        "719e9b6f4bde5f2010e0612d824e51b73a8d8e0435dc72b2a07af9289114b652"
    ),
    "mom_breadth_volatility_beta_r1": (
        "25cefee4fd02d5e13da4a763063fcedc545498272e4555f7bc438b0b23f130af"
    ),
    "mom_breadth_calendar_flow_r1": (
        "672d197a9090b60242eb2772029ccebdc2993240773530d3298b14beb4192731"
    ),
    "mom_breadth_static_hotspot_control_r1": (
        "8cdce4a40ff07dda2706120581818c21bca4c6918dc1cf960acd3a1e444e5981"
    ),
}
RECOVERY_IMPLEMENTATION_DRIFT_BLOCKERS = (
    "candidate_manifest_phase_one_lock_development_runner_sha256_mismatch",
    "candidate_manifest_phase_one_lock_development_runner_tests_sha256_mismatch",
)
RECOVERY_AUTHORIZED_CHANGES = (
    "repair_QD_archive_and_allocation_ledger_serialization_with_model_dump",
    "add_explicit_retry_safe_receipt_last_staged_publication_recovery",
    "harden_recovery_validation_and_tests_without_recomputing_research_results",
)
RECOVERY_FORBIDDEN_CHANGES = (
    "candidate_generation_or_policy_mutation",
    "market_data_read_or_return_recomputation",
    "candidate_simulation_or_new_trial_exposure",
    "model_training_or_inference",
    "frozen_OOS_challenge_or_forward_read",
    "staged_evidence_or_preregistration_mutation",
    "simulation_paper_or_broker_activity",
)
RECOVERY_AMENDMENT_REASON = (
    "Repair the failed reserved attempt's publication path without recalculating or changing "
    "any research result."
)

# Second, separate amendment: this campaign is permanently sealed with a
# preserved negative development result (0 advancing candidates; see
# docs/plan-gate-recalibration-and-research-velocity-2026-08-26.zh.md). It
# will never be reopened, resimulated, or read against frozen OOS/challenge/
# forward data under any circumstance. That makes it safe -- and, since its
# own frozen implementation files are shared modules used by all campaigns
# going forward, necessary -- to acknowledge the one-time, deliberately
# authorized recalibration of the shared gate/promotion-policy implementation
# below. Unlike the first amendment, this one *is* a policy change; it is
# authorized explicitly because it changes the rules for future campaigns,
# not because it revisits this campaign's already-sealed result.
GATE_RECALIBRATION_DRIFT_BLOCKERS = (
    "candidate_manifest_phase_one_lock_campaign_implementation_sha256_mismatch",
)
GATE_RECALIBRATION_AUTHORIZED_CHANGES = (
    "recalibrate_family_scoped_dsr_trial_count_and_promotion_gate_thresholds",
    "replace_absolute_cagr_and_tqqq_capture_gates_with_qqq_relative_equivalents",
    "split_paper_entry_and_live_entry_promotion_gate_tiers",
)
GATE_RECALIBRATION_FORBIDDEN_CHANGES = (
    "reopening_this_sealed_campaigns_development_result",
    "candidate_simulation_or_new_trial_exposure_for_this_campaign",
    "model_training_or_inference_for_this_campaign",
    "frozen_OOS_challenge_or_forward_read_for_this_campaign",
    "staged_evidence_or_preregistration_mutation_for_this_campaign",
    "simulation_paper_or_broker_activity_for_this_campaign",
)
GATE_RECALIBRATION_REASON = (
    "Recalibrate the shared campaign gate/promotion-policy implementation and this "
    "already-dead campaign's own recorded policy so both stay loadable and internally "
    "consistent under the new methodology, without reopening or resimulating this "
    "campaign's sealed, negative development result."
)


@dataclass(frozen=True)
class PricePanel:
    opens: pd.DataFrame
    closes: pd.DataFrame
    volumes: pd.DataFrame

    @property
    def index(self) -> pd.DatetimeIndex:
        return pd.DatetimeIndex(self.opens.index)

    @property
    def symbols(self) -> tuple[str, ...]:
        return tuple(str(column) for column in self.opens.columns)


@dataclass(frozen=True)
class SimulationResult:
    returns: pd.Series
    turnover: pd.Series
    signal_rows: tuple[dict[str, Any], ...]


@dataclass(frozen=True)
class CandidateDevelopmentResult:
    candidate_id: str
    iter_id: str
    spec_path: str
    promotion_eligible: bool
    quality: float
    quality_metric: str
    returns_by_cost: dict[int, pd.Series]
    metrics: dict[str, Any]
    metrics_path: str
    metrics_sha256: str
    signal_log_path: str


@dataclass(frozen=True)
class BenchmarkFamilyResult:
    returns_by_cost: dict[int, dict[str, pd.Series]]
    roles: dict[str, str]
    initialization_session_by_stream: dict[str, str]
    initial_one_way_turnover: float
    initial_wealth_by_cost: dict[int, float]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_json(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _canonical_sha256(payload: Any) -> str:
    return hashlib.sha256(_canonical_json(payload).encode("ascii")).hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON artifact must be an object: {path}")
    return payload


def _exclusive_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True) + "\n"
    with path.open("x", encoding="ascii") as handle:
        handle.write(serialized)


def _development_effective_trial_count(
    contract: ResearchCampaignContract,
    *,
    evaluated_candidate_count: int,
) -> int:
    if evaluated_candidate_count < 0:
        raise ValueError("evaluated candidate count must be nonnegative")
    budgets = contract.exposure_budgets
    actual_exposure = evaluated_candidate_count * len(COST_VIEWS)
    incremental = max(budgets.candidate_budget, actual_exposure)
    if incremental > budgets.cumulative_trial_exposure_budget:
        raise ValueError("development effective trial exposure exceeds campaign budget")
    return budgets.prior_effective_trial_count + incremental


def _verify_ledger_effective_trial_count(
    contract: ResearchCampaignContract,
    ledger: Any,
    *,
    precomputed_effective_trial_count: int,
) -> int:
    actual = effective_trial_count_from_ledger(contract, ledger)
    if (
        precomputed_effective_trial_count != EXPECTED_DEVELOPMENT_EFFECTIVE_TRIAL_COUNT
        or actual != EXPECTED_DEVELOPMENT_EFFECTIVE_TRIAL_COUNT
        or actual != precomputed_effective_trial_count
    ):
        raise ValueError("development allocation-ledger effective trial count must equal 8195")
    return actual


def _verify_runtime_lock_inventory(
    root: Path,
    contract: ResearchCampaignContract,
) -> dict[str, dict[str, str]]:
    bindings: dict[str, dict[str, str]] = {}
    for iter_id in contract.child_iteration_ids:
        path = root / ITERATION_ROOT / iter_id / "phase-one-preregistration-lock.json"
        lock = _read_json(path)
        expected_candidate_ids = [
            row.candidate_id
            for row in contract.candidate_blueprints
            if row.child_iteration_id == iter_id
        ]
        if (
            lock.get("lock_type") != "breadth_campaign_phase_one_preregistration_v1"
            or lock.get("campaign_id") != CAMPAIGN_ID
            or lock.get("iter_id") != iter_id
            or lock.get("generated_before_backtest") is not True
            or lock.get("generated_before_model_training") is not True
            or lock.get("frozen_oos_read_authorized") is not False
            or lock.get("broker_writes") is not False
            or lock.get("candidate_ids") != expected_candidate_ids
        ):
            raise ValueError(f"phase-one lock identity mismatch: {iter_id}")
        policy_hashes = lock.get("candidate_policy_sha256")
        if not isinstance(policy_hashes, dict) or set(policy_hashes) != set(expected_candidate_ids):
            raise ValueError(f"phase-one candidate policy inventory mismatch: {iter_id}")
        inventory = lock.get("immutable_inventory")
        if not isinstance(inventory, dict) or not inventory:
            raise ValueError(f"phase-one immutable inventory is malformed: {iter_id}")
        for name, binding in inventory.items():
            if not isinstance(binding, dict):
                raise ValueError(f"phase-one immutable binding is malformed: {iter_id}:{name}")
            _verify_binding(root, binding)
        required_paths = {
            **LOCKED_IMPLEMENTATION_PATHS,
            "development_integrity_amendment": INTEGRITY_AMENDMENT_PATH,
            "exchange_calendar_artifact": EXCHANGE_CALENDAR_PATH,
        }
        for name, expected_path in required_paths.items():
            binding = inventory.get(name)
            if not isinstance(binding, dict) or binding.get("path") != expected_path.as_posix():
                raise ValueError(f"phase-one required binding mismatch: {iter_id}:{name}")
        bindings[iter_id] = {
            "path": path.relative_to(root).as_posix(),
            "sha256": _sha256(path),
        }
    return bindings


def _load_development_session_calendar(
    root: Path,
    binding: Mapping[str, Any],
) -> pd.DatetimeIndex:
    if binding.get("path") != EXCHANGE_CALENDAR_PATH.as_posix():
        raise ValueError("exchange calendar binding path mismatch")
    path = _verify_binding(root, binding)
    payload = _read_json(path)
    sessions = payload.get("sessions")
    if (
        not isinstance(sessions, list)
        or not sessions
        or not all(isinstance(value, str) for value in sessions)
    ):
        raise ValueError("exchange calendar sessions are malformed")
    try:
        parsed = tuple(date.fromisoformat(value) for value in sessions)
    except ValueError as exc:
        raise ValueError("exchange calendar sessions are malformed") from exc
    expected = us_equity_session_dates(DEVELOPMENT_START, VALIDATION_END)
    if parsed != expected:
        raise ValueError("exchange calendar sessions differ from locked ruleset")
    if (
        payload.get("schema_version") != 1
        or payload.get("artifact_type") != "us_equity_daily_session_calendar_v1"
        or payload.get("campaign_id") != CAMPAIGN_ID
        or payload.get("calendar_id") != "XNYS"
        or payload.get("timezone") != "America/New_York"
        or payload.get("session_label") != "exchange_local_date"
        or payload.get("session_scope") != "regular"
        or payload.get("ruleset_id") != "open_composer_us_equity_calendar_v1"
        or payload.get("ruleset_implementation_path") != "open_composer/market_calendar.py"
        or payload.get("ruleset_implementation_sha256")
        != _sha256(root / "open_composer/market_calendar.py")
        or payload.get("requested_start") != DEVELOPMENT_START.isoformat()
        or payload.get("requested_end") != VALIDATION_END.isoformat()
        or payload.get("first_session") != sessions[0]
        or payload.get("last_session") != sessions[-1]
        or payload.get("session_count") != len(sessions)
        or payload.get("sessions_sha256") != _canonical_sha256(sessions)
        or payload.get("derived_from_price_data") is not False
        or payload.get("protected_partitions_included") is not False
        or payload.get("source_card_claim_id") != "breadth_qd_nyse_session_calendar"
    ):
        raise ValueError("exchange calendar artifact identity mismatch")
    return pd.DatetimeIndex(sessions)


def _verify_feasibility_references(
    root: Path,
    *,
    iter_id: str,
    feasibility: Mapping[str, Any],
    phase_one_lock: Mapping[str, str],
    expected_references: Mapping[str, Mapping[str, str]] | None = None,
) -> None:
    references = feasibility.get("required_references")
    names = feasibility.get("required_reference_names")
    if not isinstance(references, dict) or not references or names != sorted(references):
        raise ValueError(f"data-feasibility reference inventory mismatch: {iter_id}")
    if expected_references is not None and references != {
        name: dict(binding) for name, binding in expected_references.items()
    }:
        raise ValueError(f"data-feasibility exact reference inventory mismatch: {iter_id}")
    for name, binding in references.items():
        if not isinstance(binding, dict):
            raise ValueError(f"data-feasibility binding is malformed: {iter_id}:{name}")
        _verify_binding(root, binding)
    if references.get("phase_one_preregistration_lock") != dict(phase_one_lock):
        raise ValueError(f"data-feasibility phase-one lock identity mismatch: {iter_id}")


def _expected_feasibility_references(
    root: Path,
    *,
    iteration: Path,
    immutable_inventory: Mapping[str, Any],
    phase_one_lock: Mapping[str, str],
) -> dict[str, dict[str, str]]:
    references: dict[str, dict[str, str]] = {}
    for reference_name, inventory_name in FEASIBILITY_REFERENCE_LOCK_KEYS.items():
        binding = immutable_inventory.get(inventory_name)
        if not isinstance(binding, dict):
            raise ValueError(
                f"development recovery immutable feasibility reference missing: {reference_name}"
            )
        _verify_binding(root, binding)
        references[reference_name] = dict(binding)
    for reference_name, filename in {
        "knowledge_assessment": "knowledge-assessment.json",
        "knowledge_context": "knowledge-context.json",
        "knowledge_scout": "knowledge-scout.json",
        "model_reuse_decision": "model-reuse-decision.json",
    }.items():
        path = iteration / filename
        if path.is_symlink() or not path.is_file():
            raise FileNotFoundError(path)
        references[reference_name] = {
            "path": path.relative_to(root).as_posix(),
            "sha256": _sha256(path),
        }
    references["phase_one_preregistration_lock"] = dict(phase_one_lock)
    expected_names = set(FEASIBILITY_REFERENCE_LOCK_KEYS) | {
        "knowledge_assessment",
        "knowledge_context",
        "knowledge_scout",
        "model_reuse_decision",
        "phase_one_preregistration_lock",
    }
    if set(references) != expected_names or len(references) != 25:
        raise ValueError("development recovery expected feasibility inventory is invalid")
    return {name: references[name] for name in sorted(references)}


def _validate_dependency_skipped_iteration_gate(iter_id: str, root: Path) -> None:
    validation = validate_iteration_dossier(iter_id, root, stage="pre-backtest")
    expected = ["search_space_data_feasibility_not_authorized"]
    if validation.status != "blocked" or validation.blocked != expected:
        raise ValueError(
            f"dependency-skipped iteration has unexpected blockers: {iter_id}:{validation.blocked}"
        )


def _validate_recovery_iteration_dossier_gate(
    iter_id: str,
    root: Path,
    *,
    dependency_skipped: bool,
) -> None:
    """Allow only the implementation drift authorized by the recovery amendment."""
    validation = validate_iteration_dossier(iter_id, root, stage="pre-backtest")
    # Phase-one-lock mismatch codes sort alphabetically within
    # ``validation.blocked`` (they come from one sub-validator iterating the
    # lock's immutable inventory in key order); sort the authorized union to
    # match regardless of which specific files drifted under which amendment.
    expected = [
        *sorted({*RECOVERY_IMPLEMENTATION_DRIFT_BLOCKERS, *GATE_RECALIBRATION_DRIFT_BLOCKERS}),
        *(["search_space_data_feasibility_not_authorized"] if dependency_skipped else []),
    ]
    if validation.status != "blocked" or validation.blocked != expected or validation.warnings:
        raise ValueError(
            "development recovery iteration has unexpected dossier findings: "
            f"{iter_id}:{validation.blocked}:{validation.warnings}"
        )


def _validate_iteration_contract_identities(
    *,
    iter_id: str,
    label_contract: Mapping[str, Any],
    cost_contract: Mapping[str, Any],
    benchmark_contract: Mapping[str, Any],
    expected_symbols: tuple[str, ...],
) -> None:
    expected_cost_views = [
        {"name": "low", "one_way_bps": 10},
        {"name": "primary", "one_way_bps": 20},
        {"name": "severe", "one_way_bps": 40},
    ]
    if (
        label_contract.get("portfolio_return") != PORTFOLIO_RETURN_IDENTITY
        or label_contract.get("terminal_liquidation_included") is not False
        or label_contract.get("model_training") is not False
    ):
        raise ValueError(f"label contract return identity mismatch: {iter_id}")
    if (
        cost_contract.get("cost_views") != expected_cost_views
        or cost_contract.get("primary_one_way_bps") != PRIMARY_COST_BPS
        or cost_contract.get("cost_applied_to") != "one_way_notional_turnover_at_next_regular_open"
        or cost_contract.get("terminal_rejoin_cost_included") is not False
    ):
        raise ValueError(f"cost contract identity mismatch: {iter_id}")
    if (
        benchmark_contract.get("required") != list(BENCHMARK_FAMILY_IDS)
        or benchmark_contract.get("same_sessions") is not True
        or benchmark_contract.get("same_cost_views") is not True
        or benchmark_contract.get("cost_views_bps") != list(COST_VIEWS)
        or benchmark_contract.get("primary_one_way_bps") != PRIMARY_COST_BPS
        or benchmark_contract.get("cost_applied_to")
        != "initial_notional_at_first_available_development_open"
        or benchmark_contract.get("initialization_precedes_validation") is not True
        or benchmark_contract.get("allocation") != BENCHMARK_ALLOCATION_IDENTITY
        or benchmark_contract.get("terminal_liquidation_included") is not False
        or benchmark_contract.get("validation_return_cost_note")
        != "initialization_cost_precedes_validation_so_validation_daily_returns_are_cost_invariant"
        or benchmark_contract.get("equal_weight_symbols") != list(expected_symbols)
        or benchmark_contract.get("ex_post_best_symbols") != list(expected_symbols)
        or benchmark_contract.get("ex_post_best_symbol_selectable") is not False
        or benchmark_contract.get("cash_proxy_symbol") != "BIL"
        or benchmark_contract.get("market_proxy_symbol") != "SPY"
        or benchmark_contract.get("growth_proxy_symbol") != "QQQ"
        or benchmark_contract.get("sector_theme_proxy_symbol") != "XLK"
        or benchmark_contract.get("leveraged_growth_proxy_symbol") != "TQQQ"
    ):
        raise ValueError(f"benchmark contract identity mismatch: {iter_id}")


def _assert_pristine_publication_state(
    root: Path,
    contract: ResearchCampaignContract,
) -> None:
    occupied = [
        root / DEVELOPMENT_ATTEMPT_PATH,
        root / CAMPAIGN_ROOT / "qd-archive.json",
        root / CAMPAIGN_ROOT / "allocation-ledger.jsonl",
        root / CAMPAIGN_ROOT / "development-evaluation-report.json",
        root / DEVELOPMENT_RECEIPT_PATH,
    ]
    occupied.extend(
        root / ITERATION_ROOT / iter_id / "evaluation-run"
        for iter_id in contract.child_iteration_ids
    )
    occupied.extend((root / CAMPAIGN_ROOT).glob("development-evaluation.staging-*"))
    for iter_id in contract.child_iteration_ids:
        occupied.extend((root / ITERATION_ROOT / iter_id).glob("evaluation-run.staging-*"))
    existing = sorted(path.relative_to(root).as_posix() for path in occupied if path.exists())
    if existing:
        raise FileExistsError(
            "development campaign is one-shot and state already exists: " + ", ".join(existing)
        )


def _reserve_development_attempt(
    root: Path,
    *,
    contract: ResearchCampaignContract,
    campaign_contract_sha256: str,
    phase_one_locks: Mapping[str, Mapping[str, str]],
    evaluated_candidate_count: int,
    effective_trial_count: int,
    run_token: str,
) -> dict[str, str]:
    path = root / DEVELOPMENT_ATTEMPT_PATH
    payload = {
        "schema_version": 1,
        "campaign_id": CAMPAIGN_ID,
        "reserved_at": datetime.now(UTC).isoformat(),
        "status": "reserved_before_development_market_data_read",
        "one_shot": True,
        "run_token": run_token,
        "campaign_contract_sha256": campaign_contract_sha256,
        "phase_one_locks": dict(phase_one_locks),
        "implementation": {
            name: {"path": path.as_posix(), "sha256": _sha256(root / path)}
            for name, path in LOCKED_IMPLEMENTATION_PATHS.items()
        },
        "registered_candidate_count": contract.exposure_budgets.candidate_budget,
        "evaluated_candidate_count": evaluated_candidate_count,
        "cost_views_bps": list(COST_VIEWS),
        "incremental_effective_trial_count": effective_trial_count
        - contract.exposure_budgets.prior_effective_trial_count,
        "effective_trial_count": effective_trial_count,
        "frozen_oos_rows_read": 0,
        "frozen_oos_read_authorized": False,
        "model_training_count": 0,
        "broker_writes": False,
    }
    _exclusive_write_json(path, payload)
    return {"path": DEVELOPMENT_ATTEMPT_PATH.as_posix(), "sha256": _sha256(path)}


def _staged_publication_binding(
    staged_path: Path,
    *,
    destination_path: Path,
    root: Path,
) -> dict[str, str]:
    return {
        "path": destination_path.relative_to(root).as_posix(),
        "sha256": _sha256(staged_path),
    }


def _publish_staged_outputs(
    *,
    root: Path,
    branch_staging: Mapping[str, Path],
    campaign_staging: Path,
    publication_files: list[Mapping[str, Any]] | None = None,
) -> None:
    branch_destinations = {
        iter_id: root / ITERATION_ROOT / iter_id / "evaluation-run" for iter_id in branch_staging
    }
    campaign_names = (
        "qd-archive.json",
        "allocation-ledger.jsonl",
        "development-evaluation-report.json",
    )
    for iter_id, source in sorted(branch_staging.items()):
        destination = branch_destinations[iter_id]
        if source == destination:
            if source.is_symlink() or not source.is_dir():
                raise ValueError(f"development publication branch is invalid: {iter_id}")
            continue
        if source.exists():
            if source.is_symlink() or not source.is_dir() or destination.exists():
                raise FileExistsError(f"development publication branch collision: {iter_id}")
            _move_publication_path(source, destination)
        elif destination.is_symlink() or not destination.is_dir():
            raise FileNotFoundError(f"development publication branch is missing: {iter_id}")
    for name in campaign_names:
        source = campaign_staging / name
        destination = root / CAMPAIGN_ROOT / name
        if source.exists():
            if source.is_symlink() or not source.is_file() or destination.exists():
                raise FileExistsError(f"development campaign publication collision: {name}")
            _move_publication_path(source, destination)
        elif destination.is_symlink() or not destination.is_file():
            raise FileNotFoundError(f"development campaign publication is missing: {name}")
    if publication_files is not None:
        for binding in publication_files:
            _verify_binding(root, binding)

    receipt_source = campaign_staging / DEVELOPMENT_RECEIPT_PATH.name
    receipt_destination = root / DEVELOPMENT_RECEIPT_PATH
    if receipt_source.exists():
        if (
            receipt_source.is_symlink()
            or not receipt_source.is_file()
            or receipt_destination.exists()
        ):
            raise FileExistsError("development publication receipt collision")
        _move_publication_path(receipt_source, receipt_destination)
    elif receipt_destination.is_symlink() or not receipt_destination.is_file():
        raise FileNotFoundError("development publication receipt is missing")
    if campaign_staging.exists():
        if campaign_staging.is_symlink() or any(campaign_staging.iterdir()):
            raise ValueError("development campaign staging has unexpected residual files")
        campaign_staging.rmdir()


def _move_publication_path(source: Path, destination: Path) -> None:
    """Move one fully validated publication artifact into canonical custody."""
    source.replace(destination)


def _verify_binding(root: Path, binding: Mapping[str, Any]) -> Path:
    raw = Path(str(binding.get("path") or ""))
    if raw.is_absolute() or ".." in raw.parts:
        raise ValueError(f"artifact path must be repository relative: {raw}")
    path = root / raw
    if not path.is_file() or path.is_symlink():
        raise FileNotFoundError(path)
    expected = str(binding.get("sha256") or "")
    if _sha256(path) != expected:
        raise ValueError(f"artifact SHA-256 mismatch: {raw}")
    return path


def _read_price_csv_until(
    path: Path,
    *,
    end: date,
    start: date = DEVELOPMENT_START,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    end_session_found = False
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {"timestamp", "open", "close", "volume"}
        if reader.fieldnames is None or not required.issubset(reader.fieldnames):
            raise ValueError(f"price CSV schema mismatch: {path}")
        for row in reader:
            timestamp = pd.Timestamp(str(row["timestamp"]))
            session = timestamp.date()
            if session > end:
                raise ValueError(f"price CSV is missing the declared development end: {path}")
            if session < start:
                continue
            rows.append(
                {
                    "session": pd.Timestamp(session),
                    "open": float(row["open"]),
                    "close": float(row["close"]),
                    "volume": float(row["volume"]),
                }
            )
            if session == end:
                end_session_found = True
                break
    if not end_session_found:
        raise ValueError(f"price CSV is missing the declared development end: {path}")
    frame = pd.DataFrame(rows)
    if frame.empty:
        raise ValueError(f"price CSV has no development rows: {path}")
    frame = frame.set_index("session").sort_index()
    if frame.index.has_duplicates:
        raise ValueError(f"price CSV has duplicate sessions: {path}")
    if frame.index[0].date() != start or frame.index[-1].date() != end:
        raise ValueError(f"price CSV does not match declared development bounds: {path}")
    values = frame[["open", "close", "volume"]].to_numpy(dtype=float)
    if not np.isfinite(values).all() or (frame[["open", "close"]] <= 0.0).any().any():
        raise ValueError(f"price CSV contains invalid development values: {path}")
    return frame


def _panel_from_symbol_frames(
    frames: Mapping[str, pd.DataFrame],
    *,
    start: date,
    end: date,
    expected_sessions: pd.DatetimeIndex,
) -> PricePanel:
    if not frames:
        raise ValueError("price panel requires at least one symbol")
    expected = pd.DatetimeIndex(expected_sessions)
    if (
        expected.empty
        or expected.has_duplicates
        or not expected.is_monotonic_increasing
        or expected[0].date() != start
        or expected[-1].date() != end
    ):
        raise ValueError("locked exchange sessions do not match panel bounds")
    for symbol, frame in frames.items():
        index = pd.DatetimeIndex(frame.index)
        if not index.equals(expected):
            missing = expected.difference(index)
            extra = index.difference(expected)
            raise ValueError(
                "price panel does not exactly cover locked exchange sessions: "
                f"{symbol}:missing={len(missing)}:extra={len(extra)}"
            )
    ordered = sorted(frames)
    opens = pd.DataFrame({symbol: frames[symbol].loc[expected, "open"] for symbol in ordered})
    closes = pd.DataFrame({symbol: frames[symbol].loc[expected, "close"] for symbol in ordered})
    volumes = pd.DataFrame({symbol: frames[symbol].loc[expected, "volume"] for symbol in ordered})
    return PricePanel(opens=opens, closes=closes, volumes=volumes)


def _snapshot_items_by_symbol(manifest: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    selected: dict[str, Mapping[str, Any]] = {}
    items = manifest.get("items")
    if not isinstance(items, list):
        raise ValueError("snapshot manifest items are missing")
    for item in items:
        if not isinstance(item, dict) or item.get("adjustment") != "all":
            continue
        symbol = str(item.get("symbol") or "").upper()
        if not symbol:
            continue
        if symbol in selected:
            raise ValueError(f"snapshot has duplicate all-adjusted item: {symbol}")
        selected[symbol] = item
    return selected


def _load_snapshot_panel(
    root: Path,
    manifest_path: Path,
    symbols: tuple[str, ...],
    *,
    start: date,
    expected_sessions: pd.DatetimeIndex,
) -> PricePanel:
    manifest = _read_json(manifest_path)
    if (
        manifest.get("manifest_type") != "development_partition_snapshot_v1"
        or manifest.get("campaign_id") != CAMPAIGN_ID
        or manifest.get("first_session") != start.isoformat()
        or manifest.get("last_session") != VALIDATION_END.isoformat()
        or manifest.get("protected_partitions_included") is not False
        or manifest.get("future_source_metadata_included") is not False
    ):
        raise ValueError(f"snapshot is not development-only: {manifest_path}")
    items = _snapshot_items_by_symbol(manifest)
    frames: dict[str, pd.DataFrame] = {}
    for symbol in symbols:
        item = items.get(symbol)
        if item is None:
            raise ValueError(f"snapshot is missing all-adjusted symbol: {symbol}")
        output = Path(str(item.get("output_path") or ""))
        if output.is_absolute() or ".." in output.parts:
            raise ValueError(f"snapshot output path is invalid: {output}")
        path = manifest_path.parent / output
        if not path.is_file() or path.is_symlink():
            raise FileNotFoundError(path)
        expected = str(item.get("output_sha256") or "")
        if _sha256(path) != expected:
            raise ValueError(f"snapshot output SHA-256 mismatch: {symbol}")
        if (
            str(item.get("first_timestamp") or "")[:10] != start.isoformat()
            or str(item.get("last_timestamp") or "")[:10] != VALIDATION_END.isoformat()
        ):
            raise ValueError(f"snapshot item bounds mismatch: {symbol}")
        frames[symbol] = _read_price_csv_until(path, start=start, end=VALIDATION_END)
    return _panel_from_symbol_frames(
        frames,
        start=start,
        end=VALIDATION_END,
        expected_sessions=expected_sessions,
    )


def _load_static_panel(
    root: Path,
    data_contract: Mapping[str, Any],
    symbols: tuple[str, ...],
    *,
    start: date,
    expected_sessions: pd.DatetimeIndex,
) -> PricePanel:
    bindings = data_contract.get("artifacts")
    if not isinstance(bindings, list):
        raise ValueError("static data contract artifacts are missing")
    by_symbol: dict[str, Mapping[str, Any]] = {}
    for binding in bindings:
        if not isinstance(binding, dict):
            continue
        stem = Path(str(binding.get("path") or "")).name.split("_", maxsplit=1)[0].upper()
        by_symbol[stem] = binding
    frames: dict[str, pd.DataFrame] = {}
    for symbol in symbols:
        binding = by_symbol.get(symbol)
        if binding is None:
            raise ValueError(f"static data contract is missing symbol: {symbol}")
        frames[symbol] = _read_price_csv_until(
            _verify_binding(root, binding),
            start=start,
            end=VALIDATION_END,
        )
    return _panel_from_symbol_frames(
        frames,
        start=start,
        end=VALIDATION_END,
        expected_sessions=expected_sessions,
    )


def _load_branch_panel(
    root: Path,
    *,
    iter_id: str,
    spec_path: Path,
    exchange_sessions: pd.DatetimeIndex,
) -> PricePanel:
    spec = load_strategy_spec(root / spec_path)
    symbols = tuple(str(symbol).upper() for symbol in spec.universe)
    data_contract = _read_json(root / ITERATION_ROOT / iter_id / "data-contract.json")
    start = date.fromisoformat(str(data_contract.get("first_session") or ""))
    expected_sessions = exchange_sessions[exchange_sessions >= pd.Timestamp(start)]
    artifact_bindings = data_contract.get("artifacts")
    if not isinstance(artifact_bindings, list) or not artifact_bindings:
        raise ValueError(f"data contract artifacts are missing: {iter_id}")
    data_path = Path(str(spec.data.path))
    matching = [row for row in artifact_bindings if row.get("path") == data_path.as_posix()]
    if data_path.suffix == ".json":
        if len(matching) != 1:
            raise ValueError(f"spec data artifact binding mismatch: {iter_id}")
        manifest_path = _verify_binding(root, matching[0])
        return _load_snapshot_panel(
            root,
            manifest_path,
            symbols,
            start=start,
            expected_sessions=expected_sessions,
        )
    return _load_static_panel(
        root,
        data_contract,
        symbols,
        start=start,
        expected_sessions=expected_sessions,
    )


def _load_benchmark_panel(
    root: Path,
    contract: Mapping[str, Any],
    *,
    exchange_sessions: pd.DatetimeIndex,
) -> PricePanel:
    expected: Mapping[str, Any] | None = None
    for iter_id in contract.get("child_iteration_ids", []):
        data_contract = _read_json(root / ITERATION_ROOT / iter_id / "data-contract.json")
        rows = data_contract.get("promotion_benchmark_artifacts")
        if not isinstance(rows, list):
            raise ValueError(f"promotion benchmark bindings are missing: {iter_id}")
        matches = [row for row in rows if row.get("path") == BENCHMARK_SNAPSHOT.as_posix()]
        if len(matches) != 1:
            raise ValueError(f"promotion benchmark snapshot binding mismatch: {iter_id}")
        if expected is None:
            expected = matches[0]
        elif expected != matches[0]:
            raise ValueError("promotion benchmark bindings differ across child iterations")
    if expected is None:
        raise ValueError("campaign has no promotion benchmark binding")
    path = _verify_binding(root, expected)
    return _load_snapshot_panel(
        root,
        path,
        BENCHMARK_SYMBOLS,
        start=DEVELOPMENT_START,
        expected_sessions=exchange_sessions,
    )


def _rsi(values: pd.DataFrame, window: int) -> pd.DataFrame:
    delta = values.diff()
    gains = delta.clip(lower=0.0)
    losses = -delta.clip(upper=0.0)
    average_gain = gains.ewm(alpha=1.0 / window, adjust=False, min_periods=window).mean()
    average_loss = losses.ewm(alpha=1.0 / window, adjust=False, min_periods=window).mean()
    relative_strength = average_gain / average_loss.replace(0.0, np.nan)
    result = 100.0 - 100.0 / (1.0 + relative_strength)
    return result.where(average_loss > 0.0, 100.0)


def _features(panel: PricePanel) -> dict[str, pd.DataFrame]:
    close = panel.closes
    close_return = close.pct_change()
    return {
        "trend_20": close / close.shift(20) - 1.0,
        "trend_63": close / close.shift(63) - 1.0,
        "trend_126": close / close.shift(126) - 1.0,
        "trend_252": close / close.shift(252) - 1.0,
        "return_5": close / close.shift(5) - 1.0,
        "trend_gap_200": close / close.rolling(200, min_periods=200).mean() - 1.0,
        "realized_volatility_20": close_return.rolling(20, min_periods=20).std(ddof=1),
        "realized_volatility_63": close_return.rolling(63, min_periods=63).std(ddof=1),
        "breakout_high_55": close.rolling(55, min_periods=55).max(),
        "exit_low_20": close.rolling(20, min_periods=20).min(),
        "drawdown_63": close / close.rolling(63, min_periods=63).max() - 1.0,
        "overnight_return": panel.opens / close.shift(1) - 1.0,
        "intraday_return": close / panel.opens - 1.0,
        "volume_ratio_20": panel.volumes / panel.volumes.rolling(20, min_periods=20).mean(),
        "volume_shock_20": panel.volumes / panel.volumes.rolling(20, min_periods=20).mean() - 1.0,
        "rsi_7": _rsi(close, 7),
        "momentum_252_skip21": close.shift(21) / close.shift(252) - 1.0,
    }


def _fallback() -> dict[str, float]:
    return {"BIL": 1.0}


def _validate_weights(weights: Mapping[str, float], symbols: tuple[str, ...]) -> None:
    if not weights:
        raise ValueError("target weights are empty")
    if set(weights) - set(symbols):
        raise ValueError("target weights reference symbols outside the panel")
    values = np.asarray(list(weights.values()), dtype=float)
    if not np.isfinite(values).all() or np.any(values < 0.0):
        raise ValueError("target weights must be finite and nonnegative")
    if not math.isclose(float(values.sum()), 1.0, rel_tol=0.0, abs_tol=1e-12):
        raise ValueError("target weights must sum to one")


def _equal_weight(selected: list[str], *, max_weight: float) -> dict[str, float]:
    if not selected:
        return _fallback()
    ordered = sorted(set(selected))
    weight = min(1.0 / len(ordered), max_weight)
    result = {symbol: weight for symbol in ordered}
    residual = 1.0 - weight * len(ordered)
    if residual > 1e-15:
        result["BIL"] = residual
    return result


def _inverse_volatility_weight(
    volatility: pd.Series,
    selected: list[str],
    *,
    max_weight: float,
) -> dict[str, float]:
    usable = [
        symbol
        for symbol in sorted(set(selected))
        if symbol in volatility.index
        and math.isfinite(float(volatility[symbol]))
        and float(volatility[symbol]) > 0.0
    ]
    if not usable:
        return _fallback()
    raw = {symbol: 1.0 / float(volatility[symbol]) for symbol in usable}
    remaining = 1.0
    active = set(usable)
    result: dict[str, float] = {}
    while active and remaining > 1e-15:
        denominator = math.fsum(raw[symbol] for symbol in active)
        proposed = {symbol: remaining * raw[symbol] / denominator for symbol in sorted(active)}
        capped = [symbol for symbol, weight in proposed.items() if weight > max_weight]
        if not capped:
            result.update(proposed)
            remaining = 0.0
            break
        for symbol in capped:
            result[symbol] = max_weight
            remaining -= max_weight
            active.remove(symbol)
    if remaining > 1e-15:
        result["BIL"] = result.get("BIL", 0.0) + remaining
    return result


def _is_week_end(decision: pd.Timestamp, execution: pd.Timestamp) -> bool:
    return tuple(decision.isocalendar()[:2]) != tuple(execution.isocalendar()[:2])


def _is_month_end(decision: pd.Timestamp, execution: pd.Timestamp) -> bool:
    return (decision.year, decision.month) != (execution.year, execution.month)


def _calendar_window_active(
    sessions: pd.DatetimeIndex,
    position: int,
    parameters: Mapping[str, Any],
) -> bool:
    session = sessions[position]
    same_month = [
        idx
        for idx, value in enumerate(sessions)
        if value.year == session.year and value.month == session.month
    ]
    month_position = same_month.index(position)
    month_from_end = len(same_month) - month_position
    offsets = parameters.get("relative_month_session_offsets")
    if isinstance(offsets, list):
        relative = -1 if month_from_end == 1 else month_position
        return relative in {int(value) for value in offsets}
    if "last_sessions_of_month" in parameters:
        return month_from_end <= int(parameters["last_sessions_of_month"])
    quarter = (session.month - 1) // 3 + 1
    same_quarter = [
        idx
        for idx, value in enumerate(sessions)
        if value.year == session.year and (value.month - 1) // 3 + 1 == quarter
    ]
    quarter_position = same_quarter.index(position)
    quarter_from_end = len(same_quarter) - quarter_position
    return quarter_from_end <= int(parameters["last_sessions_of_quarter"]) or (
        quarter_position < int(parameters["first_sessions_of_quarter"])
    )


def _calendar_active_sessions(
    sessions: pd.DatetimeIndex,
    parameters: Mapping[str, Any],
) -> set[pd.Timestamp]:
    month_groups: dict[tuple[int, int], list[pd.Timestamp]] = {}
    quarter_groups: dict[tuple[int, int], list[pd.Timestamp]] = {}
    for session in sessions:
        month_groups.setdefault((session.year, session.month), []).append(session)
        quarter_groups.setdefault((session.year, (session.month - 1) // 3 + 1), []).append(session)
    active: set[pd.Timestamp] = set()
    offsets = parameters.get("relative_month_session_offsets")
    if isinstance(offsets, list):
        wanted = {int(value) for value in offsets}
        for values in month_groups.values():
            for position, session in enumerate(values):
                relative = -1 if position == len(values) - 1 else position
                if relative in wanted:
                    active.add(session)
        return active
    if "last_sessions_of_month" in parameters:
        count = int(parameters["last_sessions_of_month"])
        for values in month_groups.values():
            active.update(values[-count:])
        return active
    first = int(parameters["first_sessions_of_quarter"])
    last = int(parameters["last_sessions_of_quarter"])
    for values in quarter_groups.values():
        active.update(values[:first])
        active.update(values[-last:])
    return active


def build_target_schedule(
    policy: Mapping[str, Any],
    panel: PricePanel,
    *,
    exchange_sessions: pd.DatetimeIndex,
) -> dict[pd.Timestamp, dict[str, float]]:
    policy_type = str(policy.get("policy_type") or "")
    parameters = policy.get("signal_parameters")
    allocation = policy.get("allocation_parameters")
    if not isinstance(parameters, dict) or not isinstance(allocation, dict):
        raise ValueError("candidate policy parameters are malformed")
    dates = pd.DatetimeIndex(exchange_sessions)
    if not panel.index.equals(dates):
        raise ValueError("price panel index differs from locked exchange sessions")
    features = _features(panel)
    symbols = panel.symbols
    risk_symbols = [symbol for symbol in symbols if symbol != "BIL"]
    schedule: dict[pd.Timestamp, dict[str, float]] = {}
    active_age: dict[str, int] = {}
    breakout_state: dict[str, bool] = {symbol: False for symbol in risk_symbols}
    calendar_active = (
        _calendar_active_sessions(dates, parameters)
        if policy_type == "exchange_session_calendar_window"
        else set()
    )

    for decision_position in range(len(dates) - 1):
        decision = dates[decision_position]
        execution = dates[decision_position + 1]
        row = decision_position
        weights: dict[str, float] | None = None

        if policy_type == "exchange_session_calendar_window":
            weights = (
                {str(allocation["risk_asset"]): 1.0}
                if execution in calendar_active
                else _fallback()
            )
        elif policy_type in {"absolute_trend_allocation", "multihorizon_trend_vote"}:
            should_rebalance = (
                _is_month_end(decision, execution)
                if policy.get("rebalance_frequency") == "month_end"
                else _is_week_end(decision, execution)
            )
            if should_rebalance:
                assets = [str(value) for value in allocation["risk_assets"]]
                if policy_type == "absolute_trend_allocation":
                    selected = [
                        symbol
                        for symbol in assets
                        if float(features["trend_252"].iloc[row].get(symbol, np.nan)) > 0.0
                    ]
                else:
                    selected = []
                    for symbol in assets:
                        votes = sum(
                            float(features[name].iloc[row].get(symbol, np.nan)) > 0.0
                            for name in ("trend_63", "trend_126", "trend_252")
                        )
                        if votes >= int(parameters["positive_votes_required"]):
                            selected.append(symbol)
                weights = _inverse_volatility_weight(
                    features["realized_volatility_20"].iloc[row],
                    selected,
                    max_weight=float(allocation["max_weight"]),
                )
        elif policy_type == "stateful_breakout_channel" and _is_week_end(decision, execution):
            assets = [str(value) for value in allocation["risk_assets"]]
            for symbol in assets:
                close = float(panel.closes.iloc[row][symbol])
                entry = float(features["breakout_high_55"].iloc[row][symbol])
                exit_value = float(features["exit_low_20"].iloc[row][symbol])
                if math.isfinite(exit_value) and close <= exit_value * (1.0 + 1e-12):
                    breakout_state[symbol] = False
                if math.isfinite(entry) and close >= entry * (1.0 - 1e-12):
                    breakout_state[symbol] = True
            weights = _equal_weight(
                [symbol for symbol in assets if breakout_state[symbol]],
                max_weight=float(allocation["max_weight"]),
            )
        elif policy_type in {
            "lagged_overnight_gap_fade",
            "lagged_gap_trend_continuation",
            "intraday_loss_next_session_recovery",
        }:
            if policy_type == "lagged_overnight_gap_fade":
                selected = [
                    symbol
                    for symbol in risk_symbols
                    if float(features["overnight_return"].iloc[row][symbol])
                    <= float(parameters["completed_session_gap_max"])
                    and float(features["volume_ratio_20"].iloc[row][symbol])
                    >= float(parameters["volume_ratio_min"])
                ]
                selected.sort(
                    key=lambda symbol: float(features["overnight_return"].iloc[row][symbol])
                )
            elif policy_type == "lagged_gap_trend_continuation":
                selected = [
                    symbol
                    for symbol in risk_symbols
                    if float(features["overnight_return"].iloc[row][symbol])
                    >= float(parameters["completed_session_gap_min"])
                    and float(features["trend_20"].iloc[row][symbol])
                    > float(parameters["trend_20_min"])
                ]
                selected.sort(
                    key=lambda symbol: float(features["overnight_return"].iloc[row][symbol]),
                    reverse=True,
                )
            else:
                selected = [
                    symbol
                    for symbol in risk_symbols
                    if float(features["intraday_return"].iloc[row][symbol])
                    <= float(parameters["completed_session_intraday_return_max"])
                    and float(features["trend_20"].iloc[row][symbol])
                    > float(parameters["trend_20_min"])
                ]
                selected.sort(
                    key=lambda symbol: float(features["intraday_return"].iloc[row][symbol])
                )
            weights = _equal_weight(selected[:3], max_weight=float(allocation["max_weight"]))
        elif policy_type in {
            "cross_sectional_loser_recovery",
            "rsi_recovery_confirmation",
            "volume_shock_reversal",
        }:
            max_holding = int(parameters["max_holding_sessions"])
            active_age = {
                symbol: age + 1 for symbol, age in active_age.items() if age + 1 < max_holding
            }
            if policy_type == "rsi_recovery_confirmation":
                active_age = {
                    symbol: age
                    for symbol, age in active_age.items()
                    if float(features["rsi_7"].iloc[row][symbol])
                    < float(parameters["exit_rsi_min"])
                }
                entrants = [
                    symbol
                    for symbol in risk_symbols
                    if row > 0
                    and float(features["rsi_7"].iloc[row - 1][symbol])
                    <= float(parameters["prior_rsi_max"])
                    and float(features["rsi_7"].iloc[row][symbol])
                    > float(parameters["current_rsi_min"])
                    and float(features["trend_gap_200"].iloc[row][symbol]) > 0.0
                ]
                entrants.sort(key=lambda symbol: float(features["rsi_7"].iloc[row][symbol]))
            elif policy_type == "volume_shock_reversal":
                entrants = [
                    symbol
                    for symbol in risk_symbols
                    if float(features["return_5"].iloc[row][symbol])
                    <= float(parameters["return_5_max"])
                    and float(features["volume_shock_20"].iloc[row][symbol])
                    >= float(parameters["volume_shock_min"])
                    and float(features["trend_gap_200"].iloc[row][symbol]) > 0.0
                ]
                entrants.sort(key=lambda symbol: float(features["return_5"].iloc[row][symbol]))
            else:
                entrants = [
                    symbol
                    for symbol in risk_symbols
                    if float(features["return_5"].iloc[row][symbol])
                    <= float(parameters["return_5_max"])
                    and float(features["trend_gap_200"].iloc[row][symbol]) > 0.0
                ]
                entrants.sort(key=lambda symbol: float(features["return_5"].iloc[row][symbol]))
            limit = int(parameters.get("select_worst_count", 3))
            for symbol in entrants:
                if len(active_age) >= limit:
                    break
                active_age.setdefault(symbol, 0)
            weights = _equal_weight(
                list(active_age)[:limit],
                max_weight=float(allocation["max_weight"]),
            )
        elif policy_type == "cross_asset_inverse_volatility" and _is_week_end(decision, execution):
            assets = [str(value) for value in allocation["risk_assets"]]
            selected = [
                symbol
                for symbol in assets
                if float(features["trend_gap_200"].iloc[row][symbol])
                > float(parameters["trend_gap_200_min"])
            ]
            weights = _inverse_volatility_weight(
                features["realized_volatility_20"].iloc[row],
                selected,
                max_weight=float(allocation["max_weight"]),
            )
        elif policy_type == "discrete_beta_ladder" and _is_week_end(decision, execution):
            trend = float(features["trend_gap_200"].iloc[row]["QQQ"])
            volatility = float(features["realized_volatility_20"].iloc[row]["QQQ"]) * math.sqrt(
                float(parameters["annualization_sessions"])
            )
            if not math.isfinite(trend) or trend <= float(
                parameters["risk_off_when_trend_gap_200_lte"]
            ):
                sleeve = "BIL"
            elif volatility <= float(parameters["tqqq_when_annualized_vol_lte"]):
                sleeve = "TQQQ"
            elif volatility <= float(parameters["qld_when_annualized_vol_lte"]):
                sleeve = "QLD"
            else:
                sleeve = str(parameters["otherwise"])
            weights = {sleeve: 1.0}
        elif policy_type == "volatility_drawdown_state_switch" and _is_week_end(
            decision, execution
        ):
            vol20 = float(features["realized_volatility_20"].iloc[row]["QQQ"])
            vol63 = float(features["realized_volatility_63"].iloc[row]["QQQ"])
            drawdown = float(features["drawdown_63"].iloc[row]["QQQ"])
            trend = float(features["trend_gap_200"].iloc[row]["QQQ"])
            stress = (
                math.isfinite(vol20)
                and math.isfinite(vol63)
                and vol63 > 0.0
                and vol20 / vol63 >= float(parameters["stress_vol_ratio_min"])
            ) or (math.isfinite(drawdown) and drawdown <= float(parameters["stress_drawdown_max"]))
            risk_on = (
                math.isfinite(drawdown)
                and drawdown >= float(parameters["risk_on_drawdown_min"])
                and math.isfinite(trend)
                and trend > float(parameters["risk_on_trend_gap_min"])
            )
            sleeve = (
                str(allocation["stress"])
                if stress
                else str(allocation["risk_on"])
                if risk_on
                else str(allocation["transition"])
            )
            weights = {sleeve: 1.0}
        elif policy_type == "static_hotspot_cross_sectional_rank_control" and _is_month_end(
            decision, execution
        ):
            scores = features["momentum_252_skip21"].iloc[row].drop(labels=["BIL"], errors="ignore")
            scores = scores[np.isfinite(scores.to_numpy(dtype=float))]
            selected = list(
                scores.sort_values(ascending=False, kind="stable")
                .head(int(parameters["select_count"]))
                .index
            )
            weights = _equal_weight(selected, max_weight=float(allocation["max_weight"]))
        elif policy_type.startswith("pit_"):
            raise ValueError("PIT stock policies cannot run without their declared dependency")
        elif policy_type not in {
            "absolute_trend_allocation",
            "multihorizon_trend_vote",
            "stateful_breakout_channel",
            "cross_asset_inverse_volatility",
            "discrete_beta_ladder",
            "volatility_drawdown_state_switch",
            "static_hotspot_cross_sectional_rank_control",
        }:
            raise ValueError(f"unsupported candidate policy type: {policy_type}")

        if weights is not None:
            _validate_weights(weights, symbols)
            schedule[execution] = weights
    return schedule


def simulate_target_schedule(
    panel: PricePanel,
    schedule: Mapping[pd.Timestamp, Mapping[str, float]],
    *,
    cost_bps: int,
    validation_start: date = VALIDATION_START,
    validation_end: date = VALIDATION_END,
) -> SimulationResult:
    if cost_bps < 0:
        raise ValueError("cost bps must be nonnegative")
    dates = panel.index
    weights = {symbol: 0.0 for symbol in panel.symbols}
    if "BIL" not in weights:
        raise ValueError("candidate panel requires BIL fallback")
    weights["BIL"] = 1.0
    returns: list[float] = []
    turnover_rows: list[float] = []
    return_dates: list[pd.Timestamp] = []
    signals: list[dict[str, Any]] = []
    for position in range(len(dates) - 1):
        current = dates[position]
        following = dates[position + 1]
        turnover = 0.0
        if current in schedule:
            target = {symbol: float(schedule[current].get(symbol, 0.0)) for symbol in panel.symbols}
            _validate_weights(
                {key: value for key, value in target.items() if value > 0.0},
                panel.symbols,
            )
            turnover = math.fsum(abs(target[symbol] - weights[symbol]) for symbol in panel.symbols)
            weights = target
            row = {
                "schema_version": 1,
                "execution_session": current.date().isoformat(),
                "decision_session": dates[position - 1].date().isoformat()
                if position > 0
                else None,
                "target_weights": {
                    symbol: value for symbol, value in sorted(weights.items()) if value > 0.0
                },
                "one_way_turnover": turnover,
                "broker_writes": False,
            }
            row["signal_id"] = _canonical_sha256(row)
            signals.append(row)
        asset_returns = panel.opens.iloc[position + 1] / panel.opens.iloc[position] - 1.0
        gross_return = math.fsum(
            weights[symbol] * float(asset_returns[symbol]) for symbol in panel.symbols
        )
        transaction_cost = turnover * cost_bps / 10_000.0
        net_return = (1.0 - transaction_cost) * (1.0 + gross_return) - 1.0
        if not math.isfinite(net_return) or net_return <= -1.0:
            raise ValueError(f"candidate produced invalid return on {following.date()}")
        denominator = 1.0 + gross_return
        weights = {
            symbol: weights[symbol] * (1.0 + float(asset_returns[symbol])) / denominator
            for symbol in panel.symbols
        }
        if validation_start <= following.date() <= validation_end:
            return_dates.append(following)
            returns.append(net_return)
            turnover_rows.append(turnover)
    return SimulationResult(
        returns=pd.Series(returns, index=pd.DatetimeIndex(return_dates), dtype=float),
        turnover=pd.Series(turnover_rows, index=pd.DatetimeIndex(return_dates), dtype=float),
        signal_rows=tuple(
            row
            for row in signals
            if validation_start <= date.fromisoformat(row["execution_session"]) <= validation_end
        ),
    )


def _asset_returns(panel: PricePanel, symbol: str, index: pd.DatetimeIndex) -> pd.Series:
    values = panel.opens[symbol].pct_change()
    result = values.reindex(index)
    if result.isna().any():
        raise ValueError(f"benchmark return stream is incomplete: {symbol}")
    return result.astype(float)


def _fixed_initial_notional_buy_and_hold_returns(
    panel: PricePanel,
    symbols: tuple[str, ...],
    index: pd.DatetimeIndex,
    *,
    cost_bps: int,
) -> pd.Series:
    if not symbols:
        raise ValueError("buy-and-hold benchmark requires at least one symbol")
    if cost_bps < 0 or cost_bps >= 10_000:
        raise ValueError("buy-and-hold benchmark cost bps must be in [0, 10000)")
    if index.empty or panel.index[0] >= index[0]:
        raise ValueError("buy-and-hold benchmark initialization must precede validation")
    missing = sorted(set(symbols) - set(panel.symbols))
    if missing:
        raise ValueError(f"buy-and-hold benchmark symbols are missing: {missing}")
    selected = panel.opens.loc[:, list(symbols)].astype(float)
    initial = selected.iloc[0]
    if not np.isfinite(initial.to_numpy(dtype=float)).all() or (initial <= 0.0).any():
        raise ValueError("buy-and-hold benchmark has invalid initial opens")
    gross_wealth = selected.divide(initial, axis="columns").mean(axis="columns")
    net_wealth = gross_wealth * (1.0 - cost_bps / 10_000.0)
    result = net_wealth.pct_change().reindex(index)
    if result.isna().any() or not np.isfinite(result.to_numpy(dtype=float)).all():
        raise ValueError("buy-and-hold benchmark return stream is incomplete")
    return result.astype(float)


def _compound(values: pd.Series) -> float:
    return float(np.expm1(np.log1p(values.to_numpy(dtype=float)).sum()))


def _cagr(values: pd.Series) -> float:
    return float((1.0 + _compound(values)) ** (252.0 / len(values)) - 1.0)


def _max_drawdown(values: pd.Series) -> float:
    wealth = np.concatenate(([1.0], np.cumprod(1.0 + values.to_numpy(dtype=float))))
    return float(np.min(wealth / np.maximum.accumulate(wealth) - 1.0))


def _safe_sharpe(excess: pd.Series) -> float:
    values = excess.to_numpy(dtype=float)
    if len(values) < 2 or float(np.std(values, ddof=1)) <= 0.0:
        return -999.0
    return annualized_sharpe(values)


def _fold_returns(
    values: pd.Series,
    fold_contract: Mapping[str, Any],
) -> tuple[list[list[float]], list[dict[str, Any]]]:
    rows: list[list[float]] = []
    summaries: list[dict[str, Any]] = []
    folds = fold_contract.get("folds")
    if not isinstance(folds, list) or len(folds) != 4:
        raise ValueError("development fold contract must define four folds")
    for fold in folds:
        mask = (values.index >= pd.Timestamp(fold["start_session"])) & (
            values.index <= pd.Timestamp(fold["end_session"])
        )
        selected = values.loc[mask]
        if selected.empty:
            raise ValueError(f"development fold is empty: {fold['fold_id']}")
        rows.append(selected.to_list())
        summaries.append(
            {
                "fold_id": fold["fold_id"],
                "row_count": len(selected),
                "total_return": _compound(selected),
            }
        )
    return rows, summaries


def _promotion_passes(
    metrics: Mapping[str, float | int],
    sharpe: float,
    dsr_probability: float,
    contract: ResearchCampaignContract,
) -> dict[str, bool]:
    policy = contract.candidate_promotion_policy
    family_policy = contract.statistical_family_policy
    if family_policy.primary_sharpe_operator != ">":
        raise ValueError("unsupported primary Sharpe operator")
    return {
        "sharpe_excess_bil": sharpe > family_policy.primary_sharpe_minimum,
        "dsr_probability": dsr_probability >= family_policy.dsr_minimum,
        "cagr": float(metrics["cagr"]) >= policy.cagr_minimum,
        "cagr_excess_qqq": float(metrics["cagr_excess_qqq"]) >= policy.cagr_excess_qqq_minimum,
        "tqqq_cagr_capture": float(metrics["tqqq_cagr_capture"])
        >= policy.tqqq_cagr_capture_minimum,
        "tqqq_upside_capture": float(metrics["tqqq_upside_capture"])
        >= policy.tqqq_upside_capture_minimum,
        "tqqq_downside_capture": float(metrics["tqqq_downside_capture"])
        <= policy.tqqq_downside_capture_maximum,
        "max_drawdown": float(metrics["max_drawdown"]) >= policy.max_drawdown_minimum,
        "mar": float(metrics["mar"]) >= policy.mar_minimum,
        "positive_fold_count": int(metrics["positive_fold_count"]) >= policy.minimum_positive_folds,
        "stress_total_return": float(metrics["stress_total_return"])
        > policy.stress_total_return_minimum,
    }


def _write_jsonl(path: Path, rows: list[dict[str, Any]] | tuple[dict[str, Any], ...]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(_canonical_json(row) + "\n" for row in rows),
        encoding="ascii",
    )


def _write_or_verify_json(
    staged_path: Path,
    final_path: Path,
    payload: Mapping[str, Any],
) -> Path:
    expected = (json.dumps(dict(payload), indent=2, sort_keys=True) + "\n").encode("utf-8")
    existing = [path for path in (staged_path, final_path) if path.exists()]
    if len(existing) > 1:
        raise FileExistsError(
            f"development publication artifact has dual custody: {final_path.name}"
        )
    if existing:
        path = existing[0]
        if path.is_symlink() or not path.is_file() or path.read_bytes() != expected:
            raise ValueError(
                f"development publication artifact identity mismatch: {final_path.name}"
            )
        return path
    write_json(staged_path, dict(payload))
    return staged_path


def _write_or_verify_jsonl(
    staged_path: Path,
    final_path: Path,
    rows: list[dict[str, Any]],
) -> Path:
    expected = "".join(_canonical_json(row) + "\n" for row in rows).encode("ascii")
    existing = [path for path in (staged_path, final_path) if path.exists()]
    if len(existing) > 1:
        raise FileExistsError(
            f"development publication artifact has dual custody: {final_path.name}"
        )
    if existing:
        path = existing[0]
        if path.is_symlink() or not path.is_file() or path.read_bytes() != expected:
            raise ValueError(
                f"development publication artifact identity mismatch: {final_path.name}"
            )
        return path
    _write_jsonl(staged_path, rows)
    return staged_path


def _benchmark_family(
    benchmark_panel: PricePanel,
    branch_panel: PricePanel,
    *,
    primary_symbol: str,
    index: pd.DatetimeIndex,
) -> BenchmarkFamilyResult:
    if primary_symbol not in branch_panel.symbols:
        raise ValueError(f"same-symbol benchmark is absent from branch universe: {primary_symbol}")
    full_universe = tuple(branch_panel.symbols)
    primary_asset_returns = {
        symbol: _fixed_initial_notional_buy_and_hold_returns(
            branch_panel,
            (symbol,),
            index,
            cost_bps=PRIMARY_COST_BPS,
        )
        for symbol in full_universe
    }
    best_symbol = max(
        full_universe,
        key=lambda symbol: _cagr(primary_asset_returns[symbol]),
    )
    best_id = f"{best_symbol}_ex_post_best"
    returns_by_cost: dict[int, dict[str, pd.Series]] = {}
    for cost_bps in COST_VIEWS:
        streams = {
            f"{symbol}_buy_hold": _fixed_initial_notional_buy_and_hold_returns(
                benchmark_panel,
                (symbol,),
                index,
                cost_bps=cost_bps,
            )
            for symbol in BENCHMARK_SYMBOLS
        }
        streams[f"{primary_symbol}_same_symbol_buy_hold"] = (
            _fixed_initial_notional_buy_and_hold_returns(
                branch_panel,
                (primary_symbol,),
                index,
                cost_bps=cost_bps,
            )
        )
        streams["equal_weight_universe"] = _fixed_initial_notional_buy_and_hold_returns(
            branch_panel,
            full_universe,
            index,
            cost_bps=cost_bps,
        )
        streams[best_id] = _fixed_initial_notional_buy_and_hold_returns(
            branch_panel,
            (best_symbol,),
            index,
            cost_bps=cost_bps,
        )
        returns_by_cost[cost_bps] = streams
    roles = {
        "same_symbol_buy_and_hold": f"{primary_symbol}_same_symbol_buy_hold",
        "equal_weight_universe": "equal_weight_universe",
        "market_proxy": "SPY_buy_hold",
        "growth_proxy": "QQQ_buy_hold",
        "sector_theme_proxy": "XLK_buy_hold",
        "cash_proxy": "BIL_buy_hold",
        "leveraged_growth_proxy": "TQQQ_buy_hold",
        "ex_post_best_symbol": best_id,
    }
    benchmark_initialization = benchmark_panel.index[0].date().isoformat()
    branch_initialization = branch_panel.index[0].date().isoformat()
    initialization_session_by_stream = {
        f"{symbol}_buy_hold": benchmark_initialization for symbol in BENCHMARK_SYMBOLS
    }
    initialization_session_by_stream.update(
        {
            f"{primary_symbol}_same_symbol_buy_hold": branch_initialization,
            "equal_weight_universe": branch_initialization,
            best_id: branch_initialization,
        }
    )
    return BenchmarkFamilyResult(
        returns_by_cost=returns_by_cost,
        roles=roles,
        initialization_session_by_stream=initialization_session_by_stream,
        initial_one_way_turnover=1.0,
        initial_wealth_by_cost={cost: 1.0 - cost / 10_000.0 for cost in COST_VIEWS},
    )


def _candidate_metrics(
    contract: ResearchCampaignContract,
    *,
    result_by_cost: Mapping[int, SimulationResult],
    benchmark_family: BenchmarkFamilyResult,
    fold_contract: Mapping[str, Any],
    effective_trial_count: int,
) -> dict[str, Any]:
    primary = result_by_cost[PRIMARY_COST_BPS].returns
    benchmark_streams = benchmark_family.returns_by_cost[PRIMARY_COST_BPS]
    benchmark_roles = benchmark_family.roles
    cash = benchmark_streams[benchmark_roles["cash_proxy"]]
    excess = primary - cash
    fold_values, fold_summaries = _fold_returns(primary, fold_contract)
    promotion = recompute_candidate_promotion_metrics(
        candidate_returns=primary.to_list(),
        qqq_returns=benchmark_streams[benchmark_roles["growth_proxy"]].to_list(),
        tqqq_returns=benchmark_streams[benchmark_roles["leveraged_growth_proxy"]].to_list(),
        stress_returns=result_by_cost[40].returns.to_list(),
        development_fold_returns=fold_values,
        annualization_sessions=contract.candidate_promotion_policy.annualization_sessions,
    )
    sharpe = _safe_sharpe(excess)
    try:
        dsr = deflated_sharpe_probability(
            excess.to_numpy(dtype=float),
            trial_count=effective_trial_count,
            hac_lag=contract.statistical_family_policy.dsr_hac_lag,
        )
    except ValueError:
        dsr = 0.0
    passes = _promotion_passes(
        promotion,
        sharpe,
        dsr,
        contract,
    )
    fold_excess_sharpes = []
    for fold, summary in zip(fold_values, fold_summaries, strict=True):
        fold_id = summary["fold_id"]
        fold_definition = next(row for row in fold_contract["folds"] if row["fold_id"] == fold_id)
        cash_slice = cash.loc[
            (cash.index >= pd.Timestamp(fold_definition["start_session"]))
            & (cash.index <= pd.Timestamp(fold_definition["end_session"]))
        ]
        fold_excess_sharpes.append(
            _safe_sharpe(pd.Series(fold, index=cash_slice.index, dtype=float) - cash_slice)
        )
    return {
        "row_count": len(primary),
        "first_return_session": primary.index[0].date().isoformat(),
        "last_return_session": primary.index[-1].date().isoformat(),
        "terminal_liquidation_in_metrics": False,
        "return_stream_identity": "continuous_daily_open_to_open_net_returns_terminal_free",
        "primary_cost_bps": PRIMARY_COST_BPS,
        "annualized_sharpe_excess_bil": sharpe,
        "development_dsr_probability_diagnostic": dsr,
        "development_dsr_effective_trial_count": effective_trial_count,
        "quality": min(fold_excess_sharpes),
        "quality_metric": contract.qd_archive.quality_metric,
        "fold_excess_sharpes": dict(
            zip((row["fold_id"] for row in fold_summaries), fold_excess_sharpes, strict=True)
        ),
        "folds": fold_summaries,
        "promotion_metric_diagnostics": promotion,
        "development_gate_diagnostics": passes,
        "all_development_gate_diagnostics_pass": all(passes.values()),
        "cost_views": {
            str(cost): {
                "cagr": _cagr(simulation.returns),
                "total_return": _compound(simulation.returns),
                "max_drawdown": _max_drawdown(simulation.returns),
                "total_one_way_turnover": float(simulation.turnover.sum()),
            }
            for cost, simulation in sorted(result_by_cost.items())
        },
        "benchmark_metrics": {
            role: {
                "stream_id": benchmark_id,
                "primary_cost_bps": PRIMARY_COST_BPS,
                "cagr": _cagr(benchmark_streams[benchmark_id]),
                "total_return": _compound(benchmark_streams[benchmark_id]),
                "cost_views": {
                    str(cost_bps): {
                        "initialization_cost_bps": cost_bps,
                        "initialization_session": benchmark_family.initialization_session_by_stream[
                            benchmark_id
                        ],
                        "initialization_precedes_validation": True,
                        "initial_one_way_turnover": benchmark_family.initial_one_way_turnover,
                        "initial_wealth_after_cost": benchmark_family.initial_wealth_by_cost[
                            cost_bps
                        ],
                        "cagr": _cagr(streams[benchmark_id]),
                        "total_return": _compound(streams[benchmark_id]),
                    }
                    for cost_bps, streams in sorted(benchmark_family.returns_by_cost.items())
                },
                "allocation": BENCHMARK_ALLOCATION_IDENTITY,
                "terminal_liquidation_included": False,
            }
            for role, benchmark_id in benchmark_roles.items()
        },
    }


def _trial_row(
    *,
    candidate_id: str,
    iter_id: str,
    action: str,
    spec_path: str,
    metrics_path: str | None,
    metrics_sha256: str | None,
    effective_trial_exposure: float,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "campaign_id": CAMPAIGN_ID,
        "iter_id": iter_id,
        "candidate_id": candidate_id,
        "action": action,
        "visibility_partition": "development_validation",
        "spec_path": spec_path,
        "metrics_path": metrics_path,
        "metrics_sha256": metrics_sha256,
        "cost_views_bps": list(COST_VIEWS) if action == "evaluate" else [],
        "effective_trial_exposure": effective_trial_exposure,
        "model_training_count": 0,
        "frozen_oos_rows_read": 0,
        "broker_writes": False,
    }


def _development_family_diagnostics(
    contract: ResearchCampaignContract,
    *,
    evaluated: list[CandidateDevelopmentResult],
    benchmark_returns: pd.Series,
    effective_trial_count: int,
) -> dict[str, Any]:
    promotable = sorted(
        (result for result in evaluated if result.promotion_eligible),
        key=lambda result: result.candidate_id,
    )
    candidate_ids = [result.candidate_id for result in promotable]
    base = {
        "scope": "all_evaluated_promotion_eligible_candidates",
        "visibility_partition": "development_validation",
        "return_stream_identity": "continuous_daily_open_to_open_net_returns_terminal_free",
        "primary_cost_bps": PRIMARY_COST_BPS,
        "candidate_ids": candidate_ids,
        "effective_trial_count": effective_trial_count,
        "diagnostic_only_not_frozen_oos_evidence": True,
    }
    if len(promotable) < 2:
        return {
            **base,
            "status": "undefined",
            "pass": False,
            "reason": "fewer_than_two_evaluated_promotion_eligible_candidates",
        }
    policy = contract.statistical_family_policy
    try:
        statistics = recompute_campaign_statistics(
            candidate_ids=candidate_ids,
            candidate_returns={
                result.candidate_id: result.returns_by_cost[PRIMARY_COST_BPS].to_list()
                for result in promotable
            },
            benchmark_returns=benchmark_returns.to_list(),
            effective_trial_count=effective_trial_count,
            dsr_hac_lag=policy.dsr_hac_lag,
            pbo_block_count=policy.pbo_block_count,
            pbo_in_sample_block_count=policy.pbo_in_sample_block_count,
            spa_block_length=policy.spa_block_length,
            spa_resample_count=policy.spa_resample_count,
            spa_seed=policy.spa_seed,
        )
    except (ArithmeticError, ValueError) as exc:
        return {
            **base,
            "status": "undefined",
            "pass": False,
            "reason": f"{type(exc).__name__}:{exc}",
        }
    for result in promotable:
        reported = float(result.metrics["development_dsr_probability_diagnostic"])
        actual = statistics.candidate_dsr_probabilities[result.candidate_id]
        if not math.isclose(reported, actual, rel_tol=1e-12, abs_tol=1e-12):
            raise ValueError(f"development DSR recomputation mismatch: {result.candidate_id}")
    pbo_pass = statistics.pbo_probability <= policy.pbo_maximum
    spa_pass = statistics.spa_p_value <= policy.spa_p_value_maximum
    return {
        **base,
        "status": "ok",
        "candidate_sharpe_excess_bil": statistics.candidate_sharpe_excess_bil,
        "candidate_dsr_probabilities": statistics.candidate_dsr_probabilities,
        "pbo": {
            "value": statistics.pbo_probability,
            "operator": "<=",
            "threshold": policy.pbo_maximum,
            "pass": pbo_pass,
        },
        "spa": {
            "value": statistics.spa_p_value,
            "operator": "<=",
            "threshold": policy.spa_p_value_maximum,
            "pass": spa_pass,
        },
        "pass": pbo_pass and spa_pass,
    }


def _advancing_pair_correlation_diagnostic(
    contract: ResearchCampaignContract,
    advancing_returns: Mapping[str, pd.Series],
) -> dict[str, Any]:
    policy = contract.statistical_family_policy.advancing_pair_correlation
    if policy.method != "pearson" or policy.operator != "<=":
        raise ValueError("unsupported advancing-pair correlation policy")
    ordered = sorted(advancing_returns)
    correlations = {
        f"{left}:{right}": float(
            advancing_returns[left].corr(advancing_returns[right], method=policy.method)
        )
        for offset, left in enumerate(ordered)
        for right in ordered[offset + 1 :]
    }
    passing_pairs = [
        {
            "left": pair.split(":", maxsplit=1)[0],
            "right": pair.split(":", maxsplit=1)[1],
            "correlation": value,
        }
        for pair, value in sorted(correlations.items())
        if math.isfinite(value) and abs(value) <= policy.absolute_maximum
    ]
    return {
        "policy": {
            "method": policy.method,
            "return_stream": policy.return_stream,
            "absolute_maximum": policy.absolute_maximum,
            "operator": policy.operator,
            "minimum_passing_pair_count": policy.minimum_passing_pair_count,
        },
        "correlations": correlations,
        "passing_pairs": passing_pairs,
        "passing_pair_count": len(passing_pairs),
        "pass": len(passing_pairs) >= policy.minimum_passing_pair_count,
    }


@dataclass(frozen=True)
class StagedDevelopmentRecovery:
    attempt: dict[str, Any]
    attempt_binding: dict[str, str]
    amendment_binding: dict[str, str]
    campaign_contract_sha256: str
    campaign_staging: Path
    branch_staging: dict[str, Path]
    evaluated: tuple[CandidateDevelopmentResult, ...]
    excluded_candidate_ids: tuple[str, ...]
    branch_reports: dict[str, Any]
    partition_contract_sha256_by_iter: dict[str, str]


@dataclass(frozen=True)
class RecoveryCampaignOutputs:
    archive: dict[str, Any]
    ledger_rows: tuple[dict[str, Any], ...]
    report: dict[str, Any]


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file() or path.is_symlink():
        raise FileNotFoundError(path)
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="ascii").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid staged JSONL row: {path}:{line_number}") from exc
        if not isinstance(row, dict):
            raise ValueError(f"staged JSONL row must be an object: {path}:{line_number}")
        rows.append(row)
    return rows


def _is_sha256(value: Any) -> bool:
    text = str(value or "")
    return len(text) == 64 and all(character in "0123456789abcdef" for character in text)


def _staged_evidence_inventory_binding(
    root: Path,
    *,
    contract: ResearchCampaignContract,
    run_token: str,
) -> dict[str, Any]:
    files: list[dict[str, Any]] = []
    branch_ids: list[str] = []
    for iter_id in contract.child_iteration_ids:
        feasibility = _read_json(root / ITERATION_ROOT / iter_id / "data-feasibility.json")
        if feasibility.get("historical_evaluation_authorized") is not True:
            continue
        branch_ids.append(iter_id)
        staging = root / ITERATION_ROOT / iter_id / f"evaluation-run.staging-{run_token}"
        destination = root / ITERATION_ROOT / iter_id / "evaluation-run"
        sources = [path for path in (staging, destination) if path.exists()]
        if len(sources) != 1 or sources[0].is_symlink() or not sources[0].is_dir():
            raise ValueError(f"development recovery branch custody is invalid: {iter_id}")
        source = sources[0]
        for path in sorted(source.iterdir()):
            if path.is_symlink() or not path.is_file():
                raise ValueError(f"development recovery staged entry is not a file: {path}")
            files.append(
                {
                    "path": (destination / path.name).relative_to(root).as_posix(),
                    "size_bytes": path.stat().st_size,
                    "sha256": _sha256(path),
                }
            )
    payload = {
        "algorithm": "sha256_canonical_json_sorted_path_size_sha256_v1",
        "run_token": run_token,
        "branch_ids": branch_ids,
        "file_count": len(files),
        "files": files,
    }
    return {
        "algorithm": payload["algorithm"],
        "run_token": run_token,
        "branch_ids": branch_ids,
        "file_count": len(files),
        "sha256": _canonical_sha256(payload),
    }


def _recovery_preregistration_inventory_binding(
    root: Path,
    *,
    contract: ResearchCampaignContract,
) -> dict[str, Any]:
    files: list[dict[str, Any]] = []
    for iter_id in contract.child_iteration_ids:
        lock = _read_json(root / ITERATION_ROOT / iter_id / "phase-one-preregistration-lock.json")
        if lock.get("mutable_after_lock") != list(RECOVERY_MUTABLE_PREREGISTRATION_FILES):
            raise ValueError(
                f"development recovery mutable preregistration inventory mismatch: {iter_id}"
            )
        for name in RECOVERY_MUTABLE_PREREGISTRATION_FILES:
            path = root / ITERATION_ROOT / iter_id / name
            if path.is_symlink() or not path.is_file():
                raise FileNotFoundError(path)
            files.append(
                {
                    "path": path.relative_to(root).as_posix(),
                    "size_bytes": path.stat().st_size,
                    "sha256": _sha256(path),
                }
            )
    payload = {
        "algorithm": "sha256_canonical_json_sorted_path_size_sha256_v1",
        "iteration_ids": list(contract.child_iteration_ids),
        "file_count": len(files),
        "files": files,
    }
    return {
        "algorithm": payload["algorithm"],
        "iteration_ids": payload["iteration_ids"],
        "file_count": len(files),
        "sha256": _canonical_sha256(payload),
    }


def _validate_recovery_knowledge_state(
    root: Path,
    *,
    iter_id: str,
    iteration: Path,
    immutable_inventory: Mapping[str, Any],
) -> None:
    baseline_path = iteration / "knowledge-baseline.json"
    scout_path = iteration / "knowledge-scout.json"
    assessment_path = iteration / "knowledge-assessment.json"
    context_path = iteration / "knowledge-context.json"
    reuse_path = iteration / "model-reuse-decision.json"
    mutable_paths = (
        baseline_path,
        scout_path,
        assessment_path,
        context_path,
        reuse_path,
    )
    if any(path.is_symlink() or not path.is_file() for path in mutable_paths):
        raise FileNotFoundError(f"development recovery knowledge evidence missing: {iter_id}")
    expected_file_hashes = RECOVERY_KNOWLEDGE_FILE_SHA256.get(iter_id)
    actual_file_hashes = tuple(_sha256(iteration / name) for name in RECOVERY_KNOWLEDGE_FILENAMES)
    knowledge_payloads = {
        name: _read_json(iteration / name) for name in RECOVERY_KNOWLEDGE_FILENAMES
    }
    if (
        expected_file_hashes is None
        or actual_file_hashes != expected_file_hashes
        or _canonical_sha256(knowledge_payloads) != RECOVERY_KNOWLEDGE_PAYLOAD_SHA256.get(iter_id)
    ):
        raise ValueError(f"development recovery exact knowledge evidence mismatch: {iter_id}")

    external_brief = immutable_inventory.get("external_brief_json")
    query_manifest = immutable_inventory.get("knowledge_scout_queries")
    if not isinstance(external_brief, dict) or not isinstance(query_manifest, dict):
        raise ValueError(f"development recovery knowledge lock binding missing: {iter_id}")
    _verify_binding(root, external_brief)
    _verify_binding(root, query_manifest)
    expected_visibility = {
        "candidate_generation_excludes": ["challenge_result", "forward_observation"],
        "candidate_generation_reads": ["public_literature", "train_only_empirical"],
        "failed_results_retained": True,
        "serialized_model_reuse_requires_decision": True,
    }

    scout = knowledge_payloads[scout_path.name]
    expected_scout = {
        "schema_version": 2,
        "iter_id": iter_id,
        "manifest_path": query_manifest["path"],
        "query_manifest_sha256": query_manifest["sha256"],
        "baseline_path": baseline_path.relative_to(root).as_posix(),
        "baseline_sha256": _sha256(baseline_path),
        "external_brief_path": external_brief["path"],
        "external_brief_sha256": external_brief["sha256"],
        "contract": {
            "effectiveness_requires_empirical_evidence": True,
            "newest_is_effective": False,
            "search_hit_is_validated_knowledge": False,
        },
    }
    if any(scout.get(name) != value for name, value in expected_scout.items()):
        raise ValueError(f"development recovery knowledge scout identity mismatch: {iter_id}")

    context = knowledge_payloads[context_path.name]
    expected_context = {
        "schema_version": 1,
        "iter_id": iter_id,
        "contract": {
            "challenge_and_forward_results_excluded_from_candidate_generation": True,
            "context_is_research_input_not_alpha": True,
            "restricted_model_outcomes_redacted": True,
            "stale_sources_require_refresh": True,
        },
        "visibility_contract": expected_visibility,
    }
    if any(context.get(name) != value for name, value in expected_context.items()):
        raise ValueError(f"development recovery knowledge context identity mismatch: {iter_id}")
    restricted = context.get("restricted_memory_summary")
    if not isinstance(restricted, dict) or restricted.get("outcome_details_exposed") is not False:
        raise ValueError(f"development recovery restricted knowledge leak: {iter_id}")

    reuse = knowledge_payloads[reuse_path.name]
    expected_reuse = {
        "schema_version": 1,
        "iter_id": iter_id,
        "default_policy": "no_warm_start_without_explicit_drift_or_data_reason",
        "round_decision": {
            "action": "no_model_training_deterministic_discovery_round",
            "reason": (
                "The campaign tests orthogonal deterministic mechanisms first; prior failed "
                "models remain negative memory and receive no trial budget."
            ),
            "retrain": False,
            "status_provenance_required_for_any_future_model": True,
            "warm_start": False,
        },
    }
    if any(reuse.get(name) != value for name, value in expected_reuse.items()):
        raise ValueError(f"development recovery model reuse identity mismatch: {iter_id}")

    assessment = knowledge_payloads[assessment_path.name]
    expected_assessment = {
        "schema_version": 1,
        "iter_id": iter_id,
        "external_brief_path": external_brief["path"],
        "external_brief_sha256": external_brief["sha256"],
        "knowledge_context_path": context_path.relative_to(root).as_posix(),
        "knowledge_index_path": "reports/research/knowledge/index.json",
        "model_reuse_decision_path": reuse_path.relative_to(root).as_posix(),
        "scout_path": scout_path.relative_to(root).as_posix(),
        "status": "ok",
        "blocked": [],
        "visibility_contract": expected_visibility,
        "novelty_policy": {
            "default_requires_new_or_refresh_evidence": True,
            "pure_implementation_repair_reuse": None,
        },
    }
    if any(assessment.get(name) != value for name, value in expected_assessment.items()):
        raise ValueError(f"development recovery knowledge assessment identity mismatch: {iter_id}")


def _validate_recovery_preregistration_state(
    root: Path,
    *,
    contract: ResearchCampaignContract,
    attempt: Mapping[str, Any],
) -> int:
    """Revalidate mutable preregistration evidence without reading market returns."""
    campaign_validation = validate_campaign_contract(CAMPAIGN_ID, root, stage="pre-discovery")
    if not campaign_validation.ok:
        raise ValueError(
            f"development recovery campaign preregistration invalid: {campaign_validation.blocked}"
        )

    hypotheses = {row.hypothesis_id: row for row in contract.hypotheses}
    blueprints_by_iteration = {
        iter_id: [row for row in contract.candidate_blueprints if row.child_iteration_id == iter_id]
        for iter_id in contract.child_iteration_ids
    }
    expected_trial_accounting = {
        "campaign_candidate_count": contract.exposure_budgets.candidate_budget,
        "campaign_trial_exposure_budget": (
            contract.exposure_budgets.cumulative_trial_exposure_budget
        ),
        "effective_trial_count_source": "campaign_pre_oos_seal",
        "maximum_effective_trial_count": (
            contract.exposure_budgets.prior_effective_trial_count
            + contract.exposure_budgets.cumulative_trial_exposure_budget
        ),
        "minimum_effective_trial_count": (
            contract.exposure_budgets.prior_effective_trial_count
            + contract.exposure_budgets.candidate_budget
        ),
        "minimum_incremental_trial_count": contract.exposure_budgets.candidate_budget,
        "prior_effective_trial_count": contract.exposure_budgets.prior_effective_trial_count,
    }
    phase_one_locks = attempt["phase_one_locks"]
    evaluated_count = 0

    for iter_id in contract.child_iteration_ids:
        iteration = root / ITERATION_ROOT / iter_id
        manifest_path = iteration / "candidate-manifest.json"
        feasibility_path = iteration / "data-feasibility.json"
        search_path = iteration / "search-space.json"
        universe_path = iteration / "universe-contract.json"
        manifest = _read_json(manifest_path)
        feasibility = _read_json(feasibility_path)
        search_space = _read_json(search_path)
        universe_contract = _read_json(universe_path)
        lock = _read_json(_verify_binding(root, phase_one_locks[iter_id]))
        inventory = lock["immutable_inventory"]
        if lock.get("mutable_after_lock") != list(RECOVERY_MUTABLE_PREREGISTRATION_FILES):
            raise ValueError(
                f"development recovery mutable preregistration contract mismatch: {iter_id}"
            )
        data_contract = _read_json(_verify_binding(root, inventory["data_contract"]))
        dependency_status = data_contract.get("dependency_status")
        if dependency_status not in {"ready", "dependency_skipped"}:
            raise ValueError(f"development recovery dependency status invalid: {iter_id}")
        authorized = dependency_status == "ready"
        blueprints = blueprints_by_iteration[iter_id]
        expected_ids = [row.candidate_id for row in blueprints]
        _validate_recovery_knowledge_state(
            root,
            iter_id=iter_id,
            iteration=iteration,
            immutable_inventory=inventory,
        )

        candidates = manifest.get("candidates")
        if (
            manifest.get("schema_version") != 2
            or manifest.get("manifest_type") != "generic_candidate_family_v1"
            or manifest.get("iter_id") != iter_id
            or manifest.get("campaign_id") != CAMPAIGN_ID
            or manifest.get("candidate_count") != len(blueprints)
            or manifest.get("generated_before_backtest") is not True
            or manifest.get("model_training_authorized") is not False
            or manifest.get("trial_accounting") != expected_trial_accounting
            or not isinstance(candidates, list)
            or [str(row.get("candidate_id")) for row in candidates] != expected_ids
        ):
            raise ValueError(
                f"development recovery candidate manifest identity mismatch: {iter_id}"
            )

        contract_groups = {
            "benchmarks": ("benchmark_contract", "benchmark_contract", "benchmarks"),
            "candidate_policies": (
                "candidate_policy_contract",
                "candidate_policy_contract",
                "candidate_policies",
            ),
            "costs": ("cost_contract", "cost_contract", "costs"),
            "data": ("data_contract", "data_contract", "data"),
            "features": ("feature_contract", "feature_contract", "features"),
            "labels": ("label_contract", "label_contract", "labels"),
            "validation": ("validation_contract", "validation_contract", "validation"),
        }
        groups = manifest.get("contracts")
        contract_ids: dict[str, str] = {}
        if not isinstance(groups, dict) or set(groups) != set(contract_groups):
            raise ValueError(
                f"development recovery manifest contract inventory mismatch: {iter_id}"
            )
        for group_name, (lock_name, candidate_field, kind) in contract_groups.items():
            group = groups[group_name]
            expected_contract_id = f"{iter_id}_{kind}_v1"
            binding = inventory.get(lock_name)
            if not isinstance(binding, dict) or group != {expected_contract_id: binding}:
                raise ValueError(
                    f"development recovery manifest contract group mismatch: {iter_id}:{group_name}"
                )
            contract_payload = _read_json(_verify_binding(root, binding))
            if (
                contract_payload.get("schema_version") != 1
                or contract_payload.get("contract_id") != expected_contract_id
                or contract_payload.get("campaign_id") != CAMPAIGN_ID
                or contract_payload.get("iter_id") != iter_id
            ):
                raise ValueError(
                    f"development recovery manifest bound contract identity mismatch: "
                    f"{iter_id}:{group_name}"
                )
            contract_ids[candidate_field] = expected_contract_id

        policy_contract = _read_json(_verify_binding(root, inventory["candidate_policy_contract"]))
        policy_rows = policy_contract.get("policies")
        if (
            policy_contract.get("schema_version") != 1
            or policy_contract.get("campaign_id") != CAMPAIGN_ID
            or policy_contract.get("iter_id") != iter_id
            or policy_contract.get("contract_id") != contract_ids["candidate_policy_contract"]
            or policy_contract.get("generated_before_backtest") is not True
            or policy_contract.get("policy_count") != len(blueprints)
            or not isinstance(policy_rows, list)
            or [str(row.get("candidate_id")) for row in policy_rows] != expected_ids
        ):
            raise ValueError(f"development recovery candidate policy identity mismatch: {iter_id}")
        policies_by_id = {str(row["candidate_id"]): row for row in policy_rows}
        locked_policy_hashes = lock.get("candidate_policy_sha256")
        if not isinstance(locked_policy_hashes, dict) or set(locked_policy_hashes) != set(
            expected_ids
        ):
            raise ValueError(f"development recovery candidate policy lock mismatch: {iter_id}")

        expected_spec_hashes: dict[str, str] = {}
        expected_candidates: list[dict[str, Any]] = []
        expected_universe: tuple[str, ...] | None = None
        primary_spec_name = ""
        primary_objective = ""
        for candidate, blueprint in zip(candidates, blueprints, strict=True):
            candidate_id = blueprint.candidate_id
            policy_row = policies_by_id[candidate_id]
            policy = policy_row.get("policy")
            if not isinstance(policy, dict):
                raise ValueError(
                    f"development recovery candidate policy is malformed: {candidate_id}"
                )
            policy_sha256 = _canonical_sha256(policy)
            if (
                policy_row.get("method_variant") != blueprint.method_variant
                or policy_row.get("factor_variant") != blueprint.factor_variant
                or policy_row.get("policy_sha256") != policy_sha256
                or locked_policy_hashes.get(candidate_id) != policy_sha256
            ):
                raise ValueError(
                    f"development recovery candidate policy semantics mismatch: {candidate_id}"
                )

            spec_binding = inventory.get(f"spec_{candidate_id}")
            if not isinstance(spec_binding, dict):
                raise ValueError(
                    f"development recovery candidate spec binding missing: {candidate_id}"
                )
            spec_path = _verify_binding(root, spec_binding)
            spec = load_strategy_spec(spec_path)
            spec_relative = spec_path.relative_to(root).as_posix()
            expected_spec_hashes[spec_relative] = strategy_content_hash(spec)
            spec_payload = spec.model_dump(mode="json")
            if not primary_spec_name:
                primary_spec_name = str(spec_payload.get("name") or "")
            spec_universe = tuple(str(symbol).upper() for symbol in spec.universe)
            if expected_universe is None:
                expected_universe = spec_universe
            elif spec_universe != expected_universe:
                raise ValueError(
                    f"development recovery candidate universe order mismatch: {iter_id}"
                )
            research_design = spec_payload.get("research_design")
            notes = spec_payload.get("notes")
            if not isinstance(research_design, dict) or not isinstance(notes, dict):
                raise ValueError(
                    f"development recovery candidate spec metadata missing: {candidate_id}"
                )
            if not primary_objective:
                primary_objective = str(notes.get("intent") or "")
            expected_design = {
                "iter_id": iter_id,
                "campaign_id": CAMPAIGN_ID,
                "campaign_contract_path": (
                    CAMPAIGN_ROOT / "research-campaign-contract.json"
                ).as_posix(),
                "candidate_manifest_path": manifest_path.relative_to(root).as_posix(),
                "data_feasibility_path": feasibility_path.relative_to(root).as_posix(),
                "universe_contract_path": universe_path.relative_to(root).as_posix(),
                "candidate_policy_contract_path": (iteration / "candidate-policy-contract.json")
                .relative_to(root)
                .as_posix(),
                "preregistration_lock_path": (iteration / "phase-one-preregistration-lock.json")
                .relative_to(root)
                .as_posix(),
            }
            if any(research_design.get(name) != value for name, value in expected_design.items()):
                raise ValueError(
                    f"development recovery candidate spec binding drift: {candidate_id}"
                )
            expected_parameter_space = {
                "candidate_id": [candidate_id],
                "method_variant": [blueprint.method_variant],
                "factor_variant": [blueprint.factor_variant],
                "parameter_search": [False],
            }
            if research_design.get("parameter_space") != expected_parameter_space:
                raise ValueError(
                    f"development recovery candidate parameter identity mismatch: {candidate_id}"
                )
            expected_notes = {
                "campaign_id": CAMPAIGN_ID,
                "candidate_id": candidate_id,
                "hypothesis_id": blueprint.hypothesis_id,
                "branch_id": blueprint.branch_id,
                "method": blueprint.method_variant,
                "factor_variant": blueprint.factor_variant,
                "archive_descriptors": dict(blueprint.archive_descriptors),
                "candidate_policy": policy,
            }
            if any(notes.get(name) != value for name, value in expected_notes.items()):
                raise ValueError(
                    f"development recovery candidate spec semantics drift: {candidate_id}"
                )

            mechanism = str(blueprint.archive_descriptors.get("mechanism_family") or "")
            development_partition_path = iteration / "development-partition-contract.json"
            expected_candidate = {
                "ablation": blueprint.factor_variant,
                "archive_descriptors": dict(blueprint.archive_descriptors),
                "benchmark_contract": contract_ids["benchmark_contract"],
                "branch_id": blueprint.branch_id,
                "campaign_id": CAMPAIGN_ID,
                "candidate_id": candidate_id,
                "candidate_policy_contract": contract_ids["candidate_policy_contract"],
                "candidate_policy_sha256": policy_sha256,
                "child_iteration_id": iter_id,
                "cost_contract": contract_ids["cost_contract"],
                "data_contract": contract_ids["data_contract"],
                "development_partition_contract_path": development_partition_path.relative_to(
                    root
                ).as_posix(),
                "development_partition_contract_sha256": _sha256(development_partition_path),
                "fallback": policy.get("fallback_symbol"),
                "feature_contract": contract_ids["feature_contract"],
                "hypothesis_id": blueprint.hypothesis_id,
                "label_contract": contract_ids["label_contract"],
                "method": blueprint.method_variant,
                "path": mechanism,
                "promotion_eligible": blueprint.promotion_eligible,
                "quality_metric": contract.qd_archive.quality_metric,
                "role": "deterministic_mechanism_candidate",
                "spec_path": spec_relative,
                "universe_contract_path": universe_path.relative_to(root).as_posix(),
                "universe_contract_sha256": _sha256(universe_path),
                "validation_contract": contract_ids["validation_contract"],
            }
            if candidate != expected_candidate:
                raise ValueError(
                    f"development recovery candidate manifest semantics mismatch: {candidate_id}"
                )
            expected_candidates.append(expected_candidate)

        expected_manifest = {
            "schema_version": 2,
            "manifest_type": "generic_candidate_family_v1",
            "campaign_id": CAMPAIGN_ID,
            "iter_id": iter_id,
            "generated_at": lock["created_at"],
            "generated_before_backtest": True,
            "model_training_authorized": False,
            "candidate_count": len(expected_candidates),
            "trial_accounting": expected_trial_accounting,
            "spec_hashes": expected_spec_hashes,
            "contracts": groups,
            "candidates": expected_candidates,
        }
        if manifest != expected_manifest:
            raise ValueError(f"development recovery exact candidate manifest mismatch: {iter_id}")

        expected_manifest_path = manifest_path.relative_to(root).as_posix()
        expected_feasibility_path = feasibility_path.relative_to(root).as_posix()
        expected_search_contracts = {
            "benchmark": inventory["benchmark_contract"]["path"],
            "candidate_policy": inventory["candidate_policy_contract"]["path"],
            "cost": inventory["cost_contract"]["path"],
            "cumulative_trial": inventory["cumulative_trial_contract"]["path"],
            "data": inventory["data_contract"]["path"],
            "development_partition": inventory["development_partition_contract"]["path"],
            "feature": inventory["feature_contract"]["path"],
            "holdout": inventory["holdout_contract"]["path"],
            "label": inventory["label_contract"]["path"],
            "universe": universe_path.relative_to(root).as_posix(),
            "validation": inventory["validation_contract"]["path"],
        }
        path_names = sorted({str(row["path"]) for row in expected_candidates})
        expected_search_paths = [
            {
                "benchmark_family": list(BENCHMARK_FAMILY_IDS),
                "candidate_count": len(expected_candidates),
                "hypothesis_refs": sorted({row.hypothesis_id for row in blueprints}),
                "name": path_names[0],
                "parameters": {
                    "candidate_ids": expected_ids,
                    "factor_variants": [row.factor_variant for row in blueprints],
                    "method_variants": [row.method_variant for row in blueprints],
                    "model_training": False,
                    "mutation": "none",
                },
            }
        ]
        first_spec_path = str(expected_candidates[0]["spec_path"])
        evaluation_root = ITERATION_ROOT / iter_id / "evaluation-run"
        expected_search_space = {
            "adaptive_selection_disclosure": ADAPTIVE_SELECTION_DISCLOSURE,
            "campaign_contract_path": (
                CAMPAIGN_ROOT / "research-campaign-contract.json"
            ).as_posix(),
            "campaign_contract_sha256": attempt["campaign_contract_sha256"],
            "campaign_id": CAMPAIGN_ID,
            "candidate_manifest_contract": "generic_candidate_family_v1",
            "candidate_manifest_path": expected_manifest_path,
            "candidate_manifest_sha256": _sha256(manifest_path),
            "contracts": expected_search_contracts,
            "cost_table_path": inventory["cost_contract"]["path"],
            "created_at": lock["created_at"],
            "cumulative_trial_count": expected_trial_accounting["minimum_effective_trial_count"],
            "cumulative_trial_count_semantics": (
                "preregistered_minimum_before_allocation_ledger_seal"
            ),
            "data_feasibility_path": expected_feasibility_path,
            "data_feasibility_sha256": _sha256(feasibility_path),
            "evaluation_report_paths": [(evaluation_root / "evaluation-report.json").as_posix()],
            "iter_id": iter_id,
            "knowledge_contract": {
                "assessment_path": (iteration / "knowledge-assessment.json")
                .relative_to(root)
                .as_posix(),
                "modality_role_matrix_path": inventory["modality_role_matrix"]["path"],
                "model_reuse_decision_path": (iteration / "model-reuse-decision.json")
                .relative_to(root)
                .as_posix(),
                "required_visibility_partitions": [
                    "public_literature",
                    "train_only_empirical",
                    "challenge_result",
                    "forward_observation",
                ],
                "scout_path": (iteration / "knowledge-scout.json").relative_to(root).as_posix(),
            },
            "objective": primary_objective,
            "paths": expected_search_paths,
            "schema_version": 3,
            "source_spec_path": first_spec_path,
            "spec_hash": expected_spec_hashes[first_spec_path],
            "strategy_name": primary_spec_name,
            "total_candidate_budget": len(blueprints),
            "trial_accounting": expected_trial_accounting,
            "trial_ledger_paths": [(evaluation_root / "trial-ledger.jsonl").as_posix()],
        }
        if (
            path_names != [str(blueprints[0].archive_descriptors["mechanism_family"])]
            or search_space != expected_search_space
        ):
            raise ValueError(f"development recovery search-space identity mismatch: {iter_id}")

        staging = iteration / f"evaluation-run.staging-{attempt['run_token']}"
        final = iteration / "evaluation-run"
        evaluation_sources = [path for path in (staging, final) if path.exists()]
        if len(evaluation_sources) != int(authorized):
            raise ValueError(
                f"development recovery authorization/evaluation custody mismatch: {iter_id}"
            )
        blueprint = blueprints[0]
        hypothesis = hypotheses[blueprint.hypothesis_id]
        if not authorized and hypothesis.universe_selection != "point_in_time":
            raise ValueError(
                f"development recovery unexpected dependency-skipped mechanism: {iter_id}"
            )
        expected_action = "evaluate" if authorized else "dependency_skipped"
        expected_reason = (
            "complete_bound_development_panel"
            if authorized
            else "point_in_time_universe_dependency_missing_fail_closed"
        )
        expected_scope = (
            "development_train_and_development_validation_only"
            if authorized
            else "no_evaluation_until_dependency_is_resolved"
        )
        expected_authorization_rows = [
            {
                "action": expected_action,
                "candidate_binding_sha256": candidate_authorization_binding_sha256(candidate),
                "candidate_id": candidate["candidate_id"],
                "path": candidate["path"],
                "reason_code": expected_reason,
            }
            for candidate in expected_candidates
        ]
        expected_accounting = {
            "balanced": True,
            "dependency_skipped_count": 0 if authorized else len(expected_candidates),
            "evaluation_authorized_count": len(expected_candidates) if authorized else 0,
            "frozen_candidate_count": len(expected_candidates),
            "unresolved_count": 0,
        }
        expected_path_gates = {
            path_name: {
                "action": expected_action,
                "candidate_ids": [
                    row["candidate_id"] for row in expected_candidates if row["path"] == path_name
                ],
                "historical_evaluation_go": authorized,
                "scope": expected_scope,
            }
            for path_name in path_names
        }
        expected_references = _expected_feasibility_references(
            root,
            iteration=iteration,
            immutable_inventory=inventory,
            phase_one_lock=phase_one_locks[iter_id],
        )
        expected_feasibility = {
            "blockers": [
                *(PIT_DEPENDENCY_BLOCKERS if not authorized else ()),
                *DEVELOPMENT_STAGE_BLOCKERS,
            ],
            "broker_writes": False,
            "campaign_id": CAMPAIGN_ID,
            "campaign_universe": {
                "capability_ids": ["market.alpaca_bars"],
                "status": dependency_status,
                "universe_selection": hypothesis.universe_selection,
            },
            "candidate_accounting": expected_accounting,
            "candidate_authorization": {
                "candidate_count": len(candidates),
                "rows": expected_authorization_rows,
            },
            "conclusion": (
                "development_evaluation_authorized"
                if authorized
                else "dependency_skipped_fail_closed"
            ),
            "generated_at": lock["created_at"],
            "generated_before_backtest": True,
            "generated_before_model_training": True,
            "historical_evaluation_authorized": authorized,
            "historical_positive_alpha_claim_authorized": False,
            "iter_id": iter_id,
            "llm_contribution_pass": False,
            "paper_ready_pass": False,
            "path_gates": expected_path_gates,
            "report_type": "mom_breadth_qd_r1_candidate_data_feasibility",
            "required_reference_names": sorted(expected_references),
            "required_references": expected_references,
            "research_pass": False,
            "schema_version": 1,
            "workflow_pass": True,
        }
        if feasibility != expected_feasibility:
            raise ValueError(f"development recovery data-feasibility semantics mismatch: {iter_id}")
        _verify_feasibility_references(
            root,
            iter_id=iter_id,
            feasibility=feasibility,
            phase_one_lock=phase_one_locks[iter_id],
            expected_references=expected_references,
        )

        expected_universe_binding = {
            "path": expected_feasibility_path,
            "sha256": _sha256(feasibility_path),
        }
        expected_universe_contract: dict[str, Any] = {
            "campaign_id": CAMPAIGN_ID,
            "capability_ids": ["market.alpaca_bars"],
            "child_iteration_id": iter_id,
            "contract_id": f"{iter_id}_universe_v1",
            "contract_status": dependency_status,
            "data_feasibility_binding": expected_universe_binding,
            "hypothesis_id": blueprint.hypothesis_id,
            "promotion_eligible": blueprint.promotion_eligible,
            "schema_version": 1,
            "universe_selection": hypothesis.universe_selection,
        }
        if authorized:
            membership_mode = {
                "fixed_long_lived": "fixed_long_lived_symbols",
                "cross_asset": "fixed_cross_asset_symbols",
                "static_hotspot_control": "static_hotspot_control",
            }.get(hypothesis.universe_selection)
            if membership_mode is None:
                raise ValueError(f"development recovery unsupported ready universe: {iter_id}")
            expected_universe_contract["universe_definition"] = {
                "membership_mode": membership_mode,
                "selection_frozen_at": lock["created_at"],
                "selection_rule": (
                    "campaign_preregistered_fixed_symbol_inventory_no_post_result_substitution"
                ),
                "survivorship_bias_control_only": (
                    iter_id == "mom_breadth_static_hotspot_control_r1"
                ),
                "symbols": list(expected_universe or ()),
            }
        else:
            expected_universe_contract["blockers"] = list(PIT_DEPENDENCY_BLOCKERS)
        if universe_contract != expected_universe_contract:
            raise ValueError(f"development recovery exact universe contract mismatch: {iter_id}")

        _validate_recovery_iteration_dossier_gate(
            iter_id,
            root,
            dependency_skipped=not authorized,
        )
        if authorized:
            evaluated_count += len(expected_candidates)

    return evaluated_count


def _validate_recovery_amendment(
    root: Path,
    *,
    contract: ResearchCampaignContract,
    attempt: Mapping[str, Any],
    attempt_binding: Mapping[str, str],
    run_token: str,
    authorized_branch_count: int,
) -> dict[str, str]:
    path = root / DEVELOPMENT_RECOVERY_AMENDMENT_PATH
    amendment = _read_json(path)
    failure = amendment.get("failure")
    prior = amendment.get("prior_implementation")
    repaired = amendment.get("repaired_implementation")
    recovery = amendment.get("recovery_contract")
    status = amendment.get("status_before_repair")
    staged_evidence = amendment.get("staged_evidence_inventory")
    preregistration_evidence = amendment.get("preregistration_evidence_inventory")
    if (
        set(amendment)
        != {
            "schema_version",
            "campaign_id",
            "reason",
            "failure",
            "prior_implementation",
            "repaired_implementation",
            "recovery_contract",
            "status_before_repair",
            "staged_evidence_inventory",
            "preregistration_evidence_inventory",
            "authorized_changes",
            "forbidden_changes",
        }
        or amendment.get("schema_version") != 1
        or amendment.get("campaign_id") != CAMPAIGN_ID
        or amendment.get("reason") != RECOVERY_AMENDMENT_REASON
        or not isinstance(failure, dict)
        or set(failure)
        != {
            "run_token",
            "attempt",
            "stage",
            "exception_type",
            "exception_message",
        }
        or failure.get("run_token") != run_token
        or failure.get("attempt") != dict(attempt_binding)
        or failure.get("stage") != "campaign_qd_archive_serialization"
        or failure.get("exception_type") != "AttributeError"
        or failure.get("exception_message")
        != "'QualityDiversityArchive' object has no attribute 'to_dict'"
        or not isinstance(prior, dict)
        or set(prior) != {"development_runner", "development_runner_tests"}
        or not isinstance(repaired, dict)
        or set(repaired) != {"development_runner", "development_runner_tests"}
        or not isinstance(recovery, dict)
        or not isinstance(status, dict)
        or not isinstance(staged_evidence, dict)
        or not isinstance(preregistration_evidence, dict)
    ):
        raise ValueError("development publication recovery amendment identity mismatch")
    for name in ("development_runner", "development_runner_tests"):
        expected_prior = attempt.get("implementation", {}).get(name)
        expected_path = LOCKED_IMPLEMENTATION_PATHS[name]
        expected_repaired = {
            "path": expected_path.as_posix(),
            "sha256": _sha256(root / expected_path),
        }
        if prior.get(name) != expected_prior or repaired.get(name) != expected_repaired:
            raise ValueError(f"development recovery implementation identity mismatch: {name}")
    expected_recovery = {
        "run_token": run_token,
        "attempt_sha256": attempt_binding["sha256"],
        "staged_evidence_only": True,
        "candidate_simulation_count": 0,
        "market_return_evaluation_count": 0,
        "incremental_effective_trial_count": 0,
        "frozen_oos_rows_read": 0,
        "model_training_count": 0,
        "simulation_or_paper_activity": False,
        "broker_writes": False,
    }
    if recovery != expected_recovery:
        raise ValueError("development publication recovery contract mismatch")
    expected_status = {
        "attempt_present": True,
        "campaign_staging_present": True,
        "branch_staging_count": authorized_branch_count,
        "candidate_metrics_count": int(attempt["evaluated_candidate_count"]),
        "final_evaluation_present": False,
        "completion_receipt_present": False,
        "frozen_oos_rows_read": 0,
        "model_training_count": 0,
        "broker_writes": False,
    }
    if status != expected_status:
        raise ValueError("development publication pre-recovery status mismatch")
    actual_staged_evidence = _staged_evidence_inventory_binding(
        root,
        contract=contract,
        run_token=run_token,
    )
    if staged_evidence != actual_staged_evidence:
        raise ValueError("development publication staged evidence SHA-256 mismatch")
    actual_preregistration_evidence = _recovery_preregistration_inventory_binding(
        root,
        contract=contract,
    )
    if preregistration_evidence != actual_preregistration_evidence:
        raise ValueError("development publication preregistration evidence SHA-256 mismatch")
    if amendment.get("authorized_changes") != list(RECOVERY_AUTHORIZED_CHANGES) or amendment.get(
        "forbidden_changes"
    ) != list(RECOVERY_FORBIDDEN_CHANGES):
        raise ValueError("development publication recovery amendment scope is missing")
    return {
        "path": DEVELOPMENT_RECOVERY_AMENDMENT_PATH.as_posix(),
        "sha256": _sha256(path),
    }


def _validate_recovery_locked_state(
    root: Path,
    *,
    contract: ResearchCampaignContract,
    attempt: Mapping[str, Any],
) -> None:
    implementation = attempt.get("implementation")
    if not isinstance(implementation, dict) or set(implementation) != set(
        LOCKED_IMPLEMENTATION_PATHS
    ):
        raise ValueError("development attempt implementation inventory mismatch")
    mutable_names = {"development_runner", "development_runner_tests"}
    for name, relative in LOCKED_IMPLEMENTATION_PATHS.items():
        binding = implementation.get(name)
        if not isinstance(binding, dict) or binding.get("path") != relative.as_posix():
            raise ValueError(f"development attempt implementation binding mismatch: {name}")
        if name not in mutable_names:
            _verify_binding(root, binding)

    phase_one_locks = attempt.get("phase_one_locks")
    if not isinstance(phase_one_locks, dict) or set(phase_one_locks) != set(
        contract.child_iteration_ids
    ):
        raise ValueError("development attempt phase-one lock inventory mismatch")
    expected_ids_by_iteration = {
        iter_id: [
            row.candidate_id
            for row in contract.candidate_blueprints
            if row.child_iteration_id == iter_id
        ]
        for iter_id in contract.child_iteration_ids
    }
    mutable_paths = {
        LOCKED_IMPLEMENTATION_PATHS[name].as_posix(): implementation[name] for name in mutable_names
    }
    for iter_id in contract.child_iteration_ids:
        binding = phase_one_locks[iter_id]
        expected_path = ITERATION_ROOT / iter_id / "phase-one-preregistration-lock.json"
        if not isinstance(binding, dict) or binding.get("path") != expected_path.as_posix():
            raise ValueError(f"development recovery phase-one lock path mismatch: {iter_id}")
        lock_path = _verify_binding(root, binding)
        lock = _read_json(lock_path)
        inventory = lock.get("immutable_inventory")
        if (
            lock.get("campaign_id") != CAMPAIGN_ID
            or lock.get("iter_id") != iter_id
            or lock.get("candidate_ids") != expected_ids_by_iteration[iter_id]
            or not isinstance(inventory, dict)
        ):
            raise ValueError(f"development recovery phase-one lock identity mismatch: {iter_id}")
        for item in inventory.values():
            if not isinstance(item, dict):
                raise ValueError(f"development recovery lock binding is malformed: {iter_id}")
            raw_path = str(item.get("path") or "")
            if raw_path in mutable_paths:
                if item != mutable_paths[raw_path]:
                    raise ValueError(
                        f"development recovery prior implementation drift: {iter_id}:{raw_path}"
                    )
            else:
                _verify_binding(root, item)


def _validate_recovery_attempt(
    root: Path,
    *,
    run_token: str,
    attempt_sha256: str,
    contract: ResearchCampaignContract,
) -> tuple[dict[str, Any], dict[str, str], str]:
    if len(run_token) != 32 or any(character not in "0123456789abcdef" for character in run_token):
        raise ValueError("development recovery run token is invalid")
    if not _is_sha256(attempt_sha256):
        raise ValueError("development recovery attempt SHA-256 is invalid")
    attempt_path = root / DEVELOPMENT_ATTEMPT_PATH
    if not attempt_path.is_file() or attempt_path.is_symlink():
        raise FileNotFoundError(attempt_path)
    actual_attempt_sha256 = _sha256(attempt_path)
    if actual_attempt_sha256 != attempt_sha256:
        raise ValueError("development recovery attempt SHA-256 mismatch")
    attempt = _read_json(attempt_path)
    campaign_contract_path = root / CAMPAIGN_ROOT / "research-campaign-contract.json"
    campaign_contract_sha256 = _sha256(campaign_contract_path)
    _validate_recovery_locked_state(root, contract=contract, attempt=attempt)
    evaluated_count = _validate_recovery_preregistration_state(
        root,
        contract=contract,
        attempt=attempt,
    )
    effective_trial_count = _development_effective_trial_count(
        contract,
        evaluated_candidate_count=evaluated_count,
    )
    expected = {
        "schema_version": 1,
        "campaign_id": CAMPAIGN_ID,
        "status": "reserved_before_development_market_data_read",
        "one_shot": True,
        "run_token": run_token,
        "campaign_contract_sha256": campaign_contract_sha256,
        "registered_candidate_count": contract.exposure_budgets.candidate_budget,
        "evaluated_candidate_count": evaluated_count,
        "cost_views_bps": list(COST_VIEWS),
        "incremental_effective_trial_count": effective_trial_count
        - contract.exposure_budgets.prior_effective_trial_count,
        "effective_trial_count": effective_trial_count,
        "frozen_oos_rows_read": 0,
        "frozen_oos_read_authorized": False,
        "model_training_count": 0,
        "broker_writes": False,
    }
    if any(attempt.get(name) != value for name, value in expected.items()):
        raise ValueError("development recovery attempt identity mismatch")
    return (
        attempt,
        {"path": DEVELOPMENT_ATTEMPT_PATH.as_posix(), "sha256": actual_attempt_sha256},
        campaign_contract_sha256,
    )


def _staged_calendar_dates(root: Path, attempt: Mapping[str, Any]) -> list[str]:
    phase_one_locks = attempt["phase_one_locks"]
    first_binding = next(iter(phase_one_locks.values()))
    lock = _read_json(_verify_binding(root, first_binding))
    calendar_binding = lock["immutable_inventory"]["exchange_calendar_artifact"]
    calendar = _read_json(_verify_binding(root, calendar_binding))
    sessions = [str(value) for value in calendar.get("sessions", [])]
    if not sessions or sessions != sorted(set(sessions)):
        raise ValueError("development recovery session calendar mismatch")
    return sessions


def _staged_validation_dates(root: Path, attempt: Mapping[str, Any]) -> list[str]:
    dates = [
        str(value)
        for value in _staged_calendar_dates(root, attempt)
        if VALIDATION_START.isoformat() <= str(value) <= VALIDATION_END.isoformat()
    ]
    if (
        len(dates) != 753
        or dates[0] != VALIDATION_START.isoformat()
        or dates[-1] != VALIDATION_END.isoformat()
        or dates != sorted(set(dates))
    ):
        raise ValueError("development recovery validation calendar mismatch")
    return dates


def _validate_staged_signal_log(
    path: Path,
    *,
    session_dates: list[str] | None = None,
    allowed_symbols: tuple[str, ...] | None = None,
) -> None:
    rows = _read_jsonl(path)
    if not rows:
        raise ValueError(f"staged signal log is empty: {path}")
    signal_ids: set[str] = set()
    previous_execution: str | None = None
    session_positions = (
        {session: offset for offset, session in enumerate(session_dates)}
        if session_dates is not None
        else None
    )
    for row in rows:
        signal_id = str(row.get("signal_id") or "")
        weights = row.get("target_weights")
        if (
            row.get("schema_version") != 1
            or row.get("broker_writes") is not False
            or not _is_sha256(signal_id)
            or signal_id in signal_ids
            or not isinstance(weights, dict)
            or not weights
            or any(not math.isfinite(float(value)) for value in weights.values())
        ):
            raise ValueError(f"staged signal log identity mismatch: {path}")
        signal_ids.add(signal_id)
        if session_positions is None or allowed_symbols is None:
            continue
        expected_keys = {
            "schema_version",
            "execution_session",
            "decision_session",
            "target_weights",
            "one_way_turnover",
            "broker_writes",
            "signal_id",
        }
        execution = str(row.get("execution_session") or "")
        decision = str(row.get("decision_session") or "")
        turnover = float(row.get("one_way_turnover", math.nan))
        weights = {str(symbol): float(value) for symbol, value in weights.items()}
        identity = dict(row)
        identity.pop("signal_id", None)
        execution_position = session_positions.get(execution)
        if (
            set(row) != expected_keys
            or execution_position is None
            or execution_position == 0
            or session_dates[execution_position - 1] != decision
            or execution < VALIDATION_START.isoformat()
            or execution > VALIDATION_END.isoformat()
            or (previous_execution is not None and execution <= previous_execution)
            or set(weights) - set(allowed_symbols)
            or any(value < 0.0 for value in weights.values())
            or not math.isclose(math.fsum(weights.values()), 1.0, rel_tol=0.0, abs_tol=1e-12)
            or not math.isfinite(turnover)
            or not 0.0 <= turnover <= 2.0 + 1e-12
            or _canonical_sha256(identity) != signal_id
        ):
            raise ValueError(f"staged signal log semantic mismatch: {path}")
        previous_execution = execution


def _validate_staged_candidate_metrics(
    *,
    contract: ResearchCampaignContract,
    fold_contract: Mapping[str, Any],
    metrics: Mapping[str, Any],
    result_returns: pd.Series,
    candidate_id: str,
    iter_id: str,
    spec_path: str,
    promotion_eligible: bool,
    attempt_binding: Mapping[str, str],
    quality_metric: str,
    effective_trial_count: int,
) -> None:
    gates = metrics.get("development_gate_diagnostics")
    cost_views = metrics.get("cost_views")
    if (
        metrics.get("schema_version") != 1
        or metrics.get("campaign_id") != CAMPAIGN_ID
        or metrics.get("iter_id") != iter_id
        or metrics.get("candidate_id") != candidate_id
        or metrics.get("spec_path") != spec_path
        or metrics.get("promotion_eligible") is not promotion_eligible
        or metrics.get("visibility_partition") != "development_validation"
        or metrics.get("workflow_pass") is not True
        or metrics.get("research_pass") is not False
        or metrics.get("paper_ready_pass") is not False
        or metrics.get("development_evaluation_attempt") != dict(attempt_binding)
        or metrics.get("frozen_oos_rows_read") != 0
        or metrics.get("broker_writes") is not False
        or metrics.get("row_count") != len(result_returns)
        or metrics.get("first_return_session") != VALIDATION_START.isoformat()
        or metrics.get("last_return_session") != VALIDATION_END.isoformat()
        or metrics.get("terminal_liquidation_in_metrics") is not False
        or metrics.get("return_stream_identity")
        != "continuous_daily_open_to_open_net_returns_terminal_free"
        or metrics.get("primary_cost_bps") != PRIMARY_COST_BPS
        or metrics.get("development_dsr_effective_trial_count") != effective_trial_count
        or metrics.get("quality_metric") != quality_metric
        or not math.isfinite(float(metrics.get("quality", math.nan)))
        or not math.isfinite(float(metrics.get("annualized_sharpe_excess_bil", math.nan)))
        or not 0.0 <= float(metrics.get("development_dsr_probability_diagnostic", math.nan)) <= 1.0
        or not isinstance(gates, dict)
        or not gates
        or any(not isinstance(value, bool) for value in gates.values())
        or metrics.get("all_development_gate_diagnostics_pass") is not all(gates.values())
        or not isinstance(cost_views, dict)
        or set(cost_views) != {str(cost) for cost in COST_VIEWS}
    ):
        raise ValueError(f"staged candidate metrics identity mismatch: {candidate_id}")
    primary = cost_views[str(PRIMARY_COST_BPS)]
    expected_primary = {
        "cagr": _cagr(result_returns),
        "total_return": _compound(result_returns),
        "max_drawdown": _max_drawdown(result_returns),
    }
    if not isinstance(primary, dict) or any(
        not math.isclose(
            float(primary.get(name, math.nan)),
            value,
            rel_tol=1e-12,
            abs_tol=1e-12,
        )
        for name, value in expected_primary.items()
    ):
        raise ValueError(f"staged primary return metrics mismatch: {candidate_id}")

    # Public recovery always loads the strict contract. Lightweight test doubles stop
    # after validating the file graph and primary return identity.
    if not isinstance(contract, ResearchCampaignContract):
        return

    fold_values, expected_fold_summaries = _fold_returns(result_returns, fold_contract)
    fold_excess = metrics.get("fold_excess_sharpes")
    expected_fold_ids = [str(row["fold_id"]) for row in expected_fold_summaries]
    if (
        metrics.get("folds") != expected_fold_summaries
        or not isinstance(fold_excess, dict)
        or list(fold_excess) != expected_fold_ids
        or any(not math.isfinite(float(value)) for value in fold_excess.values())
        or not math.isclose(
            float(metrics["quality"]),
            min(float(value) for value in fold_excess.values()),
            rel_tol=1e-12,
            abs_tol=1e-12,
        )
    ):
        raise ValueError(f"staged candidate fold or quality mismatch: {candidate_id}")

    promotion = metrics.get("promotion_metric_diagnostics")
    benchmark_metrics = metrics.get("benchmark_metrics")
    required_promotion = {
        "cagr",
        "cagr_excess_qqq",
        "tqqq_cagr_capture",
        "tqqq_upside_capture",
        "tqqq_downside_capture",
        "max_drawdown",
        "mar",
        "positive_fold_count",
        "stress_total_return",
    }
    if (
        not isinstance(promotion, dict)
        or set(promotion) != required_promotion
        or any(not math.isfinite(float(value)) for value in promotion.values())
        or not isinstance(benchmark_metrics, dict)
        or set(benchmark_metrics)
        != set(contract.candidate_promotion_policy.required_benchmark_roles)
    ):
        raise ValueError(f"staged promotion or benchmark inventory mismatch: {candidate_id}")
    growth = benchmark_metrics.get("growth_proxy")
    leveraged = benchmark_metrics.get("leveraged_growth_proxy")
    stress = cost_views[str(COST_VIEWS[-1])]
    if (
        not isinstance(growth, dict)
        or not isinstance(leveraged, dict)
        or not isinstance(stress, dict)
    ):
        raise ValueError(f"staged promotion benchmark metrics are malformed: {candidate_id}")
    cagr = expected_primary["cagr"]
    max_drawdown = expected_primary["max_drawdown"]
    derived_promotion = {
        "cagr": cagr,
        "cagr_excess_qqq": cagr - float(growth.get("cagr", math.nan)),
        "tqqq_cagr_capture": cagr / float(leveraged.get("cagr", math.nan)),
        "max_drawdown": max_drawdown,
        "mar": cagr / abs(max_drawdown),
        "positive_fold_count": sum(_compound(pd.Series(values)) > 0.0 for values in fold_values),
        "stress_total_return": float(stress.get("total_return", math.nan)),
    }
    if any(
        not math.isclose(
            float(promotion.get(name, math.nan)),
            float(value),
            rel_tol=1e-12,
            abs_tol=1e-12,
        )
        for name, value in derived_promotion.items()
    ):
        raise ValueError(f"staged promotion metric recomputation mismatch: {candidate_id}")

    expected_gates = _promotion_passes(
        promotion,
        float(metrics["annualized_sharpe_excess_bil"]),
        float(metrics["development_dsr_probability_diagnostic"]),
        contract,
    )
    if gates != expected_gates:
        raise ValueError(f"staged development gate recomputation mismatch: {candidate_id}")


def _load_validated_staged_results(
    root: Path,
    *,
    contract: ResearchCampaignContract,
    attempt: dict[str, Any],
    attempt_binding: dict[str, str],
    run_token: str,
    amendment_binding: dict[str, str],
    campaign_contract_sha256: str,
    completed: bool = False,
) -> StagedDevelopmentRecovery:
    campaign_staging = root / CAMPAIGN_ROOT / f"development-evaluation.staging-{run_token}"
    campaign_stages = sorted((root / CAMPAIGN_ROOT).glob("development-evaluation.staging-*"))
    campaign_names = {
        "qd-archive.json",
        "allocation-ledger.jsonl",
        "development-evaluation-report.json",
        DEVELOPMENT_RECEIPT_PATH.name,
    }
    if not completed:
        if campaign_stages != [campaign_staging] or campaign_staging.is_symlink():
            raise ValueError("development recovery campaign staging identity mismatch")
        staged_campaign_names = {path.name for path in campaign_staging.iterdir()}
        if staged_campaign_names - campaign_names or any(
            path.is_symlink() or not path.is_file() for path in campaign_staging.iterdir()
        ):
            raise ValueError("development recovery campaign staging contains unexpected files")
        for name in campaign_names:
            staged_path = campaign_staging / name
            final_path = root / CAMPAIGN_ROOT / name
            if staged_path.exists() and final_path.exists():
                raise FileExistsError(
                    f"development recovery campaign file has dual custody: {name}"
                )
        if (root / DEVELOPMENT_RECEIPT_PATH).exists():
            raise FileExistsError("development recovery completion receipt already exists")

    session_dates = _staged_calendar_dates(root, attempt)
    dates = [
        value
        for value in session_dates
        if VALIDATION_START.isoformat() <= value <= VALIDATION_END.isoformat()
    ]
    if dates != _staged_validation_dates(root, attempt):
        raise ValueError("development recovery validation date derivation mismatch")
    index = pd.DatetimeIndex(pd.to_datetime(dates))
    blueprints = {row.candidate_id: row for row in contract.candidate_blueprints}
    evaluated: list[CandidateDevelopmentResult] = []
    excluded: list[str] = []
    branch_reports: dict[str, Any] = {}
    branch_staging: dict[str, Path] = {}
    partition_contract_sha256_by_iter: dict[str, str] = {}
    total_trial_exposure = 0.0

    for iter_id in contract.child_iteration_ids:
        iteration = root / ITERATION_ROOT / iter_id
        manifest = _read_json(iteration / "candidate-manifest.json")
        candidates = manifest.get("candidates")
        if not isinstance(candidates, list):
            raise ValueError(f"staged recovery candidate manifest is malformed: {iter_id}")
        expected_ids = [
            blueprint.candidate_id
            for blueprint in contract.candidate_blueprints
            if blueprint.child_iteration_id == iter_id
        ]
        if [str(row.get("candidate_id")) for row in candidates] != expected_ids:
            raise ValueError(f"staged recovery candidate inventory mismatch: {iter_id}")
        feasibility = _read_json(iteration / "data-feasibility.json")
        authorized = feasibility.get("historical_evaluation_authorized") is True
        stage = iteration / f"evaluation-run.staging-{run_token}"
        stages = sorted(iteration.glob("evaluation-run.staging-*"))
        final = iteration / "evaluation-run"
        if not authorized:
            if stages or final.exists():
                raise ValueError(f"dependency-skipped branch has staged evaluation: {iter_id}")
            excluded.extend(expected_ids)
            branch_reports[iter_id] = {
                "status": "dependency_skipped",
                "evaluated_count": 0,
                "evaluation_artifacts_written": False,
            }
            continue
        if completed:
            if stages or final.is_symlink() or not final.is_dir():
                raise ValueError(
                    f"completed development recovery branch custody mismatch: {iter_id}"
                )
            source = final
        else:
            sources = [path for path in (*stages, final) if path.exists()]
            if len(sources) != 1 or sources[0] not in {stage, final} or sources[0].is_symlink():
                raise ValueError(
                    f"development recovery branch staging identity mismatch: {iter_id}"
                )
            source = sources[0]
        branch_staging[iter_id] = source
        expected_names = {
            "evaluation-report.json",
            "trial-ledger.jsonl",
            "development-return-matrix.json",
            *(f"{candidate_id}-metrics.json" for candidate_id in expected_ids),
            *(f"{candidate_id}-signal-log.jsonl" for candidate_id in expected_ids),
        }
        entries = list(source.iterdir())
        if {entry.name for entry in entries} != expected_names or any(
            entry.is_symlink() or not entry.is_file() for entry in entries
        ):
            raise ValueError(f"development recovery staged file inventory mismatch: {iter_id}")

        matrix = _read_json(source / "development-return-matrix.json")
        returns = matrix.get("returns")
        if (
            matrix.get("schema_version") != 1
            or matrix.get("campaign_id") != CAMPAIGN_ID
            or matrix.get("iter_id") != iter_id
            or matrix.get("visibility_partition") != "development_validation"
            or matrix.get("return_stream_identity")
            != "continuous_daily_open_to_open_net_returns_terminal_free"
            or matrix.get("cost_bps") != PRIMARY_COST_BPS
            or matrix.get("dates") != dates
            or matrix.get("frozen_oos_rows_read") != 0
            or not isinstance(returns, dict)
            or list(returns) != expected_ids
        ):
            raise ValueError(f"development recovery return matrix mismatch: {iter_id}")
        trials = _read_jsonl(source / "trial-ledger.jsonl")
        if [str(row.get("candidate_id")) for row in trials] != expected_ids:
            raise ValueError(f"development recovery trial inventory mismatch: {iter_id}")
        trials_by_id = {str(row["candidate_id"]): row for row in trials}
        branch_candidate_reports: dict[str, Any] = {}
        partition_contract_path = iteration / "development-partition-contract.json"
        fold_contract = (
            _read_json(partition_contract_path)
            if isinstance(contract, ResearchCampaignContract)
            else {}
        )
        partition_contract_sha256_by_iter[iter_id] = _sha256(partition_contract_path)

        for candidate_row in candidates:
            candidate_id = str(candidate_row["candidate_id"])
            blueprint = blueprints[candidate_id]
            spec_path = str(candidate_row["spec_path"])
            spec = load_strategy_spec(root / spec_path)
            allowed_symbols = tuple(str(symbol).upper() for symbol in spec.universe)
            values = returns.get(candidate_id)
            if (
                not isinstance(values, list)
                or len(values) != len(dates)
                or any(not math.isfinite(float(value)) or float(value) <= -1.0 for value in values)
            ):
                raise ValueError(f"development recovery candidate returns mismatch: {candidate_id}")
            result_returns = pd.Series(values, index=index, dtype=float)
            metrics_staging_path = source / f"{candidate_id}-metrics.json"
            metrics = _read_json(metrics_staging_path)
            metrics_sha256 = _sha256(metrics_staging_path)
            _validate_staged_candidate_metrics(
                contract=contract,
                fold_contract=fold_contract,
                metrics=metrics,
                result_returns=result_returns,
                candidate_id=candidate_id,
                iter_id=iter_id,
                spec_path=spec_path,
                promotion_eligible=blueprint.promotion_eligible,
                attempt_binding=attempt_binding,
                quality_metric=contract.qd_archive.quality_metric,
                effective_trial_count=int(attempt["effective_trial_count"]),
            )
            metrics_path = final / f"{candidate_id}-metrics.json"
            signal_path = final / f"{candidate_id}-signal-log.jsonl"
            expected_trial = _trial_row(
                candidate_id=candidate_id,
                iter_id=iter_id,
                action="evaluate",
                spec_path=spec_path,
                metrics_path=metrics_path.relative_to(root).as_posix(),
                metrics_sha256=metrics_sha256,
                effective_trial_exposure=float(len(COST_VIEWS)),
            )
            if trials_by_id[candidate_id] != expected_trial:
                raise ValueError(f"development recovery trial row mismatch: {candidate_id}")
            if metrics.get("signal_log_path") != signal_path.relative_to(root).as_posix():
                raise ValueError(f"development recovery signal path mismatch: {candidate_id}")
            _validate_staged_signal_log(
                source / signal_path.name,
                session_dates=session_dates,
                allowed_symbols=allowed_symbols,
            )
            evaluated.append(
                CandidateDevelopmentResult(
                    candidate_id=candidate_id,
                    iter_id=iter_id,
                    spec_path=spec_path,
                    promotion_eligible=blueprint.promotion_eligible,
                    quality=float(metrics["quality"]),
                    quality_metric=str(metrics["quality_metric"]),
                    returns_by_cost={PRIMARY_COST_BPS: result_returns},
                    metrics=metrics,
                    metrics_path=metrics_path.relative_to(root).as_posix(),
                    metrics_sha256=metrics_sha256,
                    signal_log_path=signal_path.relative_to(root).as_posix(),
                )
            )
            branch_candidate_reports[candidate_id] = metrics
            total_trial_exposure += float(expected_trial["effective_trial_exposure"])

        report = _read_json(source / "evaluation-report.json")
        expected_report = {
            "schema_version": 1,
            "campaign_id": CAMPAIGN_ID,
            "iter_id": iter_id,
            "workflow_pass": True,
            "research_pass": False,
            "paper_ready_pass": False,
            "status": "development_evaluated",
            "candidate_count": len(candidates),
            "evaluated_count": len(candidates),
            "candidates": branch_candidate_reports,
            "effective_trial_count": attempt["effective_trial_count"],
            "development_evaluation_attempt": attempt_binding,
            "publication_receipt_required": True,
            "publication_receipt_path": DEVELOPMENT_RECEIPT_PATH.as_posix(),
            "frozen_oos_rows_read": 0,
            "broker_writes": False,
        }
        if report != expected_report:
            raise ValueError(f"development recovery branch report mismatch: {iter_id}")
        branch_reports[iter_id] = report

    if (
        len(evaluated) != attempt["evaluated_candidate_count"]
        or len(excluded)
        != attempt["registered_candidate_count"] - attempt["evaluated_candidate_count"]
        or not math.isclose(
            total_trial_exposure,
            float(attempt["incremental_effective_trial_count"]),
        )
    ):
        raise ValueError("development recovery aggregate exposure mismatch")
    return StagedDevelopmentRecovery(
        attempt=attempt,
        attempt_binding=attempt_binding,
        amendment_binding=amendment_binding,
        campaign_contract_sha256=campaign_contract_sha256,
        campaign_staging=campaign_staging,
        branch_staging=branch_staging,
        evaluated=tuple(evaluated),
        excluded_candidate_ids=tuple(sorted(excluded)),
        branch_reports=branch_reports,
        partition_contract_sha256_by_iter=partition_contract_sha256_by_iter,
    )


def run_development_campaign(root: Path) -> dict[str, Any]:
    base = root.resolve()
    validation = validate_campaign_contract(CAMPAIGN_ID, base, stage="pre-discovery")
    if not validation.ok:
        raise ValueError(f"campaign pre-discovery gate failed: {validation.blocked}")
    contract = load_campaign_contract(CAMPAIGN_ID, base)
    _assert_pristine_publication_state(base, contract)
    contract_payload = _read_json(base / CAMPAIGN_ROOT / "research-campaign-contract.json")
    campaign_contract_sha256 = _sha256(base / CAMPAIGN_ROOT / "research-campaign-contract.json")
    phase_one_locks = _verify_runtime_lock_inventory(base, contract)

    preflight: dict[str, dict[str, Any]] = {}
    evaluated_candidate_count = 0
    exchange_calendar_binding: dict[str, Any] | None = None
    for iter_id in contract.child_iteration_ids:
        iteration = base / ITERATION_ROOT / iter_id
        manifest = _read_json(iteration / "candidate-manifest.json")
        feasibility = _read_json(iteration / "data-feasibility.json")
        data_contract = _read_json(iteration / "data-contract.json")
        policy_contract = _read_json(iteration / "candidate-policy-contract.json")
        fold_contract = _read_json(iteration / "development-partition-contract.json")
        candidates = manifest.get("candidates")
        policies = policy_contract.get("policies")
        if not isinstance(candidates, list) or not isinstance(policies, list):
            raise ValueError(f"candidate preregistration inventory is malformed: {iter_id}")
        policies_by_id = {str(row["candidate_id"]): row["policy"] for row in policies}
        if set(policies_by_id) != {str(row.get("candidate_id")) for row in candidates}:
            raise ValueError(f"candidate policy inventory mismatch: {iter_id}")
        lock = _read_json(iteration / "phase-one-preregistration-lock.json")
        if lock.get("candidate_policy_sha256") != {
            candidate_id: _canonical_sha256(policy)
            for candidate_id, policy in policies_by_id.items()
        }:
            raise ValueError(f"candidate policy lock hash mismatch: {iter_id}")
        immutable_inventory = lock.get("immutable_inventory")
        if not isinstance(immutable_inventory, dict):
            raise ValueError(f"phase-one immutable inventory is malformed: {iter_id}")
        expected_references = _expected_feasibility_references(
            base,
            iteration=iteration,
            immutable_inventory=immutable_inventory,
            phase_one_lock=phase_one_locks[iter_id],
        )
        _verify_feasibility_references(
            base,
            iter_id=iter_id,
            feasibility=feasibility,
            phase_one_lock=phase_one_locks[iter_id],
            expected_references=expected_references,
        )
        calendar_binding = data_contract.get("exchange_calendar_artifact")
        if (
            not isinstance(calendar_binding, dict)
            or data_contract.get("calendar_id") != "XNYS"
            or data_contract.get("calendar_coverage_policy") != "exact_each_symbol"
            or data_contract.get("missing_calendar_session_action") != "fail_closed"
            or data_contract.get("extra_non_session_action") != "fail_closed"
            or data_contract.get("price_intersection_as_calendar_allowed") is not False
        ):
            raise ValueError(f"data contract exchange-calendar identity mismatch: {iter_id}")
        if exchange_calendar_binding is None:
            exchange_calendar_binding = calendar_binding
        elif exchange_calendar_binding != calendar_binding:
            raise ValueError("exchange-calendar bindings differ across child iterations")
        expected_symbols: tuple[str, ...] | None = None
        for row in candidates:
            spec = load_strategy_spec(base / Path(str(row["spec_path"])))
            symbols = tuple(str(symbol).upper() for symbol in spec.universe)
            if expected_symbols is None:
                expected_symbols = symbols
            elif symbols != expected_symbols:
                raise ValueError(f"candidate spec universe order mismatch: {iter_id}")
        if expected_symbols is None:
            raise ValueError(f"candidate preregistration inventory is empty: {iter_id}")
        _validate_iteration_contract_identities(
            iter_id=iter_id,
            label_contract=_read_json(iteration / "label-contract.json"),
            cost_contract=_read_json(iteration / "cost-contract.json"),
            benchmark_contract=_read_json(iteration / "benchmark-contract.json"),
            expected_symbols=expected_symbols,
        )
        authorized = bool(feasibility.get("historical_evaluation_authorized"))
        _validate_recovery_iteration_dossier_gate(
            iter_id,
            base,
            dependency_skipped=not authorized,
        )
        if authorized:
            if feasibility.get("conclusion") != "development_evaluation_authorized":
                raise ValueError(f"authorized iteration conclusion mismatch: {iter_id}")
            evaluated_candidate_count += len(candidates)
        else:
            authorization = feasibility.get("candidate_authorization")
            rows = authorization.get("rows") if isinstance(authorization, dict) else None
            if (
                feasibility.get("conclusion") != "dependency_skipped_fail_closed"
                or not isinstance(rows, list)
                or [str(row.get("candidate_id")) for row in rows]
                != [str(row.get("candidate_id")) for row in candidates]
                or any(
                    row.get("action") != "dependency_skipped"
                    or row.get("reason_code")
                    != "point_in_time_universe_dependency_missing_fail_closed"
                    for row in rows
                )
            ):
                raise ValueError(f"unauthorized iteration is not fail-closed: {iter_id}")
        preflight[iter_id] = {
            "manifest": manifest,
            "feasibility": feasibility,
            "data_contract": data_contract,
            "policies": policies_by_id,
            "fold_contract": fold_contract,
            "authorized": authorized,
        }

    if exchange_calendar_binding is None:
        raise ValueError("campaign has no exchange-calendar binding")
    exchange_sessions = _load_development_session_calendar(
        base,
        exchange_calendar_binding,
    )

    registered_ids = {
        str(row["candidate_id"])
        for state in preflight.values()
        for row in state["manifest"]["candidates"]
    }
    expected_ids = {row.candidate_id for row in contract.candidate_blueprints}
    if registered_ids != expected_ids:
        raise ValueError("campaign candidate inventory changed before development attempt")
    effective_trial_count = _development_effective_trial_count(
        contract,
        evaluated_candidate_count=evaluated_candidate_count,
    )
    run_token = uuid4().hex
    attempt_binding = _reserve_development_attempt(
        base,
        contract=contract,
        campaign_contract_sha256=campaign_contract_sha256,
        phase_one_locks=phase_one_locks,
        evaluated_candidate_count=evaluated_candidate_count,
        effective_trial_count=effective_trial_count,
        run_token=run_token,
    )
    campaign_staging = base / CAMPAIGN_ROOT / f"development-evaluation.staging-{run_token}"
    campaign_staging.mkdir(parents=False, exist_ok=False)
    branch_staging = {
        iter_id: base / ITERATION_ROOT / iter_id / f"evaluation-run.staging-{run_token}"
        for iter_id, state in preflight.items()
        if state["authorized"]
    }
    for staging in branch_staging.values():
        staging.mkdir(parents=False, exist_ok=False)

    # No market-return bytes may be read before the one-shot attempt is reserved above.
    benchmark_panel = _load_benchmark_panel(
        base,
        contract_payload,
        exchange_sessions=exchange_sessions,
    )
    validation_index = exchange_sessions[
        (exchange_sessions >= pd.Timestamp(VALIDATION_START))
        & (exchange_sessions <= pd.Timestamp(VALIDATION_END))
    ]
    if len(validation_index) < 252:
        raise ValueError("development validation has fewer than 252 common sessions")

    blueprints = {row.candidate_id: row for row in contract.candidate_blueprints}
    evaluated: list[CandidateDevelopmentResult] = []
    excluded: list[str] = []
    branch_reports: dict[str, Any] = {}

    for iter_id in contract.child_iteration_ids:
        iteration = base / ITERATION_ROOT / iter_id
        state = preflight[iter_id]
        manifest = state["manifest"]
        feasibility = state["feasibility"]
        fold_contract = state["fold_contract"]
        policies = state["policies"]
        candidates = manifest.get("candidates")
        assert isinstance(candidates, list)
        authorized = bool(state["authorized"])
        branch_trial_rows: list[dict[str, Any]] = []
        branch_candidate_reports: dict[str, Any] = {}
        if not authorized:
            for row in candidates:
                excluded.append(str(row["candidate_id"]))
            branch_reports[iter_id] = {
                "status": "dependency_skipped",
                "evaluated_count": 0,
                "evaluation_artifacts_written": False,
            }
            continue

        staging = branch_staging[iter_id]
        destination = iteration / "evaluation-run"
        first_spec_path = Path(str(candidates[0]["spec_path"]))
        branch_panel = _load_branch_panel(
            base,
            iter_id=iter_id,
            spec_path=first_spec_path,
            exchange_sessions=exchange_sessions,
        )
        branch_exchange_sessions = exchange_sessions[
            exchange_sessions
            >= pd.Timestamp(str(state["data_contract"].get("first_session") or ""))
        ]
        primary_symbol = str(load_strategy_spec(base / first_spec_path).data.symbol).upper()
        benchmark_family = _benchmark_family(
            benchmark_panel,
            branch_panel,
            primary_symbol=primary_symbol,
            index=validation_index,
        )
        branch_returns: dict[str, list[float]] = {}
        for row in candidates:
            candidate_id = str(row["candidate_id"])
            spec_path = Path(str(row["spec_path"]))
            spec = load_strategy_spec(base / spec_path)
            if set(str(symbol).upper() for symbol in spec.universe) != set(branch_panel.symbols):
                raise ValueError(f"candidate universe identity drift: {candidate_id}")
            schedule = build_target_schedule(
                policies[candidate_id],
                branch_panel,
                exchange_sessions=branch_exchange_sessions,
            )
            simulations = {
                cost: simulate_target_schedule(branch_panel, schedule, cost_bps=cost)
                for cost in COST_VIEWS
            }
            for simulation in simulations.values():
                if not simulation.returns.index.equals(validation_index):
                    raise ValueError(f"candidate return index mismatch: {candidate_id}")
            signal_path = destination / f"{candidate_id}-signal-log.jsonl"
            signal_staging_path = staging / signal_path.name
            _write_jsonl(
                signal_staging_path,
                list(simulations[PRIMARY_COST_BPS].signal_rows),
            )
            metrics = _candidate_metrics(
                contract,
                result_by_cost=simulations,
                benchmark_family=benchmark_family,
                fold_contract=fold_contract,
                effective_trial_count=effective_trial_count,
            )
            metrics.update(
                {
                    "schema_version": 1,
                    "campaign_id": CAMPAIGN_ID,
                    "iter_id": iter_id,
                    "candidate_id": candidate_id,
                    "spec_path": spec_path.as_posix(),
                    "signal_log_path": signal_path.relative_to(base).as_posix(),
                    "visibility_partition": "development_validation",
                    "promotion_eligible": bool(blueprints[candidate_id].promotion_eligible),
                    "workflow_pass": True,
                    "research_pass": False,
                    "paper_ready_pass": False,
                    "development_evaluation_attempt": attempt_binding,
                    "frozen_oos_rows_read": 0,
                    "broker_writes": False,
                }
            )
            metrics_path = destination / f"{candidate_id}-metrics.json"
            metrics_staging_path = staging / metrics_path.name
            write_json(metrics_staging_path, metrics)
            metrics_sha256 = _sha256(metrics_staging_path)
            relative_metrics_path = metrics_path.relative_to(base).as_posix()
            evaluated.append(
                CandidateDevelopmentResult(
                    candidate_id=candidate_id,
                    iter_id=iter_id,
                    spec_path=spec_path.as_posix(),
                    promotion_eligible=bool(blueprints[candidate_id].promotion_eligible),
                    quality=float(metrics["quality"]),
                    quality_metric=str(metrics["quality_metric"]),
                    returns_by_cost={cost: simulations[cost].returns for cost in COST_VIEWS},
                    metrics=metrics,
                    metrics_path=relative_metrics_path,
                    metrics_sha256=metrics_sha256,
                    signal_log_path=signal_path.relative_to(base).as_posix(),
                )
            )
            branch_returns[candidate_id] = simulations[PRIMARY_COST_BPS].returns.to_list()
            branch_candidate_reports[candidate_id] = metrics
            trial = _trial_row(
                candidate_id=candidate_id,
                iter_id=iter_id,
                action="evaluate",
                spec_path=spec_path.as_posix(),
                metrics_path=relative_metrics_path,
                metrics_sha256=metrics_sha256,
                effective_trial_exposure=float(len(COST_VIEWS)),
            )
            branch_trial_rows.append(trial)
        _write_jsonl(staging / "trial-ledger.jsonl", branch_trial_rows)
        write_json(
            staging / "development-return-matrix.json",
            {
                "schema_version": 1,
                "campaign_id": CAMPAIGN_ID,
                "iter_id": iter_id,
                "visibility_partition": "development_validation",
                "return_stream_identity": "continuous_daily_open_to_open_net_returns_terminal_free",
                "cost_bps": PRIMARY_COST_BPS,
                "dates": [value.date().isoformat() for value in validation_index],
                "returns": branch_returns,
                "frozen_oos_rows_read": 0,
            },
        )
        report = {
            "schema_version": 1,
            "campaign_id": CAMPAIGN_ID,
            "iter_id": iter_id,
            "workflow_pass": True,
            "research_pass": False,
            "paper_ready_pass": False,
            "status": "development_evaluated",
            "candidate_count": len(candidates),
            "evaluated_count": len(candidates),
            "candidates": branch_candidate_reports,
            "effective_trial_count": effective_trial_count,
            "development_evaluation_attempt": attempt_binding,
            "publication_receipt_required": True,
            "publication_receipt_path": DEVELOPMENT_RECEIPT_PATH.as_posix(),
            "frozen_oos_rows_read": 0,
            "broker_writes": False,
        }
        write_json(staging / "evaluation-report.json", report)
        branch_reports[iter_id] = report

    qd_candidates = []
    for result in evaluated:
        blueprint = blueprints[result.candidate_id]
        partition_path = ITERATION_ROOT / result.iter_id / "development-partition-contract.json"
        qd_candidates.append(
            QualityDiversityCandidate(
                candidate_id=result.candidate_id,
                hypothesis_id=blueprint.hypothesis_id,
                branch=blueprint.branch_id,
                archive_descriptors=dict(blueprint.archive_descriptors),
                quality=result.quality,
                quality_metric=result.quality_metric,
                visibility_partition="development_validation",
                metrics_snapshot_path=result.metrics_path,
                metrics_snapshot_sha256=result.metrics_sha256,
                partition_contract_path=partition_path.as_posix(),
                partition_contract_sha256=_sha256(base / partition_path),
                promotion_eligible=result.promotion_eligible,
                resource_rung=0,
            )
        )
    archive = build_quality_diversity_archive(
        qd_candidates,
        quality_diversity_policy_from_campaign(
            contract,
            campaign_contract_sha256=campaign_contract_sha256,
        ),
        excluded_candidate_ids=excluded,
        require_complete_inventory=True,
    )
    write_json(campaign_staging / "qd-archive.json", archive.model_dump())
    elite_ids = {elite.candidate.candidate_id for elite in archive.elites}
    results_by_id = {result.candidate_id: result for result in evaluated}

    ledger = initialize_allocation_ledger(
        contract,
        campaign_contract_sha256=campaign_contract_sha256,
    )
    for blueprint in contract.candidate_blueprints:
        result = results_by_id.get(blueprint.candidate_id)
        if result is None:
            decision = "dependency_skipped"
            metrics_sha256 = hashlib.sha256(
                f"{blueprint.candidate_id}:dependency_skipped".encode("ascii")
            ).hexdigest()
            exposure = 0.0
            resource = {"deterministic_candidate_evaluations": 0.0, "cost_views": 0.0}
        else:
            diagnostics_pass = bool(result.metrics["all_development_gate_diagnostics_pass"])
            if not blueprint.promotion_eligible:
                decision = "reject"
            elif blueprint.candidate_id in elite_ids and diagnostics_pass:
                decision = "advance"
            elif blueprint.candidate_id in elite_ids:
                decision = "stop"
            else:
                decision = "prune"
            metrics_sha256 = result.metrics_sha256
            exposure = float(len(COST_VIEWS))
            resource = {"deterministic_candidate_evaluations": 1.0, "cost_views": 3.0}
        ledger = append_allocation_entry(
            ledger,
            candidate_id=blueprint.candidate_id,
            decision=decision,
            resource_used=resource,
            metrics_snapshot_sha256=metrics_sha256,
            effective_trial_exposure=exposure,
            visibility_partition="development_validation",
        )
    effective_trial_count = _verify_ledger_effective_trial_count(
        contract,
        ledger,
        precomputed_effective_trial_count=effective_trial_count,
    )
    _write_jsonl(
        campaign_staging / "allocation-ledger.jsonl",
        [entry.model_dump() for entry in ledger.entries],
    )

    advancing = [entry.candidate_id for entry in ledger.entries if entry.decision == "advance"]
    family_diagnostics = _development_family_diagnostics(
        contract,
        evaluated=evaluated,
        benchmark_returns=_fixed_initial_notional_buy_and_hold_returns(
            benchmark_panel,
            ("BIL",),
            validation_index,
            cost_bps=PRIMARY_COST_BPS,
        ),
        effective_trial_count=effective_trial_count,
    )
    advancing_returns = {
        candidate_id: results_by_id[candidate_id].returns_by_cost[PRIMARY_COST_BPS]
        for candidate_id in advancing
        if candidate_id in results_by_id
    }
    correlation_diagnostic = _advancing_pair_correlation_diagnostic(
        contract,
        advancing_returns,
    )
    pre_oos_development_ready = bool(
        family_diagnostics.get("pass") and correlation_diagnostic["pass"]
    )
    report = {
        "schema_version": 1,
        "campaign_id": CAMPAIGN_ID,
        "stage": "development_only",
        "workflow_pass": True,
        "research_pass": False,
        "paper_ready_pass": False,
        "evaluated_candidate_count": len(evaluated),
        "dependency_skipped_candidate_ids": sorted(excluded),
        "qd_elite_candidate_ids": sorted(elite_ids),
        "development_gate_advancing_candidate_ids": advancing,
        "development_family_statistics_diagnostic": family_diagnostics,
        "development_pre_oos_ready": pre_oos_development_ready,
        "effective_trial_count": effective_trial_count,
        "effective_trial_exposure": math.fsum(
            entry.effective_trial_exposure for entry in ledger.entries
        ),
        "allocation_ledger_head_sha256": ledger.head_sha256,
        "advancing_pair_correlation_diagnostic": correlation_diagnostic,
        "advancing_primary_return_correlations": correlation_diagnostic["correlations"],
        "low_correlation_absolute_maximum": correlation_diagnostic["policy"]["absolute_maximum"],
        "low_correlation_advancing_pairs": correlation_diagnostic["passing_pairs"],
        "branches": branch_reports,
        "development_evaluation_attempt": attempt_binding,
        "publication_receipt_required": True,
        "publication_receipt_path": DEVELOPMENT_RECEIPT_PATH.as_posix(),
        "frozen_oos_rows_read": 0,
        "frozen_oos_read_authorized": False,
        "model_training_count": 0,
        "broker_writes": False,
        "next_action": (
            "generate_backtest_forensics_then_prepare_pre_oos_seal_without_reading_frozen_oos"
        )
        if pre_oos_development_ready
        else (
            "do_not_open_frozen_oos_preserve_negative_development_result_"
            "and_open_independent_campaign"
        ),
    }
    write_json(campaign_staging / "development-evaluation-report.json", report)

    publication_files = []
    for iter_id, staging in sorted(branch_staging.items()):
        destination = base / ITERATION_ROOT / iter_id / "evaluation-run"
        publication_files.extend(
            _staged_publication_binding(
                path,
                destination_path=destination / path.name,
                root=base,
            )
            for path in sorted(staging.iterdir())
            if path.is_file()
        )
    for name in (
        "qd-archive.json",
        "allocation-ledger.jsonl",
        "development-evaluation-report.json",
    ):
        publication_files.append(
            _staged_publication_binding(
                campaign_staging / name,
                destination_path=base / CAMPAIGN_ROOT / name,
                root=base,
            )
        )
    receipt = {
        "schema_version": 1,
        "campaign_id": CAMPAIGN_ID,
        "published_at": datetime.now(UTC).isoformat(),
        "status": "complete",
        "completion_marker": True,
        "development_evaluation_attempt": attempt_binding,
        "campaign_contract_sha256": campaign_contract_sha256,
        "effective_trial_count": effective_trial_count,
        "evaluated_candidate_count": len(evaluated),
        "dependency_skipped_candidate_count": len(excluded),
        "publication_file_count": len(publication_files),
        "publication_files": publication_files,
        "receipt_published_last": True,
        "frozen_oos_rows_read": 0,
        "model_training_count": 0,
        "broker_writes": False,
    }
    write_json(campaign_staging / DEVELOPMENT_RECEIPT_PATH.name, receipt)
    _publish_staged_outputs(
        root=base,
        branch_staging=branch_staging,
        campaign_staging=campaign_staging,
        publication_files=publication_files,
    )
    published_receipt = _read_json(base / DEVELOPMENT_RECEIPT_PATH)
    if published_receipt != receipt:
        raise ValueError("development publication receipt identity changed")
    for binding in publication_files:
        _verify_binding(base, binding)
    return report


def _publication_recovery_evidence(
    *,
    run_token: str,
    attempt_sha256: str,
    amendment_binding: Mapping[str, str],
) -> dict[str, Any]:
    return {
        "performed": True,
        "run_token": run_token,
        "attempt_sha256": attempt_sha256,
        "amendment": dict(amendment_binding),
        "staged_evidence_only": True,
        "candidate_simulation_count": 0,
        "market_return_evaluation_count": 0,
        "incremental_effective_trial_count": 0,
        "frozen_oos_rows_read": 0,
        "model_training_count": 0,
        "simulation_or_paper_activity": False,
        "broker_writes": False,
    }


def _reconstruct_recovery_publication(
    *,
    contract: ResearchCampaignContract,
    validated_branches: StagedDevelopmentRecovery,
    attempt: Mapping[str, Any],
    attempt_binding: Mapping[str, str],
    recovery_evidence: Mapping[str, Any],
    campaign_contract_sha256: str,
) -> RecoveryCampaignOutputs:
    recovery_amendment = recovery_evidence.get("amendment")
    recovery_run_token = str(recovery_evidence.get("run_token") or "")
    if (
        validated_branches.attempt != dict(attempt)
        or validated_branches.attempt_binding != dict(attempt_binding)
        or not isinstance(recovery_amendment, Mapping)
        or validated_branches.amendment_binding != dict(recovery_amendment)
        or validated_branches.campaign_contract_sha256 != campaign_contract_sha256
        or validated_branches.campaign_staging.name
        != f"development-evaluation.staging-{recovery_run_token}"
    ):
        raise ValueError("recovery publication reconstruction input identity mismatch")

    blueprints = {row.candidate_id: row for row in contract.candidate_blueprints}
    qd_candidates = []
    for result in validated_branches.evaluated:
        blueprint = blueprints[result.candidate_id]
        partition_sha256 = validated_branches.partition_contract_sha256_by_iter.get(result.iter_id)
        if not _is_sha256(str(partition_sha256 or "")):
            raise ValueError(f"recovery partition contract binding is missing: {result.iter_id}")
        partition_path = ITERATION_ROOT / result.iter_id / "development-partition-contract.json"
        qd_candidates.append(
            QualityDiversityCandidate(
                candidate_id=result.candidate_id,
                hypothesis_id=blueprint.hypothesis_id,
                branch=blueprint.branch_id,
                archive_descriptors=dict(blueprint.archive_descriptors),
                quality=result.quality,
                quality_metric=result.quality_metric,
                visibility_partition="development_validation",
                metrics_snapshot_path=result.metrics_path,
                metrics_snapshot_sha256=result.metrics_sha256,
                partition_contract_path=partition_path.as_posix(),
                partition_contract_sha256=partition_sha256,
                promotion_eligible=result.promotion_eligible,
                resource_rung=0,
            )
        )
    archive = build_quality_diversity_archive(
        qd_candidates,
        quality_diversity_policy_from_campaign(
            contract,
            campaign_contract_sha256=campaign_contract_sha256,
        ),
        excluded_candidate_ids=validated_branches.excluded_candidate_ids,
        require_complete_inventory=True,
    )
    elite_ids = {elite.candidate.candidate_id for elite in archive.elites}
    results_by_id = {result.candidate_id: result for result in validated_branches.evaluated}

    ledger = initialize_allocation_ledger(
        contract,
        campaign_contract_sha256=campaign_contract_sha256,
    )
    for blueprint in contract.candidate_blueprints:
        result = results_by_id.get(blueprint.candidate_id)
        if result is None:
            decision = "dependency_skipped"
            metrics_sha256 = hashlib.sha256(
                f"{blueprint.candidate_id}:dependency_skipped".encode("ascii")
            ).hexdigest()
            exposure = 0.0
            resource = {"deterministic_candidate_evaluations": 0.0, "cost_views": 0.0}
        else:
            diagnostics_pass = bool(result.metrics["all_development_gate_diagnostics_pass"])
            if not blueprint.promotion_eligible:
                decision = "reject"
            elif blueprint.candidate_id in elite_ids and diagnostics_pass:
                decision = "advance"
            elif blueprint.candidate_id in elite_ids:
                decision = "stop"
            else:
                decision = "prune"
            metrics_sha256 = result.metrics_sha256
            exposure = float(len(COST_VIEWS))
            resource = {"deterministic_candidate_evaluations": 1.0, "cost_views": 3.0}
        ledger = append_allocation_entry(
            ledger,
            candidate_id=blueprint.candidate_id,
            decision=decision,
            resource_used=resource,
            metrics_snapshot_sha256=metrics_sha256,
            effective_trial_exposure=exposure,
            visibility_partition="development_validation",
        )
    effective_trial_count = _verify_ledger_effective_trial_count(
        contract,
        ledger,
        precomputed_effective_trial_count=int(attempt["effective_trial_count"]),
    )
    advancing = [entry.candidate_id for entry in ledger.entries if entry.decision == "advance"]
    if advancing:
        raise ValueError(
            "development publication recovery refuses advancing candidates because the daily "
            "benchmark return stream was not staged"
        )

    promotable_ids = sorted(
        result.candidate_id for result in validated_branches.evaluated if result.promotion_eligible
    )
    family_diagnostics = {
        "scope": "all_evaluated_promotion_eligible_candidates",
        "visibility_partition": "development_validation",
        "return_stream_identity": "continuous_daily_open_to_open_net_returns_terminal_free",
        "primary_cost_bps": PRIMARY_COST_BPS,
        "candidate_ids": promotable_ids,
        "effective_trial_count": effective_trial_count,
        "diagnostic_only_not_frozen_oos_evidence": True,
        "status": "undefined",
        "pass": False,
        "reason": "benchmark_return_stream_not_staged_before_publication_failure",
        "candidate_dsr_probabilities_from_staged_metrics": {
            result.candidate_id: result.metrics["development_dsr_probability_diagnostic"]
            for result in validated_branches.evaluated
            if result.promotion_eligible
        },
        "market_return_recomputation_prohibited": True,
    }
    correlation_diagnostic = _advancing_pair_correlation_diagnostic(contract, {})
    report = {
        "schema_version": 1,
        "campaign_id": CAMPAIGN_ID,
        "stage": "development_only",
        "workflow_pass": True,
        "research_pass": False,
        "paper_ready_pass": False,
        "evaluated_candidate_count": len(validated_branches.evaluated),
        "dependency_skipped_candidate_ids": list(validated_branches.excluded_candidate_ids),
        "qd_elite_candidate_ids": sorted(elite_ids),
        "development_gate_advancing_candidate_ids": advancing,
        "development_family_statistics_diagnostic": family_diagnostics,
        "development_pre_oos_ready": False,
        "effective_trial_count": effective_trial_count,
        "effective_trial_exposure": math.fsum(
            entry.effective_trial_exposure for entry in ledger.entries
        ),
        "allocation_ledger_head_sha256": ledger.head_sha256,
        "advancing_pair_correlation_diagnostic": correlation_diagnostic,
        "advancing_primary_return_correlations": correlation_diagnostic["correlations"],
        "low_correlation_absolute_maximum": correlation_diagnostic["policy"]["absolute_maximum"],
        "low_correlation_advancing_pairs": correlation_diagnostic["passing_pairs"],
        "branches": validated_branches.branch_reports,
        "development_evaluation_attempt": dict(attempt_binding),
        "publication_recovery": dict(recovery_evidence),
        "recovery_non_recomputed_statistics": {
            "status": "preserved_from_staged_metrics_not_recomputed",
            "reason": (
                "the publication failure occurred after candidate evaluation, but daily "
                "benchmark and non-primary-cost return streams were not staged"
            ),
            "fields": [
                "annualized_sharpe_excess_bil_20bps",
                "development_fold_excess_sharpes_and_qd_quality",
                "development_dsr_probability_diagnostic",
                "qqq_and_tqqq_upside_downside_capture_statistics",
                "10bps_daily_derived_statistics",
                "40bps_daily_derived_statistics",
            ],
            "market_return_recomputation_prohibited": True,
            "promotion_credit": "none",
        },
        "publication_receipt_required": True,
        "publication_receipt_path": DEVELOPMENT_RECEIPT_PATH.as_posix(),
        "frozen_oos_rows_read": 0,
        "frozen_oos_read_authorized": False,
        "model_training_count": 0,
        "broker_writes": False,
        "next_action": (
            "do_not_open_frozen_oos_preserve_negative_development_result_"
            "and_open_independent_campaign"
        ),
    }
    return RecoveryCampaignOutputs(
        archive=archive.model_dump(),
        ledger_rows=tuple(entry.model_dump() for entry in ledger.entries),
        report=report,
    )


def _validate_completed_recovery_campaign_outputs(
    root: Path,
    outputs: RecoveryCampaignOutputs,
) -> None:
    expected = {
        "qd-archive.json": (json.dumps(outputs.archive, indent=2, sort_keys=True) + "\n").encode(
            "utf-8"
        ),
        "allocation-ledger.jsonl": "".join(
            _canonical_json(row) + "\n" for row in outputs.ledger_rows
        ).encode("ascii"),
        "development-evaluation-report.json": (
            json.dumps(outputs.report, indent=2, sort_keys=True) + "\n"
        ).encode("utf-8"),
    }
    for name, expected_bytes in expected.items():
        path = root / CAMPAIGN_ROOT / name
        if path.is_symlink() or not path.is_file() or path.read_bytes() != expected_bytes:
            raise ValueError(
                f"completed development recovery campaign output identity mismatch: {name}"
            )


def _expected_recovery_publication_paths(
    root: Path,
    *,
    contract: ResearchCampaignContract,
) -> set[str]:
    paths = {
        (CAMPAIGN_ROOT / "qd-archive.json").as_posix(),
        (CAMPAIGN_ROOT / "allocation-ledger.jsonl").as_posix(),
        (CAMPAIGN_ROOT / "development-evaluation-report.json").as_posix(),
    }
    for iter_id in contract.child_iteration_ids:
        iteration = root / ITERATION_ROOT / iter_id
        feasibility = _read_json(iteration / "data-feasibility.json")
        if feasibility.get("historical_evaluation_authorized") is not True:
            continue
        candidates = _read_json(iteration / "candidate-manifest.json")["candidates"]
        destination = ITERATION_ROOT / iter_id / "evaluation-run"
        names = {
            "evaluation-report.json",
            "trial-ledger.jsonl",
            "development-return-matrix.json",
            *(f"{row['candidate_id']}-metrics.json" for row in candidates),
            *(f"{row['candidate_id']}-signal-log.jsonl" for row in candidates),
        }
        paths.update((destination / name).as_posix() for name in names)
    return paths


def _load_completed_recovery(
    root: Path,
    *,
    contract: ResearchCampaignContract,
    attempt: Mapping[str, Any],
    attempt_binding: Mapping[str, str],
    recovery_evidence: Mapping[str, Any],
    campaign_contract_sha256: str,
) -> dict[str, Any]:
    receipt_path = root / DEVELOPMENT_RECEIPT_PATH
    if receipt_path.is_symlink() or not receipt_path.is_file():
        raise ValueError("completed development recovery receipt custody mismatch")
    receipt = _read_json(receipt_path)
    try:
        datetime.fromisoformat(str(receipt.get("published_at")))
    except (TypeError, ValueError) as exc:
        raise ValueError("completed development recovery publication timestamp is invalid") from exc
    publication_files = receipt.get("publication_files")
    expected_publication_paths = _expected_recovery_publication_paths(
        root,
        contract=contract,
    )
    expected = {
        "schema_version": 1,
        "campaign_id": CAMPAIGN_ID,
        "status": "complete",
        "completion_marker": True,
        "development_evaluation_attempt": dict(attempt_binding),
        "publication_recovery": dict(recovery_evidence),
        "campaign_contract_sha256": campaign_contract_sha256,
        "effective_trial_count": attempt["effective_trial_count"],
        "evaluated_candidate_count": attempt["evaluated_candidate_count"],
        "dependency_skipped_candidate_count": attempt["registered_candidate_count"]
        - attempt["evaluated_candidate_count"],
        "receipt_published_last": True,
        "frozen_oos_rows_read": 0,
        "model_training_count": 0,
        "broker_writes": False,
    }
    expected_receipt_keys = {
        *expected,
        "published_at",
        "publication_file_count",
        "publication_files",
    }
    if (
        set(receipt) != expected_receipt_keys
        or any(receipt.get(name) != value for name, value in expected.items())
        or not isinstance(publication_files, list)
        or receipt.get("publication_file_count") != len(publication_files)
        or receipt.get("publication_file_count") != len(expected_publication_paths)
        or len({str(row.get("path")) for row in publication_files if isinstance(row, dict)})
        != len(publication_files)
        or {str(row.get("path")) for row in publication_files if isinstance(row, dict)}
        != expected_publication_paths
    ):
        raise ValueError("completed development recovery receipt identity mismatch")
    for binding in publication_files:
        if (
            not isinstance(binding, dict)
            or set(binding) != {"path", "sha256"}
            or not _is_sha256(str(binding.get("sha256") or ""))
        ):
            raise ValueError("completed development recovery publication binding is malformed")
        _verify_binding(root, binding)
    for iter_id in contract.child_iteration_ids:
        feasibility = _read_json(root / ITERATION_ROOT / iter_id / "data-feasibility.json")
        final = root / ITERATION_ROOT / iter_id / "evaluation-run"
        stages = list((root / ITERATION_ROOT / iter_id).glob("evaluation-run.staging-*"))
        authorized = feasibility.get("historical_evaluation_authorized") is True
        invalid_final = (
            final.is_symlink() or not final.is_dir()
            if authorized
            else final.is_symlink() or final.exists()
        )
        if stages or invalid_final:
            raise ValueError(f"completed development recovery branch custody mismatch: {iter_id}")
        if authorized:
            expected_names = {
                Path(path).name
                for path in expected_publication_paths
                if Path(path).parent == ITERATION_ROOT / iter_id / "evaluation-run"
            }
            entries = list(final.iterdir())
            if {path.name for path in entries} != expected_names or any(
                path.is_symlink() or not path.is_file() for path in entries
            ):
                raise ValueError(
                    f"completed development recovery branch inventory mismatch: {iter_id}"
                )
    expected_campaign_stage = (
        root
        / CAMPAIGN_ROOT
        / f"development-evaluation.staging-{recovery_evidence.get('run_token')}"
    )
    campaign_stages = list((root / CAMPAIGN_ROOT).glob("development-evaluation.staging-*"))
    if campaign_stages:
        if (
            campaign_stages != [expected_campaign_stage]
            or campaign_stages[0].is_symlink()
            or not campaign_stages[0].is_dir()
            or any(campaign_stages[0].iterdir())
        ):
            raise ValueError("completed development recovery has residual campaign staging")
    amendment_binding = recovery_evidence.get("amendment")
    if not isinstance(amendment_binding, dict):
        raise ValueError("completed development recovery amendment binding is malformed")
    validated_branches = _load_validated_staged_results(
        root,
        contract=contract,
        attempt=dict(attempt),
        attempt_binding=dict(attempt_binding),
        run_token=str(recovery_evidence.get("run_token") or ""),
        amendment_binding=dict(amendment_binding),
        campaign_contract_sha256=campaign_contract_sha256,
        completed=True,
    )
    outputs = _reconstruct_recovery_publication(
        contract=contract,
        validated_branches=validated_branches,
        attempt=attempt,
        attempt_binding=attempt_binding,
        recovery_evidence=recovery_evidence,
        campaign_contract_sha256=campaign_contract_sha256,
    )
    _validate_completed_recovery_campaign_outputs(root, outputs)
    return outputs.report


def recover_staged_development_publication(
    root: Path,
    *,
    run_token: str,
    attempt_sha256: str,
) -> dict[str, Any]:
    """Publish the reserved attempt from staged evidence without recomputing returns."""
    base = root.resolve()
    contract = load_campaign_contract(CAMPAIGN_ID, base)
    attempt, attempt_binding, campaign_contract_sha256 = _validate_recovery_attempt(
        base,
        run_token=run_token,
        attempt_sha256=attempt_sha256,
        contract=contract,
    )
    authorized_branch_count = sum(
        _read_json(base / ITERATION_ROOT / iter_id / "data-feasibility.json").get(
            "historical_evaluation_authorized"
        )
        is True
        for iter_id in contract.child_iteration_ids
    )
    amendment_binding = _validate_recovery_amendment(
        base,
        contract=contract,
        attempt=attempt,
        attempt_binding=attempt_binding,
        run_token=run_token,
        authorized_branch_count=authorized_branch_count,
    )
    recovery_evidence = _publication_recovery_evidence(
        run_token=run_token,
        attempt_sha256=attempt_sha256,
        amendment_binding=amendment_binding,
    )
    if (base / DEVELOPMENT_RECEIPT_PATH).is_file():
        return _load_completed_recovery(
            base,
            contract=contract,
            attempt=attempt,
            attempt_binding=attempt_binding,
            recovery_evidence=recovery_evidence,
            campaign_contract_sha256=campaign_contract_sha256,
        )
    staged = _load_validated_staged_results(
        base,
        contract=contract,
        attempt=attempt,
        attempt_binding=attempt_binding,
        run_token=run_token,
        amendment_binding=amendment_binding,
        campaign_contract_sha256=campaign_contract_sha256,
    )

    outputs = _reconstruct_recovery_publication(
        contract=contract,
        validated_branches=staged,
        attempt=attempt,
        attempt_binding=attempt_binding,
        recovery_evidence=recovery_evidence,
        campaign_contract_sha256=campaign_contract_sha256,
    )
    report = outputs.report

    campaign_output_paths = {
        "qd-archive.json": _write_or_verify_json(
            staged.campaign_staging / "qd-archive.json",
            base / CAMPAIGN_ROOT / "qd-archive.json",
            outputs.archive,
        ),
        "allocation-ledger.jsonl": _write_or_verify_jsonl(
            staged.campaign_staging / "allocation-ledger.jsonl",
            base / CAMPAIGN_ROOT / "allocation-ledger.jsonl",
            list(outputs.ledger_rows),
        ),
        "development-evaluation-report.json": _write_or_verify_json(
            staged.campaign_staging / "development-evaluation-report.json",
            base / CAMPAIGN_ROOT / "development-evaluation-report.json",
            report,
        ),
    }

    publication_files = []
    for iter_id, stage in sorted(staged.branch_staging.items()):
        destination = base / ITERATION_ROOT / iter_id / "evaluation-run"
        publication_files.extend(
            _staged_publication_binding(
                path,
                destination_path=destination / path.name,
                root=base,
            )
            for path in sorted(stage.iterdir())
            if path.is_file()
        )
    for name in (
        "qd-archive.json",
        "allocation-ledger.jsonl",
        "development-evaluation-report.json",
    ):
        publication_files.append(
            _staged_publication_binding(
                campaign_output_paths[name],
                destination_path=base / CAMPAIGN_ROOT / name,
                root=base,
            )
        )
    staged_receipt_path = staged.campaign_staging / DEVELOPMENT_RECEIPT_PATH.name
    existing_staged_receipt = (
        _read_json(staged_receipt_path) if staged_receipt_path.is_file() else None
    )
    published_at = (
        str(existing_staged_receipt.get("published_at"))
        if existing_staged_receipt is not None
        else datetime.now(UTC).isoformat()
    )
    receipt = {
        "schema_version": 1,
        "campaign_id": CAMPAIGN_ID,
        "published_at": published_at,
        "status": "complete",
        "completion_marker": True,
        "development_evaluation_attempt": attempt_binding,
        "publication_recovery": recovery_evidence,
        "campaign_contract_sha256": campaign_contract_sha256,
        "effective_trial_count": report["effective_trial_count"],
        "evaluated_candidate_count": len(staged.evaluated),
        "dependency_skipped_candidate_count": len(staged.excluded_candidate_ids),
        "publication_file_count": len(publication_files),
        "publication_files": publication_files,
        "receipt_published_last": True,
        "frozen_oos_rows_read": 0,
        "model_training_count": 0,
        "broker_writes": False,
    }
    _write_or_verify_json(
        staged_receipt_path,
        base / DEVELOPMENT_RECEIPT_PATH,
        receipt,
    )
    _publish_staged_outputs(
        root=base,
        branch_staging=staged.branch_staging,
        campaign_staging=staged.campaign_staging,
        publication_files=publication_files,
    )
    published_receipt = _read_json(base / DEVELOPMENT_RECEIPT_PATH)
    if published_receipt != receipt:
        raise ValueError("recovered development publication receipt identity changed")
    for binding in publication_files:
        _verify_binding(base, binding)
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--recover-run-token")
    parser.add_argument("--attempt-sha256")
    args = parser.parse_args()
    if bool(args.recover_run_token) != bool(args.attempt_sha256):
        parser.error("--recover-run-token and --attempt-sha256 must be supplied together")
    if args.recover_run_token:
        report = recover_staged_development_publication(
            args.root,
            run_token=args.recover_run_token,
            attempt_sha256=args.attempt_sha256,
        )
    else:
        report = run_development_campaign(args.root)
    print(_canonical_json(report))


if __name__ == "__main__":
    main()
