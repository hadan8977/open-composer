"""Step 6.5: IC = n/a must come with an explicit diagnosis."""

from __future__ import annotations

import json
from pathlib import Path

from open_composer.research.auto_research import run_auto_research


def test_overnight_factors_produce_ic_or_diagnosis(repo_root: Path) -> None:
    result = run_auto_research(
        thesis="Overnight thesis: exploit overnight gap behavior on SYN daily bars.",
        universe=["SYN"],
        timeframe="daily",
        data_source="sample",
        data_path="data/sample/syn_daily.csv",
        max_factors=5,
        use_llm=False,
        root=repo_root,
    )

    ic = json.loads((Path(result.report_path).parent / "ic_scores.json").read_text())
    overnight_ids = [
        factor_id
        for factor_id in ic
        if "overnight" in factor_id.lower() or "gap" in factor_id.lower()
    ]
    assert overnight_ids, f"no overnight factor candidate found; ic keys = {list(ic)}"

    for factor_id in overnight_ids:
        row = ic[factor_id]
        rank_ic = row.get("rank_ic")
        diagnosis = row.get("rank_ic_diagnosis")
        assert (rank_ic is not None) or (diagnosis is not None), (
            f"factor {factor_id}: rank_ic=None AND no diagnosis. row={row}"
        )


def test_ic_diagnosis_values_are_known(repo_root: Path) -> None:
    known = {
        "insufficient_observations",
        "low_coverage",
        "zero_variance_signal",
        "all_nan_signal",
        "rank_ic_undefined_unknown_reason",
    }
    source = repo_root / "open_composer" / "research" / "auto_research.py"
    text = source.read_text(encoding="utf-8")

    for value in known:
        assert value in text, f"expected diagnosis enum {value!r} missing"
