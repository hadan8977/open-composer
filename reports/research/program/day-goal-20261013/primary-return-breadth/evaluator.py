# ruff: noqa: E501
"""Deterministic nonpromotable component reference, not a broker execution engine."""

import bisect
import hashlib
import json
import math
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from open_composer.market_sessions import next_us_equity_session, us_equity_session_close
from open_composer.research.campaign_statistics import deflated_sharpe_probability
from open_composer.research.features.price_hygiene import sanitize_price_matrices

P = Path(__file__).parent
SYMS = ["SPY", "SSO", "BIL"]


def bind(p):
    p = Path(p)
    return {
        "path": str(p),
        "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
        "bytes": p.stat().st_size,
    }


def save(p, x):
    Path(p).write_text(json.dumps(x, indent=2, default=str, allow_nan=False) + "\n")


def load_bars(kind):
    rows = []
    for p in sorted((P / "inputs").glob("bars_" + kind + "-*.json")):
        for s, bs in json.loads(p.read_text())["bars"].items():
            rows.extend(dict(symbol=s, **b) for b in bs)
    df = pd.DataFrame(rows)
    df["date"] = (
        pd.to_datetime(df.t, utc=True)
        .dt.tz_convert("America/New_York")
        .dt.tz_localize(None)
        .dt.normalize()
    )
    assert not df.duplicated(["symbol", "date"]).any()
    return df


def load_actions():
    rows = []
    for p in sorted((P / "inputs").glob("actions-*.json")):
        data = json.loads(p.read_text())
        for typ, seq in data["corporate_actions"].items():
            rows.extend(dict(action_group=typ, **a) for a in seq)
    return rows


def normalized_actions(rows):
    out = []
    for a in rows:
        typ = a["action_group"]
        s = a.get("symbol")
        if s not in SYMS:
            continue
        if typ not in {"cash_dividends", "forward_splits", "reverse_splits"}:
            raise ValueError("Unsupported action " + typ)
        ex = a["ex_date"]
        if ex < "2015-01-01" or ex > "2026-10-12":
            continue
        r = {"id": a["id"], "symbol": s, "ex_date": ex, "type": typ}
        if typ == "cash_dividends":
            assert a.get("payable_date") and a["payable_date"] >= ex
            rate = a.get("cash_rate", a.get("rate"))
            assert rate is not None and rate > 0 and a.get("foreign") is False
            assert (
                a.get("currency", "USD") == "USD"
            )  # fixedUS-listedUSDfunds; absence explicitly retained in acceptance
            assert (
                not a.get("sub_type")
                and not a.get("due_bill_on_date")
                and not a.get("due_bill_off_date")
            )
            r.update(
                amount=float(rate),
                payable_date=a["payable_date"],
                record_date=a.get("record_date"),
                currency_field=a.get("currency"),
                rate_field="cash_rate" if "cash_rate" in a else "rate",
            )
        else:
            r.update(ratio=float(a["new_rate"]) / float(a["old_rate"]))
            assert r["ratio"] > 0
        out.append(r)
    assert len({a["id"] for a in out}) == len(out)
    return sorted(out, key=lambda a: (a["ex_date"], a["type"], a["id"]))


def matrices(raw, adj, actions):
    index = pd.DatetimeIndex(sorted(set(raw.date)))
    close = raw.pivot(index="date", columns="symbol", values="c").reindex(index=index, columns=SYMS)
    opening = raw.pivot(index="date", columns="symbol", values="o").reindex_like(close)
    ac = adj.pivot(index="date", columns="symbol", values="c").reindex_like(close)
    known = {
        s: [
            pd.Timestamp(a["ex_date"])
            for a in actions
            if a["symbol"] == s and a["type"] != "cash_dividends"
        ]
        for s in SYMS
    }
    close, opening, hygiene = sanitize_price_matrices(
        close,
        opening,
        known_corporate_actions=known,
        corporate_action_feed="actual_bound_Alpaca_actions",
    )
    assert opening is not None
    return close, opening, ac, hygiene


def make_signals(adjclose, events):
    # Weekday grid keeps holidays at zero; missing real-session observations never filled.
    r = adjclose.pct_change(fill_method=None)
    assert r.iloc[1:].notna().all().all()
    grid = pd.bdate_range(adjclose.index[0], adjclose.index[-1])
    excess = (np.log1p(r.SPY) - np.log1p(r.BIL)).reindex(grid)
    holidays = ~grid.isin(adjclose.index)
    excess.loc[holidays] = 0.0
    feats = pd.DataFrame({f"x{n}": excess.rolling(n, min_periods=n).sum() for n in [5, 21, 63]})
    qs = {n: feats[f"x{n}"].expanding(min_periods=252).quantile(0.2).shift(1) for n in [5, 21, 63]}
    q = {n: (feats[f"x{n}"] <= qs[n]) & qs[n].notna() for n in qs}
    feats["D1"] = q[5]
    feats["D2"] = q[5] & q[21]
    feats["D3"] = q[5] & q[21] & q[63]
    dates = adjclose.index
    ordered = sorted(events, key=lambda e: e["date"])
    anchors = [pd.Timestamp(e["date"]) for e in ordered]
    activations = []
    for e in ordered:
        if e.get("replay_activation_at"):
            activations.append(pd.Timestamp(e["replay_activation_at"]))
        else:
            # Synthetic test events exercise the same declared conservative rule.
            activate = next_us_equity_session(pd.Timestamp(e["date"]).date())
            activations.append(
                pd.Timestamp(
                    datetime.combine(
                        activate,
                        us_equity_session_close(activate),
                        tzinfo=ZoneInfo("America/New_York"),
                    ).astimezone(UTC)
                )
            )
    phase = []
    placebo = []
    anc = []
    for i, t in enumerate(dates):
        closing = us_equity_session_close(t.date())
        assert closing is not None
        cutoff = pd.Timestamp(
            datetime.combine(t.date(), closing, tzinfo=ZoneInfo("America/New_York")).astimezone(UTC)
        )
        j = bisect.bisect_right(activations, cutoff) - 1
        anchor = anchors[j] if j >= 0 else None
        target = dates[i + 1] if i + 1 < len(dates) else pd.NaT
        elapsed = (
            int(np.busday_count(anchor.date(), target.date()))
            if anchor is not None and pd.notna(target)
            else -999
        )
        shifted = elapsed - 5
        phase.append(elapsed)
        placebo.append(shifted)
        anc.append(anchor)
    f = feats.reindex(dates)
    f["next_phase"] = phase
    f["placebo_phase"] = placebo
    f["anchor"] = anc
    f["late_even"] = f.next_phase.isin(
        list(range(9, 14)) + list(range(19, 24)) + list(range(29, 34))
    )
    f["shift_even"] = f.placebo_phase.isin(
        list(range(9, 14)) + list(range(19, 24)) + list(range(29, 34))
    )
    return f


def cash_due_date(day, eligible, dividend=False):
    d = pd.Timestamp(day)
    count = 1 if dividend else (4 if d.year <= 2017 else 3 if d < pd.Timestamp("2024-05-28") else 2)
    j = bisect.bisect_right(eligible, d)
    assert j + count - 1 < len(eligible), "Cash proxy calendar coverage exhausted"
    return eligible[j + count - 1]


def simulate(
    close, opening, target, actions, capital=20000, cost=0.002, settlement=True, cash_days=None
):
    dates = pd.DatetimeIndex(close.index)
    assert len(dates) == len(opening) == len(target)
    cash = float(capital)
    shares = 0
    pending = []
    receivables = []
    rows = []
    orders = []
    events = []
    entry_count = 0
    reject_count = 0
    total_cost = 0.0
    dividends = 0.0
    frozen = {"side": "none", "qty": 0, "limit": None}
    eligible = [
        pd.Timestamp(x)
        for x in (
            cash_days
            if cash_days is not None
            else json.loads((P / "cash-calendar.json").read_text())["eligible_dates"]
        )
    ]
    for i, d in enumerate(dates):
        ds = d.date().isoformat()
        # Credits due today are not used to resize yesterday's frozen order.
        credits = [x for x in pending if x["due_date"] <= d]
        cash += sum(x["amount"] for x in credits)
        pending = [x for x in pending if x["due_date"] > d]
        payments = [x for x in receivables if x["due_date"] <= d]
        cash += sum(x["amount"] for x in payments)
        receivables = [x for x in receivables if x["due_date"] > d]
        today = [a for a in actions if a["ex_date"] == ds]
        for a in today:
            if a["type"] == "cash_dividends":
                continue
            ratio = a["ratio"]
            new_shares = shares * ratio
            new_qty = frozen["qty"] * ratio
            assert (
                abs(new_shares - round(new_shares)) < 1e-8 and abs(new_qty - round(new_qty)) < 1e-8
            ), "Fractional split/CIL not accepted"
            shares = int(round(new_shares))
            frozen["qty"] = int(round(new_qty))
            if frozen["limit"] is not None:
                frozen["limit"] /= ratio
            events.append(
                {"date": ds, "event": "split", "id": a["id"], "ratio": ratio, "new_shares": shares}
            )
        for a in today:
            if a["type"] != "cash_dividends":
                continue
            amount = shares * a["amount"]
            due = cash_due_date(a["payable_date"], eligible, dividend=True)
            receivables.append({"due_date": due, "amount": amount, "id": a["id"]})
            dividends += amount
            events.append(
                {
                    "date": ds,
                    "event": "dividend_entitlement",
                    "id": a["id"],
                    "owned_before_open": shares,
                    "amount": amount,
                    "payable_date": a["payable_date"],
                    "proxy_cash_available_date": str(due.date()),
                }
            )
        price = float(opening.iloc[i])
        if frozen["side"] != "none":
            q = frozen["qty"]
            side = frozen["side"]
            valid = math.isfinite(price) and price > 0
            allin = q * price * (1 + cost)
            accepted = (
                valid
                and q > 0
                and (side == "sell" or (price <= frozen["limit"] and allin <= cash + 1e-8))
            )
            row = {
                "date": ds,
                "signal_date": str(dates[i - 1].date()) if i else None,
                "side": side,
                "quantity": q,
                "reference_open": price if valid else None,
                "limit": frozen["limit"],
                "accepted": accepted,
                "cash_before": cash,
                "fill_kind": "daily_trade_reference_model",
            }
            if accepted:
                fee = q * price * cost
                total_cost += fee
                if side == "buy":
                    cash -= allin
                    shares += q
                    entry_count += 1
                else:
                    assert q == shares
                    shares -= q
                    if settlement:
                        pending.append(
                            {"due_date": cash_due_date(d, eligible), "amount": q * price - fee}
                        )
                    else:
                        cash += q * price - fee
                row["cost"] = fee
            else:
                reject_count += 1
                row["reason"] = "missing_reference_or_frozen_guard_or_cash"
            row["cash_after"] = cash
            orders.append(row)
        mark = float(close.iloc[i])
        assert shares == 0 or (math.isfinite(mark) and mark > 0), "Missing held close NAV N/A"
        unsettled = sum(x["amount"] for x in pending)
        recv = sum(x["amount"] for x in receivables)
        nav = cash + unsettled + recv + shares * (mark if math.isfinite(mark) else 0)
        assert cash >= -1e-7 and shares >= 0 and nav > 0
        rows.append(
            {
                "date": d,
                "nav": nav,
                "shares": shares,
                "proxy_available_cash": cash,
                "unavailable_sales_credit": unsettled,
                "dividend_receivable": recv,
                "position_value": shares * (mark if math.isfinite(mark) else 0),
                "target_known_at_close": bool(target.iloc[i]),
            }
        )
        frozen = {"side": "none", "qty": 0, "limit": None}
        if bool(target.iloc[i]) and shares == 0:
            assert math.isfinite(mark) and mark > 0, "Missing formation close"
            limit = mark * 1.05
            q = int(math.floor((cash + 1e-10) / (limit * (1 + cost))))
            if q > 0:
                frozen = {"side": "buy", "qty": q, "limit": limit}
            else:
                events.append(
                    {"date": ds, "event": "formation_zero_lot", "proxy_cash": cash, "target": 1}
                )
        elif not bool(target.iloc[i]) and shares > 0:
            frozen = {"side": "sell", "qty": shares, "limit": None}
    frame = pd.DataFrame(rows).set_index("date")
    return (
        frame,
        orders,
        events,
        {
            "entries": entry_count,
            "rejects": reject_count,
            "side_cost_dollars": total_cost,
            "dividend_entitlements_dollars": dividends,
            "initial_capital": capital,
            "side_cost_bps": cost * 10000,
            "unavailable_sales_terminal": sum(x["amount"] for x in pending),
            "unpaid_dividend_terminal": sum(x["amount"] for x in receivables),
            "cash_clock": "unverified_conservative_proxy"
            if settlement
            else "unqualified_immediate_sale_credit_diagnostic",
        },
    )


def lagged_wealth_excess(market, rf, horizon):
    return (
        (1 + market).rolling(horizon).apply(np.prod, raw=True)
        - (1 + rf).rolling(horizon).apply(np.prod, raw=True)
    ).shift(1)


def hac(x, lag=5):
    x = np.asarray(x, dtype=float)
    n = len(x)
    u = x - x.mean()
    var = float(np.dot(u, u) / n)
    for k in range(1, min(lag, n - 1) + 1):
        var += 2 * (1 - k / (lag + 1)) * float(np.dot(u[k:], u[:-k]) / n)
    se = math.sqrt(max(0.0, var) / n)
    return {
        "mean_daily_bp": float(x.mean() * 10000),
        "HAC_se_bp": se * 10000,
        "t": float(x.mean() / se) if se > 0 else None,
        "MDE80_daily_bp": 2.8016 * se * 10000,
        "n": n,
    }


def performance(nav, bil=None):
    r = nav.pct_change(fill_method=None).iloc[1:]
    assert r.notna().all() and np.isfinite(r).all()
    excess = r if bil is None else r - bil.reindex(r.index)
    assert excess.notna().all()
    elapsed = (nav.index[-1] - nav.index[0]).days / 365.25
    dd = nav / nav.cummax() - 1
    underwater = 0
    longest = 0
    for v in dd:
        underwater = underwater + 1 if v < -1e-10 else 0
        longest = max(longest, underwater)
    trough = dd.idxmin()
    peak = nav.loc[:trough].idxmax()
    peak_value = float(nav.loc[peak])
    later = nav.loc[trough:]
    recovered = later[later >= peak_value - 1e-8]
    recovery = {
        "peak_date": str(peak.date()),
        "trough_date": str(trough.date()),
        "recovery_date": str(recovered.index[0].date()) if len(recovered) else None,
        "sessions_trough_to_recovery": int(
            nav.index.get_loc(recovered.index[0]) - nav.index.get_loc(trough)
        )
        if len(recovered)
        else None,
    }
    std = excess.std(ddof=1)
    try:
        dsr = deflated_sharpe_probability(excess.to_numpy(), trial_count=25, hac_lag=5)
    except ValueError:
        dsr = None
    return {
        "first_close": str(nav.index[0].date()),
        "last_close": str(nav.index[-1].date()),
        "sessions": len(nav),
        "initial_NAV": float(nav.iloc[0]),
        "final_NAV": float(nav.iloc[-1]),
        "dollar_gain": float(nav.iloc[-1] - nav.iloc[0]),
        "total_return": float(nav.iloc[-1] / nav.iloc[0] - 1),
        "CAGR": float((nav.iloc[-1] / nav.iloc[0]) ** (1 / elapsed) - 1) if elapsed > 0 else None,
        "annual_vol": float(r.std(ddof=1) * np.sqrt(252)),
        "Sharpe_ex_BIL": float(excess.mean() / std * np.sqrt(252)) if std > 0 else None,
        "max_drawdown": float(dd.min()),
        "longest_underwater_sessions": longest,
        "max_drawdown_recovery": recovery,
        "underwater_terminal_sessions": underwater,
        "worst_compounded_windows": {
            str(k): float(((1 + r).rolling(k).apply(np.prod, raw=True) - 1).min())
            for k in [5, 21, 63]
            if len(r) >= k
        },
        "DSR_probability_currentstudy_trial25_HAC5": dsr,
        "DSR_assumption": "Native campaign_statistics expected-max benchmark;25 fixedprimary/control/benchmarkstreams;accounting/source-description views separate;priorsealedbranch familywideDSRnotcertified, conservative HAC effectiveT; descriptive seen-only.",
    }


def paired_bootstrap(diffs, draws=2000):
    x = diffs.to_numpy()
    assert np.isfinite(x).all()
    n, m = x.shape
    rng = np.random.default_rng(20261013)
    out = []
    center = x - x.mean(axis=0)
    ses = np.array([hac(x[:, j])["HAC_se_bp"] / 10000 for j in range(m)])
    maxt = []
    for _b in range(draws):
        starts = rng.integers(0, n, size=math.ceil(n / 20))
        ids = ((starts[:, None] + np.arange(20)) % n).ravel()[:n]
        sample = x[ids].mean(axis=0)
        out.append(sample)
        maxt.append(
            float(np.max(np.abs(center[ids].mean(axis=0) / np.where(ses > 0, ses, np.inf))))
        )
    a = np.asarray(out)
    critical = float(np.quantile(maxt, 0.95))
    result = {}
    for j, c in enumerate(diffs):
        h = hac(x[:, j])
        h.update(
            blockbootstrap95_mean_bp=(np.quantile(a[:, j], [0.025, 0.975]) * 10000).tolist(),
            family_maxT95_mean_bp=[
                float((x[:, j].mean() - critical * ses[j]) * 10000),
                float((x[:, j].mean() + critical * ses[j]) * 10000),
            ],
        )
        result[c] = h
    return {
        "method": "20session circular calendarblock bootstrap;all6paired differences jointmaxT;seed20261013;2000draws",
        "maxT_critical": critical,
        "comparisons": result,
    }
