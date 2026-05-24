from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from open_composer.adapters.data import fetch_ohlcv, load_ohlcv_for_spec
from open_composer.config import data_feed, default_openai_model, ensure_dir, project_root
from open_composer.feature_packets import (
    FeaturePacketEvidence,
    FeaturePacketRow,
    default_materialized_feature_path,
    write_feature_packet,
)
from open_composer.models.strategy_spec import FactorConfig, StrategySpec, load_strategy_spec
from open_composer.research.llm_backends import get_backend
from open_composer.storage import append_jsonl, write_json

SCHEMA_VERSION = "2"


@dataclass(frozen=True)
class MaterializationResult:
    strategy_name: str
    factor_name: str
    prompt_hash: str
    input_view_version: int
    model: str
    packet_count: int
    cache_hits: int
    cache_misses: int
    packets_path: Path
    run_path: Path
    trial_ledger_path: Path
    skipped_for_existing: int
    errors: int


def materialize_factor(
    spec_path: Path,
    factor_name: str,
    *,
    root: Path | None = None,
    backend: str = "openai",
    refresh: bool = False,
    symbols: list[str] | None = None,
) -> MaterializationResult:
    base = root or project_root()
    spec = load_strategy_spec(spec_path)
    factor = spec.factors.get(factor_name)
    if factor is None:
        raise ValueError(f"factor not found: {factor_name}")
    if factor.source != "llm_feature":
        raise ValueError(f"factor {factor_name} is not source=llm_feature")
    if factor.path:
        raise ValueError(
            f"factor {factor_name} already points to replay packets; remove path to materialize"
        )
    _validate_materializable_factor(factor_name, factor)

    prompt_path = _resolve_path(base, str(factor.prompt_template_path))
    prompt = prompt_path.read_text(encoding="utf-8")
    prompt_hash = _hash_text(prompt)
    model = factor.model_ref or default_openai_model()
    packets_path = default_materialized_feature_path(base, spec.name, factor_name)
    out_dir = ensure_dir(packets_path.parent)
    run_path = out_dir / "materialization-run.json"
    trial_ledger_path = out_dir / "prompt-trial-ledger.jsonl"
    existing = _read_existing_keys(packets_path) if not refresh else set()
    llm = get_backend(backend)

    target_symbols = [item.upper() for item in (symbols or [spec.primary_symbol])]
    cache_hits = 0
    cache_misses = 0
    errors = 0
    packet_count = 0
    output_schema = factor.output_schema.model_dump(mode="json") if factor.output_schema else {}
    for symbol in target_symbols:
        frame = _load_symbol_frame(spec, base, symbol, refresh=refresh)
        rows = _input_rows(frame, symbol)
        for row in rows:
            input_payload = _input_payload(row, factor)
            input_hash = _hash_json(input_payload)
            key = _cache_key(
                symbol=symbol,
                visible_at=row["visible_at"],
                input_view_version=int(factor.input_view_version or 1),
                input_hash=input_hash,
                prompt_hash=prompt_hash,
                model=model,
            )
            if key in existing:
                cache_hits += 1
                continue
            cache_misses += 1
            try:
                output = llm.infer(
                    model=model,
                    prompt=prompt,
                    input_payload=input_payload,
                    output_schema=output_schema,
                )
                features = _features_from_output(output, factor)
                packet = FeaturePacketRow(
                    timestamp=row["timestamp"],
                    published_at=row["timestamp"],
                    fetched_at=datetime.now(UTC),
                    visible_at=row["visible_at"],
                    source=f"llm_materialize:{factor.input_view}",
                    symbol=symbol,
                    dedupe_key=key,
                    schema_version=SCHEMA_VERSION,
                    summary=f"Materialized {factor_name} from {factor.input_view}.",
                    model=model,
                    input_hash=input_hash,
                    prompt_hash=prompt_hash,
                    features=features,
                    evidence=FeaturePacketEvidence(
                        single_modality_baseline_metric="pending_promotion_quant_baseline",
                        marginal_lift_metric="pending_promotion_marginal_lift",
                        missing_modality_robustness="pending_promotion_missing_modality",
                        notes=(
                            "Materialized packet; promotion writes aggregate marginal evidence "
                            "for this factor."
                        ),
                    ),
                    input_view=str(factor.input_view),
                    input_view_version=factor.input_view_version,
                )
                write_feature_packet(packets_path, packet)
                append_jsonl(
                    trial_ledger_path,
                    [
                        {
                            "ts": datetime.now(UTC).isoformat(),
                            "dedupe_key": key,
                            "status": "ok",
                            "input_hash": input_hash,
                            "prompt_hash": prompt_hash,
                            "model": model,
                        }
                    ],
                )
                existing.add(key)
                packet_count += 1
            except Exception as exc:  # noqa: BLE001 - per-row materialization ledger
                errors += 1
                append_jsonl(
                    trial_ledger_path,
                    [
                        {
                            "ts": datetime.now(UTC).isoformat(),
                            "dedupe_key": key,
                            "status": "error",
                            "error": str(exc),
                            "input_hash": input_hash,
                            "prompt_hash": prompt_hash,
                            "model": model,
                        }
                    ],
                )

    result = MaterializationResult(
        strategy_name=spec.name,
        factor_name=factor_name,
        prompt_hash=prompt_hash,
        input_view_version=int(factor.input_view_version or 1),
        model=model,
        packet_count=packet_count,
        cache_hits=cache_hits,
        cache_misses=cache_misses,
        packets_path=packets_path,
        run_path=run_path,
        trial_ledger_path=trial_ledger_path,
        skipped_for_existing=cache_hits,
        errors=errors,
    )
    write_json(run_path, _result_payload(result, base))
    return result


def _validate_materializable_factor(name: str, factor: FactorConfig) -> None:
    missing = [
        field
        for field, value in {
            "input_view": factor.input_view,
            "input_view_version": factor.input_view_version,
            "prompt_template_path": factor.prompt_template_path,
            "output_schema": factor.output_schema,
            "field": factor.field,
        }.items()
        if value is None or value == ""
    ]
    if missing:
        raise ValueError(f"llm_feature factor {name} is missing: {', '.join(missing)}")


def _load_symbol_frame(
    spec: StrategySpec,
    root: Path,
    symbol: str,
    *,
    refresh: bool = False,
) -> Any:
    if spec.data.source == "sample":
        return load_ohlcv_for_spec(spec, root, refresh=refresh)
    return fetch_ohlcv(
        root=root,
        symbol=symbol,
        timeframe=spec.timeframe,
        start=None,
        end=None,
        source=spec.data.source,
        feed=spec.data.feed or data_feed(),
        use_cache=not refresh,
    )


def _input_rows(frame, symbol: str) -> list[dict[str, Any]]:
    if "timestamp" not in frame.columns:
        raise ValueError("materialization requires timestamp column")
    rows: list[dict[str, Any]] = []
    for raw in frame.tail(16).to_dict(orient="records"):
        timestamp = _timestamp(raw["timestamp"])
        rows.append(
            {
                "symbol": symbol,
                "timestamp": timestamp,
                "visible_at": timestamp,
                "ohlcv": {
                    key: raw.get(key)
                    for key in ("open", "high", "low", "close", "volume")
                    if key in raw
                },
            }
        )
    return rows


def _input_payload(row: dict[str, Any], factor: FactorConfig) -> dict[str, Any]:
    return {
        "input_view": factor.input_view,
        "input_view_version": factor.input_view_version,
        **row,
    }


def _features_from_output(output: dict[str, Any], factor: FactorConfig) -> dict[str, Any]:
    field = str(factor.field)
    features = dict(output)
    if field not in features and "score" in features:
        features[field] = features["score"]
    if field not in features:
        features[field] = factor.default
    return features


def _read_existing_keys(path: Path) -> set[str]:
    if not path.exists():
        return set()
    keys: set[str] = set()
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            try:
                raw = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(raw, dict) and raw.get("dedupe_key"):
                keys.add(str(raw["dedupe_key"]))
    return keys


def _cache_key(
    *,
    symbol: str,
    visible_at: datetime,
    input_view_version: int,
    input_hash: str,
    prompt_hash: str,
    model: str,
) -> str:
    return (
        f"llm:{symbol}:{visible_at.isoformat()}:{input_view_version}:"
        f"{input_hash}:{prompt_hash}:{model}:{SCHEMA_VERSION}"
    )


def _result_payload(result: MaterializationResult, root: Path) -> dict[str, Any]:
    return {
        "strategy_name": result.strategy_name,
        "factor_name": result.factor_name,
        "prompt_hash": result.prompt_hash,
        "input_view_version": result.input_view_version,
        "model": result.model,
        "packet_count": result.packet_count,
        "cache_hits": result.cache_hits,
        "cache_misses": result.cache_misses,
        "skipped_for_existing": result.skipped_for_existing,
        "errors": result.errors,
        "packets_path": _relpath(result.packets_path, root),
        "run_path": _relpath(result.run_path, root),
        "trial_ledger_path": _relpath(result.trial_ledger_path, root),
    }


def _timestamp(value: Any) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _hash_text(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def _hash_json(value: dict[str, Any]) -> str:
    payload = json.dumps(value, sort_keys=True, default=str)
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _resolve_path(root: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else root / path


def _relpath(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()
