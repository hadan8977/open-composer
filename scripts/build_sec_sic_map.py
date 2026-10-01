"""Free industry classification: SEC SIC codes mapped to Fama-French 48 / 12.

Why: the multi-signal equity book needs an industry label per symbol for
risk-model grouping and industry neutralization; the project had none.
Queue entry ``T-20260930-02`` (field ``plan``, "新增数据") specified this
build; this script is its data half only (no signal test lives here).

Pipeline
--------
1. Universe: every distinct symbol in ``data/features/universe_broad/*.parquet``
   (read with duckdb), minus probable ETFs/funds, flagged exactly as
   ``open_composer.research.features.universe.exclude_funds_and_etfs`` does
   (``is_probable_fund_or_etf`` in
   ``data/features/universe/_asset_metadata.parquet``; a symbol absent from
   that metadata is kept).
2. Symbol -> CIK: ``data/raw/sec_ma/cik_symbol_history.parquet`` (cik,
   symbol, first_date, last_date; includes delisted names) is the primary
   map and keeps its date ranges, so a symbol reused by two CIKs over time
   maps to each CIK only for its own period. ``data/raw/sec_xbrl/
   company_tickers.json`` (current SEC list) is the fallback for symbols
   missing from the history table; those rows carry null link dates
   (= unbounded, the current mapping).
3. SIC per CIK: preferred source is the SEC bulk file
   ``https://www.sec.gov/Archives/edgar/daily-index/bulkdata/submissions.zip``
   (one streamed download, then only the needed ``CIK##########.json``
   members are read, one at a time; ``CIK##########-submissions-NNN.json``
   pagination members are skipped). Fallback (bulk download fails, or
   ``--source api``): ``https://data.sec.gov/submissions/CIK##########.json``
   per CIK at <= 5 requests/second with backoff on 403/429/5xx and a
   resumable JSONL checkpoint.
4. SIC -> industry: Ken French's ``Siccodes48.zip`` / ``Siccodes12.zip``
   range files (raw copies under ``data/raw/french_industry/``). A SIC in
   no range goes to 48 "Other" / 12 "Other"; a missing SIC maps to the same
   two "Other" buckets with ``sic`` null.

Known limitation: SIC is the registrant's CURRENT code in EDGAR, not a
point-in-time classification. A company that changed business keeps its
latest SIC for all of history. ``coverage.json`` counts the CIKs whose
``formerNames`` list is non-empty as a rough indicator of identity changes
(it is not a SIC-change count).

Date caveat for consumers: the SEC symbol history dates a link only while the
ticker was in force there, but price bars here are keyed by the current ticker
for the whole history (META carries 2016+ bars, the history row starts
2022-06-09). Use :func:`lookup_sic_row`: a covering link is ``date_verified``,
otherwise the nearest link is returned unverified. ``coverage.json`` reports
both the date-verified share and the any-period share.

Capability registry: ``capabilities/registry.yaml`` entry
``events.sec_filings`` does not cover ``data.sec.gov`` submissions, so
``reference.sec_sic_industry`` registers this source.

SEC fair access: ``SEC_USER_AGENT`` is read from the process environment
through ``load_dotenv`` inside :class:`SecClient` (imported from
``scripts/build_sec_xbrl_fundamentals.py``); this script never opens,
prints or logs it.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import duckdb  # noqa: E402
import pandas as pd  # noqa: E402

HISTORY_PATH = ROOT / "data" / "raw" / "sec_ma" / "cik_symbol_history.parquet"
TICKERS_PATH = ROOT / "data" / "raw" / "sec_xbrl" / "company_tickers.json"
UNIVERSE_BROAD_GLOB = ROOT / "data" / "features" / "universe_broad" / "*.parquet"
ASSET_METADATA_PATH = ROOT / "data" / "features" / "universe" / "_asset_metadata.parquet"
SUBMISSIONS_DIR = ROOT / "data" / "raw" / "sec_submissions"
SUBMISSIONS_ZIP = SUBMISSIONS_DIR / "submissions.zip"
API_CHECKPOINT = SUBMISSIONS_DIR / "submissions_api_checkpoint.jsonl"
FRENCH_DIR = ROOT / "data" / "raw" / "french_industry"
OUT_DIR = ROOT / "data" / "features" / "sic_map"
OUT_PATH = OUT_DIR / "sic_map.parquet"
COVERAGE_PATH = OUT_DIR / "coverage.json"

SUBMISSIONS_ZIP_URL = "https://www.sec.gov/Archives/edgar/daily-index/bulkdata/submissions.zip"
SUBMISSIONS_API_URL = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
FRENCH_URL = "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/{name}.zip"

API_MIN_INTERVAL_SECONDS = 0.2  # <= 5 requests per second
POOLS = {"P1000": 1000, "P1500": 1500, "P3000": 3000}
MIN_CLOSE = 5.0
MEMBER_RE = re.compile(r"^CIK(\d{10})\.json$")
RANGE_RE = re.compile(r"^\s+(\d{4})-(\d{4})\b")
HEADER_RE = re.compile(r"^\s*(\d{1,2})\s+(\S+)\s+(.*\S)\s*$")

OUTPUT_COLUMNS = [
    "symbol",
    "cik",
    "link_first_date",
    "link_last_date",
    "sic",
    "sic_description",
    "ff48",
    "ff48_name",
    "ff12",
    "ff12_name",
    "entity_name",
    "source",
    "fetched_at_utc",
]


def log(message: str) -> None:
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{stamp}] [sic-map] {message}", flush=True)


# --------------------------------------------------------------------------
# Ken French industry definitions
# --------------------------------------------------------------------------


def parse_french_siccodes(text: str) -> tuple[list[tuple[int, int, int]], dict[int, str]]:
    """Parse a ``SiccodesNN.txt`` file.

    Returns ``(ranges, names)``: ``ranges`` is a list of ``(lo, hi, industry)``
    in file order, ``names`` maps industry number to its short name. Header
    lines look like `` 1 Agric  Agriculture``; range lines like
    ``          0100-0199 Agricultural production - crops`` (the description is
    optional). Blank lines are ignored.
    """
    ranges: list[tuple[int, int, int]] = []
    names: dict[int, str] = {}
    current: int | None = None
    for line in text.splitlines():
        if not line.strip():
            continue
        range_match = RANGE_RE.match(line)
        if range_match:
            if current is None:
                raise ValueError(f"SIC range before any industry header: {line!r}")
            lo, hi = int(range_match.group(1)), int(range_match.group(2))
            if lo > hi:
                raise ValueError(f"inverted SIC range: {line!r}")
            ranges.append((lo, hi, current))
            continue
        header = HEADER_RE.match(line)
        if header:
            current = int(header.group(1))
            names[current] = header.group(2)
            continue
        raise ValueError(f"unparseable Siccodes line: {line!r}")
    return ranges, names


def map_sic_to_industry(
    sic: int | None,
    ranges: list[tuple[int, int, int]],
    names: dict[int, str],
    other: int,
) -> tuple[int, str]:
    """Industry of ``sic``. First matching range in file order wins; a SIC in
    no range, or a missing SIC, goes to the ``other`` industry."""
    if sic is not None:
        for lo, hi, industry in ranges:
            if lo <= sic <= hi:
                return industry, names[industry]
    return other, names[other]


def load_french_definitions(
    directory: Path = FRENCH_DIR, *, download: bool = True
) -> dict[int, tuple[list[tuple[int, int, int]], dict[int, str]]]:
    """``{48: (ranges, names), 12: (ranges, names)}``; downloads the two raw zips
    into ``directory`` when absent (keeps the raw ``.zip`` and ``.txt``)."""
    definitions = {}
    for number in (48, 12):
        name = f"Siccodes{number}"
        txt = directory / f"{name}.txt"
        if not txt.exists():
            archive = directory / f"{name}.zip"
            if not archive.exists():
                if not download:
                    raise FileNotFoundError(archive)
                import httpx

                directory.mkdir(parents=True, exist_ok=True)
                response = httpx.get(
                    FRENCH_URL.format(name=name), timeout=60, follow_redirects=True
                )
                response.raise_for_status()
                archive.write_bytes(response.content)
            with zipfile.ZipFile(archive) as zf:
                zf.extractall(directory)
        definitions[number] = parse_french_siccodes(txt.read_text(encoding="latin-1"))
    return definitions


# --------------------------------------------------------------------------
# Symbol -> CIK
# --------------------------------------------------------------------------


def normalize_symbol(symbol: str) -> str:
    """Matching key for share-class tickers (``BRK.B`` == ``BRK-B``)."""
    return str(symbol).strip().upper().replace(".", "-").replace("/", "-")


def build_symbol_cik_links(
    symbols: list[str], history: pd.DataFrame, tickers: dict[str, int]
) -> pd.DataFrame:
    """Symbol -> CIK links with validity periods.

    ``history`` has ``cik, symbol, first_date, last_date``; each matching row
    becomes one link with its own period. Symbols with no history row fall
    back to ``tickers`` (``{symbol: cik}`` from ``company_tickers.json``) and
    get null link dates (unbounded). Columns: ``symbol, cik, link_first_date,
    link_last_date, link_source`` (``history`` or ``company_tickers``).
    """
    hist = history.copy()
    hist["key"] = hist["symbol"].map(normalize_symbol)
    by_key = {key: grp for key, grp in hist.groupby("key")}
    ticker_by_key = {normalize_symbol(sym): cik for sym, cik in tickers.items()}
    rows: list[dict[str, Any]] = []
    for symbol in sorted(set(symbols)):
        key = normalize_symbol(symbol)
        grp = by_key.get(key)
        if grp is not None and len(grp):
            for rec in grp.itertuples(index=False):
                rows.append(
                    {
                        "symbol": symbol,
                        "cik": int(rec.cik),
                        "link_first_date": pd.Timestamp(rec.first_date),
                        "link_last_date": pd.Timestamp(rec.last_date),
                        "link_source": "history",
                    }
                )
        elif key in ticker_by_key:
            rows.append(
                {
                    "symbol": symbol,
                    "cik": int(ticker_by_key[key]),
                    "link_first_date": pd.NaT,
                    "link_last_date": pd.NaT,
                    "link_source": "company_tickers",
                }
            )
    frame = pd.DataFrame(
        rows,
        columns=["symbol", "cik", "link_first_date", "link_last_date", "link_source"],
    )
    frame["link_first_date"] = pd.to_datetime(frame["link_first_date"])
    frame["link_last_date"] = pd.to_datetime(frame["link_last_date"])
    return frame.drop_duplicates(
        subset=["symbol", "cik", "link_first_date", "link_last_date"]
    ).reset_index(drop=True)


def ciks_for_symbol_on(links: pd.DataFrame, symbol: str, on: Any) -> list[int]:
    """CIKs mapped to ``symbol`` on date ``on`` (null link dates are open-ended)."""
    day = pd.Timestamp(on)
    sub = links[links["symbol"] == symbol]
    mask = (sub["link_first_date"].isna() | (sub["link_first_date"] <= day)) & (
        sub["link_last_date"].isna() | (sub["link_last_date"] >= day)
    )
    return sorted(int(c) for c in sub.loc[mask, "cik"])


def lookup_sic_row(sic_map: pd.DataFrame, symbol: str, on: Any) -> tuple[pd.Series | None, bool]:
    """Row of ``sic_map`` to use for ``symbol`` on date ``on`` and whether the
    link period covers ``on`` (``date_verified``).

    Price bars in this repo are keyed by the symbol as Alpaca serves it today,
    so a renamed company (FB -> META) appears under its current ticker for the
    whole history while the SEC history table dates the link only from the
    rename. Rows with a non-null SIC are preferred; among them a covering link
    wins, otherwise the link nearest in time is returned with
    ``date_verified=False`` so the caller can choose to drop it. Reused tickers
    can therefore mis-map outside verified dates; the flag is the guard.
    """
    sub = sic_map[(sic_map["symbol"] == symbol) & sic_map["sic"].notna()]
    if sub.empty:
        return None, False
    day = pd.Timestamp(on)
    first = sub["link_first_date"]
    last = sub["link_last_date"]
    covers = (first.isna() | (first <= day)) & (last.isna() | (last >= day))
    if covers.any():
        return sub[covers].iloc[-1], True
    gap = pd.concat([(first - day).abs(), (last - day).abs()], axis=1).min(axis=1)
    return sub.loc[gap.idxmin()], False


# --------------------------------------------------------------------------
# SIC per CIK
# --------------------------------------------------------------------------


def is_cik_member(name: str) -> bool:
    """True for ``CIK##########.json`` members; pagination members
    (``CIK##########-submissions-NNN.json``) and anything else are skipped."""
    return MEMBER_RE.match(name) is not None


def member_name(cik: int) -> str:
    return f"CIK{int(cik):010d}.json"


def extract_sic_record(doc: dict[str, Any]) -> dict[str, Any]:
    """Top-level ``sic`` / ``sicDescription`` / ``name`` of a submissions JSON.
    ``sic`` is an int, or None when absent, empty, non-numeric or zero."""
    raw = doc.get("sic")
    sic: int | None
    try:
        sic = int(str(raw).strip()) if raw not in (None, "") else None
    except ValueError:
        sic = None
    if sic == 0:
        sic = None
    description = doc.get("sicDescription") or None
    former = doc.get("formerNames") or []
    return {
        "sic": sic,
        "sic_description": description,
        "entity_name": doc.get("name") or None,
        "former_names_count": len(former) if isinstance(former, list) else 0,
    }


def read_bulk_records(zip_path: Path, ciks: set[int]) -> dict[int, dict[str, Any]]:
    """Read only the needed ``CIK##########.json`` members, one at a time."""
    records: dict[int, dict[str, Any]] = {}
    with zipfile.ZipFile(zip_path) as zf:
        for cik in sorted(ciks):
            name = member_name(cik)
            try:
                info = zf.getinfo(name)
            except KeyError:
                continue
            with zf.open(info) as handle:
                records[cik] = extract_sic_record(json.loads(handle.read()))
    return records


def download_bulk(client: Any, path: Path = SUBMISSIONS_ZIP) -> None:
    """Stream submissions.zip to ``path`` (HEAD for size first). Resumable at the
    file level: an existing complete file of the advertised size is reused."""
    head = client._client.head(SUBMISSIONS_ZIP_URL)
    head.raise_for_status()
    size = int(head.headers.get("content-length", "0"))
    log(f"submissions.zip advertised size {size / 1e9:.2f} GB")
    if path.exists() and size and path.stat().st_size == size:
        log("reusing existing submissions.zip")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_suffix(".zip.part")
    client.stream_to_file(SUBMISSIONS_ZIP_URL, partial)
    partial.rename(path)


def load_checkpoint(path: Path) -> dict[int, dict[str, Any]]:
    done: dict[int, dict[str, Any]] = {}
    if not path.exists():
        return done
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue  # truncated last line from an interrupted run
            done[int(row["cik"])] = row
    return done


def _ends_with_newline(path: Path) -> bool:
    with path.open("rb") as handle:
        handle.seek(-1, 2)
        return handle.read(1) == b"\n"


def fetch_api_records(
    client: Any, ciks: set[int], checkpoint: Path = API_CHECKPOINT
) -> dict[int, dict[str, Any]]:
    """Per-CIK API fallback, resumable: CIKs already in the JSONL checkpoint are
    not requested again. 404 is recorded as a missing-record row (sic null);
    any other non-200 after ``SecClient`` backoff is NOT checkpointed so a rerun
    retries it."""
    done = load_checkpoint(checkpoint)
    todo = sorted(c for c in ciks if c not in done)
    log(f"API fallback: {len(done):,} checkpointed, {len(todo):,} to fetch")
    checkpoint.parent.mkdir(parents=True, exist_ok=True)
    failures = 0
    with checkpoint.open("a", encoding="utf-8") as out:
        if checkpoint.stat().st_size and not _ends_with_newline(checkpoint):
            out.write("\n")  # an interrupted run left a truncated last line
        for i, cik in enumerate(todo, start=1):
            status, body = client.get(SUBMISSIONS_API_URL.format(cik=cik))
            fetched = datetime.now(UTC).isoformat()
            if status == 200:
                row = {
                    "cik": cik,
                    "fetched_at_utc": fetched,
                    **extract_sic_record(json.loads(body)),
                }
            elif status == 404:
                row = {
                    "cik": cik,
                    "fetched_at_utc": fetched,
                    "sic": None,
                    "sic_description": None,
                    "entity_name": None,
                    "former_names_count": 0,
                }
            else:
                failures += 1
                log(f"  CIK {cik}: HTTP {status}, not checkpointed")
                continue
            out.write(json.dumps(row) + "\n")
            out.flush()
            done[cik] = row
            if i % 200 == 0:
                log(f"  {i:,}/{len(todo):,} fetched")
    if failures:
        log(f"{failures} CIKs failed and will be retried on rerun")
    return {c: r for c, r in done.items() if c in ciks}


# --------------------------------------------------------------------------
# Assembly
# --------------------------------------------------------------------------


def assemble_sic_map(
    links: pd.DataFrame,
    records: dict[int, dict[str, Any]],
    definitions: dict[int, tuple[list[tuple[int, int, int]], dict[int, str]]],
    *,
    source: str,
    fetched_at_utc: str,
) -> pd.DataFrame:
    ranges48, names48 = definitions[48]
    ranges12, names12 = definitions[12]
    rows = []
    for rec in links.itertuples(index=False):
        info = records.get(int(rec.cik), {})
        sic = info.get("sic")
        ff48, ff48_name = map_sic_to_industry(sic, ranges48, names48, 48)
        ff12, ff12_name = map_sic_to_industry(sic, ranges12, names12, 12)
        rows.append(
            {
                "symbol": rec.symbol,
                "cik": int(rec.cik),
                "link_first_date": rec.link_first_date,
                "link_last_date": rec.link_last_date,
                "sic": sic,
                "sic_description": info.get("sic_description"),
                "ff48": ff48,
                "ff48_name": ff48_name,
                "ff12": ff12,
                "ff12_name": ff12_name,
                "entity_name": info.get("entity_name"),
                "source": source,
                "fetched_at_utc": fetched_at_utc,
            }
        )
    frame = pd.DataFrame(rows, columns=OUTPUT_COLUMNS)
    frame["cik"] = frame["cik"].astype("int64")
    frame["sic"] = frame["sic"].astype("Int64")
    frame["ff48"] = frame["ff48"].astype("int64")
    frame["ff12"] = frame["ff12"].astype("int64")
    return frame


def mapped_symbol_months(
    panel: pd.DataFrame, sic_map: pd.DataFrame, *, strict_dates: bool = True
) -> pd.Series:
    """Boolean per ``panel`` row: has a non-null SIC. ``strict_dates`` requires
    the link period to cover ``month_end``; otherwise any link of the symbol."""
    valid = sic_map.loc[sic_map["sic"].notna(), ["symbol", "link_first_date", "link_last_date"]]
    valid = valid.assign(_link=True)
    merged = panel[["symbol", "month_end"]].reset_index().merge(valid, on="symbol", how="left")
    ok = merged["_link"].eq(True)
    if strict_dates:
        ok &= merged["link_first_date"].isna() | (merged["link_first_date"] <= merged["month_end"])
        ok &= merged["link_last_date"].isna() | (merged["link_last_date"] >= merged["month_end"])
    merged["ok"] = ok
    flag = merged.groupby("index")["ok"].any()
    return flag.reindex(panel.index, fill_value=False)


def coverage_by_year(panel: pd.DataFrame, sic_map: pd.DataFrame) -> dict[str, dict[str, Any]]:
    """Per pool and year: share of pool symbol-months with a non-null SIC."""
    out: dict[str, dict[str, Any]] = {}
    for pool, top in POOLS.items():
        sub = panel[(panel["adv_rank"] <= top) & (panel["close"] >= MIN_CLOSE)].copy()
        sub["mapped"] = mapped_symbol_months(sub, sic_map)
        sub["mapped_any_period"] = mapped_symbol_months(sub, sic_map, strict_dates=False)
        sub["year"] = sub["month_end"].dt.year
        per_year = {}
        for year, grp in sub.groupby("year"):
            per_year[str(year)] = {
                "symbol_months": int(len(grp)),
                "mapped_share": round(float(grp["mapped"].mean()), 4),
                "mapped_any_period_share": round(float(grp["mapped_any_period"].mean()), 4),
            }
        out[pool] = {
            "by_year": per_year,
            "overall_symbol_months": int(len(sub)),
            "overall_mapped_share": round(float(sub["mapped"].mean()), 4),
            "overall_mapped_any_period_share": round(float(sub["mapped_any_period"].mean()), 4),
        }
    return out


def load_universe_panel() -> pd.DataFrame:
    """Funds/ETFs excluded the way ``exclude_funds_and_etfs`` does."""
    panel = duckdb.sql(
        f"select month_end, symbol, adv_rank, close from read_parquet('{UNIVERSE_BROAD_GLOB}')"
    ).df()
    panel["month_end"] = pd.to_datetime(panel["month_end"])
    if ASSET_METADATA_PATH.exists():
        meta = pd.read_parquet(ASSET_METADATA_PATH)
        fund_symbols = set(meta.loc[meta["is_probable_fund_or_etf"], "symbol"])
    else:  # metadata cache absent: nothing flagged (names unknown)
        fund_symbols = set()
    return panel[~panel["symbol"].isin(fund_symbols)].reset_index(drop=True)


def build(source: str, limit: int | None = None) -> None:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
    from build_sec_xbrl_fundamentals import SecClient

    log("loading universe, history, tickers, French definitions")
    panel = load_universe_panel()
    symbols = sorted(panel["symbol"].unique())
    history = pd.read_parquet(HISTORY_PATH)
    tickers_raw = json.loads(TICKERS_PATH.read_text())
    tickers = {str(v["ticker"]): int(v["cik_str"]) for v in tickers_raw.values()}
    definitions = load_french_definitions()
    links = build_symbol_cik_links(symbols, history, tickers)
    link_symbols = set(links["symbol"])
    log(
        f"{len(symbols):,} non-fund universe symbols; {len(link_symbols):,} linked to a CIK "
        f"({int((links['link_source'] == 'company_tickers').sum())} link rows via company_tickers "
        f"fallback); {links['cik'].nunique():,} distinct CIKs"
    )
    ciks = set(int(c) for c in links["cik"].unique())
    if limit is not None:
        ciks = set(sorted(ciks)[:limit])

    records: dict[int, dict[str, Any]] = {}
    used_source = ""
    fetched_at = ""
    if source in {"bulk", "auto"}:
        try:
            client = SecClient()
            download_bulk(client)
            records = read_bulk_records(SUBMISSIONS_ZIP, ciks)
            used_source = "submissions_bulk"
            fetched_at = datetime.fromtimestamp(SUBMISSIONS_ZIP.stat().st_mtime, UTC).isoformat()
            log(f"bulk: {len(records):,}/{len(ciks):,} CIK members found")
        except Exception as exc:  # noqa: BLE001 - any bulk failure triggers the fallback
            if source == "bulk":
                raise
            log(f"bulk failed ({type(exc).__name__}); falling back to the per-CIK API")
    if not used_source:
        client = SecClient(min_interval=API_MIN_INTERVAL_SECONDS)
        records = fetch_api_records(client, ciks)
        used_source = "submissions_api"
        fetched_at = datetime.now(UTC).isoformat()

    sic_map = assemble_sic_map(
        links, records, definitions, source=used_source, fetched_at_utc=fetched_at
    )
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    sic_map.to_parquet(OUT_PATH, index=False)
    log(f"wrote {OUT_PATH} ({len(sic_map):,} rows)")

    coverage = coverage_by_year(panel, sic_map)
    latest = panel["month_end"].max()
    p1000 = panel[
        (panel["adv_rank"] <= 1000) & (panel["close"] >= MIN_CLOSE) & (panel["month_end"] == latest)
    ]
    p1000_all = panel[(panel["adv_rank"] <= 1000) & (panel["close"] >= MIN_CLOSE)].copy()
    p1000_all["mapped"] = mapped_symbol_months(p1000_all, sic_map)
    unmapped = (
        p1000_all.loc[~p1000_all["mapped"], "symbol"].value_counts().head(30).rename_axis("symbol")
    )
    latest_ind = p1000.merge(
        sic_map.drop_duplicates("symbol", keep="last")[["symbol", "ff48", "ff48_name"]],
        on="symbol",
        how="left",
    )
    latest_ind["ff48"] = latest_ind["ff48"].fillna(48).astype(int)
    latest_ind["ff48_name"] = latest_ind["ff48_name"].fillna("Other")
    dist = latest_ind.groupby(["ff48", "ff48_name"]).size().reset_index(name="members")
    p1000_miss = p1000_all[~p1000_all["mapped"]]
    linked = set(sic_map["symbol"])
    sic_symbols = set(sic_map.loc[sic_map["sic"].notna(), "symbol"])
    causes = {
        "no_cik_link": int((~p1000_miss["symbol"].isin(linked)).sum()),
        "linked_but_sec_sic_null": int(
            (p1000_miss["symbol"].isin(linked) & ~p1000_miss["symbol"].isin(sic_symbols)).sum()
        ),
        "sic_exists_only_outside_link_dates": int(p1000_miss["symbol"].isin(sic_symbols).sum()),
    }
    former = sum(1 for r in records.values() if r.get("former_names_count", 0) > 0)
    report = {
        "source": used_source,
        "fetched_at_utc": fetched_at,
        "universe_symbols_non_fund": len(symbols),
        "symbols_linked_to_cik": len(link_symbols),
        "link_rows": int(len(sic_map)),
        "link_rows_via_company_tickers": int((links["link_source"] == "company_tickers").sum()),
        "distinct_ciks": len(ciks),
        "ciks_with_record": len(records),
        "ciks_with_sic": int(sum(1 for r in records.values() if r.get("sic") is not None)),
        "ciks_with_former_names": former,
        "target_p1000_overall_mapped_share": 0.95,
        "coverage": coverage,
        "p1000_date_verified_miss_causes_symbol_months": causes,
        "p1000_top30_unmapped_symbols": {k: int(v) for k, v in unmapped.items()},
        "p1000_ff48_latest_month_end": str(latest.date()),
        "p1000_ff48_distribution": [
            {"ff48": int(r.ff48), "name": r.ff48_name, "members": int(r.members)}
            for r in dist.itertuples()
        ],
        "p1000_ff48_industries_below_5_members": [
            {"ff48": int(r.ff48), "name": r.ff48_name, "members": int(r.members)}
            for r in dist.itertuples()
            if r.members < 5
        ],
        "sic_is_point_in_time": False,
    }
    COVERAGE_PATH.write_text(json.dumps(report, indent=2))
    log(f"wrote {COVERAGE_PATH}")
    print_summary(report)


def print_summary(report: dict[str, Any]) -> None:
    print("\nShare of pool symbol-months with a non-null SIC (strict link dates)")
    years = sorted(report["coverage"]["P1000"]["by_year"])
    print("year   " + "  ".join(f"{p:>7}" for p in POOLS))
    for year in years:
        cells = [
            f"{report['coverage'][p]['by_year'].get(year, {}).get('mapped_share', 0):7.1%}"
            for p in POOLS
        ]
        print(f"{year}  " + "  ".join(cells))
    print(
        "all    "
        + "  ".join(f"{report['coverage'][p]['overall_mapped_share']:7.1%}" for p in POOLS)
    )
    print(
        "any-period "
        + "  ".join(
            f"{report['coverage'][p]['overall_mapped_any_period_share']:7.1%}" for p in POOLS
        )
    )
    print(
        "P1000 date-verified misses by cause:",
        report["p1000_date_verified_miss_causes_symbol_months"],
    )
    print("\nTop date-verified-unmapped P1000 symbols:", report["p1000_top30_unmapped_symbols"])
    print(f"\nFF48 in P1000 at {report['p1000_ff48_latest_month_end']}:")
    for row in report["p1000_ff48_distribution"]:
        print(f"  {row['ff48']:>2} {row['name']:<6} {row['members']}")
    print("industries < 5 members:", report["p1000_ff48_industries_below_5_members"])


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--source", choices=["auto", "bulk", "api"], default="auto")
    parser.add_argument("--limit", type=int, default=None, help="debug: first N CIKs only")
    args = parser.parse_args(argv)
    build(args.source, args.limit)


if __name__ == "__main__":
    main()
