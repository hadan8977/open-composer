from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import numpy as np

import scripts.research_return_enhanced_router as base
from open_composer.config import ensure_dir, project_root
from open_composer.models.strategy_spec import load_strategy_spec
from open_composer.storage import write_json

REPORT_STEM = "nasdaq_tqqq_return_enhanced_router_daily-long-window"
START_DATE = "2020-07-27"
END_DATE = "2026-05-22"


def main() -> None:
    root = project_root()
    base.START_DATE = START_DATE
    base.END_DATE = END_DATE
    spec = load_strategy_spec(root / base.SPEC_PATH)
    dates, opens, closes = base._load_arrays(root)
    date_index = {date: index for index, date in enumerate(dates)}
    first_tradable = max(251, date_index["2021-07-27"])
    cost_rate = spec.costs.commission_pct / 100 + spec.costs.slippage_bps / 10_000

    open_to_open_returns = np.zeros_like(opens)
    open_to_open_returns[:-1] = opens[1:] * (1 - cost_rate) / (opens[:-1] * (1 + cost_rate)) - 1
    raw_open_to_open_returns = np.zeros_like(opens)
    raw_open_to_open_returns[:-1] = opens[1:] / opens[:-1] - 1

    params = base.BetaOverrideParams(
        momentum_lookback_days=30,
        min_momentum_pct=10.0,
        override_advantage_pct=-5.0,
        confirmation_sma_days=100,
        exclude_tqqq=True,
    )
    strategy_returns, strategy_weights = base._run_candidate(
        dates=dates,
        closes=closes,
        open_to_open_returns=open_to_open_returns,
        params=params,
    )
    iter2_weights = base._iter2_base_weights(closes)
    iter2_returns = (iter2_weights * open_to_open_returns).sum(axis=1)
    tqqq_returns, tqqq_weights = _buy_hold_returns(
        raw_open_to_open_returns,
        first_tradable,
        "TQQQ",
    )
    qqq_returns, qqq_weights = _buy_hold_returns(
        raw_open_to_open_returns,
        first_tradable,
        "QQQ",
    )

    periods = [
        ("long_window_first_tradable", dates[first_tradable], END_DATE),
        ("pre_2023_stress", dates[first_tradable], "2022-12-30"),
        ("calendar_2022_bear", "2022-01-03", "2022-12-30"),
        ("calendar_2023_rebound", "2023-01-03", "2023-12-29"),
        ("calendar_2024_bull", "2024-01-02", "2024-12-31"),
        ("calendar_2025_choppy", "2025-01-02", "2025-12-31"),
        ("calendar_2026_ytd", "2026-01-02", END_DATE),
        ("current_research_window", "2023-01-03", END_DATE),
        ("current_oos_window", "2024-11-04", END_DATE),
    ]
    period_rows = []
    for label, start_date, end_date in periods:
        start = date_index[start_date]
        end = date_index[end_date]
        period_rows.append(
            {
                "label": label,
                "start_date": start_date,
                "end_date": end_date,
                "strategy": _metrics(dates, strategy_returns, strategy_weights, start, end),
                "local_iter2": _metrics(dates, iter2_returns, iter2_weights, start, end),
                "tqqq_buy_hold": _metrics(dates, tqqq_returns, tqqq_weights, start, end),
                "qqq_buy_hold": _metrics(dates, qqq_returns, qqq_weights, start, end),
            }
        )

    payload = {
        "strategy_name": base.STRATEGY,
        "report_type": "long_window_fixed_route_stress",
        "selected_route_label": params.label,
        "data_profile": {
            "provider": "alpaca",
            "feed": "iex",
            "source_mode": "cache",
            "adjusted": False,
            "first_cache_date": dates[0],
            "first_tradable_date_after_warmup": dates[first_tradable],
            "last_cache_date": dates[-1],
            "caveats": [
                "Fixed selected parameters are stress-tested; no long-window reselection is used.",
                "Local Alpaca IEX cache is not SIP data and is treated as raw/non-adjusted.",
                "Current-symbol universe remains survivorship-biased.",
            ],
        },
        "periods": period_rows,
        "interpretation": _interpret(period_rows),
    }
    reports = ensure_dir(root / "reports" / "research")
    json_path = reports / f"{REPORT_STEM}.json"
    md_path = reports / f"{REPORT_STEM}.md"
    write_json(json_path, payload)
    _write_markdown(md_path, payload)
    print(json.dumps({"json": str(json_path), "markdown": str(md_path)}, indent=2))


def _buy_hold_returns(
    open_to_open_returns: np.ndarray,
    start_index: int,
    symbol: str,
) -> tuple[np.ndarray, np.ndarray]:
    weights = np.zeros_like(open_to_open_returns)
    weights[start_index:, base.UNIVERSE.index(symbol)] = 1.0
    returns = (weights * open_to_open_returns).sum(axis=1)
    return returns, weights


def _metrics(
    dates: list[str],
    returns: np.ndarray,
    weights: np.ndarray,
    start: int,
    end: int,
) -> dict[str, Any]:
    metrics = base._metrics(returns, weights, start, end)
    metrics["start_date"] = dates[start]
    metrics["end_date"] = dates[end]
    metrics["calmar_ratio"] = _calmar(metrics)
    return metrics


def _calmar(metrics: dict[str, Any]) -> float | None:
    max_dd = abs(float(metrics["max_drawdown_pct"]))
    if max_dd <= 0:
        return None
    return float(metrics["annualized_return_pct"]) / max_dd


def _interpret(period_rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_label = {row["label"]: row for row in period_rows}
    bear = by_label["calendar_2022_bear"]["strategy"]
    long_window = by_label["long_window_first_tradable"]["strategy"]
    current = by_label["current_research_window"]["strategy"]
    return {
        "logic_runs_through_long_window": True,
        "pre_2023_degradation": bear["total_return_pct"] < 0,
        "current_window_materially_stronger_than_2022": (
            current["annualized_return_pct"] > long_window["annualized_return_pct"]
            and bear["total_return_pct"] < 0
        ),
        "summary": (
            "The fixed route runs on the longer cache, but 2022 is a clear stress "
            "period. The edge is concentrated in the post-2023 high-beta momentum "
            "environment, so the current logic should be treated as regime-sensitive."
        ),
    }


def _write_markdown(path: Path, payload: dict[str, Any]) -> None:
    lines = [
        "# Long Window Stress: Return-Enhanced Router",
        "",
        f"- Strategy: `{payload['strategy_name']}`",
        f"- Route: `{payload['selected_route_label']}`",
        f"- First cache date: `{payload['data_profile']['first_cache_date']}`",
        f"- First tradable after warmup: "
        f"`{payload['data_profile']['first_tradable_date_after_warmup']}`",
        f"- Last cache date: `{payload['data_profile']['last_cache_date']}`",
        "",
        "## Period Results",
        "",
        "| Period | Strategy Total | Strategy Ann. | Strategy Sharpe | Strategy DD | "
        "Iter2 Total | TQQQ B&H | QQQ B&H |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in payload["periods"]:
        strategy = row["strategy"]
        lines.append(
            f"| {row['label']} | {_fmt(strategy['total_return_pct'])}% | "
            f"{_fmt(strategy['annualized_return_pct'])}% | "
            f"{_fmt(strategy['sharpe_ratio'])} | "
            f"{_fmt(strategy['max_drawdown_pct'])}% | "
            f"{_fmt(row['local_iter2']['total_return_pct'])}% | "
            f"{_fmt(row['tqqq_buy_hold']['total_return_pct'])}% | "
            f"{_fmt(row['qqq_buy_hold']['total_return_pct'])}% |"
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            f"- {payload['interpretation']['summary']}",
            "",
            "## Caveats",
            "",
            *[f"- {item}" for item in payload["data_profile"]["caveats"]],
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _fmt(value: Any) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        if math.isnan(value):
            return "n/a"
        return f"{value:.2f}"
    return str(value)


if __name__ == "__main__":
    main()
