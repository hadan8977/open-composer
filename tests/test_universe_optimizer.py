from __future__ import annotations

from pathlib import Path

import pandas as pd

from open_composer.adapters.data.sample import normalize_ohlcv
from open_composer.research.universe_optimizer import optimize_strategy_universe


def test_universe_optimizer_writes_per_symbol_specs(
    sample_workspace: Path,
    monkeypatch,
    preregister_iteration_dossier,
) -> None:
    sample = pd.read_csv(sample_workspace / "data" / "sample" / "qqq_15m.csv")

    def fake_fetch_ohlcv(**kwargs):
        frame = sample.copy()
        if kwargs["symbol"] == "BBB":
            frame["close"] = frame["close"] * 1.01
        return normalize_ohlcv(frame)

    monkeypatch.setattr("open_composer.research.universe_optimizer.fetch_ohlcv", fake_fetch_ohlcv)
    spec_path = sample_workspace / "strategy_specs/drafts/fixture_pullback_15m.yaml"
    preregister_iteration_dossier(spec_path, candidate_count=18)
    result = optimize_strategy_universe(
        spec_path,
        sample_workspace,
        symbols=["AAA", "BBB"],
        refresh_data=False,
    )

    assert result.report_path.exists()
    assert len(result.selected_specs) == 2
    assert all(path.exists() for path in result.selected_specs)
    assert {item.symbol for item in result.selections} == {"AAA", "BBB"}
    assert "excessive trades" in result.report_path.read_text(encoding="utf-8")
