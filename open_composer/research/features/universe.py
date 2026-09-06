"""Point-in-time (PIT) liquidity universe for the Step 11 ML-first research
loop (docs/plan-step-11-ml-first-loop-2026-09-06.zh.md section 3.2).

At every month-end ``t``, the universe is the top ``top_n`` symbols by
trailing ``adv_lookback_days``-session dollar ADV *as measured at t* -- never
a single latest-window snapshot applied across all history, which would use
2026 liquidity to decide 2016 membership (look-ahead). ``close > min_close``
is evaluated at the same month-end, for the same reason. This is the same PIT
discipline and the same DuckDB idiom already used and tested in
``scripts/evaluate_cross_sectional_momentum_liquid500.py`` (Step 10 Wave 2);
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
#: **Consumer note**: ``month_end`` is each symbol's own last available trade
#: date within that calendar month, not a single shared date -- a symbol that
#: stopped trading mid-month (delisted, halted) is ranked and admitted using
#: its own last trading day, which is the PIT-correct choice (it never had a
#: later price to rank on) but means two rows for the "same" monthly cohort
#: can carry different exact ``month_end`` values (verified against the real
#: archive: 2016-03 has 1174 rows dated 2016-03-31 and 1 row dated
#: 2016-03-23). Group by ``month_end.dt.to_period("M")`` to reconstruct "the
#: cohort decided at month X", never by the exact ``month_end`` value.
UNIVERSE_PANEL_COLUMNS = ("month_end", "symbol", "adv_rank", "dollar_adv", "close")


def build_pit_universe_panel(
    daily_glob: str,
    *,
    adv_lookback_days: int = DEFAULT_ADV_LOOKBACK_DAYS,
    top_n: int = DEFAULT_TOP_N,
    min_close: float = DEFAULT_MIN_CLOSE,
    memory_limit: str = DEFAULT_MEMORY_LIMIT,
    temp_directory: str | None = None,
    con: duckdb.DuckDBPyConnection | None = None,
) -> pd.DataFrame:
    """One row per (month_end, symbol) admitted to the PIT top-``top_n``
    dollar-ADV universe. ``daily_glob`` is a DuckDB ``read_parquet`` glob
    (e.g. ``data/sip/daily/*/*.parquet``); ``symbol NOT LIKE '%.%'``/``'%/%'``
    excludes share-class/warrant ticker variants, matching the convention
    already used by ``scripts/evaluate_cross_sectional_momentum_liquid500.py``.
    """
    owns_connection = con is None
    connection = con or duckdb.connect()
    try:
        connection.execute(f"SET memory_limit='{memory_limit}'")
        if temp_directory is not None:
            Path(temp_directory).mkdir(parents=True, exist_ok=True)
            connection.execute(f"SET temp_directory='{temp_directory}'")
        query = f"""
            WITH raw AS (
                SELECT symbol, timestamp, close, volume
                FROM read_parquet({daily_glob!r})
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
            SELECT trade_date AS month_end, symbol, adv_rank, dollar_adv, close
            FROM ranked
            WHERE adv_rank <= {top_n}
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
