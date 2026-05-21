from __future__ import annotations

import re
from dataclasses import dataclass
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
from open_composer.research.kernel import (
    build_default_research_brief,
    search_space_from_spec,
)
from open_composer.storage import write_json
from open_composer.strategy_versions import register_strategy_version


@dataclass(frozen=True)
class DraftResult:
    path: Path
    used_llm: bool
    fallback_reason: str | None


def draft_strategy_from_idea(
    idea: str,
    root: Path | None = None,
    use_llm: bool = False,
    client: Any | None = None,
) -> Path:
    """Draft a strategy from an idea and return the spec path.

    For backwards compatibility, returns only the path. Use
    draft_strategy_from_idea_with_status() to also get LLM fallback metadata.
    """
    return draft_strategy_from_idea_with_status(idea, root, use_llm, client).path


def draft_strategy_from_idea_with_status(
    idea: str,
    root: Path | None = None,
    use_llm: bool = False,
    client: Any | None = None,
) -> DraftResult:
    base = root or project_root()
    used_llm = False
    fallback_reason: str | None = None
    spec: StrategySpec | None = None
    if use_llm and _has_openai_config(client):
        try:
            spec = _draft_with_llm(idea, client)
        except Exception as exc:
            fallback_reason = f"{type(exc).__name__}: {exc}"
            spec = None
    if spec is not None:
        used_llm = True
    if spec is None:
        spec = _deterministic_draft(idea)
    spec = _with_standard_research_design(spec)
    path = base / "strategy_specs" / "drafts" / f"{spec.name}.yaml"
    ensure_dir(path.parent)
    path.write_text(yaml.safe_dump(spec.model_dump(mode="json"), sort_keys=False), encoding="utf-8")
    _write_draft_research_plan(spec, path, base, fallback_reason=fallback_reason)
    register_strategy_version(
        path,
        base,
        created_by="strategy_draft_llm" if used_llm else "strategy_draft_deterministic",
        model_ref=default_openai_model() if used_llm else None,
        prompt_session_id=_prompt_session_id(idea),
    )
    return DraftResult(path=path, used_llm=used_llm, fallback_reason=fallback_reason)


def _with_standard_research_design(spec: StrategySpec) -> StrategySpec:
    if spec.research_design is not None:
        return spec
    notes = spec.notes.model_dump(mode="json")
    legacy = notes.get("research_design") if isinstance(notes, dict) else None
    parameter_space: dict[str, list[object]] = {}
    candidate_budget = 100
    selection_objective = "risk_adjusted_alpha_after_costs"
    validation_plan = [
        "reference_backtest",
        "out_of_sample",
        "walk_forward",
        "cost_sensitivity",
        "benchmark_family",
    ]
    if isinstance(legacy, dict):
        ranges = legacy.get("parameter_ranges")
        if isinstance(ranges, dict):
            parameter_space = {
                str(key): list(value) for key, value in ranges.items() if isinstance(value, list)
            }
        candidate_budget = int(legacy.get("candidate_cap") or candidate_budget)
        selection_objective = str(legacy.get("objective") or selection_objective)
        raw_validation = legacy.get("validation_plan")
        if isinstance(raw_validation, list) and raw_validation:
            validation_plan = [str(item) for item in raw_validation]
    raw = spec.model_dump(mode="json")
    raw["research_design"] = _standard_research_design(
        parameter_space=parameter_space,
        candidate_budget=candidate_budget,
        selection_objective=selection_objective,
        validation_plan=validation_plan,
    )
    return StrategySpec.model_validate(raw)


def _write_draft_research_plan(
    spec: StrategySpec,
    spec_path: Path,
    root: Path,
    *,
    fallback_reason: str | None = None,
) -> Path:
    research_brief = build_default_research_brief(spec)
    search_space = search_space_from_spec(spec)
    plan_path = root / "reports" / "research" / f"{spec.name}-draft-research-plan.json"
    payload: dict[str, object] = {
        "strategy_name": spec.name,
        "source_spec_path": _relpath(spec_path, root),
        "status": "draft",
        "research_brief": research_brief.model_dump(mode="json"),
        "search_space": search_space.model_dump(mode="json"),
        "default_validation": [
            "spec_validation",
            "capability_evaluation",
            "reference_backtest",
            "factor_lab",
            "promotion_report",
            "paper_readiness_summary",
        ],
        "promotion_blockers_until_evidenced": [
            "oos_walk_forward_cost_benchmark_evidence",
            "execution_reality",
            "data_quality",
            "paper_readiness",
        ],
    }
    if fallback_reason:
        payload["llm_fallback_reason"] = fallback_reason
    write_json(plan_path, payload)
    return plan_path


def _standard_research_design(
    *,
    parameter_space: dict[str, list[object]],
    candidate_budget: int,
    selection_objective: str,
    validation_plan: list[str] | None = None,
) -> dict[str, object]:
    return {
        "parameter_space": parameter_space,
        "candidate_budget": candidate_budget,
        "selection_objective": selection_objective,
        "anti_overfit_notes": [
            "Select candidates on training windows before evaluating OOS evidence.",
            "Keep the full searched parameter space and trial ledger as artifacts.",
            "Do not promote sample, fixture, or fallback data as paper-ready evidence.",
        ],
        "validation_plan": validation_plan
        or [
            "reference_backtest",
            "out_of_sample",
            "walk_forward",
            "cost_sensitivity",
            "benchmark_family",
        ],
    }


def _has_openai_config(client: Any | None) -> bool:
    return client is not None or bool(openai_api_key())


def _draft_with_llm(idea: str, client: Any | None = None) -> StrategySpec | None:
    client = client or _openai_client()
    messages = [
        {
            "role": "system",
            "content": (
                "Generate an Open Composer StrategySpec. Keep real trading manual_signal. "
                "Use registered capabilities only: market.alpaca_bars, market.longbridge_bars, "
                "events.sec_filings, macro.fred_series, news.alpha_vantage, news.gdelt. "
                "Use conservative risk."
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
    if _is_breakout_idea(idea):
        return _breakout_draft(idea)
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
            "research_design": _standard_research_design(
                parameter_space={
                    "entry_ema_bars": [3, 5, 8],
                    "rsi_bars": [3, 6, 14],
                    "stop_loss_pct": [0.8, 1.0, 1.2],
                    "take_profit_pct": [1.5, 2.0, 2.5],
                },
                candidate_budget=200,
                selection_objective="alpha_vs_benchmark_family_after_costs",
            ),
            "notes": {
                "intent": (
                    "Buy pullbacks only after deterministic technical confirmation; attach "
                    "company event, macro, and news context before manual or paper action."
                ),
                "research_design": _research_design(
                    data_timeframe=timeframe,
                    method_variants=["pullback", "context_filter"],
                    factor_variants=[
                        "ema_trend",
                        "rsi_state",
                        "volume_confirmation",
                        "event_news_macro_context",
                    ],
                    parameter_ranges={
                        "entry_ema_bars": [3, 5, 8],
                        "rsi_bars": [3, 6, 14],
                        "stop_loss_pct": [0.8, 1.0, 1.2],
                        "take_profit_pct": [1.5, 2.0, 2.5],
                    },
                    universe_variants=[[symbol]],
                ),
                "open_questions": [
                    (
                        "Evaluate Longbridge Nasdaq Basic versus Alpaca IEX before relying on "
                        "intraday fills."
                    ),
                    "Measure Alpha Vantage and GDELT coverage against the active watchlist.",
                ],
            },
        }
    )


def _breakout_draft(idea: str) -> StrategySpec:
    symbol = _extract_symbol(idea)
    timeframe = "15m" if _mentions_intraday(idea) else "1h"
    slug = f"{symbol.lower()}_breakout_volume_{timeframe}".replace("-", "_")
    return StrategySpec.model_validate(
        {
            "name": slug,
            "description": (
                f"{symbol} breakout strategy using lagged highs, volume confirmation, "
                "and volatility filters."
            ),
            "timeframe": timeframe,
            "universe": [symbol],
            "lifecycle": "draft",
            "factors": {
                "breakout_level": {
                    "source": "expression",
                    "expression": "lag(highest(close, 6), 1)",
                    "description": "Prior rolling high shifted by one bar.",
                },
                "volatility_range": {
                    "source": "expression",
                    "expression": "atr(5)",
                    "description": "Five-bar average true range.",
                },
                "bear_cross": {
                    "source": "expression",
                    "expression": "crossunder(ema(close, 3), ema(close, 8))",
                    "description": "Short EMA crossing below slow EMA.",
                },
            },
            "entry": {
                "all": [
                    "close > breakout_level",
                    "volume > sma(volume, 5)",
                    "volatility_range > 0.45",
                ]
            },
            "exit": {
                "any": [
                    "close < ema(close, 5)",
                    "bear_cross",
                ]
            },
            "risk": {
                "max_trades_per_day": 2,
                "max_position_weight": 0.12,
                "stop_loss_pct": 1.0,
                "take_profit_pct": 2.4,
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
            "llm_review": {"enabled": False, "model": None},
            "required_capabilities": ["market.sample_ohlcv"],
            "research_design": _standard_research_design(
                parameter_space={
                    "breakout_lookback_bars": [5, 6, 10],
                    "atr_bars": [5, 8, 14],
                    "stop_loss_pct": [0.8, 1.0, 1.2],
                    "take_profit_pct": [2.0, 2.4, 3.0],
                },
                candidate_budget=120,
                selection_objective="risk_adjusted_alpha_after_costs",
            ),
            "notes": {
                "intent": (
                    "Trade deterministic price breakouts only after a prior-window high is "
                    "exceeded with volume and minimum realized range."
                ),
                "research_design": _research_design(
                    data_timeframe=timeframe,
                    method_variants=["breakout", "volume_expansion", "trend_follow"],
                    factor_variants=[
                        "lagged_high",
                        "volume_confirmation",
                        "atr_filter",
                        "ema_exit",
                    ],
                    parameter_ranges={
                        "breakout_lookback_bars": [5, 6, 10],
                        "atr_bars": [5, 8, 14],
                        "stop_loss_pct": [0.8, 1.0, 1.2],
                        "take_profit_pct": [2.0, 2.4, 3.0],
                    },
                    universe_variants=[[symbol]],
                ),
                "open_questions": [
                    "Add commission and slippage sensitivity before paper automation.",
                    "Validate breakout lookback length with out-of-sample data.",
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
            "research_design": _standard_research_design(
                parameter_space={
                    "fast_ema_bars": [5, 8, 13],
                    "slow_ema_bars": [13, 21, 34],
                    "rsi_bars": [6, 14],
                    "stop_loss_pct": [0.8, 1.1, 1.5],
                    "take_profit_pct": [2.0, 3.2, 4.0],
                },
                candidate_budget=200,
                selection_objective="theme_proxy_alpha_after_costs",
            ),
            "notes": {
                "intent": (
                    "Trade intraday continuation in memory/storage names when MU leads on "
                    "price, volume, and AI data-center context. Real trading remains manual."
                ),
                "research_design": _research_design(
                    data_timeframe=timeframe,
                    method_variants=["momentum", "rotation", "theme_proxy"],
                    factor_variants=[
                        "ema_trend",
                        "relative_momentum",
                        "volume_confirmation",
                        "event_news_macro_context",
                    ],
                    parameter_ranges={
                        "fast_ema_bars": [5, 8, 13],
                        "slow_ema_bars": [13, 21, 34],
                        "rsi_bars": [6, 14],
                        "stop_loss_pct": [0.8, 1.1, 1.5],
                        "take_profit_pct": [2.0, 3.2, 4.0],
                    },
                    universe_variants=[["MU"], ["MU", "WDC", "STX"]],
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


def _is_breakout_idea(idea: str) -> bool:
    normalized = idea.lower()
    keywords = [
        "breakout",
        "volume expansion",
        "new high",
        "突破",
        "放量",
        "创新高",
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


def _research_design(
    *,
    data_timeframe: str,
    method_variants: list[str],
    factor_variants: list[str],
    parameter_ranges: dict[str, list[object]],
    universe_variants: list[list[str]],
) -> dict[str, object]:
    return {
        "data_timeframe": data_timeframe,
        "signal_timeframe": data_timeframe,
        "rebalance_frequency": "bar_close",
        "llm_review_frequency": "post_signal_only",
        "method_variants": method_variants,
        "factor_variants": factor_variants,
        "parameter_ranges": parameter_ranges,
        "universe_variants": universe_variants,
        "candidate_cap": 200,
        "objective": "alpha_vs_benchmark_family_after_costs",
    }


def _prompt_session_id(idea: str) -> str:
    import hashlib

    digest = hashlib.sha256(idea.encode("utf-8")).hexdigest()[:16]
    return f"idea_{digest}"


def _relpath(path: Path, base: Path) -> str:
    try:
        return path.relative_to(base).as_posix()
    except ValueError:
        return path.as_posix()
