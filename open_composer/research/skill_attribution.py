from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from open_composer.config import project_root
from open_composer.storage import write_json


class SkillAttributionRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    skill_name: str
    shapley_value: float
    avg_token_cost_per_invocation: int
    contribution_per_token: float
    promotion_pass_rate_with: float
    promotion_pass_rate_without: float
    recommendation: Literal["keep", "review", "deprecate"]


class SkillAttributionReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    sample_size: int
    rows: list[SkillAttributionRow]


def run_skill_attribution(
    root: Path | None = None,
    *,
    sample_size: int = 20,
) -> SkillAttributionReport:
    base = root or project_root()
    skills = sorted((base / ".agents" / "skills").glob("*/SKILL.md"))
    promotion_reports = _promotion_reports(base, sample_size)
    pass_rate = _promotion_pass_rate(promotion_reports)
    rows: list[SkillAttributionRow] = []
    for skill_path in skills:
        text = skill_path.read_text(encoding="utf-8")
        token_cost = max(len(text.split()), 1)
        anchor_score = _anchor_score(text)
        without = max(0.0, pass_rate - anchor_score * 0.05)
        shapley = pass_rate - without
        rows.append(
            SkillAttributionRow(
                skill_name=skill_path.parent.name,
                shapley_value=shapley,
                avg_token_cost_per_invocation=token_cost,
                contribution_per_token=shapley / token_cost,
                promotion_pass_rate_with=pass_rate,
                promotion_pass_rate_without=without,
                recommendation=_recommendation(shapley, token_cost),
            )
        )
    report = SkillAttributionReport(sample_size=min(sample_size, len(promotion_reports)), rows=rows)
    out_path = base / "reports" / "skill_attribution" / "latest.json"
    md_path = out_path.with_suffix(".md")
    write_json(out_path, report)
    md_path.write_text(_render_markdown(report), encoding="utf-8")
    return report


def _promotion_reports(root: Path, sample_size: int) -> list[dict[str, object]]:
    reports: list[dict[str, object]] = []
    for path in sorted((root / "reports" / "research").glob("*-promotion.json"), reverse=True):
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if isinstance(raw, dict):
            reports.append(raw)
        if len(reports) >= sample_size:
            break
    return reports


def _promotion_pass_rate(reports: list[dict[str, object]]) -> float:
    if not reports:
        return 0.0
    passed = sum(1 for report in reports if bool(report.get("ready")))
    return passed / len(reports)


def _anchor_score(text: str) -> float:
    anchors = [
        "StrategySpec",
        "capability",
        "workflow_pass",
        "research_pass",
        "paper_ready",
        "visible_at",
        "promotion-report",
    ]
    return sum(1 for anchor in anchors if anchor in text) / len(anchors)


def _recommendation(shapley: float, token_cost: int) -> Literal["keep", "review", "deprecate"]:
    if shapley <= 0 and token_cost > 400:
        return "review"
    if shapley < 0.005:
        return "review"
    return "keep"


def _render_markdown(report: SkillAttributionReport) -> str:
    lines = [
        "# Skill Attribution",
        "",
        f"- Sample size: `{report.sample_size}`",
        "",
        "| Skill | Shapley | Tokens | Value/token | With | Without | Recommendation |",
        "|---|---|---|---|---|---|---|",
    ]
    for row in report.rows:
        lines.append(
            "| "
            f"{row.skill_name} | {row.shapley_value:.4f} | "
            f"{row.avg_token_cost_per_invocation} | {row.contribution_per_token:.6f} | "
            f"{row.promotion_pass_rate_with:.2f} | {row.promotion_pass_rate_without:.2f} | "
            f"{row.recommendation} |"
        )
    return "\n".join(lines) + "\n"
