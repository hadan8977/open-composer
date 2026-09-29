"""T-20260929-11: multi-quarter SUE history elastic net (Kaczmarek & Zaremba 2025).

Builds `reports/research/iterations/h20260929_11_multiq_sue/scores.parquet`
(symbol, date, score, score_shuf, sue1, model_year), `model-fits.json` (per
test-year hyperparameters, coefficients, training sizes, monthly RankIC) and
`price-hygiene.json`. Everything is fixed in candidate-manifest.json before
any result was computed; see its `contracts` block.

    scripts/run_capped.sh --mem 1.3G -- \\
        uv run python scripts/build_h20260929_11_multiq_sue_scores.py

Point-in-time rules:
  * An earnings event becomes visible on the first session after the filing
    (`days_since_report == 0` row of data/features/sec_fundamentals_daily);
    the features of date d use only events with visible date <= d.
  * The model for test year Y is trained only on month-end samples whose label
    end session (open[t+22]) is strictly before the first session of Y.
  * Hyperparameters are chosen only by TimeSeriesSplit(gap=1) inside that
    training set.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ITER = "h20260929_11_multiq_sue"
OUT_DIR = ROOT / "reports/research/iterations" / ITER
CACHE_DIR = ROOT / "data/features" / ITER
MEMBERSHIP_CSV = ROOT / "data/sip-delisted/sp500_ticker_start_end_fja05680.csv"
SUE_DAILY_DIR = ROOT / "data/features/sec_fundamentals_daily"

PANEL_START = "2015-01-02"
PANEL_END = "2026-09-17"  # same HOLD_END as run_h20260918_05_recent_menu
FIRST_TRAIN_MONTH_END = pd.Timestamp("2016-06-01")
TEST_YEARS = list(range(2019, 2027))
N_LAGS = 8
STALE_DAYS = 200
LABEL_START = 1  # open of session t+1
LABEL_END = 22  # open of session t+22
ALPHAS = [1e-4, 3e-4, 1e-3, 3e-3, 1e-2, 3e-2, 1e-1]
L1_RATIOS = [0.1, 0.5, 0.9]
CV_SPLITS = 4
CV_GAP_MONTHS = 1
SEED = 20260929
SPLIT_RATIOS = np.array([2, 3, 4, 5, 10, 1 / 2, 1 / 3, 1 / 4, 1 / 5, 1 / 10])
SPLIT_TOL = 0.02
FEATURE_NAMES = (
    [f"sue_eps_lag{j}" for j in range(1, N_LAGS + 1)]
    + [f"sue_rev_lag{j}" for j in range(1, N_LAGS + 1)]
    + ["streak_pos", "streak_neg", "n_missing_eps", "n_missing_rev"]
)


# --------------------------------------------------------------------------
# pool + prices
# --------------------------------------------------------------------------


def load_membership() -> pd.DataFrame:
    df = pd.read_csv(MEMBERSHIP_CSV)
    df["start_date"] = pd.to_datetime(df["start_date"])
    df["end_date"] = pd.to_datetime(df["end_date"].fillna("2099-01-01"))
    return df[df["end_date"] >= "2016-01-01"].reset_index(drop=True)


def pool_tickers() -> list[str]:
    return sorted(load_membership()["ticker"].unique())


def membership_matrix(index: pd.DatetimeIndex, tickers: list[str]) -> pd.DataFrame:
    """Boolean (date x ticker): S&P 500 member on that date."""
    mem = load_membership()
    out = pd.DataFrame(False, index=index, columns=tickers)
    for row in mem.itertuples(index=False):
        if row.ticker not in out.columns:
            continue
        mask = (index >= row.start_date) & (index <= row.end_date)
        out.loc[mask, row.ticker] = True
    return out


def _load_prices_raw(tickers: list[str]) -> pd.DataFrame:
    import duckdb

    con = duckdb.connect()
    con.execute("SET memory_limit='600MB'")
    con.execute("SET threads=2")
    in_list = ",".join(f"'{s}'" for s in [*tickers, "SPY"])
    frame = con.execute(
        f"""
        WITH src AS (
            SELECT symbol, timestamp::DATE AS d, open, close, volume, trade_count
            FROM read_parquet('data/sip/daily/*/*.parquet')
            UNION ALL
            SELECT symbol, timestamp::DATE AS d, open, close, volume, trade_count
            FROM read_parquet('data/sip-delisted/daily/*.parquet')
        )
        SELECT * FROM src
        WHERE symbol IN ({in_list})
          AND d >= DATE '{PANEL_START}' AND d <= DATE '{PANEL_END}'
        """
    ).df()
    con.close()
    ghost = (frame["volume"].fillna(0) <= 0) & (frame["trade_count"].fillna(0) <= 0)
    frame = frame.loc[~ghost]
    frame = frame.sort_values("volume", ascending=False).drop_duplicates(["symbol", "d"])
    return frame


def load_pool_prices(refresh: bool = False) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """(close, open, hygiene manifest) for the pool, after
    `sanitize_price_matrices` with default parameters. Cached under data/features."""
    from open_composer.research.features.price_hygiene import sanitize_price_matrices

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cpath, opath, hpath = (
        CACHE_DIR / "close.parquet",
        CACHE_DIR / "open.parquet",
        CACHE_DIR / "hygiene.json",
    )
    if not refresh and cpath.exists() and opath.exists() and hpath.exists():
        return (
            pd.read_parquet(cpath),
            pd.read_parquet(opath),
            json.loads(hpath.read_text(encoding="utf-8")),
        )
    frame = _load_prices_raw(pool_tickers())
    close = frame.pivot(index="d", columns="symbol", values="close").sort_index()
    open_ = frame.pivot(index="d", columns="symbol", values="open").sort_index()
    close.index = pd.to_datetime(close.index)
    open_.index = pd.to_datetime(open_.index)
    calendar = close["SPY"].dropna().index
    close = close.reindex(calendar).drop(columns=["SPY"], errors="ignore")
    open_ = open_.reindex(calendar).drop(columns=["SPY"], errors="ignore")
    close, open_, report = sanitize_price_matrices(close, open_)
    manifest = report.manifest()
    manifest["n_symbols"] = int(close.shape[1])
    manifest["calendar"] = [str(calendar[0].date()), str(calendar[-1].date())]
    close.to_parquet(cpath)
    open_.to_parquet(opath)
    hpath.write_text(json.dumps(manifest, default=str), encoding="utf-8")
    return close, open_, manifest


# --------------------------------------------------------------------------
# events and features
# --------------------------------------------------------------------------


def load_events(tickers: list[str]) -> pd.DataFrame:
    """One row per (symbol, visible session): sue_eps, sue_rev."""
    parts = []
    for path in sorted(SUE_DAILY_DIR.glob("*.parquet")):
        df = pd.read_parquet(
            path, columns=["symbol", "trade_date", "sue_eps", "sue_rev", "days_since_report"]
        )
        df = df[df["symbol"].isin(tickers) & (df["days_since_report"] == 0)]
        parts.append(df[["symbol", "trade_date", "sue_eps", "sue_rev"]])
    ev = pd.concat(parts, ignore_index=True)
    ev = ev.sort_values(["symbol", "trade_date"]).drop_duplicates(
        ["symbol", "trade_date"], keep="last"
    )
    return ev.reset_index(drop=True)


def _streaks(values: np.ndarray, positive: bool) -> np.ndarray:
    out = np.zeros(len(values))
    run = 0
    for i, v in enumerate(values):
        cond = np.isfinite(v) and ((v > 0) if positive else (v < 0))
        run = run + 1 if cond else 0
        out[i] = run
    return out


class EventStore:
    """Per-symbol event arrays, padded so lag lookups are pure indexing."""

    def __init__(self, events: pd.DataFrame, symbols: list[str]):
        self.symbols = list(symbols)
        self.dates: list[np.ndarray] = []
        pad = N_LAGS
        kmax = int(events.groupby("symbol").size().max()) if len(events) else 0
        width = pad + kmax + 1
        self.eps = np.full((len(symbols), width), np.nan)
        self.rev = np.full((len(symbols), width), np.nan)
        self.spos = np.zeros((len(symbols), kmax + 2))
        self.sneg = np.zeros((len(symbols), kmax + 2))
        grouped = {s: g for s, g in events.groupby("symbol")}
        for i, sym in enumerate(symbols):
            g = grouped.get(sym)
            if g is None:
                self.dates.append(np.array([], dtype="datetime64[ns]"))
                continue
            n = len(g)
            self.dates.append(g["trade_date"].to_numpy(dtype="datetime64[ns]"))
            self.eps[i, pad : pad + n] = g["sue_eps"].to_numpy()
            self.rev[i, pad : pad + n] = g["sue_rev"].to_numpy()
            self.spos[i, 1 : n + 1] = _streaks(g["sue_eps"].to_numpy(), True)
            self.sneg[i, 1 : n + 1] = _streaks(g["sue_eps"].to_numpy(), False)

    def counts(self, dates: pd.DatetimeIndex) -> np.ndarray:
        """(len(dates), n_symbols): number of events visible on or before each date."""
        d64 = dates.to_numpy(dtype="datetime64[ns]")
        out = np.zeros((len(dates), len(self.symbols)), dtype=np.int64)
        for i, arr in enumerate(self.dates):
            if len(arr):
                out[:, i] = np.searchsorted(arr, d64, side="right")
        return out

    def features(self, k: np.ndarray, sym_idx: np.ndarray) -> np.ndarray:
        """Raw features (n, 20) for symbols `sym_idx` with event counts `k`.
        Lag j value = event number k-j (1 = most recent). Only events counted in
        `k` (visible on or before the date) are ever indexed."""
        pad = N_LAGS
        cols = []
        eps_lags = np.stack([self.eps[sym_idx, pad + k - j] for j in range(1, N_LAGS + 1)], axis=1)
        rev_lags = np.stack([self.rev[sym_idx, pad + k - j] for j in range(1, N_LAGS + 1)], axis=1)
        cols.append(eps_lags)
        cols.append(rev_lags)
        cols.append(self.spos[sym_idx, k][:, None])
        cols.append(self.sneg[sym_idx, k][:, None])
        cols.append(np.isnan(eps_lags).sum(axis=1)[:, None].astype(float))
        cols.append(np.isnan(rev_lags).sum(axis=1)[:, None].astype(float))
        return np.hstack(cols)

    def last_visible(self, k: np.ndarray, sym_idx: np.ndarray) -> np.ndarray:
        out = np.full(len(sym_idx), np.datetime64("NaT"), dtype="datetime64[ns]")
        for n, (s, kk) in enumerate(zip(sym_idx, k, strict=True)):
            if kk >= 1:
                out[n] = self.dates[s][kk - 1]
        return out


def rank_standardize(raw: np.ndarray) -> np.ndarray:
    """Fill missing with 0, then per column (average percentile rank) - 0.5."""
    filled = np.where(np.isfinite(raw), raw, 0.0)
    return pd.DataFrame(filled).rank(pct=True, method="average").to_numpy() - 0.5


def split_like(close: pd.DataFrame) -> pd.DataFrame:
    """Signal-day rule: close/prev close within 2% of a common split ratio."""
    ratio = close / close.shift(1)
    flag = pd.DataFrame(False, index=close.index, columns=close.columns)
    arr = ratio.to_numpy()
    out = np.zeros(arr.shape, dtype=bool)
    for r in SPLIT_RATIOS:
        out |= np.abs(arr / r - 1.0) <= SPLIT_TOL
    flag[:] = out
    return flag


def labels_month_end(open_: pd.DataFrame, positions: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """(label matrix (len(positions), n_sym), label end session position)."""
    op = open_.to_numpy()
    op_ff = open_.ffill().to_numpy()
    n = len(open_.index)
    lab = np.full((len(positions), op.shape[1]), np.nan)
    end_pos = positions + LABEL_END
    for r, p in enumerate(positions):
        if p + LABEL_END >= n:
            continue
        start = op[p + LABEL_START]
        end = op_ff[p + LABEL_END]
        with np.errstate(invalid="ignore", divide="ignore"):
            lab[r] = end / start - 1.0
    return lab, end_pos


def month_end_positions(index: pd.DatetimeIndex) -> np.ndarray:
    s = pd.Series(np.arange(len(index)), index=index)
    return s.groupby(index.to_period("M")).max().to_numpy()


# --------------------------------------------------------------------------
# panel of features for a set of dates
# --------------------------------------------------------------------------


class Panel:
    def __init__(self) -> None:
        self.close, self.open_, self.hygiene = load_pool_prices()
        self.symbols = list(self.close.columns)
        self.index = self.close.index
        events = load_events(self.symbols)
        self.store = EventStore(events, self.symbols)
        self.member = membership_matrix(self.index, self.symbols).to_numpy()
        self.split = split_like(self.close).to_numpy()
        self.close_np = self.close.to_numpy()
        self.mom = (self.close.shift(21) / self.close.shift(252) - 1.0).to_numpy()

    def snapshot(self, positions: np.ndarray):
        """For each session position: (eligible symbol idx, standardized X, raw sue1, mom)."""
        dates = self.index[positions]
        counts = self.store.counts(dates)
        out = []
        for r, p in enumerate(positions):
            k_all = counts[r]
            ok = self.member[p] & np.isfinite(self.close_np[p]) & ~self.split[p] & (k_all >= 1)
            idx = np.flatnonzero(ok)
            if len(idx) == 0:
                out.append((idx, np.zeros((0, len(FEATURE_NAMES))), np.array([]), np.array([])))
                continue
            k = k_all[idx]
            last = self.store.last_visible(k, idx)
            fresh = (dates[r].to_datetime64() - last) <= np.timedelta64(STALE_DAYS, "D")
            idx, k = idx[fresh], k[fresh]
            raw = self.store.features(k, idx)
            sue1 = raw[:, 0].copy()
            out.append((idx, rank_standardize(raw), sue1, self.mom[p, idx]))
        return out


# --------------------------------------------------------------------------
# model
# --------------------------------------------------------------------------


def training_months_for_year(
    label_end_pos: np.ndarray, usable: list[bool], first_pos: int
) -> list[int]:
    """Indices of month-end samples usable for a test year starting at session
    `first_pos`: the sample must exist and its label end session must lie strictly
    before the first session of the test year."""
    return [r for r, ok in enumerate(usable) if ok and label_end_pos[r] < first_pos]


def cv_splits(month_id: np.ndarray):
    from sklearn.model_selection import TimeSeriesSplit

    months = np.unique(month_id)
    tss = TimeSeriesSplit(n_splits=CV_SPLITS, gap=CV_GAP_MONTHS)
    for tr, va in tss.split(months):
        tr_rows = np.flatnonzero(np.isin(month_id, months[tr]))
        va_rows = np.flatnonzero(np.isin(month_id, months[va]))
        yield tr_rows, va_rows


def fit_enet(X: np.ndarray, y: np.ndarray, month_id: np.ndarray) -> dict:
    from sklearn.linear_model import ElasticNet, ElasticNetCV

    cv = list(cv_splits(month_id))
    cvm = ElasticNetCV(
        alphas=ALPHAS,
        l1_ratio=L1_RATIOS,
        cv=cv,
        max_iter=10000,
        fit_intercept=True,
        random_state=0,
    )
    cvm.fit(X, y)
    alpha, l1 = float(cvm.alpha_), float(cvm.l1_ratio_)
    model = ElasticNet(
        alpha=alpha, l1_ratio=l1, max_iter=10000, fit_intercept=True, random_state=0
    ).fit(X, y)
    return {"model": model, "alpha": alpha, "l1_ratio": l1}


def shuffle_labels(y: np.ndarray, month_id: np.ndarray, year: int) -> np.ndarray:
    """Permute labels within each training month (numpy default_rng([SEED, year]))."""
    rng = np.random.default_rng([SEED, year])
    out = y.copy()
    for m in np.unique(month_id):
        rows = np.flatnonzero(month_id == m)
        out[rows] = y[rows][rng.permutation(len(rows))]
    return out


def spearman(a: np.ndarray, b: np.ndarray) -> float:
    ok = np.isfinite(a) & np.isfinite(b)
    if ok.sum() < 30:
        return float("nan")
    ra = pd.Series(a[ok]).rank().to_numpy()
    rb = pd.Series(b[ok]).rank().to_numpy()
    return float(np.corrcoef(ra, rb)[0, 1])


def ic_summary(ics: list[float]) -> dict:
    arr = np.array([x for x in ics if np.isfinite(x)])
    if len(arr) < 3:
        return {"n_months": int(len(arr)), "mean": None, "t": None}
    return {
        "n_months": int(len(arr)),
        "mean": float(arr.mean()),
        "t": float(arr.mean() / (arr.std(ddof=1) / np.sqrt(len(arr)))),
    }


def main() -> int:
    t0 = time.time()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    panel = Panel()
    print(f"panel {panel.close.shape}, events loaded, {time.time() - t0:.0f}s", flush=True)
    (OUT_DIR / "price-hygiene.json").write_text(
        json.dumps(panel.hygiene, indent=2, default=str), encoding="utf-8"
    )

    me_pos = month_end_positions(panel.index)
    me_pos = me_pos[panel.index[me_pos] >= FIRST_TRAIN_MONTH_END]
    me_pos = me_pos[me_pos + LABEL_END < len(panel.index)]
    snaps = panel.snapshot(me_pos)
    labels, end_pos = labels_month_end(panel.open_, me_pos)
    train_rows = []  # per month-end: (X, y_rank)
    for r, (idx, X, _sue1, _mom) in enumerate(snaps):
        if len(idx) == 0:
            train_rows.append(None)
            continue
        lab = labels[r, idx]
        ok = np.isfinite(lab) & np.isfinite(panel.open_.to_numpy()[me_pos[r] + LABEL_START, idx])
        if ok.sum() < 30:
            train_rows.append(None)
            continue
        y_rank = pd.Series(lab[ok]).rank(pct=True).to_numpy() - 0.5
        train_rows.append((X[ok], y_rank))
    print(f"training snapshots {sum(t is not None for t in train_rows)}", flush=True)

    fits: dict[str, dict] = {}
    score_frames = []
    ic_rows: dict[str, dict[int, list[float]]] = {
        k: {} for k in ("enet", "enet_shuf", "sue1", "mom12_1")
    }
    for year in TEST_YEARS:
        first_pos = int(np.searchsorted(panel.index, pd.Timestamp(f"{year}-01-01")))
        if first_pos >= len(panel.index):
            break
        sel = training_months_for_year(end_pos, [t is not None for t in train_rows], first_pos)
        Xs = np.vstack([train_rows[r][0] for r in sel])
        ys = np.concatenate([train_rows[r][1] for r in sel])
        mid = np.concatenate([np.full(len(train_rows[r][1]), n) for n, r in enumerate(sel)])
        real = fit_enet(Xs, ys, mid)
        shuf = fit_enet(Xs, shuffle_labels(ys, mid, year), mid)
        fits[str(year)] = {
            "train_months": len(sel),
            "train_rows": int(len(ys)),
            "train_first_month_end": str(panel.index[me_pos[sel[0]]].date()),
            "train_last_month_end": str(panel.index[me_pos[sel[-1]]].date()),
            "train_last_label_end": str(panel.index[end_pos[sel[-1]]].date()),
            "test_year_first_session": str(panel.index[first_pos].date()),
            "alpha": real["alpha"],
            "l1_ratio": real["l1_ratio"],
            "coef": dict(zip(FEATURE_NAMES, map(float, real["model"].coef_), strict=True)),
            "intercept": float(real["model"].intercept_),
            "shuf_alpha": shuf["alpha"],
            "shuf_l1_ratio": shuf["l1_ratio"],
            "shuf_nonzero_coefs": int((shuf["model"].coef_ != 0).sum()),
        }
        print(
            f"year {year}: rows {len(ys)} alpha {real['alpha']} l1 {real['l1_ratio']}"
            f" nonzero {(real['model'].coef_ != 0).sum()} ({time.time() - t0:.0f}s)",
            flush=True,
        )
        last_pos = int(
            np.searchsorted(panel.index, pd.Timestamp(f"{year}-12-31"), side="right") - 1
        )
        pos_year = np.arange(first_pos, last_pos + 1)
        me_set = set(month_end_positions(panel.index).tolist())
        snap_y = panel.snapshot(pos_year)
        for p, (idx, X, sue1, mom) in zip(pos_year, snap_y, strict=True):
            if len(idx) == 0:
                continue
            score = real["model"].predict(X)
            score_shuf = shuf["model"].predict(X)
            score_frames.append(
                pd.DataFrame(
                    {
                        "symbol": np.array(panel.symbols)[idx],
                        "date": panel.index[p],
                        "score": score,
                        "score_shuf": score_shuf,
                        "sue1": sue1,
                        "model_year": year,
                    }
                )
            )
            if p in me_set and p + LABEL_END < len(panel.index):
                lab_all, _ = labels_month_end(panel.open_, np.array([p]))
                lab = lab_all[0, idx]
                for key, vec in (
                    ("enet", score),
                    ("enet_shuf", score_shuf),
                    ("sue1", sue1),
                    ("mom12_1", mom),
                ):
                    ic_rows[key].setdefault(year, []).append(spearman(vec, lab))

    scores = pd.concat(score_frames, ignore_index=True)
    scores.to_parquet(OUT_DIR / "scores.parquet", index=False)

    rankic: dict[str, dict] = {}
    for key, per_year in ic_rows.items():
        rankic[key] = {str(y): ic_summary(v) for y, v in sorted(per_year.items())}
        rankic[key]["2019-2023"] = ic_summary(
            [x for y, v in per_year.items() if y <= 2023 for x in v]
        )
        rankic[key]["2024+"] = ic_summary([x for y, v in per_year.items() if y >= 2024 for x in v])
    (OUT_DIR / "model-fits.json").write_text(
        json.dumps(
            {
                "iter_id": ITER,
                "feature_names": FEATURE_NAMES,
                "alphas": ALPHAS,
                "l1_ratios": L1_RATIOS,
                "cv": f"TimeSeriesSplit(n_splits={CV_SPLITS}, gap={CV_GAP_MONTHS}) on months",
                "seed": SEED,
                "fits": fits,
                "monthly_rankic": rankic,
                "rankic_note": (
                    "Spearman between the model score on each month-end session and the"
                    " open[t+22]/open[t+1]-1 return; rows per test-year model."
                ),
                "scores_rows": int(len(scores)),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(json.dumps({k: {p: v[p] for p in ("2019-2023", "2024+")} for k, v in rankic.items()}))
    print(f"done in {time.time() - t0:.0f}s, scores {scores.shape}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
