# ruff: noqa: E501
"""Build the equity-book signal library v1 (design section 4; ``equity_book/signals.py``).

Output ``data/research/equity_book/signals/<year>.parquet`` (long, U3000 members, every session; per
signal ``<name>_raw`` / ``<name>`` / ``<name>_cov``, theme scores, ``m0_composite``) plus
``_coverage_<year>.json`` and ``_alpha_columns.json``.  One row group per chunk of months; the build
is resumable per year (an existing year file is skipped unless ``--force``).

Stages::

    alpha-cols   coverage of every alpha101 / alpha191 column in U3000 from 2017 on; keeps >= 90%
    build        the signal files (needs alpha-cols)
    report       measurement report -> reports/research/program/signals-v1-2026-10-01/

Run (capped)::

    scripts/run_capped.sh --mem 1.8G -- uv run python scripts/build_equity_book_signals.py alpha-cols
    scripts/run_capped.sh --mem 1.8G -- uv run python scripts/build_equity_book_signals.py build
    scripts/run_capped.sh --mem 1.8G -- uv run python scripts/build_equity_book_signals.py report
"""

from __future__ import annotations

import argparse
import json
import resource
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from open_composer.research.equity_book import risk as rk  # noqa: E402
from open_composer.research.equity_book import signals as sg  # noqa: E402
from open_composer.research.equity_book.panel import DEFAULT_DIR, PricePanel  # noqa: E402
from open_composer.research.equity_book.returns import forward_open_to_open  # noqa: E402

FEAT = ROOT / "data/features"
PANEL = DEFAULT_DIR / "panel"
OUT = sg.SIGNALS_DIR
FACTS = FEAT / "sec_fundamentals/facts.parquet"
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
WARMUP = 260  # sessions of price history loaded before the first session of a year
MIN_ALPHA_COVERAGE = 0.90
FIRST_YEAR = 2017


def _log(msg: str) -> None:
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
    print(f"[{time.strftime('%H:%M:%S')}] (peak {rss:.0f} MB) {msg}", flush=True)


def _duck():
    import duckdb

    con = duckdb.connect()
    con.execute("SET memory_limit='600MB'")
    con.execute("SET threads=2")
    return con


def _ns(s: pd.Series) -> pd.Series:
    return pd.to_datetime(s).astype("datetime64[ns]")


# ---------------------------------------------------------------------------
# alpha columns
# ---------------------------------------------------------------------------


def stage_alpha_cols() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    con = _duck()
    result: dict = {"min_coverage": MIN_ALPHA_COVERAGE, "from_year": FIRST_YEAR, "tables": {}}
    for table, key in (("alpha101_broad", "alpha101"), ("alpha191_broad", "alpha191")):
        files = sorted((FEAT / table).glob("20*.parquet"))
        cols = [
            r[0]
            for r in con.execute(f"describe select * from read_parquet('{files[0]}')").fetchall()
            if r[0] not in ("symbol", "trade_date")
        ]
        num = {c: 0 for c in cols}
        den = 0
        for f in files:
            y = int(f.stem)
            if y < FIRST_YEAR:
                continue
            sel = ", ".join(f"sum((isfinite(a.{c}))::int)" for c in cols)
            row = con.execute(
                f"""select count(*), {sel}
                    from read_parquet('{PANEL / f"{y}.parquet"}') p
                    left join read_parquet('{f}') a using (symbol, trade_date)
                    where p.in_u3000"""
            ).fetchone()
            den += int(row[0])
            for c, v in zip(cols, row[1:], strict=True):
                num[c] += int(v or 0)
            _log(f"{table} {y} rows {row[0]}")
        cov = {c: num[c] / den for c in cols}
        kept = [c for c in cols if cov[c] >= MIN_ALPHA_COVERAGE]
        result["tables"][key] = {"rows": den, "coverage": cov, "kept": kept}
    result["kept"] = {k: v["kept"] for k, v in result["tables"].items()}
    (OUT / "_alpha_columns.json").write_text(json.dumps(result, indent=1))
    _log(
        "kept "
        + ", ".join(
            f"{k}: {len(v['kept'])}/{len(v['coverage'])}" for k, v in result["tables"].items()
        )
    )


# ---------------------------------------------------------------------------
# build
# ---------------------------------------------------------------------------


class Context:
    """Everything that is loaded once: calendar, industry map, facts events, seasonality table,
    SPY variance."""

    def __init__(self, alpha_cols: dict[str, list[str]], light: bool = False) -> None:
        self.con = _duck()
        self.alpha_cols = alpha_cols
        self.specs = sg.all_specs(alpha_cols)
        cal = pd.read_parquet(PANEL / "_calendar.parquet")
        self.dates = pd.DatetimeIndex(cal["trade_date"])
        self.mapping, self.groups = sg.load_industry_groups()
        self.flows: dict[str, pd.DataFrame] = {}
        self.dropped_facts = 0
        facts = self.con.execute(
            f"""select cik, concept, period_end, val, filed, usable_session
                from read_parquet('{FACTS}')
                where period_kind = 'FY' and not restated
                  and concept in ({", ".join(repr(c) for c in FLOW_CONCEPTS)})"""
        ).df()
        for concept, col in FLOW_CONCEPTS.items():
            ev, bad = sg.annual_flow_events(facts[facts["concept"] == concept])
            self.flows[col] = ev
            self.dropped_facts += bad
        del facts
        if light:
            return
        etf = self.con.execute(
            f"select trade_date, close from read_parquet('{DEFAULT_DIR / 'etf_daily.parquet'}') "
            "where symbol = 'SPY' order by trade_date"
        ).df()
        spy = pd.Series(etf["close"].to_numpy(), index=pd.DatetimeIndex(etf["trade_date"]))
        spy = spy.reindex(self.dates)
        self.spy_var = spy.pct_change().rolling(252, min_periods=60).var()
        self.ever = (
            self.con.execute(
                f"select distinct symbol from read_parquet('{PANEL}/20*.parquet') where in_u3000 order by 1"
            )
            .df()["symbol"]
            .tolist()
        )
        pp = PricePanel.from_dir(symbols=self.ever, include_etfs=False, load_open=False)
        me = sg.month_end_closes(pp.close, pp.dates)
        me.columns = pp.symbols
        del pp
        self.mret = sg.monthly_returns(me)
        del me
        self._seas: dict[tuple[int, int], pd.Series] = {}

    def seas(self, y: int, m: int) -> pd.Series:
        if (y, m) not in self._seas:
            self._seas[(y, m)] = sg.seasonality(self.mret, y, m)
        return self._seas[(y, m)]

    def next_session(self, d: pd.Timestamp) -> pd.Timestamp:
        i = self.dates.searchsorted(d)
        if i + 1 < len(self.dates):
            return self.dates[i + 1]
        return d + pd.offsets.BDay(1)


def join_table(
    con, path: Path, base: pd.DataFrame, cols: list[str], extra: list[str] | None = None
) -> pd.DataFrame:
    """Left join ``cols`` of a (symbol, trade_date) parquet onto ``base`` (symbol, trade_date)."""
    if not path.exists():
        return pd.DataFrame(columns=["symbol", "trade_date", *cols, *(extra or [])])
    con.register("base_keys", base[["symbol", "trade_date"]])
    sel = ", ".join(f"t.{c}" for c in [*cols, *(extra or [])])
    df = con.execute(
        f"""select b.symbol, b.trade_date, {sel}
            from base_keys b join read_parquet('{path}') t
              on t.symbol = b.symbol and t.trade_date = b.trade_date"""
    ).df()
    con.unregister("base_keys")
    df["trade_date"] = _ns(df["trade_date"])
    return df.drop_duplicates(["symbol", "trade_date"], keep="last")


def build_year(ctx: Context, year: int, chunk_months: int, force: bool) -> None:
    path = OUT / f"{year}.parquet"
    if path.exists() and not force:
        _log(f"{year}: exists, skipped")
        return
    import pyarrow as pa
    import pyarrow.parquet as pq

    t0 = time.time()
    con = ctx.con
    panel = con.execute(
        f"""select trade_date, symbol, close, mcap, mcap_source, ff48, beta_252_spy, idio_vol_63
            from read_parquet('{PANEL / f"{year}.parquet"}') where in_u3000
            order by trade_date, symbol"""
    ).df()
    panel["trade_date"] = _ns(panel["trade_date"])
    panel["ind_code"] = sg.industry_codes(panel["ff48"], ctx.mapping, ctx.groups)
    symbols = sorted(panel["symbol"].unique())
    first_pos = int(ctx.dates.searchsorted(panel["trade_date"].min()))
    start = ctx.dates[max(first_pos - WARMUP, 0)]
    end = panel["trade_date"].max()

    # ---- wide price signals for the year ----------------------------------
    pp = PricePanel.from_dir(
        symbols=symbols, include_etfs=False, start=str(start.date()), end=str(end.date())
    )
    dates, syms = pp.dates, pp.symbols
    close, open_ = pp.close, pp.open
    mom = sg.momentum_matrix(close)
    rev21 = sg.return_matrix(close, 21)
    on252 = sg.rolling_mean_min_obs(sg.overnight_matrix(open_, close), 252, 200)
    ret1 = sg.return_matrix(close, 1)
    del open_
    # static group of each column for the fallback residuals (first group seen in the year)
    first_grp = panel.drop_duplicates("symbol", keep="first").set_index("symbol")["ind_code"]
    gcol = first_grp.reindex(syms).fillna(-1).to_numpy("int64")
    fb = sg.group_demeaned_returns(ret1, gcol, sg.MIN_INDUSTRY_MEMBERS)
    del ret1
    resid = np.full(close.shape, np.nan)
    for ry in range(year - 2, year + 1):
        rp = RISK_RES.format(y=ry)
        if not Path(rp).exists():
            continue
        r = pd.read_parquet(rp)
        ri = dates.get_indexer(pd.DatetimeIndex(r["trade_date"]))
        ci = syms.get_indexer(r["symbol"].astype(str))
        ok = (ri >= 0) & (ci >= 0)
        resid[ri[ok], ci[ok]] = r["resid"].to_numpy("float64")[ok]
        del r
    rmom, used_fb = sg.resid_momentum(resid, fb)
    del resid, fb
    row_i = dates.get_indexer(pd.DatetimeIndex(panel["trade_date"]))
    col_i = syms.get_indexer(panel["symbol"].astype(str))
    ok = (row_i >= 0) & (col_i >= 0)
    ri_, ci_ = np.where(ok, row_i, 0), np.where(ok, col_i, 0)

    def gather(a: np.ndarray) -> np.ndarray:
        return np.where(ok, a[ri_, ci_], np.nan)

    panel["mom_12_1"] = gather(mom)
    panel["rev21"] = gather(rev21)
    panel["on252"] = gather(on252)
    panel["resid_mom_12_1"] = gather(rmom)
    panel["resid_mom_fallback"] = np.where(ok, used_fb[ri_, ci_], False) & np.isfinite(
        panel["resid_mom_12_1"]
    )
    del mom, rev21, on252, rmom, used_fb, close, pp
    _log(f"{year}: wide signals done, {len(panel):,} rows, {len(symbols)} symbols")

    # ---- chunks -----------------------------------------------------------
    months = sorted(panel["trade_date"].dt.month.unique())
    groups = [months[i : i + chunk_months] for i in range(0, len(months), chunk_months)]
    tmp = path.with_suffix(".parquet.tmp")
    writer = None
    cov_sum: dict[str, int] = {}
    n_rows = 0
    for g in groups:
        base = panel[panel["trade_date"].dt.month.isin(g)].reset_index(drop=True)
        raw = assemble_raw(ctx, year, base)
        out = sg.process_frame(raw, ctx.specs)
        table = pa.Table.from_pandas(out, preserve_index=False)
        if writer is None:
            writer = pq.ParquetWriter(tmp, table.schema, compression="zstd")
        writer.write_table(table.cast(writer.schema))
        n_rows += len(out)
        for c in out.columns:
            if c.endswith("_cov") or c == "resid_mom_12_1_fallback":
                cov_sum[c] = cov_sum.get(c, 0) + int(out[c].sum())
        cov_sum["m0_themes_ge6"] = cov_sum.get("m0_themes_ge6", 0) + int(
            (out["m0_n_themes"] >= 6).sum()
        )
        _log(f"{year}: months {g} -> {len(out):,} rows")
        del base, raw, out, table
    writer.close()
    tmp.replace(path)
    cov = {k: v / max(n_rows, 1) for k, v in cov_sum.items()}
    meta = {
        "rows": n_rows,
        "symbols": len(symbols),
        "dates": int(panel["trade_date"].nunique()),
        "coverage": cov,
        "seconds": round(time.time() - t0, 1),
        "dropped_fact_rows_total": ctx.dropped_facts,
    }
    (OUT / f"_coverage_{year}.json").write_text(json.dumps(meta, indent=1))
    _log(f"{year}: wrote {path.name} ({n_rows:,} rows) in {time.time() - t0:.0f}s")


RISK_RES = str(rk.RISK_DIR / "residuals_{y}.parquet")


def assemble_raw(ctx: Context, year: int, base: pd.DataFrame) -> pd.DataFrame:
    """Oriented raw signals for the rows of ``base`` (already sorted by date, symbol)."""
    con = ctx.con
    raw = base[["trade_date", "symbol", "ind_code", "resid_mom_fallback"]].copy()
    td = base["trade_date"]
    mcap = base["mcap"].to_numpy("float64")

    # fundamentals (aligned to the first session after the filing) + annual flows from the facts
    f = join_table(con, FEAT / "sec_fundamentals_daily" / f"{year}.parquet", base, FUND_COLS)
    f = base[["symbol", "trade_date", "mcap"]].merge(f, on=["symbol", "trade_date"], how="left")
    for col, ev in ctx.flows.items():
        f[col] = sg.annual_flow_asof(ev, f["cik"], f["trade_date"])
    fr = sg.fundamental_raw(f)
    for c in fr.columns:
        raw[c] = fr[c].to_numpy()

    # investment: nsi
    nsi = join_table(con, FEAT / "nsi" / "nsi.parquet", base, ["nsi252"])
    n = base[["symbol", "trade_date"]].merge(nsi, on=["symbol", "trade_date"], how="left")
    raw["neg_nsi_12m"] = -n["nsi252"].to_numpy("float64")

    # momentum
    raw["mom_12_1"] = base["mom_12_1"].to_numpy()
    raw["resid_mom_12_1"] = base["resid_mom_12_1"].to_numpy()
    gm = sg.group_mean(base["mom_12_1"], td, base["ind_code"].to_numpy(), sg.MIN_INDUSTRY_MEMBERS)
    raw["ind_mom_12_1"] = np.where(np.isfinite(base["mom_12_1"]), gm, np.nan)

    # low risk
    nb, niv = sg.lowrisk_raw(
        td,
        base["beta_252_spy"].to_numpy("float64"),
        base["idio_vol_63"].to_numpy("float64"),
        mcap,
        ctx.spy_var,
    )
    raw["neg_beta_252"] = nb
    raw["neg_idio_vol_63"] = niv

    # insider
    ipath = FEAT / "insider_broad" / f"{year}.parquet"
    icols = [
        r[0] for r in con.execute(f"describe select * from read_parquet('{ipath}')").fetchall()
    ]
    # the Form 4 10b5-1 checkbox exists from 2023; earlier years: every open-market trade is "non-plan"
    nb_col = "net_buy_usd_nonplan_60d" if "net_buy_usd_nonplan_60d" in icols else "net_buy_usd_60d"
    ins = join_table(con, ipath, base, ["visible_at", "cmp_opportunistic_buy_60d", nb_col])
    ins = ins.rename(columns={nb_col: "net_buy_usd_nonplan_60d"})
    i = base[["symbol", "trade_date", "mcap"]].merge(ins, on=["symbol", "trade_date"], how="left")
    ir = sg.insider_raw(i, i["mcap"].to_numpy("float64"), i["trade_date"])
    for c in ir.columns:
        raw[c] = ir[c].to_numpy()

    # short information
    sv = join_table(
        con,
        FEAT / "short_volume_broad" / f"{year}.parquet",
        base,
        ["visible_date", "short_volume_ratio_mean_21"],
    )
    s = base[["symbol", "trade_date"]].merge(sv, on=["symbol", "trade_date"], how="left")
    raw["neg_short_vol_ratio_21"] = sg.short_volume_raw(s, s["trade_date"])
    si = join_table(
        con,
        FEAT / "short_interest" / f"{year}.parquet",
        base,
        ["visible_date", "short_interest_shares"],
    )
    s2 = base[["symbol", "trade_date"]].merge(si, on=["symbol", "trade_date"], how="left")
    raw["neg_si_shares"] = sg.short_interest_raw(
        s2, f["shares_outstanding"].to_numpy("float64"), s2["trade_date"]
    )

    # seasonality: the calendar month of the next session, mean of the same month in the last 5 years
    seas = np.full(len(base), np.nan)
    nxt = {d: ctx.next_session(d) for d in td.unique()}
    tgt = pd.DataFrame(
        {
            "y": td.map(lambda d: nxt[d].year).to_numpy(),
            "m": td.map(lambda d: nxt[d].month).to_numpy(),
        }
    )
    syms_arr = base["symbol"].to_numpy()
    for (ty, tm), idx in tgt.groupby(["y", "m"]).indices.items():
        seas[idx] = ctx.seas(int(ty), int(tm)).reindex(syms_arr[idx]).to_numpy("float64")
    raw["seas_5y"] = seas

    # fast signals
    rev = base["rev21"]
    gmr = sg.group_mean(rev, td, base["ind_code"].to_numpy(), sg.MIN_INDUSTRY_MEMBERS)
    raw["rev_21_ind"] = -(rev.to_numpy() - gmr)
    raw["on252"] = base["on252"].to_numpy()
    nw = join_table(
        con, FEAT / "news_attention" / f"{year}.parquet", base, ["visible_at", "attention_surge_5d"]
    )
    nn = base[["symbol", "trade_date"]].merge(nw, on=["symbol", "trade_date"], how="left")
    raw["news_attention"] = (
        sg.news_raw(nn, nn["trade_date"]) if len(nw) else np.full(len(base), np.nan)
    )
    for table, key, prefix in (
        ("alpha101_broad", "alpha101", "a101_"),
        ("alpha191_broad", "alpha191", "g191_"),
    ):
        cols = ctx.alpha_cols.get(key, [])
        if not cols:
            continue
        a = join_table(con, FEAT / table / f"{year}.parquet", base, cols)
        aa = base[["symbol", "trade_date"]].merge(a, on=["symbol", "trade_date"], how="left")
        for c in cols:
            v = aa[c].to_numpy("float64")
            raw[prefix + c] = np.where(np.isfinite(v), v, np.nan)
    raw = raw.replace([np.inf, -np.inf], np.nan)
    return raw


def stage_build(years: list[int], chunk_months: int, force: bool) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    ac = json.loads((OUT / "_alpha_columns.json").read_text())["kept"]
    ctx = Context(ac)
    _log(
        f"context ready: {len(ctx.specs)} signals, {len(ctx.ever)} ever-U3000 symbols, facts guard dropped {ctx.dropped_facts}"
    )
    for y in years:
        build_year(ctx, y, chunk_months, force)


# ---------------------------------------------------------------------------
# report
# ---------------------------------------------------------------------------

STRESS = ("2017-10-02", "2023-08-31")
ANCHOR = ("2024-01-08", "2026-08-15")
FULL = ("2017-01-03", "2026-08-15")
HORIZON = 21
REPORT_DIR = ROOT / "reports/research/program/signals-v1-2026-10-01"
SPLIT_FLAG_HI, SPLIT_FLAG_LO = 1.8, 0.55  # latest / as-filed share count at t outside -> flagged


def iter_signal_dates(columns: list[str]):
    """Yield ``(date, frame)`` for every session in file order; frames hold ``trade_date``,
    ``symbol``, ``ind_code`` and ``columns``."""
    import pyarrow.parquet as pq

    keys = ["trade_date", "symbol", "ind_code"]
    for f in sorted(OUT.glob("20*.parquet")):
        pf = pq.ParquetFile(f)
        for g in range(pf.num_row_groups):
            df = pf.read_row_group(g, columns=keys + columns).to_pandas()
            for d, sub in df.groupby("trade_date", sort=True):
                yield pd.Timestamp(d), sub.reset_index(drop=True)


def demean_by_group(r: np.ndarray, codes: np.ndarray) -> np.ndarray:
    """Return minus the equal-weighted mean of its industry group (>= 5 finite members); a name in
    a smaller group or unclassified: minus the cross-sectional mean."""
    out = np.full(r.shape, np.nan)
    ok = np.isfinite(r)
    if not ok.any():
        return out
    dm = sg.industry_demean(np.where(ok, r, np.nan), codes)
    grouped = ok & (codes >= 0)
    cnt = np.bincount(codes[grouped].astype(int), minlength=64)
    grouped[grouped] = cnt[codes[grouped].astype(int)] >= sg.MIN_INDUSTRY_MEMBERS
    out[ok] = np.where(grouped, dm, r - np.nanmean(r))[ok]
    return out


def window_stats(
    dates: pd.DatetimeIndex, ic: np.ndarray, lo: str, hi: str, me_mask: np.ndarray
) -> dict:
    sel = (dates >= pd.Timestamp(lo)) & (dates <= pd.Timestamp(hi)) & np.isfinite(ic)
    x = ic[sel]
    xm = ic[sel & me_mask]
    return {
        "ic": float(np.mean(x)) if len(x) else float("nan"),
        "nw21_t": sg.newey_west_t(x, 21) if len(x) else float("nan"),
        "n_days": int(len(x)),
        "monthly_ic": float(np.mean(xm)) if len(xm) else float("nan"),
        "monthly_t": sg.plain_t(xm) if len(xm) > 2 else float("nan"),
        "n_months": int(len(xm)),
    }


def sanitize(o):
    """JSON-safe copy: NaN / inf -> None, numpy scalars -> Python."""
    if isinstance(o, dict):
        return {str(k): sanitize(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [sanitize(v) for v in o]
    if isinstance(o, (np.floating, float)):
        return float(o) if np.isfinite(o) else None
    if isinstance(o, np.integer):
        return int(o)
    return o


def _fmt(v: float, nd: int = 4) -> str:
    return "" if not np.isfinite(v) else f"{v:.{nd}f}"


def stage_report() -> None:
    t0 = time.time()
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    ac = json.loads((OUT / "_alpha_columns.json").read_text())
    specs = sg.all_specs(ac["kept"])
    names = [s.name for s in specs] + [f"theme_{t}" for t in sg.THEMES] + ["m0_composite"]
    is_theme = {n: n.startswith("theme_") or n == "m0_composite" for n in names}
    cols = [n for n in names] + [f"{s.name}_cov" for s in specs]
    corr_names = list(sg.SLOW_NAMES) + [s.name for s in sg.FAST_BASE_SIGNALS] + ["m0_composite"]

    # prices for the forward label
    con = _duck()
    ever = (
        con.execute(
            f"select distinct symbol from read_parquet('{PANEL}/20*.parquet') where in_u3000 order by 1"
        )
        .df()["symbol"]
        .tolist()
    )
    pp = PricePanel.from_dir(symbols=ever, include_etfs=False)
    cal = pp.dates
    col_of = {s: i for i, s in enumerate(pp.symbols)}
    _log(f"prices loaded {pp.close.shape}")

    # split / share-change diagnostic inputs: latest as-filed share count per symbol
    last_sh = (
        con.execute(
            f"""select symbol, arg_max(shares_outstanding, trade_date) as sh_last
            from read_parquet('{FEAT / "sec_fundamentals_daily"}/*.parquet')
            where shares_outstanding > 0 group by symbol"""
        )
        .df()
        .set_index("symbol")["sh_last"]
    )
    is_me_cal = pd.Series(cal[:-1].month.to_numpy() != cal[1:].month.to_numpy(), index=cal[:-1])

    dates_list: list[pd.Timestamp] = []
    ic_raw: dict[str, list[float]] = {n: [] for n in names}
    ic_ind: dict[str, list[float]] = {n: [] for n in names}
    value_names = ["bm", "ep", "sp", "cfp", "theme_value"]
    ic_clean: dict[str, list[float]] = {n: [] for n in value_names}
    ic_flag: dict[str, list[float]] = {n: [] for n in value_names}
    me_dates: list[pd.Timestamp] = []
    corr_sum = np.zeros((len(corr_names), len(corr_names)))
    corr_n = np.zeros((len(corr_names), len(corr_names)))
    ac_vals: dict[str, list[float]] = {n: [] for n in names}
    prev_me: pd.DataFrame | None = None
    me_flags: list[tuple[pd.Timestamp, pd.DataFrame]] = []
    n_dates = 0
    for d, df in iter_signal_dates(cols):
        p = int(cal.searchsorted(d))
        if p >= len(cal) or cal[p] != d:
            continue
        is_me = bool(is_me_cal.get(d, False))
        if p + 1 + HORIZON >= len(cal) and not is_me:
            continue
        n_dates += 1
        sym_col = np.array([col_of.get(s, -1) for s in df["symbol"]])
        have_fwd = p + 1 + HORIZON < len(cal)
        if have_fwd:
            fwd_all = forward_open_to_open(pp.open, pp.close, p + 1, p + 1 + HORIZON)
            fwd = np.where(sym_col >= 0, fwd_all[np.where(sym_col >= 0, sym_col, 0)], np.nan)
            fwd_ind = demean_by_group(fwd, df["ind_code"].to_numpy())
            dates_list.append(d)
            for n in names:
                sc = df[n].to_numpy("float64")
                if not is_theme[n]:
                    sc = np.where(df[f"{n}_cov"].to_numpy(), sc, np.nan)
                elif n.startswith("theme_"):  # a theme score only where one of its signals exists
                    any_cov = np.any(
                        [df[f"{x}_cov"].to_numpy() for x in sg.THEME_SIGNALS[n[6:]]], axis=0
                    )
                    sc = np.where(any_cov, sc, np.nan)
                ic_raw[n].append(sg.rank_ic(sc, fwd))
                ic_ind[n].append(sg.rank_ic(sc, fwd_ind))
        if is_me:
            me_dates.append(d)
            sub = df.set_index("symbol")
            # exact Spearman among the corr set on pairwise-covered names
            mat = np.column_stack(
                [
                    np.where(sub[f"{n}_cov"], sub[n], np.nan)
                    if n != "m0_composite"
                    else sub[n].to_numpy("float64")
                    for n in corr_names
                ]
            )
            for a in range(len(corr_names)):
                for b in range(a, len(corr_names)):
                    ok = np.isfinite(mat[:, a]) & np.isfinite(mat[:, b])
                    if ok.sum() >= 30:
                        c = sg.rank_ic(mat[ok, a], mat[ok, b])
                        if np.isfinite(c):
                            corr_sum[a, b] += c
                            corr_n[a, b] += 1
            # month-to-month rank autocorrelation
            if prev_me is not None:
                both = sub.index.intersection(prev_me.index)
                for n in names:
                    a_ = sub.loc[both, n].to_numpy("float64")
                    b_ = prev_me.loc[both, n].to_numpy("float64")
                    if not is_theme[n]:
                        ok = (
                            sub.loc[both, f"{n}_cov"].to_numpy()
                            & prev_me.loc[both, f"{n}_cov"].to_numpy()
                        )
                        a_, b_ = np.where(ok, a_, np.nan), np.where(ok, b_, np.nan)
                    ac_vals[n].append(sg.rank_ic(a_, b_))
            prev_me = sub[[*names, *[f"{s.name}_cov" for s in specs]]]
            if have_fwd:
                me_flags.append(
                    (
                        d,
                        sub[
                            [n for n in value_names] + [f"{n}_cov" for n in value_names[:4]]
                        ].copy(),
                    )
                )
                # share-count flag for the value diagnostic
                fwd_s = pd.Series(fwd, index=df["symbol"].to_numpy())
                me_flags[-1][1]["fwd"] = fwd_s.reindex(sub.index).to_numpy()
        if n_dates % 250 == 0:
            _log(f"report pass: {n_dates} dates, last {d.date()}")
    _log(f"pass done: {len(dates_list)} dates with forward returns, {len(me_dates)} month-ends")

    # ---- value diagnostic: names whose share count changed a lot between t and the latest filing
    diag: dict = {}
    if me_flags:
        con.register("sh_dates", pd.DataFrame({"trade_date": [d for d, _ in me_flags]}))
        sh_t = con.execute(
            f"""select f.symbol, f.trade_date, f.shares_outstanding
                from read_parquet('{FEAT / "sec_fundamentals_daily"}/*.parquet') f
                join sh_dates s on s.trade_date = f.trade_date"""
        ).df()
        sh_t["trade_date"] = _ns(sh_t["trade_date"])
        sh_idx = sh_t.set_index(["trade_date", "symbol"])["shares_outstanding"]
        by_year: dict[int, list[float]] = {}
        for d, sub in me_flags:
            shares_t = sh_idx.reindex(pd.MultiIndex.from_product([[d], sub.index])).to_numpy()
            ratio = last_sh.reindex(sub.index).to_numpy() / np.where(shares_t > 0, shares_t, np.nan)
            known = np.isfinite(ratio)
            flag = known & ((ratio >= SPLIT_FLAG_HI) | (ratio <= SPLIT_FLAG_LO))
            fwd = sub["fwd"].to_numpy()
            by_year.setdefault(d.year, []).append(float(flag.sum() / max(known.sum(), 1)))
            for n in value_names:
                sc = sub[n].to_numpy("float64")
                if n != "theme_value":
                    sc = np.where(sub[f"{n}_cov"], sc, np.nan)
                else:
                    sc = np.where(known, sc, np.nan)
                ic_clean[n].append(sg.rank_ic(np.where(~flag, sc, np.nan), fwd))
                ic_flag[n].append(sg.rank_ic(np.where(flag, sc, np.nan), fwd, min_n=20))
        me_idx = pd.DatetimeIndex([d for d, _ in me_flags])
        diag = {
            "definition": f"flag = latest as-filed share count / share count at t >= {SPLIT_FLAG_HI} or <= {SPLIT_FLAG_LO} (a later split or a very large issuance); IC at month-ends vs open(t+1)->open(t+22)",
            "flag_share_by_year": {str(y): float(np.mean(v)) for y, v in sorted(by_year.items())},
            "signals": {},
        }
        for n in value_names:
            row = {}
            for wn, (lo, hi) in (("stress", STRESS), ("anchor", ANCHOR)):
                sel = (me_idx >= pd.Timestamp(lo)) & (me_idx <= pd.Timestamp(hi))
                for tag, arr in (("all_unflagged_only", ic_clean[n]), ("flagged_only", ic_flag[n])):
                    x = np.asarray(arr)[sel]
                    row[f"{wn}_{tag}"] = {
                        "ic": float(np.nanmean(x)),
                        "t": sg.plain_t(x),
                        "n": int(np.isfinite(x).sum()),
                    }
            diag["signals"][n] = row

    dates = pd.DatetimeIndex(dates_list)
    me_set = set(me_dates)
    me_mask = np.array([d in me_set for d in dates])
    results: dict = {
        "windows": {"stress": STRESS, "anchor": ANCHOR, "full": FULL},
        "ic": {},
        "autocorr": {},
    }
    for n in names:
        results["ic"][n] = {}
        for var, store in (("raw_ret", ic_raw), ("industry_adj_ret", ic_ind)):
            arr = np.asarray(store[n], dtype="float64")
            results["ic"][n][var] = {
                wn: window_stats(dates, arr, lo, hi, me_mask)
                for wn, (lo, hi) in (("stress", STRESS), ("anchor", ANCHOR), ("full", FULL))
            }
        a = np.asarray(ac_vals[n], dtype="float64")
        results["autocorr"][n] = {
            "mean": float(np.nanmean(a)) if np.isfinite(a).any() else float("nan"),
            "median": float(np.nanmedian(a)) if np.isfinite(a).any() else float("nan"),
            "n_months": int(np.isfinite(a).sum()),
        }
    cm = np.where(corr_n > 0, corr_sum / np.maximum(corr_n, 1), np.nan)
    cm = np.where(np.isnan(cm), cm.T, cm)
    cmat = np.triu(cm) + np.triu(cm, 1).T
    results["corr"] = {
        "names": corr_names,
        "matrix": cmat.tolist(),
        "n_month_ends": int(corr_n.max()),
    }
    results["value_split_diagnostic"] = diag
    cov_by_year = {}
    for f in sorted(OUT.glob("_coverage_*.json")):
        m = json.loads(f.read_text())
        cov_by_year[f.stem.split("_")[-1]] = {
            "rows": m["rows"],
            "dates": m["dates"],
            "symbols": m["symbols"],
            "coverage": m["coverage"],
        }
    results["coverage_by_year"] = cov_by_year
    results["fundamentals_check"] = fundamentals_check(ac["kept"])
    results["meta"] = {
        "label": "open(t+1) -> open(t+22) via returns.forward_open_to_open, horizon 21 sessions",
        "ic": "daily cross-sectional Spearman between the processed score (covered names only) and the forward return; industry-adjusted = return minus the equal-weighted mean of the risk-model industry group (>= 5 members, else the cross-sectional mean)",
        "t": "nw21_t = Newey-West (Bartlett, 21 lags) t of the daily IC series, overlapping 22-session labels; monthly_t = plain t over the last session of each month (non-overlapping)",
        "autocorr": "mean over consecutive month-ends of the Spearman correlation between the two cross-sections (names covered in both)",
        "corr": "mean over month-ends of the exact Spearman correlation on pairwise-covered names (processed scores)",
        "seconds": round(time.time() - t0, 1),
        "peak_rss_mb": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024),
    }
    (REPORT_DIR / "results.json").write_text(json.dumps(sanitize(results), indent=1))
    write_report_md(results, specs)
    _log("report written")


def fundamentals_check(alpha_cols: dict) -> dict:
    """The annual net income rebuilt from the facts must equal ``roe x stockholders_equity`` of
    ``sec_fundamentals_daily`` (same first-filed FY series), on the month-ends of 2024."""
    ctx = Context(alpha_cols, light=True)
    con = ctx.con
    f = con.execute(
        f"""select symbol, trade_date, cik, roe, stockholders_equity from read_parquet('{FEAT / "sec_fundamentals_daily/2024.parquet"}')
            where roe is not null and stockholders_equity is not null and cik is not null
              and strftime(trade_date, '%d') in ('15', '28') """
    ).df()
    f["trade_date"] = _ns(f["trade_date"])
    ni = sg.annual_flow_asof(ctx.flows["ni_a"], f["cik"], f["trade_date"])
    target = f["roe"].to_numpy() * f["stockholders_equity"].to_numpy()
    ok = np.isfinite(ni) & np.isfinite(target)
    rel = np.abs(ni[ok] - target[ok]) / np.maximum(np.abs(target[ok]), 1.0)
    return {
        "rows_compared": int(ok.sum()),
        "share_within_1e-6": float((rel < 1e-6).mean()),
        "share_within_1e-3": float((rel < 1e-3).mean()),
        "rows_without_annual_ni": int((~np.isfinite(ni)).sum()),
        "facts_rows_dropped_by_pit_guard": ctx.dropped_facts,
    }


def write_report_md(res: dict, specs) -> None:
    L: list[str] = []
    w = L.append
    w("# Signal library v1 (S1) -- measurement report\n")
    w(
        "Task T-20261001-05, coordinator code R1001-0725-S1.  Measurements on data the project has already seen; they do not choose signals (M0 uses every slow signal).\n"
    )
    m = res["meta"]
    w(f"- IC: {m['ic']}.")
    w(f"- Label: {m['label']}.")
    w(f"- t: {m['t']}.")
    w(f"- Autocorrelation: {m['autocorr']}.")
    w(f"- Correlation: {m['corr']}.")
    w(
        f"- Windows (decision dates): stress {STRESS[0]}..{STRESS[1]}, anchor {ANCHOR[0]}..{ANCHOR[1]}, full {FULL[0]}..{FULL[1]}.\n"
    )

    # coverage
    years = sorted(res["coverage_by_year"])
    w("## Coverage by year (share of U3000 rows with a finite raw value)\n")
    shown = [s for s in specs if not s.name.startswith(("a101_", "g191_"))]
    w("| signal | " + " | ".join(years) + " |")
    w("|---|" + "---|" * len(years))
    for s in shown:
        row = [
            _fmt(res["coverage_by_year"][y]["coverage"].get(f"{s.name}_cov", float("nan")), 3)
            for y in years
        ]
        w(f"| {s.name} | " + " | ".join(row) + " |")
    row = [
        _fmt(res["coverage_by_year"][y]["coverage"].get("m0_themes_ge6", float("nan")), 3)
        for y in years
    ]
    w("| rows with >= 6 of 9 slow themes covered | " + " | ".join(row) + " |")
    row = [
        _fmt(res["coverage_by_year"][y]["coverage"].get("resid_mom_12_1_fallback", float("nan")), 3)
        for y in years
    ]
    w("| resid_mom_12_1 from the fallback residuals | " + " | ".join(row) + " |")
    w(
        "| rows (U3000) | "
        + " | ".join(str(res["coverage_by_year"][y]["rows"]) for y in years)
        + " |"
    )
    w("")
    al = [s for s in specs if s.name.startswith(("a101_", "g191_"))]
    vals = np.array(
        [
            [res["coverage_by_year"][y]["coverage"].get(f"{s.name}_cov", np.nan) for y in years]
            for s in al
        ]
    )
    w(
        f"Alpha columns kept ({len(al)}): coverage min {np.nanmin(vals):.3f}, mean {np.nanmean(vals):.3f} over all years; list in `data/research/equity_book/signals/_alpha_columns.json`.\n"
    )

    # IC tables
    def ic_table(rows: list[str], title: str) -> None:
        w(f"## {title}\n")
        w("Each cell: mean daily IC / NW(21) t / monthly non-overlapping t.\n")
        w(
            "| signal | stress raw | stress ind-adj | anchor raw | anchor ind-adj | full raw | full ind-adj |"
        )
        w("|---|---|---|---|---|---|---|")
        for n in rows:
            cells = []
            for wn in ("stress", "anchor", "full"):
                for var in ("raw_ret", "industry_adj_ret"):
                    r = res["ic"][n][var][wn]
                    cells.append(
                        f"{_fmt(r['ic'])} / {_fmt(r['nw21_t'], 2)} / {_fmt(r['monthly_t'], 2)}"
                    )
            w(f"| {n} | " + " | ".join(cells) + " |")
        w("")

    ic_table([s.name for s in specs if s.theme != "fast"], "Rank IC, slow signals")
    ic_table(
        [f"theme_{t}" for t in sg.THEMES] + ["m0_composite"],
        "Rank IC, theme scores and the M0 composite",
    )
    ic_table(
        [s.name for s in specs if s.name in {x.name for x in sg.FAST_BASE_SIGNALS}],
        "Rank IC, fast signals (ML inputs only)",
    )
    ic_table([s.name for s in al], "Rank IC, alpha101 / alpha191 columns (fast, ML inputs only)")

    # autocorr
    w("## Month-to-month rank autocorrelation\n")
    w("| signal | mean | median | months |")
    w("|---|---|---|---|")
    for n in [s.name for s in specs] + [f"theme_{t}" for t in sg.THEMES] + ["m0_composite"]:
        a = res["autocorr"][n]
        w(f"| {n} | {_fmt(a['mean'], 3)} | {_fmt(a['median'], 3)} | {a['n_months']} |")
    w("")

    # corr
    names = res["corr"]["names"]
    mat = np.array(res["corr"]["matrix"], dtype="float64")
    w(f"## Signal correlation (mean exact Spearman at {res['corr']['n_month_ends']} month-ends)\n")
    w("| | " + " | ".join(n[:11] for n in names) + " |")
    w("|---|" + "---|" * len(names))
    for i, n in enumerate(names):
        w(f"| {n} | " + " | ".join(_fmt(mat[i, j], 2) for j in range(len(names))) + " |")
    pairs = sorted(
        (
            (abs(mat[i, j]), names[i], names[j], mat[i, j])
            for i in range(len(names))
            for j in range(i + 1, len(names))
            if np.isfinite(mat[i, j])
        ),
        reverse=True,
    )
    w("\nLargest absolute pairwise correlations:\n")
    for _, a, b, c in pairs[:12]:
        w(f"- {a} / {b}: {c:.2f}")
    w("")

    # diag
    d = res["value_split_diagnostic"]
    if d:
        w("## Diagnostic: split-contaminated market cap in the value ratios\n")
        w(d["definition"] + ".\n")
        w(
            "Share of month-end U3000 names flagged, by year: "
            + ", ".join(f"{y} {v:.3f}" for y, v in d["flag_share_by_year"].items())
            + ".\n"
        )
        w("| signal | window | IC unflagged | t | n | IC flagged | t | n |")
        w("|---|---|---|---|---|---|---|---|")
        for n, row in d["signals"].items():
            for wn in ("stress", "anchor"):
                u, f = row[f"{wn}_all_unflagged_only"], row[f"{wn}_flagged_only"]
                w(
                    f"| {n} | {wn} | {_fmt(u['ic'])} | {_fmt(u['t'], 2)} | {u['n']} | {_fmt(f['ic'])} | {_fmt(f['t'], 2)} | {f['n']} |"
                )
        w("")
    fc = res["fundamentals_check"]
    w(
        "## Check: annual net income from the facts vs `roe x stockholders_equity` (2024, two days a month)\n"
    )
    w(
        f"- rows compared {fc['rows_compared']}, within 1e-6: {fc['share_within_1e-6']:.4f}, within 1e-3: {fc['share_within_1e-3']:.4f}; rows with no annual NI from the facts {fc['rows_without_annual_ni']}; fact rows dropped by the point-in-time guard {fc['facts_rows_dropped_by_pit_guard']}."
    )
    w(f"\nRuntime {m['seconds']} s, peak RSS {m['peak_rss_mb']} MB.")
    (REPORT_DIR / "report.md").write_text("\n".join(L) + "\n")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("stage", choices=["alpha-cols", "build", "report"])
    ap.add_argument("--years", default=None, help="e.g. 2019 or 2019-2021")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--chunk-months", type=int, default=3)
    args = ap.parse_args()
    if args.stage == "alpha-cols":
        stage_alpha_cols()
    elif args.stage == "build":
        if args.years:
            a, _, b = args.years.partition("-")
            years = list(range(int(a), int(b or a) + 1))
        else:
            years = list(range(FIRST_YEAR, 2027))
        stage_build(years, args.chunk_months, args.force)
    else:
        stage_report()


if __name__ == "__main__":
    main()
