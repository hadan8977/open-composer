#!/usr/bin/env python3
"""Bottom-up bulk harvest: pull the whole archive, classify every item against
the coverage map, then digest by cell.

Card: ``docs/plan-research-coverage-2026-09-23.zh.md`` section 4 rule 7 (the
two search modes -- top-down by coverage cell, bottom-up by bulk ingest) and
section 3 (the coverage map itself, machine-readable at
``reports/research/harvest/coverage.json``). Where ``scripts/harvest_search.py``
asks a narrow question and searches for an answer, this script goes the other
way: pull everything quant-related the archive has, classify each item
against every coverage cell independently of any search topic, then let gaps
(cells with nothing, or items that fit no cell at all) show up bottom-up.

Three subcommands, run under the project venv::

    uv run python scripts/harvest_feed.py pull --corpus articles
    uv run python scripts/harvest_feed.py pull --corpus repos --min-stars 100
    uv run python scripts/harvest_feed.py classify --corpus articles --batch 10 --max-calls 5
    uv run python scripts/harvest_feed.py digest

``pull`` pages through the archive REST API (``researcher.marketmaker.cc``,
the same one ``harvest_search.py``'s ``archive`` channel uses), dedupes by
URL and appends new items to ``/opt/oc-search/feed/items/<corpus>.jsonl``
(bulk data, outside the repo, like ``/opt/oc-search/cache``). Resumable: a
rerun keeps what it already has and only appends items it has not seen. For
``repos`` the API itself honours ``min_stars`` as a server-side filter
(confirmed by probing on 2026-09-23: ``/repos?min_stars=100`` returns
``total=2764`` instead of ``39917``), so ``--min-stars`` is passed straight
through rather than paging everything and filtering locally. There is no
working server-side date filter (a probed ``since=`` parameter changed
nothing), so ``--since`` is a local post-filter instead.

``classify`` sends unclassified items (title + description/abstract,
truncated) to the owner's DeepSeek-compatible endpoint in batches, using one
system prompt per run (built from the current coverage map, hashed once and
stamped on every output row) that asks for strict per-item JSON. Output goes
to ``/opt/oc-search/feed/classified/<corpus>.jsonl``, checkpointed after every
batch so a stopped run loses at most one batch of unwritten work. Credentials,
rate-limit handling and the shared quota gate reuse
``scripts/score_earnings_text.py``'s helpers (``load_credentials``,
``ChatCallResult``, ``compute_next_try_at``, ``RateLimitStop``,
``write_next_try_at``, and the shared
``data/features/earnings_text_scores/next_try_at.json`` cool-down file) by
import rather than by copying them. Two of those helpers were fixed at the
source on 2026-09-23 for this tool: ``make_requests_chat_call_fn`` takes
``max_tokens`` (a batch reply needs ~2000), and ``is_rate_limited`` no longer
keyword-scans a successful reply, whose text can legitimately say
"limitations".

``digest`` reads every classified row (no network) and writes
``reports/research/harvest/feed-digest-<date>.md`` (per cell: counts by
evidence tier, top 12 relevant items; a section for items whose cells are
``new:*``, i.e. items that point at a coverage-map gap; totals) plus
``reports/research/harvest/feed-cell-counts.json`` (small, commit-sized).

Hard constraints repeated here because this script is where they bite:
credentials are read only through ``scorer.load_credentials`` and are never
printed, logged, or written anywhere except as the Authorization header of
the chat-completions call; on HTTP 429 or a "limit"/"quota" reply the whole
``classify`` run stops immediately, checkpoints what it has, writes
``next_try_at.json``, and exits 0; ``classify`` also checks that same file
*before* doing anything if it is already in the future. Classification
itself is delegated entirely to the endpoint -- nothing here uses model
reasoning to fill in a coverage cell.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from scripts import score_earnings_text as scorer
from scripts.harvest_search import ARCHIVE, normalize_url
from scripts.score_earnings_text import (
    ChatCallFn,
    ChatCallResult,
    RateLimitStop,
    compute_next_try_at,
    sha256_hex,
)

ROOT = Path(__file__).resolve().parents[1]
HARVEST_DIR = ROOT / "reports" / "research" / "harvest"
COVERAGE_PATH = HARVEST_DIR / "coverage.json"
LOG_PATH = ROOT / "logs" / "harvest_feed.log"

FEED_HOME = Path("/opt/oc-search/feed")
ITEMS_DIR = FEED_HOME / "items"
CLASSIFIED_DIR = FEED_HOME / "classified"
CALL_LOG_PATH = CLASSIFIED_DIR / "call-log.jsonl"

CORPORA = ("articles", "papers", "repos")
ITEM_TEXT_CHARS = 600

EVIDENCE_ORDER = (
    "live_record",
    "forward_test",
    "independent_replication",
    "author_backtest",
    "claim_only",
    "theory",
    "tool_or_data",
)
EVIDENCE_RANK = {name: rank for rank, name in enumerate(EVIDENCE_ORDER)}
VALID_MARKET_HINTS = ("us_equity_etf", "other_market", "unclear")
VALID_HORIZON = {"intraday", "days", "weeks", "months"}
VALID_DATA_NEEDED = {"local_price", "free_other", "paid", "unknown"}
VALID_LONG_ONLY_OK = {"yes", "no", "unknown"}

#: Pages sorted newest-first (confirmed by probing on 2026-09-23: default
#: ``articles``/``papers`` order is date-descending and never reshuffles as
#: new items are appended) can stop as soon as a whole page has nothing new.
#: ``repos`` is sorted by stars, which reorders as star counts change, so a
#: "fully seen" page there does not reliably mean older pages are seen too;
#: it is cheap enough (a few thousand items with ``--min-stars``) to always
#: page through fully instead.
EARLY_STOP_CORPORA = {"articles", "papers"}

LOG = logging.getLogger("harvest_feed")


def _setup_logging() -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    if LOG.handlers:
        return
    LOG.setLevel(logging.INFO)
    LOG.propagate = False
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    file_handler = logging.FileHandler(LOG_PATH)
    file_handler.setFormatter(formatter)
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)
    LOG.addHandler(file_handler)
    LOG.addHandler(stream_handler)


def now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def read_jsonl(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def load_coverage_cells(path: Path | None = None) -> list[dict]:
    data = json.loads((path or COVERAGE_PATH).read_text(encoding="utf-8"))
    return data.get("cells", [])


# --------------------------------------------------------------------------
# pull
# --------------------------------------------------------------------------


@dataclass
class PullStats:
    corpus: str
    total_available: int = 0
    pulled_new: int = 0
    pages_fetched: int = 0
    stopped_early_for_time: bool = False
    stopped_early_no_new: bool = False


def passes_since(item: dict, since: str) -> bool:
    """Local post-filter: the archive's ``since=`` query parameter is a
    no-op (probed 2026-09-23: identical ``total`` and ordering with or
    without it), so date filtering happens here instead. Undated items are
    kept rather than silently dropped."""

    date = (item.get("date") or item.get("published") or item.get("created_at") or "")[:10]
    return True if not date else date >= since


def pull_corpus(
    corpus: str,
    fetch_page: Callable[[dict], dict],
    *,
    existing_urls: set[str],
    min_stars: int | None = None,
    since: str | None = None,
    page_size: int = 100,
    delay: float = 0.3,
    time_budget_s: float | None = 900.0,
    early_stop: bool | None = None,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
    on_page: Callable[[list[dict]], None] | None = None,
) -> tuple[PullStats, list[dict]]:
    """Page through one corpus and return ``(stats, new_rows)``.

    Pure and network-free by itself: ``fetch_page(params) -> body`` (the
    parsed JSON response) and ``existing_urls`` (already-seen, normalized
    URLs from a prior run) are both injected, so this is unit-testable
    without touching the network or disk. The real HTTP call with retries
    and backoff lives in ``_archive_get``, used only from ``cmd_pull``.

    ``on_page``, if given, is called with just that page's new rows right
    after each page is processed, so a caller can checkpoint to disk
    incrementally (a run stopped between pages then loses at most one
    page of unwritten work, not the whole pull). The full accumulated
    list is still returned at the end either way.
    """

    if early_stop is None:
        early_stop = corpus in EARLY_STOP_CORPORA
    seen = set(existing_urls)
    new_rows: list[dict] = []
    stats = PullStats(corpus=corpus)
    offset = 0
    start = clock()
    while True:
        if time_budget_s is not None and clock() - start > time_budget_s:
            stats.stopped_early_for_time = True
            break
        params = {"limit": page_size, "offset": offset}
        if corpus == "repos" and min_stars is not None:
            params["min_stars"] = min_stars
        body = fetch_page(params)
        stats.total_available = body.get("total", 0)
        items = body.get("items") or []
        if not items:
            break
        stats.pages_fetched += 1
        page_had_new = False
        page_rows: list[dict] = []
        for item in items:
            url = item.get("url")
            if not url:
                continue
            key = normalize_url(url)
            if key in seen:
                continue
            seen.add(key)
            page_had_new = True
            if since and not passes_since(item, since):
                continue
            page_rows.append({"corpus": corpus, "pulled_at": now_iso(), **item})
        new_rows.extend(page_rows)
        stats.pulled_new = len(new_rows)
        if page_rows and on_page is not None:
            on_page(page_rows)
        offset += page_size
        if offset >= stats.total_available:
            break
        if early_stop and not page_had_new:
            stats.stopped_early_no_new = True
            break
        sleep(delay)
    return stats, new_rows


def _archive_get(corpus: str, params: dict, *, timeout: float, retries: int) -> dict:
    import requests

    last_error: str | None = None
    for attempt in range(retries):
        try:
            resp = requests.get(f"{ARCHIVE}/{corpus}", params=params, timeout=timeout)
        except requests.RequestException as exc:
            last_error = str(exc)
        else:
            if resp.status_code == 200:
                return resp.json()
            last_error = f"HTTP {resp.status_code}"
        if attempt < retries - 1:
            time.sleep(min(2**attempt, 20))
    raise RuntimeError(f"archive fetch failed for {corpus} {params}: {last_error}")


def cmd_pull(args: argparse.Namespace) -> int:
    _setup_logging()
    if args.min_stars is not None and args.corpus != "repos":
        print(f"--min-stars only applies to --corpus repos; ignoring for {args.corpus}")
        args.min_stars = None

    ITEMS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = ITEMS_DIR / f"{args.corpus}.jsonl"
    existing = read_jsonl(out_path)
    existing_urls = {normalize_url(row["url"]) for row in existing if row.get("url")}

    def fetch_page(params: dict) -> dict:
        return _archive_get(args.corpus, params, timeout=args.timeout, retries=args.retries)

    def checkpoint_page(page_rows: list[dict]) -> None:
        with out_path.open("a", encoding="utf-8") as handle:
            for row in page_rows:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    time_budget_s = args.time_budget_minutes * 60 if args.time_budget_minutes else None
    stats, _new_rows = pull_corpus(
        args.corpus,
        fetch_page,
        existing_urls=existing_urls,
        min_stars=args.min_stars,
        since=args.since,
        page_size=args.page_size,
        delay=args.delay,
        time_budget_s=time_budget_s,
        on_page=checkpoint_page,
    )

    LOG.info(
        "pull corpus=%s total_available=%d pulled_new=%d pages=%d "
        "stopped_for_time=%s stopped_no_new=%s",
        stats.corpus,
        stats.total_available,
        stats.pulled_new,
        stats.pages_fetched,
        stats.stopped_early_for_time,
        stats.stopped_early_no_new,
    )
    notice = ""
    if stats.stopped_early_for_time:
        notice = " (stopped: time budget)"
    elif stats.stopped_early_no_new:
        notice = " (stopped: reached already-pulled items)"
    print(
        f"{args.corpus}: total_available={stats.total_available} pulled_new={stats.pulled_new} "
        f"pages_fetched={stats.pages_fetched} already_had={len(existing_urls)}{notice}"
    )
    return 0


# --------------------------------------------------------------------------
# classify: prompt building
# --------------------------------------------------------------------------

_PROMPT_HEADER = (
    "You are a quantitative-research triage assistant for a personal US-equity trading "
    "research project. You will be given a numbered batch of items pulled in bulk from a "
    "quant-content archive (blog posts, arXiv papers, or GitHub repos). For EACH item, decide "
    "where it fits in this project's coverage map and how strong its performance evidence is. "
    "Judge only from the text given; do not use outside knowledge about the source.\n\n"
    "Coverage map cells (id: name):"
)

_PROMPT_FIELDS = (
    "For each item, output one JSON object with these fields:\n"
    '- "index": integer, the item position in this batch (matches its "Item N" label), '
    "starting at 1.\n"
    '- "relevant": true/false -- is this trading or investing research applicable to US '
    "equities or US-listed ETFs (long or short, any horizon)? false for unrelated topics "
    "(crypto-only, forex-only, non-US markets, non-finance software, etc).\n"
    '- "cells": a list of 1 to 3 coverage-cell ids from the list above that this item best '
    'fits. If nothing above fits AND "relevant" is true, use a single-element list with '
    '"new:<short label>" (a short new label you invent, e.g. "new:sec_form_144_signal") -- '
    "this marks a genuine gap in the coverage map, so only use it for something that really "
    'is US-equity/ETF trading or investing research. If "relevant" is false, never invent a '
    '"new:" label: pick the closest existing cell(s) instead, using '
    '"out_of_scope.crypto_nonus" for crypto, non-US or other markets this project cannot '
    "trade, or the closest topical cell for anything else not about trading or investing at "
    "all (e.g. general software, math, or unrelated research).\n"
    '- "evidence": the strongest performance evidence the item itself states, one of: '
    '"live_record" (real-money or independently tracked forward results), "forward_test" (a '
    "preregistered or out-of-sample test the authors ran going forward), "
    '"independent_replication" (someone other than the original author reproduced the '
    'result), "author_backtest" (only the original author\'s historical backtest), '
    '"claim_only" (performance claims with no backtest or record shown), "theory" (no '
    'empirical result at all -- a pure methodology or theory piece), "tool_or_data" (not a '
    "strategy at all -- a data source, library or tool).\n"
    '- "market": one of {market_hints}.\n'
    '- "horizon": one of "intraday", "days", "weeks", "months" -- the holding period the item '
    'discusses; pick the closest if several are mentioned, "months" if unspecified but '
    "clearly not short-term.\n"
    '- "data_needed": one of "local_price" (only price/volume history), "free_other" (other '
    'data available free, e.g. filings, news, macro), "paid" (needs a paid data source), '
    '"unknown".\n'
    '- "long_only_ok": "yes" if the idea works long-only, "no" if it inherently needs '
    'shorting, "unknown".\n'
    '- "reported_performance": a short string with any numbers the text itself states (e.g. '
    '"Sharpe 1.4, 2019-2023"), or null if the text gives no numbers.\n'
    '- "summary": one plain sentence describing the item.\n'
    '- "novelty": integer 1-5, how novel this is versus well-known factors/strategies (1 = '
    "textbook RSI/MACD/momentum, 5 = a mechanism you have not seen described before).\n\n"
    "Reply with ONLY a JSON array with exactly one object per item above, in the same order, "
    "no other text, no Markdown code fence."
)

_REPAIR_INSTRUCTION = (
    "Your last reply was not a valid JSON array matching the required schema (wrong length, "
    "invalid JSON, or a field failed validation). Reply again with ONLY a corrected JSON array "
    "with exactly one object per item above, in the same order that they appeared, no other "
    "text, no Markdown code fence."
)


def build_system_prompt(cells: list[dict]) -> str:
    listing = "\n".join(f"- {c['id']}: {c['name']}" for c in sorted(cells, key=lambda c: c["id"]))
    market_hints = ", ".join(f'"{hint}"' for hint in VALID_MARKET_HINTS)
    fields = _PROMPT_FIELDS.format(market_hints=market_hints)
    return f"{_PROMPT_HEADER}\n{listing}\n\n{fields}"


def display_source(corpus: str, item: dict) -> str:
    if corpus == "articles":
        return item.get("source") or ""
    if corpus == "papers":
        return "arXiv"
    return "GitHub"


def truncate(text: str, limit: int = ITEM_TEXT_CHARS) -> str:
    text = (text or "").strip()
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def item_title_and_meta(corpus: str, item: dict) -> tuple[str, str, str]:
    title = (item.get("title") or item.get("name") or "").strip()
    if corpus == "articles":
        meta = f"source={item.get('source') or ''} date={item.get('date') or ''}"
        body = item.get("desc") or ""
    elif corpus == "papers":
        authors = ", ".join(item.get("authors") or [])[:200]
        meta = f"authors={authors} date={item.get('published') or ''}"
        body = item.get("abstract") or ""
    else:
        topics = ", ".join(item.get("topics") or [])[:200]
        meta = f"stars={item.get('stars')} topics={topics} date={item.get('created_at') or ''}"
        body = item.get("description") or ""
    return title, meta, body


def build_user_message(corpus: str, batch: list[dict]) -> str:
    blocks = [f"Corpus: {corpus}"]
    for position, item in enumerate(batch, start=1):
        title, meta, body = item_title_and_meta(corpus, item)
        blocks.append(f"Item {position}:\nTitle: {title}\n{meta}\nText: {truncate(body)}")
    return "\n\n".join(blocks)


def item_identity_fields(corpus: str, item: dict) -> dict:
    title = (item.get("title") or item.get("name") or "").strip()
    date = (item.get("date") or item.get("published") or item.get("created_at") or "")[:10]
    return {
        "corpus": corpus,
        "url": item.get("url"),
        "title": title,
        "source": display_source(corpus, item),
        "item_date": date,
    }


# --------------------------------------------------------------------------
# classify: reply parsing / validation
# --------------------------------------------------------------------------

_CODE_FENCE_RE__PREFIX = "```"


def _strip_code_fence(content: str) -> str:
    stripped = content.strip()
    if stripped.startswith(_CODE_FENCE_RE__PREFIX):
        stripped = stripped[len(_CODE_FENCE_RE__PREFIX) :]
        stripped = stripped.split("\n", 1)[1] if "\n" in stripped else ""
    if stripped.endswith(_CODE_FENCE_RE__PREFIX):
        stripped = stripped[: -len(_CODE_FENCE_RE__PREFIX)]
    return stripped.strip()


def _extract_json_array(content: str) -> object | None:
    stripped = _strip_code_fence(content)
    try:
        obj = json.loads(stripped)
        if isinstance(obj, list):
            return obj
    except (json.JSONDecodeError, TypeError):
        pass
    start, end = stripped.find("["), stripped.rfind("]")
    if start == -1 or end == -1 or end < start:
        return None
    try:
        obj = json.loads(stripped[start : end + 1])
    except json.JSONDecodeError:
        return None
    return obj if isinstance(obj, list) else None


def validate_item_obj(obj: object, *, expected_index: int, known_cell_ids: set[str]) -> dict | None:
    if not isinstance(obj, dict):
        return None
    if obj.get("index") != expected_index:
        return None
    if not isinstance(obj.get("relevant"), bool):
        return None
    cells = obj.get("cells")
    if not isinstance(cells, list) or not (1 <= len(cells) <= 3):
        return None
    clean_cells = []
    for cell in cells:
        if not isinstance(cell, str):
            return None
        cell = cell.strip()
        if cell.startswith("new:"):
            if len(cell) <= len("new:"):
                return None
        elif cell not in known_cell_ids:
            return None
        clean_cells.append(cell)
    if obj.get("evidence") not in EVIDENCE_RANK:
        return None
    market = obj.get("market")
    if not isinstance(market, str) or not market.strip():
        return None
    if obj.get("horizon") not in VALID_HORIZON:
        return None
    if obj.get("data_needed") not in VALID_DATA_NEEDED:
        return None
    if obj.get("long_only_ok") not in VALID_LONG_ONLY_OK:
        return None
    reported = obj.get("reported_performance")
    if reported is not None and not isinstance(reported, str):
        return None
    summary = obj.get("summary")
    if not isinstance(summary, str) or not summary.strip():
        return None
    try:
        novelty = int(obj.get("novelty"))
    except (TypeError, ValueError):
        return None
    if not (1 <= novelty <= 5):
        return None
    return {
        "relevant": obj["relevant"],
        "cells": clean_cells,
        "evidence": obj["evidence"],
        "market": market.strip(),
        "horizon": obj["horizon"],
        "data_needed": obj["data_needed"],
        "long_only_ok": obj["long_only_ok"],
        "reported_performance": (reported.strip() if reported else None) or None,
        "summary": summary.strip(),
        "novelty": novelty,
    }


def parse_batch_reply(
    content: str, *, batch_size: int, known_cell_ids: set[str]
) -> list[dict] | None:
    array = _extract_json_array(content)
    if array is None or len(array) != batch_size:
        return None
    results = []
    for position, obj in enumerate(array, start=1):
        validated = validate_item_obj(obj, expected_index=position, known_cell_ids=known_cell_ids)
        if validated is None:
            return None
        results.append(validated)
    return results


def _empty_classification_fields() -> dict:
    return {
        "relevant": None,
        "cells": [],
        "evidence": None,
        "market": None,
        "horizon": None,
        "data_needed": None,
        "long_only_ok": None,
        "reported_performance": None,
        "summary": None,
        "novelty": None,
    }


# --------------------------------------------------------------------------
# classify: endpoint call
# --------------------------------------------------------------------------


def _raise_rate_limit_stop(result: ChatCallResult) -> None:
    reason = f"HTTP {result.status_code}" if result.status_code == 429 else "quota/limit in body"
    raise RateLimitStop(compute_next_try_at(result, now=datetime.now(UTC)), reason)


def _call_with_repair(
    messages: list[dict[str, str]],
    *,
    batch_size: int,
    call_fn: ChatCallFn,
    known_cell_ids: set[str],
) -> tuple[list[dict] | None, int, int]:
    result = call_fn(messages)
    if scorer.is_rate_limited(result):
        _raise_rate_limit_stop(result)
    prompt_tokens, completion_tokens = result.prompt_tokens, result.completion_tokens
    parsed = None
    if result.status_code == 200 and result.content_text:
        parsed = parse_batch_reply(
            result.content_text, batch_size=batch_size, known_cell_ids=known_cell_ids
        )
    if parsed is None:
        repair_messages = [
            *messages,
            {"role": "assistant", "content": result.content_text or ""},
            {"role": "user", "content": _REPAIR_INSTRUCTION},
        ]
        retry_result = call_fn(repair_messages)
        if scorer.is_rate_limited(retry_result):
            _raise_rate_limit_stop(retry_result)
        prompt_tokens += retry_result.prompt_tokens
        completion_tokens += retry_result.completion_tokens
        if retry_result.status_code == 200 and retry_result.content_text:
            parsed = parse_batch_reply(
                retry_result.content_text, batch_size=batch_size, known_cell_ids=known_cell_ids
            )
    return parsed, prompt_tokens, completion_tokens


# --------------------------------------------------------------------------
# classify: batch loop
# --------------------------------------------------------------------------


@dataclass
class ClassifyStats:
    calls: int = 0
    processed: int = 0
    ok: int = 0
    parse_error: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    stopped_for_rate_limit: bool = False
    rate_limit_stop: RateLimitStop | None = None


def chunk(seq: list, n: int) -> list[list]:
    return [seq[i : i + n] for i in range(0, len(seq), n)]


def already_classified_urls(corpus: str) -> set[str]:
    path = CLASSIFIED_DIR / f"{corpus}.jsonl"
    return {row["url"] for row in read_jsonl(path) if row.get("url")}


def pending_items(items: list[dict], already: set[str]) -> list[dict]:
    seen = {normalize_url(u) for u in already}
    return [item for item in items if item.get("url") and normalize_url(item["url"]) not in seen]


def classify_items(
    corpus: str,
    pending: list[dict],
    *,
    batch_size: int,
    max_calls: int,
    call_fn: ChatCallFn,
    model: str,
    system_prompt: str,
    prompt_sha256: str,
    known_cell_ids: set[str],
    on_batch_done: Callable[[list[dict], dict], None],
) -> ClassifyStats:
    """Classify ``pending`` in batches, calling ``on_batch_done(rows,
    call_log_row)`` once per completed (or malformed-after-repair) batch so
    the caller can checkpoint to disk incrementally. Stops immediately (no
    further calls) the first time either call in a batch looks rate-limited;
    whatever batches already completed before that stay checkpointed."""

    stats = ClassifyStats()
    for batch in chunk(pending, batch_size)[:max_calls]:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": build_user_message(corpus, batch)},
        ]
        try:
            parsed, prompt_tokens, completion_tokens = _call_with_repair(
                messages, batch_size=len(batch), call_fn=call_fn, known_cell_ids=known_cell_ids
            )
        except RateLimitStop as stop:
            stats.stopped_for_rate_limit = True
            stats.rate_limit_stop = stop
            return stats

        when = now_iso()
        status = "ok" if parsed is not None else "parse_error"
        rows = []
        for position, item in enumerate(batch):
            fields = parsed[position] if parsed is not None else _empty_classification_fields()
            rows.append(
                {
                    **item_identity_fields(corpus, item),
                    **fields,
                    "status": status,
                    "model": model,
                    "prompt_sha256": prompt_sha256,
                    "classified_at": when,
                }
            )
        if status == "ok":
            stats.ok += len(batch)
        else:
            stats.parse_error += len(batch)
        stats.calls += 1
        stats.processed += len(batch)
        stats.prompt_tokens += prompt_tokens
        stats.completion_tokens += completion_tokens

        call_log_row = {
            "ts": when,
            "corpus": corpus,
            "batch_size": len(batch),
            "status": status,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "model": model,
            "prompt_sha256": prompt_sha256,
        }
        on_batch_done(rows, call_log_row)
    return stats


def cmd_classify(args: argparse.Namespace) -> int:
    _setup_logging()
    now = datetime.now(UTC)
    if scorer.NEXT_TRY_PATH.is_file():
        try:
            payload = json.loads(scorer.NEXT_TRY_PATH.read_text(encoding="utf-8"))
            next_try_at = datetime.strptime(payload["next_try_at"], "%Y-%m-%dT%H:%M:%SZ")
            next_try_at = next_try_at.replace(tzinfo=UTC)
        except (OSError, ValueError, KeyError):
            next_try_at = None
        if next_try_at is not None and next_try_at > now:
            reason = payload.get("reason", "")
            print(f"quota cool-down active until {payload['next_try_at']} ({reason}); exiting")
            LOG.info("classify: honouring existing next_try_at=%s", payload["next_try_at"])
            return 0

    items_path = ITEMS_DIR / f"{args.corpus}.jsonl"
    if not items_path.is_file():
        print(f"no pulled items for corpus={args.corpus}; run `pull --corpus {args.corpus}` first")
        return 1
    items = read_jsonl(items_path)
    pending = pending_items(items, already_classified_urls(args.corpus))
    if not pending:
        print(f"{args.corpus}: nothing pending ({len(items)} items, all already classified)")
        return 0

    cells = load_coverage_cells()
    known_cell_ids = {c["id"] for c in cells}
    system_prompt = build_system_prompt(cells)
    prompt_sha256 = sha256_hex(system_prompt)

    creds = scorer.load_credentials(scorer.CREDENTIALS_PATH)
    model = creds["OC_TEXT_SCORER_MODEL"]
    max_tokens = min(8000, 150 + 300 * args.batch)
    call_fn = scorer.make_requests_chat_call_fn(
        base_url=creds["OC_TEXT_SCORER_BASE_URL"],
        api_key=creds["OC_TEXT_SCORER_API_KEY"],
        model=model,
        max_tokens=max_tokens,
    )
    LOG.info(
        "classify start corpus=%s pending=%d batch=%d max_calls=%d model=%s prompt_sha256=%s",
        args.corpus,
        len(pending),
        args.batch,
        args.max_calls,
        model,
        prompt_sha256,
    )

    CLASSIFIED_DIR.mkdir(parents=True, exist_ok=True)
    classified_path = CLASSIFIED_DIR / f"{args.corpus}.jsonl"

    def on_batch_done(rows: list[dict], call_log_row: dict) -> None:
        with classified_path.open("a", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")
        with CALL_LOG_PATH.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(call_log_row, ensure_ascii=False) + "\n")
        LOG.info(
            "batch corpus=%s batch_size=%d status=%s prompt_tokens=%d completion_tokens=%d "
            "model=%s",
            call_log_row["corpus"],
            call_log_row["batch_size"],
            call_log_row["status"],
            call_log_row["prompt_tokens"],
            call_log_row["completion_tokens"],
            call_log_row["model"],
        )

    stats = classify_items(
        args.corpus,
        pending,
        batch_size=args.batch,
        max_calls=args.max_calls,
        call_fn=call_fn,
        model=model,
        system_prompt=system_prompt,
        prompt_sha256=prompt_sha256,
        known_cell_ids=known_cell_ids,
        on_batch_done=on_batch_done,
    )

    if stats.stopped_for_rate_limit and stats.rate_limit_stop is not None:
        scorer.write_next_try_at(stats.rate_limit_stop.next_try_at, stats.rate_limit_stop.reason)
        LOG.warning(
            "classify stopped for rate limit: %s; next_try_at=%s",
            stats.rate_limit_stop.reason,
            stats.rate_limit_stop.next_try_at.isoformat(),
        )

    LOG.info(
        "classify done corpus=%s calls=%d processed=%d ok=%d parse_error=%d "
        "prompt_tokens=%d completion_tokens=%d stopped_for_rate_limit=%s",
        args.corpus,
        stats.calls,
        stats.processed,
        stats.ok,
        stats.parse_error,
        stats.prompt_tokens,
        stats.completion_tokens,
        stats.stopped_for_rate_limit,
    )
    notice = " (stopped: rate limited)" if stats.stopped_for_rate_limit else ""
    print(
        f"{args.corpus}: calls={stats.calls} processed={stats.processed} ok={stats.ok} "
        f"parse_error={stats.parse_error} tokens={stats.prompt_tokens + stats.completion_tokens}"
        f"{notice}"
    )
    return 0


# --------------------------------------------------------------------------
# digest
# --------------------------------------------------------------------------


def load_all_classified(corpora: tuple[str, ...] = CORPORA) -> list[dict]:
    rows: list[dict] = []
    for corpus in corpora:
        rows.extend(read_jsonl(CLASSIFIED_DIR / f"{corpus}.jsonl"))
    return rows


def rank_items(rows: list[dict]) -> list[dict]:
    """Evidence tier, then novelty, then recency -- two stable sorts (most
    recent first, then grouped by tier/novelty) so ties keep recency order
    without needing to invert a date string into a sortable number."""

    by_recency = sorted(rows, key=lambda r: r.get("item_date") or "", reverse=True)
    return sorted(
        by_recency,
        key=lambda r: (
            EVIDENCE_RANK.get(r.get("evidence"), len(EVIDENCE_RANK)),
            -(r.get("novelty") or 0),
        ),
    )


def bucket_by_cell(
    classified_rows: list[dict],
) -> tuple[dict[str, list[dict]], dict[str, list[dict]]]:
    by_cell: dict[str, list[dict]] = {}
    by_new_label: dict[str, list[dict]] = {}
    for row in classified_rows:
        if row.get("status") != "ok" or not row.get("relevant"):
            continue
        for cell in row.get("cells") or []:
            if cell.startswith("new:"):
                label = cell[len("new:") :].strip() or "unlabeled"
                by_new_label.setdefault(label, []).append(row)
            else:
                by_cell.setdefault(cell, []).append(row)
    return by_cell, by_new_label


def evidence_tier_counts(rows: list[dict]) -> dict[str, int]:
    counts = dict.fromkeys(EVIDENCE_ORDER, 0)
    for row in rows:
        evidence = row.get("evidence")
        if evidence in counts:
            counts[evidence] += 1
    return counts


def compute_totals(corpora: tuple[str, ...], classified_rows: list[dict]) -> dict:
    items_pulled = sum(len(read_jsonl(ITEMS_DIR / f"{corpus}.jsonl")) for corpus in corpora)
    relevant = sum(1 for r in classified_rows if r.get("relevant") is True)
    parse_errors = sum(1 for r in classified_rows if r.get("status") == "parse_error")
    call_rows = read_jsonl(CALL_LOG_PATH)
    tokens = sum(
        (r.get("prompt_tokens") or 0) + (r.get("completion_tokens") or 0) for r in call_rows
    )
    return {
        "items_pulled": items_pulled,
        "items_classified": len(classified_rows),
        "relevant": relevant,
        "parse_errors": parse_errors,
        "calls": len(call_rows),
        "tokens": tokens,
    }


def format_item_line(row: dict) -> str:
    title = row.get("title") or "(untitled)"
    url = row.get("url") or ""
    source = row.get("source") or ""
    date = row.get("item_date") or ""
    summary = row.get("summary") or ""
    performance = row.get("reported_performance")
    performance_part = f" -- reported: {performance}" if performance else ""
    return f"- [{title}]({url}) -- {source}, {date}: {summary}{performance_part}"


def render_digest_markdown(
    *, date: str, cells: list[dict], classified_rows: list[dict], totals: dict
) -> str:
    by_cell, by_new_label = bucket_by_cell(classified_rows)
    lines = [f"# Bulk-feed classification digest -- {date}", ""]
    lines.append(
        "Bottom-up pass over the archive feed "
        "(`docs/plan-research-coverage-2026-09-23.zh.md` section 4 rule 7): every pulled item "
        "is classified against the coverage map independently of any search topic, so gaps "
        "show up by what never lands in a cell."
    )
    lines.append("")
    lines.append("## By coverage cell")
    lines.append("")
    for cell in sorted(cells, key=lambda c: c["id"]):
        rows = by_cell.get(cell["id"], [])
        lines.append(f"### {cell['id']} -- {cell['name']}")
        lines.append("")
        if not rows:
            lines.append("_No relevant items found in this pull._")
            lines.append("")
            continue
        counts = evidence_tier_counts(rows)
        count_str = ", ".join(f"{tier}={n}" for tier, n in counts.items() if n)
        lines.append(f"{len(rows)} relevant item(s); by evidence tier: {count_str or 'none'}")
        lines.append("")
        lines.extend(format_item_line(row) for row in rank_items(rows)[:12])
        lines.append("")

    lines.append("## Items pointing at missing cells (`new:*`)")
    lines.append("")
    if not by_new_label:
        lines.append("_None found in this pull._")
        lines.append("")
    else:
        for label in sorted(by_new_label):
            rows = by_new_label[label]
            lines.append(f"### new:{label} ({len(rows)} item(s))")
            lines.append("")
            lines.extend(format_item_line(row) for row in rank_items(rows)[:12])
            lines.append("")

    lines.append("## Totals")
    lines.append("")
    lines.extend(
        f"- {key.replace('_', ' ')}: {totals.get(key, 0)}"
        for key in (
            "items_pulled",
            "items_classified",
            "relevant",
            "parse_errors",
            "calls",
            "tokens",
        )
    )
    lines.append("")
    return "\n".join(lines)


def build_cell_counts(cells: list[dict], classified_rows: list[dict]) -> dict:
    by_cell, by_new_label = bucket_by_cell(classified_rows)
    out: dict = {
        "generated": datetime.now(UTC).date().isoformat(),
        "cells": {},
        "new_labels": {label: len(rows) for label, rows in sorted(by_new_label.items())},
    }
    for cell in sorted(cells, key=lambda c: c["id"]):
        rows = by_cell.get(cell["id"], [])
        counts = evidence_tier_counts(rows)
        counts["total_relevant"] = len(rows)
        out["cells"][cell["id"]] = counts
    return out


def cmd_digest(args: argparse.Namespace) -> int:
    date = args.date or datetime.now(UTC).date().isoformat()
    cells = load_coverage_cells()
    classified_rows = load_all_classified(CORPORA)
    totals = compute_totals(CORPORA, classified_rows)
    markdown = render_digest_markdown(
        date=date, cells=cells, classified_rows=classified_rows, totals=totals
    )

    HARVEST_DIR.mkdir(parents=True, exist_ok=True)
    digest_path = HARVEST_DIR / f"feed-digest-{date}.md"
    digest_path.write_text(markdown, encoding="utf-8")
    cell_counts_path = HARVEST_DIR / "feed-cell-counts.json"
    cell_counts_path.write_text(
        json.dumps(build_cell_counts(cells, classified_rows), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {digest_path.relative_to(ROOT)}")
    print(f"wrote {cell_counts_path.relative_to(ROOT)}")
    print(f"totals: {totals}")
    return 0


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)

    pull = sub.add_parser("pull", help="page through one archive corpus into items/<corpus>.jsonl")
    pull.add_argument("--corpus", choices=CORPORA, required=True)
    pull.add_argument("--min-stars", type=int, default=None, help="repos only: server-side filter")
    pull.add_argument("--since", default=None, help="YYYY-MM-DD; local post-filter, best-effort")
    pull.add_argument("--page-size", type=int, default=100)
    pull.add_argument("--delay", type=float, default=0.3, help="seconds between page requests")
    pull.add_argument("--timeout", type=float, default=30.0)
    pull.add_argument("--retries", type=int, default=4)
    pull.add_argument("--time-budget-minutes", type=float, default=15.0)
    pull.set_defaults(func=cmd_pull)

    classify = sub.add_parser("classify", help="send unclassified items to the scoring endpoint")
    classify.add_argument("--corpus", choices=CORPORA, required=True)
    classify.add_argument("--batch", type=int, default=10)
    classify.add_argument("--max-calls", type=int, default=300)
    classify.set_defaults(func=cmd_classify)

    digest = sub.add_parser("digest", help="write the per-cell markdown digest and cell counts")
    digest.add_argument("--date", default=None)
    digest.set_defaults(func=cmd_digest)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
