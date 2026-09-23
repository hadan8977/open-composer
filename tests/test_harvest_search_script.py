"""``scripts/harvest_search.py``: the offline parts of the search -> read -> Jev pipeline.

The script runs under the search-tools venv; these tests only touch the pieces
that decide what gets read and logged: parsing Exa output, spotting block pages
that are long enough to pass for articles, the reading-order score, and the
refusal to repeat a logged query.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "harvest_search.py"


@pytest.fixture(scope="module")
def hs():
    spec = importlib.util.spec_from_file_location("harvest_search", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules["harvest_search"] = module  # dataclasses resolve annotations through it
    spec.loader.exec_module(module)
    yield module
    sys.modules.pop("harvest_search", None)


EXA_TEXT = """Title: Update Q3 2026: Gehrman's ongoing test of 3 leveraged ETF strategies
URL: https://www.reddit.com/r/LETFs/comments/1uk300z/update_q3_2026/
Published: 2026-07-01T12:00:00.000Z
Author: u/Gehrman
Highlights:
9Sig had its best quarter yet.

Title: 自动轮动：用量化程序计算ETF品种的动量
URL: https://xueqiu.com/1118495753/384511870
Published: 2026-04-17T23:00:57.000Z
Author: N/A
Highlights:
数据是动量计算的基础
"""


def test_parse_exa_results(hs) -> None:
    results = hs.parse_exa_results(EXA_TEXT)
    assert [r.url for r in results] == [
        "https://www.reddit.com/r/LETFs/comments/1uk300z/update_q3_2026/",
        "https://xueqiu.com/1118495753/384511870",
    ]
    assert results[0].published == "2026-07-01"
    assert results[0].snippet == "9Sig had its best quarter yet."
    assert results[1].title.startswith("自动轮动")


def test_block_pages_are_not_articles(hs) -> None:
    jina_reddit = (
        "Title:  URL Source: https://www.reddit.com/r/LETFs/comments/1uk300z/\n"
        "Warning: Target URL returned error 403: Forbidden\n"
        "Markdown Content: You've been blocked by network security." + " x" * 300
    )
    assert hs.looks_blocked(jina_reddit)
    assert hs.looks_blocked('{"_waf_bd8ce2ce37":"pRPqp1CL"}' + "a" * 500)
    assert hs.looks_blocked("你似乎来到了没有知识存在的荒原 3 秒后自动跳转至知乎首页")
    assert not hs.looks_blocked("超级二八轮动策略回测 1. 前言 这个双休日" * 40)


def test_reddit_post_id_and_url_normalization(hs) -> None:
    url = "https://www.reddit.com/r/LETFs/comments/1uk300z/update_q3_2026/"
    assert hs.reddit_post_id(url) == "1uk300z"
    assert hs.reddit_post_id("https://xueqiu.com/1118495753/384511870") is None
    assert hs.normalize_url("HTTPS://Example.com/a/b/#frag") == "https://example.com/a/b"


def test_tweet_ids_route_x_links(hs) -> None:
    assert hs.tweet_id("https://x.com/QuantifiedStrat/status/2076003084375851403") == (
        "2076003084375851403"
    )
    assert hs.tweet_id("https://twitter.com/jack/status/20?s=21") == "20"
    assert hs.tweet_id("https://x.com/QuantifiedStrat") is None


def test_top_comments_skip_removed_and_rank_by_score(hs) -> None:
    tree = [
        {"kind": "t1", "data": {"body": "Nice", "score": 3}},
        {"kind": "t1", "data": {"body": "[removed]", "score": 90}},
        {"kind": "t1", "data": {"body": "Overfit: 426 configs\nno OOS", "score": 40}},
    ]
    text = hs.format_top_comments(tree)
    assert text.index("Overfit: 426 configs no OOS") < text.index("Nice")
    assert "[removed]" not in text
    assert hs.format_top_comments([]) == ""


def test_priority_puts_live_us_records_first(hs) -> None:
    base = {"concrete": 0.9, "us_long_only": 0.9, "recent": 1.0, "code": 0.0}
    live = hs.priority({**base, "evidence": "live_record", "market": "us_stocks_etfs"})
    backtest = hs.priority({**base, "evidence": "backtest", "market": "us_stocks_etfs"})
    a_share = hs.priority(
        {**base, "evidence": "live_record", "market": "china_a_shares", "us_long_only": 0.1}
    )
    chatter = hs.priority({**base, "evidence": "none", "market": "us_stocks_etfs"})
    assert live > backtest > chatter
    assert live > a_share


def test_search_id_is_stable_and_unique(hs) -> None:
    first = hs.search_id("2026-09-23", "exa", "Leveraged ETF rotation live", set())
    assert first.startswith("search:20260923:exa:leveraged_etf_rotation_live_")
    assert hs.search_id("2026-09-23", "exa", "Leveraged ETF rotation live", set()) == first
    assert hs.search_id("2026-09-23", "exa", "Leveraged ETF rotation live", {first}) == (
        first + "_2"
    )
    assert hs.search_id("2026-09-23", "web", "行业轮动", set()).startswith("search:20260923:web:")


def test_seen_urls_cover_raw_results_and_registry_sources(hs, tmp_path, monkeypatch) -> None:
    harvest = tmp_path / "harvest"
    (harvest / "raw" / "2026-09-23").mkdir(parents=True)
    (harvest / "raw" / "2026-09-23" / "a.jsonl").write_text(
        json.dumps({"url": "https://a.example/post/"}) + "\n", encoding="utf-8"
    )
    (harvest / "directions.jsonl").write_text(
        json.dumps({"id": "dir:x", "sources": [{"url": "https://b.example/paper"}]}) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(hs, "HARVEST", harvest)
    assert hs.seen_urls() == {"https://a.example/post", "https://b.example/paper"}


def test_run_refuses_a_logged_query_before_any_network_call(hs, tmp_path, monkeypatch) -> None:
    harvest = tmp_path / "harvest"
    harvest.mkdir()
    row = {
        "id": "search:20260923:exa:x",
        "date": "2026-09-23",
        "channel": "exa",
        "tool": "harvest_search.py:exa_mcp",
        "query": "leveraged etf rotation",
    }
    (harvest / "search-log.jsonl").write_text(json.dumps(row) + "\n", encoding="utf-8")
    monkeypatch.setattr(hs, "HARVEST", harvest)

    def no_network(*_args, **_kwargs):
        raise AssertionError("searched although the query is already logged")

    monkeypatch.setattr(hs, "run_search", no_network)
    args = argparse.Namespace(
        channel="exa", query="leveraged etf rotation", site=None, force=False, no_triage=True
    )
    assert hs.cmd_run(args) == 1


def test_archive_results_keep_source_and_popularity(hs) -> None:
    article = hs.archive_result(
        "articles",
        {
            "url": "https://web.archive.org/web/2024/https://alvarezquanttrading.com/blog/x/",
            "title": "UPRO/TQQQ Leveraged ETF Strategy",
            "source": "Alvarez Quant Trading",
            "date": "2024-03-28",
            "desc": "A reader sent me a leveraged ETF strategy.",
        },
    )
    assert article.engine == "archive:articles"
    assert article.published == "2024-03-28"
    assert article.snippet.startswith("Alvarez Quant Trading: ")
    script = hs.archive_result(
        "pine",
        {
            "url": "https://www.tradingview.com/script/cN0h4ehO/",
            "title": "Sector Rotation",
            "author": "Zeiierman",
            "type": "indicator",
            "likes": 229,
            "date": "2026-06-01",
            "desc": "relative strength rotation",
        },
    )
    assert script.extra["likes"] == 229
    assert "229 likes" in script.snippet
    paper = hs.archive_result(
        "papers",
        {"url": "https://arxiv.org/abs/2609.1", "title": "T", "published": "2026-09-01"},
    )
    assert (paper.engine, paper.published) == ("archive:papers", "2026-09-01")
    repo = hs.archive_result(
        "repos", {"url": "https://github.com/a/b", "name": "b", "stars": 5, "created_at": ""}
    )
    assert repo.title == "b" and repo.extra["stars"] == 5


def test_archive_corpus_choice_is_part_of_the_logged_query(hs, tmp_path, monkeypatch) -> None:
    harvest = tmp_path / "harvest"
    harvest.mkdir()
    row = {"id": "search:20260923:archive:x", "channel": "archive", "query": "rotation"}
    (harvest / "search-log.jsonl").write_text(json.dumps(row) + "\n", encoding="utf-8")
    monkeypatch.setattr(hs, "HARVEST", harvest)

    def no_network(*_args, **_kwargs):
        raise AssertionError("searched although the query is already logged")

    monkeypatch.setattr(hs, "run_search", no_network)
    args = argparse.Namespace(
        channel="archive", query="rotation", site=None, corpus=None, force=False, no_triage=True
    )
    assert hs.cmd_run(args) == 1
    assert hs.archive_corpora(args) == list(hs.DEFAULT_CORPORA)
    args.corpus = ["pine"]
    assert hs.query_label(args, "2026-09-23") == "rotation [pine]"
    args.profile = "channels"
    assert hs.query_label(args, "2026-09-23") == "[channels] rotation [pine]"
