from __future__ import annotations

import hashlib
import io
import json
import math
import os
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib.metadata import version
from itertools import combinations
from pathlib import Path
from statistics import NormalDist
from typing import Any

import numpy as np
import pandas as pd
from scipy.optimize import minimize

from open_composer.adapters.data.alpaca import AlpacaDataError
from open_composer.adapters.data.alpaca_snapshot import verify_alpaca_contract_snapshot
from open_composer.config import ensure_dir
from open_composer.market_calendar import NEW_YORK
from open_composer.models.strategy_spec import StrategySpec, load_strategy_spec
from open_composer.research.iteration_dossier import validate_iteration_dossier
from open_composer.strategy_versions import strategy_content_hash

ITER_ID = "mom_multiasset_forward_multimodal_r4"
ITERATION_DIR = Path("reports/research/iterations") / ITER_ID
DATA_DIR = Path("data/research/alpaca_etf_structural_r9")
SPEC_PATHS = {
    candidate_id: Path(f"strategy_specs/drafts/us_multiasset_forward_mm_r4_{suffix}.yaml")
    for candidate_id, suffix in {
        "R4D01": "d01",
        "R4D02": "d02",
        "R4M01": "m01",
        "R4M02": "m02",
        "R4L01": "l01",
        "R4C01": "c01",
        "R4F01": "f01",
        "R4P01": "p01",
    }.items()
}
RANKABLE_SYMBOLS = (
    "GLD",
    "IEF",
    "QQQ",
    "SPY",
    "XLB",
    "XLE",
    "XLF",
    "XLI",
    "XLK",
    "XLP",
    "XLU",
    "XLV",
    "XLY",
)
RESERVE_SYMBOL = "BIL"
CORE_FEATURES = (
    "mom_21",
    "mom_63",
    "mom_126_skip21",
    "mom_252_skip21",
    "trend_gap_126",
    "vol_21",
    "drawdown_63",
)
FORMULA_FEATURES = (
    "llm_momentum_quality",
    "llm_volume_confirmed_trend",
    "llm_rebound_trap",
    "llm_crowding_risk",
)
TOP_N = 3
HORIZON_SESSIONS = 21
EMBARGO_SESSIONS = 21
TRAINING_WINDOW_SESSIONS = 756
PRIMARY_COST_BPS = 10.0
STRESS_COST_BPS = 20.0
SEVERE_COST_BPS = 35.0
PLACEBO_SEED = 4199
FORMULA_PARAM_KEYS = (
    "transform",
    "rank_method",
    "full_sample_fit",
    "components",
    "coefficients",
    "population",
    "rank_ascending",
    "tie_break",
    "apply_at",
)


@dataclass(frozen=True)
class PanelData:
    open: pd.DataFrame
    high: pd.DataFrame
    low: pd.DataFrame
    close: pd.DataFrame
    volume: pd.DataFrame
    manifest: dict[str, Any]


@dataclass(frozen=True)
class FeatureBundle:
    raw: dict[str, pd.DataFrame]
    ranked: dict[str, pd.DataFrame]
    formulas: dict[str, pd.DataFrame]


@dataclass(frozen=True)
class ExactSimulationResult:
    daily: pd.DataFrame
    events: list[dict[str, Any]]
    metrics: dict[str, Any]


@dataclass(frozen=True)
class R4EvaluationResult:
    evaluation_path: Path
    evaluation_markdown_path: Path
    receipt_path: Path
    payload: dict[str, Any]


@dataclass(frozen=True)
class R4FreezeResult:
    preregistration_lock_path: Path
    runner_lock_path: Path
    lock_anchor_path: Path
    lock_anchor_sha256: str
    payload: dict[str, Any]


def _validate_r4_spec_execution_contract(
    specs: dict[str, StrategySpec],
) -> dict[str, Any]:
    if set(specs) != set(SPEC_PATHS):
        raise ValueError("R4 spec set must contain exactly the eight frozen candidates")

    expected_universe = {RESERVE_SYMBOL, *RANKABLE_SYMBOLS}
    for candidate_id, spec in specs.items():
        notes = spec.notes.model_dump(mode="json")
        portfolio = spec.portfolio
        checks = {
            "candidate_id": notes.get("candidate_id") == candidate_id,
            "daily": spec.timeframe == "daily",
            "long_only": spec.position_direction == "long_only",
            "universe": set(spec.universe) == expected_universe,
            "portfolio_mode": portfolio.mode == "cross_sectional_momentum",
            "execution_profile": (
                portfolio.cross_sectional_execution_profile == "monthly_equal_weight_bil_reserve"
            ),
            "rebalance_schedule": portfolio.rebalance_schedule == "calendar_month_end",
            "weighting": portfolio.weighting == "equal_weight",
            "reserve_symbol": portfolio.reserve_symbol == RESERVE_SYMBOL,
            "reserve_cap_exemption": portfolio.reserve_exempt_from_max_symbol_weight is True,
            "position_weight_enforcement": portfolio.position_weight_enforcement == "entry_only",
            "top_n": portfolio.max_symbols_per_day == TOP_N,
            "gross_exposure": portfolio.gross_exposure_limit == 1.0,
            "portfolio_weight_cap": portfolio.max_symbol_weight == 0.34,
            "risk_weight_cap": spec.risk.max_position_weight == 0.34,
            "manual_only": spec.execution.mode == "manual_signal",
            "broker_none": spec.execution.broker == "none",
            "decision_close": spec.execution.signal_on == "bar_close",
            "next_open": spec.execution.fill_assumption == "next_bar_open",
            "commission": spec.costs.commission_pct == 0.0,
            "primary_cost": spec.costs.slippage_bps == PRIMARY_COST_BPS,
            "impact_model": spec.costs.impact_model == "linear",
            "impact_eta": spec.costs.impact_eta == 0.0,
            "impact_gamma": spec.costs.impact_gamma == 0.0,
        }
        failed = sorted(name for name, passed in checks.items() if not passed)
        if failed:
            raise ValueError(
                f"R4 StrategySpec execution contract mismatch for {candidate_id}: {failed}"
            )

    formula_specs = {candidate_id: specs[candidate_id] for candidate_id in ("R4L01", "R4C01")}
    for name in FORMULA_FEATURES:
        reference = {
            key: formula_specs["R4C01"].factors[name].params.get(key) for key in FORMULA_PARAM_KEYS
        }
        for candidate_id, spec in formula_specs.items():
            actual = {key: spec.factors[name].params.get(key) for key in FORMULA_PARAM_KEYS}
            if actual != reference:
                raise ValueError(f"R4 formula contract mismatch for {candidate_id}:{name}")
        placebo = specs["R4P01"].factors[name].params
        actual_placebo = {key: placebo.get(key) for key in FORMULA_PARAM_KEYS}
        if actual_placebo != reference:
            raise ValueError(f"R4 placebo formula contract mismatch for {name}")
        if (
            placebo.get("placebo_operation") != "per_decision_session_symbol_permutation"
            or placebo.get("placebo_mapping") != "same_permutation_for_all_formula_columns"
            or placebo.get("placebo_seed") != PLACEBO_SEED
        ):
            raise ValueError(f"R4 placebo metadata mismatch for {name}")

    c01_model = specs["R4C01"].model
    p01_model = specs["R4P01"].model
    if (
        c01_model is None
        or p01_model is None
        or c01_model.model_dump(mode="json") != (p01_model.model_dump(mode="json"))
    ):
        raise ValueError("R4C01 and R4P01 must use an identical frozen model contract")
    m01_model = specs["R4M01"].model
    if m01_model is None or c01_model is None:
        raise ValueError("R4M01 and R4C01 require frozen model contracts")
    m01_paired = m01_model.model_dump(mode="json")
    c01_paired = c01_model.model_dump(mode="json")
    m01_paired.pop("features", None)
    c01_paired.pop("features", None)
    if m01_paired != c01_paired:
        raise ValueError("R4M01 and R4C01 model contracts may differ only by feature columns")
    m02_model = specs["R4M02"].model
    if (
        m02_model is None
        or m02_model.selection.method != "threshold"
        or m02_model.selection.threshold != 0.55
    ):
        raise ValueError("R4M02 must use the frozen 0.55 survival threshold")
    return {
        "rebalance_schedule": "calendar_month_end",
        "weighting": "equal_weight",
        "reserve_symbol": RESERVE_SYMBOL,
        "top_n": TOP_N,
        "formula_spec_candidate_id": "R4C01",
        "placebo_spec_candidate_id": "R4P01",
    }


def build_point_in_time_features(
    close: pd.DataFrame,
    volume: pd.DataFrame,
    *,
    rankable_symbols: tuple[str, ...] = RANKABLE_SYMBOLS,
    formula_spec: StrategySpec | None = None,
) -> FeatureBundle:
    prices = _strict_numeric_panel(close, "close", positive=True)
    volumes = _strict_numeric_panel(volume, "volume", positive=False).reindex_like(prices)
    if volumes.isna().any().any() or (volumes < 0).any().any():
        raise ValueError("volume must align with closes and remain nonnegative")
    missing = sorted(set(rankable_symbols) - set(prices.columns))
    if missing:
        raise ValueError("rankable symbols missing from feature panel: " + ", ".join(missing))

    daily = prices.pct_change(fill_method=None)
    raw = {
        "mom_21": prices.div(prices.shift(21)).sub(1.0),
        "mom_63": prices.div(prices.shift(63)).sub(1.0),
        "mom_126_skip21": prices.shift(21).div(prices.shift(126)).sub(1.0),
        "mom_252_skip21": prices.shift(21).div(prices.shift(252)).sub(1.0),
        "trend_gap_126": prices.div(prices.rolling(126, min_periods=126).mean()).sub(1.0),
        "trend_gap_252": prices.div(prices.rolling(252, min_periods=252).mean()).sub(1.0),
        "vol_21": daily.rolling(21, min_periods=21).std(ddof=0),
        "vol_63": daily.rolling(63, min_periods=63).std(ddof=0),
        "drawdown_63": prices.div(prices.rolling(63, min_periods=63).max()).sub(1.0),
        "high_gap_63": prices.div(prices.rolling(63, min_periods=63).max()).sub(1.0),
        "high_gap_252": prices.div(prices.rolling(252, min_periods=252).max()).sub(1.0),
        "volume_surprise_5": volumes.div(
            volumes.rolling(5, min_periods=5).mean().replace(0.0, np.nan)
        ).sub(1.0),
        "volume_surprise_21": volumes.div(
            volumes.rolling(21, min_periods=21).mean().replace(0.0, np.nan)
        ).sub(1.0),
        "ma_gap_50": prices.div(prices.rolling(50, min_periods=50).mean()).sub(1.0),
    }
    ranked = {
        name: cross_sectional_percentile_rank(frame, rankable_symbols=rankable_symbols)
        for name, frame in raw.items()
    }
    formulas = formula_features_from_spec(ranked, formula_spec=formula_spec)
    return FeatureBundle(raw=raw, ranked=ranked, formulas=formulas)


def cross_sectional_percentile_rank(
    frame: pd.DataFrame,
    *,
    rankable_symbols: tuple[str, ...] = RANKABLE_SYMBOLS,
) -> pd.DataFrame:
    symbols = sorted(rankable_symbols)
    values = frame.reindex(columns=symbols).astype(float)
    return values.rank(axis=1, method="first", ascending=True, pct=True)


def formula_features_from_spec(
    ranked: dict[str, pd.DataFrame],
    *,
    formula_spec: StrategySpec | None,
) -> dict[str, pd.DataFrame]:
    defaults = {
        "llm_momentum_quality": (
            ["mom_126_skip21", "high_gap_252", "vol_63"],
            [1.0, 1.0, -1.0],
        ),
        "llm_volume_confirmed_trend": (
            ["mom_63", "volume_surprise_21", "ma_gap_50"],
            [1.0, 1.0, 1.0],
        ),
        "llm_rebound_trap": (
            ["mom_21", "mom_126_skip21", "drawdown_63"],
            [1.0, -1.0, -1.0],
        ),
        "llm_crowding_risk": (
            ["mom_21", "volume_surprise_5", "high_gap_63", "mom_252_skip21"],
            [1.0, 1.0, 1.0, -1.0],
        ),
    }
    formulas: dict[str, pd.DataFrame] = {}
    for name in FORMULA_FEATURES:
        if formula_spec is None:
            components, coefficients = defaults[name]
        else:
            factor = formula_spec.factors.get(name)
            if factor is None:
                raise ValueError(f"formula factor missing from StrategySpec: {name}")
            params = factor.params
            if (
                params.get("transform")
                != "weighted_sum_of_component_cross_sectional_percentile_ranks"
                or params.get("rank_method") != "percentile_rank_by_decision_session"
                or params.get("full_sample_fit") is not False
                or params.get("population") != "rankable_symbols_with_finite_history"
                or params.get("rank_ascending") is not True
                or params.get("tie_break") != "symbol_ascending"
                or params.get("apply_at") != "decision_close"
            ):
                raise ValueError(f"formula rank transform contract mismatch: {name}")
            components = list(map(str, params.get("components") or []))
            coefficients = list(map(float, params.get("coefficients") or []))
        if not components or len(components) != len(coefficients):
            raise ValueError(f"formula component contract mismatch: {name}")
        missing = sorted(set(components) - set(ranked))
        if missing:
            raise ValueError(f"formula components missing for {name}: {', '.join(missing)}")
        value = ranked[components[0]] * coefficients[0]
        for component, coefficient in zip(components[1:], coefficients[1:], strict=True):
            value = value + ranked[component] * coefficient
        formulas[name] = value
    return formulas


def joint_formula_placebo(
    formulas: dict[str, pd.DataFrame],
    *,
    seed: int = PLACEBO_SEED,
    placebo_spec: StrategySpec | None = None,
) -> dict[str, pd.DataFrame]:
    if set(formulas) != set(FORMULA_FEATURES):
        raise ValueError("placebo requires the exact four frozen formula features")
    if placebo_spec is not None:
        factor_params = [placebo_spec.factors[name].params for name in FORMULA_FEATURES]
        seeds = {int(params.get("placebo_seed", -1)) for params in factor_params}
        if seeds != {PLACEBO_SEED} or any(
            params.get("placebo_operation") != "per_decision_session_symbol_permutation"
            or params.get("placebo_mapping") != "same_permutation_for_all_formula_columns"
            for params in factor_params
        ):
            raise ValueError("P01 placebo StrategySpec metadata mismatch")
        seed = seeds.pop()
    template = formulas[FORMULA_FEATURES[0]]
    symbols = sorted(template.columns)
    result = {name: frame.copy() for name, frame in formulas.items()}
    for name, frame in formulas.items():
        if not frame.index.equals(template.index) or list(frame.columns) != list(template.columns):
            raise ValueError(f"formula panel identity mismatch: {name}")
    for session in template.index:
        date = pd.Timestamp(session).date().isoformat()
        destinations = sorted(
            symbols,
            key=lambda symbol: hashlib.sha256(
                f"{seed}|{date}|{symbol}".encode("ascii")
            ).hexdigest(),
        )
        for name, frame in formulas.items():
            source_values = frame.loc[session, symbols].to_numpy(dtype=float)
            result[name].loc[session, destinations] = source_values
    return result


def month_end_decision_points(
    index: pd.DatetimeIndex,
    *,
    rebalance_schedule: str = "calendar_month_end",
) -> list[dict[str, Any]]:
    if rebalance_schedule != "calendar_month_end":
        raise ValueError("R4 requires rebalance_schedule=calendar_month_end")
    sessions = pd.DatetimeIndex(index)
    if sessions.has_duplicates or not sessions.is_monotonic_increasing:
        raise ValueError("decision sessions must be unique and increasing")
    periods = sessions.to_period("M")
    points: list[dict[str, Any]] = []
    for position in range(len(sessions) - 1):
        if periods[position] == periods[position + 1]:
            continue
        points.append(
            {
                "decision_position": position,
                "decision_session": sessions[position],
                "execution_position": position + 1,
                "execution_session": sessions[position + 1],
                "label_end_position": position + 1 + HORIZON_SESSIONS,
            }
        )
    return points


def build_monthly_feature_dataset(
    panel: PanelData,
    features: FeatureBundle,
    *,
    rankable_symbols: tuple[str, ...] = RANKABLE_SYMBOLS,
    placebo_spec: StrategySpec | None = None,
    rebalance_schedule: str = "calendar_month_end",
) -> pd.DataFrame:
    sessions = panel.close.index
    placebo_formulas = joint_formula_placebo(
        features.formulas,
        placebo_spec=placebo_spec,
    )
    rows: list[dict[str, Any]] = []
    for point in month_end_decision_points(
        sessions,
        rebalance_schedule=rebalance_schedule,
    ):
        decision = point["decision_session"]
        entry_position = int(point["execution_position"])
        label_end_position = int(point["label_end_position"])
        for symbol in sorted(rankable_symbols):
            row: dict[str, Any] = {
                **point,
                "decision_session": decision.date().isoformat(),
                "execution_session": point["execution_session"].date().isoformat(),
                "symbol": symbol,
            }
            for name in CORE_FEATURES:
                row[name] = features.ranked[name].at[decision, symbol]
            for name in FORMULA_FEATURES:
                row[name] = features.formulas[name].at[decision, symbol]
                row[f"placebo_{name}"] = placebo_formulas[name].at[decision, symbol]
            for name in ("mom_126_skip21", "mom_252_skip21", "trend_gap_252"):
                row[f"raw_{name}"] = features.raw[name].at[decision, symbol]
            if label_end_position < len(sessions):
                entry = float(panel.open.iloc[entry_position][symbol])
                terminal = float(panel.open.iloc[label_end_position][symbol])
                path = panel.open[symbol].iloc[entry_position : label_end_position + 1]
                path_drawdown = path.div(path.cummax()).sub(1.0)
                forward_return = terminal / entry - 1.0
                row.update(
                    {
                        "label_end_session": sessions[label_end_position].date().isoformat(),
                        "forward_return_21": forward_return,
                        "path_survival_label": int(
                            forward_return >= 0.0 and float(path_drawdown.min()) >= -0.08
                        ),
                        "max_open_path_drawdown": float(path_drawdown.min()),
                    }
                )
            else:
                row.update(
                    {
                        "label_end_session": None,
                        "forward_return_21": np.nan,
                        "path_survival_label": np.nan,
                        "max_open_path_drawdown": np.nan,
                    }
                )
            rows.append(row)
    dataset = pd.DataFrame(rows)
    if dataset.empty:
        raise ValueError("monthly feature dataset is empty")
    return dataset.sort_values(["execution_position", "symbol"]).reset_index(drop=True)


def _formula_placebo_evidence(
    dataset: pd.DataFrame,
    *,
    decision_sessions: set[str],
    seed: int = PLACEBO_SEED,
) -> dict[str, Any]:
    if not decision_sessions:
        raise ValueError("placebo evidence requires evaluated decision sessions")
    required = {
        "decision_session",
        "symbol",
        *FORMULA_FEATURES,
        *(f"placebo_{name}" for name in FORMULA_FEATURES),
    }
    missing = sorted(required - set(dataset.columns))
    if missing:
        raise ValueError("placebo evidence columns missing: " + ", ".join(missing))
    work = dataset[dataset["decision_session"].isin(decision_sessions)].copy()
    actual_sessions = set(map(str, work["decision_session"].unique()))
    if actual_sessions != decision_sessions:
        missing_sessions = sorted(decision_sessions - actual_sessions)
        raise ValueError(
            "placebo evidence decision sessions missing: " + ", ".join(missing_sessions)
        )

    valid_sessions = 0
    divergent_sessions = 0
    divergent_cells = 0
    formula_composite_nonconstant_sessions = 0
    original_records: list[dict[str, Any]] = []
    placebo_records: list[dict[str, Any]] = []
    failures: list[str] = []
    for decision_session, group in work.groupby("decision_session", sort=True):
        current = group.sort_values("symbol")
        symbols = list(map(str, current["symbol"]))
        if symbols != sorted(RANKABLE_SYMBOLS):
            failures.append(f"{decision_session}:symbol_coverage")
            continue
        original = current[list(FORMULA_FEATURES)].to_numpy(dtype=float)
        placebo = current[[f"placebo_{name}" for name in FORMULA_FEATURES]].to_numpy(dtype=float)
        if not np.isfinite(original).all() or not np.isfinite(placebo).all():
            failures.append(f"{decision_session}:nonfinite_formula_values")
            continue
        destinations = sorted(
            symbols,
            key=lambda symbol: hashlib.sha256(
                f"{seed}|{decision_session}|{symbol}".encode("ascii")
            ).hexdigest(),
        )
        destination_positions = {symbol: index for index, symbol in enumerate(symbols)}
        expected = np.empty_like(original)
        for source_position, destination in enumerate(destinations):
            expected[destination_positions[destination], :] = original[source_position, :]
        if not np.array_equal(placebo, expected):
            failures.append(f"{decision_session}:joint_permutation_mismatch")
            continue
        differences = placebo != original
        session_divergent_cells = int(differences.sum())
        divergent_cells += session_divergent_cells
        divergent_sessions += session_divergent_cells > 0
        formula_composite_nonconstant_sessions += int(
            pd.Series(original.mean(axis=1)).nunique(dropna=False) > 1
        )
        valid_sessions += 1
        for row_index, symbol in enumerate(symbols):
            original_records.append(
                {
                    "decision_session": str(decision_session),
                    "symbol": symbol,
                    "values": original[row_index].tolist(),
                }
            )
            placebo_records.append(
                {
                    "decision_session": str(decision_session),
                    "symbol": symbol,
                    "values": placebo[row_index].tolist(),
                }
            )

    expected_count = len(decision_sessions)
    joint_permutation_pass = valid_sessions == expected_count and not failures
    divergence_pass = divergent_sessions == expected_count and divergent_cells > 0
    formula_composite_pass = formula_composite_nonconstant_sessions == expected_count
    return {
        "seed": seed,
        "expected_decision_count": expected_count,
        "valid_joint_permutation_decision_count": valid_sessions,
        "divergent_decision_count": divergent_sessions,
        "divergent_cell_count": divergent_cells,
        "nonconstant_formula_composite_decision_count": formula_composite_nonconstant_sessions,
        "joint_permutation_pass": joint_permutation_pass,
        "formula_feature_divergence_pass": divergence_pass,
        "formula_composite_nonconstant_pass": formula_composite_pass,
        "original_formula_sha256": hashlib.sha256(
            _canonical_json_bytes(original_records)
        ).hexdigest(),
        "placebo_formula_sha256": hashlib.sha256(
            _canonical_json_bytes(placebo_records)
        ).hexdigest(),
        "failures": failures,
        "pass": joint_permutation_pass and divergence_pass and formula_composite_pass,
    }


def _target_difference_count(left: pd.DataFrame, right: pd.DataFrame) -> int:
    columns = sorted(set(left.columns) | set(right.columns))
    if not left.index.equals(right.index) or set(left.columns) != set(right.columns):
        raise ValueError("target difference comparison requires aligned sessions and symbols")
    left_values = left.reindex(columns=columns).to_numpy(dtype=float)
    right_values = right.reindex(columns=columns).to_numpy(dtype=float)
    return int(np.any(left_values != right_values, axis=1).sum())


def training_rows_for_prediction(
    dataset: pd.DataFrame,
    *,
    decision_position: int,
    train_start_session: str,
    feature_names: tuple[str, ...],
    label_name: str,
    maximum_window_sessions: int = TRAINING_WINDOW_SESSIONS,
    embargo_sessions: int = EMBARGO_SESSIONS,
) -> pd.DataFrame:
    cutoff = decision_position - embargo_sessions
    lower = decision_position - maximum_window_sessions
    work = dataset[
        (dataset["decision_position"] >= lower)
        & (dataset["decision_position"] < decision_position)
        & (dataset["decision_session"] >= train_start_session)
        & (dataset["label_end_position"] <= cutoff)
    ].copy()
    required = [*feature_names, label_name]
    work = work.replace([np.inf, -np.inf], np.nan).dropna(subset=required)
    return work.sort_values(["decision_position", "symbol"]).reset_index(drop=True)


def solve_post_trade_equity_ratio(
    pretrade_weights: np.ndarray,
    target_weights: np.ndarray,
    *,
    cost_bps: float,
    tolerance: float = 1e-14,
) -> tuple[float, float, float]:
    pretrade = np.asarray(pretrade_weights, dtype=float)
    target = np.asarray(target_weights, dtype=float)
    if pretrade.shape != target.shape or pretrade.ndim != 1:
        raise ValueError("pretrade and target weights must be aligned vectors")
    if (
        not np.isfinite(pretrade).all()
        or not np.isfinite(target).all()
        or (pretrade < -tolerance).any()
        or (target < -tolerance).any()
        or pretrade.sum() > 1.0 + tolerance
        or target.sum() > 1.0 + tolerance
    ):
        raise ValueError("self-financing weights must be finite, nonnegative, and sum to <=1")
    if not math.isfinite(cost_bps) or cost_bps < 0:
        raise ValueError("cost_bps must be finite and nonnegative")
    rate = cost_bps / 10_000.0
    if rate == 0.0:
        notional = float(np.abs(target - pretrade).sum())
        return 1.0, notional, 0.0

    def equation(ratio: float) -> float:
        return ratio + rate * float(np.abs(ratio * target - pretrade).sum()) - 1.0

    low = 0.0
    high = 1.0
    if equation(low) > tolerance or equation(high) < -tolerance:
        raise ValueError("self-financing cost equation has no bounded root")
    for _ in range(160):
        midpoint = (low + high) / 2.0
        if equation(midpoint) > 0.0:
            high = midpoint
        else:
            low = midpoint
    ratio = (low + high) / 2.0
    notional = float(np.abs(ratio * target - pretrade).sum())
    cost_fraction = rate * notional
    error = abs((1.0 - ratio) - cost_fraction)
    if error > tolerance:
        raise ValueError("self-financing cost reconciliation failed")
    return ratio, notional, error


def simulate_exact_target_portfolio(
    marks: pd.DataFrame,
    targets: pd.DataFrame,
    *,
    cost_bps: float,
    start: pd.Timestamp | str | None = None,
    end: pd.Timestamp | str | None = None,
    reserve_symbol: str = RESERVE_SYMBOL,
) -> ExactSimulationResult:
    prices = _strict_numeric_panel(marks, "simulation marks", positive=True)
    if list(targets.columns) != list(prices.columns):
        raise ValueError("simulation target symbols must exactly match mark symbols")
    target_values = targets.astype(float)
    if target_values.index.has_duplicates or not target_values.index.is_monotonic_increasing:
        raise ValueError("simulation targets must be unique and increasing")
    if (
        not np.isfinite(target_values.to_numpy()).all()
        or (target_values < -1e-12).any().any()
        or (target_values.sum(axis=1) > 1.0 + 1e-12).any()
    ):
        raise ValueError("simulation targets are invalid")

    selected_start = pd.Timestamp(start) if start is not None else prices.index.min()
    selected_end = pd.Timestamp(end) if end is not None else prices.index.max()
    window = prices.loc[(prices.index >= selected_start) & (prices.index <= selected_end)]
    if len(window) < 2:
        raise ValueError("simulation window requires at least two mark sessions")

    current = np.zeros(len(window.columns), dtype=float)
    cash_weight = 1.0
    equity = 1.0
    events: list[dict[str, Any]] = []
    daily_rows: list[dict[str, Any]] = []
    maximum_weight = 0.0
    first_session = window.index[0]
    prior = target_values.loc[target_values.index <= first_session]
    initial_target = prior.iloc[-1] if not prior.empty else None

    for position in range(len(window.index) - 1):
        session = window.index[position]
        next_session = window.index[position + 1]
        selected_target: pd.Series | None = None
        reason = ""
        if session in target_values.index:
            selected_target = target_values.loc[session]
            if isinstance(selected_target, pd.DataFrame):
                raise ValueError("duplicate target session")
            reason = "scheduled_rebalance"
        elif position == 0 and initial_target is not None:
            selected_target = initial_target
            reason = "independent_boundary_entry"

        pretrade_equity = equity
        cost_factor = 1.0
        if selected_target is not None:
            desired = selected_target.to_numpy(dtype=float)
            pretrade = current.copy()
            cost_factor, notional, error = solve_post_trade_equity_ratio(
                pretrade,
                desired,
                cost_bps=cost_bps,
            )
            equity *= cost_factor
            current = desired.copy()
            cash_weight = 1.0 - float(current.sum())
            maximum_weight = max(maximum_weight, float(current.max(initial=0.0)))
            if notional > 1e-15:
                events.append(
                    {
                        "session": session.date().isoformat(),
                        "reason": reason,
                        "terminal": False,
                        "pretrade_equity": pretrade_equity,
                        "pretrade_asset_weights": _weight_mapping(window.columns, pretrade),
                        "pretrade_cash_weight": 1.0 - float(pretrade.sum()),
                        "target_asset_weights": _weight_mapping(window.columns, desired),
                        "posttrade_cash_weight": cash_weight,
                        "posttrade_equity_ratio": cost_factor,
                        "full_L1_executed_notional_fraction": notional,
                        "cost_fraction_of_pretrade_equity": 1.0 - cost_factor,
                        "cost_reconciliation_error": error,
                    }
                )
        interval_maximum_weight = float(current.max(initial=0.0))

        asset_returns = (
            window.iloc[position + 1].to_numpy(dtype=float)
            / window.iloc[position].to_numpy(dtype=float)
            - 1.0
        )
        if not np.isfinite(asset_returns).all() or (asset_returns <= -1.0).any():
            raise ValueError("simulation produced invalid asset returns")
        gross_factor = cash_weight + float(np.dot(current, 1.0 + asset_returns))
        if not math.isfinite(gross_factor) or gross_factor <= 0.0:
            raise ValueError("simulation gross factor is invalid")
        net_factor = cost_factor * gross_factor
        equity = pretrade_equity * net_factor
        current = current * (1.0 + asset_returns) / gross_factor
        cash_weight = cash_weight / gross_factor
        if (
            not np.isfinite(current).all()
            or (current < -1e-12).any()
            or abs(float(current.sum()) + cash_weight - 1.0) > 1e-12
        ):
            raise ValueError("simulation drifted weights are invalid")
        maximum_weight = max(maximum_weight, float(current.max(initial=0.0)))
        interval_maximum_weight = max(
            interval_maximum_weight,
            float(current.max(initial=0.0)),
        )
        daily_rows.append(
            {
                "interval_start": session.date().isoformat(),
                "interval_end": next_session.date().isoformat(),
                "gross_factor_after_rebalance": gross_factor,
                "cost_factor": cost_factor,
                "net_factor": net_factor,
                "net_return": net_factor - 1.0,
                "equity": equity,
                "risk_asset_exposure": float(
                    sum(
                        weight
                        for symbol, weight in zip(window.columns, current, strict=True)
                        if symbol != reserve_symbol
                    )
                ),
                "maximum_asset_weight_observed": interval_maximum_weight,
            }
        )

    terminal_pretrade = current.copy()
    terminal_ratio, terminal_notional, terminal_error = solve_post_trade_equity_ratio(
        terminal_pretrade,
        np.zeros_like(terminal_pretrade),
        cost_bps=cost_bps,
    )
    if terminal_notional > 1e-15:
        pretrade_equity = equity
        equity *= terminal_ratio
        daily_rows[-1]["cost_factor"] *= terminal_ratio
        daily_rows[-1]["net_factor"] *= terminal_ratio
        daily_rows[-1]["net_return"] = daily_rows[-1]["net_factor"] - 1.0
        daily_rows[-1]["equity"] = equity
        events.append(
            {
                "session": window.index[-1].date().isoformat(),
                "reason": "terminal_liquidation",
                "terminal": True,
                "pretrade_equity": pretrade_equity,
                "pretrade_asset_weights": _weight_mapping(window.columns, terminal_pretrade),
                "pretrade_cash_weight": 1.0 - float(terminal_pretrade.sum()),
                "target_asset_weights": _weight_mapping(
                    window.columns, np.zeros_like(terminal_pretrade)
                ),
                "posttrade_cash_weight": 1.0,
                "posttrade_equity_ratio": terminal_ratio,
                "full_L1_executed_notional_fraction": terminal_notional,
                "cost_fraction_of_pretrade_equity": 1.0 - terminal_ratio,
                "cost_reconciliation_error": terminal_error,
            }
        )

    daily = pd.DataFrame(daily_rows)
    metrics = performance_metrics(daily, events, maximum_weight=maximum_weight)
    return ExactSimulationResult(daily=daily, events=events, metrics=metrics)


def performance_metrics(
    daily: pd.DataFrame,
    events: list[dict[str, Any]],
    *,
    maximum_weight: float,
) -> dict[str, Any]:
    returns = pd.to_numeric(daily["net_return"], errors="raise").astype(float)
    equity = pd.to_numeric(daily["equity"], errors="raise").astype(float)
    if (
        returns.empty
        or not np.isfinite(returns.to_numpy()).all()
        or not np.isfinite(equity.to_numpy()).all()
        or (equity <= 0.0).any()
    ):
        raise ValueError("performance path must be finite, positive, and nonempty")
    observed_maximum_weight = float(
        pd.to_numeric(daily["maximum_asset_weight_observed"], errors="raise").max()
    )
    if abs(observed_maximum_weight - maximum_weight) > 1e-12:
        raise ValueError("performance maximum weight differs from daily ledger")
    std = float(returns.std(ddof=1)) if len(returns) > 1 else 0.0
    sharpe = float(returns.mean() / std * math.sqrt(252.0)) if std > 0.0 else 0.0
    full_equity = pd.concat([pd.Series([1.0]), equity], ignore_index=True)
    drawdown = full_equity.div(full_equity.cummax()).sub(1.0)
    years = len(returns) / 252.0
    final_equity = float(equity.iloc[-1])
    full_l1 = float(sum(event["full_L1_executed_notional_fraction"] for event in events))
    return {
        "market_interval_count": len(returns),
        "total_return_pct": (final_equity - 1.0) * 100.0,
        "annualized_return_pct": (final_equity ** (1.0 / years) - 1.0) * 100.0,
        "annualized_volatility_pct": std * math.sqrt(252.0) * 100.0,
        "annualized_sharpe": sharpe,
        "max_drawdown_pct": float(drawdown.min() * 100.0),
        "positive_interval_pct": float((returns > 0.0).mean() * 100.0),
        "total_full_L1_executed_notional": full_l1,
        "annualized_full_L1_executed_notional_ratio": full_l1 / years,
        "legacy_half_turnover_report_only": 0.5 * full_l1,
        "maximum_drifted_weight": maximum_weight,
        "average_risk_asset_exposure": float(daily["risk_asset_exposure"].mean()),
        "nonzero_rebalance_count": sum(not event["terminal"] for event in events),
        "terminal_liquidation_count": sum(bool(event["terminal"]) for event in events),
        "maximum_cost_reconciliation_error": max(
            (float(event["cost_reconciliation_error"]) for event in events), default=0.0
        ),
    }


def build_cscv_partitions(
    sessions: pd.Index,
    *,
    block_count: int = 8,
    in_sample_block_count: int = 4,
) -> tuple[list[dict[str, Any]], list[np.ndarray]]:
    ordered = pd.Index(sessions)
    if len(ordered) < block_count or ordered.has_duplicates:
        raise ValueError("CSCV sessions must be unique and cover every block")
    blocks = [
        np.asarray(values, dtype=int)
        for values in np.array_split(np.arange(len(ordered)), block_count)
    ]
    if any(len(block) == 0 for block in blocks):
        raise ValueError("CSCV block cannot be empty")
    if max(map(len, blocks)) - min(map(len, blocks)) > 1:
        raise ValueError("CSCV block sizes differ by more than one")
    metadata = [
        {
            "block_id": f"B{index + 1:02d}",
            "position_start": int(block[0]),
            "position_end": int(block[-1]),
            "observation_count": len(block),
            "session_start": str(ordered[block[0]]),
            "session_end": str(ordered[block[-1]]),
        }
        for index, block in enumerate(blocks)
    ]
    partitions = [
        np.asarray(indices, dtype=int)
        for indices in combinations(range(block_count), in_sample_block_count)
    ]
    expected = math.comb(block_count, in_sample_block_count)
    if len(partitions) != expected:
        raise AssertionError("CSCV directional partition count mismatch")
    return metadata, partitions


def probability_backtest_overfitting(
    returns: pd.DataFrame,
    *,
    candidate_ids: tuple[str, ...] | list[str],
    block_count: int = 8,
    in_sample_block_count: int = 4,
) -> dict[str, Any]:
    candidates = list(candidate_ids)
    if len(candidates) < 2 or len(set(candidates)) != len(candidates):
        raise ValueError("PBO candidate IDs must be unique and contain at least two candidates")
    missing = sorted(set(candidates) - set(returns.columns))
    if missing:
        raise ValueError("PBO candidate returns missing: " + ", ".join(missing))
    values = returns[candidates].astype(float)
    if values.empty or values.index.has_duplicates or not np.isfinite(values.to_numpy()).all():
        raise ValueError("PBO returns must be finite, nonempty, and uniquely indexed")
    blocks, partitions = build_cscv_partitions(
        values.index,
        block_count=block_count,
        in_sample_block_count=in_sample_block_count,
    )
    all_blocks = set(range(len(blocks)))
    rows: list[dict[str, Any]] = []
    overfit_count = 0
    for partition_number, in_blocks_array in enumerate(partitions, start=1):
        in_blocks = tuple(map(int, in_blocks_array))
        out_blocks = tuple(sorted(all_blocks - set(in_blocks)))
        in_positions = np.sort(
            np.concatenate(
                [
                    np.arange(blocks[index]["position_start"], blocks[index]["position_end"] + 1)
                    for index in in_blocks
                ]
            )
        )
        out_positions = np.sort(
            np.concatenate(
                [
                    np.arange(blocks[index]["position_start"], blocks[index]["position_end"] + 1)
                    for index in out_blocks
                ]
            )
        )
        if set(in_positions) & set(out_positions) or len(in_positions) + len(out_positions) != len(
            values
        ):
            raise ValueError("PBO partition does not cover sessions exactly once")
        in_sharpes = {
            candidate: defined_annualized_sharpe(values.iloc[in_positions][candidate])
            for candidate in candidates
        }
        selected = sorted(candidates, key=lambda item: (-in_sharpes[item], item))[0]
        out_sharpes = {
            candidate: defined_annualized_sharpe(values.iloc[out_positions][candidate])
            for candidate in candidates
        }
        ordered = sorted(candidates, key=lambda item: (out_sharpes[item], item))
        rank = ordered.index(selected) + 1
        omega = (rank - 0.5) / len(candidates)
        logit = math.log(omega / (1.0 - omega))
        overfit = logit <= 0.0
        overfit_count += int(overfit)
        rows.append(
            {
                "partition": partition_number,
                "in_sample_blocks": [blocks[index]["block_id"] for index in in_blocks],
                "out_of_sample_blocks": [blocks[index]["block_id"] for index in out_blocks],
                "selected_candidate_id": selected,
                "in_sample_sharpes": in_sharpes,
                "out_of_sample_sharpes": out_sharpes,
                "selected_out_of_sample_rank": rank,
                "normalized_rank": omega,
                "rank_logit": logit,
                "overfit_event": overfit,
            }
        )
    expected_partition_count = math.comb(block_count, in_sample_block_count)
    if len(rows) != expected_partition_count:
        raise ValueError("R4 PBO directional partition count is incomplete")
    return {
        "method": "combinatorially_symmetric_cross_validation",
        "candidate_ids": candidates,
        "block_count": block_count,
        "in_sample_block_count": in_sample_block_count,
        "blocks": blocks,
        "partition_count": len(rows),
        "valid_partition_count": len(rows),
        "overfit_partition_count": overfit_count,
        "probability": overfit_count / len(rows),
        "partitions": rows,
    }


def defined_annualized_sharpe(values: pd.Series) -> float:
    returns = pd.to_numeric(values, errors="raise").astype(float)
    if len(returns) < 2 or not np.isfinite(returns.to_numpy()).all():
        raise ValueError("Sharpe requires at least two finite returns")
    if returns.nunique(dropna=False) < 2:
        raise ValueError("Sharpe is undefined for zero-variance returns")
    standard_deviation = float(returns.std(ddof=1))
    if standard_deviation <= 0.0:
        raise ValueError("Sharpe is undefined for zero-variance returns")
    return float(returns.mean() / standard_deviation * math.sqrt(252.0))


def deflated_sharpe_ratio(returns: pd.Series, *, trial_count: int) -> dict[str, Any]:
    values = pd.to_numeric(returns, errors="raise").astype(float)
    if trial_count < 2 or len(values) < 3 or not np.isfinite(values.to_numpy()).all():
        raise ValueError("DSR requires finite returns, at least three sessions, and N>=2")
    standard_deviation = float(values.std(ddof=1))
    if values.nunique(dropna=False) < 2 or standard_deviation <= 0.0:
        return {
            "trial_count": trial_count,
            "session_count": len(values),
            "probability": 0.0,
            "observed_annualized_sharpe": 0.0,
            "expected_max_annualized_sharpe_under_null": None,
        }
    observed_daily = float(values.mean() / standard_deviation)
    normal = NormalDist()
    gamma = 0.5772156649015329
    expected_max_standard = (1.0 - gamma) * normal.inv_cdf(1.0 - 1.0 / trial_count) + (
        gamma * normal.inv_cdf(1.0 - 1.0 / (trial_count * math.e))
    )
    expected_daily = expected_max_standard / math.sqrt(len(values) - 1)
    skew = float(values.skew())
    pearson_kurtosis = float(values.kurt()) + 3.0
    denominator = 1.0 - skew * observed_daily + ((pearson_kurtosis - 1.0) / 4.0) * observed_daily**2
    if not math.isfinite(denominator) or denominator <= 0.0:
        probability = 0.0
    else:
        statistic = (
            (observed_daily - expected_daily) * math.sqrt(len(values) - 1) / math.sqrt(denominator)
        )
        probability = normal.cdf(statistic)
    return {
        "estimator_id": "bailey_lopez_de_prado_expected_max_normal_v1",
        "trial_count": trial_count,
        "session_count": len(values),
        "probability": probability,
        "observed_annualized_sharpe": observed_daily * math.sqrt(252.0),
        "expected_max_annualized_sharpe_under_null": expected_daily * math.sqrt(252.0),
        "return_skew": skew,
        "return_pearson_kurtosis": pearson_kurtosis,
    }


def calibration_metrics(
    labels: pd.Series | np.ndarray,
    probabilities: pd.Series | np.ndarray,
    training_base_probabilities: pd.Series | np.ndarray,
    *,
    clip: float = 1e-6,
    slope_min: float = 0.7,
    slope_max: float = 1.3,
    minimum_observation_count: int = 3,
    minimum_class_count: int = 1,
) -> dict[str, Any]:
    y = np.asarray(labels, dtype=float)
    probability = np.asarray(probabilities, dtype=float)
    base = np.asarray(training_base_probabilities, dtype=float)
    if not (y.shape == probability.shape == base.shape) or y.ndim != 1 or len(y) < 3:
        raise ValueError("calibration inputs must be aligned one-dimensional vectors")
    if (
        not np.isfinite(y).all()
        or not np.isfinite(probability).all()
        or not np.isfinite(base).all()
        or not np.isin(y, [0.0, 1.0]).all()
        or (probability < 0.0).any()
        or (probability > 1.0).any()
        or (base < 0.0).any()
        or (base > 1.0).any()
    ):
        raise ValueError("calibration inputs are invalid")
    if not (0.0 < clip < 0.5):
        raise ValueError("calibration probability clip must be between zero and one half")
    if not (math.isfinite(slope_min) and math.isfinite(slope_max) and 0.0 < slope_min <= slope_max):
        raise ValueError("calibration slope bounds are invalid")
    if minimum_observation_count < 3 or minimum_class_count < 1:
        raise ValueError("calibration sample thresholds are invalid")
    model_brier = float(np.mean((probability - y) ** 2))
    base_brier = float(np.mean((base - y) ** 2))
    positive_count = int(np.sum(y == 1.0))
    negative_count = int(np.sum(y == 0.0))
    slope: float | None = None
    reason: str | None = None
    if len(y) < minimum_observation_count:
        reason = "insufficient_observations"
    elif min(positive_count, negative_count) < minimum_class_count:
        reason = "insufficient_class_count"
    elif len(np.unique(y)) < 2:
        reason = "single_class_labels"
    else:
        clipped = np.clip(probability, clip, 1.0 - clip)
        logits = np.log(clipped / (1.0 - clipped))
        if float(np.std(logits)) <= 1e-12:
            reason = "constant_probabilities"
        else:
            design = np.column_stack([np.ones(len(logits)), logits])

            def objective(coefficients: np.ndarray) -> float:
                linear = np.clip(design @ coefficients, -40.0, 40.0)
                return float(np.sum(np.logaddexp(0.0, linear) - y * linear))

            fitted = minimize(objective, np.asarray([0.0, 1.0]), method="BFGS")
            if not fitted.success or not np.isfinite(fitted.x).all():
                reason = "calibration_fit_failed"
            else:
                slope = float(fitted.x[1])
    passed = bool(
        slope is not None and model_brier < base_brier and slope_min <= slope <= slope_max
    )
    return {
        "observation_count": len(y),
        "positive_label_count": positive_count,
        "negative_label_count": negative_count,
        "minimum_observation_count": minimum_observation_count,
        "minimum_class_count": minimum_class_count,
        "model_brier_score": model_brier,
        "training_base_probability_brier_score": base_brier,
        "calibration_slope": slope,
        "calibration_failure_reason": reason,
        "joint_gate_pass": passed,
    }


def canonical_target_bytes(targets: pd.DataFrame) -> bytes:
    values = targets.sort_index().sort_index(axis=1).astype(float)
    rows = [
        {
            "execution_session": pd.Timestamp(session).date().isoformat(),
            "weights": {symbol: float(row[symbol]) for symbol in values.columns},
        }
        for session, row in values.iterrows()
    ]
    return _canonical_json_bytes(rows)


def canonical_target_hash(targets: pd.DataFrame) -> str:
    return hashlib.sha256(canonical_target_bytes(targets)).hexdigest()


def _strict_numeric_panel(frame: pd.DataFrame, label: str, *, positive: bool) -> pd.DataFrame:
    values = frame.astype(float).copy()
    if values.empty or values.index.has_duplicates or not values.index.is_monotonic_increasing:
        raise ValueError(f"{label} must be nonempty with unique increasing sessions")
    if not np.isfinite(values.to_numpy()).all():
        raise ValueError(f"{label} must be finite")
    if positive and (values <= 0.0).any().any():
        raise ValueError(f"{label} must be positive")
    return values


def _weight_mapping(columns: pd.Index, values: np.ndarray) -> dict[str, float]:
    return {str(symbol): float(value) for symbol, value in zip(columns, values, strict=True)}


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        _json_ready(value), sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("ascii")


def _json_ready(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_ready(item) for item in value]
    if isinstance(value, (np.bool_, bool)):
        return bool(value)
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        number = float(value)
        if not math.isfinite(number):
            raise ValueError("JSON evidence cannot contain nonfinite numbers")
        return number
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    return value


def build_candidate_targets_for_segment(
    dataset: pd.DataFrame,
    *,
    segment_id: str,
    execution_start: str,
    execution_end: str,
    train_start_session: str,
    columns: pd.Index,
    specs: dict[str, StrategySpec],
    provenance: dict[str, str] | None = None,
) -> tuple[
    dict[str, pd.DataFrame],
    list[dict[str, Any]],
    list[dict[str, Any]],
    pd.DataFrame,
]:
    provenance = provenance or {}
    points = (
        dataset[
            (dataset["execution_session"] >= execution_start)
            & (dataset["execution_session"] <= execution_end)
        ][
            [
                "decision_position",
                "decision_session",
                "execution_position",
                "execution_session",
            ]
        ]
        .drop_duplicates()
        .sort_values("execution_position")
    )
    if points.empty:
        raise ValueError(f"segment {segment_id} has no monthly prediction points")
    targets: dict[str, list[pd.Series]] = {candidate_id: [] for candidate_id in SPEC_PATHS}
    target_index: list[pd.Timestamp] = []
    target_records: list[dict[str, Any]] = []
    model_records: list[dict[str, Any]] = []
    calibration_rows: list[dict[str, Any]] = []
    p01_features = tuple(
        feature if feature not in FORMULA_FEATURES else f"placebo_{feature}"
        for feature in specs["R4P01"].model.features
    )

    for point in points.to_dict(orient="records"):
        decision_position = int(point["decision_position"])
        decision_session = str(point["decision_session"])
        execution_session = str(point["execution_session"])
        current = dataset[dataset["decision_position"] == decision_position].sort_values("symbol")
        if set(current["symbol"]) != set(RANKABLE_SYMBOLS):
            raise ValueError(f"rankable symbol coverage failed at {decision_session}")

        d01_symbols = _top_symbols(current, "raw_mom_252_skip21", TOP_N)
        d01 = _target_from_symbols(d01_symbols, columns)
        eligible_d02 = current[
            np.isfinite(current["raw_mom_126_skip21"])
            & np.isfinite(current["raw_trend_gap_252"])
            & (current["raw_trend_gap_252"] > 0.0)
        ]
        d02_symbols = _top_symbols(eligible_d02, "raw_mom_126_skip21", TOP_N)
        d02 = _target_from_symbols(d02_symbols, columns) if len(d02_symbols) == TOP_N else d01

        formula_values = current[list(FORMULA_FEATURES)].astype(float)
        formula_score = formula_values.mean(axis=1)
        if np.isfinite(formula_values.to_numpy()).all() and formula_score.nunique() > 1:
            l01_symbols = _top_symbols(
                current.assign(_formula_score=formula_score), "_formula_score"
            )
            l01 = _target_from_symbols(l01_symbols, columns)
            l01_fallback = None
        else:
            l01 = d01
            l01_fallback = "nonfinite_or_constant_formula_composite"

        m01_prediction, m01_record = _fit_predict_for_point(
            specs["R4M01"],
            dataset,
            current,
            decision_position=decision_position,
            train_start_session=train_start_session,
            feature_names=tuple(specs["R4M01"].model.features),
            label_name="forward_return_21",
            segment_id=segment_id,
            provenance=provenance,
        )
        model_records.append(m01_record)
        if m01_prediction is None:
            m01 = d01
            m01_symbols = d01_symbols
            m01_fallback = str(m01_record["failure_reason"])
            m01_scores = pd.Series(
                current["raw_mom_252_skip21"].to_numpy(dtype=float),
                index=current["symbol"],
            )
        else:
            m01_scores = pd.Series(m01_prediction, index=current["symbol"], dtype=float)
            m01_symbols = _top_symbols_from_series(m01_scores)
            m01 = _target_from_symbols(m01_symbols, columns)
            m01_fallback = None

        c01_prediction, c01_record = _fit_predict_for_point(
            specs["R4C01"],
            dataset,
            current,
            decision_position=decision_position,
            train_start_session=train_start_session,
            feature_names=tuple(specs["R4C01"].model.features),
            label_name="forward_return_21",
            segment_id=segment_id,
            provenance=provenance,
        )
        model_records.append(c01_record)
        if c01_prediction is None:
            c01 = m01
            c01_symbols = m01_symbols
            c01_fallback = str(c01_record["failure_reason"])
        else:
            c01_symbols = _top_symbols_from_series(
                pd.Series(c01_prediction, index=current["symbol"], dtype=float)
            )
            c01 = _target_from_symbols(c01_symbols, columns)
            c01_fallback = None

        p01_prediction, p01_record = _fit_predict_for_point(
            specs["R4P01"],
            dataset,
            current,
            decision_position=decision_position,
            train_start_session=train_start_session,
            feature_names=p01_features,
            label_name="forward_return_21",
            segment_id=segment_id,
            provenance=provenance,
        )
        model_records.append(p01_record)
        if p01_prediction is None:
            p01 = m01
            p01_symbols = m01_symbols
            p01_fallback = str(p01_record["failure_reason"])
        else:
            p01_symbols = _top_symbols_from_series(
                pd.Series(p01_prediction, index=current["symbol"], dtype=float)
            )
            p01 = _target_from_symbols(p01_symbols, columns)
            p01_fallback = None

        m02_prediction, m02_record = _fit_predict_for_point(
            specs["R4M02"],
            dataset,
            current,
            decision_position=decision_position,
            train_start_session=train_start_session,
            feature_names=tuple(specs["R4M02"].model.features),
            label_name="path_survival_label",
            segment_id=segment_id,
            provenance=provenance,
        )
        model_records.append(m02_record)
        if m02_prediction is None:
            m02 = m01
            m02_symbols = m01_symbols
            m02_fallback = str(m02_record["failure_reason"])
        else:
            survival = pd.Series(m02_prediction, index=current["symbol"], dtype=float)
            ranked = sorted(
                current["symbol"],
                key=lambda symbol: (-float(m01_scores[symbol]), str(symbol)),
            )
            threshold = specs["R4M02"].model.selection.threshold
            if threshold is None:
                raise ValueError("R4M02 survival threshold is missing")
            accepted = [symbol for symbol in ranked if float(survival[symbol]) >= float(threshold)][
                :TOP_N
            ]
            if len(accepted) < TOP_N:
                m02 = m01
                m02_symbols = m01_symbols
                m02_fallback = "fewer_than_three_survival_eligible_symbols"
            else:
                m02_symbols = accepted
                m02 = _target_from_symbols(m02_symbols, columns)
                m02_fallback = None
            base_probability = float(m02_record["training_label_mean"])
            for row, probability in zip(
                current.to_dict(orient="records"), m02_prediction, strict=True
            ):
                if row["label_end_session"] is not None and row["label_end_session"] <= (
                    execution_end
                ):
                    calibration_rows.append(
                        {
                            "segment_id": segment_id,
                            "decision_session": decision_session,
                            "execution_session": execution_session,
                            "symbol": row["symbol"],
                            "label": int(row["path_survival_label"]),
                            "probability": float(probability),
                            "training_base_probability": base_probability,
                        }
                    )

        candidate_rows = {
            "R4D01": (d01, d01_symbols, None),
            "R4D02": (d02, d02_symbols if len(d02_symbols) == TOP_N else d01_symbols, None),
            "R4M01": (m01, m01_symbols, m01_fallback),
            "R4M02": (m02, m02_symbols, m02_fallback),
            "R4L01": (l01, l01_symbols if l01_fallback is None else d01_symbols, l01_fallback),
            "R4C01": (c01, c01_symbols, c01_fallback),
            "R4F01": (m01.copy(), m01_symbols, "intentional_missing_modality_identity"),
            "R4P01": (p01, p01_symbols, p01_fallback),
        }
        target_index.append(pd.Timestamp(execution_session))
        for candidate_id, (target, selected_symbols, fallback_reason) in candidate_rows.items():
            targets[candidate_id].append(target)
            target_records.append(
                {
                    "schema_version": 1,
                    "iter_id": ITER_ID,
                    "segment_id": segment_id,
                    "candidate_id": candidate_id,
                    "decision_session": decision_session,
                    "execution_session": execution_session,
                    "selected_symbols": list(map(str, selected_symbols)),
                    "weights": {symbol: float(target[symbol]) for symbol in columns},
                    "target_sha256": hashlib.sha256(
                        _canonical_json_bytes(
                            {symbol: float(target[symbol]) for symbol in sorted(columns)}
                        )
                    ).hexdigest(),
                    "fallback_reason": fallback_reason,
                    "unexpected_model_fallback": bool(
                        fallback_reason
                        and fallback_reason
                        not in {
                            "intentional_missing_modality_identity",
                            "fewer_than_three_survival_eligible_symbols",
                        }
                    ),
                }
            )

    frames = {
        candidate_id: pd.DataFrame(rows, index=pd.DatetimeIndex(target_index), columns=columns)
        for candidate_id, rows in targets.items()
    }
    if canonical_target_bytes(frames["R4F01"]) != canonical_target_bytes(frames["R4M01"]):
        raise ValueError("R4F01 target identity with R4M01 failed")
    return frames, target_records, model_records, pd.DataFrame(calibration_rows)


def _fit_predict_for_point(
    spec: StrategySpec,
    dataset: pd.DataFrame,
    current: pd.DataFrame,
    *,
    decision_position: int,
    train_start_session: str,
    feature_names: tuple[str, ...],
    label_name: str,
    segment_id: str,
    provenance: dict[str, str],
) -> tuple[np.ndarray | None, dict[str, Any]]:
    if spec.model is None:
        raise ValueError(f"model config missing for {spec.name}")
    train = training_rows_for_prediction(
        dataset,
        decision_position=decision_position,
        train_start_session=train_start_session,
        feature_names=feature_names,
        label_name=label_name,
    )
    decision_session = str(current["decision_session"].iloc[0])
    base_record: dict[str, Any] = {
        "schema_version": 1,
        "iter_id": ITER_ID,
        "segment_id": segment_id,
        "candidate_id": str(spec.notes.model_dump(mode="json").get("candidate_id")),
        "strategy_name": spec.name,
        "spec_hash": strategy_content_hash(spec),
        "decision_session": decision_session,
        "model_kind": spec.model.kind,
        "feature_names": list(feature_names),
        "label_name": label_name,
        "training_row_count": len(train),
        "training_decision_start": (
            str(train["decision_session"].min()) if not train.empty else None
        ),
        "training_decision_end": str(train["decision_session"].max()) if not train.empty else None,
        "training_label_terminal_end": (
            str(train["label_end_session"].max()) if not train.empty else None
        ),
        "training_data_sha256": _frame_sha256(train, [*feature_names, label_name]),
        "prediction_feature_sha256": _frame_sha256(current, list(feature_names)),
        "model_config": spec.model.model_dump(mode="json"),
        "data_manifest_sha256": provenance.get("data_manifest_sha256"),
        "feature_contract_sha256": provenance.get("feature_contract_sha256"),
        "label_contract_sha256": provenance.get("label_contract_sha256"),
        "prompt_hash": provenance.get("prompt_hash"),
        "training_label_mean": (
            float(pd.to_numeric(train[label_name], errors="raise").mean())
            if not train.empty
            else None
        ),
    }
    minimum_rows = max(80, 2 * int(spec.model.hyperparameters.get("min_child_samples", 1)))
    failure_reason: str | None = None
    if len(train) < minimum_rows:
        failure_reason = "insufficient_training_rows"
    elif spec.model.kind == "lightgbm_classifier" and train[label_name].nunique() < 2:
        failure_reason = "single_class_training_labels"
    current_values = current[list(feature_names)].replace([np.inf, -np.inf], np.nan)
    if current_values.isna().any().any():
        failure_reason = "nonfinite_prediction_features"

    model = _make_estimator(spec)
    resolved_model_params = _json_ready(model.get_params(deep=True))
    prediction: np.ndarray | None = None
    fitted_model_sha256: str | None = None
    if failure_reason is None:
        try:
            model.fit(train[list(feature_names)], train[label_name])
            if spec.model.kind == "lightgbm_classifier":
                prediction = np.asarray(model.predict_proba(current_values)[:, 1], dtype=float)
            else:
                prediction = np.asarray(model.predict(current_values), dtype=float)
            if prediction.shape != (len(current),) or not np.isfinite(prediction).all():
                raise ValueError("model prediction is nonfinite or misaligned")
            booster = getattr(model, "booster_", None)
            if booster is None:
                raise ValueError("fitted LightGBM model is missing booster state")
            fitted_model_sha256 = hashlib.sha256(
                booster.model_to_string().encode("utf-8")
            ).hexdigest()
        except Exception as exc:  # Model failure is evidence and invokes the frozen fallback.
            failure_reason = f"model_fit_or_prediction_failed:{type(exc).__name__}:{exc}"
            prediction = None

    model_identity = {
        "spec_hash": base_record["spec_hash"],
        "decision_session": decision_session,
        "training_data_sha256": base_record["training_data_sha256"],
        "prediction_feature_sha256": base_record["prediction_feature_sha256"],
        "model_config": base_record["model_config"],
        "resolved_model_params": resolved_model_params,
    }
    record = {
        **base_record,
        "model_id": hashlib.sha256(_canonical_json_bytes(model_identity)).hexdigest(),
        "status": "fit_complete" if prediction is not None else "fallback_applied",
        "failure_reason": failure_reason,
        "resolved_model_class": type(model).__name__,
        "resolved_model_params": resolved_model_params,
        "fitted_model_sha256": fitted_model_sha256,
        "predictions": (
            [
                {"symbol": str(symbol), "value": float(value)}
                for symbol, value in zip(current["symbol"], prediction, strict=True)
            ]
            if prediction is not None
            else []
        ),
        "prediction_sha256": (
            hashlib.sha256(np.asarray(prediction, dtype="<f8").tobytes()).hexdigest()
            if prediction is not None
            else None
        ),
    }
    return prediction, record


def _make_estimator(spec: StrategySpec) -> Any:
    if spec.model is None:
        raise ValueError("model config is required")
    params = dict(spec.model.hyperparameters)
    params["random_state"] = int(spec.model.training.seed)
    params["deterministic"] = True
    params["force_col_wise"] = True
    if spec.model.kind == "lightgbm_regressor":
        from lightgbm import LGBMRegressor

        return LGBMRegressor(**params)
    if spec.model.kind == "lightgbm_classifier":
        from lightgbm import LGBMClassifier

        return LGBMClassifier(**params)
    raise ValueError(f"unsupported model kind: {spec.model.kind}")


def _top_symbols(frame: pd.DataFrame, score_column: str, count: int = TOP_N) -> list[str]:
    values = frame[["symbol", score_column]].replace([np.inf, -np.inf], np.nan).dropna()
    return [
        str(symbol)
        for symbol in sorted(
            values["symbol"],
            key=lambda item: (
                -float(values.loc[values["symbol"] == item, score_column].iloc[0]),
                str(item),
            ),
        )[:count]
    ]


def _top_symbols_from_series(scores: pd.Series, count: int = TOP_N) -> list[str]:
    if not np.isfinite(scores.to_numpy(dtype=float)).all():
        raise ValueError("ranking scores must be finite")
    return [
        str(symbol)
        for symbol in sorted(scores.index, key=lambda item: (-float(scores[item]), str(item)))[
            :count
        ]
    ]


def _target_from_symbols(symbols: list[str], columns: pd.Index) -> pd.Series:
    selected = list(dict.fromkeys(map(str, symbols)))[:TOP_N]
    target = pd.Series(0.0, index=columns, dtype=float)
    for symbol in selected:
        if symbol not in target.index or symbol == RESERVE_SYMBOL:
            raise ValueError(f"invalid selected risk symbol: {symbol}")
        target[symbol] = 1.0 / TOP_N
    target[RESERVE_SYMBOL] = 1.0 - float(target.sum())
    if abs(float(target.sum()) - 1.0) > 1e-12:
        raise ValueError("target weights do not sum to one")
    return target


def _frame_sha256(frame: pd.DataFrame, columns: list[str]) -> str:
    if frame.empty:
        return hashlib.sha256(b"").hexdigest()
    identity = [
        column
        for column in ["decision_position", "decision_session", "symbol", *columns]
        if column in frame.columns
    ]
    ordered = frame[identity].sort_values(
        [column for column in ["decision_position", "symbol"] if column in identity]
    )
    raw = ordered.to_csv(
        index=False,
        lineterminator="\n",
        float_format="%.17g",
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def load_r4_panel(root: Path, manifest_path: Path) -> PanelData:
    manifest = verify_alpaca_contract_snapshot(root, manifest_path)
    items = manifest.get("items")
    if not isinstance(items, list) or len(items) != 14:
        raise AlpacaDataError("R4 daily manifest must contain exactly 14 items")
    fields: dict[str, dict[str, pd.Series]] = {
        name: {} for name in ["open", "high", "low", "close", "volume"]
    }
    expected_sessions: list[str] | None = None
    for item in items:
        if (
            not isinstance(item, dict)
            or item.get("timeframe") != "daily"
            or item.get("feed") != "sip"
            or item.get("adjustment") != "all"
            or item.get("session_scope") != "regular"
        ):
            raise AlpacaDataError("R4 daily manifest item identity mismatch")
        symbol = str(item.get("symbol") or "")
        if symbol not in {*RANKABLE_SYMBOLS, RESERVE_SYMBOL}:
            raise AlpacaDataError(f"unexpected R4 daily symbol: {symbol}")
        path = manifest_path.parent / str(item.get("output_path") or "")
        raw = path.read_bytes()
        expected_sha256 = str(item.get("output_sha256") or "")
        if hashlib.sha256(raw).hexdigest() != expected_sha256:
            raise AlpacaDataError(f"R4 parsed CSV bytes differ from manifest for {symbol}")
        frame = pd.read_csv(io.BytesIO(raw))
        parsed = pd.to_datetime(frame["timestamp"], utc=True, errors="raise")
        sessions = pd.DatetimeIndex(
            parsed.dt.tz_convert(NEW_YORK).dt.tz_localize(None).dt.normalize()
        )
        if sessions.has_duplicates or not sessions.is_monotonic_increasing:
            raise AlpacaDataError(f"R4 daily sessions invalid for {symbol}")
        quality_sessions = item.get("quality", {}).get("complete_sessions")
        if not isinstance(quality_sessions, list):
            raise AlpacaDataError(f"R4 complete-session evidence missing for {symbol}")
        if expected_sessions is None:
            expected_sessions = list(map(str, quality_sessions))
        elif list(map(str, quality_sessions)) != expected_sessions:
            raise AlpacaDataError("R4 daily complete-session lists differ")
        for field in fields:
            values = pd.to_numeric(frame[field], errors="raise").to_numpy(dtype=float)
            fields[field][symbol] = pd.Series(values, index=sessions)

    panels = {field: pd.DataFrame(series).sort_index(axis=1) for field, series in fields.items()}
    expected_columns = sorted([*RANKABLE_SYMBOLS, RESERVE_SYMBOL])
    for field, panel in panels.items():
        if list(panel.columns) != expected_columns or panel.isna().any().any():
            raise AlpacaDataError(f"R4 {field} panel is incomplete")
        if not np.isfinite(panel.to_numpy()).all():
            raise AlpacaDataError(f"R4 {field} panel contains nonfinite values")
    for field in ["open", "high", "low", "close"]:
        if (panels[field] <= 0.0).any().any():
            raise AlpacaDataError(f"R4 {field} panel contains nonpositive values")
    if (panels["volume"] < 0.0).any().any():
        raise AlpacaDataError("R4 volume panel contains negative values")
    return PanelData(
        open=panels["open"],
        high=panels["high"],
        low=panels["low"],
        close=panels["close"],
        volume=panels["volume"],
        manifest=manifest,
    )


def _validate_r4_runtime_contracts(
    output: Path,
    *,
    root: Path | None = None,
) -> dict[str, Any]:
    contracts = {
        name: _load_json(output / filename)
        for name, filename in {
            "benchmark": "benchmark-contract.json",
            "candidate_manifest": "candidate-manifest.json",
            "cost": "cost-contract.json",
            "cumulative_trial": "cumulative-trial-contract.json",
            "feature": "feature-contract.json",
            "holdout": "holdout-contract.json",
            "label": "label-contract.json",
            "validation": "validation-contract.json",
        }.items()
    }
    failures: list[str] = []

    def require_equal(name: str, actual: Any, expected: Any) -> None:
        if isinstance(expected, bool):
            matched = actual is expected
        else:
            matched = actual == expected and not (
                isinstance(expected, int) and isinstance(actual, bool)
            )
        if not matched:
            failures.append(name)

    for name, contract in contracts.items():
        if contract.get("iter_id") != ITER_ID:
            failures.append(f"{name}.iter_id")

    manifest = contracts["candidate_manifest"]
    manifest_rows = manifest.get("candidates")
    manifest_ids = (
        [str(row.get("candidate_id") or "") for row in manifest_rows]
        if isinstance(manifest_rows, list) and all(isinstance(row, dict) for row in manifest_rows)
        else []
    )
    if int(manifest.get("candidate_count") or -1) != len(SPEC_PATHS):
        failures.append("candidate_manifest.candidate_count")
    if manifest_ids != list(SPEC_PATHS):
        failures.append("candidate_manifest.candidate_ids")

    trial = contracts["cumulative_trial"]
    trial_count = int(trial.get("dsr_trial_count") or -1)
    trial_lower_bound = int(trial.get("cumulative_trial_count_lower_bound") or -1)
    sensitivity_trial_counts = list(map(int, trial.get("dsr_sensitivity_trial_counts") or []))
    require_equal(
        "cumulative_trial.count_status",
        trial.get("count_status"),
        "known_lower_bound_with_preregistered_governance_stress",
    )
    require_equal("cumulative_trial.prior_lower_bound", trial.get("prior_lower_bound"), 8007)
    require_equal(
        "cumulative_trial.current_frozen_candidates",
        trial.get("current_frozen_candidates"),
        len(SPEC_PATHS),
    )
    require_equal("cumulative_trial.lower_bound", trial_lower_bound, 8015)
    require_equal("cumulative_trial.dsr_trial_count", trial_count, 100000)
    require_equal(
        "cumulative_trial.uncertainty_multiplier",
        trial.get("unrecorded_trial_uncertainty_multiplier"),
        12.5,
    )
    require_equal(
        "cumulative_trial.uncertainty_allowance",
        trial.get("unrecorded_trial_governance_allowance"),
        trial_count - trial_lower_bound,
    )
    require_equal(
        "cumulative_trial.sensitivity_trial_counts",
        sensitivity_trial_counts,
        [8015, 10000, 50000, 100000],
    )
    source_bindings = trial.get("source_bindings")
    if not isinstance(source_bindings, list) or len(source_bindings) != 3:
        failures.append("cumulative_trial.source_bindings")
    elif root is not None:
        base = root.resolve()
        for index, binding in enumerate(source_bindings):
            if not isinstance(binding, dict):
                failures.append(f"cumulative_trial.source_bindings.{index}")
                continue
            relative = Path(str(binding.get("path") or ""))
            candidate = base / relative
            try:
                resolved = candidate.resolve(strict=True)
                resolved.relative_to(base)
            except (FileNotFoundError, ValueError, OSError):
                failures.append(f"cumulative_trial.source_bindings.{index}.path")
                continue
            if candidate.is_symlink() or not resolved.is_file():
                failures.append(f"cumulative_trial.source_bindings.{index}.regular_file")
                continue
            if _sha256_file(resolved) != binding.get("sha256"):
                failures.append(f"cumulative_trial.source_bindings.{index}.sha256")

    validation = contracts["validation"]
    expected_folds = [
        {
            "fold_id": "F1",
            "train_start": "2018-02-01",
            "train_end": "2020-12-31",
            "test_start": "2021-01-04",
            "test_end": "2021-12-31",
        },
        {
            "fold_id": "F2",
            "train_start": "2018-02-01",
            "train_end": "2021-12-31",
            "test_start": "2022-01-03",
            "test_end": "2022-12-30",
        },
        {
            "fold_id": "F3",
            "train_start": "2018-02-01",
            "train_end": "2022-12-30",
            "test_start": "2023-01-03",
            "test_end": "2023-12-29",
        },
        {
            "fold_id": "F4",
            "train_start": "2018-02-01",
            "train_end": "2023-12-29",
            "test_start": "2024-01-02",
            "test_end": "2024-12-31",
        },
    ]
    require_equal("validation.folds", validation.get("folds"), expected_folds)
    pbo = validation.get("pbo")
    if not isinstance(pbo, dict):
        failures.append("validation.pbo")
        pbo = {}
    block_count = int(pbo.get("block_count") or -1)
    in_sample_block_count = int(pbo.get("in_sample_block_count") or -1)
    expected_partition_count = int(pbo.get("expected_partition_count") or -1)
    if not (1 <= in_sample_block_count < block_count):
        failures.append("validation.pbo.block_counts")
    elif math.comb(block_count, in_sample_block_count) != expected_partition_count:
        failures.append("validation.pbo.expected_partition_count")
    if int(pbo.get("minimum_valid_partition_count") or -1) != expected_partition_count:
        failures.append("validation.pbo.minimum_valid_partition_count")
    if list(pbo.get("block_ids") or []) != [f"B{index + 1:02d}" for index in range(block_count)]:
        failures.append("validation.pbo.block_ids")
    selection_ids = list(map(str, pbo.get("selection_candidate_ids") or []))
    diagnostic_ids = list(map(str, pbo.get("diagnostic_control_ids") or []))
    if selection_ids != list(map(str, trial.get("pbo_family_candidates") or [])):
        failures.append("pbo.selection_candidate_ids")
    if diagnostic_ids != list(map(str, trial.get("pbo_diagnostic_controls") or [])):
        failures.append("pbo.diagnostic_control_ids")
    if selection_ids + diagnostic_ids != list(SPEC_PATHS):
        failures.append("pbo.all_candidate_ids")
    pbo_expected = {
        "method": "combinatorially_symmetric_cross_validation",
        "return_source": "common_fold_test_daily_net_returns_primary_10bps",
        "source_start": "2021-01-04",
        "source_end": "2024-12-31",
        "return_interval_convention": (
            "open_to_open_net_return_indexed_by_interval_start_session_with_"
            "terminal_liquidation_cost_in_final_interval"
        ),
        "fold_boundary_accounting": (
            "each_outer_fold_starts_in_cash_at_test_start_open_and_liquidates_at_test_end_open"
        ),
        "expected_return_observation_count": 1001,
        "expected_block_observation_counts": [126, 125, 125, 125, 125, 125, 125, 125],
        "partition_enumeration": "all_directional_combinations",
        "evaluate_complementary_orientations": True,
        "selection_metric": "annualized_sharpe_zero_risk_free_sample_std",
        "selection_tie_break": "candidate_id_ascending",
        "shuffle": False,
    }
    for field_name, expected in pbo_expected.items():
        require_equal(f"validation.pbo.{field_name}", pbo.get(field_name), expected)

    dsr_contract = validation.get("dsr")
    if not isinstance(dsr_contract, dict):
        failures.append("validation.dsr")
        dsr_contract = {}
    dsr_expected = {
        "estimator_id": "bailey_lopez_de_prado_expected_max_normal_v1",
        "candidate_return_source": (
            "stitched_2021_2024_outer_fold_daily_net_returns_primary_10bps"
        ),
        "risk_free_return": 0.0,
        "sample_std_ddof": 1,
        "annualization_sessions": 252,
        "known_trial_count_lower_bound": trial_lower_bound,
        "promotion_governance_trial_count": trial_count,
        "sensitivity_trial_counts": sensitivity_trial_counts,
        "promotion_uses_largest_preregistered_trial_count": True,
        "expected_return_observation_count": 1001,
        "return_interval_convention": "same_unrounded_stitched_open_to_open_rows_as_PBO",
        "use_unrounded_returns": True,
        "nonfinite_or_nonpositive_denominator_action": "fail_closed",
    }
    for field_name, expected in dsr_expected.items():
        require_equal(f"validation.dsr.{field_name}", dsr_contract.get(field_name), expected)
    if dsr_contract.get("expected_return_observation_count") != pbo.get(
        "expected_return_observation_count"
    ):
        failures.append("validation.dsr_pbo_observation_count")

    model_rules = validation.get("model_rules")
    expected_model_rules = {
        "fit_within_each_fold_only": True,
        "outer_fold_walk_forward_retraining": (
            "at_each_month_end_decision_using_only_labels_available_before_that_decision"
        ),
        "maximum_training_window_sessions": TRAINING_WINDOW_SESSIONS,
        "training_label_cutoff": (
            "label_terminal_session_at_least_21_sessions_before_prediction_decision"
        ),
        "pbo_model_refit_allowed": False,
        "feature_selection_after_fold_results": False,
        "warm_start_from_prior_failed_models": False,
        "fixed_hyperparameters": True,
        "fixed_seeds": True,
        "paired_return_ranker_seed": 4101,
        "path_survival_seed": 4102,
        "R4M01_R4C01_R4P01_model_contract_identical_except_features": True,
    }
    if not isinstance(model_rules, dict):
        failures.append("validation.model_rules")
        model_rules = {}
    for field_name, expected in expected_model_rules.items():
        require_equal(f"validation.model_rules.{field_name}", model_rules.get(field_name), expected)

    role_gates = validation.get("role_gates")
    if not isinstance(role_gates, dict):
        failures.append("validation.role_gates")
        role_gates = {}
    for candidate_id in ("R4M01", "R4L01", "R4C01"):
        gate = role_gates.get(candidate_id)
        if not isinstance(gate, dict) or int(gate.get("minimum_winning_folds") or -1) < 1:
            failures.append(f"validation.role_gates.{candidate_id}.minimum_winning_folds")
    m02_gate = role_gates.get("R4M02")
    if (
        not isinstance(m02_gate, dict)
        or int(m02_gate.get("joint_brier_and_slope_passing_folds_min") or -1) < 1
    ):
        failures.append("validation.role_gates.R4M02.calibration_fold_min")
        m02_gate = {}
    expected_m02_gate = {
        "calibration_population": (
            "all_outer_fold_test_symbol_decisions_with_finite_labels_and_probabilities"
        ),
        "base_probability_source": (
            "corresponding_walk_forward_training_label_mean_for_each_prediction"
        ),
        "brier_comparison": "model_strictly_below_constant_training_base_probability",
        "calibration_slope_method": (
            "unpenalized_logistic_regression_of_label_on_clipped_prediction_logit_with_intercept"
        ),
        "probability_clip": 1e-6,
        "calibration_slope_min": 0.7,
        "calibration_slope_max": 1.3,
        "expected_observation_count_by_fold": {
            "F1": 143,
            "F2": 143,
            "F3": 143,
            "F4": 143,
        },
        "minimum_class_count_per_fold": 20,
        "joint_brier_and_slope_passing_folds_min": 3,
        "minimum_applied_gate_decisions": 6,
        "minimum_folds_with_target_difference_from_R4M01": 3,
        "aggregate_target_hash_must_differ_from_R4M01": True,
        "single_class_constant_probability_or_failed_fit_action": "fold_fail",
    }
    for field_name, expected in expected_m02_gate.items():
        require_equal(
            f"validation.role_gates.R4M02.{field_name}",
            m02_gate.get(field_name),
            expected,
        )

    expected_family_gates = {
        "positive_net_return_folds_min": 3,
        "stress_20bps_positive_folds_min": 3,
        "transfer_holdout_sharpe_min": 0.7,
        "transfer_holdout_max_drawdown_abs_pct_max": 20.0,
        "annualized_full_L1_executed_notional_ratio_max": 6.0,
        "annualized_BIL_excess_sharpe_min": 0.0,
        "cumulative_dsr_probability_min": 0.95,
        "pbo_max": 0.2,
        "pbo_min_partitions": 20,
    }
    family_gates = validation.get("family_gates")
    if not isinstance(family_gates, dict):
        failures.append("validation.family_gates")
        family_gates = {}
    for field_name, expected in expected_family_gates.items():
        require_equal(
            f"validation.family_gates.{field_name}", family_gates.get(field_name), expected
        )

    feature = contracts["feature"]
    target_contract = feature.get("target_construction")
    model_contract = feature.get("model_fitting")
    formula_contract = feature.get("formula_composition")
    if not isinstance(target_contract, dict) or int(target_contract.get("top_n") or -1) != TOP_N:
        failures.append("feature.target_construction.top_n")
    if not isinstance(model_contract, dict):
        failures.append("feature.model_fitting")
        model_contract = {}
    if int(model_contract.get("maximum_trailing_window_sessions") or -1) != (
        TRAINING_WINDOW_SESSIONS
    ):
        failures.append("feature.model_fitting.maximum_trailing_window_sessions")
    if int(model_contract.get("label_terminal_embargo_sessions") or -1) != EMBARGO_SESSIONS:
        failures.append("feature.model_fitting.label_terminal_embargo_sessions")
    if not isinstance(formula_contract, dict) or int(
        formula_contract.get("placebo_seed") or -1
    ) != (PLACEBO_SEED):
        failures.append("feature.formula_composition.placebo_seed")

    label = contracts["label"]
    for label_name in ("return_label", "path_survival_label"):
        row = label.get(label_name)
        if not isinstance(row, dict):
            failures.append(f"label.{label_name}")
            continue
        if int(row.get("horizon_sessions") or -1) != HORIZON_SESSIONS:
            failures.append(f"label.{label_name}.horizon_sessions")
        if int(row.get("embargo_sessions") or -1) != EMBARGO_SESSIONS:
            failures.append(f"label.{label_name}.embargo_sessions")

    cost = contracts["cost"]
    cost_views = {
        "gross_0bps": 0.0,
        "primary_10bps": float(cost.get("primary_cost_bps_per_executed_notional", math.nan)),
        "stress_20bps": float(cost.get("stress_cost_bps_per_executed_notional", math.nan)),
        "severe_report_only_35bps": float(
            cost.get("severe_report_only_cost_bps_per_executed_notional", math.nan)
        ),
    }
    expected_costs = {
        "primary_10bps": PRIMARY_COST_BPS,
        "stress_20bps": STRESS_COST_BPS,
        "severe_report_only_35bps": SEVERE_COST_BPS,
    }
    if any(
        not math.isfinite(cost_views[name]) or cost_views[name] != expected
        for name, expected in expected_costs.items()
    ):
        failures.append("cost.cost_views")
    accounting = cost.get("accounting")
    if (
        not isinstance(accounting, dict)
        or accounting.get("exact_self_financing_transaction_solver_required") is not True
    ):
        failures.append("cost.accounting.exact_solver")
    if cost.get("notional_basis") != "full_L1_executed_notional_including_cash_boundaries":
        failures.append("cost.notional_basis")
    require_equal(
        "cost.charged_events",
        cost.get("charged_events"),
        ["initial_entry", "every_rebalance_delta", "terminal_liquidation"],
    )
    expected_event_reason_codes = [
        "scheduled_rebalance",
        "independent_boundary_entry",
        "terminal_liquidation",
    ]
    require_equal(
        "cost.event_reason_codes",
        cost.get("event_reason_codes"),
        expected_event_reason_codes,
    )
    expected_spec_costs = {
        "commission_pct": 0.0,
        "slippage_bps": PRIMARY_COST_BPS,
        "impact_model": "linear",
        "impact_eta": 0.0,
        "impact_gamma": 0.0,
    }
    require_equal(
        "cost.strategy_spec_costs",
        cost.get("strategy_spec_costs"),
        expected_spec_costs,
    )
    if isinstance(accounting, dict):
        require_equal(
            "cost.accounting.tolerance",
            accounting.get("cost_reconciliation_tolerance"),
            1e-12,
        )
        require_equal(
            "cost.accounting.aggregate_fold_explanation",
            accounting.get("aggregate_and_fold_ledgers_must_explain_reset_differences"),
            True,
        )
        require_equal(
            "cost.accounting.reserve_costing", accounting.get("reserve_trades_are_costed"), True
        )
        require_equal(
            "cost.accounting.missing_open_price_action",
            accounting.get("missing_open_price_action"),
            "fail_closed",
        )

    holdout = contracts["holdout"]
    holdout_tca = holdout.get("matched_tca")
    cost_tca = cost.get("paper_tca")
    if not isinstance(holdout_tca, dict) or not isinstance(cost_tca, dict):
        failures.append("holdout.matched_tca")
        holdout_tca = {}
        cost_tca = {}
    if int(holdout_tca.get("minimum_unique_fills") or -1) != int(
        cost_tca.get("minimum_matched_fills") or -2
    ):
        failures.append("holdout.matched_tca.minimum_unique_fills")
    if int(holdout_tca.get("minimum_distinct_sessions") or -1) != int(
        cost_tca.get("minimum_distinct_sessions") or -2
    ):
        failures.append("holdout.matched_tca.minimum_distinct_sessions")
    if int(holdout.get("minimum_contiguous_bound_sessions") or -1) < 1:
        failures.append("holdout.minimum_contiguous_bound_sessions")
    if int(holdout.get("forward_count_start", -1)) != 0:
        failures.append("holdout.forward_count_start")
    if holdout.get("backfill_allowed") is not False:
        failures.append("holdout.backfill_allowed")

    benchmark = contracts["benchmark"]
    benchmark_rows = benchmark.get("benchmarks")
    benchmark_definitions = {
        str(row.get("benchmark_id") or ""): str(row.get("definition") or "")
        for row in benchmark_rows or []
        if isinstance(row, dict)
    }
    expected_benchmarks = {
        "same_symbol_buy_hold_SPY": "100_percent_SPY",
        "equal_weight_universe": "equal_weight_13_rankable_ETFs_monthly",
        "market_proxy": "100_percent_SPY",
        "sector_theme_proxy": "equal_weight_XLB_XLE_XLF_XLI_XLK_XLP_XLU_XLV_XLY_monthly",
        "balanced_proxy": "60_percent_SPY_40_percent_IEF_monthly",
        "cash_proxy": "100_percent_BIL",
        "ex_post_best_symbol_report_only": "best_single_symbol_after_results",
    }
    if benchmark_definitions != expected_benchmarks:
        failures.append("benchmark.definitions")
    if benchmark.get("same_cost_engine_required") is not True:
        failures.append("benchmark.same_cost_engine_required")
    benchmark_gates = benchmark.get("promotion_gates")
    expected_benchmark_gates = {
        "scope": "aggregate_common_window",
        "cost_view": "primary_10bps",
        "metric": "annualized_sharpe",
        "comparison": "candidate_greater_than_or_equal_to_each_required_benchmark",
        "required_benchmark_ids": [
            "market_proxy",
            "equal_weight_universe",
            "sector_theme_proxy",
            "balanced_proxy",
        ],
        "minimum_delta": 0.0,
        "same_symbol_buy_hold_SPY_is_identity_duplicate_of_market_proxy": True,
        "cash_proxy_raw_sharpe_is_report_only": True,
        "ex_post_best_symbol_is_report_only": True,
    }
    require_equal("benchmark.promotion_gates", benchmark_gates, expected_benchmark_gates)

    if failures:
        raise ValueError("R4 runtime contract mismatch: " + ", ".join(sorted(failures)))
    return {
        **contracts,
        "trial_count": trial_count,
        "trial_count_lower_bound": trial_lower_bound,
        "dsr_sensitivity_trial_counts": sensitivity_trial_counts,
        "cost_views": cost_views,
        "cost_reconciliation_tolerance": float(accounting["cost_reconciliation_tolerance"]),
        "cost_event_reason_codes": expected_event_reason_codes,
        "benchmark_gate_config": expected_benchmark_gates,
        "calibration_config": {
            "probability_clip": float(m02_gate["probability_clip"]),
            "slope_min": float(m02_gate["calibration_slope_min"]),
            "slope_max": float(m02_gate["calibration_slope_max"]),
            "expected_observation_count_by_fold": {
                str(key): int(value)
                for key, value in m02_gate["expected_observation_count_by_fold"].items()
            },
            "minimum_class_count_per_fold": int(m02_gate["minimum_class_count_per_fold"]),
        },
        "pbo_config": {
            "block_count": block_count,
            "in_sample_block_count": in_sample_block_count,
            "expected_partition_count": expected_partition_count,
            "minimum_valid_partition_count": int(pbo["minimum_valid_partition_count"]),
        },
        "forward_requirements": {
            "forward_epoch_utc": str(holdout["forward_epoch_utc"]),
            "minimum_contiguous_bound_sessions": int(holdout["minimum_contiguous_bound_sessions"]),
            "minimum_unique_matched_paper_fills": int(holdout_tca["minimum_unique_fills"]),
            "minimum_distinct_paper_sessions": int(holdout_tca["minimum_distinct_sessions"]),
            "backfill_allowed": bool(holdout["backfill_allowed"]),
            "paper_orders_authorized": False,
            "explicit_user_confirmation_required": True,
        },
    }


def freeze_multiasset_forward_multimodal_r4(root: Path) -> R4FreezeResult:
    base = root.resolve()
    output = base / ITERATION_DIR
    validation = validate_iteration_dossier(ITER_ID, base, stage="pre-backtest")
    if not validation.ok:
        raise ValueError("R4 cannot freeze a blocked dossier: " + ", ".join(validation.blocked))
    runtime_contracts = _validate_r4_runtime_contracts(output, root=base)
    lock_dir = output / "lock-set"
    lock_stage = output / ".r4-lock-stage"
    lock_marker = output / ".lock-set-publish.lock"
    preregistration_path = lock_dir / "preregistration-lock.json"
    runner_path = lock_dir / "runner-lock.json"
    lock_anchor_path = lock_dir / "lock-anchor.json"
    if lock_dir.exists() or lock_stage.exists() or lock_marker.exists():
        raise ValueError("R4 lock already exists; lock overwrite is prohibited")
    result_dir = output / "evaluation-run"
    attempt_path = output / "evaluation-attempt.json"
    publish_marker = output / ".evaluation-run-publish.lock"
    staged_attempts = sorted(path.name for path in output.glob(".r4-evaluation-stage-*"))
    if result_dir.exists() or attempt_path.exists() or publish_marker.exists() or staged_attempts:
        raise ValueError("R4 result or staged-attempt artifacts exist before lock")

    data_contract = _load_json(output / "data-contract.json")
    manifest_path = base / str(data_contract.get("snapshot_manifest_path") or "")
    parent_binding_path = base / str(data_contract.get("bound_parent_snapshot_path") or "")
    if _sha256_file(manifest_path) != data_contract.get("snapshot_manifest_sha256"):
        raise ValueError("R4 data manifest hash differs before lock")
    if _sha256_file(parent_binding_path) != data_contract.get("bound_parent_snapshot_sha256"):
        raise ValueError("R4 parent snapshot binding hash differs before lock")
    verify_alpaca_contract_snapshot(base, manifest_path)

    artifact_relatives = [
        f"{ITERATION_DIR.as_posix()}/benchmark-contract.json",
        f"{ITERATION_DIR.as_posix()}/candidate-manifest.json",
        f"{ITERATION_DIR.as_posix()}/cost-contract.json",
        f"{ITERATION_DIR.as_posix()}/cumulative-trial-contract.json",
        f"{ITERATION_DIR.as_posix()}/data-contract.json",
        f"{ITERATION_DIR.as_posix()}/data-feasibility.json",
        f"{ITERATION_DIR.as_posix()}/decision-record.md",
        f"{ITERATION_DIR.as_posix()}/evaluation-gates.json",
        f"{ITERATION_DIR.as_posix()}/external-brief.json",
        f"{ITERATION_DIR.as_posix()}/external-brief.md",
        f"{ITERATION_DIR.as_posix()}/feature-contract.json",
        f"{ITERATION_DIR.as_posix()}/holdout-contract.json",
        f"{ITERATION_DIR.as_posix()}/hypotheses.md",
        f"{ITERATION_DIR.as_posix()}/knowledge-assessment.json",
        f"{ITERATION_DIR.as_posix()}/knowledge-baseline.json",
        f"{ITERATION_DIR.as_posix()}/knowledge-context.json",
        f"{ITERATION_DIR.as_posix()}/knowledge-scout-queries.json",
        f"{ITERATION_DIR.as_posix()}/knowledge-scout.json",
        f"{ITERATION_DIR.as_posix()}/label-contract.json",
        f"{ITERATION_DIR.as_posix()}/modality-role-matrix.json",
        f"{ITERATION_DIR.as_posix()}/model-reuse-decision.json",
        f"{ITERATION_DIR.as_posix()}/search-space.json",
        f"{ITERATION_DIR.as_posix()}/search-space.md",
        "reports/harness/source_cards/us_multiasset_forward_multimodal_r4.jsonl",
        _relpath(parent_binding_path, base),
        _relpath(manifest_path, base),
    ]
    artifacts = [_file_binding(base / relative, base) for relative in artifact_relatives]
    loaded_specs = {
        candidate_id: load_strategy_spec(base / relative)
        for candidate_id, relative in SPEC_PATHS.items()
    }
    execution_contract = _validate_r4_spec_execution_contract(loaded_specs)
    specs = []
    for candidate_id, relative in SPEC_PATHS.items():
        path = base / relative
        spec = loaded_specs[candidate_id]
        specs.append(
            {
                "candidate_id": candidate_id,
                "path": relative.as_posix(),
                "file_sha256": _sha256_file(path),
                "semantic_sha256": strategy_content_hash(spec),
            }
        )
    locked_at = datetime.now(UTC).isoformat()
    preregistration = {
        "schema_version": 1,
        "iter_id": ITER_ID,
        "status": "behavior_contracts_locked_before_first_r4_price_calculation",
        "locked_at": locked_at,
        "candidate_count": 8,
        "cumulative_trial_count_lower_bound": runtime_contracts["trial_count_lower_bound"],
        "dsr_governance_trial_count": runtime_contracts["trial_count"],
        "first_evaluation_artifacts_absent": True,
        "historical_scope": "matched_transfer_evidence_not_pristine_promotion_holdout",
        "forward_count_at_lock": 0,
        "backfill_allowed": False,
        "artifacts": artifacts,
        "specs": specs,
        "spec_execution_contract": execution_contract,
        "prohibitions": [
            "no_candidate_or_parameter_changes_after_lock",
            "no_result_overwrite_or_rerun",
            "no_broker_client_or_order_authorization",
            "no_forward_backfill",
        ],
    }
    runner_relatives = [
        "open_composer/research/multiasset_forward_multimodal_r4.py",
        "tests/test_multiasset_forward_multimodal_r4.py",
        "open_composer/adapters/__init__.py",
        "open_composer/adapters/data/__init__.py",
        "open_composer/adapters/data/alpaca.py",
        "open_composer/adapters/data/alpaca_snapshot.py",
        "open_composer/adapters/data/provenance.py",
        "open_composer/adapters/data/sample.py",
        "open_composer/config.py",
        "open_composer/expressions.py",
        "open_composer/indicators.py",
        "open_composer/json_utils.py",
        "open_composer/market_calendar.py",
        "open_composer/models/execution_backend.py",
        "open_composer/models/__init__.py",
        "open_composer/models/signal.py",
        "open_composer/research/design_contract.py",
        "open_composer/research/__init__.py",
        "open_composer/research/iteration_dossier.py",
        "tests/test_iteration_dossier.py",
        "open_composer/models/strategy_version.py",
        "open_composer/models/strategy_spec.py",
        "open_composer/storage.py",
        "open_composer/strategy_versions.py",
        "open_composer/timeframes.py",
        "open_composer/yaml_utils.py",
        "schemas/alpaca_snapshot_contract.schema.json",
        "schemas/alpaca_snapshot_manifest.schema.json",
        "schemas/strategy_spec.schema.json",
        "open_composer/cli.py",
        "pyproject.toml",
        "uv.lock",
    ]
    runner = {
        "schema_version": 1,
        "iter_id": ITER_ID,
        "status": "implementation_locked_before_first_r4_price_calculation",
        "locked_at": locked_at,
        "files": [_file_binding(base / relative, base) for relative in runner_relatives],
        "runtime": _current_runtime(),
        "test_command": (
            "uv run pytest -q tests/test_multiasset_forward_multimodal_r4.py "
            "tests/test_iteration_dossier.py tests/test_spec_validation.py"
        ),
        "first_real_price_evaluation_completed": False,
    }
    lock_stage.mkdir(mode=0o700)
    _write_json_atomic(lock_stage / "preregistration-lock.json", preregistration)
    _write_json_atomic(lock_stage / "runner-lock.json", runner)
    anchor_subject = {
        "iter_id": ITER_ID,
        "preregistration_lock_sha256": _sha256_file(lock_stage / "preregistration-lock.json"),
        "runner_lock_sha256": _sha256_file(lock_stage / "runner-lock.json"),
    }
    lock_anchor_sha256 = hashlib.sha256(_canonical_json_bytes(anchor_subject)).hexdigest()
    lock_anchor = {
        "schema_version": 1,
        **anchor_subject,
        "operator_lock_anchor_sha256": lock_anchor_sha256,
        "operator_instruction": (
            "Record this SHA-256 outside the evaluation output and pass it explicitly to the "
            "one-shot evaluation command."
        ),
    }
    _write_json_atomic(lock_stage / "lock-anchor.json", lock_anchor)
    _publish_directory_exclusive(lock_stage, lock_dir)
    return R4FreezeResult(
        preregistration_lock_path=preregistration_path,
        runner_lock_path=runner_path,
        lock_anchor_path=lock_anchor_path,
        lock_anchor_sha256=lock_anchor_sha256,
        payload={
            "preregistration": preregistration,
            "runner": runner,
            "lock_anchor": lock_anchor,
        },
    )


def run_multiasset_forward_multimodal_r4(
    root: Path,
    *,
    expected_lock_anchor_sha256: str,
) -> R4EvaluationResult:
    base = root.resolve()
    output = base / ITERATION_DIR
    preflight = _preflight(
        base,
        expected_lock_anchor_sha256=expected_lock_anchor_sha256,
    )
    runtime_contracts = _validate_r4_runtime_contracts(output, root=base)
    validation_contract = runtime_contracts["validation"]
    feature_contract = runtime_contracts["feature"]
    manifest = runtime_contracts["candidate_manifest"]
    specs = {
        candidate_id: load_strategy_spec(base / path) for candidate_id, path in SPEC_PATHS.items()
    }
    spec_execution_contract = _validate_r4_spec_execution_contract(specs)
    attempt_binding = _reserve_evaluation_attempt(base, preflight)
    preflight["evaluation_attempt"] = attempt_binding
    panel = load_r4_panel(base, base / preflight["data_manifest_path"])
    features = build_point_in_time_features(
        panel.close,
        panel.volume,
        formula_spec=specs[spec_execution_contract["formula_spec_candidate_id"]],
    )
    dataset = build_monthly_feature_dataset(
        panel,
        features,
        placebo_spec=specs[spec_execution_contract["placebo_spec_candidate_id"]],
        rebalance_schedule=spec_execution_contract["rebalance_schedule"],
    )
    if dataset["decision_session"].min() > "2018-02-01":
        raise ValueError("R4 feature history does not cover the frozen training start")

    provenance = {
        "data_manifest_sha256": preflight["data_manifest_sha256"],
        "feature_contract_sha256": _sha256_file(output / "feature-contract.json"),
        "label_contract_sha256": _sha256_file(output / "label-contract.json"),
        "prompt_hash": str(feature_contract["llm_formula_provenance"]["prompt_hash"]),
    }
    folds = validation_contract.get("folds")
    if not isinstance(folds, list) or len(folds) != 4:
        raise ValueError("R4 requires exactly four frozen outer folds")
    segments = [
        {
            "segment_id": str(fold["fold_id"]),
            "kind": "outer_fold",
            "train_start": str(fold["train_start"]),
            "start": str(fold["test_start"]),
            "end": str(fold["test_end"]),
        }
        for fold in folds
    ]
    transfer = validation_contract.get("transfer_holdout")
    if not isinstance(transfer, dict):
        raise ValueError("R4 transfer holdout contract is missing")
    segments.append(
        {
            "segment_id": "TRANSFER",
            "kind": "transfer_holdout",
            "train_start": str(folds[0]["train_start"]),
            "start": str(transfer["start"]),
            "end": str(transfer["end"]),
        }
    )

    segment_targets: dict[str, dict[str, pd.DataFrame]] = {}
    target_records: list[dict[str, Any]] = []
    model_records: list[dict[str, Any]] = []
    calibration_by_segment: dict[str, pd.DataFrame] = {}
    for segment in segments:
        frames, records, models, calibration = build_candidate_targets_for_segment(
            dataset,
            segment_id=segment["segment_id"],
            execution_start=segment["start"],
            execution_end=segment["end"],
            train_start_session=segment["train_start"],
            columns=panel.open.columns,
            specs=specs,
            provenance=provenance,
        )
        segment_targets[segment["segment_id"]] = frames
        target_records.extend(records)
        model_records.extend(models)
        calibration_by_segment[segment["segment_id"]] = calibration

    aggregate_targets = {
        candidate_id: pd.concat(
            [segment_targets[segment["segment_id"]][candidate_id] for segment in segments]
        ).sort_index()
        for candidate_id in SPEC_PATHS
    }
    if any(frame.index.has_duplicates for frame in aggregate_targets.values()):
        raise ValueError("R4 aggregate targets contain duplicate execution sessions")
    fallback_identity = canonical_target_bytes(aggregate_targets["R4F01"]) == (
        canonical_target_bytes(aggregate_targets["R4M01"])
    )
    if not fallback_identity:
        raise ValueError("R4 missing-modality target identity failed")
    evaluated_decision_sessions = {
        str(row["decision_session"]) for row in target_records if row["candidate_id"] == "R4P01"
    }
    formula_placebo_evidence = _formula_placebo_evidence(
        dataset,
        decision_sessions=evaluated_decision_sessions,
    )

    cost_views = runtime_contracts["cost_views"]
    aggregate_simulations: dict[str, dict[str, ExactSimulationResult]] = {}
    segment_simulations: dict[str, dict[str, dict[str, ExactSimulationResult]]] = {}
    event_records: list[dict[str, Any]] = []
    daily_return_records: list[dict[str, Any]] = []
    aggregate_start = str(segments[0]["start"])
    aggregate_end = str(segments[-1]["end"])
    for candidate_id in SPEC_PATHS:
        aggregate_simulations[candidate_id] = {}
        for view_name, cost_bps in cost_views.items():
            simulation = simulate_exact_target_portfolio(
                panel.open,
                aggregate_targets[candidate_id],
                cost_bps=cost_bps,
                start=aggregate_start,
                end=aggregate_end,
            )
            aggregate_simulations[candidate_id][view_name] = simulation
            event_records.extend(
                _scoped_events(
                    simulation.events,
                    candidate_id=candidate_id,
                    scope_id="AGGREGATE",
                    cost_view=view_name,
                )
            )
            daily_return_records.extend(
                _scoped_daily_returns(
                    simulation.daily,
                    candidate_id=candidate_id,
                    scope_id="AGGREGATE",
                    cost_view=view_name,
                )
            )
        segment_simulations[candidate_id] = {}
        for segment in segments:
            scope = segment["segment_id"]
            segment_simulations[candidate_id][scope] = {}
            for view_name, cost_bps in {
                name: cost_views[name] for name in ("primary_10bps", "stress_20bps")
            }.items():
                simulation = simulate_exact_target_portfolio(
                    panel.open,
                    segment_targets[scope][candidate_id],
                    cost_bps=cost_bps,
                    start=segment["start"],
                    end=segment["end"],
                )
                segment_simulations[candidate_id][scope][view_name] = simulation
                event_records.extend(
                    _scoped_events(
                        simulation.events,
                        candidate_id=candidate_id,
                        scope_id=scope,
                        cost_view=view_name,
                    )
                )
                daily_return_records.extend(
                    _scoped_daily_returns(
                        simulation.daily,
                        candidate_id=candidate_id,
                        scope_id=scope,
                        cost_view=view_name,
                    )
                )

    simulated_pbo_returns = _stitched_fold_returns(segment_simulations, folds)
    pbo_contract = validation_contract["pbo"]
    pbo_returns, _ = _pbo_returns_from_daily_ledger(
        daily_return_records,
        folds=folds,
        candidate_ids=list(SPEC_PATHS),
    )
    if (
        list(pbo_returns.index) != list(simulated_pbo_returns.index)
        or list(pbo_returns.columns) != list(simulated_pbo_returns.columns)
        or not np.array_equal(
            pbo_returns.to_numpy(dtype=float),
            simulated_pbo_returns.to_numpy(dtype=float),
        )
    ):
        raise ValueError("R4 daily-return ledger differs from simulated PBO returns")
    pbo_candidate_ids = list(map(str, pbo_contract["selection_candidate_ids"]))
    pbo_source_rows = [
        {
            "interval_start": str(interval_start),
            **{candidate_id: float(row[candidate_id]) for candidate_id in pbo_candidate_ids},
        }
        for interval_start, row in pbo_returns.iterrows()
    ]
    if len(pbo_source_rows) != int(pbo_contract["expected_return_observation_count"]):
        raise ValueError("R4 PBO return observation count differs from frozen contract")
    pbo_config = runtime_contracts["pbo_config"]
    pbo_blocks, _ = build_cscv_partitions(
        pbo_returns.index,
        block_count=pbo_config["block_count"],
        in_sample_block_count=pbo_config["in_sample_block_count"],
    )
    if [int(block["observation_count"]) for block in pbo_blocks] != list(
        map(int, pbo_contract["expected_block_observation_counts"])
    ):
        raise ValueError("R4 PBO block sizes differ from frozen contract")
    pbo = probability_backtest_overfitting(
        pbo_returns,
        candidate_ids=pbo_candidate_ids,
        block_count=pbo_config["block_count"],
        in_sample_block_count=pbo_config["in_sample_block_count"],
    )
    if pbo["partition_count"] != int(pbo_contract["expected_partition_count"]):
        raise ValueError("R4 PBO partition count differs from frozen contract")
    pbo["return_observation_count"] = len(pbo_source_rows)
    pbo["return_source_sha256"] = hashlib.sha256(_canonical_json_bytes(pbo_source_rows)).hexdigest()
    dsr: dict[str, Any] = {}
    for candidate_id in SPEC_PATHS:
        return_rows = [
            {"interval_start": str(index), "net_return": float(value)}
            for index, value in pbo_returns[candidate_id].items()
        ]
        sensitivity = {
            str(trial_count): deflated_sharpe_ratio(
                pbo_returns[candidate_id], trial_count=trial_count
            )
            for trial_count in runtime_contracts["dsr_sensitivity_trial_counts"]
        }
        result = dict(sensitivity[str(runtime_contracts["trial_count"])])
        result["known_trial_count_lower_bound"] = runtime_contracts["trial_count_lower_bound"]
        result["promotion_governance_trial_count"] = runtime_contracts["trial_count"]
        result["sensitivity"] = sensitivity
        result["return_source_sha256"] = hashlib.sha256(
            _canonical_json_bytes(return_rows)
        ).hexdigest()
        dsr[candidate_id] = result

    m02_role_contract = validation_contract["role_gates"]["R4M02"]
    calibration = _calibration_payload(
        calibration_by_segment,
        folds,
        required_joint_passing_fold_count=int(
            m02_role_contract["joint_brier_and_slope_passing_folds_min"]
        ),
        probability_clip=float(m02_role_contract["probability_clip"]),
        slope_min=float(m02_role_contract["calibration_slope_min"]),
        slope_max=float(m02_role_contract["calibration_slope_max"]),
        expected_observation_count_by_fold={
            str(key): int(value)
            for key, value in m02_role_contract["expected_observation_count_by_fold"].items()
        },
        minimum_class_count=int(m02_role_contract["minimum_class_count_per_fold"]),
    )
    benchmark_payload, benchmark_simulations, benchmark_targets = _benchmark_family_exact(
        panel.open,
        monthly_sessions=aggregate_targets["R4D01"].index,
        start=aggregate_start,
        end=aggregate_end,
        primary_cost_bps=cost_views["primary_10bps"],
        stress_cost_bps=cost_views["stress_20bps"],
    )
    for benchmark_id, views in benchmark_simulations.items():
        for view_name, simulation in views.items():
            event_records.extend(
                _scoped_events(
                    simulation.events,
                    candidate_id=f"BENCHMARK:{benchmark_id}",
                    scope_id="AGGREGATE",
                    cost_view=view_name,
                )
            )
            daily_return_records.extend(
                _scoped_daily_returns(
                    simulation.daily,
                    candidate_id=f"BENCHMARK:{benchmark_id}",
                    scope_id="AGGREGATE",
                    cost_view=view_name,
                )
            )
    daily_return_ledger_sha256 = _jsonl_sha256(daily_return_records)
    pbo["return_source"] = {
        "artifact_name": "daily_return_ledger",
        "ledger_sha256": daily_return_ledger_sha256,
        "scope_ids": [str(fold["fold_id"]) for fold in folds],
        "cost_view": "primary_10bps",
        "candidate_ids": pbo_candidate_ids,
        "canonical_form": "interval_start_then_candidate_id_sorted_canonical_json",
        "row_count": len(pbo_source_rows),
        "sha256": pbo["return_source_sha256"],
    }
    for candidate_id, result in dsr.items():
        result["return_source"] = {
            "artifact_name": "daily_return_ledger",
            "ledger_sha256": daily_return_ledger_sha256,
            "scope_ids": [str(fold["fold_id"]) for fold in folds],
            "cost_view": "primary_10bps",
            "candidate_id": candidate_id,
            "canonical_form": "interval_start_and_net_return_canonical_json",
            "row_count": int(result["session_count"]),
            "sha256": result["return_source_sha256"],
        }
    benchmark_rows = _benchmark_ledger_rows(
        benchmark_payload,
        benchmark_simulations,
        benchmark_targets,
        promotion_gate_ids=set(
            runtime_contracts["benchmark_gate_config"]["required_benchmark_ids"]
        ),
    )
    bil_primary = benchmark_simulations["cash_proxy"]["primary_10bps"]
    candidates: dict[str, Any] = {}
    for candidate_id, spec in specs.items():
        aggregate_cost_metrics = {
            view: dict(simulation.metrics)
            for view, simulation in aggregate_simulations[candidate_id].items()
        }
        candidate_returns = aggregate_simulations[candidate_id]["primary_10bps"].daily["net_return"]
        bil_returns = bil_primary.daily["net_return"]
        try:
            bil_excess_sharpe = defined_annualized_sharpe(candidate_returns - bil_returns)
        except ValueError:
            bil_excess_sharpe = 0.0
        aggregate_cost_metrics["primary_10bps"]["annualized_BIL_excess_sharpe"] = bil_excess_sharpe
        candidate_folds = {
            str(fold["fold_id"]): {
                view: simulation.metrics
                for view, simulation in segment_simulations[candidate_id][
                    str(fold["fold_id"])
                ].items()
            }
            for fold in folds
        }
        transfer_metrics = {
            view: simulation.metrics
            for view, simulation in segment_simulations[candidate_id]["TRANSFER"].items()
        }
        candidates[candidate_id] = {
            "strategy_name": spec.name,
            "spec_path": SPEC_PATHS[candidate_id].as_posix(),
            "spec_hash": strategy_content_hash(spec),
            "promotion_eligible": bool(
                next(
                    row["promotion_eligible"]
                    for row in manifest["candidates"]
                    if row["candidate_id"] == candidate_id
                )
            ),
            "aggregate_cost_views": aggregate_cost_metrics,
            "folds": candidate_folds,
            "transfer_holdout": transfer_metrics,
            "dsr": dsr[candidate_id],
            "target_count": len(aggregate_targets[candidate_id]),
            "target_sha256": canonical_target_hash(aggregate_targets[candidate_id]),
            "unexpected_model_fallback_count": sum(
                bool(row["unexpected_model_fallback"])
                for row in target_records
                if row["candidate_id"] == candidate_id
            ),
        }

    role_gates = _evaluate_role_gates(
        candidates,
        calibration=calibration,
        aggregate_targets=aggregate_targets,
        segment_targets=segment_targets,
        formula_placebo_evidence=formula_placebo_evidence,
        validation_contract=validation_contract,
    )
    benchmark_gates = _evaluate_benchmark_gates(
        candidates,
        benchmark_payload=benchmark_payload,
        benchmark_contract=runtime_contracts["benchmark"],
    )
    candidate_gates = _evaluate_candidate_gates(
        candidates,
        validation_contract,
        benchmark_gates=benchmark_gates,
    )
    for candidate_id in candidates:
        candidates[candidate_id]["role_gate"] = role_gates[candidate_id]
        candidates[candidate_id]["benchmark_gate"] = benchmark_gates[candidate_id]
        candidates[candidate_id]["family_gates"] = candidate_gates[candidate_id]
        candidates[candidate_id]["historical_research_gate_pass"] = bool(
            candidate_gates[candidate_id]["pass"] and role_gates[candidate_id]["pass"]
        )

    cost_reconciliation = _cost_reconciliation(
        aggregate_simulations,
        segment_simulations,
        segments,
        benchmarks=benchmark_simulations,
        tolerance=runtime_contracts["cost_reconciliation_tolerance"],
        expected_event_reason_codes=set(runtime_contracts["cost_event_reason_codes"]),
    )
    workflow_pass = bool(
        fallback_identity
        and cost_reconciliation["pass"]
        and benchmark_payload["complete"]
        and benchmark_payload["same_cost_engine"]
        and all(
            not frame.isna().any().any()
            and np.isfinite(frame.to_numpy()).all()
            and np.allclose(frame.sum(axis=1).to_numpy(), 1.0, atol=1e-12, rtol=0.0)
            for frame in aggregate_targets.values()
        )
        and all(
            (
                frame.drop(columns=[RESERVE_SYMBOL])
                <= float(specs[candidate_id].portfolio.max_symbol_weight) + 1e-12
            )
            .all()
            .all()
            for candidate_id, frame in aggregate_targets.items()
        )
    )
    pbo_pass = bool(
        pbo["partition_count"] == pbo_config["expected_partition_count"]
        and pbo["valid_partition_count"] >= pbo_config["minimum_valid_partition_count"]
        and pbo["valid_partition_count"]
        >= int(validation_contract["family_gates"]["pbo_min_partitions"])
        and pbo["probability"] <= float(validation_contract["family_gates"]["pbo_max"])
    )
    selected = [
        candidate_id
        for candidate_id, payload in candidates.items()
        if payload["promotion_eligible"] and payload["historical_research_gate_pass"] and pbo_pass
    ]
    research_pass = bool(workflow_pass and selected)
    llm_contribution_pass = bool(
        workflow_pass
        and role_gates["R4C01"]["pass"]
        and candidate_gates["R4C01"]["pass"]
        and pbo_pass
    )
    paper_ready_pass = False
    decision = "continue_to_locked_forward_observation" if research_pass else "stop_r4"

    trial_rows = [
        {
            "schema_version": 1,
            "iter_id": ITER_ID,
            "candidate_id": candidate_id,
            "spec_hash": payload["spec_hash"],
            "promotion_eligible": payload["promotion_eligible"],
            "aggregate_cost_views": payload["aggregate_cost_views"],
            "folds": payload["folds"],
            "transfer_holdout": payload["transfer_holdout"],
            "dsr": payload["dsr"],
            "role_gate": payload["role_gate"],
            "family_gates": payload["family_gates"],
            "historical_research_gate_pass": payload["historical_research_gate_pass"],
        }
        for candidate_id, payload in candidates.items()
    ]
    feature_rows = _dataframe_records(dataset)
    prediction_rows = [
        {
            "schema_version": 1,
            "iter_id": ITER_ID,
            "segment_id": record["segment_id"],
            "candidate_id": record["candidate_id"],
            "model_id": record["model_id"],
            "decision_session": record["decision_session"],
            "symbol": prediction["symbol"],
            "value": prediction["value"],
            "prediction_sha256": record["prediction_sha256"],
        }
        for record in model_records
        for prediction in record["predictions"]
    ]
    prediction_reconciliation = _reconcile_model_prediction_evidence(
        model_records,
        prediction_rows,
    )
    ledger_inventory = {
        name: {"row_count": len(rows), "sha256": _jsonl_sha256(rows)}
        for name, rows in {
            "feature_ledger": feature_rows,
            "prediction_ledger": prediction_rows,
            "daily_return_ledger": daily_return_records,
            "target_ledger": target_records,
            "event_ledger": event_records,
            "benchmark_ledger": benchmark_rows,
            "model_ledger": model_records,
            "trial_ledger": trial_rows,
        }.items()
    }
    if ledger_inventory["daily_return_ledger"]["sha256"] != daily_return_ledger_sha256:
        raise ValueError("R4 daily-return ledger changed after statistical reconciliation")
    model_provenance = {
        "schema_version": 1,
        "iter_id": ITER_ID,
        "status": "historical_models_are_fold_local_evidence_not_reusable_deployed_state",
        "model_fit_count": len(model_records),
        "successful_fit_count": sum(row["status"] == "fit_complete" for row in model_records),
        "fallback_fit_count": sum(row["status"] != "fit_complete" for row in model_records),
        "data_manifest_sha256": provenance["data_manifest_sha256"],
        "feature_contract_sha256": provenance["feature_contract_sha256"],
        "label_contract_sha256": provenance["label_contract_sha256"],
        "prompt_hash": provenance["prompt_hash"],
        "warm_start_used": False,
        "serialized_estimator_promoted": False,
        "ledger_path": _relpath(output / "evaluation-run/model-ledger.jsonl", base),
        "ledger_sha256": ledger_inventory["model_ledger"]["sha256"],
        "prediction_ledger_path": _relpath(output / "evaluation-run/prediction-ledger.jsonl", base),
        "prediction_ledger_sha256": ledger_inventory["prediction_ledger"]["sha256"],
        "prediction_reconciliation": prediction_reconciliation,
    }
    result_dir = output / "evaluation-run"
    stage_dir = output / f".r4-evaluation-stage-{attempt_binding['sha256'][:16]}"
    if result_dir.exists() or stage_dir.exists():
        raise ValueError("R4 result or staged attempt already exists; overwrite is prohibited")
    stage_dir.mkdir(mode=0o700)
    names = {
        "feature_ledger": "feature-ledger.jsonl",
        "prediction_ledger": "prediction-ledger.jsonl",
        "daily_return_ledger": "daily-return-ledger.jsonl",
        "target_ledger": "target-ledger.jsonl",
        "event_ledger": "cost-event-ledger.jsonl",
        "benchmark_ledger": "benchmark-ledger.jsonl",
        "model_ledger": "model-ledger.jsonl",
        "trial_ledger": "trial-ledger.jsonl",
        "cost_reconciliation": "cost-reconciliation.json",
        "model_provenance": "model-provenance.json",
        "evaluation": "evaluation-report.json",
        "evaluation_markdown": "evaluation-report.md",
        "decision_record": "decision-record.md",
        "receipt": "evaluation-receipt.json",
    }
    paths = {name: stage_dir / filename for name, filename in names.items()}
    published_paths = {name: result_dir / filename for name, filename in names.items()}
    _write_jsonl_atomic(paths["feature_ledger"], feature_rows)
    _write_jsonl_atomic(paths["prediction_ledger"], prediction_rows)
    _write_jsonl_atomic(paths["daily_return_ledger"], daily_return_records)
    _write_jsonl_atomic(paths["target_ledger"], target_records)
    _write_jsonl_atomic(paths["event_ledger"], event_records)
    _write_jsonl_atomic(paths["benchmark_ledger"], benchmark_rows)
    _write_jsonl_atomic(paths["model_ledger"], model_records)
    _write_jsonl_atomic(paths["trial_ledger"], trial_rows)
    _write_json_atomic(paths["cost_reconciliation"], cost_reconciliation)
    _write_json_atomic(paths["model_provenance"], model_provenance)
    child_bindings = {
        name: _binding_for_destination(path, published_paths[name], base)
        for name, path in paths.items()
        if name
        in {
            "feature_ledger",
            "prediction_ledger",
            "daily_return_ledger",
            "target_ledger",
            "event_ledger",
            "benchmark_ledger",
            "model_ledger",
            "trial_ledger",
            "cost_reconciliation",
            "model_provenance",
        }
    }
    payload = {
        "schema_version": 1,
        "iter_id": ITER_ID,
        "report_type": "multiasset_forward_multimodal_r4_matched_transfer_evaluation",
        "decision": decision,
        "workflow_pass": workflow_pass,
        "research_pass": research_pass,
        "llm_contribution_pass": llm_contribution_pass,
        "paper_ready_pass": paper_ready_pass,
        "selected_candidate_ids": selected,
        "candidate_count": len(candidates),
        "cumulative_trial_count_lower_bound": runtime_contracts["trial_count_lower_bound"],
        "dsr_governance_trial_count": runtime_contracts["trial_count"],
        "common_window": {"start": aggregate_start, "end": aggregate_end},
        "historical_scope": "globally_exposed_transfer_evidence_not_pristine_promotion_holdout",
        "preflight": preflight,
        "child_artifacts": child_bindings,
        "candidates": candidates,
        "calibration": calibration,
        "family_pbo": pbo,
        "family_pbo_pass": pbo_pass,
        "spec_execution_contract": spec_execution_contract,
        "formula_placebo_evidence": formula_placebo_evidence,
        "benchmarks": benchmark_payload,
        "fallback_identity": {
            "R4F01_equals_R4M01": fallback_identity,
            "R4M01_target_sha256": canonical_target_hash(aggregate_targets["R4M01"]),
            "R4F01_target_sha256": canonical_target_hash(aggregate_targets["R4F01"]),
        },
        "cost_reconciliation": cost_reconciliation,
        "evidence_reconciliation": {
            "ledger_inventory": ledger_inventory,
            "prediction_reconciliation": prediction_reconciliation,
            "pbo_reproduced_from_daily_return_ledger": True,
            "dsr_reproduced_from_daily_return_ledger": True,
        },
        "forward_requirements": runtime_contracts["forward_requirements"],
    }
    staged_ledger_verification = _verify_staged_ledger_bundle(
        paths,
        payload,
        runtime_contracts,
        specs,
    )
    payload["evidence_reconciliation"]["staged_ledger_verification"] = staged_ledger_verification
    _write_json_atomic(paths["evaluation"], payload)
    _write_text_atomic(paths["evaluation_markdown"], _render_markdown(payload))
    _write_text_atomic(paths["decision_record"], _render_decision_record(payload))
    receipt_children = {
        name: _binding_for_destination(path, published_paths[name], base)
        for name, path in paths.items()
        if name != "receipt" and path.is_file()
    }
    receipt = {
        "schema_version": 3,
        "receipt_contract": "multiasset_forward_multimodal_r4_v3",
        "iter_id": ITER_ID,
        "evidence_publication_status": "complete",
        "decision": decision,
        "workflow_pass": workflow_pass,
        "research_pass": research_pass,
        "llm_contribution_pass": llm_contribution_pass,
        "paper_ready_pass": paper_ready_pass,
        "preregistration_lock": _file_binding(output / "lock-set/preregistration-lock.json", base),
        "runner_lock": _file_binding(output / "lock-set/runner-lock.json", base),
        "lock_anchor": _file_binding(output / "lock-set/lock-anchor.json", base),
        "evaluation_attempt": attempt_binding,
        "children": receipt_children,
        "prepublication_checks": {
            "prebacktest_dossier_status": "ok",
            "workflow_pass": workflow_pass,
            "fallback_identity": fallback_identity,
            "cost_reconciliation_pass": cost_reconciliation["pass"],
            "benchmark_family_complete": benchmark_payload["complete"],
            "staged_ledger_verification_pass": staged_ledger_verification["pass"],
        },
    }
    _write_json_atomic(paths["receipt"], receipt)
    _verify_staged_publication(paths, published_paths, payload, receipt, base)
    _reverify_locked_inputs(base, preflight)
    _publish_directory_exclusive(stage_dir, result_dir)
    final_validation = validate_iteration_dossier(ITER_ID, base, stage="final")
    if not final_validation.ok:
        raise ValueError("R4 final dossier blocked: " + ", ".join(final_validation.blocked))
    return R4EvaluationResult(
        evaluation_path=published_paths["evaluation"],
        evaluation_markdown_path=published_paths["evaluation_markdown"],
        receipt_path=published_paths["receipt"],
        payload=payload,
    )


def _reserve_evaluation_attempt(root: Path, preflight: dict[str, Any]) -> dict[str, Any]:
    path = root / ITERATION_DIR / "evaluation-attempt.json"
    payload = {
        "schema_version": 1,
        "iter_id": ITER_ID,
        "status": "reserved_before_first_price_parse",
        "reserved_at": datetime.now(UTC).isoformat(),
        "operator_lock_anchor_sha256": preflight["operator_lock_anchor_sha256"],
        "preregistration_lock_sha256": preflight["preregistration_lock_sha256"],
        "runner_lock_sha256": preflight["runner_lock_sha256"],
        "data_manifest_sha256": preflight["data_manifest_sha256"],
        "rerun_policy": "any_existing_attempt_blocks_all_future_evaluation_attempts",
    }
    content = _canonical_json_bytes(payload) + b"\n"
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags, 0o400)
    except FileExistsError as exc:
        raise ValueError("R4 evaluation attempt already exists; rerun refused") from exc
    try:
        view = memoryview(content)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise OSError("failed to write R4 evaluation attempt receipt")
            view = view[written:]
        os.fsync(descriptor)
        os.fchmod(descriptor, 0o400)
    finally:
        os.close(descriptor)
    _fsync_directory(path.parent)
    return _file_binding(path, root)


def _preflight(
    root: Path,
    *,
    expected_lock_anchor_sha256: str,
) -> dict[str, Any]:
    validation = validate_iteration_dossier(ITER_ID, root, stage="pre-backtest")
    if not validation.ok:
        raise ValueError("R4 pre-backtest dossier blocked: " + ", ".join(validation.blocked))
    output = root / ITERATION_DIR
    result_dir = output / "evaluation-run"
    attempt_path = output / "evaluation-attempt.json"
    publish_marker = output / ".evaluation-run-publish.lock"
    staged_attempts = sorted(output.glob(".r4-evaluation-stage-*"))
    if result_dir.exists() or attempt_path.exists() or publish_marker.exists() or staged_attempts:
        raise ValueError("R4 result or staged attempt already exists; reruns are prohibited")

    preregistration_path = output / "lock-set/preregistration-lock.json"
    preregistration = _load_json(preregistration_path)
    if preregistration.get("iter_id") != ITER_ID or preregistration.get("status") != (
        "behavior_contracts_locked_before_first_r4_price_calculation"
    ):
        raise ValueError("R4 preregistration lock identity is invalid")
    for binding in preregistration.get("artifacts", []):
        _verify_file_binding(root, binding)
    for binding in preregistration.get("specs", []):
        path = _verify_file_binding(
            root,
            {"path": binding.get("path"), "sha256": binding.get("file_sha256")},
        )
        spec = load_strategy_spec(path)
        if strategy_content_hash(spec) != binding.get("semantic_sha256"):
            raise ValueError(f"R4 semantic spec hash mismatch: {binding.get('path')}")

    runner_path = output / "lock-set/runner-lock.json"
    runner = _load_json(runner_path)
    if runner.get("iter_id") != ITER_ID or runner.get("status") != (
        "implementation_locked_before_first_r4_price_calculation"
    ):
        raise ValueError("R4 runner lock identity is invalid")
    for binding in runner.get("files", []):
        _verify_file_binding(root, binding)
    if runner.get("runtime") != _current_runtime():
        raise ValueError("R4 locked runtime package versions changed")

    lock_anchor_path = output / "lock-set/lock-anchor.json"
    lock_anchor = _load_json(lock_anchor_path)
    if len(expected_lock_anchor_sha256) != 64 or any(
        character not in "0123456789abcdef" for character in expected_lock_anchor_sha256
    ):
        raise ValueError("R4 expected lock anchor must be a lowercase SHA-256")
    anchor_subject = {
        "iter_id": ITER_ID,
        "preregistration_lock_sha256": _sha256_file(preregistration_path),
        "runner_lock_sha256": _sha256_file(runner_path),
    }
    computed_anchor = hashlib.sha256(_canonical_json_bytes(anchor_subject)).hexdigest()
    if lock_anchor.get("schema_version") != 1 or any(
        lock_anchor.get(key) != value for key, value in anchor_subject.items()
    ):
        raise ValueError("R4 lock anchor bindings are invalid")
    if lock_anchor.get("operator_lock_anchor_sha256") != computed_anchor:
        raise ValueError("R4 lock anchor payload is invalid")
    if expected_lock_anchor_sha256 != computed_anchor:
        raise ValueError("R4 operator-provided lock anchor does not match frozen bytes")

    data_contract_path = output / "data-contract.json"
    data_contract = _load_json(data_contract_path)
    manifest_path = root / str(data_contract.get("snapshot_manifest_path") or "")
    parent_binding_path = root / str(data_contract.get("bound_parent_snapshot_path") or "")
    if _sha256_file(manifest_path) != data_contract.get("snapshot_manifest_sha256"):
        raise ValueError("R4 data manifest hash differs from data contract")
    if _sha256_file(parent_binding_path) != data_contract.get("bound_parent_snapshot_sha256"):
        raise ValueError("R4 parent snapshot binding hash differs from data contract")
    return {
        "status": "ok",
        "dossier_checked_at": validation.checked_at.isoformat(),
        "preregistration_lock_path": _relpath(preregistration_path, root),
        "preregistration_lock_sha256": _sha256_file(preregistration_path),
        "runner_lock_path": _relpath(runner_path, root),
        "runner_lock_sha256": _sha256_file(runner_path),
        "lock_anchor_path": _relpath(lock_anchor_path, root),
        "lock_anchor_file_sha256": _sha256_file(lock_anchor_path),
        "operator_lock_anchor_sha256": computed_anchor,
        "candidate_manifest_path": _relpath(output / "candidate-manifest.json", root),
        "candidate_manifest_sha256": _sha256_file(output / "candidate-manifest.json"),
        "data_contract_path": _relpath(data_contract_path, root),
        "data_contract_sha256": _sha256_file(data_contract_path),
        "data_manifest_path": _relpath(manifest_path, root),
        "data_manifest_sha256": _sha256_file(manifest_path),
        "parent_snapshot_binding_path": _relpath(parent_binding_path, root),
        "parent_snapshot_binding_sha256": _sha256_file(parent_binding_path),
    }


def _stitched_fold_returns(
    simulations: dict[str, dict[str, dict[str, ExactSimulationResult]]],
    folds: list[dict[str, Any]],
) -> pd.DataFrame:
    columns: dict[str, pd.Series] = {}
    for candidate_id in SPEC_PATHS:
        rows = []
        for fold in folds:
            fold_id = str(fold["fold_id"])
            daily = simulations[candidate_id][fold_id]["primary_10bps"].daily
            rows.append(
                pd.Series(
                    daily["net_return"].to_numpy(dtype=float),
                    index=pd.Index(daily["interval_start"].astype(str), name="interval_start"),
                )
            )
        stitched = pd.concat(rows)
        if stitched.index.has_duplicates:
            raise ValueError(f"duplicate stitched fold return session for {candidate_id}")
        columns[candidate_id] = stitched
    frame = pd.DataFrame(columns)
    if frame.isna().any().any() or not np.isfinite(frame.to_numpy()).all():
        raise ValueError("stitched R4 fold return matrix is incomplete")
    return frame


def _calibration_payload(
    calibration_by_segment: dict[str, pd.DataFrame],
    folds: list[dict[str, Any]],
    *,
    required_joint_passing_fold_count: int,
    probability_clip: float,
    slope_min: float,
    slope_max: float,
    expected_observation_count_by_fold: dict[str, int],
    minimum_class_count: int,
) -> dict[str, Any]:
    if required_joint_passing_fold_count < 1 or required_joint_passing_fold_count > len(folds):
        raise ValueError("R4 calibration fold threshold is outside the frozen fold count")
    fold_ids = [str(fold["fold_id"]) for fold in folds]
    if set(expected_observation_count_by_fold) != set(fold_ids) or any(
        count < 3 for count in expected_observation_count_by_fold.values()
    ):
        raise ValueError("R4 calibration observation contract is invalid")
    if minimum_class_count < 1:
        raise ValueError("R4 calibration class-count contract is invalid")
    rows: dict[str, Any] = {}
    for fold in folds:
        fold_id = str(fold["fold_id"])
        frame = calibration_by_segment.get(fold_id, pd.DataFrame())
        if frame.empty:
            rows[fold_id] = {
                "observation_count": 0,
                "expected_observation_count": expected_observation_count_by_fold[fold_id],
                "observation_count_match": False,
                "positive_label_count": 0,
                "negative_label_count": 0,
                "minimum_observation_count": expected_observation_count_by_fold[fold_id],
                "minimum_class_count": minimum_class_count,
                "model_brier_score": None,
                "training_base_probability_brier_score": None,
                "calibration_slope": None,
                "calibration_failure_reason": "no_valid_fold_predictions",
                "joint_gate_pass": False,
            }
            continue
        rows[fold_id] = calibration_metrics(
            frame["label"],
            frame["probability"],
            frame["training_base_probability"],
            clip=probability_clip,
            slope_min=slope_min,
            slope_max=slope_max,
            minimum_observation_count=expected_observation_count_by_fold[fold_id],
            minimum_class_count=minimum_class_count,
        )
        rows[fold_id]["expected_observation_count"] = expected_observation_count_by_fold[fold_id]
        rows[fold_id]["observation_count_match"] = (
            rows[fold_id]["observation_count"] == expected_observation_count_by_fold[fold_id]
        )
        if not rows[fold_id]["observation_count_match"]:
            rows[fold_id]["joint_gate_pass"] = False
            rows[fold_id]["calibration_failure_reason"] = "observation_count_mismatch"
    passing = sum(bool(row["joint_gate_pass"]) for row in rows.values())
    all_observation_counts_match = all(
        bool(row["observation_count_match"]) for row in rows.values()
    )
    return {
        "candidate_id": "R4M02",
        "folds": rows,
        "joint_passing_fold_count": passing,
        "required_joint_passing_fold_count": required_joint_passing_fold_count,
        "probability_clip": probability_clip,
        "calibration_slope_min": slope_min,
        "calibration_slope_max": slope_max,
        "expected_observation_count_by_fold": expected_observation_count_by_fold,
        "minimum_class_count_per_fold": minimum_class_count,
        "all_observation_counts_match": all_observation_counts_match,
        "pass": bool(all_observation_counts_match and passing >= required_joint_passing_fold_count),
    }


def _benchmark_family_exact(
    opens: pd.DataFrame,
    *,
    monthly_sessions: pd.DatetimeIndex,
    start: str,
    end: str,
    primary_cost_bps: float,
    stress_cost_bps: float,
) -> tuple[
    dict[str, Any],
    dict[str, dict[str, ExactSimulationResult]],
    dict[str, pd.DataFrame],
]:
    columns = opens.columns
    sectors = ["XLB", "XLE", "XLF", "XLI", "XLK", "XLP", "XLU", "XLV", "XLY"]

    def targets(weights: dict[str, float], *, monthly: bool) -> pd.DataFrame:
        row = {symbol: float(weights.get(symbol, 0.0)) for symbol in columns}
        index = monthly_sessions if monthly else pd.DatetimeIndex([pd.Timestamp(start)])
        return pd.DataFrame([row] * len(index), index=index, columns=columns)

    definitions = {
        "same_symbol_buy_hold_SPY": targets({"SPY": 1.0}, monthly=False),
        "equal_weight_universe": targets(
            {symbol: 1.0 / len(RANKABLE_SYMBOLS) for symbol in RANKABLE_SYMBOLS},
            monthly=True,
        ),
        "market_proxy": targets({"SPY": 1.0}, monthly=False),
        "sector_theme_proxy": targets(
            {symbol: 1.0 / len(sectors) for symbol in sectors}, monthly=True
        ),
        "balanced_proxy": targets({"SPY": 0.6, "IEF": 0.4}, monthly=True),
        "cash_proxy": targets({RESERVE_SYMBOL: 1.0}, monthly=False),
    }
    spy_identity = canonical_target_bytes(definitions["same_symbol_buy_hold_SPY"]) == (
        canonical_target_bytes(definitions["market_proxy"])
    )
    if not spy_identity:
        raise ValueError("R4 SPY buy-and-hold and market proxy targets differ")
    simulations: dict[str, dict[str, ExactSimulationResult]] = {}
    payload: dict[str, Any] = {}
    for benchmark_id, target_frame in definitions.items():
        simulations[benchmark_id] = {}
        payload[benchmark_id] = {
            "promotion_gate": False,
            "required_evidence": True,
            "cost_views": {},
        }
        for view_name, bps in {
            "primary_10bps": primary_cost_bps,
            "stress_20bps": stress_cost_bps,
        }.items():
            simulation = simulate_exact_target_portfolio(
                opens, target_frame, cost_bps=bps, start=start, end=end
            )
            simulations[benchmark_id][view_name] = simulation
            payload[benchmark_id]["cost_views"][view_name] = simulation.metrics

    single_symbol: dict[str, ExactSimulationResult] = {}
    for symbol in columns:
        simulation = simulate_exact_target_portfolio(
            opens,
            targets({str(symbol): 1.0}, monthly=False),
            cost_bps=primary_cost_bps,
            start=start,
            end=end,
        )
        single_symbol[str(symbol)] = simulation
    best_symbol = sorted(
        single_symbol,
        key=lambda symbol: (
            -float(single_symbol[symbol].metrics["total_return_pct"]),
            symbol,
        ),
    )[0]
    best_target = targets({best_symbol: 1.0}, monthly=False)
    definitions["ex_post_best_symbol_report_only"] = best_target
    simulations["ex_post_best_symbol_report_only"] = {"primary_10bps": single_symbol[best_symbol]}
    payload["ex_post_best_symbol_report_only"] = {
        "promotion_gate": False,
        "selected_symbol": best_symbol,
        "cost_views": {"primary_10bps": single_symbol[best_symbol].metrics},
    }
    return (
        {
            "complete": spy_identity
            and set(payload)
            == {
                "same_symbol_buy_hold_SPY",
                "equal_weight_universe",
                "market_proxy",
                "sector_theme_proxy",
                "balanced_proxy",
                "cash_proxy",
                "ex_post_best_symbol_report_only",
            },
            "same_cost_engine": True,
            "identity_checks": {
                "same_symbol_buy_hold_SPY_equals_market_proxy": spy_identity,
                "same_symbol_buy_hold_SPY_target_sha256": canonical_target_hash(
                    definitions["same_symbol_buy_hold_SPY"]
                ),
                "market_proxy_target_sha256": canonical_target_hash(definitions["market_proxy"]),
            },
            "risk_free_treatment": "raw_and_BIL_excess_Sharpe_reported_separately",
            "results": payload,
        },
        simulations,
        definitions,
    )


def _evaluate_role_gates(
    candidates: dict[str, Any],
    *,
    calibration: dict[str, Any],
    aggregate_targets: dict[str, pd.DataFrame],
    segment_targets: dict[str, dict[str, pd.DataFrame]],
    formula_placebo_evidence: dict[str, Any],
    validation_contract: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    fold_ids = sorted(candidates["R4D01"]["folds"])
    role_contracts = validation_contract["role_gates"]

    def fold_sharpe(candidate_id: str, fold_id: str) -> float:
        return float(
            candidates[candidate_id]["folds"][fold_id]["primary_10bps"]["annualized_sharpe"]
        )

    def transfer_sharpe(candidate_id: str) -> float:
        return float(
            candidates[candidate_id]["transfer_holdout"]["primary_10bps"]["annualized_sharpe"]
        )

    m01_wins = [fold_sharpe("R4M01", fold) > fold_sharpe("R4D01", fold) for fold in fold_ids]
    l01_wins = [fold_sharpe("R4L01", fold) > fold_sharpe("R4D01", fold) for fold in fold_ids]
    c01_wins = [
        fold_sharpe("R4C01", fold) > max(fold_sharpe("R4M01", fold), fold_sharpe("R4P01", fold))
        for fold in fold_ids
    ]
    formula_ordering = bool(
        formula_placebo_evidence["formula_composite_nonconstant_pass"]
        and canonical_target_hash(aggregate_targets["R4L01"])
        != canonical_target_hash(aggregate_targets["R4D01"])
    )
    identity = canonical_target_bytes(aggregate_targets["R4F01"]) == canonical_target_bytes(
        aggregate_targets["R4M01"]
    )
    m02_difference_count = _target_difference_count(
        aggregate_targets["R4M02"], aggregate_targets["R4M01"]
    )
    m02_different_folds = [
        fold_id
        for fold_id in fold_ids
        if _target_difference_count(
            segment_targets[fold_id]["R4M02"],
            segment_targets[fold_id]["R4M01"],
        )
        > 0
    ]
    m02_hash_difference = canonical_target_hash(aggregate_targets["R4M02"]) != (
        canonical_target_hash(aggregate_targets["R4M01"])
    )
    m02_contract = role_contracts["R4M02"]
    m02_calibration_contract_match = bool(
        int(calibration.get("required_joint_passing_fold_count", -1))
        == int(m02_contract["joint_brier_and_slope_passing_folds_min"])
        and float(calibration.get("probability_clip", math.nan))
        == float(m02_contract["probability_clip"])
        and float(calibration.get("calibration_slope_min", math.nan))
        == float(m02_contract["calibration_slope_min"])
        and float(calibration.get("calibration_slope_max", math.nan))
        == float(m02_contract["calibration_slope_max"])
        and calibration.get("expected_observation_count_by_fold")
        == m02_contract["expected_observation_count_by_fold"]
        and int(calibration.get("minimum_class_count_per_fold", -1))
        == int(m02_contract["minimum_class_count_per_fold"])
        and calibration.get("all_observation_counts_match") is True
    )
    m02_behavior_pass = bool(
        m02_difference_count >= int(m02_contract["minimum_applied_gate_decisions"])
        and len(m02_different_folds)
        >= int(m02_contract["minimum_folds_with_target_difference_from_R4M01"])
        and (
            m02_hash_difference
            if bool(m02_contract["aggregate_target_hash_must_differ_from_R4M01"])
            else True
        )
    )
    p01_contract = role_contracts["R4P01"]
    p01_zero_fallbacks = int(candidates["R4P01"]["unexpected_model_fallback_count"]) == 0
    p01_valid = bool(
        (p01_zero_fallbacks if p01_contract["zero_unexpected_model_fallbacks_required"] else True)
        and (
            formula_placebo_evidence["joint_permutation_pass"]
            if p01_contract["joint_permutation_evidence_required"]
            else True
        )
        and (
            formula_placebo_evidence["formula_feature_divergence_pass"]
            if p01_contract["formula_feature_divergence_required"]
            else True
        )
    )
    m01_contract = role_contracts["R4M01"]
    l01_contract = role_contracts["R4L01"]
    c01_contract = role_contracts["R4C01"]
    m01_transfer_win = transfer_sharpe("R4M01") > transfer_sharpe("R4D01")
    l01_transfer_win = transfer_sharpe("R4L01") > transfer_sharpe("R4D01")
    c01_transfer_win = transfer_sharpe("R4C01") > max(
        transfer_sharpe("R4M01"), transfer_sharpe("R4P01")
    )
    c01_performance_pass = bool(
        sum(c01_wins) >= int(c01_contract["minimum_winning_folds"])
        and (
            c01_transfer_win
            if bool(c01_contract["transfer_holdout_win_against_both_required"])
            else True
        )
    )
    return {
        "R4D01": {"pass": True, "reason": "deterministic_baseline"},
        "R4D02": {"pass": True, "reason": "deterministic_control"},
        "R4M01": {
            "fold_wins": sum(m01_wins),
            "required_fold_wins": int(m01_contract["minimum_winning_folds"]),
            "transfer_win": m01_transfer_win,
            "pass": sum(m01_wins) >= int(m01_contract["minimum_winning_folds"])
            and (m01_transfer_win if m01_contract["transfer_holdout_win_required"] else True),
        },
        "R4M02": {
            "joint_calibration_passing_folds": calibration["joint_passing_fold_count"],
            "calibration_contract_match": m02_calibration_contract_match,
            "applied_gate_decision_count": m02_difference_count,
            "folds_with_target_difference_from_R4M01": m02_different_folds,
            "aggregate_target_hash_differs_from_R4M01": m02_hash_difference,
            "behavior_gate_pass": m02_behavior_pass,
            "pass": bool(
                m02_calibration_contract_match and calibration["pass"] and m02_behavior_pass
            ),
        },
        "R4L01": {
            "fold_wins": sum(l01_wins),
            "required_fold_wins": int(l01_contract["minimum_winning_folds"]),
            "transfer_win": l01_transfer_win,
            "formula_ordering_audit_pass": formula_ordering,
            "pass": sum(l01_wins) >= int(l01_contract["minimum_winning_folds"])
            and (l01_transfer_win if l01_contract["transfer_holdout_win_required"] else True)
            and formula_ordering,
        },
        "R4C01": {
            "same_fold_wins_against_M01_and_P01": sum(c01_wins),
            "required_same_fold_wins": int(c01_contract["minimum_winning_folds"]),
            "transfer_win_against_both": c01_transfer_win,
            "valid_R4P01_placebo": p01_valid,
            "performance_gate_pass": c01_performance_pass,
            "pass": c01_performance_pass and p01_valid,
        },
        "R4F01": {"exact_target_identity": identity, "pass": identity},
        "R4P01": {
            "selection_prohibited": True,
            "zero_unexpected_model_fallbacks": p01_zero_fallbacks,
            "joint_permutation_evidence_pass": formula_placebo_evidence["joint_permutation_pass"],
            "formula_feature_divergence_pass": formula_placebo_evidence[
                "formula_feature_divergence_pass"
            ],
            "pass": p01_valid,
        },
    }


def _evaluate_benchmark_gates(
    candidates: dict[str, Any],
    *,
    benchmark_payload: dict[str, Any],
    benchmark_contract: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    config = benchmark_contract["promotion_gates"]
    cost_view = str(config["cost_view"])
    metric = str(config["metric"])
    required_ids = list(map(str, config["required_benchmark_ids"]))
    minimum_delta = float(config["minimum_delta"])
    benchmark_metrics = {
        benchmark_id: float(
            benchmark_payload["results"][benchmark_id]["cost_views"][cost_view][metric]
        )
        for benchmark_id in required_ids
    }
    results: dict[str, dict[str, Any]] = {}
    for candidate_id, candidate in candidates.items():
        candidate_value = float(candidate["aggregate_cost_views"][cost_view][metric])
        deltas = {
            benchmark_id: candidate_value - benchmark_value
            for benchmark_id, benchmark_value in benchmark_metrics.items()
        }
        checks = {benchmark_id: delta >= minimum_delta for benchmark_id, delta in deltas.items()}
        results[candidate_id] = {
            "scope": str(config["scope"]),
            "cost_view": cost_view,
            "metric": metric,
            "candidate_value": candidate_value,
            "required_benchmark_values": benchmark_metrics,
            "deltas": deltas,
            "minimum_delta": minimum_delta,
            "checks": checks,
            "pass": all(checks.values()),
        }
    return results


def _benchmark_ledger_rows(
    payload: dict[str, Any],
    simulations: dict[str, dict[str, ExactSimulationResult]],
    targets: dict[str, pd.DataFrame],
    *,
    promotion_gate_ids: set[str],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for benchmark_id, views in simulations.items():
        for view_name, simulation in views.items():
            daily = _dataframe_records(simulation.daily)
            events = [_json_ready(event) for event in simulation.events]
            rows.append(
                {
                    "schema_version": 1,
                    "iter_id": ITER_ID,
                    "benchmark_id": benchmark_id,
                    "cost_view": view_name,
                    "promotion_gate": benchmark_id in promotion_gate_ids,
                    "required_evidence": True,
                    "target_sha256": canonical_target_hash(targets[benchmark_id]),
                    "daily_return_sha256": hashlib.sha256(_canonical_json_bytes(daily)).hexdigest(),
                    "cost_event_sha256": hashlib.sha256(_canonical_json_bytes(events)).hexdigest(),
                    "metrics": payload["results"][benchmark_id]["cost_views"][view_name],
                    "daily": daily,
                    "events": events,
                }
            )
    return rows


def _evaluate_candidate_gates(
    candidates: dict[str, Any],
    validation_contract: dict[str, Any],
    *,
    benchmark_gates: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    gates = validation_contract["family_gates"]
    result: dict[str, dict[str, Any]] = {}
    for candidate_id, candidate in candidates.items():
        folds = candidate["folds"]
        positive_primary = sum(
            float(row["primary_10bps"]["total_return_pct"]) > 0.0 for row in folds.values()
        )
        positive_stress = sum(
            float(row["stress_20bps"]["total_return_pct"]) > 0.0 for row in folds.values()
        )
        transfer = candidate["transfer_holdout"]["primary_10bps"]
        aggregate = candidate["aggregate_cost_views"]["primary_10bps"]
        checks = {
            "positive_net_return_folds": positive_primary
            >= int(gates["positive_net_return_folds_min"]),
            "positive_stress_20bps_folds": positive_stress
            >= int(gates["stress_20bps_positive_folds_min"]),
            "transfer_holdout_sharpe": float(transfer["annualized_sharpe"])
            >= float(gates["transfer_holdout_sharpe_min"]),
            "transfer_holdout_max_drawdown": abs(float(transfer["max_drawdown_pct"]))
            <= float(gates["transfer_holdout_max_drawdown_abs_pct_max"]),
            "annualized_full_L1_executed_notional": float(
                aggregate["annualized_full_L1_executed_notional_ratio"]
            )
            <= float(gates["annualized_full_L1_executed_notional_ratio_max"]),
            "annualized_BIL_excess_sharpe": float(aggregate["annualized_BIL_excess_sharpe"])
            >= float(gates["annualized_BIL_excess_sharpe_min"]),
            "cumulative_DSR": float(candidate["dsr"]["probability"])
            >= float(gates["cumulative_dsr_probability_min"]),
            "benchmark_relative_sharpe": bool(benchmark_gates[candidate_id]["pass"]),
            "no_unexpected_model_fallback": int(candidate["unexpected_model_fallback_count"]) == 0,
        }
        result[candidate_id] = {
            "positive_primary_fold_count": positive_primary,
            "positive_stress_fold_count": positive_stress,
            "checks": checks,
            "pass": all(checks.values()),
        }
    return result


def _cost_reconciliation(
    aggregate: dict[str, dict[str, ExactSimulationResult]],
    segments: dict[str, dict[str, dict[str, ExactSimulationResult]]],
    segment_definitions: list[dict[str, Any]],
    *,
    benchmarks: dict[str, dict[str, ExactSimulationResult]] | None = None,
    tolerance: float = 1e-12,
    expected_event_reason_codes: set[str] | None = None,
) -> dict[str, Any]:
    if not math.isfinite(tolerance) or tolerance <= 0.0:
        raise ValueError("cost reconciliation tolerance must be finite and positive")
    expected_event_reason_codes = expected_event_reason_codes or {
        "scheduled_rebalance",
        "independent_boundary_entry",
        "terminal_liquidation",
    }
    rows = []
    maximum_error = 0.0
    maximum_equity_error = 0.0
    failures: list[str] = []
    aggregate_start = str(segment_definitions[0]["start"])
    for candidate_id in SPEC_PATHS:
        aggregate_value = float(
            aggregate[candidate_id]["primary_10bps"].metrics["total_full_L1_executed_notional"]
        )
        segment_values = {
            segment["segment_id"]: float(
                segments[candidate_id][segment["segment_id"]]["primary_10bps"].metrics[
                    "total_full_L1_executed_notional"
                ]
            )
            for segment in segment_definitions
        }
        for view_name, simulation in aggregate[candidate_id].items():
            maximum_error = max(
                maximum_error,
                float(simulation.metrics["maximum_cost_reconciliation_error"]),
            )
            checks = _simulation_accounting_checks(
                simulation,
                expected_start=aggregate_start,
                tolerance=tolerance,
                expected_event_reason_codes=expected_event_reason_codes,
            )
            maximum_equity_error = max(maximum_equity_error, checks["equity_chain_error"])
            failures.extend(
                f"{candidate_id}:AGGREGATE:{view_name}:{failure}" for failure in checks["failures"]
            )
        for scope_id, scope in segments[candidate_id].items():
            expected_start = str(
                next(
                    segment["start"]
                    for segment in segment_definitions
                    if segment["segment_id"] == scope_id
                )
            )
            for view_name, simulation in scope.items():
                maximum_error = max(
                    maximum_error,
                    float(simulation.metrics["maximum_cost_reconciliation_error"]),
                )
                checks = _simulation_accounting_checks(
                    simulation,
                    expected_start=expected_start,
                    tolerance=tolerance,
                    expected_event_reason_codes=expected_event_reason_codes,
                )
                maximum_equity_error = max(maximum_equity_error, checks["equity_chain_error"])
                failures.extend(
                    f"{candidate_id}:{scope_id}:{view_name}:{failure}"
                    for failure in checks["failures"]
                )
        segment_sum = sum(segment_values.values())
        aggregate_events = aggregate[candidate_id]["primary_10bps"].events
        segment_event_groups = [
            segments[candidate_id][segment["segment_id"]]["primary_10bps"].events
            for segment in segment_definitions
        ]
        segment_events = [event for group in segment_event_groups for event in group]
        aggregate_boundaries = _boundary_notionals(aggregate_events)
        segment_boundaries = [_boundary_notionals(group) for group in segment_event_groups]
        rows.append(
            {
                "candidate_id": candidate_id,
                "aggregate_primary_full_L1": aggregate_value,
                "independent_segment_primary_full_L1": segment_values,
                "independent_segment_sum": segment_sum,
                "reset_difference_segment_sum_minus_aggregate": segment_sum - aggregate_value,
                "aggregate_boundary_full_L1": aggregate_boundaries,
                "independent_segment_boundary_full_L1": {
                    "entry_sum": float(
                        sum(boundary["entry"] or 0.0 for boundary in segment_boundaries)
                    ),
                    "terminal_sum": float(
                        sum(boundary["terminal"] or 0.0 for boundary in segment_boundaries)
                    ),
                    "event_count": len(segment_events),
                },
                "difference_explanation": (
                    "Each fold and transfer segment starts in cash and liquidates independently; "
                    "the aggregate path enters once, crosses boundaries without reset, and "
                    "liquidates once."
                ),
            }
        )
    benchmark_rows = []
    for benchmark_id, views in (benchmarks or {}).items():
        for view_name, simulation in views.items():
            maximum_error = max(
                maximum_error,
                float(simulation.metrics["maximum_cost_reconciliation_error"]),
            )
            checks = _simulation_accounting_checks(
                simulation,
                expected_start=aggregate_start,
                tolerance=tolerance,
                expected_event_reason_codes=expected_event_reason_codes,
            )
            maximum_equity_error = max(maximum_equity_error, checks["equity_chain_error"])
            failures.extend(
                f"BENCHMARK:{benchmark_id}:AGGREGATE:{view_name}:{failure}"
                for failure in checks["failures"]
            )
            benchmark_rows.append(
                {
                    "benchmark_id": benchmark_id,
                    "cost_view": view_name,
                    "full_L1_executed_notional": float(
                        simulation.metrics["total_full_L1_executed_notional"]
                    ),
                    "accounting_pass": not checks["failures"],
                }
            )
    return {
        "schema_version": 1,
        "iter_id": ITER_ID,
        "accounting": "exact_self_financing_full_L1",
        "tolerance": tolerance,
        "maximum_event_reconciliation_error": maximum_error,
        "maximum_equity_chain_error": maximum_equity_error,
        "failures": failures,
        "pass": maximum_error <= tolerance and maximum_equity_error <= tolerance and not failures,
        "rows": rows,
        "benchmark_rows": benchmark_rows,
    }


def _simulation_accounting_checks(
    simulation: ExactSimulationResult,
    *,
    expected_start: str,
    tolerance: float,
    expected_event_reason_codes: set[str],
) -> dict[str, Any]:
    failures: list[str] = []
    events = simulation.events
    daily = simulation.daily
    if not events:
        return {
            "equity_chain_error": math.inf,
            "failures": ["event_ledger_empty"],
        }
    nonterminal = [event for event in events if not event["terminal"]]
    terminal = [event for event in events if event["terminal"]]
    if not nonterminal or str(nonterminal[0]["session"]) != expected_start:
        failures.append("missing_first_session_entry")
    if len(terminal) != 1:
        failures.append("terminal_liquidation_count_not_one")
    if events[-1].get("terminal") is not True:
        failures.append("terminal_liquidation_not_last_event")
    if any(str(event.get("reason")) not in expected_event_reason_codes for event in events):
        failures.append("unexpected_event_reason")
    if any(
        bool(event.get("terminal")) != (event.get("reason") == "terminal_liquidation")
        for event in events
    ):
        failures.append("terminal_reason_mismatch")
    for event in events:
        pretrade = event.get("pretrade_asset_weights")
        target = event.get("target_asset_weights")
        if (
            not isinstance(pretrade, dict)
            or not isinstance(target, dict)
            or set(pretrade) != set(target)
        ):
            failures.append("event_weight_mapping_mismatch")
            continue
        if RESERVE_SYMBOL not in pretrade:
            failures.append("reserve_symbol_missing_from_cost_event")
            continue
        ratio = float(event["posttrade_equity_ratio"])
        reconstructed_notional = float(
            sum(abs(ratio * float(target[symbol]) - float(pretrade[symbol])) for symbol in target)
        )
        if (
            abs(reconstructed_notional - float(event["full_L1_executed_notional_fraction"]))
            > tolerance
        ):
            failures.append("event_full_L1_notional_mismatch")
    event_notional = float(
        sum(float(event["full_L1_executed_notional_fraction"]) for event in events)
    )
    if abs(event_notional - simulation.metrics["total_full_L1_executed_notional"]) > tolerance:
        failures.append("event_notional_metric_mismatch")
    factors = pd.to_numeric(daily["net_factor"], errors="raise").astype(float)
    equity = pd.to_numeric(daily["equity"], errors="raise").astype(float)
    expected_equity = factors.cumprod()
    equity_error = float(np.max(np.abs(expected_equity.to_numpy() - equity.to_numpy())))
    if equity_error > tolerance:
        failures.append("daily_factor_equity_chain_mismatch")
    if int(simulation.metrics["terminal_liquidation_count"]) != len(terminal):
        failures.append("terminal_metric_event_mismatch")
    if int(simulation.metrics["nonzero_rebalance_count"]) != len(nonterminal):
        failures.append("rebalance_metric_event_mismatch")
    return {"equity_chain_error": equity_error, "failures": failures}


def _boundary_notionals(events: list[dict[str, Any]]) -> dict[str, float | None]:
    entry = next((event for event in events if not event.get("terminal")), None)
    terminal = next((event for event in reversed(events) if event.get("terminal")), None)
    return {
        "entry": (
            float(entry["full_L1_executed_notional_fraction"]) if entry is not None else None
        ),
        "terminal": (
            float(terminal["full_L1_executed_notional_fraction"]) if terminal is not None else None
        ),
    }


def _scoped_events(
    events: list[dict[str, Any]],
    *,
    candidate_id: str,
    scope_id: str,
    cost_view: str,
) -> list[dict[str, Any]]:
    return [
        {
            "schema_version": 1,
            "iter_id": ITER_ID,
            "candidate_id": candidate_id,
            "scope_id": scope_id,
            "cost_view": cost_view,
            **event,
        }
        for event in events
    ]


def _scoped_daily_returns(
    daily: pd.DataFrame,
    *,
    candidate_id: str,
    scope_id: str,
    cost_view: str,
) -> list[dict[str, Any]]:
    return [
        {
            "schema_version": 1,
            "iter_id": ITER_ID,
            "candidate_id": candidate_id,
            "scope_id": scope_id,
            "cost_view": cost_view,
            **row,
        }
        for row in _dataframe_records(daily)
    ]


def _pbo_returns_from_daily_ledger(
    rows: list[dict[str, Any]],
    *,
    folds: list[dict[str, Any]],
    candidate_ids: list[str],
) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    fold_ids = [str(fold["fold_id"]) for fold in folds]
    fold_order = {fold_id: index for index, fold_id in enumerate(fold_ids)}
    candidate_series: dict[str, pd.Series] = {}
    for candidate_id in candidate_ids:
        selected = [
            row
            for row in rows
            if row.get("candidate_id") == candidate_id
            and row.get("scope_id") in fold_order
            and row.get("cost_view") == "primary_10bps"
        ]
        selected.sort(
            key=lambda row: (
                fold_order[str(row["scope_id"])],
                str(row["interval_start"]),
            )
        )
        intervals = [str(row["interval_start"]) for row in selected]
        if not intervals or len(intervals) != len(set(intervals)):
            raise ValueError(f"R4 daily-return ledger is incomplete for {candidate_id}")
        values = np.asarray([float(row["net_return"]) for row in selected], dtype=float)
        if not np.isfinite(values).all():
            raise ValueError(f"R4 daily-return ledger is nonfinite for {candidate_id}")
        candidate_series[candidate_id] = pd.Series(values, index=pd.Index(intervals))
    frame = pd.DataFrame(candidate_series)
    if (
        frame.empty
        or frame.isna().any().any()
        or list(frame.columns) != candidate_ids
        or frame.index.has_duplicates
    ):
        raise ValueError("R4 daily-return ledger cannot reproduce the common PBO matrix")
    source_rows = [
        {
            "interval_start": str(interval_start),
            **{candidate_id: float(value) for candidate_id, value in row.items()},
        }
        for interval_start, row in frame.iterrows()
    ]
    return frame, source_rows


def _reconcile_model_prediction_evidence(
    model_records: list[dict[str, Any]],
    prediction_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    by_model: dict[str, list[dict[str, Any]]] = {}
    seen_prediction_keys: set[tuple[str, str]] = set()
    for row in prediction_rows:
        model_id = str(row.get("model_id") or "")
        symbol = str(row.get("symbol") or "")
        key = (model_id, symbol)
        if not model_id or not symbol or key in seen_prediction_keys:
            raise ValueError(
                "R4 prediction ledger contains a missing or duplicate model-symbol key"
            )
        seen_prediction_keys.add(key)
        by_model.setdefault(model_id, []).append(row)

    seen_models: set[str] = set()
    successful_models = 0
    fallback_models = 0
    for record in model_records:
        model_id = str(record.get("model_id") or "")
        if not model_id or model_id in seen_models:
            raise ValueError("R4 model ledger contains a missing or duplicate model_id")
        seen_models.add(model_id)
        expected_predictions = record.get("predictions")
        if not isinstance(expected_predictions, list):
            raise ValueError(f"R4 model predictions are malformed for {model_id}")
        actual_rows = by_model.pop(model_id, [])
        expected_rows = [
            {
                "symbol": str(row["symbol"]),
                "value": float(row["value"]),
            }
            for row in expected_predictions
        ]
        actual_values = [
            {"symbol": str(row["symbol"]), "value": float(row["value"])} for row in actual_rows
        ]
        if actual_values != expected_rows:
            raise ValueError(f"R4 prediction ledger differs from model evidence for {model_id}")
        for row in actual_rows:
            for field in ("segment_id", "candidate_id", "decision_session", "prediction_sha256"):
                if row.get(field) != record.get(field):
                    raise ValueError(f"R4 prediction ledger {field} mismatch for {model_id}")
        if record.get("status") == "fit_complete":
            successful_models += 1
            values = np.asarray([row["value"] for row in expected_rows], dtype="<f8")
            expected_hash = hashlib.sha256(values.tobytes()).hexdigest()
            if record.get("prediction_sha256") != expected_hash:
                raise ValueError(f"R4 model prediction hash mismatch for {model_id}")
            if not str(record.get("fitted_model_sha256") or ""):
                raise ValueError(f"R4 fitted model hash is missing for {model_id}")
        else:
            fallback_models += 1
            if expected_rows or record.get("prediction_sha256") is not None:
                raise ValueError(
                    f"R4 fallback model unexpectedly contains predictions for {model_id}"
                )
    if by_model:
        raise ValueError("R4 prediction ledger contains rows without a model-ledger record")
    return {
        "pass": True,
        "model_record_count": len(model_records),
        "prediction_row_count": len(prediction_rows),
        "successful_model_count": successful_models,
        "fallback_model_count": fallback_models,
    }


def _reconcile_target_ledger_evidence(
    target_rows: list[dict[str, Any]],
    candidates: dict[str, Any],
) -> dict[str, Any]:
    expected_symbols = sorted([RESERVE_SYMBOL, *RANKABLE_SYMBOLS])
    grouped: dict[str, list[dict[str, Any]]] = {candidate_id: [] for candidate_id in SPEC_PATHS}
    seen: set[tuple[str, str]] = set()
    for row in target_rows:
        candidate_id = str(row.get("candidate_id") or "")
        execution_session = str(row.get("execution_session") or "")
        key = (candidate_id, execution_session)
        if candidate_id not in grouped or not execution_session or key in seen:
            raise ValueError("R4 target ledger contains an invalid or duplicate identity")
        seen.add(key)
        weights = row.get("weights")
        if not isinstance(weights, dict) or sorted(weights) != expected_symbols:
            raise ValueError(f"R4 target ledger symbol set mismatch for {candidate_id}")
        numeric = {symbol: float(weights[symbol]) for symbol in expected_symbols}
        values = np.asarray(list(numeric.values()), dtype=float)
        if (
            not np.isfinite(values).all()
            or (values < -1e-12).any()
            or abs(float(values.sum()) - 1.0) > 1e-12
        ):
            raise ValueError(f"R4 target ledger weights are invalid for {candidate_id}")
        row_hash = hashlib.sha256(_canonical_json_bytes(numeric)).hexdigest()
        if row.get("target_sha256") != row_hash:
            raise ValueError(f"R4 target row hash mismatch for {candidate_id}")
        grouped[candidate_id].append(row)

    hashes: dict[str, str] = {}
    for candidate_id, rows in grouped.items():
        rows.sort(key=lambda row: str(row["execution_session"]))
        if not rows:
            raise ValueError(f"R4 target ledger is empty for {candidate_id}")
        frame = pd.DataFrame(
            [row["weights"] for row in rows],
            index=pd.DatetimeIndex([row["execution_session"] for row in rows]),
            columns=expected_symbols,
            dtype=float,
        )
        target_hash = canonical_target_hash(frame)
        expected = candidates[candidate_id]
        if len(frame) != int(expected["target_count"]):
            raise ValueError(f"R4 target count mismatch for {candidate_id}")
        if target_hash != expected["target_sha256"]:
            raise ValueError(f"R4 aggregate target hash mismatch for {candidate_id}")
        hashes[candidate_id] = target_hash
    if hashes["R4F01"] != hashes["R4M01"]:
        raise ValueError("R4 staged fallback target identity failed")
    return {
        "pass": True,
        "row_count": len(target_rows),
        "candidate_target_sha256": hashes,
    }


def _reconcile_feature_and_model_refits(
    feature_rows: list[dict[str, Any]],
    model_records: list[dict[str, Any]],
    specs: dict[str, StrategySpec],
) -> dict[str, Any]:
    dataset = pd.DataFrame(feature_rows)
    required_identity = {
        "decision_position",
        "decision_session",
        "execution_position",
        "execution_session",
        "label_end_position",
        "label_end_session",
        "symbol",
    }
    if dataset.empty or not required_identity.issubset(dataset.columns):
        raise ValueError("R4 staged feature ledger identity fields are incomplete")
    if dataset.duplicated(["decision_position", "symbol"]).any():
        raise ValueError("R4 staged feature ledger contains duplicate decision-symbol rows")
    for _, group in dataset.groupby("decision_position", sort=True):
        if set(map(str, group["symbol"])) != set(RANKABLE_SYMBOLS):
            raise ValueError("R4 staged feature ledger symbol coverage mismatch")
        if any(group[field].nunique(dropna=False) != 1 for field in required_identity - {"symbol"}):
            raise ValueError("R4 staged feature ledger decision identity is inconsistent")
        row = group.iloc[0]
        if int(row["execution_position"]) != int(row["decision_position"]) + 1:
            raise ValueError("R4 staged execution position is not next-session aligned")
        decision = pd.Timestamp(str(row["decision_session"]))
        execution = pd.Timestamp(str(row["execution_session"]))
        label_position = row["label_end_position"]
        label_session = row["label_end_session"]
        if label_position is None or label_session is None:
            if not (label_position is None and label_session is None):
                raise ValueError("R4 staged unavailable label identity is inconsistent")
            if not decision < execution:
                raise ValueError("R4 staged decision/execution chronology is invalid")
            continue
        if int(label_position) != int(row["execution_position"]) + HORIZON_SESSIONS:
            raise ValueError("R4 staged label horizon position mismatch")
        label_end = pd.Timestamp(str(label_session))
        if not decision < execution < label_end:
            raise ValueError("R4 staged decision/execution/label chronology is invalid")

    successful_refits = 0
    deterministic_fallbacks = 0
    for record in model_records:
        candidate_id = str(record.get("candidate_id") or "")
        spec = specs.get(candidate_id)
        if spec is None or spec.model is None:
            raise ValueError(f"R4 staged model record has no bound spec: {candidate_id}")
        feature_names = tuple(map(str, record.get("feature_names") or []))
        label_name = str(record.get("label_name") or "")
        decision_session = str(record.get("decision_session") or "")
        current = dataset[dataset["decision_session"] == decision_session].sort_values("symbol")
        if len(current) != len(RANKABLE_SYMBOLS) or not feature_names or not label_name:
            raise ValueError(f"R4 staged model identity is incomplete: {record.get('model_id')}")
        decision_positions = current["decision_position"].unique()
        if len(decision_positions) != 1:
            raise ValueError(f"R4 staged model decision position is ambiguous: {decision_session}")
        train = training_rows_for_prediction(
            dataset,
            decision_position=int(decision_positions[0]),
            train_start_session="2018-02-01",
            feature_names=feature_names,
            label_name=label_name,
        )
        checks = {
            "training_row_count": len(train),
            "training_decision_start": (
                str(train["decision_session"].min()) if not train.empty else None
            ),
            "training_decision_end": (
                str(train["decision_session"].max()) if not train.empty else None
            ),
            "training_label_terminal_end": (
                str(train["label_end_session"].max()) if not train.empty else None
            ),
            "training_data_sha256": _frame_sha256(train, [*feature_names, label_name]),
            "prediction_feature_sha256": _frame_sha256(current, list(feature_names)),
            "training_label_mean": (
                float(pd.to_numeric(train[label_name], errors="raise").mean())
                if not train.empty
                else None
            ),
        }
        for field_name, expected in checks.items():
            actual = record.get(field_name)
            if isinstance(expected, float):
                matched = math.isclose(float(actual), expected, rel_tol=1e-12, abs_tol=1e-12)
            else:
                matched = actual == expected
            if not matched:
                raise ValueError(
                    f"R4 staged model training evidence mismatch: {record.get('model_id')}:"
                    f"{field_name}"
                )
        if record.get("model_config") != spec.model.model_dump(mode="json"):
            raise ValueError(f"R4 staged model config mismatch: {record.get('model_id')}")

        minimum_rows = max(80, 2 * int(spec.model.hyperparameters.get("min_child_samples", 1)))
        deterministic_failure: str | None = None
        if len(train) < minimum_rows:
            deterministic_failure = "insufficient_training_rows"
        elif spec.model.kind == "lightgbm_classifier" and train[label_name].nunique() < 2:
            deterministic_failure = "single_class_training_labels"
        current_values = current[list(feature_names)].replace([np.inf, -np.inf], np.nan)
        if current_values.isna().any().any():
            deterministic_failure = "nonfinite_prediction_features"
        if deterministic_failure is not None:
            if (
                record.get("status") != "fallback_applied"
                or record.get("failure_reason") != deterministic_failure
                or record.get("predictions")
            ):
                raise ValueError(
                    f"R4 staged deterministic fallback mismatch: {record.get('model_id')}"
                )
            deterministic_fallbacks += 1
            continue
        if record.get("status") != "fit_complete":
            raise ValueError(
                f"R4 non-deterministic model failure cannot be independently attested: "
                f"{record.get('model_id')}"
            )
        model = _make_estimator(spec)
        if _json_ready(model.get_params(deep=True)) != record.get("resolved_model_params"):
            raise ValueError(f"R4 staged resolved model params mismatch: {record.get('model_id')}")
        model.fit(train[list(feature_names)], train[label_name])
        if spec.model.kind == "lightgbm_classifier":
            prediction = np.asarray(model.predict_proba(current_values)[:, 1], dtype=float)
        else:
            prediction = np.asarray(model.predict(current_values), dtype=float)
        expected_predictions = [
            {"symbol": str(symbol), "value": float(value)}
            for symbol, value in zip(current["symbol"], prediction, strict=True)
        ]
        if expected_predictions != record.get("predictions"):
            raise ValueError(f"R4 staged independent model refit differs: {record.get('model_id')}")
        booster = getattr(model, "booster_", None)
        fitted_sha256 = hashlib.sha256(booster.model_to_string().encode("utf-8")).hexdigest()
        if fitted_sha256 != record.get("fitted_model_sha256"):
            raise ValueError(f"R4 staged fitted model hash mismatch: {record.get('model_id')}")
        successful_refits += 1
    return {
        "pass": True,
        "feature_row_count": len(dataset),
        "decision_count": int(dataset["decision_position"].nunique()),
        "successful_model_refit_count": successful_refits,
        "deterministic_fallback_count": deterministic_fallbacks,
    }


def _assert_metric_mapping_matches(
    label: str,
    actual: dict[str, Any],
    expected: dict[str, Any],
    *,
    ignored_fields: set[str] | None = None,
) -> None:
    ignored_fields = ignored_fields or set()
    actual_keys = set(actual) - ignored_fields
    expected_keys = set(expected) - ignored_fields
    if actual_keys != expected_keys:
        raise ValueError(f"R4 metric field set mismatch for {label}")
    for field_name in sorted(actual_keys):
        actual_value = actual[field_name]
        expected_value = expected[field_name]
        if isinstance(expected_value, bool) or isinstance(expected_value, str):
            matched = type(actual_value) is type(expected_value) and actual_value == expected_value
        elif isinstance(expected_value, int):
            matched = type(actual_value) is int and actual_value == expected_value
        elif isinstance(expected_value, float):
            matched = math.isclose(
                float(actual_value),
                expected_value,
                rel_tol=1e-12,
                abs_tol=1e-12,
            )
        else:
            matched = actual_value == expected_value
        if not matched:
            raise ValueError(f"R4 metric mismatch for {label}:{field_name}")


def _strip_scope_fields(row: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in row.items()
        if key
        not in {
            "schema_version",
            "iter_id",
            "candidate_id",
            "scope_id",
            "cost_view",
        }
    }


def _reconcile_performance_ledgers(
    daily_rows: list[dict[str, Any]],
    event_rows: list[dict[str, Any]],
    benchmark_rows: list[dict[str, Any]],
    payload: dict[str, Any],
    runtime_contracts: dict[str, Any],
) -> dict[str, Any]:
    tolerance = float(runtime_contracts["cost_reconciliation_tolerance"])
    reason_codes = set(runtime_contracts["cost_event_reason_codes"])

    def select_rows(
        rows: list[dict[str, Any]],
        candidate_id: str,
        scope_id: str,
        cost_view: str,
    ) -> list[dict[str, Any]]:
        return [
            row
            for row in rows
            if row.get("candidate_id") == candidate_id
            and row.get("scope_id") == scope_id
            and row.get("cost_view") == cost_view
        ]

    def reconcile_group(
        candidate_id: str,
        scope_id: str,
        cost_view: str,
        expected_metrics: dict[str, Any],
    ) -> tuple[pd.DataFrame, list[dict[str, Any]], dict[str, Any]]:
        selected_daily = select_rows(daily_rows, candidate_id, scope_id, cost_view)
        selected_events = select_rows(event_rows, candidate_id, scope_id, cost_view)
        if not selected_daily or not selected_events:
            raise ValueError(
                f"R4 staged performance ledger group missing: {candidate_id}:{scope_id}:{cost_view}"
            )
        intervals = [str(row.get("interval_start") or "") for row in selected_daily]
        if len(intervals) != len(set(intervals)) or intervals != sorted(intervals):
            raise ValueError(
                f"R4 staged daily intervals invalid: {candidate_id}:{scope_id}:{cost_view}"
            )
        daily = pd.DataFrame([_strip_scope_fields(row) for row in selected_daily])
        events = [_strip_scope_fields(row) for row in selected_events]
        maximum_weight = float(daily["maximum_asset_weight_observed"].max())
        recomputed = performance_metrics(daily, events, maximum_weight=maximum_weight)
        _assert_metric_mapping_matches(
            f"{candidate_id}:{scope_id}:{cost_view}",
            recomputed,
            expected_metrics,
            ignored_fields={"annualized_BIL_excess_sharpe"},
        )
        simulation = ExactSimulationResult(daily=daily, events=events, metrics=recomputed)
        checks = _simulation_accounting_checks(
            simulation,
            expected_start=str(daily.iloc[0]["interval_start"]),
            tolerance=tolerance,
            expected_event_reason_codes=reason_codes,
        )
        if checks["failures"]:
            raise ValueError(
                f"R4 staged accounting mismatch: {candidate_id}:{scope_id}:{cost_view}:"
                + ",".join(checks["failures"])
            )
        return daily, events, recomputed

    group_count = 0
    candidate_primary_daily: dict[str, pd.Series] = {}
    for candidate_id, candidate in payload["candidates"].items():
        for cost_view, metrics in candidate["aggregate_cost_views"].items():
            daily, _, _ = reconcile_group(candidate_id, "AGGREGATE", cost_view, metrics)
            group_count += 1
            if cost_view == "primary_10bps":
                candidate_primary_daily[candidate_id] = daily["net_return"].astype(float)
        for scope_id, views in {
            **candidate["folds"],
            "TRANSFER": candidate["transfer_holdout"],
        }.items():
            for cost_view, metrics in views.items():
                reconcile_group(candidate_id, scope_id, cost_view, metrics)
                group_count += 1

    benchmark_by_key: dict[tuple[str, str], dict[str, Any]] = {}
    for row in benchmark_rows:
        key = (str(row.get("benchmark_id") or ""), str(row.get("cost_view") or ""))
        if not all(key) or key in benchmark_by_key:
            raise ValueError("R4 benchmark ledger contains an invalid or duplicate identity")
        benchmark_by_key[key] = row
    required_gate_ids = set(runtime_contracts["benchmark_gate_config"]["required_benchmark_ids"])
    cash_primary: pd.Series | None = None
    for benchmark_id, benchmark in payload["benchmarks"]["results"].items():
        staged_id = f"BENCHMARK:{benchmark_id}"
        for cost_view, metrics in benchmark["cost_views"].items():
            daily, events, recomputed = reconcile_group(
                staged_id,
                "AGGREGATE",
                cost_view,
                metrics,
            )
            group_count += 1
            row = benchmark_by_key.pop((benchmark_id, cost_view), None)
            if row is None:
                raise ValueError(f"R4 benchmark ledger row missing: {benchmark_id}:{cost_view}")
            if bool(row.get("promotion_gate")) != (benchmark_id in required_gate_ids):
                raise ValueError(f"R4 benchmark promotion flag mismatch: {benchmark_id}")
            if row.get("daily") != _dataframe_records(daily):
                raise ValueError(f"R4 benchmark embedded daily rows mismatch: {benchmark_id}")
            if row.get("events") != [_json_ready(event) for event in events]:
                raise ValueError(f"R4 benchmark embedded event rows mismatch: {benchmark_id}")
            _assert_metric_mapping_matches(
                f"benchmark:{benchmark_id}:{cost_view}",
                recomputed,
                row.get("metrics") or {},
            )
            if benchmark_id == "cash_proxy" and cost_view == "primary_10bps":
                cash_primary = daily["net_return"].astype(float)
    if benchmark_by_key:
        raise ValueError("R4 benchmark ledger contains unexpected rows")
    if cash_primary is None:
        raise ValueError("R4 staged cash benchmark is missing")
    for candidate_id, returns in candidate_primary_daily.items():
        expected = float(
            payload["candidates"][candidate_id]["aggregate_cost_views"]["primary_10bps"][
                "annualized_BIL_excess_sharpe"
            ]
        )
        actual = defined_annualized_sharpe(returns - cash_primary)
        if not math.isclose(actual, expected, rel_tol=1e-12, abs_tol=1e-12):
            raise ValueError(f"R4 staged BIL-excess Sharpe mismatch for {candidate_id}")
    return {"pass": True, "simulation_group_count": group_count}


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    raise ValueError(f"blank JSONL row at {path}:{line_number}")
                row = json.loads(line)
                if not isinstance(row, dict):
                    raise ValueError(f"JSONL row must be an object at {path}:{line_number}")
                rows.append(row)
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid JSONL artifact: {path}") from exc
    return rows


def _verify_staged_ledger_bundle(
    paths: dict[str, Path],
    payload: dict[str, Any],
    runtime_contracts: dict[str, Any],
    specs: dict[str, StrategySpec],
) -> dict[str, Any]:
    ledger_names = {
        "feature_ledger": "feature_ledger",
        "prediction_ledger": "prediction_ledger",
        "daily_return_ledger": "daily_return_ledger",
        "target_ledger": "target_ledger",
        "event_ledger": "event_ledger",
        "benchmark_ledger": "benchmark_ledger",
        "model_ledger": "model_ledger",
        "trial_ledger": "trial_ledger",
    }
    inventory = payload["evidence_reconciliation"]["ledger_inventory"]
    loaded: dict[str, list[dict[str, Any]]] = {}
    for path_name, inventory_name in ledger_names.items():
        rows = _load_jsonl(paths[path_name])
        expected = inventory[inventory_name]
        if len(rows) != int(expected["row_count"]):
            raise ValueError(f"R4 staged ledger row count mismatch: {inventory_name}")
        if _jsonl_sha256(rows) != expected["sha256"]:
            raise ValueError(f"R4 staged ledger hash mismatch: {inventory_name}")
        if _sha256_file(paths[path_name]) != expected["sha256"]:
            raise ValueError(f"R4 staged ledger file hash mismatch: {inventory_name}")
        loaded[inventory_name] = rows

    target_reconciliation = _reconcile_target_ledger_evidence(
        loaded["target_ledger"],
        payload["candidates"],
    )
    prediction_reconciliation = _reconcile_model_prediction_evidence(
        loaded["model_ledger"],
        loaded["prediction_ledger"],
    )
    if prediction_reconciliation != payload["evidence_reconciliation"]["prediction_reconciliation"]:
        raise ValueError("R4 staged prediction reconciliation differs from report")
    model_refit_reconciliation = _reconcile_feature_and_model_refits(
        loaded["feature_ledger"],
        loaded["model_ledger"],
        specs,
    )

    trial_by_candidate: dict[str, dict[str, Any]] = {}
    for row in loaded["trial_ledger"]:
        candidate_id = str(row.get("candidate_id") or "")
        if candidate_id not in SPEC_PATHS or candidate_id in trial_by_candidate:
            raise ValueError("R4 staged trial ledger identity is invalid")
        trial_by_candidate[candidate_id] = row
    if set(trial_by_candidate) != set(SPEC_PATHS):
        raise ValueError("R4 staged trial ledger candidate set mismatch")
    trial_fields = {
        "spec_hash",
        "promotion_eligible",
        "aggregate_cost_views",
        "folds",
        "transfer_holdout",
        "dsr",
        "role_gate",
        "family_gates",
        "historical_research_gate_pass",
    }
    for candidate_id, row in trial_by_candidate.items():
        expected = payload["candidates"][candidate_id]
        for field_name in trial_fields:
            if _canonical_json_bytes(row.get(field_name)) != _canonical_json_bytes(
                expected.get(field_name)
            ):
                raise ValueError(f"R4 staged trial ledger mismatch: {candidate_id}:{field_name}")

    folds = runtime_contracts["validation"]["folds"]
    pbo_contract = runtime_contracts["validation"]["pbo"]
    pbo_frame, _ = _pbo_returns_from_daily_ledger(
        loaded["daily_return_ledger"],
        folds=folds,
        candidate_ids=list(SPEC_PATHS),
    )
    if len(pbo_frame) != int(pbo_contract["expected_return_observation_count"]):
        raise ValueError("R4 staged PBO observation count mismatch")
    selection_ids = list(map(str, pbo_contract["selection_candidate_ids"]))
    recomputed_pbo = probability_backtest_overfitting(
        pbo_frame,
        candidate_ids=selection_ids,
        block_count=int(pbo_contract["block_count"]),
        in_sample_block_count=int(pbo_contract["in_sample_block_count"]),
    )
    reported_pbo = payload["family_pbo"]
    for field_name, value in recomputed_pbo.items():
        if _canonical_json_bytes(reported_pbo.get(field_name)) != _canonical_json_bytes(value):
            raise ValueError(f"R4 staged PBO mismatch: {field_name}")
    pbo_source_rows = [
        {
            "interval_start": str(interval_start),
            **{candidate_id: float(row[candidate_id]) for candidate_id in selection_ids},
        }
        for interval_start, row in pbo_frame.iterrows()
    ]
    if hashlib.sha256(_canonical_json_bytes(pbo_source_rows)).hexdigest() != reported_pbo.get(
        "return_source_sha256"
    ):
        raise ValueError("R4 staged PBO source hash mismatch")

    for candidate_id in SPEC_PATHS:
        reported_dsr = payload["candidates"][candidate_id]["dsr"]
        for trial_count in runtime_contracts["dsr_sensitivity_trial_counts"]:
            recomputed = deflated_sharpe_ratio(
                pbo_frame[candidate_id],
                trial_count=trial_count,
            )
            reported = reported_dsr["sensitivity"][str(trial_count)]
            if _canonical_json_bytes(recomputed) != _canonical_json_bytes(reported):
                raise ValueError(f"R4 staged DSR mismatch: {candidate_id}:{trial_count}")

    performance_reconciliation = _reconcile_performance_ledgers(
        loaded["daily_return_ledger"],
        loaded["event_ledger"],
        loaded["benchmark_ledger"],
        payload,
        runtime_contracts,
    )
    cost_reconciliation = _load_json(paths["cost_reconciliation"])
    if _canonical_json_bytes(cost_reconciliation) != _canonical_json_bytes(
        payload["cost_reconciliation"]
    ):
        raise ValueError("R4 staged cost reconciliation differs from evaluation payload")
    model_provenance = _load_json(paths["model_provenance"])
    if model_provenance.get("ledger_sha256") != inventory["model_ledger"]["sha256"]:
        raise ValueError("R4 staged model provenance ledger binding mismatch")
    if model_provenance.get("prediction_ledger_sha256") != inventory["prediction_ledger"]["sha256"]:
        raise ValueError("R4 staged model provenance prediction binding mismatch")
    if model_provenance.get("prediction_reconciliation") != prediction_reconciliation:
        raise ValueError("R4 staged model provenance reconciliation mismatch")
    return {
        "pass": True,
        "ledger_count": len(ledger_names),
        "target_reconciliation": target_reconciliation,
        "prediction_reconciliation": prediction_reconciliation,
        "model_refit_reconciliation": model_refit_reconciliation,
        "performance_reconciliation": performance_reconciliation,
        "pbo_recomputed": True,
        "dsr_sensitivity_recomputed": True,
    }


def _verify_staged_publication(
    paths: dict[str, Path],
    published_paths: dict[str, Path],
    payload: dict[str, Any],
    receipt: dict[str, Any],
    root: Path,
) -> dict[str, Any]:
    expected_names = set(paths)
    actual_filenames = {
        path.name for path in next(iter(paths.values())).parent.iterdir() if path.is_file()
    }
    expected_filenames = {path.name for path in paths.values()}
    if actual_filenames != expected_filenames:
        raise ValueError("R4 staged publication file inventory mismatch")
    if any(path.is_symlink() or not path.is_file() for path in paths.values()):
        raise ValueError("R4 staged publication contains a non-regular file")
    if _canonical_json_bytes(_load_json(paths["evaluation"])) != _canonical_json_bytes(payload):
        raise ValueError("R4 staged evaluation report differs from in-memory payload")
    if _canonical_json_bytes(_load_json(paths["receipt"])) != _canonical_json_bytes(receipt):
        raise ValueError("R4 staged receipt differs from in-memory payload")
    if receipt.get("schema_version") != 3 or receipt.get("receipt_contract") != (
        "multiasset_forward_multimodal_r4_v3"
    ):
        raise ValueError("R4 staged receipt contract is invalid")
    expected_children = expected_names - {"receipt"}
    if set(receipt.get("children") or {}) != expected_children:
        raise ValueError("R4 staged receipt child inventory mismatch")
    for name in expected_children:
        binding = receipt["children"][name]
        expected_binding = _binding_for_destination(paths[name], published_paths[name], root)
        if binding != expected_binding:
            raise ValueError(f"R4 staged receipt child binding mismatch: {name}")
    for field_name in (
        "decision",
        "workflow_pass",
        "research_pass",
        "llm_contribution_pass",
        "paper_ready_pass",
    ):
        if receipt.get(field_name) != payload.get(field_name):
            raise ValueError(f"R4 staged receipt status mismatch: {field_name}")
    if receipt.get("paper_ready_pass") is not False:
        raise ValueError("R4 staged receipt cannot assert Paper readiness")
    for name, expected_path in {
        "preregistration_lock": root / ITERATION_DIR / "lock-set/preregistration-lock.json",
        "runner_lock": root / ITERATION_DIR / "lock-set/runner-lock.json",
        "lock_anchor": root / ITERATION_DIR / "lock-set/lock-anchor.json",
        "evaluation_attempt": root / ITERATION_DIR / "evaluation-attempt.json",
    }.items():
        if receipt.get(name) != _file_binding(expected_path, root):
            raise ValueError(f"R4 staged external binding mismatch: {name}")
    return {
        "pass": True,
        "file_count": len(expected_names),
        "child_count": len(expected_children),
    }


def _dataframe_records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    values = frame.astype(object).where(pd.notna(frame), None)
    return [_json_ready(row) for row in values.to_dict(orient="records")]


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid JSON artifact: {path}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"JSON artifact must be an object: {path}")
    return payload


def _verify_file_binding(root: Path, binding: Any) -> Path:
    if not isinstance(binding, dict):
        raise ValueError("R4 file binding must be an object")
    relative = str(binding.get("path") or "")
    path = (root / relative).resolve()
    try:
        path.relative_to(root.resolve())
    except ValueError as exc:
        raise ValueError(f"R4 file binding escapes repository: {relative}") from exc
    if not path.is_file() or path.is_symlink():
        raise ValueError(f"R4 bound file is missing, non-regular, or symlinked: {relative}")
    expected = str(binding.get("sha256") or "")
    if not expected or _sha256_file(path) != expected:
        raise ValueError(f"R4 file binding SHA-256 mismatch: {relative}")
    return path


def _write_json_atomic(path: Path, payload: Any) -> None:
    _atomic_write(path, _canonical_json_bytes(payload) + b"\n")


def _write_jsonl_atomic(path: Path, rows: list[dict[str, Any]]) -> None:
    _atomic_write(path, _jsonl_bytes(rows))


def _jsonl_bytes(rows: list[dict[str, Any]]) -> bytes:
    return b"".join(_canonical_json_bytes(row) + b"\n" for row in rows)


def _jsonl_sha256(rows: list[dict[str, Any]]) -> str:
    return hashlib.sha256(_jsonl_bytes(rows)).hexdigest()


def _write_text_atomic(path: Path, content: str) -> None:
    _atomic_write(path, content.encode("utf-8"))


def _atomic_write(path: Path, content: bytes) -> None:
    ensure_dir(path.parent)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    with temporary.open("wb") as handle:
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)
    _fsync_directory(path.parent)


def _file_binding(path: Path, root: Path) -> dict[str, Any]:
    return {
        "path": _relpath(path, root),
        "sha256": _sha256_file(path),
        "size_bytes": path.stat().st_size,
    }


def _binding_for_destination(source: Path, destination: Path, root: Path) -> dict[str, Any]:
    return {
        "path": _relpath(destination, root),
        "sha256": _sha256_file(source),
        "size_bytes": source.stat().st_size,
    }


def _current_runtime() -> dict[str, str]:
    return {
        "python": sys.version,
        "numpy": version("numpy"),
        "pandas": version("pandas"),
        "scipy": version("scipy"),
        "lightgbm": version("lightgbm"),
        "scikit_learn": version("scikit-learn"),
        "pydantic": version("pydantic"),
        "pyyaml": version("PyYAML"),
        "alpaca_py": version("alpaca-py"),
    }


def _reverify_locked_inputs(root: Path, preflight: dict[str, Any]) -> None:
    output = root / ITERATION_DIR
    preregistration_path = output / "lock-set/preregistration-lock.json"
    runner_path = output / "lock-set/runner-lock.json"
    lock_anchor_path = output / "lock-set/lock-anchor.json"
    attempt_path = output / "evaluation-attempt.json"
    if _sha256_file(preregistration_path) != preflight["preregistration_lock_sha256"]:
        raise ValueError("R4 preregistration lock changed during evaluation")
    if _sha256_file(runner_path) != preflight["runner_lock_sha256"]:
        raise ValueError("R4 runner lock changed during evaluation")
    if _sha256_file(lock_anchor_path) != preflight["lock_anchor_file_sha256"]:
        raise ValueError("R4 lock anchor changed during evaluation")
    attempt_binding = preflight.get("evaluation_attempt")
    if not isinstance(attempt_binding, dict):
        raise ValueError("R4 evaluation attempt binding is missing")
    if _verify_file_binding(root, attempt_binding) != attempt_path.resolve():
        raise ValueError("R4 evaluation attempt path changed during evaluation")
    preregistration = _load_json(preregistration_path)
    for binding in preregistration.get("artifacts", []):
        _verify_file_binding(root, binding)
    for binding in preregistration.get("specs", []):
        path = _verify_file_binding(
            root,
            {"path": binding.get("path"), "sha256": binding.get("file_sha256")},
        )
        if strategy_content_hash(load_strategy_spec(path)) != binding.get("semantic_sha256"):
            raise ValueError(f"R4 semantic spec changed during evaluation: {binding.get('path')}")
    runner = _load_json(runner_path)
    for binding in runner.get("files", []):
        _verify_file_binding(root, binding)
    if runner.get("runtime") != _current_runtime():
        raise ValueError("R4 runtime changed during evaluation")
    manifest_path = root / preflight["data_manifest_path"]
    parent_path = root / preflight["parent_snapshot_binding_path"]
    if _sha256_file(manifest_path) != preflight["data_manifest_sha256"]:
        raise ValueError("R4 data manifest changed during evaluation")
    if _sha256_file(parent_path) != preflight["parent_snapshot_binding_sha256"]:
        raise ValueError("R4 parent snapshot binding changed during evaluation")
    verify_alpaca_contract_snapshot(root, manifest_path)


def _publish_directory_exclusive(stage: Path, destination: Path) -> None:
    if not stage.is_dir() or stage.is_symlink():
        raise ValueError("R4 staged result directory is invalid")
    marker = destination.parent / f".{destination.name}-publish.lock"
    descriptor = os.open(marker, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        os.write(descriptor, f"pid={os.getpid()}\n".encode("ascii"))
        os.fsync(descriptor)
        if destination.exists():
            raise ValueError("R4 destination exists; exclusive publication refused")
        os.rename(stage, destination)
        _fsync_directory(destination.parent)
    finally:
        os.close(descriptor)
        if marker.exists():
            marker.unlink()
            _fsync_directory(destination.parent)


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _relpath(path: Path, root: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def _render_markdown(payload: dict[str, Any]) -> str:
    lines = [
        f"# R4 Evaluation: {payload['iter_id']}",
        "",
        f"- Decision: `{payload['decision']}`",
        f"- workflow_pass: `{str(payload['workflow_pass']).lower()}`",
        f"- research_pass: `{str(payload['research_pass']).lower()}`",
        f"- llm_contribution_pass: `{str(payload['llm_contribution_pass']).lower()}`",
        f"- paper_ready_pass: `{str(payload['paper_ready_pass']).lower()}`",
        f"- PBO: `{payload['family_pbo']['probability']:.6f}` over "
        f"`{payload['family_pbo']['partition_count']}` directional partitions",
        "",
        "| Candidate | Return % | Sharpe | Max DD % | DSR | Historical gate |",
        "|---|---:|---:|---:|---:|---|",
    ]
    for candidate_id, candidate in payload["candidates"].items():
        metrics = candidate["aggregate_cost_views"]["primary_10bps"]
        lines.append(
            f"| {candidate_id} | {metrics['total_return_pct']:.4f} | "
            f"{metrics['annualized_sharpe']:.4f} | {metrics['max_drawdown_pct']:.4f} | "
            f"{candidate['dsr']['probability']:.6f} | "
            f"{str(candidate['historical_research_gate_pass']).lower()} |"
        )
    lines.extend(
        [
            "",
            "Historical results are globally exposed transfer evidence. They do not satisfy the "
            "20-session forward or matched Alpaca Paper TCA requirements.",
            "",
        ]
    )
    return "\n".join(lines)


def _render_decision_record(payload: dict[str, Any]) -> str:
    if payload["research_pass"]:
        decision = "continue"
        reason = (
            "At least one frozen promotion-eligible candidate passed the matched historical "
            "research gates. This authorizes only a newly locked broker-free forward epoch."
        )
        next_step = (
            "Freeze target routing, start at zero forward sessions, and require 20 contiguous "
            "bound sessions before any separately reviewed Paper canary."
        )
    else:
        decision = "stop"
        reason = (
            "No frozen promotion-eligible candidate passed every statistical, role, cost, and "
            "stability gate under the preregistered evaluation."
        )
        next_step = (
            "Create a new preregistered iteration; do not retune or add R4 candidates after "
            "seeing these results."
        )
    return (
        f"# Decision Record: {ITER_ID}\n\n"
        "- Path: `eight_candidate_matched_etf_multimodal_family`\n"
        f"- Decision: {decision}\n"
        f"- Reason: {reason}\n"
        f"- Next iteration suggestion: {next_step}\n\n"
        f"Final stored status is `workflow_pass={str(payload['workflow_pass']).lower()}`, "
        f"`research_pass={str(payload['research_pass']).lower()}`, "
        f"`llm_contribution_pass={str(payload['llm_contribution_pass']).lower()}`, and "
        "`paper_ready_pass=false`. Broker writes remain unauthorized.\n"
    )
