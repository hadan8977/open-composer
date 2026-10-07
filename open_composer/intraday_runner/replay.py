# ruff: noqa: E501  -- the Chinese report text counts double-width characters
"""Offline replay of one historical session through the real engine (no broker, no network).

Bars come from ``data/sip/minute``; fills come from :class:`SimBroker` at the open of the
minute bar following the decision (+ slippage).  ``degrade_live=True`` feeds the engine a
deliberately degraded copy of the SIP bars (minutes dropped, volume scaled) so the post-close
IEX-vs-SIP recheck has something to find: it proves the mechanism, it is not an IEX measurement.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from open_composer.intraday_runner.bars import (
    ArchiveMinuteProvider,
    FrameMinuteProvider,
    SessionBars,
    StaticPrevClose,
    load_history,
    session_bounds,
)
from open_composer.intraday_runner.broker import SimBroker
from open_composer.intraday_runner.config import RunnerConfig
from open_composer.intraday_runner.engine import RunnerEngine
from open_composer.intraday_runner.reporting import finish_session, sip_recheck


def degrade_frame(
    frame: pd.DataFrame, *, drop: float = 0.08, volume_scale: float = 0.03, seed: int = 7
):
    rng = np.random.default_rng(seed)
    keep = rng.random(len(frame)) >= drop
    out = frame[keep].copy()
    out["volume"] = (out["volume"] * volume_scale).round()
    return out.reset_index(drop=True)


def replay_session(
    config: RunnerConfig,
    session: date,
    out_root: Path,
    *,
    sip_root: Path | None = None,
    slippage_bps: float = 1.0,
    degrade_live: bool = True,
    kill_check=None,
    prev_close_raw: dict[str, float] | None = None,
    prev_close_file: Path | None = None,
) -> dict[str, Any]:
    """``prev_close_raw`` / ``prev_close_file`` ({symbol: price}) give the official unadjusted
    previous close; without them the engine falls back to the last minute close and flags it
    (the local ``data/sip/daily`` files are split-adjusted and are not used)."""
    archive = ArchiveMinuteProvider(sip_root)
    open_ts, close_ts = session_bounds(session)
    load_history(archive, config.all_symbols, session, 20)  # one archive scan serves all reads
    day_frame = archive.fetch(config.all_symbols, open_ts, close_ts)
    if day_frame.empty:
        raise RuntimeError(f"no SIP minute bars for {session}")
    live_provider = (
        FrameMinuteProvider(degrade_frame(day_frame), "iex_sim")
        if degrade_live
        else FrameMinuteProvider(day_frame, "sip")
    )
    bars = SessionBars(live_provider, config.all_symbols, session)
    truth = SessionBars(FrameMinuteProvider(day_frame, "sip"), config.all_symbols, session)
    clock = {"ts": open_ts}
    broker = SimBroker(
        lambda symbol: truth.price_at_or_after(symbol, clock["ts"]), slippage_bps=slippage_bps
    )
    engine = RunnerEngine(
        config,
        out_root,
        session,
        broker,
        bars,
        history_provider=archive,
        prev_close_provider=StaticPrevClose(prev_close_raw, prev_close_file)
        if (prev_close_raw or prev_close_file)
        else None,
        mode="replay",
        auth_id="replay-no-authorization",
        kill_check=kill_check or (lambda: None),
        sleep=lambda _s: None,
    )
    ticks = 0
    decision = open_ts + timedelta(minutes=1)
    while decision < close_ts:
        clock["ts"] = decision
        now = decision.to_pydatetime().astimezone(UTC) + timedelta(seconds=config.bar_delay_seconds)
        engine.tick(decision, now)
        ticks += 1
        decision += timedelta(minutes=1)
    clock["ts"] = close_ts
    finished = finish_session(
        engine, close_ts.to_pydatetime().astimezone(UTC) + timedelta(minutes=10)
    )
    recheck = sip_recheck(engine, FrameMinuteProvider(day_frame, "sip")) if degrade_live else None
    return {
        "engine": engine,
        "broker": broker,
        "ticks": ticks,
        "finish": finished,
        "recheck": recheck,
        "generated_at": datetime.now(UTC).isoformat(),
    }


def render_dryrun_report(result: dict[str, Any], config: RunnerConfig, restart: dict | None) -> str:
    """Chinese dry-run report: what ran, the evidence for each requirement, the caveats."""
    from collections import Counter

    from open_composer.intraday_runner.books import EventLog

    engine = result["engine"]
    events = EventLog(engine.event_dir / "events.jsonl").read()
    kinds = Counter(e["type"] for e in events)
    index_of = {id(e): i for i, e in enumerate(events)}
    first_net = min((index_of[id(e)] for e in events if e["type"] == "net_order"), default=None)
    first_signal = min((index_of[id(e)] for e in events if e["type"] == "signal"), default=None)
    signal_log = engine.signal_log
    signal_lines = sum(1 for _ in signal_log.open(encoding="utf-8")) if signal_log.is_file() else 0
    nets = [e for e in events if e["type"] == "net_order"]
    crossed = [e for e in nets if len(e["parts"]) > 1 or e["qty"] == 0]
    flats = [e for e in nets if e.get("flatten")]
    intents_clipped = [e for e in events if e["type"] == "intent" and e.get("status") != "ok"]
    rows = result["finish"]["rows"]
    rec = result["finish"]["reconcile"]
    recheck = result.get("recheck") or {}
    lines = [
        f"# 日内运行器干跑报告 — 回放 {engine.session.isoformat()}",
        "",
        f"生成时间 {result['generated_at']}。配置 `{config.path}`（哈希 {config.content_hash[:12]}），"
        "账户名 quant2，**没有连接券商、没有下任何订单**：K 线取自本地 SIP 分钟档案，"
        "成交由进程内的假券商（SimBroker）按下一根分钟线开盘价加 1 个基点滑点模拟。",
        "",
        "## 1. 跑了什么",
        f"- 一整天 {result['ticks']} 个决策时刻（每分钟一次，09:31–15:59 美东），4 个示例策略同时在一个账户上：",
    ]
    for s in config.strategies:
        lines.append(
            f"  - `{s.name}`：插件 `{s.plugin}`，周期 {s.timeframe}，名义资金 {s.capital_usd:,.0f}，"
            f"单策略上限 {s.caps.max_notional_usd:,.0f}，日亏损上限 {s.caps.max_daily_loss_usd:,.0f}"
        )
    lines += [
        f"- 事件计数：{dict(kinds)}",
        "",
        "## 2. 要求逐项核对",
        f"- 信号先写日志再下单：第一条信号事件序号 {first_signal}，第一条净额订单事件序号 {first_net}；"
        f"`signal_logs/` 行数 {signal_lines}（每个策略每个品种每个决策时刻一行）。"
        f"{'通过' if first_signal is not None and (first_net is None or first_signal < first_net) else '未通过'}",
        f"- 净额合并与分回：{len(nets)} 张账户级订单，其中 {len(crossed)} 张含多个策略的合并或对冲；"
        "明细见下表；内部相抵的股数不按零成本记账，按策略的 assumed_cost_bps 计入。",
        f"- 收盘前平仓：平仓单 {len(flats)} 张；收盘后券商持仓 {rec['broker_positions_open'] or '无'}，"
        f"虚拟持仓 {rec['virtual_positions_open'] or '无'}。",
        f"- 风控拦截/收缩事件 {len(intents_clipped)} 条（例：单策略名义上限把 300 股收缩到上限内）。",
        f"- 子账户盈亏与券商账户对账：策略净盈亏合计 {rec['sum_strategy_net_pnl']:,.4f}，"
        f"券商权益变化 {rec['broker_day_pnl']:,.4f}，差 {rec['pnl_gap_usd']:.4f}，其中内部相抵的模型成本 "
        f"{rec['internal_cross_cost_usd']:.4f}，扣除后差 {rec['pnl_gap_ex_internal_usd']:.2e}；"
        f"持仓差异 {rec['position_diffs'] or '无'}，订单成交差异 {rec['order_fill_diffs'] or '无'}。",
        "",
        "### 账户级订单明细（时间为 UTC）",
        "",
        "| 时间 | 品种 | 方向 | 股数 | 来自各策略的变动 | 计划价 | 用途 |",
        "|---|---|---|---:|---|---:|---|",
    ]
    for e in nets:
        lines.append(
            f"| {e['tick'][11:16]} | {e['symbol']} | {e['side']} | {e['qty']} | "
            f"{e['parts']} | {e['plan_price']:.2f} | "
            f"{'平仓' if e.get('flatten') else '策略'}{'（内部对冲，不下券商单）' if e['qty'] == 0 else ''} |"
        )
    lines += [
        "",
        "## 3. 每个策略当日一行汇总（日报用）",
        "",
        "| 策略 | 成交笔数 | 计数订单 | 成交额 | 毛盈亏 | 手续费 | 滑点成本 | 净盈亏 | 实际滑点(bp) | 回测假设成本(bp) |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in rows:
        lines.append(
            f"| {r['strategy']} | {r['fills']} | {r['orders_counted']} | "
            f"{r['traded_notional_usd']:,.0f} | {r['gross_pnl_usd']:,.2f} | {r['fees_usd']:,.2f} | "
            f"{r['slippage_usd']:,.2f} | {r['net_pnl_usd']:,.2f} | "
            f"{(r['slippage_bps'] if r['slippage_bps'] is not None else float('nan')):.2f} | "
            f"{r['assumed_cost_bps']:.2f} |"
        )
    lines += [
        "",
        "毛盈亏 = 按计划价成交的盈亏；滑点成本 = 成交价相对计划价（决策时刻最后一根已收盘 K 线的收盘价）"
        "的不利偏差 × 股数；手续费按配置的费率估算（默认 0，SEC/TAF 费率待核对）；"
        "本表的滑点来自模拟成交，不代表真实成交质量。",
        "",
        "## 4. 实时源与 SIP 重算差异（机制验证）",
        f"- 实时源标记 `{recheck.get('live_feed', '-')}`：本次回放把 SIP 数据故意降级（随机丢 8% 的分钟、"
        "成交量乘 0.03）来模拟 IEX，只用于证明差异检测能工作，**不是 IEX 的实测差异**。",
    ]
    for symbol, d in (recheck.get("bars") or {}).items():
        lines.append(
            f"- {symbol}：实时 {d['live_minutes']} 分钟，SIP {d['sip_minutes']} 分钟，实时缺 "
            f"{d['missing_in_live']} 分钟，收盘价差中位 {d.get('close_diff_bps_median', 0):.2f} bp，"
            f"成交量比（实时/SIP）中位 {d.get('volume_ratio_live_over_sip_median', 0):.3f}"
        )
    dec = recheck.get("decisions") or {}
    lines.append(
        f"- 用 SIP 重算同一批决策：共比较 {dec.get('decisions_compared')} 个，"
        f"目标股数不同 {dec.get('decisions_differing')} 个，方向改变 {dec.get('side_changes')} 个。"
    )
    if restart is not None:
        lines += [
            "",
            "## 5. 重启幂等检查",
            f"- 在同一事件日志上重新启动并重放全天：新增净额订单 {restart['new_net_orders']} 张，"
            f"假券商收到的新提交 {restart['new_submits']} 次，新增汇总行 {restart['new_summary_rows']} 行"
            "（都应为 0）。",
        ]
    lines += [
        "",
        "## 6. 局限",
        "- 回放的成交价取下一根分钟线开盘价，真实市价单的延迟和盘口冲击更大；",
        "- 数据是 2026-10-02 一天，只验证流程，不是策略评估；",
        "- 示例插件不是任何研究规格：噪声带插件是简化示例，定时买卖插件是测试用；",
        "- 事件时间戳在回放里用模拟时钟（决策时刻 + 5 秒），不是墙上时间。",
    ]
    return "\n".join(lines) + "\n"
