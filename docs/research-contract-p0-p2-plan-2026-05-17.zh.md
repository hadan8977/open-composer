# Open Composer P0-P2 研究合约执行计划

日期：2026-05-17

## 联网调研结论

本轮参考了成熟量化研究与回测系统的公开实践：

- Alphalens：因子研究需要 IC/RankIC、分位收益、换手、因子收益和 tear sheet，而不是只看策略回测收益。
- QuantConnect LEAN：成熟回测把 Alpha、Portfolio、Execution、Risk 分层，并把 fill、fee、slippage、brokerage 作为现实建模模块。
- Lopez de Prado / MLFinLab 方法：多次试验后的策略选择需要 purged/embargo CV、Deflated Sharpe Ratio、PBO/CSCV 等机制，避免把反复试出来的结果当成 Alpha。
- Zipline/VolumeShareSlippage：成交模型至少应考虑成交量参与率和价格冲击，而不是固定 bps 就结束。

调研来源：

- Alphalens 文档：https://alphalens.ml4trading.io/
- QuantConnect LEAN Reality Modeling：https://www.quantconnect.com/docs/v2/writing-algorithms/reality-modeling/key-concepts
- MLFinLab Cross Validation：https://random-docs.readthedocs.io/en/latest/implementations/cross_validation.html
- Zipline Slippage models：https://zipline.ml4trading.io/_modules/zipline/finance/slippage.html

Review 后的判断：

1. P0 必须先做，因为 prompt 生成策略后默认没有统一研究合约，用户不提防过拟合时产品也应该自动做。
2. P1 必须把已有 Factor Lab、Execution Reality、数据质量接入 promotion/readiness，否则只是“展示指标”。
3. P2 可以做 MVP，但不能声称完成完整 LLM 策略图系统。本阶段只做可回放 StrategyDAG schema、LLM decision packet 和另类数据质量报告，先保证不会引入未来函数。

## 本次执行范围

### P0：默认研究合约与一键研究报告

交付：

- 新增 `ResearchContract` 模型。
- 新增 `oc strategy research-report <spec>`。
- research report 串联：
  - spec validation。
  - capability evaluation。
  - reference backtest。
  - factor lab。
  - promotion report。
  - paper readiness summary。
  - checklist：leakage、overfit、live gap、factor、execution、alternative data。
- promotion report 写入 research contract 路径。

验收：

- 不需要用户在 prompt 中主动要求，research report 默认输出防过拟合、未来函数、成交现实和数据质量状态。
- 没有 custom factors、没有真实数据、没有 benchmark family、没有 feature packet evidence 时，报告必须明确阻塞或 warning。

### P1：因子、执行、数据质量增强

交付：

- Factor Lab v2：
  - 多 horizon forward returns。
  - rolling RankIC。
  - factor stability score。
  - factor ablation hook。
  - feature packet/LLM factor replay status 汇总。
- Execution Reality v2：
  - capacity curve。
  - participation cap 建议。
  - slippage stress estimate。
  - promotion gate 接入 `execution_reality`。
- Data Quality v2：
  - provider status、source mode、sample/fixture/fallback、timeframe support、feature packet PIT status、alternative data quality。

验收：

- promotion report 将 Factor Lab 和 Execution Reality 纳入 checks。
- paper readiness 能阻塞执行现实或研究合约不完整的策略。
- dashboard/catalog 至少能读取新增报告的 status。

### P2：LLM/另类数据 MVP

交付：

- 新增 StrategyDAG schema。
- 新增 LLM decision packet schema。
- 新增 `oc strategy dag-validate <path>`。
- 新增 alternative data quality report。
- LLM 节点规则：
  - 回测禁止实时调用 LLM。
  - live/paper 的 LLM 决策必须先落盘成 packet。
  - packet 必须有 visible_at、input_hash、prompt_hash、model、schema_version。

验收：

- 可验证一个包含 quant node、llm_judge node、risk_gate node 的 DAG。
- 缺少 packet 或 packet 元数据不完整时，DAG validation 阻塞。
- research report 能展示 DAG/另类数据状态。

## 明确不在本轮完成

- 完整横截面多因子平台。
- 完整订单簿/盘口级成交模拟。
- 自动 LLM 调用和真实新闻生成特征流水线。
- 几何/拓扑特征实现。
- 实盘真钱交易写权限。

## 完成审计标准

- 本计划文档进入 `docs/`。
- P0/P1/P2 代码和 CLI 完成。
- 新增测试覆盖 research report、promotion 接入、paper readiness 接入、StrategyDAG validation、alternative data quality。
- `uv run ruff format .` 通过。
- `uv run ruff check .` 通过。
- `uv run pytest` 通过。
- `uv run oc capability test` 通过。
