from __future__ import annotations

from pathlib import Path

from open_composer.adapters.data import load_ohlcv_for_spec
from open_composer.config import project_root, run_id
from open_composer.engines.signal_engine import build_signal, signal_masks
from open_composer.feature_packets import (
    should_auto_emit_context_features,
    write_context_feature_packet,
)
from open_composer.models.signal import Signal
from open_composer.models.strategy_spec import load_strategy_spec
from open_composer.reports.writer import write_scan_report
from open_composer.storage import append_jsonl
from open_composer.strategy_versions import register_strategy_version


def run_scan(
    spec_path: Path,
    root: Path | None = None,
    refresh_data: bool = False,
) -> list[Signal]:
    base = root or project_root()
    spec = load_strategy_spec(spec_path)
    version = register_strategy_version(spec_path, base, created_by="scan")
    frame = load_ohlcv_for_spec(spec, base, refresh=refresh_data)
    entry_mask, exit_mask = signal_masks(spec, frame, root=base)
    current_run_id = run_id(f"scan-{spec.name}")
    latest = frame.iloc[-1]
    timestamp = latest["timestamp"].to_pydatetime()
    signals: list[Signal] = []

    if bool(entry_mask.iloc[-1]):
        signals.append(
            build_signal(
                spec,
                current_run_id,
                timestamp,
                "entry",
                "scan",
                float(latest["close"]),
                version_id=version.version_id,
                spec_hash=version.content_hash,
                target_weight=(
                    spec.risk.max_position_weight
                    if spec.portfolio.mode == "single_symbol"
                    else None
                ),
            )
        )
    elif bool(exit_mask.iloc[-1]):
        signals.append(
            build_signal(
                spec,
                current_run_id,
                timestamp,
                "exit",
                "scan",
                float(latest["close"]),
                version_id=version.version_id,
                spec_hash=version.content_hash,
                target_weight=0.0 if spec.portfolio.mode == "single_symbol" else None,
            )
        )

    log_path = base / "signal_logs" / f"{current_run_id}.jsonl"
    report_path = base / "reports" / "scans" / f"{current_run_id}.md"
    append_jsonl(log_path, signals)
    if should_auto_emit_context_features(spec):
        for signal in signals:
            write_context_feature_packet(signal.id, base)
    write_scan_report(
        report_path,
        current_run_id,
        spec,
        signals,
        version_id=version.version_id,
        spec_hash=version.content_hash,
        root=base,
    )
    return signals
