from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import ExtraTreesRegressor
from sklearn.linear_model import ElasticNet
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from open_composer.config import ensure_dir, project_root
from open_composer.research.multiasset_momentum import ALL_ETF_SYMBOLS, _load_panels
from open_composer.research.multiasset_momentum_ml import _evaluate_ranking_predictions
from open_composer.storage import write_json

ITER_ID = "mom_multiasset_ai_r2"
OUTPUT_DIR = Path("reports/research/iterations") / ITER_ID
SOURCE_ITER_DIR = Path("reports/research/iterations/mom_multiasset_r1")
HORIZON_BARS = 21
EMBARGO_BARS = 21
TRAIN_STEP_BARS = 5
EVAL_STEP_BARS = 21
CHALLENGE_DATES = 6
TOP_N = 5
RANDOM_SEED = 91
MAX_TRIALS = 24

CORE_FEATURES = (
    "mom_21_rank",
    "mom_63_rank",
    "mom_126_skip21_rank",
    "mom_252_skip21_rank",
    "high_252_rank",
    "vol_21_rank",
    "downside_vol_63_rank",
    "drawdown_63_rank",
    "volume_surprise_21_rank",
    "relative_spy_126_rank",
    "sector_relative_63_rank",
    "trend_consistency_252_rank",
)

MARKET_FEATURES = (
    "market_spy_mom_21",
    "market_spy_mom_63",
    "market_spy_mom_126",
    "market_spy_vol_21",
    "market_spy_drawdown_63",
    "market_cross_sectional_dispersion_21",
)

AI_FORMULAS = {
    "ai_momentum_quality": (
        "mom_126_skip21_rank + high_252_rank - vol_63_rank",
        "Long-horizon momentum confirmed by proximity to highs and penalized for volatility.",
    ),
    "ai_stable_trend": (
        "mom_252_skip21_rank + trend_consistency_252_rank - downside_vol_63_rank",
        "Persistent momentum with downside-risk penalty.",
    ),
    "ai_volume_confirmed_trend": (
        "mom_63_rank + volume_surprise_21_rank + ma_gap_50_rank",
        "Intermediate trend confirmed by participation and moving-average distance.",
    ),
    "ai_residual_breakout": (
        "relative_spy_126_rank + sector_relative_63_rank + high_252_rank",
        "Breakout that remains strong relative to market and sector peers.",
    ),
    "ai_liquidity_adjusted_momentum": (
        "mom_126_skip21_rank - amihud_21_rank - vol_21_rank",
        "Momentum discounted for illiquidity and short-horizon volatility.",
    ),
    "ai_asymmetric_trend": (
        "mom_63_rank + upside_downside_63_rank - downside_vol_21_rank",
        "Trend quality based on upside/downside asymmetry.",
    ),
    "ai_multi_horizon_agreement": (
        "mean(mom_21_rank,mom_63_rank,mom_126_skip21_rank,mom_252_skip21_rank) - dispersion",
        "Consensus across momentum horizons with disagreement penalty.",
    ),
    "ai_rebound_trap": (
        "mom_21_rank - mom_126_skip21_rank - drawdown_63_rank",
        "Short rebound that conflicts with the long trend and remains in drawdown.",
    ),
    "ai_idiosyncratic_strength": (
        "sector_relative_126_rank + relative_spy_126_rank - beta_126_rank",
        "Peer-relative strength with lower market beta dependence.",
    ),
    "ai_trend_efficiency": (
        "ma_gap_100_rank + trend_consistency_126_rank - realized_range_21_rank",
        "Directional progress relative to path noise.",
    ),
    "ai_flow_quality": (
        "signed_volume_21_rank + price_volume_corr_63_rank - volume_volatility_21_rank",
        "Volume flow aligned with price while penalizing unstable activity.",
    ),
    "ai_defensive_momentum": (
        "mom_126_skip21_rank - beta_63_rank - idio_vol_63_rank",
        "Momentum with lower systematic and idiosyncratic risk.",
    ),
    "ai_regime_trend_interaction": (
        "mom_126_skip21_rank * positive(SPY_63) - downside_vol_63_rank * negative(SPY_63)",
        "Trend exposure conditioned on the observable market regime.",
    ),
    "ai_dispersion_opportunity": (
        "sector_relative_63_rank * market_dispersion + high_126_rank",
        "Cross-sectional selection strength when stock dispersion is elevated.",
    ),
    "ai_crowding_risk": (
        "mom_21_rank + volume_surprise_5_rank + high_63_rank - mom_252_skip21_rank",
        "Fast crowded move that lacks long-horizon confirmation.",
    ),
    "ai_recovery_quality": (
        "drawdown_recovery_63_rank + mom_63_rank - downside_vol_21_rank",
        "Recovery from drawdown with improving trend and controlled downside risk.",
    ),
}


@dataclass(frozen=True)
class MultiassetAIResult:
    report_path: Path
    markdown_path: Path
    trial_ledger_path: Path
    factor_proposals_path: Path
    payload: dict[str, Any]


def run_multiasset_momentum_ai(
    root: Path | None = None,
    *,
    cost_bps: float = 10.0,
) -> MultiassetAIResult:
    base = root or project_root()
    output = ensure_dir(base / OUTPUT_DIR)
    manifest_path = base / SOURCE_ITER_DIR / "universe-manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError("complete mom_multiasset_r1 before the AI round")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    stock_symbols = [str(symbol) for symbol in manifest["selected_symbols"]]
    sector_map = {
        str(row["symbol"]): str(row.get("sector") or "Unknown") for row in manifest["selected"]
    }
    data = _load_panels(base, list(dict.fromkeys((*stock_symbols, *ALL_ETF_SYMBOLS))))
    dataset, latest, feature_groups = build_ai_factor_dataset(data, stock_symbols, sector_map)
    factor_proposals = write_factor_proposals(output, feature_groups)
    evaluation_dates = _evaluation_dates(dataset)
    if len(evaluation_dates) < 28:
        raise ValueError("AI round requires at least 28 monthly evaluation dates")
    development_dates = evaluation_dates[:-CHALLENGE_DATES]
    challenge_dates = evaluation_dates[-CHALLENGE_DATES:]
    folds = build_ai_folds(dataset, development_dates)
    if len(folds) != 4:
        raise ValueError("AI round requires exactly four valid chronological folds")

    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    base_trials: list[dict[str, Any]] = []
    oos_predictions: dict[str, pd.DataFrame] = {}
    for spec in base_trial_specs():
        row, predictions = run_base_trial(
            spec,
            folds,
            feature_groups,
            cost_bps=cost_bps,
        )
        base_trials.append({"run_id": run_id, "iter_id": ITER_ID, **row})
        oos_predictions[str(spec["trial_id"])] = predictions

    ensemble_trials = run_ensemble_trials(
        base_trials,
        oos_predictions,
        folds,
        cost_bps=cost_bps,
        run_id=run_id,
    )
    all_trials = [*base_trials, *ensemble_trials]
    if len(all_trials) != MAX_TRIALS:
        raise AssertionError(f"AI round must contain exactly {MAX_TRIALS} trials")
    trial_ledger_path = output / "trial-ledger.jsonl"
    trial_ledger_path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in all_trials),
        encoding="utf-8",
    )

    best_base = max(base_trials, key=_development_score)
    best_ai = max(
        (row for row in base_trials if row["feature_set"] in {"ai_formula", "all_selected"}),
        key=_development_score,
    )
    best_blend = max(ensemble_trials, key=_development_score)
    trial_by_id = {str(row["trial_id"]): row for row in base_trials}
    qualified_ensembles = [row for row in ensemble_trials if row["qualified"]]
    challenge_base_candidates = [best_base, best_ai]
    for ensemble in qualified_ensembles:
        challenge_base_candidates.extend(
            trial_by_id[trial_id]
            for trial_id in ensemble["component_trials"]
            if trial_id in trial_by_id
        )
    challenge_rows, frozen_models = run_historical_challenge(
        dataset,
        latest,
        development_dates,
        challenge_dates,
        feature_groups,
        candidates=challenge_base_candidates,
        ensemble_candidates=qualified_ensembles,
        output=output,
        cost_bps=cost_bps,
    )
    ai_contribution = ai_contribution_assessment(base_trials, challenge_rows)
    contribution_path = output / "ai-contribution-evidence.json"
    write_json(
        contribution_path,
        {
            "report_type": "ai_factor_marginal_lift_and_robustness",
            "iter_id": ITER_ID,
            "generated_at": datetime.now(UTC).isoformat(),
            "single_modality_baseline": "matched_model_core12_features",
            "ai_modality": "static_llm_compiled_formula_features",
            "live_llm_inference": False,
            "marginal_lift": ai_contribution["matched_model_comparisons"],
            "historical_challenge_ai_pass": ai_contribution["historical_challenge_ai_pass"],
            "missing_modality_robustness": {
                "fallback": ai_contribution["missing_ai_factor_fallback"],
                "behavior": "continue with core12 model or deterministic 12-1 weights",
                "broker_writes": False,
            },
            "llm_contribution_pass": ai_contribution["passed"],
            "conclusion": ai_contribution["label"],
        },
    )
    selected_challengers = _selected_forward_challengers(
        best_base,
        best_ai,
        best_blend,
        challenge_rows,
    )
    payload = {
        "report_type": "multiasset_momentum_ai_factor_ml_evaluation",
        "iter_id": ITER_ID,
        "run_id": run_id,
        "generated_at": datetime.now(UTC).isoformat(),
        "workflow_pass": True,
        "research_pass": False,
        "llm_contribution_pass": ai_contribution["passed"],
        "paper_ready_pass": False,
        "data_profile": {
            "provider": "longbridge",
            "feed": "nasdaq_basic",
            "data_as_of": data["data_as_of"],
            "frozen_universe_count": len(stock_symbols),
            "formal_forward_epoch": "2026-07-14T00:00:00+00:00",
            "historical_membership_caveat": True,
        },
        "sample_contract": {
            "weekly_training_rows": len(dataset),
            "weekly_training_dates": int(dataset["decision_date"].nunique()),
            "monthly_evaluation_dates": len(evaluation_dates),
            "development_evaluation_dates": len(development_dates),
            "historical_challenge_dates": len(challenge_dates),
            "horizon_bars": HORIZON_BARS,
            "embargo_bars": EMBARGO_BARS,
            "challenge_is_pristine_lockbox": False,
        },
        "feature_contract": {
            "feature_count": len(feature_groups["all"]),
            "core_count": len(feature_groups["core"]),
            "expanded_quant_count": len(feature_groups["expanded_quant"]),
            "ai_formula_count": len(feature_groups["ai_formula"]),
            "market_feature_count": len(feature_groups["market"]),
            "factor_proposals_path": _relpath(factor_proposals, base),
        },
        "search_space": {
            "candidate_count": len(all_trials),
            "base_model_candidates": len(base_trials),
            "ensemble_role_candidates": len(ensemble_trials),
            "models": sorted({str(row["model_family"]) for row in base_trials}),
            "feature_sets": sorted({str(row["feature_set"]) for row in base_trials}),
        },
        "development_trials": all_trials,
        "historical_challenge": {
            "exposed_by_prior_round": True,
            "dates": challenge_dates,
            "rows": challenge_rows,
        },
        "ai_contribution": ai_contribution,
        "ai_contribution_evidence_path": _relpath(contribution_path, base),
        "selected_forward_challengers": selected_challengers,
        "frozen_models": frozen_models,
        "trial_ledger_path": _relpath(trial_ledger_path, base),
        "limitations": [
            "The current stock universe is survivorship-biased before the 2026-07-14 freeze.",
            (
                "Weekly training rows overlap in their 21-day labels; purge and embargo "
                "reduce leakage but do not create independent market regimes."
            ),
            (
                "The historical challenge was exposed in the previous round and cannot "
                "establish formal promotion evidence."
            ),
            (
                "LLM-generated formulas are static research artifacts; no live LLM call "
                "participates in routing."
            ),
        ],
    }
    report_path = output / "evaluation-report.json"
    markdown_path = output / "evaluation-report.md"
    write_json(report_path, payload)
    markdown_path.write_text(render_ai_markdown(payload), encoding="utf-8")
    return MultiassetAIResult(
        report_path=report_path,
        markdown_path=markdown_path,
        trial_ledger_path=trial_ledger_path,
        factor_proposals_path=factor_proposals,
        payload=payload,
    )


def build_ai_factor_dataset(
    data: dict[str, Any],
    stock_symbols: list[str],
    sector_map: dict[str, str],
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, tuple[str, ...]]]:
    close = data["close"][stock_symbols].shift(1)
    open_prices = data["open"][stock_symbols]
    volume = data["volume"][stock_symbols].shift(1)
    daily = close.pct_change(fill_method=None)
    dollar_volume = close * volume
    spy_close = data["close"]["SPY"].shift(1)
    spy_daily = spy_close.pct_change(fill_method=None)

    raw: dict[str, pd.DataFrame] = {}
    for window in (5, 10, 21, 42, 63, 126, 252):
        raw[f"mom_{window}"] = close.pct_change(window, fill_method=None)
    raw["mom_126_skip21"] = close.shift(21).div(close.shift(126)).sub(1)
    raw["mom_252_skip21"] = close.shift(21).div(close.shift(252)).sub(1)
    raw["reversal_5"] = -raw["mom_5"]
    raw["reversal_21"] = -raw["mom_21"]
    for window in (20, 50, 100, 200):
        raw[f"ma_gap_{window}"] = close.div(
            close.rolling(window, min_periods=max(10, window // 2)).mean()
        ).sub(1)
    for window in (63, 126, 252):
        raw[f"high_{window}"] = close.div(
            close.rolling(window, min_periods=max(40, int(window * 0.7))).max()
        ).sub(1)
    for window in (10, 21, 63, 126):
        raw[f"vol_{window}"] = daily.rolling(window, min_periods=max(8, window // 2)).std()
    for window in (21, 63):
        raw[f"downside_vol_{window}"] = (
            daily.clip(upper=0).rolling(window, min_periods=max(12, window // 2)).std()
        )
    upside = daily.clip(lower=0).rolling(63, min_periods=40).mean()
    downside = daily.clip(upper=0).abs().rolling(63, min_periods=40).mean()
    raw["upside_downside_63"] = upside.div(downside.replace(0, np.nan))
    raw["skew_63"] = daily.rolling(63, min_periods=40).skew()
    for window in (63, 126):
        raw[f"drawdown_{window}"] = close.div(
            close.rolling(window, min_periods=max(40, window // 2)).max()
        ).sub(1)
    raw["drawdown_recovery_63"] = raw["mom_21"] - raw["drawdown_63"]
    monthly = close.pct_change(21, fill_method=None)
    for window in (126, 252):
        raw[f"trend_consistency_{window}"] = monthly.rolling(
            window, min_periods=max(80, int(window * 0.7))
        ).apply(lambda values: float(np.mean(np.asarray(values) > 0)), raw=True)
    raw["realized_range_21"] = daily.abs().rolling(21, min_periods=15).sum()
    raw["volume_surprise_5"] = (
        volume.rolling(5, min_periods=4).mean().div(volume.rolling(63, min_periods=40).mean())
    )
    raw["volume_surprise_21"] = (
        volume.rolling(21, min_periods=15).mean().div(volume.rolling(63, min_periods=40).mean())
    )
    raw["volume_volatility_21"] = (
        volume.pct_change(fill_method=None).rolling(21, min_periods=15).std()
    )
    raw["amihud_21"] = (
        daily.abs().div(dollar_volume.replace(0, np.nan)).rolling(21, min_periods=15).mean()
    )
    raw["amihud_63"] = (
        daily.abs().div(dollar_volume.replace(0, np.nan)).rolling(63, min_periods=40).mean()
    )
    raw["price_volume_corr_21"] = daily.rolling(21, min_periods=15).corr(
        volume.pct_change(fill_method=None)
    )
    raw["price_volume_corr_63"] = daily.rolling(63, min_periods=40).corr(
        volume.pct_change(fill_method=None)
    )
    raw["signed_volume_21"] = (
        (np.sign(daily) * volume)
        .rolling(21, min_periods=15)
        .sum()
        .div(volume.rolling(21, min_periods=15).sum().replace(0, np.nan))
    )
    for window in (21, 63, 126, 252):
        raw[f"relative_spy_{window}"] = close.pct_change(window, fill_method=None).sub(
            spy_close.pct_change(window, fill_method=None), axis=0
        )
    market_var_63 = spy_daily.rolling(63, min_periods=40).var().replace(0, np.nan)
    market_var_126 = spy_daily.rolling(126, min_periods=80).var().replace(0, np.nan)
    raw["beta_63"] = daily.rolling(63, min_periods=40).cov(spy_daily).div(market_var_63, axis=0)
    raw["beta_126"] = daily.rolling(126, min_periods=80).cov(spy_daily).div(market_var_126, axis=0)
    raw["idio_vol_63"] = (
        (daily.sub(raw["beta_63"].mul(spy_daily, axis=0))).rolling(63, min_periods=40).std()
    )
    for window in (21, 63, 126):
        momentum = close.pct_change(window, fill_method=None)
        sector_relative = momentum.copy()
        for sector in sorted(set(sector_map.values())):
            members = [symbol for symbol in stock_symbols if sector_map.get(symbol) == sector]
            if members:
                sector_relative[members] = momentum[members].sub(
                    momentum[members].mean(axis=1), axis=0
                )
        raw[f"sector_relative_{window}"] = sector_relative

    ranked = {f"{name}_rank": frame.rank(axis=1, pct=True) for name, frame in raw.items()}
    ai = _ai_factor_frames(ranked, spy_close, daily)
    market = _market_feature_frames(spy_close, daily, close)
    features = {
        name: frame.reindex(index=close.index, columns=close.columns)
        for name, frame in {**ranked, **ai, **market}.items()
    }
    quant_names = tuple(ranked)
    ai_names = tuple(ai)
    feature_groups = {
        "core": CORE_FEATURES,
        "expanded_quant": quant_names,
        "ai_formula": ai_names,
        "market": tuple(market),
        "all": tuple(features),
    }

    forward_return = open_prices.shift(-HORIZON_BARS).div(open_prices).sub(1)
    forward_excess = forward_return.sub(forward_return.mean(axis=1), axis=0)
    rows = _panel_rows(
        close,
        stock_symbols,
        sector_map,
        features,
        forward_return,
        forward_excess,
    )
    frame = pd.DataFrame(rows).dropna(
        subset=[*CORE_FEATURES, "forward_return_21", "forward_excess_21"]
    )
    frame = frame.replace([np.inf, -np.inf], np.nan).reset_index(drop=True)
    latest_position = _latest_complete_position(features, minimum=len(stock_symbols) // 2)
    latest = _latest_rows(
        close.index[latest_position],
        latest_position,
        stock_symbols,
        sector_map,
        features,
        raw["mom_252_skip21"],
    )
    return frame, latest, feature_groups


def _ai_factor_frames(
    ranked: dict[str, pd.DataFrame],
    spy_close: pd.Series,
    daily: pd.DataFrame,
) -> dict[str, pd.DataFrame]:
    get = ranked.__getitem__
    momentum = pd.concat(
        [
            get("mom_21_rank").stack(),
            get("mom_63_rank").stack(),
            get("mom_126_skip21_rank").stack(),
            get("mom_252_skip21_rank").stack(),
        ],
        axis=1,
    )
    agreement = momentum.mean(axis=1) - momentum.std(axis=1)
    agreement_frame = agreement.unstack()
    spy63 = spy_close.pct_change(63, fill_method=None)
    dispersion = daily.rolling(21, min_periods=15).std().mean(axis=1)
    return {
        "ai_momentum_quality": get("mom_126_skip21_rank")
        + get("high_252_rank")
        - get("vol_63_rank"),
        "ai_stable_trend": get("mom_252_skip21_rank")
        + get("trend_consistency_252_rank")
        - get("downside_vol_63_rank"),
        "ai_volume_confirmed_trend": get("mom_63_rank")
        + get("volume_surprise_21_rank")
        + get("ma_gap_50_rank"),
        "ai_residual_breakout": get("relative_spy_126_rank")
        + get("sector_relative_63_rank")
        + get("high_252_rank"),
        "ai_liquidity_adjusted_momentum": get("mom_126_skip21_rank")
        - get("amihud_21_rank")
        - get("vol_21_rank"),
        "ai_asymmetric_trend": get("mom_63_rank")
        + get("upside_downside_63_rank")
        - get("downside_vol_21_rank"),
        "ai_multi_horizon_agreement": agreement_frame,
        "ai_rebound_trap": get("mom_21_rank")
        - get("mom_126_skip21_rank")
        - get("drawdown_63_rank"),
        "ai_idiosyncratic_strength": get("sector_relative_126_rank")
        + get("relative_spy_126_rank")
        - get("beta_126_rank"),
        "ai_trend_efficiency": get("ma_gap_100_rank")
        + get("trend_consistency_126_rank")
        - get("realized_range_21_rank"),
        "ai_flow_quality": get("signed_volume_21_rank")
        + get("price_volume_corr_63_rank")
        - get("volume_volatility_21_rank"),
        "ai_defensive_momentum": get("mom_126_skip21_rank")
        - get("beta_63_rank")
        - get("idio_vol_63_rank"),
        "ai_regime_trend_interaction": get("mom_126_skip21_rank").mul(
            (spy63 > 0).astype(float), axis=0
        )
        - get("downside_vol_63_rank").mul((spy63 <= 0).astype(float), axis=0),
        "ai_dispersion_opportunity": get("sector_relative_63_rank").mul(
            dispersion.rank(pct=True), axis=0
        )
        + get("high_126_rank"),
        "ai_crowding_risk": get("mom_21_rank")
        + get("volume_surprise_5_rank")
        + get("high_63_rank")
        - get("mom_252_skip21_rank"),
        "ai_recovery_quality": get("drawdown_recovery_63_rank")
        + get("mom_63_rank")
        - get("downside_vol_21_rank"),
    }


def _market_feature_frames(
    spy_close: pd.Series,
    daily: pd.DataFrame,
    close: pd.DataFrame,
) -> dict[str, pd.DataFrame]:
    index = close.index
    columns = close.columns

    def expand(series: pd.Series) -> pd.DataFrame:
        values = np.repeat(series.reindex(index).to_numpy()[:, None], len(columns), axis=1)
        return pd.DataFrame(values, index=index, columns=columns)

    spy_daily = spy_close.pct_change(fill_method=None)
    return {
        "market_spy_mom_21": expand(spy_close.pct_change(21, fill_method=None)),
        "market_spy_mom_63": expand(spy_close.pct_change(63, fill_method=None)),
        "market_spy_mom_126": expand(spy_close.pct_change(126, fill_method=None)),
        "market_spy_vol_21": expand(spy_daily.rolling(21, min_periods=15).std()),
        "market_spy_drawdown_63": expand(
            spy_close.div(spy_close.rolling(63, min_periods=40).max()).sub(1)
        ),
        "market_cross_sectional_dispersion_21": expand(
            daily.rolling(21, min_periods=15).std().mean(axis=1)
        ),
    }


def _panel_rows(
    close: pd.DataFrame,
    symbols: list[str],
    sector_map: dict[str, str],
    features: dict[str, pd.DataFrame],
    forward_return: pd.DataFrame,
    forward_excess: pd.DataFrame,
) -> list[dict[str, Any]]:
    rows = []
    eval_positions = set(range(252, len(close) - HORIZON_BARS, EVAL_STEP_BARS))
    training_positions = set(range(252, len(close) - HORIZON_BARS, TRAIN_STEP_BARS))
    for position in sorted(training_positions | eval_positions):
        timestamp = close.index[position]
        for symbol in symbols:
            row = {
                "decision_date": timestamp.isoformat(),
                "decision_position": position,
                "label_end_position": position + HORIZON_BARS,
                "is_monthly_eval": position in eval_positions,
                "symbol": symbol,
                "sector": sector_map.get(symbol, "Unknown"),
                "forward_return_21": forward_return.at[timestamp, symbol],
                "forward_excess_21": forward_excess.at[timestamp, symbol],
                "baseline_score": features["mom_252_skip21_rank"].at[timestamp, symbol],
            }
            for name, frame in features.items():
                row[name] = frame.at[timestamp, symbol]
            rows.append(row)
    return rows


def _latest_complete_position(
    features: dict[str, pd.DataFrame],
    *,
    minimum: int,
) -> int:
    core = [features[name] for name in CORE_FEATURES]
    complete = core[0].notna().sum(axis=1)
    for frame in core[1:]:
        complete = np.minimum(complete, frame.notna().sum(axis=1))
    valid = complete[complete >= minimum]
    if valid.empty:
        raise ValueError("no current date has enough complete factor rows")
    return int(core[0].index.get_loc(valid.index[-1]))


def _latest_rows(
    timestamp: pd.Timestamp,
    position: int,
    symbols: list[str],
    sector_map: dict[str, str],
    features: dict[str, pd.DataFrame],
    baseline: pd.DataFrame,
) -> pd.DataFrame:
    rows = []
    for symbol in symbols:
        row = {
            "decision_date": timestamp.isoformat(),
            "decision_position": position,
            "symbol": symbol,
            "sector": sector_map.get(symbol, "Unknown"),
            "baseline_score": baseline.at[timestamp, symbol],
        }
        row.update({name: frame.at[timestamp, symbol] for name, frame in features.items()})
        rows.append(row)
    return pd.DataFrame(rows).replace([np.inf, -np.inf], np.nan)


def _evaluation_dates(dataset: pd.DataFrame) -> list[str]:
    return sorted(dataset.loc[dataset["is_monthly_eval"], "decision_date"].unique().tolist())


def build_ai_folds(dataset: pd.DataFrame, development_dates: list[str]) -> list[dict[str, Any]]:
    test_size = max(3, len(development_dates) // 7)
    initial = len(development_dates) - test_size * 4
    if initial < 8:
        test_size = max(2, (len(development_dates) - 8) // 4)
        initial = len(development_dates) - test_size * 4
    folds = []
    for fold in range(4):
        test_dates = development_dates[
            initial + fold * test_size : initial + (fold + 1) * test_size
        ]
        if not test_dates:
            continue
        test = dataset[dataset["decision_date"].isin(test_dates)].copy()
        test = test[test["is_monthly_eval"]].copy()
        test_start = int(test["decision_position"].min())
        cutoff = test_start - EMBARGO_BARS
        train = dataset[dataset["label_end_position"] <= cutoff].copy()
        if train.empty or test.empty:
            continue
        folds.append(
            {
                "fold": fold + 1,
                "train": train,
                "test": test,
                "train_end_position": int(train["decision_position"].max()),
                "test_start_position": test_start,
            }
        )
    return folds


def base_trial_specs() -> list[dict[str, Any]]:
    rows = []
    for family in ("elastic_net", "lightgbm_regression", "lightgbm_lambdarank", "extra_trees"):
        for feature_set in ("core12", "expanded_quant", "ai_formula", "all_selected"):
            rows.append(
                {
                    "trial_id": f"{family}_{feature_set}",
                    "model_family": family,
                    "feature_set": feature_set,
                }
            )
    return rows


def run_base_trial(
    spec: dict[str, Any],
    folds: list[dict[str, Any]],
    feature_groups: dict[str, tuple[str, ...]],
    *,
    cost_bps: float,
) -> tuple[dict[str, Any], pd.DataFrame]:
    fold_rows = []
    predictions = []
    for fold in folds:
        train = fold["train"].copy()
        test = fold["test"].copy()
        selected, selection_evidence = select_fold_features(
            train,
            feature_set=str(spec["feature_set"]),
            feature_groups=feature_groups,
        )
        model = make_ai_estimator(str(spec["model_family"]))
        predicted = fit_predict_ai_model(model, str(spec["model_family"]), train, test, selected)
        baseline = _evaluate_ranking_predictions(test, test["baseline_score"].to_numpy(), cost_bps)
        evaluation = _evaluate_ranking_predictions(test, predicted, cost_bps)
        fold_win = _fold_win(evaluation, baseline)
        fold_rows.append(
            {
                "fold": fold["fold"],
                "fold_win": fold_win,
                "selected_features": selected,
                "selection_evidence": selection_evidence,
                "train_rows": len(train),
                "train_dates": int(train["decision_date"].nunique()),
                "test_dates": int(test["decision_date"].nunique()),
                "train_end_position": fold["train_end_position"],
                "test_start_position": fold["test_start_position"],
                "purge_embargo_gap": (
                    fold["test_start_position"] - int(train["label_end_position"].max())
                ),
                "model": evaluation,
                "baseline": baseline,
            }
        )
        prediction_frame = test[
            [
                "decision_date",
                "decision_position",
                "symbol",
                "sector",
                "forward_return_21",
                "forward_excess_21",
                "baseline_score",
                *MARKET_FEATURES,
            ]
        ].copy()
        prediction_frame["prediction"] = predicted
        prediction_frame["fold"] = fold["fold"]
        predictions.append(prediction_frame)
    stitched = pd.concat(predictions, ignore_index=True)
    aggregate = _evaluate_ranking_predictions(stitched, stitched["prediction"].to_numpy(), cost_bps)
    baseline_aggregate = _evaluate_ranking_predictions(
        stitched, stitched["baseline_score"].to_numpy(), cost_bps
    )
    fold_wins = sum(bool(row["fold_win"]) for row in fold_rows)
    qualified = bool(
        fold_wins >= 3
        and not all(not row["fold_win"] for row in fold_rows[-2:])
        and _aggregate_not_worse(aggregate, baseline_aggregate)
    )
    cost_stress = {
        str(cost): _evaluate_ranking_predictions(
            stitched, stitched["prediction"].to_numpy(), float(cost)
        )
        for cost in (5, 10, 20)
    }
    return (
        {
            **spec,
            "status": "validation_complete",
            "folds": fold_rows,
            "fold_wins": fold_wins,
            "aggregate": aggregate,
            "baseline_aggregate": baseline_aggregate,
            "cost_stress_bps": cost_stress,
            "qualified": qualified,
        },
        stitched,
    )


def select_fold_features(
    train: pd.DataFrame,
    *,
    feature_set: str,
    feature_groups: dict[str, tuple[str, ...]],
) -> tuple[list[str], dict[str, Any]]:
    if feature_set == "core12":
        return list(CORE_FEATURES), {"method": "fixed_core", "candidate_count": len(CORE_FEATURES)}
    if feature_set == "expanded_quant":
        candidates = list(feature_groups["expanded_quant"])
        limit = 24
    elif feature_set == "ai_formula":
        candidates = [*CORE_FEATURES, *feature_groups["ai_formula"]]
        limit = 20
    elif feature_set == "all_selected":
        candidates = [*feature_groups["expanded_quant"], *feature_groups["ai_formula"]]
        limit = 24
    else:
        raise ValueError(f"unsupported feature set: {feature_set}")
    scores = factor_ic_scores(train, candidates)
    ordered = [
        name for name, _ in sorted(scores.items(), key=lambda item: abs(item[1]), reverse=True)
    ]
    selected: list[str] = []
    for name in ordered:
        if len(selected) >= limit:
            break
        if train[name].notna().mean() < 0.8:
            continue
        if selected:
            correlations = train[selected].corrwith(train[name]).abs()
            if bool((correlations > 0.92).any()):
                continue
        selected.append(name)
    for market_feature in MARKET_FEATURES:
        if feature_set == "all_selected" and market_feature not in selected:
            selected.append(market_feature)
    if len(selected) < 8:
        raise ValueError(f"feature selection produced only {len(selected)} features")
    return selected, {
        "method": "train_only_mean_rank_ic_then_correlation_prune",
        "candidate_count": len(candidates),
        "selected_count": len(selected),
        "top_ic": [
            {"feature": name, "mean_rank_ic": round(float(scores[name]), 6)}
            for name in ordered[:10]
        ],
    }


def factor_ic_scores(train: pd.DataFrame, features: list[str]) -> dict[str, float]:
    scores: dict[str, float] = {}
    for feature in features:
        values = []
        for _, group in train.groupby("decision_date", sort=True):
            correlation = group[feature].rank().corr(group["forward_excess_21"].rank())
            if pd.notna(correlation):
                values.append(float(correlation))
        scores[feature] = float(np.mean(values)) if values else 0.0
    return scores


def make_ai_estimator(family: str) -> Any:
    if family == "elastic_net":
        return make_pipeline(
            StandardScaler(),
            ElasticNet(
                alpha=0.002,
                l1_ratio=0.2,
                max_iter=10_000,
                random_state=RANDOM_SEED,
            ),
        )
    if family == "lightgbm_regression":
        from lightgbm import LGBMRegressor

        return LGBMRegressor(
            n_estimators=140,
            learning_rate=0.025,
            num_leaves=7,
            max_depth=3,
            min_child_samples=40,
            colsample_bytree=0.75,
            reg_lambda=2.0,
            random_state=RANDOM_SEED,
            verbosity=-1,
        )
    if family == "lightgbm_lambdarank":
        from lightgbm import LGBMRanker

        return LGBMRanker(
            objective="lambdarank",
            metric="ndcg",
            n_estimators=140,
            learning_rate=0.025,
            num_leaves=7,
            max_depth=3,
            min_child_samples=40,
            colsample_bytree=0.75,
            reg_lambda=2.0,
            random_state=RANDOM_SEED,
            verbosity=-1,
        )
    if family == "extra_trees":
        return ExtraTreesRegressor(
            n_estimators=240,
            max_features=0.65,
            min_samples_leaf=20,
            random_state=RANDOM_SEED,
            n_jobs=-1,
        )
    raise ValueError(f"unsupported model family: {family}")


def fit_predict_ai_model(
    model: Any,
    family: str,
    train: pd.DataFrame,
    test: pd.DataFrame,
    features: list[str],
) -> np.ndarray:
    train_work = train.dropna(subset=[*features, "forward_excess_21"]).copy()
    test_work = test.copy()
    fill_values = train_work[features].median()
    x_train = train_work[features].fillna(fill_values)
    x_test = test_work[features].fillna(fill_values)
    if family == "lightgbm_lambdarank":
        train_work = train_work.sort_values(["decision_date", "symbol"]).reset_index(drop=True)
        x_train = train_work[features].fillna(fill_values)
        relevance = (
            train_work.groupby("decision_date")["forward_excess_21"]
            .rank(pct=True, method="average")
            .mul(4.999)
            .astype(int)
        )
        groups = train_work.groupby("decision_date", sort=True).size().tolist()
        model.fit(x_train, relevance, group=groups)
    else:
        model.fit(x_train, train_work["forward_excess_21"])
    return np.asarray(model.predict(x_test), dtype=float)


def run_ensemble_trials(
    base_trials: list[dict[str, Any]],
    predictions: dict[str, pd.DataFrame],
    folds: list[dict[str, Any]],
    *,
    cost_bps: float,
    run_id: str,
) -> list[dict[str, Any]]:
    ranked_trials = sorted(base_trials, key=_development_score, reverse=True)
    best = ranked_trials[0]
    best_frame = predictions[str(best["trial_id"])].copy()
    top_three = ranked_trials[:3]
    top_frames = [predictions[str(row["trial_id"])] for row in top_three]
    ai_best = next(
        row for row in ranked_trials if row["feature_set"] in {"ai_formula", "all_selected"}
    )
    core_match = next(
        row
        for row in base_trials
        if row["model_family"] == ai_best["model_family"] and row["feature_set"] == "core12"
    )
    definitions: list[tuple[str, str, Any]] = [
        ("blend_rule_model_025", "rule_model_blend", 0.25),
        ("blend_rule_model_050", "rule_model_blend", 0.50),
        ("blend_rule_model_075", "rule_model_blend", 0.75),
        ("ensemble_top3_equal", "model_rank_ensemble", None),
        ("ensemble_ai_core_equal", "ai_core_ensemble", None),
        ("abstain_overlap3", "disagreement_abstention", 3),
        ("abstain_overlap4", "disagreement_abstention", 4),
        ("regime_spy63_positive", "regime_switch", 0.0),
    ]
    rows = []
    for trial_id, role, parameter in definitions:
        frame = best_frame.copy()
        if role == "rule_model_blend":
            frame["score"] = _rank_blend(frame, float(parameter))
        elif role == "model_rank_ensemble":
            frame["score"] = _multi_model_rank_average(top_frames)
        elif role == "ai_core_ensemble":
            frame["score"] = _multi_model_rank_average(
                [predictions[str(ai_best["trial_id"])], predictions[str(core_match["trial_id"])]]
            )
        elif role == "disagreement_abstention":
            frame["score"] = _agreement_score(top_frames, int(parameter))
        else:
            ranked_model = frame.groupby("decision_date")["prediction"].rank(pct=True)
            ranked_base = frame.groupby("decision_date")["baseline_score"].rank(pct=True)
            frame["score"] = np.where(
                frame["market_spy_mom_63"] > 0,
                ranked_model,
                ranked_base,
            )
        aggregate = _evaluate_ranking_predictions(frame, frame["score"].to_numpy(), cost_bps)
        baseline = _evaluate_ranking_predictions(
            frame, frame["baseline_score"].to_numpy(), cost_bps
        )
        fold_rows = []
        for fold in folds:
            part = frame[frame["fold"] == fold["fold"]]
            model_eval = _evaluate_ranking_predictions(part, part["score"].to_numpy(), cost_bps)
            baseline_eval = _evaluate_ranking_predictions(
                part, part["baseline_score"].to_numpy(), cost_bps
            )
            fold_rows.append(
                {
                    "fold": fold["fold"],
                    "fold_win": _fold_win(model_eval, baseline_eval),
                    "model": model_eval,
                    "baseline": baseline_eval,
                }
            )
        fold_wins = sum(bool(row["fold_win"]) for row in fold_rows)
        if role in {"rule_model_blend", "regime_switch"}:
            component_trials = [str(best["trial_id"])]
        elif role == "ai_core_ensemble":
            component_trials = [str(ai_best["trial_id"]), str(core_match["trial_id"])]
        else:
            component_trials = [str(row["trial_id"]) for row in top_three]
        rows.append(
            {
                "run_id": run_id,
                "iter_id": ITER_ID,
                "trial_id": trial_id,
                "model_family": "ensemble_role",
                "feature_set": role,
                "role": role,
                "parameter": parameter,
                "component_trials": component_trials,
                "folds": fold_rows,
                "fold_wins": fold_wins,
                "aggregate": aggregate,
                "baseline_aggregate": baseline,
                "qualified": bool(fold_wins >= 3 and _aggregate_not_worse(aggregate, baseline)),
            }
        )
    return rows


def _rank_blend(frame: pd.DataFrame, alpha: float) -> pd.Series:
    model_rank = frame.groupby("decision_date")["prediction"].rank(pct=True)
    baseline_rank = frame.groupby("decision_date")["baseline_score"].rank(pct=True)
    return baseline_rank * (1 - alpha) + model_rank * alpha


def _multi_model_rank_average(frames: list[pd.DataFrame]) -> pd.Series:
    ranks = [frame.groupby("decision_date")["prediction"].rank(pct=True) for frame in frames]
    return pd.concat(ranks, axis=1).mean(axis=1)


def _agreement_score(frames: list[pd.DataFrame], required_overlap: int) -> pd.Series:
    base = frames[0]
    model_average = _multi_model_rank_average(frames)
    baseline_rank = base.groupby("decision_date")["baseline_score"].rank(pct=True)
    output = baseline_rank.copy()
    for decision_date, group in base.groupby("decision_date", sort=True):
        selections = []
        for frame in frames:
            part = frame[frame["decision_date"] == decision_date]
            selections.append(set(part.nlargest(TOP_N, "prediction")["symbol"]))
        overlap = len(set.intersection(*selections)) if selections else 0
        if overlap >= required_overlap:
            output.loc[group.index] = model_average.loc[group.index]
    return output


def run_historical_challenge(
    dataset: pd.DataFrame,
    latest: pd.DataFrame,
    development_dates: list[str],
    challenge_dates: list[str],
    feature_groups: dict[str, tuple[str, ...]],
    *,
    candidates: list[dict[str, Any]],
    ensemble_candidates: list[dict[str, Any]],
    output: Path,
    cost_bps: float,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    challenge = dataset[
        dataset["decision_date"].isin(challenge_dates) & dataset["is_monthly_eval"]
    ].copy()
    challenge_start = int(challenge["decision_position"].min())
    train = dataset[dataset["label_end_position"] <= challenge_start - EMBARGO_BARS].copy()
    rows = []
    frozen = []
    predictions_by_trial: dict[str, np.ndarray] = {}
    for candidate in _unique_trials(candidates):
        selected, selection = select_fold_features(
            train,
            feature_set=str(candidate["feature_set"]),
            feature_groups=feature_groups,
        )
        model = make_ai_estimator(str(candidate["model_family"]))
        prediction = fit_predict_ai_model(
            model, str(candidate["model_family"]), train, challenge, selected
        )
        predictions_by_trial[str(candidate["trial_id"])] = prediction
        latest_prediction = _predict_with_fitted_model(
            model,
            str(candidate["model_family"]),
            train,
            latest,
            selected,
        )
        evaluation = _evaluate_ranking_predictions(challenge, prediction, cost_bps)
        baseline = _evaluate_ranking_predictions(
            challenge, challenge["baseline_score"].to_numpy(), cost_bps
        )
        passed = bool(_fold_win(evaluation, baseline))
        model_path = ensure_dir(output / "models") / f"{candidate['trial_id']}.joblib"
        joblib.dump(
            {
                "model": model,
                "features": selected,
                "family": candidate["model_family"],
                "fill_values": train[selected].median().to_dict(),
            },
            model_path,
        )
        rows.append(
            {
                "trial_id": candidate["trial_id"],
                "feature_set": candidate["feature_set"],
                "model_family": candidate["model_family"],
                "selected_features": selected,
                "selection_evidence": selection,
                "model": evaluation,
                "baseline": baseline,
                "beats_deterministic_baseline": passed,
            }
        )
        frozen.append(
            {
                "trial_id": candidate["trial_id"],
                "feature_set": candidate["feature_set"],
                "model_family": candidate["model_family"],
                "model_path": _relpath(model_path, project_root()),
                "model_sha256": _sha256_file(model_path),
                "selected_features": selected,
                "latest_decision_date": latest["decision_date"].iloc[0],
                "latest_predictions": _latest_predictions(latest, latest_prediction),
                "status": (
                    "historical_challenge_pass_forward_candidate"
                    if passed and candidate["qualified"]
                    else "diagnostic_shadow"
                ),
            }
        )
    for ensemble in ensemble_candidates:
        component_frames = []
        for trial_id in ensemble["component_trials"]:
            if trial_id not in predictions_by_trial:
                break
            frame = challenge.copy()
            frame["prediction"] = predictions_by_trial[trial_id]
            component_frames.append(frame)
        else:
            score = _ensemble_score(
                component_frames,
                role=str(ensemble["role"]),
                parameter=ensemble.get("parameter"),
            )
            evaluation = _evaluate_ranking_predictions(challenge, score.to_numpy(), cost_bps)
            baseline = _evaluate_ranking_predictions(
                challenge, challenge["baseline_score"].to_numpy(), cost_bps
            )
            rows.append(
                {
                    "trial_id": ensemble["trial_id"],
                    "feature_set": ensemble["feature_set"],
                    "model_family": "ensemble_role",
                    "component_trials": ensemble["component_trials"],
                    "model": evaluation,
                    "baseline": baseline,
                    "beats_deterministic_baseline": _fold_win(evaluation, baseline),
                }
            )
    return rows, frozen


def _ensemble_score(
    frames: list[pd.DataFrame],
    *,
    role: str,
    parameter: Any,
) -> pd.Series:
    base = frames[0]
    if role == "rule_model_blend":
        return _rank_blend(base, float(parameter))
    if role in {"model_rank_ensemble", "ai_core_ensemble"}:
        return _multi_model_rank_average(frames)
    if role == "disagreement_abstention":
        return _agreement_score(frames, int(parameter))
    if role == "regime_switch":
        ranked_model = base.groupby("decision_date")["prediction"].rank(pct=True)
        ranked_base = base.groupby("decision_date")["baseline_score"].rank(pct=True)
        return pd.Series(
            np.where(base["market_spy_mom_63"] > 0, ranked_model, ranked_base),
            index=base.index,
        )
    raise ValueError(f"unsupported ensemble role: {role}")


def _predict_with_fitted_model(
    model: Any,
    family: str,
    train: pd.DataFrame,
    latest: pd.DataFrame,
    features: list[str],
) -> np.ndarray:
    del family
    fill_values = train[features].median()
    valid = latest[features].fillna(fill_values)
    return np.asarray(model.predict(valid), dtype=float)


def ai_contribution_assessment(
    trials: list[dict[str, Any]],
    challenge_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    comparisons = []
    for family in sorted({str(row["model_family"]) for row in trials}):
        core = next(
            row
            for row in trials
            if row["model_family"] == family and row["feature_set"] == "core12"
        )
        ai = max(
            (
                row
                for row in trials
                if row["model_family"] == family
                and row["feature_set"] in {"ai_formula", "all_selected"}
            ),
            key=_development_score,
        )
        ai_wins = sum(
            _matched_fold_better(ai_fold, core_fold)
            for ai_fold, core_fold in zip(ai["folds"], core["folds"], strict=True)
        )
        comparisons.append(
            {
                "model_family": family,
                "ai_trial": ai["trial_id"],
                "core_trial": core["trial_id"],
                "ai_fold_wins_vs_core": ai_wins,
                "ai_aggregate": ai["aggregate"],
                "core_aggregate": core["aggregate"],
                "passed": bool(
                    ai_wins >= 3 and _metrics_better(ai["aggregate"], core["aggregate"])
                ),
            }
        )
    challenge_ai_pass = any(
        bool(row.get("beats_deterministic_baseline"))
        and row.get("feature_set") in {"ai_formula", "all_selected"}
        for row in challenge_rows
    )
    passed = bool(any(row["passed"] for row in comparisons) and challenge_ai_pass)
    return {
        "passed": passed,
        "generated_formula_count": len(AI_FORMULAS),
        "live_llm_inference": False,
        "matched_model_comparisons": comparisons,
        "historical_challenge_ai_pass": challenge_ai_pass,
        "missing_ai_factor_fallback": "core12 matched model or deterministic 12-1",
        "label": "independent_llm_factor_lift" if passed else "no_independent_llm_alpha",
    }


def write_factor_proposals(
    output: Path,
    feature_groups: dict[str, tuple[str, ...]],
) -> Path:
    source_path = project_root() / OUTPUT_DIR / "external-brief.json"
    input_hash = sha256(source_path.read_bytes()).hexdigest() if source_path.exists() else None
    prompt = (
        "Generate bounded point-in-time formula factors for cross-sectional momentum using "
        "only shifted OHLCV, market and sector-relative inputs; no live text signals."
    )
    payload = {
        "report_type": "static_llm_compiled_factor_proposals",
        "generated_at": datetime.now(UTC).isoformat(),
        "generated_by": "codex_offline_research_compiler",
        "live_decision_use": False,
        "input_hash": input_hash,
        "prompt_hash": sha256(prompt.encode()).hexdigest(),
        "feature_groups": {key: list(value) for key, value in feature_groups.items()},
        "proposals": [
            {
                "factor_name": name,
                "formula": formula,
                "economic_intuition": intuition,
                "input_visibility": "index-1_or_earlier",
                "source_refs": [
                    "gu_kelly_xiu_ml_asset_pricing",
                    "qlib_alpha158",
                    "rd_agent_q",
                    "alphabench",
                ],
            }
            for name, (formula, intuition) in AI_FORMULAS.items()
        ],
    }
    path = output / "factor-proposals.json"
    write_json(path, payload)
    return path


def _selected_forward_challengers(
    best_base: dict[str, Any],
    best_ai: dict[str, Any],
    best_blend: dict[str, Any],
    challenge_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    challenge_by_id = {str(row["trial_id"]): row for row in challenge_rows}
    rows = []
    for candidate in _unique_trials([best_base, best_ai, best_blend]):
        challenge = challenge_by_id.get(str(candidate["trial_id"]))
        rows.append(
            {
                "trial_id": candidate["trial_id"],
                "model_family": candidate["model_family"],
                "feature_set": candidate["feature_set"],
                "development_qualified": bool(candidate["qualified"]),
                "historical_challenge_pass": bool(
                    challenge and challenge.get("beats_deterministic_baseline")
                ),
                "virtual_paper_status": (
                    "ai_research_challenger" if candidate["qualified"] else "diagnostic_shadow"
                ),
            }
        )
    return rows


def _fold_win(model: dict[str, Any], baseline: dict[str, Any]) -> bool:
    return bool(
        (
            model["portfolio_total_return_pct"] > baseline["portfolio_total_return_pct"]
            and model["mean_rank_ic"] >= baseline["mean_rank_ic"] - 0.01
        )
        or (
            model["mean_rank_ic"] > baseline["mean_rank_ic"]
            and model["portfolio_total_return_pct"] >= baseline["portfolio_total_return_pct"] - 3.0
        )
    )


def _aggregate_not_worse(model: dict[str, Any], baseline: dict[str, Any]) -> bool:
    return bool(
        model["portfolio_total_return_pct"] >= baseline["portfolio_total_return_pct"] - 5.0
        and model["mean_rank_ic"] >= baseline["mean_rank_ic"] - 0.02
    )


def _metrics_better(model: dict[str, Any], baseline: dict[str, Any]) -> bool:
    return bool(
        model["portfolio_total_return_pct"] > baseline["portfolio_total_return_pct"]
        or model["mean_rank_ic"] > baseline["mean_rank_ic"]
    )


def _matched_fold_better(ai_fold: dict[str, Any], core_fold: dict[str, Any]) -> int:
    return int(_metrics_better(ai_fold["model"], core_fold["model"]))


def _development_score(row: dict[str, Any]) -> float:
    aggregate = row["aggregate"]
    baseline = row["baseline_aggregate"]
    return (
        float(row["fold_wins"]) * 10
        + (aggregate["portfolio_total_return_pct"] - baseline["portfolio_total_return_pct"]) / 10
        + (aggregate["mean_rank_ic"] - baseline["mean_rank_ic"]) * 100
    )


def _unique_trials(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen = set()
    output = []
    for row in rows:
        trial_id = str(row["trial_id"])
        if trial_id not in seen:
            seen.add(trial_id)
            output.append(row)
    return output


def _latest_predictions(latest: pd.DataFrame, predictions: np.ndarray) -> list[dict[str, Any]]:
    work = latest[["symbol", "sector", "baseline_score"]].copy()
    work["prediction"] = predictions
    return [
        {
            "symbol": str(row.symbol),
            "sector": str(row.sector),
            "baseline_score": float(row.baseline_score),
            "prediction": float(row.prediction),
        }
        for row in work.sort_values("prediction", ascending=False).head(10).itertuples()
    ]


def render_ai_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Multi-Asset Momentum AI Factor and ML Evaluation",
        "",
        f"- Workflow pass: `{payload['workflow_pass']}`",
        f"- Research pass: `{payload['research_pass']}`",
        f"- LLM contribution pass: `{payload['llm_contribution_pass']}`",
        f"- Paper ready pass: `{payload['paper_ready_pass']}`",
        f"- Candidates: `{payload['search_space']['candidate_count']}`",
        f"- Factors: `{payload['feature_contract']['feature_count']}`",
        "",
        "## Selected Forward Challengers",
        "",
        "| Trial | Family | Feature Set | Development | Challenge | Status |",
        "|---|---|---|---|---|---|",
    ]
    for row in payload["selected_forward_challengers"]:
        lines.append(
            f"| {row['trial_id']} | {row['model_family']} | {row['feature_set']} | "
            f"{row['development_qualified']} | {row['historical_challenge_pass']} | "
            f"{row['virtual_paper_status']} |"
        )
    lines.extend(["", "## Limitations", ""])
    lines.extend(f"- {item}" for item in payload["limitations"])
    return "\n".join(lines).rstrip() + "\n"


def _sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _relpath(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()
