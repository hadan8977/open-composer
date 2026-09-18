"""Find backfilled "delisted" symbols that are really aliases of a symbol we
already hold (ticker renames), so the broad universe does not count one
company twice.

Alpaca serves a renamed company's full history under its *current* symbol
(ELV back to 2016) and also serves the *old* symbol up to the rename (ANTM to
2022-06-27). The backfill (``scripts/backfill_delisted_daily_bars.py``) asked
for every symbol not in the archive, so it picked up the old symbols. Two
series of the same company have identical adjusted daily returns on every
non-flat day and a constant volume ratio; unrelated companies never do for
20+ days. (Matching on raw adjusted close fails whenever the survivor paid a
dividend or split after the rename, because the two series then differ by a
constant factor -- ANTM vs ELV was missed that way on the first pass.)

Outputs ``data/sip-delisted/broad/_alias_exclusions.parquet`` with one row per
(backfill symbol, matched symbol):
  drop_all     True when >= 80% of the backfill symbol's days match a
               survivor (or a longer backfill series): the whole series is a
               duplicate and is dropped.
  drop_from/to otherwise only the matched span is dropped (the rest is a
               different listing episode of a reused ticker).
``scripts/repartition_delisted_by_year.py`` applies the table.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import duckdb
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
BACKFILL_GLOB = str(ROOT / "data" / "sip-delisted" / "by_year" / "*" / "*.parquet")
ARCHIVE_GLOB = str(ROOT / "data" / "sip" / "daily" / "*" / "*.parquet")
OUT = ROOT / "data" / "sip-delisted" / "broad" / "_alias_exclusions.parquet"
MIN_MATCHED_DAYS = 20
FULL_ALIAS_SHARE = 0.8
MIN_ABS_RETURN = 0.0005
MAX_VOL_RATIO_SD = 0.05
MIN_VOLUME_A = 5000
MIN_VOLUME_B = 1000
MIN_YEAR_DAYS = 3


def _year_dirs(root: Path) -> list[int]:
    return sorted(int(p.name) for p in root.iterdir() if p.is_dir() and p.name.isdigit())


def detect(
    *, memory_limit: str, raw_glob: str | None, years: list[int] | None = None
) -> pd.DataFrame:
    """Two match keys, each aggregated per (pair, year) straight out of the
    join (no match rows are kept), then validated:

    * key A: (date, split-adjusted volume) exactly equal, volume >= 5,000 --
      robust to any price rounding, catches every rename without a later split;
    * key B: (date, log return to 3 dp, log volume ratio vs previous day to
      3 dp) equal on non-flat days with volume >= 1,000 on both days -- both
      quantities are invariant to the constant price/volume factors a later
      dividend or split introduces, and the compound key is selective enough
      (~600 x 6,000 buckets) that coincidences are rare.

    Raw adjusted closes are never compared: the survivor's adjusted series is
    off by a constant factor once it pays a dividend after the rename (ANTM vs
    ELV). A (date, 3-dp return) key alone produced ~1e8 coincidental rows and
    ran the 1 GB DuckDB budget out of memory; hence the compound key and the
    per-year aggregation with a small per-year floor.
    """
    con = duckdb.connect()
    con.execute(f"SET memory_limit='{memory_limit}'")
    con.execute("SET threads=2")
    con.execute("SET preserve_insertion_order=false")
    con.execute(f"SET temp_directory='{ROOT / 'data' / '_duckdb_tmp'}'")
    backfill_glob: str | list[str] = BACKFILL_GLOB
    if raw_glob:
        parts = [part.strip() for part in raw_glob.split(",") if part.strip()]
        backfill_glob = parts if len(parts) > 1 else parts[0]
    keyed = """
        SELECT symbol, timestamp, volume,
               round(ln(close / prev_close), 3) AS r3,
               round(ln(volume / prev_volume), 3) AS vr3,
               abs(ln(close / prev_close)) >= {min_abs_return} AS moved,
               prev_volume >= {min_volume_b} AND volume >= {min_volume_b} AS liquid_pair
        FROM (
            SELECT symbol, timestamp, volume, close,
                   lag(close) OVER w AS prev_close,
                   lag(volume) OVER w AS prev_volume
            FROM read_parquet({glob!r})
            WHERE close > 0 AND volume > 0 AND year(timestamp) = {year}
            WINDOW w AS (PARTITION BY symbol ORDER BY timestamp)
        ) WHERE prev_close IS NOT NULL AND prev_volume > 0
    """
    con.execute(
        """
        CREATE TEMP TABLE pair_year (
            symbol VARCHAR, matched_symbol VARCHAR, kind VARCHAR, key VARCHAR, year INTEGER,
            n BIGINT, first_ts DATE, last_ts DATE, sum_lr DOUBLE, sumsq_lr DOUBLE
        )
        """
    )
    con.execute(
        "CREATE TEMP TABLE bday_parts (symbol VARCHAR, eligible_days BIGINT, "
        "first_day DATE, last_day DATE)"
    )
    key_a = """
        INSERT INTO pair_year
        SELECT b.symbol, a.symbol, {kind!r}, 'A', {year}, count(*),
               min(b.timestamp)::DATE, max(b.timestamp)::DATE, 0.0, 0.0
        FROM bf_y b JOIN {other} a
          ON a.timestamp = b.timestamp AND a.volume = b.volume {extra}
        WHERE b.volume >= {min_volume_a}
        GROUP BY 1, 2 HAVING count(*) >= {min_year_days}
    """
    key_b = """
        INSERT INTO pair_year
        SELECT b.symbol, a.symbol, {kind!r}, 'B', {year}, count(*),
               min(b.timestamp)::DATE, max(b.timestamp)::DATE,
               sum(ln(b.volume / a.volume)), sum(ln(b.volume / a.volume) ^ 2)
        FROM bf_y b JOIN {other} a
          ON a.timestamp = b.timestamp AND a.r3 = b.r3 AND a.vr3 = b.vr3 {extra}
        WHERE b.moved AND a.moved AND b.liquid_pair AND a.liquid_pair
        GROUP BY 1, 2 HAVING count(*) >= {min_year_days}
    """
    for year in years or _year_dirs(ROOT / "data" / "sip" / "daily"):
        started = time.time()
        con.execute("DROP TABLE IF EXISTS bf_y")
        con.execute("DROP TABLE IF EXISTS ar_y")
        con.execute(
            "CREATE TEMP TABLE bf_y AS "
            + keyed.format(
                glob=backfill_glob,
                year=year,
                min_abs_return=MIN_ABS_RETURN,
                min_volume_b=MIN_VOLUME_B,
            )
        )
        if con.execute("SELECT count(*) FROM bf_y").fetchone()[0] == 0:
            continue
        con.execute(
            "CREATE TEMP TABLE ar_y AS "
            + keyed.format(
                glob=str(ROOT / "data" / "sip" / "daily" / str(year) / "*.parquet"),
                year=year,
                min_abs_return=MIN_ABS_RETURN,
                min_volume_b=MIN_VOLUME_B,
            )
        )
        con.execute(
            "INSERT INTO bday_parts SELECT symbol, count(*), min(timestamp)::DATE, "
            "max(timestamp)::DATE FROM bf_y WHERE moved GROUP BY 1"
        )
        for template in (key_a, key_b):
            con.execute(
                template.format(
                    kind="archive",
                    other="ar_y",
                    extra="",
                    year=year,
                    min_volume_a=MIN_VOLUME_A,
                    min_year_days=MIN_YEAR_DAYS,
                )
            )
            con.execute(
                template.format(
                    kind="backfill",
                    other="bf_y",
                    extra="AND a.symbol <> b.symbol",
                    year=year,
                    min_volume_a=MIN_VOLUME_A,
                    min_year_days=MIN_YEAR_DAYS,
                )
            )
        rows = con.execute("SELECT count(*) FROM pair_year WHERE year = ?", [year]).fetchone()[0]
        print(
            f"{year}: pair-year rows so far this year {rows}, {time.time() - started:.1f}s",
            flush=True,
        )
    con.execute(
        """
        CREATE TEMP TABLE bdays AS
        SELECT symbol, sum(eligible_days) AS eligible_days,
               min(first_day) AS first_day, max(last_day) AS last_day
        FROM bday_parts GROUP BY 1
        """
    )
    frame = con.execute(
        f"""
        WITH by_key AS (
            SELECT symbol, matched_symbol, kind, key, sum(n) AS n,
                   min(first_ts) AS first_ts, max(last_ts) AS last_ts,
                   sum(sum_lr) AS sum_lr, sum(sumsq_lr) AS sumsq_lr
            FROM pair_year GROUP BY 1, 2, 3, 4
        ),
        pairs AS (
            SELECT symbol, matched_symbol, kind,
                   max(n) AS matched_days,
                   min(first_ts) AS drop_from, max(last_ts) AS drop_to,
                   -- volume-ratio dispersion from key B rows (key A rows are exact)
                   coalesce(max(CASE WHEN key = 'B' AND n > 1 THEN
                       sqrt(greatest(sumsq_lr / n - (sum_lr / n) ^ 2, 0)) END), 0) AS vol_ratio_sd,
                   coalesce(max(CASE WHEN key = 'B' THEN sum_lr / n END), 0) AS vol_ratio_log,
                   string_agg(key, '+' ORDER BY key) AS keys
            FROM by_key GROUP BY 1, 2, 3 HAVING max(n) >= {MIN_MATCHED_DAYS}
        )
        SELECT m.symbol, m.matched_symbol, m.kind, m.keys, m.matched_days, m.drop_from, m.drop_to,
               m.vol_ratio_sd, m.vol_ratio_log,
               d.eligible_days AS backfill_days, d.first_day, d.last_day,
               round(least(m.matched_days, d.eligible_days) * 1.0 / d.eligible_days, 3)
                   AS match_share
        FROM pairs m
        JOIN bdays d ON d.symbol = m.symbol
        LEFT JOIN bdays o ON o.symbol = m.matched_symbol AND m.kind = 'backfill'
        WHERE m.kind = 'archive'
           -- backfill vs backfill (renamed, then delisted under the new symbol):
           -- the series that ends later carries the full history, so only the
           -- earlier-ending one is the alias.
           OR d.last_day < o.last_day
           OR (d.last_day = o.last_day AND d.eligible_days < o.eligible_days)
           OR (d.last_day = o.last_day AND d.eligible_days = o.eligible_days
               AND m.symbol > m.matched_symbol)
        ORDER BY match_share DESC, matched_days DESC
        """
    ).fetchdf()
    frame = frame.loc[frame["vol_ratio_sd"] <= MAX_VOL_RATIO_SD].reset_index(drop=True)
    frame["drop_all"] = frame["match_share"] >= FULL_ALIAS_SHARE
    return frame


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--memory-limit", default="1000MB")
    parser.add_argument("--years", type=int, nargs="*", default=None, help="smoke-test subset")
    parser.add_argument("--out", type=Path, default=OUT)
    parser.add_argument(
        "--raw-glob",
        default=None,
        help=(
            "comma-separated parquet globs to scan instead of data/sip-delisted/by_year "
            "(use the raw batches so already-excluded aliases are re-detected)"
        ),
    )
    args = parser.parse_args()
    started = time.time()
    frame = detect(memory_limit=args.memory_limit, raw_glob=args.raw_glob, years=args.years)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(args.out, index=False)
    summary = {
        "pairs": int(len(frame)),
        "symbols_dropped_entirely": int(frame.loc[frame["drop_all"], "symbol"].nunique()),
        "symbols_with_partial_span_dropped": int(frame.loc[~frame["drop_all"], "symbol"].nunique()),
        "by_kind": frame.groupby("kind")["symbol"].nunique().to_dict(),
        "elapsed_seconds": round(time.time() - started, 1),
        "out": str(args.out),
    }
    print(json.dumps(summary, indent=1))
    print(frame.head(12).to_string())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
