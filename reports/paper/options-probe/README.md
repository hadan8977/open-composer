# 期权多腿下单探测（T-20261007-05）

脚本 `scripts/options_mleg_probe.py`，测试 `tests/test_options_mleg_probe.py`（9 项，假券商，不连网）。

## 只读核查已得到的答案（2026-10-07 实测，`check`）

主模拟账户：`options_trading_level=3`、`options_approved_level=3`、`options_buying_power≈69,722`、`multiplier=4`、
状态 active、未被限制交易。Level 3 够做价差和铁鹰。SPY 7–21 天到期的合约 2,074 个，选中到期日 2026-10-21，
免费 indicative 期权行情能拿到买卖报价（认沽 735/730 的中间价约 0.665/0.545，认购 815/820 约 0.075/0.055）。
**多腿单能否被接受、拒绝原因、撤单是否正常，只有接受测试能回答，我没有运行。**

## 协调者怎么跑（开盘时段，交互会话）

```
uv run python scripts/options_mleg_probe.py check                     # 只读：账户字段、合约、报价
uv run python scripts/options_mleg_probe.py submit-test               # 只读：算出两张单的内容，写 plan_only 记录，不下单
uv run python scripts/options_mleg_probe.py submit-test --submit      # 真正下单、轮询、撤单、再轮询
```

产物在 `reports/paper/options-probe/<日期>/`：`probe.jsonl`（每一步的时间、状态、响应关键字段）和 `summary.md`。

## 它做什么

- 2 腿：卖 1 张约 5% 价外认沽，买 1 张行权价低 5 美元的认沽，同一到期日（SPY，14 天附近）；
- 4 腿铁鹰：再加卖约 5% 价外认购、买高 5 美元的认购；
- 每张单 `order_class=mleg`、DAY、每腿 1 张、`ratio_qty=1`，`position_intent` 为 sell_to_open / buy_to_open；
- 限价：**净权利金要得很高、不会成交**——有报价时取中间价净额的 3 倍（封顶为宽度的 90%，即 4.5 美元），没报价用固定的 4.00。
  净收入在 Alpaca 里用负的 `limit_price` 表示（我按文档约定写的，**第一次运行时确认**：若被拒的原因是价格符号，记录里能看到）；
- 订单号 `probe-mleg-<YYYYMMDD>-2leg` / `-4leg`；
- 下单后轮询到 new/accepted 或被拒（被拒时记录状态码和消息），再撤单，再轮询到确认已撤。

## 安全设计

- 默认只读；`--submit` 必须显式带；
- 下单前检查全局紧急停止（`reports/paper/kill_switch.json`，读不到按开启处理，复用运行器的 `default_kill_check`），开启则拒绝；
- 客户端来自 `alpaca_paper._trading_client()`（严格模拟盘工厂，地址和沙盒标记在那里校验，脚本不拼地址）；
- 凭据通过项目已有的读取方式取得，只在内存里用，不打印；账户字段只打印期权相关字段，不含账户号；
- 价格不可成交 + DAY + 1 张；任何一步异常（包括键盘中断）先撤掉本脚本挂出的所有单再退出（测试覆盖）；
- 收尾时再对本脚本发出的所有订单做一遍“未终结就撤”。

## 对账核查结论（只读，没有改代码）

主账户 ETF 子策略的日常流程：`scripts/run_daily_paper_cycle.py` → `oc paper sync-account` 写 `reports/paper/positions.json`、
`account.json` → `reconcile_paper_state`（`open_composer/paper_controls.py:380`）→ `write_state_drift_report`
（`open_composer/paper_state_drift.py`）。

1. **被撤掉的探测单**：不产生持仓。对账只读本地订单账本 `reports/paper/orders.jsonl`，探测单不在里面，所以不会出现 `open_order` 之类的记录。
   下单路径里的券商端检查（`_has_open_symbol_order`）按品种匹配；mleg 母单的 `symbol` 为空、腿是期权合约代码，不会与 ETF 代码匹配；
   订单状态集合 `KNOWN_ORDER_STATUSES` 覆盖 Alpaca 全部状态，不会因为陌生状态抛错。
   **唯一冲突**：金丝雀授权（canary）的 `_require_canary_open_orders_bound`（`alpaca_paper.py:1500`）要求账户范围内最多 1 张未终结订单，
   且对没有本地记录的未终结订单直接报错。探测单存活只有几秒到几十秒；探测期间不要提交金丝雀单。
2. **如果将来有成交的期权持仓或外来订单**，会触发的是**警告，不是停机**：
   - `reconcile_paper_state`：期权持仓没有对应本地订单 → `position_without_local_order`（warning），对账状态变 `warning`，`build_paper_alerts` 出告警；
     没有任何地方因对账 warning 阻止下单（我查了 `alpaca_paper.py`、`paper_readiness.py`）；
   - `infer_actual_state_from_positions`：多出的期权合约代码让实际状态变成 `unclassified_<合约>`，不等于预期状态 → 状态漂移 `warning`，
     日报周期发 `warn` 级通知（`run_daily_paper_cycle.py:420` 一带），周期本身仍是 ok；
   - `_target_weight_check`：期权合约的市值按账户净值折算权重，对比目标权重（目标里没有它）→ 超过 5% 容差时 `mismatches`，同样 warning；
     分母是账户净值，期权盈亏也会改变其他 ETF 的权重分母。
3. **需要排除时，要改的位置**（不在本任务内改）：
   - `paper_state_drift.py` 的 `infer_actual_state_from_positions` 和 `_target_weight_check` 里，先过滤掉 OCC 期权代码
     （正则 `^[A-Z.]{1,6}\d{6}[CP]\d{8}$`）或 `asset_class == us_option` 的持仓（同步时目前不存 `asset_class`，需要 `sync-account` 多存一列，或只用正则）；
   - `paper_controls.py:reconcile_paper_state` 的 `position_symbols` 同样过滤，或把期权子账户的订单号前缀 `probe-mleg-` 以及后续期权策略的前缀
     加入“已知外来订单”白名单；
   - 更干净的做法：期权策略放到另一个账户（quant1/quant2 之外再开）或给主账户的 ETF 对账一个“只看 ETF 代码集合”的范围参数。
   探测阶段（持仓为 0）不需要改。

## 如果要做成交测试（建议，不在本任务内）

1 张可成交的限价单（例如 1 张深度实值或临近中间价的单腿，或价差按对手价），当天在收盘前用反向单平掉：
- 目的：确认成交、持仓、平仓和 `position_intent` 的行为，模拟盘的期权成交是否按报价。
- 对 ETF 对账的影响：持仓存续期间会出现上面第 2 条的三类 warning（`position_without_local_order`、`unclassified_*` 状态漂移、权重 mismatch），
  日报周期发 warn 通知；平仓后持仓回到 0，warning 消失。建议先落实第 3 条的过滤，或选在 ETF 日报周期已跑完之后做，当天内平仓。
- 先做单腿，再做 2 腿，最后 4 腿；每步都人工确认 `probe.jsonl`。
