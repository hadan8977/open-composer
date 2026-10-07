#!/usr/bin/env python3
# ruff: noqa: E501
"""T-20261007-02: hourly YES price history for the frozen qualified Polymarket markets (public CLOB API, cached,
<=3 requests/s, backoff on 429/5xx). One parquet-free jsonl per market under data/research/pm_event_study/polymarket/hist/."""

import datetime as dt
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, "scripts")
import t0702_pm_grid as G

BASE = Path("data/research/pm_event_study/polymarket")
HIST = BASE / "hist"
HIST.mkdir(exist_ok=True)
UA = {"User-Agent": "Mozilla/5.0"}


def get(url):
    for i in range(7):
        try:
            return json.load(
                urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=40)
            )
        except urllib.error.HTTPError as e:
            if e.code in (429,) or e.code >= 500:
                time.sleep(2**i * 2)
                continue
            if e.code == 400:
                return {"history": []}
            raise
        except Exception:
            time.sleep(2**i)
    return None


def ts(s):
    if not s:
        return None
    s = s.replace(" ", "T").replace("Z", "+00:00")
    if len(s) == 22 and s[-3] in "+-":
        s += ":00"
    try:
        d = dt.datetime.fromisoformat(s)
    except ValueError:
        return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=dt.UTC)
    return int(d.timestamp())


ev = {}
for line in open(BASE / "events_by_tag.jsonl"):
    d = json.loads(line)
    if d.get("event_id") and d["tag"] not in G.J_EXCLUDE_TAGS:
        ev.setdefault(d["event_id"], d)
quals = []
for e in ev.values():
    for m in e["markets"]:
        if (m.get("vol") or 0) < G.J_MIN_MARKET_VOLUME:
            continue
        th = G.theme_of(e["title"], m["question"] or "")
        if th and m.get("tokens"):
            quals.append(
                {
                    "event_id": e["event_id"],
                    "title": e["title"],
                    "question": m["question"],
                    "theme": th,
                    "vol": m["vol"],
                    "token": json.loads(m["tokens"])[0],
                    "start": m.get("start") or e["start"],
                    "end": m.get("closedTime") or m.get("end") or e["end"],
                }
            )
quals.sort(key=lambda x: -x["vol"])
quals = quals[: G.J_MAX_MARKETS]
(BASE / "qualified_markets.json").write_text(json.dumps(quals, indent=1))
now = int(time.time())
w0 = ts("2024-01-01T00:00:00Z")
print("markets", len(quals), flush=True)
for i, q in enumerate(quals):
    f = HIST / f"{q['token'][:24]}.json"
    if f.exists():
        continue
    s0 = max(ts(q["start"]) or w0, w0)
    e0 = min(ts(q["end"]) or now, now)
    pts = []
    t = s0
    while t < e0:
        r = get(
            f"https://clob.polymarket.com/prices-history?market={q['token']}&startTs={t}&endTs={min(t + G.FETCH_CHUNK_DAYS * 86400, e0)}&fidelity=60"
        )
        if r is None:
            print("fail", i, t, flush=True)
            break
        pts += [(x["t"], x["p"]) for x in r.get("history", [])]
        t += G.FETCH_CHUNK_DAYS * 86400
        time.sleep(0.34)
    else:
        f.write_text(json.dumps({"token": q["token"], "n": len(pts), "pts": sorted(set(pts))}))
    if i % 20 == 0:
        print(i, len(pts), flush=True)
print("done", flush=True)
