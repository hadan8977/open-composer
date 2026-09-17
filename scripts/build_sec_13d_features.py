"""H-20260916-05 step 0b: the Schedule 13D/13G point-in-time filing table.

Reads what ``scripts/collect_sec_13d_filings.py`` collected
(``data/raw/sec_13d/``) and writes the one table every 13D-based card reads:

``data/features/sec_13d/filings.parquet``
    One row per (accession, issuer). Columns in :data:`FILING_COLUMNS`.
``data/features/sec_13d/manifest.json``
    ``fetched_at``, row/event counts by form and year, and the gap list
    (quarters with no index, accessions whose document request failed, form
    types deliberately not document-fetched, parse-confidence mix).

The point-in-time rule, in one place
------------------------------------
``visible_session`` is the first US equity session on which a trader could
have acted on the filing *inside* that session:

* acceptance timestamp is EDGAR's ``<ACCEPTANCE-DATETIME>``, which is ET;
* if the acceptance date is a session and the time is before that session's
  close (16:00 ET, 13:00 on an early close), the filing is visible that
  session;
* otherwise the next session.

That is strictly more conservative than EDGAR's own 17:30 ET dissemination
cutoff (17:30 is after every close, so a filing accepted between the close
and 17:30 is "same business day" for EDGAR but is *next session* here).

``entry_session`` is the session after ``visible_session`` -- the card's
entry is the next session's open, never the visible session's own open,
because a filing accepted at 15:55 ET would otherwise be bought at a price
that printed before it existed.

13G rows carry no acceptance timestamp because the 13G family is not
document-fetched (see the collector's ``--forms`` note: 28,828 SC 13G/A in
2024Q1 alone). Their ``visible_confidence`` is ``filing_date_only`` and
their ``visible_session`` is the session after ``Date Filed``, which is the
conservative reading of a timestamp we do not have. Nothing in the card's
primary test uses them.

Usage::

    ./scripts/run_capped.sh --mem 1.8G -- \\
        uv run python scripts/build_sec_13d_features.py
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import UTC, date, datetime, time
from functools import cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402

from open_composer.market_calendar import (  # noqa: E402
    next_us_equity_session,
    us_equity_session_close,
)
from scripts.collect_sec_13d_filings import (  # noqa: E402
    DEFAULT_FETCH_FORMS,
    DEFAULT_UNIVERSE_TOP_N,
    SCHEDULE_13_FORMS,
    TARGETS_PATH,
    load_company_tickers,
    load_docs,
    load_index,
)

OUT_ROOT = ROOT / "data" / "features" / "sec_13d"
FILINGS_PATH = OUT_ROOT / "filings.parquet"
MANIFEST_PATH = OUT_ROOT / "manifest.json"
UNIVERSE_ROOT = ROOT / "data" / "features" / "universe"

FILING_COLUMNS: tuple[str, ...] = (
    "accession",
    "form_type",
    "is_new_13d",
    "is_amendment",
    "filing_date",
    "acceptance_datetime_et",
    "visible_session",
    "entry_session",
    "visible_confidence",
    "issuer_cik",
    "issuer_symbol",
    "issuer_name",
    "issuer_match",
    "filer_names",
    "percent_of_class",
    "percent_parse_confidence",
    "percent_parse_source",
    "item4_chars",
    "item4_present",
    "universe_month_end",
    "universe_adv_rank",
    "universe_bucket",
    "size_tercile_dollar_adv",
    "dollar_adv",
    "doc_fetched",
    "truncated",
    "issuer_verified",
    "issuer_name_matches_current_registrant",
)

_NAME_NOISE = {
    "INC",
    "INCORPORATED",
    "CORP",
    "CORPORATION",
    "CO",
    "COMPANY",
    "COMPANIES",
    "LP",
    "LLC",
    "LTD",
    "LIMITED",
    "PLC",
    "NV",
    "SA",
    "AG",
    "HOLDING",
    "HOLDINGS",
    "GROUP",
    "THE",
    "TRUST",
    "PARTNERS",
    "PARTNERSHIP",
    "CLASS",
    "COMMON",
    "STOCK",
    "NEW",
    "DE",
    "AND",
}


def _name_tokens(value: object) -> set[str]:
    text = re.sub(r"[^A-Z0-9 ]+", " ", str(value or "").upper())
    return {token for token in text.split() if token and token not in _NAME_NOISE}


def _names_match(filing_name: object, registrant_title: object) -> bool | None:
    """Does the filing's issuer name still match SEC's current name for that CIK?

    A mismatch means the registrant was renamed, which usually means the
    ticker changed too -- and because the SIP tape stores bars under the
    ticker that was live on the trade date, a renamed issuer's *current*
    ticker can point at a different company's history. This flag is what the
    event study's ticker-consistency robustness row conditions on; it is not
    used to drop rows silently.
    """
    if registrant_title is None:
        return None
    left, right = _name_tokens(filing_name), _name_tokens(registrant_title)
    if not left or not right:
        return None
    overlap = len(left & right)
    return overlap >= 1 and overlap / min(len(left), len(right)) >= 0.5


@cache
def _session_close(day: date) -> time | None:
    """Memoized ``us_equity_session_close``.

    ``market_calendar._holidays`` rebuilds a year's holiday set (including an
    Easter computation) on every call and is not cached upstream, which made
    the per-filing visibility loop the slowest part of this build by an order
    of magnitude at 100k+ rows. Caching here is local and behaviour-preserving
    -- the calendar itself is untouched.
    """
    return us_equity_session_close(day)


@cache
def _next_session(day: date) -> date:
    return next_us_equity_session(day)


def visible_session(acceptance_et: pd.Timestamp) -> date:
    """First US equity session a trader could act on a filing accepted at
    ``acceptance_et`` (ET, tz-naive)."""
    stamp = pd.Timestamp(acceptance_et)
    if stamp.tzinfo is not None:
        stamp = stamp.tz_convert("America/New_York").tz_localize(None)
    day = stamp.date()
    close = _session_close(day)
    if close is not None and stamp.time() < close:
        return day
    return _next_session(day)


def entry_session(visible: date) -> date:
    """The session after ``visible`` -- where the card's entry price lives."""
    return _next_session(visible)


def _parse_acceptance(value: object) -> pd.Timestamp | None:
    text = str(value or "").strip()
    if len(text) < 14 or not text[:14].isdigit():
        return None
    try:
        return pd.Timestamp(datetime.strptime(text[:14], "%Y%m%d%H%M%S"))
    except ValueError:
        return None


def universe_cohort_table(top_n: int) -> pd.DataFrame:
    """The PIT cohort table this build joins against: one row per
    (month_end, symbol) with ``adv_rank``, ``dollar_adv`` and a liquidity
    tercile cut *inside that month's cohort*.

    Terciles are cut per cohort so "large/mid/small" always means "relative
    to that month's top-N", never relative to the whole history.

    ``dollar_adv`` is a *market-cap proxy*, not market cap: the universe
    panel has no shares outstanding and this repo has no free point-in-time
    share-count source, so every "size tercile" in this card is a liquidity
    tercile. Stated here so no downstream report can quote it as market cap.
    """
    from open_composer.research.features.universe import load_universe_panel

    panel = load_universe_panel(UNIVERSE_ROOT)
    panel = panel.loc[panel["adv_rank"] <= top_n, ["month_end", "symbol", "adv_rank", "dollar_adv"]]
    panel = panel.copy()
    panel["size_tercile_dollar_adv"] = (
        panel.groupby("month_end")["dollar_adv"]
        .transform(
            lambda values: pd.qcut(values.rank(method="first"), 3, labels=["small", "mid", "large"])
        )
        .astype(str)
    )
    return panel.sort_values(["month_end", "symbol"]).reset_index(drop=True)


def attach_universe_membership(frame: pd.DataFrame, cohorts: pd.DataFrame) -> pd.DataFrame:
    """As-of join every filing onto the last cohort whose ``month_end`` is on
    or before its filing date.

    Vectorized (``merge_asof`` with ``by=symbol``) rather than a per-row
    cohort scan: the filing table is ~100k rows against ~129 monthly cohorts
    and the row-wise version was the slowest step in the build by far.
    Filings with no matching cohort row -- an issuer outside the top-N that
    month, or a filing before the first cohort -- come back as
    ``universe_bucket == "outside"`` rather than being dropped, so the
    coverage gap stays countable in the manifest.
    """
    left = frame.reset_index(drop=True).copy()
    left["_row"] = range(len(left))
    left["_symbol"] = left["issuer_symbol"].astype("string")
    left["filing_date"] = left["filing_date"].astype("datetime64[ns]")
    sortable = left.loc[left["_symbol"].notna()].sort_values("filing_date")
    right = cohorts.rename(columns={"symbol": "_symbol"}).copy()
    right["_symbol"] = right["_symbol"].astype("string")
    # merge_asof requires identical datetime resolutions: the universe
    # parquet carries microsecond timestamps and the filing dates are
    # nanosecond, which merge_asof rejects outright rather than coercing.
    right["month_end"] = right["month_end"].astype("datetime64[ns]")
    right = right.sort_values("month_end")
    merged = pd.merge_asof(
        sortable[["_row", "_symbol", "filing_date"]],
        right,
        left_on="filing_date",
        right_on="month_end",
        by="_symbol",
        direction="backward",
    )
    merged = merged.set_index("_row")
    left = left.set_index("_row")
    left["universe_month_end"] = merged["month_end"]
    left["universe_adv_rank"] = pd.to_numeric(merged["adv_rank"], errors="coerce").astype("Int64")
    left["dollar_adv"] = pd.to_numeric(merged["dollar_adv"], errors="coerce")
    left["size_tercile_dollar_adv"] = merged["size_tercile_dollar_adv"].fillna("na")
    rank = left["universe_adv_rank"]
    left["universe_bucket"] = pd.Series("outside", index=left.index)
    left.loc[rank.notna() & (rank <= 500), "universe_bucket"] = "top500"
    left.loc[rank.notna() & (rank > 500), "universe_bucket"] = "501_1000"
    return left.reset_index(drop=True).drop(columns=["_symbol"])


def build_filings(*, top_n: int) -> tuple[pd.DataFrame, dict[str, object]]:
    index = load_index()
    targets = pd.read_parquet(TARGETS_PATH)
    docs = load_docs()
    tickers = load_company_tickers(None)
    cik_to_symbol = (
        tickers.sort_values("symbol").drop_duplicates(subset=["cik"]).set_index("cik")["symbol"]
    )

    candidates = (
        targets.groupby("accession")
        .agg(
            candidate_ciks=("candidate_cik", lambda values: sorted({int(v) for v in values})),
            candidate_symbols=("candidate_symbol", lambda values: sorted(set(values))),
            index_form_type=("form_type", "first"),
            index_date_filed=("date_filed", "first"),
        )
        .reset_index()
    )

    fetched = docs.loc[docs["http_status"] == 200].copy()
    fetched = fetched.sort_values("accession").drop_duplicates(subset=["accession"], keep="last")
    merged = candidates.merge(fetched, on="accession", how="left", suffixes=("", "_doc"))

    resolved: list[dict[str, object]] = []
    for row in merged.itertuples(index=False):
        header_cik = row.issuer_cik
        header_cik = int(header_cik) if pd.notna(header_cik) else None
        symbol: str | None = None
        match = "unresolved"
        # The index-derived candidate is whichever *associated* CIK happened to
        # map to a universe ticker, and for a Schedule 13D the filer is the
        # activist -- so when the header gives an issuer CIK that has no
        # current ticker (delisted, acquired, or simply not listed), falling
        # back to the single candidate attributes the event to the *activist's*
        # own listed company. Observed on a 164-filing sample: 38 rows (23%),
        # including a Goldman Sachs 13D on EnLink Midstream booked as an event
        # on GS. Those rows are now counted as unresolved -- which is exactly
        # the survivorship gap this table has to make visible, not hide.
        if header_cik is not None:
            mapped = cik_to_symbol.get(header_cik)
            if isinstance(mapped, str):
                symbol, match = mapped, "header_subject_cik"
            elif header_cik in set(row.candidate_ciks):
                position = list(row.candidate_ciks).index(header_cik)
                symbol, match = list(row.candidate_symbols)[position], "header_cik_in_candidates"
            else:
                match = "header_issuer_has_no_current_ticker"
        elif len(row.candidate_symbols) == 1:
            symbol = str(row.candidate_symbols[0])
            match = "single_candidate_index_only"
        elif len(row.candidate_symbols) > 1:
            match = "ambiguous_index_only"
        resolved.append(
            {
                "accession": row.accession,
                "form_type": str(row.form_type) if pd.notna(row.form_type) else row.index_form_type,
                "filing_date": pd.Timestamp(row.index_date_filed),
                "acceptance_datetime_et": row.acceptance_datetime_et,
                "issuer_cik": header_cik,
                "issuer_name": row.issuer_name,
                "issuer_symbol": symbol,
                "issuer_match": match,
                "filer_names": row.filer_names,
                "percent_of_class": row.percent_of_class,
                "percent_parse_confidence": row.percent_parse_confidence,
                "percent_parse_source": row.percent_parse_source,
                "item4_chars": row.item4_chars,
                "item4_present": row.item4_present,
                "doc_fetched": bool(pd.notna(row.http_status)),
                "truncated": row.truncated,
            }
        )
    frame = pd.DataFrame(resolved)

    frame["percent_parse_confidence"] = frame["percent_parse_confidence"].fillna("none")
    frame["percent_parse_source"] = frame["percent_parse_source"].fillna("not_fetched")
    frame["item4_chars"] = (
        pd.to_numeric(frame["item4_chars"], errors="coerce").fillna(0).astype("int64")
    )
    frame["item4_present"] = frame["item4_present"].astype("boolean").fillna(False).astype(bool)
    frame["truncated"] = frame["truncated"].astype("boolean").fillna(False).astype(bool)
    frame["form_type"] = frame["form_type"].astype(str).str.strip().str.upper()
    frame["is_amendment"] = frame["form_type"].str.endswith("/A")
    frame["is_new_13d"] = frame["form_type"] == "SC 13D"

    # A list, not ``Series.map``: when every parsed value is a Timestamp
    # pandas infers a datetime64 series and turns the ``None`` misses into
    # ``NaT``, which is not ``None`` and silently reaches the calendar with a
    # float year.
    acceptance = [_parse_acceptance(value) for value in frame["acceptance_datetime_et"]]
    frame["visible_confidence"] = [
        "acceptance_datetime" if stamp is not None else "filing_date_only" for stamp in acceptance
    ]
    visible: list[date] = []
    for stamp, filing_day in zip(acceptance, frame["filing_date"], strict=True):
        if stamp is not None:
            visible.append(visible_session(stamp))
        else:
            visible.append(_next_session(pd.Timestamp(filing_day).date()))
    frame["visible_session"] = visible
    frame["entry_session"] = [entry_session(day) for day in visible]

    # ``issuer_verified`` is the single column downstream tests must filter on.
    # Only a fetched header proves which party is the issuer: for a Schedule
    # 13D the other party is the activist, and for a 13G it is usually a large
    # index manager that is itself a listed top-1000 name (BLK, BEN, TROW...),
    # so an index-only attribution can silently turn "BlackRock filed a 13G on
    # a micro cap" into "an event on BLK".
    frame["issuer_verified"] = frame["issuer_match"] == "header_subject_cik"
    cik_to_title = (
        tickers.drop_duplicates(subset=["cik"]).set_index("cik")["company_title"].to_dict()
    )
    frame["issuer_name_matches_current_registrant"] = [
        _names_match(name, cik_to_title.get(cik)) if cik is not None else None
        for name, cik in zip(frame["issuer_name"], frame["issuer_cik"], strict=True)
    ]
    frame = attach_universe_membership(frame, universe_cohort_table(top_n))
    frame = (
        frame[list(FILING_COLUMNS)].sort_values(["filing_date", "accession"]).reset_index(drop=True)
    )

    in_universe = frame.loc[frame["universe_bucket"] != "outside"]
    index_accessions = index.drop_duplicates("accession")
    manifest = {
        "schema": "sec_13d_filings.v1",
        "card": "H-20260916-05",
        "fetched_at": datetime.now(UTC).isoformat(),
        "source": {
            "quarterly_form_index": "https://www.sec.gov/Archives/edgar/full-index/{yyyy}/QTR{n}/form.idx",
            "complete_submission": "https://www.sec.gov/Archives/{file_name}",
            "company_tickers": "https://www.sec.gov/files/company_tickers.json",
        },
        "universe_top_n": top_n,
        "index_quarters": sorted(
            path.stem for path in (ROOT / "data" / "raw" / "sec_13d" / "index").glob("*.parquet")
        ),
        "edgar_index_accessions_all_issuers": int(len(index_accessions)),
        "edgar_index_accessions_by_form": {
            str(key): int(value)
            for key, value in index_accessions["form_type"].value_counts().items()
        },
        "rows": int(len(frame)),
        "rows_in_universe": int(len(in_universe)),
        "rows_by_form": {
            str(key): int(value) for key, value in frame["form_type"].value_counts().items()
        },
        "in_universe_by_form": {
            str(key): int(value) for key, value in in_universe["form_type"].value_counts().items()
        },
        "new_13d_in_universe_by_year": {
            str(key): int(value)
            for key, value in in_universe.loc[in_universe["is_new_13d"], "filing_date"]
            .dt.year.value_counts()
            .sort_index()
            .items()
        },
        "issuer_name_matches_current_registrant": {
            "true": int((frame["issuer_name_matches_current_registrant"] == True).sum()),  # noqa: E712
            "false": int((frame["issuer_name_matches_current_registrant"] == False).sum()),  # noqa: E712
            "unknown": int(frame["issuer_name_matches_current_registrant"].isna().sum()),
            "note": (
                "False = the registrant was renamed since the filing, so its current ticker may "
                "carry another company's older bars; the event study reports a subsample "
                "restricted to True"
            ),
        },
        "issuer_verified_counts": {
            "true": int(frame["issuer_verified"].sum()),
            "false": int((~frame["issuer_verified"]).sum()),
            "note": (
                "only a fetched filing header proves which party is the issuer; index-only rows "
                "(the whole 13G family in this build) are not header-verified and must not be "
                "used as events"
            ),
        },
        "issuer_match_counts": {
            str(key): int(value) for key, value in frame["issuer_match"].value_counts().items()
        },
        "visible_confidence_counts": {
            str(key): int(value)
            for key, value in frame["visible_confidence"].value_counts().items()
        },
        "percent_parse_confidence_counts": {
            str(key): int(value)
            for key, value in frame["percent_parse_confidence"].value_counts().items()
        },
        "gaps": {
            "forms_not_document_fetched": [
                form for form in SCHEDULE_13_FORMS if form not in DEFAULT_FETCH_FORMS
            ],
            "document_http_failures": int((docs["http_status"] != 200).sum()),
            "truncated_documents": int(frame["truncated"].sum()),
            "issuer_unresolvable_rows": int(
                frame["issuer_match"]
                .isin(["header_issuer_has_no_current_ticker", "ambiguous_index_only", "unresolved"])
                .sum()
            ),
            "issuer_has_no_current_ticker_rows": int(
                (frame["issuer_match"] == "header_issuer_has_no_current_ticker").sum()
            ),
            "outside_universe_rows": int((frame["universe_bucket"] == "outside").sum()),
            "company_tickers_is_current_snapshot": (
                "issuers acquired or delisted before the snapshot have no ticker row, so their "
                "13D filings cannot be mapped at all; the PIT universe is itself built from "
                "surviving symbols only"
            ),
        },
    }
    return frame, manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--universe-top-n", type=int, default=DEFAULT_UNIVERSE_TOP_N)
    args = parser.parse_args(argv)

    frame, manifest = build_filings(top_n=args.universe_top_n)
    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    temporary = FILINGS_PATH.with_suffix(".parquet.part")
    frame.to_parquet(temporary, index=False, compression="zstd")
    temporary.replace(FILINGS_PATH)
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(json.dumps(manifest, indent=2, sort_keys=True)[:4000], flush=True)
    print(f"wrote {FILINGS_PATH} ({len(frame):,} rows)", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
