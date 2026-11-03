# ruff: noqa: E501 -- Historical evidence paths and exact audit literals.
"""Original H5 formation and explicit monthly boundaries; no fit or account API."""

import ast
import copy
import gzip
import hashlib
import json
import math
import struct
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from open_composer.market_sessions import us_equity_session_close, us_equity_session_dates
from open_composer.paper_runtime.paths import runtime_root
from open_composer.paper_runtime.six.paper_target_input_controls import (
    REPO,
    T,
    binding,
    checked,
    load,
)
from open_composer.paper_runtime.source_loader import source_bytes

P = T.parent
H5 = P / "second-swing-learned-paper-20261019"
STUDY = (
    REPO
    / "reports/research/program/usic-practitioner-research-20261013/complete-decision-system-20261014/economic-results/research-reset-20261016/state-conditioned-opportunity-v1"
)
ORIGINALS = {
    "input": (
        H5 / "h5_input.py",
        "1606b47723d902b2e9caf437da8de71d58e6335b6342ac036e345c8d48f9f9e8",
    ),
    "models": (
        H5 / "h5_models.py",
        "f396543fdb4bc86a73f83ecf79b6c8916ab7a53381cd54f27711dd9a57e46dc9",
    ),
    "math": (
        T / "current_math.py",
        "780711676f2624594baa3e7c25afbe368eba816cdf90bf3fa21058369d5a478e",
    ),
    "features": (
        STUDY / "method.py",
        "9edaab9f54acd9b646ed6dec16f49a46fb518d1f4f82d3e643ed24ce3d3806e5",
    ),
}


class FormationDependency(ValueError):
    """Missing/unreceived method support, never a K0 or funded no-trade result."""


def require(condition, reason):
    if not condition:
        raise FormationDependency(reason)


def receive_previous():
    path = T / "input/H5/output.json"
    review = load(T / "independent-current-input-review-H5.json")
    assert review["policy"] == "H5" and review["independent"] is True
    assert review["reviewer"] == "93af0483-230a-4632-8b48-c63cd53a01f7"
    assert review["source_linked_controls_accepted"] is True
    assert review["target"] == review["derived_control_witness"] == binding(path)
    return load(path)


def formation_plan(previous):
    trusted = receive_previous()
    plan = load(H5 / "source-plan.json")
    assert previous["historical_model_provenance"] == trusted["historical_model_provenance"]
    assert previous["amendment"] == trusted["amendment"]
    assert all(
        plan[key] in trusted["consumed"]
        for key in ["accepted_prepared", "retained_dated_raw", "retained_actions"]
    )
    return plan


def pure(which, names, **namespace):
    path, sha = ORIGINALS[which]
    assert hashlib.sha256(source_bytes(path, root=REPO)).hexdigest() == sha
    if isinstance(names, str):
        names = [names]
    tree = ast.parse(source_bytes(path, root=REPO))
    nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names]
    assert {n.name for n in nodes} == set(names)
    if which == "features":
        # The original feature body also uses the original declared name lists.
        constants = [
            n
            for n in tree.body
            if isinstance(n, ast.Assign)
            and any(
                isinstance(t, ast.Name) and t.id in ["STOCK", "STATE", "INTERACTIONS"]
                for t in n.targets
            )
        ]
        nodes = constants + nodes
    exec(
        compile(
            ast.fix_missing_locations(ast.Module(body=nodes, type_ignores=[])), str(path), "exec"
        ),
        namespace,
    )
    return namespace[names[-1]]


def phase(reference_day):
    """The original every-five-session anchor, not a weekday approximation."""
    end = date.fromisoformat(reference_day)
    calendar = us_equity_session_dates(date(2024, 1, 2), end + timedelta(days=20))
    require(end in calendar, "H5 reference is not a completed regular session")
    n = calendar.index(end)
    latest = n - n % 5
    return dict(
        anchor="2024-01-02",
        latest=calendar[latest].isoformat(),
        next_observation=calendar[latest + 5].isoformat(),
        next_application=calendar[latest + 6].isoformat(),
    )


def origin(row=None):
    """Receive an immutable signal, distinct from the mutable daily instruction."""
    if row is None:
        require(
            (runtime_root(REPO) / "targets/H5.json").exists(),
            "Current H5 signal instruction is absent",
        )
        target = load(runtime_root(REPO) / "targets/H5.json")
        row = target.get("signal_forecast", target.get("held_model_origin"))
    require(isinstance(row, dict), "H5 signal origin is absent")
    require(Path(row["path"]).exists(), "H5 immutable signal forecast is missing")
    signal = load(checked(row))
    require(signal.get("policy") == "H5", "Foreign H5 signal origin")
    day = signal.get("signal_observation", signal.get("reference_day"))
    require(
        day is not None and date.fromisoformat(day).isoformat() == day,
        "Missing genuine H5 observation",
    )
    require(signal["symbols"] == receive_previous()["symbols"], "H5 episode roster differs")
    if Path(row["path"]) != T / "inference/H5/output.json":
        previous = receive_previous()
        require(
            signal["models"] == previous["historical_model_provenance"]["adopted"]["states"],
            "Foreign H5 formation models",
        )
        require(
            signal["model_epoch"] == day[:7] == "2026-10"
            and signal["model_cutoff"] == "2026-09-30",
            "Unsupported H5 model month/cutoff",
        )
        captured = load(checked(signal["source"]))
        features = load(checked(signal["input"]))
        require(
            captured["reference_day"] == day
            and captured["application_day"] == signal["signal_application"],
            "H5 formation source dates differ",
        )
        require(
            features["source"] == signal["source"],
            "H5 features are not linked to their actual source",
        )
        actions = load(checked(features["action_lineage"]))
        controls = load(checked(features["current_controls"]))
        require(
            actions["current_source"] == signal["source"]
            and controls["source"] == signal["source"],
            "H5 action/unit controls have foreign source lineage",
        )
        require(
            controls["reference_day"] == day
            and controls["application_day"] == signal["signal_application"],
            "H5 control observation/application differs",
        )
        require(
            features["reference_day"] == day
            and features["support_sessions"]
            == [
                d.isoformat()
                for d in us_equity_session_dates(date(2026, 9, 30), date.fromisoformat(day))
            ],
            "Incomplete H5 connected input calendar",
        )
        require(
            features["amendment"] == previous["amendment"]
            and features["original_prepared"] == formation_plan(previous)["accepted_prepared"],
            "H5 original return/overlay support changed",
        )
        require(
            datetime.fromisoformat(captured["captured_at"].replace("Z", "+00:00"))
            <= datetime.fromisoformat(signal["computed_started_at"])
            <= datetime.fromisoformat(signal["computed_completed_at"]),
            "H5 computation precedes source completion",
        )
        # Saved-only scalar verification: no feature builder, fit or prediction API.
        scores, allocation = infer(features, states(previous))
        require(set(signal["scores"]) == set(scores), "H5 original score arms differ")
        for arm in scores:
            received = signal["scores"][arm]
            expected = scores[arm]
            require(len(received) == len(expected) == 32, "H5 incomplete scalar score roster")
            require(
                all(
                    a is None
                    and b is None
                    or type(a) is float
                    and type(b) is float
                    and struct.pack(">d", a) == struct.pack(">d", b)
                    for a, b in zip(received, expected, strict=True)
                ),
                "H5 scores differ from exact frozen states and stored features",
            )
        require(
            signal["allocation"] == allocation,
            "H5 allocation differs from received original scores",
        )
    return row, signal, day


def source_contract(reference_day, application_day, origin_row=None):
    try:
        row, signal, observed = origin(origin_row)
    except FormationDependency:
        # Data-request planning may use the original receipt conservatively.
        # h5_decision still requires the actual current instruction; no adoption.
        if origin_row is not None:
            raise
        row, signal, observed = origin(binding(T / "inference/H5/output.json"))
    p = phase(reference_day)
    calendar = us_equity_session_dates(
        date.fromisoformat(reference_day) - timedelta(days=12), date.fromisoformat(application_day)
    )
    require(
        calendar[-2].isoformat() == reference_day and calendar[-1].isoformat() == application_day,
        "Not the actual preceding-session application",
    )
    require(observed <= reference_day, "Future H5 signal origin")
    due = p["latest"] > observed
    raw_start = calendar[-3].isoformat()
    if application_day[:7] == "2026-10":
        # Original BASE bridge is anchored at Oct19, not at the preceding daily packet.
        raw_start = min(raw_start, "2026-10-19")
    elif application_day[:7] == "2026-11":
        # Current BASE daily eligibility continues from the received October
        # monthly prefix, not from the old September seed or just two last days.
        raw_start = min(raw_start, "2026-10-30")
    if due and p["latest"][:7] == "2026-10":
        raw_start = "2026-09-30"
    return dict(
        reference_day=reference_day,
        application_day=application_day,
        h5_origin=row,
        original_observation=observed,
        phase=p,
        formation_due=due,
        raw_support_start=raw_start,
        original_model_epoch="2026-10",
    )


def request_menu(plan, contract):
    assert (
        source_contract(
            contract["reference_day"], contract["application_day"], contract["h5_origin"]
        )
        == contract
    )
    menu = [(g, copy.deepcopy(r)) for g in ["core", "ETF"] for r in plan[g]["requests"]]
    tail = copy.deepcopy(plan["core"]["conditional_request"])
    tail.pop("condition")
    menu.append(("core", tail))
    calendar = us_equity_session_dates(
        date.fromisoformat(contract["reference_day"]) - timedelta(days=12),
        date.fromisoformat(contract["application_day"]),
    )
    previous = calendar[-3].isoformat()
    app = contract["application_day"]
    for group, row in menu:
        if row["key"] in ["raw-bars", "raw-reference"]:
            start = contract["raw_support_start"] if group == "core" else previous
            row["params"].update(start=start + "T00:00:00Z", end=app + "T00:00:00Z")
        elif row["key"] in ["adjusted-tail", "adjusted-history"]:
            row["params"]["end"] = app + "T00:00:00Z"
    return menu


def monthly_base_supported(application_day):
    if application_day[:7] == "2026-10":
        return None
    from open_composer.paper_runtime.six.monthly_base_model import receive_current_model

    try:
        forecast_binding, _ = receive_current_model(root=REPO, application_day=application_day)
        return forecast_binding
    except (AssertionError, KeyError, ValueError, FileNotFoundError) as error:
        raise FormationDependency(
            "BASE requires a genuinely received November monthly design/model; "
            "October scores cannot be held forever: " + str(error)
        ) from error


def states(previous):
    adopted = previous["historical_model_provenance"]["adopted"]
    assert adopted == receive_previous()["historical_model_provenance"]["adopted"]
    result = {}
    for arm, row in zip(["STOCK", "STATE"], adopted["states"], strict=True):
        assert Path(row["path"]) == H5 / "models" / (arm + ".json.gz")
        value = json.loads(gzip.decompress(checked(row).read_bytes()))
        assert value["context"] == adopted["exact_inner_contexts"][arm]
        assert value["context"]["epoch"] == "2026-10" and value["context"]["cutoff"] == "2026-09-30"
        assert all(
            value["actual_params"][k] == v for k, v in value["context"]["parameters"].items()
        )
        result[arm] = value
    return result


def feature_input(previous, raw, events, reference_day):
    """Exact accepted connected-return/overlay/features, with no labels or training."""
    import numpy as np
    import pandas as pd

    symbols = previous["symbols"]
    controls = copy.deepcopy(previous["controls"])
    require(all(day <= reference_day for _, day in raw), "Future raw row in H5 feature support")
    calendar = [
        d.isoformat()
        for d in us_equity_session_dates(date(2026, 9, 30), date.fromisoformat(reference_day))
    ]
    carriers = controls["carriers"]
    bars = {s: {} for s in controls["bars"]}
    active = [carriers[s] for s in symbols if carriers[s] is not None] + ["MTB", "SPY"]
    for s in set(active):
        for day in calendar:
            require((s, day) in raw, "H5 missing complete connected raw support: " + s + "/" + day)
            bars[s][day] = copy.deepcopy(raw[s, day])
            stamp = datetime.fromisoformat(raw[s, day]["t"].replace("Z", "+00:00"))
            require(stamp.tzinfo is not None, "H5 raw timestamp is naive")
            local = stamp.astimezone(ZoneInfo("America/New_York"))
            require(
                local.date().isoformat() == day
                and (local.hour, local.minute, local.second, local.microsecond) == (0, 0, 0, 0),
                "H5 non-daily source stamp",
            )
            require(raw[s, day]["v"] > 0 and raw[s, day].get("n", 0) > 0, "H5 ghost raw support")
    # Exact previously received distributed-child mark; never a new tradable child.
    bars["VYLR"] = copy.deepcopy(controls["bars"]["VYLR"])
    controls.update(
        bars=bars,
        actions=[
            dict(
                id=e["id"],
                kind=e["kind"],
                raw=copy.deepcopy(e["terms"]),
                economic_date=e["economic_date"],
            )
            for e in events
        ],
    )
    old_plan = load(H5 / "source-plan.json")
    extended = dict(old_plan, expected_sessions=calendar)

    def plan_load(path):
        return extended if path == H5 / "source-plan.json" else load(path)

    extend = pure(
        "input", "extend_signal", load=plan_load, HERE=H5, checked=checked, SYMBOLS=symbols
    )
    try:
        r, a, details, breaks = extend(controls)
    except (AssertionError, ValueError, KeyError) as error:
        raise FormationDependency("H5 original connected support refused: " + str(error)) from error
    frozen = [v for v in details if v["day"] <= "2026-10-19"]
    require(
        frozen == previous["connected_tail"],
        "H5 accepted connected-return prefix changed; preserve source for affected reception",
    )
    overlay = pure("input", "current_window_overlay", SYMBOLS=symbols)
    with np.load(checked(old_plan["accepted_prepared"]), allow_pickle=False) as seed:
        rr, spy, audit = overlay(
            seed["dates"][-252:],
            seed["returns"][-252:],
            seed["benchmark_SPY"][-252:],
            load(checked(previous["amendment"])),
        )
        available = seed["available"][-252:]
    original = pure("features", ["rolling_return", "trailing_drawdown", "features"], np=np, pd=pd)
    result = original(np.r_[rr, r[:, :32]], np.r_[available, a[:, :32]], np.r_[spy, r[:, 32]])

    def finite(rows):
        return [[float(x) if math.isfinite(float(x)) else None for x in row] for row in rows]

    return dict(
        symbols=symbols,
        current_stock=finite(result["stock"][-1]),
        current_state=finite(result["state"][-1]),
        eligible=[bool(x) for x in result["eligible"][-1]],
        reference_day=reference_day,
        support_sessions=calendar,
        connected_tail=details,
        hygiene_breaks=breaks,
        overlay=audit,
        amendment=previous["amendment"],
        original_prepared=old_plan["accepted_prepared"],
        historical_model_provenance=previous["historical_model_provenance"],
        train_current_vintage_mismatch=True,
        new_labels=0,
        new_fits=0,
    )


def infer(features, retained_states):
    assert sys.version_info[:2] == (3, 11), "Original H5 scalar arithmetic runtime required"
    matrix = pure("math", "h5_matrix", math=math)
    predict = pure("models", "scalar_predictions")
    allocate = pure("models", "allocate")
    scores = {}
    for arm in ["STOCK", "STATE"]:
        rows = matrix(features, retained_states[arm], arm)
        values = iter(
            predict(
                retained_states[arm]["tree_dump"],
                [r for r, yes in zip(rows, features["eligible"], strict=True) if yes],
            )
        )
        scores[arm] = [next(values) if yes else None for yes in features["eligible"]]
    return scores, allocate(scores["STOCK"], scores["STATE"], features["eligible"])


def h5_decision(
    previous, current, raw, events, reference_day, application_day, *, write, root, now
):
    row, old, observed = origin()
    p = phase(reference_day)
    source_contract(reference_day, application_day, row)
    close = us_equity_session_close(date.fromisoformat(reference_day))
    require(close is not None, "H5 unsupported observation session")
    completed = datetime.combine(
        date.fromisoformat(reference_day), close, tzinfo=ZoneInfo("America/New_York")
    ).astimezone(UTC)
    require(
        datetime.fromisoformat(now().replace("Z", "+00:00")) >= completed,
        "H5 observation has not completed",
    )
    require(observed <= reference_day, "Future H5 signal cannot be adopted")
    latest = p["latest"]
    if latest > observed:
        require(
            latest == reference_day,
            "Missed H5 formation needs exact saved formation evidence; never infer at a later close",
        )
        require(
            latest[:7] == "2026-10",
            "H5 next-month model is not received; no new fit or October-model extension",
        )
        formation_plan(previous)
        started = now()
        features = feature_input(previous, raw, events, latest)
        features.update(
            source=binding(root / "current-source.json"),
            action_lineage=binding(root / "action-lineage-QA.json"),
            current_controls=binding(root / "current-h5-support.json"),
        )
        input_row = write(root / "H5-formation-input.json", features)
        try:
            learned = states(previous)
        except FileNotFoundError as error:
            raise FormationDependency("Retained H5 model/input artifact is missing") from error
        scores, allocation = infer(features, learned)
        forecast = dict(
            policy="H5",
            symbols=previous["symbols"],
            scores=scores,
            allocation=allocation,
            signal_observation=latest,
            signal_application=application_day,
            reference_day=latest,
            input=input_row,
            source=binding(root / "current-source.json"),
            models=previous["historical_model_provenance"]["adopted"]["states"],
            model_epoch="2026-10",
            model_cutoff="2026-09-30",
            computed_started_at=started,
            computed_completed_at=now(),
            original_formula=True,
            new_fits=0,
        )
        row = write(root / "H5-formation-forecast.json", forecast)
        old = forecast
        observed = latest
        fresh = True
    else:
        allocation = copy.deepcopy(old["allocation"])
        fresh = False
    weights = allocation["weights"]
    require(
        len(weights) == len(current["current_eligible"]) == 32, "H5 incomplete instruction roster"
    )
    require(
        all(yes for yes, w in zip(current["current_eligible"], weights, strict=True) if w > 0),
        "Held H5 selection lost current unit/action support",
    )
    return dict(
        allocation=allocation,
        signal_forecast=row,
        signal_observation=observed,
        signal_application=old.get("signal_application", old.get("application_day")),
        original_computed_at=old["computed_completed_at"],
        is_fresh_prediction=fresh,
        portfolio_action="rebalance" if fresh else "hold",
        phase=p,
        model_epoch="2026-10",
        current_unit_support_received=True,
    )


def partition(ready, blocked):
    policies = {"BASE", "H5", "LSTM", "BASE_STATE_BUDGET", "MULTI_EQUAL", "MULTI_HIERARCHICAL"}
    assert set(ready).isdisjoint(blocked) and set(ready) | set(blocked) == policies
    assert isinstance(blocked, dict) and all(type(v) is str and v for v in blocked.values())
    assert ready, "No independently usable dated policy packet"
    if set(ready) & {"BASE_STATE_BUDGET", "MULTI_EQUAL", "MULTI_HIERARCHICAL"}:
        assert {"BASE", "H5"} <= set(ready), "Dependent policy lacks a current BASE/H5 instruction"
    return True


def receive_h5_instruction(root, target):
    """Read-only formation/held lineage; no source or model invocation."""
    row, signal, observed = origin(target["signal_forecast"])
    assert observed == target["signal_observation"] <= target["reference_day"]
    assert target["signal_application"] == signal.get(
        "signal_application", signal.get("application_day")
    )
    assert observed >= phase(target["reference_day"])["latest"], (
        "Missed formation cannot be published as held"
    )
    previous = receive_previous()
    carriers = previous["controls"]["carriers"]
    weights = signal["allocation"]["weights"]
    pairs = [
        (carriers.get(s) or s, float(w))
        for s, w in zip(signal["symbols"], weights, strict=True)
        if w > 0
    ]
    assert target["symbols"] == [s for s, w in pairs] and target["weights"] == [w for s, w in pairs]
    assert target["K"] == signal["allocation"]["K"]
    if target["is_fresh_prediction"]:
        assert observed == target["reference_day"] and target["portfolio_action"] == "rebalance"
        assert Path(row["path"]) == Path(root) / "H5-formation-forecast.json"
        assert (
            signal["source"] == target["source"]
            and signal["models"] == previous["historical_model_provenance"]["adopted"]["states"]
        )
        assert (
            signal["model_epoch"] == observed[:7] == "2026-10"
            and signal["model_cutoff"] == "2026-09-30"
        )
        features = load(checked(signal["input"]))
        assert Path(signal["input"]["path"]) == Path(root) / "H5-formation-input.json"
        assert (
            features["reference_day"] == observed and features["support_sessions"][-1] == observed
        )
        assert features["new_fits"] == features["new_labels"] == signal["new_fits"] == 0
        assert (
            pure("models", "allocate")(
                signal["scores"]["STOCK"], signal["scores"]["STATE"], features["eligible"]
            )
            == signal["allocation"]
        )
        assert datetime.fromisoformat(signal["computed_started_at"]) <= datetime.fromisoformat(
            signal["computed_completed_at"]
        )
    elif "received_unadopted_formation" in target:
        # A genuine saved formation can be adopted prospectively after a failed
        # worker without being relabelled as fresh inference or resending an ID.
        prior_row = target["received_unadopted_formation"]
        prior_path = checked(prior_row)
        assert prior_path.is_relative_to(REPO / "reports/paper/diagnostics")
        prior = load(prior_path)
        assert prior["policy"] == "H5"
        prior_origin = prior.get("signal_forecast", prior.get("held_model_origin"))
        _, _, prior_observed = origin(prior_origin)
        assert prior_observed < observed < target["reference_day"]
        assert target["signal_application"] < target["application_day"]
        assert {k: prior_row[k] for k in ["bytes", "sha256"]} == {
            k: target["prior_target"][k] for k in ["bytes", "sha256"]
        }
        same = dict(zip(prior["symbols"], prior["weights"], strict=True)) == dict(
            zip(target["symbols"], target["weights"], strict=True)
        )
        assert target["weights_unchanged"] is same
        assert target["portfolio_action"] == ("hold" if same else "rebalance")
    else:
        assert target["portfolio_action"] == "hold"
    return row


def receive_state_instruction(target, base, h5, *, base_row, h5_row):
    """Exact causal scaling in original28 order; output remains positive-only."""
    assert (
        target["policy"] == "BASE_STATE_BUDGET"
        and base["policy"] == "BASE"
        and h5["policy"] == "H5"
    )
    original = load(checked(base["held_model_origin"]))
    assert original["policy"] == "BASE" and len(original["symbols"]) == 28
    symbols = original["symbols"]
    assert len(set(symbols)) == 28

    def full(view):
        assert len(view["symbols"]) == len(view["weights"]) and len(set(view["symbols"])) == len(
            view["symbols"]
        )
        values = dict(zip(view["symbols"], view["weights"], strict=True))
        assert set(values) <= set(symbols) and all(
            type(x) in [int, float] and math.isfinite(x) and x > 0 for x in values.values()
        )
        result = [float(values.get(s, 0.0)) for s in symbols]
        assert view["symbols"] == [s for s, v in zip(symbols, result, strict=True) if v > 0]
        return result

    base_weights = full(base)
    actual = full(target)
    k = h5["K"]
    assert type(k) is int and 0 <= k <= 5 and target["K"] == k
    expected = [v * k / 5 for v in base_weights]
    assert all(
        struct.pack(">d", a) == struct.pack(">d", b) for a, b in zip(actual, expected, strict=True)
    )
    assert target["held_model_origins"] == [base["held_model_origin"], h5["signal_forecast"]]
    assert target["causal_inputs"] == dict(BASE=base_row, H5=h5_row)
    assert target["duplicates_BASE_now"] is (k == 5)
    assert target["cash_cause"] == "causal_H5_K_scaling_of_current_BASE"
    assert target["is_fresh_prediction"] is False
    for field in ["source", "reference_day", "application_day", "as_of", "valid_until"]:
        assert target[field] == base[field] == h5[field], "STATE causal source/clocks differ"
    assert datetime.fromisoformat(target["computed_at"]) >= max(
        datetime.fromisoformat(v["computed_at"]) for v in [base, h5]
    )
    return dict(symbols=symbols, weights=expected, K=k)
