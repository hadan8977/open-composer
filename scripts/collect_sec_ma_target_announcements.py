"""T-20260929-03 step 1: EDGAR merger-agreement 8-K collector (target-side announcements).

Direction: ``dir:merger_arbitrage_target_announcement_drift`` in the direction
registry. Question: after a public company announces it is being acquired,
is there a cost-surviving drift when we buy the target at the next open and
hold a fixed number of sessions?

Pipeline (each stage is resumable; a rerun skips finished work)
---------------------------------------------------------------
``search``
    EDGAR full-text search (``efts.sec.gov/LATEST/search-index``, free, no key)
    for 8-K files containing the phrases in :data:`QUERIES`, sliced by
    calendar month (a slice is halved when the API reports >= 10,000 hits).
    Hits are per *file* (main document or exhibit); they are grouped by
    accession later. Raw pages go to ``data/raw/sec_ma/fts/{query}/{start}_{end}.json``.
``confirm``
    Same search over DEFA14A / SC 14D9-C (the target's own solicitation and
    tender-offer communications) -> ``data/raw/sec_ma/confirm/``. Used only as an
    independent *bonus* signal that the filer is the target (filed within 5
    trading days after the 8-K). DEFM14A is deliberately not used: it appears
    only for deals that survive to the vote, which would select survivors.
``fetch``
    For each candidate accession (Item 1.01, not a completion 8-K, filer CIK
    maps to a ticker) fetch the head of the complete submission ``.txt`` in
    one range request: header (acceptance time), main 8-K text and the head of
    the merger-agreement exhibit. :func:`classify_filing` decides by code
    (never by a model) whether the *filer* is the acquired party.
``build``
    Join classification, ticker mapping and confirmations into
    ``data/features/sec_8k_ma_announcements/{year}.parquet``.

Point-in-time
-------------
``acceptance_utc`` is the EDGAR ``<ACCEPTANCE-DATETIME>`` (Eastern wall clock,
converted with zoneinfo). ``trade_date`` is the last US session on or before
the Eastern acceptance date, so ``signal_card`` (signal known by the close of
``trade_date``, entry at the next session's open) never trades on the day-0
reaction: an after-hours 8-K of day D and an intraday 8-K of day D both enter
at D+1 open. Weekend/holiday filings map to the prior session.

Ticker mapping: ``data/raw/insider`` Form 4 tables give (issuer CIK, trading
symbol) with filing dates from 2016, including names that later delisted;
the current ``company_tickers.json`` is the fallback. Unmapped candidates are
counted by year, not guessed.

SEC fair access: fixed User-Agent constant shared with
``scripts/build_earnings_events.py``, serialized requests with a minimum
interval (default 0.2 s = 5 req/s), exponential backoff on 403/429/5xx.

Usage::

    uv run python scripts/collect_sec_ma_target_announcements.py --stage search \\
        --start 2016-01 --end 2026-09
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
import threading
import time
from calendar import monthrange
from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402

from open_composer.market_calendar import us_equity_session_dates  # noqa: E402

RAW_ROOT = ROOT / "data" / "raw" / "sec_ma"
OUT_ROOT = ROOT / "data" / "features" / "sec_8k_ma_announcements"

# Same fixed identification string as scripts/build_earnings_events.py.
USER_AGENT = "open-composer research hzc43021@gmail.com"
FTS_URL = "https://efts.sec.gov/LATEST/search-index"
COMPANY_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
ARCHIVE_TXT_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{nodash}/{adsh}.txt"
ARCHIVE_INDEX_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{nodash}/{adsh}-index.htm"

MIN_REQUEST_INTERVAL_SECONDS = 0.2
HTTP_TIMEOUT_SECONDS = 60
PAGE_SIZE = 100
FTS_CAP = 10_000
FETCH_MAX_BYTES = 130_000
_EASTERN = ZoneInfo("America/New_York")

#: id -> (query string, forms)
QUERIES: dict[str, tuple[str, str]] = {
    "plan_of_merger": ('"Agreement and Plan of Merger"', "8-K"),
    "plan_of_reorg": ('"Agreement and Plan of Reorganization"', "8-K"),
}
CONFIRM_QUERY = ('"merger agreement"', "DEFA14A,SC14D9C")

_SUB_MARKERS = (
    "merger sub",
    "merger subsidiary",
    "merger corp",
    "merger co",
    "merger llc",
    "acquisition sub",
    "acquisition corp",
    "acquisition co",
    "purchaser",
    "offeror",
    "bidco",
    "holdco",
    "merger company",
)
_NAME_SUFFIX = {
    "inc",
    "incorporated",
    "corp",
    "corporation",
    "co",
    "company",
    "ltd",
    "limited",
    "plc",
    "llc",
    "lp",
    "the",
    "de",
    "nv",
    "sa",
    "ag",
    "holdings",
    "holding",
    "group",
    "trust",
}


def log(message: str) -> None:
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}", flush=True)


# --------------------------------------------------------------------------
# HTTP
# --------------------------------------------------------------------------


class SecClient:
    """Serialized, rate-limited SEC client with exponential backoff."""

    def __init__(
        self,
        *,
        min_interval: float = MIN_REQUEST_INTERVAL_SECONDS,
        client: object | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._min_interval = min_interval
        self._last_request = 0.0
        self._lock = threading.Lock()
        self._sleep = sleep
        if client is None:
            import httpx

            client = httpx.Client(
                headers={"User-Agent": USER_AGENT, "Accept-Encoding": "gzip, deflate"},
                timeout=HTTP_TIMEOUT_SECONDS,
                follow_redirects=True,
            )
        self._client = client

    def get(
        self,
        url: str,
        *,
        params: dict | None = None,
        retries: int = 6,
        max_bytes: int | None = None,
    ) -> tuple[int, bytes]:
        headers = {"Range": f"bytes=0-{max_bytes - 1}"} if max_bytes else None
        for attempt in range(retries):
            with self._lock:  # one shared request-start clock across worker threads
                elapsed = time.monotonic() - self._last_request
                if elapsed < self._min_interval:
                    self._sleep(self._min_interval - elapsed)
                self._last_request = time.monotonic()
            try:
                response = self._client.get(url, params=params, headers=headers)
            except Exception as exc:  # transport-level; httpx errors subclass Exception
                if attempt == retries - 1:
                    raise
                log(f"  transport error {type(exc).__name__}; retry {attempt + 1}/{retries}")
                self._sleep(backoff_seconds(attempt))
                continue
            if response.status_code in {403, 429, 500, 502, 503, 504}:
                if attempt == retries - 1:
                    return response.status_code, response.content
                wait = backoff_seconds(attempt)
                log(f"  HTTP {response.status_code}; backing off {wait:.0f}s")
                self._sleep(wait)
                continue
            return response.status_code, response.content
        raise RuntimeError("unreachable")

    def close(self) -> None:
        close = getattr(self._client, "close", None)
        if close:
            close()


def backoff_seconds(attempt: int) -> float:
    return float(min(120, 5 * 2**attempt))


# --------------------------------------------------------------------------
# search stage: EDGAR full-text search
# --------------------------------------------------------------------------


def month_windows(start: str, end: str) -> list[tuple[date, date]]:
    """Inclusive calendar-month windows from ``YYYY-MM`` to ``YYYY-MM``."""
    y, m = (int(x) for x in start.split("-"))
    y2, m2 = (int(x) for x in end.split("-"))
    out = []
    while (y, m) <= (y2, m2):
        out.append((date(y, m, 1), date(y, m, monthrange(y, m)[1])))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def compact_hit(hit: dict) -> dict:
    src = hit.get("_source", {})
    return {
        "id": hit.get("_id"),
        "adsh": src.get("adsh"),
        "ciks": src.get("ciks") or [],
        "names": src.get("display_names") or [],
        "file_date": src.get("file_date"),
        "form": src.get("form"),
        "file_type": src.get("file_type"),
        "file_description": src.get("file_description"),
        "items": src.get("items") or [],
    }


def search_window(
    client: SecClient, query: str, forms: str, start: date, end: date
) -> tuple[list[dict], int]:
    """All compact hits in [start, end]; halves the window when the API caps out."""
    hits: list[dict] = []
    offset = 0
    total = 0
    while True:
        params = {
            "q": query,
            "forms": forms,
            "dateRange": "custom",
            "startdt": start.isoformat(),
            "enddt": end.isoformat(),
            "from": offset,
        }
        status, body = client.get(FTS_URL, params=params)
        if status != 200:
            raise RuntimeError(f"FTS HTTP {status} for {start}..{end} from={offset}")
        payload = json.loads(body)
        page = payload["hits"]["hits"]
        total = int(payload["hits"]["total"]["value"])
        if total >= FTS_CAP and start < end:
            mid = start + (end - start) // 2
            left, _ = search_window(client, query, forms, start, mid)
            right, _ = search_window(client, query, forms, mid + timedelta(days=1), end)
            return left + right, total
        hits.extend(compact_hit(h) for h in page)
        offset += PAGE_SIZE
        if not page or offset >= total:
            return hits, total


def stage_search(
    client: SecClient,
    windows: list[tuple[date, date]],
    *,
    queries: dict[str, tuple[str, str]],
    root: Path,
) -> None:
    for qid, (query, forms) in queries.items():
        out_dir = root / qid
        out_dir.mkdir(parents=True, exist_ok=True)
        for start, end in windows:
            path = out_dir / f"{start:%Y%m}.json"
            if path.exists():
                continue
            hits, total = search_window(client, query, forms, start, end)
            tmp = path.with_suffix(".tmp")
            tmp.write_text(json.dumps({"total": total, "hits": hits}), encoding="utf-8")
            tmp.replace(path)
            log(f"search {qid} {start:%Y-%m}: total={total} hits={len(hits)}")


# --------------------------------------------------------------------------
# candidates and ticker mapping
# --------------------------------------------------------------------------


def load_candidates(search_root: Path) -> pd.DataFrame:
    """One row per 8-K accession that carries Item 1.01 and is not a completion 8-K."""
    rows: dict[str, dict] = {}
    for path in sorted(search_root.glob("*/*.json")):
        for hit in json.loads(path.read_text(encoding="utf-8"))["hits"]:
            adsh = hit["adsh"]
            if not adsh or hit.get("form") != "8-K" or not hit["ciks"]:
                continue
            row = rows.setdefault(
                adsh,
                {
                    "adsh": adsh,
                    "cik": int(hit["ciks"][0]),
                    "all_ciks": [int(c) for c in hit["ciks"]],
                    "file_date": hit["file_date"],
                    "name": hit["names"][0] if hit["names"] else "",
                    "items": hit["items"],
                    "file_types": set(),
                },
            )
            row["file_types"].add(hit.get("file_type") or "")
    frame = pd.DataFrame(list(rows.values()))
    if frame.empty:
        return frame
    frame["is_announcement_form"] = [is_announcement_items(i) for i in frame["items"]]
    frame["file_types"] = [sorted(s) for s in frame["file_types"]]
    return frame[frame["is_announcement_form"]].reset_index(drop=True)


def is_announcement_items(items: Iterable[str]) -> bool:
    """Item 1.01 present and not the completion 8-K (2.01 together with 5.01)."""
    s = set(items)
    return "1.01" in s and not ({"2.01", "5.01"} <= s)


def clean_symbol(value: object) -> str | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    s = str(value).strip().upper()
    if not s or s in {"NONE", "N/A", "NA", "NULL", "-"} or len(s) > 8:
        return None
    return s


def build_cik_symbol_history(raw_insider_root: Path) -> pd.DataFrame:
    """(cik, symbol, first_date, last_date) from Form 4 issuer fields."""
    import duckdb

    globs = [
        str(raw_insider_root / "parsed" / "*.parquet"),
        str(raw_insider_root / "tail" / "parsed" / "*.parquet"),
    ]
    con = duckdb.connect()
    con.execute("SET memory_limit='900MB'")
    try:
        parts = []
        for g in globs:
            if list(Path(g).parent.glob("*.parquet")):
                parts.append(
                    "SELECT CAST(issuer_cik AS BIGINT) AS cik, issuer_symbol AS symbol, "
                    f"CAST(filing_date AS DATE) AS d FROM read_parquet('{g}', union_by_name=true)"
                )
        sql = " UNION ALL ".join(parts)
        df = con.execute(
            f"SELECT cik, symbol, MIN(d) AS first_date, MAX(d) AS last_date FROM ({sql}) "
            "WHERE cik IS NOT NULL AND symbol IS NOT NULL GROUP BY cik, symbol"
        ).df()
    finally:
        con.close()
    df["symbol"] = df["symbol"].map(clean_symbol)
    df = df.dropna(subset=["symbol"])
    return df.reset_index(drop=True)


def map_cik_symbol(
    cik: int,
    on: date,
    history: dict[int, list[tuple[str, date, date]]],
    current: dict[int, str],
) -> tuple[str | None, str]:
    """Symbol for a CIK around ``on``: Form 4 history first, then today's SEC map."""
    rows = history.get(cik)
    if rows:
        best = None
        best_gap = None
        for sym, first, last in rows:
            if first <= on <= last:
                gap = 0
            elif on < first:
                gap = (first - on).days
            else:
                gap = (on - last).days
            if best_gap is None or gap < best_gap:
                best, best_gap = sym, gap
        if best is not None and best_gap is not None and best_gap <= 730:
            return best, "form4_history" if best_gap == 0 else "form4_history_near"
    if cik in current:
        return current[cik], "company_tickers_current"
    return None, "unmapped"


def history_lookup(df: pd.DataFrame) -> dict[int, list[tuple[str, date, date]]]:
    out: dict[int, list[tuple[str, date, date]]] = {}
    for r in df.itertuples(index=False):
        out.setdefault(int(r.cik), []).append(
            (r.symbol, pd.Timestamp(r.first_date).date(), pd.Timestamp(r.last_date).date())
        )
    return out


def load_current_tickers(client: SecClient, path: Path) -> dict[int, str]:
    if not path.exists():
        status, body = client.get(COMPANY_TICKERS_URL)
        if status != 200:
            log(f"company_tickers.json HTTP {status}; continuing without current map")
            return {}
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(body)
    data = json.loads(path.read_text(encoding="utf-8"))
    out: dict[int, str] = {}
    for row in data.values():
        sym = clean_symbol(row.get("ticker"))
        if sym:
            out.setdefault(int(row["cik_str"]), sym)
    return out


# --------------------------------------------------------------------------
# submission parsing and target/acquirer rule
# --------------------------------------------------------------------------

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def parse_submission_head(raw: str) -> dict:
    """Header fields + text of the main 8-K document and the first EX-2 exhibit head."""
    acc = re.search(r"<ACCEPTANCE-DATETIME>\s*(\d{14})", raw)
    name = re.search(r"COMPANY CONFORMED NAME:\s*(.+)", raw)
    docs = re.split(r"<DOCUMENT>", raw)[1:]
    main_text = ""
    ex2_text = ""
    for doc in docs:
        typ = re.search(r"<TYPE>\s*([^\s<]+)", doc)
        typ = typ.group(1).upper() if typ else ""
        body = doc.split("<TEXT>", 1)[-1]
        if typ in {"8-K", "8-K/A"} and not main_text:
            main_text = html_to_text(body)
        elif typ.startswith("EX-2") and not ex2_text:
            ex2_text = html_to_text(body)[:8000]
    return {
        "acceptance_et": acc.group(1) if acc else None,
        "filer_name": name.group(1).strip() if name else None,
        "main_text": main_text,
        "ex2_head": ex2_text,
    }


def html_to_text(body: str) -> str:
    body = re.sub(r"(?is)<(script|style|ix:header).*?</\1>", " ", body)
    body = _TAG_RE.sub(" ", body)
    return _WS_RE.sub(" ", html.unescape(body)).strip()


def acceptance_to_utc(stamp: str) -> pd.Timestamp:
    """EDGAR acceptance stamp (Eastern wall clock) -> tz-naive UTC timestamp."""
    naive = datetime.strptime(stamp, "%Y%m%d%H%M%S").replace(tzinfo=_EASTERN)
    return pd.Timestamp(naive.astimezone(UTC).replace(tzinfo=None))


def trade_date_for(stamp: str, sessions: list[date]) -> date | None:
    """Last session on or before the Eastern acceptance date (see module docstring)."""
    day = datetime.strptime(stamp, "%Y%m%d%H%M%S").date()
    prior = [s for s in sessions if s <= day]
    return prior[-1] if prior else None


def normalize(text: str) -> str:
    text = text.lower().replace("’", "'")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return _WS_RE.sub(" ", text).strip()


def core_name(name: str | None) -> str:
    """First two distinctive tokens of a company name ('Seagen Inc.' -> 'seagen')."""
    if not name:
        return ""
    tokens = [t for t in normalize(name).split() if t not in _NAME_SUFFIX]
    return " ".join(tokens[:2])


def _is_sub(pre_words: list[str]) -> bool:
    tail = " ".join(pre_words[-10:]) + " "
    if any(m in tail for m in _SUB_MARKERS):
        return True
    return " ".join(pre_words[-2:]).endswith(" sub") or (pre_words[-1:] == ["sub"])


def merger_directions(text: str, core: str) -> list[dict]:
    """Every '<subject> merge with and into <object>' clause with who-merges-into-whom."""
    t = normalize(text)
    words = t.split()
    out = []
    for i in range(len(words) - 3):
        if words[i : i + 3] != ["with", "and", "into"]:
            continue
        # subject ends right before 'merge'/'merged' (+ optional 'be', 'will', 'shall')
        j = i
        while j > 0 and words[j - 1] in {"merge", "merged"}:
            j -= 1
        while j > 0 and words[j - 1] in {"be", "will", "shall", "then", "to", "would"}:
            j -= 1
        pre = words[max(0, j - 10) : j]
        obj_words = words[i + 3 : i + 3 + 8]
        obj = " ".join(obj_words)
        obj_kind = (
            "company"
            if obj.startswith("the company")
            else "filer"
            if core and obj.startswith(core.split()[0]) and _obj_matches_core(obj, core)
            else "other"
        )
        subj_is_sub = _is_sub(pre)
        subj_is_filer = bool(core) and _obj_matches_core(" ".join(pre[-4:]), core, anywhere=True)
        out.append(
            {
                "obj_kind": obj_kind,
                "subj_is_sub": subj_is_sub,
                "subj_is_filer": subj_is_filer,
                "snippet": " ".join(pre[-6:] + ["MERGE_WITH_AND_INTO"] + obj_words[:6]),
            }
        )
    return out


_COMPANY_DEF_RE = re.compile("[\u201c\"']\\s*Company\\s*[\u201d\"']")


def company_definition_is_filer(main_text: str, core: str) -> bool | None:
    """Is the defined term "Company" the filer? None when it is never defined.

    Looks only at the party named right before the definition (text after the last
    ")", "and", "with" or ";"), so a filer mentioned earlier in the sentence does
    not count as the Company.
    """
    match = _COMPANY_DEF_RE.search(main_text)
    if match is None or not core:
        return None
    before = main_text[max(0, match.start() - 200) : match.start()]
    party = re.split(r"\)|\band\b|\bwith\b|;", before)[-1]
    if re.search(r"\b(?:registrant|we|our|us)\b", normalize(party)):
        return True  # the filer defines itself: 'the Registrant ("we", "our" or the "Company")'
    return _obj_matches_core(normalize(party), core, anywhere=True)


def _obj_matches_core(text: str, core: str, *, anywhere: bool = False) -> bool:
    toks = core.split()
    if not toks:
        return False
    pattern = r"\b" + r"\s+(?:[a-z0-9]+\s+)?".join(re.escape(t) for t in toks) + r"\b"
    if anywhere:
        return re.search(pattern, text) is not None
    return re.match(pattern, text) is not None


#: evidence label -> (side, weight); repeated clauses of the same kind count once
REASON_WEIGHTS: dict[str, tuple[str, int]] = {
    "sub_merges_into_filer": ("t", 3),
    "sub_merges_into_company": ("t", 3),
    "filer_merges_into_other": ("t", 2),
    "ex2_filer_is_company": ("t", 2),
    "named_merges_into_filer": ("a", 2),
    "named_merges_into_company": ("a", 2),
    "sub_merges_into_other": ("a", 3),
    "other_into_other": ("a", 1),
    "ex2_filer_is_parent_side": ("a", 1),
    "sub_is_subsidiary_of_filer": ("a", 3),
}


def score_reasons(reasons: Iterable[str]) -> tuple[int, int]:
    t = a = 0
    for label in set(reasons):
        side, weight = REASON_WEIGHTS.get(label, ("", 0))
        if side == "t":
            t += weight
        elif side == "a":
            a += weight
    return t, a


def classify_filing(
    main_text: str, filer_name: str | None, ex2_head: str = "", items: Iterable[str] = ()
) -> dict:
    """Is the 8-K filer the *acquired* party? Rule-based, no model.

    Score = target evidence - acquirer evidence from every
    "X will merge with and into Y" clause:
      * Y is the filer (by name) or "the Company" and X is a merger sub -> target (+3)
      * X is a merger sub and Y is another named entity -> acquirer (+3)
      * X is the filer and Y another named entity (filer merges away) -> target (+2)
      * X is another named entity and Y is "the Company" -> acquirer survives (+2 acquirer)
    ``is_target_rule`` needs score >= 2 and at least one clause found.
    """
    core = core_name(filer_name)
    t_score = 0
    a_score = 0
    reasons: list[str] = []
    snippet = ""
    company_is_filer = company_definition_is_filer(main_text, core)
    for c in merger_directions(main_text, core):
        if c["obj_kind"] == "company" and company_is_filer is False:
            c = {**c, "obj_kind": "other"}  # "the Company" is defined as some other entity
        if c["obj_kind"] == "filer":
            if c["subj_is_sub"]:
                t_score += 3
                reasons.append("sub_merges_into_filer")
            else:  # a named company merges into the filer: the filer survives (acquirer)
                a_score += 2
                reasons.append("named_merges_into_filer")
        elif c["obj_kind"] == "company":
            if c["subj_is_sub"]:
                t_score += 3
                reasons.append("sub_merges_into_company")
            else:
                a_score += 2
                reasons.append("named_merges_into_company")
        else:
            if c["subj_is_sub"]:
                a_score += 3
                reasons.append("sub_merges_into_other")
            elif c["subj_is_filer"]:
                t_score += 2
                reasons.append("filer_merges_into_other")
            else:
                a_score += 1
                reasons.append("other_into_other")
        snippet = snippet or c["snippet"]
    # exhibit preamble: the filer defined as "the Company" of an agreement between
    # Parent / Merger Sub / the Company, or listed as a party before the defined term.
    ex = normalize(ex2_head)
    if core and ex:
        m = re.search(
            r"(?:by and among|by and between|among|between) (.{0,500}?) the company\b", ex
        )
        if m:
            head, _, last = m.group(1).rpartition(" and ")
            if _obj_matches_core(last, core, anywhere=True):
                t_score += 2
                reasons.append("ex2_filer_is_company")
            elif _obj_matches_core(head, core, anywhere=True):
                a_score += 1  # weak: the exhibit preamble order is not reliable on its own
                reasons.append("ex2_filer_is_parent_side")
    norm_all = normalize(main_text)
    if company_is_filer is not False and re.search(
        r"\b(?:merger sub\w*|merger subsidiary|holdco|purchaser|acquisition sub\w*)\b"
        r"(?: [a-z0-9]+){0,10}? (?:a|an) (?:[a-z]+ ){0,3}"
        r"(?:wholly owned|wholly-owned|direct|indirect)(?: [a-z]+){0,3}"
        r" subsidiary of the company\b",
        norm_all,
    ):
        a_score += 3  # the merger sub / holdco belongs to the filer: the filer is the buyer
        reasons.append("sub_is_subsidiary_of_filer")
    t_score, a_score = score_reasons(reasons)  # each kind of evidence counts once
    spac_like = is_spac_name(filer_name)
    if spac_like:
        reasons.append("spac_name_excluded")
    excluded = spac_like
    if "2.01" in set(items):  # completion of an acquisition: not an announcement
        reasons.append("item_2_01_excluded")
        excluded = True
    norm_text = norm_all
    head_1_01 = norm_text[norm_text.find("item 1 01") :][:600] if "item 1 01" in norm_text else ""
    if _AMENDMENT_RE.search(norm_text) or re.search(
        r"\bamendment (?:no \d+ )?to (?:the |that certain )?"
        r"(?:agreement and plan of|merger agreement)",
        head_1_01,
    ):
        reasons.append("amendment_excluded")
        excluded = True
    if "holding company reorganization" in norm_text:
        reasons.append("holdco_reorg_excluded")
        excluded = True
    score = t_score - a_score
    return {
        "target_score": t_score,
        "acquirer_score": a_score,
        "is_target_rule": bool(score >= 2 and not excluded),
        "rule_reasons": ";".join(dict.fromkeys(reasons)),
        "snippet": snippet,
        "deal_type": detect_deal_type(main_text + " " + ex2_head),
    }


_SPAC_RE = re.compile(
    r"\b(?:acquisition|merger)\b(?:\s+(?:[ivx]+|\d+|one|two|three|four|five))?"
    r"\s+(?:corp|corporation|co|company|inc|ltd|limited|holdings)\b",
    re.IGNORECASE,
)


#: 8-K whose Item 1.01 is an amendment to an earlier merger agreement, not the deal itself.
_AMENDMENT_RE = re.compile(
    r"item 1 01 (?:entry into (?:a )?(?:material )?(?:definitive )?agreement )?"
    r"(?:(?:first|second|third|fourth|fifth|sixth) )?(?:amendment|amended|amendments)\b"
)


def is_spac_name(name: str | None) -> bool:
    """Blank-check shells ('... Acquisition Corp III'): de-SPAC 8-Ks are not target news."""
    return bool(name and _SPAC_RE.search(normalize(name)))


def detect_deal_type(text: str) -> str:
    """cash / stock / mixed from consideration keywords; empty when neither shows up."""
    t = normalize(text)
    cash = bool(
        re.search(
            r"\bin cash\b|\bcash consideration\b|\bper share in cash\b|\bcash without interest\b", t
        )
        or re.search(r"\$ ?\d+(?: \d+)? per share", t)
    )
    stock = bool(
        re.search(
            r"\bexchange ratio\b|\bshares of (?:parent )?(?:class a )?common stock of parent\b", t
        )
        or re.search(r"\bshares of [a-z0-9 ]{1,40} common stock for each share\b", t)
        or re.search(r"\bstock consideration\b|\bshare consideration\b", t)
    )
    election = "cash or stock" in t or "cash election" in t or "stock election" in t
    if (cash and stock) or election:
        return "mixed"
    if cash:
        return "cash"
    if stock:
        return "stock"
    return ""


# --------------------------------------------------------------------------
# fetch stage
# --------------------------------------------------------------------------


def fetch_one(client: SecClient, cik: int, adsh: str) -> dict:
    nodash = adsh.replace("-", "")
    url = ARCHIVE_TXT_URL.format(cik=cik, nodash=nodash, adsh=adsh)
    status, body = client.get(url, max_bytes=FETCH_MAX_BYTES)
    if status not in {200, 206}:
        return {"adsh": adsh, "cik": cik, "http_status": status}
    parsed = parse_submission_head(body.decode("utf-8", errors="replace"))
    verdict = classify_filing(
        parsed["main_text"], parsed["filer_name"], parsed["ex2_head"], items=()
    )
    return {
        "adsh": adsh,
        "cik": cik,
        "http_status": status,
        "acceptance_et": parsed["acceptance_et"],
        "filer_name": parsed["filer_name"],
        "text_len": len(parsed["main_text"]),
        # kept so the rule can be re-run offline (``--stage reclassify``) without refetching
        "main_text": parsed["main_text"][:20000],
        "ex2_head": parsed["ex2_head"],
        **verdict,
    }


def stage_fetch(
    client: SecClient,
    candidates: pd.DataFrame,
    *,
    docs_root: Path,
    limit: int | None = None,
    workers: int = 4,
) -> None:
    docs_root.mkdir(parents=True, exist_ok=True)
    done = set()
    for path in docs_root.glob("*.jsonl"):
        for line in path.read_text(encoding="utf-8").splitlines():
            if line:
                done.add(json.loads(line)["adsh"])
    todo = candidates[~candidates["adsh"].isin(done)].sort_values("file_date")
    if limit:
        todo = todo.head(limit)
    log(f"fetch: {len(todo)} to do, {len(done)} done")
    rows = list(todo.itertuples(index=False))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = pool.map(lambda r: (r, fetch_one(client, int(r.cik), r.adsh)), rows)
        for n, (row, record) in enumerate(futures, 1):
            record["file_date"] = row.file_date
            record["items"] = list(row.items)
            path = docs_root / f"{row.file_date[:7].replace('-', '')}.jsonl"
            with path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(record) + "\n")
            if n % 200 == 0:
                log(f"fetch {n}/{len(rows)} last={row.file_date}")


# --------------------------------------------------------------------------
# build stage
# --------------------------------------------------------------------------


def deal_followup_flags(
    events: pd.DataFrame, confirm: pd.DataFrame, sessions: list[date]
) -> pd.Series:
    """True when the same CIK filed DEFA14A / SC14D9C within 5 sessions after the 8-K."""
    if confirm.empty:
        return pd.Series(False, index=events.index)
    by_cik = {c: sorted(g["file_date"]) for c, g in confirm.groupby("cik")}
    idx = {s: i for i, s in enumerate(sessions)}
    out = []
    for r in events.itertuples():
        start = r.trade_date
        if start not in idx:
            out.append(False)
            continue
        end = sessions[min(idx[start] + 5, len(sessions) - 1)]
        out.append(any(start <= d <= end for d in by_cik.get(r.cik, [])))
    return pd.Series(out, index=events.index)


def load_confirm(confirm_root: Path) -> pd.DataFrame:
    rows = []
    for path in sorted(confirm_root.glob("*/*.json")):
        for hit in json.loads(path.read_text(encoding="utf-8"))["hits"]:
            for cik in hit["ciks"]:
                rows.append({"cik": int(cik), "file_date": date.fromisoformat(hit["file_date"])})
    return pd.DataFrame(rows, columns=["cik", "file_date"]).drop_duplicates()


def stage_build(
    *,
    candidates: pd.DataFrame,
    docs_root: Path,
    confirm_root: Path,
    history: dict[int, list[tuple[str, date, date]]],
    current: dict[int, str],
    out_root: Path,
) -> pd.DataFrame:
    recs = []
    for path in sorted(docs_root.glob("*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if line:
                recs.append(json.loads(line))
    docs = pd.DataFrame(recs)
    docs = docs[docs["http_status"].isin([200, 206]) & docs["acceptance_et"].notna()].copy()
    # re-run the rule on the stored text so a rule fix never needs a refetch
    verdicts = pd.DataFrame(
        [
            classify_filing(m or "", n, e or "", items=it)
            for m, n, e, it in zip(
                docs["main_text"], docs["filer_name"], docs["ex2_head"], docs["items"], strict=True
            )
        ],
        index=docs.index,
    )
    docs = docs.drop(columns=[c for c in verdicts.columns if c in docs.columns]).join(verdicts)
    docs["cik"] = docs["cik"].astype("int64")
    docs["acceptance_utc"] = docs["acceptance_et"].map(acceptance_to_utc)
    all_sessions = list(us_equity_session_dates(date(2015, 12, 1), date(2026, 12, 31)))
    docs["trade_date"] = [trade_date_for(s, all_sessions) for s in docs["acceptance_et"]]
    docs["filing_date"] = [
        datetime.strptime(s, "%Y%m%d%H%M%S").date() for s in docs["acceptance_et"]
    ]
    syms = [
        map_cik_symbol(int(c), d, history, current)
        for c, d in zip(docs["cik"], docs["filing_date"], strict=True)
    ]
    docs["symbol"] = [s for s, _ in syms]
    docs["symbol_source"] = [m for _, m in syms]
    docs["source_url"] = [
        ARCHIVE_INDEX_URL.format(cik=c, nodash=a.replace("-", ""), adsh=a)
        for c, a in zip(docs["cik"], docs["adsh"], strict=True)
    ]
    docs["visible_at"] = docs["acceptance_utc"]
    docs["item_codes"] = docs["items"].map(lambda x: ",".join(x))
    docs["has_target_followup_5d"] = deal_followup_flags(
        docs, load_confirm(confirm_root), all_sessions
    ).astype(bool)
    docs = docs.sort_values(["cik", "acceptance_utc"]).reset_index(drop=True)
    # first target-rule 8-K per CIK within a 365 day window (later ones are amendments)
    first = []
    last_seen: dict[int, pd.Timestamp] = {}
    for r in docs.itertuples():
        if not r.is_target_rule:
            first.append(False)
            continue
        prev = last_seen.get(r.cik)
        is_first = prev is None or (r.acceptance_utc - prev).days > 365
        first.append(is_first)
        if is_first:
            last_seen[r.cik] = r.acceptance_utc
    docs["is_first_for_cik_365d"] = first
    cols = [
        "symbol",
        "cik",
        "filing_date",
        "trade_date",
        "acceptance_utc",
        "visible_at",
        "item_codes",
        "deal_type",
        "source_url",
        "is_target_rule",
        "is_first_for_cik_365d",
        "has_target_followup_5d",
        "target_score",
        "acquirer_score",
        "rule_reasons",
        "symbol_source",
        "filer_name",
        "adsh",
    ]
    out = docs[cols].copy()
    out["filing_date"] = pd.to_datetime(out["filing_date"])
    out["trade_date"] = pd.to_datetime(out["trade_date"])
    out_root.mkdir(parents=True, exist_ok=True)
    for path in out_root.glob("*.parquet"):
        path.unlink()
    for year, g in out.groupby(out["filing_date"].dt.year):
        g.to_parquet(out_root / f"{year}.parquet", index=False)
    return out


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--stage", choices=("search", "confirm", "fetch", "build"), required=True)
    ap.add_argument("--start", default="2016-01")
    ap.add_argument("--end", default=datetime.now().strftime("%Y-%m"))
    ap.add_argument("--limit", type=int, help="fetch: at most N accessions this run")
    ap.add_argument("--workers", type=int, default=4, help="fetch: concurrent connections")
    ap.add_argument("--min-interval", type=float, default=MIN_REQUEST_INTERVAL_SECONDS)
    ap.add_argument("--raw-root", type=Path, default=RAW_ROOT)
    ap.add_argument("--out-root", type=Path, default=OUT_ROOT)
    args = ap.parse_args(argv)

    raw: Path = args.raw_root
    client = SecClient(min_interval=args.min_interval)
    try:
        if args.stage == "search":
            stage_search(
                client, month_windows(args.start, args.end), queries=QUERIES, root=raw / "fts"
            )
        elif args.stage == "confirm":
            stage_search(
                client,
                month_windows(args.start, args.end),
                queries={"confirm": CONFIRM_QUERY},
                root=raw / "confirm",
            )
        else:
            hist_path = raw / "cik_symbol_history.parquet"
            if not hist_path.exists():
                raw.mkdir(parents=True, exist_ok=True)
                build_cik_symbol_history(ROOT / "data" / "raw" / "insider").to_parquet(hist_path)
            history = history_lookup(pd.read_parquet(hist_path))
            current = load_current_tickers(client, raw / "company_tickers.json")
            cands = load_candidates(raw / "fts")
            cands["symbol_probe"] = [
                map_cik_symbol(int(c), date.fromisoformat(d), history, current)[0]
                for c, d in zip(cands["cik"], cands["file_date"], strict=True)
            ]
            mapped = cands[cands["symbol_probe"].notna()]
            log(f"candidates {len(cands)}; mapped to a symbol {len(mapped)}")
            if args.stage == "fetch":
                stage_fetch(
                    client, mapped, docs_root=raw / "docs", limit=args.limit, workers=args.workers
                )
            else:
                out = stage_build(
                    candidates=cands,
                    docs_root=raw / "docs",
                    confirm_root=raw / "confirm",
                    history=history,
                    current=current,
                    out_root=args.out_root,
                )
                log(f"built {len(out)} rows; target rule {int(out['is_target_rule'].sum())}")
    finally:
        client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
