from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd

from open_composer.config import ensure_dir, project_root
from open_composer.market_calendar import NEW_YORK, us_equity_session_close
from open_composer.research.mom_minute_lockbox import _session_split, _slice
from open_composer.research.mom_minute_round import (
    BASE_COST_BPS,
    _align_signal_and_trade,
    _load_research_frame,
    _strategy_returns,
)
from open_composer.research.momentum_ml_research import FEATURES, _feature_frame
from open_composer.research.momentum_signal_router import momentum_target_position
from open_composer.storage import append_jsonl, write_json

ITER_ID = "mom_minute_r4_portfolio"
OUTPUT_DIR = Path("reports/research/iterations") / ITER_ID
VIRTUAL_PAPER_DIR = Path("reports/paper/virtual_momentum_portfolio")
INITIAL_CAPITAL = 100_000.0
FROZEN_SPEC_PATH = "strategy_specs/drafts/us_mom_minute_p1_003_frozen.yaml"
VIRTUAL_PAPER_COST_BPS = {"15m": 3.0, "30m": BASE_COST_BPS["30m"]}


@dataclass(frozen=True)
class MomentumPortfolioResult:
    json_path: Path
    markdown_path: Path
    payload: dict[str, Any]


def run_momentum_strategy_portfolio(root: Path | None = None) -> MomentumPortfolioResult:
    base = root or project_root()
    ml_report = _read_json(
        base / "reports/research/iterations/mom_minute_r3_ml/model-comparison.json"
    )
    sleeves = _sleeves(base, ml_report)
    rows = []
    for sleeve in sleeves:
        frame, position, decision_frame, decision_position = _sleeve_position(base, sleeve)
        split = _session_split(frame)
        returns = _strategy_returns(
            frame,
            position,
            cost_bps=BASE_COST_BPS["30m"] if sleeve["timeframe"] == "30m" else 3.0,
            allow_overnight=True,
        )
        lockbox = _slice(returns, split["lockbox"])
        rows.append(
            {
                **sleeve,
                "full_history_metrics": _portfolio_metrics(returns),
                "lockbox_metrics": _portfolio_metrics(lockbox),
                "latest_target_weight": float(decision_position.iloc[-1]),
                "latest_signal_timestamp": pd.Timestamp(
                    decision_frame.iloc[-1]["timestamp"]
                ).isoformat(),
                "data_as_of": pd.Timestamp(decision_frame.iloc[-1]["timestamp"]).isoformat(),
                "latest_mark_price": float(decision_frame.iloc[-1]["trade_close"]),
                "evaluation_data_as_of": pd.Timestamp(frame.iloc[-1]["timestamp"]).isoformat(),
                "sleeve_definition_hash": _sleeve_definition_hash(base, sleeve),
                "model_application_status": _model_application_status(base, sleeve),
                "decision_session_complete": _decision_session_complete(
                    decision_frame, sleeve["timeframe"]
                ),
                "execution_scope": "research_virtual_paper_only",
            }
        )
    payload = {
        "report_type": "momentum_strategy_portfolio",
        "iter_id": ITER_ID,
        "generated_at": datetime.now(UTC).isoformat(),
        "workflow_pass": True,
        "research_pass": False,
        "research_status": "historical_exploration_complete_forward_validation_pending",
        "paper_ready_pass": False,
        "broker_writes": False,
        "portfolio": rows,
        "simulation": {
            "mode": "isolated_virtual_paper_sleeves",
            "initial_capital_per_sleeve": INITIAL_CAPITAL,
            "alpaca_multi_strategy_orders": False,
            "reason": "one Alpaca account has no strategy-level position sleeves",
            "forward_validation_ready": True,
        },
    }
    output = base / OUTPUT_DIR
    ensure_dir(output)
    json_path = output / "portfolio-evaluation.json"
    markdown_path = output / "portfolio-evaluation.md"
    ledger_path = output / "portfolio-trial-ledger.jsonl"
    write_json(json_path, payload)
    markdown_path.write_text(_render_markdown(payload), encoding="utf-8")
    with ledger_path.open("w", encoding="utf-8") as handle:
        for row in rows:
            ledger_row = {
                **row,
                "evidence_class": (
                    "frozen_rule_reference"
                    if row["sleeve_id"] == "R0"
                    else "diagnostic_shadow_only"
                    if row["strategy_type"] == "ml"
                    else "retrospective_exploratory"
                ),
                "selection_window_reused": row["sleeve_id"] != "R0",
            }
            handle.write(json.dumps(ledger_row, sort_keys=True) + "\n")
    return MomentumPortfolioResult(json_path, markdown_path, payload)


def run_virtual_momentum_paper(
    root: Path | None = None,
    *,
    as_of: datetime | None = None,
) -> MomentumPortfolioResult:
    base = root or project_root()
    portfolio = run_momentum_strategy_portfolio(base).payload
    observed_at = pd.Timestamp(as_of or datetime.now(UTC))
    if observed_at.tzinfo is None:
        observed_at = observed_at.tz_localize("UTC")
    else:
        observed_at = observed_at.tz_convert("UTC")
    receipts = []
    for sleeve in portfolio["portfolio"]:
        sleeve_dir = base / VIRTUAL_PAPER_DIR / sleeve["sleeve_id"]
        ensure_dir(sleeve_dir)
        ledger_path = sleeve_dir / "ledger.jsonl"
        previous = _last_observed_jsonl(ledger_path)
        definition_changed = bool(
            previous and previous.get("sleeve_definition_hash") != sleeve["sleeve_definition_hash"]
        )
        if definition_changed:
            previous = {}
        previous_equity = float(previous.get("equity", INITIAL_CAPITAL))
        previous_weight = float(previous.get("target_weight", 0.0))
        previous_mark = previous.get("mark_price")
        data_as_of = pd.Timestamp(sleeve["data_as_of"])
        data_age_hours = float((observed_at - data_as_of).total_seconds() / 3600)
        expected_session = _latest_completed_session(observed_at)
        data_session = data_as_of.tz_convert("America/New_York").date()
        status = (
            "observed"
            if data_session == expected_session and sleeve["decision_session_complete"]
            else "awaiting_fresh_market_data"
        )
        observation_id = _observation_id(
            sleeve_id=sleeve["sleeve_id"],
            data_as_of=data_as_of.isoformat(),
            target_weight=float(sleeve["latest_target_weight"]),
            sleeve_definition_hash=sleeve["sleeve_definition_hash"],
        )
        mark_price = float(sleeve["latest_mark_price"])
        epoch_anchor = status == "observed" and not previous
        if status == "observed" and not epoch_anchor:
            period = _virtual_period_metrics(base, sleeve, previous, expected_session)
            equity = previous_equity * (1.0 + period["net_return"])
        else:
            period = {
                "gross_return": 0.0,
                "turnover": 0.0,
                "cost_return": 0.0,
                "net_return": 0.0,
                "evaluated_bars": 0,
                "evaluation_start": None,
                "evaluation_end": (
                    data_as_of.isoformat() if epoch_anchor else previous.get("evaluation_end")
                ),
            }
            equity = previous_equity
        record = {
            "report_type": "momentum_virtual_paper_observation",
            "sleeve_id": sleeve["sleeve_id"],
            "strategy_type": sleeve["strategy_type"],
            "status": status,
            "observed_at": observed_at.isoformat(),
            "data_as_of": data_as_of.isoformat(),
            "data_age_hours": round(data_age_hours, 4),
            "expected_completed_session": expected_session.isoformat(),
            "decision_session_complete": sleeve["decision_session_complete"],
            "observation_id": observation_id,
            "sleeve_definition_hash": sleeve["sleeve_definition_hash"],
            "definition_epoch_reset": definition_changed,
            "epoch_anchor": epoch_anchor,
            "target_weight": sleeve["latest_target_weight"],
            "previous_target_weight": previous_weight,
            "mark_price": mark_price,
            "previous_mark_price": previous_mark,
            "gross_return": round(period["gross_return"], 10),
            "turnover": round(period["turnover"], 10),
            "cost_return": round(period["cost_return"], 10),
            "net_return": round(period["net_return"], 10),
            "evaluated_bars": period["evaluated_bars"],
            "evaluation_start": period["evaluation_start"],
            "evaluation_end": period["evaluation_end"],
            "equity": round(equity, 6),
            "initial_capital": INITIAL_CAPITAL,
            "paper_order_authorization": False,
            "broker_writes": False,
        }
        if status == "observed" and observation_id != previous.get("observation_id"):
            append_jsonl(ledger_path, [record])
        write_json(sleeve_dir / "latest.json", record)
        receipts.append(record)
    payload = {
        "report_type": "momentum_virtual_paper_portfolio_cycle",
        "generated_at": observed_at.isoformat(),
        "status": (
            "observed"
            if all(row["status"] == "observed" for row in receipts)
            else "awaiting_fresh_market_data"
        ),
        "sleeves": receipts,
        "alpaca_credentials_required_for_refresh": True,
        "paper_order_authorization": False,
        "broker_writes": False,
    }
    output = base / VIRTUAL_PAPER_DIR
    json_path = output / "latest-cycle.json"
    markdown_path = output / "latest-cycle.md"
    write_json(json_path, payload)
    markdown_path.write_text(_render_virtual_paper(payload), encoding="utf-8")
    return MomentumPortfolioResult(json_path, markdown_path, payload)


def _sleeves(root: Path, ml_report: dict[str, Any]) -> list[dict[str, Any]]:
    frozen_models = {row["model_family"]: row for row in ml_report.get("frozen_models", [])}
    return [
        {
            "sleeve_id": "R0",
            "strategy_type": "rule",
            "variant": "roc72_atr2_5",
            "timeframe": "30m",
            "status": "rule_champion",
            "spec_path": FROZEN_SPEC_PATH,
            "definition_source": "strategy_spec",
        },
        {
            "sleeve_id": "R1",
            "strategy_type": "rule",
            "variant": "roc72_no_atr",
            "timeframe": "30m",
            "status": "research_candidate",
            "definition_source": "portfolio_harness_experimental_contract",
        },
        {
            "sleeve_id": "R2",
            "strategy_type": "rule",
            "variant": "roc72_hysteresis",
            "timeframe": "30m",
            "status": "research_candidate",
            "definition_source": "portfolio_harness_experimental_contract",
        },
        {
            "sleeve_id": "R3",
            "strategy_type": "rule",
            "variant": "roc144_atr2_5",
            "timeframe": "15m",
            "status": "research_candidate",
            "definition_source": "portfolio_harness_experimental_contract",
        },
        {
            "sleeve_id": "M1",
            "strategy_type": "ml",
            "variant": "regularized_logistic",
            "timeframe": "30m",
            "definition_source": "frozen_model_plus_rule_spec",
            "base_spec_path": FROZEN_SPEC_PATH,
            **frozen_models.get("regularized_logistic", {"status": "missing_model"}),
        },
        {
            "sleeve_id": "M2",
            "strategy_type": "ml",
            "variant": "lightgbm_challenger",
            "timeframe": "30m",
            "definition_source": "frozen_model_plus_rule_spec",
            "base_spec_path": FROZEN_SPEC_PATH,
            **frozen_models.get("lightgbm_challenger", {"status": "missing_model"}),
        },
    ]


def _sleeve_position(
    root: Path, sleeve: dict[str, Any]
) -> tuple[pd.DataFrame, pd.Series, pd.DataFrame, pd.Series]:
    signal = _load_research_frame(root, "QQQ", sleeve["timeframe"])
    target = _load_research_frame(root, "TQQQ", sleeve["timeframe"])
    if signal is None or target is None:
        raise ValueError(f"missing strict data for sleeve {sleeve['sleeve_id']}")
    frame = _align_signal_and_trade(signal, target)
    decision_frame = _align_decision_frame(signal, target)
    variant = sleeve["variant"]
    position = _variant_position(frame, variant)
    decision_position = _variant_position(decision_frame, variant)
    if sleeve["strategy_type"] == "ml" and sleeve.get("model_path"):
        position = _ml_gate_position(root, frame, position, sleeve)
        decision_position = _ml_gate_position(root, decision_frame, decision_position, sleeve)
    return frame, position, decision_frame, decision_position


def _variant_position(frame: pd.DataFrame, variant: str) -> pd.Series:
    if variant == "roc72_no_atr":
        return (frame["signal_close"] / frame["signal_close"].shift(72) - 1 > 0).astype(float)
    if variant == "roc72_hysteresis":
        return _hysteresis_position(frame, lookback=72, exit_confirm=3, minimum_hold=6)
    if variant == "roc144_atr2_5":
        return momentum_target_position(frame, lookback_bars=144, atr_filter_multiplier=2.5)
    return momentum_target_position(frame, lookback_bars=72, atr_filter_multiplier=2.5)


def _align_decision_frame(signal: pd.DataFrame, traded: pd.DataFrame) -> pd.DataFrame:
    signal_cols = signal[
        ["timestamp", "open", "high", "low", "close", "volume", "session_date"]
    ].rename(
        columns={
            "open": "signal_open",
            "high": "signal_high",
            "low": "signal_low",
            "close": "signal_close",
            "volume": "signal_volume",
        }
    )
    trade_cols = traded[["timestamp", "open", "high", "low", "close", "volume"]].rename(
        columns={
            "open": "trade_open",
            "high": "trade_high",
            "low": "trade_low",
            "close": "trade_close",
            "volume": "trade_volume",
        }
    )
    return (
        signal_cols.merge(trade_cols, on="timestamp", how="inner")
        .sort_values("timestamp")
        .reset_index(drop=True)
    )


def _hysteresis_position(
    frame: pd.DataFrame,
    *,
    lookback: int,
    exit_confirm: int,
    minimum_hold: int,
) -> pd.Series:
    close = frame["signal_close"]
    risk_on = close / close.shift(lookback) - 1 > 0
    result = pd.Series(0.0, index=frame.index)
    active = False
    held = 0
    negative_count = 0
    for index, value in enumerate(risk_on.fillna(False).to_numpy()):
        if not active and value:
            active = True
            held = 0
            negative_count = 0
        elif active:
            held += 1
            negative_count = 0 if value else negative_count + 1
            if held >= minimum_hold and negative_count >= exit_confirm:
                active = False
        result.iloc[index] = float(active)
    return result


def _ml_gate_position(
    root: Path,
    frame: pd.DataFrame,
    baseline: pd.Series,
    sleeve: dict[str, Any],
) -> pd.Series:
    model_path = root / sleeve["model_path"]
    if _model_application_status(root, sleeve) != "model_verified":
        return baseline.copy()
    try:
        estimator = joblib.load(model_path)
    except Exception:
        return baseline.copy()
    features = _feature_frame(frame)
    threshold = float(sleeve["threshold"])
    result = pd.Series(0.0, index=frame.index)
    active = False
    previous = 0.0
    for index, value in enumerate(baseline.astype(float).to_numpy()):
        if value > 0 and previous <= 0:
            row = features.iloc[[index]]
            if row.notna().all(axis=None):
                try:
                    probability = float(estimator.predict_proba(row[list(FEATURES)])[:, 1][0])
                    active = bool(np.isfinite(probability) and probability >= threshold)
                except Exception:
                    active = True
            else:
                active = True
        if value <= 0:
            active = False
        result.iloc[index] = value if active else 0.0
        previous = value
    return result


def _observation_id(
    *, sleeve_id: str, data_as_of: str, target_weight: float, sleeve_definition_hash: str
) -> str:
    payload = json.dumps(
        {
            "sleeve_id": sleeve_id,
            "data_as_of": data_as_of,
            "target_weight": target_weight,
            "sleeve_definition_hash": sleeve_definition_hash,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return sha256(payload.encode("utf-8")).hexdigest()


def _sleeve_definition_hash(root: Path, sleeve: dict[str, Any]) -> str:
    identity = {key: value for key, value in sleeve.items() if key != "model_path"}
    model_path = sleeve.get("model_path")
    if model_path:
        path = root / str(model_path)
        identity["model_sha256"] = _file_sha256(path) if path.exists() else "missing"
    spec_path = sleeve.get("spec_path") or sleeve.get("base_spec_path")
    if spec_path:
        path = root / str(spec_path)
        identity["spec_sha256"] = _file_sha256(path) if path.exists() else "missing"
    return sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()


def _file_sha256(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _model_application_status(root: Path, sleeve: dict[str, Any]) -> str:
    if sleeve.get("strategy_type") != "ml":
        return "not_applicable"
    model_path = sleeve.get("model_path")
    expected_hash = sleeve.get("model_sha256")
    if not model_path or not expected_hash:
        return "fallback_missing_model_provenance"
    path = root / str(model_path)
    if not path.exists():
        return "fallback_missing_model"
    if _file_sha256(path) != expected_hash:
        return "fallback_model_hash_mismatch"
    return "model_verified"


def _latest_completed_session(observed_at: pd.Timestamp) -> date:
    local = observed_at.tz_convert("America/New_York")
    candidate = local.date()
    close = us_equity_session_close(candidate)
    if close is None or local.time() < close:
        candidate -= timedelta(days=1)
    while us_equity_session_close(candidate) is None:
        candidate -= timedelta(days=1)
    return candidate


def _decision_session_complete(frame: pd.DataFrame, timeframe: str) -> bool:
    if frame.empty:
        return False
    timestamps = pd.to_datetime(frame["timestamp"], utc=True).dt.tz_convert("America/New_York")
    session = timestamps.iloc[-1].date()
    close = us_equity_session_close(session)
    if close is None:
        return False
    minutes = int(timeframe.removesuffix("m"))
    current = pd.Timestamp(datetime.combine(session, datetime.min.time()), tz=NEW_YORK)
    current += pd.Timedelta(hours=9, minutes=30)
    end = pd.Timestamp(datetime.combine(session, close), tz=NEW_YORK)
    expected: set[pd.Timestamp] = set()
    while current < end:
        expected.add(current.tz_convert("UTC"))
        current += pd.Timedelta(minutes=minutes)
    actual = set(timestamps.loc[timestamps.dt.date == session].dt.tz_convert("UTC"))
    return actual == expected


def _virtual_period_metrics(
    root: Path,
    sleeve: dict[str, Any],
    previous: dict[str, Any],
    expected_session: date,
) -> dict[str, Any]:
    frame, position, _, _ = _sleeve_position(root, sleeve)
    timestamps = pd.to_datetime(frame["timestamp"], utc=True)
    previous_end = previous.get("evaluation_end")
    if previous_end:
        mask = timestamps > pd.Timestamp(previous_end)
    else:
        mask = timestamps.dt.tz_convert("America/New_York").dt.date == expected_session
    gross = position.astype(float) * frame["next_trade_return"].fillna(0.0)
    turnover = position.astype(float).diff().abs()
    if len(turnover):
        turnover.iloc[0] = abs(position.iloc[0])
    turnover = turnover.fillna(0.0)
    cost = turnover * VIRTUAL_PAPER_COST_BPS[sleeve["timeframe"]] / 10000.0
    net = gross - cost
    selected = net.loc[mask]
    if selected.empty:
        return {
            "gross_return": 0.0,
            "turnover": 0.0,
            "cost_return": 0.0,
            "net_return": 0.0,
            "evaluated_bars": 0,
            "evaluation_start": None,
            "evaluation_end": previous_end,
        }
    return {
        "gross_return": float((1.0 + gross.loc[mask]).prod() - 1.0),
        "turnover": float(turnover.loc[mask].sum()),
        "cost_return": float(cost.loc[mask].sum()),
        "net_return": float((1.0 + selected).prod() - 1.0),
        "evaluated_bars": int(len(selected)),
        "evaluation_start": timestamps.loc[mask].iloc[0].isoformat(),
        "evaluation_end": timestamps.loc[mask].iloc[-1].isoformat(),
    }


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def _last_jsonl(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line]
    return json.loads(lines[-1]) if lines else {}


def _last_observed_jsonl(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    for line in reversed(path.read_text(encoding="utf-8").splitlines()):
        if not line:
            continue
        row = json.loads(line)
        if row.get("status") == "observed":
            return row
    return {}


def _portfolio_metrics(returns: pd.Series) -> dict[str, Any]:
    clean = returns.replace([np.inf, -np.inf], np.nan).dropna().astype(float)
    if clean.empty:
        return {
            "total_return_pct": 0.0,
            "annualized_return_pct": 0.0,
            "sharpe": 0.0,
            "max_drawdown_pct": 0.0,
            "bars": 0,
            "trading_days": 0,
        }
    equity = (1.0 + clean).cumprod()
    total_return = float(equity.iloc[-1] - 1.0)
    calendar_years = max(
        (clean.index.max() - clean.index.min()).total_seconds() / (365.25 * 86400),
        1 / 252,
    )
    annualized = (1.0 + total_return) ** (1.0 / calendar_years) - 1.0
    bars_per_year = len(clean) / calendar_years
    std = float(clean.std(ddof=0))
    sharpe = float(clean.mean() / std * np.sqrt(bars_per_year)) if std > 0 else 0.0
    drawdown = equity / equity.cummax() - 1.0
    return {
        "total_return_pct": round(total_return * 100, 4),
        "annualized_return_pct": round(annualized * 100, 4),
        "sharpe": round(sharpe, 4),
        "max_drawdown_pct": round(float(drawdown.min()) * 100, 4),
        "bars": int(len(clean)),
        "trading_days": int(clean.index.normalize().nunique()),
    }


def _render_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Momentum Strategy Portfolio",
        "",
        "| Sleeve | Type | Variant | Status | Lockbox Return % | Sharpe | MaxDD % |",
        "|---|---|---|---|---:|---:|---:|",
    ]
    for row in payload["portfolio"]:
        metrics = row["lockbox_metrics"]
        lines.append(
            f"| {row['sleeve_id']} | {row['strategy_type']} | {row['variant']} | "
            f"{row['status']} | {metrics['total_return_pct']} | {metrics['sharpe']} | "
            f"{metrics['max_drawdown_pct']} |"
        )
    return "\n".join(lines) + "\n"


def _render_virtual_paper(payload: dict[str, Any]) -> str:
    lines = [
        "# Momentum Virtual Paper Cycle",
        "",
        f"- Status: `{payload['status']}`",
        "",
        "| Sleeve | Status | Data As Of | Target Weight |",
        "|---|---|---|---:|",
    ]
    for row in payload["sleeves"]:
        lines.append(
            f"| {row['sleeve_id']} | {row['status']} | {row['data_as_of']} | "
            f"{row['target_weight']} |"
        )
    lines.extend(["", "No Alpaca orders or broker writes were authorized."])
    return "\n".join(lines) + "\n"
