"""Adopt the H5 formation that the 2026-11-04 outage skipped, then let the daily
packet publish it.

The H5 grid is every five sessions (anchor 2024-01-02). The 2026-11-06 formation
was never built because the six-policy service was hung from 2026-11-04 17:41 to
2026-11-09 17:03, and ``h5_decision`` refuses to infer a missed formation at a
later close. This computes that formation from its own 2026-11-06 vintage with
the original code path, records it as a delayed formation, and installs it as
the live H5 instruction so the ordinary 2026-11-10 packet can publish a held
instruction from it. Nothing is invented: the features, models and marks are the
2026-11-06 receipts, and the deviation (computed four calendar days late, applied
one session after its intended 2026-11-09) is written into the receipt.

Read-only by default; ``--execute`` installs the two live target files with
backups beside them.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
T = ROOT / "reports/research/program/owner-profit-delivery-plan-20261017/current-paper-science-20261020"
RUNS = ROOT / "reports/paper/diagnostics/dated-target-refresh"
TARGETS = ROOT / "runtime/paper/six/targets"
FORMATION_DAY = "2026-11-06"
INTENDED_APPLICATION = "2026-11-09"
PACKET_REFERENCE = "2026-11-09"
PACKET_APPLICATION = "2026-11-10"


def load(path: Path) -> dict:
    return json.loads(Path(path).read_text())


def bind_row(path: Path) -> dict:
    import hashlib

    raw = Path(path).read_bytes()
    return dict(path=str(Path(path).resolve()), bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())


def atomic_write(path: Path, payload: dict) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=1, ensure_ascii=False, default=str) + "\n")
    os.replace(tmp, path)


def raw_bars(directory: Path) -> dict:
    bars = {}
    for pattern in ("core-raw-bars-*.raw", "ETF-raw-reference-*.raw"):
        for f in sorted(directory.glob("source/" + pattern)):
            body = json.loads(f.read_text())
            for symbol, rows in (body.get("bars") or {}).items():
                for row in rows:
                    bars[(symbol.upper(), row["t"][:10])] = row
    return bars


def build(prep: Path) -> dict:
    """Build the missed formation inside the 2026-11-09 packet's own receipts.

    The formation must bind the *original* source / action-lineage / unit-control
    receipts, not copies: ``origin()`` refuses a formation whose controls point at
    another path ("foreign source lineage"). So the two new artifacts are appended
    to the received dated prefix, exactly like ``recover_dated_refresh`` does, and
    only the receipt lives in ``prep``.
    """
    import open_composer.paper_runtime.six.formation_continuity as fc
    from open_composer.paper_runtime.six.produce_targets import target, save

    source_run = RUNS / PACKET_REFERENCE
    previous = load(T / "input/H5/output.json")
    current = load(source_run / "current-h5-support.json")
    events = load(source_run / "current-actions.json")["events"]
    source = load(source_run / "current-source.json")
    assert source["reference_day"] == FORMATION_DAY, source["reference_day"]
    for stale in ("H5-formation-input.json", "H5-formation-forecast.json", "targets/H5.json"):
        (source_run / stale).unlink(missing_ok=True)
    signal = fc.h5_decision(
        previous,
        current,
        raw_bars(source_run),
        events,
        FORMATION_DAY,
        INTENDED_APPLICATION,
        write=save,
        root=source_run,
        now=lambda: datetime.now(UTC).isoformat(),
    )
    assert signal["is_fresh_prediction"] is True, "expected the missed formation to be fresh"
    assert signal["signal_observation"] == FORMATION_DAY
    forecast_binding = signal["signal_forecast"]
    carriers = previous["controls"]["carriers"]
    symbols = [carriers.get(s) or s for s in current["symbols"]]
    marks = load(RUNS / PACKET_APPLICATION / "current-marks.json")
    instruction = target(
        source_run,
        "H5",
        symbols,
        signal["allocation"]["weights"],
        marks,
        source,
        PACKET_REFERENCE,
        PACKET_APPLICATION,
        signal_forecast=forecast_binding,
        signal_observation=signal["signal_observation"],
        signal_application=signal["signal_application"],
        original_computed_at=signal["original_computed_at"],
        next_regular_observation=signal["phase"]["next_observation"],
        next_regular_application=signal["phase"]["next_application"],
        model_epoch=signal["model_epoch"],
        is_fresh_prediction=False,
        portfolio_action="hold",
        K=signal["allocation"]["K"],
        delayed_formation_adopted_utc=datetime.now(UTC).isoformat(),
        delayed_formation_reason="2026-11-06 formation skipped by the 2026-11-04..09 service outage",
        allocation_intent=(
            "complete_unfulfilled_initial_allocation_only_after_operating_prefix_acceptance"
        ),
    )
    prep.mkdir(parents=True, exist_ok=True)
    atomic_write(prep / "installed-H5-instruction.json", instruction)
    receipt = dict(
        schema_version=1,
        at_utc=datetime.now(UTC).isoformat(),
        gap=dict(
            missed_formation_day=FORMATION_DAY,
            intended_application_day=INTENDED_APPLICATION,
            adopted_application_day=PACKET_APPLICATION,
            cause="six-policy service hung 2026-11-04T17:41:56Z..2026-11-09T17:03Z",
        ),
        formation=dict(
            signal_forecast=forecast_binding,
            is_fresh_prediction=signal["is_fresh_prediction"],
            allocation=signal["allocation"],
            model_epoch=signal["model_epoch"],
            next_regular_observation=signal["phase"]["next_observation"],
            next_regular_application=signal["phase"]["next_application"],
        ),
        receipts=dict(
            packet_root=str(source_run),
            source=bind_row(source_run / "current-source.json"),
            action_lineage=bind_row(source_run / "action-lineage-QA.json"),
            current_controls=bind_row(source_run / "current-h5-support.json"),
        ),
        installed_instruction=dict(path=str(TARGETS / "H5.json"), content=instruction),
        deviation=(
            "The formation was computed from its own 2026-11-06 receipts on "
            f"{PACKET_APPLICATION} instead of on the evening of {FORMATION_DAY}; it is applied "
            f"at the {PACKET_APPLICATION} open, one session after its intended "
            f"{INTENDED_APPLICATION}. No later close, label, price or fit is used."
        ),
        order_authority=False,
        broker_calls=0,
    )
    atomic_write(prep / "delayed-formation-receipt.json", receipt)
    return dict(signal=signal, instruction=instruction, receipt=receipt)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--prep",
        type=Path,
        default=ROOT / "reports/paper/diagnostics/h5-delayed-formation-20261110",
    )
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    prep = args.prep.resolve()
    prep.mkdir(parents=True, exist_ok=True)
    live_h5 = load(TARGETS / "H5.json")
    print(f"live H5 observation={live_h5.get('signal_observation')} application={live_h5.get('application_day')}")
    built = build(prep)
    sig = built["signal"]
    print(
        "formation:",
        f"observation={sig['signal_observation']}",
        f"fresh={sig['is_fresh_prediction']}",
        f"action={sig['portfolio_action']}",
        f"K={sig['allocation']['K']}",
        f"selected={[s for s, w in zip(built['instruction']['symbols'], built['instruction']['weights']) if w > 0]}",
        f"weights={[w for w in built['instruction']['weights'] if w > 0]}",
    )
    if not args.execute:
        print("dry run; pass --execute to install the H5 instruction and roll the LSTM baseline back")
        return 0
    # 1) install the adopted H5 instruction (backup first)
    backup = prep / "predecessor-targets"
    backup.mkdir(exist_ok=True)
    shutil.copyfile(TARGETS / "H5.json", backup / "H5.json")
    atomic_write(TARGETS / "H5.json", built["instruction"])
    print("installed", TARGETS / "H5.json")
    # 2) roll the daily baseline back to the 2026-11-09 packet so the LSTM
    #    adjusted-history append has exactly one new session to append.
    prior = RUNS / PACKET_APPLICATION / "predecessor-targets" / "LSTM.json"
    assert prior.exists(), prior
    shutil.copyfile(TARGETS / "LSTM.json", backup / "LSTM.json")
    shutil.copyfile(prior, TARGETS / "LSTM.json")
    print("rolled LSTM baseline back to", load(prior)["source"]["path"])
    print(json.dumps({"prep": str(prep), "backup": str(backup)}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
