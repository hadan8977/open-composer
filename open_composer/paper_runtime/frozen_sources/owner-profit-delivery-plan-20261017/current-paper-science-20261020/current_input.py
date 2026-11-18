"""Three finite current inputs, reusing accepted history/models by reference.

No labels, fits, account engine or forecast is constructed here. Only explicit
build_input calls may decode arrays, after the real new stage has been admitted.
"""

import ast
import copy
import hashlib
import json
import math
import sys
from contextlib import contextmanager
from datetime import date
from zoneinfo import ZoneInfo

from current_artifacts import receive_historical_artifacts
from current_common import (
    HERE, PARENT, TASK, binding, checked, claim_worker, clock, computing, finish, guard_write,
    load, module, now, receive_input_review, receive_stage, save, snapshot, start,
)
from current_source import FUTURE, OLD_LSTM, SYMBOLS as ETF_SYMBOLS, old_accepted_manifest, receive_sources, sessions

BASE = PARENT / "candidate-contribution/current-initialization-20261019"
H5 = PARENT / "second-swing-learned-paper-20261019"
STUDY = PARENT.parent / "usic-practitioner-research-20261013/complete-decision-system-20261014/economic-results/research-reset-20261016/state-conditioned-opportunity-v1"
H5_SYMBOLS = "AES HCA IDXX HPQ OKE XYL FOX URI AXP EXC CTVA PYPL TYL FISV AFL VRSK PBCT LH TT DXC RE TJX SNA SBUX DLR WMT USB ETR WAT SO IVZ MAA".split()


def optional(value):
    if type(value).__module__.startswith("numpy"):
        return optional(value.tolist())
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, dict):
        return {k: optional(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [optional(v) for v in value]
    return value


def digest(value):
    import numpy as np
    return hashlib.sha256(np.ascontiguousarray(value).tobytes()).hexdigest()


@contextmanager
def future_modules():
    names = ["receiver_common", "source_contract", "retained_sources", "features", "source_writer"]
    old = {n: sys.modules.pop(n, None) for n in names}
    sys.path.insert(0, str(FUTURE))
    try:
        yield
    finally:
        sys.path.pop(0)
        for n in names:
            sys.modules.pop(n, None)
            if old[n] is not None:
                sys.modules[n] = old[n]


def pure(path, name, **namespace):
    assert binding(path) in snapshot()
    nodes = [n for n in ast.parse(path.read_text()).body if isinstance(n, ast.FunctionDef) and n.name == name]
    assert len(nodes) == 1
    exec(compile(ast.fix_missing_locations(ast.Module(body=nodes, type_ignores=[])), str(path), "exec"), namespace)
    return namespace[name]


def old_input(policy):
    inventory = load(HERE / "historical-artifact-inventory.json")
    return load(checked(inventory["policies"][policy]["old_input"]))


def raw_rows(objects, symbols, days, inactive=()):
    rows = {}
    for page in objects:
        assert type(page) is dict and type(page.get("bars")) is dict
        assert set(page["bars"]) <= set(load(HERE / "source-plan.json")["raw_symbols"])
        for symbol, values in page["bars"].items():
            assert type(values) is list
            if symbol not in symbols:
                continue
            for raw in values:
                stamp = clock(raw["t"]).astimezone(ZoneInfo("America/New_York"))
                assert (stamp.hour, stamp.minute, stamp.second, stamp.microsecond) == (0, 0, 0, 0)
                day = stamp.date().isoformat()
                assert day in days and (symbol, day) not in rows
                for field in ["o", "h", "l", "c"]:
                    assert type(raw[field]) in [int, float] and math.isfinite(raw[field]) and raw[field] > 0
                for field in ["v", "n"]:
                    assert type(raw[field]) in [int, float] and math.isfinite(raw[field]) and raw[field] >= 0 and int(raw[field]) == raw[field]
                rows[(symbol, day)] = raw
    for symbol in symbols:
        if symbol in inactive:
            assert not any(s == symbol for s, _ in rows), "Ceased source unit unexpectedly reopened"
        else:
            assert {d for s, d in rows if s == symbol} == set(days), "Missing whole-session current source batch"
            assert all(rows[(symbol, d)]["v"] > 0 and rows[(symbol, d)]["n"] > 0 for d in days), "Ghost active source is missing input"
    return rows


def action_pages(objects, symbols):
    result, ids = {}, set()
    for page in objects:
        assert type(page) is dict and type(page.get("corporate_actions")) is dict, "Mandatory action batch absent"
        for kind, values in page["corporate_actions"].items():
            assert type(kind) is str and type(values) is list
            for raw in values:
                assert type(raw) is dict and type(raw.get("id")) is str and raw["id"]
                symbol = raw.get("symbol") or raw.get("source_symbol") or raw.get("acquiree_symbol") or raw.get("old_symbol")
                assert symbol in load(HERE / "source-plan.json")["raw_symbols"]
                assert raw["id"] not in ids
                ids.add(raw["id"])
                for name in ["process_date", "ex_date", "effective_date", "payable_date", "pay_date", "record_date", "declaration_date"]:
                    if raw.get(name) is not None:
                        assert type(raw[name]) is str and date.fromisoformat(raw[name]).isoformat() == raw[name]
                assert "2026-09-30" <= raw["process_date"] <= "2026-11-14"
                if symbol not in symbols:
                    continue
                day = raw.get("ex_date") or raw.get("effective_date")
                assert day is not None, "An indispensable action requires its actual economic date"
                if kind == "cash_dividends":
                    assert type(raw["rate"]) in [int, float] and math.isfinite(raw["rate"]) and raw["rate"] >= 0
                elif kind in ["forward_splits", "reverse_splits", "unit_splits"]:
                    assert all(type(raw[k]) in [int, float] and math.isfinite(raw[k]) and raw[k] > 0 for k in ["new_rate", "old_rate"])
                elif kind == "spin_offs":
                    assert type(raw["new_symbol"]) is str and raw["new_symbol"]
                    assert all(type(raw[k]) in [int, float] and math.isfinite(raw[k]) and raw[k] > 0 for k in ["new_rate", "source_rate"])
                if "2026-10-19" < day <= "2026-10-20":
                    assert kind == "cash_dividends", "Reference/application raw-unit change requires affected reception"
                result.setdefault(kind, []).append(raw)
    return [{"corporate_actions": result}]


def controls(policy, source):
    """Shared source-linked controls; no feature/model/account computation."""
    previous = old_input(policy)
    days = ["2026-10-16", "2026-10-19"]
    if policy == "BASE":
        symbols = previous["raw_units"]
        raw = raw_rows(source["objects"]["raw-bars"], symbols, days, ["WBA"])
        for symbol in symbols:
            if symbol != "WBA":
                assert raw[(symbol, "2026-10-16")]["c"] == previous["reference_marks"][symbol]
        with future_modules():
            features = module("oct20_base_action_rules", FUTURE / "features.py")
            # Unknown prior action is an affected input gap, not permission to
            # rewrite the already accepted October signal prefix.
            actions = features.merge_actions(previous["actions"], action_pages(source["objects"]["actions"], symbols), "2026-10-16")
        marks = {s: (None if s == "WBA" else float(raw[(s, "2026-10-19")]["c"])) for s in symbols}
        return dict(symbols=previous["symbols"], raw_units=symbols, bars={s: {d: r for (a, d), r in raw.items() if a == s} for s in symbols}, actions=actions, raw_reference_marks=marks)
    if policy == "H5":
        plan = load(H5 / "source-plan.json")
        symbols = plan["raw_symbols"]
        new = raw_rows(source["objects"]["raw-bars"], symbols, days, ["RE", "PBCT"])
        result = copy.deepcopy(previous["controls"])
        for (symbol, day), row in new.items():
            if day == "2026-10-16":
                assert result["bars"][symbol][day] == row, "Changed already accepted physical source row"
            else:
                assert day not in result["bars"][symbol]
                result["bars"][symbol][day] = row
        master = {r["id"]: r for r in load(checked(plan["retained_actions"]))}
        master.update({r["id"]: r for r in result["actions"]})
        amendment = load(checked(previous["amendment"]))
        known_overlay = {cell["new_received_event"]["id"]: cell["new_received_event"] for cell in amendment["overlay_cells"]}
        for page in action_pages(source["objects"]["actions"], symbols):
            for kind, values in page["corporate_actions"].items():
                for raw in values:
                    event = dict(id=raw["id"], kind=kind, raw=raw, economic_date=raw.get("ex_date") or raw.get("effective_date"))
                    if event["id"] in master:
                        assert all(master[event["id"]][k] == event[k] for k in event), "Changed accepted H5 action vintage"
                    elif event["economic_date"] <= "2026-10-16":
                        assert kind == "cash_dividends" and known_overlay.get(event["id"]) == raw, "New old-period event requires affected reception"
                    master[event["id"]] = event
        result["actions"] = [a for a in master.values() if "2026-09-30" <= a["economic_date"] <= "2026-11-14"]
        result["source_consumed"] = source["consumed"]
        result["source_completed_at"] = source["completed_at"]
        active = [s for s in symbols if s not in ["RE", "PBCT", "MTB"]]
        result["raw_reference_marks"] = {s: float(new[(s, "2026-10-19")]["c"]) for s in active}
        return result
    assert policy == "LSTM"
    raw = raw_rows(source["objects"]["raw-bars"], ETF_SYMBOLS, days)
    rights = action_pages(source["objects"]["actions"], ETF_SYMBOLS)[0]["corporate_actions"]
    assert all(k in ["cash_dividends", "forward_splits", "reverse_splits", "unit_splits"] for k in rights), "Unsupported ETF identity/entitlement"
    for s in ETF_SYMBOLS:
        assert raw[(s, "2026-10-16")]["c"] == previous["raw_reference_marks"][s]
    return dict(symbols=ETF_SYMBOLS, raw_units=ETF_SYMBOLS,
                bars={s: {d: raw[(s, d)] for d in days} for s in ETF_SYMBOLS},
                actions=[dict(kind=k, terms=r) for k, rs in rights.items() for r in rs],
                raw_reference_marks={s: float(raw[(s, "2026-10-19")]["c"]) for s in ETF_SYMBOLS})


def base_input(source, control, provenance):
    computing("input/BASE")
    import numpy as np
    previous = old_input("BASE")
    # Adopt the exact seed/data paths already consumed by the accepted old
    # input. A newer file at the same path is never an implicit vintage update.
    for row in previous["data_bindings"]:
        checked(row)
    assert binding(FUTURE / "accepted-seed.json") in previous["data_bindings"]
    with future_modules():
        receiver = module("oct20_base_seed", FUTURE / "receiver.py")
        retained = module("oct20_base_retained", FUTURE / "retained_sources.py")
        common = module("oct20_base_seed_common", FUTURE / "receiver_common.py")
        seed = receiver.seed()
        assert all(row in previous["data_bindings"] for row in seed["files"].values())
        monthly, old, physical, inherited, _, _, _ = receiver.load_previous(binding(FUTURE / "accepted-seed.json"))
        capture = load(BASE / "prospective-contract.json")["current_source"]["retained_raw_capture"]
        historical = retained.receive_retained([capture], "2026-10-19T13:30:00Z", seed["prefix_end"], "2026-10-16")
        bars = {s: {} for s in common.UNITS}
        for page in historical["raw"]:
            for s, rs in page["bars"].items():
                for r in rs:
                    day = clock(r["t"]).astimezone(ZoneInfo("America/New_York")).date().isoformat()
                    assert day not in bars[s]
                    bars[s][day] = r
        for s, rows in control["bars"].items():
            for day, row in rows.items():
                if day in bars[s]:
                    assert bars[s][day] == row, "Changed accepted raw OPEN/CLOSE/volume/count context"
                else:
                    bars[s][day] = row
        bridge = module("oct20_base_daily_bridge", BASE / "bridge.py")
        daily, triggers = bridge.extend_daily(old, physical, inherited, dict(manifest=dict(reference_day="2026-10-19", prefix_end=seed["prefix_end"]), objects={"raw-bars": [dict(bars={s: list(rs.values()) for s, rs in bars.items()})]}, actions=control["actions"]))
        assert daily["dates"][-1] == "2026-10-19"
        assert monthly["months"][-1] == "2026-09"
        for key, field in [("primitive", "primitive"), ("flags", "flags"), ("turnover", "turnover"), ("formation_eligible", "eligible")]:
            assert optional(monthly[field][-1]) == previous[key]
        current_eligible = daily["eligible"][-1]
        assert optional({s: float(daily["all_raw_close"][-1, j]) for j, s in enumerate(common.UNITS)}) == control["raw_reference_marks"]
        eligible = np.asarray(previous["formation_eligible"], dtype=bool) & current_eligible
        consumed = historical["bindings"] + list(seed["files"].values()) + [binding(FUTURE / "accepted-seed.json")]
    ages = copy.deepcopy(previous["count_ages"])
    for row in ages:
        if row["current_calendar_age"] is not None:
            row["current_calendar_age"] += 1
    state = load(checked(provenance["adopted"]["model"]))
    prior_common = module("oct20_base_legacy_imports", BASE.parent / "common.py")
    share = PARENT.parent / "share-turnover-information-20261017"
    with prior_common.legacy(share):
        method = module("oct20_base_exact_design", share / "method.py")
        design, _, _ = method.train_design(np.asarray(previous["primitive"], dtype=float),
                                           np.asarray(previous["flags"], dtype=float),
                                           np.asarray(previous["turnover"], dtype=float), np.ones(28), state=state["primitive_state"])
    assert design.shape == (28, 14) and np.isfinite(design).all()
    return dict(symbols=previous["symbols"], observation_month="2026-09", feature_observation_end=previous["feature_observation_end"],
                primitive=previous["primitive"], flags=previous["flags"], turnover=previous["turnover"], formation_eligible=previous["formation_eligible"],
                current_daily_eligible=current_eligible, eligible=eligible, current_split_jump_triggers=triggers[-1],
                model_design=design, model_design_sha256=digest(design),
                count_ages=ages, consumed=consumed, no_new_fit_labels_or_accounts=True)


def h5_input(source, control, provenance):
    computing("input/H5")
    import numpy as np
    previous = old_input("H5")
    old_plan = load(H5 / "source-plan.json")
    extended_plan = dict(old_plan, expected_sessions=sessions("2026-09-30", "2026-10-19"))
    def plan_load(path):
        return extended_plan if path == H5 / "source-plan.json" else load(path)
    extend = pure(H5 / "h5_input.py", "extend_signal", load=plan_load, HERE=H5, checked=checked, SYMBOLS=H5_SYMBOLS)
    returns, available, details, breaks = extend(control)
    old_details = [r for r in details if r["day"] <= "2026-10-16"]
    assert optional(old_details) == previous["connected_tail"], "Already accepted connected October prefix changed"
    overlay = pure(H5 / "h5_input.py", "current_window_overlay", SYMBOLS=H5_SYMBOLS)
    amendment = load(checked(previous["amendment"]))
    with np.load(checked(old_plan["accepted_prepared"]), allow_pickle=False) as data:
        # Only accepted past return/support arrays; no labels, fold selection,
        # training matrix construction or model fit is repeated.
        r, spy, overlay_audit = overlay(data["dates"][-252:], data["returns"][-252:], data["benchmark_SPY"][-252:], amendment)
        a = data["available"][-252:]
    method = module("oct20_original_h5_features", STUDY / "method.py")
    feature = method.features(np.r_[r, returns[:, :32]], np.r_[a, available[:, :32]], np.r_[spy, returns[:, 32]])
    return dict(symbols=H5_SYMBOLS, current_stock=feature["stock"][-1], current_state=feature["state"][-1], eligible=feature["eligible"][-1],
                connected_tail=details, hygiene_breaks=breaks, current_window_overlay=overlay_audit,
                train_current_vintage_mismatch=True, amendment=previous["amendment"], child_source=previous["child_source"],
                child_source_complete=previous["child_source_complete"], training=previous["training"], training_audit=previous["training_audit"],
                episode_carriers=control["carriers"], consumed=[old_plan["accepted_prepared"], old_plan["retained_dated_raw"], old_plan["retained_actions"]],
                initialization_mode="new_current_day_initialization", off_phase=True, phase_anchor="2024-01-02", phase_mod5=1,
                next_regular_observation="2026-10-23", next_regular_application="2026-10-26")


def lstm_input(source, control, provenance):
    computing("input/LSTM")
    import numpy as np
    import pandas as pd
    from open_composer.research.features.price_hygiene import sanitize_price_matrices
    local = source["local"]
    tail = sessions("2026-10-01", "2026-10-19")
    adjusted = dict(local["rows"])
    if local["missing"]:
        expected = sessions("2026-09-28", "2026-10-19")
        rows = raw_rows(source["objects"]["adjusted-tail"], ETF_SYMBOLS, expected)
        fetched = {s + ":" + d: dict(symbol=s, day=d, open=r["o"], close=r["c"]) for (s, d), r in rows.items()}
        for key, previous in {**local["request_overlap_rows"], **local["rows"]}.items():
            for name in ["open", "close"]:
                assert key in fetched and np.isclose(fetched[key][name] / previous[name], 1, rtol=1e-7, atol=1e-8), "Conditional adjusted source drift"
        adjusted.update({k: v for k, v in fetched.items() if v["day"] in tail})
    assert set(adjusted) == {s + ":" + d for s in ETF_SYMBOLS for d in tail}
    old_local = load(checked(local["previous_local"]))
    for s in ETF_SYMBOLS:
        k = local["adjustment_factors"][s]["multiplier"]
        old_k = old_local["adjustment_factors"][s]["multiplier"]
        for d in sessions("2026-10-01", "2026-10-16"):
            for name in ["open", "close"]:
                key = s + ":" + d
                assert np.isclose((adjusted[key][name] / k) / (old_local["rows"][key][name] / old_k), 1, rtol=1e-7, atol=1e-8)
    original = PARENT.parent / "return-line-replenishment-20261016/direct-position-learning-20261016"
    files = {r["path"]: r for r in old_accepted_manifest()["files"]}
    accepted = {name: files[str(original / name)] for name in ["ETF-sanitized-close.parquet", "ETF-sanitized-open.parquet", "source-features.npz"]}
    close = pd.read_parquet(checked(accepted["ETF-sanitized-close.parquet"]))[ETF_SYMBOLS]
    opening = pd.read_parquet(checked(accepted["ETF-sanitized-open.parquet"]))[ETF_SYMBOLS]
    prefix = len(close)
    for d in tail:
        close.loc[pd.Timestamp(d)] = [adjusted[s + ":" + d]["close"] / local["adjustment_factors"][s]["multiplier"] for s in ETF_SYMBOLS]
        opening.loc[pd.Timestamp(d)] = [adjusted[s + ":" + d]["open"] / local["adjustment_factors"][s]["multiplier"] for s in ETF_SYMBOLS]
    clean, cleanopen, qa = sanitize_price_matrices(close, opening)
    assert np.array_equal(clean.to_numpy(), close.to_numpy(), equal_nan=True) and np.array_equal(cleanopen.to_numpy(), opening.to_numpy(), equal_nan=True)
    assert not any(str(b.first_session_after.date()) >= "2026-10-01" for b in qa.breaks)
    features = module("oct20_lstm_original_features", original / "prepare_features.py")
    x, vol, _ = features.features(clean)
    with np.load(checked(accepted["source-features.npz"]), allow_pickle=False) as prior:
        assert prefix == 2701 and np.array_equal(x[:prefix], prior["features"], equal_nan=True)
        assert np.array_equal(vol[:prefix], prior["vol"], equal_nan=True)
    dates = close.index.strftime("%Y-%m-%d").to_numpy(dtype="U10")
    assert dates.tolist() == sessions("2016-01-04", "2026-10-19")
    first = int(np.flatnonzero(dates == "2026-01-02")[0])
    assert len(dates[first:]) == 200
    lo = first - 63
    valid = np.isfinite(x).all(-1) & np.isfinite(vol) & (vol > 1e-8)
    assert valid[lo:].all(), "Missing current/recurrent core support cannot be learned cash"
    raw_days = ["2026-10-16", "2026-10-19"]
    raw_close = pd.DataFrame([[control["bars"][s][d]["c"] for s in ETF_SYMBOLS] for d in raw_days], index=pd.to_datetime(raw_days), columns=ETF_SYMBOLS)
    raw_open = pd.DataFrame([[control["bars"][s][d]["o"] for s in ETF_SYMBOLS] for d in raw_days], index=pd.to_datetime(raw_days), columns=ETF_SYMBOLS)
    _, _, raw_qa = sanitize_price_matrices(raw_close, raw_open)
    assert not raw_qa.breaks, "Current physical raw-unit hygiene conflict"
    guard_write()
    path = HERE / "input/LSTM/sequence.npz"
    with path.open("xb") as f:
        np.savez_compressed(f, dates=dates[lo:], features=x[lo:], vol=vol[lo:], valid=valid[lo:], first_2026=np.array(63))
        f.flush()
        import os
        os.fsync(f.fileno())
    return dict(symbols=ETF_SYMBOLS, sequence=binding(path), sequence_feature_sha256=digest(x[lo:]), sequence_vol_sha256=digest(vol[lo:]), sequence_valid_sha256=digest(valid[lo:]),
                original_accepted=accepted, original_prefix_rows=2701, original_prefix_bitexact=True,
                model_context=provenance["adopted"]["original_contexts"], recurrent_burnin_sessions=63, annual_sessions=200,
                current_vol=vol[-1], current_features=x[-1],
                current_eligible=[True] * 10, adjustment_factors=local["adjustment_factors"], hygiene=qa.manifest(), raw_hygiene=raw_qa.manifest(),
                consumed=list(accepted.values()) + local["consumed"], new_labels=0, fits=0)


def build_input(policy):
    assert policy in ["BASE", "H5", "LSTM"]
    stage = "input/" + policy
    if (HERE / stage / "completed.json").exists():
        return receive_input(policy)
    s = start(stage, binding(HERE / "source/output.json"))
    claim = claim_worker(stage)
    source = receive_sources()
    assert clock(source["completed_at"]) <= clock(s["started_at"])
    provenance = receive_historical_artifacts(policy)
    control = controls(policy, source)
    function = {"BASE": base_input, "H5": h5_input, "LSTM": lstm_input}[policy]
    value = function(source, control, provenance)
    value.update(policy=policy, reference_day="2026-10-19", reference_at="2026-10-19T20:00:00Z", application_day="2026-10-20",
                 source=binding(HERE / "source/output.json"), source_complete=binding(HERE / "source/completed.json"), source_completed_at=source["completed_at"],
                 controls=control, raw_reference_marks=control["raw_reference_marks"], current_actions=control["actions"],
                 historical_model_provenance=provenance, computed_started_at=claim["claimed_at"], computed_completed_at=now())
    return finish(stage, optional(value))


def receive_input(policy, require_peer=True):
    assert policy in ["BASE", "H5", "LSTM"]
    result = receive_stage("input/" + policy)
    assert result["policy"] == policy and result["reference_day"] == "2026-10-19" and result["application_day"] == "2026-10-20"
    assert result["source"] == binding(HERE / "source/output.json") and result["source_complete"] == binding(HERE / "source/completed.json")
    source = receive_sources()
    assert result["source_completed_at"] == source["completed_at"]
    expected_controls = controls(policy, source)
    assert result["controls"] == expected_controls
    assert result["raw_reference_marks"] == expected_controls["raw_reference_marks"] and result["current_actions"] == expected_controls["actions"]
    assert result["historical_model_provenance"] == receive_historical_artifacts(policy)
    if policy == "BASE":
        previous = old_input(policy)
        for key in ["primitive", "flags", "turnover", "formation_eligible"]:
            assert result[key] == previous[key]
        assert len(result["eligible"]) == 28 and all(type(v) is bool for v in result["eligible"])
        assert result["eligible"] == [a and b for a, b in zip(result["formation_eligible"], result["current_daily_eligible"], strict=True)]
        assert result["eligible"][result["symbols"].index("WBA")] is False
    elif policy == "H5":
        previous = old_input(policy)
        assert result["training"] == previous["training"] and result["training_audit"] == previous["training_audit"]
        assert result["train_current_vintage_mismatch"] is True and result["off_phase"] is True
        assert result["amendment"] == previous["amendment"] and result["child_source"] == previous["child_source"]
        assert len(result["eligible"]) == len(result["current_stock"]) == len(result["current_state"]) == 32
        assert all(type(v) is bool for v in result["eligible"])
        assert all(len(v) == 9 for v in result["current_stock"]) and all(len(v) == 21 for v in result["current_state"])
        assert result["eligible"][H5_SYMBOLS.index("PBCT")] is False
    else:
        import numpy as np
        with np.load(checked(result["sequence"], HERE / "input/LSTM/sequence.npz"), allow_pickle=False) as z:
            assert set(z.files) == {"dates", "features", "vol", "valid", "first_2026"}
            assert z["features"].shape == (263, 10, 8) and z["vol"].shape == z["valid"].shape == (263, 10)
            assert z["features"].dtype == z["vol"].dtype == np.dtype("float64") and z["valid"].dtype == np.dtype("bool")
            assert z["first_2026"].dtype == np.dtype("int64") and z["first_2026"].shape == () and int(z["first_2026"]) == 63
            calendar = sessions("2025-01-02", "2026-10-19")
            first = calendar.index("2026-01-02")
            assert z["dates"].dtype == np.dtype("U10") and z["dates"].shape == (263,) and z["dates"].tolist() == calendar[first - 63:]
            assert np.isfinite(z["features"]).all() and np.isfinite(z["vol"]).all() and (z["vol"] > 1e-8).all() and z["valid"].all()
            assert digest(z["features"]) == result["sequence_feature_sha256"] and digest(z["vol"]) == result["sequence_vol_sha256"] and digest(z["valid"]) == result["sequence_valid_sha256"]
            assert z["vol"][-1].tolist() == result["current_vol"] and z["features"][-1].tolist() == result["current_features"]
        assert result["recurrent_burnin_sessions"] == 63 and result["annual_sessions"] == 200
        assert result["model_context"] == result["historical_model_provenance"]["adopted"]["original_contexts"]
        assert result["new_labels"] == result["fits"] == 0
    if require_peer:
        receive_input_review(policy, binding(HERE / f"independent-current-input-review-{policy}.json"), binding(HERE / "input" / policy / "output.json"))
    return result
