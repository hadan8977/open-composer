# ruff: noqa: E501 -- Exact existing evidence path.
"""Reuse completed fixed31 raw/action receipts; never modify or wake their observer."""

from datetime import date, timedelta

from receiver_common import REPO, UNITS, binding, canonical, clock, legacy, load, module

Q = (
    REPO
    / "reports/research/program/return-line-replenishment-20261016/dia-prospective-readonly-20261017"
)


def receive_retained(rows, cutoff, prefix_end, formation_end):
    objects = []
    actions = []
    bindings = []
    tail = prefix_end
    coverage = []
    received_through = None
    with legacy(Q):
        receiver = module("base_receiver_existing_capture", Q / "source_receiver.py")
        for b in rows:
            path = canonical(b["path"])
            assert path.parent.parent == Q / "source-captures" and path.name == "complete.json"
            assert binding(path) == b
            capture = receiver.capture(path.parent)
            complete = capture["complete"]
            assert clock(complete["at_utc"]) <= clock(cutoff)
            received_through = (
                max(received_through, clock(complete["at_utc"]))
                if received_through
                else clock(complete["at_utc"])
            )
            bindings.append(b)
            for role in ["raw-bars", "actions"]:
                for raw, obj in capture["pages"][role]:
                    meta_path = raw.with_suffix(".json")
                    meta = load(meta_path)
                    assert clock(meta["received_at_utc"]) <= clock(cutoff)
                    assert meta["params"]["symbols"].split(",") == UNITS
                    bindings.extend(
                        [
                            meta["response"],
                            binding(meta_path),
                            binding(raw.with_name(raw.stem + ".started.json")),
                        ]
                    )
                    if role == "raw-bars":
                        assert all(
                            meta["params"][k] == v
                            for k, v in [("feed", "sip"), ("adjustment", "raw"), ("asof", "-")]
                        )
                        left = meta["params"]["start"][:10]
                        right = meta["params"]["end"][:10]
                        coverage.append((left, right))
                        projected = {
                            s: [r for r in rs if prefix_end <= r["t"][:10] <= formation_end]
                            for s, rs in obj["bars"].items()
                        }
                        objects.append(dict(bars=projected))
                    else:
                        actions.append(obj)
            for row in complete["source_receipts"]:
                bindings.append(row)
            bindings.extend(
                [
                    complete["local"],
                    complete["publication"],
                    load(complete["local"]["path"])["selected_ADV"],
                    binding(Q / "source_receiver.py"),
                    binding(Q / "common.py"),
                ]
            )
    # Complete request ranges, rather than positive-price survivor filtering.
    for left, right in sorted(set(coverage)):
        if left <= (date.fromisoformat(tail) + timedelta(days=1)).isoformat():
            tail = max(
                tail,
                min(formation_end, (date.fromisoformat(right) - timedelta(days=1)).isoformat()),
            )
        else:
            raise ValueError("Gap between received raw source ranges")
    # Multiple capture episodes should not contain duplicate model observations.
    seen = set()
    for obj in objects:
        for s, rs in obj["bars"].items():
            for r in rs:
                key = (s, r["t"])
                assert key not in seen, "Overlapping received raw captures"
                seen.add(key)
    return dict(
        raw=objects,
        actions=actions,
        bindings=bindings,
        tail=tail,
        received_through=received_through,
    )


def discover(cutoff, prefix_end, formation_end):
    rows = []
    for p in sorted((Q / "source-captures").glob("*/complete.json")):
        p = canonical(p)
        obj = load(p)
        if (
            clock(obj["at_utc"]) <= clock(cutoff)
            and obj["day"] >= prefix_end
            and obj["day"] <= formation_end
        ):
            rows.append(binding(p))
    return rows
