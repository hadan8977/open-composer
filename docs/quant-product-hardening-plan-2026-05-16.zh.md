# Open Composer 量化可信度加固计划

日期：2026-05-16

## Review 结论

原审查报告指出的方向是正确的，但如果一次性把真多因子平台、LLM 策略 DAG、另类数据流水线、执行引擎、几何拓扑沙盒全部实现，会导致改动范围失控，也无法在一次迭代里充分验证。

本次执行计划改为一个可落地的量化可信度 MVP，先补产品底座中最影响策略可信度的能力：

1. 通用回测指标不再只看 Sharpe。
2. 回测报告默认披露流动性、成交难易度和容量压力。
3. 多因子策略有最小可用的 Factor Lab 诊断，能回答因子是否有前瞻收益、分位表现、换手和共线性风险。

LLM 策略 DAG、另类数据自动特征流水线、几何/拓扑特征族仍保留在路线图中，但必须建立在上述三项默认验证能力之后。

## 本次严格执行范围

### P0：计划文档落库

交付：

- 新增本文件，作为可进入 GitHub 的计划文档。
- 保留完整审查报告作为本地研究输出，但本文件是本次执行依据。

验收：

- 文档在 `docs/` 下，不受 `reports/research/*` ignore 规则影响。

### P1：通用回测指标扩展

交付：

- 扩展 `PerformanceMetrics`。
- 扩展 `BacktestRun`。
- 回测报告展示新增指标。

指标：

- annualized volatility。
- max drawdown。
- downside volatility。
- Sortino。
- Calmar。
- win rate。
- profit factor。
- average trade return。
- exposure ratio。
- turnover estimate。

验收：

- 样例回测能生成这些字段。
- Markdown 报告包含这些字段。
- 现有回测假设不变：bar-close signal、next-bar-open fill。

### P2：执行现实与流动性检查

交付：

- 新增执行现实评估结构。
- 基于 OHLCV 生成保守的流动性/容量诊断。
- 报告中展示平均 dollar volume、最差 dollar volume、最大 bar participation、最大 ADV participation、容量状态与警告。

限制：

- 本阶段不引入真实盘口 quote。
- 本阶段不模拟 partial fill。
- 本阶段使用 conservative proxy，不把 proxy 伪装成真实成交。

验收：

- 样例回测报告包含 `Execution Reality` 章节。
- 低成交量或高参与率会产生 warning。

### P3：轻量 Factor Lab

交付：

- 新增 `open_composer/research/factor_lab.py`。
- 新增 CLI：`uv run oc strategy factor-lab <spec>`。
- 输出 JSON 和 Markdown。

指标：

- factor coverage。
- forward return correlation。
- RankIC。
- quantile mean forward return。
- top-bottom spread。
- factor turnover。
- factor correlation matrix。
- quality flags。

限制：

- 本阶段只做单标的 OHLCV frame 内的 factor 诊断。
- 行业中性化、风险暴露、组合归因、orthogonalization 放入后续阶段。
- feature packet/LLM factor 只在可回放时参与诊断，不实时调用 LLM。

验收：

- 有表达式 factor 的样例 spec 能生成 Factor Lab 报告。
- 多因子共线性会被标记。
- 缺少 factor 的策略会输出阻塞型提示，而不是静默通过。

## 后续路线图

### R1：默认研究合约

- `oc strategy draft` 生成 research contract。
- `oc strategy research-report` 串联 validate、capability、backtest、promotion、factor-lab、execution reality。
- paper readiness 必须读取 research contract。

### R2：完整 Factor Lab

- 横截面 IC/RankIC。
- 行业/主题/市值/波动率/流动性中性化。
- 因子收益归因。
- factor ablation。
- factor timing by regime。

### R3：LLM/另类数据 StrategyDAG

- 量化节点、LLM 节点、风险节点、执行节点统一为可回放 DAG。
- LLM live 调用必须先写 decision packet，再进入策略逻辑。
- 回测只允许 replay packets。

### R4：几何/拓扑研究沙盒

- path signatures。
- TDA/persistent homology。
- covariance manifold drift。
- graph topology。
- 所有特征必须通过 Factor Lab、OOS、成本后、ablation 和基线对比。

## 本次执行结果

已完成：

- P0：计划文档落库到 `docs/quant-product-hardening-plan-2026-05-16.zh.md`。
- P1：通用回测指标扩展，回测报告展示新增风险、交易质量和暴露指标。
- P2：新增 OHLCV-only 执行现实检查，报告展示流动性、参与率、容量和 warning。
- P3：新增轻量 Factor Lab，并提供 `uv run oc strategy factor-lab <spec>` CLI。

验证：

- `uv run ruff format .`
- `uv run ruff check .`
- `uv run pytest`：233 passed，1 warning。
- `uv run oc capability test`：所有注册能力测试通过。

## 完成审计标准

本次任务只有在以下条件全部满足后才算完成：

- 计划文档存在于 `docs/`。
- P1/P2/P3 代码完成。
- 新增或更新测试覆盖 P1/P2/P3。
- `uv run ruff format .` 通过。
- `uv run ruff check .` 通过。
- `uv run pytest` 通过。
- `uv run oc capability test` 通过。
- Git 工作区只包含本次相关变更和用户已有忽略文件。
- 最新提交成功 push 到 GitHub。
