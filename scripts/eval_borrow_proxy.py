"""D7 step 2: calibrate the easy-to-borrow proxy against the Alpaca flags of one snapshot.

Reads the 2026-10-01 asset snapshot (``snapshot_alpaca_assets.py``), builds point-in-time
features per symbol at an as-of session, evaluates the design rule SE_t and some variants
(confusion matrix, precision/recall by adv_rank band), a logistic regression on the same
features (5-fold by symbol; there is a single label snapshot), and measures how stable the
proxy is when applied one to three years back against *today's* flags.

    scripts/run_capped.sh --mem 1.8G -- uv run python scripts/eval_borrow_proxy.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import polars as pl  # noqa: E402

from open_composer.research.equity_book import borrow as bw  # noqa: E402

FEATURES = ROOT / "data" / "features"
BORROW_DIR = ROOT / "data" / "research" / "equity_book" / "borrow"
REPORT_DIR = ROOT / "reports" / "research" / "program" / "borrow-proxy-v1-2026-10-01"
ASSET_METADATA = FEATURES / "universe" / "_asset_metadata.parquet"
FINRA_SI = ROOT / "data" / "raw" / "finra_short_interest" / "parsed.parquet"
BANDS = [("<=1000", 0, 1000), ("1001-2000", 1000, 2000), ("2001-3000", 2000, 3000)]
DATA_START = pd.Timestamp("2016-01-04")


def _read_year(name: str, year: int, cols: list[str]) -> pl.LazyFrame:
    return pl.scan_parquet(FEATURES / name / f"{year}.parquet").select(cols)


def sessions_calendar() -> list[pd.Timestamp]:
    parts = [
        pl.scan_parquet(FEATURES / "daily_broad" / f"{y}.parquet")
        .select("trade_date")
        .unique()
        .collect()
        for y in range(2016, 2027)
    ]
    s = pl.concat(parts)["trade_date"].unique().sort().to_list()
    return [pd.Timestamp(x) for x in s]


def first_price_dates() -> pd.Series:
    parts = []
    for y in range(2016, 2027):
        parts.append(
            pl.scan_parquet(FEATURES / "daily_broad" / f"{y}.parquet")
            .select(["symbol", "trade_date"])
            .group_by("symbol")
            .agg(pl.col("trade_date").min().alias("first"))
            .collect()
        )
    df = pl.concat(parts).group_by("symbol").agg(pl.col("first").min()).to_pandas()
    return df.set_index("symbol")["first"]


def load_asof(
    asof: pd.Timestamp, cal: list[pd.Timestamp], first_px: pd.Series, fund: set[str]
) -> pd.DataFrame:
    """Point-in-time features of every U3000 candidate at session ``asof`` (<= its date)."""
    asof = max(d for d in cal if d <= asof)
    i = cal.index(asof)
    start = cal[max(i - bw.RS_WINDOW, 0)]  # 252 sessions: ratios of sessions i-251..i need i-252
    uni = pd.concat(
        [
            pd.read_parquet(FEATURES / "universe_broad" / f"{y}.parquet")
            for y in range(max(asof.year - 1, 2016), asof.year + 1)
        ]
    )
    uni["month_end"] = pd.to_datetime(uni["month_end"])
    me = uni.loc[uni["month_end"] <= asof, "month_end"].max()
    u = uni[(uni["month_end"] == me) & (uni["adv_rank"] <= 3000) & (uni["close"] >= 5.0)]
    u = u[~u["symbol"].isin(fund)][["symbol", "adv_rank"]]
    syms = u["symbol"].tolist()
    # price rows over the 252-session window (per year file, filtered)
    px = []
    for y in sorted({start.year, asof.year}):
        px.append(
            _read_year(
                "daily_broad",
                y,
                ["symbol", "trade_date", "open", "close", "idio_vol_63", "ret_252", "vol_21"],
            )
            .filter(
                pl.col("symbol").is_in(syms)
                & (pl.col("trade_date") >= start.to_pydatetime())
                & (pl.col("trade_date") <= asof.to_pydatetime())
            )
            .collect()
        )
    px_df = pl.concat(px).sort(["symbol", "trade_date"]).to_pandas()
    px_df["ratio"] = px_df["open"] / px_df.groupby("symbol")["close"].shift(1)
    px_df["rs_up"] = bw.is_reverse_split_ratio(px_df["ratio"].to_numpy(), direction="up")
    px_df["rs_down"] = bw.is_reverse_split_ratio(px_df["ratio"].to_numpy(), direction="down")
    in_window = px_df["trade_date"] > start  # sessions start+1 .. asof = 252 sessions
    g = px_df[in_window].groupby("symbol")
    feat = g[["rs_up", "rs_down"]].max().astype(bool)
    feat.columns = ["reverse_split_252", "reverse_split_252_down"]
    last = px_df[px_df["trade_date"] == asof].set_index("symbol")
    feat["price"] = last["close"]
    feat["idio_vol_63"] = last["idio_vol_63"]
    feat["ret_252"] = last["ret_252"]
    feat["vol_21"] = last["vol_21"]
    feat = u.set_index("symbol").join(feat, how="left")
    # shares outstanding -> mcap
    so = (
        _read_year(
            "sec_fundamentals_daily", asof.year, ["symbol", "trade_date", "shares_outstanding"]
        )
        .filter(
            (pl.col("trade_date") <= asof.to_pydatetime())
            & (pl.col("trade_date") >= (asof - pd.Timedelta(days=15)).to_pydatetime())
            & pl.col("symbol").is_in(syms)
        )
        .collect()
        .sort("trade_date")
        .group_by("symbol")
        .agg(pl.col("shares_outstanding").last())
        .to_pandas()
        .set_index("symbol")["shares_outstanding"]
    )
    feat["shares_outstanding"] = so
    feat["mcap"] = feat["price"] * feat["shares_outstanding"]
    sv = (
        _read_year(
            "short_volume_broad", asof.year, ["symbol", "trade_date", "short_volume_ratio_mean_21"]
        )
        .filter((pl.col("trade_date") == asof.to_pydatetime()) & pl.col("symbol").is_in(syms))
        .collect()
        .to_pandas()
        .set_index("symbol")["short_volume_ratio_mean_21"]
    )
    feat["short_volume_ratio_mean_21"] = sv
    si = (
        pl.scan_parquet(FINRA_SI)
        .filter((pl.col("visible_date") <= asof.to_pydatetime()) & pl.col("symbol").is_in(syms))
        .select(["symbol", "visible_date", "short_interest_shares"])
        .sort("visible_date")
        .group_by("symbol")
        .agg(pl.col("short_interest_shares").last())
        .collect()
        .to_pandas()
        .set_index("symbol")["short_interest_shares"]
    )
    feat["si_over_shares"] = si / feat["shares_outstanding"]
    feat.loc[~np.isfinite(feat["si_over_shares"]), "si_over_shares"] = np.nan
    feat["si_over_shares_pct"] = bw.si_cross_sectional_pct(feat["si_over_shares"])
    feat["days_since_first_price"] = (asof - first_px.reindex(feat.index)).dt.days
    feat["asof"] = asof
    feat["universe_month_end"] = me
    feat = feat[feat["ret_252"].notna() & feat["price"].notna()]  # >= 252 sessions of history
    return feat.reset_index().rename(columns={"index": "symbol"})


# --------------------------------------------------------------------------
# metrics
# --------------------------------------------------------------------------


def confusion(pred: np.ndarray, truth: np.ndarray) -> dict[str, Any]:
    pred, truth = np.asarray(pred, bool), np.asarray(truth, bool)
    tp = int((pred & truth).sum())
    fp = int((pred & ~truth).sum())
    fn = int((~pred & truth).sum())
    tn = int((~pred & ~truth).sum())
    return {
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "tn": tn,
        "n": int(len(pred)),
        "base_rate_etb": float(truth.mean()) if len(truth) else None,
        "pred_rate": float(pred.mean()) if len(pred) else None,
        "precision": tp / (tp + fp) if tp + fp else None,
        "recall": tp / (tp + fn) if tp + fn else None,
        "false_positive_rate_among_pred": fp / (tp + fp) if tp + fp else None,
    }


def by_band(df: pd.DataFrame, pred: np.ndarray, label: str = "etb") -> dict[str, Any]:
    out = {}
    for name, lo, hi in BANDS:
        m = ((df["adv_rank"] > lo) & (df["adv_rank"] <= hi)).to_numpy()
        out[name] = confusion(np.asarray(pred)[m], df[label].to_numpy()[m])
    return out


def rule_variants(df: pd.DataFrame) -> dict[str, np.ndarray]:
    def rule(adv=2000, px=10.0, si=0.95, rs="reverse_split_252"):
        return bw.rule_mask(
            df["adv_rank"],
            df["price"],
            df[rs],
            df["si_over_shares_pct"] if si is not None else None,
            adv_rank_max=adv,
            price_min=px,
            si_pct_max=si if si is not None else 1.0,
        )

    v = {
        "v1 (adv<=2000, px>=10, no RS252, SI top5% out)": rule(),
        "v1 without SI clause": rule(si=None),
        "v1 reverse split read literally as 1/k": rule(rs="reverse_split_252_down"),
        "adv<=2000 only": bw.rule_mask(df["adv_rank"], df["price"], False, None, price_min=0.0),
        "adv<=2000, px>=10": bw.rule_mask(df["adv_rank"], df["price"], False, None),
        "adv<=1500, px>=10, no RS252, SI": rule(adv=1500),
        "adv<=1000, px>=10, no RS252, SI": rule(adv=1000),
        "adv<=2000, px>=15, no RS252, SI": rule(px=15.0),
        "adv<=2000, px>=20, no RS252, SI": rule(px=20.0),
        "adv<=2500, px>=10, no RS252, SI": rule(adv=2500),
    }
    return v


def add_extra_clause(
    df: pd.DataFrame, mask: np.ndarray, mcap_min: float | None, svr_max: float | None
) -> np.ndarray:
    m = mask.copy()
    if mcap_min is not None:
        m &= (df["mcap"] >= mcap_min).fillna(False).to_numpy()
    if svr_max is not None:
        m &= ~(df["short_volume_ratio_mean_21"] > svr_max).fillna(False).to_numpy()
    return m


LR_FEATURES = [
    "log_adv_rank",
    "log_price",
    "log_mcap",
    "idio_vol_63",
    "short_volume_ratio_mean_21",
    "si_over_shares",
    "reverse_split_252",
    "log_days_since_first_price",
]


def lr_matrix(df: pd.DataFrame) -> pd.DataFrame:
    x = pd.DataFrame(index=df.index)
    x["log_adv_rank"] = np.log(df["adv_rank"])
    x["log_price"] = np.log(df["price"])
    x["log_mcap"] = np.log(df["mcap"].where(df["mcap"] > 0))
    x["idio_vol_63"] = df["idio_vol_63"]
    x["short_volume_ratio_mean_21"] = df["short_volume_ratio_mean_21"]
    x["si_over_shares"] = df["si_over_shares"].clip(upper=df["si_over_shares"].quantile(0.99))
    x["reverse_split_252"] = df["reverse_split_252"].astype(float)
    x["log_days_since_first_price"] = np.log1p(df["days_since_first_price"].clip(lower=0))
    for c in ("log_mcap", "short_volume_ratio_mean_21", "si_over_shares"):
        x[f"{c}_missing"] = x[c].isna().astype(float)
        x[c] = x[c].fillna(x[c].median())
    x["idio_vol_63"] = x["idio_vol_63"].fillna(x["idio_vol_63"].median())
    return x


def logistic_cv(df: pd.DataFrame) -> dict[str, Any]:
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import roc_auc_score
    from sklearn.model_selection import StratifiedKFold, cross_val_predict
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    x = lr_matrix(df)
    y = df["etb"].to_numpy().astype(int)
    model = make_pipeline(StandardScaler(), LogisticRegression(max_iter=1000, C=1.0))
    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=20261001)
    p = cross_val_predict(model, x, y, cv=cv, method="predict_proba")[:, 1]
    out: dict[str, Any] = {"auc_oof": float(roc_auc_score(y, p)), "folds": 5, "by": "symbols"}
    truth = y.astype(bool)
    for thr in (0.5, 0.9, 0.95, 0.97):
        out[f"p>={thr}"] = {
            "overall": confusion(p >= thr, truth),
            "by_band": by_band(df, p >= thr),
        }
    # threshold giving precision >= 0.97 with the largest recall (OOF-selected, optimistic)
    best = None
    for thr in np.unique(np.round(np.quantile(p, np.linspace(0.3, 0.999, 300)), 4)):
        c = confusion(p >= thr, truth)
        if c["precision"] is not None and c["precision"] >= 0.97:
            if best is None or c["recall"] > best[1]["recall"]:
                best = (float(thr), c)
    out["best_recall_at_precision_ge_0.97"] = {"threshold": best[0], **best[1]} if best else None
    final = make_pipeline(StandardScaler(), LogisticRegression(max_iter=1000, C=1.0)).fit(x, y)
    coefs = final[-1].coef_[0]
    out["standardized_coefficients"] = dict(zip(x.columns, map(float, coefs), strict=True))
    out["oof_p"] = p
    return out


def main() -> int:
    import warnings

    warnings.filterwarnings("ignore")
    snap_path = sorted(BORROW_DIR.glob("alpaca_assets_*.parquet"))[-1]
    snap = pd.read_parquet(snap_path)
    cal = sessions_calendar()
    first_px = first_price_dates()
    meta = pd.read_parquet(ASSET_METADATA, columns=["symbol", "is_probable_fund_or_etf"])
    fund = set(meta.loc[meta["is_probable_fund_or_etf"].fillna(False), "symbol"])
    asof0 = cal[-1]
    print(f"snapshot {snap_path.name}, features as of {asof0.date()}", flush=True)

    df0 = load_asof(asof0, cal, first_px, fund)
    n_universe = len(df0)
    df0 = df0.merge(
        snap[["symbol", "easy_to_borrow", "shortable", "tradable"]], on="symbol", how="left"
    )
    n_missing_flag = int(df0["easy_to_borrow"].isna().sum())
    df0 = df0[df0["easy_to_borrow"].notna()].copy()
    df0["etb"] = df0["easy_to_borrow"].astype(bool)
    out: dict[str, Any] = {
        "snapshot_file": str(snap_path.relative_to(ROOT)),
        "features_asof": str(asof0.date()),
        "universe_month_end": str(df0["universe_month_end"].iloc[0].date()),
        "n_universe_candidates": n_universe,
        "n_without_alpaca_asset_row_dropped": n_missing_flag,
        "n_labeled": int(len(df0)),
        "etb_rate": float(df0["etb"].mean()),
        "etb_rate_by_band": {
            name: float(df0.loc[(df0["adv_rank"] > lo) & (df0["adv_rank"] <= hi), "etb"].mean())
            for name, lo, hi in BANDS
        },
        "n_by_band": {
            name: int(((df0["adv_rank"] > lo) & (df0["adv_rank"] <= hi)).sum())
            for name, lo, hi in BANDS
        },
        "feature_coverage": {
            c: float(df0[c].notna().mean())
            for c in ("mcap", "short_volume_ratio_mean_21", "si_over_shares", "idio_vol_63")
        },
        "reverse_split_252_share": float(df0["reverse_split_252"].mean()),
        "reverse_split_252_literal_1_over_k_share": float(df0["reverse_split_252_down"].mean()),
        "etb_rate_given_reverse_split": float(df0.loc[df0["reverse_split_252"], "etb"].mean()),
        "etb_rate_given_no_reverse_split": float(df0.loc[~df0["reverse_split_252"], "etb"].mean()),
    }
    truth = df0["etb"].to_numpy()
    variants = {}
    for name, mask in rule_variants(df0).items():
        variants[name] = {"overall": confusion(mask, truth), "by_band": by_band(df0, mask)}
    # extra clauses on top of v1 (mcap, short volume ratio)
    v1 = rule_variants(df0)["v1 (adv<=2000, px>=10, no RS252, SI top5% out)"]
    for mc in (3e8, 1e9, 2e9):
        nm = f"v1 + mcap>={mc / 1e9:g}B"
        m = add_extra_clause(df0, v1, mc, None)
        variants[nm] = {"overall": confusion(m, truth), "by_band": by_band(df0, m)}
    for sv in (0.6, 0.7):
        nm = f"v1 + short_volume_ratio_mean_21<={sv}"
        m = add_extra_clause(df0, v1, None, sv)
        variants[nm] = {"overall": confusion(m, truth), "by_band": by_band(df0, m)}
    out["rule_variants"] = variants
    lr = logistic_cv(df0)
    p = lr.pop("oof_p")
    out["logistic_regression"] = lr
    df0["lr_oof_p"] = p
    # why are v1 false positives not ETB?  profile
    fp = df0[v1 & ~truth]
    out["v1_false_positive_profile"] = {
        "n": int(len(fp)),
        "median_adv_rank": float(fp["adv_rank"].median()) if len(fp) else None,
        "median_price": float(fp["price"].median()) if len(fp) else None,
        "median_mcap": float(fp["mcap"].median()) if len(fp) else None,
        "shortable_share": float(fp["shortable"].mean()) if len(fp) else None,
        "median_si_over_shares": float(fp["si_over_shares"].median()) if len(fp) else None,
    }
    # stability: rule at earlier dates vs today's ETB flag
    stab = {}
    today_etb = set(df0.loc[df0["etb"], "symbol"])
    today_rule = set(df0.loc[v1, "symbol"])
    for years in (1, 2, 3):
        target = asof0 - pd.DateOffset(years=years)
        dfp = load_asof(target, cal, first_px, fund)
        vp = bw.rule_mask(
            dfp["adv_rank"],
            dfp["price"],
            dfp["reverse_split_252"],
            dfp["si_over_shares_pct"],
        )
        then_rule = set(dfp.loc[vp, "symbol"])
        then_all = set(dfp["symbol"])
        etb_then_present = today_etb & then_all
        snap_etb = snap.set_index("symbol")["easy_to_borrow"]
        known = dfp["symbol"].isin(snap_etb.index).to_numpy()  # still on Alpaca's active list
        lab = dfp["symbol"].map(snap_etb).fillna(False).to_numpy().astype(bool)
        dfp_k = dfp[known].assign(etb=lab[known])
        stab[f"{years}y_back"] = {
            "asof": str(dfp["asof"].iloc[0].date()),
            "n_universe_then": int(len(dfp)),
            "n_not_on_alpaca_active_list_today_excluded": int((~known).sum()),
            "todays_etb_names_present_then": len(etb_then_present),
            "share_of_todays_etb_that_met_rule_then": (
                len(etb_then_present & then_rule) / len(etb_then_present)
                if etb_then_present
                else None
            ),
            "share_of_todays_rule_names_that_met_rule_then": (
                len(today_rule & then_rule) / len(today_rule & then_all)
                if today_rule & then_all
                else None
            ),
            "rule_then_vs_etb_today": confusion(vp[known], lab[known]),
            "rule_then_vs_etb_today_by_band": by_band(dfp_k, vp[known]),
        }
        print(f"stability {years}y done", flush=True)
    out["stability"] = stab
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    (REPORT_DIR / "results.json").write_text(
        json.dumps(out, indent=2, default=str), encoding="utf-8"
    )
    df0.drop(columns=["asof", "universe_month_end"]).to_parquet(
        BORROW_DIR / "proxy_eval_features.parquet", index=False
    )
    print("wrote results.json", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
