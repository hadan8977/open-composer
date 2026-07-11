from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from itertools import product
from pathlib import Path
from typing import Any

import pandas as pd

from open_composer.config import ensure_dir, project_root
from open_composer.research.mom_minute_round import (
    BASE_COST_BPS,
    _align_signal_and_trade,
    _atr_pct,
    _benchmarks,
    _entry_count,
    _load_bundle,
    _metrics,
    _required_pair,
    _strategy_returns,
)
from open_composer.storage import write_json

ITER_ID = "mom_minute_r2"
ITERATION_DIR = Path("reports/research/iterations") / ITER_ID
LOOKBACKS = [72, 96, 120]
ATR_MULTIPLIERS = [1.5, 2.0, 2.5]


@dataclass(frozen=True)
class MomentumLockboxResult:
    evaluation_json_path: Path
    evaluation_markdown_path: Path
    trial_ledger_path: Path
    payload: dict[str, Any]


def run_mom_minute_lockbox(
    root: Path | None = None,
    *,
    report_date: str | None = None,
    lookbacks: list[int] | None = None,
    atr_multipliers: list[float] | None = None,
) -> MomentumLockboxResult:
    base = root or project_root()
    lookbacks = lookbacks or LOOKBACKS
    atr_multipliers = atr_multipliers or ATR_MULTIPLIERS
    combinations = list(product(lookbacks, atr_multipliers))
    if len(combinations) > 9:
        raise ValueError(f"mom_minute_r2 search budget exceeded: {len(combinations)} > 9")

    bundle = _load_bundle(base, "30m")
    qqq, tqqq = _required_pair(bundle, "30m")
    aligned = _align_signal_and_trade(qqq, tqqq)
    split = _session_split(aligned)
    trials: list[dict[str, Any]] = []
    returns_by_id: dict[str, tuple[pd.Series, pd.Series, pd.Series]] = {}
    for index, (lookback, multiplier) in enumerate(combinations, start=1):
        candidate, naive, stressed = _candidate_returns(aligned, lookback, multiplier)
        trial_id = f"{ITER_ID}_p1_{index:03d}"
        returns_by_id[trial_id] = (candidate, naive, stressed)
        development = _metrics(_slice(candidate, split["development"]))
        validation = _metrics(_slice(candidate, split["validation"]))
        validation_pass = development["total_return_pct"] > 0 and validation["total_return_pct"] > 0
        trials.append(
            {
                "trial_id": trial_id,
                "params": {
                    "timeframe": "30m",
                    "lookback_bars": lookback,
                    "atr_filter_multiplier": multiplier,
                    "signal_symbol": "QQQ",
                    "traded_symbol": "TQQQ",
                    "fill_assumption": "next_bar_open",
                },
                "development": development,
                "validation": validation,
                "validation_pass": validation_pass,
                "selection_score": _selection_score(development, validation),
                "lockbox": None,
            }
        )

    eligible = [trial for trial in trials if trial["validation_pass"]]
    selected = max(eligible, key=lambda row: row["selection_score"], default=None)
    lockbox: dict[str, Any] | None = None
    verdict = "stop"
    if selected is not None:
        candidate, naive, stressed = returns_by_id[selected["trial_id"]]
        candidate_holdout = _slice(candidate, split["lockbox"])
        naive_holdout = _slice(naive, split["lockbox"])
        stressed_holdout = _slice(stressed, split["lockbox"])
        metrics = _metrics(candidate_holdout)
        naive_metrics = _metrics(naive_holdout)
        x2_metrics = _metrics(stressed_holdout)
        benchmarks = _benchmarks(bundle, "30m", candidate_holdout.index)
        tqqq = benchmarks["TQQQ_buy_hold"]
        qqq_bh = benchmarks["QQQ_buy_hold"]
        gates = {
            "positive_net_return": metrics["total_return_pct"] > 0,
            "sharpe_at_least_0_8": metrics["sharpe"] >= 0.8,
            "maxdd_not_worse_than_tqqq": (
                tqqq.get("available") and metrics["max_drawdown_pct"] >= tqqq["max_drawdown_pct"]
            ),
            "x2_cost_positive": x2_metrics["total_return_pct"] > 0,
            "beats_naive_or_qqq": (
                metrics["total_return_pct"] > naive_metrics["total_return_pct"]
                or (
                    qqq_bh.get("available")
                    and metrics["total_return_pct"] > qqq_bh["total_return_pct"]
                )
            ),
        }
        passed = all(gates.values())
        verdict = "continue" if passed else "pivot"
        lockbox = {
            "opened_once": True,
            "selected_trial_id": selected["trial_id"],
            "metrics": metrics,
            "x2_cost_metrics": x2_metrics,
            "naive_baseline": naive_metrics,
            "benchmark_family": benchmarks,
            "trade_count": _entry_count(_position(aligned, **_signal_params(selected))),
            "gates": gates,
            "passed": passed,
            "failed_gates": [name for name, passed_gate in gates.items() if not passed_gate],
        }
        selected["lockbox"] = lockbox

    generated_at = datetime.now(UTC)
    payload = {
        "report_type": "mom_minute_r2_lockbox_evaluation",
        "iter_id": ITER_ID,
        "generated_at": generated_at.isoformat(),
        "report_date": report_date or generated_at.strftime("%Y%m%d"),
        "workflow_pass": True,
        "research_pass": verdict == "continue",
        "paper_ready_pass": False,
        "llm_contribution_pass": False,
        "verdict": verdict,
        "search_space": {"candidate_count": len(trials), "budget_cap": 9},
        "split": split,
        "selection_used_lockbox": False,
        "selected_trial_id": selected["trial_id"] if selected else None,
        "lockbox": lockbox,
        "trials": trials,
        "data_profile": {
            "provider": "alpaca",
            "feed": "iex",
            "evidence_tier": "research_only",
            "source_hashes": {
                symbol: frame["source_sha256"].iloc[0]
                for symbol, frame in bundle.items()
                if frame is not None and not frame.empty
            },
        },
    }
    output = base / ITERATION_DIR
    ensure_dir(output)
    json_path = output / "evaluation-report.json"
    md_path = output / "evaluation-report.md"
    ledger_path = output / "trial-ledger.jsonl"
    write_json(json_path, payload)
    md_path.write_text(_render_markdown(payload), encoding="utf-8")
    with ledger_path.open("w", encoding="utf-8") as handle:
        for trial in trials:
            handle.write(json.dumps(trial, sort_keys=True) + "\n")
    return MomentumLockboxResult(json_path, md_path, ledger_path, payload)


def _session_split(frame: pd.DataFrame) -> dict[str, dict[str, Any]]:
    sessions = list(dict.fromkeys(frame["session_date"].tolist()))
    if len(sessions) < 5:
        raise ValueError("mom_minute_r2 requires at least five sessions")
    dev_end = max(int(len(sessions) * 0.6), 1)
    val_end = max(int(len(sessions) * 0.8), dev_end + 1)
    groups = {
        "development": sessions[:dev_end],
        "validation": sessions[dev_end:val_end],
        "lockbox": sessions[val_end:],
    }
    return {
        name: {
            "start_session": values[0],
            "end_session": values[-1],
            "session_count": len(values),
        }
        for name, values in groups.items()
    }


def _slice(returns: pd.Series, split: dict[str, Any]) -> pd.Series:
    local_dates = returns.index.tz_convert("America/New_York").date.astype(str)
    mask = (local_dates >= split["start_session"]) & (local_dates <= split["end_session"])
    return returns.loc[mask]


def _position(frame: pd.DataFrame, lookback_bars: int, atr_filter_multiplier: float) -> pd.Series:
    close = frame["signal_close"]
    momentum = close / close.shift(lookback_bars) - 1.0
    atr_pct = _atr_pct(frame, lookback_bars)
    threshold = close.rolling(lookback_bars, min_periods=lookback_bars).max() * (
        1 - atr_filter_multiplier * atr_pct
    )
    return ((momentum > 0) & (close > threshold)).astype(float)


def _candidate_returns(
    frame: pd.DataFrame, lookback: int, multiplier: float
) -> tuple[pd.Series, pd.Series, pd.Series]:
    position = _position(frame, lookback, multiplier)
    close = frame["signal_close"]
    naive = (close / close.shift(lookback) - 1.0 > 0).astype(float)
    base = _strategy_returns(frame, position, cost_bps=BASE_COST_BPS["30m"], allow_overnight=True)
    naive_returns = _strategy_returns(
        frame, naive, cost_bps=BASE_COST_BPS["30m"], allow_overnight=True
    )
    stressed = _strategy_returns(
        frame, position, cost_bps=BASE_COST_BPS["30m"] * 2, allow_overnight=True
    )
    return base, naive_returns, stressed


def _selection_score(development: dict[str, Any], validation: dict[str, Any]) -> float:
    return float(
        validation["sharpe"] * 10
        + validation["total_return_pct"]
        + development["sharpe"]
        + validation["max_drawdown_pct"] * 0.25
    )


def _signal_params(trial: dict[str, Any]) -> dict[str, Any]:
    return {
        "lookback_bars": int(trial["params"]["lookback_bars"]),
        "atr_filter_multiplier": float(trial["params"]["atr_filter_multiplier"]),
    }


def _render_markdown(payload: dict[str, Any]) -> str:
    lockbox = payload["lockbox"]
    lines = [
        "# mom_minute_r2 Lockbox Evaluation",
        "",
        f"- Verdict: `{payload['verdict']}`",
        f"- Candidates: `{payload['search_space']['candidate_count']}`",
        f"- Selected: `{payload['selected_trial_id'] or 'none'}`",
        "- Selection used lockbox: `false`",
        "- Data: Alpaca IEX research-only; no paper/promotion claim.",
        "",
        "## Chronological Split",
        "",
    ]
    for name, row in payload["split"].items():
        lines.append(
            f"- `{name}`: {row['start_session']} to {row['end_session']} "
            f"({row['session_count']} sessions)"
        )
    lines.extend(["", "## Lockbox", ""])
    if lockbox is None:
        lines.append(
            "No candidate was positive in both development and validation; lockbox stayed closed."
        )
    else:
        metrics = lockbox["metrics"]
        lines.append(
            f"Return `{metrics['total_return_pct']}%`, Sharpe `{metrics['sharpe']}`, "
            f"MaxDD `{metrics['max_drawdown_pct']}%`, x2-cost return "
            f"`{lockbox['x2_cost_metrics']['total_return_pct']}%`."
        )
        lines.extend(["", "| Gate | Pass |", "|---|---:|"])
        lines.extend(f"| `{name}` | `{passed}` |" for name, passed in lockbox["gates"].items())
    return "\n".join(lines).rstrip() + "\n"
