"""T2 (plan-earnings-text-forward-test-2026-09-22): earnings-text tone/guidance
scorer.

Card: ``docs/plan-earnings-text-forward-test-2026-09-22.zh.md`` section 1 (row
T2) / section 3 (frozen prompt + entity neutralisation) / section 6 (model
endpoint, credentials, rate-limit rules); ``docs/plan-strategy-factory-2026-09-22.zh.md``
section 7 (endpoint + 5-hour rate-limit rules).

What this does
--------------
Reads earnings-release plain text (either from a T1 event table,
``data/features/earnings_events/{year}.parquet``, or from an explicit list of
raw text files), strips identifying entities (company name, ticker, month
names, four-digit years, dollar amounts) so the model cannot lean on training
recall of a specific company/period, sends the frozen prompt (section 3) to
the user's OpenAI-compatible endpoint, parses ``{tone, guidance, rationale}``
out of the reply, and writes one row per event to
``data/features/earnings_text_scores/{year}.parquet``.

Hard constraints (plan doc header, repeated here because this script is the
one place they actually bite)
------------------------------
* Credentials live only in ``/root/.config/open-composer/text-scorer.env``
  (mode 600, outside the repo). They are read once into memory and used only
  as the Authorization header of the chat-completions call. Nothing in this
  module ever prints, logs, or writes the API key or the parsed credential
  values; log lines record only the model name and the frozen prompt's
  SHA-256, per plan-strategy-factory section 7.
* This script does not spend Claude Code subscription tokens on bulk
  scoring -- it calls the user-provided endpoint directly over HTTP.
* 5-hour rolling quota: every call's ``usage`` is recorded; an HTTP 429, or
  any response body mentioning "limit"/"quota", stops the batch immediately,
  writes ``data/features/earnings_text_scores/next_try_at.json``, and exits
  0 (not an error -- this is the designed backpressure behaviour). The
  output parquet is checkpointed every 100 scored events so a stopped batch
  loses at most 99 events of work.
* Resume is idempotent: an accession already present in the target output
  partition is skipped without a network call.

Usage
-----
Dry run (no network calls; prints up to 3 neutralised samples)::

    ./.venv/bin/python scripts/score_earnings_text.py --year 2024 --dry-run

Pilot on the 30-row T1 table::

    ./scripts/run_capped.sh --mem 1.8G -- ./.venv/bin/python \\
        scripts/score_earnings_text.py --year 2024 --limit 30

Pilot directly against raw text files (no event-table metadata; ticker and
acceptance_utc are unknown so they are left null and only ticker/month/year/
dollar-amount neutralisation applies, not the company-name pass)::

    ./scripts/run_capped.sh --mem 1.8G -- ./.venv/bin/python \\
        scripts/score_earnings_text.py --text-paths data/raw/earnings_text/*/*.txt --limit 200

Determinism check (scores the same events twice, logs |delta(tone)|)::

    ./.venv/bin/python scripts/score_earnings_text.py --year 2024 --limit 5 --determinism-check
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import re
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]

EVENTS_DIR = ROOT / "data" / "features" / "earnings_events"
OUT_DIR = ROOT / "data" / "features" / "earnings_text_scores"
NEXT_TRY_PATH = OUT_DIR / "next_try_at.json"
LOG_PATH = ROOT / "logs" / "score_earnings_text.log"

#: Credentials file per plan section 6. Outside the repo, mode 600. Parsed
#: as plain KEY=VALUE lines -- no SDK, no dotenv dependency needed for three
#: variables, and this keeps the parse path auditable in one place.
CREDENTIALS_PATH = Path("/root/.config/open-composer/text-scorer.env")
REQUIRED_CREDENTIAL_KEYS = (
    "OC_TEXT_SCORER_BASE_URL",
    "OC_TEXT_SCORER_API_KEY",
    "OC_TEXT_SCORER_MODEL",
)

CHAT_TEMPERATURE = 0
CHAT_MAX_TOKENS = 200
HTTP_TIMEOUT_SECONDS = 60.0

#: ~12k tokens by characters, at a ~4 chars/token heuristic (plan section 3).
MAX_TEXT_CHARS = 48_000

CHECKPOINT_EVERY = 100
DEFAULT_RETRY_MINUTES = 30
DETERMINISM_THRESHOLD = 0.1

LOG = logging.getLogger("score_earnings_text")


def _setup_logging() -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.FileHandler(LOG_PATH), logging.StreamHandler(sys.stdout)],
    )


# --------------------------------------------------------------------------
# Frozen prompt (plan section 3) -- do not edit in place; a wording change
# is a new version and must get a new PROMPT_SHA256.
# --------------------------------------------------------------------------

SYSTEM_PROMPT = (
    "你是财报文本分析员。只依据给定文本判断管理层对未来经营的语气，"
    "不要猜公司身份，不要引用外部知识。"
)
_USER_PROMPT_HEADER = "文本（已去掉公司名、代码、日期、绝对金额）："
_USER_PROMPT_FOOTER = (
    "输出 JSON：`tone`（−1 到 1，负=悲观）、`guidance`（up/same/down/none）、"
    "`rationale`（≤ 30 字）。"
)
_TEXT_PLACEHOLDER = "{{TEXT}}"
USER_PROMPT_TEMPLATE = f"{_USER_PROMPT_HEADER}\n{_TEXT_PLACEHOLDER}\n\n{_USER_PROMPT_FOOTER}"

#: Hash of the *template* (system prompt + user template with the text
#: placeholder, not any one filled-in message) -- constant across every row,
#: per T2's "prompt_sha256 written into every row" requirement.
_PROMPT_TEMPLATE_FOR_HASH = json.dumps(
    {"system": SYSTEM_PROMPT, "user_template": USER_PROMPT_TEMPLATE},
    ensure_ascii=False,
    sort_keys=True,
)
PROMPT_SHA256 = hashlib.sha256(_PROMPT_TEMPLATE_FOR_HASH.encode("utf-8")).hexdigest()

_RETRY_INSTRUCTION = "只返回合法 JSON，不要包含解释、Markdown 代码块或其他文字。"


def build_user_message(neutralised_text: str) -> str:
    return USER_PROMPT_TEMPLATE.replace(_TEXT_PLACEHOLDER, neutralised_text)


def build_messages(neutralised_text: str) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": build_user_message(neutralised_text)},
    ]


def build_retry_messages(neutralised_text: str, prior_reply: str) -> list[dict[str, str]]:
    messages = build_messages(neutralised_text)
    messages.append({"role": "assistant", "content": prior_reply})
    messages.append({"role": "user", "content": _RETRY_INSTRUCTION})
    return messages


# --------------------------------------------------------------------------
# Entity neutralisation (plan section 3): company name, ticker, month
# names, four-digit years, dollar amounts -> placeholders.
# --------------------------------------------------------------------------

_COMPANY_SUFFIX_RE = re.compile(
    r",?\s+(?:Inc|Incorporated|Corp|Corporation|Co|Company|Companies|plc|Ltd|Limited|"
    r"LLC|L\.P\.|LP|Group|Holdings?)\.?\s*$",
    re.IGNORECASE,
)
_MONTH_RE = re.compile(
    r"\b(January|February|March|April|May|June|July|August|September|October|November|"
    r"December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sept|Sep|Oct|Nov|Dec)\b",
    re.IGNORECASE,
)
_YEAR_RE = re.compile(r"\b(?:18|19|20)\d{2}\b")
_DOLLAR_RE = re.compile(
    r"\$\s?\d[\d,]*(?:\.\d+)?(?:\s?(?:billion|million|thousand|bn|mn|k))?",
    re.IGNORECASE,
)


def _company_name_variants(company_name: str) -> list[str]:
    """The full registered name plus its core name with trailing corporate
    suffixes (Inc/Corp/Company/...) stripped, longest first, so a press
    release that drops the suffix ("Agilent" reports for "Agilent
    Technologies, Inc.") still gets neutralised."""

    variants = {company_name.strip()}
    core = company_name.strip()
    for _ in range(3):
        stripped = _COMPANY_SUFFIX_RE.sub("", core).strip().rstrip(",").strip()
        if not stripped or stripped == core:
            break
        core = stripped
        variants.add(core)
    return sorted((v for v in variants if v), key=len, reverse=True)


def neutralise_text(
    text: str,
    *,
    company_name: str | None,
    ticker: str | None,
    max_chars: int = MAX_TEXT_CHARS,
) -> str:
    result = text
    if company_name:
        for variant in _company_name_variants(company_name):
            if len(variant) < 3:  # too short to safely blanket-replace
                continue
            # (?<!\w)/(?!\w) rather than \b: a short registrant name like
            # "Alcoa Corp" is a *prefix* of "Alcoa Corporation" as it
            # actually appears in press-release text, and \b after the
            # trailing "p" would still match there (word->word is not a
            # boundary either way) -- leaving a leaked "[COMPANY]oration".
            # These lookarounds require the character straddling each edge
            # to not be a word character, so a longer word continuing past
            # the variant blocks the match instead of truncating it.
            pattern = re.compile(r"(?<!\w)" + re.escape(variant) + r"(?!\w)", re.IGNORECASE)
            result = pattern.sub("[COMPANY]", result)
    if ticker and ticker.strip():
        # Case-sensitive and word-bounded: tickers are conventionally
        # rendered upper-case in filings ("NASDAQ: MSFT"); a case-insensitive
        # match on a short ticker (e.g. "A") would blanket-replace common
        # English words instead.
        result = re.compile(r"\b" + re.escape(ticker.strip()) + r"\b").sub("[TICKER]", result)
    result = _DOLLAR_RE.sub("[AMOUNT]", result)
    result = _MONTH_RE.sub("[MONTH]", result)
    result = _YEAR_RE.sub("[YEAR]", result)
    if len(result) > max_chars:
        result = result[:max_chars]
    return result


def sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------
# Reply parsing / validation
# --------------------------------------------------------------------------

_VALID_GUIDANCE = {"up", "same", "down", "none"}
_JSON_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)
_CODE_FENCE_RE = re.compile(r"^```[a-zA-Z]*\n?|```\s*$")


def _extract_json_object(content: str) -> dict | None:
    stripped = _CODE_FENCE_RE.sub("", content.strip()).strip()
    try:
        return json.loads(stripped)
    except (json.JSONDecodeError, TypeError):
        pass
    match = _JSON_OBJECT_RE.search(stripped)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return None


def validate_score_obj(obj: object) -> dict | None:
    if not isinstance(obj, dict):
        return None
    try:
        tone = float(obj.get("tone"))
    except (TypeError, ValueError):
        return None
    tone = max(-1.0, min(1.0, tone))
    guidance = obj.get("guidance")
    if not isinstance(guidance, str) or guidance.strip().lower() not in _VALID_GUIDANCE:
        return None
    rationale = obj.get("rationale")
    if rationale is not None and not isinstance(rationale, str):
        rationale = str(rationale)
    return {
        "tone": tone,
        "guidance": guidance.strip().lower(),
        "rationale": (rationale or "")[:200],
    }


def parse_score_reply(content: str) -> dict | None:
    obj = _extract_json_object(content)
    if obj is None:
        return None
    return validate_score_obj(obj)


# --------------------------------------------------------------------------
# HTTP call abstraction (plain requests; injectable for tests)
# --------------------------------------------------------------------------


@dataclass
class ChatCallResult:
    status_code: int
    content_text: str | None
    prompt_tokens: int = 0
    completion_tokens: int = 0
    raw_body: str = ""
    headers: dict[str, str] = field(default_factory=dict)
    error: str | None = None


ChatCallFn = Callable[[list[dict[str, str]]], ChatCallResult]

_LIMIT_KEYWORDS_RE = re.compile(r"limit|quota", re.IGNORECASE)


def is_rate_limited(result: ChatCallResult) -> bool:
    if result.status_code == 429:
        return True
    return bool(result.raw_body) and bool(_LIMIT_KEYWORDS_RE.search(result.raw_body))


def make_requests_chat_call_fn(
    *, base_url: str, api_key: str, model: str, timeout: float = HTTP_TIMEOUT_SECONDS
) -> ChatCallFn:
    """A ``ChatCallFn`` backed by plain ``requests`` against an
    OpenAI-compatible ``POST {base_url}/chat/completions``. ``api_key`` is
    closed over here and never logged or returned."""

    import requests

    url = base_url.rstrip("/") + "/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    def call(messages: list[dict[str, str]]) -> ChatCallResult:
        payload = {
            "model": model,
            "messages": messages,
            "temperature": CHAT_TEMPERATURE,
            "max_tokens": CHAT_MAX_TOKENS,
        }
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=timeout)
        except requests.RequestException as exc:
            return ChatCallResult(status_code=0, content_text=None, error=str(exc))
        content_text = None
        prompt_tokens = 0
        completion_tokens = 0
        if response.status_code == 200:
            try:
                data = response.json()
                content_text = data["choices"][0]["message"]["content"]
                usage = data.get("usage") or {}
                prompt_tokens = int(usage.get("prompt_tokens") or 0)
                completion_tokens = int(usage.get("completion_tokens") or 0)
            except (ValueError, KeyError, IndexError, TypeError):
                content_text = None
        return ChatCallResult(
            status_code=response.status_code,
            content_text=content_text,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            raw_body=response.text,
            headers=dict(response.headers),
        )

    return call


def compute_next_try_at(result: ChatCallResult, *, now: datetime) -> datetime:
    retry_after = result.headers.get("Retry-After") or result.headers.get("retry-after")
    if retry_after:
        retry_after = retry_after.strip()
        if retry_after.isdigit():
            return now + timedelta(seconds=int(retry_after))
        try:
            parsed = parsedate_to_datetime(retry_after)
        except (TypeError, ValueError, IndexError):
            parsed = None
        if parsed is not None:
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=UTC)
            return parsed.astimezone(UTC)
    return now + timedelta(minutes=DEFAULT_RETRY_MINUTES)


class RateLimitStop(Exception):
    def __init__(self, next_try_at: datetime, reason: str) -> None:
        super().__init__(reason)
        self.next_try_at = next_try_at
        self.reason = reason


def _raise_rate_limit_stop(result: ChatCallResult) -> None:
    reason = (
        f"HTTP {result.status_code}"
        if result.status_code == 429
        else "quota/limit in response body"
    )
    raise RateLimitStop(compute_next_try_at(result, now=datetime.now(UTC)), reason)


# --------------------------------------------------------------------------
# Per-event scoring
# --------------------------------------------------------------------------


def score_text(
    *,
    raw_text: str,
    company_name: str | None,
    ticker: str | None,
    call_fn: ChatCallFn,
    model: str,
) -> dict:
    """Neutralise, call the endpoint (with one JSON-only retry on parse
    failure), and return the scoring fields (``tone``/``guidance``/
    ``rationale``/``model``/hashes/token counts/``status``). Raises
    :class:`RateLimitStop` if either call looks rate-limited; the caller is
    responsible for stopping the whole batch when that happens."""

    neutral_text = neutralise_text(raw_text, company_name=company_name, ticker=ticker)
    neutral_sha = sha256_hex(neutral_text)
    result = call_fn(build_messages(neutral_text))
    if is_rate_limited(result):
        _raise_rate_limit_stop(result)

    prompt_tokens = result.prompt_tokens
    completion_tokens = result.completion_tokens
    parsed = parse_score_reply(result.content_text) if result.content_text else None
    status = "ok"

    if result.status_code != 200 or result.content_text is None:
        status = "http_error"
    elif parsed is None:
        retry_result = call_fn(build_retry_messages(neutral_text, result.content_text))
        if is_rate_limited(retry_result):
            _raise_rate_limit_stop(retry_result)
        prompt_tokens += retry_result.prompt_tokens
        completion_tokens += retry_result.completion_tokens
        if retry_result.status_code == 200 and retry_result.content_text:
            parsed = parse_score_reply(retry_result.content_text)
        status = "ok" if parsed is not None else "parse_error"

    return {
        "tone": parsed["tone"] if parsed else None,
        "guidance": parsed["guidance"] if parsed else None,
        "rationale": parsed["rationale"] if parsed else None,
        "model": model,
        "prompt_sha256": PROMPT_SHA256,
        "neutralised_text_sha256": neutral_sha,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "status": status,
    }


# --------------------------------------------------------------------------
# Event loading
# --------------------------------------------------------------------------


@dataclass
class EventInput:
    accession: str
    cik: str | None
    ticker: str | None
    company_name: str | None
    acceptance_utc: str | None
    text_path: Path


def _clean_opt_str(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, float) and pd.isna(value):
        return None
    text = str(value).strip()
    return text or None


def load_events_from_events_parquet(path: Path, *, limit: int | None) -> list[EventInput]:
    df = pd.read_parquet(
        path, columns=["cik", "ticker", "company_name", "accession", "acceptance_utc", "text_path"]
    )
    events: list[EventInput] = []
    for row in df.itertuples(index=False):
        text_path_raw = _clean_opt_str(row.text_path)
        if text_path_raw is None:
            continue
        text_path = Path(text_path_raw)
        if not text_path.is_absolute():
            text_path = ROOT / text_path
        if not text_path.exists():
            continue
        events.append(
            EventInput(
                accession=str(row.accession),
                cik=_clean_opt_str(row.cik),
                ticker=_clean_opt_str(row.ticker),
                company_name=_clean_opt_str(row.company_name),
                acceptance_utc=_clean_opt_str(row.acceptance_utc),
                text_path=text_path,
            )
        )
        if limit is not None and len(events) >= limit:
            break
    return events


#: Raw text cache layout is ``data/raw/earnings_text/{cik}/{accession}.txt``
#: (see scripts/build_earnings_events.py); parse both back out of the path.
_TEXT_PATH_RE = re.compile(r"(?P<cik>[^/\\]+)[/\\](?P<accession>[^/\\]+)\.txt$")


def load_events_from_text_paths(paths: list[str], *, limit: int | None) -> list[EventInput]:
    events: list[EventInput] = []
    for raw in paths:
        candidate = Path(raw)
        if not candidate.exists():
            LOG.warning("skip missing text path: %s", candidate)
            continue
        match = _TEXT_PATH_RE.search(str(candidate))
        cik = match.group("cik") if match else None
        accession = match.group("accession") if match else candidate.stem
        events.append(
            EventInput(
                accession=accession,
                cik=cik,
                ticker=None,
                company_name=None,
                acceptance_utc=None,
                text_path=candidate,
            )
        )
        if limit is not None and len(events) >= limit:
            break
    return events


def output_partition_key(event: EventInput) -> str:
    if event.acceptance_utc:
        return event.acceptance_utc[:4]
    return "unknown"


# --------------------------------------------------------------------------
# Output: checkpoint / resume
# --------------------------------------------------------------------------

OUTPUT_COLUMNS = [
    "accession",
    "cik",
    "ticker",
    "acceptance_utc",
    "tone",
    "guidance",
    "rationale",
    "model",
    "prompt_sha256",
    "neutralised_text_sha256",
    "prompt_tokens",
    "completion_tokens",
    "scored_at",
    "status",
]


def flush_partition(partition_key: str, new_rows: list[dict]) -> int:
    if not new_rows:
        return 0
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / f"{partition_key}.parquet"
    new_df = pd.DataFrame(new_rows, columns=OUTPUT_COLUMNS)
    if out_path.exists():
        existing = pd.read_parquet(out_path)
        existing = existing[~existing["accession"].isin(new_df["accession"])]
        merged = pd.concat([existing, new_df], ignore_index=True)
    else:
        merged = new_df
    merged = merged.sort_values(["accession"]).reset_index(drop=True)
    tmp_path = out_path.with_suffix(".parquet.tmp")
    merged.to_parquet(tmp_path, index=False)
    tmp_path.replace(out_path)
    return len(new_df)


def load_already_scored(partition_keys: set[str]) -> set[str]:
    scored: set[str] = set()
    for key in partition_keys:
        path = OUT_DIR / f"{key}.parquet"
        if not path.exists():
            continue
        try:
            df = pd.read_parquet(path, columns=["accession"])
        except Exception as exc:  # pragma: no cover - corrupt/partial file
            LOG.warning("failed reading existing partition %s: %s", path, exc)
            continue
        scored.update(df["accession"].astype(str).tolist())
    return scored


def write_next_try_at(next_try_at: datetime, reason: str) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "next_try_at": next_try_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "reason": reason,
        "written_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    NEXT_TRY_PATH.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


# --------------------------------------------------------------------------
# Batch loop
# --------------------------------------------------------------------------


@dataclass
class BatchStats:
    processed: int = 0
    ok: int = 0
    parse_error: int = 0
    http_error: int = 0
    skipped_already_scored: int = 0
    skipped_no_text: int = 0
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
    stopped_for_rate_limit: bool = False

    def record(self, row: dict) -> None:
        self.processed += 1
        status = row["status"]
        if status == "ok":
            self.ok += 1
        elif status == "parse_error":
            self.parse_error += 1
        elif status == "http_error":
            self.http_error += 1
        self.total_prompt_tokens += row["prompt_tokens"]
        self.total_completion_tokens += row["completion_tokens"]


def _hour_bucket(ts: datetime) -> str:
    return ts.strftime("%Y-%m-%dT%HZ")


def run_batch(events: list[EventInput], call_fn: ChatCallFn, *, model: str) -> BatchStats:
    partition_keys = {output_partition_key(e) for e in events}
    already_scored = load_already_scored(partition_keys)
    stats = BatchStats()
    pending: dict[str, list[dict]] = {}
    token_hours: dict[str, dict[str, int]] = {}

    def flush_all() -> None:
        for key, rows in list(pending.items()):
            n = flush_partition(key, rows)
            if n:
                LOG.info("checkpoint: wrote %d rows -> %s.parquet", n, key)
            pending[key] = []

    for event in events:
        if event.accession in already_scored:
            stats.skipped_already_scored += 1
            continue
        try:
            raw_text = event.text_path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            LOG.warning("skip %s: cannot read %s (%s)", event.accession, event.text_path, exc)
            stats.skipped_no_text += 1
            continue

        try:
            result = score_text(
                raw_text=raw_text,
                company_name=event.company_name,
                ticker=event.ticker,
                call_fn=call_fn,
                model=model,
            )
        except RateLimitStop as stop:
            flush_all()
            write_next_try_at(stop.next_try_at, stop.reason)
            LOG.warning(
                "rate limited (%s) at accession=%s; stopping batch, next_try_at=%s",
                stop.reason,
                event.accession,
                stop.next_try_at.isoformat(),
            )
            stats.stopped_for_rate_limit = True
            return stats

        now = datetime.now(UTC)
        row = {
            "accession": event.accession,
            "cik": event.cik,
            "ticker": event.ticker,
            "acceptance_utc": event.acceptance_utc,
            **result,
            "scored_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        pending.setdefault(output_partition_key(event), []).append(row)
        stats.record(row)

        bucket = token_hours.setdefault(_hour_bucket(now), {"prompt": 0, "completion": 0})
        bucket["prompt"] += row["prompt_tokens"]
        bucket["completion"] += row["completion_tokens"]

        if stats.processed % CHECKPOINT_EVERY == 0:
            flush_all()
            for hour, counts in sorted(token_hours.items()):
                LOG.info(
                    "cumulative tokens hour=%s prompt=%d completion=%d",
                    hour,
                    counts["prompt"],
                    counts["completion"],
                )

    flush_all()
    for hour, counts in sorted(token_hours.items()):
        LOG.info(
            "cumulative tokens hour=%s prompt=%d completion=%d",
            hour,
            counts["prompt"],
            counts["completion"],
        )
    return stats


# --------------------------------------------------------------------------
# Dry run / determinism check
# --------------------------------------------------------------------------


def run_dry_run(events: list[EventInput], *, sample_count: int = 3) -> None:
    LOG.info(
        "dry-run: %d candidate events, prompt_sha256=%s, no network calls",
        len(events),
        PROMPT_SHA256,
    )
    for i, event in enumerate(events):
        try:
            raw_text = event.text_path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            LOG.warning("dry-run: cannot read %s (%s)", event.text_path, exc)
            continue
        neutral_text = neutralise_text(
            raw_text, company_name=event.company_name, ticker=event.ticker
        )
        if i < sample_count:
            header = (
                f"--- sample {i + 1}/{sample_count}: "
                f"accession={event.accession} ticker={event.ticker} ---"
            )
            print(header)
            print(neutral_text[:1500])
            print()
    LOG.info("dry-run complete")


def run_determinism_check(
    events: list[EventInput],
    call_fn: ChatCallFn,
    *,
    model: str,
    threshold: float = DETERMINISM_THRESHOLD,
) -> int:
    deltas: list[float] = []
    for event in events:
        try:
            raw_text = event.text_path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            LOG.warning("determinism check: cannot read %s (%s)", event.text_path, exc)
            continue
        try:
            first = score_text(
                raw_text=raw_text,
                company_name=event.company_name,
                ticker=event.ticker,
                call_fn=call_fn,
                model=model,
            )
            second = score_text(
                raw_text=raw_text,
                company_name=event.company_name,
                ticker=event.ticker,
                call_fn=call_fn,
                model=model,
            )
        except RateLimitStop as stop:
            LOG.warning("determinism check: rate limited (%s); aborting", stop.reason)
            return 1
        t1, t2 = first.get("tone"), second.get("tone")
        if t1 is None or t2 is None:
            LOG.warning(
                "determinism check: accession=%s produced a non-numeric tone, skipping",
                event.accession,
            )
            continue
        delta = abs(t1 - t2)
        deltas.append(delta)
        LOG.info(
            "determinism check: accession=%s tone1=%.3f tone2=%.3f delta=%.3f",
            event.accession,
            t1,
            t2,
            delta,
        )
    if not deltas:
        LOG.warning("determinism check: no comparable pairs, result=FAIL")
        return 1
    max_delta = max(deltas)
    passed = max_delta <= threshold
    LOG.info(
        "determinism check result: n=%d max_delta=%.3f threshold=%.2f result=%s",
        len(deltas),
        max_delta,
        threshold,
        "PASS" if passed else "FAIL",
    )
    return 0 if passed else 1


# --------------------------------------------------------------------------
# Credentials
# --------------------------------------------------------------------------


def load_credentials(path: Path) -> dict[str, str]:
    """Parse ``KEY=VALUE`` lines from ``path``. Never logs or returns the
    path's contents through any channel other than the returned dict, which
    the caller must not print or persist."""

    if not path.exists():
        raise SystemExit(f"credentials file not found: {path}")
    creds: dict[str, str] = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        creds[key.strip()] = value.strip().strip('"').strip("'")
    missing = [k for k in REQUIRED_CREDENTIAL_KEYS if not creds.get(k)]
    if missing:
        raise SystemExit(f"credentials file missing keys: {missing}")
    return creds


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    source = parser.add_mutually_exclusive_group()
    source.add_argument(
        "--input", type=Path, default=None, help="explicit event-table parquet path"
    )
    source.add_argument(
        "--year", type=int, default=None, help="load data/features/earnings_events/{year}.parquet"
    )
    source.add_argument(
        "--text-paths",
        nargs="+",
        default=None,
        help="explicit raw text files (cik/accession parsed from the path; ticker/company_name/"
        "acceptance_utc left null)",
    )
    parser.add_argument(
        "--limit", type=int, default=None, help="stop after this many candidate events"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="build prompts and print samples, call nothing"
    )
    determinism_help = (
        f"score each candidate event twice and assert |delta(tone)| <= {DETERMINISM_THRESHOLD:.2f}"
    )
    parser.add_argument("--determinism-check", action="store_true", help=determinism_help)
    return parser


def load_events(args: argparse.Namespace) -> list[EventInput]:
    if args.text_paths:
        return load_events_from_text_paths(args.text_paths, limit=args.limit)
    if args.input:
        path = Path(args.input)
    elif args.year:
        path = EVENTS_DIR / f"{args.year}.parquet"
    else:
        raise SystemExit("one of --input, --year, --text-paths is required")
    if not path.exists():
        raise SystemExit(f"input parquet not found: {path}")
    return load_events_from_events_parquet(path, limit=args.limit)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    _setup_logging()
    events = load_events(args)
    LOG.info("loaded %d candidate events (limit=%s)", len(events), args.limit)

    if args.dry_run:
        run_dry_run(events)
        return 0

    creds = load_credentials(CREDENTIALS_PATH)
    model = creds["OC_TEXT_SCORER_MODEL"]
    call_fn = make_requests_chat_call_fn(
        base_url=creds["OC_TEXT_SCORER_BASE_URL"],
        api_key=creds["OC_TEXT_SCORER_API_KEY"],
        model=model,
    )
    LOG.info("model=%s prompt_sha256=%s", model, PROMPT_SHA256)

    if args.determinism_check:
        sample = events[:5] if args.limit is None else events
        return run_determinism_check(sample, call_fn, model=model)

    stats = run_batch(events, call_fn, model=model)
    LOG.info(
        "done: processed=%d ok=%d parse_error=%d http_error=%d skipped_already_scored=%d "
        "skipped_no_text=%d stopped_for_rate_limit=%s prompt_tokens=%d completion_tokens=%d",
        stats.processed,
        stats.ok,
        stats.parse_error,
        stats.http_error,
        stats.skipped_already_scored,
        stats.skipped_no_text,
        stats.stopped_for_rate_limit,
        stats.total_prompt_tokens,
        stats.total_completion_tokens,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
