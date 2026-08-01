from __future__ import annotations

import hashlib
import importlib.metadata
import json
import math
import subprocess
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from statistics import NormalDist
from typing import Any

import numpy as np
import pandas as pd

from open_composer.adapters.data.sample import normalize_ohlcv
from open_composer.analytics import build_performance_metrics
from open_composer.config import ensure_dir, project_root
from open_composer.market_calendar import (
    expected_us_equity_rth_bar_starts,
    us_equity_session_close,
)
from open_composer.models.strategy_spec import load_strategy_spec
from open_composer.research.iteration_dossier import validate_iteration_dossier
from open_composer.storage import write_json
from open_composer.strategy_versions import strategy_content_hash

ITER_ID = "mom_multiscale_low_turnover_r6"
STRATEGY_NAME = "us_multiscale_low_turnover_r6"
FORMAL_FORWARD_START = "2026-07-20"
DATA_DIR = Path("data/research/alpaca_multiscale_r6")
ITERATION_DIR = Path("reports/research/iterations") / ITER_ID
PANEL_MANIFEST_PATH = ITERATION_DIR / "panel-manifest.json"
CANDIDATE_MANIFEST_PATH = ITERATION_DIR / "candidate-manifest.json"
DATA_FEASIBILITY_PATH = ITERATION_DIR / "data-feasibility.json"
SEARCH_SPACE_PATH = ITERATION_DIR / "search-space.json"
SPEC_PATH = Path("strategy_specs/drafts/us_multiscale_low_turnover_r6.yaml")
RUNNER_PATH = Path("open_composer/research/multiscale_low_turnover_r6.py")
UNIVERSE_MANIFEST_PATH = ITERATION_DIR / "universe-manifest.json"
Q2_EXECUTION_MAP_PATH = ITERATION_DIR / "q2-execution-map.json"

SPY = "SPY"
SECTOR_SYMBOLS = (
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
CORE_SYMBOLS = (SPY, *SECTOR_SYMBOLS)
BENCHMARK_SYMBOLS = ("QQQ", "BIL")
ALL_DAILY_SYMBOLS = (*CORE_SYMBOLS, *BENCHMARK_SYMBOLS)
PRIMITIVE_FIELDS = ("open", "high", "low", "close", "volume")
DAILY_START = datetime(2018, 1, 1, tzinfo=UTC)
INTRADAY_START = datetime(2024, 1, 1, tzinfo=UTC)
INTRADAY_MINUTES = 30
COST_SCENARIOS = (5.0, 10.0, 20.0)
OUTER_FOLDS = 4
EXPECTED_CANDIDATE_IDS = (
    "D01",
    "D02",
    "D03",
    "D04",
    "D05",
    "D06",
    "E01",
    "E02",
    "N01",
    "N02",
)


class R6ContractViolation(ValueError):
    pass


class R6FutureFeatureError(R6ContractViolation):
    pass


@dataclass(frozen=True)
class R6Panel:
    daily: dict[str, pd.DataFrame]
    intraday: dict[str, pd.DataFrame]
    daily_sessions: tuple[date, ...]
    intraday_sessions: tuple[date, ...]


@dataclass(frozen=True)
class R6DailyFeatures:
    raw_score: pd.DataFrame
    residual_score: pd.DataFrame
    raw_eligible: pd.DataFrame
    residual_eligible: pd.DataFrame
    realized_vol_21: pd.DataFrame
    regime_on: pd.Series
    sector_breadth_126: pd.Series
    evaluation_start: date


@dataclass(frozen=True)
class R6Simulation:
    gross_returns: pd.Series
    turnover: pd.Series
    weights: pd.DataFrame


@dataclass(frozen=True)
class R6DiagnosticResult:
    evaluation_path: Path
    markdown_path: Path
    trial_ledger_path: Path
    payload: dict[str, Any]


def refresh_r6_market_data(
    root: Path | None = None,
    *,
    requested_end: datetime | None = None,
) -> dict[str, Any]:
    """Fetch an adjustment-explicit R6 snapshot without touching prior frozen rounds."""
    base = root or project_root()
    end = requested_end or datetime.now(UTC)
    output = ensure_dir(base / DATA_DIR)

    try:
        from alpaca.data.enums import Adjustment
        from alpaca.data.historical import StockHistoricalDataClient
        from alpaca.data.requests import StockBarsRequest
        from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
        from dotenv import load_dotenv
    except ImportError as exc:  # pragma: no cover - dependency is exercised by live CLI only
        raise R6ContractViolation("alpaca-py and python-dotenv are required") from exc

    load_dotenv(base / ".env")
    from open_composer.config import alpaca_api_key_id, alpaca_api_secret_key

    client = StockHistoricalDataClient(
        api_key=alpaca_api_key_id(),
        secret_key=alpaca_api_secret_key(),
    )
    rows: list[dict[str, Any]] = []
    for symbol in ALL_DAILY_SYMBOLS:
        request = StockBarsRequest(
            symbol_or_symbols=[symbol],
            timeframe=TimeFrame.Day,
            start=DAILY_START,
            end=end,
            feed="iex",
            adjustment=Adjustment.ALL,
        )
        frame = _alpaca_response_frame(client.get_stock_bars(request), symbol)
        path = output / f"{symbol.lower()}_1d_alpaca_iex_all.csv"
        _write_snapshot(path, frame)
        rows.append(
            _receipt_row(
                base,
                path,
                symbol=symbol,
                timeframe="1d",
                requested_start=DAILY_START,
                requested_end=end,
            )
        )

    intraday_timeframe = TimeFrame(INTRADAY_MINUTES, TimeFrameUnit.Minute)
    for symbol in CORE_SYMBOLS:
        request = StockBarsRequest(
            symbol_or_symbols=[symbol],
            timeframe=intraday_timeframe,
            start=INTRADAY_START,
            end=end,
            feed="iex",
            adjustment=Adjustment.ALL,
        )
        frame = _alpaca_response_frame(client.get_stock_bars(request), symbol)
        frame = _regular_session_only(frame)
        path = output / f"{symbol.lower()}_30m_alpaca_iex_all.csv"
        _write_snapshot(path, frame)
        rows.append(
            _receipt_row(
                base,
                path,
                symbol=symbol,
                timeframe="30m",
                requested_start=INTRADAY_START,
                requested_end=end,
            )
        )

    receipt = {
        "schema_version": 1,
        "report_type": "multiscale_low_turnover_r6_refresh_receipt",
        "iter_id": ITER_ID,
        "generated_at": datetime.now(UTC).isoformat(),
        "provider": "alpaca",
        "feed": "iex",
        "adjustment": "all",
        "sdk": {
            "package": "alpaca-py",
            "version": importlib.metadata.version("alpaca-py"),
        },
        "request_contract": {
            "daily_start_inclusive": DAILY_START.isoformat(),
            "intraday_start_inclusive": INTRADAY_START.isoformat(),
            "end_exclusive": end.isoformat(),
            "endpoint": "alpaca_stock_historical_bars",
            "pagination": "alpaca_py_client_managed",
            "request_ids_available": False,
        },
        "source_mode": "live_fetch",
        "fallback_used": False,
        "requested_end": end.isoformat(),
        "rows": rows,
    }
    write_json(output / "refresh-receipt.json", receipt)
    return receipt


def prepare_r6_panel(root: Path | None = None) -> dict[str, Any]:
    base = root or project_root()
    panel = load_r6_panel(base)
    receipt_path = base / DATA_DIR / "refresh-receipt.json"
    receipt = _load_json(receipt_path)
    if receipt.get("fallback_used") is not False:
        raise R6ContractViolation("R6 refresh receipt must prove fallback_used=false")
    if receipt.get("adjustment") != "all":
        raise R6ContractViolation("R6 refresh receipt must bind adjustment=all")

    daily_expected = _calendar_sessions(panel.daily_sessions[0], panel.daily_sessions[-1])
    intraday_expected = _calendar_sessions(panel.intraday_sessions[0], panel.intraday_sessions[-1])
    daily_set = set(panel.daily_sessions)
    intraday_set = set(panel.intraday_sessions)
    daily_included = [day.isoformat() for day in panel.daily_sessions]
    intraday_included = [day.isoformat() for day in panel.intraday_sessions]
    daily_excluded = [day.isoformat() for day in sorted(set(daily_expected) - daily_set)]
    intraday_excluded = [day.isoformat() for day in sorted(set(intraday_expected) - intraday_set)]
    daily_quality = []
    for symbol in ALL_DAILY_SYMBOLS:
        available = set(panel.daily[symbol].index).intersection(daily_expected)
        daily_quality.append(
            {
                "symbol": symbol,
                "complete_session_count": len(available),
                "missing_sessions": [
                    day.isoformat() for day in sorted(set(daily_expected) - available)
                ],
            }
        )
    intraday_quality = []
    for symbol in CORE_SYMBOLS:
        complete = _complete_intraday_sessions(panel.intraday[symbol], INTRADAY_MINUTES)
        intraday_quality.append(
            {
                "symbol": symbol,
                "complete_session_count": len(complete.intersection(intraday_expected)),
                "missing_or_incomplete_sessions": [
                    day.isoformat() for day in sorted(set(intraday_expected) - complete)
                ],
            }
        )
    file_rows = []
    receipt_by_path = {str(row["path"]): row for row in receipt.get("rows", [])}
    for path in sorted((base / DATA_DIR).glob("*.csv")):
        relative = str(path.relative_to(base))
        row = receipt_by_path.get(relative)
        if not row:
            raise R6ContractViolation(f"file is not bound by refresh receipt: {relative}")
        actual_sha = _sha256_file(path)
        if row.get("sha256") != actual_sha:
            raise R6ContractViolation(f"refresh receipt hash mismatch: {relative}")
        file_rows.append(
            {
                "symbol": row["symbol"],
                "timeframe": row["timeframe"],
                "path": relative,
                "sha256": actual_sha,
                "record_count": row["record_count"],
                "first_timestamp": row["first_timestamp"],
                "last_timestamp": row["last_timestamp"],
                "provider": "alpaca",
                "feed": "iex",
                "adjustment": "all",
                "source_mode": "live_fetch",
                "fallback_used": False,
                "snapshot_written_at": datetime.fromtimestamp(
                    path.stat().st_mtime, tz=UTC
                ).isoformat(),
            }
        )

    generator_path = base / Path(__file__).relative_to(base)
    calendar_path = base / "open_composer/market_calendar.py"
    registry_path = base / "capabilities/registry.yaml"
    generator = _git_provenance(base)
    generator.update(
        {
            "module_path": str(generator_path.relative_to(base)),
            "module_sha256": _sha256_file(generator_path),
            "command": "refresh_r6_market_data then prepare_r6_panel",
        }
    )
    manifest = {
        "schema_version": 1,
        "report_type": "multiscale_low_turnover_r6_panel_manifest",
        "panel_id": "alpaca_iex_adjusted_all_r6_20260717",
        "iter_id": ITER_ID,
        "generated_at": datetime.now(UTC).isoformat(),
        "scope": "fixed_sector_etf_IEX_adjusted_diagnostic",
        "provider": "alpaca",
        "feed": "iex",
        "adjustment": "all",
        "source_mode": "live_fetch",
        "fallback_used": False,
        "primitive_fields": list(PRIMITIVE_FIELDS),
        "forward_fill_allowed": False,
        "zero_return_substitution_allowed": False,
        "generator": generator,
        "capability": {
            "id": "market.alpaca_bars",
            "registry_path": str(registry_path.relative_to(base)),
            "registry_sha256": _sha256_file(registry_path),
        },
        "calendar": {
            "id": "local_us_equity_calendar_v1",
            "timezone": "America/New_York",
            "timestamp_label": "bar_start",
            "path": str(calendar_path.relative_to(base)),
            "sha256": _sha256_file(calendar_path),
            "special_closures": [
                {
                    "date": "2025-01-09",
                    "reason": "national_day_of_mourning_for_former_president_jimmy_carter",
                }
            ],
        },
        "daily": {
            "symbols": list(ALL_DAILY_SYMBOLS),
            "strict_common_session_count": len(panel.daily_sessions),
            "strict_common_first_session": panel.daily_sessions[0].isoformat(),
            "strict_common_last_session": panel.daily_sessions[-1].isoformat(),
            "calendar_session_count": len(daily_expected),
            "included_sessions": daily_included,
            "included_sessions_sha256": _canonical_sha(daily_included),
            "global_excluded_sessions": daily_excluded,
            "global_excluded_sessions_sha256": _canonical_sha(daily_excluded),
            "session_policy": "exact_intersection_all_14_daily_series",
            "per_symbol_quality": daily_quality,
        },
        "intraday": {
            "symbols": list(CORE_SYMBOLS),
            "timeframe_minutes": INTRADAY_MINUTES,
            "strict_common_complete_session_count": len(panel.intraday_sessions),
            "strict_common_first_session": panel.intraday_sessions[0].isoformat(),
            "strict_common_last_session": panel.intraday_sessions[-1].isoformat(),
            "calendar_session_count": len(intraday_expected),
            "included_sessions": intraday_included,
            "included_sessions_sha256": _canonical_sha(intraday_included),
            "global_excluded_sessions": intraday_excluded,
            "global_excluded_sessions_sha256": _canonical_sha(intraday_excluded),
            "session_policy": "all_12_core_symbols_exact_expected_RTH_grid",
            "timestamp_label": "bar_start",
            "per_symbol_quality": intraday_quality,
            "daily_aggregation_contract": {
                "complete_sessions_only": True,
                "fill": "none",
                "open": "first_bar_open",
                "high": "maximum_bar_high",
                "low": "minimum_bar_low",
                "close": "last_bar_close",
                "volume": "sum_bar_volume",
                "label": "America/New_York_session_date",
            },
        },
        "formal_forward_start": FORMAL_FORWARD_START,
        "formal_forward_daily_observation_count": sum(
            day >= date.fromisoformat(FORMAL_FORWARD_START) for day in panel.daily_sessions
        ),
        "formal_forward_intraday_observation_count": sum(
            day >= date.fromisoformat(FORMAL_FORWARD_START) for day in panel.intraday_sessions
        ),
        "input_files": file_rows,
        "refresh_receipt": {
            "path": str(receipt_path.relative_to(base)),
            "sha256": _sha256_file(receipt_path),
            "sdk": receipt.get("sdk"),
            "request_contract": receipt.get("request_contract"),
        },
        "paper_data_qualified": False,
        "paper_data_blockers": [
            "alpaca_basic_IEX_is_not_consolidated_SIP",
            "official_open_close_and_matched_execution_parity_missing",
            "formal_forward_observations_missing",
        ],
    }
    output = ensure_dir(base / ITERATION_DIR)
    write_json(output / PANEL_MANIFEST_PATH.name, manifest)
    return manifest


def build_r6_data_feasibility(root: Path | None = None) -> dict[str, Any]:
    base = root or project_root()
    panel_path = base / PANEL_MANIFEST_PATH
    candidate_path = base / CANDIDATE_MANIFEST_PATH
    panel = _load_json(panel_path)
    manifest = _load_json(candidate_path)
    candidates = manifest.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        raise R6ContractViolation("R6 candidate manifest has no candidates")

    candidates_by_path: dict[str, list[dict[str, Any]]] = {}
    for candidate in candidates:
        if not isinstance(candidate, dict):
            raise R6ContractViolation("R6 candidate row must be an object")
        candidates_by_path.setdefault(str(candidate["path"]), []).append(candidate)

    path_actions = {
        "daily_core": (
            "run_diagnostic",
            True,
            "strict_live_adjusted_daily_panel_complete",
        ),
        "intraday_overlay": (
            "run_diagnostic",
            True,
            "strict_complete_intraday_panel_shadow_only",
        ),
        "event_llm": (
            "dependency_skipped",
            False,
            "real_historical_PIT_event_packets_missing",
        ),
        "negative_controls": (
            "run_diagnostic",
            True,
            "mandatory_negative_control_path",
        ),
    }
    if set(candidates_by_path) != set(path_actions):
        raise R6ContractViolation("R6 candidate paths do not match authorization contract")

    universe_payload = {
        "schema_version": 1,
        "iter_id": ITER_ID,
        "scope": "fixed_current_sector_etf_universe_diagnostic",
        "survivorship_labelled": True,
        "selection_rule": "fixed_SPY_11_SPDR_sector_ETFs_QQQ_and_BIL_preregistered",
        "core_symbols": list(CORE_SYMBOLS),
        "benchmark_symbols": list(BENCHMARK_SYMBOLS),
        "all_symbols": list(ALL_DAILY_SYMBOLS),
        "point_in_time_membership_claimed": False,
        "delisted_instruments_included": False,
        "promotion_authority": False,
    }
    write_json(base / UNIVERSE_MANIFEST_PATH, universe_payload)

    path_gates: dict[str, dict[str, Any]] = {}
    authorization_rows = []
    runnable = 0
    skipped = 0
    for path_name, rows in candidates_by_path.items():
        action, diagnostic_go, reason = path_actions[path_name]
        candidate_ids = [str(row["candidate_id"]) for row in rows]
        path_gates[path_name] = {
            "q2_action": action,
            "historical_diagnostic_go": diagnostic_go,
            "historical_research_qualified": False,
            "candidate_ids": candidate_ids,
            "reason_code": reason,
        }
        if action == "run_diagnostic":
            runnable += len(rows)
        else:
            skipped += len(rows)
        for row in rows:
            authorization_rows.append(
                {
                    "candidate_id": row["candidate_id"],
                    "path": path_name,
                    "action": action,
                    "reason_code": reason,
                    "candidate_binding_sha256": _canonical_sha(row),
                    "evidence_path": str(PANEL_MANIFEST_PATH),
                    "evidence_sha256": _sha256_file(panel_path),
                }
            )

    runnable_ids = {
        str(row["candidate_id"])
        for path_name, rows in candidates_by_path.items()
        if path_actions[path_name][0] == "run_diagnostic"
        for row in rows
    }
    execution_rows = []
    for candidate in candidates:
        candidate_id = str(candidate["candidate_id"])
        if candidate_id not in runnable_ids:
            continue
        execution_rows.append(
            {
                "candidate_id": candidate_id,
                "path": candidate["path"],
                "method": candidate["method"],
                "candidate_binding_sha256": _canonical_sha(candidate),
                "primitive_fields": ["open", "close", "volume"],
                "required_benchmarks": [
                    "SPY_buy_and_hold",
                    "QQQ_buy_and_hold",
                    "equal_weight_sector_universe",
                    "BIL_cash_proxy",
                    "uninvested_cash",
                    "ex_post_best_symbol_report_only",
                ],
                "research_pass": False,
                "paper_ready_pass": False,
                "promotion_eligible": False,
            }
        )
    execution_map = {
        "schema_version": 1,
        "iter_id": ITER_ID,
        "scope": "historical_current_universe_diagnostic",
        "survivorship_labelled": True,
        "primitive_field_allowlist": ["open", "close", "volume"],
        "high_low_dependent_candidates_allowed": False,
        "forward_fill_allowed": False,
        "zero_return_substitution_allowed": False,
        "runnable_candidate_count": len(execution_rows),
        "rows": sorted(execution_rows, key=lambda row: str(row["candidate_id"])),
    }
    write_json(base / Q2_EXECUTION_MAP_PATH, execution_map)
    cost_path = base / ITERATION_DIR / "cost-contract.json"

    payload = {
        "schema_version": 1,
        "report_type": "multiscale_low_turnover_r6_data_feasibility",
        "iter_id": ITER_ID,
        "generated_at": datetime.now(UTC).isoformat(),
        "workflow_pass": True,
        "research_pass": False,
        "llm_contribution_pass": False,
        "paper_ready_pass": False,
        "q2_diagnostic_execution_authorized": True,
        "scope": panel["scope"],
        "formal_forward_start": FORMAL_FORWARD_START,
        "formal_forward_daily_observation_count": panel["formal_forward_daily_observation_count"],
        "formal_forward_intraday_observation_count": panel[
            "formal_forward_intraday_observation_count"
        ],
        "panel_manifest": {
            "path": str(PANEL_MANIFEST_PATH),
            "sha256": _sha256_file(panel_path),
        },
        "candidate_manifest": {
            "path": str(CANDIDATE_MANIFEST_PATH),
            "sha256": _sha256_file(candidate_path),
        },
        "parent_universe": {
            "path": str(UNIVERSE_MANIFEST_PATH),
            "sha256": _sha256_file(base / UNIVERSE_MANIFEST_PATH),
        },
        "daily_panel": {
            "path": str(PANEL_MANIFEST_PATH),
            "sha256": _sha256_file(panel_path),
        },
        "intraday_panel": {
            "path": str(PANEL_MANIFEST_PATH),
            "sha256": _sha256_file(panel_path),
        },
        "cost_contract": {
            "path": str(cost_path.relative_to(base)),
            "sha256": _sha256_file(cost_path),
        },
        "q2_execution_map": {
            "path": str(Q2_EXECUTION_MAP_PATH),
            "sha256": _sha256_file(base / Q2_EXECUTION_MAP_PATH),
        },
        "path_gates": path_gates,
        "candidate_accounting": {
            "frozen_candidate_count": len(candidates),
            "diagnostic_runnable_count": runnable,
            "dependency_skipped_count": skipped,
            "unresolved_count": 0,
            "balanced": runnable + skipped == len(candidates),
        },
        "q2_authorization": {
            "candidate_count": len(candidates),
            "rows": sorted(authorization_rows, key=lambda row: str(row["candidate_id"])),
        },
        "data_quality": {
            "daily_strict_common_session_count": panel["daily"]["strict_common_session_count"],
            "daily_last_session": panel["daily"]["strict_common_last_session"],
            "intraday_strict_common_session_count": panel["intraday"][
                "strict_common_complete_session_count"
            ],
            "intraday_last_session": panel["intraday"]["strict_common_last_session"],
            "adjustment": panel["adjustment"],
            "fallback_used": panel["fallback_used"],
            "forward_fill_allowed": panel["forward_fill_allowed"],
            "zero_return_substitution_allowed": panel["zero_return_substitution_allowed"],
        },
        "paper_data_qualified": False,
        "paper_data_blockers": list(panel["paper_data_blockers"]),
    }
    write_json(base / DATA_FEASIBILITY_PATH, payload)
    return payload


def load_r6_panel(root: Path | None = None) -> R6Panel:
    base = root or project_root()
    daily: dict[str, pd.DataFrame] = {}
    intraday: dict[str, pd.DataFrame] = {}
    daily_date_sets: list[set[date]] = []
    intraday_complete_sets: list[set[date]] = []

    for symbol in ALL_DAILY_SYMBOLS:
        path = base / DATA_DIR / f"{symbol.lower()}_1d_alpaca_iex_all.csv"
        frame = _load_market_frame(path)
        frame = frame.assign(session=_daily_sessions(frame))
        if frame["session"].duplicated().any():
            raise R6ContractViolation(f"duplicate daily session for {symbol}")
        frame = frame.loc[frame["session"].map(us_equity_session_close).notna()].copy()
        daily[symbol] = frame.set_index("session").sort_index()
        daily_date_sets.append(set(daily[symbol].index))

    for symbol in CORE_SYMBOLS:
        path = base / DATA_DIR / f"{symbol.lower()}_30m_alpaca_iex_all.csv"
        frame = _load_market_frame(path)
        intraday[symbol] = frame
        intraday_complete_sets.append(_complete_intraday_sessions(frame, INTRADAY_MINUTES))

    daily_sessions = tuple(sorted(set.intersection(*daily_date_sets)))
    intraday_sessions = tuple(sorted(set.intersection(*intraday_complete_sets)))
    if not daily_sessions or not intraday_sessions:
        raise R6ContractViolation("R6 strict session intersection is empty")
    if daily_sessions[-1] < date(2026, 7, 1) or intraday_sessions[-1] < date(2026, 7, 1):
        raise R6ContractViolation("R6 market data does not reach July 2026")
    return R6Panel(
        daily=daily,
        intraday=intraday,
        daily_sessions=daily_sessions,
        intraday_sessions=intraday_sessions,
    )


def build_r6_daily_features(panel: R6Panel) -> R6DailyFeatures:
    close = _daily_field(panel, "close")
    returns = close.pct_change(fill_method=None)
    sector_close = close.loc[:, SECTOR_SYMBOLS]
    spy_returns = returns[SPY]

    mom_21 = sector_close / sector_close.shift(21) - 1.0
    mom_63 = sector_close / sector_close.shift(63) - 1.0
    mom_126_skip21 = sector_close.shift(21) / sector_close.shift(126) - 1.0
    mom_252_skip21 = sector_close.shift(21) / sector_close.shift(252) - 1.0
    spy_mom_63 = close[SPY] / close[SPY].shift(63) - 1.0
    relative_spy_63 = mom_63.sub(spy_mom_63, axis=0)
    moving_average_126 = sector_close.rolling(126, min_periods=126).mean()
    realized_vol_21 = returns.loc[:, SECTOR_SYMBOLS].rolling(21, min_periods=21).std() * math.sqrt(
        252.0
    )

    raw_score = (
        0.30 * _cross_section_rank(mom_21)
        + 0.30 * _cross_section_rank(mom_63)
        + 0.25 * _cross_section_rank(mom_126_skip21)
        + 0.15 * _cross_section_rank(mom_252_skip21)
    )
    raw_eligible = (sector_close > moving_average_126) & (relative_spy_63 > 0.0)

    spy_variance = spy_returns.rolling(126, min_periods=126).var()
    beta = pd.DataFrame(index=close.index, columns=SECTOR_SYMBOLS, dtype=float)
    residual = pd.DataFrame(index=close.index, columns=SECTOR_SYMBOLS, dtype=float)
    for symbol in SECTOR_SYMBOLS:
        covariance = returns[symbol].rolling(126, min_periods=126).cov(spy_returns)
        beta[symbol] = covariance / spy_variance.where(spy_variance.abs() >= 1e-12)
        residual[symbol] = returns[symbol] - beta[symbol] * spy_returns
    residual_momentum_63 = residual.rolling(63, min_periods=63).sum()
    residual_momentum_126_skip21 = residual.shift(21).rolling(105, min_periods=105).sum()
    block_returns = [
        sector_close.shift(offset) / sector_close.shift(offset + 21) - 1.0
        for offset in (0, 21, 42, 63, 84, 105)
    ]
    trend_consistency = sum((block > 0.0).astype(float) for block in block_returns) / 6.0
    trend_consistency = trend_consistency.where(
        sum(block.notna().astype(int) for block in block_returns) == 6
    )
    residual_score = (
        0.40 * _cross_section_rank(residual_momentum_63)
        + 0.35 * _cross_section_rank(residual_momentum_126_skip21)
        + 0.25 * _cross_section_rank(trend_consistency)
    )
    residual_eligible = (sector_close > moving_average_126) & (trend_consistency >= 0.5)

    sector_breadth = (sector_close > moving_average_126).mean(axis=1)
    spy_ma_126 = close[SPY].rolling(126, min_periods=126).mean()
    regime_on = (close[SPY] > spy_ma_126) & (sector_breadth >= 0.45)
    complete = (
        raw_score.notna().all(axis=1)
        & residual_score.notna().all(axis=1)
        & realized_vol_21.notna().all(axis=1)
        & regime_on.notna()
    )
    valid_dates = list(complete.index[complete])
    if not valid_dates:
        raise R6ContractViolation("R6 daily feature warmup never completes")
    evaluation_start = valid_dates[0]
    return R6DailyFeatures(
        raw_score=raw_score,
        residual_score=residual_score,
        raw_eligible=raw_eligible,
        residual_eligible=residual_eligible,
        realized_vol_21=realized_vol_21,
        regime_on=regime_on,
        sector_breadth_126=sector_breadth,
        evaluation_start=evaluation_start,
    )


def build_daily_candidate_weights(
    candidate_id: str,
    panel: R6Panel,
    features: R6DailyFeatures,
) -> pd.DataFrame:
    if candidate_id not in {"D01", "D02", "D03", "D04", "D05", "N01"}:
        raise R6ContractViolation(f"unsupported daily candidate: {candidate_id}")
    dates = list(panel.daily_sessions)
    output = pd.DataFrame(0.0, index=dates, columns=ALL_DAILY_SYMBOLS)
    start_index = dates.index(features.evaluation_start)
    interval = 21 if candidate_id in {"D04", "D05"} else 5
    score = features.raw_score if candidate_id == "D02" else features.residual_score
    eligible = features.raw_eligible if candidate_id == "D02" else features.residual_eligible
    if candidate_id == "N01":
        rng = np.random.default_rng(77)
        source = features.residual_score.loc[dates[start_index:]].copy()
        shuffled = source.iloc[rng.permutation(len(source))].copy()
        shuffled.index = source.index
        score = features.residual_score.copy()
        score.loc[source.index] = shuffled

    current = pd.Series(0.0, index=ALL_DAILY_SYMBOLS, dtype=float)
    for offset, session in enumerate(dates[start_index:]):
        if offset % interval == 0:
            if candidate_id == "D01":
                close = panel.daily[SPY].at[session, "close"]
                history = panel.daily[SPY].loc[:session, "close"].tail(126)
                momentum_history = panel.daily[SPY].loc[:session, "close"].tail(127)
                on = (
                    len(history) == 126
                    and len(momentum_history) == 127
                    and close > float(history.mean())
                    and close / float(momentum_history.iloc[0]) - 1.0 > 0.0
                )
                current[:] = 0.0
                current[SPY] = 1.0 if on else 0.0
            else:
                ranked = _ranked_symbols(score.loc[session], eligible.loc[session])
                previous = [symbol for symbol in SECTOR_SYMBOLS if current[symbol] > 0.0]
                hold_rank = 5 if candidate_id in {"D04", "D05"} else 0
                selected = _select_with_hold_band(ranked, previous, top_n=3, hold_rank=hold_rank)
                current[:] = 0.0
                if selected:
                    if candidate_id == "D05" and bool(features.regime_on.loc[session]):
                        current = _inverse_volatility_weights(
                            selected,
                            features.realized_vol_21.loc[session],
                            target_volatility=0.12,
                        ).reindex(ALL_DAILY_SYMBOLS, fill_value=0.0)
                    elif candidate_id != "D05":
                        current.loc[selected] = 1.0 / len(selected)
        output.loc[session] = current
    return output


def simulate_daily_weights(panel: R6Panel, signal_weights: pd.DataFrame) -> R6Simulation:
    opens = _daily_field(panel, "open").loc[:, signal_weights.columns]
    weights_at_open = signal_weights.shift(1).fillna(0.0).iloc[:-1].copy()
    open_returns = (opens.shift(-1) / opens - 1.0).iloc[:-1]
    weights_at_open = weights_at_open.loc[open_returns.index]
    gross_returns = (weights_at_open * open_returns).sum(axis=1)
    turnover = weights_at_open.diff().abs().sum(axis=1)
    turnover.iloc[0] = weights_at_open.iloc[0].abs().sum()
    if len(turnover):
        turnover.iloc[-1] += weights_at_open.iloc[-1].abs().sum()
    return R6Simulation(
        gross_returns=gross_returns,
        turnover=turnover,
        weights=weights_at_open,
    )


def simulate_intraday_overlay(
    panel: R6Panel,
    features: R6DailyFeatures,
) -> R6Simulation:
    sessions = [
        session
        for session in panel.intraday_sessions
        if session > features.evaluation_start and session in set(panel.daily_sessions)
    ]
    if len(sessions) < 252:
        raise R6ContractViolation("R6 intraday overlay has fewer than 252 complete sessions")
    daily_dates = list(panel.daily_sessions)
    daily_target = build_daily_candidate_weights("D05", panel, features)
    open_daily = _daily_field(panel, "open")
    open_0930, close_1000, open_1030 = _intraday_anchor_frames(panel, sessions)

    weights = pd.DataFrame(0.0, index=sessions[:-1], columns=ALL_DAILY_SYMBOLS)
    gross = pd.Series(0.0, index=sessions[:-1], dtype=float)
    turnover = pd.Series(0.0, index=sessions[:-1], dtype=float)
    current = pd.Series(0.0, index=ALL_DAILY_SYMBOLS, dtype=float)
    for offset, (session, next_session) in enumerate(
        zip(sessions[:-1], sessions[1:], strict=False)
    ):
        next_open_returns = open_daily.loc[next_session] / open_daily.loc[session] - 1.0
        if offset % 21 != 0:
            gross.loc[session] = float((current * next_open_returns).sum())
            weights.loc[session] = current
            continue

        daily_index = daily_dates.index(session)
        if daily_index == 0:
            raise R6ContractViolation("intraday overlay lacks a prior daily signal session")
        prior_session = daily_dates[daily_index - 1]
        base_target = daily_target.loc[prior_session].copy()
        first_hour = close_1000.loc[session] / open_0930.loc[session] - 1.0
        spy_first_hour = float(first_hour[SPY])
        breadth = float((first_hour.loc[list(SECTOR_SYMBOLS)] > 0.0).mean())
        target = base_target.copy()
        for symbol in SECTOR_SYMBOLS:
            increasing = target[symbol] > current[symbol] + 1e-12
            relative = float(first_hour[symbol] - spy_first_hour)
            buy_allowed = spy_first_hour > -0.005 and relative > 0.0 and breadth >= 0.45
            if increasing and not buy_allowed:
                target[symbol] = min(target[symbol], current[symbol])

        pre_returns = open_1030.loc[session] / open_0930.loc[session] - 1.0
        post_returns = open_daily.loc[next_session] / open_1030.loc[session] - 1.0
        pre_portfolio = float((current * pre_returns).sum())
        rebalance_turnover = float((target - current).abs().sum())
        post_portfolio = float((target * post_returns).sum())
        gross.loc[session] = (1.0 + pre_portfolio) * (1.0 + post_portfolio) - 1.0
        turnover.loc[session] = rebalance_turnover
        current = target
        weights.loc[session] = current

    if len(turnover):
        turnover.iloc[-1] += current.abs().sum()
    return R6Simulation(gross_returns=gross, turnover=turnover, weights=weights)


def reject_future_feature_control() -> None:
    raise R6FutureFeatureError("future open is unavailable at complete-session-close decision time")


def run_r6_diagnostics(root: Path | None = None) -> R6DiagnosticResult:
    base = root or project_root()
    _verify_r6_preregistration(base)
    panel = load_r6_panel(base)
    features = build_r6_daily_features(panel)

    simulations = {
        candidate_id: simulate_daily_weights(
            panel, build_daily_candidate_weights(candidate_id, panel, features)
        )
        for candidate_id in ("D01", "D02", "D03", "D04", "D05", "N01")
    }
    simulations["D06"] = simulate_intraday_overlay(panel, features)
    raw_results: dict[str, dict[str, Any]] = {}
    for candidate_id, simulation in simulations.items():
        start = features.evaluation_start
        candidate_results = {}
        for cost_bps in COST_SCENARIOS:
            candidate_results[_cost_key(cost_bps)] = _evaluate_simulation(
                simulation,
                cost_bps=cost_bps,
                start_after=start,
            )
        raw_results[candidate_id] = {
            "candidate_id": candidate_id,
            "status": "completed",
            "cost_scenarios": candidate_results,
        }

    contract_audit = _build_r6_contract_audit(panel, features, raw_results)
    results = {
        candidate_id: _invalid_r6_result(
            raw_results[candidate_id],
            status="invalid_control" if candidate_id == "N01" else "invalid_contract",
            reason_codes=contract_audit["candidate_reason_codes"][candidate_id],
        )
        for candidate_id in simulations
    }
    results["E01"] = _skipped_result("E01", "real_historical_SEC_PIT_packets_missing")
    results["E02"] = _skipped_result(
        "E02", "real_historical_news_earnings_call_PIT_packets_missing"
    )
    try:
        reject_future_feature_control()
    except R6FutureFeatureError as exc:
        results["N02"] = {
            "candidate_id": "N02",
            "status": "invalid_control",
            "reason_codes": ["tautological_future_feature_stub_not_strategy_path"],
            "metrics_authority": False,
            "selection_prohibited": True,
            "raw_control_outcome": {
                "status": "rejected_control",
                "reason_code": "future_feature_availability_rejected",
                "detail": str(exc),
            },
        }
    else:  # pragma: no cover - the control must always fail closed
        raise R6ContractViolation("future-feature control was not rejected")

    benchmarks = _annotate_r6_benchmarks(_build_benchmarks(panel, features))
    raw_placebo = _placebo_assessment(raw_results)
    placebo = {
        **raw_placebo,
        "raw_proxy_pass": raw_placebo["pass"],
        "pass": False,
        "contract_valid": False,
        "reason_code": "parent_and_placebo_use_invalid_non_self_financing_accounting",
    }
    candidate_gates = {
        candidate_id: _invalid_r6_candidate_gate(
            _candidate_gate(raw_results[candidate_id]),
            contract_audit["candidate_reason_codes"][candidate_id],
        )
        for candidate_id in ("D01", "D02", "D03", "D04", "D05")
    }
    overfit = _overfit_diagnostics(raw_results)
    overfit.update(
        {
            "raw_proxy_pass": overfit["pass"],
            "pass": False,
            "contract_valid": False,
            "threshold_preregistered": False,
            "reason_codes": [
                "candidate_returns_include_invalid_contracts",
                "DSR_probability_threshold_not_preregistered_numerically",
                "PBO_proxy_is_not_CSCV",
            ],
        }
    )
    ranking = sorted(
        ("D01", "D02", "D03", "D04", "D05"),
        key=lambda candidate_id: (
            _metric_value(
                raw_results[candidate_id]["cost_scenarios"]["10bps"]["aggregate"],
                "sharpe",
                default=-math.inf,
            ),
            candidate_id,
        ),
        reverse=True,
    )
    diagnostic_leader_id = ranking[0]
    selected_id = None
    historical_candidate_gate_pass = False
    formal_forward_count = int(
        _load_json(base / PANEL_MANIFEST_PATH).get("formal_forward_daily_observation_count", 0)
    )

    ledger_rows = []
    manifest = _load_json(base / CANDIDATE_MANIFEST_PATH)
    result_by_id = results
    for candidate in manifest["candidates"]:
        candidate_id = str(candidate["candidate_id"])
        row = {
            "schema_version": 1,
            "iter_id": ITER_ID,
            "candidate_id": candidate_id,
            "path": candidate["path"],
            "role": candidate["role"],
            "method": candidate["method"],
            "ablation": candidate["ablation"],
            "status": result_by_id[candidate_id]["status"],
            "selection_prohibited": bool(candidate.get("selection_prohibited", False)),
            "candidate_binding_sha256": _canonical_sha(candidate),
            "result": result_by_id[candidate_id],
        }
        if candidate_id in candidate_gates:
            row["promotion_gate"] = candidate_gates[candidate_id]
        ledger_rows.append(row)

    payload = {
        "schema_version": 1,
        "report_type": "multiscale_low_turnover_r6_evaluation",
        "iter_id": ITER_ID,
        "strategy_name": STRATEGY_NAME,
        "generated_at": datetime.now(UTC).isoformat(),
        "workflow_pass": False,
        "historical_candidate_gate_pass": historical_candidate_gate_pass,
        "research_pass": False,
        "llm_contribution_pass": False,
        "paper_ready_pass": False,
        "research_pass_blockers": [
            "no_contract_valid_historical_candidate",
            "R6_backtest_accounting_invalid",
            "backtest_forensics_blocked",
            "independent_SIP_or_cross_source_parity_missing",
        ],
        "paper_ready_blockers": [
            "formal_forward_observations_missing"
            if formal_forward_count == 0
            else "formal_forward_gate_not_assessed",
            "matched_paper_TCA_missing",
            "paper_safety_review_missing",
            "promotion_not_passed",
        ],
        "data_scope": {
            "scope": "fixed_sector_etf_IEX_adjusted_diagnostic",
            "daily_session_count": len(panel.daily_sessions),
            "daily_first_session": panel.daily_sessions[0].isoformat(),
            "daily_last_session": panel.daily_sessions[-1].isoformat(),
            "daily_evaluation_start": features.evaluation_start.isoformat(),
            "intraday_complete_session_count": len(panel.intraday_sessions),
            "intraday_first_session": panel.intraday_sessions[0].isoformat(),
            "intraday_last_session": panel.intraday_sessions[-1].isoformat(),
            "formal_forward_start": FORMAL_FORWARD_START,
            "formal_forward_observation_count": formal_forward_count,
            "provider": "alpaca",
            "feed": "iex",
            "adjustment": "all",
        },
        "candidate_accounting": {
            "frozen_candidate_count": len(EXPECTED_CANDIDATE_IDS),
            "completed_count": sum(row["status"] == "completed" for row in results.values()),
            "invalid_contract_count": sum(
                row["status"] == "invalid_contract" for row in results.values()
            ),
            "invalid_control_count": sum(
                row["status"] == "invalid_control" for row in results.values()
            ),
            "dependency_skipped_count": sum(
                row["status"] == "skipped_dependency" for row in results.values()
            ),
            "rejected_control_count": sum(
                row["status"] == "rejected_control" for row in results.values()
            ),
            "unresolved_count": 0,
        },
        "candidate_results": [results[candidate_id] for candidate_id in EXPECTED_CANDIDATE_IDS],
        "candidate_gates": candidate_gates,
        "negative_controls": {
            "score_placebo": placebo,
            "future_feature": results["N02"],
        },
        "overfit_diagnostics": overfit,
        "benchmarks": benchmarks,
        "diagnostic_leader": {
            "candidate_id": None,
            "historical_gate_pass": False,
            "selection_authority": False,
            "reason_code": "no_contract_valid_candidate",
            "metrics_10bps": None,
        },
        "raw_metric_leader": {
            "candidate_id": diagnostic_leader_id,
            "contract_valid": False,
            "selection_authority": False,
            "metrics_10bps": raw_results[diagnostic_leader_id]["cost_scenarios"]["10bps"][
                "aggregate"
            ],
        },
        "selected_candidate_ids": [selected_id] if selected_id else [],
        "selection_note": (
            "Exactly one historically eligible candidate exists, but it remains diagnostic "
            "until forensics and data parity pass."
            if selected_id
            else (
                "No contract-valid candidate exists. Raw R6 metrics are retained only to audit "
                "the failed implementation and cannot authorize forward or paper selection."
            )
        ),
        "contract_audit": contract_audit,
        "input_bindings": {
            "spec_path": str(SPEC_PATH),
            "spec_hash": strategy_content_hash(load_strategy_spec(base / SPEC_PATH)),
            "candidate_manifest_sha256": _sha256_file(base / CANDIDATE_MANIFEST_PATH),
            "data_feasibility_sha256": _sha256_file(base / DATA_FEASIBILITY_PATH),
            "panel_manifest_sha256": _sha256_file(base / PANEL_MANIFEST_PATH),
            "cost_contract_sha256": _sha256_file(base / ITERATION_DIR / "cost-contract.json"),
            "runner_path": str(RUNNER_PATH),
            "runner_sha256": _sha256_file(base / RUNNER_PATH),
        },
    }
    output = ensure_dir(base / ITERATION_DIR)
    evaluation_path = output / "evaluation-report.json"
    markdown_path = output / "evaluation-report.md"
    ledger_path = output / "trial-ledger.jsonl"
    write_json(evaluation_path, payload)
    _write_jsonl(ledger_path, ledger_rows)
    markdown_path.write_text(_render_r6_evaluation(payload), encoding="utf-8")
    write_json(
        output / "feature-diagnostics.json",
        _feature_diagnostics(panel, features),
    )
    write_json(
        output / "forward-observation-status.json",
        {
            "schema_version": 1,
            "iter_id": ITER_ID,
            "formal_forward_start": FORMAL_FORWARD_START,
            "observation_count": formal_forward_count,
            "status": "blocked_no_observations" if formal_forward_count == 0 else "pending_review",
            "broker_orders_authorized": False,
        },
    )
    return R6DiagnosticResult(
        evaluation_path=evaluation_path,
        markdown_path=markdown_path,
        trial_ledger_path=ledger_path,
        payload=payload,
    )


def _verify_r6_preregistration(root: Path) -> None:
    dossier = validate_iteration_dossier(ITER_ID, root, stage="pre-backtest")
    if not dossier.ok:
        raise R6ContractViolation(
            "R6 pre-backtest dossier gate failed: " + ", ".join(dossier.blocked)
        )
    search = _load_json(root / SEARCH_SPACE_PATH)
    manifest_path = root / CANDIDATE_MANIFEST_PATH
    feasibility_path = root / DATA_FEASIBILITY_PATH
    if search.get("candidate_manifest_sha256") != _sha256_file(manifest_path):
        raise R6ContractViolation("R6 candidate manifest hash mismatch")
    if search.get("data_feasibility_sha256") != _sha256_file(feasibility_path):
        raise R6ContractViolation("R6 data feasibility hash mismatch")
    spec = load_strategy_spec(root / SPEC_PATH)
    if search.get("spec_hash") != strategy_content_hash(spec):
        raise R6ContractViolation("R6 StrategySpec hash mismatch")
    manifest = _load_json(manifest_path)
    candidate_ids = tuple(str(row["candidate_id"]) for row in manifest["candidates"])
    if candidate_ids != EXPECTED_CANDIDATE_IDS:
        raise R6ContractViolation("R6 candidate ID accounting or order changed")
    feasibility = _load_json(feasibility_path)
    if feasibility.get("q2_diagnostic_execution_authorized") is not True:
        raise R6ContractViolation("R6 diagnostic execution is not authorized")
    _verify_panel_manifest(root)


def _verify_panel_manifest(root: Path) -> None:
    manifest = _load_json(root / PANEL_MANIFEST_PATH)
    if manifest.get("adjustment") != "all" or manifest.get("fallback_used") is not False:
        raise R6ContractViolation("R6 panel adjustment or fallback contract changed")
    receipt = manifest.get("refresh_receipt", {})
    receipt_path = root / str(receipt.get("path") or "")
    if not receipt_path.exists() or receipt.get("sha256") != _sha256_file(receipt_path):
        raise R6ContractViolation("R6 refresh receipt binding mismatch")
    for row in manifest.get("input_files", []):
        path = root / str(row.get("path") or "")
        if not path.exists() or row.get("sha256") != _sha256_file(path):
            raise R6ContractViolation(f"R6 input file binding mismatch: {path}")
    for key, count_key, sessions_key in (
        ("daily", "strict_common_session_count", "included_sessions"),
        ("intraday", "strict_common_complete_session_count", "included_sessions"),
    ):
        section = manifest.get(key, {})
        sessions = section.get(sessions_key)
        if not isinstance(sessions, list) or len(sessions) != section.get(count_key):
            raise R6ContractViolation(f"R6 {key} explicit session membership mismatch")
        if section.get("included_sessions_sha256") != _canonical_sha(sessions):
            raise R6ContractViolation(f"R6 {key} included session hash mismatch")


def _evaluate_simulation(
    simulation: R6Simulation,
    *,
    cost_bps: float,
    start_after: date,
) -> dict[str, Any]:
    mask = pd.Index(simulation.gross_returns.index).map(lambda value: value > start_after)
    gross = simulation.gross_returns.loc[mask].astype(float)
    turnover = simulation.turnover.reindex(gross.index).fillna(0.0).astype(float)
    weights = simulation.weights.reindex(gross.index).fillna(0.0)
    net = gross - turnover * (cost_bps / 10_000.0)
    aggregate = _performance_payload(net, gross, turnover, weights)
    folds = []
    for fold_number, positions in enumerate(np.array_split(np.arange(len(net)), OUTER_FOLDS), 1):
        if len(positions) == 0:
            continue
        index = net.index[positions]
        fold_payload = _performance_payload(
            net.loc[index], gross.loc[index], turnover.loc[index], weights.loc[index]
        )
        fold_payload.update(
            {
                "fold": fold_number,
                "start": index[0].isoformat(),
                "end": index[-1].isoformat(),
            }
        )
        folds.append(fold_payload)
    return {
        "one_way_cost_bps": cost_bps,
        "aggregate": aggregate,
        "folds": folds,
        "positive_fold_count": sum(
            float(fold.get("total_return_pct") or 0.0) > 0.0 for fold in folds
        ),
    }


def _performance_payload(
    net: pd.Series,
    gross: pd.Series,
    turnover: pd.Series,
    weights: pd.DataFrame,
) -> dict[str, Any]:
    equity = [1.0, *(1.0 + net).cumprod().tolist()]
    exposure = weights.abs().sum(axis=1)
    metrics = build_performance_metrics(
        equity,
        "daily",
        trade_pnls=net.loc[turnover > 0.0].tolist(),
        trade_return_pcts=(net.loc[turnover > 0.0] * 100.0).tolist(),
        exposure_pct=float(exposure.mean() * 100.0) if len(exposure) else 0.0,
        turnover_ratio=float(turnover.sum()),
    )
    return {
        "session_count": len(net),
        "start": net.index[0].isoformat() if len(net) else None,
        "end": net.index[-1].isoformat() if len(net) else None,
        "total_return_pct": _round((equity[-1] - 1.0) * 100.0),
        "gross_total_return_pct": _round(((1.0 + gross).prod() - 1.0) * 100.0),
        "annualized_return_pct": _round(metrics.annualized_return_pct),
        "annualized_volatility_pct": _round(metrics.annualized_volatility_pct),
        "sharpe": _round(metrics.sharpe_ratio),
        "sortino": _round(metrics.sortino_ratio),
        "calmar": _round(metrics.calmar_ratio),
        "max_drawdown_pct": _round(metrics.max_drawdown_pct),
        "win_rate_pct": _round(metrics.win_rate_pct),
        "exposure_pct": _round(metrics.exposure_pct),
        "turnover_units": _round(float(turnover.sum())),
        "rebalance_day_count": int((turnover > 1e-12).sum()),
        "average_daily_turnover": _round(float(turnover.mean()) if len(turnover) else 0.0),
        "maximum_symbol_weight": _round(float(weights.max().max()) if not weights.empty else 0.0),
        "cost_drag_pct_points": _round((((1.0 + gross).prod() - 1.0) - (equity[-1] - 1.0)) * 100.0),
    }


def _build_benchmarks(panel: R6Panel, features: R6DailyFeatures) -> dict[str, Any]:
    templates: dict[str, pd.Series] = {}
    columns = list(ALL_DAILY_SYMBOLS)
    for name, symbol in (
        ("SPY_buy_and_hold", "SPY"),
        ("QQQ_buy_and_hold", "QQQ"),
        ("BIL_cash_proxy", "BIL"),
    ):
        weights = pd.Series(0.0, index=columns, dtype=float)
        weights[symbol] = 1.0
        templates[name] = weights
    equal_weight = pd.Series(0.0, index=columns, dtype=float)
    equal_weight.loc[list(SECTOR_SYMBOLS)] = 1.0 / len(SECTOR_SYMBOLS)
    templates["equal_weight_sector_universe"] = equal_weight
    templates["uninvested_cash"] = pd.Series(0.0, index=columns, dtype=float)

    gross_by_sector = {}
    opens = _daily_field(panel, "open")
    evaluation_mask = pd.Index(opens.index).map(lambda value: value > features.evaluation_start)
    for symbol in SECTOR_SYMBOLS:
        returns = (opens[symbol].shift(-1) / opens[symbol] - 1.0).iloc[:-1]
        returns = returns.loc[evaluation_mask[:-1]]
        gross_by_sector[symbol] = float((1.0 + returns).prod() - 1.0)
    best_symbol = sorted(gross_by_sector, key=lambda symbol: (gross_by_sector[symbol], symbol))[-1]
    best_weight = pd.Series(0.0, index=columns, dtype=float)
    best_weight[best_symbol] = 1.0
    templates["ex_post_best_single_sector_report_only"] = best_weight

    output = {}
    for name, template in templates.items():
        signals = pd.DataFrame(0.0, index=panel.daily_sessions, columns=columns)
        active_dates = signals.loc[features.evaluation_start :].index
        signals.loc[active_dates, :] = np.broadcast_to(
            template.to_numpy(dtype=float),
            (len(active_dates), len(template)),
        )
        simulation = simulate_daily_weights(panel, signals)
        output[name] = {
            "report_only": name == "ex_post_best_single_sector_report_only",
            "fixed_symbol": best_symbol
            if name == "ex_post_best_single_sector_report_only"
            else None,
            "cost_scenarios": {
                _cost_key(cost): _evaluate_simulation(
                    simulation, cost_bps=cost, start_after=features.evaluation_start
                )
                for cost in COST_SCENARIOS
            },
        }
    return output


def _placebo_assessment(results: dict[str, dict[str, Any]]) -> dict[str, Any]:
    parent = results["D03"]["cost_scenarios"]["10bps"]["aggregate"]
    placebo = results["N01"]["cost_scenarios"]["10bps"]["aggregate"]
    sharpe_lift = _metric_value(placebo, "sharpe", 0.0) - _metric_value(parent, "sharpe", 0.0)
    return_lift = (
        _metric_value(placebo, "total_return_pct", 0.0)
        - _metric_value(parent, "total_return_pct", 0.0)
    ) / 100.0
    return {
        "parent_candidate_id": "D03",
        "placebo_candidate_id": "N01",
        "cost_bps": 10.0,
        "sharpe_lift": _round(sharpe_lift),
        "total_return_lift_fraction": _round(return_lift),
        "maximum_sharpe_lift": 0.1,
        "maximum_total_return_lift_fraction": 0.02,
        "pass": sharpe_lift <= 0.1 and return_lift <= 0.02,
    }


def _candidate_gate(result: dict[str, Any]) -> dict[str, Any]:
    ten = result["cost_scenarios"]["10bps"]
    twenty = result["cost_scenarios"]["20bps"]
    aggregate = ten["aggregate"]
    checks = {
        "positive_10bps_total_return": _metric_value(aggregate, "total_return_pct", -math.inf)
        > 0.0,
        "sharpe_at_least_0_5_at_10bps": _metric_value(aggregate, "sharpe", -math.inf) >= 0.5,
        "max_drawdown_no_worse_than_25pct": _metric_value(aggregate, "max_drawdown_pct", -math.inf)
        >= -25.0,
        "at_least_3_positive_10bps_folds": int(ten["positive_fold_count"]) >= 3,
        "positive_20bps_total_return": _metric_value(
            twenty["aggregate"], "total_return_pct", -math.inf
        )
        > 0.0,
        "position_cap_at_most_40pct": _metric_value(aggregate, "maximum_symbol_weight", math.inf)
        <= 0.4 + 1e-9,
    }
    return {"pass": all(checks.values()), "checks": checks}


def _overfit_diagnostics(results: dict[str, dict[str, Any]]) -> dict[str, Any]:
    candidate_ids = ("D01", "D02", "D03", "D04", "D05")
    sharpes = np.array(
        [
            _metric_value(
                results[candidate_id]["cost_scenarios"]["10bps"]["aggregate"],
                "sharpe",
                0.0,
            )
            for candidate_id in candidate_ids
        ],
        dtype=float,
    )
    leader_index = int(np.argmax(sharpes))
    leader_id = candidate_ids[leader_index]
    mean = float(sharpes.mean())
    std = float(sharpes.std(ddof=0))
    expected_max = mean + std * math.sqrt(2.0 * math.log(len(candidate_ids)))
    observations = int(results[leader_id]["cost_scenarios"]["10bps"]["aggregate"]["session_count"])
    standard_error = math.sqrt((1.0 + 0.5 * sharpes[leader_index] ** 2) / observations)
    z_score = (
        (sharpes[leader_index] - expected_max) / standard_error
        if standard_error > 0.0
        else -math.inf
    )
    dsr_probability = NormalDist().cdf(z_score) if math.isfinite(z_score) else 0.0

    fold_failures = 0
    for fold_index in range(OUTER_FOLDS):
        fold_sharpes = [
            _metric_value(
                results[candidate_id]["cost_scenarios"]["10bps"]["folds"][fold_index],
                "sharpe",
                -math.inf,
            )
            for candidate_id in candidate_ids
        ]
        leader_fold = fold_sharpes[leader_index]
        if leader_fold <= float(np.median(fold_sharpes)):
            fold_failures += 1
    pbo_proxy = fold_failures / OUTER_FOLDS
    passed = pbo_proxy < 0.5 and dsr_probability >= 0.95
    return {
        "candidate_count": len(candidate_ids),
        "selected_by_aggregate_sharpe": leader_id,
        "selected_sharpe": _round(sharpes[leader_index]),
        "expected_max_sharpe_proxy": _round(expected_max),
        "deflated_sharpe_probability_proxy": _round(dsr_probability),
        "pbo_proxy": _round(pbo_proxy),
        "pbo_definition": (
            "fraction_of_four_folds_where_aggregate_leader_is_at_or_below_median_candidate_sharpe"
        ),
        "pass": passed,
        "limitations": "Five-candidate, four-fold proxy; not full CSCV or exact non-normal DSR.",
    }


def _daily_field(panel: R6Panel, field: str) -> pd.DataFrame:
    return pd.DataFrame(
        {
            symbol: panel.daily[symbol].loc[list(panel.daily_sessions), field].astype(float)
            for symbol in ALL_DAILY_SYMBOLS
        },
        index=list(panel.daily_sessions),
    )


def _cross_section_rank(frame: pd.DataFrame) -> pd.DataFrame:
    ordered = frame.loc[:, list(SECTOR_SYMBOLS)]
    ranks = ordered.rank(axis=1, method="first", ascending=True, na_option="keep")
    return (ranks - 1.0) / (len(SECTOR_SYMBOLS) - 1.0)


def _ranked_symbols(score: pd.Series, eligible: pd.Series) -> list[str]:
    return sorted(
        [
            symbol
            for symbol in SECTOR_SYMBOLS
            if bool(eligible.get(symbol, False)) and math.isfinite(float(score[symbol]))
        ],
        key=lambda symbol: (-float(score[symbol]), symbol),
    )


def _select_with_hold_band(
    ranked: list[str],
    previous: list[str],
    *,
    top_n: int,
    hold_rank: int,
) -> list[str]:
    retained = [
        symbol
        for symbol in previous
        if symbol in ranked and hold_rank > 0 and ranked.index(symbol) < hold_rank
    ]
    selected = sorted(retained, key=lambda symbol: ranked.index(symbol))[:top_n]
    for symbol in ranked:
        if symbol not in selected:
            selected.append(symbol)
        if len(selected) == top_n:
            break
    return selected


def _inverse_volatility_weights(
    selected: list[str],
    volatility: pd.Series,
    *,
    target_volatility: float,
) -> pd.Series:
    vol = volatility.loc[selected].astype(float).clip(lower=1e-6)
    raw = (1.0 / vol) / (1.0 / vol).sum()
    ex_ante = math.sqrt(float(((raw * vol) ** 2).sum()))
    gross = min(1.0, target_volatility / ex_ante) if ex_ante > 0.0 else 0.0
    weights = (raw * gross).clip(upper=0.4)
    return weights


def _intraday_anchor_frames(
    panel: R6Panel,
    sessions: list[date],
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    open_0930 = pd.DataFrame(index=sessions, columns=CORE_SYMBOLS, dtype=float)
    close_1000 = pd.DataFrame(index=sessions, columns=CORE_SYMBOLS, dtype=float)
    open_1030 = pd.DataFrame(index=sessions, columns=CORE_SYMBOLS, dtype=float)
    for symbol in CORE_SYMBOLS:
        frame = panel.intraday[symbol].copy()
        timestamps = pd.to_datetime(frame["timestamp"], utc=True)
        local = timestamps.dt.tz_convert("America/New_York")
        frame["session"] = local.dt.date
        frame["slot"] = local.dt.strftime("%H:%M")
        indexed = frame.set_index(["session", "slot"])
        for session in sessions:
            try:
                open_0930.at[session, symbol] = float(indexed.at[(session, "09:30"), "open"])
                close_1000.at[session, symbol] = float(indexed.at[(session, "10:00"), "close"])
                open_1030.at[session, symbol] = float(indexed.at[(session, "10:30"), "open"])
            except KeyError as exc:
                raise R6ContractViolation(
                    f"missing intraday anchor for {symbol} {session}"
                ) from exc
    return open_0930, close_1000, open_1030


def _feature_diagnostics(panel: R6Panel, features: R6DailyFeatures) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "iter_id": ITER_ID,
        "evaluation_start": features.evaluation_start.isoformat(),
        "daily_session_count": len(panel.daily_sessions),
        "intraday_complete_session_count": len(panel.intraday_sessions),
        "raw_score_finite_rows": int(features.raw_score.notna().all(axis=1).sum()),
        "residual_score_finite_rows": int(features.residual_score.notna().all(axis=1).sum()),
        "regime_on_session_count": int(features.regime_on.sum()),
        "average_sector_breadth_126": _round(features.sector_breadth_126.mean()),
        "future_feature_used": False,
        "forward_fill_used": False,
        "zero_return_substitution_used": False,
    }


def _skipped_result(candidate_id: str, reason_code: str) -> dict[str, Any]:
    return {
        "candidate_id": candidate_id,
        "status": "skipped_dependency",
        "reason_code": reason_code,
        "selection_prohibited": True,
        "cost_scenarios": None,
    }


def _invalid_r6_result(
    raw_result: dict[str, Any],
    *,
    status: str,
    reason_codes: list[str],
) -> dict[str, Any]:
    return {
        "candidate_id": raw_result["candidate_id"],
        "status": status,
        "reason_codes": list(reason_codes),
        "selection_prohibited": True,
        "metrics_authority": False,
        "cost_scenarios": None,
        "raw_metrics": {
            "status": raw_result["status"],
            "cost_scenarios": raw_result["cost_scenarios"],
            "use": "audit_only_not_strategy_performance_evidence",
        },
    }


def _invalid_r6_candidate_gate(
    raw_gate: dict[str, Any],
    reason_codes: list[str],
) -> dict[str, Any]:
    return {
        "pass": False,
        "contract_valid": False,
        "raw_metric_gate_pass": raw_gate["pass"],
        "checks": {
            **raw_gate["checks"],
            "implementation_contract_valid": False,
        },
        "reason_codes": list(reason_codes),
    }


def _annotate_r6_benchmarks(benchmarks: dict[str, Any]) -> dict[str, Any]:
    for name, row in benchmarks.items():
        if name == "equal_weight_sector_universe":
            raw_cost_scenarios = row.pop("cost_scenarios")
            row.update(
                {
                    "status": "invalid_contract",
                    "metrics_authority": False,
                    "reason_codes": ["non_self_financing_constant_weight_accounting"],
                    "cost_scenarios": None,
                    "raw_metrics": {
                        "cost_scenarios": raw_cost_scenarios,
                        "use": "audit_only_not_benchmark_evidence",
                    },
                }
            )
        else:
            row.update({"status": "completed", "metrics_authority": True})
    return benchmarks


def _build_r6_contract_audit(
    panel: R6Panel,
    features: R6DailyFeatures,
    raw_results: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    daily_dates = list(panel.daily_sessions)
    start_index = daily_dates.index(features.evaluation_start)
    parent_fill_dates = [
        daily_dates[index + 1]
        for index in range(start_index, len(daily_dates), 21)
        if index + 1 < len(daily_dates)
    ]
    overlay_sessions = [
        session
        for session in panel.intraday_sessions
        if session > features.evaluation_start and session in set(panel.daily_sessions)
    ]
    overlay_schedule = overlay_sessions[:-1:21]
    shared_last = overlay_sessions[-2] if len(overlay_sessions) >= 2 else None
    parent_shared_schedule = [
        session
        for session in parent_fill_dates
        if overlay_sessions
        and shared_last is not None
        and overlay_sessions[0] <= session <= shared_last
    ]
    overlap = sorted(set(parent_shared_schedule) & set(overlay_schedule))
    cap_failures = {}
    for candidate_id in ("D01", "D02", "D03", "D04", "D05"):
        maximum = _metric_value(
            raw_results[candidate_id]["cost_scenarios"]["10bps"]["aggregate"],
            "maximum_symbol_weight",
            math.inf,
        )
        if maximum > 0.4 + 1e-9:
            cap_failures[candidate_id] = _round(maximum)

    candidate_reason_codes = {
        "D01": ["strategy_spec_position_cap_not_enforced"],
        "D02": [
            "strategy_spec_position_cap_not_enforced",
            "non_self_financing_constant_weight_accounting",
        ],
        "D03": [
            "strategy_spec_position_cap_not_enforced",
            "non_self_financing_constant_weight_accounting",
        ],
        "D04": [
            "strategy_spec_position_cap_not_enforced",
            "non_self_financing_constant_weight_accounting",
        ],
        "D05": ["non_self_financing_constant_weight_accounting"],
        "D06": [
            "non_self_financing_constant_weight_accounting",
            "parent_rebalance_schedule_mismatch",
            "D05_same_intraday_window_benchmark_missing",
        ],
        "N01": [
            "non_self_financing_constant_weight_accounting",
            "single_shuffle_is_not_placebo_distribution",
        ],
    }
    return {
        "status": "blocked",
        "raw_metrics_authority": False,
        "candidate_reason_codes": candidate_reason_codes,
        "findings": [
            {
                "severity": "P1",
                "code": "non_self_financing_constant_weight_accounting",
                "affected_candidate_ids": ["D02", "D03", "D04", "D05", "D06", "N01"],
                "affected_benchmarks": ["equal_weight_sector_universe"],
                "detail": (
                    "The legacy R6 evaluator applies unchanged target weights on every return "
                    "row and charges turnover only when targets change. Holdings drift is not "
                    "represented, so multi-asset returns, exposure, turnover, and costs are "
                    "invalid."
                ),
            },
            {
                "severity": "P1",
                "code": "parent_rebalance_schedule_mismatch",
                "affected_candidate_ids": ["D06"],
                "detail": (
                    "D06 anchors its 21-session schedule to the first intraday-complete session "
                    "instead of reusing D05's actual next-open execution mask."
                ),
            },
            {
                "severity": "P1",
                "code": "strategy_spec_position_cap_not_enforced",
                "affected_candidate_ids": sorted(cap_failures),
                "maximum_symbol_weights_at_10bps": cap_failures,
                "declared_maximum": 0.4,
            },
            {
                "severity": "P1",
                "code": "implementation_not_bound_in_original_report",
                "detail": "The regenerated audit report adds the runner path and SHA-256 binding.",
            },
            {
                "severity": "P2",
                "code": "future_feature_control_tautological",
                "affected_candidate_ids": ["N02"],
                "detail": (
                    "The control raises directly and does not exercise the candidate feature path."
                ),
            },
            {
                "severity": "P2",
                "code": "terminal_execution_date_reported_one_session_early",
                "reported_return_row_end": panel.daily_sessions[-2].isoformat(),
                "terminal_liquidation_session": panel.daily_sessions[-1].isoformat(),
            },
        ],
        "D06_schedule_evidence": {
            "parent_D05_shared_fill_count": len(parent_shared_schedule),
            "D06_overlay_rebalance_count": len(overlay_schedule),
            "exact_overlap_count": len(overlap),
            "parent_D05_first_fill": parent_shared_schedule[0].isoformat()
            if parent_shared_schedule
            else None,
            "D06_first_rebalance": overlay_schedule[0].isoformat() if overlay_schedule else None,
            "overlap_dates": [session.isoformat() for session in overlap],
            "parent_D05_shared_fill_dates_sha256": _canonical_sha(
                [session.isoformat() for session in parent_shared_schedule]
            ),
            "D06_overlay_rebalance_dates_sha256": _canonical_sha(
                [session.isoformat() for session in overlay_schedule]
            ),
        },
    }


def _cost_key(value: float) -> str:
    return f"{int(value)}bps" if float(value).is_integer() else f"{value:g}bps"


def _metric_value(
    payload: dict[str, Any],
    key: str,
    default: float,
) -> float:
    value = payload.get(key)
    if value is None:
        return float(default)
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return float(default)
    return parsed if math.isfinite(parsed) else float(default)


def _round(value: float | None, digits: int = 6) -> float | None:
    if value is None:
        return None
    parsed = float(value)
    return round(parsed, digits) if math.isfinite(parsed) else None


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    ensure_dir(path.parent)
    path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def _render_r6_evaluation(payload: dict[str, Any]) -> str:
    raw_leader = payload["raw_metric_leader"]
    lines = [
        "# R6 Low-Turnover Multiscale Evaluation",
        "",
        f"- Workflow pass: `{payload['workflow_pass']}`",
        f"- Historical candidate gate pass: `{payload['historical_candidate_gate_pass']}`",
        f"- Research pass: `{payload['research_pass']}`",
        f"- LLM contribution pass: `{payload['llm_contribution_pass']}`",
        f"- Paper-ready pass: `{payload['paper_ready_pass']}`",
        "- Contract-valid diagnostic leader: `none`",
        f"- Raw metric leader (invalid, audit only): `{raw_leader['candidate_id']}`",
        "- Formal-forward observations: "
        f"`{payload['data_scope']['formal_forward_observation_count']}`",
        "",
        "## Candidate Results At 10 bps One-Way",
        "",
        "| Candidate | Status | Total return | Sharpe | Max drawdown | Positive folds | Turnover |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for row in payload["candidate_results"]:
        if row["status"] in {"invalid_contract", "invalid_control"} and row.get("raw_metrics"):
            ten = row["raw_metrics"]["cost_scenarios"]["10bps"]
            aggregate = ten["aggregate"]
            lines.append(
                (
                    "| {candidate} | {status} (raw audit only) | {total}% | {sharpe} | "
                    "{drawdown}% | {folds}/4 | {turnover} |"
                ).format(
                    candidate=row["candidate_id"],
                    status=row["status"],
                    total=aggregate["total_return_pct"],
                    sharpe=aggregate["sharpe"],
                    drawdown=aggregate["max_drawdown_pct"],
                    folds=ten["positive_fold_count"],
                    turnover=aggregate["turnover_units"],
                )
            )
            continue
        if row["status"] != "completed":
            lines.append(
                f"| {row['candidate_id']} | {row['status']} | n/a | n/a | n/a | n/a | n/a |"
            )
            continue
        ten = row["cost_scenarios"]["10bps"]
        aggregate = ten["aggregate"]
        lines.append(
            (
                "| {candidate} | completed | {total}% | {sharpe} | {drawdown}% "
                "| {folds}/4 | {turnover} |"
            ).format(
                candidate=row["candidate_id"],
                total=aggregate["total_return_pct"],
                sharpe=aggregate["sharpe"],
                drawdown=aggregate["max_drawdown_pct"],
                folds=ten["positive_fold_count"],
                turnover=aggregate["turnover_units"],
            )
        )
    lines.extend(
        [
            "",
            "## Controls And Limits",
            "",
            "- Shuffled-score placebo valid/pass: "
            f"`{payload['negative_controls']['score_placebo']['contract_valid']}` / "
            f"`{payload['negative_controls']['score_placebo']['pass']}`",
            f"- PBO proxy: `{payload['overfit_diagnostics']['pbo_proxy']}`",
            "- Deflated Sharpe probability proxy: "
            f"`{payload['overfit_diagnostics']['deflated_sharpe_probability_proxy']}`",
            "- D02-D06 multi-asset raw metrics use invalid non-self-financing accounting.",
            "- D06 does not share D05's rebalance mask and cannot measure intraday lift.",
            "- D01-D04 violate the StrategySpec 40 percent symbol cap.",
            "- The future-feature control is a stub, not an end-to-end availability test.",
            "- Event candidates use no fixture or retrospective LLM substitute.",
            "- IEX data remains diagnostic until independent consolidated-price parity "
            "and matched TCA exist.",
            "- No candidate has broker order authority.",
            "",
            "R6 is frozen as failed implementation evidence. No raw return in this report is "
            "eligible for strategy selection or paper simulation.",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def _alpaca_response_frame(response: Any, symbol: str) -> pd.DataFrame:
    raw = response.df.reset_index()
    if "symbol" in raw:
        raw = raw.loc[raw["symbol"].astype(str).str.upper() == symbol].drop(columns="symbol")
    if raw.empty:
        raise R6ContractViolation(f"Alpaca returned no bars for {symbol}")
    frame = normalize_ohlcv(raw)
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
    return frame.sort_values("timestamp").drop_duplicates("timestamp", keep="last")


def _regular_session_only(frame: pd.DataFrame) -> pd.DataFrame:
    timestamps = pd.to_datetime(frame["timestamp"], utc=True)
    local = timestamps.dt.tz_convert("America/New_York")
    minutes = local.dt.hour * 60 + local.dt.minute
    return frame.loc[(minutes >= 9 * 60 + 30) & (minutes < 16 * 60)].reset_index(drop=True)


def _write_snapshot(path: Path, frame: pd.DataFrame) -> None:
    ensure_dir(path.parent)
    output = frame.loc[:, ["timestamp", *PRIMITIVE_FIELDS]].copy()
    output["timestamp"] = pd.to_datetime(output["timestamp"], utc=True).map(
        lambda value: value.isoformat()
    )
    output.to_csv(path, index=False)


def _receipt_row(
    root: Path,
    path: Path,
    *,
    symbol: str,
    timeframe: str,
    requested_start: datetime,
    requested_end: datetime,
) -> dict[str, Any]:
    frame = _load_market_frame(path)
    timestamps = pd.to_datetime(frame["timestamp"], utc=True)
    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "path": str(path.relative_to(root)),
        "record_count": len(frame),
        "first_timestamp": timestamps.min().isoformat(),
        "last_timestamp": timestamps.max().isoformat(),
        "sha256": _sha256_file(path),
        "requested_start": requested_start.isoformat(),
        "requested_end": requested_end.isoformat(),
        "provider": "alpaca",
        "feed": "iex",
        "adjustment": "all",
        "source_mode": "live_fetch",
        "fallback_used": False,
    }


def _load_market_frame(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise R6ContractViolation(f"required R6 market file is missing: {path}")
    frame = normalize_ohlcv(pd.read_csv(path))
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True, errors="raise")
    if frame.empty:
        raise R6ContractViolation(f"R6 market file is empty: {path}")
    if frame["timestamp"].duplicated().any() or not frame["timestamp"].is_monotonic_increasing:
        raise R6ContractViolation(f"timestamps are duplicate or non-monotonic: {path}")
    values = frame.loc[:, PRIMITIVE_FIELDS].to_numpy(dtype=float)
    if not np.isfinite(values).all():
        raise R6ContractViolation(f"non-finite OHLCV value: {path}")
    if (frame[["open", "high", "low", "close"]] <= 0).any().any():
        raise R6ContractViolation(f"non-positive price: {path}")
    if (frame["volume"] < 0).any():
        raise R6ContractViolation(f"negative volume: {path}")
    return frame


def _daily_sessions(frame: pd.DataFrame) -> pd.Series:
    return pd.to_datetime(frame["timestamp"], utc=True).dt.tz_convert("America/New_York").dt.date


def _complete_intraday_sessions(frame: pd.DataFrame, minutes: int) -> set[date]:
    timestamps = pd.to_datetime(frame["timestamp"], utc=True)
    local_days = timestamps.dt.tz_convert("America/New_York").dt.date
    complete: set[date] = set()
    for session, indexes in local_days.groupby(local_days).groups.items():
        expected = expected_us_equity_rth_bar_starts(session, minutes)
        observed = set(timestamps.loc[indexes])
        if expected and observed == expected:
            complete.add(session)
    return complete


def _calendar_sessions(start: date, end: date) -> tuple[date, ...]:
    sessions = []
    current = start
    while current <= end:
        if us_equity_session_close(current) is not None:
            sessions.append(current)
        current += timedelta(days=1)
    return tuple(sessions)


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise R6ContractViolation(f"invalid JSON artifact: {path}") from exc
    if not isinstance(payload, dict):
        raise R6ContractViolation(f"JSON artifact must be an object: {path}")
    return payload


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_sha(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _git_provenance(root: Path) -> dict[str, Any]:
    def run(*args: str) -> str:
        result = subprocess.run(
            ["git", *args],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stdout

    status = run("status", "--porcelain=v1", "--untracked-files=all")
    return {
        "git_commit": run("rev-parse", "HEAD").strip(),
        "worktree_dirty": bool(status.strip()),
        "worktree_status_sha256": hashlib.sha256(status.encode()).hexdigest(),
    }


def _finite_or_none(value: float) -> float | None:
    return float(value) if math.isfinite(float(value)) else None
