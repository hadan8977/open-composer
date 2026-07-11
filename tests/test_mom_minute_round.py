from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
from typer.testing import CliRunner

from open_composer.cli import app
from open_composer.research.mom_minute_round import (
    _align_signal_and_trade,
    _benchmarks,
    _load_research_frame,
    _strategy_returns,
    run_mom_minute_round,
)


def test_strategy_returns_execute_from_next_bar_open(sample_workspace: Path) -> None:
    _write_symbol(sample_workspace, "qqq", "30m")
    _write_symbol(sample_workspace, "tqqq", "30m", leverage=2.5)
    signal = _load_research_frame(sample_workspace, "QQQ", "30m")
    traded = _load_research_frame(sample_workspace, "TQQQ", "30m")
    assert signal is not None and traded is not None
    aligned = _align_signal_and_trade(signal, traded)
    returns = _strategy_returns(
        aligned,
        pd.Series(1.0, index=aligned.index),
        cost_bps=0.0,
        allow_overnight=True,
    )

    expected = aligned.iloc[0]["next_execution_open"] / aligned.iloc[0]["execution_open"] - 1
    assert returns.iloc[0] == expected
    assert aligned.iloc[0]["execution_open"] == aligned.iloc[1]["trade_open"]


def test_benchmarks_require_overlap_and_include_full_family(sample_workspace: Path) -> None:
    for symbol, leverage in [
        ("qqq", 1.0),
        ("tqqq", 2.5),
        ("spy", 0.8),
        ("xlk", 1.1),
        ("bil", 0.05),
    ]:
        _write_symbol(sample_workspace, symbol, "30m", leverage=leverage)
    bundle = {
        symbol: _load_research_frame(sample_workspace, symbol, "30m")
        for symbol in ["QQQ", "TQQQ", "SPY", "XLK", "BIL"]
    }
    qqq = bundle["QQQ"]
    assert qqq is not None
    index = pd.DatetimeIndex(pd.to_datetime(qqq["timestamp"], utc=True)[:20])

    benchmarks = _benchmarks(bundle, "30m", index)

    assert all(
        name in benchmarks
        for name in [
            "QQQ_buy_hold",
            "TQQQ_buy_hold",
            "SPY_market_proxy",
            "XLK_sector_theme_proxy",
            "BIL_cash_proxy",
            "equal_weight_universe",
            "ex_post_best_symbol",
        ]
    )
    missing_index = pd.DatetimeIndex([pd.Timestamp("2030-01-01T14:30:00Z")])
    assert _benchmarks(bundle, "30m", missing_index)["QQQ_buy_hold"]["available"] is False


def test_mom_minute_round_writes_bounded_ledger(sample_workspace: Path) -> None:
    _write_symbol(sample_workspace, "qqq", "30m")
    _write_symbol(sample_workspace, "tqqq", "30m", leverage=2.5)
    _write_symbol(sample_workspace, "spy", "30m", leverage=0.8)
    _write_symbol(sample_workspace, "xlk", "30m", leverage=1.1)
    _write_symbol(sample_workspace, "bil", "30m", leverage=0.05)

    result = run_mom_minute_round(
        sample_workspace,
        report_date="20260710",
        p1_timeframes=["30m"],
        p1_lookbacks=[3],
        p1_exit_styles=["ema_cross"],
        p3_timeframes=["30m"],
        p3_overnight_thresholds_pct=[0.0],
        p3_intraday_confirms=["none"],
    )

    assert result.evaluation_json_path.exists()
    assert result.evaluation_markdown_path.exists()
    assert result.trial_ledger_path.exists()
    rows = result.trial_ledger_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(rows) == 2
    payload = json.loads(result.evaluation_json_path.read_text(encoding="utf-8"))
    assert payload["search_space"]["candidate_count"] == 2
    assert payload["paper_ready_pass"] is False
    assert payload["trials"][0]["oos_evidence"] is False
    assert payload["trials"][0]["folds"] == []


def test_mom_minute_round_cli(sample_workspace: Path, monkeypatch) -> None:
    monkeypatch.setattr("open_composer.cli.project_root", lambda: sample_workspace)
    _write_symbol(sample_workspace, "qqq", "30m")
    _write_symbol(sample_workspace, "tqqq", "30m", leverage=2.5)
    _write_symbol(sample_workspace, "spy", "30m", leverage=0.8)
    _write_symbol(sample_workspace, "xlk", "30m", leverage=1.1)
    _write_symbol(sample_workspace, "bil", "30m", leverage=0.05)

    result = CliRunner().invoke(
        app,
        [
            "research",
            "mom-minute-r1",
            "--report-date",
            "20260710",
            "--smoke",
        ],
        catch_exceptions=False,
    )

    assert result.exit_code == 0
    assert "mom_minute_r1 evaluation written" in result.output


def _write_symbol(
    root: Path,
    symbol: str,
    timeframe: str,
    *,
    leverage: float = 1.0,
) -> None:
    path = root / "data" / "research" / "alpaca_minute" / f"{symbol}_{timeframe}_alpaca_iex.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    timestamps = []
    opens = []
    highs = []
    lows = []
    closes = []
    volumes = []
    price = 100.0
    for day in pd.date_range("2026-01-05", periods=12, freq="B"):
        for offset in range(13):
            ts = pd.Timestamp(day.date()).tz_localize("America/New_York") + pd.Timedelta(
                hours=9, minutes=30 + offset * 30
            )
            ret = (0.001 if offset % 3 != 0 else -0.0005) * leverage
            open_price = price
            close_price = price * (1 + ret)
            timestamps.append(ts.tz_convert("UTC"))
            opens.append(open_price)
            highs.append(max(open_price, close_price) * 1.001)
            lows.append(min(open_price, close_price) * 0.999)
            closes.append(close_price)
            volumes.append(100_000)
            price = close_price
    frame = pd.DataFrame(
        {
            "timestamp": timestamps,
            "open": opens,
            "high": highs,
            "low": lows,
            "close": closes,
            "volume": volumes,
        }
    )
    frame.to_csv(path, index=False)
