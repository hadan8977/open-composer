"""Harness policy loader — reads harness/risk_domains.yaml and artifact_contracts.yaml.

Provides:
- load_risk_domains()  → dict of domain_id → RiskDomain
- detect_risk_domains(spec) → list[str]  active domain ids for a given spec
- required_artifacts_for_domains(domain_ids) → set[str]
- required_skills_for_domains(domain_ids) → set[str]
- blocking_rules_for_domains(domain_ids, pass_name) → list[str]
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path

import yaml

_HARNESS_DIR = Path(__file__).parent.parent.parent / "harness"


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class BlockingRule:
    id: str
    description: str
    blocks: str  # "research_pass" | "paper_ready_pass" | ...


@dataclass
class RiskDomain:
    id: str
    description: str
    triggers: dict
    required_skills: list[str]
    required_artifacts: list[str]
    blocking_rules: list[BlockingRule]


@dataclass
class ArtifactContract:
    name: str
    description: str
    path_template: str
    format: str
    required_fields: list[str]


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------


@cache
def load_risk_domains() -> dict[str, RiskDomain]:
    path = _HARNESS_DIR / "risk_domains.yaml"
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text())
    domains: dict[str, RiskDomain] = {}
    for domain_id, raw in (data.get("risk_domains") or {}).items():
        rules = [
            BlockingRule(
                id=r["id"],
                description=r.get("description", ""),
                blocks=r.get("blocks", ""),
            )
            for r in (raw.get("blocking_rules") or [])
        ]
        domains[domain_id] = RiskDomain(
            id=domain_id,
            description=raw.get("description", ""),
            triggers=raw.get("triggers") or {},
            required_skills=raw.get("required_skills") or [],
            required_artifacts=raw.get("required_artifacts") or [],
            blocking_rules=rules,
        )
    return domains


@cache
def load_artifact_contracts() -> dict[str, ArtifactContract]:
    path = _HARNESS_DIR / "artifact_contracts.yaml"
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text())
    contracts: dict[str, ArtifactContract] = {}
    for name, raw in (data.get("artifacts") or {}).items():
        contracts[name] = ArtifactContract(
            name=name,
            description=raw.get("description", ""),
            path_template=raw.get("path", ""),
            format=raw.get("format", ""),
            required_fields=raw.get("required_fields") or [],
        )
    return contracts


# ---------------------------------------------------------------------------
# Risk domain detection
# ---------------------------------------------------------------------------


def detect_risk_domains(spec: object, root: Path | None = None) -> list[str]:
    """Return the list of risk domain IDs active for the given StrategySpec.

    Detection is purely based on spec fields and (optionally) capability data
    already loaded into the spec. Does not run backtests or shell commands.
    """
    domains = load_risk_domains()
    active: list[str] = []

    for domain_id, domain in domains.items():
        if _domain_matches(domain, spec, root):
            active.append(domain_id)

    return active


def _domain_matches(domain: RiskDomain, spec: object, root: Path | None) -> bool:
    triggers = domain.triggers
    if not triggers:
        return False

    def _get(attr: str, default=None):
        return getattr(spec, attr, default)

    # timeframe
    if "timeframe" in triggers:
        tf = _get("timeframe") or _get("data", {})
        if isinstance(tf, str):
            tf = [tf]
        elif hasattr(tf, "timeframe"):
            tf = [tf.timeframe]
        if not isinstance(tf, list):
            tf = []
        if not any(t in triggers["timeframe"] for t in tf):
            return False

    # fill_assumption
    if "fill_assumption" in triggers:
        exec_obj = _get("execution")
        fa = getattr(exec_obj, "fill_assumption", None) if exec_obj else None
        if fa not in triggers["fill_assumption"]:
            return False

    # execution_mode
    if "execution_mode" in triggers:
        exec_obj = _get("execution")
        mode = getattr(exec_obj, "mode", None) if exec_obj else None
        if mode not in triggers["execution_mode"]:
            return False

    # symbol_patterns (universe symbols match against regex list)
    if "symbol_patterns" in triggers:
        universe = _get("universe")
        symbols: list[str] = []
        if universe is not None:
            raw_syms = getattr(universe, "symbols", None) or []
            symbols = list(raw_syms)
        patterns = triggers["symbol_patterns"]
        if not any(
            any(re.search(rf"^{pat}$", sym, re.IGNORECASE) for pat in patterns) for sym in symbols
        ):
            return False

    # has_adjustable_parameters
    if triggers.get("has_adjustable_parameters"):
        params = _get("parameters") or {}
        has_range = False
        if isinstance(params, dict):
            for v in params.values():
                if isinstance(v, dict) and ("range" in v or "step" in v):
                    has_range = True
                    break
        if not has_range:
            return False

    # llm_review_enabled
    if "llm_review_enabled" in triggers:
        llm_review = _get("llm_review")
        enabled = getattr(llm_review, "enabled", False) if llm_review else False
        if bool(enabled) != bool(triggers["llm_review_enabled"]):
            return False

    # required_capability_kinds (checks spec's declared capabilities)
    if "required_capability_kinds" in triggers:
        needed_kinds = set(triggers["required_capability_kinds"])
        cap_obj = _get("capabilities") or {}
        found_kinds: set[str] = set()
        if isinstance(cap_obj, dict):
            for v in cap_obj.values():
                kind = getattr(v, "kind", None) or (v.get("kind") if isinstance(v, dict) else None)
                if kind:
                    found_kinds.add(kind)
        if not needed_kinds.intersection(found_kinds):
            return False

    # all_capabilities_workflow_only
    if triggers.get("all_capabilities_workflow_only"):
        if root is None:
            return False
        # Full evaluation requires a spec_path; skip if unavailable
        return False

    # broker
    if "broker" in triggers:
        exec_obj = _get("execution")
        broker = getattr(exec_obj, "broker", None) if exec_obj else None
        if broker not in triggers["broker"]:
            return False

    return True


# ---------------------------------------------------------------------------
# Helpers for harness plan / verify
# ---------------------------------------------------------------------------


def required_artifacts_for_domains(domain_ids: list[str]) -> set[str]:
    domains = load_risk_domains()
    result: set[str] = set()
    for did in domain_ids:
        if did in domains:
            result.update(domains[did].required_artifacts)
    return result


def required_skills_for_domains(domain_ids: list[str]) -> set[str]:
    domains = load_risk_domains()
    result: set[str] = set()
    for did in domain_ids:
        if did in domains:
            result.update(domains[did].required_skills)
    return result


@dataclass
class ActiveBlockingRule:
    domain_id: str
    rule_id: str
    description: str
    blocks: str


def blocking_rules_for_domains(domain_ids: list[str]) -> list[ActiveBlockingRule]:
    domains = load_risk_domains()
    result: list[ActiveBlockingRule] = []
    for did in domain_ids:
        if did not in domains:
            continue
        for rule in domains[did].blocking_rules:
            result.append(
                ActiveBlockingRule(
                    domain_id=did,
                    rule_id=rule.id,
                    description=rule.description,
                    blocks=rule.blocks,
                )
            )
    return result


def artifact_path(artifact_name: str, strategy_name: str) -> Path:
    contracts = load_artifact_contracts()
    if artifact_name not in contracts:
        msg = f"Unknown artifact: {artifact_name!r}"
        raise KeyError(msg)
    template = contracts[artifact_name].path_template
    rel = template.replace("{strategy}", strategy_name)
    return Path(rel)


@dataclass
class ArtifactStatus:
    name: str
    required: bool
    path: Path
    present: bool
    schema_ok: bool
    missing_fields: list[str] = field(default_factory=list)


def check_artifact(artifact_name: str, strategy_name: str, root: Path) -> ArtifactStatus:
    """Check whether an artifact file exists and contains required fields."""
    import json

    contracts = load_artifact_contracts()
    if artifact_name not in contracts:
        return ArtifactStatus(
            name=artifact_name,
            required=True,
            path=Path("unknown"),
            present=False,
            schema_ok=False,
            missing_fields=["(contract not found)"],
        )
    contract = contracts[artifact_name]
    path = root / artifact_path(artifact_name, strategy_name)
    if not path.exists():
        return ArtifactStatus(
            name=artifact_name,
            required=True,
            path=path,
            present=False,
            schema_ok=False,
            missing_fields=contract.required_fields or [],
        )

    missing: list[str] = []
    if contract.required_fields:
        try:
            if contract.format == "jsonl":
                lines = [ln for ln in path.read_text().splitlines() if ln.strip()]
                if not lines:
                    missing = contract.required_fields
                else:
                    first = json.loads(lines[0])
                    missing = [f for f in contract.required_fields if f not in first]
            elif contract.format == "json":
                obj = json.loads(path.read_text())
                missing = [f for f in contract.required_fields if f not in obj]
        except Exception:
            missing = contract.required_fields

    return ArtifactStatus(
        name=artifact_name,
        required=True,
        path=path,
        present=True,
        schema_ok=len(missing) == 0,
        missing_fields=missing,
    )
