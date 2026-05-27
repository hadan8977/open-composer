from __future__ import annotations

import importlib.util
import json
import sys
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Any

from open_composer.config import ensure_dir, project_root
from open_composer.storage import append_jsonl, write_json

ITER5_SCRIPT = Path("scripts/research_return_enhanced_longbridge_history.py")
STRATEGY = "nasdaq_tqqq_return_enhanced_router_daily_iter6"
REPORT_STEM = f"{STRATEGY}-regime-defense"
SPEC_PATH = Path("strategy_specs/drafts/nasdaq_tqqq_return_enhanced_router_daily_iter6.yaml")
SELECTED_ROUTE_LABEL = (
    "beta_override:baseiter2_lb20_min20_adv0_sma50_exTQQQ_"
    "gateq200ormom120_mdd504p25_g0.87_tqqq_cycle"
)


def main() -> None:
    started = perf_counter()
    base = project_root()
    iter5 = _load_iter5_module(base)
    spec = iter5.load_strategy_spec(base / SPEC_PATH)
    dates, opens, closes, availability = iter5._load_history_arrays(base, iter5.UNIVERSE)
    date_index = {date: index for index, date in enumerate(dates)}
    cost_rate = spec.costs.commission_pct / 100 + spec.costs.slippage_bps / 10_000
    open_to_open = iter5._open_to_open_returns(opens, cost_rate=cost_rate)
    raw_open_to_open = iter5._open_to_open_returns(opens, cost_rate=0.0)
    first_tradable = max(251, date_index.get("2011-02-11", 251))
    end_index = date_index[iter5.END_DATE]
    grid = _iter6_grid(iter5)
    cache = iter5._build_indicator_cache(closes, grid)
    iter2_weights = iter5._iter2_base_weights(closes, cache)
    iter2_returns = iter5._portfolio_returns(iter2_weights, open_to_open)
    baseline = iter5._metrics(dates, iter2_returns, iter2_weights, first_tradable, end_index)
    tqqq = iter5._return_metrics(
        dates,
        raw_open_to_open[:, iter5.UNIVERSE.index(iter5.BENCHMARK_SYMBOL)],
        first_tradable,
        end_index,
    )
    candidate_rows = _evaluate_grid(
        iter5=iter5,
        dates=dates,
        closes=closes,
        open_to_open=open_to_open,
        grid=grid,
        base_weights=iter2_weights,
        cache=cache,
        baseline=baseline,
        tqqq=tqqq,
        first_tradable=first_tradable,
        end_index=end_index,
    )
    selected = next(row for row in candidate_rows if row["params"].label == SELECTED_ROUTE_LABEL)
    passing = [row for row in candidate_rows if _full_standard_pass(row)]
    passing.sort(key=lambda row: row["full_window"]["total_return_pct"], reverse=True)
    walk_forward = iter5._anchored_yearly_walk_forward(
        dates=dates,
        candidate_rows=candidate_rows,
        baseline_returns=iter2_returns,
        first_tradable=first_tradable,
    )
    pass_status = _pass_status(selected, passing, walk_forward)
    reports = ensure_dir(base / "reports" / "research")
    control = ensure_dir(reports / "control")
    payload = {
        "strategy_name": STRATEGY,
        "report_type": "iter6_regime_defense_research",
        "generated_at": datetime.now(UTC).isoformat(),
        "spec_path": str(SPEC_PATH),
        "selected_route_label": SELECTED_ROUTE_LABEL,
        "selected_candidate": _candidate_payload(iter5, selected, selected=True),
        "best_passing_candidate": _candidate_payload(iter5, passing[0]) if passing else None,
        "pass_status": pass_status,
        "acceptance_standard": {
            "return_gate": (
                "full-window total return must beat reconstructed iter2 and TQQQ buy-hold"
            ),
            "risk_gate": "full-window max drawdown must be better than -65%",
            "sharpe_gate": "full-window Sharpe must be >= 0.85",
            "calendar_gate": "negative calendar years must be <= 4",
            "concentration_gate": "max symbol exposure share must be <= 60%",
            "walk_forward_gate": "anchored yearly positive folds must be >= 60%",
        },
        "data_profile": {
            "provider": "longbridge",
            "feed": "nasdaq_basic",
            "adjusted": True,
            "requested_start": iter5.START_DATE,
            "requested_end": iter5.END_DATE,
            "availability": availability,
            "caveats": [
                "Longbridge Nasdaq Basic is not consolidated SIP data.",
                (
                    "Expanded stock universe is current-symbol biased until PIT membership "
                    "evidence exists."
                ),
                "This research pass is not paper readiness by itself.",
            ],
        },
        "cost_model": {
            "commission_pct": spec.costs.commission_pct,
            "slippage_bps": spec.costs.slippage_bps,
            "fill_assumption": spec.execution.fill_assumption,
        },
        "baseline": {
            "reconstructed_iter2": baseline,
            "tqqq_buy_hold": tqqq,
        },
        "search_space": _search_space(grid),
        "top_candidates": [
            _candidate_payload(iter5, row, selected=row["params"].label == SELECTED_ROUTE_LABEL)
            for row in sorted(
                candidate_rows,
                key=lambda row: (_full_standard_pass(row), row["full_window"]["total_return_pct"]),
                reverse=True,
            )[:20]
        ],
        "walk_forward": walk_forward,
        "anti_leakage": [
            "Signals at index t use confirmed closes through index t-1 only.",
            "Trades are evaluated from the next regular-session open.",
            "The 504-day QQQ drawdown filter uses only prior closes.",
            "Anchored yearly walk-forward selects parameters from prior dates only.",
        ],
        "runtime_seconds": round(perf_counter() - started, 4),
    }
    json_path = reports / f"{REPORT_STEM}.json"
    md_path = reports / f"{REPORT_STEM}.md"
    write_json(json_path, payload)
    write_json(
        reports / f"{STRATEGY}-candidate-set.json",
        {
            "strategy_name": STRATEGY,
            "selected_route_label": SELECTED_ROUTE_LABEL,
            "candidate_count": len(candidate_rows),
            "passing_candidate_count": len(passing),
            "candidates": [
                _candidate_payload(
                    iter5,
                    row,
                    selected=row["params"].label == SELECTED_ROUTE_LABEL,
                    compact=True,
                )
                for row in sorted(
                    candidate_rows,
                    key=lambda row: (
                        _full_standard_pass(row),
                        row["full_window"]["total_return_pct"],
                    ),
                    reverse=True,
                )
            ],
        },
    )
    write_json(reports / f"{STRATEGY}-search-space.json", _search_space(grid))
    write_json(reports / f"{STRATEGY}-walk-forward.json", walk_forward)
    write_json(reports / f"{STRATEGY}-evidence-manifest.json", _evidence_manifest(payload))
    trial_path = reports / f"{STRATEGY}-trial-ledger.jsonl"
    if trial_path.exists():
        trial_path.unlink()
    append_jsonl(
        trial_path,
        [
            _candidate_payload(
                iter5,
                row,
                selected=row["params"].label == SELECTED_ROUTE_LABEL,
                compact=True,
            )
            for row in candidate_rows
        ],
    )
    write_json(
        control / f"{STRATEGY}-state.json",
        {
            "strategy_name": STRATEGY,
            "selected_route_label": SELECTED_ROUTE_LABEL,
            "workflow_pass": pass_status["workflow_pass"],
            "research_pass": pass_status["research_pass"],
            "paper_ready_pass": pass_status["paper_ready_pass"],
            "updated_at": payload["generated_at"],
            "latest_report": str(json_path),
            "blockers": pass_status["paper_ready_blockers"],
        },
    )
    (control / f"{STRATEGY}-memory.md").write_text(_memory(payload), encoding="utf-8")
    _write_markdown(md_path, payload)
    print(
        json.dumps(
            {
                "json": str(json_path),
                "markdown": str(md_path),
                "selected_route_label": SELECTED_ROUTE_LABEL,
                "workflow_pass": pass_status["workflow_pass"],
                "research_pass": pass_status["research_pass"],
                "paper_ready_pass": pass_status["paper_ready_pass"],
                "selected_total_return_pct": selected["full_window"]["total_return_pct"],
                "selected_sharpe": selected["full_window"]["sharpe_ratio"],
                "selected_max_drawdown_pct": selected["full_window"]["max_drawdown_pct"],
                "walk_forward_positive_rate": pass_status["walk_forward_positive_rate"],
            },
            indent=2,
        )
    )


def _load_iter5_module(root: Path) -> Any:
    module_path = root / ITER5_SCRIPT
    spec = importlib.util.spec_from_file_location("iter5_longbridge_research", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {module_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules["iter5_longbridge_research"] = module
    spec.loader.exec_module(module)
    return module


def _iter6_grid(iter5: Any) -> list[Any]:
    rows = []
    for advantage in [0.0, -5.0, -20.0]:
        for sma in [50, 100]:
            for scale in [1.0, 0.95, 0.9, 0.87, 0.85]:
                for max_drawdown in [None, 20.0, 25.0, 35.0]:
                    rows.append(
                        iter5.BetaOverrideParams(
                            momentum_lookback_days=20,
                            min_momentum_pct=20.0,
                            override_advantage_pct=advantage,
                            confirmation_sma_days=sma,
                            exclude_tqqq=True,
                            cycle_gate="q200ormom120",
                            market_drawdown_lookback_days=504 if max_drawdown is not None else None,
                            max_market_drawdown_pct=max_drawdown,
                            gross_exposure_scale=scale,
                            base_mode="tqqq_cycle",
                        )
                    )
    dedup = []
    seen = set()
    for row in rows:
        if row.label not in seen:
            dedup.append(row)
            seen.add(row.label)
    return dedup


def _evaluate_grid(
    *,
    iter5: Any,
    dates: list[str],
    closes: Any,
    open_to_open: Any,
    grid: list[Any],
    base_weights: Any,
    cache: Any,
    baseline: dict[str, Any],
    tqqq: dict[str, Any],
    first_tradable: int,
    end_index: int,
) -> list[dict[str, Any]]:
    rows = []
    for index, params in enumerate(grid, start=1):
        returns, weights = iter5._run_beta_override(
            closes=closes,
            open_to_open_returns=open_to_open,
            params=params,
            base_weights=base_weights,
            cache=cache,
        )
        full = iter5._metrics(dates, returns, weights, first_tradable, end_index)
        full["beats_iter2_total_return"] = full["total_return_pct"] > baseline["total_return_pct"]
        full["return_delta_vs_iter2_pct"] = full["total_return_pct"] - baseline["total_return_pct"]
        full["beats_tqqq_buy_hold_total_return"] = (
            full["total_return_pct"] > tqqq["total_return_pct"]
        )
        full["return_delta_vs_tqqq_buy_hold_pct"] = (
            full["total_return_pct"] - tqqq["total_return_pct"]
        )
        annual = iter5._calendar_metrics(dates, returns, weights, first_tradable, end_index)
        rows.append(
            {
                "trial_id": f"iter6_{index:04d}",
                "params": params,
                "full_window": full,
                "annual": annual,
                "score": iter5._score_candidate(full, annual, baseline),
                "returns": returns,
                "weights": weights,
            }
        )
    rows.sort(key=lambda row: row["score"], reverse=True)
    return rows


def _full_standard_pass(row: dict[str, Any]) -> bool:
    full = row["full_window"]
    negative_years = [item for item in row["annual"] if item["metrics"]["total_return_pct"] < 0]
    return bool(
        full["beats_iter2_total_return"]
        and full["beats_tqqq_buy_hold_total_return"]
        and full["max_drawdown_pct"] > -65
        and full["sharpe_ratio"] is not None
        and full["sharpe_ratio"] >= 0.85
        and len(negative_years) <= 4
        and full["max_symbol_exposure_share_pct"] <= 60
    )


def _pass_status(
    selected: dict[str, Any],
    passing: list[dict[str, Any]],
    walk_forward: dict[str, Any],
) -> dict[str, Any]:
    wf_rate = (
        walk_forward["positive_folds"] / walk_forward["fold_count"]
        if walk_forward["fold_count"]
        else 0.0
    )
    selected_negative_years = [
        row["year"] for row in selected["annual"] if row["metrics"]["total_return_pct"] < 0
    ]
    research_pass = _full_standard_pass(selected) and wf_rate >= 0.6
    return {
        "workflow_pass": True,
        "research_pass": research_pass,
        "llm_contribution_pass": False,
        "paper_ready_pass": False,
        "selected_negative_calendar_years": selected_negative_years,
        "passing_candidate_count": len(passing),
        "walk_forward_positive_rate": wf_rate,
        "walk_forward_positive_folds": walk_forward["positive_folds"],
        "walk_forward_fold_count": walk_forward["fold_count"],
        "paper_ready_blockers": [
            (
                "Backtest forensics, execution reality, promotion, and readiness gates must be "
                "refreshed for iter6."
            ),
            (
                "The expanded stock universe is current-symbol biased until PIT membership "
                "evidence is added."
            ),
            "No LLM/news/macro signal is enabled, so llm_contribution_pass remains false.",
            (
                "paper_auto activation requires active lifecycle, Alpaca Paper broker config, "
                "and explicit user confirmation."
            ),
        ],
    }


def _candidate_payload(
    iter5: Any,
    row: dict[str, Any],
    *,
    selected: bool = False,
    compact: bool = False,
) -> dict[str, Any]:
    payload = {
        "trial_id": row["trial_id"],
        "params": asdict(row["params"]) | {"label": row["params"].label},
        "score": row["score"],
        "full_window": row["full_window"],
        "negative_calendar_years": [
            item["year"] for item in row["annual"] if item["metrics"]["total_return_pct"] < 0
        ],
        "full_standard_pass": _full_standard_pass(row),
        "selected": selected,
    }
    if not compact:
        payload["annual"] = row["annual"]
    return payload


def _search_space(grid: list[Any]) -> dict[str, Any]:
    values: dict[str, set[Any]] = {}
    for params in grid:
        for key, value in asdict(params).items():
            try:
                values.setdefault(key, set()).add(value)
            except TypeError:
                continue
    return {
        "candidate_count": len(grid),
        "families": ["tqqq_cycle_high_beta_override_with_504d_market_drawdown_filter"],
        "parameters": {
            key: sorted(items, key=lambda value: (-1, "") if value is None else (0, str(value)))
            for key, items in values.items()
        },
        "selection_note": (
            "Iter6 only changes regime defense around iter5's near-miss route: "
            "504-session QQQ drawdown filter and 0.85-1.0 gross exposure scaling."
        ),
    }


def _evidence_manifest(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "strategy_name": STRATEGY,
        "selected_route_label": payload["selected_route_label"],
        "workflow_pass": payload["pass_status"]["workflow_pass"],
        "research_pass": payload["pass_status"]["research_pass"],
        "paper_ready_pass": payload["pass_status"]["paper_ready_pass"],
        "required_before_paper_ready": [
            "harness plan",
            "capability evaluation",
            "source cards",
            "backtest forensics",
            "execution reality",
            "target-weight mapping",
            "harness verify",
            "promotion report",
            "paper readiness",
            "paper safety review",
        ],
        "known_limitations": payload["data_profile"]["caveats"],
    }


def _memory(payload: dict[str, Any]) -> str:
    selected = payload["selected_candidate"]
    full = selected["full_window"]
    blockers = "\n".join(f"- {item}" for item in payload["pass_status"]["paper_ready_blockers"])
    return (
        "# iter6 research memory\n\n"
        f"- Selected route: `{payload['selected_route_label']}`.\n"
        f"- Research pass: `{payload['pass_status']['research_pass']}`; "
        "paper_ready_pass: `False`.\n"
        f"- Full-window total return `{full['total_return_pct']:.2f}%`, "
        f"Sharpe `{full['sharpe_ratio']:.3f}`, max drawdown "
        f"`{full['max_drawdown_pct']:.2f}%`.\n"
        f"- Walk-forward positive rate "
        f"`{payload['pass_status']['walk_forward_positive_rate']:.2%}`.\n"
        "- Do not rerun broad universe expansion before PIT membership controls; next work should "
        "either complete paper gates for this selected route or solve PIT universe bias.\n\n"
        "## Paper blockers\n\n"
        f"{blockers}\n"
    )


def _write_markdown(path: Path, payload: dict[str, Any]) -> None:
    selected = payload["selected_candidate"]
    full = selected["full_window"]
    lines = [
        "# Iter6 Regime Defense Research",
        "",
        f"- Strategy: `{payload['strategy_name']}`",
        f"- Selected route: `{payload['selected_route_label']}`",
        f"- Workflow pass: `{payload['pass_status']['workflow_pass']}`",
        f"- Research pass: `{payload['pass_status']['research_pass']}`",
        f"- Paper ready pass: `{payload['pass_status']['paper_ready_pass']}`",
        "",
        "## Selected Candidate",
        "",
        f"- Total return: `{full['total_return_pct']:.2f}%`",
        f"- Annualized return: `{full['annualized_return_pct']:.2f}%`",
        f"- Sharpe: `{full['sharpe_ratio']:.3f}`",
        f"- Max drawdown: `{full['max_drawdown_pct']:.2f}%`",
        f"- Negative years: `{selected['negative_calendar_years']}`",
        f"- Delta vs TQQQ buy-hold: `{full['return_delta_vs_tqqq_buy_hold_pct']:.2f}%`",
        "",
        "## Walk Forward",
        "",
        f"- Positive folds: `{payload['walk_forward']['positive_folds']}` / "
        f"`{payload['walk_forward']['fold_count']}`",
        f"- Beats baseline folds: `{payload['walk_forward']['beats_baseline_folds']}` / "
        f"`{payload['walk_forward']['fold_count']}`",
        "",
        "## Paper Blockers",
        "",
        *[f"- {item}" for item in payload["pass_status"]["paper_ready_blockers"]],
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
