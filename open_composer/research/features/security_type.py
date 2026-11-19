"""Dated SEC issuer evidence for the daily SIP universe."""

import json
from zipfile import ZipFile

import pandas as pd

from open_composer.adapters.events.fetcher import sec_submission_tables
from open_composer.market_sessions import NEW_YORK

STOCK_TYPES = ("operating", "adr")
FORMS = {
    "operating": {"10-K", "10-Q", "40-F", "8-K", "S-1", "F-1"},
    "adr": {"20-F", "6-K"},
    "fund": {
        "N-CSR", "N-CSRS", "N-PORT", "NPORT-P", "NPORT-EX", "N-CEN", "N-1A",
        "485BPOS", "485APOS", "N-2", "N-8A", "N-8B-2", "N-14", "497K",
    },
}
INSTRUMENT_SUFFIX = r"(?:[./-](?:WS|WT|U|R|RT|RTWI|PR[A-Z0-9]?)|[-/^]P[A-Z0-9]{0,2})$"


def register_security_evidence(con, symbols):
    from scripts.build_sec_sic_map import HISTORY_PATH, SUBMISSIONS_DIR, member_name

    # Match earnings_releases: carry forward first observations without using
    # the reconstructed interval end or the current tickers in the SEC snapshot.
    history = pd.read_parquet(HISTORY_PATH, columns=["cik", "symbol", "first_date"])
    history = history.loc[history.symbol.isin(symbols)]
    links = history.groupby(["symbol", "first_date"]).cik.agg(["min", "max"]).reset_index()
    links["cik"] = links["min"].where(links["min"] == links["max"]).astype("Int64")
    links["link_at"] = (
        (links.first_date + pd.Timedelta(days=1)).dt.tz_localize(NEW_YORK).dt.tz_convert("UTC")
    )
    links["next_link_at"] = links.groupby("symbol").link_at.shift(-1)
    con.register("security_links", links[["symbol", "cik", "link_at", "next_link_at"]])

    form_type = {form: kind for kind, forms in FORMS.items() for form in forms}
    evidence = []
    with ZipFile(SUBMISSIONS_DIR / "submissions-current.zip") as source:
        names = set(source.namelist())

        def read_page(name):
            return json.loads(source.read(name))

        for cik in sorted(links.cik.dropna().unique()):
            name = member_name(cik)
            if name not in names:
                continue
            first = {}
            for table in sec_submission_tables(read_page(name)["filings"], start="", read_page=read_page):
                for form, accepted in zip(table["form"], table["acceptanceDateTime"], strict=True):
                    kind = form_type.get(form.removesuffix("/A"))
                    if kind and accepted and (kind not in first or accepted < first[kind]):
                        first[kind] = accepted
            evidence.append({"cik": cik, **first})
    filings = pd.DataFrame(evidence, columns=["cik", *FORMS])
    for kind in FORMS:
        filings[kind] = pd.to_datetime(filings[kind], utc=True)
    con.register("security_filings", filings)


# The type is selected at the next regular open, strictly after its evidence.
# A known fund filing overrides an operating or foreign-issuer filing.
TYPED_MEMBERS = f"""
    SELECT m.*, c.session, c.known_at, l.cik AS issuer_cik,
           CASE
               WHEN regexp_matches(m.symbol, '{INSTRUMENT_SUFFIX}') THEN 'other'
               WHEN f.fund < c.decision_at THEN 'fund'
               WHEN f.adr < c.decision_at THEN 'adr'
               WHEN f.operating < c.decision_at THEN 'operating'
               ELSE 'unknown'
           END AS security_type,
           CASE
               WHEN regexp_matches(m.symbol, '{INSTRUMENT_SUFFIX}') THEN c.known_at
               WHEN f.fund < c.decision_at THEN greatest(l.link_at, f.fund)
               WHEN f.adr < c.decision_at THEN greatest(l.link_at, f.adr)
               WHEN f.operating < c.decision_at THEN greatest(l.link_at, f.operating)
           END AS security_type_known_at
    FROM members m
    JOIN calendar c USING (trade_date)
    LEFT JOIN security_links l
      ON m.issuer_symbol = l.symbol AND l.link_at < c.decision_at
      AND coalesce(l.next_link_at, 'infinity'::TIMESTAMPTZ) >= c.decision_at
    LEFT JOIN security_filings f USING (cik)
"""
