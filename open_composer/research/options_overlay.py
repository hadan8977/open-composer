from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import yaml

from open_composer.config import ensure_dir, project_root, run_id
from open_composer.engines.backtest_engine import run_backtest
from open_composer.models.options import (
    OptionBacktestRun,
    OptionBacktestTrade,
    OptionOverlaySpec,
)
from open_composer.models.strategy_spec import load_strategy_spec
from open_composer.storage import write_json


@dataclass(frozen=True)
class OptionOverlayArtifacts:
    spec: OptionOverlaySpec
    run: OptionBacktestRun
    trades: list[OptionBacktestTrade]
    score: float


@dataclass(frozen=True)
class OptionOverlayOptimizationResult:
    report_path: Path
    selected_spec_paths: list[Path]
    artifacts: list[OptionOverlayArtifacts]


def optimize_option_overlays(
    spec_paths: list[Path],
    root: Path | None = None,
    max_premium_weight: float = 0.03,
    min_trades: int = 1,
) -> OptionOverlayOptimizationResult:
    base = root or project_root()
    selected: list[OptionOverlayArtifacts] = []
    selected_paths: list[Path] = []
    all_artifacts: list[OptionOverlayArtifacts] = []
    for spec_path in spec_paths:
        equity_spec = load_strategy_spec(spec_path)
        equity_artifacts = run_backtest(spec_path, root=base)
        candidates = _overlay_candidates(
            equity_spec.name, equity_spec.primary_symbol, max_premium_weight
        )
        scored: list[OptionOverlayArtifacts] = []
        for overlay in candidates:
            run, trades = backtest_option_overlay(
                overlay,
                equity_artifacts.trades,
                underlying_total_return_pct=equity_artifacts.run.total_return_pct,
                underlying_trades=equity_artifacts.run.trades,
            )
            score = _score_overlay(run, min_trades)
            scored.append(OptionOverlayArtifacts(overlay, run, trades, score))
        scored.sort(key=lambda item: item.score, reverse=True)
        all_artifacts.extend(scored)
        winner = scored[0]
        selected.append(winner)
        selected_paths.append(_write_overlay_spec(base, winner.spec))
        _write_overlay_report(base, winner)
    selected.sort(key=lambda item: item.score, reverse=True)
    report_path = base / "reports" / "research" / "memory_storage_options_overlay_optimization.md"
    _write_summary_report(report_path, selected, all_artifacts)
    return OptionOverlayOptimizationResult(report_path, selected_paths, selected)


def backtest_option_overlay(
    spec: OptionOverlaySpec,
    equity_trades,
    start_equity: float = 100_000.0,
    underlying_total_return_pct: float | None = None,
    underlying_trades: int | None = None,
) -> tuple[OptionBacktestRun, list[OptionBacktestTrade]]:
    equity = start_equity
    option_trades: list[OptionBacktestTrade] = []
    skipped = 0
    for trade in equity_trades:
        if trade.exit_time is None or trade.exit_price is None:
            skipped += 1
            continue
        option_trade = _price_option_trade(spec, trade, equity)
        if option_trade is None:
            skipped += 1
            continue
        equity += option_trade.pnl
        option_trades.append(option_trade)
    run = OptionBacktestRun(
        run_id=run_id(f"options-{spec.name}"),
        overlay_name=spec.name,
        underlying_strategy=spec.underlying_strategy,
        symbol=spec.symbol,
        overlay_type=spec.overlay_type,
        trades=len(option_trades),
        skipped_trades=skipped,
        start_equity=start_equity,
        end_equity=equity,
        total_return_pct=(equity / start_equity - 1) * 100,
        underlying_total_return_pct=underlying_total_return_pct,
        underlying_trades=underlying_trades,
        assumptions=[
            "Underlying entry/exit signals come from the equity StrategySpec backtest.",
            "Option prices use a Black-Scholes approximation, not historical option quotes.",
            "Entry buys at approximate ask and exit sells at approximate bid using spread_pct.",
            "Implied volatility is held constant through each option trade.",
            "Contracts are whole-number only; premium at risk is capped by max_premium_weight.",
            "This is paper/research output, not live options execution.",
        ],
    )
    return run, option_trades


def _overlay_candidates(
    underlying_strategy: str,
    symbol: str,
    max_premium_weight: float,
) -> list[OptionOverlaySpec]:
    base = f"{underlying_strategy}_options"
    return [
        OptionOverlaySpec(
            name=f"{base}_long_call_atm_30d",
            underlying_strategy=underlying_strategy,
            symbol=symbol,
            overlay_type="long_call",
            dte=30,
            long_moneyness_pct=0.0,
            implied_volatility=0.65,
            spread_pct=0.08,
            max_premium_weight=max_premium_weight,
            notes=["ATM long call; highest convexity and theta risk among MVP candidates."],
        ),
        OptionOverlaySpec(
            name=f"{base}_long_call_otm_30d",
            underlying_strategy=underlying_strategy,
            symbol=symbol,
            overlay_type="long_call",
            dte=30,
            long_moneyness_pct=3.0,
            implied_volatility=0.70,
            spread_pct=0.10,
            max_premium_weight=max_premium_weight,
            notes=["3% OTM long call; lower premium and higher breakeven."],
        ),
        OptionOverlaySpec(
            name=f"{base}_long_call_otm_liquid_30d",
            underlying_strategy=underlying_strategy,
            symbol=symbol,
            overlay_type="long_call",
            dte=30,
            long_moneyness_pct=3.0,
            implied_volatility=0.70,
            spread_pct=0.06,
            max_premium_weight=max_premium_weight,
            notes=[
                "3% OTM long call with a stricter liquidity assumption.",
                "Use only if live option chain spread checks confirm this is realistic.",
            ],
        ),
        OptionOverlaySpec(
            name=f"{base}_debit_spread_30d",
            underlying_strategy=underlying_strategy,
            symbol=symbol,
            overlay_type="debit_call_spread",
            dte=30,
            long_moneyness_pct=0.0,
            short_moneyness_pct=7.0,
            implied_volatility=0.65,
            spread_pct=0.10,
            max_premium_weight=max_premium_weight,
            notes=["Defined-risk call debit spread with capped upside."],
        ),
        OptionOverlaySpec(
            name=f"{base}_debit_spread_otm_30d",
            underlying_strategy=underlying_strategy,
            symbol=symbol,
            overlay_type="debit_call_spread",
            dte=30,
            long_moneyness_pct=2.0,
            short_moneyness_pct=10.0,
            implied_volatility=0.70,
            spread_pct=0.12,
            max_premium_weight=max_premium_weight,
            notes=["OTM defined-risk call spread; higher directional threshold."],
        ),
    ]


def _price_option_trade(
    spec: OptionOverlaySpec, trade, equity: float
) -> OptionBacktestTrade | None:
    entry = float(trade.entry_price)
    exit_ = float(trade.exit_price)
    hold_years = max((trade.exit_time - trade.entry_time).total_seconds(), 0) / (365 * 24 * 3600)
    entry_t = spec.dte / 365
    exit_t = max(entry_t - hold_years, 1 / 365)
    long_strike = _round_strike(entry * (1 + spec.long_moneyness_pct / 100))
    long_entry_mid = _black_scholes_call(
        entry, long_strike, entry_t, spec.risk_free_rate, spec.implied_volatility
    )
    long_exit_mid = _black_scholes_call(
        exit_, long_strike, exit_t, spec.risk_free_rate, spec.implied_volatility
    )
    entry_debit = long_entry_mid * (1 + spec.spread_pct / 2)
    exit_value = long_exit_mid * (1 - spec.spread_pct / 2)
    short_strike = None
    if spec.overlay_type == "debit_call_spread":
        if spec.short_moneyness_pct is None:
            return None
        short_strike = _round_strike(entry * (1 + spec.short_moneyness_pct / 100))
        if short_strike <= long_strike:
            return None
        short_entry_mid = _black_scholes_call(
            entry, short_strike, entry_t, spec.risk_free_rate, spec.implied_volatility
        )
        short_exit_mid = _black_scholes_call(
            exit_, short_strike, exit_t, spec.risk_free_rate, spec.implied_volatility
        )
        entry_debit = (long_entry_mid * (1 + spec.spread_pct / 2)) - (
            short_entry_mid * (1 - spec.spread_pct / 2)
        )
        exit_value = (long_exit_mid * (1 - spec.spread_pct / 2)) - (
            short_exit_mid * (1 + spec.spread_pct / 2)
        )
    if entry_debit <= 0 or exit_value < 0:
        return None
    premium_budget = equity * spec.max_premium_weight
    contracts = math.floor(premium_budget / (entry_debit * spec.contract_multiplier))
    if contracts < 1:
        return None
    premium_at_risk = contracts * entry_debit * spec.contract_multiplier
    pnl = contracts * (exit_value - entry_debit) * spec.contract_multiplier
    return OptionBacktestTrade(
        entry_time=trade.entry_time,
        exit_time=trade.exit_time,
        underlying_entry=entry,
        underlying_exit=exit_,
        underlying_return_pct=float(trade.return_pct),
        long_strike=long_strike,
        short_strike=short_strike,
        entry_debit=entry_debit,
        exit_value=exit_value,
        contracts=contracts,
        premium_at_risk=premium_at_risk,
        pnl=pnl,
        return_pct=(exit_value / entry_debit - 1) * 100,
    )


def _black_scholes_call(
    spot: float, strike: float, time_years: float, rate: float, vol: float
) -> float:
    if spot <= 0 or strike <= 0:
        return 0.0
    time_years = max(time_years, 1 / 365)
    vol_sqrt_t = vol * math.sqrt(time_years)
    if vol_sqrt_t <= 0:
        return max(0.0, spot - strike * math.exp(-rate * time_years))
    d1 = (math.log(spot / strike) + (rate + 0.5 * vol * vol) * time_years) / vol_sqrt_t
    d2 = d1 - vol_sqrt_t
    return spot * _norm_cdf(d1) - strike * math.exp(-rate * time_years) * _norm_cdf(d2)


def _norm_cdf(value: float) -> float:
    return 0.5 * (1 + math.erf(value / math.sqrt(2)))


def _round_strike(value: float) -> float:
    if value >= 100:
        increment = 5.0
    elif value >= 25:
        increment = 2.5
    else:
        increment = 1.0
    return round(value / increment) * increment


def _score_overlay(run: OptionBacktestRun, min_trades: int) -> float:
    score = run.total_return_pct
    if run.trades < min_trades:
        score -= 25
    if run.total_return_pct < 0:
        score -= 10
    score -= run.trades * 0.02
    return score


def _write_overlay_spec(root: Path, spec: OptionOverlaySpec) -> Path:
    path = root / "strategy_specs" / "options" / f"{spec.name}.yaml"
    ensure_dir(path.parent)
    path.write_text(yaml.safe_dump(spec.model_dump(mode="json"), sort_keys=False), encoding="utf-8")
    return path


def _write_overlay_report(root: Path, artifacts: OptionOverlayArtifacts) -> Path:
    report_path = root / "reports" / "options" / f"{artifacts.run.run_id}.md"
    ensure_dir(report_path.parent)
    artifacts.run.report_path = str(report_path)
    write_json(root / "reports" / "options" / f"{artifacts.run.run_id}.json", artifacts.run)
    trade_path = root / "reports" / "options" / f"{artifacts.run.run_id}-trades.json"
    write_json(
        trade_path, {"trades": [trade.model_dump(mode="json") for trade in artifacts.trades]}
    )
    lines = [
        f"# Options Overlay Backtest: {artifacts.spec.name}",
        "",
        f"- Symbol: `{artifacts.run.symbol}`",
        f"- Underlying strategy: `{artifacts.run.underlying_strategy}`",
        f"- Overlay: `{artifacts.run.overlay_type}`",
        f"- Trades: {artifacts.run.trades}",
        f"- Skipped trades: {artifacts.run.skipped_trades}",
        f"- Start equity: {artifacts.run.start_equity:.2f}",
        f"- End equity: {artifacts.run.end_equity:.2f}",
        f"- Total return: {artifacts.run.total_return_pct:.2f}%",
        "- Underlying equity return: "
        f"{_format_optional_pct(artifacts.run.underlying_total_return_pct)}",
        f"- Underlying equity trades: {_format_optional_int(artifacts.run.underlying_trades)}",
        "",
        "## Option Parameters",
        "",
        f"- DTE: {artifacts.spec.dte}",
        f"- Long moneyness: {artifacts.spec.long_moneyness_pct:.2f}%",
        f"- Short moneyness: {artifacts.spec.short_moneyness_pct}",
        f"- IV assumption: {artifacts.spec.implied_volatility:.2f}",
        f"- Spread assumption: {artifacts.spec.spread_pct:.2f}",
        f"- Max premium weight: {artifacts.spec.max_premium_weight:.2f}",
        "",
        "## Assumptions",
        "",
        *[f"- {item}" for item in artifacts.run.assumptions],
        "",
        "## Trades",
        "",
    ]
    if artifacts.trades:
        lines.extend(
            f"- {trade.entry_time.isoformat()} -> {trade.exit_time.isoformat()} "
            f"contracts={trade.contracts} PnL={trade.pnl:.2f} "
            f"option_return={trade.return_pct:.2f}% "
            f"underlying_return={trade.underlying_return_pct:.2f}%"
            for trade in artifacts.trades
        )
    else:
        lines.append("- No option trades.")
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report_path


def _write_summary_report(
    path: Path,
    selected: list[OptionOverlayArtifacts],
    all_artifacts: list[OptionOverlayArtifacts],
) -> Path:
    ensure_dir(path.parent)
    lines = [
        "# Memory/Storage Options Overlay Optimization",
        "",
        "- Scope: paper/research only.",
        "- Underlying: existing equity StrategySpec signals.",
        "- Pricing: Black-Scholes approximation with spread haircut, not historical option quotes.",
        "- Execution: no option orders are submitted by this command.",
        "- Selection: best overlays are research candidates, not activation recommendations.",
        "",
        "## Selected",
        "",
    ]
    for item in selected:
        lines.extend(
            [
                f"### {item.run.symbol}: {item.spec.name}",
                "",
                f"- Overlay: `{item.run.overlay_type}`",
                f"- Return: {item.run.total_return_pct:.2f}%",
                "- Underlying equity return: "
                f"{_format_optional_pct(item.run.underlying_total_return_pct)}",
                f"- Trades: {item.run.trades}",
                f"- Score: {item.score:.2f}",
                f"- Decision: {_decision_text(item)}",
                "",
            ]
        )
    lines.extend(["## All Candidates", ""])
    for item in sorted(all_artifacts, key=lambda entry: entry.score, reverse=True):
        lines.append(
            f"- `{item.spec.name}` {item.run.symbol} {item.run.overlay_type} "
            f"return={item.run.total_return_pct:.2f}% trades={item.run.trades} "
            f"underlying={_format_optional_pct(item.run.underlying_total_return_pct)} "
            f"score={item.score:.2f}"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _format_optional_pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.2f}%"


def _format_optional_int(value: int | None) -> str:
    return "n/a" if value is None else str(value)


def _decision_text(item: OptionOverlayArtifacts) -> str:
    if item.run.trades < 1:
        return "reject; no executable option trades under current budget/liquidity assumptions"
    if item.run.total_return_pct <= 0:
        return "reject; option overlay underperformed under current assumptions"
    if (
        item.run.underlying_total_return_pct is not None
        and item.run.total_return_pct <= item.run.underlying_total_return_pct
    ):
        return "research only; did not improve on the equity strategy"
    return "candidate for deeper option-chain validation"
