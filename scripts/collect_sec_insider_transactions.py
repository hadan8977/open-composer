"""H-20260916-01 step 0: SEC Form 4 insider-transaction collector.

Card: ``reports/research/hypotheses/H-20260916-01-insider-form4-confirmation-gate.md``
Capability: ``events.sec_form4_insider`` in ``capabilities/registry.yaml``.

What this collects
------------------
The SEC publishes "Insider Transactions Data Sets": one zip per calendar
quarter that flattens every Form 3/4/5 *filed* in that quarter into TSV
tables (``SUBMISSION``, ``REPORTINGOWNER``, ``NONDERIV_TRANS``,
``NONDERIV_HOLDING``, ``DERIV_*``, ``FOOTNOTES``, ``OWNER_SIGNATURE``).
URL pattern, verified 2026-09-16 against ``www.sec.gov``::

    https://www.sec.gov/files/structureddata/data/
        insider-transactions-data-sets/{yyyy}q{n}_form345.zip

Quarters are bucketed by ``FILING_DATE``, not by ``TRANS_DATE``: a
2024q1 zip legitimately contains transactions dated 2022 (late filings
are common). That is exactly why the point-in-time rule downstream is
"visible at the next US trading session after ``FILING_DATE``" and why
``TRANS_DATE`` is never used as a visibility timestamp.

Stages (each resumable; rerunning skips finished work)
------------------------------------------------------
``download``
    Fetch ``data/raw/insider/{yyyy}q{n}.zip`` for every quarter in range.
    An existing non-empty zip that opens cleanly is skipped. A missing
    quarter (404) is logged and skipped, never faked.
``parse``
    Flatten each zip into ``data/raw/insider/parsed/{yyyy}q{n}.parquet``
    with the normalized schema documented in :data:`PARSED_COLUMNS`.
    Holdings (``NONDERIV_HOLDING``) are parsed into a sibling
    ``parsed/holdings/{yyyy}q{n}.parquet`` only with ``--with-holdings``
    (cheap: the table is ~5x smaller than ``NONDERIV_TRANS``).
``tail-index``
    The quarterly datasets lag by roughly one quarter plus a week. For
    the tail after the last published quarter, download EDGAR's daily
    form indexes and keep the Form 4/4-A rows, into
    ``data/raw/insider/tail/index/{yyyymmdd}.parquet``.
``tail-fetch``
    Fetch each tail accession's complete submission ``.txt``, pull the
    ``<ownershipDocument>`` XML out of it and parse it into
    ``data/raw/insider/tail/parsed/{yyyymmdd}.parquet``, same normalized
    schema as ``parse``. This is the expensive stage, so it is cut down
    twice: one request per filing (the ``.txt`` already contains the XML,
    unlike the directory-listing route) and, by default, only filings
    whose index CIK is an issuer in the point-in-time top-1,000 ADV
    universe (``--tail-universe-top-n``). The daily index lists a Form 4
    once per filer -- issuer plus every reporting owner -- so that filter
    also deduplicates the accession list. It is chunked per filing day and
    fully resumable (``--tail-max-days`` to run it in slices).

SEC fair access
---------------
``SEC_USER_AGENT`` (contact email, from ``.env`` via ``load_dotenv``;
never read or printed here) is sent on every request, requests are
serialized with a minimum inter-request delay (default 0.15 s, i.e.
<= ~6.7 req/s against the SEC's 10 req/s ceiling), and nothing is
fetched in parallel.

Usage::

    nohup ./scripts/run_capped.sh --mem 1.8G -- \\
        uv run python scripts/collect_sec_insider_transactions.py \\
        --stage download --start 2016q1 > /tmp/insider_download.log 2>&1 &

    nohup ./scripts/run_capped.sh --mem 1.8G -- \\
        uv run python scripts/collect_sec_insider_transactions.py \\
        --stage parse > /tmp/insider_parse.log 2>&1 &

    nohup ./scripts/run_capped.sh --mem 1.8G -- \\
        uv run python scripts/collect_sec_insider_transactions.py \\
        --stage tail-index > /tmp/insider_tail_index.log 2>&1 &
"""

from __future__ import annotations

import argparse
import io
import os
import re
import sys
import time
import zipfile
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402
from dotenv import load_dotenv  # noqa: E402

from open_composer.market_calendar import us_equity_session_dates  # noqa: E402

RAW_ROOT = ROOT / "data" / "raw" / "insider"
PARSED_ROOT = RAW_ROOT / "parsed"
HOLDINGS_ROOT = PARSED_ROOT / "holdings"
TAIL_INDEX_ROOT = RAW_ROOT / "tail" / "index"
TAIL_PARSED_ROOT = RAW_ROOT / "tail" / "parsed"

QUARTERLY_URL = (
    "https://www.sec.gov/files/structureddata/data/"
    "insider-transactions-data-sets/{quarter}_form345.zip"
)
DAILY_INDEX_URL = "https://www.sec.gov/Archives/edgar/daily-index/{year}/QTR{qtr}/form.{stamp}.idx"
ARCHIVE_FILING_JSON = "https://www.sec.gov/Archives/edgar/data/{cik}/{nodash}/index.json"

MIN_REQUEST_INTERVAL_SECONDS = 0.15
HTTP_TIMEOUT_SECONDS = 180
DEFAULT_START_QUARTER = "2016q1"

#: Normalized parsed-transaction schema. One row per
#: (accession, non-derivative transaction, reporting owner).
#:
#: ``owner_seq`` / ``owner_count`` exist because a single Form 4 can be
#: filed jointly by several reporting owners: the *transaction* is
#: reported once but belongs to N owners. Summing ``shares`` over all
#: rows would therefore double-count joint filings. Downstream, share
#: and dollar aggregates must be computed on ``owner_seq == 0`` rows
#: only, while distinct-owner counts use every row.
PARSED_COLUMNS: tuple[str, ...] = (
    "accession",
    "document_type",
    "filing_date",
    "issuer_cik",
    "issuer_symbol",
    "reporting_owner_cik",
    "owner_seq",
    "owner_count",
    "is_director",
    "is_officer",
    "is_ten_percent_owner",
    "is_other_relationship",
    "trans_date",
    "trans_code",
    "acquired_disposed",
    "shares",
    "price_per_share",
    "shares_owned_after",
    "is_10b5_1",
    "is_10b5_1_raw",
    "direct_or_indirect",
    "source_dataset",
)

SUBMISSION_USECOLS = (
    "ACCESSION_NUMBER",
    "FILING_DATE",
    "PERIOD_OF_REPORT",
    "DOCUMENT_TYPE",
    "ISSUERCIK",
    "ISSUERTRADINGSYMBOL",
)
#: Present only from 2023q2 onward (the Rule 10b5-1 amendments added the
#: checkbox to the form). Absent columns become ``<NA>``, never ``False``.
SUBMISSION_OPTIONAL_USECOLS = ("AFF10B5ONE",)
REPORTINGOWNER_USECOLS = ("ACCESSION_NUMBER", "RPTOWNERCIK", "RPTOWNER_RELATIONSHIP")
NONDERIV_TRANS_USECOLS = (
    "ACCESSION_NUMBER",
    "NONDERIV_TRANS_SK",
    "TRANS_DATE",
    "TRANS_CODE",
    "TRANS_SHARES",
    "TRANS_PRICEPERSHARE",
    "TRANS_ACQUIRED_DISP_CD",
    "SHRS_OWND_FOLWNG_TRANS",
    "DIRECT_INDIRECT_OWNERSHIP",
)
NONDERIV_HOLDING_USECOLS = (
    "ACCESSION_NUMBER",
    "SHRS_OWND_FOLWNG_TRANS",
    "DIRECT_INDIRECT_OWNERSHIP",
)


# --------------------------------------------------------------------------
# quarter helpers
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

    The ``SEC_USER_AGENT`` value is read from the process environment and
    used only as a request header; it is never logged or written to an
    artifact.
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
            headers={
                "User-Agent": user_agent,
                "Accept-Encoding": "gzip, deflate",
                "Host": "www.sec.gov",
            },
            timeout=HTTP_TIMEOUT_SECONDS,
            follow_redirects=True,
        )

    def get(self, url: str, *, retries: int = 3) -> tuple[int, bytes]:
        import httpx

        for attempt in range(retries):
            elapsed = time.monotonic() - self._last_request
            if elapsed < self._min_interval:
                time.sleep(self._min_interval - elapsed)
            self._last_request = time.monotonic()
            try:
                response = self._client.get(url)
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
# stage: download
# --------------------------------------------------------------------------


def zip_is_readable(path: Path) -> bool:
    if not path.exists() or path.stat().st_size < 1024:
        return False
    try:
        with zipfile.ZipFile(path) as archive:
            return "SUBMISSION.tsv" in archive.namelist()
    except zipfile.BadZipFile:
        return False


def stage_download(client: SecClient, quarters: list[Quarter]) -> dict[str, str]:
    RAW_ROOT.mkdir(parents=True, exist_ok=True)
    outcome: dict[str, str] = {}
    for quarter in quarters:
        target = RAW_ROOT / f"{quarter}.zip"
        if zip_is_readable(target):
            outcome[str(quarter)] = "already_present"
            log(f"{quarter}: already present ({target.stat().st_size / 1e6:.1f} MB)")
            continue
        url = QUARTERLY_URL.format(quarter=quarter)
        status, payload = client.get(url)
        if status == 404:
            outcome[str(quarter)] = "missing_404"
            log(f"{quarter}: MISSING on sec.gov (HTTP 404) -- skipped, not faked")
            continue
        if status != 200:
            outcome[str(quarter)] = f"http_{status}"
            log(f"{quarter}: HTTP {status} -- skipped")
            continue
        temporary = target.with_suffix(".zip.part")
        temporary.write_bytes(payload)
        if not zip_is_readable(temporary):
            temporary.unlink(missing_ok=True)
            outcome[str(quarter)] = "bad_zip"
            log(f"{quarter}: downloaded payload is not a readable Form 345 zip -- discarded")
            continue
        temporary.replace(target)
        outcome[str(quarter)] = "downloaded"
        log(f"{quarter}: downloaded {target.stat().st_size / 1e6:.1f} MB")
    return outcome


# --------------------------------------------------------------------------
# stage: parse
# --------------------------------------------------------------------------


def _parse_sec_date(series: pd.Series) -> pd.Series:
    """SEC data sets write ``31-JAN-2024``; a few vintages use ISO."""
    text = series.astype("string").str.strip()
    parsed = pd.to_datetime(text, format="%d-%b-%Y", errors="coerce")
    fallback = parsed.isna() & text.notna() & (text != "")
    if fallback.any():
        parsed.loc[fallback] = pd.to_datetime(text[fallback], errors="coerce", format="mixed")
    return parsed


def _read_tsv(archive: zipfile.ZipFile, name: str, usecols: tuple[str, ...]) -> pd.DataFrame:
    with archive.open(name) as handle:
        header = handle.readline().decode("utf-8", "replace").rstrip("\r\n").split("\t")
    available = [column for column in usecols if column in header]
    with archive.open(name) as handle:
        frame = pd.read_csv(
            io.TextIOWrapper(handle, encoding="utf-8", errors="replace"),
            sep="\t",
            usecols=available,
            dtype="string",
            quoting=3,  # csv.QUOTE_NONE -- these TSVs are not quoted
            on_bad_lines="warn",
            low_memory=False,
        )
    for column in usecols:
        if column not in frame.columns:
            frame[column] = pd.Series(pd.NA, index=frame.index, dtype="string")
    return frame


#: Present from 2023q2 onward only (the Rule 10b5-1 amendments added the
#: checkbox to the form); the pre-2023q2 absence of the ``AFF10B5ONE``
#: column and any genuinely blank field both normalize to null here.
#: H-20260916-01's intel brief (2026-09-18): the observed vintages mix
#: ``"0"``/``"1"`` and ``"true"``/``"false"``, and every Form 4/4-A filing
#: from 2023q2 onward carries a non-blank value -- blanks are exclusively
#: Form 3/3-A initial statements, which never reach the transaction-level
#: table (they have no ``NONDERIV_TRANS`` rows to join against).
TEN_B5_ONE_TRUE_TOKENS = frozenset({"1", "true", "y", "yes"})
TEN_B5_ONE_FALSE_TOKENS = frozenset({"0", "false", "n", "no"})


def normalize_10b5_1_flag(raw: pd.Series) -> pd.Series:
    """Normalize a raw ``AFF10B5ONE`` text series to a nullable boolean.

    ``{'1', 'true', 'TRUE', 'Y', 'y'}`` (case-insensitive after stripping) ->
    ``True``; ``{'0', 'false', 'FALSE', 'N', 'n'}`` -> ``False``; empty or
    unrecognized text (including an all-missing column, i.e. every value
    ``pd.NA``) -> ``pd.NA``. Extracted as its own function so the mapping
    can be unit-tested without going through a whole zip.
    """
    lowered = raw.astype("string").str.strip().str.lower()
    result = pd.Series(pd.NA, index=raw.index, dtype="boolean")
    result.loc[lowered.isin(TEN_B5_ONE_TRUE_TOKENS)] = True
    result.loc[lowered.isin(TEN_B5_ONE_FALSE_TOKENS)] = False
    return result


def _owner_flags(relationship: pd.Series) -> pd.DataFrame:
    """``RPTOWNER_RELATIONSHIP`` is a comma-separated token list:
    ``Director``, ``Officer``, ``TenPercentOwner``, ``Other``."""
    text = relationship.fillna("").str.lower()
    return pd.DataFrame(
        {
            "is_director": text.str.contains("director", regex=False),
            "is_officer": text.str.contains("officer", regex=False),
            "is_ten_percent_owner": text.str.contains("tenpercentowner", regex=False),
            "is_other_relationship": text.str.contains("other", regex=False),
        },
        index=relationship.index,
    )


def parse_quarter_archive(path: Path, *, source_dataset: str) -> pd.DataFrame:
    """Flatten one quarterly zip into :data:`PARSED_COLUMNS`."""
    with zipfile.ZipFile(path) as archive:
        submission = _read_tsv(
            archive, "SUBMISSION.tsv", SUBMISSION_USECOLS + SUBMISSION_OPTIONAL_USECOLS
        )
        owners = _read_tsv(archive, "REPORTINGOWNER.tsv", REPORTINGOWNER_USECOLS)
        transactions = _read_tsv(archive, "NONDERIV_TRANS.tsv", NONDERIV_TRANS_USECOLS)
    return assemble_parsed_frame(
        submission=submission,
        owners=owners,
        transactions=transactions,
        source_dataset=source_dataset,
    )


def assemble_parsed_frame(
    *,
    submission: pd.DataFrame,
    owners: pd.DataFrame,
    transactions: pd.DataFrame,
    source_dataset: str,
) -> pd.DataFrame:
    """Join the three SEC tables into the normalized transaction frame.

    Kept separate from :func:`parse_quarter_archive` so tests can drive it
    with small in-memory frames instead of a zip.
    """
    submission = submission.copy()
    submission["filing_date"] = _parse_sec_date(submission["FILING_DATE"])
    submission["issuer_symbol"] = (
        submission["ISSUERTRADINGSYMBOL"].astype("string").str.strip().str.upper()
    )
    submission["issuer_cik"] = pd.to_numeric(submission["ISSUERCIK"], errors="coerce").astype(
        "Int64"
    )
    submission["document_type"] = submission["DOCUMENT_TYPE"].astype("string").str.strip()
    # is_10b5_1_raw keeps the stripped source text (pre-lowercasing) so a
    # future reader can audit the normalization without re-opening the zip.
    submission["is_10b5_1_raw"] = submission["AFF10B5ONE"].astype("string").str.strip()
    submission["is_10b5_1"] = normalize_10b5_1_flag(submission["AFF10B5ONE"])
    submission = submission[
        [
            "ACCESSION_NUMBER",
            "document_type",
            "filing_date",
            "issuer_cik",
            "issuer_symbol",
            "is_10b5_1",
            "is_10b5_1_raw",
        ]
    ]

    owners = owners.copy()
    owners["reporting_owner_cik"] = owners["RPTOWNERCIK"].astype("string").str.strip().str.zfill(10)
    owners = pd.concat([owners, _owner_flags(owners["RPTOWNER_RELATIONSHIP"])], axis=1)
    owners = owners.drop_duplicates(subset=["ACCESSION_NUMBER", "reporting_owner_cik"])
    owners = owners.sort_values(["ACCESSION_NUMBER", "reporting_owner_cik"], kind="stable")
    owners["owner_seq"] = owners.groupby("ACCESSION_NUMBER").cumcount().astype("int16")
    owners["owner_count"] = (
        owners.groupby("ACCESSION_NUMBER")["reporting_owner_cik"].transform("size").astype("int16")
    )
    owners = owners[
        [
            "ACCESSION_NUMBER",
            "reporting_owner_cik",
            "owner_seq",
            "owner_count",
            "is_director",
            "is_officer",
            "is_ten_percent_owner",
            "is_other_relationship",
        ]
    ]

    transactions = transactions.copy()
    transactions["trans_date"] = _parse_sec_date(transactions["TRANS_DATE"])
    transactions["trans_code"] = (
        transactions["TRANS_CODE"].astype("string").str.strip().str.upper().str[:1]
    )
    transactions["acquired_disposed"] = (
        transactions["TRANS_ACQUIRED_DISP_CD"].astype("string").str.strip().str.upper().str[:1]
    )
    transactions["shares"] = pd.to_numeric(transactions["TRANS_SHARES"], errors="coerce")
    transactions["price_per_share"] = pd.to_numeric(
        transactions["TRANS_PRICEPERSHARE"], errors="coerce"
    )
    transactions["shares_owned_after"] = pd.to_numeric(
        transactions["SHRS_OWND_FOLWNG_TRANS"], errors="coerce"
    )
    transactions["direct_or_indirect"] = (
        transactions["DIRECT_INDIRECT_OWNERSHIP"].astype("string").str.strip().str.upper().str[:1]
    )
    transactions = transactions[
        [
            "ACCESSION_NUMBER",
            "trans_date",
            "trans_code",
            "acquired_disposed",
            "shares",
            "price_per_share",
            "shares_owned_after",
            "direct_or_indirect",
        ]
    ]

    merged = transactions.merge(submission, on="ACCESSION_NUMBER", how="inner")
    merged = merged.merge(owners, on="ACCESSION_NUMBER", how="left")
    merged["accession"] = merged["ACCESSION_NUMBER"].astype("string")
    merged["source_dataset"] = source_dataset
    merged = merged.drop(columns=["ACCESSION_NUMBER"])

    for column in ("is_director", "is_officer", "is_ten_percent_owner", "is_other_relationship"):
        merged[column] = merged[column].astype("boolean")
    merged["owner_seq"] = merged["owner_seq"].astype("Int16")
    merged["owner_count"] = merged["owner_count"].astype("Int16")
    merged["reporting_owner_cik"] = merged["reporting_owner_cik"].astype("string")
    merged["source_dataset"] = merged["source_dataset"].astype("string")
    merged["is_10b5_1_raw"] = merged["is_10b5_1_raw"].astype("string")

    result = merged.reindex(columns=list(PARSED_COLUMNS))
    result = result.loc[result["filing_date"].notna()]
    return result.sort_values(["filing_date", "issuer_symbol", "accession"], kind="stable")


def parse_holdings_archive(path: Path) -> pd.DataFrame:
    with zipfile.ZipFile(path) as archive:
        submission = _read_tsv(archive, "SUBMISSION.tsv", SUBMISSION_USECOLS)
        holdings = _read_tsv(archive, "NONDERIV_HOLDING.tsv", NONDERIV_HOLDING_USECOLS)
    submission = submission.assign(
        filing_date=_parse_sec_date(submission["FILING_DATE"]),
        issuer_symbol=submission["ISSUERTRADINGSYMBOL"].astype("string").str.strip().str.upper(),
        issuer_cik=pd.to_numeric(submission["ISSUERCIK"], errors="coerce").astype("Int64"),
    )[["ACCESSION_NUMBER", "filing_date", "issuer_cik", "issuer_symbol"]]
    holdings = holdings.assign(
        shares_owned=pd.to_numeric(holdings["SHRS_OWND_FOLWNG_TRANS"], errors="coerce"),
        direct_or_indirect=holdings["DIRECT_INDIRECT_OWNERSHIP"]
        .astype("string")
        .str.strip()
        .str.upper()
        .str[:1],
    )[["ACCESSION_NUMBER", "shares_owned", "direct_or_indirect"]]
    merged = holdings.merge(submission, on="ACCESSION_NUMBER", how="inner")
    merged["accession"] = merged["ACCESSION_NUMBER"].astype("string")
    return merged.drop(columns=["ACCESSION_NUMBER"])


def stage_parse(quarters: list[Quarter], *, with_holdings: bool, force: bool) -> dict[str, str]:
    PARSED_ROOT.mkdir(parents=True, exist_ok=True)
    outcome: dict[str, str] = {}
    for quarter in quarters:
        source = RAW_ROOT / f"{quarter}.zip"
        target = PARSED_ROOT / f"{quarter}.parquet"
        if not zip_is_readable(source):
            outcome[str(quarter)] = "zip_missing"
            log(f"{quarter}: no readable zip -- parse skipped")
            continue
        if target.exists() and not force:
            outcome[str(quarter)] = "already_parsed"
            log(f"{quarter}: already parsed")
        else:
            frame = parse_quarter_archive(source, source_dataset=f"quarterly:{quarter}")
            temporary = target.with_suffix(".parquet.part")
            frame.to_parquet(temporary, index=False, compression="zstd")
            temporary.replace(target)
            outcome[str(quarter)] = "parsed"
            log(
                f"{quarter}: parsed {len(frame):,} rows "
                f"({frame['issuer_symbol'].nunique():,} symbols)"
            )
            del frame
        if with_holdings:
            HOLDINGS_ROOT.mkdir(parents=True, exist_ok=True)
            holdings_target = HOLDINGS_ROOT / f"{quarter}.parquet"
            if holdings_target.exists() and not force:
                continue
            holdings = parse_holdings_archive(source)
            temporary = holdings_target.with_suffix(".parquet.part")
            holdings.to_parquet(temporary, index=False, compression="zstd")
            temporary.replace(holdings_target)
            log(f"{quarter}: parsed {len(holdings):,} holding rows")
            del holdings
    return outcome


# --------------------------------------------------------------------------
# stage: tail (EDGAR daily index -> Form 4 XML)
# --------------------------------------------------------------------------

FORM4_INDEX_FORMS = {"4", "4/A"}


def latest_parsed_filing_date() -> pd.Timestamp | None:
    files = sorted(PARSED_ROOT.glob("*.parquet"))
    if not files:
        return None
    latest = None
    for path in files[-4:]:
        column = pd.read_parquet(path, columns=["filing_date"])["filing_date"]
        if column.empty:
            continue
        candidate = pd.Timestamp(column.max())
        latest = candidate if latest is None else max(latest, candidate)
    return latest


def _parse_form_idx(payload: bytes) -> pd.DataFrame:
    """EDGAR's fixed-width ``form.YYYYMMDD.idx``: Form Type, Company Name,
    CIK, Date Filed, File Name."""
    rows: list[tuple[str, str, str, str, str]] = []
    started = False
    for raw in payload.decode("latin-1").splitlines():
        if not started:
            if raw.startswith("---") or raw.lstrip().startswith("Form Type"):
                started = raw.startswith("---") or started
                continue
            continue
        if not raw.strip():
            continue
        # The index is space-padded; the last field is the archive path.
        parts = raw.rsplit(None, 1)
        if len(parts) != 2:
            continue
        head, file_name = parts
        form_type = head[:12].strip()
        cik_and_date = head[12:].strip()
        tokens = cik_and_date.rsplit(None, 2)
        if len(tokens) != 3:
            continue
        company, cik, date_filed = tokens
        rows.append((form_type, company, cik, date_filed, file_name))
    frame = pd.DataFrame(
        rows, columns=["form_type", "company_name", "cik", "date_filed", "file_name"]
    )
    return frame.loc[frame["form_type"].isin(FORM4_INDEX_FORMS)].reset_index(drop=True)


def stage_tail_index(
    client: SecClient, *, start: date, end: date, max_days: int | None
) -> dict[str, str]:
    TAIL_INDEX_ROOT.mkdir(parents=True, exist_ok=True)
    outcome: dict[str, str] = {}
    sessions = us_equity_session_dates(start, end)
    processed = 0
    for session in sessions:
        stamp = session.strftime("%Y%m%d")
        target = TAIL_INDEX_ROOT / f"{stamp}.parquet"
        if target.exists():
            outcome[stamp] = "already_present"
            continue
        if max_days is not None and processed >= max_days:
            log(f"tail-index: stopping at --tail-max-days={max_days} (resume by rerunning)")
            break
        url = DAILY_INDEX_URL.format(
            year=session.year, qtr=quarter_of(session).quarter, stamp=stamp
        )
        status, payload = client.get(url)
        processed += 1
        if status == 404:
            outcome[stamp] = "missing_404"
            log(f"tail-index {stamp}: no daily index (HTTP 404) -- likely a market holiday")
            continue
        if status != 200:
            outcome[stamp] = f"http_{status}"
            log(f"tail-index {stamp}: HTTP {status}")
            continue
        frame = _parse_form_idx(payload)
        frame["date_filed"] = pd.to_datetime(frame["date_filed"], errors="coerce")
        temporary = target.with_suffix(".parquet.part")
        frame.to_parquet(temporary, index=False, compression="zstd")
        temporary.replace(target)
        outcome[stamp] = "downloaded"
        log(f"tail-index {stamp}: {len(frame):,} Form 4 filings")
    return outcome


_OWNERSHIP_NS = re.compile(r"\sxmlns(:\w+)?=\"[^\"]*\"")


def parse_form4_xml(payload: bytes, *, accession: str, source_dataset: str) -> pd.DataFrame:
    """Parse one Form 4 ownership XML document into :data:`PARSED_COLUMNS`.

    Only non-derivative transactions are extracted, matching the
    quarterly dataset's ``NONDERIV_TRANS`` table.
    """
    import xml.etree.ElementTree as ET

    text = _OWNERSHIP_NS.sub("", payload.decode("utf-8", "replace"))
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return pd.DataFrame(columns=list(PARSED_COLUMNS))

    def value_of(node: ET.Element | None, *path: str) -> str | None:
        if node is None:
            return None
        current: ET.Element | None = node
        for part in path:
            if current is None:
                return None
            current = current.find(part)
        if current is None:
            return None
        inner = current.find("value")
        target = inner if inner is not None else current
        return (target.text or "").strip() or None

    document_type = (value_of(root, "documentType") or "4").strip()
    issuer = root.find("issuer")
    issuer_cik_text = value_of(issuer, "issuerCik")
    issuer_symbol = (value_of(issuer, "issuerTradingSymbol") or "").upper() or None

    owner_records: list[dict[str, object]] = []
    for owner in root.findall("reportingOwner"):
        cik = value_of(owner, "reportingOwnerId", "rptOwnerCik")
        relationship = owner.find("reportingOwnerRelationship")

        def flag(name: str, node: ET.Element | None = relationship) -> bool:
            text_value = value_of(node, name)
            return str(text_value).strip().lower() in {"1", "true"}

        owner_records.append(
            {
                "reporting_owner_cik": (cik or "").strip().zfill(10) or None,
                "is_director": flag("isDirector"),
                "is_officer": flag("isOfficer"),
                "is_ten_percent_owner": flag("isTenPercentOwner"),
                "is_other_relationship": flag("isOther"),
            }
        )
    if not owner_records:
        owner_records = [
            {
                "reporting_owner_cik": None,
                "is_director": False,
                "is_officer": False,
                "is_ten_percent_owner": False,
                "is_other_relationship": False,
            }
        ]
    owner_records.sort(key=lambda item: str(item["reporting_owner_cik"] or ""))

    aff = value_of(root, "aff10b5One")
    is_10b5_1: bool | None
    if aff is None:
        is_10b5_1 = None
    else:
        is_10b5_1 = aff.strip().lower() in {"1", "true"}

    rows: list[dict[str, object]] = []
    table = root.find("nonDerivativeTable")
    if table is None:
        return pd.DataFrame(columns=list(PARSED_COLUMNS))
    for transaction in table.findall("nonDerivativeTransaction"):
        amounts = transaction.find("transactionAmounts")
        coding = transaction.find("transactionCoding")
        ownership = transaction.find("ownershipNature")
        post = transaction.find("postTransactionAmounts")
        base = {
            "accession": accession,
            "document_type": document_type,
            # filled in by the caller from the EDGAR index's Date Filed --
            # the XML's periodOfReport is a transaction period, never a
            # visibility timestamp.
            "filing_date": pd.NaT,
            "issuer_cik": issuer_cik_text,
            "issuer_symbol": issuer_symbol,
            "trans_date": value_of(transaction, "transactionDate"),
            "trans_code": (value_of(coding, "transactionCode") or "")[:1].upper() or None,
            "acquired_disposed": (value_of(amounts, "transactionAcquiredDisposedCode") or "")[
                :1
            ].upper()
            or None,
            "shares": value_of(amounts, "transactionShares"),
            "price_per_share": value_of(amounts, "transactionPricePerShare"),
            "shares_owned_after": value_of(post, "sharesOwnedFollowingTransaction"),
            "is_10b5_1": is_10b5_1,
            "is_10b5_1_raw": aff,
            "direct_or_indirect": (value_of(ownership, "directOrIndirectOwnership") or "")[
                :1
            ].upper()
            or None,
            "source_dataset": source_dataset,
        }
        for index, owner in enumerate(owner_records):
            rows.append(
                {
                    **base,
                    **owner,
                    "owner_seq": index,
                    "owner_count": len(owner_records),
                }
            )
    frame = pd.DataFrame(rows).reindex(columns=list(PARSED_COLUMNS))
    if frame.empty:
        return frame
    frame["issuer_cik"] = pd.to_numeric(frame["issuer_cik"], errors="coerce").astype("Int64")
    for column in ("shares", "price_per_share", "shares_owned_after"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame["trans_date"] = pd.to_datetime(frame["trans_date"], errors="coerce")
    frame["filing_date"] = pd.to_datetime(frame["filing_date"], errors="coerce")
    frame["owner_seq"] = frame["owner_seq"].astype("Int16")
    frame["owner_count"] = frame["owner_count"].astype("Int16")
    frame["is_10b5_1"] = frame["is_10b5_1"].astype("boolean")
    # Match the quarterly parser's dtypes exactly, so a tail parquet and a
    # quarterly parquet concatenate without an object/extension-dtype mix.
    for column in (
        "accession",
        "document_type",
        "issuer_symbol",
        "reporting_owner_cik",
        "trans_code",
        "acquired_disposed",
        "direct_or_indirect",
        "source_dataset",
        "is_10b5_1_raw",
    ):
        frame[column] = frame[column].astype("string")
    for column in (
        "is_director",
        "is_officer",
        "is_ten_percent_owner",
        "is_other_relationship",
    ):
        frame[column] = frame[column].astype("boolean")
    for column in ("shares", "price_per_share", "shares_owned_after"):
        frame[column] = frame[column].astype("Float64")
    return frame


_OWNERSHIP_BLOCK = re.compile(
    rb"<ownershipDocument.*?</ownershipDocument>", re.DOTALL | re.IGNORECASE
)


def extract_ownership_document(submission_text: bytes) -> bytes | None:
    """Pull the ``<ownershipDocument>`` XML out of an EDGAR ``.txt`` submission.

    Fetching the complete submission text file is one request per filing,
    against three for the directory-listing route (``index.json`` plus the
    XML, plus a retry when the primary document is named unpredictably), so
    at SEC's fair-access rate this is what makes a multi-month tail
    backfill finish in hours rather than a day.
    """
    match = _OWNERSHIP_BLOCK.search(submission_text)
    return match.group(0) if match else None


def universe_issuer_ciks(top_n: int) -> set[int]:
    """Issuer CIKs whose ticker is in the point-in-time universe cohort.

    The daily form index lists a Form 4 once per *filer*, i.e. once for the
    issuer and once for every reporting owner. Keeping only rows whose CIK
    is a universe issuer therefore both deduplicates the accession list and
    drops the ~70% of daily Form 4 traffic that belongs to names we never
    trade.
    """
    from open_composer.research.features.universe import load_universe_panel

    panel = load_universe_panel(ROOT / "data" / "features" / "universe")
    symbols = set(panel.loc[panel["adv_rank"] <= top_n, "symbol"])
    ciks: set[int] = set()
    for path in sorted(PARSED_ROOT.glob("*.parquet")):
        frame = pd.read_parquet(path, columns=["issuer_symbol", "issuer_cik"])
        frame = frame.loc[frame["issuer_symbol"].isin(symbols)]
        ciks.update(int(value) for value in frame["issuer_cik"].dropna().unique())
    return ciks


def stage_tail_fetch(
    client: SecClient, *, max_days: int | None, universe_top_n: int | None
) -> dict[str, str]:
    TAIL_PARSED_ROOT.mkdir(parents=True, exist_ok=True)
    outcome: dict[str, str] = {}
    index_files = sorted(TAIL_INDEX_ROOT.glob("*.parquet"))
    if not index_files:
        log("tail-fetch: no daily indexes yet; run --stage tail-index first")
        return outcome
    allowed: set[int] | None = None
    if universe_top_n is not None:
        allowed = universe_issuer_ciks(universe_top_n)
        log(f"tail-fetch: restricted to {len(allowed):,} universe issuer CIKs")
    processed_days = 0
    for index_path in index_files:
        stamp = index_path.stem
        target = TAIL_PARSED_ROOT / f"{stamp}.parquet"
        if target.exists():
            outcome[stamp] = "already_parsed"
            continue
        if max_days is not None and processed_days >= max_days:
            log(f"tail-fetch: stopping at --tail-max-days={max_days} (resume by rerunning)")
            break
        index = pd.read_parquet(index_path)
        if allowed is not None:
            numeric_cik = pd.to_numeric(index["cik"], errors="coerce")
            index = index.loc[numeric_cik.isin(allowed)]
        index = index.drop_duplicates(subset=["file_name"])
        frames: list[pd.DataFrame] = []
        failures = 0
        for row in index.itertuples(index=False):
            file_name = str(row.file_name)
            accession = Path(file_name).stem  # edgar/data/<cik>/<accession>.txt
            status, payload = client.get(f"https://www.sec.gov/Archives/{file_name}")
            if status != 200:
                failures += 1
                continue
            document = extract_ownership_document(payload)
            if document is None:
                failures += 1
                continue
            frame = parse_form4_xml(document, accession=accession, source_dataset=f"tail:{stamp}")
            if not frame.empty:
                frame["filing_date"] = pd.to_datetime(row.date_filed)
                frames.append(frame)
        combined = (
            pd.concat(frames, ignore_index=True)
            if frames
            else pd.DataFrame(columns=list(PARSED_COLUMNS))
        )
        temporary = target.with_suffix(".parquet.part")
        combined.to_parquet(temporary, index=False, compression="zstd")
        temporary.replace(target)
        processed_days += 1
        outcome[stamp] = "fetched"
        log(
            f"tail-fetch {stamp}: {len(index):,} filings -> {len(combined):,} transaction rows "
            f"({failures} could not be retrieved)"
        )
    return outcome


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--stage",
        choices=("download", "parse", "quarterly", "tail-index", "tail-fetch"),
        default="quarterly",
        help="'quarterly' runs download then parse (default).",
    )
    parser.add_argument("--start", type=parse_quarter, default=parse_quarter(DEFAULT_START_QUARTER))
    parser.add_argument(
        "--end",
        type=parse_quarter,
        default=None,
        help="Last quarter to attempt. Default: the quarter containing today.",
    )
    parser.add_argument("--with-holdings", action="store_true")
    parser.add_argument("--force", action="store_true", help="Re-parse quarters already parsed.")
    parser.add_argument("--tail-start", type=str, default=None, help="YYYY-MM-DD.")
    parser.add_argument("--tail-end", type=str, default=None, help="YYYY-MM-DD, default today.")
    parser.add_argument("--tail-max-days", type=int, default=None)
    parser.add_argument(
        "--tail-universe-top-n",
        type=int,
        default=1000,
        help=(
            "tail-fetch only: keep filings whose index CIK is a universe issuer with "
            "adv_rank <= N. 0 disables the filter and fetches every Form 4 (about 3x "
            "the requests)."
        ),
    )
    parser.add_argument("--min-request-interval", type=float, default=MIN_REQUEST_INTERVAL_SECONDS)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    load_dotenv(ROOT / ".env")
    today = date.today()
    end_quarter = args.end or quarter_of(today)
    quarters = quarter_range(args.start, end_quarter)

    if args.stage == "parse":
        stage_parse(quarters, with_holdings=args.with_holdings, force=args.force)
        return 0

    client = SecClient(min_interval=args.min_request_interval)
    try:
        if args.stage == "download":
            stage_download(client, quarters)
        elif args.stage == "quarterly":
            stage_download(client, quarters)
            stage_parse(quarters, with_holdings=args.with_holdings, force=args.force)
        elif args.stage == "tail-index":
            latest = latest_parsed_filing_date()
            if args.tail_start:
                start = date.fromisoformat(args.tail_start)
            elif latest is not None:
                start = (latest + pd.Timedelta(days=1)).date()
            else:
                raise SystemExit("no parsed quarters yet; pass --tail-start")
            end = date.fromisoformat(args.tail_end) if args.tail_end else today
            log(f"tail-index range: {start} .. {end}")
            stage_tail_index(client, start=start, end=end, max_days=args.tail_max_days)
        elif args.stage == "tail-fetch":
            stage_tail_fetch(
                client,
                max_days=args.tail_max_days,
                universe_top_n=args.tail_universe_top_n or None,
            )
    finally:
        client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
