"""Stage 2a alpha inputs for the equity book v1 (T-20261001-08, amendment A1 section 5).

Writes ``data/research/equity_book/alpha/book_v1/``:

* ``themes_<year>.parquet`` -- trade_date, symbol, in_u3000, in_p1000 and the nine theme scores
  (float32; the mean of the processed z columns of the theme, missing = 0);
* ``formation_ic.parquet`` -- formation_date, universe (u3000 / p1000), series (nine themes, M0,
  M1), ic (Spearman rank IC against the factor-neutral 21-session target y), n.

Formation dates are the last session of each calendar month of the session calendar, from the first
signal month until ``pos(d) + 22`` leaves the panel.  The target is ``forward_open_to_open(open,
close, p + 1, p + 22)`` minus the sum over k = p + 1 .. p + 21 of ``X_d . f_k`` (``X_d`` the risk
model's exposures at the formation date, ``f_k`` the daily factor returns).  M0 is the equal-weight
composite; M1 weights a formation date by the theme ICs of formation dates at least 22 sessions
earlier (at most 60, at least 24; proportional to max(0, mean / sd), equal weights otherwise).  No
performance statistic of any book is computed here.

    scripts/run_capped.sh --mem 1.8G -- uv run python scripts/build_book_v1_alpha.py
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from open_composer.research.equity_book import optimize as op  # noqa: E402
from open_composer.research.equity_book.panel import (  # noqa: E402
    DEFAULT_DIR,
    PanelAttributes,
    PricePanel,
)
from open_composer.research.equity_book.returns import forward_open_to_open  # noqa: E402
from open_composer.research.equity_book.risk import RiskModel  # noqa: E402
from open_composer.research.equity_book.signals import THEME_SIGNALS, THEMES  # noqa: E402

OUT_DIR = DEFAULT_DIR / "alpha" / "book_v1"
SIGNALS_DIR = DEFAULT_DIR / "signals"
RISK_DIR = DEFAULT_DIR / "risk"
LAG = 22  # sessions between a formation date and its first use
HORIZON = 22  # exit open position offset (entry p + 1, exit p + 22)
MIN_NAMES = 300
PRIOR_IC = 0.03
IC_WINDOW_MAX, IC_WINDOW_MIN = 36, 12
THEME_WINDOW_MAX, THEME_WINDOW_MIN = 60, 24
UNIVERSES = {"u3000": "in_u3000", "p1000": "in_p1000"}


# ---------------------------------------------------------------------------
# pure rules (shared with scripts/run_book_v1_stage2.py and the tests)
# ---------------------------------------------------------------------------


def month_end_positions(dates: pd.DatetimeIndex) -> np.ndarray:
    """Positions of the last session of each calendar month of the session calendar."""
    s = pd.Series(np.arange(len(dates)), index=pd.DatetimeIndex(dates))
    return s.groupby(s.index.to_period("M")).max().to_numpy()


def select_window(form_pos: np.ndarray, t_pos: int, max_n: int, lag: int = LAG) -> np.ndarray:
    """Indices (ascending position order) of the most recent at most ``max_n`` formation dates
    with ``pos(d) <= t_pos - lag``.  ``form_pos`` must be sorted ascending."""
    fp = np.asarray(form_pos)
    k = int(np.searchsorted(fp, t_pos - lag, side="right"))
    return np.arange(max(0, k - max_n), k)


def ic_scale(ics: np.ndarray) -> tuple[float, bool]:
    """``IC_t`` from the (lagged, windowed) formation ICs: ``max(0, 0.5 mean + 0.5 prior)``, the
    prior 0.03 when fewer than 12 are available.  Returns (IC_t, used_prior_only)."""
    v = np.asarray(ics, dtype="float64")
    v = v[np.isfinite(v)]
    if len(v) < IC_WINDOW_MIN:
        return PRIOR_IC, True
    return float(max(0.0, 0.5 * v.mean() + 0.5 * PRIOR_IC)), False


def m1_weights(theme_ic: np.ndarray) -> tuple[np.ndarray, bool]:
    """M1 theme weights from a (n_obs, n_themes) matrix of lagged theme ICs (rows = formation
    dates, ascending; NaN = the theme's IC is undefined that month): proportional to
    ``max(0, mean / sd)`` of each theme's finite ICs in the last 60 rows.  A theme with fewer
    than 24 finite ICs in the window gets weight 0 (no evidence yet).  Equal weights when the
    matrix has fewer than 24 rows or every weight is 0.  Returns (weights summing to 1,
    fell_back_to_equal)."""
    m = np.asarray(theme_ic, dtype="float64")
    n_themes = m.shape[1] if m.ndim == 2 else len(THEMES)
    eq = np.full(n_themes, 1.0 / n_themes)
    if m.ndim != 2 or m.shape[0] < THEME_WINDOW_MIN:
        return eq, True
    m = m[-THEME_WINDOW_MAX:]
    valid = np.isfinite(m).sum(axis=0)
    with np.errstate(invalid="ignore", divide="ignore", all="ignore"):
        mean = np.nanmean(m, axis=0)
        sd = np.nanstd(m, axis=0, ddof=1)
        ir = np.where((valid >= THEME_WINDOW_MIN) & (sd > 0), mean / sd, 0.0)
    w = np.where(np.isfinite(ir), np.maximum(ir, 0.0), 0.0)
    if w.sum() <= 0:
        return eq, True
    return w / w.sum(), False


def residual_target(
    open_: np.ndarray, close: np.ndarray, p: int, x: np.ndarray, fret: np.ndarray
) -> np.ndarray:
    """``forward_open_to_open(open, close, p + 1, p + 22) - x @ sum(fret)`` where ``fret`` holds
    the daily factor returns of sessions p + 1 .. p + 21 (shape (21, K)) and ``x`` is (N, K)
    aligned to the panel columns."""
    fwd = forward_open_to_open(open_, close, p + 1, p + HORIZON)
    return fwd - x @ np.nansum(fret, axis=0)


def rank_ic(score: np.ndarray, y: np.ndarray) -> tuple[float, int]:
    """Spearman correlation of two aligned arrays over the rows where both are finite."""
    ok = np.isfinite(score) & np.isfinite(y)
    n = int(ok.sum())
    if n < 3:
        return float("nan"), n
    a = pd.Series(score[ok]).rank().to_numpy()
    b = pd.Series(y[ok]).rank().to_numpy()
    a = a - a.mean()
    b = b - b.mean()
    den = float(np.sqrt((a * a).sum() * (b * b).sum()))
    return (float((a * b).sum() / den) if den > 0 else float("nan")), n


def theme_scores(frame: pd.DataFrame) -> pd.DataFrame:
    """Nine theme scores (float32): mean of the theme's processed z columns, missing = 0."""
    out = {}
    for t in THEMES:
        cols = list(THEME_SIGNALS[t])
        out[t] = frame[cols].astype("float64").fillna(0.0).mean(axis=1).astype("float32")
    return pd.DataFrame(out, index=frame.index)


# ---------------------------------------------------------------------------
# build
# ---------------------------------------------------------------------------


def load_year(year: int, attrs: PanelAttributes) -> pd.DataFrame:
    cols = ["trade_date", "symbol"] + [c for t in THEMES for c in THEME_SIGNALS[t]]
    sig = pq.read_table(SIGNALS_DIR / f"{year}.parquet", columns=cols).to_pandas()
    flags = attrs.year(year, columns=["in_u3000", "in_p1000"])
    df = sig.merge(flags, on=["trade_date", "symbol"], how="left")
    df["in_u3000"] = df["in_u3000"].fillna(False).astype(bool)
    df["in_p1000"] = df["in_p1000"].fillna(False).astype(bool)
    df = df.sort_values(["trade_date", "symbol"], kind="stable").reset_index(drop=True)
    ts = theme_scores(df)
    out = df[["trade_date", "symbol", "in_u3000", "in_p1000"]].copy()
    for t in THEMES:
        out[t] = ts[t].to_numpy()
    return out


def factor_return_matrix(factors: list[str]) -> pd.DataFrame:
    parts = [pd.read_parquet(p) for p in sorted(RISK_DIR.glob("factor_returns_*.parquet"))]
    long = pd.concat(parts, ignore_index=True)
    return long.pivot_table(index="trade_date", columns="factor", values="ret").reindex(
        columns=factors
    )


def build(args: argparse.Namespace) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    t_start = time.time()
    rm = RiskModel()
    attrs = PanelAttributes()
    panel = PricePanel.from_dir(start="2016-09-01")
    dates = panel.dates
    fr = factor_return_matrix(rm.factors)
    me_pos = month_end_positions(dates)
    years = sorted(int(p.stem) for p in SIGNALS_DIR.glob("[0-9]*.parquet"))
    first_year = years[0]
    first_sig_date = pd.Timestamp(
        pq.read_table(SIGNALS_DIR / f"{first_year}.parquet", columns=["trade_date"])
        .column(0)
        .to_pandas()
        .min()
    )
    last_pos = len(dates) - 1
    form = [
        int(p)
        for p in me_pos
        if dates[p] >= first_sig_date.to_period("M").to_timestamp() and p + HORIZON <= last_pos
    ]
    form_by_year: dict[int, list[int]] = {}
    for p in form:
        form_by_year.setdefault(dates[p].year, []).append(p)

    rows: list[dict] = []
    hist: dict[str, list[tuple[int, np.ndarray]]] = {u: [] for u in UNIVERSES}
    skipped: list[dict] = []
    check_diff = 0.0
    for year in years:
        t0 = time.time()
        th = load_year(year, attrs)
        # engineering check against the stored T-05 theme columns (not a performance number)
        stored_cols = [f"theme_{t}" for t in THEMES]
        stored = pq.read_table(
            SIGNALS_DIR / f"{year}.parquet", columns=["trade_date", "symbol"] + stored_cols
        ).to_pandas()
        stored = stored.sort_values(["trade_date", "symbol"], kind="stable").reset_index(drop=True)
        for t in THEMES:
            check_diff = max(
                check_diff,
                float(np.abs(th[t].to_numpy() - stored[f"theme_{t}"].to_numpy()).max()),
            )
        th.to_parquet(OUT_DIR / f"themes_{year}.parquet", index=False)
        by_date = {d: g for d, g in th.groupby("trade_date", sort=False)}
        for p in form_by_year.get(year, []):
            d = dates[p]
            try:
                x_df, _, _ = rm.at(d, exact=True)
            except KeyError:
                skipped.append({"formation_date": str(d.date()), "reason": "no_risk_model"})
                continue
            g = by_date.get(d)
            if g is None:
                skipped.append({"formation_date": str(d.date()), "reason": "no_signal_rows"})
                continue
            names = [s for s in x_df.index if panel.has(s)]
            cols = np.array([panel.col(s) for s in names], dtype=int)
            x = x_df.loc[names].to_numpy("float64")
            f_win = fr.reindex(dates[p + 1 : p + HORIZON]).to_numpy("float64")
            fwd = forward_open_to_open(
                panel.open[p + 1 : p + HORIZON + 1][:, cols],
                panel.close[p + 1 : p + HORIZON + 1][:, cols],
                0,
                HORIZON - 1,
            )
            y = pd.Series(fwd - x @ np.nansum(f_win, axis=0), index=names)
            gi = g.set_index("symbol")
            for uname, ucol in UNIVERSES.items():
                members = gi.index[gi[ucol].to_numpy()].intersection(y.index)
                sub = gi.loc[members, list(THEMES)].astype("float64")
                yy = y.loc[members].to_numpy()
                if len(members) < MIN_NAMES:
                    skipped.append(
                        {"formation_date": str(d.date()), "reason": f"n<{MIN_NAMES}:{uname}"}
                    )
                    continue
                ics = np.empty(len(THEMES))
                for k, t in enumerate(THEMES):
                    ics[k], n = rank_ic(sub[t].to_numpy(), yy)
                    rows.append(
                        {
                            "formation_date": d,
                            "universe": uname,
                            "series": t,
                            "ic": ics[k],
                            "n": n,
                        }
                    )
                eq = sub.mean(axis=1)
                ic0, n0 = rank_ic(op.rank_normal(eq).to_numpy(), yy)
                rows.append(
                    {"formation_date": d, "universe": uname, "series": "M0", "ic": ic0, "n": n0}
                )
                hp = np.array([q for q, _ in hist[uname]], dtype=int)
                idx = select_window(hp, p, THEME_WINDOW_MAX)
                mat = (
                    np.vstack([hist[uname][i][1] for i in idx])
                    if len(idx)
                    else np.zeros((0, len(THEMES)))
                )
                w, _ = m1_weights(mat)
                comp = pd.Series(sub.to_numpy() @ w, index=sub.index)
                ic1, n1 = rank_ic(op.rank_normal(comp).to_numpy(), yy)
                rows.append(
                    {"formation_date": d, "universe": uname, "series": "M1", "ic": ic1, "n": n1}
                )
                hist[uname].append((p, ics.copy()))
        print(f"{year}: themes written, {time.time() - t0:.1f}s", flush=True)
        del th, by_date, stored
    fic = pd.DataFrame(rows)
    fic["formation_date"] = pd.to_datetime(fic["formation_date"])
    fic["ic"] = fic["ic"].astype("float64")
    fic["n"] = fic["n"].astype("int64")
    pq.write_table(
        pa.Table.from_pandas(fic, preserve_index=False), OUT_DIR / "formation_ic.parquet"
    )
    meta = {
        "n_formation_dates_planned": len(form),
        "n_rows": len(fic),
        "n_skipped": len(skipped),
        "skipped": skipped,
        "theme_vs_stored_max_abs_diff": check_diff,
        "elapsed_s": time.time() - t_start,
        "themes": list(THEMES),
    }
    (OUT_DIR / "build_meta.json").write_text(json.dumps(meta, indent=1))
    print(
        f"formation dates planned {len(form)}, rows {len(fic)}, skipped {len(skipped)}, "
        f"theme check max diff {check_diff:.2e}, {time.time() - t_start:.0f}s",
        flush=True,
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    args = ap.parse_args()
    build(args)


if __name__ == "__main__":
    main()
