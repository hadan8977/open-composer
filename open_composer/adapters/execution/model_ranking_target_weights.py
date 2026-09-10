"""Step 11 Wave C: ``portfolio.mode=model_ranking_portfolio`` -> target weights.

docs/plan-step-11-ml-first-loop-2026-09-06.zh.md section 5, item 2. Observation
mode only: this module never submits broker orders. It reads the most recent
trading day's row from the Wave A feature library
(``open_composer.research.features``, read-only reference from this side),
scores the point-in-time (PIT) universe with whatever candidate artifact
``portfolio.candidate_artifact_dir`` points at, keeps the top
``portfolio.top_k`` names equal-weight (plus an optional SPY beta-hedge leg),
converts the result to whole shares against the live paper account's equity
(:mod:`open_composer.adapters.execution.whole_share_sizing`), and writes the
same ``reports/execution/{name}-target-weights.json`` shape every other
target-weight adapter writes (:func:`write_router_execution_artifacts`).

**Weekly-hold contract**: a rebalance is only computed on the last US-equity
trading session of an ISO calendar week (the plan's "周五收盘出信号" -- a
short holiday week's final session stands in, matching
``open_composer.research.kernel.loop.weekly_rebalance_dates``). Every other
day this module re-emits the previously written targets untouched
(``state=hold_no_new_signal``), which is why every rebalance/order-intent row
is only produced when something actually changed -- see
:func:`build_model_ranking_rows`. That is also what keeps a strategy with
zero broker positions safe on its very first run: there is nothing to diff
against, so the first computed signal *is* the full target (never an empty
one).

**Scoring path mirrors the research loop on purpose**
(``open_composer.research.kernel.loop.build_weight_schedule``, its top-K +
hedge block): same equal-weight rule, same
``weights["__SPY_HEDGE__"] = -portfolio_beta`` hedge convention, same
``weekly_rebalance_dates``/``universe_as_of_calendar_month`` helpers, imported
rather than re-derived. The one deliberate product-side difference, called
out in that module's own docstring, is execution timing: the research loop
close-marks returns for backtest simplicity, while this adapter targets the
StrategySpec's actual ``execution_policy.order_style=opg_limit`` -- the
signal date's close decides the book, and :func:`next_us_equity_session`
names the session whose opening auction is supposed to execute it.

**Step 13 Track M additions (risk-adjusted rule score + trend gate)**: a
candidate's ``config.json`` may declare ``score_expression`` (an explicit
two-column ratio, e.g. ``{"numerator": "momentum_252_21", "denominator":
"vol_63"}`` -- never an arbitrary evaluated string) instead of a single
``score_column``, and/or a ``trend_gate`` block (``{"benchmark": "SPY",
"sma_days": 200, "cash_symbol": "BIL"}``) that routes the whole book to the
cash symbol on rebalance weeks where the benchmark closes below its own
trailing SMA. Both are additive and opt-in per candidate: a candidate whose
``config.json`` sets neither key (e.g. the existing
``step11_momentum_placeholder_v1``) is scored exactly as before, with zero
extra I/O. See :func:`load_candidate_artifact` and :func:`trend_gate_state`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Any, Protocol

import duckdb
import numpy as np
import pandas as pd

from open_composer.adapters.data.sip_parquet import load_sip_bars
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
from open_composer.market_calendar import next_us_equity_session, us_equity_session_close
from open_composer.models.strategy_spec import StrategySpec, load_strategy_spec
from open_composer.research.kernel.loop import universe_as_of_calendar_month
from open_composer.storage import append_jsonl, model_to_record
from open_composer.strategy_versions import strategy_content_hash

#: Step 11's hard memory discipline (docs/plan.../CLAUDE.md): this box has
#: 3.9GB RAM configured to sacrifice the agent session first under pressure.
#: Every feature-library read in this module goes through DuckDB with this
#: cap, and every query is scoped to a single trading day or a single
#: already-small universe file -- never a whole multi-GB panel.
DEFAULT_FEATURE_MEMORY_LIMIT = "1.2GB"
HEDGE_SYMBOL = "SPY"
#: Internal-only pseudo-symbol for the beta-hedge leg, matching
#: ``open_composer.research.kernel.loop.build_weight_schedule``'s convention
#: exactly so the two code paths stay conceptually identical.
HEDGE_KEY = "__SPY_HEDGE__"
#: Not part of the candidate-artifact interface (features.json has no
#: beta_column key) -- there is exactly one beta column in the shared
#: feature library (open_composer/research/features/daily_features.py),
#: so this is a fixed constant, not a per-candidate configurable.
DEFAULT_BETA_COLUMN = "beta_252_spy"


class ScoringModel(Protocol):
    def score(self, asof_frame: pd.DataFrame) -> pd.Series: ...


@dataclass(frozen=True)
class MomentumPlaceholderModel:
    """Rule-based stand-in: sort one already-computed feature column
    descending. No ``model.joblib`` required -- this is the "12-1 momentum
    top 50" placeholder the plan calls for so the product path can be
    exercised before the research line's fitted candidate lands (plan
    section 5, item 4). Implements the same ``.score()`` contract as
    ``open_composer.research.kernel.loop.RankingStrategy`` so swapping in a
    real fitted model later changes zero lines in this module.
    """

    score_column: str

    def score(self, asof_frame: pd.DataFrame) -> pd.Series:
        return asof_frame.set_index("symbol")[self.score_column].astype(float)


@dataclass(frozen=True)
class DerivedRatioScoreModel:
    """Rule-based stand-in, generalizing :class:`MomentumPlaceholderModel`
    from a single ranked column to a risk-adjusted ratio of two already-
    computed feature columns (Step 13 Track M, e.g. ``momentum_252_21 /
    vol_63``): no ``model.joblib`` required, same
    ``open_composer.research.kernel.loop.RankingStrategy``-compatible
    ``.score()`` contract as the single-column placeholder. Matches the
    research grid's own derivation (``scripts/run_step13_m_grid.py``'s
    ``stage_m0b``: ``panel["momentum_252_21_over_vol_63"] = (momentum_252_21
    / vol_63).replace([inf, -inf], nan)``) -- the product side computes the
    same ratio live from the two named columns instead of requiring a
    precomputed derived column in ``data/features/daily/``, since that
    table only ever carries the raw factor columns.
    """

    numerator_column: str
    denominator_column: str

    def score(self, asof_frame: pd.DataFrame) -> pd.Series:
        frame = asof_frame.set_index("symbol")
        numerator = frame[self.numerator_column].astype(float)
        denominator = frame[self.denominator_column].astype(float)
        ratio = numerator / denominator
        return ratio.replace([np.inf, -np.inf], np.nan)


@dataclass(frozen=True)
class CandidateArtifact:
    candidate_dir: Path
    config: dict[str, Any]
    features: dict[str, Any]
    model: ScoringModel
    is_placeholder: bool


def load_candidate_artifact(candidate_artifact_dir: Path) -> CandidateArtifact:
    """Load ``config.json``/``features.json`` (and ``model.joblib`` if
    present) from a candidate artifact directory, per the research line's
    authoritative export interface (``reports/research/control/step11-2026-
    09-06-progress.md``, "Wave B item 5", commit ``93ba159``): ``model.joblib``
    is a ``joblib.dump()`` of a ``loop.RankingStrategy``-protocol object --
    it already implements ``.score(asof_frame) -> pd.Series`` itself, so it
    is used directly with no adapter/wrapper class, exactly as that section
    specifies ("调用方自己做 top-K/等权,这里不重复造轮子" -- the caller does
    its own top-K/equal-weight; this module never calls ``.predict()``).
    ``features.json`` always carries ``feature_columns`` (exact training
    order); every other key that interface defines
    (``experiment_id``/``family``/``model_kind``/``feature_set``/
    ``label_column``/``execution``/``refit_through_date``/...) is metadata
    this module does not need to act on. Raises ``ValueError`` with an
    explicit, actionable message on every failure mode -- this is the
    function ``tests/test_model_ranking_target_weights.py``'s
    missing-artifact coverage exercises directly.

    Every real export always has ``model.joblib`` (per that same interface
    note: "B0/B1 没有可学习的参数,model.joblib 依然写出... 接口统一" -- even
    parameter-free candidates ship one). The ``model.joblib``-less fallback
    below is this module's *own* rule-based placeholder convention only
    (``config/model_ranking_candidates/step11_momentum_placeholder_v1``,
    used before the research line's first real export lands): it reuses the
    interface's own ``model_kind`` field (rather than inventing a new key)
    with the sentinel value ``"rule_momentum_top_k"``, plus one genuinely
    new field, ``score_column``, naming which ``feature_columns`` entry to
    rank on directly -- there is no interface-defined way to say "no model,
    just sort this column," because every real candidate has a model.
    """
    if not candidate_artifact_dir.is_dir():
        raise ValueError(
            "model_ranking_portfolio candidate_artifact_dir does not exist: "
            f"{candidate_artifact_dir}. Point portfolio.candidate_artifact_dir at a "
            "directory containing config.json and features.json (plus model.joblib "
            "for a fitted candidate; omit it for a rule-based placeholder)."
        )
    config_path = candidate_artifact_dir / "config.json"
    features_path = candidate_artifact_dir / "features.json"
    for label, path in (("config.json", config_path), ("features.json", features_path)):
        if not path.is_file():
            raise ValueError(
                f"model_ranking_portfolio candidate artifact at {candidate_artifact_dir} is "
                f"missing {label}"
            )
    config = json.loads(config_path.read_text(encoding="utf-8"))
    features = json.loads(features_path.read_text(encoding="utf-8"))
    feature_columns = features.get("feature_columns")
    if not feature_columns or not isinstance(feature_columns, list):
        raise ValueError(f"{features_path} must declare a non-empty 'feature_columns' list")
    model_path = candidate_artifact_dir / "model.joblib"
    if model_path.is_file():
        import joblib

        fitted = joblib.load(model_path)
        if not hasattr(fitted, "score") or not callable(fitted.score):
            raise ValueError(
                f"{model_path} does not implement the required .score(asof_frame) method "
                "(loop.RankingStrategy protocol); refusing to use it for scoring"
            )
        return CandidateArtifact(
            candidate_dir=candidate_artifact_dir,
            config=config,
            features=features,
            model=fitted,
            is_placeholder=False,
        )
    score_expression = config.get("score_expression")
    if score_expression is not None:
        if config.get("model_kind") != "rule_derived_ratio_top_k":
            raise ValueError(
                f"{config_path} declares score_expression but model_kind="
                f"{config.get('model_kind')!r}, not 'rule_derived_ratio_top_k'"
            )
        if not isinstance(score_expression, dict):
            raise ValueError(
                f"{config_path}:score_expression must be an object with 'numerator' and "
                f"'denominator' column names, got {score_expression!r}"
            )
        numerator = score_expression.get("numerator")
        denominator = score_expression.get("denominator")
        if not numerator or not denominator:
            raise ValueError(
                f"{config_path}:score_expression must declare non-blank 'numerator' and "
                f"'denominator' column names, got {score_expression!r}"
            )
        for label, column in (("numerator", numerator), ("denominator", denominator)):
            if column not in feature_columns:
                raise ValueError(
                    f"{config_path}:score_expression.{label}={column!r} is not in "
                    f"{features_path}:feature_columns={feature_columns!r}"
                )
        return CandidateArtifact(
            candidate_dir=candidate_artifact_dir,
            config=config,
            features=features,
            model=DerivedRatioScoreModel(
                numerator_column=str(numerator), denominator_column=str(denominator)
            ),
            is_placeholder=True,
        )

    score_column = config.get("score_column")
    if not score_column or config.get("model_kind") != "rule_momentum_top_k":
        raise ValueError(
            f"candidate at {candidate_artifact_dir} has no model.joblib and config.json does "
            "not declare model_kind=rule_momentum_top_k with a score_column; cannot score"
        )
    if score_column not in feature_columns:
        raise ValueError(
            f"{config_path}:score_column={score_column!r} is not in "
            f"{features_path}:feature_columns={feature_columns!r}"
        )
    return CandidateArtifact(
        candidate_dir=candidate_artifact_dir,
        config=config,
        features=features,
        model=MomentumPlaceholderModel(score_column=str(score_column)),
        is_placeholder=True,
    )


def latest_available_trade_date(
    root: Path, *, memory_limit: str = DEFAULT_FEATURE_MEMORY_LIMIT
) -> pd.Timestamp:
    """The most recent ``trade_date`` present anywhere under
    ``data/features/daily/``, read one (small, single-year) file at a time.
    """
    daily_dir = root / "data" / "features" / "daily"
    years = sorted(
        (int(p.stem) for p in daily_dir.glob("*.parquet") if p.stem.isdigit()), reverse=True
    )
    if not years:
        raise ValueError(f"no daily feature files found under {daily_dir}")
    con = duckdb.connect()
    try:
        con.execute(f"SET memory_limit='{memory_limit}'")
        for year in years:
            path = daily_dir / f"{year}.parquet"
            value = con.execute(
                "SELECT max(trade_date) FROM read_parquet(?)", [str(path)]
            ).fetchone()[0]
            if value is not None:
                return pd.Timestamp(value)
    finally:
        con.close()
    raise ValueError(f"every daily feature file under {daily_dir} is empty")


def load_daily_feature_row(
    root: Path,
    *,
    trade_date: pd.Timestamp,
    columns: list[str],
    memory_limit: str = DEFAULT_FEATURE_MEMORY_LIMIT,
) -> pd.DataFrame:
    """One trading day's cross-section, narrowed to ``columns`` (plus
    ``symbol``/``trade_date``) at the DuckDB layer so this never has to hold
    a whole year's panel in memory to read one day.
    """
    daily_dir = root / "data" / "features" / "daily"
    path = daily_dir / f"{trade_date.year}.parquet"
    if not path.is_file():
        raise ValueError(f"no daily feature file for year {trade_date.year} at {path}")
    column_list = ", ".join(dict.fromkeys(["symbol", "trade_date", *columns]))
    con = duckdb.connect()
    try:
        con.execute(f"SET memory_limit='{memory_limit}'")
        frame = con.execute(
            f"SELECT {column_list} FROM read_parquet(?) WHERE trade_date = ?",  # noqa: S608
            [str(path), trade_date.to_pydatetime()],
        ).fetchdf()
    finally:
        con.close()
    return frame


def load_latest_universe_cohort(
    root: Path,
    *,
    top_n: int,
    as_of: pd.Timestamp,
    memory_limit: str = DEFAULT_FEATURE_MEMORY_LIMIT,
) -> tuple[set[str], pd.Timestamp]:
    """The PIT top-``top_n``-by-ADV cohort in effect on ``as_of``, reusing
    ``open_composer.research.kernel.loop.universe_as_of_calendar_month``
    (imported, not re-derived) for the exact calendar-month-cohort semantics
    the research line already tested.
    """
    universe_dir = root / "data" / "features" / "universe"
    years = sorted(int(p.stem) for p in universe_dir.glob("*.parquet") if p.stem.isdigit())
    candidates = [year for year in years if year <= as_of.year]
    if not candidates:
        raise ValueError(f"no universe file at or before {as_of.date()} under {universe_dir}")
    path = universe_dir / f"{max(candidates)}.parquet"
    con = duckdb.connect()
    try:
        con.execute(f"SET memory_limit='{memory_limit}'")
        frame = con.execute(
            "SELECT month_end, symbol, adv_rank FROM read_parquet(?) "
            "WHERE adv_rank <= ? AND month_end <= ?",
            [str(path), int(top_n), as_of.to_pydatetime()],
        ).fetchdf()
    finally:
        con.close()
    if frame.empty:
        raise ValueError(
            f"universe file {path} has no adv_rank<={top_n} rows at/before {as_of.date()}"
        )
    frame["month_end"] = pd.to_datetime(frame["month_end"])
    cohort_symbols = universe_as_of_calendar_month(frame, as_of)
    if not cohort_symbols:
        raise ValueError(f"universe_as_of_calendar_month found no cohort for {as_of.date()}")
    cohort_month_end = frame.loc[frame["symbol"].isin(cohort_symbols), "month_end"].max()
    return cohort_symbols, pd.Timestamp(cohort_month_end)


def _sip_closes_on_or_before(
    root: Path, symbol: str, *, as_of: pd.Timestamp, lookback_days: int
) -> pd.DataFrame:
    """``symbol``'s SIP daily bars in ``(as_of - lookback_days, as_of]``,
    deduplicated to one row per ``trade_date`` -- the same raw-archive path
    the research line's trend-gate machinery reads
    (``scripts/run_step13_m_grid.py``'s ``_spy_close_and_returns``/
    ``_bil_returns``), used here instead of ``data/features/daily/`` because
    that table only carries the ranked equity universe, never a trend-gate
    benchmark or a cash leg (verified empty for both SPY and BIL, 2026-09-10).
    ``root`` is the same project-root parameter every other loader in this
    module takes (``load_sip_bars``'s own archive root is ``root/data/sip``),
    so tests can point this at a hermetic fixture archive instead of the
    real repo.
    """
    start = (as_of - pd.Timedelta(days=int(lookback_days))).to_pydatetime()
    raw = load_sip_bars(
        symbol,
        frequency="daily",
        start=start,
        end=as_of.to_pydatetime(),
        root=root / "data" / "sip",
    )
    rows = raw.loc[raw["symbol"] == symbol].copy()
    if rows.empty:
        return rows
    rows["trade_date"] = pd.to_datetime(pd.to_datetime(rows["timestamp"], utc=True).dt.date)
    rows = rows.sort_values("trade_date").drop_duplicates("trade_date", keep="last")
    return rows.loc[rows["trade_date"] <= as_of]


def trend_gate_state(
    root: Path, trend_gate: dict[str, Any], *, as_of: pd.Timestamp
) -> tuple[bool, dict[str, Any]]:
    """Whether ``trend_gate`` (``{"benchmark": "SPY", "sma_days": 200,
    "cash_symbol": "BIL"}``, Step 13 Track M's product config block) is open
    as of ``as_of``: ``benchmark``'s latest close vs. the simple mean of its
    trailing ``sma_days`` closes, inclusive of ``as_of`` itself -- the same
    formula the research line's ``spy_gap_200sma`` uses
    (``scripts/build_step13_regime_daily_features.py``:
    ``close.rolling(200, min_periods=200).mean()``, gate open iff
    ``close/sma - 1 > 0``). Raises ``ValueError`` if fewer than ``sma_days``
    sessions of history are available on/before ``as_of`` -- a silently
    short window would silently mismark the gate, which this product path
    must never do.
    """
    benchmark = str(trend_gate.get("benchmark") or "SPY")
    sma_days = int(trend_gate.get("sma_days") or 200)
    closes = _sip_closes_on_or_before(root, benchmark, as_of=as_of, lookback_days=sma_days * 2 + 30)
    if len(closes) < sma_days:
        raise ValueError(
            f"trend_gate needs {sma_days} trading sessions of {benchmark} history on/before "
            f"{as_of.date()}, found {len(closes)} under {root / 'data' / 'sip' / 'daily'}"
        )
    window = closes.tail(sma_days)
    window_close = pd.to_numeric(window["close"], errors="raise")
    sma = float(window_close.mean())
    latest_close = float(window_close.iloc[-1])
    is_open = latest_close > sma
    detail = {
        "benchmark": benchmark,
        "sma_days": sma_days,
        "as_of": as_of.date().isoformat(),
        "close": latest_close,
        "sma": sma,
        "gap": latest_close / sma - 1.0,
        "gate_open": is_open,
    }
    return is_open, detail


def _latest_sip_close(
    root: Path, symbol: str, *, as_of: pd.Timestamp, lookback_days: int = 10
) -> float:
    """Most recent SIP daily close for ``symbol`` on/before ``as_of`` --
    used for the trend gate's cash leg (e.g. BIL), which never appears in
    ``data/features/daily/`` (see :func:`_sip_closes_on_or_before`).
    """
    closes = _sip_closes_on_or_before(root, symbol, as_of=as_of, lookback_days=lookback_days)
    if closes.empty:
        raise ValueError(f"no SIP daily close for {symbol!r} on/before {as_of.date()}")
    return float(pd.to_numeric(closes["close"], errors="raise").iloc[-1])


def score_and_select(
    *,
    asof_frame: pd.DataFrame,
    universe_symbols: set[str],
    model: ScoringModel,
    top_k: int,
    hedge: str,
    beta_column: str,
    feature_columns: tuple[str, ...],
) -> tuple[dict[str, float], float | None]:
    """Top-K equal weight (+ optional SPY beta hedge), mirroring
    ``open_composer.research.kernel.loop.build_weight_schedule``'s scoring
    block exactly (see module docstring).
    """
    eligible = asof_frame.loc[asof_frame["symbol"].isin(universe_symbols)].dropna(
        subset=list(feature_columns)
    )
    if eligible.empty:
        return {}, None
    scores = model.score(eligible)
    selected_ids = scores.nlargest(top_k).index if top_k is not None else scores.index
    selected_ids = [symbol for symbol in selected_ids if symbol in scores.index]
    weight = 1.0 / len(selected_ids) if selected_ids else 0.0
    weights = dict.fromkeys(selected_ids, weight)
    portfolio_beta = None
    if hedge == "spy_beta_hedge" and weights:
        beta_by_symbol = eligible.set_index("symbol")[beta_column]
        betas = beta_by_symbol.reindex(list(weights)).fillna(0.0)
        portfolio_beta = float(sum(betas[symbol] * w for symbol, w in weights.items()))
        weights[HEDGE_KEY] = -portfolio_beta
    return weights, portfolio_beta


def _is_last_session_of_iso_week(day: date) -> bool:
    if us_equity_session_close(day) is None:
        return False
    iso_year, iso_week, _ = day.isocalendar()
    for offset in range(1, 7):
        candidate = day + timedelta(days=offset)
        if candidate.isocalendar()[:2] != (iso_year, iso_week):
            break
        if us_equity_session_close(candidate) is not None:
            return False
    return True


def most_recent_rebalance_date(as_of: date, *, lookback_days: int = 13) -> date:
    """The most recent date ``<= as_of`` that is the last US-equity trading
    session of its ISO calendar week -- the plan's weekly Friday-close
    signal date (holiday-week-safe, matching
    ``open_composer.research.kernel.loop.weekly_rebalance_dates``'s
    definition, computed here from the authoritative market calendar instead
    of a feature-panel date column since a live adapter must answer this for
    "today" even when today's own feature row does not exist yet).
    """
    cursor = as_of
    for _ in range(lookback_days):
        if _is_last_session_of_iso_week(cursor):
            return cursor
        cursor -= timedelta(days=1)
    raise ValueError(f"no weekly rebalance date found within {lookback_days} days of {as_of}")


def _price_lookup(frame: pd.DataFrame) -> dict[str, float]:
    if frame.empty or "close" not in frame.columns:
        return {}
    return {
        str(row["symbol"]): float(row["close"])
        for row in frame.to_dict("records")
        if row.get("close") is not None and float(row["close"]) > 0
    }


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
    weights = {str(row["symbol"]): float(row.get("target_weight") or 0.0) for row in latest_rows}
    signal_session = latest_rows[0].get("signal_session") if latest_rows else None
    summary = payload.get("summary") or {}
    return {
        "rebalance_session": latest_session,
        "signal_session": signal_session,
        "weights": weights,
        "portfolio_beta": summary.get("portfolio_beta"),
    }


def _resolve_account_equity(root: Path, override: float | None) -> tuple[float, str | None, str]:
    if override is not None:
        return float(override), None, "portfolio.account_equity_for_sizing"
    account_path = root / "reports" / "paper" / "account.json"
    if not account_path.is_file():
        raise ValueError(
            "model_ranking_portfolio sizing needs a live account-equity snapshot; run "
            "`oc paper sync-account` first, or set portfolio.account_equity_for_sizing "
            "for a deterministic override."
        )
    payload = json.loads(account_path.read_text(encoding="utf-8"))
    equity = payload.get("equity")
    if equity is None or float(equity) <= 0:
        raise ValueError(f"reports/paper/account.json has no positive 'equity' field: {payload}")
    return float(equity), payload.get("generated_at"), "reports/paper/account.json"


def _size_target_weights(
    weights: dict[str, float], price_lookup: dict[str, float], equity: float
) -> WholeShareSizing:
    sizing_weights = dict(weights)
    sizing_prices = dict(price_lookup)
    if HEDGE_KEY in sizing_weights:
        spy_price = price_lookup.get(HEDGE_SYMBOL)
        if spy_price is None:
            raise ValueError(
                f"hedge leg needs a {HEDGE_SYMBOL} close price for this session; none found"
            )
        sizing_prices[HEDGE_KEY] = spy_price
    return size_whole_share_portfolio(sizing_weights, sizing_prices, equity)


def build_model_ranking_rows(
    *,
    spec: StrategySpec,
    weights: dict[str, float],
    previous_weights: dict[str, float],
    sizing: WholeShareSizing,
    signal_date: date,
    rebalance_session: date,
    is_new_signal: bool,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    """Pure row-building step (no I/O): one ``target_rows`` entry per symbol
    ever seen (currently selected or just dropped), and one order-intent
    entry per symbol whose weight actually changed -- gated on
    ``is_new_signal`` so a hold day is *structurally* guaranteed to produce
    zero order intents, not just numerically (delta==0) by coincidence.
    """
    rebalance_id = f"{spec.name}:{rebalance_session.isoformat()}"
    all_symbols = sorted(set(weights) | set(previous_weights))
    target_rows: list[dict[str, object]] = []
    intents: list[dict[str, object]] = []
    for pseudo_symbol in all_symbols:
        display_symbol = HEDGE_SYMBOL if pseudo_symbol == HEDGE_KEY else pseudo_symbol
        target_weight = float(weights.get(pseudo_symbol, 0.0))
        previous_weight = float(previous_weights.get(pseudo_symbol, 0.0))
        delta = target_weight - previous_weight
        target_rows.append(
            {
                "rebalance_id": rebalance_id,
                "rebalance_session": rebalance_session.isoformat(),
                "signal_session": signal_date.isoformat(),
                "time_rule": "next_regular_session_opg_limit",
                "symbol": display_symbol,
                "target_weight": target_weight,
                "shares": int(sizing.shares.get(pseudo_symbol, 0)),
                "realized_weight": float(sizing.realized_weights.get(pseudo_symbol, 0.0)),
                "leg": "beta_hedge" if pseudo_symbol == HEDGE_KEY else "top_k",
                "selected": abs(target_weight) > 1e-12,
                "state": "signal" if is_new_signal else "hold_no_new_signal",
                "source": "model_ranking_portfolio_python_reference",
            }
        )
        if is_new_signal and abs(delta) > 1e-9:
            intents.append(
                {
                    "rebalance_id": rebalance_id,
                    "rebalance_session": rebalance_session.isoformat(),
                    "time_rule": "next_regular_session_opg_limit",
                    "symbol": display_symbol,
                    "from_weight": previous_weight,
                    "to_weight": target_weight,
                    "delta_weight": delta,
                    "side": "buy" if delta > 0 else "sell",
                    "intent_type": "set_model_ranking_target_weight",
                    "requires_order": True,
                    "broker_writes": False,
                }
            )
    return target_rows, intents


@dataclass(frozen=True)
class ModelRankingTargetWeightResult:
    report_path: Path
    json_path: Path
    signal_log_path: Path
    target_weight_count: int
    rebalance_sessions: int
    nonzero_target_rows: int
    parity_status: str
    is_new_signal: bool
    signal_count: int
    candidate_is_placeholder: bool


def run_model_ranking_target_weight_mapping(
    spec_path: Path,
    root: Path | None = None,
    *,
    account_equity_override: float | None = None,
) -> ModelRankingTargetWeightResult:
    base = root or project_root()
    spec = load_strategy_spec(spec_path)
    if spec.portfolio.mode != "model_ranking_portfolio":
        raise ValueError(
            "model ranking target mapping requires portfolio.mode=model_ranking_portfolio"
        )
    if spec.execution.mode != "manual_signal" or spec.execution.broker != "none":
        raise ValueError(
            "model_ranking_portfolio target-weight mapping is observation-only and requires "
            "execution.mode=manual_signal, execution.broker=none"
        )
    portfolio = spec.portfolio
    candidate_dir = (base / str(portfolio.candidate_artifact_dir)).resolve()
    artifact = load_candidate_artifact(candidate_dir)
    feature_columns = tuple(artifact.features.get("feature_columns") or ())
    beta_column = DEFAULT_BETA_COLUMN
    request_columns = list(dict.fromkeys([*feature_columns, "close", beta_column]))

    latest_date = latest_available_trade_date(base)
    today_frame = load_daily_feature_row(base, trade_date=latest_date, columns=request_columns)
    if today_frame.empty:
        raise ValueError(
            f"no feature rows for the latest available trade_date={latest_date.date()}"
        )
    signal_date = most_recent_rebalance_date(latest_date.date())

    previous = _read_previous_snapshot(base, spec.name)
    reuse_previous = (
        previous is not None and previous.get("signal_session") == signal_date.isoformat()
    )

    # Step 13 Track M: opt-in per candidate (config.json:trend_gate), only
    # ever (re-)evaluated on a fresh weekly signal -- a hold day re-emits
    # whatever the last rebalance decided, matching the module's own
    # weekly-hold contract (docstring above) rather than reacting to the
    # benchmark intraweek. `gate_open`/`gate_detail` stay `None` on a hold
    # day: they were not recomputed this run, not "gate open by default".
    trend_gate_cfg = artifact.config.get("trend_gate")
    gate_open: bool | None = None
    gate_detail: dict[str, Any] | None = None

    if reuse_previous:
        assert previous is not None  # narrows type for mypy; reuse_previous already implies it
        weights = dict(previous["weights"])
        portfolio_beta = previous.get("portfolio_beta")
        universe_symbols, universe_month_end = load_latest_universe_cohort(
            base, top_n=int(portfolio.universe_top_n), as_of=pd.Timestamp(signal_date)
        )
        is_new_signal = False
    else:
        universe_symbols, universe_month_end = load_latest_universe_cohort(
            base, top_n=int(portfolio.universe_top_n), as_of=pd.Timestamp(signal_date)
        )
        if trend_gate_cfg is not None:
            gate_open, gate_detail = trend_gate_state(
                base, trend_gate_cfg, as_of=pd.Timestamp(signal_date)
            )
        if trend_gate_cfg is not None and not gate_open:
            # Gate closed: the whole book goes to the cash leg, matching
            # loop.py::build_weight_schedule's research-side convention
            # (weights = {trend_gate_cash_symbol: 1.0}) -- no ranking/
            # scoring needed for an all-cash week.
            weights = {str(trend_gate_cfg.get("cash_symbol") or "BIL"): 1.0}
            portfolio_beta = None
        else:
            if pd.Timestamp(signal_date) == latest_date.normalize():
                score_frame = today_frame
            else:
                score_frame = load_daily_feature_row(
                    base, trade_date=pd.Timestamp(signal_date), columns=request_columns
                )
                if score_frame.empty:
                    raise ValueError(
                        f"no feature rows for the current weekly signal_date={signal_date}"
                    )
            weights, portfolio_beta = score_and_select(
                asof_frame=score_frame,
                universe_symbols=universe_symbols,
                model=artifact.model,
                top_k=int(portfolio.top_k),
                hedge=str(portfolio.hedge),
                beta_column=beta_column,
                feature_columns=feature_columns,
            )
            if not weights:
                raise ValueError(
                    f"model_ranking_portfolio scored zero eligible symbols for signal_date="
                    f"{signal_date} (universe_size={len(universe_symbols)}); refusing to write "
                    "an empty fresh signal -- investigate the feature/universe join before retrying"
                )
        is_new_signal = True

    previous_weights = dict(previous["weights"]) if previous is not None else {}
    rebalance_session = next_us_equity_session(signal_date)
    equity, equity_generated_at, equity_source = _resolve_account_equity(
        base, account_equity_override or portfolio.account_equity_for_sizing
    )
    price_lookup = _price_lookup(today_frame)
    if trend_gate_cfg is not None:
        # The cash leg never appears in data/features/daily/ (see
        # _sip_closes_on_or_before's docstring); fetch its price directly
        # whenever this candidate declares a trend gate, regardless of
        # whether the gate is open this run, so a hold day that is
        # reusing a previous all-cash signal can still size it.
        cash_symbol = str(trend_gate_cfg.get("cash_symbol") or "BIL")
        if cash_symbol not in price_lookup:
            price_lookup[cash_symbol] = _latest_sip_close(base, cash_symbol, as_of=latest_date)
    sizing = _size_target_weights(weights, price_lookup, equity)

    target_rows, intents = build_model_ranking_rows(
        spec=spec,
        weights=weights,
        previous_weights=previous_weights,
        sizing=sizing,
        signal_date=signal_date,
        rebalance_session=rebalance_session,
        is_new_signal=is_new_signal,
    )

    data_profile = {
        "source_mode": "cache",
        "provider": "alpaca_sip_daily_feature_archive",
        "feed": spec.data.feed or "",
        "feature_set_id": portfolio.feature_set_id,
        "feature_columns": list(feature_columns),
        "candidate_artifact_dir": str(portfolio.candidate_artifact_dir),
        "candidate_is_placeholder": artifact.is_placeholder,
        "signal_session": signal_date.isoformat(),
        "latest_available_trade_date": latest_date.date().isoformat(),
        "universe_size": len(universe_symbols),
        "universe_month_end": universe_month_end.date().isoformat(),
    }
    warnings: list[str] = []
    if artifact.is_placeholder:
        warnings.append(
            "candidate_artifact_dir is a rule-based candidate (momentum or a derived "
            "risk-adjusted score), not a research-validated model artifact"
        )
    if sizing.unaffordable:
        warnings.append(f"unaffordable_at_current_equity={list(sizing.unaffordable)}")
    parity_check = {
        "status": "ok",
        "blockers": [],
        "warnings": warnings,
        "is_new_signal": is_new_signal,
        "candidate_is_placeholder": artifact.is_placeholder,
    }
    acquisition_tier = infer_acquisition_tier(
        data_source=spec.data.source,
        data_profile=data_profile,
        explicit=spec.data_assumptions.acquisition_tier,
        refresh_data=False,
    )
    mapping_summary = {
        "mapping_mode": "model_ranking_portfolio_target_weight_mapping",
        "candidate_artifact_dir": str(portfolio.candidate_artifact_dir),
        "candidate_is_placeholder": artifact.is_placeholder,
        "feature_set_id": portfolio.feature_set_id,
        "label_horizon_days": portfolio.label_horizon_days,
        "top_k": portfolio.top_k,
        "hedge": portfolio.hedge,
        "portfolio_beta": portfolio_beta,
        "trend_gate": trend_gate_cfg,
        "trend_gate_open": gate_open,
        "trend_gate_detail": gate_detail,
        "universe_rule": portfolio.universe_rule,
        "universe_top_n": portfolio.universe_top_n,
        "universe_size": len(universe_symbols),
        "weight_deviation": sizing.weight_deviation,
        "idle_cash": sizing.idle_cash,
        "idle_cash_fraction": sizing.idle_cash_fraction,
        "invested_cash": sizing.invested_cash,
        "unaffordable": list(sizing.unaffordable),
        "account_equity": equity,
        "account_equity_generated_at": equity_generated_at,
        "account_equity_source": equity_source,
        "is_new_signal": is_new_signal,
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
            price_lookup=price_lookup,
            signal_date=signal_date,
            candidate_dir=candidate_dir,
            portfolio=portfolio,
        )
        if is_new_signal
        else []
    )
    signal_log_path = base / "signal_logs" / f"model-ranking-{spec.name}.jsonl"
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
        parity_check=parity_check,
        mapping_summary=mapping_summary,
        json_path=json_path,
        signal_log_path=signal_log_path,
        signal_count=len(signals),
    )
    return ModelRankingTargetWeightResult(
        report_path=report_path,
        json_path=json_path,
        signal_log_path=signal_log_path,
        target_weight_count=len(target_rows),
        rebalance_sessions=len({row["rebalance_session"] for row in target_rows}),
        nonzero_target_rows=sum(bool(row["selected"]) for row in target_rows),
        parity_status=str(parity_check["status"]),
        is_new_signal=is_new_signal,
        signal_count=len(signals),
        candidate_is_placeholder=artifact.is_placeholder,
    )


def _build_signals(
    *,
    spec: StrategySpec,
    intents: list[dict[str, object]],
    price_lookup: dict[str, float],
    signal_date: date,
    candidate_dir: Path,
    portfolio: Any,
) -> list[Any]:
    spec_hash = strategy_content_hash(spec)
    run_id = f"model-ranking-{spec.name}"
    # Daily-bar strategy: there is no intraday decision timestamp, so the
    # signal is timestamped at the US market close of its (already-observed)
    # signal_date, matching the close-price feature values it was scored on.
    timestamp = datetime.combine(signal_date, time(20, 0), tzinfo=UTC)
    signals = []
    for intent in intents:
        symbol = str(intent["symbol"])
        delta = float(intent["delta_weight"])
        action = "entry" if delta > 0 else "exit"
        price = price_lookup.get(symbol, 0.0)
        signal = build_signal(
            spec,
            run_id=run_id,
            timestamp=timestamp,
            action=action,
            source="model_ranking_portfolio_observation",
            price=price,
            spec_hash=spec_hash,
            symbol=symbol,
            target_weight=float(intent["to_weight"]),
            conditions=[
                f"candidate_artifact_dir={candidate_dir.as_posix()}",
                f"feature_set_id={portfolio.feature_set_id}",
                f"top_k={portfolio.top_k}",
                f"hedge={portfolio.hedge}",
                f"signal_date={signal_date.isoformat()}",
            ],
        )
        signals.append(signal)
    return signals


def _write_report(
    path: Path,
    *,
    spec: StrategySpec,
    target_rows: list[dict[str, object]],
    sizing: WholeShareSizing,
    parity_check: dict[str, object],
    mapping_summary: dict[str, object],
    json_path: Path,
    signal_log_path: Path,
    signal_count: int,
) -> None:
    held = sorted(
        (row for row in target_rows if row["selected"]),
        key=lambda row: str(row["symbol"]),
    )
    lines = [
        f"# Model-Ranking Target Weights: {spec.name}",
        "",
        f"- JSON: `{json_path}`",
        f"- Signal log: `{signal_log_path}`",
        f"- Status: `{parity_check['status']}`",
        f"- New signal this run: `{mapping_summary['is_new_signal']}`",
        f"- Candidate is placeholder: `{mapping_summary['candidate_is_placeholder']}`",
        *(
            [
                f"- Trend gate: `{mapping_summary['trend_gate']}` "
                f"(open=`{mapping_summary['trend_gate_open']}`)"
            ]
            if mapping_summary.get("trend_gate") is not None
            else []
        ),
        f"- Held names: `{len(held)}`",
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
        lines.extend(["| symbol | target weight | shares | leg |", "| --- | --- | --- | --- |"])
        lines.extend(
            f"| {row['symbol']} | {float(row['target_weight']):.4f} | {row['shares']} | "
            f"{row['leg']} |"
            for row in held
        )
    lines.append("")
    if parity_check.get("warnings"):
        lines.append("## Warnings")
        lines.append("")
        lines.extend(f"- {warning}" for warning in parity_check["warnings"])
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")
