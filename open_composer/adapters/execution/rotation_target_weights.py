"""``portfolio.mode=etf_rotation_portfolio`` -> target weights.

A periodically rescored, equal-weight, long-only rotation across a fixed
menu of ETFs (``ETFRotationConfig`` -- see
``open_composer.models.strategy_spec``). Observation-side adapter: it never
submits broker orders. It writes the same
``reports/execution/{name}-target-weights.json`` shape every other
target-weight adapter writes
(:func:`open_composer.adapters.execution.router_target_weights.write_router_execution_artifacts`),
sized to whole shares against the live paper account equity
(:func:`open_composer.adapters.execution.whole_share_sizing.size_whole_share_portfolio`).

Selection rule
--------------
1. Load each menu symbol's (and the cash symbol's) daily close from
   ``data/sip/daily/{year}/*.parquet`` (:func:`load_price_panel`), dropping
   vendor ghost bars (``volume<=0 AND trade_count<=0``).
2. ``latest_session`` = the most recent bar date for the cash symbol, bounded
   by ``as_of`` when given.
3. ``signal_session`` = the most recent rebalance date on/before
   ``latest_session`` (:func:`resolve_signal_session`) -- the last
   *available* session of the calendar month or ISO week, so recomputing on
   a later day inside the same period returns the identical date. That is
   what keeps a daily cron idempotent: the book only changes when the period
   actually rolls over, never just because the adapter ran again.
4. Each menu symbol is scored as the mean simple return over
   ``lookbacks`` sessions, counted along *that symbol's own* trading-day
   index (:func:`score_symbol`) -- two symbols with different halt/listing
   histories can have a different bar at "N sessions back" for the same
   ``signal_session``. A symbol lacking the bar at ``signal_session``, a
   required lookback bar, or ``min_history_sessions`` of history is
   ineligible and recorded with a reason rather than raising.
5. The top ``top_n`` eligible scorers are picked (:func:`select_book`); when
   ``absolute_momentum_filter`` is set, a pick whose score does not exceed
   the cash symbol's own score (computed the same way) is dropped to cash.
   Each surviving pick gets ``1/top_n``; every remaining weight (including a
   fully-empty book) goes to ``cash_symbol`` (:func:`build_weights`).
6. Sizing equity is ``min(notional_budget_usd, account_equity)`` when
   ``etf_rotation.notional_budget_usd`` is set, else the full account
   equity -- several rotation sleeves can share one paper account, each
   capped at its own dollar budget. Both the raw account equity and the
   equity actually used for sizing are recorded in the artifact ``summary``
   under distinct keys.

This module is deliberately much smaller than
``insider_portfolio_target_weights.py``: there is no forward-ledger/
preregistration ceremony and no persisted hold-state, because determinism
of ``signal_session`` (step 3) is already enough to make a same-period
rerun idempotent.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

from open_composer.adapters.execution.rotation_overlay import (
    OverlayDecision,
    apply_multiplier,
    decide_overlay,
    held_symbols,
    sleeve_equity_curve,
)
from open_composer.adapters.execution.router_target_weights import (
    infer_acquisition_tier,
    write_router_execution_artifacts,
)
from open_composer.adapters.execution.whole_share_sizing import size_whole_share_portfolio
from open_composer.engines.signal_engine import build_signal
from open_composer.market_calendar import next_us_equity_session, us_equity_session_dates
from open_composer.models.strategy_spec import StrategySpec, load_strategy_spec
from open_composer.storage import append_jsonl, model_to_record
from open_composer.strategy_versions import strategy_content_hash

#: Hard memory/thread budget for this adapter's DuckDB reads (3.9GB box,
#: other jobs may be running concurrently) -- see module brief.
DEFAULT_MEMORY_LIMIT = "600MB"
DEFAULT_THREADS = 2
MAPPING_MODE = "etf_rotation_portfolio_target_weight_mapping"
SOURCE_TAG = "etf_rotation_portfolio_python_reference"
TIME_RULE = "next_regular_session_opg_limit"
SIGNAL_SOURCE = "etf_rotation_portfolio_observation"


@dataclass(frozen=True)
class RotationTargetWeightResult:
    report_path: Path
    target_weights_path: Path
    parity_status: str
    rebalance_sessions: int
    target_weight_count: int
    nonzero_target_rows: int
    signal_log_path: Path
    signal_count: int
    manifest: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ScoreResult:
    score: float | None
    reason: str | None


# ---------------------------------------------------------------------------
# pure scoring / calendar helpers


def score_symbol(
    dates: Sequence[date],
    closes: Mapping[date, float],
    *,
    signal_session: date,
    lookbacks: Sequence[int],
    min_history_sessions: int,
) -> ScoreResult:
    """Mean simple return over ``lookbacks`` sessions, counted along this
    symbol's own trading-day index (not calendar days), anchored at
    ``signal_session``. Pure; never raises -- ineligibility is returned as a
    reason string."""
    ordered = sorted(dates)
    try:
        idx = ordered.index(signal_session)
    except ValueError:
        return ScoreResult(None, "no bar at signal_session")
    if idx + 1 < min_history_sessions:
        return ScoreResult(
            None,
            f"insufficient history: {idx + 1} session(s) on/before signal_session "
            f"(need >= {min_history_sessions})",
        )
    current = closes.get(signal_session)
    if current is None or current <= 0:
        return ScoreResult(None, "missing or non-positive close at signal_session")
    returns: list[float] = []
    for lookback in lookbacks:
        back_idx = idx - int(lookback)
        if back_idx < 0:
            return ScoreResult(
                None, f"missing lookback bar: {lookback} session(s) before signal_session"
            )
        base_close = closes.get(ordered[back_idx])
        if base_close is None or base_close <= 0:
            return ScoreResult(
                None, f"missing lookback close: {lookback} session(s) before signal_session"
            )
        returns.append(current / base_close - 1.0)
    return ScoreResult(sum(returns) / len(returns), None)


def _last_day_of_month(day: date) -> date:
    if day.month == 12:
        next_month_start = date(day.year + 1, 1, 1)
    else:
        next_month_start = date(day.year, day.month + 1, 1)
    return next_month_start - timedelta(days=1)


def _last_day_of_iso_week(day: date) -> date:
    return day + timedelta(days=7 - day.isoweekday())


def _no_trading_day_after(day: date, period_end: date) -> bool:
    """True iff the real US-equity market calendar has no trading day in
    ``(day, period_end]`` -- i.e. ``day`` is the last session of a period
    that has actually finished, regardless of what the archive happens to
    contain. Uses ``open_composer.market_calendar`` (a fixed holiday
    calendar), never the loaded price panel, which is exactly what makes
    this immune to "today's row is the newest one in the archive" false
    positives on a mid-period cron run."""
    if day >= period_end:
        return True
    return len(us_equity_session_dates(day + timedelta(days=1), period_end)) == 0


@lru_cache(maxsize=8192)
def _is_period_end_month(day: date) -> bool:
    return _no_trading_day_after(day, _last_day_of_month(day))


@lru_cache(maxsize=8192)
def _is_period_end_week(day: date) -> bool:
    return _no_trading_day_after(day, _last_day_of_iso_week(day))


def resolve_signal_session(
    available_dates: Sequence[date], rebalance: str, latest_session: date
) -> date:
    """The most recent rebalance date on/before ``latest_session``: a session
    ``d`` qualifies only when the *real* US-equity market calendar has no
    trading day after ``d`` inside the same calendar month
    (``monthly_last_session``) or ISO week (``weekly_friday``) --
    :func:`_is_period_end_month` / :func:`_is_period_end_week`.

    This must be decided from the market calendar, not from "the latest date
    the archive happens to contain": on a Wednesday, the newest row in the
    archive *is* that week's newest available row, so treating "latest
    available in the group" as the rebalance date would rebalance every
    single day. Deciding period-completion from the calendar instead is what
    makes a same-period rerun idempotent -- the candidate set does not
    change just because another (still mid-period) day's bar arrived.
    """
    bounded = sorted(day for day in available_dates if day <= latest_session)
    if rebalance == "monthly_last_session":
        candidates = [day for day in bounded if _is_period_end_month(day)]
    elif rebalance == "weekly_friday":
        candidates = [day for day in bounded if _is_period_end_week(day)]
    else:
        raise ValueError(f"unsupported etf_rotation.rebalance: {rebalance!r}")
    if not candidates:
        raise ValueError(f"no {rebalance!r} candidate session on/before {latest_session}")
    return candidates[-1]


def select_book(
    scores: Mapping[str, float],
    *,
    top_n: int,
    cash_score: float | None,
    absolute_momentum_filter: bool,
) -> tuple[list[str], list[str]]:
    """Top-``top_n`` eligible scorers (ties broken by symbol ascending),
    optionally thinned by the absolute-momentum filter. Returns
    ``(picks, dropped_by_filter)``; ``picks + dropped_by_filter`` is always
    the pre-filter top-``top_n`` list. Pure."""
    ranked = sorted(scores.items(), key=lambda item: (-item[1], item[0]))
    pre_filter = [symbol for symbol, _ in ranked[: max(int(top_n), 0)]]
    if not absolute_momentum_filter:
        return pre_filter, []
    survivors: list[str] = []
    dropped: list[str] = []
    for symbol in pre_filter:
        if cash_score is not None and scores[symbol] <= cash_score:
            dropped.append(symbol)
        else:
            survivors.append(symbol)
    return survivors, dropped


def build_weights(
    picks: Sequence[str],
    *,
    top_n: int,
    cash_symbol: str,
    unfilled_slot_policy: str = "cash",
) -> dict[str, float]:
    """Weights for the surviving picks, plus whatever is left in cash. Pure.

    ``unfilled_slot_policy="cash"`` gives each pick ``1/top_n`` and leaves a
    dropped pick's slot in ``cash_symbol``, so a two-slot book with one
    survivor is 50% invested.

    ``unfilled_slot_policy="renormalize_survivors"`` equal-weights the
    survivors among themselves, so the same book is 100% in the single
    survivor and cash appears only when nothing survives. This is what the
    preregistered grid on card H-20260918-05 measured, and it is deliberately
    not the default: it concentrates risk precisely when the absolute-momentum
    filter is warning, which is the most expensive behaviour in a real
    downturn.

    An empty book is 100% ``cash_symbol`` under either policy.
    """
    if not picks:
        return {cash_symbol: 1.0}
    if unfilled_slot_policy == "renormalize_survivors":
        weight_each = 1.0 / len(picks)
        weights = {symbol: weight_each for symbol in picks}
        weights[cash_symbol] = 0.0
        return weights
    if unfilled_slot_policy != "cash":
        raise ValueError(f"unknown unfilled_slot_policy: {unfilled_slot_policy!r}")
    weight_each = 1.0 / int(top_n)
    weights = {symbol: weight_each for symbol in picks}
    remainder = 1.0 - weight_each * len(picks)
    weights[cash_symbol] = remainder if remainder > 1e-9 else 0.0
    return weights


def resolve_sizing_equity(
    account_equity: float, notional_budget_usd: float | None
) -> tuple[float, bool, bool]:
    """``(sizing_equity, notional_budget_configured, notional_budget_binds)``.

    Several rotation sleeves can share one paper account, so each is sized
    against ``min(notional_budget_usd, account_equity)`` rather than the
    whole account when a per-strategy dollar budget is configured."""
    if notional_budget_usd is None:
        return float(account_equity), False, False
    budget = float(notional_budget_usd)
    sizing_equity = min(budget, float(account_equity))
    binds = sizing_equity < float(account_equity) - 1e-9
    return sizing_equity, True, binds


# ---------------------------------------------------------------------------
# data loading


def _year_dirs(root: Path, years: Sequence[int]) -> list[Path]:
    daily_root = root / "data" / "sip" / "daily"
    return [daily_root / str(year) for year in years if (daily_root / str(year)).is_dir()]


def load_price_panel(
    root: Path,
    symbols: Sequence[str],
    years: Sequence[int],
    *,
    memory_limit: str = DEFAULT_MEMORY_LIMIT,
    threads: int = DEFAULT_THREADS,
) -> pd.DataFrame:
    """One row per ``(symbol, trade_date)`` with that day's open and close, read from
    ``data/sip/daily/{year}/*.parquet`` for ``years`` and ``symbols`` only.
    Vendor ghost bars (``volume<=0 AND trade_count<=0``) are dropped before
    a duplicate-timestamp day is collapsed to its latest bar. Runs under a
    ``memory_limit``/``threads`` cap (default 600MB / 2 threads -- the box
    has 3.9GB total and other jobs may be running)."""
    dirs = _year_dirs(root, years)
    if not dirs:
        raise ValueError(f"no data/sip/daily year directory for {sorted(years)} under {root}")
    globs = [str(directory / "*.parquet") for directory in dirs]
    wanted = sorted({str(symbol).upper() for symbol in symbols if str(symbol).strip()})
    if not wanted:
        return pd.DataFrame(columns=["symbol", "trade_date", "open", "close"])
    con = duckdb.connect()
    try:
        con.execute(f"SET memory_limit='{memory_limit}'")
        con.execute(f"SET threads={int(threads)}")
        con.execute("SET TimeZone='UTC'")
        con.register("wanted_symbols", pd.DataFrame({"symbol": wanted}))
        frame = con.execute(
            f"""
            WITH bars AS (
                SELECT symbol, CAST(timestamp AS DATE) AS trade_date, timestamp,
                       open, close, volume, trade_count
                FROM read_parquet({globs!r}, union_by_name=true)
                WHERE symbol IN (SELECT symbol FROM wanted_symbols)
            ),
            clean AS (
                SELECT * FROM bars
                WHERE NOT (COALESCE(volume, 0) <= 0 AND COALESCE(trade_count, 0) <= 0)
            ),
            ranked AS (
                SELECT *, ROW_NUMBER() OVER (
                    PARTITION BY symbol, trade_date ORDER BY timestamp DESC
                ) AS rn
                FROM clean
            )
            SELECT symbol, trade_date, open, close FROM ranked WHERE rn = 1
            """,  # noqa: S608
        ).fetchdf()
    finally:
        con.close()
    frame["symbol"] = frame["symbol"].astype(str).str.upper()
    frame["trade_date"] = pd.to_datetime(frame["trade_date"]).dt.date
    frame["close"] = frame["close"].astype(float)
    frame["open"] = frame["open"].astype(float)
    return frame.sort_values(["symbol", "trade_date"]).reset_index(drop=True)


def _symbol_series(panel: pd.DataFrame, symbol: str) -> tuple[list[date], dict[date, float]]:
    rows = panel.loc[panel["symbol"] == symbol]
    dates = list(rows["trade_date"])
    closes = dict(zip(rows["trade_date"], rows["close"], strict=True))
    return dates, closes


def _resolve_account_equity(root: Path, override: float | None) -> tuple[float, str | None, str]:
    if override is not None:
        return float(override), None, "account_equity_override"
    account_path = root / "reports" / "paper" / "account.json"
    if not account_path.is_file():
        raise ValueError(
            "etf_rotation_portfolio sizing needs a live account-equity snapshot; run "
            "`oc paper sync-account` first (reports/paper/account.json is missing)."
        )
    payload = json.loads(account_path.read_text(encoding="utf-8"))
    equity = payload.get("equity")
    if equity is None or float(equity) <= 0:
        raise ValueError(f"reports/paper/account.json has no positive 'equity' field: {payload}")
    return float(equity), payload.get("generated_at"), "reports/paper/account.json"


def _sleeve_fills(root: Path, strategy_name: str) -> list[dict[str, Any]]:
    """This sleeve's paper fills ledger, the file
    ``open_composer.paper_rehearsal.rehearsal_fills_path`` names (read here
    directly so the observation adapter does not import the broker module).
    Missing file = nothing has filled yet."""
    path = root / "reports" / "paper" / "rehearsal" / f"{strategy_name}-fills.jsonl"
    if not path.is_file():
        return []
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def _close_frame(panel: pd.DataFrame, latest_session: date) -> pd.DataFrame:
    frame = panel.loc[panel["trade_date"] <= latest_session]
    return frame.pivot(index="trade_date", columns="symbol", values="close").sort_index()


def replay_books(
    series: Mapping[str, tuple[list[date], dict[date, float]]],
    sessions: Sequence[date],
    *,
    menu: Sequence[str],
    cash_symbol: str,
    lookbacks: Sequence[int],
    top_n: int,
    rebalance: str,
    absolute_momentum_filter: bool,
    min_history_sessions: int,
    unfilled_slot_policy: str,
) -> tuple[pd.DataFrame, list[date]]:
    """The unscaled book live from each session's open, rebuilt with this
    module's own selection rule at every rebalance close in ``sessions``;
    before the first rebalance, and whenever the cash symbol cannot be
    scored, the book is all cash. Returns ``(weights, rebalance_sessions)``."""
    period_end = _is_period_end_month if rebalance == "monthly_last_session" else None
    if rebalance == "weekly_friday":
        period_end = _is_period_end_week
    if period_end is None:
        raise ValueError(f"unsupported etf_rotation.rebalance: {rebalance!r}")
    signal_sessions = [day for day in sessions if period_end(day)]
    cash_dates, cash_closes = series[cash_symbol]
    position = {day: i for i, day in enumerate(sessions)}
    changes: dict[int, dict[str, float]] = {}
    for day in signal_sessions:
        scores: dict[str, float] = {}
        for symbol in menu:
            dates, closes = series[symbol]
            result = score_symbol(
                dates,
                closes,
                signal_session=day,
                lookbacks=lookbacks,
                min_history_sessions=min_history_sessions,
            )
            if result.reason is None:
                scores[symbol] = float(result.score)  # type: ignore[arg-type]
        cash_result = score_symbol(
            cash_dates,
            cash_closes,
            signal_session=day,
            lookbacks=lookbacks,
            min_history_sessions=min_history_sessions,
        )
        if absolute_momentum_filter and cash_result.reason is not None:
            book = {cash_symbol: 1.0}
        else:
            picks, _ = select_book(
                scores,
                top_n=top_n,
                cash_score=cash_result.score,
                absolute_momentum_filter=absolute_momentum_filter,
            )
            book = build_weights(
                picks,
                top_n=top_n,
                cash_symbol=cash_symbol,
                unfilled_slot_policy=unfilled_slot_policy,
            )
        if position[day] + 1 < len(sessions):
            changes[position[day] + 1] = book
    columns = sorted({*menu, cash_symbol})
    current: dict[str, float] = {cash_symbol: 1.0}
    rows: list[dict[str, float]] = []
    for i in range(len(sessions)):
        current = changes.get(i, current)
        rows.append(dict(current))
    weights = pd.DataFrame(rows, index=list(sessions)).reindex(columns=columns).fillna(0.0)
    return weights, signal_sessions


def _decide_overlay(
    panel: pd.DataFrame,
    series: Mapping[str, tuple[list[date], dict[date, float]]],
    *,
    menu: Sequence[str],
    cash_symbol: str,
    latest_session: date,
    lookbacks: Sequence[int],
    top_n: int,
    rebalance: str,
    absolute_momentum_filter: bool,
    min_history_sessions: int,
    unfilled_slot_policy: str,
    vol_cfg: Any,
) -> OverlayDecision:
    columns = sorted({*menu, cash_symbol})
    book_panel = panel.loc[panel["symbol"].isin(columns) & (panel["trade_date"] <= latest_session)]
    sessions = sorted(set(book_panel["trade_date"]))
    weights, signal_sessions = replay_books(
        series,
        sessions,
        menu=menu,
        cash_symbol=cash_symbol,
        lookbacks=lookbacks,
        top_n=top_n,
        rebalance=rebalance,
        absolute_momentum_filter=absolute_momentum_filter,
        min_history_sessions=min_history_sessions,
        unfilled_slot_policy=unfilled_slot_policy,
    )
    close = book_panel.pivot(index="trade_date", columns="symbol", values="close")
    open_ = book_panel.pivot(index="trade_date", columns="symbol", values="open")
    close = close.reindex(index=sessions, columns=columns)
    open_ = open_.reindex(index=sessions, columns=columns)
    boost = getattr(vol_cfg, "dip_boost", None)
    dip_close = None
    if boost is not None:
        dip_dates, dip_closes = series[str(boost.signal_symbol).upper()]
        dip_close = pd.Series(
            [dip_closes[day] for day in dip_dates if day <= latest_session],
            index=[day for day in dip_dates if day <= latest_session],
            dtype=float,
        )
    return decide_overlay(
        sessions,
        weights,
        close,
        open_,
        signal_sessions,
        base_target=float(vol_cfg.target_annual_vol),
        realized_vol_sessions=int(vol_cfg.realized_vol_sessions),
        dip_close=dip_close,
        sma_sessions=int(boost.sma_sessions) if boost is not None else 200,
        rsi_sessions=int(boost.rsi_sessions) if boost is not None else 10,
        rsi_below=float(boost.rsi_below) if boost is not None else 30.0,
        boost_target=float(boost.target_annual_vol) if boost is not None else None,
        hold_sessions=int(boost.hold_sessions) if boost is not None else None,
    )


def _overlay_report_lines(manifest: Mapping[str, Any]) -> list[str]:
    lines: list[str] = []
    overlay = manifest.get("vol_target")
    if overlay:
        realized = overlay.get("realized_annual_vol")
        lines.append(
            f"- Volatility target: multiplier `{overlay['multiplier']:.4f}` = min(1, "
            f"`{overlay['target_annual_vol']}` / realized "
            f"`{realized if realized is None else round(realized, 4)}`), decided on the "
            f"`{overlay['decision_session']}` close; boost active: `{overlay['boost_active']}`"
        )
    guard = manifest.get("sleeve_guard")
    if guard:
        lines.append(
            f"- Sleeve equity: `{guard['equity_latest']:.2f}` (peak `{guard['peak_equity']:.2f}`, "
            f"drawdown `{guard['drawdown']:.2%}`, exit at `{guard['drawdown_exit_pct']}`, "
            f"breached: `{guard['drawdown_exit_breached']}`); sizing basis "
            f"`{guard['sizing_basis']}`"
        )
    return lines


# ---------------------------------------------------------------------------
# entry points


def run_rotation_target_weight_mapping_for_spec(
    spec: StrategySpec,
    rotation_config: Any,
    spec_path: Path,
    root: Path,
    *,
    as_of: datetime | None = None,
    account_equity_override: float | None = None,
    memory_limit: str = DEFAULT_MEMORY_LIMIT,
    threads: int = DEFAULT_THREADS,
) -> RotationTargetWeightResult:
    """Same as :func:`run_rotation_target_weight_mapping` but takes an
    already-loaded ``spec`` and its ``rotation_config`` (normally
    ``spec.portfolio.etf_rotation``) separately, so tests -- and any caller
    that already has a validated config object -- do not have to round-trip
    through a YAML file."""
    if spec.execution.mode != "manual_signal" or spec.execution.broker != "none":
        raise ValueError(
            "etf_rotation_portfolio target-weight mapping is observation-only and requires "
            "execution.mode=manual_signal, execution.broker=none"
        )

    menu = [str(symbol).upper() for symbol in rotation_config.menu]
    cash_symbol = str(rotation_config.cash_symbol).upper()
    lookbacks = [int(n) for n in rotation_config.lookbacks]
    top_n = int(rotation_config.top_n)
    rebalance = str(rotation_config.rebalance)
    absolute_momentum_filter = bool(rotation_config.absolute_momentum_filter)
    min_history_sessions = int(rotation_config.min_history_sessions)
    notional_budget_usd = getattr(rotation_config, "notional_budget_usd", None)
    if notional_budget_usd is not None:
        notional_budget_usd = float(notional_budget_usd)
    vol_cfg = getattr(rotation_config, "vol_target", None)
    boost_cfg = getattr(vol_cfg, "dip_boost", None) if vol_cfg is not None else None
    sizing_basis = str(getattr(rotation_config, "sizing_basis", None) or "notional_budget")
    drawdown_exit_pct = getattr(rotation_config, "drawdown_exit_pct", None)
    tolerance_fraction = getattr(rotation_config, "rebalance_tolerance_fraction", None)
    track_sleeve = sizing_basis == "sleeve_equity" or drawdown_exit_pct is not None
    if track_sleeve and notional_budget_usd is None:
        raise ValueError("sleeve_equity sizing and drawdown_exit_pct need notional_budget_usd")
    fills = _sleeve_fills(root, spec.name) if track_sleeve else []

    now = datetime.now(UTC)
    reference_dt = as_of or now
    run_year = reference_dt.year
    years = [run_year - 2, run_year - 1, run_year]
    as_of_bound = as_of.date() if as_of else None

    symbols_needed = sorted(
        {
            *menu,
            cash_symbol,
            *held_symbols(fills),
            *([str(boost_cfg.signal_symbol).upper()] if boost_cfg is not None else []),
        }
    )
    panel = load_price_panel(
        root, symbols_needed, years, memory_limit=memory_limit, threads=threads
    )
    series = {symbol: _symbol_series(panel, symbol) for symbol in symbols_needed}

    cash_dates, cash_closes = series[cash_symbol]
    cash_candidates = [day for day in cash_dates if as_of_bound is None or day <= as_of_bound]
    if not cash_candidates:
        bound_label = as_of_bound.isoformat() if as_of_bound else "now"
        raise ValueError(f"no {cash_symbol} session on/before {bound_label} under data/sip/daily")
    latest_session = max(cash_candidates)
    signal_session = resolve_signal_session(cash_dates, rebalance, latest_session)

    scores: dict[str, float] = {}
    ineligible: dict[str, str] = {}
    for symbol in menu:
        dates, closes = series[symbol]
        result = score_symbol(
            dates,
            closes,
            signal_session=signal_session,
            lookbacks=lookbacks,
            min_history_sessions=min_history_sessions,
        )
        if result.reason is not None:
            ineligible[symbol] = result.reason
        else:
            scores[symbol] = float(result.score)

    cash_result = score_symbol(
        cash_dates,
        cash_closes,
        signal_session=signal_session,
        lookbacks=lookbacks,
        min_history_sessions=min_history_sessions,
    )
    if absolute_momentum_filter and cash_result.reason is not None:
        raise ValueError(
            f"cash_symbol {cash_symbol} is ineligible for scoring ({cash_result.reason}); "
            "cannot apply absolute_momentum_filter"
        )
    cash_score = cash_result.score

    picks, dropped_by_filter = select_book(
        scores,
        top_n=top_n,
        cash_score=cash_score,
        absolute_momentum_filter=absolute_momentum_filter,
    )
    unfilled_slot_policy = str(getattr(rotation_config, "unfilled_slot_policy", "cash") or "cash")
    weights = build_weights(
        picks,
        top_n=top_n,
        cash_symbol=cash_symbol,
        unfilled_slot_policy=unfilled_slot_policy,
    )
    book_weights = dict(weights)

    # Every price and equity the sizing reads is taken at the anchor: the
    # close whose data last changed the target weights (the rebalance close,
    # or a later volatility-target update). Between updates the share targets
    # are therefore identical run after run, which keeps the daily cron
    # idempotent; the sleeve holds its shares until the next update.
    anchor_session = signal_session
    overlay_manifest: dict[str, Any] | None = None
    if vol_cfg is not None:
        decision = _decide_overlay(
            panel,
            series,
            menu=menu,
            cash_symbol=cash_symbol,
            latest_session=latest_session,
            lookbacks=lookbacks,
            top_n=top_n,
            rebalance=rebalance,
            absolute_momentum_filter=absolute_momentum_filter,
            min_history_sessions=min_history_sessions,
            unfilled_slot_policy=unfilled_slot_policy,
            vol_cfg=vol_cfg,
        )
        weights = apply_multiplier(book_weights, decision.multiplier, cash_symbol)
        anchor_session = max(signal_session, decision.decision_session or signal_session)
        overlay_manifest = {
            "multiplier": decision.multiplier,
            "target_annual_vol": decision.target_annual_vol,
            "base_target_annual_vol": float(vol_cfg.target_annual_vol),
            "realized_annual_vol": decision.realized_annual_vol,
            "realized_vol_sessions": int(vol_cfg.realized_vol_sessions),
            "boost_active": decision.boost_active,
            "boost_target_annual_vol": float(boost_cfg.target_annual_vol) if boost_cfg else None,
            "boost_hold_sessions": int(boost_cfg.hold_sessions) if boost_cfg else None,
            "boost_signal_symbol": str(boost_cfg.signal_symbol).upper() if boost_cfg else None,
            "recent_boost_signal_sessions": [d.isoformat() for d in decision.boost_fired_sessions],
            "decision_session": decision.decision_session.isoformat()
            if decision.decision_session
            else None,
            "updates_next_session": decision.updates_next_session,
            "book_weights": book_weights,
        }

    account_equity, equity_generated_at, equity_source = _resolve_account_equity(
        root, account_equity_override
    )
    sizing_equity, notional_budget_configured, notional_budget_binds = resolve_sizing_equity(
        account_equity, notional_budget_usd
    )

    sleeve_guard: dict[str, Any] | None = None
    if track_sleeve:
        budget = float(notional_budget_usd)  # type: ignore[arg-type]
        closes_frame = _close_frame(panel, latest_session)
        curve = sleeve_equity_curve(fills, closes_frame, budget)
        at_anchor = curve.loc[[day <= anchor_session for day in curve.index]]
        equity_at_anchor = float(at_anchor.iloc[-1]) if not at_anchor.empty else budget
        equity_latest = float(curve.iloc[-1]) if not curve.empty else budget
        peak = max(budget, float(curve.max()) if not curve.empty else budget)
        drawdown = 1.0 - equity_latest / peak
        sleeve_guard = {
            "sizing_basis": sizing_basis,
            "starting_equity": budget,
            "first_fill_session": min(curve.index).isoformat() if not curve.empty else None,
            "equity_at_anchor": equity_at_anchor,
            "equity_latest": equity_latest,
            "peak_equity": peak,
            "drawdown": drawdown,
            "drawdown_exit_pct": drawdown_exit_pct,
            "drawdown_exit_breached": drawdown_exit_pct is not None
            and drawdown >= float(drawdown_exit_pct),
            "marked_through": latest_session.isoformat(),
        }
        if sizing_basis == "sleeve_equity":
            sizing_equity = min(equity_at_anchor, float(account_equity))
            notional_budget_binds = sizing_equity < float(account_equity) - 1e-9

    reference_prices: dict[str, float] = {}
    for symbol in weights:
        dates, closes = series[symbol]
        known = [day for day in dates if day <= anchor_session and closes.get(day)]
        if not known or (anchor_session == signal_session and known[-1] != signal_session):
            raise ValueError(
                f"no {symbol} close on anchor session {anchor_session} despite passing eligibility"
            )
        reference_prices[symbol] = float(closes[known[-1]])

    sizing = size_whole_share_portfolio(weights, reference_prices, sizing_equity)

    rebalance_session = next_us_equity_session(anchor_session)
    rebalance_id = f"{spec.name}:{anchor_session.isoformat()}"
    target_rows: list[dict[str, object]] = []
    for symbol in sorted(weights):
        weight = float(weights[symbol])
        leg = "cash" if symbol == cash_symbol else "rotation"
        score_value = cash_score if symbol == cash_symbol else scores.get(symbol)
        target_rows.append(
            {
                "symbol": symbol,
                "target_weight": weight,
                "realized_weight": float(sizing.realized_weights.get(symbol, 0.0)),
                "shares": int(sizing.shares.get(symbol, 0)),
                "reference_price": float(reference_prices[symbol]),
                "sizing_equity": float(sizing_equity),
                "selected": weight > 1e-12,
                "leg": leg,
                "score": score_value,
                "rebalance_id": rebalance_id,
                "rebalance_session": rebalance_session.isoformat(),
                "signal_session": signal_session.isoformat(),
                "source": SOURCE_TAG,
                "state": "signal",
                "time_rule": TIME_RULE,
            }
        )

    warnings: list[str] = []
    if ineligible:
        warnings.append(f"{len(ineligible)} menu symbol(s) ineligible: {sorted(ineligible)}")
    if dropped_by_filter:
        warnings.append(
            f"absolute_momentum_filter sent {len(dropped_by_filter)} pick(s) to cash: "
            f"{sorted(dropped_by_filter)}"
        )
    if sizing.unaffordable:
        warnings.append(f"unaffordable_at_current_equity={list(sizing.unaffordable)}")
    if notional_budget_binds:
        warnings.append(
            f"notional_budget_usd={notional_budget_usd} caps sizing below "
            f"account_equity={account_equity:.2f} (sizing_equity={sizing_equity:.2f})"
        )

    manifest: dict[str, Any] = {
        "mapping_mode": MAPPING_MODE,
        "as_of_utc": now.isoformat(),
        "as_of_bound": as_of_bound.isoformat() if as_of_bound else None,
        "menu": menu,
        "cash_symbol": cash_symbol,
        "lookbacks": lookbacks,
        "top_n": top_n,
        "rebalance": rebalance,
        "absolute_momentum_filter": absolute_momentum_filter,
        "unfilled_slot_policy": unfilled_slot_policy,
        "min_history_sessions": min_history_sessions,
        "years_read": years,
        "latest_session": latest_session.isoformat(),
        "signal_session": signal_session.isoformat(),
        "rebalance_session": rebalance_session.isoformat(),
        "scores": {**scores, cash_symbol: cash_score},
        "ineligible": [{"symbol": s, "reason": r} for s, r in sorted(ineligible.items())],
        "picks_before_filter": sorted(picks + dropped_by_filter),
        "selected": sorted(picks),
        "selected_count": len(picks),
        "dropped_by_absolute_momentum": sorted(dropped_by_filter),
        "dropped_by_absolute_momentum_count": len(dropped_by_filter),
        "weight_per_pick": (1.0 / top_n) if picks else 0.0,
        "cash_weight": float(weights.get(cash_symbol, 0.0)),
        "anchor_session": anchor_session.isoformat(),
        "vol_target": overlay_manifest,
        "sizing_basis": sizing_basis,
        "sleeve_guard": sleeve_guard,
        "rebalance_tolerance_fraction": tolerance_fraction,
        "account_equity": account_equity,
        "account_equity_generated_at": equity_generated_at,
        "account_equity_source": equity_source,
        "notional_budget_usd": notional_budget_usd,
        "notional_budget_configured": notional_budget_configured,
        "notional_budget_binds": notional_budget_binds,
        "sizing_equity": sizing_equity,
        "weight_deviation": sizing.weight_deviation,
        "idle_cash": sizing.idle_cash,
        "idle_cash_fraction": sizing.idle_cash_fraction,
        "invested_cash": sizing.invested_cash,
        "unaffordable": list(sizing.unaffordable),
        "paper_order_authorization": False,
        "broker_writes": False,
        "warnings": warnings,
    }

    data_profile = {
        "source_mode": "cache",
        "provider": "alpaca_sip_daily_archive",
        "feed": spec.data.feed or "",
        "years_read": years,
        "latest_session": manifest["latest_session"],
        "signal_session": manifest["signal_session"],
    }
    acquisition_tier = infer_acquisition_tier(
        data_source=spec.data.source,
        data_profile=data_profile,
        explicit=spec.data_assumptions.acquisition_tier,
        refresh_data=False,
    )
    parity_check = {"status": "ok", "blockers": [], "warnings": warnings}

    artifacts = write_router_execution_artifacts(
        root=root,
        spec_path=spec_path,
        spec=spec,
        target_rows=target_rows,
        rebalance_intents=[],
        data_profile=data_profile,
        route_label=None,
        mapping_summary=manifest,
        acquisition_tier=acquisition_tier,
        parity_check=parity_check,
        target_backend="python_reference",
    )
    target_weights_path = artifacts["router_target_weights"]
    report_path = target_weights_path.with_suffix(".md")

    signals = _build_signals(
        spec=spec, target_rows=target_rows, signal_session=anchor_session, manifest=manifest
    )
    signal_log_path = root / "signal_logs" / f"etf-rotation-{spec.name}.jsonl"
    if signals:
        append_jsonl(signal_log_path, [model_to_record(signal) for signal in signals])
    else:
        signal_log_path.parent.mkdir(parents=True, exist_ok=True)
        signal_log_path.touch(exist_ok=True)

    _write_report(
        report_path,
        spec=spec,
        target_rows=target_rows,
        manifest=manifest,
        target_weights_path=target_weights_path,
        signal_log_path=signal_log_path,
        signal_count=len(signals),
    )

    return RotationTargetWeightResult(
        report_path=report_path,
        target_weights_path=target_weights_path,
        parity_status=str(parity_check["status"]),
        rebalance_sessions=len({row["rebalance_session"] for row in target_rows}),
        target_weight_count=len(target_rows),
        nonzero_target_rows=sum(bool(row["selected"]) for row in target_rows),
        signal_log_path=signal_log_path,
        signal_count=len(signals),
        manifest=manifest,
    )


def run_rotation_target_weight_mapping(
    spec_path: Path,
    root: Path,
    *,
    as_of: datetime | None = None,
    account_equity_override: float | None = None,
    memory_limit: str = DEFAULT_MEMORY_LIMIT,
    threads: int = DEFAULT_THREADS,
) -> RotationTargetWeightResult:
    spec = load_strategy_spec(spec_path)
    if spec.portfolio.mode != "etf_rotation_portfolio" or spec.portfolio.etf_rotation is None:
        raise ValueError(
            "etf_rotation target mapping requires portfolio.mode=etf_rotation_portfolio with "
            "portfolio.etf_rotation"
        )
    return run_rotation_target_weight_mapping_for_spec(
        spec,
        spec.portfolio.etf_rotation,
        spec_path,
        root,
        as_of=as_of,
        account_equity_override=account_equity_override,
        memory_limit=memory_limit,
        threads=threads,
    )


def _build_signals(
    *,
    spec: StrategySpec,
    target_rows: list[dict[str, object]],
    signal_session: date,
    manifest: dict[str, Any],
) -> list[Any]:
    spec_hash = strategy_content_hash(spec)
    run_id = f"etf-rotation-{spec.name}"
    timestamp = datetime.combine(signal_session, time(20, 0), tzinfo=UTC)
    conditions = [
        f"rebalance={manifest['rebalance']}",
        f"signal_session={manifest['signal_session']}",
        f"top_n={manifest['top_n']}",
        f"absolute_momentum_filter={manifest['absolute_momentum_filter']}",
    ]
    overlay = manifest.get("vol_target")
    if overlay:
        conditions.append(
            f"vol_target_multiplier={overlay['multiplier']:.4f}"
            f";target={overlay['target_annual_vol']};boost={overlay['boost_active']}"
        )
    signals = []
    for row in target_rows:
        if not row["selected"]:
            continue
        signals.append(
            build_signal(
                spec,
                run_id=run_id,
                timestamp=timestamp,
                action="entry",
                source=SIGNAL_SOURCE,
                price=float(row["reference_price"]),
                spec_hash=spec_hash,
                symbol=str(row["symbol"]),
                target_weight=float(row["target_weight"]),
                conditions=conditions,
            )
        )
    return signals


def _write_report(
    path: Path,
    *,
    spec: StrategySpec,
    target_rows: list[dict[str, object]],
    manifest: dict[str, Any],
    target_weights_path: Path,
    signal_log_path: Path,
    signal_count: int,
) -> None:
    held = sorted(
        (row for row in target_rows if row["selected"]), key=lambda row: str(row["symbol"])
    )
    lines = [
        f"# ETF Rotation Target Weights: {spec.name}",
        "",
        f"- JSON: `{target_weights_path}`",
        f"- Signal log: `{signal_log_path}`",
        f"- Latest session: `{manifest['latest_session']}`; signal session: "
        f"`{manifest['signal_session']}`; rebalance session: `{manifest['rebalance_session']}`",
        f"- Rebalance rule: `{manifest['rebalance']}`; top_n: `{manifest['top_n']}`; "
        f"absolute momentum filter: `{manifest['absolute_momentum_filter']}`",
        f"- Selected: `{manifest['selected']}`; dropped by filter: "
        f"`{manifest['dropped_by_absolute_momentum']}`; ineligible: "
        f"`{[row['symbol'] for row in manifest['ineligible']]}`",
        f"- Account equity: `{manifest['account_equity']:.2f}`; notional budget: "
        f"`{manifest['notional_budget_usd']}`; sizing equity: `{manifest['sizing_equity']:.2f}` "
        f"(binds: `{manifest['notional_budget_binds']}`)",
        f"- Idle cash: `{manifest['idle_cash']:.2f}` (`{manifest['idle_cash_fraction']:.4%}`)",
        *_overlay_report_lines(manifest),
        f"- Signals logged this run: `{signal_count}`",
        "- Broker writes: `false`",
        "",
        "## Holdings" if held else "## Holdings (none -- 100% cash)",
        "",
    ]
    if held:
        lines.extend(
            [
                "| symbol | leg | target weight | shares | reference price | score |",
                "| --- | --- | --- | --- | --- | --- |",
            ]
        )
        lines.extend(
            f"| {row['symbol']} | {row['leg']} | {float(row['target_weight']):.4f} | "
            f"{row['shares']} | {float(row['reference_price']):.4f} | "
            f"{row['score'] if row['score'] is not None else '-'} |"
            for row in held
        )
    lines.append("")
    if manifest.get("warnings"):
        lines.append("## Warnings")
        lines.append("")
        lines.extend(f"- {warning}" for warning in manifest["warnings"])
        lines.append("")
    lines.append("## Manifest")
    lines.append("")
    lines.append("```json")
    lines.append(json.dumps(manifest, indent=2, ensure_ascii=False, default=str))
    lines.append("```")
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")
