"""Read sealed inputs once: exact gaps, clocks, causal eligibility envelope.

No policy instantiation, fills, account/return calculation or new signal bars.
"""

# ruff: noqa: E402
import calendar
import gzip
import hashlib
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

P = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(P / "code"))
from consumer_admission import ROOT, bind
from continuation_admission import claim, remaining


def ns(value):
    d = datetime.fromisoformat(value)
    return calendar.timegm(d.utctimetuple()) * 10**9 + d.microsecond * 1000


def main(job):
    claim(job, "offline_input")
    import msgspec

    frame_result = json.loads((P / "frame-preparation-result.json").read_text())
    sessions = {}
    potential = set()
    source_reads = []
    first_candidates = {}
    counters = Counter()
    for source in frame_result["outputs"]:
        if Path(source["path"]).name.startswith("2023-"):
            continue
        assert remaining(job) > 20, "bounded incomplete inventory retains old outputs"
        path = ROOT / source["path"]
        h = hashlib.sha256()
        with path.open("rb") as raw:
            for chunk in iter(lambda: raw.read(1024 * 1024), b""):
                h.update(chunk)
        assert h.hexdigest() == source["sha256"] and path.stat().st_size == source["bytes"]
        source_reads.append(source)
        with gzip.open(path, "rb") as f:
            for line in f:
                packet = msgspec.json.decode(line)
                day = packet["session"]
                s = sessions.setdefault(
                    day,
                    dict(
                        day=day,
                        ordinal=packet["ordinal"],
                        session_minutes=packet["session_minutes"],
                        start_ns=ns(packet["start"]) - packet["minute"] * 60 * 10**9,
                        missing=defaultdict(list),
                        eligible=defaultdict(list),
                        actions=[],
                    ),
                )
                for symbol in packet["missing"]:
                    s["missing"][symbol].append(packet["minute"])
                    counters["missing_" + symbol] += 1
                s["actions"].extend(packet["actions"])
                for r in packet["frames"]:
                    fr = r["frame"]
                    # Superset: ignore touch/shape/quota/cash/feedback, never
                    # exclude a possible entry using future price/outcomes.
                    rising = (
                        fr.get("ema9_previous") is not None
                        and fr.get("ema21_previous") is not None
                        and (fr["ema9"] > fr["ema9_previous"] or fr["ema21"] > fr["ema21_previous"])
                    )
                    if (
                        fr.get("epoch_valid", True)
                        and fr["leadership"]
                        and fr["market"] not in {"weak", "unknown"}
                        and fr.get("trigger_price_eligible", True)
                        and rising
                    ):
                        symbol = fr["symbol"]
                        s["eligible"][symbol].append(packet["minute"])
                        potential.add(symbol)
                        first_candidates.setdefault(symbol, dict(day=day, at=fr["end"]))
                counters["calendar_minutes"] += 1
        print(json.dumps(dict(month=path.name[:7], remaining_CPU=remaining(job))), flush=True)
    rows = []
    for day, s in sorted(sessions.items()):
        s["missing"] = dict(s["missing"])
        s["eligible"] = dict(s["eligible"])
        # Freeze short intervals independently of prices/profits. A later
        # causal activity predicate may release only necessary witnesses.
        windows = []
        for symbol, minutes in sorted(s["missing"].items()):
            groups = []
            for minute in minutes:
                if not groups or minute - groups[-1][0] >= 30:
                    groups.append([minute])
                else:
                    groups[-1].append(minute)
            for group in groups:
                start = s["start_ns"] + group[0] * 60 * 10**9
                end = s["start_ns"] + (group[-1] + 1) * 60 * 10**9
                windows.append(
                    dict(
                        id=f"{symbol}_{day}_{group[0]:03}_{group[-1] + 1:03}",
                        symbol=symbol,
                        session=day,
                        gap_minutes=group,
                        start_ns=start,
                        end_ns=end,
                        prior_start_ns=max(s["start_ns"], start - 60 * 10**9),
                        at_RTH_open=group[0] == 0,
                    )
                )
        s["windows"] = windows
        rows.append(s)
    out = dict(
        status="complete_exact_input_clock_inventory_no_market_replay",
        input=bind(P / "frame-preparation-result.json"),
        read_outputs=source_reads,
        sessions=rows,
        counts=dict(counters),
        window_count=sum(len(s["windows"]) for s in rows),
        first_possible_context=first_candidates,
        selection_limits=(
            "Eligibility is only an overinclusive causal context envelope, "
            "not an entry/fill/held-state proof. Windows are clock-defined "
            "before new outcomes; HTTP release needs independent acceptance."
        ),
        HTTP=0,
        native_engines=0,
        fills=0,
        PnL=0,
        new_Frame=0,
    )
    (P / "economic-results/complete-source-clock-inventory.json").write_text(
        json.dumps(out, indent=2) + "\n"
    )


if __name__ == "__main__":
    main(sys.argv[1])
