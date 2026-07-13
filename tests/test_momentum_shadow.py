from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import yaml

from open_composer.adapters.execution.momentum_shadow import (
    run_momentum_shadow_observation,
)
from open_composer.research.research_cache_manifest import sha256_file


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
    payload["notes"]["research_design"]["source_hashes"] = {
        "QQQ": sha256_file(root / "data/research/alpaca_minute/qqq_30m_alpaca_iex.csv"),
        "TQQQ": sha256_file(root / "data/research/alpaca_minute/tqqq_30m_alpaca_iex.csv"),
    }
    path = root / "strategy_specs/drafts/us_mom_minute_p1_003_frozen.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    return path
