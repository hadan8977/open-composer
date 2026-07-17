from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from open_composer.adapters.data.sample import normalize_ohlcv
from open_composer.config import ensure_dir, project_root
from open_composer.research.minute_momentum_feasibility import (
    run_minute_momentum_feasibility,
)
from open_composer.research.research_cache_manifest import sha256_file
from open_composer.research.stock_momentum_q2_contract import build_q2_execution_map
from open_composer.storage import write_json

ITER_ID = "mom_stock_intraday_codesign_q1"
OUTPUT_DIR = Path("reports/research/iterations") / ITER_ID
DEFAULT_SNAPSHOT_PATH = Path("data/research/multiasset_momentum/nasdaq-current-stock-snapshot.json")
FORMAL_FORWARD_EPOCH = "2026-07-15T00:00:00Z"
DEFAULT_INTRADAY_SYMBOLS = (
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
DAILY_BENCHMARK_SYMBOLS = ("SPY", "XLK", "BIL")
SYMBOL_RE = re.compile(r"^[A-Z]{1,5}$")
EXCLUDED_NAME_MARKERS = (
    " ETF",
    " ETN",
    " WARRANT",
    " WTS",
    " UNIT",
    " RIGHTS",
    " PREFERRED",
    " DEPOSITARY",
    " ACQUISITION CORP",
)
MAX_DIAGNOSTIC_INVALID_OHLC_ROWS = 1
MAX_DIAGNOSTIC_PANEL_FIELD_ANOMALIES = 20
MAX_DIAGNOSTIC_FIELD_ANOMALY_SESSIONS = 1
MAX_DIAGNOSTIC_FIELD_ANOMALY_RATIO = 0.001


@dataclass(frozen=True)
class StockMomentumFeasibilityResult:
    json_path: Path
    markdown_path: Path
    parent_universe_path: Path
    daily_manifest_path: Path
    intraday_manifest_path: Path
    cost_contract_path: Path
    payload: dict[str, Any]


def run_stock_momentum_data_feasibility(
    root: Path | None = None,
    *,
    snapshot_path: Path | None = None,
    intraday_symbols: list[str] | None = None,
    daily_min_symbols: int = 60,
    daily_max_symbols: int = 80,
    daily_min_records: int = 900,
    intraday_min_history_months: float = 18.0,
    intraday_min_sessions: int = 252,
    intraday_max_gap_rate: float = 0.02,
) -> StockMomentumFeasibilityResult:
    base = root or project_root()
    output = ensure_dir(base / OUTPUT_DIR)
    source_snapshot = _resolve_input(base, snapshot_path or DEFAULT_SNAPSHOT_PATH)
    snapshot = _load_json_object(source_snapshot)
    rows = snapshot.get("rows")
    if not isinstance(rows, list) or len(rows) < 1:
        raise ValueError("Nasdaq snapshot requires a non-empty rows array")
    parent_rows, selection_funnel, rejection_reasons = _build_parent_universe(rows)
    parent_rows.sort(
        key=lambda row: (float(row["market_cap"]), float(row["snapshot_dollar_volume"])),
        reverse=True,
    )
    if not 500 <= len(parent_rows) <= 1500:
        raise ValueError(
            "current Nasdaq parent universe must contain between 500 and 1500 eligible stocks"
        )

    parent_universe_path = output / "parent-universe.json"
    parent_payload = {
        "schema_version": 1,
        "iter_id": ITER_ID,
        "generated_at": datetime.now(UTC).isoformat(),
        "snapshot_path": _relpath(source_snapshot, base),
        "snapshot_sha256": sha256_file(source_snapshot),
        "snapshot_generated_at": snapshot.get("generated_at"),
        "snapshot_record_count": len(rows),
        "parent_count": len(parent_rows),
        "selection_contract": {
            "country": "United States",
            "symbol_pattern": SYMBOL_RE.pattern,
            "minimum_price": 10.0,
            "minimum_market_cap": 5_000_000_000.0,
            "minimum_snapshot_volume": 500_000.0,
            "excluded_security_name_markers": list(EXCLUDED_NAME_MARKERS),
        },
        "selection_funnel": selection_funnel,
        "rejection_reasons": rejection_reasons,
        "membership_status": "current_snapshot_forward_parent_only",
        "historical_membership_pit": False,
        "rows": parent_rows,
    }
    write_json(parent_universe_path, parent_payload)

    daily_rows = [
        quality
        for row in parent_rows
        if (quality := _daily_quality_row(base, row, min_records=daily_min_records)) is not None
    ]
    quality_daily = [row for row in daily_rows if row["quality_pass"]]
    quality_daily.sort(
        key=lambda row: (
            -float(row.get("median_dollar_volume_60") or 0.0),
            -float(row.get("market_cap") or 0.0),
            str(row.get("symbol") or ""),
        ),
    )
    selected_daily = _sector_capped(quality_daily, daily_max_symbols, per_sector=15)
    daily_field_anomalies = [
        {
            "symbol": str(row["symbol"]),
            "timestamp": timestamp,
            "quarantined_fields": ["high", "low"],
        }
        for row in selected_daily
        for timestamp in row.get("invalid_ohlc_timestamps", [])
    ]
    daily_anomaly_sessions = sorted(
        {pd.Timestamp(item["timestamp"]).date().isoformat() for item in daily_field_anomalies}
    )
    daily_panel_observations = sum(int(row.get("records") or 0) for row in selected_daily)
    daily_anomaly_ratio = (
        len(daily_field_anomalies) / daily_panel_observations if daily_panel_observations else 1.0
    )
    daily_anomaly_budget_pass = bool(
        len(daily_field_anomalies) <= MAX_DIAGNOSTIC_PANEL_FIELD_ANOMALIES
        and len(daily_anomaly_sessions) <= MAX_DIAGNOSTIC_FIELD_ANOMALY_SESSIONS
        and daily_anomaly_ratio <= MAX_DIAGNOSTIC_FIELD_ANOMALY_RATIO
    )
    daily_benchmark_inputs = [
        _daily_benchmark_input(base, symbol, min_records=daily_min_records)
        for symbol in DAILY_BENCHMARK_SYMBOLS
    ]
    daily_runtime_alignment = _daily_runtime_alignment(
        base,
        selected_daily,
        daily_benchmark_inputs,
    )
    daily_diagnostic_go = bool(
        len(selected_daily) >= daily_min_symbols
        and daily_anomaly_budget_pass
        and all(row["runtime_input_eligible"] for row in daily_benchmark_inputs)
        and daily_runtime_alignment["common_timestamp_count"] >= daily_min_records
    )
    cache_inventory = _daily_cache_inventory(base)
    daily_manifest_path = output / "daily-panel-manifest.json"
    daily_manifest = {
        "schema_version": 1,
        "iter_id": ITER_ID,
        "generated_at": datetime.now(UTC).isoformat(),
        "provider": "longbridge",
        "feed": "nasdaq_basic",
        "adjusted_requested": True,
        "source_scope": "local_research_cache_only",
        "parent_universe_path": _relpath(parent_universe_path, base),
        "parent_universe_sha256": sha256_file(parent_universe_path),
        "cache_inventory": cache_inventory,
        "cached_parent_symbols": len(daily_rows),
        "quality_pass_count": len(quality_daily),
        "selected_count": len(selected_daily),
        "selected_symbols": [str(row["symbol"]) for row in selected_daily],
        "sector_counts": dict(Counter(str(row["sector"]) for row in selected_daily)),
        "selection_policy": {
            "eligible_rows": "quality_pass_true",
            "sort": ["median_dollar_volume_60_desc", "market_cap_desc", "symbol_asc"],
            "maximum_symbols": daily_max_symbols,
            "maximum_per_sector": 15,
            "share_class_policy": "distinct_listings_no_issuer_aggregation",
        },
        "runtime_cross_section": {
            "rank_universe": "selected_symbols_exact",
            "breadth_universe": "selected_symbols_exact",
            "dispersion_universe": "selected_symbols_exact",
            "symbol_count": len(selected_daily),
        },
        "benchmark_inputs": daily_benchmark_inputs,
        "runtime_alignment": daily_runtime_alignment,
        "minimum_selected_symbols": daily_min_symbols,
        "maximum_selected_symbols": daily_max_symbols,
        "minimum_records": daily_min_records,
        "data_cleaning_policy": {
            "invalid_ohlc_rows_max_per_symbol": MAX_DIAGNOSTIC_INVALID_OHLC_ROWS,
            "maximum_panel_field_anomalies": MAX_DIAGNOSTIC_PANEL_FIELD_ANOMALIES,
            "maximum_affected_sessions": MAX_DIAGNOSTIC_FIELD_ANOMALY_SESSIONS,
            "maximum_panel_field_anomaly_ratio": MAX_DIAGNOSTIC_FIELD_ANOMALY_RATIO,
            "action": "quarantine_high_low_fields_only",
            "candidate_required_fields": ["open", "close", "volume"],
            "high_low_dependent_candidates_allowed": False,
            "forward_fill_allowed": False,
            "scope": "diagnostic_only",
        },
        "q2_global_excluded_sessions": [],
        "q2_field_anomalies": daily_field_anomalies,
        "field_anomaly_session_count": len(daily_anomaly_sessions),
        "field_anomaly_ratio": round(daily_anomaly_ratio, 8),
        "field_anomaly_budget_pass": daily_anomaly_budget_pass,
        "panel_content_frozen": True,
        "historical_diagnostic_go": daily_diagnostic_go,
        "historical_research_qualified": False,
        "formal_forward_epoch": FORMAL_FORWARD_EPOCH,
        "rows": daily_rows,
        "blockers": [
            "point_in_time_membership_missing",
            "inactive_and_delisted_securities_missing",
            "terminal_delisting_returns_missing",
            "permanent_instrument_identity_missing",
            "corporate_action_lineage_not_immutable",
            "provider_rights_and_entitlement_artifact_missing",
            "nasdaq_basic_is_not_consolidated_sip",
            *(
                ["benchmark_acquisition_manifest_lineage_incomplete"]
                if any(
                    row["manifest_runtime_cache_matches"] is not True
                    for row in daily_benchmark_inputs
                )
                else []
            ),
            *(
                ["no_formal_forward_epoch_observations"]
                if daily_runtime_alignment["formal_forward_observation_count"] == 0
                else []
            ),
        ],
    }
    write_json(daily_manifest_path, daily_manifest)

    selected_intraday = [
        symbol.upper() for symbol in (intraday_symbols or list(DEFAULT_INTRADAY_SYMBOLS))
    ]
    minute_report_date = f"{ITER_ID}-q1"
    minute_payload = _load_reusable_minute_payload(
        base,
        report_date=minute_report_date,
        symbols=selected_intraday,
        feed="iex",
        max_rth_gap_rate=intraday_max_gap_rate,
    )
    minute_payload_reused = minute_payload is not None
    if minute_payload is None:
        minute_result = run_minute_momentum_feasibility(
            base,
            symbols=selected_intraday,
            representative_symbols=selected_intraday,
            timeframes=["15m"],
            feed="iex",
            fetch_missing=False,
            report_date=minute_report_date,
            required_symbol_coverage_threshold=1.0,
            max_rth_gap_rate=intraday_max_gap_rate,
        )
        minute_payload = minute_result.payload
    intraday_rows = [_with_intraday_action_boundaries(base, row) for row in minute_payload["rows"]]
    intraday_excluded_sessions = sorted(
        {session for row in intraday_rows for session in row.get("q2_excluded_sessions", [])}
    )
    intraday_alignment = _intraday_panel_alignment(
        base,
        intraday_rows,
        excluded_sessions=set(intraday_excluded_sessions),
    )
    intraday_panel_complete = (
        len(intraday_rows) == len(selected_intraday)
        and all(
            _intraday_row_pass(
                row,
                min_history_months=intraday_min_history_months,
                min_sessions=intraday_min_sessions,
                max_gap_rate=intraday_max_gap_rate,
            )
            for row in intraday_rows
        )
        and intraday_alignment["verified"] is True
        and intraday_alignment["common_session_count"] >= intraday_min_sessions
        and intraday_alignment.get("common_timestamp_ratio") == 1.0
    )
    last_timestamps = [
        pd.Timestamp(row["last_timestamp"])
        for row in intraday_rows
        if row.get("status") == "ok" and row.get("last_timestamp")
    ]
    source_manifest_drift_symbols = [
        str(row.get("symbol"))
        for row in intraday_rows
        if row.get("source_manifest_matches") is not True
    ]
    intraday_blockers = [
        "iex_is_not_consolidated_sip",
        "provider_rights_and_entitlement_artifact_missing",
        "spread_and_market_impact_evidence_missing",
        "intraday_corporate_action_lineage_missing",
        "current_symbol_history_is_survivorship_prone",
        "cache_is_stale_for_forward_observation",
    ]
    if source_manifest_drift_symbols:
        intraday_blockers.append("source_acquisition_manifest_drift")
    intraday_manifest_path = output / "intraday-panel-manifest.json"
    intraday_manifest = {
        "schema_version": 1,
        "iter_id": ITER_ID,
        "generated_at": datetime.now(UTC).isoformat(),
        "provider": "alpaca",
        "feed": "iex",
        "timeframe": "15m",
        "source_timeframe": "1m",
        "timestamp_label": "start",
        "minute_feasibility_reused": minute_payload_reused,
        "resampling_code_sha256": sha256_file(
            Path(__file__).with_name("minute_momentum_feasibility.py")
        ),
        "required_symbols": selected_intraday,
        "required_symbol_count": len(selected_intraday),
        "available_symbol_count": sum(row.get("status") == "ok" for row in intraday_rows),
        "minimum_history_months": intraday_min_history_months,
        "minimum_sessions": intraday_min_sessions,
        "maximum_session_grid_gap_rate": intraday_max_gap_rate,
        "historical_diagnostic_go": intraday_panel_complete,
        "historical_research_qualified": False,
        "forward_observation_ready": False,
        "common_data_as_of": min(last_timestamps).isoformat() if last_timestamps else None,
        "latest_symbol_data_as_of": max(last_timestamps).isoformat() if last_timestamps else None,
        "panel_content_frozen": all(
            row.get("materialized_content_matches") is True for row in intraday_rows
        ),
        "source_manifest_match_count": sum(
            row.get("source_manifest_matches") is True for row in intraday_rows
        ),
        "source_manifest_drift_symbols": source_manifest_drift_symbols,
        "q2_excluded_sessions": intraday_excluded_sessions,
        "cross_symbol_alignment": intraday_alignment,
        "corporate_action_policy": (
            "Mask only the detected discontinuity session in diagnostics. The preceding "
            "session is retained because excluding it would use the next open; the heuristic "
            "does not establish provider adjustment lineage."
        ),
        "rows": intraday_rows,
        "blockers": intraday_blockers,
    }
    write_json(intraday_manifest_path, intraday_manifest)

    event_gate = _event_capability_gate(base)
    cost_contract_path = output / "cost-contract.json"
    cost_contract = {
        "schema_version": 1,
        "iter_id": ITER_ID,
        "daily_cost_v1": {
            "one_way_bps": [10.0, 20.0, 40.0],
            "selection_bps": 10.0,
            "model": "turnover_times_one_way_cost",
        },
        "intraday_cost_v1": {
            "one_way_bps": [8.0, 16.0, 32.0],
            "selection_bps": 16.0,
            "model": "turnover_times_one_way_cost",
        },
        "event_cost_v1": {
            "one_way_bps": [15.0, 30.0, 60.0],
            "selection_bps": 30.0,
            "model": "matched_daily_portfolio_cost",
        },
        "limitations": [
            "No local quote-level spread or market-impact calibration is available.",
            "All candidate evaluations must include base, 2x, and 4x cost stress.",
        ],
    }
    write_json(cost_contract_path, cost_contract)

    candidate_manifest_path = output / "candidate-manifest.json"
    q2_execution_map_path = output / "q2-execution-map.json"
    q2_execution_map = build_q2_execution_map(_load_json_object(candidate_manifest_path))
    write_json(q2_execution_map_path, q2_execution_map)

    path_gates = {
        "deterministic_daily": _diagnostic_path_gate(
            daily_diagnostic_go,
            daily_manifest_path,
            base,
            candidate_ids=[f"D{index:02d}" for index in range(1, 13)],
        ),
        "ml_native_daily": _diagnostic_path_gate(
            daily_diagnostic_go,
            daily_manifest_path,
            base,
            candidate_ids=[f"M{index:02d}" for index in range(1, 17)],
        ),
        "intraday_independent": _diagnostic_path_gate(
            False,
            intraday_manifest_path,
            base,
            candidate_ids=[f"I{index:02d}" for index in range(1, 13)],
            blocked_reason=(
                "Q.2 is preregistered as a daily-only diagnostic wave; intraday candidates "
                "remain dependency-skipped even if a synthetic or future panel passes quality."
            ),
        ),
        "event_llm": {
            "q2_action": "dependency_skipped",
            "historical_diagnostic_go": False,
            "historical_research_qualified": False,
            "candidate_ids": [f"E{index:02d}" for index in range(1, 9)],
            "reason": "No authorized immutable PIT document/news corpus is locally available.",
            "evidence_path": None,
        },
    }
    q2_authorized = daily_diagnostic_go
    runnable_candidate_count = 12 + 16 if daily_diagnostic_go else 0
    q2_authorization_rows = _candidate_authorization_rows(base, path_gates)
    payload = {
        "schema_version": 1,
        "report_type": "stock_intraday_momentum_data_feasibility",
        "iter_id": ITER_ID,
        "generated_at": datetime.now(UTC).isoformat(),
        "status": "complete_with_external_blockers" if q2_authorized else "blocked",
        "workflow_pass": True,
        "research_pass": False,
        "llm_contribution_pass": False,
        "paper_ready_pass": False,
        "q2_diagnostic_execution_authorized": q2_authorized,
        "parent_universe": {
            "path": _relpath(parent_universe_path, base),
            "sha256": sha256_file(parent_universe_path),
            "count": len(parent_rows),
            "historical_membership_pit": False,
        },
        "daily_panel": {
            "path": _relpath(daily_manifest_path, base),
            "sha256": sha256_file(daily_manifest_path),
            "selected_count": len(selected_daily),
            "runtime_common_timestamp_count": daily_runtime_alignment["common_timestamp_count"],
            "runtime_last_timestamp": daily_runtime_alignment["last_common_timestamp"],
            "diagnostic_go": daily_diagnostic_go,
        },
        "intraday_panel": {
            "path": _relpath(intraday_manifest_path, base),
            "sha256": sha256_file(intraday_manifest_path),
            "selected_count": len(selected_intraday),
            "panel_quality_go": intraday_panel_complete,
            "q2_diagnostic_go": False,
        },
        "event_and_llm": event_gate,
        "cost_contract": {
            "path": _relpath(cost_contract_path, base),
            "sha256": sha256_file(cost_contract_path),
        },
        "q2_execution_map": {
            "path": _relpath(q2_execution_map_path, base),
            "sha256": sha256_file(q2_execution_map_path),
        },
        "path_gates": path_gates,
        "q2_authorization": {
            "candidate_count": len(q2_authorization_rows),
            "rows": q2_authorization_rows,
        },
        "candidate_accounting": {
            "frozen_candidate_count": 48,
            "diagnostic_runnable_count": runnable_candidate_count,
            "dependency_skipped_count": 48 - runnable_candidate_count,
            "unresolved_count": 0,
            "balanced": runnable_candidate_count + (48 - runnable_candidate_count) == 48,
        },
        "global_blockers": [
            "historical_stock_membership_is_not_point_in_time",
            "delisting_and_symbol_mapping_history_missing",
            "provider_rights_not_verified",
            "market_feeds_are_not_consolidated_sip",
            "corporate_action_lineage_not_immutable",
            "event_news_macro_pit_corpus_unavailable",
            "benchmark_acquisition_manifest_lineage_incomplete",
            "no_formal_forward_epoch_observations",
        ],
        "interpretation": (
            "Q.2 may run only path_gates marked run_diagnostic on the frozen local data. "
            "Those results can reject designs but cannot establish research_pass or "
            "paper readiness."
        ),
    }
    json_path = output / "data-feasibility.json"
    markdown_path = output / "data-feasibility.md"
    write_json(json_path, payload)
    markdown_path.write_text(_render_markdown(payload), encoding="utf-8")
    search_space_path = output / "search-space.json"
    if search_space_path.exists():
        search_space = _load_json_object(search_space_path)
        search_space["candidate_manifest_sha256"] = sha256_file(candidate_manifest_path)
        search_space["data_feasibility_sha256"] = sha256_file(json_path)
        write_json(search_space_path, search_space)
    return StockMomentumFeasibilityResult(
        json_path=json_path,
        markdown_path=markdown_path,
        parent_universe_path=parent_universe_path,
        daily_manifest_path=daily_manifest_path,
        intraday_manifest_path=intraday_manifest_path,
        cost_contract_path=cost_contract_path,
        payload=payload,
    )


def _candidate_authorization_rows(
    root: Path,
    path_gates: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    reason_codes = {
        "deterministic_daily": "daily_diagnostic_panel_gate",
        "ml_native_daily": "daily_diagnostic_panel_gate",
        "intraday_independent": "q2_daily_scope_dependency_gate",
        "event_llm": "event_pit_corpus_gate",
    }
    manifest_path = root / OUTPUT_DIR / "candidate-manifest.json"
    manifest = _load_json_object(manifest_path)
    candidates = manifest.get("candidates")
    if not isinstance(candidates, list):
        raise ValueError("candidate manifest requires a candidates array")
    candidate_by_id = {
        str(candidate.get("candidate_id") or ""): candidate
        for candidate in candidates
        if isinstance(candidate, dict)
    }
    rows = []
    for path_name, gate in path_gates.items():
        for candidate_id in gate.get("candidate_ids", []):
            candidate = candidate_by_id.get(str(candidate_id))
            if candidate is None:
                raise ValueError(f"authorization candidate missing from manifest: {candidate_id}")
            evidence_raw = gate.get("evidence_path")
            evidence_path = root / str(evidence_raw or "") if evidence_raw else None
            rows.append(
                {
                    "candidate_id": str(candidate_id),
                    "path": path_name,
                    "action": gate["q2_action"],
                    "reason_code": reason_codes[path_name],
                    "candidate_binding_sha256": hashlib.sha256(
                        json.dumps(candidate, sort_keys=True, separators=(",", ":")).encode()
                    ).hexdigest(),
                    "evidence_path": evidence_raw,
                    "evidence_sha256": sha256_file(evidence_path)
                    if evidence_path is not None and evidence_path.is_file()
                    else None,
                }
            )
    return sorted(rows, key=lambda row: str(row["candidate_id"]))


def _build_parent_universe(
    rows: list[Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, int]]:
    stages = (
        "structured_record",
        "us_country",
        "common_stock_proxy",
        "minimum_price",
        "minimum_market_cap",
        "minimum_snapshot_liquidity",
    )
    passed = Counter({"raw_snapshot": len(rows)})
    rejected: Counter[str] = Counter()
    normalized: list[dict[str, Any]] = []
    for row in rows:
        item, reason, passed_stages = _normalize_security(row)
        passed.update(passed_stages)
        if item is None:
            rejected[reason or "unknown"] += 1
        else:
            normalized.append(item)
    funnel = []
    previous = len(rows)
    for stage in ("raw_snapshot", *stages):
        count = int(passed[stage])
        funnel.append(
            {
                "stage": stage,
                "count": count,
                "removed_from_previous": previous - count if stage != "raw_snapshot" else 0,
            }
        )
        previous = count
    return normalized, funnel, dict(sorted(rejected.items()))


def _normalize_security(
    row: Any,
) -> tuple[dict[str, Any] | None, str | None, list[str]]:
    passed: list[str] = []
    if not isinstance(row, dict):
        return None, "invalid_record", passed
    passed.append("structured_record")
    symbol = str(row.get("symbol") or "").strip().upper()
    name = str(row.get("name") or "").strip()
    if str(row.get("country") or "").strip() != "United States":
        return None, "non_us_country", passed
    passed.append("us_country")
    if not SYMBOL_RE.fullmatch(symbol):
        return None, "unsupported_symbol_shape", passed
    if any(marker in name.upper() for marker in EXCLUDED_NAME_MARKERS):
        return None, "non_common_security_name", passed
    passed.append("common_stock_proxy")
    price = _number(row.get("lastsale"))
    volume = _number(row.get("volume"))
    market_cap = _number(row.get("marketCap"))
    if price < 10:
        return None, "below_minimum_price", passed
    passed.append("minimum_price")
    if market_cap < 5_000_000_000:
        return None, "below_minimum_market_cap", passed
    passed.append("minimum_market_cap")
    if volume < 500_000:
        return None, "below_minimum_snapshot_liquidity", passed
    passed.append("minimum_snapshot_liquidity")
    return (
        {
            "symbol": symbol,
            "name": name,
            "sector": str(row.get("sector") or "Unknown").strip() or "Unknown",
            "industry": str(row.get("industry") or "Unknown").strip() or "Unknown",
            "market_cap": market_cap,
            "snapshot_price": price,
            "snapshot_volume": volume,
            "snapshot_dollar_volume": price * volume,
        },
        None,
        passed,
    )


def _daily_quality_row(
    root: Path,
    parent_row: dict[str, Any],
    *,
    min_records: int,
) -> dict[str, Any] | None:
    symbol = str(parent_row["symbol"])
    cache_path = root / "data/cache" / f"{symbol.lower()}_daily_longbridge_nasdaq_basic.csv"
    manifest_path = (
        root / "data/cache/manifests" / f"{symbol.lower()}_daily_longbridge_nasdaq_basic.json"
    )
    if not cache_path.exists() and not manifest_path.exists():
        return None
    row: dict[str, Any] = {
        **parent_row,
        "cache_path": _relpath(cache_path, root),
        "manifest_path": _relpath(manifest_path, root),
        "quality_pass": False,
    }
    if not cache_path.exists() or not manifest_path.exists():
        row["error"] = "cache_manifest_drift"
        return row
    try:
        manifest = _load_json_object(manifest_path)
        frame = normalize_ohlcv(pd.read_csv(cache_path))
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        row["error"] = str(exc)
        return row
    timestamps = pd.to_datetime(frame["timestamp"], utc=True)
    duplicate_count = int(timestamps.duplicated().sum())
    required_field_valid = frame[["open", "close"]].gt(0).all(axis=1) & frame["volume"].ge(0)
    envelope_valid = (
        frame[["high", "low"]].gt(0).all(axis=1)
        & frame["high"].ge(frame[["open", "close", "low"]].max(axis=1))
        & frame["low"].le(frame[["open", "close", "high"]].min(axis=1))
    )
    valid_row = required_field_valid & envelope_valid
    invalid_ohlc_timestamps = [timestamp.isoformat() for timestamp in timestamps.loc[~valid_row]]
    invalid_ohlc_count = len(invalid_ohlc_timestamps)
    invalid_required_field_count = int((~required_field_valid).sum())
    diagnostic_cleaning_allowed = bool(
        invalid_required_field_count == 0 and invalid_ohlc_count <= MAX_DIAGNOSTIC_INVALID_OHLC_ROWS
    )
    analysis_frame = frame.loc[required_field_valid].copy()
    records = len(frame)
    usable_records = len(analysis_frame)
    median_dollar_volume = float(
        (analysis_frame["close"] * analysis_frame["volume"]).tail(60).median()
    )
    missing_return_ratio = float(analysis_frame["close"].pct_change().isna().mean())
    adjusted = manifest.get("request_params", {}).get("adjusted") is True
    identity_matches = bool(
        str(manifest.get("symbol") or "").upper() == symbol
        and manifest.get("provider") == "longbridge"
        and manifest.get("feed") == "nasdaq_basic"
        and manifest.get("timeframe") == "daily"
    )
    try:
        manifest_integrity_matches = bool(
            int(manifest.get("records") or 0) == records
            and pd.Timestamp(manifest.get("first_timestamp")) == timestamps.min()
            and pd.Timestamp(manifest.get("last_timestamp")) == timestamps.max()
        )
    except (TypeError, ValueError):
        manifest_integrity_matches = False
    row.update(
        {
            "records": records,
            "usable_records": usable_records,
            "first_timestamp": timestamps.min().isoformat() if records else None,
            "last_timestamp": timestamps.max().isoformat() if records else None,
            "median_dollar_volume_60": round(median_dollar_volume, 2),
            "missing_return_ratio": round(missing_return_ratio, 8),
            "duplicate_timestamp_count": duplicate_count,
            "valid_ohlc": invalid_ohlc_count == 0,
            "invalid_ohlc_count": invalid_ohlc_count,
            "invalid_required_field_count": invalid_required_field_count,
            "invalid_ohlc_timestamps": invalid_ohlc_timestamps,
            "q2_excluded_sessions": [],
            "quarantined_fields": ["high", "low"] if invalid_ohlc_count else [],
            "diagnostic_cleaning_allowed": diagnostic_cleaning_allowed,
            "adjusted_requested": adjusted,
            "manifest_identity_matches": identity_matches,
            "manifest_integrity_matches": manifest_integrity_matches,
            "content_sha256": sha256_file(cache_path),
            "source_manifest_sha256": sha256_file(manifest_path),
            "quality_pass": bool(
                usable_records >= min_records
                and median_dollar_volume >= 50_000_000
                and missing_return_ratio <= 0.02
                and duplicate_count == 0
                and diagnostic_cleaning_allowed
                and adjusted
                and identity_matches
                and manifest_integrity_matches
            ),
            "error": None,
        }
    )
    return row


def _daily_benchmark_input(
    root: Path,
    symbol: str,
    *,
    min_records: int,
) -> dict[str, Any]:
    cache_path = root / "data/cache" / f"{symbol.lower()}_daily_longbridge_nasdaq_basic.csv"
    manifest_path = (
        root / "data/cache/manifests" / f"{symbol.lower()}_daily_longbridge_nasdaq_basic.json"
    )
    row: dict[str, Any] = {
        "symbol": symbol,
        "cache_path": _relpath(cache_path, root),
        "manifest_path": _relpath(manifest_path, root),
        "runtime_input_eligible": False,
    }
    if not cache_path.exists() or not manifest_path.exists():
        row["error"] = "benchmark_cache_or_manifest_missing"
        return row
    try:
        manifest = _load_json_object(manifest_path)
        frame = normalize_ohlcv(pd.read_csv(cache_path))
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        row["error"] = str(exc)
        return row
    timestamps = pd.to_datetime(frame["timestamp"], utc=True)
    duplicate_count = int(timestamps.duplicated().sum())
    required_fields_valid = bool(
        frame[["open", "close"]].gt(0).all(axis=None) and frame["volume"].ge(0).all()
    )
    manifest_cache_raw = str(manifest.get("cache_path") or "")
    manifest_cache_path = Path(manifest_cache_raw)
    if not manifest_cache_path.is_absolute():
        manifest_cache_path = root / manifest_cache_path
    manifest_identity_matches = bool(
        str(manifest.get("symbol") or "").upper() == symbol
        and manifest.get("provider") == "longbridge"
        and manifest.get("feed") == "nasdaq_basic"
        and manifest.get("timeframe") == "daily"
    )
    try:
        manifest_runtime_cache_matches = bool(
            manifest_cache_path.resolve() == cache_path.resolve()
            and int(manifest.get("records") or 0) == len(frame)
            and pd.Timestamp(manifest.get("first_timestamp")) == timestamps.min()
            and pd.Timestamp(manifest.get("last_timestamp")) == timestamps.max()
        )
    except (OSError, TypeError, ValueError):
        manifest_runtime_cache_matches = False
    row.update(
        {
            "cache_sha256": sha256_file(cache_path),
            "manifest_sha256": sha256_file(manifest_path),
            "records": len(frame),
            "first_timestamp": timestamps.min().isoformat() if len(frame) else None,
            "last_timestamp": timestamps.max().isoformat() if len(frame) else None,
            "duplicate_timestamp_count": duplicate_count,
            "required_fields_valid": required_fields_valid,
            "manifest_identity_matches": manifest_identity_matches,
            "manifest_runtime_cache_matches": manifest_runtime_cache_matches,
            "provenance_quality": (
                "manifest_bound_runtime_cache"
                if manifest_identity_matches and manifest_runtime_cache_matches
                else "local_cache_content_hash_only_manifest_lineage_incomplete"
            ),
            "runtime_input_eligible": bool(
                len(frame) >= min_records and duplicate_count == 0 and required_fields_valid
            ),
            "error": None,
        }
    )
    return row


def _daily_runtime_alignment(
    root: Path,
    selected_rows: list[dict[str, Any]],
    benchmark_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    paths = [root / str(row["cache_path"]) for row in selected_rows]
    paths.extend(
        root / str(row["cache_path"])
        for row in benchmark_rows
        if row.get("runtime_input_eligible") is True
    )
    timestamp_sets = [
        set(pd.to_datetime(pd.read_csv(path, usecols=["timestamp"])["timestamp"], utc=True))
        for path in paths
    ]
    common = sorted(set.intersection(*timestamp_sets)) if timestamp_sets else []
    union = set.union(*timestamp_sets) if timestamp_sets else set()
    formal_forward_epoch = pd.Timestamp(FORMAL_FORWARD_EPOCH)
    serialized = [timestamp.isoformat() for timestamp in common]
    return {
        "policy": "exact_intersection_of_selected62_SPY_XLK_BIL_sessions",
        "selected_symbol_count": len(selected_rows),
        "benchmark_symbol_count": len(benchmark_rows),
        "input_series_count": len(paths),
        "union_timestamp_count": len(union),
        "common_timestamp_count": len(common),
        "common_timestamp_ratio": round(len(common) / len(union), 8) if union else 0.0,
        "sessions_not_in_exact_intersection": len(union) - len(common),
        "first_common_timestamp": common[0].isoformat() if common else None,
        "last_common_timestamp": common[-1].isoformat() if common else None,
        "common_timestamps_sha256": hashlib.sha256("\n".join(serialized).encode()).hexdigest(),
        "formal_forward_epoch": FORMAL_FORWARD_EPOCH,
        "formal_forward_observation_count": sum(
            timestamp >= formal_forward_epoch for timestamp in common
        ),
        "historical_only": True,
    }


def _daily_cache_inventory(root: Path) -> dict[str, Any]:
    cache_symbols = {
        path.name.removesuffix("_daily_longbridge_nasdaq_basic.csv").upper()
        for path in (root / "data/cache").glob("*_daily_longbridge_nasdaq_basic.csv")
    }
    manifest_symbols = {
        path.name.removesuffix("_daily_longbridge_nasdaq_basic.json").upper()
        for path in (root / "data/cache/manifests").glob("*_daily_longbridge_nasdaq_basic.json")
    }
    return {
        "cache_file_count": len(cache_symbols),
        "manifest_file_count": len(manifest_symbols),
        "cache_without_manifest": sorted(cache_symbols - manifest_symbols),
        "manifest_without_cache": sorted(manifest_symbols - cache_symbols),
        "drift_free": cache_symbols == manifest_symbols,
    }


def _intraday_row_pass(
    row: dict[str, Any],
    *,
    min_history_months: float,
    min_sessions: int,
    max_gap_rate: float,
) -> bool:
    if row.get("status") != "ok":
        return False
    gap_rate = float(row.get("session_grid_gap_rate", row.get("rth_gap_rate", 1.0)) or 0.0)
    duplicate_count = int(
        row.get("rth_duplicate_bars", row.get("duplicate_timestamp_count", 0)) or 0
    )
    off_session_count = int(
        row.get("off_session_bars", row.get("off_session_timestamp_count", 0)) or 0
    )
    off_grid_count = int(row.get("off_grid_bars") or 0)
    return bool(
        float(row.get("history_months") or 0.0) >= min_history_months
        and int(row.get("rth_quality_sessions", row.get("rth_days", 0)) or 0) >= min_sessions
        and gap_rate <= max_gap_rate
        and duplicate_count == 0
        and off_session_count == 0
        and off_grid_count == 0
        and row.get("materialized_content_matches") is True
        and row.get("source_manifest_matches") is True
    )


def _with_intraday_action_boundaries(root: Path, row: dict[str, Any]) -> dict[str, Any]:
    enriched = dict(row)
    symbol = str(row.get("symbol") or "").upper()
    source_path = root / "data/cache" / f"{symbol.lower()}_1m_iex.csv"
    manifest_path = root / "data/cache/manifests" / f"{symbol.lower()}_1m_alpaca_iex.json"
    materialized_path = root / str(row.get("path") or "")
    materialized_content_matches = bool(
        materialized_path.is_file()
        and row.get("sha256")
        and sha256_file(materialized_path) == row.get("sha256")
    )
    if row.get("status") != "ok" or not source_path.exists():
        enriched.update(
            {
                "source_1m_path": _relpath(source_path, root),
                "source_1m_sha256": None,
                "source_manifest_path": _relpath(manifest_path, root),
                "source_manifest_sha256": None,
                "source_manifest_matches": False,
                "materialized_content_matches": materialized_content_matches,
                "detected_action_discontinuity_count": 0,
                "detected_action_discontinuities": [],
                "q2_excluded_sessions": [],
            }
        )
        return enriched
    try:
        frame = normalize_ohlcv(pd.read_csv(source_path))
    except (OSError, ValueError):
        enriched["action_discontinuity_check"] = "source_read_error"
        return enriched
    local = pd.to_datetime(frame["timestamp"], utc=True).dt.tz_convert("America/New_York")
    data = frame.copy()
    data["session_date"] = local.dt.date.astype(str)
    sessions = data.groupby("session_date", sort=True).agg(
        open=("open", "first"),
        close=("close", "last"),
    )
    previous_close = sessions["close"].shift(1)
    overnight_return = sessions["open"] / previous_close - 1.0
    discontinuities = []
    excluded_sessions: set[str] = set()
    session_dates = list(sessions.index)
    for index, value in enumerate(overnight_return):
        if pd.isna(value) or abs(float(value)) < 0.35:
            continue
        session_date = str(session_dates[index])
        previous_session = str(session_dates[index - 1]) if index else None
        discontinuities.append(
            {
                "session_date": session_date,
                "previous_session_date": previous_session,
                "overnight_return": round(float(value), 8),
                "classification": "possible_split_or_unadjusted_corporate_action",
            }
        )
        excluded_sessions.add(session_date)
    manifest_matches = False
    manifest_sha256 = None
    if manifest_path.exists():
        try:
            manifest = _load_json_object(manifest_path)
            manifest_sha256 = sha256_file(manifest_path)
            manifest_first = pd.Timestamp(manifest.get("first_timestamp"))
            manifest_last = pd.Timestamp(manifest.get("last_timestamp"))
            manifest_matches = bool(
                str(manifest.get("symbol") or "").upper() == symbol
                and manifest.get("provider") == "alpaca"
                and manifest.get("feed") == "iex"
                and manifest.get("timeframe") == "1m"
                and int(manifest.get("records") or 0) == len(frame)
                and manifest_first == pd.Timestamp(frame["timestamp"].min())
                and manifest_last == pd.Timestamp(frame["timestamp"].max())
            )
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            manifest_matches = False
    enriched.update(
        {
            "source_1m_path": _relpath(source_path, root),
            "source_1m_sha256": sha256_file(source_path),
            "source_manifest_path": _relpath(manifest_path, root),
            "source_manifest_sha256": manifest_sha256,
            "source_manifest_matches": manifest_matches,
            "materialized_content_matches": materialized_content_matches,
            "detected_action_discontinuity_count": len(discontinuities),
            "detected_action_discontinuities": discontinuities,
            "q2_excluded_sessions": sorted(excluded_sessions),
            "action_discontinuity_check": "heuristic_only",
        }
    )
    return enriched


def _intraday_panel_alignment(
    root: Path,
    rows: list[dict[str, Any]],
    *,
    excluded_sessions: set[str],
) -> dict[str, Any]:
    timestamp_sets: list[set[pd.Timestamp]] = []
    session_sets: list[set[str]] = []
    errors: list[str] = []
    for row in rows:
        symbol = str(row.get("symbol") or "")
        path = root / str(row.get("path") or "")
        if row.get("status") != "ok" or not path.is_file():
            errors.append(symbol or "unknown")
            continue
        try:
            frame = normalize_ohlcv(pd.read_csv(path))
        except (OSError, ValueError, KeyError):
            errors.append(symbol or "unknown")
            continue
        timestamps = pd.to_datetime(frame["timestamp"], utc=True)
        local_sessions = timestamps.dt.tz_convert("America/New_York").dt.date.astype(str)
        retained = ~local_sessions.isin(excluded_sessions)
        retained_timestamps = set(timestamps.loc[retained].tolist())
        timestamp_sets.append(retained_timestamps)
        session_sets.append(set(local_sessions.loc[retained].tolist()))
    if len(timestamp_sets) != len(rows) or not timestamp_sets:
        return {
            "verified": False,
            "error_symbols": errors,
            "common_timestamp_count": 0,
            "union_timestamp_count": 0,
            "common_session_count": 0,
            "excluded_sessions": sorted(excluded_sessions),
        }
    common_timestamps = set.intersection(*timestamp_sets)
    union_timestamps = set.union(*timestamp_sets)
    common_sessions = set.intersection(*session_sets)
    return {
        "verified": True,
        "error_symbols": [],
        "common_timestamp_count": len(common_timestamps),
        "union_timestamp_count": len(union_timestamps),
        "common_timestamp_ratio": round(len(common_timestamps) / len(union_timestamps), 8)
        if union_timestamps
        else 0.0,
        "common_session_count": len(common_sessions),
        "first_common_timestamp": min(common_timestamps).isoformat() if common_timestamps else None,
        "last_common_timestamp": max(common_timestamps).isoformat() if common_timestamps else None,
        "excluded_sessions": sorted(excluded_sessions),
    }


def _event_capability_gate(root: Path) -> dict[str, Any]:
    documents = list((root / "data/raw/events").glob("**/*.jsonl"))
    return {
        "historical_pit_training_ready": False,
        "credential_state": "not_assessed_by_cache_only_command",
        "forward_collection_ready": False,
        "local_event_file_count": len(documents),
        "required_packet_fields": [
            "published_at",
            "fetched_at",
            "visible_at",
            "first_seen_at",
            "revision_id",
            "version_id",
            "rights_scope",
            "availability_quality",
            "acquisition_mode",
            "source",
            "input_hash",
            "prompt_hash",
        ],
        "blockers": [
            "immutable_historical_pit_corpus_missing",
            "news_content_rights_unverified",
            "historical_first_seen_timestamps_unavailable",
            "fred_latest_vintage_is_not_alfred_replay",
            "event_feature_ablation_evidence_missing",
        ],
    }


def _load_reusable_minute_payload(
    root: Path,
    *,
    report_date: str,
    symbols: list[str],
    feed: str,
    max_rth_gap_rate: float,
) -> dict[str, Any] | None:
    report_path = (
        root / "reports/research/control" / f"minute-momentum-feasibility-{report_date}.json"
    )
    prior_panel_path = root / OUTPUT_DIR / "intraday-panel-manifest.json"
    transform_path = Path(__file__).with_name("minute_momentum_feasibility.py")
    if not report_path.is_file() or not prior_panel_path.is_file():
        return None
    if report_path.stat().st_mtime_ns < transform_path.stat().st_mtime_ns:
        return None
    try:
        payload = _load_json_object(report_path)
        prior_panel = _load_json_object(prior_panel_path)
    except (OSError, ValueError, json.JSONDecodeError):
        return None
    if (
        payload.get("report_type") != "minute_momentum_feasibility"
        or payload.get("feed") != feed
        or payload.get("fetch_missing") is not False
        or payload.get("symbols") != symbols
        or float(payload.get("required_symbol_coverage_threshold") or 0.0) != 1.0
        or float(payload.get("max_rth_gap_rate") or -1.0) != max_rth_gap_rate
    ):
        return None
    rows = payload.get("rows")
    prior_rows = prior_panel.get("rows")
    if not isinstance(rows, list) or not isinstance(prior_rows, list):
        return None
    if len(rows) != len(symbols) or len(prior_rows) != len(symbols):
        return None
    prior_by_symbol = {
        str(row.get("symbol") or ""): row for row in prior_rows if isinstance(row, dict)
    }
    for row in rows:
        if not isinstance(row, dict):
            return None
        symbol = str(row.get("symbol") or "")
        prior = prior_by_symbol.get(symbol)
        if symbol not in symbols or row.get("timeframe") != "15m" or prior is None:
            return None
        output_path = root / str(row.get("path") or "")
        source_path = root / str(prior.get("source_1m_path") or "")
        if not output_path.is_file() or not source_path.is_file():
            return None
        if sha256_file(output_path) != row.get("sha256"):
            return None
        if sha256_file(source_path) != prior.get("source_1m_sha256"):
            return None
    return payload


def _diagnostic_path_gate(
    go: bool,
    evidence_path: Path,
    root: Path,
    *,
    candidate_ids: list[str],
    blocked_reason: str | None = None,
) -> dict[str, Any]:
    return {
        "q2_action": "run_diagnostic" if go else "dependency_skipped",
        "historical_diagnostic_go": go,
        "historical_research_qualified": False,
        "reason": (
            "Frozen local panel is sufficient for survivorship-labelled diagnostic rejection "
            "tests, but not positive research evidence."
            if go
            else blocked_reason
            or "The complete frozen local panel did not pass coverage and integrity gates."
        ),
        "evidence_path": _relpath(evidence_path, root),
        "candidate_ids": candidate_ids,
    }


def _sector_capped(
    rows: list[dict[str, Any]],
    limit: int,
    *,
    per_sector: int,
) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()
    for row in rows:
        sector = str(row.get("sector") or "Unknown")
        if counts[sector] >= per_sector:
            continue
        selected.append(row)
        counts[sector] += 1
        if len(selected) >= limit:
            break
    return selected


def _number(value: Any) -> float:
    cleaned = re.sub(r"[^0-9.\-]", "", str(value or ""))
    try:
        return float(cleaned)
    except ValueError:
        return 0.0


def _load_json_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object: {path}")
    return payload


def _resolve_input(root: Path, path: Path) -> Path:
    return path if path.is_absolute() else root / path


def _relpath(path: Path, root: Path) -> str:
    try:
        return str(path.resolve().relative_to(root.resolve()))
    except ValueError:
        return str(path.resolve())


def _render_markdown(payload: dict[str, Any]) -> str:
    daily_panel = payload["daily_panel"]
    intraday_panel = payload["intraday_panel"]
    lines = [
        "# Stock And Intraday Momentum Data Feasibility",
        "",
        f"- Status: `{payload['status']}`",
        f"- Q.2 diagnostic execution authorized: `{payload['q2_diagnostic_execution_authorized']}`",
        f"- Historical research pass: `{payload['research_pass']}`",
        f"- Paper ready pass: `{payload['paper_ready_pass']}`",
        f"- Parent universe: `{payload['parent_universe']['count']}` current-snapshot stocks",
        (
            f"- Daily panel: `{daily_panel['selected_count']}` selected, "
            f"diagnostic go `{daily_panel['diagnostic_go']}`"
        ),
        (
            f"- Daily runtime intersection: `{daily_panel['runtime_common_timestamp_count']}` "
            f"sessions through `{daily_panel['runtime_last_timestamp']}`"
        ),
        (
            f"- Intraday panel: `{intraday_panel['selected_count']}` required, "
            f"panel quality go `{intraday_panel['panel_quality_go']}`; "
            f"Q.2 diagnostic go `{intraday_panel['q2_diagnostic_go']}`"
        ),
        "",
        "## Path Gates",
        "",
        "| path | Q.2 action | diagnostic go | research qualified |",
        "|---|---|---:|---:|",
    ]
    for path, gate in payload["path_gates"].items():
        diagnostic_go = gate["historical_diagnostic_go"]
        research_qualified = gate["historical_research_qualified"]
        lines.append(
            f"| `{path}` | `{gate['q2_action']}` | `{diagnostic_go}` | `{research_qualified}` |"
        )
    lines.extend(["", "## Global Blockers", ""])
    lines.extend(f"- `{blocker}`" for blocker in payload["global_blockers"])
    lines.extend(["", "## Interpretation", "", payload["interpretation"], ""])
    return "\n".join(lines)
