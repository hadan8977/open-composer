"""Point-in-time, as-first-reported fundamentals from SEC XBRL.

Card: ``reports/research/intel/I-20260923-08-free-data-substitutes.md``
sections 4 and 10 (verified live 2026-09-23: the ``companyfacts`` API
records ``filed``/``accn``/``form`` on every fact, and a genuine restatement
-- Apple FY2008 ``Assets`` revised from $39.572B to $36.171B by a 10-K/A
five months later -- is directly observable and recoverable for free).

What this collects
-------------------
Nine ``us-gaap``/``dei`` concepts (diluted EPS with basic as fallback,
revenue, net income, gross profit, operating income, total assets,
stockholders' equity, operating cash flow, shares outstanding) for every
symbol in ``data/features/universe_broad``, plus seven derived signals
(``sue_eps``, ``sue_rev``, ``days_since_report``, ``gross_profitability``,
``asset_growth``, ``accruals``, ``roe``), each set on the first NYSE session
after its filing became public and forward-filled from there.

Source: the bulk ``companyfacts.zip`` (confirmed live 2026-09-23: 20,395
members named ``CIK##########.json``, ~1.4 GB, downloads in ~20s at this
box's bandwidth -- far cheaper than ~9,000 rate-limited per-CIK requests
against the 10 req/s fair-access ceiling for a universe this size).
``--source api`` falls back to the per-CIK ``companyconcept`` API for small
runs or if the bulk file becomes unavailable.

SEC fair access
----------------
``SEC_USER_AGENT`` (contact email) is read from the process environment via
``load_dotenv``, exactly as ``scripts/collect_sec_insider_transactions.py``
and ``scripts/collect_sec_13d_filings.py`` already do; this script never
opens or prints ``.env``. :class:`SecClient` is the same shape as those two
scripts' clients (one connection, serialized requests, minimum inter-request
delay, retry with backoff on 403/429/5xx) with one deliberate difference:
it does **not** hard-code a ``Host`` header. ``collect_sec_insider_transactions
.SecClient`` pins ``Host: www.sec.gov`` because it only ever talks to that
host; this script also talks to ``data.sec.gov`` (the per-CIK API fallback),
and a request to ``data.sec.gov`` sent with a ``Host: www.sec.gov`` header
was verified live this session to fail outright (connection reset) rather
than silently misroute -- so the header is left for httpx to set per-request
from each URL instead of being copied verbatim.

Point-in-time rule
-------------------
A fact becomes usable on the first US equity session *after* its ``filed``
date (``open_composer.market_calendar.next_us_equity_session`` -- a same-day
filing is conservatively treated as known only from the next session, never
the filing session itself). Restatement handling (verified live, see the
intel brief): within a (cik, tag, period_start, period_end) group -- period
*start* is part of the key, not just fiscal year/period, because SEC filers
commonly tag both a single-quarter and a cumulative year-to-date fact with
the same ``end``/``fy``/``fp`` in the same filing (e.g. a Q3 10-Q's 3-month
and 9-month EPS) and the literal "(cik, concept, period end, fiscal period)"
grouping from this build's own brief would silently collide those two
different facts -- the first-filed (by ``filed`` date, then accession) row
is "as originally reported" (``restated=False``); a later row with a
genuinely different value is a restatement (``restated=True``, kept as its
own row); a later row repeating the same value (e.g. as a comparative figure
in the next period's filing) is a duplicate re-affirmation and is dropped.

Both original and restated rows feed the forward-filled daily panel, each
becoming effective at its *own* usable session -- that is the correct
point-in-time reading: the market knows the restated number from the day the
restatement itself is filed, not before. The only simplification against
full generality: a restatement of an older, already-superseded period never
regresses the *current* forward-filled value backward (``_running_latest``'s
period-end guard), and the SUE/TTM helpers below key off first-filed
(``restated=False``) rows only -- see their own docstrings for why.

SEC XBRL quirk this build works around: flow concepts have no discrete "Q4"
fact -- companies report Q1-Q3 in 10-Qs and only the cumulative annual
figure in the 10-K. :func:`derive_q4` synthesizes
``Q4 = FY - (Q1 + Q2 + Q3)`` (the standard practical approximation) for
``eps_diluted`` and ``revenue`` -- the two concepts :func:`sue_series` needs
a complete quarterly ladder for -- flagged ``derived_q4=True`` and dated at
the FY fact's own filing.

Derived signals (formulas, each against its paper)
----------------------------------------------------
``sue_eps`` / ``sue_rev``
    Standardized unexpected earnings, seasonal random walk (Foster, Olsen &
    Shevlin 1984): for quarter *t*, ``SUE_t = D_t / std(D_{t-8}..D_{t-1})``
    where ``D_k = EPS_k - EPS_{k-4}`` (same fiscal quarter a year earlier)
    and the denominator is the sample std (``ddof=1``) of the prior 8
    quarters' *own* year-over-year differences -- excluding ``D_t`` itself,
    per "prior". Needs 12 consecutive fiscal quarters of history (no gaps);
    set once, on the usable session of quarter *t*'s own first-filed report.
    ``sue_rev`` is the identical construction on revenue.
``days_since_report``
    US equity sessions since the most recently usable 10-K/10-K-A/10-Q/
    10-Q-A filing for this issuer (any concept), mirroring ``staleness_days``
    in ``scripts/build_short_interest_features.py``.
``gross_profitability``
    Gross profit / total assets (Novy-Marx 2013). Numerator is the trailing
    annual (latest 10-K) gross profit -- see "Annual vs. trailing four
    quarters" below; denominator is the latest known total assets (any
    period, quarterly updates included).
``asset_growth``
    Year-over-year growth of fiscal-year-end total assets (Cooper, Gulen &
    Schill 2008): ``(Assets_FY - Assets_FY-1) / Assets_FY-1``, matched by
    the ``fp == "FY"`` instant fact's own ``fy`` label (confirmed live this
    session: instant facts carry ``fy``/``fp`` too, not just duration
    facts). Updates once a year, at the 10-K filing.
``accruals``
    (Net income - operating cash flow) / average total assets (Sloan 1996).
    Numerator legs are each concept's trailing annual value; the average
    uses the current total assets and the total assets value from
    approximately 365 days earlier (nearest match within a 60-day tolerance
    on this issuer's own instant-assets timeline); no match within tolerance
    yields ``NaN`` rather than a one-point "average".
``roe``
    Net income (trailing annual) / latest known stockholders' equity.

Annual vs. trailing four quarters (documented simplification)
----------------------------------------------------------------
The task brief allows either "the latest usable annual or trailing-four-
quarter values." ``eps_diluted`` and ``revenue`` get the full quarterly
ladder (:func:`derive_q4` included) because SUE is defined on discrete
quarters. For ``net_income``, ``gross_profit`` and ``operating_cash_flow`` --
inputs to ``gross_profitability``/``accruals``/``roe`` only -- this build
uses the simpler, always-annual reading: the latest 10-K figure, updating
once a year. A quarterly trailing-twelve-month roll-up would update these
three ratios every quarter instead of once a year, but needs its own
Q4-derivation pass for three more concepts; deferred as a scope decision
given the build budget, not a data gap (the FY figure is exact, not a
degraded proxy).

Tickers
-------
``company_tickers.json`` (refetched fresh each run unless cached; see
:func:`load_company_tickers`) is a **current** snapshot: an issuer that
changed ticker or delisted has no historical row, so those names are
unmappable here by construction -- the same caveat
``scripts/collect_sec_13d_filings.py`` already records for the same file.
Tag heterogeneity (e.g. ``NetIncomeLoss`` vs. ``ProfitLoss``) is the
standard, documented SEC XBRL pain point, not a surprise; the fallback
lists below are the "usual fallbacks" the task brief asked for, not an
exhaustive tag-mapping layer.

Output
------
``data/features/sec_fundamentals/facts.parquet``
    Long table: one row per (cik, concept, tag, period_start, period_end,
    filed) after first-filed/restatement/fallback selection -- the audit
    trail behind the daily panel.
``data/features/sec_fundamentals_daily/{year}.parquet``
    Wide table, one row per (symbol, trade_date) that already has a price
    row in ``data/features/daily_broad`` for that year: the 9 raw concepts
    plus the 7 derived signals above, forward-filled from each value's own
    usable session and never backward filled.

Usage::

    ./scripts/run_capped.sh --mem 1200M -- \\
        uv run python scripts/build_sec_xbrl_fundamentals.py --stage all

    # small live smoke test against a handful of companies first:
    ./scripts/run_capped.sh --mem 1200M -- \\
        uv run python scripts/build_sec_xbrl_fundamentals.py --stage all --limit 20
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import zipfile
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import duckdb  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from open_composer.market_calendar import (  # noqa: E402
    next_us_equity_session,
    us_equity_session_dates,
)

RAW_ROOT = ROOT / "data" / "raw" / "sec_xbrl"
TICKERS_PATH = RAW_ROOT / "company_tickers.json"
ZIP_PATH = RAW_ROOT / "companyfacts.zip"

FACTS_ROOT = ROOT / "data" / "features" / "sec_fundamentals"
FACTS_PATH = FACTS_ROOT / "facts.parquet"
DAILY_ROOT = ROOT / "data" / "features" / "sec_fundamentals_daily"
DAILY_BROAD_ROOT = ROOT / "data" / "features" / "daily_broad"
UNIVERSE_BROAD_ROOT = ROOT / "data" / "features" / "universe_broad"

COMPANY_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
COMPANYFACTS_ZIP_URL = "https://www.sec.gov/Archives/edgar/daily-index/xbrl/companyfacts.zip"
COMPANYCONCEPT_URL = (
    "https://data.sec.gov/api/xbrl/companyconcept/CIK{cik:010d}/{taxonomy}/{tag}.json"
)

MIN_REQUEST_INTERVAL_SECONDS = 0.15
HTTP_TIMEOUT_SECONDS = 180
DEFAULT_START_YEAR = 2016
DEFAULT_BATCH_SIZE = 400

#: (taxonomy, tag, unit) candidates in fallback priority order, per concept.
CONCEPTS: dict[str, list[tuple[str, str, str]]] = {
    "eps_diluted": [
        ("us-gaap", "EarningsPerShareDiluted", "USD/shares"),
        ("us-gaap", "EarningsPerShareBasic", "USD/shares"),
    ],
    "revenue": [
        ("us-gaap", "Revenues", "USD"),
        ("us-gaap", "RevenueFromContractWithCustomerExcludingAssessedTax", "USD"),
        ("us-gaap", "SalesRevenueNet", "USD"),
    ],
    "net_income": [
        ("us-gaap", "NetIncomeLoss", "USD"),
        ("us-gaap", "ProfitLoss", "USD"),
    ],
    "gross_profit": [("us-gaap", "GrossProfit", "USD")],
    "operating_income": [("us-gaap", "OperatingIncomeLoss", "USD")],
    "total_assets": [("us-gaap", "Assets", "USD")],
    "stockholders_equity": [
        ("us-gaap", "StockholdersEquity", "USD"),
        (
            "us-gaap",
            "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
            "USD",
        ),
    ],
    "operating_cash_flow": [
        ("us-gaap", "NetCashProvidedByUsedInOperatingActivities", "USD"),
        ("us-gaap", "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations", "USD"),
    ],
    "shares_outstanding": [("dei", "EntityCommonStockSharesOutstanding", "shares")],
}
INSTANT_CONCEPTS = frozenset({"total_assets", "stockholders_equity", "shares_outstanding"})
RAW_COLUMNS = tuple(CONCEPTS)
TRAILING_ANNUAL_CONCEPTS = ("net_income", "gross_profit", "operating_cash_flow")

#: Duration-in-days bands used to classify a duration fact as one quarter,
#: one fiscal year, or something else (half-year/9-month cumulative
#: year-to-date facts, which SEC filers routinely tag alongside the discrete
#: quarter -- see the module docstring's restatement-key note). Instant
#: facts (no ``start``) classify separately as ``"instant"``.
Q_MIN_DAYS, Q_MAX_DAYS = 70, 100
FY_MIN_DAYS, FY_MAX_DAYS = 340, 392

QUARTER_ORDER = {"Q1": 0, "Q2": 1, "Q3": 2, "Q4": 3}
SUE_LOOKBACK_QUARTERS = 8
ACCRUALS_LAG_DAYS = 365
ACCRUALS_LAG_TOLERANCE_DAYS = 60

DAILY_COLUMNS = (
    "symbol",
    "trade_date",
    "cik",
    *RAW_COLUMNS,
    "sue_eps",
    "sue_rev",
    "days_since_report",
    "gross_profitability",
    "asset_growth",
    "accruals",
    "roe",
)


def log(message: str) -> None:
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{stamp}] [sec-xbrl] {message}", flush=True)


# --------------------------------------------------------------------------
# HTTP
# --------------------------------------------------------------------------


class SecClient:
    """Serialized, rate-limited SEC HTTP client.

    Same shape as ``collect_sec_insider_transactions.SecClient`` and
    ``collect_sec_13d_filings.SecClient`` (one connection, one request at a
    time, minimum inter-request delay, retry with backoff on 403/429/5xx).
    ``SEC_USER_AGENT`` is read from the process environment and used only as
    a request header; it is never logged or written to an artifact. Unlike
    the insider script's client, no ``Host`` header is pinned -- see the
    module docstring for why (this client talks to both ``www.sec.gov`` and
    ``data.sec.gov``).
    """

    def __init__(self, *, min_interval: float = MIN_REQUEST_INTERVAL_SECONDS) -> None:
        import os
        import re

        import httpx

        user_agent = os.getenv("SEC_USER_AGENT", "").strip()
        if not user_agent or re.search(r"\S+@\S+\.\S+", user_agent) is None:
            raise RuntimeError(
                "SEC_USER_AGENT with a contact email is required for live SEC fetches; "
                "populate it in .env (loaded via load_dotenv) -- this script never reads .env"
            )
        self._min_interval = min_interval
        self._last_request = 0.0
        self._client = httpx.Client(
            headers={"User-Agent": user_agent, "Accept-Encoding": "gzip, deflate"},
            timeout=HTTP_TIMEOUT_SECONDS,
            follow_redirects=True,
        )

    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_request
        if elapsed < self._min_interval:
            time.sleep(self._min_interval - elapsed)
        self._last_request = time.monotonic()

    def get(self, url: str, *, retries: int = 3) -> tuple[int, bytes]:
        import httpx

        for attempt in range(retries):
            self._throttle()
            try:
                response = self._client.get(url)
            except httpx.HTTPError as exc:
                if attempt == retries - 1:
                    raise
                log(f"  transport error ({type(exc).__name__}), retry {attempt + 1}/{retries}")
                time.sleep(2.0 * (attempt + 1))
                continue
            if response.status_code in {403, 429, 500, 502, 503, 504}:
                if attempt == retries - 1:
                    return response.status_code, response.content
                log(f"  HTTP {response.status_code}, backing off (attempt {attempt + 1})")
                time.sleep(5.0 * (attempt + 1))
                continue
            return response.status_code, response.content
        raise RuntimeError("unreachable")

    def stream_to_file(self, url: str, path: Path, *, chunk_size: int = 1 << 20) -> None:
        """Stream a large response straight to disk -- never buffers the
        whole body in memory, unlike :meth:`get`. Used only for the ~1.4 GB
        ``companyfacts.zip``, which this box's 1.2 GB job memory cap could
        not otherwise survive."""
        self._throttle()
        with self._client.stream("GET", url, timeout=HTTP_TIMEOUT_SECONDS) as response:
            response.raise_for_status()
            with open(path, "wb") as handle:
                for chunk in response.iter_bytes(chunk_size):
                    handle.write(chunk)

    def close(self) -> None:
        self._client.close()


# --------------------------------------------------------------------------
# tickers / universe
# --------------------------------------------------------------------------


def load_company_tickers(client: SecClient | None, *, refresh: bool = False) -> pd.DataFrame:
    """``cik -> ticker`` from SEC's current registrant list.

    This file is a *current* snapshot: an issuer that changed ticker or was
    acquired/delisted has no row here, so those names are unmappable by
    construction -- recorded as a caveat, not patched with a guess. Same
    file and same caveat as ``scripts/collect_sec_13d_filings
    .load_company_tickers``.
    """
    if refresh or not TICKERS_PATH.exists():
        if client is None:
            raise RuntimeError(f"{TICKERS_PATH} missing and no client to fetch it")
        status, payload = client.get(COMPANY_TICKERS_URL)
        if status != 200:
            raise RuntimeError(f"company_tickers.json fetch failed with HTTP {status}")
        TICKERS_PATH.parent.mkdir(parents=True, exist_ok=True)
        TICKERS_PATH.write_bytes(payload)
    raw = json.loads(TICKERS_PATH.read_text())
    rows = [
        (int(item["cik_str"]), str(item["ticker"]).upper(), str(item.get("title", "")))
        for item in raw.values()
        if isinstance(item, dict) and item.get("ticker") and item.get("cik_str") is not None
    ]
    frame = pd.DataFrame(rows, columns=["cik", "symbol", "company_title"])
    return frame.drop_duplicates(subset=["cik"]).reset_index(drop=True)


def load_universe_symbols() -> set[str]:
    """Every distinct symbol ever in the point-in-time broad universe."""
    con = duckdb.connect()
    try:
        got = con.execute(
            f"SELECT DISTINCT symbol FROM read_parquet('{UNIVERSE_BROAD_ROOT}/*.parquet')"
        ).df()
    finally:
        con.close()
    return set(got["symbol"])


def build_cik_symbol_map(client: SecClient | None, *, refresh: bool = False) -> pd.DataFrame:
    """``(cik, symbol, company_title)`` restricted to the broad universe."""
    tickers = load_company_tickers(client, refresh=refresh)
    universe = load_universe_symbols()
    mapped = tickers.loc[tickers["symbol"].isin(universe)].reset_index(drop=True)
    log(
        f"ticker map: {len(mapped):,} of {len(universe):,} universe symbols matched a CIK "
        f"({len(tickers):,} total registrants in company_tickers.json)"
    )
    return mapped


# --------------------------------------------------------------------------
# download
# --------------------------------------------------------------------------


def _zip_is_readable(path: Path) -> bool:
    if not path.exists() or path.stat().st_size < 1_000_000:
        return False
    try:
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
            return len(names) > 100 and names[0].startswith("CIK") and names[0].endswith(".json")
    except zipfile.BadZipFile:
        return False


def download_companyfacts_zip(client: SecClient, *, force: bool = False) -> Path:
    if ZIP_PATH.exists() and not force and _zip_is_readable(ZIP_PATH):
        log(f"companyfacts.zip already present ({ZIP_PATH.stat().st_size / 1e6:.0f} MB)")
        return ZIP_PATH
    ZIP_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = ZIP_PATH.with_suffix(".zip.part")
    log("downloading companyfacts.zip (bulk, ~1.4 GB, streamed to disk)...")
    client.stream_to_file(COMPANYFACTS_ZIP_URL, tmp)
    if not _zip_is_readable(tmp):
        tmp.unlink(missing_ok=True)
        raise RuntimeError("downloaded companyfacts.zip did not pass the readability check")
    tmp.replace(ZIP_PATH)
    log(f"downloaded companyfacts.zip ({ZIP_PATH.stat().st_size / 1e6:.0f} MB)")
    return ZIP_PATH


# --------------------------------------------------------------------------
# fact extraction
# --------------------------------------------------------------------------


def fact_rows_from_payload(cik: int, payload: dict, source_dataset: str) -> list[dict]:
    """Every tracked-concept fact in one company's ``companyfacts`` payload,
    across every fallback tag -- selection between tags happens later
    (:func:`apply_concept_fallback`), so every candidate is kept for now."""
    rows: list[dict] = []
    facts = payload.get("facts") or {}
    for concept, candidates in CONCEPTS.items():
        for priority, (taxonomy, tag, unit) in enumerate(candidates):
            entries = ((facts.get(taxonomy) or {}).get(tag) or {}).get("units", {}).get(unit)
            if not entries:
                continue
            for entry in entries:
                end = entry.get("end")
                val = entry.get("val")
                filed = entry.get("filed")
                accn = entry.get("accn")
                if end is None or val is None or filed is None or accn is None:
                    continue
                rows.append(
                    {
                        "cik": cik,
                        "concept": concept,
                        "taxonomy": taxonomy,
                        "tag": tag,
                        "priority": priority,
                        "unit": unit,
                        "period_start": entry.get("start"),
                        "period_end": end,
                        "fy": entry.get("fy"),
                        "fp": entry.get("fp"),
                        "val": float(val),
                        "accn": str(accn),
                        "form": entry.get("form"),
                        "filed": filed,
                        "source_dataset": source_dataset,
                    }
                )
    return rows


def classify_period(start: pd.Series, end: pd.Series) -> pd.Series:
    """``"instant"`` (no start), ``"Q"``/``"FY"`` (duration within the
    bands above), or ``"YTD_other"`` (a cumulative half-year/9-month fact,
    kept in ``facts.parquet`` for completeness but never used downstream)."""
    days = (end - start).dt.days
    kind = pd.Series("YTD_other", index=end.index, dtype="object")
    kind[start.isna()] = "instant"
    is_duration = start.notna()
    kind[is_duration & days.between(Q_MIN_DAYS, Q_MAX_DAYS)] = "Q"
    kind[is_duration & days.between(FY_MIN_DAYS, FY_MAX_DAYS)] = "FY"
    return kind


def rows_to_frame(rows: list[dict]) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame(
            columns=[
                "cik",
                "concept",
                "taxonomy",
                "tag",
                "priority",
                "unit",
                "period_start",
                "period_end",
                "fy",
                "fp",
                "val",
                "accn",
                "form",
                "filed",
                "source_dataset",
            ]
        )
    frame = pd.DataFrame(rows)
    # Real SEC XBRL data contains outright typos (observed live in this
    # build: a filer's `start` of "0202-02-01", presumably meant "2002-..."),
    # which pandas cannot represent as a nanosecond timestamp and raises on
    # rather than silently skipping. errors="coerce" turns those into NaT
    # instead of crashing the whole batch.
    had_start = frame["period_start"].notna()
    frame["period_start"] = pd.to_datetime(frame["period_start"], format="ISO8601", errors="coerce")
    frame["period_end"] = pd.to_datetime(frame["period_end"], format="ISO8601", errors="coerce")
    frame["filed"] = pd.to_datetime(frame["filed"], format="ISO8601", errors="coerce")
    frame["fy"] = pd.to_numeric(frame["fy"], errors="coerce").astype("Int64")
    frame["fp"] = frame["fp"].astype("string")
    frame["period_kind"] = classify_period(frame["period_start"], frame["period_end"])
    # A `start` value was present in the source but failed to parse: that is
    # a corrupt duration fact, not a true instant one (classify_period alone
    # cannot tell the two apart, since both end up with period_start = NaT).
    # Force it into the excluded YTD_other bucket rather than the instant
    # bucket, where it would wrongly feed total_assets/equity/shares.
    corrupt_start = had_start & frame["period_start"].isna()
    frame.loc[corrupt_start, "period_kind"] = "YTD_other"
    # A fact with no valid period_end or filed date is unusable regardless
    # of concept; drop rather than carry a NaT-keyed row forward.
    frame = frame.loc[frame["period_end"].notna() & frame["filed"].notna()]
    return frame.reset_index(drop=True)


def select_first_filed(frame: pd.DataFrame) -> pd.DataFrame:
    """Point-in-time selection, verified live against ``data.sec.gov``
    (module docstring): the first-filed row per (cik, tag, period_start,
    period_end) is as-originally-reported; a later row with a *different*
    value is a restatement, kept as its own row (``restated=True``); a later
    row repeating a value already seen for that period is a duplicate
    re-affirmation and is dropped.

    Grouped on ``tag`` (the literal reported item) rather than ``concept``
    (our own fallback label) so two different companies' or two different
    tags' history never cross-contaminate each other's restatement detection.
    """
    if frame.empty:
        return frame.assign(restated=pd.Series(dtype="bool"))
    key = ["cik", "taxonomy", "tag", "period_start", "period_end"]
    ordered = frame.sort_values([*key, "filed", "accn"], kind="stable").reset_index(drop=True)
    dedup = ordered.drop_duplicates(subset=[*key, "val"], keep="first").reset_index(drop=True)
    dedup["restated"] = dedup.duplicated(subset=key, keep="first")
    return dedup


def apply_concept_fallback(frame: pd.DataFrame) -> pd.DataFrame:
    """Among the tags that reported the same (cik, concept, period), keep
    only the highest-priority (lowest ``priority`` number) tag's rows."""
    if frame.empty:
        return frame.drop(columns=["priority"], errors="ignore")
    key = ["cik", "concept", "period_start", "period_end"]
    # dropna=False: instant concepts (total_assets, stockholders_equity,
    # shares_outstanding) have period_start = NaT for every row, and
    # pandas groupby's default dropna=True silently excludes NaN/NaT group
    # keys from the result -- which would make every instant-concept row
    # fail the `priority == best` test below and vanish here entirely.
    best = frame.groupby(key, dropna=False)["priority"].transform("min")
    return frame.loc[frame["priority"] == best].drop(columns=["priority"]).reset_index(drop=True)


def attach_usable_session(frame: pd.DataFrame) -> pd.DataFrame:
    """A fact is usable from the first US equity session after ``filed``
    (same-day filings are conservatively pushed to the next session)."""
    if frame.empty:
        return frame.assign(usable_session=pd.Series(dtype="datetime64[ns]"))
    unique_days = pd.Series(frame["filed"].dt.date.unique())
    mapping = {day: next_us_equity_session(day) for day in unique_days}
    frame = frame.copy()
    frame["usable_session"] = pd.to_datetime(frame["filed"].dt.date.map(mapping))
    return frame


def derive_q4(frame: pd.DataFrame) -> pd.DataFrame:
    """Synthesize ``Q4 = FY - (Q1 + Q2 + Q3)`` for ``eps_diluted``/
    ``revenue`` -- see the module docstring's "SEC XBRL quirk" note. Uses
    first-filed (``restated=False``) values of all four addends; the
    synthetic row is dated at the FY fact's own ``filed``/``usable_session``
    (that is the moment Q4 first becomes computable) and flagged
    ``derived_q4=True``.
    """
    base = frame.loc[~frame["restated"]]
    quarters = base.loc[base["period_kind"] == "Q", ["cik", "concept", "fy", "fp", "val"]]
    pivot = quarters.pivot_table(
        index=["cik", "concept", "fy"], columns="fp", values="val", aggfunc="first"
    )
    for column in ("Q1", "Q2", "Q3"):
        if column not in pivot.columns:
            pivot[column] = np.nan
    pivot = pivot[["Q1", "Q2", "Q3"]].dropna().reset_index()

    annual = base.loc[base["period_kind"] == "FY"].copy()
    annual["fy"] = annual["fy"].astype("Int64")
    pivot["fy"] = pivot["fy"].astype("Int64")
    merged = annual.merge(pivot, on=["cik", "concept", "fy"], how="inner")
    if merged.empty:
        return frame.assign(derived_q4=False) if "derived_q4" not in frame.columns else frame

    merged["val"] = merged["val"] - merged["Q1"] - merged["Q2"] - merged["Q3"]
    merged["fp"] = "Q4"
    merged["period_kind"] = "Q"
    merged["restated"] = False
    merged["derived_q4"] = True
    merged = merged.drop(columns=["Q1", "Q2", "Q3"])

    out = frame.copy()
    out["derived_q4"] = False
    return pd.concat([out, merged], ignore_index=True)


def build_facts_batch(rows: list[dict]) -> pd.DataFrame:
    """The full cleaning pipeline for one batch of companies' raw rows:
    classify -> first-filed/restatement -> concept fallback -> usable
    session -> Q4 derivation. Batches are whole companies (never split), so
    every step here is correct within a batch despite not seeing the other
    batches."""
    frame = rows_to_frame(rows)
    if frame.empty:
        return frame
    frame = select_first_filed(frame)
    frame = apply_concept_fallback(frame)
    frame = attach_usable_session(frame)
    frame = derive_q4(frame.loc[frame["concept"].isin(("eps_diluted", "revenue"))]).pipe(
        lambda derived: pd.concat(
            [
                frame.loc[~frame["concept"].isin(("eps_diluted", "revenue"))].assign(
                    derived_q4=False
                ),
                derived,
            ],
            ignore_index=True,
        )
    )
    return frame.sort_values(["cik", "concept", "period_end", "filed"], ignore_index=True)


# --------------------------------------------------------------------------
# zip / API iteration
# --------------------------------------------------------------------------


def iter_companyfacts_bulk(zip_path: Path, ciks: list[int]):
    """Yield ``(cik, payload)`` for each requested CIK found in the bulk
    zip, opening one member at a time (never the whole archive in memory).
    A CIK absent from the zip is logged and skipped, never faked."""
    with zipfile.ZipFile(zip_path) as archive:
        names = set(archive.namelist())
        for cik in ciks:
            member = f"CIK{cik:010d}.json"
            if member not in names:
                log(f"  cik {cik}: not in companyfacts.zip -- skipped")
                continue
            with archive.open(member) as handle:
                try:
                    payload = json.load(handle)
                except json.JSONDecodeError as exc:
                    log(f"  cik {cik}: bad JSON in {member} ({exc}) -- skipped")
                    continue
            yield cik, payload


def iter_companyfacts_api(client: SecClient, ciks: list[int]):
    """Per-CIK ``companyfacts`` API fallback, rate-limited under SEC's fair
    access ceiling via :class:`SecClient`."""
    for cik in ciks:
        url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"
        status, payload_bytes = client.get(url)
        if status == 404:
            log(f"  cik {cik}: no companyfacts (HTTP 404) -- skipped")
            continue
        if status != 200:
            log(f"  cik {cik}: HTTP {status} -- skipped")
            continue
        try:
            yield cik, json.loads(payload_bytes)
        except json.JSONDecodeError as exc:
            log(f"  cik {cik}: bad JSON ({exc}) -- skipped")


# --------------------------------------------------------------------------
# per-company derived signal timelines
# --------------------------------------------------------------------------


def _running_latest(
    events: list[tuple[pd.Timestamp, pd.Timestamp, float]],
) -> list[tuple[pd.Timestamp, float]]:
    """``events``: unsorted ``(usable_session, period_end, val)``. Returns
    ``(usable_session, val)`` pairs in disclosure order, keeping the value
    whose *period* is the most recent seen so far -- a late-filed
    restatement of an older, already-superseded period does not regress the
    running "current value" backward; a restatement of the still-current
    period does update it (both are legitimate new public information, just
    about different periods)."""
    ordered = sorted(events, key=lambda item: (item[0], item[1]))
    out: list[tuple[pd.Timestamp, float]] = []
    best_period_end: pd.Timestamp | None = None
    for usable_session, period_end, val in ordered:
        if best_period_end is None or period_end >= best_period_end:
            best_period_end = period_end
            out.append((usable_session, val))
    return out


def _events_for(frame: pd.DataFrame, concept: str, kinds: tuple[str, ...]) -> list[tuple]:
    sub = frame[
        (frame["concept"] == concept) & (~frame["restated"]) & frame["period_kind"].isin(kinds)
    ]
    return list(zip(sub["usable_session"], sub["period_end"], sub["val"], strict=True))


def _quarterly_dict(
    frame: pd.DataFrame, concept: str
) -> dict[int, tuple[pd.Timestamp, pd.Timestamp, float]]:
    """``qidx -> (usable_session, period_end, val)`` for one concept's
    discrete-quarter (first-filed, Q1-Q4 including derived Q4) history,
    ``qidx = fy * 4 + {Q1:0,Q2:1,Q3:2,Q4:3}`` so "same quarter a year
    earlier" is ``qidx - 4``."""
    sub = frame[
        (frame["concept"] == concept)
        & (~frame["restated"])
        & (frame["period_kind"] == "Q")
        & frame["fy"].notna()
        & frame["fp"].isin(("Q1", "Q2", "Q3", "Q4"))
    ].sort_values("filed")
    out: dict[int, tuple[pd.Timestamp, pd.Timestamp, float]] = {}
    for row in sub.itertuples():
        qidx = int(row.fy) * 4 + QUARTER_ORDER[row.fp]
        out.setdefault(qidx, (row.usable_session, row.period_end, row.val))
    return out


def sue_series(
    quarterly: dict[int, tuple[pd.Timestamp, pd.Timestamp, float]],
) -> list[tuple[pd.Timestamp, float]]:
    """Foster-Olsen-Shevlin (1984) seasonal-random-walk SUE -- see the
    module docstring for the exact formula. Requires 8 *consecutive* prior
    year-over-year differences (no gaps); a company with a gap simply has no
    SUE value until 8 clean quarters re-accumulate."""
    out: list[tuple[pd.Timestamp, float]] = []
    for t in sorted(quarterly):
        if (t - 4) not in quarterly:
            continue
        diffs = []
        gap = False
        for k in range(t - SUE_LOOKBACK_QUARTERS, t):
            if k not in quarterly or (k - 4) not in quarterly:
                gap = True
                break
            diffs.append(quarterly[k][2] - quarterly[k - 4][2])
        if gap or len(diffs) < SUE_LOOKBACK_QUARTERS:
            continue
        std = float(np.std(diffs, ddof=1))
        if not std > 0:
            continue
        d_t = quarterly[t][2] - quarterly[t - 4][2]
        out.append((quarterly[t][0], d_t / std))
    return out


def _ttm_events(quarterly: dict[int, tuple[pd.Timestamp, pd.Timestamp, float]]) -> list[tuple]:
    out = []
    for t in sorted(quarterly):
        window = (t, t - 1, t - 2, t - 3)
        if not all(k in quarterly for k in window):
            continue
        total = sum(quarterly[k][2] for k in window)
        out.append((quarterly[t][0], quarterly[t][1], float(total)))
    return out


def asset_growth_events(frame: pd.DataFrame) -> list[tuple[pd.Timestamp, float]]:
    """Cooper-Gulen-Schill (2008) annual total-assets growth: matched by the
    fiscal-year-end (``fp == "FY"``) instant ``total_assets`` fact's own
    ``fy`` label against ``fy - 1``'s same fact."""
    sub = frame[
        (frame["concept"] == "total_assets")
        & (~frame["restated"])
        & (frame["fp"] == "FY")
        & frame["fy"].notna()
    ].sort_values("filed")
    by_fy: dict[int, tuple[pd.Timestamp, float]] = {}
    for row in sub.itertuples():
        by_fy.setdefault(int(row.fy), (row.usable_session, row.val))
    out = []
    for fy in sorted(by_fy):
        prior = by_fy.get(fy - 1)
        if prior is None or not prior[1]:
            continue
        usable_session, val = by_fy[fy]
        out.append((usable_session, (val - prior[1]) / prior[1]))
    return out


def _lagged_average(dates: np.ndarray, values: np.ndarray) -> np.ndarray:
    """``(values[i] + values as of ~365 days before dates[i]) / 2``, ``NaN``
    when no prior value falls within a 60-day tolerance of the one-year mark
    (Sloan 1996's "average total assets", approximated on an irregular
    filing-event timeline rather than a fixed annual grid)."""
    target = dates - np.timedelta64(ACCRUALS_LAG_DAYS, "D")
    pos = np.searchsorted(dates, target, side="right") - 1
    lagged = np.full(len(dates), np.nan)
    valid = pos >= 0
    idx = pos[valid]
    # Gap between the *found* lagged point's own date and the one-year-ago
    # target -- not the current row's date, which is always exactly
    # ACCRUALS_LAG_DAYS from its own target by construction and would make
    # this tolerance check vacuous.
    gap_days = np.abs((dates[idx] - target[valid]).astype("timedelta64[D]").astype(np.float64))
    close_enough = gap_days <= ACCRUALS_LAG_TOLERANCE_DAYS
    lagged[valid] = np.where(close_enough, values[idx], np.nan)
    return (values + lagged) / 2.0


def compute_cik_table(cik: int, frame: pd.DataFrame) -> pd.DataFrame:
    """One row per distinct usable session this issuer's known state
    changed, every tracked column carrying the latest known value as of
    that session (forward-filled *within this compact table*) -- ready to
    be asof-joined onto the daily session grid, the same shape
    ``scripts/build_short_interest_features.py`` uses for its own
    ``records`` table."""
    streams: dict[str, list[tuple[pd.Timestamp, float]]] = {}

    for concept in RAW_COLUMNS:
        kinds = ("instant",) if concept in INSTANT_CONCEPTS else ("Q", "FY")
        streams[concept] = _running_latest(_events_for(frame, concept, kinds))

    eps_q = _quarterly_dict(frame, "eps_diluted")
    rev_q = _quarterly_dict(frame, "revenue")
    streams["sue_eps"] = sue_series(eps_q)
    streams["sue_rev"] = sue_series(rev_q)

    for concept in TRAILING_ANNUAL_CONCEPTS:
        streams[f"{concept}_trailing"] = _running_latest(_events_for(frame, concept, ("FY",)))

    streams["asset_growth"] = asset_growth_events(frame)

    reports = frame[
        (~frame["restated"]) & frame["form"].fillna("").str.startswith(("10-K", "10-Q"))
    ]
    report_sessions = sorted(set(reports["usable_session"]))
    streams["_report"] = [(session, 1.0) for session in report_sessions]

    all_sessions = sorted({session for stream in streams.values() for session, _ in stream})
    if not all_sessions:
        return pd.DataFrame()

    wide = pd.DataFrame(index=pd.DatetimeIndex(all_sessions, name="usable_session"))
    for name, stream in streams.items():
        if not stream:
            continue
        wide[name] = pd.Series(dict(stream))
    wide = wide.sort_index()

    ffill_columns = [c for c in wide.columns if c != "_report"]
    wide[ffill_columns] = wide[ffill_columns].ffill()

    if "_report" in wide.columns:
        marker = pd.Series(wide.index.to_series().where(wide["_report"].notna()), index=wide.index)
        wide["last_report_session"] = marker.ffill()
        wide = wide.drop(columns=["_report"])
    else:
        wide["last_report_session"] = pd.NaT

    def _col(name: str) -> pd.Series:
        return wide[name] if name in wide.columns else pd.Series(np.nan, index=wide.index)

    total_assets = _col("total_assets")
    wide["gross_profitability"] = _col("gross_profit_trailing") / total_assets.where(
        total_assets != 0
    )
    equity = _col("stockholders_equity")
    wide["roe"] = _col("net_income_trailing") / equity.where(equity != 0)
    avg_assets = _lagged_average(wide.index.values, total_assets.to_numpy(dtype="float64"))
    with np.errstate(invalid="ignore", divide="ignore"):
        wide["accruals"] = (
            _col("net_income_trailing") - _col("operating_cash_flow_trailing")
        ) / avg_assets

    for column in ("gross_profit_trailing", "net_income_trailing", "operating_cash_flow_trailing"):
        if column in wide.columns:
            wide = wide.drop(columns=[column])
    for column in RAW_COLUMNS + (
        "sue_eps",
        "sue_rev",
        "asset_growth",
        "gross_profitability",
        "roe",
        "accruals",
    ):
        if column not in wide.columns:
            wide[column] = np.nan

    wide["cik"] = cik
    return wide.reset_index()


# --------------------------------------------------------------------------
# facts stage orchestration
# --------------------------------------------------------------------------


def run_facts_stage(
    *, source: str, limit: int | None, batch_size: int, force: bool
) -> tuple[pd.DataFrame, dict[int, pd.DataFrame]]:
    """Extract, clean and derive-signal every mapped CIK, batched so the
    ~1.4 GB zip is never more than one member in memory at a time and the
    cleaning pipeline only ever holds one batch's raw rows.

    Returns the concatenated cleaned ``facts`` long table (written to
    ``facts.parquet`` by the caller) and ``{cik: compact_state_table}`` for
    the daily stage.
    """
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
    client = SecClient() if source == "api" or force or not TICKERS_PATH.exists() else None
    mapping = build_cik_symbol_map(client)
    ciks = sorted(mapping["cik"].unique().tolist())
    if limit is not None:
        ciks = ciks[:limit]
    log(f"facts stage: {len(ciks):,} CIKs to fetch via {source}")

    if source == "bulk":
        zip_client = client or SecClient()
        zip_path = download_companyfacts_zip(zip_client, force=force)
        if client is None:
            zip_client.close()
        source_iter = iter_companyfacts_bulk(zip_path, ciks)
        source_dataset = "companyfacts_bulk"
    elif source == "api":
        source_iter = iter_companyfacts_api(client, ciks)
        source_dataset = "companyfacts_api"
    else:
        raise ValueError(f"unknown source {source!r}")

    facts_batches: list[pd.DataFrame] = []
    cik_tables: dict[int, pd.DataFrame] = {}
    batch_rows: list[dict] = []
    batch_ciks: list[int] = []
    seen = 0
    t0 = time.monotonic()

    def _flush() -> None:
        if not batch_rows:
            return
        cleaned = build_facts_batch(batch_rows)
        facts_batches.append(cleaned)
        if not cleaned.empty:
            for cik, group in cleaned.groupby("cik"):
                table = compute_cik_table(int(cik), group)
                if not table.empty:
                    cik_tables[int(cik)] = table

    for cik, payload in source_iter:
        batch_rows.extend(fact_rows_from_payload(cik, payload, source_dataset))
        batch_ciks.append(cik)
        seen += 1
        if len(batch_ciks) >= batch_size:
            _flush()
            log(
                f"  {seen:,}/{len(ciks):,} companies processed "
                f"({time.monotonic() - t0:.0f}s elapsed)"
            )
            batch_rows, batch_ciks = [], []
    _flush()
    log(f"facts stage done: {seen:,} companies, {len(cik_tables):,} with usable state")

    facts = pd.concat(facts_batches, ignore_index=True) if facts_batches else rows_to_frame([])
    return facts, cik_tables


def write_facts(facts: pd.DataFrame) -> Path:
    FACTS_ROOT.mkdir(parents=True, exist_ok=True)
    facts.to_parquet(FACTS_PATH, index=False)
    log(f"wrote {FACTS_PATH.relative_to(ROOT)} ({len(facts):,} rows)")
    return FACTS_PATH


# --------------------------------------------------------------------------
# daily stage
# --------------------------------------------------------------------------


def build_all_events(
    cik_tables: dict[int, pd.DataFrame], session_pos: dict[pd.Timestamp, int]
) -> pd.DataFrame:
    if not cik_tables:
        return pd.DataFrame(columns=[*DAILY_COLUMNS[2:], "event_idx"])
    frame = pd.concat(cik_tables.values(), ignore_index=True)
    frame["event_idx"] = frame["usable_session"].map(session_pos)
    frame = frame.dropna(subset=["event_idx"]).copy()
    frame["event_idx"] = frame["event_idx"].astype(np.int64)
    frame["last_report_idx"] = frame["last_report_session"].map(session_pos)
    return frame.drop(columns=["usable_session", "last_report_session"])


def build_daily_year(
    year: int,
    events: pd.DataFrame,
    symbol_to_cik: dict[str, int],
    session_pos: dict[pd.Timestamp, int],
) -> pd.DataFrame:
    path = DAILY_BROAD_ROOT / f"{year}.parquet"
    if not path.exists():
        return pd.DataFrame()
    price = pd.read_parquet(path, columns=["symbol", "trade_date"])
    price = price.loc[price["symbol"].isin(symbol_to_cik)].copy()
    if price.empty or events.empty:
        return pd.DataFrame()
    price["cik"] = price["symbol"].map(symbol_to_cik)
    price["session_idx"] = price["trade_date"].map(session_pos)
    price = price.dropna(subset=["session_idx"])
    price["session_idx"] = price["session_idx"].astype(np.int64)
    price = price.sort_values(["session_idx", "cik"], ignore_index=True)

    relevant = events.loc[events["cik"].isin(set(price["cik"]))].sort_values(
        ["event_idx", "cik"], ignore_index=True
    )
    if relevant.empty:
        return pd.DataFrame()

    merged = pd.merge_asof(
        price,
        relevant,
        left_on="session_idx",
        right_on="event_idx",
        by="cik",
        direction="backward",
    )
    merged["days_since_report"] = (merged["session_idx"] - merged["last_report_idx"]).astype(
        "float64"
    )
    for column in DAILY_COLUMNS:
        if column not in merged.columns:
            merged[column] = np.nan
    return merged[list(DAILY_COLUMNS)].sort_values(["trade_date", "symbol"], ignore_index=True)


def run_daily_stage(start_year: int, end_year: int, *, force: bool) -> dict[int, dict]:
    if not FACTS_PATH.exists():
        raise SystemExit(f"no {FACTS_PATH}; run --stage facts first")
    facts = pd.read_parquet(FACTS_PATH)
    # client=None: the tickers stage (or an earlier "facts"/"all" run) must
    # already have cached company_tickers.json; this stage never fetches.
    mapping = build_cik_symbol_map(None)
    symbol_to_cik = dict(zip(mapping["symbol"], mapping["cik"], strict=True))

    last_date = min(date(end_year, 12, 31), date.today())
    sessions = pd.DatetimeIndex(
        [pd.Timestamp(day) for day in us_equity_session_dates(date(2000, 1, 1), last_date)]
    )
    session_pos = {ts: i for i, ts in enumerate(sessions)}
    span = f"{sessions[0].date()}..{sessions[-1].date()}"
    log(f"session calendar: {span} ({len(sessions):,} sessions)")

    cik_tables: dict[int, pd.DataFrame] = {}
    for cik, group in facts.groupby("cik"):
        table = compute_cik_table(int(cik), group)
        if not table.empty:
            cik_tables[int(cik)] = table
    events = build_all_events(cik_tables, session_pos)
    log(f"daily stage: {len(events):,} state-change events across {len(cik_tables):,} issuers")

    DAILY_ROOT.mkdir(parents=True, exist_ok=True)
    coverage: dict[int, dict] = {}
    for year in range(start_year, end_year + 1):
        out_path = DAILY_ROOT / f"{year}.parquet"
        if out_path.exists() and not force:
            existing = pd.read_parquet(
                out_path,
                columns=["symbol"]
                + [c for c in DAILY_COLUMNS if c not in ("symbol", "trade_date", "cik")],
            )
            coverage[year] = _year_coverage(existing)
            n_data = coverage[year]["symbols_with_data"]
            log(f"  {year}: already present, {n_data:,} symbols with data -- skipped")
            continue
        frame = build_daily_year(year, events, symbol_to_cik, session_pos)
        if frame.empty:
            log(f"  {year}: no price rows for mapped symbols -- skipped")
            continue
        frame.to_parquet(out_path, index=False)
        coverage[year] = _year_coverage(frame)
        log(
            f"  {year}: wrote {out_path.relative_to(ROOT)} "
            f"({len(frame):,} rows, {coverage[year]['symbols_with_data']:,} symbols with data)"
        )
    return coverage


def _year_coverage(frame: pd.DataFrame) -> dict:
    value_columns = [c for c in RAW_COLUMNS if c in frame.columns]
    has_data = (
        frame[value_columns].notna().any(axis=1)
        if value_columns
        else pd.Series(False, index=frame.index)
    )
    return {
        "rows": int(len(frame)),
        "symbols_total": int(frame["symbol"].nunique()),
        "symbols_with_data": int(frame.loc[has_data, "symbol"].nunique()) if has_data.any() else 0,
    }


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--stage",
        choices=("tickers", "download", "facts", "daily", "report", "all"),
        default="all",
    )
    parser.add_argument("--source", choices=("bulk", "api"), default="bulk")
    parser.add_argument("--start-year", type=int, default=DEFAULT_START_YEAR)
    parser.add_argument("--end-year", type=int, default=date.today().year)
    parser.add_argument("--limit", type=int, default=None, help="cap CIKs processed (smoke tests)")
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    parser.add_argument("--force", action="store_true")
    return parser


def print_coverage_report(coverage: dict[int, dict]) -> None:
    print("\n[sec-xbrl] coverage by year:")
    for year in sorted(coverage):
        row = coverage[year]
        print(
            f"  {year}: {row['symbols_with_data']:,}/{row['symbols_total']:,} symbols with "
            f">=1 fundamental value, {row['rows']:,} rows"
        )


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.stage in ("tickers", "all"):
        from dotenv import load_dotenv

        load_dotenv(ROOT / ".env")
        client = SecClient()
        try:
            build_cik_symbol_map(client, refresh=True)
        finally:
            client.close()
        if args.stage == "tickers":
            return 0

    if args.stage in ("download", "all") and args.source == "bulk":
        from dotenv import load_dotenv

        load_dotenv(ROOT / ".env")
        client = SecClient()
        try:
            download_companyfacts_zip(client, force=args.force)
        finally:
            client.close()
        if args.stage == "download":
            return 0

    if args.stage in ("facts", "all"):
        if args.stage == "facts" or not FACTS_PATH.exists() or args.force:
            facts, cik_tables = run_facts_stage(
                source=args.source, limit=args.limit, batch_size=args.batch_size, force=args.force
            )
            write_facts(facts)
        if args.stage == "facts":
            return 0

    if args.stage in ("daily", "all"):
        coverage = run_daily_stage(args.start_year, args.end_year, force=args.force)
        print_coverage_report(coverage)
        return 0

    if args.stage == "report":
        coverage = {}
        for path in sorted(DAILY_ROOT.glob("*.parquet")):
            year = int(path.stem)
            frame = pd.read_parquet(path)
            coverage[year] = _year_coverage(frame)
        print_coverage_report(coverage)
        return 0

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
