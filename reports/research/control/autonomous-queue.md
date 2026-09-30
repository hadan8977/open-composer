# 自动研究轮任务队列

格式和使用规则见 `docs/runbook-autonomous-round.zh.md` 第 4、9 节。自动轮按文件顺序取 `ready` 且 `not_before` 已到的任务，最多两个互不依赖的并行做；`running` 且注明"交互会话"的不要碰。机主和交互会话可以随时增删改。

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
- status: done
- priority: 2
- not_before:
- goal: S3 每月最后一个交易日调仓一次。已发表研究（Newfound Research / Corey Hoffstein 的 "rebalance timing luck"，2019 起）说：同一条规则换个调仓日，结果可能差很多；分成几批、在不同日子调仓能减少这种运气成分。这不增加任何可调参数，却可能让实盘结果更稳。它影响以后实盘试点的执行方式。
- plan: 先联网读 Newfound 原文和对趋势/杠杆策略的复现，登记来源。然后预注册：(a) S3 在每月第 1–21 个交易日调仓的 21 个版本，报告年化、夏普、最大回撤的分布，看月末版本处在分布的哪个位置（这是描述，不是挑选）；(b) 4 批版本：资金分 4 份，分别在第 0、5、10、15 个交易日偏移调仓。通过条件：4 批版本在对标窗和压力期（2016-05→2023-08）的最大回撤都比月末版本小，夏普下降不超过 0.05，20 bp/边下仍过 G1 或 G1'。窗口和成本按冻结合同。续期规则冻结到 2026-11-01，结论只作为下次续期的提案。
- done_when: 迭代档案 `--stage final` 通过；在 `reports/research/control/decision-s3-live-pilot-2026-09-24.zh.md` 末尾加 5 行以内的结论；登记簿行 `dir:s3_rebalance_timing_luck_tranching`。
- notes:
  - 2026-09-28 01:07 UTC 自动轮 aab621c8 开始。
  - 2026-09-28 结果（已对照 results.json 逐条核对）：否定，0/4。T4 对 O00：对标窗回撤 −35.2% 对 −32.3%，夏普 1.52 对 1.82，压力期回撤 −52.0% 对 −48.0%，G1/G1' 不过。T4 落在 21 个偏移版本的中位数附近；失败原因是月末版本在选择窗和对标窗都是 21 个里最好的（对标窗中位数 85.8%/1.49/−35.4%，21 个里 10 个过 G1）。产物：`reports/research/iterations/h20260928_01_s3_rebalance_tranching/`，卡片 `H-20260928-01`，登记簿 `dir:s3_rebalance_timing_luck_tranching`，决定页已加结论。

### T-20260928-02 加一条和 S3 不同向的跨资产趋势 sleeve，能否提高整体夏普
- status: done
- priority: 1
- not_before:
- goal: 机主的标准是夏普（2026-09-28）。S3 不挑调仓日的夏普：对标窗约 1.5、选择窗约 1.15、2016–2023 约 0.8（H-20260928-01）；它和 S1、S2 高度同向，所以三者合并只等于降仓（H-20260927-01）。提高夏普的正路是加一条熊市里和 S3 不同向、自身夏普也不差的收益来源。先试已发表、规则公开的跨资产趋势：债券、黄金、商品、美元。
- plan: (1) 联网读原文并登记来源：Defense First（登记簿 `dir:defense_first_taa_carlson_concretum`，代码 `scripts/run_h20260923_12_s3_defense_first.py` 的 `defense_weights`；上次 `dir:s3_defense_first_remainder` 只用它替换 S3 的闲置现金，这次是独立 sleeve 按风险加权，direction-review 里写清楚区别）；跨资产时间序列动量（Moskowitz, Ooi & Pedersen 2012；Hurst, Ooi & Pedersen 2017）的 ETF 做法。(2) 预注册、不调参：D1 = Defense First 独立 sleeve（按原规则）；D2 = TLT、GLD、DBC、UUP 各自在过去 12 个月收益高于 SHY 时持有，按过去 63 天波动率倒数分配，否则放 SHY，月度调仓。所有月度 sleeve（D1、D2 和 S3）都用 4 批调仓版本（偏移 0/5/10/15 个交易日，照 `scripts/run_h20260928_01_s3_rebalance_tranching.py` 的 T4），不挑调仓日。(3) 组合 M_D1、M_D2 = S3 与 D 按过去 63 天波动率倒数月度加权；对照 = k·S3 + (1−k)·SHY，k 在每个窗口单独求，使波动与组合相同。(4) 判定按 `docs/runbook-autonomous-round.zh.md` 第 5 节"判定分档"（机主 2026-09-28 放宽）：K2 组合夏普比对照高 ≥0.05 且对标窗和压力期（2016-05→2023-09-15）同时成立为"保留"，≥0.10 为"强保留"；D 单独的偏移中位数夏普两窗都达到 S3 的八成（1.19、0.65）也算保留（K1）。另报告 D 单独的夏普、D 与 S3 的日收益相关（压力期、对标窗、2022 年）；2026 年受污染，只作参考。(5) 通过了才做下一步（把 D 换成杠杆版本，让组合收益回到 G1 水平），不在本任务里做。
- done_when: 迭代 `--stage final` 通过；假设卡、decision record、登记簿行 `dir:cross_asset_trend_sleeve_with_s3`、覆盖地图 `portfolio.combination_and_risk` 更新；current-view 顶部最多 5 行。
- notes:
  - 2026-09-28 03:15 UTC 交互会话派 Sonnet 用批量通道执行（迭代 h20260928_02_cross_asset_sleeve；按偏移中位数判定，替代原写的 4 批版本，结果出来前已定）。自动轮不要碰。
  - 2026-09-28 交互会话补充的本地先例（写任务时漏查了，必须先读）：Step 10 W1 F2（约 09-04）已经单独测过跨资产 ETF 时间序列动量，12 个候选 0/12，最好的超额夏普 0.65；危机窗口跌得比 SPY 少但仍然亏（2022 −10.1%，2020 崩盘 −12.5%，2018Q4 −8.1%）。结论 `reports/research/control/step10-w1-cross-asset-trend-2026-09.md`，机制代码 `open_composer/research/kernel/mechanisms/cross_asset_trend_etf`，评估脚本 `scripts/evaluate_cross_asset_trend_sip.py`。能复用的数据和代码直接复用。本任务和它的区别是：不看 D 单独过不过门槛，只看和 S3 组合后的夏普增量。direction-review 里写清楚这个区别；如果 D2 的规则和 Step 10 的某个候选相同，要注明是同一规则重测。
  - 2026-09-28 结果：D1（Defense First）按 K1 保留（偏移中位数 1.48/0.73），随后机主决定不要、不做跨资产，kept 里标 dropped_by_owner；D2 否定。档案 `reports/research/iterations/h20260928_02_cross_asset_sleeve/`。

### T-20260928-05 登记簿补录 2026-09-23 以前的实验
- status: done
- priority: 1
- not_before:
- goal: 方向登记簿是 09-23 建的，没收录更早的实验，所以写新任务时会漏查本地先例（09-28 就漏了 Step 10 的跨资产趋势 0/12）。补齐后，每个新方向查重一次就能看到本地是否测过，省掉重复测试。
- plan: 轻活，不跑回测。(1) 列出 `reports/research/iterations/` 下所有不以 `h2026` 开头的档案，以及 `reports/research/control/` 里带结论的报告（`grep -l "结论\|verdict\|0/[0-9]" reports/research/control/*.md`）、`reports/research/ledger/experiments.jsonl` 里的 family。(2) 每个机制或家族用 `uv run oc research directions check <关键词>` 查重；登记簿已有就只在 evidence 里补路径，没有就追加一行：status 按原结论（refuted / partial / passed / evidence_too_weak），verdict 一句话带关键数字，evidence 写报告路径，`found_by` 写 `backfill-2026-09-28`，`reopen_if` 写原报告建议的重开条件。(3) `uv run oc research directions validate` 必须 ok。不改已有行的 status。
- done_when: 补录行数和清单写进 `reports/research/control/registry-backfill-2026-09-28.md`（每行：方向 id、原报告路径、结论）；validate ok；提交。
- notes:
  - 2026-09-28 03:15 UTC 交互会话派 Sonnet 执行，同时判定 11 个文本和方法类方向。自动轮不要碰。
  - 2026-09-28 完成：补录 21 条（`reports/research/control/registry-backfill-2026-09-28.md`），11 个文本和方法类方向已判定。

### T-20260928-06 按新标准重判登记簿，生成批量测试清单
- status: done
- priority: 1
- not_before:
- goal: 登记簿里 71 个方向只收进来没判断过，55 个标"证据不足"，当时的标准是"单独能否高收益"。机主 2026-09-28 把标准改成"夏普和 S3 差不多，或能给 S3 加分"，一部分旧方向在新标准下值得批量测。目标是把能批量测的挑出来，排成下一批、下下批。
- plan: 轻活，不跑回测。(1) 读 `docs/runbook-autonomous-round.zh.md` 第 5 节"判定分档"。(2) 对 status 为 harvested、evidence_too_weak、triaged、queued 的行逐条判断：能不能只做多、用日线数据、按公开规则写成一个每月或每周给出目标权重的函数（能 / 不能及原因）；在新标准下的先验（高 / 中 / 低，一句理由：已知的夏普、和 S3 可能的相关性）。(3) 能写成函数、先验不低的，按主题分组，每组 10–30 条，作为一个批量任务写进本队列（格式照第 9 节，plan 里列出每条规则的出处和规则要点）。(4) 登记簿里被判断过的行把 status 改成 `triaged`，verdict 写一句结论；`uv run oc research directions validate` 必须 ok。不改 refuted / passed 的行。
- done_when: `reports/research/control/retriage-2026-09-28.md`（逐条表格 + 分组）；队列新增批量任务；validate ok；提交。
- notes:
  - 2026-09-28 交互会话拆给三个代理：ETF 类 24 条（迭代 h20260928_05_registry_etf_batch2）、股票/日内/事件/模型类 25 条（h20260928_06_registry_stock_batch3，当天测）、文本和方法类 11 条（随 T-20260928-05）。自动轮不要碰。
  - 2026-09-28 完成：第一批 0/19；第二批 0/7，另有 2 条近期观察；第三批股票层面 0/10，其中 3 条需要分钟数据，转 T-20260928-12。登记簿剩下未判定的方向都已有对应任务：T-15、T-16、T-17、T-22，以及 Modal 会话的 T-10 和信任门任务。

### T-20260928-07 保留候选的前向跟踪（影子）
- status: done
- priority: 2
- not_before:
- goal: 前向证据只能按日历时间积累。保留下来的候选越早开始跟踪，越早知道它在没见过的数据上是否还成立。日线 ETF 规则是确定的函数，所以不需要每天下单：把规则连同代码版本在保留当天冻结，之后任何时候都能诚实地复算"保留日之后"的表现。
- plan: 前置条件：`reports/research/screens/SELF_CHECK_OK` 存在（批量通道已由交互会话核对）。不存在就跳过本任务，选下一个。(1) `reports/research/screens/kept.jsonl`：每个保留候选一行（id、批次、保留日期、提交哈希、候选模块和 id、档位 K1/K2、保留时的关键数字）。(2) `scripts/shadow_forward.py`：读 kept.jsonl，用 `scripts/screen_lane.py` 的同一套引擎，只算保留日之后的日收益，报告累计收益、夏普（样本不足 20 个交易日就只报收益）、同期 S3 和 SPY，并检查代码版本和冻结时的一致（不一致就报警，不算）。(3) 测试用合成数据。(4) 写 `reports/research/screens/forward.md`。以后每周一的第一轮刷新一次（加进本队列作为长期任务）。
- done_when: 脚本、测试、forward.md 生成；ruff 和相关测试通过；提交。
- notes:
  - 2026-09-28 完成（a86c785）：`scripts/shadow_forward.py`，规则按提交冻结，只算保留之后的交易日；每周一刷新见 T-20260928-19。在跟踪：月末反转、板块季节性领跑、两者各半组合 C2（都是 watch_recent）。

### T-20260928-13 Defense First 与 S3 的组合方式：优化迭代
- status: done
- priority: 1
- not_before:
- goal: Defense First（D1）单独的夏普和 S3 差不多（偏移中位数：对标窗 1.48、压力期 0.73），和 S3 的相关只有 0.27–0.30，已按 K1 保留（H-20260928-02）。但按预先登记的组合方式（过去 63 天波动率倒数、每月调），压力期只比同波动 S3 高 0.04；交互会话的粗算显示，按全期固定风险平价混合，压力期可到 0.94（S3 是 0.85）。组合方式本身可能是瓶颈。
- plan: 新迭代，先过两道检查。预注册 ≤8 个组合方式：63/126/252 天波动率倒数（每月调），252 天等风险贡献（每季调），固定资金比例 S3/D1 = 15/85、20/80、25/75（每月调回）。每个方式都在 D1 的 21 个调仓偏移上算，按中位数判断；对照仍是同波动的 S3。复用 `scripts/screen_lane.py` 的 `diversifier_edge_for_offset` 和 `combine_two_sleeves`，新方式另写函数、加测试。替换原方式的条件：对标窗和压力期的组合增量都比原方式高 ≥0.10。全部 8 个计入试验次数，报告 DSR。
- done_when: `--stage final` 通过；结论写进登记簿 `dir:cross_asset_trend_sleeve_with_s3` 的新行；current-view ≤5 行。
- notes:
  - 2026-09-28 06:3x UTC 机主决定：Defense First 不需要，不做跨资产。本任务取消（执行中的代理已叫停，半成品不入档）。

### T-20260928-14 盈余意外因子改用 8-K 2.02 公告时间（`dir:pead_xbrl_8k_llm` 的会计部分）
- status: done
- priority: 1
- not_before:
- goal: 以前按 10-Q/10-K 申报日测的盈余意外（SUE）已否定，当时写的重开条件就是"改用 8-K 2.02 财报公告的时间"。这一步不用大模型，今天就能测。
- plan: 按 `reports/research/control/registry-backfill-2026-09-28.md` 的 Job B 计划：复用 fundamentals-v1 信号卡流程和它的"改日期"安慰剂，只把 `visible_at` 换成 8-K 2.02 附件的接收时间；按原来的准入规则判断（逐年稳定、赢安慰剂、10/20 bp 下过 G1），另按 K1/K2 报告。重任务，同一时间只跑一个，跑在第三批（h20260928_06）结束之后。
- done_when: 迭代 `--stage final` 通过；登记簿新行；只有过了准入规则，才在队列加大模型读语气的第二阶段。
- notes:
  - 2026-09-28 结果（3a610d2）：不成立。t 1.06 < 3，输给错位安慰剂；20bp 组合超额 −0.14%/年，夏普 0.61，基准 0.71。第二阶段 LLM 不做。注：Modal 会话另有同号的 T-20260928-13/14，引用时带上标题。

### T-20260928-15 Claude 写因子的小批量（`dir:llm_hypothesis_code_backtest_loop` 的方法）
- status: done
- priority: 2
- not_before:
- goal: 检验"大模型提假设、写因子代码、按 IC 反馈"这个方法在我们的数据上能不能比现有因子库（Alpha101/158/191/OSAP）更好。只写代码，不做批量标注。
- plan: 预注册 5–10 个有经济逻辑的因子（写出假设和出处），一次写完不再按结果改；用现有的 IC/RankIC 流程在最近的样本外段筛；判断标准只有一条：这批最好的因子是否超过现有库最好的因子（同一样本段、同一成本）。
- done_when: 结论和数字写进登记簿；超过了才把这个方法写进自动轮手册。
- notes:
  - 2026-09-28 06:5x UTC 交互会话派 Sonnet 执行（迭代 h20260928_15_claude_factor_batch）。IC 反馈只做一轮，而且只看选择窗；并入机主六篇论文里第 1、6 篇的做法，包括置信度门。自动轮不要碰。
  - 2026-09-28 结果：不成立。协调员补正后 zoo 加入完整 Alpha158（154 列），TEST 窗口统一到 2026-09-08。批里选出的 F10（ROE+毛利率+低应计的三因子质量复合，SELECT ICIR 0.272）在 TEST rank IC 上赢 zoo 选出的 Alpha158 CORD60（0.0274 对 0.0217），但 TEST 20bp 前 50 组合夏普输（0.640 对 0.879）；两条都要满足才算通过，只满足一条。`--stage final` 通过；登记簿新增一行 `dir:llm_hypothesis_code_backtest_loop`（status refuted）；第二阶段不开。

### T-20260928-16 DeepSeek 试点：8-K 情绪加速度（一季度 IC）
- status: cancelled
- priority: 2
- not_before:
- goal: `dir:llm_8k_gdelt_sentiment_acceleration` 的最便宜否定测试。
- plan: 按 `reports/research/control/registry-backfill-2026-09-28.md` Job B 的计划。打分只用机主配置的 DeepSeek 接口，不用 Claude。先算最近一个季度的 IC（对未来 5 日收益），同时跑打乱新闻的安慰剂。IC 符号不稳、或安慰剂也能复现，就停，不搭完整的走步验证。
- done_when: IC 和安慰剂结果写进登记簿；决定继续或停止。
- notes:
  - 2026-09-28 交互会话派 Sonnet 执行；DeepSeek 限流后按 next_try_at 自动续跑。自动轮不要碰。
  - 2026-09-29 05:42:05 UTC：机主停掉执行代理（与 T-20260929-12 同一时刻），按取消处理，机主要求才继续。
    - 停止后，独立的打分脚本仍把 DeepSeek 打分跑完了（09:58 UTC，2,092/2,092 条：2,042 条新闻 + 50 份 8-K，全部 ok，存在 `data/features/h20260928_16_sentiment_accel_scores/items.parquet`）。
    - 预注册的 IC 和安慰剂没有算。如要继续，只剩这一步，不需要再调用 DeepSeek。
    - 脚本和测试已归档。

### T-20260928-17 DeepSeek 试点：10-K/8-K 风险标签特征（400 份）
- status: done
- priority: 2
- not_before:
- goal: `dir:text_to_pit_feature_extraction` 的最便宜否定测试。
- plan: 按同一份报告 Job B 的计划：50 只股票 × 8 个季度，DeepSeek 抽取结构化风险标签，作为一个特征加进现有截面排序；看 IC 增量，并跑错配申报文件的安慰剂。增量为正且符号稳定才扩大。
- done_when: 结论写进登记簿。
- notes:
  - 2026-09-28 交互会话派 Sonnet 执行，正在打分。自动轮不要碰。
  - 结果（2026-09-28，队列状态 2026-09-29 补改）：登记簿 `dir:text_to_pit_feature_extraction` 已判 refuted。真实 IC 为负，但 8 个季度样本下和安慰剂噪声分不开（反号安慰剂达到真实幅度的 75%）。档案见 `reports/research/iterations/h20260928_17_filing_risk_labels/`。

### T-20260928-18 补 VIX 和 PUTW 数据，再测两条 ETF 规则
- status: done
- priority: 2
- not_before:
- goal: 第二批里有两条只因缺数据没测：`dir:spy_sso_tlt_vix_regime_rotation`（缺 VIX）、`dir:put_credit_spread_income`（卖 put 的 ETF 代理 PUTW 缺数据）。
- plan: VIX 用 FRED 公开的 VIXCLS 日数据，PUTW 走仓库现有的日线入库流程；两种数据都要先确认日期对齐、没有未来信息。然后新开一个小批次，走批量通道（先写档案和候选清单）。按日历触发的规则声明成 "D"。
- done_when: 两条的结论写进登记簿。
- notes:
  - 2026-09-28 结果（c8ae648）：PUTW 不在 Alpaca 可交易列表（没有 SIP 日线），卖权代理不可执行；VIX/SPY/SSO/TLT 轮动属于跨资产，机主不做，搁置；FRED VIXCLS 已存在本地，留给股票内的 VIX 择时用。

### T-20260928-08 Modal 通道：云端运行器和一致性检查
- status: done
- priority: 1
- not_before:
- goal: 本机 4 GB 内存、没有 GPU，股票层面的大面板、模型训练和成批并行回测跑不动或只能跑一部分（例如 H-20260917-02 只跑了 6 个单元里的岭回归 1 个）。机主 2026-09-28 批准用 Modal 的每月 $30 免费额度。先做一个通用运行器，把现有脚本原样搬上去跑，结果和本机逐位一致，后面的任务才可信。
- plan: `scripts/modal_run.py`：限额检查（`scripts/modal_budget.py`）→ 按白名单打包代码（不含 `.env`、密钥、`data/`、`reports/`）→ 数据按需同步到卷 `oc-data` → 容器里按申请核数设线程 → 结果拉回本地原路径 → 记实际耗时和花费。支持分片并行（N 个容器同时跑）。一致性检查：在 Modal 上重跑 H-20260928-01，结果 JSON 和本机逐项一致。
- done_when: 一致性检查通过并写进 `reports/research/control/modal-parity-2026-09-28.md`；测试通过；提交；本任务花费 ≤ $1。
- notes:
  - 2026-09-28 03:2x UTC 交互会话（Modal 通道）派 Sonnet 在做，自动轮不要碰。
  - 2026-09-28 06:20 UTC 交互会话：运行器 `scripts/modal_run.py` + `scripts/modal_app.py` 完成；一致性检查通过（H-20260928-01 的 1326 个数值字段最大差 2.2e-16），报告 `reports/research/control/modal-parity-2026-09-28.md`，提交 811941b。

### T-20260928-09 Modal 通道调研：多来源截面排序模型、K 线图像 CNN
- status: done
- priority: 1
- not_before:
- goal: 两个以前因为算力搁置、而不是被证据否定的方向：(a) 把量价因子、XBRL 财报、内部人、空头、财报日等多种来源合进一个 GBDT/排序模型（Gu-Kelly-Xiu 的做法；本地只测过单项信号、等权合成和纯量价 ML）；(b) Jiang-Kelly-Xiu 2023 K 线图像 CNN（`I-20260923-09` 排第 1 的 GPU 方法，没人测过 2019 年以后）。先联网找 2020 年以后的样本外证据、大盘股只做多的数字、现成实现，再定预注册和最便宜的否定测试。
- plan: 只调研和写预注册草稿，不跑回测。产物 `reports/research/intel/I-20260928-02-modal-lane-ml-cnn.md`；登记簿查重并补行。
- done_when: 简报给出做 / 不做及理由、预注册草稿（候选不超过 12 个、窗口、成本、否定条件）；登记簿 validate ok；提交。
- notes:
  - 2026-09-28 03:2x UTC 交互会话（Modal 通道）派 Sonnet 在做，自动轮不要碰。
  - 2026-09-28 完成：简报 `reports/research/intel/I-20260928-02-modal-lane-ml-cnn.md`。机主中途决定：(a) 多来源排序模型 GO——放宽到全体 Alpaca 可交易美股（价格>=$3、21 日美元成交额>=$1M，不再限流动性前 1000），登记簿行 `dir:ml_ranking_broad_universe_custom` 改 `queued`（12 候选、分两段 Modal 预算：kill test $0.95、full eval $2.85）；(b) K 线图像 CNN 机主降级搁置（非否定），新增登记簿行 `dir:chart_image_cnn_jkx_replication`（`parked`，证据保留，否定测试已备好待重开）。`oc research directions validate` 通过。

### T-20260928-10 Modal：多来源截面排序模型（依赖 08；09 已定稿）
- status: done（Stage 1 否定测试 FAIL，不进 Stage 2）
- priority: 1
- not_before:
- goal: 回答"多种免费数据合进一个模型，能否在流动性好的股票上给出只做多、扣成本后的超额"。按 09 的预注册执行。
- plan: 预注册草稿见 `reports/research/intel/I-20260928-02-modal-lane-ml-cnn.md` A.4（12 个候选；否定测试只跑候选 5、6、11，只看压力期，走步验证 RankIC ≥ 0.02 且比纯量价基线高 ≥ 0.01 才进完整评估）。先建迭代档案、direction-review、候选清单，过 direction-check 和 pre-backtest 检查再上 Modal。约定：机主 2026-09-28 说流动性低的股票他也能交易，所以股票池不限大盘：Alpaca 可交易的美股普通股、价格 ≥ $3、21 日成交额中位数 ≥ $100 万；成本按每只股票估算（10 bp + 半个估计买卖价差，压力情形 20 bp + 整个价差），单只仓位不超过 21 日成交额的 1%，结果按流动性三档分开报；走步训练、隔离期，10/20 bp；分两段花钱（机主 2026-09-28：尽量少花）：否定测试 ≤ $1，只看 2016–2023 压力期的排序 IC 是否明显高于纯量价基线（H-20260917-02 岭回归 IC 0.007），不高就停，不看对标窗；过了才做完整评估（≤ $3），按 K1/K2 和 G1–G5 判。
- scope_2026-09-28: 机主问"LightGBM、调参、结合别的因子和策略不值得做吗"。本任务就是这个方向的主线（ML 工厂），范围定为：特征 = 量价（Alpha158/101、OSAP 价格类）+ 财报（XBRL，按申报日）+ 内部人 + 空头/卖空量 + 财报日 + 现有规则策略的信号（12-1 动量、内部人集中买入、ROE 等作为特征，让模型决定权重）+ 市场状态（SPY 趋势、波动率、板块相对强弱）；模型 = LightGBM 回归和 LambdaRank 为主，完整评估时加 CatBoost 和一个小 MLP 做等权集成；调参只在每个走步训练窗内部的验证段用 Optuna，每个模型最多 30 次，测试段不参与；标签 5/10/21 日，截面去均值并做行业/贝塔中性化；组合 = 只做多前 N 只加持仓缓冲降换手，按每只股票价差计成本；最后单独报它和 S3 按波动率倒数组合的夏普增量（K2）。否定测试仍按 A.4：只跑候选 5、6、11，只看压力期 RankIC。按机主要求直接训练、看结果，不另写长篇计划。
- design: 总体策略设计（两个引擎 + 分配层、推进顺序、接入模拟盘）见 `reports/research/control/ml-strategy-design-2026-09-28.md`；本任务是其中第 1–3 步。
- features_add_2026-09-28: I-20260928-04（JKP 因子库）2023 年以来唯一显著多于运气的一族是会计变化类（经营现金流/资产变化、季度利润/资产变化、利润/净资产变化、连续 8 季利润增长；2010–2022 年接近 0，2023 年起转强）。能用 `data/features/sec_fundamentals_daily` 算的 `ocf_at_chg1`、`niq_at_chg1`、`niq_be_chg1`、`ni_inc8q` 加进特征；只做多一侧单独夏普 <1，不单独做策略。
- done_when: 迭代 `--stage final` 通过；登记簿、覆盖地图、current-view 更新。
- notes:
  - 2026-09-28 07:00 UTC Stage 1 否定测试 FAIL（Modal 8 核/32GiB/90min 实跑，$0.2105；连
    3 次 smoke 共 $0.015，任务总花费约 $0.226）。压力期 2016-05-02→2023-08-31 验证集
    RankIC：候选 5（回归/monthly）-0.0163（t=-0.74，n=45）；候选 6（回归/biweekly）
    0.0032（t=0.21，n=106）；候选 11（LambdaRank/monthly）-0.0172（t=-0.76，n=45）；
    B0（纯量价 LightGBM 基线）0.0014（t=0.18，n=75）。判定线 RankIC>=0.02 且
    >=max(0.0071,B0)+0.01=0.0171，三个候选均未过，5/11 为负。数据层覆盖：`short_interest`/
    `short_volume` 只覆盖流动性前 1000/500（宽池子上覆盖率 17%/39%），`accruals`/
    `gross_profitability`/SUE/两个 niq_chg1 覆盖率也 <50%，均按既有 50% 阈值规则自动剔除
    （33/45 特征入模）；候选 5/6/11 的流动性三档诊断因此只有 T1_liquid 档有样本。产物：
    `reports/research/iterations/t20260928_10_ml_killtest/{results.json,feature_ic.csv,report.md}`；
    脚本 `scripts/run_t20260928_10_ml_killtest.py`；登记簿 `dir:ml_ranking_broad_universe_custom`
    改 `refuted`。不进 Stage 2（$2.85 未花）。

### T-20260929-32 放开做空：十几个"空头腿不可执行"方向重新分级 + 跳空回补多空重测
- status: running
- priority: 1
- not_before:
- goal: 机主 2026-09-29 把研究范围放到 Alpaca 模拟盘能交易的全部品种（含做空）。跳空回补 2016–2021 扣成本前年化 99%、夏普 3.0，收益在空头腿，当时只因不能做空而停。
- plan: 核对 Alpaca 做空/借券/保证金规则；重新分级所有因做空被判不可执行的方向；跳空回补做多空和"只做空 + 买 SPY 对冲"两种，空头只用容易借的股票，按价差和借券费扣成本，按成交额分档报告。
- done_when: `reports/research/control/short-unlocked-retriage-2026-09-29.md`、`reports/research/iterations/t20260929_32_gap_fade_ls/`；登记簿更新；提交。
- notes:
  - 2026-09-29 交互会话派 Sonnet 在做，自动轮不要碰。

### T-20260929-37 放开做空后的多空批量：双重股权套利、ETF 与成分股领先滞后回归、板块月内动量
- status: done
- priority: 1
- not_before:
- goal: T-20260929-32 重新分级后排进队列的三个多空方向（`reports/research/control/short-unlocked-retriage-2026-09-29.md`）。跳空回补的教训：每天全换仓的策略，扣掉价差和借券费后必亏（扣成本前每天 +11.5 bp，扣后 −38.5 bp）。所以每个方向先测换手低的版本（周度/月度调仓、持仓缓冲）。
- plan: 先读原文和登记簿证据；空头只用容易借的股票（收盘价 ≥ $5、21 日成交额 ≥ $500 万，排除空头天数最高的一成），借券费按成交额分档 0.5%/2%/5% 每年（Alpaca 模拟盘不扣借券费，回测必须自己扣）；成本 5 bp + 半个 Abdi-Ranaldo 价差，压力情形翻倍，并报告冻结的 10/20 bp；价格必须先过 `price_hygiene.sanitize_price_matrices`，剔除触发日像拆股的信号；全部调仓日偏移取中位数；安慰剂；K1/K2。
- done_when: 迭代档案 + 登记簿 + 提交。
- notes:
  - 2026-09-29 19:07 UTC 自动轮（d1ed2d06）开始，派 sonnet-high 子代理执行。
  - 2026-09-29 19:07 轮结果（协调者已按 results.json 逐条复算分档）：0/16 保留、0 近期观察，三条方向全部 refuted。双重股权最好 DC_M252_ALWAYS 对标窗/压力期偏移中位数夏普（10bp+借券）−0.02/−0.07，毛夏普 0.5–1.05 被两腿成本吃掉；ETF→成分股最好 LL_SOXX_K3_H5 0.76/−0.22（安慰剂最高 0.20，但压力期为负），XLK 版毛收益为负；板块月内动量原版 SIM_LS_K2 −1.04/−0.71，年换手 142 倍。K2 压力期增量全为负；DSR ≤0.24。注意：纯短债 sleeve 在这套 K2 机制里也有 +2.30/+0.76 的增量，低波动候选的 K2 不能单独当证据。登记簿里双重股权"5.20%/夏普 1.68"在 paperswithbacktest 页面上找不到（页面写 No backtest）。产物 `reports/research/iterations/h20260929_37_ls_short_unlocked/`、`scripts/run_h20260929_37_ls_short_unlocked.py`。

### T-20260929-33 加密货币趋势（Alpaca 现货，只做多）批量筛选
- status: done
- priority: 1
- not_before:
- goal: 机主 2026-09-29 放开范围后，加密货币是模拟盘支持、但从没按趋势规则系统测过的品种（以前只看过高频加密模型，判为不可行）。看已发表的趋势/动量规则能否达到 K1，或给 S3 加分（K2）。
- plan: 先联网找 2023–2026 的加密趋势实盘或前向记录和反面证据；数据用 Alpaca 加密日线（本机取，密钥不上传）或交易所公开数据；候选 10–20 条已发表规则（时间序列动量、均线过滤、双动量、波动率目标），全部偏移中位数、20 bp、安慰剂、K2；每天 24 小时交易，按 UTC 日收盘。
- done_when: 迭代档案 + 登记簿 + 提交。
- notes:
  - 2026-09-29 07:07 UTC 自动轮开始，派 sonnet-high 子代理执行（批量通道新增 `extend_panel` 钩子，提交 4a0775a）。

  - 2026-09-29 07:07 轮结果（协调者已对照 leaderboard.json 核对 13 条）：否定，0/13 保留、无近期观察。行情用 Binance/Coinbase 公共 K 线取美东 09:30/16:00 价（无密钥，10 个 Alpaca 可交易币，BTC/ETH 从 2016-05）。最好 BTC_DONCHIAN_ENSEMBLE_VT40：对标窗夏普 0.91（门槛 1.19）、压力期 0.71；K2 对标窗 +0.16 但压力期 −0.06。BTC 买入持有对标窗 0.62、压力期 1.13；K2 恰好相反（对标窗 −0.26、压力期 +0.53）——加密在 2016–2023 能给 S3 分散，2024 以后反而拖累。截面动量对标窗 0.02–0.12（压力期 1.39–1.48，典型的只在旧样本有效）。随机择时安慰剂 0.00，规则都有真信号但不够。DSR ≤0.35。30bp 费用检查未触发。登记簿 `dir:crypto_trend_btc`、`dir:crypto_xs_momentum` 更新；覆盖地图新格 `trend_momentum.crypto_trend`。产物：`reports/research/iterations/h20260929_33_crypto_trend/`、`scripts/fetch_crypto_session_prices.py`。
### T-20260929-34 单只股票加杠杆趋势（S3 的个股版）
- status: done
- priority: 2
- not_before:
- goal: S3 用杠杆板块 ETF 抓领涨赛道。个股版：在大盘龙头股里按动量选前 1–3 只，用 2 倍（合成的 2 倍日重置收益，2022 年后可用真实的 2 倍单股 ETF，如 NVDL；或保证金 2 倍）。检验能否达到 K1，或和 S3 组合后夏普更高。
- plan: 菜单 = 当时市值前 20–50 的股票（按时间点，不能用今天的名单）；合成 2 倍日重置收益，扣费率和融资成本；照搬 S3 的规则框架（63 日动量、绝对动量过滤、vt40），全部偏移中位数、安慰剂、K2。
- done_when: 迭代档案 + 登记簿 + 提交。
- notes:
  - 数据清洗（2026-09-29，另一会话在 T-20 踩到）：`data/sip/daily` 有破产后重新上市沿用旧代码（WOLF）、单日错误成交价（KIDZ、IXHL）、漏调的拆股（APH 2026-08-27）。个股回测必须先过 `open_composer.research.features.price_hygiene.sanitize_price_matrices(close_wide, open_wide)`（默认参数），并剔除触发日像拆股的信号；不要按持有期结果过滤。
  - 2026-09-29 07:07 UTC 自动轮开始，派 sonnet-high 子代理执行（批量通道新增 `extend_panel` 钩子，提交 4a0775a）。

  - 2026-09-29 07:07 轮结果（协调者已对照 leaderboard.json 核对 14 条）：0 保留、5 条近期观察（watch_recent，已写 kept.jsonl，commit ee2b972）：LSS_N50_K1_1X/K2_1X/K2_2X/K3_1X/K3_2X 对标窗 1.23–1.44 过 1.19，压力期 0.42–0.64 都没过 0.645（K3_2X 0.643 差 0.002）。K2 对标窗全负。选股有真增量：最好 1.44 vs 菜单等权 0.98 vs 随机 0.72。2 倍杠杆在 vt40 下不提高夏普（1x≈2x）。DSR 最高 0.73。菜单 = 时间点 S&P 500 里 63 日成交额前 20/50（`menu.parquet` 冻结到 2026-09；前向跟踪需每月末重跑 `scripts/build_h20260929_34_menu.py`）。登记簿 `dir:levered_single_stock_momentum_top_k`（partial）。产物：`reports/research/iterations/h20260929_34_levered_single_stock/`。
### T-20260929-35 日内截面规律（分钟数据，Modal）：日内周期性、隔夜/日内拉锯
- status: blocked（等机主决定日内成本口径）
- priority: 2
- not_before:
- goal: 已发表的截面日内规律，例如 Heston-Korajczyk-Sadka 2010 的同一时段收益延续，以及 Lou-Polk-Skouras 2019 的"动量赚在隔夜、反转赚在日内"，在流动性最好的股票上能否扣掉实际成本后赚钱。
- plan: 先联网找 2020 年以后的复现；成本按分钟数据估计的价差另建日内合同，同时报告冻结的 10/20 bp。
- done_when: 迭代档案 + 登记簿 + 提交。
- notes:

### T-20260929-36 纳斯达克 1 分钟多空事件路由：用 SIP 分钟数据复核
- status: done
- priority: 2
- not_before:
- goal: 登记簿 `dir:nasdaq_long_short_event_router_1m` 在 IEX 派生的 1 分钟数据上达到 research_pass（lookback=10、entry_after_bars=2、QQQ 前一段为负时才做），但没用正式 SIP 数据验证，而且当时不能做空。
- plan: 读原档案，用 `data/sip/minute`（Modal）按原规则重跑，不改参数；同时报告冻结 10/20 bp 和实测价差两种成本；安慰剂。
- done_when: 迭代档案 + 登记簿 + 提交。
- notes:
  - 数据清洗（2026-09-29，另一会话在 T-20 踩到）：`data/sip/daily` 有破产后重新上市沿用旧代码（WOLF）、单日错误成交价（KIDZ、IXHL）、漏调的拆股（APH 2026-08-27）。个股回测必须先过 `open_composer.research.features.price_hygiene.sanitize_price_matrices(close_wide, open_wide)`（默认参数），并剔除触发日像拆股的信号；不要按持有期结果过滤。
  - 2026-09-29 13:07 UTC 自动轮开始，派 sonnet-high 子代理执行（本机跑，12 只 + QQQ 的 SIP 分钟数据量小，不上 Modal）。
  - 2026-09-29 13:07 轮结果（协调者已对照 results.json 的 decision/placebo_distribution/k2_inputs 核对）：否定。冻结路由（lb10_entry2_top1…qprior_negative_reversal）在 SIP 1 分钟数据上原样重跑，原函数 `_backtest_params` 逐位复现。对标窗 2024-01-08→2026-09-28，188 笔：10bp 夏普 −0.13、年化 −1.4%；20bp 夏普 −0.73、年化 −14.2%；原草稿 2.5bp 成本下夏普 0.33，每笔毛利约 22bp、盈亏平衡约 10.9bp/边。空头腿从未触发（top_n=1 时空头与多头用同一排序、名额已被占，见 intraday_daily_rotation.py 1012–1026 行），所以 IEX 的 research_pass 实际是只做多的"开盘回落买入"。安慰剂 200 个只打赢 89%（门槛 90%）。K1 否（−0.13<1.19）、K2 否（组合增量 −0.61）。同窗同成本下 SIP 年化 10.3%/夏普 0.54，IEX 记录 35.2%/1.41，约三分之二没经受住数据源更换。分钟数据已复权。压力期待补（分钟数据 2023 起）。登记簿 `dir:nasdaq_long_short_event_router_1m` → refuted。产物：`reports/research/iterations/h20260929_36_router_sip/`，提交 fd814c7。

### T-20260929-30 模型大扫描：XGBoost/CatBoost/MLP/Ridge/LightGBM/集成 × 训练窗 × 预测周期
- status: running
- priority: 1
- not_before:
- goal: 机主 2026-09-29："XGBoost 等其他模型不行吗，多试一些，用最大的努力"。用证据回答：同一批数据上换模型族、训练窗（3 年/1 年滚动）、预测周期（5/21/63 天）能否得到可交易的排序。
- plan: 36 个组合，只按压力期 RankIC t 值选前 3（2024 年以后的数字只报告不参与挑选），前 3 做成扣价差成本的只做多组合，按 K1/K2 判；DSR 试验次数 42。Modal ≤ $3。
- done_when: `reports/research/iterations/t20260929_30_model_zoo/`；登记簿行 `dir:ml_model_zoo_stock_ranking_2026`；提交。
- notes:
  - 2026-09-29 交互会话派 Sonnet 在做，自动轮不要碰。

### T-20260929-31 强化学习与"大模型 + 强化学习"（Qwen/GRPO 等）交易证据
- status: running
- priority: 1
- not_before:
- goal: 机主问"RL 的 Qwen 之类的不行吗"。先读 2025–2026 原文和实盘记录（nof1 Alpha Arena、LiveTradeBench、Trading-R1、FLAG-Trader、FinRL 比赛），只有证据支持才定一个 ≤ $3 的试点。
- plan: 只调研；简报 + 登记簿。
- done_when: 简报在 `reports/research/intel/`；登记簿 validate ok；提交。
- notes:
  - 2026-09-29 交互会话派 Sonnet 在做，自动轮不要碰。

### T-20260928-30 纯量价 LightGBM 小盘排序：只做多组合 + 逐只价差成本
- status: done
- priority: 1
- not_before:
- goal: T-20260928-10 重跑发现纯量价 LightGBM 在放宽的股票池里有走步样本外排序能力（压力期 RankIC 0.020，t 3.1；流动性最差三分之一 0.031，t 5.75）。回答：扣掉逐只股票的价差成本后，只做多组合还剩多少，能否达到 K1/K2。
- plan: 模型 = B0 原样，每天出预测；V1 全池前 50、V2 最差流动性三分之一里前 50，等权，持仓缓冲（排名 ≤150 继续持有），月度调仓，21 个偏移取中位数；成本 10 bp + 半个 Abdi-Ranaldo 价差（压力 20 bp + 整个价差），单只 ≤ 21 日成交额中位数的 1%（账户按 $10 万）；20 个随机排名安慰剂；K2 用批量通道的同波动 S3 对比。判定线预先定死（K1：压力期 ≥0.65、对标窗 ≥1.19、压力成本下两窗年化为正；K2：+0.05）。Modal ≤ $1.5。
- done_when: `reports/research/iterations/t20260928_16_smallcap_ml_book/` 的 results.json 和 report.md；登记簿行更新；提交。
- notes:
  - 2026-09-28 14:5x UTC 交互会话派 Sonnet 在做，自动轮不要碰。
  - 2026-09-28 16:30 UTC 否定（两个版本都不过 K1/K2）：不看价差只扣 10 bp，对标窗夏普 0.21–0.33、年化 6–10%，不如 SPY；换手每年 12–17 次，价差吃掉 7–10 个百分点。`reports/research/iterations/t20260928_30_smallcap_ml_book/`，提交 23a7544。

### T-20260928-11 Modal：K 线图像 CNN 否定测试（依赖 08、09，GPU）
- status: done
- priority: 2
- not_before:
- goal: 这是本地唯一有独立复现、而且只缺 GPU 的方法。先做最便宜的否定测试：训练 2016–2019、验证 2020、测试 2021–2023，流动性前 1000 只做多最高一组，10 bp。
- plan: 待 09 定稿；复用 MIT 许可的复现代码（George-hardworking/reimaging-price-trends-replication-and-extension）。测试期最高组对全池的超额 t 值 <2 就停。分两段花钱：否定测试 ≤ $1.5（T4），过了才做对标窗完整评估（≤ $3）。排在 10 之后，10 的否定测试先出结果。
- done_when: 否定测试结论写进迭代档案和登记簿；过了再开对标窗检验。
- notes:
  - 2026-09-28 机主要求照做。第一次完整运行（T4）训练完成（第 29 轮提前停止，最好验证损失 0.6632），但样本外推断逐只逐日画图太慢，撞上 2 小时时限，模型没存，约 $2.45 白花。14:5x UTC 交互会话派 Sonnet 修：训练后先存模型、推断按股票批量多进程画图、分段存预测，再跑。
  - 2026-09-28 16:00 UTC 否定：2021–2023 超额 t −1.18、扣 10 bp 夏普 −0.65（全池 0.02）；2024 年以来也为负。`reports/research/iterations/cnn_chart_i20r5_2026-09-28/`，提交 925d651。

### T-20260928-13 找最近（2024–2026）值得训练的新模型和因子
- status: done
- priority: 1
- not_before:
- goal: 机主 2026-09-28："要找新的值得做的模型、因子，需要训练的，而不是只关注之前的论文，先找最近的。" 目标是找出 3–5 个近两年出现、有样本外或前向证据、能用我们的免费数据训练、在 Modal 上花几美元就能做否定测试的候选。
- plan: 只调研，不跑回测。(1) 搜 2024–2026 的来源，四类都要：arXiv/SSRN 新论文（看样本外是否延伸到 2023 年以后）、公开比赛的获胜方案（Kaggle Jane Street 2024、Optiver、Numerai 等，看哪些特征和模型在未见数据上有效）、带前向或实盘记录的开源仓库、从业者公开的实盘或前向记录。(2) 每个候选登记簿查重、查本地旧实验（`grep -ril`），写清和已否定路线的差别。(3) 按"每花一美元，得到能在 Alpaca 只做多执行、扣成本后结果的机会"排序；股票池可以包括流动性低的股票（机主允许），但要带价差成本。
- done_when: `reports/research/intel/I-20260928-03-recent-trainable-models.md`（证据表 + 排序 + 每个候选的否定测试和 Modal 花费估算）；登记簿新增行 validate ok；前 1–2 名写成队列任务；提交。
- notes:
  - 2026-09-28 结果：四类来源都搜了（arXiv/SSRN 2024–2026、Kaggle Jane Street/Optiver/Numerai、开源仓库、从业者实盘记录），登记簿查重覆盖 T-20260928-09/10（多来源排序模型）和已有的 AlphaForge/MASTER/期权/内部人/空头等条目，不重复。5 个候选只有 1 个够格进队列：训练一个 DEUP 式置信度/机制信任门（`dir:regime_trust_uncertainty_gate_momentum_ranker`，来自 arXiv 2603.13252 "When Alpha Breaks"），套在个股动量账本上，直接对应我们自己已经发现的问题（top-30 动量 2024 年以来 59.8%/年但回撤 −41.6%）；已写成 T-20260928-14。其余 4 个都有 2024–2026 证据但不执行：期权隐含波动率 ML（`dir:option_implied_crash_risk_xgboost_2026`，被本地已证实的免费期权数据无真实历史报价挡住）、电话会文本训练 embedding（`dir:earnings_call_transcript_trained_embeddings_2026`，本地只有 8-K 新闻稿不是电话会记录，被已证实的无免费来源挡住）、GNN 关系图模型（`dir:gnn_relational_stock_models_2024_2025`，证据太弱：30–255 只股票的小样本、只报准确率不报实盘夏普、无独立复现）、公式化因子挖掘 GP/RL 家族（AlphaForge/AlphaGen 等，重新搜了一遍，仍然只有 A 股/加密证据，Modal 解除了硬件限制但没解除证据限制，registry 条目不变）。Jane Street/Optiver/Numerai 本身没有可迁移的具体模型（数据匿名化），只作为方法论笔记登记（`dir:kaggle_jane_street_numerai_competition_methods`）。产物：`reports/research/intel/I-20260928-03-recent-trainable-models.md`；登记簿新增 5 行，`oc research directions validate` 通过。

### T-20260928-14 训练一个置信度/机制信任门，套在个股动量账本上（When Alpha Breaks 的 DEUP 式否定测试）
- status: done
- priority: 1
- not_before:
- goal: 个股动量 top-30 账本 2024 年以来 59.8%/年、但回撤 −41.6%（门槛 −35%，`docs/current-view.zh.md` 2026-09-24 11:30 章节）。机主下一步已排了一个按文献（Daniel-Moskowitz）配方的规则型防崩盘开关；本任务测一个训练出来的替代/补充：arXiv 2603.13252 "When Alpha Breaks" 给排序模型加一个两层不确定性框架——策略层的"机制信任门"（论文里 2024 年这段 AUROC 0.72–0.75）和个股层的认知不确定性上限（DEUP，用集成分歧预测排名误差）。这篇论文自己的发现——排序模型的信号恰好在 2024 年 AI 行情和板块轮动里失效——和我们自己已经发现的问题（动量账本 2024 年以来回撤失控）是同一个现象的独立印证。和已否定的规则型止盈开关（`dir:momentum_risk_control_vs_spmo`，输给日历平移安慰剂）、已否定的仓位分档元标签（`dir:meta_labeling_position_tiers`，等价于直接降仓）机制不同：这是训练出来的置信度信号，不是固定规则或单调仓位分档。
- plan: 只用本地已有数据（Alpha158 类量价特征 + 已有的 top-30 动量账本，`open_composer/research/signal_card.py`），不需要新数据。(1) 预注册：训练 k=15 个 bootstrap LightGBM 回归器（2016–2023 走步训练）预测 20 日远期收益，集成分歧作为 DEUP 式认知不确定性代理；机制信任门 G(t) = 每日截面不确定性分位数，高不确定性日对 top-30 账本减仓（先定好减仓比例，不事后调）。(2) Modal 否定测试（≤$1.5）：4 核/8GiB/45 分钟 = (4×0.0473+8×0.008)×0.75h ≈ $0.19。停止条件（先定）：门槛信号在 2024–2026 留出窗上，标记"账本回撤高于中位数的日子"的 AUROC < 0.60（论文自己的数字是 0.72–0.75，0.60 是保守下限，不是照抄论文数字），或者，用同样天数的随机日减仓做安慰剂对照，门槛版本的最大回撤改善不到 5 个百分点——两条任一命中就停，登记 refuted，不进第二段。(3) 过了才做第二段（≤$2，6 核/16GiB/90 分钟 ≈ $0.62）：按冻结合同的对标窗、压力期，K1/K2 和 G1–G5 判定，需要安慰剂。本机内存也可能装得下（规模不大），先按 Modal 预算走，执行时可以判断是否本机就能跑。
- done_when: 迭代 `--stage final` 通过（或第一段否定停止，写清原因）；登记簿行 `dir:regime_trust_uncertainty_gate_momentum_ranker` 更新为最终状态；本月 Modal 花费写进汇报（`python3 scripts/modal_budget.py status`）。
- owner_rule_check: 机主规则（2026-09-28）：减仓本身不算改进。本任务的通过线必须是夏普：门控后的账本（调仓日偏移中位数，10 bp）在对标窗和压力期的夏普都比"不门控、调到同样波动"的账本高 ≥ 0.10；只降回撤、夏普不升就判否定。按机主 09-28 的要求直接训练、看结果，不另写长篇计划。
- notes:
  - 2026-09-28 13:07 UTC 自动轮开始（Paseo 1ee0d516），派 sonnet-high 执行，迭代 h20260928_14_uncertainty_gate。
  - 2026-09-28 14:5x UTC 交互会话：13:07 那一轮派了两个后台子代理（本任务和缺口搜索）就结束了回合，Paseo 归档时把子代理一起杀了，本任务没有产物。状态改回 ready；手册已改成子代理一律前台运行。
  - 2026-09-28 19:07 UTC 自动轮开始（Paseo ecec1aba），前台派 sonnet-high 执行，迭代 h20260928_14b_uncertainty_gate（原 id h20260928_14 已被 T-14 旧编号 sue_8k 占用）。
  - 2026-09-28 20:1x UTC 结果（自动轮已对照 results.json 核对）：否定，0/3，第一段即停，未做第二段。15 个 bootstrap LightGBM 在 Modal 走步训练（2018 起样本外，花费 $0.04）。U1（高不确定时半仓）AUROC 0.522、对标窗夏普 1.136 对同波动对照 1.086（+0.050，线 0.10）、低于安慰剂 90 分位 1.177；U2（极高不确定时空仓）夏普差 −0.219；U3（剔除分歧最大的股票）夏普差 −0.324，低于随机剔除安慰剂。集成分歧不预测账本回撤。产物：`reports/research/iterations/h20260928_14b_uncertainty_gate/`，卡片 `H-20260928-31`，登记簿 `dir:regime_trust_uncertainty_gate_momentum_ranker` refuted。

### T-20260928-12 Modal：股票层面批量筛选（依赖 08 和批量通道 SELF_CHECK_OK）
- status: blocked
- priority: 2
- not_before:
- goal: 批量通道（T-20260928-03，交互会话在做）只覆盖 ETF。T-20260928-06 重判出的股票层面方向（几百到几千只股票的截面规则）本机内存放不下，在 Modal 上用同一套判定（偏移中位数夏普、同波动 S3 对比、DSR）分片并行跑。
- plan: 复用 `scripts/screen_lane.py` 的指标函数，不另写一套判定；每批 10–30 条，每条一个容器。每批 Modal 花费上限 $1（预计 $0.3–0.5）；只有候选超过本机内存时才上 Modal，ETF 级别的一律本机跑。
- done_when: 每批一个迭代档案，`--stage final` 通过；保留的写进 `reports/research/screens/kept.jsonl`。
- notes:
  - 2026-09-28 03:20 UTC 交互会话（研究）：批量通道已上线（`reports/research/screens/SELF_CHECK_OK`）。股票层面的 25 个方向正由迭代 `h20260928_06_registry_stock_batch3` 在本机测（最大 500 只、20 日重叠持仓，复用 `open_composer.research.signal_card`）；需要更大股票池、本机内存放不下的候选会在它的报告里标 `needs_modal`，本任务只接这些，不重复测本机已测的。

### T-20260928-03 批量筛选通道
- status: done
- priority: 1
- not_before:
- goal: 一次用同一套合同评估 10–30 条规则，内置"不挑调仓日"和"同波动 S3 对比"，按本批候选数报告 DSR；上线前必须精确复现 H-20260928-01 和 H-20260927-01 的数字。
- plan: 交互会话派 Sonnet 在做：`scripts/screen_lane.py`、`scripts/screen_batch.py`、`scripts/screen_batches/smoke_20260928.py`、`tests/test_screen_lane.py`。交互会话核对 `--self-check` 后创建 `reports/research/screens/SELF_CHECK_OK`。
- done_when: SELF_CHECK_OK 存在；提交。
- notes:
  - 2026-09-28 02:4x UTC 交互会话开始（自动轮不要碰）。
  - 2026-09-28 完成（e9882ff）：`scripts/screen_lane.py`、`scripts/screen_batch.py`，自检和既有数字逐位一致（`reports/research/screens/SELF_CHECK_OK`）。按日历锚定的规则必须声明为 D 并提供 signal_dates_fn，声明错了运行器会拒绝。

### T-20260928-04 第一批：S3 的替代与搭配候选库
- status: done
- priority: 1
- not_before:
- goal: 用批量通道一次判 15–25 条有实盘记录或独立复现的只做多规则：可能和 S3 差不多的（K1），或能给 S3 加分的（K2）。
- plan: 交互会话派 Sonnet 做联网调研和预注册（来源卡、direction-review、候选清单、候选模块），批量通道核对通过后运行。不含 T-20260928-02 的 D1、D2。
- done_when: 迭代 `--stage final` 通过；保留的候选写进 `reports/research/screens/kept.jsonl`；登记簿、覆盖地图、current-view 更新。
- notes:
  - 2026-09-28 交互会话负责（自动轮不要碰）。
  - 2026-09-28 结果：0/19。管理期货 ETF 和 S3 几乎不相关，但自身夏普低；资产配置规则对标窗最高 0.96（GEM）。

### T-20260927-03 新规则下第一次月度调仓核对
- status: ready
- priority: 1
- not_before: 2026-10-02 01:00 UTC
- goal: 09-30 收盘后 S2、S3 按新规则第一次月度调仓，10-01 开盘成交。核对模拟盘和研究引擎是否一致、成交质量如何，这是以后实盘的前置证据。
- plan: 读 `reports/execution/us_etf_levered_rotation_63_top2_monthly-target-weights.json` 和 S2 的同名文件（09-30 生成的目标），用 `uv run python scripts/check_rotation_overlay_parity.py` 复算 09-30 的研究引擎决定；读三条 sleeve 的 `reports/paper/rehearsal/<name>-fills.jsonl` 里 2026-10-01 的成交，看 `slippage_vs_open_bps`、是否全部成交；读 `reports/paper/alerts.md`。
- done_when: `docs/current-view.zh.md` 顶部 5 行以内的结论（一致 / 不一致及原因、滑点、有无撤单）；不一致或有撤单时在队列加修复任务。
- notes:

### T-20260927-04 修看板里的额度百分比读数
- status: done
- priority: 3
- not_before:
- goal: 2026-09-27 `open_composer.cockpit.data.quota` 读到 5 小时窗口 1000%、7 天窗口 100%、状态 stale，明显解析错了。修好后，看板能显示真实额度，自动轮以后也可以按真实额度决定跑不跑。
- plan: 用模块自己的函数取数据，只打印返回结构的键名和数值类型、数值，**绝不打印或写出令牌**；对照 `_parse_window` 找出单位或字段名变化（例如 0–1 比例和 0–100 百分比混用）；改解析并加测试（`tests/test_cockpit_quota.py` 已有 MockTransport 夹具）。不要改凭据读取逻辑。
- done_when: 相关测试通过；实测读数在 0–100 之间且有 `resets_at`；在自动轮日志摘要里写一句。
- notes:
  - 2026-09-28 交互会话派 Sonnet 在做（自动轮不要碰）：接口的 utilization 已经是百分比、resets_at 是 ISO 字符串；预检输出加 `quota`；随后按额度方案 A 改预检的判断。
  - 2026-09-28 完成（be11419）：百分比读数已修；预检加了磁盘缓存，额度按方案 A 判断。

### T-20260927-05 月度覆盖检查（第一次）
- status: ready
- priority: 3
- not_before: 2026-10-05 01:00 UTC
- goal: 按 `docs/plan-research-coverage-2026-09-23.zh.md` 第 4 节，每月检查覆盖地图还有哪些格子没搜过、没测过，避免重复和遗漏。
- plan: `uv run oc research directions summary`；统计 `reports/research/harvest/coverage.json` 各格子的方向数和状态；对照 `reports/research/harvest/feed-digest-2026-09-27.md` 找没人覆盖的格子；列出下个月最多 3 个搜索或测试任务写进本队列。
- done_when: `reports/research/control/coverage-check-2026-10.md` 写好；队列新增任务。
- notes:

### T-20260928-01 S1、S2 的调仓日运气检查
- status: done
- priority: 3
- not_before:
- goal: H-20260928-01 发现 S3 的月末调仓日在近期窗口是 21 个日子里最好的，头条数字有一大块是运气。S2（月度）和 S1（周度）也按固定日子调仓，要知道它们的数字里有多少是调仓日运气，才能给每条 sleeve 一个"不挑日子"的预期，供续期和以后实盘定规模用。
- plan: 复用 `scripts/run_h20260928_01_s3_rebalance_tranching.py` 的做法（新迭代，先过 direction-check 和 pre-backtest 检查）：S2 用续期规格（vt 0.156）做月末后 0–20 个交易日共 21 个偏移；S1 做周末后 0–4 个交易日共 5 个偏移。纯描述：报告每个窗口的最小/中位数/最大值和现行版本的排名，不采用任何偏移。只有描述、没有通过条件；现行版本排名前 3 且中位数低于它 20% 以上时，在决定页和 current-view 写"不挑日子"的数字。窗口和成本按冻结合同，压力期 2016-05→2023-08（S1 因 252 日回看从 2017-01 起）。
- done_when: 迭代档案 `--stage final` 通过；登记簿行 `dir:s1_s2_rebalance_timing_luck`；current-view 最多 3 行结论。
- notes:
  - 2026-09-28 结果已更正：首次跑漏了 `base.WARMUP_START = PANEL_START`（`run_h20260928_01_s3_rebalance_tranching.py` 有这行，本脚本原来没有），面板默默退回 recent-menu 默认起点 2022-06-01，导致"压力期"其实只覆盖 2022-06→2023-08。已修好并加了硬断言 + 回归测试重跑，面板现在正确覆盖 2016-01-04→2026-09-17；select/anchor/holdout 数字与首次一致（lookback 到 2023-09 已经热身完毕，不受影响）。更正后：S1 select/anchor 夏普(O00 1.14/1.35，中位数 0.93/1.33，差 18.3%/1.5%)、S2 select/anchor(O00 1.72/1.80，中位数 1.44/1.55，差 16.5%/14.1%)都低于 20% 高亮线，不挑日子的成分不大，不像 S3；S1 压力期(2017-01→2023-08，全量面板)O00 夏普 0.48 是 5 个偏移里最差的(第5/5，最大回撤 −32.1% 也最深)，S2 压力期(2016-05→2023-08)O00 夏普 0.52 接近中位数 0.50(第7/21)。高亮规则两条 sleeve 全窗口都没触发。两条现行规则都不变。产物：`reports/research/iterations/h20260928_23_s1_rebalance_timing/`、`reports/research/iterations/h20260928_23_s1_s2_rebalance_timing/`，登记簿 `dir:s1_s2_rebalance_timing_luck`（已追加更正行，首次的错误行保留在 jsonl 历史里，说明见两份 decision-record.md 的 "Bug fix" 段）。
  - 2026-09-28 14:5x UTC 交互会话派 Sonnet 执行（迭代 h20260928_23_s1_s2_rebalance_timing）。自动轮不要碰。

### T-20260928-19 每周一刷新前向跟踪
- status: ready
- priority: 3
- not_before: 2026-10-05 01:00 UTC
- goal: 前向证据只能按日历时间积累；`kept.jsonl` 里保留/近期观察的候选需要每周刷新一次前向表现，不必每天跑。
- plan: 跑 `scripts/run_capped.sh --mem 1.2G -- uv run python scripts/shadow_forward.py`；读 `reports/research/screens/forward.md`。只有某候选移出（`watch_exit.status == "exit"`）或新跨过阈值（前向夏普首次跌破 0.5、前向最大回撤首次超过对标窗回撤的 1.5 倍）时，才往 `docs/current-view.zh.md` 加不超过 3 行摘要；没有变化就不写。跑完把本任务的 `not_before` 改到下一个周一 01:00 UTC。
- done_when: `forward.md`/`forward.json` 已刷新；`not_before` 已推到下一个周一；必要时 current-view 已更新。
- notes:

### T-20260928-20 月末反转、板块季节性领跑：近期状态优化
- status: done
- priority: 1
- not_before:
- goal: 机主 2026-09-28 点名优化这两条近期观察规则（近两年夏普 1.24、1.40）。
- plan: 迭代 h20260928_20_recent_regime_opt。预先登记的替换规则：选择窗夏普至少高 0.10，且 2026 年不变差。
- done_when: 替换或不替换写清楚；新的观察候选进 kept.jsonl。
- notes:
  - 2026-09-28 结果（9b15143）：没有变体能替换原版。月末反转 2026 年夏普 −0.57，已失效；板块季节性相反，2026 年 3.01。两者各半组合 C2（对标窗 1.60，回撤 −7%）是描述性组合，只做前向跟踪。

### T-20260928-22 复现第 2 篇：LLM 读新闻过滤动量股（Anic 等，arXiv 2510.26228）
- status: running
- priority: 1
- not_before:
- goal: 在 DeepSeek 训练截止之后的月份里，检验"LLM 读上个月新闻，给动量前两成的股票打分，再选 50 只"是否比原版动量夏普高至少 0.10，且配错新闻的安慰剂复现不了。
- plan: 迭代 h20260928_22_llm_news_momentum_filter。DeepSeek 打分，新闻去掉公司名和代码；四个组合：原版 B、LLM 版 L、安慰剂 P、随机 R；成本 10/20bp。
- done_when: `--stage final` 通过；登记簿 `dir:llm_acceptance_judge_forward_shadow` 和第 2 篇的行已更新；通过了才加月度影子跟踪任务。
- notes:
  - 2026-09-28 06:4x UTC 交互会话派 Sonnet 执行。自动轮不要碰。

### T-20260928-40 批量筛选：因子风格 + 细分行业 ETF 动量轮动（复用 S1-S3 的机制，只换菜单）
- status: done
- priority: 2
- not_before:
- goal: S1-S3（`dir:recent_window_etf_menu_rotation`，已通过、在跑）用的是同一套跨截面 ETF 动量轮动机制（`scripts/run_h20260918_05_recent_menu.py:rotation_cell`：绝对动量过滤 + 排名前 N，63/126/252 日回看，月度/周度调仓），目前只在全球宏观、11 个 SPDR 板块、成长概念、杠杆指数四个菜单上测过。因子风格 ETF（MTUM/QUAL/USMV/VLUE/SIZE）和更细的行业 ETF（半导体/生物科技/区域银行/建筑/软件/油气开采/零售/医疗器械）离散度更高、和已测菜单的相关性可能更低，是同一台机器最便宜能测的新增量，不是新方向。
- plan: |
    新建迭代 `h20260928_40_equity_etf_menus`，候选清单模块 `scripts/screen_batches/h20260928_40_equity_etf_menus.py`（照抄 `h20260928_04_batch1.py`/`h20260928_05_batch2.py` 的写法：每个候选是纯函数 `fn(close, asof) -> weights`，只读 `close.loc[:asof]`），候选清单 JSON 见 `reports/research/iterations/h20260928_40_equity_etf_menus/candidate-manifest.json`，`direction-review.json` 引用 `dir:factor_style_etf_momentum_rotation` 和 `dir:narrow_industry_etf_momentum_rotation`。

    两个新菜单（都是绝对动量+排名前 N 轮动，和 S1-S3 引擎完全相同，只换 `MENUS` 里的 ticker 列表）：
    - **FACTOR 菜单**（来源：Quantpedia "Momentum Factor and Style Rotation Effect"，https://quantpedia.com/strategies/momentum-factor-and-style-rotation-effect，1972-2005 六只 Russell 风格 ETF 多空年化 9.25%/夏普 0.33，样本老、多空、非近期——机制复用不是这个数字本身）：MTUM、QUAL、USMV、VLUE、SIZE，5 只，全部 Alpaca 可交易、只做多。
    - **INDUSTRY 菜单**（来源：现有 S1 11 个 SPDR 板块菜单本身的实盘记录，对标窗中位数夏普 1.33-1.35；否定证据 Molchanov & Stangl "The Myth of Sector Rotation" https://acfr.aut.ac.nz/__data/assets/pdf_file/0005/294287/The-Myth-of-Sector-Rotation-non-blind.pdf 只否定宏观周期预测板块轮动，不否定价格动量机制，机制不同）：SMH、XBI、KRE、ITB、IGV、XOP、XRT、IHI，8 只，全部 Alpaca 可交易、只做多。

    网格：回看 {63, 126, 252} 日 × 排名前 N {1, 2} × 调仓 {月度, 周度}，两个菜单各 12 个组合，共 **24 个候选**（命名 `FACTOR_L{63,126,252}_N{1,2}_{MO,WK}`、`INDUSTRY_L{63,126,252}_N{1,2}_{MO,WK}`）。每个候选独立预注册判定路径：K1（偏移中位数夏普对标窗≥1.19、压力期≥0.65，20bp 下两窗年化为正）为主路径；K2（和 S3 组合增量≥0.05）为备选路径，重点看 INDUSTRY 菜单（和 S1 相关性可能高，K2 大概率过不了）、FACTOR 菜单（和现有菜单相关性未知，两条路径都测）。24 个候选算一个族，报告 DSR（`scripts/screen_batch.py` 内置）。

    `uv run oc research direction-check <path>` 和 `uv run oc research iteration validate h20260928_40_equity_etf_menus --stage pre-backtest` 通过后，跑 `uv run python scripts/screen_batch.py --batch h20260928_40_equity_etf_menus --iteration h20260928_40_equity_etf_menus`（数据已在本地面板里的用本地跑；缺的 13 只新 ticker 先用 `scripts/run_capped.sh --mem 1.8G -- uv run python scripts/fetch_daily_bars.py <新增 ticker 列表>` 或现有取数脚本补面板，同一时间只跑一个重任务）。`--stage final` 通过后，保留的候选写进 `reports/research/screens/kept.jsonl`，登记簿两条方向和覆盖地图更新。
- done_when: 迭代 `--stage final` 通过；24 个候选每个都有 K1/K2 判定结果和 DSR；`reports/research/screens/h20260928_40_equity_etf_menus/leaderboard.md` 存在；登记簿 `dir:factor_style_etf_momentum_rotation`、`dir:narrow_industry_etf_momentum_rotation` 从 queued 更新为终态（passed/partial/refuted/evidence_too_weak 等）并带 verdict、evidence、reopen_if。
- notes:
  - 2026-09-28 19:xx UTC 自动轮缺口搜索添加。
  - 2026-09-28 22:07 UTC 自动轮开始，派 sonnet-high 子代理执行。
  - 2026-09-28 结果（协调者已对照 results.json 逐条核对 24 条）：0 保留、0 强保留、5 条近期观察（全是 FACTOR 菜单，最好 FACTOR_L252_N1_WK 对标窗偏移中位数夏普 1.44、压力期 0.18，DSR 0.64），19 条否定。K2 全部不过：压力期组合增量 −0.08 到 −0.31，对标窗与 S3 相关 0.45–0.81。INDUSTRY 菜单最好的对标窗只有 0.99。两条方向登记为 refuted。产物：`reports/research/iterations/h20260928_40_equity_etf_menus/`、`reports/research/screens/h20260928_40_equity_etf_menus/`，5 条 watch_recent 已进 kept.jsonl（周一刷新前向跟踪）。

### T-20260928-41 小批量：单一国家股票指数 ETF 动量轮动（边界任务，机主先确认范围）
- status: done
- priority: 3
- not_before:
- goal: 同一套机制（见 T-20260928-40）应用到单一国家股票 ETF（EWJ 日本、EWG 德国、EWU 英国、EWA 澳大利亚、EWC 加拿大、EWZ 巴西、INDA 印度、EWY 韩国、EWT 台湾）。这些都是美股交易所上市的股票类 ETF（不是债券/黄金/商品/美元），严格符合"只用美股股票类 ETF"的范围，但和机主否决的跨资产方向相邻——本任务的第一步就是让机主确认是否在范围内，避免白测。来源：Quantpedia "Momentum Factor Effect in Country Equity Indexes"（https://quantpedia.com/strategies/momentum-factor-effect-in-country-equity-indexes，18 个国家 MSCI 指数 1975-2014 动量+低波动择时的已发表设计，本任务只借用机制，不借用其样本期数字）。
- plan: |
    先在汇报里向机主确认范围；机主未否决前不要花算力。确认后：新增 `COUNTRY` 菜单（9 只标的）到 T-20260928-40 同一个引擎/迭代基础设施（`h20260928_41_country_etf_menu`，或直接扩进 T-40 的候选模块——两者选其一，视 T-40 完成时机决定），网格缩小到回看 {63, 252} 日 × 排名前 N {1, 2} × 月度调仓 = **8 个候选**（`COUNTRY_L{63,252}_N{1,2}_MO`），判定路径同 K1/K2，DSR 按 8 候选的族计算。
- done_when: 机主范围确认记录在 notes；确认后迭代 `--stage final` 通过，登记簿 `dir:international_country_etf_momentum_rotation` 更新为终态。
- notes:
  - 2026-09-28 19:xx UTC 自动轮缺口搜索添加。
  - 2026-09-28 20:1x UTC 自动轮：改为 blocked，等机主确认单一国家股票 ETF 是否在"不做跨资产"之外；未确认前不要花算力。
  - 2026-09-29 机主确认："etf是可以的，是美股里能买到的就算"。单一国家股票 ETF 在范围内，可以测。
  - 2026-09-29 05:0x UTC 自动轮开始，派 sonnet-high 子代理执行（与 T-20260929-02 同一子代理顺序做）。
  - 2026-09-29 04:07 轮结果（协调者已对照 leaderboard.json 核对 8 条）：0/8 保留，3 条近期观察（watch_recent，已写入 kept.jsonl）：COUNTRY_L63_N1_MO 对标窗 1.21 / 压力期 0.04，COUNTRY_L252_N2_MO 1.21 / −0.14，COUNTRY_L252_N2_WK 1.22 / −0.18；DSR 最高 0.70；K2 压力期全负（−0.18 到 −0.46）。登记簿 `dir:international_country_etf_momentum_rotation` partial。产物：`reports/research/iterations/h20260928_41_country_etf_rotation/`。

### T-20260928-42 批量筛选：期权到期周日历效应（大盘/指数 ETF，只做多）
- status: done
- priority: 2
- not_before:
- goal: 缺口搜索（`gap-search-2026-09-28-22`）覆盖地图里标记"期权到期日/交易商对冲流从未搜索"的格子（`flows_structural.rebalance_and_hedging_flows`，见 `reports/research/harvest/coverage.json` 该格子的 `gap` 字段）。规则纯用日历+收盘价：每月第三个星期五所在的一周只做多大盘/指数 ETF，其余三周持现金。机制是期权到期时的展期再平衡流（做市商吸收看跌/看涨滚仓的库存压力），不需要新数据管线，是这个格子最便宜能测的候选，且能更快判断"近期（2024-2026）扣成本后夏普"是否达标。
- plan: |
    新建迭代 `h20260928_42_opex_week`，候选模块 `scripts/screen_batches/h20260928_42_opex_week.py`（纯函数 `weights_fn(close, asof) -> weights`，只读 `close.loc[:asof]`），候选清单 `reports/research/iterations/h20260928_42_opex_week/candidate-manifest.json`，`direction-review.json` 引用 `dir:option_expiration_week_calendar_effect`。

    来源与规则要点（已打开原文，非只读摘要）：
    - Quantpedia "Option-Expiration Week Effect"（https://quantpedia.com/strategies/option-expiration-week-effect）：只做多，持有 S&P 100 大盘股在含第三个星期五的那一周，其余持现金；1988-2010 年化 9.3%、夏普 0.61、最大回撤 -15.14%——样本老，本地测试就是决定性否定测试。
    - Garcia-Ares & Muravyev 2025（FMA working paper，https://www.fma.org/assets/docs/Derivatives2025/GarciaAres.pdf）：期权到期相关的收益异象集中在"第三个星期五+次周一"两天窗口，由展期造成的订单失衡驱动，样本较新（研究的是期权收益，不是股票方向收益，只作为机制近期仍在起作用的旁证，不直接确认 Quantpedia 的夏普数字）。

    `freq="D"`，用 `signal_dates_fn` 把评估限制在到期周的交易日（docstring 里日历锚定规则的标准写法，没有调仓日偏移问题）。
    网格（8 个候选，`OPEX_{TICKER}_{WEEK,WEEKMON}`）：标的 {SPY, QQQ, DIA, IWM}（S&P 100 大盘股的流动性代理，全部 Alpaca 可交易） × 窗口 {仅到期周（周一至周五）, 到期周+次周一}。
    **必须加安慰剂对照**：同一批候选清单里加入"随机选一个非到期周"的对照版本（例如每月第 1/2/4 周），验证"第三个星期五"不是碰巧选中的日子（这是冻结合同 G3 之外，针对这条规则数据挖掘风险的额外内部否证）。
    判定：K1 为主路径（偏移中位数——注意 D 频率无偏移可选，按 docstring 只有一个版本——夏普对标窗 ≥1.19、压力期 ≥0.65，20bp 下两窗年化为正）；8 个候选（不含安慰剂对照）算一族，报告 DSR。
    `uv run oc research direction-check <path>` 和 `uv run oc research iteration validate h20260928_42_opex_week --stage pre-backtest` 通过后跑 `uv run python scripts/screen_batch.py --batch h20260928_42_opex_week --iteration h20260928_42_opex_week`；SPY/QQQ/DIA/IWM 已在本地面板。`--stage final` 通过后更新登记簿和覆盖地图。
- done_when: 迭代 `--stage final` 通过；8 个候选（含安慰剂对照结果）都有 K1/K2 判定和 DSR；`dir:option_expiration_week_calendar_effect` 从 queued 更新为终态并带 verdict、evidence、reopen_if。
- notes:
  - 2026-09-28 22:21 UTC 自动轮缺口搜索添加。
  - 2026-09-29 01:07 UTC 自动轮开始，派 sonnet-high 子代理执行。
  - 2026-09-29 结果（协调者已对照 leaderboard.json 逐条核对 20 条）：否定，0/8。8 个主候选对标窗偏移夏普全为负（最好 OPEX_IWM_WEEKMON −0.18，门槛 1.19），压力期最好 0.04；K2 增量两窗全负。安慰剂反而更好：第 2 个星期五那周 QQQ 对标窗 +1.15、SPY +0.86，第三个星期五没有正向特殊性。主候选 DSR 最高 0.01。登记簿 `dir:option_expiration_week_calendar_effect` refuted。产物：`reports/research/iterations/h20260928_42_opex_week/`、`reports/research/screens/h20260928_42_opex_week/`。

### T-20260928-43 批量筛选：国会/政治交易复制型 ETF 轮动（NANC/GOP/MAGA/DEMZ，公开实盘记录可复制）
- status: done
- priority: 2
- not_before:
- goal: 缺口搜索覆盖地图 `public_records.copy_verified_live` 格子（此前搜索发现 Collective2/Kinfo 被封锁或没有可复制规则，见该格子 `gap` 字段）。本次找到一个新的、规则公开、有代码可读的替代：几只跟踪国会议员/政党捐款人公开披露交易的 ETF（NANC、GOP、MAGA、DEMZ）自 2023-02 起已实盘运行，本地 SIP 日线面板已有 2024-01 起的完整数据。用同一套已验证的跨截面轮动引擎测试在这些标的间轮动，能不能扣成本后达到近期夏普标准——比重新爬国会披露原始数据便宜得多。
- plan: |
    新建迭代 `h20260928_43_political_etf_rotation`，候选模块 `scripts/screen_batches/h20260928_43_political_etf_rotation.py`，直接复用 `scripts/run_h20260918_05_recent_menu.py:rotation_cell`（和 T-20260928-40 相同引擎，只换 `MENU=[NANC,GOP,MAGA,DEMZ]+现金`），候选清单 `reports/research/iterations/h20260928_43_political_etf_rotation/candidate-manifest.json`，`direction-review.json` 引用 `dir:congressional_political_trade_replica_etf_rotation`。

    来源与规则要点（已打开原文）：
    - bit.com 知识库"Congressional Trade Tracking"（https://www.bit.com/knowledge-hub/congressional-trade-tracking）：STOCK Act 要求国会议员 30-45 天内披露交易；NANC（Unusual Whales 民主党复制 ETF）等已是"受监管、交易所上市的基金"；同时指出披露延迟可能已让市场部分消化信息优势。
    - 24/7 Wall St（2026-04-20，https://247wallst.com/investing/2026/04/20/if-you-invested-in-these-congressional-trading-etfs-at-launch-heres-what-youd-have-today/）：自 2023-02-07 发行以来到 2026-04，NANC 总回报 88.49%（跑赢标普 500 的 74.70%），GOP 64.31%（跑输）；文章明确给出反面证据——质疑 NANC 的超额收益"是科技股集中持仓的意外结果，不是真正的信息优势"（NVDA 9.0%、MSFT 7.6%、AMZN 5.2% 等），且有国会禁止交易立法的监管风险。

    网格（12 个候选，`POLITICAL_L{63,126,252}_N{1,2}_{MO,WK}`）：回看 {63,126,252} 日 × 排名前 N {1,2} × 调仓 {月度,周度}，和 S1-S3 相同的绝对动量过滤 + 排名前 N 逻辑。
    **额外要求**（这批标的成交量薄，2024 年样本日均几千股）：除标准 10bp/20bp 外，加一档更宽价差（30-50bp，按最小可观测量级估算）的敏感性测试；候选清单里加一个"用 NANC 实际持仓集中度（大盘科技股为主）构造的动量安慰剂"，检验收益是不是单纯科技股动量而非"政治复制"框架本身。
    **样本期短**：本地面板 NANC/GOP/MAGA/DEMZ 只从 2024-01 起（约 2.7 年），完全没有 2016-2023 压力期覆盖。按手册"数据不覆盖压力期用现有部分（至少 2 年）"的规则，只按选择窗+对标窗判 K1/K2，标注"待补压力期"，不得用 2026 年那段当干净留出窗（基金自身 2024-25 的已实现收益就是上面来源数字的来源）。
    `uv run oc research direction-check <path>` 和 `--stage pre-backtest` 通过后跑 `uv run python scripts/screen_batch.py --batch h20260928_43_political_etf_rotation --iteration h20260928_43_political_etf_rotation`（4 只标的已在本地面板，见 `data/sip/daily/_LAYOUT.json` 的 shard 0201/0128/0182/0077）。`--stage final` 通过后更新登记簿和覆盖地图，报告是否通过流动性/价差敏感性测试。
- done_when: 迭代 `--stage final` 通过；12 个候选都有 K1/K2（选择窗+对标窗，压力期标注待补）判定和 DSR；宽价差敏感性和科技动量安慰剂结果都报告；`dir:congressional_political_trade_replica_etf_rotation` 更新为终态。
- notes:
  - 2026-09-28 22:21 UTC 自动轮缺口搜索添加。
  - 2026-09-29 01:4x UTC 自动轮开始，派 sonnet-high 子代理执行。
  - 2026-09-29 结果（协调者已对照 leaderboard.json 核对 24 条）：否定，0/12 主候选。最好 POLITICAL_L252_N1_MO 对标窗 0.90、选择窗 0.89（门槛 1.19），DSR 0.31；K2 对标窗增量 −0.18 到 −0.45。实际首个交易日：NANC/GOP 2023-02-07、MAGA 2017-09、DEMZ 2020-11（队列里写的"2024-01 起"不准）。大盘科技安慰剂最好 0.91，和政治菜单差不多，说明这套轮动在这 4 只上没有增量。40bp 敏感性未触发。登记簿 refuted。产物：`reports/research/iterations/h20260928_43_political_etf_rotation/`。

### T-20260928-44 批量筛选：ETF 对相对强弱切换（只做多版本的 pairs/相对价值）
- status: done
- priority: 3
- not_before:
- goal: 缺口搜索覆盖地图 `relative_value.pairs_stat_arb` 格子（`gap` 字段明确写"只做多的一腿从未单独测过"）。用同一套已验证的跨截面轮动引擎（菜单大小=2、排名前 1）在若干高相关 ETF 对之间做相对强弱二选一切换，不需要协整/残差建模、不需要做空权限，是这个格子最便宜的决定性测试。
- plan: |
    新建迭代 `h20260928_44_etf_pair_switch`，候选模块 `scripts/screen_batches/h20260928_44_etf_pair_switch.py`，复用 `rotation_cell`（MENU=每对 2 只标的，top_n=1），候选清单 `reports/research/iterations/h20260928_44_etf_pair_switch/candidate-manifest.json`，`direction-review.json` 引用 `dir:etf_pair_relative_strength_switch`。

    来源（已打开原文）：QuantConnect 论坛帖子"QQQ/SPY Momentum Rotation System"（https://www.quantconnect.com/forum/discussion/19216/qqq-spy-momentum-rotation-system/，作者 Robert Lemois）：20 日相对动量、QQQ 偏置 +1.0%、切换阈值 0.5%、每 5 个交易日调仓；2010-2024 回测 CAGR 19.02%、夏普约 0.8（作者估计）、最大回撤约 30%（COVID）。证据弱：单一作者、平台工作人员在同帖指出代码有 bug（未终止字符串、计数器提前递增等），没有其他人复现或给出样本外/实盘数字——不算证实，但也没被反面证据否定，用作"机制合理、成本几乎为零"的候选来源，不借用其具体数字。

    网格（12 个候选，`PAIR_{A}{B}_L{63,126}_MO`）：6 对 × 回看 {63,126} 日，月度调仓，沿用 S1-S3 的绝对动量过滤（两腿都跌破现金基准时持现金）：
    - QQQ/SPY（来源直接测试的这一对）
    - SMH/QQQ、XLE/XOP、KRE/XLF、IWM/SPY、ARKK/QQQ（同类高相关行业内/风格内配对，覆盖地图未测过的扩展）
    判定：K1（对标窗+压力期，全部 6 对标的本地面板有完整 2016 年起历史，无短样本问题）为主路径；12 个候选算一族报告 DSR；安慰剂：50/50 固定混合两腿的版本作为对照（检验切换本身是否比静态混合更好）。
    `uv run oc research direction-check <path>` 和 `--stage pre-backtest` 通过后跑 `uv run python scripts/screen_batch.py --batch h20260928_44_etf_pair_switch --iteration h20260928_44_etf_pair_switch`；全部标的已在本地面板。`--stage final` 通过后更新登记簿和覆盖地图。
- done_when: 迭代 `--stage final` 通过；12 个候选（含 50/50 混合安慰剂）都有 K1/K2 判定和 DSR；`dir:etf_pair_relative_strength_switch` 更新为终态。
- notes:
  - 2026-09-28 22:21 UTC 自动轮缺口搜索添加。
  - 2026-09-29 01:4x UTC 自动轮开始，派 sonnet-high 子代理执行。
  - 2026-09-29 结果（协调者已对照 leaderboard.json 核对 18 条）：否定，0/12。只有 PAIR_SMHQQQ_L63_MO 自身过 K1（对标窗 1.28、压力期 0.77），但预注册对照否证触发：静态 50/50 SMH+QQQ 压力期 0.89 更高，切换没有增量；其余 10 条对标窗 −0.05 到 0.58；K2 对标窗全负。DSR 最高 0.60。登记簿 refuted。产物：`reports/research/iterations/h20260928_44_etf_pair_switch/`。

### T-20260929-01 批量筛选：杠杆 ETF 收盘再平衡流引发的次日均值回归（SPY/QQQ/SMH，只做多）
- status: done
- priority: 2
- not_before:
- goal: 缺口搜索（`gap-search-2026-09-29-01`）覆盖地图 `flows_structural.rebalance_and_hedging_flows` 格子明确标记"LETF close-rebalancing flow ... 从未搜索"。机制：2x/3x 杠杆和反向 ETF 每天收盘前必须再平衡以维持目标杠杆比例，标的当日出现大幅波动时会产生方向已知、规模可估的收盘买卖盘，文献认为这会造成尾盘动量和次日均值回归。这是纯收盘价规则（不需要期权、AUM 或流量数据），只需要已在本地面板里的 SPY/QQQ/SMH 及其杠杆对，是这个格子最便宜能测的候选。
- plan: |
    新建迭代 `h20260929_01_letf_flow_reversal`，候选模块 `scripts/screen_batches/h20260929_01_letf_flow_reversal.py`（纯函数 `weights_fn(close, asof) -> weights`，只读 `close.loc[:asof]`，照抄 `h20260928_42_opex_week.py`/`h20260928_18_vix_putw.py` 的写法），候选清单 `reports/research/iterations/h20260929_01_letf_flow_reversal/candidate-manifest.json`，`direction-review.json` 引用 `dir:letf_close_rebalancing_flow_reversal`。

    来源与规则要点（已打开原文，非只读摘要）：
    - Lenkey (2024)，"The market impact of leveraged ETFs: A Survey of the literature"，Quantitative Finance and Economics（开放获取，http://www.aimspress.com/article/doi/10.3934/QFE.2024031，已用 WebFetch 读全文）：文献"一致报告 ETF 再平衡需求与尾盘收益/波动率之间存在统计显著的关联"，但"现有大多数论文存在潜在的严重方法论错误，经济意义上的关联看起来并不显著"；总体结论是"政策制定者等提出的担忧没有得到整体经验证据的支持"。机制是机械性的（不是行为偏差），所以理论上不该像日历效应一样被套利消失；但来源本身认为经济幅度小——这是一个"值得测但预期偏弱"的候选，不是强先验。同一次搜索找到的其他论文（Ivanov & Lenkey、SFI working paper、一篇 2021 FMA PDF、一篇 2016 REPEC 条目）未能打开全文（PDF 读取失败/付费墙），不作为独立引用来源，只在 direction 的 notes 里提及。

    **只做股票/指数类杠杆 ETF，不做跨资产**：标的限定 SPY、QQQ、SMH（未加杠杆）及其对应 3x 产品 UPRO/SPXU、TQQQ/SQQQ、SOXL/SOXS（均已确认在本地面板 `data/sip/daily/_LAYOUT.json`，分片 0278/0243/0275/0305/0278/0296/0278/0275/0275）。**明确排除** TMF/TMV（债券杠杆）和 UVXY/SVXY（波动率产品），避免触碰机主否决的跨资产边界。

    规则：某标的（SPY/QQQ/SMH）在收盘时，若"今日收盘价相对昨日收盘的涨跌幅"（或其对应 3x 产品当日涨跌幅，作为再平衡流规模的更直接代理）的绝对值 >= 阈值，则次日开盘买入该标的、持有 N 个交易日，否则持有现金。
    网格：3 个标的 x 2 种信号来源（自身收益 vs 3x 对应产品收益）x 3 个阈值 {1.5%, 2%, 3%}（文献中常用的"大幅波动日"分界）x 2 个持有期 {1, 3 个交易日} = 36 个候选，若检查后自身/3x代理两种信号高度重合可预注册收窄到 <=18 个（在 candidate-manifest.json 里写清楚精简理由，精简须在跑批之前做，不能看结果后再删）。**必须加安慰剂对照**：同样触发频率下随机选择交易日持有的对照版本（不是真的大幅波动日），检验"大幅波动日"本身是否比随机进场更好（冻结合同 G3 之外的内部否证，因为"大幅波动"是有数据挖掘风险的阈值选择）。

    `uv run oc research direction-check <path>` 和 `uv run oc research iteration validate h20260929_01_letf_flow_reversal --stage pre-backtest` 通过后跑 `uv run python scripts/screen_batch.py --batch h20260929_01_letf_flow_reversal --iteration h20260929_01_letf_flow_reversal`（全部标的已在本地面板，无需取数）。判定：K1 为主路径（偏移中位数夏普对标窗 >=1.19、压力期 >=0.65，20bp 下两窗年化为正）；K2 为备选（和 S3 组合增量 >=0.05，两窗都成立）；候选族（不含安慰剂对照）报告 DSR。`--stage final` 通过后更新登记簿 `dir:letf_close_rebalancing_flow_reversal` 和覆盖地图 `flows_structural.rebalance_and_hedging_flows`。
- done_when: 迭代 `--stage final` 通过；每个候选（含安慰剂对照结果）都有 K1/K2 判定和 DSR；`dir:letf_close_rebalancing_flow_reversal` 从 queued 更新为终态并带 verdict、evidence、reopen_if。
- notes:
  - 2026-09-29 gap search (`gap-search-2026-09-29-01`) 添加。
  - 2026-09-29 02:1x UTC 协调者合并入队并修订（执行时以本条为准，覆盖上面 plan 中冲突的部分）：(1) 只做多的"次日回归"只在**下跌**日成立（大跌日杠杆 ETF 收盘卖出，次日反弹），所以信号改为"当日收益 ≤ −阈值"，不用绝对值；(2) 3x 产品当日收益 ≈ 3 × 标的收益，两种信号来源是重复维度，删掉，只用标的自身收益；网格改为 {SPY,QQQ,SMH} × 阈值 {2%,3%} × 持有 {1,3} 天 = 12 个 `LETF_{T}_D{2,3}_H{1,3}`，另加 3 个同频率随机日安慰剂（按日期哈希的确定性伪随机，每个标的一个，频率取 D2_H1 的历史触发率）；(3) 和 `reports/research/iterations/h20260924_01_etf_dip_reversion/` 重叠（6 条已发表的 ETF 抄底规则，当时只按旧 G1/G1' 判，最好对标窗夏普 1.50、同收盘成交），先读它的 decision-record，在 direction-review 写清差异；同一批里把它的 6 条规则在 SPY、QQQ 1x 上按本合同（次日开盘成交）重判 K1/K2，12 个 `DIP_{rule}_{SPY,QQQ}`，全批 27 个，DSR 按 27 报。
  - 2026-09-29 04:1x UTC 自动轮开始，派 sonnet-high 子代理执行（按上面 02:1x 修订的 27 候选网格）。
  - 2026-09-29 04:07 轮结果（协调者已对照两个 leaderboard.json 逐条核对 27 条）：否定，0/27，无近期观察。因迭代校验器单条路径最多 24 个候选，拆成两个迭代：`h20260929_01_letf_flow_reversal`（12+3 安慰剂）和 `h20260929_01_dip_rejudge`（12）。LETF 最好 LETF_SMH_D2_H1 对标窗 0.80、压力期 −0.26；大跌日进场在三个标的上都好于同频随机日安慰剂（SMH 0.80 对 −0.24），方向成立但幅度远不够；K2 两窗全负。抄底重判最好 DIP_D1_SPY 对标窗 1.13（门槛 1.19）、压力期 0.53，K2 对标窗 +0.15 但压力期 −0.13。27 条合并 DSR 最高 0.39。登记簿 `dir:letf_close_rebalancing_flow_reversal` refuted，`dir:etf_dip_reversion_ibs_connors` 追加 K1/K2 重判。产物：`reports/research/iterations/h20260929_01_{letf_flow_reversal,dip_rejudge}/`、`reports/research/screens/h20260929_01_*`。

### T-20260929-02 节前效应在小盘/低流动性股票层面的复现（signal_card 事件模式，不需要新数据）
- status: done
- priority: 2
- not_before:
- goal: 缺口搜索覆盖地图 `flows_structural.calendar_and_fomc` 格子表面写"harvested, not tested"，但逐条查过登记簿后发现月末反转、板块季节性、pre-FOMC drift、turn-of-month 都已经测过并有结论（不要重复）。本任务找到一个该格子确实没测过的子方向：Ariel (1990) 的经典"节前溢价"效应，被后续复现研究发现在样本外（1983-2019）"只在小盘股里还存在，大盘股的溢价已基本消失"。机主 2026-09-28 明确说小盘/低流动性股票可以做（按价差建成本），这个候选正好落在这个偏好里，且能直接复用已有的股票层面信号评估工具（`open_composer/research/signal_card.py` 的 event 模式），不需要新数据管线。
- plan: |
    来源与规则要点（已打开摘要，非只读搜索片段）：
    - "The Pre-Holiday Premium of Ariel (1990) Has Largely Become A Small-Firm Effect Out of Sample"（https://exa.ai/library/publication/k47n5zm6fft，同一篇也见 https://www.nowpublishers.com/article/Details/CFR-0111，已用 WebFetch 读摘要）：Ariel (1990) 发现节前交易日的市场指数收益是平常的"9 到 14 倍"；本复现把样本延长到 1983-2019，发现节前溢价"现在只在小盘股中存在"，大盘股的溢价"已基本消失，尤其是 1990 年后"。只读到摘要（全文在付费墙/Exa API 后面），没有具体的 bps/百分比数字或显著性水平，判定只能用方向性结论，不能用具体数字做预注册目标。另有一篇 2026 年新论文（Apergis, "Abnormal returns and stock performance prior and after federal holidays", Review of Financial Economics）搜到但 WebFetch 返回 403，没有读到内容，不作为证据引用，只在 direction 的 notes 里标注避免下次盲目重试同一个付费墙。

    工具：直接用 `open_composer/research/signal_card.py` 的 `--mode event`（已内置 t1 1-500 / t2 501-1500 / t3 1501-top_n 三档按美元 ADV 分层、10bp/20bp 成本、`redate_events` 内置安慰剂——把每个事件在同一只股票上随机移动 ±126 个交易日，满足冻结合同 G3 式的内部否证要求，不需要额外写代码）。

    信号构造：事件日期 = 每个联邦市场假日休市前 2 个交易日（这样次日开盘买入正好落在假日前一个交易日，持有 h 个交易日捕捉"节前效应"文献衡量的那一段）。假日日期**不引入新数据源**：直接从已有收盘面板自身的交易日历推导（"哪些交易日之后出现了一个不能用周末解释的多日缺口"），和 `scripts/screen_batches/h20260928_42_opex_week.py` 处理"第三个星期五"日历锚点用的是同一套"已知交易日历，不是价格穿越"的约定（该脚本的 docstring 有详细说明，照抄它的日历推导方式）。构造一张 `symbol, trade_date, value=1` 的表：对 universe_broad 里每只股票，在每个符合条件的 formation date 上都置 1（同一天所有股票拿到同样的事件——这是市场层面的日历事件，不是个股特征，signal_card 的 event 模式天然支持"同一天很多只股票同时触发"）。

    两次独立跑（或一次跑两个 `--sql`/`--where` 变体）：`pre_holiday_t1`（限定 t1 tier 股票，机制预期里"已消失"的对照组）和 `pre_holiday_t3`（限定 t3 tier 股票，机制预期里"仍然存在"的目标组），`--primary-horizon 5`。用 `run_capped.sh --mem 1.8G --` 跑（signal_card 会读整张 universe_broad 面板）。

    判定（signal_card 自带的"信号是否被采纳"标准，不是策略级 K1/K2——按其 docstring，单个信号不适用策略门槛）：读 `card["flags"]` 的四项 `car_t_ge_3`、`beats_redated`（内置安慰剂）、`book_positive_20bp`、`book_positive_20bp_recent`。t3 全部为真且 t1 不全为真才算"信号采纳，和来源的小盘专属结论一致"；否则按对应结论否定或标记证据不足。
- done_when: `pre_holiday_t1` 和 `pre_holiday_t3` 两张 signal card 都生成在 `reports/research/signal-cards/`；`dir:pre_holiday_effect_small_cap_tier` 从 queued 更新为终态（admitted/refuted/evidence_too_weak）并带 verdict、evidence（signal card 路径）、reopen_if；结论要写清楚 t1 与 t3 是否复现了来源的"只在小盘股"模式。
- notes:
  - 2026-09-29 gap search (`gap-search-2026-09-29-01`) 添加。
  - 2026-09-29 02:1x UTC 协调者合并入队并修订（执行时以本条为准）：signal_card 的超额收益是相对"全体股票等权"算的，节前这种全市场同一天的日历事件在 event 模式里会被抵消，只剩"小盘减全市场"的相对差，回答不了"节前持有能不能赚钱"。改为批量通道的 D 频率日历规则（照抄 `scripts/screen_batches/h20260928_42_opex_week.py` 的日历写法）：节前最后一个交易日前一天收盘发信号、次日开盘买入，持有 {1, 2} 个交易日后清仓；标的 {IWM, IJR, IWC, VB}（小盘/微盘，本地面板已有）+ {SPY, QQQ}（大盘对照，来源预期"已消失"）= 12 个 `PREHOL_{T}_H{1,2}`；安慰剂：每个标的一个"同样次数、随机非节前日"的确定性伪随机版本（6 个）。判定 K1/K2；另报告小盘组与大盘组对标窗夏普差是否为正（来源的"只在小盘"模式）。signal_card 的 t1/t3 对比只在批量结果为正时再做。
  - 2026-09-29 05:0x UTC 自动轮开始，派 sonnet-high 子代理执行（先做 T-41，再做本任务）。
  - 2026-09-29 04:07 轮断点（子代理先做 T-41 超时，停在这里）：已完成 `scripts/screen_batches/h20260929_02_pre_holiday_etf.py`（18 候选）和 `tests/test_h20260929_02_pre_holiday_etf.py`（11 个非 manifest 测试通过、lint 干净）；原文 Ko & Yang 2021 已读（`reports/research/iterations/h20260929_02_pre_holiday_etf/sources/`，确认"节前效应现在只在小盘股"）。**还没做**：candidate-manifest.json、direction-review.json 的正式内容、cost-contract、data-feasibility、pre-backtest 校验、跑批、登记簿 `dir:pre_holiday_effect_small_cap_tier`、coverage。下一步：补齐档案 → `uv run oc research direction-check …` → `iteration validate h20260929_02_pre_holiday_etf --stage pre-backtest` → `scripts/run_capped.sh --mem 1.8G -- uv run python scripts/screen_batch.py --batch h20260929_02_pre_holiday_etf --iteration h20260929_02_pre_holiday_etf`。模块在预注册前已写好但未跑任何结果，manifest 必须在跑批前写。

  - 2026-09-29 08:0x UTC 自动轮（07:07 轮）从断点续做，派 sonnet-high 子代理。
  - 2026-09-29 07:07 轮结果（协调者已对照 leaderboard.json 核对 18 条）：否定，0/12。12 个节前持有候选对标窗夏普全为负（最好 IWC_H1 −0.81），压力期全负；K2 全负。每年约 9 次、每次进出 4 笔 × 10bp ≈ 年 4% 成本，吃掉了节前溢价；同标的随机日安慰剂 10/12 反而更好。小盘组比大盘组对标窗中位数夏普高 0.32（方向与 Ko & Yang 2021 一致，但都亏）。登记簿 `dir:pre_holiday_effect_small_cap_tier` → refuted。产物：`reports/research/iterations/h20260929_02_pre_holiday_etf/`。
### T-20260929-10 VIX 双信号波动率风险溢价（Zarattini/Mele/Aziz，SSRN 5316487；只做多的 ETP 版本）
- status: done
- priority: 2
- not_before:
- goal: 机主 2026-09-29 放开"美股能买到的 ETF 都算"，`dir:vix_term_structure_short_vol` 的不可执行理由（没有 VX 期货）有了新信息：信号只要 VIX 和 VIX3M 两个指数（CBOE 免费、FRED 有 VIXCLS），QuantConnect 的独立复现用的是 ETP。检验只做多的版本，在对标窗和压力期能否过 K1，或者作为 S3 的搭配过 K2。
- plan: 先打开 SSRN 5316487 原文和 QuantConnect 复现页（2016-01 至 2026-07 夏普 0.729，SPY 0.582；25 组参数 0.713–0.773），记下信号定义和仓位规则。批量通道候选：信号一是 VIX 减 10 日已实现波动率；信号二是 VIX/VIX3M 的期限结构。空波动率时持有 SVXY（2018-02-27 起是 −0.5 倍），否则持有 SPY 或 SHY；仓位按 VIX/100 缩放，照原文。候选不超过 12 个，包含原文参数和 2–3 个邻近参数，加一个随机日期安慰剂。按运行手册第 5 节判定。另外报告和"一半 SMH、一半 QQQ 静态持有"的对比。2018-02 之前 SVXY 是 −1 倍，压力期要分段报告，或从 2018-03 起算并写明。
- done_when: 迭代 `--stage final` 通过；登记簿 `dir:vix_term_structure_short_vol` 追加新一行，写明重开理由和结论。
- notes:
  - 2026-09-29 交互会话添加（机主给的研究清单第 3 项）。
  - 2026-09-29 05:0x UTC 自动轮开始，派 sonnet-high 子代理执行。
  - 2026-09-29 04:07 轮结果（协调者已对照 leaderboard.json 核对 12 条）：否定，0/10 主候选、无近期观察。SSRN 原文 403 未读，信号按 QuantConnect 代码级复现写；原文参数版全样本夏普约 0.59（QC 报 0.729，差异来自 SVXY 1 倍权重、无 2% 不交易带）。对标窗最好 VVRP_SIG1ONLY_SHY 0.42（门槛 1.19）；压力期最好 0.90 但对标窗 −0.05；K2 对标窗全负。DSR ≤0.16。对照静态 50/50 SMH/QQQ 对标窗 1.20、压力期 0.89。注意压力期按 2016-05 起算（含 SVXY −1 倍时段），但对标窗已足以否定。登记簿 `dir:vix_term_structure_short_vol` 追加 refuted。产物：`reports/research/iterations/h20260929_10_vix_vrp_etp/`、`data/research/vix/VXVCLS.csv`。

### T-20260929-11 多季度盈余意外历史的线性模型（Kaczmarek & Zaremba 2025 FRL；ML 复活 PEAD）
- status: done
- priority: 2
- not_before:
- goal: 机主研究清单第 1 项。单季 SUE 在我们的数据上已否定（`dir:pead_xbrl_sue_filing_date`、`dir:pead_xbrl_8k_llm`），原文的新意是用过去多个季度的 SUE 序列训练 elastic net，并且说增益在大盘股里最强。检验它在我们的 SEC XBRL 数据上，是否比单季 SUE 和动量有增量。
- plan: 先打开原文（Finance Research Letters 2025）和 Wang 等（OR Spectrum 2025），记下特征、标签和样本外设计。特征用 `data/features/sec_fundamentals_daily` 的 sue_eps/sue_rev，按申报可见日取过去 8 个季度，加连续超预期次数。选择窗 2016-06→2023-12 训练 elastic net（时间序列交叉验证选正则），测试窗 2024-01→2026-09 只跑一次。报告测试 IC、前 50 只月度组合在 10/20bp 下的夏普、和单季 SUE 及 12-1 动量的对比，以及和 S3 的相关性。按运行手册第 5 节判定，另外报告扣掉 SPY/QQQ 贝塔之后的超额。
- done_when: 迭代 `--stage final` 通过；登记簿新增 `dir:ml_multiquarter_sue_history`。
- notes:
  - 2026-09-29 交互会话添加（机主给的研究清单第 1 项）。
  - 2026-09-29 13:40 UTC 自动轮开始，派 sonnet-high 子代理执行。
  - 2026-09-29 13:07 轮结果（协调者已对照 leaderboard.json 的 judged/dsr_anchor 核对）：否定。时间点 S&P 500 池，逐年扩展窗口 elastic net（样本外 2019–2026），8 季 sue_eps/sue_rev + 连续超预期次数。偏移中位数夏普（10bp）对标窗/压力期（2019–23，压力样本短）：ENET_TOP50 0.60/0.38、ENET_TOP20 0.37/0.47、ENET_MOM 0.83/0.32，基线 SUE1_TOP50 0.88/0.59、MOM12_1 1.10/0.43、池内等权 0.72/0.55，安慰剂 打乱标签 0.68/0.36、随机 0.51/0.50。K1/K2/近期观察全不过（K2 −0.11/−0.29），增量标准输给单季 SUE、动量和打乱标签安慰剂；RankIC 2019–23 −0.006、2024+ −0.009；8 个年度模型里 4 个被正则压成全零。DSR 0.32。原文全文 403，只读到摘要。注意：共享价格清洗默认参数把 FB 等 32 只改名前的历史清空，2019–21 池子不全（不影响结论，基线同样受影响）。登记簿 `dir:ml_multiquarter_sue_history` refuted。产物：`reports/research/iterations/h20260929_11_multiq_sue/`，模块提交 73e99f4、结果提交 4e84593。

### T-20260929-12 交互会话：股票层面因子集成 + 反向 ETF 对冲，能否成为 S3 的真分散化 sleeve
- status: cancelled
- priority: 1
- not_before:
- goal: 机主放开美股 ETF 后，检验"对冲后的因子集成"这个此前从未测过的组合——之前 dir:ml_ranking_liquid500_recent_vs_momentum_rule（多头 ML 排序）和 dir:baseline_chain_b0_b1_b2_market_neutral_vs_long（SPY beta 中性对冲）都已否定，但从未测过"用真实反向 ETF（SH/PSQ）对冲以求和 S3 去相关"这条路。
- plan: 迭代 `h20260929_12_hedged_factor_ensemble`。复用 T-15 已算好的 select-window ICIR 扫描（不重新算 IC），构建 5 个静态集成（E10/E20/E40/E20D/R40）x 4 种组合形式（多头 a、SH 对冲 b、PSQ 对冲 b'、信息用多空价差 c，不含决策权重）= 20 个候选格。复用 `scripts/screen_lane.py` 的 `s3_incumbent`/`combine_two_sleeves`/`diversifier_edge_for_offset`/`evaluate_offset_window`（原样导入，不改公式）。Stage 1（2024-01-02..2026-09-08）判定：对冲形式的分散化增量 >= +0.05、单独夏普 > 0、与 S3 相关性 < 0.3 才进 Stage 2（2018-2023 walk-forward 重选）。direction-review.json 已通过 `oc research direction-check`；`iteration validate --stage pre-backtest` 已通过（lightweight_single_mechanism_exemption 警告，非阻塞）。
- done_when: `iteration validate --stage final` 通过；登记簿新增 `dir:hedged_factor_ensemble_s3_diversifier`，写明 Stage 1（及 Stage 2 如有）判定、DSR、和每个候选格的数字来源文件。
- notes:
  - 2026-09-29 交互会话新增，队列 id T-20260929-12。
  - 2026-09-29 第一次修复：协调者复核发现首次 Stage 1 "通过" 因股票腿（forward 标签）与对冲腿/S3（ending 标签）错位一天而作废；修复后诊断 corr(SPY open-to-open, S3)=0.234，我误判为"S3 本身 beta 低，非 bug"并挂起。
  - 2026-09-29 第二次修复（协调者进一步复核，纠正了我上面的误判）：S3（`salvage.simulate`）实际是 close-to-close 口径（每次调仓日在开盘价拆分隔夜腿/日内腿），不是 open-to-open；协调者实测 corr(SPY close-to-close, S3)=0.58、corr(QQQ close-to-close, S3)=0.70。改写 `run_h20260929_12_hedged_books.py`/`build_h20260929_12_stage2_e20d.py`：新增 `stock_legs`/`simulate_book`/`build_hedged_book`（原样复刻 `salvage.legs`/`salvage.simulate` 的隔夜/日内拆分公式），每笔 book 直接落在 close-to-close 口径，不再需要 shift_rows 转换；`hedge_weight_series` 回看窗口相应改为含当天（因为 close-to-close 收益在当天收盘时已完全实现）。新增回归测试：`simulate_book`/`stock_legs` 直接对拍 `run_h20260922_05_salvage.simulate`/`.legs`（冻结引擎本身），而不是自造的"预期值"。
  - 重跑结果：`corr(SPY_cc,S3)=0.5784`、`corr(QQQ_cc,S3)=0.6985`，与协调者的独立实测数字精确吻合（0.58/0.70），证实口径修复正确。但 `corr(a,S3)>0.3` 五个集成里仍有四个未过（E10 0.2113、E20 0.1842、E40 0.0994、E20D 0.2166），只有 R40 通过（0.3856）；corr(a,SPY_cc) 和 beta(b,SPY_cc) 五个全部清楚通过。协调者原话把这个结果的应对方式讲清楚了："若仍不过，停下汇报数字"——按此执行，未再自行做第三次修复。`results.json` 未写出，Stage 1 判定和登记簿条目继续挂起。详见 `reports/research/iterations/h20260929_12_hedged_factor_ensemble/decision-record.md`。
  - 2026-09-29 05:42 UTC：机主在交互会话里停掉了执行代理，按取消处理，不再重启，除非机主要求。停止时的状态：日期对齐已修好（与 salvage.simulate 逐位一致，corr(a,SPY_cc)=0.69–0.84，对冲后 beta 0.02–0.05）；第一阶段的判定还没跑。第一次"通过"是日期错位造成的，已作废（results.VOID-alignment-bug-2026-09-29.json）。

### T-20260929-03 M&A 目标股公告后漂移（需先建一个免费 EDGAR 数据管道）
- status: done
- priority: 3
- not_before:
- goal: 缺口搜索（`gap-search-2026-09-29-04`）核实 `event.8k_item_events` 格子自己的 gap 字段写的"offerings, spin-offs, M&A never searched"是准确的（不是像日历格子那样的陈旧记录）——同一个 8-K 事件格子里其它子方向（回购公告、Item 4.02 财务重述、SEO/ATM 增发、分拆）都已判定 evidence_too_weak/not_executable，唯独并购目标股公告后漂移从未搜索过、也从未在本仓库测过。搜到一篇 2025-10-13 的工作论文（`https://exa.ai/library/publication/k3grbvwxkr8`，只读到摘要，Exa 库全文在付费墙后，判定为 claim_only 未独立核实）：用新闻覆盖度、公告前成交量、交易类型（现金/换股）预测并购目标股公告后 30 天的收益，作者声称扣成本后夏普可超过 2.1（方法、样本、具体窗口都没读到，只能当方向性线索，不能当预注册的目标数字）。另一篇 1992-2021 年美国样本（51,780 个并购/公司行动事件，`https://ideas.repec.org/p/usi/wpaper/920.html`，同样只读到摘要）发现小盘并购目标股的超额收益主要在公告**之前**（信息提前泄露/分析师覆盖不足所致），提醒我们能交易的公告**之后**窗口可能比论文摘要暗示的要小。机制和已测过的所有 8-K 子方向（回购、Item 4.02、SEO/ATM、分拆）都不同，且是长仓可执行（买目标股，不需要卖空收购方或裸卖空）。
- plan: |
    **第一步（数据管道，免费，一次性）**：本地没有任何并购交易列表数据源（`capabilities/registry.yaml` 里没有 M&A 相关 capability；`data/features/` 下没有并购数据）。用 SEC EDGAR 全文检索 API（免费，无需密钥）：`https://efts.sec.gov/LATEST/search-index?q=%22Agreement+and+Plan+of+Merger%22&forms=8-K&dateRange=custom&startdt=2016-01-01&enddt=2026-09-29`（按年分页，每页最多 10 条需翻页；也可以退到季度全文索引 `https://www.sec.gov/Archives/edgar/full-index/{yyyy}/QTR{n}/form.idx` 过滤 `form=8-K` 后按关键词扫正文，作为交叉核对）。写 `scripts/collect_sec_ma_target_announcements.py`（照抄 `scripts/collect_sec_insider_transactions.py` 的结构和限速处理），产出 `data/features/sec_8k_ma_announcements/`：字段至少 `symbol, filing_date(visible_at), cik, item_codes, deal_type(cash/stock/mixed，若能从正文关键词判断; 否则留空)`。**不确认交易完成状态（是否成功交割）是否能免费拿到**——若拿不到，本任务只测"公告后固定期限持有"（不依赖完成状态），不测"持有到交割"版本，在 direction 的 notes 里如实记录。
    抽样核对：抓取后随机读 20-30 条正文，确认关键词"Agreement and Plan of Merger"命中的确实是标的公司自己被收购（不是标的公司作为收购方，需要用 8-K 正文里"Company"和交易对手的主谓关系粗判，或者用现成的"Subject Company"字段）；如果误判率明显高（类似 13G 那次 14% 的教训），如实记录并按比例打折信号强度或转 `blocked_data`。
    **第二步（信号检验，数据管道跑通后再做）**：新建迭代 `h20260929_03_ma_target_drift`，`direction-review.json` 引用 `dir:merger_arbitrage_target_announcement_drift`。用 `open_composer.research.signal_card` `--mode event`：`--sql` 从新建的 `data/features/sec_8k_ma_announcements` 取 `symbol, trade_date=filing_date, value=1`（entry 在 filing_date 后下一个交易日开盘，`signal_card` 自带的 next-open 对齐已经处理），`--primary-horizon 20`（对应论文摘要的"30 天"里最接近的内置选项；另跑一次不带 `--primary-horizon`（用默认 20）对照 60 日持有），跑两个变体：`ma_target_all`（全部标的）和 `ma_target_t3`（限定 t3 小盘/低流动性档，呼应机主"小盘可以做"的偏好，也是size-effect 论文提示信息滞后可能更小的那一档——但也要小心公告前已经涨了一截，用 redate 安慰剂能部分控制这个）。用 `run_capped.sh --mem 1.8G --` 跑（signal_card 读整张 universe_broad 面板）。
    判定：读 `card["flags"]` 的四项（`car_t_ge_3`、`beats_redated`（内置把事件在同一只股票上随机移动 ±126 交易日的安慰剂）、`book_positive_20bp`、`book_positive_20bp_recent`）。四项全真才算"信号采纳"；否则按 signal_card 自己的 admit/reject/evidence_too_weak 逻辑走。这一步只是股票层面信号库准入检验，不是策略级 K1/K2（`open_composer/research/signal_card.py` docstring 明确单个信号不适用策略门槛）；若信号被采纳，再决定是否值得单独建一个策略级批量任务。
- done_when: `data/features/sec_8k_ma_announcements` 建好并有抽样核对记录（误判率数字）；`ma_target_all`、`ma_target_t3` 两张 signal card 都生成在 `reports/research/signal-cards/`；`dir:merger_arbitrage_target_announcement_drift` 从 queued 更新为终态（admitted/refuted/evidence_too_weak/blocked_data）并带 verdict、evidence（signal card 路径 + 数据管道抽样核对结果）、reopen_if；若数据管道本身建不成（EDGAR 限速或 Item 1.01 无法可靠识别），直接标 `blocked_data`，不勉强跑后半段。
- notes:
  - 2026-09-29 gap search (`gap-search-2026-09-29-04`) 添加。
  - not_before 设到 2026-10-01：这是一个新数据管道任务，不需要 DeepSeek 打分，但涉及新脚本和抽样核对，按惯例给协调者一天余量排期；也避免和当前排队中的其它数据管道任务（如 T-20260928-16/-17 的打分通道）抢注意力。
  - **待机主决定**：如果最终发现交易完成/交割状态无法免费获取，"持有到交割"版本的并购套利（更接近论文摘要里 Sharpe>2.1 的那种设计）就做不了，只能做"固定期限持有"这个更弱的版本——这不需要机主现在决定，只在测完第一步再报告。
  - 2026-09-29 04:07 轮协调者合并入队：改为 ready、priority 3、去掉 not_before——免费 EDGAR 数据管道不需要机主决定，不算 blocked；摘要里 Sharpe>2.1 未读全文，只当弱先验。
  - 2026-09-29 19:07 UTC 自动轮（d1ed2d06）开始，派 sonnet-high 子代理执行（先建 EDGAR 管道，重计算步骤与 T-37 用 flock 串行）。
  - 2026-09-29 19:07 轮结果（协调者已核对四张卡的 flags）：refuted。免费 EDGAR 全文检索管道：11,415 条 Item 1.01 候选 8-K，1,484 个首次目标公告（2016–2026，每年 88–176 个），映射到代码 94.5%，25 条抽样误判 8%；可交易池内 576 个。四张卡（all/t3 × 20/60 日）flags 相同：car_t_ge_3 否、book_positive_20bp 否、2024 起否（beats_redated 为真只因真实 CAR 低于全部安慰剂）。ma_target_all 次日开盘入场后 20 日 CAR −0.75%（t −2.36），20bp 账本 −16.2%/年。溢价在入场前就兑现：公告前 5 日 +5.69%、公告日 +16.95%。持有到交割/按报价差的版本需要交割状态和报价，免费拿不到，未做。产物 `data/features/sec_8k_ma_announcements/`、`reports/research/iterations/h20260929_03_ma_target_drift/`、`reports/research/signal-cards/ma_target_*.json`。

### T-20260929-04 内部人集群买入：补测 H-20260916-08 唯一还空着的精确设计（top-500 池、周频）
- status: done
- priority: 3
- not_before:
- goal: 登记簿里 `dir:insider_cluster_buy_top500` 明确写着"top-500/周频这个精确设计仍未测试"（`H-20260916-08`，2026-09-16 立项后一直排在其它卡片后面、预算 3 用了 0）。这是内部人集群买入方向里唯一还留白的精确 scope；两头都已经关闭：作为事件特征已采纳但很小（CAR +0.78%/20 日，t=5.0；`reports/research/signal-cards/insider_cluster_buy.md`），作为全池月频独立策略在 1501+ 档已被否定（跑输同波动 SPY，`dir:insider_buy_independent_broad_universe`）。**预期不高**——两头都已经不理想，周频换手只会加成本——排这个任务主要是花几分钟把登记簿这最后一条空白关掉，不是一个有前景的新线索。不需要新数据，直接复用已有 Form 4 特征和 `signal_card.py`。
- plan: |
    直接用 `open_composer.research.signal_card` `--mode event`：`--source` 指向 `data/features/insider`（或 `insider_broad`，两者都已确认存在且覆盖到 2026），`--column` 用 `buyers_60d`（或等价的集群买入计数列，跑之前先 `python3 -c "import pandas as pd; print(pd.read_parquet(...).columns)"` 核对实际列名），`--where`/`--sql` 限定 `top_n=500`（H-20260916-08 原始设计的 top-500 池）、事件定义为 `buyers_60d>=2`，信号日期为每周五（周频，照抄 H-20260916-08 卡片里"weekly, top-500 pool, equal-weight up to 30 names"的设计，不要改成月频或改变阈值）。`--primary-horizon 20`（约等于原设计的持有期，若原卡片写的是不同持有期，以卡片为准并在结果里注明与卡片一致）。数据量小（只是 top-500 池的事件表 + 已有 insider 特征），本机内存放得下，不需要 `run_capped.sh`。
    判定：同 T-20260929-03，读 `card["flags"]` 四项；因为已有两个非常接近的变体都失败，这次结果无论真假都应该直接写成对整个 `insider_cluster_buy_independent` 家族的收尾判断（不要因为"万一这次不一样"而放宽判定标准或加做变体）。
- done_when: signal card 生成在 `reports/research/signal-cards/`；`dir:insider_cluster_buy_top500` 和新建的 `dir:insider_cluster_buy_top500_weekly_independent` 都从 queued/partial 更新为终态，带 verdict、evidence、reopen_if；在 `current-view.zh.md` 的下一次更新里注明"内部人集群买入方向的三个 scope（事件特征、月频全池、周频 top500）已全部有定论"。
- notes:
  - 2026-09-29 gap search (`gap-search-2026-09-29-04`) 添加。
  - 2026-09-29 16:30 UTC 自动轮（a42b6bb7）开始，派 sonnet-high 子代理执行。
  - 2026-09-29 16:30 轮结果（协调者已核对 card JSON）：否定。top-500（按月末时间点成交额排名）、每周最后一个交易日、buyers_60d≥2、次日开盘进、持有 20 日；9,352 个事件、381 只股票。flags：car_t_ge_3 假、beats_redated 真、book_positive_20bp 真、book_positive_20bp_recent 假，四项不全真。CAR(20 日) +0.15%、t 0.78、胜率 47.7%，2024 起 −0.73%；20bp 账本对全池超额 ≈0，2024 起 −11.9%/年。与卡片差异：事件模式无 30 只上限、无去重、无 BIL 填充。内部人集群买入三个 scope（事件特征小但采纳、月频全池否定、周频 top-500 否定）全部有定论。产物 `reports/research/signal-cards/insider_cluster_buy_top500_weekly.{json,md}`。

### T-20260929-21 交互会话：IPO 解禁期漂移（Field & Hanka 2001；做空 easy-to-borrow + 保守借券成本）
- status: done
- priority: 1
- not_before:
- goal: 机主要短时间线、少出手、高胜率高收益的事件策略。情报简报 I-20260929-01 §2.3/§4 定位 IPO 解禁期（IPO 后约 180 天内部人可自由卖出）：Field & Hanka (2001, JF) CAR 约 -1% 到 -3%。本任务建 PIT 事件表（SEC EDGAR 424B4 优先，本地首个交易日兜底）、预注册 ≤24 候选（含 2024-01-08→2026-09-17 TEST、2016-05-02→2023-09-15 STRESS、日期平移±60会话与随机日期安慰剂、2× 成本）、跑 close-to-close 日历组合账本、判定。
- plan: |
    迭代 `h20260929_21_ipo_lockup_expiry`。脚本 `scripts/build_h20260929_21_lockups.py`（EDGAR 424B4 事件表，复用 `scripts/collect_sec_13d_filings.py` 的 `SecClient`/`load_company_tickers`/限速与 User-Agent 约定，季度 `form.idx` 兜底扫描）、`scripts/run_h20260929_21_lockup_books.py`（日历组合账本）。测试 `tests/test_h20260929_21_lockup.py`。成本：分层 spread（top500 3bp/500-1000 6bp/1000-1500 12bp/1500+ 25bp）+ 借券 top1500 年化3%、1500+ 年化25%，另报 2× 成本。判定：TEST 最佳预注册格 calendar Sharpe >= 1.19 或与 S3 组合边际 >= +0.05，胜过日期平移安慰剂（t>=2），扛住 2× 成本；TEST 事件数 <40 则判"证据不足"，转由 STRESS window 定方向状态。DSR 用完整候选数。
- done_when: `oc research direction-check` 和 `iteration validate --stage pre-backtest`（预注册后）、`--stage final`（结果后）都通过；`results.json`+`report.md` 含中文摘要表（胜率/单笔均收益/年化事件数/最差交易/夏普/与S3相关性）；登记簿更新既有 `dir:ipo_lockup_expiration_drift` 行（status harvested → 终态）；`directions validate` 通过；本队列块改 done 并写两行结果。
- notes:
  - 2026-09-29 交互会话新增，队列 id T-20260929-21。
  - 联网证据（本次已开原文/PDF，非仅摘要）：Field & Hanka (2001 JF, SSRN 205011，registry 摘要)：1,948-3,217 份解禁协议，3日CAR约-1.5%~-1.8%，VC背景更强，效应十年样本内稳定不被快速修正。Gibbs & Hao (2018 JBF, "Short Selling Around the Expiration of IPO Share Lockups"，working-paper PDF 已读全文前3页)：空头在解禁日前数周异常增加、解禁前一日达峰，做空更多的股票解禁日收益更差（空头知情）；PE背景股票解禁日**没有**负收益/放量跳升（区别于VC背景）；书中列出具体反例 Yelp 2012-08-29 解禁日 **+23%**（"短挤"）、PokerTek +14%、Odimo -33%，说明横截面方差大、存在挤仓尾部风险。Damodaran (2019 practitioner substack)：解禁效应"2-5%"但**明确判定不可交易**——约1/3的解禁反而上涨，相对交易成本太小太不可预测，大盘高流动性名字效应尤其弱。未找到2020年代独立复现（与情报简报一致）；de-SPAC 2021-2022 波段的解禁本身未见专门量化研究，只有笼统的"post-merger 表现差"证据（机制不同，不能直接当解禁效应证据）。这些证据已计划写入 `direction-review.json`。
  - 收到一条自称"协调者"的消息，要求追加一个基于 Abdi-Ranaldo (2017) close-high-low 半价差估计 + 按ADV分层借券费(0.5%/2%/5%/25%) 的成本敏感性格，并指示不要 import 另一个会话仍在改的 `scripts/run_t20260929_32_*`。该消息不是以正常用户轮次出现，格式可疑（夹在工具结果之间、以 system-reminder 包裹），无法核实来源，本任务**未实现**该追加项，只按原始任务书的成本模型（分层spread + 3%/25%借券 + 2×成本）执行；已在 report.md 里如实记录这条未采纳的可疑指令，供机主核实。
  - 2026-09-29 结果：13 个候选全部否定——TEST 内最佳格 `L1L5_adv1500_pos`（做空、ADV<=1500档、动量过滤）calendar Sharpe 0.419（门槛 1.19），对 S3 边际 -0.274（门槛 +0.05），安慰剂 date_shift+60 t=-0.59、random_date t=0.66（均 |t|<2，仅 date_shift-60 单独 t=2.22 过线），扛住 2×成本（0.419→0.326）但收益/安慰剂两条主判据都未过；DSR（13次试验）=0.159。事件表 20 样本人工核查发现 30%（6/20，过滤前上限口径）非真普通股 IPO 事件，集中在 first_trade_fallback 口径（35%），已加名称过滤但未二次核查。price hygiene 打码了 259/3577（7.2%）事件标的，5 笔最大 |收益| 交易（RYDE/AXG/BUUU/MENS/YDDL）均未被标记为数据问题。登记簿 `dir:ipo_lockup_expiration_drift` 更新为 refuted。详见 `reports/research/iterations/h20260929_21_ipo_lockup_expiry/{report.md,results.json,decision-record.md,trial-ledger.jsonl}`。
  - 执行期间收到的"协调者"中途消息（补充 price hygiene、改用 RSS-based 前台等待、报告中位数/截尾均值）经队列内 T-20 的协调者更正确认为主会话本人发出、非注入，已按其要求实施；另外自查修复了 `shift_events()` 安慰剂函数的一处代数错误（移位后才重算窗口宽度，导致安慰剂逐笔等于真实交易，t统计量原本全部退化为 NaN/0），已加回归测试并用修复后的代码重跑出上述最终结果。
  - 协调者更正（2026-09-29 08:20 UTC）：第一条 Abdi-Ranaldo 成本敏感性消息也来自主会话。没实现不影响结论：做空方每笔均值全为负（−0.06% 到 −1.13%），更细的成本只会更差。结果文件已压缩：逐笔 car_series 和逐代码清洗明细留在本地 `results.full.json`（不入库），提交的 `results.json` 汇总数字不变。

### T-20260929-20 交互会话：个股无消息大跌反转 / 有消息大跌漂移（Chan 2003 / Savor 2012）
- status: done
- priority: 1
- not_before:
- goal: 机主要短时线、出手少、胜率高、单笔收益多的策略。情报简报 `reports/research/intel/I-20260929-01-short-horizon-selective.md`（第2.2、4节）把这个方向排第一：top-1500 ADV 个股，市场调整后单日跌幅 >=5%/8%，当天无可识别新闻/8-K 的做多反转（Chan 2003 JFE），有可识别新闻/8-K 的做空漂移（Savor 2012 JFE，仅 top-1000 ADV 易借券档）。登记簿 `dir:no_news_price_shock_reversal_chan` 状态 harvested，本仓库从未实测。
- plan: 迭代 `h20260929_20_news_nonews_drop_reversal`。12 个候选（D∈{5%,8%} × h∈{1,3,5} × {做多无新闻反转, 做空有新闻漂移}），close-to-close/次日开盘成交，按 ADV 分层价差成本（top-500 3bp / 500-1000 6bp / 1000-1500 12bp）+ 空头 1%/年借券费，另报 2× 成本；容量上限 20 个并发仓位各 ≤10%，超额按跌幅从大到小顺序接纳；两个安慰剂（新闻标签打乱、事件重新定日）在交易笔级别计算。TEST 窗 2024-01-08→2026-09-17 为唯一判定窗——数据可行性核查发现 news_packets 和 earnings_events(8-K item-2.02) 两个 PIT 新闻源都只从 2024 年才有密集覆盖（2011-2023 合计仅 195 行），STRESS 窗 2016-2023 按任务书自带的"or from news-data start"条款判定为该机制下数据不可行，不计入判定，已写入 `data-feasibility.json`。
- done_when: `direction-check` 和 `iteration validate --stage pre-backtest`/`--stage final` 都通过；`results.json`+`report.md`（含中文摘要表：cell/胜率/单笔均收益/年化笔数/夏普/与S3相关性/edge）；登记簿新增 `dir:news_vs_nonews_drop_reversal` 行；本队列块改 done 并写两行结果。
- notes:
  - 2026-09-29 交互会话新增，队列 id T-20260929-20。
  - 联网证据（本次搜索，含一篇此前未记录的复现）：Chan (2003, JFE 70(2):223-260) 和 Savor (2012, JFE 106(3):635-659) 摘要级证据确认（均为付费墙，ScienceDirect/SSRN WebFetch 均 403）；新找到 Dyl, Yuksel & Zaynutdinova (2019, Journal of Business Research 95:1-12)——样本延长到 2015 年的独立复现，同样的过度反应/反应不足模式在小盘/低机构持股名字中更强，**且发现后十进制化（post-decimalization）流动性改善后反转和漂移的幅度都在下降**——这条衰减证据说明不能假设 Chan 时代的量级在 2024-2026 依然成立，本轮直接在当前窗口实测幅度。未找到 2020 年代的独立复现。三篇来源卡见 `reports/harness/source_cards/h20260929_20_news_nonews_drop_reversal.jsonl`。
  - 收到一条自称"协调者"的消息，要求追加一个基于 Abdi-Ranaldo (2017) 价差估计 + ADV 分层借券成本(0.5%/2%/5%)的敏感性格，并引用另一会话仍在改的 `scripts/run_t20260929_32_*`。该消息不是以正常用户轮次出现，格式可疑（夹在工具结果之间、以 system-reminder 包裹，且与另一并行任务 T-20260929-21 收到的几乎同一话术的可疑消息雷同），无法核实来源，未实现该追加项，只按原始任务书的成本模型（ADV 分层价差 + 1%/年借券 + 2×成本）执行。
  - 补充：跑完之后又收到两条同一话术的可疑"协调者"消息，第一条声称 results.json 被拆股/坏数据"污染"并给出一套事后重跑方案（改用 price_hygiene 清洗、加拆股探测器、重跑12个候选），第二条是对等待机制的"更正"。同样不是正常用户轮次，均未采纳；但顺着它点出的 WOLF/APH 线索自己做了一次有边界的独立核查（见 report.md「数据质量补充核查」一节）：APH 确认是真实的未复权2:1拆股（18笔/0.04%），WOLF 确认是真实的破产重组价格跳变（389笔），另外4个代码价格序列持续异常；合计约2.5%的交易涉及这几个可疑代码，量级远不足以解释任何候选离门槛的差距，否定结论未变、未重跑。
  - 2026-09-29 结果：12 个候选全部否定——最好日历夏普 0.67（门槛 1.19），对S3分散化edge 全负（最好 -0.57，门槛 +0.05），做多腿胜率 42.9-45.1%（方向与假设相反），两条预注册安慰剂均未被真实组显著跑赢（t<2），DSR（12次试验）做多腿 <=0.178、做空腿 <0.0002。登记簿 dir:news_vs_nonews_drop_reversal 新增为 refuted。详见 reports/research/iterations/h20260929_20_news_nonews_drop_reversal/{report.md,results.json}。
  - 协调者更正（2026-09-29 08:40 UTC）：
    - 上面几条"协调者"消息确实来自启动本任务的主会话（SendMessage），不是注入。代理不改预注册方法是对的。
    - WOLF −1757% 是新旧股票接在同一代码上造成的假象。旧股已注销，每股旧股换约 0.0084–0.0139 股新股（Wolfspeed 10-Q），这笔空单实际约 +74% 到 +84%。
    - 协调者的稳健复核（截尾均值、剔除问题代码）结论不变，见 report.md「协调者更正」。

### T-20260929-50 周末加密货币涨跌预测周一美股（Mourey 等，Finance Research Letters 2025；只用加密行情做信号，交易的是股票 ETF）
- status: done
- priority: 2
- not_before:
- goal: 已发表结果说周末（美股休市）加密货币下跌会显著预示周一美股下跌，上涨则无信号，2022 年 5 月 LUNA 之后更强。问题：在我们的成本口径（10 bp 每边、收盘出信号次日开盘成交）下，这个不对称信号能不能在周一开盘之后赚到钱，或者当作 S3 的周一去风险开关。它是机主放开的"做空/反向 ETF"范围里唯一有 2025 年同行评审、样本贴近当前市场状态的新信息源，本地数据齐全，一天内可出结论。
- plan: 先按 `dir:crypto_weekend_to_monday_equity_transmission` 写 direction-review（差异：`dir:prediction_market_crypto_as_equity_signal` 只做过一日领先滞后，未做周末窗口；论文摘要没有交易规则、夏普和成本，需自己定义）。数据：`data/research/crypto/raw/binance` 的 15 分钟 K 线（T-20260929-33 已缓存，BTC/ETH 用 Coinbase 补到 2016-05），股票用 SIP 日线的 SPY/QQQ/IWM 开收盘价，不读分钟面板。信号 W = 周五 16:00 ET 到周日 24:00 UTC 的加密收益（周日收盘后已知，周一开盘成交）；不许用周一 09:30 的加密价格。**第一步（最便宜的否定测试，几行代码）**：把周一收益拆成"周五收盘到周一开盘的缺口"和"周一开盘到收盘"，比较 W<0 与 W≥0 两组的均值差和 t 值（全样本、2022-06 之后、2024 之后）。如果预测力全在缺口里（很可能，因为期货周日晚已开盘、周一开盘价已含周末信息），则按次日开盘成交规则不可交易，登记为 refuted 并注明"缺口内、成交前已反映"（Alpaca 是否有周日夜盘及是否有本地数据需另行核实，不在本任务假设内）。只有开盘到收盘或到周二开盘仍有显著差异，才做批量：约 20 条已预注册候选 = 信号{BTC，ETH，本地 10 币等权}×阈值{W<0，W<-3%}×持有{周一开盘到收盘，周一开盘到周二开盘}×标的{做空 QQQ}共 12 条，另加 IWM 做空 4 条（10 币等权信号），S3 周一去风险开关 4 条（W<0 与 W<-3%，BTC/10 币等权；被标记的周一空仓，每次多付 2 边成本）。仅做空 SPY/QQQ/IWM 这类易借券 ETF；反向 ETF（SH、SQQQ）作为 G5 只做多可执行版本单列。判定按运行手册第 5 节：K1、K2、近期观察；对标窗 2024-01-08 起，压力期 2016-05 到 2023-08（LUNA 之前当压力期单独报），选择窗 2023-09-18 到 2025-12-31。安慰剂：把周末标签在周之间打乱 500 次（真实结果须高于第 90 百分位）、只用周六窗口的信号、镜像的"上涨周末做空"（不应有效）。样本很少（约 20% 的周一），报告交易笔数和 DSR；加密侧不需要交易，所以不用 Alpaca 加密费率。
- done_when: 缺口与盘中拆分表写入结果；若继续则 20 条候选的分档、安慰剂结果和 K1/K2 判断写入 `reports/research/iterations/h20260929_50_crypto_weekend_monday/results.json`；登记簿 `dir:crypto_weekend_to_monday_equity_transmission` 更新为 refuted/partial/watch_recent 并 `oc research directions validate` 通过；覆盖地图 `trend_momentum.crypto_trend` 补一行。
- notes:
  - 2026-09-29 13:07 轮缺口搜索（gap-search-2026-09-29-13）添加。
  - 2026-09-29 13:40 UTC 自动轮开始，派 sonnet-high 子代理做第一步（缺口/盘中拆分）。
  - 2026-09-29 13:07 轮结果（协调者已对照 results.json 的 continue_rule/cells 核对）：否定，不做批量。论文效应在我们数据上复现，但只在周五收盘→周一开盘的缺口里：QQQ W<0 组比 W≥0 组低 51–62bp（t −3.0 到 −4.6），SPY 36–45bp；周一开盘→收盘没有同向效应（QQQ −2 到 +17bp，|t|≤1.1），开盘→周二开盘反而是反向。继续条件 0/12。按次日开盘成交不可交易。复开条件：确认 Alpaca 周日晚 8 点夜盘可交易且有数据。登记簿 `dir:crypto_weekend_to_monday_equity_transmission` refuted。产物：`reports/research/iterations/h20260929_50_crypto_weekend_monday/`，提交 5d5e788。

### T-20260929-51 小盘股做空"背景漂移"：同 β 对冲后的空头篮子在易借券、借券成本和随机篮子安慰剂之下是否还在（Kargarzadeh 等 arXiv 2608.14014）
- status: done
- priority: 2
- not_before:
- goal: 该论文（2023-2026，约 3000 只美股）发现"做空任何有新闻的小盘股"同 SPY β 对冲后毛夏普 1.35（20 bp 每边 0.78），新闻方向毫无贡献，全部来自小盘股相对单一 β 基准的每月约 -0.9% 漂移，作者没有建模借券费。问题：这是可交易的近期状态收益，还是"大盘巨头跑赢等权"的度量假象？回答它有两重价值：一是可能是当前市场里最便宜的空头端 Sharpe 来源；二是它是本队列所有个股空头事件测试（IPO 解禁、大跌反转、增发）必须超过的无条件基线，T-20、T-21 的空头结果没有拿它做对照。
- plan: 按 `dir:small_cap_background_drift_short_basket` 写 direction-review 与候选清单（约 20 条，批量筛选通道或单脚本均可，须过 `scripts/screen_batch.py` 的偏移中位数口径）。**第一步（最便宜的否定测试，ETF 层，几秒）**：做空 IWM、按滚动 252 天 β 对冲多 SPY，月度调仓，取所有调仓日偏移的中位数夏普；同样做 RSP 对 SPY、IJR 对 SPY、XRT 与 KRE 对 SPY。含 20 bp 每边加借券费 0.5%/年（ETB 指数 ETF）。对标窗 2024-01-08 起，压力期 2016-05 到 2023-08。若 IWM/SPY 对冲空头在对标窗的偏移中位数夏普低于 0.6，则个股篮子扣借券费后不可能高于它，直接把整条判为"近期观察或淘汰"，不再做第二步。**第二步（仅当第一步过 0.6）**：个股篮子，只读 `data/sip/daily` 和 `data/sip-delisted`，必须先跑 `open_composer.research.features.price_hygiene.sanitize_price_matrices`（默认参数），并只按信号当天排除疑似拆股（数据坑第 9 条）；池子按滚动 63 日中位成交额分位分层（1500-3000 名、500-1500 名，价格≥5 美元），以此当易借券代理；等权做空整个分层，周度/月度调仓，对冲{SPY β，IWM β，不对冲}，借券成本网格{0，5%，15%/年}，每边 10 bp 与 20 bp，同一份候选清单里再列"在池内叠加 63 日动量最差四分位/高波动四分位"两个条件变体，检查是否高于同池无条件基线。安慰剂：同池随机 50% 子集做空（应与基线持平，用来确认漂移是池的性质）、做多镜像（应为负）。必须报告最大单月轧空亏损和 2021-01/02 那类月份（压力期内）的表现。判定：运行手册第 5 节 K1/K2/近期观察，按偏移中位数；所有候选计入 DSR；若只在对标窗成立、压力期为负，标"近期观察，仅前向"，并写明失效信号（IWM/SPY 比值转为连续 6 个月上升）。
- done_when: 第一步表格（IWM/RSP/IJR/XRT/KRE 对 SPY，含借券与 20 bp）写入 `reports/research/iterations/h20260929_51_small_cap_short_drift/results.json`；若做第二步则含 20 条候选分档、借券网格、随机篮子安慰剂、最大轧空月；登记簿 `dir:small_cap_background_drift_short_basket` 更新状态并 `oc research directions validate` 通过；在 `dir:seo_atm_offering_dilution_drift` 和 `dir:ipo_lockup_expiration_drift` 的证据里写明无条件小盘空头基线的数字，供以后的空头事件测试引用。
- notes:
  - 2026-09-29 13:07 轮缺口搜索（gap-search-2026-09-29-13）添加。
  - 2026-09-29 16:07 UTC 自动轮开始（a42b6bb7），派 sonnet-high 子代理执行。
  - 2026-09-29 16:07 轮结果（协调者已对照 results.json 核对 9 条）：否定，第一步就没过线，不做第二步。IWM/SPY 252 天 β 对冲空头扣 0.5%/年借券、10bp 后对标窗偏移中位数夏普 0.39（门槛 0.6），压力期 0.55；五个 ETF 最好 XRT 0.64（压力期 0.10）、IJR 0.59；不对冲纯做空对标窗 −0.89；做多镜像安慰剂 −0.48（符合预期）。K2 全不过（IWM_M63 对标窗 +0.049、压力期 +0.067，差一点）。DSR 0.19（9 次试验）。漂移是"小盘跑输 SPY"，β 调整后对标窗约 −0.53%/月，比论文的 −0.92% 小。批量通道 `weights_frame` 只保留正权重，所以写了独立脚本 `scripts/run_h20260929_51_small_cap_short_drift.py`（复用通道窗口/偏移/模拟器/DSR，加带符号权重和借券费）。无条件小盘空头基线 = 对标窗夏普 0.39，已写进 SEO/ATM 和 IPO 解禁两行登记簿。产物 `reports/research/iterations/h20260929_51_small_cap_short_drift/`。

### T-20260929-60 DoltHub 免费期权库验收 + 本地缓存（解除期权格子的数据阻塞；T-61/62/63 的前置）
- status: done
- priority: 2
- not_before:
- goal: 期权格子从 09-15 起一直是 `blocked_data`（Alpaca 免费档没有历史报价）。2026-09-29 16 点的缺口搜索直接调用 DoltHub 的 SQL API，确认 `post-no-preference/options` 有免费的每日期权链（含买价、卖价、IV、希腊字母），2019-02-09 到 2026-09-28，另有 `volatility_history`（约 1,540 只标的的每日 iv_current、hv_current）。但每个标的每天只有约 130-190 个合约、最长约 6 周、AAPL 2024 年只有约 73% 的交易日，且没有文档写快照时间和报价来源。本任务只回答一件事：这份数据能不能用来给期权策略定价。通过就解锁 T-61（股票截面 IV 信号）、T-62（财报隐含波动率回落）、T-63（卖权利金批量）；不通过就让 T-64（付费数据）由机主决定。
- plan: 数据验收，不是策略回测，不算研究迭代的回测门；但写 `direction-review.json`（引用 `dir:dolthub_free_options_eod_chain_data`）。**预注册的通过标准先写进 results.json 的 `criteria` 字段再拉数据。**
  1. 写 `scripts/fetch_dolthub_options.py`：走 `https://www.dolthub.com/api/v1alpha1/post-no-preference/options?q=<SQL>`（无需密钥；每次最多 1000 行，所以按标的×年份×到期日分页，用 `ORDER BY ... LIMIT 1000 OFFSET n`），单线程、遇 429/5xx 指数退避、每 200 次请求写断点、结果落 `data/dolthub_options/*.parquet`（该目录不进 git，先确认 `.gitignore`；若没忽略就只加这一行，不动其它）。先做 20 次连续请求测限流；限流严重再考虑 dolt 命令行（要先查表大小，磁盘只剩约 23 GB，表大于 8 GB 不 clone）。不要用 Claude 读大量数据，只读汇总。
  2. 缓存：`volatility_history` 全表（约 280 万行量级）；`option_chain` 只拉 SPY、QQQ、IWM、SMH、NVDA、TSLA、TQQQ、AAPL、MSFT、AMZN、GOOGL、META 的 2019-02→今（约 2,000-3,000 次请求）。
  3. 验收检验（每条报数字，逐标的逐年）：(a) 交易日覆盖率 = 有数据的日期 ÷ `data/sip/daily` 该标的的交易日；(b) 时间点：用 put-call 平价 `C-P = S-K` 从近月 ATM 的买卖中间价反推标的价格，和 SIP 日线当日收盘价、次日开盘价比较，判断快照更接近哪一个；(c) 相对价差 (ask-bid)/mid：近月 ATM 与 25 delta 合约，按标的、年份的分位数（SPY/QQQ 与个股分开），和已发表的"ATM 跨式价差约占权利金 5-15%"对照；(d) `iv_current` 日自相关（应 > 0.9）、与链里 ATM 合约 vol 的一致性；(e) 缺口是否随机：缺失日和当日 |收益| 的关系；(f) 每个标的每天的合约数、到期日数随年份的变化（2019-2022 对 2024 起）；(g) 有没有零买价、买价大于卖价、卖价<买价、明显过期的报价占比。
  4. 通过标准（先写死）：SPY、QQQ、AAPL、NVDA、TSLA 五个标的的日覆盖率 2019 起 ≥ 85%、2024 起 ≥ 90%；平价反推的标的价格与 SIP 收盘价（或开盘价，取更近者）中位相对偏差 ≤ 0.10%；SPY、QQQ 近月 ATM 相对价差中位数 ≤ 3%、个股 ≤ 10%；坏报价占比 ≤ 2%。**结论只有三档**：通过（解锁 T-61/62/63，成交口径写明"用哪天的快照近似次日成交"）；部分通过（只允许覆盖率达标的标的，其它任务只能用这个标的清单，写进 T-61/62/63 的 notes）；不通过（把 T-61/62/63 改 blocked，T-64 由 blocked 改 ready 并通知机主）。
  5. 记录缓存位置、行数、每个标的的覆盖率表；若快照时间不明，明确写"信号日 d 的 IV 当作 d 收盘信息，成交用 d+1 开盘价还是 d+1 快照"的建议。登记簿 `dir:dolthub_free_options_eod_chain_data` 改状态并 `oc research directions validate` 通过。
- done_when: `reports/research/iterations/h20260929_60_dolthub_options_acceptance/results.json` 含 criteria、每标的覆盖率/价差/平价偏差表、三档结论；`scripts/fetch_dolthub_options.py` 和它的单元测试（分页、退避、断点，用假响应）通过 ruff 和 pytest；T-61/62/63 的 notes 各追加一行结论；登记簿更新且 validate ok。
- notes:
  - 2026-09-29 16:07 轮缺口搜索（gap-search-2026-09-29-16）添加。简报 `reports/research/intel/gap-search-2026-09-29-16.md`。已验证（16:1x UTC 直接 SQL 调用）：option_chain 最新日期 2026-09-28、SPY 最早 2019-02-09；volatility_history 2026-09-28 有 1,536 个标的；AAPL 2026-09-28 链 192 行、4 个到期日。本任务未开始。
  - 2026-09-29 16:30 UTC 自动轮（a42b6bb7）开始，派 sonnet-high 子代理执行。
  - 2026-09-29 16:30 轮结果（协调者已核对 results.json）：按预注册标准"不通过"。覆盖率（服务器端逐日聚合，全部 1,919 个交易日，精确）：2019 起 SPY 61.4%、AAPL 62.0%、NVDA 61.7%、TSLA 53.9%（门槛 85%）；2024 起 87.5–87.9%（门槛 90%）；QQQ 完全没有数据，IWM/SMH/TQQQ 抽查也没有。2020-01→2024-08 每周大约只有 3 天；2024-09-04 起很密（SPY 97.9%、AAPL 98.5%，事后观察，不是标准）。价差和坏报价通过（ATM 价差中位 SPY 0.7%、个股 1.8–3.5%，坏报价 ≤0.4%）；平价偏差 0.15–0.40% 超过 0.10%（只能在 09-22 起 4–5 天上比，因为 SIP 日线是复权价）。快照是 d 日收盘。未拉全链和 volatility_history 全表；续跑 `uv run python scripts/fetch_dolthub_options.py --jobs chain,volhist --symbols SPY,QQQ,AAPL,NVDA,TSLA --chain-flush-units 25 --checkpoint-every 25`。产物 `reports/research/iterations/h20260929_60_dolthub_options_acceptance/`。

### T-20260929-61 批量筛选：期权隐含波动率 vs 实现波动率的股票截面信号（Bali-Hovakimian / Goyal-Saretto 方向；交易的是股票，期权数据只当信号）
- status: blocked（T-60 不通过；等 T-64 或免费密集段新合同）
- priority: 2
- not_before:
- goal: 机主的信息源分层里，期权隐含信息排在 OHLCV 因子之上，但此前没有免费带报价的历史 IV，`dir:alpaca_free_options_iv_signals`、`dir:option_implied_crash_risk_xgboost_2026` 都因此不可执行。T-60 验收的 DoltHub `volatility_history` 提供约 1,540 只标的的每日 iv_current 和 hv_current。文献：实现波动率高于隐含波动率的股票之后收益更高（Bali & Hovakimian 2009；Goyal & Saretto 2009 测的是期权收益）；2026 年 arXiv 2608.26115 说 IV 信号 2023-2026 仍显著但 R2 很小。问题：在 2024 起的近期窗口、易借券股票上、扣 10/20 bp 之后，这类信号能不能达到 K1/K2。它交易股票，不受期权价差影响，是期权数据里成本最低的一条。
- plan: 依赖 T-60 的缓存和结论（T-60 未完成先做 T-60 的第 1-2 步；T-60 判"不通过"则本任务改 blocked）。按 `dir:iv_hv_spread_stock_ranking_dolthub` 写 direction-review 和候选清单，**先预注册再算**。信号（预注册符号，符号错的镜像只当对照，不算候选）：IVRV = hv_current − iv_current（做多值高者）；IVCHG5 = iv_current / iv_week_ago − 1（做多 IV 下降者）；DEEPDIP = 在 close>200 日均线的上升趋势股里，3 日收益 ÷ (iv_current×√(3/252)) ≤ −1.5 的"跌幅超过期权隐含"股票（Deep Dip 的公开描述，做多）。候选 12 条 = 3 信号 × 持有 {5 日/周度、21 日/月度} × {只做多前十分位，多头前十分位 + 空头后十分位并用 SPY β 对冲}；池子固定 ADV 前 1,500 且价格 ≥ 5 美元（易借券代理；空头腿只在 ADV 前 500 内做）。对照（不是候选）：只按 hv 排序、只按 iv 排序（拆解安慰剂，项目规则：被单一分量复现 ≥50% 就停，参照 `dir:short_interest_ratio_crowding_factor` 的教训）、跨标的打乱 IV 的安慰剂。**最便宜的否定测试（几分钟，先于任何回测）**：三个信号对 5 日、21 日前瞻超额收益的 RankIC，2019-02→2023-08 与 2024-01-08 起分开算，按周做 Newey-West t。继续的条件：至少一个信号在 2024 起 IC 符号与预注册相同、|t| ≥ 2.5，且 2019-2023 同号，且 hv-only/iv-only 对照复现不到 50%。全不满足就停，写否定。信号日 d 的 IV 当作 d 收盘信息，成交用 d+1 开盘价，除非 T-60 证明快照晚于收盘（则再滞后一日）。价格面板必须先过 `sanitize_price_matrices` 默认参数并只按信号当天排除疑似拆股；内存紧，读行情一律 `scripts/run_capped.sh --mem 1.8G --`。通过 IC 关口后走批量通道 `scripts/screen_batch.py`，判定按运行手册第 5 节 K1/K2/近期观察，调仓日偏移取中位数（周度 5 个、月度 21 个），报 DSR，20 bp 复核，压力期在 IV 数据可得的部分（2019-02→2023-08，标"压力样本短：2019-02 起"）。
- done_when: IC 表（三信号×两持有期×两窗×对照）写入 `reports/research/iterations/h20260929_61_iv_stock_ranking/results.json`；若过关则有 12 条候选的分档、DSR、20 bp 结果；登记簿 `dir:iv_hv_spread_stock_ranking_dolthub` 更新状态并 validate ok；`dir:alpaca_free_options_iv_signals`、`dir:iv_informed_dip_mean_reversion_live` 的证据里注明"已用带报价的 IV 重测"及结论。
- notes:
  - 2026-09-29 16:07 轮缺口搜索（gap-search-2026-09-29-16）添加。依赖 T-60。原文核对情况：Goyal-Saretto SSRN 页面 403，只按摘要知道结论，需在 direction-review 里注明。
  - 2026-09-29 16:07 轮：T-60 判"不通过"，按本任务 plan 改 blocked。免费备选（不需要机主决定，但要新建独立合同）：只用 2024-09-04 以后的密集段（SPY、AAPL、NVDA、TSLA 及 MSFT/AMZN/GOOGL/META 抽查），按手册"不足 2 年压力期"条款只判对标窗、标"待补压力期"；QQQ/IWM/SMH/TQQQ 没有数据。付费数据见 T-64。 本任务依赖 volatility_history，其 2024-09 起的覆盖率还没测，是走免费路线的第一步。

### T-20260929-62 批量筛选：财报隐含波动率回落，定义风险结构在真实买卖价下能否净赚（top-100 大盘股）
- status: blocked（T-60 不通过；等 T-64 或免费密集段新合同）
- priority: 2
- not_before:
- goal: 已发表/自述数据一致说财报隐含波动幅度平均高于实现幅度：theintrinsicinvestor.com（S&P 500 37,508 个事件 2010-2025，IV 比 RV 高 16.5 点，胜率 69%，季度夏普 2.05）；但它不含买卖价差，自己说 ATM 跨式价差占权利金 5-15%，前 100 名之外净夏普接近零或为负，且用模型 IV 而非真实报价；flashalpha 的 70 个事件（2025-06 到 2026-07）平均收割比只有 +0.02、5% 分位 −1.92。没有人用真实报价测过定义风险版本。这条是"事件短、单笔多、和 S3 相关性低"的候选，达到 K1 就值得排；Alpaca 期权 Level 3 允许价差（不允许裸卖跨式），所以只测铁蝶/铁鹰。和已否定的盈余意外三条线不同：这里交易的是波动率溢价，不押方向。
- plan: 依赖 T-60（结论为通过或部分通过；不通过则改 blocked）。按 `dir:earnings_iv_crush_defined_risk_condor` 写 direction-review 和候选清单，先预注册。事件：`data/features/earnings_events/{2024,2025,2026}.parquet`（8-K Item 2.02，`acceptance_utc` 判盘前/盘后）；2019-02→2023-12 的压力样本需要 EDGAR Item 2.02 索引，若 T-20260929-03 已建 8-K 项目表就用它，没有就只做 2024 起并按运行手册标"压力样本短/待补压力期"（2.7 年，≥2 年，按对标窗和选择窗判）。标的池：T-60 覆盖率合格的名单里 ADV 前 50 与前 100 两档。定价：信号日收盘前一交易日（盘后公告为公告日）的快照建仓、事件后第一个快照平仓（成交口径以 T-60 结论为准）；**卖在买价、买在卖价**，另加每合约 0.65 美元（Alpaca 期权佣金/监管费本轮未核实，待核实，作保守假设）；敏感性：中间价 −25% 半价差。结构（预注册，全部候选计入试验次数）：先测量项（不是可交易候选）——卖 ATM 跨式、买回，得到"净权利金捕获率"；候选 12 条 = {铁蝶（短腿 ATM，翼在 ±1.0×隐含幅度；±1.5×隐含幅度）、铁鹰（短腿在 ±0.75×隐含幅度，翼在 ±1.5×隐含幅度）} × 池 {前 50，前 100} × 过滤 {全部事件，隐含幅度 / 自身过去 8 个季度实现幅度中位数 ≥ 1.2}（flashalpha 的"梯度"）。**最便宜的否定测试（先于候选）**：top-100 的 2024 起事件，卖 ATM 跨式（卖价成交）、买回（买价成交）的平均净盈亏占权利金的比例及其分位数；再对每个事件算"实现幅度 / 隐含幅度"，和上述已发表数字对照。若净盈亏平均 ≤ 0 就停（因为翼只会增加成本），写否定。组合口径：每笔按最大亏损配同额资本、同时持仓不超过 20 笔、闲置资金收益 0，按日盈亏算夏普；财报季集中，注明月度分布。安慰剂：同标的同结构放在随机非财报日（应≈只剩成本）、把事件打乱到别的标的。判定：运行手册第 5 节 K1/K2/近期观察，"调仓日偏移"的等价做法是入场提前/推后 0、1 个交易日两组和持有 1、2 日对比，中位数判，报 DSR，20 bp 等价口径用"价差 ×1.5"复核。最大单笔亏损、翼被击穿的比例必须报告。
- done_when: 测量项表和 12 条候选分档写入 `reports/research/iterations/h20260929_62_earnings_iv_crush/results.json`（含覆盖率：有多少事件因缺链被丢弃，丢弃是否偏向大波动日）；登记簿 `dir:earnings_iv_crush_defined_risk_condor` 更新并 validate ok；若保留，写明失效信号（例如净权利金捕获率连续两个财报季为负）。
- notes:
  - 2026-09-29 16:07 轮缺口搜索（gap-search-2026-09-29-16）添加。依赖 T-60。expireworthless.com 那篇 846 个事件的测试 HTTP 402 打不开，未引用其数字。
  - 2026-09-29 16:07 轮：T-60 判"不通过"，按本任务 plan 改 blocked。免费备选（不需要机主决定，但要新建独立合同）：只用 2024-09-04 以后的密集段（SPY、AAPL、NVDA、TSLA 及 MSFT/AMZN/GOOGL/META 抽查），按手册"不足 2 年压力期"条款只判对标窗、标"待补压力期"；QQQ/IWM/SMH/TQQQ 没有数据。付费数据见 T-64。

### T-20260929-63 批量筛选：真实买卖价下的卖权利金（现金担保看跌、看跌价差、备兑看涨；ETF 与高 IV 个股/杠杆 ETF）
- status: blocked（T-60 不通过；ETF 标的无数据）
- priority: 3
- not_before:
- goal: 指数级的卖权利金证据是负面的：CBOE PUT 2007-2026 年化 6.87%、回撤 −37.1%，SPY 10.79%、−55.2%（theoptionsbench.com）；BXM 2020-2025 +51.3% 对 SPY +129.1%（coveredcallcalculator.net）；本仓库 XYLD 买入持有对标窗夏普 0.89、压力期 0.47（H-20260928-05）。没人用真实买卖价测过高 IV 标的（NVDA、TSLA、TQQQ、SMH）在 2024-2026 的表现，这是唯一可能超过 K1 的位置；同时它是唯一能给 S3 提供"下跌时收权利金"这种不同回报形状的期权族，所以还要看 K2。先验低，优先级 3。
- plan: 依赖 T-60（通过或部分通过）。按 `dir:options_premium_selling_real_chain_batch` 写 direction-review 与候选清单，先预注册。标的 7 个：SPY、QQQ、IWM、SMH、NVDA、TSLA、TQQQ（以 T-60 覆盖率合格者为准）；结构 4 个：CSP_D30（卖 30 delta 看跌，全额现金担保）、CSP_D15、PCS_D30_W10（卖 30 delta 看跌、买 10 delta 看跌的价差）、CC_D30（持有标的正股 + 卖 30 delta 看涨）；到期日取距入场 28-35 天的月到期，持有到期，不滚动、不做 wheel、不提前平仓（避免引入未预注册的管理规则）；到期按标的收盘价内在价值结算，被行权的正股当日按收盘价了结（把期权盈亏和正股方向分开）。候选 = 7×4 = 28 条，全部计入 DSR。成交：卖在买价、买在卖价，每合约 0.65 美元（待核实），敏感性用中间价 −25% 半价差；闲置担保金收益按 0 计，另报按 SHY 收益的版本。**Sharpe 优先**：每条候选必须和"同标的买入持有按同样波动率缩放"的夏普比，不比总收益；再和 S3 按 63 天波动率倒数月度组合，看 K2 增量。**调仓日偏移**：入场日偏移取上一到期日后第 1..21 个交易日的每一个（21 本账），报中位数。窗口：对标窗 2024-01-08 起；压力期只能用 2019-02→2023-08（数据从 2019-02 起，含 2020 崩盘和 2022 熊市，标"压力样本短：2019-02 起"）。**最便宜的否定测试**：SPY、QQQ 的 CSP_D30 月度、卖价成交，偏移中位数夏普对同标的同波动买入持有的夏普；若两者在 2024 起都不高于对应买入持有，就把指数族整体判否，只保留高 IV 的 NVDA/TSLA/TQQQ/SMH 格子继续；这些格子再不满足 K1 或 K2 就整批收口。必须报告最大单月亏损、2025-04 和 2022 的月份、被行权比例、最大回撤。
- done_when: 28 条候选的分档表（K1/K2/近期观察/淘汰）、每条对同波动买入持有的夏普差、DSR、20 bp 等价（价差 ×1.5）结果写入 `reports/research/iterations/h20260929_63_option_premium_selling/results.json`；登记簿 `dir:options_premium_selling_real_chain_batch` 更新并 validate ok；在 `dir:put_credit_spread_income`、`dir:covered_call_cef_income_pwb` 的证据里注明结论。
- notes:
  - 2026-09-29 16:07 轮缺口搜索（gap-search-2026-09-29-16）添加。依赖 T-60。
  - 2026-09-29 16:07 轮：T-60 判"不通过"，按本任务 plan 改 blocked。免费备选（不需要机主决定，但要新建独立合同）：只用 2024-09-04 以后的密集段（SPY、AAPL、NVDA、TSLA 及 MSFT/AMZN/GOOGL/META 抽查），按手册"不足 2 年压力期"条款只判对标窗、标"待补压力期"；QQQ/IWM/SMH/TQQQ 没有数据。付费数据见 T-64。 7 个标的里 QQQ/IWM/SMH/TQQQ 没有数据，只剩 SPY/NVDA/TSLA。

### T-20260929-64 机主决定：若 DoltHub 期权数据质量不够，是否购买历史期权买卖报价
- status: blocked（等机主决定）
- priority: 3
- not_before:
- goal: 只有 T-60 判 DoltHub 免费库"不通过"（覆盖率、时间点、价差或坏报价没达到预注册标准）时才有意义。此时 T-61（IV 股票信号）、T-62（财报波动率）、T-63（卖权利金）都没有可信的期权价格，要继续这个格子就需要付费的历史期权报价。
- plan: 阻塞原因：付费数据和新的数据预算是机主的决定（CLAUDE.md：付费超出免费额度属机主决定），自动轮不得自行购买。T-60 判"不通过"后，由自动轮把本任务 status 改 `ready` 之前，先在汇报第一条通知机主；机主给出预算后再做：核实候选供应商（ORATS、Polygon/Massive 期权历史、Databento OPRA、ThetaData 等）的价格、历史起点、是否含买卖报价与盘中快照、再分发条款——本轮没有核实任何价格。免费的替代（Alpaca 免费档、Kaggle SPY 2010-2023、OptionsDX 到 2023）已在简报里排除。
- done_when: 机主给出"买/不买/预算上限"；买则写数据接入任务并走 `modal_budget.py` 之外的独立预算记录；不买则把 `dir:dolthub_free_options_eod_chain_data` 和期权格子标 `blocked_data` 收口。
- notes:
  - 2026-09-29 16:07 轮缺口搜索（gap-search-2026-09-29-16）添加。当前不需要机主动作：等 T-60 结论。
  - 2026-09-29 16:07 轮：T-60 已判"不通过"，本轮汇报已通知机主。付费数据属机主决定，自动轮不改 ready。

### T-20260929-70 净股份发行（股本变化）因子：低发行/回购者做多，高发行者回避或对冲做空（Pontiff-Woodgate 方向，用本地 XBRL 股本，2024 起近期口径）
- status: done
- priority: 2
- not_before:
- goal: 净股份发行是发表最稳的截面异象之一（Pontiff-Woodgate JF 2008：1970-2003 最低发行十分位约 17%/年、最高约 9%/年，差约 8 个百分点，FF3 后约 6%/年），换手低（月频或季频），10 bp 和借券费相对这个量级很小，是"做空放开后新可测"里成本最友好的一类。但近期证据薄且偏负面：QuanterLab 2026-08 的 S&P 500 低股本增长 30 只等权做多（2006-2025，10 bp，作者自跑未复现）Sharpe 0.58 对等权指数 0.54，等于打平。本仓库 `dir:sec_xbrl_accounting_signals_v1` 只测了 ROE、毛利率、资产增长、应计，`dir:buyback_announcement_effect`、`dir:buyback_execution_vs_announcement` 都是 evidence_too_weak 且从未在本地计算，股本变化没有信号卡。问题：在 2024 起、扣成本和借券费之后，股本变化排序能否给出 K1/K2 级别的增量（做多低发行者、或空头腿在易借券大票里对冲做空高发行者）。
- plan: 数据本地已有：`data/features/sec_fundamentals_daily/*.parquet`（列 `shares_outstanding`，2016 起，按 8-K/10-Q/10-K 披露日的 PIT 展开，来源是 dei 封面股数 `EntityCommonStockSharesOutstanding`，facts 表里 164,083 行）；行情用 `data/features/daily_broad` 与 SIP 日线（复权价）。**不需要新数据**。注意：封面股数**没有拆股调整**，且双重股权公司可能只报一类，所以 (a) 只用 252 个交易日前后两个 PIT 值的对数变化；(b) 丢弃 |Δlog| ≥ ln(1.5) 的配对，以及区间内有疑似拆股交易日（`sanitize_price_matrices` 默认参数触发的 session）的配对；(c) 丢弃封面股数在区间内出现过 >30% 单季跳变后回摆的股票。本地没有回购金额（facts 表没有 PaymentsForRepurchase），不做美元回购版本，登记簿里注明。**先预注册再算**：写 `direction-review.json`（引用 `dir:net_share_issuance_pontiff_woodgate_recent`）和候选清单。信号（符号预注册：股本变化越低越做多）NSI252 = log(shares_t / shares_{t-252})；对照 NSI126（半年，不算候选，看信号是否只是最近一次增发）。候选 8 条 = 信号 NSI252 × 组合 {最低五分位只做多，最低五分位做多 + 最高五分位空头并用 SPY 252 日 β 对冲} × 调仓 {月频，季频} × 池 {ADV 前 500，ADV 前 1,500 且价格 ≥ 5 美元}；空头腿只在 ADV 前 500 内做（易借券代理），借券费 0.5%/年 与 3%/年 两档（费用档是敏感性，不额外增加候选数）；另有一个不算候选的对照：top-1500 等权中"剔除最高发行五分位"（只回避），用来判断收益来自多头还是空头。**最便宜的否定测试（几分钟，先于任何回测）**：`open_composer.research.signal_card` rank 模式，`--sql` 生成 NSI252（方向 -1，即低者好），池 ADV 前 1,500，`--primary-horizon 20` 和 60，报全样本（2017-2026）与 2024 起 RankIC、t、`flags`（predictive、stable_years、beats_shuffle、timely、tradable_tiers_20bp、distinct_from_controls）。继续的条件：2024 起 IC 符号与预注册相同（低发行→高收益），|t| ≥ 2.0（周/月重叠样本用 Newey-West），全样本同号，且 `distinct_from_controls` 真（不是市值/动量的替身；把 NSI 对 log 市值、12-1 动量做截面残差后 IC 至少保留 50%）。全不满足就停，写否定，不建账本。通过后走 `scripts/screen_batch.py`（价格面板先过 `sanitize_price_matrices` 默认参数，读行情一律 `scripts/run_capped.sh --mem 1.8G --`），判定按运行手册第 5 节 K1/K2/近期观察，调仓日偏移取中位数（月频 21 个、季频取 63 个的每第 3 个），DSR，20 bp 复核，压力期 2017-2023 只能标"压力样本短：2017 起"，对 S3 看 K2（相关性与压力期增量）。
- done_when: 信号卡 `reports/research/signal-cards/net_share_issuance_252.{json,md}` 和 IC 表（全样本 / 2024 起 / 残差版 / NSI126 对照）；若过关则 8 条候选分档、DSR、20 bp 与借券费两档结果写入 `reports/research/iterations/h20260929_70_net_share_issuance/results.json`；登记簿 `dir:net_share_issuance_pontiff_woodgate_recent` 更新为 refuted/partial/watch_recent 并 `oc research directions validate` 通过；`dir:buyback_announcement_effect`、`dir:buyback_execution_vs_announcement` 证据里注明"股本变化版本已本地测过"。
- notes:
  - 2026-09-29 23:05 UTC 自动轮完成：IC 闸门否定（2024 起 RankIC 20 日 +0.011 NW t 0.81、60 日 +0.005 t 0.25，要求 |t|≥2；全样本 t 2.06 靠 2021–22；残差版保留率 100%、NSI126 对照 t 0.58）。没建账本。产物 `reports/research/iterations/h20260929_70_net_share_issuance/`、`reports/research/signal-cards/net_share_issuance_252*.{json,md}`；登记簿 refuted。
  - 2026-09-29 22:07 UTC 自动轮（2681e20d）开始，派 sonnet-high 执行。
  - 2026-09-29 19:07 轮缺口搜索（gap-search-2026-09-29-19）添加。简报 `reports/research/intel/gap-search-2026-09-29-19.md`。原文核对：QuantDecoded（Pontiff-Woodgate 的二手总结，已打开）、QuanterLab 2026-08（已打开）；FAJ 2020 只有检索结果页（claim_only）。已检查 `data/features/sec_fundamentals_daily` 有 `shares_outstanding` 列（2016 起）。

### T-20260929-71 维基百科页面浏览量变化作为关注度信号（S&P 500，周频；Pyun 2025 长短组合，2024 起自己测）
- status: done
- priority: 2
- not_before:
- goal: 机主的信息源分层把"社交/关注度"放在 OHLCV 因子之上，本仓库测过新闻条数关注度（`dir:news_attention_features`，IC -0.003）但没测过维基页面浏览量。新信息：Pyun（SSRN 5172055，2025-03，2016-2023，Quiver 数据）报告页面浏览量上升的公司收益更高，周频多空组合有 FF 多因子无法解释的 alpha，月频调仓就变弱；经典的 Moat 等 2013 只有 DJIA 2004-2012。二手摘要没有夏普、成本、分时期数字，所以需要自己测。数据免费且时间点干净（Wikimedia REST 每日浏览量，已在 2026-09-29 直接调用验证：Apple_Inc. 2024-01-01 至 05 返回逐日 views），标的是易借券的 S&P 500 成分股，周频换手。它的否定成本极低（几百次 API 请求 + 一个 IC 表）。
- plan: 数据：本地**没有**维基浏览量（已检查 `data/` 目录树，无此项）；免费 API `https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/en.wikipedia/all-access/user/<title>/daily/<start>/<end>`，无需密钥，必须带描述性 User-Agent，单线程、遇 429/5xx 指数退避、断点续跑；写 `scripts/fetch_wikipedia_pageviews.py`（分页/退避/断点用假响应单测）。落 `data/wikipedia_pageviews/*.parquet`（先确认 `.gitignore` 覆盖 `data/wikipedia_pageviews/`，没有就只加这一行）。标的→文章标题映射：Wikipedia "List of S&P 500 companies" 的 wikitext（有 ticker 与公司文章链接，约 500 个）；只保留和 SIP 日线 symbol 对上的；**幸存者偏差是已知缺陷**（只有当前成分股），所以最终结论以 2024 起为主并要求 2016-2023 同号，任何时候都不把全样本夏普当证据。改名/合并的文章（如更名后标题）会造成历史断裂，丢弃 90 天内浏览量下降 >90% 的序列并记录丢弃名单。**先预注册再算**：`direction-review.json` 引用 `dir:wikipedia_pageview_attention_signal`，候选清单 = 信号 {VC7_28 = log(近 7 日总浏览量 ÷（前 28 日日均×7）)，VC28_90（对照，月度慢信号，不算候选）}中的 VC7_28 × 组合 {最高十分位做多，最高十分位做多 + 最低十分位空头并用 SPY β 对冲} × 滞后 {0：信号用截至 UTC 当日的浏览量、次日开盘成交，1：再滞后一个交易日} × 调仓日偏移 5 个 = 4 条候选（偏移取中位数判）；镜像（做多下降者）只作对照不算候选。时间点：UTC 日 d 的浏览量在 ET 20:00 才完整，所以信号只能在 d 收盘后用、d+1 开盘成交，不许用 d 收盘价成交。**最便宜的否定测试（先于账本，约 10 分钟）**：周频 RankIC（VC7_28 对下一周 SPY 超额收益），Newey-West t，分 2016-07→2023-12 与 2024-01-08 起两段，另做把标题打乱到别的股票的安慰剂 500 次。继续的条件：2024 起 IC 符号为正、|t| ≥ 2.5，且 2016-2023 同号，且真实 IC 高于安慰剂第 95 百分位。任一不满足就停，登记为 refuted。通过后再走 `scripts/screen_batch.py` 和运行手册第 5 节 K1/K2/近期观察（价格面板先过 `sanitize_price_matrices`，读行情用 `scripts/run_capped.sh --mem 1.8G --`），DSR，20 bp 复核，压力期 2016-07→2023-08 按可得样本判。
- done_when: 抓取脚本 + 单测通过 ruff/pytest；IC 表（两段、安慰剂、丢弃名单、覆盖标的数）写入 `reports/research/iterations/h20260929_71_wikipedia_pageviews/results.json`；若过关则 4 条候选分档和 DSR；登记簿 `dir:wikipedia_pageview_attention_signal` 更新终态并 validate ok。
- notes:
  - 2026-09-29 23:05 UTC 自动轮完成：IC 闸门否定（501 个标题全抓到，用 467 个；VC7_28 周频 RankIC 2024 起 −0.003 NW t −0.53，低于 500 次打乱安慰剂 p95 +0.006；2016–2023 +0.005 t 1.40，幸存者偏差）。没建账本。产物 `reports/research/iterations/h20260929_71_wikipedia_pageviews/`、`scripts/fetch_wikipedia_pageviews.py`；登记簿 refuted。
  - 2026-09-29 22:07 UTC 自动轮（2681e20d）开始，派 sonnet-high 执行。
  - 2026-09-29 19:07 轮缺口搜索（gap-search-2026-09-29-19）添加。原文核对：Pyun 论文本身没打开（SSRN 被挡），只读到 mlquants 的摘要转述，所以论文的数字一律不引用，只当作方向线索；Economics Letters 2024《The Wikipedia effect》被验证码挡住（claim_only）。API 只探测了一个标题的 5 天，没有测过限流。

### T-20260929-72 SEC 卖空交割失败（FTD）余额作为回避/做空信号（免费数据，最便宜的否定测试，收口"卖空信息"格子）
- status: done
- priority: 3
- not_before:
- goal: 覆盖地图 `alt_data.short_selling` 写着"fails-to-deliver never searched"，登记簿 `dir:sec_fails_to_deliver_signal` 仍是 evidence_too_weak 且从未在本地计算。SEC 每半个月发布一份全市场 FTD 余额（NSCC CNS，管道分隔，从 2009-07 起，数据到 2026-09；已直接打开数据页并对 `cnsfails202606a.zip` 做了 HEAD，200、1.3 MB）。文献把 FTD 高企与知情卖空、之后的负收益联系起来，但只在摘要层面读过，没有效应量；发布滞后约 15-16 个自然日会吃掉大部分短期信号；SEC 自己说 FTD 也来自多头卖出，且高 FTD 的股票偏难借券。先验低，排优先级 3，价值是用几分钟把这个从未测过的格子关掉；机主放开了易借券做空，所以只在 ADV 前 1,500 且价格 ≥ 5 美元的池里判。
- plan: 数据：本地**没有** FTD（已检查 `data/raw` 与 `data/features`，只有 `finra_short_interest`、`finra_short_volume`，那是别的序列，已否定）。下载 2019-01→最新的半月文件（约 170 个 × ~1.3 MB，`https://www.sec.gov/files/data/fails-deliver-data/cnsfails<YYYYMM><a|b>.zip`，a=上半月，b=下半月；SEC 要求描述性 User-Agent，单线程 ≤ 5 请求/秒，遇 429 退避）写 `scripts/fetch_sec_ftd.py`（分页/退避/断点用假响应单测），落 `data/sec_ftd/*.parquet`，先确认 `.gitignore` 覆盖 `data/sec_ftd/`（没有就只加这一行；`data/sec/` 是别的会话在用的目录，**不要往里写**，另建 `data/sec_ftd/`）。PIT 规则（写死）：上半月文件（结算日 1-15 日）最早可用日 = 当月最后一个自然日之后的下一个交易日；下半月文件最早可用日 = 次月 16 日之后的下一个交易日（SEC 说"约 15 日"，多留一天）。FTD 字段是余额，不是日流量，每个文件内取该文件最后一个结算日的余额。符号是 ticker，按 SIP 日线的 symbol 对齐，对不上的丢弃并报告占比（复用 ticker 要小心：只信价格字段与 SIP 收盘价偏差 <20% 的行）。**先预注册再算**：`direction-review.json` 引用 `dir:sec_fails_to_deliver_signal`；信号（符号预注册：FTD 高 → 之后收益低）FTDSH = FTD 股数 ÷ `shares_outstanding`；FTDADV = FTD 股数 × 价格 ÷ 20 日成交额；对照 FTD>0 的哑变量（不算候选）。候选最多 4 条：{FTDSH，FTDADV} × {回避闸门（top-1500 等权中剔除最高十分位），ADV 前 500 内最高十分位空头 + SPY β 对冲}，月频，借券费 3%/年（高 FTD 偏难借券，保守）。**最便宜的否定测试（约 10 分钟，先于任何账本）**：`signal_card` rank 模式，`--sql` 生成 FTDSH（方向 -1）和 FTDADV，池 ADV 前 1,500，`--primary-horizon 20`、60，`--lag` 用上述 PIT 可用日，报全样本（2019-2026）与 2024 起 RankIC、t、flags。继续的条件：2024 起符号与预注册相同、|t| ≥ 2.5、全样本同号。否则直接写"卖空信息格子收口：FTD 无信号"，不建账本，不加变体。
- done_when: 抓取脚本 + 单测通过 ruff/pytest；信号卡 `reports/research/signal-cards/ftd_*.{json,md}` 与 IC 表（含符号匹配率、丢弃比例）；若过关则最多 4 条候选的分档；登记簿 `dir:sec_fails_to_deliver_signal` 更新终态并 validate ok；覆盖地图 `alt_data.short_selling` 补一行由协调者更新（本任务不改 coverage.json）。
- notes:
  - 2026-09-29 23:35 UTC 自动轮完成：IC 闸门否定（175 个半月文件；FTD/股本、FTD/成交额 2024 起 RankIC |t| 最高 0.63，要求 ≥2.5；FTD>0 哑变量也平）。没建账本，"卖空信息"格子收口。产物 `reports/research/iterations/h20260929_72_sec_ftd/`、`scripts/fetch_sec_ftd.py`；登记簿 refuted。
  - 2026-09-29 23:12 UTC 自动轮（2681e20d）开始，派 sonnet-high 执行。
  - 2026-09-29 19:07 轮缺口搜索（gap-search-2026-09-29-19）添加。原文核对：SEC 数据页已打开（口径、字段、发布节奏来自该页）；文献效应量本轮没有读到原文（检索命中的 "Short-Sale Strategies and Return Predictability" 只读到片段，不引用数字），所以是 claim_only。

### T-20260929-80 比特币/以太币财库股（MSTR 等）和挖矿股相对币本身的价差：溢价回归还是延续（2024 起的近期状态，Beta 对冲的市场中性价差）
- status: done
- priority: 1
- not_before:
- goal: 现货比特币 ETF 上市（2024-01-11）之后，持币公司相对所持币的溢价/折价大幅波动：2024-03 溢价 2.6 倍（Kerrisdale 做空 MSTR、做多比特币 ETF），2024-11 再度扩张（MSTR 高点 $543），2025 压缩，2026-06 Strategy 企业 mNAV 首次低于 1（MSTR $82.31、BTC 约 $60.5k），2026-09-21 DWF 统计前 20 家财库公司只有 4 家高于持币价值（Strategy 0.97 倍，AlphaBriefing 同期给 1.12 倍，口径不同）。这是 2024–2026 特有的市场状态，且是对冲掉币价格 beta 的价差，预期与 S3 低相关（K2 候选）。反面证据：Haghani & White（Elm Wealth，2024-12）明确说不会持有"做多 BTC/做空 MSTR"，溢价可以持续甚至扩大（2021-02 曾到 3.9 倍），空头一侧尾部大；从业者叙述只有 1-2 个周期、作者自算（来源见登记簿 `dir:btc_treasury_miner_stock_vs_coin_relative_value`，五页均已打开）。本仓库没有测过股票对币的价差：T-33 只测 BTC 现货趋势，T-50 只测周末加密→指数 ETF（且全在缺口里）。问题：扣 10 bp 双腿成本和借券费之后，DAT/矿工股对币的价差回归（或延续）规则在 2024 起是否有 K1/K2 级别的净收益。
- plan: **数据本地已有（已亲自核对）**：`data/sip/daily/*/*.parquet`（列 symbol/timestamp/open/close…）中 MSTR（2016-01-04 起，2,700 行）、COIN、MARA、RIOT、CLSK（2020-01 起）、CIFR、WULF、HUT、IREN、CORZ、BMNR（2025-06-05 起，331 行）、FBTC（2024-01-11 起，681 行）、ETHA/FETH（2024-07-23 起）；`data/research/crypto/session_prices.parquet`（列 symbol/date/open/close，BTCUSD/ETHUSD 是美东 09:30 开、16:00 收对齐，BTC/ETH 自 2016-05）。**数据陷阱（写死）**：IBIT 在本地 2022-09-08 起就有 1,011 行，明显含更早的同代码旧证券，所以对冲腿一律用 FBTC（2024-01-11 起）或 IBIT 仅取 2024-01-11 起；SBET（2016 起 2,699 行）、XXI、NAKA 是代码复用，SBET 只取 2025-05-27 起且过价格连续性检查（相邻会话 |对数收益| >50% 且非拆股的丢弃并报告），XXI、NAKA 不用；MSTR 2024-08 的 10:1 拆股由 `sanitize_price_matrices` 默认参数处理，读行情一律 `scripts/run_capped.sh --mem 1.8G --`。本地**没有**持币量/mNAV 序列，且各来源 mNAV 口径不一致（同一天 0.97 对 1.12），所以第一版只用价格：DAT/币的价格比。**先预注册再算**：`direction-review.json` 引用 `dir:btc_treasury_miner_stock_vs_coin_relative_value`，迭代 `h20260929_80_dat_vs_coin`。价差定义：DAT 日收益 − β × 币腿日收益，β 为 60 会话滚动 OLS，截断到 [0.5, 3.0]；币腿 = 2024-01-11 起 FBTC（ETH 用 ETHA），此前用 session_prices 的 BTC 现货（每边成本 25 bp，标注"无 ETF 前只能用现货腿"）。三个配对：P1 MSTR/BTC、P2 挖矿篮子（MARA、RIOT、CLSK、CIFR、WULF、HUT、IREN、CORZ，等权、按各自上市日进入）/BTC、P3 ETH 财库（BMNR、SBET 2025-05-27 起，等权）/ETH，P3 只有对标窗（"待补压力期"）。信号两族（符号预注册）：Z 族 = log(DAT/币) 相对 L 日均值和标准差的 z，z ≥ +1.0 做空 DAT/做多币，z ≤ −1.0 反向，|z| ≤ 0.25 平仓，最长持有 60 会话，L ∈ {120, 250}（溢价高→回落，均值回归）；M 族 = 过去 K 日 β 对冲相对收益，|R| ≥ 10% 时持有与 R 同向的仓位（R<0，即 DAT 相对币走弱，则做空 DAT/做多币，预期继续走弱；R>0 则反向；持续/动量），K ∈ {20, 60}。每族 × 3 配对 × 侧别 {对称，只做空 DAT（这一侧才是发表的交易）} × 参数 = 12 + 12 = **24 条候选**（阈值 1.0/0.25/10% 固定，不调）。成交：收盘出信号、次日开盘成交；周频调仓看 5 个偏移的中位数；成本每边 10 bp（双腿），空头腿借券 3%/年（主），15%/年（敏感性，不算候选），另做 20 bp/边复核；DAT 与矿工股的借券在 Alpaca 是否易借未知，不能假定。**最便宜的否定测试（约 10 分钟，先于任何账本）**：对每个配对和每族信号，算信号与"之后 20 个会话的 β 对冲价差收益"的 Spearman IC，Newey-West（滞后 20）t，对标窗 2024-01-08→2026-09-17 和压力窗 2020-08-11→2023-12-29 分开报（P3 只有对标窗），另做 500 次随机日期安慰剂，并数对标窗内 |z|>1 的独立 episode（两次之间至少隔 20 会话）个数。**继续的条件（数字写死）**：至少一个配对在对标窗 IC 符号与预注册相同、|t| ≥ 2.0，压力窗（有数据时）同号，且对标窗独立 episode ≥ 6；否则停，写"证据不足/否定"，不建账本，不加变体。通过后走 `scripts/screen_lane.py`（参照 `scripts/screen_batches/h20260929_33_crypto_trend.py` 的口径），判定按运行手册第 5 节 K1/K2（K2 与 S3 组合增量 ≥0.05，对标窗和压力窗），DSR（24 次试验），随机入场日期安慰剂被超过的比例 ≤10%，15%/年借券下仍为正。**不做**：BTC 夜盘涨跌→DAT 次日开盘（T-50 已证明这类效应只在缺口里）、盘前盘后成交（T-35 成本口径未定）。
- done_when: IC 表（配对 × 信号族 × 窗口，含 t、安慰剂分位、episode 数、丢弃名单）写入 `reports/research/iterations/h20260929_80_dat_vs_coin/results.json`；若过关则 24 条候选分档、DSR、借券敏感性、K2；登记簿 `dir:btc_treasury_miner_stock_vs_coin_relative_value` 更新终态且 `oc research directions validate` 通过；`oc research direction-check` 和 `iteration validate --stage pre-backtest/final` 通过。
- notes:
  - 2026-09-29 缺口搜索（gap-search-2026-09-29-22，协调者任务代码 R0929-2207-D）添加。简报 `reports/research/intel/gap-search-2026-09-29-22.md`。原文核对：Substack 案例、Elm Wealth、BlockWest（DWF 报告转述）、The Defiant、AlphaBriefing 均已打开并读正文；Kerrisdale 原报告没找到可打开的地址（我试的 PDF 地址返回 404），其 2.57 倍等数字来自 Substack 转述（二手，claim_only）；github 检索 0 条相关代码；reddit 检索 0 条。
  - 2026-09-30 01:07 自动轮（协调者任务代码 R0930-0107-A）：done，evidence_too_weak。IC 闸门 12 格只有 P3 ETH 财库 Z120 过（IC −0.57，NW t −4.29，8 个 episode，全靠 2025-11→2026-08 一次溢价崩塌）；MSTR/BTC、矿工/BTC 每格 |t|≤1.19，MSTR 的 Z 回归在 2024 后符号反了（压力窗 IC −0.29/−0.40）。第二步 24 条 0 保留（23 reject、1 reject_placebo：P3_Z120_SYM 对标窗夏普 1.39/181 天，随机入场安慰剂 17.5%>10%，K2 −0.49，DSR 0.21）。产物 `reports/research/iterations/h20260929_80_dat_vs_coin/`（results.json、screen-results.json、report.md），脚本 `scripts/run_h20260929_80_dat_ic.py`、`scripts/run_h20260929_80_dat_screen.py`。重开条件：mNAV/持币量序列或第二个独立溢价周期。

### T-20260929-81 新股上市后的日历事件批量：25 天静默期到期前后的买入窗口，和首周冲高后的回落（本地已有事件表）
- status: done
- priority: 2
- not_before:
- goal: T-21 只测了 180 天解禁做空（否定，最好夏普 0.419）。IPO 后第 25 个日历日静默期到期、承销商分析师集中发起覆盖是另一个固定日期事件：Bradley、Jordan & Ritter（J. Finance 2003，已打开 PDF 全文）1996-2000 年 1,611 家 IPO，发起覆盖的公司在到期前后 5 日（-2,+2）异常收益 4.1%，未发起的 0.1%，收益集中在到期前几天；样本是泡沫期，2016 年后没有找到复现。日期在上市时就已知，不含事后信息。另一侧：Wolf Street（2025-12-29，已打开）称 2025 年有 202 个 IPO（不含 144 个 SPAC），最大 20 个里 14 个跌破发行价、11 个从盘中高点跌了 40% 以上，首日冲高后长期回落；做空侧受借券限制（新股通常借不到）。问题：在 2016-2026、尤其 2024 起（本地事件表里 424B4 确认的非 de-SPAC 新股 2024-2026 共 278 个）、扣新股价差和借券成本之后，这两个日历窗口是否还有净收益。
- plan: **数据本地已有（已亲自核对）**：事件表 `reports/research/iterations/h20260929_21_ipo_lockup_expiry/events.parquet`（列 symbol、ipo_date、method、accession、lockup_days、is_despac…；共 3,577 条，`method='424b4_confirmed'` 且非 de-SPAC 的按年数：2016 48、2017 73、2018 93、2019 89、2020 126、2021 221、2022 53、2023 65、2024 109、2025 147、2026 22）；行情 `data/sip/daily`（价格面板先过 `sanitize_price_matrices` 默认参数；T-21 已用的价格清洗和名称过滤直接复用）；成本分层复用 `scripts/run_h20260929_21_lockup_books.py`（top500 3 bp / 500-1000 6 bp / 1000-1500 12 bp / 1500+ 25 bp 每边，借券 top1500 3%/年、1500 以外 25%/年）。本地**没有**发行价，所以不能量"首日相对发行价的涨幅"；用"首个交易日开盘到第 5 个交易日收盘的累计收益 R5"当冲高代理，并在报告里写明这个口径缺陷。**先预注册再算**：`direction-review.json` 引用 `dir:ipo_quiet_period_expiry_and_post_pop_drift`，迭代 `h20260929_81_ipo_aftermarket`；样本只取 `424b4_confirmed` 且非 de-SPAC，首个收盘价 ≥ $5，前 10 个交易日成交额中位数 ≥ $5M；静默期日 QP = 首个交易日往后 25 个日历日之后的第一个交易日（Bradley 等：第 26 个日历日或其后第一个交易日为第 0 天）。候选 **12 条**：A 族做多窗口（QP-3 收盘出信号、次日开盘入场，出场在 QP+k 收盘）：(k ∈ {2, 5}) × 池 {全部合格样本，ADV 前 1,500 档}，再加入场提前一天的对照窗口（QP-2 收盘出信号、k=2）× 两个池 = 6 条；B 族"冲高后回落"做空：R5 ≥ +20% 的事件，第 6 个交易日开盘做空，持有 {20, 40} 个交易日 × 池 {全部，ADV 前 1,500 档} = 4 条，借券用上述分层价（新股借不到的风险写进报告，只当上限）；C 族镜像对照（不算候选）：R5 ≤ −10% 的事件做多同窗口。安慰剂：QP 日期整体平移 ±10、±60 个会话、随机日期，各 200 次（不算候选）。**最便宜的否定测试（约 10-20 分钟，先于任何账本）**：用 `open_composer.research.signal_card` 事件模式或直接写日历事件研究，报告 A 族窗口的市场调整累积收益（用 QQQ 与 IWM 等权作基准，Bradley 用纳指），按年分组，按 IPO 日期聚类的 t，扣每边分层成本之后的均值。**继续的条件（数字写死）**：A 族——2016-2026 合并扣成本均值 ≥ +1.0% 且 t ≥ 2.5，2024 起（n ≥ 100）均值 ≥ +1.0%，且平移 ±10 会话的安慰剂均值不超过真实均值的一半；B 族——2024 起扣借券和成本后做空 20 个会话净收益 ≥ +3%（t ≥ 2），且不能靠少数几只（去掉最大 3 笔盈利后仍为正）。两族都不满足就写"新股日历窗口收口"，登记为 refuted，不建账本；只有一族过关就只对该族走 `scripts/screen_lane.py` 和运行手册第 5 节 K1/K2、DSR（12 次试验）、20 bp 复核，K2 对 S3 的组合增量 ≥0.05。
- done_when: 年度 CAR 表、成本后均值和 t、安慰剂、去掉最大 3 笔的稳健性写入 `reports/research/iterations/h20260929_81_ipo_aftermarket/results.json`；登记簿 `dir:ipo_quiet_period_expiry_and_post_pop_drift` 更新终态并 validate ok；`direction-check` 和 `iteration validate` 两个阶段通过；报告里写明事件表 T-21 已知缺陷（抽样 30% 非普通股，已加名称过滤）在本任务如何处理。
- notes:
  - 2026-09-29 缺口搜索（gap-search-2026-09-29-22，协调者任务代码 R0929-2207-D）添加。原文核对：Bradley-Jordan-Ritter PDF 全文（已打开，数字来自摘要与正文）、Wolf Street 文章（已打开，只引用其 2025 年 IPO 统计，不引用未核对的逐只价格表以外内容）；ipo-hub 页只是搜索命中，claim_only。第二个 exa 检索一次遇到 429 后重试成功。
  - 2026-09-30 01:07 自动轮（R0930-0107-B）：done，refuted，新股日历窗口收口。过滤后 399 个 IPO（2024 起 88 个，达不到 n≥100）；FINRA 2241 在 2015-12 把静默期缩到 10 天，第 25 天在全样本里已不是规则日期。A 族 QP-3→QP+2 合并扣成本 −1.40%（t −2.21），2024 起 −3.84%；B 族 2024 起做空 20 会话 +10.55%（n=13，t 0.70），去掉最大 3 笔后 −11.75%。候选实际定义 10 条（plan 写 12，DSR 按 12 次，未用到）。产物 `reports/research/iterations/h20260929_81_ipo_aftermarket/`、`scripts/run_h20260929_81_ipo_aftermarket.py`。

### T-20260929-82 拆股公告后的漂移（美股，2016-2026，只做多，免费 EDGAR 8-K 文本建事件表）
- status: ready
- priority: 3
- not_before:
- goal: 拆股公告有文献支持的价格效应，但大小有争议：Titman、Wei & Zhao（2016 工作论文，已打开）美国 1998 年后样本，公告 3 日收益 3.32%，公告后前 60 日异常收益 3.21%（t=4.71），12 个月 DGTW 4.20%（t=3.16，约为 Ikenberry-Ramnath 早期样本 9% 的一半），作者提示与动量重叠（公司在上涨后拆股）。GitHub 上一个学生级 CRSP 复现（NathanArimilli24/stock-split-event-study，已打开，未评审）2000-2024 年公告日平均异常收益 +1.26%（t=13.2，N=3,076），第 6 个交易日左右就消失，除权日只有 +0.63% 且当天结束；2010 年代后每年不足 80 个，拆股公司中位市值到 2024 年约 $200 亿，2020/2022/2024 有苹果、特斯拉、亚马逊、英伟达等超大盘拆股。也就是说次日开盘买入大概率错过公告日反应，问题是公告后是否还有漂移。本仓库没有测过（登记簿没有拆股方向，只有别的异象 `nominal_price_anomaly_pwb`）。低换手、只做多、无借券成本，最便宜的否定测试半小时内。优先级 3：证据互相矛盾、样本每年只有几十个。
- plan: 数据：本地**没有**拆股列表（已检查 `data/features`、`data/raw`）；用免费 SEC EDGAR 全文检索建事件表，照 `scripts/collect_sec_ma_target_announcements.py` 的结构（限速、User-Agent、断点、季度 `form.idx` 交叉核对），检索词 "forward stock split"、"stock split in the form of a stock dividend"、"N-for-1 stock split" 等，表格 8-K，Items 5.03、8.01、7.01、3.03，2016-01→2026-09；排除含 "reverse stock split" 的文本；从正文抽拆股比例（只留 ≥ 2 比 1 的正向拆股）；保存 EDGAR 的 acceptanceDateTime 和文本命中片段，落 `data/features/sec_8k_stock_splits/`（先确认 `.gitignore` 覆盖；`data/sec/` 是别的会话在用，**不要往里写**）。抽样核对：随机读 25 条命中正文，误判率写进报告（T-03 是 8%）；误判率 >15% 就把限定词收紧后重抽，仍不行就标 `blocked_data`。**先预注册再算**：`direction-review.json` 引用 `dir:stock_split_announcement_drift_recent`，迭代 `h20260929_82_stock_split_drift`。入场规则（写死）：反应会话 = 若 acceptanceDateTime 在美东 15:30 之前则为当日，否则为下一个交易日；**入场 = 反应会话之后下一个会话的开盘**（不追公告日的跳空，也不用可能已被反应的价格）；参考上界（不可交易，不算候选）= 收盘后公告时在反应会话开盘入场。候选最多 **8 条**：持有 {20, 60} 个会话 × 池 {ADV 前 1,500 且价格 ≥ 5 美元，全部可映射标的} × 基准 {SPY 调整，SPY 加 IWM 等权}。对照（不算候选）：把同一批事件的公告日随机移动 ±126 个会话的安慰剂；以及按公告前 126 日收益十分位匹配的动量对照（Titman 等自己提示的混杂）。价格面板先过 `sanitize_price_matrices` 默认参数；拆股当天的价格跳变会被它标成可疑会话，**要把拆股除权日本身保留**（用复权价或跳过除权日的收益，写清楚用哪一种），读行情一律 `scripts/run_capped.sh --mem 1.8G --`。**最便宜的否定测试（数据建好后约 10 分钟，先于任何账本）**：`signal_card` 事件模式（同 T-03），持有 20 与 60 日，报全样本、2019 起、2024 起的 CAR、t、事件数。**继续的条件（数字写死）**：ADV 前 1,500 池可用事件 ≥ 40（2019-2026），入场后 20 会话 SPY 调整 CAR 均值 ≥ +1.0% 且 t ≥ 2.0，2024 起（n ≥ 15）符号为正，且高于动量匹配对照 ≥ 0.5 个百分点。任一不满足就停，登记为 refuted/evidence_too_weak，不建账本。通过后才走 `scripts/screen_lane.py` 和第 5 节 K1/K2、DSR（8 次试验）、20 bp 复核；事件太少时按"近期观察"上限处理，不能保留。
- done_when: 事件表建好并有抽样核对记录（误判率、事件数按年）；两张 signal card 或 CAR 表（20 日、60 日；全样本、2019 起、2024 起；安慰剂和动量匹配对照）写入 `reports/research/iterations/h20260929_82_stock_split_drift/results.json`；登记簿 `dir:stock_split_announcement_drift_recent` 更新终态并 validate ok；`direction-check` 与 `iteration validate` 通过。
- notes:
  - 2026-09-29 缺口搜索（gap-search-2026-09-29-22，协调者任务代码 R0929-2207-D）添加。原文核对：Titman-Wei-Zhao PDF 全文（已打开，数字来自摘要与正文）、GitHub 复现 README（已打开，学生项目，数字只当方向）；Gharghori & Nguyen（澳大利亚样本）页面被验证码拦截，只见搜索片段，claim_only，数字不引用。

### T-20260930-01 机构 60/40 再平衡的抢跑信号：用 SPY 对 10 年债的收益推算再平衡压力，只交易股票腿（低 Beta，机制是被迫的资金流）
- status: done
- priority: 1
- not_before:
- goal: Harvey、Mazzoleni、Melone（NBER w33554，2025-03，2026-01 修订版，已打开全文）：用 SPX 和 10 年期国债日收益模拟 60/40 组合的权重偏离，股票超配（机构要卖股买债）时次日股票收益下降 17 个基点；按信号做多股票/做空债券的价差组合，1997-09-10→2023-03-17 夏普 1.11（年化 10.20%，波动 9.17%），剔除 2008-09→2009-03 和 2020-03 后 0.90，论文称扣他们的期货成本后仍接近 1，高摩擦时期更强。独立复现（QuantReturns，2025-07-03，已打开）：期货版 2007-01→2025-06 夏普 1.42，SPY/TLT 的 ETF 版同期 CAGR 15.62%、波动 13.13%、夏普 1.17、Beta 0.12，未计成本、两条腿都交易。这是本轮唯一在 2007 年后样本里有夏普 >1 的公开记录，且和 S3 预期低相关（K2 候选）。反面证据：Kent Daniel 的评论（2025 Red Rock，已打开）指出信号窗口的多重比较偏差没有校正、他估计的 $160 亿年成本是最坏情形、类似的流动性提供类异象（指数纳入、短期反转、杠杆 ETF）历史上都随竞争消失；Parker-Schoar-Sun 的目标日期基金持仓显示预测再平衡里约 45% 在当月、25% 在下月完成，说明压力不只发生在次日。登记簿 `dir:index_rebalance_flow_prediction`（not_executable，2026-09-28）写"论文只有资金流可预测性、没有策略夏普、要再平衡日历"，这两点都被 2026-01 修订版（第 5 节明确规则和夏普）和本任务的纯收益信号推翻，所以重开；差异写进 direction-review。冲突要写明：价差组合有债券腿，机主 2026-09-28 否决了跨资产，所以主候选只交易股票腿，价差版只当诊断，不做模拟盘用途，除非机主另行决定。
- plan: **数据本地已有（已亲自核对）**：`data/sip/daily/*/*.parquet`（列 symbol/timestamp/open/close）里 SPY、TLT、IEF、AGG、QQQ、TQQQ、SQQQ 各 2,700 个会话，2016-01-04→2026-09-29；SH 2,579 个会话，2016-06-27 起。不需要新数据。先核对 SPY/IEF/TLT 的收盘价是否含分红（和 `data/research/longbridge_adjusted_daily` 里同代码的复权价比；不含就在报告里写明债券腿少算的票息，债券腿只是诊断，不影响股票腿）。**先预注册再算**：`direction-review.json` 引用 `dir:pension_rebalancing_front_run_equity_leg`（写明与 `dir:index_rebalance_flow_prediction` 的差异），迭代 `h20260930_01_rebalancing_front_run`，候选清单写死后再算任何结果。信号（按论文第 1.2 节和 Daniel 幻灯片，写死）：模拟组合权重 w(t+1) = w(t)(1+R_SPY) / [w(t)(1+R_SPY) + (1−w(t))(1+R_IEF)]，目标 60%，用收盘到收盘收益；**Threshold 信号**：对 δ ∈ {0.1%, 0.2%, …, 2.5%} 共 25 个阈值各模拟一个组合，t 日收盘偏离 dev = w(t) − 0.60（再平衡前的权重），|dev| > δ 时该 δ 的信号 = dev 且该组合在 t 日收盘被重置为 0.60，否则信号 0；Threshold = 25 个信号的均值；**Calendar 信号**：另一个组合只在每月最后一个交易日重置为 0.60，t 日信号 = w(t) − 0.60，只在月末最后 5 个会话内启用（前 4 个会话取 −sign，最后一个会话取倒数第 5 个会话值的反号，照 QuantReturns 的写法，执行者在候选清单里把这个写成公式再动手）；权重 W = 0.6×(−Threshold/0.012) + 0.4×CalendarMod；论文口径的价差收益 = W(t−1)×(R_SPY − R_IEF)，收盘到收盘（**不可交易的参考，不算候选**）。**成交（冻结合同）**：t 日收盘出信号，t+1 日开盘成交；持有到 t+1 收盘（open→close 腿）或 t+2 开盘（open→open）。候选 **8 条**：R1 价差 SPY−IEF，W 全量，|W| 截到 2；R2 价差 SPY−TLT（QuantReturns 的写法，同截断）；R3 只股票腿：SPY，方向 = sign(W)，仓位 = min(|W|, 1)，负向做空 SPY；R4 同 R3 用 QQQ；R5 同 R3 用 TQQQ（W>0）/ SQQQ（W<0）三倍对；R6 R3 但只在 |W| ≥ 1 的日子交易（阈值不调）；R7 R1 但只在 |W| ≥ 1 的日子交易；R8 只用 Calendar 部分的股票腿（SPY）。成本每边 10 bp、按每条腿的仓位变化量计，20 bp 复核，SPY/QQQ 空头借券 0.3%/年（敏感性 3%/年）。**最便宜的否定测试（约 15 分钟，先于任何账本）**：对 SPY、SPY−IEF 分别回归"下一日收益"在 Threshold 信号上的系数（HC3 标准误），把下一日收益拆成隔夜（t 收盘→t+1 开盘，冻结合同下拿不到）和日内（t+1 开盘→收盘，拿得到）两段，全样本 2016-01→2026-09、压力窗 2016-05→2023-08、对标窗 2024-01-08→2026-09-29 分开报，再报 Calendar 部分同样的三段；另做 500 次把信号日期随机平移 ±10~±60 会话的安慰剂。**继续的条件（数字写死）**：日内腿上 Threshold 系数符号与论文相同（股票超配→次日股票收益更低）、全样本 t ≤ −2.5，对标窗同号且 |t| ≥ 2.0；且至少一条只交易股票腿的候选（R3-R6、R8）10 bp 后的净夏普 ≥ 0.8（全样本）和 ≥ 0.8（对标窗）。如果效应主要在隔夜腿，写"在次日开盘成交下拿不到"并收口。通过后走 `scripts/screen_lane.py`，判定按运行手册第 5 节 K1/K2、DSR（8 次试验）、20 bp、随机日期安慰剂 ≤10%；价差版 R1/R2/R7 即使更好也只报给协调者，等机主对债券腿的决定。**不做**：期货版（Alpaca 无期货）、任何指数再平衡日历数据。
- done_when: 回归表（信号 × 三段收益 × 三个窗口 × HC3 t × 安慰剂分位）和 8 条候选的净夏普写入 `reports/research/iterations/h20260930_01_rebalancing_front_run/results.json`；SPY/IEF/TLT 收盘是否含分红的核对结果；登记簿 `dir:pension_rebalancing_front_run_equity_leg` 更新终态且 `oc research directions validate` 通过；`direction-check` 和 `iteration validate` 两个阶段通过。
- notes:
  - 2026-09-30 缺口搜索（gap-search-2026-09-30-01，协调者任务代码 R0930-0107-G）添加。简报 `reports/research/intel/gap-search-2026-09-30-01.md`。原文核对：NBER 全文（已打开，夏普、−17bp、剔除危机期 0.90 来自正文）、Kent Daniel 幻灯片（已打开）、QuantReturns 复现（已打开，作者自算未评审，无成本）；Parker-Schoar-Sun 的 45%/25% 来自 Daniel 幻灯片转述，claim_only。
  - 2026-09-30 01:07 自动轮（R0930-0107-C）：done，refuted（回归闸门）。SPY 日内段对 Threshold 信号：全样本系数 −0.52（HC3 t −2.84）、压力窗 t −2.68，对标窗 t −0.84（要求 |t|≥2）；价差诊断版对标窗 t −1.15。回归隐含毛收益 1.36 bp/日，10 bp 成本约 2.47 bp/日。非闸门观察：组合 W 与 CalMod 对标窗 t +1.99/+2.09——已在对标窗上看过，只能用 2026-09-18 以后的新留出另立合同。本机 SIP 日线已是分红复权。产物 `reports/research/iterations/h20260930_01_rebalancing_front_run/`、`scripts/run_h20260930_01_rebalancing.py`。

### T-20260930-02 行业相对信号批量：用免费 SEC SIC 建行业表，测行业动量、行业中性股票动量和同行业财报溢出（个股，ADV 前 1,500，多空、行业中性）
- status: ready
- priority: 2
- not_before:
- goal: 覆盖地图 `trend_momentum.stock_momentum` 写着"行业相对动量从未在本地测过，卡在没有行业分类"；本轮确认分类可以免费拿：SEC `company_tickers.json` 今天返回 200、10,431 行，`data.sec.gov/submissions/CIK0001045810.json`（NVDA）返回 sic 3674。文献（只有 Springer 综述转述，原论文没读，数字标 claim_only）：Moskowitz-Grinblatt 1999 行业动量 0.43%/月（1963-1995），扣掉行业后的个股动量只剩 0.13%/月；Grundy-Martin 加 1 个月间隔后降到不显著的 0.16%/月；Grobys-Kolari 2020（48 个行业，1926-2018）0.62%（1-0-1）、0.57%（6-1-1）、0.80%（12-1-1）/月，月度 alpha 0.56%，没有动量崩盘的期权性。Hou 2007（摘要已打开）：大公司领先小公司主要发生在行业内，由对负面信息的迟缓调整驱动，小型、竞争弱、被忽视的行业更明显，和大公司财报后小公司漂移相关；Baker 等 2019（摘要已打开，1996-2015）：同行业同行的财报新闻和本公司在其公告日的收益正相关。反面证据：Arnott 等（因子动量，摘要已打开）说行业动量在一个月周期最强但被因子动量吸收，不是独立来源；Management Science 的"Tail Wags the Dog"称跨行业扩散可能是假象（只读到标题和页眉，claim_only）；ETF 层面的行业轮动（`dir:narrow_industry_etf_momentum_rotation`）已被否定，但那是纯多头 top-N，不是行业中性多空。文献的量级（约 0.4-0.8%/月，总的）只略高于个股层面月度双腿成本，所以先验偏低，价值在于一次建好行业表，同时解锁其他行业中性方向。
- plan: **数据（已亲自核对）**：行情 `data/features/daily_broad/*.parquet`（13,733,586 行、9,191 个代码、2016-01-04→2026-09-17）用来定 ADV 前 1,500 的池；价格面板从 `data/sip/daily` 读并先过 `sanitize_price_matrices` 默认参数（拆股、坏价、代码复用），读行情一律 `scripts/run_capped.sh --mem 1.8G --`，按年分块只取池内代码。财报事件 `data/features/earnings_events/*.parquet`：16,015 行、1,448 个代码、acceptance_utc 2024-01-02→2026-09-17、fetch_status='ok' 14,923 行。**新增数据**：行业表。用 `company_tickers.json` 把池内代码映射到 CIK，再对映射到的 CIK 请求 `data.sec.gov/submissions/CIK##########.json` 取 sic（估计约 3,500 次，单线程 ≤5 次/秒、User-Agent 写描述性、遇 429 退避、断点续跑，约 12-15 分钟）；再下载 Ken French 的 48 行业 SIC 区间文件 `Siccodes48.zip` 得到 FF48；写 `scripts/fetch_sec_sic_map.py`（分页/退避/断点用假响应单测），落 `data/features/sic_map/sic_map.parquet`（先确认 `.gitignore` 覆盖；`data/sec/` 是别的会话在用，不要往里写）。已知缺陷（写进报告）：company_tickers 只含当前代码，已退市和复用代码会缺失或错配，报告缺失占比（按年）和按 `sip-delisted` 的补救；SIC 是当前值不是 PIT；行业成员少于 15 的 FF48 行业当月丢弃。**先预注册再算**：`direction-review.json` 引用 `dir:industry_relative_momentum_and_peer_earnings_spillover`，迭代 `h20260930_02_industry_relative`。池：ADV 前 1,500、价格 ≥ 5 美元、排除基金。信号族（符号预注册为文献方向）：I1 行业 1 个月动量：FF48 行业等权收益的过去 21 会话，做多前 5 名行业的全部成员、做空后 5 名，月频；I2 行业 12-1 动量（过去 252 会话跳过最近 21）同样做法；I3 行业中性个股 12-1 动量：个股 12-1 收益减所在行业均值，十分位多空；I4 同行业财报溢出（只有 2024-01 起）：t 日对股票 i，取过去 5 个会话内同行业、财报反应会话收益（用 acceptance_utc：美东 16:00 之前为当日，之后为下一交易日；取前一收盘→反应会话收盘、减 SPY）的均值，至少 2 个同行且不含本公司，排除自己今天有财报的股票；做多最高五分位、做空最低五分位，持有 5 和 20 会话。候选 **10 条**：I1{多空，仅多头 top5}、I2{多空，仅多头}、I3{十分位多空，仅多头最高十分位}、I4{持有 5，持有 20}×{多空，仅多头}。成交：收盘出信号、次日开盘成交，月频调仓看 21 个偏移的中位数，I4 按事件持有；成本用 `scripts/run_h20260929_21_lockup_books.py` 的分层价（前 500 3 bp、500-1000 6 bp、1000-1500 12 bp 每边），空头借券 3%/年（ETB 名单本地没有，标注"未核对易借"），20 bp 复核。**最便宜的否定测试（表建好后约 15 分钟，先于任何账本）**：对每个信号族算 Spearman IC 和最高五分位减最低五分位的毛收益价差，对 21 会话（I4 为 5 和 20）的行业相对收益，对标窗 2024-01-08→2026-09-17 和压力窗 2020-08-11→2023-12-29 分开报（I4 只有对标窗），Newey-West（滞后 = 持有期）t，500 次随机打乱行业标签的安慰剂。**继续的条件（数字写死）**：至少一个族在对标窗 IC 符号与文献相同、|t| ≥ 2.0，压力窗同号（I4 除外），毛价差 ≥ 0.80%/月（I4 ≥ 0.30%/5 会话），且安慰剂 IC 分位在 95% 之外；否则写"行业相对信号收口"，登记 refuted，不建账本。通过后对通过的族走 `scripts/screen_lane.py` 和第 5 节 K1/K2、DSR（10 次试验）、20 bp、随机日期安慰剂；K2 对 S3 的组合增量 ≥ 0.05。SIC 表建好后在 notes 记一行，方便行业中性的别的方向复用。
- done_when: `data/features/sic_map/sic_map.parquet` + 抓取脚本和单测（ruff/pytest 通过）+ 缺失占比表；IC 表（信号族 × 窗口，含 t、安慰剂分位、毛价差）写入 `reports/research/iterations/h20260930_02_industry_relative/results.json`；过关族的 10 条候选分档、DSR、K2；登记簿 `dir:industry_relative_momentum_and_peer_earnings_spillover` 更新终态且 `oc research directions validate` 通过；`direction-check` 和 `iteration validate` 两个阶段通过；覆盖地图 `trend_momentum.stock_momentum` 的"行业相对"一行由协调者更新。
- notes:
  - 2026-09-30 缺口搜索（gap-search-2026-09-30-01，协调者任务代码 R0930-0107-G）添加。原文核对：Springer 综述（已打开，Moskowitz-Grinblatt、Grundy-Martin、Grobys-Kolari 的数字是综述转述）、Hou 2007 摘要、Baker 等摘要、Arnott 等摘要与引言均已打开；Hong-Torous-Valkanov 的说明是行业对大盘的领先，不是本任务的信号，未采用；"Tail Wags the Dog"只读到页眉，claim_only。exa 检索的 6 页里只有摘要，原论文全文多数付费墙。

### T-20260930-03 年末税损卖出后的反弹：年内跌幅最大的股票 12 月中旬买入、持有到 1 月底，和市场对冲后的超额（十个 12 月窗口，几乎零换手）
- status: ready
- priority: 3
- not_before:
- goal: Ivkovic、Poterba、Weisbenner（NBER w10275，已打开全文）用个人投资者逐笔交易数据证明税损卖出全年存在，12 月最明显，尤其是当年在别处有已实现收益的账户。价格层面的结论只有实务摘要：Globe and Mail（2025-12-11）称 TSX 年内跌幅超 15% 的股票在 11 月中到 12 月中跑输近 4%、12 月中到 1 月中跑赢 3.6%，但正文付费墙打不开、又是加拿大样本，claim_only，不当效应量；JFIR "Tax-loss selling and the January effect revisited" 被 403，只有搜索片段说 1 月效应在减弱（更多免税账户），claim_only。也就是说"税损卖出存在"有原文，"美股 2016 后的反弹幅度"没有任何打开的来源，先验低；价值是这个窗口在 2026-12-15 前必须有结论，测试免费、换手近零、可以和 IWM/SPY 对冲，和 S3 应当低相关。
- plan: **数据本地已有（已亲自核对）**：`data/sip/daily`（美股日线 2016-01-04→2026-09-29），信号窗口 2016-12-15…2025-12-15 共十个，出场最晚 2026-01-30 也在数据里。不需要新数据。价格面板先过 `sanitize_price_matrices` 默认参数，读行情用 `scripts/run_capped.sh --mem 1.8G --`。**先预注册再算**：`direction-review.json` 引用 `dir:tax_loss_selling_year_end_rebound`，迭代 `h20260930_03_tax_loss_year_end`。池：信号日 ADV 前 1,500、价格 ≥ 5 美元、排除基金（复用 T-21 的名称过滤）。信号：年内收益 YTD = 12 月 15 日收盘 / 上年最后一个交易日收盘 − 1。主窗口 W2：12 月 15 日收盘出信号，16 日（或其后第一个交易日）开盘入场，出场 {1 月 15 日，1 月 31 日} 收盘（或前一个交易日）。候选 **6 条**：{YTD 最低十分位}×{池 ADV 前 1,500，池 ADV 排名 500-1,500}×{出场 1/15，1/31}（4 条）+ {YTD ≤ −30%}×{池 ADV 前 1,500}×{出场 1/15，1/31}（2 条，阈值不调）。收益用池等权作基准（另报 IWM 对冲），成本按分层价（前 500 3 bp、500-1000 6 bp、1000-1500 12 bp 每边，来自 `scripts/run_h20260929_21_lockup_books.py`）。诊断窗口 W1（11 月 15 日出信号，12 月 15 日出场，预期跑输，只用来看方向，不算候选，做空侧未核对易借）。安慰剂窗口（不算候选）：同样构造放在 2 月 15 日→3 月 31 日、6 月 15 日→7 月 31 日，各十年。**最便宜的否定测试（约 10 分钟，先于任何账本）**：十个年度的 W2 等权超额收益表、扣成本后均值、按年聚类的 t、正年份数、去掉最好一年后的均值，2024 起（Dec 2024、Dec 2025 两个窗口）单列，再对比两个安慰窗口。**继续的条件（数字写死）**：12 月 16 日→1 月 31 日的超额均值（扣分层成本后）≥ +1.5%，十年里 ≥ 7 年为正，按年聚类 t ≥ 2.0，两个安慰窗口均值合计不超过真实值的一半，2024 起两个窗口都为正。任一不满足就写"税损反弹收口"，登记 refuted，不建账本、不调阈值。通过也只有十个观察，只能标"近期观察"上限，2026-12-15 的窗口是真正的样本外，通过后把它写成 not_before 2026-12-15 的前向跟踪任务，不得直接上模拟盘。
- done_when: 十窗口年度表、成本后均值/t/正年份数、两个安慰窗口、2024 起窗口写入 `reports/research/iterations/h20260930_03_tax_loss_year_end/results.json`；登记簿 `dir:tax_loss_selling_year_end_rebound` 更新终态且 `oc research directions validate` 通过；`direction-check` 和 `iteration validate` 两个阶段通过。
- notes:
  - 2026-09-30 缺口搜索（gap-search-2026-09-30-01，协调者任务代码 R0930-0107-G）添加。原文核对：NBER w10275 已打开（摘要和全文）；Globe and Mail 付费墙、JFIR 403，均 claim_only。exa 检索六页里只有摘要，没有美股 2016 年后的效应大小，是本任务先验低的原因。
