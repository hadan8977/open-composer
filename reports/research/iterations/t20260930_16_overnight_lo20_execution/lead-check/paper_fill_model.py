"""Interactive lead check 2026-09-30 (Opus): where does Alpaca Paper fill queued DAY market orders?

Reads the account's own broker receipts (reports/paper/broker_receipts/orders), keeps market/day
orders submitted before 09:30 ET of the fill day, and compares each filled_avg_price with the SIP
NBBO in force at filled_at (last valid quote in [filled_at - 5 s, filled_at]) and with the raw daily
open of that session.  Credentials stay in the DataSession headers; nothing is printed or stored.
"""

import glob
import json

import numpy as np
import pandas as pd

from scripts import run_t20260930_11_gap_fade_auction as c1
from scripts import run_t20260930_15_quote_check as t15

rows = {}
for f in glob.glob("reports/paper/broker_receipts/orders/*/*.json"):
    try:
        d = json.load(open(f))
    except Exception:
        continue

    def walk(o):
        if isinstance(o, dict):
            if o.get("filled_at") and o.get("symbol") and o.get("time_in_force"):
                rows[o.get("id") or (o["symbol"], o["filled_at"])] = (
                    o["filled_at"], o.get("submitted_at"), o["symbol"], o["side"],
                    o.get("type") or o.get("order_type"), o["time_in_force"],
                    float(o.get("filled_avg_price") or np.nan),
                )
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    walk(d)
df = pd.DataFrame(list(rows.values()), columns=["filled_at", "submitted_at", "symbol", "side", "type", "tif", "px"])
df["filled_at"] = pd.to_datetime(df["filled_at"], utc=True, format="ISO8601")
df["submitted_at"] = pd.to_datetime(df["submitted_at"], utc=True, format="ISO8601")
fe = df["filled_at"].dt.tz_convert("America/New_York")
se = df["submitted_at"].dt.tz_convert("America/New_York")
queued = (se.dt.date < fe.dt.date) | ((se.dt.hour * 60 + se.dt.minute) < 570)
df = df[queued & (df["type"] == "market") & (df["tif"] == "day")].copy()
df["day"] = fe[df.index].dt.strftime("%Y-%m-%d")
df["delay_s"] = (fe[df.index] - fe[df.index].dt.normalize() - pd.Timedelta(hours=9, minutes=30)).dt.total_seconds()

s = c1.DataSession()
out = []
for r in df.itertuples():
    end_ns = int(r.filled_at.value) + 1_000
    start_ns = end_ns - 5_000_000_000
    params = {"symbols": r.symbol, "start": t15.rfc3339(start_ns), "end": t15.rfc3339(end_ns),
              "feed": "sip", "limit": 10000}
    state = {}
    token = None
    for _ in range(20):
        if token:
            params["page_token"] = token
        data = s.get_url(t15.QUOTES_URL, params)
        t15.update_last_valid(state, data.get("quotes") or {}, start_ns, end_ns)
        token = data.get("next_page_token")
        if not token:
            break
    bid, ask, _ = state.get(r.symbol, (np.nan, np.nan, -1))
    out.append((bid, ask))
df["bid"] = [x[0] for x in out]
df["ask"] = [x[1] for x in out]

opens = {}
for day, g in df.groupby("day"):
    syms = sorted(set(g["symbol"]))
    params = {"symbols": ",".join(syms), "timeframe": "1Day", "start": t15.rfc3339(t15.et_to_utc_ns(day, 0, 0)),
              "end": t15.rfc3339(t15.et_to_utc_ns(day, 23, 59)), "adjustment": "raw", "feed": "sip", "limit": 10000}
    data = s.get_url(t15.BARS_URL, params)
    for sym, bars in (data.get("bars") or {}).items():
        for b in bars:
            opens[(day, sym)] = float(b["o"])
df["open_raw"] = [opens.get((a, b), np.nan) for a, b in zip(df["day"], df["symbol"])]

sign = np.where(df["side"] == "buy", 1.0, -1.0)
mid = (df["bid"] + df["ask"]) / 2
df["pos"] = (df["px"] - df["bid"]) / (df["ask"] - df["bid"])
df["cost_vs_mid_bp"] = sign * (df["px"] / mid - 1) * 1e4
df["half_spread_bp"] = (df["ask"] - df["bid"]) / 2 / mid * 1e4
df["cost_vs_open_bp"] = sign * (df["px"] / df["open_raw"] - 1) * 1e4
df["etf"] = df["symbol"].isin(["XLK", "SHY", "SMH", "UPRO", "SPY", "QQQ", "TQQQ", "XLV", "XLB", "XLE", "XLF", "XLU", "XLY", "XLP", "XLI", "XLC", "XLRE", "TLT", "IEF", "GLD"])
print(f"queued market/day fills {len(df)}, days {df['day'].nunique()}, quote found {int(np.isfinite(df['bid']).sum())}, open found {int(np.isfinite(df['open_raw']).sum())}, calls {s.calls}, 429s {s.n429}")
q = [0.05, 0.25, 0.5, 0.75, 0.95]
for (side, etf), g in df.groupby(["side", "etf"]):
    print(f"== side={side} etf={etf} n={len(g)}")
    for c in ["pos", "cost_vs_mid_bp", "half_spread_bp", "cost_vs_open_bp", "delay_s"]:
        x = g[c].replace([np.inf, -np.inf], np.nan).dropna()
        print(f"  {c:16s} mean {x.mean():8.2f}  q05/25/50/75/95 " + " ".join(f"{v:8.2f}" for v in x.quantile(q)))
    print(f"  share at quote side (buy pos>=0.99 / sell pos<=0.01): {float(((g['pos']>=0.99) if side=='buy' else (g['pos']<=0.01)).mean()):.2f}")
df.drop(columns=["filled_at", "submitted_at"]).to_csv(
    "reports/research/iterations/t20260930_16_overnight_lo20_execution/lead-check/paper-fill-model.csv", index=False, float_format="%.6g")
