"""The channel-expansion helpers in ``scripts/harvest_expand.py``.

The script runs under the search-tools venv; these tests load it from its path
and cover only the parsing and ranking, which need no network.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


@pytest.fixture(scope="module")
def hx():
    sys.path.insert(0, str(SCRIPTS))
    spec = importlib.util.spec_from_file_location("harvest_expand", SCRIPTS / "harvest_expand.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["harvest_expand"] = module
    spec.loader.exec_module(module)
    yield module
    sys.modules.pop("harvest_expand", None)
    sys.modules.pop("harvest_search", None)
    sys.path.remove(str(SCRIPTS))


def _account(handle: str, followers: int) -> dict:
    return {"handle": handle, "name": handle, "followers": followers, "bio": "", "url": ""}


def test_cofollow_keeps_accounts_several_seeds_follow(hx) -> None:
    following = {
        "a": [_account("shared", 10), _account("big_shared", 900), _account("only_a", 5)],
        "b": [_account("Shared", 10), _account("big_shared", 900), _account("c", 1)],
        "c": [_account("big_shared", 900)],
    }
    ranked = hx.rank_cofollow(following, min_seeds=2)
    assert [row["handle"] for row in ranked] == ["big_shared", "shared"]
    assert ranked[0]["followed_by"] == ["a", "b", "c"]
    assert ranked[1]["seed_count"] == 2  # handles match case-insensitively
    assert not ranked[0]["is_seed"]
    assert all(row["handle"] != "only_a" for row in ranked)


def _page(recs: list[dict]) -> str:
    state = json.dumps({"recommendations": recs})
    return f"<script>window._preloads = JSON.parse({json.dumps(state)})</script>"


def test_substack_recommendations_parse_from_preloaded_state(hx) -> None:
    html = _page(
        [
            {
                "description": "top blokes",
                "recommendedPublication": {
                    "name": "Methods to the Madness",
                    "subdomain": "twoquants",
                    "custom_domain": None,
                    "hero_text": "systematic trading",
                },
            },
            {"recommendedPublication": {"name": "Q", "custom_domain": "www.Quantitativo.com"}},
            {"recommendedPublication": {"name": "no host"}},
        ]
    )
    pubs = hx.parse_substack_recs(html)
    assert [pub["host"] for pub in pubs] == ["twoquants.substack.com", "www.quantitativo.com"]
    assert pubs[0]["blurb"] == "top blokes"
    assert hx.parse_substack_recs("<html>no state</html>") == []


def test_recommendations_rank_by_distinct_recommenders(hx) -> None:
    pub = {"name": "x", "about": "", "blurb": ""}
    recs = {
        "a.substack.com": [{**pub, "host": "x.com"}, {**pub, "host": "b.substack.com"}],
        "b.substack.com": [{**pub, "host": "x.com"}, {**pub, "host": "x.com"}],
    }
    ranked = hx.rank_recs(recs, min_pubs=1)
    assert [(row["host"], row["rec_count"]) for row in ranked] == [
        ("x.com", 2),
        ("b.substack.com", 1),
    ]
    assert ranked[1]["walked"] and not ranked[0]["walked"]
