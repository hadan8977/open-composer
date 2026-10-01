"""S1: signal library v1 (design section 4, queue task T-20261001-05).

One long table per year, ``data/research/equity_book/signals/<year>.parquet``: U3000 members only,
every session.  For every signal ``<name>`` three columns:

* ``<name>_raw``   float32, the *oriented* raw value (higher = expected higher return; the sign of
  the literature direction is baked in, e.g. ``neg_accruals_raw = -accruals``);
* ``<name>``       float32, the processed cross-sectional score (below), 0 where missing;
* ``<name>_cov``   bool, the raw value exists (finite, point-in-time visible).

Processing, per session and per signal, within U3000: (1) winsorise at the 1st / 99th percentile,
(2) map ranks to normal scores (``Phi^-1((rank - 0.5) / n)``, ties share their average rank),
(3) demean value and quality scores within their industry group, (4) missing -> 0 (``_cov`` stays
False).  Industry group = the risk model's grouping (``risk/meta.json`` ``ff48_to_group``, the
output of :func:`open_composer.research.equity_book.risk.industry_groups`); an unclassified name
is never demeaned.

Slow themes (the M0 composite, design section 5): value, quality, investment, momentum, low risk,
earnings, insider, short information, seasonality.  ``theme_<theme>`` is the mean of the processed
scores of the theme's signals (a missing signal counts as 0), ``m0_composite`` the mean of the nine
theme scores, ``m0_n_themes`` the number of themes with at least one covered signal.  The fast
signals (21-day industry-adjusted reversal, ON252, news attention, alpha101 / alpha191 columns with
at least 90% coverage) are produced for ML only and never enter the composite.

Point-in-time rules (all tested):

* fundamentals: ``sec_fundamentals_daily`` is aligned to the first session *after* the filing; the
  annual flows (net income, revenue, operating cash flow, operating income) are rebuilt from
  ``sec_fundamentals/facts.parquet`` with the same rule (``usable_session`` <= trade date, and a row
  whose ``usable_session`` is not after its ``filed`` date is dropped);
* insider: a row counts on session ``t`` iff ``visible_at`` <= 16:00 America/New_York of ``t``;
* short volume / short interest: ``visible_date`` <= ``t`` (a row visible at ``t + 1`` is masked);
* news: ``visible_at`` as insider.

Known data caveat (reported, not corrected here): the panel ``mcap`` is ``close x SEC cover-page
shares`` with ``close`` retroactively split-adjusted and the share count as filed, so a name that
split *after* ``t`` has its ``t`` market cap understated by the split factor unless the factor is
>= 10 (``mcap_source = adv_fallback_outlier``).  Value ratios and the insider ratio divide by that
``mcap``; short interest uses the as-filed share count instead.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
from scipy.special import ndtri
from scipy.stats import rankdata

from open_composer.research.equity_book import risk as rk
from open_composer.research.equity_book.panel import DEFAULT_DIR

SIGNALS_DIR = DEFAULT_DIR / "signals"
WINSOR_LO, WINSOR_HI = 0.01, 0.99
MIN_INDUSTRY_MEMBERS = rk.MIN_IND_MEMBERS
NY = ZoneInfo("America/New_York")
FLOAT32_SAFE = 1e30

THEMES = (
    "value",
    "quality",
    "investment",
    "momentum",
    "low_risk",
    "earnings",
    "insider",
    "short_info",
    "seasonality",
)


@dataclass(frozen=True)
class SignalSpec:
    name: str
    theme: str  # one of THEMES, or "fast"
    demean: bool = False  # industry demeaning (value and quality)
    note: str = ""


def _s(name: str, theme: str, demean: bool = False, note: str = "") -> SignalSpec:
    return SignalSpec(name, theme, demean, note)


SLOW_SIGNALS: tuple[SignalSpec, ...] = (
    _s("bm", "value", True, "stockholders_equity / mcap"),
    _s("ep", "value", True, "annual net income / mcap"),
    _s("sp", "value", True, "annual revenue / mcap"),
    _s("cfp", "value", True, "annual operating cash flow / mcap"),
    _s("gp_at", "quality", True, "annual gross profit / total assets (Novy-Marx)"),
    _s("roe", "quality", True, "annual net income / stockholders equity"),
    _s("op_at", "quality", True, "annual operating income / total assets"),
    _s("neg_accruals", "quality", True, "-(NI - OCF) / avg assets (Sloan)"),
    _s("neg_asset_growth", "investment", False, "-yoy total assets growth (Cooper-Gulen-Schill)"),
    _s("neg_nsi_12m", "investment", False, "-ln(shares_t / shares_t-252), nsi table"),
    _s("mom_12_1", "momentum", False, "close[t-21] / close[t-252] - 1"),
    _s("ind_mom_12_1", "momentum", False, "mean mom_12_1 of the industry group (U3000 members)"),
    _s("resid_mom_12_1", "momentum", False, "sum of residuals t-252..t-21 / residual vol (Blitz)"),
    _s("neg_beta_252", "low_risk", False, "-Vasicek-shrunk 252d beta to SPY"),
    _s("neg_idio_vol_63", "low_risk", False, "-63d idiosyncratic vol"),
    _s("sue_eps", "earnings", False, "SUE on diluted EPS (seasonal random walk)"),
    _s("sue_rev", "earnings", False, "SUE on revenue"),
    _s("cmp_opp_buy_60d", "insider", False, "Cohen-Malloy-Pomorski opportunistic buys, 60d"),
    _s("nonplan_buy_mcap_60d", "insider", False, "net non-plan insider buy usd 60d / mcap"),
    _s("neg_short_vol_ratio_21", "short_info", False, "-21d mean short volume ratio"),
    _s("neg_si_shares", "short_info", False, "-short interest shares / shares outstanding"),
    _s("seas_5y", "seasonality", False, "mean return of the target month in the last 5 years"),
)
FAST_BASE_SIGNALS: tuple[SignalSpec, ...] = (
    _s("rev_21_ind", "fast", False, "-(21d return - industry mean)"),
    _s("on252", "fast", False, "mean overnight return, 252 sessions (>= 200 valid)"),
    _s("news_attention", "fast", False, "attention_surge_5d (2024 on)"),
)
SLOW_NAMES = tuple(s.name for s in SLOW_SIGNALS)
THEME_SIGNALS: dict[str, tuple[str, ...]] = {
    t: tuple(s.name for s in SLOW_SIGNALS if s.theme == t) for t in THEMES
}
SIGN_CONVENTION = (
    "raw columns are oriented: higher value = higher expected return, for every signal"
)


def alpha_specs(columns: dict[str, list[str]]) -> tuple[SignalSpec, ...]:
    """Fast alpha101 / alpha191 specs from ``{"alpha101": [...], "alpha191": [...]}``."""
    out = [_s(f"a101_{c}", "fast", False, "alpha101_broad") for c in columns.get("alpha101", [])]
    out += [_s(f"g191_{c}", "fast", False, "alpha191_broad") for c in columns.get("alpha191", [])]
    return tuple(out)


def all_specs(alpha_columns: dict[str, list[str]] | None = None) -> tuple[SignalSpec, ...]:
    return SLOW_SIGNALS + FAST_BASE_SIGNALS + alpha_specs(alpha_columns or {})


# ---------------------------------------------------------------------------
# cross-sectional processing
# ---------------------------------------------------------------------------


def winsorize(x: np.ndarray, lo: float = WINSOR_LO, hi: float = WINSOR_HI) -> np.ndarray:
    """Clip the finite values at their ``lo`` / ``hi`` quantiles; non-finite values stay NaN."""
    x = np.asarray(x, dtype="float64")
    out = np.where(np.isfinite(x), x, np.nan)
    ok = np.isfinite(out)
    if ok.sum() < 3:
        return out
    a, b = np.quantile(out[ok], [lo, hi])
    out[ok] = np.clip(out[ok], a, b)
    return out


def rank_normal(x: np.ndarray) -> np.ndarray:
    """``Phi^-1((rank - 0.5) / n)`` with average ranks for ties; NaN stays NaN."""
    x = np.asarray(x, dtype="float64")
    out = np.full(x.shape, np.nan)
    ok = np.isfinite(x)
    n = int(ok.sum())
    if n == 0:
        return out
    out[ok] = ndtri((rankdata(x[ok], method="average") - 0.5) / n)
    return out


def industry_demean(
    z: np.ndarray, codes: np.ndarray, min_members: int = MIN_INDUSTRY_MEMBERS
) -> np.ndarray:
    """Subtract the group mean (over finite members) from each finite score.  A group with fewer
    than ``min_members`` finite scores, and a name with a negative code (unclassified), are left
    as they are."""
    z = np.asarray(z, dtype="float64")
    codes = np.asarray(codes)
    out = z.copy()
    ok = np.isfinite(z) & (codes >= 0)
    if not ok.any():
        return out
    g = codes[ok].astype(np.int64)
    n_g = np.bincount(g)
    mean_g = np.bincount(g, weights=z[ok]) / np.maximum(n_g, 1)
    use = n_g[g] >= min_members
    idx = np.flatnonzero(ok)
    out[idx[use]] = z[idx[use]] - mean_g[g[use]]
    return out


def process_signal(
    raw: np.ndarray, codes: np.ndarray, demean: bool
) -> tuple[np.ndarray, np.ndarray]:
    """One signal on one session: ``(score, covered)``; ``score`` is 0 where not covered."""
    raw = np.asarray(raw, dtype="float64")
    covered = np.isfinite(raw)
    z = rank_normal(winsorize(raw))
    if demean:
        z = industry_demean(z, codes)
    return np.where(covered, np.nan_to_num(z, nan=0.0), 0.0), covered


def theme_composite(
    scores: dict[str, np.ndarray], covered: dict[str, np.ndarray]
) -> tuple[dict[str, np.ndarray], np.ndarray, np.ndarray]:
    """Theme scores (mean of the processed scores of the theme's signals, missing = 0), the M0
    composite (mean of the theme scores, equal weights) and the number of covered themes.  The
    scores are already oriented, so every sign is +1."""
    theme_scores: dict[str, np.ndarray] = {}
    n_cov = None
    for t in THEMES:
        names = [n for n in THEME_SIGNALS[t] if n in scores]
        arr = np.mean([scores[n] for n in names], axis=0)
        theme_scores[t] = arr
        any_cov = np.any([covered[n] for n in names], axis=0).astype(np.int8)
        n_cov = any_cov if n_cov is None else n_cov + any_cov
    comp = np.mean([theme_scores[t] for t in THEMES], axis=0)
    return theme_scores, comp, n_cov


def process_frame(raw: pd.DataFrame, specs: Sequence[SignalSpec]) -> pd.DataFrame:
    """Process a long frame of oriented raw signals (columns ``trade_date``, ``symbol``,
    ``ind_code`` and one column per spec name) session by session.  Returns the output columns
    (``<name>_raw``, ``<name>``, ``<name>_cov``, ``theme_*``, ``m0_composite``, ``m0_n_themes``)."""
    raw = raw.sort_values(["trade_date", "symbol"], kind="stable").reset_index(drop=True)
    n = len(raw)
    dates = raw["trade_date"].to_numpy()
    cuts = np.flatnonzero(np.r_[True, dates[1:] != dates[:-1], True])
    codes_all = raw["ind_code"].to_numpy()
    names = [s.name for s in specs]
    score = {s.name: np.zeros(n, dtype="float32") for s in specs}
    cov = {s.name: np.zeros(n, dtype="bool") for s in specs}
    theme_arr = {t: np.zeros(n, dtype="float32") for t in THEMES}
    comp = np.zeros(n, dtype="float32")
    n_themes = np.zeros(n, dtype="int8")
    have_slow = all(nm in names for nm in SLOW_NAMES)
    values = {s.name: raw[s.name].to_numpy("float64") for s in specs}
    for v in values.values():  # a value float32 cannot hold is a bad print, not a signal
        v[~(np.abs(v) < FLOAT32_SAFE)] = np.nan
    for a, b in zip(cuts[:-1], cuts[1:], strict=True):
        sl = slice(a, b)
        d_scores, d_cov = {}, {}
        for s in specs:
            sc, cv = process_signal(values[s.name][sl], codes_all[sl], s.demean)
            score[s.name][sl] = sc
            cov[s.name][sl] = cv
            d_scores[s.name], d_cov[s.name] = sc, cv
        if have_slow:
            ts, c, k = theme_composite(d_scores, d_cov)
            for t in THEMES:
                theme_arr[t][sl] = ts[t]
            comp[sl] = c
            n_themes[sl] = k
    out = {
        "trade_date": raw["trade_date"],
        "symbol": raw["symbol"],
        "ind_code": raw["ind_code"].astype("int16"),
    }
    for s in specs:
        out[f"{s.name}_raw"] = values[s.name].astype("float32")
        out[s.name] = score[s.name]
        out[f"{s.name}_cov"] = cov[s.name]
    if "resid_mom_fallback" in raw.columns:
        out["resid_mom_12_1_fallback"] = raw["resid_mom_fallback"].to_numpy("bool")
    if have_slow:
        for t in THEMES:
            out[f"theme_{t}"] = theme_arr[t]
        out["m0_composite"] = comp
        out["m0_n_themes"] = n_themes
    return pd.DataFrame(out)


# ---------------------------------------------------------------------------
# industry groups
# ---------------------------------------------------------------------------


def load_industry_groups(risk_dir: Path | str = rk.RISK_DIR) -> tuple[dict[int, str], list[str]]:
    """``(ff48 code -> group name, sorted group names)`` exactly as the risk model uses them."""
    meta = json.loads((Path(risk_dir) / "meta.json").read_text())
    mapping = {int(k): v for k, v in meta["ff48_to_group"].items()}
    return mapping, list(meta["groups"])


def industry_codes(ff48: pd.Series, mapping: dict[int, str], groups: Sequence[str]) -> np.ndarray:
    """Integer group code per name (-1 = unclassified)."""
    idx = {g: i for i, g in enumerate(groups)}
    table = np.full(49, -1, dtype=np.int16)
    for code, g in mapping.items():
        table[code] = idx[g]
    f = pd.to_numeric(ff48, errors="coerce").to_numpy("float64")
    ok = np.isfinite(f) & (f >= 1) & (f <= 48)
    return np.where(ok, table[np.where(ok, f, 0).astype(int)], -1).astype("int16")


def group_mean(values: pd.Series, dates: pd.Series, codes: np.ndarray, min_n: int) -> np.ndarray:
    """Mean of ``values`` over the finite members of (date, group); NaN for an unclassified name or
    a group with fewer than ``min_n`` finite members (the name itself is included)."""
    df = pd.DataFrame({"v": values.to_numpy("float64"), "d": dates.to_numpy(), "g": codes})
    df.loc[df["g"] < 0, "v"] = np.nan
    gb = df.groupby(["d", "g"])["v"]
    mean = gb.transform("mean")
    cnt = gb.transform("count")
    return np.where(cnt >= min_n, mean, np.nan)


# ---------------------------------------------------------------------------
# point-in-time visibility
# ---------------------------------------------------------------------------


def session_close_utc(dates: pd.Series | pd.DatetimeIndex) -> pd.Series:
    """16:00 America/New_York of each calendar date, as UTC timestamps.  (Half days close at 13:00;
    16:00 is used for all, so on those three sessions a filing between 13:00 and 16:00 counts as
    visible.  No point-in-time source in the library publishes in that window.)"""
    d = pd.to_datetime(pd.Series(dates)).dt.normalize()
    local = pd.to_datetime(d.dt.strftime("%Y-%m-%d") + " 16:00:00").dt.tz_localize(
        NY, ambiguous="NaT", nonexistent="NaT"
    )
    return local.dt.tz_convert("UTC")


def visible_ts_by_close(visible_at: pd.Series, trade_date: pd.Series) -> np.ndarray:
    """True where the row's ``visible_at`` (timestamp) is at or before the close of ``trade_date``;
    a missing ``visible_at`` is not visible."""
    v = pd.to_datetime(visible_at, utc=True)
    close = session_close_utc(trade_date).reset_index(drop=True)
    return (v.reset_index(drop=True) <= close).to_numpy("bool")


def visible_date_by_close(visible_date: pd.Series, trade_date: pd.Series) -> np.ndarray:
    """True where ``visible_date`` (the first session the row may be used) is <= ``trade_date``.
    A missing ``visible_date`` is not visible."""
    v = pd.to_datetime(visible_date).dt.normalize().reset_index(drop=True)
    t = pd.to_datetime(trade_date).dt.normalize().reset_index(drop=True)
    return (v <= t).to_numpy("bool")


def annual_flow_events(facts: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """Latest-fiscal-year flow per issuer from the first-filed ``FY`` facts of ONE concept
    (columns ``cik, period_end, val, filed, usable_session``): ``(events, n_dropped)`` with
    ``events`` = ``cik, usable_session, val`` keeping a fact only if its period end is the latest
    seen so far (a late restatement of an older year does not regress the series).  A fact whose
    ``usable_session`` is not strictly after ``filed`` is dropped (point-in-time guard)."""
    f = facts.copy()
    bad = ~(pd.to_datetime(f["usable_session"]) > pd.to_datetime(f["filed"]).dt.normalize())
    f = f.loc[~bad]
    f = f.sort_values(["cik", "usable_session", "period_end"], kind="stable")
    cm = f.groupby("cik")["period_end"].cummax()
    f = f.loc[f["period_end"] >= cm]
    return f[["cik", "usable_session", "val"]].reset_index(drop=True), int(bad.sum())


def annual_flow_asof(events: pd.DataFrame, cik: pd.Series, trade_date: pd.Series) -> np.ndarray:
    """Value in force at each (cik, trade_date): the latest event with ``usable_session`` <=
    ``trade_date``.  NaN where the cik is missing or no event exists yet."""
    left = pd.DataFrame(
        {
            "cik": pd.to_numeric(cik, errors="coerce").to_numpy("float64"),
            "trade_date": pd.to_datetime(trade_date).to_numpy("datetime64[ns]"),
            "i": np.arange(len(cik)),
        }
    ).dropna(subset=["cik"])
    left["cik"] = left["cik"].astype("int64")
    left = left.sort_values("trade_date", kind="stable")
    right = events.assign(
        cik=events["cik"].astype("int64"),
        usable_session=pd.to_datetime(events["usable_session"]).astype("datetime64[ns]"),
    ).sort_values("usable_session", kind="stable")
    m = pd.merge_asof(
        left,
        right,
        left_on="trade_date",
        right_on="usable_session",
        by="cik",
        direction="backward",
    )
    out = np.full(len(cik), np.nan)
    out[m["i"].to_numpy()] = m["val"].to_numpy("float64")
    return out


# ---------------------------------------------------------------------------
# raw signal formulas on aligned frames
# ---------------------------------------------------------------------------


def _ratio(num: pd.Series | np.ndarray, den: pd.Series | np.ndarray) -> np.ndarray:
    n = np.asarray(num, dtype="float64")
    d = np.asarray(den, dtype="float64")
    with np.errstate(invalid="ignore", divide="ignore"):
        r = np.where(np.isfinite(n) & np.isfinite(d) & (d > 0), n / np.where(d > 0, d, 1.0), np.nan)
    return r


def fundamental_raw(f: pd.DataFrame) -> pd.DataFrame:
    """Oriented raw value / quality / investment / earnings signals.  ``f`` has ``mcap``,
    ``stockholders_equity``, ``total_assets``, ``gross_profitability``, ``roe``, ``accruals``,
    ``asset_growth``, ``sue_eps``, ``sue_rev`` (``sec_fundamentals_daily``, aligned) and the annual
    flows ``ni_a``, ``rev_a``, ``ocf_a``, ``opinc_a`` (from the facts)."""
    out = pd.DataFrame(index=f.index)
    mcap = f["mcap"].to_numpy("float64")
    out["bm"] = _ratio(f["stockholders_equity"], mcap)
    out["ep"] = _ratio(f["ni_a"], mcap)
    out["sp"] = _ratio(f["rev_a"], mcap)
    out["cfp"] = _ratio(f["ocf_a"], mcap)
    out["gp_at"] = f["gross_profitability"].to_numpy("float64")
    out["roe"] = f["roe"].to_numpy("float64")
    out["op_at"] = _ratio(f["opinc_a"], f["total_assets"])
    out["neg_accruals"] = -f["accruals"].to_numpy("float64")
    out["neg_asset_growth"] = -f["asset_growth"].to_numpy("float64")
    out["sue_eps"] = f["sue_eps"].to_numpy("float64")
    out["sue_rev"] = f["sue_rev"].to_numpy("float64")
    return out.replace([np.inf, -np.inf], np.nan)


def insider_raw(f: pd.DataFrame, mcap: np.ndarray, trade_date: pd.Series) -> pd.DataFrame:
    """``cmp_opp_buy_60d`` and ``nonplan_buy_mcap_60d``; a row not visible by the close of its own
    ``trade_date`` is masked.  ``f`` has ``visible_at``, ``cmp_opportunistic_buy_60d``,
    ``net_buy_usd_nonplan_60d``."""
    vis = visible_ts_by_close(f["visible_at"], trade_date)
    cmp_ = np.where(vis, f["cmp_opportunistic_buy_60d"].to_numpy("float64"), np.nan)
    nb = np.where(vis, f["net_buy_usd_nonplan_60d"].to_numpy("float64"), np.nan)
    return pd.DataFrame(
        {"cmp_opp_buy_60d": cmp_, "nonplan_buy_mcap_60d": _ratio_signed(nb, mcap)}, index=f.index
    )


def _ratio_signed(num: np.ndarray, den: np.ndarray) -> np.ndarray:
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(np.isfinite(num) & np.isfinite(den) & (den > 0), num / den, np.nan)


def short_volume_raw(f: pd.DataFrame, trade_date: pd.Series) -> np.ndarray:
    """``-short_volume_ratio_mean_21``; rows whose ``visible_date`` is after the trade date are
    masked (a missing ``visible_date`` on a carried row is accepted: the mean is built from earlier
    visible records only)."""
    v = f["visible_date"]
    vis = visible_date_by_close(v, trade_date) | v.isna().to_numpy()
    return np.where(vis, -f["short_volume_ratio_mean_21"].to_numpy("float64"), np.nan)


def short_interest_raw(
    f: pd.DataFrame, shares_outstanding: np.ndarray, trade_date: pd.Series
) -> np.ndarray:
    """``-short_interest_shares / shares_outstanding`` (both as filed, so split changes cancel);
    masked when ``visible_date`` is after the trade date."""
    vis = visible_date_by_close(f["visible_date"], trade_date)
    ratio = _ratio_signed(f["short_interest_shares"].to_numpy("float64"), shares_outstanding)
    return np.where(vis, -ratio, np.nan)


def news_raw(f: pd.DataFrame, trade_date: pd.Series) -> np.ndarray:
    vis = visible_ts_by_close(f["visible_at"], trade_date)
    return np.where(vis, f["attention_surge_5d"].to_numpy("float64"), np.nan)


def lowrisk_raw(
    trade_date: pd.Series,
    beta: np.ndarray,
    idio_vol: np.ndarray,
    mcap: np.ndarray,
    market_var_by_date: pd.Series,
) -> tuple[np.ndarray, np.ndarray]:
    """``(-Vasicek beta, -idio vol)`` per row; the shrinkage is applied cross-sectionally per
    session with :func:`risk.vasicek_beta`."""
    dates = pd.to_datetime(trade_date).to_numpy()
    out = np.full(len(dates), np.nan)
    cuts = np.flatnonzero(np.r_[True, dates[1:] != dates[:-1], True])
    for a, b in zip(cuts[:-1], cuts[1:], strict=True):
        mv = float(market_var_by_date.get(pd.Timestamp(dates[a]), np.nan))
        if not np.isfinite(mv):
            continue
        out[a:b] = rk.vasicek_beta(beta[a:b], idio_vol[a:b], mcap[a:b], mv)
    iv = np.where(np.isfinite(idio_vol), -np.asarray(idio_vol, dtype="float64"), np.nan)
    return -out, iv


# ---------------------------------------------------------------------------
# price-based signals on wide (T, N) matrices
# ---------------------------------------------------------------------------


def momentum_matrix(close: np.ndarray, skip: int = 21, lookback: int = 252) -> np.ndarray:
    """``close[t - skip] / close[t - lookback] - 1`` (NaN if either is missing or t < lookback)."""
    c = np.asarray(close, dtype="float64")
    out = np.full(c.shape, np.nan)
    if c.shape[0] > lookback:
        with np.errstate(invalid="ignore", divide="ignore"):
            out[lookback:] = (
                c[lookback - skip : c.shape[0] - skip] / c[: c.shape[0] - lookback] - 1.0
            )
    return np.where(np.isfinite(out), out, np.nan)


def return_matrix(close: np.ndarray, lag: int = 1) -> np.ndarray:
    """``close[t] / close[t - lag] - 1`` (NaN where either price is missing or non-positive)."""
    c = np.asarray(close, dtype="float64")
    out = np.full(c.shape, np.nan)
    if c.shape[0] > lag:
        with np.errstate(invalid="ignore", divide="ignore"):
            r = c[lag:] / c[:-lag] - 1.0
        out[lag:] = np.where((c[lag:] > 0) & (c[:-lag] > 0), r, np.nan)
    return out


def overnight_matrix(open_: np.ndarray, close: np.ndarray) -> np.ndarray:
    """``open[t] / close[t-1] - 1``; NaN if either price is missing or non-positive."""
    o = np.asarray(open_, dtype="float64")
    c = np.asarray(close, dtype="float64")
    out = np.full(o.shape, np.nan)
    with np.errstate(invalid="ignore", divide="ignore"):
        r = o[1:] / c[:-1] - 1.0
        ok = (o[1:] > 0) & (c[:-1] > 0)
    out[1:] = np.where(ok, r, np.nan)
    return out


def rolling_mean_min_obs(x: np.ndarray, window: int, min_obs: int) -> np.ndarray:
    """Trailing mean over ``window`` rows ending at t (inclusive) with at least ``min_obs`` finite
    values (T-35's ``rolling(252, min_periods=200).mean()``)."""
    ok = np.isfinite(x)
    z = np.where(ok, x, 0.0)
    cs = np.vstack([np.zeros((1, x.shape[1])), np.cumsum(z, axis=0)])
    cc = np.vstack([np.zeros((1, x.shape[1])), np.cumsum(ok, axis=0)])
    t_n = x.shape[0]
    hi = np.arange(1, t_n + 1)
    lo = np.maximum(hi - window, 0)
    s = cs[hi] - cs[lo]
    c = cc[hi] - cc[lo]
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(c >= min_obs, s / np.maximum(c, 1), np.nan)


def window_moments(
    r: np.ndarray, lag_lo: int = 21, lag_hi: int = 252
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """For each row t >= ``lag_hi``: sum, sum of squares and count of the finite values of ``r`` in
    the rows ``t - lag_hi + 1 .. t - lag_lo`` (the daily returns between ``close[t - lag_hi]`` and
    ``close[t - lag_lo]``).  NaN / 0 for earlier rows."""
    ok = np.isfinite(r)
    z = np.where(ok, r, 0.0)
    pad = np.zeros((1, r.shape[1]))
    s = np.vstack([pad, np.cumsum(z, axis=0)])
    q = np.vstack([pad, np.cumsum(z * z, axis=0)])
    c = np.vstack([pad, np.cumsum(ok, axis=0)])
    t_n = r.shape[0]
    sums = np.full(r.shape, np.nan)
    sq = np.full(r.shape, np.nan)
    cnt = np.zeros(r.shape)
    if t_n > lag_hi:
        t = np.arange(lag_hi, t_n)
        hi_i, lo_i = t - lag_lo + 1, t - lag_hi + 1  # cumsum index k = rows 0..k-1
        sums[t] = s[hi_i] - s[lo_i]
        sq[t] = q[hi_i] - q[lo_i]
        cnt[t] = c[hi_i] - c[lo_i]
    return sums, sq, cnt


def resid_momentum(
    resid: np.ndarray,
    fallback_resid: np.ndarray,
    lag_lo: int = 21,
    lag_hi: int = 252,
    min_obs: int = 200,
) -> tuple[np.ndarray, np.ndarray]:
    """Blitz-style residual momentum: ``sum(resid) / std(resid)`` over the 12-1 window.  Uses the
    risk-model residuals where at least ``min_obs`` of the window days exist, otherwise the
    market-plus-industry fallback residuals (same window, same ``min_obs``).  Returns
    ``(value, used_fallback)``."""

    def one(r: np.ndarray) -> np.ndarray:
        s, q, c = window_moments(r, lag_lo, lag_hi)
        with np.errstate(invalid="ignore", divide="ignore"):
            var = q / np.maximum(c, 1) - (s / np.maximum(c, 1)) ** 2
            sd = np.sqrt(np.maximum(var, 0.0))
            val = np.where((c >= min_obs) & (sd > 0), s / np.where(sd > 0, sd, 1.0), np.nan)
        return val

    primary = one(resid)
    fb = one(fallback_resid)
    use_fb = ~np.isfinite(primary) & np.isfinite(fb)
    return np.where(np.isfinite(primary), primary, fb), use_fb


def group_demeaned_returns(ret: np.ndarray, group: np.ndarray, min_members: int) -> np.ndarray:
    """Per row, ``ret`` minus the equal-weighted mean over the finite columns of the same
    ``group`` (static per column, -1 = none; NaN where the group has fewer than ``min_members``
    finite columns)."""
    out = np.full(ret.shape, np.nan)
    g_ok = group >= 0
    n_g = int(group.max()) + 1 if g_ok.any() else 0
    if n_g == 0:
        return out
    gi = np.where(g_ok, group, 0)
    for t in range(ret.shape[0]):
        r = ret[t]
        ok = np.isfinite(r) & g_ok
        if not ok.any():
            continue
        s = np.bincount(gi[ok], weights=r[ok], minlength=n_g)
        n = np.bincount(gi[ok], minlength=n_g)
        with np.errstate(invalid="ignore", divide="ignore"):
            m = np.where(n >= min_members, s / np.maximum(n, 1), np.nan)
        out[t] = np.where(ok, r - m[gi], np.nan)
    return out


def month_end_closes(close: np.ndarray, dates: pd.DatetimeIndex) -> pd.DataFrame:
    """Last valid close of every calendar month, per column (index = (year, month)).  Works month by
    month so no second copy of the full matrix is made."""
    per = dates.year * 100 + dates.month
    keys = pd.unique(per)
    out = np.full((len(keys), close.shape[1]), np.nan)
    cols = np.arange(close.shape[1])
    for i, k in enumerate(keys):
        idx = np.flatnonzero(per == k)
        blk = close[idx[0] : idx[-1] + 1]
        ok = np.isfinite(blk) & (blk > 0)
        last = blk.shape[0] - 1 - np.argmax(ok[::-1], axis=0)
        out[i] = np.where(ok.any(axis=0), blk[last, cols], np.nan)
    index = pd.MultiIndex.from_tuples([(int(k) // 100, int(k) % 100) for k in keys])
    return pd.DataFrame(out, index=index.set_names(["year", "month"]))


def monthly_returns(month_end: pd.DataFrame) -> pd.DataFrame:
    """Month-end-to-month-end returns (index = (year, month)); the first month has none."""
    with np.errstate(invalid="ignore", divide="ignore"):
        ret = month_end / month_end.shift(1) - 1.0
    return ret.replace([np.inf, -np.inf], np.nan)


def seasonality(
    mret: pd.DataFrame, target_year: int, target_month: int, years: int = 5, min_years: int = 3
) -> pd.Series:
    """Heston-Sadka: mean over the ``years`` years before ``target_year`` of the same calendar
    month's return, NaN with fewer than ``min_years`` observations."""
    rows = []
    for k in range(1, years + 1):
        key = (target_year - k, target_month)
        if key in mret.index:
            rows.append(mret.loc[key])
    if not rows:
        return pd.Series(np.nan, index=mret.columns)
    m = pd.concat(rows, axis=1)
    return m.mean(axis=1).where(m.notna().sum(axis=1) >= min_years)


def target_month(next_session: pd.Timestamp) -> tuple[int, int]:
    """The calendar month the next session (``t + 1``) falls in."""
    return next_session.year, next_session.month


# ---------------------------------------------------------------------------
# measurement helpers
# ---------------------------------------------------------------------------


def rank_ic(score: np.ndarray, ret: np.ndarray, min_n: int = 30) -> float:
    """Cross-sectional Spearman correlation on the names where both are finite."""
    ok = np.isfinite(score) & np.isfinite(ret)
    if ok.sum() < min_n:
        return float("nan")
    a = rankdata(score[ok])
    b = rankdata(ret[ok])
    a -= a.mean()
    b -= b.mean()
    den = float(np.sqrt((a * a).sum() * (b * b).sum()))
    return float((a * b).sum() / den) if den > 0 else float("nan")


def newey_west_t(x: np.ndarray, lags: int) -> float:
    """t-statistic of the mean with a Bartlett-kernel (Newey-West) long-run variance."""
    x = np.asarray(x, dtype="float64")
    x = x[np.isfinite(x)]
    n = len(x)
    if n < lags + 5:
        return float("nan")
    e = x - x.mean()
    var = float(e @ e) / n
    for lag in range(1, lags + 1):
        var += 2.0 * (1.0 - lag / (lags + 1.0)) * float(e[lag:] @ e[:-lag]) / n
    if var <= 0:
        return float("nan")
    return float(x.mean() / np.sqrt(var / n))


def plain_t(x: np.ndarray) -> float:
    x = np.asarray(x, dtype="float64")
    x = x[np.isfinite(x)]
    if len(x) < 3 or x.std(ddof=1) == 0:
        return float("nan")
    return float(x.mean() / (x.std(ddof=1) / np.sqrt(len(x))))
