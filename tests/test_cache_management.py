from __future__ import annotations

from pathlib import Path

from open_composer.cache import (
    build_cache_inventory,
    clean_cache_targets,
    resolve_clean_target_keys,
)


def test_cache_inventory_separates_cleanable_and_protected_reports(
    sample_workspace: Path,
) -> None:
    generated = sample_workspace / "reports" / "backtests" / "tmp.md"
    generated.write_text("generated\n", encoding="utf-8")
    protected = sample_workspace / "reports" / "research" / "intraday-product-reflection.md"
    protected.write_text("tracked example\n", encoding="utf-8")

    inventory = {item.target.key: item for item in build_cache_inventory(sample_workspace)}

    reports = inventory["reports"]
    assert reports.cleanable_files == 1
    assert reports.protected_files == 6
    assert reports.cleanable_bytes == generated.stat().st_size


def test_cache_clean_defaults_to_data_cache_and_reports_only(sample_workspace: Path) -> None:
    cache_file = sample_workspace / "data" / "cache" / "qqq_15m_iex.csv"
    cache_file.write_text("timestamp,open\n", encoding="utf-8")
    report_file = sample_workspace / "reports" / "backtests" / "run.md"
    report_file.write_text("report\n", encoding="utf-8")
    signal_file = sample_workspace / "signal_logs" / "run.jsonl"
    signal_file.write_text("{}\n", encoding="utf-8")
    protected = sample_workspace / "reports" / "research" / "intraday-product-reflection.md"
    protected.write_text("tracked example\n", encoding="utf-8")
    paper_control = sample_workspace / "reports" / "paper" / "kill_switch.json"
    notification_log = sample_workspace / "reports" / "notifications" / "log.jsonl"

    selected = resolve_clean_target_keys()
    dry_run = clean_cache_targets(sample_workspace, selected, dry_run=True)

    assert dry_run.files == 2
    assert cache_file.exists()
    assert report_file.exists()
    assert signal_file.exists()
    assert protected.exists()
    assert paper_control.exists()
    assert notification_log.exists()

    applied = clean_cache_targets(sample_workspace, selected, dry_run=False)

    assert applied.files == 2
    assert not cache_file.exists()
    assert not report_file.exists()
    assert signal_file.exists()
    assert protected.exists()
    assert paper_control.exists()
    assert notification_log.exists()
    assert applied.protected_files == 6


def test_cache_clean_all_runtime_includes_evidence_logs(sample_workspace: Path) -> None:
    feature_file = sample_workspace / "feature_logs" / "packet.jsonl"
    feature_file.write_text("{}\n", encoding="utf-8")
    event_file = sample_workspace / "event_logs" / "events.jsonl"
    event_file.write_text("{}\n", encoding="utf-8")

    selected = resolve_clean_target_keys(all_runtime=True)
    result = clean_cache_targets(sample_workspace, selected, dry_run=False)

    assert "feature_logs" in selected
    assert "event_logs" in selected
    assert result.files == 2
    assert not feature_file.exists()
    assert not event_file.exists()
