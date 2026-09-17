"""H-20260916-05: 13D activist event drift -- pre-check, event study, tradability.

Card: ``reports/research/hypotheses/H-20260916-05-13d-activist-event-drift.md``
Data: ``data/features/sec_13d/filings.parquet`` (built by
``scripts/build_sec_13d_features.py``), ``data/features/universe`` (PIT ADV
cohorts, rebuilt 2026-09-16), ``data/features/daily`` (open/close + momentum),
``data/sip-delisted/daily`` (S&P 500 removals since 2016, used only to price
names that left the surviving tape), SIP daily bars for SPY/BIL/MTUM/SPMO.

Stages, each writing its own resumable checkpoint under
``reports/research/iterations/h20260916_05_13d_drift/``:

``precheck``
    Mandatory before any backtest (``docs/current-view.zh.md`` rule from
    L-20260916-01): events per year x form type x universe bucket x size
    tercile, the count of *new* 13D per year, and the hit rate of "a new 13D
    in the last 60 sessions" inside the momentum top-50 book versus inside
    the whole top-500 pool. If that overlap is as thin as Form 4's 1.9%,
    the answer about a 13D *layer* is already in.
``event-study``
    Entry at the next session's open after ``visible_session`` for new
    Schedule 13D filings; hold 20/40/60 sessions; excess against (a) SPY and
    (b) size-matched random controls (same entry date, same liquidity
    tercile, >= 5 seeds, reported as a distribution); split at 2024-02-05
    (10-day -> 5-business-day deadline) and by 2016-2019 / 2020-2023 /
    2024-2026; plus the sessions -5..-1 pre-visibility run-up and a
    filing-date-shift placebo (+-20 sessions, >= 5 seeds).
``tradability``
    A weekly equal-weight book of every name with a new 13D in the last 60
    sessions, priced through the same kernel engine and cost convention as
    the momentum cells (``returns_from_weight_schedule``, next-open
    execution, 10 bps/side), against SPY/MTUM/SPMO and against a same-size
    random control book (>= 5 seeds).

Usage::

    nohup ./scripts/run_capped.sh --mem 1.8G -- \\
        uv run python scripts/run_h20260916_05_13d_drift.py --stage all \\
        > reports/research/iterations/h20260916_05_13d_drift/logs/run.log 2>&1 &
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from open_composer.adapters.data.sip_parquet import load_sip_bars  # noqa: E402
from open_composer.research.features import universe as universe_mod  # noqa: E402
from open_composer.research.kernel.loop import (  # noqa: E402
    RebalanceEvent,
    returns_from_weight_schedule,
    universe_as_of_calendar_month,
    weekly_rebalance_dates,
)
from open_composer.research.kernel.mechanism_eval import annualized_cagr, max_drawdown  # noqa: E402
from open_composer.research.kernel.vol_matched import cagr_excess_vol_matched  # noqa: E402

OUT_ROOT = ROOT / "reports" / "research" / "iterations" / "h20260916_05_13d_drift"
FILINGS_PATH = ROOT / "data" / "features" / "sec_13d" / "filings.parquet"
DAILY_ROOT = ROOT / "data" / "features" / "daily"
UNIVERSE_ROOT = ROOT / "data" / "features" / "universe"
DELISTED_GLOB = ROOT / "data" / "sip-delisted" / "daily"

DATA_START = "2016-01-04"
YEARS = tuple(range(2016, 2027))
#: 2024-02-05: the Schedule 13D filing deadline went from 10 calendar days to
#: 5 business days (SEC 2023 modernization rule). Anything that only works
#: before this date is a regime that no longer exists.
DEADLINE_CHANGE = pd.Timestamp("2024-02-05")
RECENT_WINDOW_START = pd.Timestamp("2024-01-02")
HORIZONS = (20, 40, 60)
PRE_WINDOW = 5
BOOK_LOOKBACK_SESSIONS = 60
COST_BPS_PER_SIDE = 10.0
CASH_SYMBOL = "BIL"
BENCHMARK_SYMBOLS = ("SPY", "MTUM", "SPMO", CASH_SYMBOL)
SEEDS = (20260916, 20260917, 20260918, 20260919, 20260920)
PLACEBO_MAX_SHIFT = 20
MOMENTUM_TOP_N = 500
MOMENTUM_TOP_K = 50
MOMENTUM_SCORE = "momentum_252_21"


def _log(message: str) -> None:
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {message}", flush=True)


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n")


# --------------------------------------------------------------------------
# data
# --------------------------------------------------------------------------


#: One-day price ratio above which a move is treated as an unadjusted
#: corporate action rather than a return. Nothing liquid moves 10x in a
#: session; a reverse split or a post-bankruptcy re-listing does.
#:
#: Found the hard way (2026-09-17): the first tradability run reported a 154%
#: recent CAGR at 448% annualized volatility because ``data/features/daily``
#: carries WW (WW International) at 0.2496 on 2025-07-03 and 41.15 on
#: 2025-07-07 -- its post-Chapter-11 reverse split, unadjusted. One name, one
#: day, +16,386%. Across the panel there are 51 such symbol-days in 46
#: symbols (137 at a 5x threshold), so this is a property of the feature
#: store, not a one-off.
MAX_ONE_DAY_PRICE_RATIO = 10.0

#: A missing-price run this long followed by a resumption is treated as a
#: regime break, not a holding period: the return engine pads across gaps.
MAX_PRICE_GAP_SESSIONS = 5

#: Filled in by ``load_price_matrices`` and copied into every stage's payload.
PRICE_SANITIZE_STATS: dict[str, Any] = {}


def mask_unadjusted_corporate_actions(
    open_wide: pd.DataFrame, close_wide: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    """Blank each symbol's history up to and including its last *regime break*.

    Two kinds of break, both of which fabricate returns rather than describe
    them, and both found by running this book before fixing them:

    ``jump``
        Consecutive *valid* observations whose ratio is above
        ``MAX_ONE_DAY_PRICE_RATIO`` or below its reciprocal. WW (WW
        International) prints 0.2496 on 2025-07-03 and 41.15 on 2025-07-07 --
        its post-Chapter-11 reverse split, unadjusted, +16,386% in a day.
    ``gap``
        A run of at least ``MAX_PRICE_GAP_SESSIONS`` missing sessions followed
        by a resumption. AZUL disappears from the tape, comes back at 9.15,
        and ``returns_from_weight_schedule``'s ``pct_change()`` -- which pads
        by default -- bridges the hole and books +1,730% in one day. A one or
        two session halt is left alone; a multi-week disappearance is a
        different security state.

    The split/relist factor is unknowable from the panel, so the pre-break
    series is treated as a different security rather than spliced onto the
    post-break one. Masking (rather than clipping the single return) also
    removes the price *level* that produced it, so no holding window can
    straddle the join.

    Residual, stated rather than hidden: gaps shorter than the threshold are
    still padded by the return engine, so a name that halts for two sessions
    and reopens 30% lower books that move on the reopen day.
    """
    reasons: dict[str, dict[str, str]] = {}
    jump_count = 0
    gap_count = 0
    masked_cells = 0
    index = close_wide.index
    for symbol in close_wide.columns:
        values = close_wide[symbol].to_numpy(dtype="float64")
        valid = np.flatnonzero(np.isfinite(values) & (values > 0))
        if valid.size < 2:
            continue
        ratios = values[valid[1:]] / values[valid[:-1]]
        gaps = np.diff(valid)
        is_jump = (ratios > MAX_ONE_DAY_PRICE_RATIO) | (ratios < 1.0 / MAX_ONE_DAY_PRICE_RATIO)
        is_gap = gaps >= MAX_PRICE_GAP_SESSIONS
        breaks = np.flatnonzero(is_jump | is_gap)
        if breaks.size == 0:
            continue
        last = int(breaks[-1])
        kind = "jump" if is_jump[last] else "gap"
        jump_count += int(is_jump[last])
        gap_count += int(is_gap[last] and not is_jump[last])
        cutoff_position = int(valid[last])
        cutoff = index <= index[cutoff_position]
        masked_cells += int(close_wide.loc[cutoff, symbol].notna().sum())
        reasons[str(symbol)] = {
            "kind": kind,
            "last_break_before": str(pd.Timestamp(index[int(valid[last + 1])]).date()),
            "ratio": f"{float(ratios[last]):.4g}",
            "gap_sessions": str(int(gaps[last])),
        }
        close_wide.loc[cutoff, symbol] = np.nan
        open_wide.loc[cutoff, symbol] = np.nan
    stats = {
        "threshold_one_day_price_ratio": MAX_ONE_DAY_PRICE_RATIO,
        "threshold_gap_sessions": MAX_PRICE_GAP_SESSIONS,
        "symbols_masked": len(reasons),
        "symbols_masked_for_jump": jump_count,
        "symbols_masked_for_gap": gap_count,
        "price_cells_masked": masked_cells,
        "breaks_by_symbol": reasons,
        "note": (
            "unadjusted reverse splits / post-reorganization relistings and multi-week price gaps "
            "in data/features/daily; each symbol's history is blanked up to and including its last "
            "break, because the adjustment factor is not recoverable from the panel"
        ),
    }
    return open_wide, close_wide, stats


def load_price_matrices() -> tuple[pd.DataFrame, pd.DataFrame]:
    """``(open_wide, close_wide)``: sessions x symbols, float32.

    Built from ``data/features/daily`` (the surviving top-1500 ADV panel) and
    then *extended* with ``data/sip-delisted/daily`` for symbols the panel
    does not have. That second source is only the 243 S&P 500 removals since
    2016, so it does not repair survivorship -- it narrows it. Every number
    in this round is reported with the residual bias stated, because an
    activist campaign that ends in a takeover is exactly the event whose
    ticker disappears.
    """
    # Pivot per year and concatenate rather than pivoting one 7M-row frame:
    # ``pivot_table`` on the whole panel peaked well over this box's 1.8 GB cap
    # in an earlier run, and (trade_date, symbol) is already unique so there is
    # nothing to aggregate.
    open_parts: list[pd.DataFrame] = []
    close_parts: list[pd.DataFrame] = []
    for year in YEARS:
        path = DAILY_ROOT / f"{year}.parquet"
        if not path.exists():
            continue
        frame = pd.read_parquet(path, columns=["symbol", "trade_date", "open", "close"])
        frame["trade_date"] = pd.to_datetime(frame["trade_date"])
        frame = frame.drop_duplicates(subset=["trade_date", "symbol"], keep="last")
        open_parts.append(
            frame.pivot(index="trade_date", columns="symbol", values="open").astype("float32")
        )
        close_parts.append(
            frame.pivot(index="trade_date", columns="symbol", values="close").astype("float32")
        )
        del frame
    open_wide = pd.concat(open_parts).sort_index()
    close_wide = pd.concat(close_parts).sort_index()
    del open_parts, close_parts

    delisted_frames = []
    for path in sorted(DELISTED_GLOB.glob("*.parquet")):
        frame = pd.read_parquet(path, columns=["symbol", "timestamp", "open", "close"])
        delisted_frames.append(frame)
    if delisted_frames:
        delisted = pd.concat(delisted_frames, ignore_index=True)
        delisted["trade_date"] = (
            pd.to_datetime(delisted["timestamp"], utc=True).dt.tz_localize(None).dt.normalize()
        )
        extra = sorted(set(delisted["symbol"]) - set(close_wide.columns))
        delisted = delisted.loc[delisted["symbol"].isin(extra)]
        if not delisted.empty:
            open_extra = delisted.pivot_table(index="trade_date", columns="symbol", values="open")
            close_extra = delisted.pivot_table(index="trade_date", columns="symbol", values="close")
            open_wide = open_wide.join(open_extra.reindex(open_wide.index), how="left")
            close_wide = close_wide.join(close_extra.reindex(close_wide.index), how="left")
        _log(f"price matrices: added {len(extra)} delisted symbols from data/sip-delisted")

    for symbol in BENCHMARK_SYMBOLS:
        bars = load_sip_bars(symbol, frequency="daily", start=DATA_START)
        bars = bars.loc[bars["symbol"] == symbol].copy()
        bars["trade_date"] = (
            pd.to_datetime(bars["timestamp"], utc=True).dt.tz_localize(None).dt.normalize()
        )
        bars = bars.drop_duplicates("trade_date", keep="last").set_index("trade_date")
        open_wide[symbol] = bars["open"].reindex(open_wide.index).astype("float64")
        close_wide[symbol] = bars["close"].reindex(close_wide.index).astype("float64")

    open_wide = open_wide.astype("float32").sort_index()
    close_wide = close_wide.astype("float32").sort_index()
    open_wide, close_wide, sanitize_stats = mask_unadjusted_corporate_actions(open_wide, close_wide)
    PRICE_SANITIZE_STATS.clear()
    PRICE_SANITIZE_STATS.update(sanitize_stats)
    _log(
        f"price matrices: masked {sanitize_stats['symbols_masked']} symbols at a regime break "
        f"({sanitize_stats['symbols_masked_for_jump']} unadjusted >"
        f"{MAX_ONE_DAY_PRICE_RATIO:.0f}x jumps, {sanitize_stats['symbols_masked_for_gap']} "
        f">={MAX_PRICE_GAP_SESSIONS}-session gaps; "
        f"{sanitize_stats['price_cells_masked']:,} price cells)"
    )
    _log(
        f"price matrices: {open_wide.shape[0]:,} sessions x {open_wide.shape[1]:,} symbols "
        f"({open_wide.index.min().date()}..{open_wide.index.max().date()})"
    )
    return open_wide, close_wide


def load_events(*, new_only: bool = True) -> pd.DataFrame:
    frame = pd.read_parquet(FILINGS_PATH)
    frame["filing_date"] = pd.to_datetime(frame["filing_date"])
    frame["visible_session"] = pd.to_datetime(frame["visible_session"])
    frame["entry_session"] = pd.to_datetime(frame["entry_session"])
    if new_only:
        frame = frame.loc[frame["is_new_13d"]]
    return frame.reset_index(drop=True)


# --------------------------------------------------------------------------
# stage: precheck
# --------------------------------------------------------------------------


def _year_form_table(filings: pd.DataFrame) -> dict[str, dict[str, int]]:
    table = (
        filings.assign(year=filings["filing_date"].dt.year)
        .pivot_table(index="year", columns="form_type", values="accession", aggfunc="count")
        .fillna(0)
        .astype(int)
    )
    return {str(index): row.to_dict() for index, row in table.iterrows()}


def momentum_book_overlap(events: pd.DataFrame, *, lookback: int) -> dict[str, Any]:
    """The L-20260916-01 cross-table: how often does a new 13D land on a name
    the momentum book actually holds?

    The book here is an *approximation* of the M0B cell (PIT top-500 ADV
    cohort, ranked by ``momentum_252_21``, top 50, weekly on the last session
    of each ISO week) rather than a ``pick_export`` dump of it: the cell
    itself only walks 2024-2026 (its embargoed training windows start in
    2022), and this table has to cover 2016-2026 to say anything about event
    scarcity. The approximation shares the cohort logic, the score column and
    the rebalance calendar with the cell, which is what the hit-rate
    comparison needs; it does not share the trend gate, so the book here is
    always fully invested.
    """
    universe_panel = universe_mod.load_universe_panel(UNIVERSE_ROOT)
    frames = []
    for year in YEARS:
        path = DAILY_ROOT / f"{year}.parquet"
        if not path.exists():
            continue
        frames.append(pd.read_parquet(path, columns=["symbol", "trade_date", MOMENTUM_SCORE]))
    panel = pd.concat(frames, ignore_index=True)
    panel["trade_date"] = pd.to_datetime(panel["trade_date"])
    sessions = pd.DatetimeIndex(sorted(panel["trade_date"].unique()))
    rebalances = [date for date in weekly_rebalance_dates(sessions) if date >= sessions[252]]
    scores = panel.set_index(["trade_date", "symbol"])[MOMENTUM_SCORE].sort_index()
    del panel, frames

    entry_by_symbol: dict[str, list[pd.Timestamp]] = {}
    for symbol, entry in zip(events["issuer_symbol"], events["entry_session"], strict=True):
        entry_by_symbol.setdefault(str(symbol), []).append(pd.Timestamp(entry))

    rows = []
    for rebalance in rebalances:
        position = sessions.searchsorted(rebalance)
        window_start = sessions[max(0, position - lookback + 1)]
        cohort = universe_as_of_calendar_month(universe_panel, rebalance, top_n=MOMENTUM_TOP_N)
        try:
            day_scores = scores.loc[rebalance]
        except KeyError:
            continue
        day_scores = day_scores.loc[day_scores.index.isin(cohort)].dropna()
        if day_scores.empty:
            continue
        book = set(day_scores.sort_values(ascending=False).head(MOMENTUM_TOP_K).index)
        pool = set(day_scores.index)

        def _hit(
            symbols: set[str],
            start: pd.Timestamp = window_start,
            end: pd.Timestamp = rebalance,
        ) -> int:
            return sum(
                1
                for symbol in symbols
                if any(start <= entry <= end for entry in entry_by_symbol.get(symbol, ()))
            )

        rows.append(
            {
                "rebalance_date": rebalance,
                "book_size": len(book),
                "pool_size": len(pool),
                "book_hits": _hit(book),
                "pool_hits": _hit(pool),
            }
        )
    table = pd.DataFrame(rows)
    book_rate = float(table["book_hits"].sum() / table["book_size"].sum())
    pool_rate = float(table["pool_hits"].sum() / table["pool_size"].sum())
    per_year = (
        table.assign(year=table["rebalance_date"].dt.year)
        .groupby("year")[["book_hits", "book_size", "pool_hits", "pool_size"]]
        .sum()
    )
    return {
        "definition": (
            f"hit = the name had a *new* Schedule 13D whose entry session falls in the trailing "
            f"{lookback} sessions; book = PIT top-{MOMENTUM_TOP_N} cohort ranked by "
            f"{MOMENTUM_SCORE}, top {MOMENTUM_TOP_K}, weekly"
        ),
        "rebalances": int(len(table)),
        "book_position_weeks": int(table["book_size"].sum()),
        "book_hit_rate": book_rate,
        "pool_position_weeks": int(table["pool_size"].sum()),
        "pool_hit_rate": pool_rate,
        "book_over_pool": float(book_rate / pool_rate) if pool_rate else None,
        "distinct_book_hits": int(table["book_hits"].sum()),
        "per_year": {
            str(year): {
                "book_hit_rate": float(row["book_hits"] / row["book_size"])
                if row["book_size"]
                else None,
                "pool_hit_rate": float(row["pool_hits"] / row["pool_size"])
                if row["pool_size"]
                else None,
                "book_hits": int(row["book_hits"]),
            }
            for year, row in per_year.iterrows()
        },
    }


def stage_precheck(*, skip_overlap: bool) -> dict[str, Any]:
    all_filings = load_events(new_only=False)
    in_universe = all_filings.loc[all_filings["universe_bucket"] != "outside"]
    # Every per-issuer count below is restricted to header-verified rows. The
    # 13G family is index-only in this build, so its "in universe" counts
    # would otherwise be counting index managers (BLK/BEN/TROW file thousands
    # of 13Gs and are themselves top-1000 names), not targets. The exact,
    # attribution-free 13G numbers are the EDGAR index counts reported in
    # ``by_year_form_all``.
    verified = in_universe.loc[in_universe["issuer_verified"]]
    new_13d = verified.loc[verified["is_new_13d"]]

    bucket_table = (
        new_13d.assign(year=new_13d["filing_date"].dt.year)
        .pivot_table(index="year", columns="universe_bucket", values="accession", aggfunc="count")
        .fillna(0)
        .astype(int)
    )
    tercile_table = (
        new_13d.assign(year=new_13d["filing_date"].dt.year)
        .pivot_table(
            index="year", columns="size_tercile_dollar_adv", values="accession", aggfunc="count"
        )
        .fillna(0)
        .astype(int)
    )
    bucket_tercile = (
        new_13d.pivot_table(
            index="universe_bucket",
            columns="size_tercile_dollar_adv",
            values="accession",
            aggfunc="count",
        )
        .fillna(0)
        .astype(int)
    )
    distinct_issuers = (
        new_13d.assign(year=new_13d["filing_date"].dt.year)
        .groupby("year")["issuer_symbol"]
        .nunique()
    )
    # EDGAR-wide counts, straight off the quarterly form index: exact, and the
    # only 13G numbers in this round that need no issuer-attribution assumption
    # at all (one accession can appear under several CIKs, so accessions are
    # deduped first).
    from scripts.collect_sec_13d_filings import load_index

    index = load_index().drop_duplicates("accession")
    index["year"] = pd.to_datetime(index["date_filed"]).dt.year
    edgar_by_year = (
        index.pivot_table(index="year", columns="form_type", values="accession", aggfunc="count")
        .fillna(0)
        .astype(int)
    )

    payload: dict[str, Any] = {
        "card": "H-20260916-05",
        "generated_at": pd.Timestamp.utcnow().isoformat(),
        "universe_top_n": 1000,
        "edgar_index_by_year_form_all_issuers": {
            str(year): row.to_dict() for year, row in edgar_by_year.iterrows()
        },
        "edgar_index_accessions_total": int(len(index)),
        "rows_total": int(len(all_filings)),
        "rows_in_universe": int(len(in_universe)),
        "by_year_form_all": _year_form_table(all_filings),
        "by_year_form_in_universe_index_attribution": _year_form_table(in_universe),
        "by_year_form_in_universe_header_verified": _year_form_table(verified),
        "issuer_verified_counts": {
            "true": int(all_filings["issuer_verified"].sum()),
            "false": int((~all_filings["issuer_verified"]).sum()),
        },
        "new_13d_by_year_bucket": {
            str(index): row.to_dict() for index, row in bucket_table.iterrows()
        },
        "new_13d_by_year_tercile": {
            str(index): row.to_dict() for index, row in tercile_table.iterrows()
        },
        "new_13d_bucket_by_tercile": {
            str(index): row.to_dict() for index, row in bucket_tercile.iterrows()
        },
        "new_13d_distinct_issuers_by_year": {
            str(year): int(value) for year, value in distinct_issuers.items()
        },
        "new_13d_total": int(len(new_13d)),
        "new_13d_distinct_issuers": int(new_13d["issuer_symbol"].nunique()),
        "visible_confidence_counts": {
            str(key): int(value)
            for key, value in verified["visible_confidence"].value_counts().items()
        },
        "new_13d_ticker_name_consistency": {
            "true": int((new_13d["issuer_name_matches_current_registrant"] == True).sum()),  # noqa: E712
            "false": int((new_13d["issuer_name_matches_current_registrant"] == False).sum()),  # noqa: E712
        },
        "percent_of_class": {
            "median_new_13d": float(new_13d["percent_of_class"].median()),
            "confidence_counts": {
                str(key): int(value)
                for key, value in new_13d["percent_parse_confidence"].value_counts().items()
            },
        },
        "item4_chars_new_13d": {
            "median": float(new_13d["item4_chars"].median()),
            "p25": float(new_13d["item4_chars"].quantile(0.25)),
            "p75": float(new_13d["item4_chars"].quantile(0.75)),
            "present_rate": float(new_13d["item4_present"].mean()),
        },
    }
    if not skip_overlap:
        payload["momentum_book_overlap"] = momentum_book_overlap(
            new_13d, lookback=BOOK_LOOKBACK_SESSIONS
        )
    _write_json(OUT_ROOT / "precheck.json", payload)
    _log(f"precheck: new 13D in universe = {payload['new_13d_total']}")
    return payload


# --------------------------------------------------------------------------
# stage: event study
# --------------------------------------------------------------------------


def _priceable_events(
    events: pd.DataFrame, close_wide: pd.DataFrame, sessions: pd.DatetimeIndex
) -> pd.DataFrame:
    """Events whose entry session exists on the tape and whose symbol has a
    price there, with the entry index attached. Dedupes co-filed 13Ds: two
    activists filing separately on the same issuer the same day is one event,
    not two."""
    frame = events.copy()
    # ``issuer_verified`` first: only a fetched header proves the issuer, and
    # for a Schedule 13D the *other* party in the index is the activist.
    frame = frame.loc[frame["issuer_verified"]]
    frame = frame.loc[frame["universe_bucket"] != "outside"]
    frame = frame.loc[frame["visible_confidence"] == "acceptance_datetime"]
    frame = frame.loc[frame["issuer_symbol"].isin(close_wide.columns)]
    positions = sessions.searchsorted(frame["entry_session"].to_numpy())
    frame["entry_pos"] = positions
    frame = frame.loc[frame["entry_pos"] < len(sessions) - 1]
    frame = frame.sort_values(["issuer_symbol", "entry_pos", "acceptance_datetime_et"])
    frame = frame.drop_duplicates(subset=["issuer_symbol", "entry_pos"], keep="first")
    return frame.reset_index(drop=True)


def _window_return(
    prices_open: np.ndarray, prices_close: np.ndarray, entry_pos: int, horizon: int
) -> tuple[float, bool]:
    """``(return, liquidated_early)`` from the entry open to the horizon close.

    When the exit close is missing the position is marked out at the *last
    available close inside the window* instead of being dropped. Dropping is
    what a naive implementation does, and for an activism study it is a
    directional bias: the events whose ticker stops printing mid-window are
    disproportionately the successful campaigns that ended in a takeover, so
    discarding them removes the hypothesis's own best cases. ``liquidated_early``
    counts how often this happened so the report can say how much of the sample
    it touches.
    """
    exit_pos = entry_pos + horizon - 1
    if exit_pos >= len(prices_close) or exit_pos <= entry_pos:
        # The *tape* is too short, which is not an early liquidation: returning
        # a truncated window here would quietly shorten the holding period of
        # every event near the end of the sample -- i.e. exactly the 2024-2026
        # window the card's stop condition is about.
        return float("nan"), False
    entry_price = prices_open[entry_pos]
    if not np.isfinite(entry_price) or entry_price <= 0:
        return float("nan"), False
    window = prices_close[entry_pos : exit_pos + 1]
    finite = np.flatnonzero(np.isfinite(window))
    if finite.size == 0:
        return float("nan"), False
    last = int(finite[-1])
    liquidated_early = last < len(window) - 1
    return float(window[last] / entry_price - 1.0), liquidated_early


def _pre_window_return(prices_close: np.ndarray, filing_pos: int, window: int) -> float:
    start = filing_pos - window - 1
    end = filing_pos - 1
    if start < 0 or end >= len(prices_close):
        return float("nan")
    first, last = prices_close[start], prices_close[end]
    if not np.isfinite(first) or not np.isfinite(last) or first <= 0:
        return float("nan")
    return float(last / first - 1.0)


def _tstat(values: np.ndarray) -> float:
    clean = values[np.isfinite(values)]
    if len(clean) < 3:
        return float("nan")
    scale = clean.std(ddof=1) / np.sqrt(len(clean))
    return float(clean.mean() / scale) if scale > 0 else float("nan")


def _clustered_tstat(values: np.ndarray, clusters: np.ndarray) -> float:
    """t-stat on cluster means (clusters = filing months).

    Activist filings arrive in bursts and several events share the same
    market weeks, so the naive cross-sectional t-stat overstates
    independence. Reporting both is the honest version; the stop condition
    uses this one.
    """
    frame = pd.DataFrame({"value": values, "cluster": clusters}).dropna()
    if frame.empty:
        return float("nan")
    means = frame.groupby("cluster")["value"].mean().to_numpy()
    return _tstat(means)


def _summarize(values: np.ndarray, clusters: np.ndarray) -> dict[str, Any]:
    clean = values[np.isfinite(values)]
    return {
        "n": int(len(clean)),
        "mean": float(clean.mean()) if len(clean) else None,
        "median": float(np.median(clean)) if len(clean) else None,
        "t_naive": _tstat(values),
        "t_clustered_by_month": _clustered_tstat(values, clusters),
        "hit_rate": float((clean > 0).mean()) if len(clean) else None,
    }


def _control_pools(
    events: pd.DataFrame, close_wide: pd.DataFrame, top_n: int = 1000
) -> dict[tuple[pd.Timestamp, str], list[str]]:
    """``(cohort month_end, liquidity tercile) -> candidate symbols``.

    Same construction as the filing table's own tercile column, so a control
    is drawn from the same PIT cohort and the same size bucket as the event,
    and only from symbols that are priceable on our tape.
    """
    panel = universe_mod.load_universe_panel(UNIVERSE_ROOT)
    panel = panel.loc[panel["adv_rank"] <= top_n].copy()
    wanted = set(pd.to_datetime(events["universe_month_end"].dropna().unique()))
    pools: dict[tuple[pd.Timestamp, str], list[str]] = {}
    for month_end, cohort in panel.groupby("month_end"):
        if month_end not in wanted:
            continue
        cohort = cohort.loc[cohort["symbol"].isin(close_wide.columns)]
        if cohort.empty:
            continue
        terciles = pd.qcut(
            cohort["dollar_adv"].rank(method="first"), 3, labels=["small", "mid", "large"]
        ).astype(str)
        for tercile, group in cohort.groupby(terciles):
            pools[(pd.Timestamp(month_end), str(tercile))] = sorted(group["symbol"])
    return pools


def _event_matrix(
    events: pd.DataFrame,
    open_wide: pd.DataFrame,
    close_wide: pd.DataFrame,
    sessions: pd.DatetimeIndex,
    *,
    symbols: list[str] | None = None,
    entry_shift: np.ndarray | None = None,
) -> pd.DataFrame:
    """Per-event raw/SPY-excess returns for every horizon, plus the
    pre-visibility run-up. ``symbols``/``entry_shift`` are the hooks the
    control and placebo variants use, so real, control and placebo runs all
    go through this one function."""
    spy_open = open_wide["SPY"].to_numpy(dtype="float64")
    spy_close = close_wide["SPY"].to_numpy(dtype="float64")
    use_symbols = symbols if symbols is not None else events["issuer_symbol"].tolist()
    entry_positions = events["entry_pos"].to_numpy()
    if entry_shift is not None:
        entry_positions = entry_positions + entry_shift
    filing_positions = sessions.searchsorted(events["filing_date"].to_numpy())

    columns: dict[str, list[Any]] = {f"ret_{h}": [] for h in HORIZONS}
    columns.update({f"excess_{h}": [] for h in HORIZONS})
    columns.update({f"liquidated_early_{h}": [] for h in HORIZONS})
    columns["pre_excess_5"] = []
    columns["announce_excess"] = []
    columns["gap_to_entry_excess"] = []
    cache: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    for index, symbol in enumerate(use_symbols):
        if symbol not in cache:
            cache[symbol] = (
                open_wide[symbol].to_numpy(dtype="float64"),
                close_wide[symbol].to_numpy(dtype="float64"),
            )
        prices_open, prices_close = cache[symbol]
        entry_pos = int(entry_positions[index])
        for horizon in HORIZONS:
            raw, liquidated = _window_return(prices_open, prices_close, entry_pos, horizon)
            bench, _ = _window_return(spy_open, spy_close, entry_pos, horizon)
            columns[f"ret_{horizon}"].append(raw)
            columns[f"liquidated_early_{horizon}"].append(liquidated)
            columns[f"excess_{horizon}"].append(
                raw - bench if np.isfinite(raw) and np.isfinite(bench) else float("nan")
            )
        filing_pos = int(filing_positions[index])
        pre = _pre_window_return(prices_close, filing_pos, PRE_WINDOW)
        pre_bench = _pre_window_return(spy_close, filing_pos, PRE_WINDOW)
        columns["pre_excess_5"].append(
            pre - pre_bench if np.isfinite(pre) and np.isfinite(pre_bench) else float("nan")
        )
        # announcement: close before the visible session -> close of the
        # visible session (the move we cannot trade at all)
        visible_pos = int(sessions.searchsorted(events["visible_session"].to_numpy()[index]))
        announce = _close_to_close(prices_close, visible_pos - 1, visible_pos)
        announce_bench = _close_to_close(spy_close, visible_pos - 1, visible_pos)
        columns["announce_excess"].append(
            announce - announce_bench
            if np.isfinite(announce) and np.isfinite(announce_bench)
            else float("nan")
        )
        # visible session close -> entry open (the overnight gap we give up)
        gap = _close_to_open(prices_close, prices_open, visible_pos, entry_pos)
        gap_bench = _close_to_open(spy_close, spy_open, visible_pos, entry_pos)
        columns["gap_to_entry_excess"].append(
            gap - gap_bench if np.isfinite(gap) and np.isfinite(gap_bench) else float("nan")
        )
    frame = pd.DataFrame(columns, index=events.index)
    frame["filing_month"] = events["filing_date"].dt.to_period("M").astype(str)
    frame["filing_date"] = events["filing_date"].to_numpy()
    frame["symbol"] = use_symbols
    return frame


def _close_to_close(prices: np.ndarray, start: int, end: int) -> float:
    if start < 0 or end >= len(prices) or end <= start:
        return float("nan")
    first, last = prices[start], prices[end]
    if not np.isfinite(first) or not np.isfinite(last) or first <= 0:
        return float("nan")
    return float(last / first - 1.0)


def _close_to_open(closes: np.ndarray, opens: np.ndarray, close_pos: int, open_pos: int) -> float:
    if close_pos < 0 or open_pos >= len(opens) or open_pos <= close_pos:
        return float("nan")
    first, last = closes[close_pos], opens[open_pos]
    if not np.isfinite(first) or not np.isfinite(last) or first <= 0:
        return float("nan")
    return float(last / first - 1.0)


def _window_masks(events: pd.DataFrame) -> dict[str, np.ndarray]:
    filing = events["filing_date"]
    return {
        "full_2016_2026": np.ones(len(events), dtype=bool),
        "pre_deadline_change": (filing < DEADLINE_CHANGE).to_numpy(),
        "post_deadline_change": (filing >= DEADLINE_CHANGE).to_numpy(),
        "2016_2019": ((filing.dt.year >= 2016) & (filing.dt.year <= 2019)).to_numpy(),
        "2020_2023": ((filing.dt.year >= 2020) & (filing.dt.year <= 2023)).to_numpy(),
        "2024_2026": (filing.dt.year >= 2024).to_numpy(),
    }


def _sample_funnel(
    all_filings: pd.DataFrame, close_wide: pd.DataFrame, sessions: pd.DatetimeIndex
) -> dict[str, int]:
    """Step-by-step sample attrition for new Schedule 13D filings.

    Written as a funnel rather than as independent counts because the filters
    overlap: an unverified issuer is also usually "outside the universe" (its
    symbol is null), so subtracting independent counts double-counts and was
    the first version's bug.
    """
    frame = all_filings.loc[all_filings["is_new_13d"]]
    funnel = {"new_13d_rows": int(len(frame))}
    frame = frame.loc[frame["issuer_verified"]]
    funnel["header_verified_issuer"] = int(len(frame))
    frame = frame.loc[frame["universe_bucket"] != "outside"]
    funnel["in_top1000_universe_at_filing"] = int(len(frame))
    frame = frame.loc[frame["visible_confidence"] == "acceptance_datetime"]
    funnel["with_acceptance_timestamp"] = int(len(frame))
    frame = frame.loc[frame["issuer_symbol"].isin(close_wide.columns)]
    funnel["priceable_on_our_tape"] = int(len(frame))
    positions = sessions.searchsorted(frame["entry_session"].to_numpy())
    frame = frame.loc[positions < len(sessions) - 1]
    funnel["entry_session_on_tape"] = int(len(frame))
    deduped = frame.assign(
        _pos=sessions.searchsorted(frame["entry_session"].to_numpy())
    ).drop_duplicates(subset=["issuer_symbol", "_pos"])
    funnel["after_co_filer_dedupe"] = int(len(deduped))
    return funnel


def stage_event_study() -> dict[str, Any]:
    open_wide, close_wide = load_price_matrices()
    sessions = pd.DatetimeIndex(open_wide.index)
    all_filings = load_events(new_only=False)
    events = _priceable_events(all_filings.loc[all_filings["is_new_13d"]], close_wide, sessions)
    _log(f"event-study: {len(events)} priceable new-13D events")

    real = _event_matrix(events, open_wide, close_wide, sessions)
    masks = _window_masks(events)
    payload: dict[str, Any] = {
        "card": "H-20260916-05",
        "generated_at": pd.Timestamp.utcnow().isoformat(),
        "entry_rule": (
            "open of the session after visible_session; exit at the close of session entry+H-1"
        ),
        "price_sanitize": dict(PRICE_SANITIZE_STATS),
        "sample_funnel": _sample_funnel(all_filings, close_wide, sessions),
        "n_priceable_events": int(len(events)),
        "windows": {},
    }

    for name, mask in masks.items():
        subset = real.loc[mask]
        clusters = subset["filing_month"].to_numpy()
        entry = {
            "n": int(mask.sum()),
            "first_filing": str(subset["filing_date"].min())[:10] if len(subset) else None,
            "last_filing": str(subset["filing_date"].max())[:10] if len(subset) else None,
            "pre_visibility_excess_5": _summarize(subset["pre_excess_5"].to_numpy(), clusters),
            "announcement_session_excess": _summarize(
                subset["announce_excess"].to_numpy(), clusters
            ),
            "visible_close_to_entry_open_excess": _summarize(
                subset["gap_to_entry_excess"].to_numpy(), clusters
            ),
        }
        for horizon in HORIZONS:
            entry[f"excess_{horizon}"] = _summarize(
                subset[f"excess_{horizon}"].to_numpy(), clusters
            )
            entry[f"raw_{horizon}"] = _summarize(subset[f"ret_{horizon}"].to_numpy(), clusters)
            entry[f"liquidated_early_share_{horizon}"] = (
                float(subset[f"liquidated_early_{horizon}"].mean()) if len(subset) else None
            )
        payload["windows"][name] = entry

    # ---- size-matched random controls -------------------------------------
    pools = _control_pools(events, close_wide)
    control_runs: list[pd.DataFrame] = []
    for seed in SEEDS:
        rng = np.random.default_rng(seed)
        picks: list[str] = []
        for month_end, tercile, symbol in zip(
            events["universe_month_end"],
            events["size_tercile_dollar_adv"],
            events["issuer_symbol"],
            strict=True,
        ):
            pool = pools.get((pd.Timestamp(month_end), str(tercile)), [])
            candidates = [name for name in pool if name != symbol]
            picks.append(str(rng.choice(candidates)) if candidates else str(symbol))
        control_runs.append(_event_matrix(events, open_wide, close_wide, sessions, symbols=picks))
        _log(f"event-study: control seed {seed} done")

    payload["size_matched_control"] = _seed_distribution(
        control_runs, masks, real=real, label="control"
    )

    # ---- filing-date shift placebo ---------------------------------------
    placebo_runs: list[pd.DataFrame] = []
    for seed in SEEDS:
        rng = np.random.default_rng(seed + 1)
        magnitude = rng.integers(1, PLACEBO_MAX_SHIFT + 1, size=len(events))
        sign = rng.choice([-1, 1], size=len(events))
        shift = magnitude * sign
        shifted = np.clip(
            events["entry_pos"].to_numpy() + shift, 1, len(sessions) - max(HORIZONS) - 1
        )
        placebo_runs.append(
            _event_matrix(
                events,
                open_wide,
                close_wide,
                sessions,
                entry_shift=shifted - events["entry_pos"].to_numpy(),
            )
        )
        _log(f"event-study: placebo seed {seed} done")

    payload["filing_shift_placebo"] = _seed_distribution(
        placebo_runs, masks, real=real, label="placebo"
    )

    # ---- subsamples (same events, sliced) --------------------------------
    payload["subsamples"] = {}
    slices = {
        "ticker_name_consistent": (
            events["issuer_name_matches_current_registrant"] == True  # noqa: E712
        ).to_numpy(),
        "ticker_renamed_since_filing": (
            events["issuer_name_matches_current_registrant"] == False  # noqa: E712
        ).to_numpy(),
        "bucket_top500": (events["universe_bucket"] == "top500").to_numpy(),
        "bucket_501_1000": (events["universe_bucket"] == "501_1000").to_numpy(),
        "item4_above_median": (events["item4_chars"] > events["item4_chars"].median()).to_numpy(),
        "item4_below_median": (events["item4_chars"] <= events["item4_chars"].median()).to_numpy(),
        "percent_of_class_ge_10": (events["percent_of_class"] >= 10.0).to_numpy(),
        "percent_of_class_lt_10": (events["percent_of_class"] < 10.0).to_numpy(),
    }
    for name, slice_mask in slices.items():
        entry: dict[str, Any] = {"n": int(slice_mask.sum())}
        for window_name in ("full_2016_2026", "post_deadline_change"):
            combined = slice_mask & masks[window_name]
            subset = real.loc[combined]
            entry[window_name] = {
                "n": int(combined.sum()),
                **{
                    f"excess_{horizon}": _summarize(
                        subset[f"excess_{horizon}"].to_numpy(), subset["filing_month"].to_numpy()
                    )
                    for horizon in HORIZONS
                },
            }
        payload["subsamples"][name] = entry

    # ---- amendments, reported as their own rows (never in the primary) ----
    amendments = _priceable_events(
        all_filings.loc[all_filings["form_type"] == "SC 13D/A"], close_wide, sessions
    )
    if len(amendments) >= 30:
        amendment_matrix = _event_matrix(amendments, open_wide, close_wide, sessions)
        amendment_masks = _window_masks(amendments)
        payload["amendments_13d_a"] = {
            "n": int(len(amendments)),
            "windows": {
                window_name: {
                    "n": int(window_mask.sum()),
                    **{
                        f"excess_{horizon}": _summarize(
                            amendment_matrix.loc[window_mask, f"excess_{horizon}"].to_numpy(),
                            amendment_matrix.loc[window_mask, "filing_month"].to_numpy(),
                        )
                        for horizon in HORIZONS
                    },
                }
                for window_name, window_mask in amendment_masks.items()
            },
        }
    else:
        payload["amendments_13d_a"] = {"n": int(len(amendments)), "note": "too few to report"}

    payload["not_done"] = {
        "schedule_13g_rows": (
            "13G/13G/A are index-only in this build: no fetched header, so no acceptance timestamp "
            "and no header-verified issuer (the filer of a 13G is usually a listed index manager, "
            "so index-only attribution would book events on BLK/BEN/TROW). Their exact "
            "attribution-free counts are in precheck.json's by_year_form_all."
        ),
    }

    _write_json(OUT_ROOT / "event-study.json", payload)
    real.assign(**{"issuer_symbol": events["issuer_symbol"].to_numpy()}).to_parquet(
        OUT_ROOT / "event-study-per-event.parquet", index=False, compression="zstd"
    )
    return payload


def _seed_distribution(
    runs: list[pd.DataFrame],
    masks: dict[str, np.ndarray],
    *,
    real: pd.DataFrame,
    label: str,
) -> dict[str, Any]:
    """Per-window, per-horizon seed distribution and its ratio to the real
    effect (L-20260916-03's rule: report a distribution, never one number)."""
    out: dict[str, Any] = {"seeds": list(SEEDS), "label": label, "windows": {}}
    for name, mask in masks.items():
        entry: dict[str, Any] = {}
        for horizon in HORIZONS:
            column = f"excess_{horizon}"
            real_mean = float(np.nanmean(real.loc[mask, column].to_numpy()))
            seed_means = [float(np.nanmean(run.loc[mask, column].to_numpy())) for run in runs]
            pooled = np.concatenate([run.loc[mask, column].to_numpy() for run in runs])
            clusters = np.concatenate([run.loc[mask, "filing_month"].to_numpy() for run in runs])
            entry[f"excess_{horizon}"] = {
                "real_mean": real_mean,
                "real_n": int(np.isfinite(real.loc[mask, column].to_numpy()).sum()),
                "seed_n_mean": float(
                    np.mean(
                        [int(np.isfinite(run.loc[mask, column].to_numpy()).sum()) for run in runs]
                    )
                ),
                "seed_means": seed_means,
                "seed_mean_of_means": float(np.mean(seed_means)),
                "seed_min": float(np.min(seed_means)),
                "seed_max": float(np.max(seed_means)),
                "ratio_to_real": float(np.mean(seed_means) / real_mean)
                if real_mean not in (0.0,) and np.isfinite(real_mean)
                else None,
                "pooled_t_clustered_by_month": _clustered_tstat(pooled, clusters),
            }
        out["windows"][name] = entry
    return out


# --------------------------------------------------------------------------
# stage: tradability
# --------------------------------------------------------------------------


def _book_schedule(
    events: pd.DataFrame,
    sessions: pd.DatetimeIndex,
    rebalances: list[pd.Timestamp],
    *,
    lookback: int,
    symbols_override: dict[pd.Timestamp, list[str]] | None = None,
) -> tuple[list[RebalanceEvent], pd.DataFrame]:
    entry_positions = events["entry_pos"].to_numpy()
    symbols = events["issuer_symbol"].to_numpy()
    schedule: list[RebalanceEvent] = []
    rows = []
    for rebalance in rebalances:
        position = int(sessions.searchsorted(rebalance, side="right")) - 1
        if position < 0:
            continue
        mask = (entry_positions <= position) & (entry_positions > position - lookback)
        names = sorted(set(symbols[mask]))
        if symbols_override is not None:
            names = symbols_override.get(rebalance, [])
        selected = {name: 1.0 / len(names) for name in names} if names else {CASH_SYMBOL: 1.0}
        schedule.append(
            RebalanceEvent(
                date=str(pd.Timestamp(rebalance).date()),
                universe_size=len(names),
                selected=selected,
                portfolio_beta=None,
            )
        )
        rows.append({"rebalance_date": rebalance, "names": len(names)})
    return schedule, pd.DataFrame(rows)


def _invested_day_mask(schedule: list[RebalanceEvent], index: pd.DatetimeIndex) -> pd.Series:
    """True on days the book held equities rather than sitting in cash."""
    marks = pd.Series(False, index=index)
    for i, event in enumerate(schedule):
        start = pd.Timestamp(event.date)
        end = pd.Timestamp(schedule[i + 1].date) if i + 1 < len(schedule) else index[-1]
        if event.universe_size > 0:
            marks.loc[(marks.index > start) & (marks.index <= end)] = True
    return marks


def _metrics(
    returns: pd.Series, spy: pd.Series, cash: pd.Series, *, start: pd.Timestamp | None
) -> dict[str, Any]:
    series = returns.dropna()
    if start is not None:
        series = series.loc[series.index >= start]
    if len(series) < 60:
        return {"n_days": int(len(series))}
    return {
        "n_days": int(len(series)),
        "start": str(series.index.min().date()),
        "end": str(series.index.max().date()),
        "cagr": annualized_cagr(series),
        "max_drawdown": max_drawdown(series),
        "vol_annualized": float(series.std() * np.sqrt(252)),
        "cagr_excess_vol_matched_spy": cagr_excess_vol_matched(
            series, spy.reindex(series.index), cash.reindex(series.index)
        ),
    }


def stage_tradability() -> dict[str, Any]:
    open_wide, close_wide = load_price_matrices()
    sessions = pd.DatetimeIndex(open_wide.index)
    all_filings = load_events(new_only=False)
    events = _priceable_events(all_filings.loc[all_filings["is_new_13d"]], close_wide, sessions)

    rebalances = [date for date in weekly_rebalance_dates(sessions) if date >= sessions[252]]
    schedule, book_sizes = _book_schedule(
        events, sessions, rebalances, lookback=BOOK_LOOKBACK_SESSIONS
    )
    spy_returns = close_wide["SPY"].astype("float64").pct_change().dropna()
    cash_returns = close_wide[CASH_SYMBOL].astype("float64").pct_change().dropna()

    book_returns = returns_from_weight_schedule(
        schedule,
        close_wide.astype("float64"),
        spy_returns,
        cost_bps_per_side=COST_BPS_PER_SIDE,
        include_hedge=False,
        execution="next_open",
        open_wide=open_wide.astype("float64"),
    )
    turnover = _turnover(schedule)

    # Exposure normalization (docs/current-view.zh.md rule 5): a book that is
    # in cash on the weeks with no recent 13D is not running the same risk as a
    # fully invested benchmark, so both readings are reported -- the raw series
    # (cash on empty weeks) and the invested-days-only series, together with
    # the share of days actually invested. With ~120 new 13D a year in the
    # top-1000 universe and a 60-session lookback the book is almost never
    # empty, so the two readings should nearly coincide; if they do not, the
    # raw one is the misleading one.
    invested_days = _invested_day_mask(schedule, book_returns.index)
    invested_returns = book_returns.loc[invested_days]

    payload: dict[str, Any] = {
        "card": "H-20260916-05",
        "generated_at": pd.Timestamp.utcnow().isoformat(),
        "book_rule": (
            f"weekly (last session of each ISO week), equal weight across every name whose new-13D "
            f"entry session is within the trailing {BOOK_LOOKBACK_SESSIONS} sessions; "
            f"{CASH_SYMBOL} when empty; next-open execution; {COST_BPS_PER_SIDE:.0f} bps/side"
        ),
        "price_sanitize": dict(PRICE_SANITIZE_STATS),
        "names_per_week": {
            "mean": float(book_sizes["names"].mean()),
            "median": float(book_sizes["names"].median()),
            "min": int(book_sizes["names"].min()),
            "max": int(book_sizes["names"].max()),
            "empty_weeks": int((book_sizes["names"] == 0).sum()),
            "weeks": int(len(book_sizes)),
            "mean_recent": float(
                book_sizes.loc[book_sizes["rebalance_date"] >= RECENT_WINDOW_START, "names"].mean()
            ),
        },
        "weekly_two_sided_turnover_mean": float(np.mean(turnover)) if turnover else None,
        "book": {
            "full": _metrics(book_returns, spy_returns, cash_returns, start=None),
            "recent_2024": _metrics(
                book_returns, spy_returns, cash_returns, start=RECENT_WINDOW_START
            ),
        },
        "book_invested_days_only": {
            "invested_day_share_full": float(invested_days.mean()),
            "invested_day_share_recent": float(
                invested_days.loc[invested_days.index >= RECENT_WINDOW_START].mean()
            ),
            "full": _metrics(invested_returns, spy_returns, cash_returns, start=None),
            "recent_2024": _metrics(
                invested_returns, spy_returns, cash_returns, start=RECENT_WINDOW_START
            ),
        },
        "benchmarks": {},
    }
    for symbol in ("SPY", "MTUM", "SPMO"):
        series = close_wide[symbol].astype("float64").pct_change().dropna()
        payload["benchmarks"][symbol] = {
            "full": _metrics(series, spy_returns, cash_returns, start=None),
            "recent_2024": _metrics(series, spy_returns, cash_returns, start=RECENT_WINDOW_START),
        }

    # same-size random control book: identical weekly name count, names drawn
    # from the same PIT top-1000 cohort as the real book.
    universe_panel = universe_mod.load_universe_panel(UNIVERSE_ROOT)
    control_results = []
    for seed in SEEDS:
        rng = np.random.default_rng(seed + 7)
        override: dict[pd.Timestamp, list[str]] = {}
        for row in book_sizes.itertuples(index=False):
            count = int(row.names)
            if count == 0:
                override[row.rebalance_date] = []
                continue
            cohort = sorted(
                universe_as_of_calendar_month(universe_panel, row.rebalance_date, top_n=1000)
                & set(close_wide.columns)
            )
            if len(cohort) <= count:
                override[row.rebalance_date] = cohort
                continue
            override[row.rebalance_date] = [
                str(name) for name in rng.choice(cohort, size=count, replace=False)
            ]
        control_schedule, _ = _book_schedule(
            events,
            sessions,
            rebalances,
            lookback=BOOK_LOOKBACK_SESSIONS,
            symbols_override=override,
        )
        control_returns = returns_from_weight_schedule(
            control_schedule,
            close_wide.astype("float64"),
            spy_returns,
            cost_bps_per_side=COST_BPS_PER_SIDE,
            include_hedge=False,
            execution="next_open",
            open_wide=open_wide.astype("float64"),
        )
        control_results.append(
            {
                "seed": seed,
                "full": _metrics(control_returns, spy_returns, cash_returns, start=None),
                "recent_2024": _metrics(
                    control_returns, spy_returns, cash_returns, start=RECENT_WINDOW_START
                ),
            }
        )
        _log(f"tradability: control book seed {seed} done")
    payload["same_size_random_control"] = {
        "seeds": control_results,
        "recent_cagr_mean": float(
            np.mean([item["recent_2024"].get("cagr", np.nan) for item in control_results])
        ),
        "recent_vol_matched_excess_mean": float(
            np.mean(
                [
                    item["recent_2024"].get("cagr_excess_vol_matched_spy", np.nan)
                    for item in control_results
                ]
            )
        ),
        "full_vol_matched_excess_mean": float(
            np.mean(
                [
                    item["full"].get("cagr_excess_vol_matched_spy", np.nan)
                    for item in control_results
                ]
            )
        ),
    }
    _write_json(OUT_ROOT / "tradability.json", payload)
    book_sizes.to_parquet(OUT_ROOT / "book-sizes.parquet", index=False, compression="zstd")
    return payload


def _turnover(schedule: list[RebalanceEvent]) -> list[float]:
    previous: dict[str, float] = {}
    values: list[float] = []
    for event in schedule:
        weights = dict(event.selected)
        touched = set(weights) | set(previous)
        values.append(
            sum(abs(weights.get(symbol, 0.0) - previous.get(symbol, 0.0)) for symbol in touched)
        )
        previous = weights
    return values


# --------------------------------------------------------------------------
# stage: validate-13g (index-only attribution error rate)
# --------------------------------------------------------------------------


def stage_validate_13g() -> dict[str, Any]:
    """How often does index-only issuer attribution get the issuer wrong?

    The 13G family is not document-fetched in this build, so its issuer is
    taken from the one index CIK that maps to a universe ticker. For a 13G the
    other party is usually a large index manager that is itself a top-1000
    name, so that fallback can book an event on the *filer*. This stage reads
    whatever 13G/13G/A documents have been fetched as a random validation
    sample and measures the error rate directly, turning a caveat into a
    number.
    """
    import scripts.collect_sec_13d_filings as collector

    docs = collector.load_docs()
    targets = pd.read_parquet(collector.TARGETS_PATH)
    tickers = collector.load_company_tickers(None)
    cik_to_symbol = (
        tickers.sort_values("symbol").drop_duplicates(subset=["cik"]).set_index("cik")["symbol"]
    )
    sample = docs.loc[docs["form_type"].isin(["SC 13G", "SC 13G/A"]) & (docs["http_status"] == 200)]
    if sample.empty:
        payload = {"n": 0, "note": "no 13G documents fetched yet"}
        _write_json(OUT_ROOT / "validate-13g.json", payload)
        return payload
    candidates = targets.groupby("accession")["candidate_symbol"].agg(
        lambda values: sorted(set(values))
    )
    rows = []
    for row in sample.itertuples(index=False):
        index_only = candidates.get(row.accession, [])
        header_symbol = cik_to_symbol.get(int(row.issuer_cik)) if pd.notna(row.issuer_cik) else None
        rows.append(
            {
                "accession": row.accession,
                "index_only_symbol": index_only[0] if len(index_only) == 1 else None,
                "index_only_ambiguous": len(index_only) > 1,
                "header_symbol": header_symbol if isinstance(header_symbol, str) else None,
                "header_issuer_untickered": header_symbol is None
                or not isinstance(header_symbol, str),
            }
        )
    frame = pd.DataFrame(rows)
    single = frame.loc[~frame["index_only_ambiguous"]]
    comparable = single.loc[single["header_symbol"].notna()]
    agree = int((comparable["index_only_symbol"] == comparable["header_symbol"]).sum())
    payload = {
        "n_sampled": int(len(frame)),
        "n_index_only_single_candidate": int(len(single)),
        "n_comparable_header_has_ticker": int(len(comparable)),
        "agreement": agree,
        "disagreement": int(len(comparable)) - agree,
        "disagreement_rate": (
            float((len(comparable) - agree) / len(comparable)) if len(comparable) else None
        ),
        "header_issuer_untickered_rate": float(single["header_issuer_untickered"].mean()),
        "note": (
            "disagreement means the index-only fallback picked a different symbol than the "
            "filing header's SUBJECT COMPANY -- i.e. it booked the filer, not the issuer"
        ),
    }
    _write_json(OUT_ROOT / "validate-13g.json", payload)
    _log(f"validate-13g: {json.dumps(payload)}")
    return payload


# --------------------------------------------------------------------------
# stage: report (stop conditions + the five mandatory comparison numbers)
# --------------------------------------------------------------------------

#: The card's three stop conditions. Written here, in code, so the verdict is
#: recomputed from the checkpoints rather than transcribed by hand.
STOP_CONDITION_TEXT = {
    "1_post_2024_t_below_2": (
        "post-2024-02-05 excess |t| < 2 at every horizon 20/40/60 (month-clustered t)"
    ),
    "2_placebo_or_control_reproduces_half": (
        "the filing-date-shift placebo or the size-matched random control reproduces >= 50% of "
        "the real effect"
    ),
    "3_effect_only_pre_2024": (
        "the effect exists only before 2024-02-05: significant and positive pre, absent post"
    ),
}


def _max_abs_t(window: dict[str, Any]) -> float:
    values = [
        abs(window[f"excess_{horizon}"]["t_clustered_by_month"] or 0.0) for horizon in HORIZONS
    ]
    return float(max(values)) if values else float("nan")


def _positive_and_significant(window: dict[str, Any]) -> bool:
    return any(
        (window[f"excess_{horizon}"]["mean"] or 0.0) > 0
        and abs(window[f"excess_{horizon}"]["t_clustered_by_month"] or 0.0) >= 2.0
        for horizon in HORIZONS
    )


def stage_report() -> dict[str, Any]:
    pre = json.loads((OUT_ROOT / "precheck.json").read_text())
    event = json.loads((OUT_ROOT / "event-study.json").read_text())
    trade = json.loads((OUT_ROOT / "tradability.json").read_text())
    validate = {}
    validate_path = OUT_ROOT / "validate-13g.json"
    if validate_path.exists():
        validate = json.loads(validate_path.read_text())

    post = event["windows"]["post_deadline_change"]
    prior = event["windows"]["pre_deadline_change"]
    full = event["windows"]["full_2016_2026"]

    condition_1 = _max_abs_t(post) < 2.0
    ratios: dict[str, float | None] = {}
    for label, key in (("control", "size_matched_control"), ("placebo", "filing_shift_placebo")):
        for window_name in ("full_2016_2026", "post_deadline_change"):
            for horizon in HORIZONS:
                cell = event[key]["windows"][window_name][f"excess_{horizon}"]
                real_mean = cell["real_mean"]
                ratios[f"{label}:{window_name}:{horizon}"] = (
                    cell["ratio_to_real"] if (real_mean or 0.0) > 0 else None
                )
    comparable = [value for value in ratios.values() if value is not None]
    condition_2 = any(value >= 0.5 for value in comparable) if comparable else None
    condition_3 = _positive_and_significant(prior) and not _positive_and_significant(post)

    verdicts = {
        "1_post_2024_t_below_2": {
            "text": STOP_CONDITION_TEXT["1_post_2024_t_below_2"],
            "triggered": bool(condition_1),
            "evidence": {
                "post_n": post["excess_20"]["n"],
                "max_abs_t_clustered": _max_abs_t(post),
                "per_horizon": {
                    str(horizon): {
                        "mean": post[f"excess_{horizon}"]["mean"],
                        "t_clustered_by_month": post[f"excess_{horizon}"]["t_clustered_by_month"],
                    }
                    for horizon in HORIZONS
                },
            },
        },
        "2_placebo_or_control_reproduces_half": {
            "text": STOP_CONDITION_TEXT["2_placebo_or_control_reproduces_half"],
            "triggered": condition_2,
            "not_applicable_reason": (
                None
                if comparable
                else "every real effect this ratio would be taken against is <= 0, so the ratio "
                "carries no information -- condition 1 is the one that decides"
            ),
            "evidence": {"ratios_where_real_effect_positive": ratios},
        },
        "3_effect_only_pre_2024": {
            "text": STOP_CONDITION_TEXT["3_effect_only_pre_2024"],
            "triggered": bool(condition_3),
            "evidence": {
                "pre_positive_and_significant": _positive_and_significant(prior),
                "post_positive_and_significant": _positive_and_significant(post),
                "pre_n": prior["excess_20"]["n"],
                "post_n": post["excess_20"]["n"],
            },
        },
    }

    benchmarks = trade["benchmarks"]
    payload = {
        "card": "H-20260916-05",
        "family": "event_13d_drift",
        "generated_at": pd.Timestamp.utcnow().isoformat(),
        "ledger": (
            "not written: this round does not go through loop.run_experiment, so "
            "reports/research/ledger/experiments.jsonl is untouched and every contract-v2 "
            "number quoted here is a reference_only disclosure"
        ),
        "precheck": {
            "new_13d_in_universe_total": pre["new_13d_total"],
            "new_13d_distinct_issuers": pre["new_13d_distinct_issuers"],
            "new_13d_by_year": {
                year: sum(row.values()) for year, row in pre["new_13d_by_year_bucket"].items()
            },
            "momentum_book_overlap": pre["momentum_book_overlap"],
        },
        "event_study": {
            "sample_funnel": event["sample_funnel"],
            "windows": {
                name: {
                    "n": window["excess_20"]["n"],
                    **{
                        f"excess_{horizon}": {
                            "mean": window[f"excess_{horizon}"]["mean"],
                            "median": window[f"excess_{horizon}"]["median"],
                            "t_naive": window[f"excess_{horizon}"]["t_naive"],
                            "t_clustered_by_month": window[f"excess_{horizon}"][
                                "t_clustered_by_month"
                            ],
                            "hit_rate": window[f"excess_{horizon}"]["hit_rate"],
                        }
                        for horizon in HORIZONS
                    },
                    "pre_visibility_excess_5": window["pre_visibility_excess_5"],
                    "announcement_session_excess": window["announcement_session_excess"],
                }
                for name, window in event["windows"].items()
            },
            "share_of_effect_before_visibility": _pre_visibility_share(full),
        },
        "tradability": {
            "names_per_week": trade["names_per_week"],
            "weekly_two_sided_turnover_mean": trade["weekly_two_sided_turnover_mean"],
            "book": trade["book"],
            "book_invested_days_only": trade["book_invested_days_only"],
            "same_size_random_control": trade["same_size_random_control"],
        },
        "five_mandatory_numbers_recent_2024": {
            "candidate_13d_book_cagr": trade["book"]["recent_2024"].get("cagr"),
            "candidate_13d_book_cagr_excess_vol_matched_spy": trade["book"]["recent_2024"].get(
                "cagr_excess_vol_matched_spy"
            ),
            "spy_cagr": benchmarks["SPY"]["recent_2024"].get("cagr"),
            "mtum_cagr": benchmarks["MTUM"]["recent_2024"].get("cagr"),
            "spmo_cagr": benchmarks["SPMO"]["recent_2024"].get("cagr"),
            "same_size_random_control_cagr_mean": trade["same_size_random_control"][
                "recent_cagr_mean"
            ],
            "same_size_random_control_vol_matched_excess_mean": trade["same_size_random_control"][
                "recent_vol_matched_excess_mean"
            ],
        },
        "stop_conditions": verdicts,
        "hypothesis_verdict": (
            "refuted"
            if any(item["triggered"] for item in verdicts.values() if item["triggered"] is not None)
            else "not refuted"
        ),
        "validate_13g": validate,
        "caveats": [
            "the PIT ADV universe and data/features/daily are built from surviving symbols only; "
            "13D targets that were acquired or delisted are absent by construction, and a "
            "takeover is the activist campaign's own best case",
            "issuers whose CIK has no row in the current company_tickers.json cannot be mapped at "
            "all (counted in the manifest as issuer_has_no_current_ticker_rows)",
            "size terciles are cut on dollar ADV, not market cap: this repo has no free "
            "point-in-time share count",
            "the 13G family is index-only: no acceptance timestamp and no header-verified issuer",
            "t-stats are reported both naive and clustered by filing month; activist filings "
            "arrive in bursts, so the clustered one is the one the stop conditions use",
        ],
    }
    _write_json(OUT_ROOT / "report.json", payload)
    _log(f"report: verdict={payload['hypothesis_verdict']}")
    return payload


def _pre_visibility_share(window: dict[str, Any]) -> dict[str, Any]:
    """How much of the whole move happens before anyone could act on it."""
    pre = window["pre_visibility_excess_5"]["mean"] or 0.0
    announce = window["announcement_session_excess"]["mean"] or 0.0
    post = window["excess_60"]["mean"] or 0.0
    total = pre + announce + post
    return {
        "pre_visibility_5_sessions": pre,
        "announcement_session": announce,
        "post_entry_60_sessions": post,
        "total": total,
        "share_before_entry": float((pre + announce) / total) if total else None,
        "note": (
            "share_before_entry is only meaningful when the three legs have the same sign; when "
            "the post-entry leg is negative, read the three numbers, not the ratio"
        ),
    }


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--stage",
        required=True,
        choices=["precheck", "event-study", "tradability", "validate-13g", "report", "all"],
    )
    parser.add_argument("--skip-overlap", action="store_true")
    args = parser.parse_args(argv)
    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    if args.stage in {"precheck", "all"}:
        stage_precheck(skip_overlap=args.skip_overlap)
    if args.stage in {"event-study", "all"}:
        stage_event_study()
    if args.stage in {"tradability", "all"}:
        stage_tradability()
    if args.stage in {"validate-13g", "all"}:
        stage_validate_13g()
    if args.stage in {"report", "all"}:
        stage_report()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
