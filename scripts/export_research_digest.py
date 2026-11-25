"""Publish a read-only digest of the native research rounds, in Pacific time."""

import argparse
import csv
import json
import os
import re
import stat
import subprocess
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path, PurePosixPath
from tempfile import NamedTemporaryFile
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
PACIFIC = ZoneInfo("America/Los_Angeles")
LINK = re.compile(r"\[([^\[\]\n]{1,160})\]\(<?([^\s<>)]*)>?\)")
NAMES = {
    "equity_ml_20261120": "股票多因子联合选股",
    "intraday_in_play_20261120": "日内异动股与开盘突破",
    "etf_timing_20261120": "ETF 择时与跨资产轮动",
    "factor_factory": "美股单因子筛选",
    "quant1_information_20261119": "市场中性组合的信息增量",
    "event_driven_20261119": "财报、内部人和空头持仓事件",
    "jlaw_catalyst_pullback_20261119": "J Law 催化剂回踩",
    "martin_full_market_20261119": "Martin 全市场机会复现",
    "smallcap_momentum_20261119": "小盘股盘前动量",
    "martin_source_rebuild_20261119": "Martin 原文与强势股基准",
    "levered_index_trend_20261119": "杠杆指数趋势",
    "proof_a3_exposure": "市场状态与指数仓位",
    "proof_a2_model": "非价格数据与周度选股",
    "proof_a_model": "强势股模型与信息覆盖",
    "proof_a_data": "企业数据可见时点",
    "levered_index_throughput": "研究吞吐与杠杆 ETF 回放",
    "runner_diagnostic": "强势股收益集中度",
}
# Reader-facing descriptions of the initial registrations. Later families use
# their own experiment text, not the descriptions of these first families.
FAMILIES = {
    "em-20261120-3": (
        [
            "数据：296 个因子条目、按受理时间的财报及 SEC 公告、历史版分析师预期、SIP 成交。",
            "样本：美国股票和 ADR，2016 年起训练，2019–24 年开发，2025 年仅供锁定后的候选复核。",
            "对照：同型价量模型、覆盖率和强势股规则。成交另扣分钟半价差、单边 10/20 个基点。",
        ],
        [
            ("Gu、Kelly、Xiu：用机器学习联合预测股票收益", "https://doi.org/10.1093/rfs/hhaa009"),
            (
                "Chen、Zimmermann：公开选股特征及复现代码",
                "https://github.com/OpenSourceAP/CrossSection",
            ),
        ],
    ),
    "ip-20261120-4": (
        [
            "数据：SIP 开盘分钟行情、SEC 公告受理时间、可以核验的当时可见信息。",
            "样本：2016–17 年用于拟合，2018–24 年模拟美股开盘异动股。",
            "对照：价量模型、开盘突破规则。5 万美元账户按分钟容量计价差、单边 5/10 个基点和规费。",
        ],
        [],
    ),
    "et-20261120-4": (
        [
            "数据：ETF 开盘成交、已到期因子组合、FINRA 空头持仓、宏观首次发布值和历史分析师预期。",
            "样本：2019–24 年开发，2025 年和 2026 年均未因本组结果开启。",
            "对照：纯价格模型、固定配比与杠杆趋势规则。单边 5/10/20 个基点，主成本 10 个基点。",
        ],
        [
            ("Moreira、Muir：波动率管理组合", "https://doi.org/10.1111/jofi.12513"),
            (
                "Hurst、Ooi、Pedersen：跨市场趋势跟随",
                "https://www.aqr.com/Insights/Research/Journal-Article/A-Century-of-Evidence-on-Trend-Following-Investing",
            ),
        ],
    ),
}
STATUSES = {
    "running": "进行中",
    "interrupted_or_failed": "中断",
    "scope_needs_revision": "方案待修订",
    "closed_after_recovery": "已收尾",
    "round_finished": "已完成",
    "worker_checkpoint": "待续跑",
    "deadline_checkpoint": "待续跑",
    "resource_wait": "等资源",
}
DECISIONS = {"repair": "待修复", "park": "暂停", "continue": "继续研究", "branch": "分支研究"}


def load(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def elapsed_at(value):
    return datetime.fromisoformat(value).astimezone(PACIFIC).strftime("%Y-%m-%d %H:%M %Z")


def excerpt(value, limit=460):
    # Export the finding as text. Local file links, transport and full raw
    # reports stay on the research machine.
    text = LINK.sub("", value or "")
    text = re.sub(r"(?:[A-Za-z]:[\\/]|/(?:root|mnt|home)/|https?://)\S+", "", text)
    text = re.sub(r"t3-thread://\S+|\b(?:AKIA|PK[A-Z]|sk-|gh[pousr]_)[A-Za-z0-9_-]{12,}\b", "", text)
    text = re.sub(
        r"(?i)\b(?:api[_ -]?key|password|access[_ -]?token|account[_ -]?id)"
        r"\s*[:=]\s*[\w./+-]{6,}",
        "",
        text,
    )
    text = re.sub(r"[*`#]", "", text)
    text = " ".join(text.split()).strip(" ·")
    if len(text) <= limit:
        return text
    stop = max(text.rfind("。", 0, limit), text.rfind(". ", 0, limit))
    return text[: stop + 1] if stop > limit // 3 else text[:limit].rstrip() + "…"


def sources(documents):
    found = {}
    for doc in documents:
        for label, url in LINK.findall(doc):
            if not url.startswith("https://"):
                continue
            u = urlsplit(url)
            if u.username or not u.hostname or "." not in u.hostname or "token=" in u.query.lower():
                continue
            found.setdefault(url, {"label": label.strip(), "url": url})
    return list(found.values())[:12]


def native_round(path):
    run = load(path)
    phases = run.get("phases", {})
    lead = phases.get(run.get("latest_lead_phase"), phases.get("lead", {}))
    if lead.get("status") != "complete":
        lead = {}
    raw_status = run["status"]
    status = DECISIONS.get(lead.get("decision"), STATUSES.get(raw_status, raw_status))
    stamp = run.get("finished") or run.get("started")
    metrics = []
    counts = run.get("efficiency", {}).get("counts") or {}
    if counts.get("variants") is not None:
        metrics.append({"label": "实际测试变体", "value": counts["variants"]})
    if lead:
        msg = lead.get("summary", "")
        economic = lead.get("round_class") in (
            "new_money_evidence",
            "informative_learning",
            "no_information",
        )
        if lead.get("round_class") == "no_information":
            msg = "本轮未形成有效经济结论。" + msg
    elif raw_status == "scope_needs_revision":
        msg = "方案退回修订。" + (phases.get("plan_review", {}).get("summary") or "")
        economic = False
    else:
        msg = {
            "进行中": "本轮进行中，尚待研究负责人裁决。",
            "中断": "本轮执行中断，未登记研究结论。",
        }.get(status, "本轮没有已接收的负责人经济结论。")
        economic = False
    evidence = [path.relative_to(ROOT).as_posix()]
    result_path = lead.get("results")
    if (
        isinstance(result_path, str)
        and result_path.startswith(evidence[0].rsplit("/", 2)[0] + "/")
        and ".." not in result_path
    ):
        evidence.append(result_path)
    verdict = path.parent / lead.get("folder", "lead") / "verdict.md"
    if verdict.is_file():
        evidence.append(verdict.relative_to(ROOT).as_posix())
    result = ROOT / result_path if result_path in evidence else None
    context = load(result) if result and result.is_file() else {}
    data = [
        excerpt(context[k], 330)
        for k in ("data_and_exposure", "costs", "baseline")
        if isinstance(context.get(k), str)
    ]
    return dict(
        id=path.parent.name,
        at=elapsed_at(stamp),
        timestamp=stamp,
        status=status,
        summary=excerpt(msg),
        metrics=metrics,
        evidence=evidence,
        has_review=bool(lead),
        evaluated=economic,
        data=data,
        sources=sources([lead.get("summary", "")]),
        started_at=elapsed_at(run.get("started") or stamp),
    )


def recorded_rounds(catalog):
    """Read entered findings and explicitly published in-flight research stages."""
    rounds = defaultdict(dict)
    ledger = ROOT / "research/findings.tsv"
    if ledger.is_file():
        with ledger.open(encoding="utf-8-sig", newline="") as table:
            for row in csv.DictReader(table, delimiter="\t"):
                published = row.get("日期") or ""
                ref = str(row.get("报告链接") or "").strip().replace("\\", "/")
                path = PurePosixPath(ref if ref.startswith("research/") else f"research/{ref}")
                if (not re.fullmatch(r"\d{4}-\d{2}-\d{2}", published)
                    or published < catalog.get("findings_since", "")
                    or len(path.parts) < 3 or ".." in path.parts or ":" in ref
                    or path.suffix != ".md" or not (ROOT / path).is_file()):
                    continue
                task = path.parts[1]
                if len(path.parts) > 4 and path.parts[2] == "runs":
                    if (ROOT.joinpath(*path.parts[:4]) / "run.json").is_file():
                        continue
                key = "-".join(path.parts[2:]).removesuffix(".md")
                rounds[task][key] = dict(
                    id=key, timestamp=f"{published}T00:00:00",
                    name=excerpt(row.get("想法"), 70), summary=excerpt(row.get("结论")),
                    status="已收结果", stage="已收结果",
                    data=[excerpt(row.get("数据"), 330)] if row.get("数据") else [],
                    evidence=[path.as_posix()], has_review=True, evaluated=False,
                )
    for task, entry in catalog.get("recorded", {}).items():
        entry = dict(entry)
        key = entry.pop("replaces", entry["id"])
        base = rounds[task].pop(key, {})
        rounds[task][entry["id"]] = base | entry
    for entries in rounds.values():
        for row in entries.values():
            stamp = datetime.fromisoformat(row["timestamp"])
            if stamp.tzinfo is None:
                stamp = stamp.replace(tzinfo=PACIFIC)
            row["timestamp"] = stamp.isoformat()
            row["at"] = row["started_at"] = elapsed_at(row["timestamp"])
            row["summary"] = excerpt(row["summary"])
            row["metrics"] = []
            row["data"] = [row["stage"], *[excerpt(s, 330) for s in row.get("data", [])]]
            row["has_review"] = row.get("has_review", False)
            row["evaluated"] = row.get("evaluated", False)
    return rounds


def direction(folder, decisions, recorded):
    rounds = sorted(
        (native_round(p) for p in (folder / "runs").glob("*/run.json")),
        key=lambda row: datetime.fromisoformat(row["timestamp"]),
        reverse=True,
    )
    key = folder.name
    rounds.extend(recorded.values())
    registration = folder / "registration.md"
    spec_path = folder / "experiment.json"
    if not rounds and registration.is_file() and spec_path.is_file():
        stamp = datetime.fromtimestamp(registration.stat().st_mtime, PACIFIC).isoformat()
        rounds.append(dict(
            id="registration", timestamp=stamp, at=elapsed_at(stamp), status="已登记",
            summary="已登记研究定义，等待回放或结果。", metrics=[], has_review=False,
            evaluated=False, data=["研究登记"], evidence=[f"research/{key}/registration.md"],
        ))
    if not rounds and key != "factor_factory":
        return None
    docs = {
        p.name: p.read_text(encoding="utf-8-sig")
        for p in [folder / "registration.md", folder / "scope.md", folder / "report.zh.md"]
        if p.exists()
    }
    scope = docs.get("scope.md", "")
    evidence = [f"research/{key}/{name}" for name in docs]
    data = []
    if (folder / "experiment.json").exists():
        spec = load(folder / "experiment.json")
        exp = spec.get("experiment", spec)
        data = [
            excerpt(exp[field], 440)
            for field in ("data_and_exposure", "costs", "baseline")
            if isinstance(exp.get(field), str)
        ]
        evidence.append(f"research/{key}/experiment.json")
    if key == "factor_factory":
        batch = load(folder / "batches/wave1/batch.json")
        library = load(folder / "landscape/library.json")
        counts = [
            {"label": "候选条目", "value": batch["evaluated"]},
            {"label": "单因子通过", "value": len(library)},
        ]
        headline = next(s for s in docs["report.zh.md"].splitlines() if s.startswith("**"))
        milestone = load(folder / "measurements.json")["utc"]
        rounds.append(
            dict(
                id="wave1-screen",
                at=elapsed_at(milestone),
                timestamp=milestone,
                status="已完成",
                summary=excerpt(headline),
                metrics=counts,
                has_review=True,
                evaluated=True,
                data=[],
                evidence=[f"research/{key}/report.zh.md"],
            )
        )
    series = {}
    for path in (folder / "runs").glob("*-series.json"):
        for ref in load(path).get("rounds", []):
            if isinstance(ref, str):
                series[Path(ref).parent.name] = path.stem.removesuffix("-series")
    for row in rounds:
        row["series"] = series.get(row["id"], "")
    rounds.sort(key=lambda row: datetime.fromisoformat(row["timestamp"]), reverse=True)
    last = rounds[0]
    status, summary, todo = last["status"], last["summary"], ""
    if status in ("继续研究", "待修复", "分支研究") and key not in NAMES:
        status = "历史记录"
    override = decisions.get(key, {})
    for row in rounds:
        if row["id"] == override.get("round_id"):
            row["final_note"] = override["summary"]
    if override.get("round_id") == last["id"]:
        status, summary, todo = override["status"], override["summary"], override.get("next", "")
        if override["evidence"] not in evidence:
            evidence.append(override["evidence"])
    if key == "equity_ml_20261120" and status == "进行中":
        ledgers = folder / "batches" / last["id"] / "development/minute-ledgers"
        months = sorted(p.name[:7] for p in ledgers.glob("????-??-fills.parquet"))
        if months:
            summary = f"连续账户回放已写入 {months[-1]} 的逐笔成交。扣费后净收益等待本轮结算。"
    if last["id"] == "ip-20261120-4-2" and status == "进行中":
        summary = "上一轮被退回修复。正在按修复简报重建机会池，原有成交结果仅适用于旧股票池。"
    if not data:
        data = next((r["data"] for r in rounds if r["data"]), [])
    title = next(
        (s.strip("# ").removeprefix("Scope: ") for s in scope.splitlines() if s.startswith("# ")),
        "",
    )
    if not title:
        title = next((s[2:] for s in docs.get("registration.md", "").splitlines() if s.startswith("# ")), "")
    family = last["series"] or last["id"]
    if family in FAMILIES:
        data, refs = FAMILIES[family]
    else:
        refs = []
    links = [dict(label=label, url=url) for label, url in refs] + sources(docs.values())
    covered_urls = {s["url"] for s in links}
    for r in rounds:
        for source in r.get("sources", []):
            if source["url"] not in covered_urls:
                links.append(source)
                covered_urls.add(source["url"])
    return dict(
        id=key,
        name=NAMES.get(key, last.get("name") or excerpt(title, 70) or key.replace("_", " ")),
        status=status,
        summary=summary,
        next=todo,
        updated_at=last["at"],
        data=data,
        sources=links[:12],
        evidence=evidence,
        rounds=rounds,
    )


def periods(directions):
    buckets = defaultdict(list)
    for d in directions:
        for r in d["rounds"]:
            day = date.fromisoformat(r["at"][:10])
            for key in (("day", day), ("week", day - timedelta(days=day.weekday()))):
                buckets[key].append((d, r))
    output = []
    for (kind, start), members in sorted(buckets.items(), key=lambda kv: kv[0][1], reverse=True):
        end = start + timedelta(days=6 if kind == "week" else 0)
        rows = sorted(
            members,
            key=lambda m: (
                bool(m[1].get("final_note") or m[1]["evaluated"] or m[1]["has_review"]),
                m[1]["timestamp"],
            ),
            reverse=True,
        )
        highlights = {}
        for d, r in rows:
            highlights.setdefault(
                d["id"],
                dict(
                    direction_id=d["id"],
                    name=d["name"],
                    round_id=r["id"],
                    at=r["at"],
                    summary=r.get("final_note", r["summary"]),
                ),
            )
        reviewed = sum(r["has_review"] for _, r in rows)
        revised = sum(r["status"] == "方案待修订" for _, r in rows)
        overview = (f"{len(highlights)} 个方向，共 {len(rows)} 轮。"
                    f"{reviewed} 轮已有裁决或结果，{revised} 轮在方案审核时退回。")
        output.append(
            dict(
                id=f"{kind}-{start}",
                kind=kind,
                label=str(start) if kind == "day" else f"{start} – {end}",
                start=str(start),
                end=str(end),
                round_count=len(rows),
                direction_count=len(highlights),
                outcome_count=reviewed,
                revision_count=revised,
                summary=overview,
                highlights=list(highlights.values()),
            )
        )
    return output


def build():
    now = datetime.now(PACIFIC)
    path = ROOT / "research/direction-status.json"
    catalog = load(path) if path.is_file() else {}
    recorded = recorded_rounds(catalog)
    directions = [
        d
        for folder in sorted((ROOT / "research").iterdir())
        if folder.is_dir()
        and not folder.is_symlink()
        and getattr(folder.lstat(), "st_reparse_tag", 0) != stat.IO_REPARSE_TAG_MOUNT_POINT
        and (d := direction(folder, catalog.get("decisions", {}), recorded.get(folder.name, {}))) is not None
    ]
    directions.sort(key=lambda d: (d["status"] == "进行中", d["updated_at"]), reverse=True)
    launched = {d["id"] for d in directions}
    for item in catalog.get("queue", []):
        if item["id"] not in launched:
            directions.append(
                dict(
                    item,
                    summary=item["next"],
                    next="",
                    updated_at="",
                    sources=item.get("sources", []),
                    rounds=[],
                )
            )
    return dict(
        generated_at=now.strftime("%Y-%m-%d %H:%M %Z"),
        directions=directions,
        periods=periods(directions),
    )


def edit_highlights(feed, cache_path):
    from open_composer.research.windows_runtime import executable_argv

    previous = load(cache_path) if cache_path.exists() else {}
    rows = sorted(
        ((d, r) for d in feed["directions"] for r in d["rounds"] if r["has_review"]),
        key=lambda pair: pair[1]["timestamp"], reverse=True,
    )
    entries, pending = {}, {}
    seeded = set()
    for direction, row in rows:
        key = f"{direction['id']}/{row['id']}"
        source = {"方向": direction["name"], "轮次结论": row["summary"],
                  "现行裁决": row.get("final_note") or row["status"]}
        old = previous.get(key, {})
        if old.get("source") == source:
            entries[key] = old
            continue
        entries[key] = {"source": source}
        if previous or (len(seeded) < 2 and direction["id"] not in seeded):
            pending[key] = source
            seeded.add(direction["id"])
    if pending:
        prompt = (ROOT / "prompts/research-digest-editor.zh.md").read_text(encoding="utf-8")
        pi = Path.home() / ".pi/agent/bin/pi.cmd"
        argv = executable_argv([str(pi), "--provider", "commandcode", "--model",
                                "deepseek/deepseek-v4.1-flash", "--thinking", "off",
                                "--print", "--no-session", "--no-tools", "--no-skills",
                                "--no-context-files", "--system-prompt", prompt])
        assignment = "为下面每项写一条网站短讯。最多两句话，只选一个比较。只输出键到短讯的 JSON。\n"
        reply = subprocess.run(argv, input=assignment + json.dumps(pending, ensure_ascii=False),
                               text=True, encoding="utf-8", stdout=subprocess.PIPE,
                               timeout=360, check=True)
        edited = json.loads(reply.stdout.strip().removeprefix("```json").removesuffix("```").strip())
        for key in pending:
            summary = edited[key].strip()
            if not summary:
                raise ValueError(f"Empty research summary for {key}")
            entries[key]["text"] = excerpt(summary)
        save_json(cache_path, entries)
    for period in feed["periods"]:
        for h in period["highlights"]:
            entry = entries.get(f"{h['direction_id']}/{h['round_id']}", {})
            if entry.get("text"):
                h["summary"] = entry["text"]
    print(f"DeepSeek edited {len(pending)} new or revised round summaries")


def save_json(path, data):
    with NamedTemporaryFile("w", encoding="utf-8", delete=False, dir=path.parent) as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    os.replace(f.name, path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "reports/owner/research-digest.json")
    parser.add_argument("--edit-highlights", action="store_true")
    args = parser.parse_args()
    feed = build()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.edit_highlights:
        edit_highlights(feed, args.output.with_suffix(".editor.json"))
    save_json(args.output, feed)
    print(f"{len(feed['directions'])} directions, {len(feed['periods'])} periods -> {args.output}")


if __name__ == "__main__":
    main()
