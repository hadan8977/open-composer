"""Fixed nonpromotable live-fund application. No signal fitting or order interface."""

from __future__ import annotations

import json
import math
import resource
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import norm

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT))
from open_composer.research.campaign_statistics import (  # noqa: E402
    deflated_sharpe_probability,
    studentized_spa_p_value,
)
from open_composer.research.features.price_hygiene import sanitize_price_matrices  # noqa: E402
from open_composer.research.iteration_dossier import validate_iteration_dossier  # noqa: E402

TASK = Path(__file__).resolve().parent
ITER_ID = "t20261013_pressure_deletions_application"
ITER = ROOT / "reports/research/iterations" / ITER_ID
RESULT = TASK / "results"
SYMBOLS = ["NIXT", "IWN", "IWM", "VBR", "IWV", "SPY", "QQQ", "RSP", "BIL"]
HOST_COLUMNS = ["F1__net10", "S1__net10", "S2__net10", "S3__net10", "C2__net10"]


def save(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def clean(value):
    if isinstance(value, dict):
        return {str(k): clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, np.ndarray)):
        return [clean(v) for v in value]
    if isinstance(value, np.generic):
        return clean(value.item())
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def returns_from_wealth(wealth: pd.Series) -> pd.Series:
    """First row includes entry cost versus initial cash NAV of one."""
    result = wealth.pct_change(fill_method=None)
    result.iloc[0] = wealth.iloc[0] - 1
    return result


def sharpe(values: np.ndarray) -> float:
    sd = np.std(values, ddof=1)
    return float(np.mean(values) / sd * np.sqrt(252)) if sd > 0 else float("nan")


def metrics(series: pd.Series, cash: pd.Series) -> dict:
    aligned = pd.concat([series.rename("s"), cash.rename("cash")], axis=1).dropna()
    r = aligned.s.to_numpy()
    wealth = np.concatenate([[1.0], np.cumprod(1 + r)])
    high = np.maximum.accumulate(wealth)
    dd = wealth / high - 1
    underwater = 0
    longest = 0
    for below in dd[1:] < -1e-10:
        underwater = underwater + 1 if below else 0
        longest = max(longest, underwater)
    rolling21 = pd.Series(r).add(1).rolling(21).apply(np.prod, raw=True) - 1
    rolling42 = pd.Series(r).add(1).rolling(42).apply(np.prod, raw=True) - 1
    rolling252 = pd.Series(r).add(1).rolling(252).apply(np.prod, raw=True) - 1
    return clean(
        {
            "start": str(aligned.index[0].date()),
            "end": str(aligned.index[-1].date()),
            "sessions": len(r),
            "total_return": wealth[-1] - 1,
            "cagr": wealth[-1] ** (252 / len(r)) - 1,
            "mean_ann": np.mean(r) * 252,
            "vol_ann": np.std(r, ddof=1) * np.sqrt(252),
            "sharpe_ex_bil": sharpe(r - aligned.cash.to_numpy()),
            "max_drawdown": np.min(dd),
            "longest_underwater_sessions": longest,
            "current_underwater_sessions": underwater,
            "worst_21session_return": rolling21.min(),
            "worst_42session_return": rolling42.min(),
            "worst_252session_return": rolling252.min(),
            "best_252session_return": rolling252.max(),
            "negative_21session_fraction": float((rolling21.dropna() < 0).mean()),
            "negative_42session_fraction": float((rolling42.dropna() < 0).mean()),
        }
    )


def hac_ols(y: np.ndarray, x: np.ndarray | None = None, lag: int = 21) -> dict:
    y = np.asarray(y)
    n = len(y)
    design = np.ones((n, 1)) if x is None else np.column_stack([np.ones(n), x])
    beta = np.linalg.lstsq(design, y, rcond=None)[0]
    residual = y - design @ beta
    scores = design * residual[:, None]
    meat = scores.T @ scores
    for k in range(1, min(lag, n - 1) + 1):
        gamma = scores[k:].T @ scores[:-k]
        meat += (1 - k / (lag + 1)) * (gamma + gamma.T)
    inverse = np.linalg.pinv(design.T @ design)
    cov = inverse @ meat @ inverse * n / (n - design.shape[1])
    se = np.sqrt(np.maximum(0, np.diag(cov)))
    tstat = np.divide(beta, se, out=np.full_like(beta, np.nan), where=se > 0)
    return clean(
        {
            "coefficients": beta,
            "hac21_standard_errors": se,
            "t_statistics": tstat,
            "intercept_ann": beta[0] * 252,
            "intercept_ann_se": se[0] * 252,
            "intercept_p_two_sided": 2 * norm.sf(abs(tstat[0])),
            "mde80_ann_two_sided": (norm.ppf(0.975) + norm.ppf(0.8)) * se[0] * 252,
            "r_squared": 1 - np.var(residual) / np.var(y),
            "sessions": n,
        }
    )


def stationary_indexes(n: int, samples: int = 1000, seed: int = 4201) -> np.ndarray:
    rng = np.random.default_rng(seed)
    indexes = np.empty((samples, n), dtype=int)
    indexes[:, 0] = rng.integers(0, n, samples)
    for t in range(1, n):
        indexes[:, t] = np.where(
            rng.random(samples) < 1 / 21,
            rng.integers(0, n, samples),
            (indexes[:, t - 1] + 1) % n,
        )
    return indexes


def paired_report(candidate: pd.Series, baseline: pd.Series, cash: pd.Series) -> dict:
    panel = pd.concat(
        [candidate.rename("candidate"), baseline.rename("baseline"), cash.rename("cash")], axis=1
    ).dropna()
    # Exclude each pair's first common initialization row. Host and standalone
    # comparisons can start on different dates; this is not one global entry row.
    initialized_at = str(panel.index[0].date())
    panel = panel.iloc[1:]
    a, b, c = [panel[k].to_numpy() for k in ["candidate", "baseline", "cash"]]
    idx = stationary_indexes(len(panel))
    a_boot, b_boot, c_boot = a[idx], b[idx], c[idx]
    delta_boot = (
        np.mean(a_boot - c_boot, axis=1) / np.std(a_boot - c_boot, axis=1, ddof=1)
        - np.mean(b_boot - c_boot, axis=1) / np.std(b_boot - c_boot, axis=1, ddof=1)
    ) * np.sqrt(252)
    return clean(
        {
            "sessions": len(panel),
            "first_common_initialization_row_excluded": initialized_at,
            "inference_first_session": str(panel.index[0].date()),
            "inference_last_session": str(panel.index[-1].date()),
            "correlation": np.corrcoef(a, b)[0, 1],
            "annual_mean_difference": np.mean(a - b) * 252,
            "hac": hac_ols(a - b),
            "delta_sharpe_ex_bil": sharpe(a - c) - sharpe(b - c),
            "delta_sharpe_95ci_stationary21": np.quantile(delta_boot, [0.025, 0.975]),
            "mean_difference_ann_95ci": np.quantile(
                np.mean(a_boot - b_boot, axis=1) * 252, [0.025, 0.975]
            ),
            "simultaneous_down_days_fraction": np.mean((a < 0) & (b < 0)),
        }
    )


def build_streams(close: pd.DataFrame, hosts: pd.DataFrame, bps: int):
    cost = bps / 10000
    wealth = (close / close.iloc[0]) * (1 - cost)
    streams = {s: returns_from_wealth(wealth[s]) for s in SYMBOLS}
    streams["EW8"] = returns_from_wealth(wealth.drop(columns="NIXT").mean(axis=1))
    streams["NIXT_full_capital"] = streams["NIXT"]
    streams["NIXT50_BIL50"] = returns_from_wealth(0.5 * wealth.NIXT + 0.5 * wealth.BIL)
    for source in ["NIXT", "IWN"]:
        streams[f"SPY80_{source}20"] = returns_from_wealth(0.8 * wealth.SPY + 0.2 * wealth[source])
    host_panel = hosts.loc[close.index.intersection(hosts.index), HOST_COLUMNS].dropna()
    assert len(host_panel) >= 252
    host_panel.iloc[0] = 0.0  # Investor initial-close clock, not prior session exposure.
    host_wealth = (1 + host_panel).cumprod()
    for column in HOST_COLUMNS:
        streams[column] = returns_from_wealth(host_wealth[column])
    streams["HOST_EW"] = returns_from_wealth(host_wealth.mean(axis=1))
    for host_name, h in [("F1", host_wealth["F1__net10"]), ("HOST_EW", host_wealth.mean(axis=1))]:
        for source in ["NIXT", "IWN"]:
            w = wealth[source].reindex(host_panel.index)
            # Same source entry-close baseline on the host's actual common start.
            w = w / w.iloc[0] * (1 - cost)
            prefix = "HOST_EW80" if host_name == "HOST_EW" else "F1_80"
            streams[f"{prefix}_{source}20"] = returns_from_wealth(0.8 * h + 0.2 * w)
    return streams


def quote_audit() -> dict:
    result = {}
    for date in ["2024-09-10", "2025-04-03", "2025-09-10", "2026-09-10"]:
        path = TASK / "inputs" / ("quotes_" + date + ".json")
        if not path.exists():
            result[date] = {"valid_quote": False, "reason": "missing_response"}
            continue
        quotes = json.loads(path.read_text()).get("quotes") or []
        arrival = pd.Timestamp(date + " 09:45:00", tz="America/New_York").tz_convert("UTC")
        valid = [
            q
            for q in quotes
            if pd.Timestamp(q["t"]) <= arrival and q["bp"] > 0 and q["ap"] >= q["bp"]
        ]
        if not valid:
            result[date] = {
                "valid_quote": False,
                "quote_count": len(quotes),
                "reason": "no_valid_prearrival_quote",
            }
            continue
        q = max(valid, key=lambda row: row["t"])
        age = (arrival - pd.Timestamp(q["t"])).total_seconds()
        mid = (q["bp"] + q["ap"]) / 2
        trades_path = TASK / "inputs" / ("trades_" + date + ".json")
        trades = (
            json.loads(trades_path.read_text()).get("trades") or [] if trades_path.exists() else []
        )
        result[date] = {
            "valid_quote": True,
            "quote": q,
            "quote_age_seconds": age,
            "mid": mid,
            "full_spread_bps": (q["ap"] - q["bp"]) / mid * 10000,
            "following_minute_print_count": len(trades),
            "following_minute_print_shares": sum(t["s"] for t in trades),
            "limit": (
                "Displayed quote and subsequent prints do not prove fill. "
                "Size units not certified by this study."
            ),
        }
    return result


def cash_account(
    raw_close: pd.Series, quotes: dict, fee_bps: int, distributions: list
) -> tuple[pd.DataFrame | None, dict]:
    initial = quotes.get("2024-09-10", {})
    if not initial.get("valid_quote"):
        return None, {
            "exact_entry": None,
            "reason": "No valid historical arrival quote; no OHLC fill substitute",
        }
    ask = initial["quote"]["ap"]
    fee = fee_bps / 10000
    shares = int(20000 // (ask * (1 + fee)))
    entry_notional = shares * ask
    cash = 20000 - entry_notional * (1 + fee)
    assert cash >= 0
    earned = 0.0
    by_paydate = {}
    for d in distributions:
        by_paydate[d["payable_date"]] = by_paydate.get(d["payable_date"], 0) + d["amount"]
    rows = []
    for day, close in raw_close.loc["2024-09-10":].items():
        date = str(day.date())
        cash_credit = shares * by_paydate.get(date, 0)
        cash += cash_credit
        earned += cash_credit
        # Earned but not yet paid distribution is a receivable asset, not usable cash.
        receivable = shares * sum(
            d["amount"] for d in distributions if d["ex_date"] <= date < d["payable_date"]
        )
        rows.append(
            {
                "date": date,
                "shares": shares,
                "raw_close": close,
                "cash": cash,
                "dividend_cash_credit": cash_credit,
                "dividend_receivable": receivable,
                "equity": shares * close + cash + receivable,
            }
        )
    account = pd.DataFrame(rows).set_index("date")
    return account, {
        "entry_date": "2024-09-10",
        "arrival_time": "09:45 America/New_York",
        "entry_ask": ask,
        "shares": shares,
        "entry_notional": entry_notional,
        "initial_fee_dollars": entry_notional * fee,
        "initial_cash": 20000 - entry_notional * (1 + fee),
        "total_cash_dividends": earned,
        "final_equity": account.equity.iloc[-1],
        "total_return": account.equity.iloc[-1] / 20000 - 1,
        "exact_entry": "quote-anchored modelled account; not an observed fill or paper order",
        "quote_age_seconds": initial["quote_age_seconds"],
        "cash_yield": 0,
        "dividend_reinvestment": False,
        "financing": 0,
        "borrow": 0,
        "terminal_liquidation_included": False,
    }


def main() -> None:
    wall_start = time.monotonic()
    cpu_start = time.process_time()
    gate = validate_iteration_dossier(ITER_ID, ROOT, stage="pre-backtest")
    assert gate.ok, gate.blocked
    RESULT.mkdir(exist_ok=True)
    save(RESULT / "pre-backtest-gate.json", gate.to_dict(ROOT))
    bars = pd.read_parquet(TASK / "inputs/daily-bars.parquet")
    bars["session"] = pd.to_datetime(bars.session)
    adjusted = bars[bars.adjustment == "all"]
    close = adjusted.pivot(index="session", columns="symbol", values="c")[SYMBOLS]
    opening = adjusted.pivot(index="session", columns="symbol", values="o")[SYMBOLS]
    close, _, hygiene = sanitize_price_matrices(close, opening)
    save(RESULT / "price-hygiene.json", hygiene.manifest())
    close = close.loc["2024-09-10":"2026-10-12"].dropna()
    assert len(close) >= 252 and close.index.max() <= pd.Timestamp("2026-10-12")
    hosts = pd.read_parquet(
        ROOT / "data/research/account_review_2026_10/returns.parquet", columns=HOST_COLUMNS
    )
    hosts.index = pd.to_datetime(hosts.index).tz_localize(None).normalize()
    primary = build_streams(close, hosts, 20)
    stress = build_streams(close, hosts, 40)
    pd.DataFrame(primary).to_csv(RESULT / "daily-return-matrix.csv", index_label="date")
    pd.DataFrame(stress).to_csv(RESULT / "daily-return-matrix-stress.csv", index_label="date")
    result = {
        "claim_scope": "conditional_cohort",
        "source_causal_replication": "not_at_depth_missing_original_PIT_data",
        "seen_development_only": True,
        "frozen_oos_read": False,
        "source_replay": {s: metrics(r, primary["BIL"]) for s, r in primary.items()},
        "stress40bps": {s: metrics(r, stress["BIL"]) for s, r in stress.items()},
        "subperiods": {},
        "paired_comparisons": {},
        "risk_attribution": {},
        "cost_convention": (
            "20bps each investor entry side;40bpsstress, holdings drift, "
            "no terminal liquidation;host historical internal net10 preserved"
        ),
    }
    for year, label in [(2024, "launch2024"), (2025, "2025"), (2026, "2026YTD")]:
        result["subperiods"][label] = {
            s: metrics(r[r.index.year == year], primary["BIL"])
            for s, r in primary.items()
            if len(r[r.index.year == year]) > 1
        }
    for benchmark in ["IWN", "IWM", "VBR", "SPY", "QQQ", "EW8"]:
        result["paired_comparisons"]["NIXT_vs_" + benchmark] = paired_report(
            primary["NIXT"], primary[benchmark], primary["BIL"]
        )
        if benchmark in ["IWN", "IWM", "VBR", "SPY"]:
            panel = (
                pd.concat(
                    [
                        primary["NIXT"].rename("n"),
                        primary[benchmark].rename("b"),
                        primary["BIL"].rename("cash"),
                    ],
                    axis=1,
                )
                .dropna()
                .iloc[1:]
            )
            scale = panel.n.std() / panel.b.std()
            difference = (panel.n - panel.cash) - scale * (panel.b - panel.cash)
            result["risk_attribution"]["matched_vol_" + benchmark] = {
                "benchmark_expost_scale": scale,
                "attribution_only_not_implementable_leverage": True,
                "difference": hac_ols(difference.to_numpy()),
            }
    p = (
        pd.DataFrame({s: primary[s] for s in ["NIXT", "SPY", "IWN", "IWM", "BIL"]})
        .dropna()
        .iloc[1:]
    )
    x = np.column_stack([p.SPY - p.BIL, p.IWM - p.SPY, p.IWN - p.IWM])
    result["risk_attribution"]["style_ols"] = hac_ols((p.NIXT - p.BIL).to_numpy(), x)
    for host, n_name, i_name in [
        ("SPY", "SPY80_NIXT20", "SPY80_IWN20"),
        ("F1__net10", "F1_80_NIXT20", "F1_80_IWN20"),
        ("HOST_EW", "HOST_EW80_NIXT20", "HOST_EW80_IWN20"),
    ]:
        result["paired_comparisons"][n_name + "_vs_host"] = paired_report(
            primary[n_name], primary[host], primary["BIL"]
        )
        result["paired_comparisons"][n_name + "_vs_IWN_replacement"] = paired_report(
            primary[n_name], primary[i_name], primary["BIL"]
        )
        aligned = (
            pd.concat(
                [
                    primary[host].rename("host"),
                    primary.NIXT
                    if isinstance(primary, pd.DataFrame)
                    else primary["NIXT"].rename("n"),
                    primary["BIL"].rename("cash"),
                ],
                axis=1,
            )
            .dropna()
            .iloc[1:]
        )
        base = aligned.host.to_numpy()
        n = aligned.n.to_numpy()
        cash = aligned.cash.to_numpy()
        observed = sharpe(0.8 * base + 0.2 * n - cash) - sharpe(base - cash)
        shifts = [
            sharpe(0.8 * base + 0.2 * np.roll(n, shift) - cash) - sharpe(base - cash)
            for shift in range(21, len(n), 21)
        ]
        result.setdefault("alignment_placebo", {})[host] = {
            "clock": (
                "Constant-weight local daily alignment statistic only; "
                "not one of the drifting investment streams"
            ),
            "real_delta_sharpe": observed,
            "shift_delta_sharpes": shifts,
            "real_percentile": np.mean(np.asarray(shifts) <= observed),
            "causal_identification": False,
        }
    candidates = json.loads((TASK / "scientific-plan.json").read_text())["application_definitions"]
    result["dsr5_diagnostic"] = {
        c: deflated_sharpe_probability(
            (
                pd.concat([primary[c], primary["BIL"]], axis=1).dropna().iloc[1:, 0]
                - pd.concat([primary[c], primary["BIL"]], axis=1).dropna().iloc[1:, 1]
            ).to_numpy(),
            trial_count=5,
            hac_lag=21,
        )
        for c in candidates
    }
    spa = np.column_stack(
        [(primary["NIXT"] - primary[s]).iloc[1:].to_numpy() for s in ["IWN", "IWM", "VBR"]]
    )
    result["spa_style_diagnostic"] = studentized_spa_p_value(
        spa, block_length=21, resample_count=1000, seed=4201
    )
    result["pbo"] = None
    result["pbo_reason"] = (
        "No fitted chooser/ranking or selected best definition; no PBO=0 assertion"
    )
    # Holm adjusts five account comparisons; source attributions stay diagnostics.
    compare_keys = [
        "NIXT_vs_IWN",
        "NIXT_vs_SPY",
        "SPY80_NIXT20_vs_IWN_replacement",
        "F1_80_NIXT20_vs_IWN_replacement",
        "HOST_EW80_NIXT20_vs_IWN_replacement",
    ]
    pairs = sorted(
        [(result["paired_comparisons"][k]["hac"]["intercept_p_two_sided"], k) for k in compare_keys]
    )
    previous = 0.0
    result["holm5"] = {}
    for rank, (value, key) in enumerate(pairs):
        previous = min(1.0, max(previous, value * (5 - rank)))
        result["holm5"][key] = previous
    quotes = quote_audit()
    result["quotes"] = quotes
    raw = bars[bars.adjustment == "raw"].pivot(index="session", columns="symbol", values="c")
    issuer = json.loads((TASK / "sources/nixt-issuer-web-extract.json").read_text())
    payment_packet = json.loads((TASK / "sources/dividend-payable-evidence.json").read_text())
    distributions = payment_packet["distributions"]
    assert len(distributions) == len(issuer["distributions"])
    for observed, original in zip(distributions, issuer["distributions"], strict=True):
        assert observed["ex_date"] == original["ex_date"]
        assert observed["amount"] == original["amount"]
        assert observed["payable_date"] >= observed["ex_date"]
    for bps in [20, 40]:
        account, summary = cash_account(raw.NIXT, quotes, bps, distributions)
        result.setdefault("cash_accounts", {})[str(bps)] = summary
        if account is not None:
            account.to_csv(RESULT / f"whole-share-account-{bps}bps.csv")
            nav = account.equity / 20000
            nav.index = pd.to_datetime(nav.index)
            account_returns = returns_from_wealth(nav)
            result["cash_accounts"][str(bps)]["metrics"] = metrics(account_returns, primary["BIL"])
            result["cash_accounts"][str(bps)]["terminal_liquidation_sensitivity_equity"] = (
                account.equity.iloc[-1]
                - account.shares.iloc[-1] * account.raw_close.iloc[-1] * bps / 10000
            )
    # Raw cash distributions independently reconstruct shareholder total return.
    nixt = raw.NIXT.dropna()
    distributions_by_ex = {d["ex_date"]: d["amount"] for d in distributions}
    cash_ex = pd.Series(
        [distributions_by_ex.get(str(day.date()), 0) for day in nixt.index], index=nixt.index
    )
    raw_total_returns = (nixt + cash_ex) / nixt.shift() - 1
    adj_total_returns = (
        adjusted[adjusted.symbol == "NIXT"].set_index("session").c.pct_change(fill_method=None)
    )
    audit = pd.concat(
        [raw_total_returns.rename("raw_cash_ex"), adj_total_returns.rename("provider_adjusted")],
        axis=1,
    ).dropna()
    audit.to_csv(RESULT / "adjustment-audit.csv")
    result["adjustment_audit"] = {
        "max_abs_daily_difference": (audit.raw_cash_ex - audit.provider_adjusted).abs().max(),
        "mean_abs_daily_difference": (audit.raw_cash_ex - audit.provider_adjusted).abs().mean(),
        "difference_above_5bps_count": int(
            ((audit.raw_cash_ex - audit.provider_adjusted).abs() > 0.0005).sum()
        ),
        "max_difference_date": str(
            (audit.raw_cash_ex - audit.provider_adjusted).abs().idxmax().date()
        ),
    }
    endpoint = pd.Timestamp("2026-09-30")
    result["issuer_audit"] = {}
    for label, start, expected in [
        ("YTD", "2025-12-31", 0.2405),
        ("one_year", "2025-09-30", 0.2623),
    ]:
        window = adj_total_returns.loc[pd.Timestamp(start) + pd.Timedelta(days=1) : endpoint]
        value = (1 + window).prod() - 1
        result["issuer_audit"][label] = {
            "provider_adjusted_return": value,
            "issuer_mkt_return": expected,
            "difference_bps": (value - expected) * 10000,
            "boundary": (
                "Issuer midpoint-based price return; tape close can differ. "
                "Large discrepancy prevents verified source replay claim."
            ),
        }
    volume = bars[bars.adjustment == "raw"].pivot(index="session", columns="symbol", values="v")
    dollar_adv = (raw.NIXT * volume.NIXT).rolling(20, min_periods=20).mean().shift(1)
    result["capacity"] = {
        date: {
            "lagged20d_dollar_adv": dollar_adv.get(pd.Timestamp(date)),
            "20k_participation": 20000 / dollar_adv.get(pd.Timestamp(date))
            if pd.notna(dollar_adv.get(pd.Timestamp(date)))
            else None,
        }
        for date in quotes
    }
    result["flags"] = {
        "workflow_pass": True,
        "research_pass": True,
        "ml_contribution_pass": False,
        "llm_contribution_pass": False,
        "paper_ready_pass": False,
        "profitable_alpha_claim": False,
        "deployment_readiness_claim": False,
        "broker_activity_allowed": False,
        "simulation_orders_started": False,
    }
    result["resources"] = {
        "process_cpu_seconds": time.process_time() - cpu_start,
        "wall_seconds": time.monotonic() - wall_start,
        "max_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        "paid_dollars": 0,
        "model_fits": 0,
    }
    save(RESULT / "evaluation.json", clean(result))
    save(ITER / "evaluation-report.json", clean(result))
    with (ITER / "trial-ledger.jsonl").open("w") as file:
        for cid in candidates:
            file.write(
                json.dumps(
                    {
                        "candidate_id": cid,
                        "iter_id": ITER_ID,
                        "status": "evaluated_diagnostic_nonpromotable",
                        "cost_bps": 20,
                        "source_matrix": str(
                            (RESULT / "daily-return-matrix.csv").relative_to(ROOT)
                        ),
                    }
                )
                + "\n"
            )
    print(
        json.dumps(
            clean(
                {
                    "NIXT": result["source_replay"]["NIXT"],
                    "IWN": result["source_replay"]["IWN"],
                    "resources": result["resources"],
                }
            )
        )
    )


if __name__ == "__main__":
    main()
