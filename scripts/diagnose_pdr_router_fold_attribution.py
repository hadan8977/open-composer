"""Per-state / per-asset fold attribution for the pdr defensive-overlay route.

The post_drawdown_reentry router and its overlays exist only as orphaned
bytecode under open_composer/research/__pycache__/ (source was never
committed). This diagnostic loads that bytecode read-only to reproduce the
long-window fixed-route simulation and attribute each walk-forward fold's
return to router states and assets. It writes research control artifacts and
never touches specs, paper automation, or broker paths.
"""

from __future__ import annotations

import importlib
import importlib.machinery
import json
import sys
import warnings
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from open_composer.models.strategy_spec import load_strategy_spec  # noqa: E402
from open_composer.research.router_common import (  # noqa: E402
    RouterFrameDataset,
    backtest_router_params,
    load_daily_dataset,
    symbol_holding_return,
)
from open_composer.storage import write_json  # noqa: E402

ARTIFACT = (
    ROOT
    / "reports/research/"
    / "nasdaq_tqqq_post_drawdown_reentry_router_delayed30_offensive-long-window-fixed-route.json"
)
OUT_STEM = ROOT / "reports/research/control/pdr-router-fold-attribution-20260703"
BYTECODE_MODULES = [
    "router_base",
    "delayed_entry_overlay",
    "post_drawdown_reentry_router",
    "defensive_transition_overlay",
]
DATA_START = "2012-01-03"
DATA_END = "2026-05-22"
ROUTER_IMPLEMENTATION = "source_import"


def load_orphaned_router_modules() -> Any:
    global ROUTER_IMPLEMENTATION
    try:
        return importlib.import_module("open_composer.research.defensive_transition_overlay")
    except ImportError as exc:
        ROUTER_IMPLEMENTATION = "orphaned_bytecode_sourceless_load"
        warnings.warn(
            f"falling back to orphaned PDR router bytecode because source imports failed: {exc}",
            RuntimeWarning,
            stacklevel=2,
        )
    for name in BYTECODE_MODULES:
        full = f"open_composer.research.{name}"
        if full in sys.modules:
            continue
        path = ROOT / "open_composer/research/__pycache__" / f"{name}.cpython-311.pyc"
        if not path.exists():
            raise SystemExit(
                f"missing orphaned bytecode {path}; the pdr router source was never "
                "committed and cannot be reproduced without it"
            )
        loader = importlib.machinery.SourcelessFileLoader(full, str(path))
        sys.modules[full] = loader.load_module()
    return sys.modules["open_composer.research.defensive_transition_overlay"]


def simulate_daily_rows(
    spec: Any,
    dataset: RouterFrameDataset,
    overlay: Any,
    snapshot_fn: Any,
    start_index: int,
    end_index: int,
) -> list[dict[str, Any]]:
    cost_rate = spec.costs.commission_pct / 100 + spec.costs.slippage_bps / 10_000
    previous_weights: dict[str, float] = {}
    rows: list[dict[str, Any]] = []
    for index in range(start_index, end_index):
        snap = snapshot_fn(spec, dataset, overlay, index)
        contributions = {
            symbol: weight * symbol_holding_return(dataset, symbol, index, "open_to_open", spec)
            for symbol, weight in snap.weights.items()
            if weight > 0
        }
        raw = sum(contributions.values())
        turnover = sum(
            abs(snap.weights.get(symbol, 0.0) - previous_weights.get(symbol, 0.0))
            for symbol in set(snap.weights) | set(previous_weights)
        )
        cost = turnover * cost_rate
        rows.append(
            {
                "date": dataset.dates[index],
                "state": snap.state,
                "weights": {k: v for k, v in snap.weights.items() if v},
                "contributions": contributions,
                "raw_return": raw,
                "cost": cost,
                "net_return": raw - cost,
                "tqqq_return": symbol_holding_return(dataset, "TQQQ", index, "open_to_open", spec),
            }
        )
        previous_weights = snap.weights
    return rows


def compound_pct(returns: list[float]) -> float:
    value = 1.0
    for item in returns:
        value *= 1 + item
    return (value - 1) * 100


def attribute_window(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_state: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "days": 0,
            "net_return_sum": 0.0,
            "tqqq_return_sum": 0.0,
            "cost_sum": 0.0,
            "net_returns": [],
            "assets": Counter(),
        }
    )
    by_asset: dict[str, dict[str, float]] = defaultdict(
        lambda: {"days": 0, "contribution_sum": 0.0}
    )
    transitions = 0
    previous_state: str | None = None
    for row in rows:
        state = by_state[row["state"]]
        state["days"] += 1
        state["net_return_sum"] += row["net_return"]
        state["tqqq_return_sum"] += row["tqqq_return"]
        state["cost_sum"] += row["cost"]
        state["net_returns"].append(row["net_return"])
        for symbol, contribution in row["contributions"].items():
            state["assets"][symbol] += 1
            by_asset[symbol]["days"] += 1
            by_asset[symbol]["contribution_sum"] += contribution
        if previous_state is not None and row["state"] != previous_state:
            transitions += 1
        previous_state = row["state"]
    states_payload = {}
    for name, item in sorted(by_state.items(), key=lambda kv: -kv[1]["days"]):
        states_payload[name] = {
            "days": item["days"],
            "day_share_pct": round(item["days"] / len(rows) * 100, 2),
            "net_return_sum_pct": round(item["net_return_sum"] * 100, 2),
            "isolated_compound_pct": round(compound_pct(item["net_returns"]), 2),
            "tqqq_same_days_sum_pct": round(item["tqqq_return_sum"] * 100, 2),
            "gap_vs_tqqq_sum_pct": round(
                (item["net_return_sum"] - item["tqqq_return_sum"]) * 100, 2
            ),
            "cost_sum_pct": round(item["cost_sum"] * 100, 3),
            "assets_days": dict(item["assets"].most_common()),
        }
    assets_payload = {
        name: {
            "days": item["days"],
            "contribution_sum_pct": round(item["contribution_sum"] * 100, 2),
        }
        for name, item in sorted(by_asset.items(), key=lambda kv: -kv[1]["contribution_sum"])
    }
    return {
        "days": len(rows),
        "net_compound_pct": round(compound_pct([row["net_return"] for row in rows]), 2),
        "tqqq_compound_pct": round(compound_pct([row["tqqq_return"] for row in rows]), 2),
        "state_transitions": transitions,
        "by_state": states_payload,
        "by_asset": assets_payload,
    }


def main() -> None:
    artifact = json.loads(ARTIFACT.read_text(encoding="utf-8"))
    route_label = artifact["route_label"]
    spec = load_strategy_spec(ROOT / artifact["source_spec_path"])
    overlay_module = load_orphaned_router_modules()
    overlay = overlay_module.defensive_transition_overlay_from_label(route_label)
    snapshot_fn = overlay_module.defensive_transition_overlay_target_weight_snapshot
    lookback = overlay_module.defensive_transition_overlay_effective_lookback(overlay)

    dataset = load_daily_dataset(
        spec=spec,
        root=ROOT,
        symbols=[item.upper() for item in spec.universe],
        data_source="longbridge",
        feed=None,
        start=DATA_START,
        end=DATA_END,
        market_symbol="QQQ",
        benchmark_symbol="TQQQ",
    )
    end_index = len(dataset.dates) - 1
    rows = simulate_daily_rows(spec, dataset, overlay, snapshot_fn, lookback, end_index)

    engine = backtest_router_params(
        spec,
        dataset,
        overlay,
        snapshot=lambda s, d, p, i: snapshot_fn(s, d, p, i),
        start_index=lookback,
        end_index=len(dataset.dates),
    )
    folds = artifact["selected_route"]["walk_forward"]["folds"]
    fold_windows = [
        (item["fold"], item["metrics"]["start_date"], item["metrics"]["end_date"], item["metrics"])
        for item in folds
    ]

    full_attr = attribute_window(rows)
    artifact_full = artifact["selected_route"]["full_window"]
    parity = {
        "full_window": {
            "recorded_days": full_attr["days"],
            "engine_days": engine.days,
            "artifact_days": artifact_full["days"],
            "recorded_compound_pct": full_attr["net_compound_pct"],
            "engine_total_return_pct": round(engine.total_return_pct, 2),
            "artifact_total_return_pct": round(artifact_full["total_return_pct"], 2),
        },
        "folds": [],
    }
    fold_payload = []
    frame_dates = pd.Series(dataset.dates)
    for fold, start_date, end_date, reference in fold_windows:
        fold_rows = [row for row in rows if start_date <= row["date"] <= end_date]
        attr = attribute_window(fold_rows)
        start_idx = int(frame_dates[frame_dates >= start_date].index[0])
        end_idx = int(frame_dates[frame_dates <= end_date].index[-1]) + 1
        engine_fold = backtest_router_params(
            spec,
            dataset,
            overlay,
            snapshot=lambda s, d, p, i: snapshot_fn(s, d, p, i),
            start_index=start_idx,
            end_index=end_idx,
        )
        parity["folds"].append(
            {
                "fold": fold,
                "recorded_compound_pct": attr["net_compound_pct"],
                "engine_total_return_pct": round(engine_fold.total_return_pct, 2),
                "artifact_total_return_pct": round(reference["total_return_pct"], 2),
                "artifact_benchmark_pct": round(reference["benchmark_buy_hold_return_pct"], 2),
            }
        )
        fold_payload.append(
            {
                "fold": fold,
                "start_date": start_date,
                "end_date": end_date,
                "artifact_reference": {
                    "total_return_pct": reference["total_return_pct"],
                    "benchmark_buy_hold_return_pct": reference["benchmark_buy_hold_return_pct"],
                    "sharpe_ratio": reference["sharpe_ratio"],
                    "max_drawdown_pct": reference["max_drawdown_pct"],
                },
                "attribution": attr,
            }
        )

    payload = {
        "report_type": "pdr_router_fold_state_asset_attribution",
        "strategy_name": artifact["strategy_name"],
        "route_label": route_label,
        "source_artifact": str(ARTIFACT.relative_to(ROOT)),
        "reproduction": {
            "router_implementation": ROUTER_IMPLEMENTATION,
            "bytecode_modules": BYTECODE_MODULES,
            "effective_lookback_days": lookback,
            "data_profile": dataset.data_profile,
        },
        "caveats": [
            (
                "router source import is preferred; orphaned bytecode is used only as an "
                "explicit warning fallback"
            ),
            "adjusted daily research cache is research_cross_check evidence, not broker "
            "execution evidence",
            "this artifact attributes an existing fixed route; it does not discover or "
            "select parameters",
        ],
        "parity_check": parity,
        "full_window_attribution": full_attr,
        "folds": fold_payload,
    }
    write_json(OUT_STEM.with_suffix(".json"), payload)
    OUT_STEM.with_suffix(".md").write_text(render_markdown(payload), encoding="utf-8")
    golden_path = OUT_STEM.parent / "pdr-router-golden-daily-decisions-20260703.jsonl"
    with golden_path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(
                json.dumps(
                    {
                        "date": row["date"],
                        "state": row["state"],
                        "weights": row["weights"],
                        "net_return": round(row["net_return"], 12),
                    },
                    sort_keys=True,
                )
                + "\n"
            )
    print(f"wrote {golden_path}")
    print(f"wrote {OUT_STEM.with_suffix('.json')}")
    print(f"wrote {OUT_STEM.with_suffix('.md')}")
    print(json.dumps(parity, indent=2))


def render_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# PDR Router Fold Attribution (state / asset)",
        "",
        f"- Strategy: `{payload['strategy_name']}`",
        f"- Route: `{payload['route_label']}`",
        f"- Source artifact: `{payload['source_artifact']}`",
        f"- Router implementation: `{payload['reproduction']['router_implementation']}`",
        f"- Warmup lookback days: `{payload['reproduction']['effective_lookback_days']}`",
        "",
        "## Caveats",
        "",
        *[f"- {item}" for item in payload["caveats"]],
        "",
        "## Parity check (recorded loop vs router engine vs prior artifact)",
        "",
        "| window | recorded % | engine % | artifact % | TQQQ % |",
        "| --- | --- | --- | --- | --- |",
    ]
    full = payload["parity_check"]["full_window"]
    lines.append(
        f"| full | {full['recorded_compound_pct']} | {full['engine_total_return_pct']} | "
        f"{full['artifact_total_return_pct']} | - |"
    )
    for item in payload["parity_check"]["folds"]:
        lines.append(
            f"| fold {item['fold']} | {item['recorded_compound_pct']} | "
            f"{item['engine_total_return_pct']} | {item['artifact_total_return_pct']} | "
            f"{item['artifact_benchmark_pct']} |"
        )
    for fold in payload["folds"]:
        attr = fold["attribution"]
        ref = fold["artifact_reference"]
        lines.extend(
            [
                "",
                f"## Fold {fold['fold']}: {fold['start_date']} -> {fold['end_date']}",
                "",
                f"- Recorded compound: `{attr['net_compound_pct']}%` vs TQQQ "
                f"`{attr['tqqq_compound_pct']}%` (artifact: `{round(ref['total_return_pct'], 2)}%` "
                f"vs `{round(ref['benchmark_buy_hold_return_pct'], 2)}%`)",
                f"- State transitions: `{attr['state_transitions']}`",
                "",
                "| state | days | share % | net sum % | isolated % | TQQQ sum % | gap % | "
                "assets (days) |",
                "| --- | --- | --- | --- | --- | --- | --- | --- |",
            ]
        )
        for name, item in attr["by_state"].items():
            assets = ", ".join(f"{k}:{v}" for k, v in item["assets_days"].items()) or "-"
            lines.append(
                f"| {name} | {item['days']} | {item['day_share_pct']} | "
                f"{item['net_return_sum_pct']} | {item['isolated_compound_pct']} | "
                f"{item['tqqq_same_days_sum_pct']} | {item['gap_vs_tqqq_sum_pct']} | {assets} |"
            )
        lines.extend(
            [
                "",
                "| asset | days | contribution sum % |",
                "| --- | --- | --- |",
            ]
        )
        for name, item in attr["by_asset"].items():
            lines.append(f"| {name} | {item['days']} | {item['contribution_sum_pct']} |")
    attr = payload["full_window_attribution"]
    lines.extend(
        [
            "",
            "## Full window",
            "",
            f"- Recorded compound: `{attr['net_compound_pct']}%` vs TQQQ "
            f"`{attr['tqqq_compound_pct']}%`",
            f"- State transitions: `{attr['state_transitions']}`",
            "",
            "| state | days | share % | net sum % | isolated % | TQQQ sum % | gap % |",
            "| --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for name, item in attr["by_state"].items():
        lines.append(
            f"| {name} | {item['days']} | {item['day_share_pct']} | "
            f"{item['net_return_sum_pct']} | {item['isolated_compound_pct']} | "
            f"{item['tqqq_same_days_sum_pct']} | {item['gap_vs_tqqq_sum_pct']} |"
        )
    lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    main()
