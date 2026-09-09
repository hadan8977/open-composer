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
