"""Fixed private fixtures only: no future market data, fitted model or account."""

import copy
import json
import socket
import sys
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from open_composer.paper_runtime.six import formation_continuity as f
from open_composer.paper_runtime.six import paper_target_input_controls as input_controls
from open_composer.paper_runtime.six import produce_targets as producer
from open_composer.paper_runtime.six import run_dated_refresh as native

REPO = producer.REPO


@pytest.fixture(autouse=True)
def offline(monkeypatch, tmp_path):
    def deny(*a, **kw):
        raise AssertionError("Network/real child forbidden in fixture")

    monkeypatch.setattr(socket.socket, "connect", deny)
    monkeypatch.setattr(socket, "create_connection", deny)
    monkeypatch.setattr(native.subprocess, "Popen", deny)
    # Freeze a private predecessor; production target updates cannot change a test.
    if not (f.T / "inference/H5/output.json").exists():
        pytest.skip("requires the retained accepted paper science, without credentials")
    private = tmp_path / "runtime-predecessor"
    for policy in native.POLICIES:
        value = dict(symbols=[], weights=[])
        if policy == "LSTM":
            value["source"] = f.binding(input_controls.OLD / "current-source.json")
        if policy == "H5":
            value["signal_forecast"] = f.binding(f.T / "inference/H5/output.json")
        dump(private / "targets" / (policy + ".json"), value)
    monkeypatch.setattr(f, "runtime_root", lambda root: private)
    monkeypatch.setattr(producer, "runtime_root", lambda root: private)
    monkeypatch.setattr(input_controls, "runtime_root", lambda root: private)


def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, allow_nan=False))
    return f.binding(path)


@pytest.fixture
def previous():
    # Only retained metadata/contexts, not actual feature arrays or tree states.
    value = f.load(f.T / "input/H5/output.json")
    return {
        key: value[key]
        for key in [
            "symbols",
            "controls",
            "historical_model_provenance",
            "amendment",
            "connected_tail",
        ]
    }


@pytest.fixture
def tiny_features(previous):
    from datetime import date

    from open_composer.market_sessions import us_equity_session_dates

    yes = [s != "PBCT" for s in previous["symbols"]]
    return dict(
        symbols=previous["symbols"],
        eligible=yes,
        current_stock=[[0.01] * 9 if y else [None] * 9 for y in yes],
        current_state=[[0.01] * 21 if y else [None] * 21 for y in yes],
        reference_day="2026-10-23",
        support_sessions=[
            d.isoformat() for d in us_equity_session_dates(date(2026, 9, 30), date(2026, 10, 23))
        ],
        amendment=previous["amendment"],
        original_prepared=f.load(f.H5 / "source-plan.json")["accepted_prepared"],
        new_fits=0,
        new_labels=0,
    )


def tiny_states():
    # Explicitly invented constant trees, never the real October fitted states.
    return {
        arm: dict(
            context=dict(medians=[0.0] * (9 if arm == "STOCK" else 21)),
            tree_dump=dict(
                average_output=False, tree_info=[dict(tree_structure=dict(leaf_value=0.01))]
            ),
        )
        for arm in ["STOCK", "STATE"]
    }


def test_original_phase_and_request_selection():
    assert f.phase("2026-10-22")["next_observation"] == "2026-10-23"
    assert f.phase("2026-10-23")["next_application"] == "2026-11-02"
    held = f.source_contract("2026-10-22", "2026-10-23")
    formed = f.source_contract("2026-10-23", "2026-10-26")
    assert not held["formation_due"] and held["raw_support_start"] == "2026-10-19"
    assert formed["formation_due"] and formed["raw_support_start"] == "2026-09-30"
    plan = f.load(producer.N / "next-session-source-plan-M1.json")
    menu = f.request_menu(plan, formed)
    assert len(menu) == 6
    assert (
        next(r for g, r in menu if (g, r["key"]) == ("core", "raw-bars"))["params"]["start"]
        == "2026-09-30T00:00:00Z"
    )
    assert (
        next(r for g, r in menu if (g, r["key"]) == ("ETF", "raw-reference"))["params"]["start"]
        == "2026-10-22T00:00:00Z"
    )
    for g, row in menu:
        original = (
            next((v for v in plan[g]["requests"] if v["key"] == row["key"]), None)
            or plan["core"]["conditional_request"]
        )
        assert (
            row["endpoint"] == original["endpoint"]
            and row["params"]["symbols"] == original["params"]["symbols"]
        )


def test_no_future_or_missing_connected_rows(previous):
    with pytest.raises(f.FormationDependency, match="Future"):
        f.feature_input(previous, {("AES", "2026-10-26"): {}}, [], "2026-10-23")
    with pytest.raises(f.FormationDependency, match="missing complete"):
        f.feature_input(previous, {}, [], "2026-10-23")
    with pytest.raises(f.FormationDependency):
        f.source_contract("2026-10-23", "2026-10-24")


def test_original_feature_causality_and_scalar_allocation(previous):
    feature = f.pure("features", ["rolling_return", "trailing_drawdown", "features"], np=np, pd=pd)
    rng = np.random.default_rng(17)
    returns = rng.normal(0.0001, 0.008, (260, 32))
    available = np.ones((260, 32), dtype=bool)
    available[:, 16] = False
    spy = rng.normal(0.0001, 0.005, 260)
    a = feature(returns, available, spy)
    b = feature(
        np.r_[returns, np.full((1, 32), 0.9)],
        np.r_[available, np.ones((1, 32), dtype=bool)],
        np.r_[spy, 0.9],
    )
    assert np.array_equal(a["stock"], b["stock"][:-1], equal_nan=True)
    assert np.array_equal(a["state"], b["state"][:-1], equal_nan=True)
    current = dict(
        symbols=previous["symbols"],
        eligible=a["eligible"][-1].tolist(),
        current_stock=a["stock"][-1].tolist(),
        current_state=a["state"][-1].tolist(),
    )
    scores, allocation = f.infer(current, tiny_states())
    assert allocation["K"] == 5 and allocation["selected"] == [0, 1, 2, 3, 4]
    assert scores["STOCK"][16] is None and sum(allocation["weights"]) == 1
    negative = tiny_states()
    negative["STATE"]["tree_dump"]["tree_info"][0]["tree_structure"]["leaf_value"] = -0.01
    assert f.infer(current, negative)[1]["K"] == 0


def test_held_to_new_to_held_clocks(previous, tiny_features, tmp_path, monkeypatch):
    root = tmp_path / "formed"
    root.mkdir()
    source = dump(
        root / "current-source.json",
        dict(
            private_fixture=True,
            reference_day="2026-10-23",
            application_day="2026-10-26",
            captured_at="2026-10-26T00:30:00+00:00",
        ),
    )
    dump(root / "action-lineage-QA.json", dict(current_source=source, private_fixture=True))
    dump(
        root / "current-h5-support.json",
        dict(
            source=source,
            reference_day="2026-10-23",
            application_day="2026-10-26",
            private_fixture=True,
        ),
    )
    calls = []

    def features(*a, **kw):
        calls.append("features")
        return copy.deepcopy(tiny_features)

    monkeypatch.setattr(f, "feature_input", features)
    monkeypatch.setattr(f, "states", lambda value: tiny_states())
    current = dict(current_eligible=tiny_features["eligible"])
    first = f.h5_decision(
        previous,
        current,
        {},
        [],
        "2026-10-22",
        "2026-10-23",
        write=dump,
        root=root,
        now=lambda: "2026-10-23T01:00:00+00:00",
    )
    assert (
        not first["is_fresh_prediction"]
        and first["signal_observation"] == "2026-10-19"
        and not calls
    )
    new = f.h5_decision(
        previous,
        current,
        {},
        [],
        "2026-10-23",
        "2026-10-26",
        write=dump,
        root=root,
        now=lambda: "2026-10-26T01:00:00+00:00",
    )
    assert (
        new["is_fresh_prediction"]
        and new["portfolio_action"] == "rebalance"
        and new["signal_observation"] == "2026-10-23"
    )
    forecast = f.load(new["signal_forecast"]["path"])
    assert forecast["computed_started_at"].startswith("2026-10-26") and forecast["new_fits"] == 0
    live = tmp_path / "live"
    dump(live / "targets/H5.json", dict(signal_forecast=new["signal_forecast"]))
    monkeypatch.setattr(f, "runtime_root", lambda root: live)
    held = f.h5_decision(
        previous,
        current,
        {},
        [],
        "2026-10-26",
        "2026-10-27",
        write=dump,
        root=root,
        now=lambda: "2026-10-27T01:00:00+00:00",
    )
    assert (
        held["allocation"] == new["allocation"]
        and not held["is_fresh_prediction"]
        and held["signal_observation"] == "2026-10-23"
    )
    assert calls == ["features"]
    target = dict(
        signal_forecast=new["signal_forecast"],
        signal_observation="2026-10-23",
        signal_application="2026-10-26",
        reference_day="2026-10-23",
        portfolio_action="rebalance",
        is_fresh_prediction=True,
        K=new["allocation"]["K"],
        source=source,
    )
    pairs = [
        (previous["controls"]["carriers"].get(s) or s, w)
        for s, w in zip(previous["symbols"], new["allocation"]["weights"], strict=True)
        if w > 0
    ]
    target.update(symbols=[s for s, w in pairs], weights=[w for s, w in pairs])
    f.receive_h5_instruction(root, target)
    # Rebound fake scores and matching original K0 no longer self-certify.
    original = copy.deepcopy(forecast)
    forecast["scores"]["STATE"] = [
        -0.01 if v is not None else None for v in forecast["scores"]["STATE"]
    ]
    forecast["allocation"] = f.pure("models", "allocate")(
        forecast["scores"]["STOCK"], forecast["scores"]["STATE"], tiny_features["eligible"]
    )
    target.update(
        signal_forecast=dump(root / "H5-formation-forecast.json", forecast),
        K=0,
        symbols=[],
        weights=[],
    )
    with pytest.raises(f.FormationDependency, match="scores differ"):
        f.receive_h5_instruction(root, target)
    # Even a score change that leaves K/selected/weights unchanged refuses bitexact.
    forecast = copy.deepcopy(original)
    forecast["scores"]["STATE"][0] = float(np.nextafter(forecast["scores"]["STATE"][0], np.inf))
    target.update(signal_forecast=dump(root / "H5-formation-forecast.json", forecast))
    with pytest.raises(f.FormationDependency, match="scores differ"):
        f.receive_h5_instruction(root, target)
    # A held instruction must receive the completed origin as well.
    dump(live / "targets/H5.json", dict(signal_forecast=target["signal_forecast"]))
    with pytest.raises(f.FormationDependency, match="scores differ"):
        f.h5_decision(
            previous,
            current,
            {},
            [],
            "2026-10-26",
            "2026-10-27",
            write=dump,
            root=root,
            now=lambda: "2026-10-27T01:00:00+00:00",
        )


def test_unsupported_month_or_missed_formation_is_not_K0(
    previous, tiny_features, tmp_path, monkeypatch
):
    monkeypatch.setattr(
        f, "feature_input", lambda *a, **kw: pytest.fail("No later/future feature call")
    )
    current = dict(current_eligible=tiny_features["eligible"])
    for ref, app, now in [
        ("2026-10-26", "2026-10-27", "2026-10-27T01:00:00+00:00"),
        ("2026-11-06", "2026-11-09", "2026-11-09T01:00:00+00:00"),
    ]:
        with pytest.raises(f.FormationDependency):
            f.h5_decision(
                previous,
                current,
                {},
                [],
                ref,
                app,
                write=dump,
                root=tmp_path,
                now=lambda now=now: now,
            )
    with pytest.raises(f.FormationDependency):
        f.monthly_base_supported("2026-11-02")
    with pytest.raises(f.FormationDependency, match="not completed"):
        f.h5_decision(
            previous,
            current,
            {},
            [],
            "2026-10-23",
            "2026-10-26",
            write=dump,
            root=tmp_path,
            now=lambda: "2026-10-23T19:00:00+00:00",
        )


def test_per_policy_core_missing_H5_preserves_BASE(previous, tmp_path, monkeypatch):
    root = tmp_path / "partial"
    root.mkdir()
    source = dict(
        prior_reference_day="2026-10-22",
        reference_day="2026-10-23",
        application_day="2026-10-26",
        formation_request_contract=dict(raw_support_start="2026-09-30"),
    )
    dump(root / "current-source.json", source)
    base = f.load(f.T / "input/BASE/output.json")
    symbols = base["symbols"]
    marks = {s: 100.0 for s in symbols + previous["symbols"]}
    monkeypatch.setattr(producer, "receive_action_lineage", lambda root: dict(private=True))

    def dated(fn, *a, **kw):
        if fn is producer.ni.base_input:
            return lambda *args: dict(
                symbols=symbols,
                current_daily_eligible=[True] * 28,
                formation_eligible=[True] * 28,
                eligible=[True] * 28,
            )
        return lambda *args: dict(allocation=dict(weights=[0.2] * 5 + [0.0] * 23))

    monkeypatch.setattr(producer, "dated", dated)
    monkeypatch.setattr(
        producer.ni,
        "h5_input",
        lambda *args: dict(symbols=previous["symbols"], current_eligible=[True] * 32),
    )

    def missing(*args, **kw):
        raise f.FormationDependency("Private missing formation input")

    monkeypatch.setattr(producer, "h5_decision", missing)
    original = dict(BASE=(base, {}, None), H5=(previous, {}, None))
    b, h = producer.prepare_core(
        root,
        source,
        {("core", "raw-bars"): [dict(bars={})], ("core", "actions"): []},
        {},
        original,
        [],
        {},
        marks,
        set(),
        lambda *args: [],
    )
    assert b is not None and h is None and (root / "targets/BASE.json").exists()
    assert (
        not (root / "targets/H5.json").exists()
        and not (root / "targets/BASE_STATE_BUDGET.json").exists()
    )
    dump(root / "current-marks.json", marks)
    dump(
        root / "current-constituents.json",
        {k: dict(private=True) for k in ["S1", "S2", "S3", "C2", "BASE"]},
    )
    monkeypatch.setattr(producer, "receive_current_paper_maintenance", lambda: None)
    producer.assemble(root)
    blocked = {
        **f.load(root / "prepare-dependencies.json"),
        **f.load(root / "assembly-dependencies.json"),
    }
    assert set(blocked) == {"H5", "BASE_STATE_BUDGET", "MULTI_EQUAL", "MULTI_HIERARCHICAL"}
    assert f.partition({"BASE": {}, "LSTM": {}}, blocked)
    assert set(f.load(root / "current-constituents.json")) == {
        "S1",
        "S2",
        "S3",
        "C2",
        "BASE",
    }  # No invented H5 child.
    with pytest.raises(AssertionError):
        f.partition(
            {"BASE": {}, "LSTM": {}, "MULTI_EQUAL": {}},
            {p: "missing" for p in ["H5", "BASE_STATE_BUDGET", "MULTI_HIERARCHICAL"]},
        )


def test_month_boundary_keeps_ready_LSTM_and_H5_partition():
    ready = {"LSTM": {}, "H5": {}}
    blocked = {
        p: "November BASE model/design absent"
        for p in ["BASE", "BASE_STATE_BUDGET", "MULTI_EQUAL", "MULTI_HIERARCHICAL"]
    }
    assert f.partition(ready, blocked)
    with pytest.raises(AssertionError):
        f.partition(
            {"LSTM": {}, "H5": {}, "MULTI_EQUAL": {}},
            {p: "absent" for p in ["BASE", "BASE_STATE_BUDGET", "MULTI_HIERARCHICAL"]},
        )


def test_complete_invented_connected_return_feature_path(previous, tmp_path, monkeypatch):
    """Real original builders/formats over invented values, no actual saved forward."""
    from datetime import date

    from open_composer.market_sessions import us_equity_session_dates

    private = tmp_path / "h5"
    private.mkdir()
    symbols = previous["symbols"]
    days = [d.isoformat() for d in us_equity_session_dates(date(2026, 9, 30), date(2026, 10, 23))]
    seed_dates = [
        d.isoformat() for d in us_equity_session_dates(date(2025, 1, 2), date(2026, 9, 30))
    ][-252:]
    seed = private / "prepared.npz"
    np.savez_compressed(
        seed,
        dates=np.asarray(seed_dates),
        returns=np.full((252, 32), 0.0002),
        benchmark_SPY=np.full(252, 0.0002),
        available=np.ones((252, 32), dtype=bool),
    )
    boundary = private / "raw.parquet"
    pd.DataFrame(
        [
            dict(return_endpoint="2026-09-30", cohort_id=s, current_mark_raw_close=100.0)
            for s in symbols + ["SPY"]
        ]
    ).to_parquet(boundary, index=False)
    events = []
    for s, day in [("SPY", "2026-09-18"), ("USB", "2026-09-30")]:
        raw = dict(symbol=s, ex_date=day, rate=0.1)
        old = dict(
            cohort_id=s,
            return_endpoint=day,
            cash_per_previous_share=0.0,
            stock_distribution_value_per_previous_share=0.0,
            previous_economic_close=100.0,
            total_return=0.0002,
        )
        events.append(
            dict(
                symbol=s,
                day=day,
                old_stored_row=old,
                new_received_event=raw,
                cash=0.1,
                denominator=100.0,
                old_return=0.0002,
                new_current_window_return=0.0002 + 0.1 / 100.0,
            )
        )
    amendment = dump(private / "amendment.json", dict(overlay_cells=events))
    dump(
        private / "source-plan.json",
        dict(accepted_prepared=f.binding(seed), retained_dated_raw=f.binding(boundary)),
    )
    value = copy.deepcopy(previous)
    value["amendment"] = amendment
    value["controls"]["bars"]["VYLR"] = {
        "2026-10-01": dict(t="2026-10-01T04:00:00Z", c=1.0, o=1.0, v=1, n=1)
    }
    raw = {}
    tickers = {
        value["controls"]["carriers"][s]
        for s in symbols
        if value["controls"]["carriers"][s] is not None
    } | {"MTB", "SPY"}
    for s in tickers:
        for day in days:
            raw[s, day] = dict(t=day + "T04:00:00Z", o=100.0, c=100.0, h=101.0, l=99.0, v=100, n=1)
    value["connected_tail"] = []
    for day in days[1:]:
        if day > "2026-10-19":
            continue
        for s in symbols + ["SPY"]:
            ticker = "MTB" if s == "PBCT" else value["controls"]["carriers"].get(s, s)
            value["connected_tail"].append(
                dict(
                    episode=s,
                    carrier=ticker,
                    day=day,
                    previous_raw=100.0,
                    raw=100.0,
                    ratio=1.0,
                    cash_per_economic_parent=0.0,
                    child_mark=0.0,
                    action_ids=[],
                    economic_return=0.0,
                    available=s != "PBCT",
                    split_trigger=False,
                    hygiene_trigger=False,
                    ghost=False,
                )
            )
    monkeypatch.setattr(f, "H5", private)
    feature = f.feature_input(value, raw, [], "2026-10-23")
    assert (
        feature["support_sessions"] == days
        and len(feature["current_stock"]) == len(feature["current_state"]) == 32
    )
    assert all(len(row) == 9 for row in feature["current_stock"]) and all(
        len(row) == 21 for row in feature["current_state"]
    )
    assert feature["eligible"][symbols.index("PBCT")] is False
    assert feature["overlay"]["training_data_unchanged"] is True and not feature["hygiene_breaks"]
    assert f.infer(feature, tiny_states())[1]["K"] == 5
    assert feature["new_fits"] == feature["new_labels"] == 0


def test_partial_packet_real_pure_receiver_and_private_publication(tmp_path, monkeypatch, previous):
    """Invented full page/date inventories, not copied future data or forecasts."""
    import ast
    import math
    from datetime import date, timedelta
    from types import ModuleType, SimpleNamespace

    from open_composer.market_sessions import us_equity_session_dates

    root = tmp_path / "packet"
    root.mkdir()
    contract = f.source_contract("2026-10-23", "2026-10-26")
    plan = f.load(producer.N / "next-session-source-plan-M1.json")
    menu = f.request_menu(plan, contract)
    index = []
    for group, request in menu:
        params = request["params"]
        if request["key"] == "actions":
            bodies = [dict(corporate_actions={}, next_page_token=None)]
        else:
            symbols = params["symbols"].split(",")
            if group == "core" and request["key"] == "raw-bars":
                symbols = [
                    s
                    for s in symbols
                    if s not in plan["core"]["ceased_and_carriers"]["known_no_current_bar"]
                ]
            days = us_equity_session_dates(
                date.fromisoformat(params["start"][:10]),
                date.fromisoformat(params["end"][:10]) - timedelta(days=1),
            )
            cells = [
                (s, d.isoformat())
                for s in symbols
                for d in days
                if not (
                    group == "core"
                    and request["key"] == "raw-bars"
                    and s == "AES"
                    and d.isoformat() == "2026-10-05"
                )
            ]
            bodies = []
            for lo in range(0, len(cells), 9000):
                bars = {}
                for s, day in cells[lo : lo + 9000]:
                    bars.setdefault(s, []).append(
                        dict(t=day + "T04:00:00Z", o=100.0, c=100.0, h=101.0, l=99.0, v=1, n=1)
                    )
                bodies.append(
                    dict(
                        bars=bars,
                        next_page_token="private-next" if lo + 9000 < len(cells) else None,
                    )
                )
        pages = []
        for i, body in enumerate(bodies):
            stem = root / "source" / f"{group}-{request['key']}-{i:03}"
            query = dict(params)
            if i:
                query["page_token"] = "private-next"
            response = dump(stem.with_suffix(".raw"), body)
            intent = dump(
                stem.with_suffix(".started.json"),
                dict(
                    endpoint=request["endpoint"], params=query, retry=0, at="2026-10-26T00:20:00Z"
                ),
            )
            meta = dump(
                stem.with_suffix(".json"),
                dict(
                    endpoint=request["endpoint"],
                    params=query,
                    intent=intent,
                    response=response,
                    status_code=200,
                    received_at="2026-10-26T00:21:00Z",
                ),
            )
            pages.append(dict(metadata=meta, response=response))
        index.append(dict(group=group, key=request["key"], pages=pages))
    source = dict(
        application_day="2026-10-26",
        reference_day="2026-10-23",
        prior_reference_day="2026-10-22",
        captured_at="2026-10-26T00:22:00Z",
        source_plan=f.binding(producer.N / "next-session-source-plan-M1.json"),
        formation_request_contract=contract,
        data=index,
        physical_GETs=sum(len(x["pages"]) for x in index),
        full_pagination=True,
    )
    dump(root / "current-source.json", source)
    now = datetime.fromisoformat("2026-10-26T01:00:00+00:00")
    native.receive_source_inventory(
        root, now=now
    )  # Historical H5 gap does not hide current complete controls.
    raw = {}
    for item in index:
        if item["group"] == "core" and item["key"] == "raw-bars":
            for page in item["pages"]:
                for s, rows in f.load(page["response"]["path"])["bars"].items():
                    for row in rows:
                        raw[s, row["t"][:10]] = row
    with pytest.raises(f.FormationDependency, match="missing complete"):
        f.feature_input(previous, raw, [], "2026-10-23")
    lineage = producer.build_action_lineage(root, "2026-10-23", "2026-10-26")
    lineage_row = dump(root / "action-lineage-QA.json", lineage)
    dump(
        root / "current-actions.json",
        dict(
            reference_day="2026-10-23",
            application_day="2026-10-26",
            retained_action_lineage=lineage_row,
        ),
    )
    rows = {}
    saved = REPO / "reports/paper/diagnostics/resume-20261022/target-refresh/integration-targets"
    for policy in ["BASE", "LSTM"]:
        value = f.load(saved / (policy + ".json"))
        value.update(
            reference_day="2026-10-23",
            application_day="2026-10-26",
            as_of="2026-10-23T20:00:00Z",
            valid_until="2026-10-26T19:30:00Z",
            source=f.binding(root / "current-source.json"),
            retained_action_lineage=lineage_row,
        )
        value["reference_marks"] = {s: 100.0 for s in value["reference_marks"]}
        rows[policy] = dump(root / "targets" / (policy + ".json"), value)
    blocked = {
        p: "Private H5 required historical support is missing"
        for p in ["H5", "BASE_STATE_BUDGET", "MULTI_EQUAL", "MULTI_HIERARCHICAL"]
    }
    deps = dump(
        root / "policy-dependencies.json",
        dict(blocked=blocked, source=f.binding(root / "current-source.json")),
    )
    dump(
        root / "target-production-result.json",
        dict(
            source=f.binding(root / "current-source.json"),
            application_day="2026-10-26",
            targets=rows,
            blocked_policies=blocked,
            dependency_manifest=deps,
        ),
    )
    # Exact host pure target/cents receiver, extracted without a financial import.
    path = REPO / "open_composer/intraday_runner/six_paper_service.py"
    tree = ast.parse(path.read_bytes())
    nodes = []
    for n in tree.body:
        if isinstance(n, ast.FunctionDef) and n.name in ["instant", "validate_target"]:
            nodes.append(n)
        if isinstance(n, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id in ["CHILDREN", "CHILD_CAPITAL", "CHILD_STOPS"]
            for t in n.targets
        ):
            nodes.append(n)
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "SixPaperService")
    nodes.append(
        next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == "target_books")
    )
    ns = dict(math=math, datetime=datetime, UTC=UTC)
    exec(
        compile(
            ast.fix_missing_locations(ast.Module(body=nodes, type_ignores=[])), str(path), "exec"
        ),
        ns,
    )
    fake = ModuleType("open_composer.intraday_runner.six_paper_service")
    fake.SixPaperService = SimpleNamespace(target_books=ns["target_books"])
    monkeypatch.setitem(sys.modules, fake.__name__, fake)
    assert set(native.receive_packet(root, now=now)) == {"BASE", "LSTM"}

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return now

    monkeypatch.setattr(native, "datetime", Clock)
    live = tmp_path / "live"
    live.mkdir()
    monkeypatch.setattr(native, "TARGETS", live)
    for p in native.POLICIES:
        (live / (p + ".json")).write_text("exact prior " + p)
    assert set(native.publish_packet(root, now=now)) == {"BASE", "LSTM"}
    for p in blocked:
        assert (live / (p + ".json")).read_text() == "exact prior " + p
    assert not (root / "targets/H5.json").exists()


def test_current_STATE_and_embedded_causal_linkage(tmp_path):
    # Valid upstream reception is assumed; only invented dependent views are used.
    origin = f.binding(f.T / "inference/BASE/output.json")
    symbols = f.load(origin["path"])["symbols"]
    common = dict(
        source=dict(private=True),
        reference_day="2026-10-23",
        application_day="2026-10-26",
        as_of="2026-10-23T20:00:00Z",
        valid_until="2026-10-26T19:30:00Z",
        computed_at="2026-10-26T01:00:00+00:00",
    )
    base = dict(
        common, policy="BASE", symbols=symbols[:5], weights=[0.2] * 5, held_model_origin=origin
    )
    h5 = dict(common, policy="H5", K=5, signal_forecast=dict(private_immutable_forecast=True))
    rows = dict(BASE=dump(tmp_path / "BASE.json", base), H5=dump(tmp_path / "H5.json", h5))
    state = dict(
        common,
        policy="BASE_STATE_BUDGET",
        symbols=symbols[:5],
        weights=[0.2] * 5,
        K=5,
        is_fresh_prediction=False,
        duplicates_BASE_now=True,
        held_model_origins=[origin, h5["signal_forecast"]],
        causal_inputs=copy.deepcopy(rows),
        cash_cause="causal_H5_K_scaling_of_current_BASE",
    )
    for k in range(6):
        hh = dict(h5, K=k)
        ss = dict(
            state,
            K=k,
            duplicates_BASE_now=k == 5,
            symbols=symbols[:5] if k else [],
            weights=[0.2 * k / 5] * 5 if k else [],
        )
        result = f.receive_state_instruction(ss, base, hh, base_row=rows["BASE"], h5_row=rows["H5"])
        assert (
            result["symbols"] == symbols
            and len(result["weights"]) == 28
            and result["weights"][5:] == [0.0] * 23
        )
    native.receive_current_dependencies(dict(BASE=base, H5=h5, BASE_STATE_BUDGET=state), rows)
    for change in [
        dict(K=0, symbols=[], weights=[]),
        dict(weights=[0.1] * 5),
        dict(held_model_origins=[origin, {}]),
        dict(causal_inputs={}),
        dict(duplicates_BASE_now=False),
        dict(cash_cause="unexplained"),
        dict(application_day="2026-10-27"),
        dict(computed_at="2026-10-26T00:59:00+00:00"),
        dict(symbols=list(reversed(symbols[:5]))),
    ]:
        bad = dict(state, **change)
        with pytest.raises(AssertionError):
            native.receive_current_dependencies(dict(BASE=base, H5=h5, BASE_STATE_BUDGET=bad), rows)
    children = {n: dict(name=n, private=True) for n in ["S1", "S2", "S3", "C2"]}
    children.update(BASE=dict(base, name="BASE"), H5=dict(h5, name="H5"))
    equal = {
        n: dict(v, capital_usd=c / 100)
        for (n, v), c in zip(
            children.items(), [333334, 333334, 333333, 333333, 333333, 333333], strict=True
        )
    }
    hierarchical = {
        n: dict(v, capital_usd=c / 100)
        for (n, v), c in zip(
            children.items(), [166667, 166667, 166666, 500000, 500000, 500000], strict=True
        )
    }
    targets = dict(
        BASE=base,
        H5=h5,
        MULTI_EQUAL=dict(children=equal),
        MULTI_HIERARCHICAL=dict(children=hierarchical),
    )
    native.receive_current_dependencies(targets, rows)
    bad = copy.deepcopy(targets)
    bad["MULTI_HIERARCHICAL"]["children"]["H5"]["K"] = 0
    with pytest.raises(AssertionError):
        native.receive_current_dependencies(bad, rows)
    bad = copy.deepcopy(targets)
    bad["MULTI_EQUAL"]["children"]["BASE"]["held_model_origin"] = {}
    with pytest.raises(AssertionError):
        native.receive_current_dependencies(bad, rows)


def test_frozen_BASE_action_anchor_survives_date_translation():
    import ast
    from collections import defaultdict

    tree = ast.parse(Path(producer.__file__).read_text())
    dated = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "dated")
    boundary = next(n for n in dated.body if isinstance(n, ast.ClassDef) and n.name == "Boundary")
    ns = dict(
        ast=ast,
        copy=copy,
        date=producer.date,
        adoption=False,
        prev="2026-10-22",
        ref="2026-10-23",
        app="2026-10-26",
    )
    exec(
        compile(
            ast.fix_missing_locations(ast.Module(body=[boundary], type_ignores=[])),
            "private_actual_boundary",
            "exec",
        ),
        ns,
    )
    original = ast.parse(Path(producer.ni.__file__).read_text())
    node = next(
        n for n in original.body if isinstance(n, ast.FunctionDef) and n.name == "base_input"
    )
    translated = ns["Boundary"]().visit(copy.deepcopy(node))
    call = next(
        n
        for n in ast.walk(translated)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Attribute)
        and n.func.attr == "merge_actions"
    )
    assert call.args[-1].value == "2026-10-19"
    dates = {
        n.value
        for n in ast.walk(translated)
        if isinstance(n, ast.Constant) and type(n.value) is str
    }
    assert "2026-10-23" in dates  # The actual current reference still advances.
    path = (
        producer.P
        / "owner-profit-delivery-plan-20261017/candidate-contribution"
        / "future-input-receiver/features.py"
    )
    fn = next(
        n
        for n in ast.parse(path.read_text()).body
        if isinstance(n, ast.FunctionDef) and n.name == "merge_actions"
    )
    namespace = dict(UNITS={"AAPL"}, defaultdict=defaultdict)
    exec(
        compile(
            ast.fix_missing_locations(ast.Module(body=[fn], type_ignores=[])), str(path), "exec"
        ),
        namespace,
    )
    event = dict(id="PRIVATE-received-cash", symbol="AAPL", ex_date="2026-10-22", rate=0.1)

    def batch(value):
        return [dict(corporate_actions=dict(cash_dividends=[value]))]

    merged = namespace["merge_actions"]({}, batch(event), call.args[-1].value)
    assert merged["cash_dividends"] == [event]
    assert (
        namespace["merge_actions"](
            merged, batch(dict(event, process_date="2026-10-23")), call.args[-1].value
        )
        == merged
    )
    with pytest.raises(AssertionError, match="Changed accepted"):
        namespace["merge_actions"](merged, batch(dict(event, rate=0.2)), call.args[-1].value)
    with pytest.raises(AssertionError, match="retrospective"):
        namespace["merge_actions"](
            {},
            batch(dict(event, id="PRIVATE-unreceived", ex_date="2026-10-18")),
            call.args[-1].value,
        )


def test_actual_assembly_to_dependency_with_capital_wrapper(tmp_path, monkeypatch):
    root = tmp_path / "assembled"
    root.mkdir()
    source = dump(
        root / "current-source.json",
        dict(reference_day="2026-10-23", application_day="2026-10-26", private=True),
    )
    common = dict(
        source=source,
        reference_day="2026-10-23",
        application_day="2026-10-26",
        as_of="2026-10-23T20:00:00Z",
        valid_until="2026-10-26T19:30:00Z",
        computed_at="2026-10-26T01:00:00+00:00",
    )
    base = dict(
        common, policy="BASE", symbols=["AAPL"], weights=[0.2], private_upstream_received=True
    )
    h5 = dict(
        common, policy="H5", symbols=["INTC"], weights=[0.2], K=5, private_upstream_received=True
    )
    children = {
        n: dict(name=n, symbols=["SPY"], weights=[1.0], source=source)
        for n in ["S1", "S2", "S3", "C2"]
    }
    children.update(BASE=dict(base, name="BASE"), H5=dict(h5, name="H5"))
    dump(root / "current-constituents.json", children)
    dump(root / "current-marks.json", dict(AAPL=100.0, INTC=100.0, SPY=100.0))
    monkeypatch.setattr(producer, "receive_current_paper_maintenance", lambda: None)
    monkeypatch.setattr(producer, "receive_action_lineage", lambda root: dict(private=True))
    producer.assemble(root)  # Actual unchanged assembly and target storage, private directory only.
    targets = dict(BASE=base, H5=h5)
    targets.update(
        {p: f.load(root / "targets" / (p + ".json")) for p in ["MULTI_EQUAL", "MULTI_HIERARCHICAL"]}
    )
    assert not f.load(root / "assembly-dependencies.json")
    native.receive_current_dependencies(targets, {})
    for policy, expected in [
        ("MULTI_EQUAL", [333334, 333334, 333333, 333333, 333333, 333333]),
        ("MULTI_HIERARCHICAL", [166667, 166667, 166666, 500000, 500000, 500000]),
    ]:
        assert [row["capital_usd"] for row in targets[policy]["children"]] == [
            c / 100 for c in expected
        ]
        for change in ["capital", "scientific", "undeclared", "missing", "duplicate"]:
            bad = copy.deepcopy(targets)
            rows = bad[policy]["children"]
            if change == "capital":
                rows[-1]["capital_usd"] += 0.01
            elif change == "scientific":
                rows[-1]["weights"] = [0.1]
            elif change == "undeclared":
                rows[-1]["new_wrapper_claim"] = True
            elif change == "missing":
                rows.pop()
            else:
                rows[-1]["name"] = "BASE"
            with pytest.raises(AssertionError):
                native.receive_current_dependencies(bad, {})


def test_november_model_pair_changes_at_formation_and_remains_held(
    previous, tiny_features, tmp_path, monkeypatch
):
    """Real consumer/receiver paths with invented states; no fit or market source."""
    from datetime import date

    from open_composer.market_sessions import us_equity_session_dates
    from open_composer.paper_runtime.six import h5_monthly

    root = tmp_path / "november"
    root.mkdir()
    source = dump(
        root / "current-source.json",
        dict(
            reference_day="2026-11-06",
            application_day="2026-11-09",
            captured_at="2026-11-09T00:30:00+00:00",
            private_fixture=True,
        ),
    )
    dump(root / "action-lineage-QA.json", dict(current_source=source))
    dump(
        root / "current-h5-support.json",
        dict(source=source, reference_day="2026-11-06", application_day="2026-11-09"),
    )
    monthly_row = dump(
        tmp_path / "monthly.json",
        dict(completed_at="2026-11-03T08:00:00+00:00", private_fixture=True),
    )
    models = [
        dict(path="private-November-" + arm, sha256="fixture", bytes=0)
        for arm in ["STOCK", "STATE"]
    ]
    november_states = tiny_states()
    # Distinct November scores establish that daily consumption uses the new pair.
    november_states["STATE"]["tree_dump"]["tree_info"][0]["tree_structure"]["leaf_value"] = -0.02
    monkeypatch.setattr(f, "states", lambda value: tiny_states())
    monkeypatch.setattr(
        h5_monthly,
        "current",
        lambda observation, **kw: (
            monthly_row,
            dict(cutoff="2026-10-30", models=[dict(state=r) for r in models]),
            november_states,
        ),
    )
    features = copy.deepcopy(tiny_features)
    features.update(
        reference_day="2026-11-06",
        support_sessions=[
            d.isoformat() for d in us_equity_session_dates(date(2026, 9, 30), date(2026, 11, 6))
        ],
    )
    calls = []

    def received_features(*args, **kwargs):
        calls.append("features")
        return copy.deepcopy(features)

    monkeypatch.setattr(f, "feature_input", received_features)
    current = dict(current_eligible=features["eligible"])
    formed = f.h5_decision(
        previous,
        current,
        {},
        [],
        "2026-11-06",
        "2026-11-09",
        write=dump,
        root=root,
        now=lambda: "2026-11-09T01:00:00+00:00",
    )
    assert formed["model_epoch"] == "2026-11" and formed["allocation"]["K"] == 0
    assert formed["is_fresh_prediction"] and formed["portfolio_action"] == "rebalance"
    forecast = f.load(formed["signal_forecast"]["path"])
    assert forecast["models"] == models and forecast["monthly_models"] == monthly_row
    assert forecast["model_cutoff"] == "2026-10-30" and forecast["new_fits"] == 0
    target = dict(
        formed,
        policy="H5",
        reference_day="2026-11-06",
        application_day="2026-11-09",
        source=source,
        symbols=[],
        weights=[],
        K=0,
    )
    f.receive_h5_instruction(root, target)
    private_runtime = tmp_path / "runtime"
    dump(private_runtime / "targets/H5.json", target)
    monkeypatch.setattr(f, "runtime_root", lambda root: private_runtime)
    held = f.h5_decision(
        previous,
        current,
        {},
        [],
        "2026-11-09",
        "2026-11-10",
        write=dump,
        root=root,
        now=lambda: "2026-11-10T01:00:00+00:00",
    )
    assert held["model_epoch"] == "2026-11" and held["allocation"] == formed["allocation"]
    assert not held["is_fresh_prediction"] and held["portfolio_action"] == "hold"
    assert calls == ["features"]
    # Later genuine formations continue requesting the complete connected prefix.
    for ref, app in [("2026-11-13", "2026-11-16"), ("2026-11-20", "2026-11-23")]:
        contract = f.source_contract(ref, app)
        assert contract["formation_due"] and contract["raw_support_start"] == "2026-09-30"
        menu = f.request_menu(f.load(producer.N / "next-session-source-plan-M1.json"), contract)
        assert (
            next(r for g, r in menu if (g, r["key"]) == ("core", "raw-bars"))["params"]["start"]
            == "2026-09-30T00:00:00Z"
        )
    wrong = dict(forecast, models=previous["historical_model_provenance"]["adopted"]["states"])
    with pytest.raises(f.FormationDependency, match="Foreign H5 formation models"):
        f.origin(dump(root / "wrong-old-models.json", wrong))
    late_row = dump(tmp_path / "not-yet-fit.json", dict(completed_at="2026-11-10T00:00:00+00:00"))
    monkeypatch.setattr(
        h5_monthly,
        "current",
        lambda observation, **kw: (
            late_row,
            dict(cutoff="2026-10-30", models=[dict(state=r) for r in models]),
            november_states,
        ),
    )
    with pytest.raises(f.FormationDependency, match="precedes actual monthly-model"):
        f.origin(dump(root / "too-late-model.json", dict(forecast, monthly_models=late_row)))


def test_h5_monthly_date_domain_is_not_an_october_fallback(tmp_path):
    from open_composer.paper_runtime.six import h5_monthly

    for day in ["2026-10-30", "2026-11-05", "2026-12-01"]:
        with pytest.raises(AssertionError, match="Unreceived H5 observation month"):
            h5_monthly.current(day, root=tmp_path)
    with pytest.raises(FileNotFoundError):
        h5_monthly.current("2026-11-06", root=tmp_path)
