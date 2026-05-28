from __future__ import annotations

from pathlib import Path
from shutil import copyfile

import pandas as pd

from open_composer.research.factor_lab_v2 import assess_factor_panel, run_factor_lab_v2
from open_composer.research.factor_panel import build_factor_panel_from_spec, load_factor_panel


def _panel() -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    dates = pd.date_range("2024-01-01", periods=8, freq="D", tz="UTC")
    symbols = ["AAA", "BBB", "CCC", "DDD"]
    groups = {"AAA": "tech", "BBB": "tech", "CCC": "health", "DDD": "health"}
    for date_index, timestamp in enumerate(dates):
        for symbol_index, symbol in enumerate(symbols):
            value = float(symbol_index + date_index * 0.01)
            return_rank = value
            if date_index % 4 == 0 and symbol == "CCC":
                return_rank = value + 1.5
            rows.append(
                {
                    "timestamp": timestamp.isoformat(),
                    "symbol": symbol,
                    "factor_name": "quality",
                    "factor_value": value,
                    "forward_return": return_rank / 100,
                    "horizon": 1,
                    "group": groups[symbol],
                    "market_cap_bucket": "large" if symbol in {"AAA", "BBB"} else "mid",
                    "source": "expression",
                    "visible_at": timestamp.isoformat(),
                }
            )
            rows.append(
                {
                    "timestamp": timestamp.isoformat(),
                    "symbol": symbol,
                    "factor_name": "quality",
                    "factor_value": value,
                    "forward_return": return_rank / 50,
                    "horizon": 5,
                    "group": groups[symbol],
                    "market_cap_bucket": "large" if symbol in {"AAA", "BBB"} else "mid",
                    "source": "expression",
                    "visible_at": timestamp.isoformat(),
                }
            )
    return pd.DataFrame(rows)


def test_factor_lab_v2_computes_rank_ic_icir_and_decay(tmp_path: Path) -> None:
    result = assess_factor_panel(
        _panel(),
        panel_path=tmp_path / "panel.csv",
        root=tmp_path,
        report_name="unit",
    )

    metric = next(item for item in result.factor_metrics if item.horizon == 1)
    assert result.status == "ok"
    assert metric.rank_ic is not None and metric.rank_ic > 0.5
    assert metric.icir is not None
    assert metric.ic_t_stat is not None
    assert set(metric.decay_by_horizon) == {"1", "5"}
    assert metric.top_bottom_spread_pct is not None and metric.top_bottom_spread_pct > 0
    assert metric.neutralized_rank_ic is not None


def test_factor_lab_v2_flags_low_coverage_and_missing_pit(tmp_path: Path) -> None:
    panel = _panel()
    panel.loc[panel.index[:20], "factor_value"] = None
    panel["source"] = "feature_packet"
    panel["visible_at"] = None

    result = assess_factor_panel(
        panel,
        panel_path=tmp_path / "panel.csv",
        root=tmp_path,
        report_name="unit",
    )

    assert result.status == "blocked"
    assert "feature_packet_visible_at_missing" in result.quality_flags
    assert any("low_coverage" in flag for flag in result.quality_flags)


def test_factor_panel_build_and_factor_lab_v2_cli_path(
    sample_workspace: Path,
    fixture_specs_root: Path,
) -> None:
    spec_path = (
        sample_workspace / "strategy_specs" / "drafts" / "fixture_mu_breakout_volume_15m.yaml"
    )
    copyfile(fixture_specs_root / "fixture_mu_breakout_volume_15m.yaml", spec_path)

    build = build_factor_panel_from_spec(spec_path, sample_workspace)
    result = run_factor_lab_v2(build.path, sample_workspace, strategy_name=build.strategy_name)
    panel = load_factor_panel(build.path)

    assert build.rows == len(panel)
    assert result.json_path.exists()
    assert result.report_path.exists()
