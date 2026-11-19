"""Prove daily SIP archive handoffs using quotes dated before the switch."""

import numpy as np
import pandas as pd

from open_composer.adapters.data.sip_parquet import ALL_VERSIONS, _local_sources
from open_composer.research.features.price_hygiene import ghost_bar_sql_predicate
from open_composer.research.features.security_type import TYPED_MEMBERS


def archive_handoffs(con, actions):
    con.execute("""
        CREATE TEMP TABLE switches AS
        SELECT s.*, c.session AS next_session FROM (
            SELECT symbol, trade_date, source_version, adjusted_open, adjusted_close,
                   lag(trade_date) OVER w AS previous_date,
                   lag(source_version) OVER w AS previous_source,
                   lag(adjusted_close) OVER w AS previous_close
            FROM joined
            WINDOW w AS (PARTITION BY symbol ORDER BY trade_date)
        ) s JOIN calendar c ON c.trade_date = s.previous_date
        WHERE source_version <> previous_source
    """)
    first, last = con.sql("""
        SELECT coalesce(min(previous_date) FILTER (WHERE trade_date = next_session), max(trade_date)),
               max(trade_date) FROM switches
    """).fetchone()
    if last is None:
        return pd.DataFrame(columns=["symbol", "trade_date", "factor", "status"]), {}, set()

    replacement = ALL_VERSIONS[1]
    con.execute(f"""
        CREATE TEMP TABLE renames AS
        SELECT DISTINCT a.symbol AS old_symbol, a.new_symbol AS symbol,
               a.ex_date AS trade_date, p.trade_date AS previous_date,
               p.adjusted_close AS previous_close, n.adjusted_open
        FROM read_parquet(?) a
        JOIN joined p ON p.symbol = a.symbol
        JOIN calendar c ON p.trade_date = c.trade_date AND c.session = a.ex_date
        JOIN joined n ON n.symbol = a.new_symbol AND n.trade_date = a.ex_date
        WHERE a.kind = 'name_changes' AND a.symbol <> a.new_symbol
          AND a.old_cusip = a.new_cusip AND CAST(a.process_date AS DATE) <= a.ex_date
          AND p.source_version = '{replacement}' AND n.source_version = '{replacement}'
          AND NOT EXISTS (
              SELECT 1 FROM joined j WHERE j.symbol = a.symbol AND j.trade_date = a.ex_date
          )
    """, [str(actions)])
    con.execute("""
        CREATE TEMP VIEW members AS
        SELECT symbol, symbol AS issuer_symbol, trade_date FROM switches
        UNION SELECT symbol, symbol, previous_date FROM switches
        UNION SELECT old_symbol, old_symbol, previous_date FROM renames
    """)
    con.execute(f"CREATE TEMP TABLE identities AS {TYPED_MEMBERS}")
    con.execute("DROP VIEW members")
    start = pd.Timestamp(first, tz="UTC") - pd.Timedelta(days=14)
    end = pd.Timestamp(last, tz="UTC")
    con.execute("""
        CREATE TEMP TABLE tape (
            symbol VARCHAR, trade_date TIMESTAMP, open DOUBLE, close DOUBLE,
            volume DOUBLE, source_version VARCHAR
        )
    """)
    for version, paths in _local_sources("daily", "all", start, end):
        if not paths:
            continue
        con.read_parquet([p.as_posix() for p in paths], union_by_name=True).create_view("shards", replace=True)
        ghost = ghost_bar_sql_predicate(con.table("shards").columns)
        con.execute(f"""
            INSERT INTO tape
            SELECT *, '{version}' FROM (
                SELECT DISTINCT symbol, CAST(timezone('America/New_York', timestamp) AS DATE) AS trade_date,
                       open, close, volume
                FROM shards
                WHERE timestamp >= ? AND timestamp <= ? AND open > 0 AND close > 0
                  AND volume > 0 AND NOT {ghost}
                  AND (timestamp >= ? OR symbol IN (SELECT symbol FROM renames UNION SELECT old_symbol FROM renames))
            )
            QUALIFY count(*) OVER (PARTITION BY symbol, trade_date) = 1
        """, [pd.Timestamp(start.year, 1, 1, tz="UTC"), end + pd.Timedelta(days=1), start])
    con.execute("DROP VIEW shards")

    overlap = con.sql("""
        SELECT s.symbol, s.trade_date, a.trade_date AS overlap_date,
               a.close AS old_close, a.close / b.close AS factor,
               a.open / b.open AS open_factor, a.volume / b.volume AS share_ratio
        FROM switches s
        JOIN tape a ON a.symbol = s.symbol AND a.source_version = s.previous_source
           AND a.trade_date BETWEEN s.previous_date - INTERVAL 14 DAY AND s.previous_date
        JOIN tape b ON b.symbol = s.symbol AND b.trade_date = a.trade_date
           AND b.source_version = s.source_version
        WHERE s.trade_date = s.next_session
        QUALIFY row_number() OVER (PARTITION BY s.symbol, s.trade_date ORDER BY a.trade_date DESC) <= 5
    """).df()
    overlap = overlap.sort_values("overlap_date")
    terminal = overlap.groupby(["symbol", "trade_date"]).factor.transform("last")
    tolerance = np.maximum(0.0005, 0.02 / overlap.old_close)
    overlap["matches"] = (
        ((overlap.open_factor / overlap.factor - 1).abs() <= tolerance)
        & ((overlap.factor / terminal - 1).abs() <= tolerance)
        & (((overlap.share_ratio - 1).abs() <= 0.01)
           | ((overlap.share_ratio * overlap.factor - 1).abs() <= 0.01))
    )
    common = overlap.groupby(["symbol", "trade_date"])
    evidence = common.agg(overlap_days=("matches", "size"), matches=("matches", "sum"), terminal=("matches", "last"))
    evidence["factor"] = overlap.loc[overlap.matches].groupby(["symbol", "trade_date"]).factor.median()
    switches = con.execute("""
        SELECT s.*, p.issuer_cik AS old_cik, n.issuer_cik AS new_cik,
               p.security_type AS old_type, n.security_type AS new_type,
               EXISTS (SELECT 1 FROM read_parquet(?) a
                       WHERE a.symbol = s.symbol AND a.ex_date > s.previous_date AND a.ex_date <= s.trade_date
                         AND least(CAST(a.process_date AS DATE), CAST(a.record_date AS DATE)) <= s.trade_date
                         AND a.kind IN ('forward_splits', 'reverse_splits', 'stock_dividends', 'name_changes'))
                   AS action
        FROM switches s JOIN identities p ON p.symbol = s.symbol AND p.trade_date = s.previous_date
        JOIN identities n ON n.symbol = s.symbol AND n.trade_date = s.trade_date
    """, [str(actions)]).df().join(evidence, on=["symbol", "trade_date"])
    missing_identity = switches.old_cik.isna() | switches.new_cik.isna() | switches.old_type.eq("unknown") | switches.new_type.eq("unknown")
    different_identity = (switches.old_cik != switches.new_cik) | switches.old_type.ne(switches.new_type)
    switches["status"] = np.select([
        switches.trade_date.ne(switches.next_session), missing_identity,
        different_identity.fillna(False).to_numpy(dtype=bool), switches.action,
        switches.overlap_days.fillna(0).lt(2), switches.matches.lt(2) | ~switches.terminal.eq(True),
        ~((switches.adjusted_open * switches.factor / switches.previous_close).between(0.5, 2, inclusive="neither")
          & (switches.adjusted_close * switches.factor / switches.previous_close).between(0.5, 2, inclusive="neither")),
    ], ["quote gap", "missing issuer or type", "issuer or type changed", "corporate action",
        "insufficient overlap", "overlap disagreement", "price jump"], default="linked")
    switches.loc[switches.status.ne("linked"), "factor"] = np.nan

    # A dated same-CUSIP change identifies the old issuer even if SEC ticker
    # history still points the destination ticker at a different company.
    duplicates = con.sql(f"""
        SELECT r.old_symbol, r.symbol, r.trade_date, r.previous_date, a.trade_date AS alias_date
        FROM renames r
        JOIN identities i ON i.symbol = r.old_symbol AND i.trade_date = r.previous_date
        JOIN tape a ON a.symbol = r.old_symbol AND a.trade_date < r.trade_date
        JOIN tape b ON b.symbol = r.symbol AND b.trade_date = a.trade_date
           AND a.source_version = b.source_version AND a.open = b.open AND a.close = b.close AND a.volume = b.volume
        JOIN joined p ON p.symbol = r.old_symbol AND p.trade_date = a.trade_date
        WHERE a.source_version = '{replacement}' AND i.issuer_cik IS NOT NULL AND i.security_type <> 'unknown'
          AND r.adjusted_open / r.previous_close > 0.5 AND r.adjusted_open / r.previous_close < 2
    """).df()
    renames, aliases = {}, set()
    for (old, new, day, previous), rows in duplicates.groupby(
        ["old_symbol", "symbol", "trade_date", "previous_date"]
    ):
        if previous in set(rows.alias_date) and rows.alias_date.between(previous - pd.Timedelta(days=14), previous).sum() >= 2:
            renames[new] = (old, day)
            aliases.update((new, d, replacement) for d in rows.alias_date)
    for table in ("tape", "identities", "switches", "renames"):
        con.execute(f"DROP TABLE {table}")
    return switches, renames, aliases
