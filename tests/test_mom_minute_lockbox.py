from __future__ import annotations

from pathlib import Path

import pandas as pd
from typer.testing import CliRunner

from open_composer.cli import app
from open_composer.research.mom_minute_lockbox import (
    _entry_count_in_split,
    run_mom_minute_lockbox,
)


def test_lockbox_round_is_bounded_and_only_selected_trial_opens_lockbox(
    sample_workspace: Path,
) -> None:
    for symbol, leverage in [
        ("qqq", 1.0),
        ("tqqq", 2.5),
        ("spy", 0.8),
        ("xlk", 1.1),
        ("bil", 0.05),
    ]:
        _write_symbol(sample_workspace, symbol, leverage)

    result = run_mom_minute_lockbox(sample_workspace, lookbacks=[3, 4], atr_multipliers=[1.0, 1.5])

    assert result.payload["search_space"]["candidate_count"] == 4
    assert result.payload["selection_used_lockbox"] is False
    opened = [trial for trial in result.payload["trials"] if trial["lockbox"] is not None]
    assert len(opened) <= 1
    assert result.trial_ledger_path.exists()


def test_lockbox_cli_writes_report(sample_workspace: Path, monkeypatch) -> None:
    monkeypatch.setattr("open_composer.cli.project_root", lambda: sample_workspace)
    for symbol, leverage in [
        ("qqq", 1.0),
        ("tqqq", 2.5),
        ("spy", 0.8),
        ("xlk", 1.1),
        ("bil", 0.05),
    ]:
        _write_symbol(sample_workspace, symbol, leverage)

    result = CliRunner().invoke(app, ["research", "mom-minute-r2"], catch_exceptions=False)

    assert result.exit_code == 0
    assert "mom_minute_r2 verdict" in result.output


def test_lockbox_trade_count_preserves_pre_window_position_context() -> None:
    timestamps = pd.date_range("2025-01-02 14:30", periods=6, freq="30min", tz="UTC")
    frame = pd.DataFrame({"timestamp": timestamps})
    position = pd.Series([0.0, 1.0, 1.0, 0.0, 1.0, 1.0])
    split = {"start_session": "2025-01-02", "end_session": "2025-01-02"}

    assert _entry_count_in_split(position, frame, split) == 2

    later_split = {"start_session": "2025-01-03", "end_session": "2025-01-03"}
    assert _entry_count_in_split(position, frame, later_split) == 0


def _write_symbol(root: Path, symbol: str, leverage: float) -> None:
    path = root / "data/research/alpaca_minute" / f"{symbol}_30m_alpaca_iex.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    price = 100.0
    for day in pd.date_range("2025-01-02", periods=40, freq="B"):
        for offset in range(13):
            timestamp = pd.Timestamp(day.date()).tz_localize("America/New_York") + pd.Timedelta(
                hours=9, minutes=30 + offset * 30
            )
            ret = (0.001 if offset % 5 else -0.0003) * leverage
            open_price = price
            close = price * (1 + ret)
            rows.append(
                {
                    "timestamp": timestamp.tz_convert("UTC"),
                    "open": open_price,
                    "high": max(open_price, close) * 1.001,
                    "low": min(open_price, close) * 0.999,
                    "close": close,
                    "volume": 100000,
                }
            )
            price = close
    pd.DataFrame(rows).to_csv(path, index=False)
