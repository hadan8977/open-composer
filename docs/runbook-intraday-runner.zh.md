# 日内模拟盘运行器使用说明

任务 T-20261006-14。代码：`open_composer/intraday_runner/`，入口 `scripts/run_intraday_runner.py`，
测试 `tests/test_intraday_runner.py`，干跑报告 `reports/paper/intraday/runner-dryrun-<日期>.md`。
范围：Alpaca Paper 的 quant2 账户，多个日内策略同时在一个账户上自动运行；只做模拟盘，不碰实盘。

## 1. 它做什么

每分钟一个“决策时刻”（K 线收盘后 5 秒）。每个策略只在自己周期的边界（1、5、15、30 分钟）调用一次插件：

1. 取当天到此刻**已收盘**的分钟线（实时用 IEX，回放用本地 SIP），聚合到策略周期；
2. 插件返回目标仓位（股数或名义金额，负数为空头）；先写信号日志（`signal_logs/paper-intraday-runner-quant2.jsonl`）；
3. 按策略做风控（见 3），算出各策略相对自己虚拟持仓的变动；
4. 同一品种的各策略变动先相抵，得到账户级净订单；净额为 0 的只在内部对冲，不发券商单；
5. 发市价单（DAY，常规时段），订单号用 `paper_intraday._client_order_id` 的写法，带账户、日期、品种、方向、决策时刻，
   同一决策时刻重复运行得到同一个订单号；
6. 成交后按各策略剩余变动比例分回（整股，最大余数法）。**分回价格**：所有参与策略取同一个券商成交均价（部分成交按每次增量的均价），
   所以各策略盈亏之和与券商账户盈亏对得上。**内部相抵的部分不按零成本记账**：相抵的股数（反向策略的全部成交，以及同向策略
   分到的相抵部分）按该策略配置的 `assumed_cost_bps`（回测假设的成本）计入 `internal_cross_cost`；净额恰好为 0、完全不发券商单的
   订单也一样（按计划价成交，另记模型成本）。这笔成本券商账户看不到，所以对账时“策略盈亏合计 − 券商权益变化”
   的差里包含它，报告会单独列出 `internal_cross_cost_usd` 和扣除它之后的差；
   **不挂券商端订单**：多策略模式只发 DAY 市价单，不用括号单、止损单或限价单；止损见下面的客户端止损；
7. 15:55 美东（半天市提前到收盘前 5 分钟）起所有不允许过夜的策略目标改为 0，每分钟重试直到平掉；
8. 收盘后对账、写每个策略一行的当日汇总；再用 SIP 历史重算当天决策，记录与实时源的差异。

## 1b. 影子模式和模拟盘模式

- **影子模式**（`run` 不带 `--allow-paper-orders`，不需要授权，不发任何订单）：接 IEX 实时行情，信号、意图、净额订单全部写日志，
  成交用模型：计划价 ± `shadow_slippage_bps`（配置项，默认 1 bp），子账户持仓、盈亏、止损、平仓、每日汇总都照常演化，
  所有检查照跑，事件写到 `<日期>-plan/`。不读券商持仓（影子账本自己对自己对账）；只读调用券商的可卖空资产信息。
  影子版本按协调者追加指令：10-09（周五）13:00 UTC 前交付，当天开始影子运行。
- **模拟盘模式**（带 `--allow-paper-orders`）：要有授权文件，首单当天起（10-12 周一）才启用；启动时先做只读的开户检查（见 6）。

## 2. 插件接口

```python
from open_composer.intraday_runner.plugins import IntradayPlugin, PluginContext, PluginDecision, Target, register_plugin

@register_plugin("my_strategy")            # 或在配置里写 "open_composer.intraday_runner.strategies.mod:Class"
class MyStrategy(IntradayPlugin):
    history_days = 14                       # 需要前几个交易日的分钟线（只含严格早于今天的）
    def decide(self, ctx: PluginContext) -> PluginDecision:
        # ctx.bars      今天已收盘的 K 线（本策略周期）：symbol, bar_close_ts, open..volume, feed
        # ctx.history   前几天的分钟线；ctx.positions / ctx.last_prices / ctx.state / ctx.day_pnl_usd
        return PluginDecision(targets={"SPY": Target(notional_usd=100_000)}, state={"side": 1})
```

- 没提到的品种保持原目标（“常驻目标”）；返回 `Target(shares=0)` 才是平仓。
- 引擎在每次调用前断言没有偷看（`assert_point_in_time`）：K 线收盘时刻不得晚于决策时刻，历史不得含当天。
- 插件抛异常只跳过这个策略这一次（事件 `plugin_error`），不影响其他策略。
- 状态 `state` 随信号事件落盘，重启后恢复。
- 示例：`noise_band_example`（SPY 噪声带，简化示例，不是研究规格）、`timed_trade`（定时买卖，测试用）。
  T-20261006-15 / -21 交规格后，在 `open_composer/intraday_runner/strategies/` 里加插件文件，配置里写点路径
  （只允许 `open_composer.` 开头的模块）。

## 3. 风控（下单前）

| 层级 | 检查 | 触发后 |
|---|---|---|
| 策略 | 名义金额上限（`max_notional_usd`）、单品种上限（`max_symbol_notional_usd`） | 只限制**增加**的部分：目标按上限收缩；价格上涨造成的超限不强平 |
| 策略 | 每天最多下单数（`max_orders_per_day`） | 只拦会增加敞口的单；平仓、减仓永远放行 |
| 策略 | 每日亏损上限（`max_daily_loss_usd`，已实现+未实现−费用） | 事件 `halt`，当天该策略平仓并停止新开仓 |
| 策略 | 卖空 | 只做 Alpaca 标明 `shortable` 且 `easy_to_borrow` 的品种；查不到按不可卖空处理 |
| 策略 | 客户端止损（`stop_loss_pct`，默认关；`stop_cooldown_minutes`，默认 30） | 每个决策时刻用最新 1 分钟收盘价对平均成本判断；触发后事件 `stop`，该品种目标强制为 0，经净额合并正常下市价单，冷却期内插件再要求也保持空仓。没有任何券商端止损单 |
| 策略 | 缺 K 线不交易 | 该决策时刻最新一根 1 分钟线（决策时刻前一分钟）缺失的品种，不开仓、不加仓、不调仓（事件 `bars.missing_latest`），不补零、不用旧价交易；平仓和止损不受影响（用最近一个收盘价作计划价） |
| 策略 | 调仓死区（`resize_band`，默认 5%） | 同方向小幅变动不下单，防止按名义金额定仓时随价格每分钟碎单 |
| 账户 | 总名义金额上限（`max_gross_notional_usd`） | 超出的增仓单被缩小或拦下；对冲和减仓不受限 |
| 账户 | 总每日亏损上限 | 事件 `halt`，全账户平仓并停止 |
| 账户 | 全局模拟盘紧急停止（`reports/paper/kill_switch.json`，读不到按开启处理） | 所有订单（包括平仓）都不发，只记 `blocked`；仓位留给人处理 |
| 账户 | 运行器停止文件 `reports/paper/intraday/runner/quant2/STOP` | 不开新仓，所有策略平仓（减仓单照发） |
| 账户 | 券商持仓与各子账户之和不一致（`drift`） | 该品种不碰，只记事件；收盘对账会列出 |
| 账户 | 同一品种被券商拒单 3 次 | 当天不再对该品种下单 |

**每个品种同一时刻只有一个方向的订单**（Alpaca 对同一品种已有反向未成交单时拒绝新单，提示 potential wash trade，模拟盘也一样；
来源：Alpaca User Protection 文档和论坛案例）：

- 先按品种把各策略的变动净额合并，每个品种每个决策时刻最多一张券商单；
- 每个决策时刻开始时，上一个决策时刻留下的未终结订单（市价单正常几秒内成交）一律先撤单，并**轮询确认撤掉**（成交了一部分的按已成交部分分回），
  然后才规划新单；撤单还没确认（`pending_cancel`）的品种本轮不下单，下一个决策时刻按常驻目标再来；
- 下单前再只读查一次该品种的未成交订单：有**不是本运行器发的**反向挂单，不撤别人的单、不下新单（事件 `order_abandoned`，原因
  `foreign_opposite_open_order`），下一个决策时刻重试；
- 测试覆盖：假券商在有反向挂单时拒单（`wash trade`），运行器先撤后下、不重复下单；撤单未确认时不下；外部反向挂单不被撤。

**翻向分两步**（一张单从净多翻到净空，Alpaca 是否接受没有核实）：净订单先限制到把现有持仓平到零，**成交确认后**才开反向仓：
下一个决策时刻按常驻目标（每分钟都重试，不等插件周期）发开仓腿。对成交时点的影响：翻向的开仓腿比平仓腿晚一个决策时刻（约 1 分钟，
对 30 分钟周期的策略也是约 1 分钟，因为重试按分钟走），期间品种处于空仓；翻向时会多付一次来回的滑点和一分钟的价格漂移，
回测若假设同价翻转会略微乐观。

## 4. 文件和断点恢复

所有状态都是追加写的事件日志：`reports/paper/intraday/runner/quant2/<日期>/events.jsonl`
（不带 `--allow-paper-orders` 的计划模式写到 `<日期>-plan/`，两者不混）。

写入顺序 = 审计顺序：`signal` → `intent` → `net_order`（先写、再下单）→ `submit_result` → `fill_sync`（含分回明细，一行为一个提交单位）。

进程被杀后重新启动（cron 每 5 分钟拉起一次，文件锁保证只有一份）：

- 从日志重放出各策略持仓、盈亏、下单计数、停止状态、插件状态；
- 只有 `net_order` 没有 `submit_result` 的订单：先按订单号问券商。券商有 → 认领，不重发；没有且在 120 秒内（或是平仓单）→ 用同一订单号重发；
  超过 120 秒的开仓/加仓单放弃（事件 `order_abandoned`），下一个决策时刻按目标重算；
- 已提交未成交的订单：每个决策时刻先同步；超过 60 秒仍未终结的撤单，部分成交按已成交部分分回，剩余由常驻目标重试；
- 同一决策时刻已写过信号的策略重用当时的决定，不再调用插件；日志末行写到一半会被忽略。

其他产物：`daily-summary.jsonl`（每天每个策略一行）、`<日期>/report.md`、`<日期>/bars-live.parquet`（运行器当时看到的分钟线）、
`<日期>/sip-recheck.json`、`<日期>/carry.json`（允许过夜策略的持仓，次日开盘作为期初）。

## 5. 数据源与调用限制

- 实时：Alpaca 免费行情只有 IEX，不是全市场 SIP；运行器显式用 `feed=iex`（不读 `ALPACA_DATA_FEED`），每个事件和日报行都带 `feed`。
  行情凭据取自 quant2 的 env 文件（变量名 `ALPACA_QUANT2_API_KEY_ID`、`ALPACA_QUANT2_API_SECRET_KEY`，
  文件由 `OC_BOOK_ACCOUNTS_ENV` 指定，默认 `/root/.config/open-composer/paper-book-accounts.env`；代码只引用变量名）。
- **调用限制**：Alpaca 每分钟 200 次，订单和行情共用。所有券商和行情调用经同一个滑动窗口限流器（配置 `api_calls_per_minute`，默认 180），
  满了就排队等，不丢调用；行情只在第一次读全天，之后每分钟只读最近 5 分钟（合并），每页按约 1 万行折算调用数。
  免费实时**推送**（WebSocket）只有 30 个品种，本运行器用 REST 轮询分钟线，不受这个 30 的限制，但品种数越多每分钟调用页数越多；
  上线前请把 `all_symbols` 数量和 `api_calls_per_minute` 对一下（运行器日志的限流器 `waited_seconds` 可看排队情况）。
- 2026-10-07 已用 quant2 的行情凭据只读验证过 `feed=iex` 和 `feed=sip` 的分钟线读取（SPY/QQQ，各 30 分钟 30 根）；盘中实时延迟没有在盘中实测。
- 历史（插件需要的前几天分钟线）：读本地 `data/sip/minute`，要求夜间归档已更新到前一个交易日；缺了插件会拿到空历史，
  示例插件返回 `no_history`。启动时预加载（约 30–60 秒）。
- 收盘后：`recheck` 命令用 SIP 历史重算：分钟线差异（缺失分钟、收盘价差、成交量比）和**决策差异**
  （用日志里的持仓和状态、SIP 的 K 线重跑同一批决策，目标股数不同的个数和方向改变数）。
  这是前向检验的一部分：IEX 成交量只占 SIP 的一小部分，稀疏品种会缺分钟。

## 6. 上线步骤（协调者）

时间线（追加指令）：**10-09（周五）13:00 UTC 前交影子版本**，当天开始影子运行；10-12（周一）起才下模拟单。

前提和依赖：

- **quant2 原来的组合计划和对账定时任务**（`run_book_v12_daily.py --plan/--submit/--reconcile` 里 quant2 的部分，按 10-06 的账户分工 quant2
  已不跑股票多空组合）由协调者在 10-09 前处理掉；本运行器不处理它们。它们若还在对 quant2 下单或对账，会与运行器的持仓/订单互相干扰。
- `reports/paper/kill_switch.json` 存在且为关闭；夜间 SIP 归档正常（插件要前一个交易日的分钟线）。

步骤：

1. 写配置 `config/intraday/runner-quant2.yaml`（参照 `runner-dryrun.yaml`）：每个策略的插件、品种、周期、名义资金、
   四个上限、`assumed_cost_bps`（回测假设的成本，写进日报对比，也是内部相抵部分的记账成本）、可选 `stop_loss_pct`。
   账户上限要小于等于授权里的上限。
2. **影子运行**（10-09 起）：`uv run python scripts/run_intraday_runner.py run --config config/intraday/runner-quant2.yaml`
   （crontab 第一条）。每天看 `<日期>-plan/report.md`、`daily-summary.jsonl`，收盘后 SIP 重算（crontab 第二条，不带 `--allow-paper-orders` 时读 `-plan`）。
3. **上线前只读检查（模拟盘首单前）**：`uv run python scripts/run_intraday_runner.py preflight --config ...`
   只读查询 quant2 是否空仓、有没有挂单（也可以带着允许过夜策略的期初持仓来比）。非空仓或有挂单时只报告（退出码 3），
   **不会自动平仓或撤单**；`run --allow-paper-orders` 在当天首次启动时做同样的检查，不通过就不交易，写 `preflight-<日期>.json` 并返回
   `preflight_failed`。
4. 写授权（只能由协调者写，引用机主 10-06 的原话；绑定配置哈希和 quant2 账户哈希，改配置要重写）：
   `uv run python scripts/run_intraday_runner.py authorize --config ... --authorized-by <谁> --basis "<机主原话>" --days 14 --confirm-paper-only`
5. 10-12（周一）起把 crontab 里的启动命令换成带 `--allow-paper-orders` 的版本；第一天人工盯：`status` 命令看持仓和停止状态，STOP 文件可随时叫停。
6. 每天收盘后看 `report.md` 和 `daily-summary.jsonl`：对账是否 OK、实际滑点对 `assumed_cost_bps`、SIP 差异、`bars.missing_latest` 占比。

## 7. crontab 草稿（UTC，不要由研究代码安装）

程序自己按纽约时间判断窗口（夏令时/冬令时都对），所以 cron 用宽窗口、重复拉起：

```cron
# 看门狗：开盘前 20 分钟起每 5 分钟尝试启动；已在运行则静默退出（文件锁），崩溃后会被拉起并从日志恢复。
# 影子阶段（10-09 起）用这一行（不下单）：
*/5 12-20 * * 1-5  cd /root/codex-test/open-composer && /root/.local/bin/uv run python scripts/run_intraday_runner.py run --config config/intraday/runner-quant2.yaml >> logs/intraday-runner.log 2>&1
# 10-12 起换成这一行（下模拟单；二选一，不要同时装）：
# */5 12-20 * * 1-5  cd /root/codex-test/open-composer && /root/.local/bin/uv run python scripts/run_intraday_runner.py run --config config/intraday/runner-quant2.yaml --allow-paper-orders >> logs/intraday-runner.log 2>&1

# 收盘后 SIP 重算：夏令时 16:35 美东 = 20:35 UTC，冬令时 21:35 UTC；太早时程序自己退出。
# 影子阶段不带 --allow-paper-orders，10-12 起带上
35 20,21 * * 1-5   cd /root/codex-test/open-composer && /root/.local/bin/uv run python scripts/run_intraday_runner.py recheck --config config/intraday/runner-quant2.yaml --source alpaca >> logs/intraday-runner.log 2>&1
```

## 8. 已知风险

- **IEX 与 SIP**：实时决策用 IEX，成交量只是 SIP 的零头，稀疏品种缺分钟，价格也可能与全市场不同；
  对分钟线收盘价敏感、对成交量敏感的策略，实时结果会与 SIP 回测不同。差异由 `recheck` 量化，前几天要重点看。
- **市价单滑点**：计划价 = 决策时刻最后一根已收盘 K 线的收盘价，成交在其后 5 秒以上；模拟盘成交价不保证贴近真实盘口。
  日报里的“实际滑点”是对计划价的偏差，不是对成交时盘口的偏差。费率（SEC/TAF）默认 0，待核对。
- **断点恢复**：以上设计由单元测试覆盖（券商接受后崩溃、接受前崩溃、过期放弃、重复决策时刻、日志末行损坏），
  但没有在真实券商上演练过；首日建议人工在 15:00 左右杀一次进程看恢复。
- **整股和碎单**：目标按整股截断；调仓死区 5% 防碎单；很小的名义金额在高价股上可能变成 0 股。
- **卖空成本**：易借股的借券费按 0 估算；模拟盘不反映真实借券可得性。
- **平仓可靠性（v1.1）**：只用常规时段市价单；平仓时间按策略配置 `flatten_et`（15:45–15:59，缺省取 `session.flatten_et`，默认 15:55），半天市取收盘前同样的分钟数；到点后每 30 秒重试（订单号带 `r1` 后缀，先撤旧单并确认），最后一次不晚于收盘前 30 秒；仍未平掉的会在 `report.md` 的对账里列出，需人工处理。
  不使用 opg/cls 竞价单（模拟盘成交不完整，见数据层陷阱 55）。
- **缺 K 线**：IEX 对不活跃品种常缺分钟，缺则不交易（不补零），活跃度低的策略会少成交；日报里要看缺失比例，别把“少交易”误当成“没信号”。
- **时钟与调度**：依赖系统时钟；决策晚于 90 秒视为过期，跳过插件调用（只做对账、平仓和重试）。

## v1.1：上一交易日官方未复权收盘价

- 开盘前 `preload` 取所有配置品种上一交易日收盘价：Alpaca 历史日线，`adjustment=raw`、`feed=sip`，走共用限流器（1 个槽位），放进 `ctx.prev_close_raw`（只含策略自己的品种）。
- 事件日志 `prev_close` 记来源和数值；日线取不到的品种退回上一交易日最后一根分钟线收盘价，并记 `prev_close_fallback` 标记事件；两者都没有则该品种缺省（插件自行处理）。每个交易日只取一次，重启后沿用日志里的值。
- 回放：`replay --prev-close-file prices.json`（`{"QQQ": 479.12}`）或 `replay_session(prev_close_raw=...)`；不给就走分钟线退回并留标记。`data/sip/daily` 是复权的，不能用。
