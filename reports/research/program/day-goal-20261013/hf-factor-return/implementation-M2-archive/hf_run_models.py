"""Bound complete model study. Real-market computation starts only after native gates."""

import argparse
import json
import math
import mmap
import os
import pickle
import re
import resource
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
from hf_features import FEATURE, P, bind, save
from hf_models import Moments, hgb, ols, pls_prefix, ridge_path

IT = "t20261013_hf_factor_conditional_method"
E = P / "economic"
M = E / "models"


def economic_cpu_used():
    used = 0.0
    for path in E.glob("*-resource-*.txt"):
        text = path.read_text()
        for kind in ["User", "System"]:
            match = re.search(kind + r" time \(seconds\): ([\d.]+)", text)
            if match:
                used += float(match.group(1))
    return used


def guard(stage):
    from open_composer.research.iteration_dossier import validate_iteration_dossier

    hold = json.loads(Path("reports/research/control/owner-compute-hold.json").read_text())
    assert hold.get("research_paused") is False
    review = json.loads((P / "independent-implementation-review.json").read_text())
    assert review["verdict"] == "approve_implementation" and review["author"] != review["reviewer"]
    rows = review["bindings"]
    rows = list(rows.values()) if isinstance(rows, dict) else rows
    assert any(r["sha256"] == bind(P / "implementation-manifest.json")["sha256"] for r in rows)
    gate = validate_iteration_dossier(IT, Path.cwd(), stage="pre-backtest")
    assert gate.status == "ok", gate.blocked
    admission = json.loads((P / "resource-admission.json").read_text())
    assert admission["local_CPU_cores"] == 1 and admission["memory_cap_MiB"] <= 900
    assert admission["economic_unique_cap_coreseconds"] == 7006.69
    if stage != "calibrate":
        projection = json.loads((E / "full-resource-projection.json").read_text())
        assert projection["full_package_fits_existing_cap"]
    os.sched_setaffinity(0, {min(os.sched_getaffinity(0))})
    remaining = 7006.69 - economic_cpu_used()
    future = 300 + 106.69  # Independent result reservation and unreleased contingency.
    if stage == "linear":
        future += 700 + projection["HGB_remaining_conservative_CPU"]
    elif stage == "hgb":
        future += 700
    limit = min(
        {"calibrate": 450, "linear": 1700, "hgb": 4200}[stage], math.floor(remaining - future)
    )
    assert limit > 0, "actual remaining economic cap/reservations block this stage"
    resource.setrlimit(resource.RLIMIT_CPU, (limit, limit))
    E.mkdir(exist_ok=True)
    M.mkdir(exist_ok=True)
    return admission


def dataset():
    meta = json.loads((FEATURE / "feature-metadata.json").read_text())
    rows = json.loads((FEATURE / "packet-row-clock.json").read_text())
    n = meta["n_rows"]
    assert n == len(rows)
    years = np.array([int(r["date"][:4]) for r in rows])
    labels = np.load(FEATURE / "labels.npy", mmap_mode="r")[:n]
    eligible = np.flatnonzero((years >= 1997) & np.isfinite(labels).all(1))
    return meta, rows, years, labels, eligible


def feature_path(candidate):
    if candidate.get("measurement") == "MARKET_LAGS":
        return FEATURE / "AR26.npy"
    suffix = "_STALE" if candidate.get("feature_set") == "STALE" else ""
    return FEATURE / ("HAR-" + candidate["measurement"] + suffix + ".npy")


def columns(candidate, meta):
    if candidate.get("measurement") == "MARKET_LAGS":
        return np.arange(candidate["lags"])
    kind = candidate["feature_set"]
    if kind == "MKT":
        factors = [meta["market_column"]]
    elif kind == "KEY6":
        factors = sorted([meta["market_column"]] + meta["key5_columns"])
    elif kind == "MINUS5":
        factors = [i for i in range(272) if i not in meta["key5_columns"]]
    else:
        factors = list(range(272))
    return np.array([j * 272 + i for j in range(3) for i in factors])


def evict(x):
    if isinstance(x, np.memmap):
        x._mmap.madvise(mmap.MADV_DONTNEED)


def predict_coefficients(x, ids, cols, coefficients, state):
    beta = np.column_stack(coefficients)
    result = np.empty((len(ids), len(coefficients)))
    for start in range(0, len(ids), 2048):
        ix = ids[start : start + 2048]
        part = x[np.ix_(ix, cols)]
        scaled = (part - state["mean"]) / state["scale"]
        result[start : start + len(ix)] = (scaled @ beta) * state["target_scale"] + state[
            "target_mean"
        ]
        evict(x)
    return result


def trial(candidate, year, parameters, **extra):
    row = dict(
        candidate_id=candidate["candidate_id"],
        historical_train_validation_end_year=year - 1,
        test_start_year=year,
        parameters=parameters,
        source_seen=True,
        feature_input_manifest=bind(FEATURE / "feature-input-manifest.json"),
        label=candidate.get("label"),
        cost_selection_used=False,
        **extra,
    )
    row["logical_trial_id"] = (
        candidate["candidate_id"] + "__" + str(year) + "__" + json.dumps(parameters, sort_keys=True)
    )
    with (E / "model-trial-ledger.jsonl").open("a") as f:
        f.write(json.dumps(row, allow_nan=False) + "\n")


def linear():
    meta, rows, years, labels, eligible = dataset()
    candidates = [
        c
        for c in json.loads((P / "scientific-plan.json").read_text())["candidates"]
        if c["model"] != "HGB"
    ]
    predictions = np.full((len(rows), len(candidates)), np.nan)
    caches = {}
    folds = []
    for year in range(2004, 2021):
        historical = eligible[years[eligible] < year]
        n = math.floor(0.8 * len(historical))
        train, valid = historical[:n], historical[n:]
        test = np.flatnonzero(years == year)  # Does not require a matured future target.
        for j, c in enumerate(candidates):
            if c["model"] == "zero":
                predictions[test, j] = 0
                continue
            target = 0 if c.get("label") == "All" else 1
            if c["model"] == "historical_training_mean":
                value = float(labels[train, target].mean())
                predictions[test, j] = value
                trial(c, year, {}, n_train=n, n_validation=len(valid), physical_training_mean=True)
                save(
                    M / f"{c['candidate_id']}-{year}.json",
                    dict(value=value, n_train=n, label=c["label"]),
                )
                continue
            path = feature_path(c)
            save(
                E / "linear-current-fit.json",
                dict(
                    candidate_id=c["candidate_id"],
                    year=year,
                    n_train=n,
                    actual_train_last_date=rows[int(train[-1])]["date"],
                    validation_last_date=rows[int(valid[-1])]["date"],
                    source_feature=bind(FEATURE / "feature-input-manifest.json"),
                    physical_shared_moment_preparation_started=True,
                ),
            )
            x = np.load(path, mmap_mode="r")[: len(rows)]
            name = str(path)
            if name not in caches:
                caches[name] = (Moments(x.shape[1]), 0)
            moments, previous_n = caches[name]
            assert previous_n <= n
            for start in range(previous_n, n, 2048):
                ids = train[start : min(start + 2048, n)]
                moments.add(x[ids], np.asarray(labels[ids]))
                evict(x)
            caches[name] = (moments, n)
            cols = columns(c, meta)
            gram, cross, state = moments.standardized(cols, target)
            if c["model"] == "PLS":
                params = [dict(K=k) for k in range(1, min(10, len(cols)) + 1)]
                betas = pls_prefix(gram, cross, len(params))
            elif c["model"] == "Ridge":
                grid = np.linspace(-1, 8, 100)
                params = [
                    dict(
                        log_lambda=float(v),
                        lambda_normalized=float(np.exp(v)),
                        alpha_unscaled=float(n * np.exp(v)),
                    )
                    for v in grid
                ]
                betas = ridge_path(gram, cross, grid)
            else:
                params = [dict(solver="np.linalg.lstsq_normalized_Gram_rcondNone")]
                betas = [ols(gram, cross)]
            valpred = predict_coefficients(x, valid, cols, betas, state)
            losses = np.square(valpred - labels[valid, target, None]).mean(0)
            best = int(np.argmin(losses))
            predictions[test, j] = predict_coefficients(x, test, cols, [betas[best]], state)[:, 0]
            for k, param in enumerate(params):
                trial(
                    c,
                    year,
                    param,
                    n_train=n,
                    n_validation=len(valid),
                    validation_MSE=float(losses[k]),
                    selected_by_validation=k == best,
                    physical_shared_moments=True,
                    physical_prefix_reuse=c["model"] == "PLS",
                )
            model_path = M / f"{c['candidate_id']}-{year}.npz"
            np.savez(
                model_path,
                coefficient=betas[best],
                columns=cols,
                mean=state["mean"],
                scale=state["scale"],
                target_mean=state["target_mean"],
                target_scale=state["target_scale"],
                constant=state["constant"],
            )
            folds.append(
                dict(
                    candidate_id=c["candidate_id"],
                    year=year,
                    n_train=n,
                    n_validation=len(valid),
                    train_last_row=int(train[-1]),
                    validation_last_row=int(valid[-1]),
                    test_rows=len(test),
                    selected=params[best],
                    model=bind(model_path),
                    validation_MSE=float(losses[best]),
                )
            )
        save(E / "linear-progress.json", dict(last_completed_year=year, whole_study_complete=False))
        print("linear_complete_year", year, flush=True)
    np.save(E / "linear-predictions.npy", predictions)
    save(
        E / "linear-model-manifest.json",
        dict(
            candidate_ids=[c["candidate_id"] for c in candidates],
            predictions=bind(E / "linear-predictions.npy"),
            folds=folds,
            source_feature_manifest=bind(FEATURE / "feature-input-manifest.json"),
        ),
    )


def scaled_hgb_input(measurement, year):
    meta, rows, years, labels, eligible = dataset()
    prior = eligible[years[eligible] < year]
    n = math.floor(0.8 * len(prior))
    raw = np.load(FEATURE / f"HAR-{measurement}.npy", mmap_mode="r")[: len(rows)]
    path = E / f"HGB-scaled-{measurement}-{year}.npy"
    state_path = E / f"HGB-scaling-{measurement}-{year}.npz"
    if path.exists() and state_path.exists():
        data = np.load(path, mmap_mode="r")
        with np.load(state_path) as f:
            state = {k: f[k].copy() for k in f.files}
        assert data.shape == (len(prior), 816) and int(state["n_train"]) == n
        return data, labels[prior, 1], state, n, prior
    moments = Moments(816)
    for start in range(0, n, 2048):
        ids = prior[start : min(start + 2048, n)]
        # The scaler needs diagonal moments, not a fresh full Gram.
        part = raw[ids]
        moments.n += len(part)
        moments.sx += part.sum(0)
        moments.xx[np.diag_indices(816)] += np.square(part).sum(0)
        moments.sy += labels[ids].sum(0)
        moments.yy += np.square(labels[ids]).sum(0)
        evict(raw)
    _, _, state = moments.standardized(np.arange(816), 1)
    scaled = np.lib.format.open_memmap(path, mode="w+", dtype="float64", shape=(len(prior), 816))
    for start in range(0, len(prior), 2048):
        ids = prior[start : start + 2048]
        scaled[start : start + len(ids)] = (raw[ids] - state["mean"]) / state["scale"]
        scaled.flush()
        evict(scaled)
        evict(raw)
    np.savez(state_path, **state)
    save(
        E / f"HGB-input-{measurement}-{year}.json",
        dict(
            scaled=bind(path),
            scaling=bind(state_path),
            source=bind(FEATURE / "feature-input-manifest.json"),
            n_train=n,
            n_validation=len(prior) - n,
            training_last_row=int(prior[n - 1]),
            actual_training_last_date=rows[int(prior[n - 1])]["date"],
            validation_last_row=int(prior[-1]),
            actual_validation_last_date=rows[int(prior[-1])]["date"],
            year=year,
        ),
    )
    return scaled, labels[prior, 1], state, n, prior


def checkpoint_path(measurement, year, depth, rate, trees):
    return M / f"HGB-{measurement}-{year}-depth{depth}-lr{rate}-trees{trees}.pkl"


def calibrate():
    before = resource.getrusage(resource.RUSAGE_SELF)
    x, y, state, n, prior = scaled_hgb_input("IDX", 2019)
    ys = (y[:n] - state["target_mean"]) / state["target_scale"]
    model = hgb(6, 0.1, 50, warm_start=True)
    stages = []
    candidate = next(
        c
        for c in json.loads((P / "scientific-plan.json").read_text())["candidates"]
        if c["candidate_id"] == "HGB_IDX_CTS"
    )
    for trees in [50, 150, 350]:
        trial(
            candidate,
            2019,
            dict(depth=6, learning_rate=0.1, max_iter=trees),
            calibration=True,
            state="started",
            validation_score_deferred=True,
        )
        model.set_params(max_iter=trees).fit(x[:n], ys)
        path = checkpoint_path("IDX", 2019, 6, 0.1, trees)
        path.write_bytes(pickle.dumps(model, protocol=5))
        used = resource.getrusage(resource.RUSAGE_SELF)
        elapsed = used.ru_utime + used.ru_stime - before.ru_utime - before.ru_stime
        stages.append(
            dict(
                trees=trees,
                checkpoint=bind(path),
                cumulative_CPU=elapsed,
                max_RSS_KiB=used.ru_maxrss,
            )
        )
        save(
            E / "calibration-progress.json",
            dict(stages=stages, n_train=n, validation_or_test_metrics_read=False),
        )
        trial(
            candidate,
            2019,
            dict(depth=6, learning_rate=0.1, max_iter=trees),
            calibration=True,
            state="completed",
            trees_added=trees - (stages[-2]["trees"] if len(stages) > 1 else 0),
            validation_score_deferred=True,
        )
        print("calibration_trees", trees, "CPU", round(elapsed, 3), flush=True)
        evict(x)
    _, _, years, labels, eligible = dataset()
    ratios = {
        year: math.floor(0.8 * sum(years[eligible] < year)) / n for year in [2004, 2009, 2014, 2019]
    }
    # Conservatively count both depths at the measured larger depth, both rates/views.
    equivalents = 8 * sum(ratios.values()) - 1
    measured = stages[-1]["cumulative_CPU"]
    remaining_hgb = measured * equivalents * 1.25
    projection = dict(
        schema_version=1,
        calibration_cell="HGB_IDX_CTS/2019/depth6/lr.1/350",
        calibration_CPU=measured,
        n_train=n,
        refit_n_ratios=ratios,
        remaining_largestfit_equivalents=equivalents,
        HGB_remaining_conservative_CPU=remaining_hgb,
        linear_ceiling=1700,
        accounts_ceiling=700,
        independent_result_reservation=300,
        extra_margin=500,
        author_estimated_whole_economic_CPU=measured + remaining_hgb + 1700 + 700 + 300 + 500,
        unique_economic_cap=7006.69,
        full_package_fits_existing_cap=measured + remaining_hgb + 1700 + 700 + 300 + 500 <= 7006.69,
        actual_test_or_economic_metrics_seen=False,
        stages=stages,
        fit_memory_peak_KiB=stages[-1]["max_RSS_KiB"],
        no_automatic_scope_reduction=True,
    )
    save(E / "full-resource-projection.json", projection)
    print(
        "full_package_fits_existing_cap", projection["full_package_fits_existing_cap"], flush=True
    )


def nonlinear():
    meta, rows, years, labels, eligible = dataset()
    prediction = np.full((len(rows), 2), np.nan)
    summaries = []
    for column, view in enumerate(["IDX", "INV"]):
        candidate = next(
            c
            for c in json.loads((P / "scientific-plan.json").read_text())["candidates"]
            if c["candidate_id"] == f"HGB_{view}_CTS"
        )
        raw = np.load(FEATURE / f"HAR-{view}.npy", mmap_mode="r")[: len(rows)]
        for year in [2004, 2009, 2014, 2019]:
            x, y, state, n, prior = scaled_hgb_input(view, year)
            ys = (y[:n] - state["target_mean"]) / state["target_scale"]
            candidates = []
            for depth in [4, 6]:
                for rate in [0.01, 0.1]:
                    model = None
                    for trees in [50, 150, 350]:
                        path = checkpoint_path(view, year, depth, rate, trees)
                        reused = (
                            path.exists()
                            and view == "IDX"
                            and year == 2019
                            and depth == 6
                            and rate == 0.1
                        )
                        if reused:
                            model = pickle.loads(path.read_bytes())
                        else:
                            trial(
                                candidate,
                                year,
                                dict(depth=depth, learning_rate=rate, max_iter=trees),
                                state="started",
                                physical_warmstart=True,
                                validation_score_deferred=True,
                            )
                            model = (
                                hgb(depth, rate, trees, warm_start=True)
                                if model is None
                                else model.set_params(max_iter=trees)
                            )
                            model.fit(x[:n], ys)
                            path.write_bytes(pickle.dumps(model, protocol=5))
                        evict(x)
                        val = model.predict(x[n:]) * state["target_scale"] + state["target_mean"]
                        mse = float(np.square(val - y[n:]).mean())
                        candidates.append((mse, trees, depth, rate, path))
                        if not reused:
                            trial(
                                candidate,
                                year,
                                dict(depth=depth, learning_rate=rate, max_iter=trees),
                                physical_warmstart=True,
                                validation_MSE=mse,
                                calibration_reused=False,
                                state="completed",
                                trees_added=trees
                                - (50 if trees == 150 else 150 if trees == 350 else 0),
                            )
                        else:
                            save(
                                E / f"calibration-validation-{trees}.json",
                                dict(validation_MSE=mse, checkpoint=bind(path), no_new_fit=True),
                            )
                        evict(x)
            winner = min(candidates, key=lambda r: r[:4])
            model = pickle.loads(winner[-1].read_bytes())
            test = np.flatnonzero((years >= year) & (years < min(year + 5, 2021)))
            for start in range(0, len(test), 2048):
                ids = test[start : start + 2048]
                part = (raw[ids] - state["mean"]) / state["scale"]
                prediction[ids, column] = (
                    model.predict(part) * state["target_scale"] + state["target_mean"]
                )
                evict(raw)
            summaries.append(
                dict(
                    candidate_id=candidate["candidate_id"],
                    year=year,
                    selected=dict(trees=winner[1], depth=winner[2], learning_rate=winner[3]),
                    validation_MSE=winner[0],
                    n_train=n,
                    n_validation=len(prior) - n,
                    test_rows=len(test),
                    model=bind(winner[-1]),
                    frozen5year=True,
                )
            )
            print("HGB_complete", view, year, flush=True)
    np.save(E / "HGB-predictions.npy", prediction)
    save(
        E / "HGB-model-manifest.json",
        dict(
            candidate_ids=["HGB_IDX_CTS", "HGB_INV_CTS"],
            folds=summaries,
            predictions=bind(E / "HGB-predictions.npy"),
        ),
    )


def main():
    args = argparse.ArgumentParser()
    args.add_argument("stage", choices=["calibrate", "linear", "hgb"])
    stage = args.parse_args().stage
    guard(stage)
    save(
        E / f"{stage}-inflight.json",
        dict(
            pid=os.getpid(),
            started_at=datetime.now(UTC).isoformat(),
            code=bind(Path(__file__)),
            stage=stage,
            previous_CPU_and_failures_retained=True,
        ),
    )
    {"calibrate": calibrate, "linear": linear, "hgb": nonlinear}[stage]()
    used = resource.getrusage(resource.RUSAGE_SELF)
    save(
        E / f"{stage}-resource.json",
        dict(
            CPU_process=used.ru_utime + used.ru_stime,
            max_RSS_KiB=used.ru_maxrss,
            stage=stage,
            completed=True,
            model_trials=bind(E / "model-trial-ledger.jsonl"),
        ),
    )


if __name__ == "__main__":
    main()
