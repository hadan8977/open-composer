# Strict Data Readiness Product Review

日期: 2026-05-29

## 背景

最新策略迭代中，候选 router 的收益、Sharpe 和回撤已经达到研究标准，但 `oc strategy evidence` 仍然返回 `blocked`。实际阻塞不是策略参数本身，而是 `strict_data`：当前证据来自 cached Alpaca IEX 1m 数据，不能作为 paper-ready 市场证据。

## 严格 Review

### 1. 是否有必要

有必要。产品当前把真实阻塞压缩成 `promotion` / `paper_readiness`，会误导 Codex/Claude 继续做参数搜索，而不是先补数据严格性证据。这直接降低策略迭代效率。

### 2. 是否已经做了

部分已做。Promotion JSON 里有 `strict_data` check，但 research report、control state 和 memory packet 没有把它作为首要行动充分暴露。

### 3. 可行性

高。只需要在现有 artifact reducer 中传播结构化 gate details，不需要引入新数据供应商、远程服务或重型工作流。

### 4. 与核心目标的关系

高度相关。核心目标是让 Codex/Claude 在长上下文和文件证据中高效迭代。产品必须把“当前该优化策略，还是该补证据”讲清楚，否则会浪费 agent session。

## 本轮优化范围

1. `strict_data` gate 输出 `blocked_reasons`、`required_evidence_tiers` 和 `next_actions`。
2. Router research report 的 `blocked_items` 使用真实阻塞项，例如 `promotion:strict_data`。
3. Research control 在 router 场景中从 promotion selected route 恢复关键指标。
4. Memory packet 明确提示: 当前应先做 strict data / paper-ready 数据验证，不应继续大范围参数搜索。

## 不做的内容

1. 不接入新的付费数据源。
2. 不放松 paper-ready gate。
3. 不修改策略参数或 paper_auto 状态。
4. 不把 Dashboard/CLI 变成远程执行入口。

