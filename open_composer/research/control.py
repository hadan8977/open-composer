from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from open_composer.config import ensure_dir, project_root
from open_composer.models.strategy_spec import load_strategy_spec
from open_composer.research.metadata import workspace_relative_path
from open_composer.strategy_versions import strategy_content_hash

MAX_MEMORY_BYTES = 1024


@dataclass(frozen=True)
class ResearchControlResult:
    strategy_name: str
    state_path: Path
    memory_path: Path
    state: dict[str, Any]
    memory_packet: str


def update_research_control(
    spec: Path | str,
    root: Path | None = None,
    *,
    max_memory_bytes: int = MAX_MEMORY_BYTES,
) -> ResearchControlResult:
    """Build the compact research control state and LLM memory packet.

    The controller is intentionally a reducer over existing evidence. It does
    not run backtests, create strategy variants, or turn statistical diagnostics
    into early-stage hard gates.
    """
    base = root or project_root()
    spec_path = Path(spec)
    strategy = load_strategy_spec(spec_path)
    control_dir = ensure_dir(base / "reports" / "research" / "control")
    evidence = _collect_evidence(base, strategy.name)
    state = _build_state(base, spec_path, strategy, evidence)
    memory_packet = _memory_packet(state, max_bytes=max_memory_bytes)

    state_path = control_dir / f"{strategy.name}-state.json"
    memory_path = control_dir / f"{strategy.name}-memory.md"
    state["memory_packet_path"] = workspace_relative_path(memory_path, base)
    state_path.write_text(
        json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    memory_path.write_text(memory_packet, encoding="utf-8")
    return ResearchControlResult(
        strategy_name=strategy.name,
        state_path=state_path,
        memory_path=memory_path,
        state=state,
        memory_packet=memory_packet,
    )


def load_memory_packet(strategy_name: str, root: Path | None = None) -> str | None:
    base = root or project_root()
    path = base / "reports" / "research" / "control" / f"{strategy_name}-memory.md"
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8").strip()
    return text or None


def _collect_evidence(root: Path, strategy_name: str) -> dict[str, Any]:
    return {
        "parameter_sweep": _read_json(
            root / "reports" / "research" / f"{strategy_name}-parameter-sweep.json"
        ),
        "research_report": _read_json(
            root / "reports" / "research" / f"{strategy_name}-research-report.json"
        ),
        "promotion": _read_json(root / "reports" / "research" / f"{strategy_name}-promotion.json"),
        "harness_verify": _read_json(
            root / "reports" / "harness" / "verify" / f"{strategy_name}.json"
        ),
        "harness_runs": _read_jsonl(
            root / "reports" / "research" / "harness-runs.jsonl", strategy_name
        ),
        "router_target_weights": _read_json(
            root / "reports" / "execution" / f"{strategy_name}-target-weights.json"
        ),
        "router_observation": _read_json(
            root / "reports" / "execution" / f"{strategy_name}-execution-observation.json"
        ),
        "router_cost_stress": _read_json(
            root / "reports" / "research" / f"{strategy_name}-router-cost-stress.json"
        ),
        "router_data_evidence": _read_json(
            root / "reports" / "research" / f"{strategy_name}-router-data-evidence.json"
        ),
        "short_exposure_policy": _read_json(
            root
            / "reports"
            / "harness"
            / "execution"
            / f"{strategy_name}-short-exposure-policy.json"
        ),
    }


def _build_state(
    root: Path,
    spec_path: Path,
    strategy: Any,
    evidence: dict[str, Any],
) -> dict[str, Any]:
    raw_sweep = evidence.get("parameter_sweep")
    raw_report = evidence.get("research_report")
    raw_verify = evidence.get("harness_verify")
    sweep = raw_sweep if isinstance(raw_sweep, dict) else {}
    report = raw_report if isinstance(raw_report, dict) else {}
    verify = raw_verify if isinstance(raw_verify, dict) else {}
    promotion = evidence.get("promotion") if isinstance(evidence.get("promotion"), dict) else {}
    router_state = _router_state(evidence)
    short_state = _dict(evidence.get("short_exposure_policy"))
    research_design = _research_design_state(strategy)

    candidates = _list(sweep.get("candidates"))
    selected = _dict(sweep.get("selection_decision")).get("selected_candidate")
    if not isinstance(selected, dict) and candidates:
        selected = candidates[0]

    blocked_items = _blocked_items(report, verify, promotion)
    warning_items = _warning_items(sweep, report, promotion)
    failed_configurations = _failed_configurations(candidates, selected)
    effective_combinations = _effective_combinations(selected)
    next_actions = _next_actions(
        blocked_items=blocked_items,
        warning_items=warning_items,
        failed_configurations=failed_configurations,
        effective_combinations=effective_combinations,
        sweep=sweep,
        verify=verify,
        router_state=router_state,
        short_state=short_state,
        research_design=research_design,
    )

    return {
        "schema_version": "1",
        "generated_at": datetime.now(UTC).isoformat(),
        "strategy_name": strategy.name,
        "source_spec_path": workspace_relative_path(spec_path, root),
        "spec_hash": strategy_content_hash(strategy),
        "objective": _objective(strategy, report),
        "current_best": _current_best(selected),
        "router_state": router_state,
        "short_state": short_state,
        "data_acquisition_tier": _data_acquisition_tier(strategy, router_state, promotion),
        "research_design": research_design,
        "effective_combinations": effective_combinations,
        "failed_configurations": failed_configurations,
        "blocked_items": blocked_items,
        "warning_items": warning_items,
        "next_actions": next_actions,
        "controller_rules": [
            "Reuse existing research and harness evidence before proposing a new change.",
            "Change at most one or two strategic variables per generation loop.",
            (
                "Do not globally reject a single factor; only avoid context-specific "
                "failed combinations."
            ),
            (
                "Treat multiple-testing and regime diagnostics as warnings during "
                "exploration and gates near promotion."
            ),
            "Prefer fixing blocked evidence and path issues before adding new strategy complexity.",
        ],
        "source_artifacts": _source_artifacts(root, strategy.name),
    }


def _memory_packet(state: dict[str, Any], *, max_bytes: int) -> str:
    lines = [
        f"# Research Memory: {state['strategy_name']}",
        f"- Objective: {_clip(str(state.get('objective') or ''), 160)}",
    ]
    best = _dict(state.get("current_best"))
    if best:
        lines.append(
            "- Current best: "
            + _clip(
                (
                    f"{best.get('candidate_name')} score={best.get('score')} "
                    f"params={best.get('params')}"
                ),
                220,
            )
        )
    blocked = _list(state.get("blocked_items"))
    if blocked:
        lines.append("- Fix first: " + _clip("; ".join(str(item) for item in blocked[:3]), 220))
    router = _dict(state.get("router_state"))
    if router:
        lines.append(
            "- Router: "
            + _clip(
                (
                    f"substate={router.get('execution_substate')} "
                    f"latest={router.get('latest_rebalance_session')} "
                    f"orders={router.get('latest_order_required_intents')}"
                ),
                180,
            )
        )
    tier = state.get("data_acquisition_tier")
    if tier:
        lines.append(f"- Data tier: {tier}")
    failures = _list(state.get("failed_configurations"))
    if failures:
        lines.append(
            "- Avoid repeating: "
            + _clip("; ".join(_failure_line(item) for item in failures[:3]), 240)
        )
    effective = _list(state.get("effective_combinations"))
    if effective:
        lines.append(
            "- Preserve/test around: "
            + _clip("; ".join(_effective_line(item) for item in effective[:2]), 220)
        )
    actions = _list(state.get("next_actions"))
    if actions:
        lines.append("- Next: " + _clip("; ".join(str(item) for item in actions[:4]), 260))
    lines.append(
        "- Control: use evidence first, change <=2 variables, no global factor bans, "
        "warn not hard-block early diagnostics."
    )
    text = "\n".join(lines).strip() + "\n"
    while len(text.encode("utf-8")) > max_bytes and len(lines) > 3:
        lines.pop(-2)
        text = "\n".join(lines).strip() + "\n"
    if len(text.encode("utf-8")) > max_bytes:
        encoded = text.encode("utf-8")[: max(max_bytes - 4, 0)]
        text = encoded.decode("utf-8", errors="ignore").rstrip() + "\n"
    return text


def _blocked_items(
    report: dict[str, Any],
    verify: dict[str, Any],
    promotion: dict[str, Any],
) -> list[str]:
    items: list[str] = []
    items.extend(str(item) for item in _list(report.get("blocked_items")))
    for artifact in _list(verify.get("artifacts")):
        if not isinstance(artifact, dict):
            continue
        if not artifact.get("present") or not artifact.get("schema_ok"):
            name = artifact.get("name", "unknown_artifact")
            missing = artifact.get("missing_fields") or []
            detail = f"{name}:missing" if not artifact.get("present") else f"{name}:schema"
            if missing:
                detail += f"({','.join(str(item) for item in missing[:3])})"
            items.append(detail)
    for blocker in _list(_dict(promotion.get("five_pass_checks")).get("blockers")):
        items.append(str(blocker))
    return _dedupe(items)[:8]


def _warning_items(
    sweep: dict[str, Any],
    report: dict[str, Any],
    promotion: dict[str, Any],
) -> list[str]:
    warnings = [str(item) for item in _list(report.get("warning_items"))]
    warnings.extend(
        str(item)
        for item in _list(_dict(sweep.get("selection_decision")).get("promotion_blockers"))
    )
    stability = _dict(sweep.get("stability"))
    pbo = stability.get("pbo_proxy")
    if isinstance(pbo, int | float) and not isinstance(pbo, bool) and pbo >= 0.5:
        warnings.append(f"high_pbo_proxy={pbo:.2f}")
    if promotion and promotion.get("status") not in (None, "ok"):
        warnings.append(f"promotion_status={promotion.get('status')}")
    return _dedupe(warnings)[:8]


def _failed_configurations(
    candidates: list[Any],
    selected: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    selected_name = selected.get("strategy_name") if isinstance(selected, dict) else None
    rows: list[dict[str, Any]] = []
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        if candidate.get("strategy_name") == selected_name:
            continue
        flags = [str(item) for item in _list(candidate.get("quality_flags"))]
        metrics = _dict(candidate.get("metrics"))
        score = candidate.get("score")
        is_weak = bool(flags) or _number(score) is None or (_number(score) or 0) <= 0
        if not is_weak:
            continue
        rows.append(
            {
                "candidate_name": candidate.get("strategy_name"),
                "params": _dict(candidate.get("params")),
                "reason": _failure_reason(flags, metrics, score),
                "metrics": _compact_metrics(metrics),
            }
        )
    return rows[:5]


def _effective_combinations(selected: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(selected, dict):
        return []
    metrics = _dict(selected.get("metrics"))
    return [
        {
            "candidate_name": selected.get("strategy_name"),
            "params": _dict(selected.get("params")),
            "reason": (
                "current best in latest available sweep; still requires OOS, walk-forward, "
                "cost, benchmark, and paper-readiness evidence"
            ),
            "metrics": _compact_metrics(metrics),
        }
    ]


def _next_actions(
    *,
    blocked_items: list[str],
    warning_items: list[str],
    failed_configurations: list[dict[str, Any]],
    effective_combinations: list[dict[str, Any]],
    sweep: dict[str, Any],
    verify: dict[str, Any],
    router_state: dict[str, Any],
    short_state: dict[str, Any],
    research_design: dict[str, Any],
) -> list[str]:
    actions: list[str] = []
    if blocked_items:
        actions.append("clear blocked harness/research evidence before adding strategy complexity")
    if not sweep:
        actions.append("run a bounded parameter sweep only after defining a small search space")
    if effective_combinations:
        actions.append(
            "test a narrow neighbor around the current best instead of restarting the design"
        )
    if failed_configurations:
        actions.append(
            "avoid repeating failed parameter combinations unless a new filter or regime condition "
            "changes the context"
        )
    if warning_items:
        actions.append(
            "treat overfit, sample, and promotion warnings as diagnostics during exploration"
        )
    if _dict(verify).get("overall") == "ok":
        actions.append("move toward promotion diagnostics rather than broad exploration")
    if router_state and router_state.get("execution_substate") != "observation_only":
        actions.append("refresh router target weights and execution observation")
    if router_state and not router_state.get("latest_rebalance_session"):
        actions.append("refresh router target weights and execution observation")
    if short_state and short_state.get("paper_auto_default") == "blocked":
        actions.append("resolve short-selling broker and borrow evidence before paper")
    if research_design and research_design.get("selection_objective"):
        actions.append("align next trial with research design selection objective")
    return _dedupe(actions)[:5]


def _current_best(selected: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(selected, dict):
        return None
    return {
        "candidate_name": selected.get("strategy_name"),
        "rank": selected.get("rank"),
        "score": selected.get("score"),
        "params": _dict(selected.get("params")),
        "metrics": _compact_metrics(_dict(selected.get("metrics"))),
        "quality_flags": [str(item) for item in _list(selected.get("quality_flags"))],
    }


def _source_artifacts(root: Path, strategy_name: str) -> dict[str, str | None]:
    paths = {
        "parameter_sweep": root / "reports" / "research" / f"{strategy_name}-parameter-sweep.json",
        "research_report": root / "reports" / "research" / f"{strategy_name}-research-report.json",
        "promotion": root / "reports" / "research" / f"{strategy_name}-promotion.json",
        "harness_verify": root / "reports" / "harness" / "verify" / f"{strategy_name}.json",
        "harness_runs": root / "reports" / "research" / "harness-runs.jsonl",
        "router_target_weights": root
        / "reports"
        / "execution"
        / f"{strategy_name}-target-weights.json",
        "router_observation": root
        / "reports"
        / "execution"
        / f"{strategy_name}-execution-observation.json",
        "router_cost_stress": root
        / "reports"
        / "research"
        / f"{strategy_name}-router-cost-stress.json",
        "router_data_evidence": root
        / "reports"
        / "research"
        / f"{strategy_name}-router-data-evidence.json",
    }
    return {
        key: workspace_relative_path(path, root) if path.exists() else None
        for key, path in paths.items()
    }


def _objective(strategy: Any, report: dict[str, Any]) -> str:
    design = _research_design_state(strategy)
    if design.get("selection_objective"):
        return str(design["selection_objective"])
    brief = _dict(report.get("research_brief"))
    if brief.get("objective"):
        return str(brief["objective"])
    intent = getattr(getattr(strategy, "notes", None), "intent", "") or getattr(
        strategy, "description", ""
    )
    return str(
        intent or f"Research {strategy.name} efficiently with bounded evidence-driven iterations."
    )


def _router_state(evidence: dict[str, Any]) -> dict[str, Any]:
    observation = _dict(evidence.get("router_observation"))
    if not observation:
        target = _dict(evidence.get("router_target_weights"))
        if not target:
            return {}
        summary = _dict(target.get("summary"))
        return {
            "execution_substate": "observation_only",
            "route_label": target.get("route_label"),
            "latest_rebalance_session": None,
            "latest_order_required_intents": summary.get("order_required_intents"),
            "target_weight_summary": summary,
            "blockers": [],
        }
    return {
        "execution_substate": observation.get("execution_substate"),
        "route_label": observation.get("route_label"),
        "latest_rebalance_session": observation.get("latest_rebalance_session"),
        "latest_order_required_intents": observation.get("latest_order_required_intents"),
        "blockers": _list(observation.get("blockers")),
        "warnings": _list(observation.get("warnings")),
    }


def _research_design_state(strategy: Any) -> dict[str, Any]:
    design = getattr(strategy, "research_design", None)
    if design is not None:
        return design.model_dump(mode="json")
    notes = getattr(strategy, "notes", None)
    if notes is None:
        return {}
    raw = notes.model_dump(mode="json").get("research_design")
    if not isinstance(raw, dict):
        return {}
    return {
        "parameter_space": raw.get("parameter_ranges", {}),
        "candidate_budget": raw.get("candidate_cap"),
        "selection_objective": raw.get("objective", ""),
        "anti_overfit_notes": raw.get("anti_overfit_notes", []),
        "validation_plan": raw.get("validation_plan", []),
    }


def _data_acquisition_tier(
    strategy: Any,
    router_state: dict[str, Any],
    promotion: dict[str, Any],
) -> str | None:
    assumptions = getattr(strategy, "data_assumptions", None)
    explicit = getattr(assumptions, "acquisition_tier", None) if assumptions else None
    if explicit:
        return str(explicit)
    if promotion.get("evidence_acquisition_tier"):
        return str(promotion["evidence_acquisition_tier"])
    target_summary = _dict(router_state.get("target_weight_summary"))
    if target_summary.get("acquisition_tier"):
        return str(target_summary["acquisition_tier"])
    return None


def _failure_reason(flags: list[str], metrics: dict[str, Any], score: Any) -> str:
    if flags:
        return "quality_flags=" + ",".join(flags[:3])
    sharpe = _number(metrics.get("sharpe_ratio"))
    trades = _number(metrics.get("trades"))
    if sharpe is not None and sharpe <= 0:
        return f"non_positive_sharpe={sharpe}"
    if trades is not None and trades <= 0:
        return "no_trades"
    return f"weak_score={score}"


def _failure_line(item: Any) -> str:
    if not isinstance(item, dict):
        return str(item)
    return f"{item.get('params')} => {item.get('reason')}"


def _effective_line(item: Any) -> str:
    if not isinstance(item, dict):
        return str(item)
    return f"{item.get('params')} ({item.get('reason')})"


def _compact_metrics(metrics: dict[str, Any]) -> dict[str, Any]:
    keys = ["total_return_pct", "alpha_vs_buy_hold_pct", "sharpe_ratio", "signals", "trades"]
    return {key: metrics.get(key) for key in keys if key in metrics}


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _read_jsonl(path: Path, strategy_name: str) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    for line in lines:
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict) and row.get("strategy_name") == strategy_name:
            rows.append(row)
    return rows[-10:]


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    return None


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for item in items:
        if item and item not in seen:
            seen.add(item)
            output.append(item)
    return output


def _clip(value: str, limit: int) -> str:
    return value if len(value) <= limit else value[: max(limit - 3, 0)].rstrip() + "..."
