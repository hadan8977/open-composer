"""T2 (plan-earnings-text-forward-test-2026-09-22): fixture-based unit tests
for the earnings-text tone/guidance scorer. No network access -- a fake
``ChatCallFn`` stands in for the real HTTP call, matching the card's "no
network" test scope (mirrors ``tests/test_build_earnings_events.py``).

Four things are pinned, because each is a place scoring could silently do
the wrong thing:

* :func:`neutralise_text` -- company name (incl. suffix-stripped core name),
  ticker, month names, four-digit years and dollar amounts all become
  placeholders, and the ~12k-token character truncation is applied.
* :func:`parse_score_reply` -- valid JSON (bare or fenced in Markdown)
  parses; invalid JSON, an out-of-enum ``guidance``, or a non-numeric
  ``tone`` all report failure rather than fabricating a score.
* :func:`run_batch` checkpoint/resume -- a second run over the same events
  plus one new one only calls the (fake) endpoint for the new accession.
* :func:`run_batch` the 429 stop path -- a rate-limited response stops the
  batch immediately, checkpoints whatever was already scored, and writes
  ``next_try_at.json`` instead of raising.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from scripts.score_earnings_text import (
    PROMPT_SHA256,
    ChatCallResult,
    EventInput,
    RateLimitStop,
    build_messages,
    compute_next_try_at,
    flush_partition,
    is_rate_limited,
    load_already_scored,
    neutralise_text,
    parse_score_reply,
    run_batch,
    score_text,
    validate_score_obj,
)

# --------------------------------------------------------------------------
# Entity neutralisation
# --------------------------------------------------------------------------


def test_neutralise_replaces_company_ticker_month_year_amount():
    text = (
        "Alcoa Corporation (NYSE: AA) reported revenue of $1.2 billion for "
        "January 2024, up from $950 million a year earlier."
    )
    result = neutralise_text(text, company_name="Alcoa Corporation", ticker="AA")
    assert "Alcoa" not in result
    assert "AA" not in result.split()  # ticker token gone (word-bounded)
    assert "$1.2 billion" not in result
    assert "January" not in result
    assert "2024" not in result
    assert "[COMPANY]" in result
    assert "[TICKER]" in result
    assert "[AMOUNT]" in result
    assert "[MONTH]" in result
    assert "[YEAR]" in result


def test_neutralise_matches_core_name_without_suffix():
    # Press releases often drop just the legal suffix ("Agilent Technologies"
    # vs. the SEC registrant name "Agilent Technologies, Inc."); the
    # suffix-stripped core name is matched as its own variant. Dropping to a
    # single informal word ("Agilent" alone) is a known limitation, not
    # covered here.
    text = "Agilent Technologies today announced quarterly results."
    result = neutralise_text(text, company_name="Agilent Technologies, Inc.", ticker=None)
    assert "Agilent Technologies" not in result
    assert "[COMPANY]" in result


def test_neutralise_ticker_is_word_bounded_and_case_sensitive():
    # Word-bounded: a ticker glued into a longer token ("ACMECorp") is left
    # alone. Case-sensitive: lowercase incidental text ("acme") is left
    # alone -- tickers are conventionally rendered upper-case in filings.
    text = (
        "ACME reported results today. lowercase acme is unaffected. "
        "ACMECorp is unaffected too. (NASDAQ: ACME)"
    )
    result = neutralise_text(text, company_name=None, ticker="ACME")
    assert result.count("[TICKER]") == 2  # the two standalone "ACME" tokens only
    assert "lowercase acme is unaffected" in result
    assert "ACMECorp is unaffected too" in result


def test_neutralise_handles_missing_company_and_ticker():
    text = "Results improved in March 2023 versus $10 million last year."
    result = neutralise_text(text, company_name=None, ticker=None)
    assert "[MONTH]" in result
    assert "[YEAR]" in result
    assert "[AMOUNT]" in result


def test_neutralise_truncates_to_max_chars():
    text = "x" * 100_000
    result = neutralise_text(text, company_name=None, ticker=None, max_chars=1_000)
    assert len(result) == 1_000


def test_prompt_sha256_is_stable_and_nonempty():
    assert isinstance(PROMPT_SHA256, str)
    assert len(PROMPT_SHA256) == 64
    messages = build_messages("some neutralised text")
    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"
    assert "some neutralised text" in messages[1]["content"]


# --------------------------------------------------------------------------
# JSON parsing
# --------------------------------------------------------------------------


def test_parse_score_reply_valid_json():
    reply = json.dumps({"tone": 0.4, "guidance": "up", "rationale": "strong demand"})
    parsed = parse_score_reply(reply)
    assert parsed == {"tone": 0.4, "guidance": "up", "rationale": "strong demand"}


def test_parse_score_reply_strips_markdown_fence():
    reply = '```json\n{"tone": -0.2, "guidance": "down", "rationale": "soft outlook"}\n```'
    parsed = parse_score_reply(reply)
    assert parsed is not None
    assert parsed["tone"] == -0.2
    assert parsed["guidance"] == "down"


def test_parse_score_reply_extracts_embedded_json_object():
    reply = 'Here is my answer: {"tone": 0, "guidance": "same", "rationale": "flat"} thanks.'
    parsed = parse_score_reply(reply)
    assert parsed is not None
    assert parsed["guidance"] == "same"


def test_parse_score_reply_invalid_json_returns_none():
    assert parse_score_reply("not json at all") is None


def test_validate_score_obj_rejects_bad_guidance():
    assert validate_score_obj({"tone": 0.1, "guidance": "bullish", "rationale": "x"}) is None


def test_validate_score_obj_rejects_non_numeric_tone():
    assert validate_score_obj({"tone": "very positive", "guidance": "up", "rationale": "x"}) is None


def test_validate_score_obj_clamps_out_of_range_tone():
    result = validate_score_obj({"tone": 5, "guidance": "up", "rationale": "x"})
    assert result is not None
    assert result["tone"] == 1.0


# --------------------------------------------------------------------------
# score_text with a fake call function
# --------------------------------------------------------------------------


def _ok_result(
    tone: float, guidance: str, *, prompt_tokens=10, completion_tokens=5
) -> ChatCallResult:
    body = json.dumps({"tone": tone, "guidance": guidance, "rationale": "test"})
    return ChatCallResult(
        status_code=200,
        content_text=body,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        raw_body=body,
    )


def _queue_call_fn(results: list[ChatCallResult]):
    calls: list[list[dict]] = []

    def call(messages: list[dict[str, str]]) -> ChatCallResult:
        calls.append(messages)
        return results[len(calls) - 1]

    call.calls = calls  # type: ignore[attr-defined]
    return call


def test_score_text_ok_on_first_try():
    call_fn = _queue_call_fn([_ok_result(0.5, "up")])
    row = score_text(
        raw_text="Great quarter for Acme Corp.",
        company_name="Acme Corp",
        ticker="ACME",
        call_fn=call_fn,
        model="Deepseek-v4-flash",
    )
    assert row["status"] == "ok"
    assert row["tone"] == 0.5
    assert row["guidance"] == "up"
    assert row["prompt_sha256"] == PROMPT_SHA256
    assert row["prompt_tokens"] == 10
    assert row["completion_tokens"] == 5
    assert len(call_fn.calls) == 1


def test_score_text_retries_once_on_parse_failure_then_succeeds():
    bad = ChatCallResult(status_code=200, content_text="not json", raw_body="not json")
    good = _ok_result(-0.3, "down")
    call_fn = _queue_call_fn([bad, good])
    row = score_text(
        raw_text="Weak quarter.", company_name=None, ticker=None, call_fn=call_fn, model="m"
    )
    assert row["status"] == "ok"
    assert row["tone"] == -0.3
    assert len(call_fn.calls) == 2
    # tokens from both attempts are summed
    assert row["prompt_tokens"] == good.prompt_tokens
    assert row["completion_tokens"] == good.completion_tokens


def test_score_text_parse_error_after_failed_retry():
    bad = ChatCallResult(status_code=200, content_text="still not json", raw_body="still not json")
    call_fn = _queue_call_fn([bad, bad])
    row = score_text(
        raw_text="Ambiguous quarter.", company_name=None, ticker=None, call_fn=call_fn, model="m"
    )
    assert row["status"] == "parse_error"
    assert row["tone"] is None
    assert row["guidance"] is None


def test_score_text_http_error_status():
    err = ChatCallResult(status_code=500, content_text=None, raw_body="internal error")
    call_fn = _queue_call_fn([err])
    row = score_text(
        raw_text="Some text.", company_name=None, ticker=None, call_fn=call_fn, model="m"
    )
    assert row["status"] == "http_error"


def test_score_text_raises_rate_limit_stop_on_429():
    limited = ChatCallResult(status_code=429, content_text=None, raw_body="rate limit exceeded")
    call_fn = _queue_call_fn([limited])
    try:
        score_text(raw_text="text", company_name=None, ticker=None, call_fn=call_fn, model="m")
    except RateLimitStop as stop:
        assert stop.next_try_at > datetime.now(UTC)
    else:
        raise AssertionError("expected RateLimitStop")


def test_is_rate_limited_detects_quota_keyword_without_429_status():
    result = ChatCallResult(status_code=400, content_text=None, raw_body="daily quota exceeded")
    assert is_rate_limited(result) is True


def test_is_rate_limited_false_for_ordinary_error():
    result = ChatCallResult(status_code=500, content_text=None, raw_body="internal server error")
    assert is_rate_limited(result) is False


def test_compute_next_try_at_uses_retry_after_seconds():
    now = datetime(2026, 9, 22, 0, 0, 0, tzinfo=UTC)
    result = ChatCallResult(status_code=429, content_text=None, headers={"Retry-After": "120"})
    next_try = compute_next_try_at(result, now=now)
    assert (next_try - now).total_seconds() == 120


def test_compute_next_try_at_defaults_to_30_minutes():
    now = datetime(2026, 9, 22, 0, 0, 0, tzinfo=UTC)
    result = ChatCallResult(status_code=429, content_text=None, headers={})
    next_try = compute_next_try_at(result, now=now)
    assert (next_try - now).total_seconds() == 1800


# --------------------------------------------------------------------------
# run_batch: checkpoint/resume and the 429 stop path
# --------------------------------------------------------------------------


def _write_text(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def _patch_out_dir(monkeypatch, tmp_path: Path) -> Path:
    import scripts.score_earnings_text as mod

    out_dir = tmp_path / "scores"
    monkeypatch.setattr(mod, "OUT_DIR", out_dir)
    monkeypatch.setattr(mod, "NEXT_TRY_PATH", out_dir / "next_try_at.json")
    return out_dir


def test_run_batch_checkpoints_and_resume_skips_already_scored(tmp_path, monkeypatch):
    out_dir = _patch_out_dir(monkeypatch, tmp_path)

    event_a = EventInput(
        accession="0001-24-000001",
        cik="1",
        ticker="AAA",
        company_name="Aaa Corp",
        acceptance_utc="2024-03-01T12:00:00Z",
        text_path=_write_text(
            tmp_path / "raw" / "1" / "0001-24-000001.txt", "Aaa Corp had a fine quarter."
        ),
    )
    event_b = EventInput(
        accession="0002-24-000002",
        cik="2",
        ticker="BBB",
        company_name="Bbb Corp",
        acceptance_utc="2024-03-02T12:00:00Z",
        text_path=_write_text(
            tmp_path / "raw" / "2" / "0002-24-000002.txt", "Bbb Corp had a tough quarter."
        ),
    )
    call_fn = _queue_call_fn([_ok_result(0.2, "up"), _ok_result(-0.4, "down")])

    stats = run_batch([event_a, event_b], call_fn, model="m")
    assert stats.processed == 2
    assert stats.ok == 2
    assert stats.skipped_already_scored == 0

    out_path = out_dir / "2024.parquet"
    assert out_path.exists()
    import pandas as pd

    df = pd.read_parquet(out_path)
    assert set(df["accession"]) == {"0001-24-000001", "0002-24-000002"}

    # Second run: same two events plus a brand-new one. The already-scored
    # two must not trigger any (fake) network call.
    event_c = EventInput(
        accession="0003-24-000003",
        cik="3",
        ticker="CCC",
        company_name="Ccc Corp",
        acceptance_utc="2024-03-03T12:00:00Z",
        text_path=_write_text(
            tmp_path / "raw" / "3" / "0003-24-000003.txt", "Ccc Corp beat expectations."
        ),
    )
    call_fn_2 = _queue_call_fn([_ok_result(0.6, "up")])
    stats_2 = run_batch([event_a, event_b, event_c], call_fn_2, model="m")
    assert stats_2.skipped_already_scored == 2
    assert stats_2.processed == 1
    assert len(call_fn_2.calls) == 1

    df_2 = pd.read_parquet(out_path)
    assert set(df_2["accession"]) == {
        "0001-24-000001",
        "0002-24-000002",
        "0003-24-000003",
    }


def test_run_batch_stops_and_writes_next_try_at_on_429(tmp_path, monkeypatch):
    out_dir = _patch_out_dir(monkeypatch, tmp_path)

    event_a = EventInput(
        accession="0001-24-000001",
        cik="1",
        ticker="AAA",
        company_name="Aaa Corp",
        acceptance_utc="2024-05-01T12:00:00Z",
        text_path=_write_text(
            tmp_path / "raw" / "1" / "0001-24-000001.txt", "Aaa Corp had a fine quarter."
        ),
    )
    event_b = EventInput(
        accession="0002-24-000002",
        cik="2",
        ticker="BBB",
        company_name="Bbb Corp",
        acceptance_utc="2024-05-02T12:00:00Z",
        text_path=_write_text(
            tmp_path / "raw" / "2" / "0002-24-000002.txt", "Bbb Corp had a tough quarter."
        ),
    )
    limited = ChatCallResult(
        status_code=429,
        content_text=None,
        raw_body="rate limit exceeded",
        headers={"Retry-After": "60"},
    )
    call_fn = _queue_call_fn([_ok_result(0.1, "same"), limited])

    stats = run_batch([event_a, event_b], call_fn, model="m")

    assert stats.processed == 1
    assert stats.ok == 1
    assert stats.stopped_for_rate_limit is True

    # The first event was checkpointed before the stop.
    out_path = out_dir / "2024.parquet"
    import pandas as pd

    df = pd.read_parquet(out_path)
    assert set(df["accession"]) == {"0001-24-000001"}

    # next_try_at.json was written with a retry time derived from Retry-After.
    next_try_path = out_dir / "next_try_at.json"
    assert next_try_path.exists()
    payload = json.loads(next_try_path.read_text())
    assert "next_try_at" in payload
    assert "reason" in payload


def test_load_already_scored_reads_existing_partition(tmp_path, monkeypatch):
    out_dir = _patch_out_dir(monkeypatch, tmp_path)
    out_dir.mkdir(parents=True, exist_ok=True)

    flush_partition(
        "2024",
        [
            {
                "accession": "0001-24-000001",
                "cik": "1",
                "ticker": "AAA",
                "acceptance_utc": "2024-03-01T12:00:00Z",
                "tone": 0.1,
                "guidance": "up",
                "rationale": "x",
                "model": "m",
                "prompt_sha256": PROMPT_SHA256,
                "neutralised_text_sha256": "abc",
                "prompt_tokens": 1,
                "completion_tokens": 1,
                "scored_at": "2024-03-01T12:05:00Z",
                "status": "ok",
            }
        ],
    )
    scored = load_already_scored({"2024"})
    assert scored == {"0001-24-000001"}


def test_is_rate_limited_ignores_a_successful_reply_that_mentions_limits():
    result = ChatCallResult(
        status_code=200,
        content_text='{"tone": 0.1, "guidance": "limited visibility", "rationale": "x"}',
        raw_body='{"choices": [{"message": {"content": "limited visibility"}}]}',
    )
    assert is_rate_limited(result) is False
