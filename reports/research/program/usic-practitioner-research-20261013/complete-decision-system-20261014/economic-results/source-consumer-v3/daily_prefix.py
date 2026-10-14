"""Same causal daily matrices as FrameProducer, assembled in vector form.

Full raw dictionaries are input storage only. Sanitization is invoked separately
on each then-available150-observation prefix, never once on future full history.
"""

from dataclasses import replace
from math import isfinite

import pandas as pd
from frame_producer import vendor_day

from open_composer.market_sessions import NEW_YORK
from open_composer.research.features.price_hygiene import sanitize_price_matrices


def daily_history(producer, symbol, day):
    original = [
        vendor_day(d, r) for d, r in sorted(producer.raw_days[symbol].items()) if d < str(day)
    ]
    days = []
    for row in original[-producer.p["warmup_sessions"] :]:
        ratio = 1.0
        prior = row.end.astimezone(NEW_YORK).date().isoformat()
        for a in producer.actions:
            r = a["row"]
            if (
                a["kind"] == "forward_splits"
                and r["symbol"] == symbol
                and prior < r["ex_date"] <= str(day)
            ):
                ratio *= r["new_rate"] / r["old_rate"]
        days.append(
            replace(
                row,
                open=row.open / ratio,
                high=row.high / ratio,
                low=row.low / ratio,
                close=row.close / ratio,
                volume=row.volume * ratio,
                vwap=row.vwap / ratio if row.vwap is not None else None,
            )
        )
    if not days:
        producer.hygiene[symbol] = dict(masked=0, breaks=[])
        return days
    first = days[0].end.astimezone(NEW_YORK).date()
    sessions = [d for d in producer.calendar if first <= d < day]
    index = pd.DatetimeIndex(sessions)
    data = {row.end.astimezone(NEW_YORK).date(): row for row in days if row.volume > 0}
    # Identical old index/order/NaNs and float dtype; avoid450000 scalar .at
    # writes and900000 scalar reads across six symbols/dates.
    assert set(data) <= set(sessions), "unexpected_daily_outside_calendar"
    close = pd.DataFrame(
        {symbol: [float(data[d].close) if d in data else float("nan") for d in sessions]},
        index=index,
    )
    opened = pd.DataFrame(
        {symbol: [float(data[d].open) if d in data else float("nan") for d in sessions]},
        index=index,
    )
    cleaned, clean_open, report = sanitize_price_matrices(close, opened)
    producer.hygiene[symbol] = dict(
        masked=report.price_cells_masked,
        breaks=[
            dict(kind=b.kind, first_after=str(b.first_session_after.date()), masked=b.masked)
            for b in report.breaks
        ],
        as_of=str(day),
    )
    producer.qa["stock_daily_hygiene_masked_cells"] += report.price_cells_masked
    good = {
        d
        for d, c, o in zip(
            sessions, cleaned[symbol].to_numpy(), clean_open[symbol].to_numpy(), strict=True
        )
        if isfinite(c) and isfinite(o)
    }
    return [row for row in days if row.end.astimezone(NEW_YORK).date() in good]
