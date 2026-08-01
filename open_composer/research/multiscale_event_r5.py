from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from open_composer.analytics import build_performance_metrics
from open_composer.config import ensure_dir, project_root
from open_composer.models.strategy_spec import load_strategy_spec
from open_composer.research.iteration_dossier import validate_iteration_dossier
from open_composer.storage import write_json
from open_composer.strategy_versions import strategy_content_hash

ITER_ID = "mom_multiscale_event_r5"
STRATEGY_NAME = "us_multiscale_event_momentum_r5"
FORMAL_FORWARD_START = "2026-07-20"
ITERATION_DIR = Path("reports/research/iterations") / ITER_ID
SPEC_PATH = Path("strategy_specs/drafts/us_multiscale_event_momentum_r5.yaml")
CANDIDATE_MANIFEST_PATH = ITERATION_DIR / "candidate-manifest.json"
SEARCH_SPACE_PATH = ITERATION_DIR / "search-space.json"
DATA_FEASIBILITY_PATH = ITERATION_DIR / "data-feasibility.json"
COST_CONTRACT_PATH = ITERATION_DIR / "cost-contract.json"
PRIOR_EVIDENCE_PATH = ITERATION_DIR / "prior-evidence.json"
SOURCE_CARDS_PATH = Path("reports/harness/source_cards/us_multiscale_event_momentum_r5.jsonl")

ETF_SYMBOLS = (
    "SPY",
    "XLB",
    "XLC",
    "XLE",
    "XLF",
    "XLI",
    "XLK",
    "XLP",
    "XLRE",
    "XLU",
    "XLV",
    "XLY",
)
SECTOR_SYMBOLS = ETF_SYMBOLS[1:]
STOCK_SYMBOLS = (
    "AAPL",
    "AMD",
    "AMZN",
    "AVGO",
    "GOOGL",
    "META",
    "MSFT",
    "NFLX",
    "NVDA",
    "TSLA",
)
ALL_SYMBOLS = (*ETF_SYMBOLS, *STOCK_SYMBOLS)
EXPECTED_CANDIDATE_IDS = tuple(
    [f"D{index:02d}" for index in range(1, 10)]
    + [f"E{index:02d}" for index in range(1, 5)]
    + ["N01", "N02"]
)
REQUIRED_ANCHORS = ("09:30", "10:00", "10:30", "15:00", "15:30")
PRIMITIVE_FIELDS = ("open", "high", "low", "close", "volume")
ROLLING_VOLUME_SESSIONS = 20
OUTER_FOLDS = 4
COST_SCENARIOS = (5.0, 10.0, 20.0)


class ContractViolation(ValueError):
    pass


class FutureFeatureError(ContractViolation):
    pass


@dataclass(frozen=True)
class SessionPanel:
    open_0930: pd.DataFrame
    close_1000: pd.DataFrame
    open_1030: pd.DataFrame
    open_1530: pd.DataFrame
    close_1530: pd.DataFrame
    first_hour_volume: pd.DataFrame
    source_rows: tuple[dict[str, Any], ...]

    @property
    def sessions(self) -> pd.DatetimeIndex:
        return self.open_0930.index


@dataclass(frozen=True)
class FeatureSet:
    first_hour_return: pd.DataFrame
    market_relative: pd.DataFrame
    prior_five_session_return: pd.DataFrame
    gap: pd.DataFrame
    relative_volume: pd.DataFrame
    breadth: pd.Series

    @property
    def sessions(self) -> pd.DatetimeIndex:
        return self.first_hour_return.index


@dataclass(frozen=True)
class CandidateSelections:
    selections: dict[str, dict[pd.Timestamp, tuple[str, ...]]]
    scores: dict[str, pd.DataFrame]


@dataclass(frozen=True)
class MultiscaleEventResult:
    evaluation_path: Path
    markdown_path: Path
    trial_ledger_path: Path
    payload: dict[str, Any]


def prepare_multiscale_event_inputs(root: Path | None = None) -> dict[str, Any]:
    base = root or project_root()
    required = _required_preregistration_paths(base)
    for path in required.values():
        if not path.exists():
            raise ContractViolation(f"required preregistration artifact is missing: {path}")

    panel = _load_exact_panel(base)
    manifest = _load_json(required["candidate_manifest"])
    candidates = manifest.get("candidates", [])
    candidate_by_path: dict[str, list[str]] = {}
    for candidate in candidates:
        candidate_by_path.setdefault(str(candidate["path"]), []).append(
            str(candidate["candidate_id"])
        )

    common = panel.sessions
    forward_start = pd.Timestamp(FORMAL_FORWARD_START)
    input_bundle = _input_bundle_payload(panel)
    bindings = {
        name: _artifact_binding(path, base)
        for name, path in required.items()
        if name != "source_spec"
    }
    bindings["source_spec"] = {
        **_artifact_binding(required["source_spec"], base),
        "strategy_content_hash": strategy_content_hash(load_strategy_spec(required["source_spec"])),
    }
    path_gates = {
        "deterministic_intraday": {
            "action": "run_diagnostic",
            "historical_diagnostic_go": True,
            "historical_research_qualified": False,
            "candidate_ids": candidate_by_path["deterministic_intraday"],
            "reason_code": "complete_shared_IEX_OHLCV_panel",
        },
        "event_factor": {
            "action": "dependency_skipped",
            "historical_diagnostic_go": False,
            "historical_research_qualified": False,
            "candidate_ids": candidate_by_path["event_factor"],
            "reason_code": "real_historical_PIT_event_packets_missing",
        },
        "negative_controls": {
            "action": "run_diagnostic",
            "historical_diagnostic_go": True,
            "historical_research_qualified": False,
            "candidate_ids": candidate_by_path["negative_controls"],
            "reason_code": "mandatory_control_path",
        },
    }
    runnable_count = len(path_gates["deterministic_intraday"]["candidate_ids"]) + len(
        path_gates["negative_controls"]["candidate_ids"]
    )
    skipped_count = len(path_gates["event_factor"]["candidate_ids"])
    payload = {
        "schema_version": 1,
        "report_type": "multiscale_event_r5_data_feasibility",
        "iter_id": ITER_ID,
        "generated_at": datetime.now(UTC).isoformat(),
        "workflow_pass": True,
        "research_pass": False,
        "llm_contribution_pass": False,
        "paper_ready_pass": False,
        "diagnostic_execution_authorized": True,
        "scope": "historical_current_basket_IEX_diagnostic",
        "survivorship_labelled": True,
        "primitive_fields": list(PRIMITIVE_FIELDS),
        "forward_fill_allowed": False,
        "zero_return_substitution_allowed": False,
        "etf_symbols": list(ETF_SYMBOLS),
        "stock_symbols": list(STOCK_SYMBOLS),
        "selected_symbol_count": len(ALL_SYMBOLS),
        "exact_common_session_count": len(common),
        "exact_common_first_session": common.min().date().isoformat(),
        "exact_common_last_session": common.max().date().isoformat(),
        "feature_warmup_sessions": ROLLING_VOLUME_SESSIONS,
        "diagnostic_session_count": len(common) - ROLLING_VOLUME_SESSIONS,
        "formal_forward_start": FORMAL_FORWARD_START,
        "formal_forward_observation_count": int((common >= forward_start).sum()),
        "input_bundle_sha256": _canonical_sha(input_bundle),
        "input_files": [dict(row) for row in panel.source_rows],
        "bindings": bindings,
        "path_gates": path_gates,
        "candidate_accounting": {
            "frozen_candidate_count": len(candidates),
            "diagnostic_runnable_count": runnable_count,
            "dependency_skipped_count": skipped_count,
            "unresolved_count": 0,
            "balanced": runnable_count + skipped_count == len(candidates),
        },
        "capability_status": {
            "alpaca_IEX_intraday_research": "diagnostic_only",
            "consolidated_SIP_or_official_auction": "blocked",
            "historical_SEC_PIT_packets": "blocked",
            "historical_news_PIT_packets": "blocked",
            "licensed_call_transcripts_or_audio": "blocked",
            "matched_intraday_TCA": "blocked",
        },
        "limitations": [
            "Alpaca Basic bars are IEX-only and are not consolidated SIP evidence.",
            "The ten-stock basket is current and survivorship-labelled, not PIT membership.",
            "No real historical SEC, news, transcript, or audio replay packet is available.",
            "No forward observations occur on or after the formal forward epoch.",
            "No matched decision, quote, order, fill, spread, or market-impact TCA exists.",
            "The diagnostic does not authorize signals, paper orders, or model training.",
        ],
    }
    write_json(base / DATA_FEASIBILITY_PATH, payload)
    return payload


def validate_multiscale_event_preflight(root: Path | None = None) -> list[str]:
    base = root or project_root()
    blockers: list[str] = []
    dossier = validate_iteration_dossier(ITER_ID, base, stage="pre-backtest")
    if not dossier.ok:
        blockers.extend(f"iteration:{item}" for item in dossier.blocked)

    required = _required_preregistration_paths(base)
    required["data_feasibility"] = base / DATA_FEASIBILITY_PATH
    for name, path in required.items():
        if not path.exists():
            blockers.append(f"{name}_missing")
    if blockers:
        return blockers

    search = _load_json(required["search_space"])
    manifest = _load_json(required["candidate_manifest"])
    feasibility = _load_json(required["data_feasibility"])
    preregistration = search.get("preregistration", {})
    if preregistration.get("candidate_manifest_sha256") != _sha256_file(
        required["candidate_manifest"]
    ):
        blockers.append("candidate_manifest_sha256_mismatch")
    candidate_ids = tuple(
        str(candidate.get("candidate_id")) for candidate in manifest.get("candidates", [])
    )
    if candidate_ids != EXPECTED_CANDIDATE_IDS:
        blockers.append("candidate_id_order_or_set_mismatch")
    if manifest.get("candidate_count") != len(EXPECTED_CANDIDATE_IDS):
        blockers.append("candidate_count_mismatch")
    if manifest.get("generated_before_backtest") is not True:
        blockers.append("candidate_manifest_not_preregistered")
    if search.get("total_candidate_budget") != len(EXPECTED_CANDIDATE_IDS):
        blockers.append("search_space_budget_mismatch")

    spec = load_strategy_spec(required["source_spec"])
    spec_hash = strategy_content_hash(spec)
    expected_spec_hash = manifest.get("spec_hashes", {}).get(SPEC_PATH.as_posix())
    if expected_spec_hash != spec_hash or search.get("spec_hash") != spec_hash:
        blockers.append("source_spec_content_hash_mismatch")
    blockers.extend(_validate_feature_contract(manifest))

    expected_passes = {
        "workflow_pass": True,
        "research_pass": False,
        "llm_contribution_pass": False,
        "paper_ready_pass": False,
        "diagnostic_execution_authorized": True,
    }
    for field, expected in expected_passes.items():
        if feasibility.get(field) is not expected:
            blockers.append(f"data_feasibility_{field}_invalid")
    if feasibility.get("formal_forward_observation_count") != 0:
        blockers.append("unexpected_formal_forward_observations")
    if feasibility.get("forward_fill_allowed") is not False:
        blockers.append("forward_fill_contract_mismatch")
    if feasibility.get("zero_return_substitution_allowed") is not False:
        blockers.append("zero_return_substitution_contract_mismatch")
    if feasibility.get("primitive_fields") != list(PRIMITIVE_FIELDS):
        blockers.append("primitive_field_contract_mismatch")

    path_gates = feasibility.get("path_gates", {})
    expected_actions = {
        "deterministic_intraday": "run_diagnostic",
        "event_factor": "dependency_skipped",
        "negative_controls": "run_diagnostic",
    }
    for path_name, action in expected_actions.items():
        if path_gates.get(path_name, {}).get("action") != action:
            blockers.append(f"path_gate_{path_name}_invalid")

    try:
        panel = _load_exact_panel(base)
    except ContractViolation as exc:
        blockers.append(f"panel:{exc}")
    else:
        if feasibility.get("input_bundle_sha256") != _canonical_sha(_input_bundle_payload(panel)):
            blockers.append("input_bundle_sha256_mismatch")
        if feasibility.get("exact_common_session_count") != len(panel.sessions):
            blockers.append("common_session_count_mismatch")

    bindings = feasibility.get("bindings", {})
    for name, path in required.items():
        if name in {"data_feasibility", "source_spec"}:
            continue
        if bindings.get(name, {}).get("sha256") != _sha256_file(path):
            blockers.append(f"{name}_binding_mismatch")
    if bindings.get("source_spec", {}).get("strategy_content_hash") != spec_hash:
        blockers.append("source_spec_binding_mismatch")
    return blockers


def run_multiscale_event_r5(root: Path | None = None) -> MultiscaleEventResult:
    base = root or project_root()
    blockers = validate_multiscale_event_preflight(base)
    if blockers:
        raise ContractViolation("preflight blocked: " + ", ".join(blockers))

    output_dir = ensure_dir(base / ITERATION_DIR)
    panel = _load_exact_panel(base)
    features = _build_features(panel)
    selections = _build_candidate_selections(features)
    labels = {
        "midday": (panel.open_1530 / panel.open_1030 - 1.0).loc[features.sessions],
        "last_half_hour": (panel.close_1530 / panel.open_1530 - 1.0).loc[features.sessions],
    }
    _require_finite_frame(labels["midday"], "midday labels")
    _require_finite_frame(labels["last_half_hour"], "last-half-hour labels")
    folds = _chronological_folds(features.sessions)

    manifest = _load_json(base / CANDIDATE_MANIFEST_PATH)
    feasibility = _load_json(base / DATA_FEASIBILITY_PATH)
    search = _load_json(base / SEARCH_SPACE_PATH)
    candidate_by_id = {
        str(candidate["candidate_id"]): candidate for candidate in manifest["candidates"]
    }
    benchmark_results, benchmark_hash = _build_benchmarks(
        labels,
        features,
        folds,
    )

    candidate_results: dict[str, dict[str, Any]] = {}
    label_by_candidate = {
        "D01": "last_half_hour",
        "D02": "midday",
        "D03": "last_half_hour",
        "D04": "midday",
        "D05": "midday",
        "D06": "midday",
        "D07": "midday",
        "D08": "midday",
        "D09": "midday",
        "N01": "midday",
    }
    for candidate_id, label_name in label_by_candidate.items():
        candidate_results[candidate_id] = {
            "status": "complete",
            "label_window": label_name,
            "selection_prohibited": bool(
                candidate_by_id[candidate_id].get("selection_prohibited", False)
            ),
            "score_sha256": _frame_sha(selections.scores[candidate_id]),
            "metrics_by_cost_bps": {
                str(int(cost)): _evaluate_selection(
                    selections.selections[candidate_id],
                    labels[label_name],
                    folds,
                    cost_bps=cost,
                )
                for cost in COST_SCENARIOS
            },
        }
    for candidate_id in ("E01", "E02", "E03", "E04"):
        candidate_results[candidate_id] = {
            "status": "skipped_dependency",
            "selection_prohibited": bool(
                candidate_by_id[candidate_id].get("selection_prohibited", False)
            ),
            "required_dependency": candidate_by_id[candidate_id]["required_dependency"],
            "fallback": candidate_by_id[candidate_id]["fallback"],
            "metrics_by_cost_bps": None,
            "reason": "real historical PIT event packets are absent",
        }
    future_control = _future_feature_control()
    if not future_control["mandatory_outcome_met"]:
        raise ContractViolation("future-feature negative control did not reject")
    candidate_results["N02"] = {
        "status": "rejected_control",
        "selection_prohibited": True,
        "metrics_by_cost_bps": None,
        "control": future_control,
    }

    placebo = _placebo_gate(candidate_results)
    _attach_acceptance(candidate_results, benchmark_results, placebo)
    pbo = _pbo_diagnostic(candidate_results)
    dsr = _dsr_proxy(candidate_results)
    diagnostic_leader = _diagnostic_leader(candidate_results)
    forward_candidates = [
        candidate_id
        for candidate_id in EXPECTED_CANDIDATE_IDS
        if candidate_id.startswith("D")
        and candidate_results[candidate_id].get("acceptance", {}).get("passed")
    ]
    if not placebo["passed"]:
        forward_candidates = []
    forward_candidates = forward_candidates[:1]

    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    input_hashes = {
        "candidate_manifest_sha256": _sha256_file(base / CANDIDATE_MANIFEST_PATH),
        "data_feasibility_sha256": _sha256_file(base / DATA_FEASIBILITY_PATH),
        "input_bundle_sha256": feasibility["input_bundle_sha256"],
        "cost_contract_sha256": _sha256_file(base / COST_CONTRACT_PATH),
        "prior_evidence_sha256": _sha256_file(base / PRIOR_EVIDENCE_PATH),
        "search_space_sha256": _sha256_file(base / SEARCH_SPACE_PATH),
        "spec_hash": strategy_content_hash(load_strategy_spec(base / SPEC_PATH)),
        "code_sha256": _sha256_file(Path(__file__)),
    }
    ledger_rows = []
    for candidate_id in EXPECTED_CANDIDATE_IDS:
        candidate = candidate_by_id[candidate_id]
        result = candidate_results[candidate_id]
        if result["status"] == "skipped_dependency":
            action = "dependency_skipped"
        elif result["status"] == "rejected_control":
            action = "rejected_control"
        else:
            action = "run_diagnostic"
        ledger_rows.append(
            {
                "run_id": run_id,
                "iter_id": ITER_ID,
                "candidate_id": candidate_id,
                "candidate_binding_sha256": _canonical_sha(candidate),
                "path": candidate["path"],
                "role": candidate["role"],
                "method": candidate["method"],
                "ablation": candidate["ablation"],
                "action": action,
                "status": result["status"],
                "scope": "historical_current_basket_IEX_diagnostic",
                "survivorship_labelled": True,
                "workflow_pass": result["status"]
                in {"complete", "skipped_dependency", "rejected_control"},
                "research_pass": False,
                "llm_contribution_pass": False,
                "paper_ready_pass": False,
                "promotion_eligible": False,
                "selection_prohibited": result["selection_prohibited"],
                "input_hashes": input_hashes,
                "random_seed": candidate.get("random_seed"),
                "serialized_model": False,
                "folds": _fold_rows(folds),
                "metrics_by_cost_bps": result.get("metrics_by_cost_bps"),
                "benchmark_family_sha256": benchmark_hash,
                "acceptance": result.get("acceptance"),
                "control": result.get("control"),
                "dependency": result.get("required_dependency"),
            }
        )
    ledger_path = output_dir / "trial-ledger.jsonl"
    ledger_path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in ledger_rows),
        encoding="utf-8",
    )

    feature_payload = {
        "schema_version": 1,
        "iter_id": ITER_ID,
        "run_id": run_id,
        "session_count": len(features.sessions),
        "first_session": features.sessions.min().date().isoformat(),
        "last_session": features.sessions.max().date().isoformat(),
        "feature_hashes": {
            "first_hour_return": _frame_sha(features.first_hour_return),
            "market_relative": _frame_sha(features.market_relative),
            "prior_five_session_return": _frame_sha(features.prior_five_session_return),
            "gap": _frame_sha(features.gap),
            "relative_volume": _frame_sha(features.relative_volume),
            "breadth": _series_sha(features.breadth),
        },
        "candidate_score_hashes": {
            candidate_id: result["score_sha256"]
            for candidate_id, result in candidate_results.items()
            if result.get("score_sha256")
        },
        "serialized_models": [],
        "live_API_calls": [],
    }
    feature_path = output_dir / "feature-diagnostics.json"
    write_json(feature_path, feature_payload)

    payload = {
        "schema_version": 1,
        "report_type": "multiscale_event_intraday_family_evaluation",
        "iter_id": ITER_ID,
        "strategy_name": STRATEGY_NAME,
        "run_id": run_id,
        "generated_at": datetime.now(UTC).isoformat(),
        "workflow_pass": True,
        "research_pass": False,
        "llm_contribution_pass": False,
        "paper_ready_pass": False,
        "scope": "historical_current_basket_IEX_diagnostic",
        "survivorship_labelled": True,
        "candidate_count": len(EXPECTED_CANDIDATE_IDS),
        "completed_candidate_count": 10,
        "dependency_skipped_count": 4,
        "rejected_control_count": 1,
        "selected_candidates": [],
        "diagnostic_leader": diagnostic_leader,
        "forward_observation_candidate_ids": forward_candidates,
        "formal_forward_start": FORMAL_FORWARD_START,
        "formal_forward_observation_count": 0,
        "data_window": {
            "common_first_session": panel.sessions.min().date().isoformat(),
            "common_last_session": panel.sessions.max().date().isoformat(),
            "common_session_count": len(panel.sessions),
            "diagnostic_first_session": features.sessions.min().date().isoformat(),
            "diagnostic_last_session": features.sessions.max().date().isoformat(),
            "diagnostic_session_count": len(features.sessions),
        },
        "input_hashes": input_hashes,
        "folds": _fold_rows(folds),
        "cost_scenarios_one_way_bps": list(COST_SCENARIOS),
        "candidate_results": candidate_results,
        "benchmark_family": {
            "selection_eligible": False,
            "results": benchmark_results,
            "sha256": benchmark_hash,
            "ex_post_best_is_one_fixed_symbol_per_window": True,
        },
        "multiple_testing": {
            "candidate_budget": search["total_candidate_budget"],
            "selectable_deterministic_count": 9,
            "pbo_diagnostic": pbo,
            "dsr_proxy": dsr,
            "quant_score_placebo": placebo,
            "future_feature_control_pass": future_control["mandatory_outcome_met"],
        },
        "event_modality": {
            "historical_training_authorized": False,
            "live_calls_inside_diagnostic": False,
            "dependency_skipped_candidate_ids": ["E01", "E02", "E03", "E04"],
            "missing_modality_behavior": "exact_D09_quant_only_fallback",
            "conference_call_candidate_count": 0,
        },
        "promotion_blockers": [
            "historical_PIT_universe_missing",
            "consolidated_SIP_or_independent_intraday_parity_missing",
            "real_historical_SEC_news_packets_missing",
            "licensed_call_transcript_or_audio_provider_missing",
            "matched_intraday_order_TCA_missing",
            "no_formal_forward_observations",
            "paper_safety_review_not_run",
        ],
        "trial_ledger_path": str(ledger_path.relative_to(base)),
        "feature_diagnostics_path": str(feature_path.relative_to(base)),
        "limitations": feasibility["limitations"],
    }
    evaluation_path = output_dir / "evaluation-report.json"
    markdown_path = output_dir / "evaluation-report.md"
    write_json(evaluation_path, payload)
    markdown_path.write_text(_render_evaluation_markdown(payload), encoding="utf-8")
    _write_decision_record(base, payload)
    return MultiscaleEventResult(evaluation_path, markdown_path, ledger_path, payload)


def _required_preregistration_paths(base: Path) -> dict[str, Path]:
    return {
        "candidate_manifest": base / CANDIDATE_MANIFEST_PATH,
        "search_space": base / SEARCH_SPACE_PATH,
        "cost_contract": base / COST_CONTRACT_PATH,
        "prior_evidence": base / PRIOR_EVIDENCE_PATH,
        "source_cards": base / SOURCE_CARDS_PATH,
        "source_spec": base / SPEC_PATH,
    }


def _validate_feature_contract(manifest: dict[str, Any]) -> list[str]:
    features = manifest.get("contracts", {}).get("features", {}).get("intraday_quant_v1", {})
    expected_formulas = {
        "first_hour_return",
        "first_hour_market_relative",
        "prior_five_session_return",
        "prior_close_to_open_gap",
        "same_slot_relative_volume",
        "sector_breadth",
        "cross_section_rank",
    }
    if set(features.get("formulas", {})) != expected_formulas:
        return ["intraday_feature_formula_contract_incomplete"]
    if features.get("cross_section_tie_break") != "symbol_ascending":
        return ["cross_section_tie_break_contract_mismatch"]
    return []


def _load_exact_panel(root: Path) -> SessionPanel:
    frames: dict[str, pd.DataFrame] = {}
    source_rows: list[dict[str, Any]] = []
    for symbol in ETF_SYMBOLS:
        path = root / f"data/research/alpaca_minute/{symbol.lower()}_30m_alpaca_iex.csv"
        bars = _read_bar_frame(path, symbol)
        sessions = _sessionize_30m(bars, symbol)
        frames[symbol] = sessions
        source_rows.append(_source_row(path, root, symbol, bars, sessions, "30m", "30m"))
    for symbol in STOCK_SYMBOLS:
        path = root / f"data/research/alpaca_minute/{symbol.lower()}_15m_alpaca_iex.csv"
        bars = _read_bar_frame(path, symbol)
        aggregated = _aggregate_15m_to_30m(bars, symbol)
        sessions = _sessionize_30m(aggregated, symbol)
        frames[symbol] = sessions
        source_rows.append(_source_row(path, root, symbol, bars, sessions, "15m", "30m"))

    common = frames[ALL_SYMBOLS[0]].index
    for symbol in ALL_SYMBOLS[1:]:
        common = common.intersection(frames[symbol].index, sort=False)
    common = common.sort_values()
    if len(common) < 252 + ROLLING_VOLUME_SESSIONS:
        raise ContractViolation(f"exact shared complete-session count {len(common)} is below 272")

    panel_fields: dict[str, pd.DataFrame] = {}
    for field in [
        "open_0930",
        "close_1000",
        "open_1030",
        "open_1530",
        "close_1530",
        "first_hour_volume",
    ]:
        frame = pd.DataFrame(
            {symbol: frames[symbol].loc[common, field] for symbol in ALL_SYMBOLS},
            index=common,
            dtype=float,
        )
        _require_finite_frame(frame, field)
        panel_fields[field] = frame
    return SessionPanel(
        **panel_fields,
        source_rows=tuple(source_rows),
    )


def _read_bar_frame(path: Path, symbol: str) -> pd.DataFrame:
    if not path.exists():
        raise ContractViolation(f"missing source file for {symbol}: {path}")
    frame = pd.read_csv(path, usecols=["timestamp", *PRIMITIVE_FIELDS])
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True, errors="coerce")
    if frame["timestamp"].isna().any() or frame["timestamp"].duplicated().any():
        raise ContractViolation(f"{symbol} contains invalid or duplicate timestamps")
    for field in PRIMITIVE_FIELDS:
        frame[field] = pd.to_numeric(frame[field], errors="coerce")
    values = frame[list(PRIMITIVE_FIELDS)].to_numpy(dtype=float)
    if not np.isfinite(values).all():
        raise ContractViolation(f"{symbol} contains non-finite primitive values")
    if (frame[["open", "high", "low", "close"]] <= 0).any().any():
        raise ContractViolation(f"{symbol} contains non-positive price values")
    if (frame["volume"] < 0).any():
        raise ContractViolation(f"{symbol} contains negative volume")
    invalid_range = (frame["high"] < frame[["open", "close", "low"]].max(axis=1)) | (
        frame["low"] > frame[["open", "close", "high"]].min(axis=1)
    )
    if invalid_range.any():
        raise ContractViolation(f"{symbol} contains invalid OHLC ranges")
    return frame.set_index("timestamp").sort_index()[list(PRIMITIVE_FIELDS)]


def _aggregate_15m_to_30m(frame: pd.DataFrame, symbol: str) -> pd.DataFrame:
    local = frame.copy()
    local.index = local.index.tz_convert("America/New_York")
    buckets = local.index.floor("30min")
    grouped = local.groupby(buckets, sort=True)
    counts = grouped.size()
    first_at = grouped.apply(lambda value: value.index.min())
    last_at = grouped.apply(lambda value: value.index.max())
    valid = (counts == 2) & ((last_at - first_at) == pd.Timedelta(minutes=15))
    aggregated = grouped.agg(
        open=("open", "first"),
        high=("high", "max"),
        low=("low", "min"),
        close=("close", "last"),
        volume=("volume", "sum"),
    )
    aggregated = aggregated.loc[valid]
    if aggregated.empty:
        raise ContractViolation(f"{symbol} has no complete 15m pairs for 30m aggregation")
    aggregated.index.name = "timestamp"
    return aggregated


def _sessionize_30m(frame: pd.DataFrame, symbol: str) -> pd.DataFrame:
    local = frame.copy()
    if str(local.index.tz) != "America/New_York":
        local.index = local.index.tz_convert("America/New_York")
    local["session"] = pd.DatetimeIndex(local.index.date)
    local["slot"] = local.index.strftime("%H:%M")
    rows = []
    indexes = []
    for session, group in local.groupby("session", sort=True):
        slot_counts = group["slot"].value_counts()
        if any(slot_counts.get(anchor, 0) != 1 for anchor in REQUIRED_ANCHORS):
            continue
        by_slot = group.set_index("slot")
        rows.append(
            {
                "open_0930": float(by_slot.loc["09:30", "open"]),
                "close_1000": float(by_slot.loc["10:00", "close"]),
                "open_1030": float(by_slot.loc["10:30", "open"]),
                "open_1530": float(by_slot.loc["15:30", "open"]),
                "close_1530": float(by_slot.loc["15:30", "close"]),
                "first_hour_volume": float(
                    by_slot.loc["09:30", "volume"] + by_slot.loc["10:00", "volume"]
                ),
            }
        )
        indexes.append(pd.Timestamp(session))
    if not rows:
        raise ContractViolation(f"{symbol} has no complete required-anchor sessions")
    result = pd.DataFrame(rows, index=pd.DatetimeIndex(indexes, name="session"))
    _require_finite_frame(result, f"{symbol} session panel")
    return result


def _source_row(
    path: Path,
    root: Path,
    symbol: str,
    bars: pd.DataFrame,
    sessions: pd.DataFrame,
    source_timeframe: str,
    runtime_timeframe: str,
) -> dict[str, Any]:
    return {
        "symbol": symbol,
        "path": str(path.relative_to(root)),
        "sha256": _sha256_file(path),
        "source_timeframe": source_timeframe,
        "runtime_timeframe": runtime_timeframe,
        "row_count": len(bars),
        "first_timestamp": bars.index.min().isoformat(),
        "last_timestamp": bars.index.max().isoformat(),
        "complete_anchor_session_count": len(sessions),
        "first_complete_session": sessions.index.min().date().isoformat(),
        "last_complete_session": sessions.index.max().date().isoformat(),
    }


def _build_features(panel: SessionPanel) -> FeatureSet:
    first_hour = panel.close_1000 / panel.open_0930 - 1.0
    market_relative = first_hour.sub(first_hour["SPY"], axis=0)
    prior_five = panel.close_1530.shift(1) / panel.close_1530.shift(6) - 1.0
    gap = panel.open_0930 / panel.close_1530.shift(1) - 1.0
    rolling_volume = (
        panel.first_hour_volume.shift(1)
        .rolling(ROLLING_VOLUME_SESSIONS, min_periods=ROLLING_VOLUME_SESSIONS)
        .median()
    )
    relative_volume = panel.first_hour_volume / rolling_volume
    breadth = (first_hour[list(SECTOR_SYMBOLS)] > 0).mean(axis=1)
    complete = (
        first_hour.notna().all(axis=1)
        & market_relative.notna().all(axis=1)
        & prior_five.notna().all(axis=1)
        & gap.notna().all(axis=1)
        & relative_volume.notna().all(axis=1)
        & breadth.notna()
    )
    sessions = panel.sessions[complete]
    result = FeatureSet(
        first_hour_return=first_hour.loc[sessions],
        market_relative=market_relative.loc[sessions],
        prior_five_session_return=prior_five.loc[sessions],
        gap=gap.loc[sessions],
        relative_volume=relative_volume.loc[sessions],
        breadth=breadth.loc[sessions],
    )
    for name, frame in {
        "first hour": result.first_hour_return,
        "market relative": result.market_relative,
        "prior five": result.prior_five_session_return,
        "gap": result.gap,
        "relative volume": result.relative_volume,
    }.items():
        _require_finite_frame(frame, name)
    return result


def _build_candidate_selections(features: FeatureSet) -> CandidateSelections:
    sectors = list(SECTOR_SYMBOLS)
    stocks = list(STOCK_SYMBOLS)
    relative = features.market_relative[sectors]
    prior_five = features.prior_five_session_return[sectors]
    gap = features.gap[sectors]
    relative_volume = features.relative_volume[sectors]
    relative_rank = _rank_frame(relative)
    trend_rank = _rank_frame(prior_five)
    gap_rank = _rank_frame(gap)
    volume_rank = _rank_frame(relative_volume)
    scores = {
        "D01": features.first_hour_return[["SPY"]],
        "D02": relative,
        "D03": relative,
        "D04": 0.6 * relative_rank + 0.4 * trend_rank,
        "D05": 0.5 * relative_rank + 0.3 * trend_rank + 0.2 * volume_rank,
        "D06": 0.5 * relative_rank + 0.5 * gap_rank,
        "D07": 0.5 * relative_rank + 0.3 * trend_rank + 0.2 * volume_rank,
        "D08": (0.4 * relative_rank + 0.25 * trend_rank + 0.2 * volume_rank + 0.15 * gap_rank),
        "D09": features.market_relative[stocks],
    }
    selections: dict[str, dict[pd.Timestamp, tuple[str, ...]]] = {
        candidate_id: {} for candidate_id in [*scores, "N01"]
    }
    for session in features.sessions:
        selections["D01"][session] = (
            ("SPY",) if features.first_hour_return.loc[session, "SPY"] > 0 else ()
        )
        d02 = _top_symbols(relative.loc[session], relative.loc[session] > 0, top_n=3)
        selections["D02"][session] = d02
        selections["D03"][session] = d02
        selections["D04"][session] = _top_symbols(
            scores["D04"].loc[session],
            (relative.loc[session] > 0) & (prior_five.loc[session] > 0),
            top_n=3,
        )
        selections["D05"][session] = _top_symbols(
            scores["D05"].loc[session],
            (relative.loc[session] > 0) & (relative_volume.loc[session] >= 1.0),
            top_n=3,
        )
        selections["D06"][session] = _top_symbols(
            scores["D06"].loc[session],
            (relative.loc[session] > 0) & (gap.loc[session] > 0),
            top_n=3,
        )
        breadth_gate = (
            features.first_hour_return.loc[session, "SPY"] > 0
            and features.breadth.loc[session] >= 0.5
        )
        selections["D07"][session] = selections["D05"][session] if breadth_gate else ()
        selections["D08"][session] = _top_symbols(
            scores["D08"].loc[session],
            pd.Series(True, index=sectors),
            top_n=3,
        )
        stock_relative = features.market_relative.loc[session, stocks]
        selections["D09"][session] = _top_symbols(
            stock_relative,
            stock_relative > 0,
            top_n=3,
        )

    rng = np.random.default_rng(77)
    permutation = rng.permutation(len(features.sessions))
    shuffled = scores["D08"].iloc[permutation].copy()
    shuffled.index = features.sessions
    scores["N01"] = shuffled
    for session in features.sessions:
        selections["N01"][session] = _top_symbols(
            shuffled.loc[session],
            pd.Series(True, index=sectors),
            top_n=3,
        )
    return CandidateSelections(selections=selections, scores=scores)


def _rank_frame(frame: pd.DataFrame) -> pd.DataFrame:
    return frame.apply(_rank_series, axis=1)


def _rank_series(values: pd.Series) -> pd.Series:
    ordered = sorted(values.index, key=lambda symbol: (-float(values[symbol]), str(symbol)))
    if len(ordered) == 1:
        return pd.Series({ordered[0]: 1.0}, dtype=float)
    return pd.Series(
        {symbol: 1.0 - rank / (len(ordered) - 1) for rank, symbol in enumerate(ordered)},
        dtype=float,
    ).reindex(values.index)


def _top_symbols(scores: pd.Series, eligible: pd.Series, *, top_n: int) -> tuple[str, ...]:
    symbols = [str(symbol) for symbol in scores.index if bool(eligible.loc[symbol])]
    symbols.sort(key=lambda symbol: (-float(scores.loc[symbol]), symbol))
    return tuple(symbols[:top_n])


def _chronological_folds(sessions: pd.DatetimeIndex) -> tuple[pd.DatetimeIndex, ...]:
    if len(sessions) < OUTER_FOLDS * 30:
        raise ContractViolation("fewer than 30 diagnostic sessions per chronological fold")
    return tuple(pd.DatetimeIndex(values) for values in np.array_split(sessions, OUTER_FOLDS))


def _evaluate_selection(
    selections: dict[pd.Timestamp, tuple[str, ...]],
    label_returns: pd.DataFrame,
    folds: tuple[pd.DatetimeIndex, ...],
    *,
    cost_bps: float,
) -> dict[str, Any]:
    net_returns, gross_returns, traded = _selection_returns(
        selections,
        label_returns,
        cost_bps=cost_bps,
    )
    fold_rows = []
    for fold_number, fold_sessions in enumerate(folds, start=1):
        fold_rows.append(
            {
                "fold": fold_number,
                "start": fold_sessions.min().date().isoformat(),
                "end": fold_sessions.max().date().isoformat(),
                **_metrics_from_returns(
                    net_returns.loc[fold_sessions],
                    gross_returns.loc[fold_sessions],
                    traded.loc[fold_sessions],
                ),
            }
        )
    return {
        "aggregate": _metrics_from_returns(net_returns, gross_returns, traded),
        "folds": fold_rows,
    }


def _selection_returns(
    selections: dict[pd.Timestamp, tuple[str, ...]],
    label_returns: pd.DataFrame,
    *,
    cost_bps: float,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    gross_values = []
    trade_flags = []
    for session in label_returns.index:
        symbols = selections.get(session, ())
        if symbols:
            values = label_returns.loc[session, list(symbols)]
            if not np.isfinite(values.to_numpy(dtype=float)).all():
                raise ContractViolation(f"non-finite label for selected symbols on {session}")
            gross_values.append(float(values.mean()))
            trade_flags.append(True)
        else:
            gross_values.append(0.0)
            trade_flags.append(False)
    gross = pd.Series(gross_values, index=label_returns.index, dtype=float)
    traded = pd.Series(trade_flags, index=label_returns.index, dtype=bool)
    round_trip_cost = 2.0 * float(cost_bps) / 10_000.0
    net = gross - traded.astype(float) * round_trip_cost
    return net, gross, traded


def _metrics_from_returns(
    net_returns: pd.Series,
    gross_returns: pd.Series,
    traded: pd.Series,
) -> dict[str, Any]:
    equity = (1.0 + net_returns).cumprod()
    metrics = build_performance_metrics(
        [1.0, *equity.tolist()],
        "daily",
        trade_pnls=net_returns.loc[traded].tolist(),
        trade_return_pcts=(net_returns.loc[traded] * 100.0).tolist(),
        exposure_pct=float(traded.mean() * 100.0),
        turnover_ratio=float(traded.sum() * 2.0),
    )
    return {
        "total_return_pct": round(float(equity.iloc[-1] - 1.0) * 100.0, 6),
        "annualized_return_pct": _rounded(metrics.annualized_return_pct),
        "sharpe": _rounded(metrics.sharpe_ratio),
        "annualized_volatility_pct": _rounded(metrics.annualized_volatility_pct),
        "max_drawdown_pct": round(float(metrics.max_drawdown_pct), 6),
        "sortino": _rounded(metrics.sortino_ratio),
        "calmar": _rounded(metrics.calmar_ratio),
        "session_count": len(net_returns),
        "trade_day_count": int(traded.sum()),
        "exposure_pct": round(float(traded.mean() * 100.0), 6),
        "win_rate_pct": _rounded(metrics.win_rate_pct),
        "average_gross_trade_return_bps": round(
            float(gross_returns.loc[traded].mean() * 10_000.0) if traded.any() else 0.0,
            6,
        ),
        "average_net_trade_return_bps": round(
            float(net_returns.loc[traded].mean() * 10_000.0) if traded.any() else 0.0,
            6,
        ),
        "round_trip_turnover_units": float(traded.sum() * 2.0),
    }


def _build_benchmarks(
    labels: dict[str, pd.DataFrame],
    features: FeatureSet,
    folds: tuple[pd.DatetimeIndex, ...],
) -> tuple[dict[str, Any], str]:
    results: dict[str, Any] = {}
    for window, returns in labels.items():
        sessions = returns.index
        always_spy = {session: ("SPY",) for session in sessions}
        equal_sector = {session: tuple(SECTOR_SYMBOLS) for session in sessions}
        equal_stock = {session: tuple(STOCK_SYMBOLS) for session in sessions}
        cash = {session: () for session in sessions}
        best_sector = max(
            SECTOR_SYMBOLS,
            key=lambda symbol: float((1.0 + returns[symbol]).prod() - 1.0),
        )
        fixed_best = {session: (best_sector,) for session in sessions}
        reversal = {}
        for session in sessions:
            relative = features.market_relative.loc[session, list(SECTOR_SYMBOLS)]
            eligible = relative < 0
            ordered = sorted(
                [symbol for symbol in SECTOR_SYMBOLS if bool(eligible.loc[symbol])],
                key=lambda symbol: (float(relative.loc[symbol]), symbol),
            )
            reversal[session] = tuple(ordered[:3])
        benchmark_selections = {
            "SPY_same_window": always_spy,
            "equal_weight_sector_universe": equal_sector,
            "equal_weight_stock_universe": equal_stock,
            "uninvested_cash": cash,
            "ex_post_best_sector_report_only": fixed_best,
            "first_hour_reversal_control": reversal,
        }
        results[window] = {
            "ex_post_best_sector": best_sector,
            "ex_post_best_selection_eligible": False,
            "results_by_cost_bps": {
                str(int(cost)): {
                    benchmark_id: _evaluate_selection(
                        selection,
                        returns,
                        folds,
                        cost_bps=cost,
                    )
                    for benchmark_id, selection in benchmark_selections.items()
                }
                for cost in COST_SCENARIOS
            },
        }
    return results, _canonical_sha(results)


def _placebo_gate(candidate_results: dict[str, dict[str, Any]]) -> dict[str, Any]:
    parent = candidate_results["D08"]["metrics_by_cost_bps"]["5"]["aggregate"]
    placebo = candidate_results["N01"]["metrics_by_cost_bps"]["5"]["aggregate"]
    sharpe_lift = _number(placebo["sharpe"]) - _number(parent["sharpe"])
    return_lift = (placebo["total_return_pct"] - parent["total_return_pct"]) / 100.0
    passed = sharpe_lift <= 0.1 and return_lift <= 0.02
    result = {
        "passed": passed,
        "parent_candidate_id": "D08",
        "placebo_candidate_id": "N01",
        "sharpe_lift": round(sharpe_lift, 6),
        "total_return_lift": round(return_lift, 6),
        "maximum_sharpe_lift": 0.1,
        "maximum_total_return_lift": 0.02,
    }
    candidate_results["N01"]["control"] = result
    return result


def _attach_acceptance(
    candidate_results: dict[str, dict[str, Any]],
    benchmarks: dict[str, Any],
    placebo: dict[str, Any],
) -> None:
    parent_by_candidate = {
        "D04": "D02",
        "D05": "D04",
        "D06": "D02",
        "D07": "D05",
        "D08": "D02",
    }
    benchmark_by_candidate = {
        "D01": "SPY_same_window",
        "D02": "equal_weight_sector_universe",
        "D03": "equal_weight_sector_universe",
        "D04": "equal_weight_sector_universe",
        "D05": "equal_weight_sector_universe",
        "D06": "equal_weight_sector_universe",
        "D07": "equal_weight_sector_universe",
        "D08": "equal_weight_sector_universe",
        "D09": "equal_weight_stock_universe",
    }
    for candidate_id in [f"D{index:02d}" for index in range(1, 10)]:
        result = candidate_results[candidate_id]
        base = result["metrics_by_cost_bps"]["5"]
        aggregate = base["aggregate"]
        stress = result["metrics_by_cost_bps"]["20"]["aggregate"]
        positive_folds = sum(fold["total_return_pct"] > 0 for fold in base["folds"])
        label_window = result["label_window"]
        benchmark_id = benchmark_by_candidate[candidate_id]
        benchmark = benchmarks[label_window]["results_by_cost_bps"]["5"][benchmark_id]
        benchmark_sharpe = _number(benchmark["aggregate"]["sharpe"])
        parent_id = parent_by_candidate.get(candidate_id)
        parent_fold_wins = None
        if parent_id:
            parent_folds = candidate_results[parent_id]["metrics_by_cost_bps"]["5"]["folds"]
            parent_fold_wins = sum(
                current["total_return_pct"] > parent["total_return_pct"]
                for current, parent in zip(base["folds"], parent_folds, strict=True)
            )
        checks = {
            "minimum_trade_days": aggregate["trade_day_count"] >= 30,
            "minimum_positive_folds": positive_folds >= 3,
            "minimum_base_sharpe": _number(aggregate["sharpe"]) >= 0.5,
            "maximum_drawdown": aggregate["max_drawdown_pct"] >= -15.0,
            "positive_at_20bps": stress["total_return_pct"] > 0,
            "beats_declared_benchmark_sharpe": _number(aggregate["sharpe"]) > benchmark_sharpe,
            "parent_fold_improvement": parent_fold_wins is None or parent_fold_wins >= 3,
            "placebo_family_gate": bool(placebo["passed"]),
        }
        result["acceptance"] = {
            "passed": all(checks.values()),
            "checks": checks,
            "positive_fold_count": positive_folds,
            "declared_benchmark": benchmark_id,
            "benchmark_base_sharpe": _rounded(benchmark_sharpe),
            "parent_candidate_id": parent_id,
            "parent_fold_win_count": parent_fold_wins,
            "historical_selection_authority": False,
        }
    for candidate_id in ("E01", "E02", "E03", "E04"):
        candidate_results[candidate_id]["acceptance"] = {
            "passed": False,
            "reason": "dependency skipped",
        }
    candidate_results["N01"]["acceptance"] = {
        "passed": bool(placebo["passed"]),
        "selection_prohibited": True,
        "reason": "mandatory shuffled-score placebo",
    }
    candidate_results["N02"]["acceptance"] = {
        "passed": bool(candidate_results["N02"]["control"]["mandatory_outcome_met"]),
        "selection_prohibited": True,
        "reason": "mandatory future-feature rejection",
    }


def _future_feature_control() -> dict[str, Any]:
    decision_at = pd.Timestamp("2026-01-05T15:30:00Z")
    feature_at = decision_at + pd.Timedelta(microseconds=1)
    rejected = False
    try:
        _assert_feature_availability(feature_at, decision_at)
    except FutureFeatureError:
        rejected = True
    return {
        "feature_name": "future_close",
        "decision_at": decision_at.isoformat(),
        "feature_visible_at": feature_at.isoformat(),
        "outcome": "rejected_control" if rejected else "accepted_in_error",
        "mandatory_outcome": "rejected_control",
        "mandatory_outcome_met": rejected,
    }


def _assert_feature_availability(
    feature_visible_at: pd.Timestamp,
    decision_at: pd.Timestamp,
) -> None:
    if feature_visible_at > decision_at:
        raise FutureFeatureError("feature is visible after the decision boundary")


def _pbo_diagnostic(candidate_results: dict[str, dict[str, Any]]) -> dict[str, Any]:
    candidate_ids = [f"D{index:02d}" for index in range(1, 10)]
    fold_values = {
        candidate_id: [
            fold["total_return_pct"]
            for fold in candidate_results[candidate_id]["metrics_by_cost_bps"]["5"]["folds"]
        ]
        for candidate_id in candidate_ids
    }
    rows = []
    below_median = 0
    for held_out in range(OUTER_FOLDS):
        training_scores = {
            candidate_id: float(
                np.mean([value for index, value in enumerate(values) if index != held_out])
            )
            for candidate_id, values in fold_values.items()
        }
        winner = max(candidate_ids, key=lambda value: (training_scores[value], value))
        held_out_scores = {
            candidate_id: fold_values[candidate_id][held_out] for candidate_id in candidate_ids
        }
        ordered = sorted(
            candidate_ids,
            key=lambda value: (held_out_scores[value], value),
            reverse=True,
        )
        rank = ordered.index(winner) + 1
        is_below = rank > math.ceil(len(candidate_ids) / 2)
        below_median += int(is_below)
        rows.append(
            {
                "held_out_fold": held_out + 1,
                "development_winner": winner,
                "held_out_rank": rank,
                "held_out_candidate_count": len(candidate_ids),
                "below_median": is_below,
            }
        )
    return {
        "method": "four_fold_leave_one_slice_out_rank_diagnostic",
        "pbo": round(below_median / OUTER_FOLDS, 6),
        "rows": rows,
        "limitations": "Diagnostic proxy on four chronological slices, not CSCV proof.",
    }


def _dsr_proxy(candidate_results: dict[str, dict[str, Any]]) -> dict[str, Any]:
    values = np.asarray(
        [
            _number(
                candidate_results[f"D{index:02d}"]["metrics_by_cost_bps"]["5"]["aggregate"][
                    "sharpe"
                ]
            )
            for index in range(1, 10)
        ],
        dtype=float,
    )
    mean = float(values.mean())
    std = float(values.std(ddof=1)) if len(values) > 1 else 0.0
    expected_max = mean + std * math.sqrt(2.0 * math.log(len(values)))
    observed_max = float(values.max())
    return {
        "method": "expected_max_sharpe_proxy",
        "trial_count": len(values),
        "mean_candidate_sharpe": round(mean, 6),
        "candidate_sharpe_std": round(std, 6),
        "expected_max_sharpe": round(expected_max, 6),
        "observed_max_sharpe": round(observed_max, 6),
        "observed_minus_expected": round(observed_max - expected_max, 6),
        "limitations": "Not a full non-normal Deflated Sharpe Ratio significance test.",
    }


def _diagnostic_leader(candidate_results: dict[str, dict[str, Any]]) -> dict[str, Any]:
    candidate_ids = [f"D{index:02d}" for index in range(1, 10)]
    leader = max(
        candidate_ids,
        key=lambda candidate_id: (
            _number(
                candidate_results[candidate_id]["metrics_by_cost_bps"]["5"]["aggregate"]["sharpe"]
            ),
            candidate_id,
        ),
    )
    metrics = candidate_results[leader]["metrics_by_cost_bps"]["5"]["aggregate"]
    return {
        "candidate_id": leader,
        "base_one_way_cost_bps": 5.0,
        "total_return_pct": metrics["total_return_pct"],
        "sharpe": metrics["sharpe"],
        "max_drawdown_pct": metrics["max_drawdown_pct"],
        "report_only": True,
    }


def _fold_rows(folds: tuple[pd.DatetimeIndex, ...]) -> list[dict[str, Any]]:
    return [
        {
            "fold": index,
            "start": fold.min().date().isoformat(),
            "end": fold.max().date().isoformat(),
            "session_count": len(fold),
            "evidence_role": "chronological_diagnostic_slice_not_pristine_OOS",
        }
        for index, fold in enumerate(folds, start=1)
    ]


def _write_decision_record(root: Path, payload: dict[str, Any]) -> None:
    placebo_pass = payload["multiple_testing"]["quant_score_placebo"]["passed"]
    forward_ids = payload["forward_observation_candidate_ids"]
    if forward_ids:
        quant_decision = "continue observation"
        quant_reason = (
            f"Candidate {forward_ids[0]} met the frozen diagnostic checks, but only for "
            "broker-free forward observation. Historical IEX evidence remains non-promotional."
        )
    else:
        quant_decision = "stop"
        quant_reason = (
            "No deterministic candidate cleared every frozen cost, fold, benchmark, drawdown, "
            f"and placebo gate. Placebo pass was {placebo_pass}."
        )
    lines = [
        f"# Decision Record: {ITER_ID}",
        "",
        "## Deterministic Intraday Path",
        "",
        "- Path: Nine fixed 30-minute market, sector, and stock intraday candidates.",
        f"- Decision: {quant_decision}.",
        f"- Reason: {quant_reason}",
        (
            "- Next iteration suggestion: Do not broaden parameters. Collect formal-forward "
            "observations only for the named candidate, if any, and obtain independent "
            "consolidated-data parity before reconsideration."
        ),
        "",
        "## Filing And News Path",
        "",
        "- Path: Filing-only, news-only, combined, and stale/shuffled event candidates.",
        "- Decision: stop historical execution; continue data acquisition only.",
        (
            "- Reason: All four candidates were dependency-skipped because real historical "
            "PIT packets do not exist. Fixtures and retrospective LLM output were not "
            "substituted."
        ),
        (
            "- Next iteration suggestion: Configure a compliant SEC contact identity and an "
            "approved news credential, then build forward packets with publication, fetch, "
            "visibility, source, input, prompt, dedupe, and evidence-span provenance."
        ),
        "",
        "## Conference Calls And AI",
        "",
        "- Path: Prepared remarks, Q&A, guidance, and audio-derived factors.",
        "- Decision: stop.",
        (
            "- Reason: No licensed transcript or audio provider is registered. R5 trained no "
            "model and made no live LLM call; AI participation was limited to research, "
            "deterministic implementation, and review."
        ),
        (
            "- Next iteration suggestion: Evaluate provider rights and timestamp coverage "
            "before adding any counted call candidate. Preserve a lexical baseline and "
            "missing-modality fallback."
        ),
        "",
        "## Paper Simulation",
        "",
        "- Path: Simulated-order activation.",
        "- Decision: stop.",
        (
            "- Reason: `workflow_pass=true`, `research_pass=false`, "
            "`llm_contribution_pass=false`, and `paper_ready_pass=false`; formal-forward "
            "evidence, SIP parity, matched intraday TCA, and paper safety review are absent."
        ),
        (
            "- Next iteration suggestion: Keep broker authority false until every promotion "
            "and safety blocker is closed."
        ),
    ]
    text = "\n".join(lines).rstrip() + "\n"
    (root / ITERATION_DIR / "decision-record.md").write_text(text, encoding="utf-8")


def _render_evaluation_markdown(payload: dict[str, Any]) -> str:
    leader = payload["diagnostic_leader"]
    placebo = payload["multiple_testing"]["quant_score_placebo"]
    lines = [
        f"# R5 Multiscale Event Momentum Evaluation: {payload['run_id']}",
        "",
        "## Outcome",
        "",
        f"- Workflow pass: `{payload['workflow_pass']}`",
        f"- Research pass: `{payload['research_pass']}`",
        f"- LLM contribution pass: `{payload['llm_contribution_pass']}`",
        f"- Paper-ready pass: `{payload['paper_ready_pass']}`",
        f"- Diagnostic leader: `{leader['candidate_id']}` (report only)",
        f"- Leader total return at 5 bps one-way: `{leader['total_return_pct']}%`",
        f"- Leader Sharpe at 5 bps one-way: `{leader['sharpe']}`",
        f"- Leader max drawdown: `{leader['max_drawdown_pct']}%`",
        f"- Shuffled-score placebo pass: `{placebo['passed']}`",
        f"- Forward-observation candidates: `{payload['forward_observation_candidate_ids']}`",
        "",
        "## Accounting",
        "",
        f"- Frozen candidates: `{payload['candidate_count']}`",
        f"- Completed diagnostics: `{payload['completed_candidate_count']}`",
        f"- Dependency-skipped event candidates: `{payload['dependency_skipped_count']}`",
        f"- Rejected controls: `{payload['rejected_control_count']}`",
        "",
        "## Boundary",
        "",
        "These results use a current, survivorship-labelled basket and Alpaca Basic IEX bars. "
        "They cannot establish point-in-time stock-selection alpha, consolidated execution "
        "quality, event-factor lift, or paper readiness.",
        "",
        "## Promotion Blockers",
        "",
    ]
    lines.extend(f"- `{blocker}`" for blocker in payload["promotion_blockers"])
    return "\n".join(lines).rstrip() + "\n"


def _input_bundle_payload(panel: SessionPanel) -> dict[str, Any]:
    return {
        "aggregation_contract": "strict_complete_15m_pairs_to_30m_v1",
        "required_anchors": list(REQUIRED_ANCHORS),
        "common_sessions": [session.date().isoformat() for session in panel.sessions],
        "input_files": [dict(row) for row in panel.source_rows],
    }


def _artifact_binding(path: Path, root: Path) -> dict[str, Any]:
    return {
        "path": str(path.relative_to(root)),
        "sha256": _sha256_file(path),
    }


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ContractViolation(f"JSON artifact is not an object: {path}")
    return payload


def _require_finite_frame(frame: pd.DataFrame, name: str) -> None:
    if frame.empty or not np.isfinite(frame.to_numpy(dtype=float)).all():
        raise ContractViolation(f"{name} contains missing or non-finite values")


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_sha(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _frame_sha(frame: pd.DataFrame) -> str:
    payload = {
        "index": [str(value) for value in frame.index],
        "columns": [str(value) for value in frame.columns],
        "values": frame.astype(float).round(12).values.tolist(),
    }
    return _canonical_sha(payload)


def _series_sha(series: pd.Series) -> str:
    payload = {
        "index": [str(value) for value in series.index],
        "values": series.astype(float).round(12).tolist(),
    }
    return _canonical_sha(payload)


def _rounded(value: float | None) -> float | None:
    return None if value is None or not math.isfinite(value) else round(float(value), 6)


def _number(value: float | None) -> float:
    return float(value) if value is not None and math.isfinite(value) else -math.inf
