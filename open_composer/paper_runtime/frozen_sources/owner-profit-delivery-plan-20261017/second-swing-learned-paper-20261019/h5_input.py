"""One source-linked current input and fixed October training-row reception."""

import hashlib
from zoneinfo import ZoneInfo

from h5_common import (
    HERE, STUDY, SYMBOLS, binding, checked, claim_worker, clock,
    finish, guard_write, load, now, received_inventory, receive_stage,
    start, upstream,
)
from h5_source import receive_child_source, receive_sources


def digest(a):
    return hashlib.sha256(a.tobytes()).hexdigest()


def october_fold(data):
    """Exact original monthly-fold selection for the ONE explicit new epoch."""
    import numpy as np
    dates = data["dates"]
    cutoff = int(np.flatnonzero(dates <= "2026-09-30")[-1])
    assert dates[cutoff] == "2026-09-30"
    calendar = np.arange(cutoff + 1)[-756:]
    calendar = calendar[dates[calendar] >= "2021-01-04"]
    mature = calendar[data["maturity"][calendar] <= cutoff]
    ii, jj = np.where(data["eligible"][mature] & np.isfinite(data["labels"][mature]))
    td = mature[ii]
    counts = np.bincount(td, minlength=len(dates))
    weights = 1 / counts[td] if len(td) else np.array([])
    assert len(td) >= 5000 and len(np.unique(td)) >= 252 and len(np.unique(jj)) >= 20, "Unsupported October model depth BLOCKS, never K0"
    return dict(train_d=td, train_j=jj, weights=weights, calendar=calendar,
                cutoff=np.asarray(cutoff))


def source_controls(source, child):
    """Actual raw/action relationship; used in creation and completed reception."""
    import math
    from datetime import date

    def number(value, *, positive=False, integer=False):
        assert type(value) in [int, float] and math.isfinite(value)
        assert value > 0 if positive else value >= 0
        assert not integer or int(value) == value
        return value

    def dated(value):
        assert type(value) is str and date.fromisoformat(value).isoformat() == value
        return value

    def validate_action(kind, raw):
        assert type(kind) is str and type(raw) is dict
        assert type(raw["id"]) is str and raw["id"]
        for field in ["ex_date", "effective_date", "process_date"]:
            if raw.get(field) is not None:
                dated(raw[field])
        if kind == "cash_dividends":
            assert type(raw["symbol"]) is str and raw["symbol"]
            dated(raw["ex_date"])
            number(raw["rate"])
        elif kind in ["forward_splits", "reverse_splits"]:
            assert type(raw["symbol"]) is str and raw["symbol"]
            dated(raw["ex_date"])
            number(raw["new_rate"], positive=True)
            number(raw["old_rate"], positive=True)
        elif kind == "spin_offs":
            assert all(type(raw[k]) is str and raw[k] for k in ["source_symbol", "new_symbol"])
            dated(raw["ex_date"])
            number(raw["new_rate"], positive=True)
            number(raw["source_rate"], positive=True)

    p = load(HERE / "source-plan.json")
    from h5_common import receive_amendment
    amendment = receive_amendment()
    assert amendment["source01_complete"] == binding(HERE / "source/completed.json")
    assert amendment["actual_fresh_actions"] == binding(HERE / "source/actions/GET001.raw")
    assert child["symbol"] == "VYLR" and child["day"] == "2026-10-01"
    assert child["source"] == binding(HERE / "child-source/output.json")
    assert child["completed"] == binding(HERE / "child-source/completed.json")
    bars = {s: {} for s in p["raw_symbols"]}
    assert source["objects"]["raw-bars"] and source["objects"]["actions"]
    for page in source["objects"]["raw-bars"]:
        assert type(page) is dict and type(page["bars"]) is dict
        assert set(page["bars"]) <= set(bars)
        for symbol, rows in page["bars"].items():
            assert type(rows) is list
            for raw in rows:
                assert type(raw) is dict and type(raw["t"]) is str
                timestamp = clock(raw["t"]).astimezone(ZoneInfo("America/New_York"))
                day = timestamp.date().isoformat()
                assert (timestamp.hour, timestamp.minute, timestamp.second, timestamp.microsecond) == (0, 0, 0, 0), "Daily factory bars require New York midnight session stamps"
                assert day in p["expected_sessions"] and day not in bars[symbol]
                for k in ["o", "c"]:
                    number(raw[k], positive=True)
                number(raw["v"])
                number(raw["n"], integer=True)
                bars[symbol][day] = raw
    # Complete requests alone cannot turn a missing active batch into cash.
    active = [s for s in SYMBOLS if s not in ["RE", "PBCT"]] + ["EG", "MTB", "SPY"]
    for s in active:
        assert set(bars[s]) == set(p["expected_sessions"]), "Incomplete required current source sessions"
    assert not bars["RE"] and not bars["PBCT"], "Ceased original units unexpectedly reopened; receive new identity first"
    bars["VYLR"] = {"2026-10-01": child["raw"]}
    actions = {a["id"]: a for a in load(checked(p["retained_actions"]))}
    for page in source["objects"]["actions"]:
        assert type(page) is dict and type(page["corporate_actions"]) is dict, "Unreceived actions batch is not an empty event set"
        for kind, rows in page["corporate_actions"].items():
            assert type(rows) is list
            for raw in rows:
                validate_action(kind, raw)
                item = dict(id=raw["id"], kind=kind, raw=raw,
                            economic_date=raw.get("ex_date") or raw.get("effective_date") or raw.get("process_date"))
                assert item["economic_date"] is not None
                if item["id"] in actions:
                    old = actions[item["id"]]
                    assert all(old[k] == item[k] for k in item), "Changed accepted action vintage"
                else:
                    if item["economic_date"] <= "2026-09-30":
                        matches = [x for x in amendment["overlay_cells"] if x["new_received_event"] == raw]
                        assert kind == "cash_dividends" and len(matches) == 1, "Only exact two prospectively approved current-window events; no historical rewrite"
                        assert matches[0]["day"] == item["economic_date"] and matches[0]["symbol"] == raw["symbol"]
                    actions[item["id"]] = item
    for a in actions.values():
        if "2026-09-30" <= a["economic_date"] <= "2026-11-14":
            validate_action(a["kind"], a["raw"])
    carrier = {s: ("EG" if s == "RE" else None if s == "PBCT" else s) for s in SYMBOLS}
    # Actual initialization starts in cash. Historic PBCT entitlement stays a
    # signal mark, not a tradable replacement or a new account receivable.
    for a in actions.values():
        if not ("2026-10-16" < a["economic_date"] <= "2026-10-19"):
            continue
        raw = a["raw"]
        affected = set(raw.get(k) for k in ["symbol", "source_symbol", "old_symbol", "acquiree_symbol"])
        if affected & set(active) and a["kind"] != "cash_dividends":
            raise ValueError("Postreference current-unit change needs a new affected scientific reception")
    marks = {s: float(bars[s]["2026-10-16"]["c"]) for s in active if s != "MTB"}
    return dict(bars=bars, actions=[a for a in actions.values() if "2026-09-30" <= a["economic_date"] <= "2026-11-14"], carriers=carrier,
                raw_reference_marks=marks, source_consumed=source["consumed"],
                source_completed_at=source["completed_at"], child_source=child,
                amendment=binding(HERE / "current-input-amendment.json"))


def current_window_overlay(dates, original_returns, original_spy, amendment):
    """Only two current-feature cells change; stored training arrays never change."""
    import numpy as np
    returns, spy = original_returns.copy(), original_spy.copy()
    assert [(x["symbol"], x["day"]) for x in amendment["overlay_cells"]] == [("SPY", "2026-09-18"), ("USB", "2026-09-30")]
    changed = []
    allowed_stock = np.zeros(returns.shape, dtype=bool)
    allowed_spy = np.zeros(spy.shape, dtype=bool)
    for cell in amendment["overlay_cells"]:
        ii = np.flatnonzero(dates == cell["day"])
        assert len(ii) == 1
        i = int(ii[0])
        row, event = cell["old_stored_row"], cell["new_received_event"]
        assert row["cohort_id"] == event["symbol"] == cell["symbol"]
        assert row["return_endpoint"] == event["ex_date"] == cell["day"]
        assert row["cash_per_previous_share"] == 0 and row["stock_distribution_value_per_previous_share"] == 0
        assert cell["cash"] == event["rate"] and cell["denominator"] == row["previous_economic_close"] > 0
        assert cell["old_return"] == row["total_return"]
        target = spy if cell["symbol"] == "SPY" else returns[:, SYMBOLS.index(cell["symbol"])]
        assert target[i] == cell["old_return"], "Frozen original current-window input drift"
        corrected = cell["old_return"] + cell["cash"] / cell["denominator"]
        assert corrected == cell["new_current_window_return"]
        target[i] = corrected
        if cell["symbol"] == "SPY":
            allowed_spy[i] = True
        else:
            allowed_stock[i, SYMBOLS.index(cell["symbol"])] = True
        changed.append(dict(symbol=cell["symbol"], day=cell["day"], old=cell["old_return"], corrected=corrected))
    assert np.array_equal(returns[~allowed_stock], original_returns[~allowed_stock], equal_nan=True)
    assert np.array_equal(spy[~allowed_spy], original_spy[~allowed_spy], equal_nan=True)
    return returns, spy, dict(changed=changed, all_other_prefix_cells_exact=True,
                             training_data_unchanged=True, train_current_vintage_mismatch=True)


def extend_signal(controls):
    """Append only twelve actual economic-return observations, never old labels."""
    import numpy as np
    import pandas as pd
    from open_composer.research.features.price_hygiene import sanitize_price_matrices
    p = load(HERE / "source-plan.json")
    old_rows = pd.read_parquet(checked(p["retained_dated_raw"]))
    cols = SYMBOLS + ["SPY"]
    prior = old_rows.pivot(index="return_endpoint", columns="cohort_id", values="current_mark_raw_close")[cols]
    prior.loc[prior.index >= "2022-04-01", "PBCT"] = np.nan
    assert prior.index[-1] == "2026-09-30"
    bars = controls["bars"]
    for s in cols:
        ticker = "MTB" if s == "PBCT" else "EG" if s == "RE" else s
        row = old_rows[(old_rows.cohort_id == s) & (old_rows.return_endpoint == "2026-09-30")]
        assert len(row) == 1 and float(row.iloc[0].current_mark_raw_close) == float(bars[ticker]["2026-09-30"]["c"]), "Raw boundary vintage/unit drift"
    tail = p["expected_sessions"][1:]
    close = prior.reindex(list(prior.index) + tail).copy()
    opens = close * np.nan
    for s in cols:
        if s == "PBCT":
            continue
        ticker = controls["carriers"].get(s, s)
        for day in tail:
            raw = bars[ticker][day]
            if raw["v"] == 0 and raw.get("n", 0) == 0:
                continue
            close.at[day, s], opens.at[day, s] = raw["c"], raw["o"]
    # Old prefix is immutable accepted signal history. Default sanitizer only
    # determines new physical eligibility/trigger evidence; it never rewrites it.
    clean, _, report = sanitize_price_matrices(close, opens)
    trigger = {(e.as_dict()["symbol"], e.as_dict()["first_session_after"]) for e in report.breaks}
    returns = np.full((len(tail), len(cols)), np.nan)
    available = np.zeros((len(tail), len(cols)), dtype=bool)
    details = []
    for i, day in enumerate(tail):
        prev = p["expected_sessions"][i]
        for j, s in enumerate(cols):
            ticker = "MTB" if s == "PBCT" else controls["carriers"].get(s, s)
            current, previous = bars[ticker][day], bars[ticker][prev]
            ratio, cash, child_value, split = 1.0, 0.0, 0.0, False
            linked = []
            for a in controls["actions"]:
                if a["economic_date"] != day:
                    continue
                raw, kind = a["raw"], a["kind"]
                if kind == "cash_dividends" and raw.get("symbol") == ticker:
                    cash += float(raw["rate"])
                    linked.append(a["id"])
                elif kind in ["forward_splits", "reverse_splits"] and raw.get("symbol") == ticker:
                    f = float(raw["new_rate"]) / float(raw["old_rate"])
                    assert min(abs(f - round(f)), abs(1 / f - round(1 / f))) <= 1e-8, "Unsupported noninteger conversion"
                    ratio *= f
                    split = True
                    linked.append(a["id"])
                elif kind == "spin_offs" and raw.get("source_symbol") == ticker:
                    child = raw["new_symbol"]
                    assert child in bars and day in bars[child], "Unreceived indispensable distributed-child mark"
                    child_value += float(raw["new_rate"]) / float(raw["source_rate"]) * float(bars[child][day]["c"])
                    linked.append(a["id"])
                elif kind not in ["cash_dividends", "forward_splits", "reverse_splits", "spin_offs"]:
                    if ticker in [raw.get(k) for k in ["symbol", "source_symbol", "old_symbol", "acquiree_symbol"]]:
                        raise ValueError("New current episode conversion/action has no accepted mapping")
            multiplier = .118 if s == "PBCT" else 1.0
            pc, cc = multiplier * float(previous["c"]), multiplier * float(current["c"])
            cash *= multiplier
            child_value *= multiplier
            ghost = (current["v"] == 0 and current.get("n", 0) == 0) or (previous["v"] == 0 and previous.get("n", 0) == 0)
            hygiene = (s, day) in trigger
            if not ghost and not hygiene:
                returns[i, j] = (ratio * cc + cash + child_value) / pc - 1
            available[i, j] = s != "PBCT" and bool(pd.notna(clean.at[day, s])) and not hygiene and not split and np.isfinite(returns[i, j])
            details.append(dict(episode=s, carrier=ticker, day=day, previous_raw=previous["c"], raw=current["c"], ratio=ratio,
                                cash_per_economic_parent=cash, child_mark=child_value, action_ids=linked,
                                economic_return=float(returns[i, j]) if np.isfinite(returns[i, j]) else None,
                                available=bool(available[i, j]), split_trigger=split, hygiene_trigger=hygiene, ghost=ghost))
    return returns, available, details, [e.as_dict() for e in report.breaks]


def prepare_current_input():
    if (HERE / "input/completed.json").exists():
        return receive_current_input(require_peer=False)
    start("input", binding(HERE / "child-source/output.json"))
    s = claim_worker("input")
    source = receive_sources()
    child = receive_child_source()
    assert clock(source["completed_at"]) <= clock(child["completed_at"]) <= clock(s["started_at"])
    consumed = received_inventory()
    controls = source_controls(source, child)
    returns, available, details, breaks = extend_signal(controls)
    import numpy as np
    with np.load(checked(load(HERE / "source-plan.json")["accepted_prepared"]), allow_pickle=False) as data:
        assert data["dates"][-1] == "2026-09-30" and data["returns"].shape == (2198, 32)
        assert data["episodes"].tolist() == ["COHORT20210104_" + x for x in SYMBOLS]
        fold = october_fold(data)
        from h5_common import receive_amendment
        amendment = receive_amendment()
        current_history, current_spy, overlay_audit = current_window_overlay(data["dates"][-252:], data["returns"][-252:], data["benchmark_SPY"][-252:], amendment)
        r = np.r_[current_history, returns[:, :32]]
        a = np.r_[data["available"][-252:], available[:, :32]]
        spy = np.r_[current_spy, returns[:, 32]]
        method = upstream("h5_original_method", STUDY / "method.py")
        feature = method.features(r, a, spy)
        td, tj = fold["train_d"], fold["train_j"]
        audit = dict(rows=len(td), dates=len(np.unique(td)), episodes=len(np.unique(tj)),
                     latest_label_end=str(data["dates"][data["maturity"][td].max()]),
                     ID_weight_sha256=hashlib.sha256(np.column_stack([td, tj]).tobytes() + fold["weights"].tobytes()).hexdigest(),
                     labels_sha256=digest(data["labels"][td, tj]), stock_sha256=digest(data["stock"][td, tj]),
                     state_sha256=digest(data["state"][td, tj]), cutoff="2026-09-30", calendar_count=len(fold["calendar"]))
        # Bind preprocessing to the accepted input before any estimator exists.
        # The fit and completed-state receiver compare these exact identities.
        from h5_models import impute
        audit["preprocessing"] = {}
        for arm, names in [("STOCK", method.STOCK), ("STATE", method.STOCK + method.STATE + method.INTERACTIONS + ["missing_" + n for n in method.STATE + method.INTERACTIONS])]:
            train, _, medians = impute(data[arm.lower()][td, tj], np.empty((0, 9 if arm == "STOCK" else 21)), arm == "STATE")
            audit["preprocessing"][arm] = dict(feature_order=names, medians=medians.tolist(),
                medians_sha256=digest(medians), train_matrix_sha256=digest(train), width=train.shape[1])
        # Actual calendar phase is checked without outcomes or legacy targets.
        all_dates = data["dates"].tolist() + load(HERE / "source-plan.json")["expected_sessions"][1:]
        first = all_dates.index("2024-01-02")
        assert (len(all_dates) - 1 - first) % 5 == 0 and all_dates[-1] == "2026-10-16"
        assert all_dates[-6] == "2026-10-09" and all_dates[-11] == "2026-10-02"
    guard_write()
    with (HERE / "input/training.npz").open("xb") as f:
        np.savez_compressed(f, **fold)
    output = dict(reference_day="2026-10-16", source=binding(HERE / "source/output.json"),
                  source_complete=binding(HERE / "source/completed.json"), consumed=consumed,
                  child_source=binding(HERE / "child-source/output.json"), child_source_complete=binding(HERE / "child-source/completed.json"),
                  amendment=binding(HERE / "current-input-amendment.json"), current_window_overlay=overlay_audit,
                  train_current_vintage_mismatch=True,
                  controls=controls, connected_tail=details, hygiene_breaks=breaks,
                  training=binding(HERE / "input/training.npz"), training_audit=audit,
                  current_stock=feature["stock"][-1], current_state=feature["state"][-1],
                  eligible=feature["eligible"][-1], raw_reference_marks=controls["raw_reference_marks"],
                  episode_carriers=controls["carriers"], computed_started_at=load(HERE / "input/worker-started.json")["claimed_at"], computed_completed_at=now())
    # Nonfinite legitimate state numerics are encoded null, never zeros.
    from h5_common import clean
    return finish("input", clean(output))


def receive_current_input(*, require_peer=True):
    obj = receive_stage("input")
    assert obj["reference_day"] == "2026-10-16"
    assert obj["source"] == binding(HERE / "source/output.json") and obj["source_complete"] == binding(HERE / "source/completed.json")
    source = receive_sources()
    child = receive_child_source()
    assert obj["child_source"] == binding(HERE / "child-source/output.json") and obj["child_source_complete"] == binding(HERE / "child-source/completed.json")
    assert obj["amendment"] == binding(HERE / "current-input-amendment.json") and obj["train_current_vintage_mismatch"] is True
    assert obj["controls"] == source_controls(source, child), "Stored controls must relate to exact actual source"
    assert obj["raw_reference_marks"] == obj["controls"]["raw_reference_marks"]
    assert obj["episode_carriers"] == obj["controls"]["carriers"]
    assert obj["consumed"] == received_inventory()
    checked(obj["training"], HERE / "input/training.npz")
    assert len(obj["eligible"]) == len(obj["current_stock"]) == len(obj["current_state"]) == 32
    assert all(type(x) is bool for x in obj["eligible"])
    assert all(len(x) == 9 for x in obj["current_stock"]) and all(len(x) == 21 for x in obj["current_state"])
    if require_peer:
        from h5_common import receive_input_review
        r = receive_input_review(binding(HERE / "independent-current-input-review.json"), binding(HERE / "input/output.json"))
        assert r["derived_control_witness"] == binding(HERE / "input/output.json")
    return obj
