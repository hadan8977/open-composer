from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import yaml

from open_composer.adapters.data import fetch_ohlcv
from open_composer.config import data_feed, ensure_dir, project_root
from open_composer.engines.backtest_engine import BacktestArtifacts, backtest_frame
from open_composer.models.strategy_spec import StrategySpec, load_strategy_spec


@dataclass(frozen=True)
class HorizonSelection:
    symbol: str
    profile: str
    spec: StrategySpec
    artifacts: BacktestArtifacts
    score: float
    bars: int
    start_time: str
    end_time: str


@dataclass(frozen=True)
class HorizonOptimizationResult:
    report_path: Path
    selected_specs: list[Path]
    selections: list[HorizonSelection]
    candidates: list[HorizonSelection]


def optimize_strategy_horizons(
    spec_path: Path,
    root: Path | None = None,
    symbols: list[str] | None = None,
    data_source: Literal["alpaca", "longbridge"] = "alpaca",
    feed: str | None = None,
    min_return_pct: float = 1.0,
    min_sharpe: float = 0.0,
    min_trades: int = 1,
    max_preferred_trades: int = 18,
    refresh_data: bool = True,
) -> HorizonOptimizationResult:
    base = root or project_root()
    source = load_strategy_spec(spec_path)
    universe = [item.upper() for item in (symbols or source.universe)]
    selected: list[HorizonSelection] = []
    candidates: list[HorizonSelection] = []
    selected_paths: list[Path] = []
    selected_feed = feed or data_feed()

    for symbol in universe:
        scored: list[HorizonSelection] = []
        for candidate in _horizon_candidate_specs(
            source, symbol, universe, data_source, selected_feed
        ):
            frame = fetch_ohlcv(
                root=base,
                symbol=symbol,
                timeframe=candidate.timeframe,
                start=None,
                end=None,
                source=data_source,
                feed=candidate.data.feed or selected_feed,
                use_cache=not refresh_data,
            )
            artifacts = backtest_frame(
                candidate,
                frame,
                run_id_value=f"horizon-{candidate.name}",
            )
            score = _score_horizon_candidate(
                artifacts,
                min_return_pct=min_return_pct,
                min_sharpe=min_sharpe,
                min_trades=min_trades,
                max_preferred_trades=max_preferred_trades,
            )
            scored.append(
                HorizonSelection(
                    symbol=symbol,
                    profile=str(candidate.notes.model_extra.get("horizon_profile", "")),
                    spec=candidate,
                    artifacts=artifacts,
                    score=score,
                    bars=len(frame),
                    start_time=frame["timestamp"].iloc[0].isoformat(),
                    end_time=frame["timestamp"].iloc[-1].isoformat(),
                )
            )
        scored.sort(key=lambda item: item.score, reverse=True)
        winner = scored[0]
        selected.append(winner)
        candidates.extend(scored)
        selected_paths.append(_write_selected_spec(base, winner.spec))

    selected.sort(key=lambda item: item.score, reverse=True)
    candidates.sort(key=lambda item: item.score, reverse=True)
    report_path = base / "reports" / "research" / f"{source.name}-horizon-optimization.md"
    _write_horizon_report(
        report_path,
        source,
        selected,
        candidates,
        min_return_pct=min_return_pct,
        min_sharpe=min_sharpe,
        min_trades=min_trades,
        max_preferred_trades=max_preferred_trades,
    )
    return HorizonOptimizationResult(report_path, selected_paths, selected, candidates)


def _horizon_candidate_specs(
    source: StrategySpec,
    symbol: str,
    universe: list[str],
    data_source: Literal["alpaca", "longbridge"],
    feed: str,
) -> list[StrategySpec]:
    variants = [
        {
            "suffix": "5m_fast_scan",
            "profile": "higher_frequency_scan",
            "timeframe": "5m",
            "entry": {
                "all": [
                    "close > ema(close, 3)",
                    "ema(close, 3) > ema(close, 8)",
                    "rsi(close, 3) > 55",
                    "volume > sma(volume, 3)",
                ],
                "any": [],
            },
            "exit": {"all": [], "any": ["close < ema(close, 3)", "rsi(close, 3) > 88"]},
            "risk": {
                "max_trades_per_day": 4,
                "stop_loss_pct": 0.8,
                "take_profit_pct": 2.0,
            },
            "thesis": "Tests whether more frequent 5m scans capture intraday momentum earlier.",
        },
        {
            "suffix": "5m_opening_continuation",
            "profile": "higher_frequency_scan",
            "timeframe": "5m",
            "entry": {
                "all": [
                    "close > ema(close, 5)",
                    "ema(close, 5) > ema(close, 13)",
                    "rsi(close, 6) > 52",
                    "volume > sma(volume, 5)",
                ],
                "any": [],
            },
            "exit": {"all": [], "any": ["close < ema(close, 8)", "rsi(close, 6) > 92"]},
            "risk": {
                "max_trades_per_day": 3,
                "stop_loss_pct": 1.0,
                "take_profit_pct": 3.0,
            },
            "thesis": "Keeps 5m scans but requires short trend confirmation.",
        },
        {
            "suffix": "15m_trend_hold",
            "profile": "lower_turnover_hold",
            "timeframe": "15m",
            "entry": {
                "all": [
                    "close > ema(close, 8)",
                    "ema(close, 5) > ema(close, 13)",
                    "ema(close, 13) > ema(close, 21)",
                    "rsi(close, 6) > 55",
                    "volume > sma(volume, 8)",
                ],
                "any": [],
            },
            "exit": {"all": [], "any": ["close < ema(close, 21)", "rsi(close, 6) > 98"]},
            "risk": {
                "max_trades_per_day": 1,
                "stop_loss_pct": 2.0,
                "take_profit_pct": 10.0,
            },
            "thesis": "Reduces churn and lets intraday winners compound longer.",
        },
        {
            "suffix": "15m_swing_hold",
            "profile": "lower_turnover_hold",
            "timeframe": "15m",
            "entry": {
                "all": [
                    "close > ema(close, 13)",
                    "ema(close, 8) > ema(close, 21)",
                    "rsi(close, 14) > 55",
                    "volume > sma(volume, 13)",
                ],
                "any": [],
            },
            "exit": {"all": [], "any": ["close < ema(close, 34)", "rsi(close, 14) > 99"]},
            "risk": {
                "max_trades_per_day": 1,
                "stop_loss_pct": 2.5,
                "take_profit_pct": 12.0,
            },
            "thesis": "Pushes the strategy toward fewer, longer intraday/swing-style holds.",
        },
        {
            "suffix": "15m_breakout_momentum",
            "profile": "lower_turnover_hold",
            "timeframe": "15m",
            "entry": {
                "all": [
                    "close > highest(close, 20)",
                    "macd_hist(close, 12, 26, 9) > 0",
                    "roc(close, 10) > 0",
                    "volume > sma(volume, 10)",
                ],
                "any": [],
            },
            "exit": {
                "all": [],
                "any": ["close < ema(close, 8)", "macd_hist(close, 12, 26, 9) < 0"],
            },
            "risk": {
                "max_trades_per_day": 1,
                "stop_loss_pct": 1.5,
                "take_profit_pct": 5.0,
            },
            "thesis": "Tests a cleaner breakout/momentum profile on the main 15m horizon.",
        },
        {
            "suffix": "1h_trend_hold",
            "profile": "lower_frequency_trend",
            "timeframe": "1h",
            "entry": {
                "all": [
                    "close > ema(close, 8)",
                    "ema(close, 5) > ema(close, 13)",
                    "ema(close, 13) > ema(close, 21)",
                    "rsi(close, 14) > 54",
                    "volume > sma(volume, 8)",
                ],
                "any": [],
            },
            "exit": {"all": [], "any": ["close < ema(close, 21)", "rsi(close, 14) > 98"]},
            "risk": {
                "max_trades_per_day": 1,
                "stop_loss_pct": 3.0,
                "take_profit_pct": 12.0,
            },
            "thesis": "Tests whether options-friendly trend duration matters more than scan speed.",
        },
        {
            "suffix": "1h_breakout_momentum",
            "profile": "lower_frequency_trend",
            "timeframe": "1h",
            "entry": {
                "all": [
                    "close > ema(close, 21)",
                    "macd_hist(close, 12, 26, 9) > 0",
                    "rsi(close, 14) > 55",
                    "volume > sma(volume, 8)",
                ],
                "any": [],
            },
            "exit": {
                "all": [],
                "any": ["close < ema(close, 21)", "macd_hist(close, 12, 26, 9) < 0"],
            },
            "risk": {
                "max_trades_per_day": 1,
                "stop_loss_pct": 3.0,
                "take_profit_pct": 12.0,
            },
            "thesis": "Adds a higher-quality momentum breakout variant on the 1h horizon.",
        },
    ]
    output: list[StrategySpec] = []
    for variant in variants:
        raw = source.model_dump(mode="json")
        raw["name"] = (
            f"{_base_strategy_name(source.name)}_{symbol.lower()}_{data_source}_{variant['suffix']}"
        )
        raw["description"] = f"{source.description} Horizon candidate: {variant['suffix']}."
        raw["timeframe"] = variant["timeframe"]
        raw["universe"] = universe
        raw["lifecycle"] = "draft"
        raw["entry"] = variant["entry"]
        raw["exit"] = variant["exit"]
        raw["risk"] = {**raw["risk"], **variant["risk"]}
        raw["execution"] = {**raw["execution"], "mode": "manual_signal", "broker": "none"}
        raw["data"] = {"source": data_source, "symbol": symbol, "path": None, "feed": feed}
        raw["data_assumptions"] = {
            **raw["data_assumptions"],
            "source": data_source,
            "timezone": "America/New_York",
        }
        raw["required_capabilities"] = [
            (
                "market.longbridge_bars"
                if data_source == "longbridge" and item.startswith("market.")
                else "market.alpaca_bars"
                if item.startswith("market.")
                else item
            )
            for item in raw.get("required_capabilities", [])
        ]
        raw["notes"] = {
            **raw.get("notes", {}),
            "horizon_profile": variant["profile"],
            "horizon_thesis": variant["thesis"],
            "horizon_optimization": (
                "Selected from 5m higher-frequency, 15m lower-turnover, "
                "and 1h trend-hold candidates."
            ),
        }
        output.append(StrategySpec.model_validate(raw))
    return output


def _score_horizon_candidate(
    artifacts: BacktestArtifacts,
    min_return_pct: float,
    min_sharpe: float,
    min_trades: int,
    max_preferred_trades: int,
) -> float:
    run = artifacts.run
    annualized_return = (
        run.annualized_return_pct if run.annualized_return_pct is not None else run.total_return_pct
    )
    sharpe_bonus = max(run.sharpe_ratio or 0.0, 0.0) * 5.0
    score = annualized_return or 0.0
    if (annualized_return or 0.0) < min_return_pct:
        score -= 5.0
    if (run.sharpe_ratio or 0.0) < min_sharpe:
        score -= 5.0
    if run.trades < min_trades:
        score -= 5.0
    if (annualized_return or 0.0) < 0:
        score -= 5.0
    score += sharpe_bonus
    score += min(run.trades, max_preferred_trades) * 0.03
    score -= run.signals * 0.015
    score -= max(0, run.trades - max_preferred_trades) * 0.35
    return score


def _base_strategy_name(name: str) -> str:
    marker = "_optimized_"
    return name.split(marker, 1)[0] if marker in name else name


def _write_selected_spec(root: Path, spec: StrategySpec) -> Path:
    output_path = root / "strategy_specs" / "drafts" / f"{spec.name}.yaml"
    ensure_dir(output_path.parent)
    output_path.write_text(
        yaml.safe_dump(spec.model_dump(mode="json"), sort_keys=False),
        encoding="utf-8",
    )
    return output_path


def _write_horizon_report(
    path: Path,
    source: StrategySpec,
    selected: list[HorizonSelection],
    candidates: list[HorizonSelection],
    min_return_pct: float,
    min_sharpe: float,
    min_trades: int,
    max_preferred_trades: int,
) -> Path:
    ensure_dir(path.parent)
    lines = [
        f"# Horizon Optimization: {source.name}",
        "",
        "- Experiment: compare higher scan frequency against lower turnover and longer holds.",
        f"- Symbols: {', '.join(item.symbol for item in selected)}",
        f"- Minimum return target: {min_return_pct:.2f}%",
        f"- Minimum Sharpe target: {min_sharpe:.2f}",
        f"- Minimum closed trades: {min_trades}",
        f"- Max preferred closed trades: {max_preferred_trades}",
        "- Return metric: period account-level return, not annualized.",
        "- Scoring penalizes excessive trades/signals because options overlays are "
        "spread/theta sensitive.",
        "",
        "## Selected Per Symbol",
        "",
    ]
    for item in selected:
        run = item.artifacts.run
        lines.extend(
            [
                f"### {item.symbol}: {item.spec.name}",
                "",
                f"- Profile: `{item.profile}`",
                f"- Timeframe: `{item.spec.timeframe}`",
                f"- Score: {item.score:.2f}",
                f"- Bars: {item.bars}",
                f"- Window: {item.start_time} -> {item.end_time}",
                f"- Return: {run.total_return_pct:.2f}%",
                f"- Annualized return: {run.annualized_return_pct:.2f}%"
                if run.annualized_return_pct is not None
                else "- Annualized return: n/a",
                f"- Sharpe ratio: {run.sharpe_ratio:.2f}"
                if run.sharpe_ratio is not None
                else "- Sharpe ratio: n/a",
                f"- Signals: {run.signals}",
                f"- Closed trades: {run.trades}",
                f"- Max trades/day: {item.spec.risk.max_trades_per_day}",
                f"- Entry: `{'; '.join([*item.spec.entry.all, *item.spec.entry.any])}`",
                f"- Exit: `{'; '.join([*item.spec.exit.all, *item.spec.exit.any])}`",
                "",
            ]
        )
    lines.extend(["## All Candidates", ""])
    for item in candidates:
        run = item.artifacts.run
        annualized = _format_optional_pct(run.annualized_return_pct)
        sharpe = _format_optional_ratio(run.sharpe_ratio)
        lines.append(
            f"- `{item.spec.name}` {item.symbol} profile={item.profile} "
            f"timeframe={item.spec.timeframe} return={run.total_return_pct:.2f}% "
            f"annualized={annualized} sharpe={sharpe} "
            f"signals={run.signals} trades={run.trades} bars={item.bars} score={item.score:.2f}"
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- If 5m candidates win only through many short trades, they are scanner "
            "candidates, not options candidates.",
            "- If 15m or 1h candidates have fewer trades with comparable return, "
            "prefer them for option overlays.",
            "- If all candidates underperform the existing equity strategy, keep the "
            "current equity strategy and change the options thesis before paper execution.",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _format_optional_pct(value: float | None) -> str:
    return "" if value is None else f"{value:.2f}%"


def _format_optional_ratio(value: float | None) -> str:
    return "" if value is None else f"{value:.2f}"
