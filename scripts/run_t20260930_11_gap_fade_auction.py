# ruff: noqa: E501
"""T-20260930-11 (corridor C1): official auction prices vs daily-bar open/close for
the T-20260929-32 cross-sectional gap-fade picks.

Design is frozen in ``reports/research/iterations/t20260930_11_gap_fade_auction/
hypotheses.md``; this script only executes it.

Sub-commands (run in this order):

* ``picks``   rebuild the daily-bar picks (selection rule, price hygiene and split-like
  trigger filter imported from ``run_t20260929_32_gap_fade_ls``), E_bar by tier and leg,
  the stress-window E_bar (daily bars only) and the stratified 400-row sample.
  Memory: the raw long parquet is processed in symbol chunks (per-symbol hygiene and
  per-symbol features are chunk-invariant; the cross-sectional top-10 is merged exactly
  from per-chunk top-10s), so it fits ``run_capped.sh --mem 1.2G``.
* ``check5``  fetch the full frozen windows for 5 sample rows for a hand check of the
  condition codes (writes cache/check5_*.json; the human-readable
  ``condition-code-check.md`` is written by hand from it).
* ``fetch``   fetch official prices for all sample rows, resumable (jsonl cache).
* ``analyze`` paired difference Delta, bootstrap, E_off, verdict -> results.json.

Frozen interpretation choices (set before any official price was fetched):

* T2+T3 pooling: per leg, tiers are weighted by their number of population pick rows in
  the benchmark window (the E_bar row counts); the two legs get equal weight.  The same
  pooling with sample-row weights is reported as a reference only.
* Official open = trade whose condition list contains ``Q``, preferring the listing
  exchange (tape A -> N, tape B -> P/A, tape C -> Q); otherwise the listing-exchange
  ``O`` print.  Official close = ``M`` (listing exchange first), otherwise the
  listing-exchange ``6`` print.  Rows with neither are ``missing``.
* Efficiency only: the closing window is requested from 16:00:00 ET (an ``M`` or ``6``
  print cannot precede the close) and paging stops once the listing-exchange official
  print is found and time has passed a short margin; the opening window starts at the
  frozen 09:29:00 and stops early only after a listing-exchange ``Q`` was seen past 09:30:30.
  ``check5`` uses the full frozen windows.
* The local daily panel is split/dividend adjusted, the SIP trades are not.  Delta (total)
  = r_off - r_bar is scale free; the open/close parts use the unadjusted Alpaca daily bar
  (``rawbar`` rows, GET /v2/stocks/bars adjustment=raw) so they share the trades' price basis.
* A row whose official open or close differs from the raw daily-bar price by more than 30%
  is a data mismatch (scale or bad print).  It is counted in the missing rate and left
  out of the primary Delta statistics; statistics including such rows are reported too.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import time
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

ITERATION_ID = "t20260930_11_gap_fade_auction"
OUT_DIR = ROOT / "reports" / "research" / "iterations" / ITERATION_ID
CACHE_DIR = OUT_DIR / "cache"
SAMPLE_PATH = OUT_DIR / "sample.csv"
RESULTS_PATH = OUT_DIR / "results.json"
PICKS_PATH = CACHE_DIR / "picks.parquet"
OFFICIAL_PATH = CACHE_DIR / "official_prices.jsonl"
WIDE_PATH = (
    ROOT
    / "reports"
    / "research"
    / "iterations"
    / "t20260929_32_gap_fade_ls"
    / "cache"
    / "wide_matrices.parquet"
)

SEED = 20260930
BENCH_START = "2024-01-08"
STRESS_WINDOW = ("2016-05-02", "2023-08-31")
K_LEG = 10
DTC_TOP_DECILE = 0.90
ADV_MIN_SHORT = 5e6
TIER_EDGES = {"T1": (5e6, 20e6), "T2": (20e6, 100e6), "T3": (100e6, float("inf"))}
TIER_SAMPLE = {"T1": 80, "T2": 160, "T3": 160}
THRESHOLD_BP = 8.0
MISSING_LIMIT = 0.20
MISMATCH_LIMIT = 0.30
BOOTSTRAP_DRAWS = 2000
CHUNK_SYMBOLS = 700

NY = ZoneInfo("America/New_York")
DATA_URL = "https://data.alpaca.markets/v2/stocks/{symbol}/trades"
BARS_URL = "https://data.alpaca.markets/v2/stocks/bars"
MIN_INTERVAL_S = 1.0 / 3.0
PAGE_LIMIT = 10000
MAX_PAGES = 40
KEEP_CONDS = {"Q", "O", "M", "6", "5", "9", "X"}
LISTING_BY_TAPE = {"A": ("N",), "B": ("P", "A"), "C": ("Q",)}


def _log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


# --------------------------------------------------------------------------
# pure helpers (unit-tested)
# --------------------------------------------------------------------------


def direction(leg: str) -> int:
    """+1 for the long leg, -1 for the short leg."""
    if leg == "long":
        return 1
    if leg == "short":
        return -1
    raise ValueError(f"unknown leg {leg!r}")


def tier_of(dv21: float) -> str | None:
    """T1 $5-20M, T2 $20-100M, T3 >$100M; None below $5M (long-leg only)."""
    for name, (lo, hi) in TIER_EDGES.items():
        if lo <= dv21 < hi:
            return name
    return None


def delta_components(
    d: int, o_bar: float, c_bar: float, o_off: float, c_off: float
) -> dict[str, float]:
    """Paired difference r_off - r_bar and its open/close parts, all in decimal returns.

    r_bar = d*(C_bar/O_bar - 1); r_off = d*(C_off/O_off - 1); the open part
    d*(O_bar/O_off - 1) and close part d*(C_off/C_bar - 1) are both relative to the
    daily-bar prices and add up to delta to first order.
    """
    r_bar = d * (c_bar / o_bar - 1.0)
    r_off = d * (c_off / o_off - 1.0)
    return {
        "r_bar": r_bar,
        "r_off": r_off,
        "delta": r_off - r_bar,
        "delta_open": d * (o_bar / o_off - 1.0),
        "delta_close": d * (c_off / c_bar - 1.0),
    }


def _pick_official(
    trades: list[dict[str, Any]],
    primary: str,
    fallback: str,
    listing: tuple[str, ...],
) -> dict[str, Any] | None:
    """Official print: primary condition (listing exchange first), else listing fallback."""

    def has(t: dict[str, Any], code: str) -> bool:
        return code in (t.get("c") or [])

    prim = [t for t in trades if has(t, primary)]
    prim_listing = [t for t in prim if t.get("x") in listing]
    if prim_listing:
        best = sorted(prim_listing, key=lambda t: (t["t"], -float(t.get("s") or 0)))[0]
        return {**best, "source": f"{primary}_listing", "n_primary": len(prim)}
    if prim:
        best = sorted(prim, key=lambda t: (-float(t.get("s") or 0), t["t"]))[0]
        return {**best, "source": f"{primary}_other", "n_primary": len(prim)}
    fb = [t for t in trades if has(t, fallback) and t.get("x") in listing]
    if fb:
        best = sorted(fb, key=lambda t: (t["t"], -float(t.get("s") or 0)))[0]
        return {**best, "source": f"{fallback}_listing", "n_primary": 0}
    return None


def official_open(trades: list[dict[str, Any]], tape: str) -> dict[str, Any] | None:
    """Condition Q (listing exchange first), else the listing-exchange O print."""
    return _pick_official(trades, "Q", "O", LISTING_BY_TAPE.get(tape, ()))


def official_close(trades: list[dict[str, Any]], tape: str) -> dict[str, Any] | None:
    """Condition M (listing exchange first), else the listing-exchange 6 print."""
    return _pick_official(trades, "M", "6", LISTING_BY_TAPE.get(tape, ()))


def stratified_sample(picks: pd.DataFrame, seed: int = SEED) -> pd.DataFrame:
    """Seeded stratified sample: tier x leg cells, dates uniform, one row per date.

    ``picks`` needs date, symbol, leg, tier.  Cells are visited in a fixed order; a
    cell with fewer rows than requested is taken whole; if it has fewer dates than
    requested the remainder is filled from unused rows.
    """
    rng = np.random.default_rng(seed)
    frames = []
    for tier, n_tier in TIER_SAMPLE.items():
        for leg in ("long", "short"):
            n = n_tier // 2
            cell = picks[(picks["tier"] == tier) & (picks["leg"] == leg)].sort_values(
                ["date", "symbol"], kind="stable"
            )
            if len(cell) <= n:
                frames.append(cell)
                continue
            dates = np.array(sorted(cell["date"].unique()))
            k = min(n, len(dates))
            chosen = rng.choice(dates, size=k, replace=False)
            take = []
            for dte in sorted(chosen):
                rows = np.flatnonzero((cell["date"] == dte).to_numpy())
                take.append(int(rows[rng.integers(len(rows))]))
            if k < n:
                rest = np.setdiff1d(np.arange(len(cell)), np.array(take))
                take.extend(rng.choice(rest, size=n - k, replace=False).tolist())
            frames.append(cell.iloc[sorted(take)])
    out = pd.concat(frames, ignore_index=True)
    out["sample_id"] = out["symbol"] + "|" + pd.to_datetime(out["date"]).dt.strftime("%Y-%m-%d")
    out["sample_id"] = out["sample_id"] + "|" + out["leg"]
    return out


def pooled_e_off(
    cells: dict[tuple[str, str], tuple[float, float, float]],
) -> float:
    """cells[(tier, leg)] = (weight, E_bar_bp, mean_delta_bp) for tiers T2 and T3.

    Per leg: weighted mean of E_bar+mean_delta with the tier weights; legs equal weight.
    """
    legs = []
    for leg in ("long", "short"):
        num = den = 0.0
        for tier in ("T2", "T3"):
            w, e_bar, dlt = cells[(tier, leg)]
            num += w * (e_bar + dlt)
            den += w
        legs.append(num / den)
    return float(np.mean(legs))


# --------------------------------------------------------------------------
# picks
# --------------------------------------------------------------------------


def _chunk_picks(
    chunk: list[str],
    dates_index: pd.DatetimeIndex,
    dtc: pd.DataFrame,
    parent: Any,
    ph: Any,
) -> pd.DataFrame:
    import pyarrow.parquet as pq

    tbl = pq.read_table(
        WIDE_PATH,
        columns=["symbol", "date", "open", "close", "volume"],
        filters=[("symbol", "in", chunk)],
    )
    df = tbl.to_pandas()
    df["date"] = pd.to_datetime(df["date"])
    wides = {
        c: df.pivot(index="date", columns="symbol", values=c).reindex(dates_index)
        for c in ("open", "close", "volume")
    }
    del df, tbl
    (close_m, open_m), _report = ph.mask_regime_breaks(wides["close"], wides["open"])
    panel = parent.build_signal_panel(close_m, open_m, wides["volume"], filter_split_like=True)
    if panel.empty:
        return panel
    panel["prev_close"] = parent.lookup_from_wide(close_m.shift(1), panel["date"], panel["symbol"])
    panel["date"] = panel["date"].astype("datetime64[ns]")
    d = dtc[dtc["symbol"].isin(chunk)].copy()
    d["visible_date"] = d["visible_date"].astype("datetime64[ns]")
    panel = parent.attach_dtc(panel, d)
    not_top = panel["dtc_cross_sectional_pct"].isna() | (
        panel["dtc_cross_sectional_pct"] < DTC_TOP_DECILE
    )
    short_ok = (panel["dv21"] >= ADV_MIN_SHORT) & not_top
    out = []
    for leg, mask, asc in (
        ("long", pd.Series(True, index=panel.index), True),
        ("short", short_ok, False),
    ):
        sub = panel.loc[mask].sort_values(["date", "symbol"], kind="stable")
        sub = sub.assign(rank=sub.groupby("date")["z"].rank(method="first", ascending=asc))
        sub = sub[sub["rank"] <= K_LEG].copy()
        sub["leg"] = leg
        out.append(sub)
    res = pd.concat(out, ignore_index=True)
    return res.rename(columns={"open": "open_bar", "close": "close_bar"})[
        [
            "date",
            "symbol",
            "leg",
            "z",
            "dv21",
            "open_bar",
            "close_bar",
            "prev_close",
            "dtc_cross_sectional_pct",
        ]
    ]


def merge_top_k(parts: pd.DataFrame) -> pd.DataFrame:
    """Global per-date top-K per leg from per-chunk top-K rows (exact)."""
    out = []
    for leg, asc in (("long", True), ("short", False)):
        sub = parts[parts["leg"] == leg].sort_values(["date", "symbol"], kind="stable")
        sub = sub.assign(rank=sub.groupby("date")["z"].rank(method="first", ascending=asc))
        out.append(sub[sub["rank"] <= K_LEG].drop(columns="rank"))
    return (
        pd.concat(out, ignore_index=True)
        .sort_values(["date", "leg", "symbol"])
        .reset_index(drop=True)
    )


def bar_edge_table(picks: pd.DataFrame, start: str, end: str | None) -> dict[str, Any]:
    """E_bar (bp) by tier and leg: mean d*(C/O-1); plus the long-leg <$5M share."""
    m = picks["date"] >= pd.Timestamp(start)
    if end is not None:
        m &= picks["date"] <= pd.Timestamp(end)
    w = picks[m].copy()
    w["d"] = np.where(w["leg"] == "long", 1.0, -1.0)
    w["r"] = w["d"] * (w["close_bar"] / w["open_bar"] - 1.0) * 1e4
    tab: dict[str, Any] = {}
    for tier in TIER_EDGES:
        tab[tier] = {}
        for leg in ("long", "short"):
            s = w[(w["tier"] == tier) & (w["leg"] == leg)]["r"]
            tab[tier][leg] = {
                "n": int(len(s)),
                "E_bar_bp": float(s.mean()) if len(s) else None,
                "se_bp": float(s.std(ddof=1) / np.sqrt(len(s))) if len(s) > 1 else None,
            }
    longs = w[w["leg"] == "long"]
    tab["long_rows_total"] = int(len(longs))
    tab["long_rows_dv21_below_5m"] = int((longs["tier"].isna()).sum())
    tab["long_dv21_below_5m_share"] = float(longs["tier"].isna().mean()) if len(longs) else None
    tab["window"] = [start, end or str(w["date"].max().date())]
    return tab


def cmd_picks(_args: argparse.Namespace) -> int:
    import pyarrow.parquet as pq

    from open_composer.research.features import price_hygiene as ph
    from scripts import run_t20260929_32_gap_fade_ls as parent

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    sym_tbl = pq.read_table(WIDE_PATH, columns=["symbol"], read_dictionary=["symbol"])
    symbols = sorted({str(s) for ch in sym_tbl.column(0).chunks for s in ch.dictionary.to_pylist()})
    del sym_tbl
    date_tbl = pq.read_table(WIDE_PATH, columns=["date"])
    dates_index = pd.DatetimeIndex(
        sorted(pd.to_datetime(date_tbl.column(0).unique().to_pandas()))
    ).astype("datetime64[ns]")
    del date_tbl
    _log(
        f"{len(symbols):,} symbols, {len(dates_index):,} sessions {dates_index[0].date()}..{dates_index[-1].date()}"
    )
    dtc = parent.load_dtc()
    parts = []
    for i in range(0, len(symbols), CHUNK_SYMBOLS):
        chunk = symbols[i : i + CHUNK_SYMBOLS]
        p = _chunk_picks(chunk, dates_index, dtc, parent, ph)
        parts.append(p)
        _log(f"chunk {i // CHUNK_SYMBOLS + 1}: {len(p):,} candidate rows")
    picks = merge_top_k(pd.concat(parts, ignore_index=True))
    picks["tier"] = picks["dv21"].map(tier_of)
    picks.to_parquet(PICKS_PATH, index=False)
    latest = str(picks["date"].max().date())
    bench = bar_edge_table(picks, BENCH_START, None)
    stress = bar_edge_table(picks, *STRESS_WINDOW)
    summary = {
        "generated_at": datetime.now(UTC).isoformat(),
        "sessions": [str(dates_index[0].date()), str(dates_index[-1].date())],
        "latest_pick_date": latest,
        "bench": bench,
        "stress": stress,
        "picks_total": int(len(picks)),
    }
    (CACHE_DIR / "picks_summary.json").write_text(json.dumps(summary, indent=1) + "\n")
    _log(f"bench {bench}")
    _log(f"stress {stress}")

    pool = picks[(picks["date"] >= pd.Timestamp(BENCH_START)) & picks["tier"].notna()]
    sample = stratified_sample(pool, SEED)
    cols = [
        "sample_id", "symbol", "date", "leg", "tier", "z", "dv21",
        "open_bar", "close_bar", "prev_close", "dtc_cross_sectional_pct",
    ]  # fmt: skip
    sample["date"] = pd.to_datetime(sample["date"]).dt.strftime("%Y-%m-%d")
    sample[cols].to_csv(SAMPLE_PATH, index=False)
    counts = sample.groupby(["tier", "leg"]).size().to_dict()
    _log(f"sample rows {len(sample)}: {counts}")
    return 0


# --------------------------------------------------------------------------
# Alpaca historical trades (data API only)
# --------------------------------------------------------------------------


def et_to_utc(day: str, hh: int, mm: int, ss: int = 0) -> str:
    y, m, d = (int(x) for x in day.split("-"))
    ts = datetime(y, m, d, hh, mm, ss, tzinfo=NY).astimezone(UTC)
    return ts.strftime("%Y-%m-%dT%H:%M:%SZ")


def _norm_trade(t: dict[str, Any]) -> dict[str, Any]:
    return {
        "t": t.get("t"),
        "x": t.get("x"),
        "p": t.get("p"),
        "s": t.get("s"),
        "c": t.get("c") or [],
        "z": t.get("z"),
    }


class DataSession:
    """Rate-paced (<=3 req/s) GET session for data.alpaca.markets; 429 backs off.

    Credentials are read from the environment (``.env`` via load_dotenv) and live only
    in the session headers; nothing here logs or stores headers.
    """

    def __init__(self) -> None:
        import requests
        from dotenv import load_dotenv

        from open_composer.config import alpaca_api_key_id, alpaca_api_secret_key

        load_dotenv(dotenv_path=ROOT / ".env")
        key, secret = alpaca_api_key_id(), alpaca_api_secret_key()
        if not key or not secret:
            raise SystemExit("ALPACA_API_KEY_ID/ALPACA_API_SECRET_KEY not set")
        self.session = requests.Session()
        self.session.headers.update({"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret})
        self._last = 0.0
        self.calls = 0
        self.n429 = 0

    def get(self, symbol: str, params: dict[str, Any], max_retries: int = 8) -> dict[str, Any]:
        return self.get_url(DATA_URL.format(symbol=symbol), params, max_retries)

    def get_url(self, url: str, params: dict[str, Any], max_retries: int = 8) -> dict[str, Any]:
        for attempt in range(max_retries):
            wait = MIN_INTERVAL_S - (time.monotonic() - self._last)
            if wait > 0:
                time.sleep(wait)
            self._last = time.monotonic()
            resp = self.session.get(url, params=params, timeout=40)
            self.calls += 1
            if resp.status_code == 200:
                return resp.json()
            if resp.status_code == 429 or resp.status_code >= 500:
                self.n429 += resp.status_code == 429
                retry = resp.headers.get("Retry-After")
                sleep_s = float(retry) if retry else min(2**attempt, 60)
                time.sleep(sleep_s + random.uniform(0, 0.5))
                continue
            raise RuntimeError(f"HTTP {resp.status_code} for {url} {resp.text[:200]}")
        raise RuntimeError(f"gave up after {max_retries} attempts for {url}")


def fetch_window(
    session: DataSession,
    symbol: str,
    start: str,
    end: str,
    stop_fn: Any = None,
    max_pages: int = MAX_PAGES,
) -> dict[str, Any]:
    """Page through trades in [start, end); keep official-print candidates and the
    first/last 5 trades; ``stop_fn(kept, last_t)`` may end paging early."""
    token = None
    kept: list[dict[str, Any]] = []
    first: list[dict[str, Any]] = []
    last: list[dict[str, Any]] = []
    n_seen = pages = 0
    truncated = False
    while True:
        params = {"start": start, "end": end, "limit": PAGE_LIMIT, "feed": "sip"}
        if token:
            params["page_token"] = token
        body = session.get(symbol, params)
        pages += 1
        trades = [_norm_trade(t) for t in (body.get("trades") or [])]
        n_seen += len(trades)
        if len(first) < 5:
            first.extend(trades[: 5 - len(first)])
        if trades:
            last = (last + trades)[-5:]
        kept.extend(t for t in trades if KEEP_CONDS & set(t["c"]))
        token = body.get("next_page_token")
        if not token:
            break
        if stop_fn is not None and trades and stop_fn(kept, trades[-1]["t"]):
            break
        if pages >= max_pages:
            truncated = True
            break
    return {
        "kept": kept,
        "first": first,
        "last": last,
        "n_trades": n_seen,
        "pages": pages,
        "truncated": truncated,
    }


def _t_of(iso: str) -> datetime:
    return datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(NY)


def make_open_stop(tape: str) -> Any:
    listing = LISTING_BY_TAPE.get(tape, ())

    def stop(kept: list[dict[str, Any]], last_t: str) -> bool:
        t = _t_of(last_t)
        past = t.hour * 3600 + t.minute * 60 + t.second >= 9 * 3600 + 30 * 60 + 30
        return past and any("Q" in k["c"] and k["x"] in listing for k in kept)

    return stop


def make_close_stop(tape: str) -> Any:
    listing = LISTING_BY_TAPE.get(tape, ())

    def stop(kept: list[dict[str, Any]], last_t: str) -> bool:
        t = _t_of(last_t)
        past = t.hour * 3600 + t.minute * 60 + t.second >= 16 * 3600 + 60
        has_m = any("M" in k["c"] and k["x"] in listing for k in kept)
        has_6 = any("6" in k["c"] and k["x"] in listing for k in kept)
        return past and has_m and has_6

    return stop


def summarize_official(
    window: str, res: dict[str, Any], tape: str | None, symbol: str, day: str, sid: str
) -> dict[str, Any]:
    kept = res["kept"]
    tape = (
        tape or (kept[0]["z"] if kept else None) or (res["first"][0]["z"] if res["first"] else None)
    )
    pick = None
    if tape:
        pick = official_open(kept, tape) if window == "open" else official_close(kept, tape)
    row: dict[str, Any] = {
        "sample_id": sid,
        "window": window,
        "symbol": symbol,
        "date": day,
        "tape": tape,
        "n_trades": res["n_trades"],
        "pages": res["pages"],
        "truncated": res["truncated"],
        "n_kept_prints": len(kept),
    }
    if pick is None:
        row.update(
            {
                "status": "missing",
                "reason": "no_trades" if not res["n_trades"] else "no_official_print",
            }
        )
        prims = [k for k in kept if {"Q", "M"} & set(k["c"])]
        row["cands"] = prims[:6]
    else:
        prim_code = "Q" if window == "open" else "M"
        prices = [k["p"] for k in kept if prim_code in k["c"]]
        row.update(
            {
                "status": "ok",
                "source": pick["source"],
                "price": pick["p"],
                "exchange": pick["x"],
                "time": pick["t"],
                "size": pick["s"],
                "n_primary_prints": pick["n_primary"],
                "primary_price_range_bp": (
                    (max(prices) / min(prices) - 1.0) * 1e4 if len(prices) > 1 else 0.0
                ),
            }
        )
    row["prints"] = kept[:12]
    row["first"] = res["first"][:3]
    row["last"] = res["last"][-3:]
    return row


def _tape_hint(session: DataSession, symbol: str, day: str) -> str | None:
    body = session.get(
        symbol,
        {
            "start": et_to_utc(day, 9, 30, 0),
            "end": et_to_utc(day, 9, 31, 0),
            "limit": 1,
            "feed": "sip",
        },
    )
    trades = body.get("trades") or []
    return trades[0].get("z") if trades else None


def fetch_raw_bar(session: DataSession, symbol: str, day: str, sid: str) -> dict[str, Any]:
    """Unadjusted Alpaca daily bar for the session (price basis of the official prints).

    The local daily panel is split- and dividend-adjusted as of download, the trades are
    not; the raw bar gives the adjustment factor so the open/close parts of Delta are
    computed on one price basis.
    """
    nxt = (date.fromisoformat(day) + timedelta(days=1)).isoformat()
    body = session.get_url(
        BARS_URL,
        {
            "symbols": symbol,
            "timeframe": "1Day",
            "start": day,
            "end": nxt,
            "adjustment": "raw",
            "feed": "sip",
            "limit": 5,
        },
    )
    bars = (body.get("bars") or {}).get(symbol) or []
    bars = [b for b in bars if str(b.get("t", ""))[:10] == day] or bars[:1]
    row: dict[str, Any] = {"sample_id": sid, "window": "rawbar", "symbol": symbol, "date": day}
    if bars:
        b = bars[0]
        row.update(
            {
                "status": "ok",
                "o": b.get("o"),
                "c": b.get("c"),
                "h": b.get("h"),
                "l": b.get("l"),
                "t": b.get("t"),
            }
        )
    else:
        row.update({"status": "missing", "reason": "no_raw_bar"})
    return row


def fetch_row(session: DataSession, row: pd.Series, full: bool = False) -> list[dict[str, Any]]:
    symbol, day, sid = row["symbol"], row["date"], row["sample_id"]
    tape = _tape_hint(session, symbol, day)
    out = []
    open_res = fetch_window(
        session,
        symbol,
        et_to_utc(day, 9, 29, 0),
        et_to_utc(day, 9, 45, 0),
        None if full or tape is None else make_open_stop(tape),
    )
    out.append(summarize_official("open", open_res, tape, symbol, day, sid))
    close_start = et_to_utc(day, 15, 59, 0) if full else et_to_utc(day, 16, 0, 0)
    close_res = fetch_window(
        session,
        symbol,
        close_start,
        et_to_utc(day, 16, 10, 0),
        None if full or tape is None else make_close_stop(tape),
    )
    out.append(summarize_official("close", close_res, tape, symbol, day, sid))
    out.append(fetch_raw_bar(session, symbol, day, sid))
    return out


def _done_keys() -> set[tuple[str, str]]:
    if not OFFICIAL_PATH.exists():
        return set()
    keys = set()
    for line in OFFICIAL_PATH.read_text().splitlines():
        if line.strip():
            r = json.loads(line)
            keys.add((r["sample_id"], r["window"]))
    return keys


def cmd_check5(_args: argparse.Namespace) -> int:
    sample = pd.read_csv(SAMPLE_PATH)
    order = [("T2", "long"), ("T2", "short"), ("T3", "long"), ("T3", "short"), ("T1", "short")]
    rows = []
    for tier, leg in order:
        sub = sample[(sample["tier"] == tier) & (sample["leg"] == leg)]
        if len(sub):
            rows.append(sub.iloc[0])
    session = DataSession()
    for row in rows:
        res = fetch_row(session, row, full=True)
        path = CACHE_DIR / f"check5_{row['symbol']}_{row['date']}.json"
        payload = {
            "sample_row": {
                k: (v if not isinstance(v, (np.floating, np.integer)) else float(v))
                for k, v in row.items()
            },
            "windows": res,
        }
        path.write_text(json.dumps(payload, indent=1, default=str) + "\n")
        _log(
            f"check5 {row['sample_id']} tier={row['tier']} -> {[(r['window'], r['status'], r.get('source'), r.get('price'), r.get('exchange')) for r in res]}"
        )
    return 0


def cmd_fetch(args: argparse.Namespace) -> int:
    sample = pd.read_csv(SAMPLE_PATH)
    done = _done_keys()
    session = DataSession()
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    todo = [
        r
        for _, r in sample.iterrows()
        if any((r["sample_id"], w) not in done for w in ("open", "close", "rawbar"))
    ]
    _log(f"{len(sample)} sample rows, {len(todo)} to fetch")
    t0 = time.time()
    for i, row in enumerate(todo):
        results = fetch_row(session, row)
        with OFFICIAL_PATH.open("a") as fh:
            for r in results:
                if (r["sample_id"], r["window"]) not in done:
                    fh.write(json.dumps(r, default=str) + "\n")
                    done.add((r["sample_id"], r["window"]))
        if (i + 1) % 20 == 0:
            _log(
                f"{i + 1}/{len(todo)} rows, {session.calls} calls, {session.n429} x429, {time.time() - t0:.0f}s"
            )
        if args.limit and i + 1 >= args.limit:
            break
    return 0


# --------------------------------------------------------------------------
# analyze
# --------------------------------------------------------------------------


def _quantiles(x: np.ndarray) -> dict[str, float]:
    q = np.quantile(x, [0.05, 0.25, 0.5, 0.75, 0.95])
    return {
        "p05": float(q[0]),
        "p25": float(q[1]),
        "median": float(q[2]),
        "p75": float(q[3]),
        "p95": float(q[4]),
    }


def build_paired_frame(sample: pd.DataFrame, official: pd.DataFrame) -> pd.DataFrame:
    """Sample rows joined with official open/close prints and the unadjusted daily bar.

    Delta (total) = r_off - r_bar with r_bar from the local daily panel; both returns are
    intraday ratios, so the adjustment factor cancels.  The open/close parts are computed
    against the unadjusted (raw) daily bar, the same price basis as the trades.
    """
    op = official[official["window"] == "open"].drop_duplicates("sample_id", keep="last")
    cl = official[official["window"] == "close"].drop_duplicates("sample_id", keep="last")
    rb = official[official["window"] == "rawbar"].drop_duplicates("sample_id", keep="last")
    df = (
        sample.merge(
            op[["sample_id", "status", "source", "price", "exchange", "tape"]].rename(
                columns={
                    "status": "open_status",
                    "source": "open_source",
                    "price": "o_off",
                    "exchange": "open_exchange",
                }
            ),
            on="sample_id",
            how="left",
        )
        .merge(
            cl[["sample_id", "status", "source", "price", "exchange"]].rename(
                columns={
                    "status": "close_status",
                    "source": "close_source",
                    "price": "c_off",
                    "exchange": "close_exchange",
                }
            ),
            on="sample_id",
            how="left",
        )
        .merge(
            rb[["sample_id", "status", "o", "c"]].rename(
                columns={"status": "raw_status", "o": "o_raw", "c": "c_raw"}
            ),
            on="sample_id",
            how="left",
        )
    )
    df["d"] = df["leg"].map(direction)
    have = (df["open_status"] == "ok") & (df["close_status"] == "ok") & (df["raw_status"] == "ok")
    df["has_both"] = have
    keys = ("r_bar", "r_off", "delta", "delta_open", "delta_close")
    comp = []
    for d, ob, cb, orw, crw, oo, co, h in zip(
        df["d"],
        df["open_bar"],
        df["close_bar"],
        df["o_raw"],
        df["c_raw"],
        df["o_off"],
        df["c_off"],
        have,
        strict=True,
    ):
        if not h:
            comp.append(dict.fromkeys(keys, np.nan))
            continue
        total = delta_components(int(d), ob, cb, oo, co)
        parts = delta_components(int(d), orw, crw, oo, co)
        total["delta_open"] = parts["delta_open"]
        total["delta_close"] = parts["delta_close"]
        comp.append(total)
    df = pd.concat([df, pd.DataFrame(comp, index=df.index)], axis=1)
    df["delta_parts_residual"] = df["delta"] - df["delta_open"] - df["delta_close"]
    df["adj_factor_open"] = df["open_bar"] / df["o_raw"]
    df["adj_factor_close"] = df["close_bar"] / df["c_raw"]
    dev_o = (df["o_off"] / df["o_raw"] - 1.0).abs()
    dev_c = (df["c_off"] / df["c_raw"] - 1.0).abs()
    df["mismatch"] = have & ((dev_o > MISMATCH_LIMIT) | (dev_c > MISMATCH_LIMIT))
    df["usable"] = have & ~df["mismatch"]
    return df


def cell_stats(g: pd.DataFrame, e_bar: float | None, rng: np.random.Generator) -> dict[str, Any]:
    u = g[g["usable"]]
    n_s = int(len(g))
    n_ok = int(len(u))
    out: dict[str, Any] = {
        "n_sample": n_s,
        "n_usable": n_ok,
        "n_mismatch": int(g["mismatch"].sum()),
        "n_missing_either": int((~g["has_both"]).sum()),
        "missing_rate": float(1.0 - n_ok / n_s) if n_s else None,
        "E_bar_bp": e_bar,
    }
    if n_ok == 0:
        return out
    dl = u["delta"].to_numpy() * 1e4
    out.update(
        {
            "mean_delta_bp": float(dl.mean()),
            "mean_delta_open_bp": float(u["delta_open"].mean() * 1e4),
            "mean_delta_close_bp": float(u["delta_close"].mean() * 1e4),
            "delta_quantiles_bp": _quantiles(dl),
            "mean_r_off_bp_sample": float(u["r_off"].mean() * 1e4),
            "mean_r_bar_bp_sample": float(u["r_bar"].mean() * 1e4),
        }
    )
    idx = rng.integers(0, n_ok, size=(BOOTSTRAP_DRAWS, n_ok))
    boots = dl[idx].mean(axis=1)
    lo, hi = np.quantile(boots, [0.05, 0.95])
    out["mean_delta_ci90_bp"] = [float(lo), float(hi)]
    if e_bar is not None:
        out["E_off_bp"] = float(e_bar + dl.mean())
        out["E_off_ci90_bp"] = [float(e_bar + lo), float(e_bar + hi)]
    return out


def cmd_analyze(_args: argparse.Namespace) -> int:
    picks = pd.read_parquet(PICKS_PATH)
    sample = pd.read_csv(SAMPLE_PATH)
    official = pd.DataFrame(
        [json.loads(x) for x in OFFICIAL_PATH.read_text().splitlines() if x.strip()]
    )
    df = build_paired_frame(sample, official)
    rng = np.random.default_rng(SEED)
    bench = bar_edge_table(picks, BENCH_START, None)
    stress = bar_edge_table(picks, *STRESS_WINDOW)
    tiers: dict[str, Any] = {}
    for tier in TIER_EDGES:
        tiers[tier] = {}
        for leg in ("long", "short"):
            g = df[(df["tier"] == tier) & (df["leg"] == leg)]
            tiers[tier][leg] = {
                "n_population_bench": bench[tier][leg]["n"],
                **cell_stats(g, bench[tier][leg]["E_bar_bp"], rng),
            }
        g = df[df["tier"] == tier]
        n_s = len(g)
        n_ok = int(g["usable"].sum())
        miss = float(1.0 - n_ok / n_s) if n_s else None
        tiers[tier]["tier_missing_rate"] = miss
        tiers[tier]["tier_n_sample"] = int(n_s)
        tiers[tier]["no_conclusion"] = bool(miss is None or miss > MISSING_LIMIT)

    # pooled T2+T3
    def cells_for(
        pop_weights: bool, deltas: dict[tuple[str, str], np.ndarray]
    ) -> dict[tuple[str, str], tuple[float, float, float]]:
        cells = {}
        for tier in ("T2", "T3"):
            for leg in ("long", "short"):
                t = tiers[tier][leg]
                w = t["n_population_bench"] if pop_weights else max(t["n_usable"], 0)
                cells[(tier, leg)] = (
                    float(w),
                    float(t["E_bar_bp"]),
                    float(np.mean(deltas[(tier, leg)]))
                    if len(deltas[(tier, leg)])
                    else float("nan"),
                )
        return cells

    deltas = {
        (tier, leg): df[(df["tier"] == tier) & (df["leg"] == leg) & df["usable"]][
            "delta"
        ].to_numpy()
        * 1e4
        for tier in ("T2", "T3")
        for leg in ("long", "short")
    }
    have_all = all(len(v) for v in deltas.values())
    pooled: dict[str, Any] = {}
    if have_all:
        pooled_e = pooled_e_off(cells_for(True, deltas))
        pooled_e_bar = pooled_e_off(
            {k: (w, e, 0.0) for k, (w, e, _d) in cells_for(True, deltas).items()}
        )
        pooled_alt = pooled_e_off(cells_for(False, deltas))
        boots = np.empty(BOOTSTRAP_DRAWS)
        keys = list(deltas)
        for b in range(BOOTSTRAP_DRAWS):
            cur = {}
            for k in keys:
                arr = deltas[k]
                cur[k] = arr[rng.integers(0, len(arr), size=len(arr))].mean()
            base = cells_for(True, deltas)
            boots[b] = pooled_e_off({k: (base[k][0], base[k][1], float(cur[k])) for k in keys})
        lo, hi = np.quantile(boots, [0.05, 0.95])
        pooled = {
            "e_off_T2T3_bp": pooled_e,
            "e_off_T2T3_ci90_bp": [float(lo), float(hi)],
            "bootstrap_share_e_off_ge_threshold_reference": float((boots >= THRESHOLD_BP).mean()),
            "e_bar_T2T3_bp": pooled_e_bar,
            "mean_delta_T2T3_bp": pooled_e - pooled_e_bar,
            "e_off_T2T3_sample_weighted_bp_reference": pooled_alt,
            "weights_population_rows": {
                f"{t}_{lg}": tiers[t][lg]["n_population_bench"]
                for t in ("T2", "T3")
                for lg in ("long", "short")
            },
        }
    nc = [t for t in ("T2", "T3") if tiers[t]["no_conclusion"]]
    if nc or not have_all:
        verdict, status = (
            "no_conclusion",
            "missing_rate_above_20pct_or_empty_cell:" + ",".join(nc or ["cell"]),
        )
    elif pooled["e_off_T2T3_bp"] >= THRESHOLD_BP:
        verdict, status = "continue", "conclusive"
    else:
        verdict, status = "close", "conclusive"

    # groupings within T2+T3 usable sample
    u = df[df["usable"] & df["tier"].isin(["T2", "T3"])].copy()

    def group_mean(col: str, by: pd.Series) -> dict[str, Any]:
        g = u.groupby(by, observed=True)[col].agg(["mean", "count"])
        return {
            str(k): {"mean_delta_bp": float(v["mean"] * 1e4), "n": int(v["count"])}
            for k, v in g.iterrows()
        }

    groups: dict[str, Any] = {}
    if len(u) >= 9:
        groups["by_abs_z_tercile"] = group_mean(
            "delta", pd.qcut(u["z"].abs(), 3, labels=["low", "mid", "high"], duplicates="drop")
        )
        groups["by_price_tercile"] = group_mean(
            "delta", pd.qcut(u["o_raw"], 3, labels=["low", "mid", "high"], duplicates="drop")
        )
        groups["by_dv21_group"] = group_mean("delta", u["tier"])
        groups["by_leg"] = group_mean("delta", u["leg"])

    # condition-code statistics
    stat: dict[str, Any] = {}
    for window in ("open", "close"):
        w = official[official["window"] == window]
        stat[window] = {
            "rows": int(len(w)),
            "status_counts": w["status"].value_counts().to_dict(),
            "source_counts": w["source"].value_counts(dropna=True).to_dict()
            if "source" in w
            else {},
            "exchange_counts": w["exchange"].value_counts(dropna=True).to_dict()
            if "exchange" in w
            else {},
            "missing_reasons": w[w["status"] != "ok"]["reason"].value_counts().to_dict()
            if "reason" in w
            else {},
            "truncated": int(w["truncated"].astype(bool).sum()),
            "multi_primary_prints": int(
                (w.get("n_primary_prints", pd.Series(dtype=float)).fillna(0) > 1).sum()
            ),
            "primary_price_range_bp_max": float(
                w.get("primary_price_range_bp", pd.Series(dtype=float)).max()
            )
            if "primary_price_range_bp" in w
            else None,
        }
    stat["tape_counts"] = (
        official.drop_duplicates("sample_id")["tape"].value_counts(dropna=False).to_dict()
    )

    # by-source Delta (listing vs other vs fallback), diagnostics only
    by_source = {}
    uu = df[df["usable"]]
    for (so, sc), g in uu.groupby(["open_source", "close_source"]):
        by_source[f"{so}|{sc}"] = {
            "n": int(len(g)),
            "mean_delta_bp": float(g["delta"].mean() * 1e4),
        }

    incl = df[df["has_both"]]
    including_mismatch = {
        "n": int(len(incl)),
        "mean_delta_bp": float(incl["delta"].mean() * 1e4) if len(incl) else None,
    }

    results = {
        "iter_id": ITERATION_ID,
        "generated_at": datetime.now(UTC).isoformat(),
        "verdict": verdict,
        "conclusion_status": status,
        "threshold_bp": THRESHOLD_BP,
        **pooled,
        "tiers": tiers,
        "stress_E_bar": stress,
        "stress_E_bar_T2T3_pooled_bp": pooled_e_off(
            {
                (t, lg): (float(stress[t][lg]["n"]), float(stress[t][lg]["E_bar_bp"]), 0.0)
                for t in ("T2", "T3")
                for lg in ("long", "short")
            }
        ),
        "bench_E_bar": bench,
        "long_dv21_below_5m_share": bench["long_dv21_below_5m_share"],
        "delta_groups_T2T3": groups,
        "delta_by_official_source_pair": by_source,
        "delta_including_mismatch_rows": including_mismatch,
        "condition_code_stats": stat,
        "sample": {
            "rows": int(len(sample)),
            "seed": SEED,
            "by_tier_leg": {
                f"{t}_{lg}": int(((sample["tier"] == t) & (sample["leg"] == lg)).sum())
                for t in TIER_EDGES
                for lg in ("long", "short")
            },
        },
        "bootstrap": {"draws": BOOTSTRAP_DRAWS, "seed": SEED, "interval": "90% percentile"},
        "notes": {
            "E_off_definition": "E_off = E_bar (all bench-window picks, daily bars) + mean paired Delta (sample rows with usable official prices)",
            "mismatch_limit": MISMATCH_LIMIT,
            "missing_limit": MISSING_LIMIT,
            "workflow_pass": True,
            "research_pass": False,
            "paper_ready_pass": False,
        },
    }
    RESULTS_PATH.write_text(
        json.dumps(
            results,
            indent=2,
            default=lambda o: float(o) if isinstance(o, (np.floating, np.integer)) else str(o),
        )
        + "\n"
    )
    df.to_csv(CACHE_DIR / "paired_frame.csv", index=False)
    _log(f"verdict={verdict} status={status} e_off_T2T3={pooled.get('e_off_T2T3_bp')}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("picks").set_defaults(fn=cmd_picks)
    sub.add_parser("check5").set_defaults(fn=cmd_check5)
    p = sub.add_parser("fetch")
    p.add_argument("--limit", type=int, default=0)
    p.set_defaults(fn=cmd_fetch)
    sub.add_parser("analyze").set_defaults(fn=cmd_analyze)
    args = parser.parse_args(argv)
    return int(args.fn(args))


if __name__ == "__main__":
    raise SystemExit(main())
