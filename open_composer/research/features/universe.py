"""Point-in-time (PIT) liquidity universe for the Step 11 ML-first research
loop (docs/plan-step-11-ml-first-loop-2026-09-06.zh.md section 3.2).

At every month-end ``t``, the universe is the top ``top_n`` symbols by
trailing ``adv_lookback_days``-session dollar ADV *as measured at t* -- never
a single latest-window snapshot applied across all history, which would use
2026 liquidity to decide 2016 membership (look-ahead). ``close > min_close``
is evaluated at the same month-end, for the same reason. This is the same PIT
discipline and the same DuckDB idiom already used and tested in
``scripts/evaluate_cross_sectional_momentum_liquid500.py`` (Step 10 Wave 2;
archived 2026-09-14 to git branch ``archive/rounds-2026-09``);
this module factors the query out into a reusable, testable function instead
of copy-pasting a third near-identical script.

**Known, recorded limitation (not fixed this round)**: the source archive
``data/sip/daily/`` was built from Alpaca's *currently active* US-equity
asset list (``scripts/fetch_sip_universe.py::load_universe``), so a symbol
that delisted before the archive's first fetch is invisible to this query
regardless of how liquid it once was. Step 10 Wave 2 measured this
survivorship-bias effect as immaterial for a large-cap-tilted liquid-500
momentum family (CAGR delta -0.12pp); a top-1500 universe reaches further
into small/mid caps, where historical delisting rates are higher, so the same
"immaterial" conclusion does not automatically transfer. ``data/sip-delisted/``
exists and could close this gap for the S&P 500 subset it covers, but the
plan's section 3.2 does not ask for that merge this round and it is left as a
next-iteration item (see the Step 11 ledger and the final report's candidate
list).
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd

DEFAULT_ADV_LOOKBACK_DAYS = 60
DEFAULT_TOP_N = 1500
DEFAULT_MIN_CLOSE = 5.0
DEFAULT_MEMORY_LIMIT = "2GB"

#: Columns persisted to ``data/features/universe/{year}.parquet``, per plan
#: section 3.2 ("列：month_end, symbol, adv_rank"). ``dollar_adv`` and
#: ``close`` are kept too -- they are cheap, already computed, and useful for
#: debugging/auditing the ranking without re-deriving it.
#:
#: **Consumer note**: ``month_end`` is one single shared date per calendar
#: month -- the last session of that month present in the source archive, the
#: date the whole cohort is decided on. ``dollar_adv`` and ``close`` are still
#: each symbol's own last available values *within* that month: a symbol that
#: stopped trading mid-month (delisted, acquired, halted) is ranked on its own
#: last trading day, which is the PIT-correct choice (it never had a later
#: price to rank on), but it is still stamped with the cohort's shared
#: ``month_end`` so the cohort is a single dated cross-section.
#:
#: Before 2026-09-16 ``month_end`` carried each symbol's *own* last trade date,
#: which made every acquisition/delisting emit a one-row "cohort" dated
#: mid-month (e.g. 2019-10-02 BID, 2021-04-05 PS); a consumer asking "the most
#: recent cohort as of date d" for a d inside that month then got a 1-symbol
#: universe. See ``reports/research/control/universe-cohort-fix-2026-09-16.md``.
#: Grouping by ``month_end.dt.to_period("M")`` remains correct and is what
#: ``kernel.loop.universe_as_of_calendar_month`` does; it is now equivalent to
#: grouping by the exact value.
UNIVERSE_PANEL_COLUMNS = ("month_end", "symbol", "adv_rank", "dollar_adv", "close")


def build_pit_universe_panel(
    daily_glob: str | list[str],
    *,
    adv_lookback_days: int = DEFAULT_ADV_LOOKBACK_DAYS,
    top_n: int | None = DEFAULT_TOP_N,
    min_close: float = DEFAULT_MIN_CLOSE,
    min_dollar_adv: float | None = None,
    memory_limit: str = DEFAULT_MEMORY_LIMIT,
    temp_directory: str | None = None,
    con: duckdb.DuckDBPyConnection | None = None,
) -> pd.DataFrame:
    """One row per (month_end, symbol) admitted to the PIT dollar-ADV universe,
    where ``month_end`` is the *shared* cohort date of that calendar month (the
    month's last session in ``daily_glob``) -- see :data:`UNIVERSE_PANEL_COLUMNS`.
    The archive's trailing, still-running calendar month gets no cohort at all
    (see the ``complete_month_end`` CTE): a monthly universe must not start
    applying mid-month.

    Admission has two independent knobs, both applied at each month end:
    ``top_n`` keeps the ``top_n`` highest trailing-dollar-ADV symbols
    (``None`` = no rank cap) and ``min_dollar_adv`` keeps symbols whose
    trailing dollar ADV is at least that floor (``None`` = no floor). Every row
    still carries ``adv_rank`` over the *whole* month-end cross-section, so a
    floor-mode universe can be split into liquidity bands (1-500 / 501-1500 /
    1501+) downstream without rebuilding. The rank-cap default reproduces the
    pre-2026-09-17 top-1500 universe; the floor mode is the broad universe of
    ``reports/research/hypotheses/D-20260917-01-broad-universe-and-delisted-backfill.md``.

    ``daily_glob`` is a DuckDB ``read_parquet`` glob or a list of globs (e.g.
    ``["data/sip/daily/*/*.parquet", "data/sip-delisted/by_year/*/*.parquet"]``
    so backfilled delisted names rank alongside survivors);
    ``symbol NOT LIKE '%.%'``/``'%/%'`` excludes share-class/warrant ticker
    variants, matching the convention already used by
    ``scripts/evaluate_cross_sectional_momentum_liquid500.py`` (archived
    2026-09-14 to git branch ``archive/rounds-2026-09``).
    """
    if top_n is None and min_dollar_adv is None:
        raise ValueError("at least one of top_n or min_dollar_adv must be set")
    admission = []
    if top_n is not None:
        admission.append(f"ranked.adv_rank <= {int(top_n)}")
    if min_dollar_adv is not None:
        admission.append(f"ranked.dollar_adv >= {float(min_dollar_adv)}")
    admission_sql = " AND ".join(admission)
    owns_connection = con is None
    connection = con or duckdb.connect()
    from scripts.forward_io_limits import apply_forward_limits

    apply_forward_limits(connection)
    try:
        connection.execute(f"SET memory_limit='{memory_limit}'")
        if temp_directory is not None:
            Path(temp_directory).mkdir(parents=True, exist_ok=True)
            connection.execute(f"SET temp_directory='{temp_directory}'")
        query = f"""
            WITH raw AS (
                SELECT symbol, timestamp, close, volume
                FROM read_parquet({daily_glob!r}, union_by_name=true)
                WHERE symbol NOT LIKE '%.%' AND symbol NOT LIKE '%/%'
            ),
            priced AS (
                SELECT
                    symbol,
                    CAST(timestamp AS DATE) AS trade_date,
                    close,
                    AVG(close * volume) OVER (
                        PARTITION BY symbol ORDER BY timestamp
                        ROWS BETWEEN {adv_lookback_days - 1} PRECEDING AND CURRENT ROW
                    ) AS dollar_adv
                FROM raw
            ),
            month_last_session AS (
                -- The cohort date: the last session of each calendar month
                -- present anywhere in the archive. Shared by every row of the
                -- cohort so that a symbol whose own last bar of the month is
                -- mid-month (delisted/acquired/halted) does not emit a
                -- separate, one-row, mid-month "cohort".
                SELECT date_trunc('month', trade_date) AS month_key,
                       MAX(trade_date) AS cohort_date
                FROM priced
                GROUP BY 1
            ),
            complete_month_end AS (
                -- Only *finished* calendar months get a cohort: a month is
                -- finished once the archive holds a session in a later month.
                -- The archive's trailing, still-running month would otherwise
                -- be stamped with a mid-month cohort date -- the same class of
                -- defect as the delisting rows above, since a monthly universe
                -- must not change membership in the middle of a month. It
                -- reappears, dated the real month end, on the next rebuild
                -- once the following month has data.
                SELECT month_key, cohort_date
                FROM month_last_session
                WHERE month_key < (SELECT MAX(month_key) FROM month_last_session)
            ),
            monthly AS (
                SELECT *,
                       ROW_NUMBER() OVER (
                           PARTITION BY symbol, date_trunc('month', trade_date)
                           ORDER BY trade_date DESC
                       ) AS rank_in_month
                FROM priced
                WHERE dollar_adv IS NOT NULL
            ),
            month_end AS (
                SELECT * FROM monthly WHERE rank_in_month = 1 AND close > {min_close}
            ),
            ranked AS (
                SELECT *,
                       RANK() OVER (
                           PARTITION BY date_trunc('month', trade_date) ORDER BY dollar_adv DESC
                       ) AS adv_rank
                FROM month_end
            )
            SELECT complete_month_end.cohort_date AS month_end,
                   ranked.symbol,
                   ranked.adv_rank,
                   ranked.dollar_adv,
                   ranked.close
            FROM ranked
            JOIN complete_month_end
              ON complete_month_end.month_key = date_trunc('month', ranked.trade_date)
            WHERE {admission_sql}
            ORDER BY month_end, adv_rank
        """
        panel = connection.execute(query).fetchdf()
    finally:
        if owns_connection:
            connection.close()
    panel["month_end"] = pd.to_datetime(panel["month_end"])
    return panel


def exclude_funds_and_etfs(panel: pd.DataFrame, asset_metadata: pd.DataFrame) -> pd.DataFrame:
    """Drop rows whose symbol is flagged ``is_probable_fund_or_etf`` in
    ``asset_metadata`` (see ``asset_metadata.py``). A symbol absent from
    ``asset_metadata`` (e.g. delisted before the metadata snapshot) is kept --
    absence of evidence is not evidence of being a fund.
    """
    fund_symbols = set(asset_metadata.loc[asset_metadata["is_probable_fund_or_etf"], "symbol"])
    return panel.loc[~panel["symbol"].isin(fund_symbols)].reset_index(drop=True)


def write_universe_by_year(panel: pd.DataFrame, out_dir: Path | str) -> dict[int, Path]:
    """Split ``panel`` by ``month_end`` calendar year and write
    ``{out_dir}/{year}.parquet`` with columns :data:`UNIVERSE_PANEL_COLUMNS`.
    Returns the year -> path mapping actually written.
    """
    out_root = Path(out_dir)
    out_root.mkdir(parents=True, exist_ok=True)
    written: dict[int, Path] = {}
    years = sorted(int(year) for year in panel["month_end"].dt.year.unique())
    for year in years:
        year_frame = panel.loc[panel["month_end"].dt.year == year, list(UNIVERSE_PANEL_COLUMNS)]
        year_frame = year_frame.sort_values(["month_end", "adv_rank"]).reset_index(drop=True)
        path = out_root / f"{year}.parquet"
        year_frame.to_parquet(path, index=False)
        written[year] = path
    return written


def load_universe_panel(feature_root: Path | str, years: list[int] | None = None) -> pd.DataFrame:
    """Read back ``data/features/universe/{year}.parquet`` for ``years``
    (default: every year present) and concatenate into one frame.
    """
    root = Path(feature_root)
    if years is None:
        years = sorted(int(path.stem) for path in root.glob("*.parquet") if path.stem.isdigit())
    frames = [pd.read_parquet(root / f"{year}.parquet") for year in years]
    if not frames:
        raise FileNotFoundError(f"no universe parquet files found under {root}")
    return pd.concat(frames, ignore_index=True)


def universe_union_symbols(feature_root: Path | str, years: list[int] | None = None) -> set[str]:
    """The full-history union of every symbol that was ever admitted to the
    universe -- the set every downstream feature/label computation should
    restrict itself to (plan section 3.3: "只算并集里的 symbol").
    """
    panel = load_universe_panel(feature_root, years=years)
    return set(panel["symbol"].unique())



def build_daily_sip_universe(stage: Path, output: Path) -> dict:
    """Build the dated close observations and their next eligible execution session."""
    from datetime import datetime, time, timedelta
    from time import perf_counter

    import numpy as np

    from open_composer.research.equity_book.borrow import detect_reverse_splits, reverse_split_in_window
    from open_composer.market_sessions import NEW_YORK, next_us_equity_session, us_equity_session_dates
    from open_composer.research.features.archive_handoffs import archive_handoffs
    from open_composer.research.features.daily_actions import (
        ACTIONS, ANCHORS, action_factors, join_action_bars, reconstruct_raw,
    )
    from open_composer.research.features.panel import _connect, load_sip_daily_panel
    from open_composer.research.features.price_hygiene import (
        DEFAULT_MASK_GAP_LONG_SESSIONS,
        drop_ghost_bars,
        sanitize_price_matrices,
    )
    from open_composer.research.features.security_type import (
        TYPED_MEMBERS,
        register_security_evidence,
    )

    started = perf_counter()
    stage.mkdir(parents=True, exist_ok=True)
    for year in range(2016, datetime.now().year + 1):
        for basis in ("all", "raw"):
            if (stage / f"{basis}-{year}.parquet").exists():
                continue
            for start, end in (("01-01", "06-30"), ("07-01", "12-31")):
                path = stage / f"{basis}-{year}-{start}.parquet"
                if path.exists():
                    continue
                bars = load_sip_daily_panel(
                    f"{year}-{start}", f"{year}-{end}T23:59:59Z", adjustment=basis,
                )
                bars = drop_ghost_bars(bars)
                bars[["symbol", "trade_date", "open", "close", "volume", "source_version"]].to_parquet(
                    path, index=False, row_group_size=65536,
                )
                del bars

    pending = output.with_suffix(".partial")
    with _connect("500MB") as con:
        con.execute(f"SET temp_directory={(stage / 'spill').as_posix()!r}")
        for view, basis in (("adj", "all"), ("raw", "raw")):
            path = (stage / f"{basis}-*.parquet").as_posix()
            con.execute(f"CREATE VIEW {view} AS SELECT * FROM read_parquet({path!r})")
        anchors = output.parent / ANCHORS
        con.execute(f"CREATE VIEW anchors AS SELECT * FROM read_parquet({anchors.as_posix()!r})")
        first, last = con.sql(
            "SELECT min(trade_date), max(trade_date) FROM adj WHERE symbol = 'SPY'"
        ).fetchone()
        action_path = output.parent / ACTIONS
        actions, mapped_actions = action_factors(con, action_path, anchors, last)
        sessions = us_equity_session_dates(first.date(), last.date())
        dates = pd.DatetimeIndex(sessions)
        members = pd.Index(con.sql("SELECT DISTINCT symbol FROM adj ORDER BY 1").fetchnumpy()["symbol"])
        next_sessions = [next_us_equity_session(d) for d in sessions]
        calendar = pd.DataFrame({
            "trade_date": dates,
            "session": pd.to_datetime(next_sessions),
            "known_at": pd.to_datetime([
                datetime.combine(d + timedelta(days=1), time(), NEW_YORK) for d in sessions
            ], utc=True),
            "decision_at": pd.to_datetime([
                datetime.combine(d, time(9, 30), NEW_YORK) for d in next_sessions
            ], utc=True),
        })
        con.register("calendar", calendar)
        join_action_bars(con, "b.trade_date IN (SELECT trade_date FROM calendar)")
        register_security_evidence(con, members)
        switches, renames, aliases = archive_handoffs(con, action_path)
        switch_keys = ["symbol", "trade_date"]
        alias_mask = [(r.symbol, r.trade_date, r.source_version) in aliases for r in switches.itertuples()]
        switches.loc[alias_mask, "status"] = "backfilled alias"
        switches.loc[alias_mask, "factor"] = np.nan
        alias_rows = pd.DataFrame(sorted(aliases), columns=["symbol", "trade_date", "source_version"])
        con.register("aliases", alias_rows.astype({
            "symbol": "string", "trade_date": "datetime64[ns]", "source_version": "string",
        }))
        removed_aliases = con.sql("""
            SELECT count(*) FROM joined SEMI JOIN aliases USING (symbol, trade_date, source_version)
        """).fetchone()[0]
        factors = switches.set_index(switch_keys).factor
        batches = []
        for lo in range(0, len(members), 256):
            keys = members[lo:lo + 256].tolist()
            extra = [new for new, (old, _) in renames.items() if old in keys and new not in keys]
            extra_symbols = " OR j.symbol IN (" + ", ".join("?" for _ in extra) + ")" if extra else ""
            f = con.execute(f"""
                SELECT j.* FROM joined j ANTI JOIN aliases USING (symbol, trade_date, source_version)
                WHERE j.symbol BETWEEN ? AND ? {extra_symbols}
            """, [keys[0], keys[-1], *extra]).df()
            f["trade_date"] = f["trade_date"].astype("datetime64[ns]")
            f["lineage"] = f.symbol
            for new, (old, day) in renames.items():
                f.loc[f.symbol.eq(new) & f.trade_date.ge(day), "lineage"] = old
            f = f.loc[f.lineage.isin(keys)].sort_values(["lineage", "trade_date"]).reset_index(drop=True)
            groups = f.groupby("lineage", sort=False)
            previous_source = groups.source_version.shift()
            source_change = previous_source.notna() & f.source_version.ne(previous_source)
            factor = factors.reindex(pd.MultiIndex.from_frame(f[switch_keys])).to_numpy(dtype=float)
            # A rename's first row inherits the old ticker's basis; its original
            # source-switch candidate measured a different predecessor.
            factor = np.where(source_change & f.symbol.eq(groups.symbol.shift()), factor, np.nan)
            unlinked = source_change & np.isnan(factor)
            scale = pd.Series(np.nan_to_num(factor, nan=1), index=f.index).groupby(f.lineage).cumprod()
            prices = f[["trade_date", "lineage"]].assign(
                close=f.adjusted_close * scale, open=f.adjusted_open * scale,
            ).set_index(["trade_date", "lineage"])
            close, open_ = prices.close.unstack(), prices.open.unstack()
            hygiene = sanitize_price_matrices(
                close.reindex(dates), open_.reindex(dates), preserve_history=True, break_at_open=True,
            )[2]
            breaks = {(b.symbol, b.first_session_after) for b in hygiene.breaks if b.masked}
            f["regime_start"] = [
                (s, d) in breaks for s, d in zip(f.lineage, f.trade_date, strict=True)
            ]
            f["session_pos"] = dates.get_indexer(f.trade_date)
            # Reconstruct raw units on their native archive and ticker basis.
            raw_break = f.regime_start | source_change | f.symbol.ne(groups.symbol.shift())
            f["security_id"] = f.lineage + "@" + raw_break.groupby(f.lineage).cumsum().astype(str)
            error_fields = ["close_error", "volume_error", "dollars_error"]
            f[error_fields] = reconstruct_raw(f, actions, mapped_actions)
            f["regime_start"] |= unlinked
            f["security_id"] = f.lineage + "@" + groups.regime_start.cumsum().astype(str)
            life = f.groupby("security_id", sort=False)
            f["listing_date"] = life.trade_date.transform("first")
            f["issuer_symbol"] = life.symbol.transform("first")
            rows = f.session_pos.to_numpy()
            ids = pd.Index(f.security_id.unique())
            cols = ids.get_indexer(f.security_id)
            shape = (len(dates), len(ids))
            ro = pd.DataFrame(np.full(shape, np.nan))
            rc = ro.copy()
            ro.values[rows, cols], rc.values[rows, cols] = f.raw_open, f.original_raw_close
            rs = detect_reverse_splits(ro, rc)
            f["reverse_split_252"] = reverse_split_in_window(rs).to_numpy()[rows, cols]
            del ro, rc, rs
            f["dollar_volume"] = f.close * f.raw_volume
            liquidity = pd.DataFrame(np.full(shape, np.nan))
            liquidity.values[rows, cols] = f.dollar_volume
            f["median_dollar_volume_20"] = liquidity.shift().rolling(20).median().to_numpy()[rows, cols]
            f["adjusted_close"] *= scale
            f["adjusted_open"] *= scale
            base = life.adjusted_close.transform("first")
            f["adjusted_close"] = (100 * f.adjusted_close / base).astype("float32")
            f["adjusted_open"] = (100 * f.adjusted_open / base).astype("float32")
            f["last_trade_date"] = pd.NaT
            f["is_member"] = True
            exits = life.tail(1)[["symbol", "issuer_symbol", "lineage", "security_id",
                                  "listing_date", "trade_date", "session_pos"]].copy()
            next_break = exits.lineage.eq(exits.lineage.shift(-1))
            following = life.session_pos.first().shift(-1).reindex(exits.security_id).to_numpy()
            expiry = exits.session_pos + DEFAULT_MASK_GAP_LONG_SESSIONS
            exits["session_pos"] = np.where(next_break, np.minimum(expiry, following), expiry).astype(int)
            exits = exits.loc[exits.session_pos < len(dates)].copy()
            exits["last_trade_date"] = exits.trade_date
            exits["trade_date"] = dates[exits.session_pos]
            exits["is_member"] = False
            fields = [
                "trade_date", "symbol", "issuer_symbol", "security_id", "close", "adjusted_open", "adjusted_close",
                "raw_volume", "dollar_volume", "median_dollar_volume_20", "reverse_split_252",
                "listing_date", "last_trade_date", "is_member", "source_version",
                *error_fields,
            ]
            batch = stage / f"members-{lo}.parquet"
            pd.concat([f, exits], ignore_index=True)[fields].to_parquet(batch, index=False)
            batches.append(batch.as_posix())
            del f, groups, life, close, open_, liquidity

        con.execute("DROP TABLE joined")
        con.execute(f"CREATE VIEW members AS SELECT * FROM read_parquet({batches!r})")
        con.execute(f"""
            COPY (
                SELECT * EXCLUDE (issuer_symbol, issuer_cik, {", ".join(error_fields)}) FROM ({TYPED_MEMBERS})
                ORDER BY trade_date, security_id
            ) TO {pending.as_posix()!r} (FORMAT PARQUET, COMPRESSION ZSTD, ROW_GROUP_SIZE 32768)
        """)
        report = con.execute("""
            SELECT year(trade_date) AS year, count(DISTINCT symbol) AS names,
                   count(*) AS member_rows, count(close) AS priced_rows,
                   count(*) FILTER (WHERE median_dollar_volume_20 >= 10000000) AS liquid_rows,
                   count(DISTINCT security_id) FILTER (WHERE median_dollar_volume_20 >= 10000000) AS liquid_members,
                   count(*) - count(close) AS missing_close, count(*) - count(raw_volume) AS missing_volume,
                   count(*) - count(dollar_volume) AS missing_dollars,
                   count(*) - count(median_dollar_volume_20) AS missing_median
            FROM read_parquet(?) WHERE is_member AND session IS NOT NULL GROUP BY 1 ORDER BY 1
        """, [str(pending)]).df().to_dict("records")
        type_report = con.execute("""
            SELECT year(session) AS year, security_type, count(*) AS member_rows,
                   count(dollar_volume) AS priced_rows, sum(dollar_volume) AS dollar_volume
            FROM read_parquet(?) WHERE is_member GROUP BY 1, 2 ORDER BY 1, 2
        """, [str(pending)]).fetchall()
        n_rows = con.execute("SELECT count(*) FROM read_parquet(?)", [str(pending)]).fetchone()[0]
        quantiles = ", ".join(
            f"count({field}) AS {field}_rows, quantile_cont({field}, [0.5, 0.99]) AS {field}"
            for field in error_fields
        )
        errors = con.sql(f"""
            SELECT coalesce(source_version, 'all sources') AS source, {quantiles}
            FROM members WHERE is_member GROUP BY GROUPING SETS ((source_version), ())
            ORDER BY source
        """).fetchall()
    pending.replace(output)
    return {
        "by_year": report,
        "by_security_type": [
            dict(year=year, security_type=kind, member_rows=rows, priced_rows=priced, dollar_volume=dollars)
            for year, kind, rows, priced, dollars in type_report
        ],
        "raw_overlap_errors": [
            dict(zip(["source", *(key for field in error_fields for key in (f"{field}_rows", field))], row))
            for row in errors
        ],
        "symbols": len(members), "rows": n_rows, "first": str(dates[0].date()),
        "last": str(dates[-1].date()), "build_seconds": perf_counter() - started,
        "archive_switches": [
            dict(trade_date=str(day.date()), reason=reason, count=int(count))
            for (day, reason), count in switches.groupby(["trade_date", "status"]).size().items()
        ],
        "ticker_changes": [
            dict(old_symbol=old, symbol=new, trade_date=str(day.date())) for new, (old, day) in renames.items()
        ],
        "backfilled_alias_rows": removed_aliases,
    }
