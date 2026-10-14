---
name: idea-to-paper
description: >
  Develop an investment or strategy-research idea, challenge, or requirement
  into source-led research and a decision about its economic contribution.
  Covers strategies, factors, data, models, timing and execution; paper
  deployment applies only when relevant and authorized. Unrelated product,
  documentation and agent-method maintenance do not use this research workflow.
---

# 从研究想法到有效决策

依据 `docs/research-mission.zh.md` 和 `docs/task-owned-research.zh.md` 判断当前目标，依据 `reports/research/control/owner-compute-hold.json` 判断动作授权。2026-10-13方法更新前瞻适用；旧冻结合同、已见窗口、累计预算、纸盘授权与停止规则保留。

先理解想法要改善的决策及现有组合/研究中的用途。研究对象可以是因子、数据、模型、择时、风险或执行组件，不默认生成独立策略、账户或sleeve。简短质疑可直接用证据回答；以下内容按问题选用，不是每次必填的流程。

## 选择值得投入的问题

复用现有方向、原始结果、模型记忆和新鲜来源。新方向或关键设计先查原论文/实现、公开结果、独立复现、发表后变化与反证；保存实际读过的来源，搜索摘要不等于原文。不设固定来源类别或年份配额。

比较收益用途、证据强度、复现差距、成本/容量与投入，给出自己的判断；不因数据现成、模型新或熟悉旧任务而决定方向。已知失败只约束它实际检验的主张，错误摘要可依据原结果注明更正；重开需要可指认的新信息或差异，原失败和曝光不清零。

## 让实验回答关键问题

区分忠实复现与本地适配，保留原定义、真实输入、PIT可见时间和允许分区。按主张选择足够样本、信息、模型容量或执行尺度；三点规模曲线是可用方法，不是通用数量要求。邻近参数和成本档不能冒充机制覆盖。

基线、安慰剂、功效、多重检验、借券/融资/费用、滑点/延迟、永久证券身份和价格卫生按实际风险使用。注意小账户整股/容量限制、IEX实时与SIP历史的差异，以及纸盘成交不能证明真实可成交。组件成果按当前研究阶段验收；IC、数据就绪或流程通过不能冒充净收益。

可调参数与多模型研究按现有准入范围登记候选、选择规则和累计试验；不设统一30变体、最高三点中位或每轮只改一两个变量。新定义按允许范围形成新版本，已冻结窗口与成功门不回改。模型角色、匹配增量、缺模态和fallback按用途设计，不为每个任务凑全模型角色。

## 自主执行与适用审查

完整owner对准备、实现、下一实验、修复、解释和接续负责。批准探索空间内、不改变冻结科学定义的连续实验与普通代码实现/恢复，复用原完整包和累计上限；不因写代码、换目录或方法维护重新触发经济审查。

新经济假设、关键科学定义变化或真正超范围工作，使用 `research-plan-reviewer` 对受影响部分独立审查；作者不冒充独立reviewer。策略经济执行前使用真实适用的 `oc research direction-check`、`oc research iteration validate`、knowledge/campaign等原生门；来源和同语义修复可继续解除缺口，门未过不启动依赖它的经济计算。

组织agent的prompt/工具/分工可在授权范围内改进；用于生成特征、标签或信号的prompt/模型变化则核对科学影响。角色、effort与fallback从 `config/research-agent-roles.json` 读取，实际槽位和内存准入见 `config/memory-budget.json`；重任务用现有 `scripts/run_capped.sh`，不沿用旧固定时间窗。使用Modal仍先过现有预算检查，Hadan按worker合同，不新增付费。

## 深度、停投和交付

预算是上限，不是必须用完的目标。浅层无效不足以否定整个机制；对具体主张的否定需要相称的忠实性、功效、机制覆盖和反证。证据不足可标 `not_at_depth`，同时依据机会成本、输入限制或反证选择继续、暂缓或停止投入，写清尚未证明什么。硬资源/设备/授权边界始终优先；not_at_depth不自动获得追加投入。

可信深挖可跨日，用实际新增证据与下一行动维持连续性；不为日/周数量削深，也不无限研究直到赚钱。尽快取得经济或依赖解除成果，因子/数据/模型组件不强制两周独立上盘。适用shadow/paper工作按既有授权、账户容量、到期、仓位上限和停止规则推进；不新增账户或自动续签，不因本技能扩大实盘权限。

按既有任务状态和报告路线交付：实际问题与结论、原始证据、限制、累计投入和下一动作。区分 workflow_pass、research_pass、ml_contribution_pass、llm_contribution_pass、paper_ready_pass，缺有效评估则收益N/A。保留有用经验和失败，不新建报告/恢复/技能管理平台。

部署或前向监测时，按需查 `docs/plan-v3-2026-10-06.zh.md` 的既有sleeve/授权合同、`docs/evaluation-standard.zh.md` 的适用评价，以及 `docs/owner-reporting.zh.md` 的报告路线；这些入口中的旧通用步序/两周要求按现行方法解释，已有60交易日有效期、交互授权、IEX信号对照和停止/监测约定不由技能精简取消。
