"""Frozen monthly definitions; no file reads, models or accounts on import."""

from bisect import bisect_right
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from fractions import Fraction
from zoneinfo import ZoneInfo

import numpy as np

CONTINUOUS = [
    "ret1",
    "mom12_2",
    "rv63",
    "log_month_volume_E",
    "log_disclosed_shares_E",
    "log_end_raw_price",
    "log_disclosed_size",
    "preformation_PTH",
    "count_age_over120",
]
FLAGS = [
    "share_supported",
    "raw_volume_complete",
    "split_basis_supported",
    "preformation_PTH_supported",
]


def _aware_clock(value):
    """Unknown/naive publication time stays unknown, never midnight-imputed."""
    try:
        clock = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return clock.astimezone(UTC) if clock.tzinfo is not None else None
    except (AttributeError, TypeError, ValueError):
        return None


def split_factor(events, left, right, decision):
    """Normalize event IDs/ratios; daily dates alone cannot order two splits."""
    grouped = {}
    for event in events:
        ex = event.get("ex_date")
        if ex is None:
            raise ValueError("Split without economic date")
        if left < ex <= right:
            process = event.get("process_date")
            old, new = event.get("old_rate"), event.get("new_rate")
            if not process or process > decision[:10] or not old or not new:
                raise ValueError("Unknown split ratio/conditional availability")
            try:
                old_value, new_value = float(old), float(new)
            except (TypeError, ValueError) as exc:
                raise ValueError("Unparsed split ratio") from exc
            if not np.isfinite([old_value, new_value]).all() or min(old_value, new_value) <= 0:
                raise ValueError("Invalid split rates")
            q = new_value / old_value
            if not np.isfinite(q) or q <= 0:
                raise ValueError("Invalid split units")
            ratio = Fraction(Decimal(str(new))) / Fraction(Decimal(str(old)))
            identity = event.get("economic_event_id") or event["id"]
            key = (ex, identity)
            if key in grouped:
                prior, prior_ratio = grouped[key]
                if prior_ratio != ratio or any(
                    prior.get(k) != event.get(k)
                    for k in ["symbol", "from_symbol", "to_symbol", "economic_sequence"]
                ):
                    raise ValueError("Conflicting versions of one economic split")
            else:
                grouped[key] = (event, ratio)
    factor, applied = Fraction(1), []
    for ex in sorted({key[0] for key in grouped}):
        same_day = {key[1]: value for key, value in grouped.items() if key[0] == ex}
        order = sorted(same_day)
        if len(same_day) > 1:
            # A received inline source may explicitly identify successive share
            # units and their ordered economic IDs. Do not synthesize this
            # witness from daily ex-dates, ratios or provider IDs. The current
            # date-only provider contract supplies no such sequencing proof.
            witnesses = [item[0].get("economic_sequence") for item in same_day.values()]
            sequence = witnesses[0]
            if not isinstance(sequence, dict) or not all(x == sequence for x in witnesses):
                raise ValueError("Ambiguous same-date split composition")
            order = sequence.get("ordered_event_ids", [])
            if (
                sequence.get("basis") != "successive_share_units"
                or not sequence.get("source_text")
                or len(order) != len(same_day)
                or len(set(order)) != len(order)
                or set(order) != set(same_day)
            ):
                raise ValueError("Unproved same-date split sequence/basis")
        for identity in order:
            event, ratio = same_day[identity]
            factor *= ratio
            applied.append(event["id"])
    value = float(factor)
    if not np.isfinite(value) or value <= 0:
        raise ValueError("Invalid compounded split units")
    return value, applied


def _matches_count_witness(record, witness):
    """Bind the selected fact to its exact retained cover/class witness.

    Inventory records originate only in companyfacts' units['shares']; an
    explicit different unit is invalid. Cover unitref is validated by the
    retained parser as a share unit, independently of the accession lookup.
    """
    if not witness or witness.get("supported") is not True:
        return False
    saved = witness.get("record", {})
    if any(record.get(k) != saved.get(k) for k in ["accn", "end", "filed", "form"]):
        return False
    if record.get("unit", "shares") != "shares" or saved.get("unit", "shares") != "shares":
        return False
    if witness.get("clock", {}).get("accn", record["accn"]) != record["accn"]:
        return False
    counts = witness.get("cover_counts", [])
    context = witness.get("count_context", {})
    securities = witness.get("common_registered_securities", [])
    security = witness.get("matched_security")
    if (
        len(counts) != 1
        or context.get("instant") != record["end"]
        or len(securities) != 1
        or security != securities[0]
        or not security
        or not all(security.get(k) for k in ["context", "ticker", "title"])
        or "share" not in str(counts[0].get("unit", "")).lower()
    ):
        return False
    try:
        values = [Decimal(str(x)) for x in [record["val"], saved["val"], counts[0]["value"]]]
        return all(x.is_finite() and x > 0 for x in values) and len(set(values)) == 1
    except (KeyError, TypeError, ValueError, InvalidOperation):
        return False


def select_count(records, witnesses, dates, formation_end, decision):
    decision_clock = datetime.fromisoformat(decision)
    if decision_clock.tzinfo is None:
        decision_clock = decision_clock.replace(tzinfo=ZoneInfo("America/New_York"))
    eligible = []
    for record in records:
        pos = bisect_right(dates, record["filed"])
        if pos == len(dates) or record["end"] > formation_end:
            continue
        visible = dates[pos] + "T09:30:00"
        if (
            datetime.fromisoformat(visible).replace(tzinfo=ZoneInfo("America/New_York"))
            > decision_clock
        ):
            continue
        witness = witnesses.get(record["accn"])
        actual = _aware_clock((witness or {}).get("clock", {}).get("acceptanceDateTime"))
        if actual is not None and actual > decision_clock:
            continue
        eligible.append((record, witness, visible, actual))
    if not eligible:
        return dict(supported=False, reason="no_public_instant_count")
    # Latest public instant first; do not select an older count because the
    # latest disclosure's class witness is missing or inconvenient.
    latest = max(x[0]["end"] for x in eligible)
    eligible = [x for x in eligible if x[0]["end"] == latest]
    filed = max(x[0]["filed"] for x in eligible)
    eligible = [x for x in eligible if x[0]["filed"] == filed]
    known_order = all(x[3] is not None for x in eligible)
    if known_order:
        publication = max(x[3] for x in eligible)
        eligible = [x for x in eligible if x[3] == publication]
    # Missing actual clocks leave an unordered filed-day group. Differing
    # values or an unproved class cannot be resolved by accession sorting or
    # selecting an older supported row; no invented publication time is used.
    if len({Decimal(str(x[0]["val"])) for x in eligible}) != 1:
        return dict(
            supported=False,
            reason="conflicting_latest_disclosure" if known_order else "unknown_publication_order",
        )
    record, witness, visible, actual = max(eligible, key=lambda x: x[0]["accn"])
    age = (datetime.fromisoformat(formation_end) - datetime.fromisoformat(record["end"])).days
    out = dict(
        record=record,
        age=age,
        conditional_visible=visible,
        actual_publication=actual.isoformat() if actual is not None else None,
        publication_order="actual_acceptance" if known_order else "conservative_filed_day_tie",
        class_witness_supported=all(_matches_count_witness(x[0], x[1]) for x in eligible),
    )
    if not 0 <= age <= 120:
        return dict(**out, supported=False, reason="instant_age_outside0_120")
    if not out["class_witness_supported"]:
        return dict(**out, supported=False, reason="same_traded_class_unproved")
    return dict(**out, supported=True, reason="public_same_class_instant")


def volume_count_basis(days, volumes, selected, events, end, decision):
    """Raw day shares and disclosed shares on one end-E basis, dividends absent."""
    ve = 0.0
    for day, volume in zip(days, volumes, strict=True):
        if not np.isfinite(volume) or volume < 0 or volume != int(volume):
            raise ValueError("Missing/nonshare raw volume")
        factor, _ = split_factor(events, day, end, decision)
        ve += volume * factor
    if not np.isfinite(ve) or ve <= 0:
        raise ValueError("No positive complete raw month volume")
    se, turnover = np.nan, np.nan
    if selected["supported"]:
        record = selected["record"]
        factor, _ = split_factor(events, record["end"], end, decision)
        se = float(record["val"]) * factor
        if se <= 0 or not np.isfinite(se):
            raise ValueError("Invalid common-share denominator")
        turnover = ve / se
    return ve, se, turnover


def price_high(dates, close, endpoint, events, decision):
    if endpoint < 251:
        return np.nan
    left = endpoint - 251
    historical = []
    for i in range(left, endpoint + 1):
        if not np.isfinite(close[i]) or close[i] <= 0:
            return np.nan
        try:
            factor, _ = split_factor(events, dates[i], dates[endpoint], decision)
        except ValueError:
            return np.nan
        historical.append(close[i] / factor)
    return float(historical[-1] / max(historical))


def unit_label(dates, returns, raw_close, symbol, entry, exit_day):
    """Known-priced operating capital; WBA CVR is separate, never valued at0."""
    if exit_day is None:
        return dict(
            net10=np.nan,
            gross=np.nan,
            CVR_units=np.nan,
            total_wealth_lower=np.nan,
            total_wealth_upper=np.nan,
            reason="pending_next_month_close",
        )
    if not np.isfinite(raw_close[entry]) or raw_close[entry] <= 0:
        return dict(
            net10=np.nan,
            gross=np.nan,
            CVR_units=np.nan,
            total_wealth_lower=np.nan,
            total_wealth_upper=np.nan,
            reason="unknown_executable_entry_reference",
        )
    capital, rights, converted = 1.0, 0.0, False
    for d in range(entry + 1, exit_day + 1):
        if symbol == "WBA" and dates[d] == "2025-08-28":
            price = raw_close[d - 1]
            if not np.isfinite(price) or price <= 0:
                return dict(
                    net10=np.nan,
                    gross=np.nan,
                    CVR_units=np.nan,
                    total_wealth_lower=np.nan,
                    total_wealth_upper=np.nan,
                    reason="unknown_conversion_reference",
                )
            rights += capital / price
            capital *= 11.45 / price
            converted = True
        elif not converted:
            r = returns[d]
            if not np.isfinite(r):
                return dict(
                    net10=np.nan,
                    gross=np.nan,
                    CVR_units=np.nan,
                    total_wealth_lower=np.nan,
                    total_wealth_upper=np.nan,
                    reason="unknown_ordinary_held_return",
                )
            capital *= 1 + r
    return dict(
        net10=capital * 0.999 / 1.001 - 1,
        gross=capital - 1,
        CVR_units=rights,
        total_wealth_lower=capital,
        total_wealth_upper=capital + 3 * rights,
        reason="operating_capital_with_separate_CVR_bounds"
        if rights
        else "known_priced_connected_path",
    )


def weighted_median(x, weights):
    valid = np.isfinite(x)
    if not valid.any():
        return 0.0
    order = np.argsort(x[valid], kind="stable")
    xx, ww = x[valid][order], weights[valid][order]
    return float(xx[np.searchsorted(np.cumsum(ww), ww.sum() / 2, side="left")])


def train_design(raw, flags, turnover, weights, state=None):
    """Train-only imputation/z scores, then products, then final Ridge scaling."""
    if state is None:
        med = np.array([weighted_median(raw[:, j], weights) for j in range(raw.shape[1])])
        x = np.where(np.isfinite(raw), raw, med)
        mu = np.average(x, axis=0, weights=weights)
        sd = np.sqrt(np.average((x - mu) ** 2, axis=0, weights=weights))
        sd[sd < 1e-12] = 1
        valid = np.isfinite(turnover) & (turnover > 0)
        lt = np.full(len(turnover), np.nan)
        lt[valid] = np.log(turnover[valid])
        # Only genuinely supported T observations determine T normalization.
        tm = float(np.average(lt[valid], weights=weights[valid])) if valid.any() else 0.0
        ts = (
            float(np.sqrt(np.average((lt[valid] - tm) ** 2, weights=weights[valid])))
            if valid.any()
            else 1.0
        )
        ts = ts if ts >= 1e-12 else 1.0
        state = dict(
            median=med.tolist(),
            mean=mu.tolist(),
            scale=sd.tolist(),
            turnover_mean=tm,
            turnover_scale=ts,
        )
    x = np.where(np.isfinite(raw), raw, np.asarray(state["median"]))
    z = (x - np.asarray(state["mean"])) / np.asarray(state["scale"])
    base = np.c_[z, flags, z[:, 0] * z[:, 7]]
    zt = np.zeros(len(turnover))
    valid = np.isfinite(turnover) & (turnover > 0)
    zt[valid] = (np.log(turnover[valid]) - state["turnover_mean"]) / state["turnover_scale"]
    aug = np.c_[base, zt, z[:, 0] * zt]
    return base, aug, state


def target(scores, eligible, symbols, policy, ret1, turnover):
    valid = list(np.flatnonzero(eligible))
    q = np.zeros(len(symbols))
    if policy == "COHORT_EW":
        if valid:
            q[valid] = min(0.2, 1 / len(valid))
        return q
    if policy in ["BASE", "AUG"]:
        if not np.isfinite(scores[valid]).all():
            return q  # Unsupported fit is explicit cash, never future backfill.
        valid = [j for j in valid if scores[j] > 0]
        ranking = scores
    else:
        valid = [j for j in valid if np.isfinite(ret1[j]) and ret1[j] > 0]
        if policy == "WINNER_HIGH_T":
            valid = [j for j in valid if np.isfinite(turnover[j]) and turnover[j] > 0]
            if valid:
                median = float(np.median(turnover[valid]))
                valid = [j for j in valid if turnover[j] >= median]
        elif policy != "MOM1":
            raise ValueError("Unknown frozen policy")
        ranking = ret1
    q[sorted(valid, key=lambda j: (-float(ranking[j]), str(symbols[j])))[:5]] = 0.2
    return q
