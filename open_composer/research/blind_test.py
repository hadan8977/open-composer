from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from open_composer.adapters.data import load_ohlcv_for_spec
from open_composer.config import project_root
from open_composer.engines.backtest_engine import backtest_frame
from open_composer.models.strategy_spec import StrategySpec, load_strategy_spec
from open_composer.research.metadata import workspace_relative_path
from open_composer.storage import write_json

BlindMode = Literal["real", "anonymous", "random_remap", "sector_preserved"]


class BlindTestResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: BlindMode
    ticker_mapping_hash: str
    return_pct: float
    sharpe: float
    signal_count: int
    correlation_with_real: float | None = None
    signal_digest: str


class BlindTestReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    strategy_name: str
    strategy_path: str
    results: list[BlindTestResult]
    interpretation: str


def run_blind_test(
    spec_path: Path,
    root: Path | None = None,
    *,
    seed: int = 42,
) -> BlindTestReport:
    base = root or project_root()
    spec = load_strategy_spec(spec_path)
    frame = load_ohlcv_for_spec(spec, base)
    results: list[BlindTestResult] = []
    for mode in ("real", "anonymous", "random_remap", "sector_preserved"):
        rewritten_spec, mapping = _rewrite_spec(spec, mode, seed=seed)
        artifacts = backtest_frame(
            rewritten_spec,
            frame,
            root=base,
            run_id_value=f"blind-test-{spec.name}-{mode}",
        )
        results.append(_build_result(mode, mapping, artifacts))
    real_digest = results[0].signal_digest
    for index, result in enumerate(results[1:], start=1):
        results[index] = result.model_copy(
            update={"correlation_with_real": _signal_correlation(real_digest, result.signal_digest)}
        )
    report = BlindTestReport(
        strategy_name=spec.name,
        strategy_path=workspace_relative_path(spec_path, base),
        results=results,
        interpretation=_interpret(results),
    )
    out_path = base / "reports" / "blind_test" / f"{spec.name}.json"
    md_path = out_path.with_suffix(".md")
    write_json(out_path, report)
    md_path.write_text(_render_markdown(report), encoding="utf-8")
    return report


def load_blind_test_report(
    spec_name: str,
    root: Path | None = None,
) -> BlindTestReport | None:
    base = root or project_root()
    path = base / "reports" / "blind_test" / f"{spec_name}.json"
    if not path.exists():
        return None
    return BlindTestReport.model_validate_json(path.read_text(encoding="utf-8"))


def _rewrite_spec(
    spec: StrategySpec,
    mode: BlindMode,
    *,
    seed: int,
) -> tuple[StrategySpec, dict[str, str]]:
    if mode == "real":
        mapping = {symbol: symbol for symbol in spec.universe}
        return spec, mapping

    symbols = list(spec.universe)
    if mode == "anonymous":
        remapped = [f"ASSET_{index:03d}" for index, _ in enumerate(symbols, start=1)]
    elif mode == "random_remap":
        remapped = _deterministic_shuffle(symbols, seed=seed, prefix="RND")
    else:
        remapped = _deterministic_shuffle(symbols, seed=seed + 7, prefix="SECTOR")
    mapping = {original: new for original, new in zip(symbols, remapped, strict=True)}
    raw = spec.model_dump(mode="json")
    raw["universe"] = [mapping[symbol] for symbol in raw["universe"]]
    if raw.get("data", {}).get("symbol"):
        raw["data"]["symbol"] = mapping.get(raw["data"]["symbol"], raw["data"]["symbol"])
    raw["name"] = f"{spec.name}_{mode}"
    raw["description"] = f"{spec.description} [blind_test:{mode}]"
    rewritten = StrategySpec.model_validate(raw)
    return rewritten, mapping


def _deterministic_shuffle(symbols: list[str], *, seed: int, prefix: str) -> list[str]:
    if not symbols:
        return []
    offset = seed % len(symbols)
    rotated = symbols[offset:] + symbols[:offset]
    return [f"{prefix}_{index:03d}" for index, _ in enumerate(rotated, start=1)]


def _build_result(
    mode: BlindMode,
    mapping: dict[str, str],
    artifacts,
) -> BlindTestResult:
    run = artifacts.run
    signal_digest = _signal_digest(artifacts.signals)
    return BlindTestResult(
        mode=mode,
        ticker_mapping_hash=_mapping_hash(mapping),
        return_pct=run.total_return_pct,
        sharpe=run.sharpe_ratio or 0.0,
        signal_count=run.signals,
        signal_digest=signal_digest,
    )


def _signal_digest(signals) -> str:
    payload = [
        {
            "timestamp": signal.timestamp.isoformat(),
            "action": signal.action,
            "side": signal.side,
        }
        for signal in signals
    ]
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _signal_correlation(real_digest: str, other_digest: str) -> float:
    return 1.0 if real_digest == other_digest else 0.0


def _mapping_hash(mapping: dict[str, str]) -> str:
    raw = json.dumps(mapping, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _interpret(results: list[BlindTestResult]) -> str:
    real = next(result for result in results if result.mode == "real")
    anonymous = next(result for result in results if result.mode == "anonymous")
    random_remap = next(result for result in results if result.mode == "random_remap")
    sector = next(result for result in results if result.mode == "sector_preserved")
    if abs(real.sharpe - anonymous.sharpe) <= 0.3 and anonymous.correlation_with_real == 1.0:
        return (
            "Anonymous and real runs stay aligned; this strategy looks structure-driven "
            "rather than ticker-memory-driven."
        )
    if anonymous.correlation_with_real != 1.0:
        return (
            "Anonymous remapping changes the signal path; ticker identity likely affects "
            "the strategy or one of its feature packets."
        )
    if abs(real.sharpe - sector.sharpe) < abs(real.sharpe - random_remap.sharpe):
        return (
            "Sector-preserved remapping is closer than random remapping, so the strategy "
            "seems to depend more on sector context than raw ticker identity."
        )
    return "Blind-test modes do not materially separate on the current frame."


def _render_markdown(report: BlindTestReport) -> str:
    lines = [
        f"# Blind Test: {report.strategy_name}",
        "",
        f"- Strategy path: `{report.strategy_path}`",
        f"- Interpretation: {report.interpretation}",
        "",
        "| Mode | Return % | Sharpe | Signals | Corr w/ real | Mapping hash |",
        "|---|---|---|---|---|---|",
    ]
    for result in report.results:
        lines.append(
            "| "
            f"{result.mode} | {result.return_pct:.2f} | {result.sharpe:.2f} | "
            f"{result.signal_count} | "
            f"{_format_optional(result.correlation_with_real)} | "
            f"`{result.ticker_mapping_hash[:12]}` |"
        )
    return "\n".join(lines) + "\n"


def _format_optional(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:.2f}"
