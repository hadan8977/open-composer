"""T1 (plan-earnings-text-forward-test-2026-09-22): point-in-time earnings-event
table built from SEC EDGAR.

Card: ``docs/plan-earnings-text-forward-test-2026-09-22.zh.md`` section 1 (row
T1) / section 2 (data sources) / section 4 (evaluation rules -- T1 only
supplies the event table those rules run on, it applies no evaluation logic
itself).

What this collects
-------------------
Every 8-K filing with Item 2.02 ("Results of Operations and Financial
Condition") from ``--start`` (default 2024-01-01) to ``--end`` (default
today) for the union of tickers in the broad liquid universe
(``data/features/universe_broad/{year}.parquet``, month-end cohorts, top
``--top-n`` symbols per cohort by ``adv_rank``), with the one timestamp that
makes this table point-in-time: the submissions API's
``acceptanceDateTime``. For each matching filing this also fetches the
earnings-release exhibit (EX-99.1, or EX-99.2 when its filing-index
description mentions results/earnings/quarter) and stores plain text with
HTML tags and tables stripped.

Sources (all free, all cited from the plan doc section 2)
----------------------------------------------------------
``https://www.sec.gov/files/company_tickers.json``
    Current ticker -> CIK map. This has no history, so a ticker that does
    not resolve here (renamed/delisted/never listed under SEC's current
    map) is written to ``unresolved_tickers.json`` instead of being guessed.
``https://data.sec.gov/submissions/CIK##########.json``
    Per-company filing history: ``filings.recent.{accessionNumber,
    acceptanceDateTime, form, items}`` (parallel arrays) plus
    ``filings.files[]`` pages for companies with long histories.
``https://www.sec.gov/Archives/edgar/data/{cik}/{accession_nodash}/{accession}-index.htm``
    The filing's document table (Seq/Description/Document/Type/Size), used
    to pick the exhibit and resolve its relative URL.

Point-in-time note: EDGAR's ``acceptanceDateTime`` string carries a literal
"Z" suffix but the wall-clock value is Eastern local time, not UTC (a
long-standing EDGAR quirk -- see the ``_EASTERN`` comment below). This
script converts it properly via ``zoneinfo`` so ``acceptance_utc`` is a real
UTC instant across the EST/EDT boundary; verify this on the pilot's 30 rows
against a couple of independently known release times before trusting it.

SEC fair access
----------------
User-Agent is the fixed string ``"open-composer research
hzc43021@gmail.com"`` (no ``.env`` is read here). Requests are strictly
serialized with a minimum inter-request interval enforcing <= 8 req/s, and
429/500/502/503/504 responses get exponential backoff and a retry.

Idempotency / resume
---------------------
Exhibit text is cached at ``data/raw/earnings_text/{cik}/{accession}.txt``;
if that file already exists and is non-empty, this run reuses it (fetch
status ``"cached"``) instead of re-fetching. The per-year output parquet is
loaded, merged (new rows replace old rows with the same accession) and
rewritten, so reruns and ``--limit`` pilots are safe to repeat or extend.

Usage
-----
Pilot (verify by hand before the full run)::

    ./scripts/run_capped.sh --mem 1.8G -- ./.venv/bin/python \\
        scripts/build_earnings_events.py --limit 30

Full run, detached, log tailable::

    nohup ./scripts/run_capped.sh --mem 1.8G -- ./.venv/bin/python \\
        scripts/build_earnings_events.py \\
        > logs/build_earnings_events.log 2>&1 &
    tail -f logs/build_earnings_events.log
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import sys
import time
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]

UNIVERSE_DIR = ROOT / "data" / "features" / "universe_broad"
OUT_DIR = ROOT / "data" / "features" / "earnings_events"
UNRESOLVED_PATH = OUT_DIR / "unresolved_tickers.json"
RAW_TEXT_ROOT = ROOT / "data" / "raw" / "earnings_text"
RAW_CACHE_ROOT = ROOT / "data" / "raw" / "earnings_text" / "_cache"
COMPANY_TICKERS_CACHE = RAW_CACHE_ROOT / "company_tickers.json"

USER_AGENT = "open-composer research hzc43021@gmail.com"
COMPANY_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik10}.json"
SUBMISSIONS_FILE_URL = "https://data.sec.gov/submissions/{name}"
ARCHIVES_BASE = "https://www.sec.gov/Archives/edgar/data/{cik}/{accession_nodash}/"

#: >= 8 requests/second ceiling -> minimum 0.125s between requests. Kept
#: strictly below the plan doc's 10 req/s SEC limit.
MIN_REQUEST_INTERVAL_SECONDS = 1.0 / 8.0
HTTP_TIMEOUT_SECONDS = 30.0
RETRYABLE_STATUS = {403, 429, 500, 502, 503, 504}
MAX_RETRIES = 5

REQUIRED_FORM = "8-K"
REQUIRED_ITEM = "2.02"

#: EDGAR's submissions API stamps ``acceptanceDateTime`` with a trailing
#: "Z" as if it were UTC, but the wall-clock value is US Eastern local time
#: (observed across every EDGAR full-text-search and submissions payload;
#: acceptance windows close at 17:30 ET / 22:00 or 21:00 "Z" depending on
#: season, which only makes sense as an Eastern-local stamp). Treat the
#: naive value as America/New_York and convert properly so DST transitions
#: don't shift accepted-before/after-hours classification by an hour.
_EASTERN = ZoneInfo("America/New_York")

_EX99_TYPE_RE = re.compile(r"^EX-?99(\.(\d+))?$", re.IGNORECASE)
_EX99_KEYWORD_RE = re.compile(r"results|earnings|quarter", re.IGNORECASE)

_TABLE_RE = re.compile(r"(?is)<table\b.*?</table>")
_SCRIPT_STYLE_RE = re.compile(r"(?is)<(script|style)\b.*?</\1>")
_BLOCK_BREAK_RE = re.compile(r"(?is)<br\s*/?>|</?(?:p|div|tr|li|h[1-6])(?:\s[^>]*)?>")
_TAG_RE = re.compile(r"(?s)<[^>]+>")
_WS_RE = re.compile("[ \t\u00a0]+")
_MULTI_NEWLINE_RE = re.compile(r"\n{3,}")

_ROW_RE = re.compile(r"(?is)<tr[^>]*>(.*?)</tr>")
_CELL_RE = re.compile(r"(?is)<t[dh][^>]*>(.*?)</t[dh]>")
_HREF_RE = re.compile(r'(?is)href="([^"]+)"')
_DOC_TABLE_RE = re.compile(r'(?is)<table[^>]*class="tableFile"[^>]*>(.*?)</table>')


def log(message: str) -> None:
    stamp = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"[{stamp}] {message}", flush=True)


# --------------------------------------------------------------------------
# HTTP client (serialized, rate-limited, retrying)
# --------------------------------------------------------------------------


class SecClient:
    def __init__(self, *, min_interval: float = MIN_REQUEST_INTERVAL_SECONDS) -> None:
        import httpx

        self._min_interval = min_interval
        self._last_request = 0.0
        self._client = httpx.Client(
            headers={"User-Agent": USER_AGENT, "Accept-Encoding": "gzip, deflate"},
            timeout=HTTP_TIMEOUT_SECONDS,
            follow_redirects=True,
        )

    def get(self, url: str, *, retries: int = MAX_RETRIES) -> tuple[int, bytes]:
        import httpx

        for attempt in range(retries):
            elapsed = time.monotonic() - self._last_request
            if elapsed < self._min_interval:
                time.sleep(self._min_interval - elapsed)
            self._last_request = time.monotonic()
            try:
                response = self._client.get(url)
            except httpx.HTTPError as exc:
                if attempt == retries - 1:
                    raise
                log(
                    f"  transport error ({type(exc).__name__}) on {url}, "
                    f"retry {attempt + 1}/{retries}"
                )
                time.sleep(2.0 * (attempt + 1))
                continue
            if response.status_code in RETRYABLE_STATUS:
                if attempt == retries - 1:
                    return response.status_code, response.content
                log(f"  HTTP {response.status_code} on {url}, backing off (attempt {attempt + 1})")
                time.sleep(5.0 * (attempt + 1))
                continue
            return response.status_code, response.content
        raise RuntimeError("unreachable")

    def close(self) -> None:
        self._client.close()


# --------------------------------------------------------------------------
# Universe -> tickers -> CIK
# --------------------------------------------------------------------------


def load_universe_symbols(start: date, end: date, *, top_n: int) -> list[str]:
    """Union of top-``top_n`` (by ``adv_rank``) symbols across every
    month-end cohort in ``[start, end]``, read from the year-partitioned
    broad universe parquet files."""

    symbols: set[str] = set()
    for year in range(start.year, end.year + 1):
        path = UNIVERSE_DIR / f"{year}.parquet"
        if not path.exists():
            continue
        df = pd.read_parquet(path, columns=["month_end", "symbol", "adv_rank"])
        df = df[(df["month_end"] >= pd.Timestamp(start)) & (df["month_end"] <= pd.Timestamp(end))]
        df = df[df["adv_rank"] <= top_n]
        symbols.update(df["symbol"].astype(str).tolist())
    return sorted(symbols)


def load_company_tickers(client: SecClient, *, refresh: bool) -> dict[str, str]:
    """``{TICKER: "0000320193"}`` (10-digit zero-padded CIK) from SEC's
    current ticker map. Cached locally under ``data/raw`` (gitignored,
    refetchable) so repeated pilot/full runs don't repeat this request."""

    if not refresh and COMPANY_TICKERS_CACHE.exists():
        payload = json.loads(COMPANY_TICKERS_CACHE.read_text())
    else:
        status, content = client.get(COMPANY_TICKERS_URL)
        if status != 200:
            if COMPANY_TICKERS_CACHE.exists():
                log(f"company_tickers.json fetch failed (HTTP {status}); using stale cache")
                payload = json.loads(COMPANY_TICKERS_CACHE.read_text())
            else:
                raise RuntimeError(f"company_tickers.json fetch failed: HTTP {status}")
        else:
            payload = json.loads(content)
            RAW_CACHE_ROOT.mkdir(parents=True, exist_ok=True)
            COMPANY_TICKERS_CACHE.write_text(json.dumps(payload))
    mapping: dict[str, str] = {}
    for row in payload.values():
        ticker = str(row.get("ticker", "")).strip().upper()
        cik = row.get("cik_str")
        if not ticker or cik is None:
            continue
        mapping[ticker] = f"{int(cik):010d}"
    return mapping


def resolve_tickers(
    symbols: list[str], ticker_to_cik: dict[str, str]
) -> tuple[dict[str, str], list[str]]:
    resolved: dict[str, str] = {}
    unresolved: list[str] = []
    for symbol in symbols:
        cik = ticker_to_cik.get(symbol.upper())
        if cik is None:
            unresolved.append(symbol)
        else:
            resolved[symbol] = cik
    return resolved, unresolved


def write_unresolved(unresolved: list[str]) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": COMPANY_TICKERS_URL,
        "note": "Tickers in the broad universe cohorts that do not resolve against SEC's "
        "*current* company_tickers.json map (renamed/delisted/never SEC-registered under "
        "this symbol). Not guessed; left out of the event table.",
        "count": len(unresolved),
        "tickers": sorted(unresolved),
    }
    UNRESOLVED_PATH.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


# --------------------------------------------------------------------------
# Acceptance timestamp
# --------------------------------------------------------------------------


def to_utc_iso(raw: str | None) -> str | None:
    """EDGAR's ``acceptanceDateTime`` (Eastern local, mislabeled with a "Z")
    to a real UTC instant, ISO-8601 with a trailing "Z"."""

    if not raw:
        return None
    text = raw.strip()
    if text.endswith("Z"):
        text = text[:-1]
    try:
        naive = datetime.fromisoformat(text)
    except ValueError:
        return None
    eastern = naive.replace(tzinfo=_EASTERN)
    utc = eastern.astimezone(UTC)
    return utc.strftime("%Y-%m-%dT%H:%M:%SZ")


# --------------------------------------------------------------------------
# Filing selection
# --------------------------------------------------------------------------


def parse_items(items_raw: str | None) -> list[str]:
    if not items_raw:
        return []
    return [part.strip() for part in str(items_raw).split(",") if part.strip()]


def filing_matches(form: str | None, items_raw: str | None) -> bool:
    """The T1 scope filter: form is 8-K and its Items include 2.02."""

    if not form or form.strip().upper() != REQUIRED_FORM:
        return False
    return REQUIRED_ITEM in parse_items(items_raw)


@dataclass
class FilingRow:
    accession: str
    filing_date: str | None
    acceptance_raw: str | None
    form: str | None
    items: str | None
    primary_document: str | None = None


def rows_from_arrays(payload: dict) -> list[FilingRow]:
    """``filings.recent`` (or a ``filings.files[]`` page, same parallel-array
    shape) to a list of per-filing rows."""

    accessions = payload.get("accessionNumber", [])
    n = len(accessions)

    def col(key: str) -> list:
        values = payload.get(key, [])
        if len(values) != n:
            return [None] * n
        return values

    filing_dates = col("filingDate")
    acceptances = col("acceptanceDateTime")
    forms = col("form")
    items = col("items")
    primary_docs = col("primaryDocument")
    return [
        FilingRow(
            accession=accessions[i],
            filing_date=filing_dates[i],
            acceptance_raw=acceptances[i],
            form=forms[i],
            items=items[i],
            primary_document=primary_docs[i],
        )
        for i in range(n)
    ]


def collect_filing_rows(
    client: SecClient, cik10: str, *, start: date
) -> tuple[str | None, list[FilingRow]]:
    """All filing rows for one company, paging back into ``filings.files[]``
    when the ``recent`` window does not reach ``start``."""

    status, content = client.get(SUBMISSIONS_URL.format(cik10=cik10))
    if status != 200:
        log(f"  submissions fetch failed for CIK {cik10}: HTTP {status}")
        return None, []
    payload = json.loads(content)
    company_name = payload.get("name")
    recent = payload.get("filings", {}).get("recent", {})
    rows = rows_from_arrays(recent)

    oldest_date = min((r.filing_date for r in rows if r.filing_date), default=None)
    if oldest_date is not None and oldest_date <= start.isoformat():
        return company_name, rows

    for file_meta in payload.get("filings", {}).get("files", []):
        filing_to = file_meta.get("filingTo")
        if filing_to and filing_to < start.isoformat():
            # This page (and, by construction, every later one) is entirely
            # before the window we need.
            continue
        name = file_meta.get("name")
        if not name:
            continue
        status, content = client.get(SUBMISSIONS_FILE_URL.format(name=name))
        if status != 200:
            log(f"  submissions page fetch failed for {name}: HTTP {status}")
            continue
        page_payload = json.loads(content)
        rows.extend(rows_from_arrays(page_payload))
        filing_from = file_meta.get("filingFrom")
        if filing_from and filing_from <= start.isoformat():
            break
    return company_name, rows


# --------------------------------------------------------------------------
# Exhibit selection and text extraction
# --------------------------------------------------------------------------


@dataclass
class ExhibitCandidate:
    doc_type: str
    description: str
    href: str


def _clean_cell_text(cell_html: str) -> str:
    text = _TAG_RE.sub(" ", cell_html)
    text = html.unescape(text)
    return _WS_RE.sub(" ", text).strip()


def parse_document_table(index_html: str) -> list[ExhibitCandidate]:
    """The filing index page's "Document Format Files" table to a list of
    ``(type, description, href)`` candidates."""

    table_match = _DOC_TABLE_RE.search(index_html)
    if not table_match:
        return []
    body = table_match.group(1)
    candidates: list[ExhibitCandidate] = []
    for row_match in _ROW_RE.finditer(body):
        cells = _CELL_RE.findall(row_match.group(1))
        if len(cells) < 4:
            continue
        # Columns: Seq, Description, Document, Type, Size (Type/Size may be
        # absent for a couple of ancillary rows; skip those defensively).
        description = _clean_cell_text(cells[1])
        document_cell = cells[2]
        doc_type = _clean_cell_text(cells[3]) if len(cells) > 3 else ""
        href_match = _HREF_RE.search(document_cell)
        if not href_match:
            continue
        candidates.append(
            ExhibitCandidate(doc_type=doc_type, description=description, href=href_match.group(1))
        )
    return candidates


def pick_ex99(candidates: list[ExhibitCandidate]) -> ExhibitCandidate | None:
    """EX-99.1 first; otherwise an EX-99.x whose index-page description
    mentions results/earnings/quarter (the plan's fallback rule)."""

    def is_ex99(candidate: ExhibitCandidate) -> re.Match | None:
        return _EX99_TYPE_RE.match(candidate.doc_type.strip())

    ex99_candidates = [c for c in candidates if is_ex99(c)]
    for candidate in ex99_candidates:
        match = _EX99_TYPE_RE.match(candidate.doc_type.strip())
        if match and match.group(2) == "1":
            return candidate
    for candidate in ex99_candidates:
        if _EX99_KEYWORD_RE.search(candidate.description):
            return candidate
    return None


def html_to_text(raw_html: str) -> str:
    """HTML earnings-release body to plain text: scripts/styles and whole
    ``<table>`` blocks dropped first (the plan's "去表格"), then remaining
    tags stripped and whitespace collapsed."""

    text = _TABLE_RE.sub(" ", raw_html)
    text = _SCRIPT_STYLE_RE.sub(" ", text)
    # Literal newlines/tabs in the HTML *source* are insignificant whitespace
    # (pretty-printing, not a visual line break) and must not become
    # paragraph breaks; collapse them to spaces before inserting the real
    # block-level breaks below.
    text = re.sub(r"[\r\n\t]+", " ", text)
    text = _BLOCK_BREAK_RE.sub("\n", text)
    text = _TAG_RE.sub(" ", text)
    text = html.unescape(text)
    # Collapse in-line whitespace per line but keep the line structure itself
    # (including blank lines from adjacent block boundaries, e.g.
    # "</p><p>") so real paragraph gaps survive as exactly one blank line;
    # dropping empty lines here would merge every paragraph onto one line.
    lines = [_WS_RE.sub(" ", line).strip() for line in text.split("\n")]
    text = "\n".join(lines)
    text = _MULTI_NEWLINE_RE.sub("\n\n", text)
    return text.strip()


def sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------
# Main build
# --------------------------------------------------------------------------


@dataclass
class EventRow:
    cik: str
    ticker: str
    company_name: str | None
    accession: str
    acceptance_utc: str | None
    form: str
    items: str
    ex99_url: str | None
    text_path: str | None
    text_sha256: str | None
    text_chars: int
    fetch_status: str


@dataclass
class BuildStats:
    companies_seen: int = 0
    filings_matched: int = 0
    rows_written: int = 0
    ok: int = 0
    cached: int = 0
    no_ex99: int = 0
    http_error: int = 0
    skipped_out_of_range: int = 0
    per_status: dict[str, int] = field(default_factory=dict)


def fetch_exhibit_text(
    client: SecClient, cik10: str, accession: str, ex99_url: str
) -> tuple[str, int, str] | None:
    """``(text, char_count, status)`` for one exhibit, or ``None`` on
    fetch failure. Reuses the cached ``.txt`` file when present."""

    cik_plain = str(int(cik10))
    out_path = RAW_TEXT_ROOT / cik_plain / f"{accession}.txt"
    if out_path.exists() and out_path.stat().st_size > 0:
        text = out_path.read_text(encoding="utf-8", errors="replace")
        return text, len(text), "cached"

    status, content = client.get(ex99_url)
    if status != 200:
        return None
    raw_html = content.decode("utf-8", errors="replace")
    text = html_to_text(raw_html)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(text, encoding="utf-8")
    return text, len(text), "ok"


def build(
    *,
    start: date,
    end: date,
    top_n: int,
    limit: int | None,
    refresh_tickers: bool,
) -> BuildStats:
    stats = BuildStats()
    client = SecClient()
    try:
        log(
            f"loading broad-universe symbols for [{start}, {end}], "
            f"top {top_n} by adv_rank per cohort"
        )
        symbols = load_universe_symbols(start, end, top_n=top_n)
        log(f"universe symbols: {len(symbols)}")

        ticker_to_cik = load_company_tickers(client, refresh=refresh_tickers)
        resolved, unresolved = resolve_tickers(symbols, ticker_to_cik)
        write_unresolved(unresolved)
        log(
            f"resolved {len(resolved)} tickers to CIK, "
            f"{len(unresolved)} unresolved -> {UNRESOLVED_PATH}"
        )

        rows_by_year: dict[int, list[dict]] = {}
        stopped_early = False
        for ticker, cik10 in sorted(resolved.items()):
            if stopped_early:
                break
            stats.companies_seen += 1
            company_name, filing_rows = collect_filing_rows(client, cik10, start=start)
            for filing in filing_rows:
                if not filing_matches(filing.form, filing.items):
                    continue
                acceptance_utc = to_utc_iso(filing.acceptance_raw)
                if acceptance_utc is None:
                    log(
                        f"  {ticker} {filing.accession}: missing/unparseable "
                        "acceptanceDateTime, skipping"
                    )
                    continue
                accept_date = acceptance_utc[:10]
                if accept_date < start.isoformat() or accept_date > end.isoformat():
                    stats.skipped_out_of_range += 1
                    continue
                stats.filings_matched += 1

                accession_nodash = filing.accession.replace("-", "")
                cik_plain = str(int(cik10))
                index_url = (
                    ARCHIVES_BASE.format(cik=cik_plain, accession_nodash=accession_nodash)
                    + f"{filing.accession}-index.htm"
                )
                ex99_url: str | None = None
                text_path: str | None = None
                text_sha256: str | None = None
                text_chars = 0
                fetch_status = "no_ex99"

                index_status, index_content = client.get(index_url)
                if index_status != 200:
                    fetch_status = "http_error"
                    stats.http_error += 1
                else:
                    candidates = parse_document_table(
                        index_content.decode("utf-8", errors="replace")
                    )
                    picked = pick_ex99(candidates)
                    if picked is None:
                        stats.no_ex99 += 1
                    else:
                        href = picked.href
                        ex99_url = href if href.startswith("http") else "https://www.sec.gov" + href
                        result = fetch_exhibit_text(client, cik10, filing.accession, ex99_url)
                        if result is None:
                            fetch_status = "http_error"
                            stats.http_error += 1
                        else:
                            text, text_chars, fetch_status = result
                            out_path = RAW_TEXT_ROOT / cik_plain / f"{filing.accession}.txt"
                            text_path = str(out_path.relative_to(ROOT))
                            text_sha256 = sha256_hex(text)
                            if fetch_status == "ok":
                                stats.ok += 1
                            else:
                                stats.cached += 1

                event = EventRow(
                    cik=cik10,
                    ticker=ticker,
                    company_name=company_name,
                    accession=filing.accession,
                    acceptance_utc=acceptance_utc,
                    form=filing.form or REQUIRED_FORM,
                    items=filing.items or "",
                    ex99_url=ex99_url,
                    text_path=text_path,
                    text_sha256=text_sha256,
                    text_chars=text_chars,
                    fetch_status=fetch_status,
                )
                year = int(accept_date[:4])
                rows_by_year.setdefault(year, []).append(event.__dict__)
                stats.rows_written += 1
                stats.per_status[fetch_status] = stats.per_status.get(fetch_status, 0) + 1
                log(
                    f"  [{stats.rows_written}] {ticker} {filing.accession} "
                    f"accepted={acceptance_utc} status={fetch_status} chars={text_chars}"
                )

                if limit is not None and stats.rows_written >= limit:
                    stopped_early = True
                    break

            if stats.companies_seen % 50 == 0:
                log(
                    f"progress: {stats.companies_seen}/{len(resolved)} companies, "
                    f"{stats.rows_written} rows written"
                )

        write_year_partitions(rows_by_year)
    finally:
        client.close()
    return stats


def write_year_partitions(rows_by_year: dict[int, list[dict]]) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for year, rows in rows_by_year.items():
        new_df = pd.DataFrame(rows)
        out_path = OUT_DIR / f"{year}.parquet"
        if out_path.exists():
            existing = pd.read_parquet(out_path)
            existing = existing[~existing["accession"].isin(new_df["accession"])]
            merged = pd.concat([existing, new_df], ignore_index=True)
        else:
            merged = new_df
        merged = merged.sort_values(["acceptance_utc", "ticker"]).reset_index(drop=True)
        tmp_path = out_path.with_suffix(".parquet.tmp")
        merged.to_parquet(tmp_path, index=False)
        tmp_path.replace(out_path)
        log(f"wrote {len(merged)} rows -> {out_path} ({len(new_df)} new/updated this run)")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--start", default="2024-01-01", help="ISO date, inclusive (default 2024-01-01)"
    )
    parser.add_argument("--end", default=None, help="ISO date, inclusive (default: today)")
    parser.add_argument(
        "--top-n", type=int, default=1500, help="Top N symbols per month-end cohort by adv_rank"
    )
    parser.add_argument(
        "--limit", type=int, default=None, help="Stop after this many matched filings (pilot runs)"
    )
    parser.add_argument(
        "--refresh-tickers",
        action="store_true",
        help="Refetch company_tickers.json instead of using the cache",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    start = date.fromisoformat(args.start)
    end = date.fromisoformat(args.end) if args.end else datetime.now(UTC).date()
    log(f"build_earnings_events start={start} end={end} top_n={args.top_n} limit={args.limit}")
    stats = build(
        start=start,
        end=end,
        top_n=args.top_n,
        limit=args.limit,
        refresh_tickers=args.refresh_tickers,
    )
    log(
        "done: companies_seen={companies_seen} filings_matched={filings_matched} "
        "rows_written={rows_written} ok={ok} cached={cached} no_ex99={no_ex99} "
        "http_error={http_error} skipped_out_of_range={skipped_out_of_range}".format(
            **stats.__dict__
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
