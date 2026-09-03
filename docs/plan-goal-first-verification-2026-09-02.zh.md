# 目标导向的验证与改造执行计划（第一步，交 Sonnet 执行）

日期：`2026-09-02`
计划版本：`2.0`（1.0 的五天排期被用户否决：**本周内全部做完，下周要有策略和模型在模拟盘跑**）
基线提交：`5d85497` + 工作区未提交改动（本文件、`docs/capability-gap-analysis-2026-09-02.zh.md`、坑清单第八章、`scripts/fetch_watchdog.sh`、`.gitignore`）
执行者：**Sonnet（无上下文）**。结论文档由 Claude 写，执行者不写。
截止：`2026-09-06`（周日）全部 Wave 完成；`2026-09-07` 起进入第三步（策略与模型迭代），下周内有候选进入模拟盘。
前置文档：`docs/capability-gap-analysis-2026-09-02.zh.md`（差距分析；本计划是对它的再验证、重排序与最小改造）

---

## 0. 续跑协议（最先读，每次开工都读）

本计划可能跨多次会话执行。**进度账本**是唯一的状态来源：

```
reports/research/control/goal-first-2026-09-02-progress.md
```

规则：
1. **开工第一件事**：读账本。找到第一个状态不是 `done` 的 Wave；若是 `in_progress`，从第一个未勾选的步骤继续。**已勾选的步骤不重做**，但要确认其产物路径存在（不存在则视为未做）。
2. **每完成一个步骤立刻更新账本**（勾选 + 产物路径 + 关键数字），不要攒到 Wave 结束。开始一个超过 10 分钟的步骤前，先在账本写 `in_progress: <步骤> 开始于 <UTC 时间>，命令：...`。
3. **每个 Wave 结束独立 commit**，账本一起提交。commit message 以 `goal-first W<n>:` 开头，写明回答了哪个 Q。停工前必须 commit 账本。
4. 账本不存在时，用 §10 的模板创建它，这是 W0 的唯一内容。
5. 账本末尾有 **"结论输入"** 区，每个 Wave 结束把该 Wave 的裁定、数字、产物路径写进去。Claude 只读这一区和产物写结论，**不会重跑任何东西**。

---

## 1. 给执行者的前置说明

**环境**（每条 shell 命令都要）：
```bash
export PATH="$HOME/.local/bin:$PATH"
export UV_CACHE_DIR=/tmp/open-composer-uv-cache
```
**代码改动后必须跑**：`uv run ruff format . && uv run ruff check . && uv run pytest -q`；产品面改动加 `uv run oc repo check --strict`。

**机器**：6 核 / 3.8GB 内存 / 磁盘剩约 118GB。
- **禁止 `pytest -n auto`**，上限 `-n 2`。
- 后台有分钟线抓取（2016-2022，写 `data/sip-hist/`，约 2 天，`scripts/fetch_watchdog.sh` 守护，日志 `/tmp/fetch_minute_2016_2022.log`）。它常驻约 200MB。**不要启动第二个抓取进程**，不要碰 `data/sip-hist/`。
- 网盘推送任务 `sip-minute-push` / `sip-daily-push` / `sip-hist-minute-push` 已注册（`gdrive task list`），**不要删除**。
- 内存分级：**轻**（<300MB，可并行）/ **重**（可达 1GB，必须单独跑，开跑前 `free -m` 可用 ≥1200MB）。见 §8 并行表。

**既有失败**：`tests/test_mom_breadth_qd_r1.py` 11 个失败，其余为零。回归标准：仍为 11 且全部来自该文件。

**禁改文件**（封存 campaign 的预注册锁 SHA-256 绑定）：
```
capabilities/registry.yaml  open_composer/market_calendar.py  open_composer/models/strategy_spec.py
open_composer/research/campaign_statistics.py  open_composer/research/iteration_dossier.py
open_composer/research/quality_diversity.py  open_composer/storage.py  pyproject.toml  uv.lock
open_composer/research/mom_breadth_qd_r1.py  tests/test_mom_breadth_qd_r1.py
scripts/prepare_mom_breadth_qd_r1.py  strategy_specs/drafts/us_breadth_*.yaml
```
推论：新依赖只能 `uv run --with duckdb ...` 临时用；`spec.data.source` 的取值集合不能改，SIP 通过 `spec.data.path` 与 `frame.attrs` 溯源接入（W2）。

**用户 2026-09-02 决定**：模拟盘账号事项（滞留 TQQQ、kill switch、测试单）**等有策略要接入时再处理**，本计划不做、不催。

---

## 2. 目标与判定

- 用户目标：尽快得到有效策略与模型，尽快接入实盘获取收益。
- 第一里程碑：一个策略走完 20 个交易日模拟盘验证，进入人工实盘 50% 仓位（`docs/runbook-live-manual-execution.zh.md`）。
- 本周的 Done：§9 的六个问题全部有产物支撑的答案；ETF 策略族的研究与产品路径在 SIP 数据上端到端可用；至少一个候选的证据链准备到 `oc paper readiness` 可评估。

**排序原则**：只用 ETF 的策略族没有幸存者偏差问题（宇宙固定显式），现有冠军路由和 SPY/QQQ 日内动量都属于这一族，所以最快路径是先在干净 SIP 数据上重建 ETF 策略族证据，横截面只做可行性判断。外部证据：《What survives honest evaluation?》（arXiv 2608.27734）在 453 只美股 + 39 只 ETF 上拒绝了全部 LLM 发现的策略，被动基准被认证，预注册假设享有更低证据门槛。第一个上实盘的更可能是简单、有文献支撑、预注册的机制。

---

## 3. Wave 总览与截止

| Wave | 内容 | 回答 | 内存 | 截止 |
|---|---|---|---|---|
| W0 | 创建账本 | — | 轻 | 09-02 |
| W1 | 运营闭环跑起来 | Q2 | 轻 | 09-03 |
| W2 | SIP 接入研究路径与产品路径 | 前置 | 轻 | 09-03 |
| W3 | 冠军路由 SIP 重建 + 门槛裁定 + 晋级证据链 | Q1 | 轻 | 09-04 |
| W4 | 分钟线重采样器 + 单 ETF 日内动量机制 + 嵌套前推 | Q3 | 重 | 09-05 |
| W5 | 产品主路径端到端 + ML 路径 smoke | Q5 | 轻 | 09-04 |
| W6 | 横截面可行性时间盒（DuckDB + 幸存者偏差量级） | Q4 | 重 | 09-05 |
| W7 | 执行现实只读分析 + 4 张 source card | Q6 | 轻 | 09-05 |
| W8 | 基线健康（`make verify`、全量测试） | — | 重 | 夜间 |
| W9 | 下周模拟盘候选准备 | — | 轻 | 09-06 |

---

## 4. Wave 详细定义

### W0 创建账本（10 分钟）
按 §10 模板创建 `reports/research/control/goal-first-2026-09-02-progress.md`，commit `goal-first W0: progress ledger`。

### W1 运营闭环跑起来（半天，轻）
1. `uv run python scripts/run_daily_paper_cycle.py --dry-run` 确认可运行；然后 `bash scripts/install_daily_cron.sh`（13:45 UTC 工作日）。
2. 追加 cron（同一 crontab，带标记注释 `# open-composer sip refresh`）：工作日 22:30 UTC 执行 `cd <repo> && uv run python scripts/fetch_sip_universe.py --kind daily --start-year 2026 --end-year 2026 --out data/sip && uv run python scripts/check_sip_freshness.py`；freshness 非零退出时调用 `uv run oc notify test`（或通知模块的 `system_alert` 入口）发告警。**注意**：此 cron 与后台分钟抓取共用 Alpaca 配额，先确认 `assert_resumable_layout` 对 daily 目录放行（daily 的 `_LAYOUT.json` 是 batch_size=40，若被拒，改为只跑 `check_sip_freshness.py` 并把增量抓取写成"待用户决定"，不要绕过校验）。
3. Telegram：`uv run oc notify status` 看配置；缺 `config/notifications.yaml` 就按 `open_composer/notifications/__init__.py` 的 `DEFAULT_POLICIES` 写一份；`uv run oc notify test`。**Done 的硬条件是手机收到**；收不到就把缺的环境变量名（不含值）写进账本，标 `blocked_on_user`。
4. 账本记录：cron 行、首次自动运行的产物路径（`reports/paper/validation/`、`reports/paper/status.json` 时间戳）。

**Done**：cron 已装且首次自动运行留下当日产物；Telegram 送达或明确 blocked_on_user。

### W2 SIP 接入研究路径与产品路径（半天到一天，轻）
1. `open_composer/research/router_common.load_daily_dataset` 增加 `data_source="sip_parquet"` 分支，调用 `open_composer/adapters/data/sip_parquet.py` 的加载函数，保留 `frame.attrs`（`data_source_mode="sip_parquet"`、`data_source_adjustment="all"`）。测试：同一标的同一窗口，返回 schema 与 `alpaca` 分支一致。
2. `open_composer/adapters/data/__init__.load_ohlcv_for_spec`：当 `spec.data.source == "alpaca"` 且 `spec.data.path` 以 `data/sip/` 开头时，走 SIP parquet 加载并标注同样的 attrs。这让 `oc strategy evidence / promotion-report / train / paper readiness` 都能在 SIP 上跑，且不改 `strategy_spec.py`。测试：一个 `path: data/sip/daily` 的 spec 能加载并带正确 attrs；`path` 不存在时错误清晰。
3. 在 `docs/data-layer-pitfalls-and-capabilities.zh.md` 第 8 条补一句：spec 级 SIP 通过 `data.path` 接入。

**Done**：两条路径各有测试；`uv run oc strategy backtest <某个 QQQ 日线 spec，path 指向 data/sip/daily>` 能产出报告且报告里 provenance 写着 sip_parquet。

### W3 冠军路由 SIP 重建 + 门槛裁定 + 晋级证据链（一天，轻）
冠军：`strategy_specs/active/nasdaq_tqqq_post_drawdown_reentry_router_delayed30_offensive_paper_auto_candidate.yaml`。历史证据建立在含 20 处虚假跳变的 IEX 数据上（`docs/finding-iex-cache-price-adjustment-defect-2026-09-01.zh.md` §6.1）。
1. 用 spec 里冻结的参数，在 `sip_parquet` 上重放全窗口（2016-01-04 至今）。入口以 `oc strategy hybrid-adaptive-router --data-source sip_parquet ...` 和 `oc strategy router-gate-eval` / `router-attribution` 的输入格式为准；**不搜索、不改参数**。
2. 写 `scripts/evaluate_champion_route_sip.py`（模板 `scripts/evaluate_vol02_recalibrated.py`，≤150 行）：路由日收益流 → `open_composer/research/kernel/mechanism_eval.evaluate_candidate`，门槛来自 `config/promotion/kernel-paper-tier-gates.json`；`dsr_trial_count` 用该族历史有效 N（在 `reports/research/control/` 找 7.R/7.T 记录，找不到取 32 并注明）。输出全窗口、三个危机窗口（q4_2018 / covid / 2022）、选择后窗口（2026-07-09 至今，用 `recent_window_diagnostic`）。
3. 与 IEX 时代数值并排（`reports/research/control/pdr-router-ml-gate-eval-20260703.json` 的固定路由数值）。写 `reports/research/control/champion-route-sip-revalidation-2026-09.md` + 同名 json。
4. **若 `promotion_eligible=true`**：重建晋级证据链——`oc strategy promotion-report`、`oc harness plan/verify`、新增一张 source card 记录复权口径检查（`adjustment=all`，提供者 SIP），`paper-safety-review` 更新；目标是 `oc paper readiness <冠军> --strict` 只剩用户决策类 blocker（授权、kill switch、账户）。
5. **若不通过**：把负结果追加到 `reports/research/control/strategy-iteration-progress-2026-07-01.md` 的迭代日志（新章节），冠军标记为封存；**不得调参补救**。

**Done**：裁定 json 存在且 `gates_provenance` 指向 git 已提交合同；账本"结论输入"写明通过/未通过与逐门结果。

### W4 分钟线重采样器 + 单 ETF 日内动量（一天半，重，单独跑）
1. `open_composer/research/kernel/resample.py`（≤150 行）：只保留 RTH（09:30-16:00 ET，用 `market_calendar`）、VWAP 成交量加权、以 09:30 为锚的 5m/30m/1h、覆盖率下限 80%（不足标记不可用）、半日市、**禁止**分钟合成日线。测试用 QQQ 一周分钟线：bar 数、盘前盘后剔除、VWAP 与手算一致、半日市最后一根。
2. `open_composer/research/kernel/mechanisms/intraday_momentum_etf.py`（≤120 行，P1b 的 `Mechanism` 接口）：按 Zarattini/Aziz/Barbon 规则（噪声区间 = 过去 N 日同时刻平均绝对波动 × 系数；突破上/下轨顺势；收盘前平仓；可选跟踪止损），参数空间显式有界：系数 {0.5,1.0,1.5} × N {10,14,20} × 止损 {有,无} = 18 组。
3. `scripts/search_intraday_momentum_etf.py`：SPY 与 QQQ，2023-2026 分钟线，**按年分块读取、先重采样到 5m**，`run_nested_expression`同级的 `run_nested_walk_forward` 逐折重选；成本 2 bps + 1 bps 假设价差（报告里标为假设）；所有组合进 `effective_independent_trials`，DSR 按聚类数收费；门槛来自同一份合同。记录峰值 RSS 与耗时（`/usr/bin/time -v`）。
4. 产物：`reports/research/search/intraday-momentum-etf-2026-09.json` + md。

**Done**：裁定 json（`promotion_eligible` 或逐门结果）；RSS <1GB 的实测记录；账本"结论输入"写明有信号/无信号。

### W5 产品主路径端到端 + ML 路径 smoke（一天，轻，可与 W3 并行）
1. `uv run oc research iteration init goal_first_w5_qqq_momentum`；填齐外部简报（≥8 来源、≥3 论文，来源用本文件 §11 与差距分析 §9，逐条写 `core_claim / project_applicability / reflection`）、假设、搜索空间、候选清单（≤12 组合）、预注册锁；`uv run oc research iteration validate goal_first_w5_qqq_momentum --stage pre-backtest` 必须 `ok`。
2. `uv run oc research auto "QQQ daily trend continuation with volatility filter" --universe QQQ --timeframe daily --data-source sip_parquet --iteration-id goal_first_w5_qqq_momentum --max-factors 5 --no-llm`。
3. 对产出 spec：`oc strategy evidence` → `oc strategy promotion-report` → `oc harness plan` → `oc paper readiness <name>`。**不改代码绕过 blocker**；每个 blocker 的名字、触发条件、需要的手工产物记进账本。
4. ML smoke：给该 spec 加 `model: {kind: lightgbm_classifier, label: forward_direction, horizon_bars: 5, ...}`（字段以 `MLModelConfig` 为准），`oc strategy train` 与 `oc strategy backtest-walk-forward` 在 SIP 日线上跑通（目的只是证明模型路径在真实数据上可用，不是找 alpha；结果如实记录）。
5. 记录每步耗时。

**Done**：不改代码能走到 promotion-report；readiness blocker 列表完整；ML 两条命令在真实数据上产出报告。

### W6 横截面可行性时间盒（一天，重，单独跑；到点即停）
1. `uv run --with duckdb python -`：`SET memory_limit='800MB'; SET temp_directory='/tmp/duck';` 视图 `read_parquet('data/sip/daily/*/*.parquet')`。三条查询记录耗时与峰值 RSS：(a) 全市场某日横截面；(b) 单标的 10 年；(c) 每月末按过去 252-21 日收益排名取前十分位的 12-1 动量月度组合收益 2016-2026，等权，成本 20 bps。
2. 幸存者偏差量级：取 Wikipedia "List of S&P 500 companies" 变动表（或其衍生 GitHub 数据集）2016 年以来被移除的 ticker；写 `scripts/fetch_symbol_list.py`（≤60 行，复用 `fetch_sip_universe._fetch_batch`），抓到 `data/sip-delisted/daily/`（加入 `.gitignore`，**不写进 `data/sip/`**）。比较宇宙 A（当前 ACTIVE 里 ADV 前 500）与宇宙 B（A ∪ 移除名单按在世期间参与）的 12-1 动量 CAGR / Sharpe / MaxDD。
3. 产物：`reports/research/data-quality/cross-sectional-feasibility-2026-09.md`。

**判定规则**（先写下）：CAGR 差 >2pp/年或 Sharpe 差 >0.2 → 横截面必须等完整底座；否则大盘横截面可用"ACTIVE + 移除名单"廉价修复先行。三条查询任一 >60s 或 RSS >1GB → 本机不做横截面，写明需要的机器规格。
**Done**：报告存在，两条判定各有结论。超过一天未完成 → 记录已完成部分，标 `timeboxed_stop`，不延期。

### W7 执行现实只读分析 + 4 张 source card（半天，轻）
1. 读 `reports/paper/sync.jsonl` 里 2026-06-01 / 06-03 / 07-10 三笔取消/过期出场单：限价 vs 当日开盘价，判断"没到价"还是"被拒"。**不下任何单**（用户决定：账号事项等策略要接入时再处理）。
2. 读 `paper_authorization.py` 的 canary order style 与 `execution_policy.py` 的 TIF 映射，列出若 OPG 不可用时要改的字段与默认值。
3. source cards（`reports/harness/source_cards/goal_first_w7.jsonl`，字段按 `open_composer/models/source_card.py`）：Zarattini/Aziz/Barbon（SSRN 4824172）、Maróy（SSRN 5095349）、What survives honest evaluation（arXiv 2608.27734）、When Alpha Disappears（arXiv 2605.23959）。每张写 `impact_on_spec`。

**Done**：分析 md 在 `reports/execution/`；4 张卡 `source_verified`。

### W8 基线健康（夜间跑，重）
`make verify` 与 `uv run pytest -q --runslow -n 2` 各一次，`free -m` 可用 ≥1500MB 时再跑。记录耗时、失败数（必须 11 且同一文件）。**Done**：账本有两组数字。

### W9 下周模拟盘候选准备（半天，轻）
按 W3/W4 结果选候选：W3 通过 → 冠军；否则 W4 有信号 → 日内动量（需写 spec，`portfolio.mode` 与执行路径以 `adaptive_intraday_router` 现有 paper 路径为准）；两者皆否 → 写明没有候选，下周第三步从机制补充开始。
对选中的候选：spec 在 `strategy_specs/drafts/`（不动 lifecycle），证据链齐到 `oc paper readiness <name>` 输出只剩用户决策类 blocker。在账本"结论输入"列出**周一需要用户做的事**（清单形式：审批 lifecycle、kill switch、TQQQ 处置、`--allow-paper-orders`）。

**Done**：readiness 报告存在且 blocker 全是用户决策类；账本有周一清单。

---

## 5. 执行顺序

```
W0 → W1 ──┐
W2 ───────┼→ W3 ──┐
          └→ W5 ──┼→ W9 → （Claude 写结论）
W4（单独，重）──┤
W6（单独，重）──┤
W7 ─────────────┘
W8 每晚
```
W1 与 W2 可同时做；W3 与 W5 可同时做（都轻）；W4、W6、W8 三者**互斥**且不与其他重负载同时。

---

## 6. 取舍：本周不做

时序基础模型 / 合成数据 / RL / 多代理交易员；Nautilus parity；代码去重与一次性模块归档；完整横截面底座（退市全量、复权因子表、PIT 成分股）；CPCV、Optuna、SHAP；向量 RAG；Longbridge 跨源深度；模拟盘下单测试。全部记入第三步候选。

---

## 7. 禁止事项

1. 不用 `pytest -n auto`；不修 11 个既有失败；不碰 `mom_breadth_*`。
2. 不改 §1 禁改文件。
3. **不为让 W3/W4 通过而调参或改门槛**；门槛只来自 `config/promotion/kernel-paper-tier-gates.json`。
4. 不混用 SIP 与 IEX；不把 `data/sip-hist/`、`data/sip-delisted/` 合并进 `data/sip/`。
5. 不启动第二个抓取；不删网盘推送任务。
6. 不提交任何模拟盘/券商订单；不改 `.env`；产物里不写密钥。
7. 每个 Wave 独立 commit；停工前 commit 账本。
8. 不写结论文档（那是 Claude 的），只填账本"结论输入"。

---

## 8. 内存与并行表

| 任务 | 峰值估计 | 可与谁并行 |
|---|---|---|
| 后台分钟抓取 | 200MB 常驻 | 所有 |
| W1/W2/W3/W5/W7/W9 | <300MB | 彼此可并行 |
| W4 分钟线（按年分块 + 先重采样） | ≤1GB | 无 |
| W6 DuckDB（memory_limit 800MB） | ≤1GB | 无 |
| W8 全量测试 `-n 2` | ~1.5GB | 无，夜间 |

---

## 9. 六个问题

| # | 问题 | Wave |
|---|---|---|
| Q1 | 冠军路由在干净 SIP 上还活着吗？能否直接进模拟盘验证？ | W3 |
| Q2 | 运营闭环能否一天内真正跑起来，缺什么？ | W1 |
| Q3 | 分钟线单 ETF 日内动量在本项目、本机上可行吗？成本后有信号吗？ | W4 |
| Q4 | 横截面研究在本机可行吗？幸存者偏差在大盘宇宙上多大？ | W6 |
| Q5 | 产品主路径在真实数据上能端到端跑通吗？卡在哪？ML 路径可用吗？ | W5 |
| Q6 | 实盘执行假设成立吗？ | W7（只读部分） |

---

## 10. 账本模板

```markdown
# goal-first 2026-09-02 进度账本
最后更新：<UTC>  当前 Wave：W<n>  状态：todo | in_progress | done | blocked_on_user | timeboxed_stop

## W0 创建账本
- [ ] 创建本文件  commit: <hash>

## W1 运营闭环
- [ ] dry-run 通过  产物：
- [ ] cron 安装  行：
- [ ] SIP 增量 + freshness cron  行：
- [ ] Telegram 送达  时间：
- [ ] 首次自动运行产物  路径：
状态：  commit:

## W2 SIP 接入
- [ ] router_common sip_parquet 分支 + 测试
- [ ] load_ohlcv_for_spec data.path 分支 + 测试
- [ ] backtest 报告 provenance=sip_parquet  路径：
状态：  commit:

## W3 冠军路由
- [ ] SIP 重放  路径：
- [ ] 裁定脚本 + json  路径：  promotion_eligible=
- [ ] 与 IEX 并排表  路径：
- [ ] 晋级证据链（若通过）/ 负结果记录（若未通过）  路径：
状态：  commit:

## W4 日内动量
- [ ] resample.py + 测试
- [ ] 机制模板
- [ ] 嵌套前推裁定  路径：  peak RSS：  耗时：
状态：  commit:

## W5 产品主路径
- [ ] dossier validate ok  iteration:
- [ ] research auto 完成  run_dir:
- [ ] evidence / promotion / harness / readiness  blocker 列表：
- [ ] ML smoke  报告：
状态：  commit:

## W6 横截面时间盒
- [ ] DuckDB 三条查询  耗时/RSS：
- [ ] 移除名单抓取  数量：
- [ ] 偏差量级  CAGR 差：  Sharpe 差：
状态：  commit:

## W7 执行现实 + source cards
- [ ] 三笔出场单分析  路径：
- [ ] OPG 不可用时的改动清单
- [ ] 4 张 source card
状态：  commit:

## W8 基线
- [ ] make verify  耗时：
- [ ] 全量测试  失败数：  耗时：
状态：  commit:

## W9 模拟盘候选准备
- [ ] 候选：
- [ ] readiness 报告  路径：  剩余 blocker：
- [ ] 周一用户清单
状态：  commit:

## 结论输入（Claude 只读这里 + 产物）
- Q1：
- Q2：
- Q3：
- Q4：
- Q5：
- Q6：
- 推荐候选与理由：
- 周一用户清单：
- 本周未完成项与原因：
```

---

## 11. 来源（本计划新增，其余见差距分析 §9）

- What survives honest evaluation? Leakage-safe, search-aware assessment of LLM-driven trading strategy discovery：https://arxiv.org/abs/2608.27734
- When Alpha Disappears: A One-Switch Benchmark for Decision-Time Leakage in Financial Backtests：https://arxiv.org/abs/2605.23959
- Beat the Market: An Effective Intraday Momentum Strategy for S&P500 ETF (SPY)：https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4824172
- Improvements to Intraday Momentum Strategies Using Parameter Optimization and Different Exit Strategies（Maróy 2025）：https://papers.ssrn.com/sol3/papers.cfm?abstract_id=5095349
- Moreira, Muir. Volatility-Managed Portfolios. Journal of Finance 2017.

---

## 12. 后台任务状态（2026-09-02 18:00 UTC 实测）

- `data/sip/minute/` 2023-2026 完成（1,279,495,748 行，13,405 只）。
- 2016-2022 分钟线抓取运行中，写 `data/sip-hist/minute/`（独立目录：宇宙 13,416→13,414 使布局校验正确拒绝续写旧目录）。实测约 20 秒/分片、每年 1,118 分片，约 2 天，约 70GB。看门狗进程匹配已锚定 `python scripts/fetch_sip_universe.py`。
- 网盘：`datasets/sip/minute`、`datasets/sip/daily`、`datasets/sip-hist/minute` 由三个 push 任务同步，首次运行 18:00 UTC 已开始传输。本地与网盘上 `sip-hist` 都必须与 `sip` 分开存。
- 已知限制：抓取宇宙仍是 ACTIVE-only；加载器只读 `data/sip/`，接入 `data/sip-hist/` 属第三步。
