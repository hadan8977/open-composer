from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from open_composer.config import ensure_dir, project_root
from open_composer.engines.signal_engine import build_signal
from open_composer.models.signal import Signal
from open_composer.models.strategy_spec import load_strategy_spec
from open_composer.research.intraday_daily_rotation import (
    IntradayDailyCandidate,
    IntradayDailyParams,
    LLMIntradayDailyResearchResult,
    _day_bars,
    _load_dataset,
    _selected_positions,
    run_intraday_daily_rotation_research,
    run_llm_intraday_daily_rotation_selection,
)
from open_composer.storage import append_jsonl, write_json


class LLMAdaptiveRouterChoice(BaseModel):
    model_config = ConfigDict(extra="forbid")

    selected_label: str
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str
    news_usage_plan: str = ""
    expected_risks: list[str] = Field(default_factory=list)
    rejected_labels: list[str] = Field(default_factory=list)


@dataclass(frozen=True)
class AdaptiveRouterResearchResult:
    report_path: Path
    json_path: Path
    candidates: list[IntradayDailyCandidate]
    walk_forward: list[object]
    research_cost: dict[str, Any]
    runtime_seconds: dict[str, Any]
    data_profile: dict[str, Any]

    @property
    def best(self) -> Any:
        candidate = self.candidates[0]
        return SimpleNamespace(
            rank=candidate.rank,
            route=SimpleNamespace(
                label=f"open_momentum:{candidate.params.label}", sub_strategies=[candidate.params]
            ),
            train=SimpleNamespace(base=candidate.train),
            out_of_sample=SimpleNamespace(base=candidate.out_of_sample),
            full_window=SimpleNamespace(base=candidate.full_window),
            quality_flags=candidate.quality_flags,
        )


@dataclass(frozen=True)
class LLMAdaptiveRouterResearchResult:
    report_path: Path
    json_path: Path
    prompt_path: Path
    choice: LLMAdaptiveRouterChoice
    status: str


@dataclass(frozen=True)
class RoutedIntradaySubStrategy:
    label: str
    params: IntradayDailyParams


@dataclass(frozen=True)
class RoutedIntradaySignalPlan:
    symbol: str
    weight: float
    signal_price: float
    sub_strategy_label: str
    side: str = "long"


@dataclass(frozen=True)
class AdaptiveRouterScanResult:
    report_path: Path
    json_path: Path
    signal_log_path: Path
    route: Any
    selected_sub_strategy: RoutedIntradaySubStrategy | None
    signal_plans: list[RoutedIntradaySignalPlan]
    signals: list[Signal]
    latest_prices: dict[str, float]
    date: str
    feature_packet_path: Path | None = None
    context_packet_paths: list[Path] | None = None


def run_adaptive_intraday_router_research(
    spec_path: Path,
    root: Path | None = None,
    **kwargs: Any,
) -> AdaptiveRouterResearchResult:
    result = run_intraday_daily_rotation_research(spec_path, root, **_base_kwargs(kwargs))
    base = root or project_root()
    spec = load_strategy_spec(spec_path)
    payload = json.loads(result.json_path.read_text(encoding="utf-8"))
    payload["mode"] = "adaptive_intraday_internal_router"
    payload["route_family"] = "open_momentum"
    payload["acceptance_gate"] = payload.get("acceptance_gate", {"passed": False})
    json_path = base / "reports" / "research" / f"{spec.name}-adaptive-intraday-router.json"
    report_path = json_path.with_suffix(".md")
    write_json(json_path, payload)
    report_text = result.report_path.read_text(encoding="utf-8").replace(
        "# Intraday Daily Rotation",
        "# Adaptive Intraday Router",
    )
    report_text = report_text.replace(str(result.json_path), str(json_path))
    ensure_dir(report_path.parent)
    report_path.write_text(report_text, encoding="utf-8")
    _write_adaptive_router_factor_lab(base, spec.name, payload)
    return AdaptiveRouterResearchResult(
        report_path=report_path,
        json_path=json_path,
        candidates=result.candidates,
        walk_forward=result.walk_forward,
        research_cost=result.research_cost,
        runtime_seconds=result.runtime_seconds,
        data_profile=result.data_profile,
    )


def _write_adaptive_router_factor_lab(
    root: Path,
    strategy_name: str,
    payload: dict[str, Any],
) -> None:
    """Write route-level diagnostics for adaptive router promotion gates."""

    candidates = payload.get("candidates") if isinstance(payload.get("candidates"), list) else []
    selected = candidates[0] if candidates and isinstance(candidates[0], dict) else {}
    acceptance = payload.get("acceptance_gate")
    acceptance = acceptance if isinstance(acceptance, dict) else {}
    selected_flags = selected.get("quality_flags")
    acceptance_flags = acceptance.get("quality_flags")
    quality_flags = [
        str(item)
        for item in (
            selected_flags
            if isinstance(selected_flags, list)
            else acceptance_flags
            if isinstance(acceptance_flags, list)
            else []
        )
    ]
    hard_flags = [flag for flag in quality_flags if flag != "does_not_beat_ex_post_best_symbol"]
    status = "ok" if bool(acceptance.get("passed")) and not hard_flags else "warning"
    oos = _metrics_dict(selected.get("out_of_sample"))
    full = _metrics_dict(selected.get("full_window"))
    factor_metrics = [
        {
            "name": "selected_route_oos_equal_weight_alpha",
            "source": "adaptive_intraday_router",
            "value": oos.get("alpha_vs_equal_weight_annualized_pct"),
            "status": "ok"
            if (oos.get("alpha_vs_equal_weight_annualized_pct") or 0) > 0
            else "warning",
        },
        {
            "name": "selected_route_oos_sharpe",
            "source": "adaptive_intraday_router",
            "value": oos.get("sharpe_ratio"),
            "status": "ok" if (oos.get("sharpe_ratio") or 0) >= 1.0 else "warning",
        },
        {
            "name": "selected_route_full_max_drawdown",
            "source": "adaptive_intraday_router",
            "value": full.get("max_drawdown_pct"),
            "status": "ok" if abs(full.get("max_drawdown_pct") or 0) <= 30.0 else "warning",
        },
        {
            "name": "walk_forward_positive_alpha_folds",
            "source": "adaptive_intraday_router",
            "value": acceptance.get("walk_forward_positive_alpha_folds"),
            "status": "ok"
            if acceptance.get("walk_forward_positive_alpha_folds")
            == acceptance.get("walk_forward_fold_count")
            else "warning",
        },
    ]
    json_path = root / "reports" / "research" / f"{strategy_name}-factor-lab.json"
    report_path = json_path.with_suffix(".md")
    report_payload = {
        "schema_version": "1",
        "strategy_name": strategy_name,
        "mode": "router_level_diagnostic",
        "status": status,
        "generated_at": datetime.now(UTC).isoformat(),
        "selected_route_label": selected.get("label"),
        "quality_flags": hard_flags,
        "benchmark_warnings": quality_flags,
        "acceptance_gate": acceptance,
        "factor_metrics": factor_metrics,
        "source_artifact": f"reports/research/{strategy_name}-adaptive-intraday-router.json",
    }
    write_json(json_path, report_payload)
    lines = [
        f"# Router Factor Lab: {strategy_name}",
        "",
        "- Mode: `router_level_diagnostic`",
        f"- Status: `{status}`",
        f"- Selected route: `{selected.get('label') or 'missing'}`",
        f"- Quality flags: `{', '.join(hard_flags) if hard_flags else 'none'}`",
        f"- Benchmark warnings: `{', '.join(quality_flags) if quality_flags else 'none'}`",
        "",
        "## Route Metrics",
        "",
        "| Metric | Value | Status |",
        "| --- | ---: | --- |",
    ]
    for metric in factor_metrics:
        lines.append(f"| `{metric['name']}` | `{metric.get('value')}` | `{metric['status']}` |")
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _metrics_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        nested = value.get("base")
        if isinstance(nested, dict):
            return nested
        return value
    return {}


def run_llm_adaptive_intraday_router_selection(
    spec_path: Path,
    root: Path | None = None,
    *,
    client: Any | None = None,
    model: str | None = None,
    **kwargs: Any,
) -> LLMAdaptiveRouterResearchResult:
    result: LLMIntradayDailyResearchResult = run_llm_intraday_daily_rotation_selection(
        spec_path,
        root,
        client=client,
        model=model,
        **_base_kwargs(kwargs),
    )
    choice = LLMAdaptiveRouterChoice(
        selected_label=f"open_momentum:{result.choice.selected_label}"
        if not result.choice.selected_label.startswith("open_")
        else result.choice.selected_label,
        confidence=result.choice.confidence,
        rationale=result.choice.rationale,
        news_usage_plan="No news adjustment without PIT packets.",
        expected_risks=result.choice.expected_risks,
        rejected_labels=result.choice.rejected_labels,
    )
    payload = json.loads(result.json_path.read_text(encoding="utf-8"))
    payload["mode"] = "llm_adaptive_router"
    payload["choice"] = choice.model_dump(mode="json")
    write_json(result.json_path, payload)
    return LLMAdaptiveRouterResearchResult(
        report_path=result.report_path,
        json_path=result.json_path,
        prompt_path=result.prompt_path,
        choice=choice,
        status=result.status,
    )


def run_adaptive_intraday_router_scan(
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
    route_label: str | None = None,
    scan_date: str | None = None,
    refresh_data: bool = False,
    emit_context_packets: bool = True,
    emit_news_packet: bool = True,
    news_lookback_hours: int = 72,
) -> AdaptiveRouterScanResult:
    base = root or project_root()
    spec = load_strategy_spec(spec_path)
    selected_label = route_label or spec.portfolio.selected_route_label
    if not selected_label:
        raise ValueError(
            "adaptive router scan requires --route-label or portfolio.selected_route_label"
        )
    params = _parse_route_label(selected_label)
    dataset = _load_dataset(
        spec=spec,
        root=base,
        symbols=[item.upper() for item in (symbols or spec.universe)],
        data_source=data_source,
        feed=feed or spec.data.feed,
        start=start,
        end=end,
        benchmark_symbol=benchmark_symbol,
        market_symbol=market_symbol,
        refresh_data=refresh_data,
    )
    index = _scan_index(dataset, scan_date)
    selected = _selected_positions(dataset, index, params, spec)
    day = dataset.dates[index]
    timestamp = _day_bars(
        dataset, selected[0].symbol if selected else dataset.symbols[0], index
    ).timestamps[-1]
    max_weight = spec.portfolio.max_symbol_weight or spec.risk.max_position_weight
    weight = min(
        max_weight, (spec.portfolio.gross_exposure_limit or max_weight) / max(len(selected), 1)
    )
    plans: list[RoutedIntradaySignalPlan] = []
    signals: list[Signal] = []
    latest_prices: dict[str, float] = {}
    for symbol in dataset.symbols:
        bars = _day_bars(dataset, symbol, index)
        if bars is not None:
            latest_prices[symbol] = float(bars.closes[-1])
    for item in selected:
        bars = _day_bars(dataset, item.symbol, index)
        if bars is None:
            continue
        price = float(bars.closes[-1])
        signed_weight = weight if item.side == "long" else -weight
        side_override = "buy" if item.side == "long" else "sell"
        plans.append(
            RoutedIntradaySignalPlan(
                item.symbol,
                signed_weight,
                price,
                params.label,
                item.side,
            )
        )
        signals.append(
            build_signal(
                spec,
                f"adaptive-router-scan-{day}",
                timestamp,
                "entry",
                "adaptive_router_scan",
                price,
                execution_backend="python_reference",
                symbol=item.symbol,
                conditions=[
                    f"route={selected_label}",
                    f"sub_strategy={params.label}",
                    f"side={item.side}",
                ],
                target_weight=signed_weight,
                side_override=side_override,
            )
        )
    signal_log_path = base / "signal_logs" / f"adaptive-router-scan-{spec.name}-{day}.jsonl"
    append_jsonl(signal_log_path, signals)
    json_path = base / "reports" / "scans" / f"{spec.name}-adaptive-router-scan.json"
    report_path = json_path.with_suffix(".md")
    feature_path = (
        _write_news_packet(base, spec.name, day, [item.symbol for item in selected])
        if emit_news_packet
        else None
    )
    result = AdaptiveRouterScanResult(
        report_path=report_path,
        json_path=json_path,
        signal_log_path=signal_log_path,
        route=SimpleNamespace(label=selected_label),
        selected_sub_strategy=RoutedIntradaySubStrategy(params.label, params) if selected else None,
        signal_plans=plans,
        signals=signals,
        latest_prices=latest_prices,
        date=day,
        feature_packet_path=feature_path,
        context_packet_paths=[],
    )
    write_json(
        json_path,
        {
            "strategy_name": spec.name,
            "mode": "adaptive_intraday_router_scan",
            "date": day,
            "route_label": selected_label,
            "signals": [signal.model_dump(mode="json") for signal in signals],
            "signal_plans": [plan.__dict__ for plan in plans],
            "feature_packet_path": str(feature_path) if feature_path else None,
        },
    )
    ensure_dir(report_path.parent)
    report_path.write_text(
        f"# Adaptive Router Scan: {spec.name}\n\n- Date: `{day}`\n- Signals: `{len(signals)}`\n",
        encoding="utf-8",
    )
    return result


def _base_kwargs(kwargs: dict[str, Any]) -> dict[str, Any]:
    if "max_candidates" not in kwargs and kwargs.get("max_base_candidates") is not None:
        kwargs = {**kwargs, "max_candidates": kwargs["max_base_candidates"]}
    allowed = {
        "symbols",
        "data_source",
        "feed",
        "start",
        "end",
        "benchmark_symbol",
        "market_symbol",
        "lookback_days",
        "entry_after_bars",
        "top_n_values",
        "min_opening_return_pct",
        "min_prior_momentum_pct",
        "min_relative_volume",
        "selection_styles",
        "max_opening_return_pct",
        "max_prior_momentum_pct",
        "market_gates",
        "objective",
        "out_of_sample_ratio",
        "walk_forward_folds",
        "walk_forward_top_k",
        "max_candidates",
        "refresh_data",
    }
    return {key: value for key, value in kwargs.items() if key in allowed}


def _parse_route_label(label: str) -> IntradayDailyParams:
    raw = label.split(":", 1)[1] if ":" in label else label
    parts = raw.split("_")
    gate, suffix_start = _parse_market_gate_parts(parts)
    suffix = "_".join(parts[suffix_start:])
    max_opening = None
    max_momentum = None
    if "reversal" in suffix:
        for item in parts[suffix_start:]:
            if item.startswith("maxopen"):
                raw_open = item.removeprefix("maxopen")
                max_opening = None if raw_open == "none" else float(raw_open)
            if item.startswith("maxmom"):
                raw_mom = item.removeprefix("maxmom")
                max_momentum = None if raw_mom == "none" else float(raw_mom)
    return IntradayDailyParams(
        selection_style="opening_reversal" if "reversal" in raw else "opening_momentum",
        lookback_days=int(parts[0].removeprefix("lb")),
        entry_after_bars=int(parts[1].removeprefix("entry")),
        top_n=int(parts[2].removeprefix("top")),
        min_opening_return_pct=float(parts[3].removeprefix("open")),
        min_prior_momentum_pct=float(parts[4].removeprefix("mom")),
        min_relative_volume=float(parts[5].removeprefix("rv")),
        market_gate=gate,  # type: ignore[arg-type]
        max_opening_return_pct=max_opening,
        max_prior_momentum_pct=max_momentum,
    )


def _parse_market_gate_parts(parts: list[str]) -> tuple[str, int]:
    token = parts[6]
    if token == "none":
        return "none", 7
    if token == "qopen" and len(parts) > 9 and parts[8] == "prior":
        return f"qqq_open_{parts[7]}_prior_{parts[9]}", 10
    if token in {"qopen", "qprior"} and len(parts) > 7:
        return f"qqq_{token.removeprefix('q')}_{parts[7]}", 8
    return token.replace("qopen", "qqq_open").replace("qprior", "qqq_prior"), 7


def _scan_index(dataset: Any, scan_date: str | None) -> int:
    if scan_date is None:
        return len(dataset.dates) - 1
    if scan_date not in dataset.dates:
        raise ValueError(f"scan_date not present in dataset: {scan_date}")
    return dataset.dates.index(scan_date)


def _write_news_packet(root: Path, strategy_name: str, day: str, symbols: list[str]) -> Path:
    path = root / "feature_logs" / f"{strategy_name}_adaptive_router_news.jsonl"
    now = datetime.now(UTC)
    rows = [
        {
            "timestamp": now.isoformat(),
            "published_at": (now - timedelta(hours=1)).isoformat(),
            "fetched_at": now.isoformat(),
            "visible_at": now.isoformat(),
            "source": "local-rule-news-v1",
            "symbol": symbol,
            "dedupe_key": hashlib.sha256(f"{strategy_name}|{day}|{symbol}".encode()).hexdigest(),
            "schema_version": "1",
            "summary": "No live news inference in lightweight router scan.",
            "sentiment": "neutral",
            "model": "local-rule-news-v1",
            "input_hash": "sha256:" + hashlib.sha256(f"{day}|{symbol}".encode()).hexdigest(),
            "prompt_hash": "sha256:" + hashlib.sha256(b"adaptive-router-news-v1").hexdigest(),
            "features": {"trial_news_only": True, "sentiment_score": 0.0},
        }
        for symbol in (symbols or ["QQQ"])
    ]
    append_jsonl(path, rows)
    return path
