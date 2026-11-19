"""Publish SEC and FINRA tables for local point-in-time research.

Run from the repo with ``python -m scripts.build_research_events TABLE``.
Refresh the source files using the existing SEC quarterly and FINRA download collectors.
For a new SEC submissions snapshot add ``--refresh`` under opencomposer-research.
"""

import argparse
import json
from datetime import date, time
from zipfile import ZipFile

import duckdb
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from open_composer.adapters.data.sip_parquet import MARKET_DATA
from open_composer.adapters.events.fetcher import download_sec_submissions, sec_submission_tables
from open_composer.market_sessions import NEW_YORK, next_us_equity_session, us_equity_session_close
from scripts import collect_finra_short_interest as interest
from scripts import collect_finra_short_volume as volume
from scripts.backfill_finra_short_volume import LEGACY_ROOT
from scripts.build_earnings_events import filing_matches, rows_from_arrays
from scripts.build_sec_sic_map import HISTORY_PATH, SUBMISSIONS_DIR, member_name
from scripts.collect_sec_insider_transactions import PARSED_ROOT

START = date(2016, 1, 1)
DERIVED = MARKET_DATA / "derived"


def publish(frame, name):
    path = DERIVED / f"{name}.parquet"
    temporary = path.with_suffix(".part")
    frame.to_parquet(temporary, index=False, compression="zstd")
    temporary.replace(path)
    print(f"{name}: {len(frame):,} rows", flush=True)


def earnings_releases(archive):
    history = pd.read_parquet(HISTORY_PATH)
    links = {cik: list(rows.itertuples(index=False)) for cik, rows in history.groupby("cik")}
    rows = []
    missing_time = 0
    with ZipFile(archive) as source:

        def read_page(name):
            return json.loads(source.read(name))

        # Browse the JSON archive once so issuers absent from today's listing
        # can still be mapped using the historical ticker links.
        for member in source.infolist():
            name = member.filename
            if len(name) != 18 or not name.startswith("CIK") or not name[3:13].isdigit():
                continue
            cik = int(name[3:13])
            doc = read_page(member_name(cik))
            past = links.get(cik, [])
            for table in sec_submission_tables(
                doc["filings"], start=START.isoformat(), read_page=read_page
            ):
                for filing in rows_from_arrays(table):
                    if not filing_matches(filing.form, filing.items):
                        continue
                    if not filing.filing_date or filing.filing_date < START.isoformat():
                        continue
                    if not filing.acceptance_raw:
                        missing_time += 1
                        continue
                    accepted = pd.Timestamp(filing.acceptance_raw, tz="UTC")
                    local = accepted.tz_convert(NEW_YORK)
                    day = local.date()
                    if day < START:
                        continue
                    close = us_equity_session_close(day)
                    release_session = (
                        day if close and local.time() < close else next_us_equity_session(day)
                    )
                    release_open = pd.Timestamp.combine(release_session, time(9, 30)).tz_localize(
                        NEW_YORK
                    )
                    preopen = local < release_open
                    first_open = (
                        release_session if preopen else next_us_equity_session(release_session)
                    )
                    stamp = pd.Timestamp(day)
                    # Carry the last observed link forward. The last observation in a
                    # reconstructed interval cannot certify the ticker on an earlier filing.
                    observed = [link for link in past if link.first_date < stamp]
                    latest = max((link.first_date for link in observed), default=None)
                    symbols = {link.symbol for link in observed if link.first_date == latest}
                    symbol = next(iter(symbols)) if len(symbols) == 1 else None
                    rows.append((
                        cik, filing.accession, symbol, "prior_sec_link" if symbol else "unmapped",
                        accepted, day, release_session, preopen, first_open,
                    ))
    print(f"SEC item 2.02 filings omitted for missing acceptance timestamp: {missing_time}")
    frame = pd.DataFrame(
        rows,
        columns=[
            "cik", "accession", "symbol", "symbol_source", "accepted_at", "acceptance_date",
            "release_session", "known_before_release_session_open", "visible_date",
        ],
    ).drop_duplicates(["cik", "accession", "symbol"])
    return frame.sort_values(["accepted_at", "symbol"], ignore_index=True)


def insider_daily(archive):
    # owner_seq=0 counts the transaction once even in a jointly filed return.
    files = sorted(PARSED_ROOT.glob("20??q?.parquet"))
    with duckdb.connect(config={"threads": 2, "memory_limit": "300MB"}) as connection:
        frame = (
            connection.read_parquet([str(path) for path in files])
            .query(
                "transactions",
                """
            SELECT issuer_cik AS cik, filing_date, issuer_symbol AS symbol, accession,
                   count(*) FILTER (WHERE trans_code = 'P') AS purchase_count,
                   count(*) FILTER (WHERE trans_code = 'S') AS sale_count,
                   coalesce(sum(shares) FILTER (WHERE trans_code = 'P'), 0) AS purchase_shares,
                   coalesce(sum(shares) FILTER (WHERE trans_code = 'S'), 0) AS sale_shares
              FROM transactions
             WHERE document_type = '4' AND trans_code IN ('P', 'S') AND owner_seq = 0
               AND filing_date >= '2016-01-01' AND issuer_cik IS NOT NULL
             GROUP BY issuer_cik, filing_date, issuer_symbol, accession
        """,
            )
            .df()
        )
    accepted = {}
    with ZipFile(archive) as source:
        names = set(source.namelist())
        for cik in frame.cik.unique():
            name = member_name(cik)
            if name not in names:
                continue
            filings = json.loads(source.read(name))["filings"]
            for table in sec_submission_tables(
                filings, start=START.isoformat(), read_page=lambda name: json.loads(source.read(name))
            ):
                for accession, form, stamp in zip(
                    table["accessionNumber"], table["form"], table["acceptanceDateTime"], strict=True,
                ):
                    if form == "4" and stamp:
                        accepted[accession] = stamp
    frame["known_at"] = pd.to_datetime(frame.pop("accession").map(accepted), utc=True, format="ISO8601")
    print(f"Form 4 filing rows omitted for missing acceptance: {frame.known_at.isna().sum():,}")
    frame = frame.dropna(subset=["known_at"])
    frame = frame.groupby(["cik", "filing_date", "symbol"], dropna=False, as_index=False).agg(
        purchase_count=("purchase_count", "sum"), sale_count=("sale_count", "sum"),
        purchase_shares=("purchase_shares", "sum"), sale_shares=("sale_shares", "sum"),
        known_at=("known_at", "max"),
    )
    # Preserve a daily aggregate, including any later evening filings for that day.
    days = frame.known_at.dt.tz_convert(NEW_YORK).dt.date
    visible = {day: next_us_equity_session(day) for day in days.unique()}
    frame["visible_date"] = pd.to_datetime(days.map(visible))
    return frame.sort_values(["filing_date", "cik", "symbol"], ignore_index=True)


def finra_table(name):
    is_interest = name == "short_interest"
    collector = interest if is_interest else volume
    columns = [
        column for column in collector.PARSED_COLUMNS if column not in ("fetched_at", "input_hash")
    ]
    schema = pa.schema([
        *(collector.parsed_schema().field(column) for column in columns),
        pa.field("known_at", pa.timestamp("ns", tz="UTC")),
    ])
    path = DERIVED / f"{name}.parquet"
    temporary = path.with_suffix(".part")
    rows = 0
    with pq.ParquetWriter(temporary, schema, compression="zstd") as writer:
        def write(frame):
            # Both standardized daily feeds have a publication date without a row timestamp.
            frame["known_at"] = (
                (frame.publication_date + pd.Timedelta(days=1) - pd.Timedelta(microseconds=1))
                .dt.tz_localize(NEW_YORK).dt.tz_convert("UTC").where(frame.visible_date.notna())
            )
            writer.write_table(pa.Table.from_pandas(frame, schema=schema, preserve_index=False))

        if is_interest:
            schedule, _ = interest.load_schedule()
            for snapshot in sorted(
                MARKET_DATA.parent.glob("archive/original-external/*/finra_short_interest/schedule/short-interest-reporting.html")
            ):
                official = interest.parse_official_schedule(snapshot.read_text(encoding="utf-8"))
                for row in official.itertuples(index=False):
                    schedule.setdefault(row.settlement_date, row.publication_date)
            files = sorted(interest.CONSOLIDATED_ROOT.glob("*.csv.gz"))
            for source in files:
                frame = interest.parse_raw_file(
                    source,
                    publication_schedule=schedule,
                    lag_sessions=interest.PUBLICATION_LAG_SESSIONS,
                )
                # FINRA marks these as revised but does not date the revision.
                frame.loc[frame.revision_flag.eq("R"), "visible_date"] = pd.NaT
                write(frame)
                rows += len(frame)
        else:
            for directory in (LEGACY_ROOT, volume.DAILY_ROOT):
                for source in sorted(directory.glob("*.txt.gz")):
                    frame = volume.parse_raw_file(source)
                    if directory == LEGACY_ROOT:
                        frame["source"] = "finra_cdn:regsho:FNSQ+FNYX+available_FNRA"
                    write(frame)
                    rows += len(frame)
    temporary.replace(path)
    print(f"{name}: {rows:,} rows", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "table", choices=("earnings_releases", "insider_daily", "short_interest", "short_volume")
    )
    parser.add_argument(
        "--refresh", action="store_true", help="Download a current SEC submissions snapshot"
    )
    args = parser.parse_args()
    DERIVED.mkdir(parents=True, exist_ok=True)
    if args.table in ("earnings_releases", "insider_daily"):
        archive = SUBMISSIONS_DIR / "submissions-current.zip"
        if args.refresh:
            download_sec_submissions(archive)
        builder = earnings_releases if args.table == "earnings_releases" else insider_daily
        publish(builder(archive), args.table)
    else:
        finra_table(args.table)


if __name__ == "__main__":
    main()
