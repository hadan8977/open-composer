"""H-20260916-07 step 1: point-in-time FINRA short-interest features.

Card: ``reports/research/hypotheses/H-20260916-07-finra-short-interest-avoid-list.md``
Input: ``data/raw/finra_short_interest/parsed.parquet`` (written by
``scripts/collect_finra_short_interest.py``) plus ``data/features/daily/`` for
the own-ADV denominator and ``data/features/universe/`` for the point-in-time
pool.
Output: ``data/features/short_interest/{year}.parquet`` -- one row per
``(trade_date, symbol)`` in the same ``symbol, trade_date`` key shape every
other feature library under ``data/features/`` uses.

Point-in-time rule (the only visibility rule in this file)
----------------------------------------------------------
A FINRA short-interest snapshot is usable from the **next US equity session
after its publication date**, where the publication date is FINRA's own
published one (the official settlement/publication table, scraped by the
collector) or, for settlement dates the live table does not cover, the rule
that table validates exactly: settlement + 7 US equity sessions. That makes
visibility settlement + 8 sessions at the earliest, consistent with FINRA's
prose ("roughly eight business days").

``settlementDate`` is **never** a visibility date. It is the date the positions
are as of, a week and a half before anybody outside FINRA can see them; keying
features on it would be a look-ahead worth more than any effect this card is
testing. ``staleness_days`` exists so that every row states how old its record
is instead of hiding it.

Columns
-------
See ``open_composer.research.features.short_interest`` for the contract; it is
the single source of the column list. Briefly:

``days_to_cover``
    FINRA's own ``daysToCoverQuantity`` for the latest visible record. Null,
    not 0, when that record's ``average_daily_volume`` is not positive (FINRA
    documents 0 as the field's *default*, i.e. "not computed").
``short_interest_ratio``
    ``short_interest_shares / adv_shares_63`` with ``adv_shares_63 =
    dollar_adv_63 / close`` from ``data/features/daily`` at the row's own
    ``trade_date``. This is an ADV-normalized ratio, **not** percent of float:
    the repo has no shares-outstanding or float series, so the card's "float
    proxy if available" branch is unavailable and this file says so rather than
    silently substituting one. Unlike ``days_to_cover`` it moves every day
    (the denominator does), which is deliberate: a squeeze risk measure should
    fall when a name's own volume explodes.
``dtc_change_vs_prior``
    ``days_to_cover`` minus the same symbol's previous *published* record's
    ``days_to_cover``. Both records are visible at the row's date by
    construction.
``dtc_cross_sectional_pct``
    Percentile of ``days_to_cover`` within that session's point-in-time
    top-500 ADV cohort. Symbols in the 501-1000 band are scored against the
    same top-500 reference distribution (``searchsorted``), so one threshold
    means one thing everywhere. Null when fewer than
    :data:`MIN_CROSS_SECTION` top-500 names have a visible record that day.
``staleness_days``
    US equity sessions from the record's ``visible_date`` to ``trade_date``
    (0 on the first usable session). Published as a negative control.

Revisions
---------
FINRA republishes a cycle with ``revisionFlag = 'R'`` when the *prior* cycle
was revised. This builder deliberately does not back-apply revisions: each
snapshot is used exactly as it was published, which is the only reading that
stays point-in-time. The flag survives in the raw archive for anyone who wants
to measure how often it fires.

Placebo (required by the card)
------------------------------
``--shift-publication-days N`` shifts every settlement date's publication (and
therefore visibility) session by a random integer drawn from
``{-N..-1} u {1..N}`` with a fixed seed (``--seed``, default 20260916). The
draw is per settlement date -- the natural granularity, since all ~209 dates
are published as one file each -- and the output goes to a separate root
(``data/features/short_interest_placebo_shift{N}_seed{S}/``) so a placebo table
can never be mistaken for the real one. A negative shift makes a snapshot
"visible" before FINRA published it; that is the point, and it is why the
placebo roots must never feed anything but a control cell.

Usage::

    ./scripts/run_capped.sh --mem 1.8G -- \\
        uv run python scripts/build_short_interest_features.py --as-of 2026-09-16

    for seed in 20260916 20260917 20260918 20260919 20260920; do
        ./scripts/run_capped.sh --mem 1.8G -- \\
            uv run python scripts/build_short_interest_features.py \\
            --shift-publication-days 10 --seed "$seed" --as-of 2026-09-16
    done
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from open_composer.market_calendar import us_equity_session_dates  # noqa: E402
from open_composer.research.features.short_interest import (  # noqa: E402
    CROSS_SECTIONAL_POOL_TOP_N,
    SHORT_INTEREST_COLUMNS,
    SHORT_INTEREST_METADATA_COLUMNS,
    SHORT_INTEREST_ROOT,
)
from open_composer.research.features.universe import load_universe_panel  # noqa: E402
from open_composer.research.kernel.loop import universe_as_of_calendar_month  # noqa: E402

PARSED_PATH = ROOT / "data" / "raw" / "finra_short_interest" / "parsed.parquet"
DAILY_ROOT = ROOT / "data" / "features" / "daily"
UNIVERSE_ROOT = ROOT / "data" / "features" / "universe"

FEATURE_UNIVERSE_TOP_N = 1000
#: Minimum number of top-500 names with a visible record before a session's
#: cross-sectional percentile is computed at all.
MIN_CROSS_SECTION = 50
DEFAULT_PLACEBO_SEED = 20260916
#: 2018 is the first full year the free FINRA API covers (the earliest
#: settlement date is 2017-12-29, first visible 2018-01-10).
DEFAULT_START_YEAR = 2018

READ_COLUMNS = (
    "settlement_date",
    "publication_date",
    "visible_date",
    "symbol",
    "short_interest_shares",
    "average_daily_volume",
    "days_to_cover",
)


def log(message: str) -> None:
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}", flush=True)


# --------------------------------------------------------------------------
# records
# --------------------------------------------------------------------------


def load_records(
    *,
    symbols: set[str] | None,
    sessions: pd.DatetimeIndex,
    shift_days: int,
    seed: int,
) -> pd.DataFrame:
    """Every published snapshot as ``(symbol, visible_idx, ...)`` rows.

    ``visible_idx`` is the position in ``sessions`` of the first session the
    snapshot may be used on. A snapshot whose visibility falls outside the
    session index (before the first or after the last) is dropped, not clamped:
    clamping would invent a visibility date.
    """
    if not PARSED_PATH.exists():
        raise SystemExit(
            f"no parsed FINRA archive at {PARSED_PATH}; run "
            "scripts/collect_finra_short_interest.py --stage download then --stage parse"
        )
    frame = pd.read_parquet(PARSED_PATH, columns=list(READ_COLUMNS))
    if symbols is not None:
        frame = frame.loc[frame["symbol"].isin(symbols)]
    frame = frame.copy()
    for column in ("settlement_date", "publication_date", "visible_date"):
        frame[column] = pd.to_datetime(frame[column]).dt.normalize()
    position = {timestamp: index for index, timestamp in enumerate(sessions)}
    frame["visible_idx"] = frame["visible_date"].map(position).astype("Int64")
    if shift_days > 0:
        frame = _apply_publication_shift(frame, shift_days=shift_days, seed=seed)
    frame = frame.loc[frame["visible_idx"].notna()].copy()
    frame["visible_idx"] = frame["visible_idx"].astype(np.int64)
    # FINRA documents days-to-cover's 0 as a default, not a measurement.
    frame.loc[~(frame["average_daily_volume"] > 0), "days_to_cover"] = np.nan
    frame = frame.sort_values(["symbol", "settlement_date"], ignore_index=True)
    frame["dtc_change_vs_prior"] = frame.groupby("symbol", sort=False)["days_to_cover"].diff()
    return frame.sort_values(["symbol", "visible_idx"], ignore_index=True)


def _apply_publication_shift(frame: pd.DataFrame, *, shift_days: int, seed: int) -> pd.DataFrame:
    """Placebo: per-settlement-date random +/-1..N session shift of visibility."""
    settlement_dates = pd.DatetimeIndex(sorted(frame["settlement_date"].unique()))
    rng = np.random.default_rng(seed)
    magnitude = rng.integers(1, shift_days + 1, size=len(settlement_dates))
    sign = rng.choice(np.array([-1, 1]), size=len(settlement_dates))
    shifts = pd.Series(magnitude * sign, index=settlement_dates)
    log(
        f"placebo: shifting visibility by a per-settlement-date draw from "
        f"+/-1..{shift_days} sessions (seed {seed}); "
        f"mean |shift| = {float(np.abs(shifts).mean()):.2f} sessions"
    )
    shifted = frame["visible_idx"] + frame["settlement_date"].map(shifts).astype("Int64")
    out = frame.copy()
    out["visible_idx"] = shifted
    out["placebo_visibility_shift_sessions"] = frame["settlement_date"].map(shifts).to_numpy()
    return out


# --------------------------------------------------------------------------
# per-year grid
# --------------------------------------------------------------------------


def load_adv_shares(year: int, symbols: set[str]) -> pd.DataFrame:
    """``(symbol, trade_date, adv_shares_63)`` -- our own 63-session average
    share volume, from ``dollar_adv_63 / close``.

    Non-positive or missing ``close`` yields null rather than an infinity: a
    ratio whose denominator we do not have is not a measurement.
    """
    path = DAILY_ROOT / f"{year}.parquet"
    if not path.exists():
        return pd.DataFrame(columns=["symbol", "trade_date", "adv_shares_63"])
    frame = pd.read_parquet(path, columns=["symbol", "trade_date", "close", "dollar_adv_63"])
    frame = frame.loc[frame["symbol"].isin(symbols)]
    close = frame["close"].where(frame["close"] > 0)
    frame["adv_shares_63"] = frame["dollar_adv_63"] / close
    return frame[["symbol", "trade_date", "adv_shares_63"]]


def build_year(
    year: int,
    *,
    records: pd.DataFrame,
    sessions: pd.DatetimeIndex,
    universe_panel: pd.DataFrame,
    top_n: int,
) -> pd.DataFrame:
    """One year of the feature table."""
    target_positions = np.flatnonzero(sessions.year == year)
    if target_positions.size == 0:
        return pd.DataFrame()
    target_dates = sessions[target_positions]
    cohorts = {
        timestamp: universe_as_of_calendar_month(universe_panel, timestamp, top_n=top_n)
        for timestamp in target_dates
    }
    pool_cohorts = {
        timestamp: set(
            universe_as_of_calendar_month(
                universe_panel, timestamp, top_n=CROSS_SECTIONAL_POOL_TOP_N
            )
        )
        for timestamp in target_dates
    }
    rows = [
        (timestamp, position, symbol)
        for timestamp, position in zip(target_dates, target_positions, strict=True)
        for symbol in cohorts[timestamp]
    ]
    if not rows:
        return pd.DataFrame()
    grid = pd.DataFrame(rows, columns=["trade_date", "session_idx", "symbol"])
    grid["in_pool_500"] = [
        symbol in pool_cohorts[timestamp]
        for timestamp, symbol in zip(grid["trade_date"], grid["symbol"], strict=True)
    ]

    # Latest visible record per (symbol, session): a backward as-of join on the
    # session index. ``merge_asof`` needs both sides sorted by the key.
    usable = records.loc[records["symbol"].isin(set(grid["symbol"]))]
    merged = pd.merge_asof(
        grid.sort_values("session_idx", ignore_index=True),
        usable[
            [
                "symbol",
                "visible_idx",
                "settlement_date",
                "publication_date",
                "visible_date",
                "short_interest_shares",
                "average_daily_volume",
                "days_to_cover",
                "dtc_change_vs_prior",
            ]
        ].sort_values("visible_idx", ignore_index=True),
        left_on="session_idx",
        right_on="visible_idx",
        by="symbol",
        direction="backward",
    )
    merged = merged.rename(columns={"average_daily_volume": "finra_average_daily_volume"})
    merged["si_record_present"] = merged["visible_idx"].notna()
    merged["staleness_days"] = (merged["session_idx"] - merged["visible_idx"]).astype("Float64")

    adv = load_adv_shares(year, set(grid["symbol"]))
    merged = merged.merge(adv, on=["symbol", "trade_date"], how="left")
    denominator = merged["adv_shares_63"].where(merged["adv_shares_63"] > 0)
    merged["short_interest_ratio"] = merged["short_interest_shares"] / denominator

    merged["dtc_cross_sectional_pct"] = _cross_sectional_percentile(merged)

    for column in ("days_to_cover", "short_interest_ratio", "dtc_change_vs_prior"):
        merged[column] = merged[column].astype("float64")
    merged["staleness_days"] = merged["staleness_days"].astype("float64")
    merged["si_record_present"] = merged["si_record_present"].astype("float64")
    columns = ["symbol", "trade_date", *SHORT_INTEREST_COLUMNS, *SHORT_INTEREST_METADATA_COLUMNS]
    return merged[columns].sort_values(["trade_date", "symbol"], ignore_index=True)


def _cross_sectional_percentile(merged: pd.DataFrame) -> pd.Series:
    """Percentile of ``days_to_cover`` against each session's top-500 pool.

    The reference distribution is the top-500 names *with a visible record*;
    every row (including 501-1000 band names) is scored against it with
    ``searchsorted`` so one threshold has one meaning. Sessions whose pool has
    fewer than :data:`MIN_CROSS_SECTION` usable names get null, not a
    percentile computed off a handful of names.
    """
    out = pd.Series(np.nan, index=merged.index, dtype="float64")
    for _, group in merged.groupby("session_idx", sort=False):
        pool = group.loc[group["in_pool_500"], "days_to_cover"].dropna().to_numpy()
        if pool.size < MIN_CROSS_SECTION:
            continue
        reference = np.sort(pool)
        values = group["days_to_cover"].to_numpy()
        valid = ~np.isnan(values)
        if not valid.any():
            continue
        ranks = np.searchsorted(reference, values[valid], side="right") / reference.size
        positions = group.index.to_numpy()[valid]
        out.loc[positions] = ranks
    return out


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--start-year", type=int, default=DEFAULT_START_YEAR)
    parser.add_argument("--end-year", type=int, default=date.today().year)
    parser.add_argument("--top-n", type=int, default=FEATURE_UNIVERSE_TOP_N)
    parser.add_argument(
        "--shift-publication-days",
        type=int,
        default=0,
        help="Placebo: per-settlement-date random +/-1..N session shift of visibility.",
    )
    parser.add_argument("--seed", type=int, default=DEFAULT_PLACEBO_SEED)
    parser.add_argument(
        "--as-of",
        type=str,
        default=None,
        help=(
            "Last feature date, YYYY-MM-DD. Defaults to today. Sessions after this date "
            "get no row at all, rather than a row whose record is stale only because the "
            "future has not happened yet."
        ),
    )
    parser.add_argument("--out-root", type=Path, default=None)
    parser.add_argument("--force", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    shift = max(0, args.shift_publication_days)
    out_root = args.out_root or (
        SHORT_INTEREST_ROOT
        if shift == 0
        else SHORT_INTEREST_ROOT.with_name(f"short_interest_placebo_shift{shift}_seed{args.seed}")
    )
    out_root.mkdir(parents=True, exist_ok=True)

    as_of = date.fromisoformat(args.as_of) if args.as_of else date.today()
    last_date = min(date(args.end_year, 12, 31), as_of)
    sessions = pd.DatetimeIndex(
        [
            pd.Timestamp(day)
            for day in us_equity_session_dates(date(args.start_year, 1, 1), last_date)
        ]
    )
    log(
        f"feature dates: {sessions[0].date()} .. {sessions[-1].date()} ({len(sessions):,} sessions)"
    )

    universe_panel = load_universe_panel(UNIVERSE_ROOT)
    universe_symbols = set(universe_panel.loc[universe_panel["adv_rank"] <= args.top_n, "symbol"])
    log(
        f"point-in-time universe union (adv_rank <= {args.top_n}): "
        f"{len(universe_symbols):,} symbols"
    )

    records = load_records(
        symbols=universe_symbols, sessions=sessions, shift_days=shift, seed=args.seed
    )
    log(
        f"{len(records):,} visible snapshots for {records['symbol'].nunique():,} symbols, "
        f"settlement {records['settlement_date'].min().date()}.."
        f"{records['settlement_date'].max().date()}, "
        f"days_to_cover null rate {float(records['days_to_cover'].isna().mean()):.3%}"
    )

    written: list[str] = []
    coverage: dict[str, float] = {}
    for year in range(args.start_year, args.end_year + 1):
        target = out_root / f"{year}.parquet"
        if target.exists() and not args.force:
            log(f"{year}: already built")
            written.append(str(target))
            continue
        frame = build_year(
            year,
            records=records,
            sessions=sessions,
            universe_panel=universe_panel,
            top_n=args.top_n,
        )
        if frame.empty:
            log(f"{year}: no rows (no sessions or no universe cohort)")
            continue
        temporary = target.with_suffix(".parquet.part")
        frame.to_parquet(temporary, index=False, compression="zstd")
        temporary.replace(target)
        written.append(str(target))
        coverage[str(year)] = float(frame["si_record_present"].mean())
        log(
            f"{year}: {len(frame):,} rows, {frame['symbol'].nunique():,} symbols, "
            f"with a visible record {coverage[str(year)]:.2%}, "
            f"median staleness {float(frame['staleness_days'].median()):.0f} sessions"
        )
        del frame

    manifest = {
        "card": "H-20260916-07",
        "built_at": datetime.now().astimezone().isoformat(),
        "as_of": last_date.isoformat(),
        "first_feature_date": sessions[0].date().isoformat(),
        "last_feature_date": sessions[-1].date().isoformat(),
        "source_parsed_archive": str(PARSED_PATH.relative_to(ROOT)),
        "visibility_rule": "next_us_equity_session(publication_date)",
        "publication_rule": "FINRA official schedule where published, else settlement + 7 sessions",
        "settlement_date_is_not_a_visibility_date": True,
        "feature_universe_top_n": args.top_n,
        "cross_sectional_pool_top_n": CROSS_SECTIONAL_POOL_TOP_N,
        "min_cross_section": MIN_CROSS_SECTION,
        "short_interest_ratio_denominator": "own dollar_adv_63 / close (ADV shares), not float",
        "placebo_shift_publication_days": shift,
        "placebo_seed": args.seed if shift else None,
        "coverage_share_with_visible_record": coverage,
        "years": written,
    }
    (out_root / "_build_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    log(f"wrote {out_root / '_build_manifest.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
