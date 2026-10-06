---
name: idea-to-paper
description: >
  Use whenever the owner states an idea, direction, doubt, complaint or new
  requirement (for example "为什么不做高频", "一个账户只测一个策略没意义",
  "另类数据还能挖什么"), and whenever a new research direction is opened.
  Turns one sentence into the work a professional quant shop would do: owner
  intent, how institutions, mature individuals and good open projects solve
  it, a judgment first, a family of variants run to minimum effective depth,
  paper trading within 14 days, iteration, and a plain-language report.
---

# 想法到模拟盘

机主 2026-10-06 要求：每次输入一个想法，都要主动想专业量化机构、成熟个人和优质项目怎么落地，站在巨人的肩膀上；先给判断，再构造、深入研究、优化、迭代。本流程把这件事固定下来。规则来源：`docs/plan-v3-2026-10-06.zh.md`、`docs/research-mission.zh.md`、`docs/owner-rules-register.zh.md`。

## 1. 意图

- 写一句"机主想要的是……"，分清他说的和他想的。例如他问"为什么只测两个策略"，真正要的是"模拟盘容量要变成研究吞吐量和高夏普"。
- 对照 `docs/owner-rules-register.zh.md` 和使命文件，查有没有冲突；有冲突先解决再动手。

## 2. 业界怎么做

至少看三类来源：
- 机构：论文、白皮书、量化基金公开分享；
- 学术：原始论文，以及发表后的复现和反面证据，包括发表后的衰减；
- 成熟个人和项目：GitHub 实现、QuantConnect 社区、带实盘记录的策略，重点看 2024 年以后的。

要求：
- 搜索摘要不算读过：打开原文，快照存到 `reports/research/intel/sources/<主题>/`。
- 先查本地：方向登记簿 `reports/research/harvest/directions.jsonl`（每个 id 看最后一行）、旧实验、策略库 `reports/research/strategy-library/catalog.json`。
- 已否定的方向，只有新增可指认的信息、数据或机制时才重开，并写明差异。

## 3. 先给判断

写出判断，每一项都要有依据，不编数字：
- 值不值得做，为什么；
- 预期夏普和容量的量级；
- 主要风险；
- 和现有子策略的相关性；
- 用哪个账户。

多个候选按期望价值排序，并说明不做的理由。

## 4. 一族变体，不是一个想法

- 写出参数、方法、因子、股票池、频率等变体，每个轴至少三个深度点。
- 同时写同暴露的简单基线和安慰剂。
- 模型按经济问题选，并和简单基线比增量。

## 5. 补上机主没提的问题

每次都过一遍：
- 功效：能检出的最小夏普，最短样本；
- 多重检验：有效试验数、DSR；
- 成本：价差（开盘和收盘时段）、借券、手续费；
- 执行：模拟盘成交偏乐观；实时行情是 IEX，回测是 SIP；
- 资金：整股取整、小资金、容量；
- 组合：子策略之间的相关性；
- 状态：适用的市场状态、失效信号、退出规则；
- 数据：时点正确，不偷看；
- 授权：到期日。

## 6. 最快拿到样本

- 先想怎么用历史数据一次检验很多事件、很多品种，不等前向数据慢慢攒。
- "攒够 60 个发布日再测"这种设计不允许。
- 确实只能前向的，先上模拟盘，边跑边攒。

## 7. 预注册和执行

- 档案：`uv run oc research iteration init`；写 `direction-review.json`；`uv run oc research direction-check <档案>`；`uv run oc research iteration validate <档案> --stage pre-backtest`。
- 派独立 Paseo 代理（`claude/sonnet`，high），派之前在队列里标为运行中。
- 任务说明照 `reports/research/control/briefs/T-20261006-21.md` 的结构写：任务代码、目标、业界做法、预注册网格、数据、成本、交付、禁止、汇报、上限。
- 重任务用 `flock /tmp/oc-heavy.lock ./scripts/run_capped.sh --mem 1.2G -- …`；上 Modal 先过 `scripts/modal_budget.py check`。

## 8. 两周时钟

- 立项起 14 天内，要么到评价标准的 P0 以上并上模拟盘，要么按五条深度规则否定。五条是：复现原文、忠实实现、至少三个深度点的规模曲线、用完预算、功效足够。
- 大模型模块可以延长研究时间，但简单版照样两周上模拟盘。
- "未到深度"不是停放状态。必须写缺哪几条、下一个实验、截止日、预算，然后继续做。

## 9. 上模拟盘

- 子策略规格：信号接口、仓位上限、每日亏损上限、停止条件。
- 授权文件引用机主 10-06 晚的原话："只要你觉得可行的，直接全部上模拟盘去测"。
- 单独记账；每天和回测同口径对照；前向评价用模型成本重算。
- 账户：quant1 放日频和多日子策略，quant2 放日内，主账户放 ETF 和期权。实盘另需机主授权。

## 10. 迭代

- 前向结果和成交质量回到研究：好的加仓，不好的按停止条件停。
- 停掉的写清死因，登记进方向登记簿。

## 11. 汇报

- 用业务语言，先写结论；分证据、计划、结论三段。
- 给机主的文字跑 `uv run python scripts/owner_report.py lint <文件>`，错误必须为 0。

## 以前犯过的错，不要再犯

- 一个 100 万账户只测一个夏普约 1 的组合；
- 只做机主举例的几个方向；
- "攒够 60 个事件再测"这种等待式设计；
- 把"未到深度"当停放；
- 把高频当边缘方向；
- 只回答机主的问题，不提出自己的判断和计划；
- 方案出自自己的脑子，没先查别人怎么做。
