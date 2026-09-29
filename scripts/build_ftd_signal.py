"""SEC fails-to-deliver signals (T-20260929-72, h20260929_72_sec_ftd).

Input ``data/sec_ftd/cnsfails<YYYYMM><a|b>.parquet`` (scripts/fetch_sec_ftd.py) plus
``data/features/daily_broad`` and ``sec_fundamentals_daily``. Output
``data/features/ftd/ftd.parquet`` (symbol, trade_date, ftdsh, ftdadv, ftd_dummy) and
``build_summary.json`` (match and drop counts).

Frozen rules (written before any return was computed):

* One balance per file: the rows of the file's LAST settlement date. The SEC file lists
  every security with a non-zero balance (since 2008-09-16), so a symbol absent from the
  file has a zero balance.
* PIT: the balance is usable from the first trading day after ``available_date`` (see
  ``fetch_sec_ftd.available_date``) and held until the next file becomes usable. The
  card's own close-signal -> next-open convention adds one further session.
* A balance is held at most 25 sessions (files the SEC did not serve leave NaN gaps,
  never a stale carry-over).
* Ticker alignment: exact match of the FTD ticker to a SIP symbol of the universe
  (ADV rank <= 3000 at some month end, close >= 5). Unmatched rows are counted and
  dropped. Reused tickers / bad prints: the FTD price field is the PREVIOUS day's close;
  a row is kept only if it is within 20% of the SIP close of the last trading day before
  the settlement date. Rows with a missing price, no SIP close or a deviation >= 20% are
  dropped (their symbol-file value is unknown, NaN, not zero).
* FTDSH = fails / shares_outstanding. Denominator: latest point-in-time cover-page
  ``shares_outstanding`` at the day before settlement (forward fill <= 5 sessions; not
  split adjusted, so used only as the latest value). Row dropped for FTDSH when shares
  are missing or <= 0, fails / shares > 0.5, or shares x SIP close is below 20 million
  or above 5 trillion dollars.
* FTDADV = fails x SIP close / ``dollar_adv_21`` (the prebuilt 21-session mean dollar
  volume, both at the day before settlement; the plan said 20 sessions, the prebuilt
  window is 21).
* ftd_dummy = 1 for a kept row with fails > 0 (control, not a candidate), else 0.

    flock /tmp/oc-heavy-r2207.lock scripts/run_capped.sh --mem 1.8G -- \
        uv run python scripts/build_ftd_signal.py
"""

from __future__ import annotations

import json
import re
import sys
from datetime import date
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from fetch_sec_ftd import available_date  # noqa: E402

FEATURES = ROOT / "data" / "features"
FTD_DIR = ROOT / "data" / "sec_ftd"
OUT_DIR = FEATURES / "ftd"
PRICE_TOL = 0.20
MAX_FTD_OVER_SHARES = 0.5
MIN_CAP, MAX_CAP = 2.0e7, 5.0e12
FFILL_LIMIT = 5
MAX_HOLD_SESSIONS = 25  # a balance is not carried past this many sessions (missing file)


def prev_trading_index(dates: pd.DatetimeIndex, d: date) -> int:
    """Index of the last session strictly before ``d`` (-1 if none)."""
    return int(dates.searchsorted(pd.Timestamp(d), side="left")) - 1


def main() -> None:
    con = duckdb.connect()
    con.execute("SET memory_limit='1000MB'")
    con.execute("SET threads=2")
    symbols = pd.Index(
        sorted(
            con.execute(
                f"SELECT DISTINCT symbol FROM read_parquet('{FEATURES}/universe_broad/*.parquet') "
                "WHERE adv_rank <= 3000 AND close >= 5"
            ).df()["symbol"]
        )
    )
    all_syms = set(
        con.execute(
            f"SELECT DISTINCT symbol FROM read_parquet('{FEATURES}/daily_broad/*.parquet')"
        ).df()["symbol"]
    )
    dates = pd.DatetimeIndex(
        con.execute(
            f"SELECT DISTINCT trade_date FROM read_parquet('{FEATURES}/daily_broad/*.parquet') "
            "ORDER BY 1"
        ).df()["trade_date"]
    )
    con.register("syms", pd.DataFrame({"symbol": symbols, "sid": np.arange(len(symbols))}))
    con.register("days", pd.DataFrame({"trade_date": dates, "tid": np.arange(len(dates))}))
    px = con.execute(
        f"""SELECT d.tid, s.sid, CAST(p.close AS FLOAT) AS close,
                   CAST(p.dollar_adv_21 AS DOUBLE) AS adv21
        FROM read_parquet('{FEATURES}/daily_broad/*.parquet') p
        JOIN syms s USING (symbol) JOIN days d USING (trade_date)"""
    ).fetchnumpy()
    shape = (len(dates), len(symbols))
    close = np.full(shape, np.nan, dtype=np.float32)
    adv21 = np.full(shape, np.nan, dtype=np.float64)
    close[px["tid"], px["sid"]] = px["close"]
    adv21[px["tid"], px["sid"]] = px["adv21"]
    del px
    sh = con.execute(
        f"""SELECT d.tid, s.sid, q.shares_outstanding AS sh
        FROM read_parquet('{FEATURES}/sec_fundamentals_daily/*.parquet') q
        JOIN syms s USING (symbol) JOIN days d ON d.trade_date = CAST(q.trade_date AS TIMESTAMP)
        WHERE q.shares_outstanding IS NOT NULL"""
    ).fetchnumpy()
    con.close()
    shares = np.full(shape, np.nan, dtype=np.float64)
    shares[sh["tid"], sh["sid"]] = sh["sh"]
    del sh
    shares = pd.DataFrame(shares).ffill(limit=FFILL_LIMIT).to_numpy()
    sym_idx = {s: i for i, s in enumerate(symbols)}
    trading_days = [d.date() for d in dates]

    files = sorted(FTD_DIR.glob("cnsfails*.parquet"))
    per_file: list[dict] = []
    windows: list[tuple[int, dict[int, tuple[float, float, float]], set[int]]] = []
    tot = dict.fromkeys(
        (
            "rows",
            "matched_any_sip_symbol",
            "matched_universe",
            "price_ok",
            "no_price",
            "no_sip_close",
            "price_deviation",
            "ftdsh_valid",
            "ftdsh_drop_shares",
            "ftdsh_drop_ratio",
            "ftdsh_drop_cap",
            "ftdadv_valid",
            "ftdadv_drop_adv",
        ),
        0,
    )
    for f in files:
        m = re.match(r"cnsfails(\d{6})([ab])\.parquet", f.name)
        if not m:
            continue
        ym, half = m.groups()
        av = available_date(ym, half, trading_days)
        frame = pd.read_parquet(f)
        if frame.empty or av is None:
            continue
        last = frame["settlement_date"].max()
        rows = frame[frame["settlement_date"] == last]
        pt = prev_trading_index(dates, last)
        st = dict.fromkeys(tot, 0)
        st["rows"] = len(rows)
        values: dict[int, list[float]] = {}
        unknown: set[int] = set()
        for r in rows.itertuples(index=False):
            sym = str(r.symbol).strip().upper()
            if sym in all_syms:
                st["matched_any_sip_symbol"] += 1
            sid = sym_idx.get(sym)
            if sid is None or pt < 0:
                continue
            st["matched_universe"] += 1
            px_ftd = r.price
            c = float(close[pt, sid]) if np.isfinite(close[pt, sid]) else None
            if px_ftd is None or not np.isfinite(px_ftd):
                st["no_price"] += 1
                unknown.add(sid)
                continue
            if c is None:
                st["no_sip_close"] += 1
                unknown.add(sid)
                continue
            if abs(px_ftd / c - 1.0) >= PRICE_TOL:
                st["price_deviation"] += 1
                unknown.add(sid)
                continue
            st["price_ok"] += 1
            qty = float(r.quantity)
            sh_v = shares[pt, sid]
            a21 = adv21[pt, sid]
            ftdsh = np.nan
            if not np.isfinite(sh_v) or sh_v <= 0:
                st["ftdsh_drop_shares"] += 1
            elif qty / sh_v > MAX_FTD_OVER_SHARES:
                st["ftdsh_drop_ratio"] += 1
            elif not (MIN_CAP <= sh_v * c <= MAX_CAP):
                st["ftdsh_drop_cap"] += 1
            else:
                ftdsh = qty / sh_v
                st["ftdsh_valid"] += 1
            ftdadv = np.nan
            if np.isfinite(a21) and a21 > 0:
                ftdadv = qty * c / a21
                st["ftdadv_valid"] += 1
            else:
                st["ftdadv_drop_adv"] += 1
            acc = values.setdefault(sid, [0.0, 0.0, 0.0, 0.0])  # qty-sum aggregates per symbol
            acc[0] += 0.0 if np.isnan(ftdsh) else ftdsh
            acc[1] += 0.0 if np.isnan(ftdadv) else ftdadv
            acc[2] += 1.0 if not np.isnan(ftdsh) else 0.0
            acc[3] += 1.0 if not np.isnan(ftdadv) else 0.0
        per_sym: dict[int, tuple[float, float, float]] = {}
        for sid, (a, b, na, nb) in values.items():
            per_sym[sid] = (a if na else np.nan, b if nb else np.nan, 1.0)
        windows.append((int(dates.searchsorted(pd.Timestamp(av))), per_sym, unknown))
        for k in tot:
            tot[k] += st[k]
        per_file.append({"file": f.name, "last_settlement": str(last), "available": str(av), **st})
    # expand: window i holds from its availability index up to the next window's
    windows.sort(key=lambda w: w[0])
    out_frames = []
    for i, (t0, per_sym, unknown) in enumerate(windows):
        t1 = windows[i + 1][0] if i + 1 < len(windows) else len(dates)
        t1 = min(t1, t0 + MAX_HOLD_SESSIONS)
        if t0 >= t1:
            continue
        sh_col = np.zeros(len(symbols))
        adv_col = np.zeros(len(symbols))
        dum_col = np.zeros(len(symbols))
        for sid, (a, b, _) in per_sym.items():
            sh_col[sid], adv_col[sid], dum_col[sid] = a, b, 1.0
        for sid in unknown:
            if sid not in per_sym:
                sh_col[sid] = adv_col[sid] = dum_col[sid] = np.nan
        block = close[t0:t1]
        ti, si = np.nonzero(np.isfinite(block))
        out_frames.append(
            pd.DataFrame(
                {
                    "symbol": symbols[si],
                    "trade_date": dates[t0 + ti],
                    "ftdsh": sh_col[si],
                    "ftdadv": adv_col[si],
                    "ftd_dummy": dum_col[si],
                }
            )
        )
    out = pd.concat(out_frames, ignore_index=True)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out.to_parquet(OUT_DIR / "ftd.parquet", index=False)
    summary = {
        "files_used": len(per_file),
        "first_available": per_file[0]["available"] if per_file else None,
        "last_available": per_file[-1]["available"] if per_file else None,
        "totals_last_settlement_rows": tot,
        "rate_matched_any_sip_symbol": tot["matched_any_sip_symbol"] / max(tot["rows"], 1),
        "rate_matched_universe": tot["matched_universe"] / max(tot["rows"], 1),
        "rate_price_consistent_of_matched": tot["price_ok"] / max(tot["matched_universe"], 1),
        "dropped_share_of_matched_universe": 1 - tot["price_ok"] / max(tot["matched_universe"], 1),
        "ftdsh_valid_of_price_ok": tot["ftdsh_valid"] / max(tot["price_ok"], 1),
        "ftdadv_valid_of_price_ok": tot["ftdadv_valid"] / max(tot["price_ok"], 1),
        "output_rows": int(len(out)),
        "nonnull_ftdsh": int(out["ftdsh"].notna().sum()),
        "nonnull_ftdadv": int(out["ftdadv"].notna().sum()),
        "share_ftd_positive_rows": float((out["ftd_dummy"] > 0).mean()),
    }
    (OUT_DIR / "build_summary.json").write_text(json.dumps(summary, indent=2))
    (OUT_DIR / "per_file.json").write_text(json.dumps(per_file, indent=1))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
