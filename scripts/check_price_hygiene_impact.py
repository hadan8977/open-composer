"""Before/after impact of the 2026-09-17 price-hygiene fix on the one cell
the coordinator named: ``step13_m0b_mom_over_vol63_uni500_k50_gate_off``.

Why this script exists rather than a rerun of ``scripts/run_step13_m_grid.py
--stage m0b``: that stage looks the cell's ``config_hash`` up in the shared
ledger and returns the recorded row instead of recomputing, and it *appends*
to the ledger. This round must not write a ledger line, and must compute the
same cell four ways:

============ ============================== ==============================
variant      ``--daily-root``               ``--hygiene``
============ ============================== ==============================
``before``   the pre-fix feature table      ``off`` (pads gaps, no masking)
``after``    the rebuilt feature table      ``on``
``data_only``the rebuilt feature table      ``off``
``code_only``the pre-fix feature table      ``on``
============ ============================== ==============================

so the difference can be attributed to the data fix (ghost bars dropped in
``features/daily_features.py``) or the code fix (regime-break masking plus
un-padded returns in ``kernel.loop.returns_from_weight_schedule``).

Everything except those two switches is imported from
``scripts/run_step13_m_grid.py`` -- universe/price/regime loading, cash and
benchmark augmentation, the rebalance grid, the cell's own parameters -- so
the numbers cannot diverge from the cell they claim to re-measure for any
reason other than the switch under test. The two panel loaders are rebound
to the requested ``--daily-root`` (both the price panel and the feature
panel, or the run would mix two vintages).

Metrics come from the gate contract's own evaluator with
``reference_only=True`` (no ledger write, no promotion claim): recent-window
(2024-01-02 onward) net CAGR, max drawdown, and vol-matched SPY excess.

Each variant writes its own JSON, and an existing JSON is skipped unless
``--force``, so an interrupted run resumes::

    nohup ./scripts/run_capped.sh --mem 1.8G -- \\
        uv run python scripts/check_price_hygiene_impact.py \\
        --variant before --daily-root data/features/daily_backup_2026-09-17 \\
        --hygiene off > reports/research/control/price-hygiene-impact/before.log 2>&1 &
"""

from __future__ import annotations

import argparse
import importlib
import json
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from open_composer.research.features import panel as panel_mod  # noqa: E402
from open_composer.research.kernel.baseline_strategies import MomentumFactorStrategy  # noqa: E402
from open_composer.research.kernel.loop import (  # noqa: E402
    LAST_PRICE_HYGIENE_MANIFEST,
    build_weight_schedule,
    returns_from_weight_schedule,
)
from open_composer.research.kernel.pick_export import turnover_per_rebalance  # noqa: E402
from open_composer.research.regime import gates as regime_gates  # noqa: E402

m_grid = importlib.import_module("scripts.run_step13_m_grid")

OUT_DIR = ROOT / "reports" / "research" / "control" / "price-hygiene-impact"
#: The cell, verbatim from ``run_step13_m_grid.run_m0b_cell``'s M0b grid.
EXPERIMENT_ID = "step13_m0b_mom_over_vol63_uni500_k50_gate_off"
SCORE_COLUMN = "momentum_252_21_over_vol_63"
UNIVERSE_TOP_N = 500
TOP_K = 50


def _log(message: str) -> None:
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {message}", flush=True)


def _rebind_panel_loaders(daily_root: Path) -> None:
    """Point both loaders at ``daily_root``.

    ``panel.load_price_panel``/``load_feature_panel`` take ``daily_root`` as
    a keyword whose default is bound at definition time, so patching the
    module constant would not work; ``run_step13_m_grid`` imported both names
    into its own namespace, so rebinding them there is what the loaders it
    calls actually resolve.
    """
    m_grid.load_price_panel = lambda **kwargs: panel_mod.load_price_panel(
        daily_root=daily_root, **kwargs
    )
    m_grid.load_feature_panel = lambda *args, **kwargs: panel_mod.load_feature_panel(
        *args, daily_root=daily_root, **kwargs
    )


def run_variant(*, daily_root: Path, hygiene: bool) -> dict[str, Any]:
    _rebind_panel_loaders(daily_root)
    common = m_grid._load_common_data()
    _log("loading M0b feature panel (momentum_252_21 + vol_63, rebalance dates only) ...")
    panel = m_grid.load_feature_panel(
        ["momentum_252_21", "vol_63"],
        ["label_rank_5"],
        dates=common.weekly_dates,
        include_prices=False,
    )
    ratio = panel["momentum_252_21"] / panel["vol_63"]
    panel[SCORE_COLUMN] = ratio.replace([np.inf, -np.inf], np.nan)

    trading_calendar = pd.DatetimeIndex(sorted(common.price_panel["trade_date"].unique()))
    _log(f"building the weight schedule for {EXPERIMENT_ID} ...")
    schedule = build_weight_schedule(
        panel=panel,
        universe_panel=common.universe_panel,
        strategy_factory=lambda: MomentumFactorStrategy(factor_column=SCORE_COLUMN),
        feature_columns=[SCORE_COLUMN],
        label_column="label_rank_5",
        label_horizon_days=5,
        test_years=m_grid.TEST_YEARS,
        top_k=TOP_K,
        hedge="none",
        trading_calendar=trading_calendar,
        train_window_months=m_grid.TRAIN_WINDOW_MONTHS,
        refit_frequency="quarterly",
        universe_top_n=UNIVERSE_TOP_N,
        trend_gate_series=None,
        trend_gate_cash_symbol=m_grid.CASH_SYMBOL,
    )
    price_wide = common.price_panel.pivot(index="trade_date", columns="symbol", values="close")
    open_wide = common.price_panel.pivot(index="trade_date", columns="symbol", values="open")

    _log(f"pricing (price_hygiene_enabled={hygiene}) ...")
    kwargs: dict[str, Any] = {
        "include_hedge": False,
        "execution": "next_open",
        "open_wide": open_wide,
        "price_hygiene_enabled": hygiene,
    }
    primary = returns_from_weight_schedule(
        schedule,
        price_wide,
        common.spy_returns,
        cost_bps_per_side=m_grid.PRIMARY_COST_BPS,
        **kwargs,
    )
    hygiene_manifest = dict(LAST_PRICE_HYGIENE_MANIFEST)
    stress = returns_from_weight_schedule(
        schedule, price_wide, common.spy_returns, cost_bps_per_side=m_grid.STRESS_COST_BPS, **kwargs
    )

    weekly_recent = m_grid._weekly_returns_excluding_cash(
        schedule, primary, recent_start=pd.Timestamp(regime_gates.RECENT_WINDOW_START)
    )
    verdict = regime_gates.evaluate_recent_high_return_candidate(
        experiment_id=EXPERIMENT_ID,
        config_hash=f"price_hygiene_check_{'on' if hygiene else 'off'}",
        full_returns=primary,
        full_stress_returns=stress,
        spy_returns=common.spy_returns,
        bil_returns=common.bil_returns,
        weekly_holding_period_net_returns_recent=weekly_recent,
        rebalances_with_change_per_year=m_grid._rebalances_with_change_per_year(schedule),
        family=m_grid.FAMILY,
        is_ml=False,
        reference_only=True,
    )
    turnover = turnover_per_rebalance(schedule)
    selected = [event for event in schedule if event.selected]
    picks = sorted({symbol for event in selected for symbol in event.selected})
    # Only the masked symbols this book actually held are worth naming.
    masked = set(hygiene_manifest.get("masked_symbols", ()))
    return {
        "experiment_id": EXPERIMENT_ID,
        "daily_root": str(daily_root),
        "price_hygiene_enabled": hygiene,
        "recent_window": [
            verdict.metrics["recent_window_start"],
            verdict.metrics["recent_window_end"],
        ],
        "cagr_recent_net": verdict.metrics["cagr_recent_net"],
        "max_drawdown_recent": verdict.metrics["max_drawdown_recent"],
        "cagr_excess_vol_matched_spy": verdict.metrics["cagr_excess_vol_matched_spy"],
        "vol_match_weight_vs_spy": verdict.metrics["vol_match_weight_vs_spy"],
        "hit_rate_weekly": verdict.metrics["hit_rate_weekly"],
        "stress_cost_recent_cagr_net": verdict.metrics["stress_cost_recent_cagr_net"],
        "full_window_cagr_net": float((1.0 + primary).prod() ** (252.0 / len(primary)) - 1.0),
        "return_rows": int(len(primary)),
        "rebalance_count": len(selected),
        "distinct_symbols_held": len(picks),
        "turnover_per_rebalance_mean": (
            float(np.mean(turnover[1:])) if len(turnover) > 1 else None
        ),
        "held_symbols_masked_by_hygiene": sorted(masked.intersection(picks)),
        "price_hygiene": {
            key: value for key, value in hygiene_manifest.items() if key != "breaks_by_symbol"
        },
        "price_hygiene_breaks_for_held_symbols": {
            symbol: hygiene_manifest.get("breaks_by_symbol", {}).get(symbol)
            for symbol in sorted(masked.intersection(picks))
        },
        "computed_at": pd.Timestamp.now(tz="UTC").isoformat(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--variant", required=True, help="name for the output JSON")
    parser.add_argument("--daily-root", default="data/features/daily")
    parser.add_argument("--hygiene", choices=["on", "off"], required=True)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / f"{args.variant}.json"
    if out_path.exists() and not args.force:
        _log(f"{out_path} exists -- nothing to do (use --force to recompute)")
        print(out_path.read_text())
        return 0

    daily_root = (ROOT / args.daily_root).resolve()
    if not daily_root.is_dir():
        raise SystemExit(f"--daily-root {daily_root} is not a directory")
    _log(f"variant={args.variant} daily_root={daily_root} hygiene={args.hygiene}")
    result = run_variant(daily_root=daily_root, hygiene=args.hygiene == "on")
    tmp = out_path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(result, indent=2, default=str))
    tmp.replace(out_path)
    _log(
        f"{args.variant}: cagr_recent_net={result['cagr_recent_net']:.4f} "
        f"mdd={result['max_drawdown_recent']:.4f} "
        f"vol_matched_spy_excess={result['cagr_excess_vol_matched_spy']:.4f}"
    )
    _log(f"wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
