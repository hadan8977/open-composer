# Step 8 Go-Live 就绪：每日运营循环 + Paper 验证 + 实盘 Runbook（2026-07-06）

> 执行者注意：本文档自包含，不依赖会话上下文。所有路径相对仓库根
> `/root/codex-test/open-composer`，在当前部署分支上继续（Step 7.S 已完成；
> 若 Step 7.T 已开始，本计划与其在不同模块上工作，冲突面很小，按提交顺序正常
> rebase 即可）。先执行 Wave 8.P 修正本文档，然后按修正后的 Wave 顺序执行，
> 每个 Wave 一个独立提交，红灯即停。

## 0. 背景与产品转向（必要事实）

产品定位从「研究工作台」转向「**运营管线 + 受限研究道**」。理由：

- 已有强证据策略在 paper 上：活跃 paper_auto 候选
  `nasdaq_tqqq_post_drawdown_reentry_router_delayed30_offensive_paper_auto_candidate`
  （固定路由 PDR 路由器；同数据 14 年回测：年化 35.72%、Sharpe 1.014、
  MaxDD -43.24%、q4_2018/covid/2022 三次危机全部大幅跑赢 TQQQ）。
- 但运营循环断着：`reports/paper/status.json` 显示
  `account_snapshot_at=2026-06-03`（一个月未同步）、`alert_status=warning`
  （3 条告警）、机器上没有任何 cron/调度在跑每日循环。
- 命令面已齐备，本计划**只做编排与验收，不重建**：
  `oc run paper`（对活跃策略跑 scanner/review/Alpaca Paper 受控提交）、
  `oc paper submit / readiness / sync / sync-account / status / reconcile /
  alerts / monitor / monitor-loop / kill-switch`、`oc notify`、
  `oc data verify-research-cache`（Step 7.S 新增，manifest+sha256 校验）、
  `oc strategy target-weights`（Step 7.R 已修复活跃候选的 label 解析）。
- 当前 `oc paper readiness <strategy> --strict` 为 `ready=yes` 但
  `status=warning`，且 `execution_substate=observation_only`。因此本计划的
  paper 循环默认只做信号、target weights、review card、monitor 与通知；在
  router order authorization 补齐前，不传 `--allow-paper-orders`，不提交 broker
  paper order。

**用户已拍板的三个决策（写死进本计划，Codex 不得更改）**：
1. 实盘执行 = **人工按 review card 下单**。项目规则不变：自动写单仅到
   Alpaca Paper，实盘自动化仍在范围外。
2. Paper 验证窗口 = **20 个交易日**（验证执行链路可靠性，不验证收益；
   收益证据来自长窗口回测）。
3. 实盘首期仓位 = **50%**（路由权重 × 0.5，其余持 BIL/现金）。

## 1. 目标与 Done 定义

| # | 目标 | Done 定义 |
|---|---|---|
| G1 | 运营基线修复 | 账户/持仓快照当日新鲜；3 条 warning 告警逐条处置（修复或书面豁免）；活跃候选 `oc paper readiness` 通过且有当日 target-weights 工件 |
| G2 | 每日自动循环 | 单入口命令跑通全链路；连续 5 个交易日零人工干预成功（失败有通知）后视为稳定 |
| G3 | Paper 验证装置 | 每日自动累积验证记录，第 20 个合格交易日自动产出 `paper_validation_pass=true/false` 报告 |
| G4 | 实盘 Runbook | 一页纸日常流程 + 50% 仓位映射表 + kill 规则阈值写死 |
| G5 | 漂移监控 | 状态转换逐日对账进入每日循环；月度同数据重放审计有命令可跑 |
| G6 | 跨源重验 | 固定路由在第二数据源上重放，产出 `route_cross_source_pass` 明确 true/false 报告（实盘启动第三道门） |

## 1.1 执行顺序修正

Wave 8.5 与每日循环实现无代码依赖，却是实盘启动前更靠前的证据门。为了避免先
建设运营循环、后发现固定路由跨源不稳，本计划按以下顺序执行：

1. Wave 8.P：修正并注册本文档。
2. Wave 8.0：运营基线修复。
3. Wave 8.5：跨数据源固定路由重验。
4. Wave 8.1：每日 observation-only paper cycle。
5. Wave 8.4：漂移监控与月度 replay audit。
6. Wave 8.2：20 日 paper validation-report。
7. Wave 8.3：人工实盘 runbook。

## 1.2 Wave 8.P 计划修正与注册

1. 修正本文档中的 CLI 命令形态，尤其 `oc paper readiness <strategy>` 为位置参数，
   不是 `--strategy` option。
2. 明确 active paper candidate 当前仍是 `observation_only`，daily cycle 默认不传
   `--allow-paper-orders`。
3. 将本文档注册进 `open_composer/repo_check.py` 的 `CURRENT_DOCS` 与
   `tests/test_repo_check.py`。
4. 本 Wave 不运行 broker 写操作、不改 active spec、不生成策略或 paper order。

## 2. Wave 8.0 运营基线修复

1. 依次跑并保存工件：`oc paper sync`、`oc paper sync-account`、
   `oc paper monitor`、`oc paper status`。确认 `account_snapshot_at` 变为当日。
2. 读取 `reports/paper/alerts.md`，对现存 3 条 warning 逐条给出处置：
   能修的修（例如快照过期类告警在第 1 步后应消失）；属于历史遗留且不影响
   活跃候选的，在 `reports/paper/alert-triage-20260706.md` 中记录豁免理由。
   不允许静默忽略。
3. `oc paper readiness nasdaq_tqqq_post_drawdown_reentry_router_delayed30_offensive_paper_auto_candidate --strict`
   必须通过；不通过则修复其指出的缺口（这是本 Wave 的核心验收）。
4. 为活跃候选生成当日 target-weights 工件（`oc strategy target-weights`，
   Step 7.R 修复后应可直接工作），确认工件落盘路径并在提交信息中记录。
5. 数据前置：`oc data verify-research-cache` 通过（研究缓存不动；paper 用
   实时数据路径，此项只是习惯性校验）。

## 3. Wave 8.1 每日自动循环（paper 自动、实盘只出卡）

新增 `scripts/run_daily_paper_cycle.py`（stdlib + 项目内部模块），
串联既有命令，**不得绕过或弱化任何既有控制**（readiness 检查、kill-switch、
非 paper_auto 策略的人工确认要求全部保持）：

1. 步骤（任一步失败 → 走第 3 点的失败路径，不继续）：
   a. 交易日判断（非交易日直接记录 skip 并退出 0）。
   b. 市场数据刷新（复用活跃策略现有数据路径；不重抓研究缓存）。
   c. `oc run paper <strategy>`（活跃策略信号生成 + scanner/review 控制），
      默认不传 `--allow-paper-orders`，因此在 order authorization 补齐前只产生
      observation/manual-review 信号，不提交 broker paper order。信号必须先落日志。
   d. review card 输出到 `reports/paper/review_cards/YYYYMMDD.md`：
      当日路由状态、目标权重、**50% 实盘映射列**（权重 × 0.5，余额 BIL）、
      与前一日的差异、以及「今天实盘需要做什么」的一句话结论
      （无变化日应显式写「无操作」）。
   e. `oc paper monitor`（含 reconcile + alerts + status 刷新）。
   f. 汇总一条通知（复用 `oc notify` 既有通道）：日期、路由状态、是否有单、
      对账结果、告警数、验证进度 k/20。
2. 结构化运行日志：`reports/paper/daily_cycle/YYYYMMDD.json`
   （每步名称、开始/结束时间、退出状态、工件路径）。这是 Wave 8.2 的输入。
3. 失败路径：任何一步非零 → 写 `status=failed` 的循环日志 + 立即
   `oc notify` 告警（内容含失败步骤与日志路径）→ 退出非零。连续 2 个
   交易日失败的处置写进 runbook（人工介入 + 视情况 kill-switch）。
4. 调度：交付 `scripts/install_daily_cron.sh`（幂等；写清 crontab 行，
   工作日美东开盘前触发，注明时区换算与服务器时区），**但不执行安装**——
   安装是用户的一条命令，写在 §8 用户操作清单。
5. 单测：循环编排器的步骤成功/失败/非交易日三条路径（子进程调用打桩）。

## 4. Wave 8.2 Paper 验证装置（20 个交易日）

新增 `oc paper validation-report`（核心逻辑进
`open_composer/adapters/paper/` 或 `open_composer/research/` 旁的合适模块，
CLI 薄封装）：

1. 输入：`reports/paper/daily_cycle/*.json`、`sync.jsonl`、
   reconciliation/status 工件、信号日志。窗口起点 = 第一条合格循环日志。
2. 每个交易日判定为 pass 需同时满足：
   a. 当日循环 `status=ok`（或 skip 的非交易日不计入分母）；
   b. 三方对账一致：信号 ↔ 订单 ↔ 持仓（reconcile 无未解释差异）;
   c. 无新增 error 级告警；warning 需已在 triage 文件中有处置记录；
   d. 执行偏差在阈值内：成交价 vs 当日参考开盘价偏差 ≤ 0.5%（无单日自动 pass）。
3. 输出 `reports/paper/validation/paper-validation-progress.md/.json`：
   进度 k/20、逐日判定表、失败日原因。第 20 个合格日自动产出终版
   `paper-validation-report-<date>.{md,json}`，字段 `paper_validation_pass`。
   **中断规则**：任何一天不合格不清零，但连续 2 个失败日 ⇒ 窗口重新开始
   （链路不稳就该重验，这条写死）。
4. 与既有 `paper_ready_pass` 的关系：validation 报告是执行链路证据，
   不改变研究侧四个 pass 的语义；报告中显式写明这一点。
5. 单测：构造循环日志 fixture，验证 pass/fail/重开窗三条路径与 20 日终版触发。

## 5. Wave 8.3 实盘 Runbook + 50% 仓位映射

交付 `docs/runbook-live-manual-execution.zh.md`（一页纸导向，中文）：

1. 每日流程（≈5 分钟）：开盘前读通知/review card → 若「无操作」则结束 →
   若有变化，按 50% 映射表下实盘单（市价开盘附近）→ 在
   `reports/live/manual_journal.jsonl` 记一行（日期、动作、成交价、数量；
   新增 `oc journal live-log` 薄命令或直接文档化 JSONL 格式，二选一，选简单的）。
2. 仓位映射表：路由 11 个状态 → 目标权重 × 0.5 + 50% BIL 的对照表
   （从 review card 的实盘映射列直接抄单）。
3. Kill 规则（阈值写死在文档，触发即人工执行并启用
   `oc paper kill-switch --enable`）：
   - 每日循环连续 2 个交易日失败 → 实盘暂停新操作，仅允许降风险；
   - 实盘账户自启动起回撤超过 **-25%**（50% 仓位下约对应全仓 -50% 级别，
     已越过历史 MaxDD）→ 全部转 BIL + 强制复盘（重放审计 + 归因）后才能恢复；
   - 数据/对账异常当日 → 实盘不操作，维持现状。
4. 前置声明：实盘启动条件 = `paper_validation_pass=true` **且**
   `route_cross_source_pass=true`（Wave 8.5）。文档开头放一个
   显式检查清单（两份验证报告路径、readiness、kill-switch 状态）。
5. 该 runbook 注册进 `open_composer/repo_check.py` CURRENT_DOCS。

## 6. Wave 8.4 漂移监控

1. 状态转换对账并入每日循环（Wave 8.1 的 monitor 步骤之后）：当日引擎期望
   路由状态（来自 target-weights/信号工件）vs paper 实际持仓推断状态，不一致
   → warning 告警 + 写入循环日志。核心函数进模块并带单测。
2. 月度重放审计命令 `oc strategy router-replay-audit`（薄封装）：
   `oc data verify-research-cache` → 用 `open_composer/research/pdr_attribution.py`
   重放固定路由 → 与最近一次入库基线数字对比（同数据纪律：数字对不上先查
   manifest 哈希）→ 输出 `reports/research/control/router-replay-audit-<date>.md`。
   月度执行写进 runbook 的月检清单。
3. 验证/月报中都包含 paper（及实盘启动后的 manual_journal）与引擎的跟踪误差。

## 7. Wave 8.5 跨数据源重验（实盘启动第三道门）

动机（写给执行者的事实）：固定路由的全部回测证据来自单一研究缓存，且路由
参数本身就是在这份数据上历史搜索选出的——「同源选择偏差 + 单源依赖」是
上实盘前最大的两个证据缺口。项目已实证调整数据漂移（同一路由在 2026-05
缓存上 4334%、2026-07 重抓后 5644%），所以跨源重验不是形式主义。本 Wave
**只重放固定路由，零搜索、零参数修改、不碰任何 spec**。

1. 源选择与探测：经 `capabilities/registry.yaml` 选第二日线源，首选 Alpaca
   日线（凭据已有，走既有配置面）；备选 `market.longbridge_bars`（trial）。
   先探测路由全部符号（以研究缓存 manifest 的符号清单为准）的可得历史深度，
   确定最大重叠窗口。重叠窗口必须覆盖 q4_2018、covid_crash、calendar_2022
   三个危机窗口（预计 ≥2016 可满足）；覆盖不了则本 Wave 记 `blocked` 并停，
   不得用更短窗口出结论。
2. 物化：新增 `oc data fetch-alt-daily --source <name>`（或等价脚本），落盘
   `data/research/<source>_daily/` + manifest（symbol、行数、首末日期、
   sha256），与主研究缓存物理隔离，禁止就地覆盖主缓存。
3. 重放与同窗基线：复用 `open_composer/research/pdr_attribution.py` 的既有
   重放路径，在主缓存与第二源上各重放一次固定路由，**两边都截到同一重叠
   窗口**（同数据纪律：不得拿全窗口旧数字来比）。
4. 判定 `route_cross_source_pass`（全部满足才 true）：
   a. 危机结论不翻转：第二源上路由在三个危机窗口内仍全部跑赢同窗 TQQQ，
      方向结论不变；
   b. 重叠窗口年化收益与 MaxDD 两源差均 ≤ 5pp（绝对百分点）；
   c. 逐日路由状态序列一致率 ≥ 95%；不一致日全部列出并归因
      （数据差异 vs 规则敏感）。
5. 输出 `reports/research/control/route-cross-source-validation-<date>.{md,json}`：
   两源 manifest 哈希、重叠窗口、全窗与逐危机窗口对比表、状态不一致日清单、
   `route_cross_source_pass` 字段。gitignore 白名单纳入该 .md 与 .json。
6. 失败处置：`route_cross_source_pass=false` ⇒ 实盘启动阻塞（与 §5 前置
   声明联动），先出差异归因报告再议；**不得通过调路由参数把它「修」成
   通过**——那是用第二源做二次搜索，恰好是本门要挡的事。
7. 单测：判定函数三条路径（pass / 危机翻转 fail / 状态一致率 fail），用小型
   合成双源 fixture。

## 8. 用户操作清单（Codex 不得代做）

- 跑一次 `bash scripts/install_daily_cron.sh` 安装每日调度（Wave 8.1 交付后）。
- 实盘券商选择与开户/入金；首期资金量自定（仓位规则已定 50%）。
- `paper_validation_pass=true` 后，按 runbook 启动实盘。
- push 决策：按既定安排，7.T 与本计划完成后一并推送并设 upstream。

## 9. 边界与安全（全程有效）

- 不改策略行为、不改活跃 spec、不做 promotion；研究缓存与黄金对照不重抓。
- 不弱化任何既有控制：readiness、kill-switch、信号先落日志、双重确认语义。
- 实盘零自动化：代码中不得出现实盘下单路径或实盘 API 权限要求。
- 不触碰 `.env`/密钥；通知与 broker 凭据只经既有配置面。
- 不新增第三方依赖；cron 只交付脚本不安装。
- 每个 Wave 独立提交：8.P → 8.0 → 8.5 → 8.1 → 8.4 → 8.2 → 8.3。

## 10. 验收命令

每个 Wave 提交前：

```bash
uv run ruff format . && uv run ruff check .
uv run pytest -q
uv run oc repo check --strict
make verify
```

额外冒烟：

```bash
uv run python scripts/run_daily_paper_cycle.py --dry-run   # 8.1，打印步骤计划不执行
uv run oc paper validation-report                          # 8.2，day-1 进度报告
uv run oc strategy router-replay-audit --help              # 8.4
uv run oc paper readiness nasdaq_tqqq_post_drawdown_reentry_router_delayed30_offensive_paper_auto_candidate --strict
uv run oc data fetch-alt-daily --help                      # 8.5（脚本实现则跑脚本 --help）
```

## 11. 交付清单

- [ ] 8.0：快照刷新 + 告警 triage 文档 + readiness 通过 + 当日 target-weights 工件。
- [ ] 8.1：`run_daily_paper_cycle.py` + review card（含 50% 实盘映射列）+
      循环日志 + 失败通知 + `install_daily_cron.sh` + 单测。
- [ ] 8.2：`oc paper validation-report`（20 日窗口、连续 2 失败重开窗）+ 单测。
- [ ] 8.3：`docs/runbook-live-manual-execution.zh.md`（映射表 + kill 规则 + 启动前检查清单）。
- [ ] 8.4：状态转换对账 + `oc strategy router-replay-audit` + 单测。
- [ ] 8.5：第二源物化（manifest）+ 跨源重放报告（`route_cross_source_pass`
      verdict）+ 单测。
- [ ] 本计划与 runbook 注册进 `open_composer/repo_check.py` CURRENT_DOCS 与
      `tests/test_repo_check.py`（参照 7.R/7.S 先例）。
