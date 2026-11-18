# ruff: noqa: E501 -- Exact retained scientific formulas and disclosure literals.
"""Incremental raw economic units, original monthly features and strictly mature labels."""

from collections import defaultdict
from datetime import date

import numpy as np
import pandas as pd
from receiver_common import (
    SHARE,
    SYMBOLS,
    UNITS,
    absolute_fact_time,
    calendar,
    clock,
    legacy,
    module,
    month_dates,
)

from open_composer.market_sessions import NEW_YORK, next_us_equity_session, us_equity_session_dates
from open_composer.research.features.price_hygiene import sanitize_price_matrices


def merge_actions(old, objects, prefix_end):
    ids = {r["id"]: (kind, r) for kind, rows in old.items() for r in rows}
    for obj in objects:
        assert isinstance(obj.get("corporate_actions"), dict), "Missing action batch"
        for kind, rows in obj["corporate_actions"].items():
            for r in rows:
                symbol = r.get("symbol") or r.get("source_symbol") or r.get("acquiree_symbol")
                if symbol not in UNITS:
                    assert r.get("acquirer_symbol") in UNITS, "Unexpected action identity"
                    continue  # Acquirer-only merger is not an entitlement to existing common holders.
                if r["id"] in ids:
                    prior_kind, prior = ids[r["id"]]
                    assert kind == prior_kind and {
                        k: v for k, v in r.items() if k != "process_date"
                    } == {k: v for k, v in prior.items() if k != "process_date"}, (
                        "Changed accepted action terms"
                    )
                    continue
                day = r.get("ex_date") or r.get("effective_date")
                assert day and day > prefix_end, (
                    "New retrospective/missing-date action requires affected reception"
                )
                ids[r["id"]] = (kind, r)
    result = defaultdict(list)
    for kind, r in ids.values():
        result[kind].append(r)
    return dict(result)


def one_return(previous, current, symbol, day, raw, indices, actions):
    """Exact accepted close-reinvested exdate economic-unit bridge, not cashbook."""
    if not np.isfinite(previous):
        return np.nan, False
    ratio, cash, spin = 1.0, 0.0, 0.0
    trigger = False
    for kind, rows in actions.items():
        for a in rows:
            target = a.get("symbol") or a.get("source_symbol") or a.get("acquiree_symbol")
            ex = a.get("ex_date") or a.get("effective_date")
            if target != symbol or ex != day:
                continue
            if kind == "cash_dividends":
                rate = float(a["rate"])
                assert np.isfinite(rate) and rate >= 0
                cash += rate
            elif kind in ["forward_splits", "reverse_splits", "unit_splits"]:
                q = float(a["new_rate"]) / float(a["old_rate"])
                assert np.isfinite(q) and q > 0
                ratio *= q
                trigger = True
            elif kind == "spin_offs":
                child = a["new_symbol"]
                assert child in UNITS, "Unreceived distributed security identity"
                mark = raw[indices[day], UNITS.index(child)]
                assert np.isfinite(mark) and mark > 0, (
                    "Unknown child mark; no invented cash or zero"
                )
                spin += float(a["new_rate"]) / float(a["source_rate"]) * mark
            elif symbol == "WBA" and kind == "stock_and_cash_mergers":
                return np.nan, False  # Original scalar label handles known cash + separate CVR.
            else:
                raise ValueError(
                    "Unreceived action conversion/ordinary return: " + kind + ":" + a["id"]
                )
    return (
        (ratio * current + cash + spin) / previous - 1 if np.isfinite(current) else np.nan
    ), trigger


def extend_daily(old, raw_units, inherited, source):
    month = source["manifest"]["formation_month"]
    last = month_dates(month)[-1]
    dates = [
        d.isoformat()
        for d in us_equity_session_dates(
            date.fromisoformat(str(old["dates"][0])), date.fromisoformat(last)
        )
    ]
    old_dates = old["dates"].tolist()
    assert dates[: len(old_dates)] == old_dates
    assert raw_units["symbols"].tolist() == UNITS and raw_units["dates"].tolist() == old_dates
    assert old["symbols"].tolist() == SYMBOLS
    n = len(old_dates)
    shape = (len(dates), 31)
    close, opening, volume = [np.full(shape, np.nan) for _ in range(3)]
    close[:n] = raw_units["raw_close"]
    opening[:n] = raw_units["raw_open"]
    assert np.array_equal(close[:n, :28], old["raw_close"], equal_nan=True)
    assert np.array_equal(opening[:n, :28], old["raw_open"], equal_nan=True)
    volume[:n, :28] = old["raw_volume"]
    if "all_raw_volume" in old:
        volume[:n] = old["all_raw_volume"]
    index = {d: i for i, d in enumerate(dates)}
    seen = set()
    for obj in source["objects"]["raw-bars"]:
        assert isinstance(obj.get("bars"), dict)
        for s, rows in obj["bars"].items():
            assert s in UNITS
            j = UNITS.index(s)
            for r in rows:
                t = clock(r["t"]).astimezone(NEW_YORK)
                assert (t.hour, t.minute, t.second, t.microsecond) == (0, 0, 0, 0), (
                    "Not an exact daily source bar"
                )
                day = t.date().isoformat()
                assert day in index and day >= source["manifest"]["prefix_end"]
                assert (s, day) not in seen
                seen.add((s, day))
                if r["v"] == 0 and r.get("n", 0) == 0:
                    continue
                assert float(r["v"]) >= 0 and float(r["v"]) == int(r["v"])
                i = index[day]
                if i < n:
                    assert close[i, j] == r["c"] and opening[i, j] == r["o"], "Raw prefix drift"
                    if j < 28:
                        assert volume[i, j] == r["v"], "Raw-volume prefix drift"
                close[i, j], opening[i, j], volume[i, j] = r["c"], r["o"], r["v"]
    returns = np.full((len(dates), 28), np.nan)
    returns[:n] = old["returns"]
    eligible = np.zeros_like(returns, dtype=bool)
    eligible[:n] = inherited["eligible"]
    trigger = np.zeros_like(eligible)
    actions = source["actions"]
    for i in range(n, len(dates)):
        for j, s in enumerate(SYMBOLS):
            returns[i, j], trigger[i, j] = one_return(
                close[i - 1, j], close[i, j], s, dates[i], close, index, actions
            )
    frame = pd.DataFrame(returns)
    log = np.log1p(frame)
    parts = [np.expm1(log.rolling(k, min_periods=k).sum()).to_numpy() for k in [5, 21, 63]]
    parts.append(np.expm1(log.rolling(231, min_periods=231).sum()).shift(21).to_numpy())
    parts += [frame.rolling(k, min_periods=k).std().to_numpy() for k in [21, 63]]
    finite = np.isfinite(np.stack(parts, axis=-1)).all(-1)
    for i in range(n, len(dates)):
        c, o, report = sanitize_price_matrices(
            pd.DataFrame(close[: i + 1, :28], index=dates[: i + 1], columns=SYMBOLS),
            pd.DataFrame(opening[: i + 1, :28], index=dates[: i + 1], columns=SYMBOLS),
        )
        for b in report.manifest()["breaks_by_symbol"].items():
            for item in b[1]:
                if item["kind"] == "jump" and item["first_session_after"] == dates[i]:
                    trigger[i, SYMBOLS.index(b[0])] = True
        eligible[i] = np.isfinite(c.iloc[-1].to_numpy()) & ~trigger[i] & finite[i]
        eligible[i, SYMBOLS.index("WBA")] = False  # Known legal cancellation, issuer retained.
    return dict(
        dates=np.asarray(dates),
        symbols=np.asarray(SYMBOLS),
        raw_close=close[:, :28],
        raw_open=opening[:, :28],
        raw_volume=volume[:, :28],
        returns=returns,
        eligible=eligible,
        all_raw_close=close,
        all_raw_open=opening,
        all_raw_volume=volume,
        all_symbols=np.asarray(UNITS),
    ), trigger


def formation(daily, source):
    """Parameterization of exact accepted September/current-row recipe."""
    month = source["manifest"]["formation_month"]
    cutoff = source["manifest"]["source_cutoff"]
    dates = daily["dates"].tolist()
    days = month_dates(month)
    assert dates[-len(days) :] == days, "Incomplete or stale formation calendar"
    a = dates.index(days[0])
    e = len(dates) - 1
    p = a - 1
    close = pd.DataFrame(daily["raw_close"], index=dates, columns=SYMBOLS)
    opening = pd.DataFrame(daily["raw_open"], index=dates, columns=SYMBOLS)
    ce, _, he = sanitize_price_matrices(close, opening)
    cp, _, hp = sanitize_price_matrices(close.iloc[: p + 1], opening.iloc[: p + 1])
    splits = {
        s: [
            x
            for kind in ["forward_splits", "reverse_splits", "unit_splits"]
            for x in source["actions"].get(kind, [])
            if x.get("symbol") == s
        ]
        for s in SYMBOLS
    }
    previous = sorted({d[:7] for d in dates if d[:7] < month})
    moms = previous[-12:-1]
    history = [i for i, d in enumerate(dates) if d[:7] in moms]
    primitive = []
    flags = []
    turns = []
    ok = []
    records = []
    decision = calendar(month)["source_cutoff"]
    with legacy(SHARE):
        method = module("base_receiver_original_method", SHARE / "method.py")
        for j, s in enumerate(SYMBOLS):
            rr = daily["returns"][:, j]
            r = rr[a : e + 1]
            ret = float(np.prod(1 + r) - 1) if np.isfinite(r).all() else np.nan
            mom = (
                float(np.prod(1 + rr[history]) - 1)
                if len(moms) == 11 and np.isfinite(rr[history]).all()
                else np.nan
            )
            rv = (
                float(rr[e - 62 : e + 1].std(ddof=1))
                if e >= 62 and np.isfinite(rr[e - 62 : e + 1]).all()
                else np.nan
            )
            selected = method.select_count(
                source["inventory"]["selected_members"][s].get("records", []),
                source["witnesses"].get(s, {}),
                dates + [clock(cutoff).date().isoformat()],
                dates[e],
                decision,
            )
            complete = bool(np.isfinite(daily["raw_volume"][a : e + 1, j]).all())
            basis = False
            ve = se = t = np.nan
            error = None
            if complete:
                try:
                    ve, se, t = method.volume_count_basis(
                        dates[a : e + 1],
                        daily["raw_volume"][a : e + 1, j],
                        selected,
                        splits[s],
                        dates[e],
                        decision,
                    )
                    basis = True
                except ValueError as exc:
                    error = str(exc)
            pth = method.price_high(
                dates, cp.iloc[:, j].to_numpy(), p, splits[s], dates[p] + "T23:59:59"
            )
            end = float(ce.iloc[e, j])
            trigger = any(x.get("ex_date") == dates[e] for x in splits[s]) or any(
                x["kind"] == "jump" and x["first_session_after"] == dates[e]
                for x in he.manifest()["breaks_by_symbol"].get(s, [])
            )
            eligible = bool(
                daily["eligible"][e, j]
                and np.isfinite(ret)
                and np.isfinite(end)
                and end > 0
                and not trigger
            )
            logs = [
                float(np.log(x)) if np.isfinite(x) and x > 0 else np.nan
                for x in [ve, se, end, se * end]
            ]
            primitive.append([ret, mom, rv, *logs, pth, selected.get("age", np.nan) / 120])
            flags.append(
                [bool(selected["supported"] and np.isfinite(t)), complete, basis, np.isfinite(pth)]
            )
            turns.append(t)
            ok.append(eligible)
            records.append(
                dict(
                    symbol=s,
                    selected_count=selected,
                    volume_basis_error=error,
                    V_E=ve,
                    S_E=se,
                    turnover=t,
                    eligible=eligible,
                )
            )
    return dict(
        primitive=np.asarray(primitive),
        flags=np.asarray(flags),
        turnover=np.asarray(turns),
        eligible=np.asarray(ok),
    ), dict(records=records, sanitizer=[he.manifest(), hp.manifest()])


def complete_labels(monthly, daily, source_cutoff, pending):
    """Only explicitly pending old slots, strict actual exit-close and receipt maturity."""
    dates = daily["dates"].tolist()
    result = {k: v.copy() for k, v in monthly.items()}
    events = []
    completed_rows = []
    with legacy(SHARE):
        method = module("base_receiver_original_label", SHARE / "method.py")
        for i in pending:
            month = str(result["months"][i])
            end = next_us_equity_session(date.fromisoformat(month_dates(month)[-1]))
            exit_day = next_us_equity_session(
                date(end.year + (end.month == 12), end.month % 12 + 1, 1) - pd.Timedelta(days=1)
            )
            if exit_day.isoformat() not in dates or absolute_fact_time(
                exit_day.isoformat()
            ) >= clock(source_cutoff):
                continue
            entry = dates.index(end.isoformat())
            exit_index = dates.index(exit_day.isoformat())
            assert int(result["entry"][i]) == entry
            result["label_end"][i] = exit_index
            completed_rows.append(i)
            for j, s in enumerate(SYMBOLS):
                if not result["eligible"][i, j] or np.isfinite(result["label"][i, j]):
                    continue
                out = method.unit_label(
                    dates, daily["returns"][:, j], daily["raw_close"][:, j], s, entry, exit_index
                )
                result["label"][i, j] = out["net10"]
                events.append(
                    dict(
                        month=month,
                        symbol=s,
                        entry=dates[entry],
                        exit=dates[exit_index],
                        actual_exit_clock=absolute_fact_time(dates[exit_index]).isoformat(),
                        **out,
                    )
                )
    return result, events, completed_rows
