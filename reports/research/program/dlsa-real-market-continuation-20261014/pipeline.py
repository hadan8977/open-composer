"""Executable fixed method package. Economic branch is blocked until real admission."""

import argparse
import hashlib
import importlib.util
import json
import time
from pathlib import Path

import numpy as np
from method_math import (
    fractional_account,
    paired_summary,
    path_windows,
    pca_projection,
    performance_summary,
    project,
    source_ou_policy,
    threshold_policy,
)

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[3]


def load(name):
    return json.loads((OUT / name).read_text())


def write(name, value):
    p = OUT / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(value, indent=2, default=str) + "\n")


def checked(binding):
    primary = ROOT / binding["path"]
    path = primary if primary.is_file() else OUT / binding["path"]
    if not path.is_file() or not path.resolve().is_relative_to(ROOT) or path.is_symlink():
        raise ValueError("invalid actual bound file")
    if hashlib.sha256(path.read_bytes()).hexdigest() != binding["sha256"]:
        raise ValueError("changed bound file " + str(path))
    return path


def blockers():
    result = []
    for name, required in [
        ("independent-plan-review.json", {"verdict": "approve_deep_plan"}),
        ("independent-implementation-review.json", {"verdict": "approve_implementation"}),
        ("root-admission.json", {"economic_execution_admitted": True, "training_allocated": True}),
        ("inputs/independent-method-input-acceptance.json", {"accepted": True}),
        ("native-gates/final-admission-receipt.json", {"status": "ok"}),
    ]:
        try:
            obj = load(name)
            if any(obj.get(k) != v for k, v in required.items()):
                result.append(name + ": required actual verdict/admission absent")
            if "independent" in name and (
                not obj.get("reviewer") or obj.get("reviewer") == obj.get("author")
            ):
                result.append(name + ": independent authorship absent")
            for b in obj.get("bindings", {}).values():
                if isinstance(b, dict) and "sha256" in b:
                    checked(b)
        except (OSError, ValueError, KeyError) as exc:
            result.append(name + ": " + str(exc))
    # Authorization snapshots cannot turn the current action-specific policy into
    # a timeless lease. Root admission is task-scoped, not self-created here.
    hold = json.loads((ROOT / "reports/research/control/owner-compute-hold.json").read_text())
    if hold.get("research_paused"):
        result.append("current owner research pause")
    try:
        admission = load("root-admission.json")
        if admission.get("task_id") != "DLSA-REAL-MARKET-METHOD-20261014":
            result.append("wrong root task admission")
        if (
            admission.get("plan_sha256")
            != hashlib.sha256((OUT / "scientific-plan.md").read_bytes()).hexdigest()
        ):
            result.append("root admission not bound to this complete scientific plan")
        if not admission.get("fresh_resource_admission"):
            result.append("fresh resource/worker/budget admission absent")
    except (OSError, ValueError):
        pass
    return result


def construct_inputs(packet):
    returns = packet["total_return"].astype(np.float64)
    signal = packet["available_to_signal"].astype(bool)
    live = packet["episode_alive"].astype(bool)
    t, n = returns.shape
    residual = np.full((t, n), np.nan)
    projections = np.zeros((t, n, n), dtype=np.float32)
    for i in range(252, t):
        history = returns[i - 252 : i]
        eligible = np.isfinite(history).all(axis=0) & live[i - 1] & signal[i - 1]
        ids = np.flatnonzero(eligible)
        if len(ids) < 7:
            continue
        p = pca_projection(history[:, ids])
        projections[i][np.ix_(ids, ids)] = p
        if np.isfinite(returns[i, ids]).all() and signal[i, ids].all():
            residual[i, ids] = p @ returns[i, ids]
    return residual, projections


def cnn_type():
    p = OUT / "implementation/source-CNNTransformer.py"
    approved = load("implementation-manifest.json")
    bound = next(b for b in approved["files"] if b["path"].endswith(p.name))
    checked(bound)
    spec = importlib.util.spec_from_file_location("dlsa_source_cnn", p)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.CNNTransformer


def train_fit(torch, model_type, candidate, paths, residual, projections, execution, returns):
    fit_id = candidate["fit_id"]
    dest = OUT / "run/checkpoints" / (fit_id + ".pt")
    dest.parent.mkdir(parents=True, exist_ok=True)
    device = load("root-admission.json").get("device", "cpu")
    model = model_type(random_seed=candidate["seed"], lookback=30, device=device).to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=0.001)
    start_epoch, start_batch = 0, 0
    manifest_sha = hashlib.sha256((OUT / "candidate-manifest.json").read_bytes()).hexdigest()
    if dest.exists():
        saved = torch.load(dest, map_location=device, weights_only=False)
        if saved["manifest_sha256"] != manifest_sha:
            raise ValueError("checkpoint belongs to another fixed experiment")
        model.load_state_dict(saved["model"])
        optimizer.load_state_dict(saved["optimizer"])
        torch.set_rng_state(saved["rng_cpu"].cpu())
        if device.startswith("cuda"):
            torch.cuda.set_rng_state_all(saved["rng_cuda"])
        start_epoch, start_batch = saved["epoch"], saved["batch"]
    rows = candidate["training_execution_indices"]
    for epoch in range(start_epoch, 100):
        model.train()
        for batch, lo in enumerate(range(0, len(rows), 125)):
            if epoch == start_epoch and batch < start_batch:
                continue
            ii = np.asarray(rows[lo : lo + 125])
            eligible = np.isfinite(paths[ii]).all(axis=-1)
            if not eligible.any(axis=1).all():
                raise ValueError("no causal residual signal in training date; no row deletion")
            x = torch.as_tensor(paths[ii][eligible], dtype=torch.float32, device=device)
            raw = torch.zeros(eligible.shape, dtype=torch.float32, device=device)
            raw[torch.as_tensor(eligible, device=device)] = model(x).reshape(-1)
            # Execution e uses the factor projection estimated no later than e-1.
            p = torch.as_tensor(projections[execution[ii] - 1], device=device)
            q0 = torch.bmm(raw[:, None, :], p).squeeze(1)
            q = q0 / (q0.abs().sum(dim=1, keepdim=True) + 1e-8)
            r = returns[execution[ii] + 1]
            exposed = q.detach().cpu().numpy() != 0
            if not np.isfinite(r[exposed]).all():
                raise ValueError("unresolved held training return; no zero/drop")
            r = torch.as_tensor(np.where(np.isfinite(r), r, 0), dtype=torch.float32, device=device)
            gross = (q * r).sum(dim=1)
            turnover = torch.cat([q[:1].abs().sum(dim=1), (q[1:] - q[:-1]).abs().sum(dim=1)])
            cost = candidate["training_costs"]
            net = (
                gross
                - cost["transaction"] * turnover
                - cost["short_daily"] * q.clamp(max=0).abs().sum(dim=1)
            )
            loss = -net.mean() / (net.std(unbiased=False) + 1e-8)
            if not torch.isfinite(loss):
                raise ValueError("nonfinite objective")
            optimizer.zero_grad()
            loss.backward()
            if any(
                p.grad is not None and not torch.isfinite(p.grad).all() for p in model.parameters()
            ):
                raise ValueError("nonfinite gradient")
            count = load("run/training-exposure.json")
            count["attempted_updates"] += 1
            write("run/training-exposure.json", count)
            optimizer.step()
            count["completed_updates"] += 1
            write("run/training-exposure.json", count)
            next_epoch, next_batch = (epoch, batch + 1) if lo + 125 < len(rows) else (epoch + 1, 0)
            value = {
                "model": model.state_dict(),
                "optimizer": optimizer.state_dict(),
                "epoch": next_epoch,
                "batch": next_batch,
                "rng_cpu": torch.get_rng_state(),
                "rng_cuda": torch.cuda.get_rng_state_all() if device.startswith("cuda") else [],
                "manifest_sha256": manifest_sha,
            }
            temp = dest.with_suffix(".tmp")
            torch.save(value, temp)
            temp.replace(dest)
        start_batch = 0
    model.eval()
    indices = np.asarray(candidate["evaluation_execution_indices"])
    output = []
    with torch.no_grad():
        for ii in np.array_split(indices, max(1, int(np.ceil(len(indices) / 8)))):
            path_index = ii - candidate.get("inference_lag_sessions", 0)
            if np.any(path_index < 0):
                raise ValueError("placebo history unavailable")
            mask = np.isfinite(paths[path_index]).all(axis=-1)
            raw = np.zeros(mask.shape)
            if mask.any():
                raw[mask] = (
                    model(
                        torch.as_tensor(paths[path_index][mask], dtype=torch.float32, device=device)
                    )
                    .reshape(-1)
                    .cpu()
                    .numpy()
                )
            output.extend(project(raw, projections[execution[ii] - 1]))
    return np.asarray(output)


def run():
    blocked = blockers()
    write(
        "native-gates/attempted-economic-entry.json",
        {"blocked": blocked, "training_started": False, "economic_started": False},
    )
    if blocked:
        raise SystemExit("economic execution blocked; see attempted-economic-entry.json")
    acceptance = load("inputs/independent-method-input-acceptance.json")
    packet = np.load(checked(acceptance["bindings"]["packet"]), allow_pickle=False)
    dates = packet["dates"].astype(str)
    expected = load("candidate-manifest.json")
    if list(dates) != expected["calendar"]:
        raise ValueError("accepted date calendar differs from frozen manifest")
    started = time.monotonic()
    exposure = OUT / "run/training-exposure.json"
    if not exposure.exists():
        write(
            "run/training-exposure.json",
            {
                "attempted_updates": 0,
                "completed_updates": 0,
                "completed_fit_ids": [],
                "historical_accepted_fits": 12,
                "historical_accepted_updates": 9600,
            },
        )
    residual, projections = construct_inputs(packet)
    execution = np.arange(30, len(dates) - 1)
    paths = path_windows(residual, execution)
    eval_index = np.asarray(expected["evaluation_execution_indices"])
    eval_positions = np.searchsorted(execution, eval_index)
    daily_returns = packet["total_return"][eval_index + 1]
    simple, pathz, old = [], [], None
    for i, e in zip(eval_positions, eval_index, strict=True):
        available = np.isfinite(paths[i]).all(axis=-1)
        old = threshold_policy(np.where(available[:, None], paths[i], 0), old)
        old[~available] = 0
        ou = source_ou_policy(np.where(available[:, None], paths[i], 0))
        ou[~available] = 0
        simple.append(project(ou, projections[e - 1]))
        pathz.append(project(old, projections[e - 1]))
    targets = {"S0": np.asarray(simple), "S3": np.zeros_like(simple), "S6": np.asarray(pathz)}
    import torch

    torch.set_num_threads(1)
    model_type = cnn_type()
    fits = expected["fits"]
    seed_targets = {method: [] for method in ["S1", "S2", "S4"]}
    for method in ["S1", "S2"]:
        for seed in [0, 1]:
            segments, placebo_segments = [], []
            for fit in [x for x in fits if x["stream"] == method and x["seed"] == seed]:
                remaining = load("run/training-exposure.json")
                if (
                    remaining["attempted_updates"] >= 19200
                    and fit["fit_id"] not in remaining["completed_fit_ids"]
                ):
                    raise ValueError("complete cumulative update cap exhausted")
                fit["training_execution_indices"] = np.searchsorted(
                    execution, fit["training_calendar_indices"]
                ).tolist()
                fit["evaluation_execution_indices"] = np.searchsorted(
                    execution, fit["evaluation_calendar_indices"]
                ).tolist()
                segment = train_fit(
                    torch,
                    model_type,
                    fit,
                    paths,
                    residual,
                    projections,
                    execution,
                    packet["total_return"],
                )
                if fit["block"] == -1:
                    val_r = packet["total_return"][
                        np.asarray(fit["evaluation_calendar_indices"]) + 1
                    ]
                    write(
                        "run/validation/" + fit["fit_id"] + ".json",
                        {
                            "diagnostic_only_no_model_selection": True,
                            "source5_short1": fractional_account(segment, val_r, 0.0005, 0.0001),
                        },
                    )
                else:
                    segments.append(segment)
                if method == "S2" and fit["block"] >= 0:
                    placebo = dict(fit, inference_lag_sessions=60)
                    placebo_segments.append(
                        train_fit(
                            torch,
                            model_type,
                            placebo,
                            paths,
                            residual,
                            projections,
                            execution,
                            packet["total_return"],
                        )
                    )
                remaining = load("run/training-exposure.json")
                if fit["fit_id"] not in remaining["completed_fit_ids"]:
                    remaining["completed_fit_ids"].append(fit["fit_id"])
                    write("run/training-exposure.json", remaining)
            seed_targets[method].append(np.concatenate(segments))
            if method == "S2":
                seed_targets["S4"].append(np.concatenate(placebo_segments))
        targets[method] = np.mean(seed_targets[method], axis=0)
    targets["S4"] = np.mean(seed_targets["S4"], axis=0)
    targets["S5"] = targets["S2"].copy()
    targets["S5"][125:145] = 0
    for method in ["S1", "S2", "S4"]:
        for seed, q in enumerate(seed_targets[method]):
            targets[method + "_seed" + str(seed)] = q
    reports = {}
    for name, q in targets.items():
        reports[name] = {}
        for bps in [0, 2, 5, 10, 20, 40]:
            reports[name][str(bps)] = fractional_account(q, daily_returns, bps / 10000, 0.0001)
    primary = {name: np.asarray([r["net_return"] for r in reports[name]["5"]]) for name in reports}
    write("run/matched-net-returns.json", reports)
    write(
        "run/performance-summary.json",
        {
            name: {fee: performance_summary(rows) for fee, rows in cells.items()}
            for name, cells in reports.items()
        },
    )
    benchmark = {"not_available": {}, "same_symbol": {}}
    live = packet["episode_alive"][eval_index - 1].astype(bool)
    alive_count = live.sum(axis=1, keepdims=True)
    if not np.any(alive_count == 0):
        ew = live / alive_count
        benchmark["historical_cohort_equal_weight"] = performance_summary(
            fractional_account(ew, daily_returns, 0.0005, 0.0001)
        )
    for j, security in enumerate(packet["security_episode"].astype(str)):
        if not live[:, j].all():
            benchmark["not_available"][security] = (
                "not eligible whole evaluation; no survivor replacement"
            )
            continue
        q = np.zeros_like(daily_returns)
        q[:, j] = 1
        try:
            benchmark["same_symbol"][security] = performance_summary(
                fractional_account(q, daily_returns, 0.0005, 0.0001)
            )
        except ValueError:
            benchmark["not_available"][security] = "unresolved economic return"
    if benchmark["same_symbol"]:
        winner = max(
            benchmark["same_symbol"],
            key=lambda s: benchmark["same_symbol"][s]["net_profit_fraction"],
        )
        benchmark["ex_post_best_symbol_diagnostic"] = {
            "symbol": winner,
            "performance": benchmark["same_symbol"][winner],
            "promotion_eligible": False,
            "no_model_selection_use": True,
        }
    for proxy in ["SPY", "BIL", "XLF", "XLI"]:
        key = "benchmark_" + proxy
        if key in packet.files:
            r = packet[key][eval_index + 1].reshape(-1, 1)
            benchmark[proxy] = performance_summary(
                fractional_account(np.ones_like(r), r, 0.0005, 0)
            )
        else:
            benchmark["not_available"][proxy] = "actual matched economic return input not accepted"
    write("run/benchmark-family.json", benchmark)
    write("run/paired-inference.json", paired_summary(primary["S2"], primary["S1"], primary["S0"]))
    np.savez_compressed(OUT / "run/targets-and-returns.npz", **targets, asset_returns=daily_returns)
    write(
        "run/execution-receipt.json",
        {
            "complete_core_comparison": True,
            "complete_registered_package": True,
            "remaining": [
                "independent final scientific acceptance; optional host layer N/A if unconnected"
            ],
            "host_incremental_return": None,
            "host_NA_reason": "no bound actual host continuous return series",
            "wall_seconds": time.monotonic() - started,
            "paper_ready_pass": False,
        },
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["inspect", "run"])
    args = parser.parse_args()
    if args.command == "inspect":
        print(
            json.dumps(
                {
                    "task": "DLSA-REAL-MARKET-METHOD-20261014",
                    "blocked": blockers(),
                    "actual_training_started": False,
                    "actual_economic_started": False,
                }
            )
        )
    else:
        run()


if __name__ == "__main__":
    main()
