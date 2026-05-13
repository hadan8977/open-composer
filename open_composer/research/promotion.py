from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field
from pathlib import Path
from statistics import mean
from typing import Literal

from open_composer.adapters.data import load_ohlcv_for_spec
from open_composer.config import ensure_dir, project_root
from open_composer.engines.backtest_engine import BacktestArtifacts, backtest_frame
from open_composer.models.strategy_spec import StrategySpec, load_strategy_spec
from open_composer.storage import write_json

PromotionStatus = Literal["ok", "warning", "blocked"]


@dataclass(frozen=True)
class PromotionCheck:
    name: str
    status: PromotionStatus
    message: str
    details: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class PromotionReport:
    strategy_name: str
    source_spec_path: str
    status: PromotionStatus
    ready: bool
    checks: list[PromotionCheck]
    report_path: str
    json_path: str


def build_promotion_report(
    spec_path: Path,
    root: Path | None = None,
    out_of_sample_ratio: float = 0.3,
    walk_forward_folds: int = 3,
    cost_slippage_bps: list[int] | None = None,
) -> PromotionReport:
    base = root or project_root()
    spec = load_strategy_spec(spec_path)
    frame = load_ohlcv_for_spec(spec, base)
    if len(frame) < 4:
        msg = "promotion gate requires at least 4 bars of data"
        raise ValueError(msg)

    cost_slippage_bps = cost_slippage_bps or [0, 5, 10]
    checks: list[PromotionCheck] = []

    full = backtest_frame(
        spec,
        frame,
        root=base,
        run_id_value=f"promotion-{spec.name}-full",
    )
    checks.append(
        PromotionCheck(
            name="in_sample",
            status=_status_from_sanity(
                full.run.data_sanity.status if full.run.data_sanity else "warning"
            ),
            message=(
                "Full-window backtest captured in-sample research evidence; "
                "review data sanity before promotion."
            ),
            details=_run_details(full),
        )
    )

    oos_check, oos_artifacts = _out_of_sample_check(
        spec=spec,
        frame=frame,
        root=base,
        out_of_sample_ratio=out_of_sample_ratio,
    )
    checks.append(oos_check)

    wf_check, walk_forward_runs = _walk_forward_check(
        spec=spec,
        frame=frame,
        root=base,
        folds=walk_forward_folds,
    )
    checks.append(wf_check)

    cost_check, cost_runs = _cost_sensitivity_check(
        spec=spec,
        frame=frame,
        root=base,
        slippage_bps=cost_slippage_bps,
    )
    checks.append(cost_check)

    comparison_check, comparison_rows = _data_comparison_check(spec, base)
    checks.append(comparison_check)

    ready = all(check.status == "ok" for check in checks)
    status = "ok" if ready else "warning"
    report_path = base / "reports" / "research" / f"{spec.name}-promotion.md"
    json_path = base / "reports" / "research" / f"{spec.name}-promotion.json"
    _write_promotion_json(
        json_path,
        spec_path,
        spec,
        status,
        ready,
        checks,
        full,
        oos_artifacts,
        walk_forward_runs,
        cost_runs,
        comparison_rows,
    )
    _write_promotion_report(
        report_path,
        spec_path,
        spec,
        status,
        ready,
        checks,
        full,
        oos_artifacts,
        walk_forward_runs,
        cost_runs,
        comparison_rows,
        json_path,
    )
    return PromotionReport(
        strategy_name=spec.name,
        source_spec_path=str(spec_path),
        status=status,
        ready=ready,
        checks=checks,
        report_path=str(report_path),
        json_path=str(json_path),
    )


def _out_of_sample_check(
    *,
    spec: StrategySpec,
    frame,
    root: Path,
    out_of_sample_ratio: float,
) -> tuple[PromotionCheck, BacktestArtifacts | None]:
    split = max(int(len(frame) * (1 - out_of_sample_ratio)), 2)
    split = min(split, len(frame) - 1)
    oos_frame = frame.iloc[split:].copy()
    if len(oos_frame) < 2:
        return (
            PromotionCheck(
                name="out_of_sample",
                status="blocked",
                message="Not enough data left for an out-of-sample slice.",
                details={"rows": len(oos_frame)},
            ),
            None,
        )
    artifacts = backtest_frame(
        spec,
        oos_frame,
        root=root,
        run_id_value=f"promotion-{spec.name}-oos",
    )
    status = _status_from_sanity(
        artifacts.run.data_sanity.status if artifacts.run.data_sanity else "warning"
    )
    return (
        PromotionCheck(
            name="out_of_sample",
            status=status,
            message=(
                "Trailing slice evaluated as out-of-sample promotion evidence; "
                "compare with in-sample before using paper."
            ),
            details=_run_details(artifacts),
        ),
        artifacts,
    )


def _walk_forward_check(
    *,
    spec: StrategySpec,
    frame,
    root: Path,
    folds: int,
) -> tuple[PromotionCheck, list[BacktestArtifacts]]:
    folds = max(folds, 1)
    fold_size = max(len(frame) // (folds + 1), 2)
    runs: list[BacktestArtifacts] = []
    fold_details: list[dict[str, object]] = []
    for index in range(folds):
        start = (index + 1) * fold_size
        end = min(len(frame), start + fold_size)
        wf_frame = frame.iloc[start:end].copy()
        if len(wf_frame) < 2:
            continue
        artifacts = backtest_frame(
            spec,
            wf_frame,
            root=root,
            run_id_value=f"promotion-{spec.name}-wf-{index + 1}",
        )
        runs.append(artifacts)
        fold_details.append(
            {
                "fold": index + 1,
                "rows": len(wf_frame),
                "total_return_pct": artifacts.run.total_return_pct,
                "annualized_return_pct": artifacts.run.annualized_return_pct,
                "sharpe_ratio": artifacts.run.sharpe_ratio,
                "status": artifacts.run.data_sanity.status
                if artifacts.run.data_sanity
                else "warning",
            }
        )
    if not runs:
        return (
            PromotionCheck(
                name="walk_forward",
                status="blocked",
                message="No walk-forward folds could be built from the available data.",
                details={"folds": folds},
            ),
            runs,
        )
    status = "ok" if all(item["status"] == "ok" for item in fold_details) else "warning"
    return (
        PromotionCheck(
            name="walk_forward",
            status=status,
            message="Sequential slices evaluated as walk-forward evidence.",
            details={
                "fold_count": len(runs),
                "folds": fold_details,
                "mean_return_pct": mean(item["total_return_pct"] for item in fold_details),
                "mean_sharpe": mean(float(item["sharpe_ratio"] or 0.0) for item in fold_details),
            },
        ),
        runs,
    )


def _cost_sensitivity_check(
    *,
    spec: StrategySpec,
    frame,
    root: Path,
    slippage_bps: list[int],
) -> tuple[PromotionCheck, list[BacktestArtifacts]]:
    runs: list[BacktestArtifacts] = []
    details: list[dict[str, object]] = []
    for bps in slippage_bps:
        candidate = _clone_spec_with_costs(spec, slippage_bps=bps)
        artifacts = backtest_frame(
            candidate,
            frame,
            root=root,
            run_id_value=f"promotion-{spec.name}-cost-{bps}",
        )
        runs.append(artifacts)
        details.append(
            {
                "slippage_bps": bps,
                "total_return_pct": artifacts.run.total_return_pct,
                "annualized_return_pct": artifacts.run.annualized_return_pct,
                "sharpe_ratio": artifacts.run.sharpe_ratio,
                "status": artifacts.run.data_sanity.status
                if artifacts.run.data_sanity
                else "warning",
            }
        )
    status = "ok" if all(item["status"] == "ok" for item in details) else "warning"
    return (
        PromotionCheck(
            name="cost_sensitivity",
            status=status,
            message="Backtests rerun under multiple slippage assumptions.",
            details={
                "scenarios": details,
            },
        ),
        runs,
    )


def _data_comparison_check(
    spec: StrategySpec,
    root: Path,
) -> tuple[PromotionCheck, list[dict[str, object]]]:
    comparisons_root = root / "reports" / "data" / "comparisons"
    rows: list[dict[str, object]] = []
    if not comparisons_root.exists():
        return (
            PromotionCheck(
                name="data_comparison",
                status="warning",
                message="No data comparison reports are available yet.",
                details={},
            ),
            rows,
        )
    for path in sorted(comparisons_root.glob("*.json")):
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if not isinstance(raw, dict):
            continue
        if raw.get("symbol", "").upper() != spec.primary_symbol.upper():
            continue
        if raw.get("timeframe") != spec.timeframe:
            continue
        rows.append(
            {
                "path": str(path),
                "left_source": raw.get("left_source"),
                "right_source": raw.get("right_source"),
                "coverage_pct": raw.get("matched_coverage_pct"),
                "max_close_diff_bps": raw.get("max_abs_close_diff_bps"),
                "missing_left_rows": raw.get("missing_left_rows"),
                "missing_right_rows": raw.get("missing_right_rows"),
            }
        )
    if not rows:
        return (
            PromotionCheck(
                name="data_comparison",
                status="warning",
                message="No matching data comparison report found for this strategy.",
                details={},
            ),
            rows,
        )
    return (
        PromotionCheck(
            name="data_comparison",
            status="ok",
            message="Matching data comparison reports are available.",
            details={"comparisons": rows},
        ),
        rows,
    )


def _clone_spec_with_costs(spec: StrategySpec, *, slippage_bps: int) -> StrategySpec:
    raw = copy.deepcopy(spec.model_dump(mode="json"))
    raw["costs"] = {**raw["costs"], "slippage_bps": slippage_bps}
    return StrategySpec.model_validate(raw)


def _run_details(artifacts: BacktestArtifacts) -> dict[str, object]:
    run = artifacts.run
    return {
        "run_id": run.run_id,
        "bars": run.bars,
        "signals": run.signals,
        "trades": run.trades,
        "total_return_pct": run.total_return_pct,
        "annualized_return_pct": run.annualized_return_pct,
        "sharpe_ratio": run.sharpe_ratio,
        "data_sanity_status": run.data_sanity.status if run.data_sanity else "warning",
        "evidence_level": run.data_sanity.evidence_level if run.data_sanity else "unknown",
    }


def _status_from_sanity(status: str) -> PromotionStatus:
    return "ok" if status == "ok" else "warning"


def _write_promotion_json(
    path: Path,
    spec_path: Path,
    spec: StrategySpec,
    status: PromotionStatus,
    ready: bool,
    checks: list[PromotionCheck],
    full: BacktestArtifacts,
    oos: BacktestArtifacts | None,
    walk_forward_runs: list[BacktestArtifacts],
    cost_runs: list[BacktestArtifacts],
    comparison_rows: list[dict[str, object]],
) -> Path:
    ensure_dir(path.parent)
    payload = {
        "strategy_name": spec.name,
        "source_spec_path": str(spec_path),
        "status": status,
        "ready": ready,
        "checks": [
            {
                "name": check.name,
                "status": check.status,
                "message": check.message,
                "details": check.details,
            }
            for check in checks
        ],
        "full_window": _run_details(full),
        "out_of_sample": _run_details(oos) if oos else None,
        "walk_forward": [_run_details(item) for item in walk_forward_runs],
        "cost_sensitivity": [_run_details(item) for item in cost_runs],
        "data_comparisons": comparison_rows,
    }
    write_json(path, payload)
    return path


def _write_promotion_report(
    path: Path,
    spec_path: Path,
    spec: StrategySpec,
    status: PromotionStatus,
    ready: bool,
    checks: list[PromotionCheck],
    full: BacktestArtifacts,
    oos: BacktestArtifacts | None,
    walk_forward_runs: list[BacktestArtifacts],
    cost_runs: list[BacktestArtifacts],
    comparison_rows: list[dict[str, object]],
    json_path: Path,
) -> Path:
    ensure_dir(path.parent)
    lines = [
        f"# Promotion Report: {spec.name}",
        "",
        f"- Status: `{status}`",
        f"- Ready for paper: `{'yes' if ready else 'no'}`",
        f"- Source spec: `{spec_path}`",
        f"- JSON report: `{json_path}`",
        "",
        "## Checks",
        "",
    ]
    for check in checks:
        lines.extend(
            [
                f"### {check.name}",
                f"- Status: `{check.status}`",
                f"- Message: {check.message}",
            ]
        )
        if check.details:
            lines.append(f"- Details: `{json.dumps(check.details, sort_keys=True)}`")
        lines.append("")
    lines.extend(
        [
            "## Full Window",
            "",
            *_run_lines(full),
            "",
            "## Out Of Sample",
            "",
            *(_run_lines(oos) if oos is not None else ["- No out-of-sample slice was available."]),
            "",
            "## Walk Forward",
            "",
        ]
    )
    if walk_forward_runs:
        for item in walk_forward_runs:
            lines.extend(_run_lines(item))
            lines.append("")
    else:
        lines.append("- No walk-forward runs were produced.")
    lines.extend(["## Cost Sensitivity", ""])
    if cost_runs:
        for item in cost_runs:
            lines.extend(_run_lines(item))
            lines.append("")
    else:
        lines.append("- No cost sensitivity runs were produced.")
        lines.append("")
    lines.extend(["## Data Comparisons", ""])
    if comparison_rows:
        for row in comparison_rows:
            lines.append(
                f"- `{row.get('left_source')}` vs `{row.get('right_source')}` "
                f"coverage `{row.get('coverage_pct')}` max_close_diff_bps "
                f"`{row.get('max_close_diff_bps')}`"
            )
    else:
        lines.append("- No matching data comparison reports were found.")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _run_lines(artifacts: BacktestArtifacts | None) -> list[str]:
    if artifacts is None:
        return ["- No run."]
    run = artifacts.run
    return [
        f"- Run: `{run.run_id}`",
        f"- Return: `{run.total_return_pct:.2f}%`",
        f"- Annualized: `{run.annualized_return_pct:.2f}%`"
        if run.annualized_return_pct is not None
        else "- Annualized: `n/a`",
        f"- Sharpe: `{run.sharpe_ratio:.2f}`"
        if run.sharpe_ratio is not None
        else "- Sharpe: `n/a`",
        f"- Signals: `{run.signals}`",
        f"- Trades: `{run.trades}`",
        f"- Data sanity: `{run.data_sanity.status if run.data_sanity else 'warning'}`",
        f"- Evidence level: `{run.data_sanity.evidence_level if run.data_sanity else 'unknown'}`",
    ]
