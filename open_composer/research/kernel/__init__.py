from open_composer.research.kernel.artifacts import (
    ResearchArtifactWriter,
    append_research_run_index,
    research_report_paths,
)
from open_composer.research.kernel.candidates import CandidateScore, CandidateSet, CandidateSpec
from open_composer.research.kernel.effective_trials import (
    DEFAULT_CORRELATION_THRESHOLD,
    EffectiveTrialsReport,
    TrialCluster,
    effective_independent_trials,
)
from open_composer.research.kernel.gates import GateResult, GateStatus
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

__all__ = [
    "CandidateScore",
    "CandidateSet",
    "CandidateSpec",
    "DEFAULT_CORRELATION_THRESHOLD",
    "DEFAULT_EMBARGO_BARS",
    "DEFAULT_FOLD_COUNT",
    "EffectiveTrialsReport",
    "EvaluationBundle",
    "GateResult",
    "GateStatus",
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
    "append_research_run_index",
    "build_default_research_brief",
    "effective_independent_trials",
    "research_report_paths",
    "returns_from_ohlcv",
    "rolling_origin_folds",
    "search_space_from_spec",
]
