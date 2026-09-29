"""H-20260928-22 unit tests: PIT news cutoff, anonymization, placebo mismatch, cache keys.

Card: reports/research/hypotheses/H-20260928-22-llm-news-momentum-filter.md.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

mod = importlib.import_module("scripts.score_h20260928_22_news_momentum")


def _news_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "id": [1, 2, 3, 4],
            "symbols": [
                ["AAPL"],
                ["AAPL"],
                ["MSFT"],
                ["AAPL", "MSFT"],
            ],
            "visible_at": pd.to_datetime(
                [
                    "2026-05-20T12:00:00Z",  # AAPL, well before asof -> included
                    "2026-05-29T22:00:00Z",  # AAPL, AFTER asof (21:00 UTC) -> excluded
                    "2026-05-25T12:00:00Z",  # MSFT, before asof -> included for MSFT
                    "2026-05-28T20:00:00Z",  # AAPL+MSFT, before asof -> included both
                ],
                utc=True,
            ),
            "headline": [
                "Apple Inc. announces new product",
                "Apple Inc. late headline",
                "Microsoft Corp beats estimates",
                "Apple Inc. and Microsoft Corp announce partnership",
            ],
            "summary": ["", "", "", ""],
        }
    )


def test_headlines_after_signal_close_are_excluded() -> None:
    news = mod.explode_news(_news_frame())
    asof = pd.Timestamp("2026-05-29T21:00:00Z")  # formation close approximation
    name_map = {"AAPL": "Apple Inc.", "MSFT": "Microsoft Corp"}
    rows = mod.headlines_for(news, "AAPL", asof, name_map)
    ids = {r["id"] for r in rows}
    assert 1 in ids  # before close, included
    assert 4 in ids  # before close, included (shared headline)
    assert 2 not in ids  # visible_at (22:00 UTC) is AFTER asof (21:00 UTC) -> excluded


def test_headlines_outside_lookback_window_are_excluded() -> None:
    news = mod.explode_news(_news_frame())
    # asof far in the future so the 30-day lookback window excludes everything above.
    asof = pd.Timestamp("2026-08-15T21:00:00Z")
    name_map = {"AAPL": "Apple Inc."}
    rows = mod.headlines_for(news, "AAPL", asof, name_map)
    assert rows == []


def test_explode_news_multi_symbol_headline_attributed_to_each_ticker() -> None:
    news = mod.explode_news(_news_frame())
    assert "AAPL" in news and "MSFT" in news
    assert set(news["AAPL"]["id"]) == {1, 2, 4}
    assert set(news["MSFT"]["id"]) == {3, 4}


def test_anonymization_removes_company_name_and_ticker() -> None:
    text = "Apple Inc. announces new product; AAPL shares rise."
    out = mod.anonymize(text, ticker="AAPL", company_name="Apple Inc.")
    assert "Apple" not in out
    assert "AAPL" not in out
    assert out.count("the company") >= 2


def test_anonymization_handles_suffix_variants() -> None:
    # "Apple Inc." should also neutralise a press-release mention that drops
    # the corporate suffix ("Apple announces...").
    text = "Apple announces record profit."
    out = mod.anonymize(text, ticker="AAPL", company_name="Apple Inc.")
    assert "Apple" not in out
    assert "the company" in out


def test_placebo_headlines_never_belong_to_the_scored_stock() -> None:
    tickers = ["AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA", "JPM"]
    for seed in range(50):
        mapping = mod.derangement_map(tickers, seed=seed)
        for t in tickers:
            assert mapping[t] != t, f"seed={seed} ticker={t} mapped to itself"
        # every ticker's headlines are used exactly once (a permutation)
        assert sorted(mapping.values()) == sorted(tickers)


def test_derangement_map_single_ticker_is_itself_by_construction() -> None:
    # Degenerate pool of size 1 has no valid derangement; the function must
    # not crash, and the caller (main()) never invokes P scoring on such a
    # pool since MIN_MEMBERS_FOR_DECILE already guards against tiny pools.
    mapping = mod.derangement_map(["AAPL"], seed=1)
    assert mapping == {"AAPL": "AAPL"}


def test_cache_key_changes_when_headlines_change() -> None:
    item = mod.Item(
        variant="L",
        month="2026-05-29",
        ticker="AAPL",
        headline_ticker="AAPL",
        asof=pd.Timestamp("2026-05-29T21:00:00Z"),
        horizon=pd.Timestamp("2026-06-30T21:00:00Z"),
    )
    h1 = mod.item_hash(item, headline_ids=[1, 2, 3])
    h2 = mod.item_hash(item, headline_ids=[1, 2, 4])
    h3 = mod.item_hash(item, headline_ids=[1, 2, 3])
    assert h1 != h2
    assert h1 == h3  # deterministic given the same inputs


def test_cache_key_changes_when_variant_or_headline_ticker_changes() -> None:
    base = dict(
        month="2026-05-29",
        ticker="AAPL",
        asof=pd.Timestamp("2026-05-29T21:00:00Z"),
        horizon=pd.Timestamp("2026-06-30T21:00:00Z"),
    )
    item_l = mod.Item(variant="L", headline_ticker="AAPL", **base)
    item_p = mod.Item(variant="P", headline_ticker="MSFT", **base)
    h_l = mod.item_hash(item_l, headline_ids=[1, 2])
    h_p = mod.item_hash(item_p, headline_ids=[1, 2])
    assert h_l != h_p


def test_parse_score_extracts_and_clips_a_bare_number() -> None:
    assert mod.parse_score("0.7341") == 0.7341
    assert mod.parse_score("The score is 0.42.") == 0.42
    assert mod.parse_score("1.5") == 1.0  # clipped to [0, 1]
    assert mod.parse_score("-0.3") == 0.0  # clipped
    assert mod.parse_score("no number here") is None
