# Open Composer Step 7 完整执行计划：ML / Decay / LLM 三角色

日期：2026-07-02
方法：UltraCode review lanes + 本地验证 + 逐 wave 提交
前置：Step 6.5-6.8、Step 7.A 初版与 hardening 已落地

## 0. 目标

把 Step 7 从“只完成 7.A ML backend”推进到完整闭环：

- 7.A：确认并补齐 ML 训练、OOS、promotion gate、CLI 与 auto research model emit。
- 7.B：实现因子衰减监控，写入 `reports/factors/{factor_id}/decay-monitor.jsonl`，提供 CLI、通知、Dashboard 只读视图。
- 7.C：实现 LLM 三角色的安全最小版本：
  - L1 `oc factor propose`：LLM/本地 stub 只提出候选因子，必须过 AST + IC/IR + 相关性闸门后进入 pending artifact。
  - L2 `oc strategy explain`：从 ML training artifacts 生成结构化解释与 trace；LLM 只 advisory，不改变交易逻辑。
  - L3：记录 `qqq_news_regime_15m` 全历史 materialize 的可重复命令与状态，不在无明确成本确认时强行触发大量 live LLM 调用。

## 1. 产品边界

- `StrategySpec` 仍是策略行为源头。
- CLI + 文件是第一产品表面；Dashboard 只读，不跑回测、不写策略、不发 broker order。
- real-money broker write access 仍然 out of scope。
- sample、fixture、cache fallback、proposal-only、LLM advisory artifacts 都不能标成 paper-ready Alpha。
- LLM/news/event/macro 特征只有 point-in-time replay packet 与 marginal lift evidence 完整后，才能影响 promotion。

## 2. 当前状态

已完成：

- `StrategySpec.model` schema、LightGBM 后端、purged/embargo rolling training。
- `oc strategy train`、`oc strategy backtest-walk-forward`、`oc strategy explain` 轻量 ML feature importance。
- ML promotion 已使用 stitched OOS prediction stream 和 ML fold metadata。
- `oc research auto --model lightgbm` 已存在。

未完成：

- 7.B 的 `factor_decay.py`、`oc factor decay-monitor/decay-report/retire`、Dashboard factor decay read model。
- 7.C.L1 的 proposal artifact workflow。
- 7.C.L2 的 structured LLM advisory explanation + trace。
- 7.C.L3 的 backfill 状态记录。

## 3. UltraCode Review Lanes

1. Code path and tests：CLI shape、artifact paths、deterministic tests、repo check。
2. Quant method：IC/IR、decay threshold、no lookahead、proposal overfit/correlation gates。
3. Data capability：sample/cache/live tier 不混淆；LLM proposal 不等于 paper-ready evidence。
4. Execution and paper safety：所有新增命令只写研究 artifacts，不激活 paper/live。
5. Product UX：报告和 Dashboard 清楚显示 healthy/watch/retired/pending/advisory 状态。

## 4. 执行 Waves

### Wave 7.0 文档与严格 review

- 新增本文档。
- 用 sidecar review 分别审查 7.A、7.B、7.C。
- 更新 `repo_check.CURRENT_DOCS`。

验收：

- 文档入 `CURRENT_DOCS`。
- review 结论被纳入后续实现或风险记录。

### Wave 7.B 因子衰减监控

新增：

- `open_composer/research/factor_decay.py`
- CLI：
  - `oc factor decay-monitor [--factor-id ...]`
  - `oc factor decay-report [--days N]`
  - `oc factor retire FACTOR_ID --reason ...`
- Dashboard：
  - catalog JSON 增加 `factor_catalog`
  - API `/api/factors/{factor_id}/decay`
  - React 只读 Factor Catalog tab
- cron 脚本：`deploy/cron/factor-decay-monitor.sh`

验收：

- lineage 缺失时明确报错。
- 有 lineage 的 factor 可写 `decay-monitor.jsonl`。
- insufficient data 不误报 decay。
- 连续告警可在 report 中显示 watch/retire?。
- Telegram 通过现有 `safe_dispatch_notification(kind="system_alert")`，不会因配置缺失阻塞监控。

### Wave 7.C.L1 因子提案

新增：

- `open_composer/research/factor_propose.py`
- CLI：
  - `oc factor propose THESIS --base-factors ... --max-candidates ...`
  - `oc factor approve PROPOSAL_ID`
  - `oc factor reject PROPOSAL_ID --reason ...`

保守边界：

- `approve` 只更新 proposal artifact 状态并写 approved ledger，不自动修改 `factor_library.py`。
- proposal 通过 expression AST safety、IC/IR、与现有因子相关性闸门后才进入 `pending_review`。
- 无 OpenAI key 时使用 deterministic local candidate generator，保证 sample-data workflow 可跑。

验收：

- 重复 catalog id 被拒绝。
- 不安全表达式被拒绝。
- 低 IC/IR 或高度相关候选不会 pending。
- pending/approved/rejected 都是结构化 JSONL artifacts。

### Wave 7.C.L2 结构化策略解释

新增：

- `open_composer/research/llm_explainer.py`
- `oc strategy explain SPEC --llm/--no-llm --top-n N`

行为：

- 默认 no-llm：从 ML training JSON / live training run 写 deterministic explanation。
- `--llm` 且有 API key：用 structured schema 生成 advisory explanation。
- 写：
  - `reports/research/ml/{strategy}/explain.md`
  - `reports/research/ml/{strategy}/explain.json`
  - `reports/research/ml/{strategy}/trace.jsonl`
- 不修改 StrategySpec，不追加 promotion 结论为通过。

验收：

- 无 model 的 spec 会被拒绝。
- 无 API key 的 `--llm` 有清晰 fallback/status，不失败污染报告。
- trace 记录 model、prompt hash、input hash、operation。

### Wave 7.C.L3 LLM factor backfill 状态

新增：

- `reports/research/llm_backfill/qqq_news_regime_15m-backfill-plan.md`
- 记录可重复命令、预期 packet path、当前 packet count、是否执行 live backfill。

验收：

- 不强行触发大量 OpenAI 调用。
- 文件明确写出执行命令和 paper-readiness 限制。

## 5. 全局验收

- `ruff format .`
- `ruff check .`
- `pytest tests/ -q`
- `oc repo check --strict`
- `make verify`
- 工作树扫描确认只提交源码、测试、文档和必要脚本，不提交 cache/report churn。

## 6. 非目标

- 不做 cross-sectional ML 7.A.2。
- 不引入 PyTorch / deep RL / Qlib workflow。
- 不让 LLM 直接生成 entry/exit 或自动交易。
- 不启用 paper_auto 或 live broker writes。
- 不自动把 LLM proposal 写入 factor catalog 源码。
