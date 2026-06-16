from __future__ import annotations

import hashlib
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Any

import pandas as pd

from open_composer.models.strategy_spec import StrategySpec
from open_composer.strategy_versions import strategy_content_hash


@dataclass(frozen=True)
class ResearchCost:
    candidate_count: int
    walk_forward_candidate_count: int
    walk_forward_top_k: int | None
    walk_forward_folds: int
    estimated_candidate_evaluation_passes: int
    estimated_walk_forward_validation_passes: int
    estimated_walk_forward_selected_passes: int
    estimated_total_backtest_passes: int
    cost_model: str


def estimate_grid_research_cost(
    *,
    candidate_count: int,
    walk_forward_candidate_count: int,
    walk_forward_top_k: int | None,
    walk_forward_folds: int,
    candidate_passes_per_candidate: int = 3,
    selected_passes_per_fold: int = 2,
) -> ResearchCost:
    effective_folds = max(walk_forward_folds, 1)
    candidate_passes = candidate_count * candidate_passes_per_candidate
    walk_forward_validation_passes = walk_forward_candidate_count * effective_folds
    walk_forward_selected_passes = effective_folds * selected_passes_per_fold
    return ResearchCost(
        candidate_count=candidate_count,
        walk_forward_candidate_count=walk_forward_candidate_count,
        walk_forward_top_k=walk_forward_top_k,
        walk_forward_folds=effective_folds,
        estimated_candidate_evaluation_passes=candidate_passes,
        estimated_walk_forward_validation_passes=walk_forward_validation_passes,
        estimated_walk_forward_selected_passes=walk_forward_selected_passes,
        estimated_total_backtest_passes=(
            candidate_passes + walk_forward_validation_passes + walk_forward_selected_passes
        ),
        cost_model=(
            f"candidate_count * {candidate_passes_per_candidate} candidate passes + "
            "walk_forward_candidate_count * folds validation passes + "
            f"{selected_passes_per_fold} selected passes per fold"
        ),
    )


def runtime_payload(started_at: float, stages: dict[str, float]) -> dict[str, Any]:
    return {
        "total": round(perf_counter() - started_at, 6),
        "stages": {key: round(value, 6) for key, value in stages.items()},
    }


def frame_data_profile(
    frame: pd.DataFrame,
    *,
    symbol: str | None = None,
    timeframe: str | None = None,
    provider: str | None = None,
    feed: str | None = None,
    source_mode: str | None = None,
    path: str | Path | None = None,
) -> dict[str, Any]:
    timestamps = pd.to_datetime(frame["timestamp"], utc=True) if "timestamp" in frame else []
    first_timestamp = timestamps.iloc[0].isoformat() if len(timestamps) else None
    last_timestamp = timestamps.iloc[-1].isoformat() if len(timestamps) else None
    attrs = getattr(frame, "attrs", {})
    provider_value = attrs.get("data_source_provider") or provider
    feed_value = attrs.get("data_source_feed") or feed
    source_mode_value = attrs.get("data_source_mode") or source_mode
    path_value = attrs.get("data_source_path") or path
    acquisition_tier = data_acquisition_tier(
        data_source=str(provider_value or ""),
        source_mode=str(source_mode_value or ""),
        strict_live=source_mode_value == "live_fetch",
    )
    warnings = _data_profile_warnings(
        records=len(frame),
        feed=feed_value,
        source_mode=source_mode_value,
        first_timestamp=first_timestamp,
        last_timestamp=last_timestamp,
    )
    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "provider": provider_value,
        "feed": feed_value,
        "source_mode": source_mode_value,
        "path": str(path_value) if path_value is not None else None,
        "records": int(len(frame)),
        "first_timestamp": first_timestamp,
        "last_timestamp": last_timestamp,
        "data_as_of": last_timestamp,
        "profile_generated_at": datetime.now(UTC).isoformat(),
        "acquisition_tier": acquisition_tier,
        "cache_fallback": source_mode_value in {"cache", "cache_resampled"},
        "strict_live": source_mode_value == "live_fetch",
        "warnings": warnings,
    }


def combined_data_profile(profiles: list[dict[str, Any]]) -> dict[str, Any]:
    last_values = [item.get("last_timestamp") for item in profiles if item.get("last_timestamp")]
    first_values = [item.get("first_timestamp") for item in profiles if item.get("first_timestamp")]
    warnings: list[str] = []
    for item in profiles:
        warnings.extend(str(warning) for warning in item.get("warnings", []))
    providers = sorted({str(item.get("provider")) for item in profiles if item.get("provider")})
    feeds = sorted({str(item.get("feed")) for item in profiles if item.get("feed")})
    modes = sorted({str(item.get("source_mode")) for item in profiles if item.get("source_mode")})
    return {
        "symbols": [item.get("symbol") for item in profiles if item.get("symbol")],
        "provider": providers[0] if len(providers) == 1 else None,
        "providers": providers,
        "feed": feeds[0] if len(feeds) == 1 else None,
        "feeds": feeds,
        "source_mode": modes[0] if len(modes) == 1 else None,
        "source_modes": modes,
        "records": sum(int(item.get("records", 0) or 0) for item in profiles),
        "first_timestamp": min(first_values) if first_values else None,
        "last_timestamp": min(last_values) if last_values else None,
        "data_as_of": min(last_values) if last_values else None,
        "profile_generated_at": datetime.now(UTC).isoformat(),
        "acquisition_tier": combined_data_acquisition_tier(profiles),
        "cache_fallback": any(bool(item.get("cache_fallback")) for item in profiles),
        "strict_live": (
            all(bool(item.get("strict_live")) for item in profiles) if profiles else False
        ),
        "warnings": sorted(set(warnings)),
        "per_symbol": profiles,
    }


def data_acquisition_tier(
    *,
    data_source: str | None,
    source_mode: str | None,
    strict_live: bool = False,
) -> str:
    """Classify market data evidence for research and promotion gates."""
    source = (data_source or "").lower()
    mode = (source_mode or "").lower()
    if source == "sample" or "sample" in mode:
        return "sample_smoke"
    if "fixture" in mode or "fallback" in mode:
        return "fixture_replay"
    if strict_live or mode == "live_fetch":
        return "research_strict"
    if mode in {"cache", "cache_resampled", "materialized_history_cache"}:
        return "research_replay_cache"
    return "research_cross_check"


def combined_data_acquisition_tier(profiles: list[dict[str, Any]]) -> str:
    if not profiles:
        return "research_cross_check"
    tiers = [str(item.get("acquisition_tier") or "") for item in profiles]
    if any(tier == "sample_smoke" for tier in tiers):
        return "sample_smoke"
    if any(tier == "fixture_replay" for tier in tiers):
        return "fixture_replay"
    if all(tier == "research_strict" for tier in tiers):
        return "research_strict"
    if any(tier == "research_replay_cache" for tier in tiers):
        return "research_replay_cache"
    return "research_cross_check"


def research_brief(
    *,
    strategy_name: str,
    objective: str,
    hypothesis: str,
    constraints: list[str],
) -> dict[str, Any]:
    return {
        "strategy_name": strategy_name,
        "objective": objective,
        "hypothesis": hypothesis,
        "constraints": constraints,
    }


def search_space(
    *,
    family: str,
    candidate_count: int,
    parameter_ranges: dict[str, list[Any]],
    filters: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "family": family,
        "candidate_count": candidate_count,
        "parameter_ranges": parameter_ranges,
        "filters": filters or [],
    }


def research_run_manifest(
    *,
    root: Path,
    strategy: StrategySpec,
    source_path: Path,
    trial_count: int,
    search_space_payload: dict[str, Any],
    data_profile: dict[str, Any] | None = None,
    feature_packet_paths: list[str] | None = None,
    prompt_hash: str | None = None,
    runtime: dict[str, Any] | None = None,
) -> dict[str, Any]:
    git_commit, git_dirty = _git_state(root)
    data_path = data_profile.get("path") if data_profile else None
    return {
        "git_commit": git_commit,
        "git_dirty": git_dirty,
        "strategy_name": strategy.name,
        "spec_hash": strategy_content_hash(strategy),
        "source_path": workspace_relative_path(source_path, root),
        "data_profile": data_profile or {},
        "data_path_hash": _file_hash(root / str(data_path)) if data_path else None,
        "feature_packet_hashes": {
            path: _file_hash(root / path) for path in feature_packet_paths or []
        },
        "prompt_hash": prompt_hash,
        "trial_count": trial_count,
        "search_space": search_space_payload,
        "runtime": runtime or {},
    }


def hypothesis_ledger(
    *,
    hypothesis: str,
    visible_evidence: list[str],
    hidden_evidence: list[str],
    counterevidence: list[str],
    conclusion: str,
) -> list[dict[str, Any]]:
    return [
        {
            "hypothesis": hypothesis,
            "visible_evidence": visible_evidence,
            "hidden_evidence": hidden_evidence,
            "counterevidence": counterevidence,
            "conclusion": conclusion,
        }
    ]


def _data_profile_warnings(
    *,
    records: int,
    feed: object,
    source_mode: object,
    first_timestamp: str | None,
    last_timestamp: str | None,
) -> list[str]:
    warnings: list[str] = []
    if records == 0:
        warnings.append("no_rows_available")
    if source_mode == "cache":
        warnings.append("cache_data_used")
    if source_mode == "cache_resampled":
        warnings.append("cache_resampled_from_intraday")
    if str(feed or "").lower() == "iex":
        warnings.append("iex_feed_not_full_market_sip")
    if first_timestamp is None or last_timestamp is None:
        warnings.append("missing_data_timestamps")
    return warnings


def _git_state(root: Path) -> tuple[str | None, bool | None]:
    commit = _git_output(root, "rev-parse", "HEAD")
    status = _git_output(root, "status", "--short")
    return commit, bool(status) if status is not None else None


def _git_output(root: Path, *args: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def _file_hash(path: Path) -> str | None:
    if not path.exists() or not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def workspace_relative_path(path: Path, base: Path) -> str:
    try:
        return path.relative_to(base).as_posix()
    except ValueError:
        return path.as_posix()
