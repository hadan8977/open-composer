"""Tests for scripts/export_candidate_artifact.py.

Strategy: never touch the real 6M-row data/features/daily/*.parquet archive
or the real ledger -- monkeypatch ``load_feature_panel`` (the memory-lean
DuckDB-backed panel loader this script calls, 2026-09-09 rewrite) to return
a small synthetic panel, and point LEDGER_PATH at a tmp_path fixture ledger
with a hand-written record matching the real ledger's schema (see
loop.py::run_experiment's record dict). B1 (parameter-free momentum) is
used for the full-pipeline test since its ``fit`` is a no-op -- this
exercises every step of ``export_candidate_artifact`` (registry lookup,
ledger lookup, panel load, full-history train-frame construction, joblib
dump, three metadata files) without paying for a real model fit.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import export_candidate_artifact as eca  # noqa: E402

SYMBOLS = ["AAA", "BBB", "CCC"]


def _synthetic_panel(n_days: int = 40) -> pd.DataFrame:
    dates = pd.bdate_range("2024-01-02", periods=n_days)
    rng = np.random.default_rng(2)
    rows = []
    for symbol in SYMBOLS:
        price = 100.0
        for i, date in enumerate(dates):
            price *= 1.0 + rng.normal(0, 0.01)
            rows.append(
                {
                    "symbol": symbol,
                    "trade_date": date,
                    "close": price,
                    "momentum_252_21": rng.normal(0, 1),
                    # Last 3 rows unresolved, like a real forward label near
                    # the end of history -- exercises the "no explicit
                    # embargo, the notna mask alone drops these" behavior
                    # _build_full_history_train_frame's docstring describes.
                    "label_rank_5": rng.uniform(0, 1) if i < n_days - 3 else np.nan,
                }
            )
    return pd.DataFrame(rows)


def _ledger_record(**overrides: object) -> dict[str, object]:
    record = {
        "experiment_id": "step11_b1_momentum_top50",
        "config_hash": "deadbeefcafef00d",
        "family": "step11_baseline_chain",
        "model_kind": "b1_momentum",
        "feature_set": "daily_only",
        "label_horizon_days": 5,
        "top_k": 50,
        "hedge": "spy_beta_hedge",
        "hyperparameters": {},
        "test_years": [2024],
        "dsr_trial_count": 2,
        "long_only": {
            "metrics": {"cagr_excess_vol_matched_benchmark": -0.05},
            "gate_results": {"cagr_excess_vol_matched_benchmark": False, "mar": True},
            "all_gates_pass": False,
            "sharpe_excess_bil": 0.4,
        },
        "market_neutral": {
            "metrics": {"cagr_excess_vol_matched_benchmark": -0.2},
            "gate_results": {"cagr_excess_vol_matched_benchmark": False, "mar": False},
            "all_gates_pass": False,
            "sharpe_excess_bil": -0.6,
        },
        "tearsheet_path": "reports/research/tearsheets/step11_b1_momentum_top50.html",
        "mlflow_run_id": "abc123",
        "recorded_at": "2026-09-08T00:00:00+00:00",
    }
    record.update(overrides)
    return record


def _v2_ledger_record(**overrides: object) -> dict[str, object]:
    """Shape matches ``scripts/run_step13_m_grid.py::_append_v2_ledger_record``
    exactly (dataclasses.asdict of a ``RecentHighReturnVerdict`` plus the
    owning ``ExperimentConfig``'s own fields) -- the v1 ``_ledger_record``
    fixture above predates the v2 gate contract and has a different shape
    (``long_only``/``market_neutral`` sub-objects instead of a flat
    ``metrics``/``gate_results``), so rule-candidate export tests need
    their own fixture.
    """
    record: dict[str, object] = {
        "experiment_id": "step13_m0b_mom_over_vol63_uni500_k50_gate_off",
        "config_hash": "abc123v2",
        "family": "step13_recent_high_return",
        "model_kind": "rule_single_factor",
        "hyperparameters": {"score_column": "momentum_252_21_over_vol_63"},
        "trend_gate": None,
        "universe_top_n": 500,
        "dsr_trial_count": 24,
        "metrics": {
            "cagr_recent_net": 0.330,
            "max_drawdown_recent": -0.283,
            "hit_rate_weekly": 0.616,
            "cagr_excess_vol_matched_spy": -0.05,
        },
        "disclosure": {"turnover_annualized_recent": 12.0},
        "gate_results": {
            "cagr_recent_net_minimum": True,
            "cagr_excess_vol_matched_spy_minimum": False,
            "max_drawdown_recent_minimum": False,
        },
        "gates_not_applicable": ["ml_placebo_rank_ic_abs_maximum"],
        "all_gates_pass": False,
        "promotion_eligible": False,
        "gate_contract": "recent_regime_high_return_gates_v2",
        "recorded_at": "2026-09-10T09:00:00+00:00",
    }
    record.update(overrides)
    return record


@pytest.fixture
def v2_ledger_path(tmp_path: Path) -> Path:
    path = tmp_path / "v2_experiments.jsonl"
    path.write_text(json.dumps(_v2_ledger_record()) + "\n")
    return path


@pytest.fixture
def ledger_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "experiments.jsonl"
    path.write_text(json.dumps(_ledger_record()) + "\n")
    monkeypatch.setattr(eca, "LEDGER_PATH", path)
    return path


@pytest.fixture
def patched_panel_loader(monkeypatch: pytest.MonkeyPatch) -> pd.DataFrame:
    panel = _synthetic_panel()
    monkeypatch.setattr(
        eca, "load_feature_panel", lambda feature_columns, label_columns, **kwargs: panel
    )  # noqa: ARG005
    return panel


def test_export_writes_all_four_artifacts_with_a_working_model(
    tmp_path: Path, ledger_path: Path, patched_panel_loader: pd.DataFrame
) -> None:
    out_root = tmp_path / "candidates"
    out_dir = eca.export_candidate_artifact("step11_b1_momentum_top50", out_root=out_root)

    assert out_dir == out_root / "step11_b1_momentum_top50"
    for name in ("model.joblib", "features.json", "config.json", "README.md"):
        assert (out_dir / name).exists(), name

    features = json.loads((out_dir / "features.json").read_text())
    assert features["feature_columns"] == ["momentum_252_21"]
    assert features["label_column"] == "label_rank_5"
    assert features["top_k"] == 50
    assert features["hedge"] == "spy_beta_hedge"
    # Ledger record predates train_row_dates/execution (like every real B0-B2
    # record recorded before 2026-09-08) -- must default, not KeyError.
    assert features["train_row_dates"] == "all"
    assert features["execution"] == "close_marked"
    # Last 3 rows of each symbol have an unresolved label_rank_5 (NaN) --
    # refit_through_date must reflect the last row that actually had one,
    # not the panel's absolute last date.
    expected_last_date = _synthetic_panel()["trade_date"].iloc[-4]  # 4th-from-last row overall
    assert pd.Timestamp(features["refit_through_date"]) <= expected_last_date

    config = json.loads((out_dir / "config.json").read_text())
    assert config["feature_columns"] == ["momentum_252_21"]
    assert config["experiment_id"] == "step11_b1_momentum_top50"

    readme = (out_dir / "README.md").read_text()
    assert "step11_b1_momentum_top50" in readme
    assert "NOT promotion-approved" in readme

    # The exported object must be immediately usable via the RankingStrategy
    # protocol -- the whole point of exporting the strategy object itself
    # rather than a bare sklearn/LightGBM model (see the ledger's Wave B
    # item 5 design-tradeoff note).
    model = joblib.load(out_dir / "model.joblib")
    asof_frame = pd.DataFrame({"symbol": SYMBOLS, "momentum_252_21": [0.5, -0.5, 0.1]})
    scores = model.score(asof_frame)
    assert set(scores.index) == set(SYMBOLS)
    assert scores.loc["AAA"] == pytest.approx(0.5)


def test_export_is_idempotent_and_overwrites_cleanly(
    tmp_path: Path, ledger_path: Path, patched_panel_loader: pd.DataFrame
) -> None:
    out_root = tmp_path / "candidates"
    first = eca.export_candidate_artifact("step11_b1_momentum_top50", out_root=out_root)
    second = eca.export_candidate_artifact("step11_b1_momentum_top50", out_root=out_root)
    assert first == second
    assert (second / "model.joblib").exists()


def test_unknown_experiment_id_raises(tmp_path: Path, ledger_path: Path) -> None:
    with pytest.raises(SystemExit, match="no registry entry"):
        eca.export_candidate_artifact("not_a_real_experiment_id", out_root=tmp_path / "candidates")


def test_missing_ledger_record_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    empty_ledger = tmp_path / "empty.jsonl"
    empty_ledger.write_text("")
    monkeypatch.setattr(eca, "LEDGER_PATH", empty_ledger)
    with pytest.raises(SystemExit, match="no ledger record"):
        eca.export_candidate_artifact("step11_b1_momentum_top50", out_root=tmp_path / "candidates")


@pytest.mark.parametrize(
    ("experiment_id", "expected_base"),
    [
        ("step11_b3_lightgbm_grid_daily_only", "step11_b3_lightgbm_grid_daily_only"),
        ("step11_b3_lightgbm_grid_daily_only_next_open", "step11_b3_lightgbm_grid_daily_only"),
        ("step11_b1_momentum_top50", "step11_b1_momentum_top50"),
    ],
)
def test_base_experiment_id_strips_next_open_suffix_only(
    experiment_id: str, expected_base: str
) -> None:
    assert eca._base_experiment_id(experiment_id) == expected_base


def test_build_full_history_train_frame_drops_unresolved_tail_labels() -> None:
    panel = _synthetic_panel()
    train_frame, refit_through_date = eca._build_full_history_train_frame(
        panel,
        feature_columns=["momentum_252_21"],
        label_column="label_rank_5",
        extra_train_columns=(),
        train_row_dates="all",
    )
    assert train_frame["label_rank_5"].notna().all()
    assert refit_through_date < panel["trade_date"].max()


def test_build_full_history_train_frame_rebalance_dates_restricts_to_weekly_rows() -> None:
    panel = _synthetic_panel()
    from open_composer.research.kernel import loop

    trading_calendar = pd.DatetimeIndex(sorted(panel["trade_date"].unique()))
    weekly = set(loop.weekly_rebalance_dates(trading_calendar))

    train_frame, _ = eca._build_full_history_train_frame(
        panel,
        feature_columns=["momentum_252_21"],
        label_column="label_rank_5",
        extra_train_columns=(),
        train_row_dates="rebalance_dates",
    )
    assert set(train_frame["trade_date"]) <= weekly
    assert not train_frame.empty


def test_build_full_history_train_frame_rejects_unknown_train_row_dates() -> None:
    panel = _synthetic_panel()
    with pytest.raises(ValueError, match="train_row_dates"):
        eca._build_full_history_train_frame(
            panel,
            feature_columns=["momentum_252_21"],
            label_column="label_rank_5",
            extra_train_columns=(),
            train_row_dates="bogus",
        )


class TestFindFamilyLedgerRecord:
    def test_filters_by_family_not_just_experiment_id(self, tmp_path: Path) -> None:
        path = tmp_path / "experiments.jsonl"
        path.write_text(
            "\n".join(
                json.dumps(rec)
                for rec in (
                    {"experiment_id": "dup", "family": "family_a", "metrics": {"x": 1}},
                    {"experiment_id": "dup", "family": "family_b", "metrics": {"x": 2}},
                )
            )
            + "\n"
        )
        record = eca._find_family_ledger_record("dup", "family_b", ledger_path=path)
        assert record is not None
        assert record["metrics"]["x"] == 2

    def test_returns_none_when_ledger_file_missing(self, tmp_path: Path) -> None:
        missing = tmp_path / "nope.jsonl"
        assert eca._find_family_ledger_record("x", "y", ledger_path=missing) is None

    def test_returns_none_when_no_matching_record(self, tmp_path: Path) -> None:
        path = tmp_path / "experiments.jsonl"
        path.write_text(json.dumps({"experiment_id": "other", "family": "f"}) + "\n")
        assert eca._find_family_ledger_record("x", "f", ledger_path=path) is None


class TestExportRuleCandidateArtifact:
    """Step 13 Track M product path: a rule candidate scored by a derived
    ratio (config.json:score_expression), no model.joblib, source ledger
    metrics/gates quoted verbatim in the README.
    """

    def test_writes_config_features_readme_no_model_joblib(
        self, tmp_path: Path, v2_ledger_path: Path
    ) -> None:
        out_root = tmp_path / "candidates"
        out_dir = eca.export_rule_candidate_artifact(
            "step13_rule_mom_over_vol63_uni500_k50_gate_off",
            source_ledger_experiment_id="step13_m0b_mom_over_vol63_uni500_k50_gate_off",
            score_expression={"numerator": "momentum_252_21", "denominator": "vol_63"},
            universe_top_n=500,
            top_k=50,
            trend_gate=None,
            out_root=out_root,
            ledger_path=v2_ledger_path,
        )

        assert out_dir == out_root / "step13_rule_mom_over_vol63_uni500_k50_gate_off"
        assert not (out_dir / "model.joblib").exists()
        for name in ("config.json", "features.json", "README.md"):
            assert (out_dir / name).exists(), name

        config = json.loads((out_dir / "config.json").read_text())
        assert config["model_kind"] == "rule_derived_ratio_top_k"
        assert config["score_expression"] == {
            "numerator": "momentum_252_21",
            "denominator": "vol_63",
        }
        assert config["universe_top_n"] == 500
        assert config["top_k"] == 50
        assert config["trend_gate"] is None
        assert config["source_ledger_experiment_id"] == (
            "step13_m0b_mom_over_vol63_uni500_k50_gate_off"
        )

        features = json.loads((out_dir / "features.json").read_text())
        assert features["feature_columns"] == ["momentum_252_21", "vol_63"]
        assert features["top_k"] == 50

        readme = (out_dir / "README.md").read_text()
        assert "step13_m0b_mom_over_vol63_uni500_k50_gate_off" in readme
        assert "0.33" in readme  # cagr_recent_net, quoted verbatim from the ledger
        assert "cagr_excess_vol_matched_spy_minimum" in readme  # a failed gate, named
        assert "all_gates_pass" in readme
        assert "False" in readme
        assert "NOT promotion-approved" in readme

    def test_trend_gate_block_is_written_when_provided(
        self, tmp_path: Path, v2_ledger_path: Path
    ) -> None:
        trend_gate = {"benchmark": "SPY", "sma_days": 200, "cash_symbol": "BIL"}
        # v2_ledger_path only has a record for the uni500/gate_off cell (see
        # _v2_ledger_record) -- this experiment_id has no match, exercising
        # the "no ledger record found" README path at the same time as the
        # trend_gate block, rather than needing a second ledger fixture.
        out_dir = eca.export_rule_candidate_artifact(
            "step13_rule_mom_over_vol63_uni200_k50_gate_on",
            source_ledger_experiment_id="step13_m0b_mom_over_vol63_uni200_k50_gate_on",
            score_expression={"numerator": "momentum_252_21", "denominator": "vol_63"},
            universe_top_n=200,
            top_k=50,
            trend_gate=trend_gate,
            out_root=tmp_path / "candidates",
            ledger_path=v2_ledger_path,
        )

        config = json.loads((out_dir / "config.json").read_text())
        assert config["trend_gate"] == trend_gate
        readme = (out_dir / "README.md").read_text()
        assert "No ledger record found" in readme
        assert "BIL" in readme

    def test_missing_ledger_record_does_not_raise(self, tmp_path: Path) -> None:
        empty_ledger = tmp_path / "empty.jsonl"
        empty_ledger.write_text("")

        out_dir = eca.export_rule_candidate_artifact(
            "some_candidate",
            source_ledger_experiment_id="does_not_exist",
            score_expression={"numerator": "a", "denominator": "b"},
            universe_top_n=500,
            top_k=50,
            trend_gate=None,
            out_root=tmp_path / "candidates",
            ledger_path=empty_ledger,
        )

        assert (out_dir / "README.md").exists()
        assert "No ledger record found" in (out_dir / "README.md").read_text()

    def test_is_idempotent_and_overwrites_cleanly(
        self, tmp_path: Path, v2_ledger_path: Path
    ) -> None:
        out_root = tmp_path / "candidates"
        kwargs = dict(
            source_ledger_experiment_id="step13_m0b_mom_over_vol63_uni500_k50_gate_off",
            score_expression={"numerator": "momentum_252_21", "denominator": "vol_63"},
            universe_top_n=500,
            top_k=50,
            trend_gate=None,
            out_root=out_root,
            ledger_path=v2_ledger_path,
        )
        first = eca.export_rule_candidate_artifact("dup_test", **kwargs)
        second = eca.export_rule_candidate_artifact("dup_test", **kwargs)
        assert first == second == out_root / "dup_test"
