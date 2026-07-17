from __future__ import annotations

import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from open_composer.capabilities.registry import get_capability
from open_composer.config import ensure_dir, project_root, run_id
from open_composer.models.capability import Capability
from open_composer.models.event import EventRecord
from open_composer.storage import append_jsonl

SOURCE_TO_CAPABILITY = {
    "sec": "events.sec_filings",
    "sec_filings": "events.sec_filings",
    "fred": "macro.fred_series",
    "fred_series": "macro.fred_series",
    "alpha_vantage": "news.alpha_vantage",
    "alpha_vantage_news": "news.alpha_vantage",
    "gdelt": "news.gdelt",
}


def fetch_capability_events(
    source: str,
    root: Path | None = None,
    symbols: list[str] | None = None,
    offline: bool = True,
    limit: int | None = None,
    time_from: str | None = None,
    time_to: str | None = None,
    sort: str | None = None,
) -> list[EventRecord]:
    base = root or project_root()
    capability_id = SOURCE_TO_CAPABILITY.get(source, source)
    capability = get_capability(capability_id, base)
    events = (
        _load_fixture_events(base / capability.fixture)
        if offline
        else _fetch_live_events(
            capability,
            symbols,
            limit=limit,
            time_from=time_from,
            time_to=time_to,
            sort=sort,
        )
    )
    selected = _filter_symbols(events, symbols)
    destination = _destination_path(base, capability.kind, capability.provider)
    append_jsonl(destination, selected)
    append_jsonl(base / "event_logs" / f"{destination.stem}.jsonl", selected)
    return selected


def _fetch_live_events(
    capability: Capability,
    symbols: list[str] | None,
    *,
    limit: int | None = None,
    time_from: str | None = None,
    time_to: str | None = None,
    sort: str | None = None,
) -> list[EventRecord]:
    selected_symbols = symbols or ["QQQ"]
    if capability.id == "events.sec_filings":
        return _fetch_sec_filings(selected_symbols)
    if capability.id == "macro.fred_series":
        return _fetch_fred_series(["DGS10", "FEDFUNDS"])
    if capability.id == "news.alpha_vantage":
        return _fetch_alpha_vantage_news(
            selected_symbols,
            limit=limit,
            time_from=time_from,
            time_to=time_to,
            sort=sort,
        )
    if capability.id == "news.gdelt":
        return _fetch_gdelt_news(selected_symbols)
    raise NotImplementedError(f"live fetch is not implemented for {capability.id}")


def _load_fixture_events(path: Path) -> list[EventRecord]:
    events: list[EventRecord] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                event = EventRecord.model_validate(json.loads(line))
                events.append(event.model_copy(update={"acquisition_mode": "fixture_replay"}))
    return _dedupe_events(events)


def _filter_symbols(events: list[EventRecord], symbols: list[str] | None) -> list[EventRecord]:
    if not symbols:
        return events
    selected = {symbol.upper() for symbol in symbols}
    macro_symbols = {"FED", "DGS10", "FEDFUNDS", "CPIAUCSL", "UNRATE"}
    return [event for event in events if event.symbol in selected or event.symbol in macro_symbols]


def _dedupe_events(events: list[EventRecord]) -> list[EventRecord]:
    seen: set[str] = set()
    output: list[EventRecord] = []
    for event in sorted(events, key=lambda item: item.published_at):
        if event.dedupe_key in seen:
            continue
        seen.add(event.dedupe_key)
        output.append(event)
    return output


def _destination_path(root: Path, kind: str, provider: str) -> Path:
    current_run = run_id(provider)
    if kind == "macro":
        path = root / "data" / "raw" / "macro" / f"{current_run}.jsonl"
    else:
        path = root / "data" / "raw" / "events" / provider / f"{current_run}.jsonl"
    ensure_dir(path.parent)
    return path


def _http_get_json(url: str, params: dict[str, Any] | None = None) -> dict[str, Any] | list[Any]:
    import httpx

    headers = {"User-Agent": _sec_user_agent()} if "sec.gov" in url else {}
    response = httpx.get(url, params=params, headers=headers, timeout=20)
    response.raise_for_status()
    return response.json()


def _fetch_sec_filings(symbols: list[str]) -> list[EventRecord]:
    _sec_user_agent()
    tickers_payload = _http_get_json("https://www.sec.gov/files/company_tickers.json")
    if not isinstance(tickers_payload, dict):
        return []
    symbol_to_cik = {
        str(item["ticker"]).upper(): str(item["cik_str"]).zfill(10)
        for item in tickers_payload.values()
        if isinstance(item, dict) and "ticker" in item and "cik_str" in item
    }
    records: list[EventRecord] = []
    for symbol in symbols:
        cik = symbol_to_cik.get(symbol.upper())
        if not cik:
            continue
        payload = _http_get_json(f"https://data.sec.gov/submissions/CIK{cik}.json")
        if not isinstance(payload, dict):
            continue
        filings = payload.get("filings", {}).get("recent", {})
        forms = filings.get("form", [])[:10]
        accession_numbers = filings.get("accessionNumber", [])[:10]
        filing_dates = filings.get("filingDate", [])[:10]
        primary_docs = filings.get("primaryDocument", [])[:10]
        acceptance_datetimes = filings.get("acceptanceDateTime", [])[:10]
        fetched_at = datetime.now(UTC)
        for index, (form, accession, filing_date, primary_doc) in enumerate(
            zip(forms, accession_numbers, filing_dates, primary_docs, strict=False)
        ):
            acceptance_raw = (
                acceptance_datetimes[index] if index < len(acceptance_datetimes) else None
            )
            acceptance_at = _parse_optional_datetime(acceptance_raw)
            published_at = acceptance_at or fetched_at
            visible_at = max(published_at, fetched_at)
            accession_path = str(accession).replace("-", "")
            url = (
                f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession_path}/{primary_doc}"
            )
            records.append(
                EventRecord(
                    id=f"sec-{symbol.lower()}-{accession}",
                    source="sec",
                    symbol=symbol.upper(),
                    published_at=published_at,
                    fetched_at=fetched_at,
                    visible_at=visible_at,
                    first_seen_at=fetched_at,
                    accepted_at=acceptance_at,
                    revision="as_filed_accession",
                    revision_id=str(accession),
                    version_id=str(accession),
                    rights="source_document_rights_unverified",
                    rights_scope="public_access_reuse_unverified",
                    availability_quality=(
                        "fetch_time_with_official_acceptance"
                        if acceptance_at is not None
                        else "fetch_time_first_seen"
                    ),
                    availability_basis="collector_first_seen_and_sec_acceptance",
                    acquisition_mode="live_api",
                    event_type=str(form),
                    title=f"{symbol.upper()} SEC filing {form}",
                    summary=f"SEC EDGAR filing {form} for {symbol.upper()} filed on {filing_date}.",
                    url=url,
                    sentiment="neutral",
                    relevance_score=0.75,
                    dedupe_key=f"sec:{symbol.upper()}:{accession}",
                    raw={
                        "accession": accession,
                        "form": form,
                        "filing_date": filing_date,
                        "acceptance_datetime": acceptance_raw,
                    },
                )
            )
    return _dedupe_events(records)


def _fetch_fred_series(series_ids: list[str]) -> list[EventRecord]:
    api_key = os.getenv("FRED_API_KEY")
    if not api_key:
        raise RuntimeError("FRED_API_KEY is required for live FRED fetch")
    records: list[EventRecord] = []
    for series_id in series_ids:
        payload = _http_get_json(
            "https://api.stlouisfed.org/fred/series/observations",
            {
                "series_id": series_id,
                "api_key": api_key,
                "file_type": "json",
                "sort_order": "desc",
                "limit": 5,
            },
        )
        if not isinstance(payload, dict):
            continue
        fetched_at = datetime.now(UTC)
        for observation in payload.get("observations", []):
            date_value = observation.get("date")
            value = observation.get("value")
            if not date_value or value in {None, "."}:
                continue
            records.append(
                EventRecord(
                    id=f"fred-{series_id}-{date_value}",
                    source="fred",
                    symbol=series_id,
                    published_at=fetched_at,
                    fetched_at=fetched_at,
                    visible_at=fetched_at,
                    first_seen_at=fetched_at,
                    revision="latest_snapshot_non_vintage",
                    revision_id="unknown_latest_snapshot",
                    version_id="unknown_latest_snapshot",
                    rights="underlying_series_terms_unverified",
                    rights_scope="internal_replay_unverified",
                    availability_quality="forward_only_fetch_time",
                    availability_basis="collector_first_seen",
                    acquisition_mode="live_api_forward_only",
                    event_type="macro_series_observation",
                    title=f"{series_id} observation",
                    summary=f"{series_id} observation value {value}.",
                    url=f"https://fred.stlouisfed.org/series/{series_id}",
                    sentiment="neutral",
                    relevance_score=0.8,
                    dedupe_key=f"fred:{series_id}:{date_value}",
                    raw=observation,
                    value=float(value),
                )
            )
    return _dedupe_events(records)


def _fetch_alpha_vantage_news(
    symbols: list[str],
    *,
    limit: int | None = None,
    time_from: str | None = None,
    time_to: str | None = None,
    sort: str | None = None,
) -> list[EventRecord]:
    api_key = os.getenv("ALPHA_VANTAGE_API_KEY")
    if not api_key:
        raise RuntimeError("ALPHA_VANTAGE_API_KEY is required for live Alpha Vantage fetch")
    records: list[EventRecord] = []
    for requested_symbol in symbols:
        payload = _fetch_alpha_vantage_news_payload(
            api_key=api_key,
            symbol=requested_symbol.upper(),
            limit=limit,
            time_from=time_from,
            time_to=time_to,
            sort=sort,
        )
        records.extend(
            _alpha_vantage_records_from_payload(
                payload=payload,
                symbols=[requested_symbol.upper()],
            )
        )
    return _dedupe_events(records)


def _fetch_alpha_vantage_news_payload(
    *,
    api_key: str,
    symbol: str,
    limit: int | None,
    time_from: str | None,
    time_to: str | None,
    sort: str | None,
) -> dict[str, Any] | list[Any]:
    params: dict[str, Any] = {
        "function": "NEWS_SENTIMENT",
        "tickers": symbol,
        "apikey": api_key,
        "limit": limit or 50,
    }
    if time_from:
        params["time_from"] = time_from
    if time_to:
        params["time_to"] = time_to
    if sort:
        params["sort"] = sort
    return _http_get_json("https://www.alphavantage.co/query", params)


def _alpha_vantage_records_from_payload(
    *,
    payload: dict[str, Any] | list[Any],
    symbols: list[str],
) -> list[EventRecord]:
    if not isinstance(payload, dict):
        return []
    if payload.get("Information") or payload.get("Note") or payload.get("Error Message"):
        message = payload.get("Information") or payload.get("Note") or payload.get("Error Message")
        raise RuntimeError(f"Alpha Vantage NEWS_SENTIMENT response: {message}")
    records: list[EventRecord] = []
    for item in payload.get("feed", []):
        time_published = str(item.get("time_published", ""))
        if not time_published:
            continue
        published = datetime.strptime(time_published[:14], "%Y%m%dT%H%M%S").replace(tzinfo=UTC)
        ticker_sentiment = item.get("ticker_sentiment", [])
        fetched_at = datetime.now(UTC)
        visible = _alpha_vantage_visible_at(item, published, fetched_at)
        for symbol, relevance, sentiment in _alpha_vantage_symbol_rows(
            symbols,
            ticker_sentiment,
            item,
        ):
            records.append(
                EventRecord(
                    id=f"alpha-vantage-{symbol.lower()}-{time_published}",
                    source="alpha_vantage",
                    symbol=symbol,
                    published_at=published,
                    fetched_at=fetched_at,
                    visible_at=visible,
                    first_seen_at=fetched_at,
                    revision="provider_current_snapshot",
                    revision_id="provider_current_snapshot",
                    version_id=str(item.get("url") or time_published),
                    rights="provider_and_original_source_terms_unverified",
                    rights_scope="internal_model_input_unverified",
                    availability_quality=(
                        "provider_first_seen_timestamp"
                        if visible != fetched_at
                        else "fetch_time_first_seen"
                    ),
                    availability_basis="collector_first_seen",
                    acquisition_mode="live_api",
                    event_type="news_sentiment",
                    title=str(item.get("title", "")),
                    summary=str(item.get("summary", "")),
                    url=str(item.get("url", "")),
                    sentiment=sentiment,
                    relevance_score=relevance,
                    dedupe_key=f"alpha_vantage:{symbol}:{item.get('url', time_published)}",
                    raw=item,
                )
            )
    return _dedupe_events(records)


def _fetch_gdelt_news(symbols: list[str]) -> list[EventRecord]:
    query = " OR ".join(symbol.upper() for symbol in symbols)
    payload = _http_get_json(
        "https://api.gdeltproject.org/api/v2/doc/doc",
        {"query": query, "mode": "ArtList", "format": "json", "maxrecords": 50},
    )
    if not isinstance(payload, dict):
        return []
    records: list[EventRecord] = []
    for article in payload.get("articles", []):
        published_raw = article.get("seendate") or article.get("datetime")
        if not published_raw:
            continue
        published = _parse_gdelt_datetime(str(published_raw))
        title = str(article.get("title", ""))
        url = str(article.get("url", ""))
        symbol = _first_symbol_in_text(symbols, f"{title} {article.get('sourcecountry', '')}")
        fetched_at = datetime.now(UTC)
        records.append(
            EventRecord(
                id=f"gdelt-{symbol.lower()}-{abs(hash(url or title))}",
                source="gdelt",
                symbol=symbol,
                published_at=published,
                fetched_at=fetched_at,
                visible_at=fetched_at,
                first_seen_at=fetched_at,
                revision="provider_current_snapshot",
                revision_id="provider_current_snapshot",
                version_id=url or title,
                rights="linked_article_rights_unverified",
                rights_scope="metadata_only_until_verified",
                availability_quality="fetch_time_first_seen",
                availability_basis="collector_first_seen",
                acquisition_mode="live_api",
                event_type="broad_news",
                title=title,
                summary=str(article.get("domain", "")),
                url=url,
                sentiment="unknown",
                relevance_score=0.55,
                dedupe_key=f"gdelt:{symbol}:{url or title}",
                raw=article,
            )
        )
    return _dedupe_events(records)


def _best_news_symbol(symbols: list[str], ticker_sentiment: list[dict[str, Any]]) -> str:
    ranked = sorted(
        ticker_sentiment,
        key=lambda item: float(item.get("relevance_score", 0) or 0),
        reverse=True,
    )
    for item in ranked:
        ticker = str(item.get("ticker", "")).upper()
        if ticker in {symbol.upper() for symbol in symbols}:
            return ticker
    return symbols[0].upper()


def _ticker_relevance(symbol: str, ticker_sentiment: list[dict[str, Any]]) -> float:
    for item in ticker_sentiment:
        if str(item.get("ticker", "")).upper() == symbol.upper():
            return float(item.get("relevance_score", 0) or 0)
    return 0.5


def _alpha_vantage_symbol_rows(
    symbols: list[str],
    ticker_sentiment: list[dict[str, Any]],
    item: dict[str, Any],
) -> list[tuple[str, float, str]]:
    selected = {symbol.upper() for symbol in symbols}
    rows: list[tuple[str, float, str]] = []
    for ticker_row in ticker_sentiment:
        ticker = str(ticker_row.get("ticker", "")).upper()
        if ticker not in selected:
            continue
        relevance = float(ticker_row.get("relevance_score", 0.0) or 0.0)
        sentiment = _normalize_sentiment(
            ticker_row.get("ticker_sentiment_label") or item.get("overall_sentiment_label")
        )
        rows.append((ticker, relevance, sentiment))
    if rows:
        return rows
    symbol = _best_news_symbol(symbols, ticker_sentiment)
    return [
        (
            symbol,
            _ticker_relevance(symbol, ticker_sentiment),
            _normalize_sentiment(item.get("overall_sentiment_label")),
        )
    ]


def _normalize_sentiment(value: Any) -> str:
    normalized = str(value or "unknown").lower()
    if "bull" in normalized or "positive" in normalized:
        return "positive"
    if "bear" in normalized or "negative" in normalized:
        return "negative"
    if "neutral" in normalized:
        return "neutral"
    return "unknown"


def _alpha_vantage_visible_at(
    item: dict[str, Any], published_at: datetime, fetched_at: datetime
) -> datetime:
    provider_visible_at = _parse_optional_datetime(
        item.get("visible_at") or item.get("first_seen_at")
    )
    return max(published_at, fetched_at, provider_visible_at or fetched_at)


def _sec_user_agent() -> str:
    user_agent = os.getenv("SEC_USER_AGENT", "").strip()
    if not user_agent or re.search(r"\S+@\S+\.\S+", user_agent) is None:
        raise RuntimeError("SEC_USER_AGENT with a contact email is required for live SEC fetches")
    return user_agent


def _parse_optional_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        if len(value) >= 15 and value[:8].isdigit() and "T" in value:
            return datetime.strptime(value[:14], "%Y%m%dT%H%M%S").replace(tzinfo=UTC)
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _first_symbol_in_text(symbols: list[str], text: str) -> str:
    upper_text = text.upper()
    for symbol in symbols:
        if symbol.upper() in upper_text:
            return symbol.upper()
    return symbols[0].upper()


def _parse_gdelt_datetime(value: str) -> datetime:
    normalized = value.replace("Z", "")
    if len(normalized) >= 14 and normalized[:8].isdigit():
        return datetime.strptime(normalized[:14], "%Y%m%d%H%M%S").replace(tzinfo=UTC)
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def event_record_from_live_payload(source: str, symbol: str, payload: dict) -> EventRecord:
    fetched_at = datetime.now(UTC)
    published = payload.get("published_at") or payload.get("time_published") or fetched_at
    if isinstance(published, str):
        published_at = datetime.fromisoformat(published.replace("Z", "+00:00"))
    else:
        published_at = published
    provider_visible_at = _parse_optional_datetime(
        payload.get("visible_at") or payload.get("first_seen_at")
    )
    accepted_at = _parse_optional_datetime(payload.get("accepted_at"))
    visible_at = max(
        value
        for value in (published_at, fetched_at, provider_visible_at, accepted_at)
        if value is not None
    )
    title = str(payload.get("title", "untitled event"))
    return EventRecord(
        id=str(payload.get("id", f"{source}:{symbol}:{published_at.isoformat()}")),
        source=source,
        symbol=symbol,
        published_at=published_at,
        fetched_at=fetched_at,
        visible_at=visible_at,
        first_seen_at=fetched_at,
        accepted_at=accepted_at,
        vintage_at=_parse_optional_datetime(payload.get("vintage_at")),
        revision=str(payload.get("revision", "unknown")),
        revision_id=str(payload.get("revision_id", "unknown")),
        version_id=str(payload.get("version_id", "unknown")),
        rights=str(payload.get("rights", "unknown")),
        rights_scope=str(payload.get("rights_scope", "unknown")),
        availability_quality=str(payload.get("availability_quality", "fetch_time_first_seen")),
        availability_basis=str(payload.get("availability_basis", "collector_first_seen")),
        acquisition_mode=str(payload.get("acquisition_mode", "live_api")),
        event_type=str(payload.get("event_type", source)),
        title=title,
        summary=str(payload.get("summary", "")),
        url=str(payload.get("url", "")),
        sentiment=str(payload.get("sentiment", "unknown")),
        relevance_score=float(payload.get("relevance_score", 0.0)),
        dedupe_key=str(
            payload.get("dedupe_key", f"{source}:{symbol}:{published_at.isoformat()}:{title}")
        ),
        raw=payload,
    )
