# ruff: noqa: E501
#!/usr/bin/env python3
"""T-20261007-03 step 1b: DeepSeek extraction of major customers from 10-K snippets.

One call per filing that has at least one non-negative customer-concentration
snippet (rules in ``t03_fetch_snippets.py``). Uses the project's text-scorer
endpoint (credentials file outside the repo, read once, never printed) through
the client of ``score_earnings_text.py``. Single process (flock), local cap of
``CAP_PER_5H`` calls per rolling 5 hours. HTTP 429 or a quota body stops the run
with a nonzero exit: only evidenced recovery times allow bounded automatic
retries, and ``failure_state.json`` persists the circuit across reruns.
Reruns skip finished accessions.
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import re
import sys
import time
from contextlib import ExitStack
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import score_earnings_text as st  # noqa: E402
import t03_retry as retry  # noqa: E402

DATA = ROOT / "data" / "features" / "economic_links"
SNIP = DATA / "_snippets"
OUT = DATA / "_llm"
LEDGER = OUT / "ledger.jsonl"
NEXT_TRY = OUT / "next_try_at.json"
LOCK = OUT / ".lock"
FAILURE_STATE = OUT / "failure_state.json"
CAP_PER_5H = 880
WINDOW = timedelta(hours=5)
MAX_TOKENS = 2200

SYSTEM = (
    "You extract major-customer disclosures from excerpts of one company's annual report (10-K). "
    "The company is the SUPPLIER. Return only JSON, no prose."
)
INSTRUCTION = """Excerpts follow. Extract every customer the company says it depends on or that accounts for a stated share of its revenue, sales or receivables. Rules:
- Only entities the text says buy from the company (customers). Not suppliers, competitors, joint-venture partners, acquisition targets, lenders, or the company's own segments or products.
- Use the name exactly as written (for example "Apple Inc.", "Wal-Mart", "U.S. Government"). If the text only says "Customer A" or "one customer", name is null and type is "anonymous".
- type: "company" (a named business), "government" (any government or agency, including Department of Defense), "anonymous" (unnamed), "group" (a group such as distributors, OEMs, or top-ten customers).
- pct: percent of the company's total revenue or sales as a number (12.5), null if absent or if the percent is of receivables only (then set basis to "receivables"). basis: "revenue", "receivables", or "unknown".
- lower_bound: true when the text only says "more than/over/at least X%" or "more than 10%" without the exact figure (then pct is X), else false.
- fiscal_year: the fiscal year the percent refers to (integer), null if unclear. If several years are given, return one row per year.
- quote: the shortest exact sentence fragment (under 220 characters) supporting the row.
- If the excerpts state that no customer reached 10% and name nobody, return {"no_major_customer": true, "customers": []}.
Output compact JSON on one line (no indentation, no newlines), at most 15 customers, strongest first. Return: {"no_major_customer": bool, "customers": [{"name": str|null, "type": str, "pct": number|null, "basis": str, "lower_bound": bool, "fiscal_year": int|null, "quote": str}]}

Excerpts:
"""

NEG = re.compile(
    r"\bno (?:single |individual |one |other |sales to any )?(?:customers?|clients?)\b.{0,140}?"
    r"(?:10|ten|5|five|2|two)\s*(?:%|percent)|"
    r"\b(?:did not|does not|had no|have no|not have any)\b.{0,60}?(?:customers?|clients?).{0,120}?"
    r"(?:10|ten)\s*(?:%|percent)",
    re.I,
)
PCT_RE = re.compile(r"\d{1,3}(?:\.\d+)?\s*(?:%|percent)", re.I)


def is_negative(snippet: str) -> bool:
    return bool(NEG.search(snippet)) and len(snippet) < 380 and len(PCT_RE.findall(snippet)) <= 2


def prompt_hash() -> str:
    return hashlib.sha256((SYSTEM + INSTRUCTION).encode()).hexdigest()


def load_filings() -> list[dict]:
    seen: dict[str, dict] = {}
    for f in sorted(SNIP.glob("part_main_*.jsonl")):
        for line in f.read_text().splitlines():
            if line.strip():
                r = json.loads(line)
                seen[r["accession"]] = r
    return list(seen.values())


def done_accessions() -> set[str]:
    done: set[str] = set()
    for f in OUT.glob("part_*.jsonl"):
        for line in f.read_text().splitlines():
            if line.strip():
                r = json.loads(line)
                if r.get("parsed") is not None:
                    done.add(r["accession"])
    return done


def calls_in_window(now: datetime) -> list[datetime]:
    if not LEDGER.exists():
        return []
    out = []
    for line in LEDGER.read_text().splitlines():
        if line.strip():
            t = datetime.fromisoformat(json.loads(line)["t"])
            if now - t < WINDOW:
                out.append(t)
    return out


def parse_reply(text: str) -> dict | None:
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return None
    try:
        obj = json.loads(m.group(0))
    except ValueError:
        return None
    if not isinstance(obj, dict) or not isinstance(obj.get("customers", []), list):
        return None
    return obj


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--newest-first", action="store_true", default=True)
    ap.add_argument("--accessions", help="comma list, for tests")
    ap.add_argument(
        "--recovery-probe",
        action="store_true",
        help="owner-controlled single-call probe of a blocked upstream; still obeys local cap and wait",
    )
    ap.add_argument(
        "--recovery-evidence",
        type=Path,
        help="Root-reviewed JSON with recovery_confirmed=true and basis=provider_quota_recovered or owner_authorized_existing_alternative",
    )
    args = ap.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    lock = LOCK.open("w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print("another extraction process holds the lock", flush=True)
        return retry.EXIT_NO_PROGRESS
    now = datetime.now(UTC)
    state = retry.read_state(FAILURE_STATE, LEDGER)
    if args.recovery_probe and (
        not args.recovery_evidence or not retry.valid_recovery_evidence(args.recovery_evidence)
    ):
        print(f"no progress; next_action={retry.BLOCK_ACTION}", flush=True)
        return retry.EXIT_BLOCKED
    if state.get("blocked") and not args.recovery_probe:
        print(
            f"no progress; retry circuit blocked after {state['consecutive_failures']} failures; next_action={retry.BLOCK_ACTION}",
            flush=True,
        )
        return retry.EXIT_BLOCKED
    if NEXT_TRY.exists():
        value = json.loads(NEXT_TRY.read_text()).get("next_try_at")
        nt = datetime.fromisoformat(value) if value else None
        if nt and nt > now:
            print(f"waiting until {nt.isoformat()}", flush=True)
            return retry.EXIT_WAIT

    filings = load_filings()
    done = done_accessions()
    todo, rule_neg = [], []
    for r in filings:
        if r["accession"] in done or r["status"] != "ok" or not r["snippets"]:
            continue
        pos = [s for s in r["snippets"] if not is_negative(s)]
        if pos:
            r = {**r, "snippets": pos}
            todo.append(r)
        else:
            rule_neg.append(r)
    if args.accessions:
        want = set(args.accessions.split(","))
        todo = [r for r in todo if r["accession"] in want]
    todo.sort(key=lambda r: r["filing_date"], reverse=args.newest_first)
    if args.limit:
        todo = todo[: args.limit]
    if args.recovery_probe:
        todo = todo[:1]
    print(f"to extract {len(todo)}; rule-negative {len(rule_neg)}", flush=True)
    if not todo:
        return 0

    def local_wait(now: datetime) -> bool:
        used = calls_in_window(now)
        if len(used) < CAP_PER_5H:
            return False
        nt = min(used) + WINDOW + timedelta(seconds=30)
        retry.write_json(
            NEXT_TRY,
            {
                "next_try_at": nt.isoformat(),
                "reason": "local cap",
                "next_action": "wait_until_next_try_at",
            },
        )
        print(f"local cap reached; next try {nt.isoformat()}", flush=True)
        return True

    if local_wait(now):
        return retry.EXIT_WAIT

    creds = st.load_credentials(st.CREDENTIALS_PATH)
    call = st.make_requests_chat_call_fn(
        base_url=creds["OC_TEXT_SCORER_BASE_URL"],
        api_key=creds["OC_TEXT_SCORER_API_KEY"],
        model=creds["OC_TEXT_SCORER_MODEL"],
        max_tokens=MAX_TOKENS,
    )
    ph = prompt_hash()
    part = OUT / f"part_{datetime.now(UTC):%Y%m%dT%H%M%S}.jsonl"
    n = 0
    with ExitStack() as stack:
        fh = None
        led = stack.enter_context(LEDGER.open("a"))

        def record_call(res, now: datetime) -> int | None:
            nonlocal state
            limited = st.is_rate_limited(res)
            detail = (
                retry.diagnostics(res, now=now, limited=limited)
                if limited or res.status_code != 200
                else {}
            )
            led.write(
                json.dumps(
                    {
                        "t": now.isoformat(),
                        "status": res.status_code,
                        "pt": res.prompt_tokens,
                        "ct": res.completion_tokens,
                        **detail,
                    }
                )
                + "\n"
            )
            led.flush()
            if not detail:
                return None
            state = retry.record_failure(FAILURE_STATE, state, detail, now=now)
            if limited:
                retry.write_json(
                    NEXT_TRY,
                    {
                        "next_try_at": detail["recovery_at"],
                        "reason": detail["reason"],
                        "blocked": state["blocked"],
                        "next_action": state["next_action"],
                    },
                )
                print(
                    f"no progress; http {res.status_code}; reason={detail['reason']}; failures={state['consecutive_failures']}; next_action={state['next_action']}",
                    flush=True,
                )
                return retry.EXIT_BLOCKED if state["blocked"] else retry.EXIT_WAIT
            if state["blocked"]:
                print(
                    f"no progress; failed-call threshold reached; next_action={state['next_action']}",
                    flush=True,
                )
                return retry.EXIT_BLOCKED
            return None

        for r in todo:
            now = datetime.now(UTC)
            if local_wait(now):
                return retry.EXIT_WAIT
            text = "\n---\n".join(r["snippets"])[:7000]
            msgs = [
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": INSTRUCTION + text},
            ]
            res = call(msgs)
            stopped = record_call(res, datetime.now(UTC))
            if stopped is not None:
                return stopped
            parsed = parse_reply(res.content_text) if res.content_text else None
            if parsed is None and res.status_code == 200 and not args.recovery_probe:
                # one retry for unparsable JSON
                msgs2 = msgs + [
                    {"role": "assistant", "content": res.content_text or ""},
                    {"role": "user", "content": "Return valid JSON only, in the schema above."},
                ]
                if local_wait(datetime.now(UTC)):
                    return retry.EXIT_WAIT
                res = call(msgs2)
                stopped = record_call(res, datetime.now(UTC))
                if stopped is not None:
                    return stopped
                parsed = parse_reply(res.content_text) if res.content_text else None
            if res.status_code != 200 and res.status_code != 0:
                print(f"http {res.status_code} on {r['accession']}; skipping for now", flush=True)
                time.sleep(5)
                continue
            if res.status_code == 0:
                time.sleep(10)
                continue
            row = {
                "accession": r["accession"],
                "cik": r["cik"],
                "filing_date": r["filing_date"],
                "acceptance_datetime": r["acceptance_datetime"],
                "prompt_sha256": ph,
                "parsed": parsed,
                "raw": None if parsed else (res.content_text or "")[:4000],
            }
            if fh is None:
                fh = stack.enter_context(part.open("a"))
            fh.write(json.dumps(row) + "\n")
            fh.flush()
            if parsed is None:
                state = retry.record_failure(
                    FAILURE_STATE,
                    state,
                    {"reason": "unparsable_response", "recovery_at": None},
                    now=datetime.now(UTC),
                )
                if state["blocked"]:
                    print(
                        "no progress; unparsable-response threshold reached; next_action=inspect_failed_response_before_restart",
                        flush=True,
                    )
                    return retry.EXIT_BLOCKED
                continue
            retry.clear_success(FAILURE_STATE, NEXT_TRY)
            state = {}
            n += 1
            if n % 50 == 0:
                print(f"[{datetime.now(UTC):%H:%M:%S}] {n} extracted", flush=True)
    print(f"finished {n}", flush=True)
    if not n:
        print("no progress; next_action=inspect_failed_response_before_restart", flush=True)
        return retry.EXIT_NO_PROGRESS
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
