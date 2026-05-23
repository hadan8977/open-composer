from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from open_composer.research.hybrid_router_core import run_hybrid_adaptive_router_research


@dataclass(frozen=True)
class WideRouterResearchResult:
    report_path: Path
    json_path: Path
    selected_route_label: str
    research_pass: bool
    paper_ready_pass: bool


def run_wide_router_research(
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
    refresh_data: bool = False,
) -> WideRouterResearchResult:
    result = run_hybrid_adaptive_router_research(
        spec_path,
        root,
        symbols=symbols,
        data_source=data_source,
        feed=feed,
        start=start,
        end=end,
        benchmark_symbol=benchmark_symbol,
        market_symbol=market_symbol,
        holding_modes=["open_to_open"],
        momentum_lookback_days=[20, 40],
        top_n_values=[1, 2],
        market_sma_days=[None, 50],
        max_candidates=16,
        walk_forward_top_k=4,
        refresh_data=refresh_data,
    )
    return WideRouterResearchResult(
        report_path=result.report_path,
        json_path=result.json_path,
        selected_route_label=result.selected_route_label,
        research_pass=result.research_pass,
        paper_ready_pass=False,
    )
