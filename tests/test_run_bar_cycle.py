"""Tests for scripts/run_bar_cycle.py (BarCycleRunner) and
open_composer.execution.schedule (``oc paper schedule-suggest``).

Plan: docs/plan-step-14-timeframe-agnostic-bar-cycle-runner-2026-09-11.zh.md
section "Tests required". Three layers:

* Static + dynamic observation-mode guarantees -- the plan doc's own
  required check ("BarCycleRunner observation mode asserts zero broker/
  order calls"): the Step 14 execution modules never reference the broker
  order-write path at all (source-text check), ``_require_observation_mode``
  rejects a paper_auto/alpaca_paper spec before any bar fetch/engine/sync
  call happens, and the one subprocess call this script ever makes
  (``oc paper sync-account``) is read-only and spied on directly.
* Fast synthetic tests with a fake BarSource/SignalEngine (injected via
  monkeypatch on the module-level resolve_bar_source/resolve_engine, since
  run_one_cycle calls them by bare name) -- dispatch, runner-level
  idempotency (a no-op ComputeResult, target_weights=None, must never touch
  the target-weights artifact -- the bug caught during development), and
  output artifact schema (bar-cycle day-log, engine state, target-weights
  JSON).
* One real-local-archive-data integration test running the actual product
  spec (strategy_specs/drafts/us_reversal_trend_1h_h26.yaml) end-to-end
  through run_one_cycle with ArchiveBarSource + ReversalTrendSignalEngine,
  skipif no local SIP archive -- this repo's own smoke test for the first
  non-daily product connection.
"""

from __future__ import annotations

import importlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd
import pytest
import yaml

from open_composer.adapters.data.sip_parquet import default_sip_root
from open_composer.execution.bar_source import ArchiveBarSource
from open_composer.execution.schedule import suggest_crontab_line
from open_composer.execution.signal_engine import (
    ComputeResult,
    EngineState,
    ModelRankingSignalEngine,
    ReversalTrendSignalEngine,
    TargetWeights,
)
from open_composer.models.strategy_spec import StrategySpec, load_strategy_spec

run_bar_cycle = importlib.import_module("scripts.run_bar_cycle")

_UNIVERSE = ["AAA", "BBB"]

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _event_spec_dict(
    name: str = "test_bar_cycle_event",
    *,
    mode: str = "manual_signal",
    broker: str = "none",
    timeframe: str = "1h",
) -> dict[str, Any]:
    return {
        "name": name,
        "description": "Test-only event_driven_capacity_book spec for run_bar_cycle.py tests.",
        "timeframe": timeframe,
        "universe": _UNIVERSE,
        "lifecycle": "draft",
        "position_direction": "long_only",
        "entry": {"all": ["close > 0"], "any": []},
        "exit": {"all": [], "any": ["close <= 0"]},
        "risk": {
            "max_trades_per_day": 50,
            "max_position_weight": 0.10,
            "stop_loss_pct": None,
            "take_profit_pct": None,
        },
        "portfolio": {
            "mode": "event_driven_capacity_book",
            "event_signal_engine": "reversal_trend_engine",
            "event_holding_bars": 26,
            "event_exit_rule": "time_stop",
            "event_signal_set": "bull_and_recl",
            "event_max_positions": 10,
            "event_position_weight": 0.10,
        },
        "execution": {
            "backend": "python_reference",
            "mode": mode,
            "signal_on": "bar_close",
            "fill_assumption": "next_bar_open",
            "broker": broker,
        },
        "data": {"source": "alpaca", "feed": "sip"},
    }


def _write_spec_yaml(tmp_path: Path, raw: dict[str, Any], filename: str = "spec.yaml") -> Path:
    path = tmp_path / filename
    path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
    # Fail fast (inside the test, not deep inside run_one_cycle) if the fixture itself is invalid.
    StrategySpec.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
    return path


def _fake_bars_panel(as_of: pd.Timestamp) -> pd.DataFrame:
    rows = []
    for symbol in _UNIVERSE:
        rows.append(
            {
                "symbol": symbol,
                "timestamp": as_of - pd.Timedelta(hours=1),
                "bar_close_ts": as_of,
                "open": 100.0,
                "high": 101.0,
                "low": 99.0,
                "close": 100.5,
                "volume": 1000,
                "feed": "sip",
            }
        )
    return pd.DataFrame(rows)


@dataclass
class _FakeBarSource:
    frame: pd.DataFrame
    calls: list[dict[str, Any]] = field(default_factory=list)

    def get_bars(self, symbols, timeframe, start, end, *, session="regular", as_of=None):
        self.calls.append(
            {
                "symbols": list(symbols),
                "timeframe": timeframe,
                "start": start,
                "end": end,
                "session": session,
                "as_of": as_of,
            }
        )
        return self.frame


@dataclass
class _FakeEngine:
    results: list[ComputeResult]
    calls: list[dict[str, Any]] = field(default_factory=list)

    def compute(self, bars_panel, spec, state, as_of, *, root=None):
        result = self.results[len(self.calls)]
        self.calls.append({"as_of": as_of, "root": root, "state": state})
        return result


def _install_fakes(
    monkeypatch: pytest.MonkeyPatch, *, bar_source: _FakeBarSource, engine: _FakeEngine
) -> None:
    monkeypatch.setattr(run_bar_cycle, "resolve_bar_source", lambda data_source: bar_source)
    monkeypatch.setattr(run_bar_cycle, "resolve_engine", lambda spec_path, spec: engine)


# ---------------------------------------------------------------------------
# Observation-mode-only guarantee: static + dynamic
# ---------------------------------------------------------------------------

_BROKER_ORDER_SYMBOLS = (
    "submit_paper_order",
    "PaperOrderError",
    "TradingClient",
    "MarketOrderRequest",
    "LimitOrderRequest",
    "alpaca.trading",
)


@pytest.mark.parametrize(
    "module_path",
    [
        "scripts/run_bar_cycle.py",
        "open_composer/execution/bar_source.py",
        "open_composer/execution/signal_engine.py",
        "open_composer/execution/schedule.py",
    ],
)
def test_bar_cycle_modules_never_reference_the_broker_order_write_path(
    repo_root: Path, module_path: str
) -> None:
    source = (repo_root / module_path).read_text(encoding="utf-8")
    for symbol in _BROKER_ORDER_SYMBOLS:
        assert symbol not in source, f"{module_path} must never reference {symbol!r}"


def test_require_observation_mode_accepts_manual_signal_none() -> None:
    spec = StrategySpec.model_validate(_event_spec_dict())
    run_bar_cycle._require_observation_mode(spec)  # must not raise


def test_require_observation_mode_rejects_paper_auto() -> None:
    spec = StrategySpec.model_validate(_event_spec_dict(mode="paper_auto", broker="alpaca_paper"))
    with pytest.raises(run_bar_cycle.BarCycleError):
        run_bar_cycle._require_observation_mode(spec)


def test_run_one_cycle_rejects_paper_auto_before_touching_bars_or_engine_or_sync(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The observation-mode guard must fire before resolve_engine,
    resolve_bar_source, or the sync-account subprocess call -- i.e. a
    disallowed spec never reaches any code path that could touch bars,
    signals, or the broker.
    """
    spec_path = _write_spec_yaml(
        tmp_path, _event_spec_dict(mode="paper_auto", broker="alpaca_paper")
    )

    def _boom(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("must not be called when execution mode is not observation-only")

    monkeypatch.setattr(run_bar_cycle, "resolve_engine", _boom)
    monkeypatch.setattr(run_bar_cycle, "resolve_bar_source", _boom)
    monkeypatch.setattr(run_bar_cycle, "_sync_account", _boom)

    with pytest.raises(run_bar_cycle.BarCycleError):
        run_bar_cycle.run_one_cycle(
            spec_path=spec_path,
            root=tmp_path,
            as_of=pd.Timestamp("2024-01-02T15:30:00Z"),
            data_source="archive",
            history_lookback_days=30,
            oc_cmd=["true"],
            skip_sync_account=False,
        )


def test_sync_account_is_the_only_subprocess_call_and_is_read_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    spec_path = _write_spec_yaml(tmp_path, _event_spec_dict())
    as_of = pd.Timestamp("2024-01-02T15:30:00Z")
    bars = _fake_bars_panel(as_of)
    tw = TargetWeights(
        weights={"AAA": 0.10},
        rebalance_session=as_of.isoformat(),
        signal_session=as_of.isoformat(),
        metadata={},
    )
    result = ComputeResult(
        target_weights=tw,
        signals=[],
        new_state=EngineState(engine="reversal_trend_engine", last_bar_close_ts=as_of.isoformat()),
        artifacts_written_by_engine=False,
        notes=["synthetic"],
    )
    _install_fakes(
        monkeypatch, bar_source=_FakeBarSource(bars), engine=_FakeEngine(results=[result])
    )

    recorded_calls: list[list[str]] = []
    real_run = run_bar_cycle.subprocess.run

    def _spy_run(argv, **kwargs):  # noqa: ANN001
        recorded_calls.append(list(argv))
        import subprocess as _subprocess

        return _subprocess.CompletedProcess(argv, 0, stdout="ok\n", stderr="")

    monkeypatch.setattr(run_bar_cycle.subprocess, "run", _spy_run)

    run_bar_cycle.run_one_cycle(
        spec_path=spec_path,
        root=tmp_path,
        as_of=as_of,
        data_source="archive",
        history_lookback_days=30,
        oc_cmd=["uv", "run", "oc"],
        skip_sync_account=False,
    )

    assert len(recorded_calls) == 1, f"expected exactly one subprocess call, got {recorded_calls}"
    argv = recorded_calls[0]
    assert argv[-2:] == ["paper", "sync-account"]
    forbidden = ("submit", "order", "authorize", "kill-switch")
    joined = " ".join(argv).lower()
    for term in forbidden:
        assert term not in joined, f"unexpected broker-adjacent subprocess call: {argv}"
    assert real_run is not run_bar_cycle.subprocess.run  # sanity: monkeypatch really applied


# ---------------------------------------------------------------------------
# resolve_engine / resolve_bar_source dispatch
# ---------------------------------------------------------------------------


def test_resolve_engine_dispatches_model_ranking_portfolio(tmp_path: Path) -> None:
    spec = StrategySpec.model_validate(
        {
            **_event_spec_dict(timeframe="daily"),
            "portfolio": {
                "mode": "model_ranking_portfolio",
                "candidate_artifact_dir": "candidates/x",
                "universe_rule": "pit_adv_top_n",
                "universe_top_n": 5,
                "feature_set_id": "daily_only",
                "label_horizon_days": 21,
                "top_k": 2,
                "rebalance": "weekly_friday_close_monday_open",
                "weighting": "equal_weight",
                "hedge": "none",
            },
        }
    )
    engine = run_bar_cycle.resolve_engine(tmp_path / "spec.yaml", spec)
    assert isinstance(engine, ModelRankingSignalEngine)


def test_resolve_engine_dispatches_reversal_trend_engine(tmp_path: Path) -> None:
    spec = StrategySpec.model_validate(_event_spec_dict())
    engine = run_bar_cycle.resolve_engine(tmp_path / "spec.yaml", spec)
    assert isinstance(engine, ReversalTrendSignalEngine)


def test_resolve_engine_rejects_unknown_event_signal_engine(tmp_path: Path) -> None:
    raw = _event_spec_dict()
    raw["portfolio"]["event_signal_engine"] = "not_a_real_engine"
    spec = StrategySpec.model_validate(raw)
    with pytest.raises(run_bar_cycle.BarCycleError):
        run_bar_cycle.resolve_engine(tmp_path / "spec.yaml", spec)


def test_resolve_bar_source_dispatch() -> None:
    from open_composer.execution.bar_source import AlpacaBarSource

    assert isinstance(run_bar_cycle.resolve_bar_source("archive"), ArchiveBarSource)
    assert isinstance(run_bar_cycle.resolve_bar_source("alpaca"), AlpacaBarSource)
    with pytest.raises(run_bar_cycle.BarCycleError):
        run_bar_cycle.resolve_bar_source("not_a_real_source")


# ---------------------------------------------------------------------------
# Runner-level idempotency + artifact schema (fake bar source / engine)
# ---------------------------------------------------------------------------


def test_no_op_compute_result_never_touches_the_target_weights_artifact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    spec_path = _write_spec_yaml(tmp_path, _event_spec_dict())
    spec = load_strategy_spec(spec_path)
    as_of = pd.Timestamp("2024-01-02T15:30:00Z")
    bars = _fake_bars_panel(as_of)

    first_tw = TargetWeights(
        weights={"AAA": 0.10, "BBB": 0.10},
        rebalance_session=as_of.isoformat(),
        signal_session=as_of.isoformat(),
        metadata={"bootstrap": True},
    )
    first_state = EngineState(
        engine="reversal_trend_engine", last_bar_close_ts=as_of.isoformat(), payload={"n": 1}
    )
    first_result = ComputeResult(
        target_weights=first_tw,
        signals=[],
        new_state=first_state,
        artifacts_written_by_engine=False,
        notes=["bootstrap"],
    )
    second_state = EngineState(
        engine="reversal_trend_engine", last_bar_close_ts=as_of.isoformat(), payload={"n": 1}
    )
    second_result = ComputeResult(
        target_weights=None,
        signals=[],
        new_state=second_state,
        artifacts_written_by_engine=False,
        notes=["no-op: no new bar since last run"],
    )
    fake_engine = _FakeEngine(results=[first_result, second_result])
    _install_fakes(monkeypatch, bar_source=_FakeBarSource(bars), engine=fake_engine)

    record1 = run_bar_cycle.run_one_cycle(
        spec_path=spec_path,
        root=tmp_path,
        as_of=as_of,
        data_source="archive",
        history_lookback_days=30,
        oc_cmd=["true"],
        skip_sync_account=True,
    )
    tw_path = tmp_path / "reports" / "execution" / f"{spec.name}-target-weights.json"
    assert record1["target_weights_written"] is True
    payload_after_first = json.loads(tw_path.read_text(encoding="utf-8"))
    held_after_first = {
        row["symbol"] for row in payload_after_first["target_weights"] if row["selected"]
    }
    assert held_after_first == {"AAA", "BBB"}

    record2 = run_bar_cycle.run_one_cycle(
        spec_path=spec_path,
        root=tmp_path,
        as_of=as_of,
        data_source="archive",
        history_lookback_days=30,
        oc_cmd=["true"],
        skip_sync_account=True,
    )
    assert record2["target_weights_written"] is False
    payload_after_second = json.loads(tw_path.read_text(encoding="utf-8"))
    # Untouched byte-for-byte: a no-op result must never blank/overwrite the
    # previously-written book (the bug caught during development).
    assert payload_after_second == payload_after_first


def test_bar_cycle_day_log_schema(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    spec_path = _write_spec_yaml(tmp_path, _event_spec_dict())
    spec = load_strategy_spec(spec_path)
    as_of = pd.Timestamp("2024-01-02T15:30:00Z")
    bars = _fake_bars_panel(as_of)
    tw = TargetWeights(
        weights={"AAA": 0.10},
        rebalance_session=as_of.isoformat(),
        signal_session=as_of.isoformat(),
        metadata={},
    )
    result = ComputeResult(
        target_weights=tw,
        signals=[],
        new_state=EngineState(engine="reversal_trend_engine", last_bar_close_ts=as_of.isoformat()),
        artifacts_written_by_engine=False,
        notes=["synthetic"],
    )
    _install_fakes(
        monkeypatch, bar_source=_FakeBarSource(bars), engine=_FakeEngine(results=[result])
    )

    record = run_bar_cycle.run_one_cycle(
        spec_path=spec_path,
        root=tmp_path,
        as_of=as_of,
        data_source="archive",
        history_lookback_days=30,
        oc_cmd=["true"],
        skip_sync_account=True,
    )
    assert record["status"] == "ok"
    assert record["paper_order_authorization"] is False
    assert record["broker_writes"] is False
    assert "safety_note" in record

    log_path = run_bar_cycle._bar_cycle_log_path(tmp_path, spec.name, spec.timeframe, as_of)
    assert log_path.name == f"{spec.name}-1h-20240102.json"
    payload = json.loads(log_path.read_text(encoding="utf-8"))
    assert payload["report_type"] == "bar_cycle_day"
    assert payload["strategy"] == spec.name
    assert payload["timeframe"] == "1h"
    assert payload["date"] == "2024-01-02"
    assert len(payload["records"]) == 1
    assert payload["records"][0]["paper_order_authorization"] is False
    assert payload["records"][0]["broker_writes"] is False

    # A second cycle on the *same day* (e.g. hourly cron firing every 30
    # minutes) accumulates into the same day-file rather than overwriting it.
    later = as_of + pd.Timedelta(minutes=30)
    result2 = ComputeResult(
        target_weights=None,
        signals=[],
        new_state=EngineState(engine="reversal_trend_engine", last_bar_close_ts=as_of.isoformat()),
        artifacts_written_by_engine=False,
        notes=["no-op"],
    )
    fake_engine2 = _FakeEngine(results=[result2])
    _install_fakes(monkeypatch, bar_source=_FakeBarSource(bars), engine=fake_engine2)
    run_bar_cycle.run_one_cycle(
        spec_path=spec_path,
        root=tmp_path,
        as_of=later,
        data_source="archive",
        history_lookback_days=30,
        oc_cmd=["true"],
        skip_sync_account=True,
    )
    payload_after_second = json.loads(log_path.read_text(encoding="utf-8"))
    assert len(payload_after_second["records"]) == 2


def test_state_json_schema(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    spec_path = _write_spec_yaml(tmp_path, _event_spec_dict())
    spec = load_strategy_spec(spec_path)
    as_of = pd.Timestamp("2024-01-02T15:30:00Z")
    bars = _fake_bars_panel(as_of)
    tw = TargetWeights(
        weights={"AAA": 0.10},
        rebalance_session=as_of.isoformat(),
        signal_session=as_of.isoformat(),
        metadata={},
    )
    new_state = EngineState(
        engine="reversal_trend_engine",
        last_bar_close_ts=as_of.isoformat(),
        payload={"bootstrapped": True, "admitted_trade_keys": ["AAA|2024-01-02T14:30:00+00:00"]},
    )
    result = ComputeResult(
        target_weights=tw, signals=[], new_state=new_state, artifacts_written_by_engine=False
    )
    _install_fakes(
        monkeypatch, bar_source=_FakeBarSource(bars), engine=_FakeEngine(results=[result])
    )

    run_bar_cycle.run_one_cycle(
        spec_path=spec_path,
        root=tmp_path,
        as_of=as_of,
        data_source="archive",
        history_lookback_days=30,
        oc_cmd=["true"],
        skip_sync_account=True,
    )
    state_path = run_bar_cycle._state_path(tmp_path, spec.name)
    payload = json.loads(state_path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 1
    assert payload["engine"] == "reversal_trend_engine"
    assert payload["last_bar_close_ts"] == as_of.isoformat()
    assert payload["payload"]["bootstrapped"] is True


# ---------------------------------------------------------------------------
# small pure-function unit tests
# ---------------------------------------------------------------------------


def test_parse_as_of_defaults_to_now() -> None:
    before = pd.Timestamp.now(tz="UTC")
    parsed = run_bar_cycle._parse_as_of(None)
    after = pd.Timestamp.now(tz="UTC")
    assert before <= parsed <= after


def test_parse_as_of_localizes_naive_and_converts_aware() -> None:
    naive = run_bar_cycle._parse_as_of("2024-01-02T15:30:00")
    assert naive == pd.Timestamp("2024-01-02T15:30:00", tz="UTC")
    aware = run_bar_cycle._parse_as_of("2024-01-02T10:30:00-05:00")
    assert aware == pd.Timestamp("2024-01-02T15:30:00", tz="UTC")


def test_default_data_source() -> None:
    assert run_bar_cycle._default_data_source(False, None) == "archive"
    assert run_bar_cycle._default_data_source(True, None) == "alpaca"
    assert run_bar_cycle._default_data_source(True, "archive") == "archive"


# ---------------------------------------------------------------------------
# oc paper schedule-suggest (open_composer.execution.schedule)
# ---------------------------------------------------------------------------


def test_suggest_crontab_line_daily_matches_the_live_installed_cron_schedule(
    tmp_path: Path,
) -> None:
    # "0 23 * * 1-5" is the exact schedule field of the two already-installed
    # live crontab entries (us_model_ranking_portfolio_top50,
    # us_recent_high_return_top50) -- this suggestion must never drift from it.
    spec = StrategySpec.model_validate(_event_spec_dict(timeframe="daily"))
    line = suggest_crontab_line(tmp_path / "spec.yaml", spec, root=tmp_path)
    assert line.startswith("0 23 * * 1-5 ")
    assert "run_bar_cycle.py" in line
    assert "\n" not in line  # must be copy-pasteable as one crontab line


def test_suggest_crontab_line_intraday_uses_a_30_minute_session_poll(tmp_path: Path) -> None:
    spec = StrategySpec.model_validate(_event_spec_dict(timeframe="1h"))
    line = suggest_crontab_line(tmp_path / "spec.yaml", spec, root=tmp_path)
    assert line.startswith("*/30 13-21 * * 1-5 ")
    assert "--spec" in line
    assert spec.name in line


def test_suggest_crontab_line_1m_recommends_follow_mode_not_cron(tmp_path: Path) -> None:
    spec = StrategySpec.model_validate(_event_spec_dict(timeframe="1m"))
    line = suggest_crontab_line(tmp_path / "spec.yaml", spec, root=tmp_path)
    assert "--follow" in line
    assert "no fixed cron line" in line


def test_suggest_crontab_line_weekly_reports_unsupported(tmp_path: Path) -> None:
    spec = StrategySpec.model_validate(_event_spec_dict(timeframe="weekly"))
    line = suggest_crontab_line(tmp_path / "spec.yaml", spec, root=tmp_path)
    assert "not supported" in line


def test_suggest_crontab_line_spec_path_is_relative_to_root_when_possible(tmp_path: Path) -> None:
    (tmp_path / "strategy_specs" / "drafts").mkdir(parents=True)
    spec_path = tmp_path / "strategy_specs" / "drafts" / "x.yaml"
    spec_path.write_text("placeholder", encoding="utf-8")
    spec = StrategySpec.model_validate(_event_spec_dict(timeframe="daily"))
    line = suggest_crontab_line(spec_path, spec, root=tmp_path)
    assert "--spec strategy_specs/drafts/x.yaml" in line
    assert str(tmp_path) not in line.split("--spec ")[1]


# ---------------------------------------------------------------------------
# Real local-archive-data integration test / smoke test for the actual
# product spec (strategy_specs/drafts/us_reversal_trend_1h_h26.yaml)
# ---------------------------------------------------------------------------

_ARCHIVE_PRESENT = (default_sip_root() / "minute").is_dir()
_REAL_SPEC_PATH = (
    Path(__file__).resolve().parents[1]
    / "strategy_specs"
    / "drafts"
    / "us_reversal_trend_1h_h26.yaml"
)


@pytest.mark.skipif(
    not _ARCHIVE_PRESENT, reason="local SIP minute archive (data/sip/minute) is not present"
)
def test_real_product_spec_runs_end_to_end_in_observation_mode(tmp_path: Path) -> None:
    """The actual us_reversal_trend_1h_h26.yaml spec, through the real
    ArchiveBarSource + ReversalTrendSignalEngine, end to end via
    run_one_cycle -- a short lookback window to keep this fast. Writes only
    under a throwaway tmp_path root, never the real reports/ tree.
    """
    spec = load_strategy_spec(_REAL_SPEC_PATH)
    as_of = pd.Timestamp("2026-09-09T20:00:00Z")

    record = run_bar_cycle.run_one_cycle(
        spec_path=_REAL_SPEC_PATH,
        root=tmp_path,
        as_of=as_of,
        data_source="archive",
        history_lookback_days=90,
        oc_cmd=["true"],
        skip_sync_account=True,
    )
    assert record["status"] == "ok"
    assert record["paper_order_authorization"] is False
    assert record["broker_writes"] is False
    assert record["bar_count"] > 0

    state_path = run_bar_cycle._state_path(tmp_path, spec.name)
    assert state_path.is_file()
    state_payload = json.loads(state_path.read_text(encoding="utf-8"))
    assert state_payload["engine"] == "reversal_trend_engine"
    assert state_payload["payload"]["bootstrapped"] is True

    tw_path = tmp_path / "reports" / "execution" / f"{spec.name}-target-weights.json"
    assert tw_path.is_file()
    tw_payload = json.loads(tw_path.read_text(encoding="utf-8"))
    for row in tw_payload["target_weights"]:
        assert row["target_weight"] <= 0.10 + 1e-9

    # A second call at the identical as_of is a harmless no-op (idempotency)
    # and must not perturb the artifact already on disk.
    before = tw_path.read_text(encoding="utf-8")
    record2 = run_bar_cycle.run_one_cycle(
        spec_path=_REAL_SPEC_PATH,
        root=tmp_path,
        as_of=as_of,
        data_source="archive",
        history_lookback_days=90,
        oc_cmd=["true"],
        skip_sync_account=True,
    )
    assert record2["target_weights_written"] is False
    assert tw_path.read_text(encoding="utf-8") == before
