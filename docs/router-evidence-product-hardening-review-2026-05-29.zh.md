# Router Evidence 产品硬化复盘与执行计划

日期：2026-05-29

## 背景

在继续优化 `nasdaq_long_short_event_router_1m_sweep_001` 时，策略本身的主要问题已经不是参数表现，而是产品证据链的可用性：

- `oc strategy evidence` 对 router 策略进入通用单标的 backtest/factor-lab 链路，运行过久且没有进度输出。
- research brief 要求 `shorting` source card，但已有 source card 使用的是 `short_selling` 风险域命名，导致验证误报缺失。
- 历史 source card 中存在 `limitations: []` 旧格式，当前 Pydantic schema 要求字符串，导致 evidence 管道直接崩溃。

这些问题会削弱 Codex/Claude Code 的优势：模型已经能生成正确的 router 证据，但产品控制面把它带进了不合适的通用流程，浪费上下文、时间和迭代预算。

## 严格 Review

### 1. Router evidence 轻量路径

必要性：高。

原因：

- router 策略已经有专用 artifacts：router research、target weights、data evidence、cost stress、promotion、harness verify。
- 通用 backtest 和单标的 Factor Lab 不适合 portfolio-level / intraday router。
- evidence 命令必须是汇总已有证据的 reducer，而不是重新跑一套不匹配的研究流程。

决策：

- 对 `adaptive_intraday_internal_router`、`hybrid_adaptive_router`、`beta_exposure_router` 使用轻量 router evidence report。
- 保留普通单标的策略的原 evidence 路径。

### 2. Source card 旧格式兼容

必要性：高。

原因：

- 本地已有 artifacts 使用过 `limitations: list[str]`。
- 因为一个非核心字段格式差异让整条 evidence 管道失败，不符合持续迭代产品定位。

决策：

- SourceCard 模型在读入时把 list 格式规范化为字符串。
- 不改变 source card 的核心 claim/source/accessed_at 语义。

### 3. Method family alias

必要性：中高。

原因：

- 产品内部有 `shorting`、`short_selling`、`short_sale` 等相近命名。
- 这类命名差异不应该阻塞用户已经补齐的正式来源卡。

决策：

- research brief validator 对 `shorting` 增加别名匹配。
- 不降低 source card 必填要求，只修正误判。

## 已执行修改

1. `open_composer/research/evidence.py`
   - 增加 router 专用 lightweight evidence path。
   - 生成 `router_research_report`，跳过通用单标的 backtest/factor-lab。
   - 保持 promotion、paper readiness、harness verify 分离。

2. `open_composer/models/source_card.py`
   - 兼容旧的 `limitations: list[str]`。

3. `open_composer/research/research_brief.py`
   - 增加 `shorting` 方法族的 source-card alias 匹配。

4. 测试覆盖
   - SourceCard 旧 limitations 格式。
   - shorting/short_selling source-card 匹配。
   - router evidence 不再调用 generic research report。

## 验证

- `uv run ruff format .`
- `uv run ruff check .`
- `uv run pytest`
- 真实策略命令：
  - `oc strategy evidence strategy_specs/drafts/nasdaq_long_short_event_router_1m_sweep_001.yaml`

结果：

- 全量测试通过。
- router evidence 命令从长时间无输出，变为几秒内完成。

## 后续建议

1. 为 router evidence 增加阶段进度输出。
2. 让 Dashboard 明确显示 `workflow_pass`、`research_pass`、`llm_contribution_pass`、`paper_ready_pass` 的差异。
3. 为 strict data 添加专门的下一步 action：SIP/第二数据源对比，而不是继续参数搜索。
4. 把 `core_beta_satellite_router` 补进 router promotion/evidence 专用路径后，再纳入 lightweight evidence。
