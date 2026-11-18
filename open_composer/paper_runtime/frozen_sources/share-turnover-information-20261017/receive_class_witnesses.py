"""Narrow public SEC covers for actual retained fixed-cohort count accessions.

Source receipt only. It computes no turnover, market feature, label or account.
One client identity, serialized start rate <=4/s, two connections, no 403 retry.
"""

import asyncio
import gzip
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import httpx
from dotenv import load_dotenv
from lxml import html

ROOT = Path(__file__).resolve().parents[4]
V = Path(__file__).resolve().parent
OUT = V / "class-witnesses"
ALIASES = {"FISV": {"FISV", "FI"}, "RE": {"RE", "EG"}}


def save(path, obj):
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(obj, indent=2, allow_nan=False) + "\n")
    temp.replace(path)


def binding(path):
    raw = path.read_bytes()
    return dict(
        path=str(path.relative_to(ROOT)), bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest()
    )


def parse_cover(raw, symbol, expected):
    """Strict, conservative source witness; unsupported is retained, never guessed."""
    tree = html.fromstring(raw)
    contexts = {}
    titles, tickers, facts = {}, {}, []
    for node in tree.iter():
        tag = str(node.tag).lower()
        if tag.endswith(":context") or tag == "context":
            instant, dimensions = None, []
            for child in node.iter():
                ctag = str(child.tag).lower()
                if ctag.endswith(":instant"):
                    instant = "".join(child.itertext()).strip()
                if ctag.endswith(":explicitmember") or ctag.endswith(":typedmember"):
                    dimensions.append("".join(child.itertext()).strip())
            contexts[node.get("id")] = dict(instant=instant, dimensions=dimensions)
        name = (node.get("name") or "").lower()
        if name not in {
            "dei:security12btitle",
            "dei:tradingsymbol",
            "dei:entitycommonstocksharesoutstanding",
        }:
            continue
        context = node.get("contextref")
        text = " ".join("".join(node.itertext()).split())
        if name == "dei:security12btitle":
            titles[context] = text
        elif name == "dei:tradingsymbol":
            tickers[context] = text
        elif name == "dei:entitycommonstocksharesoutstanding":
            try:
                value = Decimal(re.sub(r"[,\s]", "", text)) * (
                    Decimal(10) ** int(node.get("scale", "0"))
                )
                if node.get("sign") == "-":
                    value = -value
            except Exception:
                return dict(supported=False, reason="unparsed_cover_count")
            facts.append(
                dict(value=str(value), context=context, unit=node.get("unitref"), text=text)
            )
    common = [
        dict(context=c, title=t, ticker=tickers.get(c))
        for c, t in titles.items()
        if re.search(r"\bcommon\s+(?:stock|shares?)\b|\bordinary\s+shares?\b", t, re.I)
        and not re.search(r"preferred|preference|depositary", t, re.I)
    ]
    matches = [x for x in common if x["ticker"] in ALIASES.get(symbol, {symbol})]
    unique_facts = {(x["value"], x["context"], x["unit"]): x for x in facts}
    output = dict(
        supported=False,
        reason="ambiguous_or_absent_class_witness",
        common_registered_securities=common,
        cover_counts=list(unique_facts.values()),
        source_claim=(
            "One cover common-share count and one registered common class, "
            "exact retained instant/value; no inference from CIK alone"
        ),
    )
    if len(common) != 1 or len(matches) != 1 or len(unique_facts) != 1:
        return output
    fact = next(iter(unique_facts.values()))
    context = contexts.get(fact["context"], {})
    output["count_context"] = context
    if (
        Decimal(fact["value"]) != Decimal(str(expected["val"]))
        or context.get("instant") != expected["end"]
    ):
        output["reason"] = "cover_vs_companyfacts_instant_or_value_mismatch"
        return output
    if not fact["unit"] or "share" not in fact["unit"].lower():
        output["reason"] = "unproved_share_unit"
        return output
    # Dimensional facts need an actual matching class member, never a ticker guess.
    dimensions = context.get("dimensions", [])
    security_dimensions = contexts.get(matches[0]["context"], {}).get("dimensions", [])
    if dimensions and not set(dimensions).issubset(set(security_dimensions)):
        output["reason"] = "count_class_dimensions_not_matched"
        return output
    output.update(
        supported=True, reason="exact_single_common_class_cover_count", matched_security=matches[0]
    )
    return output


def source_plan():
    inventory = json.loads((V / "share-source-inventory.json").read_text())
    queue, missing = [], []
    archive = ROOT / "data/raw/sec_submissions/submissions.zip"
    archive_cache = OUT / "historical-submissions"
    archive_cache.mkdir(exist_ok=True)
    for symbol, member in inventory["selected_members"].items():
        if not member.get("cik"):
            continue
        records = [
            r for r in member.get("records", []) if "2020-07-01" <= r["filed"] <= "2026-09-30"
        ]
        if not records:
            continue
        clocks = {r["accn"]: r for r in member["submission"]["candidate_filing_clocks"]}
        for extra in member["submission"].get("historical_archive_files", []):
            if extra["filingTo"] < "2020-07-01" or extra["filingFrom"] > "2026-09-30":
                continue
            path = archive_cache / extra["name"]
            if not path.exists():
                received = subprocess.run(
                    ["unzip", "-p", str(archive), extra["name"]], capture_output=True
                )
                if received.returncode != 0:
                    missing.append(
                        dict(
                            symbol=symbol,
                            historical_member=extra["name"],
                            unzip_code=received.returncode,
                        )
                    )
                    continue
                json.loads(received.stdout)
                path.write_bytes(received.stdout)
            old = json.loads(path.read_text())
            for i, accn in enumerate(old.get("accessionNumber", [])):
                clocks.setdefault(
                    accn,
                    dict(
                        accn=accn,
                        primaryDocument=old["primaryDocument"][i],
                        acceptanceDateTime=old.get(
                            "acceptanceDateTime", [None] * len(old["accessionNumber"])
                        )[i],
                    ),
                )
        seen = set()
        for record in records:
            key = record["accn"]
            if key in seen:
                continue
            seen.add(key)
            clock = clocks.get(key)
            if not clock or not clock.get("primaryDocument"):
                missing.append(
                    dict(symbol=symbol, accn=key, reason="no_received_primary_document_locator")
                )
                continue
            base = f"https://www.sec.gov/Archives/edgar/data/{member['cik']}"
            url = f"{base}/{key.replace('-', '')}/{clock['primaryDocument']}"
            queue.append(
                dict(symbol=symbol, cik=member["cik"], record=record, clock=clock, url=url)
            )
    save(
        OUT / "source-plan.json",
        dict(
            purpose="Exact same-class source witnesses; no prices/turnover/labels/fits/accounts",
            authority=binding(
                ROOT
                / "reports/research/program/session-handoff-20261016"
                / "share-turnover-information-main-decision.json"
            ),
            inventory=binding(V / "share-source-inventory.json"),
            date_scope=(
                "retained count filings2020-07-01..2026-09-30; eventual causal120day age required"
            ),
            queue=queue,
            missing=missing,
            requests_not_broad_universe=True,
        ),
    )
    return queue


async def receive(queue):
    load_dotenv(ROOT / ".env")
    agent = os.environ["SEC_USER_AGENT"]
    assert re.search(r"\S+@\S+\.\S+", agent)
    gate = asyncio.Lock()
    last = 0.0
    forbidden = asyncio.Event()
    results = []
    work = asyncio.Queue()
    for item in queue:
        work.put_nowait(item)
    async with httpx.AsyncClient(
        headers={"User-Agent": agent, "Accept-Encoding": "gzip, deflate"},
        timeout=90,
        follow_redirects=True,
        limits=httpx.Limits(max_connections=2),
    ) as client:

        async def worker():
            nonlocal last
            while not work.empty():
                item = work.get_nowait()
                key = f"{item['symbol']}-{item['record']['accn']}"
                receipt = OUT / (key + ".json")
                if receipt.exists():
                    prior = json.loads(receipt.read_text())
                    assert all(prior[k] == item[k] for k in item)
                    if prior.get("received_gzip"):
                        assert (
                            binding(ROOT / prior["received_gzip"]["path"]) == prior["received_gzip"]
                        )
                    results.append(prior)
                    continue
                if forbidden.is_set():
                    results.append(
                        dict(
                            **item,
                            supported=False,
                            reason="receipt_route_stopped_after_access_denial",
                        )
                    )
                    continue
                started = datetime.now(UTC).isoformat()
                try:
                    old = V / "sec-cover-receipts/WMT-20260828.json"
                    old_receipt = json.loads(old.read_text()) if old.exists() else {}
                    if (
                        old_receipt.get("url") == item["url"]
                        and old_receipt.get("status_code") == 200
                    ):
                        raw = (ROOT / old_receipt["path"]).read_bytes()
                        status, reuse = 200, binding(old)
                    else:
                        async with gate:
                            await asyncio.sleep(max(0, 0.26 - (time.monotonic() - last)))
                            last = time.monotonic()
                        response = await client.get(item["url"])
                        status, raw, reuse = response.status_code, response.content, None
                    target = OUT / (key + ".html.gz")
                    with gzip.GzipFile(filename=str(target), mode="wb", mtime=0) as f:
                        f.write(raw)
                    witness = (
                        parse_cover(raw, item["symbol"], item["record"])
                        if status == 200
                        else dict(supported=False, reason=f"HTTP{status}")
                    )
                    row = dict(
                        **item,
                        **witness,
                        method="GET" if reuse is None else "reuse_received_GET",
                        status_code=status,
                        raw_entity_bytes=len(raw),
                        raw_entity_sha256=hashlib.sha256(raw).hexdigest(),
                        received_gzip=binding(target),
                        reused_receipt=reuse,
                        started_at_utc=started,
                        received_at_utc=datetime.now(UTC).isoformat(),
                    )
                    if status in (403, 429):
                        forbidden.set()
                except Exception as exc:
                    row = dict(
                        **item,
                        supported=False,
                        reason="source_receipt_error",
                        error=repr(exc),
                        started_at_utc=started,
                    )
                save(receipt, row)
                results.append(row)
                if len(results) % 50 == 0:
                    save(
                        OUT / "progress.json",
                        dict(
                            received=len(results),
                            planned=len(queue),
                            supported=sum(r.get("supported", False) for r in results),
                            access_denial_stopped=forbidden.is_set(),
                        ),
                    )
                    print(json.dumps(dict(completed=len(results), planned=len(queue))), flush=True)

        await asyncio.gather(worker(), worker())
    return results


def main():
    OUT.mkdir(exist_ok=True)
    resume = sys.argv[1:] == ["--resume-received"]
    assert not sys.argv[1:] or resume, "Unexpected source operation"
    marker = OUT / ("source-parser-recovery-started.json" if resume else "source-started.json")
    if resume:
        prior_exit = json.loads((V / "class-source-exit.json").read_text())
        assert prior_exit["returncode"] == 143 and prior_exit["source_only"] is True
        plan = json.loads((OUT / "source-plan.json").read_text())
        assert plan["inventory"] == binding(V / "share-source-inventory.json")
        assert not (OUT / "source-result.json").exists(), "Reuse completed source result"
    fd = os.open(marker, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
    os.close(fd)
    save(
        marker,
        dict(pid=os.getpid(), started_at_utc=datetime.now(UTC).isoformat(), source_only=True),
    )
    queue = plan["queue"] if resume else source_plan()
    print(json.dumps(dict(planned=len(queue))), flush=True)
    rows = asyncio.run(receive(queue))
    save(
        OUT / "source-result.json",
        dict(
            completed_at_utc=datetime.now(UTC).isoformat(),
            planned=len(queue),
            receipt_objects=len(rows),
            supported=sum(r.get("supported", False) for r in rows),
            rows=rows,
            numerical_entry=False,
            no_prices_features_labels_models_accounts=True,
        ),
    )
    print(
        json.dumps(
            dict(receipt_objects=len(rows), supported=sum(r.get("supported", False) for r in rows))
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
