"""Build the daily English Wikipedia attention history for liquid issuers."""

from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path
from time import monotonic, sleep
from urllib.parse import quote, unquote
from zoneinfo import ZoneInfo

import duckdb
import httpx
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
DERIVED = ROOT.parent / "market-data" / "derived"
UNIVERSE = DERIVED / "daily-us-stock-universe.parquet"
SEC_HISTORY = ROOT / "data/raw/sec_ma/cik_symbol_history.parquet"
PARTS = DERIVED / ".wiki-pageviews-by-article"
VIEWS = DERIVED / "wiki-pageviews.parquet"
MAPPING = DERIVED / "wiki-pageviews-mapping.parquet"
COVERAGE = DERIVED / "wiki-pageviews-coverage.csv"
FIRST_DAY = date(2016, 1, 1)
WDQS = "https://query.wikidata.org/sparql"
PAGEVIEWS = "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article"
CIK_QUERY = """
SELECT ?item ?cik ?article WHERE {
  ?item wdt:P5531 ?cik .
  ?article schema:about ?item; schema:isPartOf <https://en.wikipedia.org/> .
}
"""
TICKER_QUERY = """
SELECT ?item ?ticker ?article ?start ?end WHERE {
  VALUES ?exchange { wd:Q13677 wd:Q82059 wd:Q846626 wd:Q10593835 wd:Q16846407 }
  ?item p:P414 ?listing .
  ?listing ps:P414 ?exchange; pq:P249 ?ticker; wikibase:rank ?rank .
  FILTER(?rank != wikibase:DeprecatedRank)
  OPTIONAL { ?listing pq:P580 ?start . }
  OPTIONAL { ?listing pq:P582 ?end . }
  ?article schema:about ?item; schema:isPartOf <https://en.wikipedia.org/> .
}
"""
VIEW_SCHEMA = pa.schema([
    ("wikidata_id", pa.string()),
    ("article", pa.string()),
    ("view_date", pa.date32()),
    ("views", pa.int64()),
    ("known_at", pa.timestamp("us", tz="UTC")),
    ("fetched_at", pa.timestamp("us", tz="UTC")),
])


def liquid_segments(end):
    with duckdb.connect(config={"threads": 2}) as db:
        return db.execute("""
            WITH universe AS (
              SELECT * FROM read_parquet(?) WHERE is_member AND trade_date <= ?
            ), eligible AS (
              SELECT year(trade_date) AS year, security_id, symbol,
                     min(trade_date)::DATE AS first_liquid,
                     max(trade_date)::DATE AS last_liquid
              FROM universe
              WHERE trade_date >= '2016-01-01' AND median_dollar_volume_20 >= 10000000
                AND security_type IN ('operating', 'adr', 'unknown')
              GROUP BY ALL
            ), ticker_segments AS (
              SELECT symbol, count(DISTINCT security_id) AS segments FROM universe GROUP BY symbol
            ), history AS (
              SELECT DISTINCT u.security_id, h.cik
              FROM (SELECT security_id, symbol, min(trade_date) AS first_day,
                           max(trade_date) AS last_day
                    FROM universe GROUP BY security_id, symbol) u
              JOIN read_parquet(?) h ON h.symbol = u.symbol
                 AND h.first_date <= u.last_day AND h.last_date >= u.first_day
            )
            SELECT e.*, t.segments, list(DISTINCT h.cik ORDER BY h.cik)
                FILTER (WHERE h.cik IS NOT NULL) AS ciks
            FROM eligible e JOIN ticker_segments t USING (symbol)
            LEFT JOIN history h USING (security_id)
            GROUP BY ALL ORDER BY year, security_id, symbol
        """, [str(UNIVERSE), end, str(SEC_HISTORY)]).fetchall()


def get(client, url, *, params=None, interval=0):
    for attempt in range(5):
        begin = monotonic()
        try:
            response = client.get(url, params=params)
            fetched_at = datetime.now(UTC)
        except httpx.TransportError:
            if attempt == 4:
                raise
            sleep(max(interval - (monotonic() - begin), 2 ** attempt))
            continue
        if response.status_code not in (429, 500, 502, 503, 504) or attempt == 4:
            sleep(max(0, interval - (monotonic() - begin)))
            return response, fetched_at
        header = response.headers.get("Retry-After")
        delay = max(5, 2 ** (attempt + 1))
        if header:
            delay = (int(header) if header.isdecimal() else
                     (parsedate_to_datetime(header) - datetime.now(UTC)).total_seconds())
        sleep(max(delay, interval - (monotonic() - begin)))


def wikidata_rows(client, query):
    response, _ = get(client, WDQS, params={"query": query, "format": "json"})
    response.raise_for_status()
    for row in response.json()["results"]["bindings"]:
        yield {name: value["value"] for name, value in row.items()}


def build_mapping(client, end):
    by_cik = defaultdict(set)
    ciks_by_item = defaultdict(set)
    by_ticker = defaultdict(list)
    for row in wikidata_rows(client, CIK_QUERY):
        if row["cik"].isdecimal():
            cik = int(row["cik"])
            by_cik[cik].add((row["item"], row["article"]))
            ciks_by_item[row["item"]].add(cik)
    for row in wikidata_rows(client, TICKER_QUERY):
        ticker = row["ticker"].upper().replace(".", "-")
        by_ticker[ticker].append(row)

    fetched_at = datetime.now(UTC)
    records = []
    for year, security_id, symbol, first, last, segments, ciks in liquid_segments(end):
        cik = ciks[0] if ciks and len(ciks) == 1 else None
        candidates = by_cik[cik]
        source = "Wikidata P5531 + SEC dated symbol history"
        if not candidates and (not ciks or cik is not None):
            candidates = {
                (row["item"], row["article"])
                for row in by_ticker[symbol.replace(".", "-")]
                if (row.get("start", "0000")[:10] <= last.isoformat())
                and (row.get("end", "9999")[:10] >= first.isoformat())
                and (segments == 1 or ("start" in row and "end" in row))
                and (cik is None or not ciks_by_item[row["item"]] - {cik})
            }
            source = "Wikidata P414/P249 (US exchange ticker)"
        item, article_url = next(iter(candidates)) if len(candidates) == 1 else (None, None)
        qid = item.rsplit("/", 1)[-1] if item else None
        title = unquote(article_url.split("/wiki/", 1)[1]) if article_url else None
        records.append({
            "year": year, "security_id": security_id, "symbol": symbol,
            "first_liquid": first, "last_liquid": last, "cik": cik,
            "issuer_id": f"cik:{cik}" if cik else (qid or f"security:{security_id}"),
            "wikidata_id": qid, "article": title, "article_url": article_url,
            "mapping_source": source if qid else None, "mapping_fetched_at": fetched_at,
        })
    frame = pd.DataFrame(records)
    frame["cik"] = frame["cik"].astype("Int64")
    return frame


def save_table(table, path):
    pending = path.with_suffix(".tmp")
    pq.write_table(table, pending)
    pending.replace(path)


def capture_article(client, qid, article, end):
    path = PARTS / f"{qid}.parquet"
    prior = pq.read_table(path) if path.exists() else None
    start = FIRST_DAY
    if prior is not None and prior.schema.metadata[b"article"].decode() == article:
        metadata = prior.schema.metadata
        through = date.fromisoformat(metadata[b"through"].decode())
        if date.fromisoformat(metadata.get(b"requested_end", metadata[b"through"]).decode()) >= end:
            return
        start = through + timedelta(days=1)
    else:
        prior = None
    if end < start:
        return

    url = (f"{PAGEVIEWS}/en.wikipedia/all-access/user/{quote(article, safe='')}/daily/"
           f"{start:%Y%m%d}00/{end:%Y%m%d}00")
    # The generic project User-Agent uses the anonymous Wikimedia limit (10/min).
    response, fetched_at = get(client, url, interval=6.1)
    if response.status_code == 404:
        items = []
    else:
        response.raise_for_status()
        items = response.json()["items"]

    rows = []
    for item in items:
        day_start = datetime.strptime(item["timestamp"], "%Y%m%d%H").replace(tzinfo=UTC)
        rows.append({"wikidata_id": qid, "article": article, "view_date": day_start.date(),
                     "views": item["views"], "known_at": day_start + timedelta(days=2),
                     "fetched_at": fetched_at})
    # Leave recent missing days eligible for retrieval on the next run.
    through = max([end - timedelta(days=2), *(row["view_date"] for row in rows)])
    table = pa.Table.from_pylist(rows, schema=VIEW_SCHEMA)
    if prior is not None:
        through = max(through, start - timedelta(days=1))
        table = pa.concat_tables([prior, table])
    save_table(table.replace_schema_metadata({
        "article": article, "through": through.isoformat(), "requested_end": end.isoformat(),
    }), path)


def main():
    end = datetime.now(ZoneInfo("America/Los_Angeles")).date() - timedelta(days=1)
    PARTS.mkdir(parents=True, exist_ok=True)
    with httpx.Client(headers={"User-Agent": "MarketResearchArchive/1.0"},
                      timeout=65, follow_redirects=True) as client:
        mapping = build_mapping(client, end)
        save_table(pa.Table.from_pandas(mapping, preserve_index=False), MAPPING)
        coverage = (mapping.assign(mapped=mapping["wikidata_id"].notna())
                    .groupby(["year", "issuer_id"])["mapped"].any()
                    .groupby("year").agg(liquid_issuers="size", mapped_issuers="sum"))
        coverage["mapped_share"] = coverage["mapped_issuers"] / coverage["liquid_issuers"]
        coverage.to_csv(COVERAGE)
        print(coverage.to_string(), flush=True)

        articles = list(mapping[["wikidata_id", "article"]].dropna()
                        .drop_duplicates().sort_values("wikidata_id").itertuples(index=False, name=None))
        print(f"Fetching {len(articles)} articles through {end}", flush=True)
        for index, (qid, article) in enumerate(articles, 1):
            capture_article(client, qid, article, end)
            if index % 100 == 0:
                print(f"{index}/{len(articles)} articles checked", flush=True)

    pending = VIEWS.with_suffix(".tmp")
    with pq.ParquetWriter(pending, VIEW_SCHEMA) as writer:
        for qid, _ in articles:
            writer.write_table(pq.read_table(PARTS / f"{qid}.parquet"))
    pending.replace(VIEWS)
    print(f"{VIEWS}: {pq.ParquetFile(VIEWS).metadata.num_rows} rows", flush=True)


if __name__ == "__main__":
    main()
