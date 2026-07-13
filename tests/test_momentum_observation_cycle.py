from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd
import yaml

from open_composer.research.momentum_observation_cycle import (
    build_theoretical_execution_proxy,
    evaluate_momentum_shadow_readiness,
    run_momentum_observation_cycle,
)
from open_composer.storage import append_jsonl


def test_cycle_is_slot_idempotent_and_broker_free(sample_workspace: Path, monkeypatch) -> None:
    spec_path, last = _workspace(sample_workspace)

    def forbidden(*args, **kwargs):
        raise AssertionError("network or broker entry point must not be called")

    monkeypatch.setattr(
        "open_composer.research.momentum_observation_cycle.refresh_momentum_research_data",
        forbidden,
    )
    as_of = (last + pd.Timedelta(hours=1)).to_pydatetime()
    first = run_momentum_observation_cycle(spec_path, sample_workspace, as_of=as_of)
    first_receipt = first.receipt_path.read_text(encoding="utf-8")
    second = run_momentum_observation_cycle(spec_path, sample_workspace, as_of=as_of)

    assert second.receipt_path.read_text(encoding="utf-8") == first_receipt
    assert first.payload["broker_writes"] is False
    assert first.payload["paper_order_authorization"] is False
    assert not (sample_workspace / "reports/paper/orders.jsonl").exists()


def test_cycle_failure_writes_remediation_without_receipt(
    sample_workspace: Path, monkeypatch
) -> None:
    spec_path, last = _workspace(sample_workspace)

    def fail(*args, **kwargs):
        raise RuntimeError("strict refresh failed")

    monkeypatch.setattr(
        "open_composer.research.momentum_observation_cycle.refresh_momentum_research_data", fail
    )
    as_of = (last + pd.Timedelta(hours=1)).to_pydatetime()
    try:
        run_momentum_observation_cycle(spec_path, sample_workspace, as_of=as_of, refresh=True)
    except RuntimeError as exc:
        assert "strict refresh failed" in str(exc)
    else:
        raise AssertionError("failed refresh must block the cycle")

    run_dir = sample_workspace / "reports/shadow" / spec_path.stem / "runs"
    assert not list(run_dir.glob("*.json"))
    remediations = list(
        (sample_workspace / "reports/shadow" / spec_path.stem / "remediations").glob("*.json")
    )
    assert len(remediations) == 1


def test_theoretical_proxy_is_not_observed_fill(tmp_path: Path) -> None:
    ledger = tmp_path / "forward.jsonl"
    append_jsonl(
        ledger,
        [
            {
                "spec_hash": "abc",
                "signal_timestamp": "2026-07-14T13:00:00+00:00",
                "effective_timestamp": "2026-07-14T13:30:00+00:00",
                "decision_price": 100.0,
                "expected_execution_open": 101.0,
            }
        ],
    )

    rows = build_theoretical_execution_proxy(ledger)

    assert rows[0]["decision_to_next_open_bps"] == 100.0
    assert rows[0]["observed_fill"] is False
    assert rows[0]["quote_available"] is False
    assert rows[0]["execution_session_type"] == "opening_proxy"


def test_readiness_separates_product_shadow_paper_and_ml(tmp_path: Path) -> None:
    ledger = tmp_path / "forward.jsonl"
    proxy = tmp_path / "proxy.jsonl"
    rows = []
    for day_index, day in enumerate(pd.date_range("2026-01-02", periods=60, freq="B")):
        for intent_index in range(2):
            timestamp = pd.Timestamp(day).tz_localize("America/New_York") + pd.Timedelta(
                hours=10 + intent_index
            )
            rows.append(
                {
                    "signal_timestamp": timestamp.tz_convert("UTC").isoformat(),
                    "effective_timestamp": (
                        timestamp.tz_convert("UTC") + pd.Timedelta(minutes=30)
                    ).isoformat(),
                    "order_required_intent": True,
                    "target_weight": float((day_index + intent_index) % 2),
                }
            )
    append_jsonl(ledger, rows)
    append_jsonl(proxy, [{"id": index} for index in range(len(rows))])

    readiness = evaluate_momentum_shadow_readiness(
        ledger,
        proxy,
        shadow_status="observation_only",
        as_of=pd.Timestamp("2026-04-01T20:00:00Z"),
        cross_source={"passed": True, "expires_at": "2026-05-01T00:00:00Z"},
        observed_fill_tca={"passed": True, "expires_at": "2026-05-01T00:00:00Z"},
    )

    assert readiness["status"] == "shadow_observation_complete"
    assert readiness["product_capability_complete"] is True
    assert readiness["paper_ready_pass"] is False
    assert readiness["paper_authorized"] is False
    assert readiness["ml_eligible"] is False


def _workspace(root: Path) -> tuple[Path, pd.Timestamp]:
    for symbol, leverage in (("qqq", 1.0), ("tqqq", 2.5)):
        _write_data(root, symbol, leverage)
    source = Path(__file__).parents[1] / "strategy_specs/drafts/us_mom_minute_p1_003_frozen.yaml"
    payload = yaml.safe_load(source.read_text(encoding="utf-8"))
    design = payload["notes"]["research_design"]
    design["forward_epoch_utc"] = "2026-01-01T00:00:00+00:00"
    design["source_contract"]["symbols"] = {
        symbol: _contract(root, symbol) for symbol in ("QQQ", "TQQQ")
    }
    encoded = json.dumps(design["source_contract"], sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )
    design["source_contract_sha256"] = hashlib.sha256(encoded).hexdigest()
    spec_path = root / "strategy_specs/drafts/us_mom_minute_p1_003_frozen.yaml"
    spec_path.parent.mkdir(parents=True, exist_ok=True)
    spec_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    last = pd.Timestamp(
        pd.read_csv(root / "data/research/alpaca_minute/qqq_30m_alpaca_iex.csv")["timestamp"].iloc[
            -1
        ]
    )
    return spec_path, last


def _write_data(root: Path, symbol: str, leverage: float) -> None:
    path = root / "data/research/alpaca_minute" / f"{symbol}_30m_alpaca_iex.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    price = 100.0
    for day in pd.date_range("2026-01-02", periods=40, freq="B"):
        for offset in range(13):
            timestamp = pd.Timestamp(day.date()).tz_localize("America/New_York") + pd.Timedelta(
                hours=9, minutes=30 + offset * 30
            )
            close = price * (1 + 0.0005 * leverage)
            rows.append(
                {
                    "timestamp": timestamp.tz_convert("UTC"),
                    "open": price,
                    "high": close * 1.001,
                    "low": price * 0.999,
                    "close": close,
                    "volume": 100000,
                }
            )
            price = close
    pd.DataFrame(rows).to_csv(path, index=False)


def _contract(root: Path, symbol: str) -> dict[str, object]:
    path = root / "data/research/alpaca_minute" / f"{symbol.lower()}_30m_alpaca_iex.csv"
    raw = path.read_bytes()
    frame = pd.read_csv(path)
    return {
        "symbol": symbol,
        "prefix_rows": len(frame),
        "prefix_bytes": len(raw),
        "prefix_last_timestamp": pd.Timestamp(frame["timestamp"].iloc[-1]).isoformat(),
        "prefix_sha256": hashlib.sha256(raw).hexdigest(),
    }
