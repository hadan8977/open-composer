#!/usr/bin/env python3
"""Daily prediction-market odds digest for the owner (plain Chinese, about 40 lines).

T-20261002-45. Reads the hourly point-in-time snapshots written by
scripts/collect_prediction_markets.py and writes
``data/features/prediction_markets/digest/YYYY-MM-DD.md`` (the file of a date is replaced by
the latest run of that date; the snapshots themselves are never touched). Sections:

  1. Polymarket watchlist by group: yes price, change versus the snapshot nearest 24 h and
     7 d earlier (when one exists), volume.
  2. Kalshi macro releases in the next 10 NYSE sessions: implied mean and standard deviation
     from the latest snapshot (the builder's cleaning and pmf, imported), and U_rel when
     computable.
  3. The latest H1 shadow line, if one exists.

Research and decision support only: no order, no account, no key. Missing or stale (older
than 3 hours) snapshots are reported at the top instead of failing silently.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))

import build_kalshi_release_uncertainty as bk  # noqa: E402
import collect_prediction_markets as collect  # noqa: E402
import pm_release_shadow as shadow  # noqa: E402

ET = ZoneInfo("America/New_York")
OUT_ROOT = ROOT / "data/features/prediction_markets"
STALE_AFTER = timedelta(hours=3)
HORIZONS = (
    ("24h", timedelta(hours=24), timedelta(hours=6)),
    ("7d", timedelta(days=7), timedelta(hours=24)),
)
KALSHI_SESSIONS_AHEAD = 10
MAX_PER_GROUP = 4
DISCLAIMER = "仅供研究与决策参考，不构成交易建议；本脚本不下单、不连接任何账户。"

# --------------------------------------------------------------------- snapshots


def list_snapshots(folder: Path) -> list[tuple[datetime, Path]]:
    """(UTC time, file) of every snapshot under ``folder``, oldest first."""
    out = []
    for path in folder.glob("date=*/part-*.parquet"):
        try:
            day = path.parent.name.removeprefix("date=")
            hms = path.stem.removeprefix("part-")
            stamp = datetime.strptime(f"{day} {hms}", "%Y-%m-%d %H%M%S").replace(tzinfo=UTC)
        except ValueError:
            continue
        out.append((stamp, path))
    return sorted(out)


def nearest(
    snaps: list[tuple[datetime, Path]], target: datetime, tolerance: timedelta, latest: datetime
) -> tuple[datetime, Path] | None:
    best = None
    for stamp, path in snaps:
        if stamp >= latest:
            continue
        gap = abs(stamp - target)
        if gap <= tolerance and (best is None or gap < best[0]):
            best = (gap, (stamp, path))
    return best[1] if best else None


# ------------------------------------------------------------------- formatting


def money(value: Any) -> str:
    if value is None or pd.isna(value):
        return "n/a"
    v = float(value)
    if v >= 1e6:
        return f"${v / 1e6:.1f}M"
    if v >= 1e3:
        return f"${v / 1e3:.0f}k"
    return f"${v:.0f}"


def pct(value: Any) -> str:
    return "n/a" if value is None or pd.isna(value) else f"{float(value) * 100:.1f}%"


def delta(now: Any, then: Any) -> str:
    if now is None or then is None or pd.isna(now) or pd.isna(then):
        return "n/a"
    return f"{(float(now) - float(then)) * 100:+.1f}pp"


def age_text(delta_t: timedelta) -> str:
    hours = delta_t.total_seconds() / 3600
    return f"{hours:.1f} 小时前"


# --------------------------------------------------------------------- sections


def polymarket_section(
    snaps: list[tuple[datetime, Path]],
    latest: tuple[datetime, Path],
    notes: dict[str, str] | None = None,
) -> list[str]:
    now_df = pd.read_parquet(latest[1])
    past: dict[str, pd.DataFrame] = {}
    for label, horizon, tol in HORIZONS:
        hit = nearest(snaps, latest[0] - horizon, tol, latest[0])
        if hit:
            past[label] = pd.read_parquet(hit[1]).set_index("market_id")
    lines = [f"## Polymarket 观察清单（快照 {latest[0]:%Y-%m-%d %H:%M} UTC）"]
    for group, frame in now_df.groupby("watch_group", sort=False):
        ordered = frame.sort_values("yes_price", ascending=False)
        for _, row in ordered.head(MAX_PER_GROUP).iterrows():
            changes = []
            for label, _, _ in HORIZONS:
                then = past[label]["yes_price"].get(row["market_id"]) if label in past else None
                changes.append(f"{label} {delta(row['yes_price'], then)}")
            flag = " [已关闭]" if bool(row.get("closed")) else ""
            question = (notes or {}).get(str(row["market_id"])) or str(row["question"])
            question = question if len(question) <= 58 else question[:57] + "…"
            lines.append(
                f"- [{group}] {question}: {pct(row['yes_price'])} ({', '.join(changes)}; "
                f"总量 {money(row['volume'])}, 24h {money(row['volume_24h'])}){flag}"
            )
        if len(ordered) > MAX_PER_GROUP:
            lines.append(f"  （{group} 另有 {len(ordered) - MAX_PER_GROUP} 个较低概率档未列出）")
    return lines


def implied_moments(event_rows: pd.DataFrame) -> dict[str, Any]:
    """Implied mean/std from one snapshot using the builder's cleaning and pmf."""
    greater = event_rows[
        (event_rows["strike_type"] == "greater") & event_rows["floor_strike"].notna()
    ]
    if greater.empty:
        return {"n_usable_strikes": 0, "pmf_mean": float("nan"), "U": float("nan")}
    candles = pd.DataFrame(
        {
            "market_ticker": greater["market_ticker"].to_numpy(),
            "end_period_ts": 0,
            "yes_bid_close": greater["yes_bid"].to_numpy(),
            "yes_ask_close": greater["yes_ask"].to_numpy(),
            "price_close": greater["last_price"].to_numpy(),
        }
    )
    strikes = dict(
        zip(greater["market_ticker"], greater["floor_strike"].astype(float), strict=True)
    )
    return bk.event_distribution(candles, strikes, 1)


def kalshi_section(
    path: Path, today: date, forward_rows: list[dict[str, Any]]
) -> tuple[list[str], list[dict[str, Any]]]:
    df = pd.read_parquet(path)
    horizon = today
    for _ in range(KALSHI_SESSIONS_AHEAD):
        horizon = shadow.next_session(horizon)
    lines = [f"## Kalshi 宏观数据（未来 {KALSHI_SESSIONS_AHEAD} 个交易日，当前快照隐含分布）"]
    items: list[dict[str, Any]] = []
    for event, rows in df.groupby("event_ticker"):
        closes = rows.loc[rows["strike_type"] == "greater", "close_time"].dropna()
        if closes.empty:
            continue
        release = bk.release_date_et(str(closes.max()))
        if not (today < release <= horizon):
            continue
        series = str(rows["series_ticker"].iloc[0])
        mo = implied_moments(rows)
        item = {
            "event": event,
            "series": series,
            "release_date": release,
            "n_usable_strikes": int(mo.get("n_usable_strikes") or 0),
            "mean": mo.get("pmf_mean"),
            "std": mo.get("U"),
            "U_rel": None,
        }
        if item["n_usable_strikes"] >= bk.MIN_USABLE_STRIKES and pd.notna(item["std"]):
            hist = shadow.history_frame(series, release, forward_rows)
            item["U_rel"] = shadow.u_rel_for(series, release, str(event), float(item["std"]), hist)[
                "U_rel"
            ]
        items.append(item)
    items.sort(key=lambda i: (i["release_date"], i["event"]))
    if not items:
        lines.append("- 窗口内没有已开盘的宏观事件。")
    for it in items:
        if it["n_usable_strikes"] < bk.MIN_USABLE_STRIKES or pd.isna(it["std"]):
            body = f"可用档位不足（{it['n_usable_strikes']}），无隐含分布"
        else:
            rel = "n/a" if it["U_rel"] is None else f"{it['U_rel']:.2f}"
            body = f"隐含均值 {it['mean']:.3f}，标准差 {it['std']:.3f}，U_rel {rel}"
        lines.append(f"- {it['release_date']} {it['event']}: {body}")
    return lines, items


def shadow_section(out_dir: Path) -> list[str]:
    days = [r for r in shadow.read_jsonl(out_dir / shadow.SIGNALS) if r.get("record_type") == "day"]
    lines = ["## H1 前向影子记录（forward_only_no_decision，不构成结论）"]
    if not days:
        lines.append("- 尚无记录（首次信号在下一个宏观发布日前一天 15:00-15:50 ET）。")
        return lines
    last = days[-1]
    rel = last.get("day_U_rel")
    lines.append(
        f"- 最新: 发布日 {last['release_date']}，day_U_rel "
        f"{'n/a' if rel is None else f'{rel:.2f}'}，would_hold={last.get('would_hold')}，"
        f"FOMC日={last.get('fomc_day')}"
    )
    s = shadow.summarize(out_dir)
    d = s["D_QQQ_R_cc_ex_bp"]
    lines.append(
        f"- 累计非FOMC发布日 {s['forward_non_fomc_release_days']}/{s['target_days']}，"
        f"已实现 {s['realized_non_fomc_days']}，D = "
        f"{'n/a' if d is None else f'{d:+.1f} bp'}"
    )
    return lines


# ------------------------------------------------------------------------ build


def build_digest(
    out_root: Path = OUT_ROOT,
    *,
    now: datetime | None = None,
    shadow_dir: Path | None = None,
    watchlist_path: Path = collect.WATCHLIST,
) -> tuple[str, dict[str, Any]]:
    moment = (now or datetime.now(UTC)).astimezone(UTC)
    today = moment.astimezone(ET).date()
    k_snaps = list_snapshots(out_root / "kalshi_hourly")
    p_snaps = list_snapshots(out_root / "polymarket_hourly")
    sdir = shadow_dir if shadow_dir is not None else out_root / "h1_shadow"
    summary: dict[str, Any] = {"date": today.isoformat(), "warnings": []}
    head = [f"# 预测市场赔率日报 {today}（生成于 {moment:%Y-%m-%d %H:%M} UTC）", DISCLAIMER]
    for name, snaps in (("Kalshi", k_snaps), ("Polymarket", p_snaps)):
        if not snaps:
            summary["warnings"].append(f"{name} 没有快照")
            head.append(f"警告: {name} 没有任何快照，对应部分缺失。")
            continue
        age = moment - snaps[-1][0]
        summary[f"{name.lower()}_snapshot_utc"] = snaps[-1][0].isoformat()
        if age > STALE_AFTER:
            summary["warnings"].append(f"{name} 快照已过期 {age_text(age)}")
            head.append(f"警告: {name} 最新快照是 {age_text(age)}，超过 3 小时，数据可能已过期。")
    body: list[str] = []
    if p_snaps:
        notes = {}
        if watchlist_path.exists():
            notes = {
                m["id"]: m["note"] for m in collect.load_watchlist(watchlist_path) if m["note"]
            }
        body += polymarket_section(p_snaps, p_snaps[-1], notes)
        summary["polymarket_markets"] = int(len(pd.read_parquet(p_snaps[-1][1])))
    forward = shadow.read_jsonl(sdir / shadow.SIGNALS)
    if k_snaps:
        lines, items = kalshi_section(k_snaps[-1][1], today, forward)
        body += lines
        summary["kalshi_upcoming"] = [
            {
                "event": i["event"],
                "release_date": i["release_date"].isoformat(),
                "mean": None if pd.isna(i["mean"]) else round(float(i["mean"]), 4),
                "std": None if pd.isna(i["std"]) else round(float(i["std"]), 4),
                "U_rel": None if i["U_rel"] is None else round(float(i["U_rel"]), 3),
            }
            for i in items
        ]
    body += shadow_section(sdir)
    return "\n".join(head + body) + "\n", summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-root", type=Path, default=OUT_ROOT)
    parser.add_argument("--now", help="ISO UTC time override (tests)")
    args = parser.parse_args(argv)
    now = datetime.fromisoformat(args.now.replace("Z", "+00:00")) if args.now else None
    if now is not None and now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    text, summary = build_digest(args.out_root, now=now)
    target = args.out_root / "digest" / f"{summary['date']}.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    summary["file"] = str(target)
    summary["lines"] = text.count("\n")
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
