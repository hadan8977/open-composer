from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from open_composer.cli import app
from open_composer.dashboard import build_dashboard_catalog
from open_composer.dashboard.server import build_factor_decay_payload
from open_composer.research.factor_decay import (
    build_decay_report,
    monitor_factor_decay,
    retire_factor,
)
from open_composer.research.factor_lineage import append_lineage

FACTOR_ID = "alpha101_009_roc_5d"


def _write_decay_spec(root: Path) -> Path:
    path = root / "strategy_specs" / "drafts" / "decay_factor_probe.yaml"
    raw = {
        "name": "decay_factor_probe",
        "description": "Test factor decay monitoring on sample SYN daily data.",
        "timeframe": "daily",
        "universe": ["SYN"],
        "lifecycle": "draft",
        "entry": {"any": ["momentum_signal > 0"]},
        "exit": {"any": ["momentum_signal < 0"]},
        "risk": {"max_trades_per_day": 1, "max_position_weight": 0.5},
        "execution": {
            "mode": "manual_signal",
            "signal_on": "bar_close",
            "fill_assumption": "next_bar_open",
            "broker": "none",
        },
        "data": {
            "source": "sample",
            "symbol": "SYN",
            "path": "data/sample/syn_daily.csv",
        },
        "data_assumptions": {
            "source": "sample",
            "adjusted": True,
            "timezone": "America/New_York",
        },
        "factors": {
            "momentum_signal": {
                "source": "factor_library",
                "factor_id": FACTOR_ID,
            }
        },
        "llm_review": {"enabled": False},
        "required_capabilities": ["market.sample_ohlcv"],
        "notes": {"intent": "test only"},
    }
    path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
    append_lineage(FACTOR_ID, path, added_by="pytest", root=root)
    return path


def test_monitor_factor_decay_writes_history(sample_workspace: Path) -> None:
    _write_decay_spec(sample_workspace)

    record = monitor_factor_decay(
        FACTOR_ID,
        root=sample_workspace,
        rolling_3m_bars=10,
        rolling_12m_bars=20,
        horizon_bars=1,
        min_observations=10,
        dispatch_alert=False,
    )

    assert record["factor_id"] == FACTOR_ID
    assert record["status"] in {"healthy", "alert"}
    assert record["sample_size"] >= 10
    history_path = sample_workspace / "reports" / "factors" / FACTOR_ID / "decay-monitor.jsonl"
    rows = [json.loads(line) for line in history_path.read_text(encoding="utf-8").splitlines()]
    assert rows[-1]["factor_id"] == FACTOR_ID
    report = build_decay_report(sample_workspace, days=365)
    assert any(row["factor_id"] == FACTOR_ID for row in report)


def test_monitor_factor_decay_requires_lineage(sample_workspace: Path) -> None:
    with pytest.raises(FileNotFoundError, match="no lineage"):
        monitor_factor_decay(FACTOR_ID, root=sample_workspace, dispatch_alert=False)


def test_retire_factor_updates_lineage(sample_workspace: Path) -> None:
    _write_decay_spec(sample_workspace)

    payload = retire_factor(FACTOR_ID, reason="decay test", root=sample_workspace)

    assert payload["retirement_reason"] == "decay test"
    lineage = json.loads(
        (sample_workspace / "reports" / "factors" / FACTOR_ID / "lineage.json").read_text(
            encoding="utf-8"
        )
    )
    assert lineage["retirement_reason"] == "decay test"


def test_factor_decay_cli_and_dashboard_payload(
    sample_workspace: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_decay_spec(sample_workspace)
    monkeypatch.chdir(sample_workspace)

    result = CliRunner().invoke(
        app,
        ["factor", "decay-monitor", "--factor-id", FACTOR_ID, "--no-notify"],
        catch_exceptions=False,
    )

    assert result.exit_code == 0
    assert "Factor Decay Monitor" in result.output
    catalog = build_dashboard_catalog(sample_workspace)
    factor = next(item for item in catalog.factor_catalog if item.factor_id == FACTOR_ID)
    assert catalog.summary.factor_count >= 1
    assert factor.latest_decay_status in {"healthy", "alert", "insufficient_data"}
    payload = build_factor_decay_payload(sample_workspace, FACTOR_ID)
    assert payload["factor_id"] == FACTOR_ID
    assert payload["latest"]["factor_id"] == FACTOR_ID
