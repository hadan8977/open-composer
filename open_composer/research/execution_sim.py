from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from statistics import fmean
from typing import Literal

from open_composer.adapters.execution.nautilus_trader import (
    build_nautilus_trader_plan,
    nautilus_trader_available,
)
from open_composer.config import ensure_dir, project_root
from open_composer.experiments import append_experiment_run, artifact_ref
from open_composer.models.experiment import ExperimentRun
from open_composer.models.market_data import MarketDataManifest
from open_composer.models.strategy_spec import load_strategy_spec
from open_composer.storage import write_json
from open_composer.strategy_versions import strategy_content_hash

ExecutionSimStatus = Literal["ok", "warning", "blocked"]


@dataclass(frozen=True)
class ExecutionSimResult:
    strategy_name: str
    status: ExecutionSimStatus
    selected_backend: str
    market_data_manifest_path: str | None
    market_data_kind: str | None
    row_count: int
    latency_ms: float
    average_spread_bps: float | None
    partial_fill_rate_proxy_pct: float | None
    blockers: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    json_path: Path | None = None
    report_path: Path | None = None


def run_execution_sim(
    spec_path: Path,
    market_data_manifest: Path | None,
    root: Path | None = None,
) -> ExecutionSimResult:
    base = root or project_root()
    spec = load_strategy_spec(spec_path)
    plan = build_nautilus_trader_plan(spec_path, base)
    blockers: list[str] = []
    warnings: list[str] = []
    manifest: MarketDataManifest | None = None
    manifest_path_label: str | None = None
    avg_spread_bps: float | None = None
    partial_fill_rate: float | None = None

    if market_data_manifest is None or not market_data_manifest.exists():
        blockers.append("market_data_manifest_missing")
    else:
        manifest = MarketDataManifest.model_validate(
            json.loads(market_data_manifest.read_text(encoding="utf-8"))
        )
        manifest_path_label = _relative_label(market_data_manifest, base)
        if manifest.paper_ready:
            warnings.append("manifest_marked_paper_ready_but_execution_sim_is_research_only")
        if manifest.kind == "trade_tick":
            warnings.append("trade_tick_has_no_quote_spread")
        if "not_monotonic" in ",".join(manifest.quality_flags):
            blockers.append("market_data_manifest_not_monotonic")
        avg_spread_bps = _average_spread_bps(base / manifest.path, manifest.kind)
        partial_fill_rate = _partial_fill_rate_proxy(spec, manifest.kind)

    if spec.execution.fill_assumption == "next_bar_open":
        warnings.append("execution_fill_assumption_is_bar_based")
    if spec.execution.fill_assumption in {"quote_mid_or_limit", "nautilus_fill_model"} and (
        manifest is None
        or manifest.kind not in {"quote_tick", "depth_snapshot", "order_book_delta"}
    ):
        blockers.append("microstructure_fill_requires_quote_or_depth_data")
    if spec.execution.backend != "nautilus_trader":
        warnings.append("strategy_backend_is_not_nautilus_trader")
    if not nautilus_trader_available():
        warnings.append("nautilus_trader_not_installed")
    status: ExecutionSimStatus = "blocked" if blockers else "warning" if warnings else "ok"
    result = ExecutionSimResult(
        strategy_name=spec.name,
        status=status,
        selected_backend=plan.selected_backend,
        market_data_manifest_path=manifest_path_label,
        market_data_kind=manifest.kind if manifest else None,
        row_count=manifest.row_count if manifest else 0,
        latency_ms=spec.reality_model.latency_ms if spec.reality_model else 0.0,
        average_spread_bps=avg_spread_bps,
        partial_fill_rate_proxy_pct=partial_fill_rate,
        blockers=blockers,
        warnings=warnings,
        json_path=base / "reports" / "research" / f"{spec.name}-execution-sim.json",
        report_path=base / "reports" / "research" / f"{spec.name}-execution-sim.md",
    )
    _write_execution_sim_outputs(result)
    append_experiment_run(
        ExperimentRun(
            run_id=f"execution-sim-{spec.name}",
            name=f"Execution Sim: {spec.name}",
            research_mode="audited",
            kind="execution_sim",
            strategy_name=spec.name,
            source_spec_path=_relative_label(spec_path, base),
            spec_hash=strategy_content_hash(spec),
            status=status,
            gate_status=status,
            metrics={
                "row_count": result.row_count,
                "average_spread_bps": result.average_spread_bps,
                "partial_fill_rate_proxy_pct": result.partial_fill_rate_proxy_pct,
            },
            artifact_refs=[
                artifact_ref(
                    result.report_path, root=base, kind="report", producer="execution_sim"
                ),
                artifact_ref(result.json_path, root=base, kind="json", producer="execution_sim"),
            ],
            blocked_reasons=blockers,
            warning_reasons=warnings,
        ),
        base,
    )
    return result


def _write_execution_sim_outputs(result: ExecutionSimResult) -> None:
    if result.json_path is None or result.report_path is None:
        return
    write_json(
        result.json_path,
        {
            **asdict(result),
            "json_path": str(result.json_path),
            "report_path": str(result.report_path),
            "research_only": True,
            "interpretation": (
                "Execution simulation is a research/readiness artifact. It does not submit "
                "paper orders and does not replace broker TCA."
            ),
        },
    )
    ensure_dir(result.report_path.parent)
    lines = [
        f"# Execution Simulation: {result.strategy_name}",
        "",
        f"- Status: `{result.status}`",
        f"- Selected backend: `{result.selected_backend}`",
        f"- Market data manifest: `{result.market_data_manifest_path or 'missing'}`",
        f"- Market data kind: `{result.market_data_kind or 'missing'}`",
        f"- Rows: `{result.row_count}`",
        f"- Latency ms: `{result.latency_ms:.2f}`",
        f"- Average spread bps: `{_fmt(result.average_spread_bps)}`",
        f"- Partial fill proxy: `{_fmt_pct(result.partial_fill_rate_proxy_pct)}`",
        f"- Blockers: `{', '.join(result.blockers) or 'none'}`",
        f"- Warnings: `{', '.join(result.warnings) or 'none'}`",
    ]
    result.report_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def _average_spread_bps(path: Path, kind: str) -> float | None:
    if kind == "quote_tick":
        spreads: list[float] = []
        for row in _load_jsonl(path):
            bid = float(row["bid_price"])
            ask = float(row["ask_price"])
            mid = (bid + ask) / 2
            if mid > 0:
                spreads.append(((ask - bid) / mid) * 10_000)
        return fmean(spreads) if spreads else None
    if kind == "depth_snapshot":
        spreads = []
        for row in _load_jsonl(path):
            bid = max(float(level["price"]) for level in row["bids"])
            ask = min(float(level["price"]) for level in row["asks"])
            mid = (bid + ask) / 2
            if mid > 0:
                spreads.append(((ask - bid) / mid) * 10_000)
        return fmean(spreads) if spreads else None
    return None


def _partial_fill_rate_proxy(spec, kind: str) -> float | None:
    if spec.reality_model is None:
        return None
    if spec.reality_model.partial_fill_model == "none":
        return 0.0
    if kind in {"depth_snapshot", "order_book_delta"}:
        return 10.0
    if kind == "quote_tick":
        return 20.0
    return None


def _load_jsonl(path: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                raw = json.loads(line)
                if isinstance(raw, dict):
                    rows.append(raw)
    return rows


def _relative_label(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def _fmt(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.4f}"


def _fmt_pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.2f}%"
