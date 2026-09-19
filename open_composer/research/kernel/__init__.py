"""Research kernel public surface.

Re-exports are resolved lazily (PEP 562). Eager re-exports used to create an
import cycle: ``open_composer.research.campaign`` imports
``kernel.effective_trials``, importing that submodule executes this package
``__init__``, which used to import ``kernel.mechanism_eval``, which imports
``campaign`` again -- at that point ``campaign`` is only partially initialised
and the import fails with ``cannot import name
'_UNMEASURABLE_DOWNSIDE_CAPTURE_RATIO'``. Resolving names on first attribute
access keeps the public API identical while letting either module be imported
first.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

_EXPORTS: dict[str, str] = {
    "ResearchArtifactWriter": "artifacts",
    "append_research_run_index": "artifacts",
    "research_report_paths": "artifacts",
    "CandidateScore": "candidates",
    "CandidateSet": "candidates",
    "CandidateSpec": "candidates",
    "DEFAULT_CORRELATION_THRESHOLD": "effective_trials",
    "EffectiveTrialsReport": "effective_trials",
    "TrialCluster": "effective_trials",
    "effective_independent_trials": "effective_trials",
    "GateResult": "gates",
    "GateStatus": "gates",
    "Candidate": "mechanism_eval",
    "CandidateVerdict": "mechanism_eval",
    "FamilyVerdict": "mechanism_eval",
    "Mechanism": "mechanism_eval",
    "annualized_cagr": "mechanism_eval",
    "evaluate_candidate": "mechanism_eval",
    "evaluate_family": "mechanism_eval",
    "expand_mechanism": "mechanism_eval",
    "max_drawdown": "mechanism_eval",
    "recent_window_diagnostic": "mechanism_eval",
    "EvaluationBundle": "metrics",
    "MetricSummary": "metrics",
    "DEFAULT_EMBARGO_BARS": "rolling_origin",
    "DEFAULT_FOLD_COUNT": "rolling_origin",
    "returns_from_ohlcv": "rolling_origin",
    "rolling_origin_folds": "rolling_origin",
    "TrialLedger": "trials",
    "TrialRecord": "trials",
    "PurgedEmbargoConfig": "windows",
    "ResearchWindowSplit": "windows",
    "WalkForwardSlice": "windows",
    "ResearchBrief": "workflow",
    "ResearchRunIndexRecord": "workflow",
    "SearchSpace": "workflow",
    "build_default_research_brief": "workflow",
    "search_space_from_spec": "workflow",
}

if TYPE_CHECKING:  # pragma: no cover - import-time typing aid only
    from open_composer.research.kernel.artifacts import (
        ResearchArtifactWriter,
        append_research_run_index,
        research_report_paths,
    )
    from open_composer.research.kernel.candidates import (
        CandidateScore,
        CandidateSet,
        CandidateSpec,
    )
    from open_composer.research.kernel.effective_trials import (
        DEFAULT_CORRELATION_THRESHOLD,
        EffectiveTrialsReport,
        TrialCluster,
        effective_independent_trials,
    )
    from open_composer.research.kernel.gates import GateResult, GateStatus
    from open_composer.research.kernel.mechanism_eval import (
        Candidate,
        CandidateVerdict,
        FamilyVerdict,
        Mechanism,
        annualized_cagr,
        evaluate_candidate,
        evaluate_family,
        expand_mechanism,
        max_drawdown,
        recent_window_diagnostic,
    )
    from open_composer.research.kernel.metrics import EvaluationBundle, MetricSummary
    from open_composer.research.kernel.rolling_origin import (
        DEFAULT_EMBARGO_BARS,
        DEFAULT_FOLD_COUNT,
        returns_from_ohlcv,
        rolling_origin_folds,
    )
    from open_composer.research.kernel.trials import TrialLedger, TrialRecord
    from open_composer.research.kernel.windows import (
        PurgedEmbargoConfig,
        ResearchWindowSplit,
        WalkForwardSlice,
    )
    from open_composer.research.kernel.workflow import (
        ResearchBrief,
        ResearchRunIndexRecord,
        SearchSpace,
        build_default_research_brief,
        search_space_from_spec,
    )


def __getattr__(name: str) -> Any:
    module_name = _EXPORTS.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    from importlib import import_module

    module = import_module(f"{__name__}.{module_name}")
    value = getattr(module, name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(_EXPORTS))


__all__ = [
    "Candidate",
    "CandidateScore",
    "CandidateSet",
    "CandidateSpec",
    "CandidateVerdict",
    "DEFAULT_CORRELATION_THRESHOLD",
    "DEFAULT_EMBARGO_BARS",
    "DEFAULT_FOLD_COUNT",
    "EffectiveTrialsReport",
    "EvaluationBundle",
    "FamilyVerdict",
    "GateResult",
    "GateStatus",
    "Mechanism",
    "MetricSummary",
    "PurgedEmbargoConfig",
    "ResearchArtifactWriter",
    "ResearchBrief",
    "ResearchRunIndexRecord",
    "ResearchWindowSplit",
    "SearchSpace",
    "TrialCluster",
    "TrialLedger",
    "TrialRecord",
    "WalkForwardSlice",
    "annualized_cagr",
    "append_research_run_index",
    "build_default_research_brief",
    "effective_independent_trials",
    "evaluate_candidate",
    "evaluate_family",
    "expand_mechanism",
    "max_drawdown",
    "recent_window_diagnostic",
    "research_report_paths",
    "returns_from_ohlcv",
    "rolling_origin_folds",
    "search_space_from_spec",
]
