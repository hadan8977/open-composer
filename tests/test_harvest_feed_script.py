"""Coverage-plan section 4 rule 7 (bottom-up bulk harvest): fixture-based unit
tests for ``scripts/harvest_feed.py``. No network access -- a fake
``ChatCallFn`` stands in for the real HTTP call and a fake ``fetch_page``
stands in for the archive REST API, matching ``tests/test_score_earnings_text.py``'s
"no network" test scope.

Five things are pinned, because each is a place the bulk-classify pipeline
could silently do the wrong thing:

* :func:`build_system_prompt` -- every coverage cell from a small map appears
  in the rendered prompt, and the prompt is stable regardless of input order
  (it is hashed once per run and stamped on every output row).
* :func:`parse_batch_reply` -- a valid JSON array (bare or fenced) parses;
  wrong length, invalid JSON, an out-of-enum field, an unknown cell id, too
  many cells, or a mismatched ``index`` all report failure rather than
  fabricating a classification.
* :func:`pending_items` -- resume skips items whose (normalized) URL is
  already in the classified set; :func:`pull_corpus` skips URLs already
  pulled and only appends genuinely new ones.
* :func:`classify_items` / :func:`_call_with_repair` -- a rate-limited reply
  (fake 429 ``ChatCallResult``) stops the batch loop immediately and
  checkpoints (via ``on_batch_done``) whatever batches already completed;
  a malformed reply gets exactly one repair retry before being recorded as
  ``parse_error``.
* :func:`rank_items` / :func:`render_digest_markdown` -- items rank by
  evidence tier, then novelty, then recency, and the rendered digest reflects
  that order plus shows cells with no relevant items as visible gaps.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

from scripts.harvest_feed import (
    _call_with_repair,
    bucket_by_cell,
    build_system_prompt,
    classify_items,
    evidence_tier_counts,
    parse_batch_reply,
    passes_since,
    pending_items,
    pull_corpus,
    rank_items,
    render_digest_markdown,
)
from scripts.score_earnings_text import ChatCallResult, RateLimitStop, is_rate_limited

SAMPLE_CELLS = [
    {"id": "trend_momentum.stock_momentum", "name": "Individual-stock momentum"},
    {"id": "event.earnings_pead", "name": "Post-earnings drift"},
    {"id": "alt_data.short_selling", "name": "FINRA short volume"},
]
KNOWN_CELL_IDS = {c["id"] for c in SAMPLE_CELLS}


def _valid_item(index: int, **overrides) -> dict:
    base = {
        "index": index,
        "relevant": True,
        "cells": ["trend_momentum.stock_momentum"],
        "evidence": "author_backtest",
        "market": "us_equity_etf",
        "horizon": "weeks",
        "data_needed": "local_price",
        "long_only_ok": "yes",
        "reported_performance": "Sharpe 1.2",
        "summary": "A momentum strategy.",
        "novelty": 2,
    }
    base.update(overrides)
    return base


def _queue_call_fn(results: list[ChatCallResult]):
    calls: list[list[dict]] = []

    def call(messages: list[dict[str, str]]) -> ChatCallResult:
        calls.append(messages)
        return results[len(calls) - 1]

    call.calls = calls  # type: ignore[attr-defined]
    return call


# --------------------------------------------------------------------------
# Prompt building
# --------------------------------------------------------------------------


def test_build_system_prompt_lists_every_cell_and_every_field():
    prompt = build_system_prompt(SAMPLE_CELLS)
    for cell in SAMPLE_CELLS:
        assert f"- {cell['id']}: {cell['name']}" in prompt
    for field in (
        '"index"',
        '"relevant"',
        '"cells"',
        '"evidence"',
        '"market"',
        '"horizon"',
        '"data_needed"',
        '"long_only_ok"',
        '"reported_performance"',
        '"summary"',
        '"novelty"',
    ):
        assert field in prompt
    assert "live_record" in prompt and "tool_or_data" in prompt
    assert "us_equity_etf" in prompt
    assert "JSON array" in prompt


def test_build_system_prompt_is_order_independent_and_stable():
    forwards = build_system_prompt(SAMPLE_CELLS)
    backwards = build_system_prompt(list(reversed(SAMPLE_CELLS)))
    assert forwards == backwards  # cells are sorted internally before rendering


# --------------------------------------------------------------------------
# Reply parsing / validation
# --------------------------------------------------------------------------


def test_parse_batch_reply_valid_array():
    content = json.dumps(
        [_valid_item(1), _valid_item(2, relevant=False, cells=["new:widget_signal"])]
    )
    result = parse_batch_reply(content, batch_size=2, known_cell_ids=KNOWN_CELL_IDS)
    assert result is not None
    assert len(result) == 2
    assert result[0]["evidence"] == "author_backtest"
    assert result[1]["cells"] == ["new:widget_signal"]
    assert result[1]["relevant"] is False


def test_parse_batch_reply_strips_markdown_fence():
    content = "```json\n" + json.dumps([_valid_item(1)]) + "\n```"
    result = parse_batch_reply(content, batch_size=1, known_cell_ids=KNOWN_CELL_IDS)
    assert result is not None
    assert result[0]["novelty"] == 2


def test_parse_batch_reply_extracts_array_embedded_in_prose():
    content = "Here you go: " + json.dumps([_valid_item(1)]) + " hope that helps."
    result = parse_batch_reply(content, batch_size=1, known_cell_ids=KNOWN_CELL_IDS)
    assert result is not None


def test_parse_batch_reply_wrong_length_is_malformed():
    content = json.dumps([_valid_item(1)])
    assert parse_batch_reply(content, batch_size=2, known_cell_ids=KNOWN_CELL_IDS) is None


def test_parse_batch_reply_invalid_json_is_malformed():
    assert parse_batch_reply("not json at all", batch_size=1, known_cell_ids=KNOWN_CELL_IDS) is None


def test_parse_batch_reply_bad_evidence_enum_is_malformed():
    content = json.dumps([_valid_item(1, evidence="pretty_sure")])
    assert parse_batch_reply(content, batch_size=1, known_cell_ids=KNOWN_CELL_IDS) is None


def test_parse_batch_reply_unknown_cell_id_is_malformed():
    content = json.dumps([_valid_item(1, cells=["not_a_real_cell"])])
    assert parse_batch_reply(content, batch_size=1, known_cell_ids=KNOWN_CELL_IDS) is None


def test_parse_batch_reply_too_many_cells_is_malformed():
    ids = {"a", "b", "c", "d"}
    content = json.dumps([_valid_item(1, cells=["a", "b", "c", "d"])])
    assert parse_batch_reply(content, batch_size=1, known_cell_ids=ids) is None


def test_parse_batch_reply_index_mismatch_is_malformed():
    items = [_valid_item(1), _valid_item(1)]  # both claim to be item 1
    content = json.dumps(items)
    assert parse_batch_reply(content, batch_size=2, known_cell_ids=KNOWN_CELL_IDS) is None


def test_parse_batch_reply_novelty_out_of_range_is_malformed():
    content = json.dumps([_valid_item(1, novelty=9)])
    assert parse_batch_reply(content, batch_size=1, known_cell_ids=KNOWN_CELL_IDS) is None


def test_parse_batch_reply_bad_long_only_ok_is_malformed():
    content = json.dumps([_valid_item(1, long_only_ok="mostly")])
    assert parse_batch_reply(content, batch_size=1, known_cell_ids=KNOWN_CELL_IDS) is None


def test_parse_batch_reply_null_reported_performance_is_ok():
    content = json.dumps([_valid_item(1, reported_performance=None)])
    result = parse_batch_reply(content, batch_size=1, known_cell_ids=KNOWN_CELL_IDS)
    assert result is not None
    assert result[0]["reported_performance"] is None


# --------------------------------------------------------------------------
# Resume skipping
# --------------------------------------------------------------------------


def test_pending_items_skips_already_classified_urls():
    items = [{"url": f"https://a.example/{i}"} for i in (1, 2, 3)]
    already = {"https://a.example/2"}
    result = pending_items(items, already)
    assert [i["url"] for i in result] == ["https://a.example/1", "https://a.example/3"]


def test_pending_items_normalizes_urls_for_comparison():
    items = [{"url": "https://A.example.com/x/"}]
    already = {"https://a.example.com/x"}
    assert pending_items(items, already) == []


def test_pending_items_skips_items_with_no_url():
    items = [{"title": "no url here"}, {"url": "https://a.example/1"}]
    assert pending_items(items, set()) == [{"url": "https://a.example/1"}]


def test_pull_corpus_skips_existing_urls():
    pages = {0: {"total": 2, "items": [{"url": "https://x/1"}, {"url": "https://x/2"}]}}
    stats, rows = pull_corpus(
        "repos",
        lambda params: pages[params["offset"] // params["limit"]],
        existing_urls={"https://x/1"},
        page_size=2,
        delay=0,
        sleep=lambda _s: None,
    )
    assert [r["url"] for r in rows] == ["https://x/2"]
    assert stats.pulled_new == 1


# --------------------------------------------------------------------------
# pull_corpus: pagination, since filter, early stop, time budget
# --------------------------------------------------------------------------


def test_pull_corpus_paginates_and_dedupes_within_a_run():
    pages = {
        0: {
            "total": 3,
            "items": [{"url": "https://x/1", "title": "A"}, {"url": "https://x/2", "title": "B"}],
        },
        1: {"total": 3, "items": [{"url": "https://x/3", "title": "C"}]},
    }
    calls = []

    def fetch(params):
        calls.append(dict(params))
        return pages[params["offset"] // params["limit"]]

    stats, rows = pull_corpus(
        "articles", fetch, existing_urls=set(), page_size=2, delay=0, sleep=lambda _s: None
    )
    assert stats.pages_fetched == 2
    assert stats.pulled_new == 3
    assert [r["url"] for r in rows] == ["https://x/1", "https://x/2", "https://x/3"]
    assert all(row["corpus"] == "articles" and row["pulled_at"] for row in rows)
    assert len(calls) == 2


def test_pull_corpus_early_stops_when_a_full_page_is_already_seen():
    pages = {
        0: {"total": 4, "items": [{"url": "https://x/1"}, {"url": "https://x/2"}]},
        1: {"total": 4, "items": [{"url": "https://x/3"}, {"url": "https://x/4"}]},
    }
    calls = []

    def fetch(params):
        calls.append(dict(params))
        return pages[params["offset"] // params["limit"]]

    stats, rows = pull_corpus(
        "articles",  # articles is in EARLY_STOP_CORPORA
        fetch,
        existing_urls={"https://x/1", "https://x/2"},
        page_size=2,
        delay=0,
        sleep=lambda _s: None,
    )
    assert stats.stopped_early_no_new is True
    assert rows == []
    assert len(calls) == 1  # page 2 (all-new) was never fetched


def test_pull_corpus_does_not_early_stop_repos_on_a_fully_seen_page():
    pages = {
        0: {"total": 4, "items": [{"url": "https://x/1"}, {"url": "https://x/2"}]},
        1: {"total": 4, "items": [{"url": "https://x/3"}, {"url": "https://x/4"}]},
    }

    def fetch(params):
        return pages[params["offset"] // params["limit"]]

    stats, rows = pull_corpus(
        "repos",  # repos is sorted by stars, which reorders -- never early-stop
        fetch,
        existing_urls={"https://x/1", "https://x/2"},
        page_size=2,
        delay=0,
        sleep=lambda _s: None,
    )
    assert stats.stopped_early_no_new is False
    assert [r["url"] for r in rows] == ["https://x/3", "https://x/4"]


def test_pull_corpus_respects_time_budget():
    pages = {n: {"total": 10_000, "items": [{"url": f"https://x/{n}"}]} for n in range(50)}
    clock_values = iter([0.0, 0.0, 100.0])  # start, first in-budget check, second over-budget check

    stats, rows = pull_corpus(
        "repos",
        lambda params: pages[params["offset"] // params["limit"]],
        existing_urls=set(),
        page_size=1,
        delay=0,
        sleep=lambda _s: None,
        time_budget_s=10.0,
        clock=lambda: next(clock_values),
    )
    assert stats.stopped_early_for_time is True
    assert stats.pages_fetched == 1


def test_passes_since_keeps_undated_items():
    assert passes_since({}, "2025-01-01") is True


def test_passes_since_compares_date_prefix():
    assert passes_since({"date": "2026-01-01T00:00:00Z"}, "2025-06-01") is True
    assert passes_since({"published": "2024-01-01"}, "2025-06-01") is False


def test_pull_corpus_since_filters_locally_without_skipping_pagination():
    pages = {
        0: {
            "total": 2,
            "items": [
                {"url": "https://x/1", "date": "2020-01-01"},
                {"url": "https://x/2", "date": "2026-01-01"},
            ],
        }
    }
    stats, rows = pull_corpus(
        "articles",
        lambda params: pages[params["offset"] // params["limit"]],
        existing_urls=set(),
        page_size=2,
        delay=0,
        sleep=lambda _s: None,
        since="2025-01-01",
    )
    assert [r["url"] for r in rows] == ["https://x/2"]
    assert stats.pulled_new == 1


# --------------------------------------------------------------------------
# 429 handling
# --------------------------------------------------------------------------


def test_call_with_repair_raises_rate_limit_stop_on_429():
    limited = ChatCallResult(status_code=429, content_text=None, raw_body="rate limit exceeded")
    call_fn = _queue_call_fn([limited])
    try:
        _call_with_repair([], batch_size=1, call_fn=call_fn, known_cell_ids=KNOWN_CELL_IDS)
    except RateLimitStop as stop:
        assert stop.next_try_at > datetime.now(UTC)
    else:
        raise AssertionError("expected RateLimitStop")


def test_is_batch_rate_limited_true_on_429():
    result = ChatCallResult(status_code=429, content_text=None, raw_body="rate limit exceeded")
    assert is_rate_limited(result) is True


def test_is_batch_rate_limited_true_on_non_200_quota_body():
    result = ChatCallResult(status_code=400, content_text=None, raw_body="daily quota exceeded")
    assert is_rate_limited(result) is True


def test_is_batch_rate_limited_false_on_200_even_if_content_mentions_limit():
    # Regression: confirmed live on 2026-09-23 -- a real batch call returned a
    # valid HTTP 200 classification whose own "summary" text said an article
    # "discusses ... limitations of pairs trading", and the imported
    # score_earnings_text.is_rate_limited flagged that as a rate limit purely
    # because "limit" is a substring of "limitations", stopping every batch
    # before anything was ever classified. A 200 response must never be
    # treated as rate-limited from its own generated content.
    body = json.dumps(
        {
            "choices": [
                {"message": {"content": '[{"summary": "discusses position limits and quotas"}]'}}
            ]
        }
    )
    result = ChatCallResult(status_code=200, content_text="ok", raw_body=body)
    assert is_rate_limited(result) is False


def test_call_with_repair_does_not_treat_successful_reply_as_rate_limited():
    reply = json.dumps([_valid_item(1, summary="Discusses position limits and quotas.")])
    call_fn = _queue_call_fn([ChatCallResult(status_code=200, content_text=reply, raw_body=reply)])
    parsed, _prompt_tokens, _completion_tokens = _call_with_repair(
        [], batch_size=1, call_fn=call_fn, known_cell_ids=KNOWN_CELL_IDS
    )
    assert parsed is not None
    assert parsed[0]["summary"] == "Discusses position limits and quotas."


def test_classify_items_stops_immediately_and_keeps_prior_checkpoints():
    ok_reply = json.dumps([_valid_item(1)])
    call_fn = _queue_call_fn(
        [
            ChatCallResult(
                status_code=200, content_text=ok_reply, prompt_tokens=5, completion_tokens=5
            ),
            ChatCallResult(status_code=429, content_text=None, raw_body="rate limit exceeded"),
        ]
    )
    checkpoints: list[tuple[list[dict], dict]] = []
    items = [{"url": f"https://x/{i}", "title": f"T{i}", "desc": "d"} for i in range(2)]

    stats = classify_items(
        "articles",
        items,
        batch_size=1,
        max_calls=10,
        call_fn=call_fn,
        model="m",
        system_prompt=build_system_prompt(SAMPLE_CELLS),
        prompt_sha256="deadbeef",
        known_cell_ids=KNOWN_CELL_IDS,
        on_batch_done=lambda rows, log_row: checkpoints.append((rows, log_row)),
    )

    assert stats.stopped_for_rate_limit is True
    assert stats.rate_limit_stop is not None
    assert stats.calls == 1  # only the first, successful batch was counted
    assert len(checkpoints) == 1  # its rows were checkpointed before the stop
    assert checkpoints[0][0][0]["status"] == "ok"


# --------------------------------------------------------------------------
# classify_items: happy path, repair, parse_error, max_calls
# --------------------------------------------------------------------------


def test_classify_items_happy_path_single_batch():
    items = [
        {"url": "https://x/1", "title": "T1", "desc": "d1"},
        {"url": "https://x/2", "title": "T2", "desc": "d2"},
    ]
    reply = json.dumps([_valid_item(1), _valid_item(2, novelty=4)])
    call_fn = _queue_call_fn(
        [
            ChatCallResult(
                status_code=200, content_text=reply, prompt_tokens=20, completion_tokens=30
            )
        ]
    )
    checkpoints: list[tuple[list[dict], dict]] = []

    stats = classify_items(
        "articles",
        items,
        batch_size=2,
        max_calls=10,
        call_fn=call_fn,
        model="m",
        system_prompt="sys",
        prompt_sha256="abc123",
        known_cell_ids=KNOWN_CELL_IDS,
        on_batch_done=lambda rows, log_row: checkpoints.append((rows, log_row)),
    )

    assert stats.calls == 1
    assert stats.ok == 2
    assert stats.parse_error == 0
    assert stats.prompt_tokens == 20
    assert stats.completion_tokens == 30
    rows, call_log = checkpoints[0]
    assert rows[0]["url"] == "https://x/1"
    assert rows[0]["status"] == "ok"
    assert rows[0]["prompt_sha256"] == "abc123"
    assert rows[1]["novelty"] == 4
    assert call_log["batch_size"] == 2
    assert call_log["status"] == "ok"


def test_classify_items_repairs_once_then_succeeds():
    items = [{"url": "https://x/1", "title": "T1", "desc": "d1"}]
    bad = ChatCallResult(status_code=200, content_text="not json", raw_body="not json")
    good = ChatCallResult(
        status_code=200,
        content_text=json.dumps([_valid_item(1)]),
        prompt_tokens=1,
        completion_tokens=1,
    )
    call_fn = _queue_call_fn([bad, good])
    checkpoints: list[tuple[list[dict], dict]] = []

    stats = classify_items(
        "articles",
        items,
        batch_size=1,
        max_calls=10,
        call_fn=call_fn,
        model="m",
        system_prompt="sys",
        prompt_sha256="abc",
        known_cell_ids=KNOWN_CELL_IDS,
        on_batch_done=lambda rows, log_row: checkpoints.append((rows, log_row)),
    )

    assert stats.ok == 1
    assert len(call_fn.calls) == 2  # the original call plus one repair retry
    assert checkpoints[0][0][0]["status"] == "ok"


def test_classify_items_records_parse_error_after_failed_repair():
    items = [{"url": "https://x/1", "title": "T1", "desc": "d1"}]
    bad = ChatCallResult(status_code=200, content_text="still not json", raw_body="still not json")
    call_fn = _queue_call_fn([bad, bad])
    checkpoints: list[tuple[list[dict], dict]] = []

    stats = classify_items(
        "articles",
        items,
        batch_size=1,
        max_calls=10,
        call_fn=call_fn,
        model="m",
        system_prompt="sys",
        prompt_sha256="abc",
        known_cell_ids=KNOWN_CELL_IDS,
        on_batch_done=lambda rows, log_row: checkpoints.append((rows, log_row)),
    )

    assert stats.parse_error == 1
    assert stats.ok == 0
    rows, call_log = checkpoints[0]
    assert rows[0]["status"] == "parse_error"
    assert rows[0]["relevant"] is None
    assert rows[0]["cells"] == []
    assert call_log["status"] == "parse_error"


def test_classify_items_respects_max_calls():
    items = [{"url": f"https://x/{i}", "title": "T", "desc": "d"} for i in range(4)]
    reply = json.dumps([_valid_item(1)])
    call_fn = _queue_call_fn(
        [ChatCallResult(status_code=200, content_text=reply) for _ in range(10)]
    )

    stats = classify_items(
        "articles",
        items,
        batch_size=1,
        max_calls=2,
        call_fn=call_fn,
        model="m",
        system_prompt="sys",
        prompt_sha256="abc",
        known_cell_ids=KNOWN_CELL_IDS,
        on_batch_done=lambda rows, log_row: None,
    )

    assert stats.calls == 2
    assert stats.processed == 2


# --------------------------------------------------------------------------
# Digest ranking
# --------------------------------------------------------------------------


def test_rank_items_orders_by_evidence_then_novelty_then_recency():
    rows = [
        {"id": "a", "evidence": "claim_only", "novelty": 5, "item_date": "2026-01-01"},
        {"id": "b", "evidence": "live_record", "novelty": 1, "item_date": "2020-01-01"},
        {"id": "c", "evidence": "live_record", "novelty": 3, "item_date": "2025-01-01"},
        {"id": "d", "evidence": "live_record", "novelty": 3, "item_date": "2026-01-01"},
    ]
    ranked = rank_items(rows)
    assert [r["id"] for r in ranked] == ["d", "c", "b", "a"]


def test_bucket_by_cell_groups_relevant_rows_and_new_labels():
    rows = [
        {"status": "ok", "relevant": True, "cells": ["trend_momentum.stock_momentum"]},
        {"status": "ok", "relevant": True, "cells": ["new:widget_signal"]},
        {"status": "ok", "relevant": True, "cells": ["new:widget_signal"]},
        {"status": "ok", "relevant": False, "cells": ["trend_momentum.stock_momentum"]},
        {"status": "parse_error", "relevant": None, "cells": []},
    ]
    by_cell, by_new_label = bucket_by_cell(rows)
    assert len(by_cell["trend_momentum.stock_momentum"]) == 1
    assert len(by_new_label["widget_signal"]) == 2


def test_evidence_tier_counts_counts_each_tier_and_zero_fills_the_rest():
    rows = [{"evidence": "live_record"}, {"evidence": "live_record"}, {"evidence": "claim_only"}]
    counts = evidence_tier_counts(rows)
    assert counts["live_record"] == 2
    assert counts["claim_only"] == 1
    assert counts["theory"] == 0
    assert counts["tool_or_data"] == 0


def test_render_digest_markdown_ranks_items_within_a_cell():
    cells = [{"id": "trend_momentum.stock_momentum", "name": "Stock momentum"}]
    rows = [
        {
            "status": "ok",
            "relevant": True,
            "cells": ["trend_momentum.stock_momentum"],
            "evidence": "claim_only",
            "novelty": 5,
            "item_date": "2026-01-01",
            "title": "Claim-only piece",
            "url": "https://x/claim",
            "source": "Blog",
            "summary": "s",
            "reported_performance": None,
        },
        {
            "status": "ok",
            "relevant": True,
            "cells": ["trend_momentum.stock_momentum"],
            "evidence": "live_record",
            "novelty": 1,
            "item_date": "2020-01-01",
            "title": "Live-tracked piece",
            "url": "https://x/live",
            "source": "Blog",
            "summary": "s",
            "reported_performance": "CAGR 12%",
        },
    ]
    totals = {
        "items_pulled": 2,
        "items_classified": 2,
        "relevant": 2,
        "parse_errors": 0,
        "calls": 1,
        "tokens": 100,
    }
    markdown = render_digest_markdown(
        date="2026-09-23", cells=cells, classified_rows=rows, totals=totals
    )
    live_pos = markdown.index("Live-tracked piece")
    claim_pos = markdown.index("Claim-only piece")
    assert live_pos < claim_pos  # live_record outranks claim_only despite lower novelty/older date
    assert "reported: CAGR 12%" in markdown
    assert "items pulled: 2" in markdown


def test_render_digest_markdown_shows_empty_cells_as_visible_gaps():
    cells = [{"id": "empty.cell", "name": "Nothing Here"}]
    totals = {
        "items_pulled": 0,
        "items_classified": 0,
        "relevant": 0,
        "parse_errors": 0,
        "calls": 0,
        "tokens": 0,
    }
    markdown = render_digest_markdown(
        date="2026-09-23", cells=cells, classified_rows=[], totals=totals
    )
    assert "empty.cell" in markdown
    assert "No relevant items found" in markdown
