from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from statistics import mean
from time import perf_counter
from typing import Any

from open_composer.capabilities import load_registry
from open_composer.config import data_feed, ensure_dir, project_root
from open_composer.feature_packets import (
    FeaturePacketEvidence,
    FeaturePacketRow,
    assert_visible_at_not_in_future,
    inspect_feature_packet,
)
from open_composer.json_utils import json_safe_payload
from open_composer.models.event import EventRecord
from open_composer.models.strategy_spec import StrategySpec, load_strategy_spec
from open_composer.research.hybrid_router_core import (
    HybridRouterMetrics,
    HybridRouterParams,
    _DailyHybridDataset,
    _effective_lookback,
    _hybrid_selected_symbols,
    _load_daily_hybrid_dataset,
    hybrid_params_from_label,
)
from open_composer.research.intraday_daily_rotation import (
    _alpha,
    _annualized_from_total,
    _win_pct,
)
from open_composer.research.metadata import (
    hypothesis_ledger,
    runtime_payload,
    search_space,
)
from open_composer.research.router_common import (
    daily_buy_hold_return as _daily_buy_hold_return,
)
from open_composer.research.router_common import (
    daily_sharpe as _daily_sharpe,
)
from open_composer.research.router_common import (
    max_drawdown_pct as _max_drawdown_pct,
)
from open_composer.research.router_common import (
    symbol_holding_return as _symbol_holding_return,
)
from open_composer.storage import write_json


@dataclass(frozen=True)
class NewsFeatureSnapshot:
    symbol: str
    decision_timestamp: datetime
    events: list[EventRecord]
    sentiment_score: float
    latest_published_at: datetime
    latest_fetched_at: datetime
    visible_at: datetime

    @property
    def news_count(self) -> int:
        return len(self.events)

    @property
    def missing_news(self) -> bool:
        return not self.events


@dataclass(frozen=True)
class HybridNewsMarginalLiftResult:
    report_path: Path
    json_path: Path
    feature_packet_path: Path
    baseline: HybridRouterMetrics
    news_gated: HybridRouterMetrics
    missing_news_fallback: HybridRouterMetrics
    news_only: HybridRouterMetrics
    llm_contribution_pass: bool
    marginal_lift_alpha_annualized_pct: float | None


def run_hybrid_news_marginal_lift_research(
    spec_path: Path,
    root: Path | None = None,
    *,
    symbols: list[str] | None = None,
    data_source: str = "alpaca",
    feed: str | None = None,
    start: str | None = None,
    end: str | None = None,
    benchmark_symbol: str = "TQQQ",
    market_symbol: str = "QQQ",
    selected_route_label: str | None = None,
    lookback_days: int = 5,
    sentiment_threshold: float = 0.0,
    min_oos_lift_pct: float = 1.0,
    out_of_sample_ratio: float = 0.3,
    refresh_data: bool = False,
) -> HybridNewsMarginalLiftResult:
    started_at = perf_counter()
    stages: dict[str, float] = {}
    base = root or project_root()
    spec = load_strategy_spec(spec_path)
    universe = [item.upper() for item in (symbols or spec.universe)]
    selected_feed = feed or spec.data.feed or data_feed()
    label = selected_route_label or spec.portfolio.selected_route_label
    if not label:
        raise ValueError("hybrid news marginal-lift research requires selected_route_label")
    params = hybrid_params_from_label(label)

    stage_started = perf_counter()
    dataset = _load_daily_hybrid_dataset(
        spec=spec,
        root=base,
        symbols=universe,
        data_source=data_source,
        feed=selected_feed,
        start=start,
        end=end,
        benchmark_symbol=benchmark_symbol,
        market_symbol=market_symbol,
        refresh_data=refresh_data,
    )
    stages["load_data"] = perf_counter() - stage_started

    stage_started = perf_counter()
    events = _load_replayable_news_events(base)
    feature_cache = _build_feature_cache(
        dataset=dataset,
        events=events,
        lookback_days=lookback_days,
    )
    stages["build_pit_news_features"] = perf_counter() - stage_started

    start_index = _effective_lookback(params)
    end_index = _hybrid_end_index(dataset, params)
    split = _split_index(len(dataset.dates), out_of_sample_ratio, params)

    stage_started = perf_counter()
    baseline_train = _backtest_variant(
        spec=spec,
        dataset=dataset,
        params=params,
        feature_cache=feature_cache,
        start_index=start_index,
        end_index=split,
        variant="quant_baseline",
        sentiment_threshold=sentiment_threshold,
    )
    baseline_oos = _backtest_variant(
        spec=spec,
        dataset=dataset,
        params=params,
        feature_cache=feature_cache,
        start_index=split,
        end_index=end_index,
        variant="quant_baseline",
        sentiment_threshold=sentiment_threshold,
    )
    baseline_full = _backtest_variant(
        spec=spec,
        dataset=dataset,
        params=params,
        feature_cache=feature_cache,
        start_index=start_index,
        end_index=end_index,
        variant="quant_baseline",
        sentiment_threshold=sentiment_threshold,
    )
    news_gated_oos = _backtest_variant(
        spec=spec,
        dataset=dataset,
        params=params,
        feature_cache=feature_cache,
        start_index=split,
        end_index=end_index,
        variant="news_gated",
        sentiment_threshold=sentiment_threshold,
    )
    news_gated_full = _backtest_variant(
        spec=spec,
        dataset=dataset,
        params=params,
        feature_cache=feature_cache,
        start_index=start_index,
        end_index=end_index,
        variant="news_gated",
        sentiment_threshold=sentiment_threshold,
    )
    missing_news_fallback = _backtest_variant(
        spec=spec,
        dataset=dataset,
        params=params,
        feature_cache={},
        start_index=split,
        end_index=end_index,
        variant="missing_news_fallback",
        sentiment_threshold=sentiment_threshold,
    )
    news_only_oos = _backtest_variant(
        spec=spec,
        dataset=dataset,
        params=params,
        feature_cache=feature_cache,
        start_index=split,
        end_index=end_index,
        variant="news_only",
        sentiment_threshold=sentiment_threshold,
    )
    stages["backtest_variants"] = perf_counter() - stage_started

    marginal_lift = _metric_delta(
        news_gated_oos.alpha_vs_benchmark_buy_hold_annualized_pct,
        baseline_oos.alpha_vs_benchmark_buy_hold_annualized_pct,
    )
    news_coverage = _coverage_stats(feature_cache, split, end_index)
    llm_contribution_pass = bool(
        marginal_lift is not None
        and marginal_lift >= min_oos_lift_pct
        and news_gated_oos.traded_days >= 20
        and news_coverage["rows_with_news"] > 0
    )

    json_path = base / "reports" / "research" / f"{spec.name}-news-marginal-lift.json"
    report_path = json_path.with_suffix(".md")
    feature_packet_path = _feature_packet_path(spec, base)
    evidence = _packet_evidence(
        baseline_oos=baseline_oos,
        news_gated_oos=news_gated_oos,
        missing_news_fallback=missing_news_fallback,
        marginal_lift=marginal_lift,
        report_path=report_path,
        root=base,
    )

    stage_started = perf_counter()
    packet_count = _write_feature_packets(
        path=feature_packet_path,
        spec=spec,
        dataset=dataset,
        feature_cache=feature_cache,
        evidence=evidence,
    )
    inspection = inspect_feature_packet(feature_packet_path, "sentiment_score")
    stages["write_feature_packets"] = perf_counter() - stage_started

    runtime = runtime_payload(started_at, stages)
    _write_json(
        path=json_path,
        spec_path=spec_path,
        spec=spec,
        dataset=dataset,
        params=params,
        events=events,
        lookback_days=lookback_days,
        sentiment_threshold=sentiment_threshold,
        min_oos_lift_pct=min_oos_lift_pct,
        out_of_sample_ratio=out_of_sample_ratio,
        split_index=split,
        baseline_train=baseline_train,
        baseline_oos=baseline_oos,
        baseline_full=baseline_full,
        news_gated_oos=news_gated_oos,
        news_gated_full=news_gated_full,
        missing_news_fallback=missing_news_fallback,
        news_only_oos=news_only_oos,
        marginal_lift=marginal_lift,
        news_coverage=news_coverage,
        llm_contribution_pass=llm_contribution_pass,
        feature_packet_path=feature_packet_path,
        feature_packet_count=packet_count,
        feature_packet_inspection=inspection.model_dump(mode="json"),
        runtime=runtime,
        root=base,
    )
    _write_markdown(
        path=report_path,
        json_path=json_path,
        spec=spec,
        dataset=dataset,
        params=params,
        lookback_days=lookback_days,
        sentiment_threshold=sentiment_threshold,
        min_oos_lift_pct=min_oos_lift_pct,
        baseline_oos=baseline_oos,
        news_gated_oos=news_gated_oos,
        missing_news_fallback=missing_news_fallback,
        news_only_oos=news_only_oos,
        news_gated_full=news_gated_full,
        marginal_lift=marginal_lift,
        news_coverage=news_coverage,
        llm_contribution_pass=llm_contribution_pass,
        feature_packet_path=feature_packet_path,
        inspection_status=inspection.point_in_time_status,
        runtime=runtime,
    )
    return HybridNewsMarginalLiftResult(
        report_path=report_path,
        json_path=json_path,
        feature_packet_path=feature_packet_path,
        baseline=baseline_oos,
        news_gated=news_gated_oos,
        missing_news_fallback=missing_news_fallback,
        news_only=news_only_oos,
        llm_contribution_pass=llm_contribution_pass,
        marginal_lift_alpha_annualized_pct=marginal_lift,
    )


def _build_feature_cache(
    *,
    dataset: _DailyHybridDataset,
    events: list[EventRecord],
    lookback_days: int,
) -> dict[tuple[int, str], NewsFeatureSnapshot]:
    cache: dict[tuple[int, str], NewsFeatureSnapshot] = {}
    events_by_symbol = _index_news_events(events)
    for index in range(1, len(dataset.dates)):
        decision_timestamp = _decision_timestamp(dataset, index)
        for symbol in dataset.symbols:
            eligible = _eligible_events(
                symbol=symbol,
                market_symbol=dataset.market_symbol,
                decision_timestamp=decision_timestamp,
                events_by_symbol=events_by_symbol,
                lookback_days=lookback_days,
            )
            latest_published = max(
                (event.published_at for event in eligible),
                default=decision_timestamp,
            )
            latest_fetched = max(
                (event.fetched_at for event in eligible),
                default=decision_timestamp,
            )
            latest_published = _utc(latest_published)
            latest_fetched = _utc(latest_fetched)
            visible_at = max(
                (_event_visible_at(event) for event in eligible), default=decision_timestamp
            )
            if visible_at > decision_timestamp:
                visible_at = decision_timestamp
            cache[(index, symbol)] = NewsFeatureSnapshot(
                symbol=symbol,
                decision_timestamp=decision_timestamp,
                events=eligible,
                sentiment_score=_news_sentiment_score(eligible),
                latest_published_at=latest_published,
                latest_fetched_at=latest_fetched,
                visible_at=visible_at,
            )
    return cache


def _backtest_variant(
    *,
    spec: StrategySpec,
    dataset: _DailyHybridDataset,
    params: HybridRouterParams,
    feature_cache: dict[tuple[int, str], NewsFeatureSnapshot],
    start_index: int,
    end_index: int,
    variant: str,
    sentiment_threshold: float,
    start_equity: float = 100_000.0,
) -> HybridRouterMetrics:
    start_index = max(start_index, _effective_lookback(params))
    end_index = min(end_index, _hybrid_end_index(dataset, params))
    returns: list[float] = []
    selected_counts: list[int] = []
    equity_curve = [start_equity]
    equity = start_equity
    traded_days = 0
    round_trips = 0
    skipped_days = 0
    max_names_by_weight = max(1, int(1 / params.max_position_weight))
    effective_top_n = min(params.top_n, max_names_by_weight, spec.risk.max_trades_per_day)
    for index in range(start_index, end_index):
        selected = _selected_for_variant(
            spec=spec,
            dataset=dataset,
            params=params,
            feature_cache=feature_cache,
            index=index,
            top_n=effective_top_n,
            variant=variant,
            sentiment_threshold=sentiment_threshold,
        )
        if not selected:
            strategy_return = 0.0
            skipped_days += 1
        else:
            weight = min(params.max_position_weight, 1 / len(selected))
            strategy_return = sum(
                weight * _symbol_holding_return(dataset, symbol, index, params.holding_mode, spec)
                for symbol in selected
            )
            traded_days += 1
            round_trips += len(selected)
        selected_counts.append(len(selected))
        returns.append(strategy_return)
        equity *= 1 + strategy_return
        equity_curve.append(equity)
    period_dates = dataset.dates[start_index:end_index]
    total_return_pct = (equity / start_equity - 1) * 100
    benchmark_buy_hold = _daily_buy_hold_return(
        dataset,
        dataset.benchmark_symbol,
        start_index,
        end_index,
    )
    market_buy_hold = _daily_buy_hold_return(
        dataset,
        dataset.market_symbol,
        start_index,
        end_index,
    )
    equal_weight_buy_hold = mean(
        _daily_buy_hold_return(dataset, symbol, start_index, end_index)
        for symbol in dataset.symbols
    )
    universe_returns = {
        symbol: _daily_buy_hold_return(dataset, symbol, start_index, end_index)
        for symbol in dataset.symbols
    }
    best_symbol = max(universe_returns, key=universe_returns.get) if universe_returns else None
    best_return = universe_returns[best_symbol] if best_symbol else 0.0
    annualized = _annualized_from_total(total_return_pct, len(returns))
    benchmark_annualized = _annualized_from_total(benchmark_buy_hold, len(returns))
    market_annualized = _annualized_from_total(market_buy_hold, len(returns))
    equal_weight_annualized = _annualized_from_total(equal_weight_buy_hold, len(returns))
    return HybridRouterMetrics(
        days=len(returns),
        start_date=period_dates[0] if period_dates else None,
        end_date=period_dates[-1] if period_dates else None,
        total_return_pct=total_return_pct,
        annualized_return_pct=annualized,
        sharpe_ratio=_daily_sharpe(returns),
        max_drawdown_pct=_max_drawdown_pct(equity_curve),
        traded_days=traded_days,
        round_trips=round_trips,
        average_selected_count=mean(selected_counts) if selected_counts else 0.0,
        win_day_pct=_win_pct(returns),
        benchmark_symbol=dataset.benchmark_symbol,
        benchmark_buy_hold_return_pct=benchmark_buy_hold,
        benchmark_buy_hold_annualized_pct=benchmark_annualized,
        alpha_vs_benchmark_buy_hold_annualized_pct=_alpha(annualized, benchmark_annualized),
        market_symbol=dataset.market_symbol,
        market_buy_hold_return_pct=market_buy_hold,
        market_buy_hold_annualized_pct=market_annualized,
        alpha_vs_market_buy_hold_annualized_pct=_alpha(annualized, market_annualized),
        equal_weight_buy_hold_return_pct=equal_weight_buy_hold,
        equal_weight_buy_hold_annualized_pct=equal_weight_annualized,
        alpha_vs_equal_weight_buy_hold_annualized_pct=_alpha(annualized, equal_weight_annualized),
        best_symbol_buy_hold_pct=best_return,
        best_symbol=best_symbol,
        alpha_vs_best_symbol_buy_hold_pct=total_return_pct - best_return,
        exposure_pct=(traded_days / len(returns) * 100) if returns else 0.0,
        skipped_days=skipped_days,
    )


def _selected_for_variant(
    *,
    spec: StrategySpec,
    dataset: _DailyHybridDataset,
    params: HybridRouterParams,
    feature_cache: dict[tuple[int, str], NewsFeatureSnapshot],
    index: int,
    top_n: int,
    variant: str,
    sentiment_threshold: float,
) -> list[str]:
    if variant == "news_only":
        scored: list[tuple[float, str]] = []
        for symbol in dataset.symbols:
            snapshot = feature_cache.get((index, symbol))
            if snapshot is None or snapshot.news_count == 0:
                continue
            if snapshot.sentiment_score >= sentiment_threshold:
                scored.append((snapshot.sentiment_score, symbol))
        scored.sort(reverse=True)
        return [symbol for _, symbol in scored[:top_n]]

    selected = _hybrid_selected_symbols(dataset, index, params, top_n)
    if variant in {"quant_baseline", "missing_news_fallback"}:
        return selected
    if variant != "news_gated":
        raise ValueError(f"unsupported hybrid news variant: {variant}")
    filtered: list[str] = []
    for symbol in selected:
        snapshot = feature_cache.get((index, symbol))
        if snapshot is None or snapshot.missing_news:
            filtered.append(symbol)
            continue
        if snapshot.sentiment_score >= sentiment_threshold:
            filtered.append(symbol)
    return filtered[: min(top_n, spec.risk.max_trades_per_day)]


def _write_feature_packets(
    *,
    path: Path,
    spec: StrategySpec,
    dataset: _DailyHybridDataset,
    feature_cache: dict[tuple[int, str], NewsFeatureSnapshot],
    evidence: FeaturePacketEvidence,
) -> int:
    ensure_dir(path.parent)
    rows: list[dict[str, Any]] = []
    for (index, _symbol), snapshot in sorted(feature_cache.items()):
        packet = _feature_packet_row(
            spec=spec,
            dataset=dataset,
            index=index,
            snapshot=snapshot,
            evidence=evidence,
        )
        assert_visible_at_not_in_future(packet)
        rows.append(packet.model_dump(mode="json", exclude_none=True))
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(json_safe_payload(row), sort_keys=True) + "\n")
    return len(rows)


def _feature_packet_row(
    *,
    spec: StrategySpec,
    dataset: _DailyHybridDataset,
    index: int,
    snapshot: NewsFeatureSnapshot,
    evidence: FeaturePacketEvidence,
) -> FeaturePacketRow:
    event_payload = [
        {
            "source": event.source,
            "symbol": event.symbol,
            "published_at": _utc(event.published_at).isoformat(),
            "fetched_at": _utc(event.fetched_at).isoformat(),
            "sentiment": event.sentiment,
            "relevance_score": event.relevance_score,
            "dedupe_key": event.dedupe_key,
            "title": event.title,
        }
        for event in snapshot.events
    ]
    positive_count = sum(event.sentiment == "positive" for event in snapshot.events)
    negative_count = sum(event.sentiment == "negative" for event in snapshot.events)
    neutral_count = sum(event.sentiment == "neutral" for event in snapshot.events)
    return FeaturePacketRow(
        timestamp=snapshot.decision_timestamp,
        published_at=snapshot.latest_published_at,
        fetched_at=snapshot.latest_fetched_at,
        visible_at=snapshot.visible_at,
        source="hybrid_router_news_replay",
        symbol=snapshot.symbol,
        dedupe_key=f"hybrid_news:{spec.name}:{dataset.dates[index]}:{snapshot.symbol}",
        schema_version="1",
        summary=(
            f"PIT local-rule news features for {snapshot.symbol} on {dataset.dates[index]}; "
            f"{snapshot.news_count} eligible trial/free news records."
        ),
        sentiment=_score_to_sentiment(snapshot.sentiment_score),
        model="local-rule-news-v1",
        input_hash=_hash_payload(
            {
                "strategy": spec.name,
                "date": dataset.dates[index],
                "symbol": snapshot.symbol,
                "events": event_payload,
            }
        ),
        prompt_hash=_hash_payload(
            {
                "template": "hybrid_router_news_marginal_lift_v1",
                "rule": "weighted sentiment over PIT eligible symbol, QQQ, SPY, and FED news",
            }
        ),
        features={
            "sentiment_score": snapshot.sentiment_score,
            "news_count": snapshot.news_count,
            "positive_news_count": positive_count,
            "negative_news_count": negative_count,
            "neutral_news_count": neutral_count,
            "max_relevance": max(
                (event.relevance_score for event in snapshot.events),
                default=0.0,
            ),
            "trial_news_only": True,
            "missing_news": snapshot.missing_news,
        },
        evidence=evidence,
    )


def _packet_evidence(
    *,
    baseline_oos: HybridRouterMetrics,
    news_gated_oos: HybridRouterMetrics,
    missing_news_fallback: HybridRouterMetrics,
    marginal_lift: float | None,
    report_path: Path,
    root: Path,
) -> FeaturePacketEvidence:
    return FeaturePacketEvidence(
        single_modality_baseline_metric=(
            "quant_baseline_oos_alpha_vs_tqqq_ann="
            f"{_fmt(baseline_oos.alpha_vs_benchmark_buy_hold_annualized_pct)}"
        ),
        marginal_lift_metric=(
            "news_gated_oos_alpha_vs_tqqq_ann="
            f"{_fmt(news_gated_oos.alpha_vs_benchmark_buy_hold_annualized_pct)}; "
            f"lift={_fmt(marginal_lift)}"
        ),
        missing_modality_robustness=(
            "missing_news_fallback_oos_alpha_vs_tqqq_ann="
            f"{_fmt(missing_news_fallback.alpha_vs_benchmark_buy_hold_annualized_pct)}"
        ),
        fixture_path=_relpath(report_path, root),
        notes="Trial/free news replay evidence; not independent paper-ready LLM/news Alpha.",
    )


def _write_json(
    *,
    path: Path,
    spec_path: Path,
    spec: StrategySpec,
    dataset: _DailyHybridDataset,
    params: HybridRouterParams,
    events: list[EventRecord],
    lookback_days: int,
    sentiment_threshold: float,
    min_oos_lift_pct: float,
    out_of_sample_ratio: float,
    split_index: int,
    baseline_train: HybridRouterMetrics,
    baseline_oos: HybridRouterMetrics,
    baseline_full: HybridRouterMetrics,
    news_gated_oos: HybridRouterMetrics,
    news_gated_full: HybridRouterMetrics,
    missing_news_fallback: HybridRouterMetrics,
    news_only_oos: HybridRouterMetrics,
    marginal_lift: float | None,
    news_coverage: dict[str, int | float],
    llm_contribution_pass: bool,
    feature_packet_path: Path,
    feature_packet_count: int,
    feature_packet_inspection: dict[str, Any],
    runtime: dict[str, Any],
    root: Path,
) -> Path:
    capability_summary = _news_capability_summary(root)
    payload = {
        "strategy_name": spec.name,
        "source_spec_path": _relpath(spec_path, root),
        "mode": "hybrid_news_marginal_lift",
        "route_label": params.label,
        "symbols": dataset.symbols,
        "market_symbol": dataset.market_symbol,
        "benchmark_symbol": dataset.benchmark_symbol,
        "data_profile": dataset.data_profile,
        "research_window": {
            "start": baseline_full.start_date,
            "end": baseline_full.end_date,
            "out_of_sample_ratio": out_of_sample_ratio,
            "split_date": dataset.dates[split_index] if split_index < len(dataset.dates) else None,
        },
        "capabilities": capability_summary,
        "news_sources": {
            "event_count": len(events),
            "lookback_days": lookback_days,
            "sentiment_threshold": sentiment_threshold,
            "trial_news_only": True,
        },
        "search_space": search_space(
            family="hybrid_news_marginal_lift",
            candidate_count=3,
            parameter_ranges={
                "news_variant": ["quant_baseline", "news_gated", "missing_news_fallback"],
                "lookback_days": [lookback_days],
                "sentiment_threshold": [sentiment_threshold],
                "selected_route_label": [params.label],
            },
            filters=[
                "feature packets replay by visible_at",
                "no live LLM or live news calls inside backtest",
                "missing-news fallback keeps deterministic quant route",
            ],
        ),
        "hypothesis_ledger": hypothesis_ledger(
            hypothesis=(
                "PIT news/sentiment features add marginal lift to the selected hybrid route."
            ),
            visible_evidence=[
                "quant baseline OOS metrics",
                "news-gated OOS metrics",
                "missing-modality fallback OOS metrics",
                "feature packet inspection",
                "no live LLM call; Alpha Vantage/GDELT news sentiment replay only",
            ],
            hidden_evidence=[],
            counterevidence=[] if llm_contribution_pass else _llm_counterevidence(news_coverage),
            conclusion="passed" if llm_contribution_pass else "failed",
        ),
        "metrics": {
            "baseline_train": baseline_train.__dict__,
            "baseline_oos": baseline_oos.__dict__,
            "baseline_full": baseline_full.__dict__,
            "news_gated_oos": news_gated_oos.__dict__,
            "news_gated_full": news_gated_full.__dict__,
            "missing_news_fallback_oos": missing_news_fallback.__dict__,
            "news_only_oos": news_only_oos.__dict__,
        },
        "marginal_lift": {
            "alpha_vs_tqqq_annualized_pct": marginal_lift,
            "min_required_pct": min_oos_lift_pct,
            "news_contribution_pass": llm_contribution_pass,
            "llm_contribution_pass": llm_contribution_pass,
            "independent_llm_alpha_pass": False,
            "llm_api_called": False,
            "feature_modality": "trial_news_sentiment_replay",
            "interpretation": (
                "PIT news/sentiment feature shows positive marginal lift; this is not "
                "independent LLM Alpha."
                if llm_contribution_pass
                else "No independent news/LLM Alpha is evidenced; keep feature advisory."
            ),
        },
        "news_coverage": news_coverage,
        "missing_modality_robustness": {
            "fallback_policy": "neutral_quant_route",
            "oos_alpha_vs_tqqq_annualized_pct": (
                missing_news_fallback.alpha_vs_benchmark_buy_hold_annualized_pct
            ),
            "matches_baseline": _metric_delta(
                missing_news_fallback.alpha_vs_benchmark_buy_hold_annualized_pct,
                baseline_oos.alpha_vs_benchmark_buy_hold_annualized_pct,
            )
            == 0,
        },
        "feature_packets": {
            "path": _relpath(feature_packet_path, root),
            "record_count": feature_packet_count,
            "inspection": feature_packet_inspection,
        },
        "runtime_seconds": runtime,
        "safety_note": (
            "This is PIT replay evidence from trial/free news fixtures or cache. It is not "
            "paper-ready market evidence and does not call a live LLM."
        ),
    }
    return write_json(path, payload)


def _write_markdown(
    *,
    path: Path,
    json_path: Path,
    spec: StrategySpec,
    dataset: _DailyHybridDataset,
    params: HybridRouterParams,
    lookback_days: int,
    sentiment_threshold: float,
    min_oos_lift_pct: float,
    baseline_oos: HybridRouterMetrics,
    news_gated_oos: HybridRouterMetrics,
    missing_news_fallback: HybridRouterMetrics,
    news_only_oos: HybridRouterMetrics,
    news_gated_full: HybridRouterMetrics,
    marginal_lift: float | None,
    news_coverage: dict[str, int | float],
    llm_contribution_pass: bool,
    feature_packet_path: Path,
    inspection_status: str,
    runtime: dict[str, Any],
) -> Path:
    ensure_dir(path.parent)
    lines = [
        f"# Hybrid News Marginal-Lift Evidence: {spec.name}",
        "",
        f"- JSON report: `{json_path}`",
        f"- Feature packet: `{feature_packet_path}`",
        f"- Route: `{params.label}`",
        f"- Symbols: `{', '.join(dataset.symbols)}`",
        f"- Market/benchmark: `{dataset.market_symbol}` / `{dataset.benchmark_symbol}`",
        f"- Lookback days: `{lookback_days}`",
        f"- Sentiment threshold: `{sentiment_threshold}`",
        f"- Minimum OOS lift required: `{min_oos_lift_pct:.2f}%`",
        f"- Feature packet PIT status: `{inspection_status}`",
        f"- Runtime seconds: `{runtime['total']:.2f}`",
        "",
        "## Result",
        "",
        f"- News/alternative-data contribution pass: `{llm_contribution_pass}`",
        "- Independent LLM Alpha pass: `False`",
        f"- OOS marginal lift vs quant baseline: `{_fmt(marginal_lift)}%`",
        f"- OOS news coverage rows with news: `{news_coverage['rows_with_news']}`",
        f"- OOS news coverage ratio: `{news_coverage['coverage_ratio']:.4f}`",
        "",
        "## OOS Metrics",
        "",
        "| Variant | Return | Annualized | Alpha vs TQQQ Annualized | Sharpe | Traded Days |",
        "|---|---:|---:|---:|---:|---:|",
        _variant_row("quant_baseline", baseline_oos),
        _variant_row("news_gated", news_gated_oos),
        _variant_row("missing_news_fallback", missing_news_fallback),
        _variant_row("news_only", news_only_oos),
        "",
        "## Full Window News-Gated",
        "",
        f"- Return: `{news_gated_full.total_return_pct:.2f}%`",
        f"- Annualized: `{_fmt(news_gated_full.annualized_return_pct)}%`",
        f"- Alpha vs TQQQ annualized: "
        f"`{_fmt(news_gated_full.alpha_vs_benchmark_buy_hold_annualized_pct)}%`",
        "- Traded days / round trips: "
        f"`{news_gated_full.traded_days}/{news_gated_full.round_trips}`",
        "",
        "## Interpretation",
        "",
        "- Feature packets include visible_at, published_at, fetched_at, source, input_hash, "
        "prompt_hash, and marginal-lift evidence fields.",
        "- Trial/free news is used only as PIT replay context; this report does not make "
        "the strategy paper-ready.",
        "- If the marginal lift is zero or negative, the correct conclusion is that "
        "LLM/news remains advisory rather than independent Alpha.",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _eligible_events(
    *,
    symbol: str,
    market_symbol: str,
    decision_timestamp: datetime,
    events_by_symbol: dict[str, list[EventRecord]],
    lookback_days: int,
) -> list[EventRecord]:
    lower_bound = decision_timestamp - timedelta(days=lookback_days)
    allowed_symbols = {symbol.upper(), market_symbol.upper(), "QQQ", "SPY", "FED"}
    selected: list[EventRecord] = []
    seen: set[str] = set()
    for allowed_symbol in allowed_symbols:
        for event in events_by_symbol.get(allowed_symbol, []):
            if event.dedupe_key in seen:
                continue
            visible_at = _event_visible_at(event)
            if visible_at > decision_timestamp:
                continue
            if visible_at < lower_bound:
                continue
            selected.append(event)
            seen.add(event.dedupe_key)
    selected.sort(key=lambda item: (item.relevance_score, item.published_at), reverse=True)
    return selected[:12]


def _index_news_events(events: list[EventRecord]) -> dict[str, list[EventRecord]]:
    indexed: dict[str, list[EventRecord]] = {}
    for event in events:
        if event.source not in {"alpha_vantage", "gdelt"}:
            continue
        indexed.setdefault(event.symbol.upper(), []).append(event)
    for symbol_events in indexed.values():
        symbol_events.sort(key=_event_visible_at)
    return indexed


def _load_replayable_news_events(root: Path) -> list[EventRecord]:
    paths: list[Path] = []
    raw_root = root / "data" / "raw" / "events"
    if raw_root.exists():
        paths.extend(sorted(raw_root.rglob("*.jsonl")))
    for relative in [
        "data/fixtures/capabilities/alpha_vantage_news.jsonl",
        "data/fixtures/capabilities/gdelt_news.jsonl",
    ]:
        fixture_path = root / relative
        if fixture_path.exists():
            paths.append(fixture_path)
    records: list[EventRecord] = []
    for path in paths:
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                try:
                    records.append(EventRecord.model_validate(json.loads(line)))
                except (json.JSONDecodeError, ValueError):
                    continue
    return _dedupe_events(records)


def _dedupe_events(records: list[EventRecord]) -> list[EventRecord]:
    output: list[EventRecord] = []
    seen: set[str] = set()
    for record in sorted(records, key=lambda item: item.published_at):
        if record.dedupe_key in seen:
            continue
        seen.add(record.dedupe_key)
        output.append(record)
    return output


def _news_sentiment_score(events: list[EventRecord]) -> float:
    if not events:
        return 0.0
    score = 0.0
    total_weight = 0.0
    for event in events:
        direction = {"positive": 1.0, "negative": -1.0, "neutral": 0.0}.get(
            event.sentiment,
            0.0,
        )
        weight = max(event.relevance_score, 0.1)
        score += direction * weight
        total_weight += weight
    return score / total_weight if total_weight > 0 else 0.0


def _event_visible_at(event: EventRecord) -> datetime:
    visible_at = getattr(event, "visible_at", None)
    if visible_at is not None:
        return _utc(visible_at)
    return _utc(event.published_at)


def _score_to_sentiment(score: float) -> str:
    if score > 0.15:
        return "positive"
    if score < -0.15:
        return "negative"
    return "neutral"


def _coverage_stats(
    feature_cache: dict[tuple[int, str], NewsFeatureSnapshot],
    start_index: int,
    end_index: int,
) -> dict[str, int | float]:
    rows = [
        snapshot
        for (index, _symbol), snapshot in feature_cache.items()
        if start_index <= index < end_index
    ]
    rows_with_news = sum(snapshot.news_count > 0 for snapshot in rows)
    return {
        "rows": len(rows),
        "rows_with_news": rows_with_news,
        "coverage_ratio": rows_with_news / len(rows) if rows else 0.0,
        "total_news_records": sum(snapshot.news_count for snapshot in rows),
    }


def _news_capability_summary(root: Path) -> list[dict[str, object]]:
    registry = load_registry(root)
    rows = []
    for capability in registry.capabilities:
        if capability.kind != "news":
            continue
        rows.append(
            {
                "id": capability.id,
                "status": capability.status,
                "provider": capability.provider,
                "fixture": capability.fixture,
                "caveats": capability.caveats,
            }
        )
    return rows


def _feature_packet_path(spec: StrategySpec, root: Path) -> Path:
    factor = spec.factors.get("news_sentiment_gate")
    if factor and factor.path:
        path = Path(factor.path)
        return path if path.is_absolute() else root / path
    return root / "feature_logs" / f"{spec.name}_news_features.jsonl"


def _decision_timestamp(dataset: _DailyHybridDataset, index: int) -> datetime:
    previous_index = max(0, index - 1)
    return datetime.fromisoformat(f"{dataset.dates[previous_index]}T20:00:00+00:00")


def _split_index(frame_len: int, ratio: float, params: HybridRouterParams) -> int:
    max_lookback = _effective_lookback(params)
    split = int(frame_len * (1 - ratio))
    split = max(split, max_lookback + 20)
    return min(split, frame_len - 20)


def _hybrid_end_index(dataset: _DailyHybridDataset, params: HybridRouterParams) -> int:
    if params.holding_mode == "open_to_open":
        return len(dataset.frame) - 1
    return len(dataset.frame)


def _metric_delta(value: float | None, baseline: float | None) -> float | None:
    if value is None or baseline is None:
        return None
    return value - baseline


def _variant_row(label: str, metrics: HybridRouterMetrics) -> str:
    return (
        f"| `{label}` | {metrics.total_return_pct:.2f}% | "
        f"{_fmt(metrics.annualized_return_pct)}% | "
        f"{_fmt(metrics.alpha_vs_benchmark_buy_hold_annualized_pct)}% | "
        f"{_fmt(metrics.sharpe_ratio)} | {metrics.traded_days} |"
    )


def _llm_counterevidence(news_coverage: dict[str, int | float]) -> list[str]:
    rows = ["external_llm_api_not_called"]
    if int(news_coverage.get("rows_with_news", 0) or 0) == 0:
        rows.append("no_pit_news_rows_in_oos_window")
    else:
        rows.append("marginal_lift_below_required_threshold")
    rows.append("trial_news_sources_are_not_paper_ready_market_evidence")
    return rows


def _hash_payload(payload: Any) -> str:
    encoded = json.dumps(json_safe_payload(payload), sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _utc(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def _fmt(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.2f}"


def _relpath(path: Path | str, root: Path) -> str:
    candidate = Path(path)
    try:
        return candidate.relative_to(root).as_posix()
    except ValueError:
        return candidate.as_posix()
