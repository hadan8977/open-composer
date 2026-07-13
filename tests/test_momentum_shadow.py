from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd
import yaml

from open_composer.adapters.execution.momentum_shadow import (
    run_momentum_shadow_observation,
)


def test_shadow_observation_maps_qqq_to_tqqq_without_broker_writes(
    sample_workspace: Path,
) -> None:
    _write_data(sample_workspace, "qqq", 1.0)
    _write_data(sample_workspace, "tqqq", 2.5)
    spec_path = _write_spec(sample_workspace)

    last = pd.read_csv(sample_workspace / "data/research/alpaca_minute/tqqq_30m_alpaca_iex.csv")[
        "timestamp"
    ].iloc[-1]
    result = run_momentum_shadow_observation(
        spec_path,
        sample_workspace,
        as_of=(pd.Timestamp(last) + pd.Timedelta(hours=1)).to_pydatetime(),
    )

    targets = json.loads(result.target_weights_path.read_text(encoding="utf-8"))
    review = json.loads(result.review_json_path.read_text(encoding="utf-8"))
    signals = [json.loads(line) for line in result.signal_log_path.read_text().splitlines()]
    assert {row["symbol"] for row in targets["target_weights"]} == {"TQQQ"}
    assert all(row["signal_symbol"] == "QQQ" for row in targets["target_weights"])
    assert all(signal["symbol"] == "TQQQ" for signal in signals)
    assert review["execution_substate"] == "observation_only"
    assert review["paper_order_authorization"] is False
    assert review["broker_writes"] is False
    assert not (sample_workspace / "reports/paper/orders.jsonl").exists()
    ledger = [json.loads(line) for line in result.forward_ledger_path.read_text().splitlines()]
    assert ledger
    assert all(row["evidence_class"] == "forward_observation" for row in ledger)
    assert all(row["broker_writes"] is False for row in ledger)


def test_shadow_observation_is_idempotent_and_blocks_stale_data(sample_workspace: Path) -> None:
    _write_data(sample_workspace, "qqq", 1.0)
    _write_data(sample_workspace, "tqqq", 2.5)
    spec_path = _write_spec(sample_workspace)
    first = run_momentum_shadow_observation(
        spec_path,
        sample_workspace,
        as_of=pd.Timestamp("2027-01-01T00:00:00Z").to_pydatetime(),
    )
    text = first.signal_log_path.read_text(encoding="utf-8")
    second = run_momentum_shadow_observation(
        spec_path,
        sample_workspace,
        as_of=pd.Timestamp("2027-01-01T00:00:00Z").to_pydatetime(),
    )
    assert second.status == "blocked"
    assert second.signal_log_path.read_text(encoding="utf-8") == text


def test_shadow_forward_ledger_is_idempotent(sample_workspace: Path) -> None:
    _write_data(sample_workspace, "qqq", 1.0)
    _write_data(sample_workspace, "tqqq", 2.5)
    spec_path = _write_spec(sample_workspace)
    last = pd.Timestamp(
        pd.read_csv(sample_workspace / "data/research/alpaca_minute/qqq_30m_alpaca_iex.csv")[
            "timestamp"
        ].iloc[-1]
    )
    as_of = (last + pd.Timedelta(hours=1)).to_pydatetime()

    first = run_momentum_shadow_observation(spec_path, sample_workspace, as_of=as_of)
    first_rows = first.forward_ledger_path.read_text(encoding="utf-8").splitlines()
    second = run_momentum_shadow_observation(spec_path, sample_workspace, as_of=as_of)

    assert second.forward_ledger_path.read_text(encoding="utf-8").splitlines() == first_rows


def test_historical_replay_does_not_count_as_forward_evidence(sample_workspace: Path) -> None:
    _write_data(sample_workspace, "qqq", 1.0)
    _write_data(sample_workspace, "tqqq", 2.5)
    spec_path = _write_spec(sample_workspace)
    payload = yaml.safe_load(spec_path.read_text(encoding="utf-8"))
    payload["notes"]["research_design"]["forward_epoch_utc"] = "2027-01-01T00:00:00+00:00"
    spec_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    last = pd.Timestamp(
        pd.read_csv(sample_workspace / "data/research/alpaca_minute/qqq_30m_alpaca_iex.csv")[
            "timestamp"
        ].iloc[-1]
    )

    result = run_momentum_shadow_observation(
        spec_path,
        sample_workspace,
        as_of=(last + pd.Timedelta(hours=1)).to_pydatetime(),
    )

    assert result.signal_count > 0
    assert not result.forward_ledger_path.exists()


def test_shadow_as_of_does_not_see_future_appended_bars(sample_workspace: Path) -> None:
    _write_data(sample_workspace, "qqq", 1.0)
    _write_data(sample_workspace, "tqqq", 2.5)
    spec_path = _write_spec(sample_workspace)
    as_of = pd.Timestamp("2026-02-20T20:00:00Z").to_pydatetime()
    first = run_momentum_shadow_observation(spec_path, sample_workspace, as_of=as_of)
    first_targets = json.loads(first.target_weights_path.read_text(encoding="utf-8"))[
        "target_weights"
    ]

    _append_day(sample_workspace, "qqq", 1.0, "2026-04-01")
    _append_day(sample_workspace, "tqqq", 2.5, "2026-04-01")
    second = run_momentum_shadow_observation(spec_path, sample_workspace, as_of=as_of)

    second_targets = json.loads(second.target_weights_path.read_text(encoding="utf-8"))[
        "target_weights"
    ]
    assert second_targets == first_targets


def test_shadow_blocks_frozen_prefix_mutation(sample_workspace: Path) -> None:
    _write_data(sample_workspace, "qqq", 1.0)
    _write_data(sample_workspace, "tqqq", 2.5)
    spec_path = _write_spec(sample_workspace)
    path = sample_workspace / "data/research/alpaca_minute/qqq_30m_alpaca_iex.csv"
    frame = pd.read_csv(path)
    frame.loc[0, "close"] = float(frame.loc[0, "close"]) + 1.0
    frame.to_csv(path, index=False)

    try:
        run_momentum_shadow_observation(spec_path, sample_workspace)
    except ValueError as exc:
        assert "frozen source prefix" in str(exc)
    else:
        raise AssertionError("historical prefix mutation must block observation")


def test_shadow_observation_blocks_latest_timestamp_mismatch(sample_workspace: Path) -> None:
    _write_data(sample_workspace, "qqq", 1.0)
    _write_data(sample_workspace, "tqqq", 2.5)
    target_path = sample_workspace / "data/research/alpaca_minute/tqqq_30m_alpaca_iex.csv"
    target = pd.read_csv(target_path).iloc[:-1]
    target.to_csv(target_path, index=False)
    spec_path = _write_spec(sample_workspace)

    try:
        run_momentum_shadow_observation(spec_path, sample_workspace)
    except ValueError as exc:
        assert "latest QQQ/TQQQ timestamps" in str(exc)
    else:
        raise AssertionError("latest timestamp mismatch must block shadow observation")


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
            ret = (0.001 if offset % 4 else -0.0002) * leverage
            close = price * (1 + ret)
            rows.append(
                {
                    "timestamp": timestamp.tz_convert("UTC"),
                    "open": price,
                    "high": max(price, close) * 1.001,
                    "low": min(price, close) * 0.999,
                    "close": close,
                    "volume": 100000,
                }
            )
            price = close
    pd.DataFrame(rows).to_csv(path, index=False)


def _write_spec(root: Path) -> Path:
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
    path = root / "strategy_specs/drafts/us_mom_minute_p1_003_frozen.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    return path


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


def _append_day(root: Path, symbol: str, leverage: float, day: str) -> None:
    path = root / "data/research/alpaca_minute" / f"{symbol}_30m_alpaca_iex.csv"
    existing = pd.read_csv(path)
    price = float(existing["close"].iloc[-1])
    rows = []
    for offset in range(13):
        timestamp = pd.Timestamp(day).tz_localize("America/New_York") + pd.Timedelta(
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
    pd.DataFrame(rows).to_csv(path, mode="a", header=False, index=False)
