# ruff: noqa: E501
#!/usr/bin/env python3
"""T-20261007-03 step 1d: DeepSeek adjudication of customer names the rules could not match.

Reads ``links.parquet`` (from ``t03_build_links.py``), takes unique company-type names with no
CIK, shows the model up to 5 fuzzy candidates per name plus the supplier quote, and writes
``name_judgements.json`` {name: cik or null}. 15 names per call; shares the call ledger, the 5-hour
cap and the lock of ``t03_llm_extract.py`` (run it after the extraction finished).
"""

from __future__ import annotations

import fcntl
import json
import re
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import score_earnings_text as st  # noqa: E402
import t03_build_links as bl  # noqa: E402
import t03_llm_extract as ex  # noqa: E402

D = ex.DATA
OUTJ = D / "name_judgements.json"
BATCH = 15

SYSTEM = "You match company names from annual-report customer disclosures to US-listed companies. Return only JSON."
INSTR = """For each item, decide which candidate (by id) is the SAME company as the customer name, a parent or the listed company whose stock price reflects this customer. Rules:
- Pick a candidate only when you are confident (same company, a former name, a brand of it, or its listed parent). Wholly owned subsidiaries map to the listed parent.
- If the customer is private, foreign-only, a government, a hospital, or none of the candidates fits, answer null.
- If you are confident the customer is a US-listed company that is NOT among the candidates, you may give "ticker" (its exchange ticker) instead of an id.
Return a JSON list, one object per item in order: [{"n": item number, "id": candidate id or null, "ticker": string or null}]
Items:
"""


def main() -> int:
    links = pd.read_parquet(D / "links.parquet")
    comp = links[(links["customer_type"] == "company") & links["customer_cik"].isna()]
    names = comp.groupby("customer_name").agg(n=("accession", "size"), quote=("quote", "first"))
    judged = json.loads(OUTJ.read_text()) if OUTJ.exists() else {}
    todo = [n for n in names.sort_values("n", ascending=False).index if n not in judged]
    print(f"unmatched unique names {len(names)}, to judge {len(todo)}", flush=True)
    if not todo:
        return 0
    lock = (D / "_llm" / ".lock").open("w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print("extraction process holds the lock; run after it finished", flush=True)
        return 0
    m = bl.Matcher()
    sic = m.sic
    sym2cik = {s: int(c) for s, c in zip(sic["symbol"], sic["cik"], strict=False)}
    creds = st.load_credentials(st.CREDENTIALS_PATH)
    call = st.make_requests_chat_call_fn(
        base_url=creds["OC_TEXT_SCORER_BASE_URL"],
        api_key=creds["OC_TEXT_SCORER_API_KEY"],
        model=creds["OC_TEXT_SCORER_MODEL"],
        max_tokens=1500,
    )
    ncalls = 0
    with ex.LEDGER.open("a") as led:
        for i in range(0, len(todo), BATCH):
            chunk = todo[i : i + BATCH]
            now = datetime.now(UTC)
            used = ex.calls_in_window(now)
            if len(used) >= ex.CAP_PER_5H:
                nt = min(used) + ex.WINDOW + timedelta(seconds=30)
                print(f"cap reached; next try {nt.isoformat()}", flush=True)
                break
            lines, cand_ids = [], []
            for j, name in enumerate(chunk, 1):
                cands = m.candidates(name, 5)
                cand_ids.append({str(k): c for k, (c, _) in enumerate(cands, 1)})
                cl = (
                    "; ".join(
                        f"{k}={a} [{m.sic[m.sic.cik == c].symbol.iloc[0] if (m.sic.cik == c).any() else '?'}]"
                        for k, (c, a) in enumerate(cands, 1)
                    )
                    or "none"
                )
                q = str(names.loc[name, "quote"] or "")[:160]
                lines.append(f'{j}. name="{name}" quote="{q}" candidates: {cl}')
            res = call(
                [
                    {"role": "system", "content": SYSTEM},
                    {"role": "user", "content": INSTR + "\n".join(lines)},
                ]
            )
            led.write(
                json.dumps(
                    {
                        "t": now.isoformat(),
                        "status": res.status_code,
                        "pt": res.prompt_tokens,
                        "ct": res.completion_tokens,
                    }
                )
                + "\n"
            )
            led.flush()
            ncalls += 1
            if st.is_rate_limited(res):
                nt = st.compute_next_try_at(res, now=now)
                ex.NEXT_TRY.write_text(
                    json.dumps({"next_try_at": nt.isoformat(), "reason": "adjudication"})
                )
                print("rate limited", flush=True)
                break
            mm = re.search(r"\[.*\]", res.content_text or "", re.S)
            try:
                arr = json.loads(mm.group(0)) if mm else []
            except ValueError:
                arr = []
            got = {int(o.get("n", 0)): o for o in arr if isinstance(o, dict)}
            for j, name in enumerate(chunk, 1):
                o = got.get(j)
                if o is None:
                    continue
                cik = None
                if o.get("id") is not None:
                    cik = cand_ids[j - 1].get(str(o["id"]))
                elif o.get("ticker"):
                    cik = sym2cik.get(str(o["ticker"]).upper())
                judged[name] = int(cik) if cik else None
            OUTJ.write_text(json.dumps(judged))
    print(f"calls {ncalls}, judged {len(judged)}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
