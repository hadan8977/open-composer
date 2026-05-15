from __future__ import annotations

import json
import math
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from open_composer.config import project_root
from open_composer.models.strategy_spec import load_strategy_spec
from open_composer.research.metadata import workspace_relative_path
from open_composer.storage import write_json


class RegimeMatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    window_end: str
    similarity: float
    macro_count: int
    news_count: int
    positive_news_count: int
    negative_news_count: int
    market_note: str


class RegimeSearchReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    strategy_name: str
    strategy_path: str
    target_window_end: str
    lookback_months: int
    matches: list[RegimeMatch]


def search_similar_regimes(
    spec_path: Path,
    *,
    target_window_end: datetime | None = None,
    lookback_months: int = 6,
    top_k: int = 5,
    root: Path | None = None,
) -> RegimeSearchReport:
    base = root or project_root()
    spec = load_strategy_spec(spec_path)
    records = _load_records(base)
    if not records:
        records = _load_fixture_records(base)
    target_end = target_window_end or max(_record_time(record) for record in records)
    windows = _monthly_windows(records)
    target_key = target_end.strftime("%Y-%m")
    target_vector = windows.get(target_key) or _aggregate(records)
    matches = []
    for key, vector in sorted(windows.items()):
        if key == target_key:
            continue
        similarity = _cosine(target_vector, vector)
        matches.append(
            RegimeMatch(
                window_end=key,
                similarity=similarity,
                macro_count=int(vector[0]),
                news_count=int(vector[1]),
                positive_news_count=int(vector[2]),
                negative_news_count=int(vector[3]),
                market_note=_market_note(vector),
            )
        )
    matches = sorted(matches, key=lambda item: item.similarity, reverse=True)[:top_k]
    report = RegimeSearchReport(
        strategy_name=spec.name,
        strategy_path=workspace_relative_path(spec_path, base),
        target_window_end=target_key,
        lookback_months=lookback_months,
        matches=matches,
    )
    out_path = base / "reports" / "regime_search" / f"{spec.name}.json"
    md_path = out_path.with_suffix(".md")
    write_json(out_path, report)
    md_path.write_text(_render_markdown(report), encoding="utf-8")
    return report


def _load_records(root: Path) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for folder in [root / "data" / "raw" / "macro", root / "data" / "raw" / "events"]:
        if not folder.exists():
            continue
        for path in sorted(folder.rglob("*.jsonl")):
            records.extend(_load_jsonl(path))
    return records


def _load_fixture_records(root: Path) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for path in [
        root / "data" / "fixtures" / "capabilities" / "fred_macro.jsonl",
        root / "data" / "fixtures" / "capabilities" / "alpha_vantage_news.jsonl",
    ]:
        records.extend(_load_jsonl(path))
    return records


def _load_jsonl(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    rows: list[dict[str, object]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            raw = json.loads(line)
            if isinstance(raw, dict):
                rows.append(raw)
    return rows


def _monthly_windows(records: list[dict[str, object]]) -> dict[str, list[float]]:
    grouped: dict[str, list[dict[str, object]]] = {}
    for record in records:
        grouped.setdefault(_record_time(record).strftime("%Y-%m"), []).append(record)
    return {key: _aggregate(values) for key, values in grouped.items()}


def _aggregate(records: list[dict[str, object]]) -> list[float]:
    macro = [
        record for record in records if str(record.get("event_type")) == "macro_series_observation"
    ]
    news = [record for record in records if str(record.get("event_type")) == "news_sentiment"]
    positive = [record for record in news if record.get("sentiment") == "positive"]
    negative = [record for record in news if record.get("sentiment") == "negative"]
    relevance = sum(float(record.get("relevance_score") or 0.0) for record in records)
    macro_value = sum(
        float(record.get("value") or record.get("raw", {}).get("value") or 0.0) for record in macro
    )
    return [
        float(len(macro)),
        float(len(news)),
        float(len(positive)),
        float(len(negative)),
        relevance,
        macro_value,
    ]


def _record_time(record: dict[str, object]) -> datetime:
    value = str(record.get("published_at") or record.get("fetched_at"))
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(left * right for left, right in zip(a, b, strict=True))
    norm_a = math.sqrt(sum(value * value for value in a))
    norm_b = math.sqrt(sum(value * value for value in b))
    if not norm_a or not norm_b:
        return 0.0
    return dot / (norm_a * norm_b)


def _market_note(vector: list[float]) -> str:
    if vector[2] > vector[3]:
        return "positive news skew"
    if vector[3] > vector[2]:
        return "negative news skew"
    return "neutral or macro-only window"


def _render_markdown(report: RegimeSearchReport) -> str:
    lines = [
        f"# Regime Search: {report.strategy_name}",
        "",
        f"- Strategy path: `{report.strategy_path}`",
        f"- Target window: `{report.target_window_end}`",
        f"- Lookback months: `{report.lookback_months}`",
        "",
        "| Window | Similarity | Macro | News | Positive | Negative | Note |",
        "|---|---|---|---|---|---|---|",
    ]
    for match in report.matches:
        lines.append(
            "| "
            f"{match.window_end} | {match.similarity:.3f} | {match.macro_count} | "
            f"{match.news_count} | {match.positive_news_count} | "
            f"{match.negative_news_count} | {match.market_note} |"
        )
    return "\n".join(lines) + "\n"
