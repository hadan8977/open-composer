from __future__ import annotations

import argparse
import json
from pathlib import Path

from open_composer.config import project_root
from open_composer.models.strategy_spec import load_strategy_spec
from open_composer.research.defensive_transition_overlay import DefensiveTransitionOverlay
from open_composer.research.hybrid_router_core import hybrid_params_from_label
from open_composer.research.pdr_ml_gate import train_pdr_ml_gate_trials
from open_composer.research.post_drawdown_reentry_router import (
    PostDrawdownReentryParams,
    post_drawdown_reentry_params_from_label,
)
from open_composer.research.router_common import load_daily_dataset

DEFAULT_SPEC = "strategy_specs/drafts/nasdaq_tqqq_pdr_router_mlgate_iter1.yaml"
DEFAULT_START = "2012-01-03"
DEFAULT_END = "2026-05-22"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Train the bounded 12-trial PDR defensive-exit ML gate."
    )
    parser.add_argument("--spec", default=DEFAULT_SPEC)
    parser.add_argument(
        "--data-source", default="longbridge", choices=["longbridge", "alpaca", "sample"]
    )
    parser.add_argument("--feed", default=None)
    parser.add_argument("--start", default=DEFAULT_START)
    parser.add_argument("--end", default=DEFAULT_END)
    parser.add_argument("--window-bars", type=int, default=756)
    parser.add_argument("--test-window-bars", type=int, default=126)
    parser.add_argument("--retrain-every-bars", type=int, default=63)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    root = project_root()
    spec_path = Path(args.spec)
    if not spec_path.is_absolute():
        spec_path = root / spec_path
    spec = load_strategy_spec(spec_path)
    params = hybrid_params_from_label(spec.portfolio.selected_route_label or "")
    base_params = _base_pdr_params(params)
    dataset = load_daily_dataset(
        spec=spec,
        root=root,
        symbols=spec.universe,
        data_source=args.data_source,
        feed=args.feed,
        start=args.start,
        end=args.end,
        market_symbol="QQQ",
        benchmark_symbol="TQQQ",
    )
    summary = train_pdr_ml_gate_trials(
        spec,
        dataset,
        base_params,
        root=root,
        window_bars=args.window_bars,
        test_window_bars=args.test_window_bars,
        retrain_every_bars=args.retrain_every_bars,
        seed=args.seed,
    )
    print(json.dumps(summary, indent=2, sort_keys=True))


def _base_pdr_params(params: object) -> PostDrawdownReentryParams:
    if isinstance(params, PostDrawdownReentryParams):
        return params
    if isinstance(params, DefensiveTransitionOverlay):
        return post_drawdown_reentry_params_from_label(params.base_route_label)
    raise ValueError(f"unsupported PDR ML gate route params: {type(params).__name__}")


if __name__ == "__main__":
    main()
