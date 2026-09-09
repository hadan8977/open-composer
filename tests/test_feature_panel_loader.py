"""Memory-lean panel loaders and their equivalence with the full-panel path."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from open_composer.research.features.panel import load_feature_panel, load_price_panel
from open_composer.research.kernel import loop
from open_composer.research.kernel.baseline_strategies import MomentumFactorStrategy

SYMBOLS = ["AAA", "BBB", "CCC", "DDD"]


def _write_fixture(root: Path) -> tuple[Path, Path, pd.DataFrame]:
    rng = np.random.default_rng(3)
    dates = pd.bdate_range("2019-01-02", "2020-12-31")
    rows = []
    for symbol in SYMBOLS:
        price = 100.0 * np.cumprod(1 + rng.normal(0.0004, 0.02, len(dates)))
        for i, date in enumerate(dates):
            rows.append(
                {
                    "symbol": symbol,
                    "trade_date": date,
                    "open": price[i] * (1 + rng.normal(0, 0.003)),
                    "close": price[i],
                    "momentum_252_21": rng.normal(),
                    "vol_21": abs(rng.normal()),
                    "beta_252_spy": 1.0,
                }
            )
    daily = pd.DataFrame(rows)
    labels = daily[["symbol", "trade_date"]].copy()
    labels["label_rank_5"] = rng.random(len(labels))
    labels["label_excess_5"] = rng.normal(size=len(labels))
    daily_root, labels_root = root / "daily", root / "labels"
    daily_root.mkdir()
    labels_root.mkdir()
    for year, part in daily.groupby(daily["trade_date"].dt.year):
        part.to_parquet(daily_root / f"{year}.parquet", index=False)
    for year, part in labels.groupby(labels["trade_date"].dt.year):
        part.to_parquet(labels_root / f"{year}.parquet", index=False)
    full = daily.merge(labels, on=["symbol", "trade_date"])
    return daily_root, labels_root, full


@pytest.fixture
def fixture_roots(tmp_path: Path) -> tuple[Path, Path, pd.DataFrame]:
    return _write_fixture(tmp_path)


def test_price_panel_is_narrow_float32_with_categorical_symbol(fixture_roots) -> None:
    daily_root, _, full = fixture_roots
    prices = load_price_panel(daily_root=daily_root, memory_limit="256MB")
    assert list(prices.columns) == ["symbol", "trade_date", "open", "close"]
    assert str(prices["symbol"].dtype) == "category"
    assert prices["close"].dtype == np.float32
    assert len(prices) == len(full)


def test_feature_panel_filters_to_requested_dates_and_casts(fixture_roots) -> None:
    daily_root, labels_root, full = fixture_roots
    calendar = pd.DatetimeIndex(sorted(full["trade_date"].unique()))
    fridays = loop.weekly_rebalance_dates(calendar)
    panel = load_feature_panel(
        ["momentum_252_21", "vol_21", "beta_252_spy"],
        ["label_rank_5"],
        dates=fridays,
        daily_root=daily_root,
        labels_root=labels_root,
        memory_limit="256MB",
    )
    assert set(panel["trade_date"].unique()) == set(fridays)
    assert len(panel) == len(SYMBOLS) * len(fridays)
    assert panel["momentum_252_21"].dtype == np.float32
    assert "label_excess_5" not in panel.columns  # only requested labels
    assert {"open", "close"} <= set(panel.columns)  # include_prices default
    lean = load_feature_panel(
        ["momentum_252_21"],
        ["label_rank_5"],
        include_prices=False,
        daily_root=daily_root,
        labels_root=labels_root,
        memory_limit="256MB",
    )
    assert "close" not in lean.columns


def test_weekly_panel_plus_price_panel_reproduces_the_full_panel_experiment(
    fixture_roots, monkeypatch: pytest.MonkeyPatch
) -> None:
    daily_root, labels_root, full = fixture_roots
    calendar = pd.DatetimeIndex(sorted(full["trade_date"].unique()))
    fridays = loop.weekly_rebalance_dates(calendar)
    features = ["momentum_252_21", "vol_21", "beta_252_spy"]
    weekly = load_feature_panel(
        features,
        ["label_rank_5"],
        dates=fridays,
        daily_root=daily_root,
        labels_root=labels_root,
        memory_limit="256MB",
    )
    prices = load_price_panel(daily_root=daily_root, memory_limit="256MB")
    universe_panel = pd.DataFrame(
        {"symbol": SYMBOLS, "month_end": [pd.Timestamp("2019-01-31")] * len(SYMBOLS)}
    )
    # A real-looking benchmark: all-zero returns leave mechanism_eval's
    # conditional-capture benchmark subset empty and it raises by design.
    spy = pd.Series(np.random.default_rng(9).normal(0.0003, 0.01, len(calendar)), index=calendar)
    config = loop.ExperimentConfig(
        experiment_id="equiv",
        family="test",
        model_kind="momentum",
        feature_set="daily_only",
        label_horizon_days=5,
        feature_columns=tuple(features),
        top_k=2,
        test_years=(2020,),
        train_row_dates="rebalance_dates",
        execution="next_open",
    )
    kwargs = dict(
        universe_panel=universe_panel,
        label_column="label_rank_5",
        strategy_factory=lambda: MomentumFactorStrategy("momentum_252_21"),
        spy_returns=spy,
        qqq_returns=spy,
        tqqq_returns=spy,
        bil_returns=spy,
        write_ledger=False,
        write_tearsheet=False,
        write_mlflow=False,
    )
    full_panel = full.copy()
    for column in features + ["label_rank_5", "open", "close"]:
        full_panel[column] = full_panel[column].astype(np.float32)
    reference = loop.run_experiment(config, panel=full_panel, **kwargs)
    lean = loop.run_experiment(config, panel=weekly, price_panel=prices, **kwargs)
    assert lean.long_only.metrics["cagr"] == pytest.approx(
        reference.long_only.metrics["cagr"], rel=1e-6
    )
    assert lean.long_only.metrics["max_drawdown"] == pytest.approx(
        reference.long_only.metrics["max_drawdown"], rel=1e-6
    )
