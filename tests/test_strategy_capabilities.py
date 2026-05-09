from __future__ import annotations

from pathlib import Path

from open_composer.strategy_capabilities import assess_strategy_capabilities


def _write_spec(
    path: Path,
    *,
    expression: str = "close > ema(close, 5)",
    llm_enabled: bool = False,
    required_capabilities: list[str] | None = None,
) -> Path:
    capabilities = required_capabilities or ["market.sample_ohlcv"]
    capability_lines = "\n".join(f"  - {capability}" for capability in capabilities)
    llm_text = "true" if llm_enabled else "false"
    path.write_text(
        f"""name: test_strategy
description: Capability classification fixture.
timeframe: 15m
universe: [QQQ]
lifecycle: draft
entry:
  all:
    - "{expression}"
exit:
  any:
    - "rsi(close, 3) > 80"
risk:
  max_trades_per_day: 2
  max_position_weight: 0.2
  stop_loss_pct: 1.0
  take_profit_pct: 2.0
execution:
  mode: manual_signal
  signal_on: bar_close
  fill_assumption: next_bar_open
  broker: none
data:
  source: sample
  symbol: QQQ
  path: data/sample/qqq_15m.csv
llm_review:
  enabled: {llm_text}
required_capabilities:
{capability_lines}
""",
        encoding="utf-8",
    )
    return path


def test_strategy_capability_report_for_pure_technical_spec(tmp_path: Path) -> None:
    spec_path = _write_spec(tmp_path / "pure.yaml")

    report = assess_strategy_capabilities(spec_path)

    assert report.finding("python_mvp_backtest").status == "supported"
    assert report.finding("tradingview_pine_strategy").status == "supported"
    assert report.finding("alpaca_paper_execution").status == "blocked"
    assert report.finding("llm_quant_workflow").status == "blocked"
    assert report.expression_functions == ["ema", "rsi"]


def test_strategy_capability_report_marks_llm_context_as_partial(tmp_path: Path) -> None:
    spec_path = _write_spec(
        tmp_path / "llm.yaml",
        llm_enabled=True,
        required_capabilities=[
            "market.sample_ohlcv",
            "events.sec_filings",
            "news.alpha_vantage",
        ],
    )

    report = assess_strategy_capabilities(spec_path)

    assert report.finding("python_mvp_backtest").status == "partial"
    assert report.finding("tradingview_pine_strategy").status == "partial"
    assert report.finding("llm_quant_workflow").status == "partial"


def test_strategy_capability_report_marks_unsupported_expressions(tmp_path: Path) -> None:
    spec_path = _write_spec(tmp_path / "unsupported.yaml", expression="atr(14) > 2")

    report = assess_strategy_capabilities(spec_path)

    assert report.finding("python_mvp_backtest").status == "unsupported"
    assert report.finding("tradingview_pine_strategy").status == "unsupported"
    assert "atr(14) > 2" in report.finding("python_mvp_backtest").reasons[0]
