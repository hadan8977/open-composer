from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import yaml

from open_composer.config import ensure_dir, project_root
from open_composer.models.strategy_spec import StrategySpec, load_strategy_spec
from open_composer.paper_readiness import (
    assess_paper_strategy_readiness_for_spec,
    format_paper_readiness_blockers,
    write_paper_readiness_report,
)
from open_composer.strategy_versions import register_strategy_version

Lifecycle = Literal["draft", "approved", "active", "retired"]


@dataclass(frozen=True)
class StrategyListing:
    name: str
    lifecycle: Lifecycle
    path: Path
    execution_mode: str
    broker: str
    data_source: str


def list_strategies(root: Path | None = None) -> list[StrategyListing]:
    base = root or project_root()
    listings: list[StrategyListing] = []
    for lifecycle in ["drafts", "approved", "active", "retired"]:
        for path in sorted((base / "strategy_specs" / lifecycle).glob("*.yaml")):
            spec = load_strategy_spec(path)
            listings.append(
                StrategyListing(
                    name=spec.name,
                    lifecycle=spec.lifecycle,
                    path=path,
                    execution_mode=spec.execution.mode,
                    broker=spec.execution.broker,
                    data_source=spec.data.source,
                )
            )
    return listings


def approve_strategy(spec_path: Path, root: Path | None = None) -> Path:
    spec = load_strategy_spec(spec_path)
    parent = register_strategy_version(spec_path, root, created_by="approve_parent")
    raw = spec.model_dump(mode="json")
    raw["lifecycle"] = "approved"
    raw["execution"] = {
        **raw["execution"],
        "mode": "manual_signal",
        "broker": "none",
    }
    path = _write_lifecycle_spec(raw, "approved", root)
    register_strategy_version(
        path,
        root,
        parent_version_id=parent.version_id,
        created_by="strategy_approve",
    )
    return path


def activate_strategy(
    spec_path: Path,
    root: Path | None = None,
    paper_auto: bool = False,
    allow_paper_auto: bool = False,
    data_source: Literal["keep", "sample", "alpaca", "longbridge"] = "keep",
    enforce_paper_readiness: bool = False,
) -> Path:
    base = root or project_root()
    if paper_auto and not allow_paper_auto:
        raise ValueError("paper_auto activation requires --allow-paper-auto")
    spec = load_strategy_spec(spec_path)
    parent = register_strategy_version(spec_path, base, created_by="activate_parent")
    raw = spec.model_dump(mode="json")
    raw["lifecycle"] = "active"
    if paper_auto:
        raw["execution"] = {
            **raw["execution"],
            "backend": "nautilus_trader",
            "mode": "paper_auto",
            "broker": "alpaca_paper",
        }
    else:
        raw["execution"] = {**raw["execution"], "mode": "manual_signal", "broker": "none"}
    if data_source != "keep":
        raw["data"] = {**raw["data"], "source": data_source}
        if data_source in {"alpaca", "longbridge"}:
            raw["data"]["path"] = None
            raw["data"]["symbol"] = spec.primary_symbol
    if paper_auto and enforce_paper_readiness:
        candidate = StrategySpec.model_validate(raw)
        report = assess_paper_strategy_readiness_for_spec(candidate, base)
        write_paper_readiness_report(
            report,
            base,
            output_path=base
            / "reports"
            / "paper"
            / "readiness"
            / f"{candidate.name}.activation_candidate.json",
        )
        if not report.ready:
            raise ValueError(format_paper_readiness_blockers(report))
    path = _write_lifecycle_spec(raw, "active", base)
    register_strategy_version(
        path,
        base,
        parent_version_id=parent.version_id,
        created_by="strategy_activate",
    )
    return path


def disable_strategy(name_or_path: str | Path, root: Path | None = None) -> Path:
    base = root or project_root()
    active_path = _resolve_strategy_path(name_or_path, base, preferred_lifecycle="active")
    spec = load_strategy_spec(active_path)
    parent = register_strategy_version(active_path, base, created_by="disable_parent")
    raw = spec.model_dump(mode="json")
    raw["lifecycle"] = "retired"
    raw["execution"] = {**raw["execution"], "mode": "manual_signal", "broker": "none"}
    retired_path = _write_lifecycle_spec(raw, "retired", base)
    register_strategy_version(
        retired_path,
        base,
        parent_version_id=parent.version_id,
        created_by="strategy_disable",
    )
    if active_path.exists():
        active_path.unlink()
    return retired_path


def resolve_strategy_path(name_or_path: str | Path, root: Path | None = None) -> Path:
    return _resolve_strategy_path(name_or_path, root or project_root())


def _write_lifecycle_spec(raw: dict, folder: str, root: Path | None = None) -> Path:
    base = root or project_root()
    spec = StrategySpec.model_validate(raw)
    path = base / "strategy_specs" / folder / f"{spec.name}.yaml"
    ensure_dir(path.parent)
    path.write_text(yaml.safe_dump(spec.model_dump(mode="json"), sort_keys=False), encoding="utf-8")
    load_strategy_spec(path)
    return path


def _resolve_strategy_path(
    name_or_path: str | Path,
    root: Path,
    preferred_lifecycle: str | None = None,
) -> Path:
    value = Path(name_or_path)
    if value.exists():
        return value
    folders = ["active", "approved", "drafts", "retired"]
    if preferred_lifecycle:
        folders = [preferred_lifecycle, *[item for item in folders if item != preferred_lifecycle]]
    for folder in folders:
        candidate = root / "strategy_specs" / folder / f"{name_or_path}.yaml"
        if candidate.exists():
            return candidate
    raise FileNotFoundError(f"StrategySpec not found: {name_or_path}")
