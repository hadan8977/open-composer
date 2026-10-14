"""Causal official daily holding clock independent of sparse entry Frames.

Uses the already accepted, split-reconciled stock daily prefix hygiene helper.
No quotes/native engine/returns or new source requests; no signal bar produced.
"""

# ruff: noqa: E402
import json
import sys
from dataclasses import asdict
from datetime import date
from pathlib import Path

P = Path(__file__).resolve().parents[2]
ROOT = P.parents[4]
sys.path.insert(0, str(P / "code"))
from consumer_admission import bind, save, verify_bindings
from continuation_admission import claim, remaining


def main(job):
    claim(job, "offline_input")
    from decision_system import read_parameters
    from frame_producer import SYMBOLS, FrameProducer
    from geometry import ema

    from open_composer.market_sessions import NEW_YORK

    inputs = json.loads((P / "complete-input-v2-result.json").read_text())
    aux = {Path(b["path"]).name: b for b in inputs["auxiliary_outputs"]}
    verify_bindings({k: aux[k] for k in ("daily-basis.json", "actions.json")})
    daily = json.loads((ROOT / aux["daily-basis.json"]["path"]).read_text())
    actions = json.loads((ROOT / aux["actions.json"]["path"]).read_text())
    assert isinstance(actions, list)
    parameters = read_parameters(
        ROOT / "strategy_specs/drafts/martin_complete_system_20261014.yaml"
    )
    producer = FrameProducer(parameters, daily, [], actions)
    from daily_prefix import daily_history

    comparisons = []
    for symbol, asof in [
        ("LMND", "2024-01-02"),
        ("SMCI", "2024-09-30"),
        ("SMCI", "2024-10-01"),
        ("GME", "2025-10-03"),
    ]:
        old = producer._daily_history(symbol, date.fromisoformat(asof))
        old_report = dict(producer.hygiene[symbol])
        new = daily_history(producer, symbol, date.fromisoformat(asof))
        assert [asdict(r) for r in old] == [asdict(r) for r in new]
        assert old_report == producer.hygiene[symbol]
        comparisons.append(dict(symbol=symbol, asof=asof, rows=len(old), exact=True))
    save(
        Path(__file__).resolve().parent / "daily-prefix-equivalence.json",
        dict(
            cases=comparisons,
            unchanged_reference=bind(P / "code/frame_producer.py"),
            vector_assembly=bind(Path(__file__).resolve().parent / "daily_prefix.py"),
        ),
    )
    inventory = json.loads(
        (P / "economic-results/complete-source-clock-inventory.json").read_text()
    )
    rows = []
    partial = Path(__file__).resolve().parent / "holding-daily-prefix-partial.jsonl"
    assert not partial.exists(), "retain existing partial rather than overwrite/repeat"
    for session in inventory["sessions"]:
        assert remaining(job) > 20, "budgetpartial not complete input"
        day = date.fromisoformat(session["day"])
        prior = producer.calendar[producer.ordinal[day] - 1]
        for symbol in SYMBOLS:
            history = daily_history(producer, symbol, day)
            valid = len(history) >= 9 and history[-1].end.astimezone(NEW_YORK).date() == prior
            row = dict(
                day=str(day),
                symbol=symbol,
                open_ns=session["start_ns"],
                status="observed_causal_previous_vendor_daily"
                if valid
                else "unresolved_latest_holding_daily",
                expected_prior_session=str(prior),
                price_basis_as_of=str(day),
                prefix_hygiene=dict(producer.hygiene[symbol]),
            )
            if valid:
                row.update(
                    available_at=history[-1].end.isoformat(),
                    prior_daily_close=history[-1].close,
                    prior_daily_ema9=ema([d.close for d in history], 9),
                    price_source=(
                        "same accepted official raw daily prefix as original entry "
                        "context; available20:00NY"
                    ),
                )
            rows.append(row)
        with partial.open("a") as f:
            for row in rows[-6:]:
                f.write(json.dumps(row) + "\n")
        if len(rows) % 120 == 0:
            print(
                json.dumps(dict(day=str(day), rows=len(rows), remaining_CPU=remaining(job))),
                flush=True,
            )
    save(
        Path(__file__).resolve().parent / "holding-daily-context.json",
        dict(
            status="complete_causal_official_holding_prefixes",
            rows=rows,
            input=bind(P / "complete-input-v2-result.json"),
            daily_basis=aux["daily-basis.json"],
            actions=aux["actions.json"],
            hygiene=bind(P / "code/frame_producer.py"),
            calendar_inventory=bind(P / "economic-results/complete-source-clock-inventory.json"),
            HTTP=0,
            engines=0,
            fit=0,
            PnL=0,
            signal_Frame_writes=0,
            unknown=sum(r["status"].startswith("unresolved") for r in rows),
            interpretation=(
                "No RTH bar reconstruction. Official daily may include extended "
                "hours; this is a named current-vintage adaptation. Holding "
                "decisions use prior20:00NY data at the nextRTHopen, never "
                "same-session future closes."
            ),
        ),
    )


if __name__ == "__main__":
    main(sys.argv[1])
