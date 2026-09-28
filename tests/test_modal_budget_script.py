"""Modal spend guard: worst-case pricing, unbilled window and the cap decision."""

from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import modal_budget as mb  # noqa: E402

NOW = datetime(2026, 9, 28, 12, 0, tzinfo=UTC)


def test_worst_case_prices_cpu_memory_and_gpu() -> None:
    assert mb.worst_case_usd(8, 32, 120, None) == round((8 * 0.0473 + 32 * 0.008) * 2, 4)
    assert mb.worst_case_usd(2, 8, 60, "T4") == round(2 * 0.0473 + 8 * 0.008 + 0.59, 4)


def test_recent_jobs_count_until_billing_catches_up() -> None:
    rows = [
        {"at": (NOW - timedelta(hours=1)).isoformat(), "timeout_min": 60, "worst_case_usd": 1.5},
        {"at": (NOW - timedelta(hours=10)).isoformat(), "timeout_min": 60, "worst_case_usd": 9.0},
    ]
    assert mb.unbilled_worst_case(rows, NOW) == 1.5


def test_cap_refuses_a_job_that_could_cross_it() -> None:
    assert mb.decide(20.0, 2.0, 2.9)["allowed"]
    assert not mb.decide(20.0, 2.0, 3.1)["allowed"]


def test_cost_parser_accepts_dollar_strings() -> None:
    assert mb._cost("$1,234.50") == 1234.5
    assert mb._cost(0.25) == 0.25
    assert mb._cost(None) == 0.0
