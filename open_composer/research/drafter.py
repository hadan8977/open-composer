from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

from open_composer.config import (
    default_openai_model,
    ensure_dir,
    openai_api_key,
    openai_base_url,
    project_root,
)
from open_composer.models.strategy_spec import StrategySpec


def draft_strategy_from_idea(
    idea: str,
    root: Path | None = None,
    use_llm: bool = False,
    client: Any | None = None,
) -> Path:
    base = root or project_root()
    spec = _draft_with_llm(idea, client) if use_llm and _has_openai_config(client) else None
    if spec is None:
        spec = _deterministic_draft(idea)
    path = base / "strategy_specs" / "drafts" / f"{spec.name}.yaml"
    ensure_dir(path.parent)
    path.write_text(yaml.safe_dump(spec.model_dump(mode="json"), sort_keys=False), encoding="utf-8")
    return path


def _has_openai_config(client: Any | None) -> bool:
    return client is not None or bool(openai_api_key())


def _draft_with_llm(idea: str, client: Any | None = None) -> StrategySpec | None:
    client = client or _openai_client()
    messages = [
        {
            "role": "system",
            "content": (
                "Generate an Open Composer StrategySpec. Keep real trading manual_signal. "
                "Use registered capabilities only: market.alpaca_bars, events.sec_filings, "
                "macro.fred_series, news.alpha_vantage, news.gdelt. Use conservative risk."
            ),
        },
        {"role": "user", "content": idea},
    ]
    response = client.responses.parse(
        model=default_openai_model(),
        input=messages,
        text_format=StrategySpec,
    )
    for output in getattr(response, "output", []):
        if getattr(output, "type", None) != "message":
            continue
        for item in getattr(output, "content", []):
            parsed = getattr(item, "parsed", None)
            if isinstance(parsed, StrategySpec):
                return parsed
            if isinstance(parsed, dict):
                return StrategySpec.model_validate(parsed)
    return None


def _openai_client() -> Any:
    from openai import OpenAI

    return OpenAI(api_key=openai_api_key(), base_url=openai_base_url())


def _deterministic_draft(idea: str) -> StrategySpec:
    if _is_memory_storage_idea(idea):
        return _memory_storage_draft(idea)
    symbol = _extract_symbol(idea)
    timeframe = "15m" if "15m" in idea.lower() or "15 m" in idea.lower() else "1h"
    slug = f"{symbol.lower()}_pullback_context_{timeframe}".replace("-", "_")
    return StrategySpec.model_validate(
        {
            "name": slug,
            "description": f"{symbol} pullback strategy with event, macro, and news context.",
            "timeframe": timeframe,
            "universe": [symbol],
            "lifecycle": "draft",
            "entry": {
                "all": [
                    "close > ema(close, 5)",
                    "rsi(close, 3) < 75",
                    "volume > sma(volume, 3)",
                ]
            },
            "exit": {"any": ["rsi(close, 3) > 82", "close < ema(close, 5)"]},
            "risk": {
                "max_trades_per_day": 3,
                "max_position_weight": 0.2,
                "stop_loss_pct": 1.2,
                "take_profit_pct": 2.0,
            },
            "execution": {
                "mode": "manual_signal",
                "signal_on": "bar_close",
                "fill_assumption": "next_bar_open",
                "broker": "none",
            },
            "data": {
                "source": "sample",
                "symbol": symbol,
                "path": f"data/sample/{symbol.lower()}_15m.csv",
            },
            "data_assumptions": {
                "source": "sample",
                "adjusted": True,
                "timezone": "America/New_York",
            },
            "llm_review": {"enabled": True, "model": default_openai_model()},
            "required_capabilities": [
                "market.sample_ohlcv",
                "events.sec_filings",
                "macro.fred_series",
                "news.alpha_vantage",
                "news.gdelt",
            ],
            "notes": {
                "intent": (
                    "Buy pullbacks only after deterministic technical confirmation; attach "
                    "company event, macro, and news context before manual or paper action."
                ),
                "open_questions": [
                    "Evaluate Alpaca IEX versus paid SIP before relying on intraday fills.",
                    "Measure Alpha Vantage and GDELT coverage against the active watchlist.",
                ],
            },
        }
    )


def _memory_storage_draft(idea: str) -> StrategySpec:
    timeframe = "15m" if _mentions_intraday(idea) else "1h"
    return StrategySpec.model_validate(
        {
            "name": "memory_storage_momentum_15m",
            "description": (
                "Intraday MU momentum strategy for the memory/storage AI data-center theme."
            ),
            "timeframe": timeframe,
            "universe": ["MU", "WDC", "STX"],
            "lifecycle": "draft",
            "entry": {
                "all": [
                    "close > ema(close, 8)",
                    "ema(close, 5) > ema(close, 13)",
                    "rsi(close, 6) > 55",
                    "volume > sma(volume, 8)",
                ]
            },
            "exit": {"any": ["close < ema(close, 8)", "rsi(close, 6) > 88"]},
            "risk": {
                "max_trades_per_day": 2,
                "max_position_weight": 0.2,
                "stop_loss_pct": 1.1,
                "take_profit_pct": 3.2,
            },
            "execution": {
                "mode": "manual_signal",
                "signal_on": "bar_close",
                "fill_assumption": "next_bar_open",
                "broker": "none",
            },
            "data": {"source": "sample", "symbol": "MU", "path": "data/sample/mu_15m.csv"},
            "data_assumptions": {
                "source": "sample",
                "adjusted": True,
                "timezone": "America/New_York",
            },
            "llm_review": {"enabled": True, "model": default_openai_model()},
            "required_capabilities": [
                "market.memory_storage_sample",
                "events.sec_filings",
                "macro.fred_series",
                "news.alpha_vantage",
                "news.gdelt",
            ],
            "notes": {
                "intent": (
                    "Trade intraday continuation in memory/storage names when MU leads on "
                    "price, volume, and AI data-center context. Real trading remains manual."
                ),
                "open_questions": [
                    "Confirm live Alpaca IEX coverage versus paid SIP before production use.",
                    "Measure whether MU, WDC, or STX provides the cleanest intraday proxy.",
                    "Keep news/event context as a filter and review input, not a sole entry rule.",
                ],
            },
        }
    )


def _is_memory_storage_idea(idea: str) -> bool:
    normalized = idea.lower()
    keywords = [
        "memory",
        "storage",
        "dram",
        "nand",
        "hbm",
        "micron",
        "内存",
        "存储",
    ]
    return any(keyword in normalized for keyword in keywords)


def _mentions_intraday(idea: str) -> bool:
    normalized = idea.lower()
    return any(token in normalized for token in ["15m", "15 m", "intraday", "日内", "盘中"])


def _extract_symbol(idea: str) -> str:
    for token in re.findall(r"\b[A-Z]{2,5}\b", idea):
        if token not in {"SEC", "LLM", "API"}:
            return token
    return "QQQ"
