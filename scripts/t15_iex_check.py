"""T-20261006-15: IEX versus SIP signal agreement (evaluation standard 5b item 8).

Fetches Alpaca free-plan IEX 1-minute bars (raw prices) for the last ~60 sessions and recomputes the
group A noise-band positions and the group B predictors on both feeds. Thresholds written in
amendment-2026-10-06-main-grid.md before this ran: direction agreement >= 90 percent and rank
correlation >= 0.8. Credentials are loaded by dotenv inside this process and never printed.
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
load_dotenv(ROOT / ".env")
import t15_engine as E  # noqa: E402

from open_composer.adapters.data.alpaca import fetch_alpaca_bars  # noqa: E402

OUT = ROOT / "reports/research/iterations/t20261006_15_intraday_rules/iex_check.json"
NY = "America/New_York"
START = "2026-07-06"


def iex_frame(sym: str) -> pd.DataFrame:
    root = Path("/tmp/t15_alpaca_cache")
    root.mkdir(exist_ok=True)
    df = fetch_alpaca_bars(
        root,
        sym,
        "1m",
        datetime(2026, 6, 15, tzinfo=UTC),
        datetime.now(UTC) - timedelta(minutes=20),
        "iex",
        use_cache=False,
        adjustment="raw",
    )
    d = pd.DataFrame(df)
    ts = pd.to_datetime(d["timestamp"], utc=True).dt.tz_convert(NY)
    d = d.assign(date=ts.dt.normalize().dt.tz_localize(None), minute=ts.dt.hour * 60 + ts.dt.minute)
    d = (
        d[(d.minute >= 570) & (d.minute <= 959)]
        .drop(columns=["timestamp"])
        .drop_duplicates(["date", "minute"])
    )
    d = d.sort_values(["date", "minute"]).reset_index(drop=True)
    tp = (d.high + d.low + d.close) / 3.0
    pv = (tp * d.volume).groupby(d.date).cumsum()
    vv = d.volume.groupby(d.date).cumsum()
    d["vwap"] = np.where(vv > 0, pv / vv, d.close)
    return d


def run(symbols):
    out = {"start": START, "symbols": {}}
    for sym in symbols:
        iex = iex_frame(sym)
        pi = E.Panel(sym, frame=iex)
        ps = E.Panel(sym, start="2026-06-15")
        common = pi.dates.intersection(ps.dates)
        common = common[common >= pd.Timestamp(START)]
        ii = pi.dates.get_indexer(common)
        si = ps.dates.get_indexer(common)
        rec = {
            "sessions_compared": int(len(common)),
            "iex_minutes_per_session_mean": float(
                iex.groupby("date").size().reindex(common).mean()
            ),
        }
        for k in (15, 30):
            sg_i = E.noise_sigma(pi, 14)
            sg_s = E.noise_sigma(ps, 14)
            for M in (1.0, 1.5):
                Pi = E.a_position_paths(pi, sg_i, k, [M], ["both"])[(M, "both")][ii]
                Ps = E.a_position_paths(ps, sg_s, k, [M], ["both"])[(M, "both")][si]
                agree = float(np.mean(Pi == Ps))
                flat_agree = float(np.mean((Pi == 0) == (Ps == 0)))
                active = (Pi != 0) | (Ps != 0)
                act_agree = float(np.mean(Pi[active] == Ps[active])) if active.any() else None
                # band width rank correlation at the check slots
                ms = E.check_slots(k)
                wi = (sg_i[ii][:, ms]).ravel()
                ws = (sg_s[si][:, ms]).ravel()
                ok = np.isfinite(wi) & np.isfinite(ws)
                rho = (
                    float(pd.Series(wi[ok]).corr(pd.Series(ws[ok]), method="spearman"))
                    if ok.sum() > 10
                    else None
                )
                rec[f"A_k{k}_M{M}"] = {
                    "direction_agreement_all_checks": agree,
                    "flat_vs_active_agreement": flat_agree,
                    "agreement_when_either_active": act_agree,
                    "sigma_spearman": rho,
                }
        fi, fs = E.b_features(pi), E.b_features(ps)
        for name in ("r1_intraday", "r1_overnight", "r12"):
            a, b = fi[name][ii], fs[name][si]
            ok = np.isfinite(a) & np.isfinite(b)
            rec[f"B_{name}"] = {
                "sign_agreement": float(np.mean(np.sign(a[ok]) == np.sign(b[ok]))),
                "spearman": float(pd.Series(a[ok]).corr(pd.Series(b[ok]), method="spearman")),
                "n": int(ok.sum()),
            }
        out["symbols"][sym] = rec
        print(sym, json.dumps(rec)[:600], flush=True)
    thr = {"direction_agreement_min": 0.90, "rank_corr_min": 0.80}
    out["thresholds"] = thr
    OUT.write_text(json.dumps(out, indent=1) + "\n")


if __name__ == "__main__":
    run(sys.argv[1:] or ["SPY", "QQQ", "IWM"])
