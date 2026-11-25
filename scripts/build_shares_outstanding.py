"""Build the SEC shares/float panel with python -m scripts.build_shares_outstanding."""

import argparse
import json
from datetime import datetime
from functools import cache
from math import log10
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
BASIC_SHARES = (
    "CommonStockSharesOutstanding",
    "WeightedAverageNumberOfSharesOutstandingBasic",
    "WeightedAverageNumberOfShareOutstandingBasicAndDiluted",
)
# (issuer, source accession) maps to (traded symbol, ordinary shares per traded unit).
# Verona: SEC 2017 F-6 (333-217353). Adaptimmune: SEC 2015 Nasdaq 8-A.
DEPOSITARY_RATIOS = {
    (1657312, "0001193805-17-000655"): ("VRNA", 8),
    (1621227, "0001104659-15-032500"): ("ADAP", 6),
}
# Exact cover text where the structured share tag disagrees. Sources in shares-unit-repair.md.
VERIFIED_COVER_SHARES = {
    (1398805, "0001683168-22-005630"): 10_084_970,
    (1398805, "0001683168-22-007522"): 10_095_562,
    (1398805, "0001683168-23-002090"): 10_229_060,
    (1398805, "0001683168-23-002822"): 10_760_195,
    (1601669, "0001601669-19-000003"): 22_682_875,
}


@cache
def session_clock(day):
    return us_equity_session_close(day), next_us_equity_session(day)


def filing_facts(path, start, issuer_types, depositary_ratios):
    with ZipFile(path) as facts, ZipFile(SUBMISSIONS_DIR / "submissions-current.zip") as submissions:
        def submission(name):
            return json.loads(submissions.read(name))

        for cik in sorted(pd.read_parquet(HISTORY_PATH, columns=["cik"]).cik.unique().tolist()):
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
            clocks = {}
            first_depositary = first_foreign = None
            for table in sec_submission_tables(submission(name)["filings"], start="", read_page=submission):
                for accession, stamp, form in zip(
                    table["accessionNumber"], table["acceptanceDateTime"], table["form"], strict=True
                ):
                    if not stamp:
                        continue
                    clocks[accession] = stamp
                    form = form.removesuffix("/A")
                    if form in {"F-6", "F-6EF", "F-6 POS", "F-6EF POS"}:
                        first_depositary = min(first_depositary or stamp, stamp)
                    if form in {"F-1", "20-F"}:
                        first_foreign = min(first_foreign or stamp, stamp)
                    if ratio := DEPOSITARY_RATIOS.get((cik, accession)):
                        depositary_ratios.append((cik, *ratio, stamp))
            issuer_types.append((cik, first_depositary, first_foreign))
            share_filings = {row["accn"] for kind, row in rows if kind == "shares_outstanding"}
            gaap = payload.get("us-gaap", {})
            basic = {}
            for priority, tag in enumerate(BASIC_SHARES):
                for row in gaap.get(tag, {}).get("units", {}).get("shares", []):
                    accession = row.get("accn")
                    if accession not in share_filings or not row.get("end") or row.get("val", 0) <= 0:
                        continue
                    rank = (-priority, row["end"], row.get("start", ""))
                    best_rank, previous = basic.get(accession, ((), None))
                    if rank > best_rank:
                        basic[accession] = rank, row
                    elif rank == best_rank and previous is not None and previous["val"] != row["val"]:
                        basic[accession] = rank, None
            rows.extend(("basic", row) for _, row in basic.values() if row is not None)
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
                    # Keep the source integer exact, even if another fact exceeds BIGINT.
                    yield cik, kind, row["end"], str(row["val"]), accession, accepted, day, release


def prepare(con, path):
    start = con.sql("SELECT min(trade_date)::DATE::VARCHAR FROM universe").fetchone()[0]
    issuer_types, depositary_ratios = [], []
    facts = pd.DataFrame.from_records(filing_facts(path, start, issuer_types, depositary_ratios), columns=[
        "cik", "kind", "as_of_date", "value", "accession", "known_at", "accepted_day", "release_session",
    ])
    con.register("facts", facts)
    con.register("issuer_type_evidence", pd.DataFrame(issuer_types, columns=["cik", "depositary_at", "foreign_at"]))
    con.execute("""
        CREATE TEMP TABLE issuer_types AS
        SELECT cik, depositary_at::TIMESTAMPTZ AS depositary_at, foreign_at::TIMESTAMPTZ AS foreign_at
        FROM issuer_type_evidence
    """)
    con.unregister("issuer_type_evidence")
    con.execute("""
        CREATE TEMP TABLE depositary_ratios (
            cik BIGINT, symbol VARCHAR, ordinary_per_depositary DOUBLE, ratio_at TIMESTAMPTZ
        )
    """)
    if depositary_ratios:
        con.executemany("INSERT INTO depositary_ratios VALUES (?, ?, ?, ?)", depositary_ratios)
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
        CREATE TEMP TABLE depositary_titles AS
        SELECT si.symbol, l.cik, min(si.known_at) AS title_at
        FROM read_parquet({(DERIVED / 'short_interest.parquet').as_posix()!r}) si
        ASOF JOIN by_symbol l ON si.symbol = l.symbol AND si.settlement_date > l.first_date
        WHERE l.cik IS NOT NULL AND si.known_at IS NOT NULL
          AND regexp_matches(si.issue_name, '(?i)depositary|depository|\\b(?:adr|ads|dep shs?)\\b')
        GROUP BY si.symbol, l.cik
    """)
    con.execute(f"""
        CREATE TEMP TABLE share_actions AS
        SELECT l.cik, a.ex_date::DATE AS ex_date,
               min(greatest(a.ex_date::DATE, a.process_date::DATE)) AS effective_session,
               CASE WHEN a.kind = 'stock_dividends' THEN a.rate ELSE a.new_rate / a.old_rate END AS ratio
        FROM read_parquet({(DERIVED / ACTIONS).as_posix()!r}) a
        ASOF JOIN by_symbol l ON a.symbol = l.symbol AND a.ex_date > l.first_date
        WHERE a.kind IN ('reverse_splits', 'forward_splits', 'stock_dividends')
          AND a.process_date IS NOT NULL AND l.cik IS NOT NULL AND ratio > 0 AND ratio <> 1
          -- Alpaca backfilled these spin-offs under forward_splits.
          AND NOT (a.kind = 'forward_splits' AND (a.symbol, a.ex_date::DATE) IN (
              ('FTV', DATE '2020-10-09'), ('CUZ', DATE '2016-10-07'), ('HCP', DATE '2016-11-01')
          ))
        GROUP BY l.cik, a.ex_date::DATE, ratio
    """)
    con.execute("""
        CREATE TEMP TABLE dated AS
        WITH unambiguous AS (
            SELECT DISTINCT * REPLACE (as_of_date::DATE AS as_of_date, value::DOUBLE AS value),
                   value AS raw_value
            FROM facts WHERE kind <> 'basic'
            WINDOW w AS (PARTITION BY cik, kind, accession, as_of_date)
            QUALIFY min(value::DOUBLE) OVER w = max(value::DOUBLE) OVER w
        )
        SELECT f.*, i.symbol, i.first_date AS link_date
        FROM unambiguous f
        ASOF JOIN by_cik i ON f.cik = i.cik AND f.accepted_day > i.first_date
        ASOF JOIN by_symbol l ON i.symbol = l.symbol AND f.accepted_day > l.first_date
        WHERE f.cik = l.cik
        QUALIFY row_number() OVER (
            PARTITION BY f.cik, i.first_date, kind, known_at ORDER BY as_of_date DESC, accession DESC
        ) = 1
    """)
    con.execute("""
        CREATE TEMP TABLE floats AS
        WITH prices AS (
            SELECT f.cik, f.accession, f.as_of_date, p.close AS raw_close
            FROM dated f
            ASOF JOIN by_cik i ON f.cik = i.cik AND f.as_of_date > i.first_date
            ASOF JOIN by_symbol l ON i.symbol = l.symbol AND f.as_of_date > l.first_date
            JOIN universe p ON p.symbol = i.symbol AND p.trade_date = f.as_of_date
            WHERE f.kind = 'public_float' AND f.cik = l.cik AND p.close > 0 AND p.known_at < f.known_at
        )
        SELECT f.*, p.raw_close
        FROM dated f LEFT JOIN prices p USING (cik, accession, as_of_date)
        WHERE f.kind = 'public_float'
    """)
    repair_units(con)
    con.execute("""
        CREATE TEMP TABLE reports AS
        SELECT * FROM (
            SELECT s.*, NULL::DOUBLE AS raw_close FROM shares s
            UNION ALL BY NAME SELECT f.* FROM floats f
        ) QUALIFY as_of_date = max(as_of_date) OVER (
            PARTITION BY cik, link_date, kind ORDER BY known_at
        )
    """)
    con.execute("""
        CREATE TEMP TABLE report_adjustments AS
        WITH steps AS (
            SELECT r.cik, r.kind, r.link_date, r.known_at, a.effective_session, product(a.ratio) AS ratio
            FROM reports r JOIN share_actions a ON r.cik = a.cik AND r.as_of_date < a.ex_date
            GROUP BY ALL
        )
        SELECT * EXCLUDE (ratio), product(ratio) OVER (
            PARTITION BY cik, kind, link_date, known_at ORDER BY effective_session
        ) AS factor
        FROM steps
    """)
    con.unregister("facts")
    reports = con.sql("SELECT count(*) FROM reports").fetchone()[0]
    print(f"{len(facts):,} SEC facts with filing clocks, {reports:,} dated reports", flush=True)


def unit_scale(value, references):
    votes = {}
    for reference in references:
        if reference is not None:
            ratio = value / reference
            scale = round(log10(ratio) / 3)
            if 0.7 <= ratio / 1000.0**scale <= 1.3:
                votes[scale] = votes.get(scale, 0) + 1
    if votes:
        scale = max(votes, key=votes.get)
        count = votes.pop(scale)
        if scale == 0 and count > max(votes.values(), default=0):
            return 'ok', 1.0
        factor = 1000.0**-scale
        if count >= 2 and count > max(votes.values(), default=0) and value * factor >= 1:
            return 'rescaled', factor
    return 'ambiguous', None


def repair_units(con):
    evidence = con.sql("""
        WITH basic AS (
            SELECT cik, accession, as_of_date::DATE AS as_of_date, value::DOUBLE AS value
            FROM facts WHERE kind = 'basic'
        ), filings AS (
            SELECT *, lag(as_of_date) OVER w AS prev_date, lag(known_at) OVER w AS prev_at
            FROM dated WHERE kind = 'shares_outstanding'
            WINDOW w AS (PARTITION BY cik, link_date ORDER BY known_at)
        ), priced_floats AS (
            SELECT * FROM floats WHERE raw_close IS NOT NULL
            QUALIFY as_of_date = max(as_of_date) OVER (
                PARTITION BY cik, link_date ORDER BY known_at
            )
        )
        SELECT s.cik, s.link_date, s.accession, s.value,
               CASE WHEN s.prev_at < s.known_at AND s.as_of_date - s.prev_date BETWEEN 0 AND 550
                    THEN prev.factor END AS previous_multiplier,
               CASE WHEN s.as_of_date - b.as_of_date BETWEEN 0 AND 550
                    THEN b.value * basic_units.factor END AS financials,
               CASE WHEN coalesce(i.depositary_at <= s.known_at OR i.foreign_at <= s.known_at
                                  OR d.title_at <= s.known_at, false) THEN NULL
                    WHEN s.as_of_date - f.as_of_date BETWEEN 0 AND 550
                    THEN f.value / f.raw_close * own_float.factor
                    WHEN s.as_of_date - p.as_of_date BETWEEN 0 AND 550
                    THEN p.value / p.raw_close * previous_float.factor END AS float_reference
        FROM filings s
        LEFT JOIN basic b USING (cik, accession)
        LEFT JOIN priced_floats f USING (cik, link_date, accession)
        LEFT JOIN issuer_types i USING (cik)
        LEFT JOIN depositary_titles d ON s.cik = d.cik AND s.symbol = d.symbol
        ASOF LEFT JOIN priced_floats p ON s.cik = p.cik AND s.link_date = p.link_date
            AND s.known_at > p.known_at
        CROSS JOIN LATERAL (
            SELECT coalesce(product(a.ratio), 1) AS factor FROM share_actions a
            WHERE a.cik = s.cik AND a.ex_date > s.prev_date AND a.ex_date <= s.as_of_date
              AND a.effective_session <= s.accepted_day
        ) prev
        CROSS JOIN LATERAL (
            SELECT coalesce(product(a.ratio), 1) AS factor FROM share_actions a
            WHERE a.cik = s.cik AND a.ex_date > b.as_of_date AND a.ex_date <= s.as_of_date
              AND a.effective_session <= s.accepted_day
        ) basic_units
        CROSS JOIN LATERAL (
            SELECT coalesce(product(a.ratio), 1) AS factor FROM share_actions a
            WHERE a.cik = s.cik AND a.ex_date > f.as_of_date AND a.ex_date <= s.as_of_date
              AND a.effective_session <= s.accepted_day
        ) own_float
        CROSS JOIN LATERAL (
            SELECT coalesce(product(a.ratio), 1) AS factor FROM share_actions a
            WHERE a.cik = s.cik AND a.ex_date > p.as_of_date AND a.ex_date <= s.as_of_date
              AND a.effective_session <= s.accepted_day
        ) previous_float
        ORDER BY s.cik, s.link_date, s.known_at
    """).fetchall()
    checked = []
    previous_key = previous = None
    for cik, link_date, accession, value, multiplier, financials, float_reference in evidence:
        key = (cik, link_date)
        prior = previous * multiplier if key == previous_key and previous and multiplier else None
        if verified := VERIFIED_COVER_SHARES.get((cik, accession)):
            status, factor = ('ok' if verified == value else 'rescaled'), verified / value
        else:
            status, factor = unit_scale(value, (financials, prior, float_reference))
        checked.append((cik, accession, status, factor))
        previous_key, previous = key, value * factor if factor is not None else None
    con.register("checked_units", pd.DataFrame(checked, columns=[
        "cik", "accession", "scale_status", "scale_factor",
    ]))
    con.execute("""
        CREATE TEMP TABLE shares AS
        SELECT s.*, c.scale_status, c.scale_factor
        FROM dated s JOIN checked_units c USING (cik, accession)
        WHERE s.kind = 'shares_outstanding'
    """)
    con.unregister("checked_units")


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
           o.raw_value::BIGINT AS shares_outstanding_reported, o.as_of_date AS shares_outstanding_as_of_date,
           o.known_at AS shares_outstanding_known_at, o.release_session AS shares_outstanding_release_session,
           o.accession AS shares_outstanding_accession,
           CASE WHEN r.ratio_at < o.known_at THEN r.ordinary_per_depositary END AS ordinary_per_depositary,
           CASE WHEN i.depositary_at < m.decision_at OR d.title_at < m.decision_at
                       OR r.ratio_at < m.decision_at THEN 'depositary'
                WHEN i.foreign_at < m.decision_at THEN 'unverified' END AS depositary_status,
           CASE WHEN o.accession IS NULL THEN NULL
                WHEN depositary_status IS NOT NULL AND ordinary_per_depositary IS NULL THEN 'ambiguous'
                WHEN ordinary_per_depositary <> 1 AND o.scale_status = 'ok' THEN 'rescaled'
                ELSE o.scale_status END AS unit_status,
           CASE WHEN unit_status <> 'ambiguous'
                THEN o.scale_factor / coalesce(ordinary_per_depositary, 1) END AS unit_factor,
           o.value * unit_factor * coalesce(s.factor, 1) AS shares_outstanding,
           f.value / f.raw_close * coalesce(t.factor, 1) AS float_shares_estimate,
           f.value AS public_float_usd, f.raw_close AS public_float_raw_close,
           f.as_of_date AS public_float_as_of_date, f.known_at AS public_float_known_at,
           f.release_session AS public_float_release_session, f.accession AS public_float_accession
    FROM linked m
    ASOF LEFT JOIN (SELECT * FROM reports WHERE kind = 'shares_outstanding') o
        ON m.cik = o.cik AND m.link_date = o.link_date AND m.decision_at > o.known_at
    ASOF LEFT JOIN (SELECT * FROM reports WHERE kind = 'public_float') f
        ON m.cik = f.cik AND m.link_date = f.link_date AND m.decision_at > f.known_at
    ASOF LEFT JOIN (SELECT * FROM report_adjustments WHERE kind = 'shares_outstanding') s
        ON o.cik = s.cik AND o.link_date = s.link_date AND o.known_at = s.known_at
        AND m.session >= s.effective_session
    ASOF LEFT JOIN (SELECT * FROM report_adjustments WHERE kind = 'public_float') t
        ON f.cik = t.cik AND f.link_date = t.link_date AND f.known_at = t.known_at
        AND m.session >= t.effective_session
    LEFT JOIN issuer_types i ON m.cik = i.cik
    LEFT JOIN depositary_titles d ON m.cik = d.cik AND m.symbol = d.symbol
    ASOF LEFT JOIN depositary_ratios r
        ON m.cik = r.cik AND m.symbol = r.symbol AND m.decision_at > r.ratio_at
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
                      WHERE shares_outstanding_reported IS NOT NULL OR public_float_usd IS NOT NULL
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
