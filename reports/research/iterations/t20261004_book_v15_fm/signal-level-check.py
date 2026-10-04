import numpy as np, pandas as pd
S = ["bm","ep","sp","cfp","gp_at","roe","op_at","neg_accruals","neg_asset_growth","neg_nsi_12m","mom_12_1","ind_mom_12_1","resid_mom_12_1","neg_beta_252","neg_idio_vol_63","sue_eps","sue_rev","cmp_opp_buy_60d","nonplan_buy_mcap_60d","neg_short_vol_ratio_21","neg_si_shares","seas_5y"]
d = pd.read_parquet("data/research/equity_book/regimes/signal_ls_daily.parquet")
if "trade_date" in d.columns: d = d.set_index("trade_date")
d.index = pd.to_datetime(d.index); d = d[S]
print("daily", d.index.min().date(), d.index.max().date(), "nan share", round(float(d.isna().mean().mean()),3))
m = (1 + d.fillna(0)).resample("ME").prod() - 1
def nwt(x, L=3):
    x = np.asarray(x, float); x = x[~np.isnan(x)]; n = len(x); mu = x.mean(); e = x - mu
    v = e @ e / n
    for l in range(1, L + 1): v += 2 * (1 - l / (L + 1)) * (e[l:] @ e[:-l]) / n
    return mu / np.sqrt(v / n), n
win = {"stress": ("2017-10-01","2023-08-31"), "recent": ("2024-01-01","2026-09-30"), "all": ("2017-10-01","2026-09-30")}
for lb in (1, 12):
    past = m.rolling(lb).sum().shift(1)
    sgn = np.sign(past)
    wml = []; tsfm = []; ew = []
    for t in m.index:
        r = m.loc[t]; s = sgn.loc[t]
        ok = s.notna() & (s != 0)
        if ok.sum() < 10: wml.append(np.nan); tsfm.append(np.nan); ew.append(np.nan); continue
        w_ = r[ok & (s > 0)]; l_ = r[ok & (s < 0)]
        wml.append(w_.mean() - l_.mean() if len(w_) and len(l_) else np.nan)
        tsfm.append((s[ok] * r[ok]).mean()); ew.append(r[ok].mean())
    R = pd.DataFrame({"wml": wml, "tsfm": tsfm, "ew": ew, "tilt": np.array(tsfm) * 0.5 + np.array(ew) * 0.5}, index=m.index)
    for k, (a, b) in win.items():
        x = R.loc[a:b].dropna()
        sr = lambda c: x[c].mean() / x[c].std() * np.sqrt(12)
        t, n = nwt(x["wml"])
        print(f"lb{lb:2d} {k:6s} n{n:3d} WML mean {x['wml'].mean()*1e4:6.1f}bp/mo NW t {t:5.2f} | SR ew {sr('ew'):5.2f} tsfm {sr('tsfm'):5.2f} 50/50 {sr('tilt'):5.2f} | corr(tsfm,ew) {x['tsfm'].corr(x['ew']):.2f}")
