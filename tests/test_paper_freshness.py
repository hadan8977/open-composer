from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml

from open_composer.execution_policy import require_orderable_execution_policy
from open_composer.models.signal import Signal
from open_composer.models.strategy_spec import load_strategy_spec
from open_composer.paper_freshness import require_fresh_paper_signal, require_paper_order_window


def test_intraday_paper_signal_requires_current_session_bar() -> None:
    observed_at = datetime(2026, 7, 20, 15, 0, tzinfo=UTC)
    signal = _signal(
        timeframe="15m",
        timestamp=datetime(2026, 7, 20, 14, 55, tzinfo=UTC),
        created_at=datetime(2026, 7, 20, 14, 59, tzinfo=UTC),
    )

    require_fresh_paper_signal(signal, observed_at=observed_at)

    signal.timestamp = datetime(2026, 7, 20, 13, 0, tzinfo=UTC)
    with pytest.raises(ValueError, match="market timestamp is stale"):
        require_fresh_paper_signal(signal, observed_at=observed_at)


def test_intraday_paper_signal_blocks_non_trading_day() -> None:
    observed_at = datetime(2026, 7, 19, 15, 0, tzinfo=UTC)
    signal = _signal(
        timeframe="15m",
        timestamp=datetime(2026, 7, 19, 14, 55, tzinfo=UTC),
        created_at=datetime(2026, 7, 19, 14, 59, tzinfo=UTC),
    )

    with pytest.raises(ValueError, match="non-trading day"):
        require_fresh_paper_signal(signal, observed_at=observed_at)


def test_daily_paper_signal_requires_latest_completed_session() -> None:
    observed_at = datetime(2026, 7, 20, 13, 0, tzinfo=UTC)
    signal = _signal(
        timeframe="daily",
        timestamp=datetime(2026, 7, 17, 4, 0, tzinfo=UTC),
        created_at=datetime(2026, 7, 20, 12, 59, tzinfo=UTC),
    )

    require_fresh_paper_signal(signal, observed_at=observed_at)

    signal.timestamp = datetime(2026, 7, 16, 4, 0, tzinfo=UTC)
    with pytest.raises(ValueError, match="latest completed"):
        require_fresh_paper_signal(signal, observed_at=observed_at)


def test_opening_policy_uses_conservative_pre_0928_window(sample_workspace: Path) -> None:
    source = sample_workspace / "strategy_specs" / "drafts" / "fixture_pullback_15m.yaml"
    raw = yaml.safe_load(source.read_text(encoding="utf-8"))
    raw["lifecycle"] = "active"
    raw["execution"]["mode"] = "paper_auto"
    raw["execution"]["broker"] = "alpaca_paper"
    source.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
    spec = load_strategy_spec(source)
    policy_path = (
        sample_workspace
        / "reports"
        / "harness"
        / "execution"
        / f"{spec.name}-execution-policy.json"
    )
    policy_path.parent.mkdir(parents=True, exist_ok=True)
    policy_path.write_text(
        '{"policy_id":"loo-window","order_style":"loo_limit","time_in_force":"opg"}',
        encoding="utf-8",
    )
    policy = require_orderable_execution_policy(spec, sample_workspace)

    require_paper_order_window(
        spec,
        policy,
        observed_at=datetime(2026, 7, 20, 13, 25, tzinfo=UTC),
    )
    with pytest.raises(ValueError, match="09:20 through 09:27"):
        require_paper_order_window(
            spec,
            policy,
            observed_at=datetime(2026, 7, 20, 13, 28, tzinfo=UTC),
        )
    with pytest.raises(ValueError, match="non-trading day"):
        require_paper_order_window(
            spec,
            policy,
            observed_at=datetime(2026, 7, 19, 13, 25, tzinfo=UTC),
        )


def _signal(
    *,
    timeframe: str,
    timestamp: datetime,
    created_at: datetime,
) -> Signal:
    return Signal(
        id="sig_freshness",
        run_id="run_freshness",
        strategy_name="freshness_strategy",
        strategy_id="freshness_strategy",
        version_id="ver_0123456789ab",
        spec_hash="0" * 64,
        symbol="SPY",
        timeframe=timeframe,
        timestamp=timestamp,
        action="entry",
        side="buy",
        source="test",
        price=100.0,
        conditions=[],
        lifecycle="active",
        execution_mode="paper_auto",
        fill_assumption="next_bar_open",
        created_at=created_at,
    )
