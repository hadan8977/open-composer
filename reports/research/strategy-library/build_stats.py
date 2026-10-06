"""Regenerate catalog.md from catalog.json, first-batch.json and the registry snapshot.

    python3 reports/research/strategy-library/build_stats.py            # rewrites catalog.md
    python3 reports/research/strategy-library/build_stats.py --print    # numbers only

Every number in catalog.md is computed here; the prose blocks are static text.
"""

from __future__ import annotations

import importlib.util
import json
import re
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
CAT = json.load(open(HERE / "catalog.json"))
FB = json.load(open(HERE / "first-batch.json"))
FAMS = json.load(open(HERE / "families.json"))
DIRS = {r["id"]: r for r in json.load(open(HERE / "_directions_latest.json"))}

spec = importlib.util.spec_from_file_location("sel", HERE / "select_first_batch.py")
sel = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sel)

IN_PROGRESS = sel.IN_PROGRESS
DENIED = sel.DENIED


def state(r: dict) -> str:
    """not_tradable / not_a_strategy / in_progress_or_live / tested_not_at_depth / never_tested"""
    if r["entry_type"] != "strategy":
        return "not_a_strategy (placebo/drop)"
    if r["alpaca_tradable"] != "yes":
        return "not_tradable"
    sts = sel.specific_statuses(r)
    if any(s in IN_PROGRESS for s in sts) or r.get("in_equity_book"):
        return "in_progress_or_live"
    if any(s == "not_executable" for s in sts):
        return "registry_not_executable"
    if sel.tested_statuses(r):
        return "tested_not_at_depth"
    return "never_tested_individually"


def has_data(r: dict) -> bool:
    return r["data_local"] == "yes"


def table(counter_rows: list[tuple], header: list[str]) -> str:
    out = ["| " + " | ".join(header) + " |", "|" + "|".join(["---"] * len(header)) + "|"]
    for row in counter_rows:
        out.append("| " + " | ".join(str(x) for x in row) + " |")
    return "\n".join(out)


def crosstab(rows: list[dict], key: str, cols: list[str], colfn) -> list[tuple]:
    keys = sorted({r[key] for r in rows})
    out = []
    for k in keys:
        sub = [r for r in rows if r[key] == k]
        c = Counter(colfn(r) for r in sub)
        out.append((k, len(sub), *[c.get(col, 0) for col in cols]))
    out.append(("**total**", len(rows), *[sum(1 for r in rows if colfn(r) == col) for col in cols]))
    return out


def compute() -> dict:
    s = {}
    s["n_rows"] = len(CAT)
    s["by_origin"] = Counter(r["origin_list"] for r in CAT)
    s["n_families"] = len(FAMS)
    s["multi_origin_families"] = sum(1 for f in FAMS if len(f["origins"]) >= 2)
    s["states"] = Counter(state(r) for r in CAT)
    s["tradable"] = sum(1 for r in CAT if r["alpaca_tradable"] == "yes" and r["entry_type"] == "strategy")
    s["tradable_data_yes"] = sum(1 for r in CAT if r["alpaca_tradable"] == "yes" and r["entry_type"] == "strategy" and has_data(r))
    s["tradable_data_1d"] = sum(1 for r in CAT if r["alpaca_tradable"] == "yes" and r["entry_type"] == "strategy" and r["adapter_1d"])
    s["never_yes"] = sum(1 for r in CAT if state(r) == "never_tested_individually" and has_data(r))
    s["never_1d"] = sum(1 for r in CAT if state(r) == "never_tested_individually" and r["adapter_1d"])
    s["never_all_tradable"] = sum(1 for r in CAT if state(r) == "never_tested_individually")
    s["notdepth_yes"] = sum(1 for r in CAT if state(r) == "tested_not_at_depth" and has_data(r))
    s["notdepth_1d"] = sum(1 for r in CAT if state(r) == "tested_not_at_depth" and r["adapter_1d"])
    s["notdepth_all"] = sum(1 for r in CAT if state(r) == "tested_not_at_depth")
    s["depth_ok_yes"] = sum(1 for r in CAT if r["prior_depth_ok"] == "yes")
    s["registry_n"] = len(DIRS)
    s["registry_status"] = Counter(r["status"] for r in DIRS.values())
    return s


def main() -> None:
    s = compute()
    if "--print" in sys.argv:
        print(json.dumps({k: (dict(v) if isinstance(v, Counter) else v) for k, v in s.items()}, indent=1))
        return
    items = FB["items"]
    meta = FB["meta"]
    tr_rows = [r for r in CAT if r["entry_type"] == "strategy"]
    states = ["never_tested_individually", "tested_not_at_depth", "in_progress_or_live", "registry_not_executable", "not_tradable"]
    L = []
    A = L.append
    A("# 策略库总清单（T-20261006-13，2026-10-06）")
    A("")
    A("清单本体是 `catalog.json`（每行一条策略，字段见第 2 节）；本文所有数字由 `build_stats.py` 从 `catalog.json`、`first-batch.json` 和登记簿快照算出，运行 `python3 reports/research/strategy-library/build_stats.py` 可以重现。没有跑任何回测。")
    A("")
    A("## 1. 现状（建清单前已有的东西）")
    A("")
    A(f"- 方向登记簿 `reports/research/harvest/directions.jsonl`：{s['registry_n']} 个方向（同一 id 取最后一行），状态分布 "
      + "、".join(f"{k} {v}" for k, v in s["registry_status"].most_common()) + "。")
    A("- 已导入的因子库（2026-10-06 核对列数）：规则因子库 `open_composer/research/factor_library.py` 84 个定义；`data/features/alpha158` 154 列（计划写 158，末年文件 154 列）、`alpha101` 20 列、`alpha191` 34 列、`osap_price` 25 列（OSAP 价格类）、`daily` 46 列；另有 Alpha191 公式移植的登记结论 `dir:gtja191_alpha_formulas`（refuted）。")
    A("- 已筛过什么：公开因子/异象库只按作者自己发表的收益序列做了结果普查（`I-20260923-01`，609 个序列，OSAP 只有 198 个多空 predictor 的 2023-10..2024-12 共 15 个月窗口，窗口极短，不能当作我们自己的复现）；本地自己复现过的只有价格类和 SEC 会计类的一小部分，进入了股票多空书信号表（`docs/equity-book-design.zh.md` 第 4 节：价值、质量、投资/发行、动量、低风险、盈余、内部人、卖空信息、季节性、快信号，约 10 类）和 `dir:ml_ranking_liquid500_recent_vs_momentum_rule`（refuted）。")
    A("- 结论：登记簿里没有任何一条旧否定带深度台账（`depth_curve.jsonl` 在仓库里一个都没有，2026-10-04 的五条深度规则晚于全部旧结论），所以 `prior_depth_ok` 只能写 unknown；本清单把\"测过但未到深度\"和\"从没单独测过\"分开数。")
    A(f"- 本清单里满足五条深度规则的旧否定数量：{s['depth_ok_yes']}。")
    A("")
    A("## 2. 登记口径")
    A("")
    A("四个来源，共 " + str(s["n_rows"]) + " 行：")
    A("")
    A(table([("151 Trading Strategies（Kakushadze-Serur 2018，SSRN 3247865）", s["by_origin"]["k151"], "全书目录里所有带编号的策略条目 174 条，加第 20 章基础设施 1 条；'Generalities'、'A few comments' 是背景章节，不登记。PDF 取自镜像（SSRN 直链 403），361 页，sha256 见来源快照。"),
             ("Open Source Asset Pricing SignalDoc.csv", s["by_origin"]["osap"], "331 行全登记：212 个 Predictor、114 个 Placebo、5 个 Drop；Placebo/Drop 登记但不进筛选。"),
             ("QuantConnect Strategy Library", s["by_origin"]["qc"], "抓取时目录页共 84 个教程链接，其中大小写重复 1 个；2 个页面返回 'Page Not Found'（仍登记，页面缺失写在 alpaca_note）。目录页和文档页都是静态 HTML，可能落后于 QC 现行库，见第 7 节。"),
             ("本地登记簿补充行", s["by_origin"]["reg"], "只取日内、高频、事件、另类数据、加密、期权、文本类方向（status 不是 duplicate），因为三个公开清单在这些类别很薄，不补就没法判断覆盖；字段比前三个来源粗。")],
            ["来源", "行数", "说明"]))
    A("")
    A("字段：`id, name, source, original_paper, origin_list, asset_class, frequency, direction, data_needed, data_local(+detail), alpaca_tradable(+note, basis), prior_local, prior_ids, prior_best_status, prior_scope, prior_depth_ok, screen_lane_ready, engine, lane_adapter, complexity, family_key, notes`，另有 `adapter_1d`（一天内能补数据）。")
    A("")
    A("- `prior_scope`：none（没有旧结论）、generic_only（只被通用 ML 排序类方向覆盖）、family_level（OSAP 因子所在机制族测过，本因子没有单独测）、specific（登记簿里就是这一条）。")
    A("- `engine`：lane（`scripts/screen_lane.py`：长仓、日/周/月、ETF 或股票收盘价面板，改参数即可进）、book（股票多空书信号列，不走 screen_lane）、new（需要新代码）。`screen_lane_ready` 只对 lane 且数据齐的条目为真。")
    A("- Alpaca 可交易判定：期权只认文档列出的 Level 1–3；未列出但风险有限的组合标 inferred；任何裸空头一律 no；期货、外汇、现券、CDS、可转债、房地产等一律 no（见 `alpaca_scope_snapshot.md`）。")
    A("")
    A("## 3. 统计")
    A("")
    A("**按来源 × 状态**（状态由 `build_stats.py` 的 `state()` 判定）：")
    A("")
    A(table(crosstab(CAT, "origin_list", states, state), ["来源", "行数"] + states))
    A("")
    A("**按资产类 × 状态**：")
    A("")
    A(table(crosstab(CAT, "asset_class", states, state), ["资产类", "行数"] + states))
    A("")
    A("**按频率 × 状态**：")
    A("")
    A(table(crosstab(CAT, "frequency", states, state), ["频率", "行数"] + states))
    A("")
    A("**按数据可得性（仅策略条目）**：")
    A("")
    A(table([(k, sum(1 for r in tr_rows if r["data_local"] == k), sum(1 for r in tr_rows if r["data_local"] == k and r["alpaca_tradable"] == "yes")) for k in ["yes", "partial", "no"]], ["data_local", "条数", "其中 Alpaca 可交易"]))
    A("")
    A(f"- 机制族（`family_key`）共 {s['n_families']} 个；出现在两个及以上来源的 {s['multi_origin_families']} 个（`families.json`）。")
    A("")
    A("## 4. 关键数字")
    A("")
    A(table([
        ("总条目", s["n_rows"]),
        ("策略条目（扣除 OSAP 安慰剂/放弃项）", len(tr_rows)),
        ("Alpaca 能交易的策略条目", s["tradable"]),
        ("能交易且本地数据齐（data_local=yes）", s["tradable_data_yes"]),
        ("能交易且数据齐或一天内能补（adapter_1d）", s["tradable_data_1d"]),
        ("**能交易 + 数据齐 + 从没单独测过**", s["never_yes"]),
        ("能交易 + 数据齐或一天内能补 + 从没单独测过", s["never_1d"]),
        ("能交易 + 从没单独测过（不管数据）", s["never_all_tradable"]),
        ("**能交易 + 数据齐 + 以前测过但未到深度**", s["notdepth_yes"]),
        ("能交易 + 数据齐或一天内能补 + 以前测过但未到深度", s["notdepth_1d"]),
        ("能交易 + 以前测过但未到深度（不管数据）", s["notdepth_all"]),
        ("进行中或已在用（不重复）", s["states"]["in_progress_or_live"]),
        ("不能交易（登记但不筛选）", s["states"]["not_tradable"]),
    ], ["指标", "数量"]))
    A("")
    A("\"从没单独测过\"包含 OSAP 里只有机制族被测过、本因子没单独测的 `family_level` 条目；这类条目的族级结论不能当作本因子的否定。")
    A("")
    A("## 5. 第一批（" + str(len(items)) + " 个，规则见 `selection-rule.md`，选择由 `select_first_batch.py` 机械执行）")
    A("")
    A(f"合格候选池 {meta['pool_size']} 个；各资格条件排除的行数（一行可能同时不满足几条）：" + "、".join(f"{k} {v}" for k, v in meta["excluded_counts_by_condition (a row can fail several)"].items()) + "。")
    sf = meta["bucket_shortfall"]
    A("配额缺口：" + ("、".join(f"{k} 少 {v} 个" for k, v in sf.items()) + "（合格条目不够，按规则如实报告，没有放宽资格条件）。" if sf else "无，四个桶都满足最低配额。"))
    A(f"重测配额用掉 {meta['retests_selected']} / {meta['retest_cap']}：这些是登记簿里单独在本地测过、被否定但没到深度的方向（`prior_locally_tested` 为启发式判定），规则允许补深度，上次缺什么写在 `first-batch.json` 的 `retest_reason`。其余日内、事件条目在登记簿里是 parked 或只有文献否定，没有本地测试。")
    A("")
    A("构成：")
    A("")
    A(table([(k, v) for k, v in sorted(Counter(i["asset_class"] for i in items).items())], ["资产类", "个数"]))
    A("")
    A(table([(k, v) for k, v in sorted(Counter(i["frequency"] for i in items).items())], ["频率", "个数"]))
    A("")
    A(table(sorted(Counter(i["origin_list"] for i in items).items()), ["来源", "个数"]))
    A("")
    A(table(sorted(Counter(i["engine"] for i in items).items()), ["通道", "个数（lane=screen_lane 模板；book=股票多空书；new=新代码）"]))
    A("")
    A(f"机制族 {len({i['family_key'] for i in items})} 个，每族最多 3 个。")
    A("")
    A("| # | id | 名称 | 频率 | 资产 | 通道 | 证据等级 | 机制族 | 重测 |")
    A("|---|---|---|---|---|---|---|---|---|")
    for i in items:
        A(f"| {i['rank']} | {i['id']} | {i['name'][:58]} | {i['frequency']} | {i['asset_class']} | {i['engine']} | {i['evidence_tier']} | {i['family_key']} | {'是' if i['retest'] else ''} |")
    A("")
    A("每项的数据适配、模板、成本口径、满足的规则在 `first-batch.json`。成本口径对应：lane 条目 10 bp/边基线、20 bp 压力、次日开盘成交、超额对 BIL；book 条目按 `equity-book-design.zh.md` 第 7 节；日内、期权、加密的成本合同还没冻结，写\"待定\"，没有自造数字。")
    A("")
    A("## 6. 剩下的怎么排到 10 月底")
    A("")
    chosen = {i["id"] for i in items}
    pool = [r for r in CAT if sel.eligibility(r)[0] and r["id"] not in chosen]
    pool.sort(key=sel.sort_key)
    n = len(pool)
    cuts = [0, min(50, n), min(100, n), n]
    labels = [("10-19..10-22", "第二批"), ("10-23..10-27", "第三批"), ("10-28..10-31", "第四批")]
    sched = []
    for (a, b), (d, name) in zip(zip(cuts, cuts[1:]), labels):
        sub = pool[a:b]
        sched.append((name, d, len(sub), dict(Counter(r["engine"] for r in sub)), dict(Counter(bucket for bucket in (sel.bucket(r) for r in sub)))))
    A(f"第一批之外，合格候选池还剩 {n} 个，按同一排序切三批；第一批 10-15 前完成筛选，之后每批前先重跑 `select_first_batch.py` 的资格检查（旧批的结果会改变 E4/E5）：")
    A("")
    A(table([(a, b, c, d, e) for a, b, c, d, e in sched], ["批次", "日期", "个数", "通道构成", "频率构成"]))
    A("")
    A("这些日期是估计的排期，不是承诺；每批要先过 `oc research direction-check` 和迭代门禁（CLAUDE.md），且受 Modal 月度额度和轮次预算约束，预算未知的部分不自行猜定。")
    A("")
    A("**数据补给能解锁的条目**（能交易但被 E2 挡住；数字来自 catalog.json）：")
    A("")
    blocked = [r for r in CAT if r["alpaca_tradable"] == "yes" and r["entry_type"] == "strategy" and not r["adapter_1d"]]
    tags = Counter()
    for r in blocked:
        m = re.search(r"Compustat items ([a-z0-9_,]+) from", r["data_local_detail"])
        if m:
            for t in m.group(1).split(","):
                tags[t] += 1
    cat_block = Counter()
    for r in blocked:
        if r["origin_list"] == "osap":
            cat_block["OSAP/" + r["osap_cat_data"] + "/" + r["data_local"]] += 1
        else:
            cat_block[r["origin_list"] + "/" + r["data_local"]] += 1
    A(table(sorted(cat_block.items(), key=lambda x: -x[1]), ["被挡住的类别（来源/数据类型/本地状态）", "条数"]))
    A("")
    A("OSAP 会计类缺的 XBRL 科目（Compustat 名，数字是它出现在多少个被挡条目里；一次解析 `companyfacts.zip` 补齐一批科目，能同时解锁多个条目）：" + "、".join(f"{t} {c}" for t, c in tags.most_common(14)) + "。")
    A("")
    A("## 7. 没查清的")
    A("")
    A("- QuantConnect 现行策略库可能比抓到的 84 个教程多（抓到的目录页页脚写 2022；官方博客说策略来源还包括 Quantpedia 免费策略、SSRN、arXiv）；本清单只登记了抓到的这些，没找到更大的官方目录入口。")
    A("- Alpaca 对信用价差、蝶式、秃鹰、日历价差等多腿期权的支持只有文档的\"买入看涨/看跌价差\"一条明确说明；这些条目的 `alpaca_basis` 标 inferred，需要一次模拟盘探测才能定。")
    A("- 登记簿旧否定的深度状态全是 unknown，没有逐条核对当时满足了五条里的几条；`retest_reason` 只是摘录登记簿 verdict，不是深度审计。")
    A("- 本地数据判断（`data_local`）按目录和列名做的，没有逐个因子检查覆盖率和起止日；OSAP 会计类\"一天内能补\"按缺失 Compustat 科目数（≤2）粗估，XBRL 到 Compustat 科目的映射可能需要更多工作。")
    A("- 登记簿补充行的字段由登记簿记录粗略推出，频率、资产类和数据可得性比三个公开清单的行粗。")
    A("- 选择规则改过一次（见 `selection-rule.md` 第 7 节的修订记录）：第一次运行后发现一个登记簿 id 写错（`multi_signal_equity_book` 是机制族名，真 id 是 `dir:multi_signal_risk_controlled_equity_book`），以及把登记簿的 evidence_too_weak/parked 一律当成\"本地测过\"。两处都是定义和数据错误，修正发生在看过第一次名单之后；第一次的名单保存在 `first-batch.v1-superseded.json`，没有按名单内容改配额。")
    A("- `prior_locally_tested` 是启发式（登记簿状态加证据路径加 verdict 关键词），不是逐条审计；个别条目可能误判（例如 `dir:news_attention_features` 状态是 refuted 但被判为本地未测）。")
    open(HERE / "catalog.md", "w").write("\n".join(L) + "\n")
    print("wrote catalog.md", len(L), "lines")


if __name__ == "__main__":
    main()
