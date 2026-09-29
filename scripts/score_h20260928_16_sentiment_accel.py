"""T-20260928-16 DeepSeek pilot: 8-K + news polarity/magnitude scoring.

Card: reports/research/control/autonomous-queue.md T-20260928-16;
reports/research/iterations/h20260928_16_8k_sentiment_accel/{direction-review,
candidate-manifest}.json.

Scores two item kinds via the owner-configured DeepSeek endpoint (through the
existing OpenAI-compatible client in scripts/score_earnings_text.py -- same
credentials file, same rate-limit/checkpoint/retry machinery, only the prompt
and output schema differ):

* 8-K text: 2026 Q2 filings for the 50 preregistered tickers
  (data/features/earnings_events/2026.parquet, text from
  data/raw/earnings_text/<cik>/<accession>.txt).
* News: 2026 Q2 Alpaca/Benzinga items for the same 50 tickers
  (data/features/news_packets/2026.parquet).

Each item gets {polarity in [-1, 1], magnitude in [0, 1]} plus a `visible_at`
timestamp = the item's own filing/news timestamp + SCORING_LATENCY_MINUTES
(the assumed time it takes to score), per the brief's point-in-time rule.

Every response is cached on disk under
data/research/llm_cache/h20260928_16_8k_sentiment_accel/<item_hash>.json
keyed by a sha256 of (item kind, id, neutralised text, prompt version) so a
rerun never re-queries an already-scored item. Output rows are written to
data/features/h20260928_16_sentiment_accel_scores/items.parquet, checkpointed
every CHECKPOINT_EVERY items.

Usage
-----
Dry run (no network calls, prints candidate counts and 2 sample prompts)::

    uv run python scripts/score_h20260928_16_sentiment_accel.py --dry-run

Score everything (rate-limit-aware; safe to rerun, resumes from the parquet +
disk cache)::

    ./scripts/run_capped.sh --mem 1.2G -- uv run python \\
        scripts/score_h20260928_16_sentiment_accel.py
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import logging
import sys
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

_set = importlib.import_module("scripts.score_earnings_text")

EVENTS_PATH = ROOT / "data/features/earnings_events/2026.parquet"
NEWS_PATH = ROOT / "data/features/news_packets/2026.parquet"
OUT_DIR = ROOT / "data/features/h20260928_16_sentiment_accel_scores"
OUT_PATH = OUT_DIR / "items.parquet"
CACHE_DIR = ROOT / "data/research/llm_cache/h20260928_16_8k_sentiment_accel"
NEXT_TRY_PATH = OUT_DIR / "next_try_at.json"
LOG_PATH = ROOT / "logs/score_h20260928_16_sentiment_accel.log"

QUARTER_START = pd.Timestamp("2026-04-01", tz="UTC")
QUARTER_END = pd.Timestamp("2026-07-01", tz="UTC")  # exclusive

# Preregistered 50-ticker sample (candidate-manifest.json SENT01
# parameters.universe_tickers -- fixed seed random.Random(20260928).sample of
# the 1343 tickers with an 'ok'-fetch-status 8-K in 2026 Q2). Copied verbatim,
# not regenerated here, so a code change to the sampling routine can never
# silently change the preregistered universe after the fact.
UNIVERSE_TICKERS = [
    "AAON",
    "AAPL",
    "ADBE",
    "ALIT",
    "ALT",
    "AMC",
    "ARCB",
    "ATR",
    "BTU",
    "BYD",
    "CADL",
    "CZR",
    "DELL",
    "DLTR",
    "DVLT",
    "EHC",
    "ERIE",
    "EVRG",
    "FANG",
    "FLNA",
    "FNB",
    "FRMI",
    "FRSH",
    "GENB",
    "GPCR",
    "HAL",
    "HONA",
    "HWM",
    "L",
    "LIVN",
    "LOAR",
    "LSCC",
    "NAVN",
    "OGN",
    "PCAR",
    "PODD",
    "QS",
    "RRC",
    "RXT",
    "SIRI",
    "STLD",
    "SUI",
    "TER",
    "TOL",
    "TXG",
    "UAA",
    "WAB",
    "WAL",
    "WEX",
    "YUM",
]
assert len(UNIVERSE_TICKERS) == 50
UNIVERSE_SET = set(UNIVERSE_TICKERS)

SCORING_LATENCY_MINUTES = 15
CHECKPOINT_EVERY = 50

LOG = logging.getLogger("score_h20260928_16")

PROMPT_VERSION = "h20260928_16_v1"
SYSTEM_PROMPT = (
    "You are a financial-text sentiment scorer. Read only the given text "
    "(a company name/ticker/date-neutralised SEC 8-K excerpt or a news "
    "headline+summary). Do not guess the company's identity or use outside "
    "knowledge of what happened to any specific company."
)
USER_TEMPLATE = (
    "Text (company name, ticker, month names, years and dollar amounts have "
    "been replaced with placeholders):\n{TEXT}\n\n"
    "Output JSON only: `polarity` (a number from -1 to 1: -1 = very negative "
    "for the subject company, 0 = neutral, +1 = very positive), `magnitude` "
    "(a number from 0 to 1: 0 = trivial/routine/no real information content, "
    "1 = major/highly consequential news)."
)
RETRY_INSTRUCTION = "Return only valid JSON, no explanation, no Markdown code fence."


def build_messages(neutral_text: str) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": USER_TEMPLATE.replace("{TEXT}", neutral_text)},
    ]


def build_retry_messages(neutral_text: str, prior_reply: str) -> list[dict[str, str]]:
    messages = build_messages(neutral_text)
    messages.append({"role": "assistant", "content": prior_reply})
    messages.append({"role": "user", "content": RETRY_INSTRUCTION})
    return messages


def parse_reply(content: str) -> dict | None:
    obj = _set._extract_json_object(content)
    if not isinstance(obj, dict):
        return None
    try:
        polarity = float(obj.get("polarity"))
        magnitude = float(obj.get("magnitude"))
    except (TypeError, ValueError):
        return None
    if not (polarity == polarity and magnitude == magnitude):  # NaN check
        return None
    polarity = max(-1.0, min(1.0, polarity))
    magnitude = max(0.0, min(1.0, magnitude))
    return {"polarity": polarity, "magnitude": magnitude}


@dataclass
class Item:
    item_kind: str  # "8k" or "news"
    item_id: str
    ticker: str
    source_timestamp: pd.Timestamp  # acceptance_utc (8-K) or visible_at (news)
    raw_text: str
    company_name: str | None


def load_8k_items() -> list[Item]:
    df = pd.read_parquet(
        EVENTS_PATH,
        columns=[
            "cik",
            "ticker",
            "company_name",
            "accession",
            "acceptance_utc",
            "text_path",
            "fetch_status",
        ],
    )
    df["acceptance_utc"] = pd.to_datetime(df["acceptance_utc"], utc=True)
    df = df[
        (df["acceptance_utc"] >= QUARTER_START)
        & (df["acceptance_utc"] < QUARTER_END)
        & df["ticker"].isin(UNIVERSE_SET)
        & (df["fetch_status"] == "ok")
    ]
    items: list[Item] = []
    for row in df.itertuples(index=False):
        text_path = ROOT / str(row.text_path)
        if not text_path.exists():
            continue
        try:
            raw_text = text_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        items.append(
            Item(
                item_kind="8k",
                item_id=str(row.accession),
                ticker=str(row.ticker),
                source_timestamp=row.acceptance_utc,
                raw_text=raw_text,
                company_name=str(row.company_name) if pd.notna(row.company_name) else None,
            )
        )
    return items


def load_news_items() -> list[Item]:
    df = pd.read_parquet(NEWS_PATH, columns=["id", "symbols", "visible_at", "headline", "summary"])
    df["visible_at"] = pd.to_datetime(df["visible_at"], utc=True)
    df = df[(df["visible_at"] >= QUARTER_START) & (df["visible_at"] < QUARTER_END)]

    items: list[Item] = []
    for row in df.itertuples(index=False):
        symbols = row.symbols
        if symbols is None:
            continue
        matched = [s for s in symbols if s in UNIVERSE_SET]
        if not matched:
            continue
        # A headline mentioning several universe tickers is attributed to
        # each -- distinct (item_id, ticker) rows so a multi-name headline
        # (e.g. an M&A story) contributes to every named ticker's feature,
        # not just the first alphabetically.
        headline = str(row.headline or "")
        summary = str(row.summary or "")
        text = f"{headline}\n{summary}".strip()
        if not text:
            continue
        for ticker in matched:
            items.append(
                Item(
                    item_kind="news",
                    item_id=f"{row.id}:{ticker}",
                    ticker=ticker,
                    source_timestamp=row.visible_at,
                    raw_text=text,
                    company_name=None,
                )
            )
    return items


def neutralise(item: Item) -> str:
    return _set.neutralise_text(
        item.raw_text, company_name=item.company_name, ticker=item.ticker, max_chars=8000
    )


def item_hash(item: Item, neutral_text: str) -> str:
    payload = json.dumps(
        {
            "kind": item.item_kind,
            "id": item.item_id,
            "prompt_version": PROMPT_VERSION,
            "text_sha256": hashlib.sha256(neutral_text.encode("utf-8")).hexdigest(),
        },
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def visible_at_for(item: Item) -> str:
    return (item.source_timestamp + timedelta(minutes=SCORING_LATENCY_MINUTES)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )


def load_cached(h: str) -> dict | None:
    path = CACHE_DIR / f"{h}.json"
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def write_cache(h: str, payload: dict) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    (CACHE_DIR / f"{h}.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False))


def load_already_scored() -> set[str]:
    if not OUT_PATH.is_file():
        return set()
    try:
        df = pd.read_parquet(OUT_PATH, columns=["item_hash"])
    except Exception:
        return set()
    return set(df["item_hash"].astype(str).tolist())


OUTPUT_COLUMNS = [
    "item_kind",
    "item_id",
    "ticker",
    "source_timestamp",
    "visible_at",
    "polarity",
    "magnitude",
    "status",
    "item_hash",
    "prompt_version",
    "scored_at",
]


def flush(rows: list[dict]) -> int:
    if not rows:
        return 0
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    new_df = pd.DataFrame(rows, columns=OUTPUT_COLUMNS)
    if OUT_PATH.is_file():
        existing = pd.read_parquet(OUT_PATH)
        existing = existing[~existing["item_hash"].isin(new_df["item_hash"])]
        merged = pd.concat([existing, new_df], ignore_index=True)
    else:
        merged = new_df
    tmp = OUT_PATH.with_suffix(".parquet.tmp")
    merged.to_parquet(tmp, index=False)
    tmp.replace(OUT_PATH)
    return len(new_df)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args(argv)

    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.FileHandler(LOG_PATH), logging.StreamHandler(sys.stdout)],
    )

    items_8k = load_8k_items()
    items_news = load_news_items()
    all_items = items_8k + items_news
    LOG.info("candidates: 8-K=%d news=%d total=%d", len(items_8k), len(items_news), len(all_items))
    if args.limit is not None:
        all_items = all_items[: args.limit]

    if args.dry_run:
        for it in all_items[:2]:
            neutral = neutralise(it)
            print("---", it.item_kind, it.item_id, it.ticker, "---")
            print(neutral[:800])
            print()
        LOG.info("dry-run complete, prompt_version=%s", PROMPT_VERSION)
        return 0

    creds = _set.load_credentials(_set.CREDENTIALS_PATH)
    model = creds["OC_TEXT_SCORER_MODEL"]
    call_fn = _set.make_requests_chat_call_fn(
        base_url=creds["OC_TEXT_SCORER_BASE_URL"],
        api_key=creds["OC_TEXT_SCORER_API_KEY"],
        model=model,
    )
    LOG.info("model=%s prompt_version=%s", model, PROMPT_VERSION)

    already = load_already_scored()
    pending: list[dict] = []
    processed = ok = cached_hits = errors = 0

    for item in all_items:
        neutral_text = neutralise(item)
        h = item_hash(item, neutral_text)
        if h in already:
            continue
        cached = load_cached(h)
        if cached is not None:
            cached_hits += 1
            parsed = {"polarity": cached["polarity"], "magnitude": cached["magnitude"]}
            status = cached["status"]
        else:
            try:
                result = call_fn(build_messages(neutral_text))
            except Exception as exc:  # network hiccup, not a rate-limit signal
                LOG.warning("network error on %s: %s", item.item_id, exc)
                errors += 1
                continue
            if _set.is_rate_limited(result):
                flush(pending)
                stop = _set.compute_next_try_at(result, now=datetime.now(UTC))
                NEXT_TRY_PATH.parent.mkdir(parents=True, exist_ok=True)
                NEXT_TRY_PATH.write_text(
                    json.dumps(
                        {
                            "next_try_at": stop.strftime("%Y-%m-%dT%H:%M:%SZ"),
                            "reason": f"HTTP {result.status_code}",
                            "written_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
                        },
                        indent=2,
                    )
                )
                LOG.warning("rate limited; stopping. next_try_at=%s", stop.isoformat())
                LOG.info(
                    "done(rate_limited): processed=%d ok=%d cached=%d errors=%d",
                    processed,
                    ok,
                    cached_hits,
                    errors,
                )
                return 0
            parsed = parse_reply(result.content_text) if result.content_text else None
            if parsed is None and result.content_text:
                retry = call_fn(build_retry_messages(neutral_text, result.content_text))
                if _set.is_rate_limited(retry):
                    flush(pending)
                    LOG.warning("rate limited on retry; stopping.")
                    return 0
                if retry.status_code == 200 and retry.content_text:
                    parsed = parse_reply(retry.content_text)
            status = "ok" if parsed is not None else "parse_error"
            write_cache(
                h,
                {
                    "item_kind": item.item_kind,
                    "item_id": item.item_id,
                    "polarity": parsed["polarity"] if parsed else None,
                    "magnitude": parsed["magnitude"] if parsed else None,
                    "status": status,
                    "model": model,
                    "prompt_version": PROMPT_VERSION,
                },
            )
        processed += 1
        if status == "ok":
            ok += 1
        row = {
            "item_kind": item.item_kind,
            "item_id": item.item_id,
            "ticker": item.ticker,
            "source_timestamp": item.source_timestamp.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "visible_at": visible_at_for(item),
            "polarity": parsed["polarity"] if parsed else None,
            "magnitude": parsed["magnitude"] if parsed else None,
            "status": status,
            "item_hash": h,
            "prompt_version": PROMPT_VERSION,
            "scored_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        pending.append(row)
        if len(pending) >= CHECKPOINT_EVERY:
            n = flush(pending)
            LOG.info(
                "checkpoint: wrote %d rows (processed=%d ok=%d cached=%d)",
                n,
                processed,
                ok,
                cached_hits,
            )
            pending = []

    flush(pending)
    LOG.info(
        "done: processed=%d ok=%d cached_hits=%d errors=%d total_candidates=%d",
        processed,
        ok,
        cached_hits,
        errors,
        len(all_items),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
