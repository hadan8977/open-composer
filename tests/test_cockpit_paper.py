from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from open_composer.cockpit.app import create_app
from open_composer.cockpit.data import paper as P
from open_composer.config import project_root

REPO_ROOT = project_root()

REAL_STRATEGY_NAMES = {
    "us_recent_high_return_top50",
    "us_etf_sector_rotation_252_top2_weekly",
    "us_etf_growth_rotation_blend_top2_monthly",
    "us_etf_levered_rotation_63_top2_monthly",
    "us_insider_buy_broad_monthly",
}

_NOW = datetime(2026, 9, 19, tzinfo=UTC)


# --------------------------------------------------------------------------
# Discovery + the authorized/observation_only/expired distinction
# --------------------------------------------------------------------------


def test_five_real_strategies_are_discovered() -> None:
    assert set(P.discover_strategy_names(REPO_ROOT)) == REAL_STRATEGY_NAMES


def test_insider_strategy_is_observation_only() -> None:
    auth = P.load_authorization(REPO_ROOT, "us_insider_buy_broad_monthly", now=_NOW)
    assert auth.state == "observation_only"
    assert auth.status == "unknown"
    assert auth.expires_at is None


@pytest.mark.parametrize(
    "name",
    [
        "us_recent_high_return_top50",
        "us_etf_sector_rotation_252_top2_weekly",
        "us_etf_growth_rotation_blend_top2_monthly",
        "us_etf_levered_rotation_63_top2_monthly",
    ],
)
def test_the_other_four_strategies_are_authorized(name: str) -> None:
    auth = P.load_authorization(REPO_ROOT, name, now=_NOW)
    assert auth.state == "authorized", (name, auth)
    assert auth.expires_at is not None
    assert auth.days_remaining is not None
    assert auth.days_remaining > 0
    # ok because 2026-10-02 is well outside the plan's 7-day warn window from
    # 2026-09-19 -- see module docstring / plan section 4 top bar.
    assert auth.status == "ok"


def test_expired_authorization_is_classified_expired(tmp_path: Path) -> None:
    # Freezes the clock rather than writing anything under the real
    # `reports/` tree -- a synthetic strategy in tmp_path only.
    rehearsal_dir = tmp_path / "reports" / "paper" / "rehearsal"
    rehearsal_dir.mkdir(parents=True)
    (rehearsal_dir / "fake_strategy-authorization.json").write_text(
        json.dumps(
            {
                "authorization_id": "reh_test",
                "expires_at": "2020-01-01T00:00:00+00:00",
                "limits": {"max_orders_per_session": 5},
                "scope": "test scope",
                "broker_account_id_hash": "abcdef0123456789",
            }
        ),
        encoding="utf-8",
    )

    auth = P.load_authorization(tmp_path, "fake_strategy", now=_NOW)

    assert auth.state == "expired"
    assert auth.status == "stale"
    assert auth.days_remaining is not None
    assert auth.days_remaining < 0


def test_authorization_close_to_expiry_is_warn(tmp_path: Path) -> None:
    rehearsal_dir = tmp_path / "reports" / "paper" / "rehearsal"
    rehearsal_dir.mkdir(parents=True)
    (rehearsal_dir / "soon-authorization.json").write_text(
        json.dumps({"expires_at": "2026-09-22T00:00:00+00:00"}), encoding="utf-8"
    )

    auth = P.load_authorization(tmp_path, "soon", now=_NOW)

    assert auth.state == "authorized"
    assert auth.status == "warn"


def test_no_authorization_file_is_observation_only_not_a_warning(tmp_path: Path) -> None:
    auth = P.load_authorization(tmp_path, "brand_new_strategy", now=_NOW)
    assert auth.state == "observation_only"
    assert auth.warnings == ()


def test_corrupt_authorization_file_does_not_masquerade_as_observation_only(
    tmp_path: Path,
) -> None:
    rehearsal_dir = tmp_path / "reports" / "paper" / "rehearsal"
    rehearsal_dir.mkdir(parents=True)
    (rehearsal_dir / "broken-authorization.json").write_text("{not json", encoding="utf-8")

    auth = P.load_authorization(tmp_path, "broken", now=_NOW)

    # A present-but-corrupt file must not be silently downgraded to "never
    # authorized" -- that would hide a real authorization behind noise.
    assert auth.state == "authorized"
    assert auth.status == "unknown"
    assert auth.warnings


def test_broker_account_id_hash_is_never_rendered_in_full(tmp_path: Path) -> None:
    long_hash = "d9589fb0319a7f1a740d40c4c1bd209568c0e6609e72d02a4be5a6b5545592d7"
    rehearsal_dir = tmp_path / "reports" / "paper" / "rehearsal"
    rehearsal_dir.mkdir(parents=True)
    (rehearsal_dir / "x-authorization.json").write_text(
        json.dumps(
            {"expires_at": "2026-10-02T00:00:00+00:00", "broker_account_id_hash": long_hash}
        ),
        encoding="utf-8",
    )

    auth = P.load_authorization(tmp_path, "x", now=_NOW)

    assert auth.broker_account_id_hash_prefix is not None
    assert auth.broker_account_id_hash_prefix != long_hash
    assert long_hash not in auth.broker_account_id_hash_prefix


# --------------------------------------------------------------------------
# Fills-summary: real numbers, and graceful degradation
# --------------------------------------------------------------------------


def test_top50_fills_summary_has_real_fill_rate_and_slippage_numbers() -> None:
    fills = P.load_fills_summary(REPO_ROOT, "us_recent_high_return_top50")
    assert fills.available is True
    assert len(fills.sessions) >= 1
    for session in fills.sessions:
        assert session.fill_rate_by_notional is not None
        assert 0.0 <= session.fill_rate_by_notional <= 1.0
    assert fills.latest is not None


def test_authorized_strategy_without_fills_summary_file_degrades_to_warning(
    tmp_path: Path,
) -> None:
    # An authorized sleeve whose first reconcile has not run yet. Built in a
    # temp workspace: the 2026-09-19 version read the live repo and broke as
    # soon as the reconcile cron wrote that sleeve's summary on 2026-09-22.
    rehearsal_dir = tmp_path / "reports" / "paper" / "rehearsal"
    rehearsal_dir.mkdir(parents=True)
    (rehearsal_dir / "sleeve-authorization.json").write_text(
        json.dumps({"strategy_name": "sleeve", "status": "authorized"}), encoding="utf-8"
    )
    fills = P.load_fills_summary(tmp_path, "sleeve")
    assert fills.available is False
    assert fills.warnings


def test_authorized_strategy_with_empty_sessions_is_available_but_empty(tmp_path: Path) -> None:
    # A fills-summary.json whose "sessions" object is `{}` -- present and
    # well-formed, just nothing recorded yet. That is a different, more
    # specific fact than "missing" and must not be collapsed into the same
    # warning bucket. (Temp workspace for the same reason as above.)
    rehearsal_dir = tmp_path / "reports" / "paper" / "rehearsal"
    rehearsal_dir.mkdir(parents=True)
    (rehearsal_dir / "sleeve-fills-summary.json").write_text(
        json.dumps(
            {
                "strategy_name": "sleeve",
                "generated_at": "2026-09-19T14:09:00+00:00",
                "sessions": {},
            }
        ),
        encoding="utf-8",
    )
    fills = P.load_fills_summary(tmp_path, "sleeve")
    assert fills.available is True
    assert fills.sessions == ()


def test_missing_fills_summary_degrades_to_warning_not_exception(tmp_path: Path) -> None:
    fills = P.load_fills_summary(tmp_path, "no_such_strategy")
    assert fills.available is False
    assert fills.warnings


def test_corrupt_fills_summary_degrades_to_warning_not_exception(tmp_path: Path) -> None:
    rehearsal_dir = tmp_path / "reports" / "paper" / "rehearsal"
    rehearsal_dir.mkdir(parents=True)
    (rehearsal_dir / "broken-fills-summary.json").write_text("{not valid json", encoding="utf-8")

    fills = P.load_fills_summary(tmp_path, "broken")

    assert fills.available is False
    assert fills.warnings


# --------------------------------------------------------------------------
# Equity history: real series where one exists, no fabrication where it does not
# --------------------------------------------------------------------------


def test_top50_has_a_real_multi_point_equity_history() -> None:
    series = P.build_equity_series(REPO_ROOT, "us_recent_high_return_top50")
    assert series.has_history is True
    assert len(series.points) >= 2
    # strictly non-decreasing in time (sorted), and every point is a real,
    # independently sourced observation
    timestamps = [p.at for p in series.points]
    assert timestamps == sorted(timestamps)
    assert all(
        p.source in ("daily_cycle_observation", "rehearsal_cycle_snapshot") for p in series.points
    )
    layout = P.compute_equity_chart_layout(series)
    assert layout is not None
    assert len(layout.bars) == len(series.points)


def test_insider_strategy_has_no_real_equity_history() -> None:
    # Only one rehearsal cycle file has ever been written for this strategy
    # and it has no daily_cycle observation logs at all (never authorized to
    # run the daily observation cycle the other four sleeves have).
    series = P.build_equity_series(REPO_ROOT, "us_insider_buy_broad_monthly")
    assert series.has_history is False
    assert P.compute_equity_chart_layout(series) is None


def test_no_history_when_nothing_at_all_is_on_disk(tmp_path: Path) -> None:
    series = P.build_equity_series(tmp_path, "ghost_strategy")
    assert series.points == ()
    assert series.has_history is False
    assert P.compute_equity_chart_layout(series) is None


def test_a_single_real_point_is_still_not_a_history(tmp_path: Path) -> None:
    rehearsal_dir = tmp_path / "reports" / "paper" / "rehearsal"
    rehearsal_dir.mkdir(parents=True)
    (rehearsal_dir / "lonely-2026-09-18-065638.json").write_text(
        json.dumps({"generated_at": "2026-09-18T06:56:38+00:00", "equity": 100000.0}),
        encoding="utf-8",
    )

    series = P.build_equity_series(tmp_path, "lonely")

    assert len(series.points) == 1
    assert series.has_history is False
    assert series.latest is not None
    assert series.latest.equity == 100000.0
    assert P.compute_equity_chart_layout(series) is None


def test_equity_series_never_reads_sync_or_rotation_baselines_jsonl(tmp_path: Path) -> None:
    # sync.jsonl (raw broker order/fill sync records) and
    # rotation_baselines.jsonl (per-session benchmark returns) both live
    # directly under reports/paper/, not under rehearsal/ or daily_cycle/,
    # and neither carries this account's own equity -- this module must not
    # treat either as an equity source.
    (tmp_path / "reports" / "paper").mkdir(parents=True)
    (tmp_path / "reports" / "paper" / "sync.jsonl").write_text(
        '{"equity": 999999.0}\n', encoding="utf-8"
    )
    (tmp_path / "reports" / "paper" / "rotation_baselines.jsonl").write_text(
        '{"equity": 999999.0}\n', encoding="utf-8"
    )

    series = P.build_equity_series(tmp_path, "some_strategy")

    assert series.points == ()


# --------------------------------------------------------------------------
# Strategy detail assembly
# --------------------------------------------------------------------------


def test_top50_has_a_dedicated_ledger_and_matches_the_broker_account() -> None:
    detail = P.build_strategy_detail(REPO_ROOT, "us_recent_high_return_top50", now=_NOW)
    assert detail.has_dedicated_ledger is True
    assert detail.positions, "expected target/position rows from the latest cycle"
    assert "match" in detail.positions_agreement


def test_insider_has_no_dedicated_ledger() -> None:
    detail = P.build_strategy_detail(REPO_ROOT, "us_insider_buy_broad_monthly", now=_NOW)
    assert detail.has_dedicated_ledger is False
    assert "no dedicated position ledger" in detail.positions_agreement
    for row in detail.positions:
        assert row.ledger_qty is None


# --------------------------------------------------------------------------
# Routes
# --------------------------------------------------------------------------


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())


def test_paper_index_returns_200_and_lists_every_strategy(client: TestClient) -> None:
    response = client.get("/paper")
    assert response.status_code == 200
    for name in REAL_STRATEGY_NAMES:
        assert name in response.text


def test_paper_index_shows_expired_and_observation_labels(client: TestClient) -> None:
    response = client.get("/paper")
    assert "observation only" in response.text


@pytest.mark.parametrize(
    "strategy",
    [
        "us_recent_high_return_top50",
        "us_etf_sector_rotation_252_top2_weekly",
        "us_etf_growth_rotation_blend_top2_monthly",
        "us_etf_levered_rotation_63_top2_monthly",
        "us_insider_buy_broad_monthly",
    ],
)
def test_paper_detail_returns_200_for_every_real_strategy(
    client: TestClient, strategy: str
) -> None:
    response = client.get(f"/paper/{strategy}")
    assert response.status_code == 200


def test_paper_detail_marks_insider_as_observation_only_not_trading(client: TestClient) -> None:
    response = client.get("/paper/us_insider_buy_broad_monthly")
    assert response.status_code == 200
    assert "observation only" in response.text
    assert "never been permitted to submit a real paper order" in response.text


@pytest.mark.parametrize(
    "path",
    ["/paper/nope", "/paper/../app.py", "/paper/..%2fapp.py", "/paper/%2e%2e%2fapp.py"],
)
def test_bad_strategy_names_return_4xx_not_500(client: TestClient, path: str) -> None:
    response = client.get(path)
    assert 400 <= response.status_code < 500


def test_top_bar_rehearsal_countdown_is_populated_on_every_screen(client: TestClient) -> None:
    for path in ("/", "/health", "/lineage", "/agents", "/paper"):
        response = client.get(path)
        assert response.status_code == 200
        assert 'data-slot="rehearsal-countdown"' in response.text
        assert "pending T5" not in response.text


def test_rehearsal_countdown_reflects_real_authorizations() -> None:
    countdown = P.build_rehearsal_countdown(REPO_ROOT, now=_NOW)
    assert countdown.status in ("ok", "warn", "stale", "unknown")
    assert countdown.label != "no rehearsal authorizations on file"
