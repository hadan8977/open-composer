# ruff: noqa: E402 -- Runtime paths and frozen-source imports initialize in order.
"""Date-bound maintenance adapter for the remaining intraday paper policies.

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
                bodies.append(load(checked(p["response"])))
            else:
                bodies.append(p)
        assert bodies[-1].get("next_page_token") is None
        result[row["group"], row["key"]] = bodies
    return result


def bars(objects, frozen=None):
    out = {}
    invalid = set()
    for p in objects:
        for s, rs in p["bars"].items():
            for r in rs:
                key = (s, r["t"][:10])
                if key in out or not all(
                    isinstance(r.get(k), (int, float)) and math.isfinite(r[k]) and r[k] > 0
                    for k in ("o", "h", "l", "c")
                ):
                    invalid.add(key)
                out[key] = r
    for symbol, day in invalid:
        out.pop((symbol, day))
        if frozen is not None:
            frozen.setdefault(symbol, "invalid_or_duplicate_bar")
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
        frozen_symbols=load(root / "frozen-symbols.json"),
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


def prepare_core(root, source, obj, control, previous, normalized, raw, marks, bad):
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
    proxy.core_bars = lambda ps, syms, *, inactive=(): {
        (s, d): row
        for (s, d), row in raw.items()
        if s in syms and s not in inactive and d in support_days
    }
    proxy.core_actions = lambda ps, syms: ps
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
                monthly_forecast,
                root=REPO,
                reference_day=ref,
                control=control,
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
                formation_eligible=[bool(v) for v in load(checked(monthly_forecast))["eligible"]],
                current_daily_eligible=current["current_daily_eligible"],
                eligible=instruction["eligible"],
                raw_reference_marks=current["raw_reference_marks"],
                current_actions=current["current_actions"],
            )
            origin = {
                key: instruction[key]
                for key in [
                    "held_model_origin",
                    "held_signal_observation",
                    "held_signal_application",
                    "original_computed_at",
                    "owner_date_exception",
                    "new_fit_count",
                    "is_fresh_prediction",
                    "historical_timely_source_claim",
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
            frozen_symbols=bad
            | h5["frozen_symbols"]
            | {
                carriers.get(s) or s: "missing_h5_current_support"
                for s, eligible in zip(
                    hcurrent["symbols"], hcurrent["current_eligible"], strict=True
                )
                if not eligible
            },
        )
    except FormationDependency as error:
        blocked["H5"] = str(error)
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
    frozen = {}
    raw = bars(obj["core", "raw-bars"], frozen)
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
    frozen.update({b.symbol: "raw_price_break" for b in qa.breaks})
    marks = {
        s: float(raw[s, ref]["c"])
        for s in symbols
        if (s, ref) in raw and raw[s, ref].get("v", 0) > 0 and raw[s, ref].get("n", 0) > 0
    }
    if not marks:
        raise ValueError(f"No usable raw marks on {ref}")
    core = load(N / "next-session-source-plan-M1.json")["core"]["raw_symbols"]
    lineage = build_action_lineage(root, ref, app)
    frozen.update(lineage["frozen_symbols"])
    for s in core:
        if s not in marks:
            frozen.setdefault(s, "missing_raw_reference_bar")
    lineage_row = save(root / "action-lineage-QA.json", lineage)
    allowed = {r["id"] for r in lineage["events"] if r["economic_date"] is not None}
    obj["core", "actions"] = [
        {
            "corporate_actions": {
                kind: [
                    row
                    for row in rows
                    if row.get("id") in allowed
                    and not any(
                        row.get(k) in frozen
                        for k in ("symbol", "source_symbol", "old_symbol", "acquiree_symbol")
                    )
                ]
                for kind, rows in page["corporate_actions"].items()
            }
        }
        for page in obj["core", "actions"]
    ]
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
                and s not in frozen,
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
    # Saved two-model recurrent inference inputs, original immutable2701-session prefix.
    old = previous["LSTM"][0]
    syms = old["symbols"]
    accepted = old["original_accepted"]
    cl = pd.read_parquet(checked(accepted["ETF-sanitized-close.parquet"]))[syms]
    op = pd.read_parquet(checked(accepted["ETF-sanitized-open.parquet"]))[syms]
    adjusted = bars(obj["core", "adjusted-tail"], frozen)
    prior_root, _, oldsource = active_baseline()
    oldobj = pages(oldsource)
    oldtail = bars(oldobj["core", "adjusted-tail"])
    from open_composer.paper_runtime.six.adjusted_history import (
        append_adjusted_history,
        cash_actions,
    )

    prior_qa = load(prior_root / "lstm-input-QA.json")
    old_scales = {s: float(prior_qa["basis"][s]["multiplier"]) for s in syms}
    if "canonical_close" in prior_qa:
        prior_cl = pd.read_parquet(checked(prior_qa["canonical_close"]))[syms]
        prior_op = pd.read_parquet(checked(prior_qa["canonical_open"]))[syms]
        cl, op = prior_cl, prior_op
    else:
        for (symbol, day), row in oldtail.items():
            if symbol in syms and "2026-10-01" <= day <= oldsource["reference_day"]:
                cl.loc[pd.Timestamp(day), symbol] = row["c"] / old_scales[symbol]
                op.loc[pd.Timestamp(day), symbol] = row["o"] / old_scales[symbol]
        cl, op = cl.sort_index(), op.sort_index()
    op, cl, scales, revision = append_adjusted_history(
        op,
        cl,
        oldtail,
        adjusted,
        old_scales,
        cash_actions(obj["core", "actions"]),
        prior_reference=oldsource["reference_day"],
        reference=ref,
        frozen=frozen,
    )
    basis = {s: dict(multiplier=scales[s], **revision[s]) for s in syms}
    cc, oo, lqa = sanitize_price_matrices(cl, op)
    frozen.update(
        {
            b.symbol: "adjusted_price_break"
            for b in lqa.breaks
            if b.as_dict()["first_session_after"] == ref
        }
    )
    methoddir = P / "return-line-replenishment-20261016/direct-position-learning-20261016"
    features = mod("refresh_original_features", methoddir / "prepare_features.py")
    x, vol, _ = features.features(cc)
    first = np.flatnonzero(cl.index.strftime("%Y-%m-%d") == "2026-01-02")[0]
    lo = first - 63
    x = x[lo:]
    vol = vol[lo:]
    expected = us_equity_session_dates(date(2026, 1, 2), date.fromisoformat(ref))
    if len(x) != len(expected) + 63 or cl.index[-1].date() != date.fromisoformat(ref):
        raise ValueError("LSTM history has no current session")
    for j, symbol in enumerate(syms):
        if symbol in frozen or not np.isfinite(x[-1, j]).all() or not np.isfinite(vol[-1, j]):
            frozen.setdefault(symbol, "unavailable_lstm_features")
            vol[-1, j] = np.inf
    vol[~np.isfinite(vol)] = np.inf
    np.savez_compressed(root / "current-lstm-sequence.npz", features=x, vol=vol)
    cl.to_parquet(root / "LSTM-canonical-close.parquet")
    op.to_parquet(root / "LSTM-canonical-open.parquet")
    save(
        root / "lstm-input-QA.json",
        dict(
            sequence=bind(root / "current-lstm-sequence.npz"),
            canonical_close=bind(root / "LSTM-canonical-close.parquet"),
            canonical_open=bind(root / "LSTM-canonical-open.parquet"),
            full_sequence_rows=len(x),
            annual_sessions=len(expected),
            burnin_sessions=63,
            basis=basis,
            hygiene=lqa.manifest(),
            checkpoint_context=old["model_context"],
        ),
    )
    save(root / "frozen-symbols.json", frozen)
    prepare_core(root, source, obj, control, previous, normalized, raw, marks, frozen)
    print(json.dumps({"frozen_symbols": frozen}), flush=True)
    save(
        root / "preparation-result.json",
        dict(
            status="inputs_and_core_targets_prepared_LSTM_pending",
            reference_day=ref,
            application_day=app,
            raw_hygiene=qa.manifest(),
            core_raw_rows=len(raw),
            source=bind(root / "current-source.json"),
            new_fits=0,
        ),
    )


def finish(root):
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
    blocked = load(root / "prepare-dependencies.json")
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
            else "dated_staging_targets_completed_not_installed",
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
    p.add_argument("--phase", choices=["prepare", "finish"], required=True)
    a = p.parse_args()
    root = a.output.resolve()
    assert root.is_relative_to(REPO / "reports/paper/diagnostics")
    {"prepare": prepare, "finish": finish}[a.phase](root)


if __name__ == "__main__":
    main()
