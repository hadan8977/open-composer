# ruff: noqa: E501
#!/usr/bin/env python3
"""T-20261007-03 step 1c: customer names -> CIK/ticker, point-in-time link table.

Inputs: ``_llm/part_*.jsonl`` (DeepSeek extraction), ``aliases.parquet`` (normalised
company names and SEC former names), ``sic_map`` (cik <-> symbol with dates), the
10-K index (for the next filing of the same supplier), ``name_judgements.json``
(LLM adjudication of names the rules could not settle, optional).

Match tiers: ``alias`` (exact normalised name), ``alias_trim`` (exact after dropping
generic trailing words), ``prefix`` (all customer tokens are the leading tokens of
exactly one alias), ``fuzzy`` (difflib ratio >= 0.93, unique best), ``llm`` (from
the judgements file). Government, anonymous and group customers are kept with no code.

Output ``links_all.parquet`` (every extracted row) and ``links.parquet`` (one row per
supplier filing x customer, latest fiscal year with a percent).
"""

from __future__ import annotations

import difflib
import json
import re
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from t03_build_aliases import norm  # noqa: E402

D = ROOT / "data" / "features" / "economic_links"
TRIM = re.compile(
    r"\b(group|international|stores|store|holdings|usa|us|america|americas|north america|worldwide|global|industries|technologies|systems|energy|resources|bancorp|financial)\b"
)
STRIP = [
    re.compile(r"\(.*?\)"),
    re.compile(r"\b(and|&)\s+(its|their|certain)\b.*$", re.I),
    re.compile(r"\b(and|including)\s+(its\s+)?(affiliates|subsidiaries|affiliated)\b.*$", re.I),
    re.compile(r"\bd/b/a\b.*$", re.I),
    re.compile(r",?\s*together with\b.*$", re.I),
    re.compile(r",\s*(inc|llc|ltd|corp|lp)\b.*$", re.I),
]
MANUAL = {
    "wal mart": "walmart",
    "wal mart stores": "walmart",
    "google": "alphabet",
    "hewlett packard": "hp",
    "at and t": "at and t",
    "amazon com": "amazon com",
    "exxon mobil": "exxon mobil",
    "royal dutch shell": "shell",
    "general electric": "general electric",
    "ibm": "international business machines",
    "gm": "general motors",
    "dow chemical": "dow",
    "facebook": "meta platforms",
}


def clean_name(name: str) -> str:
    s = name
    for r in STRIP:
        s = r.sub("", s)
    n = norm(s)
    return MANUAL.get(n, n)


class Matcher:
    def __init__(self) -> None:
        a = pd.read_parquet(D / "aliases.parquet")
        self.by_alias: dict[str, set[int]] = a.groupby("alias")["cik"].agg(set).to_dict()
        self.keys = sorted(self.by_alias)
        trimmed: dict[str, set[int]] = {}
        for k, v in self.by_alias.items():
            t = re.sub(r"\s+", " ", TRIM.sub(" ", k)).strip()
            if t:
                trimmed.setdefault(t, set()).update(v)
        self.by_trim = trimmed
        self.first_tok: dict[str, list[str]] = {}
        for k in self.keys:
            self.first_tok.setdefault(k.split(" ")[0], []).append(k)
        sic = pd.read_parquet(ROOT / "data/features/sic_map/sic_map.parquet")
        self.sic = sic
        # prefer ciks that have a symbol (listed) when an alias is shared
        self.listed = set(sic["cik"].astype(int))

    def pick(self, ciks: set[int]) -> int | None:
        c = {x for x in ciks if x in self.listed}
        if len(c) == 1:
            return next(iter(c))
        return None

    def match(self, raw: str) -> tuple[int | None, str]:
        n = clean_name(raw)
        if not n:
            return None, "none"
        if n in self.by_alias:
            c = self.pick(self.by_alias[n])
            return (c, "alias") if c else (None, "ambiguous")
        t = re.sub(r"\s+", " ", TRIM.sub(" ", n)).strip()
        if t and t in self.by_trim:
            c = self.pick(self.by_trim[t])
            if c:
                return c, "alias_trim"
        toks = n.split(" ")
        cands = [k for k in self.first_tok.get(toks[0], []) if k.split(" ")[: len(toks)] == toks]
        ciks = {c for k in cands for c in self.by_alias[k]}
        c = self.pick(ciks)
        if c and len(toks[0]) >= 4:
            return c, "prefix"
        close = difflib.get_close_matches(n, self.keys, n=2, cutoff=0.93)
        if close:
            c = self.pick(self.by_alias[close[0]])
            if c and (len(close) == 1 or difflib.SequenceMatcher(None, n, close[1]).ratio() < 0.9):
                return c, "fuzzy"
        return None, "none"

    def candidates(self, raw: str, k: int = 5) -> list[tuple[int, str]]:
        n = clean_name(raw)
        out: list[tuple[int, str]] = []
        for key in difflib.get_close_matches(n, self.keys, n=k, cutoff=0.6):
            for c in self.by_alias[key]:
                if c in self.listed:
                    out.append((c, key))
        return out[:k]


def load_rows() -> list[dict]:
    latest: dict[str, dict] = {}
    for f in sorted((D / "_llm").glob("part_*.jsonl")):
        for line in f.read_text().splitlines():
            if line.strip():
                r = json.loads(line)
                if r.get("parsed") is not None:
                    latest[r["accession"]] = r
    return list(latest.values())


def main() -> int:
    m = Matcher()
    judged = {}
    jp = D / "name_judgements.json"
    if jp.exists():
        judged = json.loads(jp.read_text())
    idx = pd.read_parquet(ROOT / "data/features/text_similarity/filings_index.parquet")
    idx["acc_utc"] = pd.to_datetime(idx["acceptance_datetime"], utc=True)
    idx = idx.sort_values(["cik", "acc_utc"])
    idx["next_acc"] = idx.groupby("cik")["acc_utc"].shift(-1)
    nxt = dict(zip(idx["accession"], idx["next_acc"], strict=False))
    sic = m.sic
    sym_of = sic.groupby("cik")["symbol"].agg(lambda s: ",".join(sorted(set(s)))).to_dict()

    rows = []
    cache: dict[str, tuple[int | None, str]] = {}
    for r in load_rows():
        p = r["parsed"]
        acc = pd.Timestamp(r["acceptance_datetime"])
        acc = acc.tz_localize("UTC") if acc.tzinfo is None else acc.tz_convert("UTC")
        to = nxt.get(r["accession"])
        vis_to = to if pd.notna(to) else acc + pd.Timedelta(days=400)
        base = {
            "supplier_cik": r["cik"],
            "accession": r["accession"],
            "filing_date": r["filing_date"],
            "visible_from": acc,
            "visible_to": vis_to,
            "no_major_customer": bool(p.get("no_major_customer")),
        }
        custs = p.get("customers") or []
        if not custs:
            rows.append({**base, "customer_name": None, "customer_type": "none"})
        for c in custs:
            name, typ = c.get("name"), c.get("type") or "anonymous"
            ccik, how = None, "n/a"
            if name and typ == "company":
                if name not in cache:
                    cache[name] = m.match(name)
                ccik, how = cache[name]
                if ccik is None and name in judged and judged[name]:
                    ccik, how = int(judged[name]), "llm"
            rows.append(
                {
                    **base,
                    "customer_name": name,
                    "customer_type": typ,
                    "customer_cik": ccik,
                    "match_method": how,
                    "customer_symbols": sym_of.get(ccik) if ccik else None,
                    "pct": c.get("pct"),
                    "lower_bound": c.get("lower_bound"),
                    "basis": c.get("basis"),
                    "fiscal_year": c.get("fiscal_year"),
                    "quote": c.get("quote"),
                }
            )
    df = pd.DataFrame(rows)
    df.to_parquet(D / "links_all.parquet", index=False)
    # one row per filing x customer: latest fiscal year, preferring a stated percent
    df["_fy"] = pd.to_numeric(df["fiscal_year"], errors="coerce").fillna(-1)
    df["_has"] = df["pct"].notna().astype(int)
    key = df["customer_name"].fillna("") + "|" + df["customer_type"]
    df["_key"] = key
    best = (
        df.sort_values(["accession", "_key", "_fy", "_has"], ascending=[True, True, False, False])
        .drop_duplicates(["accession", "_key"])
        .drop(columns=["_fy", "_has", "_key"])
    )
    best.to_parquet(D / "links.parquet", index=False)
    comp = best[best["customer_type"] == "company"]
    print(
        f"filings {df.accession.nunique()}, link rows {len(best)}, company rows {len(comp)}, "
        f"matched {comp.customer_cik.notna().sum()} ({comp.customer_cik.notna().mean():.0%})"
    )
    print(comp["match_method"].value_counts().to_dict())
    unmatched = comp[comp["customer_cik"].isna()]["customer_name"].value_counts()
    print("top unmatched:", unmatched.head(25).to_dict())
    return 0


if __name__ == "__main__":
    sys.exit(main())
