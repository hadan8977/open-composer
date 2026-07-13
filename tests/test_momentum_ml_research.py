from __future__ import annotations

from pathlib import Path

import pandas as pd
from typer.testing import CliRunner

from open_composer.cli import app
from open_composer.research.momentum_ml_research import (
    _eligible_windows,
    _entry_events,
    _feature_frame,
    _gate_position,
    _trial_definitions,
    write_momentum_ml_design,
)


def test_features_are_strictly_index_minus_one() -> None:
    frame = _aligned_frame(100)
    features = _feature_frame(frame)
    expected_roc = frame["signal_close"].iloc[72] / frame["signal_close"].iloc[0] - 1

    assert features.iloc[-1]["qqq_roc_12_index_minus_1"] == (
        frame["signal_close"].iloc[-2] / frame["signal_close"].iloc[-14] - 1
    )
    assert pd.isna(features.iloc[72]["qqq_roc_72_index_minus_1"])
    assert features.iloc[73]["qqq_roc_72_index_minus_1"] == expected_roc


def test_entry_label_uses_aligned_future_tqqq_returns_after_cost() -> None:
    frame = _aligned_frame(120)
    position = pd.Series(0.0, index=frame.index)
    position.iloc[80:90] = 1.0
    events = _entry_events(frame, position, _feature_frame(frame))

    assert len(events) == 1
    path = frame["next_trade_return"].iloc[80:90]
    expected = (1.0 + path).prod() - 1.0 - 0.0006
    assert events.iloc[0]["forward_net_return"] == expected
    assert events.iloc[0]["episode_bars"] == 10
    assert events.iloc[0]["label"] == int(expected > 0)


def test_meta_gate_never_creates_entry_and_missing_decision_falls_back() -> None:
    baseline = pd.Series([0.0, 1.0, 1.0, 0.0, 1.0, 1.0])
    events = pd.DataFrame({"bar_index": [1], "label": [1]})
    accepted = pd.Series([False], index=events.index)

    gated = _gate_position(baseline, events, accepted, offset=0)

    assert gated.tolist() == [0.0, 0.0, 0.0, 0.0, 1.0, 1.0]
    assert (gated <= baseline).all()


def test_strategy_specific_search_is_bounded() -> None:
    trials = _trial_definitions()
    assert len(trials) == 8
    assert {trial["model_family"] for trial in trials} == {
        "regularized_logistic",
        "lightgbm_challenger",
    }


def test_failed_or_partial_trial_cannot_be_selected() -> None:
    from open_composer.research.momentum_ml_research import _best_trial

    rows = [
        {
            "model_family": "lightgbm_challenger",
            "failures": [{"fold": 1}],
            "oos_entry_coverage": 1.0,
            "stitched_oos_metrics": {"total_return_pct": 100.0, "sharpe": 5.0},
        },
        {
            "model_family": "lightgbm_challenger",
            "failures": [],
            "oos_entry_coverage": 0.75,
            "stitched_oos_metrics": {"total_return_pct": 90.0, "sharpe": 4.0},
        },
    ]

    assert _best_trial(rows, "lightgbm_challenger") is None


def test_walk_forward_windows_do_not_split_active_episode() -> None:
    frame = _aligned_frame(6500)
    baseline = pd.Series(0.0, index=frame.index)
    baseline.iloc[1290:1310] = 1.0
    baseline.iloc[2600:2610] = 1.0
    events = pd.DataFrame(
        {
            "bar_index": [100 + index * 40 for index in range(140)],
            "label": [index % 2 for index in range(140)],
        }
    )

    windows = _eligible_windows(frame, events, baseline)

    assert all(
        (window.test_start_idx == 0 or baseline.iloc[window.test_start_idx - 1] == 0)
        and baseline.iloc[window.test_end_idx - 1] == 0
        for window in windows
    )


def test_design_blocks_small_historical_sample(sample_workspace: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    spec_path = _copy_spec(sample_workspace, repo_root)
    for symbol in ["qqq", "tqqq", "spy", "xlk", "bil"]:
        _write_symbol(sample_workspace, symbol)

    result = write_momentum_ml_design(spec_path, sample_workspace)

    assert result.payload["training_authorized"] is False
    assert "entry_events" in result.payload["blockers"]
    assert result.payload["execution_scope"] == "research_only_no_target_weight_control"


def test_design_cli_accepts_repo_relative_spec(sample_workspace: Path, monkeypatch) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    _copy_spec(sample_workspace, repo_root)
    for symbol in ["qqq", "tqqq", "spy", "xlk", "bil"]:
        _write_symbol(sample_workspace, symbol)
    monkeypatch.setattr("open_composer.cli.project_root", lambda: sample_workspace)

    result = CliRunner().invoke(
        app,
        [
            "research",
            "momentum-ml-design",
            "strategy_specs/drafts/us_mom_minute_p1_003_frozen.yaml",
        ],
        catch_exceptions=False,
    )

    assert result.exit_code == 0
    assert "training_authorized=False" in result.output


def _aligned_frame(rows: int) -> pd.DataFrame:
    timestamp = pd.date_range("2025-01-02 14:30", periods=rows, freq="30min", tz="UTC")
    close = pd.Series([100.0 + index for index in range(rows)])
    return pd.DataFrame(
        {
            "timestamp": timestamp,
            "signal_open": close - 0.1,
            "signal_high": close + 0.5,
            "signal_low": close - 0.5,
            "signal_close": close,
            "trade_open": close * 2,
            "trade_close": close * 2.01,
            "next_trade_return": 0.001,
        }
    )


def _copy_spec(root: Path, repo_root: Path) -> Path:
    source = repo_root / "strategy_specs/drafts/us_mom_minute_p1_003_frozen.yaml"
    target = root / "strategy_specs/drafts/us_mom_minute_p1_003_frozen.yaml"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    return target


def _write_symbol(root: Path, symbol: str) -> None:
    path = root / "data/research/alpaca_minute" / f"{symbol}_30m_alpaca_iex.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    price = 100.0
    for day in pd.date_range("2025-01-02", periods=20, freq="B"):
        for offset in range(13):
            timestamp = pd.Timestamp(day.date()).tz_localize("America/New_York") + pd.Timedelta(
                hours=9, minutes=30 + offset * 30
            )
            close = price * 1.001
            rows.append(
                {
                    "timestamp": timestamp.tz_convert("UTC"),
                    "open": price,
                    "high": close * 1.001,
                    "low": price * 0.999,
                    "close": close,
                    "volume": 100000,
                }
            )
            price = close
    pd.DataFrame(rows).to_csv(path, index=False)
