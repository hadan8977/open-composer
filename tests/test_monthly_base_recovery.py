"""Private fixtures only: no real fit, HTTP, account or production writes."""

import json
from datetime import UTC, datetime

import pytest

from open_composer.paper_runtime.six import formation_continuity as continuity
from open_composer.paper_runtime.six import monthly_base_model as monthly
from open_composer.paper_runtime.six import produce_targets as producer


def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))
    return monthly._binding(path)


@pytest.mark.parametrize("at", ["2026-11-03T14:34:59+00:00", "2026-11-03T21:15:00+00:00"])
def test_actual_fit_window_blocks_before_packet_or_admission(at, tmp_path, monkeypatch):
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime.fromisoformat(at)

    monkeypatch.setattr(monthly, "datetime", Clock)
    monkeypatch.setattr(monthly, "receive_owner_exception", lambda *a, **kw: {
        "actual_source_cutoff": "2026-11-03T09:35:00-05:00",
        "actual_fit_seal_deadline": "2026-11-03T16:15:00-05:00",
    })
    monkeypatch.setattr(monthly, "receive_input", lambda *a, **kw: pytest.fail("No packet access outside the actual window"))
    with pytest.raises(AssertionError, match="actual fit window"):
        monthly.produce_model({}, root=tmp_path, owner_exception=tmp_path / "decision", output=tmp_path / "model",
            admit=lambda *a: pytest.fail("No native admission or estimator call"))
    assert not (tmp_path / "model").exists()


def test_new_month_uses_new_BASE_and_same_causal_STATE_input(tmp_path, monkeypatch):
    if not (producer.T / "input/BASE/output.json").exists():
        pytest.skip("requires retained accepted metadata only")
    original = producer.load(producer.T / "input/BASE/output.json")
    previous_h5 = producer.load(producer.T / "input/H5/output.json")
    symbols, hsymbols = original["symbols"], previous_h5["symbols"]
    packet = tmp_path / "packet"
    packet.mkdir()
    source = dict(prior_reference_day="2026-11-02", reference_day="2026-11-03", application_day="2026-11-04",
        formation_request_contract=dict(raw_support_start="2026-10-19"))
    dump(packet / "current-source.json", source)
    model_binding = dump(tmp_path / "new-model.json", dict(eligible=[True] * 28))
    prior = tmp_path / "prior"
    for policy in ["BASE", "H5", "BASE_STATE_BUDGET"]:
        dump(prior / "targets" / (policy + ".json"), dict(symbols=[], weights=[]))
    # Same weights in a different month remain a genuine rebalance event.
    dump(prior / "targets/BASE.json", dict(symbols=[symbols[26]], weights=[0.2], held_model_origin={"private": "old-month"}))
    monkeypatch.setattr(producer, "runtime_root", lambda root: prior)
    monkeypatch.setattr(producer, "monthly_base_supported", lambda app: model_binding)
    monkeypatch.setattr(producer, "receive_action_lineage", lambda root: dict(private=True))

    def dated(fn, *args, **kwargs):
        pytest.fail("Neither the old September daily bridge nor stale October adoption may run")

    monkeypatch.setattr(producer, "dated", dated)
    monkeypatch.setattr(monthly, "daily_controls", lambda *a, **kw: dict(
        symbols=symbols, current_daily_eligible=[True] * 28,
        formation_eligible=[True] * 28, eligible=[True] * 28,
        raw_reference_marks={s: 100 for s in symbols}, current_actions=[]))
    new_weights = [0.0] * 28
    new_weights[26] = 0.2

    def instruction(row, **kwargs):
        assert row == model_binding and kwargs["current_daily_eligible"][-1] is False
        return dict(symbols=symbols, weights=new_weights, eligible=kwargs["current_daily_eligible"],
            held_model_origin=model_binding, held_signal_observation="2026-10-30", held_signal_application="2026-11-04",
            original_computed_at="2026-11-03T14:36:00+00:00", owner_date_exception=dict(private=True),
            new_fit_count=0, is_fresh_prediction=False, historical_timely_source_claim=False)

    monkeypatch.setattr(monthly, "current_instruction", instruction)
    monkeypatch.setattr(producer.ni, "h5_input", lambda *a: dict(symbols=hsymbols, current_eligible=[True] * 32))
    hweights = [0.2, 0.2] + [0.0] * 30
    monkeypatch.setattr(producer, "h5_decision", lambda *a, **kw: dict(
        allocation=dict(weights=hweights, K=2), signal_forecast=dict(private=True),
        signal_observation="2026-10-30", signal_application="2026-11-02",
        original_computed_at="2026-11-02T00:22:00+00:00",
        phase=dict(next_observation="2026-11-06", next_application="2026-11-09"),
        model_epoch="2026-10", is_fresh_prediction=False, portfolio_action="hold"))
    marks = {s: 100.0 for s in symbols + hsymbols}
    b, h = producer.prepare_core(packet, source,
        {("core", "raw-bars"): [dict(bars={})], ("core", "actions"): []}, {},
        dict(BASE=(original, {}, None), H5=(previous_h5, {}, None)), [], {}, marks, {symbols[-1]}, lambda *a: [])
    assert b["symbols"] == [symbols[26]] and b["weights"] == [0.2]
    assert b["held_model_origin"] == model_binding
    assert b["portfolio_action"] == "rebalance" and b["new_monthly_model_adoption"] is True
    current = producer.load(packet / "current-base-input.json")
    assert current["monthly_forecast"] == model_binding and "model_design" not in current
    state = producer.load(packet / "targets/BASE_STATE_BUDGET.json")
    assert state["symbols"] == [symbols[26]] and state["weights"] == pytest.approx([0.08])
    assert state["held_model_origins"][0] == model_binding
    assert state["portfolio_action"] == "rebalance" and state["new_monthly_model_adoption"] is True
    assert state["causal_inputs"]["BASE"] == monthly._binding(packet / "targets/BASE.json")
    assert state["causal_inputs"]["H5"] == monthly._binding(packet / "targets/H5.json")


@pytest.mark.parametrize("app", ["2026-11-03", "2026-12-01"])
def test_current_month_boundary_refuses_without_reading_a_model(app, tmp_path):
    with pytest.raises(AssertionError, match="early or indefinite"):
        monthly.receive_current_model(root=tmp_path, application_day=app, now=datetime(2026, 11, 4, tzinfo=UTC))


def test_monthly_guard_requires_actual_received_model(monkeypatch):
    def missing(**kwargs):
        raise FileNotFoundError("Private missing sealed monthly output")

    monkeypatch.setattr(monthly, "receive_current_model", missing)
    with pytest.raises(continuity.FormationDependency, match="genuinely received November"):
        continuity.monthly_base_supported("2026-11-04")


@pytest.mark.parametrize("ref, app", [("2026-11-03", "2026-11-04"), ("2026-11-04", "2026-11-05"), ("2026-11-05", "2026-11-06")])
def test_november_raw_tail_keeps_monthly_prefix_across_later_days(ref, app, monkeypatch):
    monkeypatch.setattr(continuity, "origin", lambda row: ({"private": True}, {}, "2026-10-30"))
    contract = continuity.source_contract(ref, app, origin_row={"private": True})
    assert contract["raw_support_start"] == "2026-10-30"
