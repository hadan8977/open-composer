# 自动研究轮任务队列

格式和使用规则见 `docs/runbook-autonomous-round.zh.md` 第 4、9 节。自动轮按文件顺序取第一个 `ready` 且 `not_before` 已到的任务；机主和交互会话可以随时增删改。

### T-20260927-01 三条模拟盘策略合并成一个账户，是否比单独 S3 更好
- status: done
- priority: 1
- not_before:
- goal: S3 近期很强，但 2016–2023 压力期最大回撤 −48%。检验把 S1、S2 和 S3 按事先固定的比例合在一个账户里，能不能在收益代价不大的情况下明显降低回撤。如果能，它就是以后实盘试点的更好候选；如果只是"降仓"的效果，就说明分散没有额外价值。
- plan: 迭代 `h20260927_01_sleeve_combination`。用冻结的研究引擎（`scripts/run_h20260922_05_salvage.py` 的 `run_cell`，S1 无叠加、S2 按续期规格的波动率目标、S3 为 vt40 + 超卖加仓 60/10）生成三条 sleeve 的每日净收益，窗口从三者都持仓的第一天到 2026-09。预注册 3 个组合：M1 三等分；M2 S3 与 S1 各一半；M3 按过去 63 天波动率倒数加权；都在月末把 sleeve 权重调回，调仓部分每边 10 bp。每个组合配一个"只降仓"对照：k·S3 + (1−k)·SHY，k 按窗口使对照与组合的实现波动率相同。通过条件：组合过 G1 或 G1'、过 G4；在对标窗和压力期（共同起点→2023-08）夏普都比对照高 ≥0.10；压力期最大回撤比对照小。2026 留出窗照算但标为受污染，只作参考。
- done_when: 预注册通过两道检查后运行；`--stage final` 通过；假设卡、decision record、登记簿行 `dir:paper_sleeve_combination`、覆盖地图 `portfolio.combination_and_risk` 更新。
- notes:
  - 2026-09-27 19:05 UTC 交互会话派 Sonnet 5 high（Paseo 代理）执行，19:26 前完成。
  - 2026-09-27 结果（交互会话已对照 results.json 核对）：否定，0/3。三个组合都过 G1/G1'（10 和 20 bp）、压力期回撤也比对照浅，但没有一个在对标窗和压力期都比"同波动降仓的 S3"夏普高 0.10（M1 +0.086/−0.001，M2 +0.018/+0.023，M3 +0.294/−0.047）。S2 与 S3 日收益相关 0.83（压力期）。结论：想要更小回撤，直接降低 S3 仓位（其余放 SHY）效果一样。产物：`reports/research/iterations/h20260927_01_sleeve_combination/`，卡片 `H-20260927-01`，登记簿 `dir:paper_sleeve_combination`。

### T-20260927-02 S3 的调仓日运气：分批调仓能否降低回撤
- status: ready
- priority: 2
- not_before:
- goal: S3 每月最后一个交易日调仓一次。已发表研究（Newfound Research / Corey Hoffstein 的 "rebalance timing luck"，2019 起）说：同一条规则换个调仓日，结果可能差很多；分成几批、在不同日子调仓能减少这种运气成分。这不增加任何可调参数，却可能让实盘结果更稳。它影响以后实盘试点的执行方式。
- plan: 先联网读 Newfound 原文和对趋势/杠杆策略的复现，登记来源。然后预注册：(a) S3 在每月第 1–21 个交易日调仓的 21 个版本，报告年化、夏普、最大回撤的分布，看月末版本处在分布的哪个位置（这是描述，不是挑选）；(b) 4 批版本：资金分 4 份，分别在第 0、5、10、15 个交易日偏移调仓。通过条件：4 批版本在对标窗和压力期（2016-05→2023-08）的最大回撤都比月末版本小，夏普下降不超过 0.05，20 bp/边下仍过 G1 或 G1'。窗口和成本按冻结合同。续期规则冻结到 2026-11-01，结论只作为下次续期的提案。
- done_when: 迭代档案 `--stage final` 通过；在 `reports/research/control/decision-s3-live-pilot-2026-09-24.zh.md` 末尾加 5 行以内的结论；登记簿行 `dir:s3_rebalance_timing_luck_tranching`。
- notes:

### T-20260927-03 新规则下第一次月度调仓核对
- status: ready
- priority: 1
- not_before: 2026-10-02 01:00 UTC
- goal: 09-30 收盘后 S2、S3 按新规则第一次月度调仓，10-01 开盘成交。核对模拟盘和研究引擎是否一致、成交质量如何，这是以后实盘的前置证据。
- plan: 读 `reports/execution/us_etf_levered_rotation_63_top2_monthly-target-weights.json` 和 S2 的同名文件（09-30 生成的目标），用 `uv run python scripts/check_rotation_overlay_parity.py` 复算 09-30 的研究引擎决定；读三条 sleeve 的 `reports/paper/rehearsal/<name>-fills.jsonl` 里 2026-10-01 的成交，看 `slippage_vs_open_bps`、是否全部成交；读 `reports/paper/alerts.md`。
- done_when: `docs/current-view.zh.md` 顶部 5 行以内的结论（一致 / 不一致及原因、滑点、有无撤单）；不一致或有撤单时在队列加修复任务。
- notes:

### T-20260927-04 修看板里的额度百分比读数
- status: ready
- priority: 3
- not_before:
- goal: 2026-09-27 `open_composer.cockpit.data.quota` 读到 5 小时窗口 1000%、7 天窗口 100%、状态 stale，明显解析错了。修好后，看板能显示真实额度，自动轮以后也可以按真实额度决定跑不跑。
- plan: 用模块自己的函数取数据，只打印返回结构的键名和数值类型、数值，**绝不打印或写出令牌**；对照 `_parse_window` 找出单位或字段名变化（例如 0–1 比例和 0–100 百分比混用）；改解析并加测试（`tests/test_cockpit_quota.py` 已有 MockTransport 夹具）。不要改凭据读取逻辑。
- done_when: 相关测试通过；实测读数在 0–100 之间且有 `resets_at`；在自动轮日志摘要里写一句。
- notes:

### T-20260927-05 月度覆盖检查（第一次）
- status: ready
- priority: 3
- not_before: 2026-10-05 01:00 UTC
- goal: 按 `docs/plan-research-coverage-2026-09-23.zh.md` 第 4 节，每月检查覆盖地图还有哪些格子没搜过、没测过，避免重复和遗漏。
- plan: `uv run oc research directions summary`；统计 `reports/research/harvest/coverage.json` 各格子的方向数和状态；对照 `reports/research/harvest/feed-digest-2026-09-27.md` 找没人覆盖的格子；列出下个月最多 3 个搜索或测试任务写进本队列。
- done_when: `reports/research/control/coverage-check-2026-10.md` 写好；队列新增任务。
- notes:
