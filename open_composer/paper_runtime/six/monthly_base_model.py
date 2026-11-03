"""One finite, owner-authorized BASE restart fit and read-only daily adoption.

The actual receipt/fit dates differ from the frozen fact/label cutoff. This
module never submits orders, writes account state, publishes targets, or waits.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import time
from datetime import UTC, date, datetime
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import numpy as np

from open_composer.paper_runtime.six.monthly_base_recovery import (
    FORMATION,
    SCIENTIFIC_CUTOFF,
    _binding,
    _checked,
    _clock,
    _load,
    _originals,
    _save,
    receive_input,
)

MODEL_PARAMETERS = {"kind": "ridge_regressor", "alpha": 10.0, "fit_intercept": True, "seed": 20261017}
MODEL_OUTPUT = Path("reports/paper/diagnostics/base-monthly-recovery-20261103/model")
MODEL_POINTER = Path("runtime/paper/six/monthly-base-current.json")


def receive_owner_exception(path, *, now):
    decision = _load(path)
    assert decision["formation_month"] == FORMATION
    assert decision["scientific_fact_and_label_cutoff"] == SCIENTIFIC_CUTOFF
    assert decision["actual_source_cutoff"] == "2026-11-03T09:35:00-05:00"
    assert decision["actual_fit_seal_deadline"] == "2026-11-03T16:15:00-05:00"
    assert decision["first_execution_day"] == "2026-11-04" and decision["last_application_day"] == "2026-11-30"
    assert decision["earliest_order_time"] == "09:40 America/New_York"
    assert decision["preserve_model_parameters_and_account_state"] is True
    assert decision["backdated_actual_orders"] is False
    assert set(decision["policies"]) == {"BASE", "BASE_STATE_BUDGET", "MULTI_EQUAL", "MULTI_HIERARCHICAL"}
    assert _clock(decision["recorded_at"]) <= now
    return decision


def _producer_bindings(root):
    from open_composer.paper_runtime.six import monthly_base_recovery
    from open_composer.research.ml_backend import model_factory

    return [_binding(__file__), _binding(monthly_base_recovery.__file__), _binding(model_factory.__file__)]


def _append(path, row):
    with Path(path).open("a") as stream:
        stream.write(json.dumps(row, allow_nan=False) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def produce_model(context_binding, *, root, owner_exception, output, admit):
    """One original-parameter fit, only after the actual authorized source cutoff.

    `admit(binding, code_bindings, owner_exception, invocation_id)` is the same
    real native/resource admission shape required by the original producer.
    This function has no optional or JSON-status replacement for admission.
    """
    root, output = Path(root).resolve(), Path(output).resolve()
    now = datetime.now(UTC)
    decision = receive_owner_exception(owner_exception, now=now)
    assert _clock(decision["actual_source_cutoff"]) <= now < _clock(decision["actual_fit_seal_deadline"]), "Outside actual fit window; no early fit, catchup or implicit date roll"
    if output.exists():
        return receive_forecast(_binding(output / "forecast.json"), root=root, now=now)
    assert not output.is_relative_to(root / "runtime")
    context = receive_input(context_binding, root=root, now=now)
    assert _clock(context["actual_sources_received_through"]) <= _clock(decision["actual_source_cutoff"])
    code = _producer_bindings(root)
    fingerprint = json.dumps(code, sort_keys=True)
    decision_binding = _binding(owner_exception)
    invocation = uuid4().hex
    admission = admit(context_binding, code, decision, invocation)
    assert admission and json.dumps(code, sort_keys=True) == fingerprint and code == _producer_bindings(root)
    assert decision_binding == _binding(owner_exception)
    output.mkdir(parents=True)
    started = {"invocation_id": invocation, "pid": os.getpid(), "context": context_binding,
        "owner_exception": decision_binding, "producer_bindings": code, "admission": admission}
    _append(output / "journal.jsonl", dict(started, event="started", at=datetime.now(UTC).isoformat()))
    computation_started = datetime.now(UTC).isoformat()
    try:
        with _originals(root) as modules:
            rc = modules["receiver_common"]
            with np.load(context["outputs"]["packet.npz"]["path"], allow_pickle=False) as packet:
                z = {key: packet[key] for key in packet.files}
            with rc.legacy(rc.SHARE):
                learning = rc.module("base_restart_original_learning", rc.SHARE / "learning.py")
                method = rc.module("base_restart_original_method", rc.SHARE / "method.py")
                current = len(z["entry"]) - 1
                fold = learning.fold(z, current)
                ii, jj, weights = fold["i"], fold["j"], fold["weights"]
                assert fold["IDs_sha256"] == context["fold"]["IDs_sha256"]
                assert fold["weights_sha256"] == context["fold"]["weights_sha256"]
                scores, allocations, state = np.full(28, np.nan), np.zeros(28), None
                reason = "insufficient_original_fold_support" if not fold["supported"] else None
                if fold["supported"]:
                    train, _, primitive = method.train_design(z["primitive"][ii, jj], z["flags"][ii, jj], z["turnover"][ii, jj], weights)
                    test, _, _ = method.train_design(z["primitive"][current], z["flags"][current], z["turnover"][current], np.ones(28), state=primitive)
                    from open_composer.research.ml_backend.model_factory import create_model

                    estimator = create_model(SimpleNamespace(model=SimpleNamespace(kind="ridge_regressor", hyperparameters={"alpha": 10.0, "fit_intercept": True}, training=SimpleNamespace(seed=20261017))))
                    assert _producer_bindings(root) == code
                    estimator.fit(train, z["label"][ii, jj], scale__sample_weight=weights, model__sample_weight=weights)
                    scores = estimator.predict(test)
                    allocations = method.target(scores, z["eligible"][current], z["symbols"], "BASE", z["primitive"][current, :, 0], z["turnover"][current])
                    if not np.isfinite(scores[z["eligible"][current]]).all():
                        reason = "nonfinite_eligible_score"
                    if reason is None and not allocations.any():
                        reason = "no_positive_eligible_BASE_score"
                    state = {"primitive_state": primitive,
                        "model": {"mean": estimator.named_steps["scale"].mean_, "scale": estimator.named_steps["scale"].scale_, "coef": estimator.named_steps["model"].coef_, "intercept": float(estimator.named_steps["model"].intercept_)}}
                serialized_scores = [float(s) if math.isfinite(s) else None for s in scores]
                state_row = rc.clean({**started, "state": state, "fold": {k: v for k, v in fold.items() if k not in ["i", "j", "weights"]}, "scores": serialized_scores, "weights": allocations.tolist()})
                _save(output / "state.json", state_row)
                maturity = max((str(z["dates"][int(z["label_end"][i])]) for i in np.unique(ii)), default="0001-01-01")
                assert _clock(maturity + "T23:59:59-04:00") < _clock(SCIENTIFIC_CUTOFF)
                completed = datetime.now(UTC).isoformat()
                forecast = {**started, "schema": "monthly-base-prospective-restart-v1", "policy": "BASE", "formation_month": FORMATION,
                    "scientific_fact_and_label_cutoff": SCIENTIFIC_CUTOFF,
                    "actual_sources_received_through": context["actual_sources_received_through"],
                    "computation_started_at": computation_started, "computation_completed_at": completed,
                    "model_parameters": MODEL_PARAMETERS, "training_label_end_through": maturity,
                    "state": _binding(output / "state.json"), "symbols": rc.SYMBOLS,
                    "scores": serialized_scores, "weights": allocations.tolist(), "eligible": z["eligible"][current].tolist(),
                    "K": int((allocations > 0).sum()), "selected": [s for s, w in zip(rc.SYMBOLS, allocations, strict=True) if w],
                    "fit_supported": bool(fold["supported"]), "cash_reason": reason,
                    "fit_calls": int(fold["supported"]), "historical_timely_source_claim": False,
                    "first_execution_day": decision["first_execution_day"], "last_application_day": decision["last_application_day"]}
                assert datetime.now(UTC) < _clock(decision["actual_fit_seal_deadline"])
                _save(output / "forecast.json", forecast)
                _save(output / "seal.json", {"forecast": _binding(output / "forecast.json"), "state": forecast["state"], "actual_sealed_at": datetime.now(UTC).isoformat(), **started})
                _append(output / "journal.jsonl", {**started, "event": "completed", "at": datetime.now(UTC).isoformat(), "seal": _binding(output / "seal.json")})
    except BaseException as exc:
        _append(output / "journal.jsonl", {**started, "event": "failed", "at": datetime.now(UTC).isoformat(), "error_type": type(exc).__name__})
        raise
    return receive_forecast(_binding(output / "forecast.json"), root=root)


def receive_forecast(forecast_binding, *, root, now=None):
    """Read sealed actual model output; no prediction or account calls."""
    now = datetime.now(UTC) if now is None else now
    path = _checked(forecast_binding, root)
    forecast = _load(path)
    assert forecast["schema"] == "monthly-base-prospective-restart-v1" and forecast["policy"] == "BASE"
    assert forecast["formation_month"] == FORMATION and forecast["scientific_fact_and_label_cutoff"] == SCIENTIFIC_CUTOFF
    assert forecast["model_parameters"] == MODEL_PARAMETERS
    assert forecast["producer_bindings"] == _producer_bindings(root)
    decision_path = _checked(forecast["owner_exception"], root)
    decision = receive_owner_exception(decision_path, now=now)
    context = receive_input(forecast["context"], root=root, now=now)
    state = _load(_checked(forecast["state"], root))
    seal_path = path.parent / "seal.json"
    seal = _load(seal_path)
    assert seal["forecast"] == forecast_binding and seal["state"] == forecast["state"]
    journal = [_load_json_line(row) for row in (path.parent / "journal.jsonl").read_text().splitlines()]
    assert len(journal) == 2 and [r["event"] for r in journal] == ["started", "completed"]
    assert journal[1]["seal"] == _binding(seal_path)
    keys = ["invocation_id", "pid", "context", "owner_exception", "producer_bindings", "admission"]
    for key in keys:
        assert state[key] == seal[key] == journal[0][key] == journal[1][key] == forecast[key]
    assert forecast["scores"] == state["scores"] and forecast["weights"] == state["weights"]
    assert forecast["fit_supported"] is state["fold"]["supported"]
    assert forecast["fit_calls"] == int(forecast["fit_supported"])
    assert (state["state"] is not None) == forecast["fit_supported"]
    assert _clock(context["actual_sources_received_through"]) <= _clock(decision["actual_source_cutoff"]) <= _clock(journal[0]["at"]) <= _clock(forecast["computation_started_at"]) <= _clock(forecast["computation_completed_at"]) <= _clock(seal["actual_sealed_at"]) <= _clock(journal[1]["at"]) <= min(now, _clock(decision["actual_fit_seal_deadline"]))
    assert forecast["symbols"] == context["whole_roster"] and len(forecast["symbols"]) == 28
    assert forecast["first_execution_day"] == decision["first_execution_day"] and forecast["last_application_day"] == decision["last_application_day"]
    scores = np.asarray([np.nan if value is None else value for value in forecast["scores"]])
    eligible = np.asarray(forecast["eligible"], dtype=bool)
    assert len(eligible) == len(scores) == 28 and all(type(v) is bool for v in forecast["eligible"])
    with _originals(root) as modules:
        rc = modules["receiver_common"]
        with rc.legacy(rc.SHARE):
            method = rc.module("base_restart_receive_method", rc.SHARE / "method.py")
            expected = method.target(scores, eligible, np.asarray(forecast["symbols"]), "BASE", np.zeros(28), np.zeros(28))
            assert expected.tolist() == forecast["weights"]
            if state["state"] is not None:
                with np.load(context["outputs"]["packet.npz"]["path"], allow_pickle=False) as packet:
                    assert eligible.tolist() == packet["eligible"][-1].tolist()
                    design, _, _ = method.train_design(packet["primitive"][-1], packet["flags"][-1], packet["turnover"][-1], np.ones(28), state=state["state"]["primitive_state"])
                model = state["state"]["model"]
                reproduced = ((design - np.asarray(model["mean"])) / np.asarray(model["scale"])) @ np.asarray(model["coef"]) + model["intercept"]
                assert np.allclose(scores, reproduced, rtol=1e-12, atol=1e-12), "Forecast differs from sealed original model state"
    assert forecast["K"] == len(forecast["selected"]) == int((expected > 0).sum())
    assert forecast["selected"] == [symbol for symbol, weight in zip(forecast["symbols"], expected, strict=True) if weight]
    assert 0 <= forecast["K"] <= 5
    return forecast


def _load_json_line(value):
    return json.loads(value)


def current_instruction(forecast_binding, *, root, application_day, current_daily_eligible, now=None):
    """Frozen monthly scores plus original daily eligibility allocator for targets.

    Caller supplies daily eligibility from the existing current raw/action and
    sanitizer path. BASE_STATE and the two MULTI consumers use this same result.
    """
    assert date.fromisoformat(application_day).isoformat() == application_day
    forecast = receive_forecast(forecast_binding, root=root, now=now)
    assert forecast["first_execution_day"] <= application_day <= forecast["last_application_day"]
    assert len(current_daily_eligible) == 28 and all(type(v) is bool for v in current_daily_eligible)
    eligible = [a and b for a, b in zip(forecast["eligible"], current_daily_eligible, strict=True)]
    scores = np.asarray([np.nan if v is None else v for v in forecast["scores"]])
    with _originals(root) as modules:
        rc = modules["receiver_common"]
        with rc.legacy(rc.SHARE):
            method = rc.module("base_restart_daily_allocator", rc.SHARE / "method.py")
            weights = method.target(scores, np.asarray(eligible), np.asarray(forecast["symbols"]), "BASE", np.zeros(28), np.zeros(28))
    return {"symbols": forecast["symbols"], "weights": weights.tolist(), "scores": forecast["scores"], "eligible": eligible,
        "held_model_origin": forecast_binding, "held_signal_observation": "2026-10-30", "held_signal_application": forecast["first_execution_day"],
        "original_computed_at": forecast["computation_completed_at"], "owner_date_exception": forecast["owner_exception"],
        "new_fit_count": 0, "is_fresh_prediction": False, "historical_timely_source_claim": False}


def install_forecast(forecast_binding, *, root):
    """Install only the verified model pointer; first permitted application is Nov 4."""
    root = Path(root).resolve()
    assert Path(forecast_binding["path"]) == root / MODEL_OUTPUT / "forecast.json"
    forecast = receive_forecast(forecast_binding, root=root)
    pointer_path = root / MODEL_POINTER
    assert pointer_path.parent.is_dir(), "Existing paper runtime required; never initialize an account"
    row = {"schema": "monthly-base-current-v1", "formation_month": FORMATION, "forecast": forecast_binding,
        "owner_exception": forecast["owner_exception"], "first_execution_day": forecast["first_execution_day"],
        "last_application_day": forecast["last_application_day"], "installed_at": datetime.now(UTC).isoformat()}
    if pointer_path.exists():
        previous = _load(pointer_path)
        assert all(previous[key] == row[key] for key in row if key != "installed_at"), "Different installed monthly model; no replacement"
        return _binding(pointer_path)
    temporary = pointer_path.with_name(pointer_path.name + ".tmp-" + str(os.getpid()))
    _save(temporary, row)
    temporary.replace(pointer_path)
    return _binding(pointer_path)


def receive_current_model(*, root, application_day, now=None):
    """Fixed-location current model reception for the existing finite daily producer."""
    root = Path(root).resolve()
    now = datetime.now(UTC) if now is None else now
    assert date.fromisoformat(application_day).isoformat() == application_day
    assert "2026-11-04" <= application_day <= "2026-11-30", "No early or indefinite monthly adoption"
    pointer = _load(root / MODEL_POINTER)
    assert pointer["schema"] == "monthly-base-current-v1" and pointer["formation_month"] == FORMATION
    assert _clock(pointer["installed_at"]) <= now
    assert Path(pointer["forecast"]["path"]) == root / MODEL_OUTPUT / "forecast.json"
    forecast = receive_forecast(pointer["forecast"], root=root, now=now)
    for key in ["owner_exception", "first_execution_day", "last_application_day"]:
        assert pointer[key] == forecast[key]
    return pointer["forecast"], forecast


def receive_target(packet_root, target, *, root, now=None):
    """Check that an adopted BASE sleeve uses this model and its actual daily input."""
    packet_root = Path(packet_root).resolve()
    forecast_binding, forecast = receive_current_model(root=root, application_day=target["application_day"], now=now)
    current_path = packet_root / "current-base-input.json"
    assert target["monthly_current_input"] == _binding(current_path)
    current = _load(current_path)
    assert current["monthly_forecast"] == target["held_model_origin"] == forecast_binding
    assert current["source"] == target["source"] and current["source"] == _binding(packet_root / "current-source.json")
    assert current["reference_day"] == target["reference_day"] and current["application_day"] == target["application_day"]
    assert current["formation_eligible"] == forecast["eligible"]
    expected = current_instruction(forecast_binding, root=root, application_day=target["application_day"], current_daily_eligible=current["current_daily_eligible"], now=now)
    assert current["eligible"] == expected["eligible"]
    pairs = [(s, w) for s, w in zip(expected["symbols"], expected["weights"], strict=True) if w > 0]
    assert list(zip(target["symbols"], target["weights"], strict=True)) == pairs
    for key in ["held_signal_observation", "held_signal_application", "original_computed_at", "owner_date_exception"]:
        assert target[key] == expected[key]
    return forecast_binding


def daily_controls(forecast_binding, *, root, reference_day, control, raw_objects, action_objects):
    """Extend the received October daily prefix with the actual November tail.

    Uses the unchanged original daily bridge. The September-seed bridge would
    otherwise omit October days once the global request rolls into November.
    """
    forecast = receive_forecast(forecast_binding, root=root)
    current = prepared_daily_controls(forecast["context"], root=root, reference_day=reference_day,
        control=control, raw_objects=raw_objects, action_objects=action_objects)
    assert current["formation_eligible"] == forecast["eligible"]
    return current


def prepared_daily_controls(context_binding, *, root, reference_day, control, raw_objects, action_objects):
    """Engineering reception of real daily eligibility, without fitting a model."""
    context = receive_input(context_binding, root=root)
    with np.load(context["outputs"]["packet.npz"]["path"], allow_pickle=False) as packet:
        formation_eligible = packet["eligible"][-1].tolist()
    with _originals(root) as modules:
        rc, features = modules["receiver_common"], modules["features"]
        with np.load(context["outputs"]["daily.npz"]["path"], allow_pickle=False) as packet:
            daily = {key: packet[key] for key in packet.files}
        prefix_end = str(daily["dates"][-1])
        assert prefix_end == "2026-10-30" and reference_day >= prefix_end
        units = {"dates": daily["dates"], "symbols": daily["all_symbols"],
            "raw_close": daily["all_raw_close"], "raw_open": daily["all_raw_open"]}
        projected = []
        for body in raw_objects:
            rows = {symbol: [bar for bar in body["bars"].get(symbol, []) if prefix_end <= bar["t"][:10] <= reference_day] for symbol in rc.UNITS}
            projected.append({"bars": rows})
        actions = {}
        for body in action_objects:
            for kind, rows in body["corporate_actions"].items():
                for row in rows:
                    symbol = row.get("symbol") or row.get("source_symbol") or row.get("acquiree_symbol")
                    if symbol in rc.UNITS or row.get("acquirer_symbol") in rc.UNITS:
                        actions.setdefault(kind, []).append(row)
        joined_actions = features.merge_actions(_load(context["outputs"]["actions.json"]["path"]), [{"corporate_actions": actions}], prefix_end)
        bridge_path = Path(root) / "reports/research/program/owner-profit-delivery-plan-20261017/candidate-contribution/current-initialization-20261019/bridge.py"
        bridge = rc.module("base_monthly_original_daily_bridge", bridge_path)
        current, triggers = bridge.extend_daily(daily, units, {"eligible": daily["eligible"]}, {
            "manifest": {"reference_day": reference_day, "prefix_end": prefix_end},
            "objects": {"raw-bars": projected}, "actions": joined_actions})
        assert str(current["dates"][-1]) == reference_day
        marks = {s: control["symbols"][s]["raw_close"] for s in rc.UNITS}
        observed = rc.clean({s: float(current["all_raw_close"][-1, j]) for j, s in enumerate(rc.UNITS)})
        assert observed == marks, "Current daily bridge differs from actual unit controls"
        return {"symbols": context["whole_roster"], "formation_eligible": formation_eligible,
            "current_daily_eligible": current["eligible"][-1].tolist(),
            "eligible": (np.asarray(formation_eligible) & current["eligible"][-1]).tolist(),
            "raw_reference_marks": marks, "current_actions": control["current_actions_by_group"]["core"],
            "current_split_jump_triggers": triggers[-1].tolist(), "monthly_daily_prefix": context["outputs"]["daily.npz"]}


def _native_admission(root, context_binding, code, decision, invocation):
    from open_composer.paper_runtime.six.paper_target_input_controls import receive_current_paper_maintenance

    authority = receive_current_paper_maintenance()
    authorization_path = Path(root) / "runtime/paper/six/owner-authorization.json"
    authorization = _load(authorization_path)
    config_path = Path(root) / "config/paper/six-service.json"
    config = _load(config_path)
    assert authorization.get("paper_only") is True
    assert _clock(config["expires_at"]) > datetime.now(UTC)
    group = Path("/proc/self/cgroup").read_text().strip().split(":")[-1]
    cgroup = Path("/sys/fs/cgroup") / group.lstrip("/")
    memory = {name: (cgroup / name).read_text().strip() for name in ["memory.max", "memory.swap.max", "memory.current"]}
    assert memory["memory.max"] != "max" and int(memory["memory.max"]) <= 2458 * 1024 * 1024
    assert os.environ.get("OMP_NUM_THREADS") == os.environ.get("OPENBLAS_NUM_THREADS") == "1"
    return {"current_paper_maintenance": authority, "existing_paper_authorization": _binding(authorization_path), "existing_paper_config": _binding(config_path),
        "context": context_binding, "code": code, "invocation_id": invocation, "resources": memory, "received_at": datetime.now(UTC).isoformat()}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("/root/codex-test/open-composer"))
    parser.add_argument("--context", type=Path, required=True)
    parser.add_argument("--owner-exception", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--check-only", action="store_true")
    parser.add_argument("--wait-until-cutoff", action="store_true", help="One bounded sleep, one fit, then exit; no polling or retry")
    parser.add_argument("--install", action="store_true", help="Install the model pointer after verified completion, never paper targets")
    args = parser.parse_args()
    os.environ["OPEN_COMPOSER_ROOT"] = str(args.root.resolve())
    now = datetime.now(UTC)
    decision = receive_owner_exception(args.owner_exception, now=now)
    context_binding = _binding(args.context)
    context = receive_input(context_binding, root=args.root, now=now)
    assert _clock(context["actual_sources_received_through"]) <= _clock(decision["actual_source_cutoff"])
    if args.check_only:
        print(json.dumps({"status": "checked_no_fit", "context": context_binding, "not_before": decision["actual_source_cutoff"], "deadline": decision["actual_fit_seal_deadline"]}))
        return
    execution_log = args.output.with_name(args.output.name + "-finite-execution.jsonl")
    if args.wait_until_cutoff:
        execution_log.parent.mkdir(parents=True, exist_ok=True)
        first = {"event": "finite_execution_started", "pid": os.getpid(), "at": now.isoformat(),
            "not_before": decision["actual_source_cutoff"], "latest_exit": decision["actual_fit_seal_deadline"],
            "context": context_binding, "owner_exception": _binding(args.owner_exception), "retry_count": 0}
        # Exclusive creation is also the duplicate-waiter guard. Failures retain
        # the same file and cannot silently launch another wait/fit.
        with execution_log.open("x") as stream:
            stream.write(json.dumps(first) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        delay = max(0, (_clock(decision["actual_source_cutoff"]) - now).total_seconds())
        if delay:
            time.sleep(delay)
        _append(execution_log, {"event": "single_wait_completed", "at": datetime.now(UTC).isoformat()})
        now = datetime.now(UTC)
    if now < _clock(decision["actual_source_cutoff"]):
        print(json.dumps({"status": "not_due_no_fit", "not_before": decision["actual_source_cutoff"]}))
        raise SystemExit(75)
    try:
        result = produce_model(context_binding, root=args.root, owner_exception=args.owner_exception, output=args.output,
            admit=lambda *values: _native_admission(args.root, *values))
        forecast_binding = _binding(args.output / "forecast.json")
        installed = install_forecast(forecast_binding, root=args.root) if args.install else None
        if args.wait_until_cutoff:
            _append(execution_log, {"event": "finite_execution_completed", "at": datetime.now(UTC).isoformat(), "forecast": forecast_binding, "installed_pointer": installed})
        print(json.dumps({"status": "sealed_current_monthly_BASE", "forecast": forecast_binding, "installed_pointer": installed, "selected": result["selected"], "weights": result["weights"]}))
    except BaseException as exc:
        if args.wait_until_cutoff:
            _append(execution_log, {"event": "finite_execution_failed", "at": datetime.now(UTC).isoformat(), "error_type": type(exc).__name__, "retry_count": 0})
        raise


if __name__ == "__main__":
    main()
