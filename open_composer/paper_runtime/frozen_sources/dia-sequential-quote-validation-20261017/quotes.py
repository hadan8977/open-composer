"""Pure frozen quote-state selection; no network, cache or account access."""

import calendar
import math
import re
from datetime import datetime


def timestamp_ns(text):
    match = re.fullmatch(r"(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d)(?:\.(\d{1,9}))?(Z|[+-]\d\d:\d\d)", text)
    if match is None:
        raise ValueError("Unsupported quote timestamp")
    dt = datetime.fromisoformat(match[1] + match[3].replace("Z", "+00:00"))
    seconds = calendar.timegm(dt.utctimetuple())
    return seconds * 10**9 + int((match[2] or "").ljust(9, "0"))


def select_quote(messages, cutoff_ns, day, conditions, venues):
    candidates = [(timestamp_ns(q["t"]), q) for q in messages]
    if any(t < cutoff_ns - 5 * 10**9 or t > cutoff_ns for t, _ in candidates):
        raise ValueError("Raw source timestamp outside frozen inclusive window")
    base = dict(valid=False, cutoff_ns=cutoff_ns, source_record_count=len(candidates))
    if not candidates:
        return dict(base, reason="no_observation_in_frozen_five_second_window")
    latest = max(t for t, _ in candidates)
    tied = [q for t, q in candidates if t == latest]
    keys = ["t", "bp", "ap", "bs", "as", "bx", "ax", "c", "z"]
    states = [{k: q.get(k) for k in keys} for q in tied]
    canonical = []
    for raw in states:
        state = dict(raw, t=latest)
        if isinstance(state["c"], list) and len(state["c"]) == 1:
            state["c"] = state["c"] * 2
        canonical.append(state)
    base.update(timestamp_ns=latest, age_ns=cutoff_ns - latest, latest_tie_count=len(tied))
    if any(state != canonical[0] for state in canonical[1:]):
        return dict(base, reason="ambiguous_equal_timestamp_states", raw_latest_states=states)
    q = states[0]
    base["raw_quote"] = q
    base["raw_latest_states"] = states
    if q["z"] not in conditions:
        return dict(base, reason="unknown_tape")
    codes = q["c"]
    if not isinstance(codes, list) or len(codes) not in [1, 2]:
        return dict(base, reason="missing_or_invalid_condition_arity")
    if len(codes) == 1:
        codes = codes * 2
    if any(c != "R" or c not in conditions[q["z"]] for c in codes):
        return dict(base, reason="nonregular_quote_condition")
    if any(
        not isinstance(q[k], (int, float))
        or isinstance(q[k], bool)
        or not math.isfinite(q[k])
        or q[k] <= 0
        for k in ["bp", "ap"]
    ):
        return dict(base, reason="invalid_or_withdrawn_side_price")
    if q["bp"] >= q["ap"]:
        return dict(base, reason="locked_or_crossed")
    if any(type(q[k]) is not int or q[k] <= 0 for k in ["bs", "as"]):
        return dict(base, reason="invalid_or_zero_displayed_size")
    if any(q[k] not in venues or not q[k] for k in ["bx", "ax"]):
        return dict(base, reason="unknown_side_venue")
    factor = 100 if day < "2025-11-03" else 1
    return dict(
        base,
        valid=True,
        reason="valid_regular_latest_vendor_quote",
        bid=float(q["bp"]),
        ask=float(q["ap"]),
        bid_shares=q["bs"] * factor,
        ask_shares=q["as"] * factor,
        raw_size_unit="round_lots_of_100" if factor == 100 else "shares",
        lot_to_shares_factor=factor,
    )


def prior_unit_guard(quote, reference_close, prior_mark_valid, split_session, threshold):
    """The later session close/open cannot validate the earlier quote wave."""
    if not quote["valid"]:
        return quote
    reason = None
    if split_session:
        reason = "known_mechanical_split_session_ordinary_execution_excluded"
    elif not prior_mark_valid or not math.isfinite(reference_close) or reference_close <= 0:
        reason = "prior_completed_close_hygiene_or_reference_missing"
    elif not all(1 / threshold < quote[k] / reference_close < threshold for k in ["bid", "ask"]):
        reason = "default_known_unit_break_guard"
    return dict(quote, valid=False, reason=reason) if reason else quote
