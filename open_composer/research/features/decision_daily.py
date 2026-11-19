"""Yearly daily stock features keyed by security_id and next opening session."""

from __future__ import annotations

import argparse
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter

import numpy as np
import pandas as pd

from open_composer.adapters.data.sip_parquet import MARKET_DATA
from open_composer.market_sessions import NEW_YORK, us_equity_session_dates
from open_composer.research.features.panel import _connect, load_sip_daily_panel
from open_composer.research.features.price_hygiene import daily_returns_no_pad, drop_ghost_bars
from open_composer.research.features.security_type import STOCK_TYPES
from open_composer.research.ml_backend.daily_labels import daily_labels

DERIVED = MARKET_DATA / "derived"
FEATURES = DERIVED / "features-daily"
UNIVERSE = DERIVED / "daily-us-stock-universe.parquet"
RETURN_WINDOWS = (1, 5, 21, 63, 126, 252)
RETURNS = tuple(f"return_{n}" for n in RETURN_WINDOWS)
RANKS = tuple(f"rs_rank_{n}" for n in RETURN_WINDOWS)
MARKET = (
    "share_above_sma_50",
    "share_above_sma_200",
    "new_highs_minus_lows_52w",
    "advance_decline",
    "up_25pct_3m",
    "universe_count",
    "spy_vs_sma_50",
    "spy_vs_sma_200",
    "qqq_vs_sma_50",
    "qqq_vs_sma_200",
)
FEATURE_COLUMNS = (
    *RETURNS,
    *RANKS,
    "volatility_21",
    "adr_pct_20",
    "gap",
    "volume_ratio_5",
    "volume_ratio_20",
    "median_dollar_volume_20",
    "days_since_earnings",
    "earnings_gap",
    "earnings_volume_ratio",
    "insider_purchase_count_30d",
    "insider_purchase_shares_30d",
    "insider_purchase_reports_30d",
    "short_interest_shares",
    "days_to_cover",
    "off_exchange_short_ratio",
    "shares_outstanding",
    *MARKET,
)
KEY = ["security_id", "session"]


def read_daily_features(year: int, *, root: Path = FEATURES, **kwargs) -> pd.DataFrame:
    """Read one decision-session year. Pass parquet columns or filters to limit the read."""
    return pd.read_parquet(root / f"{year}.parquet", **kwargs)


def read_daily_labels(year: int, *, root: Path = FEATURES, **kwargs) -> pd.DataFrame:
    return pd.read_parquet(root / "labels" / f"{year}.parquet", **kwargs)


def _price_block(frame, calendar, clocks, year):
    # security_id already segments the default opening-price hygiene breaks
    # and ALL archive switches. Reindex by exchange session, including halts.
    ids = pd.Index(frame.security_id.unique())
    ci = ids.get_indexer(frame.security_id)
    ri = calendar.get_indexer(frame.trade_date)
    shape = (len(calendar), len(ids))

    def wide(field):
        values = np.full(shape, np.nan, dtype="float32")
        values[ri, ci] = frame[field]
        return pd.DataFrame(values).where(values > 0)

    active = frame.session.dt.year.eq(year) & frame.security_type.isin(STOCK_TYPES)
    features = frame.loc[
        active,
        [
            *KEY,
            "symbol",
            "trade_date",
            "listing_date",
            "known_at",
            "security_type_known_at",
            "median_dollar_volume_20",
        ],
    ].reset_index(drop=True)
    if features.empty:
        return features, features[KEY]
    row, col = ri[active], ci[active]
    opens, close, volume = (
        wide(field) for field in ("adjusted_open", "adjusted_close", "raw_volume")
    )
    high, low = wide("high_over_open") * opens, wide("low_over_open") * opens
    returns = daily_returns_no_pad(close)
    for n, name in zip(RETURN_WINDOWS, RETURNS, strict=True):
        uninterrupted = returns.rolling(n, min_periods=n).count().eq(n)
        features[name] = (close / close.shift(n) - 1).where(uninterrupted).to_numpy()[row, col]
    for name, values in (
        ("volatility_21", returns.rolling(21).std()),
        ("adr_pct_20", (100 * (high / low - 1)).rolling(20).mean()),
        ("gap", opens / close.shift(1) - 1),
        *((f"volume_ratio_{n}", volume / volume.shift().rolling(n).mean()) for n in (5, 20)),
    ):
        features[name] = values.to_numpy()[row, col].astype("float32")
    labels = features[KEY].assign(
        **daily_labels(
            opens.to_numpy(),
            high.to_numpy(),
            low.to_numpy(),
            calendar.get_indexer(features.session),
            col,
            clocks,
        )
    )
    return features, labels


def _copy(con, sql, path):
    pending = path.with_suffix(".partial")
    con.execute(
        f"COPY ({sql}) TO {pending.as_posix()!r} "
        "(FORMAT PARQUET, COMPRESSION ZSTD, ROW_GROUP_SIZE 32768)"
    )
    pending.replace(path)


def _join_inputs(con, lo, hi):
    # All snapshot and event clocks use strict pre-open eligibility. Bounds
    # on input scans allow row-group pruning without changing join semantics.
    for source, day, fields in (
        (
            "shares_outstanding",
            "session",
            "security_id, session, shares_outstanding_reported, shares_outstanding_known_at",
        ),
        ("short_volume", "trade_date", "symbol, trade_date, short_volume, total_volume, known_at"),
    ):
        con.execute(f"""
            CREATE OR REPLACE TEMP VIEW {source}_year AS SELECT {fields}
            FROM {source} WHERE {day} >= DATE '{lo}' - INTERVAL 7 DAYS AND {day} < DATE '{hi}'
        """)
    con.execute(f"""
        CREATE OR REPLACE TEMP TABLE buys AS
        SELECT symbol, known_at,
               sum(sum(purchase_count)) OVER w AS buys,
               sum(sum(purchase_shares)) OVER w AS shares,
               sum(count(*)) OVER w AS days
        FROM insider_daily
        WHERE purchase_count > 0 AND known_at >= DATE '{lo}' - INTERVAL 32 DAYS
          AND known_at < DATE '{hi}' + INTERVAL 1 DAY
        GROUP BY symbol, known_at WINDOW w AS (PARTITION BY symbol ORDER BY known_at)
    """)
    rank = ", ".join(
        f"CASE WHEN p.{f} IS NOT NULL THEN "
        f"(rank() OVER (w ORDER BY p.{f} NULLS LAST) - 1) / "
        f"greatest(count(p.{f}) OVER w - 1, 1) END AS {r}"
        for f, r in zip(RETURNS, RANKS, strict=True)
    )
    numeric = ", ".join(f"{name}::FLOAT AS {name}" for name in FEATURE_COLUMNS)
    return f"""
        WITH decisions AS (
            SELECT *, make_timestamptz(year(session), month(session), day(session),
                9, 30, 0, 'America/New_York') AS decision_at,
                greatest(session::DATE - INTERVAL 30 DAYS, listing_date)
                    AT TIME ZONE 'America/New_York' AS cluster_start
            FROM price_features
            WHERE session >= DATE '{lo}' AND session < DATE '{hi}'
              AND known_at < decision_at AND security_type_known_at < decision_at
        ), joined AS (
            SELECT p.* EXCLUDE (known_at, security_type_known_at, cluster_start, listing_date),
                   greatest(max(greatest(p.known_at, p.security_type_known_at)) OVER w,
                       CASE WHEN earned THEN e.accepted_at END,
                       CASE WHEN gapped THEN g.gap_available_at END,
                       CASE WHEN has_volume THEN v.volume_available_at END,
                       CASE WHEN b.known_at >= p.cluster_start THEN b.known_at END,
                       CASE WHEN has_interest THEN i.known_at END,
                       s.known_at, o.shares_outstanding_known_at, m.known_at) AS known_at,
                   {rank},
                   CASE WHEN earned THEN date_diff('day', e.acceptance_date, p.session) END
                       AS days_since_earnings,
                   CASE WHEN gapped THEN g.opening_gap END AS earnings_gap,
                   CASE WHEN has_volume THEN v.volume_ratio_20d END AS earnings_volume_ratio,
                   coalesce(b.buys, 0) - coalesce(prior.buys, 0) AS insider_purchase_count_30d,
                   coalesce(b.shares, 0) - coalesce(prior.shares, 0) AS insider_purchase_shares_30d,
                   coalesce(b.days, 0) - coalesce(prior.days, 0) AS insider_purchase_reports_30d,
                   CASE WHEN has_interest THEN i.short_interest_shares END AS short_interest_shares,
                   CASE WHEN has_interest AND i.average_daily_volume > 0 THEN i.days_to_cover END
                       AS days_to_cover,
                   s.short_volume / nullif(s.total_volume, 0) AS off_exchange_short_ratio,
                   o.shares_outstanding_reported AS shares_outstanding,
                   {", ".join("m." + c for c in MARKET)}
            FROM decisions p
            ASOF LEFT JOIN (
                SELECT * FROM release_clock
                WHERE accepted_at BETWEEN TIMESTAMPTZ '{lo}' - INTERVAL 120 DAYS
                                   AND TIMESTAMPTZ '{hi}' + INTERVAL 1 DAY
            ) e
                ON p.symbol = e.symbol AND p.decision_at > e.accepted_at
            ASOF LEFT JOIN (
                SELECT * FROM gap_clock
                WHERE gap_available_at BETWEEN TIMESTAMPTZ '{lo}' - INTERVAL 120 DAYS
                                   AND TIMESTAMPTZ '{hi}' + INTERVAL 1 DAY
            ) g
                ON p.symbol = g.symbol AND p.decision_at > g.gap_available_at
            ASOF LEFT JOIN (
                SELECT * FROM volume_clock
                WHERE volume_available_at BETWEEN TIMESTAMPTZ '{lo}' - INTERVAL 120 DAYS
                                   AND TIMESTAMPTZ '{hi}' + INTERVAL 1 DAY
            ) v
                ON p.symbol = v.symbol AND p.decision_at > v.volume_available_at
            ASOF LEFT JOIN buys b ON p.symbol = b.symbol AND p.decision_at > b.known_at
            ASOF LEFT JOIN buys prior
                ON p.symbol = prior.symbol AND p.cluster_start > prior.known_at
            ASOF LEFT JOIN (
                SELECT * FROM official_interest
                WHERE known_at BETWEEN TIMESTAMPTZ '{lo}' - INTERVAL 90 DAYS
                                   AND TIMESTAMPTZ '{hi}' + INTERVAL 1 DAY
            ) i
                ON p.symbol = i.symbol AND p.decision_at > i.known_at
            LEFT JOIN short_volume_year s
                ON p.symbol = s.symbol AND p.trade_date = s.trade_date
                AND s.known_at < p.decision_at
            LEFT JOIN shares_outstanding_year o
                ON p.security_id = o.security_id AND p.session = o.session
                AND o.shares_outstanding_known_at < p.decision_at
            ASOF LEFT JOIN market_state m ON p.decision_at > m.known_at
            CROSS JOIN LATERAL (SELECT
                e.acceptance_date >= greatest(p.listing_date, p.session - INTERVAL 120 DAYS)
                    AS earned,
                g.session_date >= greatest(p.listing_date, p.session - INTERVAL 120 DAYS)
                    AS gapped,
                v.session_date >= greatest(p.listing_date, p.session - INTERVAL 120 DAYS)
                    AS has_volume,
                i.settlement_date >= p.listing_date
                AND i.known_at >= p.decision_at - INTERVAL 90 DAYS
                    AS has_interest
            )
            WINDOW w AS (PARTITION BY p.session)
        )
        SELECT security_id, symbol, session, trade_date, decision_at, known_at, {numeric}
        FROM joined ORDER BY session, security_id
    """


def _register_inputs(con, derived):
    for source in (
        "earnings_releases",
        "earnings_gaps",
        "insider_daily",
        "short_interest",
        "short_volume",
        "shares_outstanding",
        "market_state",
    ):
        path = (derived / f"{source}.parquet").as_posix()
        con.execute(f"CREATE VIEW {source} AS SELECT * FROM read_parquet({path!r})")
    for name, source, clock, condition in (
        ("release_clock", "earnings_releases", "accepted_at", "true"),
        ("gap_clock", "earnings_gaps", "gap_available_at", "opening_gap IS NOT NULL"),
        ("volume_clock", "earnings_gaps", "volume_available_at", "volume_ratio_20d IS NOT NULL"),
    ):
        con.execute(f"""
            CREATE VIEW {name} AS SELECT * FROM {source} WHERE symbol IS NOT NULL AND {condition}
            QUALIFY row_number() OVER (PARTITION BY symbol, {clock} ORDER BY accession DESC) = 1
        """)
    con.execute("""
        CREATE VIEW official_interest AS SELECT * FROM short_interest
        WHERE known_at IS NOT NULL AND publication_date_source = 'finra_official_schedule_page'
    """)


def build_daily_features(years: range, *, derived: Path = DERIVED) -> None:
    """Materialize feature/label partitions using one active decision year."""
    root = derived / FEATURES.name
    (root / "labels").mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=derived) as temp, _connect("600MB") as con:
        stage = Path(temp)
        con.execute("SET temp_directory = ?", [str(stage / "duckdb")])
        universe_path = (derived / UNIVERSE.name).as_posix()
        con.execute(
            f"CREATE VIEW universe AS SELECT * FROM read_parquet({universe_path!r}) WHERE is_member"
        )
        _register_inputs(con, derived)
        first, last = con.sql("SELECT min(trade_date), max(trade_date) FROM universe").fetchone()
        for year in years:
            started = perf_counter()
            lo, hi = pd.Timestamp(year, 1, 1), pd.Timestamp(year + 1, 1, 1)
            back = max(first, lo - pd.Timedelta(days=400))
            forward = hi + pd.Timedelta(days=35)
            calendar = pd.DatetimeIndex(us_equity_session_dates(back.date(), forward.date()))
            clocks = (calendar + pd.Timedelta(days=1)).tz_localize(NEW_YORK).tz_convert("UTC")
            bars_paths = []
            bar_end = min(forward, last)
            start_half = back.year * 2 + (back.month > 6)
            end_half = bar_end.year * 2 + (bar_end.month > 6)
            for half in range(start_half, end_half + 1):
                begin = pd.Timestamp(half // 2, 1 + 6 * (half % 2), 1)
                end = begin + pd.DateOffset(months=6) - pd.Timedelta(days=1)
                # Stage six months at a time, and reuse overlap in the next build year.
                path = stage / f"bars-{begin.date()}.parquet"
                bars_paths.append(path.as_posix())
                if not path.exists():
                    bars = drop_ghost_bars(
                        load_sip_daily_panel(
                            str(begin.date()),
                            f"{end.date()}T23:59:59Z",
                        )
                    )
                    bars["high_over_open"] = (bars.high / bars.open).astype("float32")
                    bars["low_over_open"] = (bars.low / bars.open).astype("float32")
                    bars[
                        [
                            "symbol",
                            "trade_date",
                            "source_version",
                            "high_over_open",
                            "low_over_open",
                        ]
                    ].to_parquet(path, index=False)
                    del bars
            con.execute(
                f"""
                CREATE OR REPLACE TEMP TABLE price AS
                SELECT u.security_id, u.symbol, u.trade_date, u.session, u.listing_date, u.known_at,
                       u.security_type, u.security_type_known_at, u.adjusted_open, u.adjusted_close,
                       u.raw_volume, u.median_dollar_volume_20, b.high_over_open, b.low_over_open
                FROM universe u LEFT JOIN read_parquet({bars_paths!r}) b
                     USING (symbol, trade_date, source_version)
                WHERE u.trade_date BETWEEN ? AND ?
                  AND u.security_id IN (
                      SELECT security_id FROM universe WHERE session >= ? AND session < ?
                        AND security_type IN {STOCK_TYPES!r}
                  )
                ORDER BY security_id, trade_date
            """,
                [back, min(last, forward), lo, hi],
            )
            ids = con.sql("SELECT DISTINCT security_id FROM price ORDER BY 1").fetchnumpy()[
                "security_id"
            ]
            feature_paths, label_paths = [], []
            for offset in range(0, len(ids), 256):
                block = ids[offset : offset + 256]
                frame = con.execute(
                    "SELECT * FROM price WHERE security_id BETWEEN ? AND ?",
                    [block[0], block[-1]],
                ).df()
                f, labels = _price_block(frame, calendar, clocks, year)
                if len(f):
                    for name, data, paths in (
                        ("feature", f, feature_paths),
                        ("label", labels, label_paths),
                    ):
                        path = stage / f"{name}-{year}-{offset}.parquet"
                        data.to_parquet(path, index=False)
                        paths.append(path.as_posix())
            con.execute("DROP TABLE price")
            con.execute(f"""
                CREATE OR REPLACE TEMP VIEW price_features AS
                SELECT * FROM read_parquet({feature_paths!r})
            """)
            quarters = []
            for start in pd.date_range(lo, hi, freq="QS", inclusive="left"):
                stop = start + pd.DateOffset(months=3)
                path = stage / f"joined-{start.date()}.parquet"
                _copy(con, _join_inputs(con, start.date(), stop.date()), path)
                quarters.append(path.as_posix())
            _copy(
                con,
                f"SELECT * FROM read_parquet({quarters!r}) ORDER BY session, security_id",
                root / f"{year}.parquet",
            )
            _copy(
                con,
                f"SELECT * FROM read_parquet({label_paths!r}) ORDER BY session, security_id",
                root / "labels" / f"{year}.parquet",
            )
            for path in feature_paths + label_paths + quarters:
                Path(path).unlink()
            print(f"{year}: features and labels in {perf_counter() - started:.1f}s", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--first-year", type=int, default=2016)
    parser.add_argument("--last-year", type=int, default=2026)
    args = parser.parse_args()
    build_daily_features(range(args.first_year, args.last_year + 1))
