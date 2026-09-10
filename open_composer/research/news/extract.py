"""Step 13 Track L, L1: LLM extraction-only event tagging.

docs/plan-step-13-recent-high-return-ml-and-llm-tracks-2026-09-09.zh.md
section 4.2. The LLM here does exactly one thing: state, in a fixed enum
plus a -1/0/1 direction, what a headline/summary already says -- never a
forward-looking judgment. That boundary is enforced by the prompt wording
(``EXTRACTION_PROMPT`` includes the plan's required verbatim instruction,
checked in tests) and by never giving the model anything beyond the
headline/summary text itself (no price history, no "what happened next").

Cost/scope controls (all plan section 4.2):

* batches of ``MAX_ARTICLES_PER_CALL`` articles per call;
* scope is the weekly candidate pool -- top-``N`` by ``momentum_252_21``
  within the PIT universe (:func:`compute_weekly_candidate_pools`) --
  extracting the entire market feed would be both wasteful and outside
  budget; the plan's eventual "M0/M1 rank + current holdings" union is not
  substituted here because Track M results do not exist yet (documented
  simplification, not silently done);
* a hard ``TOKEN_BUDGET_PER_WEEK`` token budget, enforced by summing the
  ledger (``reports/research/llm_ledger/step13_news_extraction.jsonl``)
  before every call and stopping -- not silently truncating -- once a call
  would risk exceeding it;
* a cache keyed by ``(article id, prompt_hash)`` so a rerun after a prompt
  change re-pays only for what changed, and a rerun with an unchanged
  prompt re-pays nothing.

Output: ``data/features/news_events/{year}.parquet``, one row per article
extraction, bucketed by the article's own ``created_at`` year (the same
convention ``collector.py`` uses for ``{year}.parquet``). Section 4.3's
daily feature builder (``scripts/build_news_daily_features.py``) reads this.
"""

from __future__ import annotations

import hashlib
import json
import random
import time
from collections.abc import Callable, Iterable, Iterator, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

from open_composer.research.features.universe import exclude_funds_and_etfs, load_universe_panel
from open_composer.research.kernel.loop import universe_as_of_calendar_month
from open_composer.research.llm_backends import LLMBackend
from open_composer.research.news.collector import NEWS_PACKETS_ROOT

ROOT = Path(__file__).resolve().parents[3]
EVENTS_ROOT = ROOT / "data" / "features" / "news_events"
LEDGER_PATH = ROOT / "reports" / "research" / "llm_ledger" / "step13_news_extraction.jsonl"
DAILY_FEATURES_ROOT = ROOT / "data" / "features" / "daily"
UNIVERSE_ROOT = ROOT / "data" / "features" / "universe"

MAX_ARTICLES_PER_CALL = 25
MAX_FIELD_CHARS = 300
TOKEN_BUDGET_PER_WEEK = 30_000_000
DEFAULT_CANDIDATE_POOL_TOP_N = 150
#: 2026-09-10: caps a single flooded mega-cap symbol's article count within
#: one week so it cannot dominate the token budget at the expense of every
#: other symbol's news that week. "Per symbol" not "per article" -- a
#: multi-symbol article can still be kept via any one of its symbols that
#: has not hit this cap yet (see iter_weekly_extraction_batches).
MAX_ARTICLES_PER_SYMBOL_PER_WEEK = 40

#: 2026-09-10: a sustained backend outage costs 0 tokens per failed call, so
#: the token budget alone never stops a run against a dead endpoint -- these
#: bound wall-clock cost instead. Backoff ramps 30s -> 60 -> 120 -> 240 ->
#: 480, capped at 600s (10 min); it reaches that cap by the 6th failure
#: (30 * 2**5 = 960 > 600). DEFAULT_MAX_CONSECUTIVE_FAILURES is the hard
#: stop -- a run gives up (exit non-zero at the CLI) before the backoff
#: schedule's own 6th step in the default configuration (5 < 6), which is
#: intentional: the schedule is a ceiling on how long any single wait can
#: be, not a promise that every step of it is used.
DEFAULT_MAX_CONSECUTIVE_FAILURES = 5
BACKOFF_START_SECONDS = 30.0
BACKOFF_CAP_SECONDS = 600.0

#: Plan section 4.2's exact enum, order preserved for readability only.
EVENT_TYPES: tuple[str, ...] = (
    "earnings_beat",
    "earnings_miss",
    "guidance_raise",
    "guidance_cut",
    "analyst_upgrade",
    "analyst_downgrade",
    "price_target_up",
    "price_target_down",
    "ma_target",
    "ma_acquirer",
    "contract_or_product",
    "regulatory_or_legal_negative",
    "insider_or_buyback",
    "offering_or_dilution",
    "macro_or_sector",
    "other_noise",
)

#: Fixed in code (plan section 4.2: "抽取提示词固化在代码里并算 prompt_hash") so
#: prompt_hash() is a pure function of this module's source, not a runtime
#: file read. Contains the plan's required verbatim instruction.
EXTRACTION_PROMPT = """You are extracting structured facts from financial news headlines and
summaries. This is an EXTRACTION task, not a prediction or judgment task.

Required instruction (verbatim, plan section 4.2): "只抽取标题/摘要本身陈述的内容；不得使用任何
外部知识或对后续走势的判断" -- in English: extract only what the headline/summary itself
states; do not use any outside knowledge or make any judgment about subsequent price movement.

For each article in the input list, return exactly one result object, in the same order as
the input, with its "id" copied through unchanged. Do not skip, merge, split, or reorder
articles.

Fields per result:
- "id": the article id, copied verbatim from the input.
- "event_type": exactly one of: earnings_beat, earnings_miss, guidance_raise, guidance_cut,
  analyst_upgrade, analyst_downgrade, price_target_up, price_target_down, ma_target,
  ma_acquirer, contract_or_product, regulatory_or_legal_negative, insider_or_buyback,
  offering_or_dilution, macro_or_sector, other_noise. Pick "other_noise" if nothing else
  clearly applies -- do not force a fit.
- "stated_direction": -1, 0, or 1 -- the direction the headline/summary itself states or
  implies for the named company (-1 negative, 0 neutral/unclear, 1 positive). This is what
  the text SAYS, not a prediction of what happens next.
- "company_specific": true if the article is about a specific company's own
  results/actions/situation; false if it is primarily macro, sector-wide, or about an
  unrelated topic (politics, general market commentary, etc.) that only mentions the company
  in passing.
- "confidence": a number from 0 to 1 for how clearly the text itself supports this
  event_type/stated_direction classification -- not confidence about what will happen to the
  stock price.

Only use information present in the headline and summary text given to you. Never use
outside knowledge about the company, the event, or how markets reacted historically. Never
state or imply a forecast of future price movement."""


def prompt_hash() -> str:
    return hashlib.sha256(EXTRACTION_PROMPT.encode("utf-8")).hexdigest()


#: The Responses API does not report a training-data knowledge cutoff for
#: the model actually used; guessing a specific date would be exactly the
#: kind of fabricated precision this project's discipline (AGENTS.md) rules
#: out. Every extraction record instead carries this fixed disclosure
#: string plus the real ``model_id`` used, satisfying the "record model_id
#: and knowledge_cutoff" requirement without inventing a date. Full caveat:
#: config/promotion/recent-regime-high-return-gates-v2.json:knowledge_time_disclosure.
KNOWLEDGE_CUTOFF_DISCLOSURE = (
    "not reported by the API for the model actually used; treat as a 2026-vintage "
    "model that may already know 2024-2026 outcomes -- see knowledge_time_disclosure "
    "in config/promotion/recent-regime-high-return-gates-v2.json"
)

_RESULT_ITEM_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "id": {"type": "string"},
        "event_type": {"type": "string", "enum": list(EVENT_TYPES)},
        "stated_direction": {"type": "integer", "enum": [-1, 0, 1]},
        "company_specific": {"type": "boolean"},
        "confidence": {"type": "number"},
    },
    "required": ["id", "event_type", "stated_direction", "company_specific", "confidence"],
    "additionalProperties": False,
}

#: Wrapped in a top-level object (not a bare array) -- the more portable
#: shape for strict JSON-schema structured outputs. Range-checking
#: ``confidence`` to [0, 1] happens in Python (``_validate_and_tag``) rather
#: than via schema ``minimum``/``maximum``, to avoid depending on which
#: strict-mode schema keywords the configured model's endpoint accepts.
EXTRACTION_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"results": {"type": "array", "items": _RESULT_ITEM_SCHEMA}},
    "required": ["results"],
    "additionalProperties": False,
}


def truncate(text: Any, limit: int = MAX_FIELD_CHARS) -> str:
    value = "" if text is None else str(text)
    return value if len(value) <= limit else value[: limit - 1].rstrip() + "…"


def build_batch_input(articles: pd.DataFrame) -> dict[str, Any]:
    return {
        "articles": [
            {
                "id": str(row.id),
                "headline": truncate(row.headline),
                "summary": truncate(row.summary),
            }
            for row in articles.itertuples()
        ]
    }


def _infer_with_usage(backend: LLMBackend, **kwargs: Any) -> tuple[dict[str, Any], dict[str, int]]:
    """Use ``infer_with_usage`` when the backend has it (``OpenAIBackend``,
    2026-09-09); otherwise fall back to plain ``infer`` with zero usage
    (offline/local-test backends, which report no real token spend)."""
    infer_with_usage = getattr(backend, "infer_with_usage", None)
    if callable(infer_with_usage):
        result, usage = infer_with_usage(**kwargs)
        return result, usage
    result = backend.infer(**kwargs)
    return result, {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}


def _validate_and_tag(
    raw: Any, *, article_ids: Sequence[str], model: str, prompt_hash_value: str
) -> list[dict[str, Any]]:
    if not isinstance(raw, dict) or not isinstance(raw.get("results"), list):
        raise ValueError("extraction response missing a 'results' list")
    results: list[Any] = raw["results"]
    if len(results) != len(article_ids):
        raise ValueError(f"expected {len(article_ids)} results, got {len(results)}")
    now = datetime.now(UTC)
    tagged: list[dict[str, Any]] = []
    for expected_id, item in zip(article_ids, results, strict=True):
        if not isinstance(item, dict):
            raise ValueError("extraction result item is not an object")
        got_id = str(item.get("id"))
        if got_id != str(expected_id):
            raise ValueError(f"result id {got_id!r} != expected {expected_id!r} at this position")
        event_type = item.get("event_type")
        if event_type not in EVENT_TYPES:
            raise ValueError(f"unknown event_type {event_type!r}")
        stated_direction = item.get("stated_direction")
        if stated_direction not in (-1, 0, 1):
            raise ValueError(f"stated_direction must be -1/0/1, got {stated_direction!r}")
        confidence = item.get("confidence")
        if not isinstance(confidence, int | float) or not (0.0 <= float(confidence) <= 1.0):
            raise ValueError(f"confidence must be in [0, 1], got {confidence!r}")
        tagged.append(
            {
                "id": str(expected_id),
                "event_type": event_type,
                "stated_direction": int(stated_direction),
                "company_specific": bool(item.get("company_specific")),
                "confidence": float(confidence),
                "model_id": model,
                "knowledge_cutoff": KNOWLEDGE_CUTOFF_DISCLOSURE,
                "prompt_hash": prompt_hash_value,
                "extracted_at": now,
            }
        )
    return tagged


@dataclass(frozen=True)
class BatchResult:
    rows: list[dict[str, Any]]
    usage: dict[str, int]
    article_ids: list[str]
    status: str  # "ok" | "error"
    error: str | None = None


def extract_batch(articles: pd.DataFrame, *, backend: LLMBackend, model: str) -> BatchResult:
    """One LLM call over up to ``MAX_ARTICLES_PER_CALL`` articles. Always
    returns a result (never raises) so the caller can ledger every call,
    including failed ones, per plan section 6 ("账本...包括失败的")."""
    article_ids = [str(v) for v in articles["id"].tolist()]
    phash = prompt_hash()
    try:
        raw, usage = _infer_with_usage(
            backend,
            model=model,
            prompt=EXTRACTION_PROMPT,
            input_payload=build_batch_input(articles),
            output_schema=EXTRACTION_OUTPUT_SCHEMA,
        )
        rows = _validate_and_tag(raw, article_ids=article_ids, model=model, prompt_hash_value=phash)
        return BatchResult(rows=rows, usage=usage, article_ids=article_ids, status="ok")
    except Exception as exc:  # noqa: BLE001 -- every call must ledger, including failures
        return BatchResult(
            rows=[],
            usage={"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
            article_ids=article_ids,
            status="error",
            error=str(exc),
        )


def ledger_row(
    *,
    batch_index: int,
    model: str,
    prompt_hash_value: str,
    usage: dict[str, int],
    article_ids: Sequence[str],
    status: str,
    error: str | None,
) -> dict[str, Any]:
    return {
        "ts": datetime.now(UTC).isoformat(),
        "batch_index": batch_index,
        "model": model,
        "prompt_hash": prompt_hash_value,
        "input_tokens": int(usage.get("input_tokens", 0)),
        "output_tokens": int(usage.get("output_tokens", 0)),
        "total_tokens": int(usage.get("total_tokens", 0)),
        "article_ids": list(article_ids),
        "status": status,
        "error": error,
    }


def append_ledger(rows: Iterable[dict[str, Any]], *, ledger_path: Path = LEDGER_PATH) -> None:
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    with ledger_path.open("a", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, default=str) + "\n")


def tokens_used_so_far(ledger_path: Path = LEDGER_PATH) -> int:
    """Sum of every already-ledgered call's input+output tokens. The ledger
    file is scoped to this one push (``step13_news_extraction.jsonl``, no
    date partitioning), so this sum *is* "this week's" spend by
    construction -- no separate date filter needed."""
    if not ledger_path.exists():
        return 0
    total = 0
    with ledger_path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            total += int(row.get("input_tokens", 0)) + int(row.get("output_tokens", 0))
    return total


def events_path(year: int, *, root: Path = EVENTS_ROOT) -> Path:
    return root / f"{year}.parquet"


def load_cached_keys(years: Iterable[int], *, root: Path = EVENTS_ROOT) -> set[tuple[str, str]]:
    """Every ``(article id, prompt_hash)`` already extracted and persisted,
    across the given years -- the cache key plan section 4.2 specifies."""
    keys: set[tuple[str, str]] = set()
    for year in years:
        path = events_path(year, root=root)
        if not path.exists():
            continue
        frame = pd.read_parquet(path, columns=["id", "prompt_hash"])
        keys.update(zip(frame["id"].astype(str), frame["prompt_hash"].astype(str), strict=True))
    return keys


def append_events(
    rows: list[dict[str, Any]], *, source_years: dict[str, int], root: Path = EVENTS_ROOT
) -> None:
    """Persist extraction result rows. ``source_years`` maps article id ->
    the calendar year of its own ``created_at`` (the collector's own
    per-year bucketing convention), so a result lands in the same
    ``{year}.parquet`` its source article did. Deduplicates by
    ``(id, prompt_hash)``, keeping the newest row, so a rerun that only
    partially overlaps a prior one never double-counts."""
    if not rows:
        return
    root.mkdir(parents=True, exist_ok=True)
    by_year: dict[int, list[dict[str, Any]]] = {}
    for row in rows:
        year = source_years[row["id"]]
        by_year.setdefault(year, []).append(row)
    for year, year_rows in by_year.items():
        path = events_path(year, root=root)
        new_frame = pd.DataFrame(year_rows)
        if path.exists():
            existing = pd.read_parquet(path)
            combined = pd.concat([existing, new_frame], ignore_index=True)
        else:
            combined = new_frame
        combined = combined.sort_values(["id"]).drop_duplicates(
            subset=["id", "prompt_hash"], keep="last"
        )
        combined.to_parquet(path, index=False)


def _connect(memory_limit: str = "1GB") -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    con.execute(f"SET memory_limit='{memory_limit}'")
    con.execute("SET threads=2")
    con.execute("SET preserve_insertion_order=false")
    con.execute("SET enable_progress_bar=false")
    return con


def weekly_fridays(start: pd.Timestamp, end: pd.Timestamp) -> pd.DatetimeIndex:
    """Every calendar Friday in ``[start, end]``. This only bounds which
    articles are worth paying to extract (a cost-control scope, not a
    trading decision), so a plain calendar Friday is precise enough --
    unlike a real rebalance schedule, it does not need the exchange
    trading calendar's holiday adjustments."""
    return pd.date_range(pd.Timestamp(start), pd.Timestamp(end), freq="W-FRI")


def _load_eligible_universe(universe_root: Path) -> pd.DataFrame:
    """``month_end, symbol`` (plus whatever else ``load_universe_panel``
    returns) for every name that is not a probable fund/ETF -- reuses
    ``universe.py``/``loop.py``'s own PIT cohort machinery (see
    ``universe_as_of_calendar_month``'s docstring for why "most recent
    ``month_end`` <= date" must group by calendar month, not compare raw
    ``month_end`` values directly) rather than a second implementation of
    the same lookup. Loads every available year (small, ~10k rows/year) so
    an early-in-year Friday can still resolve to the prior year's last
    cohort -- no separate "which years do I need" computation required.
    """
    try:
        universe = load_universe_panel(universe_root)
    except FileNotFoundError:
        return pd.DataFrame(columns=["month_end", "symbol"])
    meta_path = universe_root / "_asset_metadata.parquet"
    if not meta_path.exists():
        return universe
    meta = pd.read_parquet(meta_path, columns=["symbol", "is_probable_fund_or_etf"])
    return exclude_funds_and_etfs(universe, meta)


def compute_weekly_candidate_pools(
    start: pd.Timestamp,
    end: pd.Timestamp,
    *,
    top_n: int = DEFAULT_CANDIDATE_POOL_TOP_N,
    daily_root: Path = DAILY_FEATURES_ROOT,
    universe_root: Path = UNIVERSE_ROOT,
    memory_limit: str = "1GB",
) -> dict[pd.Timestamp, set[str]]:
    """``{Friday -> top-N symbols by momentum_252_21}`` among that Friday's
    PIT-eligible universe (``universe_as_of_calendar_month``: most recent
    calendar-month cohort on or before the Friday, ex-fund/ETF). Plan
    section 4.2: "先用 momentum_252_21 前 150 代替" the eventual M0/M1-rank +
    current-holdings union -- Track M results do not exist yet, so this
    simplification is used and disclosed here, not silently assumed away.
    """
    fridays = list(weekly_fridays(start, end))
    if not fridays:
        return {}
    universe = _load_eligible_universe(universe_root)
    if universe.empty:
        return {friday: set() for friday in fridays}

    years = sorted({*range(pd.Timestamp(start).year, pd.Timestamp(end).year + 1)})
    daily_files = [
        str(daily_root / f"{year}.parquet")
        for year in years
        if (daily_root / f"{year}.parquet").exists()
    ]
    if not daily_files:
        return {friday: set() for friday in fridays}

    con = _connect(memory_limit)
    try:
        con.register("_fridays", pd.DataFrame({"trade_date": fridays}))
        momentum = (
            con.execute(
                f"""
            SELECT d.symbol AS symbol, d.trade_date AS trade_date,
                   d.momentum_252_21 AS momentum_252_21
            FROM read_parquet({daily_files!r}, union_by_name=true) d
            JOIN _fridays f ON f.trade_date = d.trade_date
            WHERE d.momentum_252_21 IS NOT NULL
            """
            )
            .fetch_arrow_table()
            .to_pandas()
        )
    finally:
        con.close()
    momentum["trade_date"] = pd.to_datetime(momentum["trade_date"])

    pools: dict[pd.Timestamp, set[str]] = {}
    for friday in fridays:
        eligible_symbols = universe_as_of_calendar_month(universe, friday)
        if not eligible_symbols:
            pools[friday] = set()
            continue
        week_rows = momentum.loc[
            (momentum["trade_date"] == friday) & (momentum["symbol"].isin(eligible_symbols))
        ]
        top = week_rows.nlargest(top_n, "momentum_252_21")
        pools[friday] = set(top["symbol"])
    return pools


def candidate_pool_for_date(day: pd.Timestamp, pools: dict[pd.Timestamp, set[str]]) -> set[str]:
    """The candidate pool in force on ``day``: the most recent Friday's
    pool on or before ``day`` (PIT -- a day's scope never depends on a
    later week's pool)."""
    eligible = [friday for friday in pools if friday <= day]
    if not eligible:
        return set()
    return pools[max(eligible)]


def select_articles_for_extraction(
    articles: pd.DataFrame,
    *,
    pools: dict[pd.Timestamp, set[str]],
    cached_keys: set[tuple[str, str]],
    prompt_hash_value: str,
) -> pd.DataFrame:
    """Filter ``articles`` (collector packet rows) down to the ones actually
    worth an LLM call: symbols intersect that article's week's candidate
    pool, and not already cached under the current prompt.

    Fully vectorized (``merge_asof`` + ``explode`` + ``isin``) -- 2026-09-10
    rewrite after a per-row Python-loop version (``.iloc`` plus a linear
    pool scan per row) proved far too slow on the real ~685k-article
    archive: still hadn't finished after several minutes in the first real
    bulk run. This version does the same filtering as one small number of
    vectorized pandas/numpy operations instead of 685k individual ones.
    """
    if articles.empty or not pools:
        return articles.iloc[0:0]
    all_pool_symbols: set[str] = set().union(*pools.values())
    if not all_pool_symbols:
        return articles.iloc[0:0]

    working = articles.reset_index(drop=True).copy()
    working["_row_pos"] = range(len(working))
    working["_date"] = pd.to_datetime(working["created_at"]).dt.tz_localize(None).dt.normalize()

    fridays = pd.DataFrame({"_friday": sorted(pools)})
    merged = pd.merge_asof(
        working.sort_values("_date"),
        fridays.sort_values("_friday"),
        left_on="_date",
        right_on="_friday",
        direction="backward",  # most recent Friday <= this article's date (PIT)
    )
    merged = merged.dropna(subset=["_friday"])  # before the first Friday -> no pool yet
    if merged.empty:
        return articles.iloc[0:0]

    # Explode (row, symbol) pairs, then immediately drop anything that is
    # not in *any* week's pool -- shrinks the join before it happens rather
    # than after, since most mentioned symbols are never a top-150 name.
    exploded = merged[["_row_pos", "_friday", "symbols"]].explode("symbols")
    exploded = exploded.dropna(subset=["symbols"])
    exploded = exploded.loc[exploded["symbols"].isin(all_pool_symbols)]
    if exploded.empty:
        return articles.iloc[0:0]

    pool_pairs = pd.DataFrame(
        [(friday, symbol) for friday, symbols in pools.items() for symbol in symbols],
        columns=["_friday", "symbols"],
    )
    matched_positions = set(
        exploded.merge(pool_pairs, on=["_friday", "symbols"], how="inner")["_row_pos"]
    )
    if not matched_positions:
        return articles.iloc[0:0]

    cached_ids_for_prompt = {
        article_id for article_id, phash in cached_keys if phash == prompt_hash_value
    }
    matched = working.loc[sorted(matched_positions)]
    keep = matched.loc[~matched["id"].astype(str).isin(cached_ids_for_prompt), "_row_pos"]
    return articles.iloc[sorted(keep.tolist())]


def _weekly_matched_articles(
    con: duckdb.DuckDBPyConnection,
    *,
    year_files: list[str],
    week_start: pd.Timestamp,
    week_end_exclusive: pd.Timestamp,
    pool_symbols: Sequence[str],
    max_per_symbol: int,
) -> pd.DataFrame:
    """One week's worth of in-scope articles, read directly from the
    consolidated ``data/features/news_packets/{year}.parquet`` archives via
    DuckDB (columnar + predicate pushdown on ``created_at`` -- never reads
    more than this one week's rows into memory). An article is kept if,
    for at least one of its symbols that is also in ``pool_symbols``, it
    ranks among that symbol's ``max_per_symbol`` most recent articles this
    week (caps a single flooded symbol without dropping a multi-symbol
    article just because one of its *other* symbols is flooded).
    """
    symbol_list_sql = "(" + ", ".join(repr(s) for s in pool_symbols) + ")"
    query = f"""
        WITH windowed AS (
            SELECT id, created_at, headline, summary, symbols
            FROM read_parquet({year_files!r}, union_by_name=true)
            WHERE created_at >= ? AND created_at < ?
        ),
        exploded AS (
            SELECT id, created_at, headline, summary, UNNEST(symbols) AS symbol
            FROM windowed
        ),
        ranked AS (
            SELECT *, ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY created_at DESC) AS rn
            FROM exploded
            WHERE symbol IN {symbol_list_sql}
        )
        SELECT id, ANY_VALUE(created_at) AS created_at, ANY_VALUE(headline) AS headline,
               ANY_VALUE(summary) AS summary
        FROM ranked
        WHERE rn <= ?
        GROUP BY id
        ORDER BY created_at
    """
    frame = (
        con.execute(query, [week_start, week_end_exclusive, max_per_symbol])
        .fetch_arrow_table()
        .to_pandas()
    )
    frame["id"] = frame["id"].astype(str)
    return frame


def iter_weekly_extraction_batches(
    pools: dict[pd.Timestamp, set[str]],
    *,
    cached_keys: set[tuple[str, str]],
    prompt_hash_value: str,
    packets_root: Path = NEWS_PACKETS_ROOT,
    max_articles_per_symbol_per_week: int = MAX_ARTICLES_PER_SYMBOL_PER_WEEK,
    batch_size: int = MAX_ARTICLES_PER_CALL,
    memory_limit: str = "1GB",
) -> Iterator[pd.DataFrame]:
    """Streams batches of up to ``batch_size`` in-scope, not-yet-cached
    articles, one week at a time.

    2026-09-10 rewrite: the prior "load every raw article into one pandas
    frame, then filter" path was OOM-killed at the run_capped 1.8GB cap on
    the real ~685k-article archive (``loaded 684876 raw articles from
    _daily/`` was the last line before the kernel memcg kill). This version
    reads only each week's rows from the consolidated
    ``data/features/news_packets/{year}.parquet`` files via DuckDB
    (predicate pushdown on ``created_at``), so peak memory is bounded by
    one week's matched rows, not the whole archive, regardless of how many
    years are requested.
    """
    year_files = sorted(str(p) for p in packets_root.glob("*.parquet") if p.stem.isdigit())
    if not year_files:
        return
    cached_ids_for_prompt = {
        article_id for article_id, phash in cached_keys if phash == prompt_hash_value
    }
    sorted_fridays = sorted(pools)
    con = _connect(memory_limit)
    try:
        for i, friday in enumerate(sorted_fridays):
            pool = pools[friday]
            if not pool:
                continue
            week_end_exclusive = (
                sorted_fridays[i + 1]
                if i + 1 < len(sorted_fridays)
                else friday + pd.Timedelta(days=3650)
            )
            matched = _weekly_matched_articles(
                con,
                year_files=year_files,
                week_start=friday,
                week_end_exclusive=week_end_exclusive,
                pool_symbols=sorted(pool),
                max_per_symbol=max_articles_per_symbol_per_week,
            )
            if matched.empty:
                continue
            matched = matched.loc[~matched["id"].isin(cached_ids_for_prompt)]
            if matched.empty:
                continue
            for start_idx in range(0, len(matched), batch_size):
                yield matched.iloc[start_idx : start_idx + batch_size]
    finally:
        con.close()


def backoff_seconds(consecutive_failures: int, *, rng: random.Random | None = None) -> float:
    """Equal-jitter exponential backoff for the delay before trying the
    *next* batch after a failure (a failed batch is not retried in place --
    see :func:`run_extraction_batches`): ``consecutive_failures=1`` ->
    around 30s, doubling each additional failure, capped at 600s (10 min).
    Equal jitter (``base/2 + uniform(0, base/2)``) keeps the expected delay
    close to the nominal schedule while avoiding perfectly synchronized
    retries.
    """
    generator = rng or random
    base = min(BACKOFF_START_SECONDS * (2 ** max(consecutive_failures - 1, 0)), BACKOFF_CAP_SECONDS)
    return base / 2 + generator.uniform(0, base / 2)


def run_extraction_batches(
    batches: Iterable[pd.DataFrame],
    *,
    backend: LLMBackend,
    model: str,
    budget: int,
    max_consecutive_failures: int = DEFAULT_MAX_CONSECUTIVE_FAILURES,
    sleep: Callable[[float], None] | None = None,
    rng: random.Random | None = None,
    ledger_path: Path = LEDGER_PATH,
    events_root: Path = EVENTS_ROOT,
) -> Iterator[dict[str, Any]]:
    """Runs ``batches`` against ``backend``, ledgering and checkpointing
    every call, yielding one small progress dict per batch attempted plus a
    final summary dict (``{"final": True, ...}``) when the run stops.

    Every batch is ledgered (and, if successful, persisted to the events
    store) *before* it is yielded, so a consumer that stops iterating, or
    crashes, never loses the checkpoint for a batch it already saw -- the
    next call with a freshly-loaded ``cached_keys`` (see
    :func:`load_cached_keys`) naturally resumes from the first
    not-yet-cached article, never repeating already-successful work and
    never restarting from scratch. This is the same mechanism whether the
    stop was a clean end of input, the token budget, or the failure circuit
    breaker below.

    Stops (``stopped_reason``) on whichever comes first: the token budget
    (``"budget_exhausted"``), ``max_consecutive_failures`` failures in a row
    with no intervening success (``"consecutive_failures"`` -- a sustained
    backend outage costs 0 tokens per call, so the budget alone would never
    stop it), or the input being exhausted (``"exhausted_input"``).
    ``sleep``/``rng`` are injectable so tests can run the failure path
    without real delays.
    """
    sleep_fn = sleep if sleep is not None else time.sleep
    phash = prompt_hash()
    batches_run = 0
    articles_processed = 0
    consecutive_failures = 0

    def _summary(stopped_reason: str) -> dict[str, Any]:
        return {
            "final": True,
            "batches_run": batches_run,
            "articles_processed": articles_processed,
            "tokens_used_so_far": tokens_used_so_far(ledger_path=ledger_path),
            "budget": budget,
            "stopped_reason": stopped_reason,
        }

    for batch in batches:
        used = tokens_used_so_far(ledger_path=ledger_path)
        if used >= budget:
            yield _summary("budget_exhausted")
            return
        result = extract_batch(batch, backend=backend, model=model)
        row = ledger_row(
            batch_index=batches_run,
            model=model,
            prompt_hash_value=phash,
            usage=result.usage,
            article_ids=result.article_ids,
            status=result.status,
            error=result.error,
        )
        append_ledger([row], ledger_path=ledger_path)
        if result.status == "ok":
            consecutive_failures = 0
            source_years = {
                str(art.id): pd.Timestamp(art.created_at).year for art in batch.itertuples()
            }
            append_events(result.rows, source_years=source_years, root=events_root)
            articles_processed += len(result.rows)
        else:
            consecutive_failures += 1
        batches_run += 1
        yield {
            "final": False,
            "batch_index": batches_run,
            "status": result.status,
            "error": result.error,
            "article_count": len(batch),
            "input_tokens": row["input_tokens"],
            "output_tokens": row["output_tokens"],
            "consecutive_failures": consecutive_failures,
        }
        if consecutive_failures >= max_consecutive_failures:
            yield _summary("consecutive_failures")
            return
        if result.status != "ok":
            sleep_fn(backoff_seconds(consecutive_failures, rng=rng))
    yield _summary("exhausted_input")
