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

from open_composer.config import ensure_dir, project_root
from open_composer.models.strategy_spec import load_strategy_spec
from open_composer.research.hybrid_router_core import (
    _effective_lookback,
    hybrid_params_from_label,
    hybrid_target_weight_snapshot,
)
from open_composer.research.router_common import (
    RouterFrameDataset,
    backtest_router_params,
    load_daily_dataset,
    symbol_holding_return,
)
from open_composer.storage import write_json

DEFAULT_SPEC_PATH = Path(
    "strategy_specs/active/"
    "nasdaq_tqqq_post_drawdown_reentry_router_delayed30_offensive_paper_auto_candidate.yaml"
)
DEFAULT_SOURCE_ARTIFACT = Path(
    "reports/research/"
    "nasdaq_tqqq_post_drawdown_reentry_router_delayed30_offensive-long-window-fixed-route.json"
)
DEFAULT_OUT_DIR = Path("reports/research/control")
DEFAULT_DATE_TAG = "20260703"
DEFAULT_START = "2012-01-03"
DEFAULT_END = "2026-05-22"
DEFAULT_FOLDS: tuple[tuple[str, str, str], ...] = (
    ("fold1", "2013-01-08", "2015-03-31"),
    ("fold2", "2015-04-01", "2017-06-27"),
    ("fold3", "2017-06-28", "2019-09-17"),
    ("fold4", "2019-09-18", "2021-12-06"),
    ("fold5", "2021-12-07", "2024-02-28"),
    ("fold6", "2024-02-29", "2026-05-21"),
)
BYTECODE_MODULES = [
    "router_base",
    "delayed_entry_overlay",
    "post_drawdown_reentry_router",
    "defensive_transition_overlay",
]


def load_pdr_router_modules(root: Path | None = None) -> str:
    """Prefer restored source imports; fall back to orphan bytecode with a warning."""
    try:
        importlib.import_module("open_composer.research.defensive_transition_overlay")
        return "source_import"
    except ImportError as exc:
        implementation = "orphaned_bytecode_sourceless_load"
        warnings.warn(
            f"falling back to orphaned PDR router bytecode because source imports failed: {exc}",
            RuntimeWarning,
            stacklevel=2,
        )
    base = root or project_root()
    for name in BYTECODE_MODULES:
        full = f"open_composer.research.{name}"
        if full in sys.modules:
            continue
        path = base / "open_composer/research/__pycache__" / f"{name}.cpython-311.pyc"
        if not path.exists():
            raise FileNotFoundError(
                f"missing orphaned bytecode {path}; restored PDR router source is unavailable"
            )
        loader = importlib.machinery.SourcelessFileLoader(full, str(path))
        sys.modules[full] = loader.load_module()
    return implementation


def simulate_daily_rows(
    spec: Any,
    dataset: RouterFrameDataset,
    params: object,
    start_index: int,
    end_index: int,
) -> list[dict[str, Any]]:
    cost_rate = spec.costs.commission_pct / 100 + spec.costs.slippage_bps / 10_000
    previous_weights: dict[str, float] = {}
    rows: list[dict[str, Any]] = []
    for index in range(start_index, end_index):
        snap = hybrid_target_weight_snapshot(spec, dataset, params, index)
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
                "weights": {key: value for key, value in snap.weights.items() if value},
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
    if not rows:
        return {
            "days": 0,
            "net_compound_pct": 0.0,
            "tqqq_compound_pct": 0.0,
            "state_transitions": 0,
            "by_state": {},
            "by_asset": {},
        }
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


def parse_fold_windows(value: str | None) -> tuple[tuple[str, str, str], ...]:
    if not value:
        return DEFAULT_FOLDS
    windows: list[tuple[str, str, str]] = []
    for raw in value.split(","):
        parts = [item.strip() for item in raw.split(":")]
        if len(parts) != 3 or not all(parts):
            raise ValueError(
                "--folds must be comma-separated name:start:end values, "
                "for example fold1:2013-01-08:2015-03-31"
            )
        windows.append((parts[0], parts[1], parts[2]))
    return tuple(windows)


def run_pdr_router_attribution(
    spec_path: Path = DEFAULT_SPEC_PATH,
    *,
    root: Path | None = None,
    label: str | None = None,
    data_source: str = "longbridge",
    feed: str | None = None,
    start: str = DEFAULT_START,
    end: str = DEFAULT_END,
    folds: tuple[tuple[str, str, str], ...] = DEFAULT_FOLDS,
    out_dir: Path = DEFAULT_OUT_DIR,
    date_tag: str = DEFAULT_DATE_TAG,
    source_artifact: Path | None = DEFAULT_SOURCE_ARTIFACT,
) -> dict[str, Any]:
    base = root or project_root()
    resolved_spec = spec_path if spec_path.is_absolute() else base / spec_path
    spec = load_strategy_spec(resolved_spec)
    route_label = label or spec.portfolio.selected_route_label
    if not route_label:
        raise ValueError(
            "router attribution requires --label or spec.portfolio.selected_route_label"
        )
    router_implementation = load_pdr_router_modules(base)
    params = hybrid_params_from_label(route_label)
    lookback = _effective_lookback(params)
    dataset = load_daily_dataset(
        spec=spec,
        root=base,
        symbols=[item.upper() for item in spec.universe],
        data_source=data_source,
        feed=feed,
        start=start,
        end=end,
        market_symbol="QQQ",
        benchmark_symbol="TQQQ",
    )
    end_index = len(dataset.dates) - 1
    rows = simulate_daily_rows(spec, dataset, params, lookback, end_index)
    source_payload = _load_source_artifact(base, source_artifact)
    payload = build_pdr_attribution_payload(
        spec=spec,
        dataset=dataset,
        params=params,
        route_label=route_label,
        rows=rows,
        fold_windows=folds,
        start_index=lookback,
        end_index=end_index,
        router_implementation=router_implementation,
        source_artifact=source_artifact,
        source_payload=source_payload,
    )
    out_root = ensure_dir(out_dir if out_dir.is_absolute() else base / out_dir)
    stem = out_root / f"pdr-router-fold-attribution-{date_tag}"
    json_path = stem.with_suffix(".json")
    md_path = stem.with_suffix(".md")
    golden_path = out_root / f"pdr-router-golden-daily-decisions-{date_tag}.jsonl"
    write_json(json_path, payload)
    md_path.write_text(render_markdown(payload), encoding="utf-8")
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
    payload["artifact_paths"] = {
        "json": str(json_path),
        "markdown": str(md_path),
        "golden_daily_decisions": str(golden_path),
    }
    write_json(json_path, payload)
    return payload


def build_pdr_attribution_payload(
    *,
    spec: Any,
    dataset: RouterFrameDataset,
    params: object,
    route_label: str,
    rows: list[dict[str, Any]],
    fold_windows: tuple[tuple[str, str, str], ...],
    start_index: int,
    end_index: int,
    router_implementation: str,
    source_artifact: Path | None,
    source_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    engine = backtest_router_params(
        spec,
        dataset,
        params,
        snapshot=hybrid_target_weight_snapshot,
        start_index=start_index,
        end_index=end_index + 1,
    )
    full_attr = attribute_window(rows)
    artifact_full = (source_payload or {}).get("selected_route", {}).get("full_window", {})
    parity = {
        "full_window": {
            "recorded_days": full_attr["days"],
            "engine_days": engine.days,
            "artifact_days": artifact_full.get("days"),
            "recorded_compound_pct": full_attr["net_compound_pct"],
            "engine_total_return_pct": round(engine.total_return_pct, 2),
            "artifact_total_return_pct": _round_optional(artifact_full.get("total_return_pct")),
        },
        "folds": [],
    }
    fold_payload = []
    frame_dates = pd.Series(dataset.dates)
    reference_by_fold = _reference_by_fold(source_payload)
    for fold, start_date, end_date in fold_windows:
        fold_rows = [row for row in rows if start_date <= row["date"] <= end_date]
        attr = attribute_window(fold_rows)
        start_idx = int(frame_dates[frame_dates >= start_date].index[0])
        end_idx = int(frame_dates[frame_dates <= end_date].index[-1]) + 1
        engine_fold = backtest_router_params(
            spec,
            dataset,
            params,
            snapshot=hybrid_target_weight_snapshot,
            start_index=start_idx,
            end_index=end_idx,
        )
        reference = reference_by_fold.get(fold, {})
        parity["folds"].append(
            {
                "fold": fold,
                "recorded_compound_pct": attr["net_compound_pct"],
                "engine_total_return_pct": round(engine_fold.total_return_pct, 2),
                "artifact_total_return_pct": _round_optional(reference.get("total_return_pct")),
                "artifact_benchmark_pct": _round_optional(
                    reference.get("benchmark_buy_hold_return_pct")
                ),
            }
        )
        fold_payload.append(
            {
                "fold": fold,
                "start_date": start_date,
                "end_date": end_date,
                "artifact_reference": {
                    "total_return_pct": reference.get("total_return_pct"),
                    "benchmark_buy_hold_return_pct": reference.get("benchmark_buy_hold_return_pct"),
                    "sharpe_ratio": reference.get("sharpe_ratio"),
                    "max_drawdown_pct": reference.get("max_drawdown_pct"),
                },
                "attribution": attr,
            }
        )
    return {
        "report_type": "pdr_router_fold_state_asset_attribution",
        "strategy_name": spec.name,
        "route_label": route_label,
        "source_artifact": str(source_artifact) if source_artifact else None,
        "reproduction": {
            "router_implementation": router_implementation,
            "bytecode_modules": BYTECODE_MODULES,
            "effective_lookback_days": _effective_lookback(params),
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
        f"{_fmt(full['artifact_total_return_pct'])} | - |"
    )
    for item in payload["parity_check"]["folds"]:
        lines.append(
            f"| fold {item['fold']} | {item['recorded_compound_pct']} | "
            f"{item['engine_total_return_pct']} | {_fmt(item['artifact_total_return_pct'])} | "
            f"{_fmt(item['artifact_benchmark_pct'])} |"
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
                f"`{attr['tqqq_compound_pct']}%` (artifact: "
                f"`{_fmt(_round_optional(ref['total_return_pct']))}%` vs "
                f"`{_fmt(_round_optional(ref['benchmark_buy_hold_return_pct']))}%`)",
                f"- State transitions: `{attr['state_transitions']}`",
                "",
                "| state | days | share % | net sum % | isolated % | TQQQ sum % | gap % | "
                "assets (days) |",
                "| --- | --- | --- | --- | --- | --- | --- | --- |",
            ]
        )
        for name, item in attr["by_state"].items():
            assets = ", ".join(f"{key}:{value}" for key, value in item["assets_days"].items())
            lines.append(
                f"| {name} | {item['days']} | {item['day_share_pct']} | "
                f"{item['net_return_sum_pct']} | {item['isolated_compound_pct']} | "
                f"{item['tqqq_same_days_sum_pct']} | {item['gap_vs_tqqq_sum_pct']} | "
                f"{assets or '-'} |"
            )
        lines.extend(["", "| asset | days | contribution sum % |", "| --- | --- | --- |"])
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


def _load_source_artifact(root: Path, source_artifact: Path | None) -> dict[str, Any] | None:
    if source_artifact is None:
        return None
    path = source_artifact if source_artifact.is_absolute() else root / source_artifact
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _reference_by_fold(source_payload: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    output: dict[str, dict[str, Any]] = {}
    for item in (
        (source_payload or {}).get("selected_route", {}).get("walk_forward", {}).get("folds", [])
    ):
        output[item["fold"]] = item.get("metrics", {})
    return output


def _round_optional(value: Any) -> float | None:
    if value is None:
        return None
    return round(float(value), 2)


def _fmt(value: Any) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, int | float):
        return f"{float(value):.2f}"
    return str(value)
