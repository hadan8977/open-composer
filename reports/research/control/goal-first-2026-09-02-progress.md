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
- [ ] SIP 重放  路径：
- [ ] 裁定脚本 + json  路径：  promotion_eligible=
- [ ] 与 IEX 并排表  路径：
- [ ] 晋级证据链（若通过）/ 负结果记录（若未通过）  路径：
状态：todo  commit:

## W4 日内动量
- [ ] resample.py + 测试
- [ ] 机制模板
- [ ] 嵌套前推裁定  路径：  peak RSS：  耗时：
状态：todo  commit:

## W5 产品主路径
- [ ] dossier validate ok  iteration:
- [ ] research auto 完成  run_dir:
- [ ] evidence / promotion / harness / readiness  blocker 列表：
- [ ] ML smoke  报告：
状态：todo  commit:

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
