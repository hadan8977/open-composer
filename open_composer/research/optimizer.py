from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from open_composer.adapters.data import load_ohlcv_for_spec
from open_composer.config import ensure_dir, project_root
from open_composer.engines.backtest_engine import BacktestArtifacts, backtest_frame
from open_composer.models.strategy_spec import StrategySpec, load_strategy_spec
from open_composer.research.iteration_dossier import require_iteration_execution_gate


@dataclass
class OptimizationResult:
    best_spec_path: Path
    report_path: Path
    best_spec: StrategySpec
    best_artifacts: BacktestArtifacts
    candidates: list[tuple[StrategySpec, BacktestArtifacts, float]]


def optimize_strategy(
    spec_path: Path,
    root: Path | None = None,
    min_return_pct: float = 1.0,
    min_signals: int = 1,
    min_sharpe: float = 0.0,
) -> OptimizationResult:
    base = root or project_root()
    require_iteration_execution_gate(
        spec_path,
        base,
        enforce_unbound_design=True,
        require_registered_iteration=True,
    )
    spec = load_strategy_spec(spec_path)
    frame = load_ohlcv_for_spec(spec, base)
    candidates = []
    for candidate in _candidate_specs(spec):
        artifacts = backtest_frame(
            candidate,
            frame,
            root=base,
            run_id_value=f"opt-{candidate.name}",
        )
        score = _score_candidate(artifacts, min_return_pct, min_signals, min_sharpe)
        candidates.append((candidate, artifacts, score))
    candidates.sort(key=lambda item: item[2], reverse=True)
    best_spec, best_artifacts, _ = candidates[0]
    output_path = base / "strategy_specs" / "drafts" / f"{best_spec.name}.yaml"
    ensure_dir(output_path.parent)
    output_path.write_text(
        yaml.safe_dump(best_spec.model_dump(mode="json"), sort_keys=False),
        encoding="utf-8",
    )
    report_path = base / "reports" / "research" / f"{spec.name}-optimization.md"
    _write_optimization_report(
        report_path,
        spec,
        candidates,
        min_return_pct,
        min_signals,
        min_sharpe,
    )
    return OptimizationResult(
        best_spec_path=output_path,
        report_path=report_path,
        best_spec=best_spec,
        best_artifacts=best_artifacts,
        candidates=candidates,
    )


def _candidate_specs(spec: StrategySpec) -> list[StrategySpec]:
    base = spec.model_dump(mode="json")
    variants = [
        {
            "suffix": "optimized_fast",
            "entry": {
                "all": [
                    "close > ema(close, 5)",
                    "ema(close, 5) > ema(close, 13)",
                    "rsi(close, 6) > 55",
                    "volume > sma(volume, 5)",
                ]
            },
            "exit": {"any": ["close < ema(close, 5)", "rsi(close, 6) > 90"]},
            "risk": {"stop_loss_pct": 1.0, "take_profit_pct": 3.0},
        },
        {
            "suffix": "optimized_balanced",
            "entry": {
                "all": [
                    "close > ema(close, 8)",
                    "ema(close, 5) > ema(close, 13)",
                    "rsi(close, 6) > 55",
                    "volume > sma(volume, 8)",
                ]
            },
            "exit": {"any": ["close < ema(close, 8)", "rsi(close, 6) > 92"]},
            "risk": {"stop_loss_pct": 1.1, "take_profit_pct": 3.5},
        },
        {
            "suffix": "optimized_volume",
            "entry": {
                "all": [
                    "close > ema(close, 5)",
                    "rsi(close, 3) > 58",
                    "volume > sma(volume, 3)",
                ]
            },
            "exit": {"any": ["close < ema(close, 5)", "rsi(close, 3) > 94"]},
            "risk": {"stop_loss_pct": 1.2, "take_profit_pct": 2.6},
        },
        {
            "suffix": "optimized_opening_continuation",
            "entry": {
                "all": [
                    "close > ema(close, 5)",
                    "rsi(close, 6) > 50",
                    "volume > sma(volume, 5)",
                ]
            },
            "exit": {"any": ["close < ema(close, 13)", "rsi(close, 6) > 96"]},
            "risk": {
                "max_trades_per_day": 2,
                "stop_loss_pct": 1.5,
                "take_profit_pct": 6.0,
            },
        },
        {
            "suffix": "optimized_trend_hold",
            "entry": {
                "all": [
                    "close > ema(close, 8)",
                    "ema(close, 5) > ema(close, 13)",
                    "rsi(close, 6) > 52",
                    "volume > sma(volume, 5)",
                ]
            },
            "exit": {"any": ["close < ema(close, 13)", "rsi(close, 6) > 98"]},
            "risk": {
                "max_trades_per_day": 1,
                "stop_loss_pct": 1.8,
                "take_profit_pct": 8.0,
            },
        },
        {
            "suffix": "optimized_fast_reentry",
            "entry": {
                "all": [
                    "close > ema(close, 3)",
                    "rsi(close, 3) > 52",
                    "volume > sma(volume, 3)",
                ]
            },
            "exit": {"any": ["close < ema(close, 3)", "rsi(close, 3) > 88"]},
            "risk": {
                "max_trades_per_day": 4,
                "stop_loss_pct": 1.0,
                "take_profit_pct": 2.5,
            },
        },
        {
            "suffix": "optimized_breakout_momentum",
            "entry": {
                "all": [
                    "close > highest(close, 20)",
                    "macd_hist(close, 12, 26, 9) > 0",
                    "roc(close, 10) > 0",
                    "volume > sma(volume, 10)",
                ]
            },
            "exit": {"any": ["close < ema(close, 8)", "macd_hist(close, 12, 26, 9) < 0"]},
            "risk": {
                "max_trades_per_day": 1,
                "stop_loss_pct": 1.5,
                "take_profit_pct": 5.0,
            },
        },
        {
            "suffix": "optimized_mean_reversion",
            "entry": {
                "all": [
                    "close < bollinger_lower(close, 20, 2.0)",
                    "rsi(close, 6) < 30",
                    "zscore(close, 20) < 0",
                    "volume > sma(volume, 10)",
                ]
            },
            "exit": {"any": ["close > bollinger_mid(close, 20)", "rsi(close, 6) > 58"]},
            "risk": {
                "max_trades_per_day": 2,
                "stop_loss_pct": 1.2,
                "take_profit_pct": 3.0,
            },
        },
        {
            "suffix": "optimized_volume_plus",
            "entry": {
                "all": [
                    "close > ema(close, 5)",
                    "rsi(close, 4) > 56",
                    "volume > sma(volume, 5)",
                ]
            },
            "exit": {"any": ["close < ema(close, 8)", "rsi(close, 4) > 94"]},
            "risk": {
                "max_trades_per_day": 2,
                "stop_loss_pct": 1.0,
                "take_profit_pct": 4.0,
            },
        },
    ]
    output: list[StrategySpec] = []
    for variant in variants:
        raw = dict(base)
        raw["name"] = f"{spec.name}_{variant['suffix']}"
        raw["description"] = f"{spec.description} Optimized candidate: {variant['suffix']}."
        raw["entry"] = variant["entry"]
        raw["exit"] = variant["exit"]
        raw["risk"] = {**raw["risk"], **variant["risk"]}
        raw["notes"] = {
            **raw.get("notes", {}),
            "optimization_candidate": variant["suffix"],
        }
        output.append(StrategySpec.model_validate(raw))
    return output


def _score_candidate(
    artifacts: BacktestArtifacts,
    min_return_pct: float,
    min_signals: int,
    min_sharpe: float,
) -> float:
    run = artifacts.run
    annualized_return = (
        run.annualized_return_pct if run.annualized_return_pct is not None else run.total_return_pct
    )
    sharpe_bonus = max(run.sharpe_ratio or 0.0, 0.0) * 5.0
    meets_return = (annualized_return or 0.0) >= min_return_pct
    meets_signals = artifacts.run.signals >= min_signals
    meets_sharpe = (run.sharpe_ratio or 0.0) >= min_sharpe
    penalty = 0.0 if meets_return and meets_signals and meets_sharpe else 10.0
    return (
        (annualized_return or 0.0) + sharpe_bonus + run.trades * 0.25 + run.signals * 0.05 - penalty
    )


def _write_optimization_report(
    path: Path,
    original: StrategySpec,
    candidates: list[tuple[StrategySpec, BacktestArtifacts, float]],
    min_return_pct: float,
    min_signals: int,
    min_sharpe: float,
) -> Path:
    ensure_dir(path.parent)
    lines = [
        f"# Strategy Optimization: {original.name}",
        "",
        f"- Minimum return target: {min_return_pct:.2f}%",
        f"- Minimum signal target: {min_signals}",
        f"- Minimum Sharpe target: {min_sharpe:.2f}",
        "- Objective: choose the highest-scoring candidate without using future bars.",
        "- Return metric: period account-level return, not annualized.",
        "",
        "## Candidates",
        "",
    ]
    for spec, artifacts, score in candidates:
        lines.extend(
            [
                f"### {spec.name}",
                "",
                f"- Score: {score:.2f}",
                f"- Return: {artifacts.run.total_return_pct:.2f}%",
                f"- Annualized return: {artifacts.run.annualized_return_pct:.2f}%"
                if artifacts.run.annualized_return_pct is not None
                else "- Annualized return: n/a",
                f"- Sharpe ratio: {artifacts.run.sharpe_ratio:.2f}"
                if artifacts.run.sharpe_ratio is not None
                else "- Sharpe ratio: n/a",
                f"- Signals: {artifacts.run.signals}",
                f"- Closed trades: {artifacts.run.trades}",
                f"- Entry: `{'; '.join([*spec.entry.all, *spec.entry.any])}`",
                f"- Exit: `{'; '.join([*spec.exit.all, *spec.exit.any])}`",
                "",
            ]
        )
    winner = candidates[0]
    lines.extend(
        [
            "## Selected",
            "",
            f"- Strategy: `{winner[0].name}`",
            f"- Return: {winner[1].run.total_return_pct:.2f}%",
            f"- Annualized return: {winner[1].run.annualized_return_pct:.2f}%"
            if winner[1].run.annualized_return_pct is not None
            else "- Annualized return: n/a",
            f"- Sharpe ratio: {winner[1].run.sharpe_ratio:.2f}"
            if winner[1].run.sharpe_ratio is not None
            else "- Sharpe ratio: n/a",
            f"- Signals: {winner[1].run.signals}",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")
    return path
