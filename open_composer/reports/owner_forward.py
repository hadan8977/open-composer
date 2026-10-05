"""Owner digest, A batch (T-20261005-39): forward record vs expectation, v1.2 daily actions.

Pure readers and renderers: no broker call, no model call.  The forward numbers come from the
stitched record of T-20261004-70 (``summary.json`` for the z values and window sizes,
``record.csv`` for the daily returns that the probabilistic Sharpe ratio needs); a candidate
without forward sessions is written as missing, never filled in.
"""

from __future__ import annotations

import csv
import json
import math
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from statistics import NormalDist
from typing import Any

FORWARD_RECORD_DIR = Path("reports/research/program/forward-record-2026-10-06")
FORWARD_SEGMENTS = ("oos_shadow", "paper")
FORWARD_CANDIDATES = ("S1", "S2", "S3", "C2", "V12F1", "V12F2")
MIN_SAMPLE = 10  # below this no estimate is given (owner rule for the statistics envelope)
CONFIDENCE = 0.95
TRADING_DAYS = 252
BOOK_ACTIONS_START = date(2026, 10, 7)  # first order day; earlier plans are dry runs
BOOK_ACTIONS_DAYS = 5
BOOK_ACCOUNTS = ("quant1", "quant2")
BOOK_DIR = Path("reports/paper/book")

_N = NormalDist()


@dataclass(frozen=True)
class ForwardRow:
    candidate: str
    n_forward: int | None  # forward sessions in the stitched record; None = no record
    z_full: float | None
    z_recent: float | None
    sharpe_annual: float | None
    psr: float | None
    min_trl: float | None  # sessions needed for PSR >= CONFIDENCE at the observed Sharpe
    progress: float | None  # n_forward / min_trl
    note: str  # why a field is missing, "" when complete


@dataclass(frozen=True)
class BookAction:
    account: str
    day: date
    n_planned: int | None
    plan_dry_run: bool | None
    n_sent: int | None
    n_rejected: int | None
    n_filled: int | None
    n_partial: int | None
    n_unfilled: int | None
    turnover: float | None  # (buy + sell notional) / equity basis
    receipts: tuple[str, ...]
    state: str  # "未开始" | "已出计划，未发单" | "已发单，待对账" | "已对账"


# ---------------------------------------------------------------------------
# statistics
# ---------------------------------------------------------------------------


def _moments(returns: list[float]) -> tuple[float, float, float, float]:
    """Mean, sample std (ddof=1), skewness and Pearson kurtosis (population moments)."""
    n = len(returns)
    mean = sum(returns) / n
    centered = [r - mean for r in returns]
    m2 = sum(c * c for c in centered) / n
    std = math.sqrt(sum(c * c for c in centered) / (n - 1))
    if m2 <= 0:
        return mean, std, float("nan"), float("nan")
    skew = (sum(c**3 for c in centered) / n) / m2**1.5
    kurt = (sum(c**4 for c in centered) / n) / m2**2
    return mean, std, skew, kurt


def _denominator(sr_pp: float, skew: float, kurt: float) -> float:
    value = 1.0 - skew * sr_pp + (kurt - 1.0) / 4.0 * sr_pp**2
    return math.sqrt(value) if value > 0 else float("nan")


def sharpe_confidence(
    returns: list[float], sharpe_annual: float | None = None
) -> dict[str, float | None]:
    """Annual Sharpe, PSR against 0 and the minimum record length for ``CONFIDENCE``.

    ``sharpe_annual`` is the Sharpe the record already carries (excess of the risk-free rate);
    without it the Sharpe is mean / std of ``returns`` with a zero risk-free rate.  Skewness and
    kurtosis always come from ``returns``.

    PSR is Bailey and Lopez de Prado (2012), the same formula as
    ``open_composer.research.scorecard_v2.psr``; ``min_trl`` is their minimum track record
    length in sessions, ``1 + (1 - skew*SR + (kurt-1)/4*SR^2) * (z_alpha / SR)^2``, defined only
    for a positive Sharpe.  Fewer than ``MIN_SAMPLE`` returns or a flat series give ``None``.
    """
    empty: dict[str, float | None] = {"sharpe_annual": None, "psr": None, "min_trl": None}
    if len(returns) < MIN_SAMPLE:
        return empty
    mean, std, skew, kurt = _moments(returns)
    if not std > 1e-12 or math.isnan(skew):
        return empty
    sr_pp = mean / std if sharpe_annual is None else sharpe_annual / math.sqrt(TRADING_DAYS)
    den = _denominator(sr_pp, skew, kurt)
    if math.isnan(den):
        return empty
    out: dict[str, float | None] = {
        "sharpe_annual": sr_pp * math.sqrt(TRADING_DAYS),
        "psr": _N.cdf(sr_pp * math.sqrt(len(returns) - 1) / den),
        "min_trl": None,
    }
    if sr_pp > 0:
        out["min_trl"] = 1.0 + den**2 * (_N.inv_cdf(CONFIDENCE) / sr_pp) ** 2
    return out


# ---------------------------------------------------------------------------
# forward record vs expectation
# ---------------------------------------------------------------------------


def _forward_returns(rows: list[dict[str, str]], candidate: str) -> list[float]:
    chosen = [
        (r["date"], float(r["net_return"]))
        for r in rows
        if r["candidate"] == candidate and r["segment"] in FORWARD_SEGMENTS
    ]
    return [value for _, value in sorted(chosen)]


def _z_value(block: dict[str, Any] | None, key: str) -> float | None:
    value = ((block or {}).get(key) or {}).get("z")
    return float(value) if isinstance(value, int | float) else None


def build_forward_rows(summary: dict[str, Any], record: list[dict[str, str]]) -> list[ForwardRow]:
    rows: list[ForwardRow] = []
    candidates = summary.get("candidates") or {}
    for name in FORWARD_CANDIDATES:
        entry = candidates.get(name)
        if not entry:
            rows.append(
                ForwardRow(name, None, None, None, None, None, None, None, "缺：记录里没有该候选")
            )
            continue
        zblock = (entry.get("primary_boundary_commit") or {}).get("z") or {}
        n_forward = (zblock.get("backtest_full") or {}).get("n_forward")
        z_full = _z_value(zblock, "backtest_full")
        z_recent = _z_value(zblock, "backtest_recent")
        returns = _forward_returns(record, name)
        if not returns:
            rows.append(
                ForwardRow(name, 0, z_full, z_recent, None, None, None, None, "缺：还没有前向会话")
            )
            continue
        segment = ((entry.get("primary_boundary_commit") or {}).get("segments") or {}).get(
            "forward_oos_plus_paper", {}
        ).get("strategy") or {}
        recorded = segment.get("sharpe") if segment.get("days") == len(returns) else None
        stats = sharpe_confidence(returns, recorded)
        min_trl = stats["min_trl"]
        progress = len(returns) / min_trl if min_trl else None
        note = ""
        if len(returns) < MIN_SAMPLE:
            note = f"样本不足（{len(returns)} < {MIN_SAMPLE}）"
        elif min_trl is None:
            note = "夏普 ≤ 0，达不到 95% 信心"
        rows.append(
            ForwardRow(
                name,
                len(returns),
                z_full if n_forward == len(returns) else None,
                z_recent if n_forward == len(returns) else None,
                stats["sharpe_annual"],
                stats["psr"],
                min_trl,
                progress,
                note,
            )
        )
    return rows


def load_forward_rows(root: Path) -> tuple[list[ForwardRow], dict[str, Any]] | None:
    base = root / FORWARD_RECORD_DIR
    try:
        summary = json.loads((base / "summary.json").read_text(encoding="utf-8"))
        with (base / "record.csv").open(encoding="utf-8", newline="") as handle:
            record = list(csv.DictReader(handle))
    except (OSError, ValueError):
        return None
    meta = {
        "last_session": summary.get("last_session_in_record"),
        "track_start": summary.get("track_start"),
        "source": str(FORWARD_RECORD_DIR),
    }
    return build_forward_rows(summary, record), meta


def _fmt(value: float | None, spec: str) -> str:
    return "缺" if value is None else format(value, spec)


def render_forward(loaded: tuple[list[ForwardRow], dict[str, Any]] | None) -> list[str]:
    if loaded is None:
        return [f"前向记录 `{FORWARD_RECORD_DIR}` 读取失败，无法对照预期。"]
    rows, meta = loaded
    lines = [
        f"前向对预期（{meta['track_start']} 起，记录截至 {meta['last_session']}；"
        f"前向 = 样本外影子 + 模拟盘，不含设计时看过的日子）：",
        "",
        "| 候选 | 前向会话 | z（全 / 近期） | 夏普（年化） | 概率夏普 | 95% 所需会话 "
        "| 进度 | 备注 |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for row in rows:
        z = "缺" if row.z_full is None else f"{row.z_full:+.2f} / {_fmt(row.z_recent, '+.2f')}"
        needed = "—" if row.min_trl is None else f"{row.min_trl:,.0f}"
        progress = "—" if row.progress is None else f"{min(row.progress, 9.99) * 100:.0f}%"
        if row.sharpe_annual is None:
            sharpe = psr = "缺"
        else:
            sharpe, psr = f"{row.sharpe_annual:+.2f}", f"{row.psr * 100:.0f}%"
        lines.append(
            f"| {row.candidate} | {'缺' if row.n_forward is None else row.n_forward} | {z} | "
            f"{sharpe} | {psr} | {needed} | {progress} | {row.note or '—'} |"
        )
    lines.extend(
        [
            "",
            "z = (前向日均收益 − 回测日均收益) / (回测日标准差 / √前向会话数)，取自 "
            f"`{meta['source']}/summary.json`；夏普取自 summary.json 的 "
            "forward_oos_plus_paper（已扣无风险利率）；"
            "概率夏普和 95% 所需会话由该夏普加 `record.csv` 前向日收益的偏度、峰度，"
            "按 Bailey–López de Prado（2012）公式算出，基准夏普 0。"
            f"少于 {MIN_SAMPLE} 个会话不给估计；日收益不是独立同分布，会话少于约 20 时只作描述。",
        ]
    )
    return lines


# ---------------------------------------------------------------------------
# v1.2 daily actions
# ---------------------------------------------------------------------------


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _file_days(folder: Path) -> set[date]:
    days: set[date] = set()
    if not folder.is_dir():
        return days
    for path in folder.glob("*.json"):
        try:
            days.add(date.fromisoformat(path.name.split(".")[0]))
        except ValueError:
            continue
    return days


def collect_book_actions(
    root: Path,
    *,
    start: date = BOOK_ACTIONS_START,
    limit: int = BOOK_ACTIONS_DAYS,
    accounts: tuple[str, ...] = BOOK_ACCOUNTS,
) -> list[BookAction]:
    """One row per (execution day >= ``start``, account) with a plan, receipt or daily file."""
    base = root / BOOK_DIR
    days: set[date] = set()
    for account in accounts:
        for sub in ("plans", "orders", "daily"):
            days |= {d for d in _file_days(base / account / sub) if d >= start}
    rows: list[BookAction] = []
    for day in sorted(days)[-limit:]:
        for account in accounts:
            rows.append(_book_action(base / account, root, account, day))
    return rows


def _book_action(folder: Path, root: Path, account: str, day: date) -> BookAction:
    stamp = day.isoformat()
    plan = _read_json(folder / "plans" / f"{stamp}.json")
    daily = _read_json(folder / "daily" / f"{stamp}.json")
    receipt_paths = sorted((folder / "orders").glob(f"{stamp}*.json")) if folder.is_dir() else []
    receipts = [r for p in receipt_paths if (r := _read_json(p)) is not None]
    summary = (plan or {}).get("summary") or {}
    basis = (plan or {}).get("equity_basis")
    traded = (summary.get("buy_notional") or 0.0) + (summary.get("sell_notional") or 0.0)
    turnover = traded / basis if plan and basis else None
    rec = (daily or {}).get("reconciliation") or {}
    if daily:
        state = "已对账"
    elif receipts:
        state = "已发单，待对账"
    elif plan:
        state = "已出计划，未发单"
    else:
        state = "未开始"
    return BookAction(
        account=account,
        day=day,
        n_planned=summary.get("n_orders") if plan else None,
        plan_dry_run=bool(plan.get("dry_run")) if plan else None,
        n_sent=sum(len(r.get("sent") or []) for r in receipts) if receipts else None,
        n_rejected=sum(len(r.get("failed") or []) for r in receipts) if receipts else None,
        n_filled=rec.get("n_filled") if daily else None,
        n_partial=rec.get("n_partial") if daily else None,
        n_unfilled=((rec.get("n_unfilled") or 0) + (rec.get("n_missing") or 0)) if daily else None,
        turnover=turnover,
        receipts=tuple(str(p.relative_to(root)) for p in receipt_paths),
        state=state,
    )


def _count(value: int | None) -> str:
    return "—" if value is None else str(value)


def render_book_actions(
    actions: list[BookAction], *, start: date = BOOK_ACTIONS_START
) -> list[str]:
    if not actions:
        return [
            f"v1.2 每日动作：未开始（首单 {start.isoformat()}；此前的计划是彩排，不计入）。",
        ]
    lines = [
        f"v1.2 每日动作（{start.isoformat()} 起，最近 {BOOK_ACTIONS_DAYS} 个有文件的日子；"
        "换手 = （买入 + 卖出金额）/ 权益基数）：",
        "",
        "| 日期 | 账户 | 状态 | 计划 | 发出 | 未接受 | 成交 | 部分 | 未成交 | 换手 | 回执 |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for a in actions:
        turnover = "—" if a.turnover is None else f"{a.turnover * 100:.1f}%"
        receipts = "；".join(f"`{p}`" for p in a.receipts) or "—"
        lines.append(
            f"| {a.day.isoformat()} | {a.account} | {a.state} | {_count(a.n_planned)} | "
            f"{_count(a.n_sent)} | {_count(a.n_rejected)} | {_count(a.n_filled)} | "
            f"{_count(a.n_partial)} | {_count(a.n_unfilled)} | {turnover} | {receipts} |"
        )
    return lines
