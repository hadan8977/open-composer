from __future__ import annotations

from pathlib import Path

from open_composer.models.execution_backend import ExecutionBackendPlan
from open_composer.strategy_capabilities import assess_strategy_capabilities


def _write_spec(
    path: Path,
    *,
    expression: str = "close > ema(close, 5)",
    llm_enabled: bool = False,
    required_capabilities: list[str] | None = None,
    backend: str = "python_reference",
    data_source: str = "sample",
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
  backend: {backend}
  mode: manual_signal
  signal_on: bar_close
  fill_assumption: next_bar_open
  broker: none
data:
  source: {data_source}
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
    assert report.finding("nautilus_trader_backend").status == "partial"
    assert any(
        "selected backend remains python_reference" in reason
        for reason in report.finding("nautilus_trader_backend").reasons
    )
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
    assert report.finding("nautilus_trader_backend").status == "partial"
    assert any(
        "LLM review" in reason for reason in report.finding("nautilus_trader_backend").reasons
    )
    assert report.finding("llm_quant_workflow").status == "partial"


def test_strategy_capability_report_marks_unsupported_expressions(tmp_path: Path) -> None:
    spec_path = _write_spec(
        tmp_path / "unsupported.yaml",
        expression="supertrend(close, 10) > 0",
    )

    report = assess_strategy_capabilities(spec_path)

    assert report.finding("python_mvp_backtest").status == "unsupported"
    assert report.finding("tradingview_pine_strategy").status == "unsupported"
    assert "supertrend(close, 10) > 0" in report.finding("python_mvp_backtest").reasons[0]


def test_strategy_capability_report_supports_statistical_expressions(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "open_composer.adapters.execution.nautilus_trader.nautilus_trader_available",
        lambda: True,
    )
    spec_path = _write_spec(
        tmp_path / "statistical.yaml",
        expression="macd(close, 12, 26) > macd_signal(close, 12, 26, 9)",
        backend="nautilus_trader",
    )

    report = assess_strategy_capabilities(spec_path)

    assert report.finding("python_mvp_backtest").status == "supported"
    assert report.finding("tradingview_pine_strategy").status == "supported"
    assert report.finding("nautilus_trader_backend").status == "supported"
    assert "macd" in report.expression_functions
    assert "macd_signal" in report.expression_functions


def test_strategy_capability_report_accepts_longbridge_data_source(tmp_path: Path) -> None:
    spec_path = _write_spec(
        tmp_path / "longbridge.yaml",
        data_source="longbridge",
    )

    report = assess_strategy_capabilities(spec_path)

    assert report.finding("python_mvp_backtest").status == "supported"


def test_strategy_capability_relative_path_finds_router_authorization(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "open_composer.strategy_capabilities.build_nautilus_trader_plan",
        lambda _: ExecutionBackendPlan(
            strategy_id="router",
            strategy_name="router",
            selected_backend="nautilus_trader",
            target_backend="nautilus_trader",
            execution_mode="paper_auto",
            broker="alpaca_paper",
            data_source="alpaca",
            symbol="QQQ",
            timeframe="daily",
            supported=True,
            status="supported",
            reasons=[],
            nautilus_installed=True,
        ),
    )
    spec_dir = tmp_path / "strategy_specs" / "active"
    spec_dir.mkdir(parents=True)
    spec_path = spec_dir / "router.yaml"
    spec_path.write_text(
        """name: router
description: Relative path router fixture.
timeframe: daily
universe: [QQQ, TQQQ]
lifecycle: active
position_direction: long_only
entry:
  all:
    - "close > sma(close, 50)"
exit:
  any:
    - "close < sma(close, 50)"
risk:
  max_trades_per_day: 1
  max_position_weight: 0.8
execution:
  backend: nautilus_trader
  mode: paper_auto
  signal_on: bar_close
  fill_assumption: next_bar_open
  broker: alpaca_paper
portfolio:
  mode: hybrid_adaptive_router
  max_symbols_per_day: 1
  gross_exposure_limit: 0.8
  max_symbol_weight: 0.8
  selected_route_label: beta_override:test
data:
  source: alpaca
  symbol: QQQ
llm_review:
  enabled: false
required_capabilities:
  - market.alpaca_bars
""",
        encoding="utf-8",
    )
    paper_dir = tmp_path / "reports" / "harness" / "paper"
    paper_dir.mkdir(parents=True)
    safety_path = paper_dir / "router-paper-safety-review.json"
    safety_path.write_text('{"strategy_name":"router","overall":"approved","blocking_items":[]}')
    execution_dir = tmp_path / "reports" / "execution"
    execution_dir.mkdir(parents=True)
    (execution_dir / "router-target-weights.json").write_text("{}", encoding="utf-8")
    (execution_dir / "router-rebalance-intents.json").write_text("{}", encoding="utf-8")
    (paper_dir / "router-router-order-authorization.json").write_text(
        """{
  "strategy_name": "router",
  "execution_substate": "order_authorized",
  "authorized": true,
  "authorized_at": "2026-05-30T00:00:00Z",
  "execution_policy_id": "policy-router",
  "target_weights_path": "reports/execution/router-target-weights.json",
  "rebalance_intents_path": "reports/execution/router-rebalance-intents.json",
  "paper_safety_review_path": "reports/harness/paper/router-paper-safety-review.json"
}""",
        encoding="utf-8",
    )

    report = assess_strategy_capabilities(Path("strategy_specs/active/router.yaml"))

    assert report.finding("alpaca_paper_execution").status == "supported"
