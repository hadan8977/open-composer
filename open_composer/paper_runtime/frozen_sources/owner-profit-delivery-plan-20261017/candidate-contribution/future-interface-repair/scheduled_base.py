# ruff: noqa: E501 -- Frozen roster and explicit interface literals.
"""Callable monthly BASE producer; no scheduler, market fetch, broker or import work.

The caller supplies the reviewed monthly input receiver and its actual native/resource
admission. This library does not grant either authority. Run in a fresh child process
because the unchanged research helpers temporarily isolate legacy module names.
"""

import hashlib
import json
import math
import os
import uuid
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
TASK = HERE.parent
REPO = TASK.parents[4]
UPSTREAM = REPO / "reports/research/program/share-turnover-information-20261017"
POLICY = "DIA28_BASE_SEQUENTIAL_ORIGINAL"
VERSION = "monthly-base-producer-v1"
LABEL_UNIT = "Archived complete monthly hypothetical10bp net operating opportunity; no quote-derived replacement"
SYMBOLS = "MMM AMGN AAPL BA CAT CVX CSCO KO DOW GS HD HON INTC IBM JNJ JPM MCD MRK MSFT NKE PG CRM TRV UNH VZ V WBA DIS".split()


def clock(value):
    value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    assert value.tzinfo is not None, "Aware actual clocks required"
    return value.astimezone(UTC)


def now():
    return datetime.now(UTC).isoformat()


def canonical(path):
    p = Path(path).absolute()
    assert p.resolve() == p, "Canonical context required"
    return p


def binding(path):
    p = canonical(path)
    return dict(
        path=str(p), bytes=p.stat().st_size, sha256=hashlib.sha256(p.read_bytes()).hexdigest()
    )


def verify(row):
    assert binding(row["path"]) == row, "Changed consumed bytes"


def load(path):
    return json.loads(canonical(path).read_text())


def write(path, value):
    path = canonical(path)
    assert not path.exists(), "No overwrites or unreceived-prefix recovery"
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("x") as stream:
        json.dump(value, stream, allow_nan=False, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def calendar(formation_month):
    from open_composer.market_sessions import (
        NEW_YORK,
        next_us_equity_session,
        us_equity_session_close,
    )

    year, month = map(int, formation_month.split("-"))
    assert formation_month == f"{year:04d}-{month:02d}"
    first = date(year + (month == 12), month % 12 + 1, 1)
    decision = next_us_equity_session(first - timedelta(days=1))
    execution = next_us_equity_session(decision)
    close = us_equity_session_close(decision)
    return dict(
        source_cutoff=datetime.combine(decision, time(9, 35), NEW_YORK).isoformat(),
        quantity_commit=(
            datetime.combine(decision, close, NEW_YORK) + timedelta(minutes=15)
        ).isoformat(),
        sell_wave=datetime.combine(execution, time(9, 35), NEW_YORK).isoformat(),
        buy_wave=datetime.combine(execution, time(9, 40), NEW_YORK).isoformat(),
    )


def code_bindings():
    return [
        binding(p)
        for p in [
            HERE / "scheduled_base.py",
            HERE / "forecast.schema.json",
            TASK / "common.py",
            UPSTREAM / "method.py",
            UPSTREAM / "learning.py",
            REPO / "open_composer/research/ml_backend/model_factory.py",
            REPO / "open_composer/market_sessions.py",
        ]
    ]


def verify_reviewed_code(reviewed_code, fingerprint):
    assert json.dumps(reviewed_code, sort_keys=True) == fingerprint, "Admission arguments mutated"
    assert code_bindings() == reviewed_code, "Reviewed producer changed after admission"


def admit_reviewed(admit, context_binding, schedule):
    reviewed_code = code_bindings()
    fingerprint = json.dumps(reviewed_code, sort_keys=True)
    admission = admit(context_binding, reviewed_code, schedule)
    verify_reviewed_code(reviewed_code, fingerprint)
    assert admission, "Actual runner admission required"
    return admission, reviewed_code, fingerprint


def validate_forecast(row):
    # Explicit schema/semantic receiver: no optional third-party schema runtime.
    schema = load(HERE / "forecast.schema.json")
    assert set(row) == set(schema["required"])
    assert isinstance(row["original_label_unit"], str) and row["original_label_unit"] == LABEL_UNIT
    assert isinstance(row["invocation_id"], str) and len(row["invocation_id"]) == 32
    int(row["invocation_id"], 16)
    assert type(row["pid"]) is int and row["pid"] > 0
    assert isinstance(row["data_bindings"], list) and len(row["data_bindings"]) >= 3
    assert all(
        isinstance(row[k], list)
        for k in ["symbols", "scores", "weights", "eligible", "selected", "producer_bindings"]
    )
    assert row["symbols"] == SYMBOLS and row["policy"] == POLICY and row["version"] == VERSION
    assert row["calendar"] == calendar(row["formation_month"])
    assert row["producer_bindings"] == code_bindings()
    assert len(row["scores"]) == len(row["weights"]) == len(row["eligible"]) == 28
    assert all(type(x) is bool for x in row["eligible"])
    assert type(row["fit_supported"]) is bool and row["no_offcycle_adoption"] is True
    assert row["cash_reason"] is None or isinstance(row["cash_reason"], str)
    assert isinstance(row["admission"], dict) and row["admission"]
    assert all(s is None or (type(s) in [int, float] and math.isfinite(s)) for s in row["scores"])
    assert all(w in [0, 0.2] for w in row["weights"]) and sum(row["weights"]) <= 1.000000001
    assert all(type(w) in [int, float] for w in row["weights"])
    assert row["selected"] == [s for s, w in zip(SYMBOLS, row["weights"], strict=True) if w]
    assert row["K"] == len(row["selected"])
    assert type(row["K"]) is int and row["K"] <= 5
    if row["fit_supported"] and row["cash_reason"] is None:
        assert all(
            s is not None for s, ok in zip(row["scores"], row["eligible"], strict=True) if ok
        )
        ranked = sorted(
            [i for i in range(28) if row["eligible"][i] and row["scores"][i] > 0],
            key=lambda i: (-row["scores"][i], SYMBOLS[i]),
        )[:5]
        assert row["weights"] == [0.2 if i in ranked else 0 for i in range(28)]
    assert clock(row["computation_started_at"]) <= clock(row["computation_completed_at"])
    assert clock(row["packet_received_at"]) <= clock(row["computation_started_at"])
    assert clock(row["computation_completed_at"]) <= clock(row["publication_started_at"])
    cutoff = clock(row["calendar"]["source_cutoff"])
    assert cutoff <= clock(row["computation_started_at"])
    assert clock(row["publication_started_at"]) <= clock(now())
    assert clock(row["sources_received_through"]) <= cutoff
    assert row["training_label_end_through"] < cutoff.date().isoformat()
    assert (
        date.fromisoformat(row["training_label_end_through"]).isoformat()
        == row["training_label_end_through"]
    )
    if not row["fit_supported"] or row["cash_reason"] is not None:
        assert row["K"] == 0
    for item in row["data_bindings"]:
        verify(item)
    return row


def receive_context(expected, formation_month):
    """Same canonical source/packet closure at creation and completed recovery."""
    verify(expected)
    context = load(expected["path"])
    assert context["formation_month"] == formation_month
    assert context["source_cutoff"] == calendar(formation_month)["source_cutoff"]
    assert context["accepted_recipe"] == binding(TASK / "prepare_package.py")
    assert isinstance(context["data_bindings"], list) and context["data_bindings"]
    assert clock(context["sources_received_through"]) <= clock(context["source_cutoff"])
    assert (
        clock(context["sources_received_through"])
        <= clock(context["packet_received_at"])
        <= clock(now())
    )
    for item in [context["packet"], context["accepted_recipe"], *context["data_bindings"]]:
        verify(item)
    return context


def receive(directory, formation_month, expected_context, *, before_commit=True):
    """Return completed canonical output only; this is not order authorization."""
    directory = canonical(directory)
    forecast, seal, journal = [
        directory / name for name in ["forecast.json", "seal.json", "journal.jsonl"]
    ]
    rows = [json.loads(x) for x in canonical(journal).read_text().splitlines()]
    s = load(seal)
    row = validate_forecast(load(forecast))
    assert row["formation_month"] == formation_month and row["source_context"] == expected_context
    context = receive_context(expected_context, formation_month)
    state_path = directory / "state.json"
    state = load(state_path)
    assert set(state) == {
        "invocation_id",
        "pid",
        "producer_bindings",
        "admission",
        "source_context",
        "formation_month",
        "state",
        "fold",
        "scores",
        "weights",
    }
    assert state["fold"]["supported"] == row["fit_supported"]
    assert state["scores"] == row["scores"] and state["weights"] == row["weights"]
    assert row["fit_supported"] or state["state"] is None
    assert row["data_bindings"] == [
        context["packet"],
        context["accepted_recipe"],
        *context["data_bindings"],
        binding(state_path),
    ]
    assert row["packet_received_at"] == context["packet_received_at"]
    assert row["sources_received_through"] == context["sources_received_through"]
    context_keys = [
        "invocation_id",
        "pid",
        "producer_bindings",
        "admission",
        "source_context",
        "formation_month",
    ]
    for key in context_keys:
        assert state[key] == row[key] == s[key]
    assert s["forecast"] == binding(forecast) and s["source_context"] == expected_context
    assert len(rows) == 2 and [r["event"] for r in rows] == ["started", "completed"]
    for r in rows:
        for key in context_keys:
            assert r[key] == row[key]
    assert rows[0]["source_context"] == rows[1]["source_context"] == expected_context
    assert (
        rows[1]["seal"] == binding(seal)
        and rows[0]["formation_month"] == rows[1]["formation_month"] == formation_month
    )
    assert clock(row["calendar"]["source_cutoff"]) <= clock(rows[0]["started_at"])
    assert clock(context["packet_received_at"]) <= clock(rows[0]["started_at"])
    assert (
        clock(rows[0]["started_at"])
        <= clock(row["computation_started_at"])
        <= clock(row["computation_completed_at"])
        <= clock(row["publication_started_at"])
        <= clock(s["published_at"])
        <= clock(rows[1]["completed_at"])
        <= clock(now())
    )
    if before_commit:
        assert clock(rows[1]["completed_at"]) <= clock(row["calendar"]["quantity_commit"]), (
            "Late publication: no catch-up"
        )
    return dict(
        forecast=row,
        output_seal=binding(seal),
        published_at=s["published_at"],
        completed_at=rows[1]["completed_at"],
    )


def produce(directory, formation_month, context_path, *, receive_monthly_input, admit):
    """Exactly one BASE fit, after caller's actual admission and input reception.

    receive_monthly_input(context_path, cutoff) must return the SAME checked context
    and certify its packet using the accepted raw/count/action/sanitizer recipe.
    A binding list alone is not that reception. No generic/unchecked default exists.
    admit is the reviewed runner's real native/resource callback, not a status file.
    """
    import importlib.util

    import numpy as np

    schedule = calendar(formation_month)
    directory = canonical(directory)
    context_path = canonical(context_path)
    context_binding = binding(context_path)
    if directory.exists():
        return receive(directory, formation_month, context_binding)
    assert clock(schedule["source_cutoff"]) <= clock(now()) < clock(schedule["quantity_commit"])
    context = receive_monthly_input(context_path, schedule["source_cutoff"])
    assert context == receive_context(context_binding, formation_month)
    admission, reviewed_code, code_fingerprint = admit_reviewed(admit, context_binding, schedule)
    z = dict(np.load(context["packet"]["path"], allow_pickle=False))
    assert z["symbols"].tolist() == SYMBOLS and str(z["months"][-1]) == formation_month
    assert str(z["dates"][-1])[:7] == formation_month and int(z["entry"][-1]) == len(z["dates"])
    assert int(z["label_end"][-1]) == -1 and not np.isfinite(z["label"][-1]).any()
    assert z["primitive"].shape[1:] == (28, 9) and z["flags"].shape[1:] == (28, 4)
    directory.mkdir(parents=True, exist_ok=False)
    journal = directory / "journal.jsonl"
    start = dict(
        event="started",
        invocation_id=uuid.uuid4().hex,
        pid=os.getpid(),
        producer_bindings=reviewed_code,
        admission=admission,
        formation_month=formation_month,
        source_context=context_binding,
        started_at=now(),
    )
    with journal.open("x") as stream:
        stream.write(json.dumps(start) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    computation_started_at = now()
    # Load unchanged helpers under the same isolated legacy context as the accepted fit.
    spec = importlib.util.spec_from_file_location("mcc_producer_common", TASK / "common.py")
    shared = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(shared)
    with shared.legacy(UPSTREAM):
        learning = shared.module("mcc_monthly_learning", UPSTREAM / "learning.py")
        method = shared.module("mcc_monthly_method", UPSTREAM / "method.py")
        current = len(z["entry"]) - 1
        f = learning.fold(z, current)
        ii, jj, w = f["i"], f["j"], f["weights"]
        scores, q, state = np.full(28, np.nan), np.zeros(28), None
        reason = "insufficient_original_fold_support" if not f["supported"] else None
        if f["supported"]:
            verify_reviewed_code(reviewed_code, code_fingerprint)
            train, _, primitive = method.train_design(
                z["primitive"][ii, jj], z["flags"][ii, jj], z["turnover"][ii, jj], w
            )
            test, _, _ = method.train_design(
                z["primitive"][current],
                z["flags"][current],
                z["turnover"][current],
                np.ones(28),
                state=primitive,
            )
            from open_composer.research.ml_backend.model_factory import create_model

            estimator = create_model(
                SimpleNamespace(
                    model=SimpleNamespace(
                        kind="ridge_regressor",
                        hyperparameters=dict(alpha=10.0, fit_intercept=True),
                        training=SimpleNamespace(seed=20261017),
                    )
                )
            )
            verify_reviewed_code(reviewed_code, code_fingerprint)
            estimator.fit(train, z["label"][ii, jj], scale__sample_weight=w, model__sample_weight=w)
            scores = estimator.predict(test)
            q = method.target(
                scores,
                z["eligible"][current],
                z["symbols"],
                "BASE",
                z["primitive"][current, :, 0],
                z["turnover"][current],
            )
            if not np.isfinite(scores[z["eligible"][current]]).all():
                reason = "nonfinite_eligible_score"
            state = dict(
                primitive_state=primitive,
                model=dict(
                    mean=estimator.named_steps["scale"].mean_,
                    scale=estimator.named_steps["scale"].scale_,
                    coef=estimator.named_steps["model"].coef_,
                    intercept=float(estimator.named_steps["model"].intercept_),
                ),
            )
            if reason is None and not q.any():
                reason = "no_positive_eligible_BASE_score"
    write(
        directory / "state.json",
        shared.clean(
            dict(
                **{k: v for k, v in start.items() if k not in ["event", "started_at"]},
                state=state,
                fold={k: v for k, v in f.items() if k not in ["i", "j", "weights"]},
                scores=[float(s) if math.isfinite(s) else None for s in scores],
                weights=q.tolist(),
            )
        ),
    )
    maturity = max(
        (str(z["dates"][int(z["label_end"][i])]) for i in np.unique(ii)), default="0001-01-01"
    )
    row = dict(
        invocation_id=start["invocation_id"],
        pid=start["pid"],
        policy=POLICY,
        version=VERSION,
        formation_month=formation_month,
        calendar=schedule,
        sources_received_through=context["sources_received_through"],
        packet_received_at=context["packet_received_at"],
        computation_started_at=computation_started_at,
        computation_completed_at=now(),
        publication_started_at=now(),
        training_label_end_through=maturity,
        fit_supported=bool(f["supported"]),
        cash_reason=reason,
        symbols=SYMBOLS,
        scores=[float(s) if math.isfinite(s) else None for s in scores],
        eligible=z["eligible"][current].astype(bool).tolist(),
        weights=q.tolist(),
        K=int((q > 0).sum()),
        selected=[s for s, w in zip(SYMBOLS, q, strict=True) if w],
        source_context=context_binding,
        data_bindings=[
            context["packet"],
            context["accepted_recipe"],
            *context["data_bindings"],
            binding(directory / "state.json"),
        ],
        producer_bindings=reviewed_code,
        admission=admission,
        original_label_unit=LABEL_UNIT,
        no_offcycle_adoption=True,
    )
    validate_forecast(row)
    verify_reviewed_code(reviewed_code, code_fingerprint)
    assert clock(now()) < clock(schedule["quantity_commit"]), (
        "Computation missed commit; retain failed prefix"
    )
    write(directory / "forecast.json", row)
    write(
        directory / "seal.json",
        dict(
            **{k: v for k, v in start.items() if k not in ["event", "started_at"]},
            forecast=binding(directory / "forecast.json"),
            published_at=now(),
        ),
    )
    with journal.open("a") as stream:
        stream.write(
            json.dumps(
                dict(
                    **{k: v for k, v in start.items() if k not in ["event", "started_at"]},
                    event="completed",
                    completed_at=now(),
                    seal=binding(directory / "seal.json"),
                )
            )
            + "\n"
        )
        stream.flush()
        os.fsync(stream.fileno())
    return receive(directory, formation_month, context_binding)
