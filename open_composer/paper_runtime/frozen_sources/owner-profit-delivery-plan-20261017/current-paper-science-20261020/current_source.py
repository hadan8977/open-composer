"""Fixed75 current source receipt; lawful transport remains f9/66ad-owned.

Import is inert. Local array reception and every HTTP dispatch require a real
new source-stage admission. Complete old captures are never recast as current.
"""

import ast
import copy
import hashlib
import math
import json
import os
from datetime import date

from current_common import (
    DEADLINE, HERE, OPERATING, PARENT, PEER, REPO, TASK, authority, binding,
    canonical, checked, claim_worker, clock, finish, guard_write, kernel, load,
    module, now, process_identity, receive_go, receive_stage, save, snapshot, start,
)

OLD_LSTM = PARENT / "second-learned-paper-20261019"
FUTURE = PARENT / "candidate-contribution/future-input-receiver"
SYMBOLS = "SPY QQQ IWM EFA EEM IEF TLT GLD DBC UUP".split()


def sessions(first, last):
    from open_composer.market_sessions import us_equity_session_dates
    return [d.isoformat() for d in us_equity_session_dates(date.fromisoformat(first), date.fromisoformat(last))]


def source_payload(path):
    p = canonical(path)
    assert p.is_relative_to(HERE / "source") and p.suffix in {".json", ".raw"}
    return json.loads(p.read_text())


def upstream_function(path, name):
    """Compile one exact accepted pure page/writer function, not its old entry."""
    path = canonical(path)
    assert binding(path) in snapshot()
    nodes = [n for n in ast.parse(path.read_text()).body if isinstance(n, ast.FunctionDef) and n.name == name]
    assert len(nodes) == 1
    namespace = dict(canonical=canonical, binding=binding, checked=checked,
                     load=source_payload, clock=clock, now=now, save=save, json=json, os=os)
    exec(compile(ast.fix_missing_locations(ast.Module(body=nodes, type_ignores=[])), str(path), "exec"), namespace)
    return namespace[name]


def old_accepted_manifest():
    path = OLD_LSTM / "source-plan.json"
    assert binding(path) in snapshot()
    old_plan = load(path)
    return load(checked(old_plan["accepted_source_manifest"]))


def read_frozen_file(path, guard, reader):
    """Read one pinned inode; atomic path replacement cannot change this fd."""
    started_at = now()
    with path.open("rb") as f:
        a = os.fstat(f.fileno())
        assert (a.st_size, a.st_mtime_ns) == (guard["bytes"], guard["mtime_ns"]), "Frozen current shard version changed before open"
        def digest():
            f.seek(0)
            h = hashlib.sha256()
            for block in iter(lambda: f.read(1048576), b""):
                h.update(block)
            f.seek(0)
            return h.hexdigest()
        before = digest()
        data = reader(f)
        after = digest()
        b = os.fstat(f.fileno())
        assert (a.st_dev, a.st_ino, a.st_size, a.st_mtime_ns) == (b.st_dev, b.st_ino, b.st_size, b.st_mtime_ns)
        assert before == after, "In-place source mutation during reception"
    return data, dict(path=str(path), bytes=a.st_size, sha256=before, mtime_ns=a.st_mtime_ns,
                      inode=a.st_ino, read_started_at=started_at, read_completed_at=now())


def receive_local_projection(local):
    """Immutable selected numeric source closure; origin hashes are provenance."""
    p = load(checked(local["projection"], HERE / "source/local-projection.json"))
    started = load(HERE / "source/started.json")
    assert p["task_id"] == TASK and p["started"] == binding(HERE / "source/started.json")
    assert p["invocation"] == started["go"]["request"]["invocation"]
    plan = load(HERE / "source-plan.json")
    assert len(p["origins"]) == len(plan["local_adjusted_guards"]) == 9
    for origin, guard in zip(p["origins"], plan["local_adjusted_guards"]):
        assert {k: origin[k] for k in ["path", "bytes", "mtime_ns"]} == {k: guard[k] for k in ["path", "bytes", "mtime_ns"]}
        assert type(origin["sha256"]) is str and len(origin["sha256"]) == 64 and all(c in "0123456789abcdef" for c in origin["sha256"])
        assert clock(started["started_at"]) <= clock(origin["read_started_at"]) <= clock(origin["read_completed_at"]) <= clock(p["created_at"]) <= clock(local["actual_received_at"])
    rows = p["rows"]
    prefix = sessions("2026-01-02", "2026-09-30")
    tail = sessions("2026-10-01", "2026-10-19")
    allowed = {s + ":" + d for s in SYMBOLS for d in prefix + tail}
    assert {s + ":" + d for s in SYMBOLS for d in prefix} <= set(rows) <= allowed
    for key, row in rows.items():
        assert key == row["symbol"] + ":" + row["day"] and row["symbol"] in SYMBOLS
        assert all(type(row[k]) in [int, float] and math.isfinite(row[k]) and row[k] > 0 for k in ["open", "close"])
    assert local["rows"] == {k: v for k, v in rows.items() if v["day"] in tail}
    overlap = sessions("2026-09-28", "2026-09-30")
    assert local["request_overlap_rows"] == {k: v for k, v in rows.items() if v["day"] in overlap}
    assert local["missing"] == [s + ":" + d for d in tail for s in SYMBOLS if s + ":" + d not in rows]
    assert local["adjustment_factors"] == p["adjustment_factors"]
    assert local["consumed"] == p["accepted_references"] + [local["projection"]]
    for row in local["consumed"]:
        checked(row)
    return p


def local_adjusted():
    """Receive actual frozen local tail; no fitting or source GET in this call."""
    authority()
    kernel("source")
    guard_write()
    started = load(HERE / "source/started.json")
    claim = load(HERE / "source/worker-started.json")
    receive_go(started["go"])
    assert claim["process"] == process_identity() == started["go"]["request"]["process"]
    assert claim["started"] == binding(HERE / "source/started.json")
    assert claim["invocation"] == started["go"]["request"]["invocation"]
    assert not (HERE / "source/completed.json").exists()
    import numpy as np
    import pandas as pd
    plan = load(HERE / "source-plan.json")
    manifest = old_accepted_manifest()
    rows_by_path = {r["path"]: r for r in manifest["files"]}
    original = PARENT.parent / "return-line-replenishment-20261016/direct-position-learning-20261016"
    close_row = rows_by_path[str(original / "ETF-sanitized-close.parquet")]
    open_row = rows_by_path[str(original / "ETF-sanitized-open.parquet")]
    close = pd.read_parquet(checked(close_row))[SYMBOLS]
    opening = pd.read_parquet(checked(open_row))[SYMBOLS]
    inventory = load(checked(plan["prior_artifacts"], HERE / "historical-artifact-inventory.json"))
    old_local_row = next(r for r in inventory["policies"]["LSTM"]["support_artifacts"] if r["path"] == str(OLD_LSTM / "source/local.json"))
    old_local = load(checked(old_local_row))
    expected_old = sessions("2026-01-02", "2026-09-30")
    previous_tail = sessions("2026-10-01", "2026-10-16")
    tail = sessions("2026-10-01", "2026-10-19")
    assert len(expected_old) == 187 and len(previous_tail) == 12 and len(tail) == 13
    rows, overlaps, factors, consumed = {}, {}, {}, [close_row, open_row, old_local_row]
    projection_rows, origins = {}, []
    for guard in plan["local_adjusted_guards"]:
        p = canonical(guard["path"])
        data, origin = read_frozen_file(p, guard, lambda f: pd.read_parquet(f, columns=["symbol", "timestamp", "open", "close"], filters=[("symbol", "in", guard["symbols"])]))
        origins.append(origin)
        data["day"] = pd.to_datetime(data.timestamp, utc=True).dt.strftime("%Y-%m-%d")
        assert not data.duplicated(["symbol", "day"]).any()
        for symbol in guard["symbols"]:
            z = data[data.symbol == symbol].set_index("day").sort_index()
            assert set(expected_old) <= set(z.index), "Missing indispensable current-vintage overlap"
            old_close = close.loc[pd.to_datetime(expected_old), symbol].to_numpy(dtype=float)
            ratio = z.loc[expected_old, "close"].to_numpy(dtype=float) / old_close
            k = float(ratio[0])  # Frozen original Jan2 selection, not diagnostic-dependent.
            assert np.isfinite(ratio).all() and k > 0
            assert np.allclose(ratio, k, rtol=1e-7, atol=1e-8), "Nonuniform current close revision"
            open_ratio = z.loc[expected_old, "open"].to_numpy(dtype=float) / opening.loc[pd.to_datetime(expected_old), symbol].to_numpy(dtype=float)
            assert np.isfinite(open_ratio).all() and np.allclose(open_ratio, k, rtol=1e-7, atol=1e-8), "Current OPEN basis differs"
            max_tail_error = 0.0
            n_tail = 0
            for day in previous_tail:
                key = symbol + ":" + day
                prior = old_local["rows"][key]
                prior_k = old_local["adjustment_factors"][symbol]["multiplier"]
                if day in z.index:
                    for name in ["open", "close"]:
                        current_value = float(z.loc[day, name]) / k
                        old_value = prior[name] / prior_k
                        assert np.isclose(current_value / old_value, 1, rtol=1e-7, atol=1e-8), "Nonuniform previously accepted October tail revision"
                        max_tail_error = max(max_tail_error, abs(current_value / old_value - 1))
                    n_tail += 1
            factors[symbol] = dict(multiplier=k, selected_day="2026-01-02", overlap=len(ratio),
                                   max_ratio_deviation=float(np.max(np.abs(ratio - k))),
                                   max_open_ratio_deviation=float(np.max(np.abs(open_ratio - k))),
                                   prior_October_overlap=n_tail, max_prior_October_relative_deviation=max_tail_error)
            for day in sessions("2026-09-28", "2026-09-30"):
                r = z.loc[day]
                overlaps[symbol + ":" + day] = dict(symbol=symbol, day=day, open=float(r.open), close=float(r.close))
            for day in tail:
                if day in z.index:
                    r = z.loc[day]
                    o, c = float(r.open), float(r.close)
                    assert np.isfinite([o, c]).all() and min(o, c) > 0
                    rows[symbol + ":" + day] = dict(symbol=symbol, day=day, open=o, close=c)
            for day in expected_old + tail:
                if day in z.index:
                    r = z.loc[day]
                    projection_rows[symbol + ":" + day] = dict(symbol=symbol, day=day, open=float(r.open), close=float(r.close))
    assert set(factors) == set(SYMBOLS)
    missing = [s + ":" + d for d in tail for s in SYMBOLS if s + ":" + d not in rows]
    projection_path = HERE / "source/local-projection.json"
    save(projection_path, dict(task_id=TASK, started=binding(HERE / "source/started.json"),
         invocation=started["go"]["request"]["invocation"], rows=projection_rows, origins=origins,
         adjustment_factors=factors, accepted_references=consumed, created_at=now()))
    local = dict(symbols=SYMBOLS, tail_sessions=tail, rows=rows, request_overlap_rows=overlaps,
                 missing=missing, adjustment_factors=factors, previous_local=old_local_row,
                 projection=binding(projection_path), consumed=consumed + [binding(projection_path)], actual_received_at=now())
    receive_local_projection(local)
    return local


def frozen_requests(local):
    plan = load(HERE / "source-plan.json")
    requests = copy.deepcopy(plan["requests"])
    if local["missing"]:
        request = copy.deepcopy(plan["conditional_request"])
        request.pop("condition")
        requests.append(request)
    return requests


def source_fetch_guard(expected_context):
    """Exact f9 API: before factory, every dispatch and after pacing; no GET."""
    authority()
    kernel("source")
    guard_write()
    context = load(checked(expected_context, HERE / "source/context.json"))
    assert context["task_id"] == TASK
    started = load(checked(context["started"], HERE / "source/started.json"))
    receive_go(started["go"])
    assert started["go"]["request"]["stage"] == "source"
    claim = load(HERE / "source/worker-started.json")
    assert claim["process"] == process_identity() == started["go"]["request"]["process"]
    assert claim["started"] == context["started"] and claim["native"] == started["go"]["native"]
    assert claim["invocation"] == started["go"]["request"]["invocation"]
    assert context["go"] == started["go"] and context["plan"] == binding(HERE / "source-plan.json")
    local = load(checked(context["local"], HERE / "source/local.json"))
    assert context["requests"] == frozen_requests(local)
    assert clock(started["started_at"]) <= clock(local["actual_received_at"]) <= clock(context["created_at"]) <= clock(now()) < clock(DEADLINE)
    receive_local_projection(local)
    assert not (HERE / "source/completed.json").exists(), "Completed source never dispatches again"
    return None


def receive_transport():
    manifest_path = OPERATING / "current-science-source-transport-manifest.json"
    review_path = OPERATING / "independent-current-science-source-transport-review-66ad.json"
    review = load(review_path)
    manifest = load(manifest_path)
    assert review["task_id"] == TASK and review["reviewer"] == "66ad4b54-ec62-400b-9a03-a29682cf58e6"
    assert review["independent"] is True and review["accepted_for_source_transport"] is True
    assert review["verdict"] == "approve_implementation" and review["target"] == binding(manifest_path)
    assert manifest["task_id"] == TASK and manifest["source_only"] is True
    assert manifest["scientific_manifest"] == binding(HERE / "implementation-manifest.json")
    assert canonical(manifest["scientific_review_path"]) == HERE / "independent-implementation-review.json"
    scientific = load(manifest["scientific_review_path"])
    assert scientific["task_id"] == TASK and scientific["reviewer"] == PEER
    assert scientific["verdict"] == "approve_implementation" and scientific["target"] == manifest["scientific_manifest"]
    bindings = manifest["bindings"]
    assert bindings and len({r["path"] for r in bindings}) == len(bindings)
    for row in bindings:
        checked(row)
    scope = load(checked(manifest["scope"], OPERATING / "current-science-source-transport-bindings.json"))
    assert manifest["scope"] in bindings and scope["task_id"] == TASK
    assert canonical(scope["root"]) == REPO and canonical(scope["component_root"]) == HERE
    assert scope["deadline"] == DEADLINE and scope["source_only"] is True and scope["no_quote_or_account_route"] is True
    assert scope["source_plan"] == binding(HERE / "source-plan.json") and scope["source_plan"] in bindings
    expected_module = OPERATING / "current_science_source_transport.py"
    assert binding(expected_module) in bindings
    for name in ["market_factory", "existing_transport", "existing_binding_reader"]:
        assert scope[name] in bindings
    assert review["verification"]["source_plan"] == scope["source_plan"]
    assert review["bindings"]["scientific_manifest"] == manifest["scientific_manifest"]
    assert review["bindings"]["manifest"] == binding(manifest_path)
    assert binding(HERE / "current_source.py") in snapshot()
    return expected_module


def collect_current_sources():
    if (HERE / "source/completed.json").exists():
        receive_sources()
        return binding(HERE / "source/output.json")
    started = start("source")
    claim = claim_worker("source")
    local = local_adjusted()
    save(HERE / "source/local.json", local)
    save(HERE / "source/context.json", dict(task_id=TASK, started=binding(HERE / "source/started.json"),
         go=started["go"], plan=binding(HERE / "source-plan.json"), local=binding(HERE / "source/local.json"),
         requests=frozen_requests(local), created_at=now()))
    context_binding = binding(HERE / "source/context.json")
    context = load(context_binding["path"])
    transport = module("oct20_received_operating_transport", receive_transport()).CurrentScienceSourceTransport()
    writer = upstream_function(FUTURE / "source_writer.py", "capture_request")
    def fetch(endpoint, params, timeout):
        source_fetch_guard(context_binding)
        result = transport.fetch(endpoint, params, timeout)
        # The accepted capture writer persists full raw bytes/status before
        # failure/late refusal. No body is discarded to satisfy a line estimate.
        return result
    try:
        for request in context["requests"]:
            writer(HERE / "source" / request["key"], copy.deepcopy(request), DEADLINE,
                   fetch, clock("2026-10-20T00:00:00Z"), context_binding)
        source_fetch_guard(context_binding)
        return finish("source", dict(context=context_binding, local=context["local"], requests=context["requests"],
                      computed_started_at=claim["claimed_at"], computed_completed_at=now()))
    finally:
        transport.close()


def receive_sources():
    result = receive_stage("source")
    context = load(checked(result["context"], HERE / "source/context.json"))
    started = load(checked(context["started"], HERE / "source/started.json"))
    assert context["go"] == started["go"] and context["plan"] == binding(HERE / "source-plan.json")
    local = load(checked(context["local"], HERE / "source/local.json"))
    assert result["local"] == context["local"] and result["requests"] == context["requests"] == frozen_requests(local)
    receive_local_projection(local)
    reader = upstream_function(FUTURE / "source_contract.py", "pages")
    objects, consumed = {}, [result["context"], result["local"]]
    for request in context["requests"]:
        bodies, rows, latest = reader(HERE / "source" / request["key"], request, DEADLINE, clock(started["started_at"]))
        complete = load(HERE / "source" / request["key"] / "complete.json")
        assert complete["capture_context"] == result["context"]
        assert latest <= clock(result["computed_completed_at"]) <= clock(load(HERE / "source/completed.json")["completed_at"])
        objects[request["key"]] = bodies
        consumed.extend(rows)
    expected = {"started.json", "worker-started.json", "context.json", "local.json", "local-projection.json", "output.json", "seal.json", "completed.json"} | {r["key"] for r in context["requests"]}
    assert {p.name for p in (HERE / "source").iterdir()} == expected
    return dict(local=local, objects=objects, consumed=consumed, completed_at=load(HERE / "source/completed.json")["completed_at"])
