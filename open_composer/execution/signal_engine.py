"""``SignalEngine``: one ``compute()`` contract for every StrategySpec.

Step 14 plan (``docs/plan-step-14-timeframe-agnostic-bar-cycle-runner-2026-09-11.zh.md``
section 1): ``compute(bars_panel, spec, state, as_of) -> (TargetWeights,
signals, new_state)``. ``scripts/run_bar_cycle.py`` calls this once per new
bar close; every engine below is responsible for its own idempotency (the
runner guarantees it is never called twice for the same bar, but an engine
must still be safe to call with an unchanged ``bars_panel``/``as_of``).

Two engines:

* :class:`ModelRankingSignalEngine` -- a thin wrap over the existing,
  already-tested
  ``open_composer.adapters.execution.model_ranking_target_weights.run_model_ranking_target_weight_mapping``
  (Step 11 Wave C). Stateless/weekly-rebalance: that function already reads
  its own inputs and decides hold-vs-new-signal itself, so this adapter does
  not use ``bars_panel``/``state`` at all and performs no I/O beyond calling
  that one unchanged function.
* :class:`ReversalTrendSignalEngine` -- turns
  ``open_composer.research.regime.reversal_trend_hourly``'s batch (whole
  history, no state) entry/exit/portfolio-admission mechanism into a
  stateful, incremental engine. See its docstring for the design (full
  history recompute + diff-against-persisted-state, not a hand-rolled
  incremental re-simulation) and exactly why that is the *safe* choice here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

import numpy as np
import pandas as pd

from open_composer.config import project_root
from open_composer.engines.signal_engine import build_signal
from open_composer.models.signal import Signal
from open_composer.models.strategy_spec import StrategySpec
from open_composer.research.pine_port.reversal_trend import (
    ReversalTrendParams,
    compute_reversal_trend,
)
from open_composer.research.regime import reversal_trend_hourly as rth

REVERSAL_TREND_BAR_COLUMNS = ("symbol", "timestamp", "bar_close_ts", "open", "high", "low", "close")

#: Sentinel "not yet exited" marker for a currently-open TradeCandidate --
#: strictly after any real bar timestamp this repo's data will ever produce,
#: so admit_by_capacity's "slot frees when a candidate's exit_time passes"
#: rule never frees an unresolved position's slot.
_OPEN_SENTINEL_EXIT_TIME = pd.Timestamp.max.tz_localize("UTC")


@dataclass
class EngineState:
    """Persisted, engine-owned state -- serialized verbatim (as JSON) to
    ``reports/execution/<strategy>-state.json`` by ``scripts/run_bar_cycle.py``;
    this dataclass is just the in-memory shape both the runner and every
    engine share. ``payload`` is engine-specific (opaque to the runner).
    """

    schema_version: int = 1
    engine: str = ""
    #: ISO8601 UTC timestamp of the newest bar this engine has ever acted
    #: on, or ``None`` before the first run. The runner's own idempotency
    #: check also uses this field's BarSource-level counterpart, but each
    #: engine owns and persists its own copy so a fresh engine implementation
    #: can define "acted on" however is correct for it.
    last_bar_close_ts: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "engine": self.engine,
            "last_bar_close_ts": self.last_bar_close_ts,
            "payload": self.payload,
        }

    @classmethod
    def from_json(cls, data: dict[str, Any] | None, *, engine: str) -> EngineState:
        if not data:
            return cls(engine=engine)
        return cls(
            schema_version=int(data.get("schema_version", 1)),
            engine=str(data.get("engine") or engine),
            last_bar_close_ts=data.get("last_bar_close_ts"),
            payload=dict(data.get("payload") or {}),
        )


@dataclass
class TargetWeights:
    """A SignalEngine's current desired book: ``symbol -> weight`` (0..1).
    Generic across portfolio construction styles -- a weekly top-K book, a
    10-slot event-driven book, anything else a future engine adds.
    """

    weights: dict[str, float]
    rebalance_session: str
    signal_session: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ComputeResult:
    #: ``None`` means "nothing changed, do not touch the target-weights
    #: artifact" (the idempotent-no-op case: no new bar since the last run).
    #: A real (possibly empty-book) ``TargetWeights`` means "this is the
    #: current book as of this bar," and the runner writes it.
    target_weights: TargetWeights | None
    signals: list[Signal]
    new_state: EngineState
    #: True when the engine already performed its own artifact I/O (target-
    #: weights JSON + signal log) inside compute() -- currently only
    #: ModelRankingSignalEngine, which wraps an existing, self-contained,
    #: already-tested product function that writes those files itself. The
    #: runner must not redundantly rewrite them for such an engine.
    artifacts_written_by_engine: bool = False
    notes: list[str] = field(default_factory=list)


class SignalEngine(Protocol):
    def compute(
        self,
        bars_panel: pd.DataFrame,
        spec: StrategySpec,
        state: EngineState,
        as_of: pd.Timestamp,
        *,
        root: Path | None = None,
    ) -> ComputeResult: ...


# ---------------------------------------------------------------------------
# ModelRankingSignalEngine
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ModelRankingSignalEngine:
    """Thin SignalEngine wrap over
    ``open_composer.adapters.execution.model_ranking_target_weights.run_model_ranking_target_weight_mapping``.
    ``spec_path`` must point at the same StrategySpec YAML passed to
    ``scripts/run_bar_cycle.py --spec``.
    """

    spec_path: Path
    #: Forwarded verbatim to run_model_ranking_target_weight_mapping; leave
    #: unset in every real invocation (reads the live paper account's
    #: equity from reports/paper/account.json). Exists so tests can pin a
    #: deterministic equity without a fixture account.json.
    account_equity_override: float | None = None

    def compute(
        self,
        bars_panel: pd.DataFrame,
        spec: StrategySpec,
        state: EngineState,
        as_of: pd.Timestamp,
        *,
        root: Path | None = None,
    ) -> ComputeResult:
        from open_composer.adapters.execution.model_ranking_target_weights import (
            run_model_ranking_target_weight_mapping,
        )

        base = root or project_root()
        result = run_model_ranking_target_weight_mapping(
            self.spec_path, base, account_equity_override=self.account_equity_override
        )
        target_weights = TargetWeights(
            weights={},
            rebalance_session="",
            metadata={
                "json_path": str(result.json_path),
                "report_path": str(result.report_path),
                "signal_log_path": str(result.signal_log_path),
                "is_new_signal": result.is_new_signal,
                "signal_count": result.signal_count,
                "target_weight_count": result.target_weight_count,
                "nonzero_target_rows": result.nonzero_target_rows,
                "parity_status": result.parity_status,
                "candidate_is_placeholder": result.candidate_is_placeholder,
            },
        )
        new_state = EngineState(
            engine="model_ranking_portfolio",
            last_bar_close_ts=as_of.isoformat(),
            payload={"last_json_path": str(result.json_path)},
        )
        return ComputeResult(
            target_weights=target_weights,
            # Already appended to signal_logs/model-ranking-{name}.jsonl by
            # the wrapped function -- returning them again here would
            # duplicate them if the runner also logs them.
            signals=[],
            new_state=new_state,
            artifacts_written_by_engine=True,
            notes=[
                f"model_ranking_portfolio: is_new_signal={result.is_new_signal} "
                f"signals_logged={result.signal_count}"
            ],
        )


# ---------------------------------------------------------------------------
# ReversalTrendSignalEngine
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ReversalTrendEngineParams:
    holding_bars: int
    exit_rule: rth.ExitRule
    signal_set: rth.SignalSet
    max_positions: int = rth.MAX_POSITIONS
    position_weight: float = rth.POSITION_WEIGHT

    @classmethod
    def from_spec(cls, spec: StrategySpec) -> ReversalTrendEngineParams:
        """StrategySpec is this repo's source of truth for strategy
        behavior (CLAUDE.md) -- every tunable of this engine is read from
        ``spec.portfolio.event_*`` (validated non-null together by
        ``PortfolioConfig.require_event_driven_fields`` whenever
        ``mode=="event_driven_capacity_book"``), never hardcoded in Python.
        """
        portfolio = spec.portfolio
        if portfolio.mode != "event_driven_capacity_book":
            raise ValueError(
                "reversal_trend_engine requires portfolio.mode=event_driven_capacity_book, "
                f"got {portfolio.mode!r}"
            )
        return cls(
            holding_bars=int(portfolio.event_holding_bars),  # type: ignore[arg-type]
            exit_rule=portfolio.event_exit_rule,  # type: ignore[assignment]
            signal_set=portfolio.event_signal_set,  # type: ignore[assignment]
            max_positions=int(portfolio.event_max_positions),  # type: ignore[arg-type]
            position_weight=float(portfolio.event_position_weight),  # type: ignore[arg-type]
        )


def _entry_signal_mask(indicators: pd.DataFrame, signal_set: rth.SignalSet) -> np.ndarray:
    """The exact same boolean entry mask
    ``reversal_trend_hourly.generate_symbol_candidates`` derives internally
    (its own ``bull_only``/``bull_and_recl`` branch) -- duplicated here
    (rather than imported, since that function does not expose it) only to
    *discover* a still-open pending position that function's own contract
    silently drops at the data's right edge (see its docstring: "drop the
    incomplete trade"). Never used to decide exits -- see module docstring.
    """
    if signal_set == "bull_only":
        return indicators["f_bull"].to_numpy(dtype=bool)
    return (indicators["f_bull"] | indicators["f_recl"]).to_numpy(dtype=bool)


def _trade_key(symbol: str, entry_time: pd.Timestamp) -> str:
    return f"{symbol}|{pd.Timestamp(entry_time).isoformat()}"


def _find_pending_entry(
    symbol: str,
    indicators: pd.DataFrame,
    *,
    signal_set: rth.SignalSet,
    blocked_until_bar: int,
) -> rth.TradeCandidate | None:
    """The single currently-open (unresolved-within-available-data)
    position for ``symbol``, if any -- the same non-pyramiding rule
    ``generate_symbol_candidates`` uses (a symbol holds at most one position
    at a time), applied only to the *first* qualifying signal bar strictly
    after ``blocked_until_bar`` (the last real, closed trade's exit_bar for
    this symbol, or -1 if none). This is deliberately not a general-purpose
    re-simulation of entry/exit: it only ever needs to answer "is there one
    pending position, and if its entry has actually filled yet, at what
    price" -- exit timing for a pending position is never computed here
    (correct by construction: any position generate_symbol_candidates could
    already resolve would already be in its output, not here).
    """
    n = len(indicators)
    if n == 0:
        return None
    signal = _entry_signal_mask(indicators, signal_set)
    candidate_bars = np.flatnonzero(signal)
    eligible = candidate_bars[candidate_bars > blocked_until_bar]
    if eligible.size == 0:
        return None
    signal_bar = int(eligible[0])
    entry_bar = signal_bar + 1
    adx_at_entry = float(indicators["adx"].to_numpy(dtype=float)[signal_bar])
    timestamps = indicators["timestamp"].to_numpy()
    if entry_bar >= n:
        # Signal just fired at the latest available bar's close; the fill
        # (next bar's open) has not happened yet -- no real entry price
        # exists. Represented with entry_bar=-1 as a caller-visible "not
        # filled yet" marker; entry_price/entry_time reference the signal
        # bar's own close/time (decision-time reference, matching this
        # repo's existing convention elsewhere -- e.g.
        # model_ranking_target_weights._build_signals prices a fresh signal
        # at its decision-day close, not a not-yet-observed fill price).
        return rth.TradeCandidate(
            symbol=symbol,
            entry_bar=-1,
            entry_time=pd.Timestamp(timestamps[signal_bar]),
            entry_price=float(indicators["close"].to_numpy(dtype=float)[signal_bar]),
            exit_bar=-1,
            exit_time=_OPEN_SENTINEL_EXIT_TIME,
            exit_price=float("nan"),
            exit_reason="pending",  # type: ignore[arg-type]
            adx_at_entry=adx_at_entry,
        )
    entry_price = float(indicators["open"].to_numpy(dtype=float)[entry_bar])
    return rth.TradeCandidate(
        symbol=symbol,
        entry_bar=entry_bar,
        entry_time=pd.Timestamp(timestamps[entry_bar]),
        entry_price=entry_price,
        exit_bar=-1,
        exit_time=_OPEN_SENTINEL_EXIT_TIME,
        exit_price=float("nan"),
        exit_reason="pending",  # type: ignore[arg-type]
        adx_at_entry=adx_at_entry,
    )


@dataclass(frozen=True)
class ReversalTrendSignalEngine:
    """Stateful, incremental wrap of
    ``open_composer.research.regime.reversal_trend_hourly`` (Step 13-P).

    **Design: full-history recompute + diff-against-state, not a hand-rolled
    incremental re-simulation.** ``compute_reversal_trend``'s indicator/state
    machine (EMA200, RSI dwell counters, arm/lock/cooldown timers) is
    recursive from the true start of a symbol's series and is not designed
    to resume from a serialized mid-series state -- and this engine must
    not modify that module (owned by a different, already-frozen track).
    So every ``compute()`` call re-derives indicators and admitted trades
    over the *entire* available history up to ``as_of`` (cheap at this
    universe's scale: a few hundred symbols x a few thousand hourly bars),
    using the exact same, unmodified
    ``reversal_trend_hourly.generate_symbol_candidates``/``admit_by_capacity``
    the Step 13-P batch backtest uses -- which is what makes incremental-vs-
    batch reconciliation a tautology rather than a hope: the incremental
    engine *is* the batch engine, called repeatedly over a growing window,
    with a thin diff layer converting each call's full result into "what
    changed since last time." Persisted state
    (``admitted_trade_keys``/``open_trade_keys``) exists only to make that
    diff -- and therefore idempotency -- possible; it is never required to
    reproduce a correct *current* result. A lost/corrupted state file is the
    safe failure mode: it re-triggers ``bootstrap`` (below) rather than
    computing a wrong result, so the worst case is "re-absorb history with
    no signals," never a spurious or duplicate signal.

    ``generate_symbol_candidates`` only ever returns *closed* (fully
    resolved) trades -- any position still within its holding window at the
    data's right edge is silently dropped (see that function's own
    docstring). Every currently-open position is therefore *not* discovered
    by that function and needs :func:`_find_pending_entry` (a much smaller,
    lower-risk helper: it only needs the entry-signal mask, not the exit
    simulation) to find it, then included in the same
    ``admit_by_capacity`` capacity-admission pass (via a sentinel
    "never expires" exit time) so a pending/open position competes for
    portfolio slots exactly like a closed one would have.

    **Bootstrap**: on a strategy's first-ever run (no persisted state), the
    full historical admitted-trade set is absorbed into state *without*
    emitting any signals (a fresh connection must not backfill months of
    historical entry/exit signals with today's timestamp) -- only the
    *current* open positions are published as the initial target weights,
    matching this repo's existing "first run establishes the baseline, no
    phantom history" convention (e.g.
    ``model_ranking_target_weights._read_previous_snapshot``).
    """

    def compute(
        self,
        bars_panel: pd.DataFrame,
        spec: StrategySpec,
        state: EngineState,
        as_of: pd.Timestamp,
        *,
        root: Path | None = None,
    ) -> ComputeResult:
        params = ReversalTrendEngineParams.from_spec(spec)
        missing = [c for c in REVERSAL_TREND_BAR_COLUMNS if c not in bars_panel.columns]
        if missing:
            raise ValueError(f"reversal_trend_engine requires columns {missing} in bars_panel")

        prior_last_close = _parse_ts(state.last_bar_close_ts)
        if bars_panel.empty:
            return _no_op_result(state, reason="no bars available")

        latest_bar_close_ts = pd.Timestamp(bars_panel["bar_close_ts"].max())
        if prior_last_close is not None and latest_bar_close_ts <= prior_last_close:
            return _no_op_result(state, reason="no new bar since last run")

        bootstrap = not bool(state.payload.get("bootstrapped", False))

        admitted_now, latest_bar_start = self._recompute_admitted(bars_panel, params)
        now_by_key = {_trade_key(t.symbol, t.entry_time): t for t in admitted_now}
        open_now = {
            key: trade for key, trade in now_by_key.items() if trade.exit_time > latest_bar_start
        }

        previous_open_keys = set(state.payload.get("open_trade_keys") or [])
        previous_admitted_keys = set(state.payload.get("admitted_trade_keys") or [])

        signals: list[Signal] = []
        notes: list[str] = []
        if bootstrap:
            notes.append(
                f"bootstrap: {len(admitted_now)} historical admitted trade(s) absorbed, "
                f"{len(open_now)} currently open, 0 signals emitted"
            )
        else:
            # Diff against *every* trade ever admitted (not just the
            # currently-open set): this call may follow a gap wide enough
            # that a trade both entered and exited since the last call (the
            # runner is only guaranteed to be idempotent/no-op-safe, not
            # guaranteed to be invoked every single bar -- e.g. an --as-of
            # replay stepping day-by-day, or a cron recovering from
            # downtime). Diffing only open_now against the previous open set
            # would silently drop that trade's signals entirely, since it
            # would never appear as "newly open" or "newly closed" in either
            # snapshot.
            new_admitted_keys = sorted(set(now_by_key) - previous_admitted_keys)
            for key in new_admitted_keys:
                trade = now_by_key[key]
                signals.append(_entry_signal(spec, trade, as_of))
                if trade.exit_reason != "pending":
                    # Already resolved by the time we noticed it (whole
                    # lifecycle happened inside the gap since the last call)
                    # -- emit its real, historically-timestamped exit too.
                    signals.append(_exit_signal(spec, trade, as_of, params))
            # Trades that were already known and open last call, and are no
            # longer open now, but were not just-discovered above (their
            # entry was already signaled in an earlier call) -- only the
            # exit is new.
            newly_closed_keys = sorted(
                (previous_open_keys - set(open_now)) - set(new_admitted_keys)
            )
            for key in newly_closed_keys:
                closed_trade = now_by_key.get(key)
                if closed_trade is None or closed_trade.exit_reason == "pending":
                    # Should not happen (a previously-open position that is
                    # no longer open must have resolved into a real closed
                    # candidate this run), but never fabricate an exit
                    # signal from a trade we cannot find/resolve.
                    continue
                signals.append(_exit_signal(spec, closed_trade, as_of, params))
            notes.append(
                f"newly_admitted={len(new_admitted_keys)} newly_closed={len(newly_closed_keys)} "
                f"signals={len(signals)}"
            )

        # Every open (or just-signaled-pending-fill) position counts toward
        # the book at position_weight immediately, matching this repo's
        # existing next_bar_open convention (the target-weights file is the
        # *intended* book as of the decision, not the confirmed-fill book --
        # e.g. model_ranking_target_weights sets to_weight the same way,
        # before its own next-session OPG fill has happened).
        weights = {trade.symbol: params.position_weight for trade in open_now.values()}
        target_weights = TargetWeights(
            weights=weights,
            rebalance_session=latest_bar_start.isoformat(),
            signal_session=latest_bar_close_ts.isoformat(),
            metadata={
                "engine": "reversal_trend_engine",
                "params": {
                    "holding_bars": params.holding_bars,
                    "exit_rule": params.exit_rule,
                    "signal_set": params.signal_set,
                },
                "open_position_count": len(weights),
                "pending_entry_symbols": sorted(
                    trade.symbol for trade in open_now.values() if trade.entry_bar == -1
                ),
                "bootstrap": bootstrap,
            },
        )
        new_state = EngineState(
            engine="reversal_trend_engine",
            last_bar_close_ts=latest_bar_close_ts.isoformat(),
            payload={
                "bootstrapped": True,
                "admitted_trade_keys": sorted(now_by_key),
                "open_trade_keys": sorted(open_now),
                "open_positions": [
                    {
                        "symbol": trade.symbol,
                        "entry_time": trade.entry_time.isoformat(),
                        "entry_price": trade.entry_price,
                        "filled": trade.entry_bar != -1,
                        "adx_at_entry": trade.adx_at_entry,
                    }
                    for trade in open_now.values()
                ],
            },
        )
        return ComputeResult(
            target_weights=target_weights,
            signals=signals,
            new_state=new_state,
            artifacts_written_by_engine=False,
            notes=notes,
        )

    def _recompute_admitted(
        self, bars_panel: pd.DataFrame, params: ReversalTrendEngineParams
    ) -> tuple[list[rth.TradeCandidate], pd.Timestamp]:
        all_candidates: list[rth.TradeCandidate] = []
        latest_bar_start = pd.Timestamp(bars_panel["timestamp"].max())
        sorted_bars = bars_panel.sort_values(["symbol", "timestamp"], kind="mergesort")
        for symbol, group in sorted_bars.groupby("symbol", sort=False):
            ordered = group.reset_index(drop=True)
            indicators = compute_reversal_trend(ordered, ReversalTrendParams())
            closed = rth.generate_symbol_candidates(
                symbol,
                indicators,
                holding_bars=params.holding_bars,
                exit_rule=params.exit_rule,
                signal_set=params.signal_set,
            )
            blocked_until_bar = closed[-1].exit_bar if closed else -1
            pending = _find_pending_entry(
                symbol,
                indicators,
                signal_set=params.signal_set,
                blocked_until_bar=blocked_until_bar,
            )
            all_candidates.extend(closed)
            if pending is not None:
                all_candidates.append(pending)
        admitted = rth.admit_by_capacity(all_candidates, max_positions=params.max_positions)
        return admitted, latest_bar_start


def _entry_signal(spec: StrategySpec, trade: rth.TradeCandidate, as_of: pd.Timestamp) -> Signal:
    from open_composer.strategy_versions import strategy_content_hash

    filled = trade.entry_bar != -1
    return build_signal(
        spec,
        run_id=f"reversal-trend-{spec.name}",
        timestamp=trade.entry_time.to_pydatetime(),
        action="entry",
        source="reversal_trend_engine_observation",
        price=trade.entry_price,
        spec_hash=strategy_content_hash(spec),
        symbol=trade.symbol,
        target_weight=rth.POSITION_WEIGHT,
        conditions=[
            f"adx_at_entry={trade.adx_at_entry:.2f}",
            f"filled={filled}",
            "signal=f_bull|f_recl" if not filled else "fill=next_bar_open",
        ],
    )


def _exit_signal(
    spec: StrategySpec,
    trade: rth.TradeCandidate,
    as_of: pd.Timestamp,
    params: ReversalTrendEngineParams,
) -> Signal:
    from open_composer.strategy_versions import strategy_content_hash

    cost_bps = rth.cost_bps_for_symbol(trade.symbol)
    net_return = rth.net_return(trade.entry_price, trade.exit_price, cost_bps)
    return build_signal(
        spec,
        run_id=f"reversal-trend-{spec.name}",
        timestamp=trade.exit_time.to_pydatetime(),
        action="exit",
        source="reversal_trend_engine_observation",
        price=trade.exit_price,
        spec_hash=strategy_content_hash(spec),
        symbol=trade.symbol,
        target_weight=0.0,
        conditions=[
            f"exit_reason={trade.exit_reason}",
            f"holding_bars={params.holding_bars}",
            f"net_return_after_cost={net_return:.4f}",
        ],
    )


def _parse_ts(value: str | None) -> pd.Timestamp | None:
    if not value:
        return None
    return pd.Timestamp(value)


def _no_op_result(state: EngineState, *, reason: str) -> ComputeResult:
    # target_weights=None: an idempotent no-op must never overwrite the
    # existing reports/execution/<strategy>-target-weights.json with an
    # empty book -- see ComputeResult.target_weights's docstring.
    return ComputeResult(
        target_weights=None,
        signals=[],
        new_state=state,
        artifacts_written_by_engine=False,
        notes=[f"no-op: {reason}"],
    )
