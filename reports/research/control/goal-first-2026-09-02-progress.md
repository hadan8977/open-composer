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
- [x] `open_composer/research/kernel/resample.py`：RTH-only、成交量加权 VWAP、以 09:30 为锚（用现有 `market_calendar.expected_us_equity_rth_bar_starts`/`validate_us_equity_bar_grid`，未重造覆盖率校验）、半日市正确截断、覆盖率下限（默认 80%，低于则整桶丢弃不填补）、拒绝 daily 目标频率。10 个测试（`tests/test_kernel_resample.py`）覆盖盘前盘后剔除、VWAP 与算术平均对照、半日市、覆盖率丢弃、DST（11 月标准时 vs 8 月夏令时）。全部通过，且用真实 QQQ 分钟数据人工核对过 VWAP 精确匹配。
- [x] 机制模板：`open_composer/research/kernel/mechanisms/intraday_momentum_etf.py`（Zarattini/Aziz/Barbon 波动率缩放噪声带突破，Maróy 出场规则警示已体现为"每个参数向量都记为同一机制族"）。18 组合（噪声系数{0.5,1,1.5}×回看{10,14,20}×止损{开,关}）。6 个测试覆盖预热期排除、无交易日记为 0（不是省略——省略会压缩年化的天数分母）、因果性（未来数据不泄露到更早的判定）、止损优于持有到收盘。
- [x] 嵌套前推裁定：`scripts/search_intraday_momentum_etf.py`。**过程中独立发现并修复 3 个问题**（详见 `reports/research/control/goal-first-w4-intraday-momentum-2026-09.md`）：(1) 与 W3 完全同类的时区/日期索引不匹配 bug 独立复现一次——机制自己的按日收益索引与 benchmark 的日线索引表示法不一致；**没有原地再修一次，而是抽成共享函数** `open_composer/research/kernel/benchmark_returns.py::daily_returns_on_naive_dates`，W3 脚本同步重构复用（重跑 W3 脚本验证：产物 JSON 逐字节 diff 为空，行为零变化）；(2) 日线与分钟线两个 SIP 归档刷新不同步（分钟已到 2026-09-01，日线还在 2026-08-31），在 benchmark 覆盖边界之外的信号日期需要裁掉，加了"裁到 benchmark 实际覆盖范围"的通用处理。
- [x] **实测**：SPY+QQQ 各 3.5 年 5 分钟线（每标的约 71,160 根 bar，源自全市场分钟归档逐年加载+立即重采样+丢弃原始数据），**峰值 RSS 581MB**（预算 1GB 以内）；受后台 2016-2022 分钟抓取的磁盘 I/O 争用影响，单次全量运行约 15 分钟（计算本身很快，主要耗在磁盘竞争）。
- [x] **结果：两个标的均为干净负结果**。18 组合聚成有效 N=3（breadth_ratio=0.167，确认大部分组合是同一机制的相关变体）。QQQ 最优组合 Sharpe-excess-BIL=-0.466，DSR=0.083，8 门过 3；SPY 最优 Sharpe-excess-BIL=-0.914，DSR=0.064，8 门过 3。36 个候选（18×2 标的）**0 个 promotion_eligible**。两者的 QQQ/TQQQ 上行捕获都接近 0（0.001-0.012），符合"低频触发、大部分时间打平、偶尔白付一次成本"的形态，不是真正捕获了日内延续。**未做任何调参**。
- [x] 全量回归：新增 19 个测试全部通过（resample 10 + mechanism 6 + benchmark_returns 3）；`uv run pytest -q -n 2` 仍然 11 个失败全部且仅来自 `test_mom_breadth_qd_r1.py`；`oc repo check --strict` = ok。
状态：done  commit: (pending)

**Q3 答案（供结论文档直接引用）**：分钟线单 ETF 日内动量在本机**计算上完全可行**（581MB，远低于 1GB 预算，~15 分钟单次全量评估）。**成本后无信号**——SPY 与 QQQ 的最优组合 Sharpe-excess-BIL 均为负，DSR 远低于门槛，8 门只过 3，0 个候选可晋级，且效应量不是"差一点"（Sharpe 明显为负）。这不代表日内动量整体不可行，只说明这个具体简化规则、这两个标的、这 3.5 年窗口没有找到信号；文献本身（What survives honest evaluation）就预期有效 alpha 极度稀疏，这不是放松门槛的理由。

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
- [x] 出场单分析（实为 4 笔，不是计划估计的 3 笔——补上了 2026-06-01 SOXL 买单）：`reports/research/control/goal-first-w7-execution-reality-2026-09.md`。全账本 `oc-` 前缀订单：OPG 限价单 4 笔 4 笔未成交，day 市价单 6 笔 6 笔成交，无中间态。逐笔核对开盘价与限价关系后发现**4 笔里有 2 笔的价格关系本该允许成交**（SOXL 买单限价 224.63 vs 实际开盘 217.26；TQQQ 卖单限价 87.05 vs 实际开盘 87.48），不能单纯用"没到价"解释。`accepted_at` 字段全账本（含全部成交单）恒为 null，是采集缺口不是信号，已在文档里明确排除误读。**未下任何测试单**（用户 2026-09-02 决定：等策略要接入时再处理）。
- [x] OPG 不可用时的改动清单：`paper_authorization.py` 的 `CANARY_ALLOWED_ORDER_STYLES = {"opg_limit","loo_limit"}` 与任何解析出 `opg` TIF 的 `execution_policy.order_style` 都需要非 OPG 默认——`loo_limit` 单独用，或 `day_market` 配 `naked_market_justification`（`StrategySpec.execution_policy` 字段，`strategy_spec.py` 校验器已支持）；账本里唯一有真实成交证据的就是 day 市价单。
- [x] 4 张 source card：`reports/harness/source_cards/goal_first_w7.jsonl`（Zarattini/Aziz/Barbon、Maróy、What survives honest evaluation、When Alpha Disappears），全部 `source_verified`，各带 `impact_on_spec`。
状态：done  commit: (pending)

**Q6 答案（供结论文档直接引用）**：实盘执行假设**不能确认也不能排除**——4 笔 OPG 限价单历史 0 成交，其中 2 笔按价格本该成交却没成交，与 6 笔 day 市价单 100% 成交形成对比，但 4 个数据点不足以下定论，账本里也没有能区分"被拒绝"与"进了竞价没成交"的字段。需要一笔真实测试单才能有确定答案，按用户决定推迟到有策略要接入时。产品层面已有现成的非 OPG 退路（`loo_limit`/`day_market`+理由字段），一旦确认 OPG 不可用可以直接切换。

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
