# ruff: noqa: E402 -- Runtime paths and frozen-source imports initialize in order.
"""Date-bound maintenance adapter for the existing six frozen paper policies.

Stages write only diagnostics. The sole native paper operator integrates targets.
No fits, account calls, funding, scheduling, or service invocation are present.
"""

import argparse
import ast
import copy
import hashlib
import json
import math
import os
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from open_composer.market_sessions import us_equity_session_close, us_equity_session_dates
from open_composer.paper_runtime.paths import repo_root, runtime_root
from open_composer.research.features.price_hygiene import sanitize_price_matrices

REPO = repo_root()
P = REPO / "reports/research/program"
OLD = P / "paper-launch-20min-20261021"
T = P / "owner-profit-delivery-plan-20261017/current-paper-science-20261020"
N = T / "next-session-20261021"
from open_composer.paper_runtime.source_loader import (
    install_source_imports,
    load_source,
    source_bytes,
)

install_source_imports(REPO)
sys.path.insert(0, str(N))
import next_control_input as controls
import next_current_input as ni
import next_session_data as data

from open_composer.paper_runtime.six.formation_continuity import (
    FormationDependency,
    h5_decision,
    monthly_base_supported,
    partition,
)
from open_composer.paper_runtime.six.paper_target_input_controls import (
    active_baseline,
    build_action_lineage,
    receive_action_lineage,
    receive_current_paper_maintenance,
)


def load(p):
    return json.loads(Path(p).read_text())


def bind(p):
    p = Path(p)
    b = p.read_bytes()
    return dict(path=str(p.resolve()), bytes=len(b), sha256=hashlib.sha256(b).hexdigest())


def checked(r):
    assert bind(r["path"]) == r
    return Path(r["path"])


def clean(v):
    if isinstance(v, np.ndarray):
        return clean(v.tolist())
    if isinstance(v, np.generic):
        return clean(v.item())
    if isinstance(v, dict):
        return {k: clean(x) for k, x in v.items()}
    if isinstance(v, (tuple, list)):
        return [clean(x) for x in v]
    return v


def save(p, v):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    b = (json.dumps(clean(v), indent=2, allow_nan=False) + "\n").encode()
    with p.open("x") as f:
        f.write(b.decode())
        f.flush()
        os.fsync(f.fileno())
    return bind(p)


def mod(name, p):
    return load_source(name, p, root=REPO)


def dated(fn, prev, ref, app, *, namespace=None, adoption=False):
    node = next(
        n
        for n in ast.parse(Path(sys.modules[fn.__module__].__file__).read_text()).body
        if isinstance(n, ast.FunctionDef) and n.name == fn.__name__
    )

    class Boundary(ast.NodeTransformer):
        def visit_Constant(self, n):
            if (
                not adoption
                and type(n.value) is str
                and n.value in ["2026-10-19", "2026-10-20", "2026-10-21"]
            ):
                return ast.copy_location(
                    ast.Constant(
                        {"2026-10-19": prev, "2026-10-20": ref, "2026-10-21": app}[n.value]
                    ),
                    n,
                )
            return n

        def visit_Call(self, n):
            if isinstance(n.func, ast.Attribute) and n.func.attr == "merge_actions":
                assert isinstance(n.args[-1], ast.Constant) and n.args[-1].value == "2026-10-19"
                anchor = copy.deepcopy(n.args[-1])
                n = self.generic_visit(n)
                n.args[-1] = anchor
                return n
            return self.generic_visit(n)

        def visit_Compare(self, n):
            if (
                adoption
                and isinstance(n.left, ast.Subscript)
                and isinstance(n.left.value, ast.Name)
                and n.left.value.id in ["current_input", "current_controls"]
                and isinstance(n.left.slice, ast.Constant)
            ):
                key = n.left.slice.value
                if key in ["reference_day", "application_day"] and len(n.comparators) == 1:
                    n.comparators = [ast.Constant(ref if key == "reference_day" else app)]
            return self.generic_visit(n)

        def visit_keyword(self, n):
            if adoption and n.arg in ["reference_day", "application_day"]:
                n.value = ast.Constant(ref if n.arg == "reference_day" else app)
            return self.generic_visit(n)

        def visit_AugAssign(self, n):
            if (
                isinstance(n.target, ast.Subscript)
                and isinstance(n.target.slice, ast.Constant)
                and n.target.slice.value == "current_calendar_age"
            ):
                n.value = ast.Constant((date.fromisoformat(ref) - date(2026, 10, 19)).days)
            return self.generic_visit(n)

    node = Boundary().visit(node)
    ns = dict(fn.__globals__)
    if namespace:
        ns.update(namespace)
    exec(
        compile(
            ast.fix_missing_locations(ast.Module(body=[node], type_ignores=[])),
            str(Path(sys.modules[fn.__module__].__file__)),
            "exec",
        ),
        ns,
    )
    return ns[fn.__name__]


def pages(source):
    result = {}
    for row in source["data"]:
        bodies = []
        for p in row["pages"]:
            if "metadata" in p:
                meta = load(checked(p["metadata"]))
                assert meta["status_code"] == 200 and meta["response"] == p["response"]
                bodies.append(load(checked(p["response"])))
            else:
                bodies.append(p)
        assert bodies[-1].get("next_page_token") is None
        result[row["group"], row["key"]] = bodies
    return result


def bars(objects):
    out = {}
    for p in objects:
        for s, rs in p["bars"].items():
            for r in rs:
                key = (s, r["t"][:10])
                assert key not in out, "duplicate source cell"
                assert all(math.isfinite(r[k]) and r[k] > 0 for k in ["o", "h", "l", "c"])
                out[key] = r
    return out


def session_clocks(ref, app):
    refday, appday = map(date.fromisoformat, [ref, app])
    rc, ac = us_equity_session_close(refday), us_equity_session_close(appday)
    assert rc is not None and ac is not None
    prior_close = datetime.combine(refday, rc, tzinfo=ZoneInfo("America/New_York")).astimezone(UTC)
    expiry = datetime.combine(appday, ac, tzinfo=ZoneInfo("America/New_York")).astimezone(
        UTC
    ) - timedelta(minutes=30)
    return prior_close.isoformat().replace("+00:00", "Z"), expiry.isoformat().replace("+00:00", "Z")


def target(root, policy, symbols, weights, marks, source, ref, app, **extra):
    pairs = [(s, float(w)) for s, w in zip(symbols, weights, strict=True) if w > 0]
    assert len(set(symbols)) == len(symbols) and sum(w for _, w in pairs) <= 1 + 1e-12
    assert all(s in marks and math.isfinite(marks[s]) and marks[s] > 0 for s, _ in pairs)
    prior = load(runtime_root(REPO) / "targets" / (policy + ".json"))
    same = dict(zip(prior["symbols"], prior["weights"], strict=False)) == dict(pairs)
    asof, expiry = session_clocks(ref, app)
    v = dict(
        policy=policy,
        as_of=asof,
        reference_day=ref,
        application_day=app,
        valid_until=expiry,
        portfolio_action="hold" if same else "rebalance",
        symbols=[s for s, _ in pairs],
        weights=[w for _, w in pairs],
        reference_marks=marks,
        source=bind(root / "current-source.json"),
        computed_at=datetime.now(UTC).isoformat(),
        new_fit_count=0,
        is_fresh_prediction=False,
        initial_missing_allocation_may_be_completed=False,
        prior_target=bind(runtime_root(REPO) / "targets" / (policy + ".json")),
        weights_unchanged=same,
        current_inputs_are_new_but_held_prediction_is_not_new=True,
    )
    v.update(extra)
    v["current_inputs_are_new_but_held_prediction_is_not_new"] = not v["is_fresh_prediction"]
    v["retained_action_lineage"] = receive_action_lineage(root)
    save(root / "targets" / (policy + ".json"), v)
    return v


def prepare_core(root, source, obj, control, previous, normalized, raw, marks, bad, action_parser):
    prev, ref, app = (
        source["prior_reference_day"],
        source["reference_day"],
        source["application_day"],
    )
    raw_start = source["formation_request_contract"]["raw_support_start"]
    base_start = max(raw_start, "2026-10-19")
    support_days = [
        d.isoformat()
        for d in us_equity_session_dates(date.fromisoformat(base_start), date.fromisoformat(ref))
    ]
    base_pages = [
        dict(
            bars={
                s: [row for row in rows if row["t"][:10] >= base_start]
                for s, rows in page["bars"].items()
            }
        )
        for page in obj["core", "raw-bars"]
    ]
    proxy = SimpleNamespace(**vars(data))
    proxy.core_bars = lambda ps, syms, *, inactive=(): data.original("core", "raw_rows")(
        ps, syms, support_days, inactive
    )
    proxy.core_actions = lambda ps, syms: action_parser(ps, syms)
    blocked = {}
    b = None
    h = None
    oldbase = load(T / "inference/BASE/output.json")
    base_symbols = oldbase["symbols"]
    try:
        monthly_forecast = monthly_base_supported(app)
        if monthly_forecast is None:
            current = dated(ni.base_input, prev, ref, app, namespace={"data": proxy})(
                control, {}, {"raw-bars": base_pages, "actions": obj["core", "actions"]}, previous
            )
        else:
            from open_composer.paper_runtime.six.monthly_base_model import daily_controls

            current = daily_controls(
                monthly_forecast, root=REPO, reference_day=ref, control=control,
                raw_objects=obj["core", "raw-bars"],
                action_objects=obj["core", "actions"],
            )
        current = clean(current)
        current.update(reference_day=ref, application_day=app)
        current["current_daily_eligible"] = [
            bool(e) and s not in bad
            for s, e in zip(current["symbols"], current["current_daily_eligible"], strict=True)
        ]
        current["eligible"] = [
            a and b
            for a, b in zip(
                current["formation_eligible"], current["current_daily_eligible"], strict=True
            )
        ]
        if monthly_forecast is None:
            base = dated(data.BASE_adoption, prev, ref, app, adoption=True)(
                previous["BASE"][0], oldbase, current
            )
            origin = dict(
                held_model_origin=bind(T / "inference/BASE/output.json"),
                held_signal_observation="2026-10-19",
                held_signal_application="2026-10-20",
                original_computed_at=oldbase["computed_completed_at"],
            )
        else:
            from open_composer.paper_runtime.six.monthly_base_model import current_instruction

            instruction = current_instruction(
                monthly_forecast,
                root=REPO,
                application_day=app,
                current_daily_eligible=current["current_daily_eligible"],
            )
            assert instruction["symbols"] == current["symbols"]
            base_symbols = instruction["symbols"]
            base = dict(allocation=dict(weights=instruction["weights"]))
            # The held monthly design lives in the newly sealed packet. Retain
            # only current daily controls here, never relabel the old design.
            current = dict(
                reference_day=ref,
                application_day=app,
                source=bind(root / "current-source.json"),
                symbols=base_symbols,
                monthly_forecast=monthly_forecast,
                formation_eligible=[
                    bool(v)
                    for v in load(checked(monthly_forecast))["eligible"]
                ],
                current_daily_eligible=current["current_daily_eligible"],
                eligible=instruction["eligible"],
                raw_reference_marks=current["raw_reference_marks"],
                current_actions=current["current_actions"],
            )
            origin = {
                key: instruction[key]
                for key in [
                    "held_model_origin", "held_signal_observation",
                    "held_signal_application", "original_computed_at",
                    "owner_date_exception", "new_fit_count",
                    "is_fresh_prediction", "historical_timely_source_claim",
                ]
            }
            prior_base = load(runtime_root(REPO) / "targets/BASE.json")
            origin["new_monthly_model_adoption"] = (
                prior_base.get("held_model_origin") != monthly_forecast
            )
            if origin["new_monthly_model_adoption"]:
                # A genuine monthly event still rebalances when its roster and
                # weights match the previous month; daily repeats then hold.
                origin["portfolio_action"] = "rebalance"
        save(root / "current-base-input.json", current)
        if monthly_forecast is not None:
            origin["monthly_current_input"] = bind(root / "current-base-input.json")
        b = target(
            root,
            "BASE",
            base_symbols,
            base["allocation"]["weights"],
            marks,
            source,
            ref,
            app,
            **origin,
            allocation_intent=(
                "original_monthly_BASE_with_current_daily_eligibility"
                if monthly_forecast is not None
                else "complete_unfulfilled_initial_allocation_only_after_operating_prefix_acceptance"
            ),
        )
    except (ValueError, AssertionError, KeyError, FileNotFoundError) as error:
        blocked["BASE"] = "BASE current method/input dependency: " + str(error)
    try:
        hcurrent = ni.h5_input(control, previous)
        hcurrent.update(
            reference_day=ref, application_day=app, source=bind(root / "current-source.json")
        )
        save(root / "current-h5-support.json", hcurrent)
        h5 = h5_decision(
            previous["H5"][0],
            hcurrent,
            raw,
            normalized,
            ref,
            app,
            write=save,
            root=root,
            now=lambda: datetime.now(UTC).isoformat(),
        )
        carriers = previous["H5"][0]["controls"]["carriers"]
        h = target(
            root,
            "H5",
            [carriers.get(s) or s for s in hcurrent["symbols"]],
            h5["allocation"]["weights"],
            marks,
            source,
            ref,
            app,
            signal_forecast=h5["signal_forecast"],
            signal_observation=h5["signal_observation"],
            signal_application=h5["signal_application"],
            original_computed_at=h5["original_computed_at"],
            next_regular_observation=h5["phase"]["next_observation"],
            next_regular_application=h5["phase"]["next_application"],
            model_epoch=h5["model_epoch"],
            is_fresh_prediction=h5["is_fresh_prediction"],
            portfolio_action=h5["portfolio_action"],
            K=h5["allocation"]["K"],
            allocation_intent="complete_unfulfilled_initial_allocation_only_after_operating_prefix_acceptance",
        )
    except FormationDependency as error:
        blocked["H5"] = str(error)
    if b is not None and h is not None:
        monthly_event = (
            dict(portfolio_action="rebalance", new_monthly_model_adoption=True)
            if b.get("new_monthly_model_adoption")
            else {}
        )
        target(
            root,
            "BASE_STATE_BUDGET",
            base_symbols,
            [w * h["K"] / 5 for w in base["allocation"]["weights"]],
            marks,
            source,
            ref,
            app,
            K=h["K"],
            duplicates_BASE_now=h["K"] == 5,
            held_model_origins=[b["held_model_origin"], h["signal_forecast"]],
            causal_inputs=dict(
                BASE=bind(root / "targets/BASE.json"), H5=bind(root / "targets/H5.json")
            ),
            cash_cause="causal_H5_K_scaling_of_current_BASE",
            allocation_intent="complete_unfulfilled_initial_allocation_only_after_operating_prefix_acceptance",
            **monthly_event,
        )
    else:
        blocked["BASE_STATE_BUDGET"] = (
            "Current BASE and causal H5 K are both required; no cash or stale-K replacement"
        )
    save(root / "prepare-dependencies.json", blocked)
    return b, h


def prepare(root):
    receive_current_paper_maintenance()
    source = load(root / "current-source.json")
    ref, app, prev = (
        source["reference_day"],
        source["application_day"],
        source["prior_reference_day"],
    )
    assert app == datetime.now(UTC).date().isoformat()
    obj = pages(source)
    raw = bars(obj["core", "raw-bars"])
    other = bars(obj["ETF", "raw-reference"])
    for k, v in other.items():
        if k in raw:
            assert all(raw[k][f] == v[f] for f in ["o", "c"]), "Shared source raw basis differs"
    raw.update(other)
    symbols = sorted({s for s, d in raw})
    days = [prev, ref]
    close = pd.DataFrame(
        {s: [raw.get((s, d), {}).get("c", np.nan) for d in days] for s in symbols},
        index=pd.to_datetime(days),
    )
    opening = pd.DataFrame(
        {s: [raw.get((s, d), {}).get("o", np.nan) for d in days] for s in symbols},
        index=pd.to_datetime(days),
    )
    _, _, qa = sanitize_price_matrices(close, opening)
    bad = {b.symbol for b in qa.breaks}
    marks = {s: float(raw[s, ref]["c"]) for s in symbols if (s, ref) in raw}
    core = load(N / "next-session-source-plan-M1.json")["core"]["raw_symbols"]
    # Original action parser: only the current reference/application boundary advances.
    original = data.original("core", "action_pages")
    node = next(
        n
        for n in ast.parse(source_bytes(T / "current_input.py", root=REPO)).body
        if isinstance(n, ast.FunctionDef) and n.name == "action_pages"
    )

    class ActionDate(ast.NodeTransformer):
        def visit_Constant(self, n):
            return (
                ast.copy_location(ast.Constant({"2026-10-19": ref, "2026-10-20": app}[n.value]), n)
                if type(n.value) is str and n.value in ["2026-10-19", "2026-10-20"]
                else n
            )

    ns = dict(original.__globals__)
    exec(
        compile(
            ast.fix_missing_locations(ast.Module(body=[ActionDate().visit(node)], type_ignores=[])),
            str(T / "current_input.py"),
            "exec",
        ),
        ns,
    )
    _actions = ns["action_pages"](obj["core", "actions"], core)
    lineage = build_action_lineage(root, ref, app)
    lineage_row = save(root / "action-lineage-QA.json", lineage)
    normalized = controls.normalize_events(
        lineage["events"],
        retained_alias_lineage={
            "source": bind(T / "input/BASE/output.json"),
            "review": bind(T / "independent-current-input-review-BASE.json"),
        },
    )
    control = dict(
        reference_day=ref,
        application_day=app,
        symbols={
            s: dict(
                supported=s in marks
                and all(
                    (s, d) in raw and raw[s, d].get("v", 0) > 0 and raw[s, d].get("n", 0) > 0
                    for d in days
                )
                and s not in bad,
                raw_close=marks.get(s),
            )
            for s in set(core) | set(symbols)
        },
        current_actions_by_group={"core": normalized},
    )
    previous = {
        p: (load(T / "input" / p / "output.json"), bind(T / "input" / p / "output.json"), None)
        for p in ["BASE", "H5", "LSTM"]
    }
    save(root / "current-marks.json", marks)
    save(
        root / "current-actions.json",
        dict(
            events=normalized,
            retained_action_lineage=lineage_row,
            source=bind(root / "current-source.json"),
            application_day=app,
            reference_day=ref,
            unknown_older_alias_economic_dates_preserved=True,
            dividend_entitlement_not_certified=True,
        ),
    )
    receive_action_lineage(root)
    b, h = prepare_core(
        root, source, obj, control, previous, normalized, raw, marks, bad, ns["action_pages"]
    )
    # Saved two-model recurrent inference inputs, original immutable2701-session prefix.
    old = previous["LSTM"][0]
    syms = old["symbols"]
    accepted = old["original_accepted"]
    cl = pd.read_parquet(checked(accepted["ETF-sanitized-close.parquet"]))[syms]
    op = pd.read_parquet(checked(accepted["ETF-sanitized-open.parquet"]))[syms]
    adjusted = bars(obj["core", "adjusted-tail"])
    prior_root, prior_target, oldsource = active_baseline()
    oldobj = pages(oldsource)
    oldtail = bars(oldobj["core", "adjusted-tail"])
    from open_composer.paper_runtime.six.adjusted_history import append_adjusted_history, cash_actions

    prior_qa = load(prior_root / "lstm-input-QA.json")
    old_scales = {s: float(prior_qa["basis"][s]["multiplier"]) for s in syms}
    if "canonical_close" in prior_qa:
        prior_cl = pd.read_parquet(checked(prior_qa["canonical_close"]))[syms]
        prior_op = pd.read_parquet(checked(prior_qa["canonical_open"]))[syms]
        assert np.array_equal(prior_cl.loc[cl.index], cl)
        assert np.array_equal(prior_op.loc[op.index], op)
        cl, op = prior_cl, prior_op
    else:
        for (symbol, day), row in oldtail.items():
            if symbol in syms and "2026-10-01" <= day <= oldsource["reference_day"]:
                cl.loc[pd.Timestamp(day), symbol] = row["c"] / old_scales[symbol]
                op.loc[pd.Timestamp(day), symbol] = row["o"] / old_scales[symbol]
        cl, op = cl.sort_index(), op.sort_index()
    op, cl, scales, revision = append_adjusted_history(
        op, cl, oldtail, adjusted, old_scales, cash_actions(obj["core", "actions"]),
        prior_reference=oldsource["reference_day"], reference=ref,
    )
    basis = {s: dict(multiplier=scales[s], **revision[s]) for s in syms}
    cc, oo, lqa = sanitize_price_matrices(cl, op)
    assert not lqa.breaks and np.array_equal(cc, cl) and np.array_equal(oo, op)
    methoddir = P / "return-line-replenishment-20261016/direct-position-learning-20261016"
    features = mod("refresh_original_features", methoddir / "prepare_features.py")
    x, vol, _ = features.features(cl)
    with np.load(checked(accepted["source-features.npz"]), allow_pickle=False) as z:
        assert np.array_equal(x[:2701], z["features"], equal_nan=True) and np.array_equal(
            vol[:2701], z["vol"], equal_nan=True
        )
    first = np.flatnonzero(cl.index.strftime("%Y-%m-%d") == "2026-01-02")[0]
    lo = first - 63
    x = x[lo:]
    vol = vol[lo:]
    expected = us_equity_session_dates(date(2026, 1, 2), date.fromisoformat(ref))
    assert (
        len(x) == len(expected) + 63
        and cl.index[-1].date() == date.fromisoformat(ref)
        and np.isfinite(x).all()
        and np.isfinite(vol).all()
    )
    with np.load(prior_root / "current-lstm-sequence.npz", allow_pickle=False) as prior:
        prefix = dict(
            rows=len(prior["features"]),
            features_bitexact=np.array_equal(x[: len(prior["features"])], prior["features"]),
            vol_bitexact=np.array_equal(vol[: len(prior["vol"])], prior["vol"]),
            max_feature_error=float(np.max(abs(x[: len(prior["features"])] - prior["features"]))),
        )
    save(root / "lstm-prior-prefix-QA.json", prefix)
    assert prefix["features_bitexact"] and prefix["vol_bitexact"], (
        "Retain changed prior prefix; no inference"
    )
    np.savez_compressed(root / "current-lstm-sequence.npz", features=x, vol=vol)
    cl.to_parquet(root / "LSTM-canonical-close.parquet")
    op.to_parquet(root / "LSTM-canonical-open.parquet")
    save(
        root / "lstm-input-QA.json",
        dict(
            sequence=bind(root / "current-lstm-sequence.npz"),
            prior_sequence=bind(prior_root / "current-lstm-sequence.npz"),
            canonical_close=bind(root / "LSTM-canonical-close.parquet"),
            canonical_open=bind(root / "LSTM-canonical-open.parquet"),
            full_sequence_rows=len(x),
            annual_sessions=len(expected),
            burnin_sessions=63,
            old2701_prefix_bitexact=True,
            previous_current_sequence=prefix,
            basis=basis,
            hygiene=lqa.manifest(),
            checkpoint_context=old["model_context"],
        ),
    )
    # Original ETF recipes and original causal overlay schedule; no new thresholds.
    from open_composer.adapters.execution import rotation_target_weights as rot
    from open_composer.models.strategy_spec import load_strategy_spec

    plan = load(N / "next-session-source-plan-M1.json")["ETF"]
    ar = bars(obj["ETF", "adjusted-history"])
    dates = us_equity_session_dates(date(2024, 1, 2), date.fromisoformat(ref))
    ss = plan["symbols"]
    assert set(ar) == {(s, d.isoformat()) for s in ss for d in dates}
    oldar = bars(oldobj["ETF", "adjusted-history"])
    prior_etf_qa = load(prior_root / "ETF-basis-QA.json")
    if "canonical_close" in prior_etf_qa:
        ec = pd.read_parquet(checked(prior_etf_qa["canonical_close"]))
        eo = pd.read_parquet(checked(prior_etf_qa["canonical_open"]))
        etf_scales = prior_etf_qa["divisors"]
    else:
        accepted_panel = pd.DataFrame([
            dict(symbol=s, trade_date=pd.Timestamp(d), open=r["o"], close=r["c"])
            for (s, d), r in oldar.items()
        ])
        ec = accepted_panel.pivot(index="trade_date", columns="symbol", values="close")
        eo = accepted_panel.pivot(index="trade_date", columns="symbol", values="open")
        etf_scales = {s: 1.0 for s in ec.columns}
    eo, ec, etf_scales, etf_revision = append_adjusted_history(
        eo, ec, oldar, ar, etf_scales, cash_actions(obj["ETF", "actions"]),
        prior_reference=oldsource["reference_day"], reference=ref,
    )
    ec.to_parquet(root / "ETF-canonical-close.parquet")
    eo.to_parquet(root / "ETF-canonical-open.parquet")
    save(root / "ETF-basis-QA.json", dict(
        canonical_close=bind(root / "ETF-canonical-close.parquet"),
        canonical_open=bind(root / "ETF-canonical-open.parquet"),
        divisors=etf_scales, source_revision=etf_revision,
        prior_OC_cells_compared=len(oldar) * 2, prior_canonical_cells_replaced=0,
        first_session=dates[0].isoformat(), last_session=dates[-1].isoformat(),
        sessions=len(dates), symbols=ss,
    ))
    panel = pd.DataFrame([
        dict(symbol=s, trade_date=d.date(), open=float(eo.loc[d, s]), close=float(ec.loc[d, s]))
        for s in ec.columns for d in ec.index
    ])
    ecl, eop, eqa = sanitize_price_matrices(ec, eo)
    assert (
        not eqa.breaks
        and np.array_equal(ecl, ec)
        and np.array_equal(eop, eo)
        and np.isfinite(ec).all().all()
    )
    children = {}
    previous_etf = load(T / "later-session-20261020/ETF-decisions/output.json")["children"]
    for p in ["S1", "S2", "S3", "C2"]:
        cfg = load_strategy_spec(checked(plan["specs"][p])).portfolio.etf_rotation
        menu = list(cfg.menu)
        cash = cfg.cash_symbol
        series = {s: rot._symbol_series(panel, s) for s in plan["menus"][p]}
        formation = rot.resolve_signal_session(series[cash][0], str(cfg.rebalance), dates[-1])
        overlay = None
        if p == "C2":
            r = rot.eom_sector_blend_book(
                series,
                formation,
                menu=menu,
                cash_symbol=cash,
                reversal_symbol=cfg.eom_sector_blend.reversal_symbol,
                reversal_weight=float(cfg.eom_sector_blend.reversal_weight),
                top_n=2,
            )
            assert not r.ineligible and r.reversal_reason is None
            weights = dict(r.weights)
        else:
            scores = {
                s: rot.score_symbol(
                    *series[s],
                    signal_session=formation,
                    lookbacks=list(cfg.lookbacks),
                    min_history_sessions=cfg.min_history_sessions,
                )
                for s in menu
            }
            assert all(v.reason is None for v in scores.values())
            cashscore = rot.score_symbol(
                *series[cash],
                signal_session=formation,
                lookbacks=list(cfg.lookbacks),
                min_history_sessions=cfg.min_history_sessions,
            )
            picks, _ = rot.select_book(
                {s: v.score for s, v in scores.items()},
                top_n=2,
                cash_score=cashscore.score,
                absolute_momentum_filter=True,
            )
            weights = rot.build_weights(
                picks, top_n=2, cash_symbol=cash, unfilled_slot_policy="renormalize_survivors"
            )
            if p in ["S2", "S3"]:
                d = rot._decide_overlay(
                    panel,
                    series,
                    menu=menu,
                    cash_symbol=cash,
                    latest_session=dates[-1],
                    lookbacks=list(cfg.lookbacks),
                    top_n=2,
                    rebalance=str(cfg.rebalance),
                    absolute_momentum_filter=True,
                    min_history_sessions=cfg.min_history_sessions,
                    unfilled_slot_policy="renormalize_survivors",
                    vol_cfg=cfg.vol_target,
                )
                weights = rot.apply_multiplier(weights, d.multiplier, cash)
                overlay = dict(
                    decision_session=d.decision_session.isoformat() if d.decision_session else None,
                    updates_next_session=d.updates_next_session,
                    multiplier=d.multiplier,
                    boost_active=d.boost_active,
                    target_annual_vol=d.target_annual_vol,
                )
        prior = previous_etf[p]
        new_event = formation.isoformat() > oldsource["reference_day"] or (
            overlay is not None
            and overlay["decision_session"] is not None
            and overlay["decision_session"] > oldsource["reference_day"]
        )
        children[p] = dict(
            name=p,
            symbols=list(weights),
            weights=list(weights.values()),
            reference_marks=marks,
            formation_day=formation.isoformat(),
            observed_through=ref,
            overlay=overlay,
            portfolio_action="rebalance" if new_event else "hold",
            drawdown_exit_pct=float(cfg.drawdown_exit_pct),
            source=bind(root / "current-source.json"),
            stop_state_must_be_carried=True,
        )
    if b is not None:
        children["BASE"] = dict(b, name="BASE")
    if h is not None:
        children["H5"] = dict(h, name="H5")
    save(root / "current-constituents.json", children)
    save(
        root / "preparation-result.json",
        dict(
            status="inputs_and_held_ETF_targets_prepared_LSTM_pending",
            reference_day=ref,
            application_day=app,
            raw_hygiene=qa.manifest(),
            ETF_hygiene=eqa.manifest(),
            core_raw_rows=len(raw),
            source=bind(root / "current-source.json"),
            new_fits=0,
        ),
    )


def assemble(root, *, received_children=None):
    receive_current_paper_maintenance()
    receive_action_lineage(root)
    source = load(root / "current-source.json")
    ref, app = source["reference_day"], source["application_day"]
    children = (
        load(root / "current-constituents.json") if received_children is None else received_children
    )
    marks = load(root / "current-marks.json")
    blocked = {}
    if set(children) != {"S1", "S2", "S3", "C2", "BASE", "H5"}:
        blocked = {
            p: "All six current child payloads are required; missing "
            + ",".join(sorted({"S1", "S2", "S3", "C2", "BASE", "H5"} - set(children)))
            for p in ["MULTI_EQUAL", "MULTI_HIERARCHICAL"]
        }
        save(root / "assembly-dependencies.json", blocked)
        return
    for p in ["MULTI_EQUAL", "MULTI_HIERARCHICAL"]:
        fractions = {
            x: 1 / 6 if p == "MULTI_EQUAL" else 1 / 12 if x in ["S1", "S2", "S3"] else 1 / 4
            for x in children
        }
        cents = dict(
            zip(
                children,
                [333334, 333334, 333333, 333333, 333333, 333333]
                if p == "MULTI_EQUAL"
                else [166667, 166667, 166666, 500000, 500000, 500000],
                strict=True,
            )
        )
        combined = {}
        rows = []
        for name, ch in children.items():
            rows.append(dict(ch, name=name, capital_usd=cents[name] / 100))
            for s, w in zip(ch["symbols"], ch["weights"], strict=True):
                combined[s] = combined.get(s, 0) + w * fractions[name]
        target(
            root,
            p,
            list(combined),
            list(combined.values()),
            marks,
            source,
            ref,
            app,
            children=rows,
            cross_child_lending=False,
            outer_rebalance=False,
            aggregate_display_only=True,
            portfolio_action="hold",
        )
    save(root / "assembly-dependencies.json", blocked)


def finish(root, *, received_prepare_dependencies=None):
    receive_current_paper_maintenance()
    receive_action_lineage(root)
    source = load(root / "current-source.json")
    ref, app = source["reference_day"], source["application_day"]
    inf = load(root / "current-lstm-inference.json")
    old = load(T / "input/LSTM/output.json")
    marks = load(root / "current-marks.json")
    target(
        root,
        "LSTM",
        old["symbols"],
        inf["weights"],
        marks,
        source,
        ref,
        app,
        is_fresh_prediction=True,
        portfolio_action="rebalance",
        full_sequence_rows=inf["full_sequence_rows"],
        models=[r["checkpoint"] for r in old["model_context"]],
        prefix_parity=inf["prefix_max_errors"],
        new_inference_count=2,
        initial_missing_allocation_may_be_completed=False,
    )
    blocked = {
        **(
            load(root / "prepare-dependencies.json")
            if received_prepare_dependencies is None
            else received_prepare_dependencies
        ),
        **load(root / "assembly-dependencies.json"),
    }
    rows = {p.stem: bind(p) for p in (root / "targets").glob("*.json")}
    partition(rows, blocked)
    dependency_row = save(
        root / "policy-dependencies.json",
        dict(
            blocked=blocked, source=bind(root / "current-source.json"), no_blocked_target_retag=True
        ),
    )
    save(
        root / "target-production-result.json",
        dict(
            status="partial_current_targets_with_explicit_dependencies"
            if blocked
            else "six_dated_staging_targets_completed_not_installed",
            at_utc=datetime.now(UTC).isoformat(),
            source=bind(root / "current-source.json"),
            reference_day=ref,
            application_day=app,
            targets=rows,
            blocked_policies=blocked,
            dependency_manifest=dependency_row,
            new_fits=0,
            LSTM_fresh_inferences=2,
            BASE_H5_signal_clocks_distinguished=True,
            operator_or_account_calls=0,
        ),
    )


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--phase", choices=["prepare", "assemble", "finish"], required=True)
    a = p.parse_args()
    root = a.output.resolve()
    assert root.is_relative_to(REPO / "reports/paper/diagnostics")
    {"prepare": prepare, "assemble": assemble, "finish": finish}[a.phase](root)


if __name__ == "__main__":
    main()
