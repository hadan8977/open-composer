from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from open_composer.config import ensure_dir, project_root, run_id
from open_composer.expressions import (
    ExpressionError,
    assert_expression_safe,
    evaluate_raw_expression,
)
from open_composer.research.factor_library import (
    factor_definition_ids,
    get_factor,
    materialize_expression,
)
from open_composer.storage import append_jsonl, write_json

MIN_OBSERVATIONS = 20


def propose_factors(
    thesis: str,
    *,
    root: Path | None = None,
    data_path: str = "data/sample/syn_daily.csv",
    base_factors: list[str] | None = None,
    max_candidates: int = 5,
    min_abs_rank_ic: float = 0.01,
    min_abs_ir: float = 0.0,
    max_abs_correlation: float = 0.70,
    use_llm: bool = False,
) -> dict[str, Any]:
    base = root or project_root()
    proposal_id = run_id("factor-proposal")
    frame = _load_frame(base, data_path)
    raw_candidates = _deterministic_candidates(thesis, max_candidates=max_candidates)
    candidates = [
        _evaluate_candidate(
            frame,
            candidate,
            root=base,
            base_factors=base_factors or [],
            min_abs_rank_ic=min_abs_rank_ic,
            min_abs_ir=min_abs_ir,
            max_abs_correlation=max_abs_correlation,
        )
        for candidate in raw_candidates
    ]
    pending = [item for item in candidates if item["status"] == "pending_review"]
    payload = {
        "proposal_id": proposal_id,
        "created_at": _now(),
        "status": "pending_review" if pending else "blocked",
        "thesis": thesis,
        "mode": "llm_requested_deterministic_fallback" if use_llm else "deterministic",
        "llm_status": (
            "not_called_default_deterministic"
            if not use_llm
            else "not_called_no_catalog_mutation_path_uses_deterministic_candidates"
        ),
        "data_path": data_path,
        "base_factors": base_factors or [],
        "gates": {
            "min_observations": MIN_OBSERVATIONS,
            "min_abs_rank_ic": min_abs_rank_ic,
            "min_abs_ir": min_abs_ir,
            "max_abs_correlation": max_abs_correlation,
        },
        "candidates": candidates,
        "pending_candidate_count": len(pending),
        "safety_note": (
            "Proposal artifacts are research-only. Approval does not edit factor_library.py "
            "or make a strategy paper-ready."
        ),
    }
    path = _proposal_path(base, proposal_id)
    write_json(path, payload)
    append_jsonl(
        base / "reports" / "factor_proposals" / "index.jsonl",
        [
            {
                "proposal_id": proposal_id,
                "created_at": payload["created_at"],
                "status": payload["status"],
                "thesis": thesis,
                "pending_candidate_count": len(pending),
                "path": _relpath(path, base),
            }
        ],
    )
    payload["path"] = _relpath(path, base)
    return payload


def approve_factor_proposal(
    proposal_id: str,
    *,
    root: Path | None = None,
    reason: str = "",
) -> dict[str, Any]:
    return _update_proposal_status(proposal_id, "approved", root=root, reason=reason)


def reject_factor_proposal(
    proposal_id: str,
    *,
    root: Path | None = None,
    reason: str = "",
) -> dict[str, Any]:
    return _update_proposal_status(proposal_id, "rejected", root=root, reason=reason)


def _evaluate_candidate(
    frame: pd.DataFrame,
    candidate: dict[str, Any],
    *,
    root: Path,
    base_factors: list[str],
    min_abs_rank_ic: float,
    min_abs_ir: float,
    max_abs_correlation: float,
) -> dict[str, Any]:
    candidate_id = str(candidate["id"])
    expression = str(candidate["expression"])
    blockers: list[str] = []
    warnings: list[str] = []
    catalog_ids = set(factor_definition_ids())
    if candidate_id in catalog_ids:
        blockers.append("duplicate_catalog_id")
    try:
        assert_expression_safe(expression)
    except Exception as exc:
        blockers.append("unsafe_expression")
        return {
            **candidate,
            "status": "rejected",
            "blockers": blockers,
            "warnings": warnings,
            "error": str(exc),
        }
    try:
        values = pd.to_numeric(evaluate_raw_expression(expression, frame), errors="coerce")
    except (ExpressionError, TypeError, ValueError) as exc:
        blockers.append("expression_evaluation_failed")
        return {
            **candidate,
            "status": "rejected",
            "blockers": blockers,
            "warnings": warnings,
            "error": str(exc),
        }
    values = values.replace([float("inf"), float("-inf")], pd.NA)
    forward_return = _forward_return(frame, 1)
    joined = pd.DataFrame({"factor": values, "forward_return": forward_return}).dropna()
    observations = int(len(joined))
    unique_values = int(values.nunique(dropna=True))
    rank_ic = _rank_ic(joined["factor"], joined["forward_return"])
    rolling_ics = _rolling_rank_ic(joined["factor"], joined["forward_return"])
    rolling_mean = float(pd.Series(rolling_ics).mean()) if rolling_ics else None
    rolling_std = float(pd.Series(rolling_ics).std(ddof=0)) if len(rolling_ics) > 1 else None
    ir = None if rolling_std in {None, 0.0} else float((rolling_mean or 0.0) / rolling_std)
    max_corr, corr_factor = _max_abs_correlation(frame, values, base_factors)
    if observations < MIN_OBSERVATIONS:
        blockers.append("insufficient_observations")
    if unique_values <= 1:
        blockers.append("zero_variance")
    if rank_ic is None or abs(rank_ic) < min_abs_rank_ic:
        blockers.append("weak_rank_ic")
    if ir is None:
        warnings.append("ir_unavailable")
        if min_abs_ir > 0:
            blockers.append("weak_ir")
    elif abs(ir) < min_abs_ir:
        blockers.append("weak_ir")
    if max_corr is not None and max_corr >= max_abs_correlation:
        blockers.append("too_correlated_with_base_factor")
    return {
        **candidate,
        "status": "rejected" if blockers else "pending_review",
        "blockers": blockers,
        "warnings": warnings,
        "metrics": {
            "observations": observations,
            "unique_values": unique_values,
            "rank_ic": rank_ic,
            "rolling_rank_ic_mean": rolling_mean,
            "rolling_rank_ic_std": rolling_std,
            "ir": ir,
            "max_abs_correlation_to_base": max_corr,
            "most_correlated_base_factor": corr_factor,
        },
    }


def _deterministic_candidates(thesis: str, *, max_candidates: int) -> list[dict[str, Any]]:
    lower = thesis.lower()
    templates: list[tuple[str, str, str, str]] = []
    if "overnight" in lower or "gap" in lower:
        templates.extend(
            [
                (
                    "overnight_gap_1",
                    "overnight_gap",
                    "open / lag(close, 1) - 1",
                    "Prior close to open gap.",
                ),
                (
                    "gap_reversal_pressure",
                    "overnight_gap",
                    "(open / lag(close, 1) - 1) * -1",
                    "Contrarian overnight gap pressure.",
                ),
            ]
        )
    if "mean" in lower or "reversion" in lower or "oversold" in lower:
        templates.extend(
            [
                (
                    "rsi_reversion_14",
                    "mean_reversion",
                    "50 - rsi(close, 14)",
                    "Distance below neutral RSI.",
                ),
                (
                    "close_sma_reversion_20",
                    "mean_reversion",
                    "sma(close, 20) / close - 1",
                    "Discount to 20-bar average.",
                ),
            ]
        )
    if "vol" in lower or "breakout" in lower:
        templates.extend(
            [
                (
                    "vol_adjusted_breakout_20",
                    "volatility",
                    "(close / sma(close, 20) - 1) / stddev(close, 20)",
                    "Trend breakout scaled by realized volatility.",
                ),
                (
                    "atr_range_pressure_14",
                    "volatility",
                    "(high - low) / atr(14)",
                    "Current range relative to ATR.",
                ),
            ]
        )
    if "regime" in lower or "risk" in lower or "defensive" in lower:
        templates.extend(
            [
                (
                    "trend_regime_50",
                    "regime",
                    "close / sma(close, 50) - 1",
                    "Intermediate trend regime.",
                ),
                (
                    "vol_regime_20",
                    "regime",
                    "stddev(close, 20)",
                    "Recent realized volatility regime.",
                ),
            ]
        )
    if "trend" in lower or "momentum" in lower or not templates:
        templates.extend(
            [
                ("trend_roc_20", "trend", "roc(close, 20)", "20-bar price momentum."),
                (
                    "sma_trend_20",
                    "trend",
                    "close / sma(close, 20) - 1",
                    "Distance above 20-bar average.",
                ),
            ]
        )
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for label, family, expression, rationale in templates:
        digest = hashlib.sha1(f"{thesis}|{expression}".encode()).hexdigest()[:8]
        candidate_id = f"proposal_{_slug(label)}_{digest}"
        if candidate_id in seen:
            continue
        seen.add(candidate_id)
        result.append(
            {
                "id": candidate_id,
                "family": family,
                "label": label.replace("_", " "),
                "expression": expression,
                "rationale": rationale,
            }
        )
        if len(result) >= max_candidates:
            break
    return result


def _max_abs_correlation(
    frame: pd.DataFrame,
    values: pd.Series,
    base_factors: list[str],
) -> tuple[float | None, str | None]:
    best_value: float | None = None
    best_factor: str | None = None
    for factor_id in base_factors:
        try:
            factor = get_factor(factor_id)
            if not factor.expression:
                continue
            expression = materialize_expression(factor, {})
            other = pd.to_numeric(evaluate_raw_expression(expression, frame), errors="coerce")
        except Exception:
            continue
        corr = _corr(values, other)
        if corr is None:
            continue
        abs_corr = abs(corr)
        if best_value is None or abs_corr > best_value:
            best_value = float(abs_corr)
            best_factor = factor_id
    return best_value, best_factor


def _update_proposal_status(
    proposal_id: str,
    status: str,
    *,
    root: Path | None,
    reason: str,
) -> dict[str, Any]:
    base = root or project_root()
    path = _proposal_path(base, proposal_id)
    if not path.exists():
        raise FileNotFoundError(f"proposal not found: {proposal_id}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    payload["status"] = status
    payload[f"{status}_at"] = _now()
    payload[f"{status}_reason"] = reason
    write_json(path, payload)
    append_jsonl(
        base / "reports" / "factor_proposals" / f"{status}-ledger.jsonl",
        [
            {
                "proposal_id": proposal_id,
                "status": status,
                "reason": reason,
                "updated_at": payload[f"{status}_at"],
                "path": _relpath(path, base),
            }
        ],
    )
    payload["path"] = _relpath(path, base)
    return payload


def _load_frame(root: Path, data_path: str) -> pd.DataFrame:
    path = root / data_path
    frame = pd.read_csv(path)
    if "timestamp" not in frame.columns:
        raise ValueError(f"{path} must include timestamp column")
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
    for column in ["open", "high", "low", "close", "volume"]:
        if column not in frame.columns:
            raise ValueError(f"{path} must include {column} column")
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    return frame


def _forward_return(frame: pd.DataFrame, horizon: int) -> pd.Series:
    close = pd.to_numeric(frame["close"], errors="coerce")
    return close.shift(-horizon) / close - 1.0


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


def _rolling_rank_ic(factor: pd.Series, forward_return: pd.Series, window: int = 20) -> list[float]:
    joined = pd.DataFrame({"factor": factor, "forward_return": forward_return}).dropna()
    values: list[float] = []
    if len(joined) < window:
        return values
    for end in range(window, len(joined) + 1):
        value = _rank_ic(
            joined["factor"].iloc[end - window : end],
            joined["forward_return"].iloc[end - window : end],
        )
        if value is not None:
            values.append(value)
    return values


def _corr(left: pd.Series, right: pd.Series) -> float | None:
    joined = pd.DataFrame({"left": left, "right": right}).dropna()
    if len(joined) < 3 or joined["left"].nunique() <= 1 or joined["right"].nunique() <= 1:
        return None
    value = joined["left"].corr(joined["right"])
    return None if pd.isna(value) else float(value)


def _proposal_path(root: Path, proposal_id: str) -> Path:
    safe_id = re.sub(r"[^A-Za-z0-9_.-]", "-", proposal_id)
    return ensure_dir(root / "reports" / "factor_proposals") / f"{safe_id}.json"


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_") or "factor"


def _relpath(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _now() -> str:
    return datetime.now(UTC).isoformat()
