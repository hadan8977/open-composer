"""Next-open targets on the same adjusted basis as the stock universe."""

import numpy as np

LABEL_COST_BP = 10
STOP_FRACTION = 0.05
HORIZONS = (5, 20)


def daily_labels(opens, highs, lows, row, col, bar_known_at):
    """Entry at the decision-session open, exit at open +5/+20 sessions.

    Barriers use a fixed 5% stop and 10% target. An opening breach wins;
    otherwise the stop wins same-bar ties. A timeout is 20 complete bars.
    Missing prices before the outcome censor it. The completed-bar clock
    conservatively dates even outcomes that were already known at the open.
    """
    entry = opens[row, col]
    valid = np.isfinite(entry)
    label = np.full(len(row), np.nan, dtype="float32")
    resolved = np.full(len(row), -1)
    result = {}
    cost = LABEL_COST_BP / 10_000
    stop, target = entry * (1 - STOP_FRACTION), entry * (1 + 2 * STOP_FRACTION)
    for step in range(21):
        day = row + step
        open_ = opens[day, col]
        valid &= np.isfinite(open_)
        if step in HORIZONS:
            ratio = np.divide(open_, entry, where=valid, out=np.full(len(row), np.nan))
            result[f"net_return_{step}"] = (ratio * (1 - cost) / (1 + cost) - 1).astype("float32")
            result[f"matures_at_{step}"] = bar_known_at.take(day).where(valid)
        if step == 20:
            break

        high, low = highs[day, col], lows[day, col]
        pending = (resolved == -1) & valid
        stopped = open_ <= stop
        reached = open_ >= target
        complete = np.isfinite(high) & np.isfinite(low)
        stopped |= ~reached & complete & (low <= stop)
        reached |= complete & (high >= target)
        hit = pending & (stopped | reached)
        label[hit] = np.where(stopped[hit], -1, 1)
        resolved[hit] = day[hit]
        # Missing OHLC censors a still-pending barrier, independently of open returns.
        resolved[pending & ~hit & ~complete] = -2
        if step == 19:
            timeout = pending & ~hit & complete
            label[timeout] = 0
            resolved[timeout] = day[timeout]

    return {
        **result,
        "barrier_20": label,
        "matures_at_barrier": bar_known_at.take(resolved.clip(min=0)).where(resolved >= 0),
    }
