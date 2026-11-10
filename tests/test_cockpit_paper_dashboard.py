"""Presentation updates cannot change published money or hide new actual books."""

import copy
import json
import threading
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace

import pytest

from open_composer.cockpit.data.paper_dashboard import build_paper_dashboard, find_ledger_detail

NOW = datetime(2026, 10, 27, 10, tzinfo=UTC)


def overview():
    return {
        "available": True,
        "through_session": "2026-10-26",
        "snapshot": {
            "at_end": "2026-10-27T04:20:03+00:00",
            "capital_usd": 120000,
            "pnl_usd": 1234.56,
            "return_pct": 1.0288,
            "adjustment_usd": 3.45,
            "rows": [
                {
                    "id": "six/BASE",
                    "label": "BASE",
                    "capital_usd": 20000,
                    "pnl_usd": -103.44,
                    "return_pct": -0.5172,
                    "status": "实际账本",
                },
                {
                    "id": "legacy/rotation",
                    "label": "S1",
                    "capital_usd": 15000,
                    "pnl_usd": 507.28,
                    "return_pct": 3.3818667,
                    "status": "实际账本",
                },
                {
                    "id": "F1",
                    "label": "F1",
                    "capital_usd": 1000000,
                    "pnl_usd": 24824.96,
                    "return_pct": 2.482496,
                    "status": "实际账本 · 计划归属待核",
                },
            ],
        },
    }


def trial(task_id="BASE-CURRENT-INITIALIZATION-20261019", **changes):
    values = dict(
        task_id=task_id,
        label="Ridge stock model",
        status="running",
        service_phase="waiting_market_open",
        observed_at=NOW,
        service_observed_at=NOW,
        market_as_of="2026-10-27",
        capital_usd=999999,
        net_pnl_usd=888888,
        net_return_pct=77,
    )
    values.update(changes)
    return SimpleNamespace(**values)


def test_runtime_metadata_never_replaces_accounting_money_or_dates():
    original = overview()
    before = copy.deepcopy(original)
    model = trial()
    dashboard = build_paper_dashboard(original, trials=[model], now=NOW)
    row = dashboard["rows"][0]
    assert dashboard["snapshot"] == before["snapshot"]
    assert original == before
    assert row["pnl_usd"] == -103.44 and row["return_pct"] == -0.5172
    assert row["capital_usd"] == 20000
    assert row["status_label"] == "待开盘"
    assert row["source_id"] == model.task_id and row["source_kind"] == "trial"
    assert row["market_as_of"] == "2026-10-26"
    assert row["observed_at"] == before["snapshot"]["at_end"]
    assert row["runtime_observed_at"] == NOW.isoformat()
    assert row["href"] == "/paper/ledger/six/BASE"
    assert dashboard["snapshot_label"] == "10-27 04:20 UTC"
    json.dumps(dashboard, allow_nan=False)


def test_new_actual_records_are_visible_without_expanding_totals():
    model = trial("NEW-MODEL-20261027")
    report = SimpleNamespace(
        strategies=[
            SimpleNamespace(
                name="new_sleeve",
                label="New sleeve",
                authorization=SimpleNamespace(state="authorized"),
                generated_at=NOW,
            ),
        ],
        account_books=[
            SimpleNamespace(
                account="new_account",
                book_id="sample:F3",
                label="F3",
                status="current",
                observed_at=NOW,
                market_as_of=date(2026, 10, 26),
                net_pnl_usd=123,
            ),
        ],
        validation_trials=[model],
    )
    original = overview()
    dashboard = build_paper_dashboard(original, report, now=NOW)
    assert dashboard["snapshot"] == original["snapshot"]
    added = dashboard["rows"][3:]
    assert {r["id"] for r in added} == {
        "trial/NEW-MODEL-20261027",
        "legacy/new_sleeve",
        "book/new_account",
    }
    assert all(r["status_label"] == "等待估值" for r in added)
    assert all(r["pnl_usd"] is r["return_pct"] is r["capital_usd"] is None for r in added)
    assert all(r["observed_at"] is None and r["market_as_of"] is None for r in added)
    json.dumps(dashboard, allow_nan=False)


def test_configuration_only_and_never_started_records_are_not_actual_strategies():
    report = {
        "strategies": [
            {"name": "observer", "authorization": {"state": "observation_only"}},
        ],
        "account_books": [
            {"account": "observer", "status": "observation_only", "observed_at": NOW},
        ],
        "validation_trials": [
            trial("NOT-STARTED", status="not_started", service_phase=None),
            trial("CONFIG", status="configuration_only"),
        ],
        "intraday_configurations": [{"name": "configured", "status": "configuration_only"}],
    }
    dashboard = build_paper_dashboard(overview(), report, now=NOW)
    assert len(dashboard["rows"]) == 3


def test_explicit_policy_binding_supports_arbitrary_new_policy_names():
    model = trial("UNRELATED-RESEARCH-TASK")
    dashboard = build_paper_dashboard(
        overview(), trials=[{"trial": model, "policy": "NEW_POLICY"}], now=NOW
    )
    assert dashboard["rows"][-1]["id"] == "six/NEW_POLICY"
    detail = find_ledger_detail(
        dashboard, "six/NEW_POLICY", trials=[{"trial": model, "policy": "NEW_POLICY"}]
    )
    assert detail["trial"] is model
    assert detail["row"]["pnl_usd"] is None


@pytest.mark.parametrize("ledger_id", [None, "models/NEW_MODEL"])
def test_registered_identity_survives_publication_without_duplicate_rows(tmp_path, ledger_id):
    from open_composer.cockpit.data.paper_trials import load_validation_trials

    task_id = "UNRELATED-RESEARCH-TASK-20261027"
    config = tmp_path / "config/paper-validation-dashboard.json"
    config.parent.mkdir()
    snapshot = tmp_path / "reports/paper/validation/new.json"
    snapshot.parent.mkdir(parents=True)
    config.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "candidates": [
                    {
                        "task_id": task_id,
                        "policy": "NEW_MODEL",
                        "ledger_id": ledger_id,
                        "snapshot": str(snapshot.relative_to(tmp_path)),
                    }
                ],
            }
        )
    )
    snapshot.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "task_id": task_id,
                "mode": "paper",
                "status": "starting",
                "observed_at_utc": NOW.isoformat(),
            }
        )
    )
    (registered,) = load_validation_trials(tmp_path, now=NOW)
    assert registered.policy == "NEW_MODEL" and registered.ledger_id == ledger_id
    identity = ledger_id or "six/NEW_MODEL"
    before = build_paper_dashboard(overview(), trials=[registered], now=NOW)
    pending = [r for r in before["rows"] if r["source_id"] == task_id]
    assert len(pending) == 1 and pending[0]["id"] == identity
    assert pending[0]["pnl_usd"] is None and pending[0]["status_label"] == "等待估值"

    published = overview()
    published["snapshot"]["rows"].append(
        dict(
            id=identity,
            label="New model",
            capital_usd=20000,
            pnl_usd=50,
            return_pct=0.25,
            status="实际账本",
        )
    )
    # Wrapping the dataclass must also retain its explicit ledger identity.
    trials = [{"trial": registered}]
    after = build_paper_dashboard(published, trials=trials, now=NOW)
    matched = [r for r in after["rows"] if r["source_id"] == task_id]
    assert len(matched) == 1 and len(after["rows"]) == len(before["rows"])
    assert matched[0]["id"] == identity and matched[0]["href"] == pending[0]["href"]
    assert matched[0]["pnl_usd"] == 50 and matched[0]["return_pct"] == 0.25
    assert after["snapshot"] == published["snapshot"]
    assert find_ledger_detail(after, identity, trials=trials)["trial"] is registered


def test_legacy_task_identity_matching_prefers_longest_tokens_and_avoids_substrings():
    original = overview()
    original["snapshot"]["rows"].append(
        dict(original["snapshot"]["rows"][0], id="six/BASE_STATE_BUDGET", label="STATE")
    )
    state = trial("BASE-STATE-BUDGET-PAPER-20261027")
    unrelated = trial("DATABASE-RESEARCH-20261027")
    dashboard = build_paper_dashboard(original, trials=[state, unrelated], now=NOW)
    rows = {r["id"]: r for r in dashboard["rows"]}
    assert rows["six/BASE"]["source_kind"] == "ledger"
    assert rows["six/BASE_STATE_BUDGET"]["source_id"] == state.task_id
    assert rows["trial/DATABASE-RESEARCH-20261027"]["pnl_usd"] is None


def test_native_detail_resolves_the_same_account_and_legacy_sources():
    sleeve = SimpleNamespace(name="rotation", authorization=SimpleNamespace(state="authorized"))
    book = SimpleNamespace(account="quant1", book_id="demo:F1", status="current", observed_at=NOW)
    report = SimpleNamespace(strategies=[sleeve], account_books=[book])
    dashboard = build_paper_dashboard(overview(), report, now=NOW)
    legacy = find_ledger_detail(dashboard, "legacy/rotation", report)
    account = find_ledger_detail(dashboard, "F1", report)
    assert legacy["sleeve"] is sleeve
    assert legacy["row"]["source_href"] == "/paper/rotation"
    assert account["book"] is book
    assert account["row"]["pnl_usd"] == 24824.96
    assert find_ledger_detail(dashboard, "not-a-ledger", report) is None


def test_retired_rows_keep_contribution_and_retired_status():
    original = overview()
    original["snapshot"]["rows"][1].update(status="已退出", capital_usd=None, return_pct=None)
    report = {"strategies": [{"name": "rotation", "authorization": {"state": "authorized"}}]}
    row = build_paper_dashboard(original, report, now=NOW)["rows"][1]
    assert row["status_label"] == "已退出"
    assert row["pnl_usd"] == 507.28 and row["return_pct"] is None


def test_snapshot_age_uses_valuation_time_instead_of_report_generation():
    original = overview()
    original["snapshot"]["at_end"] = (NOW - timedelta(hours=37)).isoformat()
    report = {"generated_at": NOW, "validation_trials": [trial()]}
    dashboard = build_paper_dashboard(original, report, now=NOW)
    assert dashboard["stale"] is True
    assert dashboard["snapshot_status"] == "stale"
    assert dashboard["snapshot_status_label"] == "待更新"
    assert dashboard["snapshot"]["pnl_usd"] == 1234.56


def test_unavailable_overview_keeps_new_actual_strategy_with_unknown_money():
    dashboard = build_paper_dashboard({"available": False}, trials=[trial()], now=NOW)
    assert dashboard["available"] is False
    assert dashboard["snapshot"] == {}
    assert len(dashboard["rows"]) == 1
    assert dashboard["rows"][0]["pnl_usd"] is None
    assert dashboard["snapshot_at"] is None


def test_ambiguous_account_alias_cannot_attach_two_books_to_one_accounting_row():
    report = {
        "account_books": [
            {"account": name, "book_id": "same:F1", "status": "current", "observed_at": NOW}
            for name in ("one", "two")
        ]
    }
    dashboard = build_paper_dashboard(overview(), report, now=NOW)
    rows = {r["id"]: r for r in dashboard["rows"]}
    assert rows["F1"]["source_kind"] == "ledger"
    assert rows["book/one"]["pnl_usd"] is None
    assert rows["book/two"]["pnl_usd"] is None


def test_report_cache_shares_reads_until_expiry_and_isolates_roots(tmp_path, monkeypatch):
    from open_composer.cockpit.data import paper_dashboard as module

    ticks = [100.0]
    reads = []

    def read(root):
        report = SimpleNamespace(root=root, generated_at=NOW, sequence=len(reads))
        reads.append(report)
        return report

    monkeypatch.setattr(module, "monotonic", lambda: ticks[0])
    monkeypatch.setattr(module, "_read_dashboard_report", read)
    first = module.get_dashboard_report(tmp_path / "one")
    ticks[0] = 129.9
    assert module.get_dashboard_report(tmp_path / "one" / ".") is first
    assert first.generated_at == NOW
    other = module.get_dashboard_report(tmp_path / "two")
    assert other is not first and len(reads) == 2
    ticks[0] = 130.0
    assert module.get_dashboard_report(tmp_path / "one") is not first
    assert len(reads) == 3
    assert module.get_dashboard_report(tmp_path / "two") is other


def test_simultaneous_report_requests_construct_only_once(tmp_path, monkeypatch):
    from open_composer.cockpit.data import paper_dashboard as module

    started = threading.Event()
    release = threading.Event()
    reports, reads = [], []
    expected = SimpleNamespace(generated_at=NOW)

    def read(root):
        reads.append(root)
        started.set()
        assert release.wait(timeout=2)
        return expected

    monkeypatch.setattr(module, "_read_dashboard_report", read)
    first = threading.Thread(target=lambda: reports.append(module.get_dashboard_report(tmp_path)))
    second = threading.Thread(target=lambda: reports.append(module.get_dashboard_report(tmp_path)))
    first.start()
    try:
        assert started.wait(timeout=2)
        second.start()
    finally:
        release.set()
        first.join(timeout=2)
        if second.ident is not None:
            second.join(timeout=2)
    assert not first.is_alive() and not second.is_alive()
    assert len(reads) == 1 and len(reports) == 2
    assert all(report is expected for report in reports)
