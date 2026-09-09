"""Step 13 Track L, L0: Alpaca News (Benzinga) PIT packet collection.

docs/plan-step-13-recent-high-return-ml-and-llm-tracks-2026-09-09.zh.md
section 4.1. Pulls the *entire* market news feed (no symbol filter -- the
candidate pool that actually needs extraction is applied later, at L1, so
this stage stays a cheap, complete, re-usable archive rather than being
re-fetched every time the candidate pool changes) from
``GET https://data.alpaca.markets/v1beta1/news``, paginated via
``next_page_token``, ``include_content=false`` (headline + summary only).

Two distinct visibility semantics, both required by the promotion gate
contract's ``knowledge_time_disclosure`` block
(``config/promotion/recent-regime-high-return-gates-v2.json``):

* **Historical** (``historical=True``): ``visible_at = created_at + 15min``
  -- the provider timestamp plus a fixed disclosure lag, not a proof of
  local first-seen time. This is research-tier evidence only (a 2026
  extraction model may already "know" 2024-2026 outcomes) -- never cited as
  clean PIT evidence on its own.
* **Forward** (``historical=False``): ``visible_at = fetched_at`` -- the
  collector's own wall-clock fetch time. This is the only clean PIT
  evidence this pipeline can produce, and only accumulates from whenever
  forward collection starts (see ``collect_forward``).

Credentials: ``ALPACA_API_KEY_ID`` / ``ALPACA_API_SECRET_KEY`` via
``open_composer.config`` (``os.environ`` accessors) -- this module never
calls ``load_dotenv()`` itself and never reads/prints ``.env``; the caller
(``scripts/collect_alpaca_news_packets.py``) loads it once at process start,
same pattern as ``scripts/update_sip_archive.py``.

Layout on disk (``data/features/news_packets/``):

- ``_daily/{YYYY-MM-DD}.parquet``: one file per calendar day actually
  fetched -- the resumability unit ("day already collected" == "file
  exists"), and the crash-safety unit (a crash mid-pull leaves at most one
  partial day to re-fetch, never corrupts an already-written day).
- ``{year}.parquet``: consolidated view for a year, built by
  ``consolidate_year`` from that year's ``_daily/*.parquet`` files,
  deduplicated by ``id`` (keep last -- a forward re-fetch of a recent day
  can see a provider-side update to an already-collected article).
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

from open_composer.config import alpaca_api_key_id, alpaca_api_secret_key

ROOT = Path(__file__).resolve().parents[3]
NEWS_PACKETS_ROOT = ROOT / "data" / "features" / "news_packets"
DAILY_ROOT = NEWS_PACKETS_ROOT / "_daily"

ALPACA_NEWS_URL = "https://data.alpaca.markets/v1beta1/news"
PAGE_LIMIT = 50
#: 200 req/min is the documented Alpaca data-API limit; sleeping this long
#: between page fetches caps us at <120/min with real per-request latency on
#: top, leaving headroom rather than tuning right up against the wall.
MIN_SECONDS_BETWEEN_REQUESTS = 0.4
HISTORICAL_VISIBILITY_LAG = timedelta(minutes=15)

#: Exact packet schema, plan section 4.1. Order matters only for readability
#: (parquet columns are addressed by name everywhere downstream).
PACKET_COLUMNS: tuple[str, ...] = (
    "id",
    "created_at",
    "updated_at",
    "symbols",
    "headline",
    "summary",
    "source",
    "url",
    "author",
    "fetched_at",
    "visible_at",
)


class AlpacaCredentialsMissing(RuntimeError):
    pass


def _headers() -> dict[str, str]:
    api_key = alpaca_api_key_id()
    secret_key = alpaca_api_secret_key()
    if not api_key or not secret_key:
        raise AlpacaCredentialsMissing(
            "ALPACA_API_KEY_ID / ALPACA_API_SECRET_KEY are required for the news collector "
            "(set them in .env; this module never reads .env directly, only os.environ via "
            "open_composer.config, populated by the caller's load_dotenv())"
        )
    return {"APCA-API-KEY-ID": api_key, "APCA-API-SECRET-KEY": secret_key}


@dataclass(frozen=True)
class _PageResult:
    articles: list[dict[str, Any]]
    next_page_token: str | None


_last_request_monotonic: float | None = None


def _rate_limit_wait() -> None:
    global _last_request_monotonic
    now = time.monotonic()
    if _last_request_monotonic is not None:
        elapsed = now - _last_request_monotonic
        remaining = MIN_SECONDS_BETWEEN_REQUESTS - elapsed
        if remaining > 0:
            time.sleep(remaining)
    _last_request_monotonic = time.monotonic()


def _fetch_page(
    *,
    start_iso: str,
    end_iso: str,
    page_token: str | None,
    session: Any = None,
) -> _PageResult:
    """One page of the Alpaca News v1beta1 feed. No ``symbols`` param at all
    (plan: "不做 symbol 过滤") -- the entire market feed for this window.
    """
    import httpx

    client = session or httpx
    params: dict[str, Any] = {
        "start": start_iso,
        "end": end_iso,
        "limit": PAGE_LIMIT,
        "sort": "asc",
        "include_content": False,
    }
    if page_token:
        params["page_token"] = page_token
    _rate_limit_wait()
    response = client.get(ALPACA_NEWS_URL, params=params, headers=_headers(), timeout=30)
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise RuntimeError("Alpaca news response must be a JSON object")
    articles = payload.get("news", [])
    if not isinstance(articles, list):
        raise RuntimeError("Alpaca news response 'news' field must be a list")
    return _PageResult(articles=articles, next_page_token=payload.get("next_page_token"))


def _article_to_packet(
    article: dict[str, Any], *, fetched_at: datetime, historical: bool
) -> dict[str, Any] | None:
    article_id = article.get("id")
    created_at_raw = article.get("created_at")
    if article_id is None or not created_at_raw:
        return None
    created_at = pd.Timestamp(created_at_raw)
    if created_at.tzinfo is None:
        created_at = created_at.tz_localize("UTC")
    updated_at_raw = article.get("updated_at") or created_at_raw
    updated_at = pd.Timestamp(updated_at_raw)
    if updated_at.tzinfo is None:
        updated_at = updated_at.tz_localize("UTC")
    visible_at = created_at + HISTORICAL_VISIBILITY_LAG if historical else pd.Timestamp(fetched_at)
    symbols = [
        str(symbol).upper().strip()
        for symbol in article.get("symbols", []) or []
        if isinstance(symbol, str) and symbol.strip()
    ]
    return {
        "id": str(article_id),
        "created_at": created_at,
        "updated_at": updated_at,
        "symbols": symbols,
        "headline": str(article.get("headline") or ""),
        "summary": str(article.get("summary") or ""),
        "source": str(article.get("source") or ""),
        "url": str(article.get("url") or ""),
        "author": str(article.get("author") or ""),
        "fetched_at": pd.Timestamp(fetched_at),
        "visible_at": visible_at,
    }


def _to_utc_iso(moment: datetime) -> str:
    ts = pd.Timestamp(moment)
    ts = ts.tz_localize("UTC") if ts.tzinfo is None else ts.tz_convert("UTC")
    return ts.isoformat()


def fetch_window(
    *,
    start: datetime,
    end: datetime,
    historical: bool,
    session: Any = None,
    max_pages: int | None = None,
) -> list[dict[str, Any]]:
    """All articles published in ``[start, end)``, paginated to exhaustion
    (or ``max_pages``, for tests). One ``fetched_at`` timestamp is shared by
    every packet from this call -- they were all fetched "now", by
    construction.
    """
    start_iso = _to_utc_iso(start)
    end_iso = _to_utc_iso(end)
    fetched_at = datetime.now(UTC)
    packets: list[dict[str, Any]] = []
    page_token: str | None = None
    pages_fetched = 0
    while True:
        page = _fetch_page(
            start_iso=start_iso, end_iso=end_iso, page_token=page_token, session=session
        )
        for article in page.articles:
            packet = _article_to_packet(article, fetched_at=fetched_at, historical=historical)
            if packet is not None:
                packets.append(packet)
        pages_fetched += 1
        if not page.next_page_token:
            break
        if max_pages is not None and pages_fetched >= max_pages:
            break
        page_token = page.next_page_token
    return packets


def daily_packet_path(day: date) -> Path:
    return DAILY_ROOT / f"{day.isoformat()}.parquet"


def _packets_to_frame(packets: list[dict[str, Any]]) -> pd.DataFrame:
    if not packets:
        return pd.DataFrame(columns=PACKET_COLUMNS)
    frame = pd.DataFrame(packets)
    return frame[list(PACKET_COLUMNS)]


def collect_day(day: date, *, historical: bool, session: Any = None) -> pd.DataFrame:
    """One calendar day's full-market news feed, UTC boundaries
    ``[day 00:00:00, day+1 00:00:00)``.
    """
    start = datetime(day.year, day.month, day.day, tzinfo=UTC)
    end = start + timedelta(days=1)
    packets = fetch_window(start=start, end=end, historical=historical, session=session)
    return _packets_to_frame(packets)


@dataclass(frozen=True)
class HistoricalCollectionSummary:
    days_requested: int
    days_fetched: int
    days_skipped_already_done: int
    total_articles: int


def collect_historical_range(
    start_date: date,
    end_date: date,
    *,
    resume: bool = True,
    session: Any = None,
    progress: Any = None,
) -> HistoricalCollectionSummary:
    """Day-by-day historical pull, ``[start_date, end_date]`` inclusive.
    Resumable: a day whose ``_daily/{day}.parquet`` already exists is
    skipped (unless ``resume=False``), so a killed/restarted run picks up
    exactly where it left off with no separate state file to go stale.
    """
    DAILY_ROOT.mkdir(parents=True, exist_ok=True)
    days_fetched = 0
    days_skipped = 0
    total_articles = 0
    day = start_date
    days_requested = (end_date - start_date).days + 1
    while day <= end_date:
        path = daily_packet_path(day)
        if resume and path.exists():
            days_skipped += 1
            day += timedelta(days=1)
            continue
        frame = collect_day(day, historical=True, session=session)
        frame.to_parquet(path, index=False)
        days_fetched += 1
        total_articles += len(frame)
        if progress is not None:
            progress(day, len(frame))
        day += timedelta(days=1)
    return HistoricalCollectionSummary(
        days_requested=days_requested,
        days_fetched=days_fetched,
        days_skipped_already_done=days_skipped,
        total_articles=total_articles,
    )


def consolidate_year(year: int) -> Path:
    """Concatenate every collected day in ``year`` into one
    ``{year}.parquet``, deduplicated by ``id`` (keep last -- a forward
    re-fetch of an already-collected recent day may see a provider-side
    update)."""
    NEWS_PACKETS_ROOT.mkdir(parents=True, exist_ok=True)
    day_paths = sorted(DAILY_ROOT.glob(f"{year}-*.parquet"))
    frames = [pd.read_parquet(path) for path in day_paths]
    combined = (
        pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=PACKET_COLUMNS)
    )
    if not combined.empty:
        combined = combined.sort_values(["created_at", "id"]).drop_duplicates(
            subset=["id"], keep="last"
        )
    out_path = NEWS_PACKETS_ROOT / f"{year}.parquet"
    combined.to_parquet(out_path, index=False)
    return out_path


def collect_forward(
    lookback_days: int = 3, *, session: Any = None, today: date | None = None
) -> HistoricalCollectionSummary:
    """Forward mode (plan section 4.1's ``--forward``): re-fetch the last
    ``lookback_days`` calendar days fresh every time (``historical=False``,
    so ``visible_at = fetched_at`` -- the only clean PIT evidence this
    pipeline produces), overwriting each day's ``_daily`` file (not
    resumable by design -- forward mode always wants the latest provider
    state for recent days, and dedup-by-id at consolidation time handles
    the overlap with whatever historical/earlier-forward data already
    exists for the same days).
    """
    DAILY_ROOT.mkdir(parents=True, exist_ok=True)
    today = today or datetime.now(UTC).date()
    total_articles = 0
    days_fetched = 0
    for offset in range(lookback_days):
        day = today - timedelta(days=offset)
        frame = collect_day(day, historical=False, session=session)
        frame.to_parquet(daily_packet_path(day), index=False)
        days_fetched += 1
        total_articles += len(frame)
    return HistoricalCollectionSummary(
        days_requested=lookback_days,
        days_fetched=days_fetched,
        days_skipped_already_done=0,
        total_articles=total_articles,
    )
