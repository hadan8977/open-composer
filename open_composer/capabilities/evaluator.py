from __future__ import annotations

import math
from pathlib import Path

import pandas as pd

from open_composer.adapters.data.sample import normalize_ohlcv
from open_composer.capabilities.native_fixtures import (
    NATIVE_MARKET_SHAPES,
    evaluate_native_market_fixture,
)
from open_composer.config import ensure_dir, project_root
from open_composer.models.capability import Capability, CapabilityEvaluation
from open_composer.models.event import EventRecord
from open_composer.reports.capabilities import write_capability_report
from open_composer.storage import write_json


def evaluate_capabilities(root: Path | None = None) -> list[CapabilityEvaluation]:
    from open_composer.capabilities.registry import load_registry

    base = root or project_root()
    registry = load_registry(base)
    evaluations = [_evaluate_capability(base, capability) for capability in registry.capabilities]
    write_json(
        base / "reports" / "capabilities" / "evaluation.json",
        {"evaluations": [evaluation.model_dump(mode="json") for evaluation in evaluations]},
    )
    write_capability_report(base / "reports" / "capabilities" / "evaluation.md", evaluations)
    return evaluations


def _evaluate_capability(root: Path, capability: Capability) -> CapabilityEvaluation:
    path = root / capability.fixture
    issues: list[str] = []
    records = 0
    score_parts: list[float] = []

    if not path.exists():
        return CapabilityEvaluation(
            capability_id=capability.id,
            status=capability.status,
            records=0,
            score=0.0,
            passed=False,
            issues=[f"fixture missing: {capability.fixture}"],
        )

    data_shape = str((capability.model_extra or {}).get("data_shape") or "")
    if capability.kind == "market" and data_shape in NATIVE_MARKET_SHAPES:
        records, native_scores, native_issues = evaluate_native_market_fixture(
            root, path, data_shape
        )
        score_parts.extend(native_scores)
        issues.extend(native_issues)
    elif capability.kind == "market" and data_shape == "vendor_stock_quote_v1":
        records, quote_score_parts, quote_issues = _evaluate_stock_quote_fixture(path)
        score_parts.extend(quote_score_parts)
        issues.extend(quote_issues)
    elif capability.kind == "market" and data_shape == "vendor_stock_trade_v1":
        records, trade_scores, trade_issues = _evaluate_stock_trade_fixture(path)
        score_parts.extend(trade_scores)
        issues.extend(trade_issues)
    elif capability.kind == "market" and data_shape == "paired_eod_index_v1":
        records, paired_score_parts, paired_issues = _evaluate_paired_index_fixture(path)
        score_parts.extend(paired_score_parts)
        issues.extend(paired_issues)
    elif capability.kind == "market":
        try:
            frame = normalize_ohlcv(pd.read_csv(path))
            records = len(frame)
            score_parts.append(1.0 if records >= 5 else 0.5)
            score_parts.append(1.0 if frame["timestamp"].is_monotonic_increasing else 0.5)
            score_parts.append(
                1.0
                if frame[["open", "high", "low", "close", "volume"]].notna().all().all()
                else 0.0
            )
        except Exception as exc:
            issues.append(str(exc))
            score_parts.append(0.0)
    elif capability.kind in {"event", "macro", "news"}:
        valid, duplicates, event_issues = _evaluate_event_fixture(path)
        records = valid
        issues.extend(event_issues)
        score_parts.append(1.0 if valid > 0 else 0.0)
        score_parts.append(max(0.0, 1.0 - duplicates))
        score_parts.append(1.0 if not event_issues else 0.6)
    else:
        valid, option_issues = _evaluate_jsonl_fixture(path)
        records = valid
        issues.extend(option_issues)
        score_parts.append(1.0 if valid > 0 else 0.0)
        score_parts.append(1.0 if not option_issues else 0.6)

    score = round(sum(score_parts) / len(score_parts), 4) if score_parts else 0.0
    passed = score >= capability.min_score and not any(
        "missing" in issue.lower() for issue in issues
    )
    if not passed and not issues:
        issues.append(f"score {score:.2f} below required {capability.min_score:.2f}")
    ensure_dir(root / "reports" / "capabilities")
    return CapabilityEvaluation(
        capability_id=capability.id,
        status=capability.status,
        records=records,
        score=score,
        passed=passed,
        issues=issues,
    )


def _evaluate_stock_trade_fixture(path: Path) -> tuple[int, list[float], list[str]]:
    """Raw tape schema only; fixture validity does not certify trade signing."""
    import json

    required = {"symbol", "t", "p", "s", "x", "c", "z", "i"}
    valid, issues = 0, []
    for line_number, text in enumerate(path.read_text().splitlines(), 1):
        if not text.strip():
            continue
        try:
            row = json.loads(text)
            assert isinstance(row, dict) and required <= row.keys(), "missing trade fields"
            assert isinstance(row["symbol"], str) and row["symbol"], "missing symbol"
            assert pd.Timestamp(row["t"]).tzinfo is not None, "missing timestamp timezone"
            assert type(row["p"]) in [int, float] and math.isfinite(row["p"]) and row["p"] > 0, (
                "invalid raw price"
            )
            assert type(row["s"]) is int and row["s"] > 0, "invalid raw size"
            assert row["z"] in ["A", "B", "C"], "missing or unsupported tape"
            assert isinstance(row["x"], str) and row["x"], "missing venue"
            assert type(row["i"]) is int and row["i"] >= 0, "missing trade identity"
            assert isinstance(row["c"], list) and all(isinstance(c, str) and c for c in row["c"]), (
                "invalid conditions"
            )
            valid += 1
        except (AssertionError, ValueError, TypeError, KeyError) as exc:
            issues.append(f"line {line_number}: {exc}")
    return valid, [1.0 if valid else 0.0, 0.0 if issues else 1.0], issues


def _evaluate_stock_quote_fixture(path: Path) -> tuple[int, list[float], list[str]]:
    """Raw vendor schema only; zero/withdrawn quotes are not fill eligibility."""
    import json

    required = {"symbol", "t", "bp", "ap", "bs", "as", "bx", "ax", "c", "z"}
    valid, issues = 0, []
    for line_number, text in enumerate(path.read_text().splitlines(), 1):
        if not text.strip():
            continue
        try:
            row = json.loads(text)
            assert isinstance(row, dict) and required <= row.keys(), "missing quote fields"
            assert isinstance(row["symbol"], str) and row["symbol"], "missing symbol"
            stamp = pd.Timestamp(row["t"])
            assert stamp.tzinfo is not None, "missing timestamp timezone"
            for key in ["bp", "ap"]:
                assert (
                    type(row[key]) in [int, float] and math.isfinite(row[key]) and row[key] >= 0
                ), "invalid raw price"
            assert all(type(row[k]) is int and row[k] >= 0 for k in ["bs", "as"]), (
                "invalid raw size"
            )
            assert row["z"] in ["A", "B", "C"], "missing or unsupported tape"
            assert all(isinstance(row[k], str) and row[k] for k in ["bx", "ax"]), "missing venue"
            assert isinstance(row["c"], list) and len(row["c"]) in [1, 2], "invalid conditions"
            assert all(isinstance(c, str) and c for c in row["c"]), "invalid condition code"
            valid += 1
        except (AssertionError, ValueError, TypeError, KeyError) as exc:
            issues.append(f"line {line_number}: {exc}")
    return valid, [1.0 if valid else 0.0, 0.0 if issues else 1.0], issues


def _evaluate_paired_index_fixture(path: Path) -> tuple[int, list[float], list[str]]:
    required = {
        "timestamp",
        "vix_open",
        "vix_high",
        "vix_low",
        "vix_close",
        "vix3m_open",
        "vix3m_high",
        "vix3m_low",
        "vix3m_close",
    }
    issues: list[str] = []
    try:
        frame = pd.read_csv(path)
        missing = sorted(required - set(frame.columns))
        if missing:
            return 0, [0.0, 0.0, 0.0], ["missing columns: " + ", ".join(missing)]
        timestamps = pd.to_datetime(frame["timestamp"], utc=True, errors="raise")
        numeric = frame[sorted(required - {"timestamp"})].apply(pd.to_numeric, errors="raise")
        finite_positive = all(
            math.isfinite(float(value)) and float(value) > 0 for value in numeric.to_numpy().ravel()
        )
        valid_ohlc = finite_positive and all(
            (
                numeric[f"{prefix}_high"]
                >= numeric[[f"{prefix}_open", f"{prefix}_low", f"{prefix}_close"]].max(axis=1)
            ).all()
            and (
                numeric[f"{prefix}_low"]
                <= numeric[[f"{prefix}_open", f"{prefix}_high", f"{prefix}_close"]].min(axis=1)
            ).all()
            for prefix in ("vix", "vix3m")
        )
        unique_monotonic = timestamps.is_monotonic_increasing and not timestamps.duplicated().any()
        records = len(frame)
        if not finite_positive:
            issues.append("paired index OHLC contains non-finite or non-positive values")
        if finite_positive and not valid_ohlc:
            issues.append("paired index OHLC bounds are invalid")
        if not unique_monotonic:
            issues.append("paired index timestamps must be unique and monotonic")
        return (
            records,
            [1.0 if records >= 5 else 0.5, float(unique_monotonic), float(valid_ohlc)],
            issues,
        )
    except Exception as exc:
        return 0, [0.0, 0.0, 0.0], [str(exc)]


def _evaluate_event_fixture(path: Path) -> tuple[int, float, list[str]]:
    import json

    issues: list[str] = []
    valid = 0
    dedupe_keys: set[str] = set()
    duplicates = 0
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                event = EventRecord.model_validate(json.loads(line))
            except Exception as exc:
                issues.append(f"line {line_number}: {exc}")
                continue
            valid += 1
            if event.dedupe_key in dedupe_keys:
                duplicates += 1
            dedupe_keys.add(event.dedupe_key)
    duplicate_ratio = duplicates / valid if valid else 1.0
    return valid, duplicate_ratio, issues


def _evaluate_jsonl_fixture(path: Path) -> tuple[int, list[str]]:
    import json

    issues: list[str] = []
    valid = 0
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                raw = json.loads(line)
            except json.JSONDecodeError as exc:
                issues.append(f"line {line_number}: {exc}")
                continue
            if not isinstance(raw, dict):
                issues.append(f"line {line_number}: expected object")
                continue
            valid += 1
    return valid, issues
