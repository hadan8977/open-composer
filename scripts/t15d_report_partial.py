"""Report the completed ETF portion of T-20261006-15-D without changing the grid.

The D accumulator stores daily gross returns, cost components, trade-level gross/cost
observations, and two placebo families.  This script only summarizes those frozen outputs;
it deliberately labels cross-sectional IC as unavailable for a two-name basket.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
ACC = ROOT / "data/features/t15_work/d_acc"
OUT = ROOT / "reports/research/iterations/t20261006_15_intraday_rules"
DATES = np.load(ROOT / "data/features/t15_work/ab_QQQ.npz", allow_pickle=False)["dates"]
RECENT_START = np.datetime64("2024-01-08")
RECENT_END = np.datetime64("2026-10-06")
RECENT = (DATES >= RECENT_START) & (DATES <= RECENT_END)
TRADING_DAYS = 252


def annual_sharpe(values: np.ndarray) -> float:
    x = np.asarray(values, dtype=float)
    x = x[np.isfinite(x)]
    if len(x) < 2 or not np.isfinite(x.std(ddof=1)) or x.std(ddof=1) <= 0:
        return float("nan")
    return float(x.mean() / x.std(ddof=1) * math.sqrt(TRADING_DAYS))


def nw_t_mean(values: np.ndarray, lags: int = 5) -> float:
    x = np.asarray(values, dtype=float)
    x = x[np.isfinite(x)]
    if len(x) < 3:
        return float("nan")
    mean = float(x.mean())
    centered = x - mean
    lrv = float(np.dot(centered, centered) / len(x))
    for lag in range(1, min(lags, len(x) - 1) + 1):
        lrv += (
            2.0
            * (1.0 - lag / (lags + 1.0))
            * float(np.dot(centered[lag:], centered[:-lag]) / len(x))
        )
    return float(mean / math.sqrt(max(lrv / len(x), 1e-30)))


def max_drawdown(values: np.ndarray) -> float:
    x = np.asarray(values, dtype=float)
    x = x[np.isfinite(x)]
    if len(x) == 0:
        return float("nan")
    curve = np.cumprod(1.0 + x)
    return float(np.min(curve / np.maximum.accumulate(curve) - 1.0))


def alpha_against_benchmark(returns: np.ndarray, benchmark: np.ndarray) -> dict[str, float]:
    y = np.asarray(returns, dtype=float)
    b = np.asarray(benchmark, dtype=float)
    ok = np.isfinite(y) & np.isfinite(b)
    y, b = y[ok], b[ok]
    if len(y) < 20:
        return {
            "alpha_daily": float("nan"),
            "alpha_annual": float("nan"),
            "alpha_t_nw5": float("nan"),
        }
    X = np.column_stack([np.ones(len(b)), b])
    beta = np.linalg.lstsq(X, y, rcond=None)[0]
    resid = y - X @ beta
    n = len(y)
    Q = X.T @ X / n
    score = X * resid[:, None]
    S = score.T @ score / n
    for lag in range(1, 6):
        weight = 1.0 - lag / 6.0
        gamma = score[lag:].T @ score[:-lag] / n
        S += weight * (gamma + gamma.T)
    inv = np.linalg.pinv(Q)
    cov = inv @ S @ inv / n
    se = math.sqrt(max(float(cov[0, 0]), 1e-30))
    return {
        "alpha_daily": float(beta[0]),
        "alpha_annual": float(beta[0] * TRADING_DAYS),
        "alpha_t_nw5": float(beta[0] / se),
        "beta_benchmark": float(beta[1]),
    }


def load_benchmark() -> np.ndarray:
    qqq = np.load(ROOT / "data/features/t15_work/ab_QQQ.npz", allow_pickle=False)["daily_ret"]
    spy = np.load(ROOT / "data/features/t15_work/ab_SPY.npz", allow_pickle=False)["daily_ret"]
    out = np.full(len(qqq), np.nan, dtype=float)
    both = np.isfinite(qqq) & np.isfinite(spy)
    out[both] = (qqq[both] + spy[both]) / 2.0
    out[np.isfinite(qqq) & ~np.isfinite(spy)] = qqq[np.isfinite(qqq) & ~np.isfinite(spy)]
    out[~np.isfinite(qqq) & np.isfinite(spy)] = spy[~np.isfinite(qqq) & np.isfinite(spy)]
    return out


def percentile(observed: float, placebo: np.ndarray) -> float | None:
    x = np.asarray(placebo, dtype=float)
    x = x[np.isfinite(x)]
    if not np.isfinite(observed) or len(x) == 0:
        return None
    return float((np.sum(x < observed) + 0.5 * np.sum(x == observed)) / len(x))


def summarize(path: Path, benchmark: np.ndarray) -> dict[str, object]:
    z = np.load(path, allow_pickle=False)
    n = int(z["N"])
    gross = z["g"]
    cost = (z["cv"] + z["cf"]) / 1e4 / n
    net = gross - cost
    r = net[RECENT]
    g = gross[RECENT]
    bench = benchmark[RECENT]
    trade_day = z["tr_day"]
    trade_gross = z["tr_g"]
    trade_cost = z["tr_c"]
    trade_recent = (
        trade_day >= int(np.flatnonzero(RECENT)[0]) if len(trade_day) else np.zeros(0, bool)
    )
    trade_net_bp = trade_gross[trade_recent] - trade_cost[trade_recent]
    placebo_net = z["pl_g"][:, RECENT] - cost[RECENT][None, :]
    random_net = z["rd_g"][:, RECENT] - z["rd_c"][:, RECENT]
    observed_sr = annual_sharpe(r)
    placebo_sr = np.array([annual_sharpe(x) for x in placebo_net])
    random_sr = np.array([annual_sharpe(x) for x in random_net])
    return {
        "file": str(path.relative_to(ROOT)),
        "period": "1h" if "_1h_" in path.name else "1m",
        "variant": path.stem.split("_main_", 1)[-1],
        "basket": "QQQ_SPY",
        "names": 2,
        "recent_start": str(RECENT_START),
        "recent_end": str(RECENT_END),
        "sessions": int(r.size),
        "trades_recent": int(trade_recent.sum()),
        "gross_sharpe_recent": annual_sharpe(g),
        "net_sharpe_recent": observed_sr,
        "annual_net_return": float(np.nanmean(r) * TRADING_DAYS),
        "annual_volatility": float(np.nanstd(r, ddof=1) * math.sqrt(TRADING_DAYS)),
        "max_drawdown": max_drawdown(r),
        "mean_net_bp_per_trade": (
            float(np.nanmean(trade_net_bp)) if len(trade_net_bp) else float("nan")
        ),
        "trade_net_t_nw5": nw_t_mean(trade_net_bp) if len(trade_net_bp) else float("nan"),
        "daily_net_t_nw5": nw_t_mean(r),
        "alpha": alpha_against_benchmark(r, bench),
        "direction_placebo_net_sharpe_percentile": percentile(observed_sr, placebo_sr),
        "same_slot_random_day_net_sharpe_percentile": percentile(observed_sr, random_sr),
        "placebo_net_sharpe_mean": float(np.nanmean(placebo_sr)),
        "random_day_net_sharpe_mean": float(np.nanmean(random_sr)),
        "cross_sectional_rank_ic": None,
        "cross_sectional_rank_ic_reason": (
            "QQQ+SPY has only two names; the frozen accumulator is a time-series basket, "
            "not a cross-sectional stock panel."
        ),
    }


def main() -> int:
    benchmark = load_benchmark()
    rows = []
    for period in ("1h", "1m"):
        for suffix in (
            "long_primary_only",
            "long_primary_and_reclaim",
            "longshort_primary_only",
            "longshort_primary_and_reclaim",
        ):
            path = ACC / f"QQQ_SPY_{period}_main_{suffix}.npz"
            if path.exists():
                rows.append(summarize(path, benchmark))
    payload = {
        "status": "partial_etf_accumulators_only",
        "contract": "t20261006_15_intraday_rules",
        "as_of": "2026-10-09",
        "recent_window": [str(RECENT_START), str(RECENT_END)],
        "rows": rows,
        "notes": [
            "No stock TOP50 results are included; those require the pending minute extraction.",
            "Cross-sectional IC is intentionally N/A for a two-name basket; stock IC will be "
            "computed when C/D TOP50 data exists.",
            "These are frozen-grid diagnostics, not a paper-readiness decision.",
        ],
    }
    out = OUT / "results_d_partial.json"
    out.write_text(json.dumps(payload, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    lines = [
        "# D 组 Reversal Trend：ETF 部分阶段报告",
        "",
        "状态：`partial_etf_accumulators_only`。这是冻结主网格的阶段性统计，不是最终 P1 判定。",
        "",
        "近期窗口：2024-01-08 至 2026-10-06。收益扣除冻结成本；alpha 是对等权 "
        "QQQ/SPY 日收益的 Newey-West 截距；两只 ETF 不足以给出有意义的横截面 Rank IC。",
        "",
        "| 周期 | 方向/信号 | 毛 Sharpe | 净 Sharpe | 年化净收益 | 交易数 | 每笔净 bp | "
        "交易 t(NW) | alpha/年 | alpha t | 随机方向分位 | 随机时段分位 |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for x in rows:
        a = x["alpha"]
        lines.append(
            f"| {x['period']} | {x['variant']} | {x['gross_sharpe_recent']:.3f} | "
            f"{x['net_sharpe_recent']:.3f} | {x['annual_net_return']:.2%} | {x['trades_recent']} | "
            f"{x['mean_net_bp_per_trade']:.2f} | {x['trade_net_t_nw5']:.2f} | "
            f"{a['alpha_annual']:.2%} | {a['alpha_t_nw5']:.2f} | "
            f"{x['direction_placebo_net_sharpe_percentile']:.3f} | "
            f"{x['same_slot_random_day_net_sharpe_percentile']:.3f} |"
        )
    lines += [
        "",
        "结论：本阶段只报告 ETF 篮子。任何正净 Sharpe 仍需与 100 个安慰剂、DSR、"
        "相位/持有期稳健性和 TOP50 股票规模曲线一起审核；没有横截面 IC 不能称为股票 Alpha。",
    ]
    (OUT / "report_d_partial.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"rows": len(rows), "json": str(out), "md": str(OUT / "report_d_partial.md")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
