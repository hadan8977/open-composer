#!/usr/bin/env python3
"""10-K text-change data for U3000 companies (T-20261002-03).

Data step of ``reports/research/iterations/t20261002_lazy_prices_ic``. For every
10-K, similarity to the same company's previous 10-K on three sections (full
text, Item 1A risk factors, Item 7 MD&A), each as raw-term-frequency cosine
(``cos``) and word-set Jaccard (``jac``). Visible time is EDGAR
``acceptanceDateTime`` mapped to a trading day with ``attribute_trading_day``.
This script computes no returns and no IC.

Rules follow ``hypotheses.md`` section 2 exactly:

* form exactly ``10-K`` (no 10-K/A, 10-KT, 10-K405), filing date
  2014-07-01..2026-09-30;
* HTML -> text with lxml; ``ix:header``, hidden elements and every ``<table>``
  removed;
* sections: full text; Item 1A (ends at Item 1B or Item 2); Item 7 (ends at
  Item 7A or Item 8). A heading must start a line (block elements are
  separated by newlines) so in-sentence cross references are not headings; when
  a title occurs several times (table of contents), the occurrence with the
  longest body wins;
* tokens: lower case, 2-20 ASCII letters, no stemming, no stop words;
* pairs: the current and previous 10-K of one CIK filed 300-430 days apart;
* a section with fewer than 50 words is missing (NaN), never zero. ``rf_found``
  / ``mda_found`` mean "located with at least 50 words".

Stages: ``universe`` -> ``index`` -> ``fetch`` (resumable, sequential SEC
requests, 2 parser processes, no HTML or text is written to disk) -> ``merge``.

symbol->CIK: links shorter than 180 days are dropped; among links covering a
date the longest span wins. A link with null dates (symbols that have only one
undated link in ``sic_map``) is treated as open-ended, the convention of
``scripts/build_sec_sic_map.py``.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import signal
import subprocess
import sys
import time
import zipfile
from collections import Counter
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

PANEL_DIR = ROOT / "data" / "research" / "equity_book" / "panel"
SIC_MAP = ROOT / "data" / "features" / "sic_map" / "sic_map.parquet"
SUBMISSIONS_ZIP = ROOT / "data" / "raw" / "sec_submissions" / "submissions.zip"
OUT_DIR = ROOT / "data" / "features" / "text_similarity"

FILING_START = "2014-07-01"
FILING_END = "2026-09-30"
MIN_LINK_SPAN_DAYS = 180
MIN_WORDS = 50
PAIR_GAP_MIN = 300
PAIR_GAP_MAX = 430
CIKS_PER_PART = 100
MAX_DOC_BYTES = 30_000_000
IN_FLIGHT = 4
EXIT_TIME_LIMIT = 3
MIN_INTERVAL = 0.125
SECTIONS = ("full", "rf", "mda")

_H = r"[^\S\n]*"  # horizontal whitespace
_M = "\u27e6?"  # optional marker opener left by a heading-only table
RF_START = re.compile(rf"^{_H}{_M}{_H}item{_H}1a\b", re.I | re.M)
RF_END = re.compile(rf"^{_H}{_M}{_H}item{_H}(?:1b|2)\b", re.I | re.M)
MDA_START = re.compile(rf"^{_H}{_M}{_H}item{_H}7\b", re.I | re.M)
MDA_END = re.compile(rf"^{_H}{_M}{_H}item{_H}(?:7a|8)\b", re.I | re.M)
MARKER_RE = re.compile("\u27e6[^\u27e7\n]*\u27e7")
TABLE_HEADING_RE = re.compile(r"^\W*(?:part\s+[ivx]+\W*)?item\s*(\d{1,2}[ab]?)\b", re.I)
TABLE_HEADING_MAX_CHARS = 300
HIDDEN_STYLE = re.compile(r"display\s*:\s*none", re.I)
TOKEN_RE = re.compile(r"[a-z]+")
BLOCK_TAGS = frozenset(
    "address article aside blockquote body br caption center dd details div dl dt "
    "fieldset figcaption figure footer form h1 h2 h3 h4 h5 h6 header hr li main "
    "nav ol p pre section summary ul".split()
)
DROP_TAGS = frozenset({"table", "script", "style", "ix:header", "head"})


def log(message: str) -> None:
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}", flush=True)


# --------------------------------------------------------------------------
# universe
# --------------------------------------------------------------------------


def build_cik_map(members: pd.DataFrame, links: pd.DataFrame) -> pd.DataFrame:
    """Contiguous (symbol, cik, first_date, last_date) runs.

    ``members``: (symbol, trade_date) rows that are U3000 members. Links shorter
    than ``MIN_LINK_SPAN_DAYS`` are dropped; of the links covering a date the one
    with the longest span wins (ties: smaller CIK). Null-dated links are
    open-ended with infinite span.
    """
    cols = ["symbol", "cik", "first_date", "last_date"]
    links = links.copy()
    span = (links["link_last_date"] - links["link_first_date"]).dt.days.astype(float)
    undated = links["link_first_date"].isna() | links["link_last_date"].isna()
    links["span"] = np.where(undated, np.inf, span)
    links = links[links["span"] >= MIN_LINK_SPAN_DAYS]
    by_symbol = {
        s: g.sort_values(["span", "cik"], ascending=[False, True])
        for s, g in links.groupby("symbol")
    }
    out: list[tuple[str, int, pd.Timestamp, pd.Timestamp]] = []
    for symbol, grp in members.groupby("symbol"):
        cand = by_symbol.get(symbol)
        if cand is None:
            continue
        dates = pd.DatetimeIndex(np.sort(grp["trade_date"].unique()))
        first = cand["link_first_date"].fillna(pd.Timestamp.min).to_numpy()
        last = cand["link_last_date"].fillna(pd.Timestamp.max).to_numpy()
        covers = (dates.to_numpy()[:, None] >= first[None, :]) & (
            dates.to_numpy()[:, None] <= last[None, :]
        )
        # candidates are sorted best-first, so the first covering link wins
        has = covers.any(axis=1)
        pick = covers.argmax(axis=1)
        ciks = cand["cik"].to_numpy()[pick]
        start = None
        for i in range(len(dates)):
            cur = int(ciks[i]) if has[i] else None
            if start is not None and (cur is None or cur != start[0]):
                out.append((symbol, start[0], start[1], dates[i - 1]))
                start = None
            if cur is not None and start is None:
                start = (cur, dates[i])
        if start is not None:
            out.append((symbol, start[0], start[1], dates[-1]))
    return pd.DataFrame(out, columns=cols)


def load_u3000_members() -> pd.DataFrame:
    frames = []
    for path in sorted(PANEL_DIR.glob("20*.parquet")):
        df = pd.read_parquet(path, columns=["trade_date", "symbol", "in_u3000"])
        frames.append(df[df["in_u3000"].fillna(False).astype(bool)][["symbol", "trade_date"]])
    members = pd.concat(frames, ignore_index=True)
    members["trade_date"] = pd.to_datetime(members["trade_date"])
    return members


def cmd_universe(args: argparse.Namespace) -> int:
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    members = load_u3000_members()
    links = pd.read_parquet(SIC_MAP, columns=["symbol", "cik", "link_first_date", "link_last_date"])
    cik_map = build_cik_map(members, links)
    cik_map.to_parquet(out / "cik_map.parquet", index=False)
    ciks = sorted({int(c) for c in cik_map["cik"]})
    (out / "ciks.json").write_text(json.dumps(ciks))
    mapped = set(cik_map["symbol"])
    log(
        f"universe: {members['symbol'].nunique()} u3000 symbols, "
        f"{len(mapped)} mapped, {len(ciks)} CIKs, {len(cik_map)} runs"
    )
    return 0


# --------------------------------------------------------------------------
# index
# --------------------------------------------------------------------------


def _filings_from_block(cik: int, block: dict[str, Any]) -> list[dict[str, Any]]:
    forms = block.get("form") or []
    rows = []
    for i, form in enumerate(forms):
        if form != "10-K":
            continue
        filing_date = block["filingDate"][i]
        if not (FILING_START <= filing_date <= FILING_END):
            continue
        primary = block["primaryDocument"][i]
        if not primary:
            continue
        accession = block["accessionNumber"][i]
        accepted = block["acceptanceDateTime"][i] or None
        rows.append(
            {
                "cik": cik,
                "accession": accession,
                "filing_date": filing_date,
                "acceptance_datetime": accepted,
                "report_date": block["reportDate"][i] or None,
                "primary_document": primary,
                "url": f"https://www.sec.gov/Archives/edgar/data/{cik}/"
                f"{accession.replace('-', '')}/{primary}",
            }
        )
    return rows


def index_filings(zf: zipfile.ZipFile, cik: int) -> tuple[list[dict[str, Any]], int]:
    """10-K rows for one CIK (recent block plus the pagination members needed to
    reach ``FILING_START``) and the number of pagination members missing."""
    try:
        doc = json.loads(zf.read(f"CIK{cik:010d}.json"))
    except KeyError:
        return [], 0
    filings = doc.get("filings", {})
    recent = filings.get("recent", {})
    rows = _filings_from_block(cik, recent)
    dates = recent.get("filingDate") or []
    missing = 0
    if not dates or min(dates) > FILING_START:
        for page in filings.get("files", []):
            if page.get("filingTo", "9999") < FILING_START:
                continue
            try:
                block = json.loads(zf.read(page["name"]))
            except KeyError:
                missing += 1
                continue
            rows.extend(_filings_from_block(cik, block))
    seen: set[str] = set()
    unique = []
    for row in rows:
        if row["accession"] not in seen:
            seen.add(row["accession"])
            unique.append(row)
    return unique, missing


def cmd_index(args: argparse.Namespace) -> int:
    out = Path(args.out_dir)
    ciks = json.loads((out / "ciks.json").read_text())
    rows: list[dict[str, Any]] = []
    missing_pages = 0
    no_member = 0
    with zipfile.ZipFile(SUBMISSIONS_ZIP) as zf:
        for cik in ciks:
            got, missing = index_filings(zf, int(cik))
            missing_pages += missing
            if not got and f"CIK{int(cik):010d}.json" not in zf.NameToInfo:
                no_member += 1
            rows.extend(got)
    df = pd.DataFrame(rows)
    df["filing_date"] = pd.to_datetime(df["filing_date"])
    df["acceptance_datetime"] = pd.to_datetime(df["acceptance_datetime"], utc=True, errors="coerce")
    df["report_date"] = pd.to_datetime(df["report_date"], errors="coerce")
    df = df.sort_values(["cik", "filing_date", "accession"]).reset_index(drop=True)
    df.to_parquet(out / "filings_index.parquet", index=False)
    log(
        f"index: {len(df)} 10-K rows over {df['cik'].nunique()} CIKs "
        f"({len(ciks)} requested, {no_member} without a submissions member, "
        f"{missing_pages} missing pagination members); "
        f"{int(df['acceptance_datetime'].isna().sum())} without acceptanceDateTime"
    )
    return 0


# --------------------------------------------------------------------------
# parsing and similarity (pure functions)
# --------------------------------------------------------------------------


def tokenize(text: str) -> Counter[str]:
    """Lower-case runs of ASCII letters with length 2..20."""
    return Counter(w for w in TOKEN_RE.findall(text.lower()) if 2 <= len(w) <= 20)


def html_to_text(data: bytes) -> str:
    """Document text with ``ix:header``, hidden elements and all tables removed;
    block elements are separated by newlines.

    Many filings lay out the section headings (``Item 7.`` ...) as one-row
    tables. Dropping them would erase the section boundaries, so a table whose
    whole text is a short ``Item N`` heading leaves a one-line marker
    ``[item 7a]`` (code only, bracketed with U+27E6/U+27E7) instead of
    disappearing; markers are stripped before tokenizing, so no table text
    reaches the counts.
    """
    import lxml.html

    root = lxml.html.document_fromstring(data)
    for el in list(root.iter("table")):
        if el.getparent() is None:
            continue
        code = _heading_table_code(el)
        if code is not None:
            for child in list(el):
                el.remove(child)
            el.clear(keep_tail=True)
            el.tag = "div"
            el.text = f"\u27e6item {code}\u27e7"
    doomed = []
    for el in root.iter():
        tag = el.tag
        if not isinstance(tag, str):
            continue
        tag = tag.lower()
        if tag in DROP_TAGS:
            doomed.append(el)
            continue
        style = el.get("style")
        if style and HIDDEN_STYLE.search(style):
            doomed.append(el)
    for el in doomed:
        if el.getparent() is not None:
            el.drop_tree()
    for el in root.iter():
        tag = el.tag
        if isinstance(tag, str) and tag.lower() in BLOCK_TAGS:
            el.text = "\n" + (el.text or "")
            el.tail = "\n" + (el.tail or "")
    return root.text_content()


def _heading_table_code(table: Any) -> str | None:
    """``7a`` for a table whose entire text is a short ``Item 7A ...`` heading."""
    chunks: list[str] = []
    total = 0
    for piece in table.itertext():
        chunks.append(piece)
        total += len(piece)
        if total > 4 * TABLE_HEADING_MAX_CHARS:
            return None
    flat = re.sub(r"\s+", " ", "".join(chunks)).strip()
    if not flat or len(flat) > TABLE_HEADING_MAX_CHARS:
        return None
    match = TABLE_HEADING_RE.match(flat)
    return match.group(1).lower() if match else None


def find_section(text: str, start_re: re.Pattern[str], end_re: re.Pattern[str]) -> str | None:
    """Longest ``start .. first-end-after-start`` span over all start headings.
    A start heading with no end marker after it is not a candidate."""
    ends = [m.start() for m in end_re.finditer(text)]
    best: str | None = None
    for m in start_re.finditer(text):
        stop = next((e for e in ends if e > m.end()), None)
        if stop is None:
            continue
        if best is None or stop - m.start() > len(best):
            best = text[m.start() : stop]
    return best


def _edge(text: str | None, n: int = 200) -> list[str] | None:
    if text is None:
        return None
    flat = re.sub(r"\s+", " ", MARKER_RE.sub(" ", text)).strip()
    return [flat[:n], flat[-n:]]


def parse_document(data: bytes, want_snippets: bool = False) -> dict[str, Any]:
    """Section term counts and word totals for one 10-K HTML document. Runs in a
    worker process; nothing is written to disk."""
    text = html_to_text(data)
    parts: dict[str, str | None] = {
        "full": text,
        "rf": find_section(text, RF_START, RF_END),
        "mda": find_section(text, MDA_START, MDA_END),
    }
    out: dict[str, Any] = {}
    for name, body in parts.items():
        counter = tokenize(MARKER_RE.sub(" ", body)) if body is not None else Counter()
        n = sum(counter.values())
        out[f"n_{name}"] = n
        if name == "full" or n >= MIN_WORDS:
            out[name] = dict(counter)
        else:
            out[name] = None
    out["found_rf"] = out["rf"] is not None
    out["found_mda"] = out["mda"] is not None
    if want_snippets:
        out["snippets"] = {"rf": _edge(parts["rf"]), "mda": _edge(parts["mda"])}
    return out


def cosine(a: dict[str, int], b: dict[str, int]) -> float:
    if len(a) > len(b):
        a, b = b, a
    dot = sum(v * b.get(k, 0) for k, v in a.items())
    na = math.sqrt(sum(v * v for v in a.values()))
    nb = math.sqrt(sum(v * v for v in b.values()))
    return dot / (na * nb) if na and nb else float("nan")


def jaccard(a: dict[str, int], b: dict[str, int]) -> float:
    ka, kb = set(a), set(b)
    union = len(ka | kb)
    return len(ka & kb) / union if union else float("nan")


def similarity(a: dict[str, int] | None, b: dict[str, int] | None) -> tuple[float, float]:
    """(cos, jac); NaN when either side is missing or has fewer than MIN_WORDS."""
    if not a or not b or sum(a.values()) < MIN_WORDS or sum(b.values()) < MIN_WORDS:
        return float("nan"), float("nan")
    return cosine(a, b), jaccard(a, b)


def pair_filings(filings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Add pair columns to a CIK's filings (dicts with ``filing_date`` as
    Timestamp, ``accession`` and a ``counts`` dict or None). The previous 10-K is
    the adjacent earlier filing; the pair exists only when the gap is
    300..430 days and both documents parsed."""
    ordered = sorted(filings, key=lambda f: (f["filing_date"], f["accession"]))
    for i, cur in enumerate(ordered):
        cur["has_pair"] = False
        cur["prev_accession"] = None
        cur["prev_filing_date"] = pd.NaT
        cur["gap_days"] = np.nan
        for s in SECTIONS:
            cur[f"cos_{s}"] = np.nan
            cur[f"jac_{s}"] = np.nan
        if i == 0:
            continue
        prev = ordered[i - 1]
        gap = (cur["filing_date"] - prev["filing_date"]).days
        if not (PAIR_GAP_MIN <= gap <= PAIR_GAP_MAX):
            continue
        if cur.get("counts") is None or prev.get("counts") is None:
            continue
        cur["has_pair"] = True
        cur["prev_accession"] = prev["accession"]
        cur["prev_filing_date"] = prev["filing_date"]
        cur["gap_days"] = gap
        for s in SECTIONS:
            cur[f"cos_{s}"], cur[f"jac_{s}"] = similarity(cur["counts"][s], prev["counts"][s])
    return ordered


# --------------------------------------------------------------------------
# fetch
# --------------------------------------------------------------------------


def pending_ciks(all_ciks: Iterable[int], progress: dict[str, Any], resume: bool) -> list[int]:
    done = set(progress.get("completed_ciks", [])) if resume else set()
    return [int(c) for c in all_ciks if int(c) not in done]


def _atomic_write(path: Path, text: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text)
    tmp.replace(path)


def _load_progress(path: Path) -> dict[str, Any]:
    if path.exists():
        return json.loads(path.read_text())
    return {"completed_ciks": [], "n_parts": 0, "requests": 0, "elapsed_seconds": 0.0, "runs": []}


def _filing_row(
    rec: pd.Series,
    parsed: dict[str, Any] | None,
    fetch_status: str,
    parse_status: str | None,
    doc_bytes: int,
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "cik": int(rec["cik"]),
        "accession": rec["accession"],
        "filing_date": rec["filing_date"],
        "acceptance_datetime": rec["acceptance_datetime"],
        "report_date": rec["report_date"],
        "fetch_status": fetch_status,
        "parse_status": parse_status,
        "doc_bytes": doc_bytes,
        "n_words_full": parsed["n_full"] if parsed else None,
        "n_words_rf": parsed["n_rf"] if parsed else None,
        "n_words_mda": parsed["n_mda"] if parsed else None,
        "rf_found": bool(parsed["found_rf"]) if parsed else False,
        "mda_found": bool(parsed["found_mda"]) if parsed else False,
        "counts": {s: parsed[s] for s in SECTIONS} if parsed else None,
    }
    return row


def process_cik(
    cik: int,
    filings: pd.DataFrame,
    client: Any,
    pool: Any,
    want_snippets: int,
    snippets: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], int]:
    """Fetch and parse every 10-K of one CIK (sequential requests, parsing in the
    pool) and return paired filing rows plus the number of requests made."""
    from concurrent.futures import FIRST_COMPLETED, wait

    pending: list[tuple[pd.Series, Any, str, int]] = []
    rows: list[dict[str, Any]] = []
    requests = 0

    def collect(item: tuple[pd.Series, Any, str, int]) -> None:
        rec, fut, fstatus, nbytes = item
        try:
            parsed = fut.result()
            pstatus = "ok"
        except Exception as exc:  # parse failure is data, not a crash
            parsed, pstatus = None, f"error:{type(exc).__name__}"
        if parsed is not None and parsed["n_full"] == 0:
            pstatus = "no_text"
        if (
            parsed is not None
            and want_snippets
            and len(snippets) < want_snippets
            and parsed["found_rf"]
            and parsed["found_mda"]
        ):
            snippets.append(
                {"accession": rec["accession"], "cik": int(rec["cik"]), **parsed["snippets"]}
            )
        rows.append(_filing_row(rec, parsed, fstatus, pstatus, nbytes))

    for _, rec in filings.iterrows():
        while sum(1 for p in pending if not p[1].done()) >= IN_FLIGHT:
            wait([p[1] for p in pending if not p[1].done()], return_when=FIRST_COMPLETED)
        requests += 1
        try:
            status, body = client.get(rec["url"])
        except Exception as exc:
            rows.append(_filing_row(rec, None, f"error:{type(exc).__name__}", None, 0))
            continue
        if status != 200:
            rows.append(_filing_row(rec, None, f"http_{status}", None, 0))
            continue
        if len(body) > MAX_DOC_BYTES:
            rows.append(_filing_row(rec, None, "ok", "too_large", len(body)))
            continue
        fut = pool.submit(
            parse_document, body, bool(want_snippets) and len(snippets) < want_snippets
        )
        pending.append((rec, fut, "ok", len(body)))
    for item in pending:
        collect(item)
    paired = pair_filings(rows)
    for row in paired:
        row.pop("counts", None)  # term counts are large; keep only the scalar results
    return paired, requests


def cmd_fetch(args: argparse.Namespace) -> int:
    import multiprocessing
    from concurrent.futures import ProcessPoolExecutor

    from collect_sec_13d_filings import SecClient
    from dotenv import load_dotenv

    load_dotenv(dotenv_path=ROOT / ".env")
    out = Path(args.out_dir)
    parts_dir = out / "_parts"
    parts_dir.mkdir(parents=True, exist_ok=True)
    progress_path = out / "_progress.json"
    ciks = json.loads((out / "ciks.json").read_text())
    index = pd.read_parquet(out / "filings_index.parquet")
    by_cik = {int(c): g.sort_values(["filing_date", "accession"]) for c, g in index.groupby("cik")}
    if not args.resume and (progress_path.exists() or any(parts_dir.glob("part_*.parquet"))):
        log("fetch: progress or parts already exist; pass --resume or use another --out-dir")
        return 2
    progress = _load_progress(progress_path)
    todo = [c for c in pending_ciks(ciks, progress, args.resume) if c in by_cik]
    if args.limit_ciks:
        todo = todo[: args.limit_ciks]
    log(f"fetch: {len(todo)} CIKs to do ({len(progress['completed_ciks'])} already done)")

    stop = {"flag": False}

    def on_signal(signum: int, _frame: Any) -> None:
        stop["flag"] = True
        log(f"signal {signum}: stopping at the next CIK boundary")

    signal.signal(signal.SIGTERM, on_signal)
    signal.signal(signal.SIGINT, on_signal)

    client = SecClient(min_interval=args.min_interval)
    pool = ProcessPoolExecutor(
        max_workers=args.workers, mp_context=multiprocessing.get_context("spawn")
    )
    started = time.monotonic()
    run = {"start_utc": datetime.now(UTC).isoformat(), "ciks_done": 0, "requests": 0}
    buffer: list[dict[str, Any]] = []
    buffer_ciks: list[int] = []
    snippets: list[dict[str, Any]] = []
    exit_code = 0

    def flush() -> None:
        if not buffer_ciks:
            return
        part = pd.DataFrame([{k: v for k, v in r.items() if k != "counts"} for r in buffer])
        path = parts_dir / f"part_{progress['n_parts']:04d}.parquet"
        tmp = path.with_suffix(".tmp")
        part.to_parquet(tmp, index=False)
        tmp.replace(path)
        progress["n_parts"] += 1
        progress["completed_ciks"] = sorted(set(progress["completed_ciks"]) | set(buffer_ciks))
        progress["requests"] += run["requests"] - progress.get("_flushed_requests", 0)
        progress["_flushed_requests"] = run["requests"]
        progress["elapsed_seconds"] = progress.get("elapsed_seconds", 0.0) + (
            time.monotonic() - started - progress.get("_flushed_seconds", 0.0)
        )
        progress["_flushed_seconds"] = time.monotonic() - started
        _atomic_write(progress_path, json.dumps(progress))
        log(f"wrote {path.name}: {len(buffer_ciks)} CIKs, {len(buffer)} filings")
        buffer.clear()
        buffer_ciks.clear()

    try:
        for cik in todo:
            if stop["flag"] or (time.monotonic() - started) > args.max_minutes * 60:
                exit_code = EXIT_TIME_LIMIT
                break
            rows, n_req = process_cik(cik, by_cik[cik], client, pool, args.snippets, snippets)
            buffer.extend(rows)
            buffer_ciks.append(cik)
            run["ciks_done"] += 1
            run["requests"] += n_req
            if len(buffer_ciks) >= CIKS_PER_PART:
                flush()
    finally:
        flush()
        pool.shutdown(wait=True, cancel_futures=True)
        client.close()
        run["end_utc"] = datetime.now(UTC).isoformat()
        run["exit_code"] = exit_code
        progress.setdefault("runs", []).append(run)
        progress.pop("_flushed_requests", None)
        progress.pop("_flushed_seconds", None)
        _atomic_write(progress_path, json.dumps(progress))
        if snippets:
            _atomic_write(out / "_snippets.json", json.dumps(snippets, indent=1))
    remaining = len(
        [c for c in ciks if int(c) in by_cik and int(c) not in set(progress["completed_ciks"])]
    )
    log(
        f"fetch done: exit {exit_code}, {run['ciks_done']} CIKs this run, "
        f"{remaining} CIKs remaining"
    )
    return exit_code


# --------------------------------------------------------------------------
# merge
# --------------------------------------------------------------------------

FILING_COLS = [
    "cik", "accession", "filing_date", "acceptance_datetime", "visible_day",
    "n_words_full", "n_words_rf", "n_words_mda", "rf_found", "mda_found",
    "fetch_status", "parse_status",
]  # fmt: skip
PAIR_COLS = [
    "cik", "accession", "prev_accession", "filing_date", "prev_filing_date", "gap_days",
    "visible_day", "cos_full", "cos_rf", "cos_mda", "jac_full", "jac_rf", "jac_mda",
]  # fmt: skip


def visible_days(acceptance: pd.Series, trading_days: pd.DatetimeIndex) -> pd.Series:
    """First trading day whose 16:00 ET close is >= acceptance time; NaT when the
    time falls outside the trading calendar (before its first or after its last
    close), because ``attribute_trading_day`` clips there."""
    from build_h20260928_16_sentiment_accel_feature import _naive_days, attribute_trading_day

    result = pd.Series(pd.NaT, index=acceptance.index, dtype="datetime64[ns]")
    valid = acceptance.notna()
    if not valid.any():
        return result
    days = _naive_days(trading_days)
    closes = (days.tz_localize("America/New_York") + pd.Timedelta(hours=16)).tz_convert("UTC")
    ok = valid & (acceptance <= closes.max()) & (acceptance > closes.min())
    if ok.any():
        result.loc[ok] = pd.to_datetime(attribute_trading_day(acceptance[ok], trading_days))
    return result


def _git_hash() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True
        ).stdout.strip()
    except Exception:
        return "unknown"


def cmd_merge(args: argparse.Namespace) -> int:
    out = Path(args.out_dir)
    parts = sorted((out / "_parts").glob("part_*.parquet"))
    if not parts:
        log("merge: no parts yet")
        return 1
    df = pd.concat([pd.read_parquet(p) for p in parts], ignore_index=True)
    df = df.drop_duplicates("accession", keep="last").reset_index(drop=True)
    trading_days = pd.DatetimeIndex(
        sorted(
            pd.concat(
                pd.read_parquet(p, columns=["trade_date"])["trade_date"].drop_duplicates()
                for p in sorted(PANEL_DIR.glob("20*.parquet"))
            ).unique()
        )
    )
    df["acceptance_datetime"] = pd.to_datetime(df["acceptance_datetime"], utc=True)
    df["visible_day"] = visible_days(df["acceptance_datetime"], trading_days)
    filings = df[FILING_COLS].copy()
    pairs = df[df["has_pair"].astype(bool)][PAIR_COLS].copy()
    filings.to_parquet(out / "10k_filings.parquet", index=False)
    pairs.to_parquet(out / "10k_pairs.parquet", index=False)
    progress = _load_progress(out / "_progress.json")
    runs = progress.get("runs", [])
    manifest = {
        "stage": "merge",
        "created_utc": datetime.now(UTC).isoformat(),
        "git_hash": _git_hash(),
        "params": {
            "filing_start": FILING_START,
            "filing_end": FILING_END,
            "min_link_span_days": MIN_LINK_SPAN_DAYS,
            "min_words": MIN_WORDS,
            "pair_gap_days": [PAIR_GAP_MIN, PAIR_GAP_MAX],
            "ciks_per_part": CIKS_PER_PART,
            "token_regex": "[a-z]+ filtered to length 2..20, lower case",
        },
        "n_parts": len(parts),
        "n_filings": len(filings),
        "n_pairs": len(pairs),
        "n_ciks_completed": len(progress.get("completed_ciks", [])),
        "fetch_status_counts": filings["fetch_status"].value_counts().to_dict(),
        "parse_status_counts": filings["parse_status"].fillna("none").value_counts().to_dict(),
        "first_run_start_utc": runs[0]["start_utc"] if runs else None,
        "last_run_end_utc": runs[-1].get("end_utc") if runs else None,
        "requests": progress.get("requests"),
        "elapsed_seconds": progress.get("elapsed_seconds"),
    }
    _atomic_write(out / "_manifest.json", json.dumps(manifest, indent=1, default=str))
    log(f"merge: {len(filings)} filings, {len(pairs)} pairs from {len(parts)} parts")
    return 0


# --------------------------------------------------------------------------
# cli
# --------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--out-dir", default=str(OUT_DIR))
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("universe")
    sub.add_parser("index")
    fetch = sub.add_parser("fetch")
    fetch.add_argument("--resume", action="store_true")
    fetch.add_argument("--max-minutes", type=float, default=120.0)
    fetch.add_argument("--limit-ciks", type=int, default=0)
    fetch.add_argument("--workers", type=int, default=2)
    fetch.add_argument("--min-interval", type=float, default=MIN_INTERVAL)
    fetch.add_argument("--snippets", type=int, default=0)
    sub.add_parser("merge")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    os.environ.setdefault("POLARS_SKIP_CPU_CHECK", "1")
    return {"universe": cmd_universe, "index": cmd_index, "fetch": cmd_fetch, "merge": cmd_merge}[
        args.command
    ](args)


if __name__ == "__main__":
    raise SystemExit(main())
