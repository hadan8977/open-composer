# ruff: noqa: E501
"""Build the equity-book risk model (design section 6, ``open_composer/research/equity_book/risk.py``).

Reads the panel (``scripts/build_equity_book_panel.py``), the point-in-time fundamentals and
``daily_broad``; writes ``data/research/equity_book/risk/`` (see ``risk.py``).

    scripts/run_capped.sh --mem 1.8G -- uv run python scripts/build_equity_book_risk.py [--start 2017-01-01]
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
from open_composer.research.equity_book.backtest import signal_positions  # noqa: E402
from open_composer.research.equity_book.panel import DEFAULT_DIR, PricePanel  # noqa: E402

DAILY = ROOT / "data/features/daily_broad"
FUND = ROOT / "data/features/sec_fundamentals_daily"
SIC_PATH = ROOT / "data/features/sic_map/sic_map.parquet"


def _log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def _duck():
    import duckdb

    con = duckdb.connect()
    con.execute("SET memory_limit='600MB'")
    con.execute("SET threads=2")
    return con


def load_year_frame(con, year: int) -> pd.DataFrame:
    """U3000 rows of one year with the style inputs joined (point-in-time fundamentals)."""
    panel = DEFAULT_DIR / "panel" / f"{year}.parquet"
    fund = FUND / f"{year}.parquet"
    daily = DAILY / f"{year}.parquet"
    return con.execute(
        f"""
        select p.trade_date, p.symbol, p.mcap, p.ff48, p.beta_252_spy, p.idio_vol_63, p.in_p1000,
               f.stockholders_equity, f.gross_profitability, f.asset_growth, d.dollar_adv_63
        from read_parquet('{panel}') p
        left join read_parquet('{fund}') f on f.symbol = p.symbol and f.trade_date = p.trade_date
        left join read_parquet('{daily}') d on d.symbol = p.symbol and d.trade_date = p.trade_date
        where p.in_u3000 and p.mcap > 0
        order by p.trade_date, p.symbol
        """
    ).df()


def group_table(con) -> tuple[dict[int, str], list[str], pd.Series]:
    members = con.execute(
        f"select ff48, count(*) * 1.0 / count(distinct trade_date) as n "
        f"from read_parquet('{DEFAULT_DIR}/panel/20*.parquet') where in_p1000 and ff48 is not null "
        "group by 1"
    ).df()
    members = members.set_index("ff48")["n"]
    parent = rk.ff12_parent(pd.read_parquet(SIC_PATH))
    gmap = rk.industry_groups(members, parent)
    groups = sorted(set(gmap.values()))
    return gmap, groups, members


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2017-01-01")
    ap.add_argument("--end", default=None)
    ap.add_argument("--out", default=str(rk.RISK_DIR))
    args = ap.parse_args()
    t0 = time.time()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    con = _duck()
    gmap, groups, members = group_table(con)
    factors = rk.factor_names(groups)
    n_groups = len(groups)
    gidx = {g: i for i, g in enumerate(groups)}
    code_to_idx = np.array([gidx[gmap[c]] for c in range(1, 49)], dtype=np.int64)
    other_idx = int(code_to_idx[47])  # FF48 "Other": missing industry
    _log(f"{n_groups} industry groups, {len(factors)} factors")
    prices = PricePanel.from_dir(include_etfs=True, load_open=False)
    close = prices.close
    dates = prices.dates
    syms = prices.symbols
    spy_close = pd.Series(close[:, prices.col("SPY")], index=dates)
    spy_ret = spy_close.pct_change()
    spy_arr = spy_ret.to_numpy()
    spy_var = spy_ret.rolling(252, min_periods=60).var().bfill().to_numpy()
    wk = signal_positions(dates, "W", 0)
    mo = signal_positions(dates, "M", 0)
    saved_pos = set(wk) | set(mo)
    start = pd.Timestamp(args.start)
    end = pd.Timestamp(args.end) if args.end else dates[-1]

    spec = rk.SpecificVariance(len(syms))
    f_hist: list[np.ndarray] = []
    prev = None
    stats = {"regressions": 0, "skipped_days": 0, "r2_by_year": {}, "n_names_by_year": {}}
    all_years = sorted(int(p.stem) for p in (DEFAULT_DIR / "panel").glob("20*.parquet"))
    for year in [y for y in all_years if start.year <= y <= end.year]:
        df = load_year_frame(con, year)
        df = df[(df["trade_date"] >= start) & (df["trade_date"] <= end)]
        fr_rows, res_rows, exp_rows, cov_rows = [], [], [], []
        r2s, ns = [], []
        for d, g in df.groupby("trade_date", sort=True):
            pos = int(dates.get_loc(d))
            cols = syms.get_indexer(g["symbol"].astype(str))
            ok_cols = cols >= 0
            g = g[ok_cols]
            cols = cols[ok_cols]
            if len(g) < rk.MIN_NAMES:
                stats["skipped_days"] += 1
                prev = None
                continue
            # 1. regress today's return on yesterday's exposures
            if prev is not None and prev["pos"] == pos - 1:
                y = close[pos, prev["cols"]] / close[pos - 1, prev["cols"]] - 1.0
                ok = np.isfinite(y) & (np.abs(y) <= rk.RET_CLIP)
                if ok.sum() >= rk.MIN_NAMES:
                    f, resid, r2 = rk.cross_section_regression(
                        y[ok], prev["group"][ok], prev["styles"][ok], prev["cap"][ok], n_groups
                    )
                    f_hist.append(f)
                    stats["regressions"] += 1
                    r2s.append(r2)
                    fr_rows.append(pd.DataFrame({"trade_date": d, "factor": factors, "ret": f}))
                    res_rows.append(
                        pd.DataFrame(
                            {
                                "trade_date": d,
                                "symbol": syms[prev["cols"][ok]],
                                "resid": resid.astype("float32"),
                            }
                        )
                    )
                    spec.update(prev["cols"][ok], resid)
            # 2. today's exposures
            cap = g["mcap"].to_numpy("float64")
            ff = g["ff48"].to_numpy(dtype="float64", na_value=np.nan)
            group = np.where(
                np.isfinite(ff),
                code_to_idx[np.clip(np.nan_to_num(ff, nan=48) - 1, 0, 47).astype(int)],
                other_idx,
            )
            with np.errstate(invalid="ignore", divide="ignore"):
                mom = (
                    close[pos - 21, cols] / close[pos - 252, cols] - 1.0
                    if pos >= 252
                    else np.full(len(cols), np.nan)
                )
                rev = (
                    close[pos, cols] / close[pos - 21, cols] - 1.0
                    if pos >= 21
                    else np.full(len(cols), np.nan)
                )
                book = g["stockholders_equity"].to_numpy("float64") / cap
                adv63 = g["dollar_adv_63"].to_numpy("float64")
                liq = np.where(adv63 > 0, np.log(np.where(adv63 > 0, adv63, 1.0)), np.nan)
            beta_ewma = rk.ewma_beta(close, pos, cols, spy_arr, rk.BETA_HALFLIFE, rk.BETA_WINDOW)
            beta_raw = np.where(
                np.isfinite(beta_ewma), beta_ewma, g["beta_252_spy"].to_numpy("float64")
            )
            beta_v = rk.vasicek_beta(
                beta_raw,
                g["idio_vol_63"].to_numpy("float64"),
                cap,
                float(spy_var[pos]),
            )
            raw = {
                "size": np.log(cap),
                "beta": beta_v,
                "momentum": mom,
                "resid_vol": g["idio_vol_63"].to_numpy("float64"),
                "liquidity": liq,
                "value": book,
                "profitability": g["gross_profitability"].to_numpy("float64"),
                "investment": g["asset_growth"].to_numpy("float64"),
                "reversal": rev,
            }
            styles = np.column_stack([rk.standardize_style(raw[s], cap) for s in rk.STYLES])
            prev = {"pos": pos, "cols": cols, "group": group, "styles": styles, "cap": cap}
            # 3. save exposures / covariance on Fridays and month-ends
            if pos in saved_pos and len(f_hist) >= rk.MIN_FACTOR_OBS:
                fmat = np.vstack(f_hist)
                fcov = rk.factor_covariance(fmat)
                dvar = rk.shrink_specific(spec.raw(cols), cap)
                e = pd.DataFrame(
                    {
                        "trade_date": d,
                        "symbol": g["symbol"].to_numpy(),
                        "industry": np.array(groups)[group],
                        **{s: styles[:, k] for k, s in enumerate(rk.STYLES)},
                        "beta_vasicek": beta_v,
                        "beta_ewma": np.clip(beta_raw, -1.0, 4.0),
                        "spec_var": dvar,
                        "mcap": cap,
                        "in_p1000": g["in_p1000"].to_numpy(),
                    }
                )
                exp_rows.append(e)
                ii, jj = np.meshgrid(
                    np.arange(len(factors)), np.arange(len(factors)), indexing="ij"
                )
                fa = np.array(factors)
                cov_rows.append(
                    pd.DataFrame(
                        {
                            "trade_date": d,
                            "factor_i": fa[ii.ravel()],
                            "factor_j": fa[jj.ravel()],
                            "value": fcov.ravel(),
                        }
                    )
                )
            ns.append(len(g))
        for name, rows in (
            ("factor_returns", fr_rows),
            ("residuals", res_rows),
            ("exposures", exp_rows),
            ("cov", cov_rows),
        ):
            if rows:
                pd.concat(rows, ignore_index=True).to_parquet(
                    out / f"{name}_{year}.parquet", index=False
                )
        stats["r2_by_year"][year] = float(np.mean(r2s)) if r2s else None
        stats["n_names_by_year"][year] = float(np.mean(ns)) if ns else None
        _log(
            f"{year}: {len(r2s)} regressions, mean R2 {stats['r2_by_year'][year]}, "
            f"mean names {stats['n_names_by_year'][year]}, saved dates {len(exp_rows)}"
        )
        del df, fr_rows, res_rows, exp_rows, cov_rows
    meta = {
        "factors": factors,
        "groups": groups,
        "styles": rk.STYLES,
        "ff48_to_group": {str(k): v for k, v in gmap.items()},
        "p1000_members_per_session": {str(int(k)): float(v) for k, v in members.items()},
        "params": {
            "hl_var": rk.HL_VAR,
            "hl_corr": rk.HL_CORR,
            "hl_spec": rk.HL_SPEC,
            "nw_lags": rk.NW_LAGS,
            "spec_shrink": rk.SPEC_SHRINK,
            "spec_floor_frac": rk.SPEC_FLOOR_FRAC,
            "style_clip": rk.STYLE_CLIP,
            "ret_clip": rk.RET_CLIP,
            "min_ind_members": rk.MIN_IND_MEMBERS,
        },
        "first_date": str(start.date()),
        "built_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "runtime_s": time.time() - t0,
        "peak_rss_mb": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0,
        "stats": stats,
    }
    (out / "meta.json").write_text(json.dumps(meta, indent=1))
    _log(f"done in {time.time() - t0:.0f}s, peak RSS {meta['peak_rss_mb']:.0f} MB")


if __name__ == "__main__":
    main()
