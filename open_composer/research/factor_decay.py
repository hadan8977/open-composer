from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

from open_composer.adapters.data import load_ohlcv_for_spec
from open_composer.config import project_root
from open_composer.expressions import prepare_factor_frame
from open_composer.models.strategy_spec import FactorConfig, load_strategy_spec
from open_composer.notifications import safe_dispatch_notification
from open_composer.research.factor_library import get_factor
from open_composer.storage import append_jsonl


def monitor_factor_decay(
    factor_id: str,
    *,
    rolling_3m_bars: int = 63,
    rolling_12m_bars: int = 252,
    horizon_bars: int = 5,
    min_observations: int = 30,
    root: Path | None = None,
    dispatch_alert: bool = True,
) -> dict[str, Any]:
    """Append one factor decay-monitor row for a catalog factor.

    Decay is measured on absolute rolling rank IC because catalog factors can be
    useful in either direction. The raw rolling IC is still recorded for review.
    """
    if rolling_3m_bars < 2:
        raise ValueError("rolling_3m_bars must be at least 2")
    if rolling_12m_bars < rolling_3m_bars:
        raise ValueError("rolling_12m_bars must be >= rolling_3m_bars")
    if horizon_bars < 1:
        raise ValueError("horizon_bars must be at least 1")

    base = root or project_root()
    lineage_path = base / "reports" / "factors" / factor_id / "lineage.json"
    if not lineage_path.exists():
        raise FileNotFoundError(f"no lineage for {factor_id}; run `oc factor use-in` first")
    lineage = _read_json(lineage_path)
    used_specs = [item for item in lineage.get("used_in_specs", []) if isinstance(item, dict)]
    if not used_specs:
        raise ValueError(f"factor {factor_id} has lineage but no used_in_specs entries")

    spec_path = _latest_existing_spec_path(base, used_specs)
    spec = load_strategy_spec(spec_path)
    frame = load_ohlcv_for_spec(spec, base)
    factor_key, factor_config = _factor_config_for_decay(spec, factor_id)
    prepared = prepare_factor_frame(
        frame,
        {factor_key: factor_config},
        root=base,
        symbol=spec.primary_symbol,
        require_feature_symbol=False,
    )
    signal = pd.to_numeric(prepared[factor_key], errors="coerce")
    forward_return = _forward_return(frame, horizon_bars)
    joined = pd.DataFrame({"factor": signal, "forward_return": forward_return}).dropna()
    specs_using_factor = [
        str(item.get("spec_path", "")) for item in used_specs if item.get("spec_path")
    ]
    active_specs_using_factor = [
        path for path in specs_using_factor if str(path).startswith("strategy_specs/active/")
    ]

    base_record: dict[str, Any] = {
        "factor_id": factor_id,
        "monitor_ts": _now(),
        "status": "insufficient_data",
        "decay_alert": False,
        "alert_reason": None,
        "specs_using_factor": specs_using_factor,
        "active_specs_using_factor": active_specs_using_factor,
        "sample_spec_path": _relpath(spec_path, base),
        "symbol": spec.primary_symbol,
        "timeframe": spec.timeframe,
        "horizon_bars": horizon_bars,
        "rolling_3m_bars": rolling_3m_bars,
        "rolling_12m_bars": rolling_12m_bars,
        "sample_size": int(len(joined)),
    }
    if len(joined) < max(min_observations, rolling_3m_bars):
        record = {
            **base_record,
            "alert_reason": (
                f"insufficient observations: {len(joined)} < "
                f"{max(min_observations, rolling_3m_bars)}"
            ),
        }
        _append_record(base, factor_id, record)
        return record

    rolling_ics = _rolling_rank_ic(joined["factor"], joined["forward_return"], rolling_3m_bars)
    if len(rolling_ics) < 2:
        record = {
            **base_record,
            "alert_reason": "insufficient rolling IC windows",
            "sample_size": int(len(rolling_ics)),
        }
        _append_record(base, factor_id, record)
        return record

    current_3m = float(rolling_ics.iloc[-1])
    current_12m = _rank_ic(
        joined["factor"].tail(rolling_12m_bars),
        joined["forward_return"].tail(rolling_12m_bars),
    )
    history = rolling_ics.iloc[:-1] if len(rolling_ics) > 1 else rolling_ics
    abs_history = history.abs()
    recent = rolling_ics.tail(min(rolling_12m_bars, len(rolling_ics)))
    recent_std = float(recent.std(ddof=0)) if len(recent) > 1 else 0.0
    rolling_12m_ir = None if recent_std <= 0 else float(abs(recent.mean()) / recent_std)
    historical_25 = float(history.quantile(0.25))
    historical_50 = float(history.quantile(0.50))
    historical_75 = float(history.quantile(0.75))
    historical_abs_25 = float(abs_history.quantile(0.25))
    historical_abs_50 = float(abs_history.quantile(0.50))
    historical_abs_75 = float(abs_history.quantile(0.75))
    alert = abs(current_3m) < historical_abs_25
    alert_reason = None
    if alert:
        alert_reason = (
            f"abs 3m rank IC ({abs(current_3m):.4f}) below historical abs 25th "
            f"percentile ({historical_abs_25:.4f}); factor decay suspected"
        )

    record = {
        **base_record,
        "status": "alert" if alert else "healthy",
        "rolling_3m_rank_ic": current_3m,
        "rolling_12m_rank_ic": current_12m,
        "rolling_12m_ir": rolling_12m_ir,
        "ic_historical_25pct": historical_25,
        "ic_historical_50pct": historical_50,
        "ic_historical_75pct": historical_75,
        "abs_ic_historical_25pct": historical_abs_25,
        "abs_ic_historical_50pct": historical_abs_50,
        "abs_ic_historical_75pct": historical_abs_75,
        "decay_alert": alert,
        "alert_reason": alert_reason,
        "rolling_window_count": int(len(rolling_ics)),
    }
    _append_record(base, factor_id, record)
    if alert and dispatch_alert:
        safe_dispatch_notification(
            kind="system_alert",
            severity="warn",
            title=f"Factor decay alert: {factor_id}",
            body=alert_reason or "factor decay suspected",
            metadata={
                "factor_id": factor_id,
                "specs_using_factor": specs_using_factor,
                "sample_spec_path": record["sample_spec_path"],
            },
            root=base,
        )
    return record


def monitor_all_active_factors(
    root: Path | None = None,
    *,
    active_only: bool = False,
    dispatch_alert: bool = True,
) -> list[dict[str, Any]]:
    base = root or project_root()
    factors_dir = base / "reports" / "factors"
    if not factors_dir.exists():
        return []
    results: list[dict[str, Any]] = []
    for factor_dir in sorted(path for path in factors_dir.iterdir() if path.is_dir()):
        lineage_path = factor_dir / "lineage.json"
        if not lineage_path.exists():
            continue
        if active_only and not _lineage_has_active_spec(lineage_path):
            continue
        try:
            results.append(
                monitor_factor_decay(
                    factor_dir.name,
                    root=base,
                    dispatch_alert=dispatch_alert,
                )
            )
        except Exception as exc:  # noqa: BLE001 - report per-factor failure without aborting batch
            results.append(
                {
                    "factor_id": factor_dir.name,
                    "monitor_ts": _now(),
                    "status": "error",
                    "decay_alert": False,
                    "error": str(exc),
                }
            )
    return results


def read_decay_history(
    root: Path | None, factor_id: str, *, limit: int | None = None
) -> list[dict[str, Any]]:
    base = root or project_root()
    path = base / "reports" / "factors" / factor_id / "decay-monitor.jsonl"
    if not path.exists():
        return []
    rows = [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]
    return rows[-limit:] if limit is not None else rows


def build_factor_decay_payload(
    root: Path | None, factor_id: str, *, limit: int = 90
) -> dict[str, Any]:
    history = read_decay_history(root, factor_id, limit=limit)
    return {
        "factor_id": factor_id,
        "history": history,
        "latest": history[-1] if history else None,
        "alert_count": sum(1 for row in history if row.get("decay_alert")),
    }


def build_decay_report(root: Path | None = None, *, days: int = 90) -> list[dict[str, Any]]:
    base = root or project_root()
    cutoff = datetime.now(UTC) - timedelta(days=days)
    factors_dir = base / "reports" / "factors"
    rows: list[dict[str, Any]] = []
    if not factors_dir.exists():
        return rows
    for factor_dir in sorted(path for path in factors_dir.iterdir() if path.is_dir()):
        history = [
            row
            for row in read_decay_history(base, factor_dir.name)
            if _parse_ts(str(row.get("monitor_ts", ""))) >= cutoff
        ]
        if not history:
            continue
        alerts = sum(1 for row in history if row.get("decay_alert"))
        latest = history[-1]
        rows.append(
            {
                "factor_id": factor_dir.name,
                "checks": len(history),
                "alerts": alerts,
                "latest_status": latest.get("status", "unknown"),
                "latest_3m_rank_ic": latest.get("rolling_3m_rank_ic"),
                "latest_12m_ir": latest.get("rolling_12m_ir"),
                "recommendation": "retire?" if alerts >= 3 else "watch" if alerts else "healthy",
            }
        )
    return rows


def retire_factor(factor_id: str, *, reason: str = "", root: Path | None = None) -> dict[str, Any]:
    base = root or project_root()
    lineage_path = base / "reports" / "factors" / factor_id / "lineage.json"
    if not lineage_path.exists():
        raise FileNotFoundError(f"factor {factor_id} has no lineage")
    payload = _read_json(lineage_path)
    payload["retired_at"] = _now()
    payload["retirement_reason"] = reason
    lineage_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def _factor_config_for_decay(spec: Any, factor_id: str) -> tuple[str, FactorConfig]:
    for name, config in spec.factors.items():
        if config.source == "factor_library" and config.factor_id == factor_id:
            return name, config
        if name == factor_id:
            return name, config
    factor = get_factor(factor_id)
    if not factor.expression:
        raise ValueError(
            f"factor {factor_id} has no expression template and cannot be decay-monitored"
        )
    return factor_id, FactorConfig(source="factor_library", factor_id=factor_id)


def _latest_existing_spec_path(base: Path, used_specs: list[dict[str, Any]]) -> Path:
    for item in reversed(used_specs):
        raw_path = item.get("spec_path")
        if not raw_path:
            continue
        path = base / str(raw_path)
        if path.exists():
            return path
    raise FileNotFoundError("no used_in_specs entry points to an existing StrategySpec")


def _forward_return(frame: pd.DataFrame, horizon_bars: int) -> pd.Series:
    close = pd.to_numeric(frame["close"], errors="coerce")
    return close.shift(-horizon_bars) / close - 1.0


def _rolling_rank_ic(factor: pd.Series, forward_return: pd.Series, window: int) -> pd.Series:
    joined = pd.DataFrame({"factor": factor, "forward_return": forward_return}).dropna()
    values: list[float | None] = []
    index: list[Any] = []
    for end in range(window, len(joined) + 1):
        chunk = joined.iloc[end - window : end]
        values.append(_rank_ic(chunk["factor"], chunk["forward_return"]))
        index.append(joined.index[end - 1])
    return pd.Series(values, index=index, dtype="float64").dropna()


def _rank_ic(factor: pd.Series, forward_return: pd.Series) -> float | None:
    joined = pd.DataFrame({"factor": factor, "forward_return": forward_return}).dropna()
    if len(joined) < 3:
        return None
    if (
        joined["factor"].nunique(dropna=True) <= 1
        or joined["forward_return"].nunique(dropna=True) <= 1
    ):
        return None
    value = joined["factor"].rank().corr(joined["forward_return"].rank())
    return None if pd.isna(value) else float(value)


def _append_record(base: Path, factor_id: str, record: dict[str, Any]) -> Path:
    return append_jsonl(base / "reports" / "factors" / factor_id / "decay-monitor.jsonl", [record])


def _lineage_has_active_spec(path: Path) -> bool:
    payload = _read_json(path)
    used_specs = payload.get("used_in_specs", [])
    return any(
        isinstance(item, dict)
        and str(item.get("spec_path", "")).startswith("strategy_specs/active/")
        for item in used_specs
    )


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _parse_ts(value: str) -> datetime:
    if not value:
        return datetime.fromtimestamp(0, UTC)
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _relpath(path: Path, base: Path) -> str:
    try:
        return path.resolve().relative_to(base.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _now() -> str:
    return datetime.now(UTC).isoformat()
