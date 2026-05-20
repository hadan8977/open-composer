from __future__ import annotations

import argparse
import json
from pathlib import Path
from time import perf_counter

import pandas as pd

from open_composer.config import project_root
from open_composer.models.strategy_spec import load_strategy_spec
from open_composer.research.hybrid_adaptive_router import (
    _backtest_hybrid_params,
    _build_hybrid_params_grid,
    _daily_frame_from_intraday,
    _DailyHybridDataset,
    _effective_lookback,
    _hybrid_quality_flags,
    _hybrid_score,
)
from open_composer.research.intraday_daily_rotation import _DailyBars, _regular_session_days
from open_composer.research.metadata import combined_data_profile, frame_data_profile
from open_composer.research.rotation import _filter_time_window
from open_composer.storage import write_json

SYMBOLS = [
    "AAPL",
    "MSFT",
    "NVDA",
    "AMZN",
    "META",
    "GOOGL",
    "AVGO",
    "AMD",
    "QCOM",
    "AMAT",
    "NFLX",
    "TSLA",
]
BENCHMARK = "TQQQ"
MARKET = "QQQ"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--mode",
        choices=["intraday-cache", "daily-2022", "performance-seeking", "both"],
        default="both",
    )
    args = parser.parse_args()
    started = perf_counter()
    root = project_root()
    spec_path = root / "strategy_specs" / "drafts" / "nasdaq_hybrid_adaptive_router_1m.yaml"
    spec = load_strategy_spec(spec_path)
    params_grid = _risk_managed_grid()
    if args.mode == "performance-seeking":
        _run_performance_seeking(root=root, spec=spec, started=started)
        return
    if args.mode in {"intraday-cache", "both"}:
        dataset = _load_local_cache_dataset(
            root=root,
            spec_timeframe=str(spec.timeframe),
            symbols=SYMBOLS,
            start="2022-01-01",
            end="2026-05-18",
            use_daily_cache=False,
        )
        payload = _research_payload(
            dataset=dataset,
            spec=spec,
            params_grid=params_grid,
            selection_split_date="2024-10-10",
            windows=[
                ("stress_2024_pre_oct", "2024-05-01", "2024-10-09"),
                ("recent_advantage", "2024-10-10", "2026-05-18"),
                ("full_2024_2026", "2024-05-01", "2026-05-18"),
                ("calendar_2025", "2025-01-01", "2025-12-31"),
                ("ytd_2026", "2026-01-01", "2026-05-18"),
            ],
            walk_forward_boundaries=[
                ("fold_1", "2024-05-01", "2024-10-09", "2024-10-10", "2025-03-31"),
                ("fold_2", "2024-05-01", "2025-03-31", "2025-04-01", "2025-09-30"),
                ("fold_3", "2024-05-01", "2025-09-30", "2025-10-01", "2026-05-18"),
            ],
            started=started,
            mode="hybrid_risk_managed_research",
        )
        json_path = (
            root / "reports" / "research" / "nasdaq_hybrid_adaptive_router_1m-risk-managed.json"
        )
        md_path = json_path.with_suffix(".md")
        write_json(json_path, _jsonable(payload))
        _write_markdown(md_path, json_path, payload)
        print(
            json.dumps(
                {
                    "json": str(json_path),
                    "md": str(md_path),
                    "best": payload["best"]["label"],
                    "pass_status": payload["pass_status"],
                },
                indent=2,
            )
        )

    if args.mode not in {"daily-2022", "both"}:
        return
    daily_dataset = _load_local_cache_dataset(
        root=root,
        spec_timeframe="daily",
        symbols=SYMBOLS,
        start="2022-01-01",
        end="2026-05-18",
        use_daily_cache=True,
    )
    daily_payload = _research_payload(
        dataset=daily_dataset,
        spec=spec,
        params_grid=params_grid,
        selection_split_date="2024-01-01",
        windows=[
            ("calendar_2022", "2022-01-01", "2022-12-31"),
            ("calendar_2023", "2023-01-01", "2023-12-31"),
            ("calendar_2024", "2024-01-01", "2024-12-31"),
            ("calendar_2025", "2025-01-01", "2025-12-31"),
            ("ytd_2026", "2026-01-01", "2026-05-18"),
            ("full_2022_2026", "2022-01-01", "2026-05-18"),
        ],
        walk_forward_boundaries=[
            ("fold_1", "2022-01-01", "2022-12-31", "2023-01-01", "2023-12-31"),
            ("fold_2", "2022-01-01", "2023-12-31", "2024-01-01", "2024-12-31"),
            ("fold_3", "2022-01-01", "2024-12-31", "2025-01-01", "2025-12-31"),
            ("fold_4", "2022-01-01", "2025-12-31", "2026-01-01", "2026-05-18"),
        ],
        started=started,
        mode="hybrid_risk_managed_daily_robustness",
    )
    daily_json = (
        root
        / "reports"
        / "research"
        / "nasdaq_hybrid_adaptive_router_1m-risk-managed-daily-2022.json"
    )
    daily_md = daily_json.with_suffix(".md")
    write_json(daily_json, _jsonable(daily_payload))
    _write_markdown(daily_md, daily_json, daily_payload)
    print(
        json.dumps(
            {
                "json": str(daily_json),
                "md": str(daily_md),
                "best": daily_payload["best"]["label"],
                "pass_status": daily_payload["pass_status"],
            },
            indent=2,
        )
    )


def _risk_managed_grid():
    return _build_hybrid_params_grid(
        holding_modes=["open_to_open"],
        momentum_lookback_days=[20, 40],
        top_n_values=[2, 3],
        market_sma_days=[50, 100],
        min_momentum_pct=[0.0, 5.0],
        max_position_weight=[0.20],
        gross_exposure_limit=[0.60],
        momentum_score_mode=["raw"],
        risk_adjustment_lookback_days=[None],
        market_below_sma_scale=[0.0],
        volatility_lookback_days=[20],
        target_volatility_annual_pct=[18.0, 24.0],
        market_drawdown_lookback_days=[20],
        market_drawdown_brake_pct=[8.0],
        brake_exposure_scale=[0.5],
        max_candidates=64,
    )


def _performance_seeking_grid():
    return _build_hybrid_params_grid(
        holding_modes=["open_to_open"],
        momentum_lookback_days=[60, 120],
        top_n_values=[3, 4, 5],
        market_sma_days=[50],
        min_momentum_pct=[0.0],
        max_position_weight=[0.20, 0.25],
        gross_exposure_limit=[0.60, 0.75],
        momentum_score_mode=["raw", "risk_adjusted"],
        risk_adjustment_lookback_days=[None, 20],
        market_below_sma_scale=[0.5],
        volatility_lookback_days=[20],
        target_volatility_annual_pct=[40.0],
        market_drawdown_lookback_days=[60],
        market_drawdown_brake_pct=[12.0],
        brake_exposure_scale=[0.5],
        max_candidates=16,
    )


def _run_performance_seeking(*, root: Path, spec, started: float) -> None:
    dataset = _load_local_cache_dataset(
        root=root,
        spec_timeframe="daily",
        symbols=SYMBOLS,
        start="2022-01-01",
        end="2026-05-18",
        use_daily_cache=True,
    )
    params_grid = _performance_seeking_grid()
    payload = _research_payload(
        dataset=dataset,
        spec=spec,
        params_grid=params_grid,
        selection_split_date="2024-01-01",
        windows=[
            ("calendar_2022", "2022-01-01", "2022-12-31"),
            ("calendar_2023", "2023-01-01", "2023-12-31"),
            ("calendar_2024", "2024-01-01", "2024-12-31"),
            ("calendar_2025", "2025-01-01", "2025-12-31"),
            ("ytd_2026", "2026-01-01", "2026-05-18"),
            ("recent_2024_2026", "2024-01-01", "2026-05-18"),
            ("full_2022_2026", "2022-01-01", "2026-05-18"),
        ],
        walk_forward_boundaries=[
            ("fold_1", "2022-01-01", "2022-12-31", "2023-01-01", "2023-12-31"),
            ("fold_2", "2022-01-01", "2023-12-31", "2024-01-01", "2024-12-31"),
            ("fold_3", "2022-01-01", "2024-12-31", "2025-01-01", "2025-12-31"),
            ("fold_4", "2022-01-01", "2025-12-31", "2026-01-01", "2026-05-18"),
        ],
        started=started,
        mode="hybrid_performance_seeking_daily_robustness",
    )
    json_path = (
        root
        / "reports"
        / "research"
        / "nasdaq_hybrid_adaptive_router_1m-performance-seeking-daily.json"
    )
    md_path = json_path.with_suffix(".md")
    write_json(json_path, _jsonable(payload))
    _write_markdown(md_path, json_path, payload)
    print(
        json.dumps(
            {
                "json": str(json_path),
                "md": str(md_path),
                "best": payload["best"]["label"],
                "pass_status": payload["pass_status"],
            },
            indent=2,
        )
    )


def _load_local_cache_dataset(
    *,
    root: Path,
    spec_timeframe: str,
    symbols: list[str],
    start: str,
    end: str,
    use_daily_cache: bool,
) -> _DailyHybridDataset:
    all_symbols = list(dict.fromkeys([*symbols, BENCHMARK, MARKET]))
    bars: dict[str, dict[str, _DailyBars]] = {}
    profiles = []
    for symbol in all_symbols:
        path = root / "data" / "cache" / f"{symbol.lower()}_{spec_timeframe}_iex.csv"
        frame = pd.read_csv(path)
        frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
        frame = frame[
            (frame["timestamp"] >= pd.Timestamp(start, tz="UTC"))
            & (frame["timestamp"] <= pd.Timestamp(end, tz="UTC"))
        ]
        profiles.append(
            frame_data_profile(
                frame,
                symbol=symbol,
                timeframe=spec_timeframe,
                provider="alpaca",
                feed="iex",
                source_mode="cache",
                path=str(path),
            )
        )
        bars[symbol] = _daily_cache_days(frame) if use_daily_cache else _regular_session_days(frame)
    common = sorted(set.intersection(*(set(bars[symbol]) for symbol in all_symbols)))
    frame = _daily_frame_from_intraday(bars, common, all_symbols)
    frame = _filter_time_window(frame, start, end)
    return _DailyHybridDataset(
        symbols=symbols,
        benchmark_symbol=BENCHMARK,
        market_symbol=MARKET,
        dates=list(frame["date"].astype(str)),
        frame=frame,
        data_profile=combined_data_profile(profiles),
    )


def _daily_cache_days(frame: pd.DataFrame) -> dict[str, _DailyBars]:
    days: dict[str, _DailyBars] = {}
    data = frame.copy().sort_values("timestamp").reset_index(drop=True)
    for _, row in data.iterrows():
        date = pd.Timestamp(row["timestamp"]).tz_convert("America/New_York").date().isoformat()
        days[date] = _DailyBars(
            timestamps=[row["timestamp"]],
            opens=pd.Series([row["open"]]).to_numpy(dtype=float),
            closes=pd.Series([row["close"]]).to_numpy(dtype=float),
            volumes=pd.Series([row["volume"]]).to_numpy(dtype=float),
        )
    return days


def _research_payload(
    *,
    dataset,
    spec,
    params_grid,
    selection_split_date,
    windows,
    walk_forward_boundaries,
    started,
    mode,
):
    split = _split_by_date(dataset, selection_split_date)
    candidates = []
    for params in params_grid:
        train = _backtest_hybrid_params(
            spec,
            dataset,
            params,
            start_index=_effective_lookback(params),
            end_index=split,
        )
        oos = _backtest_hybrid_params(
            spec,
            dataset,
            params,
            start_index=split,
            end_index=len(dataset.dates),
        )
        full = _backtest_hybrid_params(
            spec,
            dataset,
            params,
            start_index=_effective_lookback(params),
            end_index=len(dataset.dates),
        )
        candidates.append(
            {
                "label": params.label,
                "params": params,
                "score": _research_score(train, mode),
                "train": train,
                "out_of_sample": oos,
                "full": full,
                "quality_flags": _hybrid_quality_flags(train, oos, full),
            }
        )
    candidates.sort(key=lambda row: float(row["score"]), reverse=True)
    best = candidates[0]
    selected_params = best["params"]
    validation = []
    for name, start, end in windows:
        start_index = max(_split_by_date(dataset, start), _effective_lookback(selected_params))
        end_index = _split_by_date(dataset, end, side="right")
        metrics = _backtest_hybrid_params(
            spec,
            dataset,
            selected_params,
            start_index=start_index,
            end_index=end_index,
        )
        validation.append(
            {"name": name, "requested_start": start, "requested_end": end} | metrics.__dict__
        )

    wf_rows = _walk_forward(
        dataset,
        spec,
        [row["params"] for row in candidates[: min(12, len(candidates))]],
        boundaries=walk_forward_boundaries,
    )
    return {
        "mode": mode,
        "selection_policy": f"train_metrics_only_pre_{selection_split_date}",
        "anti_leakage": [
            "candidate scores use train metrics only",
            "OOS/recent/full windows are validation evidence only",
            "signals use prior confirmed closes and next regular-session open fills",
            "volatility and drawdown scales use only prior QQQ closes",
        ],
        "search_space": {
            "candidate_count": len(params_grid),
            "bounded_before_results": True,
            "parameters": _params_grid_ranges(params_grid),
        },
        "acceptance_standard": _acceptance_standard(mode),
        "best": _candidate_payload(best, rank=1),
        "top_candidates": [
            _candidate_payload(row, rank=index) for index, row in enumerate(candidates[:10], 1)
        ],
        "walk_forward": wf_rows,
        "validation_windows": validation,
        "data_profile": dataset.data_profile,
        "runtime_seconds": round(perf_counter() - started, 4),
        "pass_status": _pass_status(validation, wf_rows),
        "research_notes": [
            "This is a risk-managed candidate, not a paper_auto promotion.",
            "LLM/news is not used as an execution factor in this run.",
            "Alpaca IEX cache remains non-SIP evidence.",
        ],
    }


def _split_by_date(dataset: _DailyHybridDataset, date: str, *, side: str = "left") -> int:
    dates = list(dataset.dates)
    if side == "right":
        return next((index for index, value in enumerate(dates) if value > date), len(dates))
    return next((index for index, value in enumerate(dates) if value >= date), len(dates))


def _walk_forward(dataset, spec, params_grid, boundaries=None):
    boundaries = boundaries or [
        ("fold_1", "2024-05-01", "2024-10-09", "2024-10-10", "2025-03-31"),
        ("fold_2", "2024-05-01", "2025-03-31", "2025-04-01", "2025-09-30"),
        ("fold_3", "2024-05-01", "2025-09-30", "2025-10-01", "2026-05-18"),
    ]
    rows = []
    for fold, train_start, train_end, test_start, test_end in boundaries:
        scored = []
        for params in params_grid:
            train = _backtest_hybrid_params(
                spec,
                dataset,
                params,
                start_index=max(_split_by_date(dataset, train_start), _effective_lookback(params)),
                end_index=_split_by_date(dataset, train_end, side="right"),
            )
            scored.append(
                (
                    _research_score(train, "hybrid_performance_seeking_daily_robustness"),
                    params,
                    train,
                )
            )
        scored.sort(key=lambda item: item[0], reverse=True)
        score, params, train = scored[0]
        test = _backtest_hybrid_params(
            spec,
            dataset,
            params,
            start_index=max(_split_by_date(dataset, test_start), _effective_lookback(params)),
            end_index=_split_by_date(dataset, test_end, side="right"),
        )
        rows.append(
            {
                "fold": fold,
                "params": params.__dict__ | {"label": params.label},
                "score": score,
                "train": train.__dict__,
                "test": test.__dict__,
            }
        )
    return rows


def _research_score(metrics, mode: str) -> float:
    if mode != "hybrid_performance_seeking_daily_robustness":
        return _hybrid_score(metrics, "risk_adjusted_benchmark_alpha")
    annualized = metrics.annualized_return_pct or -100.0
    market_alpha = metrics.alpha_vs_market_buy_hold_annualized_pct or -100.0
    equal_weight_alpha = metrics.alpha_vs_equal_weight_buy_hold_annualized_pct or -100.0
    sharpe = metrics.sharpe_ratio or 0.0
    drawdown = abs(min(metrics.max_drawdown_pct, 0.0))
    concentration_penalty = max(0.0, metrics.max_symbol_weight_pct - 25.0) * 4.0
    high_sharpe_penalty = max(0.0, sharpe - 2.5) * 25.0
    sparse_penalty = max(0, 120 - metrics.traded_days) * 0.5
    score = (
        annualized
        + 0.65 * market_alpha
        + 0.35 * equal_weight_alpha
        + 8.0 * sharpe
        - 0.8 * drawdown
        - concentration_penalty
        - high_sharpe_penalty
        - sparse_penalty
    )
    if annualized <= 0:
        score -= 500
    if sharpe < 0.5:
        score -= 100
    if metrics.max_drawdown_pct <= -32:
        score -= 500
    return score


def _candidate_payload(row: dict, rank: int) -> dict:
    params = row["params"]
    return {
        "rank": rank,
        "label": row["label"],
        "params": params.__dict__,
        "score": row["score"],
        "quality_flags": row["quality_flags"],
        "train": row["train"].__dict__,
        "out_of_sample": row["out_of_sample"].__dict__,
        "full": row["full"].__dict__,
    }


def _pass_status(validation: list[dict], walk_forward: list[dict]) -> dict:
    by_name = {row["name"]: row for row in validation}
    recent = by_name.get("recent_advantage") or by_name.get("calendar_2025") or validation[-1]
    stress = by_name.get("stress_2024_pre_oct") or by_name.get("calendar_2022") or validation[0]
    full = by_name.get("full_2024_2026") or by_name.get("full_2022_2026") or validation[-1]
    positive_wf = sum((row["test"]["annualized_return_pct"] or -100) > 0 for row in walk_forward)
    conditions = {
        "recent_positive": (recent["annualized_return_pct"] or -100) > 0,
        "full_annualized_at_least_12_pct": (full["annualized_return_pct"] or -100) >= 12,
        "full_alpha_vs_qqq_positive": (full["alpha_vs_market_buy_hold_annualized_pct"] or -100) > 0,
        "full_alpha_vs_equal_weight_positive": (
            full["alpha_vs_equal_weight_buy_hold_annualized_pct"] or -100
        )
        > 0,
        "stress_drawdown_controlled": stress["max_drawdown_pct"] > -32,
        "full_drawdown_controlled": full["max_drawdown_pct"] > -32,
        "max_symbol_weight_ok": max(row["max_symbol_weight_pct"] for row in validation) <= 25,
        "max_gross_ok": max(row["max_gross_exposure_pct"] for row in validation) <= 100,
        "walk_forward_majority_positive": positive_wf >= max(2, len(walk_forward) // 2 + 1),
    }
    return {
        "workflow_pass": True,
        "research_pass": all(conditions.values()),
        "llm_contribution_pass": False,
        "paper_ready_pass": False,
        "conditions": conditions,
        "walk_forward_positive_tests": positive_wf,
        "walk_forward_tests": len(walk_forward),
    }


def _params_grid_ranges(params_grid) -> dict:
    def sort_optional(values):
        return sorted(values, key=lambda value: -1 if value is None else value)

    return {
        "holding_mode": sorted({item.holding_mode for item in params_grid}),
        "momentum_lookback_days": sorted({item.momentum_lookback_days for item in params_grid}),
        "top_n": sorted({item.top_n for item in params_grid}),
        "market_sma_days": sort_optional({item.market_sma_days for item in params_grid}),
        "min_momentum_pct": sorted({item.min_momentum_pct for item in params_grid}),
        "max_position_weight": sorted({item.max_position_weight for item in params_grid}),
        "gross_exposure_limit": sorted({item.gross_exposure_limit for item in params_grid}),
        "momentum_score_mode": sorted({item.momentum_score_mode for item in params_grid}),
        "risk_adjustment_lookback_days": sort_optional(
            {item.risk_adjustment_lookback_days for item in params_grid}
        ),
        "market_below_sma_scale": sorted({item.market_below_sma_scale for item in params_grid}),
        "volatility_lookback_days": sort_optional(
            {item.volatility_lookback_days for item in params_grid}
        ),
        "target_volatility_annual_pct": sort_optional(
            {item.target_volatility_annual_pct for item in params_grid}
        ),
        "market_drawdown_lookback_days": sort_optional(
            {item.market_drawdown_lookback_days for item in params_grid}
        ),
        "market_drawdown_brake_pct": sort_optional(
            {item.market_drawdown_brake_pct for item in params_grid}
        ),
        "brake_exposure_scale": sorted({item.brake_exposure_scale for item in params_grid}),
    }


def _acceptance_standard(mode: str) -> dict:
    if mode == "hybrid_performance_seeking_daily_robustness":
        return {
            "full_annualized_return_pct": ">= 12",
            "full_alpha_vs_qqq_buy_hold_annualized_pct": "> 0",
            "full_alpha_vs_equal_weight_buy_hold_annualized_pct": "> 0",
            "max_drawdown_pct": "> -32",
            "max_symbol_weight_pct": "<= 25",
            "max_gross_exposure_pct": "<= 100",
            "walk_forward": "majority positive annualized test windows",
            "paper_ready_pass": False,
        }
    return {
        "positive_recent_or_full_return": True,
        "max_drawdown_pct": "> -30",
        "max_symbol_weight_pct": "<= 25",
        "max_gross_exposure_pct": "<= 60",
        "sharpe_review_band": "0.5 to 2.5 preferred; >2.5 flagged as overfit risk",
        "paper_ready_pass": False,
    }


def _jsonable(payload):
    return json.loads(json.dumps(payload, default=str))


def _fmt(value) -> str:
    if value is None:
        return "n/a"
    return f"{float(value):.2f}"


def _write_markdown(path: Path, json_path: Path, payload: dict) -> None:
    best = payload["best"]
    lines = [
        "# Risk-Managed Hybrid Router Research",
        "",
        f"- JSON report: `{json_path}`",
        f"- Selection policy: `{payload['selection_policy']}`",
        f"- Best train-selected route: `{best['label']}`",
        f"- Research pass: `{payload['pass_status']['research_pass']}`",
        f"- Paper ready pass: `{payload['pass_status']['paper_ready_pass']}`",
        "",
        "## Anti-Leakage",
        "",
        *[f"- {item}" for item in payload["anti_leakage"]],
        "",
        "## Validation Windows",
        "",
        "| Window | Actual Dates | Ann. Return | Sharpe | Max DD | Max Gross | "
        "Max Symbol | Alpha vs TQQQ Ann. | Round Trips |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in payload["validation_windows"]:
        lines.append(
            f"| {row['name']} | {row.get('start_date')} -> {row.get('end_date')} | "
            f"{_fmt(row.get('annualized_return_pct'))}% | {_fmt(row.get('sharpe_ratio'))} | "
            f"{_fmt(row.get('max_drawdown_pct'))}% | {_fmt(row.get('max_gross_exposure_pct'))}% | "
            f"{_fmt(row.get('max_symbol_weight_pct'))}% | "
            f"{_fmt(row.get('alpha_vs_benchmark_buy_hold_annualized_pct'))}% | "
            f"{row.get('round_trips')} |"
        )
    lines.extend(
        [
            "",
            "## Walk Forward",
            "",
            "| Fold | Route | Test Ann. Return | Test Sharpe | Test Max DD |",
            "|---|---|---:|---:|---:|",
        ]
    )
    for row in payload["walk_forward"]:
        test = row["test"]
        lines.append(
            f"| {row['fold']} | `{row['params']['label']}` | "
            f"{_fmt(test.get('annualized_return_pct'))}% | {_fmt(test.get('sharpe_ratio'))} | "
            f"{_fmt(test.get('max_drawdown_pct'))}% |"
        )
    lines.extend(
        [
            "",
            "## Conclusion",
            "",
            "- This run is a research pass candidate only if all standards pass.",
            "- LLM/news remains advisory; no independent LLM Alpha is claimed.",
            "- Kill switch should stay enabled until paper readiness is separately reviewed.",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
