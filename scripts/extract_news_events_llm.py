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
import time
from collections.abc import Iterable
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


def _chunked(frame: pd.DataFrame, size: int) -> list[pd.DataFrame]:
    return [frame.iloc[i : i + size] for i in range(0, len(frame), size)]


def _run_batches(
    batches: Iterable[pd.DataFrame],
    *,
    backend_name: str,
    model: str | None,
    budget: int,
    max_consecutive_failures: int = ex.DEFAULT_MAX_CONSECUTIVE_FAILURES,
) -> dict[str, object]:
    """Thin CLI wrapper: all the retry/backoff/circuit-breaker/checkpoint
    logic lives in the tested ``ex.run_extraction_batches`` generator (a
    script file is not easily unit-testable, so the real logic does not
    live here -- see ``tests/test_news_extract.py``); this just prints each
    yielded progress event and returns the final summary dict."""
    backend = get_backend(backend_name)
    model = model or default_openai_model()
    summary: dict[str, object] | None = None
    for event in ex.run_extraction_batches(
        batches,
        backend=backend,
        model=model,
        budget=budget,
        max_consecutive_failures=max_consecutive_failures,
    ):
        if event["final"]:
            summary = event
            break
        suffix = (
            ""
            if event["status"] == "ok"
            else f" -- FAILED ({event['consecutive_failures']} in a row): {event['error']}"
        )
        print(
            f"  batch {event['batch_index']}: {event['status']}, "
            f"{event['article_count']} articles, "
            f"{event['input_tokens']}+{event['output_tokens']} tokens{suffix}",
            flush=True,
        )
    assert summary is not None  # run_extraction_batches always yields a final event
    if summary["stopped_reason"] in ("budget_exhausted", "consecutive_failures"):
        print(f"  STOP: {summary['stopped_reason']}", flush=True)
    return summary


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
        _chunked(picked, ex.MAX_ARTICLES_PER_CALL),
        backend_name=backend_name,
        model=model,
        budget=ex.TOKEN_BUDGET_PER_WEEK,
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
    return time.strftime("%H:%M:%S")


def _bulk(args: argparse.Namespace) -> int:
    start, end = args.start, args.end
    latest_daily = sorted(DAILY_ROOT.glob("*.parquet"))
    latest_date = date.fromisoformat(latest_daily[-1].stem) if latest_daily else None
    if latest_date is not None and end > latest_date:
        print(f"capping --end {end} to latest collected day {latest_date}", flush=True)
        end = latest_date
    print(
        f"[{time_now()}] bulk extraction {start} .. {end}, top_n={args.top_n}, "
        f"budget_tokens={args.budget_tokens}, backend={args.backend}, "
        f"model={args.model or default_openai_model()}, already_used={ex.tokens_used_so_far()} ...",
        flush=True,
    )

    pools = ex.compute_weekly_candidate_pools(
        pd.Timestamp(start), pd.Timestamp(end), top_n=args.top_n, memory_limit="1GB"
    )
    print(f"computed {len(pools)} weekly candidate pools", flush=True)

    # Cache keys from *every* year we have ever written extraction output
    # for, not just the requested range: a small fraction of articles
    # collected in a given day carry an old created_at (Alpaca's date-
    # window query matches updated_at too, surfacing corrected/republished
    # old articles -- verified 2026-09-10, not a parsing bug), so
    # data/features/news_events/{year}.parquet can have entries for years
    # outside [start.year, end.year]. Scoping the cache lookup that
    # narrowly would just mean occasionally re-paying for an old article,
    # not a correctness bug, but this is cheap and avoids the waste.
    existing_years = (
        sorted(int(p.stem) for p in ex.EVENTS_ROOT.glob("*.parquet") if p.stem.isdigit())
        if ex.EVENTS_ROOT.exists()
        else []
    )
    cached_keys = ex.load_cached_keys(existing_years)
    print(
        f"{len(cached_keys)} (id, prompt_hash) pairs already cached across years {existing_years}",
        flush=True,
    )

    phash = ex.prompt_hash()
    # Streams batches week by week straight from the consolidated
    # data/features/news_packets/{year}.parquet archives via DuckDB --
    # never materializes the full multi-year article set in pandas (the
    # prior load-everything path was OOM-killed at the run_capped 1.8GB cap
    # on the real ~685k-article archive).
    batches = ex.iter_weekly_extraction_batches(
        pools, cached_keys=cached_keys, prompt_hash_value=phash, memory_limit="1GB"
    )
    summary = _run_batches(
        batches,
        backend_name=args.backend,
        model=args.model,
        budget=args.budget_tokens,
        max_consecutive_failures=args.max_consecutive_failures,
    )
    print(f"\nbulk summary: {summary}", flush=True)
    if summary["stopped_reason"] == "consecutive_failures":
        print(
            f"FATAL: {args.max_consecutive_failures} consecutive batch failures -- "
            "stopping rather than burning through the rest of the backlog against a "
            "dead endpoint. Rerun the exact same command once the backend recovers: "
            "the cache/ledger checkpoints mean nothing already-succeeded repeats.",
            flush=True,
        )
        return 1
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
    parser.add_argument(
        "--max-consecutive-failures",
        type=int,
        default=ex.DEFAULT_MAX_CONSECUTIVE_FAILURES,
        help="stop (exit non-zero) after this many batch failures in a row -- "
        "guards against a dead/rate-limited endpoint burning through the whole "
        "backlog for zero tokens spent (failed calls cost 0 tokens, so the "
        "budget gate alone never stops that case)",
    )
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
