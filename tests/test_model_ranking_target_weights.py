from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest
import yaml

from open_composer.adapters.execution.model_ranking_target_weights import (
    load_candidate_artifact,
    most_recent_rebalance_date,
    run_model_ranking_target_weight_mapping,
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
    candidate_dir = root / "candidates" / "test_momentum_placeholder"
    candidate_dir.mkdir(parents=True, exist_ok=True)
    (candidate_dir / "config.json").write_text(
        json.dumps(
            {
                "candidate_id": "test_momentum_placeholder",
                "strategy_kind": "rule_momentum_top_k",
                "score_column": "momentum_252_21",
            }
        ),
        encoding="utf-8",
    )
    (candidate_dir / "features.json").write_text(
        json.dumps(
            {
                "feature_set_id": "daily_only",
                "feature_columns": ["momentum_252_21"],
                "label_horizon_days": 21,
                "top_k": top_k,
                "hedge": hedge,
                "beta_column": "beta_252_spy",
            }
        ),
        encoding="utf-8",
    )
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
