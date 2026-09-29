"""Net share issuance signal (T-20260929-70, h20260929_70_net_share_issuance).

NSI_L = ln(shares_t / shares_{t-L}) for L = 252 (candidate signal) and 126
(control), from the point-in-time cover-page share count in
``data/features/sec_fundamentals_daily`` (column ``shares_outstanding``; not split
adjusted, so a share-count pair is dropped when any of these frozen rules fire):

  (a) either end is missing or non-positive (values are forward-filled at most 5
      sessions to bridge calendar mismatches, never across a missing filing);
  (b) |ln(shares_t / shares_{t-L})| >= ln(1.5)    (split / reverse-split scale);
  (c) a split-like price session of the symbol lies in (t-L, t]: the sessions where
      ``sanitize_price_matrices`` defaults report a break (``last_session_before``
      .. ``first_session_after``) -- prices are split adjusted, so this catches
      bad prints and reused tickers, not ordinary splits;
  (d) within [t-L, t] the ratio to the base value reached |ln| >= ln(1.3) and
      came back below ln(1.3) by t (a swing-and-return, e.g. one class reported
      in one filing and the other class in the next).

Run through ``scripts/run_capped.sh --mem 1.8G --``. Output: ``data/features/nsi/nsi.parquet``
(symbol, trade_date, nsi252, nsi126) plus ``build_summary.json`` with drop counts.
"""

from __future__ import annotations

import json
import sys
import warnings
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from open_composer.research.features.price_hygiene import sanitize_price_matrices  # noqa: E402

FEATURES = ROOT / "data" / "features"
OUT_DIR = FEATURES / "nsi"
LN_1_5 = float(np.log(1.5))
LN_1_3 = float(np.log(1.3))
FFILL_LIMIT = 5


def clean_pairs(
    shares: np.ndarray, break_flag: np.ndarray, lag: int
) -> tuple[np.ndarray, dict[str, int]]:
    """``ln(s_t / s_{t-lag})`` per (session, symbol) with rules (a)-(d) applied.

    ``shares`` and ``break_flag`` are sessions x symbols; ``break_flag`` is True on
    sessions inside a split-like price break span. Returns the NaN-masked signal
    and the number of pairs each rule removed (counted on pairs valid under (a)).
    """
    T, N = shares.shape
    out = np.full((T, N), np.nan, dtype=np.float64)
    drops = {"valid_pairs": 0, "b_scale": 0, "c_price_break": 0, "d_swing_back": 0, "kept": 0}
    if T <= lag:
        return out, drops
    with np.errstate(invalid="ignore", divide="ignore"):
        logs = np.where(shares > 0, np.log(shares), np.nan)
    cum_break = np.cumsum(break_flag.astype(np.int32), axis=0)
    for j in range(N):
        x = logs[:, j]
        if not np.isfinite(x).any():
            continue
        cur = x[lag:]
        base = x[:-lag]
        delta = cur - base
        valid = np.isfinite(delta)
        if not valid.any():
            continue
        drops["valid_pairs"] += int(valid.sum())
        bad_b = valid & (np.abs(delta) >= LN_1_5)
        cb = cum_break[:, j]
        bad_c = valid & ((cb[lag:] - cb[:-lag]) > 0)
        win = np.lib.stride_tricks.sliding_window_view(x, lag + 1)  # (T-lag, lag+1)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            exc = np.nanmax(np.abs(win - base[:, None]), axis=1)
        bad_d = valid & (exc >= LN_1_3) & (np.abs(delta) < LN_1_3)
        drops["b_scale"] += int(bad_b.sum())
        drops["c_price_break"] += int((bad_c & ~bad_b).sum())
        drops["d_swing_back"] += int((bad_d & ~bad_b & ~bad_c).sum())
        keep = valid & ~bad_b & ~bad_c & ~bad_d
        drops["kept"] += int(keep.sum())
        col = np.full(T, np.nan)
        col[lag:] = np.where(keep, delta, np.nan)
        out[:, j] = col
    return out, drops


def _ffill_limited(a: np.ndarray, limit: int) -> np.ndarray:
    df = pd.DataFrame(a).ffill(limit=limit)
    return df.to_numpy()


def main() -> None:
    con = duckdb.connect()
    con.execute("SET memory_limit='1000MB'")
    con.execute("SET threads=2")
    uni = con.execute(
        f"SELECT DISTINCT symbol FROM read_parquet('{FEATURES}/universe_broad/*.parquet') "
        "WHERE adv_rank <= 3000 AND close >= 5"
    ).df()
    symbols = pd.Index(sorted(uni["symbol"]))
    dates = pd.DatetimeIndex(
        con.execute(
            "SELECT DISTINCT trade_date "
            f"FROM read_parquet('{FEATURES}/daily_broad/*.parquet') ORDER BY 1"
        ).df()["trade_date"]
    )
    con.register("syms", pd.DataFrame({"symbol": symbols, "sid": np.arange(len(symbols))}))
    con.register("days", pd.DataFrame({"trade_date": dates, "tid": np.arange(len(dates))}))
    px = con.execute(
        f"""SELECT d.tid, s.sid, CAST(p.close AS FLOAT) AS close
        FROM read_parquet('{FEATURES}/daily_broad/*.parquet') p
        JOIN syms s USING (symbol) JOIN days d USING (trade_date)"""
    ).fetchnumpy()
    close = np.full((len(dates), len(symbols)), np.nan, dtype=np.float32)
    close[px["tid"], px["sid"]] = px["close"]
    del px
    _c, _o, report = sanitize_price_matrices(pd.DataFrame(close, index=dates, columns=symbols))
    del _c, _o, close
    break_flag = np.zeros((len(dates), len(symbols)), dtype=bool)
    for br in report.breaks:
        if br.symbol not in symbols:
            continue
        lo = dates.searchsorted(br.last_session_before)
        hi = dates.searchsorted(br.first_session_after)
        break_flag[lo + 1 : hi + 1, symbols.get_loc(br.symbol)] = True
    sh = con.execute(
        f"""SELECT d.tid, s.sid, q.shares_outstanding AS sh
        FROM read_parquet('{FEATURES}/sec_fundamentals_daily/*.parquet') q
        JOIN syms s USING (symbol) JOIN days d ON d.trade_date = CAST(q.trade_date AS TIMESTAMP)
        WHERE q.shares_outstanding IS NOT NULL"""
    ).fetchnumpy()
    con.close()
    shares = np.full((len(dates), len(symbols)), np.nan, dtype=np.float64)
    shares[sh["tid"], sh["sid"]] = sh["sh"]
    del sh
    shares = _ffill_limited(shares, FFILL_LIMIT)
    summary: dict = {
        "rules": "a missing/non-positive; b |dlog|>=ln1.5; c split-like price break in (t-L,t]; "
        "d excursion>=ln1.3 that returned below ln1.3",
        "symbols": int(len(symbols)),
        "sessions": int(len(dates)),
        "price_breaks_detected": int(len(report.breaks)),
        "symbols_masked_by_hygiene": int(report.symbols_masked),
    }
    cols: dict[str, np.ndarray] = {}
    for lag in (252, 126):
        sig, drops = clean_pairs(shares, break_flag, lag)
        cols[f"nsi{lag}"] = sig
        summary[f"L{lag}"] = drops
        print(lag, drops, flush=True)
    frames = []
    ok = np.isfinite(cols["nsi252"]) | np.isfinite(cols["nsi126"])
    ti, si = np.nonzero(ok)
    frame = pd.DataFrame(
        {
            "symbol": symbols[si],
            "trade_date": dates[ti],
            "nsi252": cols["nsi252"][ti, si],
            "nsi126": cols["nsi126"][ti, si],
        }
    )
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(OUT_DIR / "nsi.parquet", index=False)
    summary["rows"] = int(len(frame))
    summary["nonnull_nsi252"] = int(frame["nsi252"].notna().sum())
    summary["nonnull_nsi126"] = int(frame["nsi126"].notna().sum())
    (OUT_DIR / "build_summary.json").write_text(json.dumps(summary, indent=2))
    del frames


if __name__ == "__main__":
    main()
