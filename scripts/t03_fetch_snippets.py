# ruff: noqa: E501
#!/usr/bin/env python3
"""T-20261007-03 step 1a: fetch each 10-K and keep only customer-concentration paragraphs.

Reads ``data/features/text_similarity/filings_index.parquet`` (the 10-K index of
T-20261002-03), downloads each primary document with the shared rate-limited
``SecClient``, converts HTML to text keeping table rows (``cell | cell``), and
stores only paragraphs that match the major-customer rules (at most
``MAX_SNIPPET_CHARS`` per filing). Full text is never written to disk.

Resumable: one JSONL line per finished accession under
``data/features/economic_links/_snippets/``; reruns skip finished accessions.
Run through ``scripts/heavy_run.sh --mem 0.8G -- ...``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import signal
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import pandas as pd  # noqa: E402

INDEX = ROOT / "data" / "features" / "text_similarity" / "filings_index.parquet"
OUT = ROOT / "data" / "features" / "economic_links" / "_snippets"
MAX_DOC_BYTES = 14_000_000
MAX_SNIPPET_CHARS = 6000
MAX_PARA_CHARS = 1200
STREAM_CHUNK_BYTES = 65_536
BLOCK = frozenset(
    "address article aside blockquote body br caption center dd details div dl dt fieldset "
    "figcaption figure footer form h1 h2 h3 h4 h5 h6 header hr li main nav ol p pre section "
    "summary ul tr".split()
)
DROP = frozenset({"script", "style", "ix:header", "head"})
HIDDEN = re.compile(r"display\s*:\s*none", re.I)

PCT = r"\d{1,3}(?:\.\d+)?\s*%|\d{1,3}(?:\.\d+)?\s*percent"
# a paragraph is a candidate when it talks about customers and a revenue share
CUST = re.compile(
    r"\b(customers?|clients?|distributors?|licensees?|collaborators?|payors?|resellers?)\b", re.I
)
HAS_PCT = re.compile(PCT, re.I)
REV = re.compile(r"\b(revenues?|sales|net sales|receivable|billings)\b", re.I)
# customer word and a percentage within 150 characters of each other, either order
NEAR = re.compile(
    rf"(?:customers?|clients?|distributors?|licensees?|collaborators?|resellers?)\b.{{0,150}}(?:{PCT})"
    rf"|(?:{PCT}).{{0,150}}\b(?:customers?|clients?|distributors?|licensees?|collaborators?|resellers?)\b",
    re.I,
)
KEY = re.compile(
    r"(accounted for|(?:major|largest|significant|"
    r"principal|key|top|single|one|two|three|four|five) customers?|customer concentration|"
    r"concentrations? of credit risk|customer [A-Z]\b|10\s*%\s*or more|more than 10|"
    r"in excess of 10|exceed(?:ed|ing)? 10|at least 10)",
    re.I,
)


def html_to_paragraphs(data: bytes) -> list[str]:
    """Text split into paragraph lines, table rows flattened as 'cell | cell'."""
    import lxml.html

    root = lxml.html.document_fromstring(data)
    doomed = []
    for el in root.iter():
        tag = el.tag
        if not isinstance(tag, str):
            continue
        tag = tag.lower()
        if tag in DROP:
            doomed.append(el)
            continue
        style = el.get("style")
        if style and HIDDEN.search(style):
            doomed.append(el)
    for el in doomed:
        if el.getparent() is not None:
            el.drop_tree()
    for el in root.iter():
        tag = el.tag
        if not isinstance(tag, str):
            continue
        tag = tag.lower()
        if tag in ("td", "th"):
            el.tail = " | " + (el.tail or "")
        elif tag in BLOCK:
            el.text = "\n" + (el.text or "")
            el.tail = "\n" + (el.tail or "")
    text = root.text_content()
    out = []
    for line in text.split("\n"):
        line = re.sub(r"\s+", " ", line.replace("\xa0", " ")).strip()
        line = re.sub(r"(?:\|\s*)+", "| ", line).strip(" |")
        if line:
            out.append(line)
    return out


_DROP_RE = re.compile(rb"<(script|style|ix:header|head)\b.*?</\1\s*>|<!--.*?-->", re.I | re.S)
_CELL_RE = re.compile(rb"</t[dh]\s*>", re.I)
_BLOCK_RE = re.compile(rb"</?(?:" + "|".join(sorted(BLOCK)).encode() + rb")\b[^>]*>", re.I)
_TAG_RE = re.compile(rb"<[^>]+>")


def html_to_paragraphs_fast(data: bytes) -> list[str]:
    """Regex tag stripper: far lower memory than building a DOM (a 10-K is 1-15 MB)."""
    import html as htmllib

    data = _DROP_RE.sub(b" ", data)
    data = _CELL_RE.sub(b" | ", data)
    data = _BLOCK_RE.sub(b"\n", data)
    data = _TAG_RE.sub(b"", data)
    text = htmllib.unescape(data.decode("utf-8", "replace"))
    out = []
    for line in text.split("\n"):
        line = re.sub(r"\s+", " ", line.replace("\xa0", " ")).strip()
        line = re.sub(r"(?:\|\s*)+", "| ", line).strip(" |")
        if line:
            out.append(line)
    return out


def candidate_snippets(paras: list[str]) -> list[str]:
    """Customer-concentration paragraphs, with the previous short line for table rows."""
    picked: list[tuple[int, str]] = []
    for i, p in enumerate(paras):
        if len(p) < 25 or not CUST.search(p) or not HAS_PCT.search(p):
            continue
        if not KEY.search(p) or not NEAR.search(p):
            continue
        picked.append((i, p))
    out: list[str] = []
    total = 0
    seen: set[str] = set()
    for i, p in picked:
        text = p[:MAX_PARA_CHARS]
        # table rows are short: prepend the heading line above them for context
        if len(p) < 160 and i > 0 and len(paras[i - 1]) < 300:
            text = paras[i - 1][:300] + " // " + text
        if text in seen:
            continue
        seen.add(text)
        if total + len(text) > MAX_SNIPPET_CHARS:
            break
        out.append(text)
        total += len(text)
    return out


def done_accessions() -> set[str]:
    done: set[str] = set()
    # The extractor/coverage readers consume only part_main_*.jsonl. Pilot
    # checkpoints must not suppress filings that never entered that stream.
    for f in OUT.glob("part_main_*.jsonl"):
        with f.open() as fh:
            for line in fh:
                if line.strip():
                    row = json.loads(line)
                    if row["status"] in {"ok", "too_large"}:
                        done.add(row["accession"])
    return done


def select_filings(idx: pd.DataFrame, args, done: set[str]) -> pd.DataFrame:
    if args.filing_start:
        idx = idx[idx["filing_date"] >= pd.Timestamp(args.filing_start)]
    if args.filing_end:
        idx = idx[idx["filing_date"] <= pd.Timestamp(args.filing_end)]
    idx = idx.sort_values(
        ["filing_date", "accession"], ascending=[not args.newest_first, True]
    ).drop_duplicates("accession")
    if args.sample:
        idx = idx.sample(args.sample, random_state=args.seed)
    todo = idx[~idx["accession"].isin(done)]
    return todo.head(args.limit) if args.limit else todo


def fetch_once_bounded(client, url: str) -> tuple[int, bytes, bool]:
    """One SEC request, no retry/redirect; cap streamed identity-body bytes.

    Uses the existing SecClient's transport and serialized rate-limit state.
    Oversize bodies consume at most MAX_DOC_BYTES + STREAM_CHUNK_BYTES; the
    returned prefix is explicitly incomplete and must never enter extraction.
    """
    delay = client._min_interval - (time.monotonic() - client._last_request)
    if delay > 0:
        time.sleep(delay)
    client._last_request = time.monotonic()
    with client._client.stream(
        "GET",
        url,
        follow_redirects=False,
        timeout=30,
        headers={"Accept-Encoding": "identity"},
    ) as response:
        if response.status_code != 200:
            return response.status_code, b"", False
        if response.headers.get("Content-Encoding", "identity").lower() != "identity":
            raise ValueError("bounded fetch requires an identity response body")
        chunks, size = [], 0
        for chunk in response.iter_raw(chunk_size=STREAM_CHUNK_BYTES):
            chunks.append(chunk)
            size += len(chunk)
            if size > MAX_DOC_BYTES:
                return 200, b"".join(chunks), False
        return 200, b"".join(chunks), True


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="stop after this many new filings")
    ap.add_argument("--sample", type=int, default=0, help="random sample of filings (pilot)")
    ap.add_argument("--seed", type=int, default=20261007)
    ap.add_argument("--min-interval", type=float, default=0.15)
    ap.add_argument("--tag", default="main")
    ap.add_argument("--filing-start", type=lambda s: datetime.strptime(s, "%Y-%m-%d").date())
    ap.add_argument("--filing-end", type=lambda s: datetime.strptime(s, "%Y-%m-%d").date())
    ap.add_argument("--newest-first", action="store_true")
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="print selected metadata; no client, credentials or writes",
    )
    ap.add_argument(
        "--bounded-fetch",
        action="store_true",
        help="one request per filing; no retries/redirects; requires --limit",
    )
    args = ap.parse_args()
    if args.limit < 0 or (args.bounded_fetch and (args.limit <= 0 or args.sample)):
        ap.error("bounded fetch requires a positive --limit and no --sample")
    if args.filing_start and args.filing_end and args.filing_start > args.filing_end:
        ap.error("--filing-start must be <= --filing-end")
    if not args.sample and not (args.tag == "main" or args.tag.startswith("main_")):
        ap.error("non-pilot --tag must be main or main_* for the existing extractor")

    idx = pd.read_parquet(INDEX)
    done = done_accessions()
    todo = select_filings(idx, args, done)
    if args.dry_run:
        print(json.dumps(todo[["accession", "filing_date", "url"]].astype(str).to_dict("records")))
        return 0

    from collect_sec_13d_filings import SecClient
    from dotenv import load_dotenv

    load_dotenv(dotenv_path=ROOT / ".env")
    OUT.mkdir(parents=True, exist_ok=True)
    print(f"[{datetime.now(UTC):%H:%M:%S}] todo {len(todo)} of {len(idx)}", flush=True)

    stop = {"flag": False, "signal": 0}

    def on_signal(signum, _frame):
        stop["flag"] = True
        stop["signal"] = signum

    signal.signal(signal.SIGTERM, on_signal)
    signal.signal(signal.SIGINT, on_signal)

    client = SecClient(min_interval=args.min_interval)
    part = OUT / f"part_{args.tag}_{datetime.now(UTC):%Y%m%dT%H%M%S}.jsonl"
    n = hits = 0
    fetch_failed = False
    t0 = time.monotonic()
    with part.open("a") as fh:
        for _, rec in todo.iterrows():
            if stop["flag"]:
                break
            row = {
                "accession": rec["accession"],
                "cik": int(rec["cik"]),
                "filing_date": str(rec["filing_date"].date()),
                "acceptance_datetime": str(rec["acceptance_datetime"]),
                "status": "ok",
                "snippets": [],
                "source_url": rec["url"],
                "bounded_fetch": args.bounded_fetch,
            }
            try:
                complete = True
                if args.bounded_fetch:
                    status, body, complete = fetch_once_bounded(client, rec["url"])
                else:
                    status, body = client.get(rec["url"])
                row.update(
                    body_bytes=len(body),
                    body_sha256=hashlib.sha256(body).hexdigest(),
                    body_complete=complete,
                    hash_scope="complete_response_body" if complete else "received_prefix_only",
                )
                if status != 200:
                    row["status"] = f"http_{status}"
                elif len(body) > MAX_DOC_BYTES:
                    row["status"] = "too_large"
                else:
                    row["snippets"] = candidate_snippets(html_to_paragraphs_fast(body))
            except Exception as exc:  # fetch/parse failure is data
                row["status"] = f"error:{type(exc).__name__}"
            row["fetched_at"] = datetime.now(UTC).isoformat()
            n += 1
            hits += bool(row["snippets"])
            fh.write(json.dumps(row) + "\n")
            fh.flush()
            if args.bounded_fetch and row["status"].startswith(("http_", "error:")):
                fetch_failed = True
                break
            if n % 200 == 0:
                rate = n / (time.monotonic() - t0)
                print(
                    f"[{datetime.now(UTC):%H:%M:%S}] {n} done, hits {hits}, {rate:.1f}/s",
                    flush=True,
                )
    client.close()
    print(f"finished {n} filings, with snippets {hits}", flush=True)
    return 128 + stop["signal"] if stop["flag"] else int(fetch_failed)


if __name__ == "__main__":
    raise SystemExit(main())
