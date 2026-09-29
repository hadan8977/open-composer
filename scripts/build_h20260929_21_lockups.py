"""T-20260929-21: build a point-in-time IPO share-lockup-expiration event list.

Card: ``reports/research/iterations/h20260929_21_ipo_lockup_expiry``.
Intel: ``reports/research/intel/I-20260929-01-short-horizon-selective.md`` S2.3/S4
(Field & Hanka 2001 JF: 3-day CAR approx -1.5% to -1.8% at IPO share-lockup
expiration; Gibbs & Hao 2018 JBF: PE-backed IPOs do NOT show the effect,
short-squeeze tail risk is real -- Yelp +23% on its 2012-08-29 lockup date).

Event construction, two methods
--------------------------------
``424b4_confirmed``
    An SEC EDGAR 424B4 (final prospectus) filing whose filer/subject CIK maps
    (via the SEC's *current* ``company_tickers.json`` snapshot) to a ticker
    that begins trading in our local daily panel within a tight window of the
    filing date (-3..+5 calendar days -- the SEC requires a 424(b)(4) to be
    filed within 2 business days of pricing, and IPOs begin trading 0-1
    sessions after pricing). This tight window is what turns a 424B4 index
    (which also contains thousands of follow-on/secondary offerings by
    already-listed issuers) into a genuine-IPO candidate set, entirely from
    already-downloaded index data -- no extra network fetch is needed to
    apply it.
``first_trade_fallback``
    A symbol's first trading day in the local daily panel, for symbols not
    already claimed by a ``424b4_confirmed`` match, restricted to
    ``PANEL_START + FALLBACK_MIN_PANEL_AGE_DAYS`` .. panel end (a symbol
    present on day 1 of the panel is not evidence of an IPO -- the panel
    simply starts there) and passing the exclusion heuristics documented on
    ``classify_fallback_candidate``.

Lockup date
-----------
IPO date + 180 calendar days, rolled forward to the next date present in the
daily panel's own trading-day index (not an external holiday calendar). Where
a 424B4 full-text fetch found an explicit "N day(s)" lock-up period near a
"lock-up"/"lock up" mention, that N is used instead of 180 and
``lockup_days_source="parsed"``; otherwise ``lockup_days_source="assumed_180"``.

de-SPAC tagging
----------------
``is_despac`` is a best-effort tag (not a filter): True if EITHER (a) the
fetched filing text contains a de-SPAC keyword ("blank check", "business
combination company", "special purpose acquisition") or (b) the symbol's
first 20 trading-panel sessions average close is within $9.50-$10.50 with a
21-session return stdev < 1.5% (the flat, cash-in-trust price signature of a
SPAC that has not yet found a merger target). Per the brief this is a
caveat/tag, not a full de-SPAC merger-date lockup model.

Stages (index -> map -> fetch -> build), each resumable.

Usage::

    scripts/run_capped.sh --mem 1.8G -- uv run python \\
        scripts/build_h20260929_21_lockups.py --stage index
    scripts/run_capped.sh --mem 1.8G -- uv run python \\
        scripts/build_h20260929_21_lockups.py --stage map
    scripts/run_capped.sh --mem 1.8G -- uv run python \\
        scripts/build_h20260929_21_lockups.py --stage fetch
    scripts/run_capped.sh --mem 1.8G -- uv run python \\
        scripts/build_h20260929_21_lockups.py --stage build
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from collect_sec_13d_filings import (  # noqa: E402
    Quarter,
    SecClient,
    load_company_tickers,
    log,
    parse_quarter,
    quarter_of,
    quarter_range,
)
from dotenv import load_dotenv  # noqa: E402

RAW_ROOT = ROOT / "data" / "sec" / "424b4"
INDEX_ROOT = RAW_ROOT / "index"
DOCS_ROOT = RAW_ROOT / "docs"
TARGETS_PATH = RAW_ROOT / "targets.parquet"
DOCS_PATH = RAW_ROOT / "docs.parquet"

ITER_DIR = ROOT / "reports" / "research" / "iterations" / "h20260929_21_ipo_lockup_expiry"
EVENTS_PATH = ITER_DIR / "events.parquet"
HANDCHECK_PATH = ITER_DIR / "handcheck_sample.json"

DAILY_BROAD_DIR = ROOT / "data" / "features" / "daily_broad"


def _read_daily_broad(columns: list[str]) -> pd.DataFrame:
    paths = sorted(DAILY_BROAD_DIR.glob("*.parquet"))
    if not paths:
        raise FileNotFoundError(f"no parquet files under {DAILY_BROAD_DIR}")
    return pd.concat([pd.read_parquet(p, columns=columns) for p in paths], ignore_index=True)


QUARTER_INDEX_URL = "https://www.sec.gov/Archives/edgar/full-index/{year}/QTR{qtr}/form.idx"
ARCHIVE_URL = "https://www.sec.gov/Archives/{file_name}"

FORM_TYPE = "424B4"
DEFAULT_START_QUARTER = "2015q1"
DEFAULT_END_QUARTER = "2026q3"
DEFAULT_MAX_BYTES = 400_000

# Confirmed-IPO cross-check window: filing_date -3 .. +5 calendar days vs the
# ticker's first appearance in the daily panel.
CONFIRM_WINDOW_BEFORE_DAYS = 3
CONFIRM_WINDOW_AFTER_DAYS = 5

# Fallback candidates must be at least this many calendar days after the
# panel's own first date, else "first appearance" just reflects panel
# truncation, not a real IPO.
FALLBACK_MIN_PANEL_AGE_DAYS = 180
FALLBACK_MIN_FIRST_CLOSE = 3.0  # excludes shells / reverse-split artifacts

LOCKUP_DAYS_DEFAULT = 180

DESPAC_TEXT_KEYWORDS = (
    "blank check company",
    "blank check corporation",
    "special purpose acquisition",
    "business combination company",
)
_LOCKUP_DAYS_RE = re.compile(r"lock[\s\-]?up\s+period[^.]{0,80}?(\d{2,3})\s+day", re.IGNORECASE)
_LOCKUP_DAYS_RE_ALT = re.compile(r"(\d{2,3})\s+day[^.]{0,60}?lock[\s\-]?up", re.IGNORECASE)


# --------------------------------------------------------------------------
# stage: index
# --------------------------------------------------------------------------


def parse_424b4_index(payload: bytes) -> pd.DataFrame:
    """Parse EDGAR's space-padded ``form.idx``, keeping only ``424B4`` rows.

    Same robust structural split as ``collect_sec_13d_filings.parse_form_index``
    (archive path is the last whitespace token; CIK/Date Filed are the two
    tokens before the company name; form type is what remains) rather than
    fixed-width column slicing, which the 2024-12-18 SC 13D/G rename broke
    for that script. ``424B4`` was not renamed in that mandate, but the
    structural parse is reused anyway for robustness and to keep both
    collectors' output shape consistent.
    """
    rows: list[tuple[str, str, str, str]] = []
    started = False
    for raw in payload.decode("latin-1").splitlines():
        if not started:
            started = raw.startswith("---")
            continue
        if not raw.strip():
            continue
        parts = raw.rsplit(None, 1)
        if len(parts) != 2:
            continue
        head, file_name = parts
        tokens = head.rsplit(None, 2)
        if len(tokens) != 3:
            continue
        form_and_company, cik, date_filed = tokens
        split = re.split(r"\s{2,}", form_and_company.strip(), maxsplit=1)
        form_type = split[0].strip().upper()
        if form_type != FORM_TYPE:
            continue
        company = split[1].strip() if len(split) > 1 else ""
        rows.append((company, cik, date_filed, file_name))
    frame = pd.DataFrame(rows, columns=["company_name", "cik", "date_filed", "file_name"])
    frame["cik"] = pd.to_numeric(frame["cik"], errors="coerce").astype("Int64")
    frame["date_filed"] = pd.to_datetime(frame["date_filed"], errors="coerce")
    frame["accession"] = frame["file_name"].map(lambda v: Path(str(v)).stem)
    frame["form_type"] = FORM_TYPE
    return frame.reset_index(drop=True)


def stage_index(client: SecClient, quarters: list[Quarter], *, force: bool) -> dict[str, str]:
    INDEX_ROOT.mkdir(parents=True, exist_ok=True)
    outcome: dict[str, str] = {}
    for quarter in quarters:
        target = INDEX_ROOT / f"{quarter}.parquet"
        if target.exists() and not force:
            outcome[str(quarter)] = "already_present"
            continue
        url = QUARTER_INDEX_URL.format(year=quarter.year, qtr=quarter.quarter)
        status, payload = client.get(url)
        if status == 404:
            outcome[str(quarter)] = "missing_404"
            log(f"index {quarter}: MISSING on sec.gov (HTTP 404) -- skipped, not faked")
            continue
        if status != 200:
            outcome[str(quarter)] = f"http_{status}"
            log(f"index {quarter}: HTTP {status} -- skipped")
            continue
        frame = parse_424b4_index(payload)
        del payload
        tmp = target.with_suffix(".parquet.part")
        frame.to_parquet(tmp, index=False, compression="zstd")
        tmp.replace(target)
        outcome[str(quarter)] = "downloaded"
        log(f"index {quarter}: {len(frame):,} 424B4 index rows")
    return outcome


def load_index(quarters: list[Quarter] | None = None) -> pd.DataFrame:
    paths = (
        sorted(INDEX_ROOT.glob("*.parquet"))
        if quarters is None
        else [INDEX_ROOT / f"{q}.parquet" for q in quarters]
    )
    frames = [pd.read_parquet(p) for p in paths if p.exists()]
    if not frames:
        raise RuntimeError(f"no 424B4 index parquet under {INDEX_ROOT}; run --stage index")
    return pd.concat(frames, ignore_index=True)


# --------------------------------------------------------------------------
# local daily-panel helpers (no network)
# --------------------------------------------------------------------------


def load_trading_calendar() -> pd.DatetimeIndex:
    """Every distinct trade_date in ``data/features/daily_broad`` -- used as
    the panel's own trading calendar for the lockup-date roll (never an
    external holiday list, per the brief)."""
    frame = _read_daily_broad(["trade_date"])
    return pd.DatetimeIndex(sorted(frame["trade_date"].unique()))


def load_first_trade_dates() -> pd.DataFrame:
    """Per-symbol first trade_date and first-close, from
    ``data/features/daily_broad`` (chosen over ``data/features/daily`` because
    it has materially broader coverage of thin, newly-listed names -- e.g.
    2024 IPO "OS" (OneStream) is present in ``daily_broad`` with 112 rows and
    absent from ``daily``; verified before writing this script). This is a
    substitution from the literal ``data/features/daily`` path named in the
    task brief, made because ``daily`` demonstrably misses some recent small
    IPOs that ``daily_broad`` has; documented here rather than silently
    switched."""
    frame = _read_daily_broad(["symbol", "trade_date", "close"])
    frame = frame.sort_values(["symbol", "trade_date"])
    first = frame.groupby("symbol", as_index=False).first()
    first = first.rename(columns={"trade_date": "first_trade_date", "close": "first_close"})
    return first


def roll_forward(date: pd.Timestamp, calendar: pd.DatetimeIndex) -> pd.Timestamp:
    """Next trading-calendar date >= ``date``. Raises if past the calendar end
    (caller should treat that as an unbuildable event, not fabricate a date)."""
    pos = calendar.searchsorted(date, side="left")
    if pos >= len(calendar):
        raise ValueError(f"{date} is past the trading calendar's end ({calendar[-1]})")
    return calendar[pos]


# --------------------------------------------------------------------------
# stage: map
# --------------------------------------------------------------------------


def classify_fallback_candidate(symbol: str, first_close: float) -> tuple[bool, str]:
    """``(eligible, reason)`` for a first-trade-date fallback IPO proxy.

    Excludes: (a) SPAC-unit/warrant-style ticker suffixes (weak, documented
    heuristic -- unit tickers commonly render as ``XXXXU``/``XXXX.U`` and
    warrants as ``XXXXW``/``XXXX.WS`` in vendor feeds); (b) sub-$3 first
    close (reverse-merger / shell-company artifacts, not underwritten IPOs).
    Ticker-change and spin-off exclusion is NOT separately modeled here (the
    brief allows documenting the heuristic rather than building full
    corporate-action resolution); the 20-sample hand-check reports the
    resulting error rate honestly.
    """
    symbol = symbol.upper()
    if re.search(r"(\.U|\.WS|\.W|WS)$", symbol) or (
        symbol.endswith(("U", "W")) and len(symbol) <= 5
    ):
        return False, "spac_unit_or_warrant_suffix_heuristic"
    if not np.isfinite(first_close) or first_close < FALLBACK_MIN_FIRST_CLOSE:
        return False, "first_close_below_min"
    return True, "ok"


def stage_map(client: SecClient) -> dict[str, object]:
    index = load_index().dropna(subset=["cik"]).copy()
    tickers = load_company_tickers(client)
    cik_to_symbol = (
        tickers.sort_values("symbol").drop_duplicates(subset=["cik"]).set_index("cik")["symbol"]
    )
    index["candidate_symbol"] = index["cik"].map(cik_to_symbol)
    mapped = index.loc[index["candidate_symbol"].notna()].copy()

    first_trade = load_first_trade_dates()
    mapped = mapped.merge(first_trade, left_on="candidate_symbol", right_on="symbol", how="left")
    mapped["days_filing_to_first_trade"] = (
        mapped["first_trade_date"] - mapped["date_filed"]
    ).dt.days
    mapped["confirmed_ipo"] = mapped["first_trade_date"].notna() & mapped[
        "days_filing_to_first_trade"
    ].between(-CONFIRM_WINDOW_BEFORE_DAYS, CONFIRM_WINDOW_AFTER_DAYS)

    confirmed = (
        mapped.loc[mapped["confirmed_ipo"]]
        .sort_values(["date_filed", "accession"])
        .drop_duplicates(subset=["candidate_symbol"], keep="first")
        .copy()
    )
    confirmed["method"] = "424b4_confirmed"
    confirmed["ipo_date"] = confirmed["date_filed"]

    calendar_start = first_trade["first_trade_date"].min()
    cutoff = calendar_start + pd.Timedelta(days=FALLBACK_MIN_PANEL_AGE_DAYS)
    claimed = set(confirmed["candidate_symbol"])
    fallback_pool = first_trade.loc[
        (~first_trade["symbol"].isin(claimed)) & (first_trade["first_trade_date"] >= cutoff)
    ].copy()
    elig = fallback_pool.apply(
        lambda r: classify_fallback_candidate(r["symbol"], r["first_close"]), axis=1
    )
    fallback_pool["fallback_eligible"] = [e[0] for e in elig]
    fallback_pool["fallback_reason"] = [e[1] for e in elig]
    fallback = fallback_pool.loc[fallback_pool["fallback_eligible"]].copy()
    fallback["method"] = "first_trade_fallback"
    fallback["ipo_date"] = fallback["first_trade_date"]
    fallback["candidate_symbol"] = fallback["symbol"]
    fallback["accession"] = pd.NA
    fallback["file_name"] = pd.NA
    fallback["date_filed"] = pd.NaT
    fallback["days_filing_to_first_trade"] = pd.NA

    keep_cols = [
        "candidate_symbol",
        "ipo_date",
        "method",
        "accession",
        "file_name",
        "date_filed",
        "first_trade_date",
        "first_close",
        "days_filing_to_first_trade",
    ]
    targets = pd.concat([confirmed[keep_cols], fallback[keep_cols]], ignore_index=True).sort_values(
        "ipo_date"
    )
    RAW_ROOT.mkdir(parents=True, exist_ok=True)
    tmp = TARGETS_PATH.with_suffix(".parquet.part")
    targets.to_parquet(tmp, index=False, compression="zstd")
    tmp.replace(TARGETS_PATH)

    summary = {
        "index_424b4_rows": int(len(index)),
        "cik_mapped_rows": int(len(mapped)),
        "confirmed_ipo_candidates": int(len(confirmed)),
        "fallback_pool_before_filter": int(len(fallback_pool)),
        "fallback_candidates": int(len(fallback)),
        "fallback_excluded_by_reason": {
            k: int(v)
            for k, v in fallback_pool.loc[~fallback_pool["fallback_eligible"]]["fallback_reason"]
            .value_counts()
            .items()
        },
        "total_targets": int(len(targets)),
    }
    log(f"map: {json.dumps(summary)}")
    return summary


# --------------------------------------------------------------------------
# stage: fetch (424b4_confirmed candidates only -- lock-up days + despac text)
# --------------------------------------------------------------------------


def parse_lockup_days(text: str) -> int | None:
    m = _LOCKUP_DAYS_RE.search(text) or _LOCKUP_DAYS_RE_ALT.search(text)
    if not m:
        return None
    days = int(m.group(1))
    if 10 <= days <= 400:
        return days
    return None


def despac_text_hit(text: str) -> bool:
    lowered = text.lower()
    return any(kw in lowered for kw in DESPAC_TEXT_KEYWORDS)


def fetched_accessions() -> set[str]:
    if not DOCS_PATH.exists():
        return set()
    return set(pd.read_parquet(DOCS_PATH, columns=["accession"])["accession"].astype(str))


def stage_fetch(client: SecClient, *, max_bytes: int, limit: int | None) -> dict[str, object]:
    if not TARGETS_PATH.exists():
        raise RuntimeError(f"{TARGETS_PATH} missing; run --stage map first")
    targets = pd.read_parquet(TARGETS_PATH)
    confirmed = targets.loc[targets["method"] == "424b4_confirmed"].dropna(subset=["file_name"])
    done = fetched_accessions()
    pending = confirmed.loc[~confirmed["accession"].astype(str).isin(done)].copy()
    if limit is not None:
        pending = pending.head(limit)
    log(
        f"fetch: {len(confirmed)} confirmed targets, "
        f"{len(done)} already fetched, {len(pending)} pending"
    )
    rows: list[dict[str, object]] = []
    ok = 0
    fail = 0
    for row in pending.itertuples(index=False):
        url = ARCHIVE_URL.format(file_name=row.file_name)
        status, payload = client.get(url, max_bytes=max_bytes)
        if status not in {200, 206} or not payload:
            fail += 1
            rows.append(
                {
                    "accession": str(row.accession),
                    "symbol": row.candidate_symbol,
                    "http_status": int(status),
                    "lockup_days_parsed": None,
                    "is_despac_text_hit": False,
                    "body_chars": 0,
                }
            )
            continue
        text = payload.decode("latin-1", errors="replace")
        rows.append(
            {
                "accession": str(row.accession),
                "symbol": row.candidate_symbol,
                "http_status": int(status),
                "lockup_days_parsed": parse_lockup_days(text),
                "is_despac_text_hit": despac_text_hit(text),
                "body_chars": len(text),
            }
        )
        ok += 1
    if rows:
        new_frame = pd.DataFrame(rows)
        if DOCS_PATH.exists():
            prior = pd.read_parquet(DOCS_PATH)
            new_frame = pd.concat([prior, new_frame], ignore_index=True)
        DOCS_ROOT.mkdir(parents=True, exist_ok=True)
        tmp = DOCS_PATH.with_suffix(".parquet.part")
        new_frame.to_parquet(tmp, index=False, compression="zstd")
        tmp.replace(DOCS_PATH)
    summary = {"fetched_ok": ok, "fetched_fail": fail, "total_pending_seen": len(pending)}
    log(f"fetch: {json.dumps(summary)}")
    return summary


# --------------------------------------------------------------------------
# stage: build (final PIT event table)
# --------------------------------------------------------------------------


def build_spac_price_flags(daily: pd.DataFrame, symbols: set[str]) -> dict[str, bool]:
    """Precomputed once (a single groupby over the whole panel) rather than
    re-scanning the ~1.3M-row daily frame per event -- the original
    per-symbol ``daily.loc[daily["symbol"] == symbol]`` scan made this stage
    effectively O(n_events * n_rows) and did not finish in a reasonable time
    on ~4,000 events; this is O(n_rows log n_rows) once."""
    sub = daily.loc[daily["symbol"].isin(symbols)].sort_values(["symbol", "trade_date"])
    flags: dict[str, bool] = {}
    for symbol, group in sub.groupby("symbol", sort=False):
        head = group.head(20)
        if len(head) < 10:
            flags[symbol] = False
            continue
        mean_close = float(head["close"].mean())
        if not (9.5 <= mean_close <= 10.5):
            flags[symbol] = False
            continue
        rets = head["close"].pct_change().dropna()
        flags[symbol] = bool(len(rets) >= 5 and rets.std() < 0.015)
    return flags


#: Non-common-stock security-name keywords (preferred units/shares, debt
#: securities, warrants/rights, tangible equity units). Added after this
#: iteration's 20-sample hand-check found BPYPO ("...6.375% Class A
#: Cumulative Redeemable Perpetual Preferred Units, Series 2") and RZC
#: ("...7.125% Fixed-Rate Reset Subordinated Debentures due 2052") -- both
#: from the ``first_trade_fallback`` method -- misclassified as IPO-lockup
#: events; neither has the VC/employee-lockup dynamics Field & Hanka (2001)
#: describe. Reuses the ``name`` field already cached in
#: ``data/features/universe/_asset_metadata.parquet`` (same file
#: ``open_composer.research.features.asset_metadata`` builds for the
#: ETF/fund exclusion, extended here with a preferred/debt keyword set that
#: file's own ``is_probable_fund_or_etf`` does not cover). This does NOT
#: catch every residual error found in the hand-check (a closed-end fund
#: with a fund-silent legal name, a same-day ticker rename of an
#: already-public company, and one 2021-era first-trade-date anomaly all
#: survive it) -- see the hand-check note in report.md for the honest,
#: undiscounted error rate.
_NON_COMMON_STOCK_NAME_RE = re.compile(
    r"(PREFERRED|DEBENTURE|SUBORDINATED NOTE|SENIOR NOTE|\bNOTES DUE\b|"
    r"TANGIBLE EQUITY UNIT|\bWARRANTS?\b|\bRIGHTS\b|DEPOSITARY SHARES)",
    re.IGNORECASE,
)
ASSET_METADATA_PATH = ROOT / "data" / "features" / "universe" / "_asset_metadata.parquet"


def load_non_common_stock_symbols() -> set[str]:
    if not ASSET_METADATA_PATH.exists():
        return set()
    meta = pd.read_parquet(ASSET_METADATA_PATH, columns=["symbol", "name"])
    hit = meta.loc[meta["name"].fillna("").str.contains(_NON_COMMON_STOCK_NAME_RE)]
    return set(hit["symbol"])


def build_events() -> dict[str, object]:
    targets = pd.read_parquet(TARGETS_PATH)
    docs = (
        pd.read_parquet(DOCS_PATH)
        if DOCS_PATH.exists()
        else pd.DataFrame(
            columns=["accession", "symbol", "lockup_days_parsed", "is_despac_text_hit"]
        )
    )
    targets = targets.merge(
        docs[["accession", "lockup_days_parsed", "is_despac_text_hit"]],
        on="accession",
        how="left",
    )
    calendar = load_trading_calendar()

    daily = _read_daily_broad(["symbol", "trade_date", "close"])
    daily_syms = set(daily["symbol"].unique())
    non_common_stock = load_non_common_stock_symbols()

    prelim = []
    excluded_non_common_stock = 0
    for row in targets.itertuples(index=False):
        symbol = row.candidate_symbol
        ipo_date = row.ipo_date
        if pd.isna(ipo_date) or symbol not in daily_syms:
            continue
        if symbol in non_common_stock:
            excluded_non_common_stock += 1
            continue
        lockup_days = (
            int(row.lockup_days_parsed) if pd.notna(row.lockup_days_parsed) else LOCKUP_DAYS_DEFAULT
        )
        lockup_days_source = "parsed" if pd.notna(row.lockup_days_parsed) else "assumed_180"
        raw_L = pd.Timestamp(ipo_date) + pd.Timedelta(days=lockup_days)
        try:
            L = roll_forward(raw_L, calendar)
        except ValueError:
            continue
        despac_text = bool(row.is_despac_text_hit) if pd.notna(row.is_despac_text_hit) else False
        prelim.append(
            {
                "symbol": symbol,
                "ipo_date": pd.Timestamp(ipo_date),
                "method": row.method,
                "accession": row.accession,
                "lockup_days": lockup_days,
                "lockup_days_source": lockup_days_source,
                "lockup_date_raw": raw_L,
                "lockup_date": L,
                "is_despac_text_hit": despac_text,
            }
        )
    spac_flags = build_spac_price_flags(daily, {e["symbol"] for e in prelim})
    events = []
    for e in prelim:
        despac_price = spac_flags.get(e["symbol"], False)
        e["is_despac_price_heuristic"] = despac_price
        e["is_despac"] = e["is_despac_text_hit"] or despac_price
        events.append(e)
    events_df = pd.DataFrame(events).sort_values(["lockup_date", "symbol"]).reset_index(drop=True)
    ITER_DIR.mkdir(parents=True, exist_ok=True)
    events_df.to_parquet(EVENTS_PATH, index=False)

    rng = np.random.default_rng(20260929)
    n = len(events_df)
    sample_idx = rng.choice(n, size=min(20, n), replace=False)
    sample = events_df.iloc[sorted(sample_idx)][
        ["symbol", "ipo_date", "method", "lockup_date", "lockup_days_source", "is_despac"]
    ].copy()
    sample["ipo_date"] = sample["ipo_date"].astype(str)
    sample["lockup_date"] = sample["lockup_date"].astype(str)
    HANDCHECK_PATH.write_text(json.dumps(sample.to_dict(orient="records"), indent=2, default=str))

    summary = {
        "total_events": int(n),
        "excluded_non_common_stock_name_filter": excluded_non_common_stock,
        "by_method": {k: int(v) for k, v in events_df["method"].value_counts().items()},
        "by_lockup_days_source": {
            k: int(v) for k, v in events_df["lockup_days_source"].value_counts().items()
        },
        "is_despac_count": int(events_df["is_despac"].sum()),
        "handcheck_sample_path": str(HANDCHECK_PATH),
        "events_path": str(EVENTS_PATH),
    }
    log(f"build: {json.dumps(summary)}")
    (ITER_DIR / "build_summary.json").write_text(json.dumps(summary, indent=2))
    return summary


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--stage", required=True, choices=["index", "map", "fetch", "build"])
    p.add_argument("--start", type=parse_quarter, default=parse_quarter(DEFAULT_START_QUARTER))
    p.add_argument("--end", type=parse_quarter, default=parse_quarter(DEFAULT_END_QUARTER))
    p.add_argument("--max-bytes", type=int, default=DEFAULT_MAX_BYTES)
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--min-interval", type=float, default=0.15)
    p.add_argument("--force", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    load_dotenv(dotenv_path=ROOT / ".env")
    RAW_ROOT.mkdir(parents=True, exist_ok=True)
    if args.stage == "build":
        build_events()
        return 0
    client = SecClient(min_interval=args.min_interval)
    try:
        if args.stage == "index":
            end = args.end or quarter_of(pd.Timestamp.today().date())
            outcome = stage_index(client, quarter_range(args.start, end), force=args.force)
            log(f"index summary: {json.dumps(outcome)}")
        elif args.stage == "map":
            stage_map(client)
        else:
            stage_fetch(client, max_bytes=args.max_bytes, limit=args.limit)
    finally:
        client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
