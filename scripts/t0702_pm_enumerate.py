#!/usr/bin/env python3
# ruff: noqa: E501
"""T-20261007-02: enumerate Polymarket events by tag from the public Gamma API (no key); cached, rate limited."""

import json
import time
import urllib.error
import urllib.request
from pathlib import Path

OUT = Path("data/research/pm_event_study/polymarket/events_by_tag.jsonl")
TAGS = [
    "tariffs",
    "fed",
    "fed-rates",
    "economy",
    "economic-policy",
    "macro-indicators",
    "politics",
    "trump",
    "recession",
    "government-shutdown",
    "elections",
    "us-politics",
    "inflation",
    "jobs-report",
    "us-election",
    "trump-presidency",
    "trade-war",
    "debt-ceiling",
    "house",
    "senate",
    "geopolitics",
]
UA = {"User-Agent": "Mozilla/5.0"}


def get(url):
    for i in range(6):
        try:
            return json.load(
                urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=40)
            )
        except urllib.error.HTTPError as e:
            if e.code == 429 or e.code >= 500:
                time.sleep(2**i * 2)
                continue
            if e.code == 404:
                return None
            raise
        except Exception:
            time.sleep(2**i)
    return None


seen = set()
if OUT.exists():
    for line in OUT.open():
        seen.add(json.loads(line)["tag"])
with OUT.open("a") as f:
    for tag in TAGS:
        if tag in seen:
            continue
        n = 0
        for closed in ("true", "false"):
            off = 0
            while True:
                r = get(
                    f"https://gamma-api.polymarket.com/events?tag_slug={tag}&closed={closed}&limit=100&offset={off}&start_date_min=2023-10-01&order=volume&ascending=false"
                )
                time.sleep(0.35)
                if not r:
                    break
                for e in r:
                    ms = [
                        {
                            "question": m.get("question"),
                            "conditionId": m.get("conditionId"),
                            "tokens": m.get("clobTokenIds"),
                            "vol": m.get("volumeNum"),
                            "start": m.get("startDate"),
                            "end": m.get("endDate"),
                            "closedTime": m.get("closedTime"),
                            "outcomes": m.get("outcomes"),
                        }
                        for m in e.get("markets", [])
                    ]
                    f.write(
                        json.dumps(
                            {
                                "tag": tag,
                                "event_id": e["id"],
                                "slug": e["slug"],
                                "title": e["title"],
                                "volume": e.get("volume"),
                                "start": e.get("startDate"),
                                "end": e.get("endDate"),
                                "closed": e.get("closed"),
                                "markets": ms,
                            }
                        )
                        + "\n"
                    )
                    n += 1
                if len(r) < 100 or off >= 1500:
                    break
                off += 100
        f.write(json.dumps({"tag": tag, "event_id": None, "n": n}) + "\n")
        f.flush()
        print(tag, n, flush=True)
