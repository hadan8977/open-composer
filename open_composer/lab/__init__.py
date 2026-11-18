"""Shared research accounting, cumulative trials and native-engine adapters."""

from open_composer.lab.adapters import book_engine, screen_engine, screen_variants, spec_engine
from open_composer.lab.batch import Variant, run_batch
from open_composer.lab.ledger import TrialLedger
from open_composer.lab.metrics import DSRConfig, dsr_summary
from open_composer.lab.models import EngineResult, Experiment
from open_composer.research.features.price_hygiene import sanitize_price_matrices

__all__ = [
    "DSRConfig",
    "EngineResult",
    "Experiment",
    "TrialLedger",
    "Variant",
    "book_engine",
    "dsr_summary",
    "run_batch",
    "sanitize_price_matrices",
    "screen_engine",
    "screen_variants",
    "spec_engine",
]
