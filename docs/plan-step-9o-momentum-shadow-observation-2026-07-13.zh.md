# Open Composer Step 9.O：动量候选物化与 Shadow Observation

日期：2026-07-13

## 1. 目标

把 `mom_minute_r2_p1_003` 从专用研究 runner 中物化为一个冻结、可审计、
可重复生成目标仓位的 StrategySpec 产品路径，并建立完全不访问 broker、不会提交
订单的 shadow observation。该路径用于收集新的 forward OOS 与执行偏差证据，
不是 paper 授权、promotion 或 ML 训练。

## 2. UltraCode Review 结论

1. 当前 draft 仍是参数范围说明，未把 QQQ signal、TQQQ target、72-bar、2.5x
   rolling ATR filter 和 next-open 生效规则结构化为唯一 source of truth。
2. 通用 scan 会把 `data.symbol=QQQ` 解释为交易 QQQ；`oc strategy target-weights`
   又只支持现有四类 router，无法正确表达跨标的动量目标。
3. `oc run paper` 要求 active lifecycle，且 routed paper runtime 可能读取 broker
   账户，不适合本轮严格无 broker I/O 的 observation。
4. Harness 只检测到 leveraged ETF，尚未表达 09:30 与日内 next-open 的两类执行
   风险；IEX、短 OOS、gap、spread、capacity 和跨源证据仍是 paper blocker。
5. 当前候选锁箱虽过预注册门，但落后 naive momentum 与 TQQQ B&H；ML 不能用于
   追赶这个差距，必须继续 blocked。

## 3. Wave 9.O.0：计划与冻结候选

- 注册本文档；
- 为 StrategySpec 增加最小的 `momentum_signal_router` portfolio mode；
- route label 固定编码 `signal=QQQ,target=TQQQ,timeframe=30m,lookback=72,
  atr=2.5,weight=1.0`；
- draft 保持 `manual_signal`、`broker=none`，不得修改 active spec；
- spec hash 与 `mom_minute_r2_p1_003` evaluation/decision record 双向引用。

验收：spec validate、harness plan 和 capability report 能识别跨标的目标与
leveraged ETF 风险；route label 与研究参数全等。

## 4. Wave 9.O.1：Shadow Target-Weight Adapter

新增 `oc strategy shadow-observe <spec>`：

- 只接受 draft + manual_signal + broker none；
- 读取本地已物化 QQQ/TQQQ 30m research cache，不 fetch、不 fallback；
- 使用与锁箱 runner 相同的纯函数计算目标状态；
- bar close 决策，下一根 TQQQ bar open 生效；QQQ/TQQQ 时间戳不一致则 blocked；
- 每个已完成 decision bar 生成 TQQQ 0/1 target snapshot；只有目标变化才生成
  stable Signal 和 order-required intent；
- 复用 target-weight/rebalance observation schema，但 `execution_substate` 永远是
  `observation_only` 或 `blocked`；
- 写 deterministic review card，明确 `paper_order_authorization=false`、
  `broker_writes=false`；
- 禁止 import/call broker submit、account sync、paper runner。

验收：QQQ provenance、TQQQ target、next-open timing、退出、幂等、stale/misaligned
bar、无 broker artifact 与 source hash 全部由单测锁定。

## 5. Wave 9.O.2：执行现实与 Forward-OOS 合同

- 写 execution policy/reality、gap stress、leveraged ETF risk 和 shadow fill-quality
  模板/状态报告；
- 09:30 与日内执行分开：前者比较 MOO/OPG 与 LOO/OPG，后者比较 marketable
  limit 与 passive limit + timeout；本 Wave 只记录计划，不授权订单；
- slippage 压力至少 `3/6/12/20 bps`；gap 至少 `2/4/7%`；capacity 默认 1% 保守
  成交量上限；
- forward OOS 累积规则：至少 20 交易日且 30 个 intent 才可评估 shadow，参数
  冻结，不能反向调参；
- paper 前置：至少 60 交易日 QQQ/TQQQ 跨源覆盖 >=95%、状态一致 >=99%、方向
  一致 100%，以及真实/模拟 fill 报告；
- ML 前置：至少 800 个真正 OOS decision、跨源和 forward OOS 均通过、固定
  feature/label、最多 12 组合、purged+embargo、LightGBM 同时胜过线性与冻结规则。

验收：状态报告必须把未达到的时间/订单/跨源/ML 门标为 blocked，不能仅靠
workflow pass 变绿。

## 6. 边界

- 不改 `strategy_specs/active/`，不激活 lifecycle；
- 不访问或写入 Alpaca broker，不运行 paper order，不触碰 `.env`；
- 不训练 ML，不扩大参数搜索，不重开当前 lockbox；
- 不新增依赖，不重抓 data，不提交 data 大文件；
- 不 merge、不 push，除非用户另行要求；
- 每 Wave 独立提交，阴性/blocked 状态作为正常结果记录。

## 7. 每 Wave 验收

```bash
uv run ruff format . && uv run ruff check .
uv run pytest -q
uv run oc repo check --strict
make verify
```
