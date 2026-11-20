"""Resolve and validate a finite JSON experiment before launching any numerical work."""
import argparse
import json
from datetime import date, timedelta
from functools import partial
from inspect import signature
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, PositiveInt, TypeAdapter

from open_composer.lab.batch import Variant, run_batch
from open_composer.lab.ledger import TrialLedger
from research.levered_index_throughput.leveraged_family import STAGES, development_trial, replay_family
from open_composer.lab.leveraged_index import replay_bridge
from open_composer.lab.models import Experiment
from open_composer.market_sessions import us_equity_session_dates
from open_composer.models.strategy_spec import load_strategy_spec
from open_composer.research.agent_workflow import identifier, local_path


class SpecFields(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", allow_inf_nan=False)


class Prices(SpecFields):
    start: date


class Parameters(SpecFields):
    freeze: str
    prices: Prices


class FamilyParameters(Parameters):
    screen_checkpoint: str | None = None


class BridgeParameters(Parameters):
    block_sessions: PositiveInt


class FamilySpec(SpecFields):
    adapter: Literal["leveraged_index_family"]
    experiment: Experiment
    parameters: FamilyParameters


class BridgeSpec(SpecFields):
    adapter: Literal["leveraged_index_bridge"]
    experiment: Experiment
    parameters: BridgeParameters


class ExposureParameters(SpecFields):
    features: list[str]
    start: date
    sealed_start: date
    end: date
    capital: PositiveInt
    costs: list[PositiveInt]
    horizon: PositiveInt
    embargo: PositiveInt
    half_life: PositiveInt
    penalty: float
    switch_cost: float
    registration: str


class ExposureSpec(SpecFields):
    adapter: Literal["weekly_index_exposure"]
    experiment: Experiment
    parameters: ExposureParameters


class FactorParameters(SpecFields):
    slate: str
    library_batch: str | None = None
    official_interest: bool = False
    preceding_statistics: str | None = None
    split: Literal["development", "validation", "context"]
    capital: PositiveInt


class FactorSpec(SpecFields):
    adapter: Literal["dated_factor_screen"]
    experiment: Experiment
    parameters: FactorParameters


SPEC = TypeAdapter(Annotated[FamilySpec | BridgeSpec | ExposureSpec | FactorSpec,
                             Field(discriminator="adapter")])


class FrozenComparison(BaseModel):
    # Remaining fields describe the original selection and reserved-window decision.
    model_config = ConfigDict(strict=True)
    candidate: Literal["qqq_vol_gate"]
    matched_control: Literal["tqqq_vol"]
    comparator: Literal["s3"]
    capital_usd: Literal[15000]
    development_start: date
    development_end: date
    costs_bps_per_side: tuple[Literal[10], Literal[20]]


def resolve_spec(root, spec_path, batch_id):
    spec = SPEC.validate_json(spec_path.read_bytes())
    experiment = spec.experiment
    direction = root / "research" / identifier(experiment.direction)
    folder = direction / "batches" / identifier(batch_id) / spec.adapter
    params = spec.parameters
    if isinstance(spec, FactorSpec):
        from research.factor_factory.run import run_wave

        if experiment.kind != "diagnostic" or (folder.parent / "results.json").exists():
            raise ValueError("A factor wave requires a new diagnostic batch")
        return experiment, partial(run_wave, root, folder.parent, spec)
    if experiment.kind == "financial":
        ledger = TrialLedger(direction / "trials.jsonl")
        if not ledger.path.is_file() or ledger.n_trials == 0:
            raise ValueError("Financial Results require existing selectable trial exposure")
    if folder.parent.exists():
        raise FileExistsError(folder.parent)
    parameters = params.model_dump(mode="json", exclude_none=True)
    if isinstance(spec, ExposureSpec):
        from open_composer.lab.exposure_study import run_exposure
        from open_composer.lab.exposure_inputs import INPUTS

        if experiment.kind != "financial":
            raise ValueError("Exposure replay requires a financial account")
        event, = ledger.events()
        if event.event != "started" or event.candidate != spec.adapter or event.batch != "registration":
            raise ValueError("Expected an unused registered exposure trial")
        if spec != SPEC.validate_json(local_path(root, event.parameters["spec"]).read_bytes()):
            raise ValueError("Execution spec differs from frozen trial")
        for path in [local_path(root, params.registration), INPUTS/"marks.parquet", INPUTS/"state.parquet"]:
            if not path.is_file():
                raise FileNotFoundError(path)
        signature(run_exposure).bind(root, folder, **parameters)
        return experiment, Variant(spec.adapter, parameters, partial(run_exposure, root, folder, **parameters),
                                   registered_trial_id=event.trial_id)
    freeze = local_path(root, params.freeze)
    frozen = FrozenComparison.model_validate_json(freeze.read_bytes())
    if not params.prices.start < frozen.development_start <= frozen.development_end:
        raise ValueError("Price warmup must precede the frozen development window")
    rotation = load_strategy_spec(root / "strategy_specs/drafts/us_etf_levered_rotation_63_top2_monthly.yaml")
    warmup = us_equity_session_dates(params.prices.start, frozen.development_start - timedelta(days=1))
    if len(warmup) < rotation.portfolio.etf_rotation.min_history_sessions:
        raise ValueError("Insufficient warmup for the registered rotation")
    if isinstance(spec, FamilySpec):
        adapter = replay_family
        source = freeze.parents[2]
        for run, module in [("4-1", "replay"), ("5-10", "semiconductor_attribution"),
                            *((f"5-{i}", name) for i, name in enumerate(STAGES, 1))]:
            if not (source / f"lt-20261119-{run}/worker/{module}.py").is_file():
                raise FileNotFoundError(f"Missing registered worker {module} in {source}")
        signature(TrialLedger.start).bind(None, **development_trial(frozen.candidate, frozen.matched_control))
        if params.screen_checkpoint is not None:
            cache = local_path(root, params.screen_checkpoint)
            trial = cache.parents[3]
            old, = json.loads((trial.parent / "manifest.json").read_text(encoding="utf-8"))["variants"]
            if (trial.parent.parent != direction / "batches" or old["id"] != spec.adapter
                    or old["parameters"] != {k: v for k, v in parameters.items() if k != "screen_checkpoint"}):
                raise ValueError("Screen checkpoint must belong to the same registered comparison")
            screens = list(cache.glob("screen-*.pkl"))
            if not screens or set(cache.iterdir()) != set(screens):
                raise ValueError("Checkpoint must contain only completed screen account files")
    else:
        adapter = replay_bridge
        days = us_equity_session_dates(frozen.development_start, frozen.development_end)
        size = params.block_sessions
        if not any(days[i].year >= 2024 for i in range(0, len(days) - size + 1, size)):
            raise ValueError("Bridge requires a complete recent restart window")
    signature(adapter).bind(root, folder, **parameters)
    variant = Variant(spec.adapter, parameters, partial(adapter, root, folder, **parameters),
                      counts_as_trial=False, exposure_note="Fixed historical replication.")
    return experiment, variant


def run_spec(root, spec_path, batch_id):
    experiment, variant = resolve_spec(root, spec_path, batch_id)
    if callable(variant):
        return variant()
    return run_batch(root, experiment=experiment, batch_id=batch_id, variants=[variant], selected_id=variant.id)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("spec", type=Path)
    parser.add_argument("batch_id")
    parser.add_argument("--terminal", action="store_true")
    args = parser.parse_args()
    batch = run_spec(Path.cwd(), args.spec, args.batch_id)
    if args.terminal:
        result, = batch.results.values()
        marker = args.spec.parent / "batch-results.json"
        temp = marker.with_suffix(".tmp")
        temp.write_bytes(result.read_bytes())
        temp.replace(marker)
