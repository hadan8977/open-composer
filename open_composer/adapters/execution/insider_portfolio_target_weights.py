"""``portfolio.mode=insider_buy_portfolio`` -> target weights (H-20260917-01).

Second paper-rehearsal book after ``us_recent_high_return_top50``
(``docs/plan-step-17-paper-rehearsal-portfolio-canary-2026-09-15.zh.md``).
Observation-side adapter: it never submits broker orders. It writes the same
``reports/execution/{name}-target-weights.json`` shape every other
target-weight adapter writes (:func:`write_router_execution_artifacts`), so
``open_composer.paper_rehearsal`` consumes it unchanged -- the rows carry
``symbol``, ``side``, ``target_weight``, ``reference_price``,
``sizing_equity`` and ``selected`` exactly like the model-ranking adapter's.

Selection rule (every knob is ``portfolio.insider_buy`` in the StrategySpec,
see ``InsiderBuyPortfolioConfig``)
------------------------------------------------------------------------------
1. **Universe** = the latest *completed* point-in-time cohort of the universe
   root (``data/features/universe_broad``; falls back to
   ``data/features/universe`` with a loud warning field when the broad table
   has no yearly files yet), optionally narrowed to an ``adv_rank`` band.
2. **Feature date** = the latest ``trade_date`` in the insider table that is
   ``<=`` the last *completed* US-equity session as of ``now`` -- never a
   future or still-running session.
3. **Eligible** = cohort symbols whose insider row on that date has
   ``open_market_buy_count_60d >= min``, ``net_buy_usd_60d >= min`` and
   ``buyers_60d >= min``; ranked by ``rank_column`` descending (ties by symbol).
4. **Fresh-bar check** = a candidate with no SIP daily bar inside the last
   ``stale_bar_sessions`` sessions is skipped (delisted / halted /
   backfilled-only) and recorded; the book is filled from the next names.
5. **Weights** = equal weight over the first ``max_names`` survivors at
   ``gross_target``; if that exceeds ``per_name_cap`` the per-name weight is
   clamped and the gross is scaled *down* (recorded), never the cap up.
6. **Reference price** = each name's last SIP daily close on/before the
   feature-date bound (``data/sip/daily``), whole-share sized against the
   live paper account equity (``reports/paper/account.json``).

Monthly-hold contract
---------------------
A fresh signal is computed when no previous snapshot exists (the initial full
entry on first authorization) or when the feature date's calendar month
differs from the previous snapshot's ``signal_month`` -- i.e. the first run
whose feature date lies after a month end. Every other run re-emits the
previous weights (``state=hold_no_new_signal``) with refreshed reference
prices, so whole-share drift is handled by the rehearsal planner's churn
tolerance and no new order intents are produced.

Every run publishes a small manifest (feature dates used, cohort month end,
counts, skips, fallbacks, warnings) inside the artifact ``summary`` and the
markdown report so the rehearsal run is auditable.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import duckdb
import pandas as pd

from open_composer.adapters.execution.router_target_weights import (
    infer_acquisition_tier,
    write_router_execution_artifacts,
)
from open_composer.adapters.execution.whole_share_sizing import (
    WholeShareSizing,
    size_whole_share_portfolio,
)
from open_composer.config import project_root
from open_composer.engines.signal_engine import build_signal
from open_composer.market_calendar import (
    next_us_equity_session,
    us_equity_session_close,
    us_equity_session_dates,
)
from open_composer.models.strategy_spec import (
    InsiderBuyPortfolioConfig,
    StrategySpec,
    load_strategy_spec,
)
from open_composer.research.kernel.loop import universe_as_of_calendar_month
from open_composer.storage import append_jsonl, model_to_record
from open_composer.strategy_versions import strategy_content_hash

#: Same memory discipline as the model-ranking adapter: every read is a
#: single-day or single-year DuckDB query under this cap (3.9GB box).
DEFAULT_MEMORY_LIMIT = "1.2GB"
MAPPING_MODE = "insider_buy_portfolio_target_weight_mapping"
SOURCE_TAG = "insider_buy_portfolio_python_reference"
TIME_RULE = "next_regular_session_day_market_open_queue"
SIGNAL_SOURCE = "insider_buy_portfolio_observation"
REQUIRED_INSIDER_COLUMNS: tuple[str, ...] = (
    "open_market_buy_count_60d",
    "net_buy_usd_60d",
    "buyers_60d",
)


@dataclass(frozen=True)
class ResolvedRoot:
    path: Path
    requested: str
    used: str
    fallback_used: bool
    warning: str | None


@dataclass(frozen=True)
class BookSelection:
    weights: dict[str, float]
    weight_per_name: float
    gross_effective: float
    gross_scaled_down: bool
    skipped_stale: tuple[str, ...]
    eligible_ranked: tuple[str, ...]


@dataclass(frozen=True)
class InsiderPortfolioTargetWeightResult:
    report_path: Path
    json_path: Path
    signal_log_path: Path
    target_weight_count: int
    rebalance_sessions: int
    nonzero_target_rows: int
    parity_status: str
    is_new_signal: bool
    signal_count: int
    manifest: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# roots, dates


def _year_files(root: Path) -> list[int]:
    if not root.is_dir():
        return []
    return sorted(int(p.stem) for p in root.glob("*.parquet") if p.stem.isdigit())


def resolve_feature_root(
    base: Path, preferred: str, fallback: str | None, *, label: str
) -> ResolvedRoot:
    """Prefer ``preferred``; fall back (with a recorded warning) only when it
    has no yearly parquet files at all. Raises when neither is usable."""
    preferred_path = base / preferred
    if _year_files(preferred_path):
        return ResolvedRoot(preferred_path, preferred, preferred, False, None)
    if fallback:
        fallback_path = base / fallback
        if _year_files(fallback_path):
            warning = (
                f"{label}: preferred root {preferred} has no yearly parquet files; "
                f"FELL BACK to {fallback} (narrower coverage -- label this run accordingly)"
            )
            return ResolvedRoot(fallback_path, preferred, fallback, True, warning)
    raise ValueError(
        f"{label}: neither {preferred} nor fallback {fallback!r} has yearly parquet files "
        f"under {base}"
    )


def last_completed_us_equity_session(now: datetime, timezone: str = "America/New_York") -> date:
    """The most recent US-equity session whose close has already passed."""
    local = now.astimezone(ZoneInfo(timezone))
    day = local.date()
    close = us_equity_session_close(day)
    if close is not None and local.time() >= close:
        return day
    cursor = day - timedelta(days=1)
    for _ in range(14):
        if us_equity_session_close(cursor) is not None:
            return cursor
        cursor -= timedelta(days=1)
    raise ValueError(f"no US equity session within 14 days before {day}")


def _connect(memory_limit: str) -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    con.execute(f"SET memory_limit='{memory_limit}'")
    con.execute("SET TimeZone='UTC'")
    return con


def latest_insider_feature_date(
    root: Path, *, not_after: date, memory_limit: str = DEFAULT_MEMORY_LIMIT
) -> pd.Timestamp:
    """Latest insider ``trade_date`` ``<= not_after``, newest year file first."""
    years = [year for year in _year_files(root) if year <= not_after.year]
    if not years:
        raise ValueError(f"no insider feature file at or before {not_after} under {root}")
    bound = datetime.combine(not_after, time())
    con = _connect(memory_limit)
    try:
        for year in sorted(years, reverse=True):
            value = con.execute(
                "SELECT max(trade_date) FROM read_parquet(?) WHERE trade_date <= ?",
                [str(root / f"{year}.parquet"), bound],
            ).fetchone()[0]
            if value is not None:
                return pd.Timestamp(value)
    finally:
        con.close()
    raise ValueError(f"insider feature files under {root} have no rows on/before {not_after}")


def load_insider_cross_section(
    root: Path,
    *,
    trade_date: pd.Timestamp,
    columns: list[str],
    memory_limit: str = DEFAULT_MEMORY_LIMIT,
) -> pd.DataFrame:
    path = root / f"{trade_date.year}.parquet"
    if not path.is_file():
        raise ValueError(f"no insider feature file for year {trade_date.year} at {path}")
    column_list = ", ".join(dict.fromkeys(["symbol", "trade_date", *columns]))
    con = _connect(memory_limit)
    try:
        frame = con.execute(
            f"SELECT {column_list} FROM read_parquet(?) WHERE trade_date = ?",  # noqa: S608
            [str(path), trade_date.to_pydatetime()],
        ).fetchdf()
    finally:
        con.close()
    frame["symbol"] = frame["symbol"].astype(str)
    return frame


def load_universe_cohort(
    root: Path, *, as_of: pd.Timestamp, memory_limit: str = DEFAULT_MEMORY_LIMIT
) -> tuple[pd.DataFrame, pd.Timestamp]:
    """``(cohort[symbol, adv_rank], month_end)`` of the PIT cohort in effect on
    ``as_of`` (``kernel.loop.universe_as_of_calendar_month`` semantics)."""
    years = [year for year in _year_files(root) if year <= as_of.year]
    if not years:
        raise ValueError(f"no universe file at or before {as_of.date()} under {root}")
    con = _connect(memory_limit)
    frame = pd.DataFrame()
    try:
        for year in sorted(years, reverse=True)[:2]:
            frame = con.execute(
                "SELECT month_end, symbol, adv_rank FROM read_parquet(?) WHERE month_end <= ?",
                [str(root / f"{year}.parquet"), as_of.to_pydatetime()],
            ).fetchdf()
            if not frame.empty:
                break
    finally:
        con.close()
    if frame.empty:
        raise ValueError(f"universe root {root} has no cohort at/before {as_of.date()}")
    frame["month_end"] = pd.to_datetime(frame["month_end"])
    frame["symbol"] = frame["symbol"].astype(str)
    symbols = universe_as_of_calendar_month(frame, as_of)
    if not symbols:
        raise ValueError(f"universe_as_of_calendar_month found no cohort for {as_of.date()}")
    cohort = frame.loc[frame["symbol"].isin(symbols)]
    month_end = pd.Timestamp(cohort["month_end"].max())
    cohort = cohort.loc[cohort["month_end"].dt.to_period("M") == month_end.to_period("M")]
    cohort = (
        cohort.sort_values(["adv_rank", "symbol"])
        .drop_duplicates("symbol", keep="first")
        .loc[:, ["symbol", "adv_rank"]]
        .reset_index(drop=True)
    )
    cohort["adv_rank"] = cohort["adv_rank"].astype(int)
    return cohort, month_end


def load_latest_closes(
    root: Path,
    symbols: list[str] | set[str] | tuple[str, ...],
    *,
    as_of: date,
    lookback_sessions: int,
    memory_limit: str = DEFAULT_MEMORY_LIMIT,
) -> tuple[dict[str, float], dict[str, date], date | None]:
    """Each symbol's last SIP daily close inside the last ``lookback_sessions``
    sessions ending at ``as_of`` (``data/sip/daily/{year}/*.parquet``).
    Symbols absent from the result had no bar in that window (stale)."""
    wanted = sorted({str(s).upper() for s in symbols if str(s).strip()})
    if not wanted:
        return {}, {}, None
    sessions = us_equity_session_dates(as_of - timedelta(days=lookback_sessions * 3 + 14), as_of)
    if not sessions:
        raise ValueError(f"no US equity sessions on/before {as_of}")
    window = sessions[-lookback_sessions:]
    start = window[0]
    daily_dir = root / "data" / "sip" / "daily"
    globs = [
        str(daily_dir / str(year) / "*.parquet")
        for year in sorted({start.year, as_of.year})
        if (daily_dir / str(year)).is_dir()
    ]
    if not globs:
        raise ValueError(
            f"no SIP daily archive year directory for {start}..{as_of} under {daily_dir}"
        )
    start_ts = datetime.combine(start, time(), tzinfo=UTC)
    end_ts = datetime.combine(as_of + timedelta(days=1), time(), tzinfo=UTC)
    con = _connect(memory_limit)
    try:
        con.register("wanted_symbols", pd.DataFrame({"symbol": wanted}))
        frame = con.execute(
            f"""
            WITH bars AS (
                SELECT symbol, CAST(timestamp AS DATE) AS trade_date, timestamp, close
                FROM read_parquet({globs!r}, union_by_name=true)
                WHERE symbol IN (SELECT symbol FROM wanted_symbols)
                  AND timestamp >= ? AND timestamp < ?
                  AND close IS NOT NULL AND close > 0
            ),
            ranked AS (
                SELECT *, ROW_NUMBER() OVER (
                    PARTITION BY symbol ORDER BY trade_date DESC, timestamp DESC
                ) AS rn
                FROM bars
            )
            SELECT symbol, trade_date, close FROM ranked WHERE rn = 1
            """,  # noqa: S608
            [start_ts, end_ts],
        ).fetchdf()
    finally:
        con.close()
    closes: dict[str, float] = {}
    price_sessions: dict[str, date] = {}
    for row in frame.to_dict("records"):
        symbol = str(row["symbol"]).upper()
        closes[symbol] = float(row["close"])
        price_sessions[symbol] = pd.Timestamp(row["trade_date"]).date()
    reference_session = max(price_sessions.values()) if price_sessions else None
    return closes, price_sessions, reference_session


# ---------------------------------------------------------------------------
# selection (pure)


def rank_eligible_candidates(
    insider_frame: pd.DataFrame,
    cohort: pd.DataFrame,
    params: InsiderBuyPortfolioConfig,
) -> pd.DataFrame:
    """Cohort (band-filtered) joined to the insider cross-section, thresholded
    and ranked by ``params.rank_column`` descending (ties: symbol ascending).
    Pure; returns ``symbol, adv_rank, <insider columns>``."""
    band = cohort.copy()
    if params.adv_rank_min is not None:
        band = band.loc[band["adv_rank"] >= int(params.adv_rank_min)]
    if params.adv_rank_max is not None:
        band = band.loc[band["adv_rank"] <= int(params.adv_rank_max)]
    band = band.assign(symbol=band["symbol"].astype(str).str.upper())
    rows = insider_frame.assign(symbol=insider_frame["symbol"].astype(str).str.upper())
    joined = band.merge(rows, on="symbol", how="inner")
    for column in (*REQUIRED_INSIDER_COLUMNS, params.rank_column):
        if column not in joined.columns:
            raise ValueError(f"insider table lacks required column {column!r}")
    mask = (
        (joined["open_market_buy_count_60d"].fillna(0) >= params.min_open_market_buy_count_60d)
        & (joined["net_buy_usd_60d"].fillna(-1.0) >= params.min_net_buy_usd_60d)
        & (joined["buyers_60d"].fillna(0) >= params.min_buyers_60d)
        & joined[params.rank_column].notna()
    )
    eligible = joined.loc[mask].copy()
    eligible = eligible.sort_values(
        [params.rank_column, "symbol"], ascending=[False, True], kind="stable"
    )
    return eligible.reset_index(drop=True)


def equal_weights_with_cap(
    symbols: list[str], *, gross_target: float, per_name_cap: float
) -> tuple[dict[str, float], float, float, bool]:
    """``(weights, weight_per_name, gross_effective, scaled_down)``: equal
    weight at ``gross_target``, clamped to ``per_name_cap`` per name -- the
    gross is scaled down rather than the cap exceeded."""
    count = len(symbols)
    if count == 0:
        return {}, 0.0, 0.0, False
    weight = float(gross_target) / count
    scaled_down = False
    if weight > float(per_name_cap) + 1e-12:
        weight = float(per_name_cap)
        scaled_down = True
    return dict.fromkeys(symbols, weight), weight, weight * count, scaled_down


def finalize_book(
    ranked: pd.DataFrame,
    *,
    stale_symbols: set[str],
    params: InsiderBuyPortfolioConfig,
) -> BookSelection:
    """Drop stale names, keep the first ``max_names`` survivors, weight them."""
    ordered = [str(s) for s in ranked["symbol"].tolist()]
    skipped = tuple(s for s in ordered if s in stale_symbols)
    survivors = [s for s in ordered if s not in stale_symbols][: int(params.max_names)]
    weights, per_name, gross, scaled = equal_weights_with_cap(
        survivors, gross_target=params.gross_target, per_name_cap=params.per_name_cap
    )
    return BookSelection(
        weights=weights,
        weight_per_name=per_name,
        gross_effective=gross,
        gross_scaled_down=scaled,
        skipped_stale=skipped,
        eligible_ranked=tuple(ordered),
    )


# ---------------------------------------------------------------------------
# rows, snapshot, equity


def _read_previous_snapshot(root: Path, strategy_name: str) -> dict[str, Any] | None:
    path = root / "reports" / "execution" / f"{strategy_name}-target-weights.json"
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None
    rows = payload.get("target_weights") or []
    if not rows:
        return None
    sessions = sorted({str(row["rebalance_session"]) for row in rows})
    latest_session = sessions[-1]
    latest_rows = [row for row in rows if str(row.get("rebalance_session")) == latest_session]
    weights = {
        str(row["symbol"]).upper(): float(row.get("target_weight") or 0.0)
        for row in latest_rows
        if abs(float(row.get("target_weight") or 0.0)) > 1e-12
    }
    summary = payload.get("summary") or {}
    signal_session = latest_rows[0].get("signal_session") if latest_rows else None
    signal_month = summary.get("signal_month") or (
        str(signal_session)[:7] if signal_session else None
    )
    return {
        "rebalance_session": latest_session,
        "signal_session": signal_session,
        "signal_month": signal_month,
        "weights": weights,
    }


def _resolve_account_equity(root: Path, override: float | None) -> tuple[float, str | None, str]:
    if override is not None:
        return float(override), None, "account_equity_override"
    account_path = root / "reports" / "paper" / "account.json"
    if not account_path.is_file():
        raise ValueError(
            "insider_buy_portfolio sizing needs a live account-equity snapshot; run "
            "`oc paper sync-account` first (reports/paper/account.json is missing)."
        )
    payload = json.loads(account_path.read_text(encoding="utf-8"))
    equity = payload.get("equity")
    if equity is None or float(equity) <= 0:
        raise ValueError(f"reports/paper/account.json has no positive 'equity' field: {payload}")
    return float(equity), payload.get("generated_at"), "reports/paper/account.json"


def build_insider_rows(
    *,
    spec: StrategySpec,
    weights: dict[str, float],
    previous_weights: dict[str, float],
    sizing: WholeShareSizing,
    price_lookup: dict[str, float],
    price_sessions: dict[str, date],
    equity: float,
    signal_date: date,
    rebalance_session: date,
    is_new_signal: bool,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    """One target row per symbol currently selected or just dropped, and one
    order intent per changed weight (only on a fresh signal). Pure."""
    rebalance_id = f"{spec.name}:{rebalance_session.isoformat()}"
    target_rows: list[dict[str, object]] = []
    intents: list[dict[str, object]] = []
    for symbol in sorted(set(weights) | set(previous_weights)):
        target_weight = float(weights.get(symbol, 0.0))
        previous_weight = float(previous_weights.get(symbol, 0.0))
        delta = target_weight - previous_weight
        price = price_lookup.get(symbol)
        target_rows.append(
            {
                "rebalance_id": rebalance_id,
                "rebalance_session": rebalance_session.isoformat(),
                "signal_session": signal_date.isoformat(),
                "time_rule": TIME_RULE,
                "symbol": symbol,
                "side": "buy" if target_weight > 1e-12 else "sell",
                "target_weight": target_weight,
                "shares": int(sizing.shares.get(symbol, 0)),
                "realized_weight": float(sizing.realized_weights.get(symbol, 0.0)),
                "reference_price": float(price) if price else None,
                "price_session": (
                    price_sessions[symbol].isoformat() if symbol in price_sessions else None
                ),
                "sizing_equity": float(equity),
                "leg": "insider_buy",
                "selected": target_weight > 1e-12,
                "state": "signal" if is_new_signal else "hold_no_new_signal",
                "source": SOURCE_TAG,
            }
        )
        if is_new_signal and abs(delta) > 1e-9:
            intents.append(
                {
                    "rebalance_id": rebalance_id,
                    "rebalance_session": rebalance_session.isoformat(),
                    "time_rule": TIME_RULE,
                    "symbol": symbol,
                    "from_weight": previous_weight,
                    "to_weight": target_weight,
                    "delta_weight": delta,
                    "side": "buy" if delta > 0 else "sell",
                    "intent_type": "set_insider_buy_target_weight",
                    "requires_order": True,
                    "broker_writes": False,
                }
            )
    return target_rows, intents


def _sessions_between(earlier: date, later: date) -> int:
    if later <= earlier:
        return 0
    return max(len(us_equity_session_dates(earlier, later)) - 1, 0)


# ---------------------------------------------------------------------------
# entry point


def run_insider_portfolio_target_weight_mapping(
    spec_path: Path,
    root: Path | None = None,
    *,
    now: datetime | None = None,
    account_equity_override: float | None = None,
    memory_limit: str = DEFAULT_MEMORY_LIMIT,
) -> InsiderPortfolioTargetWeightResult:
    base = root or project_root()
    stamp = now or datetime.now(UTC)
    spec = load_strategy_spec(spec_path)
    if spec.portfolio.mode != "insider_buy_portfolio" or spec.portfolio.insider_buy is None:
        raise ValueError(
            "insider target mapping requires portfolio.mode=insider_buy_portfolio with "
            "portfolio.insider_buy"
        )
    if spec.execution.mode != "manual_signal" or spec.execution.broker != "none":
        raise ValueError(
            "insider_buy_portfolio target-weight mapping is observation-only and requires "
            "execution.mode=manual_signal, execution.broker=none"
        )
    params = spec.portfolio.insider_buy
    warnings: list[str] = []

    universe_root = resolve_feature_root(
        base, params.universe_root, params.universe_fallback_root, label="universe"
    )
    insider_root = resolve_feature_root(
        base,
        params.insider_feature_root,
        params.insider_feature_fallback_root,
        label="insider_features",
    )
    warnings.extend(w for w in (universe_root.warning, insider_root.warning) if w)

    bound = last_completed_us_equity_session(stamp, spec.data_assumptions.timezone)
    feature_date = latest_insider_feature_date(
        insider_root.path, not_after=bound, memory_limit=memory_limit
    )
    feature_lag = _sessions_between(feature_date.date(), bound)
    if feature_lag > 1:
        warnings.append(
            f"insider table is {feature_lag} sessions behind the last completed session "
            f"({feature_date.date()} vs {bound}); run scripts/refresh_insider_features_for_paper.sh"
        )
    cohort, month_end = load_universe_cohort(
        universe_root.path, as_of=feature_date, memory_limit=memory_limit
    )
    band = cohort
    if params.adv_rank_min is not None:
        band = band.loc[band["adv_rank"] >= int(params.adv_rank_min)]
    if params.adv_rank_max is not None:
        band = band.loc[band["adv_rank"] <= int(params.adv_rank_max)]

    previous = _read_previous_snapshot(base, spec.name)
    signal_month = f"{feature_date:%Y-%m}"
    reuse_previous = bool(
        previous is not None
        and previous.get("signal_month") == signal_month
        and previous.get("weights")
    )

    insider_rows_in_band = None
    eligible_count = None
    selection: BookSelection
    if reuse_previous:
        assert previous is not None
        held = list(previous["weights"])
        closes, price_sessions, reference_session = load_latest_closes(
            base,
            held,
            as_of=bound,
            lookback_sessions=params.stale_bar_sessions,
            memory_limit=memory_limit,
        )
        selection = BookSelection(
            weights=dict(previous["weights"]),
            weight_per_name=max(previous["weights"].values()) if previous["weights"] else 0.0,
            gross_effective=float(sum(previous["weights"].values())),
            gross_scaled_down=False,
            skipped_stale=tuple(s for s in held if s not in closes),
            eligible_ranked=tuple(held),
        )
        is_new_signal = False
        rebalance_session = date.fromisoformat(str(previous["rebalance_session"]))
        signal_date = (
            date.fromisoformat(str(previous["signal_session"]))
            if previous.get("signal_session")
            else feature_date.date()
        )
    else:
        columns = list(dict.fromkeys([*REQUIRED_INSIDER_COLUMNS, params.rank_column]))
        insider_frame = load_insider_cross_section(
            insider_root.path, trade_date=feature_date, columns=columns, memory_limit=memory_limit
        )
        if insider_frame.empty:
            raise ValueError(
                f"insider table has no rows on feature date {feature_date.date()} under "
                f"{insider_root.path}"
            )
        insider_rows_in_band = int(
            insider_frame["symbol"].astype(str).str.upper().isin(set(band["symbol"])).sum()
        )
        ranked = rank_eligible_candidates(insider_frame, cohort, params)
        eligible_count = int(len(ranked))
        closes, price_sessions, reference_session = load_latest_closes(
            base,
            ranked["symbol"].tolist(),
            as_of=bound,
            lookback_sessions=params.stale_bar_sessions,
            memory_limit=memory_limit,
        )
        selection = finalize_book(
            ranked, stale_symbols=set(ranked["symbol"]) - set(closes), params=params
        )
        if not selection.weights:
            raise ValueError(
                "insider_buy_portfolio selected zero eligible symbols for feature date "
                f"{feature_date.date()} (universe_in_band={len(band)}, eligible={eligible_count}, "
                f"stale={len(selection.skipped_stale)}); refusing to write an empty fresh signal"
            )
        is_new_signal = True
        if reference_session is None:
            reference_session = bound
        rebalance_session = next_us_equity_session(reference_session)
        signal_date = feature_date.date()
    if selection.gross_scaled_down:
        warnings.append(
            f"per-name cap {params.per_name_cap} binds with {len(selection.weights)} names: gross "
            f"scaled down to {selection.gross_effective:.4f} (target {params.gross_target})"
        )
    if selection.skipped_stale:
        warnings.append(
            f"skipped {len(selection.skipped_stale)} name(s) with no daily bar in the last "
            f"{params.stale_bar_sessions} sessions: {list(selection.skipped_stale)[:20]}"
        )

    previous_weights = dict(previous["weights"]) if previous is not None else {}
    equity, equity_generated_at, equity_source = _resolve_account_equity(
        base, account_equity_override
    )
    priced = {s: closes[s] for s in selection.weights if s in closes}
    sizing = size_whole_share_portfolio(selection.weights, priced, equity)
    target_rows, intents = build_insider_rows(
        spec=spec,
        weights=selection.weights,
        previous_weights=previous_weights,
        sizing=sizing,
        price_lookup=closes,
        price_sessions=price_sessions,
        equity=equity,
        signal_date=signal_date,
        rebalance_session=rebalance_session,
        is_new_signal=is_new_signal,
    )

    def _rel(path: Path) -> str:
        try:
            return path.relative_to(base).as_posix()
        except ValueError:
            return path.as_posix()

    manifest: dict[str, Any] = {
        "mapping_mode": MAPPING_MODE,
        "hypothesis_card": "H-20260917-01",
        "as_of_utc": stamp.astimezone(UTC).isoformat(),
        "feature_date_bound_last_completed_session": bound.isoformat(),
        "insider_feature_date": feature_date.date().isoformat(),
        "insider_feature_lag_sessions": feature_lag,
        "insider_feature_root": _rel(insider_root.path),
        "insider_feature_root_requested": insider_root.requested,
        "insider_root_fallback_used": insider_root.fallback_used,
        "universe_root": _rel(universe_root.path),
        "universe_root_requested": universe_root.requested,
        "universe_root_fallback_used": universe_root.fallback_used,
        "universe_month_end": month_end.date().isoformat(),
        "universe_size": int(len(cohort)),
        "adv_rank_band": [params.adv_rank_min, params.adv_rank_max],
        "universe_in_band": int(len(band)),
        "insider_rows_in_band": insider_rows_in_band,
        "thresholds": {
            "min_open_market_buy_count_60d": params.min_open_market_buy_count_60d,
            "min_net_buy_usd_60d": params.min_net_buy_usd_60d,
            "min_buyers_60d": params.min_buyers_60d,
        },
        "rank_column": params.rank_column,
        "max_names": params.max_names,
        "eligible_after_thresholds": eligible_count,
        "skipped_stale": list(selection.skipped_stale),
        "skipped_stale_count": len(selection.skipped_stale),
        "selected_count": len(selection.weights),
        "weight_per_name": selection.weight_per_name,
        "gross_target": params.gross_target,
        "per_name_cap": params.per_name_cap,
        "gross_effective": selection.gross_effective,
        "gross_scaled_down": selection.gross_scaled_down,
        "reference_price_session": reference_session.isoformat() if reference_session else None,
        "rebalance_session": rebalance_session.isoformat(),
        "signal_month": signal_month,
        "is_new_signal": is_new_signal,
        "unpriced_selected": sorted(s for s in selection.weights if s not in closes),
        "warnings": warnings,
    }

    data_profile = {
        "source_mode": "cache",
        "provider": "alpaca_sip_daily_archive+sec_form4_insider_features",
        "feed": spec.data.feed or "",
        "insider_feature_root": manifest["insider_feature_root"],
        "universe_root": manifest["universe_root"],
        "insider_feature_date": manifest["insider_feature_date"],
        "universe_month_end": manifest["universe_month_end"],
        "reference_price_session": manifest["reference_price_session"],
        "fallbacks": {
            "insider_root_fallback_used": insider_root.fallback_used,
            "universe_root_fallback_used": universe_root.fallback_used,
        },
    }
    if sizing.unaffordable:
        warnings.append(f"unaffordable_at_current_equity={list(sizing.unaffordable)}")
    parity_check = {
        "status": "ok",
        "blockers": [],
        "warnings": warnings,
        "is_new_signal": is_new_signal,
    }
    acquisition_tier = infer_acquisition_tier(
        data_source=spec.data.source,
        data_profile=data_profile,
        explicit=spec.data_assumptions.acquisition_tier,
        refresh_data=False,
    )
    mapping_summary = {
        **manifest,
        "selection_manifest": manifest,
        "weight_deviation": sizing.weight_deviation,
        "idle_cash": sizing.idle_cash,
        "idle_cash_fraction": sizing.idle_cash_fraction,
        "invested_cash": sizing.invested_cash,
        "unaffordable": list(sizing.unaffordable),
        "account_equity": equity,
        "account_equity_generated_at": equity_generated_at,
        "account_equity_source": equity_source,
        "paper_order_authorization": False,
        "broker_writes": False,
    }
    artifacts = write_router_execution_artifacts(
        root=base,
        spec_path=spec_path,
        spec=spec,
        target_rows=target_rows,
        rebalance_intents=intents,
        data_profile=data_profile,
        route_label=None,
        mapping_summary=mapping_summary,
        acquisition_tier=acquisition_tier,
        parity_check=parity_check,
        target_backend="python_reference",
    )
    json_path = artifacts["router_target_weights"]
    report_path = json_path.with_suffix(".md")

    signals = (
        _build_signals(
            spec=spec,
            intents=intents,
            price_lookup=closes,
            signal_date=signal_date,
            manifest=manifest,
        )
        if is_new_signal
        else []
    )
    signal_log_path = base / "signal_logs" / f"insider-buy-{spec.name}.jsonl"
    if signals:
        append_jsonl(signal_log_path, [model_to_record(signal) for signal in signals])
    else:
        signal_log_path.parent.mkdir(parents=True, exist_ok=True)
        signal_log_path.touch(exist_ok=True)

    _write_report(
        report_path,
        spec=spec,
        target_rows=target_rows,
        sizing=sizing,
        manifest=manifest,
        json_path=json_path,
        signal_log_path=signal_log_path,
        signal_count=len(signals),
    )
    return InsiderPortfolioTargetWeightResult(
        report_path=report_path,
        json_path=json_path,
        signal_log_path=signal_log_path,
        target_weight_count=len(target_rows),
        rebalance_sessions=len({row["rebalance_session"] for row in target_rows}),
        nonzero_target_rows=sum(bool(row["selected"]) for row in target_rows),
        parity_status=str(parity_check["status"]),
        is_new_signal=is_new_signal,
        signal_count=len(signals),
        manifest=manifest,
    )


def _build_signals(
    *,
    spec: StrategySpec,
    intents: list[dict[str, object]],
    price_lookup: dict[str, float],
    signal_date: date,
    manifest: dict[str, Any],
) -> list[Any]:
    spec_hash = strategy_content_hash(spec)
    run_id = f"insider-buy-{spec.name}"
    timestamp = datetime.combine(signal_date, time(20, 0), tzinfo=UTC)
    conditions = [
        f"insider_feature_date={manifest['insider_feature_date']}",
        f"universe_month_end={manifest['universe_month_end']}",
        f"rank_column={manifest['rank_column']}",
        f"thresholds={json.dumps(manifest['thresholds'], sort_keys=True)}",
        f"insider_root_fallback_used={manifest['insider_root_fallback_used']}",
        f"universe_root_fallback_used={manifest['universe_root_fallback_used']}",
    ]
    signals = []
    for intent in intents:
        symbol = str(intent["symbol"])
        delta = float(intent["delta_weight"])
        signals.append(
            build_signal(
                spec,
                run_id=run_id,
                timestamp=timestamp,
                action="entry" if delta > 0 else "exit",
                source=SIGNAL_SOURCE,
                price=price_lookup.get(symbol, 0.0),
                spec_hash=spec_hash,
                symbol=symbol,
                target_weight=float(intent["to_weight"]),
                conditions=conditions,
            )
        )
    return signals


def _write_report(
    path: Path,
    *,
    spec: StrategySpec,
    target_rows: list[dict[str, object]],
    sizing: WholeShareSizing,
    manifest: dict[str, Any],
    json_path: Path,
    signal_log_path: Path,
    signal_count: int,
) -> None:
    held = sorted(
        (row for row in target_rows if row["selected"]), key=lambda row: str(row["symbol"])
    )
    lines = [
        f"# Insider-Buy Target Weights: {spec.name}",
        "",
        f"- JSON: `{json_path}`",
        f"- Signal log: `{signal_log_path}`",
        f"- New signal this run: `{manifest['is_new_signal']}` "
        f"(signal month `{manifest['signal_month']}`)",
        f"- Insider feature date: `{manifest['insider_feature_date']}` "
        f"(bound `{manifest['feature_date_bound_last_completed_session']}`, "
        f"lag `{manifest['insider_feature_lag_sessions']}` sessions)",
        f"- Insider root: `{manifest['insider_feature_root']}` "
        f"(fallback used: `{manifest['insider_root_fallback_used']}`)",
        f"- Universe root: `{manifest['universe_root']}` "
        f"(fallback used: `{manifest['universe_root_fallback_used']}`), cohort month end "
        f"`{manifest['universe_month_end']}`, size `{manifest['universe_size']}`, "
        f"in band `{manifest['universe_in_band']}`",
        f"- Eligible after thresholds: `{manifest['eligible_after_thresholds']}`; skipped stale: "
        f"`{manifest['skipped_stale_count']}`; selected: `{manifest['selected_count']}`",
        f"- Weight per name: `{manifest['weight_per_name']:.4f}`; gross effective: "
        f"`{manifest['gross_effective']:.4f}` (target `{manifest['gross_target']}`, "
        f"scaled down: `{manifest['gross_scaled_down']}`)",
        f"- Reference price session: `{manifest['reference_price_session']}`; rebalance session: "
        f"`{manifest['rebalance_session']}`",
        f"- Signals logged this run: `{signal_count}`",
        f"- Idle cash: `{sizing.idle_cash:.2f}` ({sizing.idle_cash_fraction:.4%})",
        f"- Weight deviation: `{sizing.weight_deviation:.4%}`",
        f"- Unaffordable names: `{list(sizing.unaffordable) or 'none'}`",
        "- Broker writes: `false`",
        "",
        "## Holdings" if held else "## Holdings (none)",
        "",
    ]
    if held:
        lines.extend(
            [
                "| symbol | target weight | shares | reference price | price session |",
                "| --- | --- | --- | --- | --- |",
            ]
        )
        lines.extend(
            f"| {row['symbol']} | {float(row['target_weight']):.4f} | {row['shares']} | "
            f"{row['reference_price'] if row['reference_price'] is not None else '-'} | "
            f"{row['price_session'] or '-'} |"
            for row in held
        )
    lines.append("")
    if manifest.get("warnings"):
        lines.append("## Warnings")
        lines.append("")
        lines.extend(f"- {warning}" for warning in manifest["warnings"])
        lines.append("")
    lines.append("## Selection manifest")
    lines.append("")
    lines.append("```json")
    lines.append(json.dumps(manifest, indent=2, ensure_ascii=False, default=str))
    lines.append("```")
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")
