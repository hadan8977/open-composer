"""One-off bounded SEC input audit for DAY3-NEWS-EMBEDDING; no market/model IO."""
from __future__ import annotations

import collections
import datetime as dt
import gzip
import hashlib
import html
import json
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[5]
BASE = Path(__file__).resolve().parent
S0 = BASE / "s0"
TEXT_ROOT = (ROOT / "data/raw/earnings_text").resolve()
LIMIT_META = 8 * 1024 * 1024
LIMIT_TEXT = 400 * 1024 * 1024
LIMIT_RESPONSE = 16 * 1024 * 1024
LIMIT_ATTEMPTS = 64
LIMIT_WALL = 1800
DEADLINE = dt.datetime(2026, 9, 17, 23, 59, 59, tzinfo=dt.timezone.utc)
SEED = "DAY3-NEWS-S0-v1"
KIND_ORDER = ("earnings", "production-delivery", "guidance", "mixed", "unknown")
TABLE_RE = re.compile(r"(?is)<table\b.*?</table>")
SCRIPT_RE = re.compile(r"(?is)<(script|style)\b.*?</\1>")
TAG_RE = re.compile(r"(?s)<[^>]+>")
BREAK_RE = re.compile(r"(?is)<br\s*/?>|</?(?:p|div|tr|li|h[1-6])(?:\s[^>]*)?>")
FIELDS = {
    "eps": re.compile(r"(?i)\b(?:diluted|basic|adjusted)?\s*(?:EPS|earnings per share)\b"),
    "revenue": re.compile(r"(?i)\b(?:revenue|net sales|total sales)\b"),
    "profit": re.compile(r"(?i)\b(?:net income|operating income|gross profit|net loss)\b"),
    "guidance": re.compile(r"(?i)\b(?:guidance|outlook|expects?|forecast)\b"),
    "yoy": re.compile(r"(?i)\b(?:year[- ]over[- ]year|year[- ]on[- ]year|prior[- ]year|same quarter last year|compared (?:with|to) (?:the )?(?:same|prior))\b"),
}
NUM = re.compile(r"(?i)(?:\$\s*)?[-+]?\d[\d,]*(?:\.\d+)?\s*(?:%|million|billion|per share|bps)?")


def utc() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write_json(path: Path, obj: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
    tmp.replace(path)


def sha_file(path: Path, allowance: int) -> tuple[str, int]:
    h = hashlib.sha256()
    n = 0
    with path.open("rb") as f:
        while chunk := f.read(min(65536, allowance - n + 1)):
            n += len(chunk)
            if n > allowance:
                raise RuntimeError(f"read_cap_exceeded:{path}:{n}>{allowance}")
            h.update(chunk)
    return h.hexdigest(), n


def normalized(raw: str, *, keep_tables: bool) -> str:
    t = raw if keep_tables else TABLE_RE.sub(" ", raw)
    t = SCRIPT_RE.sub(" ", t)
    t = re.sub(r"[\r\n\t]+", " ", t)
    t = BREAK_RE.sub("\n", t)
    t = TAG_RE.sub(" ", t)
    t = html.unescape(t)
    t = "\n".join(re.sub("[ \t\u00a0]+", " ", line).strip() for line in t.split("\n"))
    return re.sub(r"\n{3,}", "\n\n", t).strip()


def kind_of(t: str) -> tuple[str, list[str]]:
    # Only the first 10k characters; broad document-family evidence, not a factor.
    p = t[:10000].lower()
    evidence = []
    if re.search(r"\b(?:quarterly|annual|fourth quarter|third quarter|second quarter|first quarter|financial results|earnings release|results of operations)\b", p):
        evidence.append("earnings")
    if re.search(r"\b(?:production and deliver(?:y|ies)|vehicle deliveries|units delivered|monthly production|production update)\b", p):
        evidence.append("production-delivery")
    if re.search(r"\b(?:financial guidance|business outlook|revis(?:es|ed) (?:its|full.year) guidance|guidance for fiscal)\b", p):
        evidence.append("guidance")
    return ("mixed" if len(evidence) > 1 else evidence[0] if evidence else "unknown", evidence)


def field_presence(t: str) -> dict[str, bool]:
    return {k: bool(v.search(t)) for k, v in FIELDS.items()}


def quota(groups: dict[str, list[dict]], q: int) -> dict[str, int]:
    total = sum(len(v) for v in groups.values())
    if total <= q:
        return {k: len(v) for k, v in groups.items()}
    shares = {k: q * len(v) / total for k, v in groups.items()}
    n = {k: int(v) for k, v in shares.items()}
    for k in sorted(groups, key=lambda x: (-(shares[x] - n[x]), x))[:q - sum(n.values())]:
        n[k] += 1
    return n


def manifest_phase() -> None:
    if (S0 / "sample-manifest.json").exists():
        raise RuntimeError("sample_manifest_exists_no_resample")
    S0.mkdir(exist_ok=True)
    start = time.monotonic()
    now = utc()
    plan = json.loads((BASE / "v1-preserved/plan.json").read_text())
    binds = plan["input_contract"]["existing_metadata_bindings"]
    actual = []
    frames = []
    meta_bytes = 0
    for b in binds:
        p = ROOT / b["path"]
        size = p.stat().st_size
        if size != b["bytes"] or meta_bytes + 2 * size > LIMIT_META:
            raise RuntimeError("metadata_size_or_budget_mismatch")
        h, n = sha_file(p, LIMIT_META - meta_bytes)
        meta_bytes += n
        if h != b["sha256"]:
            raise RuntimeError(f"metadata_sha_mismatch:{p}")
        tab = pq.read_table(p)
        meta_bytes += size  # conservative: charge a full parquet read, even if OS served cache
        if tab.num_rows != b["rows_metadata"] or meta_bytes > LIMIT_META:
            raise RuntimeError("metadata_rows_or_budget_mismatch")
        actual.append({**b, "actual_sha256": h, "actual_bytes": size, "actual_rows": tab.num_rows})
        frames.extend(tab.to_pylist())
    counts = collections.Counter()
    unique = {}
    symbols = collections.defaultdict(set)
    for row in frames:
        counts["all_metadata_rows"] += 1
        acc = str(row.get("accession") or "")
        cik = str(row.get("cik") or "").lstrip("0")
        key = (cik, acc)
        symbols[key].add(str(row.get("ticker") or ""))
        date = row.get("acceptance_utc")
        if isinstance(date, str):
            try:
                date = dt.datetime.fromisoformat(date.replace("Z", "+00:00"))
            except ValueError:
                date = None
        if isinstance(date, dt.datetime) and date.tzinfo is None:
            date = date.replace(tzinfo=dt.timezone.utc)
        if not isinstance(date, dt.datetime):
            counts["unknown_acceptance"] += 1
            continue
        if date > DEADLINE or date.year not in (2024, 2025, 2026):
            counts["outside_cutoff"] += 1
            continue
        form = str(row.get("form") or "")
        items = str(row.get("items") or "")
        if form != "8-K" or "2.02" not in items:
            counts["wrong_form_or_item"] += 1
            continue
        counts["item202_within_cutoff"] += 1
        if key in unique:
            counts["duplicate_cik_accession"] += 1
            continue
        unique[key] = (row, date)
    inventory = []
    text_bytes = 0
    for (cik, acc), (row, date) in sorted(unique.items()):
        if time.monotonic() - start > LIMIT_WALL:
            counts["wall_partial"] += 1
            break
        path_str = row.get("text_path")
        url = str(row.get("ex99_url") or "")
        status = str(row.get("fetch_status") or "")
        out = {"cik": cik, "accession": acc, "year": date.year, "acceptance_utc": date.isoformat(),
               "ticker_symbols": sorted(symbols[(cik, acc)]), "url": url, "fetch_status": status,
               "metadata_text_sha256": row.get("text_sha256"), "metadata_text_chars": row.get("text_chars"),
               "text_path": path_str, "form": row.get("form"), "items": row.get("items"),
               "security_identity": "unknown_historical_permanent_security"}
        if len(out["ticker_symbols"]) > 1:
            counts["multiple_ticker_strings_per_accession"] += 1
        if not url:
            counts["no_ex99"] += 1
            out["qualification"] = "no_ex99"
        elif not path_str:
            counts["no_text_path"] += 1
            out["qualification"] = "no_text_path"
        elif not re.fullmatch(r"https://www\.sec\.gov/Archives/edgar/data/\d+/[0-9-]+/[^?#]+", url):
            counts["noncanonical_url"] += 1
            out["qualification"] = "noncanonical_url"
        else:
            p = (ROOT / str(path_str)).resolve()
            if not p.is_relative_to(TEXT_ROOT):
                counts["text_path_outside_root"] += 1
                out["qualification"] = "bad_text_path"
            elif not p.is_file():
                counts["missing_text_file"] += 1
                out["qualification"] = "missing_text_file"
            else:
                n = p.stat().st_size
                if text_bytes + n > LIMIT_TEXT:
                    counts["text_budget_partial"] += 1
                    out["qualification"] = "text_cap_unread"
                else:
                    h, nread = sha_file(p, LIMIT_TEXT - text_bytes)
                    text_bytes += nread
                    out.update({"actual_text_sha256": h, "actual_text_bytes": nread,
                                "cache_mtime_not_fetch_at": dt.datetime.fromtimestamp(p.stat().st_mtime, dt.timezone.utc).isoformat()})
                    if h != row.get("text_sha256"):
                        counts["text_hash_mismatch"] += 1
                        out["qualification"] = "hash_mismatch"
                    else:
                        with p.open("r", encoding="utf-8", errors="replace") as f:
                            prefix = f.read(10000)
                        # Charge the extra prefix read to the existing text budget.
                        text_bytes += len(prefix.encode("utf-8"))
                        if text_bytes > LIMIT_TEXT:
                            out["qualification"] = "text_cap_unread"
                            counts["text_budget_partial"] += 1
                        else:
                            kind, ev = kind_of(prefix)
                            out.update({"qualification": "cache_hash_ok", "kind": kind,
                                        "kind_evidence": ev, "cached_fields_prefix": field_presence(prefix),
                                        "cached_prefix_digit_tokens": len(NUM.findall(prefix))})
                            counts["cache_hash_ok"] += 1
        inventory.append(out)
    # URL-level canonicalization and deterministic year x kind selection.
    by_url = {}
    for r in inventory:
        if r.get("qualification") == "cache_hash_ok":
            by_url.setdefault(r["url"], []).append(r)
    candidates = []
    for url, rows in by_url.items():
        r = sorted(rows, key=lambda z: (z["acceptance_utc"], z["cik"], z["accession"]))[0].copy()
        r["metadata_rows_for_url"] = len(rows)
        r["rank_sha256"] = digest(f'{SEED}|{r["cik"]}|{r["accession"]}|{url}'.encode())
        candidates.append(r)
    counts["unique_url_candidates"] = len(candidates)
    counts["url_duplicate_rows"] = sum(len(v) - 1 for v in by_url.values())
    groups_by_year = {y: collections.defaultdict(list) for y in (2024, 2025, 2026)}
    for r in candidates:
        groups_by_year[r["year"]][r["kind"]].append(r)
    picked = []
    year_quota = {2024: 22, 2025: 21, 2026: 21}
    year_counts = {y: sum(map(len, groups_by_year[y].values())) for y in year_quota}
    carry = 0
    for y in year_quota:
        q = min(year_counts[y], year_quota[y] + carry)
        carry = year_quota[y] + carry - q
        allocations = quota(groups_by_year[y], q)
        for k in sorted(allocations):
            ranks = sorted(groups_by_year[y][k], key=lambda r: r["rank_sha256"])
            for rank, r in enumerate(ranks[:allocations[k]], 1):
                picked.append({**r, "stratum": f"{y}|{k}", "stratum_quota": allocations[k], "rank": rank})
    # Fixed-order fill if a later year lacked enough rows: allocate to earlier residual pool.
    if carry:
        seen = {r["url"] for r in picked}
        for y in year_quota:
            residual = [r for r in candidates if r["year"] == y and r["url"] not in seen]
            for r in sorted(residual, key=lambda z: z["rank_sha256"])[:carry]:
                picked.append({**r, "stratum": f"{y}|{r['kind']}|carry", "stratum_quota": None, "rank": None})
                seen.add(r["url"])
                carry -= 1
            if not carry:
                break
    picked.sort(key=lambda r: (r["year"], r["kind"], r["rank_sha256"]))
    for i, r in enumerate(picked, 1):
        r["request_ordinal"] = i
    with gzip.open(S0 / "inventory.jsonl.gz", "wt", encoding="utf-8", compresslevel=6) as f:
        for r in inventory:
            f.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")
    inv_h = sha_file(S0 / "inventory.jsonl.gz", LIMIT_TEXT)[0]
    manifest = {"schema_version": 1, "selection_version": SEED, "frozen_at_utc": utc(),
                "S0_started_at_utc": now, "method_script_sha256": sha_file(Path(__file__), LIMIT_META)[0],
                "builder_script_sha256": sha_file(ROOT / "scripts/build_earnings_events.py", LIMIT_META)[0],
                "plan_v1_sha256": sha_file(BASE / "v1-preserved/plan.json", LIMIT_META)[0],
                "metadata": actual, "metadata_bytes_conservatively_charged": meta_bytes,
                "text_bytes_read": text_bytes, "text_limit": LIMIT_TEXT, "inventory_sha256": inv_h,
                "inventory_path": str((S0 / "inventory.jsonl.gz").relative_to(ROOT)),
                "counts": dict(counts), "selection_recipe": "review.DAY3-NEWS-S0-v1; year 22/21/21, kind proportional largest remainder, SHA rank",
                "rows": picked, "network_attempts_before_manifest": 0}
    write_json(S0 / "sample-manifest.json", manifest)
    print(json.dumps({"manifest": "s0/sample-manifest.json", "rows": len(picked), "counts": dict(counts),
                      "metadata_bytes": meta_bytes, "text_bytes": text_bytes, "elapsed_s": time.monotonic() - start}))


def fetch_phase() -> None:
    manifest_path = S0 / "sample-manifest.json"
    manifest = json.loads(manifest_path.read_text())
    if not manifest["rows"] or len(manifest["rows"]) > LIMIT_ATTEMPTS:
        raise RuntimeError("manifest_empty_or_exceeds_64")
    if (S0 / "network-ledger.jsonl").exists():
        raise RuntimeError("network_ledger_exists_refuse_reset")
    start = dt.datetime.fromisoformat(manifest["S0_started_at_utc"])
    run_start = time.monotonic()
    requests = 0
    response_bytes = 0
    audits = []
    reason = "manifest_exhausted"
    # Reject all redirects; no retry, proxy switching or credential use.
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, request, fp, code, msg, headers, newurl):
            return None
    opener = urllib.request.build_opener(NoRedirect)
    for row in manifest["rows"]:
        if (dt.datetime.now(dt.timezone.utc) - start).total_seconds() >= LIMIT_WALL or time.monotonic() - run_start >= LIMIT_WALL:
            reason = "wall_cap"
            break
        if requests >= LIMIT_ATTEMPTS or response_bytes >= LIMIT_RESPONSE:
            reason = "request_or_body_cap"
            break
        url = row["url"]
        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.netloc != "www.sec.gov" or not parsed.path.startswith("/Archives/edgar/data/"):
            reason = "url_outside_manifested_sec_archive"
            break
        requests += 1
        fetched = utc()
        rec = {"ordinal": requests, "url": url, "cik": row["cik"], "accession": row["accession"],
               "fetched_at_utc": fetched, "status": None, "bytes": 0, "sha256": None,
               "headers": {}, "error": None}
        output = S0 / "original-html" / f'{requests:02d}.response'
        output.parent.mkdir(exist_ok=True)
        h = hashlib.sha256()
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "open-composer research hzc43021@gmail.com", "Accept-Encoding": "identity"})
            try:
                res = opener.open(req, timeout=20)
            except urllib.error.HTTPError as e:
                res = e
            rec["status"] = res.getcode()
            rec["headers"] = {k: v for k, v in res.headers.items() if k.lower() in ("content-type", "last-modified", "etag", "content-length", "location", "date")}
            with output.open("wb") as f:
                while response_bytes < LIMIT_RESPONSE:
                    block = res.read(min(16384, LIMIT_RESPONSE - response_bytes))
                    if not block:
                        break
                    f.write(block)
                    h.update(block)
                    response_bytes += len(block)
                    rec["bytes"] += len(block)
            rec["sha256"] = h.hexdigest()
            res.close()
            if rec["status"] == 200 and rec["bytes"] and response_bytes < LIMIT_RESPONSE:
                raw = output.read_bytes().decode("utf-8", errors="replace")
                dropped = normalized(raw, keep_tables=False)
                retained = normalized(raw, keep_tables=True)
                table_texts = [normalized(t, keep_tables=True) for t in TABLE_RE.findall(raw)]
                long_prose_tables = [t for t in table_texts if len(t.split()) >= 30 and re.search(r"(?i)\b(?:we|our|management|business|demand|customer|operations|segment)\b", t)]
                rec["audit"] = {"table_count": len(table_texts), "table_text_chars": sum(map(len, table_texts)),
                                "layout_prose_table_count_min30words": len(long_prose_tables),
                                "layout_prose_table_chars": sum(map(len, long_prose_tables)),
                                "retained_chars": len(retained), "dropped_chars": len(dropped),
                                "cache_chars_metadata": row["metadata_text_chars"],
                                "recomputed_dropped_matches_cache_hash": digest(dropped.encode()) == row["actual_text_sha256"],
                                "raw_sha256": rec["sha256"], "retained_sha256": digest(retained.encode()),
                                "dropped_sha256": digest(dropped.encode()),
                                "cache_sha256_from_frozen_manifest": row["actual_text_sha256"],
                                "retained_fields": field_presence(retained),
                                "dropped_fields": field_presence(dropped),
                                "cache_prefix_fields_from_frozen_manifest": row["cached_fields_prefix"],
                                "retained_numeric_tokens": len(NUM.findall(retained)),
                                "dropped_numeric_tokens": len(NUM.findall(dropped)),
                                "cache_prefix_numeric_tokens_from_frozen_manifest": row["cached_prefix_digit_tokens"],
                                "table_prose_example_truncated": [t[:220] for t in long_prose_tables[:2]],
                                "version_status": "current_refetch_only_unknown_historical_vintage"}
                audits.append(rec["audit"])
        except Exception as e:
            rec["error"] = f"{type(e).__name__}: {e}"[:500]
            if output.exists():
                rec["sha256"] = h.hexdigest()
        with (S0 / "network-ledger.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False, sort_keys=True) + "\n")
        if rec["status"] in (403, 429):
            reason = f"sec_http_{rec['status']}_no_retry"
            break
        if rec["status"] in (301, 302, 303, 307, 308):
            reason = "redirect_requires_new_bound_manifest_and_attempt"
            break
        if response_bytes >= LIMIT_RESPONSE:
            reason = "all_response_body_cap"
            break
    write_json(S0 / "fetch-result.json", {"finished_at_utc": utc(), "stop_reason": reason,
                                           "attempts": requests, "response_bytes_all_status": response_bytes,
                                           "html_200_with_audit": len(audits), "wall_seconds_from_manifest_start":
                                           (dt.datetime.now(dt.timezone.utc) - start).total_seconds()})
    print(json.dumps({"attempts": requests, "all_response_bytes": response_bytes, "audited": len(audits), "stop": reason}))


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in ("manifest", "fetch"):
        raise SystemExit("usage: s0_run.py manifest|fetch")
    {"manifest": manifest_phase, "fetch": fetch_phase}[sys.argv[1]]()
