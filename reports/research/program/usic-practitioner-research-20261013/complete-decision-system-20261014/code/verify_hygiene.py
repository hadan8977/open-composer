"""Bound stock daily prefix equivalence; no Frames, fitting, signals or P&L."""

import json
import resource
import time
from dataclasses import replace
from datetime import date

from consumer_admission import ROOT, P, bind
from decision_system import read_parameters
from frame_producer import NEW_YORK, SYMBOLS, FrameProducer, vendor_day


def old_reconciled(producer, symbol, day):
    original = [
        vendor_day(d, r) for d, r in sorted(producer.raw_days[symbol].items()) if d < str(day)
    ]
    days = []
    for row in original[-producer.p["warmup_sessions"] :]:
        ratio = 1.0
        prior = row.end.astimezone(NEW_YORK).date().isoformat()
        for action in producer.actions:
            r = action["row"]
            if (
                action["kind"] == "forward_splits"
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
    return days


def main():
    import pandas as pd

    from open_composer.research.features.price_hygiene import sanitize_price_matrices

    resource.setrlimit(resource.RLIMIT_CPU, (19, 20))
    started = time.process_time()
    root = P / "inputs/full-v1"
    paths = [root / "daily-basis.json", root / "actions.json"]
    daily, actions = [json.loads(p.read_text()) for p in paths]
    params = read_parameters(ROOT / "strategy_specs/drafts/martin_complete_system_20261014.yaml")
    producer = FrameProducer(params, daily, [], actions)
    proof = FrameProducer(dict(params, warmup_sessions=100000), daily, [], actions)
    # This diagnostic never supplies full-period cleaned prices to a decision.
    # Zero detected breaks and zero ghosts imply every prefix/suffix is unchanged:
    # future known splits scale both sides of every prior ratio uniformly.
    canonical = {s: old_reconciled(proof, s, date(2026, 1, 1)) for s in SYMBOLS}
    index = pd.DatetimeIndex(producer.calendar)
    close = pd.DataFrame(float("nan"), index=index, columns=SYMBOLS)
    opened = close.copy()
    ghosts = []
    for symbol, days in canonical.items():
        for row in days:
            at = row.end.astimezone(NEW_YORK).date()
            if row.volume <= 0:
                ghosts.append(dict(symbol=symbol, session=str(at)))
            close.at[pd.Timestamp(at), symbol] = row.close
            opened.at[pd.Timestamp(at), symbol] = row.open
    cleaned, clean_open, hygiene = sanitize_price_matrices(close, opened)
    assert not hygiene.breaks and not ghosts, (hygiene, ghosts)
    assert cleaned.equals(close) and clean_open.equals(opened)
    actual = []
    dates = (date(2023, 12, 1), date(2024, 9, 30), date(2024, 10, 1), date(2025, 12, 31))
    for day in dates:
        for symbol in SYMBOLS:
            old = old_reconciled(producer, symbol, day)
            new = producer._daily_history(symbol, day)
            assert old == new, (symbol, day, producer.hygiene[symbol])
            actual.append(
                dict(symbol=symbol, as_of=str(day), observations=len(new), unchanged=True)
            )
    result = dict(
        status="actual_zero_break_equivalence_and_causal_prefix_verified",
        source_bindings=[bind(p) for p in paths],
        implementation=[bind(P / "code/frame_producer.py"), bind(P / "code/verify_hygiene.py")],
        canonical_daily_observations=sum(len(v) for v in canonical.values()),
        detected_default_breaks=0,
        ghost_observations=0,
        actual_prefix_checks=actual,
        actual_prefix_check_count=len(actual),
        retained_prefix_context_equivalence=True,
        default_hygiene=True,
        proof=(
            "No default adjacent jump or gap in homogeneous known-split u"
            "nits; no ghosts. Prefixes and warmup suffixes cannot introdu"
            "ce a break. Future split rebasing is uniform over a past pre"
            "fix and ratio-invariant. Full-period diagnostic is never use"
            "d as feature data."
        ),
        trigger_mask=(
            "Separate causal entry-only overlay from actual09:30 minute. "
            "Existing Frame bytes retained; holding outcomes never filter"
            "ed."
        ),
        prior_failed_diagnostic=bind(P / "causal-hygiene-verification-resource.txt"),
        prior_failure_claimed_complete=False,
        Frame_regeneration=0,
        PnL=0,
        fit=0,
        HTTP=0,
        CPU=time.process_time() - started,
    )
    (P / "causal-hygiene-verification.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
