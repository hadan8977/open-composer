from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import yaml

from open_composer.adapters.data import fetch_ohlcv
from open_composer.config import data_feed, ensure_dir, project_root
from open_composer.engines.backtest_engine import BacktestArtifacts, backtest_frame
from open_composer.models.strategy_spec import StrategySpec, load_strategy_spec
from open_composer.research.optimizer import _candidate_specs


@dataclass(frozen=True)
class UniverseSelection:
    symbol: str
    spec: StrategySpec
    artifacts: BacktestArtifacts
    score: float
    bars: int


@dataclass(frozen=True)
class UniverseOptimizationResult:
    report_path: Path
    selected_specs: list[Path]
    selections: list[UniverseSelection]


def optimize_strategy_universe(
    spec_path: Path,
    root: Path | None = None,
    symbols: list[str] | None = None,
    data_source: Literal["alpaca"] = "alpaca",
    feed: str | None = None,
    min_return_pct: float = 1.0,
    min_signals: int = 1,
    max_trades: int = 45,
    refresh_data: bool = True,
) -> UniverseOptimizationResult:
    base = root or project_root()
    source_spec = load_strategy_spec(spec_path)
    universe = [item.upper() for item in (symbols or source_spec.universe)]
    selected: list[UniverseSelection] = []
    output_paths: list[Path] = []
    for symbol in universe:
        candidate_base = _symbol_spec(
            source_spec, symbol, universe, data_source, feed or data_feed()
        )
        frame = fetch_ohlcv(
            root=base,
            symbol=symbol,
            timeframe=candidate_base.timeframe,
            start=None,
            end=None,
            feed=candidate_base.data.feed or data_feed(),
            use_cache=not refresh_data,
        )
        scored: list[UniverseSelection] = []
        for candidate in _candidate_specs(candidate_base):
            artifacts = backtest_frame(candidate, frame, run_id_value=f"universe-{candidate.name}")
            score = _score_universe_candidate(artifacts, min_return_pct, min_signals, max_trades)
            scored.append(
                UniverseSelection(
                    symbol=symbol,
                    spec=candidate,
                    artifacts=artifacts,
                    score=score,
                    bars=len(frame),
                )
            )
        scored.sort(key=lambda item: item.score, reverse=True)
        winner = scored[0]
        selected.append(winner)
        output_paths.append(_write_selected_spec(base, winner.spec))
    selected.sort(key=lambda item: item.score, reverse=True)
    report_path = base / "reports" / "research" / f"{source_spec.name}-universe-optimization.md"
    _write_universe_report(
        report_path,
        source_spec,
        selected,
        min_return_pct,
        min_signals,
        max_trades,
    )
    return UniverseOptimizationResult(
        report_path=report_path,
        selected_specs=output_paths,
        selections=selected,
    )


def _symbol_spec(
    source: StrategySpec,
    symbol: str,
    universe: list[str],
    data_source: Literal["alpaca"],
    feed: str,
) -> StrategySpec:
    raw = source.model_dump(mode="json")
    raw["name"] = f"{_base_strategy_name(source.name)}_{symbol.lower()}_{data_source}"
    raw["description"] = f"{source.description} Universe candidate for {symbol}."
    raw["universe"] = universe
    raw["lifecycle"] = "draft"
    raw["execution"] = {**raw["execution"], "mode": "manual_signal", "broker": "none"}
    raw["data"] = {"source": data_source, "symbol": symbol, "path": None, "feed": feed}
    raw["data_assumptions"] = {
        **raw["data_assumptions"],
        "source": data_source,
        "timezone": "America/New_York",
    }
    raw["required_capabilities"] = [
        "market.alpaca_bars" if item.startswith("market.") else item
        for item in raw.get("required_capabilities", [])
    ]
    raw["notes"] = {
        **raw.get("notes", {}),
        "universe_optimization": (
            "Selected from per-symbol Alpaca 15m candidates with turnover-aware scoring."
        ),
    }
    return StrategySpec.model_validate(raw)


def _base_strategy_name(name: str) -> str:
    marker = "_optimized_"
    return name.split(marker, 1)[0] if marker in name else name


def _score_universe_candidate(
    artifacts: BacktestArtifacts,
    min_return_pct: float,
    min_signals: int,
    max_trades: int,
) -> float:
    run = artifacts.run
    score = run.total_return_pct
    if run.total_return_pct < min_return_pct:
        score -= 5.0
    if run.signals < min_signals or run.trades == 0:
        score -= 5.0
    score += min(run.trades, max_trades) * 0.02
    score -= run.signals * 0.01
    score -= max(0, run.trades - max_trades) * 0.25
    score -= max(0, run.signals - max_trades * 2) * 0.08
    if run.total_return_pct < 0:
        score -= 5.0
    return score


def _write_selected_spec(root: Path, spec: StrategySpec) -> Path:
    output_path = root / "strategy_specs" / "drafts" / f"{spec.name}.yaml"
    ensure_dir(output_path.parent)
    output_path.write_text(
        yaml.safe_dump(spec.model_dump(mode="json"), sort_keys=False),
        encoding="utf-8",
    )
    return output_path


def _write_universe_report(
    path: Path,
    source: StrategySpec,
    selections: list[UniverseSelection],
    min_return_pct: float,
    min_signals: int,
    max_trades: int,
) -> Path:
    ensure_dir(path.parent)
    lines = [
        f"# Universe Optimization: {source.name}",
        "",
        f"- Symbols: {', '.join(item.symbol for item in selections)}",
        f"- Minimum return target: {min_return_pct:.2f}%",
        f"- Minimum signal target: {min_signals}",
        f"- Max preferred closed trades: {max_trades}",
        "- Return metric: period account-level return, not annualized.",
        "- Score penalizes excessive trades/signals for paper/live executability.",
        "",
        "## Selected Per Symbol",
        "",
    ]
    for item in selections:
        run = item.artifacts.run
        lines.extend(
            [
                f"### {item.symbol}: {item.spec.name}",
                "",
                f"- Score: {item.score:.2f}",
                f"- Bars: {item.bars}",
                f"- Return: {run.total_return_pct:.2f}%",
                f"- Signals: {run.signals}",
                f"- Closed trades: {run.trades}",
                f"- Entry: `{'; '.join([*item.spec.entry.all, *item.spec.entry.any])}`",
                f"- Exit: `{'; '.join([*item.spec.exit.all, *item.spec.exit.any])}`",
                "",
            ]
        )
    path.write_text("\n".join(lines), encoding="utf-8")
    return path
