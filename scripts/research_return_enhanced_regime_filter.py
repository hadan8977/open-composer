from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np

import scripts.research_return_enhanced_router as base
from open_composer.config import ensure_dir, project_root
from open_composer.models.strategy_spec import load_strategy_spec
from open_composer.storage import write_json

REPORT_STEM = "nasdaq_tqqq_return_enhanced_router_daily-regime-filter"
START_DATE = "2020-07-27"
END_DATE = "2026-05-22"


@dataclass(frozen=True)
class RegimeGate:
    label: str
    sma_days: int | None = None
    momentum_days: int | None = None
    drawdown_days: int | None = None
    max_drawdown_pct: float | None = None
    vol_days: int | None = None
    max_ann_vol_pct: float | None = None
    mode: str = "and"


def main() -> None:
    root = project_root()
    base.START_DATE = START_DATE
    base.END_DATE = END_DATE
    spec = load_strategy_spec(root / base.SPEC_PATH)
    dates, opens, closes = base._load_arrays(root)
    date_index = {date: index for index, date in enumerate(dates)}
    cost_rate = spec.costs.commission_pct / 100 + spec.costs.slippage_bps / 10_000
    open_to_open_returns = np.zeros_like(opens)
    open_to_open_returns[:-1] = opens[1:] * (1 - cost_rate) / (opens[:-1] * (1 + cost_rate)) - 1

    params = base.BetaOverrideParams(
        momentum_lookback_days=30,
        min_momentum_pct=10.0,
        override_advantage_pct=-5.0,
        confirmation_sma_days=100,
        exclude_tqqq=True,
    )
    baseline_returns, baseline_weights = base._run_candidate(
        dates=dates,
        closes=closes,
        open_to_open_returns=open_to_open_returns,
        params=params,
    )
    gates = _gates()
    rows = []
    for gate in gates:
        returns, weights = _run_gated_override(
            closes=closes,
            open_to_open_returns=open_to_open_returns,
            params=params,
            gate=gate,
        )
        rows.append(
            _row(
                dates=dates,
                date_index=date_index,
                returns=returns,
                weights=weights,
                baseline_returns=baseline_returns,
                baseline_weights=baseline_weights,
                gate=gate,
            )
        )
    rows.sort(key=lambda item: item["score"], reverse=True)
    payload = {
        "strategy_name": base.STRATEGY,
        "report_type": "regime_filter_grid",
        "base_route_label": params.label,
        "selected_gate": rows[0],
        "candidates": rows,
        "objective": {
            "primary": (
                "repair 2022 bear-market damage without materially reducing 2024-2026 upside"
            ),
            "selection": (
                "score = long_window_total + current_oos_total + 0.5*calendar_2024_total "
                "- 2*abs(min(2022_total, 0)) - 0.5*abs(long_window_max_drawdown)"
            ),
        },
        "caveats": [
            "This is a regime-filter research grid, not a promoted StrategySpec.",
            "Fixed selected override parameters are reused; only market-cycle gating varies.",
            "Local Alpaca IEX cache is not SIP data and remains current-symbol biased.",
        ],
    }
    reports = ensure_dir(root / "reports" / "research")
    json_path = reports / f"{REPORT_STEM}.json"
    md_path = reports / f"{REPORT_STEM}.md"
    write_json(json_path, _jsonable(payload))
    _write_markdown(md_path, payload)
    print(json.dumps({"json": str(json_path), "markdown": str(md_path)}, indent=2))


def _gates() -> list[RegimeGate]:
    return [
        RegimeGate("no_extra_cycle_gate"),
        RegimeGate("qqq_sma100", sma_days=100),
        RegimeGate("qqq_sma150", sma_days=150),
        RegimeGate("qqq_sma200", sma_days=200),
        RegimeGate("qqq_sma250", sma_days=250),
        RegimeGate("qqq_mom60", momentum_days=60),
        RegimeGate("qqq_mom120", momentum_days=120),
        RegimeGate("qqq_sma200_or_mom120", sma_days=200, momentum_days=120, mode="or"),
        RegimeGate("qqq_sma200_and_mom120", sma_days=200, momentum_days=120),
        RegimeGate("qqq_dd252_not_worse_20", drawdown_days=252, max_drawdown_pct=20.0),
        RegimeGate("qqq_dd252_not_worse_25", drawdown_days=252, max_drawdown_pct=25.0),
        RegimeGate(
            "qqq_sma200_or_dd252_20",
            sma_days=200,
            drawdown_days=252,
            max_drawdown_pct=20.0,
            mode="or",
        ),
        RegimeGate(
            "qqq_sma200_and_dd252_25",
            sma_days=200,
            drawdown_days=252,
            max_drawdown_pct=25.0,
        ),
        RegimeGate("qqq_vol20_below_35", vol_days=20, max_ann_vol_pct=35.0),
        RegimeGate(
            "qqq_sma200_and_vol20_below_35",
            sma_days=200,
            vol_days=20,
            max_ann_vol_pct=35.0,
        ),
    ]


def _run_gated_override(
    *,
    closes: np.ndarray,
    open_to_open_returns: np.ndarray,
    params: base.BetaOverrideParams,
    gate: RegimeGate,
) -> tuple[np.ndarray, np.ndarray]:
    weights = base._iter2_base_weights(closes)
    tqqq_index = base.UNIVERSE.index(base.BENCHMARK_SYMBOL)
    min_index = max(
        251,
        params.momentum_lookback_days + 1,
        params.confirmation_sma_days or 0,
        gate.sma_days or 0,
        (gate.momentum_days or 0) + 1,
        gate.drawdown_days or 0,
        (gate.vol_days or 0) + 1,
    )
    for index in range(min_index, len(closes) - 1):
        if not _gate_passes(closes, index, gate):
            continue
        raw = (closes[index - 1] / closes[index - 1 - params.momentum_lookback_days] - 1) * 100
        eligible = raw >= params.min_momentum_pct
        if params.exclude_tqqq:
            eligible[tqqq_index] = False
        if not bool(eligible.any()):
            continue
        selected = int(np.argsort(np.where(eligible, raw, -1e12))[::-1][0])
        if params.confirmation_sma_days is not None:
            sma = closes[index - params.confirmation_sma_days : index, selected].mean()
            if closes[index - 1, selected] <= sma:
                continue
        if raw[selected] < raw[tqqq_index] + params.override_advantage_pct:
            continue
        weights[index, :] = 0.0
        weights[index, selected] = 1.0
    returns = (weights * open_to_open_returns).sum(axis=1)
    return returns, weights


def _gate_passes(closes: np.ndarray, index: int, gate: RegimeGate) -> bool:
    if gate.label == "no_extra_cycle_gate":
        return True
    qqq_index = base.UNIVERSE.index(base.MARKET_SYMBOL)
    checks = []
    if gate.sma_days is not None:
        sma = closes[index - gate.sma_days : index, qqq_index].mean()
        checks.append(closes[index - 1, qqq_index] > sma)
    if gate.momentum_days is not None:
        momentum = (
            closes[index - 1, qqq_index] / closes[index - 1 - gate.momentum_days, qqq_index] - 1
        )
        checks.append(momentum > 0)
    if gate.drawdown_days is not None and gate.max_drawdown_pct is not None:
        window = closes[index - gate.drawdown_days : index, qqq_index]
        drawdown = (window[-1] / window.max() - 1) * 100
        checks.append(drawdown > -gate.max_drawdown_pct)
    if gate.vol_days is not None and gate.max_ann_vol_pct is not None:
        window = closes[index - gate.vol_days - 1 : index, qqq_index]
        daily = window[1:] / window[:-1] - 1
        ann_vol = float(daily.std(ddof=0) * math.sqrt(252) * 100)
        checks.append(ann_vol <= gate.max_ann_vol_pct)
    if not checks:
        return True
    if gate.mode == "or":
        return any(checks)
    return all(checks)


def _row(
    *,
    dates: list[str],
    date_index: dict[str, int],
    returns: np.ndarray,
    weights: np.ndarray,
    baseline_returns: np.ndarray,
    baseline_weights: np.ndarray,
    gate: RegimeGate,
) -> dict[str, Any]:
    periods = {
        "long_window": _metrics(
            dates, returns, weights, date_index["2021-07-27"], date_index[END_DATE]
        ),
        "calendar_2022": _metrics(
            dates, returns, weights, date_index["2022-01-03"], date_index["2022-12-30"]
        ),
        "calendar_2023": _metrics(
            dates, returns, weights, date_index["2023-01-03"], date_index["2023-12-29"]
        ),
        "calendar_2024": _metrics(
            dates, returns, weights, date_index["2024-01-02"], date_index["2024-12-31"]
        ),
        "calendar_2025": _metrics(
            dates, returns, weights, date_index["2025-01-02"], date_index["2025-12-31"]
        ),
        "calendar_2026_ytd": _metrics(
            dates, returns, weights, date_index["2026-01-02"], date_index[END_DATE]
        ),
        "current_oos": _metrics(
            dates, returns, weights, date_index["2024-11-04"], date_index[END_DATE]
        ),
    }
    baseline = {
        "long_window": _metrics(
            dates,
            baseline_returns,
            baseline_weights,
            date_index["2021-07-27"],
            date_index[END_DATE],
        ),
        "calendar_2022": _metrics(
            dates,
            baseline_returns,
            baseline_weights,
            date_index["2022-01-03"],
            date_index["2022-12-30"],
        ),
        "calendar_2024": _metrics(
            dates,
            baseline_returns,
            baseline_weights,
            date_index["2024-01-02"],
            date_index["2024-12-31"],
        ),
        "current_oos": _metrics(
            dates,
            baseline_returns,
            baseline_weights,
            date_index["2024-11-04"],
            date_index[END_DATE],
        ),
    }
    score = (
        periods["long_window"]["total_return_pct"]
        + periods["current_oos"]["total_return_pct"]
        + 0.5 * periods["calendar_2024"]["total_return_pct"]
        - 2.0 * abs(min(periods["calendar_2022"]["total_return_pct"], 0.0))
        - 0.5 * abs(periods["long_window"]["max_drawdown_pct"])
    )
    return {
        "gate": asdict(gate),
        "score": float(score),
        "periods": periods,
        "baseline_no_gate": baseline,
    }


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
    return metrics


def _write_markdown(path: Path, payload: dict[str, Any]) -> None:
    lines = [
        "# Regime Filter Grid: Return-Enhanced Router",
        "",
        f"- Strategy: `{payload['strategy_name']}`",
        f"- Base route: `{payload['base_route_label']}`",
        f"- Selected gate: `{payload['selected_gate']['gate']['label']}`",
        "",
        "## Top Candidates",
        "",
        "| Rank | Gate | Score | Long Total | Long DD | 2022 Total | 2024 Total | OOS Total |",
        "|---:|---|---:|---:|---:|---:|---:|---:|",
    ]
    for rank, row in enumerate(payload["candidates"][:10], start=1):
        periods = row["periods"]
        lines.append(
            f"| {rank} | {row['gate']['label']} | {_fmt(row['score'])} | "
            f"{_fmt(periods['long_window']['total_return_pct'])}% | "
            f"{_fmt(periods['long_window']['max_drawdown_pct'])}% | "
            f"{_fmt(periods['calendar_2022']['total_return_pct'])}% | "
            f"{_fmt(periods['calendar_2024']['total_return_pct'])}% | "
            f"{_fmt(periods['current_oos']['total_return_pct'])}% |"
        )
    lines.extend(
        [
            "",
            "## Caveats",
            "",
            *[f"- {item}" for item in payload["caveats"]],
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


def _jsonable(value: Any) -> Any:
    return json.loads(json.dumps(value, default=_json_default))


def _json_default(value: Any) -> Any:
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, Path):
        return str(value)
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


if __name__ == "__main__":
    main()
