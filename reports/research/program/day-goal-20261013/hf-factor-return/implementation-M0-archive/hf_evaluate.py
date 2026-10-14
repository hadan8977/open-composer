"""Complete common-target inference and funded-account evaluation after native go."""

import json
import math
import os
import resource
from datetime import UTC, datetime
from pathlib import Path
from statistics import NormalDist

import numpy as np
import pandas as pd
from hf_accounts import run_funded
from hf_diagnostics import run_fractional
from hf_features import FEATURE, P, bind, save
from hf_run_models import IT, E, economic_cpu_used

OUT = E / "results"


def hac_ratio(day_sum, day_count, lag=5):
    s, n = np.asarray(day_sum, float), np.asarray(day_count, float)
    estimate = s.sum() / n.sum()
    residual = s - estimate * n
    t = len(s)
    longvar = float(residual @ residual / t)
    for k in range(1, min(lag, t - 1) + 1):
        longvar += 2 * (1 - k / (lag + 1)) * float(residual[k:] @ residual[:-k] / t)
    se = math.sqrt(max(longvar, 0) * t) / n.sum()
    z = estimate / se if se > 0 else None
    return dict(
        loss_control_minus_treatment=estimate,
        HAC_lag=lag,
        SE=se,
        z=z,
        p_two_sided=math.erfc(abs(z) / math.sqrt(2)) if z is not None else None,
        MDE80_two_sided_normal=(1.959963984540054 + 0.8416212335729143) * se,
        days=t,
        windows=int(n.sum()),
    )


def block_draws(n, draws=2000, block=20):
    rng = np.random.default_rng(20261013)
    starts = rng.integers(0, n, size=(draws, math.ceil(n / block)))
    return ((starts[:, :, None] + np.arange(block)) % n).reshape(draws, -1)[:, :n]


def paired_inference(predictions, all_target, cts_target, rows, ids, contrasts):
    ix = {name: i for i, name in enumerate(ids)}
    used = sorted({ix[r[k]] for r in contrasts for k in ["treatment_id", "control_id"]})
    base = np.isfinite(predictions[:, used]).all(1)
    results = {}
    for label, y in [("All_primary", all_target), ("Cts_descriptive", cts_target)]:
        keep = base & np.isfinite(y)
        dates = np.array([r["date"] for r in rows])[keep]
        unique, day_index = np.unique(dates, return_inverse=True)
        counts = np.bincount(day_index)
        sums = np.empty((len(unique), len(contrasts)))
        summaries = []
        for j, r in enumerate(contrasts):
            diff = np.square(predictions[keep, ix[r["control_id"]]] - y[keep]) - np.square(
                predictions[keep, ix[r["treatment_id"]]] - y[keep]
            )
            sums[:, j] = np.bincount(day_index, weights=diff, minlength=len(unique))
            summaries.append(dict(contrast=r, **hac_ratio(sums[:, j], counts)))
        draw = block_draws(len(unique))
        estimates = sums.sum(0) / counts.sum()
        boots = np.empty((len(draw), len(contrasts)))
        for start in range(0, len(draw), 100):
            selected = draw[start : start + 100]
            boots[start : start + len(selected)] = (
                sums[selected].sum(1) / counts[selected].sum(1)[:, None]
            )
        se = np.array([r["SE"] for r in summaries])
        valid = se > 0
        centered = np.zeros_like(boots)
        centered[:, valid] = (boots[:, valid] - estimates[valid]) / se[valid]
        maxima = np.abs(centered).max(1)
        for j, r in enumerate(summaries):
            r["block20_bootstrap_95"] = [float(v) for v in np.quantile(boots[:, j], [0.025, 0.975])]
            r["joint_two_sided_maxT_p"] = (
                float((1 + (maxima >= abs(r["z"])).sum()) / (len(draw) + 1))
                if r["z"] is not None
                else None
            )
        results[label] = dict(
            common_windows=int(keep.sum()),
            common_days=len(unique),
            first=unique[0],
            last=unique[-1],
            paired=summaries,
            bootstrap_draws=2000,
            block_packetdays=20,
            seed=20261013,
            primary_family=label == "All_primary",
            same_six_family_intersection=True,
        )
        np.savez(
            OUT / f"paired-{label}.npz",
            dates=unique,
            day_sums=sums,
            counts=counts,
            bootstrap_estimates=boots,
        )
    return results


def statistical_metrics(predictions, y, ids, rows):
    years = np.array([int(r["date"][:4]) for r in rows])
    output = {}
    for j, name in enumerate(ids):
        output[name] = {}
        for label, target in y.items():
            byyear = {}
            for year in [None] + list(range(2004, 2021)):
                keep = np.isfinite(predictions[:, j]) & np.isfinite(target)
                if year is not None:
                    keep &= years == year
                truth, pred = target[keep], predictions[keep, j]
                denom = float(truth @ truth)
                byyear["full" if year is None else str(year)] = dict(
                    n=len(truth),
                    uncentered_R2=1 - float(np.square(truth - pred).sum()) / denom
                    if denom > 0
                    else None,
                    RMSE=float(np.sqrt(np.square(truth - pred).mean())) if len(truth) else None,
                )
            output[name][label] = byyear
    return output


def continuous_metrics(nav, dates, bil=None, market=None):
    nav = np.asarray(nav, dtype=float)
    if len(nav) < 2 or not np.isfinite(nav).all() or np.any(nav <= 0):
        return dict(
            continuous_NAV_ready=False,
            terminal_NAV=None,
            CAGR=None,
            Sharpe_netstd=None,
            primary_physical_Sharpe_ex_BIL=None,
            reason="internal_unknown_or_invalid_NAV; no rows dropped",
        )
    returns = nav[1:] / nav[:-1] - 1
    vol = float(np.std(returns, ddof=1))
    elapsed = (pd.Timestamp(dates[-1]) - pd.Timestamp(dates[0])).days / 365.25
    ratio = nav / np.maximum.accumulate(nav) - 1
    underwater = ratio < 0
    trough = int(np.argmin(ratio))
    peak = int(np.argmax(nav[: trough + 1]))
    recovery = np.flatnonzero(nav[trough:] >= nav[peak])
    recovered_at = int(trough + recovery[0]) if len(recovery) else None
    longest = run = 0
    for flag in underwater:
        run = run + 1 if flag else 0
        longest = max(longest, run)
    excess_sr = None
    if bil is not None:
        bil = np.asarray(bil, float)
        if bil.shape == nav.shape and np.isfinite(bil).all() and (bil > 0).all():
            ex = returns - (bil[1:] / bil[:-1] - 1)
            exvol = float(np.std(ex, ddof=1))
            excess_sr = float(np.mean(ex) / exvol * np.sqrt(252)) if exvol > 0 else None
    beta = None
    if market is not None:
        market = np.asarray(market, float)
        if market.shape == returns.shape and np.isfinite(market).all() and np.var(market) > 0:
            beta = float(np.cov(returns, market, ddof=1)[0, 1] / np.var(market, ddof=1))
    tails = {}
    for h in [5, 21, 63]:
        if len(nav) > h:
            rr = nav[h:] / nav[:-h] - 1
            tails[str(h)] = dict(worst=float(rr.min()), q05=float(np.quantile(rr, 0.05)))
    return dict(
        continuous_NAV_ready=True,
        terminal_NAV=float(nav[-1]),
        dollar_profit=float(nav[-1] - nav[0]),
        CAGR=float((nav[-1] / nav[0]) ** (1 / elapsed) - 1) if elapsed > 0 else None,
        Sharpe_netstd=float(returns.mean() / vol * np.sqrt(252)) if vol > 0 else None,
        primary_physical_Sharpe_ex_BIL=excess_sr,
        SPY_beta=beta,
        max_drawdown=float(ratio.min()),
        longest_underwater_sessions=longest,
        max_drawdown_trough_date=dates[trough],
        max_drawdown_episode_peak_date=dates[peak],
        recovery_sessions_from_trough=recovered_at - trough if recovered_at is not None else None,
        recovery_sessions_from_peak=recovered_at - peak if recovered_at is not None else None,
        max_drawdown_unrecovered_at_end=recovered_at is None,
        underwater_fraction=float(underwater.mean()),
        tail_returns=tails,
        no_terminal_liquidation=True,
        source_grossvol_Sharpe=False,
    )


def descriptive_dsr(nav, effective_trials):
    nav = np.asarray(nav, float)
    if len(nav) < 3 or not np.isfinite(nav).all() or np.any(nav <= 0):
        return dict(probability=None, reason="continuous NAV unavailable")
    r = nav[1:] / nav[:-1] - 1
    std = float(np.std(r, ddof=1))
    if std == 0:
        return dict(probability=None, reason="zero variance")
    sr = float(r.mean() / std)
    z = (r - r.mean()) / std
    skew = float(np.mean(z**3))
    kurt = float(np.mean(z**4))
    n = max(int(effective_trials), 2)
    normal = NormalDist()
    expected = (
        0.5772156649015329 * normal.inv_cdf(1 - 1 / n)
        + (1 - 0.5772156649015329) * normal.inv_cdf(1 - 1 / (n * math.e))
    ) / math.sqrt(len(r) - 1)
    denominator = math.sqrt(max(1 - skew * sr + (kurt - 1) / 4 * sr**2, np.finfo(float).eps))
    return dict(
        probability=float(normal.cdf((sr - expected) * math.sqrt(len(r) - 1) / denominator)),
        effective_trials=n,
        expected_null_max_daily_Sharpe=expected,
        assumption="IID normal null-Sharpe dispersion1/sqrt(T-1); skew/kurtosis correction",
        dependence_adjusted=False,
        descriptive_only=True,
        primary_physical_ex_BIL_gate_replaced=False,
        promotion_evidence=False,
    )


def economic_data():
    bridge = P / "market-input/cache-bridge"
    days = json.loads((P / "funded-SPY-clock-proposed.json").read_text())["rows"]
    expected = {r["date"]: r for r in days}
    bars = {}
    for year in range(2016, 2021):
        data = pd.read_parquet(bridge / f"SPY-raw15-aggregated-{year}.parquet")
        for r in data.to_dict("records"):
            day = str(r["date"].date())
            assert day in expected
            bars.setdefault(day, {})[(r["window_minute"] - 570) // 15] = r
    daily_path = P.parent / "primary-return-breadth/inputs/bars_raw-01.json"
    raw = json.loads(daily_path.read_text())["bars"]
    daily = {s: {r["t"][:10]: r for r in raw[s]} for s in ["SPY", "BIL"]}
    actions = json.loads((bridge / "SPY-BIL-bound-actions.json").read_text())["actions"]
    cash = json.loads((P.parent / "primary-return-breadth/cash-calendar.json").read_text())[
        "eligible_dates"
    ]
    return days, bars, daily, actions, cash


def accounts(predictions, ids, rows):
    days, bars, daily, actions, cash = economic_data()
    marks = {s: {d: r["c"] for d, r in daily[s].items()} for s in daily}
    dates = [r["date"] for r in days]
    allowed = set(dates)
    score_maps = {
        name: {
            (r["date"], r["minute"]): float(predictions[i, j])
            for i, r in enumerate(rows)
            if r["date"] in allowed and np.isfinite(predictions[i, j])
        }
        for j, name in enumerate(ids)
    }
    stock = np.array([marks["SPY"][d] for d in dates])
    div = np.array(
        [
            sum(
                a["amount"]
                for a in actions
                if a["symbol"] == "SPY" and a["ex_date"] == d and a["type"] == "cash_dividends"
            )
            for d in dates
        ]
    )
    market = (stock[1:] + div[1:]) / stock[:-1] - 1
    metric, paths = {}, {}
    for bps in [0, 1, 5, 20, 40]:
        cost = bps / 10000
        bil_bars = {
            d: {
                0: dict(
                    open=daily["BIL"][d]["o"], close=daily["BIL"][d]["c"], first_price_age_minutes=0
                )
            }
            for d in dates
        }
        # Dailyopening reference is the frozen APP benchmark convention, not a quote/fill claim.
        bil = run_funded(
            days, bil_bars, marks["BIL"], {}, actions, cash, cost, symbol="BIL", mode="buy_hold"
        )
        bil_nav = [r["nav"] for r in bil["daily"]]
        for control, kwargs in [
            ("SPY_BH", dict(mode="buy_hold")),
            ("SPY_OVERNIGHT_ONLY", dict(mode="overnight_only")),
        ]:
            account = run_funded(days, bars, marks["SPY"], {}, actions, cash, cost, **kwargs)
            key = f"{control}__{bps}"
            save(OUT / f"{key}-ledger.json", account)
            paths[key] = [r["nav"] for r in account["daily"]]
        save(OUT / f"BIL_BH__{bps}-ledger.json", bil)
        paths[f"BIL_BH__{bps}"] = bil_nav
        paths[f"CASH__{bps}"] = [20000.0] * len(days)
        for name in ids:
            scores = score_maps[name]
            account = run_funded(days, bars, marks["SPY"], scores, actions, cash, cost)
            key = f"{name}__{bps}"
            save(OUT / f"{key}-ledger.json", account)
            nav = [r["nav"] for r in account["daily"]]
            paths[key] = nav
            metric[key] = dict(
                full=continuous_metrics(nav, dates, bil_nav, market),
                fees=sum(r["fee"] for r in account["orders"]),
                order_attempts=len(account["orders"]),
                filled=sum(r["status"] == "reference_filled" for r in account["orders"]),
                gross_notional_turnover_initial=(
                    sum(
                        r["quantity"] * r["actual_reference"]
                        for r in account["orders"]
                        if r["status"] == "reference_filled"
                    )
                    / 20000
                ),
                unsettled_cash_wait_sessions=sum(r["unsettled"] > 0 for r in account["daily"]),
                mean_available_cash=float(np.mean([r["cash"] for r in account["daily"]])),
                mean_unsettled_sale_cash=float(np.mean([r["unsettled"] for r in account["daily"]])),
                nofills={
                    s: sum(r["status"] == s for r in account["orders"])
                    for s in sorted({r["status"] for r in account["orders"]})
                },
                mean_daily_exposure=float(
                    np.mean(
                        [
                            (r["q"] * r["raw_daily_closing_mark"]) / r["nav"]
                            for r in account["daily"]
                            if r["nav"] is not None and r["nav"] > 0
                        ]
                    )
                ),
                temporal_views=temporal_views(nav, dates, bil_nav, market),
            )
        print("funded_fee_view_complete", bps, flush=True)
    for key, nav in paths.items():
        if key not in metric:
            bps = key.rsplit("__", 1)[1]
            metric[key] = dict(
                full=continuous_metrics(nav, dates, paths[f"BIL_BH__{bps}"], market),
                temporal_views=temporal_views(nav, dates, paths[f"BIL_BH__{bps}"], market),
            )
    pd.DataFrame(paths, index=pd.to_datetime(dates)).to_parquet(
        OUT / "continuous-funded-NAV.parquet"
    )
    return metric


def expected_dates(days):
    return {r["date"] for r in days}


def host_contribution(predictions, ids, rows):
    days, bars, daily, actions, cash = economic_data()
    host_path = Path("data/research/account_review_2026_10/returns.parquet")
    host = pd.read_parquet(host_path)
    dates = [r["date"] for r in days]
    index = pd.to_datetime(dates)
    columns = ["S1__net10", "S2__net10", "S3__net10", "C2__net10", "F1__net10"]
    common = index.intersection(host.index)
    if len(common) < 2:
        return dict(
            ready=False, reason="no common actual closing clock", host_input=bind(host_path)
        )
    first, last = common[0], common[-1]
    subdays = [d for d in days if first <= pd.Timestamp(d["date"]) <= last]
    subdates = [r["date"] for r in subdays]
    subindex = pd.to_datetime(subdates)
    if (
        not subindex.isin(host.index).all()
        or not np.isfinite(host.loc[subindex, columns].to_numpy()[1:]).all()
    ):
        return dict(
            ready=False,
            reason="internal missing host row/value; no fill or intersection deletion",
            host_input=bind(host_path),
        )
    h = host.loc[subindex, columns].to_numpy()
    growth = np.vstack((np.ones(5), np.cumprod(1 + h[1:], axis=0)))
    host_nav = {"HOST_F1_net10": 16000 * growth[:, 4], "HOST_EW_net10": 3200 * growth.sum(axis=1)}
    allowed = set(subdates)
    marks = {s: {d: r["c"] for d, r in daily[s].items()} for s in daily}
    stock = np.array([marks["SPY"][d] for d in subdates])
    dividend = np.array(
        [
            sum(
                a["amount"]
                for a in actions
                if a["symbol"] == "SPY" and a["ex_date"] == d and a["type"] == "cash_dividends"
            )
            for d in subdates
        ]
    )
    market = (stock[1:] + dividend[1:]) / stock[:-1] - 1
    scoremaps = {
        name: {
            (r["date"], r["minute"]): float(predictions[i, j])
            for i, r in enumerate(rows)
            if r["date"] in allowed and np.isfinite(predictions[i, j])
        }
        for j, name in enumerate(ids)
    }
    output = {}
    matrices = {}
    for bps in [20, 40]:
        cost = bps / 10000
        sleeve = {"CASH": np.full(len(subdays), 4000.0)}
        bil_bars = {
            d: {
                0: dict(
                    open=daily["BIL"][d]["o"], close=daily["BIL"][d]["c"], first_price_age_minutes=0
                )
            }
            for d in subdates
        }
        for symbol, source in [("SPY", bars), ("BIL", bil_bars)]:
            book = run_funded(
                subdays, source, marks[symbol], {}, actions, cash, cost, 4000, symbol, "buy_hold"
            )
            sleeve[symbol] = np.array([r["nav"] for r in book["daily"]], float)
            save(OUT / f"host4k-{symbol}-BH__{bps}-ledger.json", book)
        for name in ids:
            book = run_funded(
                subdays, bars, marks["SPY"], scoremaps[name], actions, cash, cost, 4000
            )
            sleeve[name] = np.array([r["nav"] for r in book["daily"]], float)
            save(OUT / f"host4k-{name}__{bps}-ledger.json", book)
        for host_name, base in host_nav.items():
            for name, path in sleeve.items():
                combined = base + path
                key = f"{host_name}__{name}__{bps}"
                matrices[key] = combined
                output[key] = dict(
                    metrics=continuous_metrics(combined, subdates, base + sleeve["BIL"], market),
                    controls={},
                    initialization_row_deleted_only_for_this_pair=True,
                )
                if name in ids:
                    for control in ["CASH", "BIL", "SPY", "PLS_IDX_MKT"]:
                        reference = base + sleeve[control]
                        if np.isfinite(combined).all() and np.isfinite(reference).all():
                            r = combined[1:] / combined[:-1] - 1
                            rc = reference[1:] / reference[:-1] - 1
                            diff = r - rc
                            output[key]["controls"][control] = dict(
                                terminal_dollar_difference=float(combined[-1] - reference[-1]),
                                annual_mean_return_difference=float(diff.mean() * 252),
                                daily_return_difference_HAC=hac_ratio(diff, np.ones(len(diff))),
                            )
                        else:
                            output[key]["controls"][control] = dict(
                                terminal_dollar_difference=None,
                                annual_mean_return_difference=None,
                                reason="affected physical book/internal unknown, no row deletion",
                            )
    pd.DataFrame(matrices, index=subindex).to_parquet(OUT / "continuous-host-NAV.parquet")
    return dict(
        ready=True,
        host_input=bind(host_path),
        first_common_close=subdates[0],
        last_common_close=subdates[-1],
        rows=len(subdays),
        results=output,
        host_initial=16000,
        sleeve_initial=4000,
        EW_initial_component_weights_then_drift=True,
        daily80_20_rebalance=False,
        physical20k_account_scaled_to4k=False,
        inherited_host_net10_not_relabelled20bps=True,
        actual_integrated_broker_funding_verified=False,
    )


def fractional_diagnostics(predictions, ids, rows):
    days, bars, daily, actions, cash = economic_data()
    dates = [r["date"] for r in days]
    allowed = set(dates)
    marks = {d: r["c"] for d, r in daily["SPY"].items()}
    results = {}
    for j, name in enumerate(ids):
        scores = {
            (r["date"], r["minute"]): float(predictions[i, j])
            for i, r in enumerate(rows)
            if r["date"] in allowed and np.isfinite(predictions[i, j])
        }
        for bps in [0, 1, 5, 20, 40]:
            for sign in [False, True]:
                for night in [False, True]:
                    for latency in [0, 1]:
                        key = f"{name}__{bps}__sign{int(sign)}__night{int(night)}__lag{latency}"
                        book = run_fractional(
                            days,
                            bars,
                            marks,
                            scores,
                            actions,
                            cash,
                            bps / 10000,
                            sign,
                            night,
                            latency,
                        )
                        metric = continuous_metrics(book["nav"], dates)
                        net = book["nav"][1:] / book["nav"][:-1] - 1
                        source_denominator = np.sqrt(np.mean(book["gross_daily"][1:] ** 2) * 252)
                        metric.update(
                            funded=False,
                            physical_20k_profit_claim=False,
                            reference_daily_gross_second_moment_ratio=(
                                float(np.mean(net) * 252 / source_denominator)
                                if source_denominator > 0
                                else None
                            ),
                            original_source_quoted_cost_and_grossvol_replication=False,
                            fees_fraction_initial=float(book["fees"].sum()),
                            borrow_fraction_initial=float(book["borrow"].sum()),
                            order_attempts=len(book["events"]),
                            no_fill_attempts=int((book["events"]["status"] == 0).sum()),
                            borrowing_APP=book["borrowing_APP"],
                        )
                        results[key] = metric
                        np.savez(
                            OUT / f"diagnostic-{key}.npz",
                            nav=book["nav"],
                            gross_daily=book["gross_daily"],
                            fees=book["fees"],
                            borrow=book["borrow"],
                            events=book["events"],
                            exposure=book["exposure"],
                        )
        print("fractional_diagnostic_candidate_complete", name, flush=True)
    assert len(results) == 800
    return results


def temporal_views(nav, dates, bil, market):
    nav = np.asarray(nav, float)
    bil = np.asarray(bil, float)
    year = np.array([int(d[:4]) for d in dates])
    views = []
    for y in range(2016, 2021):
        ix = np.flatnonzero(year == y)
        if len(ix):
            views.append((str(y), max(0, ix[0] - 1), ix[-1] + 1))
    for name, mask in [("2016_2018", year <= 2018), ("2019_2020", year >= 2019)]:
        ix = np.flatnonzero(mask)
        views.append((name, max(0, ix[0] - 1), ix[-1] + 1))
    for n in [252, 126, 63]:
        views.append(("last" + str(n), max(0, len(nav) - n - 1), len(nav)))
    return {
        name: continuous_metrics(nav[a:b], dates[a:b], bil[a:b], market[a : b - 1])
        for name, a, b in views
    }


def main():
    from open_composer.research.iteration_dossier import validate_iteration_dossier

    hold = json.loads(Path("reports/research/control/owner-compute-hold.json").read_text())
    assert hold.get("research_paused") is False
    gate = validate_iteration_dossier(IT, Path.cwd(), stage="pre-backtest")
    assert gate.status == "ok"
    projection = json.loads((E / "full-resource-projection.json").read_text())
    assert projection["full_package_fits_existing_cap"]
    assert (
        json.loads((P / "independent-implementation-review.json").read_text())["verdict"]
        == "approve_implementation"
    )
    os.sched_setaffinity(0, {min(os.sched_getaffinity(0))})
    remaining = 7006.69 - economic_cpu_used() - 300 - 106.69
    limit = min(700, math.floor(remaining))
    assert limit > 0, "actual remaining economic reservation blocks evaluation"
    resource.setrlimit(resource.RLIMIT_CPU, (limit, limit))
    OUT.mkdir(exist_ok=True)
    rows = json.loads((FEATURE / "packet-row-clock.json").read_text())
    labels = np.load(FEATURE / "labels.npy", mmap_mode="r")[: len(rows)]
    linear_manifest = json.loads((E / "linear-model-manifest.json").read_text())
    nonlinear_manifest = json.loads((E / "HGB-model-manifest.json").read_text())
    ids = linear_manifest["candidate_ids"] + nonlinear_manifest["candidate_ids"]
    prediction = np.column_stack(
        (np.load(E / "linear-predictions.npy"), np.load(E / "HGB-predictions.npy"))
    )
    plan = json.loads((P / "scientific-plan.json").read_text())
    assert set(ids) == {r["candidate_id"] for r in plan["candidates"]} and len(ids) == 20
    statistics = statistical_metrics(
        prediction, {"All": labels[:, 0], "Cts": labels[:, 1]}, ids, rows
    )
    paired = paired_inference(
        prediction,
        labels[:, 0],
        labels[:, 1],
        rows,
        ids,
        plan["inference_and_contribution"]["primary_contrasts"],
    )
    funded = accounts(prediction, ids, rows)
    diagnostics = fractional_diagnostics(prediction, ids, rows)
    host = host_contribution(prediction, ids, rows)
    trials = [
        json.loads(line) for line in (E / "model-trial-ledger.jsonl").read_text().splitlines()
    ]
    logical_ids = {r["logical_trial_id"] for r in trials}
    effective = len(logical_ids) + 800 + 100 + 40
    matrix = pd.read_parquet(OUT / "continuous-funded-NAV.parquet")
    dsr = {name: descriptive_dsr(matrix[name], effective) for name in matrix.columns}
    save(OUT / "statistical-results.json", statistics)
    save(OUT / "paired-results.json", paired)
    save(OUT / "funded-results.json", funded)
    save(OUT / "fractional-diagnostic-results.json", diagnostics)
    save(OUT / "host-results.json", host)
    save(
        OUT / "descriptive-DSR.json",
        dict(
            effective_trials=effective,
            logical_model_trials=len(logical_ids),
            fractional_views=800,
            funded20k_views=100,
            host4k_views=40,
            results=dsr,
            PBO=None,
            SPA=None,
            reason="no selectable cohort or untouched OOS; DSR descriptive assumption only",
        ),
    )
    used = resource.getrusage(resource.RUSAGE_SELF)
    save(
        E / "evaluation-resource.json",
        dict(
            CPU_process=used.ru_utime + used.ru_stime,
            max_RSS_KiB=used.ru_maxrss,
            completed=True,
            research_pass=False,
            paper_ready_pass=False,
            as_of_utc=datetime.now(UTC).isoformat(),
        ),
    )


if __name__ == "__main__":
    main()
