"""Generate a compliant single-mechanism research-iteration dossier skeleton.

Why: `open_composer/research/iteration_dossier.py::_campaign_requirement_blockers`
requires every iteration created after 2026-08-15 to bind a full research
campaign contract (hypothesis tree, branch quotas, candidate blueprints,
visibility partitions, exposure budgets -- see `AGENTS.md` Breadth Campaign
Governance) before `oc research iteration validate` will pass. That machinery
is the right tool for a breadth-first multi-branch discovery campaign; it is
disproportionate for a single preregistered mechanism with a small, fixed
parameter grid and no branching. Step 10 (see
docs/plan-step-10-mechanism-supplementation-2026-09-03.zh.md section 3.1) adds
a narrow, structural exemption for that case: `_lightweight_single_mechanism_exempt`
grants it only when the search-space payload is a single path, a small fixed
budget (<=24), carries no campaign fields at all, and declares a preregistered
candidate manifest -- never from the boolean attestation alone. This script
is the "make it actually lightweight" half of that change: it turns a small
input JSON into the compliant file set the gate still requires (candidate
manifest, cost table, data-feasibility report, and the four narrative
dossier files), so a single-mechanism iteration does not need campaign
machinery to reach `oc research iteration validate <iter_id> --stage
pre-backtest` returning `status: ok`.

What this script does NOT do: it does not invent or edit the StrategySpec
that represents the mechanism family. The caller must already have a spec
(see `strategy_specs/drafts/goal_first_w5_qqq_momentum_family.yaml` for a
worked example) whose `research_design.iter_id`, `.candidate_manifest_path`,
and `.data_feasibility_path` already match the canonical paths this script
will use (`reports/research/iterations/<iter_id>/{candidate-manifest,
data-feasibility}.json`). Every preregistered candidate in the grid shares
that one spec_path -- the manifest records each candidate's specific
parameter values in an informational `parameters` field, since the actual
grid is applied by an evaluation script (e.g.
scripts/evaluate_beta_exposure_family_sip.py), not by generating one spec
file per grid point. Nothing here authorizes a backtest, promotion, or paper
order; it only produces the preregistration artifacts and self-checks that
`oc research iteration validate --stage pre-backtest` reports `ok`.

Usage:
    uv run python scripts/new_lightweight_iteration.py <config.json> [--overwrite]

See `_EXAMPLE_CONFIG` below for the input schema, or run with --print-example.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from open_composer.config import project_root
from open_composer.models.strategy_spec import load_strategy_spec
from open_composer.research.design_contract import research_design_mapping
from open_composer.research.iteration_dossier import (
    candidate_authorization_binding_sha256,
    init_iteration_dossier,
    validate_iteration_dossier,
)
from open_composer.strategy_versions import strategy_content_hash

_CONTRACT_GROUPS = ("data", "features", "labels", "validation", "costs", "benchmarks")

_EXAMPLE_CONFIG: dict[str, Any] = {
    "iter_id": "step10_example_single_mechanism_r1",
    "strategy_name": "example_strategy_family",
    "representative_spec_path": "strategy_specs/drafts/example_strategy_family.yaml",
    "path_name": "example_mechanism",
    "hypothesis_id": "H1",
    "objective": "One-sentence research objective.",
    "benchmark_family": ["same_symbol_buy_and_hold", "cash_proxy_bil"],
    "candidates": [
        {"candidate_id": "C01", "parameters": {"lookback_days": 100}},
        {"candidate_id": "C02", "parameters": {"lookback_days": 200}},
    ],
    "cost_table": {"base_cost_bps": 5, "stress_cost_bps": 20},
    "sources": [
        {
            "claim_id": "example_claim_1",
            "url": "https://example.com/paper",
            "published_or_updated_at": "2025-01-01",
            "source_type": "paper",
            "credibility": "high",
            "core_claim": "...",
            "project_applicability": "...",
            "reflection": "...",
        }
    ],
    "topic_coverage": ["a", "b", "c", "d", "e", "f"],
    "hypothesis": {
        "statement": "...",
        "failure_mode": "...",
        "measurement": "...",
        "stop_pivot": "...",
    },
    "decision": {
        "path": "...",
        "decision": "pending",
        "reason": "...",
        "next_iteration_suggestion": "...",
    },
}


#: Step 11 plan section 3.5's frozen cost assumption, used as the cost_table
#: fallback for --from-ledger when a ledger row does not itself carry
#: cost_bps_per_side/stress_cost_bps_per_side (the ledger schema records
#: metrics and gate results, not every ExperimentConfig field verbatim --
#: see reports/research/control/step11-2026-09-06-progress.md).
_STEP11_DEFAULT_COST_TABLE = {
    "base_cost_bps": 10.0,
    "stress_cost_bps": 25.0,
    "source": "docs/plan-step-11-ml-first-loop-2026-09-06.zh.md section 3.5 (frozen default)",
}
#: Cross-sectional analogue of the standard benchmark family (AGENTS.md:
#: "same-symbol buy-and-hold, equal-weight universe, market proxy,
#: sector/theme proxy, cash proxy, ex-post best symbol") -- there is no
#: single "same symbol" for a top-K rotating book, so the universe
#: equal-weight benchmark stands in for it; sector/theme proxy is omitted
#: (no sector map registered for this universe, an already-recorded gap in
#: paper_readiness._portfolio_risk_check's details).
_STEP11_CROSS_SECTIONAL_BENCHMARK_FAMILY = [
    "universe_equal_weight",
    "market_proxy_spy",
    "cash_proxy_bil",
]


def _fail(message: str) -> None:
    raise SystemExit(f"new_lightweight_iteration: {message}")


def _load_ledger_experiment(root: Path, experiment_id: str) -> dict[str, Any]:
    ledger_path = root / "reports" / "research" / "ledger" / "experiments.jsonl"
    if not ledger_path.is_file():
        _fail(f"no experiment ledger at {_relpath(ledger_path, root)}")
    matches = []
    for line_number, line in enumerate(ledger_path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            _fail(f"{_relpath(ledger_path, root)}:{line_number} is not valid JSON: {exc}")
        if isinstance(row, dict) and row.get("experiment_id") == experiment_id:
            matches.append(row)
    if not matches:
        _fail(
            f"no ledger row with experiment_id={experiment_id!r} in {_relpath(ledger_path, root)}"
        )
    # _append_ledger dedupes on (config_hash, family), so more than one row
    # sharing an experiment_id would mean the ledger itself is inconsistent
    # -- surface that loudly rather than silently picking one.
    if len(matches) > 1:
        _fail(f"ledger has {len(matches)} rows with experiment_id={experiment_id!r}; expected 1")
    return matches[0]


def config_from_ledger(
    *,
    root: Path,
    experiment_id: str,
    iter_id: str,
    strategy_name: str,
    representative_spec_path: str,
    sources: list[dict[str, Any]] | None,
    topic_coverage: list[str] | None,
    source_cards_path: str | None,
) -> dict[str, Any]:
    """Build a ``new_lightweight_iteration.py`` input config from a real
    ``reports/research/ledger/experiments.jsonl`` row instead of hand-typed
    JSON (Step 11 Wave C item 4: promote the current best-of-chain ledger
    experiment through the standard preregistration path). Every field below
    is either read directly off the ledger row or is this repo's
    already-frozen Step 11 default (cited, not guessed) -- ``sources``/
    ``topic_coverage``/``source_cards_path`` are the one part this function
    deliberately does NOT fabricate: research-stage source-card exemption
    (plan section 1) does not extend to this promotion step, so the caller
    must supply real ones or this function fails closed (see ``main()``).
    """
    row = _load_ledger_experiment(root, experiment_id)
    family = str(row.get("family") or "unknown_family")
    model_kind = str(row.get("model_kind") or "unknown_model")
    feature_set = str(row.get("feature_set") or "unknown_feature_set")
    top_k = row.get("top_k")
    hedge = str(row.get("hedge") or "none")
    label_horizon_days = row.get("label_horizon_days")
    long_only = row.get("long_only") or {}
    long_gates = long_only.get("gate_results") or {}
    gate_pass_count = sum(1 for value in long_gates.values() if value is True)
    gate_total = len(long_gates) or 8
    verdict_summary = (
        f"long_only gates {gate_pass_count}/{gate_total} pass "
        f"(all_gates_pass={long_only.get('all_gates_pass')}); "
        f"recorded_at={row.get('recorded_at')}; "
        f"tearsheet={row.get('tearsheet_path')}; mlflow_run_id={row.get('mlflow_run_id')}"
    )
    candidate_parameters = {
        "family": family,
        "model_kind": model_kind,
        "feature_set": feature_set,
        "label_horizon_days": label_horizon_days,
        "top_k": top_k,
        "hedge": hedge,
        "config_hash": row.get("config_hash"),
    }
    return {
        "iter_id": iter_id,
        "strategy_name": strategy_name,
        "representative_spec_path": representative_spec_path,
        "path_name": family,
        "hypothesis_id": "H1_ledger_best_of_chain",
        "objective": (
            f"Promote ledger experiment_id={experiment_id} (family={family}, "
            f"model_kind={model_kind}) -- the current best-of-chain Step 11 baseline "
            "-- into a model_ranking_portfolio StrategySpec for observation-mode paper "
            "connection (no order submission this round)."
        ),
        "benchmark_family": list(_STEP11_CROSS_SECTIONAL_BENCHMARK_FAMILY),
        "candidates": [{"candidate_id": experiment_id, "parameters": candidate_parameters}],
        "cost_table": dict(_STEP11_DEFAULT_COST_TABLE),
        "sources": sources or [],
        "topic_coverage": topic_coverage or [],
        "hypothesis": {
            "statement": (
                f"{family}/{model_kind} ranks the PIT top-1500-ADV universe and holds the "
                f"top {top_k} equal-weight; it should beat the equal-weight-universe and "
                "market-proxy benchmarks after costs."
            ),
            "failure_mode": (
                "Fails to clear the unlevered-family-paper-tier-gates.json contract "
                f"out-of-sample after costs -- verdict: {verdict_summary}"
            ),
            "measurement": (
                "reports/research/ledger/experiments.jsonl gate_results against "
                "config/promotion/unlevered-family-paper-tier-gates.json, long_only and "
                "market_neutral variants, 2018-2026 walk-forward out-of-sample."
            ),
            "stop_pivot": (
                "Not promoted while all_gates_pass is false for both variants; continue "
                "observation-mode connection and revisit when a later ledger experiment "
                "for this family clears the gate contract."
            ),
        },
        "decision": {
            "path": family,
            "decision": "not_promoted_observation_only",
            "reason": verdict_summary,
            "next_iteration_suggestion": (
                "Re-run this dossier generator against the next ledger experiment_id once "
                "the research line's B3 grid or a later candidate clears more gates."
            ),
        },
        "source_cards_path": source_cards_path or "",
    }


def _require(config: dict[str, Any], key: str) -> Any:
    if key not in config or config[key] in (None, "", []):
        _fail(f"config missing required key: {key}")
    return config[key]


def _load_config(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        _fail(f"cannot read config {path}: {exc}")
    if not isinstance(payload, dict):
        _fail("config must be a JSON object")
    return payload


def _iteration_root(root: Path, iter_id: str) -> Path:
    return root / "reports/research/iterations" / iter_id


def _relpath(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def build_dossier(config: dict[str, Any], root: Path, *, overwrite: bool) -> Path:
    iter_id = str(_require(config, "iter_id"))
    strategy_name = str(_require(config, "strategy_name"))
    spec_relpath = str(_require(config, "representative_spec_path"))
    path_name = str(_require(config, "path_name"))
    hypothesis_id = str(_require(config, "hypothesis_id"))
    objective = str(_require(config, "objective"))
    benchmark_family = list(_require(config, "benchmark_family"))
    candidates_input = list(_require(config, "candidates"))
    sources = list(_require(config, "sources"))
    topic_coverage = list(_require(config, "topic_coverage"))
    hypothesis_text = dict(_require(config, "hypothesis"))
    decision_text = dict(_require(config, "decision"))
    cost_table = dict(config.get("cost_table") or {"note": "no cost assumptions supplied"})
    source_cards_path = str(_require(config, "source_cards_path"))

    budget = len(candidates_input)
    if budget < 1 or budget > 24:
        _fail(f"candidate grid must have 1-24 entries for the lightweight path, got {budget}")
    candidate_ids = [str(row["candidate_id"]) for row in candidates_input]
    if len(set(candidate_ids)) != len(candidate_ids):
        _fail("duplicate candidate_id values in config['candidates']")

    spec_path = root / spec_relpath
    if not spec_path.is_file():
        _fail(f"representative_spec_path does not exist: {spec_relpath}")
    spec = load_strategy_spec(spec_path)
    spec_hash = strategy_content_hash(spec)
    design = research_design_mapping(spec)
    if design.get("iter_id") != iter_id:
        _fail(
            f"spec's research_design.iter_id ({design.get('iter_id')!r}) does not match "
            f"config iter_id ({iter_id!r}); fix the spec before generating the dossier"
        )
    if str(design.get("campaign_contract_path") or "").strip():
        _fail("spec declares campaign_contract_path; the lightweight path requires none")

    iteration_root = _iteration_root(root, iter_id)
    manifest_path = iteration_root / "candidate-manifest.json"
    cost_path = iteration_root / "cost-table.json"
    feasibility_path = iteration_root / "data-feasibility.json"
    if not overwrite:
        for existing in [manifest_path, cost_path, feasibility_path]:
            if existing.exists():
                _fail(f"{_relpath(existing, root)} already exists; pass --overwrite to replace")

    expected_manifest_relpath = _relpath(manifest_path, root)
    expected_feasibility_relpath = _relpath(feasibility_path, root)
    if str(design.get("candidate_manifest_path") or "") != expected_manifest_relpath:
        _fail(
            "spec's research_design.candidate_manifest_path must equal "
            f"{expected_manifest_relpath!r}, got {design.get('candidate_manifest_path')!r}"
        )
    feasibility_binding = design.get("data_feasibility_path") or design.get(
        "universe_contract_path"
    )
    if feasibility_binding != expected_feasibility_relpath:
        _fail(
            "spec's research_design.data_feasibility_path must equal "
            f"{expected_feasibility_relpath!r}, got {feasibility_binding!r}"
        )

    paths = init_iteration_dossier(iter_id, root, overwrite=overwrite)

    candidate_rows = [
        {
            "candidate_id": row["candidate_id"],
            "path": path_name,
            "role": "deterministic_mechanism_candidate",
            "method": str(row.get("method") or path_name),
            "ablation": str(row.get("ablation") or "none"),
            "spec_path": spec_relpath,
            "fallback": str(row.get("fallback") or "BIL"),
            "data_contract": "fixture",
            "feature_contract": "fixture",
            "label_contract": "fixture",
            "validation_contract": "fixture",
            "cost_contract": "fixture",
            "benchmark_contract": "fixture",
            "parameters": row.get("parameters") or {},
        }
        for row in candidates_input
    ]
    manifest = {
        "schema_version": 1,
        "iter_id": iter_id,
        "generated_before_backtest": True,
        "generated_at": datetime.now(UTC).isoformat(),
        "candidate_count": len(candidate_rows),
        "contracts": {
            group: {"fixture": {"description": "single-mechanism lightweight path"}}
            for group in _CONTRACT_GROUPS
        },
        "spec_hashes": {spec_relpath: spec_hash},
        "candidates": candidate_rows,
    }
    _write_json(manifest_path, manifest)

    _write_json(cost_path, cost_table)

    feasibility = {
        "schema_version": 1,
        "report_type": "single_mechanism_lightweight_path",
        "iter_id": iter_id,
        "workflow_pass": True,
        "research_pass": False,
        "llm_contribution_pass": False,
        "paper_ready_pass": False,
        "historical_evaluation_authorized": True,
        "path_gates": {
            path_name: {
                "action": "evaluate",
                "historical_evaluation_go": True,
                "candidate_ids": candidate_ids,
            }
        },
        "candidate_accounting": {
            "frozen_candidate_count": len(candidate_rows),
            "evaluation_authorized_count": len(candidate_rows),
            "dependency_skipped_count": 0,
            "unresolved_count": 0,
            "balanced": True,
        },
        "candidate_authorization": {
            "candidate_count": len(candidate_rows),
            "rows": [
                {
                    "candidate_id": row["candidate_id"],
                    "path": row["path"],
                    "action": "evaluate",
                    "reason_code": "single_mechanism_lightweight_path_ready",
                    "candidate_binding_sha256": candidate_authorization_binding_sha256(row),
                }
                for row in candidate_rows
            ],
        },
        "required_reference_names": ["cost_table"],
        "required_references": {
            "cost_table": {
                "path": _relpath(cost_path, root),
                "sha256": _sha256(cost_path),
            }
        },
    }
    _write_json(feasibility_path, feasibility)

    # Union of parameter axes across the grid, purely descriptive (the manifest
    # is the authoritative per-candidate binding).
    parameter_axes: dict[str, list[Any]] = {}
    for row in candidates_input:
        for key, value in (row.get("parameters") or {}).items():
            axis = parameter_axes.setdefault(key, [])
            if value not in axis:
                axis.append(value)

    search_space = {
        "schema_version": 3,
        "created_at": datetime.now(UTC).isoformat(),
        "iter_id": iter_id,
        "strategy_name": strategy_name,
        "source_spec_path": spec_relpath,
        "spec_hash": spec_hash,
        "single_mechanism_no_campaign_attestation": True,
        "total_candidate_budget": len(candidate_rows),
        "candidate_manifest_path": expected_manifest_relpath,
        "candidate_manifest_sha256": _sha256(manifest_path),
        "cost_table_path": _relpath(cost_path, root),
        "data_feasibility_path": expected_feasibility_relpath,
        "data_feasibility_sha256": _sha256(feasibility_path),
        "paths": [
            {
                "name": path_name,
                "candidate_count": len(candidate_rows),
                "hypothesis_refs": [hypothesis_id],
                "parameters": parameter_axes or {"candidate_count": len(candidate_rows)},
                "benchmark_family": benchmark_family,
            }
        ],
        "trial_ledger_paths": [],
        "evaluation_report_paths": [],
    }
    paths.search_space_json.write_text(
        json.dumps(search_space, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )

    if len(sources) < 8:
        _fail(f"config['sources'] needs >= 8 entries, got {len(sources)}")
    paper_like = {"paper", "academic_paper", "working_paper", "ssrn", "arxiv"}
    paper_count = sum(
        1 for s in sources if str(s.get("source_type", "")).strip().lower() in paper_like
    )
    if paper_count < 3:
        _fail(f"config['sources'] needs >= 3 paper-type entries, got {paper_count}")
    if len(topic_coverage) < 6:
        _fail(f"config['topic_coverage'] needs >= 6 entries, got {len(topic_coverage)}")

    external_brief = {
        "schema_version": 2,
        "iter_id": iter_id,
        "strategy_name": strategy_name,
        "source_spec_path": spec_relpath,
        "spec_hash": spec_hash,
        "objective": objective,
        "current_source_card_paths": [source_cards_path],
        "source_evidence_bindings": [
            {
                "source_url": source["url"],
                "source_card_path": source_cards_path,
                "claim_id": source.get("claim_id", f"claim_{index}"),
            }
            for index, source in enumerate(sources)
        ],
        "sources": sources,
        "topic_coverage": topic_coverage,
        "candidate_matrix_revisions": [
            {"path": path_name, "decision": "keep", "reason": "initial preregistration"}
        ],
        "hypothesis_links": [{"hypothesis_id": hypothesis_id, "source_urls": [sources[0]["url"]]}],
    }
    paths.external_brief_json.write_text(
        json.dumps(external_brief, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )
    paths.external_brief_md.write_text(
        f"""# External Brief: {iter_id}

## Objective

{objective}

## Sources

{len(sources)} source cards recorded in `external-brief.json`
({paper_count} paper-type). Source card records: `{source_cards_path}`.
Topic coverage: {", ".join(topic_coverage)}.

## Scope

This brief supports the single-mechanism lightweight path (search-space
`single_mechanism_no_campaign_attestation: true`). Its evidence backs the
preregistered candidate grid for path `{path_name}` only, not any other
mechanism family or promotion decision.
""",
        encoding="utf-8",
    )

    paths.hypotheses_md.write_text(
        f"""# Hypotheses: {iter_id}

## Hypothesis

{hypothesis_text.get("statement", "")}

## Failure mode

{hypothesis_text.get("failure_mode", "")}

## Measurement

{hypothesis_text.get("measurement", "")}

## Stop/Pivot criterion

{hypothesis_text.get("stop_pivot", "")}
""",
        encoding="utf-8",
    )
    paths.decision_record_md.write_text(
        f"""# Decision Record: {iter_id}

## Path

{decision_text.get("path", "")}

## Decision

{decision_text.get("decision", "pending")}

## Reason

{decision_text.get("reason", "")}

## Next iteration suggestion

{decision_text.get("next_iteration_suggestion", "")}
""",
        encoding="utf-8",
    )
    paths.search_space_md.write_text(
        f"""# Search Space: {iter_id}

Single-mechanism lightweight path (no campaign contract; see
docs/plan-step-10-mechanism-supplementation-2026-09-03.zh.md section 3.1).
One path, `{path_name}`, with {len(candidate_rows)} preregistered candidates
sharing spec `{spec_relpath}`. Benchmark family: {", ".join(benchmark_family)}.
Costs: `{_relpath(cost_path, root)}`. The candidate manifest at
`{expected_manifest_relpath}` is the authoritative per-candidate parameter
binding; this file is descriptive only.
""",
        encoding="utf-8",
    )

    result = validate_iteration_dossier(iter_id, root, stage="pre-backtest")
    print(json.dumps(result.to_dict(root), indent=2))
    if not result.ok:
        _fail("generated dossier still fails pre-backtest validation; see blocked[] above")
    return iteration_root


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("config", nargs="?", type=Path, help="path to the input config JSON")
    parser.add_argument(
        "--from-ledger",
        metavar="EXPERIMENT_ID",
        help=(
            "Build the config from reports/research/ledger/experiments.jsonl instead of "
            "a hand-written JSON file (Step 11 Wave C item 4: promote a real baseline-chain "
            "experiment). Requires --spec, --iter-id, and --strategy-name; sources/"
            "topic-coverage/source-cards-path are NOT fabricated -- pass --sources-json or "
            "this fails closed with the exact promotion-path source-evidence blocker."
        ),
    )
    parser.add_argument(
        "--spec",
        type=Path,
        help="(with --from-ledger) representative_spec_path, relative to the repo root",
    )
    parser.add_argument(
        "--iter-id",
        help="(with --from-ledger) iter_id; must match the spec's research_design.iter_id",
    )
    parser.add_argument(
        "--strategy-name",
        help="(with --from-ledger) strategy_name for the generated dossier",
    )
    parser.add_argument(
        "--sources-json",
        type=Path,
        help=(
            "(with --from-ledger) path to a JSON array of source records "
            "(>=8 entries, >=3 paper-type) -- see _EXAMPLE_CONFIG['sources'] for the shape"
        ),
    )
    parser.add_argument(
        "--topic-coverage",
        action="append",
        default=[],
        help="(with --from-ledger) repeatable; needs >=6 total",
    )
    parser.add_argument(
        "--source-cards-path",
        help="(with --from-ledger) path recorded as this dossier's source_cards_path",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="replace an existing candidate-manifest/cost-table/data-feasibility/dossier set",
    )
    parser.add_argument(
        "--print-example",
        action="store_true",
        help="print an example config JSON to stdout and exit",
    )
    args = parser.parse_args(argv)

    if args.print_example:
        print(json.dumps(_EXAMPLE_CONFIG, indent=2))
        return 0

    root = project_root()
    if args.from_ledger:
        missing = [
            name
            for name, value in (
                ("--spec", args.spec),
                ("--iter-id", args.iter_id),
                ("--strategy-name", args.strategy_name),
            )
            if not value
        ]
        if missing:
            parser.error(f"--from-ledger requires {', '.join(missing)}")
        sources: list[dict[str, Any]] | None = None
        if args.sources_json:
            sources_payload = json.loads(args.sources_json.read_text(encoding="utf-8"))
            if not isinstance(sources_payload, list):
                _fail(f"{args.sources_json} must contain a JSON array of source records")
            sources = sources_payload
        config = config_from_ledger(
            root=root,
            experiment_id=args.from_ledger,
            iter_id=args.iter_id,
            strategy_name=args.strategy_name,
            representative_spec_path=str(args.spec),
            sources=sources,
            topic_coverage=list(args.topic_coverage) or None,
            source_cards_path=args.source_cards_path,
        )
        print(json.dumps(config, indent=2, sort_keys=True))
    else:
        if args.config is None:
            parser.error("config is required unless --from-ledger or --print-example is given")
        config = _load_config(args.config)

    build_dossier(config, root, overwrite=args.overwrite)
    return 0


if __name__ == "__main__":
    sys.exit(main())
