"""Step 13 Track L, L1: CLI for open_composer.research.news.extract.

docs/plan-step-13-recent-high-return-ml-and-llm-tracks-2026-09-09.zh.md
section 4.2.

Usage::

    # 5-article smoke test against the real OpenAI backend (real, small,
    # cheap call -- writes ledger/cache normally, just at small scale):
    uv run python scripts/extract_news_events_llm.py --smoke-n 5

    # Bulk run, scoped to the weekly candidate pool, budget-gated,
    # resumable (cache-checkpointed per batch -- safe to kill and rerun):
    uv run python scripts/extract_news_events_llm.py --start 2024-01-01 --end 2024-12-31

Credentials come from ``.env`` via ``load_dotenv()`` below, same pattern as
``scripts/collect_alpaca_news_packets.py`` -- this script loads it once at
startup and never reads or prints its contents.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402
from dotenv import load_dotenv  # noqa: E402

from open_composer.config import default_openai_model  # noqa: E402
from open_composer.research.llm_backends import get_backend  # noqa: E402
from open_composer.research.news import extract as ex  # noqa: E402
from open_composer.research.news.collector import DAILY_ROOT  # noqa: E402


def _parse_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def _load_daily_files(start: date, end: date) -> pd.DataFrame:
    """Read already-collected ``_daily/{day}.parquet`` files directly (not
    the consolidated ``{year}.parquet``, which only reflects whatever the
    collector had finished as of its last full-range run). Tolerant of a
    file the collector is mid-writing (skips it with a warning instead of
    crashing the whole extraction run)."""
    frames = []
    day = start
    while day <= end:
        path = DAILY_ROOT / f"{day.isoformat()}.parquet"
        if path.exists():
            try:
                frames.append(pd.read_parquet(path))
            except Exception as exc:  # noqa: BLE001 -- tolerate a file mid-write
                print(f"  skip {path.name}: {exc}", flush=True)
        day = day + pd.Timedelta(days=1)
    if not frames:
        return pd.DataFrame(columns=["id", "created_at", "symbols", "headline", "summary"])
    return pd.concat(frames, ignore_index=True)


def _run_batches(
    articles: pd.DataFrame, *, backend_name: str, model: str | None, budget: int
) -> dict[str, object]:
    backend = get_backend(backend_name)
    model = model or default_openai_model()
    phash = ex.prompt_hash()
    batches_run = 0
    articles_processed = 0
    stopped_reason = "exhausted_input"
    for start_idx in range(0, len(articles), ex.MAX_ARTICLES_PER_CALL):
        used = ex.tokens_used_so_far()
        if used >= budget:
            stopped_reason = "budget_exhausted"
            print(f"  STOP: {used} tokens already used, budget is {budget}", flush=True)
            break
        batch = articles.iloc[start_idx : start_idx + ex.MAX_ARTICLES_PER_CALL]
        result = ex.extract_batch(batch, backend=backend, model=model)
        row = ex.ledger_row(
            batch_index=batches_run,
            model=model,
            prompt_hash_value=phash,
            usage=result.usage,
            article_ids=result.article_ids,
            status=result.status,
            error=result.error,
        )
        ex.append_ledger([row])
        if result.status == "ok":
            source_years = {
                str(art.id): pd.Timestamp(art.created_at).year for art in batch.itertuples()
            }
            ex.append_events(result.rows, source_years=source_years)
            articles_processed += len(result.rows)
        else:
            print(f"  batch {batches_run} FAILED: {result.error}", flush=True)
        batches_run += 1
        running_total = row["input_tokens"] + row["output_tokens"] + used
        print(
            f"  batch {batches_run}: {result.status}, {len(batch)} articles, "
            f"{row['input_tokens']}+{row['output_tokens']} tokens, "
            f"running total {running_total}",
            flush=True,
        )
    return {
        "batches_run": batches_run,
        "articles_processed": articles_processed,
        "tokens_used_so_far": ex.tokens_used_so_far(),
        "budget": budget,
        "stopped_reason": stopped_reason,
    }


def _smoke(n: int, *, backend_name: str, model: str | None) -> int:
    print(f"[{time_now()}] smoke test: extracting {n} real articles ...", flush=True)
    # Scan the earliest collected days for N articles with a non-empty
    # symbols list (a meaningful smoke test exercises company_specific=True
    # at least once) -- falls back to whatever exists if not enough found.
    day_paths = sorted(DAILY_ROOT.glob("*.parquet"))
    if not day_paths:
        print("no _daily/*.parquet files found -- run the collector first", flush=True)
        return 1
    found: list[pd.DataFrame] = []
    found_rows = 0
    for path in day_paths:
        frame = pd.read_parquet(path)
        with_symbols = frame.loc[frame["symbols"].apply(lambda s: len(s) > 0)]
        if not with_symbols.empty:
            found.append(with_symbols)
            found_rows += len(with_symbols)
        if found_rows >= n:
            break
    picked = pd.concat(found, ignore_index=True) if found else pd.read_parquet(day_paths[0]).head(n)
    picked = picked.head(n)
    print(f"picked {len(picked)} articles:", flush=True)
    print(
        picked[["id", "created_at", "symbols", "headline"]].to_string(index=False),
        flush=True,
    )
    summary = _run_batches(
        picked, backend_name=backend_name, model=model, budget=ex.TOKEN_BUDGET_PER_WEEK
    )
    print(f"\nsmoke summary: {summary}", flush=True)
    if summary["articles_processed"] > 0:
        year = int(pd.Timestamp(picked.iloc[0]["created_at"]).year)
        result_frame = pd.read_parquet(ex.events_path(year))
        result_frame = result_frame.loc[result_frame["id"].isin(picked["id"].astype(str))]
        print("\nextraction results:", flush=True)
        print(result_frame.to_string(index=False), flush=True)
    return 0


def time_now() -> str:
    import time

    return time.strftime("%H:%M:%S")


def _bulk(args: argparse.Namespace) -> int:
    start, end = args.start, args.end
    latest_daily = sorted(DAILY_ROOT.glob("*.parquet"))
    latest_date = date.fromisoformat(latest_daily[-1].stem) if latest_daily else None
    if latest_date is not None and end > latest_date:
        print(f"capping --end {end} to latest collected day {latest_date}", flush=True)
        end = latest_date
    print(f"[{time_now()}] bulk extraction {start} .. {end}, top_n={args.top_n} ...", flush=True)

    pools = ex.compute_weekly_candidate_pools(
        pd.Timestamp(start), pd.Timestamp(end), top_n=args.top_n, memory_limit="1GB"
    )
    print(f"computed {len(pools)} weekly candidate pools", flush=True)

    articles = _load_daily_files(start, end)
    print(f"loaded {len(articles)} raw articles from _daily/", flush=True)
    if articles.empty:
        print("nothing to extract", flush=True)
        return 0

    years = sorted({pd.Timestamp(v).year for v in articles["created_at"]})
    cached_keys = ex.load_cached_keys(years)
    print(
        f"{len(cached_keys)} (id, prompt_hash) pairs already cached for years {years}", flush=True
    )

    phash = ex.prompt_hash()
    selected = ex.select_articles_for_extraction(
        articles, pools=pools, cached_keys=cached_keys, prompt_hash_value=phash
    )
    selected = selected.sort_values("created_at")
    print(f"{len(selected)} articles in scope (candidate pool intersect, not cached)", flush=True)
    if selected.empty:
        print("nothing new to extract (already cached or out of scope)", flush=True)
        return 0

    summary = _run_batches(
        selected, backend_name=args.backend, model=args.model, budget=args.budget_tokens
    )
    print(f"\nbulk summary: {summary}", flush=True)
    return 0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--smoke-n",
        type=int,
        default=None,
        help="real extraction smoke test: one run of this many articles "
        "(first N with non-empty symbols from already-collected data), no "
        "candidate-pool/cache scope filtering -- prints the parsed result",
    )
    parser.add_argument("--start", type=_parse_date, default=None)
    parser.add_argument("--end", type=_parse_date, default=None)
    parser.add_argument("--top-n", type=int, default=ex.DEFAULT_CANDIDATE_POOL_TOP_N)
    parser.add_argument("--budget-tokens", type=int, default=ex.TOKEN_BUDGET_PER_WEEK)
    parser.add_argument("--model", default=None)
    parser.add_argument("--backend", default="openai", choices=["openai", "local_test_stub"])
    return parser.parse_args()


def main() -> int:
    load_dotenv(dotenv_path=ROOT / ".env")
    args = _parse_args()
    if args.smoke_n is not None:
        return _smoke(args.smoke_n, backend_name=args.backend, model=args.model)
    if args.start is None or args.end is None:
        print("bulk mode requires --start and --end (or use --smoke-n)", flush=True)
        return 2
    return _bulk(args)


if __name__ == "__main__":
    raise SystemExit(main())
