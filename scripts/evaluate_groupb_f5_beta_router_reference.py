"""Step 12 Group B F5: QQQ/TQQQ/QLD/BIL beta-router reference, real SIP bars.

docs/plan-step-12-groupb-recent-regime-high-hit-rate-2026-09-09.zh.md
section 2 (F5) and section 3 (Wednesday 2026-09-09 22:00 UTC deadline).

F5 is a leveraged reference item, never a promotion candidate (plan: "参考
项（不参与晋级）"): this script still runs it through
``open_composer.research.regime.gates.evaluate_regime_candidate`` (with
``reference_only=True``, which forces ``promotion_eligible`` to ``False``
regardless of gate outcomes) purely so its numbers are reported on the
exact same metric definitions as F1-F4, for the "high recent CAGR but
bigger drawdown" side-by-side comparison the plan asks for.

Holding-period definition for hit rate/profit factor: unlike F1 (discrete
trades with genuine flat/BIL-only periods excluded from the denominator),
this router is *always* invested in exactly one of {BIL, QQQ, QLD, TQQQ}
and re-evaluates weekly, so there is no "flat" period to exclude -- every
calendar week is a holding period. hit rate/profit factor here are
therefore computed over weekly-compounded returns, not per-trade returns.

Memory: run via ``./scripts/run_capped.sh --mem 0.6G -- uv run python
scripts/evaluate_groupb_f5_beta_router_reference.py`` (4 symbols of daily
bars, well inside Step 12's current 0.6G constraint while Group A's grid runs).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd

from open_composer.adapters.data.sip_parquet import load_sip_bars
from open_composer.research.regime import beta_router_reference as f5
from open_composer.research.regime import gates as regime_gates

EXPERIMENT_ID = "groupb_f5_beta_router_reference_v1"
ROOT = Path(__file__).resolve().parents[1]


def _config_hash() -> str:
    payload = {
        "experiment_id": EXPERIMENT_ID,
        "symbols": list(f5.SYMBOLS),
        "signal_parameters": f5.SIGNAL_PARAMETERS,
        "cost_bps_per_side": f5.COST_BPS_PER_SIDE,
        "stress_cost_bps_per_side": f5.STRESS_COST_BPS_PER_SIDE,
    }
    blob = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:16]


def _weekly_returns(daily_returns: pd.Series) -> list[float]:
    weekly = daily_returns.groupby(pd.PeriodIndex(daily_returns.index, freq="W")).apply(
        lambda window: float((1.0 + window).prod() - 1.0)
    )
    return weekly.tolist()


def main() -> None:
    print(f"loading SIP daily bars for {list(f5.SYMBOLS)}...", flush=True)
    raw = load_sip_bars(list(f5.SYMBOLS), frequency="daily")
    closes: dict[str, pd.Series] = {}
    opens: dict[str, pd.Series] = {}
    for symbol in f5.SYMBOLS:
        rows = raw.loc[raw["symbol"] == symbol].sort_values("timestamp")
        index = pd.DatetimeIndex(rows["timestamp"])
        closes[symbol] = pd.Series(rows["close"].to_numpy(dtype=float), index=index)
        opens[symbol] = pd.Series(rows["open"].to_numpy(dtype=float), index=index)

    base_returns = f5.simulate_beta_router(closes, opens, cost_bps_per_side=f5.COST_BPS_PER_SIDE)
    stress_returns = f5.simulate_beta_router(
        closes, opens, cost_bps_per_side=f5.STRESS_COST_BPS_PER_SIDE
    )
    print(
        f"router return stream: {base_returns.index.min().date()}.."
        f"{base_returns.index.max().date()}, {len(base_returns)} sessions",
        flush=True,
    )

    bil_returns = closes["BIL"].pct_change().dropna()

    recent_cutoff = pd.Timestamp(regime_gates.RECENT_WINDOW_START, tz="UTC")
    recent_slice = base_returns.loc[base_returns.index >= recent_cutoff]
    disclosure_slice = base_returns.loc[base_returns.index < recent_cutoff]
    if recent_slice.empty:
        raise SystemExit("no recent-window data for the beta router reference")

    holding_period_recent = _weekly_returns(recent_slice)
    holding_period_disclosure = (
        _weekly_returns(disclosure_slice) if not disclosure_slice.empty else None
    )

    config_hash = _config_hash()
    verdict = regime_gates.evaluate_regime_candidate(
        experiment_id=EXPERIMENT_ID,
        config_hash=config_hash,
        full_returns=base_returns,
        full_stress_returns=stress_returns,
        bil_returns=bil_returns,
        holding_period="weekly",
        holding_period_net_returns_recent=holding_period_recent,
        holding_period_net_returns_disclosure=holding_period_disclosure,
        # No discrete trade count for a continuously-invested weekly router
        # (it never sits flat -- it always holds one of BIL/QQQ/QLD/TQQQ);
        # leaving this None keeps the ledger's trade_count_* fields honest
        # rather than mislabeling "weeks evaluated" as "trades".
        trade_count_recent=None,
        turnover_annualized_recent=None,
        family=regime_gates.LEDGER_FAMILY,
        reference_only=True,
    )

    print(json.dumps(verdict.model_dump(), indent=2, default=str), flush=True)
    print(
        f"all_gates_pass={verdict.all_gates_pass} "
        f"promotion_eligible={verdict.promotion_eligible} (forced False: reference_only)"
    )

    record = {
        "experiment_id": verdict.experiment_id,
        "config_hash": verdict.config_hash,
        "family": verdict.family,
        "mechanism": "beta_router_reference_vol02_ported",
        "symbols": list(f5.SYMBOLS),
        "holding_period": verdict.holding_period,
        "is_ml": verdict.is_ml,
        "reference_only": verdict.reference_only,
        "cost_bps_per_side": f5.COST_BPS_PER_SIDE,
        "stress_cost_bps_per_side": f5.STRESS_COST_BPS_PER_SIDE,
        "signal_parameters": f5.SIGNAL_PARAMETERS,
        "dsr_trial_count": verdict.dsr_trial_count,
        "metrics": verdict.metrics,
        "disclosure": verdict.disclosure,
        "gate_results": verdict.gate_results,
        "gates_not_applicable": list(verdict.gates_not_applicable),
        "all_gates_pass": verdict.all_gates_pass,
        "promotion_eligible": verdict.promotion_eligible,
        "gates_provenance": verdict.gates_provenance,
        "gate_contract": verdict.gate_contract,
        "recorded_at": pd.Timestamp.now(tz="UTC").isoformat(),
    }
    appended = regime_gates.append_ledger(record)
    print(f"ledger appended: {appended} -> {regime_gates.LEDGER_PATH}")


if __name__ == "__main__":
    main()
