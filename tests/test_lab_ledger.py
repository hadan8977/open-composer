from pathlib import Path

import pytest

from open_composer.lab import TrialLedger


def test_cumulative_exposure_preserves_failed_prior_and_unfinished_trials(tmp_path: Path):
    ledger = TrialLedger(tmp_path / "trials.jsonl")
    ledger.import_prior("old-run", count=7, evidence=["original/trials.json"], note="Seen trials")
    before = ledger.path.read_bytes()
    ledger.start("b1/a", batch="b1", candidate="a", parameters={"threshold": 2})
    ledger.finish("b1/a", status="failed", evidence=["failure.json"], note="Bad input")
    ledger.start("b2/a", batch="b2", candidate="a", parameters={"threshold": 3})
    ledger.start("b2/stress", batch="b2", candidate="stress", parameters={}, counts_as_trial=False)
    assert ledger.n_trials == 9
    assert ledger.path.read_bytes().startswith(before)
    snapshot = tmp_path / "snapshot.jsonl"
    assert ledger.snapshot(snapshot) == 9
    assert snapshot.read_bytes() == ledger.path.read_bytes()
    with pytest.raises(ValueError, match="already exists"):
        ledger.import_prior("old-run", count=7, evidence=["old"], note="Duplicate")
    with pytest.raises(ValueError, match="unfinished start"):
        ledger.finish("b1/a", status="complete", evidence=[])
    with pytest.raises(ValueError, match="original evidence"):
        ledger.import_prior("missing", count=4, evidence=[], note="No evidence")


def test_corrupted_ledger_is_not_truncated_or_ignored(tmp_path: Path):
    path = tmp_path / "trials.jsonl"
    path.write_text('{"partial":')
    with pytest.raises(ValueError):
        TrialLedger(path).start("new", batch="b", candidate="a", parameters={})
    assert path.read_text() == '{"partial":'
