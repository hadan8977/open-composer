# ruff: noqa: E501
"""T-20261006-18: library batch-1 factor values (point-in-time, U3000 grid of the equity book).

Stages (each writes its own parquet, nothing is kept in memory across stages)::

    scripts/run_capped.sh --mem 1.2G -- uv run python scripts/t18_factors.py events    # accounting events
    scripts/run_capped.sh --mem 1.2G -- uv run python scripts/t18_factors.py price     # price factors, per year
    scripts/run_capped.sh --mem 1.2G -- uv run python scripts/t18_factors.py assemble  # join + cross-section processing

Every factor is *oriented* (higher = expected higher return, the OSAP ``Sign`` baked in) and defined
in ``DEFINITIONS`` against the OSAP SignalDoc text (``data/raw/factor_libraries/osap/OSAP_SignalDoc.csv``).
Accounting values use the first-filed (as originally reported) facts and become usable on the session
``sec_fundamentals`` calls ``usable_session`` (first session after the filing).
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

EB = ROOT / "data/research/equity_book"
OUT = ROOT / "data/research/t18_library"
FACTS_OLD = ROOT / "data/features/sec_fundamentals/facts.parquet"
FACTS_EXTRA = OUT / "facts_extra.parquet"
EVENTS = OUT / "acct_events.parquet"
PRICE_DIR = OUT / "price_factors"
FACTOR_DIR = OUT / "factors"
DAY = np.timedelta64(1, "D")

# ---------------------------------------------------------------------------
# registry (preregistered; one row per first-batch ``book`` candidate)
# ---------------------------------------------------------------------------
# status: ok = computed; insufficient = not computable from local data (``missing`` says what)
DEFINITIONS: dict[str, dict] = {
    "ReturnSkew": dict(
        osap="ReturnSkew",
        sign=-1,
        kind="price",
        status="ok",
        note="skewness of 21 daily returns, >=15 obs (OSAP: previous month)",
    ),
    "ReturnSkew3F": dict(
        osap="ReturnSkew3F",
        sign=-1,
        kind="price",
        status="insufficient",
        missing="Fama-French daily factors mktrf/smb/hml (only monthly FF5 and industry files are local)",
    ),
    "BetaTailRisk": dict(
        osap="BetaTailRisk",
        sign=1,
        kind="price",
        status="ok",
        note="Kelly-Jiang tail beta; tailEX from all local stocks with prior close >= 5, monthly beta over up to 120 months, min 60 (local history starts 2016-02)",
    ),
    "GrAdExp": dict(
        osap="GrAdExp",
        sign=-1,
        kind="acct",
        status="ok",
        note="ln(adv_FY) - ln(adv_FY-1), both >= $0.1M, exclude lowest mcap decile",
    ),
    "RDAbility": dict(
        osap="RDAbility",
        sign=1,
        kind="acct",
        status="ok",
        note="mean slope of ln(sale growth) on ln(1+xrd/sale) lags 1..5 over 8 FYs, >=6 pairs, top tercile of xrd/sale, rd>0",
    ),
    "OrgCap": dict(
        osap="OrgCap",
        sign=1,
        kind="acct",
        status="ok",
        note="0.85*OrgCap + sga, init 4*sga, / assets; no GNP deflator, all fiscal year ends, history from 2009 (XBRL)",
    ),
    "EarningsStreak": dict(
        osap="EarningsStreak",
        sign=1,
        kind="acct",
        status="insufficient",
        missing="IBES analyst consensus mean estimate and announcement dates (no analyst-estimate data local)",
    ),
    "IntMom": dict(
        osap="IntMom", sign=1, kind="price", status="ok", note="close[t-126]/close[t-252]-1"
    ),
    "InvGrowth": dict(
        osap="InvGrowth",
        sign=-1,
        kind="acct",
        status="ok",
        note="FY inventory growth (no deflator: common factor in the cross-section), SIC 1-digit 4/6 and at/ppent<=0 dropped",
    ),
    "Cash": dict(
        osap="Cash",
        sign=1,
        kind="acct",
        status="ok",
        note="cash and short-term investments / total assets, latest quarter",
    ),
    "PctAcc": dict(
        osap="PctAcc",
        sign=-1,
        kind="acct",
        status="ok",
        note="(ib - oancf)/|ib| annual, ib=0 -> 0.01; ib = income from continuing operations else net income",
    ),
    "ChTax": dict(
        osap="ChTax",
        sign=1,
        kind="acct",
        status="ok",
        note="4-quarter change in quarterly income tax expense / assets 4 quarters earlier",
    ),
    "OPLeverage": dict(
        osap="OPLeverage",
        sign=1,
        kind="acct",
        status="ok",
        note="(sga + cogs)/assets, latest FY, sga missing -> 0",
    ),
    "ChEQ": dict(
        osap="ChEQ",
        sign=-1,
        kind="acct",
        status="ok",
        note="book equity / book equity 1y earlier - 1 (latest quarter vs same quarter a year before), both > 0",
    ),
    "roaq": dict(
        osap="roaq",
        sign=1,
        kind="acct",
        status="ok",
        note="quarterly net income / total assets of the previous quarter",
    ),
    "MomOffSeason06YrPlus": dict(
        osap="MomOffSeason06YrPlus",
        sign=-1,
        kind="price",
        status="ok",
        note="mean monthly return of the non-same calendar months, lags 61..120 months; needs >=30 months; local history starts 2016-02 so valid only from about 2025",
    ),
    "MomOffSeason16YrPlus": dict(
        osap="MomOffSeason16YrPlus",
        sign=-1,
        kind="price",
        status="insufficient",
        missing="monthly returns 16-20 years back (need prices from 1996-2010; local history starts 2016)",
    ),
    "MomSeason06YrPlus": dict(
        osap="MomSeason06YrPlus",
        sign=1,
        kind="price",
        status="ok",
        note="mean return of the same calendar month in years 6..10 back, >=3 of 5 years; valid from about 2025",
    ),
    "MomSeason11YrPlus": dict(
        osap="MomSeason11YrPlus",
        sign=1,
        kind="price",
        status="insufficient",
        missing="monthly returns 11-15 years back (need prices from 2001-2015; local history starts 2016)",
    ),
    "MomSeason16YrPlus": dict(
        osap="MomSeason16YrPlus",
        sign=1,
        kind="price",
        status="insufficient",
        missing="monthly returns 16-20 years back (need prices from 1996-2010; local history starts 2016)",
    ),
    "CompositeDebtIssuance": dict(
        osap="CompositeDebtIssuance",
        sign=-1,
        kind="acct",
        status="ok",
        note="ln(dltt+dlc) - ln(same 5 years earlier); LongTermDebtNoncurrent (fallback LongTermDebt) + current debt",
    ),
    "BPEBM": dict(
        osap="BPEBM",
        sign=-1,
        kind="acct",
        status="ok",
        note="BP - EBM, dc and dvpa set to 0 (no XBRL equivalent), latest quarter balance sheet, mve = panel market cap",
    ),
    "EBM": dict(
        osap="EBM",
        sign=1,
        kind="acct",
        status="ok",
        note="enterprise book-to-market, dc and dvpa set to 0, latest quarter balance sheet, mve = panel market cap",
    ),
    "ConvDebt": dict(
        osap="ConvDebt",
        sign=-1,
        kind="acct",
        status="insufficient",
        missing="Compustat dc (deferred charges) and cshrc (shares reserved for conversion); no comparable XBRL tag, a convertible-note tag would be a different signal",
    ),
    "SUE": dict(
        osap="(QuantConnect SUE)",
        sign=1,
        kind="book",
        status="ok",
        note="book column sue_eps_raw (EPS seasonal-difference SUE, 8-quarter std); same definition as the book's earnings theme member, so overlap is expected",
    ),
}
COMPUTED = [k for k, v in DEFINITIONS.items() if v["status"] == "ok"]


# ---------------------------------------------------------------------------
# accounting events
# ---------------------------------------------------------------------------
class CikData:
    """First-filed facts of one company as sorted numpy arrays per (concept, kind)."""

    def __init__(self, df: pd.DataFrame) -> None:
        self.d: dict[tuple[str, str], tuple[np.ndarray, np.ndarray, np.ndarray]] = {}
        for (c, k), g in df.groupby(["concept", "period_kind"], sort=False):
            g = g.sort_values(["period_end", "filed"], kind="stable").drop_duplicates(
                "period_end", keep="first"
            )
            self.d[(c, k)] = (
                g["period_end"].to_numpy("datetime64[D]"),
                g["val"].to_numpy("float64"),
                g["usable_session"].to_numpy("datetime64[D]"),
            )

    def latest(self, c: str, k: str, t: np.datetime64):
        a = self.d.get((c, k))
        if a is None:
            return None
        nz = np.flatnonzero(a[2] <= t)
        if nz.size == 0:
            return None
        i = nz[-1]
        return a[0][i], a[1][i]

    def at_end(self, c: str, k: str, t: np.datetime64, end: np.datetime64, tol: int = 40):
        """Value of the known period whose end is within ``tol`` days of ``end``."""
        a = self.d.get((c, k))
        if a is None:
            return None
        ok = (a[2] <= t) & (np.abs((a[0] - end) / DAY) <= tol)
        nz = np.flatnonzero(ok)
        if nz.size == 0:
            return None
        j = nz[np.argmin(np.abs((a[0][nz] - end) / DAY))]
        return a[1][j]

    def known(self, c: str, k: str, t: np.datetime64):
        a = self.d.get((c, k))
        if a is None:
            return None
        m = a[2] <= t
        return a[0][m], a[1][m]

    def times(self) -> np.ndarray:
        return np.unique(np.concatenate([a[2] for a in self.d.values()]))


def _ln(x: float) -> float:
    return float(np.log(x)) if x is not None and x > 0 else np.nan


def org_cap(ends: np.ndarray, sga: np.ndarray) -> float:
    oc = 4.0 * sga[0]
    for i in range(1, len(sga)):
        gap = max(int(round((ends[i] - ends[i - 1]) / np.timedelta64(365, "D"))), 1)
        oc = oc * 0.85**gap + sga[i]
    return float(oc)


def rd_ability(fy_ends, sale, rd_ends, rd) -> tuple[float, float]:
    """(RDAbility, latest xrd/sale) from the known FY series; NaN when the OSAP conditions fail."""
    if len(sale) < 9 or len(rd) < 6:
        return np.nan, np.nan
    s = pd.Series(sale, index=pd.DatetimeIndex(fy_ends).year)
    s = s[~s.index.duplicated(keep="last")]
    r = pd.Series(rd, index=pd.DatetimeIndex(rd_ends).year)
    r = r[~r.index.duplicated(keep="last")]
    years = s.index.to_numpy()
    if len(years) < 9:
        return np.nan, np.nan
    last = years.max()
    if last not in r.index or not r[last] > 0 or not s[last] > 0:
        return np.nan, np.nan
    yrs = np.arange(last - 7, last + 1)
    window_rd = r.reindex(yrs)
    if window_rd.notna().sum() < 6 or (window_rd.fillna(0) > 0).sum() < 4:
        return np.nan, np.nan
    sale_y = s.reindex(np.arange(last - 8, last + 1))
    g = pd.Series(np.log(sale_y.to_numpy()[1:] / sale_y.to_numpy()[:-1]), index=yrs)
    x_all = np.log1p(
        r.reindex(np.arange(last - 13, last + 1)) / s.reindex(np.arange(last - 13, last + 1))
    )
    slopes = []
    for lag in range(1, 6):
        x = x_all.reindex(yrs - lag).to_numpy()
        y = g.to_numpy()
        ok = np.isfinite(x) & np.isfinite(y)
        if ok.sum() < 6:
            continue
        xm, ym = x[ok].mean(), y[ok].mean()
        vx = ((x[ok] - xm) ** 2).sum()
        if vx <= 0:
            continue
        slopes.append(((x[ok] - xm) * (y[ok] - ym)).sum() / vx)
    if len(slopes) < 5:
        return np.nan, np.nan
    return float(np.mean(slopes)), float(r[last] / s[last])


def cik_events(cik: int, df: pd.DataFrame) -> list[dict]:
    D = CikData(df)
    out = []
    for t in D.times():
        row: dict = {"cik": cik, "T": t}
        ta = D.latest("total_assets", "instant", t)
        # Cash, ChEQ, roaq, ChTax, CompDebt, EBM components: quarterly balance sheet
        che = D.latest("cash_sti", "instant", t)
        if ta is not None and che is not None and abs((ta[0] - che[0]) / DAY) <= 30 and ta[1] > 0:
            row["Cash"] = che[1] / ta[1]
        ceq = D.latest("stockholders_equity", "instant", t)
        if ceq is not None:
            lag = D.at_end(
                "stockholders_equity", "instant", t, ceq[0] - np.timedelta64(365, "D"), 45
            )
            if lag is not None and lag > 0 and ceq[1] > 0:
                row["ChEQ"] = ceq[1] / lag - 1.0
            # EBM components (missing debt / preferred count as 0, che and ceq required)
            if che is not None and abs((ceq[0] - che[0]) / DAY) <= 30:
                dl = D.at_end("ltd_nc", "instant", t, ceq[0], 30)
                dc_ = D.at_end("debt_cur", "instant", t, ceq[0], 30)
                pf = D.at_end("pref", "instant", t, ceq[0], 30)
                row.update(
                    ebm_ceq=ceq[1],
                    ebm_che=che[1],
                    ebm_dltt=0.0 if dl is None else dl,
                    ebm_dlc=0.0 if dc_ is None else dc_,
                    ebm_pref=0.0 if pf is None else pf,
                    ebm_end=ceq[0],
                )
            # CompositeDebtIssuance
            dl = D.at_end("ltd_nc", "instant", t, ceq[0], 30)
            if dl is not None:
                dc_ = D.at_end("debt_cur", "instant", t, ceq[0], 30) or 0.0
                end5 = ceq[0] - np.timedelta64(5 * 365, "D")
                dl5 = D.at_end("ltd_nc", "instant", t, end5, 60)
                if dl5 is not None:
                    dc5 = D.at_end("debt_cur", "instant", t, end5, 60) or 0.0
                    row["CompositeDebtIssuance"] = _ln(dl + dc_) - _ln(dl5 + dc5)
        ni = D.latest("net_income", "Q", t)
        if ni is not None:
            tae = D.at_end("total_assets", "instant", t, ni[0] - np.timedelta64(91, "D"), 25)
            if tae is not None and tae > 0:
                row["roaq"] = ni[1] / tae
        tx = D.latest("tax", "Q", t)
        if tx is not None:
            tx4 = D.at_end("tax", "Q", t, tx[0] - np.timedelta64(365, "D"), 30)
            ta4 = D.at_end("total_assets", "instant", t, tx[0] - np.timedelta64(365, "D"), 45)
            if tx4 is not None and ta4 is not None and ta4 > 0:
                row["ChTax"] = (tx[1] - tx4) / ta4
        # annual items
        ib = D.latest("ib_cont", "FY", t)
        nif = D.latest("net_income", "FY", t)
        ocf = D.latest("operating_cash_flow", "FY", t)
        ibv = None
        if ib is not None and nif is not None and ib[0] >= nif[0] - np.timedelta64(10, "D"):
            ibv, ibe = ib[1], ib[0]
        elif nif is not None:
            ibv, ibe = nif[1], nif[0]
        if ibv is not None and ocf is not None and abs((ocf[0] - ibe) / DAY) <= 10:
            den = abs(ibv) if ibv != 0 else 0.01
            row["PctAcc"] = (ibv - ocf[1]) / den
        cogs = D.latest("cogs", "FY", t)
        if cogs is not None:
            ta_c = D.at_end("total_assets", "instant", t, cogs[0], 30)
            sg = D.at_end("sga", "FY", t, cogs[0], 10)
            if ta_c is not None and ta_c > 0:
                row["OPLeverage"] = (cogs[1] + (0.0 if sg is None else sg)) / ta_c
        adv = D.latest("adv", "FY", t)
        if adv is not None:
            adv1 = D.at_end("adv", "FY", t, adv[0] - np.timedelta64(365, "D"), 45)
            if adv1 is not None and adv[1] >= 1e5 and adv1 >= 1e5:
                row["GrAdExp"] = _ln(adv[1]) - _ln(adv1)
        inv = D.latest("inventory", "instant", t)
        fy_end = nif[0] if nif is not None else None
        if fy_end is not None:
            inv = (fy_end, D.at_end("inventory", "instant", t, fy_end, 10))
            if inv[1] is not None:
                inv1 = D.at_end("inventory", "instant", t, fy_end - np.timedelta64(365, "D"), 30)
                ppe = D.at_end("ppent", "instant", t, fy_end, 10)
                tafy = D.at_end("total_assets", "instant", t, fy_end, 10)
                if (
                    inv1 is not None
                    and inv1 > 0
                    and inv[1] > 0
                    and ppe is not None
                    and ppe > 0
                    and tafy is not None
                    and tafy > 0
                ):
                    row["InvGrowth"] = inv[1] / inv1 - 1.0
        sg_known = D.known("sga", "FY", t)
        if sg_known is not None and len(sg_known[0]) >= 3:
            ta_s = D.at_end("total_assets", "instant", t, sg_known[0][-1], 30)
            if ta_s is not None and ta_s > 0:
                row["OrgCap"] = org_cap(sg_known[0], sg_known[1]) / ta_s
        rv = D.known("revenue", "FY", t)
        rk = D.known("rd", "FY", t)
        if rv is not None and rk is not None:
            a, b = rd_ability(rv[0], rv[1], rk[0], rk[1])
            row["RDAbility"], row["rdsale"] = a, b
        # age references so a stale value is not carried for years
        row["age_q"] = (
            ni[0] if ni is not None else (ta[0] if ta is not None else np.datetime64("NaT"))
        )
        row["age_fy"] = nif[0] if nif is not None else np.datetime64("NaT")
        out.append(row)
    return out


def build_events() -> None:
    from scripts import build_sec_xbrl_fundamentals as bx

    OUT.mkdir(parents=True, exist_ok=True)
    keep_old = [
        "total_assets",
        "net_income",
        "stockholders_equity",
        "operating_cash_flow",
        "revenue",
    ]
    old = pd.read_parquet(FACTS_OLD)
    old = old[old["concept"].isin(keep_old)]
    ni = old[old["concept"] == "net_income"]
    ni = ni[~ni["restated"]]
    d4 = bx.derive_q4(ni.assign(derived_q4=False))
    d4 = d4[d4["derived_q4"]]
    old = old[~old["restated"]]
    old = pd.concat([old, d4], ignore_index=True)
    ex = pd.read_parquet(FACTS_EXTRA)
    ex = ex[~ex["restated"]]
    cols = ["cik", "concept", "period_kind", "period_end", "val", "filed", "usable_session"]
    allf = pd.concat([old[cols], ex[cols]], ignore_index=True)
    allf = allf[allf["period_kind"].isin(["Q", "FY", "instant"])]
    del old, ex, d4, ni
    rows: list[dict] = []
    n = 0
    for cik, g in allf.groupby("cik", sort=True):
        rows.extend(cik_events(int(cik), g))
        n += 1
        if n % 500 == 0:
            print(f"cik {n}", flush=True)
    ev = pd.DataFrame(rows)
    ev["T"] = pd.to_datetime(ev["T"])
    for c in ("age_q", "age_fy", "ebm_end"):
        if c in ev:
            ev[c] = pd.to_datetime(ev[c])
    ev = ev.sort_values(["T", "cik"]).reset_index(drop=True)
    ev.to_parquet(EVENTS, index=False)
    print(ev.shape)
    print(ev.notna().mean().round(3).to_string())


# ---------------------------------------------------------------------------
# price factors
# ---------------------------------------------------------------------------
def load_close_wide() -> tuple[pd.DatetimeIndex, pd.Index, np.ndarray]:
    """Adjusted closes of every symbol in ``prices/``, float32, on the panel calendar."""
    cal = pd.DatetimeIndex(pd.read_parquet(EB / "panel/_calendar.parquet")["trade_date"])
    syms: set[str] = set()
    files = sorted((EB / "prices").glob("*.parquet"))
    for f in files:
        syms |= set(pd.read_parquet(f, columns=["symbol"])["symbol"])
    symbols = pd.Index(sorted(syms))
    c = np.full((len(cal), len(symbols)), np.nan, dtype="float32")
    for f in files:
        df = pd.read_parquet(f, columns=["trade_date", "symbol", "close"]).drop_duplicates(
            ["trade_date", "symbol"], keep="last"
        )
        r = cal.get_indexer(pd.DatetimeIndex(df["trade_date"]))
        k = symbols.get_indexer(df["symbol"])
        ok = (r >= 0) & (k >= 0)
        c[r[ok], k[ok]] = df["close"].to_numpy("float32")[ok]
    return cal, symbols, c


def month_table(cal: pd.DatetimeIndex) -> pd.DataFrame:
    """One row per calendar month present: last session position and month index (year*12+month-1)."""
    df = pd.DataFrame({"pos": np.arange(len(cal)), "mi": cal.year * 12 + cal.month - 1})
    return df.groupby("mi").agg(last=("pos", "max")).reset_index()


def tail_ex(cal: pd.DatetimeIndex, close: np.ndarray, months: pd.DataFrame) -> np.ndarray:
    """Kelly-Jiang monthly tailEX: mean of ln(r / p5) over pooled daily returns below the month's 5th percentile
    (stocks with previous close >= 5)."""
    out = np.full(len(months), np.nan)
    mi_of_pos = cal.year * 12 + cal.month - 1
    for j, m in enumerate(months["mi"].to_numpy()):
        pos = np.flatnonzero(mi_of_pos == m)
        pos = pos[pos > 0]
        r = close[pos] / close[pos - 1] - 1.0
        prev = close[pos - 1]
        x = r[(prev >= 5) & np.isfinite(r)]
        if x.size < 1000:
            continue
        p5 = np.quantile(x, 0.05)
        below = x[x < p5]
        if p5 < 0 and below.size:
            out[j] = float(np.mean(np.log(below / p5)))
    return out


def monthly_returns(close: np.ndarray, months: pd.DataFrame) -> np.ndarray:
    """(n_months, N) month-end to month-end returns; the first month has none."""
    me = close[months["last"].to_numpy()].astype("float64")
    out = np.full_like(me, np.nan)
    out[1:] = me[1:] / me[:-1] - 1.0
    return out


def beta_tail(mret: np.ndarray, te: np.ndarray, window: int = 120, min_obs: int = 60) -> np.ndarray:
    """(n_months, N) slope of the stock's monthly return on tailEX over the trailing window ending at each month."""
    n, k = mret.shape
    out = np.full((n, k), np.nan)
    for j in range(n):
        lo = max(0, j - window + 1)
        x = te[lo : j + 1]
        y = mret[lo : j + 1]
        okx = np.isfinite(x)[:, None] & np.isfinite(y)
        cnt = okx.sum(axis=0)
        xm = np.where(okx, x[:, None], 0.0)
        ym = np.where(okx, y, 0.0)
        with np.errstate(invalid="ignore", divide="ignore"):
            mx = xm.sum(0) / cnt
            my = ym.sum(0) / cnt
            cov = (np.where(okx, (x[:, None] - mx) * (y - my), 0.0)).sum(0)
            var = (np.where(okx, (x[:, None] - mx) ** 2, 0.0)).sum(0)
            b = cov / var
        out[j] = np.where(cnt >= min_obs, b, np.nan)
    return out


def seasonality(mret: np.ndarray, mi: np.ndarray, target: int) -> tuple[np.ndarray, np.ndarray]:
    """Season (mean of same-month returns 6..10 years back, >=3 of 5) and off-season (mean of the other months of
    lags 61..120, >=30) for the predicted month index ``target``."""
    k = mret.shape[1]
    pos = {int(m): i for i, m in enumerate(mi)}
    same = [pos[target - 12 * y] for y in range(6, 11) if (target - 12 * y) in pos]
    other = [pos[target - L] for L in range(61, 121) if L % 12 != 0 and (target - L) in pos]
    season = np.full(k, np.nan)
    off = np.full(k, np.nan)
    if same:
        a = mret[same]
        ok = np.isfinite(a)
        s = np.where(ok, a, 0.0).sum(0) / np.maximum(ok.sum(0), 1)
        season = np.where(ok.sum(0) >= 3, s, np.nan)
    if other:
        a = mret[other]
        ok = np.isfinite(a)
        s = np.where(ok, a, 0.0).sum(0) / np.maximum(ok.sum(0), 1)
        off = np.where(ok.sum(0) >= 30, s, np.nan)
    return season, off


def rolling_skew(ret: np.ndarray, window: int = 21, min_obs: int = 15) -> np.ndarray:
    return pd.DataFrame(ret).rolling(window, min_periods=min_obs).skew().to_numpy("float32")


def build_price() -> None:
    PRICE_DIR.mkdir(parents=True, exist_ok=True)
    cal, symbols, close = load_close_wide()
    months = month_table(cal)
    mret = monthly_returns(close, months)
    te = tail_ex(cal, close, months)
    btm = beta_tail(mret, te)
    mi = months["mi"].to_numpy()
    pos_year = cal.year.to_numpy()
    mi_day = (cal.year * 12 + cal.month - 1).to_numpy()
    # month completed by the close of each session: the month itself if the session is its last, else the previous month
    last_pos = set(months["last"].to_numpy().tolist())
    for year in range(2017, 2027):
        rows = np.flatnonzero(pos_year == year)
        sig = pd.read_parquet(EB / f"signals/{year}.parquet", columns=["trade_date", "symbol"])
        sig_syms = pd.Index(sorted(set(sig["symbol"])))
        cols = symbols.get_indexer(sig_syms)
        keep = cols >= 0
        sig_syms, cols = sig_syms[keep], cols[keep]
        lo = max(rows[0] - 260, 0)
        sub = close[lo : rows[-1] + 1][:, cols].astype("float64")
        ret = np.vstack([np.full((1, sub.shape[1]), np.nan), sub[1:] / sub[:-1] - 1.0])
        sk = rolling_skew(ret)
        off = rows[0] - lo
        d = {"ReturnSkew": sk[off:]}
        n = len(rows)
        intmom = np.full((n, sub.shape[1]), np.nan)
        for i in range(n):
            p = off + i
            if p - 252 >= 0:
                intmom[i] = sub[p - 126] / sub[p - 252] - 1.0
        d["IntMom"] = intmom
        # seasonality and tail beta
        seas = np.full((n, sub.shape[1]), np.nan)
        offs = np.full((n, sub.shape[1]), np.nan)
        btail = np.full((n, sub.shape[1]), np.nan)
        cache: dict[int, tuple[np.ndarray, np.ndarray]] = {}
        for i, p in enumerate(rows):
            nxt = p + 1
            tgt = int(mi_day[nxt]) if nxt < len(cal) else int(mi_day[p]) + 1
            if tgt not in cache:
                s_, o_ = seasonality(mret, mi, tgt)
                cache[tgt] = (s_[cols], o_[cols])
            seas[i], offs[i] = cache[tgt]
            done_m = int(mi_day[p]) if p in last_pos else int(mi_day[p]) - 1
            j = np.flatnonzero(mi == done_m)
            if j.size:
                btail[i] = btm[j[0]][cols]
        d["MomSeason06YrPlus"] = seas
        d["MomOffSeason06YrPlus"] = offs
        d["BetaTailRisk"] = btail
        frames = []
        dates = cal[rows]
        base = pd.DataFrame(
            {
                "trade_date": np.repeat(dates.to_numpy(), len(sig_syms)),
                "symbol": np.tile(sig_syms.to_numpy(), n),
            }
        )
        for k_, v in d.items():
            base[k_] = v.reshape(-1).astype("float32")
        base = base.merge(sig, on=["trade_date", "symbol"], how="inner")
        base.to_parquet(PRICE_DIR / f"{year}.parquet", index=False)
        print(
            year,
            base.shape,
            base.drop(columns=["trade_date", "symbol"]).notna().mean().round(3).to_dict(),
            flush=True,
        )
        del sub, ret, sk, base, d, seas, offs, btail, intmom, frames
    pd.DataFrame({"mi": mi, "tail_ex": te}).to_parquet(OUT / "tail_ex_monthly.parquet", index=False)


# ---------------------------------------------------------------------------
# assemble: join everything on the U3000 grid of the book, oriented raw values
# ---------------------------------------------------------------------------
FY_BASED = ("GrAdExp", "PctAcc", "OPLeverage", "InvGrowth", "OrgCap", "RDAbility")
Q_BASED = ("Cash", "ChEQ", "roaq", "ChTax", "CompositeDebtIssuance", "EBM", "BPEBM")
FY_MAX_AGE_DAYS, Q_MAX_AGE_DAYS = 550, 230


def assemble_year(year: int, events: pd.DataFrame, sic: pd.Series) -> pd.DataFrame:
    sig = pd.read_parquet(
        EB / f"signals/{year}.parquet", columns=["trade_date", "symbol", "ind_code", "sue_eps_raw"]
    )
    pan = pd.read_parquet(
        EB / f"panel/{year}.parquet",
        columns=["trade_date", "symbol", "mcap", "in_u3000", "in_p1000"],
    )
    pf = pd.read_parquet(PRICE_DIR / f"{year}.parquet")
    g = sig.merge(pan, on=["trade_date", "symbol"], how="left").merge(
        pf, on=["trade_date", "symbol"], how="left"
    )
    fund = pd.read_parquet(
        ROOT / f"data/features/sec_fundamentals_daily/{year}.parquet",
        columns=["symbol", "cik", "trade_date"],
    )
    cmap = fund.sort_values("trade_date").drop_duplicates("symbol", keep="last")[["symbol", "cik"]]
    g = g.merge(cmap, on="symbol", how="left")
    g = g.sort_values("trade_date").reset_index(drop=True)
    ev = events[(events["T"] <= g["trade_date"].max())].sort_values("T")
    ev = ev.rename(columns={"cik": "cik_ev"})
    g["cik"] = g["cik"].astype("Int64")
    has = g["cik"].notna()
    left = g[has].copy()
    left["cik"] = left["cik"].astype("int64")
    ev["cik_ev"] = ev["cik_ev"].astype("int64")
    m = pd.merge_asof(
        left.sort_values("trade_date"),
        ev,
        left_on="trade_date",
        right_on="T",
        left_by="cik",
        right_by="cik_ev",
        tolerance=pd.Timedelta(days=FY_MAX_AGE_DAYS + 120),
        direction="backward",
    )
    g = _merge_back(g, m)
    td = g["trade_date"]
    age_fy = (td - g["age_fy"]).dt.days
    age_q = (td - g["age_q"]).dt.days
    for c in FY_BASED:
        if c in g:
            g.loc[~(age_fy <= FY_MAX_AGE_DAYS), c] = np.nan
    for c in Q_BASED:
        if c in g:
            g.loc[~(age_q <= Q_MAX_AGE_DAYS), c] = np.nan
    mv = g["mcap"].to_numpy("float64")
    che, ceq = g["ebm_che"], g["ebm_ceq"]
    debt = g["ebm_dltt"] + g["ebm_dlc"]
    with np.errstate(invalid="ignore", divide="ignore"):
        bp = (ceq + g["ebm_pref"]) / mv
        ebm = (ceq + che - debt + g["ebm_pref"]) / (mv + che - debt + g["ebm_pref"])
    ok_age = age_q <= Q_MAX_AGE_DAYS
    g["EBM"] = np.where(ok_age & (mv > 0), ebm, np.nan)
    g["BPEBM"] = np.where(ok_age & (mv > 0), bp - ebm, np.nan)
    # cross-sectional / classification filters of the OSAP definitions
    q10 = g.groupby("trade_date")["mcap"].transform(lambda x: x.quantile(0.10))
    g.loc[g["mcap"] < q10, "GrAdExp"] = np.nan
    if "RDAbility" in g:
        q67 = g.groupby("trade_date")["rdsale"].transform(lambda x: x.quantile(2 / 3))
        g.loc[~(g["rdsale"] >= q67), "RDAbility"] = np.nan
    sic1 = g["cik"].map(sic) // 1000
    g.loc[sic1.isin([4, 6]), "InvGrowth"] = np.nan
    out = g[["trade_date", "symbol", "ind_code", "mcap", "in_u3000", "in_p1000"]].copy()
    for name in COMPUTED:
        d = DEFINITIONS[name]
        col = "sue_eps_raw" if name == "SUE" else name
        out[name] = (d["sign"] * g[col]).astype("float32")
    return out


def _merge_back(g: pd.DataFrame, m: pd.DataFrame) -> pd.DataFrame:
    cols = [c for c in m.columns if c not in g.columns]
    return g.merge(m[["trade_date", "symbol", *cols]], on=["trade_date", "symbol"], how="left")


def build_assemble() -> None:
    FACTOR_DIR.mkdir(parents=True, exist_ok=True)
    ev = pd.read_parquet(EVENTS)
    sic_df = pd.read_parquet(
        ROOT / "data/features/sic_map/sic_map.parquet", columns=["cik", "sic"]
    ).dropna()
    sic = (
        sic_df.drop_duplicates("cik")
        .set_index(sic_df.drop_duplicates("cik")["cik"].astype("int64"))["sic"]
        .astype("int64")
    )
    for year in range(2017, 2027):
        out = assemble_year(year, ev, sic)
        out.to_parquet(FACTOR_DIR / f"{year}.parquet", index=False)
        cov = (
            out[COMPUTED].notna().groupby(out["in_u3000"].fillna(False).to_numpy()).mean().round(3)
        )
        print(year, out.shape, cov.loc[True].to_dict() if True in cov.index else {}, flush=True)


if __name__ == "__main__":
    stage = sys.argv[1] if len(sys.argv) > 1 else ""
    if stage == "events":
        build_events()
    elif stage == "price":
        build_price()
    elif stage == "assemble":
        build_assemble()
    else:
        raise SystemExit(f"unknown stage {stage}")
