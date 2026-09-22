"""T3 (plan-earnings-text-forward-test-2026-09-22 section 1 row T3 / section 4):
turn scored earnings text into a cross-sectional return test.

Rules, frozen in the plan before any score existed:

  entry   the first regular-session OPEN at or after `acceptance_utc + 60 min`
          (so an after-hours filing trades at the next open, and a filing
          accepted during the session waits for the following open);
  exit    the close of the entry session; +1 and +5 session closes also reported;
  buckets quintiles of `tone` inside each entry date, dates with fewer than
          `--min-events` scored filings are dropped;
  costs   10 and 20 bp per side, charged on both legs;
  base    the same quintile procedure run on two price-only signals -- the
          entry gap (entry open / previous close - 1) and relative dollar
          volume -- to answer whether the text adds anything a price screen
          would not have given for free;
  placebo `tone` reshuffled inside each entry date, 20 seeds.

This script makes no claim about the forward test. Any historical result here is
contaminated by whatever the scoring model already knew about these companies and
periods; the plan treats it as a magnitude reference and a kill test only.
"""

from __future__ import annotations

import argparse
import glob
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SCORES = ROOT / "data/features/earnings_text_scores"
DAILY_GLOB = str(ROOT / "data/sip/daily/*/shard-*.parquet")
OUT_DIR = ROOT / "reports/research/iterations/h20260922_01_earnings_text"
ET = "America/New_York"


def load_scores() -> pd.DataFrame:
    files = sorted(glob.glob(str(SCORES / "2*.parquet")))
    if not files:
        raise SystemExit("no scores yet")
    d = pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)
    d = d[(d.status == "ok") & d.acceptance_utc.notna() & d.ticker.notna()].copy()
    d["accept"] = pd.to_datetime(d.acceptance_utc, utc=True, format="mixed").dt.tz_convert(ET)
    d["ready"] = d["accept"] + pd.Timedelta(minutes=60)
    return d.drop_duplicates("accession")


def load_bars(tickers: list[str], start: str, end: str) -> pd.DataFrame:
    import duckdb

    con = duckdb.connect()
    con.execute("SET memory_limit='900MB'")
    con.execute("SET threads=2")
    in_list = ",".join(f"'{t}'" for t in sorted(set(tickers)))
    df = con.execute(
        f"""
        SELECT symbol, timestamp::DATE AS d, open, close, volume, trade_count
        FROM read_parquet('{DAILY_GLOB}')
        WHERE symbol IN ({in_list}) AND timestamp::DATE BETWEEN DATE '{start}' AND DATE '{end}'
        ORDER BY symbol, d
        """
    ).df()
    con.close()
    ghost = (df["volume"].fillna(0) <= 0) & (df["trade_count"].fillna(0) <= 0)
    return df.loc[~ghost].reset_index(drop=True)


def attach_trades(scores: pd.DataFrame, bars: pd.DataFrame) -> pd.DataFrame:
    bars = bars.sort_values(["symbol", "d"]).reset_index(drop=True)
    bars["d"] = pd.to_datetime(bars["d"])
    bars["i"] = bars.groupby("symbol").cumcount()
    bars["prev_close"] = bars.groupby("symbol")["close"].shift(1)
    dv = bars["close"] * bars["volume"]
    bars["adv20"] = dv.groupby(bars["symbol"]).transform(lambda x: x.rolling(20).mean())

    sessions = np.array(sorted(bars["d"].unique()), dtype="datetime64[D]")
    ready = scores["ready"].dt.tz_localize(None)
    ready_day = ready.dt.normalize().to_numpy("datetime64[D]")
    before_open = (ready.dt.hour * 60 + ready.dt.minute) <= 9 * 60 + 30
    target = np.where(before_open.to_numpy(), ready_day, ready_day + np.timedelta64(1, "D"))
    idx = np.searchsorted(sessions, target, side="left")
    ok = idx < len(sessions)
    out = scores.loc[ok, ["accession", "ticker", "tone", "guidance"]].copy()
    out["entry_date"] = pd.to_datetime(sessions[idx[ok]])

    entry = out.merge(
        bars[["symbol", "d", "i", "open", "prev_close", "adv20"]],
        left_on=["ticker", "entry_date"],
        right_on=["symbol", "d"],
        how="inner",
    ).drop(columns=["symbol", "d"])
    closes = bars[["symbol", "i", "close"]]
    for h in (0, 1, 5):
        entry = entry.merge(
            closes.assign(i=closes["i"] - h).rename(columns={"close": f"c{h}"}),
            left_on=["ticker", "i"],
            right_on=["symbol", "i"],
            how="left",
        ).drop(columns=["symbol"])
        entry[f"ret_d{h}"] = entry[f"c{h}"] / entry["open"] - 1.0
    entry = entry[entry["open"] > 0].copy()
    entry["gap"] = entry["open"] / entry["prev_close"] - 1.0
    entry["relvol"] = entry["adv20"] / entry.groupby("entry_date")["adv20"].transform("median")
    return entry


def quintile_stats(t: pd.DataFrame, signal: str, ret_col: str, cost_bps: float) -> dict:
    net = t[ret_col] - 2.0 * cost_bps / 10_000.0
    d = t.assign(_net=net).dropna(subset=[signal, "_net"])
    res = {"signal": signal, "ret": ret_col, "cost_bps": cost_bps, "events": int(len(d))}
    per_day = []
    for day, g in d.groupby("entry_date"):
        if len(g) < 10 or g[signal].nunique() < 5:
            continue
        q = pd.qcut(g[signal].rank(method="first"), 5, labels=False)
        top = g.loc[q == 4, "_net"].mean()
        bot = g.loc[q == 0, "_net"].mean()
        per_day.append({"day": day, "q5": top, "q1": bot, "ls": top - bot, "n": len(g)})
    if not per_day:
        return {**res, "days": 0}
    p = pd.DataFrame(per_day)
    for name in ("ls", "q5"):
        x = p[name].dropna()
        res[f"{name}_bp"] = float(x.mean() * 1e4)
        res[f"{name}_t"] = (
            float(x.mean() / x.std(ddof=1) * np.sqrt(len(x))) if x.std(ddof=1) > 0 else np.nan
        )
        res[f"{name}_hit"] = float((x > 0).mean())
    res["days"] = int(len(p))
    res["events_used"] = int(p["n"].sum())
    return res


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-events", type=int, default=10)
    ap.add_argument("--placebo-seeds", type=int, default=20)
    args = ap.parse_args(argv)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    s = load_scores()
    lo = (s["ready"].min() - pd.Timedelta(days=15)).date().isoformat()
    hi = (s["ready"].max() + pd.Timedelta(days=20)).date().isoformat()
    print(f"{len(s)} scored events, {s.ticker.nunique()} tickers, {lo} .. {hi}", flush=True)
    bars = load_bars(s.ticker.unique().tolist(), lo, hi)
    print(f"{len(bars)} bars for {bars.symbol.nunique()} symbols", flush=True)
    t = attach_trades(s, bars)
    t.to_parquet(OUT_DIR / "events.parquet")
    print(f"{len(t)} tradable events", flush=True)

    out = []
    for ret_col in ("ret_d0", "ret_d1", "ret_d5"):
        for cost in (10.0, 20.0):
            for sig in ("tone", "gap", "relvol"):
                out.append(quintile_stats(t, sig, ret_col, cost))
    real = pd.DataFrame(out)

    # placebo: tone reshuffled inside each entry date
    rows = []
    for seed in range(args.placebo_seeds):
        rng = np.random.default_rng(20260922 + seed)
        tp = t.copy()
        tp["tone"] = tp.groupby("entry_date")["tone"].transform(
            lambda x, _g=rng: _g.permutation(x.to_numpy())
        )
        r = quintile_stats(tp, "tone", "ret_d0", 10.0)
        rows.append(
            {"seed": seed, "ls_bp": r.get("ls_bp", np.nan), "q5_bp": r.get("q5_bp", np.nan)}
        )
    pl = pd.DataFrame(rows)
    base = real[(real.signal == "tone") & (real.ret == "ret_d0") & (real.cost_bps == 10.0)].iloc[0]
    beat_ls = float((pl.ls_bp > base.get("ls_bp", np.nan)).mean())
    beat_q5 = float((pl.q5_bp > base.get("q5_bp", np.nan)).mean())

    real.to_parquet(OUT_DIR / "quintiles.parquet")
    pl.to_parquet(OUT_DIR / "placebo.parquet")
    summary = {
        "iter_id": "h20260922_01_earnings_text",
        "card_id": "H-20260922-01",
        "scored_events": int(len(s)),
        "tradable_events": int(len(t)),
        "date_span": [str(t.entry_date.min().date()), str(t.entry_date.max().date())],
        "placebo_beat_ls": beat_ls,
        "placebo_beat_q5": beat_q5,
        "placebo_ls_bp_median": float(pl.ls_bp.median()),
        "results": real.to_dict("records"),
        "note": "historical segment only; the scoring model's knowledge may overlap this "
        "period, so this is a magnitude reference and a kill test, not evidence of "
        "tradable alpha. The verdict comes from the forward shadow that starts with "
        "the Q3 season on 2026-10-13.",
    }
    (OUT_DIR / "summary.json").write_text(json.dumps(summary, indent=2, default=float) + "\n")
    cols = [
        "signal",
        "ret",
        "cost_bps",
        "days",
        "events_used",
        "ls_bp",
        "ls_t",
        "ls_hit",
        "q5_bp",
        "q5_t",
    ]
    print(real[[c for c in cols if c in real.columns]].round(2).to_string(index=False))
    print(
        f"\nplacebo beat: long-short {beat_ls:.0%}, long-only {beat_q5:.0%}, "
        f"placebo median long-short {pl.ls_bp.median():.1f} bp"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
