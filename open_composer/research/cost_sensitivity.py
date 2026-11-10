from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from open_composer.adapters.data import load_ohlcv_for_spec
from open_composer.config import project_root
from open_composer.engines.backtest_engine import backtest_frame
from open_composer.models.strategy_spec import StrategySpec, load_strategy_spec
from open_composer.research.iteration_dossier import (
    NativeExecutionControl,
    require_iteration_execution_gate,
)
from open_composer.research.metadata import workspace_relative_path
from open_composer.storage import write_json

ImpactModel = Literal["linear", "sqrt", "almgren_chriss"]


class CostGridResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    commission_pct: float
    slippage_bps: float
    impact_model: ImpactModel
    impact_eta: float
    impact_gamma: float
    return_pct: float
    sharpe: float
    signal_count: int
    trade_count: int


class CostGridReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    strategy_name: str
    strategy_path: str
    results: list[CostGridResult]
    ranking_spread: float
    warning: str
    selectable_candidate: Literal[False] = False
    promotion_eligible: Literal[False] = False


def run_cost_grid(
    spec_path: Path,
    *,
    commission_grid: list[float],
    slippage_grid: list[float],
    impact_models: list[str],
    root: Path | None = None,
) -> CostGridReport:
    base = root or project_root()
    spec = load_strategy_spec(spec_path)
    admission = require_iteration_execution_gate(
        spec,
        base,
        enforce_unbound_design=True,
        require_registered_iteration=spec.data.source != "sample",
    )
    controls = []
    for commission_pct in commission_grid:
        for slippage_bps in slippage_grid:
            for impact_model in impact_models:
                candidate = _rewrite_costs(
                    spec,
                    commission_pct=commission_pct,
                    slippage_bps=slippage_bps,
                    impact_model=impact_model,
                )
                control = (
                    NativeExecutionControl(
                        source=spec,
                        purpose="cost_grid",
                        parameters={
                            "commission_pct": commission_pct,
                            "slippage_bps": slippage_bps,
                            "impact_model": impact_model,
                        },
                    )
                    if admission is not None
                    else None
                )
                require_iteration_execution_gate(
                    candidate, base, enforce_unbound_design=True, native_control=control
                )
                controls.append((candidate, control))
    frame = load_ohlcv_for_spec(spec, base)
    results: list[CostGridResult] = []
    for candidate, control in controls:
        commission_pct = candidate.costs.commission_pct
        slippage_bps = candidate.costs.slippage_bps
        impact_model = candidate.costs.impact_model
        artifacts = backtest_frame(
            candidate,
            frame,
            root=base,
            run_id_value=(f"cost-grid-{spec.name}-{commission_pct}-{slippage_bps}-{impact_model}"),
            native_control=control,
        )
        results.append(
            CostGridResult(
                commission_pct=commission_pct,
                slippage_bps=slippage_bps,
                impact_model=impact_model,  # type: ignore[arg-type]
                impact_eta=candidate.costs.impact_eta,
                impact_gamma=candidate.costs.impact_gamma,
                return_pct=artifacts.run.total_return_pct,
                sharpe=artifacts.run.sharpe_ratio or 0.0,
                signal_count=artifacts.run.signals,
                trade_count=artifacts.run.trades,
            )
        )
    ranking_spread = max((item.sharpe for item in results), default=0.0) - min(
        (item.sharpe for item in results), default=0.0
    )
    warning = (
        "Sharpe spread indicates cost sensitivity"
        if ranking_spread > 1.0
        else "Cost spread is within the current warning threshold"
    )
    report = CostGridReport(
        strategy_name=spec.name,
        strategy_path=workspace_relative_path(spec_path, base),
        results=results,
        ranking_spread=ranking_spread,
        warning=warning,
    )
    out_path = base / "reports" / "cost_grid" / f"{spec.name}.json"
    md_path = out_path.with_suffix(".md")
    write_json(out_path, report)
    md_path.write_text(_render_markdown(report), encoding="utf-8")
    return report


def _rewrite_costs(
    spec: StrategySpec,
    *,
    commission_pct: float,
    slippage_bps: float,
    impact_model: str,
) -> StrategySpec:
    raw = spec.model_dump(mode="json")
    raw["costs"] = {
        **raw["costs"],
        "commission_pct": commission_pct,
        "slippage_bps": slippage_bps,
        "impact_model": impact_model,
        "impact_eta": 0.0 if impact_model == "linear" else 1.0,
        "impact_gamma": 0.0 if impact_model != "almgren_chriss" else 0.5,
    }
    return StrategySpec.model_validate(raw)


def _render_markdown(report: CostGridReport) -> str:
    lines = [
        f"# Cost Grid: {report.strategy_name}",
        "",
        f"- Strategy path: `{report.strategy_path}`",
        f"- Ranking spread: `{report.ranking_spread:.2f}`",
        f"- Warning: {report.warning}",
        "",
        "| Commission % | Slippage bps | Impact model | Return % | Sharpe | Signals | Trades |",
        "|---|---|---|---|---|---|---|",
    ]
    for result in report.results:
        lines.append(
            "| "
            f"{result.commission_pct:.4f} | {result.slippage_bps:.1f} | {result.impact_model} | "
            f"{result.return_pct:.2f} | {result.sharpe:.2f} | "
            f"{result.signal_count} | {result.trade_count} |"
        )
    return "\n".join(lines) + "\n"
