# ruff: noqa: E501 -- Exact provenance/clock contract literals.
"""Actual monthly source-to-feature receiver, with canonical completed recovery."""

import json
import os
import uuid

import numpy as np
from features import complete_labels, extend_daily, formation, merge_actions
from receiver_common import (
    HERE,
    REPO,
    SHARE,
    SYMBOLS,
    TASK,
    UNITS,
    absolute_fact_time,
    binding,
    calendar,
    canonical,
    checked,
    clean,
    clock,
    legacy,
    load,
    module,
    now,
    save,
)
from source_contract import receive_sources

RUNTIME = HERE / "received"


def code_bindings():
    paths = [
        HERE / n
        for n in [
            "receiver.py",
            "receiver_common.py",
            "source_contract.py",
            "source_writer.py",
            "retained_sources.py",
            "features.py",
            "source-contract.json",
            "accepted-seed.json",
            "scheduled_base.py",
            "forecast.schema.json",
        ]
    ]
    paths += [SHARE / n for n in ["method.py", "learning.py", "receive_class_witnesses.py"]]
    paths += [
        REPO / "open_composer/market_sessions.py",
        REPO / "open_composer/research/features/price_hygiene.py",
    ]
    paths += [
        TASK / "common.py",
        TASK / "future-interface-repair/scheduled_base.py",
        REPO / "open_composer/research/ml_backend/model_factory.py",
    ]
    from retained_sources import Q

    paths += [Q / "common.py", Q / "source_receiver.py"]
    return [binding(p) for p in paths]


def append_journal(path, row):
    canonical(path)
    with path.open("a") as f:
        f.write(json.dumps(clean(row), allow_nan=False) + "\n")
        f.flush()
        os.fsync(f.fileno())


def seed():
    """Receive accepted derivative prefix identities, not an archive/source replay."""
    obj = load(HERE / "accepted-seed.json")
    manifest = load(checked(obj["accepted_input_manifest"], TASK / "input-manifest.json"))
    assert (
        obj["accepted_input_manifest"]["sha256"]
        == "7406b9521d3f21b495ff0f26b003e3a78e17594a4941a92fb76ac1db26a9224c"
    )
    for row in obj["files"].values():
        checked(row)
        assert row in manifest["files"], "Seed is not an actually accepted input binding"
    return obj


def load_previous(previous):
    if previous == binding(HERE / "accepted-seed.json"):
        s = seed()
        files = s["files"]
        monthly = dict(np.load(checked(files["monthly"]), allow_pickle=False))
        daily = dict(np.load(checked(files["daily"]), allow_pickle=False))
        raw = dict(np.load(checked(files["raw_units"]), allow_pickle=False))
        inherited = dict(np.load(checked(files["inherited"]), allow_pickle=False))
        permutation = [inherited["symbols"].tolist().index(x) for x in SYMBOLS]
        inherited["eligible"] = inherited["eligible"][:, permutation]
        actions = load(checked(files["actions"]))
        assert monthly["symbols"].tolist() == daily["symbols"].tolist() == SYMBOLS
        pending = [i for i, m in enumerate(monthly["months"]) if str(m) in s["pending_months"]]
        assert len(pending) == len(s["pending_months"])
        assert all(not np.isfinite(monthly["label"][i]).any() for i in pending)
        return (
            monthly,
            daily,
            raw,
            inherited,
            actions,
            pending,
            list(files.values()) + [binding(HERE / "accepted-seed.json")],
        )
    checkpoint_path = checked(previous)
    assert checkpoint_path.name == "checkpoint.json"
    old = load(checkpoint_path)
    context = receive_monthly_input(old["context"]["path"], old["source_cutoff"])
    assert context["checkpoint"] == previous
    daily = dict(np.load(checked(old["daily"]), allow_pickle=False))
    monthly = dict(np.load(checked(old["monthly"]), allow_pickle=False))
    raw = dict(
        dates=daily["dates"],
        symbols=daily["all_symbols"],
        raw_close=daily["all_raw_close"],
        raw_open=daily["all_raw_open"],
    )
    derivatives = [
        old["daily"],
        old["monthly"],
        old["actions"],
        binding(checkpoint_path.parent / "context.json"),
        binding(checkpoint_path.parent / "seal.json"),
        binding(checkpoint_path.parent / "journal.jsonl"),
    ]
    return (
        monthly,
        daily,
        raw,
        dict(eligible=daily["eligible"]),
        load(checked(old["actions"])),
        old["pending_rows"],
        context["data_bindings"] + derivatives + [previous],
    )


def unique_bindings(rows):
    unique = {}
    for b in rows:
        assert b["path"] not in unique or unique[b["path"]] == b, "Conflicting consumed identities"
        unique[b["path"]] = b
    return list(unique.values())


def receive_prefix(previous):
    """Receive seed/linked metadata without reconstructing features or targets."""
    if previous == binding(HERE / "accepted-seed.json"):
        s = seed()
        with np.load(checked(s["files"]["monthly"]), allow_pickle=False) as z:
            months = z["months"].tolist()
        assert months[-1] == s["last_formation"]
        pending = [i for i, m in enumerate(months) if m in s["pending_months"]]
        assert [months[i] for i in pending] == s["pending_months"]
        return dict(
            prefix_end=s["prefix_end"],
            last_formation=months[-1],
            months=months,
            pending_rows=pending,
            monthly=s["files"]["monthly"],
            bindings=list(s["files"].values()) + [previous],
        )
    path = checked(previous)
    assert path.name == "checkpoint.json" and path.parent.parent == RUNTIME
    checkpoint = load(path)
    context = receive_monthly_input(
        path.parent / "context.json", calendar(path.parent.name)["source_cutoff"]
    )
    assert context["checkpoint"] == previous
    with np.load(checked(checkpoint["monthly"]), allow_pickle=False) as z:
        months = z["months"].tolist()
    return dict(
        prefix_end=month_dates_last(path.parent.name),
        last_formation=path.parent.name,
        months=months,
        pending_rows=checkpoint["pending_rows"],
        monthly=checkpoint["monthly"],
        bindings=context["data_bindings"]
        + [
            checkpoint["daily"],
            checkpoint["monthly"],
            checkpoint["actions"],
            binding(path.parent / "context.json"),
            binding(path.parent / "seal.json"),
            binding(path.parent / "journal.jsonl"),
            previous,
        ],
    )


def month_dates_last(month):
    from receiver_common import month_dates

    return month_dates(month)[-1]


def receive_completed_closure(context, seal, folder):
    """Same authoritative source+prefix closure on creation and completed reuse."""
    source = receive_sources(checked(context["source_manifest"]), context["source_cutoff"])
    prefix = receive_prefix(context["previous"])
    manifest = source["manifest"]
    month = context["formation_month"]
    assert manifest["previous"] == context["previous"]
    assert manifest["prefix_end"] == prefix["prefix_end"]
    assert month_dates_after(prefix["last_formation"]) == month
    reception = load(canonical(folder / "source-reception.json"))
    assert reception["source_manifest"] == context["source_manifest"]
    assert reception["bindings"] == source["bindings"]
    assert reception["sources_received_through"] == source["sources_received_through"]
    assert reception["raw_coverage"] == source["raw_coverage"]
    assert reception["source_roster"] == UNITS and reception["output_roster"] == SYMBOLS
    checkpoint = load(canonical(folder / "checkpoint.json"))
    assert set(checkpoint) == {
        "formation_month",
        "source_cutoff",
        "context",
        "monthly",
        "daily",
        "actions",
        "previous",
        "pending_rows",
        "completed_pending_rows",
    }
    assert checkpoint["formation_month"] == month
    assert checkpoint["source_cutoff"] == context["source_cutoff"]
    assert checkpoint["previous"] == context["previous"]
    assert checkpoint["context"] == dict(path=str(folder / "context.json"))
    assert checkpoint["monthly"] == context["packet"] == seal["outputs"]["packet.npz"]
    assert checkpoint["daily"] == seal["outputs"]["daily.npz"]
    assert checkpoint["actions"] == seal["outputs"]["actions.json"]
    mature = [
        i
        for i in prefix["pending_rows"]
        if absolute_fact_time(
            clock(calendar(month_dates_after(prefix["months"][i]))["source_cutoff"])
            .date()
            .isoformat()
        )
        < clock(context["source_cutoff"])
        and clock(calendar(month_dates_after(prefix["months"][i]))["source_cutoff"])
        .date()
        .isoformat()
        <= month_dates_last(month)
    ]
    assert checkpoint["completed_pending_rows"] == mature
    expected_pending = [i for i in prefix["pending_rows"] if i not in mature] + [
        len(prefix["months"])
    ]
    assert checkpoint["pending_rows"] == expected_pending
    with np.load(checked(checkpoint["monthly"]), allow_pickle=False) as z:
        assert z["months"].tolist() == prefix["months"] + [month]
        assert z["symbols"].tolist() == SYMBOLS
        assert int(z["label_end"][-1]) == -1 and not np.isfinite(z["label"][-1]).any()
        with np.load(checked(prefix["monthly"]), allow_pickle=False) as original:
            for key in ["primitive", "flags", "turnover", "eligible", "months", "entry"]:
                assert (
                    np.array_equal(z[key][:-1], original[key], equal_nan=True)
                    if np.issubdtype(z[key].dtype, np.number)
                    else np.array_equal(z[key][:-1], original[key])
                ), "Changed frozen monthly prefix: " + key
            old_labels = original["label"]
            finite = np.isfinite(old_labels)
            assert np.array_equal(z["label"][:-1][finite], old_labels[finite])
            assert np.isnan(
                z["label"][:-1][~finite & ~np.isin(np.arange(len(old_labels)), mature)[:, None]]
            ).all()
            dates = z["dates"].tolist()
            ends = original["label_end"].copy()
            for i in mature:
                exit_day = (
                    clock(calendar(month_dates_after(prefix["months"][i]))["source_cutoff"])
                    .date()
                    .isoformat()
                )
                ends[i] = dates.index(exit_day)
            assert np.array_equal(z["label_end"][:-1], ends)
    checked(prefix["monthly"])
    outputs_before_context = [
        seal["outputs"][n]
        for n in [
            "daily.npz",
            "actions.json",
            "checkpoint.json",
            "source-reception.json",
            "feature-reception.json",
            "maturity-reception.json",
        ]
    ]
    expected = unique_bindings(
        prefix["bindings"]
        + source["bindings"]
        + [context["previous"]]
        + context["code_bindings"]
        + outputs_before_context
    )
    assert context["data_bindings"] == expected, "Unreceived/substituted consumed source or prefix"


def receive_monthly_input(context_path, source_cutoff):
    """No decode/relabel/refit on recovery: receive the actual completed source build."""
    context_path = canonical(context_path)
    assert context_path.name == "context.json" and context_path.parent.parent == RUNTIME
    month = context_path.parent.name
    assert source_cutoff == calendar(month)["source_cutoff"]
    context = load(context_path)
    folder = context_path.parent
    journal_path = canonical(folder / "journal.jsonl")
    rows = [json.loads(x) for x in journal_path.read_text().splitlines()]
    seal = load(canonical(folder / "seal.json"))
    assert len(rows) == 2 and [r["event"] for r in rows] == ["started", "completed"], (
        "Orphan/partial/duplicate input invocation"
    )
    keys = [
        "invocation_id",
        "pid",
        "formation_month",
        "source_cutoff",
        "source_manifest",
        "previous",
        "code_bindings",
        "admission",
    ]
    for key in keys:
        assert rows[0][key] == rows[1][key] == context[key] == seal[key]
    assert context["formation_month"] == month and context["source_cutoff"] == source_cutoff
    assert context["code_bindings"] == code_bindings(), "Changed scientific receiver"
    assert rows[1]["seal"] == binding(folder / "seal.json")
    assert seal["context"] == binding(context_path)
    assert context["packet"] == binding(folder / "packet.npz")
    assert context["checkpoint"] == binding(folder / "checkpoint.json")
    assert seal["outputs"] == {
        n: binding(folder / n)
        for n in [
            "packet.npz",
            "daily.npz",
            "actions.json",
            "checkpoint.json",
            "source-reception.json",
            "feature-reception.json",
            "maturity-reception.json",
        ]
    }
    assert context["accepted_recipe"] == binding(TASK / "prepare_package.py")
    assert (
        context["sources_received_through"]
        == load(folder / "source-reception.json")["sources_received_through"]
    )
    assert (
        clock(context["sources_received_through"])
        <= clock(source_cutoff)
        <= clock(rows[0]["started_at"])
        <= clock(context["packet_received_at"])
        <= clock(seal["published_at"])
        <= clock(rows[1]["completed_at"])
        <= clock(now())
    )
    assert clock(rows[1]["completed_at"]) <= clock(calendar(month)["quantity_commit"]), (
        "Late scientific input; no catch-up"
    )
    assert context["data_bindings"] == seal["data_bindings"]
    assert (
        context["source_manifest"] in context["data_bindings"]
        and context["previous"] in context["data_bindings"]
    )
    assert context["data_bindings"] and len({b["path"] for b in context["data_bindings"]}) == len(
        context["data_bindings"]
    )
    for b in context["data_bindings"]:
        checked(b)
    source = load(checked(context["source_manifest"]))
    assert source["formation_month"] == month and source["source_cutoff"] == source_cutoff
    assert (
        not context["future_label_generated"]
        and context["whole_roster"] == SYMBOLS
        and context["source_roster"] == UNITS
    )
    receive_completed_closure(context, seal, folder)
    return context


def build_monthly_input(source_manifest_path, *, admit):
    """One genuinely admitted incremental build; unavailable/partial prefixes refuse."""
    manifest_path = canonical(source_manifest_path)
    manifest_binding = binding(manifest_path)
    manifest = load(manifest_path)
    assert binding(manifest_path) == manifest_binding
    month = manifest["formation_month"]
    cutoff = manifest["source_cutoff"]
    assert cutoff == calendar(month)["source_cutoff"]
    assert month in load(HERE / "source-contract.json")["permitted_formation_months"], (
        "Outside bounded monthly authority"
    )
    folder = RUNTIME / month
    if folder.exists():
        context = receive_monthly_input(folder / "context.json", cutoff)
        assert (
            context["source_manifest"] == binding(manifest_path)
            and context["previous"] == manifest["previous"]
        )
        return folder / "context.json"
    assert clock(cutoff) <= clock(now()) < clock(calendar(month)["quantity_commit"])
    codes = code_bindings()
    fingerprint = json.dumps(codes, sort_keys=True)
    invocation = uuid.uuid4().hex
    admission = admit(manifest_binding, codes, calendar(month), invocation)
    assert (
        admission
        and json.dumps(codes, sort_keys=True) == fingerprint
        and codes == code_bindings()
        and binding(manifest_path) == manifest_binding
    )
    ctx = dict(
        invocation_id=invocation,
        pid=os.getpid(),
        formation_month=month,
        source_cutoff=cutoff,
        source_manifest=manifest_binding,
        previous=manifest["previous"],
        code_bindings=codes,
        admission=admission,
    )
    folder.mkdir(parents=True, exist_ok=False)
    append_journal(folder / "journal.jsonl", dict(**ctx, event="started", started_at=now()))
    # Failed work leaves its started prefix and source bytes. Never silently rebuild it.
    try:
        monthly, old, raw, inherited, old_actions, pending, prefix_bindings = load_previous(
            manifest["previous"]
        )
        assert manifest["prefix_end"] == str(old["dates"][-1])
        assert str(monthly["months"][-1]) < month, (
            "Duplicate/stale formation; no prior-month fallback"
        )
        assert month_dates_after(str(monthly["months"][-1])) == month, "Missing monthly prefix"
        source = receive_sources(manifest_path, cutoff)
        assert binding(manifest_path) == manifest_binding
        source["actions"] = merge_actions(
            old_actions, source["objects"]["actions"], manifest["prefix_end"]
        )
        daily, trigger = extend_daily(old, raw, inherited, source)
        for source_binding in prefix_bindings + source["bindings"]:
            checked(source_binding)
        completed, label_events, completed_rows = complete_labels(monthly, daily, cutoff, pending)
        current, feature_receipt = formation(daily, source)
        packet = {
            k: completed[k]
            for k in [
                "context",
                "symbols",
                "months",
                "primitive",
                "flags",
                "turnover",
                "eligible",
                "label",
                "entry",
                "label_end",
            ]
        }
        packet["dates"] = daily["dates"]
        for k in ["primitive", "flags", "turnover", "eligible"]:
            packet[k] = np.concatenate(
                [packet[k], np.asarray(current[k], dtype=packet[k].dtype)[None]], axis=0
            )
        for k, value in [("months", month), ("entry", len(daily["dates"])), ("label_end", -1)]:
            packet[k] = np.concatenate([packet[k], np.asarray([value], dtype=packet[k].dtype)])
        packet["label"] = np.concatenate([packet["label"], np.full((1, 28), np.nan)])
        # Original features, eligibility and already finite targets remain exact.
        for k in ["primitive", "flags", "turnover", "eligible", "months", "entry"]:
            assert (
                np.array_equal(packet[k][:-1], monthly[k], equal_nan=True)
                if np.issubdtype(packet[k].dtype, np.number)
                else np.array_equal(packet[k][:-1], monthly[k])
            )
        finite = np.isfinite(monthly["label"])
        assert np.array_equal(packet["label"][:-1][finite], monthly["label"][finite])
        assert json.dumps(codes, sort_keys=True) == fingerprint and codes == code_bindings()
        for source_binding in prefix_bindings + source["bindings"]:
            checked(source_binding)
        with legacy(SHARE):
            learning = module("base_receiver_unchanged_fold", SHARE / "learning.py")
            fold = learning.fold(packet, len(packet["entry"]) - 1)
        np.savez_compressed(folder / "packet.npz", **packet)
        np.savez_compressed(folder / "daily.npz", **daily)
        save(folder / "actions.json", source["actions"])
        save(
            folder / "source-reception.json",
            dict(
                source_manifest=manifest_binding,
                source_roster=UNITS,
                output_roster=SYMBOLS,
                sources_received_through=source["sources_received_through"],
                bindings=source["bindings"],
                raw_coverage=source["raw_coverage"],
                source_snapshot_not_historical_PIT=True,
            ),
        )
        save(
            folder / "feature-reception.json",
            dict(
                **feature_receipt,
                fold={k: v for k, v in fold.items() if k not in ["i", "j", "weights"]},
                actual_computed_at=now(),
                prefix_features_preserved=True,
            ),
        )
        save(
            folder / "maturity-reception.json",
            dict(
                completed_pending_slots=label_events,
                original_fee_per_side=0.001,
                original_label_not_quote_exit=True,
                new_formation_label_absent=True,
                actual_computed_at=now(),
            ),
        )
        context_path = folder / "context.json"
        remaining = [i for i in pending if i not in completed_rows] + [len(packet["entry"]) - 1]
        # Checkpoint refers to the canonical context path, not a circular context digest.
        save(
            folder / "checkpoint.json",
            dict(
                formation_month=month,
                source_cutoff=cutoff,
                context=dict(path=str(context_path)),
                monthly=binding(folder / "packet.npz"),
                daily=binding(folder / "daily.npz"),
                actions=binding(folder / "actions.json"),
                previous=manifest["previous"],
                completed_pending_rows=completed_rows,
                pending_rows=remaining,
            ),
        )
        outputs_before_context = [
            binding(folder / n)
            for n in [
                "daily.npz",
                "actions.json",
                "checkpoint.json",
                "source-reception.json",
                "feature-reception.json",
                "maturity-reception.json",
            ]
        ]
        all_bindings = (
            prefix_bindings
            + source["bindings"]
            + [manifest["previous"]]
            + codes
            + outputs_before_context
        )
        all_bindings = unique_bindings(all_bindings)
        context = dict(
            **ctx,
            packet=binding(folder / "packet.npz"),
            checkpoint=binding(folder / "checkpoint.json"),
            accepted_recipe=binding(TASK / "prepare_package.py"),
            data_bindings=all_bindings,
            sources_received_through=source["sources_received_through"],
            packet_received_at=now(),
            future_label_generated=False,
            whole_roster=SYMBOLS,
            source_roster=UNITS,
        )
        save(context_path, context)
        assert clock(now()) < clock(calendar(month)["quantity_commit"]), (
            "Input computation missed commitment"
        )
        outputs = {
            n: binding(folder / n)
            for n in [
                "packet.npz",
                "daily.npz",
                "actions.json",
                "checkpoint.json",
                "source-reception.json",
                "feature-reception.json",
                "maturity-reception.json",
            ]
        }
        save(
            folder / "seal.json",
            dict(
                **ctx,
                context=binding(context_path),
                outputs=outputs,
                data_bindings=all_bindings,
                published_at=now(),
            ),
        )
        append_journal(
            folder / "journal.jsonl",
            dict(**ctx, event="completed", completed_at=now(), seal=binding(folder / "seal.json")),
        )
    except BaseException as exc:
        append_journal(
            folder / "journal.jsonl", dict(**ctx, event="failed", failed_at=now(), error=repr(exc))
        )
        raise
    receive_monthly_input(context_path, cutoff)
    return context_path


def month_dates_after(month):
    year, m = map(int, month.split("-"))
    return f"{year + (m == 12):04d}-{m % 12 + 1:02d}"


def publish_forecast(month, *, admit):
    """Public deterministic forecast slot; never a second fit in another directory."""
    import scheduled_base

    context_path = RUNTIME / month / "context.json"
    receive_monthly_input(context_path, calendar(month)["source_cutoff"])
    return scheduled_base.produce(
        RUNTIME / month / "forecast",
        month,
        context_path,
        receive_monthly_input=receive_monthly_input,
        admit=admit,
    )
