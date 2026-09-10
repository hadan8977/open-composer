from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest
import yaml

from open_composer.adapters.execution.model_ranking_target_weights import (
    DerivedRatioScoreModel,
    MomentumPlaceholderModel,
    load_candidate_artifact,
    most_recent_rebalance_date,
    run_model_ranking_target_weight_mapping,
    trend_gate_state,
)
from open_composer.models.strategy_spec import StrategySpec

# A real trading week the live SIP/feature archive already covers (verified
# 2026-09-08 against the actual data/features/daily/2026.parquet): Friday
# 2026-09-04 is the last trading session of its ISO week; the following
# Monday 2026-09-07 is Labor Day (closed), so 2026-09-08 (Tuesday) is the
# first trading day of the *next* ISO week and is not itself a rebalance day.
SIGNAL_DATE = pd.Timestamp("2026-09-04")
HOLD_DATE = pd.Timestamp("2026-09-08")
UNIVERSE = ["AAA", "BBB", "CCC", "DDD", "EEE"]
MOMENTUM = {"AAA": 0.30, "BBB": 0.25, "CCC": 0.20, "DDD": 0.15, "EEE": 0.10}
CLOSE = {"AAA": 100.0, "BBB": 50.0, "CCC": 20.0, "DDD": 10.0, "EEE": 5.0, "SPY": 500.0}
#: Deliberately *not* monotone with MOMENTUM -- ranking by
#: momentum_252_21/vol_63 (CCC 4.0, DDD 3.0, BBB 2.5, EEE 2.0, AAA 1.0) must
#: pick a different top-3 (CCC/DDD/BBB) than ranking by raw momentum_252_21
#: alone would (AAA/BBB/CCC), so a test asserting the former proves the
#: derived ratio -- not just the numerator column -- actually drove
#: selection.
VOL_63 = {"AAA": 0.30, "BBB": 0.10, "CCC": 0.05, "DDD": 0.05, "EEE": 0.05}


class _FixedScoreModel:
    """Module-level (joblib/pickle needs an importable class, not a nested
    one) synthetic loop.RankingStrategy-protocol object for
    ``_fitted_candidate_dir``: scores as ``-momentum_252_21``, i.e. the
    *inverse* of the placeholder rule, so a test asserting on the model's
    own ranking fails loudly if load_candidate_artifact ever silently
    ignored the fitted model.joblib and fell back to the placeholder rule
    instead.
    """

    def score(self, asof_frame: pd.DataFrame) -> pd.Series:
        return -asof_frame.set_index("symbol")["momentum_252_21"].astype(float)


def _write_daily_features(root: Path, dates: list[pd.Timestamp]) -> None:
    rows = []
    for trade_date in dates:
        for symbol in [*UNIVERSE, "SPY"]:
            rows.append(
                {
                    "symbol": symbol,
                    "trade_date": trade_date,
                    "close": CLOSE[symbol],
                    "momentum_252_21": MOMENTUM.get(symbol, 0.05),
                    "beta_252_spy": 1.0 if symbol != "SPY" else 0.0,
                }
            )
    frame = pd.DataFrame(rows)
    out_dir = root / "data" / "features" / "daily"
    out_dir.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(out_dir / "2026.parquet", index=False)


def _write_universe(root: Path, *, month_end: pd.Timestamp) -> None:
    rows = [
        {
            "month_end": month_end,
            "symbol": symbol,
            "adv_rank": rank + 1,
            "dollar_adv": 1_000_000.0 - rank,
            "close": CLOSE[symbol],
        }
        for rank, symbol in enumerate(UNIVERSE)
    ]
    out_dir = root / "data" / "features" / "universe"
    out_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_parquet(out_dir / "2026.parquet", index=False)


def _candidate_dir(root: Path, *, top_k: int = 3, hedge: str = "none") -> Path:
    # Field names match the research line's authoritative export interface
    # (reports/research/control/step11-2026-09-06-progress.md, "Wave B item
    # 5", commit 93ba159): config.json is an ExperimentConfig-shaped dump,
    # features.json carries feature_columns (the only key this adapter
    # reads) plus the interface's other metadata fields. model_kind +
    # score_column together are this module's own rule-based-placeholder
    # convention (no model.joblib), not part of that interface.
    candidate_dir = root / "candidates" / "test_momentum_placeholder"
    candidate_dir.mkdir(parents=True, exist_ok=True)
    (candidate_dir / "config.json").write_text(
        json.dumps(
            {
                "experiment_id": "test_momentum_placeholder",
                "family": "test_b1_momentum",
                "model_kind": "rule_momentum_top_k",
                "feature_set": "daily_only",
                "label_horizon_days": 21,
                "feature_columns": ["momentum_252_21"],
                "top_k": top_k,
                "hedge": hedge,
                "train_row_dates": "rule_based_no_training",
                "score_column": "momentum_252_21",
            }
        ),
        encoding="utf-8",
    )
    (candidate_dir / "features.json").write_text(
        json.dumps(
            {
                "experiment_id": "test_momentum_placeholder",
                "family": "test_b1_momentum",
                "model_kind": "rule_momentum_top_k",
                "feature_set": "daily_only",
                "feature_columns": ["momentum_252_21"],
                "label_column": "label_rank_21",
                "label_horizon_days": 21,
                "top_k": top_k,
                "hedge": hedge,
                "train_row_dates": "rule_based_no_training",
                "execution": "close_marked",
                "refit_through_date": None,
            }
        ),
        encoding="utf-8",
    )
    return candidate_dir


def _write_daily_features_with_vol(root: Path, dates: list[pd.Timestamp]) -> None:
    """Like ``_write_daily_features``, plus a ``vol_63`` column so
    ``score_expression={"numerator": "momentum_252_21", "denominator":
    "vol_63"}`` tests can prove the *ratio* -- not raw ``momentum_252_21``
    alone -- drives selection (see module-level ``VOL_63``).
    """
    rows = []
    for trade_date in dates:
        for symbol in [*UNIVERSE, "SPY"]:
            rows.append(
                {
                    "symbol": symbol,
                    "trade_date": trade_date,
                    "close": CLOSE[symbol],
                    "momentum_252_21": MOMENTUM.get(symbol, 0.05),
                    "vol_63": VOL_63.get(symbol, 0.05),
                    "beta_252_spy": 1.0 if symbol != "SPY" else 0.0,
                }
            )
    frame = pd.DataFrame(rows)
    out_dir = root / "data" / "features" / "daily"
    out_dir.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(out_dir / "2026.parquet", index=False)


def _derived_ratio_candidate_dir(
    root: Path, *, top_k: int = 3, trend_gate: dict[str, object] | None = None
) -> Path:
    """A ``score_expression``/rule_derived_ratio_top_k candidate directory
    (Step 13 Track M product path), no ``model.joblib`` -- same "rule needs
    no training" convention as ``_candidate_dir``'s single-column
    placeholder, generalized to a two-column ratio plus an optional
    ``trend_gate`` block.
    """
    candidate_dir = root / "candidates" / "test_derived_ratio"
    candidate_dir.mkdir(parents=True, exist_ok=True)
    config: dict[str, object] = {
        "experiment_id": "test_derived_ratio",
        "family": "test_step13_m0b",
        "model_kind": "rule_derived_ratio_top_k",
        "feature_set": "daily27",
        "label_horizon_days": 5,
        "feature_columns": ["momentum_252_21", "vol_63"],
        "top_k": top_k,
        "hedge": "none",
        "train_row_dates": "rule_based_no_training",
        "score_expression": {"numerator": "momentum_252_21", "denominator": "vol_63"},
    }
    if trend_gate is not None:
        config["trend_gate"] = trend_gate
    (candidate_dir / "config.json").write_text(json.dumps(config), encoding="utf-8")
    (candidate_dir / "features.json").write_text(
        json.dumps(
            {
                "experiment_id": "test_derived_ratio",
                "family": "test_step13_m0b",
                "model_kind": "rule_derived_ratio_top_k",
                "feature_set": "daily27",
                "feature_columns": ["momentum_252_21", "vol_63"],
                "label_column": "label_rank_5",
                "label_horizon_days": 5,
                "top_k": top_k,
                "hedge": "none",
                "train_row_dates": "rule_based_no_training",
                "execution": "next_open",
                "refit_through_date": None,
            }
        ),
        encoding="utf-8",
    )
    return candidate_dir


def _write_sip_daily_archive(
    root: Path, series_by_symbol: dict[str, tuple[pd.DatetimeIndex, list[float]]]
) -> None:
    """A miniature ``data/sip/daily/{year}/shard-0000.parquet`` archive
    (same layout ``tests/test_sip_parquet_loader.py`` builds), for the
    trend gate's benchmark/cash-symbol reads
    (:func:`open_composer.adapters.execution.model_ranking_target_weights.
    trend_gate_state`), which never come from ``data/features/daily/``.
    """
    frames = []
    for symbol, (dates, closes) in series_by_symbol.items():
        frames.append(
            pd.DataFrame(
                {
                    "symbol": [symbol] * len(dates),
                    "timestamp": pd.DatetimeIndex(dates, tz="UTC"),
                    "open": closes,
                    "high": closes,
                    "low": closes,
                    "close": closes,
                    "volume": [1_000_000.0] * len(dates),
                    "trade_count": [100.0] * len(dates),
                    "vwap": closes,
                }
            )
        )
    combined = pd.concat(frames, ignore_index=True)
    for year, group in combined.groupby(combined["timestamp"].dt.year):
        out_dir = root / "data" / "sip" / "daily" / str(int(year))
        out_dir.mkdir(parents=True, exist_ok=True)
        group.to_parquet(out_dir / "shard-0000.parquet", index=False)


def _fitted_candidate_dir(root: Path) -> Path:
    """A candidate directory with a real model.joblib -- a tiny synthetic
    object implementing the loop.RankingStrategy protocol directly
    (.score(asof_frame) -> pd.Series), exactly as the research line's real
    exports do, to prove load_candidate_artifact uses it as-is with no
    .predict()-based wrapper.
    """
    import joblib

    candidate_dir = root / "candidates" / "test_fitted_candidate"
    candidate_dir.mkdir(parents=True, exist_ok=True)
    (candidate_dir / "config.json").write_text(
        json.dumps(
            {
                "experiment_id": "test_fitted_candidate",
                "family": "test_b3_lightgbm",
                "model_kind": "lightgbm_rank",
                "feature_set": "daily_only",
                "label_horizon_days": 21,
                "feature_columns": ["momentum_252_21"],
                "top_k": 3,
                "hedge": "none",
                "train_row_dates": "rebalance_dates",
            }
        ),
        encoding="utf-8",
    )
    (candidate_dir / "features.json").write_text(
        json.dumps(
            {
                "experiment_id": "test_fitted_candidate",
                "family": "test_b3_lightgbm",
                "model_kind": "lightgbm_rank",
                "feature_set": "daily_only",
                "feature_columns": ["momentum_252_21"],
                "label_column": "label_rank_21",
                "label_horizon_days": 21,
                "top_k": 3,
                "hedge": "none",
                "train_row_dates": "rebalance_dates",
                "execution": "next_open",
                "refit_through_date": "2026-08-28",
            }
        ),
        encoding="utf-8",
    )
    joblib.dump(_FixedScoreModel(), candidate_dir / "model.joblib")
    return candidate_dir


def _write_spec(
    root: Path,
    repo_root: Path,
    *,
    candidate_dir: Path,
    top_k: int = 3,
    hedge: str = "none",
    name: str = "test_model_ranking_portfolio",
) -> Path:
    fixture = (
        repo_root / "tests" / "fixtures" / "strategy_specs" / "drafts" / "fixture_pullback_15m.yaml"
    )
    raw = yaml.safe_load(fixture.read_text(encoding="utf-8"))
    raw.update(
        {
            "name": name,
            "timeframe": "daily",
            "universe": UNIVERSE,
            "portfolio": {
                "mode": "model_ranking_portfolio",
                "candidate_artifact_dir": candidate_dir.relative_to(root).as_posix(),
                "universe_rule": "pit_adv_top_n",
                "universe_top_n": 5,
                "feature_set_id": "daily_only",
                "label_horizon_days": 21,
                "top_k": top_k,
                "rebalance": "weekly_friday_close_monday_open",
                "weighting": "equal_weight",
                "hedge": hedge,
            },
        }
    )
    raw["risk"]["max_position_weight"] = 0.5
    raw["data"]["source"] = "alpaca"
    raw["data"]["path"] = None
    raw["data"]["feed"] = "sip"
    path = root / f"{name}.yaml"
    path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
    StrategySpec.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
    return path


class TestLoadCandidateArtifact:
    def test_missing_directory_raises_clear_error(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="does not exist"):
            load_candidate_artifact(tmp_path / "nope")

    def test_missing_config_json_raises_clear_error(self, tmp_path: Path) -> None:
        candidate_dir = tmp_path / "candidate"
        candidate_dir.mkdir()
        (candidate_dir / "features.json").write_text(
            json.dumps({"feature_columns": ["momentum_252_21"]}), encoding="utf-8"
        )
        with pytest.raises(ValueError, match="config.json"):
            load_candidate_artifact(candidate_dir)

    def test_missing_features_json_raises_clear_error(self, tmp_path: Path) -> None:
        candidate_dir = tmp_path / "candidate"
        candidate_dir.mkdir()
        (candidate_dir / "config.json").write_text("{}", encoding="utf-8")
        with pytest.raises(ValueError, match="features.json"):
            load_candidate_artifact(candidate_dir)

    def test_rule_based_placeholder_without_score_column_raises(self, tmp_path: Path) -> None:
        candidate_dir = tmp_path / "candidate"
        candidate_dir.mkdir()
        (candidate_dir / "config.json").write_text("{}", encoding="utf-8")
        (candidate_dir / "features.json").write_text(
            json.dumps({"feature_columns": ["momentum_252_21"]}), encoding="utf-8"
        )
        with pytest.raises(ValueError, match="score_column"):
            load_candidate_artifact(candidate_dir)

    def test_real_momentum_placeholder_artifact_loads(self, repo_root: Path) -> None:
        candidate_dir = (
            repo_root / "config" / "model_ranking_candidates" / "step11_momentum_placeholder_v1"
        )
        artifact = load_candidate_artifact(candidate_dir)
        assert artifact.is_placeholder is True
        assert artifact.model.score_column == "momentum_252_21"  # type: ignore[attr-defined]
        assert artifact.features["feature_columns"] == ["momentum_252_21"]

    def test_model_joblib_is_used_directly_with_no_predict_wrapper(self, tmp_path: Path) -> None:
        candidate_dir = _fitted_candidate_dir(tmp_path)

        artifact = load_candidate_artifact(candidate_dir)

        assert artifact.is_placeholder is False
        frame = pd.DataFrame(
            {"symbol": ["AAA", "BBB", "CCC"], "momentum_252_21": [0.30, 0.20, 0.10]}
        )
        scores = artifact.model.score(frame)
        # The fixture model ranks ascending (inverse of momentum) -- if this
        # module silently fell back to the placeholder rule instead of
        # calling the fitted model's own .score(), CCC (lowest momentum)
        # would not come out on top.
        assert scores.idxmax() == "CCC"

    def test_model_joblib_missing_score_method_raises_clear_error(self, tmp_path: Path) -> None:
        import joblib

        candidate_dir = tmp_path / "candidate"
        candidate_dir.mkdir()
        (candidate_dir / "config.json").write_text("{}", encoding="utf-8")
        (candidate_dir / "features.json").write_text(
            json.dumps({"feature_columns": ["momentum_252_21"]}), encoding="utf-8"
        )
        joblib.dump(object(), candidate_dir / "model.joblib")

        with pytest.raises(ValueError, match="\\.score"):
            load_candidate_artifact(candidate_dir)


class TestMostRecentRebalanceDate:
    def test_friday_is_its_own_rebalance_date(self) -> None:
        assert most_recent_rebalance_date(SIGNAL_DATE.date()) == SIGNAL_DATE.date()

    def test_midweek_after_a_holiday_monday_falls_back_to_prior_friday(self) -> None:
        assert most_recent_rebalance_date(HOLD_DATE.date()) == SIGNAL_DATE.date()


class TestRunModelRankingTargetWeightMapping:
    def test_missing_candidate_artifact_dir_raises_clear_error(
        self, tmp_path: Path, repo_root: Path
    ) -> None:
        missing_dir = tmp_path / "candidates" / "does_not_exist"
        spec_path = _write_spec(tmp_path, repo_root, candidate_dir=missing_dir)
        _write_daily_features(tmp_path, [SIGNAL_DATE])
        _write_universe(tmp_path, month_end=SIGNAL_DATE)

        with pytest.raises(ValueError, match="does not exist"):
            run_model_ranking_target_weight_mapping(
                spec_path, tmp_path, account_equity_override=100_000.0
            )

    def test_zero_holdings_start_produces_full_top_k_target(
        self, tmp_path: Path, repo_root: Path
    ) -> None:
        candidate_dir = _candidate_dir(tmp_path, top_k=3)
        spec_path = _write_spec(tmp_path, repo_root, candidate_dir=candidate_dir, top_k=3)
        _write_daily_features(tmp_path, [SIGNAL_DATE])
        _write_universe(tmp_path, month_end=SIGNAL_DATE)

        result = run_model_ranking_target_weight_mapping(
            spec_path, tmp_path, account_equity_override=100_000.0
        )

        assert result.is_new_signal is True
        assert result.nonzero_target_rows == 3
        assert result.signal_count == 3  # every held name is a fresh entry from zero
        assert result.candidate_is_placeholder is True

        payload = json.loads(result.json_path.read_text(encoding="utf-8"))
        rows = payload["target_weights"]
        held = {row["symbol"]: row for row in rows if row["selected"]}
        assert set(held) == {"AAA", "BBB", "CCC"}  # top-3 by momentum_252_21
        for row in held.values():
            assert row["target_weight"] == pytest.approx(1.0 / 3.0)
            assert row["shares"] > 0
            assert row["state"] == "signal"
        signal_lines = result.signal_log_path.read_text(encoding="utf-8").splitlines()
        assert len(signal_lines) == 3
        for line in signal_lines:
            record = json.loads(line)
            assert record["action"] == "entry"

    def test_non_rebalance_day_holds_previous_target_not_empty(
        self, tmp_path: Path, repo_root: Path
    ) -> None:
        candidate_dir = _candidate_dir(tmp_path, top_k=3)
        spec_path = _write_spec(tmp_path, repo_root, candidate_dir=candidate_dir, top_k=3)
        _write_daily_features(tmp_path, [SIGNAL_DATE])
        _write_universe(tmp_path, month_end=SIGNAL_DATE)
        first = run_model_ranking_target_weight_mapping(
            spec_path, tmp_path, account_equity_override=100_000.0
        )
        assert first.is_new_signal is True

        # Advance the feature archive to a non-rebalance day (Tuesday after a
        # Labor Day Monday); nothing about the top-K membership changes.
        _write_daily_features(tmp_path, [SIGNAL_DATE, HOLD_DATE])

        second = run_model_ranking_target_weight_mapping(
            spec_path, tmp_path, account_equity_override=100_000.0
        )

        assert second.is_new_signal is False
        assert second.signal_count == 0  # a hold day logs no new signals
        assert second.nonzero_target_rows == 3  # still the full target, never empty

        payload = json.loads(second.json_path.read_text(encoding="utf-8"))
        rows = payload["target_weights"]
        held = {row["symbol"]: row for row in rows if row["selected"]}
        assert set(held) == {"AAA", "BBB", "CCC"}
        for row in held.values():
            assert row["state"] == "hold_no_new_signal"
            assert row["target_weight"] == pytest.approx(1.0 / 3.0)
        # No intents/order requirements on a hold day.
        assert payload["summary"]["order_required_intents"] == 0
        # Prices are re-derived from the latest available day even on a hold.
        assert (
            payload["data_profile"]["latest_available_trade_date"] == HOLD_DATE.date().isoformat()
        )
        assert payload["data_profile"]["signal_session"] == SIGNAL_DATE.date().isoformat()

    def test_missing_account_equity_snapshot_raises_clear_error(
        self, tmp_path: Path, repo_root: Path
    ) -> None:
        candidate_dir = _candidate_dir(tmp_path, top_k=3)
        spec_path = _write_spec(tmp_path, repo_root, candidate_dir=candidate_dir, top_k=3)
        _write_daily_features(tmp_path, [SIGNAL_DATE])
        _write_universe(tmp_path, month_end=SIGNAL_DATE)

        with pytest.raises(ValueError, match="oc paper sync-account"):
            run_model_ranking_target_weight_mapping(spec_path, tmp_path)

    def test_spy_beta_hedge_leg_is_sized_and_labeled(self, tmp_path: Path, repo_root: Path) -> None:
        candidate_dir = _candidate_dir(tmp_path, top_k=3, hedge="spy_beta_hedge")
        spec_path = _write_spec(
            tmp_path, repo_root, candidate_dir=candidate_dir, top_k=3, hedge="spy_beta_hedge"
        )
        _write_daily_features(tmp_path, [SIGNAL_DATE])
        _write_universe(tmp_path, month_end=SIGNAL_DATE)

        result = run_model_ranking_target_weight_mapping(
            spec_path, tmp_path, account_equity_override=100_000.0
        )

        payload = json.loads(result.json_path.read_text(encoding="utf-8"))
        hedge_rows = [row for row in payload["target_weights"] if row["leg"] == "beta_hedge"]
        assert len(hedge_rows) == 1
        assert hedge_rows[0]["symbol"] == "SPY"
        assert hedge_rows[0]["target_weight"] < 0  # short leg
        assert hedge_rows[0]["shares"] < 0
        assert payload["summary"]["portfolio_beta"] == pytest.approx(1.0)

    def test_fitted_model_joblib_drives_selection_end_to_end(
        self, tmp_path: Path, repo_root: Path
    ) -> None:
        candidate_dir = _fitted_candidate_dir(tmp_path)
        spec_path = _write_spec(tmp_path, repo_root, candidate_dir=candidate_dir, top_k=3)
        _write_daily_features(tmp_path, [SIGNAL_DATE])
        _write_universe(tmp_path, month_end=SIGNAL_DATE)

        result = run_model_ranking_target_weight_mapping(
            spec_path, tmp_path, account_equity_override=100_000.0
        )

        assert result.candidate_is_placeholder is False
        payload = json.loads(result.json_path.read_text(encoding="utf-8"))
        held = {row["symbol"] for row in payload["target_weights"] if row["selected"]}
        # The fixture model ranks ascending (inverse of momentum_252_21), so
        # the bottom-3-by-momentum names (CCC, DDD, EEE) should be selected
        # instead of the top-3 (AAA, BBB, CCC) the placeholder would pick.
        assert held == {"CCC", "DDD", "EEE"}


class TestDerivedRatioScoreModel:
    def test_score_is_numerator_over_denominator(self) -> None:
        frame = pd.DataFrame(
            {"symbol": ["AAA", "BBB"], "momentum_252_21": [0.30, 0.25], "vol_63": [0.30, 0.10]}
        )
        model = DerivedRatioScoreModel(
            numerator_column="momentum_252_21", denominator_column="vol_63"
        )
        scores = model.score(frame)
        assert scores.loc["AAA"] == pytest.approx(1.0)
        assert scores.loc["BBB"] == pytest.approx(2.5)

    def test_zero_denominator_maps_to_nan_not_inf(self) -> None:
        frame = pd.DataFrame({"symbol": ["AAA"], "momentum_252_21": [0.30], "vol_63": [0.0]})
        model = DerivedRatioScoreModel(
            numerator_column="momentum_252_21", denominator_column="vol_63"
        )
        scores = model.score(frame)
        assert pd.isna(scores.loc["AAA"])


class TestLoadCandidateArtifactScoreExpression:
    def test_score_expression_loads_derived_ratio_model(self, tmp_path: Path) -> None:
        candidate_dir = _derived_ratio_candidate_dir(tmp_path)

        artifact = load_candidate_artifact(candidate_dir)

        assert artifact.is_placeholder is True
        assert isinstance(artifact.model, DerivedRatioScoreModel)
        assert artifact.model.numerator_column == "momentum_252_21"
        assert artifact.model.denominator_column == "vol_63"

    def test_wrong_model_kind_raises(self, tmp_path: Path) -> None:
        candidate_dir = tmp_path / "candidate"
        candidate_dir.mkdir()
        (candidate_dir / "config.json").write_text(
            json.dumps(
                {
                    "model_kind": "rule_momentum_top_k",
                    "score_expression": {"numerator": "a", "denominator": "b"},
                }
            ),
            encoding="utf-8",
        )
        (candidate_dir / "features.json").write_text(
            json.dumps({"feature_columns": ["a", "b"]}), encoding="utf-8"
        )
        with pytest.raises(ValueError, match="rule_derived_ratio_top_k"):
            load_candidate_artifact(candidate_dir)

    def test_blank_numerator_or_denominator_raises(self, tmp_path: Path) -> None:
        candidate_dir = tmp_path / "candidate"
        candidate_dir.mkdir()
        (candidate_dir / "config.json").write_text(
            json.dumps(
                {
                    "model_kind": "rule_derived_ratio_top_k",
                    "score_expression": {"numerator": "", "denominator": "vol_63"},
                }
            ),
            encoding="utf-8",
        )
        (candidate_dir / "features.json").write_text(
            json.dumps({"feature_columns": ["momentum_252_21", "vol_63"]}), encoding="utf-8"
        )
        with pytest.raises(ValueError, match="numerator"):
            load_candidate_artifact(candidate_dir)

    def test_column_not_in_feature_columns_raises(self, tmp_path: Path) -> None:
        candidate_dir = tmp_path / "candidate"
        candidate_dir.mkdir()
        (candidate_dir / "config.json").write_text(
            json.dumps(
                {
                    "model_kind": "rule_derived_ratio_top_k",
                    "score_expression": {"numerator": "momentum_252_21", "denominator": "vol_999"},
                }
            ),
            encoding="utf-8",
        )
        (candidate_dir / "features.json").write_text(
            json.dumps({"feature_columns": ["momentum_252_21", "vol_63"]}), encoding="utf-8"
        )
        with pytest.raises(ValueError, match="denominator"):
            load_candidate_artifact(candidate_dir)

    def test_existing_placeholder_still_loads_unchanged(self, repo_root: Path) -> None:
        # Regression guard for deliverable 1's "keep every existing default"
        # requirement: the real placeholder candidate has no
        # score_expression key at all and must still hit the score_column
        # path exactly as before.
        candidate_dir = (
            repo_root / "config" / "model_ranking_candidates" / "step11_momentum_placeholder_v1"
        )
        artifact = load_candidate_artifact(candidate_dir)
        assert artifact.is_placeholder is True
        assert isinstance(artifact.model, MomentumPlaceholderModel)


class TestTrendGateState:
    def test_gate_open_when_close_above_trailing_sma(self, tmp_path: Path) -> None:
        dates = pd.bdate_range(end=SIGNAL_DATE, periods=15)
        closes = [float(100 + i) for i in range(15)]  # ascending
        _write_sip_daily_archive(tmp_path, {"SPY": (dates, closes)})

        is_open, detail = trend_gate_state(
            tmp_path,
            {"benchmark": "SPY", "sma_days": 5, "cash_symbol": "BIL"},
            as_of=SIGNAL_DATE,
        )

        assert is_open is True
        assert detail["gate_open"] is True
        assert detail["close"] > detail["sma"]

    def test_gate_closed_when_close_below_trailing_sma(self, tmp_path: Path) -> None:
        dates = pd.bdate_range(end=SIGNAL_DATE, periods=15)
        closes = [float(114 - i) for i in range(15)]  # descending
        _write_sip_daily_archive(tmp_path, {"SPY": (dates, closes)})

        is_open, detail = trend_gate_state(
            tmp_path,
            {"benchmark": "SPY", "sma_days": 5, "cash_symbol": "BIL"},
            as_of=SIGNAL_DATE,
        )

        assert is_open is False
        assert detail["gate_open"] is False
        assert detail["close"] < detail["sma"]

    def test_insufficient_history_raises_clear_error(self, tmp_path: Path) -> None:
        dates = pd.bdate_range(end=SIGNAL_DATE, periods=3)
        closes = [100.0, 101.0, 102.0]
        _write_sip_daily_archive(tmp_path, {"SPY": (dates, closes)})

        with pytest.raises(ValueError, match="trading sessions"):
            trend_gate_state(
                tmp_path,
                {"benchmark": "SPY", "sma_days": 5, "cash_symbol": "BIL"},
                as_of=SIGNAL_DATE,
            )


class TestRunModelRankingTargetWeightMappingTrendGate:
    _TREND_GATE = {"benchmark": "SPY", "sma_days": 5, "cash_symbol": "BIL"}

    def test_gate_closed_routes_full_book_to_cash_symbol(
        self, tmp_path: Path, repo_root: Path
    ) -> None:
        candidate_dir = _derived_ratio_candidate_dir(tmp_path, top_k=3, trend_gate=self._TREND_GATE)
        spec_path = _write_spec(tmp_path, repo_root, candidate_dir=candidate_dir, top_k=3)
        _write_daily_features_with_vol(tmp_path, [SIGNAL_DATE])
        _write_universe(tmp_path, month_end=SIGNAL_DATE)
        dates = pd.bdate_range(end=SIGNAL_DATE, periods=15)
        spy_closes = [float(114 - i) for i in range(15)]  # descending -> gate closed
        _write_sip_daily_archive(
            tmp_path, {"SPY": (dates, spy_closes), "BIL": (dates, [91.5] * 15)}
        )

        result = run_model_ranking_target_weight_mapping(
            spec_path, tmp_path, account_equity_override=100_000.0
        )

        assert result.is_new_signal is True
        payload = json.loads(result.json_path.read_text(encoding="utf-8"))
        held = {row["symbol"]: row for row in payload["target_weights"] if row["selected"]}
        assert set(held) == {"BIL"}
        assert held["BIL"]["target_weight"] == pytest.approx(1.0)
        assert held["BIL"]["shares"] > 0
        assert payload["summary"]["trend_gate_open"] is False
        assert payload["summary"]["trend_gate"] == self._TREND_GATE

    def test_gate_open_ranks_by_derived_ratio_not_raw_momentum(
        self, tmp_path: Path, repo_root: Path
    ) -> None:
        candidate_dir = _derived_ratio_candidate_dir(tmp_path, top_k=3, trend_gate=self._TREND_GATE)
        spec_path = _write_spec(tmp_path, repo_root, candidate_dir=candidate_dir, top_k=3)
        _write_daily_features_with_vol(tmp_path, [SIGNAL_DATE])
        _write_universe(tmp_path, month_end=SIGNAL_DATE)
        dates = pd.bdate_range(end=SIGNAL_DATE, periods=15)
        spy_closes = [float(100 + i) for i in range(15)]  # ascending -> gate open
        _write_sip_daily_archive(
            tmp_path, {"SPY": (dates, spy_closes), "BIL": (dates, [91.5] * 15)}
        )

        result = run_model_ranking_target_weight_mapping(
            spec_path, tmp_path, account_equity_override=100_000.0
        )

        payload = json.loads(result.json_path.read_text(encoding="utf-8"))
        held = {row["symbol"] for row in payload["target_weights"] if row["selected"]}
        # Ranking by momentum_252_21/vol_63 (CCC 4.0, DDD 3.0, BBB 2.5, EEE
        # 2.0, AAA 1.0) picks CCC/DDD/BBB -- not AAA/BBB/CCC, which is what
        # raw momentum_252_21 alone would pick (see module-level VOL_63).
        assert held == {"CCC", "DDD", "BBB"}
        assert payload["summary"]["trend_gate_open"] is True

    def test_candidate_without_trend_gate_key_never_touches_sip_archive(
        self, tmp_path: Path, repo_root: Path
    ) -> None:
        # No data/sip/ directory exists at all in this tmp_path -- if the
        # adapter tried to read one for a candidate with no trend_gate key,
        # this would raise. Regression guard for "zero extra I/O when the
        # key is absent" (module docstring).
        candidate_dir = _derived_ratio_candidate_dir(tmp_path, top_k=3, trend_gate=None)
        spec_path = _write_spec(tmp_path, repo_root, candidate_dir=candidate_dir, top_k=3)
        _write_daily_features_with_vol(tmp_path, [SIGNAL_DATE])
        _write_universe(tmp_path, month_end=SIGNAL_DATE)

        result = run_model_ranking_target_weight_mapping(
            spec_path, tmp_path, account_equity_override=100_000.0
        )

        payload = json.loads(result.json_path.read_text(encoding="utf-8"))
        held = {row["symbol"] for row in payload["target_weights"] if row["selected"]}
        assert held == {"CCC", "DDD", "BBB"}
        assert payload["summary"]["trend_gate"] is None
        assert payload["summary"]["trend_gate_open"] is None
