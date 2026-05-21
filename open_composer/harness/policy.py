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
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
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
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
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

    # Trigger composition: default is "all" (every trigger must match).
    # Set "match: any" in YAML to activate the domain if any single trigger matches.
    # The "match" key itself is metadata, not a trigger condition.
    match_mode = str(triggers.get("match", "all")).lower()
    trigger_keys = [k for k in triggers if k != "match"]

    def _check(key: str) -> bool:
        return _check_single_trigger(key, triggers[key], spec, _get)

    if match_mode == "any":
        return any(_check(k) for k in trigger_keys)
    return all(_check(k) for k in trigger_keys)


def _check_single_trigger(key: str, value: object, spec: object, _get) -> bool:
    """Evaluate one trigger condition. Returns True if the spec satisfies it.

    Unknown trigger keys return False (strict) — adding a trigger without a handler
    here is treated as 'cannot evaluate', not 'always passes'.
    """
    if key == "timeframe":
        tf = _get("timeframe") or _get("data", {})
        if isinstance(tf, str):
            tf = [tf]
        elif hasattr(tf, "timeframe"):
            tf = [tf.timeframe]
        if not isinstance(tf, list):
            return False
        return any(t in value for t in tf)

    if key == "fill_assumption":
        exec_obj = _get("execution")
        fa = getattr(exec_obj, "fill_assumption", None) if exec_obj else None
        return fa in value

    if key == "execution_mode":
        exec_obj = _get("execution")
        mode = getattr(exec_obj, "mode", None) if exec_obj else None
        return mode in value

    if key == "symbol_patterns":
        universe = _get("universe")
        symbols: list[str] = []
        if isinstance(universe, list):
            symbols = [str(s) for s in universe]
        elif universe is not None:
            raw_syms = getattr(universe, "symbols", None) or []
            symbols = list(raw_syms)
        patterns = value if isinstance(value, list) else [value]
        return any(
            any(re.search(rf"^{pat}$", sym, re.IGNORECASE) for pat in patterns) for sym in symbols
        )

    if key == "has_adjustable_parameters":
        if not value:
            return False
        params = _get("parameters") or {}
        if not isinstance(params, dict):
            return False
        return any(isinstance(v, dict) and ("range" in v or "step" in v) for v in params.values())

    if key == "llm_review_enabled":
        llm_review = _get("llm_review")
        enabled = getattr(llm_review, "enabled", False) if llm_review else False
        return bool(enabled) == bool(value)

    if key == "required_capability_kinds":
        needed_kinds = set(value) if isinstance(value, list) else set()
        cap_obj = _get("capabilities") or {}
        found_kinds: set[str] = set()
        if isinstance(cap_obj, dict):
            for v in cap_obj.values():
                kind = getattr(v, "kind", None) or (v.get("kind") if isinstance(v, dict) else None)
                if kind:
                    found_kinds.add(kind)
        return bool(needed_kinds.intersection(found_kinds))

    if key == "broker":
        exec_obj = _get("execution")
        broker = getattr(exec_obj, "broker", None) if exec_obj else None
        return broker in value

    if key == "all_capabilities_workflow_only":
        # Requires spec_path + capability registry; only evaluated by full verify path.
        return False

    if key in {"backtest_days_lt", "trade_count_lt"}:
        # These need post-backtest evidence that is not available at plan time.
        return False

    return False


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
                lines = [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
                if not lines:
                    missing = contract.required_fields
                else:
                    first = json.loads(lines[0])
                    missing = [f for f in contract.required_fields if f not in first]
            elif contract.format == "json":
                obj = json.loads(path.read_text(encoding="utf-8"))
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
