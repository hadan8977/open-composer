"""Owner-facing wording: business names and the internal-code lint.

The owner (2026-10-06) could not read the daily e-mail: it was full of task
codes (``T-75``), strategy codes (``S3``, ``F1``, ``v1.2``), file paths and
pasted round logs.  Rules, in ``docs/owner-reporting.zh.md`` section 0:

* plain business language, no internal codes;
* no parenthetical process details;
* file paths and codes only in the evidence appendix (a ``## 附`` heading);
* round logs are attachments, never the report.

``lint_owner_text`` finds violations; the daily writer must reach zero errors
before committing.  ``apply_business_names`` is the send-time fallback for the
codes that have a fixed business name.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Strategy and account names as the owner knows them.
STRATEGY_NAMES: dict[str, str] = {
    "us_etf_sector_rotation_252_top2_weekly": "行业轮动",
    "us_etf_growth_rotation_blend_top2_monthly": "成长轮动",
    "us_etf_levered_rotation_63_top2_monthly": "杠杆轮动",
    "us_etf_eom_sector_blend_monthly": "月末效应",
}
STRATEGY_RULES: dict[str, str] = {
    "us_etf_sector_rotation_252_top2_weekly": "每周换成过去一年涨得最多的两个行业 ETF",
    "us_etf_growth_rotation_blend_top2_monthly": (
        "每月在成长类 ETF 里选两个，按波动控制仓位，余钱放短期国债"
    ),
    "us_etf_levered_rotation_63_top2_monthly": (
        "每月在 3 倍杠杆 ETF 里选过去三个月最强的两个，按波动控制仓位"
    ),
    "us_etf_eom_sector_blend_monthly": "月末前后买入，按历史季节性挑行业",
}
ACCOUNT_NAMES: dict[str, str] = {
    "quant1": "市场中性账户",
    "quant2": "SPY 增强账户",
}
ACCOUNT_RULES: dict[str, str] = {
    "quant1": "多空金额相等，余钱放短期国债",
    "quant2": "以 SPY 打底，再叠加 0.3 倍的多空",
}
# Live-track candidate ids -> business names.
CANDIDATE_NAMES: dict[str, str] = {
    "S1": "行业轮动",
    "S2": "成长轮动",
    "S3": "杠杆轮动",
    "C2": "月末效应",
    "V12F1": "股票多空（市场中性）",
    "V12F2": "股票多空（SPY 增强）",
}

# Send-time fallback: codes with one fixed business meaning.  Longest first so
# "v1.2 F1" is replaced before "F1".
_ALIASES: tuple[tuple[str, str], ...] = (
    (r"v1\.2\s*F1", "股票多空（市场中性）"),
    (r"v1\.2\s*F2", "股票多空（SPY 增强）"),
    (r"v1\.2", "股票多空组合"),
    (r"S1", "行业轮动"),
    (r"S2", "成长轮动"),
    (r"S3", "杠杆轮动"),
    (r"C2", "月末效应"),
    (r"F1", "股票多空（市场中性）"),
    (r"F2", "股票多空（SPY 增强）"),
    (r"quant1", "市场中性账户"),
    (r"quant2", "SPY 增强账户"),
)
_EDGE_L = r"(?<![A-Za-z0-9_./-])"
_EDGE_R = r"(?![A-Za-z0-9_])"

# Errors: codes and paths the owner cannot read.
_ERROR_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("任务或档案编号", re.compile(_EDGE_L + r"[THIEW]-?\d{8}-\d{2,3}[a-z]?" + _EDGE_R)),
    ("任务编号", re.compile(_EDGE_L + r"T-?\d{2,4}[a-z]?" + _EDGE_R)),
    (
        "策略或计划代号",
        re.compile(
            _EDGE_L
            + r"(?:S[1-4]\*?|C[12]\*?|F[1-3]|E[1-6]|P[0-6]|L[12]|D[1-9](?:\.\d)?|V[12]"
            + r"|A[1-3]|H[12]F|O[1-3]|R[1-3]|V12F[12])"
            + _EDGE_R
        ),
    ),
    ("版本代号", re.compile(_EDGE_L + r"v\d+\.\d+" + _EDGE_R)),
    ("账户代号", re.compile(_EDGE_L + r"quant[12]" + _EDGE_R)),
    ("代码或路径", re.compile(r"`[^`\n]+`")),
    ("文件路径", re.compile(r"(?:reports|docs|scripts|config|data|logs)/[\w./-]+")),
)
# Warnings: jargon and process words that need a rewrite, not a ban.
_WARN_WORDS: tuple[str, ...] = (
    "DSR",
    "PSR",
    "ΔSR",
    "ERC",
    "ICIR",
    "RankIC",
    "OOS",
    "主审",
    "执行轮",
    "简报",
    "子代理",
    "闸门",
    "额度",
    "限额",
    "队列",
    "预注册",
    "口径",
    "run_capped",
)
_PAREN_RE = re.compile(r"（([^（）\n]*)）|\(([^()\n]*)\)")
PAREN_WARN_CHARS = 30
APPENDIX_RE = re.compile(r"^#{1,3}\s*附")


@dataclass(frozen=True)
class LintFinding:
    line: int  # 1-based
    level: str  # "error" | "warn"
    kind: str
    text: str


def _body_lines(text: str) -> list[tuple[int, str]]:
    """Numbered lines before the evidence appendix; code and paths are allowed after it."""
    out: list[tuple[int, str]] = []
    for number, line in enumerate(text.splitlines(), start=1):
        if APPENDIX_RE.match(line):
            break
        out.append((number, line))
    return out


def lint_owner_text(text: str) -> list[LintFinding]:
    findings: list[LintFinding] = []
    for number, line in _body_lines(text):
        for kind, pattern in _ERROR_PATTERNS:
            for match in pattern.finditer(line):
                findings.append(LintFinding(number, "error", kind, match.group(0)))
        for word in _WARN_WORDS:
            if word in line:
                findings.append(LintFinding(number, "warn", "术语或内部用语", word))
        for match in _PAREN_RE.finditer(line):
            inner = match.group(1) if match.group(1) is not None else match.group(2)
            if len(inner) > PAREN_WARN_CHARS:
                findings.append(LintFinding(number, "warn", "括号里的长说明", inner[:40]))
    return findings


def lint_errors(text: str) -> list[LintFinding]:
    return [item for item in lint_owner_text(text) if item.level == "error"]


def format_findings(findings: list[LintFinding]) -> str:
    if not findings:
        return "ok: 没有内部代号、路径或长括号"
    return "\n".join(
        f"{item.level} 第 {item.line} 行 {item.kind}: {item.text}" for item in findings
    )


def apply_business_names(text: str) -> str:
    """Replace codes that have one fixed business name, outside the appendix only."""
    lines = text.splitlines(keepends=True)
    out: list[str] = []
    in_appendix = False
    for line in lines:
        if APPENDIX_RE.match(line):
            in_appendix = True
        if not in_appendix:
            for code, name in _ALIASES:
                line = re.sub(_EDGE_L + code + _EDGE_R, name, line)
        out.append(line)
    return "".join(out)


def strategy_name(name: str) -> str:
    return STRATEGY_NAMES.get(name, name)


def account_name(account: str) -> str:
    return ACCOUNT_NAMES.get(account, account)


def candidate_name(candidate_id: str, fallback: str | None = None) -> str:
    return CANDIDATE_NAMES.get(candidate_id, fallback or candidate_id)
