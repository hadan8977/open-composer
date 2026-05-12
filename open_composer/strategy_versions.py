from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from difflib import unified_diff
from pathlib import Path

import yaml

from open_composer.config import ensure_dir, project_root
from open_composer.models.strategy_spec import StrategySpec, load_strategy_spec
from open_composer.models.strategy_version import StrategyVersion
from open_composer.storage import write_json


@dataclass(frozen=True)
class StrategyVersionDiff:
    strategy_name: str
    left_version_id: str
    right_version_id: str
    changed: bool
    diff_lines: list[str]


@dataclass(frozen=True)
class StrategyRollbackResult:
    path: Path
    version: StrategyVersion


def strategy_content_hash(spec: StrategySpec) -> str:
    payload = json.dumps(
        spec.model_dump(mode="json"),
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def strategy_version_id(spec: StrategySpec) -> str:
    return f"ver_{strategy_content_hash(spec)[:12]}"


def register_strategy_version(
    spec_path: Path | str,
    root: Path | None = None,
    *,
    parent_version_id: str | None = None,
    created_by: str = "system",
    model_ref: str | None = None,
    prompt_session_id: str | None = None,
) -> StrategyVersion:
    base = root or project_root()
    path = Path(spec_path)
    spec = load_strategy_spec(path)
    content_hash = strategy_content_hash(spec)
    version_id = f"ver_{content_hash[:12]}"
    version_root = base / "strategy_versions" / spec.name
    snapshot_path = version_root / f"{version_id}.yaml"
    manifest_path = version_root / f"{version_id}.json"
    now = datetime.now(UTC)

    ensure_dir(version_root)
    if not snapshot_path.exists():
        snapshot_path.write_text(
            yaml.safe_dump(spec.model_dump(mode="json"), sort_keys=False),
            encoding="utf-8",
        )

    source_path = _relpath(path, base)
    if manifest_path.exists():
        version = StrategyVersion.model_validate_json(manifest_path.read_text(encoding="utf-8"))
        source_paths = sorted({*version.source_paths, source_path})
        version = version.model_copy(
            update={
                "source_paths": source_paths,
                "last_seen_at": now,
                "lifecycle": spec.lifecycle,
            }
        )
    else:
        version = StrategyVersion(
            strategy_id=spec.name,
            strategy_name=spec.name,
            version_id=version_id,
            content_hash=content_hash,
            lifecycle=spec.lifecycle,
            source_paths=[source_path],
            snapshot_path=_relpath(snapshot_path, base),
            manifest_path=_relpath(manifest_path, base),
            parent_version_id=parent_version_id,
            created_by=created_by,
            created_at=now,
            first_seen_at=now,
            last_seen_at=now,
            model_ref=model_ref,
            prompt_session_id=prompt_session_id,
            symbol=spec.primary_symbol,
            timeframe=spec.timeframe,
            universe=list(spec.universe),
            factor_names=sorted(spec.factors),
            llm_feature_factor_names=sorted(
                name for name, factor in spec.factors.items() if factor.source == "llm_feature"
            ),
            feature_packet_factor_names=sorted(
                name for name, factor in spec.factors.items() if factor.source == "feature_packet"
            ),
            backend=spec.execution.backend,
            execution_mode=spec.execution.mode,
            broker=spec.execution.broker,
            data_source=spec.data.source,
            llm_review_enabled=spec.llm_review.enabled,
            required_capabilities=list(spec.required_capabilities),
        )
    write_json(manifest_path, version)
    return version


def load_strategy_versions(
    root: Path | None = None,
    strategy_name: str | None = None,
) -> list[StrategyVersion]:
    base = root or project_root()
    version_root = base / "strategy_versions"
    if strategy_name:
        paths = sorted((version_root / strategy_name).glob("*.json"))
    else:
        paths = sorted(version_root.glob("*/*.json"))
    versions = [
        StrategyVersion.model_validate_json(path.read_text(encoding="utf-8")) for path in paths
    ]
    versions.sort(key=lambda item: (item.strategy_name, item.created_at, item.version_id))
    return versions


def find_registered_strategy_version(
    root: Path | None,
    strategy_name: str,
    version_id: str,
) -> StrategyVersion | None:
    base = root or project_root()
    path = base / "strategy_versions" / strategy_name / f"{version_id}.json"
    if not path.exists():
        return None
    return StrategyVersion.model_validate_json(path.read_text(encoding="utf-8"))


def diff_strategy_versions(
    root: Path | None,
    strategy_name: str,
    left_version_id: str,
    right_version_id: str,
) -> StrategyVersionDiff:
    base = root or project_root()
    left = _require_strategy_version(base, strategy_name, left_version_id)
    right = _require_strategy_version(base, strategy_name, right_version_id)
    left_text = (base / left.snapshot_path).read_text(encoding="utf-8").splitlines()
    right_text = (base / right.snapshot_path).read_text(encoding="utf-8").splitlines()
    diff_lines = list(
        unified_diff(
            left_text,
            right_text,
            fromfile=left.snapshot_path,
            tofile=right.snapshot_path,
            lineterm="",
        )
    )
    return StrategyVersionDiff(
        strategy_name=strategy_name,
        left_version_id=left_version_id,
        right_version_id=right_version_id,
        changed=bool(diff_lines),
        diff_lines=diff_lines,
    )


def rollback_strategy_version(
    root: Path | None,
    strategy_name: str,
    version_id: str,
    *,
    created_by: str = "strategy_rollback",
) -> StrategyRollbackResult:
    base = root or project_root()
    version = _require_strategy_version(base, strategy_name, version_id)
    snapshot_path = base / version.snapshot_path
    raw = yaml.safe_load(snapshot_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        msg = f"{snapshot_path} must contain a YAML mapping"
        raise ValueError(msg)

    raw["lifecycle"] = "draft"
    raw["execution"] = {
        **raw.get("execution", {}),
        "mode": "manual_signal",
        "broker": "none",
    }
    spec = StrategySpec.model_validate(raw)
    target = base / "strategy_specs" / "drafts" / f"{spec.name}.yaml"
    ensure_dir(target.parent)
    target.write_text(
        yaml.safe_dump(spec.model_dump(mode="json"), sort_keys=False),
        encoding="utf-8",
    )
    registered = register_strategy_version(
        target,
        base,
        parent_version_id=version.version_id,
        created_by=created_by,
    )
    return StrategyRollbackResult(path=target, version=registered)


def _require_strategy_version(
    root: Path,
    strategy_name: str,
    version_id: str,
) -> StrategyVersion:
    version = find_registered_strategy_version(root, strategy_name, version_id)
    if version is None:
        raise FileNotFoundError(f"Strategy version not found: {strategy_name} {version_id}")
    return version


def _relpath(path: Path, base: Path) -> str:
    try:
        return str(path.relative_to(base))
    except ValueError:
        return str(path)
