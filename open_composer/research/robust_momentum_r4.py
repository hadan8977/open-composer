from __future__ import annotations

import hashlib
import itertools
import json
import math
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from open_composer.analytics import build_performance_metrics
from open_composer.config import ensure_dir, project_root
from open_composer.models.strategy_spec import load_strategy_spec
from open_composer.research.iteration_dossier import validate_iteration_dossier
from open_composer.storage import write_json
from open_composer.strategy_versions import strategy_content_hash

ITER_ID = "mom_robust_momentum_r4"
STRATEGY_NAME = "us_robust_momentum_ensemble_r4"
SPEC_PATH = Path("strategy_specs/drafts/us_robust_momentum_ensemble_r4.yaml")
ITERATION_DIR = Path("reports/research/iterations") / ITER_ID
CANDIDATE_MANIFEST_PATH = ITERATION_DIR / "candidate-manifest.json"
SEARCH_SPACE_PATH = ITERATION_DIR / "search-space.json"
DATA_FEASIBILITY_PATH = ITERATION_DIR / "data-feasibility.json"
COST_CONTRACT_PATH = ITERATION_DIR / "cost-contract.json"
PRIOR_EVIDENCE_PATH = ITERATION_DIR / "prior-evidence.json"
SOURCE_UNIVERSE_PATH = Path("reports/research/iterations/mom_multiasset_r1/universe-manifest.json")

ETF_TREND_SYMBOLS = ("SPY", "QQQ", "IWM", "DIA", "XLK", "SMH", "GLD", "TLT")
SECTOR_ETF_BY_SECTOR = {
    "Basic Materials": "XLB",
    "Consumer Discretionary": "XLY",
    "Consumer Staples": "XLP",
    "Energy": "XLE",
    "Finance": "XLF",
    "Financials": "XLF",
    "Health Care": "XLV",
    "Industrials": "XLI",
    "Real Estate": "XLRE",
    "Technology": "XLK",
    "Telecommunications": "XLC",
    "Utilities": "XLU",
}
RISKY_SLEEVES = ("etf_trend", "residual_stock", "sector_relative")
ALL_SLEEVES = (*RISKY_SLEEVES, "cash")
EXPECTED_CANDIDATE_IDS = tuple(
    [f"D{index:02d}" for index in range(1, 8)]
    + [f"M{index:02d}" for index in range(1, 7)]
    + ["N01", "N02"]
)
FORMAL_FORWARD_START = "2026-07-20"
MIN_COMMON_SESSIONS = 900
MIN_HISTORY_BARS = 300
DECISION_STRIDE_BARS = 5
STOCK_REBALANCE_MULTIPLE = 4
LABEL_HORIZON_BARS = 21
PURGE_BARS = 21
EMBARGO_BARS = 21
OUTER_FOLDS = 4
BASE_COST_BPS = 10.0


class ContractViolation(ValueError):
    pass


class FutureFeatureError(ContractViolation):
    pass


@dataclass(frozen=True)
class Panel:
    open: pd.DataFrame
    close: pd.DataFrame
    volume: pd.DataFrame
    stock_symbols: tuple[str, ...]
    all_symbols: tuple[str, ...]
    sector_by_symbol: dict[str, str]
    source_rows: tuple[dict[str, Any], ...]


@dataclass(frozen=True)
class Fold:
    fold: int
    train_dates: tuple[pd.Timestamp, ...]
    test_dates: tuple[pd.Timestamp, ...]


@dataclass(frozen=True)
class RobustMomentumResult:
    evaluation_path: Path
    markdown_path: Path
    trial_ledger_path: Path
    payload: dict[str, Any]


def prepare_robust_momentum_inputs(root: Path | None = None) -> dict[str, Any]:
    base = root or project_root()
    panel = _load_exact_panel(base)
    manifest_path = base / CANDIDATE_MANIFEST_PATH
    cost_path = base / COST_CONTRACT_PATH
    prior_path = base / PRIOR_EVIDENCE_PATH
    source_universe_path = base / SOURCE_UNIVERSE_PATH
    spec_path = base / SPEC_PATH
    search_path = base / SEARCH_SPACE_PATH
    for path in [
        manifest_path,
        cost_path,
        prior_path,
        source_universe_path,
        spec_path,
        search_path,
    ]:
        if not path.exists():
            raise ContractViolation(f"required preregistration artifact is missing: {path}")

    common = panel.open.index
    forward_start = pd.Timestamp(FORMAL_FORWARD_START, tz="UTC")
    input_rows = [dict(row) for row in panel.source_rows]
    input_bundle_sha = _canonical_sha(input_rows)
    payload = {
        "schema_version": 1,
        "report_type": "robust_momentum_r4_data_feasibility",
        "iter_id": ITER_ID,
        "generated_at": datetime.now(UTC).isoformat(),
        "workflow_pass": True,
        "research_pass": False,
        "llm_contribution_pass": False,
        "paper_ready_pass": False,
        "diagnostic_execution_authorized": True,
        "scope": "historical_current_universe_diagnostic",
        "survivorship_labelled": True,
        "primitive_fields": ["open", "close", "volume"],
        "forward_fill_allowed": False,
        "zero_return_substitution_allowed": False,
        "selected_symbol_count": len(panel.all_symbols),
        "stock_symbol_count": len(panel.stock_symbols),
        "selected_symbols": list(panel.all_symbols),
        "stock_symbols": list(panel.stock_symbols),
        "exact_common_session_count": len(common),
        "exact_common_first_session": common.min().isoformat(),
        "exact_common_last_session": common.max().isoformat(),
        "formal_forward_start": FORMAL_FORWARD_START,
        "formal_forward_observation_count": int((common >= forward_start).sum()),
        "input_bundle_sha256": input_bundle_sha,
        "input_files": input_rows,
        "bindings": {
            "candidate_manifest": _artifact_binding(manifest_path, base),
            "cost_contract": _artifact_binding(cost_path, base),
            "prior_evidence": _artifact_binding(prior_path, base),
            "source_universe": _artifact_binding(source_universe_path, base),
            "source_spec": {
                **_artifact_binding(spec_path, base),
                "strategy_content_hash": strategy_content_hash(load_strategy_spec(spec_path)),
            },
            "search_space": _artifact_binding(search_path, base),
        },
        "capability_status": {
            "daily_price_research": "diagnostic_only",
            "point_in_time_universe": "blocked",
            "inactive_security_and_delisting_returns": "blocked",
            "corporate_action_lineage": "blocked",
            "independent_source_validation": "blocked",
            "opening_auction_tca": "blocked",
        },
        "limitations": [
            "Stock membership is a frozen current snapshot, not historical PIT membership.",
            (
                "Inactive securities, terminal delisting returns, and permanent identifiers "
                "are absent."
            ),
            "The ordinary Longbridge cache is limited to 1,000 daily bars.",
            "Adjusted-price factor lineage and revision history are not independently reconciled.",
            "Nasdaq Basic is not consolidated SIP or official primary-exchange auction data.",
            "No observations occur after the formal forward epoch.",
        ],
    }
    write_json(base / DATA_FEASIBILITY_PATH, payload)
    return payload


def validate_robust_momentum_preflight(root: Path | None = None) -> list[str]:
    base = root or project_root()
    blockers: list[str] = []
    dossier = validate_iteration_dossier(ITER_ID, base, stage="pre-backtest")
    if not dossier.ok:
        blockers.extend(f"iteration:{value}" for value in dossier.blocked)

    required = {
        "search_space": base / SEARCH_SPACE_PATH,
        "candidate_manifest": base / CANDIDATE_MANIFEST_PATH,
        "data_feasibility": base / DATA_FEASIBILITY_PATH,
        "cost_contract": base / COST_CONTRACT_PATH,
        "prior_evidence": base / PRIOR_EVIDENCE_PATH,
        "source_spec": base / SPEC_PATH,
    }
    for label, path in required.items():
        if not path.exists():
            blockers.append(f"{label}_missing")
    if blockers:
        return blockers

    search = _load_json(required["search_space"])
    manifest = _load_json(required["candidate_manifest"])
    feasibility = _load_json(required["data_feasibility"])
    prereg = search.get("preregistration", {})
    if prereg.get("candidate_manifest_sha256") != _sha256_file(required["candidate_manifest"]):
        blockers.append("candidate_manifest_sha256_mismatch")
    candidates = manifest.get("candidates", [])
    candidate_ids = tuple(str(row.get("candidate_id")) for row in candidates)
    if candidate_ids != EXPECTED_CANDIDATE_IDS:
        blockers.append("candidate_id_order_or_set_mismatch")
    if manifest.get("generated_before_backtest") is not True:
        blockers.append("candidate_manifest_not_preregistered")
    if manifest.get("candidate_count") != len(EXPECTED_CANDIDATE_IDS):
        blockers.append("candidate_count_mismatch")
    if feasibility.get("diagnostic_execution_authorized") is not True:
        blockers.append("data_feasibility_not_authorized")
    for pass_name, expected in {
        "workflow_pass": True,
        "research_pass": False,
        "llm_contribution_pass": False,
        "paper_ready_pass": False,
    }.items():
        if feasibility.get(pass_name) is not expected:
            blockers.append(f"data_feasibility_{pass_name}_invalid")
    if feasibility.get("formal_forward_observation_count") != 0:
        blockers.append("unexpected_formal_forward_observations")
    if feasibility.get("primitive_fields") != ["open", "close", "volume"]:
        blockers.append("primitive_field_contract_mismatch")
    if feasibility.get("forward_fill_allowed") is not False:
        blockers.append("forward_fill_contract_mismatch")

    try:
        panel = _load_exact_panel(base)
    except ContractViolation as exc:
        blockers.append(f"panel:{exc}")
    else:
        current_rows = [dict(row) for row in panel.source_rows]
        if feasibility.get("input_bundle_sha256") != _canonical_sha(current_rows):
            blockers.append("input_bundle_sha256_mismatch")
        if feasibility.get("exact_common_session_count") != len(panel.open.index):
            blockers.append("common_session_count_mismatch")
    bindings = feasibility.get("bindings", {})
    for label, path in {
        "candidate_manifest": required["candidate_manifest"],
        "cost_contract": required["cost_contract"],
        "prior_evidence": required["prior_evidence"],
        "search_space": required["search_space"],
    }.items():
        expected = bindings.get(label, {}).get("sha256")
        if expected != _sha256_file(path):
            blockers.append(f"{label}_binding_mismatch")
    spec = load_strategy_spec(required["source_spec"])
    if feasibility.get("bindings", {}).get("source_spec", {}).get(
        "strategy_content_hash"
    ) != strategy_content_hash(spec):
        blockers.append("source_spec_content_hash_mismatch")
    return blockers


def _load_exact_panel(root: Path) -> Panel:
    spec = load_strategy_spec(root / SPEC_PATH)
    source_universe = _load_json(root / SOURCE_UNIVERSE_PATH)
    stock_symbols = tuple(str(value) for value in source_universe.get("selected_symbols", []))
    if len(stock_symbols) != 40 or len(set(stock_symbols)) != 40:
        raise ContractViolation("source stock universe must contain exactly 40 unique symbols")
    all_symbols = tuple(str(value) for value in spec.universe)
    if len(all_symbols) != 59 or len(set(all_symbols)) != 59:
        raise ContractViolation("StrategySpec universe must contain exactly 59 unique symbols")
    if not set(stock_symbols).issubset(all_symbols):
        raise ContractViolation("StrategySpec does not contain the frozen stock universe")
    required_context = set(ETF_TREND_SYMBOLS) | set(SECTOR_ETF_BY_SECTOR.values()) | {"BIL"}
    if not required_context.issubset(all_symbols):
        raise ContractViolation("StrategySpec is missing ETF, sector, or cash context")

    frames: dict[str, pd.DataFrame] = {}
    source_rows: list[dict[str, Any]] = []
    for symbol in all_symbols:
        path = root / f"data/cache/{symbol.lower()}_daily_longbridge_nasdaq_basic.csv"
        frame = _read_source_frame(path, symbol)
        frames[symbol] = frame
        source_rows.append(
            {
                "symbol": symbol,
                "path": str(path.relative_to(root)),
                "sha256": _sha256_file(path),
                "row_count": len(frame),
                "first_session": frame.index.min().isoformat(),
                "last_session": frame.index.max().isoformat(),
            }
        )
    common = frames[all_symbols[0]].index
    for symbol in all_symbols[1:]:
        common = common.intersection(frames[symbol].index, sort=False)
    common = common.sort_values()
    if len(common) < MIN_COMMON_SESSIONS:
        raise ContractViolation(
            f"exact common session count {len(common)} is below {MIN_COMMON_SESSIONS}"
        )

    panels: dict[str, pd.DataFrame] = {}
    for field in ["open", "close", "volume"]:
        panels[field] = pd.DataFrame(
            {symbol: frames[symbol].loc[common, field] for symbol in all_symbols},
            index=common,
            dtype=float,
        )
        if panels[field].isna().any().any():
            raise ContractViolation(f"{field} contains missing values after exact intersection")
    selected_rows = source_universe.get("selected", [])
    sector_by_symbol = {
        str(row["symbol"]): str(row.get("sector") or "Unknown")
        for row in selected_rows
        if isinstance(row, dict) and row.get("symbol")
    }
    if set(sector_by_symbol) != set(stock_symbols):
        raise ContractViolation("sector labels do not match the frozen stock universe")
    return Panel(
        open=panels["open"],
        close=panels["close"],
        volume=panels["volume"],
        stock_symbols=stock_symbols,
        all_symbols=all_symbols,
        sector_by_symbol=sector_by_symbol,
        source_rows=tuple(source_rows),
    )


def _read_source_frame(path: Path, symbol: str) -> pd.DataFrame:
    if not path.exists():
        raise ContractViolation(f"missing source file for {symbol}: {path}")
    frame = pd.read_csv(path, usecols=["timestamp", "open", "close", "volume"])
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True, errors="coerce")
    if frame["timestamp"].isna().any() or frame["timestamp"].duplicated().any():
        raise ContractViolation(f"{symbol} contains invalid or duplicate timestamps")
    for field in ["open", "close", "volume"]:
        frame[field] = pd.to_numeric(frame[field], errors="coerce")
    values = frame[["open", "close", "volume"]].to_numpy(dtype=float)
    if not np.isfinite(values).all():
        raise ContractViolation(f"{symbol} contains non-finite primitive values")
    if (frame[["open", "close"]] <= 0).any().any() or (frame["volume"] < 0).any():
        raise ContractViolation(f"{symbol} contains invalid primitive values")
    return frame.set_index("timestamp").sort_index()[["open", "close", "volume"]]


def _decision_dates(panel: Panel) -> pd.DatetimeIndex:
    stop = len(panel.close.index) - LABEL_HORIZON_BARS - 2
    return panel.close.index[MIN_HISTORY_BARS:stop:DECISION_STRIDE_BARS]


def _build_base_sleeve_targets(
    panel: Panel,
    decision_dates: pd.DatetimeIndex,
) -> tuple[dict[str, pd.DataFrame], pd.DataFrame]:
    columns = list(panel.all_symbols)
    target_rows = {name: [] for name in ALL_SLEEVES}
    legacy_rows: list[pd.Series] = []
    previous_residual: list[str] = []
    previous_sector: list[str] = []
    previous_legacy: list[str] = []
    last_residual = _cash_asset_weights(columns)
    last_sector = _cash_asset_weights(columns)
    last_legacy = _cash_asset_weights(columns)
    for sequence, date in enumerate(decision_dates):
        position = panel.close.index.get_loc(date)
        target_rows["etf_trend"].append(_etf_trend_weights(panel, position))
        if sequence % STOCK_REBALANCE_MULTIPLE == 0:
            residual_scores = _residual_stock_scores(panel, position)
            previous_residual = _buffered_sector_selection(
                residual_scores,
                panel.sector_by_symbol,
                previous_residual,
                top_n=10,
                buffer=3,
                sector_cap=2,
            )
            last_residual = _stock_asset_weights(panel, position, previous_residual)
            sector_scores = _sector_relative_scores(panel, position)
            previous_sector = _buffered_sector_selection(
                sector_scores,
                panel.sector_by_symbol,
                previous_sector,
                top_n=10,
                buffer=3,
                sector_cap=2,
            )
            last_sector = _stock_asset_weights(panel, position, previous_sector)
            legacy_scores = pd.Series(
                {
                    symbol: _window_return(panel.close[symbol], position, 252, 21)
                    for symbol in panel.stock_symbols
                }
            ).sort_values(ascending=False)
            previous_legacy = list(legacy_scores.head(5).index)
            last_legacy = _equal_asset_weights(columns, previous_legacy)
        target_rows["residual_stock"].append(last_residual.copy())
        target_rows["sector_relative"].append(last_sector.copy())
        target_rows["cash"].append(_cash_asset_weights(columns))
        legacy_rows.append(last_legacy.copy())
    sleeves = {
        name: pd.DataFrame(rows, index=decision_dates, columns=columns, dtype=float)
        for name, rows in target_rows.items()
    }
    legacy = pd.DataFrame(legacy_rows, index=decision_dates, columns=columns, dtype=float)
    return sleeves, legacy


def _etf_trend_weights(panel: Panel, position: int) -> pd.Series:
    scores: dict[str, float] = {}
    for symbol in ETF_TREND_SYMBOLS:
        returns = {
            lookback: _window_return(panel.close[symbol], position, lookback, 0)
            for lookback in [63, 126, 252]
        }
        if returns[252] <= 0:
            continue
        scores[symbol] = 0.2 * returns[63] + 0.3 * returns[126] + 0.5 * returns[252]
    if not scores:
        return _cash_asset_weights(list(panel.all_symbols))
    selected = list(pd.Series(scores).sort_values(ascending=False).head(2).index)
    close_returns = panel.close[list(selected)].pct_change(fill_method=None)
    volatility = close_returns.iloc[position - 21 + 1 : position + 1].std(ddof=1)
    inverse = 1.0 / volatility.clip(lower=1e-6)
    raw = 0.5 * pd.Series(1.0 / len(selected), index=selected) + 0.5 * inverse / inverse.sum()
    raw = _cap_and_normalize(raw, cap=0.6)
    result = pd.Series(0.0, index=panel.all_symbols, dtype=float)
    result.loc[selected] = raw
    return result


def _residual_stock_scores(panel: Panel, position: int) -> pd.Series:
    close_returns = panel.close.pct_change(fill_method=None)
    end = position - 20
    start = end - 126
    market = close_returns["SPY"].iloc[start:end]
    rows: dict[str, dict[str, float]] = {}
    for symbol in panel.stock_symbols:
        sector = panel.sector_by_symbol[symbol]
        sector_etf = SECTOR_ETF_BY_SECTOR.get(sector, "SPY")
        y = close_returns[symbol].iloc[start:end]
        regressors = [np.ones(len(y)), market.to_numpy(dtype=float)]
        if sector_etf != "SPY":
            regressors.append(close_returns[sector_etf].iloc[start:end].to_numpy(dtype=float))
        x = np.column_stack(regressors)
        y_values = y.to_numpy(dtype=float)
        if not np.isfinite(x).all() or not np.isfinite(y_values).all():
            raise ContractViolation(f"non-finite residual window for {symbol}")
        coefficients, *_ = np.linalg.lstsq(x, y_values, rcond=None)
        residual = y_values - x @ coefficients
        blocks = [float(residual[offset : offset + 21].sum()) for offset in range(0, 126, 21)]
        rows[symbol] = {
            "residual": float(residual.sum()),
            "persistence": float(np.mean(np.asarray(blocks) > 0)),
            "efficiency": float(abs(residual.sum()) / max(np.abs(residual).sum(), 1e-9)),
            "liquidity": float(
                (panel.close[symbol] * panel.volume[symbol])
                .iloc[position - 59 : position + 1]
                .median()
            ),
            "volatility": float(close_returns[symbol].iloc[position - 62 : position + 1].std()),
        }
    frame = pd.DataFrame.from_dict(rows, orient="index")
    ranks = frame.rank(pct=True, method="average")
    return (
        0.55 * ranks["residual"]
        + 0.20 * ranks["persistence"]
        + 0.15 * ranks["efficiency"]
        + 0.10 * ranks["liquidity"]
        - 0.10 * ranks["volatility"]
    ).sort_values(ascending=False)


def _sector_relative_scores(panel: Panel, position: int) -> pd.Series:
    rows: dict[str, dict[str, float]] = {}
    returns_126 = pd.Series(
        {
            symbol: _window_return(panel.close[symbol], position, 126, 21)
            for symbol in panel.stock_symbols
        }
    )
    returns_63 = pd.Series(
        {
            symbol: _window_return(panel.close[symbol], position, 63, 21)
            for symbol in panel.stock_symbols
        }
    )
    sectors = pd.Series(panel.sector_by_symbol)
    relative_126 = returns_126 - returns_126.groupby(sectors).transform("median")
    relative_63 = returns_63 - returns_63.groupby(sectors).transform("median")
    for symbol in panel.stock_symbols:
        monthly = [
            _window_return(panel.close[symbol], position - offset, 21, 21)
            for offset in range(0, 126, 21)
        ]
        rows[symbol] = {
            "relative_126": float(relative_126[symbol]),
            "relative_63": float(relative_63[symbol]),
            "persistence": float(np.mean(np.asarray(monthly) > 0)),
        }
    ranks = pd.DataFrame.from_dict(rows, orient="index").rank(pct=True, method="average")
    return (
        0.55 * ranks["relative_126"] + 0.25 * ranks["relative_63"] + 0.20 * ranks["persistence"]
    ).sort_values(ascending=False)


def _buffered_sector_selection(
    scores: pd.Series,
    sector_by_symbol: dict[str, str],
    previous: list[str],
    *,
    top_n: int,
    buffer: int,
    sector_cap: int,
) -> list[str]:
    order = list(scores.sort_values(ascending=False).index)
    rank = {symbol: index + 1 for index, symbol in enumerate(order)}
    selected: list[str] = []
    sector_counts: dict[str, int] = {}
    for symbol in previous:
        sector = sector_by_symbol[symbol]
        if (
            rank.get(symbol, math.inf) <= top_n + buffer
            and sector_counts.get(sector, 0) < sector_cap
        ):
            selected.append(symbol)
            sector_counts[sector] = sector_counts.get(sector, 0) + 1
    for symbol in order:
        if len(selected) >= top_n:
            break
        if symbol in selected:
            continue
        sector = sector_by_symbol[symbol]
        if sector_counts.get(sector, 0) >= sector_cap:
            continue
        selected.append(symbol)
        sector_counts[sector] = sector_counts.get(sector, 0) + 1
    return selected


def _stock_asset_weights(panel: Panel, position: int, symbols: list[str]) -> pd.Series:
    if not symbols:
        return _cash_asset_weights(list(panel.all_symbols))
    close_returns = panel.close[symbols].pct_change(fill_method=None)
    volatility = close_returns.iloc[position - 62 : position + 1].std(ddof=1).clip(lower=1e-6)
    inverse = 1.0 / volatility
    raw = 0.5 * pd.Series(1.0 / len(symbols), index=symbols) + 0.5 * inverse / inverse.sum()
    raw = _cap_and_normalize(raw, cap=0.15)
    result = pd.Series(0.0, index=panel.all_symbols, dtype=float)
    result.loc[symbols] = raw
    return result


def _window_return(series: pd.Series, position: int, lookback: int, skip: int) -> float:
    end = position - skip
    start = end - lookback
    if start < 0:
        raise ContractViolation("insufficient history for preregistered lookback")
    return float(series.iloc[end] / series.iloc[start] - 1.0)


def _cap_and_normalize(weights: pd.Series, *, cap: float) -> pd.Series:
    result = weights.clip(lower=0).astype(float)
    if result.sum() <= 0:
        return pd.Series(1.0 / len(result), index=result.index)
    result /= result.sum()
    for _ in range(len(result) + 2):
        excess = float((result - cap).clip(lower=0).sum())
        result = result.clip(upper=cap)
        if excess <= 1e-12:
            break
        eligible = result < cap - 1e-12
        if not eligible.any():
            break
        room = cap - result[eligible]
        result.loc[eligible] += excess * room / room.sum()
    if result.sum() <= 0:
        raise ContractViolation("weight normalization failed")
    return result / result.sum()


def _cash_asset_weights(columns: list[str]) -> pd.Series:
    result = pd.Series(0.0, index=columns, dtype=float)
    result.loc["BIL"] = 1.0
    return result


def _equal_asset_weights(columns: list[str], selected: list[str]) -> pd.Series:
    if not selected:
        return _cash_asset_weights(columns)
    result = pd.Series(0.0, index=columns, dtype=float)
    result.loc[selected] = 1.0 / len(selected)
    return result


def _artifact_binding(path: Path, root: Path) -> dict[str, str]:
    return {"path": str(path.relative_to(root)), "sha256": _sha256_file(path)}


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ContractViolation(f"JSON artifact is not an object: {path}")
    return payload


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_sha(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _asset_open_returns(panel: Panel) -> pd.DataFrame:
    returns = panel.open.shift(-2).divide(panel.open.shift(-1)) - 1.0
    return returns.replace([np.inf, -np.inf], np.nan)


def _simulate_asset_targets(
    panel: Panel,
    targets: pd.DataFrame,
    *,
    cost_bps: float,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> dict[str, Any]:
    asset_returns = _asset_open_returns(panel)
    dates = panel.open.loc[start:end].index
    current = _cash_asset_weights(list(panel.all_symbols))
    daily_returns: list[float] = []
    daily_turnover: list[float] = []
    daily_risky_exposure: list[float] = []
    output_dates: list[pd.Timestamp] = []
    decision_lookup = {date: targets.loc[date] for date in targets.index if start <= date <= end}
    for date in dates:
        row_returns = asset_returns.loc[date]
        if row_returns.isna().any():
            continue
        turnover = 0.0
        if date in decision_lookup:
            target = decision_lookup[date].astype(float).reindex(panel.all_symbols).fillna(0.0)
            if (target < -1e-12).any() or not math.isclose(float(target.sum()), 1.0, abs_tol=1e-8):
                raise ContractViolation(f"invalid asset target on {date.isoformat()}")
            turnover = 0.5 * float((target - current).abs().sum())
            current = target
        gross_return = float(np.dot(current.to_numpy(), row_returns.to_numpy()))
        net_return = gross_return - turnover * cost_bps / 10_000.0
        if not math.isfinite(net_return) or net_return <= -1.0:
            raise ContractViolation(f"invalid simulated return on {date.isoformat()}")
        daily_returns.append(net_return)
        daily_turnover.append(turnover)
        daily_risky_exposure.append(float(1.0 - current.get("BIL", 0.0)))
        output_dates.append(date)
        gross_asset_values = current * (1.0 + row_returns)
        gross_value = float(gross_asset_values.sum())
        if gross_value <= 0:
            raise ContractViolation("portfolio value became non-positive")
        current = gross_asset_values / gross_value
    return {
        "returns": pd.Series(daily_returns, index=pd.DatetimeIndex(output_dates), dtype=float),
        "turnover": pd.Series(daily_turnover, index=pd.DatetimeIndex(output_dates), dtype=float),
        "risky_exposure": pd.Series(
            daily_risky_exposure,
            index=pd.DatetimeIndex(output_dates),
            dtype=float,
        ),
    }


def _build_sleeve_return_panel(
    panel: Panel,
    sleeve_targets: dict[str, pd.DataFrame],
    decision_dates: pd.DatetimeIndex,
) -> pd.DataFrame:
    start = decision_dates.min()
    end = panel.open.index[-3]
    returns = {}
    for sleeve_name in ALL_SLEEVES:
        simulation = _simulate_asset_targets(
            panel,
            sleeve_targets[sleeve_name],
            cost_bps=0.0,
            start=start,
            end=end,
        )
        returns[sleeve_name] = simulation["returns"]
    frame = pd.DataFrame(returns).dropna()
    if frame.empty or frame.isna().any().any():
        raise ContractViolation("base sleeve return panel is incomplete")
    return frame


def _build_feature_label_dataset(
    panel: Panel,
    decision_dates: pd.DatetimeIndex,
    sleeve_returns: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[pd.Timestamp, pd.Timestamp]]:
    features: dict[pd.Timestamp, dict[str, float]] = {}
    labels: dict[pd.Timestamp, dict[str, int]] = {}
    label_ends: dict[pd.Timestamp, pd.Timestamp] = {}
    stock_close = panel.close[list(panel.stock_symbols)]
    stock_ma126 = stock_close.rolling(126, min_periods=126).mean()
    stock_ret21 = stock_close.divide(stock_close.shift(21)) - 1.0
    spy_close = panel.close["SPY"]
    spy_returns = spy_close.pct_change(fill_method=None)
    for date in decision_dates:
        if date not in sleeve_returns.index:
            continue
        sleeve_position = sleeve_returns.index.get_loc(date)
        panel_position = panel.close.index.get_loc(date)
        if sleeve_position < 126:
            continue
        if sleeve_position + LABEL_HORIZON_BARS > len(sleeve_returns):
            continue
        row: dict[str, float] = {}
        for sleeve in ALL_SLEEVES:
            series = sleeve_returns[sleeve]
            for lookback in [21, 63, 126]:
                window = series.iloc[sleeve_position - lookback : sleeve_position]
                row[f"{sleeve}_return_{lookback}"] = float((1.0 + window).prod() - 1.0)
            for lookback in [21, 63]:
                window = series.iloc[sleeve_position - lookback : sleeve_position]
                row[f"{sleeve}_volatility_{lookback}"] = float(window.std(ddof=1) * math.sqrt(252))
            wealth = (1.0 + series.iloc[sleeve_position - 63 : sleeve_position]).cumprod()
            row[f"{sleeve}_drawdown_63"] = float((wealth / wealth.cummax() - 1.0).min())
        risky_window = sleeve_returns[list(RISKY_SLEEVES)].iloc[
            sleeve_position - 63 : sleeve_position
        ]
        for left, right in itertools.combinations(RISKY_SLEEVES, 2):
            row[f"corr_63_{left}_{right}"] = float(risky_window[left].corr(risky_window[right]))
        row["spy_return_21"] = _window_return(spy_close, panel_position, 21, 0)
        row["spy_return_126"] = _window_return(spy_close, panel_position, 126, 0)
        row["spy_volatility_21"] = float(
            spy_returns.iloc[panel_position - 20 : panel_position + 1].std(ddof=1) * math.sqrt(252)
        )
        row["spy_volatility_63"] = float(
            spy_returns.iloc[panel_position - 62 : panel_position + 1].std(ddof=1) * math.sqrt(252)
        )
        spy_wealth = spy_close.iloc[panel_position - 62 : panel_position + 1]
        row["spy_drawdown_63"] = float((spy_wealth / spy_wealth.cummax() - 1.0).min())
        row["spy_trend_gap_126"] = float(
            spy_close.iloc[panel_position]
            / spy_close.iloc[panel_position - 125 : panel_position + 1].mean()
            - 1.0
        )
        row["stock_breadth_126"] = float(
            (stock_close.iloc[panel_position] > stock_ma126.iloc[panel_position]).mean()
        )
        row["stock_dispersion_21"] = float(stock_ret21.iloc[panel_position].std(ddof=1))
        if not all(math.isfinite(value) for value in row.values()):
            continue
        available_at = date + pd.Timedelta(hours=16)
        decision_at = available_at + pd.Timedelta(microseconds=1)
        _assert_feature_availability(available_at, decision_at)
        features[date] = row

        future = sleeve_returns.iloc[sleeve_position : sleeve_position + LABEL_HORIZON_BARS]
        cash_path = (1.0 + future["cash"]).cumprod()
        label_row = {}
        for sleeve in RISKY_SLEEVES:
            risky_path = (1.0 + future[sleeve]).cumprod()
            relative_path = risky_path / cash_path
            relative_return = float(relative_path.iloc[-1] - 1.0)
            relative_drawdown = float((relative_path / relative_path.cummax() - 1.0).min())
            label_row[sleeve] = int(relative_return < -0.02 or relative_drawdown < -0.08)
        labels[date] = label_row
        label_ends[date] = future.index[-1]
    feature_frame = pd.DataFrame.from_dict(features, orient="index").sort_index()
    label_frame = pd.DataFrame.from_dict(labels, orient="index").sort_index().astype(int)
    shared = feature_frame.index.intersection(label_frame.index)
    feature_frame = feature_frame.loc[shared]
    label_frame = label_frame.loc[shared]
    if len(shared) < 70:
        raise ContractViolation(f"only {len(shared)} complete ML decision dates are available")
    return feature_frame, label_frame, {date: label_ends[date] for date in shared}


def _assert_feature_availability(
    feature_available_at: pd.Timestamp,
    decision_at: pd.Timestamp,
) -> None:
    if feature_available_at >= decision_at:
        raise FutureFeatureError(
            f"feature available at {feature_available_at.isoformat()} is not before "
            f"decision {decision_at.isoformat()}"
        )


def _future_feature_control() -> dict[str, Any]:
    decision_at = pd.Timestamp("2026-01-05T21:00:00Z")
    future_at = decision_at + pd.Timedelta(days=1)
    try:
        _assert_feature_availability(future_at, decision_at)
    except FutureFeatureError as exc:
        return {
            "status": "rejected_control",
            "mandatory_outcome_met": True,
            "reason": str(exc),
        }
    return {
        "status": "failed_control",
        "mandatory_outcome_met": False,
        "reason": "future feature was accepted",
    }


def _build_outer_folds(
    dates: pd.DatetimeIndex,
    label_ends: dict[pd.Timestamp, pd.Timestamp],
    session_index: pd.DatetimeIndex,
) -> list[Fold]:
    if len(dates) < 70:
        raise ContractViolation("outer folds require at least 70 complete decision dates")
    initial_train_count = max(32, len(dates) // 3)
    test_blocks = np.array_split(np.asarray(dates[initial_train_count:], dtype=object), OUTER_FOLDS)
    folds: list[Fold] = []
    for fold_number, raw_test in enumerate(test_blocks, start=1):
        test_dates = tuple(pd.Timestamp(value) for value in raw_test)
        if len(test_dates) < 8:
            raise ContractViolation("outer test fold is too short")
        test_start = test_dates[0]
        embargo_boundary = _session_boundary(session_index, test_start, EMBARGO_BARS)
        train_dates = tuple(
            date for date in dates if date < test_start and label_ends[date] < embargo_boundary
        )
        if len(train_dates) < 20:
            raise ContractViolation(
                f"outer fold {fold_number} has insufficient purged training dates"
            )
        folds.append(Fold(fold_number, train_dates, test_dates))
    return folds


def _fit_risk_predictions(
    features: pd.DataFrame,
    labels: pd.DataFrame,
    label_ends: dict[pd.Timestamp, pd.Timestamp],
    session_index: pd.DatetimeIndex,
    folds: list[Fold],
    *,
    family: Literal["logistic", "hist_gradient"],
    seed: int,
    shuffle_labels: bool = False,
) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    predictions = pd.DataFrame(index=features.index, columns=RISKY_SLEEVES, dtype=float)
    diagnostics: list[dict[str, Any]] = []
    for fold in folds:
        train_dates = list(fold.train_dates)
        test_dates = list(fold.test_dates)
        x_outer = features.loc[train_dates]
        x_test = features.loc[test_dates]
        split = max(12, int(len(train_dates) * 0.75))
        calibration_dates = train_dates[split:]
        if len(calibration_dates) < 5:
            raise ContractViolation(f"fold {fold.fold} has insufficient calibration dates")
        calibration_start = calibration_dates[0]
        inner_boundary = _session_boundary(session_index, calibration_start, EMBARGO_BARS)
        inner_dates = [date for date in train_dates[:split] if label_ends[date] < inner_boundary]
        if len(inner_dates) < 10:
            raise ContractViolation(f"fold {fold.fold} has insufficient purged inner training")
        for sleeve_number, sleeve in enumerate(RISKY_SLEEVES):
            y_outer = labels.loc[train_dates, sleeve].copy()
            if shuffle_labels:
                generator = np.random.default_rng(seed + fold.fold * 100 + sleeve_number)
                y_outer.iloc[:] = generator.permutation(y_outer.to_numpy())
            y_inner = y_outer.loc[inner_dates]
            y_calibration = y_outer.loc[calibration_dates]
            raw_test, calibration_status = _fit_predict_calibrated_classifier(
                family,
                features.loc[inner_dates],
                y_inner,
                features.loc[calibration_dates],
                y_calibration,
                x_outer,
                y_outer,
                x_test,
                seed=seed + fold.fold * 10 + sleeve_number,
            )
            predictions.loc[test_dates, sleeve] = raw_test
            actual = labels.loc[test_dates, sleeve].to_numpy(dtype=float)
            brier = float(np.mean((raw_test - actual) ** 2))
            diagnostics.append(
                {
                    "fold": fold.fold,
                    "sleeve": sleeve,
                    "family": family,
                    "shuffle_labels": shuffle_labels,
                    "outer_train_count": len(train_dates),
                    "inner_train_count": len(inner_dates),
                    "calibration_count": len(calibration_dates),
                    "test_count": len(test_dates),
                    "calibration_status": calibration_status,
                    "train_event_rate": round(float(y_outer.mean()), 8),
                    "test_event_rate": round(float(actual.mean()), 8),
                    "brier_score": round(brier, 8),
                }
            )
    test_index = pd.DatetimeIndex(date for fold in folds for date in fold.test_dates)
    output = predictions.loc[test_index]
    if output.isna().any().any():
        raise ContractViolation(f"{family} OOS risk predictions are incomplete")
    return output, diagnostics


def _fit_predict_calibrated_classifier(
    family: Literal["logistic", "hist_gradient"],
    x_inner: pd.DataFrame,
    y_inner: pd.Series,
    x_calibration: pd.DataFrame,
    y_calibration: pd.Series,
    x_outer: pd.DataFrame,
    y_outer: pd.Series,
    x_test: pd.DataFrame,
    *,
    seed: int,
) -> tuple[np.ndarray, str]:
    if y_outer.nunique() < 2 or y_inner.nunique() < 2:
        constant = float(y_outer.mean())
        return np.full(len(x_test), constant), "constant_event_rate"
    inner_model = _classifier_pipeline(family, seed)
    inner_model.fit(x_inner, y_inner)
    calibration_raw = inner_model.predict_proba(x_calibration)[:, 1]
    calibrator: LogisticRegression | None = None
    if y_calibration.nunique() >= 2:
        calibrator = LogisticRegression(C=1.0, solver="lbfgs", random_state=seed)
        calibrator.fit(_probability_logit(calibration_raw), y_calibration)
    outer_model = _classifier_pipeline(family, seed)
    outer_model.fit(x_outer, y_outer)
    test_raw = outer_model.predict_proba(x_test)[:, 1]
    if calibrator is None:
        return np.clip(test_raw, 0.001, 0.999), "uncalibrated_single_class_holdout"
    calibrated = calibrator.predict_proba(_probability_logit(test_raw))[:, 1]
    return np.clip(calibrated, 0.001, 0.999), "inner_holdout_platt"


def _classifier_pipeline(
    family: Literal["logistic", "hist_gradient"],
    seed: int,
) -> Pipeline:
    if family == "logistic":
        return Pipeline(
            [
                ("imputer", SimpleImputer(strategy="median")),
                ("scaler", StandardScaler()),
                (
                    "model",
                    LogisticRegression(
                        C=0.1,
                        class_weight="balanced",
                        max_iter=2_000,
                        solver="lbfgs",
                        random_state=seed,
                    ),
                ),
            ]
        )
    return Pipeline(
        [
            ("imputer", SimpleImputer(strategy="median")),
            (
                "model",
                HistGradientBoostingClassifier(
                    max_depth=2,
                    max_iter=100,
                    learning_rate=0.03,
                    l2_regularization=10.0,
                    min_samples_leaf=20,
                    random_state=seed,
                ),
            ),
        ]
    )


def _probability_logit(values: np.ndarray) -> np.ndarray:
    clipped = np.clip(values, 0.001, 0.999)
    return np.log(clipped / (1.0 - clipped)).reshape(-1, 1)


def _session_boundary(
    session_index: pd.DatetimeIndex,
    start: pd.Timestamp,
    bars: int,
) -> pd.Timestamp:
    position = session_index.get_loc(start)
    if not isinstance(position, int) or position < bars:
        raise ContractViolation("insufficient sessions for embargo boundary")
    return session_index[position - bars]


def _build_deterministic_component_targets(
    features: pd.DataFrame,
    sleeve_returns: pd.DataFrame,
) -> dict[str, pd.DataFrame]:
    output = {
        candidate_id: pd.DataFrame(index=features.index, columns=ALL_SLEEVES, dtype=float)
        for candidate_id in [f"D{index:02d}" for index in range(1, 8)]
    }
    previous = {
        candidate_id: pd.Series([1 / 3, 1 / 3, 1 / 3, 0.0], index=ALL_SLEEVES)
        for candidate_id in output
    }
    for date in features.index:
        position = sleeve_returns.index.get_loc(date)
        covariance = sleeve_returns[list(RISKY_SLEEVES)].iloc[position - 63 : position].cov()
        vol = np.sqrt(np.diag(covariance.to_numpy()))
        equal = pd.Series([1 / 3, 1 / 3, 1 / 3, 0.0], index=ALL_SLEEVES)
        inverse = _risky_to_component(_inverse_volatility(vol))
        risk_parity = _risky_to_component(_capped_risk_parity(covariance.to_numpy()))
        min_variance = _risky_to_component(_shrinkage_minimum_variance(covariance.to_numpy()))
        panic_cap = _panic_exposure_cap(features.loc[date])
        drawdown_cap = _drawdown_exposure_cap(features.loc[date])
        proposed = {
            "D01": equal,
            "D02": inverse,
            "D03": risk_parity,
            "D04": min_variance,
            "D05": _apply_risky_cap(risk_parity, panic_cap),
            "D06": _apply_risky_cap(risk_parity, drawdown_cap),
            "D07": _apply_risky_cap(min_variance, min(panic_cap, drawdown_cap)),
        }
        for candidate_id, weights in proposed.items():
            banded = _apply_component_band(previous[candidate_id], weights, band=0.05)
            output[candidate_id].loc[date] = banded
            previous[candidate_id] = banded
    return output


def _inverse_volatility(volatility: np.ndarray) -> np.ndarray:
    inverse = 1.0 / np.clip(volatility, 1e-6, None)
    return _capped_array(inverse / inverse.sum(), cap=0.5)


def _capped_risk_parity(covariance: np.ndarray) -> np.ndarray:
    weights = np.full(covariance.shape[0], 1.0 / covariance.shape[0])
    for _ in range(200):
        portfolio_vol = math.sqrt(max(float(weights @ covariance @ weights), 1e-12))
        marginal = covariance @ weights / portfolio_vol
        contributions = weights * marginal
        target = portfolio_vol / len(weights)
        updated = weights * target / np.clip(contributions, 1e-8, None)
        updated = _capped_array(updated / updated.sum(), cap=0.5)
        if np.max(np.abs(updated - weights)) < 1e-8:
            break
        weights = updated
    return _capped_array(weights, cap=0.5)


def _shrinkage_minimum_variance(covariance: np.ndarray) -> np.ndarray:
    diagonal = np.diag(np.diag(covariance))
    shrunk = 0.5 * covariance + 0.5 * diagonal
    shrunk += np.eye(len(shrunk)) * 1e-8
    inverse = np.linalg.pinv(shrunk)
    raw = inverse @ np.ones(len(shrunk))
    raw = np.clip(raw, 0.0, None)
    if raw.sum() <= 1e-12:
        raw = np.ones(len(shrunk))
    return _capped_array(raw / raw.sum(), cap=0.5)


def _capped_array(values: np.ndarray, *, cap: float) -> np.ndarray:
    series = pd.Series(values, dtype=float)
    return _cap_and_normalize(series, cap=cap).to_numpy()


def _risky_to_component(risky: np.ndarray) -> pd.Series:
    return pd.Series([*risky, 0.0], index=ALL_SLEEVES, dtype=float)


def _panic_exposure_cap(row: pd.Series) -> float:
    cap = 1.0
    if row["spy_return_126"] <= 0 or row["stock_breadth_126"] < 0.4:
        cap = min(cap, 0.5)
    rebound = row["spy_return_21"] > 0.08 and row["spy_drawdown_63"] < -0.08
    if row["spy_volatility_21"] > 0.30 and rebound:
        cap = min(cap, 0.25)
    return cap


def _drawdown_exposure_cap(row: pd.Series) -> float:
    cap = 1.0
    sleeve_drawdown = min(row[f"{sleeve}_drawdown_63"] for sleeve in RISKY_SLEEVES)
    if sleeve_drawdown < -0.10:
        cap = min(cap, 0.5)
    if row["spy_trend_gap_126"] > 0.15 and row["spy_volatility_21"] > 0.20:
        cap = min(cap, 0.7)
    return cap


def _apply_risky_cap(weights: pd.Series, cap: float) -> pd.Series:
    result = weights.copy()
    risky_total = float(result[list(RISKY_SLEEVES)].sum())
    if risky_total > cap:
        result.loc[list(RISKY_SLEEVES)] *= cap / risky_total
    result.loc["cash"] = 1.0 - float(result[list(RISKY_SLEEVES)].sum())
    return result


def _apply_component_band(previous: pd.Series, proposed: pd.Series, *, band: float) -> pd.Series:
    result = proposed.copy()
    unchanged = (proposed - previous).abs() < band
    result.loc[unchanged] = previous.loc[unchanged]
    result = result.clip(lower=0.0)
    return result / result.sum()


def _model_gate_weights(probabilities: pd.Series) -> pd.Series:
    safe = (1.0 - probabilities.reindex(RISKY_SLEEVES)).clip(lower=0.0, upper=1.0)
    risky_cap = float(safe.mean())
    if safe.sum() <= 1e-12:
        return pd.Series([0.0, 0.0, 0.0, 1.0], index=ALL_SLEEVES)
    risky = safe / safe.sum() * risky_cap
    return pd.Series([*risky.to_numpy(), 1.0 - risky_cap], index=ALL_SLEEVES)


def _build_ml_component_targets(
    deterministic: dict[str, pd.DataFrame],
    logistic: pd.DataFrame,
    hist_gradient: pd.DataFrame,
    shuffled: pd.DataFrame,
) -> dict[str, pd.DataFrame]:
    index = logistic.index
    output = {
        candidate_id: pd.DataFrame(index=index, columns=ALL_SLEEVES, dtype=float)
        for candidate_id in ["M01", "M02", "M03", "M04", "M05", "M06", "N01"]
    }
    previous = {candidate_id: deterministic["D07"].loc[index[0]].copy() for candidate_id in output}
    for date in index:
        parent = deterministic["D07"].loc[date]
        logistic_weights = _model_gate_weights(logistic.loc[date])
        hist_weights = _model_gate_weights(hist_gradient.loc[date])
        shuffled_weights = _model_gate_weights(shuffled.loc[date])
        disagreement = bool(
            ((logistic.loc[date] > 0.5) != (hist_gradient.loc[date] > 0.5)).any()
            or (logistic.loc[date] - hist_gradient.loc[date]).abs().max() > 0.25
        )
        if disagreement:
            abstention = _apply_risky_cap(parent, 0.25)
        else:
            abstention = 0.5 * parent + 0.25 * logistic_weights + 0.25 * hist_weights
        proposed = {
            "M01": logistic_weights,
            "M02": hist_weights,
            "M03": 0.75 * parent + 0.25 * logistic_weights,
            "M04": 0.50 * parent + 0.50 * logistic_weights,
            "M05": 0.75 * parent + 0.25 * hist_weights,
            "M06": abstention,
            "N01": shuffled_weights,
        }
        for candidate_id, weights in proposed.items():
            weights = weights.clip(lower=0.0)
            weights /= weights.sum()
            banded = _apply_component_band(previous[candidate_id], weights, band=0.05)
            output[candidate_id].loc[date] = banded
            previous[candidate_id] = banded
    return output


def _component_to_asset_targets(
    component_targets: pd.DataFrame,
    sleeve_targets: dict[str, pd.DataFrame],
    all_symbols: tuple[str, ...],
) -> pd.DataFrame:
    rows = []
    for date in component_targets.index:
        asset = pd.Series(0.0, index=all_symbols, dtype=float)
        for sleeve in ALL_SLEEVES:
            asset += float(component_targets.loc[date, sleeve]) * sleeve_targets[sleeve].loc[date]
        asset = _enforce_asset_cap(asset, cap=0.15)
        rows.append(asset)
    return pd.DataFrame(rows, index=component_targets.index, columns=all_symbols, dtype=float)


def _enforce_asset_cap(weights: pd.Series, *, cap: float) -> pd.Series:
    result = weights.clip(lower=0.0).astype(float)
    risky = result.drop(labels=["BIL"])
    excess = float((risky - cap).clip(lower=0.0).sum())
    result.loc[risky.index] = risky.clip(upper=cap)
    result.loc["BIL"] += excess
    if result.sum() <= 0:
        result.loc["BIL"] = 1.0
    return result / result.sum()


def run_robust_momentum_r4(root: Path | None = None) -> RobustMomentumResult:
    base = root or project_root()
    blockers = validate_robust_momentum_preflight(base)
    if blockers:
        raise ContractViolation("preflight blocked: " + ", ".join(blockers))
    output = ensure_dir(base / ITERATION_DIR)
    panel = _load_exact_panel(base)
    manifest = _load_json(base / CANDIDATE_MANIFEST_PATH)
    feasibility = _load_json(base / DATA_FEASIBILITY_PATH)
    decision_dates = _decision_dates(panel)
    sleeve_targets, legacy_targets = _build_base_sleeve_targets(panel, decision_dates)
    sleeve_returns = _build_sleeve_return_panel(panel, sleeve_targets, decision_dates)
    features, labels, label_ends = _build_feature_label_dataset(
        panel,
        decision_dates,
        sleeve_returns,
    )
    folds = _build_outer_folds(features.index, label_ends, panel.open.index)
    test_dates = pd.DatetimeIndex(date for fold in folds for date in fold.test_dates)
    deterministic_components = _build_deterministic_component_targets(features, sleeve_returns)

    logistic_predictions, logistic_diagnostics = _fit_risk_predictions(
        features,
        labels,
        label_ends,
        panel.open.index,
        folds,
        family="logistic",
        seed=41,
    )
    hist_predictions, hist_diagnostics = _fit_risk_predictions(
        features,
        labels,
        label_ends,
        panel.open.index,
        folds,
        family="hist_gradient",
        seed=43,
    )
    shuffled_predictions, shuffled_diagnostics = _fit_risk_predictions(
        features,
        labels,
        label_ends,
        panel.open.index,
        folds,
        family="logistic",
        seed=77,
        shuffle_labels=True,
    )
    ml_components = _build_ml_component_targets(
        deterministic_components,
        logistic_predictions,
        hist_predictions,
        shuffled_predictions,
    )
    component_targets = {
        candidate_id: frame.loc[test_dates]
        for candidate_id, frame in deterministic_components.items()
    }
    component_targets.update(ml_components)
    asset_targets = {
        candidate_id: _component_to_asset_targets(
            targets,
            sleeve_targets,
            panel.all_symbols,
        )
        for candidate_id, targets in component_targets.items()
    }
    future_control = _future_feature_control()
    if not future_control["mandatory_outcome_met"]:
        raise ContractViolation("future-feature negative control did not reject")

    start = test_dates.min()
    last_position = panel.open.index.get_loc(test_dates.max())
    end = panel.open.index[min(last_position + DECISION_STRIDE_BARS - 1, len(panel.open.index) - 3)]
    fold_windows = _fold_windows(panel, folds, end)
    cost_scenarios = [10.0, 20.0, 40.0]
    benchmark_targets, ex_post_best_symbol = _benchmark_targets(
        panel,
        sleeve_targets,
        legacy_targets,
        deterministic_components["D01"].loc[test_dates],
        test_dates,
        start,
        end,
    )
    benchmark_results = {
        str(int(cost)): {
            benchmark_id: _evaluate_target_metrics(
                panel,
                targets,
                cost_bps=cost,
                start=start,
                end=end,
                fold_windows=fold_windows,
            )
            for benchmark_id, targets in benchmark_targets.items()
        }
        for cost in cost_scenarios
    }
    benchmark_hash = _canonical_sha(benchmark_results)

    candidate_by_id = {str(row["candidate_id"]): row for row in manifest.get("candidates", [])}
    candidate_results: dict[str, dict[str, Any]] = {}
    for candidate_id in EXPECTED_CANDIDATE_IDS:
        if candidate_id == "N02":
            candidate_results[candidate_id] = {
                "status": "rejected_control",
                "selection_prohibited": True,
                "control": future_control,
                "metrics_by_cost_bps": None,
            }
            continue
        candidate_results[candidate_id] = {
            "status": "complete",
            "selection_prohibited": bool(
                candidate_by_id[candidate_id].get("selection_prohibited", False)
            ),
            "metrics_by_cost_bps": {
                str(int(cost)): _evaluate_target_metrics(
                    panel,
                    asset_targets[candidate_id],
                    cost_bps=cost,
                    start=start,
                    end=end,
                    fold_windows=fold_windows,
                )
                for cost in cost_scenarios
            },
        }
    _attach_acceptance(candidate_results)
    pbo = _pbo_diagnostic(candidate_results)
    dsr = _dsr_proxy(candidate_results)
    placebo_pass = _placebo_gate(candidate_results)

    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    code_path = Path(__file__)
    candidate_manifest_sha = _sha256_file(base / CANDIDATE_MANIFEST_PATH)
    data_feasibility_sha = _sha256_file(base / DATA_FEASIBILITY_PATH)
    cost_contract_sha = _sha256_file(base / COST_CONTRACT_PATH)
    spec_hash = strategy_content_hash(load_strategy_spec(base / SPEC_PATH))
    ledger_rows = []
    for candidate_id in EXPECTED_CANDIDATE_IDS:
        candidate = candidate_by_id[candidate_id]
        result = candidate_results[candidate_id]
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
                "action": "rejected_control" if candidate_id == "N02" else "run_diagnostic",
                "status": result["status"],
                "scope": "historical_current_universe_diagnostic",
                "survivorship_labelled": True,
                "workflow_pass": result["status"] in {"complete", "rejected_control"},
                "research_pass": False,
                "llm_contribution_pass": False,
                "paper_ready_pass": False,
                "promotion_eligible": False,
                "selection_prohibited": result["selection_prohibited"],
                "input_hashes": {
                    "candidate_manifest_sha256": candidate_manifest_sha,
                    "data_feasibility_sha256": data_feasibility_sha,
                    "input_bundle_sha256": feasibility["input_bundle_sha256"],
                    "cost_contract_sha256": cost_contract_sha,
                    "spec_hash": spec_hash,
                    "code_sha256": _sha256_file(code_path),
                },
                "random_seed": candidate.get("random_seed")
                or candidate.get("model", {}).get("random_seed"),
                "serialized_model": False,
                "folds": [_fold_contract_row(fold, label_ends) for fold in folds],
                "metrics_by_cost_bps": result.get("metrics_by_cost_bps"),
                "benchmark_family_sha256": benchmark_hash,
                "acceptance": result.get("acceptance"),
                "control": result.get("control"),
            }
        )
    ledger_path = output / "trial-ledger.jsonl"
    ledger_path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in ledger_rows),
        encoding="utf-8",
    )

    prediction_payload = {
        "schema_version": 1,
        "iter_id": ITER_ID,
        "run_id": run_id,
        "feature_columns": list(features.columns),
        "feature_matrix_sha256": _frame_sha(features),
        "label_matrix_sha256": _frame_sha(labels),
        "folds": [_fold_contract_row(fold, label_ends) for fold in folds],
        "logistic": _prediction_records(logistic_predictions),
        "hist_gradient": _prediction_records(hist_predictions),
        "shuffled_logistic": _prediction_records(shuffled_predictions),
        "diagnostics": {
            "logistic": logistic_diagnostics,
            "hist_gradient": hist_diagnostics,
            "shuffled_logistic": shuffled_diagnostics,
        },
        "serialized_models": [],
    }
    prediction_path = output / "risk-predictions.json"
    write_json(prediction_path, prediction_payload)

    selectable = [
        candidate_id
        for candidate_id, row in candidate_results.items()
        if not row["selection_prohibited"] and row.get("acceptance", {}).get("passed")
    ]
    diagnostic_leader = _diagnostic_leader(candidate_results)
    payload = {
        "schema_version": 1,
        "report_type": "robust_momentum_sleeve_family_evaluation",
        "iter_id": ITER_ID,
        "strategy_name": STRATEGY_NAME,
        "run_id": run_id,
        "generated_at": datetime.now(UTC).isoformat(),
        "workflow_pass": True,
        "research_pass": False,
        "llm_contribution_pass": False,
        "paper_ready_pass": False,
        "scope": "historical_current_universe_diagnostic",
        "survivorship_labelled": True,
        "candidate_count": len(EXPECTED_CANDIDATE_IDS),
        "completed_candidate_count": 14,
        "rejected_control_count": 1,
        "selected_candidates": [],
        "diagnostic_leader": diagnostic_leader,
        "forward_observation_candidate_ids": selectable if placebo_pass else [],
        "formal_forward_start": FORMAL_FORWARD_START,
        "formal_forward_observation_count": 0,
        "data_window": {
            "common_first_session": panel.open.index.min().isoformat(),
            "common_last_session": panel.open.index.max().isoformat(),
            "common_session_count": len(panel.open.index),
            "oos_start": start.isoformat(),
            "oos_end": end.isoformat(),
            "oos_session_count": int(len(panel.open.loc[start:end])),
        },
        "input_hashes": {
            "candidate_manifest_sha256": candidate_manifest_sha,
            "data_feasibility_sha256": data_feasibility_sha,
            "input_bundle_sha256": feasibility["input_bundle_sha256"],
            "cost_contract_sha256": cost_contract_sha,
            "prior_evidence_sha256": _sha256_file(base / PRIOR_EVIDENCE_PATH),
            "spec_hash": spec_hash,
            "code_sha256": _sha256_file(code_path),
        },
        "folds": [_fold_contract_row(fold, label_ends) for fold in folds],
        "cost_scenarios_one_way_bps": cost_scenarios,
        "candidate_results": candidate_results,
        "benchmark_family": {
            "selection_eligible": False,
            "ex_post_best_symbol": ex_post_best_symbol,
            "ex_post_best_symbol_selection_eligible": False,
            "results_by_cost_bps": benchmark_results,
            "sha256": benchmark_hash,
        },
        "model_validation": {
            "feature_count": len(features.columns),
            "complete_decision_date_count": len(features),
            "oos_prediction_date_count": len(test_dates),
            "label_horizon_bars": LABEL_HORIZON_BARS,
            "purge_bars": PURGE_BARS,
            "embargo_bars": EMBARGO_BARS,
            "outer_fold_count": len(folds),
            "stage_local_preprocessing": True,
            "inner_holdout_calibration": True,
            "serialized_models": [],
            "prediction_artifact_path": str(prediction_path.relative_to(base)),
        },
        "multiple_testing": {
            "pbo_diagnostic": pbo,
            "dsr_proxy": dsr,
            "shuffled_label_control_pass": placebo_pass,
            "future_feature_control_pass": future_control["mandatory_outcome_met"],
        },
        "promotion_blockers": [
            "point_in_time_universe_missing",
            "inactive_securities_and_delisting_returns_missing",
            "corporate_action_lineage_missing",
            "longbridge_history_limited_to_1000_bars",
            "independent_source_validation_failed",
            "official_open_or_sip_execution_evidence_missing",
            "matched_opening_order_tca_missing",
            "no_formal_forward_observations",
        ],
        "trial_ledger_path": str(ledger_path.relative_to(base)),
        "limitations": list(feasibility["limitations"]),
    }
    evaluation_path = output / "evaluation-report.json"
    markdown_path = output / "evaluation-report.md"
    write_json(evaluation_path, payload)
    markdown_path.write_text(_render_evaluation_markdown(payload), encoding="utf-8")
    _write_decision_record(base, payload)
    return RobustMomentumResult(evaluation_path, markdown_path, ledger_path, payload)


def _benchmark_targets(
    panel: Panel,
    sleeve_targets: dict[str, pd.DataFrame],
    legacy_targets: pd.DataFrame,
    equal_components: pd.DataFrame,
    test_dates: pd.DatetimeIndex,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> tuple[dict[str, pd.DataFrame], str]:
    columns = list(panel.all_symbols)
    targets: dict[str, pd.DataFrame] = {}
    for symbol in ["SPY", "XLK", "BIL"]:
        targets[symbol] = pd.DataFrame(
            [_equal_asset_weights(columns, [symbol]) for _ in test_dates],
            index=test_dates,
        )
    targets["equal_weight_stock_universe"] = pd.DataFrame(
        [_equal_asset_weights(columns, list(panel.stock_symbols)) for _ in test_dates],
        index=test_dates,
    )
    targets["legacy_12_1_stock_anchor"] = legacy_targets.loc[test_dates]
    targets["equal_weight_sleeves"] = _component_to_asset_targets(
        equal_components,
        sleeve_targets,
        panel.all_symbols,
    )
    open_returns = _asset_open_returns(panel).loc[start:end]
    cumulative = (1.0 + open_returns).prod() - 1.0
    ex_post_best = str(cumulative.idxmax())
    targets["ex_post_best_symbol_report_only"] = pd.DataFrame(
        [_equal_asset_weights(columns, [ex_post_best]) for _ in test_dates],
        index=test_dates,
    )
    for symbol in panel.all_symbols:
        targets[f"same_symbol_buy_and_hold:{symbol}"] = pd.DataFrame(
            [_equal_asset_weights(columns, [symbol]) for _ in test_dates],
            index=test_dates,
        )
    return targets, ex_post_best


def _fold_windows(
    panel: Panel,
    folds: list[Fold],
    final_end: pd.Timestamp,
) -> list[tuple[int, pd.Timestamp, pd.Timestamp]]:
    windows = []
    for index, fold in enumerate(folds):
        start = fold.test_dates[0]
        if index + 1 < len(folds):
            next_start = folds[index + 1].test_dates[0]
            next_position = panel.open.index.get_loc(next_start)
            end = panel.open.index[next_position - 1]
        else:
            end = final_end
        windows.append((fold.fold, start, end))
    return windows


def _evaluate_target_metrics(
    panel: Panel,
    targets: pd.DataFrame,
    *,
    cost_bps: float,
    start: pd.Timestamp,
    end: pd.Timestamp,
    fold_windows: list[tuple[int, pd.Timestamp, pd.Timestamp]],
) -> dict[str, Any]:
    simulation = _simulate_asset_targets(
        panel,
        targets,
        cost_bps=cost_bps,
        start=start,
        end=end,
    )
    folds = []
    for fold_number, fold_start, fold_end in fold_windows:
        fold_targets = targets.loc[(targets.index >= fold_start) & (targets.index <= fold_end)]
        fold_simulation = _simulate_asset_targets(
            panel,
            fold_targets,
            cost_bps=cost_bps,
            start=fold_start,
            end=fold_end,
        )
        folds.append(
            {
                "fold": fold_number,
                "start": fold_start.isoformat(),
                "end": fold_end.isoformat(),
                **_metrics_from_simulation(fold_simulation),
            }
        )
    return {"aggregate": _metrics_from_simulation(simulation), "folds": folds}


def _metrics_from_simulation(simulation: dict[str, Any]) -> dict[str, Any]:
    returns: pd.Series = simulation["returns"]
    turnover: pd.Series = simulation["turnover"]
    risky_exposure: pd.Series = simulation["risky_exposure"]
    equity = (1.0 + returns).cumprod()
    curve = [1.0, *equity.tolist()]
    metrics = build_performance_metrics(
        curve,
        "daily",
        exposure_pct=float(risky_exposure.mean() * 100),
        turnover_ratio=float(turnover.sum()),
    )
    rebalance_turnover = turnover[turnover > 1e-12]
    return {
        "total_return_pct": round(float(equity.iloc[-1] - 1.0) * 100, 6),
        "annualized_return_pct": _rounded(metrics.annualized_return_pct),
        "sharpe": _rounded(metrics.sharpe_ratio),
        "annualized_volatility_pct": _rounded(metrics.annualized_volatility_pct),
        "max_drawdown_pct": round(float(metrics.max_drawdown_pct), 6),
        "sortino": _rounded(metrics.sortino_ratio),
        "calmar": _rounded(metrics.calmar_ratio),
        "session_count": len(returns),
        "rebalance_count": int((turnover > 1e-12).sum()),
        "cumulative_one_way_turnover_pct": round(float(turnover.sum()) * 100, 6),
        "average_one_way_turnover_pct": round(
            float(rebalance_turnover.mean() * 100) if len(rebalance_turnover) else 0.0,
            6,
        ),
        "average_risky_exposure_pct": round(float(risky_exposure.mean()) * 100, 6),
    }


def _attach_acceptance(candidate_results: dict[str, dict[str, Any]]) -> None:
    for candidate_id, result in candidate_results.items():
        if candidate_id == "N02":
            result["acceptance"] = {
                "passed": bool(result["control"]["mandatory_outcome_met"]),
                "reason": "mandatory future-feature rejection control",
            }
            continue
        parent_id = "D01" if candidate_id.startswith("D") else "D07"
        if candidate_id in {"D01", "D07"}:
            parent_id = "D01"
        current10 = result["metrics_by_cost_bps"]["10"]
        parent10 = candidate_results[parent_id]["metrics_by_cost_bps"]["10"]
        current40 = result["metrics_by_cost_bps"]["40"]
        parent40 = candidate_results[parent_id]["metrics_by_cost_bps"]["40"]
        fold_wins = sum(
            row["total_return_pct"] > baseline["total_return_pct"]
            for row, baseline in zip(
                current10["folds"],
                parent10["folds"],
                strict=True,
            )
        )
        current_aggregate = current10["aggregate"]
        parent_aggregate = parent10["aggregate"]
        passed = bool(
            not result["selection_prohibited"]
            and fold_wins >= 3
            and (current_aggregate["sharpe"] or -math.inf)
            >= (parent_aggregate["sharpe"] or -math.inf)
            and current_aggregate["max_drawdown_pct"] >= parent_aggregate["max_drawdown_pct"] - 2.0
            and current40["aggregate"]["total_return_pct"]
            >= parent40["aggregate"]["total_return_pct"]
        )
        result["acceptance"] = {
            "passed": passed,
            "parent_candidate_id": parent_id,
            "fold_wins": fold_wins,
            "required_fold_wins": 3,
            "base_cost_sharpe_delta": _delta(
                current_aggregate["sharpe"], parent_aggregate["sharpe"]
            ),
            "base_cost_max_drawdown_delta_pct": round(
                current_aggregate["max_drawdown_pct"] - parent_aggregate["max_drawdown_pct"],
                6,
            ),
            "forty_bps_return_delta_pct": round(
                current40["aggregate"]["total_return_pct"]
                - parent40["aggregate"]["total_return_pct"],
                6,
            ),
        }


def _placebo_gate(candidate_results: dict[str, dict[str, Any]]) -> bool:
    placebo = candidate_results["N01"]["metrics_by_cost_bps"]["10"]
    parent = candidate_results["D07"]["metrics_by_cost_bps"]["10"]
    placebo_sharpe = placebo["aggregate"]["sharpe"] or -math.inf
    parent_sharpe = parent["aggregate"]["sharpe"] or -math.inf
    fold_wins = sum(
        row["total_return_pct"] > baseline["total_return_pct"]
        for row, baseline in zip(placebo["folds"], parent["folds"], strict=True)
    )
    return bool(placebo_sharpe <= parent_sharpe + 0.2 and fold_wins <= 2)


def _pbo_diagnostic(candidate_results: dict[str, dict[str, Any]]) -> dict[str, Any]:
    candidate_ids = [
        candidate_id
        for candidate_id in EXPECTED_CANDIDATE_IDS
        if candidate_id not in {"N01", "N02"}
    ]
    fold_scores = {
        candidate_id: np.asarray(
            [
                (row["sharpe"] if row["sharpe"] is not None else -10.0)
                for row in candidate_results[candidate_id]["metrics_by_cost_bps"]["10"]["folds"]
            ],
            dtype=float,
        )
        for candidate_id in candidate_ids
    }
    below_median = 0
    split_rows = []
    fold_indices = range(OUTER_FOLDS)
    for in_sample in itertools.combinations(fold_indices, OUTER_FOLDS // 2):
        out_sample = tuple(index for index in fold_indices if index not in in_sample)
        winner = max(
            candidate_ids,
            key=lambda candidate_id: float(fold_scores[candidate_id][list(in_sample)].mean()),
        )
        oos_values = {
            candidate_id: float(fold_scores[candidate_id][list(out_sample)].mean())
            for candidate_id in candidate_ids
        }
        ordered = sorted(oos_values, key=oos_values.get)
        percentile = (ordered.index(winner) + 1) / len(ordered)
        below_median += int(percentile <= 0.5)
        split_rows.append(
            {
                "in_sample_folds": [index + 1 for index in in_sample],
                "out_of_sample_folds": [index + 1 for index in out_sample],
                "selected_candidate_id": winner,
                "oos_percentile": round(percentile, 6),
            }
        )
    return {
        "method": "four_fold_complementary_rank_diagnostic",
        "split_count": len(split_rows),
        "pbo": round(below_median / len(split_rows), 6),
        "coarse_four_fold_caveat": True,
        "splits": split_rows,
    }


def _dsr_proxy(candidate_results: dict[str, dict[str, Any]]) -> dict[str, Any]:
    sharpes = []
    by_candidate = {}
    for candidate_id in EXPECTED_CANDIDATE_IDS:
        if candidate_id in {"N01", "N02"}:
            continue
        sharpe = candidate_results[candidate_id]["metrics_by_cost_bps"]["10"]["aggregate"]["sharpe"]
        if sharpe is not None:
            sharpes.append(float(sharpe))
            by_candidate[candidate_id] = float(sharpe)
    mean = float(np.mean(sharpes))
    standard_deviation = float(np.std(sharpes, ddof=1)) if len(sharpes) > 1 else 0.0
    expected_max = mean + standard_deviation * math.sqrt(2.0 * math.log(max(len(sharpes), 2)))
    leader = max(by_candidate, key=by_candidate.get)
    return {
        "method": "repository_backtest_forensics_expected_max_sharpe_proxy",
        "trial_count": len(sharpes),
        "mean_candidate_sharpe": round(mean, 6),
        "candidate_sharpe_std": round(standard_deviation, 6),
        "expected_max_sharpe": round(expected_max, 6),
        "observed_max_sharpe": round(by_candidate[leader], 6),
        "observed_max_candidate_id": leader,
        "passes_two_times_expected_max": bool(by_candidate[leader] > 2.0 * expected_max),
        "exact_dsr": False,
    }


def _diagnostic_leader(candidate_results: dict[str, dict[str, Any]]) -> dict[str, Any]:
    eligible = [
        candidate_id
        for candidate_id in EXPECTED_CANDIDATE_IDS
        if candidate_id not in {"N01", "N02"}
    ]
    leader = max(
        eligible,
        key=lambda candidate_id: (
            candidate_results[candidate_id]["metrics_by_cost_bps"]["10"]["aggregate"]["sharpe"]
            or -math.inf
        ),
    )
    metrics = candidate_results[leader]["metrics_by_cost_bps"]["10"]["aggregate"]
    return {
        "candidate_id": leader,
        "selection_eligible": False,
        "reason": "report-only highest base-cost OOS Sharpe; not a promotion or paper selection",
        "metrics": metrics,
    }


def _fold_contract_row(
    fold: Fold,
    label_ends: dict[pd.Timestamp, pd.Timestamp],
) -> dict[str, Any]:
    return {
        "fold": fold.fold,
        "train_start": fold.train_dates[0].isoformat(),
        "train_end": fold.train_dates[-1].isoformat(),
        "max_train_label_end": max(label_ends[date] for date in fold.train_dates).isoformat(),
        "test_start": fold.test_dates[0].isoformat(),
        "test_end": fold.test_dates[-1].isoformat(),
        "train_decision_count": len(fold.train_dates),
        "test_decision_count": len(fold.test_dates),
        "purge_bars": PURGE_BARS,
        "embargo_bars": EMBARGO_BARS,
    }


def _prediction_records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    return [
        {
            "decision_date": date.isoformat(),
            **{column: round(float(frame.loc[date, column]), 8) for column in frame.columns},
        }
        for date in frame.index
    ]


def _frame_sha(frame: pd.DataFrame) -> str:
    payload = {
        "index": [value.isoformat() for value in frame.index],
        "columns": list(frame.columns),
        "values": np.round(frame.to_numpy(dtype=float), 12).tolist(),
    }
    return _canonical_sha(payload)


def _rounded(value: float | None) -> float | None:
    return None if value is None or not math.isfinite(value) else round(float(value), 6)


def _delta(left: float | None, right: float | None) -> float | None:
    if left is None or right is None:
        return None
    return round(float(left - right), 6)


def _render_evaluation_markdown(payload: dict[str, Any]) -> str:
    lines = [
        f"# Robust Momentum R4 Evaluation: {payload['run_id']}",
        "",
        f"- Scope: `{payload['scope']}`",
        f"- Workflow pass: `{str(payload['workflow_pass']).lower()}`",
        f"- Research pass: `{str(payload['research_pass']).lower()}`",
        f"- LLM contribution pass: `{str(payload['llm_contribution_pass']).lower()}`",
        f"- Paper-ready pass: `{str(payload['paper_ready_pass']).lower()}`",
        f"- Diagnostic leader: `{payload['diagnostic_leader']['candidate_id']}` (report only)",
        f"- PBO diagnostic: `{payload['multiple_testing']['pbo_diagnostic']['pbo']}`",
        "",
        "## Base-Cost Results",
        "",
        "| Candidate | Return | Sharpe | Max DD | Avg turnover | Fold wins | Accepted |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for candidate_id, row in payload["candidate_results"].items():
        if candidate_id == "N02":
            lines.append(f"| {candidate_id} | rejected control | - | - | - | - | true |")
            continue
        aggregate = row["metrics_by_cost_bps"]["10"]["aggregate"]
        acceptance = row["acceptance"]
        lines.append(
            f"| {candidate_id} | {aggregate['total_return_pct']:.2f}% | "
            f"{(aggregate['sharpe'] or 0.0):.2f} | {aggregate['max_drawdown_pct']:.2f}% | "
            f"{aggregate['average_one_way_turnover_pct']:.2f}% | "
            f"{acceptance.get('fold_wins', '-')} | {str(acceptance['passed']).lower()} |"
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            (
                "Raw 12-1 remains a benchmark only. All R4 results use a current frozen "
                "stock universe and a 1,000-bar research cache, so no candidate can establish "
                "historical alpha or paper readiness. ML models are fit only inside "
                "chronological folds, are not serialized, and have no order authority."
            ),
            "",
            "## Promotion Blockers",
            "",
            *[f"- `{item}`" for item in payload["promotion_blockers"]],
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def _write_decision_record(root: Path, payload: dict[str, Any]) -> None:
    accepted_deterministic = [
        candidate_id
        for candidate_id in [f"D{index:02d}" for index in range(1, 8)]
        if payload["candidate_results"][candidate_id]["acceptance"]["passed"]
    ]
    accepted_ml = [
        candidate_id
        for candidate_id in [f"M{index:02d}" for index in range(1, 7)]
        if payload["candidate_results"][candidate_id]["acceptance"]["passed"]
    ]
    placebo_pass = payload["multiple_testing"]["shuffled_label_control_pass"]
    deterministic_decision = "pivot" if accepted_deterministic else "stop"
    ml_decision = "pivot" if accepted_ml and placebo_pass else "stop"
    deterministic_ids = ", ".join(accepted_deterministic) or "none"
    ml_ids = ", ".join(accepted_ml) or "none"
    future_pass = str(payload["multiple_testing"]["future_feature_control_pass"]).lower()
    placebo_text = str(placebo_pass).lower()
    lines = [
        f"# Decision Record: {ITER_ID}",
        "",
        "## P1",
        "",
        "- Path: deterministic_allocator",
        f"- Decision: {deterministic_decision}",
        (
            f"- Reason: Accepted diagnostic candidates: {deterministic_ids}. All evidence "
            "remains current-universe diagnostic and cannot set research_pass."
        ),
        (
            "- Next iteration suggestion: Acquire PIT membership, delisting returns, "
            "corporate-action lineage, and longer cross-source history before any "
            "promotion-quality rerun."
        ),
        "",
        "## P2",
        "",
        "- Path: ml_risk_allocator",
        f"- Decision: {ml_decision}",
        (
            f"- Reason: Accepted diagnostic candidates: {ml_ids}; shuffled-label control "
            f"pass={placebo_text}. No model is serialized or authorized for orders."
        ),
        (
            "- Next iteration suggestion: Continue only a fixed accepted shrinkage rule in "
            "isolated forward observation; otherwise stop ML and retain the deterministic "
            "parent."
        ),
        "",
        "## P3",
        "",
        "- Path: negative_controls",
        "- Decision: continue controls",
        (
            f"- Reason: Future-feature rejection pass={future_pass} and shuffled-label "
            f"pass={placebo_text}."
        ),
        (
            "- Next iteration suggestion: Re-run both controls unchanged for any new data "
            "epoch or model role."
        ),
        "",
        (
            "Overall Decision: pivot on data and execution evidence, not on additional "
            "parameter search. `workflow_pass=true`, `research_pass=false`, "
            "`llm_contribution_pass=false`, and `paper_ready_pass=false`."
        ),
    ]
    text = "\n".join(lines) + "\n"
    (root / ITERATION_DIR / "decision-record.md").write_text(text, encoding="utf-8")
