"""H-20260916-07 step 0: FINRA bi-monthly equity short-interest collector.

Card: ``reports/research/hypotheses/H-20260916-07-finra-short-interest-avoid-list.md``
Capability: ``market.finra_short_interest`` in ``capabilities/registry.yaml``.

What this collects
------------------
FINRA Rule 4560 makes member firms report their short positions in all equity
securities twice a month. FINRA then publishes an aggregated snapshot per
settlement date. Two FINRA datasets carry it and they are **not** the same
thing:

``otcMarket/consolidatedShortInterest``
    The consolidated view across all exchanges -- exchange-listed names
    (``marketClassCode`` ``NYSE`` / ``NNM`` / ``NGS`` / ``NCM`` / ``AMEX`` ...)
    as well as OTC. This is what this collector pulls: our universe is the
    point-in-time top-1,000 by dollar ADV, i.e. exchange-listed.
``otcMarket/equityShortInterest``
    OTC-only (``marketCategoryDescription = "Other OTC"``), a different field
    set, and irrelevant to a top-1,000 book. Not collected.

Deliberately **not** collected: the daily short *sale volume* files
(``regShoDaily``). FINRA states in its own catalog that daily short sale
volume is "volume marked short on that day", not a net short position, and
that it is dominated by market-maker hedging. Reading it as bearish sentiment
is the card's failure mode (1); this file therefore cannot produce it.

Source, verified 2026-09-17
---------------------------
FINRA Query API, no credentials required for this dataset::

    POST https://api.finra.org/data/group/otcMarket/name/consolidatedShortInterest
    {"limit": 5000, "offset": N,
     "dateRangeFilters": [{"fieldName": "settlementDate",
                           "startDate": "...", "endDate": "..."}]}

    GET https://api.finra.org/partitions/group/otcMarket/name/consolidatedShortInterest
    GET https://api.finra.org/metadata/group/otcMarket/name/consolidatedShortInterest

Historical depth, measured not assumed (this is the "say exactly what is
available" part of the brief): the dataset's own ``metadata`` description says
"Data is available online for one rolling year", but the ``partitions``
endpoint lists **209 settlement dates from 2017-12-29 to 2026-08-31** and
date-filtered queries against 2018 return rows. So:

* **2017-12-29 onward is available** through this API (24 settlement dates per
  year, 16 so far in 2026).
* **2016-01-01 .. 2017-12-28 is not available** from any free FINRA endpoint we
  could find: the settlement dates simply are not in ``availablePartitions``,
  ``https://cdn.finra.org/equity/otcshortinterest/`` returns HTTP 403, and the
  ``otce.finra.org`` static-archive page is a JavaScript shell. The card's
  "2016 →" is therefore truncated to 2017-12-29 →, and every downstream table
  starts in 2018. Nothing is back-filled or interpolated.

Publication (visibility) dates
------------------------------
The API rows carry ``settlementDate`` only -- the date the positions are *as
of*, which is roughly a week and a half before anyone outside FINRA can see
them. Using it as a visibility date would be a pure look-ahead, so this
collector resolves a real publication date two ways, in this order:

1. **The official schedule**, scraped from FINRA's own "Short Interest
   Reporting" page (``--schedule`` stage), which publishes a
   settlement-date / due-date / **publication-date** table. The live page
   carries the current and next calendar year (28 rows as of 2026-09-17).
2. **The rule those rows imply**, for every earlier settlement date:
   ``publication_date = the 7th US-equity session after settlement_date``.
   The ``schedule`` stage *validates* this against all 28 official rows and
   refuses to continue if any row disagrees, so the rule is measured, not
   guessed. FINRA's prose ("roughly eight business days") is consistent with
   it: visibility is one further session after publication.

``visible_date`` = the next US equity session **after** ``publication_date``.
FINRA's publication is not timestamped on the page, so nothing may condition
on a record during its own publication session. This is the same conservative
convention ``events.sec_form4_insider`` uses for ``FILING_DATE``.

Terms of use
------------
FINRA's data pages state that FINRA Data provides **non-commercial use** of
data. This repo's use is personal research, which is inside that; the
restriction is recorded in the capability's caveats and must stay there.

Stages (each resumable; rerunning skips finished work)
------------------------------------------------------
``schedule``
    Fetch the FINRA "Short Interest Reporting" page into
    ``data/raw/finra_short_interest/schedule/short-interest-reporting.html``,
    parse the official publication table into
    ``data/raw/finra_short_interest/publication_schedule.csv`` and validate the
    7-session rule against it.
``download``
    One gzipped CSV per settlement date under
    ``data/raw/finra_short_interest/consolidated/{yyyy-mm-dd}.csv.gz``, paged
    5,000 rows at a time (the API's ``record-max-limit``). An existing
    non-empty file whose row count matches the API's ``record-total`` is
    skipped.
``parse``
    Stream every raw file into ``data/raw/finra_short_interest/parsed.parquet``
    (one row group per settlement date, so peak memory is one settlement date)
    with the normalized schema in :data:`PARSED_COLUMNS`, plus
    ``publication_date``, ``publication_date_source``, ``visible_date``,
    ``source``, ``fetched_at`` and ``input_hash`` (sha256 of the raw file the
    row came from).
``manifest``
    Rewrite ``data/raw/finra_short_interest/manifest.json`` from what is on
    disk. ``parse`` calls it for you.

Usage::

    ./scripts/run_capped.sh --mem 1.8G -- \\
        uv run python scripts/collect_finra_short_interest.py --stage schedule

    nohup ./scripts/run_capped.sh --mem 1.8G -- \\
        uv run python scripts/collect_finra_short_interest.py \\
        --stage download > /tmp/finra_si_download.log 2>&1 &

    ./scripts/run_capped.sh --mem 1.8G -- \\
        uv run python scripts/collect_finra_short_interest.py --stage parse
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import html
import io
import json
import re
import sys
import time
from datetime import UTC, date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402

from open_composer.market_calendar import (  # noqa: E402
    next_us_equity_session,
    us_equity_session_dates,
)

RAW_ROOT = ROOT / "data" / "raw" / "finra_short_interest"
CONSOLIDATED_ROOT = RAW_ROOT / "consolidated"
SCHEDULE_ROOT = RAW_ROOT / "schedule"
SCHEDULE_CSV = RAW_ROOT / "publication_schedule.csv"
PARSED_PATH = RAW_ROOT / "parsed.parquet"
MANIFEST_PATH = RAW_ROOT / "manifest.json"

API_BASE = "https://api.finra.org"
DATASET_GROUP = "otcMarket"
DATASET_NAME = "consolidatedShortInterest"
DATA_URL = f"{API_BASE}/data/group/{DATASET_GROUP}/name/{DATASET_NAME}"
PARTITIONS_URL = f"{API_BASE}/partitions/group/{DATASET_GROUP}/name/{DATASET_NAME}"
METADATA_URL = f"{API_BASE}/metadata/group/{DATASET_GROUP}/name/{DATASET_NAME}"
SCHEDULE_URL = "https://www.finra.org/filing-reporting/regulatory-filing-systems/short-interest"

SOURCE_ID = f"finra_query_api:{DATASET_GROUP}/{DATASET_NAME}"

#: The API's own ``record-max-limit`` header value.
PAGE_LIMIT = 5000
MIN_REQUEST_INTERVAL_SECONDS = 0.35
HTTP_TIMEOUT_SECONDS = 180

#: The first settlement date the free API exposes (measured, see the module
#: docstring). Requests before this return nothing; the card's nominal 2016
#: start cannot be honoured.
FIRST_AVAILABLE_SETTLEMENT = date(2017, 12, 29)

#: Publication lag implied by (and validated against) FINRA's official
#: settlement/publication table, in US equity sessions.
PUBLICATION_LAG_SESSIONS = 7

#: Raw API field -> normalized column.
FIELD_RENAME: dict[str, str] = {
    "symbolCode": "symbol",
    "issueName": "issue_name",
    "settlementDate": "settlement_date",
    "marketClassCode": "market_class_code",
    "issuerServicesGroupExchangeCode": "issuer_services_group_exchange_code",
    "currentShortPositionQuantity": "short_interest_shares",
    "previousShortPositionQuantity": "previous_short_interest_shares",
    "averageDailyVolumeQuantity": "average_daily_volume",
    "daysToCoverQuantity": "days_to_cover",
    "changePercent": "change_percent",
    "changePreviousNumber": "change_previous_shares",
    "stockSplitFlag": "stock_split_flag",
    "revisionFlag": "revision_flag",
}

#: Normalized parsed schema, in table order. One row per
#: (settlement_date, symbol).
PARSED_COLUMNS: tuple[str, ...] = (
    "settlement_date",
    "publication_date",
    "visible_date",
    "symbol",
    "short_interest_shares",
    "average_daily_volume",
    "days_to_cover",
    "previous_short_interest_shares",
    "change_percent",
    "change_previous_shares",
    "market_class_code",
    "issuer_services_group_exchange_code",
    "stock_split_flag",
    "revision_flag",
    "issue_name",
    "publication_date_source",
    "source",
    "fetched_at",
    "input_hash",
)

NUMERIC_COLUMNS: tuple[str, ...] = (
    "short_interest_shares",
    "average_daily_volume",
    "days_to_cover",
    "previous_short_interest_shares",
    "change_percent",
    "change_previous_shares",
)

STRING_COLUMNS: tuple[str, ...] = (
    "symbol",
    "market_class_code",
    "issuer_services_group_exchange_code",
    "stock_split_flag",
    "revision_flag",
    "issue_name",
    "publication_date_source",
    "source",
    "input_hash",
)


#: Every numeric column stays float64 and every flag stays string even when a
#: single settlement date happens to contain only integers, or only nulls, in a
#: column. ``parse`` streams one row group per settlement date into a single
#: parquet file, and pyarrow refuses to append a row group whose inferred
#: schema differs from the file's -- which is exactly what happened on the
#: first run: ``revision_flag`` is all-null in 2018 (inferred ``null``) and a
#: string from 2021 on, and ``short_interest_shares`` is integral on some dates
#: and not on others. Pinning the schema also means a reader never has to
#: guess whether a 0 is an integer count or a coerced null.
def parsed_schema() -> object:
    import pyarrow as pa

    fields = []
    for column in PARSED_COLUMNS:
        if column in {"settlement_date", "publication_date", "visible_date"}:
            fields.append(pa.field(column, pa.timestamp("s")))
        elif column == "fetched_at":
            fields.append(pa.field(column, pa.timestamp("us", tz="UTC")))
        elif column in NUMERIC_COLUMNS:
            fields.append(pa.field(column, pa.float64()))
        else:
            fields.append(pa.field(column, pa.string()))
    return pa.schema(fields)


MONTHS = {
    "January": 1,
    "February": 2,
    "March": 3,
    "April": 4,
    "May": 5,
    "June": 6,
    "July": 7,
    "August": 8,
    "September": 9,
    "October": 10,
    "November": 11,
    "December": 12,
}


def log(message: str) -> None:
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{stamp}] {message}", flush=True)


# --------------------------------------------------------------------------
# HTTP
# --------------------------------------------------------------------------


class FinraClient:
    """Serialized, rate-limited FINRA client.

    No credential of any kind is read: the ``otcMarket`` group's data,
    partitions and metadata endpoints are open. That is why this collector has
    no ``env:`` entry in the registry, unlike the SEC ones.
    """

    def __init__(self, *, min_interval: float = MIN_REQUEST_INTERVAL_SECONDS) -> None:
        import httpx

        self._min_interval = min_interval
        self._last_request = 0.0
        self._client = httpx.Client(
            headers={
                "User-Agent": "open-composer-research/1.0 (personal research; non-commercial)",
                "Accept-Encoding": "gzip, deflate",
            },
            timeout=HTTP_TIMEOUT_SECONDS,
            follow_redirects=True,
        )

    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_request
        if elapsed < self._min_interval:
            time.sleep(self._min_interval - elapsed)
        self._last_request = time.monotonic()

    def get(self, url: str, *, retries: int = 4) -> tuple[int, bytes, dict[str, str]]:
        import httpx

        for attempt in range(retries):
            self._throttle()
            try:
                response = self._client.get(url)
            except httpx.HTTPError as exc:
                if attempt == retries - 1:
                    raise
                log(f"  transport error ({type(exc).__name__}), retry {attempt + 1}/{retries}")
                time.sleep(2.0 * (attempt + 1))
                continue
            if response.status_code in {403, 429, 500, 502, 503, 504}:
                if attempt == retries - 1:
                    return response.status_code, response.content, dict(response.headers)
                log(f"  HTTP {response.status_code}, backing off (attempt {attempt + 1})")
                time.sleep(5.0 * (attempt + 1))
                continue
            return response.status_code, response.content, dict(response.headers)
        raise RuntimeError("unreachable")

    def post_rows(
        self, payload: dict[str, object], *, retries: int = 4
    ) -> tuple[int, bytes, dict[str, str]]:
        import httpx

        for attempt in range(retries):
            self._throttle()
            try:
                response = self._client.post(
                    DATA_URL,
                    json=payload,
                    headers={"Accept": "text/plain", "Content-Type": "application/json"},
                )
            except httpx.HTTPError as exc:
                if attempt == retries - 1:
                    raise
                log(f"  transport error ({type(exc).__name__}), retry {attempt + 1}/{retries}")
                time.sleep(2.0 * (attempt + 1))
                continue
            if response.status_code in {403, 429, 500, 502, 503, 504}:
                if attempt == retries - 1:
                    return response.status_code, response.content, dict(response.headers)
                log(f"  HTTP {response.status_code}, backing off (attempt {attempt + 1})")
                time.sleep(5.0 * (attempt + 1))
                continue
            return response.status_code, response.content, dict(response.headers)
        raise RuntimeError("unreachable")

    def close(self) -> None:
        self._client.close()


# --------------------------------------------------------------------------
# publication schedule
# --------------------------------------------------------------------------


def parse_official_schedule(page_html: str) -> pd.DataFrame:
    """The official ``(settlement_date, due_date, publication_date)`` rows from
    FINRA's "Short Interest Reporting" page.

    The page renders one HTML table per calendar year, each headed
    ``"{year} Short Interest Reporting Dates"``, with month-day cells that
    carry no year ("December 31 (Wednesday)" / "January 12 (Monday)"). The
    year comes from the heading, and a cell whose month is *earlier* than the
    settlement month rolls into the next year -- which is exactly the
    December-settlement / January-publication pair, the one row where getting
    this wrong would put visibility a year early.
    """
    text = re.sub(r"<script.*?</script>", " ", page_html, flags=re.S)
    text = re.sub(r"<style.*?</style>", " ", text, flags=re.S)
    # Collapse the document's own line breaks *before* introducing row breaks:
    # the live page happens to emit one ``<tr>`` per source line, but nothing
    # guarantees that, and a row split across source lines would otherwise
    # parse as two unusable half-rows.
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"</t[dh]>", "|", text)
    text = re.sub(r"</tr>", "\n", text)
    text = html.unescape(re.sub(r"<[^>]+>", "", text))
    rows: list[dict[str, object]] = []
    year: int | None = None
    for line in text.split("\n"):
        line = re.sub(r"[ \t ]+", " ", line).strip()
        heading = re.search(r"(\d{4}) Short Interest Reporting Dates", line)
        if heading:
            year = int(heading.group(1))
            line = line[heading.end() :]
        if year is None or "|" not in line:
            continue
        cells = [cell.strip() for cell in line.split("|")]
        parsed = [_month_day(cell) for cell in cells[:3]]
        if len(parsed) < 3 or any(item is None for item in parsed):
            continue
        settlement_month, settlement_day = parsed[0]  # type: ignore[misc]
        settlement = date(year, settlement_month, settlement_day)
        due = _roll_year(parsed[1], settlement)  # type: ignore[arg-type]
        publication = _roll_year(parsed[2], settlement)  # type: ignore[arg-type]
        rows.append(
            {
                "settlement_date": settlement,
                "due_date": due,
                "publication_date": publication,
                "source": "finra_official_schedule_page",
            }
        )
    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame
    return frame.drop_duplicates(subset=["settlement_date"], keep="last").sort_values(
        "settlement_date", ignore_index=True
    )


def _month_day(cell: str) -> tuple[int, int] | None:
    match = re.match(r"([A-Z][a-z]+)\s*(\d{1,2})\b", cell)
    if not match or match.group(1) not in MONTHS:
        return None
    return MONTHS[match.group(1)], int(match.group(2))


def _roll_year(month_day: tuple[int, int], settlement: date) -> date:
    month, day = month_day
    year = settlement.year + 1 if month < settlement.month else settlement.year
    return date(year, month, day)


def publication_date_from_rule(
    settlement: date, *, lag_sessions: int = PUBLICATION_LAG_SESSIONS
) -> date:
    """``lag_sessions`` US equity sessions after ``settlement``.

    Uses the exchange calendar, not a banking calendar: FINRA's own 2026 rows
    skip Good Friday (2026-04-03), which is a market holiday but not a federal
    one, so the exchange calendar is the one that reproduces them.
    """
    day = settlement
    for _ in range(lag_sessions):
        day = next_us_equity_session(day)
    return day


def validate_rule_against_official(official: pd.DataFrame) -> dict[str, object]:
    """Does ``publication_date_from_rule`` reproduce every official row?"""
    mismatches: list[dict[str, str]] = []
    for row in official.itertuples():
        predicted = publication_date_from_rule(row.settlement_date)
        if predicted != row.publication_date:
            mismatches.append(
                {
                    "settlement_date": row.settlement_date.isoformat(),
                    "official_publication_date": row.publication_date.isoformat(),
                    "rule_publication_date": predicted.isoformat(),
                }
            )
    return {
        "official_rows": int(len(official)),
        "lag_sessions": PUBLICATION_LAG_SESSIONS,
        "mismatches": mismatches,
        "agrees": not mismatches,
    }


def load_schedule() -> tuple[dict[date, date], dict[str, object]]:
    """``({settlement_date: official publication_date}, validation)``.

    Empty mapping when the ``schedule`` stage has not been run, in which case
    every row falls back to the rule and says so in
    ``publication_date_source``.
    """
    if not SCHEDULE_CSV.exists():
        return {}, {"official_rows": 0, "agrees": None, "mismatches": []}
    frame = pd.read_csv(SCHEDULE_CSV, parse_dates=["settlement_date", "publication_date"])
    mapping = {
        row.settlement_date.date(): row.publication_date.date() for row in frame.itertuples()
    }
    official = pd.DataFrame(
        {
            "settlement_date": [key for key in mapping],
            "publication_date": [value for value in mapping.values()],
        }
    )
    return mapping, validate_rule_against_official(official)


def stage_schedule(client: FinraClient, *, force: bool) -> int:
    SCHEDULE_ROOT.mkdir(parents=True, exist_ok=True)
    page_path = SCHEDULE_ROOT / "short-interest-reporting.html"
    if page_path.exists() and not force:
        log(f"{page_path.name}: already present -- reusing (checkpoint)")
        page_html = page_path.read_text(encoding="utf-8", errors="replace")
    else:
        status, payload, _ = client.get(SCHEDULE_URL)
        if status != 200:
            log(f"schedule page: HTTP {status} -- cannot refresh the official table")
            return 1
        page_path.write_bytes(payload)
        page_html = payload.decode("utf-8", errors="replace")
        log(f"wrote {page_path.relative_to(ROOT)} ({len(payload):,} bytes)")

    official = parse_official_schedule(page_html)
    if official.empty:
        log("schedule page parsed to 0 rows -- the page layout changed; not overwriting")
        return 1
    validation = validate_rule_against_official(official)
    official.to_csv(SCHEDULE_CSV, index=False)
    log(
        f"wrote {SCHEDULE_CSV.relative_to(ROOT)}: {len(official)} official rows "
        f"{official['settlement_date'].min()}..{official['settlement_date'].max()}"
    )
    if validation["agrees"]:
        log(
            f"publication-date rule validated: settlement + {PUBLICATION_LAG_SESSIONS} US "
            f"sessions reproduces all {validation['official_rows']} official rows"
        )
        return 0
    log(f"publication-date rule DISAGREES with the official table: {validation['mismatches']}")
    return 1


# --------------------------------------------------------------------------
# stage: download
# --------------------------------------------------------------------------


def available_settlement_dates(client: FinraClient) -> list[date]:
    status, payload, _ = client.get(PARTITIONS_URL)
    if status != 200:
        raise SystemExit(f"partitions endpoint returned HTTP {status}")
    data = json.loads(payload)
    dates: list[date] = []
    for item in data.get("availablePartitions", []):
        for value in item.get("partitions", []):
            dates.append(date.fromisoformat(str(value)[:10]))
    return sorted(set(dates))


def _raw_path(settlement: date) -> Path:
    return CONSOLIDATED_ROOT / f"{settlement.isoformat()}.csv.gz"


def _raw_row_count(path: Path) -> int:
    if not path.exists() or path.stat().st_size == 0:
        return -1
    with gzip.open(path, "rt", encoding="utf-8", newline="") as handle:
        return max(sum(1 for _ in handle) - 1, 0)


def download_settlement_date(client: FinraClient, settlement: date) -> tuple[str, int]:
    """``(outcome, rows)`` for one settlement date, written atomically."""
    path = _raw_path(settlement)
    payload_base: dict[str, object] = {
        "dateRangeFilters": [
            {
                "fieldName": "settlementDate",
                "startDate": settlement.isoformat(),
                "endDate": settlement.isoformat(),
            }
        ]
    }
    status, _, headers = client.post_rows({**payload_base, "limit": 1, "offset": 0})
    if status != 200:
        return f"http_{status}", 0
    expected = int(headers.get("record-total", 0))
    existing = _raw_row_count(path)
    if existing == expected and expected > 0:
        return "skip_complete", existing
    header_line: str | None = None
    body: list[str] = []
    offset = 0
    while offset < expected:
        status, payload, _ = client.post_rows(
            {**payload_base, "limit": PAGE_LIMIT, "offset": offset}
        )
        if status != 200:
            return f"http_{status}", 0
        chunk = payload.decode("utf-8", errors="replace").splitlines()
        if not chunk:
            break
        if header_line is None:
            header_line = chunk[0]
        body.extend(chunk[1:])
        if len(chunk) - 1 <= 0:
            break
        offset += PAGE_LIMIT
    if header_line is None:
        return "empty", 0
    CONSOLIDATED_ROOT.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".gz.part")
    with gzip.open(temporary, "wt", encoding="utf-8", newline="\n") as handle:
        handle.write(header_line + "\n")
        for line in body:
            handle.write(line + "\n")
    temporary.replace(path)
    if len(body) != expected:
        return f"partial_{len(body)}_of_{expected}", len(body)
    return "ok", len(body)


def stage_download(client: FinraClient, *, start: date, end: date | None) -> int:
    settlement_dates = [
        value
        for value in available_settlement_dates(client)
        if value >= start and (end is None or value <= end)
    ]
    log(
        f"{len(settlement_dates)} settlement-date partitions in range "
        f"{settlement_dates[0] if settlement_dates else '-'}.."
        f"{settlement_dates[-1] if settlement_dates else '-'}"
    )
    failures = 0
    for index, settlement in enumerate(settlement_dates, start=1):
        outcome, rows = download_settlement_date(client, settlement)
        if outcome not in {"ok", "skip_complete"}:
            failures += 1
        log(f"[{index}/{len(settlement_dates)}] {settlement}: {outcome} rows={rows:,}")
    log(f"download finished with {failures} non-ok settlement dates")
    return 1 if failures else 0


# --------------------------------------------------------------------------
# stage: parse
# --------------------------------------------------------------------------


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def parse_raw_file(
    path: Path,
    *,
    publication_schedule: dict[date, date],
    lag_sessions: int,
) -> pd.DataFrame:
    """One raw settlement-date file as the normalized :data:`PARSED_COLUMNS`."""
    settlement = date.fromisoformat(path.name.split(".")[0])
    with gzip.open(path, "rt", encoding="utf-8", newline="") as handle:
        frame = pd.read_csv(io.StringIO(handle.read()), dtype=str)
    frame = frame.rename(columns=FIELD_RENAME)
    for column in PARSED_COLUMNS:
        if column not in frame.columns:
            frame[column] = None
    frame["settlement_date"] = pd.Timestamp(settlement)
    official = publication_schedule.get(settlement)
    if official is not None:
        publication = official
        publication_source = "finra_official_schedule_page"
    else:
        publication = publication_date_from_rule(settlement, lag_sessions=lag_sessions)
        publication_source = f"rule_settlement_plus_{lag_sessions}_sessions"
    frame["publication_date"] = pd.Timestamp(publication)
    frame["publication_date_source"] = publication_source
    frame["visible_date"] = pd.Timestamp(next_us_equity_session(publication))
    for column in NUMERIC_COLUMNS:
        frame[column] = pd.to_numeric(frame[column], errors="coerce").astype("float64")
    frame["symbol"] = frame["symbol"].astype(str).str.strip().str.upper()
    frame["source"] = SOURCE_ID
    frame["fetched_at"] = pd.Timestamp(datetime.fromtimestamp(path.stat().st_mtime, tz=UTC))
    frame["input_hash"] = _file_hash(path)
    frame = frame.loc[frame["symbol"].str.len() > 0]
    frame = frame.drop_duplicates(subset=["settlement_date", "symbol"], keep="last")
    for column in STRING_COLUMNS:
        frame[column] = frame[column].astype("string")
    return frame[list(PARSED_COLUMNS)].sort_values("symbol", ignore_index=True)


def stage_parse(*, force: bool, lag_sessions: int) -> int:
    import pyarrow as pa
    import pyarrow.parquet as pq

    if PARSED_PATH.exists() and not force:
        log(f"{PARSED_PATH.name}: already present -- rerun with --force to rebuild")
        return stage_manifest()
    publication_schedule, validation = load_schedule()
    if not publication_schedule:
        log("no publication_schedule.csv -- every row will use the documented rule lag")
    elif validation["agrees"] is False:
        log("publication schedule disagrees with the rule; run --stage schedule first")
        return 1
    paths = sorted(CONSOLIDATED_ROOT.glob("*.csv.gz"))
    if not paths:
        log(f"no raw files under {CONSOLIDATED_ROOT.relative_to(ROOT)} -- run --stage download")
        return 1
    temporary = PARSED_PATH.with_suffix(".parquet.part")
    schema = parsed_schema()
    writer: pq.ParquetWriter | None = None
    total = 0
    try:
        for index, path in enumerate(paths, start=1):
            frame = parse_raw_file(
                path, publication_schedule=publication_schedule, lag_sessions=lag_sessions
            )
            table = pa.Table.from_pandas(frame, schema=schema, preserve_index=False)
            if writer is None:
                writer = pq.ParquetWriter(temporary, schema, compression="zstd")
            writer.write_table(table)
            total += len(frame)
            if index % 20 == 0 or index == len(paths):
                log(f"[{index}/{len(paths)}] {path.stem}: {total:,} rows so far")
    finally:
        if writer is not None:
            writer.close()
    temporary.replace(PARSED_PATH)
    log(f"wrote {PARSED_PATH.relative_to(ROOT)}: {total:,} rows from {len(paths)} settlement dates")
    return stage_manifest()


# --------------------------------------------------------------------------
# stage: manifest
# --------------------------------------------------------------------------


def stage_manifest() -> int:
    paths = sorted(CONSOLIDATED_ROOT.glob("*.csv.gz"))
    files = [
        {
            "settlement_date": path.stem.split(".")[0],
            "bytes": path.stat().st_size,
            "rows": _raw_row_count(path),
            "sha256": _file_hash(path),
        }
        for path in paths
    ]
    _, validation = load_schedule()
    parsed_rows: int | None = None
    parsed_span: list[str] | None = None
    if PARSED_PATH.exists():
        import pyarrow.parquet as pq

        parsed = pq.ParquetFile(PARSED_PATH)
        parsed_rows = parsed.metadata.num_rows
        dates = pd.read_parquet(PARSED_PATH, columns=["settlement_date"])["settlement_date"]
        parsed_span = [str(dates.min().date()), str(dates.max().date())]
    payload = {
        "capability": "market.finra_short_interest",
        "dataset": f"{DATASET_GROUP}/{DATASET_NAME}",
        "source": SOURCE_ID,
        "data_url": DATA_URL,
        "partitions_url": PARTITIONS_URL,
        "metadata_url": METADATA_URL,
        "schedule_url": SCHEDULE_URL,
        "terms": "FINRA states non-commercial use of FINRA Data; personal research only",
        "generated_at": pd.Timestamp.now(tz="UTC").isoformat(),
        "first_available_settlement_date": FIRST_AVAILABLE_SETTLEMENT.isoformat(),
        "availability_note": (
            "the free FINRA Query API exposes settlement dates from 2017-12-29 onward only; "
            "2016-01-01..2017-12-28 is not downloadable from any free FINRA endpoint found "
            "(cdn.finra.org/equity/otcshortinterest returns 403, otce.finra.org static "
            "archives is a JavaScript shell), so the card's 2016 start is truncated"
        ),
        "publication_lag_sessions": PUBLICATION_LAG_SESSIONS,
        "publication_rule_validation": validation,
        "visibility_rule": "next US equity session after publication_date",
        "settlement_dates": len(files),
        "raw_rows": sum(item["rows"] for item in files if item["rows"] > 0),
        "parsed_rows": parsed_rows,
        "parsed_settlement_span": parsed_span,
        "files": files,
    }
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    log(
        f"wrote {MANIFEST_PATH.relative_to(ROOT)}: {len(files)} settlement dates, "
        f"{payload['raw_rows']:,} raw rows, parsed_rows={parsed_rows}"
    )
    return 0


# --------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--stage",
        required=True,
        choices=["schedule", "download", "parse", "manifest", "probe"],
    )
    parser.add_argument(
        "--start",
        default=FIRST_AVAILABLE_SETTLEMENT.isoformat(),
        help="first settlement date to download (default: the earliest the API exposes)",
    )
    parser.add_argument("--end", default=None, help="last settlement date to download")
    parser.add_argument(
        "--publication-lag-sessions",
        type=int,
        default=PUBLICATION_LAG_SESSIONS,
        help="sessions between settlement and publication for dates the official table "
        "does not cover; a sensitivity knob, not a tuning parameter",
    )
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)

    RAW_ROOT.mkdir(parents=True, exist_ok=True)
    if args.stage == "manifest":
        return stage_manifest()
    if args.stage == "parse":
        return stage_parse(force=args.force, lag_sessions=args.publication_lag_sessions)

    client = FinraClient()
    try:
        if args.stage == "schedule":
            return stage_schedule(client, force=args.force)
        if args.stage == "probe":
            status, payload, _ = client.get(METADATA_URL)
            log(f"metadata HTTP {status}: {payload[:400]!r}")
            dates = available_settlement_dates(client)
            log(f"{len(dates)} settlement dates, {dates[0]}..{dates[-1]}")
            sessions = us_equity_session_dates(dates[0], dates[-1])
            log(f"calendar sanity: {len(sessions)} US sessions across that span")
            return 0
        return stage_download(
            client,
            start=date.fromisoformat(args.start),
            end=date.fromisoformat(args.end) if args.end else None,
        )
    finally:
        client.close()


if __name__ == "__main__":
    raise SystemExit(main())
