"""Tests for open_composer.execution.signal_engine.

Plan: docs/plan-step-14-timeframe-agnostic-bar-cycle-runner-2026-09-11.zh.md
section "Tests required". Two engines:

* ReversalTrendSignalEngine -- covered here with (a) fast, precise synthetic
  unit tests of _find_pending_entry (the one genuinely new piece of entry-
  signal logic this module adds; mirrors tests/test_reversal_trend_hourly_
  mechanism.py's own synthetic-fixture style), and (b) real-local-archive-
  data integration tests (mirrors tests/test_reversal_trend_port.py's
  "@pytest.mark.skipif(not archive present)" convention) for bootstrap,
  idempotency, state-replay equivalence, and pending-vs-batch consistency --
  the properties that matter for a path-dependent incremental engine, not
  hand-verified exact bar indices (compute_reversal_trend's full pipeline is
  too complex to hand-predict signal timing for synthetic OHLCV).
* ModelRankingSignalEngine -- one thin-wrap smoke test with a minimal local
  fixture tree (data/features/daily, data/features/universe, a rule-based
  candidate dir, a model_ranking_portfolio spec), confirming the adapter
  calls the existing, already-tested run_model_ranking_target_weight_mapping
  unchanged and reports back a sane ComputeResult.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest
import yaml

from open_composer.adapters.data.sip_parquet import default_sip_root
from open_composer.execution.bar_source import ArchiveBarSource
from open_composer.execution.signal_engine import (
    EngineState,
    ModelRankingSignalEngine,
    ReversalTrendSignalEngine,
    _find_pending_entry,
)
from open_composer.models.strategy_spec import StrategySpec

# ---------------------------------------------------------------------------
# _find_pending_entry: fast synthetic unit tests
# ---------------------------------------------------------------------------


def _indicator_frame(
    n: int,
    *,
    f_bull: list[int] | None = None,
    f_recl: list[int] | None = None,
    adx: float | list[float] = 25.0,
    close: list[float] | None = None,
    open_: list[float] | None = None,
) -> pd.DataFrame:
    """A minimal synthetic compute_reversal_trend-shaped frame -- only the
    columns _find_pending_entry actually reads (f_bull/f_recl/adx/close/
    open/timestamp), values hand-set rather than derived from real OHLCV
    (mirrors test_reversal_trend_hourly_mechanism.py's own _bars() helper,
    which does the same for generate_symbol_candidates).
    """
    close_values = close if close is not None else [100.0 + i for i in range(n)]
    open_values = open_ if open_ is not None else close_values
    adx_values = [adx] * n if isinstance(adx, (int, float)) else list(adx)
    timestamps = [pd.Timestamp("2024-01-02", tz="UTC") + pd.Timedelta(hours=i) for i in range(n)]
    frame = pd.DataFrame(
        {
            "timestamp": timestamps,
            "open": open_values,
            "close": close_values,
            "adx": adx_values,
            "f_bull": False,
            "f_recl": False,
        }
    )
    for i in f_bull or []:
        frame.loc[i, "f_bull"] = True
    for i in f_recl or []:
        frame.loc[i, "f_recl"] = True
    return frame


def test_find_pending_entry_returns_none_without_a_signal() -> None:
    frame = _indicator_frame(10)
    assert _find_pending_entry("AAA", frame, signal_set="bull_only", blocked_until_bar=-1) is None


def test_find_pending_entry_finds_a_filled_open_position() -> None:
    # Signal at bar 5 of 10 -> entry fills at bar 6's open (a real bar).
    frame = _indicator_frame(10, f_bull=[5])
    pending = _find_pending_entry("AAA", frame, signal_set="bull_only", blocked_until_bar=-1)
    assert pending is not None
    assert pending.entry_bar == 6
    assert pending.entry_price == pytest.approx(frame["open"].iloc[6])
    assert pending.entry_time == frame["timestamp"].iloc[6]
    assert pending.exit_reason == "pending"
    assert pending.exit_bar == -1


def test_find_pending_entry_finds_an_unfilled_signal_at_the_last_bar() -> None:
    # Signal at the very last bar (9 of 10) -> entry_bar=10 does not exist.
    frame = _indicator_frame(10, f_bull=[9])
    pending = _find_pending_entry("AAA", frame, signal_set="bull_only", blocked_until_bar=-1)
    assert pending is not None
    assert pending.entry_bar == -1
    # Reference price/time is the signal bar's own close/time (decision-time
    # reference), not a fabricated future fill.
    assert pending.entry_price == pytest.approx(frame["close"].iloc[9])
    assert pending.entry_time == frame["timestamp"].iloc[9]


def test_find_pending_entry_respects_blocked_until_bar() -> None:
    # Two signals: bar 2 (already closed -> blocked_until_bar=4) and bar 6
    # (should be found); the blocked one must never be returned again.
    frame = _indicator_frame(10, f_bull=[2, 6])
    pending = _find_pending_entry("AAA", frame, signal_set="bull_only", blocked_until_bar=4)
    assert pending is not None
    assert pending.entry_bar == 7  # signal at 6 -> fills at 7


def test_find_pending_entry_bull_and_recl_signal_set() -> None:
    frame = _indicator_frame(10, f_recl=[3])
    none_for_bull_only = _find_pending_entry(
        "AAA", frame, signal_set="bull_only", blocked_until_bar=-1
    )
    assert none_for_bull_only is None
    found = _find_pending_entry("AAA", frame, signal_set="bull_and_recl", blocked_until_bar=-1)
    assert found is not None
    assert found.entry_bar == 4


# ---------------------------------------------------------------------------
# ReversalTrendSignalEngine: real local-archive-data integration tests
# ---------------------------------------------------------------------------

_ARCHIVE_PRESENT = (default_sip_root() / "minute").is_dir()
pytestmark_archive = pytest.mark.skipif(
    not _ARCHIVE_PRESENT, reason="local SIP minute archive (data/sip/minute) is not present"
)

_WINDOW_START = pd.Timestamp("2024-01-02", tz="UTC")
_WINDOW_END = pd.Timestamp("2024-04-30 21:00", tz="UTC")
_UNIVERSE = ["AAPL", "NVDA", "SPY"]


def _reversal_trend_spec(name: str = "test_reversal_trend_1h_h26") -> StrategySpec:
    return StrategySpec.model_validate(
        {
            "name": name,
            "description": "Test-only event_driven_capacity_book spec for engine tests.",
            "timeframe": "1h",
            "universe": _UNIVERSE,
            "lifecycle": "draft",
            "position_direction": "long_only",
            "entry": {"all": ["close > 0"], "any": []},
            "exit": {"all": [], "any": ["close <= 0"]},
            "risk": {
                "max_trades_per_day": 50,
                "max_position_weight": 0.10,
                "stop_loss_pct": None,
                "take_profit_pct": None,
            },
            "portfolio": {
                "mode": "event_driven_capacity_book",
                "event_signal_engine": "reversal_trend_engine",
                "event_holding_bars": 26,
                "event_exit_rule": "time_stop",
                "event_signal_set": "bull_and_recl",
                "event_max_positions": 10,
                "event_position_weight": 0.10,
            },
            "execution": {
                "backend": "python_reference",
                "mode": "manual_signal",
                "signal_on": "bar_close",
                "fill_assumption": "next_bar_open",
                "broker": "none",
            },
            "data": {"source": "alpaca", "feed": "sip"},
        }
    )


@pytest.fixture(scope="module")
def _full_window_bars() -> pd.DataFrame:
    if not _ARCHIVE_PRESENT:
        pytest.skip("local SIP minute archive (data/sip/minute) is not present")
    source = ArchiveBarSource()
    return source.get_bars(_UNIVERSE, "1h", _WINDOW_START, _WINDOW_END, as_of=_WINDOW_END)


@pytestmark_archive
def test_bootstrap_absorbs_history_with_zero_signals(_full_window_bars: pd.DataFrame) -> None:
    spec = _reversal_trend_spec()
    engine = ReversalTrendSignalEngine()
    result = engine.compute(
        _full_window_bars, spec, EngineState(engine="reversal_trend_engine"), _WINDOW_END
    )
    assert result.signals == []
    assert result.target_weights is not None
    assert result.new_state.payload["bootstrapped"] is True
    assert len(result.new_state.payload["admitted_trade_keys"]) > 0
    # Every open position is exactly 10% (event_position_weight), never more.
    for weight in result.target_weights.weights.values():
        assert weight == pytest.approx(0.10)


@pytestmark_archive
def test_idempotent_recall_is_a_harmless_no_op(_full_window_bars: pd.DataFrame) -> None:
    spec = _reversal_trend_spec()
    engine = ReversalTrendSignalEngine()
    first = engine.compute(
        _full_window_bars, spec, EngineState(engine="reversal_trend_engine"), _WINDOW_END
    )
    second = engine.compute(_full_window_bars, spec, first.new_state, _WINDOW_END)
    assert second.signals == []
    assert second.target_weights is None
    assert "no-op" in second.notes[0]
    # A third call, even with a *later* as_of but the same bar data, is still
    # a no-op: no new bar has actually closed.
    third = engine.compute(
        _full_window_bars, spec, second.new_state, _WINDOW_END + pd.Timedelta(hours=1)
    )
    assert third.signals == []
    assert third.target_weights is None


@pytestmark_archive
def test_state_replay_equivalence_chunked_vs_single_bootstrap(
    _full_window_bars: pd.DataFrame,
) -> None:
    """Processing the window bar-by-chunk through the incremental engine
    must reach the exact same final admitted/open trade set as a single
    bootstrap call over the whole window -- the core incremental-vs-batch
    correctness property (this repo's own reconciliation, one level below
    the archive-based Step 13-P reconciliation in the plan doc's item 5,
    which additionally cross-checks against
    reversal_trend_hourly.generate_symbol_candidates directly).
    """
    spec = _reversal_trend_spec()

    single_shot = ReversalTrendSignalEngine().compute(
        _full_window_bars, spec, EngineState(engine="reversal_trend_engine"), _WINDOW_END
    )

    engine = ReversalTrendSignalEngine()
    state = EngineState(engine="reversal_trend_engine")
    chunk_ends = [
        pd.Timestamp("2024-01-31 21:00", tz="UTC"),
        pd.Timestamp("2024-02-29 21:00", tz="UTC"),
        pd.Timestamp("2024-03-31 20:00", tz="UTC"),
        _WINDOW_END,
    ]
    total_signals = 0
    non_bootstrap_calls_with_signals = 0
    for chunk_end in chunk_ends:
        chunk_bars = _full_window_bars.loc[_full_window_bars["bar_close_ts"] <= chunk_end]
        result = engine.compute(chunk_bars, spec, state, chunk_end)
        state = result.new_state
        total_signals += len(result.signals)
        if result.signals:
            non_bootstrap_calls_with_signals += 1

    assert non_bootstrap_calls_with_signals > 0, "expected at least one incremental discovery"
    single_payload = single_shot.new_state.payload
    chunked_payload = state.payload
    assert set(single_payload["admitted_trade_keys"]) == set(chunked_payload["admitted_trade_keys"])
    assert set(single_payload["open_trade_keys"]) == set(chunked_payload["open_trade_keys"])
    assert sorted(t["symbol"] for t in single_payload["open_positions"]) == sorted(
        t["symbol"] for t in chunked_payload["open_positions"]
    )
    # Re-calling with the identical full window is a no-op from here.
    again = engine.compute(_full_window_bars, spec, state, _WINDOW_END)
    assert again.signals == []
    assert again.target_weights is None


@pytestmark_archive
def test_pending_position_matches_full_window_admission(_full_window_bars: pd.DataFrame) -> None:
    """A bars_panel truncated to strictly inside a real trade's holding
    window must report that trade as "open" with the exact same entry
    price/time the full-window batch admission independently computes for
    it -- the specific property that makes pending-position discovery safe
    to trust (see _find_pending_entry's docstring).
    """
    from open_composer.research.pine_port.reversal_trend import (
        ReversalTrendParams,
        compute_reversal_trend,
    )
    from open_composer.research.regime import reversal_trend_hourly as rth

    # Ground truth: SPY's own admitted trades over the full window via the
    # unmodified batch functions directly.
    spy_bars = (
        _full_window_bars.loc[_full_window_bars["symbol"] == "SPY"]
        .sort_values("timestamp")
        .reset_index(drop=True)
    )
    spy_indicators = compute_reversal_trend(spy_bars, ReversalTrendParams())
    spy_trades = rth.generate_symbol_candidates(
        "SPY", spy_indicators, holding_bars=26, exit_rule="time_stop", signal_set="bull_and_recl"
    )
    assert spy_trades, "expected at least one closed SPY trade in the fixture window"
    target_trade = spy_trades[-1]
    # A bar strictly inside the holding window (a handful of bars after
    # entry, still before exit -- time_stop always holds >=1 bar, so +1 is
    # always safely < exit_bar).
    mid_index = min(target_trade.entry_bar + 1, target_trade.exit_bar - 1)
    truncate_at = spy_indicators["bar_close_ts"].iloc[mid_index]

    spec = _reversal_trend_spec()
    truncated = _full_window_bars.loc[_full_window_bars["bar_close_ts"] <= truncate_at]
    result = ReversalTrendSignalEngine().compute(
        truncated, spec, EngineState(engine="reversal_trend_engine"), truncate_at
    )
    open_positions = {p["symbol"]: p for p in result.new_state.payload["open_positions"]}
    assert "SPY" in open_positions
    assert open_positions["SPY"]["entry_price"] == pytest.approx(target_trade.entry_price)
    assert open_positions["SPY"]["entry_time"] == target_trade.entry_time.isoformat()


# ---------------------------------------------------------------------------
# ModelRankingSignalEngine: thin-wrap smoke test with a minimal local fixture
# ---------------------------------------------------------------------------

_MR_UNIVERSE = ["AAA", "BBB", "CCC"]
_MR_SIGNAL_DATE = pd.Timestamp("2026-09-04")  # a Friday


def _write_model_ranking_fixture(root: Path, repo_root: Path) -> Path:
    daily_dir = root / "data" / "features" / "daily"
    daily_dir.mkdir(parents=True, exist_ok=True)
    rows = [
        {
            "symbol": symbol,
            "trade_date": _MR_SIGNAL_DATE,
            "close": 100.0 + i,
            "momentum_252_21": 0.30 - i * 0.05,
            "beta_252_spy": 1.0,
        }
        for i, symbol in enumerate(_MR_UNIVERSE)
    ] + [
        {
            "symbol": "SPY",
            "trade_date": _MR_SIGNAL_DATE,
            "close": 500.0,
            "momentum_252_21": 0.05,
            "beta_252_spy": 0.0,
        }
    ]
    pd.DataFrame(rows).to_parquet(daily_dir / "2026.parquet", index=False)

    universe_dir = root / "data" / "features" / "universe"
    universe_dir.mkdir(parents=True, exist_ok=True)
    universe_rows = [
        {
            "month_end": _MR_SIGNAL_DATE,
            "symbol": symbol,
            "adv_rank": rank + 1,
            "dollar_adv": 1_000_000.0 - rank,
            "close": 100.0 + rank,
        }
        for rank, symbol in enumerate(_MR_UNIVERSE)
    ]
    pd.DataFrame(universe_rows).to_parquet(universe_dir / "2026.parquet", index=False)

    candidate_dir = root / "candidates" / "test_momentum_placeholder"
    candidate_dir.mkdir(parents=True, exist_ok=True)
    shared = {
        "experiment_id": "test_momentum_placeholder",
        "family": "test_b1_momentum",
        "model_kind": "rule_momentum_top_k",
        "feature_set": "daily_only",
        "feature_columns": ["momentum_252_21"],
        "top_k": 2,
        "hedge": "none",
        "train_row_dates": "rule_based_no_training",
    }
    (candidate_dir / "config.json").write_text(
        json.dumps({**shared, "label_horizon_days": 21, "score_column": "momentum_252_21"}),
        encoding="utf-8",
    )
    (candidate_dir / "features.json").write_text(
        json.dumps(
            {
                **shared,
                "label_column": "label_rank_21",
                "label_horizon_days": 21,
                "execution": "close_marked",
                "refit_through_date": None,
            }
        ),
        encoding="utf-8",
    )

    fixture = (
        repo_root / "tests" / "fixtures" / "strategy_specs" / "drafts" / "fixture_pullback_15m.yaml"
    )
    raw = yaml.safe_load(fixture.read_text(encoding="utf-8"))
    raw.update(
        {
            "name": "test_model_ranking_engine_wrap",
            "timeframe": "daily",
            "universe": _MR_UNIVERSE,
            "portfolio": {
                "mode": "model_ranking_portfolio",
                "candidate_artifact_dir": candidate_dir.relative_to(root).as_posix(),
                "universe_rule": "pit_adv_top_n",
                "universe_top_n": 5,
                "feature_set_id": "daily_only",
                "label_horizon_days": 21,
                "top_k": 2,
                "rebalance": "weekly_friday_close_monday_open",
                "weighting": "equal_weight",
                "hedge": "none",
            },
        }
    )
    raw["risk"]["max_position_weight"] = 0.5
    raw["data"]["source"] = "alpaca"
    raw["data"]["path"] = None
    raw["data"]["feed"] = "sip"
    spec_path = root / "test_model_ranking_engine_wrap.yaml"
    spec_path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
    StrategySpec.model_validate(yaml.safe_load(spec_path.read_text(encoding="utf-8")))
    return spec_path


def test_model_ranking_signal_engine_wraps_the_existing_function(
    tmp_path: Path, repo_root: Path
) -> None:
    spec_path = _write_model_ranking_fixture(tmp_path, repo_root)
    spec = StrategySpec.model_validate(yaml.safe_load(spec_path.read_text(encoding="utf-8")))

    engine = ModelRankingSignalEngine(spec_path=spec_path, account_equity_override=100_000.0)
    result = engine.compute(
        pd.DataFrame(),  # unused by this engine -- self-contained I/O
        spec,
        EngineState(engine="model_ranking_portfolio"),
        pd.Timestamp(_MR_SIGNAL_DATE, tz="UTC"),
        root=tmp_path,
    )
    assert result.artifacts_written_by_engine is True
    assert result.target_weights is not None
    assert result.target_weights.metadata["is_new_signal"] is True
    target_weights_path = tmp_path / "reports" / "execution" / f"{spec.name}-target-weights.json"
    assert target_weights_path.is_file()
    payload = json.loads(target_weights_path.read_text(encoding="utf-8"))
    held = [row for row in payload["target_weights"] if row["selected"]]
    assert len(held) == 2  # top_k=2
    signal_log_path = tmp_path / "signal_logs" / f"model-ranking-{spec.name}.jsonl"
    assert signal_log_path.is_file()

    # Re-invoking the engine for the same signal_date is the existing
    # function's own hold-day behavior (unchanged) -- not a new signal.
    again = engine.compute(
        pd.DataFrame(),
        spec,
        result.new_state,
        pd.Timestamp(_MR_SIGNAL_DATE, tz="UTC"),
        root=tmp_path,
    )
    assert again.target_weights is not None
    assert again.target_weights.metadata["is_new_signal"] is False
