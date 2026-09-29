"""T-20260928-17 DeepSeek pilot: structured 8-K risk-label scoring.

Card: reports/research/control/autonomous-queue.md T-20260928-17;
reports/research/iterations/h20260928_17_filing_risk_labels/{direction-review,
candidate-manifest}.json.

Scores 8-K text for the preregistered fixed-seed 50-ticker x 8-quarter
(2024Q3..2026Q2) panel via the owner-configured DeepSeek endpoint, through
the existing OpenAI-compatible client in scripts/score_earnings_text.py (same
credentials file, same rate-limit/checkpoint/retry machinery -- only the
prompt and output schema differ). Each item gets
{risk_score in [0, 1], risk_direction in {up, same, down}} plus a
`visible_at` timestamp = acceptance_utc + SCORING_LATENCY_MINUTES.

Every response is cached on disk under
data/research/llm_cache/h20260928_17_filing_risk_labels/<item_hash>.json
keyed by a sha256 of (accession, neutralised text, prompt version). Output
rows go to data/features/h20260928_17_filing_risk_labels_scores/items.parquet,
checkpointed every CHECKPOINT_EVERY items.

Some (ticker, quarter) cells have more than one 8-K (e.g. an 8-K/A amendment
or a non-earnings item in the same quarter); the feature-build script reduces
these to one value per (ticker, quarter) by taking the chronologically LAST
filing's score, not by scoring reduction here -- this script scores every
fetchable item in the panel (up to ~436 items for a 50x8=400 target).

Usage
-----
Dry run::

    uv run python scripts/score_h20260928_17_filing_risk_labels.py --dry-run

Score everything::

    ./scripts/run_capped.sh --mem 1.2G -- uv run python \\
        scripts/score_h20260928_17_filing_risk_labels.py
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

EVENTS_PATHS = [ROOT / f"data/features/earnings_events/{yr}.parquet" for yr in (2024, 2025, 2026)]
OUT_DIR = ROOT / "data/features/h20260928_17_filing_risk_labels_scores"
OUT_PATH = OUT_DIR / "items.parquet"
CACHE_DIR = ROOT / "data/research/llm_cache/h20260928_17_filing_risk_labels"
NEXT_TRY_PATH = OUT_DIR / "next_try_at.json"
LOG_PATH = ROOT / "logs/score_h20260928_17_filing_risk_labels.log"

WINDOW_START = pd.Timestamp("2024-07-01", tz="UTC")
WINDOW_END = pd.Timestamp("2026-07-01", tz="UTC")  # exclusive

# Preregistered 50-ticker sample (candidate-manifest.json RISK01
# parameters.universe_tickers -- fixed seed random.Random(20260928).sample of
# the 1146 tickers with an 8-K in ALL 8 of 2024Q3..2026Q2). Copied verbatim.
UNIVERSE_TICKERS = [
    "AAON",
    "ABBV",
    "ADMA",
    "AGX",
    "ALSN",
    "AMD",
    "AMR",
    "ASTC",
    "BA",
    "CB",
    "CCK",
    "CF",
    "CGON",
    "EHC",
    "ELS",
    "ENSG",
    "ES",
    "EXR",
    "FICO",
    "FSLR",
    "GDDY",
    "GOOG",
    "HEI",
    "HOOD",
    "HSIC",
    "HUBB",
    "IEX",
    "IR",
    "JPM",
    "KRC",
    "LHX",
    "MOH",
    "MTSI",
    "NOW",
    "NTRS",
    "NWSA",
    "OLED",
    "PSX",
    "RKLB",
    "RNR",
    "RPM",
    "SG",
    "SSNC",
    "TEL",
    "TFX",
    "ULS",
    "UWMC",
    "VVV",
    "WVE",
    "XYL",
]
assert len(UNIVERSE_TICKERS) == 50
UNIVERSE_SET = set(UNIVERSE_TICKERS)

SCORING_LATENCY_MINUTES = 15
CHECKPOINT_EVERY = 50

LOG = logging.getLogger("score_h20260928_17")

PROMPT_VERSION = "h20260928_17_v1"
SYSTEM_PROMPT = (
    "You are a financial-filing risk analyst. Read only the given text (a company "
    "name/ticker/date-neutralised SEC 8-K excerpt). Do not guess the company's "
    "identity or use outside knowledge of what happened to any specific company."
)
USER_TEMPLATE = (
    "Text (company name, ticker, month names, years and dollar amounts have "
    "been replaced with placeholders):\n{TEXT}\n\n"
    "Output JSON only: `risk_score` (a number from 0 to 1: 0 = no material "
    "risk or uncertainty language, 1 = major disclosed risk or uncertainty -- "
    "e.g. guidance cuts, litigation, restatements, covenant breaches, going-"
    "concern language, material weaknesses), `risk_direction` (one of "
    "'up', 'same', 'down': whether the disclosed risk/uncertainty level "
    "seems to be increasing, unchanged, or decreasing relative to a typical "
    "routine filing for this kind of company)."
)
RETRY_INSTRUCTION = "Return only valid JSON, no explanation, no Markdown code fence."
_VALID_DIRECTION = {"up", "same", "down"}


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
        risk_score = float(obj.get("risk_score"))
    except (TypeError, ValueError):
        return None
    if risk_score != risk_score:  # NaN
        return None
    risk_score = max(0.0, min(1.0, risk_score))
    direction = str(obj.get("risk_direction") or "").strip().lower()
    if direction not in _VALID_DIRECTION:
        direction = "same"
    return {"risk_score": risk_score, "risk_direction": direction}


@dataclass
class Item:
    accession: str
    ticker: str
    company_name: str | None
    acceptance_utc: pd.Timestamp
    quarter: str
    raw_text: str


def load_items() -> list[Item]:
    frames = []
    for path in EVENTS_PATHS:
        if path.exists():
            frames.append(
                pd.read_parquet(
                    path,
                    columns=[
                        "ticker",
                        "company_name",
                        "accession",
                        "acceptance_utc",
                        "text_path",
                        "fetch_status",
                    ],
                )
            )
    df = pd.concat(frames, ignore_index=True)
    df["acceptance_utc"] = pd.to_datetime(df["acceptance_utc"], utc=True)
    df = df[
        df["ticker"].isin(UNIVERSE_SET)
        & (df["acceptance_utc"] >= WINDOW_START)
        & (df["acceptance_utc"] < WINDOW_END)
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
        quarter = str(row.acceptance_utc.to_period("Q"))
        items.append(
            Item(
                accession=str(row.accession),
                ticker=str(row.ticker),
                company_name=str(row.company_name) if pd.notna(row.company_name) else None,
                acceptance_utc=row.acceptance_utc,
                quarter=quarter,
                raw_text=raw_text,
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
            "accession": item.accession,
            "prompt_version": PROMPT_VERSION,
            "text_sha256": hashlib.sha256(neutral_text.encode("utf-8")).hexdigest(),
        },
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def visible_at_for(item: Item) -> str:
    return (item.acceptance_utc + timedelta(minutes=SCORING_LATENCY_MINUTES)).strftime(
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
    "accession",
    "ticker",
    "quarter",
    "acceptance_utc",
    "visible_at",
    "risk_score",
    "risk_direction",
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

    items = load_items()
    LOG.info("candidates: %d (target ~400 ticker-quarters, 50 tickers x 8 quarters)", len(items))
    if args.limit is not None:
        items = items[: args.limit]

    if args.dry_run:
        for it in items[:2]:
            neutral = neutralise(it)
            print("---", it.accession, it.ticker, it.quarter, "---")
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

    for item in items:
        neutral_text = neutralise(item)
        h = item_hash(item, neutral_text)
        if h in already:
            continue
        cached = load_cached(h)
        if cached is not None:
            cached_hits += 1
            parsed = {
                "risk_score": cached["risk_score"],
                "risk_direction": cached["risk_direction"],
            }
            status = cached["status"]
        else:
            try:
                result = call_fn(build_messages(neutral_text))
            except Exception as exc:
                LOG.warning("network error on %s: %s", item.accession, exc)
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
                    "accession": item.accession,
                    "risk_score": parsed["risk_score"] if parsed else None,
                    "risk_direction": parsed["risk_direction"] if parsed else None,
                    "status": status,
                    "model": model,
                    "prompt_version": PROMPT_VERSION,
                },
            )
        processed += 1
        if status == "ok":
            ok += 1
        row = {
            "accession": item.accession,
            "ticker": item.ticker,
            "quarter": item.quarter,
            "acceptance_utc": item.acceptance_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "visible_at": visible_at_for(item),
            "risk_score": parsed["risk_score"] if parsed else None,
            "risk_direction": parsed["risk_direction"] if parsed else None,
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
        len(items),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
