#!/usr/bin/env python3
"""Find the next level of places to search from the ones already recorded.

Runs under the search-tools venv like ``harvest_search.py``:

    /opt/oc-search/venv/bin/python scripts/harvest_expand.py x-cofollow \\
        --seed quantpedia --seed Quantocracy --seed therobotjames
    /opt/oc-search/venv/bin/python scripts/harvest_expand.py substack-recs \\
        --pub algoadvantage.substack.com --depth 2

``x-cofollow`` reads whom each seed account follows and ranks the accounts that
several seeds follow. ``substack-recs`` walks Substack's recommendation pages
from the seed publications and ranks publications by how many of the walked
publications recommend them. Both write the ranked list to
``reports/research/harvest/raw/<date>/`` and one row to ``search-log.jsonl``;
nothing enters ``channels.jsonl`` until it is read and checked with
``oc research channels check``.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from collections import deque
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import harvest_search as hs  # noqa: E402

PRELOADS = re.compile(r'window\._preloads\s*=\s*JSON\.parse\("(.*?)"\)</script>', re.S)


def recorded_urls() -> dict[str, str]:
    """Channel URLs already in ``channels.jsonl``, normalized, to their ids."""
    rows = hs.read_jsonl(hs.HARVEST / "channels.jsonl")
    return {_url_key(row["url"]): row["id"] for row in rows if row.get("url")}


def _url_key(url: str) -> str:
    return re.sub(r"^https?://(www\.)?", "", url.lower()).rstrip("/")


def rank_cofollow(
    following: dict[str, list[dict[str, Any]]], min_seeds: int
) -> list[dict[str, Any]]:
    """Accounts followed by at least ``min_seeds`` seeds, most shared first."""
    seeds = {seed.lower() for seed in following}
    by_handle: dict[str, dict[str, Any]] = {}
    for seed, accounts in following.items():
        for account in accounts:
            key = account["handle"].lower()
            row = by_handle.setdefault(key, {**account, "followed_by": []})
            if seed not in row["followed_by"]:
                row["followed_by"].append(seed)
    ranked = [
        {**row, "seed_count": len(row["followed_by"]), "is_seed": key in seeds}
        for key, row in by_handle.items()
        if len(row["followed_by"]) >= min_seeds
    ]
    ranked.sort(key=lambda row: (-row["seed_count"], -(row.get("followers") or 0)))
    return ranked


def parse_substack_recs(html: str) -> list[dict[str, Any]]:
    """Publications a Substack recommends, from the page's preloaded state."""
    match = PRELOADS.search(html)
    if not match:
        return []
    state = json.loads(json.loads(f'"{match.group(1)}"'))
    pubs = []
    for rec in state.get("recommendations") or []:
        pub = rec.get("recommendedPublication") or {}
        host = pub.get("custom_domain") or (
            f"{pub['subdomain']}.substack.com" if pub.get("subdomain") else None
        )
        if host:
            pubs.append(
                {
                    "host": host.lower(),
                    "name": pub.get("name") or host,
                    "about": (pub.get("hero_text") or "")[:300],
                    "blurb": (rec.get("description") or "")[:300],
                }
            )
    return pubs


def rank_recs(recs: dict[str, list[dict[str, Any]]], min_pubs: int) -> list[dict[str, Any]]:
    """Publications recommended by at least ``min_pubs`` walked publications."""
    by_host: dict[str, dict[str, Any]] = {}
    for source, pubs in recs.items():
        for pub in pubs:
            row = by_host.setdefault(pub["host"], {**pub, "recommended_by": []})
            if source not in row["recommended_by"]:
                row["recommended_by"].append(source)
    ranked = [
        {**row, "rec_count": len(row["recommended_by"]), "walked": row["host"] in recs}
        for row in by_host.values()
        if len(row["recommended_by"]) >= min_pubs
    ]
    ranked.sort(key=lambda row: (-row["rec_count"], row["host"]))
    return ranked


def _log(channel: str, tool: str, query: str, rows: list[dict[str, Any]], notes: str) -> Path:
    today = datetime.now(UTC).date().isoformat()
    log_path = hs.HARVEST / "search-log.jsonl"
    existing = {row["id"] for row in hs.read_jsonl(log_path)}
    entry_id = hs.search_id(today, channel, query, existing)
    raw_path = hs.HARVEST / "raw" / today / f"{entry_id.split(':', 2)[2].replace(':', '_')}.jsonl"
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    with raw_path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    entry = {
        "id": entry_id,
        "date": today,
        "channel": channel,
        "tool": tool,
        "query": query,
        "results_seen": len(rows),
        "new_directions": [],
        "notes": f"raw={raw_path.relative_to(hs.ROOT)}; {notes}".strip("; "),
    }
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
    print(f"\n{entry_id}\nraw={raw_path.relative_to(hs.ROOT)}")
    return raw_path


def _refuse_repeat(channel: str, query: str) -> bool:
    repeats = [
        row["id"]
        for row in hs.read_jsonl(hs.HARVEST / "search-log.jsonl")
        if row.get("channel") == channel and row.get("query") == query
    ]
    if repeats:
        print(f"already expanded: {', '.join(repeats)} (use --force to repeat)")
    return bool(repeats)


def cmd_x_cofollow(args: argparse.Namespace) -> int:
    seeds = [seed.lstrip("@") for seed in args.seed]
    query = f"[channels] co-follow of @{', @'.join(seeds)} (>= {args.min_seeds} seeds)"
    if not args.force and _refuse_repeat("x", query):
        return 1
    if not hs.x_ready():
        print("no X session: run harvest_search.py x-login first", file=sys.stderr)
        return 2
    import asyncio

    async def collect() -> tuple[dict[str, list[dict[str, Any]]], list[str]]:
        from twscrape import gather

        api = hs._x_api()
        following, notes = {}, []
        for seed in seeds:
            try:  # a rate limit on one seed keeps what the others returned
                profile = await api.user_by_login(seed)
                if profile is None:
                    notes.append(f"@{seed} not found")
                    continue
                users = await gather(api.following(profile.id, limit=args.per_seed))
            except Exception as exc:
                notes.append(f"@{seed}: {type(exc).__name__}")
                continue
            following[seed] = [
                {
                    "handle": user.username,
                    "name": user.displayname,
                    "followers": user.followersCount,
                    "bio": (user.rawDescription or "")[:300],
                    "url": f"https://x.com/{user.username}",
                }
                for user in users
            ]
            notes.append(f"@{seed} follows {len(users)} read")
        return following, notes

    following, notes = asyncio.run(collect())
    ranked = rank_cofollow(following, args.min_seeds)
    known = recorded_urls()
    for row in ranked:
        row["channel"] = known.get(_url_key(row["url"]), "")
    _log("x", "harvest_expand.py:x_cofollow(twscrape)", query, ranked, "; ".join(notes))
    for row in ranked[: args.show]:
        tag = row["channel"] or ("seed" if row["is_seed"] else "")
        print(
            f"{row['seed_count']:2d} {row['followers'] or 0:>8} @{row['handle']:<18} "
            f"{tag:<22} {row['bio'][:80]!r}"
        )
    return 0


def cmd_substack_recs(args: argparse.Namespace) -> int:
    seeds = [re.sub(r"^https?://", "", pub).split("/")[0].lower() for pub in args.pub]
    query = f"[channels] substack recommendations from {', '.join(seeds)} depth {args.depth}"
    if not args.force and _refuse_repeat("web", query):
        return 1
    http = hs._http()
    recs: dict[str, list[dict[str, Any]]] = {}
    queue = deque((seed, 0) for seed in seeds)
    notes: list[str] = []
    while queue and len(recs) < args.max_pubs:
        host, depth = queue.popleft()
        if host in recs:
            continue
        try:
            resp = http.get(f"https://{host}/recommendations", timeout=30, impersonate="chrome")
            pubs = parse_substack_recs(resp.text) if resp.status_code == 200 else []
        except Exception as exc:  # one dead publication must not stop the walk
            notes.append(f"{host}: {type(exc).__name__}")
            pubs = []
        recs[host] = pubs
        if depth + 1 < args.depth:
            queue.extend((pub["host"], depth + 1) for pub in pubs if pub["host"] not in recs)
        time.sleep(args.pause)
    ranked = rank_recs(recs, args.min_pubs)
    known = recorded_urls()
    for row in ranked:
        row["url"] = f"https://{row['host']}/"
        row["channel"] = known.get(_url_key(row["url"]), "")
    notes.insert(0, f"walked {len(recs)} publications")
    _log("web", "harvest_expand.py:substack_recs", query, ranked, "; ".join(notes))
    for row in ranked[: args.show]:
        print(f"{row['rec_count']:2d} {row['host']:<40} {row['channel']:<28} {row['name'][:40]!r}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    cof = sub.add_parser("x-cofollow", help="rank accounts followed by several seed accounts")
    cof.add_argument("--seed", action="append", required=True, help="X handle; repeatable")
    cof.add_argument("--per-seed", type=int, default=400, help="follows to read per seed")
    cof.add_argument("--min-seeds", type=int, default=2)
    cof.add_argument("--show", type=int, default=60)
    cof.add_argument("--force", action="store_true")
    cof.set_defaults(func=cmd_x_cofollow)
    rec = sub.add_parser("substack-recs", help="walk Substack recommendations from seeds")
    rec.add_argument("--pub", action="append", required=True, help="publication host; repeatable")
    rec.add_argument("--depth", type=int, default=2, help="1 reads only the seeds' pages")
    rec.add_argument("--max-pubs", type=int, default=80, help="stop after reading this many")
    rec.add_argument("--min-pubs", type=int, default=2)
    rec.add_argument("--pause", type=float, default=1.0)
    rec.add_argument("--show", type=int, default=60)
    rec.add_argument("--force", action="store_true")
    rec.set_defaults(func=cmd_substack_recs)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
