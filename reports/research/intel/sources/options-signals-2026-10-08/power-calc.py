"""T-20261005-36c power calculation. Read-only on data/sip/daily; writes JSON next to itself.

Run: scripts/run_capped.sh --mem 900M -- uv run python <this file>
"""
import json
import math
from pathlib import Path

import numpy as np
import polars as pl
from scipy import stats

OUT = Path(__file__).with_name("power-calc-output.json")
ETF_HINT = {"SPY", "QQQ", "IWM", "DIA", "TLT", "HYG", "LQD", "GLD", "SLV", "USO", "UNG", "VXX", "UVXY", "SQQQ", "TQQQ", "SPXL", "SPXS", "SOXL", "SOXS", "TNA", "TZA", "XLF", "XLE", "XLK", "XLV", "XLY", "XLP", "XLI", "XLU", "XLB", "XLRE", "XLC", "SMH", "SOXX", "ARKK", "EEM", "EFA", "FXI", "KWEB", "IBIT", "BITO", "VOO", "VTI", "IVV", "SCHD", "JEPI", "AGG", "BND", "TQQQ", "SH", "SDS", "UPRO", "LABU", "LABD", "TECL", "FNGU", "KRE", "XBI", "IYR", "VNQ", "EWZ", "EWJ", "EWY", "EWT", "RSP", "MDY", "IJR", "IJH", "SPYG", "SPYV", "QQQM", "IEMG", "VEA", "VWO", "BIL", "SGOV", "SHY", "IEF", "TIP", "GDX", "GDXJ", "SLV", "URA", "ETHA", "FBTC", "BITX", "NVDL", "TSLL", "CONL", "MSTU", "MSTR_ETF"}
N = 200
START = "2025-07-01"

lf = (
    pl.scan_parquet("data/sip/daily/202[56]/shard-*.parquet")
    .select("symbol", "timestamp", "close", "volume")
    .with_columns(pl.col("timestamp").dt.date().alias("d"))
    .filter(pl.col("d") >= pl.date(2025, 1, 1))
)
df = lf.collect()
last = df["d"].max()
adv = (
    df.filter(pl.col("d") > last - pl.duration(days=45))
    .with_columns((pl.col("close") * pl.col("volume")).alias("dv"))
    .group_by("symbol")
    .agg(pl.col("dv").mean().alias("adv"), pl.col("close").last().alias("px"))
    .filter((pl.col("px") >= 5) & (~pl.col("symbol").is_in(list(ETF_HINT))))
    .sort("adv", descending=True)
    .head(N)
)
syms = adv["symbol"].to_list()
wide = df.filter(pl.col("symbol").is_in(syms)).pivot(on="symbol", index="d", values="close").sort("d")
px = wide.drop("d").to_numpy()
dates = wide["d"].to_list()
res = {"universe": "top-%d by 45d mean dollar volume (price>=5, ETF hint list excluded; approximate)" % N,
       "last_date": str(last), "n_dates": len(dates), "adv_median_musd": float(np.median(adv["adv"].to_numpy()) / 1e6)}
sd = {}
mask = np.array([str(d) >= START for d in dates])
for h in (1, 5, 10, 21):
    r = px[h:] / px[:-h] - 1.0
    r = np.where(np.isfinite(r), r, np.nan)
    r = r[mask[: len(r)]]
    # winsorize at 1/99 pct within each date, demean, cross-sectional sd
    out = []
    for row in r:
        row = row[np.isfinite(row)]
        if len(row) < 100:
            continue
        lo, hi = np.percentile(row, [1, 99])
        row = np.clip(row, lo, hi)
        out.append(row.std(ddof=1))
    sd[h] = float(np.mean(out))
res["xs_return_sd_by_horizon_days"] = sd

# --- IC from published long-short spreads ---
# Normal signal, top-minus-bottom q-tile: E[z|top q] - E[z|bottom q] = 2*phi(z_q)/q
def spread_z(q):
    zq = stats.norm.ppf(1 - q)
    return 2 * stats.norm.pdf(zq) / q
res["spread_in_signal_sd"] = {"quintile": spread_z(0.2), "decile": spread_z(0.1)}

def ic_from_ls(ls_pct, horizon_days, q):
    return (ls_pct / 100) / (sd_h(horizon_days) * spread_z(q))

def sd_h(h):
    # interpolate sqrt-time scaling off the measured 21d and 5d values
    return sd[5] * math.sqrt(h / 5) if h not in sd else sd[h]

cases = {
    "CW2010_orig_4factor_alpha_1w": (0.50, 5, 0.2),
    "CW_thesis_2011_2015_4f_alpha_1w": (0.19, 5, 0.2),
    "XZZ2010_orig_FF3_alpha_1w_decile_like": (0.21, 5, 0.2),
    "arXiv_smirk_2015_17_quintile_21d": (0.409, 21, 0.2),
    "AABC2014_dVolCall_decile_1m": (1.09, 21, 0.1),
    "AABC2014_dCPVol_decile_1m": (1.68, 21, 0.1),
    "JohnsonSo2012_OS_decile_1w": (0.34, 5, 0.1),
    "BaliHov2009_CPVolSpread_quintile_1m": (1.045, 21, 0.2),
    "BaliHov2009_RIVolSpread_quintile_1m": (0.732, 21, 0.2),
    "Chordia2021_RNS_1w_1996_2015": (0.17, 5, 0.1),
}
res["implied_ic_at_horizon"] = {k: ic_from_ls(*v) for k, v in cases.items()}
# arXiv panel betas: 1-sd effect on 21d return
res["implied_ic_arxiv_panel_21d"] = {
    "iv_spread_full": 0.0214 * 0.107 / sd[21], "iv_spread_AI_regime": 0.0151 * 0.135 / sd[21],
    "rns_proxy_full": 0.0030 * 1.0 / sd[21], "smirk_AI_regime": 0.0060 * 0.124 / sd[21],
}

# --- power ---
def mde_ic(n_periods, n_names, sigma_mult=1.0, z_alpha=1.96, z_beta=0.8416):
    sig = sigma_mult / math.sqrt(n_names - 1)
    return (z_alpha + z_beta) * sig / math.sqrt(n_periods)

z_bonf3 = stats.norm.ppf(1 - 0.05 / 3 / 2)
res["z_alpha_bonferroni_3"] = float(z_bonf3)
T = 60
table = []
for h in (1, 5, 10, 21):
    k = T / h
    table.append({"horizon_days": h, "indep_periods_in_60d": k,
                  "mde_ic_at_that_horizon_t2_80pct": mde_ic(k, 200),
                  "mde_ic_bonf3": mde_ic(k, 200, z_alpha=z_bonf3),
                  "mde_ic_with_xs_dependence_1.3x": mde_ic(k, 200, 1.3),
                  # convert to the equivalent 21d IC via sqrt(h) accrual, then to LS spread (quintile, 21d)
                  "equiv_21d_ic_if_linear_accrual": mde_ic(k, 200) * math.sqrt(21 / h)})
res["mde_60d_N200"] = table
# under linear accrual, t = IC21 * sqrt(21)^-1 ... compute days needed directly
def days_needed(ic21, n_names, sigma_mult=1.0, z_alpha=1.96, z_beta=0.8416):
    ic1 = ic21 / math.sqrt(21)
    return ((z_alpha + z_beta) * sigma_mult / (ic1 * math.sqrt(n_names - 1))) ** 2

grid = {}
for n in (200, 400, 1000):
    grid[str(n)] = {f"ic21={ic}": {"days_t2_80pct": days_needed(ic, n), "days_bonf3": days_needed(ic, n, z_alpha=z_bonf3),
                                   "days_dep1.3": days_needed(ic, n, 1.3)} for ic in (0.01, 0.015, 0.02, 0.03, 0.04, 0.06)}
res["days_needed_by_universe_and_ic21"] = grid
res["ic21_detectable_in_60d_N200"] = mde_ic(60 / 21, 200) * 1.0
res["ic21_detectable_in_60d_N200_linear_equiv"] = 2.8016 / (math.sqrt(199)) / math.sqrt(60 / 1) * math.sqrt(21)
# quintile LS spread (21d, %) that corresponds to a given IC21 at N200 (for reporting)
res["ls21_quintile_pct_per_ic21"] = {str(ic): ic * sd[21] * spread_z(0.2) * 100 for ic in (0.01, 0.02, 0.03)}
OUT.write_text(json.dumps(res, indent=1))
print(json.dumps(res, indent=1)[:6000])
