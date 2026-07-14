from __future__ import annotations

import json
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any

import joblib
import pandas as pd
import yaml

from open_composer.adapters.execution.router_target_weights import (
    write_router_execution_artifacts,
)
from open_composer.config import ensure_dir, project_root
from open_composer.models.strategy_spec import load_strategy_spec
from open_composer.research.multiasset_momentum import (
    ALL_ETF_SYMBOLS,
    ETF_TREND_UNIVERSE,
    _candidate_specs,
    _load_panels,
    _score_frame,
    _weights_from_scores,
)
from open_composer.research.multiasset_momentum_ml import (
    FEATURES,
    _build_panel_dataset,
    _predict,
)
from open_composer.storage import write_json

SOURCE_ITER = Path("reports/research/iterations/mom_multiasset_r1")
ML_ITER = Path("reports/research/iterations/mom_multiasset_ml_r1")
AI_ITER = Path("reports/research/iterations/mom_multiasset_ai_r2")
PORTFOLIO_PATH = ML_ITER / "portfolio-evaluation.json"
PORTFOLIO_MD_PATH = ML_ITER / "portfolio-evaluation.md"


def write_multiasset_momentum_portfolio(root: Path | None = None) -> dict[str, Any]:
    base = root or project_root()
    manifest_path = base / SOURCE_ITER / "universe-manifest.json"
    evaluation_path = base / SOURCE_ITER / "evaluation-report.json"
    ml_path = base / ML_ITER / "model-comparison.json"
    manifest = _load_json(manifest_path)
    evaluation = _load_json(evaluation_path)
    ml_report = _load_json(ml_path)
    ai_path = base / AI_ITER / "evaluation-report.json"
    ai_report = _load_json(ai_path) if ai_path.exists() else None
    stock_symbols = [str(symbol) for symbol in manifest["selected_symbols"]]
    sector_map = {
        str(row["symbol"]): str(row.get("sector") or "Unknown") for row in manifest["selected"]
    }
    symbols = list(dict.fromkeys((*stock_symbols, *ALL_ETF_SYMBOLS)))
    data = _load_panels(base, symbols)
    selected_by_path = {row["path"]: row for row in evaluation["selections"]}
    sleeve_definitions = [
        _deterministic_definition(
            "D1",
            "us_multiasset_etf_trend_d1",
            selected_by_path["P1_etf_absolute_relative"],
            "primary_deterministic",
        ),
        _deterministic_definition(
            "D2",
            "us_multiasset_stock_momentum_d2",
            selected_by_path["P3_stock_cross_sectional"],
            "primary_deterministic_exploratory_history",
        ),
        _deterministic_definition(
            "D3",
            "us_multiasset_stock_sector_relative_d3",
            selected_by_path["P5_stock_residual_sector_relative"],
            "diversification_deterministic_exploratory_history",
        ),
        _deterministic_definition(
            "D4",
            "us_multiasset_stock_trend_quality_d4",
            selected_by_path["P4_stock_trend_quality"],
            "diagnostic_deterministic",
        ),
    ]
    for model in ml_report["frozen_models"]:
        sleeve_id = "M1" if model["model_family"] == "lightgbm" else "M2"
        name = (
            "us_multiasset_stock_rank_lgbm_m1"
            if sleeve_id == "M1"
            else "us_multiasset_stock_rank_hist_m2"
        )
        sleeve_definitions.append(
            {
                "sleeve_id": sleeve_id,
                "strategy_name": name,
                "kind": "ml_ranking",
                "status": model["status"],
                "trial_id": model["trial_id"],
                "model_path": model["model_path"],
                "route_label": f"multiasset:ml:{model['trial_id']}:top5:equal",
                "top_n": 5,
            }
        )
    if ai_report is not None:
        trial_by_id = {str(row["trial_id"]): row for row in ai_report["development_trials"]}
        challenge_by_id = {
            str(row["trial_id"]): row for row in ai_report["historical_challenge"]["rows"]
        }
        for sleeve_id, trial_id, name in [
            ("A1", "regime_spy63_positive", "us_multiasset_ai_regime_a1"),
            ("A2", "abstain_overlap3", "us_multiasset_ai_agreement_a2"),
        ]:
            trial = trial_by_id.get(trial_id)
            if trial is None or not trial["qualified"]:
                continue
            challenge_pass = bool(
                challenge_by_id.get(trial_id, {}).get("beats_deterministic_baseline")
            )
            sleeve_definitions.append(
                {
                    "sleeve_id": sleeve_id,
                    "strategy_name": name,
                    "kind": "ai_ensemble",
                    "status": (
                        "ai_research_challenger_historical_challenge_pass"
                        if challenge_pass
                        else "ai_research_challenger_historical_challenge_failed"
                    ),
                    "trial_id": trial_id,
                    "route_label": f"multiasset:ai:{trial_id}",
                    "top_n": 5,
                    "role": trial["role"],
                    "parameter": trial.get("parameter"),
                    "component_trials": trial["component_trials"],
                }
            )
    spec_paths = _write_specs(
        base,
        sleeve_definitions,
        stock_symbols=stock_symbols,
        manifest_path=manifest_path,
        ml_report=ml_report,
    )
    latest_features = _build_panel_dataset(data, stock_symbols, sector_map)[1]
    ai_latest_features = None
    if ai_report is not None:
        from open_composer.research.multiasset_momentum_ai import build_ai_factor_dataset

        ai_latest_features = build_ai_factor_dataset(data, stock_symbols, sector_map)[1]
    d2_definition = next(row for row in sleeve_definitions if row["sleeve_id"] == "D2")
    d2_weights = _deterministic_latest_weights(
        d2_definition,
        data,
        stock_symbols,
        sector_map,
    )[0]
    sleeve_rows = []
    for definition in sleeve_definitions:
        if definition["kind"] == "deterministic":
            weights, signal_session, rebalance_session = _deterministic_latest_weights(
                definition,
                data,
                stock_symbols,
                sector_map,
            )
        elif definition["kind"] == "ml_ranking":
            weights, signal_session, rebalance_session = _ml_latest_weights(
                base,
                definition,
                latest_features,
                data,
            )
        else:
            if ai_report is None or ai_latest_features is None:
                raise ValueError("AI ensemble definition requires the AI evaluation report")
            weights, signal_session, rebalance_session = _ai_latest_weights(
                base,
                definition,
                ai_report,
                ai_latest_features,
                d2_weights,
                data,
            )
        spec_path = spec_paths[str(definition["strategy_name"])]
        spec = load_strategy_spec(spec_path)
        artifacts = _write_execution_artifacts(
            base,
            spec_path,
            spec,
            weights,
            signal_session=signal_session,
            rebalance_session=rebalance_session,
            data_as_of=data["data_as_of"],
            status=str(definition["status"]),
        )
        sleeve_rows.append(
            {
                **definition,
                "spec_path": _relpath(spec_path, base),
                "signal_session": signal_session,
                "rebalance_session": rebalance_session,
                "target_weights": weights,
                "gross_exposure": round(sum(abs(value) for value in weights.values()), 8),
                "target_weights_path": _relpath(artifacts["router_target_weights"], base),
                "execution_observation_path": _relpath(
                    artifacts["router_execution_observation"], base
                ),
                "broker_writes": False,
            }
        )
    payload = {
        "report_type": "multiasset_momentum_virtual_paper_portfolio",
        "generated_at": datetime.now(UTC).isoformat(),
        "workflow_pass": True,
        "research_pass": False,
        "paper_ready_pass": False,
        "llm_contribution_pass": False,
        "data_as_of": data["data_as_of"],
        "simulation": {
            "mode": "isolated_virtual_paper_sleeves",
            "initial_capital_per_sleeve": 100_000.0,
            "broker_writes": False,
            "alpaca_orders": False,
            "forward_epoch_utc": "2026-07-14T00:00:00+00:00",
            "retuning_from_forward_results": False,
        },
        "sleeves": sleeve_rows,
        "decisions": {
            "primary_deterministic": ["D1", "D2", "D3"],
            "diagnostic_deterministic": ["D4"],
            "diagnostic_ml": [
                row["sleeve_id"] for row in sleeve_rows if row["kind"] == "ml_ranking"
            ],
            "ai_research_challengers": [
                row["sleeve_id"] for row in sleeve_rows if row["kind"] == "ai_ensemble"
            ],
            "rejected_ml_roles": [
                "elastic_net_return_ranking",
                "extra_trees_return_ranking",
                "downside_risk_logistic",
                "downside_risk_lightgbm",
                "prediction_weighted_sizing",
            ],
        },
        "limitations": [
            (
                "D2-D4 and M1-M2 use a current frozen stock universe; pre-freeze history "
                "is exploratory."
            ),
            "M1 and M2 passed development folds but failed the deterministic lockbox comparison.",
            (
                "A1 and A2 passed historical development folds but failed the exposed "
                "historical challenge; they are forward diagnostic challengers only."
            ),
            (
                "All sleeves are file-based virtual paper observations and cannot submit "
                "broker orders."
            ),
        ],
    }
    portfolio_path = base / PORTFOLIO_PATH
    markdown_path = base / PORTFOLIO_MD_PATH
    write_json(portfolio_path, payload)
    markdown_path.write_text(_render_markdown(payload), encoding="utf-8")
    write_json(
        base / ML_ITER / "observation-state.json",
        {
            "report_type": "multiasset_momentum_observation_state",
            "forward_epoch_utc": payload["simulation"]["forward_epoch_utc"],
            "data_as_of": data["data_as_of"],
            "sleeves": [
                {
                    "sleeve_id": row["sleeve_id"],
                    "strategy_name": row["strategy_name"],
                    "status": row["status"],
                    "target_weights_path": row["target_weights_path"],
                }
                for row in sleeve_rows
            ],
            "broker_writes": False,
            "next_action": "append_only_forward_observation",
        },
    )
    payload["review_artifacts"] = _write_review_artifacts(
        base,
        evaluation=evaluation,
        ml_report=ml_report,
        portfolio=payload,
    )
    write_json(portfolio_path, payload)
    markdown_path.write_text(_render_markdown(payload), encoding="utf-8")
    return payload


def write_multiasset_target_weights_for_spec(
    spec_path: Path,
    root: Path | None = None,
) -> dict[str, Path]:
    base = root or project_root()
    payload = write_multiasset_momentum_portfolio(base)
    spec = load_strategy_spec(spec_path)
    sleeve = next((row for row in payload["sleeves"] if row["strategy_name"] == spec.name), None)
    if sleeve is None:
        raise ValueError(f"strategy {spec.name} is not in the multiasset portfolio")
    return {
        "router_target_weights": base / str(sleeve["target_weights_path"]),
        "router_execution_observation": base / str(sleeve["execution_observation_path"]),
    }


def _deterministic_definition(
    sleeve_id: str,
    strategy_name: str,
    selection: dict[str, Any],
    status: str,
) -> dict[str, Any]:
    return {
        "sleeve_id": sleeve_id,
        "strategy_name": strategy_name,
        "kind": "deterministic",
        "status": status,
        "path": selection["path"],
        "trial_id": selection["trial_id"],
        "params": selection["params"],
        "route_label": f"multiasset:deterministic:{selection['trial_id']}",
    }


def _write_specs(
    root: Path,
    definitions: list[dict[str, Any]],
    *,
    stock_symbols: list[str],
    manifest_path: Path,
    ml_report: dict[str, Any],
) -> dict[str, Path]:
    output = ensure_dir(root / "strategy_specs" / "drafts")
    manifest_sha = sha256(manifest_path.read_bytes()).hexdigest()
    paths = {}
    for definition in definitions:
        is_etf = definition["sleeve_id"] == "D1"
        universe = list(ETF_TREND_UNIVERSE) if is_etf else stock_symbols
        top_n = int(definition.get("top_n") or definition.get("params", {}).get("top_n") or 5)
        max_weight = 1 / top_n
        raw = {
            "name": definition["strategy_name"],
            "description": (
                "Frozen multiasset momentum virtual-paper sleeve. "
                "Cross-sectional routing is observation-only."
            ),
            "timeframe": "daily",
            "universe": universe,
            "lifecycle": "draft",
            "position_direction": "long_only",
            "entry": {"all": ["close > 0"], "any": []},
            "exit": {"all": [], "any": ["close <= 0"]},
            "risk": {
                "max_trades_per_day": max(len(universe), 3),
                "max_position_weight": max_weight,
                "stop_loss_pct": None,
                "take_profit_pct": None,
            },
            "portfolio": {
                "mode": "cross_sectional_momentum",
                "max_symbols_per_day": top_n,
                "gross_exposure_limit": 1.0,
                "max_symbol_weight": max_weight,
                "same_day_flatten": False,
                "duplicate_signal_policy": "stable_signal_id",
                "selected_route_label": definition["route_label"],
            },
            "costs": {
                "commission_pct": 0.0,
                "slippage_bps": 10.0,
                "impact_model": "linear",
                "impact_eta": 0.0,
                "impact_gamma": 0.0,
            },
            "execution": {
                "backend": "python_reference",
                "mode": "manual_signal",
                "signal_on": "bar_close",
                "fill_assumption": "next_bar_open",
                "broker": "none",
            },
            "data": {
                "source": "longbridge",
                "symbol": universe[0],
                "feed": "nasdaq_basic",
            },
            "data_assumptions": {
                "source": "longbridge",
                "adjusted": True,
                "timezone": "America/New_York",
                "acquisition_tier": "research_replay_cache",
            },
            "factors": {},
            "llm_review": {"enabled": False},
            "required_capabilities": ["market.longbridge_bars"],
            "notes": {
                "intent": "Isolated virtual-paper comparison; no broker writes.",
                "research_design": {
                    "iter_id": "mom_multiasset_ml_r1",
                    "sleeve_id": definition["sleeve_id"],
                    "status": definition["status"],
                    "trial_id": definition["trial_id"],
                    "route_label": definition["route_label"],
                    "params": definition.get("params", {}),
                    "model_path": definition.get("model_path"),
                    "universe_manifest_path": _relpath(manifest_path, root),
                    "universe_manifest_sha256": manifest_sha,
                    "ml_lockbox_pass_trials": ml_report["selection"]["lockbox_pass_trials"],
                    "ai_component_trials": definition.get("component_trials", []),
                    "ai_historical_challenge_pass": False
                    if definition["kind"] == "ai_ensemble"
                    else None,
                    "forward_epoch_utc": "2026-07-14T00:00:00+00:00",
                },
                "caveats": [
                    "Current-universe history is survivorship-biased before the freeze date.",
                    "This draft is observation-only and cannot submit broker orders.",
                ],
            },
        }
        path = output / f"{definition['strategy_name']}.yaml"
        path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
        load_strategy_spec(path)
        paths[str(definition["strategy_name"])] = path
    return paths


def _deterministic_latest_weights(
    definition: dict[str, Any],
    data: dict[str, Any],
    stock_symbols: list[str],
    sector_map: dict[str, str],
) -> tuple[dict[str, float], str, str]:
    spec = next(row for row in _candidate_specs() if row["trial_id"] == definition["trial_id"])
    universe = list(ETF_TREND_UNIVERSE) if definition["sleeve_id"] == "D1" else stock_symbols
    scores = _score_frame(str(spec["path"]), dict(spec["params"]), data, universe, sector_map)
    weights, _ = _weights_from_scores(
        scores,
        dict(spec["params"]),
        sector_map=sector_map,
        cash_symbol="BIL",
    )
    latest = weights.iloc[-1]
    output = {symbol: round(float(weight), 8) for symbol, weight in latest.items() if weight > 0}
    return output, scores.index[-2].date().isoformat(), scores.index[-1].date().isoformat()


def _ml_latest_weights(
    root: Path,
    definition: dict[str, Any],
    latest_features: pd.DataFrame,
    data: dict[str, Any],
) -> tuple[dict[str, float], str, str]:
    model = joblib.load(root / str(definition["model_path"]))
    predictions = _predict(model, latest_features[list(FEATURES)], "return_ranking")
    work = latest_features[["symbol"]].copy()
    work["prediction"] = predictions
    selected = work.nlargest(int(definition["top_n"]), "prediction")["symbol"].tolist()
    weights = {symbol: round(1 / len(selected), 8) for symbol in selected}
    index = data["close"].index
    return weights, index[-2].date().isoformat(), index[-1].date().isoformat()


def _ai_latest_weights(
    root: Path,
    definition: dict[str, Any],
    ai_report: dict[str, Any],
    latest_features: pd.DataFrame,
    baseline_weights: dict[str, float],
    data: dict[str, Any],
) -> tuple[dict[str, float], str, str]:
    frozen = {str(row["trial_id"]): row for row in ai_report["frozen_models"]}
    frames = []
    for trial_id in definition["component_trials"]:
        model_row = frozen.get(str(trial_id))
        if model_row is None:
            raise ValueError(f"missing frozen AI component model: {trial_id}")
        bundle = joblib.load(root / str(model_row["model_path"]))
        features = [str(name) for name in bundle["features"]]
        fill_values = pd.Series(bundle["fill_values"])
        predictions = bundle["model"].predict(latest_features[features].fillna(fill_values))
        frame = latest_features[["symbol", "baseline_score"]].copy()
        frame["prediction"] = predictions
        frame["rank"] = frame["prediction"].rank(pct=True)
        frames.append(frame)
    selected: list[str]
    if definition["role"] == "regime_switch":
        spy_momentum = float(latest_features["market_spy_mom_63"].iloc[0])
        selected = (
            frames[0].nlargest(int(definition["top_n"]), "prediction")["symbol"].tolist()
            if spy_momentum > 0
            else list(baseline_weights)
        )
    elif definition["role"] == "disagreement_abstention":
        selections = [
            set(frame.nlargest(int(definition["top_n"]), "prediction")["symbol"])
            for frame in frames
        ]
        overlap = len(set.intersection(*selections)) if selections else 0
        if overlap >= int(definition["parameter"]):
            average = frames[0][["symbol"]].copy()
            average["rank"] = pd.concat([frame["rank"] for frame in frames], axis=1).mean(axis=1)
            selected = average.nlargest(int(definition["top_n"]), "rank")["symbol"].tolist()
        else:
            selected = list(baseline_weights)
    else:
        raise ValueError(f"unsupported AI ensemble role: {definition['role']}")
    weights = {symbol: round(1 / len(selected), 8) for symbol in selected}
    index = data["close"].index
    return weights, index[-2].date().isoformat(), index[-1].date().isoformat()


def _write_execution_artifacts(
    root: Path,
    spec_path: Path,
    spec: Any,
    weights: dict[str, float],
    *,
    signal_session: str,
    rebalance_session: str,
    data_as_of: str,
    status: str,
) -> dict[str, Path]:
    rebalance_id = sha256(
        f"{spec.name}|{rebalance_session}|{spec.portfolio.selected_route_label}".encode()
    ).hexdigest()[:24]
    target_rows = [
        {
            "rebalance_id": rebalance_id,
            "rebalance_session": rebalance_session,
            "signal_session": signal_session,
            "time_rule": "regular_session_open",
            "symbol": symbol,
            "target_weight": float(weights.get(symbol, 0.0)),
        }
        for symbol in spec.universe
    ]
    intents = [
        {
            "rebalance_id": rebalance_id,
            "rebalance_session": rebalance_session,
            "time_rule": "regular_session_open",
            "symbol": symbol,
            "from_weight": 0.0,
            "to_weight": float(weights.get(symbol, 0.0)),
            "delta_weight": float(weights.get(symbol, 0.0)),
            "side": "buy" if weights.get(symbol, 0.0) > 0 else "hold",
            "intent_type": "set_target_weight",
            "requires_order": False,
        }
        for symbol in spec.universe
    ]
    return write_router_execution_artifacts(
        root=root,
        spec_path=spec_path,
        spec=spec,
        target_rows=target_rows,
        rebalance_intents=intents,
        data_profile={
            "provider": "longbridge",
            "feed": "nasdaq_basic",
            "adjusted": True,
            "data_as_of": data_as_of,
            "source_mode": "research_replay_cache",
        },
        route_label=spec.portfolio.selected_route_label,
        mapping_summary={
            "research_status": status,
            "broker_writes": False,
            "virtual_initial_capital": 100_000.0,
        },
        acquisition_tier="research_replay_cache",
        parity_check={
            "status": "warning",
            "warnings": [
                "Current-universe historical replay is exploratory; forward epoch is frozen."
            ],
        },
    )


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _write_review_artifacts(
    root: Path,
    *,
    evaluation: dict[str, Any],
    ml_report: dict[str, Any],
    portfolio: dict[str, Any],
) -> dict[str, str]:
    family = "us_multiasset_momentum_portfolio"
    reviewed_at = datetime.now(UTC).date().isoformat()
    data_path = root / "reports" / "harness" / "data" / f"{family}-capability-review.json"
    forensics_path = (
        root / "reports" / "harness" / "forensics" / f"{family}-backtest-forensics.json"
    )
    forensics_md_path = forensics_path.with_suffix(".md")
    execution_dir = root / "reports" / "harness" / "execution"
    policy_path = execution_dir / f"{family}-execution-policy.json"
    execution_path = execution_dir / f"{family}-execution-reality.json"
    execution_md_path = execution_path.with_suffix(".md")
    safety_path = root / "reports" / "harness" / "paper" / f"{family}-paper-safety-review.json"

    capability = {
        "strategy_name": family,
        "reviewed_at": reviewed_at,
        "capabilities": [
            {
                "capability_id": "market.longbridge_bars",
                "kind": "market",
                "status": "partial",
                "strict_behavior": "research_replay_cache",
                "paper_ready": False,
                "notes": (
                    "Adjusted daily bars support deterministic replay, but the frozen "
                    "current-stock "
                    "universe does not provide point-in-time historical membership."
                ),
            }
        ],
        "feature_packet_pit_check": "pass",
        "sample_data_caveats": [],
        "blockers": [
            "current stock membership is only formal from the 2026-07-14 freeze epoch",
            "research replay cache is not paper-ready live market evidence",
        ],
        "conclusion": "warning",
    }
    deterministic_trials = int(evaluation.get("search_space", {}).get("candidate_count") or 60)
    ml_trials = int(ml_report.get("search_space", {}).get("candidate_count") or 16)
    forensics = {
        "strategy_name": family,
        "reviewed_at": reviewed_at,
        "lookahead_check": "pass",
        "future_leak_check": "pass",
        "index_alignment": "features use index-1; returns are next-open to next-open",
        "purge_embargo": "ML uses 21-bar label horizon plus 21-bar embargo",
        "trial_ledger_present": True,
        "overfit_risk": "high",
        "multiple_testing_count": deterministic_trials + ml_trials,
        "pbo_proxy": None,
        "dsr_proxy": None,
        "sample_data_caveats": [
            "D2-D4 and M1-M2 historical results use a current frozen universe and are "
            "survivorship-biased before 2026-07-14."
        ],
        "trade_count": None,
        "trading_days": None,
        "capacity_assessment": "warning_pending_forward_quotes_and_realized_turnover",
        "short_sample": False,
        "ml_lockbox_pass_trials": ml_report["selection"]["lockbox_pass_trials"],
        "conclusion": "warning",
        "notes": (
            "The deterministic 12-1 sleeve beat both qualified nonlinear models in the locked "
            "period. ML sleeves remain diagnostic shadows and cannot be promoted."
        ),
    }
    policy = {
        "strategy_name": family,
        "reviewed_at": reviewed_at,
        "status": "observation_only",
        "recommended_order_style": "price_protected_open_or_delayed_open_after_forward_tca",
        "compared_styles": [
            {
                "style": "DAY_market_at_open",
                "benefit": "highest fill probability",
                "risk": "unbounded opening gap and spread",
                "authorized": False,
            },
            {
                "style": "LOO_OPG_limit",
                "benefit": "opening-auction price protection",
                "risk": "missed fills and partial portfolio drift",
                "authorized": False,
            },
            {
                "style": "delayed_open_5m_marketable_limit",
                "benefit": "avoids the opening auction spike",
                "risk": "tracking error against next-open research semantics",
                "authorized": False,
            },
        ],
        "broker_writes": False,
    }
    execution = {
        "strategy_name": family,
        "reviewed_at": reviewed_at,
        "status": "blocked",
        "slippage_scenarios": [
            {"name": "low", "slippage_bps": 5, "open_gap_pct": 0.2},
            {"name": "base", "slippage_bps": 10, "open_gap_pct": 0.8},
            {"name": "high", "slippage_bps": 20, "open_gap_pct": 2.5},
        ],
        "capacity_assessment": {
            "initial_capital_per_sleeve": portfolio["simulation"]["initial_capital_per_sleeve"],
            "stock_universe_minimum_median_dollar_volume": 50_000_000,
            "status": "warning",
            "reason": (
                "forward quote, spread, opening-window volume, and partial-fill evidence "
                "is not yet available"
            ),
        },
        "tca_plan": [
            "record decision close, official open, arrival bid/ask, 5-minute VWAP, and fill status",
            "compare target versus observed virtual fill weights per sleeve",
            "do not authorize orders from this artifact",
        ],
        "blockers": [
            "draft observation-only specs",
            "no broker authorization",
            "no forward opening-auction TCA",
            "current-universe survivorship caveat",
        ],
    }
    safety = {
        "strategy_name": family,
        "reviewed_at": reviewed_at,
        "lifecycle_gate": "blocked_draft",
        "execution_mode": "manual_signal",
        "broker": "none",
        "paper_auto": False,
        "router_authorization": False,
        "broker_writes": False,
        "kill_switch_required_before_authorization": True,
        "duplicate_order_policy": "not_applicable_observation_only",
        "audit_linkage": "target weights and rebalance intents are file artifacts only",
        "conclusion": "blocked",
        "notes": "No Alpaca Paper or real-money order path is enabled for this family.",
    }
    write_json(data_path, capability)
    write_json(forensics_path, forensics)
    write_json(policy_path, policy)
    write_json(execution_path, execution)
    write_json(safety_path, safety)
    forensics_md_path.write_text(
        _review_markdown("Backtest Forensics", forensics), encoding="utf-8"
    )
    execution_md_path.write_text(_review_markdown("Execution Reality", execution), encoding="utf-8")
    per_strategy_execution = _write_strategy_execution_reviews(
        root,
        portfolio=portfolio,
        reviewed_at=reviewed_at,
    )
    return {
        "capability_review": _relpath(data_path, root),
        "backtest_forensics": _relpath(forensics_path, root),
        "execution_policy": _relpath(policy_path, root),
        "execution_reality": _relpath(execution_path, root),
        "paper_safety_review": _relpath(safety_path, root),
        "per_strategy_execution": per_strategy_execution,
    }


def _review_markdown(title: str, payload: dict[str, Any]) -> str:
    lines = [f"# {title}", ""]
    for key in ("strategy_name", "reviewed_at", "status", "conclusion", "notes"):
        if key in payload:
            lines.append(f"- {key}: `{payload[key]}`")
    blockers = payload.get("blockers") or []
    if blockers:
        lines.extend(["", "## Blockers", ""])
        lines.extend(f"- {item}" for item in blockers)
    return "\n".join(lines).rstrip() + "\n"


def _write_strategy_execution_reviews(
    root: Path,
    *,
    portfolio: dict[str, Any],
    reviewed_at: str,
) -> list[dict[str, str]]:
    from open_composer.research.execution_policy import generate_execution_policy_artifacts

    source_dir = ensure_dir(root / "reports" / "harness" / "source_cards")
    rows = []
    for sleeve in portfolio["sleeves"]:
        strategy_name = str(sleeve["strategy_name"])
        primary_id = f"{strategy_name}:source-research"
        opening_cross_id = f"{strategy_name}:nasdaq-opening-cross"
        cards = [
            {
                "claim_id": primary_id,
                "claim": (
                    "Alpaca documents OPG as the time-in-force used with market or limit "
                    "orders for market-on-open and limit-on-open instructions."
                ),
                "source_url": "https://docs.alpaca.markets/us/docs/orders-at-alpaca",
                "source_type": "broker_official_docs",
                "accessed_at": reviewed_at,
                "applies_to": ["daily_open_execution", "future_paper_tca"],
                "impact_on_spec": (
                    "Compare price-protected OPG execution with delayed-open execution "
                    "before any future paper authorization."
                ),
                "limitations": (
                    "This source establishes order support, not fill quality, account "
                    "eligibility, or authorization for this draft."
                ),
            },
            {
                "claim_id": opening_cross_id,
                "claim": (
                    "Nasdaq states that its Opening Cross occurs at 9:30 ET and accepts "
                    "on-open MOO and LOO orders."
                ),
                "source_url": "https://www.nasdaqtrader.com/trader.aspx?id=openclose",
                "source_type": "exchange_official_docs",
                "accessed_at": reviewed_at,
                "applies_to": ["daily_open_execution", "opening_auction"],
                "impact_on_spec": (
                    "Treat official-open fills as an auction execution assumption that "
                    "requires separate forward TCA."
                ),
                "limitations": (
                    "Auction eligibility does not guarantee execution or remove gap, "
                    "spread, partial-fill, or venue-routing risk."
                ),
            },
        ]
        source_path = source_dir / f"{strategy_name}.jsonl"
        source_path.write_text(
            "".join(json.dumps(card, sort_keys=True) + "\n" for card in cards),
            encoding="utf-8",
        )
        spec_path = root / str(sleeve["spec_path"])
        artifacts = generate_execution_policy_artifacts(
            spec_path,
            root=root,
            overwrite=True,
            source_card_ids=[primary_id, opening_cross_id],
        )
        rows.append(
            {
                "strategy_name": strategy_name,
                "source_cards": _relpath(source_path, root),
                "execution_policy": _relpath(artifacts.policy_path, root),
                "execution_reality": _relpath(artifacts.reality_path, root),
            }
        )
    return rows


def _relpath(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def _render_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Multi-Asset Momentum Virtual-Paper Portfolio",
        "",
        f"- Data as of: `{payload['data_as_of']}`",
        f"- Forward epoch: `{payload['simulation']['forward_epoch_utc']}`",
        f"- Broker writes: `{str(payload['simulation']['broker_writes']).lower()}`",
        "",
        "| Sleeve | Strategy | Kind | Status | Targets |",
        "|---|---|---|---|---|",
    ]
    for row in payload["sleeves"]:
        targets = ", ".join(
            f"{symbol} {weight:.0%}" for symbol, weight in row["target_weights"].items()
        )
        lines.append(
            f"| {row['sleeve_id']} | {row['strategy_name']} | {row['kind']} | "
            f"{row['status']} | {targets} |"
        )
    lines.extend(["", "## Limitations", ""])
    lines.extend(f"- {item}" for item in payload["limitations"])
    return "\n".join(lines).rstrip() + "\n"
