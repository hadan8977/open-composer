"""Build the SEC shares/float panel with python -m scripts.build_shares_outstanding."""

import argparse
import json
from datetime import datetime
from functools import cache
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZipFile

import pandas as pd
import pyarrow.parquet as pq

from open_composer.adapters.events.fetcher import sec_submission_tables
from open_composer.market_sessions import NEW_YORK, next_us_equity_session, us_equity_session_close
from open_composer.research.features.daily_actions import ACTIONS, DERIVED
from open_composer.research.features.panel import _connect
from open_composer.research.features.shares_outstanding import FILENAME
from scripts.build_sec_sic_map import HISTORY_PATH, SUBMISSIONS_DIR, member_name
from scripts.build_sec_xbrl_fundamentals import COMPANYFACTS_ZIP_URL, RAW_ROOT, SecClient

COMPANYFACTS = RAW_ROOT / "companyfacts-shares-current.zip"
UNIVERSE = DERIVED / "daily-us-stock-universe.parquet"
ANNUAL_FORMS = {"10-K", "10-KT", "20-F", "40-F"}
CONCEPTS = {
    "shares_outstanding": ("EntityCommonStockSharesOutstanding", "shares"),
    "public_float": ("EntityPublicFloat", "USD"),
}


@cache
def session_clock(day):
    return us_equity_session_close(day), next_us_equity_session(day)


def filing_facts(path, start):
    with ZipFile(path) as facts, ZipFile(SUBMISSIONS_DIR / "submissions-current.zip") as submissions:
        def submission(name):
            return json.loads(submissions.read(name))

        for cik in sorted(pd.read_parquet(HISTORY_PATH, columns=["cik"]).cik.unique()):
            name = member_name(cik)
            if name not in facts.NameToInfo or name not in submissions.NameToInfo:
                continue
            payload = json.loads(facts.read(name)).get("facts") or {}
            rows = [
                (kind, row) for kind, (tag, unit) in CONCEPTS.items()
                for ns in (("dei",) if unit == "shares" else ("dei", "us-gaap"))
                for row in payload.get(ns, {}).get(tag, {}).get("units", {}).get(unit, [])
                if (row.get("filed") or "") >= start and (row.get("val") or 0) > 0
                and row.get("end") and row.get("accn") and "start" not in row
                and (unit == "shares" or (row.get("form") or "").removesuffix("/A") in ANNUAL_FORMS)
            ]
            if not rows:
                continue
            clocks = {
                accession: stamp
                for table in sec_submission_tables(submission(name)["filings"], start=start, read_page=submission)
                for accession, stamp in zip(table["accessionNumber"], table["acceptanceDateTime"], strict=True)
                if stamp
            }
            for kind, row in rows:
                accession = row["accn"]
                if accession not in clocks:
                    continue
                accepted = datetime.fromisoformat(clocks[accession])
                local = accepted.astimezone(NEW_YORK)
                day = local.date()
                close, next_day = session_clock(day)
                release = day if close and local.time() < close else next_day
                if row["end"] <= day.isoformat():
                    yield cik, kind, row["end"], row["val"], accession, accepted, day, release


def prepare(con, path):
    start = con.sql("SELECT min(trade_date)::DATE::VARCHAR FROM universe").fetchone()[0]
    facts = pd.DataFrame.from_records(filing_facts(path, start), columns=[
        "cik", "kind", "as_of_date", "value", "accession", "known_at", "accepted_day", "release_session",
    ])
    con.register("facts", facts)
    history = HISTORY_PATH.as_posix()
    # Only prior observations of a link count. The archive's interval ends
    # and today's SEC ticker list would introduce future identity information.
    for key, counterpart in (("symbol", "cik"), ("cik", "symbol")):
        con.execute(f"""
            CREATE TEMP TABLE by_{key} AS
            SELECT {key}, first_date::DATE AS first_date,
                   CASE WHEN min({counterpart}) = max({counterpart}) THEN min({counterpart}) END AS {counterpart}
            FROM read_parquet({history!r}) GROUP BY 1, 2
        """)
    con.execute(f"""
        CREATE TEMP TABLE splits AS
        WITH mapped AS (
            SELECT DISTINCT l.cik, a.ex_date::DATE AS ex_date, a.new_rate / a.old_rate AS ratio
            FROM read_parquet({(DERIVED / ACTIONS).as_posix()!r}) a
            ASOF JOIN by_symbol l ON a.symbol = l.symbol AND a.ex_date > l.first_date
            WHERE a.kind IN ('reverse_splits', 'forward_splits') AND l.cik IS NOT NULL
        )
        SELECT cik, ex_date, product(ratio) OVER (PARTITION BY cik ORDER BY ex_date) AS factor
        FROM mapped QUALIFY row_number() OVER (PARTITION BY cik, ex_date ORDER BY ratio) = 1
    """)
    con.execute("""
        CREATE TEMP TABLE reports AS
        WITH unambiguous AS (
            SELECT DISTINCT * REPLACE (as_of_date::DATE AS as_of_date) FROM facts
            WINDOW w AS (PARTITION BY cik, kind, accession, as_of_date)
            QUALIFY min(value) OVER w = max(value) OVER w
        ), dated AS (
            SELECT f.*, i.symbol, i.first_date AS link_date
            FROM unambiguous f
            ASOF JOIN by_cik i ON f.cik = i.cik AND f.accepted_day > i.first_date
            ASOF JOIN by_symbol l ON i.symbol = l.symbol AND f.accepted_day > l.first_date
            WHERE f.cik = l.cik
            QUALIFY row_number() OVER (
                PARTITION BY f.cik, i.first_date, kind, known_at ORDER BY as_of_date DESC, accession DESC
            ) = 1
        ), latest AS (
            SELECT * FROM dated QUALIFY as_of_date = max(as_of_date) OVER (
                PARTITION BY cik, link_date, kind ORDER BY known_at
            )
        ), prices AS (
            SELECT f.cik, f.accession, p.close AS raw_close
            FROM latest f
            ASOF JOIN by_cik i ON f.cik = i.cik AND f.as_of_date > i.first_date
            ASOF JOIN by_symbol l ON i.symbol = l.symbol AND f.as_of_date > l.first_date
            JOIN universe p ON p.symbol = i.symbol AND p.trade_date = f.as_of_date
            WHERE f.kind = 'public_float' AND f.cik = l.cik AND p.close > 0 AND p.known_at < f.known_at
        )
        SELECT f.*, p.raw_close, coalesce(s.factor, 1) AS as_of_factor
        FROM latest f
        ASOF LEFT JOIN splits s ON f.cik = s.cik AND f.as_of_date >= s.ex_date
        LEFT JOIN prices p ON f.cik = p.cik AND f.accession = p.accession AND f.kind = 'public_float'
    """)
    con.unregister("facts")
    reports = con.sql("SELECT count(*) FROM reports").fetchone()[0]
    print(f"{len(facts):,} SEC facts with filing clocks, {reports:,} dated reports", flush=True)


PANEL = """
    WITH members AS (
        SELECT symbol, security_id, session::DATE AS session, median_dollar_volume_20,
               make_timestamptz(year(session), month(session), day(session),
                   9, 30, 0, 'America/New_York') AS decision_at
        FROM universe WHERE session >= ? AND session < ?
    ), linked AS (
        SELECT m.*, CASE WHEN i.symbol = m.symbol THEN l.cik END AS cik, i.first_date AS link_date
        FROM members m
        ASOF LEFT JOIN by_symbol l ON m.symbol = l.symbol AND m.session > l.first_date
        ASOF LEFT JOIN by_cik i ON l.cik = i.cik AND m.session > i.first_date
    )
    SELECT m.symbol, m.security_id, m.session, m.decision_at, m.cik,
           m.median_dollar_volume_20,
           o.value * coalesce(s.factor, 1) / o.as_of_factor AS shares_outstanding,
           o.value::BIGINT AS shares_outstanding_reported, o.as_of_date AS shares_outstanding_as_of_date,
           o.known_at AS shares_outstanding_known_at, o.release_session AS shares_outstanding_release_session,
           o.accession AS shares_outstanding_accession,
           f.value / f.raw_close * coalesce(s.factor, 1) / f.as_of_factor AS float_shares_estimate,
           f.value AS public_float_usd, f.raw_close AS public_float_raw_close,
           f.as_of_date AS public_float_as_of_date, f.known_at AS public_float_known_at,
           f.release_session AS public_float_release_session, f.accession AS public_float_accession
    FROM linked m
    ASOF LEFT JOIN splits s ON m.cik = s.cik AND m.session >= s.ex_date
    ASOF LEFT JOIN (SELECT * FROM reports WHERE kind = 'shares_outstanding') o
        ON m.cik = o.cik AND m.link_date = o.link_date AND m.decision_at > o.known_at
    ASOF LEFT JOIN (SELECT * FROM reports WHERE kind = 'public_float') f
        ON m.cik = f.cik AND m.link_date = f.link_date AND m.decision_at > f.known_at
"""


def build(path, universe):
    with _connect("450MB") as con, TemporaryDirectory(dir=DERIVED) as work:
        con.execute(f"CREATE VIEW universe AS SELECT * FROM read_parquet({universe.as_posix()!r}) WHERE is_member")
        prepare(con, path)
        output = DERIVED / FILENAME
        pending = output.with_suffix(".part")
        first, last = con.sql("SELECT min(year(session)), max(year(session)) FROM universe").fetchone()
        parts = []
        for year in range(first, last + 1):
            con.execute("CREATE OR REPLACE TEMP TABLE panel AS " + PANEL, [f"{year}-01-01", f"{year + 1}-01-01"])
            coverage = con.sql("""
                SELECT count(*), count(shares_outstanding), count(float_shares_estimate),
                       count(shares_outstanding) FILTER (WHERE session - shares_outstanding_as_of_date < 120),
                       count(float_shares_estimate) FILTER (WHERE session - public_float_as_of_date < 120)
                FROM panel WHERE median_dollar_volume_20 >= 5000000
            """).fetchone()
            print(year, *coverage, flush=True)
            part = (Path(work) / f"{year}.parquet").as_posix()
            con.execute(f"""
                COPY (SELECT * EXCLUDE (median_dollar_volume_20) FROM panel
                      WHERE shares_outstanding IS NOT NULL OR public_float_usd IS NOT NULL
                      ORDER BY session, security_id) TO {part!r} (COMPRESSION ZSTD, ROW_GROUP_SIZE 32768)
            """)
            parts.append(part)
        con.execute(f"""
            COPY (SELECT * FROM read_parquet({parts!r})) TO {pending.as_posix()!r}
            (FORMAT PARQUET, COMPRESSION ZSTD)
        """)
        rows = pq.ParquetFile(pending).metadata.num_rows
        pending.replace(output)
        print(f"{output}: {rows:,} rows", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--companyfacts", type=Path, default=COMPANYFACTS)
    parser.add_argument("--universe", type=Path, default=UNIVERSE)
    parser.add_argument("--refresh", action="store_true", help="Download companyfacts under opencomposer-research")
    args = parser.parse_args()
    if args.refresh:
        client = SecClient()
        part = args.companyfacts.with_suffix(".part")
        try:
            client.stream_to_file(COMPANYFACTS_ZIP_URL, part)
        finally:
            client.close()
        part.replace(args.companyfacts)
    print("Year, liquid rows, shares covered, float covered, shares <120d, float <120d", flush=True)
    build(args.companyfacts, args.universe)


if __name__ == "__main__":
    main()
