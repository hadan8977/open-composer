# ruff: noqa: E501
"""T-20261006-22 second stage: ridge / LightGBM rankers on the selected universe and H (contract.md
sections 10 and 16).  Scores are written to ``<store>/results/ml/<model>_U<u>_H<h>.npy`` and run through
the same book, costs and windows as the rule cells.

    scripts/heavy_run.sh --mem 0.8G -- uv run python scripts/t22_ml.py --model ridge   (and lgbm)
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import warnings  # noqa: E402

from open_composer.research.equity_book.evaluate import load_rf_spy  # noqa: E402
from scripts import t22_run as R  # noqa: E402

warnings.filterwarnings("ignore", category=RuntimeWarning)
SEED = 20261006
TRAIN_NAMES_PER_DATE = 400
MAX_TRAIN_ROWS = 1_500_000
FIRST_PRED_YEAR = 2018
FEATURES = [
    "pca1",
    "pca5",
    "pca10",
    "pca21",
    "ind5",
    "ret1",
    "ret5",
    "ret21",
    "on5",
    "id5",
    "ladv",
    "turn",
    "vol21",
    "idio63",
    "beta",
    "news1d",
    "newssurge",
    "newsrow",
    "ff48",
]


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def rank_normal(x: np.ndarray, mask: np.ndarray) -> np.ndarray:
    from scipy.special import ndtri

    out = np.full(x.shape, np.nan, dtype="float32")
    v = np.flatnonzero(mask & np.isfinite(x))
    if len(v) < 20:
        return out
    r = np.argsort(np.argsort(x[v], kind="stable"), kind="stable")
    out[v] = ndtri((r + 0.5) / len(v)).astype("float32")
    return out


class Features:
    def __init__(self, store: R.Store, panel, u: int) -> None:
        self.s, self.u = store, u
        cols = np.array([panel.col(str(s)) if panel.has(str(s)) else -1 for s in store.symbols])
        self.cols = cols
        # float32 open/close on the master column order (NaN where the symbol is not in the panel)
        T, N = store.shape
        pd_idx = store.dates.get_indexer(panel.dates)
        self.o = np.full((T, N), np.nan, dtype="float32")
        self.c = np.asarray(store.m("close"), dtype="float32")
        ok = cols >= 0
        self.o[np.ix_(pd_idx, np.flatnonzero(ok))] = panel.open[:, cols[ok]].astype("float32")
        self.e_pca, self.e_ind = store.m("e_pca"), store.m("e_ind")
        self.m = {
            k: store.m(k)
            for k in (
                "adv_rank",
                "dollar_adv_21",
                "turnover",
                "vol_21",
                "idio_vol_63",
                "beta_252_spy",
                "ff48",
                "news_1d",
                "news_surge",
                "news_row",
                "is_tradeable",
            )
        }

    def candidates(self, t: int) -> np.ndarray:
        px = self.c[t]
        return (
            (np.asarray(self.m["adv_rank"][t]) <= self.u)
            & (np.asarray(self.m["is_tradeable"][t]) > 0)
            & np.isfinite(px)
            & (px >= R.PRICE_LO)
            & (px <= R.PRICE_HI)
        )

    def row(self, t: int, mask: np.ndarray) -> np.ndarray:
        """(N, F) rank-normal features at close t (only ``mask`` rows are filled)."""
        N = self.s.shape[1]
        X = np.full((N, len(FEATURES)), np.nan, dtype="float32")
        ep = np.asarray(self.e_pca[t - 20 : t + 1], dtype="float64")
        ei = np.asarray(self.e_ind[t - 4 : t + 1], dtype="float64")
        c, o = self.c, self.o
        with np.errstate(invalid="ignore", divide="ignore"):
            f = {
                "pca1": ep[-1],
                "pca5": np.nansum(ep[-5:], axis=0),
                "pca10": np.nansum(ep[-10:], axis=0),
                "pca21": np.nansum(ep, axis=0),
                "ind5": np.nansum(ei, axis=0),
                "ret1": c[t] / c[t - 1] - 1.0,
                "ret5": c[t] / c[t - 5] - 1.0,
                "ret21": c[t] / c[t - 21] - 1.0,
                "on5": np.nanmean(o[t - 4 : t + 1] / c[t - 5 : t] - 1.0, axis=0),
                "id5": np.nanmean(c[t - 4 : t + 1] / o[t - 4 : t + 1] - 1.0, axis=0),
                "ladv": np.log(np.asarray(self.m["dollar_adv_21"][t], dtype="float64")),
                "turn": np.asarray(self.m["turnover"][t], dtype="float64"),
                "vol21": np.asarray(self.m["vol_21"][t], dtype="float64"),
                "idio63": np.asarray(self.m["idio_vol_63"][t], dtype="float64"),
                "beta": np.asarray(self.m["beta_252_spy"][t], dtype="float64"),
                "news1d": np.asarray(self.m["news_1d"][t], dtype="float64"),
                "newssurge": np.asarray(self.m["news_surge"][t], dtype="float64"),
            }
        for k, name in enumerate(FEATURES):
            if name == "newsrow":
                X[:, k] = np.asarray(self.m["news_row"][t]).astype("float32")
            elif name == "ff48":
                X[:, k] = np.asarray(self.m["ff48"][t], dtype="float32")
            else:
                X[:, k] = rank_normal(f[name], mask)
        return X

    def label(self, t: int, H: int, mask: np.ndarray) -> np.ndarray:
        """Forward H-session open-to-open return from t+1 minus beta x SPY over the same span (NaN if missing)."""
        o = self.o
        s = self.s
        with np.errstate(invalid="ignore", divide="ignore"):
            r = o[t + 1 + H] / o[t + 1] - 1.0
            rs = o[t + 1 + H, s.spy] / o[t + 1, s.spy] - 1.0
        beta = np.clip(
            np.where(np.isfinite(self.m["beta_252_spy"][t]), self.m["beta_252_spy"][t], 1.0),
            -0.5,
            3.0,
        )
        y = (r - beta * rs).astype("float64")
        v = mask & np.isfinite(y)
        if v.sum() < 50:
            return np.full(y.shape, np.nan)
        lo, hi = np.percentile(y[v], [1, 99])
        y = np.clip(y, lo, hi)
        y[~v] = np.nan
        y[v] -= y[v].mean()
        return y


def fit_predict_model(kind: str, X: np.ndarray, y: np.ndarray):
    use = [i for i, n in enumerate(FEATURES) if not (kind == "ridge" and n == "ff48")]
    if kind == "ridge":
        from sklearn.linear_model import Ridge

        Xr = np.nan_to_num(X[:, use], nan=0.0)
        m = Ridge(alpha=1.0).fit(Xr, y)
        return lambda Z: m.predict(np.nan_to_num(Z[:, use], nan=0.0))
    import lightgbm as lgb

    ff_idx = FEATURES.index("ff48")
    m = lgb.LGBMRegressor(
        n_estimators=200,
        num_leaves=31,
        learning_rate=0.05,
        min_child_samples=200,
        colsample_bytree=0.8,
        subsample=0.8,
        subsample_freq=1,
        random_state=SEED,
        n_jobs=2,
        verbose=-1,
    )
    m.fit(X, y, categorical_feature=[ff_idx])
    return lambda Z: m.predict(Z)


def build_scores(store: R.Store, panel, u: int, H: int, kind: str) -> np.ndarray:
    feats = Features(store, panel, u)
    T, N = store.shape
    rng = np.random.default_rng(SEED)
    first = 260  # features need 21 sessions, residuals start at 2017-01
    # training pool: per-date subsample of rows with labels
    pool_t, pool_X, pool_y = [], [], []
    for t in range(first, T - H - 1):
        mask = feats.candidates(t)
        if mask.sum() < 150:
            continue
        y = feats.label(t, H, mask)
        v = np.flatnonzero(mask & np.isfinite(y))
        if len(v) < 100:
            continue
        pick = rng.choice(v, size=min(TRAIN_NAMES_PER_DATE, len(v)), replace=False)
        X = feats.row(t, mask)
        pool_t.append(np.full(len(pick), t))
        pool_X.append(X[pick])
        pool_y.append(y[pick].astype("float32"))
        if t % 400 == 0:
            log(f"pool t={t}")
    pt, PX, Py = np.concatenate(pool_t), np.concatenate(pool_X), np.concatenate(pool_y)
    log(f"training pool {PX.shape}")
    scores = np.full((T, N), np.nan, dtype="float32")
    for year in range(FIRST_PRED_YEAR, store.dates[-1].year + 1):
        yp = np.flatnonzero(store.dates.year == year)
        y0 = int(yp[0])
        keep = pt <= y0 - 1 - H  # label of date t ends at open t+1+H <= first session of the year
        idx = np.flatnonzero(keep)
        if len(idx) > MAX_TRAIN_ROWS:
            idx = np.sort(rng.choice(idx, size=MAX_TRAIN_ROWS, replace=False))
        t0 = time.time()
        pred = fit_predict_model(kind, PX[idx], Py[idx])
        log(f"{kind} {year}: fit on {len(idx)} rows in {time.time() - t0:.0f}s")
        for t in yp:
            mask = feats.candidates(int(t))
            if mask.sum() < 150:
                continue
            X = feats.row(int(t), mask)
            vv = np.flatnonzero(mask)
            scores[t, vv] = pred(X[vv]).astype("float32")
    return scores


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", choices=["ridge", "lgbm"], required=True)
    ap.add_argument("--window", default="recent")
    ap.add_argument(
        "--u",
        type=int,
        default=0,
        help="exploratory override of the universe (contract section 17)",
    )
    ap.add_argument("--H", type=int, default=0, help="exploratory override of the holding period")
    ap.add_argument("--exec", default="open")
    ap.add_argument("--tag", default="")
    a = ap.parse_args()
    sel = json.loads((R.RES / "selected.json").read_text())
    u, H = int(a.u or sel["universe"]), int(a.H or sel["H"])
    store = R.Store()
    out = R.RES / "ml"
    out.mkdir(parents=True, exist_ok=True)
    f = out / f"{a.model}_U{u}_H{H}.npy"
    reuse = (
        ROOT / "data/research/t22_ml_scores" / f.name
    )  # scores trained in phase 2 (shipped as data)
    if not f.exists() and reuse.exists():
        f = reuse
    start, end = (R.REC_START, R.REC_END) if False else ("2024-01-05", "2026-09-15")
    panel = R.load_panel(store, "2016-01-04", end)
    if f.exists():
        scores = np.load(f)
    else:
        scores = build_scores(store, panel, u, H, a.model)
        np.save(out / f.name, scores)
    # evaluate with the same book, costs and windows as the rule cells (recent, then stress)
    R.SCORE_OVERRIDE = scores
    rf, spy = load_rf_spy()
    for tag, (s0, e0) in {
        "ml_recent": ("2024-01-05", "2026-09-15"),
        "ml_stress": ("2017-09-29", "2023-08-31"),
    }.items():
        books = R.build_books(store, panel, s0, e0, u, "pca", 5, "none", H)
        res, probe = R.run_cell(store, panel, R.overlap_target(books, H, store), a.exec, s0, e0)
        window = ("2024-01-08", e0) if tag == "ml_recent" else (s0, e0)
        summ = R.summarize(res, rf, spy, probe, window)
        summ["cell_id"] = f"MODEL_{a.model}_U{u}_H{H}_{a.exec}"
        name = a.tag or a.model
        (out / f"{name}_{tag}.json").write_text(json.dumps(summ))
        res.daily.to_parquet(out / f"{name}_{tag}.parquet")
        log(f"{name} {tag}: net {summ['net_1x'].get('sharpe')} gross {summ['gross']['sharpe']}")


if __name__ == "__main__":
    main()
