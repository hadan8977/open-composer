# ruff: noqa: E501 -- Exact task paths, schema literals and retained formulas.
"""Accepted daily bridge; sole adaptation is explicit current reference end date."""
from datetime import date

import numpy as np
import pandas as pd
from features import one_return
from receiver_common import SYMBOLS, UNITS, clock

from open_composer.market_sessions import NEW_YORK, us_equity_session_dates
from open_composer.research.features.price_hygiene import sanitize_price_matrices


def extend_daily(old, raw_units, inherited, source):
    last = source["manifest"]["reference_day"]
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
    # The accepted physical-unit request starts2022; the accepted signal prefix
    # has2020/21 warmup. Preserve that signal prefix, never invent physical bars.
    covered = np.asarray(old_dates) >= "2022-01-01"
    assert np.array_equal(close[:n, :28][covered], old["raw_close"][covered], equal_nan=True)
    assert np.array_equal(opening[:n, :28][covered], old["raw_open"][covered], equal_nan=True)
    for physical, signal in [(close[:n, :28], old["raw_close"]), (opening[:n, :28], old["raw_open"])]:
        observed = np.isfinite(physical)
        assert np.array_equal(physical[observed], signal[observed]), "Conflicting observed raw prefix"
        assert not np.isinf(physical).any()
    close[:n, :28] = old["raw_close"]
    opening[:n, :28] = old["raw_open"]
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

