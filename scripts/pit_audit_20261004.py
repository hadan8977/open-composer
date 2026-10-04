"""T-20261004-54: point-in-time audit of the research snapshot (data pitfalls #62 and #63).

Everything is written under ``data/research/pit_audit_20261004/``; the snapshot
(``data/research/equity_book/``), ``data/features/`` and ``data/research/book_v12/`` are only read.

Stages (each one is a separate heavy step; run capped, one at a time)::

    scripts/run_capped.sh --mem 1.8G -- uv run python scripts/pit_audit_20261004.py sec
    scripts/run_capped.sh --mem 1.8G -- uv run python scripts/pit_audit_20261004.py validate-sec
    scripts/run_capped.sh --mem 1.8G -- uv run python scripts/pit_audit_20261004.py panel
    scripts/run_capped.sh --mem 1.8G -- uv run python scripts/pit_audit_20261004.py signals
    scripts/run_capped.sh --mem 1.8G -- uv run python scripts/pit_audit_20261004.py stage1

``sec`` (#62): ladder-derived columns as of the filing date.  ``build_sec_xbrl_fundamentals``
builds each issuer's quarterly ladder from the final facts table, so a quarter whose neighbours
were first filed later (comparatives first tagged a year after the fact, late 10-Q) gets a
``sue_eps`` that uses data nobody had on that date.  Here ``sue_series`` and
``asset_growth_events`` (the two ladder consumers) are called on the fact subset with
``usable_session <= s`` at every session ``s`` of the issuer's own filings; an entry that becomes
computable only at ``s`` takes effect at ``s`` (not at the usable session of its own quarter).
All other columns of ``compute_cik_table`` are already event-driven; ``validate-sec`` checks that
claim against a brute-force prefix recompute on a sample of issuers.

``panel`` (#63): ``mcap_source in (adv_fallback, adv_fallback_outlier)`` rows use the median of
``close * shares / dollar_adv_21`` of the adv-rank bucket (250 wide) over the previous 252 sessions
(expanding when shorter), instead of the whole-calendar-year median.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import Counter
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

AUDIT_DIR = ROOT / "data/research/pit_audit_20261004"
REPORT_DIR = ROOT / "reports/research/program/pit-audit-2026-10-04"
FACTS_COPY = AUDIT_DIR / "facts.parquet"
SEC_PIT_DIR = AUDIT_DIR / "sec_daily_pit"
SEC_FINAL_DIR = AUDIT_DIR / "sec_daily_final"
YEARS = list(range(2016, 2027))
OVERRIDE_COLUMNS = ("sue_eps", "sue_rev", "asset_growth")
#: columns that feed a theme signal; validated to be prefix-consistent
CHECK_COLUMNS = (
    "stockholders_equity",
    "total_assets",
    "shares_outstanding",
    "net_income",
    "gross_profitability",
    "roe",
    "accruals",
)


def _log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


# --------------------------------------------------------------------------
# #62: as-of-filing ladder
# --------------------------------------------------------------------------


def new_entries_by_session(
    sessions: list[pd.Timestamp], entries_at
) -> list[tuple[pd.Timestamp, pd.Timestamp, float]]:
    """``entries_at(s)`` returns ``[(own_session, value), ...]`` computed from the facts known at
    session ``s``.  Returns ``(effective_session, own_session, value)`` for every entry the first
    time it is computable: an entry whose inputs arrive late takes effect at the arrival session."""
    seen: Counter = Counter()
    out: list[tuple[pd.Timestamp, pd.Timestamp, float]] = []
    for s in sessions:
        now = entries_at(s)
        running: Counter = Counter()
        for key in now:
            running[key] += 1
            if running[key] > seen[key]:
                out.append((s, key[0], float(key[1])))
        seen = seen | running
    return out


def asof_values(
    index: list[pd.Timestamp], events: list[tuple[pd.Timestamp, pd.Timestamp, float]]
) -> np.ndarray:
    """Value in force at each session of ``index`` (ascending): among the events with effective
    session <= the session, the one with the latest own session (the original forward fill rule:
    the latest quarter wins; a late-computable older quarter never overrides a newer one)."""
    out = np.full(len(index), np.nan)
    ev = sorted(events, key=lambda e: e[0])
    j = 0
    best_key = None
    best_val = np.nan
    for i, d in enumerate(index):
        while j < len(ev) and ev[j][0] <= d:
            if best_key is None or ev[j][1] >= best_key:
                best_key, best_val = ev[j][1], ev[j][2]
            j += 1
        out[i] = best_val
    return out


def pit_ladder_events(
    quarterly: dict[int, tuple[pd.Timestamp, pd.Timestamp, float]], sue_series
) -> list[tuple[pd.Timestamp, pd.Timestamp, float]]:
    """PIT SUE events from one concept's final quarterly ladder (``sue_series`` is the production
    function from ``build_sec_xbrl_fundamentals``)."""
    if not quarterly:
        return []
    sessions = sorted({v[0] for v in quarterly.values()})

    def entries_at(s: pd.Timestamp) -> list[tuple[pd.Timestamp, float]]:
        return sue_series({q: v for q, v in quarterly.items() if v[0] <= s})

    return new_entries_by_session(sessions, entries_at)


def pit_asset_growth_events(frame: pd.DataFrame, asset_growth_events) -> list:
    # only the rows ``asset_growth_events`` itself uses (same filter), so the result is identical
    ta = frame[
        (frame["concept"] == "total_assets")
        & (~frame["restated"])
        & (frame["fp"] == "FY")
        & frame["fy"].notna()
    ]
    sessions = sorted(set(ta["usable_session"].dropna()))
    if not sessions:
        return []

    def entries_at(s: pd.Timestamp) -> list[tuple[pd.Timestamp, float]]:
        return asset_growth_events(ta[ta["usable_session"] <= s])

    return new_entries_by_session(sessions, entries_at)


def pit_cik_table(cik: int, frame: pd.DataFrame, b, final: pd.DataFrame | None = None):
    """``compute_cik_table`` with ``sue_eps``, ``sue_rev`` and ``asset_growth`` as of the filing
    date.  ``b`` is the ``build_sec_xbrl_fundamentals`` module."""
    tab = final if final is not None else b.compute_cik_table(cik, frame)
    if tab.empty:
        return tab
    eps_q = b._quarterly_dict(frame, "eps_diluted")
    rev_q = b._quarterly_dict(frame, "revenue")
    ev = {
        "sue_eps": pit_ladder_events(eps_q, b.sue_series),
        "sue_rev": pit_ladder_events(rev_q, b.sue_series),
        "asset_growth": pit_asset_growth_events(frame, b.asset_growth_events),
    }
    base = tab.set_index("usable_session")
    index = sorted(set(base.index) | {e[0] for v in ev.values() for e in v})
    old_index = base.index
    base = base.reindex(pd.DatetimeIndex(index, name="usable_session"))
    # only rows that did not exist in the final table carry the previous state; a genuine NaN of
    # an existing row (e.g. accruals without a one-year-ago assets match) must stay NaN
    new_rows = ~base.index.isin(old_index)
    if new_rows.any():
        base.loc[new_rows] = base.ffill().loc[new_rows]
    for col, events in ev.items():
        base[col] = asof_values(index, events)
    base["cik"] = cik
    return base.reset_index()


def load_b():
    import build_sec_xbrl_fundamentals as b

    return b


def stage_sec(limit: int | None = None) -> dict:
    b = load_b()
    facts = pd.read_parquet(FACTS_COPY)
    mapping = b.build_cik_symbol_map(None)
    symbol_to_cik = dict(zip(mapping["symbol"], mapping["cik"], strict=True))
    last_date = date.today()
    sessions = pd.DatetimeIndex(
        [pd.Timestamp(d) for d in b.us_equity_session_dates(date(2000, 1, 1), last_date)]
    )
    session_pos = {ts: i for i, ts in enumerate(sessions)}
    final_tables: dict[int, pd.DataFrame] = {}
    pit_tables: dict[int, pd.DataFrame] = {}
    t0 = time.time()
    for k, (cik, group) in enumerate(facts.groupby("cik")):
        if limit and k >= limit:
            break
        cik = int(cik)
        tab = b.compute_cik_table(cik, group)
        if tab.empty:
            continue
        final_tables[cik] = tab
        pit = pit_cik_table(cik, group, b, final=tab)
        pit_tables[cik] = pit
        if k % 500 == 0:
            _log(f"cik {k} done, {time.time() - t0:.0f}s")
    out = {}
    for name, tables, outdir in (
        ("final", final_tables, SEC_FINAL_DIR),
        ("pit", pit_tables, SEC_PIT_DIR),
    ):
        outdir.mkdir(parents=True, exist_ok=True)
        events = b.build_all_events(tables, session_pos)
        _log(f"{name}: {len(events):,} events over {len(tables):,} issuers")
        for year in YEARS:
            frame = b.build_daily_year(year, events, symbol_to_cik, session_pos)
            if frame.empty:
                continue
            frame.to_parquet(outdir / f"{year}.parquet", index=False)
            _log(f"{name} {year}: {len(frame):,} rows")
        out[name] = {"events": int(len(events)), "issuers": len(tables)}
        del events
    (AUDIT_DIR / "sec_stage_meta.json").write_text(json.dumps(out, indent=1))
    return out


def stage_validate_sec(n: int = 120, seed: int = 7) -> dict:
    """Brute-force check: for a random sample of issuers, the non-override columns of the table at
    every session equal the last row of ``compute_cik_table(facts known at that session)``."""
    b = load_b()
    facts = pd.read_parquet(FACTS_COPY)
    ciks = facts["cik"].drop_duplicates().sample(n, random_state=seed).tolist()
    mism = {c: 0 for c in CHECK_COLUMNS}
    compared = 0
    t0 = time.time()
    for cik in ciks:
        g = facts[facts["cik"] == cik]
        final = b.compute_cik_table(int(cik), g).set_index("usable_session")
        for s in sorted(g["usable_session"].dropna().unique()):
            pre = b.compute_cik_table(int(cik), g[g["usable_session"] <= s])
            if pre.empty:
                continue
            s = pd.Timestamp(s)
            pre = pre.set_index("usable_session")
            if s not in pre.index or s not in final.index:
                continue
            compared += 1
            for c in CHECK_COLUMNS:
                a, f = pre.loc[s, c], final.loc[s, c]
                if not (pd.isna(a) and pd.isna(f)) and not np.isclose(a, f, rtol=1e-9, atol=0):
                    mism[c] += 1
    res = {
        "issuers": n,
        "session_rows_compared": compared,
        "mismatch_by_column": mism,
        "seconds": round(time.time() - t0),
    }
    (AUDIT_DIR / "sec_validation.json").write_text(json.dumps(res, indent=1))
    _log(json.dumps(res))
    return res


# --------------------------------------------------------------------------
# #63: fallback market cap with past data only
# --------------------------------------------------------------------------

PANEL_SNAP = ROOT / "data/research/equity_book/panel"
PANEL_MCAP_DIR = AUDIT_DIR / "panel_mcap"
BUCKET = 250
OUTLIER = 10.0
TRAIL = 252


def bucket_of(adv_rank: np.ndarray) -> np.ndarray:
    """Same bucket as the panel SQL ``cast(adv_rank / 250 as int)``: DuckDB's ``/`` is a float
    division and the cast rounds half to even, so the buckets are centred on multiples of 250
    (ranks 126-375 -> 1, 376-625 -> 2, ...; verified on the snapshot: the implied fallback ratio
    changes at ranks 126, 375, 626, 875, ...), not ``adv_rank // 250``."""
    return np.rint(np.asarray(adv_rank, dtype="float64") / BUCKET).astype("int64")


def trailing_bucket_median(
    date_idx: np.ndarray, bucket: np.ndarray, ratio: np.ndarray, n_dates: int, trail: int = TRAIL
) -> np.ndarray:
    """``k[d, b]`` = median of ``ratio`` over rows of bucket ``b`` on sessions
    ``d - trail .. d - 1`` (expanding while fewer sessions exist; the first session falls back to
    its own cross-section).
    ``ratio`` NaN rows are ignored.  Returns an ``(n_dates, n_buckets)`` array, NaN where empty."""
    ok = np.isfinite(ratio)
    date_idx, bucket, ratio = date_idx[ok], bucket[ok], ratio[ok]
    nb = int(bucket.max()) + 1 if len(bucket) else 1
    order = np.lexsort((bucket, date_idx))
    date_idx, bucket, ratio = date_idx[order], bucket[order], ratio[order]
    # per (date, bucket) slice boundaries
    key = date_idx * nb + bucket
    starts = np.searchsorted(key, np.arange(n_dates * nb), side="left")
    ends = np.searchsorted(key, np.arange(n_dates * nb), side="right")
    k = np.full((n_dates, nb), np.nan)
    for b in range(nb):
        for d in range(n_dates):
            lo = max(0, d - trail)
            hi = d  # sessions lo .. d-1
            if hi <= lo:
                lo, hi = d, d + 1  # no past: own session
            parts = [ratio[starts[x * nb + b] : ends[x * nb + b]] for x in range(lo, hi)]
            parts = [p for p in parts if len(p)]
            if parts:
                k[d, b] = float(np.median(np.concatenate(parts)))
    return k


def year_bucket_median(
    year_of_date: np.ndarray,
    date_idx: np.ndarray,
    bucket: np.ndarray,
    ratio: np.ndarray,
    n_dates: int,
) -> np.ndarray:
    """The snapshot rule: median over the whole calendar year of the row's own date."""
    ok = np.isfinite(ratio)
    df = pd.DataFrame({"y": year_of_date[date_idx[ok]], "b": bucket[ok], "r": ratio[ok]})
    med = df.groupby(["y", "b"])["r"].median()
    nb = int(bucket.max()) + 1
    k = np.full((n_dates, nb), np.nan)
    for (y, b), v in med.items():
        k[year_of_date == y, int(b)] = v
    return k


def fallback_mcap(
    close: np.ndarray, shares: np.ndarray, adv: np.ndarray, k_row: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    """The panel SQL ``case`` for ``mcap`` / ``mcap_source`` with a given per-row ratio ``k``."""
    sh_ok = np.isfinite(shares) & (shares > 0)
    adv_pos = np.isfinite(adv) & (adv > 0)
    k_pos = np.isfinite(k_row) & (k_row > 0)
    with np.errstate(invalid="ignore", divide="ignore"):
        ratio = close * shares / adv
    inside = (ratio >= k_row / OUTLIER) & (ratio <= k_row * OUTLIER)
    first = sh_ok & adv_pos & k_pos & inside
    second = sh_ok & np.isfinite(adv) & (adv <= 0)
    mcap = np.where(first, close * shares, np.where(second, close * shares, k_row * adv))
    outlier = adv_pos & k_pos & ~inside
    src = np.where(~sh_ok, "adv_fallback", np.where(outlier, "adv_fallback_outlier", "sec"))
    return mcap, src


def stage_panel() -> dict:
    cal = pd.read_parquet(PANEL_SNAP / "_calendar.parquet")["trade_date"]
    dates = pd.DatetimeIndex(cal)
    pos = {d: i for i, d in enumerate(dates)}
    year_of = dates.year.to_numpy()
    n_dates = len(dates)
    cols = [
        "trade_date",
        "symbol",
        "close",
        "dollar_adv_21",
        "adv_rank",
        "mcap",
        "mcap_source",
        "in_u3000",
    ]
    frames = {}
    di, bk, rt = [], [], []
    for y in YEARS:
        p = PANEL_SNAP / f"{y}.parquet"
        if not p.exists():
            continue
        df = pd.read_parquet(p, columns=cols)
        sec = pd.read_parquet(
            SEC_PIT_DIR / f"{y}.parquet", columns=["symbol", "trade_date", "shares_outstanding"]
        )
        df = df.merge(sec, on=["symbol", "trade_date"], how="left")
        df["di"] = df["trade_date"].map(pos).astype("int64")
        df["bk"] = bucket_of(df["adv_rank"].to_numpy())
        with np.errstate(invalid="ignore", divide="ignore"):
            r = (df["close"] * df["shares_outstanding"] / df["dollar_adv_21"]).to_numpy("float64")
        valid = (df["shares_outstanding"] > 0) & (df["dollar_adv_21"] > 0)
        r = np.where(valid, r, np.nan)
        di.append(df["di"].to_numpy())
        bk.append(df["bk"].to_numpy())
        rt.append(r)
        frames[y] = df
        _log(f"panel {y}: {len(df):,} rows")
    di, bk, rt = np.concatenate(di), np.concatenate(bk), np.concatenate(rt)
    k_year = year_bucket_median(year_of, di, bk, rt, n_dates)
    _log("year medians done")
    k_trail = trailing_bucket_median(di, bk, rt, n_dates)
    _log("trailing medians done")
    PANEL_MCAP_DIR.mkdir(parents=True, exist_ok=True)
    meta = {}
    for y, df in frames.items():
        d_i, b_i = df["di"].to_numpy(), df["bk"].to_numpy()
        close = df["close"].to_numpy("float64")
        sh = df["shares_outstanding"].to_numpy("float64")
        adv = df["dollar_adv_21"].to_numpy("float64")
        out = df[["trade_date", "symbol", "in_u3000", "mcap", "mcap_source"]].rename(
            columns={"mcap": "mcap_snap", "mcap_source": "src_snap"}
        )
        for name, k in (("year", k_year), ("trail", k_trail)):
            m, s = fallback_mcap(close, sh, adv, k[d_i, b_i])
            out[f"mcap_{name}"], out[f"src_{name}"] = m, s
        out = out[out["in_u3000"]].reset_index(drop=True)
        out.to_parquet(PANEL_MCAP_DIR / f"{y}.parquet", index=False)
        fb_snap = out["src_snap"] != "sec"
        meta[y] = {
            "u3000_rows": int(len(out)),
            "fallback_share_snapshot": float(fb_snap.mean()),
            "year_rule_reproduces_snapshot_frac": float(
                np.isclose(out["mcap_year"], out["mcap_snap"], rtol=1e-6).mean()
            ),
            "trail_changes_mcap_frac": float(
                (~np.isclose(out["mcap_trail"], out["mcap_year"], rtol=1e-6)).mean()
            ),
            "trail_changes_source_frac": float((out["src_trail"] != out["src_year"]).mean()),
        }
        _log(f"panel_mcap {y}: {meta[y]}")
    (AUDIT_DIR / "panel_stage_meta.json").write_text(json.dumps(meta, indent=1))
    return meta


# --------------------------------------------------------------------------
# affected signals and themes
# --------------------------------------------------------------------------

SNAP_SIGNALS = ROOT / "data/research/equity_book/signals"
FEAT = ROOT / "data/features"
THEMES_DIR = AUDIT_DIR / "themes"
FLOW_CONCEPTS = {
    "net_income": "ni_a",
    "revenue": "rev_a",
    "operating_cash_flow": "ocf_a",
    "operating_income": "opinc_a",
}
FUND_COLS = [
    "cik",
    "stockholders_equity",
    "total_assets",
    "gross_profitability",
    "roe",
    "accruals",
    "asset_growth",
    "sue_eps",
    "sue_rev",
    "shares_outstanding",
]
AFFECTED = [
    "bm", "ep", "sp", "cfp", "gp_at", "roe", "op_at", "neg_accruals", "neg_asset_growth",
    "sue_eps", "sue_rev", "nonplan_buy_mcap_60d", "neg_beta_252",
]  # fmt: skip
#: variant -> (sec daily dir, mcap column)
VARIANTS = {
    "fin": (SEC_FINAL_DIR, "mcap_year"),  # production rules on the current facts
    "sec": (SEC_PIT_DIR, "mcap_year"),  # + #62 fix
    "pit": (SEC_PIT_DIR, "mcap_trail"),  # + #62 and #63 fixes
}
SIGNAL_YEARS = list(range(2017, 2027))


def load_flows() -> dict[str, pd.DataFrame]:
    from open_composer.research.equity_book import signals as sg

    facts = pd.read_parquet(
        FACTS_COPY,
        columns=[
            "cik",
            "concept",
            "period_end",
            "val",
            "filed",
            "usable_session",
            "period_kind",
            "restated",
        ],
    )
    facts = facts[
        (facts["period_kind"] == "FY")
        & (~facts["restated"])
        & facts["concept"].isin(list(FLOW_CONCEPTS))
    ]
    flows = {}
    for concept, col in FLOW_CONCEPTS.items():
        ev, _ = sg.annual_flow_events(facts[facts["concept"] == concept])
        flows[col] = ev
    return flows


def spy_variance(dates: pd.DatetimeIndex) -> pd.Series:
    etf = pd.read_parquet(
        ROOT / "data/research/equity_book/etf_daily.parquet",
        columns=["trade_date", "symbol", "close"],
    )
    etf = etf[etf["symbol"] == "SPY"].sort_values("trade_date")
    spy = pd.Series(etf["close"].to_numpy(), index=pd.DatetimeIndex(etf["trade_date"]))
    return spy.reindex(dates).pct_change().rolling(252, min_periods=60).var()


def affected_raw(base: pd.DataFrame, sec: pd.DataFrame, mcap: np.ndarray, flows, ins, spy_var):
    """Oriented raw values of the affected signals, built with the production ``signals`` functions
    on the same inputs as ``scripts/build_equity_book_signals.assemble_raw``.  ``base`` is sorted by
    (trade_date, symbol)."""
    from open_composer.research.equity_book import signals as sg

    f = base[["symbol", "trade_date"]].merge(
        sec[["symbol", "trade_date", *FUND_COLS]], on=["symbol", "trade_date"], how="left"
    )
    f["mcap"] = mcap
    for col, ev in flows.items():
        f[col] = sg.annual_flow_asof(ev, f["cik"], f["trade_date"])
    fr = sg.fundamental_raw(f)
    raw = pd.DataFrame(index=base.index)
    for c in (
        "bm",
        "ep",
        "sp",
        "cfp",
        "gp_at",
        "roe",
        "op_at",
        "neg_accruals",
        "neg_asset_growth",
        "sue_eps",
        "sue_rev",
    ):
        raw[c] = fr[c].to_numpy()
    i = base[["symbol", "trade_date"]].merge(ins, on=["symbol", "trade_date"], how="left")
    raw["nonplan_buy_mcap_60d"] = sg.insider_raw(i, mcap, i["trade_date"])[
        "nonplan_buy_mcap_60d"
    ].to_numpy()
    nb, _ = sg.lowrisk_raw(
        base["trade_date"], base["beta_252_spy"].to_numpy("float64"),
        base["idio_vol_63"].to_numpy("float64"), mcap, spy_var,
    )  # fmt: skip
    raw["neg_beta_252"] = nb
    return raw.replace([np.inf, -np.inf], np.nan)


def stage_signals(years: list[int] | None = None, variants: list[str] | None = None) -> None:
    import pyarrow.parquet as pq
    from build_book_v1_alpha import theme_scores

    from open_composer.research.equity_book import signals as sg
    from open_composer.research.equity_book.signals import THEMES

    THEMES_DIR.mkdir(parents=True, exist_ok=True)
    flows = load_flows()
    cal = pd.DatetimeIndex(pd.read_parquet(PANEL_SNAP / "_calendar.parquet")["trade_date"])
    spy_var = spy_variance(cal)
    specs = [s for s in sg.SLOW_SIGNALS if s.name in AFFECTED]
    for y in years or SIGNAL_YEARS:
        t0 = time.time()
        snap_cols = [
            "trade_date",
            "symbol",
            "ind_code",
            *sg.SLOW_NAMES,
            *[f"theme_{t}" for t in THEMES],
            "m0_composite",
        ]
        snap = pq.read_table(SNAP_SIGNALS / f"{y}.parquet", columns=snap_cols).to_pandas()
        snap = snap.sort_values(["trade_date", "symbol"], kind="stable").reset_index(drop=True)
        pan = pd.read_parquet(
            PANEL_SNAP / f"{y}.parquet",
            columns=["trade_date", "symbol", "in_u3000", "in_p1000", "beta_252_spy", "idio_vol_63"],
        )
        mc = pd.read_parquet(PANEL_MCAP_DIR / f"{y}.parquet")
        base = snap[["trade_date", "symbol"]].merge(pan, on=["trade_date", "symbol"], how="left")
        base = base.merge(
            mc[["trade_date", "symbol", "mcap_year", "mcap_trail"]],
            on=["trade_date", "symbol"], how="left",
        )  # fmt: skip
        assert len(base) == len(snap), (
            "snapshot signal rows must be a subset of in_u3000 panel rows"
        )
        icols = pd.read_parquet(FEAT / "insider_broad" / f"{y}.parquet").columns
        nb_col = (
            "net_buy_usd_nonplan_60d" if "net_buy_usd_nonplan_60d" in icols else "net_buy_usd_60d"
        )
        ins = pd.read_parquet(
            FEAT / "insider_broad" / f"{y}.parquet",
            columns=["symbol", "trade_date", "visible_at", "cmp_opportunistic_buy_60d", nb_col],
        ).rename(columns={nb_col: "net_buy_usd_nonplan_60d"})
        ins = ins.drop_duplicates(["symbol", "trade_date"], keep="last")
        for v, (sec_dir, mcol) in VARIANTS.items():
            if variants and v not in variants:
                continue
            sec = pd.read_parquet(
                sec_dir / f"{y}.parquet", columns=["symbol", "trade_date", *FUND_COLS]
            )
            sec = sec.drop_duplicates(["symbol", "trade_date"], keep="last")
            raw = affected_raw(base, sec, base[mcol].to_numpy("float64"), flows, ins, spy_var)
            fr = pd.concat([snap[["trade_date", "symbol", "ind_code"]], raw], axis=1)
            proc = sg.process_frame(fr, specs)
            z = snap[list(sg.SLOW_NAMES)].copy()
            for name in AFFECTED:
                z[name] = proc[name].to_numpy()
            th = theme_scores(z)
            out = snap[["trade_date", "symbol"]].copy()
            out["in_u3000"] = base["in_u3000"].fillna(False).to_numpy()
            out["in_p1000"] = base["in_p1000"].fillna(False).to_numpy()
            for t in THEMES:
                out[t] = th[t].to_numpy()
            out["m0"] = th[list(THEMES)].astype("float64").mean(axis=1).astype("float32").to_numpy()
            for name in AFFECTED:
                out[f"z_{name}"] = proc[name].to_numpy()
                out[f"raw_{name}"] = proc[f"{name}_raw"].to_numpy()
            out.to_parquet(THEMES_DIR / f"{v}_{y}.parquet", index=False)
            del sec, raw, fr, proc, z, th, out
        _log(f"signals {y}: {len(base):,} rows, {time.time() - t0:.0f}s")


# --------------------------------------------------------------------------
# stage 1: formation IC and rank correlations
# --------------------------------------------------------------------------

WINDOWS = {"recent": ("2024-01-08", "2026-09-15"), "stress": ("2017-10-02", "2023-08-31")}
ALL_VARIANTS = ("snap", "pit")  # "fin" / "sec" (attribution) only where files exist


def load_variant_year(v: str, y: int, columns: list[str] | None = None) -> pd.DataFrame:
    if v == "snap":
        from open_composer.research.equity_book.signals import THEMES

        cols = ["trade_date", "symbol", *[f"theme_{t}" for t in THEMES], "m0_composite"]
        df = pd.read_parquet(SNAP_SIGNALS / f"{y}.parquet", columns=cols)
        df = df.rename(columns={f"theme_{t}": t for t in THEMES} | {"m0_composite": "m0"})
        df = df.sort_values(["trade_date", "symbol"], kind="stable").reset_index(drop=True)
        pan = pd.read_parquet(
            PANEL_SNAP / f"{y}.parquet", columns=["trade_date", "symbol", "in_u3000"]
        )
        return df.merge(pan, on=["trade_date", "symbol"], how="left")
    return pd.read_parquet(THEMES_DIR / f"{v}_{y}.parquet", columns=columns)


def stage_ic() -> None:
    import build_book_v1_alpha as bv

    from open_composer.research.equity_book import optimize as op
    from open_composer.research.equity_book.panel import PricePanel
    from open_composer.research.equity_book.returns import forward_open_to_open
    from open_composer.research.equity_book.risk import RiskModel
    from open_composer.research.equity_book.signals import THEMES

    rm = RiskModel()
    panel = PricePanel.from_dir(start="2016-09-01")
    dates = panel.dates
    fr = bv.factor_return_matrix(rm.factors)
    me_pos = bv.month_end_positions(dates)
    last_pos = len(dates) - 1
    first_sig = pd.Timestamp(
        pd.read_parquet(SNAP_SIGNALS / "2017.parquet", columns=["trade_date"])["trade_date"].min()
    )
    form = [
        int(p) for p in me_pos
        if dates[p] >= first_sig.to_period("M").to_timestamp() and p + bv.HORIZON <= last_pos
    ]  # fmt: skip
    rows = []
    for y in SIGNAL_YEARS:
        fy = [p for p in form if dates[p].year == y]
        if not fy:
            continue
        wanted = {dates[p] for p in fy}
        per_v = {}
        for v in ALL_VARIANTS:
            df = load_variant_year(v, y, columns=["trade_date", "symbol", "in_u3000", *THEMES])
            df = df[df["trade_date"].isin(wanted)]
            per_v[v] = {d: g.set_index("symbol") for d, g in df.groupby("trade_date")}
            del df
        for p in fy:
            d = dates[p]
            try:
                x_df, _, _ = rm.at(d, exact=True)
            except KeyError:
                continue
            names = [s for s in x_df.index if panel.has(s)]
            cols = np.array([panel.col(s) for s in names], dtype=int)
            x = x_df.loc[names].to_numpy("float64")
            f_win = fr.reindex(dates[p + 1 : p + bv.HORIZON]).to_numpy("float64")
            fwd = forward_open_to_open(
                panel.open[p + 1 : p + bv.HORIZON + 1][:, cols],
                panel.close[p + 1 : p + bv.HORIZON + 1][:, cols],
                0, bv.HORIZON - 1,
            )  # fmt: skip
            yv = pd.Series(fwd - x @ np.nansum(f_win, axis=0), index=names)
            for v in ALL_VARIANTS:
                g = per_v[v].get(d)
                if g is None:
                    continue
                members = g.index[g["in_u3000"].fillna(False).to_numpy()].intersection(yv.index)
                if len(members) < bv.MIN_NAMES:
                    continue
                sub = g.loc[members, list(THEMES)].astype("float64")
                yy = yv.loc[members].to_numpy()
                for t in THEMES:
                    ic, n = bv.rank_ic(sub[t].to_numpy(), yy)
                    rows.append({"formation_date": d, "variant": v, "series": t, "ic": ic, "n": n})
                eq = sub.mean(axis=1)
                ic0, n0 = bv.rank_ic(op.rank_normal(eq).to_numpy(), yy)
                rows.append({"formation_date": d, "variant": v, "series": "M0", "ic": ic0, "n": n0})
        _log(f"ic {y}: {len(rows)} rows")
    pd.DataFrame(rows).to_parquet(AUDIT_DIR / "formation_ic_variants.parquet", index=False)


def spearman_by_date(a: np.ndarray, b: np.ndarray, dates: np.ndarray) -> pd.Series:
    from scipy.stats import rankdata

    cuts = np.flatnonzero(np.r_[True, dates[1:] != dates[:-1], True])
    out = {}
    for lo, hi in zip(cuts[:-1], cuts[1:], strict=True):
        x, y = a[lo:hi], b[lo:hi]
        ok = np.isfinite(x) & np.isfinite(y)
        if ok.sum() < 30:
            continue
        rx, ry = rankdata(x[ok]), rankdata(y[ok])
        rx, ry = rx - rx.mean(), ry - ry.mean()
        den = float(np.sqrt((rx * rx).sum() * (ry * ry).sum()))
        out[dates[lo]] = float((rx * ry).sum() / den) if den > 0 else np.nan
    return pd.Series(out)


def stage_corr_counts() -> dict:
    """Per-year changed-row counts and per-date Spearman correlations between variants.  Pairs
    involving ``fin`` / ``sec`` are computed for the years where those files exist."""
    import pyarrow.parquet as pq

    from open_composer.research.equity_book.signals import THEMES

    all_pairs = [("snap", "pit"), ("snap", "fin"), ("fin", "sec"), ("sec", "pit")]
    counts: dict = {}
    corr_rows = []
    for y in SIGNAL_YEARS:
        have = {v: (THEMES_DIR / f"{v}_{y}.parquet").exists() for v in ("fin", "sec", "pit")}
        if not have["pit"]:
            continue
        z = {v: load_variant_year(v, y) for v, ok in have.items() if ok}
        snap_raw = (
            pq.read_table(
                SNAP_SIGNALS / f"{y}.parquet",
                columns=["trade_date", "symbol", *[f"{n}_raw" for n in AFFECTED], *AFFECTED],
            )
            .to_pandas()
            .sort_values(["trade_date", "symbol"], kind="stable")
            .reset_index(drop=True)
        )
        snap = load_variant_year("snap", y)
        dates = z["pit"]["trade_date"].to_numpy()
        for a, b in all_pairs:
            if (a != "snap" and a not in z) or b not in z:
                continue
            ra = snap_raw if a == "snap" else z[a]
            rb = z[b]
            entry = {}
            for name in AFFECTED:
                xa = ra[f"{name}_raw" if a == "snap" else f"raw_{name}"].to_numpy("float64")
                xb = rb[f"raw_{name}"].to_numpy("float64")
                both_nan = ~np.isfinite(xa) & ~np.isfinite(xb)
                with np.errstate(invalid="ignore"):
                    diff = ~both_nan & ~(np.abs(xa - xb) <= 1e-6 * np.maximum(1e-12, np.abs(xa)))
                entry[name] = {
                    "rows": int(diff.sum()),
                    "symbols": int(rb.loc[diff, "symbol"].nunique()),
                    "cov_changed_rows": int((np.isfinite(xa) != np.isfinite(xb)).sum()),
                }
            entry["n_rows"] = int(len(rb))
            counts.setdefault(f"{a}->{b}", {})[y] = entry
        for a in ("snap", "fin"):
            if a != "snap" and a not in z:
                continue
            ra = snap if a == "snap" else z[a]
            rb = z["pit"]
            for t in (*THEMES, "m0"):
                sr = spearman_by_date(ra[t].to_numpy("float64"), rb[t].to_numpy("float64"), dates)
                for d, c in sr.items():
                    corr_rows.append({"pair": f"{a}->pit", "series": t, "trade_date": d, "rho": c})
            if a == "snap":
                for name in AFFECTED:
                    sr = spearman_by_date(
                        snap_raw[name].to_numpy("float64"),
                        rb[f"z_{name}"].to_numpy("float64"),
                        dates,
                    )
                    for d, c in sr.items():
                        corr_rows.append(
                            {"pair": "snap->pit", "series": f"z_{name}", "trade_date": d, "rho": c}
                        )
        _log(f"corr {y}")
    pd.DataFrame(corr_rows).to_parquet(AUDIT_DIR / "corr_by_date.parquet", index=False)
    (AUDIT_DIR / "changed_counts.json").write_text(json.dumps(counts, indent=1))
    return counts


def window_mask(d: pd.Series, window: tuple[str, str]) -> pd.Series:
    return (d >= pd.Timestamp(window[0])) & (d <= pd.Timestamp(window[1]))


def stage_stage1() -> dict:
    from open_composer.research.equity_book.signals import THEMES

    counts = json.loads((AUDIT_DIR / "changed_counts.json").read_text())
    corr = pd.read_parquet(AUDIT_DIR / "corr_by_date.parquet")
    ic = pd.read_parquet(AUDIT_DIR / "formation_ic_variants.parquet")
    res: dict = {"windows": WINDOWS, "changed_counts": counts}
    # per-series correlation summaries (all dates, and by window)
    summ = {}
    for (pair, series), g in corr.groupby(["pair", "series"]):
        e = {
            "all": {
                "median": float(g["rho"].median()),
                "p5": float(g["rho"].quantile(0.05)),
                "min": float(g["rho"].min()),
                "n_dates": int(len(g)),
            }
        }
        for w, rng in WINDOWS.items():
            gw = g[window_mask(g["trade_date"], rng)]
            if len(gw):
                e[w] = {"median": float(gw["rho"].median()), "p5": float(gw["rho"].quantile(0.05))}
        summ.setdefault(pair, {})[series] = e
    res["rank_corr"] = summ
    # formation IC by window
    icres: dict = {}
    for w, rng in WINDOWS.items():
        sub = ic[window_mask(ic["formation_date"], rng)]
        piv = sub.pivot_table(index="series", columns="variant", values="ic", aggfunc="mean")
        n = sub[sub["variant"] == "snap"].groupby("series").size()
        icres[w] = {
            ser: {
                **{v: float(piv.loc[ser, v]) for v in ALL_VARIANTS if v in piv.columns},
                "n_dates": int(n.get(ser, 0)),
                "d_pit_snap": float(piv.loc[ser, "pit"] - piv.loc[ser, "snap"]),
            }
            for ser in [*THEMES, "M0"]
        }
    res["formation_ic"] = icres
    # frozen gate (reports/research/program/pit-audit-2026-10-04/gate.json)
    g1 = []
    for w in WINDOWS:
        m0 = icres[w]["M0"]
        d = abs(m0["d_pit_snap"])
        rel = d / abs(m0["snap"]) if m0["snap"] else float("inf")
        if d >= 0.003 or rel >= 0.10:
            g1.append(f"M0 mean IC change in {w}: abs {d:.5f}, rel {rel:.3f}")
        for t in THEMES:
            dt = abs(icres[w][t]["d_pit_snap"])
            if dt >= 0.005:
                g1.append(f"theme {t} IC change in {w}: {dt:.5f}")
    p5 = summ["snap->pit"]["m0"]["all"]["p5"]
    if p5 < 0.98:
        g1.append(f"M0 composite rank corr p5 {p5:.4f} < 0.98")
    res["gate"] = {"opens": bool(g1), "reasons": g1, "m0_rank_corr_p5_all": p5}
    (REPORT_DIR / "stage1.json").write_text(json.dumps(res, indent=1))
    return res


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "stage", choices=["sec", "validate-sec", "panel", "signals", "ic", "corr", "stage1"]
    )
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--years", default=None, help="e.g. 2018-2026 (signals)")
    ap.add_argument("--variants", default=None, help="e.g. pit or fin,sec (signals)")
    args = ap.parse_args()
    # the book readers (RiskModel, PricePanel) must read the frozen snapshot, never the live root;
    # nothing in this script writes there
    os.environ["OC_EQUITY_BOOK_DIR"] = str(ROOT / "data/research/equity_book")
    if args.stage == "sec":
        stage_sec(args.limit)
    elif args.stage == "validate-sec":
        stage_validate_sec()
    elif args.stage == "panel":
        stage_panel()
    elif args.stage == "signals":
        yrs = None
        if args.years:
            a, _, b = args.years.partition("-")
            yrs = list(range(int(a), int(b or a) + 1))
        stage_signals(yrs, args.variants.split(",") if args.variants else None)
    elif args.stage == "ic":
        stage_ic()
    elif args.stage == "corr":
        stage_corr_counts()
    elif args.stage == "stage1":
        stage_stage1()
    else:
        raise SystemExit(f"stage {args.stage} not implemented yet")


if __name__ == "__main__":
    main()
