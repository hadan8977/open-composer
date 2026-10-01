# ruff: noqa: E501
"""Build the equity-book research panel (design ``docs/equity-book-design.zh.md`` sections 2, 3, 13).

Outputs (``data/research/equity_book/``, gitignored)::

    panel/<year>.parquet     long, one row per (trade_date, symbol), every symbol with
                             adv_rank <= 4000 in the latest universe_broad month_end <= date
    panel/_hygiene.parquet   per-symbol price-hygiene cutoffs and first valid session
    prices/<year>.parquet    open/close of every panel-universe symbol, no rank filter (engine input)
    panel/_manifest.json     counts, masked-cell totals, caveats
    etf_daily.parquet        SPY / IWM / IJR / SGOV / BIL / SHY / sector SPDRs (SIP daily)

Panel columns: trade_date, symbol, open, close, dollar_adv_21, adv_rank, mcap, mcap_source,
in_u3000, in_p1000, ff48, ff48_verified, beta_252_spy, idio_vol_63, vol_21, is_tradeable.

Price hygiene (``price_hygiene.sanitize_price_matrices``, default settings) blanks a symbol's
history up to its last maskable break (reused tickers, bad prints, long holes), so it needs the
whole 2016-2026 history of a symbol at once.  Pass 1 therefore runs per symbol chunk over all
years and records one cutoff date per symbol; pass 2 writes one parquet per year and drops the
rows at or before the cutoff (a blanked price is a missing row, ``price_cells_masked`` counts them).

Run (heavy; capped)::

    scripts/run_capped.sh --mem 1.8G -- uv run python scripts/build_equity_book_panel.py all

Subcommands: ``hygiene`` (pass 1), ``panel`` (pass 2), ``prices``, ``etf``, ``all``.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

OUT = ROOT / "data/research/equity_book"
PANEL_DIR = OUT / "panel"
DAILY = ROOT / "data/features/daily_broad"
UNIV_GLOB = str(ROOT / "data/features/universe_broad/*.parquet")
FUND_GLOB = ROOT / "data/features/sec_fundamentals_daily"
SIC_PATH = ROOT / "data/features/sic_map/sic_map.parquet"
ASSET_META = ROOT / "data/features/universe/_asset_metadata.parquet"
SIP_GLOB = str(ROOT / "data/sip/daily/*/shard-*.parquet")

ADV_RANK_MAX = 4000
U3000_RANK = 3000
P1000_RANK = 1000
MIN_CLOSE = 5.0
MIN_HISTORY = 252
MIN_SESSION_NAMES = 500
OUTLIER = 10.0  # sec mcap / (k * adv) outside [1/10, 10] -> adv fallback (unadjusted shares vs adjusted close)
ETF_SYMBOLS = [
    "SPY",
    "IWM",
    "IJR",
    "SGOV",
    "BIL",
    "SHY",
    "XLB",
    "XLC",
    "XLE",
    "XLF",
    "XLI",
    "XLK",
    "XLP",
    "XLRE",
    "XLU",
    "XLV",
    "XLY",
]
PANEL_COLUMNS = [
    "trade_date",
    "symbol",
    "open",
    "close",
    "dollar_adv_21",
    "adv_rank",
    "mcap",
    "mcap_source",
    "in_u3000",
    "in_p1000",
    "ff48",
    "ff48_verified",
    "beta_252_spy",
    "idio_vol_63",
    "vol_21",
    "is_tradeable",
]


def _log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def _duck(mem: str = "1100MB"):
    import duckdb

    tmp = OUT / "duck_tmp"
    tmp.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    con.execute(f"SET memory_limit='{mem}'")
    con.execute("SET threads=2")
    con.execute(f"SET temp_directory='{tmp}'")
    con.execute("SET TimeZone='UTC'")
    return con


def session_calendar(con) -> pd.DatetimeIndex:
    df = con.execute(
        f"select trade_date, count(*) n from read_parquet('{DAILY}/*.parquet') group by 1 order by 1"
    ).df()
    return pd.DatetimeIndex(df.loc[df["n"] >= MIN_SESSION_NAMES, "trade_date"])


def panel_symbols(con) -> list[str]:
    df = con.execute(
        f"select distinct symbol from read_parquet('{UNIV_GLOB}') "
        f"where adv_rank <= {ADV_RANK_MAX} order by 1"
    ).df()
    return df["symbol"].astype(str).tolist()


# --------------------------------------------------------------------------
# pass 1: price hygiene
# --------------------------------------------------------------------------


def stage_hygiene(chunk: int = 600) -> dict:
    from open_composer.research.features import price_hygiene as ph

    con = _duck()
    cal = session_calendar(con)
    syms = panel_symbols(con)
    _log(f"hygiene: {len(syms)} symbols, {len(cal)} sessions {cal[0].date()}..{cal[-1].date()}")
    rows = []
    tot = {"symbols_masked": 0, "price_cells_masked": 0, "symbols_masked_for_jump": 0}
    tot["symbols_masked_for_gap"] = 0
    for ci in range(0, len(syms), chunk):
        names = syms[ci : ci + chunk]
        con.register("chunk_syms", pd.DataFrame({"symbol": names}))
        df = con.execute(
            f"select d.symbol, d.trade_date, d.open, d.close from read_parquet('{DAILY}/*.parquet') d "
            "semi join chunk_syms c on d.symbol = c.symbol"
        ).df()
        df = df.drop_duplicates(["trade_date", "symbol"], keep="last")
        close_w = df.pivot(index="trade_date", columns="symbol", values="close").reindex(cal)
        open_w = df.pivot(index="trade_date", columns="symbol", values="open").reindex(cal)
        del df
        close_s, _open_s, rep = ph.sanitize_price_matrices(
            close_w.astype("float64"), open_w.astype("float64")
        )
        cutoff = {
            b.symbol: b.last_session_before for b in rep.breaks if b.masked
        }  # last maskable break per symbol
        valid = np.isfinite(close_s.to_numpy()) & (close_s.to_numpy() > 0)
        first_pos = np.where(valid.any(axis=0), valid.argmax(axis=0), -1)
        for j, sym in enumerate(close_s.columns):
            rows.append(
                {
                    "symbol": str(sym),
                    "cutoff_date": cutoff.get(str(sym), pd.NaT),
                    "first_valid_date": cal[first_pos[j]] if first_pos[j] >= 0 else pd.NaT,
                    "first_valid_pos": int(first_pos[j]),
                }
            )
        for k in tot:
            tot[k] += int(getattr(rep, k))
        _log(f"hygiene chunk {ci // chunk + 1}/{math.ceil(len(syms) / chunk)}: {tot}")
        del close_w, open_w, close_s, valid
    hyg = pd.DataFrame(rows)
    hyg["cutoff_date"] = pd.to_datetime(hyg["cutoff_date"])
    hyg["first_valid_date"] = pd.to_datetime(hyg["first_valid_date"])
    PANEL_DIR.mkdir(parents=True, exist_ok=True)
    hyg.to_parquet(PANEL_DIR / "_hygiene.parquet")
    pd.DataFrame({"trade_date": cal, "pos": np.arange(len(cal))}).to_parquet(
        PANEL_DIR / "_calendar.parquet"
    )
    out = {"hygiene": tot, "symbols": len(syms), "sessions": len(cal)}
    (PANEL_DIR / "_hygiene_manifest.json").write_text(json.dumps(out, indent=1))
    return out


# --------------------------------------------------------------------------
# industry lookup
# --------------------------------------------------------------------------


def ff48_by_month_end(symbols_months: pd.DataFrame) -> pd.DataFrame:
    """``(symbol, month_end)`` -> ``ff48``, ``ff48_verified`` through ``lookup_sic_row``.

    ``lookup_sic_row`` is only called once per constant segment of a symbol: its answer
    changes only where a link boundary is crossed or where two links trade places as
    "nearest" (a midpoint between boundaries), so all boundaries and pairwise midpoints are
    breakpoints.
    """
    from build_sec_sic_map import lookup_sic_row

    sic = pd.read_parquet(SIC_PATH)
    sic = sic[sic["sic"].notna()]
    by_sym = {s: g for s, g in sic.groupby("symbol")}
    out = []
    for sym, grp in symbols_months.groupby("symbol"):
        sub = by_sym.get(sym)
        months = pd.DatetimeIndex(sorted(grp["month_end"].unique()))
        if sub is None:
            out.extend((sym, m, pd.NA, False) for m in months)
            continue
        pts = sorted(
            {
                pd.Timestamp(x).value
                for x in pd.concat([sub["link_first_date"], sub["link_last_date"]]).dropna()
            }
        )
        brk = list(pts)
        brk += [(a + b) // 2 for i, a in enumerate(pts) for b in pts[i + 1 :]]
        brk = np.array(sorted(set(brk)), dtype="int64")
        seg = (
            np.searchsorted(brk, months.asi8, side="right")
            if len(brk)
            else np.zeros(len(months), int)
        )
        cache: dict[int, tuple[object, bool]] = {}
        for m, sg in zip(months, seg, strict=True):
            sg = int(sg)
            if sg not in cache:
                row, verified = lookup_sic_row(sub, sym, m)
                cache[sg] = (
                    pd.NA if row is None or pd.isna(row["ff48"]) else int(row["ff48"]),
                    bool(verified),
                )
            ff, ver = cache[sg]
            out.append((sym, m, ff, ver))
    df = pd.DataFrame(out, columns=["symbol", "month_end", "ff48", "ff48_verified"])
    df["ff48"] = df["ff48"].astype("Int16")
    return df


# --------------------------------------------------------------------------
# pass 2: per-year panel
# --------------------------------------------------------------------------

YEAR_SQL = """
create or replace temp table base as
select d.trade_date, d.symbol, case when d.open > 0 then d.open end as open, d.close, d.dollar_adv_21, d.beta_252_spy, d.idio_vol_63,
       d.vol_21, u.adv_rank, u.month_end, f.shares_outstanding,
       h.cutoff_date, h.first_valid_pos
from read_parquet('{daily}') d
join umap u on u.trade_date = d.trade_date and u.symbol = d.symbol
join cal c on c.trade_date = d.trade_date
join hyg h on h.symbol = d.symbol
left join read_parquet('{fund}') f on f.symbol = d.symbol and f.trade_date = d.trade_date
where d.close is not null and d.close > 0
qualify row_number() over (partition by d.symbol, d.trade_date order by d.close) = 1
"""


def stage_panel(years: list[int] | None = None) -> dict:
    con = _duck()
    hyg = pd.read_parquet(PANEL_DIR / "_hygiene.parquet")
    cal = pd.read_parquet(PANEL_DIR / "_calendar.parquet")
    con.register("hyg", hyg)
    con.register("cal", cal)
    asset = pd.read_parquet(ASSET_META, columns=["symbol", "is_probable_fund_or_etf"])
    funds = pd.DataFrame({"symbol": asset.loc[asset["is_probable_fund_or_etf"], "symbol"]})
    con.register("funds", funds)
    # trade_date -> latest universe month_end <= trade_date
    mes = pd.DatetimeIndex(
        sorted(
            con.execute(f"select distinct month_end from read_parquet('{UNIV_GLOB}')").df()[
                "month_end"
            ]
        )
    )
    td = pd.DatetimeIndex(cal["trade_date"])
    pos = mes.searchsorted(td, side="right") - 1
    cmap = pd.DataFrame({"trade_date": td[pos >= 0], "month_end": mes[pos[pos >= 0]]})
    con.register("cmap", cmap)
    con.execute(
        f"create or replace temp table umap as select cm.trade_date, u.symbol, u.adv_rank, u.month_end "
        f"from cmap cm join read_parquet('{UNIV_GLOB}') u on u.month_end = cm.month_end "
        f"where u.adv_rank <= {ADV_RANK_MAX}"
    )
    sm = con.execute("select distinct symbol, month_end from umap").df()
    _log(f"ff48 lookup for {len(sm):,} symbol-months")
    ff = ff48_by_month_end(sm)
    con.register("ffmap", ff)
    totals = {"rows": 0, "price_cells_masked": 0, "mcap_fallback_rows": 0, "no_ff48_rows": 0}
    PANEL_DIR.mkdir(parents=True, exist_ok=True)
    all_years = sorted(int(p.stem) for p in DAILY.glob("*.parquet"))
    for year in years or all_years:
        daily = DAILY / f"{year}.parquet"
        fund = FUND_GLOB / f"{year}.parquet"
        if not daily.exists():
            continue
        con.execute(YEAR_SQL.format(daily=daily, fund=fund))
        masked = con.execute(
            "select count(*) from base where cutoff_date is not null and trade_date <= cutoff_date"
        ).fetchone()[0]
        con.execute("delete from base where cutoff_date is not null and trade_date <= cutoff_date")
        # fallback ratio mcap / dollar_adv_21 by (adv-rank bucket), median within the year
        con.execute(
            """
            create or replace temp table ratio as
            select cast(adv_rank / 250 as int) as rb,
                   quantile_cont(close * shares_outstanding / dollar_adv_21, 0.5) as k
            from base
            where shares_outstanding > 0 and dollar_adv_21 > 0
            group by 1
            """
        )
        con.execute(
            f"""
            create or replace temp table out_year as
            select b.trade_date, b.symbol, b.open, b.close, b.dollar_adv_21, b.adv_rank,
                   case when b.shares_outstanding > 0 and b.dollar_adv_21 > 0 and r.k > 0
                             and b.close * b.shares_outstanding / b.dollar_adv_21 between r.k / {OUTLIER} and r.k * {OUTLIER}
                        then b.close * b.shares_outstanding
                        when b.shares_outstanding > 0 and b.dollar_adv_21 is not null and b.dollar_adv_21 <= 0
                        then b.close * b.shares_outstanding
                        else r.k * b.dollar_adv_21 end as mcap,
                   case when coalesce(b.shares_outstanding, 0) <= 0 then 'adv_fallback'
                        when b.dollar_adv_21 > 0 and r.k > 0
                             and b.close * b.shares_outstanding / b.dollar_adv_21 not between r.k / {OUTLIER} and r.k * {OUTLIER}
                        then 'adv_fallback_outlier'
                        else 'sec' end as mcap_source,
                   ((b.adv_rank <= {U3000_RANK}) and b.close >= {MIN_CLOSE}
                    and fd.symbol is null
                    and (cp.pos - b.first_valid_pos + 1) >= {MIN_HISTORY}) as in_u3000,
                   ((b.adv_rank <= {P1000_RANK}) and b.close >= {MIN_CLOSE}
                    and fd.symbol is null
                    and (cp.pos - b.first_valid_pos + 1) >= {MIN_HISTORY}) as in_p1000,
                   f.ff48, coalesce(f.ff48_verified, false) as ff48_verified,
                   b.beta_252_spy, b.idio_vol_63, b.vol_21,
                   (b.open > 0 and b.close > 0 and coalesce(b.dollar_adv_21, 0) > 0) as is_tradeable
            from base b
            left join ratio r on r.rb = cast(b.adv_rank / 250 as int)
            left join funds fd on fd.symbol = b.symbol
            join cal cp on cp.trade_date = b.trade_date
            left join ffmap f on f.symbol = b.symbol and f.month_end = b.month_end
            """
        )
        df = con.execute("select * from out_year order by trade_date, symbol").df()
        df["in_p1000"] = df["in_p1000"].fillna(False).astype(bool)
        df["in_u3000"] = df["in_u3000"].fillna(False).astype(bool)
        df["ff48_verified"] = df["ff48_verified"].fillna(False).astype(bool)
        df = df[PANEL_COLUMNS]
        df.to_parquet(PANEL_DIR / f"{year}.parquet", index=False)
        totals["rows"] += len(df)
        totals["price_cells_masked"] += int(masked)
        totals["mcap_fallback_rows"] += int((df["mcap_source"] != "sec").sum())
        totals["no_ff48_rows"] += int(df["ff48"].isna().sum())
        _log(
            f"{year}: {len(df):,} rows, u3000/day {df['in_u3000'].sum() / max(1, df['trade_date'].nunique()):.0f}, "
            f"masked rows {masked:,}, fallback mcap {(df['mcap_source'] != 'sec').mean():.3f}, "
            f"ff48 missing {df['ff48'].isna().mean():.3f}"
        )
        del df
    return totals


# --------------------------------------------------------------------------
# price-only table (no universe filter): what the backtest engine reads
# --------------------------------------------------------------------------

PRICES_DIR = OUT / "prices"


def stage_prices() -> dict:
    """``prices/<year>.parquet``: (trade_date, symbol, open, close) for *every* panel-universe
    symbol after hygiene, with no rank filter.  A held name that drops out of the top 4000 by
    ADV (and so out of ``panel/``) must keep its returns; a name with no price row from some date
    on is a delisting, never "left the universe"."""
    con = _duck()
    hyg = pd.read_parquet(PANEL_DIR / "_hygiene.parquet")
    cal = pd.read_parquet(PANEL_DIR / "_calendar.parquet")
    con.register("hyg", hyg)
    con.register("cal", cal)
    PRICES_DIR.mkdir(parents=True, exist_ok=True)
    tot = {"rows": 0}
    for p in sorted(DAILY.glob("*.parquet")):
        df = con.execute(
            f"""
            select d.trade_date, d.symbol, case when d.open > 0 then d.open end as open, d.close
            from read_parquet('{p}') d
            join hyg h on h.symbol = d.symbol
            join cal c on c.trade_date = d.trade_date
            where d.close > 0 and (h.cutoff_date is null or d.trade_date > h.cutoff_date)
            qualify row_number() over (partition by d.symbol, d.trade_date order by d.close) = 1
            order by d.trade_date, d.symbol
            """
        ).df()
        df.to_parquet(PRICES_DIR / f"{p.stem}.parquet", index=False)
        tot["rows"] += len(df)
        _log(f"prices {p.stem}: {len(df):,} rows")
    return tot


# --------------------------------------------------------------------------
# ETFs
# --------------------------------------------------------------------------


def stage_etf() -> dict:
    from open_composer.research.features import price_hygiene as ph

    con = _duck("600MB")
    names = ",".join(f"'{s}'" for s in ETF_SYMBOLS)
    df = con.execute(
        f"select symbol, cast(timestamp as date) as trade_date, open, close, volume "
        f"from read_parquet('{SIP_GLOB}') where symbol in ({names}) order by 1, 2"
    ).df()
    df["trade_date"] = pd.to_datetime(df["trade_date"])
    df = df.drop_duplicates(["trade_date", "symbol"], keep="last")
    idx = pd.DatetimeIndex(sorted(df["trade_date"].unique()))
    close_w = df.pivot(index="trade_date", columns="symbol", values="close").reindex(idx)
    open_w = df.pivot(index="trade_date", columns="symbol", values="open").reindex(idx)
    close_s, open_s, rep = ph.sanitize_price_matrices(close_w, open_w)
    keep = df.set_index(["trade_date", "symbol"])
    out = (
        pd.concat(
            [
                open_s.stack().rename("open"),
                close_s.stack().rename("close"),
            ],
            axis=1,
        )
        .dropna()
        .reset_index()
    )
    out.columns = ["trade_date", "symbol", "open", "close"]
    out = out.merge(df[["trade_date", "symbol", "volume"]], on=["trade_date", "symbol"], how="left")
    OUT.mkdir(parents=True, exist_ok=True)
    out.to_parquet(OUT / "etf_daily.parquet", index=False)
    del keep
    info = {
        "rows": len(out),
        "symbols": sorted(out["symbol"].unique().tolist()),
        "first": str(out["trade_date"].min().date()),
        "last": str(out["trade_date"].max().date()),
        "symbols_masked": int(rep.symbols_masked),
        "price_cells_masked": int(rep.price_cells_masked),
    }
    _log(f"etf_daily: {info}")
    return info


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("stage", choices=["hygiene", "panel", "prices", "etf", "all"])
    ap.add_argument("--years", type=int, nargs="*")
    args = ap.parse_args()
    t0 = time.time()
    manifest_path = PANEL_DIR / "_manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    if args.stage in ("hygiene", "all"):
        manifest["hygiene"] = stage_hygiene()
    if args.stage in ("panel", "all"):
        manifest["panel"] = stage_panel(args.years)
    if args.stage in ("prices", "all"):
        manifest["prices"] = stage_prices()
    if args.stage in ("etf", "all"):
        manifest["etf"] = stage_etf()
    manifest["built_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    manifest["caveats"] = [
        "dollar_adv_21 / beta_252_spy / idio_vol_63 / vol_21 are the daily_broad values computed "
        "before price hygiene",
        "history clock for the 252-session rule starts at the first post-hygiene valid close "
        "(daily_broad begins 2016-01-04, no earlier warmup)",
        "mcap_source adv_fallback (no SEC shares) / adv_fallback_outlier (SEC mcap outside 1/10..10 of "
        "the bucket median ratio, e.g. unadjusted shares vs split-adjusted close): "
        "median(close*shares/dollar_adv_21) by adv-rank bucket of 250 within the year times dollar_adv_21",
    ]
    PANEL_DIR.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=1, default=str))
    _log(f"done in {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
