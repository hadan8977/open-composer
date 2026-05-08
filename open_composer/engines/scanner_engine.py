from __future__ import annotations

from pathlib import Path

from open_composer.adapters.data import load_ohlcv_for_spec
from open_composer.config import project_root, run_id
from open_composer.engines.signal_engine import build_signal, signal_masks
from open_composer.models.signal import Signal
from open_composer.models.strategy_spec import load_strategy_spec
from open_composer.reports.writer import write_scan_report
from open_composer.storage import append_jsonl


def run_scan(
    spec_path: Path,
    root: Path | None = None,
    refresh_data: bool = False,
) -> list[Signal]:
    base = root or project_root()
    spec = load_strategy_spec(spec_path)
    frame = load_ohlcv_for_spec(spec, base, refresh=refresh_data)
    entry_mask, exit_mask = signal_masks(spec, frame)
    current_run_id = run_id(f"scan-{spec.name}")
    latest = frame.iloc[-1]
    timestamp = latest["timestamp"].to_pydatetime()
    signals: list[Signal] = []

    if bool(entry_mask.iloc[-1]):
        signals.append(
            build_signal(spec, current_run_id, timestamp, "entry", "scan", float(latest["close"]))
        )
    elif bool(exit_mask.iloc[-1]):
        signals.append(
            build_signal(spec, current_run_id, timestamp, "exit", "scan", float(latest["close"]))
        )

    log_path = base / "signal_logs" / f"{current_run_id}.jsonl"
    report_path = base / "reports" / "scans" / f"{current_run_id}.md"
    append_jsonl(log_path, signals)
    write_scan_report(report_path, current_run_id, spec, signals)
    return signals
