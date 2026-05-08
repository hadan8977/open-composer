# Open Composer

Open Composer 是一个面向个人交易学习者的对话式 AI 策略工作台。

第一版用文件仓库作为产品界面：用户用自然语言描述交易想法，Codex 在仓库约束下生成 `StrategySpec`、Python 回测/扫描、TradingView Pine Script、信号日志、报告和交易复盘材料。用户先通过 TradingView/本地扫描获得 15m、1h、daily、weekly 级别的信号，再手动决定交易动作。

## 当前状态

这个仓库目前处于产品定义和实现交接阶段。下一步是在新会话中按照 `OPEN-COMPOSER-BUILD-HANDOFF.md` 生成可运行项目骨架、CLI、样例策略、样例数据和测试。

## 阅读顺序

1. [OPEN-COMPOSER-BUILD-HANDOFF.md](OPEN-COMPOSER-BUILD-HANDOFF.md)
   - 新实现会话的唯一开工入口。包含产品定义、技术路线、目录结构、CLI 合同、Skill 合同、任务顺序和验收标准。

2. [OPEN-COMPOSER-PRODUCT-MVP.md](OPEN-COMPOSER-PRODUCT-MVP.md)
   - 正式 MVP 文档。说明用户、问题、范围、技术架构、核心流程、成功标准和阶段路线。

3. [OPEN-COMPOSER-CONTEXT-SUMMARY.md](OPEN-COMPOSER-CONTEXT-SUMMARY.md)
   - 背景研究总结。说明产品方向、市场参考、工具选型、LLM/Codex 分工和文档设计依据。

## 实现路线

```text
StrategySpec-first
  -> Codex AGENTS.md + repo skills
  -> Python signal/backtest/scanner engine
  -> TradingView Pine export
  -> signal parity report
  -> reports + signal logs + journal
  -> optional LLM review cards
  -> later data, paper-tracking, execution, and research adapters
```

`OPEN-COMPOSER-BUILD-HANDOFF.md` 是当前实现依据。其他文档用于补充产品判断和研究背景。
