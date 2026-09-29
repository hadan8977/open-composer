"""H-20260928-22 DeepSeek pilot: LLM news-conditioned momentum re-ranking scores.

Card: reports/research/hypotheses/H-20260928-22-llm-news-momentum-filter.md;
reports/research/iterations/h20260928_22_llm_news_momentum_filter/{direction-review,
candidate-manifest}.json.

Replicates Anic, Barbon, Seiz and Zarattini (2025, arXiv:2510.26228) "ChatGPT in
Systematic Investing": at each month-end formation, every candidate in the top-2-decile
12-1 momentum pool (of the PIT largest-500 universe) is scored 0-1 by the owner-configured
DeepSeek endpoint from its own prior-30-day anonymized news headlines (cap 20 most
recent), using the paper's own basic prompt adapted with every company identity
(ticker/name) replaced by "the company" (Glasserman & Lin 2023, arXiv:2309.17322).

This script scores ONLY variant ``L`` (every candidate, CLEAN-window months first,
newest-to-oldest; contaminated months afterward only with ``--scope full``). Variant ``P``
(headline-shuffle placebo) needs no DeepSeek calls at all: 2026-09-28 pre-scoring amendment
(see candidate-manifest.json "amendments") -- this prompt carries no stock-specific numeric
content (only anonymized headlines plus a per-month asof/horizon date shared by every
candidate scored that month), so scoring ticker A with ticker B's headlines is a
byte-identical prompt to L's own call for ticker B in the same month. P is computed
downstream in scripts/run_h20260928_22_news_momentum.py as a seeded within-month
permutation of L's already-scored values (``derangement_map``), not scored here.

A candidate with zero qualifying headlines gets the paper's own no-news rule (normalized
score 0, i.e. raw 0.5) without a DeepSeek call. Every response is cached on disk under
``data/research/llm_cache/h20260928_22/<item_hash>.json`` keyed by a sha256 of (variant,
month, ticker, headline-id list, prompt version), so a rerun never re-queries an
already-scored item. Output rows are written to
``data/features/h20260928_22_news_momentum_scores/items.parquet``, checkpointed every
``CHECKPOINT_EVERY`` items.

Usage
-----
Dry run (no network calls, prints candidate counts and 2 sample prompts)::

    uv run python scripts/score_h20260928_22_news_momentum.py --dry-run

Score the CLEAN window (rate-limit-aware; safe to rerun, resumes from the parquet + disk
cache; default)::

    ./scripts/run_capped.sh --mem 1.5G -- uv run python \\
        scripts/score_h20260928_22_news_momentum.py --scope clean

Best-effort full period (clean window first, then contaminated months, informational
only)::

    ./scripts/run_capped.sh --mem 1.5G -- uv run python \\
        scripts/score_h20260928_22_news_momentum.py --scope full
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import logging
import random
import re
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

_set = importlib.import_module("scripts.score_earnings_text")

sys.path.insert(0, str(ROOT / "scripts"))
from open_composer.research.signal_card import load_market  # noqa: E402

NEWS_PATHS = sorted((ROOT / "data/features/news_packets").glob("*.parquet"))
COMPANY_TICKERS_PATH = ROOT / "data/raw/sec_xbrl/company_tickers.json"
OUT_DIR = ROOT / "data/features/h20260928_22_news_momentum_scores"
OUT_PATH = OUT_DIR / "items.parquet"
CACHE_DIR = ROOT / "data/research/llm_cache/h20260928_22"
NEXT_TRY_PATH = OUT_DIR / "next_try_at.json"
LOG_PATH = ROOT / "logs/score_h20260928_22_news_momentum.log"

FULL_PERIOD_START = pd.Timestamp("2024-01-01")
CLEAN_WINDOW_START = pd.Timestamp(
    "2026-05-01"
)  # first month-end on/after this (tz-naive, matches market.dates)
TOP_N_UNIVERSE = 500
DECILE_HI = 2  # top-2 deciles = the L/P candidate pool
LOOKBACK_DAYS = 30
HEADLINE_CAP = 20
MIN_MEMBERS_FOR_DECILE = 30
PLACEBO_SEED_BASE = 20260928
REFUTATION_CONTAMINATED_MONTHS = 14
SLEEP_BETWEEN_CALLS_SECONDS = 0.3  # keep concurrency low; another agent shares the endpoint

CHECKPOINT_EVERY = 50
LOG = logging.getLogger("score_h20260928_22")

PROMPT_VERSION = "h20260928_22_v1"
SYSTEM_PROMPT = (
    "You are a financial analysis model tasked with constructing and rebalancing a "
    "long-only US equity portfolio based on momentum signals and news-driven sentiment "
    "scores for each stock. Read only the given text; do not guess the company's "
    "identity or use outside knowledge of what happened to any specific company."
)
USER_TEMPLATE = (
    "---- Context Preamble ----\n"
    "At the end of each month, you form a momentum portfolio of large, liquid US stocks "
    "(top decile of past 12-month returns, excluding the most recent month). To enhance "
    "the baseline momentum portfolio, you also analyze news sentiment for stocks in the "
    "broader top-2-decile momentum pool. Currently you are working with the company, "
    "whose identity has been withheld.\n\n"
    "---- News Block Information ----\n"
    "Below is a list of news related to the company, released over the previous "
    "{LOOKBACK_DAYS} days, published up to {ASOF_DATE}. They are ordered most recent "
    "first; each item has [days ago], a Title line, then a Short Summary line.\n\n"
    "{NEWS_BLOCK}\n\n"
    "---- Task Description ----\n"
    "Your task is to read all news headlines and summaries for the company published up "
    "to {ASOF_DATE}, and predict whether the company's stock upward momentum will "
    "continue through the close on {HORIZON_DATE}.\n\n"
    "---- Output Format ----\n"
    "The prediction is expressed as a score from 0 to 1, where 0 means the momentum will "
    "stop or revert, and 1 indicates that momentum will continue. Intermediate values "
    "(e.g., 0.5615) represent the probability you assign to momentum continuation.\n\n"
    "**IMPORTANT**: Output only the score (e.g., '0.7341') and nothing else."
)
RETRY_INSTRUCTION = (
    "Return only a single number between 0 and 1, no words, no JSON, no explanation."
)

_SCORE_RE = re.compile(r"(-?\d*\.?\d+)")


def build_messages(news_block: str, asof_date: str, horizon_date: str) -> list[dict[str, str]]:
    user = USER_TEMPLATE.format(
        LOOKBACK_DAYS=LOOKBACK_DAYS,
        ASOF_DATE=asof_date,
        HORIZON_DATE=horizon_date,
        NEWS_BLOCK=news_block,
    )
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]


def build_retry_messages(
    news_block: str, asof_date: str, horizon_date: str, prior_reply: str
) -> list[dict[str, str]]:
    messages = build_messages(news_block, asof_date, horizon_date)
    messages.append({"role": "assistant", "content": prior_reply})
    messages.append({"role": "user", "content": RETRY_INSTRUCTION})
    return messages


def parse_score(content: str) -> float | None:
    text = content.strip()
    match = _SCORE_RE.search(text)
    if not match:
        return None
    try:
        value = float(match.group(1))
    except ValueError:
        return None
    if value != value:  # NaN
        return None
    return max(0.0, min(1.0, value))


# --------------------------------------------------------------------------- anonymization


def load_ticker_name_map() -> dict[str, str]:
    if not COMPANY_TICKERS_PATH.exists():
        return {}
    data = json.loads(COMPANY_TICKERS_PATH.read_text(encoding="utf-8"))
    out: dict[str, str] = {}
    for row in data.values():
        ticker = str(row.get("ticker") or "").upper()
        title = str(row.get("title") or "")
        if ticker and title:
            out[ticker] = title
    return out


def anonymize(text: str, *, ticker: str, company_name: str | None) -> str:
    """Replace the company's name and ticker with "the company", following
    Glasserman & Lin (2023, arXiv:2309.17322) on GPT look-ahead/distraction bias."""
    result = text
    if company_name:
        for variant in _set._company_name_variants(company_name):
            if len(variant) < 3:
                continue
            pattern = re.compile(r"(?<!\w)" + re.escape(variant) + r"(?!\w)", re.IGNORECASE)
            result = pattern.sub("the company", result)
    if ticker:
        result = re.compile(r"\b" + re.escape(ticker) + r"\b").sub("the company", result)
    return result


# --------------------------------------------------------------------------- data loading


def explode_news(df: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """One row per (article, mentioned symbol), grouped by symbol and sorted by
    visible_at ascending, so a per-(ticker, asof) lookup is a dict hit plus a
    ``searchsorted`` on a small per-symbol series instead of a full-table scan.
    A multi-symbol headline (e.g. an M&A story) contributes to every named
    ticker's group, matching scripts/score_h20260928_16_sentiment_accel.py's
    convention. Pure function (no I/O) so it is directly unit-testable."""
    symbols_col = df["symbols"]
    rep = symbols_col.map(lambda s: len(s) if s is not None else 0)
    keep = rep > 0
    if not keep.any():
        return {}
    exploded = pd.DataFrame(
        {
            "symbol": np.concatenate(symbols_col[keep].to_numpy()),
            "id": np.repeat(df.loc[keep, "id"].to_numpy(), rep[keep].to_numpy()),
            "visible_at": np.repeat(df.loc[keep, "visible_at"].to_numpy(), rep[keep].to_numpy()),
            "headline": np.repeat(df.loc[keep, "headline"].to_numpy(), rep[keep].to_numpy()),
            "summary": np.repeat(df.loc[keep, "summary"].to_numpy(), rep[keep].to_numpy()),
        }
    )
    exploded = exploded.sort_values(["symbol", "visible_at"])
    return {sym: grp.reset_index(drop=True) for sym, grp in exploded.groupby("symbol", sort=False)}


def load_news_index() -> dict[str, pd.DataFrame]:
    frames = [
        pd.read_parquet(p, columns=["id", "symbols", "visible_at", "headline", "summary"])
        for p in NEWS_PATHS
    ]
    df = pd.concat(frames, ignore_index=True)
    df["visible_at"] = pd.to_datetime(df["visible_at"], utc=True)
    return explode_news(df)


def headlines_for(
    news_index: dict[str, pd.DataFrame],
    ticker: str,
    asof: pd.Timestamp,
    name_map: dict[str, str],
) -> list[dict]:
    grp = news_index.get(ticker)
    if grp is None or grp.empty:
        return []
    lo = asof - pd.Timedelta(days=LOOKBACK_DAYS)
    va = grp["visible_at"]
    lo_i = int(va.searchsorted(lo, side="left"))
    hi_i = int(va.searchsorted(asof, side="left"))  # strictly before asof
    sub = grp.iloc[lo_i:hi_i]
    rows = [
        {
            "id": int(r.id),
            "visible_at": r.visible_at,
            "headline": str(r.headline or ""),
            "summary": str(r.summary or ""),
        }
        for r in sub.itertuples(index=False)
    ]
    rows.sort(key=lambda r: r["visible_at"], reverse=True)
    rows = rows[:HEADLINE_CAP]
    company_name = name_map.get(ticker)
    for r in rows:
        text = f"{r['headline']}\n{r['summary']}".strip()
        r["anon_text"] = anonymize(text, ticker=ticker, company_name=company_name)
    return rows


def render_news_block(rows: list[dict], asof: pd.Timestamp) -> str:
    parts = []
    for r in rows:
        days_ago = max(0, (asof - r["visible_at"]).days)
        parts.append(f"[{days_ago} days ago]\n{r['anon_text']}")
    return "\n\n".join(parts)


# --------------------------------------------------------------------------- candidate pool


def month_end_indices(dates: pd.DatetimeIndex, start: pd.Timestamp) -> list[int]:
    periods = dates.to_period("M")
    out = []
    for i in range(len(dates) - 1):
        if periods[i] != periods[i + 1] and dates[i] >= start:
            out.append(i)
    if len(dates) and dates[-1] >= start and (not out or out[-1] != len(dates) - 1):
        out.append(len(dates) - 1)
    return out


@dataclass
class Item:
    variant: str
    month: str
    ticker: str
    headline_ticker: str  # for P, the ticker whose headlines were actually used
    asof: pd.Timestamp
    horizon: pd.Timestamp


def item_hash(item: Item, headline_ids: list[int]) -> str:
    payload = json.dumps(
        {
            "variant": item.variant,
            "month": item.month,
            "ticker": item.ticker,
            "headline_ticker": item.headline_ticker,
            "headline_ids": sorted(headline_ids),
            "prompt_version": PROMPT_VERSION,
        },
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


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
    "variant",
    "month",
    "ticker",
    "headline_ticker",
    "asof",
    "score_raw",
    "score_norm",
    "n_headlines",
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


def derangement_map(tickers: list[str], seed: int) -> dict[str, str]:
    """Each ticker maps to a different ticker's headlines (never itself)."""
    if len(tickers) < 2:
        return dict.fromkeys(tickers, tickers[0] if tickers else "")
    rng = random.Random(seed)
    for _ in range(200):
        shuffled = tickers[:]
        rng.shuffle(shuffled)
        if all(a != b for a, b in zip(tickers, shuffled, strict=True)):
            return dict(zip(tickers, shuffled, strict=True))
    # fallback: rotate by 1 (always a derangement for len>=2)
    shuffled = tickers[1:] + tickers[:1]
    return dict(zip(tickers, shuffled, strict=True))


def build_candidate_months(
    market, *, start: pd.Timestamp, momentum: np.ndarray
) -> list[tuple[int, pd.Timestamp, pd.Timestamp, list[str]]]:
    """Return (formation_idx, asof, horizon, pool_tickers) per month-end."""
    idxs = month_end_indices(market.dates, start)
    out = []
    for j, idx in enumerate(idxs):
        member = market.member()[idx]
        sig = np.where(member & np.isfinite(momentum[idx]), momentum[idx], np.nan)
        n = int(np.isfinite(sig).sum())
        if n < MIN_MEMBERS_FOR_DECILE:
            continue
        order = np.argsort(-np.where(np.isfinite(sig), sig, -np.inf))
        # top-2-deciles of the eligible member count that day (~20%)
        k = max(1, round(n * (DECILE_HI / 10.0)))
        pool_idx = order[:k]
        pool = [str(market.symbols[i]) for i in pool_idx]
        # Approximate the US market close as 21:00 UTC (4pm ET, ignoring the
        # +/-1h DST wobble -- a disclosed approximation; news visible_at is
        # tz-aware UTC and the 30-day lookback window is insensitive to a
        # one-hour offset).
        asof = market.dates[idx].tz_localize("UTC") + pd.Timedelta(hours=21)
        horizon_date = market.dates[idxs[j + 1]] if j + 1 < len(idxs) else market.dates[-1]
        horizon = horizon_date.tz_localize("UTC") + pd.Timedelta(hours=21)
        out.append((idx, asof, horizon, pool))
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--variant",
        choices=["L"],
        default="L",
        help=(
            "Only L is ever scored over the network. P (headline-shuffle placebo) needs no "
            "DeepSeek calls at all: this prompt template carries no stock-specific numeric "
            "content (only anonymized headlines plus a per-month asof/horizon date shared by "
            "every candidate that month), so scoring ticker A with ticker B's headlines "
            "produces a byte-identical prompt to L's own call for ticker B in the same "
            "month. P is therefore computed downstream, in "
            "scripts/run_h20260928_22_news_momentum.py, as a seeded within-month "
            "permutation of L's already-scored values via derangement_map() -- see the "
            "2026-09-28 pre-scoring amendment in candidate-manifest.json."
        ),
    )
    parser.add_argument(
        "--scope",
        choices=["clean", "clean_plus_refutation14", "full"],
        default="clean_plus_refutation14",
        help=(
            "clean: score only CLEAN-window formations (2026-05-29 onward; ~5 formations, "
            "underpowered alone -- see candidate-manifest.json AMEND-4). "
            "clean_plus_refutation14 (default, per the 2026-09-28 AMEND-4 fallback design): "
            "clean window first, then the 14 most recent CONTAMINATED (look-ahead) "
            "month-ends, newest first, as a refutation-only asymmetric check. full: also "
            "score every remaining contaminated month, needed only for the brief's "
            "informational L-vs-S3/K1 and full-period t-stat figures, attempted best-effort "
            "after clean_plus_refutation14 is secured."
        ),
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args(argv)

    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.FileHandler(LOG_PATH), logging.StreamHandler(sys.stdout)],
    )

    from open_composer.research.signal_card import load_signal

    LOG.info("loading market (top_n=%d)...", TOP_N_UNIVERSE)
    market = load_market(top_n=TOP_N_UNIVERSE, memory_limit="1200MB")
    momentum = load_signal(
        market, source="data/features/daily_broad", column="momentum_252_21", lag=0
    )

    months = build_candidate_months(market, start=FULL_PERIOD_START, momentum=momentum)
    LOG.info("formations: %d", len(months))

    name_map = load_ticker_name_map()
    LOG.info("loading and indexing news_packets by symbol...")
    news = load_news_index()
    LOG.info("news index: %d symbols", len(news))

    # Newest-month-first: a partial run (rate-limit-truncated) then still covers
    # the most recent, most decision-relevant months first. Within the clean
    # window this is exactly the CLEAN-window priority order; contaminated
    # (pre-cutoff) months are only appended after every clean month when
    # --scope=full, and are always ordered after the whole clean window.
    clean_start_utc = CLEAN_WINDOW_START.tz_localize("UTC")
    ordered_months = sorted(months, key=lambda m: m[1], reverse=True)
    clean_months = [m for m in ordered_months if m[1] >= clean_start_utc]
    contaminated_months = [m for m in ordered_months if m[1] < clean_start_utc]
    if args.scope == "clean":
        scope_months = clean_months
    elif args.scope == "clean_plus_refutation14":
        # contaminated_months is already sorted newest-first (inherited from
        # ordered_months); take the 14 most recent.
        scope_months = clean_months + contaminated_months[:REFUTATION_CONTAMINATED_MONTHS]
    else:  # full
        scope_months = clean_months + contaminated_months

    all_items: list[tuple[Item, list[dict]]] = []
    for _idx, asof, horizon, pool in scope_months:
        month_key = str(asof.date())
        for t in pool:
            all_items.append(
                (
                    Item("L", month_key, t, t, asof, horizon),
                    headlines_for(news, t, asof, name_map),
                )
            )

    LOG.info(
        "candidate items: %d (scope=%s, clean_months=%d, contaminated_months=%d)",
        len(all_items),
        args.scope,
        len(clean_months),
        len(contaminated_months),
    )
    if args.limit is not None:
        all_items = all_items[: args.limit]

    if args.dry_run:
        for item, rows in all_items[:2]:
            block = render_news_block(rows, item.asof)
            msgs = build_messages(block, str(item.asof.date()), str(item.horizon.date()))
            print("---", item.variant, item.month, item.ticker, "n_headlines=", len(rows), "---")
            print(msgs[1]["content"][:1000])
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
    processed = ok = cached_hits = errors = skipped_no_news = 0

    for item, rows in all_items:
        headline_ids = [r["id"] for r in rows]
        h = item_hash(item, headline_ids)
        if h in already:
            continue
        if not rows:
            skipped_no_news += 1
            pending.append(
                {
                    "variant": item.variant,
                    "month": item.month,
                    "ticker": item.ticker,
                    "headline_ticker": item.headline_ticker,
                    "asof": item.asof.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "score_raw": 0.5,
                    "score_norm": 0.0,
                    "n_headlines": 0,
                    "status": "no_news_default",
                    "item_hash": h,
                    "prompt_version": PROMPT_VERSION,
                    "scored_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
                }
            )
            if len(pending) >= CHECKPOINT_EVERY:
                n = flush(pending)
                LOG.info("checkpoint: wrote %d rows", n)
                pending = []
            continue
        cached = load_cached(h)
        if cached is not None:
            cached_hits += 1
            score_raw = cached["score_raw"]
            status = cached["status"]
        else:
            block = render_news_block(rows, item.asof)
            asof_str = str(item.asof.date())
            horizon_str = str(item.horizon.date())
            messages = build_messages(block, asof_str, horizon_str)
            try:
                result = call_fn(messages)
            except Exception as exc:
                LOG.warning("network error on %s %s: %s", item.month, item.ticker, exc)
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
                    "done(rate_limited): processed=%d ok=%d cached=%d errors=%d no_news=%d",
                    processed,
                    ok,
                    cached_hits,
                    errors,
                    skipped_no_news,
                )
                return 0
            score_raw = parse_score(result.content_text) if result.content_text else None
            if score_raw is None and result.content_text:
                retry = call_fn(
                    build_retry_messages(block, asof_str, horizon_str, result.content_text)
                )
                if _set.is_rate_limited(retry):
                    flush(pending)
                    LOG.warning("rate limited on retry; stopping.")
                    return 0
                if retry.status_code == 200 and retry.content_text:
                    score_raw = parse_score(retry.content_text)
            status = "ok" if score_raw is not None else "parse_error"
            write_cache(
                h,
                {
                    "score_raw": score_raw,
                    "status": status,
                    "model": model,
                    "prompt_version": PROMPT_VERSION,
                },
            )
            time.sleep(SLEEP_BETWEEN_CALLS_SECONDS)
        processed += 1
        if status == "ok":
            ok += 1
        score_norm = (2.0 * score_raw - 1.0) if score_raw is not None else None
        pending.append(
            {
                "variant": item.variant,
                "month": item.month,
                "ticker": item.ticker,
                "headline_ticker": item.headline_ticker,
                "asof": item.asof.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "score_raw": score_raw,
                "score_norm": score_norm,
                "n_headlines": len(rows),
                "status": status,
                "item_hash": h,
                "prompt_version": PROMPT_VERSION,
                "scored_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            }
        )
        if len(pending) >= CHECKPOINT_EVERY:
            n = flush(pending)
            LOG.info(
                "checkpoint: wrote %d rows (processed=%d ok=%d cached=%d no_news=%d)",
                n,
                processed,
                ok,
                cached_hits,
                skipped_no_news,
            )
            pending = []

    flush(pending)
    LOG.info(
        "done: processed=%d ok=%d cached_hits=%d errors=%d no_news=%d total_candidates=%d",
        processed,
        ok,
        cached_hits,
        errors,
        skipped_no_news,
        len(all_items),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
