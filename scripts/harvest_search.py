#!/usr/bin/env python3
"""Search the channels we could not reach, read the posts, and rank them with Jev.

Runs under the search-tools venv (``/opt/oc-search/venv``), not the project venv,
so the browser stack (curl_cffi, camoufox, trafilatura) never touches the
project's pinned packages. ``scripts/setup_search_tools.sh`` builds it.

    /opt/oc-search/venv/bin/python scripts/harvest_search.py run \\
        --channel exa --query "leveraged ETF rotation with live results"

``run`` searches one channel, reads each new result, asks Jev (TypeSafe's
decision model) six typed questions about it, and writes

- ``reports/research/harvest/raw/<date>/<slug>.jsonl``: results ranked by Jev,
  each with a short excerpt, how the page was read, and Jev's answers;
- one row in ``reports/research/harvest/search-log.jsonl``.

Channels: ``exa`` (semantic web search), ``web`` (local SearXNG; ``--site``),
``reddit`` (the Arctic Shift archive, posts plus top comments), ``x`` (X search or
``--x-user`` timelines through the owner's cookie once ``x-login`` has stored it;
without it, tweets found by search engines), ``github`` and ``archive``
(researcher.marketmaker.cc: Quantocracy-listed blog posts 2015-04..2026-05,
TradingView scripts, arXiv q-fin and GitHub repos; ``--corpus``).

Jev only orders the reading list. Numbers in posts stay author-reported, and a
direction enters ``directions.jsonl`` only after ``oc research directions check``.
Full page text is cached outside the repo, in ``/opt/oc-search/cache``.
Runs that read xueqiu/zhihu start a browser: wrap them in
``scripts/run_capped.sh --mem 1.8G --``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

ROOT = Path(__file__).resolve().parents[1]
HARVEST = ROOT / "reports" / "research" / "harvest"
TOOLS = Path(os.environ.get("OC_SEARCH_HOME", "/opt/oc-search"))
KEY_FILE = Path(os.environ.get("OC_SEARCH_ENV", "/root/.config/open-composer/search.env"))

SEARXNG = "http://127.0.0.1:8888"
EXA_MCP = "https://mcp.exa.ai/mcp"
ARCTIC = "https://arctic-shift.photon-reddit.com/api"
ARCHIVE = "https://researcher.marketmaker.cc/api/v1"
JEV_URL = "https://api.typesafe.ai/v1/systemone"

# Engines that answered from this server on 2026-09-23; the second set honours site:.
# Chinese engines (360search, sogou) also answered, but the owner ruled on 09-23 that
# first-hand US-equity information rarely appears on the Chinese internet.
WEB_ENGINES = "google,brave,bing,yahoo"
SITE_ENGINES = "google,brave,yahoo"
# Still readable when a link turns up: Aliyun WAF (xueqiu) and zhihu's captcha only
# let a real browser through; JoinQuant refuses non-mainland IPs, Exa keeps a copy.
BROWSER_HOSTS = ("xueqiu.com", "zhihu.com")
EXA_ONLY_HOSTS = ("joinquant.com",)
DEFAULT_SUBREDDITS = ("algotrading", "quant", "LETFs", "options", "investing")
CHANNELS = ("exa", "web", "reddit", "x", "github", "archive")
ARCHIVE_CORPORA = ("articles", "pine", "papers", "repos")
DEFAULT_CORPORA = ("articles", "pine", "papers")
# twscrape keeps the owner's X cookie session here (mode 600, outside the repo).
X_DB = TOOLS / "x-accounts.db"
X_ACCOUNT = "oc_x"
MIN_TEXT = 400
MIN_TWEET = 20
STATE_CHARS = 6000
EXCERPT_CHARS = 400

QUESTIONS: dict[str, dict[str, Any]] = {
    "concrete": {
        "type": "noul",
        "instructions": "The text describes a trading strategy, signal or factor "
        "with rules specific enough to backtest",
    },
    "evidence": {
        "type": "choice",
        "instructions": "The strongest performance evidence the text gives for its strategy",
        "criteria": {
            "live_record": "Real-money or tracked forward results after the rules were fixed",
            "backtest": "A historical backtest only",
            "claim_only": "Performance claims without a backtest or record",
            "none": "No performance evidence",
        },
    },
    "market": {
        "type": "choice",
        "instructions": "The market the strategy trades",
        "criteria": {
            "us_stocks_etfs": "US stocks or US-listed ETFs",
            "china_a_shares": "China A-shares or China-listed funds",
            "crypto": "Cryptocurrencies",
            "derivatives": "Futures, forex or options",
            "other": "Other markets, several markets, or unclear",
        },
    },
    "us_long_only": {
        "type": "noul",
        "instructions": "An individual could run it long-only in US stocks or ETFs "
        "on daily or intraday bars",
    },
    "recent": {"type": "noul", "instructions": "It reports results covering 2023 or later"},
    "code": {"type": "noul", "instructions": "It links to or includes runnable code"},
}
EVIDENCE_WEIGHT = {"live_record": 1.0, "backtest": 0.6, "claim_only": 0.3, "none": 0.1}
#: ``--profile channels``: the page is judged as a pointer to places worth
#: searching (level-1/2 channel discovery), not as a strategy.
CHANNEL_QUESTIONS: dict[str, dict[str, Any]] = {
    "directory": {
        "type": "noul",
        "instructions": "The text names or recommends specific places where people share "
        "systematic-trading strategies, factors, backtests or research: forums, communities, "
        "chat groups, newsletters, blogs, social accounts, paper or data feeds, code hubs or "
        "search tools",
    },
    "kind": {
        "type": "choice",
        "instructions": "The main kind of place the text points to",
        "criteria": {
            "community": "Forums, subreddits, Discord, Slack or Telegram groups",
            "publication": "Newsletters, blogs, aggregators or research sites",
            "social": "X/Twitter or other social media accounts or lists",
            "papers_data": "Paper series, preprint feeds, data libraries or backtest databases",
            "code_tools": "Code repositories, curated lists, search or research tools",
            "other": "Something else or unclear",
        },
    },
    "active": {
        "type": "noul",
        "instructions": "The text shows that the places it names were active in 2025 or 2026",
    },
    "us_equity": {
        "type": "noul",
        "instructions": "The places it names cover systematic trading of US stocks or ETFs, "
        "not only crypto or forex",
    },
    "free": {
        "type": "noul",
        "instructions": "The places it names can be read for free without an invitation",
    },
}


@dataclass
class Result:
    url: str
    title: str
    engine: str
    published: str = ""
    snippet: str = ""
    extra: dict[str, Any] = field(default_factory=dict)
    read_via: str = ""
    text_chars: int = 0
    excerpt: str = ""
    jev: dict[str, Any] = field(default_factory=dict)
    priority: float | None = None


# --------------------------------------------------------------------------- helpers


def _http():
    from curl_cffi import requests

    return requests


def normalize_url(url: str) -> str:
    parts = urlsplit(url.strip())
    path = parts.path.rstrip("/") or "/"
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, parts.query, ""))


def load_key(name: str = "JEV_API_KEY") -> str | None:
    if os.environ.get(name):
        return os.environ[name]
    if not KEY_FILE.is_file():
        return None
    for line in KEY_FILE.read_text(encoding="utf-8").splitlines():
        if line.startswith(f"{name}="):
            return line.split("=", 1)[1].strip().strip("'\"")
    return None


def search_id(date: str, channel: str, query: str, existing: set[str]) -> str:
    words = re.findall(r"[a-z0-9]+", query.lower())[:4]
    digest = hashlib.sha1(query.encode("utf-8")).hexdigest()[:6]
    base = f"search:{date.replace('-', '')}:{channel}:{'_'.join(words + [digest])}"
    candidate, n = base, 2
    while candidate in existing:
        candidate, n = f"{base}_{n}", n + 1
    return candidate


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def seen_urls() -> set[str]:
    urls = set()
    for path in sorted((HARVEST / "raw").glob("*/*.jsonl")):
        urls.update(normalize_url(row["url"]) for row in read_jsonl(path) if row.get("url"))
    for row in read_jsonl(HARVEST / "directions.jsonl"):
        for source in row.get("sources") or []:
            if source.get("url"):
                urls.add(normalize_url(source["url"]))
    return urls


# --------------------------------------------------------------------------- search


def _exa_call(tool: str, arguments: dict[str, Any], timeout: int = 90) -> str:
    body = {"jsonrpc": "2.0", "id": 1, "method": "tools/call"}
    body["params"] = {"name": tool, "arguments": arguments}
    headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
    resp = _http().post(EXA_MCP, json=body, headers=headers, timeout=timeout)
    resp.raise_for_status()
    match = re.search(r"^data: (\{.*\})$", resp.text, re.M)
    payload = json.loads(match.group(1) if match else resp.text)
    if payload.get("error"):
        raise RuntimeError(f"exa {tool}: {payload['error']}")
    parts = (payload.get("result") or {}).get("content") or []
    return "".join(part.get("text", "") for part in parts)


def parse_exa_results(text: str) -> list[Result]:
    results = []
    for block in re.split(r"(?m)^Title: ", text)[1:]:
        title, _, rest = block.partition("\n")
        url = re.search(r"(?m)^URL: (\S+)", rest)
        if not url:
            continue
        published = re.search(r"(?m)^Published: (\S+)", rest)
        snippet = rest.split("Highlights:", 1)[1] if "Highlights:" in rest else ""
        results.append(
            Result(
                url=url.group(1),
                title=title.strip(),
                engine="exa",
                published=published.group(1)[:10] if published else "",
                snippet=snippet.strip()[:1500],
            )
        )
    return results


def search_exa(query: str, n: int) -> tuple[list[Result], str]:
    return parse_exa_results(_exa_call("web_search_exa", {"query": query, "numResults": n})), ""


def ensure_searxng() -> None:
    http = _http()

    def healthy() -> bool:
        try:
            return http.get(f"{SEARXNG}/healthz", timeout=3).status_code == 200
        except Exception:
            return False

    if healthy():
        return
    env = {**os.environ, "SEARXNG_SETTINGS_PATH": str(TOOLS / "searxng-settings.yml")}
    with open(TOOLS / "searxng.log", "ab") as log:
        subprocess.Popen(
            [str(TOOLS / "sxvenv" / "bin" / "python"), "-m", "searx.webapp"],
            cwd=TOOLS,
            env=env,
            stdout=log,
            stderr=log,
            start_new_session=True,
        )
    for _ in range(40):
        time.sleep(1)
        if healthy():
            return
    raise RuntimeError(f"SearXNG did not start; see {TOOLS / 'searxng.log'}")


def search_searxng(query: str, n: int, engines: str) -> tuple[list[Result], str]:
    ensure_searxng()
    params = {"q": query, "format": "json", "engines": engines}
    data = _http().get(f"{SEARXNG}/search", params=params, timeout=90).json()
    results = [
        Result(
            url=row["url"],
            title=(row.get("title") or "").strip(),
            engine="searxng:" + ",".join(row.get("engines") or []),
            published=(row.get("publishedDate") or "")[:10],
            snippet=(row.get("content") or "").strip()[:1500],
        )
        for row in data.get("results", [])[:n]
    ]
    failed = "; ".join(f"{name}: {why}" for name, why in data.get("unresponsive_engines", []))
    return results, (f"unresponsive engines: {failed}" if failed else "")


def _arctic_posts(params: dict[str, Any]) -> tuple[list[dict[str, Any]], str]:
    """Arctic Shift answers 422 "Timeout. Maybe slow down a bit" on heavy searches."""
    error = ""
    for wait in (0, 5, 15):
        time.sleep(wait)
        resp = _http().get(f"{ARCTIC}/posts/search", params=params, timeout=60)
        if resp.status_code == 200:
            return resp.json().get("data") or [], ""
        try:
            error = resp.json().get("error") or f"HTTP {resp.status_code}"
        except ValueError:
            error = f"HTTP {resp.status_code}"
    return [], error


def search_reddit(query: str, n: int, subreddits: list[str]) -> tuple[list[Result], str]:
    results, notes = [], []
    for sub in subreddits:
        base = {"subreddit": sub, "limit": min(n, 100), "sort": "desc"}
        posts, error = _arctic_posts({**base, "query": query})
        if error:  # full-text search timed out; titles are indexed more cheaply
            posts, error = _arctic_posts({**base, "title": query})
            notes.append(f"r/{sub}: full-text search failed, titles only")
        if error:
            notes.append(f"r/{sub}: skipped ({error})")
        for post in posts:
            created = datetime.fromtimestamp(post.get("created_utc") or 0, UTC)
            body = (post.get("selftext") or "").strip()
            results.append(
                Result(
                    url="https://www.reddit.com" + post["permalink"],
                    title=post.get("title", "").strip(),
                    engine=f"arctic_shift:r/{sub}",
                    published=created.date().isoformat(),
                    snippet=body[:1500],
                    extra={"score": post.get("score"), "num_comments": post.get("num_comments")},
                )
            )
        time.sleep(2)
    return results, "; ".join(notes)


def search_github(query: str, n: int) -> tuple[list[Result], str]:
    params = {"q": query, "sort": "stars", "per_page": min(n, 50)}
    headers = {"Accept": "application/vnd.github+json"}
    token = load_key("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    resp = _http().get(
        "https://api.github.com/search/repositories", params=params, headers=headers, timeout=30
    )
    if resp.status_code in (403, 429) and not token:
        # The unauthenticated search API is rate limited per IP (403 from this
        # server on 2026-09-23); a site-restricted web search still finds repos.
        results, _ = search_searxng(f"site:github.com {query}", n, SITE_ENGINES)
        repos = [r for r in results if re.match(r"https://github\.com/[^/]+/[^/?#]+/?$", r.url)]
        return repos, f"github api {resp.status_code} without GITHUB_TOKEN; used site:github.com"
    resp.raise_for_status()
    results = [
        Result(
            url=repo["html_url"],
            title=repo["full_name"],
            engine="github",
            published=(repo.get("pushed_at") or "")[:10],
            snippet=f"{repo.get('description') or ''} | stars {repo.get('stargazers_count')}",
            extra={"stars": repo.get("stargazers_count"), "archived": repo.get("archived")},
        )
        for repo in resp.json().get("items", [])
    ]
    return results, ""


def archive_corpora(args: argparse.Namespace) -> list[str]:
    return list(getattr(args, "corpus", None) or DEFAULT_CORPORA)


def archive_result(corpus: str, item: dict[str, Any]) -> Result:
    """One researcher.marketmaker.cc hit. Blog URLs are Wayback snapshots, which
    also keeps them readable after the original post moves."""
    if corpus == "articles":
        return Result(
            url=item["url"],
            title=item.get("title") or "",
            engine="archive:articles",
            published=(item.get("date") or "")[:10],
            snippet=f"{item.get('source') or ''}: {item.get('desc') or ''}",
            extra={"source": item.get("source")},
        )
    if corpus == "pine":
        return Result(
            url=item["url"],
            title=item.get("title") or "",
            engine="archive:pine",
            published=(item.get("date") or "")[:10],
            snippet=f"{item.get('type') or ''} by {item.get('author') or ''}, "
            f"{item.get('likes')} likes: {item.get('desc') or ''}",
            extra={"likes": item.get("likes"), "type": item.get("type")},
        )
    if corpus == "papers":
        return Result(
            url=item["url"],
            title=item.get("title") or "",
            engine="archive:papers",
            published=(item.get("published") or "")[:10],
            snippet=(item.get("abstract") or "")[:EXCERPT_CHARS],
            extra={"categories": item.get("categories")},
        )
    return Result(
        url=item["url"],
        title=item.get("name") or "",
        engine="archive:repos",
        published=(item.get("created_at") or "")[:10],
        snippet=f"{item.get('description') or ''} | stars {item.get('stars')}",
        extra={"stars": item.get("stars")},
    )


def search_archive(query: str, n: int, corpora: list[str]) -> tuple[list[Result], str]:
    """Articles and scripts match every word, so keep those queries to one or
    two words; papers and repos rank by relevance."""
    results: list[Result] = []
    notes = []
    for corpus in corpora:
        resp = _http().get(
            f"{ARCHIVE}/{corpus}", params={"q": query, "limit": min(n, 100)}, timeout=30
        )
        resp.raise_for_status()
        body = resp.json()
        notes.append(f"{corpus} {body.get('total', 0)} hits")
        results.extend(archive_result(corpus, item) for item in body.get("items", []))
    return results, "; ".join(notes)


def tweet_id(url: str) -> str | None:
    match = re.search(r"(?:x|twitter)\.com/[^/?#]+/status(?:es)?/(\d+)", url)
    return match.group(1) if match else None


def _x_api():
    from twscrape import API

    return API(str(X_DB), raise_when_no_account=True, wait_timeout=60)


def x_ready() -> bool:
    """True once ``x-login`` has stored an active cookie session."""
    if not X_DB.is_file():
        return False
    import asyncio

    return any(info.get("active") for info in asyncio.run(_x_api().pool.accounts_info()))


def search_x(query: str, n: int, user: str | None) -> tuple[list[Result], str, str]:
    """X search or one account's timeline through the owner's cookie session.

    Without a cookie, X's own search is out of reach; tweets are then found by
    search engines (``site:x.com``) and read one by one through fxtwitter.
    """
    if not x_ready():
        if user:
            raise RuntimeError("an account timeline needs an X cookie: run `x-login` first")
        results, notes = search_searxng(f"site:x.com {query}", n, SITE_ENGINES)
        note = "no X cookie: tweets found through search engines only"
        tool = f"harvest_search.py:searxng({SITE_ENGINES}) site:x.com"
        return [r for r in results if tweet_id(r.url)], tool, f"{note}; {notes}".strip("; ")

    import asyncio

    async def collect():
        from twscrape import gather

        api = _x_api()
        if user:
            profile = await api.user_by_login(user)
            if profile is None:
                raise RuntimeError(f"no X account @{user}")
            return await gather(api.user_tweets(profile.id, limit=n))
        return await gather(api.search(query, limit=n, kv={"product": "Latest"}))

    results = [
        Result(
            url=tweet.url,
            title=tweet.rawContent.split("\n", 1)[0][:120],
            engine="x:twscrape",
            published=tweet.date.date().isoformat(),
            snippet=tweet.rawContent[:1500],
            extra={
                "author": tweet.user.username,
                "likes": tweet.likeCount,
                "retweets": tweet.retweetCount,
                "views": tweet.viewCount,
                "tweet_text": tweet.rawContent,
            },
        )
        for tweet in asyncio.run(collect())[:n]
    ]
    return results, "harvest_search.py:twscrape", ""


def run_search(args: argparse.Namespace) -> tuple[list[Result], str, str]:
    """Return results, a tool label for the search log, and engine notes."""
    if args.channel == "exa":
        results, notes = search_exa(args.query, args.n)
        return results, "harvest_search.py:exa_mcp", notes
    if args.channel == "web":
        query = f"site:{args.site} {args.query}" if args.site else args.query
        engines = args.engines or (SITE_ENGINES if args.site else WEB_ENGINES)
        results, notes = search_searxng(query, args.n, engines)
        return results, f"harvest_search.py:searxng({engines})", notes
    if args.channel == "reddit":
        subs = args.subreddit or list(DEFAULT_SUBREDDITS)
        results, notes = search_reddit(args.query, args.n, subs)
        return results, f"harvest_search.py:arctic_shift({','.join(subs)})", notes
    if args.channel == "x":
        return search_x(args.query, args.n, getattr(args, "x_user", None))
    if args.channel == "archive":
        corpora = archive_corpora(args)
        results, notes = search_archive(args.query, args.n, corpora)
        return results, f"harvest_search.py:marketmaker_archive({','.join(corpora)})", notes
    results, notes = search_github(args.query, args.n)
    return results, "harvest_search.py:github_api", notes


# --------------------------------------------------------------------------- read


BLOCK_MARKERS = (
    "You've been blocked",
    "Target URL returned error 4",
    "requiring CAPTCHA",
    "Just a moment...",
    "Access Denied",
    "_waf_",
    "当前地区暂不支持访问",
    "安全验证",
    "没有知识存在的荒原",
)


def looks_blocked(text: str) -> bool:
    """A block, captcha or not-found page is long enough to pass for an article."""
    head = text[:1200]
    return any(marker in head for marker in BLOCK_MARKERS)


def reddit_post_id(url: str) -> str | None:
    match = re.search(r"/comments/([a-z0-9]+)", url)
    return match.group(1) if match else None


def format_top_comments(tree: list[dict[str, Any]], keep: int = 8, chars: int = 400) -> str:
    comments = [node.get("data") or {} for node in tree]
    live = [c for c in comments if c.get("body") and c["body"] not in ("[removed]", "[deleted]")]
    live.sort(key=lambda c: -(c.get("score") or 0))
    if not live:
        return ""
    lines = []
    for comment in live[:keep]:
        body = re.sub(r"\s+", " ", comment["body"])[:chars]
        lines.append(f"- ({comment.get('score')}) {body}")
    return "\n\nTop comments:\n" + "\n".join(lines)


def _extract(html: str) -> str:
    import trafilatura

    text = trafilatura.extract(html, include_comments=False, favor_recall=True) or ""
    if len(text) < MIN_TEXT:
        stripped = re.sub(r"(?s)<(script|style)\b.*?</\1>", " ", html)
        text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", stripped)).strip()
    return text


class Reader:
    """Read a page by the cheapest path that works for its host, with a disk cache."""

    def __init__(self) -> None:
        self._camoufox = None
        self._page = None
        (TOOLS / "cache").mkdir(parents=True, exist_ok=True)

    def close(self) -> None:
        if self._camoufox is not None:
            self._camoufox.__exit__(None, None, None)
            self._camoufox = self._page = None

    def read(self, result: Result) -> tuple[str, str]:
        """Return (text, how it was read); how is "none" when no path produced text."""
        url, host = result.url, (urlsplit(result.url).hostname or "")
        if result.extra.get("tweet_text"):  # twscrape already returned the whole tweet
            author = result.extra.get("author", "")
            return f"@{author} ({result.published}): {result.extra['tweet_text']}", "twscrape"
        # v2: Reddit reads include the top comments.
        cache = TOOLS / "cache" / (hashlib.sha1(f"v2:{url}".encode()).hexdigest() + ".json")
        if cache.is_file():
            cached = json.loads(cache.read_text(encoding="utf-8"))
            if not looks_blocked(cached["text"]):
                return cached["text"], cached["via"] + "(cached)"
        minimum = MIN_TWEET if tweet_id(url) else MIN_TEXT
        if tweet_id(url):
            attempts = [("fxtwitter", self._fxtwitter), ("x_oembed", self._oembed)]
        elif host.endswith("reddit.com") and reddit_post_id(url):
            attempts = [("arctic_shift", self._arctic), ("exa_fetch", self._exa)]
        elif host.endswith(EXA_ONLY_HOSTS):
            attempts = [("exa_fetch", self._exa)]
        elif host.endswith(BROWSER_HOSTS):
            attempts = [("camoufox", self._browser), ("exa_fetch", self._exa)]
        else:
            attempts = [("direct", self._direct), ("jina", self._jina), ("exa_fetch", self._exa)]
        text, via = "", "none"
        for name, fetch in attempts:
            try:
                text = fetch(url)
            except Exception as exc:  # a failed path falls through to the next one
                print(f"  read {name} failed for {url[:70]}: {str(exc)[:90]}", file=sys.stderr)
                text = ""
            if len(text) >= minimum and not looks_blocked(text):
                via = name
                break
            text = ""
        if via != "none":
            cache.write_text(json.dumps({"url": url, "via": via, "text": text}), encoding="utf-8")
        return text, via

    def _arctic(self, url: str) -> str:
        """The post plus its highest-scored top-level comments, where critiques and
        the author's later live results usually are."""
        http, post_id = _http(), reddit_post_id(url)
        resp = http.get(f"{ARCTIC}/posts/ids", params={"ids": post_id}, timeout=60)
        resp.raise_for_status()
        posts = resp.json().get("data") or []
        if not posts:
            return ""
        text = f"{posts[0].get('title', '')}\n\n{posts[0].get('selftext') or ''}".strip()
        tree = http.get(f"{ARCTIC}/comments/tree", params={"link_id": post_id}, timeout=60)
        if tree.status_code == 200:
            text += format_top_comments(tree.json().get("data") or [])
        return text

    def _fxtwitter(self, url: str) -> str:
        resp = _http().get(
            f"https://api.fxtwitter.com/status/{tweet_id(url)}", impersonate="chrome", timeout=30
        )
        tweet = (resp.json().get("tweet") or {}) if resp.status_code == 200 else {}
        if not tweet.get("text"):
            return ""
        author = (tweet.get("author") or {}).get("screen_name", "")
        text = f"@{author} ({tweet.get('created_at', '')}): {tweet['text']}"
        quoted = (tweet.get("quote") or {}).get("text")
        if quoted:
            text += f"\n\nQuoted: {quoted}"
        return text + f"\n[likes {tweet.get('likes')}, replies {tweet.get('replies')}]"

    def _oembed(self, url: str) -> str:
        resp = _http().get(
            "https://publish.twitter.com/oembed",
            params={"url": url, "omit_script": 1},
            timeout=30,
        )
        html = resp.json().get("html", "") if resp.status_code == 200 else ""
        return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html)).strip()

    def _direct(self, url: str) -> str:
        resp = _http().get(url, impersonate="chrome", timeout=40)
        return _extract(resp.text) if resp.status_code == 200 else ""

    def _jina(self, url: str) -> str:
        resp = _http().get("https://r.jina.ai/" + url, timeout=60)
        return resp.text if resp.status_code == 200 else ""

    def _exa(self, url: str) -> str:
        text = _exa_call("web_fetch_exa", {"urls": [url], "maxCharacters": 20000})
        return "" if text.startswith("Error fetching") else text

    def _browser(self, url: str) -> str:
        if self._page is None:
            from camoufox.sync_api import Camoufox

            self._camoufox = Camoufox(headless=True, block_images=True, i_know_what_im_doing=True)
            self._page = self._camoufox.__enter__().new_page()
        self._page.goto(url, timeout=45000, wait_until="domcontentloaded")
        self._page.wait_for_timeout(5000)
        return _extract(self._page.content())


# --------------------------------------------------------------------------- triage


def jev_answers(
    state: str, key: str, profile: str = "strategies"
) -> tuple[dict[str, Any], int, str]:
    questions = CHANNEL_QUESTIONS if profile == "channels" else QUESTIONS
    body = {"model": "jev-latest", "state": state, "questions": questions}
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    for attempt in range(5):
        resp = _http().post(JEV_URL, json=body, headers=headers, timeout=60)
        if resp.status_code in (429, 500, 502, 503, 529):
            time.sleep(2**attempt)
            continue
        resp.raise_for_status()
        data = resp.json()
        answers = data["answers"]
        usage = int((data.get("usage") or {}).get("input_tokens") or 0)
        if profile == "channels":
            flat = {name: answers[name]["noul"] for name in ("directory", "active", "us_equity")}
            flat["free"] = answers["free"]["noul"]
            flat["kind"] = answers["kind"]["choice"]
            return flat, usage, data.get("model", "")
        flat = {
            "concrete": answers["concrete"]["noul"],
            "evidence": answers["evidence"]["choice"],
            "evidence_confidence": answers["evidence"].get("confidence"),
            "market": answers["market"]["choice"],
            "us_long_only": answers["us_long_only"]["noul"],
            "recent": answers["recent"]["noul"],
            "code": answers["code"]["noul"],
        }
        return flat, int((data.get("usage") or {}).get("input_tokens") or 0), data.get("model", "")
    raise RuntimeError("Jev kept answering 429/5xx; retry later")


def channel_priority(jev: dict[str, Any]) -> float:
    """Reading order for channel discovery: names places, active, US equities, free."""
    score = jev["directory"] * (0.5 + 0.5 * jev["active"]) * (0.4 + 0.6 * jev["us_equity"])
    return round(score * (0.6 + 0.4 * jev["free"]), 3)


def priority(jev: dict[str, Any]) -> float:
    """Reading order only: concrete rules, US long-only fit, evidence, recency, code."""
    fit = max(jev["us_long_only"], 1.0 if jev["market"] == "us_stocks_etfs" else 0.0)
    score = jev["concrete"] * (0.3 + 0.7 * fit) * EVIDENCE_WEIGHT[jev["evidence"]]
    return round(score * (1 + 0.5 * jev["recent"]) * (1 + 0.2 * jev["code"]), 3)


# --------------------------------------------------------------------------- commands


def query_label(args: argparse.Namespace, today: str) -> str:
    """The search as logged; a repeat of a logged label is refused."""
    x_user = getattr(args, "x_user", None)
    if x_user:  # a timeline is worth re-reading on another day
        label = f"@{x_user.lstrip('@')} timeline {today}"
    else:
        label = f"site:{args.site} {args.query}" if args.site else args.query
    if args.channel == "archive" and getattr(args, "corpus", None):
        label = f"{label} [{','.join(archive_corpora(args))}]"
    if getattr(args, "profile", "strategies") == "channels":
        label = f"[channels] {label}"
    return label


def cmd_run(args: argparse.Namespace) -> int:
    today = datetime.now(UTC).date().isoformat()
    log_path = HARVEST / "search-log.jsonl"
    log_rows = read_jsonl(log_path)
    label = query_label(args, today)
    profile = getattr(args, "profile", "strategies")
    repeats = [
        r["id"] for r in log_rows if r.get("channel") == args.channel and r["query"] == label
    ]
    if repeats and not args.force:
        print(f"already searched: {', '.join(repeats)} (use --force to search again)")
        return 1
    key = None if args.no_triage else load_key()
    if not args.no_triage and not key:
        print(f"no JEV_API_KEY in the environment or {KEY_FILE}; use --no-triage", file=sys.stderr)
        return 2

    results, tool, notes = run_search(args)
    seen = seen_urls()
    fresh = []
    for result in results:
        if normalize_url(result.url) in seen:
            continue
        seen.add(normalize_url(result.url))
        fresh.append(result)
    print(f"{len(results)} results, {len(fresh)} not seen before ({tool})")

    reader, tokens, model = Reader(), 0, ""
    try:
        for index, result in enumerate(fresh[: args.max_read]):
            text, result.read_via = reader.read(result)
            body = text
            if result.read_via == "none":
                body, result.read_via = result.snippet, "snippet"
            result.text_chars = len(body)
            result.excerpt = re.sub(r"\s+", " ", body)[:EXCERPT_CHARS]
            result.extra.pop("tweet_text", None)
            if key:
                state = f"Title: {result.title}\nURL: {result.url}\n"
                state += f"Published: {result.published}\n\n{body[:STATE_CHARS]}"
                result.jev, used, model = jev_answers(state, key, profile)
                rank = channel_priority if profile == "channels" else priority
                result.priority = rank(result.jev)
                tokens += used
            print(
                f"  [{index + 1}/{min(len(fresh), args.max_read)}] {result.read_via:16} "
                f"{result.priority if result.priority is not None else '-':>5} "
                f"{result.title[:60]}"
            )
    finally:
        reader.close()

    kept = fresh[: args.max_read]
    kept.sort(key=lambda r: -(r.priority or 0.0))
    entry_id = search_id(today, args.channel, label, {r["id"] for r in log_rows})
    raw_path = HARVEST / "raw" / today / f"{entry_id.split(':', 2)[2].replace(':', '_')}.jsonl"
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    with raw_path.open("w", encoding="utf-8") as handle:
        for result in kept:
            handle.write(json.dumps(asdict(result), ensure_ascii=False) + "\n")
    summary = (
        f"raw={raw_path.relative_to(ROOT)}; read {sum(r.read_via != 'snippet' for r in kept)}"
        f"/{len(kept)} full pages; jev {model or 'off'} input_tokens={tokens}"
    )
    entry = {
        "id": entry_id,
        "date": today,
        "channel": args.channel,
        "tool": tool,
        "query": label,
        "results_seen": len(results),
        "new_directions": [],
        "notes": f"{summary}; {notes}" if notes else summary,
    }
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
    print(f"\n{entry_id}\n{summary}\n")
    for result in kept[: args.show]:
        jev = result.jev or {}
        print(
            f"{result.priority if result.priority is not None else '-':>6}  "
            f"{jev.get('evidence', jev.get('kind', '-')):11} "
            f"{jev.get('market', 'active' if jev.get('active', 0) >= 0.5 else '-'):14} "
            f"{result.title[:56]}\n        {result.url}"
        )
    return 0


def cmd_fetch(args: argparse.Namespace) -> int:
    reader = Reader()
    try:
        text, via = reader.read(Result(url=args.url, title="", engine="manual"))
    finally:
        reader.close()
    print(f"[{via}] {len(text)} chars\n")
    print(text[: args.chars])
    return 0 if text else 1


def cmd_x_login(args: argparse.Namespace) -> int:
    """Store the owner's X cookie session for twscrape; the cookie is never printed."""
    cookies = load_key("X_COOKIES") or ""
    if "auth_token=" not in cookies or "ct0=" not in cookies:
        print(f"put X_COOKIES='auth_token=...; ct0=...' into {KEY_FILE} first", file=sys.stderr)
        return 2
    import asyncio

    async def store_and_test():
        api = _x_api()
        await api.pool.delete_accounts(X_ACCOUNT)
        await api.pool.add_account_cookies(X_ACCOUNT, cookies)
        return await api.user_by_login(args.test_user)

    old_umask = os.umask(0o077)
    try:
        user = asyncio.run(store_and_test())
    finally:
        os.umask(old_umask)
    X_DB.chmod(0o600)
    if user is None:
        print("cookie stored, but the test lookup failed: it may be expired", file=sys.stderr)
        return 1
    print(f"X cookie works (looked up @{user.username}); session stored in {X_DB}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="search one channel, read, rank with Jev, log")
    run.add_argument("--channel", choices=CHANNELS, required=True)
    run.add_argument("--query", default="", help="required except for --x-user")
    run.add_argument("--site", help="web channel only: restrict to a site, e.g. xueqiu.com")
    run.add_argument("--engines", help="web channel only: override the SearXNG engine list")
    run.add_argument("--subreddit", action="append", help="reddit channel; repeatable")
    run.add_argument("--x-user", help="x channel: read this account's timeline (needs x-login)")
    run.add_argument(
        "--corpus",
        action="append",
        choices=ARCHIVE_CORPORA,
        help=f"archive channel; repeatable (default: {', '.join(DEFAULT_CORPORA)})",
    )
    run.add_argument("--n", type=int, default=10, help="results to request per source")
    run.add_argument("--max-read", type=int, default=20, help="results to read and triage")
    run.add_argument("--show", type=int, default=10)
    run.add_argument("--no-triage", action="store_true", help="skip Jev")
    run.add_argument(
        "--profile",
        choices=("strategies", "channels"),
        default="strategies",
        help="channels: judge pages as pointers to new places to search (channels.jsonl)",
    )
    run.add_argument("--force", action="store_true", help="repeat a logged query")
    run.set_defaults(func=cmd_run)
    fetch = sub.add_parser("fetch", help="read one URL through the same router")
    fetch.add_argument("url")
    fetch.add_argument("--chars", type=int, default=2000)
    fetch.set_defaults(func=cmd_fetch)
    login = sub.add_parser("x-login", help="store the X cookie from search.env and test it")
    login.add_argument("--test-user", default="XDevelopers")
    login.set_defaults(func=cmd_x_login)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "run":
        if args.site and args.channel != "web":
            print("--site only applies to --channel web", file=sys.stderr)
            return 2
        if args.x_user and args.channel != "x":
            print("--x-user only applies to --channel x", file=sys.stderr)
            return 2
        if len(args.query) < 2 and not args.x_user:
            print("--query is required", file=sys.stderr)
            return 2
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
