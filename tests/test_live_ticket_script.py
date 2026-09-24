"""Manual live ticket: the fingerprint must follow the overlay, not only the rebalance id."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import live_ticket  # noqa: E402


def _targets(upro_weight: float, multiplier: float) -> dict:
    rebalance = "us_etf_levered_rotation_63_top2_monthly:2026-08-31"
    return {
        "generated_at": "2026-09-23T23:09:09Z",
        "summary": {
            "anchor_session": "2026-08-31",
            "latest_session": "2026-09-23",
            "vol_target": {"multiplier": multiplier, "boost_active": False},
        },
        "target_weights": [
            {
                "symbol": "UPRO",
                "target_weight": upro_weight,
                "reference_price": 150.27,
                "rebalance_id": rebalance,
            },
            {
                "symbol": "SHY",
                "target_weight": round(1.0 - upro_weight, 4),
                "reference_price": 81.65,
                "rebalance_id": rebalance,
            },
        ],
    }


def _spec(tmp_path: Path) -> Path:
    spec = tmp_path / "spec.yaml"
    spec.write_text(
        "name: us_etf_levered_rotation_63_top2_monthly\n"
        "portfolio:\n  etf_rotation:\n    drawdown_exit_pct: 0.25\n"
        "execution_policy:\n  order_style: day_market\n",
        encoding="utf-8",
    )
    return spec


def test_fingerprint_changes_when_overlay_moves_weights_within_a_rebalance(
    tmp_path: Path, monkeypatch
) -> None:
    spec = _spec(tmp_path)
    monkeypatch.setattr(live_ticket, "load_targets", lambda name: _targets(1.0, 1.0))
    full = live_ticket.ticket(spec, 10_000, None, None)
    monkeypatch.setattr(live_ticket, "load_targets", lambda name: _targets(0.792, 0.792))
    scaled = live_ticket.ticket(spec, 10_000, None, None)

    def fingerprint(text: str) -> str:
        line = next(x for x in text.splitlines() if x.startswith("- Targets fingerprint"))
        return line.split("`")[1]

    assert fingerprint(full) != fingerprint(scaled)
    assert "rebalance id changes" not in scaled
    assert "| UPRO | 79.2% | 150.27 | 52 |" in scaled
    assert "market orders sent after the prior close" in scaled


def test_fingerprint_is_stable_for_identical_targets() -> None:
    rows = _targets(0.792, 0.792)["target_weights"]
    assert live_ticket.targets_fingerprint(rows, 0.792) == live_ticket.targets_fingerprint(
        list(reversed(rows)), 0.792
    )
