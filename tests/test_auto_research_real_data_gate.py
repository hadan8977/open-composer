"""Work Item F: real-data auto research must be preregistered and bounded."""

from __future__ import annotations

from pathlib import Path

import pytest

from open_composer.research.auto_research import (
    REAL_DATA_SOURCES,
    _require_bounded_search,
    _require_real_data_authorization,
    run_auto_research,
)
from open_composer.research.campaign import MAX_FAMILY_EFFECTIVE_TRIAL_COUNT


def test_sample_never_reaches_the_gate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The workflow-only smoke path must be unaffected by Work Item F."""
    called: list[object] = []
    monkeypatch.setattr(
        "open_composer.research.auto_research._require_real_data_authorization",
        lambda *args, **kwargs: called.append(args),
    )
    with pytest.raises(Exception):  # noqa: B017 - downstream smoke needs a workspace
        run_auto_research("thesis", ["QQQ"], data_source="sample", root=tmp_path)
    assert called == []


def test_real_data_without_an_iteration_id_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="requires iteration_id"):
        _require_real_data_authorization("sip_parquet", None, tmp_path)


def test_real_data_with_an_unregistered_iteration_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="not execution-ready"):
        _require_real_data_authorization("sip_parquet", "never_registered_iter", tmp_path)


def test_legacy_provider_feeds_stay_unreachable(tmp_path: Path) -> None:
    # alpaca/longbridge carry no pinned adjustment provenance; the IEX cache
    # defect (docs/finding-iex-cache-price-adjustment-defect-2026-09-01.zh.md)
    # is what that costs. Only the SIP archive is admissible here.
    for source in ("alpaca", "longbridge", "iex"):
        with pytest.raises(ValueError, match="accepts"):
            _require_real_data_authorization(source, "some_iter", tmp_path)


def test_only_sip_parquet_is_an_admissible_real_source() -> None:
    assert REAL_DATA_SOURCES == ("sip_parquet",)


def test_run_auto_research_still_refuses_real_data_without_preregistration(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError):
        run_auto_research("thesis", ["QQQ"], data_source="sip_parquet", root=tmp_path)


def test_bounded_search_counts_clusters_not_candidates() -> None:
    # 40 near-duplicates of one mechanism are a handful of real trials, so a
    # raw count far above the budget can still be admissible.
    import numpy as np

    rng = np.random.default_rng(3)
    base = rng.normal(0.0004, 0.01, 600)
    duplicates = {f"c{i:03d}": (base + rng.normal(0, 0.0005, 600)).tolist() for i in range(40)}
    effective_n = _require_bounded_search(duplicates)
    assert effective_n <= MAX_FAMILY_EFFECTIVE_TRIAL_COUNT
    assert len(duplicates) > MAX_FAMILY_EFFECTIVE_TRIAL_COUNT


def test_bounded_search_refuses_a_genuinely_unbounded_search() -> None:
    import numpy as np

    rng = np.random.default_rng(4)
    independent = {
        f"c{i:03d}": rng.normal(0.0004, 0.01, 600).tolist()
        for i in range(MAX_FAMILY_EFFECTIVE_TRIAL_COUNT + 8)
    }
    with pytest.raises(ValueError, match="over the family budget"):
        _require_bounded_search(independent)
