"""H-20260916-05 step 0: SEC Schedule 13D / 13G point-in-time filing collector.

Card: ``reports/research/hypotheses/H-20260916-05-13d-activist-event-drift.md``
Capability: ``events.sec_13d_13g`` in ``capabilities/registry.yaml``.

What this collects
------------------
Every Schedule 13D / 13D/A / 13G / 13G/A filing from 2016-01 onward whose
*subject company* (the issuer, not the filer) is a member of our
point-in-time top-N ADV universe, with the one timestamp that makes the
table point-in-time: the EDGAR ``<ACCEPTANCE-DATETIME>`` out of the filing
header.

Why acceptance datetime and not ``Date Filed``: EDGAR disseminates a filing
accepted by 17:30 ET on the same business day and stamps anything later with
the *next* business day. ``Date Filed`` in the quarterly index is therefore
already a "next business day" value for late filings, but it carries no time
of day at all, so it cannot tell a 09:45 ET filing (tradable that session)
from a 16:40 ET one (not tradable until the next open). The acceptance
timestamp does, which is the whole point of this card -- 13D drift studies
die on exactly this kind of half-session look-ahead.

Stages (each resumable; rerunning skips finished work)
-----------------------------------------------------
``index``
    One request per calendar quarter for EDGAR's quarterly form index
    (``full-index/{yyyy}/QTR{n}/form.idx``, ~55 MB each), keeping only the
    four Schedule 13D/G form types, into
    ``data/raw/sec_13d/index/{yyyy}q{n}.parquet``. The raw .idx payloads are
    not kept (2.5 GB of mostly unrelated form types); the filtered parquet
    is the raw artifact.
``map``
    Fetch ``https://www.sec.gov/files/company_tickers.json`` once into
    ``data/raw/sec_13d/company_tickers.json``, join it against the PIT
    universe (``data/features/universe``) and write
    ``data/raw/sec_13d/targets.parquet``: the candidate accessions whose
    index rows contain at least one CIK that maps to a universe ticker.
    The index lists a filing once per associated CIK (subject company *and*
    every filer), so this stage cannot yet tell issuer from filer -- it only
    narrows ~600k filings to the ones worth a document request. ``fetch``
    resolves the issuer authoritatively from the header's SUBJECT COMPANY
    block.
``fetch``
    One HTTP range request per candidate accession for the head of the
    complete submission text file (``--max-bytes``, default 320 KB). The
    header at the top of that file gives the acceptance timestamp, the
    subject company and the filer names; the cover page that follows gives
    "percent of class" and (13D only) the Item 4 purpose-of-transaction
    text. Written in chunks of ``--chunk-size`` filings into
    ``data/raw/sec_13d/docs/{yyyy}q{n}/chunk-*.parquet`` so an interrupted
    quarter resumes at the last chunk rather than at the quarter boundary.
    ``--forms`` restricts which form types are fetched: the 13G family is
    ~95% of Schedule 13 traffic (28,828 SC 13G/A in 2024Q1 alone against 608
    new SC 13D) and is not in this card's primary test, so the default is
    the 13D family only and 13G rows keep index-derived visibility with
    ``visible_confidence = "filing_date_only"``.

SEC fair access
---------------
``SEC_USER_AGENT`` (contact email, from ``.env`` via ``load_dotenv``; never
read or printed here) is sent on every request, requests are serialized with
a minimum inter-request delay (default 0.15 s, i.e. <= ~6.7 req/s against
the 10 req/s ceiling), and nothing is fetched in parallel.

Usage::

    nohup ./scripts/run_capped.sh --mem 1.8G -- \\
        uv run python scripts/collect_sec_13d_filings.py --stage index \\
        > /tmp/sec13d_index.log 2>&1 &

    nohup ./scripts/run_capped.sh --mem 1.8G -- \\
        uv run python scripts/collect_sec_13d_filings.py --stage map \\
        > /tmp/sec13d_map.log 2>&1 &

    nohup ./scripts/run_capped.sh --mem 1.8G -- \\
        uv run python scripts/collect_sec_13d_filings.py --stage fetch \\
        > /tmp/sec13d_fetch.log 2>&1 &
"""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
import time
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402
from dotenv import load_dotenv  # noqa: E402

RAW_ROOT = ROOT / "data" / "raw" / "sec_13d"
INDEX_ROOT = RAW_ROOT / "index"
DOCS_ROOT = RAW_ROOT / "docs"
SAMPLE_ROOT = RAW_ROOT / "samples"
COMPANY_TICKERS_PATH = RAW_ROOT / "company_tickers.json"
TARGETS_PATH = RAW_ROOT / "targets.parquet"
UNIVERSE_ROOT = ROOT / "data" / "features" / "universe"

QUARTER_INDEX_URL = "https://www.sec.gov/Archives/edgar/full-index/{year}/QTR{qtr}/form.idx"
COMPANY_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
ARCHIVE_URL = "https://www.sec.gov/Archives/{file_name}"

#: The four Schedule 13 form types this card cares about, in their canonical
#: spelling. ``SC 13E3`` (going private) is a different filing and is
#: deliberately excluded.
#:
#: EDGAR *renamed* these form types with the 2024-12-18 structured-XML
#: mandate: ``SC 13D`` became ``SCHEDULE 13D`` and so on. Observed directly
#: (2026-09-16): 2024Q4 has 445 ``SC 13D`` and 2025Q2 has 546 ``SCHEDULE 13D``
#: plus 3 legacy ``SC 13D/A``. Both spellings are accepted and normalized to
#: the canonical one, and the raw spelling is kept in ``form_type_raw`` so the
#: rename is auditable rather than invisible.
SCHEDULE_13_FORMS: tuple[str, ...] = ("SC 13D", "SC 13D/A", "SC 13G", "SC 13G/A")
_FORM_TYPE_PATTERN = re.compile(r"^(?:SC|SCHEDULE)\s*13\s*([DG])\s*(/A)?$", re.IGNORECASE)
NEW_13D_FORM = "SC 13D"
DEFAULT_FETCH_FORMS: tuple[str, ...] = ("SC 13D", "SC 13D/A")

MIN_REQUEST_INTERVAL_SECONDS = 0.15
HTTP_TIMEOUT_SECONDS = 180
DEFAULT_START_QUARTER = "2016q1"
DEFAULT_MAX_BYTES = 320_000
DEFAULT_CHUNK_SIZE = 250
DEFAULT_UNIVERSE_TOP_N = 1000
#: Filings whose header we keep verbatim in the raw table (small, and the
#: only place a later reviewer can re-derive the acceptance timestamp from).
HEADER_KEEP_CHARS = 4000

DOC_COLUMNS: tuple[str, ...] = (
    "accession",
    "form_type",
    "filing_date",
    "acceptance_datetime_et",
    "period_of_report",
    "issuer_cik",
    "issuer_name",
    "issuer_symbol_header",
    "filer_names",
    "filer_ciks",
    "percent_of_class",
    "percent_parse_confidence",
    "percent_parse_source",
    "item4_chars",
    "item4_present",
    "body_chars",
    "truncated",
    "header_text",
    "http_status",
)


# --------------------------------------------------------------------------
# quarters
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Quarter:
    year: int
    quarter: int

    def __str__(self) -> str:
        return f"{self.year}q{self.quarter}"

    def next(self) -> Quarter:
        if self.quarter == 4:
            return Quarter(self.year + 1, 1)
        return Quarter(self.year, self.quarter + 1)


def parse_quarter(value: str) -> Quarter:
    match = re.fullmatch(r"(\d{4})[qQ]([1-4])", value.strip())
    if match is None:
        raise argparse.ArgumentTypeError(f"expected a quarter like 2016q1, got {value!r}")
    return Quarter(int(match.group(1)), int(match.group(2)))


def quarter_of(day: date) -> Quarter:
    return Quarter(day.year, (day.month - 1) // 3 + 1)


def quarter_range(start: Quarter, end: Quarter) -> list[Quarter]:
    quarters: list[Quarter] = []
    current = start
    while (current.year, current.quarter) <= (end.year, end.quarter):
        quarters.append(current)
        current = current.next()
    return quarters


# --------------------------------------------------------------------------
# HTTP
# --------------------------------------------------------------------------


class SecClient:
    """Serialized, rate-limited SEC HTTP client.

    Same shape as ``collect_sec_insider_transactions.SecClient`` (one
    connection, one request at a time, minimum inter-request delay, retry
    with backoff on 403/429/5xx) plus a byte-range helper, because a
    Schedule 13D complete submission is 100 KB-10 MB of exhibits and only
    its first few hundred KB are ever parsed here.
    """

    def __init__(self, *, min_interval: float = MIN_REQUEST_INTERVAL_SECONDS) -> None:
        import httpx

        user_agent = os.getenv("SEC_USER_AGENT", "").strip()
        if not user_agent or re.search(r"\S+@\S+\.\S+", user_agent) is None:
            raise RuntimeError(
                "SEC_USER_AGENT with a contact email is required for live SEC fetches; "
                "populate it in .env (loaded via load_dotenv) -- this script never reads .env"
            )
        self._min_interval = min_interval
        self._last_request = 0.0
        self._client = httpx.Client(
            headers={"User-Agent": user_agent, "Accept-Encoding": "gzip, deflate"},
            timeout=HTTP_TIMEOUT_SECONDS,
            follow_redirects=True,
        )

    def get(self, url: str, *, retries: int = 3, max_bytes: int | None = None) -> tuple[int, bytes]:
        import httpx

        headers = {"Range": f"bytes=0-{max_bytes - 1}"} if max_bytes else None
        for attempt in range(retries):
            elapsed = time.monotonic() - self._last_request
            if elapsed < self._min_interval:
                time.sleep(self._min_interval - elapsed)
            self._last_request = time.monotonic()
            try:
                response = self._client.get(url, headers=headers)
            except httpx.HTTPError as exc:  # transport-level, worth a retry
                if attempt == retries - 1:
                    raise
                log(f"  transport error ({type(exc).__name__}), retry {attempt + 1}/{retries}")
                time.sleep(2.0 * (attempt + 1))
                continue
            if response.status_code in {403, 429, 500, 502, 503, 504}:
                if attempt == retries - 1:
                    return response.status_code, response.content
                log(f"  HTTP {response.status_code}, backing off (attempt {attempt + 1})")
                time.sleep(5.0 * (attempt + 1))
                continue
            return response.status_code, response.content
        raise RuntimeError("unreachable")

    def close(self) -> None:
        self._client.close()


def log(message: str) -> None:
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{stamp}] {message}", flush=True)


# --------------------------------------------------------------------------
# stage: index
# --------------------------------------------------------------------------


def canonical_form_type(value: str) -> str | None:
    """``"SCHEDULE 13G/A"`` / ``"SC 13G/A"`` -> ``"SC 13G/A"``; anything that
    is not a Schedule 13D/13G -> ``None``."""
    match = _FORM_TYPE_PATTERN.match(value.strip())
    if match is None:
        return None
    return f"SC 13{match.group(1).upper()}{'/A' if match.group(2) else ''}"


def parse_form_index(payload: bytes, *, forms: tuple[str, ...] = SCHEDULE_13_FORMS) -> pd.DataFrame:
    """Parse EDGAR's space-padded ``form.idx``.

    Layout: ``Form Type``, ``Company Name``, ``CIK``, ``Date Filed``,
    ``File Name``, each padded to a column width that *changed* when the
    form types were renamed in 2024-12 (``Form Type`` was 12 characters wide,
    the ``SCHEDULE 13x`` spellings need 17). Slicing fixed columns therefore
    silently truncated ``SCHEDULE 13D/A`` to ``SCHEDULE 13D`` and turned every
    2025+ amendment into a new filing, so the fields are split structurally
    instead: the archive path is the last whitespace-delimited token, CIK and
    Date Filed are the two before the company name, and the form type is the
    first field up to the first run of two or more spaces.
    """
    rows: list[tuple[str, str, str, str, str, str]] = []
    wanted = set(forms)
    started = False
    for raw in payload.decode("latin-1").splitlines():
        if not started:
            started = raw.startswith("---")
            continue
        if not raw.strip():
            continue
        parts = raw.rsplit(None, 1)
        if len(parts) != 2:
            continue
        head, file_name = parts
        tokens = head.rsplit(None, 2)
        if len(tokens) != 3:
            continue
        form_and_company, cik, date_filed = tokens
        split = re.split(r"\s{2,}", form_and_company.strip(), maxsplit=1)
        form_type_raw = split[0].strip()
        company = split[1].strip() if len(split) > 1 else ""
        form_type = canonical_form_type(form_type_raw)
        if form_type is None or form_type not in wanted:
            continue
        rows.append((form_type, form_type_raw, company, cik, date_filed, file_name))
    frame = pd.DataFrame(
        rows,
        columns=["form_type", "form_type_raw", "company_name", "cik", "date_filed", "file_name"],
    )
    frame["cik"] = pd.to_numeric(frame["cik"], errors="coerce").astype("Int64")
    frame["date_filed"] = pd.to_datetime(frame["date_filed"], errors="coerce")
    frame["accession"] = frame["file_name"].map(lambda value: Path(str(value)).stem)
    return frame.reset_index(drop=True)


def stage_index(client: SecClient, quarters: list[Quarter], *, force: bool) -> dict[str, str]:
    INDEX_ROOT.mkdir(parents=True, exist_ok=True)
    outcome: dict[str, str] = {}
    for quarter in quarters:
        target = INDEX_ROOT / f"{quarter}.parquet"
        if target.exists() and not force:
            outcome[str(quarter)] = "already_present"
            continue
        url = QUARTER_INDEX_URL.format(year=quarter.year, qtr=quarter.quarter)
        status, payload = client.get(url)
        if status == 404:
            outcome[str(quarter)] = "missing_404"
            log(f"index {quarter}: MISSING on sec.gov (HTTP 404) -- skipped, not faked")
            continue
        if status != 200:
            outcome[str(quarter)] = f"http_{status}"
            log(f"index {quarter}: HTTP {status} -- skipped")
            continue
        frame = parse_form_index(payload)
        del payload
        temporary = target.with_suffix(".parquet.part")
        frame.to_parquet(temporary, index=False, compression="zstd")
        temporary.replace(target)
        counts = frame["form_type"].value_counts().to_dict()
        outcome[str(quarter)] = "downloaded"
        log(f"index {quarter}: {len(frame):,} Schedule 13 index rows {counts}")
    return outcome


def load_index(quarters: list[Quarter] | None = None) -> pd.DataFrame:
    paths = (
        sorted(INDEX_ROOT.glob("*.parquet"))
        if quarters is None
        else [INDEX_ROOT / f"{quarter}.parquet" for quarter in quarters]
    )
    frames = [pd.read_parquet(path) for path in paths if path.exists()]
    if not frames:
        raise RuntimeError(f"no Schedule 13 index parquet under {INDEX_ROOT}; run --stage index")
    frame = pd.concat(frames, ignore_index=True)
    return frame


# --------------------------------------------------------------------------
# stage: map
# --------------------------------------------------------------------------


def load_company_tickers(client: SecClient | None) -> pd.DataFrame:
    """``cik -> ticker`` from SEC's current registrant list.

    This file is a *current* snapshot: an issuer that was acquired or
    delisted has no row, so 13D events on names that left the tape are
    unmappable here by construction. That is recorded as a caveat on the
    capability rather than patched with a guess.
    """
    if not COMPANY_TICKERS_PATH.exists():
        if client is None:
            raise RuntimeError(f"{COMPANY_TICKERS_PATH} missing and no client to fetch it")
        status, payload = client.get(COMPANY_TICKERS_URL)
        if status != 200:
            raise RuntimeError(f"company_tickers.json fetch failed with HTTP {status}")
        COMPANY_TICKERS_PATH.parent.mkdir(parents=True, exist_ok=True)
        COMPANY_TICKERS_PATH.write_bytes(payload)
    payload = json.loads(COMPANY_TICKERS_PATH.read_text())
    rows = [
        (int(item["cik_str"]), str(item["ticker"]).upper(), str(item.get("title", "")))
        for item in payload.values()
        if isinstance(item, dict) and item.get("ticker") and item.get("cik_str") is not None
    ]
    frame = pd.DataFrame(rows, columns=["cik", "symbol", "company_title"])
    return frame.drop_duplicates(subset=["cik", "symbol"]).reset_index(drop=True)


def universe_symbols(top_n: int) -> set[str]:
    from open_composer.research.features.universe import load_universe_panel

    panel = load_universe_panel(UNIVERSE_ROOT)
    return set(panel.loc[panel["adv_rank"] <= top_n, "symbol"].astype(str))


def stage_map(client: SecClient, *, top_n: int) -> dict[str, object]:
    index = load_index()
    tickers = load_company_tickers(client)
    symbols = universe_symbols(top_n)
    mapped = tickers.loc[tickers["symbol"].isin(symbols)]
    cik_to_symbol = (
        mapped.sort_values("symbol").drop_duplicates(subset=["cik"]).set_index("cik")["symbol"]
    )
    index["candidate_symbol"] = index["cik"].map(cik_to_symbol)
    hit = index.loc[index["candidate_symbol"].notna()].copy()
    # One row per (accession, candidate issuer CIK): an accession whose index
    # rows contain two tickered CIKs (a listed company filing a 13D on
    # another listed company) stays ambiguous here on purpose and is
    # resolved from the header's SUBJECT COMPANY block in ``fetch``.
    targets = (
        hit[
            [
                "accession",
                "form_type",
                "date_filed",
                "file_name",
                "cik",
                "company_name",
                "candidate_symbol",
            ]
        ]
        .rename(columns={"cik": "candidate_cik"})
        .drop_duplicates(subset=["accession", "candidate_cik"])
        .sort_values(["date_filed", "accession"])
        .reset_index(drop=True)
    )
    TARGETS_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = TARGETS_PATH.with_suffix(".parquet.part")
    targets.to_parquet(temporary, index=False, compression="zstd")
    temporary.replace(TARGETS_PATH)
    summary = {
        "index_rows": int(len(index)),
        "index_accessions": int(index["accession"].nunique()),
        "universe_symbols": len(symbols),
        "universe_ciks_mapped": int(len(cik_to_symbol)),
        "target_rows": int(len(targets)),
        "target_accessions": int(targets["accession"].nunique()),
        "target_accessions_by_form": {
            str(key): int(value)
            for key, value in targets.drop_duplicates("accession")["form_type"]
            .value_counts()
            .items()
        },
        "ambiguous_accessions": int(
            (targets.groupby("accession")["candidate_cik"].nunique() > 1).sum()
        ),
    }
    log(f"map: {json.dumps(summary)}")
    return summary


# --------------------------------------------------------------------------
# document parsing (pure functions; unit-tested)
# --------------------------------------------------------------------------

_HEADER_END = re.compile(r"</SEC-HEADER>|</IMS-HEADER>", re.IGNORECASE)
_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"[ \t\r\f\v ]+")
_MULTI_NEWLINE = re.compile(r"\n{3,}")


def split_header(text: str) -> tuple[str, str]:
    """``(header, body)`` split at ``</SEC-HEADER>``.

    Filings before ~2001 use ``<IMS-HEADER>``; both are accepted. When no
    header terminator is present (a truncated range response that never
    reached it) the whole payload is treated as header so that the
    acceptance timestamp parser still gets a chance and the body parsers
    correctly see nothing.
    """
    match = _HEADER_END.search(text)
    if match is None:
        return text, ""
    return text[: match.end()], text[match.end() :]


def parse_header_fields(header: str) -> dict[str, object]:
    """Pull the point-in-time and identity fields out of an EDGAR header.

    The header is SGML-ish key/value lines with ``SUBJECT COMPANY:`` and
    ``FILED BY:`` blocks. Both blocks repeat the same ``CIK:`` /
    ``COMPANY CONFORMED NAME:`` keys, so which block a key belongs to is
    tracked by the most recent block marker -- reading the first ``CIK:``
    in the file would pick up whichever party EDGAR happened to serialize
    first, and for Schedule 13D that is usually the *filer*.
    """
    acceptance = None
    match = re.search(r"<ACCEPTANCE-DATETIME>\s*(\d{14})", header)
    if match:
        acceptance = match.group(1)
    form_type = _header_value(header, "CONFORMED SUBMISSION TYPE")
    filed_as_of = _header_value(header, "FILED AS OF DATE")
    period = _header_value(header, "CONFORMED PERIOD OF REPORT")

    block = None
    subject_cik: int | None = None
    subject_name: str | None = None
    subject_symbol: str | None = None
    filer_ciks: list[int] = []
    filer_names: list[str] = []
    for raw in header.splitlines():
        line = raw.strip()
        upper = line.upper()
        if upper.startswith("SUBJECT COMPANY:"):
            block = "subject"
            continue
        if upper.startswith("FILED BY:") or upper.startswith("FILER:"):
            block = "filer"
            continue
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip().upper()
        value = value.strip()
        if not value:
            continue
        if key in {"CIK", "CENTRAL INDEX KEY"}:
            # Real EDGAR headers write ``CENTRAL INDEX KEY:``; the short
            # ``CIK:`` spelling appears in a few old vintages. Accepting only
            # the short one silently produced a null issuer on every modern
            # filing (observed on a 150-filing pilot: 150/150 null).
            digits = re.sub(r"\D", "", value)
            if not digits:
                continue
            if block == "subject" and subject_cik is None:
                subject_cik = int(digits)
            elif block == "filer":
                filer_ciks.append(int(digits))
        elif key == "COMPANY CONFORMED NAME":
            if block == "subject" and subject_name is None:
                subject_name = value
            elif block == "filer":
                filer_names.append(value)
        elif key in {"TICKER SYMBOL", "TRADING SYMBOL"} and block == "subject":
            subject_symbol = value.upper()
    return {
        "acceptance_datetime_et": acceptance,
        "header_form_type": form_type,
        "filed_as_of_date": filed_as_of,
        "period_of_report": period,
        "issuer_cik": subject_cik,
        "issuer_name": subject_name,
        "issuer_symbol_header": subject_symbol,
        "filer_ciks": filer_ciks,
        "filer_names": filer_names,
    }


def _header_value(header: str, key: str) -> str | None:
    match = re.search(rf"^\s*{re.escape(key)}:\s*(.+)$", header, re.MULTILINE)
    return match.group(1).strip() if match else None


def strip_markup(body: str) -> str:
    """HTML/SGML body to plain text, collapsing runs of spaces.

    13D cover pages are tables; after tag removal the numbered rows survive
    as ``"13 PERCENT OF CLASS REPRESENTED BY AMOUNT IN ROW (11) 5.6%"``,
    which is what the percent parser keys on.
    """
    text = re.sub(r"(?is)<(script|style)\b.*?</\1>", " ", body)
    text = re.sub(r"(?is)<br\s*/?>|</(p|tr|div|table)>", "\n", text)
    text = _TAG.sub(" ", text)
    text = html.unescape(text)
    text = _WS.sub(" ", text)
    return _MULTI_NEWLINE.sub("\n\n", text)


#: Structured (XML) Schedule 13D/G, mandatory from 2024-12-18. The element
#: names vary slightly across the SEC's own samples, so several are accepted.
_XML_PERCENT = re.compile(
    r"<(?:[a-zA-Z0-9]+:)?(?:percentOfClass|classPercent|percentOwned|"
    r"aggregatePercentOfClass)>\s*([0-9]+(?:\.[0-9]+)?)\s*<",
    re.IGNORECASE,
)
_PERCENT_LABEL = re.compile(r"PERCENT\s+OF\s+CLASS", re.IGNORECASE)
_PERCENT_VALUE = re.compile(r"([0-9]{1,3}(?:\.[0-9]{1,4})?)\s*%")
_ROW_NUMBER_NOISE = re.compile(r"^\s*\(?1[0-9]?\)?\s*$")


def parse_percent_of_class(body_text: str, raw_body: str = "") -> tuple[float | None, str, str]:
    """``(percent, confidence, source)`` for the cover-page percent of class.

    Three routes, in order of trust:

    ``xml``
        A structured 13D/G (2024-12-18 onward) carries the number in an
        element; no text heuristics needed -> ``high``.
    ``label_near``
        The first ``%`` value within 160 characters after a
        "PERCENT OF CLASS" label. 13D cover pages put the value in the table
        cell immediately after the label, so a near hit is reliable ->
        ``high`` when the value is a plausible 0-100 and the gap is short.
    ``label_far``
        Same label but the value is 160-600 characters away (cover pages
        that interleave the row numbers of the next rows) -> ``medium``.

    A filing whose cover page never reached the payload (range truncation)
    or that reports a non-numeric percent returns ``(None, "none", ...)``.
    Downstream code must treat ``percent_of_class`` as optional: this card's
    primary test does not condition on it.
    """
    if raw_body:
        xml_match = _XML_PERCENT.search(raw_body)
        if xml_match:
            value = float(xml_match.group(1))
            if 0.0 <= value <= 100.0:
                return value, "high", "xml"
    best: tuple[float, int] | None = None
    for label in _PERCENT_LABEL.finditer(body_text):
        window = body_text[label.end() : label.end() + 600]
        value_match = _PERCENT_VALUE.search(window)
        if value_match is None:
            continue
        value = float(value_match.group(1))
        if not 0.0 <= value <= 100.0:
            continue
        distance = value_match.start()
        if best is None or distance < best[1]:
            best = (value, distance)
    if best is None:
        return None, "none", "not_found"
    value, distance = best
    if distance <= 160:
        return value, "high", "label_near"
    return value, "medium", "label_far"


_ITEM4_START = re.compile(
    r"ITEM\s*4\s*[.:\-—]?\s*(?:PURPOSE\s+OF\s+(?:THE\s+)?TRANSACTION)", re.IGNORECASE
)
_ITEM5_START = re.compile(r"ITEM\s*5\s*[.:\-—]?\s*(?:INTEREST|OWNERSHIP)", re.IGNORECASE)


def parse_item4_length(body_text: str) -> tuple[int, bool]:
    """``(chars, present)`` for Schedule 13D Item 4 "Purpose of Transaction".

    Used only as a crude activism proxy -- a boilerplate "the Reporting
    Person acquired the shares for investment purposes" Item 4 runs a few
    hundred characters, an activist letter with demands runs thousands. The
    last occurrence of the Item 4 heading is used because the heading also
    appears in the filing's own table of contents / cross-references, and
    the body text always comes after those.
    """
    starts = list(_ITEM4_START.finditer(body_text))
    if not starts:
        return 0, False
    start = starts[-1]
    tail = body_text[start.end() :]
    end = _ITEM5_START.search(tail)
    segment = tail[: end.start()] if end else tail
    return len(segment.strip()), True


def parse_submission(
    payload: bytes, *, accession: str, index_form_type: str, index_date_filed: str, max_bytes: int
) -> dict[str, object]:
    """One raw-table row from the head of a complete submission text file."""
    text = payload.decode("latin-1", errors="replace")
    header, body = split_header(text)
    fields = parse_header_fields(header)
    body_text = strip_markup(body) if body else ""
    header_form = str(fields.get("header_form_type") or "")
    form_type = canonical_form_type(header_form) or index_form_type
    if form_type.upper().startswith("SC 13D"):
        percent, confidence, source = parse_percent_of_class(body_text, body)
        item4_chars, item4_present = parse_item4_length(body_text)
    else:
        percent, confidence, source = parse_percent_of_class(body_text, body)
        item4_chars, item4_present = 0, False
    filed_as_of = str(fields.get("filed_as_of_date") or "").strip()
    if len(filed_as_of) == 8 and filed_as_of.isdigit():
        filed_as_of = f"{filed_as_of[:4]}-{filed_as_of[4:6]}-{filed_as_of[6:]}"
    return {
        "accession": accession,
        "form_type": form_type,
        "filing_date": filed_as_of or index_date_filed,
        "acceptance_datetime_et": fields.get("acceptance_datetime_et"),
        "period_of_report": fields.get("period_of_report"),
        "issuer_cik": fields.get("issuer_cik"),
        "issuer_name": fields.get("issuer_name"),
        "issuer_symbol_header": fields.get("issuer_symbol_header"),
        "filer_names": "|".join(str(name) for name in fields.get("filer_names") or []),
        "filer_ciks": "|".join(str(value) for value in fields.get("filer_ciks") or []),
        "percent_of_class": percent,
        "percent_parse_confidence": confidence,
        "percent_parse_source": source,
        "item4_chars": item4_chars,
        "item4_present": item4_present,
        "body_chars": len(body_text),
        "truncated": len(payload) >= max_bytes,
        "header_text": header[:HEADER_KEEP_CHARS],
        "http_status": 200,
    }


# --------------------------------------------------------------------------
# stage: fetch
# --------------------------------------------------------------------------


def _chunk_path(quarter: str, chunk: int) -> Path:
    return DOCS_ROOT / quarter / f"chunk-{chunk:05d}.parquet"


def fetched_accessions() -> set[str]:
    done: set[str] = set()
    for path in sorted(DOCS_ROOT.glob("*/chunk-*.parquet")):
        done.update(pd.read_parquet(path, columns=["accession"])["accession"].astype(str))
    return done


def stage_fetch(
    client: SecClient,
    *,
    forms: tuple[str, ...],
    max_bytes: int,
    chunk_size: int,
    limit: int | None,
    keep_samples: int,
    sample_n: int | None = None,
    sample_seed: int = 20260916,
) -> dict[str, object]:
    if not TARGETS_PATH.exists():
        raise RuntimeError(f"{TARGETS_PATH} missing; run --stage map first")
    targets = pd.read_parquet(TARGETS_PATH)
    targets = targets.loc[targets["form_type"].isin(forms)]
    accessions = (
        targets.drop_duplicates(subset=["accession"])
        .sort_values(["date_filed", "accession"])
        .reset_index(drop=True)
    )
    done = fetched_accessions()
    pending = accessions.loc[~accessions["accession"].isin(done)]
    log(
        f"fetch: {len(accessions):,} target accessions in forms {forms}, "
        f"{len(done):,} already fetched, {len(pending):,} pending"
    )
    if sample_n is not None and len(pending) > sample_n:
        # A *random* sample across the whole period, not the first N by date:
        # used to validate index-only issuer attribution on the 13G family,
        # where fetching all 92k documents is not worth it but a 1990s-to-2026
        # random sample measures the error rate honestly.
        pending = pending.sample(n=sample_n, random_state=sample_seed).sort_values(
            ["date_filed", "accession"]
        )
    if limit is not None:
        pending = pending.head(limit)
    pending = pending.copy()
    pending["quarter"] = pending["date_filed"].map(lambda value: str(quarter_of(value.date())))

    samples_written = len(list(SAMPLE_ROOT.glob("*.txt"))) if SAMPLE_ROOT.exists() else 0
    stats = {"fetched": 0, "failed": 0, "quarters": {}}
    for quarter, group in pending.groupby("quarter", sort=True):
        directory = DOCS_ROOT / str(quarter)
        directory.mkdir(parents=True, exist_ok=True)
        existing = sorted(directory.glob("chunk-*.parquet"))
        next_chunk = (int(existing[-1].stem.split("-")[1]) + 1) if existing else 0
        rows: list[dict[str, object]] = []
        quarter_failures = 0
        for row in group.itertuples(index=False):
            url = ARCHIVE_URL.format(file_name=row.file_name)
            status, payload = client.get(url, max_bytes=max_bytes)
            if status not in {200, 206} or not payload:
                quarter_failures += 1
                rows.append(
                    {
                        **{column: None for column in DOC_COLUMNS},
                        "accession": str(row.accession),
                        "form_type": str(row.form_type),
                        "filing_date": str(row.date_filed.date()),
                        "http_status": int(status),
                        "truncated": False,
                        "item4_chars": 0,
                        "item4_present": False,
                        "body_chars": 0,
                        "percent_parse_confidence": "none",
                        "percent_parse_source": "http_error",
                    }
                )
            else:
                rows.append(
                    parse_submission(
                        payload,
                        accession=str(row.accession),
                        index_form_type=str(row.form_type),
                        index_date_filed=str(row.date_filed.date()),
                        max_bytes=max_bytes,
                    )
                )
                if samples_written < keep_samples:
                    SAMPLE_ROOT.mkdir(parents=True, exist_ok=True)
                    (SAMPLE_ROOT / f"{row.accession}.txt").write_bytes(payload[:HEADER_KEEP_CHARS])
                    samples_written += 1
            if len(rows) >= chunk_size:
                _write_chunk(rows, quarter=str(quarter), chunk=next_chunk)
                stats["fetched"] += len(rows)
                log(f"fetch {quarter}: wrote chunk {next_chunk} ({len(rows)} filings)")
                rows = []
                next_chunk += 1
        if rows:
            _write_chunk(rows, quarter=str(quarter), chunk=next_chunk)
            stats["fetched"] += len(rows)
            log(f"fetch {quarter}: wrote chunk {next_chunk} ({len(rows)} filings)")
        stats["failed"] += quarter_failures
        stats["quarters"][str(quarter)] = {"filings": int(len(group)), "failed": quarter_failures}
    log(f"fetch: {json.dumps(stats)[:2000]}")
    return stats


def _write_chunk(rows: list[dict[str, object]], *, quarter: str, chunk: int) -> None:
    frame = pd.DataFrame(rows)
    for column in DOC_COLUMNS:
        if column not in frame.columns:
            frame[column] = None
    frame = frame[list(DOC_COLUMNS)]
    frame["issuer_cik"] = pd.to_numeric(frame["issuer_cik"], errors="coerce").astype("Int64")
    frame["percent_of_class"] = pd.to_numeric(frame["percent_of_class"], errors="coerce")
    frame["item4_chars"] = (
        pd.to_numeric(frame["item4_chars"], errors="coerce").fillna(0).astype("int64")
    )
    frame["item4_present"] = frame["item4_present"].fillna(False).astype(bool)
    frame["body_chars"] = (
        pd.to_numeric(frame["body_chars"], errors="coerce").fillna(0).astype("int64")
    )
    frame["truncated"] = frame["truncated"].fillna(False).astype(bool)
    target = _chunk_path(quarter, chunk)
    temporary = target.with_suffix(".parquet.part")
    frame.to_parquet(temporary, index=False, compression="zstd")
    temporary.replace(target)


def load_docs() -> pd.DataFrame:
    paths = sorted(DOCS_ROOT.glob("*/chunk-*.parquet"))
    if not paths:
        raise RuntimeError(f"no fetched documents under {DOCS_ROOT}; run --stage fetch")
    return pd.concat([pd.read_parquet(path) for path in paths], ignore_index=True)


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", required=True, choices=["index", "map", "fetch"])
    parser.add_argument("--start", type=parse_quarter, default=parse_quarter(DEFAULT_START_QUARTER))
    parser.add_argument("--end", type=parse_quarter, default=None)
    parser.add_argument("--universe-top-n", type=int, default=DEFAULT_UNIVERSE_TOP_N)
    parser.add_argument("--forms", default=",".join(DEFAULT_FETCH_FORMS))
    parser.add_argument("--max-bytes", type=int, default=DEFAULT_MAX_BYTES)
    parser.add_argument("--chunk-size", type=int, default=DEFAULT_CHUNK_SIZE)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--keep-samples", type=int, default=20)
    parser.add_argument("--sample-n", type=int, default=None)
    parser.add_argument("--sample-seed", type=int, default=20260916)
    parser.add_argument("--min-interval", type=float, default=MIN_REQUEST_INTERVAL_SECONDS)
    parser.add_argument("--force", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    load_dotenv(dotenv_path=ROOT / ".env")
    RAW_ROOT.mkdir(parents=True, exist_ok=True)
    client = SecClient(min_interval=args.min_interval)
    try:
        if args.stage == "index":
            end = args.end or quarter_of(date.today())
            outcome = stage_index(client, quarter_range(args.start, end), force=args.force)
            log(f"index summary: {json.dumps(outcome)}")
        elif args.stage == "map":
            stage_map(client, top_n=args.universe_top_n)
        else:
            forms = tuple(value.strip() for value in args.forms.split(",") if value.strip())
            stage_fetch(
                client,
                forms=forms,
                max_bytes=args.max_bytes,
                chunk_size=args.chunk_size,
                limit=args.limit,
                keep_samples=args.keep_samples,
                sample_n=args.sample_n,
                sample_seed=args.sample_seed,
            )
    finally:
        client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
