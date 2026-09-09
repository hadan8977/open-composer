"""Step 12 Group B F3: QQQ intraday opening-range momentum, real SIP minute bars.

docs/plan-step-12-groupb-recent-regime-high-hit-rate-2026-09-09.zh.md
section 2 (F3). Coordinator update 2026-09-09 07:40 UTC: F3 runs while
Group A's intraday feature grid is using memory (data volume here -- one
symbol of minute bars -- is moderate enough to run alongside it at
``--mem 1.2G``); F2/F4 wait for that grid to finish.

**Mechanism-reuse note (recorded here because the plan text is internally
inconsistent and a reader deserves to know which half was followed):**
plan section 2 describes F3 in prose as Gao et al. (2018) "first 30 minutes
predicts the last 30 minutes", parameterized by a signal window
({30, 60} minutes), a threshold ({0, 0.2%}), and long-only-vs-long-short
(2x2x2 = 8 cells) -- but the same sentence also says to reuse
``open_composer/research/kernel/mechanisms/intraday_momentum_etf.py``
verbatim, which does not implement that rule at all: it implements
Zarattini/Aziz/Barbon's opening-range noise-band breakout (entry the first
time price clears a volatility-scaled band above the session open, exit on
a trailing stop / hold to close / hold-day cap does not apply here --
same-session exit only), parameterized by
``noise_multiplier x lookback_sessions x use_trailing_stop`` (18 cells,
already preregistered in that file's own ``PARAMETER_SPACE``). Rather than
write a new, untested Gao-2018-style mechanism from scratch under this
week's time budget (higher risk of an undetected bug in new intraday
logic) or silently reinterpret the file to match the prose grid (which
would mean editing a file this plan places outside Group B's ownership
anyway -- ``mechanisms/`` is not in Group B's file list), this script
follows the literal, specific instruction: reuse the named file verbatim,
at its own preregistered 18-cell grid, unmodified. This is a documented
executive decision, not an oversight -- see the Group B report for the
same note.

Bar resolution: the reused function takes whatever intraday bar frame it
is given; the plan's prose mentions a {30, 60}-minute signal window, so
this script fixes 30-minute RTH bars (one value, not a grid dimension --
the reused mechanism's own preregistered grid does not include bar
resolution as a parameter).

Data: ``data/sip/minute`` only covers 2023-2026, so both the 24-month
walk-forward selection lookback and the 2018-2023 disclosure window are
constrained by data availability, not by choice -- see the printed
``warmup_complete_date`` and ``metrics.recent_window_start`` in the output
for the actual (later-than-2024-01-02) window this candidate could be
evaluated over, and the report's honest-shortfall section for the
consequence.

**Mandatory disclosure (plan: "披露 Step 10 §8 记录的模拟盘对等问题"):**
the closest match found in Step 10's plan
(docs/plan-step-10-mechanism-supplementation-2026-09-03.zh.md section 8,
"推迟到下一轮的项目") records that connecting any intraday mechanism to the
paper-trading path requires adding minute-level timeframe support to
``sip_parquet``'s paper-cycle integration first -- that work has not been
done, so F3 has no operational path to paper trading regardless of its
statistical verdict here. Independently (this script's own observation,
not sourced from that section): the reused mechanism's entry rule checks
"at every RTH bar close" and enters "the first time price clears the
band" using that same bar's close as both the trigger and the fill price
-- a real order can only be submitted after observing the close, so any
real fill happens at the next bar's price at the earliest, which is
optimistic by up to one 30-minute bar of price movement on the entry (this
mechanism is flat overnight and exits by the same session's close, so
there is no equivalent overnight-gap risk to disclose, only this intra-
session timing gap). The flat ``cost_bps_per_side`` assumption (2bps
commission-equivalent + 1bps assumed half-spread) is also a single point
estimate, not a stress-tested distribution of the wider spreads that
typically accompany the volatile breakout moments this rule trades on.
These are independent "can this be connected to paper trading" caveats,
not gated by (and not resolved by) the promotion verdict below.

Memory: run via ``./scripts/run_capped.sh --mem 1.2G -- uv run python
scripts/evaluate_groupb_f3_qqq_intraday_momentum.py``.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd

from open_composer.adapters.data.sip_parquet import load_sip_bars
from open_composer.research.kernel.mechanisms.intraday_momentum_etf import (
    PARAMETER_SPACE,
    daily_intraday_momentum_returns,
)
from open_composer.research.kernel.resample import resample_rth_bars
from open_composer.research.regime import etf_pullback_mean_reversion as walkforward
from open_composer.research.regime import gates as regime_gates

EXPERIMENT_ID = "groupb_f3_qqq_intraday_momentum_v1"
ROOT = Path(__file__).resolve().parents[1]
SYMBOL = "QQQ"
TARGET_MINUTES = 30
STRESS_COST_BPS_PER_SIDE = 25.0
#: Max lookback_sessions across PARAMETER_SPACE -- the true warmup floor
#: shared by every cell (a cell with a shorter lookback just gets a few
#: extra usable early sessions than this conservative shared floor).
_MAX_LOOKBACK_SESSIONS = max(cell["lookback_sessions"] for cell in PARAMETER_SPACE)


def _cell_id(index: int) -> str:
    return f"f3_cell{index:03d}"


def _config_hash() -> str:
    payload = {
        "experiment_id": EXPERIMENT_ID,
        "symbol": SYMBOL,
        "target_minutes": TARGET_MINUTES,
        "grid": [_cell_id(i) for i in range(len(PARAMETER_SPACE))],
        "parameter_space": PARAMETER_SPACE,
        "stress_cost_bps_per_side": STRESS_COST_BPS_PER_SIDE,
    }
    blob = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:16]


def _to_session_date_index(series: pd.Series) -> pd.Series:
    """Re-key a tz-aware daily series onto naive-midnight NY-calendar-date
    Timestamps -- the exact convention
    ``daily_intraday_momentum_returns`` uses for its own session index (see
    that function's "session_end" comment). A plain ``.reindex()`` between
    SIP's native tz-aware time-of-day daily index and this mechanism's
    naive-midnight session index would silently fail to match same-calendar-
    day rows otherwise.
    """
    session_dates = [pd.Timestamp(ts.tz_convert("America/New_York").date()) for ts in series.index]
    # UTC-localized (not left naive): open_composer.research.regime.
    # etf_pullback_mean_reversion.materialize_composite reconstructs its
    # quarter boundaries as tz="UTC" Timestamps (correct for F1, whose data
    # was already UTC); daily_intraday_momentum_returns's own session index
    # is naive, so this script UTC-localizes every series it feeds into that
    # shared selection/materialization machinery rather than changing code
    # Group A/F1 already relies on.
    return pd.Series(
        series.to_numpy(),
        index=pd.DatetimeIndex(session_dates).tz_localize("UTC"),
        name=series.name,
    )


def main() -> None:
    print(f"loading SIP minute bars for {SYMBOL} (2023-2026)...", flush=True)
    minute_bars = load_sip_bars(SYMBOL, frequency="minute")
    print(f"  {len(minute_bars)} raw minute rows", flush=True)
    rth_bars = resample_rth_bars(minute_bars, target_minutes=TARGET_MINUTES)
    print(
        f"  resampled to {TARGET_MINUTES}-minute RTH bars: {len(rth_bars)} bars, "
        f"{rth_bars['timestamp'].min()}..{rth_bars['timestamp'].max()}",
        flush=True,
    )
    del minute_bars

    cell_returns: dict[str, pd.Series] = {}
    cell_stress_returns: dict[str, pd.Series] = {}
    for i, params in enumerate(PARAMETER_SPACE):
        cell = _cell_id(i)
        base = daily_intraday_momentum_returns(rth_bars, params)
        stress = daily_intraday_momentum_returns(
            rth_bars, {**params, "cost_bps_per_side": STRESS_COST_BPS_PER_SIDE}
        )
        # UTC-localize: see _to_session_date_index's comment -- the shared
        # materialize_composite/select_cells_by_quarter helpers assume UTC.
        cell_returns[cell] = base.tz_localize("UTC")
        cell_stress_returns[cell] = stress.tz_localize("UTC")
        traded_sessions = int((base != 0.0).sum())
        print(f"  {cell} {params}: {traded_sessions}/{len(base)} sessions traded", flush=True)

    warmup_complete_date = min(
        series.index.min() for series in cell_returns.values()
    ) + pd.DateOffset(
        days=_MAX_LOOKBACK_SESSIONS * 2  # calendar-day pad for a session-count lookback (weekends)
    )
    selection_log = walkforward.select_cells_by_quarter(
        cell_returns, warmup_complete_date=warmup_complete_date, lookback_months=24
    )
    if not selection_log:
        raise SystemExit(
            "no eligible quarter -- 2023-2026 minute data does not span a full "
            "24-month lookback plus a test quarter"
        )
    print(
        f"{len(selection_log)} quarters selected, "
        f"{selection_log[0].quarter_start}..{selection_log[-1].quarter_end}",
        flush=True,
    )
    for selection in selection_log:
        print(
            f"  {selection.quarter_start}..{selection.quarter_end}: "
            f"{selection.selected_cell} (trailing daily Sharpe {selection.trailing_daily_sharpe})",
            flush=True,
        )

    empty_trades = {cell: [] for cell in cell_returns}
    composite_returns, _ = walkforward.materialize_composite(
        cell_returns, empty_trades, selection_log
    )
    composite_stress_returns, _ = walkforward.materialize_composite(
        cell_stress_returns, empty_trades, selection_log
    )

    print("loading BIL daily bars for the benchmark...", flush=True)
    bil_daily = load_sip_bars("BIL", frequency="daily")
    bil_close = pd.Series(
        bil_daily["close"].to_numpy(dtype=float), index=pd.DatetimeIndex(bil_daily["timestamp"])
    ).sort_index()
    bil_returns = _to_session_date_index(bil_close.pct_change().dropna())

    recent_cutoff = pd.Timestamp(regime_gates.RECENT_WINDOW_START, tz="UTC")
    recent_slice = composite_returns.loc[composite_returns.index >= recent_cutoff]
    disclosure_slice = composite_returns.loc[composite_returns.index < recent_cutoff]
    if recent_slice.empty:
        raise SystemExit("no composite sessions on/after the recent-window cutoff")

    # "Holding period" = one RTH session; flat (no-breakout) sessions are the
    # literal 0.0 sentinel daily_intraday_momentum_returns writes for a day
    # it never entered -- plan section 1: "空仓期不计入分母".
    holding_period_recent = [value for value in recent_slice.to_numpy() if value != 0.0]
    holding_period_disclosure = (
        [value for value in disclosure_slice.to_numpy() if value != 0.0]
        if not disclosure_slice.empty
        else None
    )
    if not holding_period_recent:
        raise SystemExit("no traded (nonzero) sessions in the recent gated window")

    config_hash = _config_hash()
    verdict = regime_gates.evaluate_regime_candidate(
        experiment_id=EXPERIMENT_ID,
        config_hash=config_hash,
        full_returns=composite_returns,
        full_stress_returns=composite_stress_returns,
        bil_returns=bil_returns,
        holding_period="daily_or_intraday",
        holding_period_net_returns_recent=holding_period_recent,
        holding_period_net_returns_disclosure=holding_period_disclosure,
        trade_count_recent=len(holding_period_recent),
        # One same-session round trip per traded day; not tracked as a
        # weight-turnover series for this mechanism.
        turnover_annualized_recent=None,
        family=regime_gates.LEDGER_FAMILY,
    )

    print(json.dumps(verdict.model_dump(), indent=2, default=str), flush=True)
    print(
        f"all_gates_pass={verdict.all_gates_pass} promotion_eligible={verdict.promotion_eligible}"
    )

    record = {
        "experiment_id": verdict.experiment_id,
        "config_hash": verdict.config_hash,
        "family": verdict.family,
        "mechanism": "intraday_momentum_etf_opening_range_breakout",
        "mechanism_reuse_note": (
            "plan prose described a Gao-2018 signal-window/threshold/long-short "
            "8-cell grid; the named reused file implements a different, already-"
            "preregistered 18-cell opening-range breakout grid instead -- see "
            "this script's module docstring"
        ),
        "symbol": SYMBOL,
        "target_minutes": TARGET_MINUTES,
        "holding_period": verdict.holding_period,
        "is_ml": verdict.is_ml,
        "reference_only": verdict.reference_only,
        "stress_cost_bps_per_side": STRESS_COST_BPS_PER_SIDE,
        "grid": [_cell_id(i) for i in range(len(PARAMETER_SPACE))],
        "parameter_space": PARAMETER_SPACE,
        "selection_log": [selection.model_dump() for selection in selection_log],
        "paper_trading_parity_caveats": [
            "sip_parquet paper-cycle integration has no minute-level timeframe "
            "support yet (Step 10 plan section 8) -- no operational path to "
            "paper-trade this candidate regardless of verdict",
            "entry rule triggers and fills at the same RTH bar close; a real "
            "order can only fill at the next bar at the earliest (up to one "
            "30-minute bar of optimistic entry timing)",
            "flat 3bp/side cost assumption is a point estimate, not stress-"
            "tested against wider spreads during the volatile breakout moments "
            "this rule trades on",
        ],
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
