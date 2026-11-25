# Research mission

本周派工和账户排名见[研究章程](../research/charter.zh.md)。三件共享工具优先支持在任一已登记决策时刻计算特征与标签、在同一个账户回放多股盘中意图、将原始文本转成点时信号。模型研究按消息的到达和吸收速度选择机会池、触发和持有期。方法与因子的入口见[方法库](../research/library/methods.zh.md)和[因子目录](../research/factor_factory/README.md)。

研究取舍见 [owner-taste.md](owner-taste.md)，硬约束见 [rules.md](rules.md)。下列记录保留了各日期当时的安排。11 月 19 日计划原件在 C:\OpenComposer\ops\research-plan-20261119\plan.zh.md。

## 11 月 19 日计划存档（2026-11-19 09:00 PST）

- The goal is live after-cost money in one account; paper proves it first.
- Two project-level priorities, each proven before rollout:
  1. Model-first research on non-price information (trained models on
     point-in-time fundamentals, guidance, positioning, options and text;
     rules on price bars are baselines only).
  2. A research loop at least ten times faster and cheaper with quality kept
     (compact experiment specs on shared engines, one numerical batch per
     preregistered family, look-ahead enforced in the data layer).
  Design: C:\OpenComposer\ops\research-plan-20261119\redesign-astra.md.
  Acceptance criteria, fixed before implementation:
  C:\OpenComposer\ops\research-plan-20261119\proof-contracts.md.
  Surveys: pros-ml-altdata.md, rules-to-models-and-fast-loop.md,
  data-inventory.md in the same folder. Claude owns the first-wave retrospective after its quota resets. During the pause Codex owns research decisions, source research and next-family selection under C:\OpenComposer\ops\handoff-20261119.zh.md. Codex
  GPT-6.2-astra designs and implements shared changes; GPT-6.2-sol runs
  routine work; pi DeepSeek V4.1 Flash does bulk extraction.
- Stock selection and individual-stock opening breakouts are in numerical replay and input reconstruction. The independent activist-filing study is classifying public demands. The SPY close study uses disclosed leveraged-fund assets. Analyst revisions belong to the existing stock account. ETF rotation family 1 is closed. Apply each family's advancement test and the account-wide priorities when choosing follow-ups. The measured throughput and economic outcomes are recorded in research/README.md and the proof reports.
- Line dispositions (details at the end of each scope.md): event_driven
  archived; jlaw_catalyst_pullback and martin_full_market parked;
  quant1_information concluded (not a live candidate); smallcap_momentum
  paused; levered_index_trend candidate 3 is prepared as a $15,000 paper
  sleeve (deploy and enable after the 2026-11-19 close; 20 sessions vs S3);
  martin_source_rebuild's A0 rule is the baseline for proof A.
- Use only inputs known before each decision. Heavy compute on Modal.
- Parked: martin_setup_followthrough_allocation_20261118. Do not add rules or
  attribution on the 2026-01..09 frozen Martin name lists.

## 周复盘决定（2026-11-22 12:00 PST，主会话）

本周没有任何研究线在开发期或样本外拿到被接受的扣费净收益，没有系统进入模拟盘。周额度 11-20 01:31 PST 到 91% 后研究暂停，11-23 07:30 PST 重置。

| 研究线 | 本周结果 | 决定 |
|---|---|---|
| 股票多因子模型 equity_ml_20261120 | 108 个配置已拟合；账户回放发现成交价单位错误（QBTS $7.53 记成 $0.76，ROOT、BNED 同类），旧账户作废 | **加力**：重置后先修共享成交单位并复核，再回放同 108 项；之后第二族加入时点正确的分析师修正 |
| 日内热门股 intraday_in_play_20261120 | 机会池漏掉当时合格股票，修复中（存至 2023-06） | **继续一族**：补齐全年机会池并核验后按原登记回放；仍覆盖不了成本即停 |
| ETF 择时 etf_timing_20261120 | 三次回放 0/16，对 C3 的优势剔除半导体段后为 0 | **停**；空头持仓对 C3 的仓位调节仅列候补 |
| SPY 尾盘 spy_intraday_momentum | 2022–24 净亏 $494，2024 全年持现 | **停** |
| 小盘盘前催化 smallcap_momentum_20261119 | 方案获审；183 个合格股日中仅 21 个能容纳 $6,250 | **继续一族**，按实际容量计账户；容量不足即停 |
| 13D 激进股东 activist_13d | 428 条标注 | **继续**到账户回放的事件数检验 |
| 分析师修正输入 | 主档修订后 1,652/2,165/1,719 组 | 随股票线第二族使用 |

教训：本周主要投入在数据正确性（SEC 续页、停牌时区、股本单位、分析师首见时间、成交价单位）。新数据接入前先做时点和单位抽查，而不是靠计划审阅逐个发现。
