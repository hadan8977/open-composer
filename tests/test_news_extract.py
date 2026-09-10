"""Tests for open_composer/research/news/extract.py.

Never calls a real LLM: fake backends implement the same duck-typed
protocol (``infer`` and/or ``infer_with_usage``) that
``open_composer.research.llm_backends`` backends provide.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pytest

from open_composer.research.news import extract as ex


def _article_row(article_id: str, headline: str = "H", summary: str = "S") -> dict[str, Any]:
    return {
        "id": article_id,
        "created_at": pd.Timestamp("2024-06-03T10:00:00Z"),
        "symbols": ["AAPL"],
        "headline": headline,
        "summary": summary,
    }


class _FakeBackendWithUsage:
    """Implements infer_with_usage directly (the OpenAIBackend shape)."""

    def __init__(self, results: list[dict[str, Any]], usage: dict[str, int] | None = None) -> None:
        self.results = results
        self.usage = usage or {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15}
        self.calls: list[dict[str, Any]] = []

    def infer_with_usage(self, **kwargs: Any) -> tuple[dict[str, Any], dict[str, int]]:
        self.calls.append(kwargs)
        return {"results": self.results}, self.usage

    def infer(self, **kwargs: Any) -> dict[str, Any]:  # pragma: no cover - not exercised
        raise AssertionError("infer_with_usage should be preferred when present")


class _FakeBackendInferOnly:
    """Only implements infer() (LocalTestStub's shape) -- usage must default to zero."""

    def __init__(self, results: list[dict[str, Any]]) -> None:
        self.results = results

    def infer(self, **kwargs: Any) -> dict[str, Any]:
        return {"results": self.results}


def _valid_result(article_id: str) -> dict[str, Any]:
    return {
        "id": article_id,
        "event_type": "earnings_beat",
        "stated_direction": 1,
        "company_specific": True,
        "confidence": 0.8,
    }


# --- prompt -------------------------------------------------------------


def test_prompt_contains_required_verbatim_instruction() -> None:
    assert "只抽取标题/摘要本身陈述的内容；不得使用任何" in ex.EXTRACTION_PROMPT
    assert "外部知识或对后续走势的判断" in ex.EXTRACTION_PROMPT


def test_prompt_hash_is_stable_and_deterministic() -> None:
    assert ex.prompt_hash() == ex.prompt_hash()
    assert len(ex.prompt_hash()) == 64  # sha256 hex digest


def test_output_schema_is_strict_object_wrapped_array() -> None:
    assert ex.EXTRACTION_OUTPUT_SCHEMA["type"] == "object"
    assert ex.EXTRACTION_OUTPUT_SCHEMA["additionalProperties"] is False
    item_schema = ex.EXTRACTION_OUTPUT_SCHEMA["properties"]["results"]["items"]
    assert set(item_schema["required"]) == {
        "id",
        "event_type",
        "stated_direction",
        "company_specific",
        "confidence",
    }
    assert set(item_schema["properties"]["event_type"]["enum"]) == set(ex.EVENT_TYPES)


# --- truncate / build_batch_input ---------------------------------------


def test_truncate_leaves_short_text_untouched() -> None:
    assert ex.truncate("short") == "short"
    assert ex.truncate(None) == ""


def test_truncate_clips_long_text_with_ellipsis() -> None:
    long_text = "x" * 400
    result = ex.truncate(long_text, limit=300)
    assert len(result) == 300
    assert result.endswith("…")


def test_build_batch_input_shape() -> None:
    articles = pd.DataFrame([_article_row("1"), _article_row("2")])
    payload = ex.build_batch_input(articles)
    assert payload == {
        "articles": [
            {"id": "1", "headline": "H", "summary": "S"},
            {"id": "2", "headline": "H", "summary": "S"},
        ]
    }


# --- extract_batch --------------------------------------------------------


def test_extract_batch_success_tags_every_row_with_provenance() -> None:
    articles = pd.DataFrame([_article_row("1"), _article_row("2")])
    backend = _FakeBackendWithUsage([_valid_result("1"), _valid_result("2")])

    result = ex.extract_batch(articles, backend=backend, model="test-model")

    assert result.status == "ok"
    assert result.error is None
    assert result.usage == {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15}
    assert [row["id"] for row in result.rows] == ["1", "2"]
    for row in result.rows:
        assert row["model_id"] == "test-model"
        assert row["prompt_hash"] == ex.prompt_hash()
        assert row["knowledge_cutoff"] == ex.KNOWLEDGE_CUTOFF_DISCLOSURE
        assert row["event_type"] == "earnings_beat"
        assert row["stated_direction"] == 1
        assert row["confidence"] == 0.8


def test_extract_batch_falls_back_to_infer_when_no_usage_method() -> None:
    articles = pd.DataFrame([_article_row("1")])
    backend = _FakeBackendInferOnly([_valid_result("1")])

    result = ex.extract_batch(articles, backend=backend, model="test-model")

    assert result.status == "ok"
    assert result.usage == {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}


@pytest.mark.parametrize(
    "bad_result",
    [
        {**_valid_result("1"), "event_type": "not_a_real_type"},
        {**_valid_result("1"), "stated_direction": 2},
        {**_valid_result("1"), "confidence": 1.5},
        {**_valid_result("1"), "confidence": -0.1},
        {**_valid_result("1"), "id": "wrong-id"},
    ],
)
def test_extract_batch_rejects_invalid_rows_as_a_failed_call(bad_result: dict[str, Any]) -> None:
    articles = pd.DataFrame([_article_row("1")])
    backend = _FakeBackendWithUsage([bad_result])

    result = ex.extract_batch(articles, backend=backend, model="test-model")

    assert result.status == "error"
    assert result.rows == []
    assert result.error


def test_extract_batch_rejects_wrong_result_count() -> None:
    articles = pd.DataFrame([_article_row("1"), _article_row("2")])
    backend = _FakeBackendWithUsage([_valid_result("1")])  # only one, expected two

    result = ex.extract_batch(articles, backend=backend, model="test-model")

    assert result.status == "error"
    assert "expected 2" in result.error


# --- ledger ---------------------------------------------------------------


def test_ledger_round_trip_and_token_sum(tmp_path: Path) -> None:
    ledger_path = tmp_path / "ledger.jsonl"
    row1 = ex.ledger_row(
        batch_index=0,
        model="m",
        prompt_hash_value="h",
        usage={"input_tokens": 100, "output_tokens": 50, "total_tokens": 150},
        article_ids=["1", "2"],
        status="ok",
        error=None,
    )
    row2 = ex.ledger_row(
        batch_index=1,
        model="m",
        prompt_hash_value="h",
        usage={"input_tokens": 200, "output_tokens": 20, "total_tokens": 220},
        article_ids=["3"],
        status="error",
        error="boom",
    )
    ex.append_ledger([row1], ledger_path=ledger_path)
    ex.append_ledger([row2], ledger_path=ledger_path)

    assert ex.tokens_used_so_far(ledger_path=ledger_path) == 100 + 50 + 200 + 20
    lines = ledger_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2


def test_tokens_used_so_far_missing_ledger_is_zero(tmp_path: Path) -> None:
    assert ex.tokens_used_so_far(ledger_path=tmp_path / "missing.jsonl") == 0


# --- events cache/store ----------------------------------------------------


def test_append_events_then_load_cached_keys_round_trip(tmp_path: Path) -> None:
    root = tmp_path / "news_events"
    rows = [
        {
            "id": "1",
            "event_type": "earnings_beat",
            "stated_direction": 1,
            "company_specific": True,
            "confidence": 0.8,
            "model_id": "m",
            "knowledge_cutoff": "disclosure",
            "prompt_hash": "h1",
            "extracted_at": pd.Timestamp("2024-06-03T00:00:00Z"),
        },
        {
            "id": "2",
            "event_type": "other_noise",
            "stated_direction": 0,
            "company_specific": False,
            "confidence": 0.2,
            "model_id": "m",
            "knowledge_cutoff": "disclosure",
            "prompt_hash": "h1",
            "extracted_at": pd.Timestamp("2024-06-03T00:00:00Z"),
        },
    ]
    ex.append_events(rows, source_years={"1": 2024, "2": 2024}, root=root)

    assert ex.events_path(2024, root=root).exists()
    cached = ex.load_cached_keys([2024], root=root)
    assert cached == {("1", "h1"), ("2", "h1")}


def test_append_events_dedupes_by_id_and_prompt_hash_keeping_latest(tmp_path: Path) -> None:
    root = tmp_path / "news_events"
    base_row = {
        "id": "1",
        "event_type": "earnings_beat",
        "stated_direction": 1,
        "company_specific": True,
        "confidence": 0.8,
        "model_id": "m",
        "knowledge_cutoff": "disclosure",
        "prompt_hash": "h1",
        "extracted_at": pd.Timestamp("2024-06-03T00:00:00Z"),
    }
    ex.append_events([base_row], source_years={"1": 2024}, root=root)
    updated_row = {**base_row, "confidence": 0.99}
    ex.append_events([updated_row], source_years={"1": 2024}, root=root)

    frame = pd.read_parquet(ex.events_path(2024, root=root))
    assert len(frame) == 1
    assert float(frame.iloc[0]["confidence"]) == 0.99


def test_append_events_with_no_rows_is_a_no_op(tmp_path: Path) -> None:
    root = tmp_path / "news_events"
    ex.append_events([], source_years={}, root=root)
    assert not root.exists()


# --- weekly candidate pool -------------------------------------------------


def _write_universe_fixtures(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    # month_end cohorts only become eligible ON their own month_end date
    # (universe_as_of_calendar_month: "most recent month_end <= date"), so
    # the Dec-2023 cohort is what applies through January, and the Jan-2024
    # cohort is what applies through February -- one calendar month later
    # than the naive "January cohort applies in January" reading.
    pd.DataFrame(
        [
            {"month_end": pd.Timestamp("2023-12-29"), "symbol": "AAA", "adv_rank": 1},
            {"month_end": pd.Timestamp("2023-12-29"), "symbol": "BBB", "adv_rank": 2},
            {"month_end": pd.Timestamp("2023-12-29"), "symbol": "ETF1", "adv_rank": 3},
        ]
    ).to_parquet(root / "2023.parquet")
    pd.DataFrame(
        [
            {"month_end": pd.Timestamp("2024-01-31"), "symbol": "AAA", "adv_rank": 1},
            {"month_end": pd.Timestamp("2024-01-31"), "symbol": "CCC", "adv_rank": 2},
            {"month_end": pd.Timestamp("2024-01-31"), "symbol": "ETF1", "adv_rank": 3},
        ]
    ).to_parquet(root / "2024.parquet")
    pd.DataFrame(
        [
            {"symbol": "AAA", "is_probable_fund_or_etf": False},
            {"symbol": "BBB", "is_probable_fund_or_etf": False},
            {"symbol": "CCC", "is_probable_fund_or_etf": False},
            {"symbol": "ETF1", "is_probable_fund_or_etf": True},
        ]
    ).to_parquet(root / "_asset_metadata.parquet")


def _write_daily_fixtures(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    # Fridays in Jan/Feb 2024: 2024-01-05, 01-12, ..., 02-02, 02-09, ...
    rows = []
    for friday, momentum in [
        (pd.Timestamp("2024-01-05"), {"AAA": 0.5, "BBB": 0.9, "ETF1": 0.99}),
        (pd.Timestamp("2024-02-09"), {"AAA": 0.4, "CCC": 0.7, "ETF1": 0.95}),
    ]:
        for symbol, momentum_252_21 in momentum.items():
            rows.append(
                {"symbol": symbol, "trade_date": friday, "momentum_252_21": momentum_252_21}
            )
    pd.DataFrame(rows).to_parquet(root / "2024.parquet")


def test_compute_weekly_candidate_pools_ranks_top_n_excludes_etf_pit_month(
    tmp_path: Path,
) -> None:
    universe_root = tmp_path / "universe"
    daily_root = tmp_path / "daily"
    _write_universe_fixtures(universe_root)
    _write_daily_fixtures(daily_root)

    pools = ex.compute_weekly_candidate_pools(
        pd.Timestamp("2024-01-01"),
        pd.Timestamp("2024-02-15"),
        top_n=1,
        daily_root=daily_root,
        universe_root=universe_root,
        memory_limit="512MB",
    )

    # 2024-01-05 uses the Dec-2023 cohort (AAA, BBB eligible, ETF1 excluded --
    # the Jan-2024 cohort is not eligible until its own month_end, 01-31);
    # top-1 by momentum among {AAA: 0.5, BBB: 0.9} is BBB.
    assert pools[pd.Timestamp("2024-01-05")] == {"BBB"}
    # 2024-02-09 uses the Jan-2024 cohort (AAA, CCC eligible, ETF1 excluded --
    # there is no Feb-2024 cohort in this fixture at all);
    # top-1 among {AAA: 0.4, CCC: 0.7} is CCC.
    assert pools[pd.Timestamp("2024-02-09")] == {"CCC"}
    # Every other Friday in range has no daily rows -> empty pool, not a crash.
    other_fridays = [
        f for f in pools if f not in (pd.Timestamp("2024-01-05"), pd.Timestamp("2024-02-09"))
    ]
    assert other_fridays  # sanity: there are other Fridays in a 6-week range
    assert all(pools[f] == set() for f in other_fridays)


def test_candidate_pool_for_date_uses_most_recent_friday_on_or_before() -> None:
    pools = {
        pd.Timestamp("2024-01-05"): {"AAA"},
        pd.Timestamp("2024-01-12"): {"BBB"},
    }
    assert ex.candidate_pool_for_date(pd.Timestamp("2024-01-08"), pools) == {"AAA"}
    assert ex.candidate_pool_for_date(pd.Timestamp("2024-01-12"), pools) == {"BBB"}
    assert ex.candidate_pool_for_date(pd.Timestamp("2024-01-01"), pools) == set()


# --- select_articles_for_extraction ---------------------------------------


def test_select_articles_for_extraction_filters_by_pool_and_cache() -> None:
    pools = {pd.Timestamp("2024-05-31"): {"AAPL"}}  # Friday on/before the Monday 06-03 article
    articles = pd.DataFrame(
        [
            _article_row("1"),  # AAPL, in pool, not cached -> kept
            {**_article_row("2"), "symbols": ["ZZZ"]},  # not in pool -> dropped
            {**_article_row("3"), "symbols": []},  # no symbols -> dropped
            _article_row("4"),  # AAPL, in pool, but already cached -> dropped
        ]
    )
    phash = "hash-now"
    cached_keys = {("4", "hash-now")}

    selected = ex.select_articles_for_extraction(
        articles, pools=pools, cached_keys=cached_keys, prompt_hash_value=phash
    )

    assert list(selected["id"]) == ["1"]


def test_select_articles_for_extraction_empty_input_returns_empty() -> None:
    result = ex.select_articles_for_extraction(
        pd.DataFrame(columns=["id", "created_at", "symbols"]),
        pools={},
        cached_keys=set(),
        prompt_hash_value="h",
    )
    assert result.empty


def test_select_articles_for_extraction_handles_numpy_array_symbols() -> None:
    """2026-09-10 regression: real collected packets carry ``symbols`` as a
    numpy array (parquet's list-column round trip), not a Python list.
    ``symbols or []`` evaluates the array's truthiness and raises
    ``ValueError: The truth value of an array with more than one element is
    ambiguous`` for any multi-symbol article -- this is exactly the crash
    the first real bulk-extraction run hit on its very first batch."""
    pools = {pd.Timestamp("2024-05-31"): {"AAPL"}}
    articles = pd.DataFrame(
        [
            {**_article_row("1"), "symbols": np.array(["AAPL", "MSFT"])},  # multi-elem -> kept
            {**_article_row("2"), "symbols": np.array(["ZZZ", "YYY"])},  # not in pool -> dropped
            {**_article_row("3"), "symbols": np.array([], dtype=object)},  # empty -> dropped
        ]
    )

    selected = ex.select_articles_for_extraction(
        articles, pools=pools, cached_keys=set(), prompt_hash_value="h"
    )

    assert list(selected["id"]) == ["1"]


def test_select_articles_for_extraction_after_real_parquet_round_trip(tmp_path: Path) -> None:
    """Same bug, reproduced via an actual parquet write/read (the real
    collector -> extractor path), not just a hand-built numpy array."""
    pools = {pd.Timestamp("2024-05-31"): {"AAPL"}}
    path = tmp_path / "articles.parquet"
    pd.DataFrame(
        [
            {**_article_row("1"), "symbols": ["AAPL", "MSFT"]},
            {**_article_row("2"), "symbols": []},
        ]
    ).to_parquet(path)
    articles = pd.read_parquet(path)
    assert isinstance(articles.iloc[0]["symbols"], np.ndarray)  # sanity: reproduces the real shape

    selected = ex.select_articles_for_extraction(
        articles, pools=pools, cached_keys=set(), prompt_hash_value="h"
    )

    assert list(selected["id"]) == ["1"]
