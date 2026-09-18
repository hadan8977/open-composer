"""H-20260916-07 follow-up: FINRA daily consolidated short-sale-VOLUME collector.

Card: ``reports/research/hypotheses/H-20260916-07-finra-short-interest-avoid-list.md``
refuted the bimonthly short-INTEREST snapshot (21-day residual -0.18%, not
individually significant). The 2026-09-18 intel brief's reading of that
result: the mechanism that actually replicates in the literature (Boehmer,
Jones and Zhang, "Which Shorts Are Informed?") is a DAILY short-volume FLOW,
not a twice-a-month position snapshot -- a data-granularity gap, not a dead
end. This collector closes that gap for free.

This is deliberately a *different* dataset from the one
``scripts/collect_finra_short_interest.py`` explicitly declined. That
collector's docstring says (correctly, for what it was evaluating): daily
short *sale volume* "cannot be read as bearish sentiment" because it is
dominated by market-maker hedging, not conviction. That caveat is about
reading the raw share count as a directional signal. It says nothing about
the RATIO construct built here (short volume / total volume, and that
ratio's own trailing z-score) -- the normalization the published literature
actually uses and the one this module and ``build_short_volume_features.py``
compute. Nothing about "not bearish sentiment" implies "not informative as a
relative flow measure"; those are two different claims and this module tests
the second one, not the first.

What this collects
-------------------
FINRA's Regulation SHO "Daily Short Sale Volume" files -- one file per US
equity trading session, aggregated **across the FINRA-operated Trade
Reporting Facilities, the ADF and the ORF** (i.e. off-exchange / OTC
executions; lit-exchange-matched volume is not FINRA's to report and is not
in this file). Six datasets exist per day, one per reporting facility
(``CNMS`` = all facilities consolidated into one row per symbol, ``FNQC`` =
NASDAQ TRF Chicago, ``FNRA``/``FORF`` = ADF/ORF, ``FNSQ`` = NASDAQ TRF
Carteret, ``FNYX`` = NYSE TRF). This collector deliberately pulls only
``CNMS`` (Consolidated NMS): it is already one row per ``(trade_date,
symbol)`` with volumes summed across whichever facilities traded that name
that day (its own ``Market`` column lists which ones, e.g. ``"B,Q,N"``), so
the ratio construct never has to re-aggregate five per-facility files and
risk double-counting or under-counting a symbol that traded on a subset of
them. The five single-facility files are not collected.

Source, verified 2026-09-18
----------------------------
Static files on FINRA's CDN, no credentials, no query API::

    https://cdn.finra.org/equity/regsho/daily/CNMSshvol{YYYYMMDD}.txt

Confirmed live during this build (not taken from memory):

* ``CNMSshvol20180801.txt`` -> HTTP 200 (header + 7,676 data rows + trailer).
* ``CNMSshvol20180731.txt`` -> HTTP 403 (the prior US equity session).
* FINRA's own catalog page (``finra.org/finra-data/browse-catalog/
  short-sale-volume-data/daily-short-sale-volume-files``) states: "The
  earliest date for the Consolidated NMS files is August 1, 2018." The live
  403/200 boundary above reproduces that claim exactly, so
  :data:`FIRST_AVAILABLE_DATE` is measured, not assumed.
* Weekends, exchange holidays and pre-2018-08-01 dates all return HTTP 403
  from this endpoint -- there is no header distinguishing "not a trading day"
  from "not yet available" from FINRA's response alone. This collector never
  requests a non-session date (:func:`open_composer.market_calendar.
  us_equity_session_dates` already excludes them), so every 403 this
  collector sees is either the pre-2018-08-01 boundary or a genuine gap on a
  real trading session, and the two are distinguished by date, not by
  guessing from the HTTP response.
* File layout (``finra.org/sites/default/files/2021-07/
  DailyShortSaveVolumeFileLayout.pdf`` for the per-facility 6-column format,
  confirmed against the live CNMS header
  ``Date|Symbol|ShortVolume|ShortExemptVolume|TotalVolume|Market``): pipe
  delimited, header row, one data row per symbol, a bare-integer trailer row
  giving the file's own record count -- used here as a downloaded-file
  integrity check, the same role FINRA's ``record-total`` header plays in
  ``collect_finra_short_interest.py``.
* "In the event there is no short data for a particular day, a file will
  still be produced for that day that will only contain a header and a
  trailer with a count of 0" (FINRA's own file-layout note) -- so a
  present-but-empty file is a real, documented outcome and is recorded as
  such (``ok_zero_rows``), never conflated with a missing file.
* Since 2026-02-23 FINRA reports fractional NMS share quantities to six
  decimal places (Trade Reporting Notice 2026-01-14); every volume column is
  therefore stored as float64 from day one so the parquet schema never has to
  change type partway through the archive.

Publication (visibility) rule -- established, not guessed
-----------------------------------------------------------
FINRA's own daily-file catalog page states files are "posted no later than
6:00:00pm ET of the same day on the relevant trade date." This was checked
empirically during this build, not just quoted: ``CNMSshvol20260917.txt``'s
HTTP ``Last-Modified`` header was ``Thu, 17 Sep 2026 21:18:21 GMT`` (17:18
America/New_York, before the stated 18:00 cutoff), and a request for
``CNMSshvol20260918.txt`` (the current session, requested mid-afternoon ET)
returned HTTP 403 -- i.e. not yet posted intraday, consistent with an
end-of-day release. So:

* ``publication_date = trade_date`` (the file is released the evening of the
  session it describes, not the next calendar day).
* ``visible_date = next_us_equity_session(trade_date)``: nothing may condition
  on the file during the session it was released after close, since a release
  hours after that session's own close cannot have affected that session's
  trading. The first session on which the file's content could plausibly
  inform a decision is the next one.
* This is the same "whole publication session is unusable" convention
  ``collect_finra_short_interest.py`` uses for its own publication dates, and
  ``scripts/build_short_volume_features.py``'s docstring restates and enforces
  it on the feature side.
* If FINRA ever changes this posting time (no evidence found that it has),
  :data:`PUBLICATION_SAME_DAY` records the assumption in one place so it is
  easy to audit or revise.

Terms of use
------------
Same FINRA "non-commercial use of FINRA Data" restriction as
``collect_finra_short_interest.py``; this repo's use is personal research.

Stages (each resumable; rerunning skips finished work)
--------------------------------------------------------
``download``
    One gzipped raw text file per US equity session under
    ``data/raw/finra_short_volume/cnms/{yyyy-mm-dd}.txt.gz``, byte-identical
    to what FINRA served (header, data rows, trailer). An existing file whose
    stored row count matches its own trailer count is skipped. Polite: a
    minimum inter-request delay and exponential backoff retry on
    403/429/5xx/transport errors; a date that still fails after retries is
    reported as MISSING, not silently absent.
``parse``
    Stream every raw file into ``data/raw/finra_short_volume/parsed.parquet``
    (one parquet row group per trade date, so peak memory is one day) with
    the normalized schema in :data:`PARSED_COLUMNS`.
``manifest``
    Rewrite ``data/raw/finra_short_volume/manifest.json`` from what is on
    disk: per-day row count/bytes/sha256, plus the explicit
    missing-vs-not-published accounting the task requires. ``parse`` calls it
    for you.
``probe``
    Reproduce the 403/200 boundary at :data:`FIRST_AVAILABLE_DATE` live and
    print a calendar sanity check, without downloading the full archive.

Usage::

    ./scripts/run_capped.sh --mem 1.8G -- \\
        uv run python scripts/collect_finra_short_volume.py --stage probe

    nohup ./scripts/run_capped.sh --mem 1.8G -- \\
        uv run python scripts/collect_finra_short_volume.py \\
        --stage download > /tmp/finra_sv_download.log 2>&1 &

    ./scripts/run_capped.sh --mem 1.8G -- \\
        uv run python scripts/collect_finra_short_volume.py --stage parse
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import sys
import time
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import json  # noqa: E402

import pandas as pd  # noqa: E402

from open_composer.market_calendar import (  # noqa: E402
    next_us_equity_session,
    us_equity_session_close,
    us_equity_session_dates,
)

RAW_ROOT = ROOT / "data" / "raw" / "finra_short_volume"
DAILY_ROOT = RAW_ROOT / "cnms"
PARSED_PATH = RAW_ROOT / "parsed.parquet"
MANIFEST_PATH = RAW_ROOT / "manifest.json"

BASE_URL = "https://cdn.finra.org/equity/regsho/daily"
FILE_PREFIX = "CNMSshvol"
DATASET = "CNMS (Consolidated NMS)"
SOURCE_ID = "finra_cdn:equity/regsho/daily/CNMSshvol"
CATALOG_URL = (
    "https://www.finra.org/finra-data/browse-catalog/"
    "short-sale-volume-data/daily-short-sale-volume-files"
)

#: Measured live (see module docstring), matches FINRA's own catalog text.
FIRST_AVAILABLE_DATE = date(2018, 8, 1)

#: FINRA: "posted no later than 6:00:00pm ET of the same day on the relevant
#: trade date" -- empirically checked against a live Last-Modified header,
#: see module docstring. A trade date's own session is always unusable.
PUBLICATION_SAME_DAY = True
PUBLICATION_CUTOFF_HOUR_ET = 18
NEW_YORK = ZoneInfo("America/New_York")

MIN_REQUEST_INTERVAL_SECONDS = 0.5
HTTP_TIMEOUT_SECONDS = 60
RETRYABLE_STATUS_CODES = {403, 429, 500, 502, 503, 504}

RAW_HEADER_COLUMNS: tuple[str, ...] = (
    "Date",
    "Symbol",
    "ShortVolume",
    "ShortExemptVolume",
    "TotalVolume",
    "Market",
)

FIELD_RENAME: dict[str, str] = {
    "Symbol": "symbol",
    "ShortVolume": "short_volume",
    "ShortExemptVolume": "short_exempt_volume",
    "TotalVolume": "total_volume",
    "Market": "market_facilities",
}

#: Normalized parsed schema, in table order. One row per (trade_date, symbol).
PARSED_COLUMNS: tuple[str, ...] = (
    "trade_date",
    "publication_date",
    "visible_date",
    "symbol",
    "short_volume",
    "short_exempt_volume",
    "total_volume",
    "market_facilities",
    "source",
    "fetched_at",
    "input_hash",
)

NUMERIC_COLUMNS: tuple[str, ...] = ("short_volume", "short_exempt_volume", "total_volume")
STRING_COLUMNS: tuple[str, ...] = ("symbol", "market_facilities", "source", "input_hash")

#: Outcomes that mean "a real, correctly-downloaded file exists for this day"
#: -- as opposed to a genuine gap. ``ok_zero_rows`` is FINRA's own documented
#: "no short data today" file (header + trailer count 0), not a failure.
OK_OUTCOMES = {"ok", "ok_zero_rows", "skip_complete"}


def log(message: str) -> None:
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{stamp}] {message}", flush=True)


# --------------------------------------------------------------------------
# visibility helpers
# --------------------------------------------------------------------------


def last_expected_available_session(now: datetime | None = None) -> date:
    """The most recent trade date whose file should already be postable,
    given FINRA's own "by 6:00pm ET same day" rule (see module docstring).

    Used only to pick a sensible default upper bound for ``--end``/``--as-of``
    so that "today, requested before the file could exist" is never reported
    as a missing day.
    """
    now_utc = now.astimezone(UTC) if now is not None else datetime.now(tz=UTC)
    now_et = now_utc.astimezone(NEW_YORK)
    candidate = now_et.date()
    if not (
        us_equity_session_close(candidate) is not None and now_et.hour >= PUBLICATION_CUTOFF_HOUR_ET
    ):
        candidate -= timedelta(days=1)
    while us_equity_session_close(candidate) is None:
        candidate -= timedelta(days=1)
    return candidate


# --------------------------------------------------------------------------
# HTTP
# --------------------------------------------------------------------------


class FinraCdnClient:
    """Serialized, rate-limited client for FINRA's static short-volume CDN.

    No credential is read or required: ``cdn.finra.org/equity/regsho`` is a
    public static file host.
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

    def get(self, url: str, *, retries: int = 4) -> tuple[int, bytes, str | None]:
        """``(status, body, last_modified)``. Retries transient failures
        (including 403, since this CDN gives no distinct code for "blocked"
        vs "genuinely absent") with exponential backoff.
        """
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
            if response.status_code in RETRYABLE_STATUS_CODES:
                if attempt == retries - 1:
                    return response.status_code, response.content, None
                log(f"  HTTP {response.status_code}, backing off (attempt {attempt + 1})")
                time.sleep(5.0 * (attempt + 1))
                continue
            return response.status_code, response.content, response.headers.get("last-modified")
        raise RuntimeError("unreachable")

    def close(self) -> None:
        self._client.close()


# --------------------------------------------------------------------------
# stage: download
# --------------------------------------------------------------------------


def _raw_path(day: date) -> Path:
    return DAILY_ROOT / f"{day.isoformat()}.txt.gz"


def _read_raw_lines(path: Path) -> list[str] | None:
    if not path.exists() or path.stat().st_size == 0:
        return None
    with gzip.open(path, "rt", encoding="utf-8", newline="") as handle:
        return handle.read().splitlines()


def _trailer_count(lines: list[str]) -> int | None:
    if len(lines) < 2:
        return None
    try:
        return int(lines[-1].strip())
    except ValueError:
        return None


def _raw_row_count(path: Path) -> int:
    """Data-row count (excluding header and trailer), or -1 if unusable."""
    lines = _read_raw_lines(path)
    if lines is None or len(lines) < 2:
        return -1
    return len(lines) - 2


def download_day(client: FinraCdnClient, day: date) -> tuple[str, int]:
    """``(outcome, rows)`` for one trade date, written atomically.

    ``outcome`` is one of ``skip_complete``, ``ok``, ``ok_zero_rows``,
    ``ok_trailer_mismatch_{n}_vs_{m}`` (stored anyway, flagged for audit), or
    ``http_{code}`` for a genuine failure after retries.
    """
    path = _raw_path(day)
    existing_lines = _read_raw_lines(path)
    if existing_lines is not None:
        existing_trailer = _trailer_count(existing_lines)
        if existing_trailer is not None and existing_trailer == len(existing_lines) - 2:
            return "skip_complete", existing_trailer

    url = f"{BASE_URL}/{FILE_PREFIX}{day.strftime('%Y%m%d')}.txt"
    status, payload, _ = client.get(url)
    if status != 200:
        return f"http_{status}", 0

    lines = payload.decode("utf-8", errors="replace").splitlines()
    if len(lines) < 2:
        return "malformed_too_short", 0
    header, *rest = lines
    if not rest:
        return "malformed_no_trailer", 0
    body, trailer_line = rest[:-1], rest[-1]
    trailer_count = _trailer_count([header, trailer_line])
    if trailer_count is None:
        return "malformed_trailer", 0

    DAILY_ROOT.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".txt.gz.part")
    with gzip.open(temporary, "wt", encoding="utf-8", newline="\n") as handle:
        handle.write(header + "\n")
        for line in body:
            handle.write(line + "\n")
        handle.write(trailer_line + "\n")
    temporary.replace(path)

    if trailer_count != len(body):
        return f"ok_trailer_mismatch_{len(body)}_vs_{trailer_count}", len(body)
    if trailer_count == 0:
        return "ok_zero_rows", 0
    return "ok", len(body)


def stage_download(client: FinraCdnClient, *, start: date, end: date) -> int:
    if start < FIRST_AVAILABLE_DATE:
        log(
            f"requested start {start} is before the measured earliest available date "
            f"{FIRST_AVAILABLE_DATE}; clamping (see module docstring for the live 403/200 check)"
        )
        start = FIRST_AVAILABLE_DATE
    sessions = us_equity_session_dates(start, end)
    span = f"{sessions[0]}..{sessions[-1]}" if sessions else "-"
    log(f"{len(sessions)} US equity sessions requested, {span}")
    missing: list[date] = []
    mismatched: list[date] = []
    for index, day in enumerate(sessions, start=1):
        outcome, rows = download_day(client, day)
        if outcome not in OK_OUTCOMES and not outcome.startswith("ok"):
            missing.append(day)
        elif outcome.startswith("ok_trailer_mismatch"):
            mismatched.append(day)
        log(f"[{index}/{len(sessions)}] {day}: {outcome} rows={rows:,}")
    log(f"download finished: {len(missing)} MISSING of {len(sessions)} requested sessions")
    if missing:
        missing_iso = [d.isoformat() for d in missing]
        log(f"MISSING dates (genuine gaps, not holidays -- retry these): {missing_iso}")
    if mismatched:
        mismatched_iso = [d.isoformat() for d in mismatched]
        log(f"trailer-count mismatches (stored anyway, flagged): {mismatched_iso}")
    return 1 if missing else 0


# --------------------------------------------------------------------------
# stage: parse
# --------------------------------------------------------------------------


def parsed_schema() -> object:
    import pyarrow as pa

    fields = []
    for column in PARSED_COLUMNS:
        if column in {"trade_date", "publication_date", "visible_date"}:
            fields.append(pa.field(column, pa.timestamp("s")))
        elif column == "fetched_at":
            fields.append(pa.field(column, pa.timestamp("us", tz="UTC")))
        elif column in NUMERIC_COLUMNS:
            fields.append(pa.field(column, pa.float64()))
        else:
            fields.append(pa.field(column, pa.string()))
    return pa.schema(fields)


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _file_day(path: Path) -> date:
    return date.fromisoformat(path.name.split(".")[0])


def parse_raw_file(path: Path) -> pd.DataFrame:
    """One raw trade-date file as the normalized :data:`PARSED_COLUMNS`."""
    day = _file_day(path)
    lines = _read_raw_lines(path)
    if lines is None or len(lines) < 2:
        raise ValueError(f"{path}: unreadable or too short to contain header+trailer")
    header, *rest = lines
    body = rest[:-1]
    frame = pd.read_csv(io.StringIO("\n".join([header, *body])), sep="|", dtype=str)
    frame = frame.rename(columns=FIELD_RENAME)
    for column in PARSED_COLUMNS:
        if column not in frame.columns:
            frame[column] = None
    frame["trade_date"] = pd.Timestamp(day)
    frame["publication_date"] = pd.Timestamp(day)
    frame["visible_date"] = pd.Timestamp(next_us_equity_session(day))
    for column in NUMERIC_COLUMNS:
        frame[column] = pd.to_numeric(frame[column], errors="coerce").astype("float64")
    frame["symbol"] = frame["symbol"].astype(str).str.strip().str.upper()
    frame["market_facilities"] = frame["market_facilities"].astype(str).str.strip()
    frame["source"] = SOURCE_ID
    frame["fetched_at"] = pd.Timestamp(datetime.fromtimestamp(path.stat().st_mtime, tz=UTC))
    frame["input_hash"] = _file_hash(path)
    frame = frame.loc[frame["symbol"].str.len() > 0]
    frame = frame.drop_duplicates(subset=["trade_date", "symbol"], keep="last")
    for column in STRING_COLUMNS:
        frame[column] = frame[column].astype("string")
    return frame[list(PARSED_COLUMNS)].sort_values("symbol", ignore_index=True)


def stage_parse(*, force: bool) -> int:
    import pyarrow as pa
    import pyarrow.parquet as pq

    if PARSED_PATH.exists() and not force:
        log(f"{PARSED_PATH.name}: already present -- rerun with --force to rebuild")
        return stage_manifest()
    paths = sorted(DAILY_ROOT.glob("*.txt.gz"), key=_file_day)
    if not paths:
        log(f"no raw files under {DAILY_ROOT.relative_to(ROOT)} -- run --stage download")
        return 1
    temporary = PARSED_PATH.with_suffix(".parquet.part")
    schema = parsed_schema()
    writer: pq.ParquetWriter | None = None
    total = 0
    try:
        for index, path in enumerate(paths, start=1):
            frame = parse_raw_file(path)
            table = pa.Table.from_pandas(frame, schema=schema, preserve_index=False)
            if writer is None:
                writer = pq.ParquetWriter(temporary, schema, compression="zstd")
            writer.write_table(table)
            total += len(frame)
            if index % 100 == 0 or index == len(paths):
                log(f"[{index}/{len(paths)}] {path.name}: {total:,} rows so far")
    finally:
        if writer is not None:
            writer.close()
    temporary.replace(PARSED_PATH)
    log(f"wrote {PARSED_PATH.relative_to(ROOT)}: {total:,} rows from {len(paths)} trade dates")
    return stage_manifest()


# --------------------------------------------------------------------------
# stage: manifest
# --------------------------------------------------------------------------


def stage_manifest(*, as_of: date | None = None) -> int:
    paths = sorted(DAILY_ROOT.glob("*.txt.gz"), key=_file_day)
    downloaded_days = {_file_day(path) for path in paths}
    files = []
    for path in paths:
        rows = _raw_row_count(path)
        files.append(
            {
                "trade_date": _file_day(path).isoformat(),
                "bytes": path.stat().st_size,
                "rows": rows,
                "sha256": _file_hash(path),
            }
        )
    zero_row_days = sorted(item["trade_date"] for item in files if item["rows"] == 0)

    as_of = as_of or last_expected_available_session()
    expected_sessions = (
        us_equity_session_dates(FIRST_AVAILABLE_DATE, as_of)
        if as_of >= FIRST_AVAILABLE_DATE
        else ()
    )
    missing_days = sorted(
        day.isoformat() for day in expected_sessions if day not in downloaded_days
    )

    parsed_rows: int | None = None
    parsed_span: list[str] | None = None
    if PARSED_PATH.exists():
        import pyarrow.parquet as pq

        parsed = pq.ParquetFile(PARSED_PATH)
        parsed_rows = parsed.metadata.num_rows
        dates = pd.read_parquet(PARSED_PATH, columns=["trade_date"])["trade_date"]
        if len(dates):
            parsed_span = [str(dates.min().date()), str(dates.max().date())]

    payload = {
        "capability": "market.finra_short_volume",
        "dataset": DATASET,
        "source": SOURCE_ID,
        "base_url": BASE_URL,
        "catalog_url": CATALOG_URL,
        "terms": "FINRA states non-commercial use of FINRA Data; personal research only",
        "generated_at": pd.Timestamp.now(tz="UTC").isoformat(),
        "first_available_date": FIRST_AVAILABLE_DATE.isoformat(),
        "first_available_date_evidence": (
            "live-checked 2026-09-18: CNMSshvol20180801.txt -> HTTP 200, "
            "CNMSshvol20180731.txt -> HTTP 403; matches FINRA's own catalog page text "
            "'The earliest date for the Consolidated NMS files is August 1, 2018.'"
        ),
        "publication_rule": "publication_date = trade_date (posted by ~18:00 ET same day); "
        "visible_date = next_us_equity_session(trade_date)",
        "publication_rule_evidence": (
            "FINRA catalog page: 'posted no later than 6:00:00pm ET of the same day on the "
            "relevant trade date'; empirically checked 2026-09-18: CNMSshvol20260917.txt "
            "Last-Modified 21:18:21 GMT (17:18 America/New_York, before the stated cutoff), "
            "and CNMSshvol20260918.txt (same session, requested intraday) returned HTTP 403"
        ),
        "as_of": as_of.isoformat(),
        "expected_trading_sessions": len(expected_sessions),
        "downloaded_days": len(downloaded_days),
        "missing_days_count": len(missing_days),
        "missing_days": missing_days,
        "zero_row_days_count": len(zero_row_days),
        "zero_row_days": zero_row_days,
        "raw_rows": sum(item["rows"] for item in files if item["rows"] > 0),
        "parsed_rows": parsed_rows,
        "parsed_trade_date_span": parsed_span,
        "files": files,
    }
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    log(
        f"wrote {MANIFEST_PATH.relative_to(ROOT)}: {len(files)} days on disk, "
        f"{len(missing_days)} missing of {len(expected_sessions)} expected sessions "
        f"through {as_of}, parsed_rows={parsed_rows}"
    )
    return 1 if missing_days else 0


# --------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--stage",
        required=True,
        choices=["download", "parse", "manifest", "probe"],
    )
    parser.add_argument(
        "--start",
        default=FIRST_AVAILABLE_DATE.isoformat(),
        help="first trade date to download (default: the earliest FINRA exposes)",
    )
    parser.add_argument(
        "--end",
        default=None,
        help="last trade date to download (default: the most recent session whose "
        "file should already be posted)",
    )
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)

    RAW_ROOT.mkdir(parents=True, exist_ok=True)
    if args.stage == "manifest":
        return stage_manifest()
    if args.stage == "parse":
        return stage_parse(force=args.force)

    client = FinraCdnClient()
    try:
        if args.stage == "probe":
            before = FIRST_AVAILABLE_DATE - timedelta(days=1)
            while us_equity_session_close(before) is None:
                before -= timedelta(days=1)
            status_before, _, _ = client.get(
                f"{BASE_URL}/{FILE_PREFIX}{before.strftime('%Y%m%d')}.txt"
            )
            status_first, _, last_modified = client.get(
                f"{BASE_URL}/{FILE_PREFIX}{FIRST_AVAILABLE_DATE.strftime('%Y%m%d')}.txt"
            )
            log(f"session before first-available ({before}): HTTP {status_before} (expect 403)")
            log(f"first-available ({FIRST_AVAILABLE_DATE}): HTTP {status_first} (expect 200)")
            log(f"last_expected_available_session() = {last_expected_available_session()}")
            sessions = us_equity_session_dates(FIRST_AVAILABLE_DATE, date.today())
            log(
                f"calendar sanity: {len(sessions)} US sessions from {FIRST_AVAILABLE_DATE} to today"
            )
            return 0
        end = date.fromisoformat(args.end) if args.end else last_expected_available_session()
        return stage_download(client, start=date.fromisoformat(args.start), end=end)
    finally:
        client.close()


if __name__ == "__main__":
    raise SystemExit(main())
