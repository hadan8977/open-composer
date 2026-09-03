# goal-first 2026-09-02 进度账本
最后更新：2026-09-03T01:30:00Z  当前 Wave：W2  状态：in_progress

## W0 创建账本
- [x] 创建本文件  commit: fa28e4a

## W1 运营闭环
- [x] dry-run 通过  产物：`uv run python scripts/run_daily_paper_cycle.py --dry-run` 打印 4 条计划命令（readiness/target-weights/paper/monitor），退出 0
- [x] cron 安装  行：`45 13 * * 1-5 cd /root/codex-test/open-composer && uv run python scripts/run_daily_paper_cycle.py # open-composer daily paper cycle`
- [x] SIP freshness cron  行：`30 22 * * 1-5 cd /root/codex-test/open-composer && export PATH=... && export UV_CACHE_DIR=... && uv run python scripts/check_sip_freshness.py --notify-on-stale >> /tmp/sip_freshness_cron.log 2>&1 # open-composer sip freshness`。**SIP 日线增量抓取未加入 cron**：`data/sip/daily/_LAYOUT.json` 记录 `batch_size=40`，当前 fetcher `BATCH_SIZE=12`，`assert_resumable_layout` 会正确拒绝续写（分片语义不同，续写=静默缺口）。按计划不绕过校验。**blocked_on_user 决策项**：是否值得用当前 batch_size 对 10 年日线做一次干净重抓（实测约 35 分钟、0.8GB，参照 SIP 迁移计划的实测数字）以换回可增量续写的布局；本轮不做。现在 freshness 是 `stale: []`（daily 2 session 落后、minute 1 session 落后，均在 `max_stale_sessions=2` 阈值内）。
- [x] `--notify-on-stale` 功能新增：`scripts/check_sip_freshness.py` 增加该 flag，落盘时经 `open_composer.notifications.dispatch_notification` 发 `system_alert`（warn）。新增 2 个测试（`tests/test_sip_freshness_check.py`：`test_notify_on_stale_dispatches_a_system_alert`、`test_without_the_flag_no_notification_is_dispatched`），用 `OPEN_COMPOSER_ROOT` 隔离，子进程验证。全部 7 个测试通过。
- [ ] Telegram 送达  **blocked_on_user**：`.env` 无 `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID`（`grep -c "^TELEGRAM" .env` = 0）。`oc notify status` 确认 `Telegram enabled: False`。这两个值只能由用户去 Telegram 创建 bot（@BotFather）获取，无法由执行者代办。`log_only` 通道正常工作（已验证，见下）。
- [x] 首次自动运行产物（真实运行，非 dry-run）：`reports/paper/daily_cycle/nasdaq_tqqq_post_drawdown_reentry_router_delayed30_offensive_paper_auto_candidate-20260903.json`，`status=ok, failed_step=None`，5 步全部 exit 0（readiness/target_weights/paper_cycle/paper_monitor/state_drift）；`reports/paper/status.json` 时间戳 2026-09-03；`reports/notifications/log.jsonl` 新增 `system_alert` "Daily paper cycle ok: 2026-09-03" 行（`log_only: delivered`）。

**发现并修复一个真实的运营 bug（不是本计划要求的范围，但直接阻塞 Q2）**：首次真实运行时 `target_weights` 步骤以 exit 2 失败，报错 `router requires at least 30 common daily sessions`。根因：`open_composer/adapters/data/alpaca.py:_request_start` 在 `start=None` 且无可用缓存时，默认回看窗口是 `now - 30 calendar days`（≈22 个交易日），而路由器要求至少 30 个*交易*日的共同样本——日历天与交易日的单位不匹配，永远差一截。`scripts/run_daily_paper_cycle.py` 调用 `target-weights` 时从不传 `--start`，所以只要走 `--refresh-data`（默认路径）就会触发。修复：在 `_step_commands` 里显式传 `--start (today - 400 calendar days)`（新增常量 `TARGET_WEIGHTS_LOOKBACK_DAYS = 400`，覆盖该策略族已知的最长 lookback 参数，日线数据便宜，代价可忽略）。修复前后各跑一次真实 cycle 验证：修复前 `target_weights exit=2`；修复后 `exit=0`，全流程 `status=ok`。新增 0 个测试（现有 `tests/test_daily_paper_cycle.py` 9 个测试通过，未依赖具体命令行参数，无需改测试断言）。

状态：done  commit: (pending — see below)

## W2 SIP 接入
- [x] `fetch_ohlcv` 新增 `source="sip_parquet"` 分支（`open_composer/adapters/data/__init__.py`），调用 `load_sip_bars(root=Path(root)/"data"/"sip")`（显式线程化 root，非硬编码 `default_sip_root()`，可测试隔离）；无 fallback（研究强证据，miss 必须报错不能静默降级）；`timeframes.py` 新增 `TIMEFRAME_SUPPORT["sip_parquet"]`（`supported=("daily",)`，`paper_ready=()`，故意不进 `capabilities/registry.yaml`）。**发现并修复一个真实分类 bug**：`open_composer/research/metadata.py:data_acquisition_tier` 按 `source_mode` 查表分类，不认识 `"sip_parquet"`，会落到默认分支 `research_cross_check`，与 loader 自己在 `frame.attrs` 里标的 `research_strict` 矛盾；已修复为识别 `{"live_fetch","sip_parquet"}`。
- [x] `load_ohlcv_for_spec`：`spec.data.source=="alpaca"` 且 `spec.data.path` 以 `data/sip/` 开头时分流到 `sip_parquet`（`strategy_spec.py` 的 `source` Literal 不含 `sip_parquet`，未改该禁改文件）。`load_daily_dataset`（`router_common.py`）**无需改动**——它唯一的数据源专属逻辑是 adjustment 三元式，对非 `alpaca` 恒为 `None`，SIP 的 `adjustment=all` 已烘焙进archive，天然兼容；已用真实 SIP 数据（QQQ+TQQQ, 2026-06~08）验证 `load_daily_dataset(data_source="sip_parquet")` 端到端可用（63 行、`acquisition_tier=research_strict`）。
- [x] 测试：`tests/test_data_adapter.py` 新增 3 个（`fetch_ohlcv` schema+provenance、非 daily timeframe 拒绝、`load_ohlcv_for_spec` 经 `data.path` 分流），用 `sample_workspace` 隔离 + 合成 parquet shard（不依赖真实 29GB 归档）；`tests/test_data_evidence_tiers.py` 新增 1 个（`sip_parquet` → `research_strict`）。全部通过。
- [x] backtest 报告 provenance=sip_parquet 路径：`reports/backtests/sip_smoke_qqq_daily-20260903T013222Z.md`（`oc backtest strategy_specs/drafts/sip_smoke_qqq_daily.yaml`，2680 根 bar=QQQ 全部 SIP 日线历史，`Mode: sip_parquet`）——**这是 W2 验收标准的真实端到端证据**：spec → `load_ohlcv_for_spec` → signal engine → backtest engine → report，全链路走通，非单元测试模拟。
- [x] 全量回归：`uv run pytest -q -n 2` 共 11 个失败，**全部且仅**来自 `tests/test_mom_breadth_qd_r1.py`（与既有基线完全一致，逐个比对文件名确认）；`oc repo check --strict` = `status=ok`；`ruff format .` / `ruff check .` 全绿（508 文件）。
- [x] `docs/data-layer-pitfalls-and-capabilities.zh.md` 第 8 条补充 SIP spec 级接入方式的说明。
状态：done  commit: (pending)

## W3 冠军路由
- [x] 铺垫：`open_composer/research/router_common.py` `RouterMetrics` 新增可选字段 `daily_returns`（默认 `()`，仅 `capture_returns=True` 时填充，避免 `route_cross_source.py` 现有 `asdict()` 报告膨胀）；`backtest_router_params`/`hybrid_router_core._backtest_hybrid_params` 新增 `capture_returns` 透传参数。零行为变更（15 处既有调用点未传新参数）。全部路由相关测试通过（`test_router_common.py` 等 9 个文件）。
- [x] SIP 重放：`scripts/evaluate_champion_route_sip.py`（新脚本，模板 `evaluate_vol02_recalibrated.py`）。冠军 spec 的 `selected_route_label` 原样解析（`hybrid_params_from_label`，`effective_lookback=252`），`spec.costs` 原样使用，**不搜索不改参数**。数据：SIP 全 11 标的 2016-01-04~2026-08-31（2680 公共交易日），扣除 252 日预热后可用窗口 2017-01-03~2026-08-28（2427 日）。**踩坑并修复**：路由器管线的 `dataset.dates` 是去掉时区的纯日期字符串，而 `rolling_origin.returns_from_ohlcv` 保留 SIP 原始带时区时间戳，两者 reindex 对不上导致全部 benchmark 行 missing；改为按路由器同款 `.dt.date.astype(str)` 口径构造 benchmark 收益序列。
- [x] 裁定脚本 + json：`reports/research/control/champion-route-sip-revalidation-2026-09.json`。门槛来自 `config/promotion/kernel-paper-tier-gates.json`（git blob `28e4196a`），`dsr_trial_count=32`（该路由的真实搜索历史 936+25 候选发生在 SIP 迁移前、无可聚类收益流留存，按计划"找不到就保守取 32"处理，已在报告 note 里写明不是"只试了 1 次"的主张）。**结果：8 门过 7，`promotion_eligible=False`**——`qqq_capture_ratio=0.506 < 1.0` 未过（qqq_upside_capture=0.499 / qqq_downside_capture=0.985，即对 QQQ 回撤几乎不防御但放弃了一半上涨）；DSR=0.5006（压线通过，高于门槛仅 0.0006）；Sharpe-excess-BIL=1.086；MaxDD=-35.6%；4/5 折为正。**选择后窗口崩溃**：2026-07-09 至今 37 个交易日，CAGR -58.6%（annualized from a short window, 读符号不读精度）、Sharpe -2.34，同期 QQQ +4.9%——spec 里记录的 `current_oos_annualized_return_pct: 246.7` 未能延续。**未做任何调参去凑过第 8 个门**。
- [x] 与 IEX 时代记录并排：对照 `pdr-router-ml-gate-eval-20260703.json` 的 `windows.full_window.baseline`（2013-2026，3342 日）——Sharpe 1.014 vs SIP 1.033、MaxDD -43.24% vs -42.55%、年化 35.72% vs 38.47%，**基础确定性路由的形态在 IEX→SIP 数据订正后基本保持**（不像 7.R/7.T 里 ML 门覆盖层在同样订正下发生的大幅背离）；三个危机窗口 Sharpe 对照也接近（q4_2018 -3.22→-3.10，covid -3.96→-1.33，2022 -0.45→-0.78，2022 差距最大）。完整表格见 `champion-route-sip-revalidation-2026-09.md`。
- [x] 负结果记录（未通过，按计划分支）：追加到 `reports/research/control/strategy-iteration-progress-2026-07-01.md`（新增 "goal-first W3" 章节）。**未触碰** `strategy_specs/active/*.yaml` 的 `lifecycle` 字段，也未改 `run_daily_paper_cycle.py` 的默认策略——这是产品层决策（是否让 paper/live 管线继续指向一个不满足晋级条件的候选），留给结论文档，不由数据订正类工作单方面决定。
- [x] 全量回归：`uv run pytest -q -n 2` 11 个失败，全部且仅来自 `test_mom_breadth_qd_r1.py`；`oc repo check --strict` = ok。
状态：done  commit: (pending)

**Q1 答案（供结论文档直接引用）**：冠军路由在干净 SIP 数据上不能直接进模拟盘验证——7/8 门通过但 `promotion_eligible=False`，且选择后 37 个交易日实盘参考数字已大幅转负。基础路由结构本身经受住了数据订正（形态稳定），问题不在数据缺陷，是这个特定路由的风险收益形态（几乎不防御下跌但放弃一半上涨）加上近期真实衰退。

## W4 日内动量
- [ ] resample.py + 测试
- [ ] 机制模板
- [ ] 嵌套前推裁定  路径：  peak RSS：  耗时：
状态：todo  commit:

## W5 产品主路径
- [x] `oc research iteration init goal_first_w5_qqq_momentum`：真实填写全部 6 个文件——外部简报 8 个来源（7 篇论文，本 session 内实际检索/抓取过，均带 `source_verified` 溯源卡 `reports/harness/source_cards/goal_first_w5_qqq_momentum.jsonl`）、假设、6 组合搜索空间（趋势回看 {100,150,200}×波动率门 {无,realized_vol≤中位数}）、决策记录。**首次校验**（`--stage pre-backtest`）暴露 10 个 blocker（campaign 合同缺失 + 4 个 markdown 仍是模板/缺锚点关键词 + hypotheses/decision-record 缺 4 个必需小节各自的关键词）；补全 markdown 内容后**收敛到唯一一个结构性 blocker**：`campaign_contract_required_for_new_iteration`。
- [x] **核心发现（Q5 主答案）**：2026-08-15 后创建的**任何**新 iteration（不只是"广度 campaign"）都被 `_campaign_requirement_blockers` 强制要求绑定一份完整的 `research-campaign-contract.json`（参考 `reports/research/campaigns/mom_independent_mechanisms_qd_r2/`，388 行：hypothesis tree、branch_quotas、candidate_blueprints、visibility_partitions、exposure_budgets、exploration_policy、qd_archive、statistical_family_policy、candidate_promotion_policy、expensive_resource_rungs），**没有单候选/无搜索场景的轻量通道**。6-file dossier 本身可在约 30-45 分钟内写对（已证明），campaign 合同的量级明显更大——未实际搭建（时间盒决策：已证明"必须要"，再搭一份不增加新信息）。
- [x] `research auto`/`evidence`/`promotion-report`/`strategy train`：**全部**在 `research_design_requires_iteration_gate` → `require_iteration_execution_gate` 处硬性要求已验证通过的 `iter_id`（`open_composer/research/factor_lab.py:74` 是 `oc strategy evidence` 链路里第一个触发点，`cli.py:_require_declared_iteration_gate` 是 `oc strategy train` 用的同一个函数）——由于本迭代卡在 campaign 合同，这条链路在 `run_factor_lab` 这一步就終止，`ValueError: research execution requires iter_id before execution`。**未改代码绕过**。
- [x] `oc harness plan`：**不需要** iteration 门（纯声明式，从 spec 字段推导风险域）。对 `sip_smoke_qqq_daily` 成功产出计划：检测到 `daily_open_execution` 风险域，需要 `execution-reality-reviewer`/`source-researcher` 两个技能，需要 `execution_policy`/`execution_reality_report`/`source_cards` 三个产物，两条阻断规则（裸市价单需理由、至少比较两种执行方式）。
- [x] `oc paper readiness sip_smoke_qqq_daily`：**同样不需要** iteration 门（独立评估路径）。`status=blocked`，完整给出缺口清单：`promotion_report`（依赖上面卡住的链路）、`harness_artifacts`（缺 execution_policy/execution_reality_report/source_cards）、`paper_validation`（0/20 天）、`matched_paper_tca`（需要≥30 条观测）、`capability_report`（这份 draft spec 本就不是 `lifecycle=active`+`paper_auto`，符合预期）。
- [ ] ML smoke：未实跑（`oc strategy train` 用同一 `_require_declared_iteration_gate`，会在同一处失败，已通过代码确认不需要重复实证）。
状态：done（诊断目标已达成，未强行搭建 campaign 合同）  commit: (pending)

**Q5 答案（供结论文档直接引用）**：产品主路径能端到端跑通到"声明式检查"（harness plan、paper readiness 都能独立运行并给出结构化缺口清单），但**任何真正的研究计算**（factor_lab 的 rank IC、promotion-report、ML 训练）都卡在同一道闸门——`iteration_id` 必须先通过校验，而校验又强制要求一份完整的 campaign 合同，没有单候选轻量路径。这是本周"必须改的产品清单"里最靠前的一条：要么给单候选场景加一条轻量迭代路径，要么接受每个新想法第一步就要写一份 388 行的 campaign 合同。

## W6 横截面时间盒
- [ ] DuckDB 三条查询  耗时/RSS：
- [ ] 移除名单抓取  数量：
- [ ] 偏差量级  CAGR 差：  Sharpe 差：
状态：todo  commit:

## W7 执行现实 + source cards
- [ ] 三笔出场单分析  路径：
- [ ] OPG 不可用时的改动清单
- [ ] 4 张 source card
状态：todo  commit:

## W8 基线
- [ ] make verify  耗时：
- [ ] 全量测试  失败数：  耗时：
状态：todo  commit:

## W9 模拟盘候选准备
- [ ] 候选：
- [ ] readiness 报告  路径：  剩余 blocker：
- [ ] 周一用户清单
状态：todo  commit:

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
