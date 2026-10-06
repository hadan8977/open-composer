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
- status: done
- priority: 1
- not_before:
- goal: 机主 2026-09-29 把研究范围放到 Alpaca 模拟盘能交易的全部品种（含做空）。跳空回补 2016–2021 扣成本前年化 99%、夏普 3.0，收益在空头腿，当时只因不能做空而停。
- plan: 核对 Alpaca 做空/借券/保证金规则；重新分级所有因做空被判不可执行的方向；跳空回补做多空和"只做空 + 买 SPY 对冲"两种，空头只用容易借的股票，按价差和借券费扣成本，按成交额分档报告。
- done_when: `reports/research/control/short-unlocked-retriage-2026-09-29.md`、`reports/research/iterations/t20260929_32_gap_fade_ls/`；登记簿更新；提交。
- notes:
  - 2026-09-29 交互会话派 Sonnet 在做，自动轮不要碰。
  - 2026-09-30 13:52 交互主审（Opus）：产物和提交已在（`reports/research/control/short-unlocked-retriage-2026-09-29.md`、`reports/research/iterations/t20260929_32_gap_fade_ls/`，提交 bd526ff）；结论已进纲领主线 C（跳空回补整族于 2026-09-30 关闭）。状态从 running 补成 done。

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
### T-20260929-35 日内截面规律之一：隔夜延续 × 竞价执行（Lou-Polk-Skouras 拉锯的隔夜腿；同时段周期性拆到 T-20260930-13）
- status: done（已主审 2026-09-30 11:50：判定格关闭；ON252 另立 T-20260930-14）
- priority: 1
- not_before:
- goal: 已发表的截面日内规律，例如 Heston-Korajczyk-Sadka 2010 的同一时段收益延续，以及 Lou-Polk-Skouras 2019 的"动量赚在隔夜、反转赚在日内"，在流动性最好的股票上能否扣掉实际成本后赚钱。
- plan: 先联网找 2020 年以后的复现；成本按分钟数据估计的价差另建日内合同，同时报告冻结的 10/20 bp。
- done_when: 迭代档案 + 登记簿 + 提交。
- brief: reports/research/control/briefs/T-20260929-35.md
- notes:
  - 2026-09-30 交互会话（Opus）解除阻塞，属于纲领 C2（`docs/research-program.zh.md` 主线 C）。成本合同由 Opus 定，不再等机主：逐只实测价差 + 2 bp，且 2 倍成本下仍须通过；同时报告冻结的 10/20 bp。先算毛收益，毛收益低于 2 倍往返价差就直接否定。优先级排在纲领 C1（T-20260930-11）之后。
  - 2026-09-30 07:07 自动轮（Opus）：C1、C1b 已关闭，跳空回补整族关闭；本任务现在是纲领主线 C 的唯一剩余深挖实验（纲领 C2），提为 priority 1。下一轮执行前由 Opus 先写预注册（机制、池、成本合同按上面 notes、最便宜的否定：毛收益 < 2 倍往返实测价差即否定）。注意免费行情是 IEX 实时 + SIP 15 分钟延迟，任何需要 09:30 后实时信号的规则要按可见时刻选股。
  - 2026-09-30 09:00 交互会话（Opus 主审）：预注册写死在 `reports/research/iterations/t20260929_35_overnight_persistence/hypotheses.md`，执行简报 `reports/research/control/briefs/T-20260929-35.md`。本任务只测隔夜腿：按过去隔夜收益十分位多空，收盘竞价进、次日开盘出，判定格 ON21_P1500_LS 主窗毛均值 ≥16 bp/晚通过、<8 bp 关闭（竞价每边 2 bp，2 倍 4 bp）。同时段周期性（HKS）拆到 T-20260930-13。执行轮先做本任务（重任务），T-13 在本任务的 panel 之后。
  - 2026-09-30 10:07 执行轮（Sonnet 5.5，R0930-1007）开始：子代理按简报执行。
  - 2026-09-30 10:57 执行轮：子代理跑完 panel + screen，pre-backtest 检查通过（10:12:19Z，早于 results.json generated_at 10:55:37Z），hypotheses.md 未改。字段齐全（results.json）。判定格 ON21_P1500_LS 主窗 2.56 bp/晚、t_nw5 0.66、n 683、placebo_beat 1.00、tier closed、stress_class recent_only（压力期 4.81 bp、t_nw5 2.98）、竞价 2 倍成本净 -13.89 bp/晚；第二格 ON5_P1500_LS -4.62 bp、t_nw5 -1.02、placebo_beat 0.00、tier closed、recent_only、2 倍净 -21.07。诊断：(a) 同一组合次日日内 -13.70 bp（t_nw5 -3.17），(b) P1500 按过去日内排序的下一晚 -3.84 bp（t_nw5 -1.18）。LO 前 20 主窗绝对 -0.84 bp、超额（对池等权）-7.59 bp。子代理备注（非判定）：ON252_P1500_LS 11.99 bp（t_nw5 3.08）、ON252_P500_LS 17.01 bp（t_nw5 3.24）在冻结判定格之外，20 次试验之一；placebo_beat=1.00 是因为随机组合市场中性、波动远小于真实组合（按冻结设计）；AR 价差中位数 38 bp，连续竞价成本列约 -150 bp；子代理自选了 4 项口径（先 dv21 排名再 $5/63 日过滤、腿大小 floor(10%)、价差 NaN 用当晚池中位数、诊断 (b) 用 t-21..t-1 日内均值），已写进脚本 docstring 和 report.md。未做：官方竞价价抽样（无格通过或边缘）；`--stage final` 检查（卡在试验账本和 decision record，属主审）。待主审。产物：`reports/research/iterations/t20260929_35_overnight_persistence/`（results.json、report.md、cache/panel.parquet）、`scripts/run_t20260929_35_overnight_persistence.py`、`tests/test_t20260929_35_overnight_persistence.py`、`strategy_specs/drafts/t20260929_35_overnight_persistence.yaml`、`reports/harness/source_cards/t20260929_35_overnight_persistence.jsonl`、`logs/t20260929_35_*.log`。
  - 2026-09-30 11:50 主审（交互会话 Opus）：对照 results.json 并用 cache/panel.parquet 独立重算（差值 ≤0.05 bp，AAPL 抽查 r = close_t→open_{t+1} 对齐无前视）。**判定格 ON21_P1500_LS 关闭**：主窗 +2.56 bp/晚（NW t 0.66），<8 bp；第二格 ON5 −4.6 bp 关闭；压力期 ON21 +4.8 bp（t 2.98）→ 一月口径的隔夜延续在 2016–23 就只有竞价成本的一半，2024 起更弱。拉锯仍在：同一组合次日日内 −13.7 bp（t −3.2）。死因：短窗口信号太弱，不是执行。**只报告的 ON252（过去一年）格强**：P500 LS 主窗 +17.0 bp（t 3.26）、压力期 +7.6（t 3.30）；P1500 +12.0（t 3.08）/ +8.6（t 5.35）；与 Lachance 2023「过去一年隔夜收益是最强预测变量」一致。它是 20 格之一且两窗都已看过，不能算通过 → 另立 T-20260930-14（没看过的 dv21 1501–3000 池 + 官方竞价价核对）。另：本任务 continuous_1x/2x 净值作废（日线 AR 价差对大盘股高估 20–60 倍，见 T-13 修正案 A1）。

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
- status: superseded（→ T-20260930-17）
- priority: 1
- not_before:
- goal: 机主 2026-09-29："XGBoost 等其他模型不行吗，多试一些，用最大的努力"。用证据回答：同一批数据上换模型族、训练窗（3 年/1 年滚动）、预测周期（5/21/63 天）能否得到可交易的排序。
- plan: 36 个组合，只按压力期 RankIC t 值选前 3（2024 年以后的数字只报告不参与挑选），前 3 做成扣价差成本的只做多组合，按 K1/K2 判；DSR 试验次数 42。Modal ≤ $3。
- done_when: `reports/research/iterations/t20260929_30_model_zoo/`；登记簿行 `dir:ml_model_zoo_stock_ranking_2026`；提交。
- notes:
  - 2026-09-29 交互会话派 Sonnet 在做，自动轮不要碰。
  - 2026-09-30 13:52 交互主审（Opus）：09-29 起没有任何产物（迭代目录、intel、Modal 账本、进程都没有），视为中断。由 T-20260930-17 接手，原块保留。

### T-20260929-31 强化学习与"大模型 + 强化学习"（Qwen/GRPO 等）交易证据
- status: superseded（→ T-20260930-18）
- priority: 1
- not_before:
- goal: 机主问"RL 的 Qwen 之类的不行吗"。先读 2025–2026 原文和实盘记录（nof1 Alpha Arena、LiveTradeBench、Trading-R1、FLAG-Trader、FinRL 比赛），只有证据支持才定一个 ≤ $3 的试点。
- plan: 只调研；简报 + 登记簿。
- done_when: 简报在 `reports/research/intel/`；登记簿 validate ok；提交。
- notes:
  - 2026-09-29 交互会话派 Sonnet 在做，自动轮不要碰。
  - 2026-09-30 13:52 交互主审（Opus）：09-29 起没有任何产物，视为中断。由 T-20260930-18 接手（交互会话子代理在做），原块保留。

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
- status: superseded（2026-10-01：股票层面的批量筛选由组合线取代）
- priority: 2
- not_before:
- goal: 批量通道（T-20260928-03，交互会话在做）只覆盖 ETF。T-20260928-06 重判出的股票层面方向（几百到几千只股票的截面规则）本机内存放不下，在 Modal 上用同一套判定（偏移中位数夏普、同波动 S3 对比、DSR）分片并行跑。
- plan: 复用 `scripts/screen_lane.py` 的指标函数，不另写一套判定；每批 10–30 条，每条一个容器。每批 Modal 花费上限 $1（预计 $0.3–0.5）；只有候选超过本机内存时才上 Modal，ETF 级别的一律本机跑。
- done_when: 每批一个迭代档案，`--stage final` 通过；保留的写进 `reports/research/screens/kept.jsonl`。
- notes:
  - 2026-09-28 03:20 UTC 交互会话（研究）：批量通道已上线（`reports/research/screens/SELF_CHECK_OK`）。股票层面的 25 个方向正由迭代 `h20260928_06_registry_stock_batch3` 在本机测（最大 500 只、20 日重叠持仓，复用 `open_composer.research.signal_card`）；需要更大股票池、本机内存放不下的候选会在它的报告里标 `needs_modal`，本任务只接这些，不重复测本机已测的。
  - 2026-10-01 06:42 UTC 交互会话（Opus）：组合线（`docs/equity-book-design.zh.md`）用统一的面板、风险模型和优化器评估信号，不再做股票层面的单独批量筛选。

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
- status: done
- priority: 1
- not_before:
- goal: 在 DeepSeek 训练截止之后的月份里，检验"LLM 读上个月新闻，给动量前两成的股票打分，再选 50 只"是否比原版动量夏普高至少 0.10，且配错新闻的安慰剂复现不了。
- plan: 迭代 h20260928_22_llm_news_momentum_filter。DeepSeek 打分，新闻去掉公司名和代码；四个组合：原版 B、LLM 版 L、安慰剂 P、随机 R；成本 10/20bp。
- done_when: `--stage final` 通过；登记簿 `dir:llm_acceptance_judge_forward_shadow` 和第 2 篇的行已更新；通过了才加月度影子跟踪任务。
- notes:
  - 2026-09-28 06:4x UTC 交互会话派 Sonnet 执行。自动轮不要碰。
  - 2026-09-30 19:21 UTC 交互主审（驾驶舱核对时发现）：本任务已于 2026-09-29 02:41 完成并提交（d446d41，两项预注册检验均否定，登记簿已更新），状态一直没回写，仍显示 running。改为 done，不改结论。

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
  - 2026-09-30 18:41 交互主审：T-64 机主决定不买付费期权数据。本任务只在出现免费数据或新合同时重开。
  - 2026-10-05 13:38 UTC 13:07 主审轮：免费密集段的新合同已立，`t20261005_p6_iv_signals`（数据门 T-20261005-44，测量 T-20261005-45）。注意本任务计划里 IVRV 的方向写反了：Bali–Hovakimian 2009 是"已实现减隐含与未来收益负相关"，即做多隐含高于已实现的股票；"HV 高于 IV 者做多"是 Goyal–Saretto 买期权的方向。本任务保持 blocked，不再执行，以新合同为准。

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
  - 2026-09-30 18:41 交互主审：T-64 机主决定不买付费期权数据。本任务只在出现免费数据或新合同时重开。

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
  - 2026-09-30 18:41 交互主审：T-64 机主决定不买付费期权数据。本任务只在出现免费数据或新合同时重开。

### T-20260929-64 机主决定：若 DoltHub 期权数据质量不够，是否购买历史期权买卖报价
- status: done（机主 2026-09-30 决定：不买）
- priority: 3
- not_before:
- goal: 只有 T-60 判 DoltHub 免费库"不通过"（覆盖率、时间点、价差或坏报价没达到预注册标准）时才有意义。此时 T-61（IV 股票信号）、T-62（财报波动率）、T-63（卖权利金）都没有可信的期权价格，要继续这个格子就需要付费的历史期权报价。
- plan: 阻塞原因：付费数据和新的数据预算是机主的决定（CLAUDE.md：付费超出免费额度属机主决定），自动轮不得自行购买。T-60 判"不通过"后，由自动轮把本任务 status 改 `ready` 之前，先在汇报第一条通知机主；机主给出预算后再做：核实候选供应商（ORATS、Polygon/Massive 期权历史、Databento OPRA、ThetaData 等）的价格、历史起点、是否含买卖报价与盘中快照、再分发条款——本轮没有核实任何价格。免费的替代（Alpaca 免费档、Kaggle SPY 2010-2023、OptionsDX 到 2023）已在简报里排除。
- done_when: 机主给出"买/不买/预算上限"；买则写数据接入任务并走 `modal_budget.py` 之外的独立预算记录；不买则把 `dir:dolthub_free_options_eod_chain_data` 和期权格子标 `blocked_data` 收口。
- notes:
  - 2026-09-29 16:07 轮缺口搜索（gap-search-2026-09-29-16）添加。当前不需要机主动作：等 T-60 结论。
  - 2026-09-29 16:07 轮：T-60 已判"不通过"，本轮汇报已通知机主。付费数据属机主决定，自动轮不改 ready。
  - 2026-09-30 18:41 机主决定（交互会话转记）：先不买数据。原话："我不相信一定要靠买的，这个做法不是说为了省钱，而是说要追求 ai native"。T-61/62/63 继续 blocked，只在出现免费数据或新合同时重开。

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
- status: superseded（2026-10-01：拆股漂移进组合信号库候选清单 v2）
- priority: 3
- not_before:
- goal: 拆股公告有文献支持的价格效应，但大小有争议：Titman、Wei & Zhao（2016 工作论文，已打开）美国 1998 年后样本，公告 3 日收益 3.32%，公告后前 60 日异常收益 3.21%（t=4.71），12 个月 DGTW 4.20%（t=3.16，约为 Ikenberry-Ramnath 早期样本 9% 的一半），作者提示与动量重叠（公司在上涨后拆股）。GitHub 上一个学生级 CRSP 复现（NathanArimilli24/stock-split-event-study，已打开，未评审）2000-2024 年公告日平均异常收益 +1.26%（t=13.2，N=3,076），第 6 个交易日左右就消失，除权日只有 +0.63% 且当天结束；2010 年代后每年不足 80 个，拆股公司中位市值到 2024 年约 $200 亿，2020/2022/2024 有苹果、特斯拉、亚马逊、英伟达等超大盘拆股。也就是说次日开盘买入大概率错过公告日反应，问题是公告后是否还有漂移。本仓库没有测过（登记簿没有拆股方向，只有别的异象 `nominal_price_anomaly_pwb`）。低换手、只做多、无借券成本，最便宜的否定测试半小时内。优先级 3：证据互相矛盾、样本每年只有几十个。
- plan: 数据：本地**没有**拆股列表（已检查 `data/features`、`data/raw`）；用免费 SEC EDGAR 全文检索建事件表，照 `scripts/collect_sec_ma_target_announcements.py` 的结构（限速、User-Agent、断点、季度 `form.idx` 交叉核对），检索词 "forward stock split"、"stock split in the form of a stock dividend"、"N-for-1 stock split" 等，表格 8-K，Items 5.03、8.01、7.01、3.03，2016-01→2026-09；排除含 "reverse stock split" 的文本；从正文抽拆股比例（只留 ≥ 2 比 1 的正向拆股）；保存 EDGAR 的 acceptanceDateTime 和文本命中片段，落 `data/features/sec_8k_stock_splits/`（先确认 `.gitignore` 覆盖；`data/sec/` 是别的会话在用，**不要往里写**）。抽样核对：随机读 25 条命中正文，误判率写进报告（T-03 是 8%）；误判率 >15% 就把限定词收紧后重抽，仍不行就标 `blocked_data`。**先预注册再算**：`direction-review.json` 引用 `dir:stock_split_announcement_drift_recent`，迭代 `h20260929_82_stock_split_drift`。入场规则（写死）：反应会话 = 若 acceptanceDateTime 在美东 15:30 之前则为当日，否则为下一个交易日；**入场 = 反应会话之后下一个会话的开盘**（不追公告日的跳空，也不用可能已被反应的价格）；参考上界（不可交易，不算候选）= 收盘后公告时在反应会话开盘入场。候选最多 **8 条**：持有 {20, 60} 个会话 × 池 {ADV 前 1,500 且价格 ≥ 5 美元，全部可映射标的} × 基准 {SPY 调整，SPY 加 IWM 等权}。对照（不算候选）：把同一批事件的公告日随机移动 ±126 个会话的安慰剂；以及按公告前 126 日收益十分位匹配的动量对照（Titman 等自己提示的混杂）。价格面板先过 `sanitize_price_matrices` 默认参数；拆股当天的价格跳变会被它标成可疑会话，**要把拆股除权日本身保留**（用复权价或跳过除权日的收益，写清楚用哪一种），读行情一律 `scripts/run_capped.sh --mem 1.8G --`。**最便宜的否定测试（数据建好后约 10 分钟，先于任何账本）**：`signal_card` 事件模式（同 T-03），持有 20 与 60 日，报全样本、2019 起、2024 起的 CAR、t、事件数。**继续的条件（数字写死）**：ADV 前 1,500 池可用事件 ≥ 40（2019-2026），入场后 20 会话 SPY 调整 CAR 均值 ≥ +1.0% 且 t ≥ 2.0，2024 起（n ≥ 15）符号为正，且高于动量匹配对照 ≥ 0.5 个百分点。任一不满足就停，登记为 refuted/evidence_too_weak，不建账本。通过后才走 `scripts/screen_lane.py` 和第 5 节 K1/K2、DSR（8 次试验）、20 bp 复核；事件太少时按"近期观察"上限处理，不能保留。
- done_when: 事件表建好并有抽样核对记录（误判率、事件数按年）；两张 signal card 或 CAR 表（20 日、60 日；全样本、2019 起、2024 起；安慰剂和动量匹配对照）写入 `reports/research/iterations/h20260929_82_stock_split_drift/results.json`；登记簿 `dir:stock_split_announcement_drift_recent` 更新终态并 validate ok；`direction-check` 与 `iteration validate` 通过。
- notes:
  - 2026-09-29 缺口搜索（gap-search-2026-09-29-22，协调者任务代码 R0929-2207-D）添加。原文核对：Titman-Wei-Zhao PDF 全文（已打开，数字来自摘要与正文）、GitHub 复现 README（已打开，学生项目，数字只当方向）；Gharghori & Nguyen（澳大利亚样本）页面被验证码拦截，只见搜索片段，claim_only，数字不引用。
  - 2026-10-01 06:42 UTC 交互会话（Opus）：方向大改后不再单独做成只做多策略；作为信号卡候选，组合 v1 跑通后按边际贡献判。

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
- status: superseded（2026-10-01：数据部分由组合线 D1 完成，信号部分进候选清单 v2）
- priority: 2
- not_before:
- goal: 覆盖地图 `trend_momentum.stock_momentum` 写着"行业相对动量从未在本地测过，卡在没有行业分类"；本轮确认分类可以免费拿：SEC `company_tickers.json` 今天返回 200、10,431 行，`data.sec.gov/submissions/CIK0001045810.json`（NVDA）返回 sic 3674。文献（只有 Springer 综述转述，原论文没读，数字标 claim_only）：Moskowitz-Grinblatt 1999 行业动量 0.43%/月（1963-1995），扣掉行业后的个股动量只剩 0.13%/月；Grundy-Martin 加 1 个月间隔后降到不显著的 0.16%/月；Grobys-Kolari 2020（48 个行业，1926-2018）0.62%（1-0-1）、0.57%（6-1-1）、0.80%（12-1-1）/月，月度 alpha 0.56%，没有动量崩盘的期权性。Hou 2007（摘要已打开）：大公司领先小公司主要发生在行业内，由对负面信息的迟缓调整驱动，小型、竞争弱、被忽视的行业更明显，和大公司财报后小公司漂移相关；Baker 等 2019（摘要已打开，1996-2015）：同行业同行的财报新闻和本公司在其公告日的收益正相关。反面证据：Arnott 等（因子动量，摘要已打开）说行业动量在一个月周期最强但被因子动量吸收，不是独立来源；Management Science 的"Tail Wags the Dog"称跨行业扩散可能是假象（只读到标题和页眉，claim_only）；ETF 层面的行业轮动（`dir:narrow_industry_etf_momentum_rotation`）已被否定，但那是纯多头 top-N，不是行业中性多空。文献的量级（约 0.4-0.8%/月，总的）只略高于个股层面月度双腿成本，所以先验偏低，价值在于一次建好行业表，同时解锁其他行业中性方向。
- plan: **数据（已亲自核对）**：行情 `data/features/daily_broad/*.parquet`（13,733,586 行、9,191 个代码、2016-01-04→2026-09-17）用来定 ADV 前 1,500 的池；价格面板从 `data/sip/daily` 读并先过 `sanitize_price_matrices` 默认参数（拆股、坏价、代码复用），读行情一律 `scripts/run_capped.sh --mem 1.8G --`，按年分块只取池内代码。财报事件 `data/features/earnings_events/*.parquet`：16,015 行、1,448 个代码、acceptance_utc 2024-01-02→2026-09-17、fetch_status='ok' 14,923 行。**新增数据**：行业表。用 `company_tickers.json` 把池内代码映射到 CIK，再对映射到的 CIK 请求 `data.sec.gov/submissions/CIK##########.json` 取 sic（估计约 3,500 次，单线程 ≤5 次/秒、User-Agent 写描述性、遇 429 退避、断点续跑，约 12-15 分钟）；再下载 Ken French 的 48 行业 SIC 区间文件 `Siccodes48.zip` 得到 FF48；写 `scripts/fetch_sec_sic_map.py`（分页/退避/断点用假响应单测），落 `data/features/sic_map/sic_map.parquet`（先确认 `.gitignore` 覆盖；`data/sec/` 是别的会话在用，不要往里写）。已知缺陷（写进报告）：company_tickers 只含当前代码，已退市和复用代码会缺失或错配，报告缺失占比（按年）和按 `sip-delisted` 的补救；SIC 是当前值不是 PIT；行业成员少于 15 的 FF48 行业当月丢弃。**先预注册再算**：`direction-review.json` 引用 `dir:industry_relative_momentum_and_peer_earnings_spillover`，迭代 `h20260930_02_industry_relative`。池：ADV 前 1,500、价格 ≥ 5 美元、排除基金。信号族（符号预注册为文献方向）：I1 行业 1 个月动量：FF48 行业等权收益的过去 21 会话，做多前 5 名行业的全部成员、做空后 5 名，月频；I2 行业 12-1 动量（过去 252 会话跳过最近 21）同样做法；I3 行业中性个股 12-1 动量：个股 12-1 收益减所在行业均值，十分位多空；I4 同行业财报溢出（只有 2024-01 起）：t 日对股票 i，取过去 5 个会话内同行业、财报反应会话收益（用 acceptance_utc：美东 16:00 之前为当日，之后为下一交易日；取前一收盘→反应会话收盘、减 SPY）的均值，至少 2 个同行且不含本公司，排除自己今天有财报的股票；做多最高五分位、做空最低五分位，持有 5 和 20 会话。候选 **10 条**：I1{多空，仅多头 top5}、I2{多空，仅多头}、I3{十分位多空，仅多头最高十分位}、I4{持有 5，持有 20}×{多空，仅多头}。成交：收盘出信号、次日开盘成交，月频调仓看 21 个偏移的中位数，I4 按事件持有；成本用 `scripts/run_h20260929_21_lockup_books.py` 的分层价（前 500 3 bp、500-1000 6 bp、1000-1500 12 bp 每边），空头借券 3%/年（ETB 名单本地没有，标注"未核对易借"），20 bp 复核。**最便宜的否定测试（表建好后约 15 分钟，先于任何账本）**：对每个信号族算 Spearman IC 和最高五分位减最低五分位的毛收益价差，对 21 会话（I4 为 5 和 20）的行业相对收益，对标窗 2024-01-08→2026-09-17 和压力窗 2020-08-11→2023-12-29 分开报（I4 只有对标窗），Newey-West（滞后 = 持有期）t，500 次随机打乱行业标签的安慰剂。**继续的条件（数字写死）**：至少一个族在对标窗 IC 符号与文献相同、|t| ≥ 2.0，压力窗同号（I4 除外），毛价差 ≥ 0.80%/月（I4 ≥ 0.30%/5 会话），且安慰剂 IC 分位在 95% 之外；否则写"行业相对信号收口"，登记 refuted，不建账本。通过后对通过的族走 `scripts/screen_lane.py` 和第 5 节 K1/K2、DSR（10 次试验）、20 bp、随机日期安慰剂；K2 对 S3 的组合增量 ≥ 0.05。SIC 表建好后在 notes 记一行，方便行业中性的别的方向复用。
- done_when: `data/features/sic_map/sic_map.parquet` + 抓取脚本和单测（ruff/pytest 通过）+ 缺失占比表；IC 表（信号族 × 窗口，含 t、安慰剂分位、毛价差）写入 `reports/research/iterations/h20260930_02_industry_relative/results.json`；过关族的 10 条候选分档、DSR、K2；登记簿 `dir:industry_relative_momentum_and_peer_earnings_spillover` 更新终态且 `oc research directions validate` 通过；`direction-check` 和 `iteration validate` 两个阶段通过；覆盖地图 `trend_momentum.stock_momentum` 的"行业相对"一行由协调者更新。
- notes:
  - 2026-09-30 缺口搜索（gap-search-2026-09-30-01，协调者任务代码 R0930-0107-G）添加。原文核对：Springer 综述（已打开，Moskowitz-Grinblatt、Grundy-Martin、Grobys-Kolari 的数字是综述转述）、Hou 2007 摘要、Baker 等摘要、Arnott 等摘要与引言均已打开；Hong-Torous-Valkanov 的说明是行业对大盘的领先，不是本任务的信号，未采用；"Tail Wags the Dog"只读到页眉，claim_only。exa 检索的 6 页里只有摘要，原论文全文多数付费墙。
  - 2026-10-01 06:42 UTC 交互会话（Opus）：方向大改后取代。行业表已由 D1 建成（`data/features/sic_map/sic_map.parquet`，`scripts/build_sec_sic_map.py`，P1000 任意时期覆盖 99.1%）；行业动量、行业中性动量、同行财报溢出不再单独测，作为组合信号库 v2 的候选，按边际贡献判（`docs/research-program.zh.md` 最后一节）。

### T-20260930-03 年末税损卖出后的反弹：年内跌幅最大的股票 12 月中旬买入、持有到 1 月底，和市场对冲后的超额（十个 12 月窗口，几乎零换手）
- status: done
- priority: 3
- not_before:
- goal: Ivkovic、Poterba、Weisbenner（NBER w10275，已打开全文）用个人投资者逐笔交易数据证明税损卖出全年存在，12 月最明显，尤其是当年在别处有已实现收益的账户。价格层面的结论只有实务摘要：Globe and Mail（2025-12-11）称 TSX 年内跌幅超 15% 的股票在 11 月中到 12 月中跑输近 4%、12 月中到 1 月中跑赢 3.6%，但正文付费墙打不开、又是加拿大样本，claim_only，不当效应量；JFIR "Tax-loss selling and the January effect revisited" 被 403，只有搜索片段说 1 月效应在减弱（更多免税账户），claim_only。也就是说"税损卖出存在"有原文，"美股 2016 后的反弹幅度"没有任何打开的来源，先验低；价值是这个窗口在 2026-12-15 前必须有结论，测试免费、换手近零、可以和 IWM/SPY 对冲，和 S3 应当低相关。
- plan: **数据本地已有（已亲自核对）**：`data/sip/daily`（美股日线 2016-01-04→2026-09-29），信号窗口 2016-12-15…2025-12-15 共十个，出场最晚 2026-01-30 也在数据里。不需要新数据。价格面板先过 `sanitize_price_matrices` 默认参数，读行情用 `scripts/run_capped.sh --mem 1.8G --`。**先预注册再算**：`direction-review.json` 引用 `dir:tax_loss_selling_year_end_rebound`，迭代 `h20260930_03_tax_loss_year_end`。池：信号日 ADV 前 1,500、价格 ≥ 5 美元、排除基金（复用 T-21 的名称过滤）。信号：年内收益 YTD = 12 月 15 日收盘 / 上年最后一个交易日收盘 − 1。主窗口 W2：12 月 15 日收盘出信号，16 日（或其后第一个交易日）开盘入场，出场 {1 月 15 日，1 月 31 日} 收盘（或前一个交易日）。候选 **6 条**：{YTD 最低十分位}×{池 ADV 前 1,500，池 ADV 排名 500-1,500}×{出场 1/15，1/31}（4 条）+ {YTD ≤ −30%}×{池 ADV 前 1,500}×{出场 1/15，1/31}（2 条，阈值不调）。收益用池等权作基准（另报 IWM 对冲），成本按分层价（前 500 3 bp、500-1000 6 bp、1000-1500 12 bp 每边，来自 `scripts/run_h20260929_21_lockup_books.py`）。诊断窗口 W1（11 月 15 日出信号，12 月 15 日出场，预期跑输，只用来看方向，不算候选，做空侧未核对易借）。安慰剂窗口（不算候选）：同样构造放在 2 月 15 日→3 月 31 日、6 月 15 日→7 月 31 日，各十年。**最便宜的否定测试（约 10 分钟，先于任何账本）**：十个年度的 W2 等权超额收益表、扣成本后均值、按年聚类的 t、正年份数、去掉最好一年后的均值，2024 起（Dec 2024、Dec 2025 两个窗口）单列，再对比两个安慰窗口。**继续的条件（数字写死）**：12 月 16 日→1 月 31 日的超额均值（扣分层成本后）≥ +1.5%，十年里 ≥ 7 年为正，按年聚类 t ≥ 2.0，两个安慰窗口均值合计不超过真实值的一半，2024 起两个窗口都为正。任一不满足就写"税损反弹收口"，登记 refuted，不建账本、不调阈值。通过也只有十个观察，只能标"近期观察"上限，2026-12-15 的窗口是真正的样本外，通过后把它写成 not_before 2026-12-15 的前向跟踪任务，不得直接上模拟盘。
- done_when: 十窗口年度表、成本后均值/t/正年份数、两个安慰窗口、2024 起窗口写入 `reports/research/iterations/h20260930_03_tax_loss_year_end/results.json`；登记簿 `dir:tax_loss_selling_year_end_rebound` 更新终态且 `oc research directions validate` 通过；`direction-check` 和 `iteration validate` 两个阶段通过。
- notes:
  - 2026-09-30 缺口搜索（gap-search-2026-09-30-01，协调者任务代码 R0930-0107-G）添加。原文核对：NBER w10275 已打开（摘要和全文）；Globe and Mail 付费墙、JFIR 403，均 claim_only。exa 检索六页里只有摘要，没有美股 2016 年后的效应大小，是本任务先验低的原因。
  - 2026-09-30 07:07 自动轮（R0930-0707-TL）开始：按上面 plan 原样预注册并跑最便宜的否定测试，子代理执行。
  - 2026-09-30 07:07 自动轮（R0930-0707-TL）：done，否定（"税损反弹收口"，Opus 已对照 results.json 核对）。6 条 0 条过五条条件；最好 L30_A_X0115 扣成本超额 +0.94%，按年 t 0.69，7/10 年为正，Dec 2024 −0.25% / Dec 2025 +1.99%；持有到 1/31 的三条均值全负；IWM 对冲最好 +1.31%（t 1.02）；W1 诊断窗输家没有跑输（+0.19..+1.13%）。12 月不做前向。产物 `reports/research/iterations/h20260930_03_tax_loss_year_end/`、`scripts/run_h20260930_03_tax_loss_year_end.py`；登记簿 `dir:tax_loss_selling_year_end_rebound` → refuted。

### T-20260930-10 纲领 A1：板块季节性前置扩到行业 ETF
- status: done
- priority: 1
- not_before:
- goal: C2 的收益主要来自板块季节性前置（S 腿；H-20260928-20 里 S 族 10 个变体在 2026 留出窗全部为正，2026 年 S 腿 +43.7%）。本任务检验同一机制在行业 ETF 上是否成立。成立的话，模拟盘可以多一个机制相同、持仓不同的收益来源。
- plan: 设计要点由 Opus 写在 `docs/research-program.zh.md` 主线 A；执行轮把它写进迭代档案并预注册。
  - 宇宙：2015-01 以前上市、非杠杆、非反向的美国行业 ETF，约 25 只（SPDR、iShares、VanEck 的行业 ETF，剔除 9 个板块 SPDR 本身）。清单在看结果前冻结，写进候选清单；`data/sip/daily` 里 2015–2026 缺数据的剔除，并写明剔除原因。
  - 规则与 S0 完全相同：`scripts/screen_batches/h20260928_20_recent_opt.py` 的 `make_sector_seasonality_fn`，只换 universe。
  - 预注册 6 格：top_n∈{2,3,5} × avg_years∈{1,5}。批量通道 `scripts/screen_batch.py`（K1/K2、20 bp、压力期、DSR）。
  - 安慰剂：打分窗口随机平移 1–11 个月，20 个种子；真实规则要打赢 ≥90% 的种子。
  - 最便宜的否定：6 格没有一格过 K1 → 停，纲领 A1 记否定并写死因。
  - 过了：测"C2 + 行业腿"相对 C2 的夏普增量（同波动对照），不改 C2 已冻结的规则。
- done_when: 迭代档案 + leaderboard + 纲领主线 A 的"学到了什么/下一步" + 登记簿 + 提交。
- notes:
  - 2026-09-30 交互会话（Opus）按纲领 A1 写入。国家 ETF 版不做：AllocateSmartly 1971–2025 扩展测试夏普 0.46，基准 0.38，作者已停止跟踪（https://allocatesmartly.com/front-running-seasonality-in-country-etfs-an-extended-test/）。
  - 2026-09-30 04:07 自动轮（R0930-0407）开始：Opus 预注册设计写在 `reports/research/iterations/h20260930_10_industry_seasonality/hypotheses.md`，子代理执行。
  - 2026-09-30 04:07 自动轮（R0930-0407-A1）：done，refuted（第一段）。6 格对标窗 10bp 夏普 0.52–1.12（最好 I_K2_Y5 1.12，lane 窗到 09-17 为 1.18，都 <1.19）；1 年打分格的随机平移安慰剂打赢比例 0.20–0.45（真实规则和随机挑行业分不开），5 年格 0.05；与 S0 日相关 0.65–0.75；和 C2 组合的增量 6 格两窗全为负（对标 −0.18..−0.48、压力 −0.09..−0.31）。死因：行业层面的前置在 2024–26 不强，且与 S0 重复。追加诊断 S0/C2 随机平移安慰剂（100 种子，`s0-c2-placebo.json`）：对标窗打赢比例 0.00，但选择窗 0.38、压力期 0.64，优势只在 2026。产物 `reports/research/iterations/h20260930_10_industry_seasonality/`、`reports/research/screens/h20260930_10_industry_seasonality/`、`scripts/screen_batches/h20260930_10_industry_seasonality.py`。

### T-20260930-11 纲领 C1：跳空回补 × 竞价执行的最便宜否定（官方竞价价上毛边际还在不在）
- status: done
- priority: 1
- not_before:
- goal: T-20260929-32 证明截面跳空回补的信号是真的（空头选股毛 +11.5 bp/天、毛夏普 1.33，安慰剂全输），死因是按逐只价差计的成本（18–28 bp/边，每天进出两次）。开盘竞价进、收盘竞价出不付买卖价差，可能把成本从每天约 40 bp 降到几 bp。本任务先确认毛边际在官方竞价价上还在，再决定是否做全量。
- plan: 设计要点在 `docs/research-program.zh.md` 主线 C。
  1. 入选记录：用 `reports/research/iterations/t20260929_32_gap_fade_ls/` 的每日入选；没有落盘就按它的脚本重建 2024-01-08 以后的入选。按日成交额分档（$5–20M、$20–100M、>$100M）分层抽约 300 个（股票, 日），抽样种子写进档案。
  2. 官方价：用 Alpaca 历史逐笔成交（SIP），按条件码找出上市交易所的开盘竞价成交（opening print / official open）和收盘竞价成交（closing print / official close）。先在 5 个样本上人工核对条件码的含义，写进档案。
  3. 记录日线 open/close 与官方竞价价的偏差分布。
  4. 在官方价上重算入选组合的 open→close，多空两腿按原规则的方向。
  - 判定（预先写死）：
    - 日成交额 ≥$20M 的两档，官方竞价价上的毛边际 ≥8 bp/天 → 进全量预注册。全量的成本 = 费用 + 开盘竞价冲击（按 Goyal-Jegadeesh-Wu, JFQA 2026 的开盘竞价口径做压力档）+ 借券。
    - 低于 8 bp → 关闭日内个股线（纲领主线 C 的停止条件），写死因。
- done_when: `reports/research/iterations/t20260930_11_gap_fade_auction/`（抽样表、偏差分布、分档毛边际、判定）+ 纲领主线 C 更新 + 登记簿 + 提交。
- notes:
  - 2026-09-30 交互会话（Opus）按纲领 C1 写入。只调行情 API，不下单。适用边界要写进结论：Alpaca 模拟盘的开盘竞价单成交不可靠（2026-09-15 50 单里 45 单过期），模拟盘只能验证收盘竞价腿；开盘竞价腿只能在实盘或别的券商验证。
  - 2026-09-30 04:07 自动轮（R0930-0407）开始：Opus 预注册设计写在 `reports/research/iterations/t20260930_11_gap_fade_auction/hypotheses.md`，子代理执行。
  - 2026-09-30 04:07 自动轮（R0930-0407-C1）：done，按预注册 close。T2+T3（≥$20M）官方竞价价毛边际 E_off 7.09 bp/天（90% 区间 −2.1..16.0），低于 8 bp。其中日线毛边际 E_bar 只有 6.00 bp，配对修正 Δ +1.09 bp；收盘 Δ 在每格都是 0.00（日线 close 就是官方收盘价）。所以死因不是竞价价口径，而是流动档本身边际薄：T3 多头 −17.2 bp，空头 +3.2 bp。纲领原先写的 ">$1 亿档约 +16 bp/天" 不成立，已更正。T1（$5–20M）不一样：官方价上多头 42.5 bp、空头 48.3 bp（空头靠 Δ 的尾部，中位数 0），开盘竞价中位成交额 $40 万，$1,500 的单子约占 0.4%。转为新任务 T-20260930-12（纲领 C1b）。400 行抽样、条件码核对（上市交易所 O+Q 成对，收盘 6+M）见 `reports/research/iterations/t20260930_11_gap_fade_auction/`。

### T-20260930-12 纲领 C1b：小盘跳空低开做多 × 竞价执行（$5–20M 档，只做多，不借券）
- status: done
- priority: 1
- not_before:
- goal: T-20260930-11 在官方竞价价上重算跳空回补，结果只有 T1（日成交额 $5–20M）一档的毛边际够厚。多头腿日线毛边际 +42.2 bp/天（对标窗，se 19.1），压力期 +26.6 bp（se 8.3）；官方价修正 Δ 中位数为 0，官方价毛边际 42.5 bp。开盘竞价中位成交额约 $40 万，$1,500 的单子参与率约 0.4%。T-32 的死因是每边 18–28 bp 的价差，竞价进出不付价差。只做多就不用借券，对 $1.5 万的 sleeve 容量也够。本任务回答：扣掉竞价冲击和费用后，这一档的净边际是否还在，并且是不是来自 z 信号本身，而不是小盘股日内的普遍漂移。
- plan: **先预注册再算**（Opus 设计，执行轮写进迭代档案 `t20260930_12_smallcap_gap_auction`）。
  - 信号：同 T-32 多头腿（z 最低），池限定为 dv21 ∈ [$5M, $20M]、close ≥ $5、历史 ≥ 60 天、像拆股过滤。开盘竞价买入（官方开盘价），收盘竞价卖出（官方收盘价），不过夜。
  - 历史回测用日线 open/close。T-11 已核对：收盘 Δ≡0，开盘 Δ 中位数 0，但尾部厚，所以另报"按 T-11 的 T1 多头 Δ 经验分布做 1,000 次自助扰动"的敏感性。
  - 候选 4 条：K ∈ {5, 10} × 等权/按 1/sigma21 加权。
  - 成本：基准每边 5 bp（费用 + 竞价冲击），压力每边 10 bp；另报冻结的 10/20 bp。
  - **最便宜的否定测试（先于账本）**：
    1. 每日多头篮子毛收益，按日聚类的 t，对标窗和压力期分开；
    2. 安慰剂：每天从同一池随机抽 K 只（100 个种子），真实篮子毛均值要打赢 ≥90% 的种子；
    3. 同池等权全体的 open→close 均值作基准，报超额。
  - **继续的条件（写死）**：两窗真实篮子毛均值都 ≥ +20 bp/天、按日 t ≥ 2.0，安慰剂打赢 ≥90%。满足才建账本：两窗 5 bp/边下 K1（对标 ≥1.19、压力 ≥0.65），10 bp/边下两窗年化 >0，K2 对 S3、DSR（4 次试验，本族累计另报）。
  - **前向**：2026-10-01 起每日用 Alpaca 历史逐笔（只读）取官方价，影子记录 63 个会话，这是真正的样本外。
  - **适用边界**：Alpaca 模拟盘开盘竞价单成交不可靠（09-15 50 单 45 单过期），模拟盘只能验证收盘腿；开盘腿是否可执行要写进"需要机主决定"。
- done_when: 否定测试表（两窗毛均值/t/安慰剂分位/同池基准）+ 过关后的 4 条账本分档，写入 `reports/research/iterations/t20260930_12_smallcap_gap_auction/results.json`；direction-check 与两阶段 validate 通过；登记簿更新。
- notes:
  - 2026-09-30 04:07 自动轮（R0930-0407）由 T-20260930-11 的 T1 结果派生。数据：`reports/research/iterations/t20260930_11_gap_fade_auction/cache/picks.parquet`（对标窗入选行）、`reports/research/iterations/t20260929_32_gap_fade_ls/cache/wide_matrices.parquet`（清洗后宽表）、`scripts/run_t20260930_11_gap_fade_auction.py`（官方价抓取，可复用）。T1 的对标窗 E_bar 已经看过，历史部分只能算"受污染"，前向 63 会话才是判决。
  - **2026-09-30 05:05 UTC 交互会话（Opus）审查：执行前必须改设计，以下优先于上面的 plan。**
    1. **前视问题（判决性）**：原计划按官方开盘价算 z 选股，又在官方开盘价买入。但开盘竞价单必须在 9:28 ET 前提交（Alpaca 文档：OPG 单 9:28 后当天拒收，https://docs.alpaca.markets/us/docs/orders-at-alpaca），那时开盘价还不知道。C1 的 +42.5 bp/天是在不可执行的选股口径上量的，其中可能有一部分只是竞价噪声的回归，事后才看得到。
       - 改法：选股只用 9:28 之前的信息。本地分钟档有盘前 bar（04:00 起），用 9:27 及以前最后一根盘前 bar 的收盘价，相对前一日官方收盘价算跳空和 z（预注册时二选一写死；另一种是 9:00–9:27 的 VWAP）。9:27 前没有盘前成交的票不可选。
       - 买在官方开盘价，卖在官方收盘价。
       - 两种口径都报：开盘价选股 = 前视版，只作对照；盘前选股 = 可执行版。继续/停止只按可执行版判断。
    2. **幸存者偏差**：`data/sip/daily` 没有退市股（`docs/data-layer-pitfalls-and-capabilities.zh.md` 第 3 条：SIVB、FRC 等 0 行）。小盘跳空低开做多正好漏掉后来退市的票，历史边际偏高。
       - 结论里写明这一点；对标窗与 2016–23 分开报，2016–23 缺得更多。
       - 判决仍以 10-01 起的前向影子记录为准，前向没有幸存者偏差。影子记录同样按盘前选股。
    3. **最便宜的否定先做可执行版**：先在 C1 的抽样里改用盘前信号重新选股，重算 T1 多头的毛边际。低于 20 bp/天 → 直接关闭，不建账本，纲领 C1b 记否定（死因：前视）。
  - 2026-09-30 07:07 自动轮（R0930-0707-C1b）开始：Opus 预注册写在 `reports/research/iterations/t20260930_12_smallcap_gap_auction/hypotheses.md`（按 05:05 审查改设计：X15 = 免费计划 15 分钟延迟下 09:11 ET 前的 SIP 盘前 bar 为主判定，X0 = 09:26 需付费实时 SIP，LA = 开盘价前视对照），子代理执行。
  - 2026-09-30 07:07 自动轮（R0930-0707-C1b）：done，否定（closed_unstable，Opus 已对照 results.json 的 decision_cells 核对）。判定格 X15_K10_EW 对标窗毛 −5.37 bp/天（t −1.03），安慰剂打赢 0.40，短窗 −4.15 bp；X0_K10_EW −4.80（t −0.94），0.53，+0.07；前视对照 LA_K10_EW −3.96。三条继续条件两个口径全不过，账本未跑。死因：C1 的 +42.5 bp 是整个 ≥$1M 池极端跳空（z 中位数 −3.7）落在 $5–20M 档的子集，先限池再取 10 只会混进均值 −17.3 bp 的温和跳空（`c1_reconciliation.json`）；池里只有 35% 的行 09:11 前有盘前成交。产物 `reports/research/iterations/t20260930_12_smallcap_gap_auction/`、`scripts/run_t20260930_12_smallcap_gap_auction.py`；登记簿 `dir:smallcap_gap_down_fade_auction_execution` → refuted。

### T-20260930-13 日内截面规律之二：开盘/收盘半小时同时段延续 × 一腿竞价（Heston-Korajczyk-Sadka 2010；Haendler 等 2025 样本外）
- status: done（已主审 2026-09-30 12:20：两个判定格关闭）
- priority: 2
- not_before:
- goal: 同一只股票在开盘半小时（09:30–10:00）和收盘半小时（15:30–收盘竞价）的收益与它过去 20 天同时段收益正相关（HKS：开盘 >11 bp、收盘 >8 bp 的十分位多空）。一腿走竞价后，2024–26 年的毛边际能否付 2 倍成本？是纲领主线 C2 的第二部分。
- plan: 预注册写死在 `reports/research/iterations/t20260930_13_intraday_periodicity/hypotheses.md`：两个判定格 C_L20_P1500、O_L20_P1500 各自按主窗判定；m ≥ 2×RT1 通过，m < RT1 关闭；安慰剂 100 种子、相邻时段对照；只用 2023-08 → 2026-09 分钟档，压力期等通过后再定。
- done_when: results.json + report.md + 档案通过 pre-backtest 检查；结果标"待主审"。
- brief: reports/research/control/briefs/T-20260930-13.md
- notes:
  - 2026-09-30 09:00 交互会话（Opus 主审）从 T-20260929-35 拆出并写预注册和简报。依赖 T-20260929-35 的 panel 缓存（池相同）。2023 年分钟档要同时读整年旧分片和月目录（C1b 漏了旧分片，见简报"背景"）。
  - 2026-09-30 10:58 执行轮（Sonnet 5.5，R0930-1007）开始：T-35 的 panel 已就绪，子代理按简报执行。
  - 2026-09-30 11:48 执行轮：子代理跑完 extract + screen，pre-backtest 检查通过（11:01:19Z，早于 results.json generated_at 11:42:34Z），hypotheses.md 未改（子代理称被档案生成器覆盖过一次，已逐字节还原，git diff 为空）。字段齐全（results.json，主窗 2024-01-08→2026-09-29，n=684）。判定格 C_L20_P1500：均值 17.13 bp、t_nw5 15.68、placebo_beat 1.00、rt1_bp 74.67、tier closed；O_L20_P1500：14.60 bp、t_nw5 4.84、placebo_beat 1.00、rt1_bp 77.25、tier closed。注意：这两个 tier 按冻结的 AR 价差成本（约 34 bp/腿）机械算出，而主审的修正案 A1（ceca3b9）已声明 AR 价差高估流动股价差 20–60 倍、作废 RT1 和 tier，30 天实测报价抽样未做——判定留给主审。诊断（不入 tier）：C 的盈亏平衡 h 为 4.57 bp/腿（1 倍）、0.28（2 倍）；O 为 3.30（1 倍）、2 倍为负。相邻时段对照（同时段减对照）：C +20.31 bp（t_nw5 13.18，对照本身 -3.17、t_nw5 -3.48）；O +16.92 bp（t_nw5 3.99，对照本身 -2.32、t_nw5 -0.90）。收盘段拆分：r_C1（15:30–15:50）3.83 bp（t_nw5 4.23）、r_C2（15:50–收盘，含竞价）13.23 bp（t_nw5 24.77）。其他窗口：C 的 2026 受污染窗 +21.03 bp、新留出 +14.04 bp（n=8）；O 的 2026 受污染窗 +13.63 bp（t_nw5 1.44）、新留出 +20.20 bp（n=8）。分钟覆盖（P1500 池日中有分钟 bar 的比例）：2023 0.924、2024 0.939、2025 0.964、2026 0.989；46 个池日未过收盘一致性检查；2023 年 2192 个代码中 732 个只在整年旧分片里，两种布局已合并去重（按 bar 集指纹），1453 个重叠。子代理自选口径：日线开/收盘价在 2023-07 窗口重新载入并清洗；空头腿只用易借券、DTC 缺失视为不限制；安慰剂空头腿从同一易借券集合抽取（均写进 report.md）。未做：修正案 A1 的 30 天实测报价抽样（输入在 `cache/picks_*.parquet`）；`--stage final` 检查（只被 search_space_trial_ledger_paths_empty_final 和 decision_record_missing_continue_pivot_stop 卡住，属主审）。遗留：`cache/extract/_legacy/` 是子代理创建的未用目录（删除被拒绝），可以删。待主审。产物：`reports/research/iterations/t20260930_13_intraday_periodicity/`（results.json、report.md、cache/）、`scripts/run_t20260930_13_intraday_periodicity.py`、`tests/test_t20260930_13_intraday_periodicity.py`、`strategy_specs/drafts/t20260930_13_intraday_periodicity.yaml`、`reports/harness/source_cards/t20260930_13_intraday_periodicity.jsonl`、`logs/t20260930_13_*.log`。
  - 2026-09-30 11:55 主审（交互会话 Opus）：results.json 里按日线 AR 价差算的 RT1（74.7/77.3 bp）和 tier 作废（修正案 A1，11:00 提交，早于本任务 pre-backtest 检查和结果）。毛边际：C_L20_P1500 17.1 bp/天（NW t 15.7，安慰剂 1.00），其中 15:50→收盘（含竞价）13.2 bp、t 24.8，几乎全在多头（+12.6 / −0.7）；O_L20_P1500 14.6 bp（t 4.8）；相邻时段对照 C −3.2、O −2.3 → 同时段信号真实存在。但 t 高得异常，且集中在"最后成交价 → 竞价价"这一截：时段起点用的是最后成交价，若它在价差里的位置按股票持续，会造出交易不到的收益。所以成本改为实测可成交收益的配对缺口 s（修正案 A2，11:52 提交，早于任何报价）；判定交给 T-20260930-15。流程提醒：子代理称档案生成器覆盖过一次 hypotheses.md 后已还原，以后执行轮在跑结果前先 `git diff` 冻结文件。
  - 2026-09-30 12:20 主审（交互会话 Opus）：按修正案 A2 用 T-20260930-15 的实测报价判定，**两格关闭**。C_L20_P1500：s 25.2 bp（多 18.5、空 6.7），net_1x −16.1、net_2x −49.3；30 天样本成交价口径毛 11.5 bp、可成交口径 −13.7 bp。O_L20_P1500：s 42.0 bp，net_1x −35.4。**毛边际大部分是数据假象**：日线档与分钟档的复权口径不一致（分红股 NKE/RF/KEY/TSN 等，日线 close 比分钟最后常规价高约 1%），close_日线 / p_1529_分钟 带固定偏差、跨天延续；剔除 23 只受影响股票后样本毛边际 2.3 bp，多头可成交 −7.6 bp（主审用 2025 年缓存独立复核：2,446 只里 30 只中位偏差 >0.4%）。死因：干净的同时段延续只有约 2 bp，远小于半价差（入选股约 7 bp）→ 关闭同时段周期性这条线，不改执行也救不回。已记入 `docs/data-layer-pitfalls-and-capabilities.zh.md` 第 58、59 项。

### T-20260930-14 纲领 C2a′：一年期隔夜延续（ON252）的样本外核对 + 官方竞价价核对
- status: done（已主审 2026-09-30 19:20：gate_a 过、gate_b 不过 → 按预注册关闭隔夜延续线）
- priority: 2
- not_before:
- goal: T-35 的只报告格 ON252（过去一年隔夜收益）在 P500/P1500 两窗都强（P500 LS 主窗 +17.0 bp/晚），但已被看过。用没看过的股票（dv21 1501–3000）和官方竞价价核对它是不是普遍特征、是不是日线开盘价的假象。过了就是一条可以只做多、只持有隔夜、两腿都走竞价的近期策略。
- plan: 预注册 `reports/research/iterations/t20260930_14_overnight_persistence_12m/hypotheses.md`：测试 A 池 B 两窗均值 >0 且 NW t ≥2；测试 B 20 个种子日 P500 十分位官方价配对差 ≥ −4 bp/晚、缺失 ≤10%；诊断 ADR、动量、财报夜、集中度。两个都过 → 前向影子 + 提请机主开"LO 前 20 隔夜" sleeve。
- done_when: results.json（gate_a、gate_b）+ report.md + 档案通过 pre-backtest 检查；结果标"待主审"。
- brief: reports/research/control/briefs/T-20260930-14.md
- notes:
  - 2026-09-30 16:10 UTC 执行轮（Sonnet 5.5）开始，交给 sonnet-high 子代理。
  - 2026-09-30 17:03 UTC 执行轮完成（待主审）：results.json 的 gate_a=true、gate_b=false（脚本机械判定）。测试 A（池 B dv21 1501–3000，ON252 LS，毛）：主窗 +13.69 bp/晚 t_nw5 5.19 n 683 placebo_beat 1.00；压力期 +17.35 bp t 12.02 n 1729 placebo_beat 1.00；下一天日内腿主窗 -15.72 bp、压力期 -20.74 bp；池均 1,332 只/晚，退市股占池行 22.9%。测试 B（20 个种子日，1,958 对，缺失 0）：delta_ls_bp -2.72（≥-4 过）、delta_lo20_bp -5.88（<-4 不过）→ gate_b 假；另有 10 夜 f_{t+1}/f_t≠1。诊断（P500/P1500 主窗）：剔 ADR 后 LS 17.12/11.48 bp；与 12-1 动量秩相关 0.567/0.498；剔财报夜后 16.24/11.43 bp；前 10 只占 LS 盈亏 32.2%/19.0%。子代理另报（不在 results.json、未用于判定）：LO20 里 41/1,958 行 |Δ|≥50 bp，剔除后 LO20 均值 Δ -2.64 bp。偏差：抽样日取主窗内 ON252_P500 有效夜（末日无次日开盘）；ON252 单独算，测试核对与 t35.rolling_signals 相等，t35 对账 P500 17.01/P1500 11.99 bp 一致。hypotheses.md 未变。`iteration validate --stage final` 被试验台账路径、评估报告路径和 decision record 的 continue/pivot/stop 拦住（主审填）。T-20260930-16 保持 blocked，不由执行轮改。产物：reports/research/iterations/t20260930_14_overnight_persistence_12m/{results.json,report.md}，scripts/run_t20260930_14_overnight_12m.py，tests/test_t20260930_14_overnight_12m.py。待主审。
  - 2026-09-30 11:03 交互会话（Opus 主审）写预注册和简报（提交 8b7cf83，早于任何新数据）。official 阶段约 4,000 次 Alpaca 请求，别和 T-20260930-15 同时跑。
  - 2026-09-30 12:15 主审补充简报第 2 步的测量口径（不改门槛）：逐笔官方价是原始价，面板 r 是复权价，比较前乘同日复权因子 f_d = 本地 close / 原始 close（`adjustment=raw` 日线），否则除权夜和拆股夜会混进 Δ。
  - 2026-09-30 13:25 主审轮（Opus）：本任务过了之后的下一步已预注册为 T-20260930-16（执行口径 + 账本），状态 blocked。19:07 主审轮审完本任务：gate_a、gate_b 都过就把 T-16 改成 ready，交 22:07 执行轮；任一不过就把 T-16 标 cancelled。主审检查（`t20260930_16_overnight_lo20_execution/lead-check-2026-09-30.md`）：LO20 只持隔夜主窗夏普 1.75，开盘到开盘持有只有 0.92（压力期 0.36），所以只能收盘附近买、开盘附近卖。
  - 2026-09-30 19:20 UTC 19:07 主审轮（Opus）审核：对照 results.json 核对 gate_a=true（池 B 主窗 +13.69 bp/晚 t_nw5 5.19，压力期 +17.35 t 12.02，安慰剂打赢 1.00/1.00）、gate_b=false（delta_lo20 −5.88 < −4；delta_ls −2.72 过；缺失 0/1,958）。主审用 cache/official_pairs.parquet 重算：LO20 按天均值 −5.88 bp，20 天标准误 2.18，中位日 −6.56，20 天里 13 天为负；41/400 行 |Δ|≥50 bp 贡献 60%。抽查 official_prices.jsonl：CVNA 2025-04-04 NYSE 官方开盘 09:38:19 $165.00 对日线开盘 $170.00，SMR 2026-01-14 09:32:48 $18.60 对 $18.99。上市交易所延迟开盘，第一笔成交高于卖方几分钟后能拿到的价，不是取价错误。执行方子代理剔除 |Δ|≥50 后的 −2.64 bp 不是预注册口径，不采用。按预注册"B 不过……关闭"，死因是卖出腿的执行价，不是信号（信号在样本外池成立）。日内/隔夜个股线按纲领停止条件关闭。decision record 已写、trial-ledger.jsonl 已建，`iteration validate --stage final` 通过（仅轻量豁免警告）。
  - 2026-09-30 19:32 UTC 交互主审复核（用 cache/official_pairs.parquet 重算）：LO20 按天均值 −5.88 bp、标准误 2.18、中位日 −6.56、41/400 行 |Δ|≥50 bp 均复现；负值天数是 14 天（其中 2025-04-15 为 −0.08 bp），不是 13 天，不影响结论。

### T-20260930-15 T-13 实测报价核对：同时段延续的可成交收益（修正案 A1 + A2）
- status: done（已主审 2026-09-30 12:20）
- priority: 1
- not_before:
- goal: T-13 的收盘段毛边际 17.1 bp/天集中在"最后成交价 → 收盘竞价价"，可能是成交价在价差里的位置造成的、交易不到的收益。用 Alpaca 历史 NBBO 在 30 个种子日上直接算可成交收益和缺口 s，按修正案 A2 分档，决定 T-13 两个判定格是关闭、边缘还是通过。
- plan: 简报写死：抽 30 天、15:30/15:50/10:00 的最后有效报价、s = 成交价口径 − 可成交口径的配对差；关闭 m−s−8<0，通过 m−2s−16≥0。
- done_when: quote-check.json（每格 s、net_1x、net_2x、tier）+ quote-check.md。
- brief: reports/research/control/briefs/T-20260930-15.md
- notes:
  - 2026-09-30 12:00 交互会话（Opus 主审）写简报，并由交互会话派一个 sonnet-high 子代理执行（两种自动轮都不要碰本任务）。
  - 2026-09-30 12:11 子代理（Sonnet 5.5）完成：336 次报价请求 + 150 次原始日线请求，无 429，报价缺失 0.8%/1.2%；报价按同日（复权 close / 原始 close）换到复权口径；产物 `quote-check.json`/`.md`，脚本 `scripts/run_t20260930_15_quote_check.py`，测试 13 个通过。主审已核对 quote-check.json 的 tier 与各字段，并独立复核了复权口径问题；结论见 T-20260930-13。

### T-20260930-16 纲领 C2a″：隔夜 LO20 在模拟盘可成交价上的缺口 + 按这个成本的 K1/K2/DSR 账本（依赖 T-20260930-14）
- status: cancelled（2026-09-30 19:20 主审：T-14 gate_b 不过，按 13:25 规则取消；未取任何数据）
- priority: 2
- not_before:
- goal: ON252_P500_LO20 的收益只在隔夜（主审检查：只持隔夜主窗夏普 1.75，开盘到开盘 0.92）。Alpaca 模拟盘按 NBBO 撮合、竞价单不可靠，所以要实测"15:59 按卖价买、次日 09:31 按买价卖"相对官方竞价价的缺口 c，再按 c 算 K1/K2/DSR。决定能不能向机主提议一条只持隔夜的模拟盘 sleeve。
- plan: 预注册 `reports/research/iterations/t20260930_16_overnight_lo20_execution/hypotheses.md`（13:22 写，早于 T-14 结果和任何新数据）。阶段 A：40 天 × 20 只（D1 = T-14 的 20 天，D2 = 种子 20261001 的 20 天），P1 判定、P2–P7 只报告；c = s̄_P1 + 0.5 bp，≤8 viable、≤14 k2_only、>14 closed，缺失 >10% insufficient_data。阶段 B：6 个成本合同 × 5 个窗口的账本，K1（主窗 ≥1.19、压力期 ≥0.65）、K2（两窗 ≥0.05）、DSR（试验 22）。
- done_when: results.json（tier_exec、c_bp、k1/k2 四个字段、paths、ledger、diagnostics）+ report.md + 档案通过 pre-backtest 检查；结果标"待主审"。
- brief: reports/research/control/briefs/T-20260930-16.md
- notes:
  - 2026-09-30 13:25 主审轮（Opus）写预注册、主审检查记录和简报。只有 T-14 过了才执行；约 1,300 次行情请求，别和别的取数任务同时跑。
  - 2026-09-30 13:37 交互主审（Opus）：修正案 A1（`t20260930_16_overnight_lo20_execution/amendment-2026-09-30-a1-panel-basis.md`，写于 T-14 结果和本步任何新数据之前）。判定成本 c 改为相对面板 r 配对（账本从面板 r 里扣 c，原定义相对官方价，会漏掉 T-14 测的 Δ）；加只报告路径 P8（09:32 卖出）。依据是本账户 137 笔开盘前挂好的市价单回执：个股成交中位数在 09:30 后 88–114 秒，成交价中位数正好在卖价/买价上，此时半价差中位数 13–17 bp。简报已同步。
  - 2026-09-30 19:20 UTC 19:07 主审轮（Opus）：T-14 gate_b=false（delta_lo20 −5.88 bp，门槛 −4），按本任务 13:25 写死的规则取消。阶段 A 的报价请求和账本一个都没跑；decision record 已写 Stop。

### T-20260930-17 机主问题：纯量价排序换模型族、训练窗、预测周期（阶段 1，接手 T-20260929-30）
- status: done（已主审 2026-09-30 19:20：阶段 1 核对无误；阶段 2 另立 T-20260930-19）
- priority: 3
- not_before:
- goal: 回答机主 2026-09-29 的"XGBoost 等其他模型不行吗，多试一些，用最大的努力"。在 B0 的数据、特征、目标和走步切分下，换模型族（XGBoost、CatBoost、Ridge、MLP/NN3、秩均值集成）、训练窗（3 年滚动 / 扩张）、周期（21 / 63 日），排序能力会不会实质变好。
- plan: 预注册 `reports/research/iterations/t20260930_17_model_family_sweep/hypotheses.md`（13:48 写）。阶段 1：24 格，只在压力期，用已缓存的 T-28-10 月度面板；B0 复现核对（0.0200 ± 0.0010）；模型族效应 ≥ +0.010 且 t ≥ 3 算实质改进；按压力期 NW t 取前 3 格（t ≥ 2）进阶段 2。阶段 2（组合，固定 10/20 bp，K1/K2）由主审审完阶段 1 后另发简报。Modal ≤ $3，20 个分片。
- done_when: results_stage1.json（b0_parity、cells、family_effect、answer_family、stage2_cells、modal_cost_usd）+ report.md + 档案通过 pre-backtest 检查；结果标"待主审"。
- brief: reports/research/control/briefs/T-20260930-17.md
- notes:
  - 2026-09-30 16:10 UTC 执行轮（Sonnet 5.5）开始，交给 sonnet-high 子代理。
  - 2026-09-30 17:03 UTC 执行轮完成阶段 1（待主审）：results_stage1.json 24 格齐全，b0_parity=true（LGBM_W3_H21 RankIC 0.020001）、h21_target_check_max_abs_diff 0.0、answer_family=material（仅 WX_H63 组，最好的是秩均值集成 ENS，不是单一模型族；XGB/CAT/Ridge/MLP 各组均 <+0.010）。各组 LGBM → 最好非 LGBM 差值（NW t）：W3_H21 0.02000→ENS 0.02647 +0.00647（2.72）；W3_H63 0.04064→ENS 0.04956 +0.00892（3.55）；WX_H21 0.02323→ENS 0.03145 +0.00822（3.25）；WX_H63 0.04673→ENS 0.05878 +0.01205（4.47）。stage2_cells（规则机械选出）：XGB_WX_H63 t 5.65 RankIC 0.05300、LGBM_WX_H63 t 5.40 RankIC 0.04673、CAT_WX_H63 t 5.21 RankIC 0.05391，三格均为扩张窗 + 63 日周期。换手代理（预测秩自相关）h21 0.486、h63 0.647。Modal 实际花费 $0.2206（烟测 + 20 分片）。子代理提示：H21→H63 的增益按年不均匀，Ridge/MLP 在 H63 最流动三分位（T1）为负。偏差：烟测跑了分片 8（CAT）以同时验 xgboost 与 catboost；--smoke 取前 2 个可训练 fold；预测文件多带 target、adv_tercile；close_wide 无 SPY，加了 spy 阶段（cache/spy_close.parquet）；new_lightweight_iteration.py 覆盖了 hypotheses.md，已从 /tmp/t17-hyp.bak 还原，cmp 与 git diff 为空。未做阶段 2；`--stage final` 被台账路径、评估报告路径和 decision record 的 pending 拦住（主审填）。产物：reports/research/iterations/t20260930_17_model_family_sweep/{results_stage1.json,report.md}，scripts/run_t20260930_17_model_family_sweep.py，tests/test_t20260930_17_model_family_sweep.py。待主审。
  - 2026-09-30 13:52 交互主审（Opus）写预注册和简报。文献 13:47 打开：Gu-Kelly-Xiu 2020 的非线性模型之间 R² 只差 0.33–0.40%；Avramov-Cheng-Metzker 2023 说机器学习的利润集中在微盘股、按合理成本后变差。先验：任何格子过 K1 的概率低于 5%，本任务主要是给机主有证据的答案。训练全在 Modal 上，本机只汇总，可以和 T-14 同轮跑。
  - 2026-09-30 19:20 UTC 19:07 主审轮（Opus）审核阶段 1：b0_parity、h63 的 NW 滞后 2、模型族效应和入选格都按预注册机械核对无误。四组里单一模型族最多比 LightGBM 高 +0.0072（CAT_WX_H63），都不到 +0.010；只有秩均值集成在 WX_H63 过线（+0.0121，t 4.47）。所以给机主的答案是：换模型族几乎不改变排序能力，周期（H63 约为 H21 的 2 倍）和扩张窗影响更大。排序能力集中在流动性差的三分位（入选格 T3 0.070–0.093，T1 ≤0.012、t<1）。阶段 2 的 6 本书不能加进本档案（轻量档案最多一条路径、24 个候选），另建 `t20260930_17b_model_family_book`：19:21 通过 direction-check 和 pre-backtest，简报 T-20260930-19。

### T-20260930-18 机主问题：强化学习与"大模型 + 强化学习"交易的公开证据（接手 T-20260929-31）
- status: done
- priority: 2
- not_before:
- goal: 回答机主 2026-09-29 的"RL 的 Qwen 之类的不行吗"。先读 2025–2026 原文和实盘/前向记录（nof1 Alpha Arena、LiveTradeBench、Trading-R1、FLAG-Trader、Fin-R1、FinRL 比赛、反面证据），只有证据支持才定一个 ≤ $3 的试点。
- plan: 只调研。交互会话派 1 个 Sonnet 5.5 子代理（协调者任务代码 R0930-1345-RL），产出简报、来源快照和登记簿行 `dir:rl_llm_trading_2026`；主审审核后提交。
- done_when: `reports/research/intel/rl-llm-trading-evidence-2026-09-30.md`、`reports/research/intel/sources/rl-llm-2026-09-30/`、登记簿 validate ok；提交。
- notes:
  - 2026-09-30 13:45 交互主审（Opus）派出。自动轮不要碰。
  - 2026-09-30 13:56 交互主审（Opus）审核：结论停放（`dir:rl_llm_trading_2026` parked）。有 RL 训练的证据全是回测，多数不扣成本；实盘记录（Alpha Arena、ChatGPT 微盘股）都是零样本大模型，没有 RL。最强正面证据 Alpha-R1（Qwen3-8B + GRPO，2025 年样本外、每边 10 bp，标普池年化 47.87%、夏普 1.62，作者自报 DSR 0.66–0.84）只有一年、无人复现，训练约 7,680 张 H800 卡时。反面证据：独立 FinRL PPO 夏普 0.559，低于等权 1.115（0.10% 成本，2019–2023）。主审抽核 5 个数字都在快照里；补注 Alpha Arena 数字来自一份 AI 代理写的第三方报告，属三手来源。简报 `reports/research/intel/rl-llm-trading-evidence-2026-09-30.md`，快照 30 个 .txt。


### T-20260930-19 模型族扫描阶段 2：三个 WX_H63 格做成只做多月度组合，固定 10/20 bp 下判 K1/K2（接 T-20260930-17）
- status: done（已主审 2026-10-01 01:30：refuted；parity_failed 由主审裁定为不影响判决，不重跑）
- priority: 2
- not_before:
- goal: 回答机主 09-29「XGBoost 等其他模型不行吗」的赚钱部分：阶段 1 选出的 XGB/LGBM/CAT_WX_H63 做成 V1（全池前 50）/ V2（流动性最差三分位前 50）组合后，能不能在固定成本下过 K1 或 K2？B0 的书（T-28-30）对标窗 flat10 只有 0.33。
- plan: 预注册 `reports/research/iterations/t20260930_17b_model_family_book/hypotheses.md`（19:21，规则照抄 T-17 阶段 2）。一个 Modal 容器（8 核、32 GiB、120 分钟）：重建 T-28-30 cohort → 四个格走步训练（含 B0 复现格）→ 21 个偏移 × flat10/flat20（+AR 只报告）→ 20 种子安慰剂 → K2、DSR（试验 30）。核对：阶段 1 RankIC ±0.002，B0 组合 ±0.05。
- done_when: results.json（parity、books、k1、k2、placebo、dsr、verdict）+ report.md；结果标"待主审"。
- brief: reports/research/control/briefs/T-20260930-19.md
- notes:
  - 2026-09-30 19:25 UTC 19:07 主审轮（Opus）写预注册和简报。先验：任何一本书过 K1 的概率 <5%（阶段 1 的 IC 在成本最高的股票里，K2 要在 S3 最强的 2024–26 年加分）。Modal 最坏约 $1.3，本月已用 $5.09。22:07 执行轮做。
  - 2026-09-30 22:08 UTC 22:07 执行轮（Sonnet）开始，交给一个 sonnet-high 子代理。
  - 2026-09-30 23:10 UTC 22:07 执行轮（Sonnet 5.5，子代理 52 次调用）跑完，待主审。results.json：verdict=parity_failed（`parity.all_ok` false）。阶段 2 对阶段 1 的 RankIC 差（容差 0.002）：XGB_WX_H63 0.0018 ok、LGBM_WX_H63 0.0037 fail、CAT_WX_H63 0.0051 fail、复现格 LGBM_W3_H21 0.0017 ok；B0 组合核对 ok（压力期 0.4621 对 0.462，对标窗 0.3266 对 0.327）。阶段 2 验证形成日比阶段 1 多 2 个（2023-07-31、08-31；74 对 72），在 72 个共同日上均值仍差 0.0008–0.0021（逐日差最大 0.037），多出的日子解释不了差距。六本书 K1、K2 全为 false（对标窗 flat10 夏普：XGB V1 0.163 / V2 -0.172、LGBM V1 0.333 / V2 0.267、CAT V1 0.239 / V2 0.422；压力期 0.300–0.662；K2 对标窗 -0.39 到 -0.66），DSR（试验 30）0.009–0.083，安慰剂对标窗打赢比例 0.00–1.00。Modal 实际 $0.345（烟测两次共 $0.091，本月投影 $8.55）。偏离简报：`--data` 加了 results_stage1.json；首次烟测 20 分钟超时，改 4 核 45 分钟重跑；`--stage cost` 额外写花费。`iteration validate --stage final` 余三项拦截（trial_ledger、evaluation_report、decision_record），留给主审填。产物：`scripts/run_t20260930_17b_model_family_book.py`、`tests/test_t20260930_17b_model_family_book.py`（9 测试过）、`reports/research/iterations/t20260930_17b_model_family_book/{results.json,report.md,results_smoke.json,report_smoke.md}`（results/report/smoke 已 git add -f），日志 `logs/modal-t20260930-19-*.log`。子代理 model 字段核对为 claude-sonnet-5-5。需主审决定：parity_failed（两格 RankIC 偏差超容差）按简报一字不改的规则处理，是调查原因后重跑还是按预注册视为核对失败。
  - 2026-10-01 01:30 UTC 01:07 主审轮（Opus）对照 results.json 审核：六本书 K1、K2 全不过，数字核对无误（对标窗 flat10 最好 CAT V2 0.422，门槛 1.19；K2 对标窗 -0.389 到 -0.664，压力期 +0.003 到 +0.192；DSR 0.009–0.083）。安慰剂：压力期六本全部 1.00；对标窗 LGBM V2、CAT V2 1.00，LGBM V1 0.80，其余 0.00–0.30。池内排序是真的，但流动性最差的小盘池在 2024–26 整体太弱，赚不到钱。parity_failed 的裁定：B0 组合引擎复现一致（0.4621 对 0.462、0.3266 对 0.327）；RankIC 偏差 0.0037/0.0051 都是阶段 2 偏高；书离 K1 差 ≥0.77 夏普，离 K2 差 ≥0.44，0.005 的 RankIC 差改变不了判决。可能原因（推断）：多了 2 个边界形成日，且正式跑换了核数，LightGBM/CatBoost 直方图累加顺序随线程数变，XGBoost hist 不变（XGB 正好是过的那格）。结论 refuted：纯量价排序不再加格子、不再换模型族（预注册写死）。档案 `--stage final` ok（补了 trial-ledger.jsonl、decision-record.md、search-space 的台账路径）。

### T-20261001-01 纲领 A：按结算周期定时的月末现金需求窗口（SPY），能否替换 C2 的 E 腿（Etula 等 RFS 2020；Nathan-Suominen-Tasa 2026）
- status: done（已主审 2026-10-01 07:20：refuted；与 T-02 一起按预注册关闭 dash-for-cash 线，E0 和 C2 不变）
- priority: 1
- not_before:
- goal: C2 的 E 腿 E0 很脆（2026 污染窗夏普 -0.57）。月末现金需求给出一个由结算规则决定、没有自由参数的时点：边际卖出日 b（2024-05-28 前为 τ−4，改 T+1 后为 τ−3）之后买 SPY，持有到下月第 3 个交易日。能否按机主的替换规则替换 E0，或单独过 K1/K2？
- plan: 预注册 `reports/research/iterations/t20261001_01_dash_for_cash_settlement/hypotheses.md`（direction-check、pre-backtest ok，01:29:25Z）。4 个候选（DFC_U、DFC_C 判定；两个固定 τ−4 的对照不可采用）加 E0_REF 复现。screen_batch 一次评估，100 种子随机入场安慰剂，日位置剖面与换窗诊断。替换 E0 四条：选择窗 10 bp ≥1.439、2026 ≥ -0.674、选择窗 20 bp ≥1.271、压力期 ≥0.584，加安慰剂 ≥0.90；过了只是给机主的提议。
- done_when: results.json（parity、candidates、replacement、k1、k2、diagnostics、verdict）+ report.md + leaderboard；结果标"待主审"。
- brief: reports/research/control/briefs/T-20261001-01.md
- notes:
  - 2026-10-01 01:40 UTC 01:07 主审轮（Opus）写预注册和简报。先验：K1 <10%，替换 E0 约 20%。本地 SPY 日线，很轻，60 分钟上限。04:07 执行轮做。
  - 2026-10-01 04:10 UTC 04:07 执行轮（Sonnet）开始执行。
  - 2026-10-01 04:40 UTC 执行轮（子代理 claude-sonnet-5-5）跑完。results.json：parity.all_ok=true（E0_REF 1.339/1.241/0.584/-0.574 复现）；机械 verdict=refuted。DFC_U 选择窗10bp -0.765、20bp -1.329、对标窗 -0.500、压力期 0.112、2026 0.787，K2 -0.554/-0.252，安慰剂 beat 0.03/0.16/0.77；DFC_C -0.379/-0.633/-0.104/0.359/1.230，K2 -0.349/-0.082，beat 0.14/0.60/0.94。替换四条仅 b（2026）过，a/c/d 和 placebo_ok 不过，replacement.pass 两者皆 false。诊断：换窗 post-pre -9.39bp NW t -0.42（27/100 月）；前后窗相关 改革前 -0.293(100月) 改革后 +0.035(28月)；C2 近似 50/50 混合 DFC_U 选择窗 0.284、DFC_C 0.557 对 E0 1.076。偏离：不完整的 2026-09 月不入；换窗 t 用 OLS+HAC(3)而非 newey_west_t。`iteration validate --stage final` 有 3 个拦截项（search_space 的 trial ledger / evaluation report 路径为空、decision record 缺 continue/pivot/stop），执行轮未动，留主审。产物：scripts/screen_batches/t20261001_01_dash_for_cash.py、scripts/run_t20261001_01_dfc_placebo.py、tests/test_t20261001_01_dash_for_cash.py（7 个通过）、reports/research/screens/t20261001_01_dash_for_cash/、iterations/t20261001_01_dash_for_cash_settlement/{results.json,report.md}。待主审。
  - 2026-10-01 07:20 UTC 07:07 主审轮（Opus）对照 results.json 逐条核对：parity 全为 0 差；DFC_U/DFC_C 替换四条只过 b（2026），a/c/d 和安慰剂不过（选择窗打赢 0.03/0.14），K1 对标窗 -0.500/-0.104 < 1.19，K2 两窗为负。前视、成本、调仓日三项无问题（b 由交易所日历决定，窗口无自由参数，安慰剂随机化入场日）。死因：信号在可交易的窗口上太弱，不是执行问题。补齐 final 校验（trial-ledger.jsonl、search-space 的报告路径、decision-record 写 Stop），`iteration validate --stage final` ok。登记簿追加 refuted 行。

### T-20261001-02 纲领 A：月末现金需求在我们数据里的横截面痕迹（P500 动量输家；机制测量 M1–M3，不是候选）
- status: done（已主审 2026-10-01 07:20：M1 不过 → 按预注册关闭 dash-for-cash 线；M3 日级换窗复现，只记为组合 ML 的日历特征线索）
- priority: 1
- not_before:
- goal: Nathan 等 2026 说机构为月末现金卖出动量输家，[τ−9, τ−4] 落后大盘约 7.9 bp/天，改 T+1 后边际卖出日从 τ−4 移到 τ−3（DiD +85.9 bp，t 2.68）。在我们 2016–2026 的 P500（含退市股）上测：M1 前窗输家落后（门槛 NW t ≤ -2），M2 后窗反弹，M3 换窗（含论文样本外的 2026 年 9 个月末），并报只做多输家反弹的扣成本收益。决定 T-01 的时点有没有机制支撑、要不要做横截面阶段 2。
- plan: 同一预注册的"横截面机制测量"一节。读数照 T-35（`t35.load_wide_float32` + `price_hygiene`），P500 按 63 日成交额中位数，12-1 动量十分组，成交额加权为主。
- done_when: results_xs.json（m1、m1_pass、m2、m3 三个版本、trade）+ report_xs.md；结果标"待主审"。
- brief: reports/research/control/briefs/T-20261001-02.md
- notes:
  - 2026-10-01 01:40 UTC 01:07 主审轮（Opus）写简报。M1 过的先验约 60%（论文 2002–2025 β2 -8.5 bp，t -2.2；S&P 500 成分更强）。读全市场日线，run_capped 1.8G，90 分钟上限；与 T-01 并行时等 T-01 的 screen_batch 跑完再读数据。
  - 2026-10-01 04:10 UTC 04:07 执行轮（Sonnet）开始执行。
  - 2026-10-01 04:40 UTC 执行轮（子代理 claude-sonnet-5-5）跑完（panel 在 04:31 开始，等待 T-01 leaderboard 超 25 分钟）。results_xs.json：n_months 115（2017-02→2026-08），P500 池中位 500，曾出现退市股 219。M1 d1_dv 系数 -7.66bp/天 NW t -0.86，m1_pass=false（改革前 -9.57 t -0.88，改革后 -1.75 t -0.12）；M2 后窗 +10.86bp t 2.02（改革前 +10.22 t 1.70，后 +13.20 t 1.12）；M3 θ4−θ3：overlap_2024_2025 127.78bp t 3.00，out_of_paper_2026 120.70bp t 1.58（8 个改革后月），combined 125.68bp t 3.05（θ4 +81.66，θ3 -44.03）。交易（era 口径）d1_dv net10 月均：压力期 113.58bp 夏普 0.70、对标窗 99.17bp 夏普 0.60；d1_dv_minus_spy 压力期 32.17bp 夏普 0.27、对标窗 48.91bp 夏普 0.39。偏离：日历自 2016-01 起，首个可形成月 2017-01，压力期实际自 2017-02；_load_spy 只返回隔夜收益，改写了开收盘读取；组别在 τ_f+4 到 τ_{f+1}+3 冻结（简报未定）；剔除疑似拆股日；退市后缺失收益剔除（偏向做多输家，已写入报告）。产物：scripts/run_t20261001_02_dfc_cross_section.py、tests/test_t20261001_02_dfc_cross_section.py（6 个通过）、iterations/t20261001_01_dash_for_cash_settlement/{results_xs.json,report_xs.md}、cache/、logs/t20261001-02.log。待主审。
  - 2026-10-01 07:20 UTC 07:07 主审轮（Opus）对照 results_xs.json 核对：M1 d1_dv -7.66 bp/天 NW t -0.86（门槛 ≤ -2），m1_pass=false；M2 +10.86 bp t 2.02；M3 θ 125.7 bp t 3.05（论文样本外 2026 年 8 个月 120.7 bp t 1.58）；对冲后的输家交易 D1-SPY 净夏普 压力期 0.27 / 对标窗 0.39。幸存者偏差：含退市股 219 只；退市后缺失收益被剔除，偏向让 M1 失败，但要把 t 从 -0.86 推到 -2 需要上百次 P500 名字在六天窗口内 -30% 退市，不可能，判决不变。执行偏离（组别冻结窗、剔除拆股日、2017-02 起）不影响结论。

### T-20261001-03 组合线 D2+D3：面板、唯一收益口径、回测核心、评估、风险模型
- status: done（2026-10-04 08:33 UTC 交互会话对账补记：10-01 的会话从没把状态关掉；D2/D3 的交付物 panel.py、returns.py、backtest.py、evaluate.py、risk.py 已提交，v1、v1.2 都在用）
- priority: 1
- not_before:
- goal: 搭 `docs/equity-book-design.zh.md` 第 3、6、13 节的基础：所有组合实验共用一套面板、一种收益口径、一个回测核心和一个风险模型。H-20260929-12（唯一一次对冲多因子尝试）死于口径错位，Stage 0 的 252 日 beta 对冲又留下 0.5–0.9 的实现 beta。这两件事都要在这里解决。
- plan: 交互会话已派子代理执行，代码在 `open_composer/research/equity_book/`（`panel.py`、`returns.py`、`backtest.py`、`evaluate.py`、`risk.py`）和 `scripts/build_equity_book_panel.py`。数据写到 `data/research/equity_book/`，验证报告写到 `reports/research/program/risk-model-v1-2026-10-01/`。定时轮不要碰这些文件。
- done_when:
  - 四项口径单元测试通过：SPY 复现、两股合成、融资公式、标签和持仓收益一致；
  - Stage 0 的 LS_RAW MOM_12_1 P1000 对齐回归误差 ≤1e-6；
  - 风险模型偏差统计在 0.8–1.2，预测 beta 中性化后实现 |β| 均值 < 0.15，做了 PCA 交叉核对；
  - 主审逐条核对。
- notes:
  - 2026-10-01 06:33 UTC 交互会话派 Sonnet 子代理开始，预算约 2.5 小时。

### T-20261001-04 组合线 D4+D7：成本模型（Alpaca NBBO 抽样校准）+ 易借代理
- status: done（2026-10-04 08:33 UTC 交互会话对账补记：10-01 的会话从没把状态关掉；D4/D7 的交付物 costs.py、cost_model_v1.json、borrow.py 已提交，v1、v1.2 都在用）
- priority: 1
- not_before:
- goal: 设计第 7 节和第 2 节的 SE_t。
  - 用实测价差替换固定 10 bp 和日线 AR 价差（后者偏高 20–60 倍，见数据坑 #58）。
  - 用 Alpaca 当天的 easy_to_borrow 标记，标定个股空头的资格规则。Stage 0 在次流动池的强结果全来自做空稀释型小微盘，借券是关键约束。
- plan: 交互会话已派子代理执行，代码在 `open_composer/research/equity_book/costs.py`、`borrow.py`、`cost_model_v1.json`，以及 `scripts/sample_equity_book_spreads.py`、`scripts/snapshot_alpaca_assets.py`。资产接口只读，不碰任何下单接口。定时轮不要碰这些文件。
- done_when:
  - 半价差模型的留出误差和分十分位校准表，开盘段、午间、收盘段各一套；
  - 易借代理按 ADV 分档报告精确率和召回率，并推荐 v1 规则（精确率目标 ≥0.97）；
  - 主审核对。
- notes:
  - 2026-10-01 06:34 UTC 交互会话派 Sonnet 子代理开始，预算约 2 小时。

### T-20261001-05 组合线 S1：信号库 v1（10 个主题，时点正确，U3000 每日）
- status: done（交互会话主审 14:12 核验并提交 414ad18：年度构建 2017–2026 完整，54 条组合线测试通过，可见性辅助函数审读无前视；简报要求的 IC 测量报告没做，信号层分窗口和分阶段表现见 b963aa0 的 regimes-2026-10-01）
- priority: 1
- not_before: T-20261001-03 的 D2 部分交付并提交（面板 `data/research/equity_book/panel/` 存在，`returns.py` 测试通过）
- goal: 设计第 4 节。按文献方向，把价值、质量/盈利、投资/发行、动量、低风险、盈余、内部人、卖空信息、季节性、快信号做成统一处理的截面分数，供 M0–M3 合成。证据（`reports/research/intel/pro-equity-evidence-2026-10-01.md` 第 3 节）：扣成本后靠得住的是慢信号；快信号只进 ML。
- plan:
  - **代码和数据**：`open_composer/research/equity_book/signals.py` 和 `scripts/build_equity_book_signals.py`，输出 `data/research/equity_book/signals/<year>.parquet`。长表，(trade_date, symbol)，只含 U3000 成员，每个信号一列原始值、一列处理后的 z，float32，按年分块。
  - **处理流程**（按日截面）：
    1. 1%/99% 截尾；
    2. 秩转换成正态分数；
    3. 价值和质量类在 FF48 行业内去均值，行业取面板的 ff48；
    4. 缺失记 0；
    5. 每个信号另存覆盖标记。
  - **信号清单**，严格按设计第 4 节的表：
    - bm、ep、sp、cfp。市值 = close × shares_outstanding。净利润、毛利、经营现金流是年报口径，见 `scripts/build_sec_xbrl_fundamentals.py` 的文档字符串；
    - gp_at、roe、op_at、−accruals；
    - −asset_growth、−nsi_12m；
    - mom_12_1、ind_mom_12_1、resid_mom_12_1；
    - −beta_252（Vasicek 收缩）、−idio_vol_63；
    - sue_eps、sue_rev；
    - cmp_opportunistic_buy_60d、net_buy_usd_nonplan_60d / 市值；
    - −short_volume_ratio_mean_21、−SI/股本；
    - 同月季节性：过去 5 年同一日历月的平均月收益，Heston-Sadka；
    - 快信号：行业调整的 21 日反转、ON252（`intraday_daily` 或日线 open/close 计算）、alpha101/alpha191 中覆盖完整的列、news_attention（2024 起）。
  - **时点检查**，必须写测试：
    - 基本面按 `sec_fundamentals_daily` 已对齐的日期用；
    - 内部人用 `visible_at`；
    - 空头成交用 `visible_date`；
    - 任何信号都不能用到 t 日收盘以后的信息。
  - **度量报告**：`reports/research/program/signals-v1-2026-10-01/`。这些数字只是对看过的数据做度量，不用来挑信号；M0 预注册用全部慢信号。报告内容：
    - 每个信号按年的覆盖率；
    - 对未来 21 日开盘到开盘收益（原始收益和行业调整收益两种）的秩 IC，压力期和对标窗分开报，带 NW t；
    - 信号之间的相关矩阵；
    - 月度秩自相关。证据给的量级是价值、质量、动量 0.87–0.94，可以用来核对。
  - **内存**：用 duckdb 按年处理，跑 `scripts/run_capped.sh --mem 1.8G`。
- done_when:
  - 代码、测试（ruff 和 pytest）、信号 parquet、度量报告都完成；
  - 不改动 `equity_book` 里别的模块，只新增 `signals.py`；
  - 主审核对时点测试和覆盖率。
- notes:
  - 2026-10-01 06:43 UTC 交互会话（Opus）写入。
  - 2026-10-01 07:20 UTC 交互会话派 Sonnet 子代理执行（D2/D3 已在 12d9cef 交付）。定时轮不要碰。

### T-20261001-06 组合线 D5：优化器（cvxpy + Clarabel）
- status: done（交互会话主审 14:12 核验并提交 414ad18：重试阶梯把首次求解失败全部救回，anchor_2024|A|vasicek 从 7.7% 降到 0%；未结项按 A1 第 4 节带入 Stage 2a：50% 的 optimal_inaccurate 离最优多远未核实，1e-9 参照解全部报错；Reg T 超 2.02E 的天数只报告）
- priority: 1
- not_before: T-20261001-03（D3 风险模型）和 T-20261001-04（D4 成本模型、D7 易借代理）都交付并提交
- goal: 设计第 8 节。把 α、风险模型、成本和借券放进同一个优化，得到满足中性和容量约束的目标持仓。这是组合线最核心的一块，传导系数主要由它决定。
- plan:
  - **加依赖**：`uv add cvxpy`，钉住工具调研实测过的 1.9.x，Clarabel 随 cvxpy 一起装。先看 `reports/research/intel/pro-equity-2026-10-01.md` 第 5 节的共存性证据。提交说明里写明 pyproject 和 uv.lock 的改动。
  - **`open_composer/research/equity_book/optimize.py`**，按设计第 8 节实现：
    - 目标：α'w − 风险项 − 半价差 × |Δw| − 冲击 × |Δw|^1.5 − 借券；
    - 约束：
      - 美元中性，ETF 对冲也计在内；
      - |β'w| ≤ 0.02，β 取风险模型的预测 beta；
      - 每个行业 ≤ 0.01；
      - 规模 ≤ 0.10，其他风格 ≤ 0.25；
      - 单名 |w| ≤ 0.01；
      - 总敞口 ≤ 1.0；
      - 空头只允许 SE_t 内的个股或 ETF，F1b 只允许 ETF；
      - 整股：空头价格 ≤ 0.01E；
      - E = $100 万时，单笔参与率 ≤ 1% ADV；
      - 事前年化波动 ≤ 5%，用风险约束表达，不手调 γ。
    - 风险项用因子形式（y = X'w），不要构造 N×N 矩阵。
    - 尽量用 cvxpy Parameter（DPP），避免每个日期重新编译。
    - 求解失败时沿用上期持仓，并记录失败。
  - **接口**：给 `backtest.run_book` 提供 `decide()` 适配器，参数是 α 来源、宇宙和形态（A、B、C 三种宇宙/空头配置）。
  - **测试**：
    - 无成本、无约束时与闭式均值方差解一致；
    - 所有约束在解里成立；
    - 失败时回退；
    - 整股和空头资格过滤生效。
  - **冒烟测试**：只验证管道能跑通，不做任何判定，结论不进任何报告的结论段。用 Stage 0 缓存里的 MOM_12_1 分数当 α，跑 2024 年一年的周频回测，报告：
    - 求解时间、峰值内存、失败率；
    - 事前与实现的 beta 和波动。
- done_when:
  - 代码、测试和冒烟报告 `reports/research/program/optimizer-v1-2026-10-01/` 都完成；
  - 冒烟中 N=3000 单次求解 < 10 s、峰值 < 1 GB；
  - 主审核对。
- notes:
  - 2026-10-01 06:43 UTC 交互会话（Opus）写入。
  - 2026-10-01 07:47 UTC 交互会话补记：D5 子代理 07:33 前后已开始（D3 在 12d9cef、D4/D7 在 c2bea42 交付），当时没有立刻改状态，07:07 主审轮因此写过重复简报后撤回。以后交互会话先改队列状态再派子代理。定时轮不要碰。

### T-20261001-07 组合线 Stage 2a 预注册（主审写）
- status: done（主审 2026-10-01 07:31：direction-check ok，iteration validate --stage pre-backtest ok；版本修正案 A1 待 T-05、T-06 和 D3.1 完成后由主审写，写之前不运行）
- priority: 1
- not_before:
- goal: 在任何 Stage 2 结果出来之前，把设计第 9 节的 12 个变体和第 10 节的门槛写成机器可读的预注册，接上 v3 迭代的标准入口。
- plan: 主审（Opus）自己写，执行轮不做。
  1. 登记簿新增 `dir:multi_signal_risk_controlled_equity_book`。依据见 `reports/research/program/review-2026-10-01.zh.md` 和 `reports/research/intel/pro-equity-evidence-2026-10-01.md`。写明它和已否定的单独异象方向的区别：判法是组合层面的净夏普，宇宙和空头受易借约束。
  2. `uv run oc research iteration init t20261001_book_v1`。
  3. 写 `direction-review.json`，以及含 12 条的候选清单。条目是 M0–M3 × A/B/C，周频，5 个偏移按中位数判。参数固定为设计第 9 节的值；成本模型和风险模型的版本号在 D3、D4 交付后填入，填入前不运行。
  4. 跑 `uv run oc research direction-check <path>` 和 `uv run oc research iteration validate t20261001_book_v1 --stage pre-backtest`。
  5. DSR 的试验数写 77，即 12 个变体加 Stage 0 的 65 格。
- done_when:
  - 两道检查都通过；
  - 候选清单的门槛与设计第 10 节逐字一致；
  - 已提交。
- notes:
  - 2026-10-01 06:43 UTC 交互会话（Opus）写入。
  - 2026-10-01 07:31 UTC 07:07 主审轮（Opus）完成：`reports/research/iterations/t20261001_book_v1/`（hypotheses.md 第"预注册全文"节、direction-review.json、candidate-manifest.json 12 条、search-space、data-feasibility、cost-table、lightweight-config），草稿规格 `strategy_specs/drafts/t20261001_book_v1.yaml`（oc spec validate ok），来源卡 `reports/harness/source_cards/t20261001_book_v1.jsonl`（8 张，引文都在快照里核对过），登记簿新增 `dir:multi_signal_risk_controlled_equity_book`（queued）。门槛逐字沿用设计第 10 节，另加三条只会更严的条件：K2 还要在现金对齐口径（净收益 − BIL + SHY）下成立（主审用零 α 空书测出 BIL 对 SHY 的利差在冻结口径下白送 +0.03 / +0.09）；实现 beta 还要过 Dimson beta；2 倍成本重放同一条权重路径。M2、M3 的超参数现在就固定（防止看到 2a 后再调）。安慰剂按种子轮换偏移，只对过了 K1/K2 的变体做。DSR 试验数 77。

### T-20261001-08 组合线 Stage 2a 运行：M0、M1 × A/B/C（6 个变体）
- status: done（已主审 2026-10-01 19:25：路径完整；交互会话 17:55 的否定判定经原始 JSON 复核成立；三项待主审事项都不改判决，跨年缺陷交 T-20261001-22 修）
- priority: 1
- not_before: T-20261001-05 和 T-20261001-06 的状态都以 done 开头（交互会话核验并提交 S1、D5）。修正案 A1 的规则部分已由 13:07 主审轮写好（`reports/research/iterations/t20261001_book_v1/amendment-A1.md`、`amendment-A1.json`），版本绑定表由本任务第 0 步按 A1 第 8 节机械填写
- goal: 第一次用完整管道检验"多信号组合"在两窗扣成本后能不能过冻结门槛。M0 是所有 ML 方法必须超过的基线。
- plan: 按 T-07 的预注册执行。
  - 用 `run_book`，周频调仓，5 个偏移；成本模型 v1，同时报告固定 10 bp 和 20 bp 两档对照；
  - 安慰剂：每个日期内打乱 α，100 个种子，构建方式不变。本机太慢就上 Modal，启动前先过 `scripts/modal_budget.py check`；
  - DSR 的试验数用 77。
  - 每个变体报告：
    - 净夏普、K1、K2 增量；
    - 实现 beta、行业和风格暴露；
    - 换手、成本占比；
    - 按主题去掉一个的边际贡献；
    - 固定压力日的表现。
- done_when:
  - 迭代 `--stage final` 通过；
  - `results.json` 里的每条门槛都有数字；
  - 状态写"done（待主审）"，不写结论。
- brief: reports/research/control/briefs/T-20261001-08.md
- notes:
  - 2026-10-01 06:43 UTC 交互会话（Opus）写入。
  - 2026-10-01 13:29 UTC 13:07 主审轮（Opus）：写修正案 A1（成交改为 t+1 收盘，依据只有 D4 成本测量，07:50 纲领已预告；记账规模 $1,000,000，否则冲击成本按 1 美元计；IC_t 和 M1 按预注册定义实现；watch_recent 分档；安慰剂净、毛两种口径都要达标，比预注册更严）和简报。范围缩为"跑出 54 条路径的原始结果"（45 条主路径加预注册第 7 节的 9 条去掉一个主题的诊断）：评估拆到 T-20261001-13，安慰剂拆到 T-20261001-14。本轮没有任何 Stage 2 数字。执行轮在 T-05、T-06 标 done 之前不要取本任务。
  - 2026-10-01 16:42 UTC 执行轮（Sonnet 5.5 子代理）：54/54 条路径在 Modal 跑完（45 主路径各 6 个文件，9 条诊断各 5 个）；A1 binding 填写于 16:07:48Z，提交 eaffba6；清单 `reports/research/iterations/t20261001_book_v1/stage2a-manifest.json`（提交 3154bec，all_binding_true=true，bound_before_all_files=true）；原始输出在 `.../cache/stage2a/shard_<i>/<path_id>/`（不提交）。本机管道检查 12 次调仓 0 失败，重放恒等最大差 0.0，测试 10 个通过，ETF 缓存预热 27 s；Modal 花费约 $0.88（账单 status 显示 $0.7055）。待主审：(1) 缺陷（受 A1 绑定，未修）：`RiskModel.at()` 不跨年回看，1 月初在当年第一个存盘日之前的调仓报 no_risk_model，占 45 条主路径 190 次最终失败中的 189 次（另 1 次 violation）；子代理预先计数偏移 0–4 失败率 0%、1.07%、1.28%、1.71%、0.43%，T-13 要对照 2% 门槛说明；(2) A1 未规定的实现选择：M1 主题 IC 窗口跳过未定义的 IC，主题有效 IC 不足 24 个时权重为 0（seasonality 18 个月未定义、short_info 6 个）；每月更新取日历月与上次更新不同的第一个调仓；主题名按 signals.THEMES（investment 不是 investment_issuance）；(3) 形成日有 6 个因 no_risk_model 被跳过（2017-01..06，风险模型始于 2017-07）；SCS 阶梯救回 0 次；容器内峰值内存为 nan；Modal 命令用了 --no-etf-flush。安慰剂计划已实现并测试、未运行。下一步：T-20261001-13（评估）读清单路径。
  - 2026-10-01 19:25 UTC 19:07 主审轮（Opus）复核：`results.json` 6 个变体的偏移中位数净夏普，对标窗 −0.325（M0_B）..0.700（M1_C），压力期 −0.335..0.210，没有一个达到 K1（1.19/0.65），K2 两种口径全 false，与交互会话 17:55 的判定一致。待主审三项：(1) 失败率偏移中位数 1.07%、最大 1.71%，都低于 2% 门槛，`failure_ok` 全 true；189 次 `no_risk_model` 是 `RiskModel.resolve()` 只查当年存盘日造成的（risk.py 第 350 行，读代码确认），离门槛最近的 M1_C 也差 0.49，所以不改判决，修复交给 T-20261001-22，v1.1 绑定新的哈希；(2) M1 的实现选择（IC 至少 24 个、按日历月更新、主题名）都写在 `scripts/build_book_v1_alpha.py` 的文档字符串里，v1.1 的预注册要把它们写成明文；(3) 2017-01..06 跳过的 6 个形成日是数据起点决定的，不是缺陷：风险模型 2017-07 才有，之前算不出残差目标；书的压力窗从 2017-10 起。另做了预注册停止条件的核对：M0 残差 IC 在对标窗 t = 1.16（U3000）、0.91（P1000），小于 2，条件成立（`scripts/summarize_book_residual_ic.py` → `t20261001_book_v1/residual-ic-summary.json`），结论写进纲领主线 1。
### T-20261001-09 组合线 Stage 2b：M2（GBDT 集成）和 M3（随机傅里叶特征岭回归），Modal
- status: cancelled（17:55 UTC 交互会话主审：v1 在 Stage 2a 机械否定，死因是组合构造，换合成器解决不了；ML 合成器在 v1.1 的构造下再测，见 `t20261001_book_v1/decision-record.md`）
- priority: 2
- not_before: T-20261001-08 完成
- goal: 设计第 5 节。检验 ML 合成在同数据、同成本、同组合构建下，能不能超过 M0（ml_contribution_pass）。
- plan:
  - **M2**：复用 T-17 的 Modal 管道。
    - 目标：21 日残差收益的截面秩。
    - 每年重训，训练和预测之间间隔 ≥21 个会话。
    - 特征：信号库全部列，含快信号。
  - **M3**：约 100 个特征生成 4,000 个随机傅里叶特征，做岭回归；惩罚在验证折上从 {1e-3 … 1e3} 选。
  - 两者预测完都按 T-08 的同一管道和门槛评估，变体是 M2、M3 × A/B/C，共 6 个。
  - 每次启动都先过 `scripts/modal_budget.py check`。
- done_when: 同 T-08。另外单独报告 ML 贡献。
- notes:
  - 2026-10-01 06:43 UTC 交互会话（Opus）写入。

### T-20261001-10 组合线 D3.1：风险模型修正（beta 预测、统计主题因子、波动状态）
- status: blocked（交互会话 10:18 降级：不挡 Stage 2a，见 notes；定时轮不要碰）
- priority: 2
- not_before: T-20261001-05（S1）的重任务结束（一次只跑一个重任务）
- goal: D3 验证（`reports/research/program/risk-model-v1-2026-10-01/`）在 2024–26 暴露出三个问题。在缺陷已知的风险模型上跑 Stage 2a 等于浪费算力，所以先修。
  1. 动量类书按预测 beta 对冲后，对标窗仍有 +0.40（EWMA-63）到 +0.75（模型隐含）的带符号 beta 偏差，压力期约 0。
  2. 这类书的波动被低估，对标窗偏差统计为 1.34（随机组合是 1.04，正常）。
  3. 残差的 20 因子 PCA 比随机打乱基准多解释 0.10–0.26，说明模型漏掉了共同因子（AI、加密货币、散户题材之类）。
- plan:
  - **(a) beta 预测**。候选：
    - EWMA，半衰期 21、42、63；
    - Welch 2022 "Simpler Better Market Betas"（斜率截尾、按时间衰减）；
    - 向行业均值做 Vasicek 收缩（现在是向截面均值）；
    - 特征调整 beta：用已有 beta、动量、波动、行业 beta 预测未来 63 日 beta，在压力期拟合。

    选择标准是压力期个股 beta 的预测均方误差，不用对标窗挑。对标窗只报告对冲后的带符号偏差。Welch 2022 要先打开原文、存快照。
  - **(b) 混合风险模型**：在基本面因子之外加 5–10 个统计因子，来自过去 252 日残差的 PCA，每月重估。统计因子的协方差和特质方差照常估计。
  - **(c) 因子波动的状态调整**：仿 Barra USE4 的 VRA，用横截面偏差统计调整因子协方差的整体尺度。
  - 只改 `open_composer/research/equity_book/risk.py` 和它的构建、验证脚本。保持接口不变，新增方法用参数开关，旧行为留作 v1。
- done_when:
  - 随机组合偏差统计两窗都在 0.8–1.2。
  - Stage 0 的 MOM 和 COMP4 十分位书，偏差统计两窗都在 0.8–1.2。
  - 这两本书先在行业内中性化，再按选定 beta 对冲，两窗按窗口计算的带符号实现 beta，用日频 OLS 和 Dimson 两种口径都在 ±0.15 以内。
  - 测试通过，报告写到 `reports/research/program/risk-model-v1.1-2026-10-01/`，主审核对。
  - 若修不到，写清哪一条不行、原因是什么，由主审决定 Stage 2a 用哪一版，或者推迟。
- notes:
  - 2026-10-01 07:50 UTC 交互会话（Opus）写入。D5 的冒烟测试会在全约束下测几种 beta 的实现偏差，D3.1 开工前先读它的结果。
  - 2026-10-01 10:18 UTC 交互会话（Opus）读了 D5 冒烟结果：优化器带 |β'w| ≤ 0.02 约束后，对标窗 2024 年 12 组的实现 beta 在 −0.03 到 +0.075 之间（标准误约 0.03），离 ±0.15 门槛很远。D3 的 +0.40 偏差出在"十分位书再用 SPY 对冲"的做法上，没有出现在优化后的书里。因此 D3.1 不再挡 Stage 2a：Stage 2a 先用 EWMA-63 beta 跑，D3.1 降为 priority 2，在 Stage 2a 之后视结果再做。

### T-20261001-11 组合线：大盘阶段划分与各信号分阶段表现（机主 10-01 要求"适合现在"）
- status: done（2026-10-04 08:33 UTC 交互会话对账补记：结果已提交，见 b963aa0）
- priority: 1
- not_before:
- goal: 机主要求筛选重点看是否适合现在：按 2024-01..2026-06 和 2026-07..至今分开看，或结合大盘切成合理阶段。用代码把阶段切出来，量出每个信号、主题和风险模型风格因子在各阶段、各窗口、各事前市场状态下的表现，并检验"按近期表现加权"（因子动量）是否有增量。结果作为修正案 A1 改窗口的依据和合成器设计输入，不用来挑信号。
- plan: `scripts/analyze_equity_book_regimes.py`。两步：先只用市场数据定阶段（SPY 收盘回撤 ≥7% 的高点、低点、收复点切段，加机主节点 2026-07-01；VIX 三分位只用 2016-01..2023-08 拟合），规则写在代码里，然后才算信号收益。信号收益是行业内、beta 对冲后的多空日收益，t 日收盘的分数从 t+1 开盘持有到 t+2 开盘。
- done_when: `reports/research/program/regimes-2026-10-01/` 有 report.md 和 results.json，主审写结论。
- notes:
  - 2026-10-01 10:18 UTC 交互会话（Opus）写入。

### T-20261001-12 组合线：既有研究成果审计（哪些能复用、哪些要重做、哪些进因子/择时/另类数据/大模型层）
- status: done（2026-10-04 08:33 UTC 交互会话对账补记：结果已提交，见 2d8b3e9）
- priority: 1
- not_before:
- goal: 机主要求用专业方式评估之前的研究有没有能用的、要不要重做、能不能组合成需要的因子模型和择时。登记簿 414 条逐条分类，回答每条被否定的原因是"信号本身不存在"，还是"信号是真的、但被单独只做多的研究单位或执行假设判死了"，并给出复用去向和优先级。
- plan: 子代理按评分规则逐条分类，只引用登记簿和证据文件里已有的数字，不重跑实验。主审抽查排名靠前的条目。
- done_when: `reports/research/program/prior-work-audit-2026-10-01/` 有 audit.json 和 report.zh.md，主审核对后写结论。
- notes:
  - 2026-10-01 10:18 UTC 交互会话（Opus）写入。

### T-20261001-15 组合线 RF1（机主 10-01 近期适配合同）：M0V、M0X 的 30 条新路径和 RF1 逐条判定
- status: done（17:55 UTC 交互会话主审自己算完并判定，不派子代理：RF_M0、RF_M1 用 T-08 的收盘路径算出 6 个变体 R1 都低于 0.87，全部 none；RF_M0V、RF_M0X 的 30 条路径取消，约束事实写在 `t20261001_book_rf1/report.md` 第 2 节和 `decision-record.md`；脚本 `scripts/eval_book_rf1.py`）
- priority: 1
- not_before: T-20261001-08 完成（共用运行器和 A1 的版本绑定）；判定部分在 T-20261001-13、T-20261001-14 之后
- goal: 机主 10-01 要求筛选看是否适合现在，通过后直接上模拟盘（前向两周只验证执行）。独立合同 `reports/research/iterations/t20261001_book_rf1/` 按这个标准判定同一组合：
  - A 窗 2024-01-08..2026-06-30 定通过（净夏普 ≥1.19 研究通过，≥0.87 观察档）；
  - B 窗 2026-07-01..09-17 查没坏；
  - 去掉任一阶段的稳健性；
  - 安慰剂净、毛两种口径；
  - 2017–2023 只做崩溃诊断。
- plan:
  1. 用 T-08 的同一个运行器和 A1 绑定的版本，跑 RF_M0V_{A,B,C} 和 RF_M0X_{A,B,C}，各 5 个偏移，收盘口径，加四种记账重放，共 30 条主路径。Modal 在纲领 $10 总额内。
  2. **M0V**：t 日收盘的 VIXCLS（`data/research/vix/VIXCLS.csv`，缺值沿用前值、最多 3 天）> 20.60 时，该次调仓的总敞口上限和事前波动目标都乘 0.5，否则不变。
  3. **M0X**：`reports/research/iterations/t20260930_17b_model_family_book/cache/predictions_{LGBM,XGB,CAT}_WX_H63.parquet` 三个模型在当日多头宇宙内各取百分位秩，取平均后转正态分，作为第 10 个主题 `ml_pv`，与 9 个慢主题等权。只用 trade_date ≤ 决策日 t 的预测。
  4. **RF1 判定**：按合同 hypotheses.md 第 5 节 R1–R8 逐条计算。RF_M0、RF_M1 直接用 T-08 的收盘路径；阶段取 `data/research/equity_book/regimes/phases.json` 的 phases_recent（P01..P10 在 A 窗内）；安慰剂按 T-14 的做法，只对 A 窗净夏普 ≥0.87 的变体做。
- done_when: 合同目录下有逐条判定的 results.json 和 report.md；状态写 done（待主审）。
- notes:
  - 2026-10-01 14:17 UTC 交互会话（Opus）写入。合同冻结时 v1 档案下没有任何 Stage 2 结果文件。

### T-20261001-16 组合线：支持做空的组合下单引擎（模拟盘前置，机主 10-01 同意多开模拟账户）
- status: done（10-02 04:00 UTC 主审核对后提交 e618915。tests/test_book_paper.py 57 passed，全套 4037 passed / 0 failed；quant1 只读 dry-run：数据时效检查按设计拦下，加 --as-of 2026-09-18 后 13 项全过；没有下单。下一步缺的是当天价格，即 T-22 的 live 数据，以及对账要用的收盘和 15:45 价格文件）
- priority: 1
- not_before: 无，代码可以先写。机主 10-01 约 17:30 已开 quant1、quant2（各 $1M）并授权细节由主审决定（`reports/research/control/owner-authorization-2026-10-01-book-paper-accounts.md`）；下单仍要变体达到 watch_recent 并通过 dry-run 检查表
- brief: reports/research/control/briefs/T-20261001-16.md
- goal: 组合线不管是 RF1 还是 v1 + A1 过线，都要上模拟盘，前向两周只验证执行。现有 `open_composer/paper_rehearsal.py` 第 296 行硬性要求 `position_direction == "long_only"`，只能跑 ETF sleeve，不能跑 100–250 只股票的多空中性组合。
- plan（主审写简报时细化）：
  - **输入**：每天由 `optimize.py` 生成的目标权重（含 TBILL 腿），先记信号日志，再生成订单。
  - **下单**：Alpaca `time_in_force=cls` 收盘竞价单，美东 15:50 前提交；整股取整，空头只用整股；空头下单前查 `easy_to_borrow`。
  - **多账户**：每个组合一个模拟账户，凭据按变量名从 env 文件读取。代码不打印、不保存密钥。
  - **交易前风控**：单名、总敞口、beta、Reg T 上限；数据过期就停。
  - **对账和成交质量**：成交价对官方收盘价，对模型成本给出影子损益。模拟盘不计冲击和借券费，影子损益按成本模型补上。
  - **失效信号和退出规则**：按 RF1 合同第 7 节。
  - 全部先在 dry-run 下测试，不连真实下单接口。
- done_when: dry-run 端到端测试通过；向机主提交模拟盘提议时附上检查表。
- notes:
  - 2026-10-01 14:20 UTC 交互会话（Opus）写入。机主 10-01 原话："如果前向测试只是确认执行和数据没问题，那么两周就足够了，或者说这个可以直接用模拟盘测试，我多开几个模拟盘账户给你就行了"。开账户和批准具体策略都由机主做。

### T-20261002-26 组合线 v1.2：账户层（F1/F2、整股、Reg T）、安慰剂、按评判标准 v2 定档
- status: done（fde6843 代码和 identity、412ef13 结果；06:39 UTC 主审复核：逐项对过 results.json 的分档条件，final 校验和 direction-check 都 ok，hypotheses.md 无改动）。M0_U3000 到 P1，是主变体：family DSR 0.912，全项目 DSR 0.662，毛口径安慰剂 1.00，稳健性 5/6，无否决；只差 P2 的信号层 t（2.94 < 3）。M1_U3000、M1_P1000 到 P1；M0_P1000 无档（DSR 0.680）。F1 账户近期年化 9.5%，超出 BIL 5.3%，波动 5.2%，夏普 1.03；F2 超出 SPY 4.0%，IR 1.36；保证金违规 0 次。收益来源：A 窗主要是低残差波动风格（+12.7%/年），B 窗主要是低 beta 风格（+23%/年）和特质收益（+6%/年）；最坏的 63 个会话是 2021-02。净口径安慰剂原定义退化 → 评判标准 v2.0.2；复核登记为 T-20261002-29
- priority: 1
- not_before: 无（合同 `reports/research/iterations/t20261002_book_v12/hypotheses.md` 05:31 UTC 冻结，direction-check、iteration validate 均 ok）
- goal: T-25 的 R6 在 k = 1 时 SPY 对冲平均占权益 0.68–0.84、最高 1.27，总敞口约 3 倍，超过 Reg T 上限（Alpaca 文档：隔夜 2 倍，收盘不满足次日追保）。所以要回答三个问题：在 $1M 账户里，按 F1（k 0.5 加 T-bill 腿，总敞口 ≤ 1.8）和 F2（SPY 1.0 加 0.3 叠加层），在整股、引擎 $100 最小单、退市下界的约束下还剩多少；安慰剂分位多少；按诚实的试验数能不能到 P1。
- plan: Stage A 先逐位复现 R6，再跑账户层；Stage B 跑 100 个种子的日内打乱安慰剂；Stage C 用 scorecard_v2 记分（10 变体族的 DSR，并披露全项目 111 个试验）、做因子 ETF 张成和风格归因，最后定档。纯逻辑写进 `open_composer/research/equity_book/book_v12.py`，给生产端复用。
- done_when: `t20261002_book_v12/` 下的 results、report、identity、placebo、account-summary 已提交，decision-record 已更新。
- brief: reports/research/control/briefs/T-20261002-26.md

### T-20261002-29 组合线 v1.2：按评判标准 v2.0.2 复核净口径安慰剂（只作记录，不改判定）
- status: ready（定时执行轮可取，排在 T-20261002-02 之后）
- priority: 2
- not_before: 无（本机有超过 1 GB 的进程在跑时等它结束）
- goal: 原定义的净口径安慰剂每个调仓日都重新打乱，随机组合每周整本换手，净夏普 −1.9 到 −4.7，没有信息量。按 v2.0.2 的季度内固定随机名次，给 M0_U3000 和 M1_U3000 重算净、毛分位，并比较真实组合和安慰剂的换手。
- done_when: `t20261002_book_v12/placebo-persistent.json` 已提交；默认模式的结果逐位不变。
- brief: reports/research/control/briefs/T-20261002-29.md

### T-20261002-43 组合配置：最大回撤约 30%、收益优先下的引擎权重（S3、C2、v1.2 F1/F2）
- status: done（10-02 13:28 UTC 交互会话 Opus；预注册 469ae13，结果见 `reports/research/program/allocation-dd30-2026-10-02/report.md`）
  - 机械判定（预注册第 3–5 条）：W* 过第 (i)、(ii) 条，第 (iii) 条邻点偏差 6.2 点（上限 5，来自 S3 再加 0.05：83.7%、回撤 −32.1%）不过 → 用前 10 个可行点的平均：**S3 0.60、C2 0.335、F2 0.12、F1 0.025、借款 0.08**。全窗 CAGR 32.6%、最大回撤 −29.9%；对标窗 77.2%（回撤 −21.4%，超额夏普 1.89）；2026 年内 +61.9%；2022 −22.2%、2018 −14.7%。对照（S3 0.60 + 现金）对标窗 66.0%、全窗回撤 −28.3%。
  - 数据坑第 60 项（已写进 docs）：v1.2 账本按决策日索引，t 日行在 t+2 实现；第一次运行没对齐，作废；T-20261002-30 简报已加主审修正。
- priority: 1
- not_before: 无（等 T-20261002-01 换入后用总收益口径的归档算 S3）
- goal: 机主 10-02 12:45："最大回撤30吧，你来看着配，不用很严格，追求收益优先"。在 S3、C2、v1.2 F1、F2 和现金之间定权重：近期窗口（2024-01-08 起）收益最大，全历史（含 2018、2020、2022）最大回撤不超过约 -30%。先写预注册（迭代 `h20261002_program_dd30_allocation`），再算。产物：权重、前沿表、各窗口和按调仓日偏移的稳健性，组合层的模拟盘前向记账口径。
- done_when: 预注册、结果和决定记录已提交；current-view 写入结论。

### T-20261002-44 预测市场：Kalshi 隐含的宏观发布不确定性与公告日溢价（Polymarket/Kalshi 线第一步）
- status: done（8201d44、3ad6ffd、e7e6dfc 冻结、cda45a4 测试脚本、c379663 结果、63dd227 抓取修复；10-02 13:57 UTC 交互会话主审）
  - 判定（results.json 的 continue_rule，主审逐项对过）：H1 **不成立也不否定**。D = +13.93 bp（QQQ 收盘到收盘，79 个非 FOMC 发布日 2023-07-12..2026-09-17），置换 p 0.413，近期 D +26.1 bp；SPY +19.7、IWM +24.6、开盘口径 +6.4、FOMC 单独 −9.0；去掉 2025 年 D 变成 −48.1 bp（去一年范围 −48 到 +58）。打乱的 90 分位是 51 bp，79 天分辨不出 15 bp，样本不够。H2（只有 CPI，用克利夫兰联储即时预测代替一致预期）命中 0.55（20 次，门槛 0.60），不成立。登记簿新行 `parked`。
  - 主审核对过的几点：①63dd227 比结果提交晚 13 秒，但不确定性表 13:53:34 已用修好的抓取重建、结果 13:54:07 才写，8–9 月事件都在；②hypotheses.md 只在末尾追加了校验索引和结果两节，规则和数字没改；③Kalshi 2023 年以前是区间合约（38 个事件），建表只认阈值合约，所以样本从 2023-07 开始，没有 2022。
  - 前向采集脚本已审（只读公开接口、120 秒总时限、先写临时文件再改名、不覆盖），13:57 UTC 装进 crontab（每小时 23 分，第 20 行；备份在 /tmp/lead/crontab.before-pm.*）。
- priority: 1
- not_before: 无
- goal: 机主 10-02 12:45 要求用 Polymarket 等预测市场的实时赔率做模型/策略/因子并不断迭代。主审查证后定的第一个机制（不是领先-滞后，登记簿里那条仍是 evidence_too_weak）：股市在 CPI、非农、GDP 发布日的公告溢价应随发布的不确定性变大；Kalshi 前一天下午的隐含分布标准差是唯一免费的、按发布分别的时点不确定性度量（FEDS 2026-010；Ai/Bansal/Guo NBER w31923）。设计已冻结在 `reports/research/iterations/h20261002_pm_macro_uncertainty/hypotheses.md`。本任务：补齐迭代文件、建 Kalshi 数据和不确定性表、能力登记、每小时前向采集脚本（cron 由主审装），冻结后跑 H0/H1（H2 视共识数据可得性）。
- done_when: 简报验收全部满足；results.json 机械判定 continue_rule；登记簿新增一行。
- brief: reports/research/control/briefs/T-20261002-44.md

### T-20261002-45 预测市场：H1 前向影子记录、每日赔率摘要、Polymarket 观察单自动更新
- status: done（交互会话已复核：66239f9 交付影子记录、每日摘要、观察单自动更新，测试通过；2026-10-04 交互会话装上 cron：signal 19:10/20:10、realize 23:20、摘要 12:15/21:15（周一至周五），观察单周一 11:40，Kalshi 抓取+重建 18:40；观察单改写到 data/features/prediction_markets/watchlist.live.yaml，不再改仓库文件）
- priority: 2
- not_before: 无
- goal: T-44 的 H1（Kalshi 隐含发布不确定性放大公告日溢价）样本不够、判 parked，重开条件是再积累约 60 个发布日的前向 U_rel。本任务让前向证据自动、正确地积累（T−1 日 15:00–15:50 ET 窗口内按回测同一套代码算 U_rel 并只追加记录，次日补实现收益），并给机主每天一份赔率摘要（Polymarket 观察单 + 未来 10 个交易日的 Kalshi 宏观发布隐含均值和标准差），观察单每周自动换掉已结算的市场。只做研究和决策参考，不触发任何下单。
- done_when: 三个脚本和测试已提交；摘要真实跑过一次；cron 行写进报告（主审安装）。
- brief: reports/research/control/briefs/T-20261002-45.md

### T-20261002-42 下单引擎：book_paper 的撤单和清仓命令（紧急停止路径，只用假客户端）
- status: done（a7e6e39；10-02 13:03 UTC 交互会话主审。子代理 R1002-1251-T42B 从暂存补丁接着做完）
  - 已核对：提交只含范围内 3 个文件，948 行全是新增、0 行删除，`build_plan`、`submit_plan`、`RiskLimits` 和已有检查没动；新测试 19 个，`tests/test_book_paper*.py tests/test_book_v12_targets.py` 共 129 个通过。
  - 读过的逻辑：`cancel` 只碰 `bk1-` 开头的单（`bk1-flat-` 也算），默认只撤当天计划里的 id，`--all-book` 撤全部本书单，其他单原样列在回执里；撤单不受 kill switch 限制；回执写重读后仍未成交的单。`flatten` 默认只演练，确认后才发；有未成交单就拒绝；先卖多头再买回空头；不可交易的持仓跳过并列出；订单号 `bk1-flat-` + sha256 前 36 位（共 45 字符，Alpaca 上限 48），被撤后重发要 `--attempt 2`。
  - 真实撤单测试（quant1，模拟盘）：手工挂 1 股远离市价的 `bk1-` 限价单，然后 `uv run oc book-paper cancel --account quant1 --all-book --reason "live cancel test"`，回执应为 n_requested=1、n_open_after=0。默认范围（不带 --all-book）只认当天计划文件里的 id，所以手工单要用 --all-book。挂单需要一个小脚本，交互会话在开盘时段做。
  - 10-02 13:19 UTC 真实撤单测试通过（机主 12:45 授权）：quant1 挂 1 股 SPY 买入限价 $100（bk1-livecanceltest-20261002T131900，13:19:00 提交，状态 pending_new→new），13:19:12 `cancel --all-book` 撤掉；券商 CANCELED、filled 0；回执 `reports/paper/book/quant1/orders/cancel-2026-10-02-131912.json`（不入库）requested=1、errors=0、open_after=0、untouched 0。
- priority: 1
- not_before: 无
- goal: 合同第 6 节要求首单前测过开关和撤单，第 7 节的停止规则也要有办法真正停下来。`oc book-paper` 目前没有撤单，也没有清仓。新增两个命令：`cancel` 只撤本书（`bk1-`）当天的未成交单，撤单不受 kill switch 限制；`flatten` 默认只演练、需要显式确认，按收盘竞价或盘中市价整股平掉全部持仓，跳过不可交易的持仓，有未成交单时拒绝。quant1 上的真实撤单测试在机主对检查表点头后由主审做，不在本任务内。
- done_when: 两个命令和测试（至少 10 个）已提交，旧测试原样通过；报告给出真实撤单测试要用的命令。
- brief: reports/research/control/briefs/T-20261002-42.md

### T-20261002-40 下单引擎：持仓里停牌、退市、被收购的股票不再卡住整份计划（frozen 持仓）
- status: done（ab303e5；10-02 08:14 UTC 交互会话主审）
  - 已核对：
    - 提交只含范围内 6 个文件。
    - `RiskLimits` 只新增 `max_frozen_gross = 0.02`，已有的值没改。
    - 测试从 92 个增加到 110 个（新增 18 个），全部通过。
  - 主变体回放（`engine-replay.json`）：
    - 被卡天数：quant1、quant2 都从 18 天降到 0。
    - frozen 事件 22 和 21 次，frozen 敞口最大为权益的 0.384% 和 0.197%（上限 2%）。
    - 整笔平仓各 1 次：ARTL，2026-07-07。它当天其实有收盘价，只是不在生成器的参考价里，T-28 的说法已更正。
    - 其他三个变体也是 0 天被卡，只有 M1_P1000 的 quant1 有 1 天 beta 超限，以前就有。
    - 生成器丢掉的目标权重（当天没有收盘价的股票），每天 |权重| 之和：
      - quant1 中位数 0.018%、最大 0.19%；
      - quant2 中位数 0.0096%、最大 0.10%；
      - 可忽略。
  - 假设和遗留：
    - 回放假设券商在冻结满 2 个会话后转成现金，真实时间未知；模拟盘开始后用实际收购事件核对。
    - 2% 上限没有拿成批收购做过压力测试。
    - 计划里只在有冻结股票时才出现 `frozen` 字段和 `frozen_positions` 检查，这样没有冻结时计划哈希不变，符合简报。
    - 子代理的临时目录 `/tmp/T-20261002-40`（792K）因为 `rm -rf` 被禁止没删掉，磁盘守护 7 天后清理。
  - 复核时顺手修了一处：ruff 排除 `reports/research/intel/sources/`（保存的第三方证据脚本）。原先 `ruff check .` 在那里报 133 个错，`make verify` 走不到测试那一步。
- priority: 1
- not_before: 无
- goal: T-28 回放里，主变体 60 个会话有 18 个被 `reference_prices_complete` 卡住，两个账户都是。原因是持仓里有 23 次"当天没有收盘价"的情况，其中 22 次是股票已停止交易（现金收购、合并、退市），1 次（ARTL）是某天缺价后来又交易。引擎只要有一个持仓没有参考价就整份拒绝，所以生产上每次收购都会卡 1 天或更多。改法：`AccountState` 带上券商的持仓现价；持仓里不可交易的股票记为 frozen，不下单，按券商现价计入杠杆，不进股票层检查；新增检查 `frozen_positions`，frozen 总敞口不超过权益的 2%；可交易但缺参考价、目标权重为 0 的持仓按券商现价整笔平仓；目标里有权重却缺价的照旧拒绝。回放改成带价格和可交易标记的假状态后重跑。
- done_when: 旧测试原样通过，新测试通过；主变体重跑回放 0 天被卡，或每个被卡的日子都有解释；没有放宽任何已有限额；已提交。
- brief: reports/research/control/briefs/T-20261002-40.md

### T-20261002-41 下单引擎：收盘后对账用的价格文件（官方收盘价 + 15:45 快照）
- status: done（07bac39；10-02 08:00 UTC 交互会话主审）
  - 已核对：
    - 13 个测试复跑通过。
    - 提交只含 3 个范围内文件。
    - 分钟线按起始时间标注，取 15:44 那根的收盘；缺的话回退到 15:34–15:43 的最近一根，并记下来。
    - 归档是全复权的。当天晚上生成时，复权收盘价等于 D 日原始成交价，文件里记 `price_basis`。
    - 输出在 `reports/paper/book/prices/<D>.json`，被 `reports/*` 忽略。
  - 试跑（2026-09-17）：
    - 1729 只股票，收盘价全有。
    - 快照 1727 只，其中 73 只用了回退；缺 2 只（FGI、UFPT，那 10 分钟没有成交）。
    - 快照到收盘的价差中位数 22 bp，p90 66 bp。
  - 子代理自报的失误，按代码核对属实：
    - 第一次跑测试时误调了真的 `oc book-paper reconcile`。它读到 `reports/paper/book/quant1/plans/2026-09-18.json`（之前 dry-run 留下的），哈希不符，失败在建券商客户端之前，没有读凭据、没有调接口。
    - 已改为调用时再解析 runner。
    - 生产目录里那两份旧 dry-run 文件（quant1 的 09-17 目标、09-18 计划）保留，不是本任务的。
  - 遗留：
    - 半日市（2026-11-27、12-24）没有 15:45 那根分钟线，快照会全缺。11-27 之前要补：按交易所日历，取提前收盘前 15 分钟。
    - 对账定时任务的建议：工作日 22:45 UTC，23:30 重试。列入模拟盘开始的检查清单，等机主批准。
- priority: 1
- not_before: 无
- goal: `oc book-paper` 的收盘后对账要一个 `--prices-file`，内容是 `{"official_close": …, "snapshot_1545": …}`，目前没有生成它的脚本（T-28 报告）。第一笔模拟单之前必须有，否则成交质量和影子成本算不出来。收盘后从 SIP 数据取：官方收盘价用日线，15:45 快照用分钟线（只用于事后成交分析，不需要实时）。
- done_when: 生成脚本、测试和对账驱动接入已提交；用一个历史执行日对计划里的全部股票试跑，缺价的个数和原因写进报告。
- brief: reports/research/control/briefs/T-20261002-41.md

### T-20261002-28 组合线 v1.2：生产端目标生成器、引擎历史回放、每日驱动（不下单、不装定时任务）
- status: done（6014b82；10-02 07:36 UTC 交互会话主审）
  - 已核对：
    - `engine-replay.json` 与报告一致；115 个测试通过。
    - 逐位一致：M0_U3000 在 2025-04-10、2026-03-18、2026-09-10 三天、两种形式都一致，另加 M1_P1000 的一天。
  - 主变体回放（60 个会话）：
    - 唯一失败的检查是 `reference_prices_complete`，两个账户各 18 天，都是持仓里的股票停止交易（22 次）或某天缺价（ARTL，1 次）。
    - |beta| 最大值：quant1 0.037、quant2 0.020（上限 0.05）；没有一天超过 0.04。
    - 杠杆最大值：1.82 和 1.80（上限 1.98）。
    - 每天订单数中位数：quant1 165.5、quant2 77；p95 分别是 716、432，高峰在月度刷新那一周。
    - 每天低于 $100、被舍弃的订单中位数约 690 笔，合同模拟同样有这个限制。
  - 遗留问题：
    - 引擎卡单 → T-20261002-40。
    - 对账价格文件 → T-20261002-41。
    - M1_P1000 有一天 beta 0.0516 超限，原因是对冲按固定股数持有，市场一动就漂移；主变体余量够，先记录不改。
    - 生成器丢掉了当天没收盘价的目标股票（40/60 天有，每天最多 4 只），合同模拟器则继续持有；影响待 T-30 回放一并量化。
  - 下一步：
    - T-22 的 live 目录建好后，连续 2 个会话 dry-run；
    - 拟议的定时任务（不安装）：目标 23:15 UTC，计划 18:30 UTC，提交 18:45 UTC（要机主批准），对账在 21:30 UTC 以后；11-01 夏令时结束后，18:xx 的两条改为 19:xx。
- priority: 1
- not_before: git log 里有 T-20261002-26 的代码提交（含 `open_composer/research/equity_book/book_v12.py` 和通过的 identity.json）
- goal: 模拟盘的第 3 个前置条件是生产端目标与合同账户目标逐位一致，本任务实现它，另做 60 个会话的引擎检查回放和每日驱动，为"连续 2 个会话 dry-run 全绿"做准备。生成器是无状态的：每天从数据重算 5 档，与 T-26 的模拟器状态一致。
- done_when: 3 个历史日期 × 2 种形式逐位一致；engine-replay.json 里每个失败的检查都有解释；驱动在没有环境变量时拒绝 --submit；已提交。
- brief: reports/research/control/briefs/T-20261002-28.md

### T-20261002-27 下单引擎：对冲腿和可变 T-bill 腿（v1.2 的 F1/F2 形式，只 dry-run）
- status: done（9eed9d4，05:39 UTC；05:40 主审复核：75 个测试通过（原 57 + 新 18）；v1 目标的哈希不变，因为 v1 载荷里不含新字段；beta 检查 = 股票 beta + 1.0 × 实际对冲权重；F1/F2 v2 的 dry-run 13 项检查全过）。下一步：生产端目标生成器 T-20261002-28，等 T-26 的 book_v12 模块提交后开始
- priority: 1
- not_before: 无
- goal: T-16 引擎要求核心腿权重恰好为 1.0，并把 SPY 当股票检查净敞口、单名上限和 beta，表达不了 v1.2 的两种形式：F1 是股票、SPY 对冲加可变 T-bill；F2 是 SPY 1.0 加并入的对冲。本任务把引擎扩成 BookTarget v2：向后兼容，v1 哈希不变，检查分层。生产端目标生成器之后另立任务，复用 T-26 的模块。
- done_when: 新旧测试全部通过，F1/F2 v2 dry-run 检查表全绿，已提交。
- brief: reports/research/control/briefs/T-20261002-27.md

### T-20261002-25 组合线：总收益多空的现实化阶梯（有没有简单构造的书）
- status: done（8113bb7 预注册、2959d68 结果；05:20 UTC 主审已复核）。R6 近期净夏普复算为 1.506 / 0.966 / 1.389 / 1.104，与报告一致。主审另外发现两点：R6 在 k = 1 时需要 0.68–0.84 倍（最高 1.27 倍）的多头 SPY 对冲，总敞口约 3 倍，超过 Reg T，所以要有账户层；因子 ETF 只能解释 57–63% 的日波动，U3000 的剩余 α 每年 9–11%（t 约 2.1）。按规则写 v1.2 合同 → T-20261002-26/27
- priority: 1
- not_before: 无
- goal: 残差 α 弱（T-24、残差 IC 核对），优化器传导系数只有 0.4–0.5（T-19）。信号层总收益多空在 2024–26 毛夏普 1.68，但它是每日调仓、开盘成交、做空不受限、8 bp 成本，而且 Stage 0 发现 252 日 beta 对冲会失效。所以要逐级加上现实约束：周频、收盘、只做易借券、真实价差和借券、组合层 beta 中性、VIX 风控。看看还剩多少，决定 v1.2 简单构造合同值不值得写。
- plan: 预注册 R0–R6 和决策规则：R6 近期净夏普 ≥ 0.90，beta 在 ±0.15 之内，V4 不否决，z ≥ −2。R0 必须和大盘阶段分析对齐到 1e-9。只在本机向量化计算，不跑优化器，不用 Modal。
- done_when: `reports/research/program/realism-ladder-2026-10-02/` 下的 prereg、results、report 已提交。
- brief: reports/research/control/briefs/T-20261002-25.md

### T-20261002-24 组合线：现有候选信号的残差 IC 批量筛选（v1.1 的输入）
- status: done（65b4d93 预注册、e218e62 结果；04:30 UTC 主审已读）。4 个候选都没入选。ml_pv、低 MAX、接近 52 周新高在压力期的残差 IC t 为 2.9–5.7，2024–26 降到 0.5–1.8；增量 t 都低于 0.8。Alpha158 FDR 合成两窗都约等于 0。REG 仓库里没有实现，未测
- priority: 1
- not_before: 无
- goal: T-19 和残差 IC 核对都说明瓶颈在信号。一次性筛选磁盘上已有的候选：T-19 模型预测 ml_pv、Alpha158 过 FDR 的合成、低 MAX、接近 52 周新高，以及仓库里已有实现的收益-盈余缺口反转。机制和 formation_ic 完全相同。
- plan: 预注册候选和入选规则：Bonferroni t、压力期同号、与 M1 相关 < 0.5、增量残差 IC t ≥ 2、安慰剂。先复算一个已有主题，和 formation_ic 对齐到 1e-9；不跑回测。
- done_when: `reports/research/program/signal-screen-2026-10-02/` 下的 prereg、results、report 已提交。
- brief: reports/research/control/briefs/T-20261002-24.md

### T-20261001-23 组合线 v1.1 合同：按 T-19 诊断和评判标准 v2 预注册
- status: cancelled（04:30 UTC：按停止规则，T-24 没有信号入选，v1.1 不写。转 T-20261002-25 检验'简单构造'这条路）
- priority: 1
- not_before: T-20261001-19 以 done 开头
- goal: 把组合线推到模拟孵化档。用 T-19 的 D1–D3 和 19:07 主审轮的残差 IC 上限（`residual-ic-summary.json`）决定两件事：构造（风格预算还是风格中性）、合成器（M1 型事前 IC 加权）。按评判标准 v2 写分档条件，并把 DSR 档位按试验数换算成所需夏普。
- plan:
  - 去掉风格上限的构造，要按总收益 IC 和 T-19 的收益归因论证上限；保留风格中性的构造，按残差 IC 论证。
  - 新的 direction-review，direction-check、iteration validate 都通过；预注册早于任何 v1.1 数字。
  - 安慰剂按 v2 必需。
  - 前向记录沿用 RF1 附录 1 的拼接口径（07-01 起）。
- done_when: `reports/research/iterations/t20261001_book_v1_1/` 通过两道检查并提交，执行简报写好。

### T-20261001-20 评判标准 v2 的计分代码（scorecard），并对 v1 做参考核算
- status: done（bf6dbaf，子代理 R1002-0400-T20；04:06 UTC 主审已核对。v1 参考计分：6 个变体都是 none。M1_C 的 DSR 0.682，稳健性 5；M0_A、M0_C、M1_C 触发 V4：压力期 63 个会话亏损 4.1–4.4σ，即崩溃尾部。z 检验的缺陷已修，标准升到 v2.0.1）
- priority: 1
- not_before: 无
- goal: 机主 10-01 要求整体判断、加权考量，标准由研究者定。标准见 `docs/evaluation-standard.zh.md`，阈值在 `config/evaluation-standard-v2.json`。以后每次判定都由代码输出计分 JSON，不靠手算。v1.1 合同直接用它。
- done_when: `open_composer/research/scorecard_v2.py`、测试、v1 参考计分（`reports/research/program/evaluation-standard-2026-10-01/v1-reference-scorecard.json`）已提交。
- brief: reports/research/control/briefs/T-20261001-20.md

### T-20261001-19 组合线 v1 事后诊断：构造阶梯（风格上限、开盘成交、成本）、传导系数、收益归因
- status: done（10-02 03:53 UTC 子代理提交 80a82a6；04:00 UTC 主审已读）。D1 假：去掉风格上限，A 窗毛夏普只多 0.01–0.02。D2 总体假：M0_A 改开盘口径后变好，来自优化器看到更高成本、交易更少。D3 只对 M0_A 成立（成本拖累 0.36）。A 窗收益主要来自风格溢价（低残差波动、动量）；个股部分 A 窗 +0.5–2.2%/年，B 窗为负。结论：瓶颈在信号，不在构造 → T-20261002-24
- priority: 1
- not_before: 无
- goal: v1、RF1 都在组合层失败，信号层是好的（M0 信号层 A 窗毛 1.68、B 窗 3.06；组合 M0_A 收盘 A 窗毛 1.10、B 窗 −0.80）。量化损失在哪里，作为 v1.1 合同的依据：风格上限一直顶格（M0_A 投资 85%、动量 45%、价值 37% 的调仓顶到 0.25），收盘比开盘差（对标窗毛 0.876 对 1.155），成本每年 172 bp。
- plan: 先检索原文（Lee-Stefek 2008、Ceria-Saxena-Stubbs 2012、Clarke-de Silva-Thorley 2002、开盘竞价成本、Alpaca opg/cls），在任何新数字之前写预注册和决策规则 D1–D3；L1 去掉风格上限、L2c 开盘按开盘成本、L2a 开盘按收盘成本，各 M0_A、M1_C × 5 个偏移，共 30 条 Modal 路径（≤ $2）；传导系数和按风险模型的收益归因。
- done_when: `reports/research/iterations/t20261001_book_v1/postmortem/` 下 prereg、results、report、run-manifest 已提交，D1–D3 机械给出；"v1.1 设计由主审决定"。
- brief: reports/research/control/briefs/T-20261001-19.md
- notes:
  - 新增试验 6 个（3 种构造 × 2 个变体），以后 DSR 的试验数累计 89。

### T-20261001-13 组合线 Stage 2a 评估：45 条路径的全部指标和机械条件（接 T-20261001-08）
- status: done（17:44 子代理提交 dc8b756；17:55 UTC 主审已判定：6 个变体都没过冻结门槛，`mechanical_status = no_variant_reaches_cond1_or_anchor_1_19`，v1 停止，见 `decision-record.md`）
- priority: 1
- not_before: T-20261001-08 的状态以 done 开头
- goal: 把 T-08 的原始结果算成预注册第 5、7 节和修正案 A1 要求的全部数字，机械给出每个变体的条件真假，以及哪些变体要做安慰剂。判定由主审做。
- plan: 见简报。用 `evaluate.py` 的现成函数：K1、K2 两种口径都按 5 个偏移的中位数判；另报 Dimson beta、失败率、成本分项、DSR、T-11 分阶段表现、成交时点对比、去掉一个主题的诊断。
- done_when: `reports/research/iterations/t20261001_book_v1/results.json` 和 `report.md` 已提交，含 `checks`、`placebo_needed`、`mechanical_status`；不写结论，标"待主审"。
- brief: reports/research/control/briefs/T-20261001-13.md
- notes:
  - 2026-10-01 13:29 UTC 13:07 主审轮（Opus）写入。

### T-20261001-14 组合线 Stage 2a 安慰剂：需要的变体各 100 个种子，净、毛两种口径（接 T-20261001-13）
- status: cancelled（17:55 UTC：T-13 的 `mechanical_status` 为 `no_variant_reaches_cond1_or_anchor_1_19`，按本任务前置条件取消）
- lead_note: 17:44 UTC 交互会话：T-08 实测每条路径 Modal 墙钟中位 8.2 分钟、最长 11.5 分钟（meta 的 timing_s），预算检查和函数 `timeout=` 改用 20 分钟（简报写的 60 分钟会把最坏情况估成三倍，月度 $25 上限下第二个变体就会被拦）。RF1 需要的额外安慰剂由 T-15 自己跑，不并入本任务。
- priority: 1
- not_before: T-20261001-13 的状态以 done 开头，且 `results.json` 的 `mechanical_status` 为 `pending_placebo`；为 `no_variant_reaches_cond1_or_anchor_1_19` 时本任务取消，由主审改状态
- goal: 预注册第 6 节加 A1 第 6 节：每个调仓日内打乱合成分，真实书要在净夏普和毛夏普两种口径上都打赢安慰剂（全样本 ≥ 0.95、两窗各 ≥ 0.80；watch_recent 只看对标窗 ≥ 0.80）。research_pass 和 watch_recent 都离不开这一步。
- plan: 见简报。用 Modal，每个变体 100 个分片。Stage 2 的 Modal 累计超过 $7 时停在变体之间，留 $3 给 Stage 2b。
- done_when: `results.json` 每个需要的变体都有 `placebo` 块和两个 mechanical 字段，`mechanical_status` 为 `placebo_done`；标"待主审"。
- brief: reports/research/control/briefs/T-20261001-14.md
- notes:
  - 2026-10-01 13:29 UTC 13:07 主审轮（Opus）写入。

### T-20261001-21 组合线数据：上游特征表增量刷新到最近交易日，并做时点不变性检验
- status: done（已主审 2026-10-02 01:26 UTC：执行正确，交付物齐全；价格类表不过检验的根因是 SIP 归档的复权接缝，不是构建脚本前视，也不按子代理提的两个选项处理；修归档转 T-20261002-01，特征重建转 T-20261002-02）
- priority: 1
- not_before: 无。本任务不改代码，研究快照只读。每个重步骤开始前先确认别的会话没有在跑重任务（简报第 0 步）
- brief: reports/research/control/briefs/T-20261001-21.md
- goal: 特征库停在 09-16/17（新闻停在 09-09），SIP 日线已到 09-30。RF1 的真正样本外影子从 09-18 起算，D6 前向影子和下单引擎（T-16）要求目标日是上一交易日，所以不刷新就没有任何前向证据。顺带检验构建脚本的时点正确性：多给数据重建后，09-17 以前的行必须一条不变。
- plan: 先做清单（每张表的增量采集和只建 2026 的命令，参数照抄构建清单），再备份，然后按依赖顺序逐个采集、重建；新写 `scripts/check_feature_invariance.py`，对比 cut 之前的行；检验不过就恢复备份，标 `restated`，交主审决定。全程算研究快照的哈希守护。
- done_when: `reports/research/program/data-refresh-2026-10-01/{inventory.json,invariance.json,freshness.json,report.md}` 已提交；每张表要么通过检验并刷新到 D，要么已恢复备份、写明原因；结果标"待主审"。
- notes:
  - 2026-10-01 19:25 UTC 19:07 主审轮（Opus）写入。按纲领"两周优先级第 2"和 13:07 主审轮的安排写简报。设计上的取舍：`data/features` 是只追加的时点特征库，原地追加，由备份和不变性检验把关；被 A1 哈希绑定的研究快照 `data/research/equity_book/` 不动，组合层另建 live 目录，交给 T-20261001-22 做（current-view 17:55："研究快照保持冻结，实盘数据另放一个目录"）。交互会话要自己做，就先把本任务标 `running（交互会话）`。
  - 2026-10-01 执行轮（sonnet-high 子代理 a3b1bab75c10cda65，112 次调用，模型核对 claude-sonnet-5-5）：D=2026-10-01，提交 4c9fa1e。通过并已原地换入：insider_broad（至 10-01，changed 0）、short_volume_broad（至 10-02 次日行，changed 0）、news_attention（至 10-01，changed 0）、窄 universe 2026 分区（0.054%）。未过 max_changed_share ≤0.001（候选在 data/features/_t21_tmp/，未换入，原文件未动）：universe_broad 1.106%（FGC 新增 2 键）、daily_broad 1.677%、daily 窄 1.701%（子代理称 09-15..09-17 三个交易日的收盘变了，疑似归档按新复权口径刷新，BBY 09-14 收盘 93.85 vs 94.83，推断未核实）、alpha101_broad 4.12%、alpha191_broad 0.66%、SEC facts（值未变但旧键 17 个消失，已从备份恢复，sha 核对一致）。跳过（依赖未换入的日线表）：sec_fundamentals_daily、nsi、short_interest（原始 FINRA 已采至 09-15 结算，特征表未重建）。研究快照 2511 文件前后哈希一致（snapshot_sha_before/after 已 cmp 核对）。8 个测试和 ruff 通过。产物：reports/research/program/data-refresh-2026-10-01/{report.md,inventory.json,invariance.json,freshness.json}、scripts/check_feature_invariance.py、tests/test_check_feature_invariance.py；备份 data/live/backup-20261001/。待主审决定：最后 3 个交易日边界怎么处理（只追加切点之后的新行 / 门槛忽略末 3 日）；决定前换入价格类表会违反冻结门槛，我没有改。决定后依次：把 _t21_tmp 候选换入 → sec_fundamentals_daily → nsi → short_interest。待主审。
  - 2026-10-02 01:26 UTC 01:07 主审轮（Opus）审核：
    - **核对**：
      - 原始 JSON：daily_broad 只有 09-15..09-17 三天的行变了，close 变了 142 行、69 只股票，新旧比值全部 < 1，中位 0.9947（FRO 0.9376、WHF 0.966、DX 0.986、UHT 0.981，都是在 09-15..09-22 除息的高股息股）。beta、idio_vol 和 `_rel` 列跟着 SPY 和截面一起变。
      - 根因读代码确认：`fetch_sip_universe._fetch_batch` 用 `adjustment="all"`；`update_sip_archive.py` 每晚只重抓最后 `REFETCH_LOOKBACK_SESSIONS = 2` 个交易日，以新行为准。供应商在除息或拆股后会给**全部**历史乘复权因子，我们只覆盖了最后 3 天。生效日前 2 天出现接缝，再往前的行仍是旧基准。
    - **接缝**：
      - 增量更新从 09-04 首次运行。归档里"整数拆股比例且成交额连续"的跳变 1–8 月每月 1–9 次，9 月 22 次。
      - APH（P1000）08-27 收盘比 0.500124，是一次没复权的 2:1 拆股。VRME、KUST、ZCSH、UNX、TANH 也是。
      - 分红接缝把分红漏出总收益，并把跳变提前两天。
    - **对研究结论的影响**：A 窗（到 06-30）干净。研究面板里接缝期内宇宙中的接缝只有 APH 一次。v1 的 54 条路径在 07-25..08-26 都没有持有 APH（targets.parquet 核对），接缝当天盈亏影响为 0，**v1 和 RF1 的否定不变**。T-19 的 30 条路径同样止于 09-16，没有逐条核对，留给交互会话。
    - **对前向的影响**：前向数据和四条 ETF 模拟盘都读这个归档（`rotation_target_weights.py` 第 455 行）。26 个模拟盘标的目前只有分红接缝、没有拆股接缝，风险是前瞻性的。
    - **主审决定**：
      1. 子代理提的两个选项（只追加切点之后的行 / 门槛忽略末 3 日）都不采用。复权价格水平不能只追加：新旧基准在拼接处会再出一个接缝。
      2. 先修归档（T-20261002-01）：发现某只股票被改了基准，就重抓它 2016 年至今的全部历史。只修当年会把接缝挪到 2025/2026 年交界。
      3. 特征库的价格类表当作归档的派生缓存，从修好的归档重建。不可变的时点记录是信号和目标日志（D6），不是特征表。不变性检验改成两区：
         - 严格区（≤ 2026-08-21）：收益类列必须逐位不变；
         - 之后的日期和价格水平类列只做诊断，按重述记录归因。
         - 这条只改数据质量检验的口径，原因是检验的前提被证据推翻，没有放宽任何研究门槛。
      4. 事件类表（insider、short_volume、news）已按原规则通过并换入，保留。
    - `_t21_tmp` 的候选是从有接缝的归档建的，作废，不要换入；由 T-20261002-02 按新口径重建。

### T-20261001-22 组合线数据：live 目录（组合层逐行对齐研究快照）、风险模型跨年修复、每日驱动脚本
- status: done（交互会话主审 2026-10-04 16:19 UTC：驱动实跑退出码 0（15:00–16:12，72 分钟，八张上游表闸门全过，全部 fresh）；10-02 目标已生成（quant1 F1 1784 名、净 beta 约 0；quant2 F2 SPY+±25% 叠加）。VIX 文件过期导致第一次生成被拒，已加 `scripts/fetch_vix_live.py`（FRED+CBOE 同晚收盘，重叠 9285/9285 一致）并接入 cron。窄口径 universe 2016–2025 被驱动的符号链接暂存写穿，已从 Drive 的 T-21 副本恢复（改动比例 ≤5.4e-4，组合层不用）。提交 6ff8bbd、07e010c、01ac021）
- priority: 1
- not_before: T-20261002-02 以 done 开头（10-02 01:07 主审轮加：T-21 虽已 done，但价格类表要等归档修好、按新口径重建后才能用）；T-20261001-21 以 done 开头（或 partial，但组合用到的表全部通过不变性检验）；T-20261001-19 以 done 或 cancelled 开头；没有 `running（交互会话）` 的任务在改 `panel.py`、`risk.py`、`build_equity_book_panel.py`（简报第 0 步）
- brief: reports/research/control/briefs/T-20261001-22.md
- goal: 给 D6 前向影子和 quant1/quant2 的模拟盘目标提供每天更新的组合层数据，保证和研究口径逐行一致；同时修好 `RiskModel.resolve()` 的跨年缺陷（v1 中 190 次最终失败里占 189 次；不修的话，2027 年 1 月实盘也会撞上）。
- plan: 两处小改动加测试：`OC_EQUITY_BOOK_DIR` 目录覆盖，不设时目录常量不变；`resolve()` 回看上一年。然后用 `cp` 建 live 目录，重建 2026 年的面板、信号、风险和主题分，和研究快照对比 09-17 以前的行，研究快照前后算两次 sha256。最后写每日驱动脚本，只给出建议的 crontab 行，不安装。
- done_when: `live-parity.json` 各阶段全部通过，研究快照哈希前后一致，测试通过，驱动的 `--dry-run` 能打印计划，已提交；结果标"待主审"。
- notes:
  - 2026-10-01 19:25 UTC 19:07 主审轮（Opus）写入。改动的组合层模块归交互会话管，所以前置条件要求 T-19 先结束，而且没有交互会话在改这几个文件。v1.1 的设计如果已经包含这次修复，交互会话可以把本任务标 cancelled 并注明。
  - 2026-10-02 01:26 UTC 01:07 主审轮（Opus）：SIP 归档有复权接缝，见 T-20261001-21 的审核。简报末尾加了"主审修正 10-02"一节：
    - 一致性核对改成两区口径：严格区 ≤ 2026-08-21 的收益类列逐位一致；其余只做诊断，按 `_restatements.jsonl` 归因。
    - 每日驱动整年重建当年分区，不再只追加；被改成拆股基准的 symbol 触发往年 daily_broad 分区重建。
    - 前置加了 T-20261002-02。
  - 2026-10-02 07:32 UTC 07:07 主审轮（Opus）：简报末尾加了"主审修正 10-02 第二次"。供应商价格取整到分，严格区改用两种判据：原始收益列用价格感知容差 0.04/close；信号、暴露、主题分用逐日秩相关 ≥ 0.999。每日驱动先对照 T-28 的 `scripts/run_book_v12_daily.py`，不重复实现，冲突就标 blocked。

  - 2026-10-04 09:39 UTC 交互会话主审（Opus）审 R1004-T22 汇报（65f1c36，partial）：
    - **live 目录接受**。逐行对齐不过，但差异全部可归因：复权价重定基（被重述的 symbol）、快照自身的回退市值年内前视（新登记数据坑 #63）、09-17 后的迟到申报（#62 机制）。
    - 组合层核对：5 个日期（06-30..09-17）F1/F2 目标权重相关 0.9969–0.9992，单边差 0.2–2.7% 净值，快照自身一周变化 3.4–13.8%；按事先定的规则判 clean（`live-book-parity.json`，25afd7f）。
    - EL/APLD/CALM/GURE 按 #62 接受，#62 扩大到所有季度梯派生列；#62/#63 对回测的影响交 T-20261004-54。
    - `test_stage0_ls_raw_mom_12_1_p1000_parity` 标 xfail：T-22 改动不碰它读的路径（backtest.py 不导入 risk，panel 默认目录不设环境变量时不变），失败来自 T-02 换入的 daily_broad。
    - **驱动 09:34 实跑失败**：universe 从头重建，和 T-02 的合成文件比变化 68%，备份已恢复；复权重述游标缺失，首跑会把 7326 条历史记录全当新的。已让 R1004-T22 改成月表只追加、加 `--init-cursor`、清暂存目录，然后实跑到退出码 0。
    - 10-02 的目标等驱动实跑完、insider 和 news 补到 10-02 后再生成（目标文件只写一次）。

### T-20261002-01 数据：修 SIP 日线归档的复权接缝，并一次性修复（拆股假收益、分红漏出总收益）
- status: done（b766faf；10-02 13:22 UTC 交互会话主审）
  - 已核对 archive-repair.json：前置 sha256 3741 个文件全一致（没重跑修复）；v1p_unexplained_symbols 0（上限 69）；v1p_factor_revision_symbols 53（55 行，上限 695）；bar_correction 6 行、date_set 1 行；v2p_unexplained 0；v4p_identical_before_window true；verify_v2_pass true；swap_done true，swap_utc 2026-10-02T13:19:55Z（不在禁用时段）。换入方式：先拷到 `data/sip/daily.staging-r1253` 校验 sha256，再两次 mv，避免目录空窗。V3 复查：APH 收盘比 1.00025，9 月接缝 6 个（1–8 月最多 9）。提交只含 5 个范围内文件；测试 40 个通过。
  - 待留意（不影响验收）：验证器报告修复后的归档相对旧归档少 1100 个、多 1475 个（symbol, 日期）行，子代理没拆分；V1′ 里只归出 1 条 date_set。T-02 的两区不变性检验会覆盖这类差异，T-02 报告里要写这两个数的来源。
  - 旧归档在 `data/live/backup-sip-daily-preswap-20261002`（553 MB），T-02 关闭前不清理。
- priority: 1
- not_before: 无（不在 20:30–01:00 UTC 验证或换入）
- brief: reports/research/control/briefs/T-20261002-01.md
- goal: 归档的不变式改为"每只股票的全部年份都等于供应商当前给出的复权历史"。否则：
  - 前向影子、组合模拟盘和四条 ETF 模拟盘读到的价格，每次拆股都有假的 −50%/+900% 收益（APH 08-27 ×0.500）；
  - 每次除息都把分红漏出总收益，并把跳变提前两天。
- plan:
  - `update_sip_archive.py` 加重述检测：尾部重叠行和库里不同，就重抓这只股票 2016 年至今的全部历史，改写各年份的行，记 `_restatements.jsonl`。
  - 加 `--repair-full-window` 一次性修复，先整体备份归档。
  - 新写接缝检测和修复验证脚本。V1–V4 见简报：收益除接缝区外逐位不变、跨年不变、接缝消失、没被替换的不受影响。
- done_when: `archive-repair.json` 的 V1–V4 满足简报的验收标准，测试通过，已提交；结果标"待主审"。
- notes:
  - 2026-10-02 01:26 UTC 01:07 主审轮（Opus）写入。根因和证据见 T-20261001-21 的审核。
  - 只修当年是错的，会在 2025/2026 交界造出新接缝；简报已写死全历史重抓。
  - 修复会改变四条 ETF 模拟盘下一次运行读到的历史价格水平（改成总收益口径，和它们回测时用的一致），规则不变。
  - 2026-10-02 05:41 UTC 执行轮（Sonnet 5.5，子代理 a84014510d059df67，待主审）：代码+测试已提交 874a52a（29 测试过、ruff 过；检测/全历史改写/25 分钟预算+pending/--repair-full-window/分钟只检测；新增 check_sip_seams.py、verify_sip_repair.py）。修复跑了 29 分钟、949 次 API，6952 个 symbol 被判重述（whole-year 比较 rtol 1e-6，4535 个 >1e-3，1405 个 >1e-2），改写 49906 个 symbol-年。V3 过：APH 08-27 收盘比 0.5001→1.0002，9 月接缝 22→6（1–8 月最大 9），VRME/KUST/ZCSH/UNX/TANH 不再列出。**V1 不过**（11,513,316 条违反；简报容差按 4 位小数写，实测供应商价格是 2 位小数，如 AAA 22.63→22.55；按 0.02/价格容差放宽后约 2500 个 symbol 仍有 188 条违反，疑似供应商改历史/代码复用如 NIVF）；**V2 不过**（6188，严格 1e-6 为 7779）；**V4 不过**（200 个未替换里 116 个不同；抽查 20 个只是 2026-10-01 末行的 volume/trade_count 被更正）。按简报恢复：data/sip/daily 已从 data/live/backup-sip-daily-20261002 恢复，sha256 0 不一致；修复后的树留在 data/live/failed-sip-daily-20261002（含 _restatements.jsonl）。因此归档目前仍是修复前状态，**今晚 22:00 定时任务会用新代码跑在未修复归档上**（检测到重述的 symbol 按 25 分钟预算改写，其余入 pending）。模拟盘标的 63/252 日收益变化（百分点）：SHY +0.60/+0.59、QQQ +0.11/+0.13、SPY +0.25/+0.29、GLD、SMH 0。夜间成本估算 0.86 分钟/平均夜，峰值周（1175 symbol）4.1 分钟，均 <25。未测：按"含取整容差"的完整 V1 全量；超 90 分钟上限约 3 分钟（验证器 OOM 一次需拆分）。主审要定：V1 容差口径（价格取整）、V4 是否排除最后一个会话，然后用 --repair-full-window 重做（约 35 分钟，不在 20:30–01:00 UTC）。产物：reports/research/program/data-refresh-2026-10-01/{archive-repair.json,seams-before.json,seams-after.json,sip-daily-backup-sha256.json,report.md}。data/live 下现有 3 份归档副本，磁盘剩 9.4G。
  - 2026-10-02 07:32 UTC 07:07 主审轮（Opus）审核：
    - 读了 archive-repair.json、`/tmp/t01_scan_r1.pkl`、`r2.pkl` 和 `verify_sip_repair.py`。V3 全过，修复逻辑正确。
    - V1/V2 不过：简报假设复权价有 4 位小数，实际供应商取整到分，两份归档的收益差最大约 0.02/价格。放宽后剩下的差异是同一天开盘、收盘收益平移相同的量（ACES 2021-03-29 都是 −0.23%，AER 2026-08-12 都是 −0.107%，OXLCM、OMFL/OMFS），即供应商修订了分红或复权因子；归档本来就应该跟随供应商当前的历史。
    - V4 不过：修复后那次常规更新会重抓最后几个交易日，差异只在 10-01 这一行的 volume/trade_count。
    - 决定：新口径写在任何新验证运行之前（按价格精度推导的容差；date_set / bar_correction / factor_revision / unexplained 四类；V4 只比重抓窗口之前的行）。验证已修好的 `data/live/failed-sip-daily-20261002`，通过就换入，同一执行轮接着做 T-20261002-02。这是数据质量检验口径的更正，不涉及研究门槛。
    - 磁盘现在剩 51G（df），不是 9.4G。


### T-20261002-02 数据：从修好的归档重建价格类特征表（两区不变性检验），接着刷新依赖表
- status: done（交互会话主审 2026-10-04 08:35 UTC：D = 2026-10-02。换入 daily、daily_broad、universe、universe_broad、SEC facts、SEC 日表、NSI、空头持仓（2018 起构建）；严格区按价格比例口径通过：daily_broad 4.07e-5，daily 0。alpha101/191 保留旧表：只给 ML 用，不进 M0。20 个日内列在新日期为空，M0 不用。未归因的只有 NSI 的 ESQ 和空头持仓 INHD 的 38 行，按主审裁定接受。SEC 的 sue 时点泄漏登记为数据坑 #62，审计排在 T-20261004-54。研究快照 2637 个文件 sha256 一致。提交 72b61c9、cc8c332。T-22 现在可以做）
- 交互会话注（10-02 05:40 UTC）：T-20261002-26（交互会话子代理）在 10:00 UTC 前后可能跑 1.5–2.2 GB 的重任务。本任务每个重步骤开始前用 `ps aux --sort=-rss | head` 确认；有超过 1 GB 的进程就等它结束，不要并行（本机 3.9 GB）
- priority: 1
- not_before: T-20261002-01 以 done 开头，并且 archive-repair.json 里 `verify_v2_pass` 和 `swap_done` 都为 true（07:07 主审轮预先授权，不必等主审审核）；第 1 步（代码和测试）可以和 T-01 并行
- brief: reports/research/control/briefs/T-20261002-02.md
- goal: 把组合线用到的价格类特征表接到修好的归档上，延伸到最近交易日。表包括 daily_broad、窄 daily、universe_broad、alpha101/191_broad，然后是 sec_fundamentals_daily、nsi、short_interest 和 SEC facts。给 T-22 的 live 目录和 D6 前向影子用。
- plan（主审 10-02 已定的口径，简报照此写）：
  - 价格类表是归档的派生缓存，从归档重建，不只追加。
  - 两区检验：
    - 严格区 ≤ 2026-08-21：ret_*、vol_*、max_ret_1_21、momentum_252_21、dist_from_252d_high 必须逐位不变，阈值沿用 T-21 的 max_changed_share ≤ 0.001；
    - 价格水平列（open、close、dollar_adv、amihud）、截面列（`*_rel`、adv_rank、宇宙成员）、依赖 SPY 的列（beta_252_spy、idio_vol_63），以及 08-24 之后的日期，只做诊断，按 `_restatements.jsonl` 和并集增长归因。
  - daily_broad 的往年分区是否重建：看 T-01 的被替换 symbol 数和磁盘（剩 11 GB）再定。T-21 的事件类表不动。SEC facts 换新文件：17 个旧键被 SEC 删除，值没变，记录下来。
  - `_t21_tmp` 作废。
- done_when: 各表在严格区通过，并刷新到 D；`freshness.json` 更新；研究快照哈希前后一致；已提交，标"待主审"。
- notes:
  - 2026-10-02 01:26 UTC 01:07 主审轮（Opus）登记；简报故意不提前写，等 T-01 的数字。
  - 2026-10-02 07:32 UTC 07:07 主审轮（Opus）写简报。和 01:07 的计划不同的三处：
    - 严格区不再要求逐位不变：供应商价格取整到分，被替换的 6952 个 symbol 的收益必然有取整差。改为按价格感知的容差 0.04/close，排除 T-01 归为供应商修订的 symbol；alpha 表看组合用到的列的逐日秩相关 ≥ 0.99；依赖表要求变化全部能归到被替换的 symbol 或 SEC 删除键的 CIK。
    - 只重建 2026 分区，往年分区不动（差别只有取整噪声，重建 alpha 表约 2 小时，对前向无用）。
    - 宇宙成员按时点记录处理：2026-08-31 以前各月不改，只追加 09-30。

### T-20261002-03 信号库：10-K 文本变化数据（Lazy Prices，U3000，2014-07..2026-09，EDGAR 主文档）
- status: done（交互会话主审 2026-10-04 07:54 UTC：抓取 03:29 完成，merge 和 summarize 07:41 完成；summary.json 七项验收全部通过，其中 no_early_visible_day 为真，filing-date floor 移动了 4 个可见日；4023 个 CIK，35,596 份 10-K，31,199 对（0.876），抓取失败 0，解析失败 0.06%，2016 年后 RF 和 MD&A 找到率 95.6% 和 95.4%；2016 年后有 44 对可见日为空，T-04 要排除并计数。T-04 现在可以取）
- priority: 2
- not_before: 无（简报第 0 步：不在 21:30–00:30 UTC 运行；和 T-20261002-01 不并行，T-01 先做）
- brief: reports/research/control/briefs/T-20261002-03.md
- goal: 组合 v1 的停止条件已经成立，要先补信号。这个任务建第一个文本信号的数据：每份 10-K 和上一份的相似度，分全文、1A、7 三节，算余弦和 Jaccard，可见时间取 acceptanceDateTime。信号一年只更新一次、换手极低，正好补 v1 每年 172 bp 的成本短板。
- plan:
  - 按冻结的预注册 `reports/research/iterations/t20261002_lazy_prices_ic/hypotheses.md` 第 2 节建数据，不算任何 IC。
  - 复用 `read_bulk_records`、`SecClient`、`attribute_trading_day`，每秒 8 次请求，可断点续跑，每轮最多抓 120 分钟。
- done_when: `reports/research/program/text-similarity-2026-10-02/summary.json` 满足简报的验收数字，测试通过，已提交；结果标"待主审"。
- notes:
  - 2026-10-02 01:38 UTC 01:07 主审轮（Opus）写入。direction-check 已 ok。预注册写在任何数据之前，三个候选、方向、判定都已冻结。
  - 预计 4–6 万份 10-K，抓取受 SEC 限速约束，大约要 2–3 个小时，可能跨两个执行轮。
  - 2026-10-02 06:26 UTC 执行轮（Sonnet 5.5，子代理 a18426ca2c34bca4f，待主审）：脚本+测试已提交 6ae7a01（16 测试过、ruff 过）。只抓了 218/4023 个 CIK：2428 份 10-K、2204 对，抓取失败 0、解析失败 0；2016 年后 rf_found 0.957、mda_found 0.947；cos_full 分位 5/25/50/75/95 = 0.9947/0.9979/0.9987/0.9992/0.9996（中位在 [0.80,0.999] 内但贴近上沿），cos_rf 中位 0.9979，cos_mda 中位 0.9945。**一条验收不过**：2 对的 visible_day 比 filing_date 早 >1 天（CIK 36047：filing 2021-03-01、visible 02-26；CIK 47518：filing 2018-11-19、visible 11-16；SEC acceptanceDateTime 早于 filingDate），按预注册未改，主审要定怎么处理。解析器改动（首轮 20 CIK 试跑 mda_found 0.867，因为不少申报把 Item 标题排成单行表格）：整表文本只是短的 "Item N" 标题时留标记、分词前剔除，其余表格文字仍整表剔除，这是对"剔除所有表格"的小解释，主审要确认。首轮抓取（06:03–06:15）内存每分钟涨约 100 MB，已停并修（不影响产出）；首轮请求数/用时计数丢失，summary.json 只含第二轮（1383 次、481 秒），合计约 2428 次。速度约 80 份/分钟，剩余约 3.32 万份约需 7 小时（多个 120 分钟轮）。产物：scripts/build_10k_text_similarity.py、scripts/summarize_10k_text_similarity.py、tests/test_build_10k_text_similarity.py、reports/research/program/text-similarity-2026-10-02/{report.md,summary.json}；数据在 data/features/text_similarity/（不提交；_trial/、_trial2/ 是子代理自己的试跑目录，删除被权限拒绝）。续跑命令：`setsid nohup scripts/run_capped.sh --mem 1.8G -- uv run python scripts/build_10k_text_similarity.py fetch --resume --max-minutes 120 > logs/t20261002_03_fetch3.log 2>&1 &`，之后 `merge`，再 `scripts/summarize_10k_text_similarity.py --snippets data/features/text_similarity/_trial2/_snippets.json data/features/text_similarity/_snippets_extra.json`。
  - 2026-10-02 07:32 UTC 07:07 主审轮（Opus）审核：
    - **可见时间有缺陷，已修（aad93b8）**。SEC 的 acceptanceDateTime 是混合口径：大部分是真 UTC，少数是美东时间带了假的 "Z"。主审抓了 8 份申报的 EDGAR 索引页 "Accepted" 字段核对：CIK 36047、47518、6769 是美东时间；1750、23217、4457、56047 是 UTC。按 UTC 解析会让美东口径记录里的盘后申报早一天可见。
    - 修法：一律按美东墙钟时间解析，这样绝不早于真实时间（真 UTC 的记录会推后 4–5 小时）；再加一条下限，可见日不早于申报日当天或之后的第一个交易日。
    - 对已抓的 2428 份：727 份可见日推后 1 个交易日（跨周末显示为 3–4 天），没有一份提前；可见日早于申报日的从 16 份降到 0。原验收只抓到 2 份，因为它允许早 1 天。验收改为：可见日不早于申报日当天或之后第一个交易日，必须 100% 满足。18 个测试通过。
    - 其他 SEC 管道：`build_earnings_events.py` 已经把全部记录当美东时间读，同样保守，不会前视；13D、并购管道属于已关闭方向。组合主题不用这几个管道。
    - 解析器的改动（只有 "Item N" 标题的表格留作分节标记，分词前剔除）认可：比较的文字不变，只影响分节定位。
    - cos 中位数贴近 1 是冻结定义造成的（不去停用词、原始词频），不是实现错误。候选秩 IC 不受单调变换影响。
  - 2026-10-02 08:43 UTC 07:07 主审轮在后台续跑抓取（07:15–08:39，`logs/t20261002_03_fetch3.log`）：本轮 1116 个 CIK，约 11.9k 份，每分钟约 140 份。累计 1334/4023 个 CIK、14,336 份；抓取失败 0；解析失败 11（10 份 too_large、1 份 ValueError）。还剩 2689 个 CIK，约 2.9 万份，按现在的速度约 3.4 小时，也就是两到三次 80–120 分钟的运行。
    - 续跑：`setsid nohup scripts/run_capped.sh --mem 1.2G -- uv run python scripts/build_10k_text_similarity.py fetch --resume --max-minutes 110 > logs/t20261002_03_fetch4.log 2>&1 < /dev/null &`。这次用 1.2G 上限没有出问题。不在 21:30–00:30 UTC 跑，不和 T-01/T-02 的重任务并行。主审轮的空档也可以续跑。
    - 全部抓完后：`merge`（会用 aad93b8 的可见时间代码，日志里要有 "filing-date floor moved"），再跑 `scripts/summarize_10k_text_similarity.py --snippets data/features/text_similarity/_trial2/_snippets.json data/features/text_similarity/_snippets_extra.json`。
    - 验收新增一条：可见日不早于申报日当天或之后的第一个交易日，必须 100% 满足。替代原来"不早于申报日前一天"的口径。


### T-20261002-04 信号库：Lazy Prices 残差 IC 入库检验（3 个候选、安慰剂、和 M1 的相关）
- status: ready（简报 07:07 主审轮已写；按 not_before，T-03 以 done 开头之后执行轮才能取）
- brief: reports/research/control/briefs/T-20261002-04.md
- 主审注（2026-10-02 07:32 UTC，07:07 主审轮）：T-03 的执行轮 notes 写了 cos_full/rf/mda 的分位数，所以读过队列的人都看过边际分布。这条规则按"不许看过任何 IC、收益相关统计，也不许看过和收益对齐的逐份相似度"执行：边际分布不带收益信息，候选、方向和门槛 01:38 已冻结，写简报时不能再改。
- priority: 2
- not_before: T-20261002-03 以 done 开头，并且 text-similarity-2026-10-02/summary.json 的验收全部为真（含可见日下限 100%）
- goal: 按 `t20261002_lazy_prices_ic/hypotheses.md` 第 4–5 节，机械判 PASS、WATCH 或 FAIL。PASS 的才进组合合同，预注册边际净夏普的检验。
- plan:
  - 形成日和目标收益与 `t20261001_book_v1/formation_ic.parquet` 完全相同；
  - 用 Newey-West t（滞后 3）、100 个种子的同月置换安慰剂、和 M1 合成分的秩相关；
  - 补候选清单，跑 `oc research iteration validate --stage pre-backtest`。
- done_when: `t20261002_lazy_prices_ic/results.json` 有三个候选的数字和机械判定，已提交，标"待主审"。
- notes:
  - 2026-10-02 01:38 UTC 01:07 主审轮（Opus）登记。
  - 2026-10-02 07:42 UTC 07:07 主审轮（Opus）写简报。同时在 hypotheses.md 末尾追加了修正案 01：可见时间按美东墙钟时间解析，并加申报日下限，只会推后、不会提前；另加校验器要的四个英文标记的对照。
    - pre-backtest 闸门现在是 blocked：外部简报、搜索空间、决策记录还是模板，外部简报只有 5 个来源（要 ≥ 8，其中论文 ≥ 3）。简报第 1 步要求先补齐、两道检查 ok，才能把相似度和收益对齐。
    - 机制复用 T-24 的 `screen_book_signal_candidates.py`，并先做 1e-9 的身份核对。

### T-20261002-30 账户层复盘：四条 ETF sleeve 和 v1.2 的相关、风险集中、一起亏、前向对账、去一和加 v1.2 的夏普（11-01 续期依据）
- status: done（交互会话主审 2026-10-04 10:09 UTC：数字已核对 account-review.json。T-43 权重下 S3 占组合风险 89%、有效下注 1.25；同波动口径 T-43 夏普 1.89 对 S3 1.84，增量很小；四条倒数波动加 F1 是 2.49 对 1.74。S3 前向差 −3.75%（9 天）不是启动时点：同一个 08-31 调仓，模拟盘按 09-18 的数据选 UPRO，修复后的数据选 SHY，交 T-20261004-55 查。C2 存档按修复后数据重生成也交 T-55。提交 e5ad884）
- priority: 3
- not_before: 无（不和 T-20261002-01/02 的重任务并行；22:07 执行轮不能跑 T-01 换入和 T-03 抓取，适合做这个）
- goal: 纲领两周优先级第 5 项，10-25 前交机主。四条 sleeve 同在一个模拟账户，S2 和 S3 日收益相关 0.83；v1.2 准备开新账户。要知道哪条是重复下注，以及加入 v1.2 后账户夏普在同波动口径下怎么变。只出数字，续期建议由主审写。
- plan: 复用 `run_h20260927_01_sleeve_combination.sleeve_returns()`、C2 lane 的日收益、v1.2 的账户序列和模拟盘成交记录。三个窗口算相关；按 2026-09-30 算 63 日风险贡献和持仓重叠；算去一组合和加 v1.2 组合的夏普，各配同波动的 S3 对照，另报 20 bp；报最差 21/63 日窗口；做前向对账。
- done_when: `reports/research/program/account-review-2026-10/account-review.json` 含简报列出的六个键，report.md 已写，已提交，标"待主审"。
- brief: reports/research/control/briefs/T-20261002-30.md
- notes:
  - 2026-10-02 07:35 UTC 07:07 主审轮（Opus）登记并写简报。这是描述性分析，不涉及策略选择，不需要预注册；结论和续期建议由主审在结果出来后写。

  - 2026-10-04 10:09 UTC 交互会话主审（Opus）裁定：
    - S3 风险集中是配置问题，不是数据问题。T-43 是按收益优先的预注册规则选出的，这里不事后改它。
    - 进实盘候选之前，另立合同做配置第二版：目标改为夏普优先、加单条 sleeve 风险上限，并纳入 F1 和 T-55 的脆弱性结果。
    - 补充窗 2018-02..2023-08 加 F1 反而低于对照（0.33 对 0.46），这一条要写进第二版合同。
### T-20261004-51 预测市场第二轮：Polymarket 财报超预期赔率 vs 公告窗口收益（h20261004_pm_earnings_beat_odds）
- status: done（交互会话主审 2026-10-04 08:25 UTC：按停止规则否定。A1 周 IC +0.019，t 0.43，30 周；置换百分位 64.2；净价差 −97 bp/对；安慰剂都无效；MDE 是周 IC 0.110、价差 227 bp。赔率本身有信息（AUC 0.81），但 15:00 ET 时股价已经反映。正对照按事件层 t 4.59 判通过，裁定写在 results.json。时间按 EDGAR 修正，见数据坑 #61。结果提交 2a05f83；登记 dir:prediction_market_earnings_beat_odds = refuted）
- priority: 2
- brief: reports/research/control/briefs/T-20261004-51.md
- goal: 用 2025-09 至 2026-10 已结算的 1354 个 Polymarket 财报合约，检验公告前赔率在同周横截面上的排名，能否预测公告窗口相对 SPY 的超额收益。机主 10-02 要求持续迭代预测市场。
- done_when: 文书冻结并通过 pre-backtest 检查；数据漏斗写进 data-feasibility.json；先跑正对照，再按冻结规则算 H-A；results.json 和 report.md 已提交，标"待主审"。
- notes:
  - 2026-10-04 01:26 UTC 交互会话（Opus）登记。设计冻结在 ee197a4，情报在 a75be10。
  - 功效有限：在 6% 标准差的假设下，最小可检测价差约 100 bp。不通过只说明没有大效应，不代表小效应不存在；不通过时转前向影子。

### T-20261004-01 组合线 v1.3 候选：成本感知的交易规则（部分调仓、不交易区间），在不改信号的前提下给 v1.2 主变体降成本
- status: done（否定：未过冻结的 E3，保留 v1.2 全量调仓；10-04 07:20 UTC 07:07 主审轮对照原始 JSON 复核，决策记录已写，final 校验 ok）
- priority: 2
- not_before: 无（简报第 0 步：不在 21:30–00:30 UTC 跑；不和 T-20261002-02/T-20261001-22 的重任务、T-20261002-03 的抓取并行，同一执行轮若取了 T-03，先跑完它再跑本任务，或留给下一轮）
- brief: reports/research/control/briefs/T-20261004-01.md
- goal: v1.2 主变体 M0_U3000 近期毛夏普 1.72、净 1.49，成本 224 bp/年（压力期 152 bp/年），2 倍成本下夏普 1.23；成本是它进实盘前最大的可控损耗和最大的未知。检验 5 个预注册交易规则（GP 部分调仓 ½、⅓，单位书部分调仓且 VIX 缩放立即生效，NMV 式不交易区间 0.25/0.50 个截面标准差）能否让净夏普在近期和压力期都高 ≥0.10。
- plan: 合同 `reports/research/iterations/t20261004_book_v13_tc/hypotheses.md`（2026-10-04 01:30 UTC 冻结，direction-check 和 pre-backtest 都 ok）。第 1 阶段：B0 逐位复现 R6（≤1e-12），5 规则 × 5 偏移，E1（runbook 优化规则 +0.10 两窗）、E2（≥4/5 偏移改善）、E3（全样本配对 NW t ≥2）、E4（|beta| ≤0.15）；没有规则合格就停，保留 v1.2。第 2 阶段只对 R*：其他三变体、账户层（整股、$100 最小单）、20 种子安慰剂、15 试验族 DSR 定档。另做不含收益的诊断（换手来源、各主题周度秩自相关）。
- done_when: `t20261004_book_v13_tc/{identity,results,trial-ledger,diagnostics}.json` 和 `report.md` 已提交（git add -f），`mechanical_status` 为简报列出的三个值之一，新测试通过；结果标"待主审"。
- notes:
  - 2026-10-04 01:30 UTC 01:07 主审轮（Opus）登记并写简报。看过的只有 B0 的成本拆分（合同第 0 节）：VIX 规则翻转每档每年 7.5 次，占成本 26%；先验 E1 约 20%、最终替换约 12%。不过也要交付成本-α 前沿和换手来源，供"按持续性倾斜的瞄准组合"（GP 命题 3）设计下一份合同。
  - 2026-10-04 04:40 UTC 执行轮（Sonnet 5.5 子代理，机械结果，待主审）：identity 通过（max abs diff 0.0，o0/o3 及 5 个偏移对 R6 均 0.0）；B0 近期/压力期偏移中位数净夏普 1.485/0.598；5 规则 delta（近期/压力）：P2 +0.112/+0.036，P3 +0.154/+0.056，P2V +0.038/+0.071，N25 +0.073/+0.083，N50 +0.158/+0.124；E1-E4：P2/P3/P2V 只过 E2、E4；N25 过 E2、E3(t 2.94)、E4 不过 E1；N50 过 E1、E2、E4，E3 全样本 NW t 1.76 <2 不过。selected_rule=null，mechanical_status=no_rule_eligible_keep_v12，未跑第 2 阶段。诊断 D1：VIX 翻转刷新占换手 25.9%、成本 25.7%（近期）；D2 周度秩自相关 0.93–1.00；D3 2 倍成本：N50 1.642→1.561，B0 1.485→1.269。产物：reports/research/iterations/t20261004_book_v13_tc/{identity,results,trial-ledger,diagnostics}.json、report.md，代码 open_composer/research/equity_book/trading_rules.py、scripts/book_v13_trading_rules.py、tests/test_trading_rules.py（12 测试通过，ruff 干净）；rule parquet 在 data/research/book_v13/（未提交）。待主审：`iteration validate --stage final` 为 blocked（decision_record_missing_continue_pivot_stop，decision-record.md 在禁改清单，需主审写）；子代理自加了 `--stage final`；trial-ledger 是 .json 而校验器要 .jsonl。
  - 2026-10-04 07:20 UTC 07:07 主审轮（Opus）审核：数字与 results.json 逐项一致（identity 0.0；N50 近期/压力 +0.158/+0.124、5/5 偏移、beta 合格、全样本 NW t 1.758 < 2；N25 t 2.94 但 E1 +0.073/+0.083）。前视、幸存者、调仓日检查无问题（规则与 B0 用同一信息集，全部 5 个偏移取中位）。主审发现合同自身缺陷：E3 用原始收益差，不是规模无关的，而 N50 波动只有 B0 的 0.966（总敞口 1.43 vs 1.68）；事后诊断（不改判定）同波动配对 t：N50 2.50、N25 3.59。判定按冻结规则维持'不替换'。D2 没有快主题，GP 命题 3 的后续不开。N50 冻结为唯一挑战者，只在新信息下重开（≥252 个 09-17 以后的会话离线复算，或实盘测得成本 ≥ 模型）。决策记录 `t20261004_book_v13_tc/decision-record.md`。

### T-20261004-02 组合线 v1.4 候选 第 A 阶段：样本外 ML 合成器（M2 GBDT 集成、M3 DKKM 随机特征 SDF）和简化毛收益闸门
- status: done（05c643e；10-04 16:48 UTC 16:20 主审轮对照 stage_a.json 复核：机械判定正确，stage_b_authorized，留下 m0m2、m0m3；ml_contribution_pass = false（纯 M2 压力期-ML 0.513 < M0 0.521，纯 M3 0.213）；结论以 T-54 为条件）
- priority: 1
- not_before: 无（简报第 0 步：本地重步骤不在 21:30–00:30 UTC 跑；有超过 1 GB 的进程（交互会话的 T-20261002-02）时等它结束；不起第二个 10-K 抓取进程）
- brief: reports/research/control/briefs/T-20261004-02.md
- goal: 设计文档第 5 节的 ML 合成器（Stage 2b 只因 v1 构造失败而取消）放进已到 P1 的 v1.2 构造里检验：同 22 个慢主题输入加对数市值、标签对齐这本书实际赚的收益（beta 对冲、行业去均值），每年扩张重训（2019–2026，隔离 43 个会话），看 M2、M3、M0M2、M0M3 能否在近期和压力期-ML 都打赢 M0 的简化毛夏普。回答机主"模型训练能不能帮这本书"，也决定信号层下一步是换模型还是补新输入。
- plan: 合同 `reports/research/iterations/t20261004_book_v14_ml/hypotheses.md`（2026-10-04 07:31 UTC 冻结，direction-check 和 pre-backtest 都 ok）。本任务只做第 A 阶段：建特征和标签（本地）、Modal 8 个分片训练和预测（≤ $2）、标签打乱检查、简化周度毛收益（5 个偏移取中位）对比 M0。闸门：候选两窗都高于 M0 才授权第 B 阶段（T-20261004-03）。
- done_when: `t20261004_book_v14_ml/{build.json,stage_a.json,stage_a.md,model-meta/}` 已提交（git add -f），`mechanical_status_stage_a` 为简报列出的三个值之一，新测试通过；结果标"待主审"。
- notes:
  - 2026-10-04 07:35 UTC 07:07 主审轮（Opus）登记并写简报。写之前看过：v1.2（M1 1.389 < M0 1.506；收益主要是风格溢价，特质 −1.2%/年）、T-17/T-24（纯量价 ML 近期弱）、v1.3。外部证据：DKKM 2024、AQR 2024（支持，未扣成本）、BSW 2022（反对：扣成本后线性预测更好）。先验：第 A 阶段过约 45%，ml_contribution_pass 约 25%，第 B 阶段合格约 15%，最终替换约 4%。

  - 2026-10-04 12:06 UTC 执行轮（Sonnet，子代理耗时约 115 分钟）：第 A 阶段跑完，`stage_a.json` `mechanical_status_stage_a`=stage_b_authorized，survivors=[m0m2, m0m3]；contract sha 不变，permutation_check 通过（lgbm_perm 近期 -0.519/压力 -0.019，m3_perm 0.037/-0.572，限 1.22/0.93）；embargo_ok_all 与覆盖按简报核对通过（2019 起每日成员中位 2175）。偏移中位简化毛夏普（近期/压力-ML）：m0 1.735/0.521，m2 2.114/0.513，m3 2.362/0.213，m0m2 2.008/0.582，m0m3 2.247/0.536（压力窗领先幅度 +0.061、+0.015，很小）。Modal $0.6645。产物 reports/research/iterations/t20261004_book_v14_ml/{build.json,stage_a.json,stage_a.md,model-meta/}。子代理偏差：首次 smoke 写错目录已修；最终窗口止于 2026-09-09 决策日（r5 需要 C[p+6]）；stage_a 的 Modal 成本从 0.6563 手工改为 0.6645，其余数字不变；22 个信号库列缺失用常数填，rank 后变并列平均秩。待主审。
  - 2026-10-04 16:48 UTC 16:20 主审轮（Opus）审核：合同哈希一致（af7714…），打乱检查通过（lgbm_perm 近期 −0.519/压力 −0.019，m3_perm 0.037/−0.572，限 1.22/0.93），embargo_ok_all 为真，2019 起每年最少 1998 名成员。偏移中位简化毛夏普（近期/压力-ML，括号里是赢 M0 的偏移数）：M0 1.735/0.521；M2 2.114（5/5）/0.513（1/5）；M3 2.362（5/5）/0.213（0/5）；M0M2 2.008（5/5）/0.582（4/5）；M0M3 2.247（5/5）/0.536（4/5）。闸门是两窗都高于 M0，m0m2、m0m3 机械通过；但压力期只领先 +0.061/+0.016，第 B 阶段 E1 要求净 +0.10，混合分数的周自相关 0.968/0.967 低于 M0 的 0.983（换手更高），主审估计压力期 E1 通过约 10%。纯 ML 只在近期赢：2024 年后的模型训练了 306–407 周，2019–2023 的只有 55–256 周，增量来自样本长度还是市场状态，本合同不区分。M3 暴露诊断（本轮，年度截面秩相关中位数）：2025 年对规模、动量、低 beta、低特质波动、价值、毛利、季节性都在 ±0.05 以内，对 sue_eps −0.18、空头成交比 +0.15，近期与 M0 的相关 0.001，是分散的非线性信号；M2 主要是低 beta（约 0.6）、低特质波动（0.54–0.67）和大市值（0.3–0.45）。实现偏差认可：信号库列的缺失本来就以常数存储，与 M0 同输入，不是前视；最后一个决策日 09-09（r5 需要 C[p+6]）。T-54 若发现 sue_series 实质泄漏，M0 和 ML 两边都要重算。
### T-20261004-03 组合线 v1.4 候选 第 B 阶段：第 A 阶段留下的候选走 v1.2 策略层，对比 M0（E1/E2/E4/E5、选择、ml_contribution_pass）
- status: ready（主审 10-05 07:07 轮决定：本机跑，容差不动；见简报末节）
- priority: 2
- not_before: T-20261005-01 和 T-20261005-32 都以 done 开头之后；本机条件（可用内存 ≥ 2500 MB、没有别的进程超过 1 GB、不在 21:30–00:30 UTC）见简报末节
- brief: reports/research/control/briefs/T-20261004-03.md
- goal: 对第 A 阶段的留存候选跑 v1.2 策略层 × 5 个偏移（2019-01-02 起，B0r 与 R6 逐位核对），按冻结规则判 E1（两窗 +0.10）、E2（每窗 ≥4/5 偏移）、E4（|beta| ≤ 0.15）、E5（打乱检查），选 R*，报 ml_contribution_pass 和 ml_additive；同波动配对 t 只报告。
- plan: 简报 T-20261004-03。第 C 阶段（账户层、20 种子安慰剂、族 19 定档）由下一主审轮看过本阶段后另写简报。
- done_when: `t20261004_book_v14_ml/{identity.json,results.json,report.md,trial-ledger.json}` 已提交，`mechanical_status` 为两个值之一，新测试通过；结果标"待主审"。
- notes:
  - 2026-10-05 04:09 UTC 执行轮 2c717355 开始（sonnet-high 子代理前台）
  - 2026-10-04 07:35 UTC 07:07 主审轮（Opus）登记并写简报。同一执行轮在 T-02 完成后可以接着跑本任务（不并行，重任务一次一个）。
  - 2026-10-04 12:06 UTC 执行轮：T-02 已 done 且 stage_b_authorized，但 T-02 子代理用了约 115 分钟，已到软上限，T-03 留给下一执行轮（22:07 UTC；注意不在 21:30–00:30 跑本地重步骤，可能要到 04:07 轮）。
  - 2026-10-04 12:17 UTC 执行轮开始（子代理 sonnet-high 前台，mem 1.5G）
  - 2026-10-04 13:52 UTC 执行轮：子代理写完 `scripts/book_v14_ml_eval.py`（identity/passes/evaluate 三阶段，passes 和 evaluate 未测）和 `tests/test_book_v14_ml_eval.py`（6 个合成测试通过，ruff 干净），提交 2690810。3 决策冒烟的 identity：5 个偏移 (a) 对 R6、(b) m0 对 (a) 最大差 0，pass true（不是完整序列的 1e-12 门）。完整 identity 12:24 起跑，机器 swap 约 5.7 GB、I/O 等待 60–90%（别的会话占 0.5–1.1 GB），86 分钟只拿到约 3.5 CPU 分钟，13:51 被杀，没写出任何偏移。**没有 Stage B 数字**：未写 identity.json、S_*_o*.parquet、results.json、report.md、trial-ledger.json。断点：机器安静后依次 `scripts/run_capped.sh --mem 1.5G -- uv run python scripts/book_v14_ml_eval.py --stage identity`（会写 S_B0r_o<k>.parquet）、`--stage passes`（跳过已有文件，可续跑）、`--stage evaluate`；之后用 `git add -f` + pathspec 提交 identity.json/results.json/report.md/trial-ledger.json。预计无争抢时约 20 个 pass、每个约 1 分钟。待主审（含：是否等机器空闲再跑，或把 identity 改到 Modal）。
  - 2026-10-04 16:48 UTC 16:20 主审轮：机器仍满载（负载 13、可用内存 0.57 GB、交互会话的 PIT 审计进程占 1.3 GB），第 B 阶段的 identity 和 passes 改到 Modal（预算检查 90 分钟，4 核 8 GiB，约 $0.3），evaluate 在本机只读 parquet。判定规则、窗口、候选都不变。T-20261004-04 的第 B 阶段复用本任务的 B0r，所以先做本任务。

  - 2026-10-05 05:10 UTC 执行轮 2c717355（子代理 sonnet-high，提交 657d58b）：Modal 上 identity 未过（`identity.json` pass=false，容差 1e-12 不动）。源 (b) PredictionSource(m0) 对 R6 逐位一致（≤1e-12）；路径 (a) AlphaSource M0 在偏移 0、4 通过，偏移 1/2/3 在 10/5/5 个标签行超过 1e-12（1–2 个周度决策块），最大 hedge_size 差 4.54e-07、gross 差 9.9e-08（来自 `identity.json`）。子代理在本机重跑偏移 2 的 2021-11-05 块，a 和 b 都与 R6 逐位一致，疑为 Modal CPU/BLAS 浮点差，不是逻辑错。未跑 passes/evaluate，无 results.json、report.md、trial-ledger.json、mechanical_status。`S_B0r_o*.parquet` 在 `data/research/book_v14/stage_b_out/`，来自未过门的运行，不要给 T-04 用。Modal 花费约 $0.011（本月 billed $1.18、projected $2.32/$25）。modal_run.py 实际命令加了 `--data data/research/vix` 和只同步 equity_book 的子目录；`scripts/book_v14_ml_eval.py` 加了 `--workers`、`--mirror-dir`、`--deadline-min`（进程池，循环不变，7 个测试通过，ruff 干净），子代理注明覆盖了之前一次已提交的版本。需主审决定：(1) identity 的 (a) 路径改在本机重跑（本机 CPU 对该块逐位复现）；或 (2) 给 Modal 浮点差定一个容差（冻结值 1e-12 我没动）。之后 passes 在 Modal 约 2 分钟，evaluate 本机。待主审。
  - 2026-10-05 07:56 UTC 07:07 主审轮（Opus）审核：identity.json 核对——偏移 0、4 逐位一致；偏移 1/2/3 的 a 对 R6 最大差 3.8e-7/4.5e-7/9.9e-8，b 对 a 最大差 1.24e-6/1.33e-6/1.59e-6，所以这三个偏移上 b 也不等于 R6，上面"b 对 R6 逐位一致"的说法 JSON 不支持。符合跨平台、跨线程数的浮点差（Modal 线程 = 2 × 核数），未证明。决定：冻结容差 1e-12 不改，不用 Modal 跑 identity；identity、passes、evaluate 都在本机默认线程下跑（与 R6 同平台），命令见简报末节；本机 identity 也不过就 blocked 并写第一个不一致的标签行。priority 降为 2，排在 P1 阶段 0 和 P2 阶段 1 之后（计划 v2 第 3.0 节，本机重步骤一次一条）。Modal 那批 S_B0r 不用。
### T-20261004-04 组合线 v1.5 候选：用 12 个月因子动量给 M0 的输入择时（只留过去一年多空收益为正的输入或主题），第 A、B 阶段
- status: ready
- priority: 2
- not_before: T-20261004-03 以 done 开头之后（第 B 阶段复用 T-03 在本机产生的 B0r，和它同平台，在本机跑；第 A 阶段可以在 Modal，但同一执行轮先做 T-03）
- brief: reports/research/control/briefs/T-20261004-04.md
- goal: 设计文档第 12 节择时层的第一步。v1.2 赚的主要是风格溢价，M0 对 22 个输入固定等权，过去一年一直亏的输入（近期是动量类）照样占权重。按 Ehsani–Linnainmaa 2022（时间序列赢家组合夏普 1.33，对全部等权 1.06），只留过去 12 个月多空收益为正的输入或主题，检验 v1.2 构造下偏移中位净夏普能否两窗都 +0.10。回答机主"择时"的问题；过了进影子，不过就关掉近期收益择时。
- plan: 合同 `reports/research/iterations/t20261004_book_v15_fm/hypotheses.md`（16:44 UTC 冻结，direction-check 和 pre-backtest 都 ok）。第 A 阶段：建择时权重（只用 t ≤ p−2 的标签）、3 个候选（FM12 输入层只留赢家、FM12T 主题层、FM12H 半倾斜）、恒等检验、简化周度毛夏普对 M0、每个候选 20 种子马尔可夫择时安慰剂；闸门：两窗都高于 M0，且全期安慰剂分位 ≥ 0.90。第 B 阶段：v1.2 策略层 × 5 偏移对 B0r，E1/E2/E4/E5，选 R*。第 C 阶段由主审另写。
- done_when: `t20261004_book_v15_fm/{build.json,stage_a.json,stage_a.md}` 已提交（git add -f；第 B 阶段跑了再加 results.json、report.md、trial-ledger.json），状态值在允许范围内，新测试通过；结果标"待主审"。
- notes:
  - 2026-10-04 16:48 UTC 16:20 主审轮（Opus）登记并写简报。写之前看过：信号层便宜测试（`signal-level-check.txt`：12 个月赢家等权对全等权，压力期 0.68 对 0.49、近期 1.99 对 1.81，赢家减输家 53.7 bp/月，NW t 2.74，96 个月；1 个月回看无效）、v1.2 的 M1 < M0（负面）、v1.4 第 A 阶段。原文已读：E–L 2022 表 3、Fan 2022 表 9（多空因子动量不如买入持有，没测只留赢家）。先验：第 A 阶段约 40%，第 B 阶段合格约 18%，替换约 5%。
  - 2026-10-05 07:56 UTC 07:07 主审轮：T-03 的 identity 改到本机（见 T-03 简报末节），本任务第 B 阶段跟着在本机跑，priority 降为 2。

### T-20261004-52 数据：修 8-K 财报事件表的受理时间（改用 EDGAR 索引页 Accepted，修复数据坑 #61）
- status: done（交互会话主审 2026-10-04 10:09 UTC：接受。16089 笔全部取自索引页，99.66% 的行差恰为旧偏移，20/20 抽查一致，0 删除 48 新增；55 行旧值本来就对，记录不追。下游交 T-20261004-56。v1.2 和模拟盘不读这张表，也不读 sue_8k_visible（已 grep 核对），live 路径不变。提交 5807d85）
- brief: reports/research/control/briefs/T-20261004-52.md
- priority: 3
- not_before: T-20261004-51 以 done 开头（它在用这张表做只读匹配）
- goal: `data/features/earnings_events/{2024,2025,2026}.parquet` 的 acceptance_utc 被转换了两次，比真实 UTC 晚 4 或 5 小时（数据坑 #61）。改 `scripts/build_earnings_events.py`：受理时间一律取 EDGAR 索引页的 Accepted（美东墙钟），再转成真实 UTC。重建三个年份分区，新增一列 `acceptance_source`。
- done_when:
  - 抽查 20 份，全部与索引页一致；
  - 逐行比较修复前后：所有时间差都是 +4h 或 +5h，取哪个只看夏令时，不允许出现别的差值；
  - 有测试，旧表备份到 `data/live/backup-features-20261004/earnings_events/`；
  - 提交代码和报告（数据不提交），标"待主审"。
- notes:
  - 2026-10-04 08:19 UTC 交互会话（Opus）登记，没写单独简报：done_when 就是全部验收。请求频率控制在每秒 4 次以内，带真实 User-Agent。
  - 内存很小，不跑重任务。


### T-20261004-53 预测市场第三轮：中期选举控制权赔率 → "Trump trades"（Goldstein-Li-Wang 2026 的样本外检验）＋ 前向影子到 11-04
- status: done（交互会话主审 2026-10-04 08:48 UTC：按停止规则否定。2025-10-08 至 2026-10-02 共 248 个会话（0.98 年，冻结文本估 1.4 年，估多了）；净夏普 −1.20，NW t −1.24，循环移位百分位 16.7；预测斜率 +5 bp/pp（t 0.91），论文是 13；五类资产和 Kalshi 信号全负。方向取自论文附录 A.1，与冻结的备用方向一致。登记 dir:prediction_market_policy_odds_leadlag_glw2026 = refuted。前向影子 cron 已装，按预注册记录到 11-04，cron 带日期守卫，11-05 后自动停）
- priority: 2
- brief: reports/research/control/briefs/T-20261004-53.md
- goal: 用论文原样的变换、资产和方向，检验 2026 中期选举众议院和参议院控制权赔率的日变化，能否预测次日"Trump trades"组合的收益。2025-01 至 2026-10-02 做回测；10-05 至 11-04 做前向影子，因为选前最后一个月赔率波动最大。
- done_when: 文书冻结并通过 pre-backtest 检查；数据漏斗写清楚；H-M 和安慰剂按冻结规则算完；影子脚本和测试写好（cron 由交互会话安装）；已提交，标"待主审"。
- notes:
  - 2026-10-04 08:25 UTC 交互会话（Opus）登记。设计冻结在 6f6bd6c。功效有限：只有效应接近论文的夏普 1.95 时才检测得出来。


### T-20261004-54 审计：SEC 日表 sue_series 的时点泄漏（数据坑 #62），量化它对 v1.2 earnings 主题和 M0 回测的影响
- status: done（交互会话主审 2026-10-04 16:32 UTC：接受。闸门 09:43 冻结（ad834a4），数字出来后未开：M0 平均形成 IC 近期 0.01095→0.01092（相对 −0.3%），压力窗 0.01544→0.01545；主题最大变化 value −0.00039（门槛 0.005）；综合分按日秩相关 p5 0.9990（门槛 0.98）。#62、#63 对 v1.2 M0 证据不重要，第 4 步未跑。提交 55de760、eb33e23、0530ab6）
- brief: reports/research/control/briefs/T-20261004-54.md
- priority: 2
- goal: T-02 发现 sue_series 用的是最终的季度梯，迟到的 10-Q 会改写它申报日之前的历史 sue_eps 和 sue_rev（SHPH 的 09-24 申报改写了 67 行）。研究快照里的 earnings 主题（M0 九个主题之一）可能带有少量前视。按申报日逐日重建季度梯，得到严格时点的 sue，再比较 earnings 主题的 IC 和 M0 回测夏普。
- done_when: 给出受影响的行数和 symbol 数（按年）、严格时点版与研究快照版 sue 的相关、earnings 主题 IC 的变化、M0 主变体两个窗口的净夏普变化；结论交主审。
- notes:
  - 2026-10-04 08:33 UTC 交互会话（Opus）登记。live 的最新值在时点上是对的，只有历史行受影响，所以不挡 10-07 首单；但它关系到 v1.2 回测是否可信，要在第一次复审之前做完。


### T-20261004-55 一致性：10-02 价格修复后模拟盘和研究对不上（S3 八月信号翻转、S3 信号脆弱性、C2 存档重生成）
- status: done（交互会话主审 2026-10-04 10:28 UTC：接受，提交 14dc716。08-31 翻转是数据问题，不是代码：修复前的档案 UPRO 比 SHY 高 4.7 bp，修复后低 23.7 bp，整个变化来自 SHY。主审核对"哪个 SHY 对"：修复前的 SHY 在 08-27、09-28 各有一处约 +0.30% 的批次复权接缝，修复后的序列前后一致，所以修复后的对，记入数据坑 #4。脆弱性：两份档案只在 128 个月末里的 2 个不同；5 bp 噪声下锚定窗夏普 1.817±0.028，对照 1.844；有 9% 的月末离边界不到 50 bp。C2 按修复后数据重建：锚定夏普 1.602→1.612，压力窗 0.553→0.537，对拍通过）
- priority: 1
- brief: reports/research/control/briefs/T-20261004-55.md
- goal: S3 占组合风险 89%。同一个 08-31 调仓，模拟盘（09-18 数据）选 UPRO，修复后的研究引擎选 SHY；两条代码路径在当前数据上逐位一致（54 个会话 0 差异）。要定性：是数据翻转还是代码分歧，并量化 S3 月度信号对小数据扰动的脆弱性。另外把 C2 存档按修复后数据重生成为新文件，并重做对拍。
- done_when: `reports/research/program/paper-consistency-2026-10-04/{report.md,s3_flip.json,s3_fragility.json,c2_regen.json,c2-parity.json}` 已提交，标"待主审"。
- notes:
  - 2026-10-04 10:08 UTC 交互会话（Opus）登记。顺带：10:03 一次临时运行 `check_rotation_overlay_parity.py` 覆盖了续期证据 `reports/paper/renewal/2026-09-23-overlay-parity.json`（被 gitignore，无法恢复）。已按原窗口在当前数据上重生成，结论同原件：388 个会话 0 差异。文件里加了 provenance，脚本加了 `--out/--force`，不带 `--force` 不会再覆盖。

  - 2026-10-04 10:28 UTC 交互会话主审（Opus）裁定：
    - S3 九月比回测少 3.75% 记为数据缺陷造成的执行偏差，不算策略证据。今后评 S3 的前向表现时扣除这一段并注明。
    - C2 以后的研究用 `returns.sip-repaired-20261002.parquet`；旧文件保留作历史记录。
    - S3 规则不改。"离边界近的月份按差距分配仓位或加缓冲"作为 S3 第二版或配置第二版的候选，由主审轮预注册后再测；不靠事后看结果改。
### T-20261004-56 数据：8-K 受理时间修复的下游（PM 建表器的二次撤销、sue_8k_visible 重建、T-14 gate_b 是否受影响）
- status: done（待主审）
- priority: 3
- not_before: 无（轻任务；不和别的重步骤并行）
- brief: reports/research/control/briefs/T-20261004-56.md
- goal: T-52 已把 earnings_events 改成真实 UTC。要修 `build_pm_earnings_events.py` 的二次撤销陷阱，重建 sue_8k_visible，核对 T-14 关闭隔夜线的 gate_b 是否用到这张表，并列出其他表里过时的时间列。
- done_when: `reports/research/program/earnings-events-timing-fix-2026-10-04/downstream.md` 和代码测试已提交，标"待主审"。
- notes:
  - 2026-10-04 10:09 UTC 交互会话（Opus）登记。旧 bug 只会让时间变晚，不会前视：已有的正面结论仍成立，对时点敏感的负面结论可能是假阴性。
  - 2026-10-06 22:07–22:20 UTC 执行轮（Sonnet 5.5）：提交 ab716c8。`build_pm_earnings_events.py` 改读真 UTC（+2 测试，25 个全过，未重跑 PM 管线）；`sue_8k_visible` 已备份（sha256 一致）并重建，11556→11605 行，95 行匹配行的 trade_date 变了（87 提前、8 推后），不是 T-52 预计的 268（268 是跨 16:00 ET 的全部 Item 2.02，只有 95 落在匹配的 SUE 行）；T-14 gate_b 不受影响（`run_t20260930_14_overnight_12m.py` 第 875–885 行只在 diag_stage 用 earnings_events，第 1326 行说明不进 gate；gate_b 来自第 191 行 `gate_b()`，结果 gate_a 真、gate_b 假，未建 rerun 目录）。过时时间列清单在 downstream.md §4。遗留：旧 sue_8k_visible 11556 行与在备份表上重建的 11571 行不同，原因未查；一行偏移 +60 天，疑似改配到另一份 8-K。产物 `reports/research/program/earnings-events-timing-fix-2026-10-04/`。待主审。


### T-20261004-57 数据：live 面板的回退市值改用 t−1 前 252 日分桶中位数（数据坑 #63 的构建器修法）
- status: ready（定时执行轮可取）
- priority: 3
- not_before: 2026-10-12（v1.2 模拟盘第一周不改 live 管线）
- brief: reports/research/program/pit-audit-2026-10-04/live-builder-proposal.md（T-54 的建议，按它做）
- goal: 让 live 面板的历史可复现：今天的年内中位规则每天都会改写 2026 年早期的行。live 在 D 的值本来就时点正确，T-54 测得改法对 M0 没有实质影响。#62（按申报日建梯）不在本任务，等下次动 SEC 构建器时一起做。
- done_when: `build_equity_book_panel.py` 加开关（默认新规则，研究快照不重建），测试覆盖 round-half-even 分桶；live 根按新规则重建 2026 年后跑 `scripts/check_live_book_parity.py`，目标权重相关仍 ≥ 0.97；已提交，标"待主审"。
- notes:
  - 2026-10-04 16:32 UTC 交互会话（Opus）登记。T-54 发现分桶实际是 round-half-even(adv_rank/250)，不是整除；年中位规则能 100% 复现快照（2016–25）。


### T-20261004-58 组合配置第二版合同：夏普优先、单条 sleeve 风险上限（主审轮写合同，执行轮跑）
- status: done（执行轮 2026-10-06 17:02 UTC；结果待主审）
- priority: 1
- not_before: 2026-10-06 10:00 UTC（简报第 0 步：T-32 的 results.json 有 pilot_limit 才开始；T-31 可缺，缺时按 h=0.5 并标 t31_pending）
- brief: reports/research/control/briefs/T-20261004-58.md
- goal: T-30 显示，按 T-43 权重 S3 占组合风险 89%，有效下注 1.25。同波动口径下 T-43 夏普 1.89，单用 S3 是 1.84，分散几乎没起作用；四条倒数波动加 F1 是 2.49 对 1.74，但在 2018–2023 补充窗里加 F1 更差（0.33 对 0.46）。T-55 显示 S3 有 9% 的月末离判断边界不到 50 bp，单月翻转就是 3 倍杠杆和现金的差别。机主的规则：回撤约 30%、收益优先、改进要在同波动下提高夏普。要回答：在回撤 30% 的约束下，按夏普优先的配置加单条风险上限，能不能在同波动下赢过 T-43，以及赢多少。
- plan: 由主审轮设计。要点：
  - 输入用修复后的数据（C2 用 `returns.sip-repaired-20261002.parquet`；v1.2 按数据坑 #60 移到实现日）。
  - 候选：风险平价、限风险份额的均值方差、T-43 原样。
  - 检验：同波动配对比较，判定窗口用近期，2018–2023 只看崩溃风险。
  - 安慰剂：随机权重。
  - 杠杆上限按 Alpaca 保证金，不超过 2 倍。
  - "S3 离边界近时按差距分配或加缓冲"作为另一个候选族，单独预注册。
- done_when: 合同冻结（direction-check、iteration validate 都过），执行轮跑完，主审给出是否替换 T-43 的结论。
- notes:
  - 2026-10-06 16:43 UTC 执行轮（Sonnet）开始；前置 T-32 已 done（2e6e7c4），本机 run_capped 1.2G。
  - 2026-10-06 17:02 UTC 执行轮完成（待主审）：提交 487a414；产物 reports/research/iterations/t20261005_p4_alloc_v2/{results.json,report.md,trial-ledger.json,build.json,weights-latest.json}、scripts/run_alloc_v2_t58.py、tests/test_alloc_v2_t58.py（10 项过）。results.json decision：小资金组和 1M 组均 keep_p0；无 D1 通过者（8 条规则压力期 blend ΔSR 全为负，−0.056 至 −0.654；近期 +0.07 至 +0.23，最高 IV_E4 近期 +0.233、压力期 −0.260）；CAP2 无可采纳档位（D2(b) 全部不过）。输入按 T-32 的 CAP 0.10 配置（S3*/C2*/S1*/S2*）。恒等 I1/I2 差 0.0，I3 n/a（T-32 缓存只有 5 偏移混合）。50k 可部署 P0：k*=0.75，近期年化 0.406，全期最大回撤 −0.292；P0-S3（A2 参照，l1_eligible）k*=0.50，年化 0.365，全期 MDD −0.277。需主审核对：①2x 成本口径简报与合同不一致，两种都算了（cost2x_delta_recent 与 cost2x_delta_recent_cacheblend，ERC_E4 −0.001 对 +0.168），状态都是 keep_p0；②"最小资金"k* 条件按"至少留一条 sleeve"解读；③子代理多加了 E2（S3,C2）CAP2 安慰剂族；④build.json 的 code_sha256 过期（脚本后来格式化），results.json 是最终哈希。子代理模型 claude-sonnet-5-5。
  - 2026-10-05 19:35 UTC 19:07 主审轮（Opus）：合同 `reports/research/iterations/t20261005_p4_alloc_v2/`（hypotheses.md，direction-check 和 pre-backtest 都 ok，19:33:46Z 冻结）。8 个候选：CAP2 0.80/0.70/0.60/0.50（只在 S3*、C2* 两条上设 S3 风险份额上限）、ERC/IV 在 E4（S1–S3、C2）和 E6（加 F1、F2，只有 100 万档）；对照 P0 = 0.642 S3 + 0.358 C2（T-43 在 100 万以内任何档位都不可行：F1、F2 子仓低于约 25 万）。D1 替换：同波动夏普两窗都 +0.10（混合和偏移中位数）、≥4/5 偏移、200 组随机权重安慰剂 ≥80 分位、2 倍成本不为负；D2 集中度政策：近期代价 ≥ −0.10、压力期 ≥ −0.05、六段压力片段或压力期 ES 有好处，取最紧一档；否则 keep_p0。可部署版本按 4 个资金档位 × 现金/保证金账户（Alpaca：3 倍 ETF 维持 75%、其他 30%、初始 50%、借款 6.5%/360）、最低资金（ETF 1 万、F 25 万）和全期回撤 ≥ −30% 缩放；按 DSR 打折的回撤分位数（三情景、126/252 会话）给机主对照 30%，95%/99% 分位就是减半线和停止线。功效：近期 ΔSR 标准误 0.19–0.47（ρ 0.95–0.7），0.10 是政策门槛。先验：D1 约 12%，D2 约 55%，keep_p0 约 33%；现金账户里分散规则近期年化低于 P0 约 85% → 账户类型很可能要机主定。S3 离边界缓冲族移到 P2 单独预注册。结果 10-07 22:00 前，10-08 01:07 主审轮审核。
  - 2026-10-04 16:51 UTC 交互会话（Opus）登记。T-43 是事先定好的规则机械选出的，不事后改；第二版是新合同。
  - 2026-10-05 06:47 UTC 交互会话（第二版计划 D7 第 5 节、第 9 节）：合同加三项，10-08 交付。(1) 最低资金约束：每条子策略分到的资金不低于它过 V2 所需的最低资金（V2 的量化已写进标准 vetoes.whole_share_*；各条的最低资金见 T-71 的 capacity-live-2026-10-07），达不到的在该资金档位里权重设 0 或换成小资金版；资金档位 5 万、10 万、25 万、100 万美元各给一套权重。(2) 按 DSR 打折后、按模拟分布的回撤分位数（标准第 6 节），供机主对照 30%；ETF 四条的 DSR 用 T-20261005-31（10-08 00:00 前）。(3) 主题上限取 T-20261005-32 的结果（10-07）。
- notes: 2026-10-06 01:22 UTC 01:07 主审轮：结果之前加修正案 A2（`reports/research/iterations/t20261005_p4_alloc_v2/amendment-A2.md`，简报顶部有指针）：可部署版本加 l1_eligible（含 S1 或 C2 为 false）；加部署参照 P0-S3（100% S3*，用 T-32 的 pilot_limit_s3），同口径给资金档位、账户、减半线和停止线，不是候选、N 仍为 8；D1/D2 不变。

### T-20261004-70 实盘快速通道 A1：拼接前向记录（09-01 起，分段标注；前向 z、跟踪差、哈希链）
- status: ready（2026-10-05 19:07 主审轮审核：本阶段接受；按冻结规则，v1.2 影子段从 10-02 起，下一次延长在 10-08 22:00 以后）
- priority: 1
- not_before: 2026-10-08 22:00 UTC（v1.2 模拟盘 10-07、10-08 两个会话之后；只做一次延长，简报不变，另加下面 notes 里的两项核对）
- brief: reports/research/control/briefs/T-20261004-70.md
- goal: 机主 10-04：模拟盘测试从 09-01 算，加两周真实模拟盘。评判标准 v2.1 的 L1 要每个候选（S1–S3、C2、v1.2 F1/F2、T-43 组合）有分段标注的日净收益记录：设计时看过、样本外影子、模拟盘。
- done_when: `reports/research/program/forward-record-2026-10-06/` 的 record.csv、summary.json、hash_chain.jsonl、README.md 已提交，标"待主审"。**10-06 22:00 UTC 前**。
- notes:
  - 2026-10-05 19:35 UTC 19:07 主审轮（Opus）审核 e653f6d：(1) 切分口径用简报写定的冻结规则（`t20261002_book_v12/hypotheses.md` 首次提交 10-02 05:35 UTC → 看过到 10-01），F1/F2/T-43 的样本外影子目前 0 天，影子段是 10-02..10-06，模拟盘从 10-07 起；09-16..09-30 那 11 天是"回测没用、但冻结前已经看得到"，只作参考，不计入 L1 的前向长度（不在看到结果后改口径）。(2) 重跑漂移我按日期归因：F1、F2 几乎每天都有 >1e-6 的差，最大的在 2026-09-11（0.0013/0.0032）、08-25、2025-12-30、06-17，都在 2026 年归档修复的日子附近；全期夏普存档对重跑 F1 1.042 对 1.048、F2 0.909 对 0.912，相关 0.9998，不影响任何结论，接受。(3) 引擎 net_pnl 停在 09-30，而 live 根 `_freshness.json` 已到 10-02；下一次延长时查清是 t+1 收盘成交加实现日滞后造成的，还是 live 面板缺行，写进 README。(4) 衰减规则四档阈值的校准改由 T-58 第 7 节的回撤分位数给出账户层的减半线和停止线；单个候选的前向 z、概率夏普阈值在 10-06 19:07 主审轮（P4）写。目标权重每日存档仍归交互会话。
  - 2026-10-05 17:03 UTC 执行轮 a595acf1（子代理 sonnet-high，提交 e653f6d；第一次尝试因可用内存 <700 MB 的保守闸门未跑，约 16:33 可用内存 990 MB 后重试）：v1.2 `book` 在 `run_capped --mem 1.0G` 下跑完（/tmp/t70_book_shadow.parquet，2017-10-02..2026-09-30），`assemble` 重写 record.csv（+33 行）、summary.json、README.md；hash_chain.jsonl 未变（脚本验证 0 断链），pytest tests/test_forward_record_t70.py 通过（我复跑 10 个通过）、ruff 通过。数字（子代理报告，取自 summary.json `candidates.<X>.alt_boundary_backtest_data`，按回测数据边界 09-15 切分，我核对了设计时看过段的累计收益与天数：F1 +0.275%、10 天）：影子 09-16..09-30（11 天）F1 −0.119%、F2 +0.791%、T-43 +0.363%；前向 z 全期/近期 F1 −0.33/−0.49、F2 +0.02/−0.07、T-43 −0.17/−0.37。验收未全满足：(1) 按冻结规则（冻结提交 2026-10-02 前最后一个交易日）切分，影子天数为 0（`primary_boundary_commit`，record.csv 里 F1/F2/T43 只有 design_seen 各 21 行，影子段只在 summary 的 alt 边界里）；(2) v1.2 引擎 net_pnl 只到 09-30，缺 10-01、10-02，原因未查，未改引擎；(3) 重跑与已存文件不逐位一致，最大绝对差 F1 0.00132、F2 0.00317、T-43 0.00337（`consistency_checks`）；(4) 无模拟盘段（v1.2 10-07 才开始）。S1–S3、C2 段不变。待主审：影子/设计时看过的切分口径选哪一个、10-01/10-02 缺口、重跑漂移。待主审。
  - 2026-10-05 16:09 UTC 执行轮 a595acf1（Sonnet 5.5）开始：续跑 v1.2 影子段（book）并 assemble；status 暂为 running
  - 2026-10-05 04:09 UTC 执行轮 2c717355 开始（sonnet-high 子代理前台）
  - 2026-10-04 18:17 UTC 交互会话（Opus）登记。计划 `docs/plan-owner-feedback-2026-10-04.zh.md` A1。设计时看过的段不算样本外证据。

  - 2026-10-05 05:56 UTC 执行轮 2c717355（子代理 sonnet-high，提交 ebee03d）：`reports/research/program/forward-record-2026-10-06/` 的 record.csv（122 行）、summary.json、hash_chain.jsonl（90 行，子代理独立重算 0 断链）、README.md（含四档衰减规则草案，阈值全部"待主审校准"）已提交；脚本 `scripts/forward_record_t70.py` + `tests/test_forward_record_t70.py` 测试通过。S1–S3、C2 三段齐全（累计收益 设计时看过/影子/模拟盘：S1 +0.91%/+0.28%/+1.55%；S2 +0.52%/+0.71%/+3.50%；S3 −1.48%/−0.15%/+1.70%；C2（冻结 09-25）+0.48%/−0.67%/+0.39%；数字取自 summary.json，子代理报告，我抽查了文件结构，未逐项重算）。F1/F2/T-43 只有 09-01..09-15 设计时看过段（F1 +0.27%、F2 −1.42%、T-43 −1.55%）。v1.2 影子重跑（读 live 根，写 /tmp）因机器负载 8–15、本进程只拿到 6 CPU 分钟/90 分钟，没跑完，已停；续跑命令：`scripts/run_capped.sh --mem 1.0G -- uv run python scripts/forward_record_t70.py book`，完成后 `uv run python scripts/forward_record_t70.py assemble /tmp/t70_notes.md`（备注文件 /tmp 下，丢了就重写）。发现：(1) S3 九月差是数据翻转（修复后 SIP 档案持 SHY、模拟盘持 UPRO，T-55 §1），不是执行；(2) S2/S3 的波动叠加 09-24 才进模拟盘（预注册 09-22），09-21..09-23 的跟踪差是规则差，严格说 S2/S3 影子日 09-18 也算看过；(3) 每个 sleeve 的 `reports/execution/*-target-weights.json` 每天被覆盖，哈希链只覆盖最新状态，要每日存档需改模拟盘管线（未动）；(4) 预修复档案只到 09-17，修复前 S3 信号的跟踪差分解没做。本机负载高，10-06 22:00 前续跑 F1/F2/T-43 需要在安静时段。待主审。
  - 2026-10-05 07:56 UTC 07:07 主审轮（Opus）审核：从 record.csv 逐段重算累计收益，S1–S3、C2 全部与 summary.json 一致（S1 +0.91%/+0.28%/+1.55%，S2 +0.52%/+0.71%/+3.50%，S3 −1.48%/−0.15%/+1.70%，C2 +0.48%/−0.67%/+0.39%）；S3 前向 z（全期 −0.03、近期 −0.23）在噪声内，模拟盘段波动 26.0% 对影子 12.4% 来自 T-55 的数据翻转（模拟盘持 UPRO、修复后档案持 SHY）。已交部分接受。剩余：下一执行轮在本机安静时续跑 `scripts/run_capped.sh --mem 1.0G -- uv run python scripts/forward_record_t70.py book`，再 `uv run python scripts/forward_record_t70.py assemble /tmp/t70_notes.md`（备注文件丢了就按 README 的"发现的问题"重写）。衰减规则四档阈值的校准、目标权重文件每日存档（哈希链只覆盖最新状态，要改模拟盘管线）交 19:07 主审轮（P4）和交互会话；S2/S3 的 09-18 影子日按严格口径也算看过，已在 README 注明。
### T-20261004-71 实盘快速通道 A3：v1.2 在实盘资金下的容量（集中版预注册）
- status: done（2026-10-05 06:07 UTC 交互会话审核通过并提交）
- priority: 1
- not_before: 无（改范围后不再等机主）
- brief: reports/research/control/briefs/T-20261004-71.md
- goal: 100 万美元时约 1784 名、每名约 560 美元；资金小时低于最小下单额。算原样能不能上，不能就预注册并测前 100/200/300 名的集中版，报同波动净夏普损失。
- done_when: `reports/research/program/capacity-live-<日期>/` 已提交，拿到资金数后 2 天内。
- notes:
  - 2026-10-04 18:17 UTC 交互会话（Opus）登记。
  - 2026-10-05 05:51 UTC 交互会话：按第二版计划 D5 第 5 节第 2 条和独立复核 review-1 第 0.2 节改范围，简报顶部新增一节；原第 2 步改成小资金构造，另开任务（10-08 至 10-14）。
  - 2026-10-05 06:07 UTC 交互会话审核：交付 `reports/research/program/capacity-live-2026-10-07/`。推荐起步 5 万美元、只上 ETF 子策略；ETF 四条从 1 万起可行（敞口比最低 0.942）；v1.2 的 F1、F2 子仓要约 25 万、50 万美元才过 V2。我用代码复算了 F1、F2 的整股表和按 T-43 权重折算后的账户表（账户 100 万时 F1 子仓 2.5 万，74.9% 的空头取整为 0）。PDT、碎股规则来自网页摘要，逐字核对待做。并入计划 D6 第 5 节。
  - 2026-10-05 07:23 UTC 更正（第四轮复核 review-4 第 2 节）：上一条里 F2 的"50 万"是第二轮复核的估算，已撤回。按 T-71 自己的 V2 量化（已写进标准 vetoes.whole_share_*），F1、F2 的子仓都要约 25 万美元；按 T-43 的权重相当于账户约 1,000 万和 208 万美元（计划 D7）。

### T-20261004-72 实盘快速通道 A4：实盘就绪清单和实盘下单路径
- status: blocked（等机主授权"实盘下单路径"范围变更并提供实盘账户和密钥；授权前只写清单文档，不写实盘写入代码）
- priority: 1
- not_before: 机主授权
- brief: reports/research/control/briefs/T-20261004-72.md
- goal: 失效即关闭清单（T-76 第 1 条）、分开的实盘路径、硬上限、PDT 和做空合规、先只读核对一天再下第一笔小单。
- done_when: 清单、代码、测试、`docs/runbook-live-pilot.zh.md`；**10-12 前**（取决于授权时间）。
- notes:
  - 2026-10-04 18:17 UTC 交互会话（Opus）登记。CLAUDE.md 现写明实盘写入不在范围内，必须机主明确改。

### T-20261004-73 看板改版：首页按四个问题重排，新增报告中心 /reports
- status: done（2026-10-04 18:41 UTC 交互会话验收：29881ef 已上线，/healthz 200，/、/reports、/paper、/research 均 200，首页热缓存约 0.3 秒；看过手机深色截图，四个问题按顺序回答。小问题：整页截图里底部导航条压住了钱那一块，需要在真机确认，留到第二轮）
- priority: 2
- brief: reports/research/control/briefs/T-20261004-73.md
- done_when: 10-05 06:00 UTC 前截图在 `docs/cockpit-screens/v5/`；10-06 12:00 UTC 前合入并上线。
- notes:
  - 2026-10-04 18:17 UTC 补登记（17:52 派出）。数据层只复用 `owner_digest`；594d18f（10-04 18:03 UTC）起 `owner_items`（只含机主要做的事）与 `ops_items`（运行异常）已分开，首页"要我做什么"用前者。

### T-20261004-74 交易频率 C1：S1–S3、C2 的月/周/日频率阶梯（日频加不交易带）
- status: hold（2026-10-04 18:33 UTC 交互会话暂停，定时轮不要取。原因：机主 10-04 晚指出，便宜测试对需要一定深度才见效的方向会给出假阴性。这一项将由第二版计划 T-20261004-84 重新设计）
- priority: 2
- not_before: 无
- brief: reports/research/control/briefs/T-20261004-74.md
- goal: 回答机主"为什么都是周频月频"：同一信号日频更新加不交易带，扣成本后净夏普升还是降；顺带检验 S3 的调仓日运气。先预注册再跑，20 格按多重检验口径报。
- done_when: `reports/research/iterations/t20261004_74_frequency_ladder/` 的 prereg、results、report 已提交，标"待主审"。**10-07 22:00 UTC 前**。
- notes:
  - 2026-10-04 18:17 UTC 交互会话（Opus）登记。变好的不直接替换现役，交 D2/T-58 做候选。

### T-20261004-75 稳健性 D1：集中度和市场状态诊断（半导体问题）
- status: done（2026-10-05 19:07 主审轮审核：接受，只作诊断）
- priority: 1
- not_before: 无
- brief: reports/research/control/briefs/T-20261004-75.md
- goal: 每个子策略、v1.2、T-43 组合：对 SPY/QQQ/正交化 SMH 回归，按持仓算半导体贡献，剔除半导体后的表现，按大盘和半导体状态分开的夏普，六段压力片段。只诊断，改法在 D2 和 T-58 预注册。
- done_when: `reports/research/program/concentration-regimes-2026-10-06/` 已提交，标"待主审"。**10-06 22:00 UTC 前**。
- notes:
  - 2026-10-05 19:35 UTC 19:07 主审轮（Opus）审核：checks 全过（贡献加总对引擎 ≤ 1.4e-17，record.csv 交叉 ≤ 5e-9，T-43 用修复前 C2 重建差 0）。我独立重算 T-43 夏普（program_returns.parquet 减 BIL）：全期 1.019、近期 1.635、压力期 0.630，与 results.json 一致；VIX<15 近期格 n=76、夏普 −2.90 一致。数字：S3 近期 SMH 正交 beta 0.865（t 8.2）；半导体占毛贡献 S3 近期 0.924、全期 0.712、压力期 0.399，T-43 近期 0.805；去掉半导体 ETF 后 S3 近期 1.58→0.82、压力期 0.59→0.67，T-43 近期 1.64→0.96、压力期 0.63→0.69（近期靠半导体，压力期半导体略拖累）；T-43 固定权重下 S3 风险份额近期 0.900；F1 与 S3 近期相关 −0.17，是唯一的分散来源。VIX<15 负格不是只有 2024-07：去掉 07-10..08-07 后 n=68、夏普 −1.62，但 t 约 −0.8，又是 11 个状态 × 7 个对象里挑出来的，只记作 P2 阶段 2 的待检假设，不是证据。窗口按简报用 2024-07 起，不是冻结对标窗 2024-01-08。待核对项照旧（XLK 穿透用今天的持仓、QQQ/TQQQ/SPY/UPRO 内的半导体没计入，S3/C2 份额是下限）。用途：T-58 的输入和 P2 阶段 2 的状态候选。
  - 2026-10-05 16:32 UTC 执行轮 a595acf1（子代理 sonnet-high，提交 977f986）：`reports/research/program/concentration-regimes-2026-10-06/` results.json + report.md、脚本 `scripts/concentration_regimes_t75.py` + 8 个测试（子代理报告通过，ruff 通过）已提交；我核对了 results.json 的顶层结构（7 个对象 S1/S2/S3/C2/F1/F2/T43、六个压力片段、item2/item3/回归/状态格均在），数字未逐项重算。子代理报告：S3 近期 SMH 正交 beta 0.86（t 8.2）、半导体 ETF 占毛贡献 92.4%、剔除后近期夏普 1.58→0.82；S2 半导体占比约 42%（含 XLK 穿透 47.8%）；S1/C2/F2 是大盘 beta，F1 无半导体暴露；T-43 的 S3 风险占比 90.0%；近期 VIX<15 的 76 天里 S2/S3/C2/F2/T-43 夏普为负。偏差：(1) program_returns.parquet 只有 T-43 一列，S1–S3 由缓存的 ETF 面板（/tmp/t75）重算，C2 取修复后文件；(2) 第 3 项在可用内存约 1024 MB（低于我写的 1200 MB 闸门）时跑，700M cap 内没换页，已在 report 注明；(3) T-43 原文件用修复前 C2，表 3 用修复后 C2 重建对比。待核对项：F1/F2 的半导体贡献和第 3 项（个股账本，n/a）、QQQ/TQQQ/SPY/UPRO 里的半导体（S3、C2 占比是下限）、XLK 半导体占比用今天的持仓（45.95%，SSGA 2026-10-02）套全历史（偏高）。待主审。
  - 2026-10-05 16:09 UTC 执行轮 a595acf1（Sonnet 5.5）开始（子代理前台）
  - 2026-10-04 18:17 UTC 交互会话（Opus）登记。机主 10-04：半导体周期可能已过，要从大盘和择时角度看，剔除过于明显的相关性。

### T-20261004-76 调研：GitHub 近期热门 vibe trading / AI 交易项目
- status: done（交互会话审核，2026-10-04 18:17 UTC 登记：接受，提交 9be902b。星数取自 GitHub API；32 个项目，没有一个给出扣成本、截止日后、可核验的盈利证据；借鉴的 5 条已分进 T-70、T-72、T-79 和 B 线）
- priority: 2
- brief: reports/research/control/briefs/T-20261004-76.md
- notes:
  - 独立 Paseo 代理 f627dd9d（Sonnet 5.5 high），17:49 派出，18:06 交付。X 渠道因 twscrape 未装而空缺。

### T-20261004-77 方法检验：拓扑和相关结构风险信号（G1）、路径签名特征（G2）、残差随机矩阵诊断（G3）
- status: hold（2026-10-04 18:33 UTC 交互会话暂停，定时轮不要取。原因：机主 10-04 晚指出，便宜测试对需要一定深度才见效的方向会给出假阴性。这一项将由第二版计划 T-20261004-84 重新设计）
- priority: 3
- not_before: 2026-10-08（等 T-75 的状态划分）
- brief: reports/research/control/briefs/T-20261004-77.md
- goal: 回答机主"流形、拓扑、物理建模能不能做"：证据见 `reports/research/intel/I-20261004-03-geometry-physics-methods-and-jane-street-playbook.md`。不作主攻；G1 必须胜过平均相关加已实现波动这个简单基线，G2 必须胜过同数量随机特征。
- done_when: 预注册冻结，执行轮跑完，主审给出保留或否定；否定的写进 directions.jsonl。**10-14 前**。
- notes:
  - 2026-10-04 18:17 UTC 交互会话（Opus）登记。
  - 2026-10-06 17:10 UTC 交互会话（Opus）：G1（拓扑和相关结构）由 T-20261006-20 取代，G2（路径签名）并入 T-20261006-19，G3（随机矩阵）作为风险模型基线在 T-19 采用。本任务保持 hold，不再单独执行。

### T-20261004-78 调研：顶级量化机构的公开分享和竞赛冠军方案（机主上传的 Jane Street AI 手册的延伸）
- status: running（独立 Paseo 代理 394eace8，Sonnet 5.5 high，协调码 R1004-T78）
- priority: 2
- brief: reports/research/control/briefs/T-20261004-78.md
- done_when: `reports/research/intel/I-20261004-04-practitioner-disclosures-survey.{md,json}` 和快照目录，10-05 06:00 UTC 前；交互会话审核后提交。
- notes:
  - 2026-10-04 18:17 UTC 交互会话（Opus）登记并派出。PDF 本身的评估已在 I-20261004-03 第 2 节。

### T-20261004-79 时间合同：三个时钟（received_at）、截断不变性测试、LLM 记忆检查进 llm_contribution_pass
- status: ready（定时执行轮可取）
- priority: 3
- not_before: 2026-10-12（v1.2 模拟盘第一周不改 live 数据管线）
- brief: reports/research/control/briefs/T-20261004-79.md
- goal: 来自 T-76 第 3 条和 Jane Street 播客：更强的模型更会利用前视泄漏；LLM 记忆是真问题。
- done_when: 代码、测试、`reports/research/program/time-contract-<日期>/report.md` 已提交，标"待主审"。10-16 前。
- notes:
  - 2026-10-04 18:17 UTC 交互会话（Opus）登记。

### T-20261004-80 调研（第二版计划输入）：中频交易做到什么程度才有效
- status: done（2026-10-04 18:57 UTC 交互会话审核：接受。主攻：成本感知的残差多信号短期统计套利，500–1000 只，持有 3–10 日，部分调仓，叠在 v1.2 上。执行：换仓从开盘移到收盘，开盘半价差是收盘的 3.2–4.9 倍。最大缺口是 2022 年以后没有净值证据，阶段 1 补）
- priority: 1
- brief: reports/research/control/briefs/T-20261004-80.md
- done_when: `reports/research/intel/I-20261004-05-mid-frequency-depth.{md,json}` 和快照目录，10-05 02:00 UTC 前；交互会话审核后提交。
- notes:
  - 2026-10-04 18:35 UTC 交互会话（Opus）派出。机主 10-04 晚：便宜测试会漏掉需要一定深度才见效的方向；要先调研别人怎么做。

### T-20261004-81 调研（第二版计划输入）：状态模型、主题集中、半导体周期做到什么程度才有效
- status: done（2026-10-04 18:57 UTC 交互会话审核：接受。先做主题风险预算，再做在线跳跃模型状态层（回撤控制，不是收益来源）。半导体周期指标只做条件器和监控；韩国 9 月芯片出口 603 亿美元、同比 +263% 已对快照核实。朴素的'出口好就买'方向相反）
- priority: 1
- brief: reports/research/control/briefs/T-20261004-81.md
- done_when: `reports/research/intel/I-20261004-06-regime-theme-cycle-depth.{md,json}` 和快照目录，10-05 02:00 UTC 前；交互会话审核后提交。
- notes:
  - 2026-10-04 18:35 UTC 交互会话（Opus）派出。机主 10-04 晚：便宜测试会漏掉需要一定深度才见效的方向；要先调研别人怎么做。

### T-20261004-82 调研（第二版计划输入）：物理、几何、拓扑、深度序列模型做到什么程度才见效
- status: done（2026-10-05 04:36 UTC 交互会话审核：接受。值得深做的三项：随机特征 SDF 的复杂度曲线，签名预测波动（样本外 R² 0.361 对 HAR-RV 0.224，已对快照核实），多期限辅助目标（RankIC 0.049→0.075，已核实）。动态模态分解、Koopman、拓扑作 alpha 暂不投入，附重开条件。10-04 22:30 会话额度中断，10-05 04:35 恢复后完成）
- priority: 1
- brief: reports/research/control/briefs/T-20261004-82.md
- done_when: `reports/research/intel/I-20261004-07-physics-geometry-deep-models-depth.{md,json}` 和快照目录，10-05 02:00 UTC 前；交互会话审核后提交。
- notes:
  - 2026-10-04 18:35 UTC 交互会话（Opus）派出。机主 10-04 晚：便宜测试会漏掉需要一定深度才见效的方向；要先调研别人怎么做。

### T-20261004-83 调研（第二版计划输入）：2026-08 以来的 vibe trading 新项目潮（整类）
- status: done（2026-10-05 05:15 UTC 交互会话审核通过并提交）
- priority: 1
- brief: reports/research/control/briefs/T-20261004-83.md
- done_when: `reports/research/intel/I-20261004-08-vibe-trading-wave-since-2026-08.{md,json}` 和快照目录，10-05 02:00 UTC 前；交互会话审核后提交。
- notes:
  - 2026-10-04 18:35 UTC 交互会话（Opus）派出。机主 10-04 晚：便宜测试会漏掉需要一定深度才见效的方向；要先调研别人怎么做。
  - 2026-10-05 05:15 UTC 交互会话审核，交付物已在 a11bf0e 提交（md、json、46 个快照）。复查：GitHub 搜索接口重取，"alpaca agent" 2026 窗口 767、"trading agent" 2025 窗口 603，和交付物一致；DXRG 摘要（arXiv 2609.05663）核对了金库数、无方向性优势、胜率 41% 对 50%、机械出场 +39.0 bps；17 条规则和调度偏移的数字只来自转述，计划里标"先读原文"。老项目 8 月以来的新增星数没测到（stargazers 接口要认证，本机没有 gh 和令牌）。已并入计划第 3.5 节 P5。

### T-20261004-84 第二版计划：按"最低有效深度"重做，调研支撑、多轮复核后执行
- status: done（2026-10-05 第四轮复核通过，执行中；见计划第 9 节）
- priority: 1
- goal: 机主 10-04 晚的要求：
  - 不要把他的想法缩成便宜测试；效果可能是非线性的，要做到一定程度才见效；
  - 第一轮所有问题的方案都偏浅，要先调研别人怎么做；
  - vibe trading 要看整类，重点是 8 月以后的新项目；
  - 计划反复复核，直到满足他的要求，再详细执行。
- plan: 
  - 输入：T-78、T-80–T-83 的调研，加上交互会话自己做的"研究运作方式和防假阴性"调研。
  - 写 `docs/plan-v2-2026-10-05.zh.md`。
  - 复核：先按机主要求清单自审，再由独立 Opus 复核代理审，改到全部满足。
  - 然后拆成项目和任务执行。
- done_when: 计划和复核记录已提交，执行已开始，并向机主汇报。
- notes:
  - 2026-10-04 18:35 UTC 登记。T-74、T-77 已暂停，等本计划重新设计；T-70、T-75（测量和诊断）照常。
  - 2026-10-05 06:52 UTC：第三轮复核（review-3.md）判定可以执行，剩 5 条已在 D7 处理（计划第 8.3 节）。执行清单见计划第 9 节；新任务 T-20261005-30 至 -42。交互会话提交 D7、向机主汇报后改 done。
  - 2026-10-05 07:23 UTC：第四轮（review-4.md，Sonnet 独立复核）判定 5 条全部已改，R1、S8 满足，19 条要求全部满足；4 处小改已在 D7.1 改完。已向机主汇报（交互会话 07:20 的消息）。status 改 done，执行按计划第 9 节。

### T-20261004-85 调研（第二版计划候选项目 P6）：期权波动率风险溢价在 Alpaca 上能否做深
- status: done（2026-10-05 04:48 UTC 交互会话审核通过并提交）
- priority: 2
- brief: reports/research/control/briefs/T-20261004-85.md
- done_when: `reports/research/intel/I-20261004-10-options-vrp-depth.{md,json}` 和快照目录，10-05 03:00 UTC 前；交互会话审核后提交。
- notes:
  - 2026-10-04 18:46 UTC 交互会话（Opus）派出。机主 09-29 的范围包括期权 1–3 级；我们还没有期权策略，属于主动补充。
  - 2026-10-05 04:48 UTC 交互会话审核：交付物齐全（md、json、58 个快照文件）。用快照里的 Cboe 和 French 数据独立重算，2008 年起 PUT β 0.59、年化 alpha −0.30%（t −0.23）、残差波动 5.54%，2021 年起 alpha +2.51%（t 1.43），和交付物一致；夏普 0.46 对美股 0.57，交付物写 0.47 对 0.58，是口径差。并入计划第 3.6 节时改了两处：停止线按 S3 改为近期窗口决定；新增期权作选股信息源的用途。阶段 0 的快照采集我判断属于委托范围内的数据工作，不需要机主批准预算。

### T-20261006-01 修复：live 刷新停在 nsi 的不变性检查（修复过的代码键变化），v1.2 首单前必须修好
- status: done（2026-10-06 03:38 UTC，交互会话 Opus；提交 5e1f3fd、559a869；信号日 10-05 的目标已生成）
- priority: 1
- not_before: 无；**10-06 21:30 UTC 前提交**（当晚 22:45 的刷新产出 10-07 18:30 首单要用的目标）
- goal: 10-06 00:35 UTC 的 live 刷新在 nsi 表的不变性检查失败（keys_ok=false，只有新键 1620 行、只有旧键 1750 行，样本 ALP；数值变化 2,006 行全可归因、占比 0.00032），恢复备份后整条刷新停止，v1.2 的最新目标停在信号日 10-02。不修的话 10-07 首单会用旧目标或被拒。
- plan: 见简报。键变化只对 `_restatements.jsonl` 里修复过的代码放行（10-02 04:13 的 T-01 归档修复重算了 ALP、BGM、CTSO 等的全部历史，nsi 的价格断点过滤随之保留不同日期），沿用 T-02/T-22 的"变化必须能归到被替换的代码"规则；价格表规则不变，门槛不变。
- done_when: 代码和测试已提交；验证 JSON pass=true、两个未放行计数为 0；nsi 文件 sha256 复原；结果标"待主审"。
- brief: reports/research/control/briefs/T-20261006-01.md
- notes:
  - 2026-10-06 01:53 UTC 10-06 01:07 主审轮（Opus）登记。证据：`logs/refresh_equity_book_live.log` 第 480–491 行，`data/live/backup-refresh/2026-10-05/check_nsi.json`，`data/sip/daily/_restatements.jsonl`；cron 22:45 刷新、18:30 计划（只读查看 crontab）。如果当晚刷新仍失败，10-07 04:07、10:07 的执行轮还有时间重跑，首单 18:30 才计划。
  - 2026-10-06 03:38 UTC 交互会话完成。
    - **简报的时间基准不成立**：ALP 等代码的重述记录是 10-02 04:13，nsi 备份是 10-04 15:38 建的，"备份时间以后的重述"一个也放不进来。
    - **真正原因**：CMND 的重述触发重建 daily_broad 2022–2025，这几个分区是 09-18 建的，于是把 10-02 的修复一起带了进来（坑 #64）。
    - **nsi 的规则**：只放行在被替换分区建成以后、有拆分级或行数级重述的代码，实测 88 个。只有 nsi 和 sec_fundamentals_daily 两张表适用，因为它们的行跟着价格走。
    - **nsi 验证**：在 /tmp 重建，live 文件 sha256 不变；pass，未放行键 0/0，变化占比 0.00032。
    - **备份**：改成每天只取一次，重跑同一天时保留当天的原始文件。
    - **short_interest 第二次停下**：`adv_shares_63` 是用价格水平值算的，比价格表本身的门更严（坑 #65）。修法是门跟着价格表走：只比到最后一天减 3 个交易日，排除在价格分区建成以后有重述的代码。实测排除 116 个，其余变化为 0。
    - **重跑结果**：用 `--tables` 补完剩余几张表，03:35 exit 0，游标推进到 7442。VIX 已取到 10-05。
    - **目标**：F1 sha256 d50d84be…，F2 79c46ce4…，1,784 个名字（多 1,091、空 693）。QRVO 10-05 没有收盘价被丢弃，SIP 最后一根 K 线是 10-02。
    - **跟进**：重建 2016–2021 排为 T-20261006-02。02:45 的全量 pytest 和刷新抢内存，22 分钟只跑到 8%，03:08 停掉；03:20 的一次性 cron 等刷新锁释放后重跑，日志在 `logs/full_pytest_20261006.log`。

### T-20261006-06 cockpit：密钥擦除在 JSON 转义后不再幂等（多行日志里的 `key=xx,` 行尾），API 测试因此误报
- status: ready（交互会话处理；不急，不影响模拟盘）
- priority: 4
- not_before: 无
- goal: `tests/test_cockpit_api.py::test_secret_scrub_is_a_no_op_on_every_response` 10-06 在 `/api/health.json` 上失败。
  - 失败原因：`/health` 的 "Log tails" 显示了全量 pytest 的日志，里面有测试源码 `key=len,` + 换行。
  - 通用规则 `...key...[:=]\s*\S{6,}` 在原文里只匹配到 `len,` 四个字符，不脱敏；JSON 编码以后换行变成 `\n`，`len,\n` 凑够 6 个字符就被脱敏，于是"擦除是空操作"的不变式被打破。
  - 这只会多脱敏，不会漏掉密钥：原文里 `token=` 换行后的值，原文擦除已经能匹配。
  - 当时的触发源是两条已执行完的一次性 pytest cron，已从 crontab 删掉，`test_cockpit_api` 和 `test_cockpit_app` 已通过。但规则本身仍然脆弱，任何多行日志都可能再触发。
- plan: 二选一，先写测试，并保证所有已有的擦除用例照旧：
  (a) 日志尾部的值不跨行：在 health 里逐行擦除，然后对 JSON 编码后的形式再检查一次；
  (b) 通用规则的值部分在 `\\n` 处截断，例如 `(?:(?!\\n)\S){6,}`。
- done_when: 新测试覆盖 "原文 `key=len,` + 换行" 和 "原文 `token=` + 换行 + 长值仍被擦除"；`uv run pytest tests/test_cockpit_*.py` 通过；make verify 的非测试步骤通过。
- notes:
  - 2026-10-06 14:50 UTC 交互会话登记。同一天另一条 cockpit 失败（/health 日志尾部含中文）已在 e60bb55 修好。

### T-20261006-02 重建 daily_broad 2016–2021（修复前的分区，坑 #64 的接缝）
- status: ready
- priority: 3
- not_before: 2026-10-08 00:45 UTC（首单当晚的刷新之后；不在 18:00–00:45 UTC 跑，不和其他超过 1 GB 的任务并行）
- goal: `data/features/daily_broad` 的 2016–2021 分区是 09-18 建的，在 10-02 归档修复之前；2022–2026 已经是修复后的版本。2021/2022 交界处有接缝：48 个代码是拆分级或行数级重述，约 4,500 个是分红级。v1.2 live 目标不受影响（历史从 2024 年起）；用 `data/features` 跑跨 2021/2022 研究的会受影响。
- plan: 见简报。用驱动自己的构建命令重建六年；用驱动的 `rebased_symbols` 和 `check_command` 逐年对比，全部通过才在刷新锁里替换，备份到 `data/live/backup-refresh/t20261006-02/`。不改任何门槛，不放宽名单。
- done_when: 六年检查全部通过且已替换（或者没有替换，并写明哪一年、为什么失败）；`reports/research/program/data-refresh-2026-10-01/daily-broad-2016-2021-rebuild.json` 已提交；结果标"待主审"。
- brief: reports/research/control/briefs/T-20261006-02.md
- notes:
  - 2026-10-06 02:42 UTC 交互会话（Opus）登记，来源是 T-20261006-01 的排查。

### T-20261005-01 P1 中频股票引擎 阶段 0：快信号的衰减曲线、交易速度与净夏普、对 v1.2 的增量（测量，只用于提速）
- status: ready
- priority: 1
- not_before: 无（本机重步骤不在 21:30–00:30 UTC 跑；不和其他超过 1 GB 的任务并行；排在 T-20261004-70、T-75 之后取即可，目标 10-05 16:07 执行轮前后跑完）
- goal: 把"频率怎么定"变成数据：快因子库 53 个、新快信号 7 个、合成 3 个，在 U3000 分流动性档上的日 IC 衰减（滞后 1–22）、半衰期、持续性，以及 7 种交易速度在实测收盘价差下的净夏普；决定哪些输入和速度进入第 2 阶段（v1.2 构造里的快腿）。机主 10-04：便宜测试只提速，不能否定；本任务不能关闭 P1。
- plan: 合同 `reports/research/iterations/t20261005_p1_s0_decay/`（hypotheses.md 第 0–10 节，01:30 冻结；direction-check 和 pre-backtest 都 ok）。先做恒等检验（复现 regimes/signal_ls_daily 三列，误差 ≤ 1e-9），再测量；ON5、ID5 的符号先由压力期定；晋级规则见合同第 5 节。本机，run_capped 1.8G，不用 Modal。
- done_when: `t20261005_p1_s0_decay/{results.json,report.md,trial-ledger.json}` 已提交（git add -f），mechanical_status 为三个值之一，新测试通过；结果标"待主审"。
- brief: reports/research/control/briefs/T-20261005-01.md
- notes:
  - 2026-10-06 16:08–16:27 UTC 执行轮（Sonnet）未取到：简报第 0 步要求可用内存 ≥ 2500 MB，实测 1809–1899 MB（本轮自身代理在内，交互和主审会话也占着），等了约 20 分钟未满足，退回 ready，没写任何产物。需要主审轮决定：放宽内存门槛，或在没有别的代理会话时跑。
  - 2026-10-05 01:33 UTC 01:07 主审轮（Opus）登记。第二版计划草稿 P1 阶段 0，即第一版计划 C2（10-09 前出第一批结果）。10-06 01:07 主审轮审核，并按结果写第 2 阶段合同（快腿进 v1.2 构造）或转阶段 1（学习式残差信号）。

### T-20261005-02 v1.2 首单前核实：收盘竞价单（time_in_force=cls）在 quant1/quant2 模拟账户能否被接受并成交（数据坑 #55）
- status: done（交互会话 2026-10-05 20:19 UTC：两户都接受 cls 单。quant1 买 1 股 SPY 在 19:59:59Z 成交，$774.78；quant2 卖空 1 股 AAPL 在 20:01:13Z 过期，成交 0。按 Alpaca 员工说明（论坛 19155 帖），这是模拟盘随机部分成交、剩余在收盘后过期的行为，不是拒单。数据坑 #55 和开始清单第 10 节 E2 已更新，`--tif-mode market` 已写好并测试，首单用哪种单在 10-06 第二次彩排后决定。10-06 18:50 的平仓探针照常：quant1 卖 1 股 SPY，因为持有 +1；quant2 不会发单，因为没有持仓）
- priority: 1
- not_before: 无；**10-07 18:45 UTC 首次提交前**完成（v1.2 开始清单第 71 行）
- goal: v1.2 的下单引擎默认用收盘竞价单（`open_composer/book_paper/plan.py` 第 1098 行 `tif = "cls" if mode == "close"`；T-20261001-16 规格），修正案 A1 的主口径也是 t+1 收盘竞价成交。Alpaca 订单文档的 TIF 表里 CLS、OPG 都标 Yes*，注明"标星的要联系销售"（快照 `reports/research/intel/sources/mid-frequency-2026-10-04/alpaca-orders-docs.txt`）；数据坑 #55（`docs/data-layer-pitfalls-and-capabilities.zh.md`）记着"OPG/CLS 可能要 Elite 权限，6 月以来出场单取消或过期与此吻合，待本账户实测"。开始清单只做了限价单撤单测试，没有测过收盘竞价单。万一被拒或被撤，10-07 首单会整批失败。
- plan: 交互会话在 10-05 或 10-06 美东 15:50 前，在 quant1 用 `oc book-paper` 的同一下单路径挂 1 股 SPY 收盘竞价市价单（或按开始清单的撤单测试方式），记录订单状态流转（accepted/new → filled 或 rejected/canceled 及原因）、成交价与当日官方收盘价之差；quant2 同样做一次（若它承担空头，加 1 股 ETB 名字的卖空 CLS）。结果写进数据坑 #55 和开始清单。被拒：首单改用引擎已有的 `--mode market`（DAY 市价单；限价收盘单在文档里同样标 Yes*，不能当退路），并评估对 A1 收盘成交口径的影响，写修正说明；实盘那边把"联系 Alpaca 销售开通 CLS"加进 T-72 的清单，作为机主要做的事。
- done_when: 数据坑 #55 改成已核实（附订单 ID 和状态），开始清单写明首单用的订单类型。
- notes:
  - 2026-10-05 01:35 UTC 01:07 主审轮（Opus）登记：设计 P1 阶段 0 的成交口径时发现，收盘竞价单在本账户从没实测过。
  - 2026-10-05 07:24 UTC 交互会话补充（解读口径）：Alpaca 工作人员 2024-08-21 写明，模拟盘的开盘竞价单按普通市价单在开盘报价成交（买用卖价、卖用买价），不是竞价价；用户报告收盘竞价单同样如此（快照 `reports/research/intel/sources/small-capital-ls-2026-10-07/alpaca-forum-moo-worse-than-open.txt` 和同目录 `alpaca-forum-opg-cls-paper-prices.txt`）。所以本探针只能证明模拟账户接不接受 cls 单，不能证明竞价成交质量；成交价对官方收盘价的差预期约半个价差，不算执行错误。实盘的竞价权限（订单文档标"要联系销售"）仍要单独确认，写进 T-72。

### T-20261005-20 v1.2 首单前：对照外部的通道失败清单（swiftward 34 条、Deflow）只读审模拟盘下单路径
- status: done（2026-10-05 06:07 UTC 交互会话审核通过并提交）
- priority: 1
- not_before: 无；10-07 18:45 UTC v1.2 首次提交前要用上结论
- brief: reports/research/control/briefs/T-20261005-20.md
- done_when: `reports/research/program/channel-audit-2026-10-06/audit.{md,json}`，10-05 12:00 UTC 前；交互会话审核后提交。首单前必须修的条目另开任务。
- notes:
  - 2026-10-05 05:17 UTC 交互会话（Opus）登记。来源：第二版计划第 3.5 节 P5 的第一项（T-83 调研 I-20261004-08 第 6 节第 2 项）。只读审计，不改代码，不调券商接口。
  - 2026-10-05 06:07 UTC 交互会话审核：63 条（swiftward 实际 35 条、Deflow 16 条、新增 12 条）；已防住 13、部分 27、没防住 6、不适用 17。首单前必须修：E1 拒单只记异常类名、提交命令仍退出 0（plan.py submit_plan、cli.py submit，交互会话已对代码核实）；E2 收盘竞价被拒时没有后备（决策）；E3 重跑覆盖第一次的回执和计划文件（已核实）。E1、E3 由交互会话修，E2 写进开始清单。

### T-20261005-31 ETF 四条子策略补登试验数并算 DSR（L1 试点提议的前提，10-08 前）
- status: done（2026-10-06 01:07 主审轮审核：接受）
- priority: 1
- not_before: 无（本机轻量；和 T-20261005-01 不冲突，但重跑回测时同一时间只跑一个）
- goal: 标准 v2.1 的 L1 要求"已是 P1 档"（DSR ≥ 0.70）。S1、S2、S3、C2 从没登记过试验数，证明不了。第二版计划第 5 节第 3 条推荐 10-15 提议 S3 加 C2 的试点；过不了 DSR 的不进提议（第三轮复核第 1 条）。
- plan: 按简报重建每条的试验族（S3 从严，补救设计看过的变体全算，数不清给区间按上界），用 `scorecard_v2.dsr` 按标准口径算近期和全期 DSR，N 做 0.5–5 倍敏感性。只测量，不改规格和门槛。
- done_when: `reports/research/program/etf-dsr-2026-10-08/{results.json,report.md,compute.py}` 已提交，10-08 00:00 UTC 前；结果标"待主审"。
- brief: reports/research/control/briefs/T-20261005-31.md
- notes:
  - 2026-10-05 06:47 UTC 交互会话（Opus）登记。来源：第二版计划 D7 第 9 节；第三轮复核 review-3.md 第 1 条。
- notes: 2026-10-05 22:30 UTC 执行轮（sonnet-high 子代理 R1005-T31，35 次调用）：交付 `reports/research/program/etf-dsr-2026-10-08/{results.json,report.md,compute.py}`。主结果 N=n_high，近期窗 2024-01-08..2026-09-17，字段核对齐全（四条都有 dsr_recent，试验族每项带来源）。S1 n 104/278 DSR 近期 0.6995、全期 0.831、跌破 0.70 的 N=276、passes_p1_dsr=false（差 0.0005，n_low 下 0.768）；S2 106/294 0.836/0.908、N=3371、true；S3 120/317 0.815/0.916、N=2270、true（5 倍 N 仍 0.722）；C2 25/47 0.566/0.342、N=24、false（n_low 下 0.691）。子代理自述最不确定：不能重跑的变体对相关取 0.5（S1–S3 占 86–88% 的对，C2 31%），S1 对此敏感（0.3→0.8 为 0.673→0.760）；S3 的 N 是下界（H-20260923-09 无变体清单，H-20260928-13 manifest 为空）。我未改任何策略、标准或门槛。待主审。
- notes: 2026-10-06 01:22 UTC 01:07 主审轮（Opus）审核：接受。从 results.json 各窗口的矩（会话数、年化超额夏普、偏度、峰度、SR0）独立重算 8 个 DSR，与报告一致到第 4 位；n_eff、var_sr 符合标准 config 的 dsr 段，序列为 5 个偏移等权、10bp、次日开盘、减 BIL，符合 offsets_blend。结论：S2 0.836、S3 0.815 过 P1 档 DSR（S3 试验数放大 5 倍仍 0.722）；S1 0.6995 不过（按主结果判；未重跑变体的相关假设 0.5 偏保守，实测约 0.64，取 0.8 时 0.760）；C2 0.566 不过（下界 25 时 0.691，全期 0.342；族内近期夏普最高 2.46、方差 0.54 是主因，C2 不是族内近期最好的）。后果：按计划第 9 节 C2 不进 L1 试点提议，试点按现有证据只有 S3；写了 T-32 修正案 A1（只含 S3 的决策对象）和 T-58 修正案 A2（L1 资格、P0-S3 部署参照），都在结果之前；live-track 已改。新发现的缺口：P1 档另要求安慰剂净分位 ≥ 0.90、稳健性 ≥ 3 项（标准 a–f）。S3 有旧口径证据（H-20260922-02 过 G3 随机挑选安慰剂，H-20260922-05 加档层日历平移安慰剂 0/20），但没按标准 v2 正式对应，稳健性也没计数；10-15 提议前补，不需要新实验（交 10-06 19:07 P4 主审轮）。

### T-20261005-32 P2 阶段 1：半导体和 AI 主题风险预算（上限版和对冲版），结果直接作为试点的集中度上限
- status: done（执行轮 2026-10-06 16:43 UTC；结果待主审）
- priority: 1
- not_before: 无（合同由主审轮写，目标 10-05 07:07 或 13:07 那一轮；执行部分本机，排在 T-20261005-01 之后，不和其他超过 1 GB 的任务并行）
- brief: reports/research/control/briefs/T-20261005-32.md
- goal: 机主 10-04 第 3 条：压力期夏普低、押注半导体太重，要"剔除过于明显的相关性"，平衡历史和当前夏普。专业做法是先限制暴露，再识别状态（I-20261004-06）。本阶段是风险政策：上限一定能用，要回答的是代价多大。结果直接成为 ETF 试点（S3 加 C2，10-15 提议）的集中度上限和 T-58 的输入。
- plan: 设计见第二版计划第 3.2 节阶段 1，合同要写定以下各项后冻结（direction-check、iteration validate --stage pre-backtest 都 ok）：
  - 主题因子：SMH 对 SPY 正交化的日收益；各子策略的主题暴露用 T-20261004-75 的暴露回归（滚动窗口在合同里写死）。
  - 两个版本：上限版（主题对组合风险的边际贡献上限，至少三档，档位开跑前写定）；对冲版（用 SMH 空头对冲主题 β；每日核对 SMH、SOXX 易借，难借就退回上限版；现金账户不能做空时，改为买入 SOXS，计入每日再平衡的衰减）。
  - 判定口径：加上限或对冲后再加杠杆回原来的波动，近期窗口夏普下降不超过 0.10（数字开跑前写定，不事后改）。同时报压力期夏普、预期短缺、2024-07、2025-04、2026-07 三次回放的回撤，以及回到原波动所需的总杠杆，Reg T 和杠杆 ETF 能不能放下。
  - 安慰剂：把"主题"换成其他行业 ETF（至少 4 个），同样的上限和对冲。
  - 不挑调仓日（标准 offsets_blend 口径）；成本按标准；近期窗口和按大盘划分的阶段决定，长历史只诊断。
- done_when: 合同冻结；结果和报告 10-07 18:00 UTC 前提交；主审轮写清给试点用的上限，live-track 和 T-58 引用。
- notes:
  - 2026-10-06 16:43 UTC 执行轮完成（待主审）：提交 2e6e7c4；产物 reports/research/iterations/t20261005_p2_s1_theme_budget/{results.json,report.md,trial-ledger.json,build.json}。results.json：mechanical_status=pilot_limit_selected，pilot_limit={CAP, c=0.10}，alternatives=[]；S3 单独（A1）同为 CAP 0.10。O1 CAP 近期同波动 ΔSR：0.40 +0.025、0.30 +0.009、0.20 −0.043、0.10 −0.089；0.10 档只过 replay 分支，压力期 ES 比 1.027 >1，cost_ok 对 H1F 0.10 不过；H2F、H1F 无选中档。运行 123 s、峰值 249 MB；子代理模型 claude-sonnet-5-5。数据最后会话 10-05（简报预期 10-02）。待主审：0.10 档只靠 replay 分支通过、压力期 ES 反而变差，是否采纳。
  - 2026-10-06 16:27 UTC 执行轮（Sonnet）开始，本机 run_capped 1.0G（T-01 因内存门槛未满足先让位）。
  - 2026-10-05 06:47 UTC 交互会话（Opus）登记。来源：第二版计划 D7 第 3.2 节阶段 1、第 9 节。最低有效深度：上限三档、两个版本、行业安慰剂；只做一档或只做上限版不算完成。
  - 2026-10-05 07:56 UTC 07:07 主审轮（Opus）写合同和简报：`reports/research/iterations/t20261005_p2_s1_theme_budget/`（direction-check ok，pre-backtest 07:48 ok，07:53 按计划 D7.1 把试点改成 S3 0.642 + C2 0.358 后重验 ok）。主题因子 = SMH 对 SPY 正交化（126 日窗），主题风险份额 TRS = Euler 因子份额；四档 0.40/0.30/0.20/0.10 × 三版（CAP 换成同杠杆标普 ETF；H1F 做空 SMH 加做多 SPY，按 Alpaca 保证金规则截到可行；H2F 现金账户买 SOXS 加 UPRO）= 12 个决策配置；判定：同波动近期 ΔSR ≥ −0.10、R1–R3 回放或压力期 ES 有好处、单调，取最紧一档；8 个行业 ETF 安慰剂只报告。先验：最可能 no_level_within_cost（约 55%），因为 H-20260923-09 显示 S3 的夏普主要来自 SOXL。执行本机轻量（--mem 1.0G），按 not_before 排在 T-20261005-01 之后，不和其他超过 1 GB 的任务并行。
- notes: 2026-10-06 01:22 UTC 01:07 主审轮：结果之前加修正案 A1（`reports/research/iterations/t20261005_p2_s1_theme_budget/amendment-A1.md`，简报顶部有指针）：同一判定规则对对象 S3 再算一次，写 decision_s3、pilot_limit_s3 等字段；不加路径、配置、门槛。原因：T-31 C2 DSR 不过，L1 试点只剩 S3。已跑完的话由脚本从 results.json 机械补算。

### T-20261005-30 开盘竞价单（time_in_force=opg）在 quant1/quant2 模拟账户能否被接受并成交（P1 阶段 3 的前提）
- status: running（交互会话；定时轮不要取）
- priority: 2
- not_before: 无；**10-06 美东开盘前**提交（10-07 v1.2 首单之后账户里有持仓，探针会混进账本，所以只在 10-06 做）
- goal: P1 阶段 3（执行时点）和 ETF 试点的下单说明都要知道开盘竞价单能不能用。Alpaca 文档对 OPG 和 CLS 都标"联系销售"（数据坑 #55）。收盘竞价单由 T-20261005-02 测；本任务测开盘。
- plan: 交互会话扩展 `scripts/book_paper_cls_probe.py`：10-06 约 13:00 UTC，quant1 买 1 股 QQQ（OPG），quant2 卖空 1 股 MSFT（OPG）；13:45 UTC 查状态；成交后约 13:50 UTC 用当日市价单平掉，14:05 UTC 再查。用和 CLS 探针不同的标的，不影响 10-06 18:50 的 CLS 平仓条件（SPY +1、AAPL −1）。
- done_when: 数据坑 #55 加上 OPG 的结果（订单 ID、状态流转、成交价对官方开盘价），两户在 14:30 UTC 前回到探针前的持仓。
- notes:
  - 2026-10-05 06:52 UTC 交互会话（Opus）登记。来源：第二版计划 D7 第 3.0 节排期、第 9 节。
  - 2026-10-05 07:13 UTC：探针脚本加了 `--tif opg|day`（8543214，cls 的订单号和日志名不变，测试通过）。10-06 的 cron 已装（只在 20261006 触发）：12:40 只读账户和标的、12:45 两户各一张 OPG 单（quant1 买 QQQ，quant2 卖空 MSFT）、13:40 查状态、13:45 用当日市价单平仓（要求持仓正好 +1/−1）、14:00 查状态；日志 `logs/opg_probe.log`，记录在 `reports/paper/book/<账户>/probes/2026-10-06-{opg,day}-probe.jsonl`。10-06 交互会话或 19:07 主审轮读结果，写进数据坑 #55。
  - 2026-10-05 07:24 UTC：同上，模拟盘的 opg 单按开盘报价成交，不是开盘竞价价；本探针只证明接不接受 opg 单。

### T-20261005-33 P6 阶段 0：每天自存期权链快照（数据资产，只读，不花钱）
- status: done（2026-10-06 14:15 UTC 13:07 主审轮验收；2026-10-06 14:21 UTC 交互会话已装两条 cron 和 Drive 同步任务）
- priority: 1
- not_before: 无（真实运行要在美东交易时段，10-05 16:07 或 10-06 16:07 的执行轮最合适）
- goal: Alpaca 的期权历史没有报价，晚一天开始就少一天自有的报价历史。存链快照、约 200 只个股的平值和 25-delta 隐含波动率、VIX 期限结构，作为 P6 和 P1 阶段 2a 期权选股信号的数据底座（第二版计划第 3.6 节用途 1）。
- plan: 见简报：新脚本、两条跨夏令时的 cron、disk-policy 登记和 Drive 备份、只读核对两户的期权级别、测试。
- done_when: 第一次真实运行成功、量过单日大小、cron 已装、测试通过；`reports/research/program/options-recorder-2026-10-07/report.md` 已提交，10-07 22:00 UTC 前；标"待主审"。
- brief: reports/research/control/briefs/T-20261005-33.md
- notes:
  - 2026-10-05 06:52 UTC 交互会话（Opus）登记。属于委托范围内的数据工作，不需要机主批准预算（T-85 审核时已判断）。
  - 2026-10-05 07:30 UTC 交互会话按 T-36c 改简报：个股部分从"平值和 25-delta 三个点"改成两个月度到期的整条链（现价 ±25%），另存派生点表。原因：隐含波动率价差要同一行权价的看涨和看跌，月度变化要两个到期日插值；数据过后补不回来。执行轮取任务时以简报现版本为准。
  - 2026-10-05 13:38 UTC 13:07 主审轮（Opus，P6 轮换）：简报第 7 步要执行轮装两条 cron，和手册第 0 节第 1 条（自动轮不改 crontab）冲突。简报末尾已加"主审修正"：执行轮只写好两条 cron 行（写进报告和本任务 notes），由交互会话安装，和 T-30、T-53 的做法一致；done_when 里的"cron 已装"改按"cron 行已写好、待交互会话安装"验收。**需要交互会话做**：装这两条 cron。
  - 2026-10-06 14:15 UTC 13:07 主审轮（Opus，P6）：派 sonnet-high 子代理 R1005-T33（型号 claude-sonnet-5-5，37+7 次调用）。交付 `scripts/record_option_chains.py`、`tests/test_record_option_chains.py`（17 个通过，ruff 干净）、`config/disk-policy.yaml`（protected、hot 各加 data/options）、`reports/research/program/options-recorder-2026-10-07/report.md`。主审加了两处：每行带 snapshot_ts_utc、分区 `_manifest.json` 记 run_kind，定时运行可整日替换手动数据、手动不覆盖定时；个股另取 DTE 在 [7,30) 内最大的前端到期（`expiry_role` front/m1/m2），30 天平值 IV 改为夹住 30 天的两个到期按总方差内插。第二次手动运行 14:08:56–14:13:37 UTC（美东 10:08，交易时段内）：663 次请求、0 次 429，链 30,015 行、个股链 30,348 行（front 200、m1 200、m2 196 只）、派生点 842 行（interp 839、none 3），VIX 期限结构 9,287 行（Cboe 全历史到 10-05），单日 4.037 MB（manifest）。三户（quant1、quant2、默认模拟账户）options_approved_level 和 options_trading_level 都是 3。名单 `data/options/universe/2026-10.json` 只含个股（核过无 ETF）。**cron 行已写好，待交互会话安装**（报告第 5 节，19:40 和 20:40 UTC 周一到周五；装上当天 15:40 ET 起每天自动存）；Drive 同步任务也待交互会话建。`data/options/` 没被 git 忽略，本轮在 .gitignore 加了一行。
  - 2026-10-06 14:21 UTC 交互会话：报告第 5 节的两条 cron 原样装上（19:40、20:40 UTC 周一到周五；crontab 备份 `/tmp/lead/crontab.bak.20261006T142105Z`），今天 19:40 UTC（美东 15:40）第一次定时运行。用的是 `.env` 里主模拟账户的数据密钥，和 quant1/quant2 的下单密钥分开限速，不会和 19:30 起的 v1.2 下单抢额度。Drive 任务 `options-push`：push 类型，只增不删，每天 00:00 UTC，`data/options` → `datasets/options`，已手动先跑一次。文件名每个分区固定，所以定时运行替换手动运行的那天时，Drive 上会被覆盖；只有手动运行有、定时运行没有的代码，会在 Drive 上留旧文件，只影响 10-06 这一天。

### T-20261005-34 P5 研究门补强：跨项目试验总数、语义查重和族配额、盈亏平衡成本、门槛变更留痕
- status: ready（定时执行轮可取）
- priority: 2
- not_before: 无
- goal: 深挖和进化式搜索会大量增加试验，最容易自欺。按第二版计划第 3.5 节第 3 条、第 2 节第 4 条，在 `oc research iteration` 门里补四项；已有的试验台账、候选去重、最终回执、锁箱不重做。
- plan: 见简报。新阻断只对 10-06 及以后登记的迭代生效；现有迭代的 validate 结果必须不变。门槛变更记录先登记 10-05 的 V2 整股量化。
- done_when: 代码、配置、测试、`reports/research/program/gate-additions-2026-10-09/report.md` 已提交，10-09 22:00 UTC 前；全量测试和 `oc repo check --strict` 通过；标"待主审"。
- brief: reports/research/control/briefs/T-20261005-34.md
- notes:
  - 2026-10-05 06:52 UTC 交互会话（Opus）登记。

### T-20261005-35 旧否定的功效复查（只追加）和外部负面证据登记
- status: ready（定时执行轮可取）
- priority: 2
- not_before: 无
- goal: 按 P-1，凡是按单一规格或功效不足判的否定，追加"未到深度"记录和当时的最小可检出效应；外部负面证据（I-08 第 6 项）登记进方向登记。
- plan: 见简报。只追加，不改原记录；`oc research directions validate` 必须 ok。
- done_when: `reports/research/program/power-reaudit-2026-10-08/{audit.json,report.md,compute.py}` 和登记的追加已提交，10-08 12:00 UTC 前；标"待主审"。
- brief: reports/research/control/briefs/T-20261005-35.md
- notes:
  - 2026-10-05 06:52 UTC 交互会话（Opus）登记。来源：第二版计划第 2 节第 8 条、第 3.5 节第 6 项。

### T-20261005-36 调研一页纸四份：小资金多空构造、基金内部日报、期权隐含选股信号、加密和盘后隔夜
- status: done（四份调研全部交付并审核，2026-10-05）
- priority: 1
- not_before: 无
- goal: 第二版计划要求方案先调研别人怎么做（R10）。四份分别喂给：v1.2 小资金构造的合同（10-08）；日报首屏改版（10-08）；P1 阶段 2a 和 P6 用途 2（10-08）；11 月是否开工加密、盘后和隔夜（10-09）。
- plan: (a) 小资金多空构造：补全 T-71 整理的做法（基数约束优化、整数规划、转移系数、最小手数取整、指数相对的"少配代替做空"），每种写别人怎么做、开源实现、对我们的适用性，10-08 00:00 UTC；(b) 基金内部投资经理日报和风险日报的公开描述，10-07 12:00 UTC；(c) 期权隐含信息选股信号的发表后证据和免费数据可行性，10-08 12:00 UTC；(d) 加密现货、盘后、隔夜各一页：别人怎么做、最低有效深度、开工条件，10-09 12:00 UTC。(a)(b) 先派，(c)(d) 在前两份交付后派，同时最多两个代理。
- done_when: 四份写到 `reports/research/intel/I-20261005-0{1,2,3,4}-*.md`，交互会话审核后提交。
- notes:
  - 2026-10-05 06:52 UTC 交互会话（Opus）登记。
  - 2026-10-05 06:59 UTC 交互会话派出 (a) 752a2a89（简报 briefs/T-20261005-36a.md，协调码 R1005-T36A）和 (b) 1a6a6161（briefs/T-20261005-36b.md，R1005-T36B），都是 Sonnet 5.5 high 独立 Paseo 代理。(c)(d) 在前两份交付后派。
  - 2026-10-05 07:13 UTC：(b) 已交付，交互会话审核通过：`reports/research/intel/I-20261005-02-pm-daily-risk-report-practice.md`（13 项出处，缺口写明：没有找到量化基金日报首屏的原样公开样例）；两个关键数字已复算（10 个会话里 95% 区间外至少 2 次的概率 8.6%；Lo 2002 夏普标准误 0.188）。首屏改版定稿写进 T-20261005-39 简报的 C 批。(c) 已派出 e5f347e2（briefs/T-20261005-36c.md，协调码 R1005-T36C），10-08 12:00 前交。
  - 2026-10-05 07:24 UTC：(a) 已交付，交互会话审核通过：`reports/research/intel/I-20261005-01-small-capital-long-short.{md,json}`，快照 26 个。推荐合同试三种：R1 每边前 K≤200 只两步法（空头整股、多头碎股、SPY 对冲）；R2 同 K 的混合整数规划（HiGHS）作精确对照；R3 只留多头加 SPY 对冲作下界；同 K 随机选名作安慰剂。要点：Murray–Shek 2012 全文，3,000 选 15，CPLEX 25,200 秒对截断启发式 36 秒，目标值差 1.8%；代理自己的 HiGHS 探针（交互会话未复跑），5 万美元档 F1 空头取整为 0 的名字从 419 降到 352，瓶颈是名字太多，不是求解器（419 和 T-71 的 59.1% × 709 一致）；用权重相关算转移系数没有区分力（≥ 0.999），要改用收益口径。(d) 现在派。
  - 2026-10-05 07:27 UTC：(d) 已派出 b7db6bf6（briefs/T-20261005-36d.md，协调码 R1005-T36D），10-09 12:00 前交；简报列了本地已做过的加密、隔夜、缺口档案，要求先读。
  - 2026-10-05 07:30 UTC：(c) 已交付，交互会话审核通过：`reports/research/intel/I-20261005-03-options-implied-stock-signals.{md,json}`，快照含 `power-calc.py`。功效数字已复算一致：N=200、60 天的最小可检 IC21 = 0.117（每日截面 IC 标准误 1/√200，重叠 21 日收益约 2.9 个独立期）；检出 0.03 约需 916 天；N=1,000、520 天约 0.018。结论写进计划第 3.6 节用途 2。全文被 403 的几篇只读了摘要，报告里已标明。
  - 2026-10-05 07:48 UTC：(d) 已交付，交互会话审核通过：`reports/research/intel/I-20261005-04-crypto-extended-overnight.{md,json}`。结论写进计划第 7b 节：加密 11 月不开线（暂缓，未到深度）；盘前盘后并入 P5 执行层；隔夜只做 ETF 成本口径复核（新任务 T-20261005-43），个股隔夜保持关闭。四份调研全部交付，本任务 done。几篇被 403 挡住的只读了摘要，报告里已标明。

### T-20261005-37 v1.2 小资金版构造（每边前 N 只和 F2 少配代替做空），Modal CPU
- status: ready（定时执行轮可取；合同 10-06 01:44 冻结，比原计划提前两天）
- priority: 1
- not_before: 2026-10-06 16:00 UTC（重任务，本机 1.8G；排在 T-20261005-01、T-32 之后，不和其他超过 1 GB 的任务并行，不在 21:30–00:30 UTC 跑）
- goal: Alpaca 没有碎股做空，原构造的 v1.2 要约 25 万美元子仓才过 V2（F1、F2 都是），按 T-43 的权重相当于账户约 1,000 万和 208 万美元。小资金版决定 v1.2 能否在机主的资金下上实盘（第二版计划第 5 节第 2 条）。
- plan: 合同要写定：两种做法（每边前 N 只，N 取 100、200、300，按取整可行性的最低资金档；F2 另试直接持有指数成分股、多头用碎股、把空头叠加变成"少配"）；判定按同波动夏普对原构造，V2 按标准 vetoes.whole_share_*；回测按拆分执行算成交价（碎股部分不能参加竞价，按 15:50 前后的当日单算）；模拟资金 5 万美元。Modal 8 核 16 GiB 约 10 小时、约 5 美元，开跑前过 `scripts/modal_budget.py check`。
- done_when: `reports/research/iterations/t20261006_p1_v12_small/{identity.json,results.json,report.md,trial-ledger.json}` 已提交（git add -f），F1、F2 各有 mechanical_status 和 min_capital_tier；截止 10-08 00:00 UTC；结果标"待主审"。
- brief: reports/research/control/briefs/T-20261005-37.md
- notes:
  - 2026-10-05 06:52 UTC 交互会话（Opus）登记。来源：第二版计划第 5 节第 2 条，第三轮复核第 5 条。
  - 2026-10-05 07:24 UTC 交互会话：合同输入是 T-36 (a) 的 `I-20261005-01`：R1、R2、R3 三种做法、同 K 随机选名安慰剂、收益口径的转移系数、同波动夏普保留率（带 Ledoit–Wolf 区间）。代理建议小资金版整本都在 15:50 前后下当日单（整股、碎股同单同价），回测按实际时点的价格算，不走竞价；这和计划原写的"整股竞价、碎股当日单"不同，由主审轮在合同里定，两者都要写明理由。
  - 2026-10-06 01:48 UTC 10-06 01:07 主审轮（Opus）写合同 `reports/research/iterations/t20261006_p1_v12_small/`（hypotheses.md 第 3–9 节，01:44 冻结；direction-check、pre-backtest 都 ok；5 份一手来源 10-06 01:31 重新抓取并做了来源卡）。T-36 (a) 调研已交，所以前置满足，提前到今天。决定：整本 15:50 前后当日单（碎股不能参加竞价、模拟盘不模拟竞价），回测 D+1 收盘价加收盘成本模型；候选 16 个（F1/F2 × R1 K 50/100/200/300/all、R1B 100/200、R3），2.5 万和 10 万美元档 20 条只报告，随机选名安慰剂 40 条；K* 按 V2 可行性选，不按夏普；保留率 ≥ 0.80、跟踪误差比 ≤ 0.25、压力期保留率 ≥ 0.60 分 same/related 两类。第 B 阶段（信号安慰剂）只在 related 时由主审轮另写。10-07 01:07 主审轮（P1）审核。
  - 2026-10-06 01:58 UTC 同一主审轮，结果之前加修正案 A1（`amendment-A1.md`）：T-70 测到 v1.2 重跑有数据漂移（F1 全期夏普 1.042 对 1.048），所以 I1 改为和同一次遍历里的父类模拟器逐位比，FULL 也取同一次遍历；10-02 的 A1 文件只用于 I3 和漂移诊断。简报已同步。

### T-20261005-38 评判标准 v2.2 草案：L2 的前向长度按信息量（最短记录长度）算
- status: ready（主审轮取）
- priority: 2
- not_before: 无；**10-09 22:00 UTC 前**冻结草案并告诉机主
- goal: 机主要实盘尽量快。标准 v2.1 的 L2 要求至少 6 个月前向，按 09-01 起算最早 2027-03。按信息量算可能更短，也可能更长（第二版计划第 5 节第 1 条）。
- plan: 主审轮写草案：L2 的前向长度改为"按 DSR 打折后的先验夏普，前向记录达到 95% 信心所需的最短记录长度"，下限和上限写死。**规则只能用先验和回测的量来定，不能看当前前向结果再定。** 草案冻结时记哈希，写进门槛变更记录（T-20261005-34 建好后补登），在日报里告诉机主。
- done_when: 草案文件和变更记录已提交；日报里有一段说明。
- notes:
  - 2026-10-05 06:52 UTC 交互会话（Opus）登记。
  - 2026-10-06 14:13 UTC 13:07 主审轮：v2.2 草案并入 DXRG 对照稿（`reports/research/program/dxrg-disciplines-2026-10-10.md`）的 10 处修改（第 3、4、5、6、9、11、12、15、16、17 行），都是加要求或改标定方法，不放宽阈值。第 15 行（反复读的前向阈值按"监控期内任何一天越界"标定，126 个会话内误减半 ≤ 5%、误停 ≤ 1%、误晋级 ≤ 10%）和本任务的"L2 前向长度按信息量"是同一个问题，一起写。

### T-20261005-39 日报和看板第一批改动：期望对照前向、v1.2 每日动作（A 批）；风险和暴露、统计信封（B 批）
- status: partial（A 批 done，B、C 批未做；执行轮 2026-10-05 22:08–22:30 UTC；待主审）
- priority: 1
- not_before: 无（A 批 10-07 00:50 UTC 前，B 批 10-08 00:50 UTC 前）
- goal: 机主 10-04 第 1 条（报告没有主次、太简易）。第二版计划第 4 节。首屏三件事的改版等 T-20261005-36 (b) 的调研，不在本任务里。
- plan: 见简报。
- done_when: 预览日报和看板截图在 `reports/research/program/report-v3-2026-10-08/`，代码和测试已提交；标"待主审"。
- brief: reports/research/control/briefs/T-20261005-39.md
- notes:
  - 2026-10-05 06:52 UTC 交互会话（Opus）登记。
- notes: 2026-10-05 22:30 UTC 执行轮（sonnet-high 子代理 R1005-T39，30 次调用，只做 A 批）：(1) 日报第三节新增“前向对预期”表（S1/S2/S3/C2/V12F1/V12F2：前向会话数、z、夏普、概率夏普、95% 所需会话数、进度；C2 只有 5 个会话写“样本不足”，V12F1/F2 记录里无前向会话写“缺”）；(2) 日报第二节新增 v1.2 每日动作表（10-07 起；现在写“未开始”，填充路径只靠单测覆盖，真实数据未验）。新建 `open_composer/reports/owner_forward.py`、`tests/test_owner_forward.py`、`reports/research/program/report-v3-2026-10-08/preview-daily-A.md`；改 `open_composer/reports/owner_digest.py`（DigestData +2 字段）、`docs/owner-reporting.zh.md`（第 4 节 +2 条）。ruff 过，tests/test_owner_forward.py + owner_digest 相关测试 29 过；未跑全量 pytest 和 oc repo check --strict。偏离：summary.json 没有概率夏普和最短记录长度，子代理用 Bailey–López de Prado 公式补算（夏普取自 JSON，S1 4.54）。S1 概率夏普 86%/所需 24 会话/进度 45%；S2 94%/12/92%；S3 61%/353/3%。B 批（风险和暴露、统计信封，10-08 00:50 前）和 C 批（首屏改版，10-08 12:00 前）仍为 ready 待取。待主审。
- notes: 2026-10-06 01:22 UTC 01:07 主审轮（Opus）审核 A 批：v1.2 每日动作表接受；前向对预期表有方法缺陷，已在本轮修正。缺陷：概率夏普和"95% 所需会话"用前向 11 天的观测夏普算（S2 年化 9.03 → 只需 12 个会话、进度 92%），而 T-70 的 summary.json 自己把这段标为 sharpe_meaningful=false，简报也写了"不重算口径、不补数"；11 天的年化夏普标准误约 4.8，这个进度会让机主以为 S2 快被证实了。10-06 00:50 的日报已经带着这张表发出（logs/owner-report/daily-2026-10-06.md 第 79 行），本轮汇报里更正。修正（owner_forward.py、tests/test_owner_forward.py、docs/owner-reporting.zh.md 第 55 行）：所需会话改按回测近期夏普（summary.json backtest_recent 的均值和标准差，正态矩，是下限）算，现为 S1 250、S2 159、S3 184、C2 163，进度 3–7%；记录标为不具意义时不给夏普和概率夏普。测试 31 个通过。T-38（L2 草案）会把所需会话换成按 DSR 打折的先验，届时这一列改读 T-38。B、C 批仍 ready。preview-daily-A.md 是修正前的预览，不再代表现行输出。
  - 2026-10-06 17:10 UTC 交互会话（Opus）：机主 10-06 要求日报彻底重构，本任务 C 部分的首屏方案作废，由 T-20261006-11 取代（撰写稿正文 + 逐轮记录附件 + 内部代号检查）。A、B 批的数据表保留在附件和撰写稿里使用。

### T-20261005-40 项目笔记的骨架和生成脚本（六个旗舰项目）
- status: done（待主审）
- priority: 2
- not_before: 无
- goal: 自动轮按项目续做，执行轮从项目的实验清单里取下一个实验（第二版计划第 2 节第 1、2 条）。
- plan: 见简报。
- done_when: `reports/research/programs/` 六个目录和 `scripts/program_pages.py` 已提交，`check` 通过，10-08 22:00 UTC 前；标"待主审"。
- brief: reports/research/control/briefs/T-20261005-40.md
- notes:
  - 2026-10-05 06:52 UTC 交互会话（Opus）登记。
  - 2026-10-06 22:07–22:19 UTC 执行轮（Sonnet 5.5）：六个目录、`scripts/program_pages.py`、`tests/test_program_pages.py` 已提交 d5f8377（26 个文件）；`program_pages.py check` 六项 ok；12 个测试通过，ruff 干净。子代理加了可选字段 `depends_on`；P5-E6、P4-E7–E10 因 not_before 或主审取标 planned。各项目下一个 ready 实验：P1 P1-E0（T-20261005-01）、P2 P2-E2a（T-20261006-03）、P4 P4-E6（T-20261005-37），P3、P5、P6 无 ready。待主审。


### T-20261005-41 ETF 子策略的开盘、收盘同信息比较（定试点的下单时点）
- status: done（2026-10-06 07:38 UTC 07:07 主审轮审核：接受；试点按开盘成交，沿用现状）
- priority: 1
- not_before: 无
- goal: ETF 试点走手动下单，要定用开盘还是收盘成交。同样的信号，下一交易日开盘和收盘成交扣成本后差多少（第二版计划第 3.0 节排期 10-07、第 3.1 节阶段 3）。
- plan: 见简报。
- done_when: `reports/research/program/etf-open-close-2026-10-07/` 已提交，10-07 22:00 UTC 前；标"待主审"。
- brief: reports/research/control/briefs/T-20261005-41.md
- notes:
  - 2026-10-05 06:52 UTC 交互会话（Opus）登记。
  - 2026-10-06 执行轮（Sonnet）：交付物 reports/research/program/etf-open-close-2026-10-07/{results.json,report.md,compute.py}（compute 在 git 中，提交见本轮提交）。现状口径=收盘后算信号、次日开盘成交（O）。O 减 C 年化百分点（近期/全期）：S1 +0.03/-0.11，S2 -0.15/+0.05，S3 +3.19 [0.18,6.68]/+0.18，C2 -0.23/+0.08；S3 差异集中在近期三段回调，去掉三个最大日后 +0.88，五个偏移里一个为负。成本按每边 10bp，无分时段实测。O 复现冻结引擎 1e-9 内。子代理未联网核对券商竞价单截止时间。待主审。
  - 2026-10-06 07:38 UTC 07:07 主审轮（Opus）审核：接受。对照 results.json 核对四条两种口径的年化、夏普、回撤和 O 减 C 区间，与报告表一致；O 口径与冻结引擎逐位一致（最大差 0 到 1.4e-17），C2 与存档筛选序列 2692 个交易日最大差 0；两种口径都没有前视（t−1 收盘出信号，t 开盘或 t 收盘成交），五偏移混合，不挑调仓日。结论：S1、S2、C2 区间都含 0；S3 近期 +3.19 个百分点 [0.18, 6.68] 集中在三段回调和三个交易日，全期 +0.18 含 0，不当规律。试点（只有 S3）按开盘成交下单，沿用模拟盘现状。未解决：ETF 开盘、收盘分时段价差没有实测，两口径同为每边 10 bp；用模拟盘 TCA 和试点首批成交核对。

### T-20261005-42 DXRG 论文的 17 条方法纪律，对照评判标准逐条比对
- status: done（2026-10-06 14:13 UTC，10-06 13:07 主审轮读原文后完成）
- priority: 3
- not_before: 无；10-10 22:00 UTC 前
- goal: I-20261004-08 第 6 节第 1 项。DXRG（arXiv 2609.05663）是这一类项目里唯一有规模的测量，结论是 AI 交易代理没有方向性优势；它的 17 条方法纪律和我们的标准逐条比，缺的补上。
- plan: 主审轮读原文（存快照），逐条写"我们已有／缺／不适用"，缺的列成改标准或改门的具体修改，交下一次标准修订。
- done_when: `reports/research/program/dxrg-disciplines-2026-10-10.md` 已提交。
- notes:
  - 2026-10-05 06:52 UTC 交互会话（Opus）登记。
  - 2026-10-06 14:13 UTC 13:07 主审轮（Opus，P5）：原文第 9 节逐字存快照 `reports/research/intel/sources/dxrg-2026-10-06/`；对照稿 `reports/research/program/dxrg-disciplines-2026-10-10.md`。已有 5、标准没写 1、部分 7、缺 3（第 6 条以成交为条件、第 9 条日历足迹、第 15 条反复读的 p 值）、只对 LLM 适用 1。第 15 条的膨胀用代码量过（`dxrg-disciplines-2026-10-10/repeated_looks.json`）：前向 z<−2 每天读，126 个会话内误判 13.7%（名义 2.3%）；95% 分位回撤减半线 20.3%（名义 5%）。10 处修改交 T-38 的 v2.2，停用阈值交今晚 19:07 P4。

### T-20261005-43 ETF 隔夜持有的成本口径复核（SPY、QQQ、IWM；当初按每边 10、20bp 判死，盈亏平衡只有 1.9–4.3bp）
- status: ready（主审轮取：先写合同，再交执行轮）
- priority: 2
- not_before: 2026-10-07 00:00 UTC（等 10-05 收盘竞价、10-06 开盘竞价两个探针的结果）
- goal: T-36d 调研（`reports/research/intel/I-20261005-04-crypto-extended-overnight.md` 第 4 节）发现，ETF 隔夜当初是按每边 10、20bp 的成本判死的（夏普 −3.99、−2.45），而 SPY、QQQ、IWM 的盈亏平衡是每边 1.9–4.3bp，竞价单的实际成本可能低于 1bp。按手册第 4A 节第 8 条"先改进、后否定"，死于成本口径的要先纠正口径。文献：Lou–Polk–Skouras 2019（全文）发现 1993–2013 动量利润几乎全在隔夜；反面：隔夜 ETF NightShares 上市约 13 个月后清盘（NSPY 总回报 −6.9%，同期标普 +22%）。
- plan: 主审轮按 I-20261005-04 第 4.4 节的草案写合同，direction-check 和 iteration validate 都要过：
  - 标的 SPY、QQQ、IWM；收盘买、次日开盘卖，用官方开盘和收盘价配对（复用 T-14 的官方价配对代码）；
  - 成本曲线每边 0.5、1、2、3bp；
  - 对照：同标的同波动的买入持有；另报并入现有组合（S3 加 C2）的边际夏普；
  - 窗口按标准的近期窗口和大盘阶段；**代理的描述性计算已经看过这些窗口的结果（只有 IWM 扣 1bp 后两个窗口都高于买入持有），证据要打折，进模拟盘前要有前向影子**；
  - 预算：本机不超过 2 天；预期偏否。实盘要用竞价单的话，Alpaca 要联系销售开通（T-72），模拟盘测不出竞价成交价（T-20261005-02 的解读口径）。
- done_when: 合同冻结，结果 10-09 22:00 UTC 前提交；主审轮判定并写死因或下一步。
- notes:
  - 2026-10-05 07:48 UTC 交互会话（Opus）登记。来源：T-20261005-36 (d)。

### T-20261005-44 P6 期权隐含信号的数据门：DoltHub volatility_history 全量拉取（2019-02-09..2026-09-17）和 F1–F4 检查
- status: done（2026-10-06 07:38 UTC 07:07 主审轮审核：数据接受；原口径 gate_pass=false 保留，修正案 A2 经独立复核后按决策宇宙通过，T-45 可跑）
- priority: 1
- not_before:
- goal: P1 阶段 2a（约 10-12 写合同）之前，弄清免费的 DoltHub 期权隐含波动率能不能给流动股（L12）做选股信号输入。机主的数据分层把期权排在价量之上；只靠自存快照（T-33）要好几年才有功效，DoltHub 的密集段（2024-10 起 99% 的交易日、每日约 1,535 只）是唯一的近路。本任务只做数据：拉取、覆盖、连接、时点、数值和时点标的检查，不算任何信号与收益的关系。
- plan: 合同 `reports/research/iterations/t20261005_p6_iv_signals/hypotheses.md` 第 4 节（2026-10-05 13:38 UTC 前冻结，direction-check 和 pre-backtest 都 ok）。按简报：给拉取脚本加 `--weekdays-only`；后台拉取约 3,400 次请求；写 `scripts/p6_iv_data_gate.py` 算 F1（覆盖）、F1b（L12 连接率中位 ≥ 0.60）、F2（hv_current 与自算波动率的对齐定 as-of 规则，dolt_log 定公布延迟）、F3（取值、自相关、陈旧）、F4（时点标的，只报告）；输出 data-feasibility-measured.json 和给 T-45 的 cache/volhist_sessions.parquet。
- done_when: `data-feasibility-measured.json` 和脚本、测试已提交（git add -f），gate_pass 有值，max(t) ≤ 2026-09-17；结果标"待主审"。**10-07 22:00 UTC 前**。
- brief: reports/research/control/briefs/T-20261005-44.md
- notes:
  - 2026-10-05 13:38 UTC 13:07 主审轮（Opus，P6 轮换）登记。本轮已测可得性：近期窗 674 个交易日有 594 个有数据，2024-10 起 485/490，节假日也有行，日期 d 约在下一日 06:35 UTC 提交，2021 年的行有已退市代码（证据 `reports/research/intel/sources/p6-iv-signals-2026-10-05/`）。
  - 2026-10-06 执行轮（Sonnet）：data-feasibility-measured.json（提交 4143b87）gate_pass=false，仅 F3 自相关中位 0.884 < 0.90；F1 过（594 个有数据日、晚期覆盖 0.9898、中位 1535 只），F1b 过（L12 连接中位 0.7316），F3 取值范围 0.99996、陈旧 0.0028 过；F2 as_of_rule=same_day（H_same w30 0.9987 对 H_prev 0.9888），publication_shift=0；F4 2019 年 662 只中 205 只 2026 不再出现。拉取 1,984 日单元、1,890,015 行，数据始于 2019-05-10（非 2019-02-09），--end 2026-09-17。cache/volhist_sessions.parquet max t=2026-09-17，1,803,947 行。偏离简报：子代理给拉取脚本加了 --workers、--newest-first（16 并发）、hv_week_ago/hv_month_ago 列，并把日循环改成 lo<=end；未跑全量 pytest。T-45 的前置 gate_pass=true 不满足，简报第 0 步会据此停，由主审轮决定是否改门。待主审。
  - 2026-10-06 07:38 UTC 07:07 主审轮（Opus）审核：F1、F1b、F2、F3 取值和陈旧的数字与 JSON 一致，接受。F3 自相关不过的原因：本轮诊断 `t20261005_p6_iv_signals/f3_diagnostic.py` → `f3-diagnostic.json`（只读缓存和 8-K 日期，不读收益）显示，决策宇宙（主要在 L12 的 588 个代码）中位 0.926，其余 993 个 0.804，无财报事件的 548 个（多为 ETF、ADR）0.708；即不过的部分在检验之外。合同第 4 节没写总体，是主审 10-05 的疏漏。修正案 A2（`amendment-A2.md`）：门槛 0.90 不变，只把 F3 自相关的总体对齐到第 3 节的检验宇宙，写于任何信号与收益计算之前；独立复核（sonnet-high，R1006-A2REV，`amendment-A2-review.md`）verdict approve，四种总体口径 0.9245–0.9262 都过。复核另报：L12 且有 IV 的名数每日中位 574（合同估 650–750，MDE 约大 10%）；决策宇宙的日度 IV 变化噪声比全体轻（差分自相关 −0.185）。T-45 简报第 0 步已改为接受 A2，并加了三条只报告的说明。子代理偏离简报（加 --workers、--newest-first、hv_week_ago 等列）不影响数据门，接受；没跑全量 pytest，留到 T-45 之后一并跑。

### T-20261005-45 P6 期权隐含选股信号的 IC 测量：IVRV、DIV21、DIV5、IVZ3（只晋级、不否定）
- status: ready（定时执行轮可取；重任务；数据门按修正案 A2 通过，简报第 0 步已改；仍要 T-20261005-01 已 done）
- priority: 1
- not_before: 2026-10-06 20:00 UTC
- goal: 在 2024-01-08..2026-09-15 的流动股上，测四个预注册期权隐含信号扣行业和 β 后的 IC 衰减，过晋级规则的进 P1 阶段 2a 的信号族。回答"期权信息能否给主力引擎加输入"，这是机主数据分层里最高一档的信息源第一次在近期窗口上按足够的样本测。
- plan: 合同同上（第 2、3、5、6 节）。IVRV = iv − RV21，方向 +（Bali–Hovakimian；I-03 和 T-61 写反了，已更正）；DIV21、DIV5 的方向先用压力窗定、写进 cache/signs.json 再算近期窗；IVZ3 = 3 日对数收益 ÷ 隐含幅度，方向 −，还要胜过 HVZ3。决策统计量：月度信号 CIC(2..22)（NW 25 阶），快信号 CIC(2..6)（NW 10 阶）；晋级 = 近期 L12 按冻结方向 > 0、t ≥ 2.0、BH q ≤ 0.10（4 个）。诊断：对 M0 和九个主题的边际 IC、持续性、旧信号、分档、逐年、压力窗和 B 窗。功效：CIC(2..22) 的 MDE 约 0.09，只能检出接近原文、未打折的效应；不过的写"未到深度"及原因。
- done_when: `t20261005_p6_iv_signals/{results.json,report.md,trial-ledger.json}` 已提交（git add -f），mechanical_status 为三个值之一，signs.json 的 fixed_at 早于近期窗计算，新测试通过；结果标"待主审"。**10-08 12:00 UTC 前**，供 P1 阶段 2a 合同（约 10-12）使用。
- brief: reports/research/control/briefs/T-20261005-45.md
- notes:
  - 2026-10-05 13:38 UTC 13:07 主审轮（Opus，P6 轮换）登记。先验：IVRV 约 20%，DIV21、DIV5 各约 12%，IVZ3 加 HVZ3 条件约 20%；至少一个晋级约 45%。新读的反面证据：Neuhierl 等（Management Science 2026）控制公司特征后只有少数期权特征有增量；Walter–Zimmer–Ulrich（arXiv 2609.31263，样本内）里留下的是尾部、峰度和凸性，不是 IV−RV 或 IV 变化。
  - 2026-10-06 07:38 UTC 07:07 主审轮（Opus）：T-44 审核后写修正案 A2（F3 自相关按决策宇宙计，门槛不变，独立复核 approve）。简报第 0 步改为 gate_pass=true 或 A2 生效；results.json 写 data_gate = passed_under_amendment_A2，报告开头照抄 A2 第 4 节的说明；按实际每日名数（中位约 574）报 SE 和 MDE。第二个前置（T-20261005-01 已 done）不变。

### T-20261006-03 P2 阶段 2a：跳跃模型状态层的复现（标普 1990–2023 的相对结论）和指数层九个规格
- status: ready（定时执行轮可取；合同 10-06 07:34 冻结）
- priority: 2
- not_before: 无（本机重步骤不在 21:30–00:30 UTC 跑；不和其他超过 1 GB 的任务并行；排在 priority 1 的任务之后）
- goal: 第二版计划 P2 阶段 2（10-08 至 10-13）的深度锚点。先在免费 CRSP 数据上复现 Shu–Yu–Mulvey 2024（JAM）的跳跃模型 0/1 策略：标普 1990–2023 夏普 0.48 → 0.68，回撤减半。再按输入数（3、4、6）、持续性（λ 15、50、150 和交叉验证）、模型类（JM、HMM、GMM、现有 200 日线 × VIX）扫九个规格，在指数层和同敞口波动率目标比。回答登记簿"只是回撤控制"对不对，并为阶段 2b 冻结日度乘数。
- plan: 合同 `reports/research/iterations/t20261006_p2_s2_regime_layer/hypotheses.md`（"预注册全文"第 2–4、6 节；direction-check 和 pre-backtest 都 ok）。步骤见简报：长历史数据（French 日度、FRED BAA10Y、VIXCLS、SIP SPY）、`open_composer/research/regime/jump_model.py` 加截断不变性测试、在隔离环境和 jumpmodels 包交叉核对、复现关口 R1–R3、指数层输出、冻结 `cache/multipliers.parquet`。
- done_when: `index_results.json`、`report-2a.md`、`data-provenance.json` 已提交（git add -f），reproduction.status 有值，multipliers_sha256 与缓存一致，测试通过；结果标"待主审"。目标 10-09 22:00 UTC 前。
- brief: reports/research/control/briefs/T-20261006-03.md
- notes:
  - 2026-10-06 07:38 UTC 07:07 主审轮（Opus，P2 轮换）登记。先验：复现约 65%；J3_CV 在指数层比同敞口波动率目标高 ≥ 0.05 约 45%。新证据：论文已在 JAM 25(5):493–507 发表；CBS 2025 硕士论文在因子 ETF 上方向一致但不显著。I-20261004-06 里"稀疏跳跃模型"的快照抓错了文章（arXiv 2106.09535 是物理论文），合同不引用。

### T-20261006-04 P2 阶段 2b：状态乘数加到 S1–S3、C2（S3 判定，对照同敞口波动率目标和循环平移安慰剂）
- status: ready（定时执行轮可取；前置是 T-20261006-03 已 done、乘数缓存的 sha256 一致，简报第 0 步核对）
- priority: 2
- not_before: 无（排在 T-20261006-03 之后；本机重步骤不在 21:30–00:30 UTC 跑）
- goal: 机主 10-04 说压力期夏普低；S3 占试点风险约 90%，压力期夏普约 0.59。本任务回答：带持续性的在线状态层，能否在压力窗把 S3 的同敞口夏普提高 ≥ 0.10，同时近期窗代价不超过 0.10。过了就进 8–12 周只记日志的影子；不过就写"未见增量，功效不足以否定"，P2 转阶段 3。
- plan: 合同同上（第 3、5、6、8 节）。复用 T-41 的 compute.py（sleeve_paths、simulate_effective），m ≡ 1 恒等 ≤ 1e-12；一天延迟；10 bp 和 20 bp；同敞口波动率目标按窗口和偏移匹配平均仓位；50 个循环平移安慰剂；机械标签 a–f、r，三种阶段状态。
- done_when: `results.json`、`report.md`、`trial-ledger.json` 已提交（git add -f），mechanical_status 为三个值之一，测试通过；结果标"待主审"。目标 10-11 22:00 UTC 前，10-12 07:07 主审轮（P2）审核。
- brief: reports/research/control/briefs/T-20261006-04.md
- notes:
  - 2026-10-06 07:38 UTC 07:07 主审轮（Opus，P2 轮换）登记。先验：S3 至少一个规格 PASS_SHADOW 约 20%，所有深度点都未见增量约 45%。压力窗 5.9 年，配对夏普差的标准误约 0.13–0.23，+0.10 是政策门槛，不是显著性检验。



### T-20261006-05 P6 阶段 0 关口：期权快照满 20 个交易日的完整性核对和 DoltHub 同日对照
- status: ready（简报待写：11-04 13:07 主审轮写；执行轮在有 brief 字段之前不要取）
- priority: 2
- not_before: 2026-11-04 13:00 UTC（cron 装上后约 20 个交易日）
- goal: 第二版计划第 3.6 节阶段 0 的停止条件。自存的指示性报价能不能当价格用，还是只能用于曲面形状；决定 P6 阶段 2（12 月）和 P1 期权选股信号的前向检验用哪些字段。
- plan: 按日核对四类文件的行数、名单覆盖、manifest 的 run_kind 和请求错误；同日同代码和 DoltHub volatility_history 对照平值隐含波动率；指示性报价的相对价差分布。预注册的判定照计划：差异中位数超过 30% 的，只用于曲面形状，不当成交价。
- done_when: 主审轮写好简报并加 brief 字段后，由执行轮按简报交付。
- notes:
  - 2026-10-06 14:15 UTC 10-06 13:07 主审轮（Opus，P6）登记。依赖 T-20261005-33 的 cron 已装；没装就顺延，并在汇报里写明少了多少天。

### T-20261006-11 机主日报重构：业务语言、正面回答问题、逐轮记录改附件（交互会话）
- status: done
- priority: 1
- not_before: 无
- goal: 机主 10-06 16:36 UTC 读完邮件日报后说看不懂，要求彻底重构：分清交易和研究；不写内部代号、括号细节和流水账；正面回答 10-04 的三个问题（建模、深度调研、流形拓扑）；不只做 ETF；必须做高频。
- plan:
  - 10-06 新格式日报 `reports/owner/daily/2026-10-06.zh.md`，已发邮件；
  - 程序：`open_composer/reports/owner_style.py`（业务名称、内部代号检查），`owner_digest.py`（正文 = 撰写稿或简版，逐轮记录、任务清单、运行状态改为附件），`scripts/owner_report.py tables|lint`；
  - Paseo 定时任务 `oc-owner-daily-writer`（1ffac9be，周一到周六 00:10 UTC，Opus 5.5 high）写当天日报；
  - 规范 `docs/owner-reporting.zh.md` 第 0 节、第 7 节；手册第 4A 节第 7、9 条，第 7 节第 7 步（主审轮只在三种情况发到机主对话）；
  - live-track 加 `owner_asks`（机主问题登记），`owner_decisions` 改成业务语言并带默认。
- done_when: 10-07 00:50 UTC 的邮件正文是撰写稿，检查错误为 0；交互会话 10-07 核对。
- notes:
  - 2026-10-06 17:10 UTC 交互会话（Opus）完成并提交。
  - 2026-10-06 17:12 UTC 交互会话：时间改为 00:05 UTC 撰写（定时任务 1ffac9be），01:00 UTC 发信（crontab，原 00:50；备份在 ~/.local/state/open-composer/cron-backups/）。完成判定改为 10-07 01:00 UTC 的邮件。

### T-20261006-12 高频和日内策略调研：现在最有希望扣成本赚钱的 3–5 个，10-10 前上模拟盘的路径
- status: done（交互会话初审通过；10-07 写 T-14、T-15 简报时细审）
- priority: 1
- not_before: 无
- brief: reports/research/control/briefs/T-20261006-12.md
- goal: 机主 10-06："你必须做一点高频交易策略……模拟盘既然能支持，你就得先做出来。"实盘约 2 万美元、手动或嘉信 API，和先在模拟盘做出来无关。
- plan: 见简报。交互会话审核后据此写 T-14、T-15 的简报，定 T-16 上哪 1–2 个。
- done_when: `reports/research/intel/I-20261006-01-intraday-hft-survey.{md,json}` 和来源快照交付，交互会话审核后提交；10-08 前。
- notes:
  - 2026-10-06 17:10 UTC 交互会话（Opus）登记并派代理。
  - 2026-10-06 17:14 UTC 代理交付，交互会话初审：11 张卡、16 条旧检验的缺深度判断、29 个来源快照；没有跑回测、没有下单。结论：没有一个候选有硬证据显示扣成本后赚钱；公开毛边际每笔 3–12 bp，往返成本 ETF 不足 1 bp、开盘个股 9–40 bp；前向几周只能核对成交，确认边际要几百到上万个交易日。排序（按成本最低、通道最近）：噪声带日内动量（SPY、QQQ）；限定流动性的多股票开盘区间突破；收盘窗口反转和同时段延续，旧的停放理由已过时，最值得做深。待核对：日内交易次数限制 2026-06-04 取消的说法（并入 T-17）、SPY 和前 100 大盘股的半价差实测、IEX 和 SIP 的相对成交量排序是否一致。10-07 据此写 T-14、T-15 的简报。

### T-20261006-13 策略库总清单：151 一书、OSAP、QuantConnect 全量登记，按事先写定的规则选第一批约 50 个
- status: done（交互会话初审通过；第一批的批量合同由 13:07 主审轮在 T-18 写）
- priority: 1
- not_before: 无
- brief: reports/research/control/briefs/T-20261006-13.md
- goal: 机主 10-06："交易方法有成百上千种，为什么不做呢？不要给自己设限。"把 Alpaca 能交易、我们有数据的策略全部登记，标出以前测过没有、到没到深度。
- plan: 见简报。不跑回测。第一批的批量筛选是 T-18。
- done_when: `reports/research/strategy-library/{catalog.json,catalog.md,selection-rule.md,first-batch.json,build_stats.py}` 交付，审核后提交；10-08 前。
- notes:
  - 2026-10-06 17:10 UTC 交互会话（Opus）登记并派代理。
  - 2026-10-06 17:19 UTC 代理交付，交互会话初审：catalog.json 共 694 行（151 一书 175、OSAP 331、QuantConnect 83、登记簿补充 105）；能交易 446，本地数据齐 215，一天内能补 255；能交易、数据齐、从没单独测过 97（含一天内能补 131）；测过但没到深度 68；旧否定都没有深度台账。第一批 50 个：美股 42、ETF 8；月频 27、日内 8、事件 8、日频 7；32 个机制族，每族最多 3 个；25 个能进股票多空组合的现成流程，8 个能用批量筛选模板，17 个要新代码。选择规则在看过第一版名单后改过一次（两处定义错误：登记簿 id 写错，停放和证据太弱被当成测过），第一版名单留档 first-batch.v1-superseded.json，selection-rule.md 第 7 节有记录；没有看过任何回测结果。build_stats.py 能逐字重现 catalog.md（md5 相同）。书的全文和网页打包移到仓库外 ~/.local/share/open-composer/source-snapshots/strategy-library-2026-10-06/，manifest 有 sha256。要补的数据：SEC companyfacts 解析出会计科目（一次解锁多条 OSAP 因子）、宏观公告日历；分析师、13F、专利类没有数据，不进筛选。待核对：多腿期权在 Alpaca 只有买入价差有明文，需一次模拟盘探测。

### T-20261006-14 通用日内策略运行器：把开盘区间突破的模拟下单通道扩成多策略
- status: blocked（等 T-12 定前几名的接口需求；交互会话 10-07 写简报）
- priority: 1
- not_before: 2026-10-07 12:00 UTC
- goal: 10-10 前让 1–2 个日内策略在模拟盘自动运行。需要：信号插件接口、多标的、一天多次进出、按策略的仓位上限和每日亏损上限、收盘前全部平仓、单独账本、和回测同口径的成交记录。
- plan: 复用 `open_composer/paper_intraday.py`，授权、上限、紧急停止、bracket 单、平仓、对账都已有，不另起炉灶。只在模拟盘。
- done_when: 干跑和测试通过，10-09 22:00 UTC 前。
- notes:
  - 2026-10-06 17:10 UTC 交互会话（Opus）登记。

### T-20261006-15 日内方向按深度规则重审，补做 Reversal Trend 的 1 分钟和 1 小时版
- status: blocked（等 T-12 列出旧检验各缺哪几条深度条件）
- priority: 1
- not_before: 2026-10-07 12:00 UTC
- goal: 方向登记簿里日内类 18 个方向，判否 11 个，部分成立 1 个，多是单一版本的便宜测试。按第二版计划的五条深度规则重开最值得的几个：多版本、成本曲线、机器学习变体。机主 9 月要的 Reversal Trend 1 分钟和 1 小时版，当时只测了日线版，这次补上。
- plan: 交互会话或主审轮按 T-12 的结果写合同（direction-check、iteration validate 都要过），数据用本地 SIP 分钟线 `data/sip/minute/`（2023–2026）。近期窗口决定，长历史只诊断。
- done_when: 第一批结果 10-10 22:00 UTC 前提交并审核。
- notes:
  - 2026-10-06 17:10 UTC 交互会话（Opus）登记。

### T-20261006-16 第一批 1–2 个高频或日内策略上模拟盘，做前向观察
- status: blocked（等 T-14、T-15）
- priority: 1
- not_before: 2026-10-09 13:30 UTC
- goal: 机主 10-06 要求在模拟盘做高频。10-10 前上 1–2 个，小仓位，单独记账，用前向数据检验能不能赚钱。
- plan:
  - 账户默认用主模拟账户的闲置资金（约 4.6 万美元，和 ETF 策略分开记账）；机主 10-08 前可以改成新开的模拟账户。
  - 授权文件由交互会话写，引用机主 10-06 16:36 UTC 的原话；仓位上限、每日亏损上限、停止条件写进授权。
  - 每天和回测同口径对照，进日报第二部分。
- done_when: 第一笔模拟单成交并对账，日报列入。
- notes:
  - 2026-10-06 17:10 UTC 交互会话（Opus）登记。

### T-20261006-17 嘉信 API 能力和日内交易次数限制核实，按 2 万美元重算实盘方案
- status: ready（交互会话 10-07 写简报后派执行；简报前定时轮不要取）
- priority: 2
- not_before: 2026-10-07 06:00 UTC
- goal: 机主 10-06：实盘约 2 万美元，手动或接嘉信 API，不接 Alpaca。要查清：
  - 嘉信 Trader API 支持的订单类型、碎股、做空、期权、调用频率上限和申请流程；
  - 2.5 万美元以下保证金账户的日内交易次数限制在 2026 年怎么改的，嘉信是否已执行；
  - 现金账户的结算限制；
  - 对 ETF 轮动手动下单、小资金选股和高频各意味着什么。
- plan: 只用官方文档和监管原文。小资金版合同 t20261006_p1_v12_small 按 2 万美元档重算可行性。
- done_when: `I-20261006-03` 交付；live-track 和第二版计划第 5、6 节更新；10-10 前。
- notes:
  - 2026-10-06 17:10 UTC 交互会话（Opus）登记。

### T-20261006-18 策略库第一批约 50 个的批量筛选
- status: blocked（等 T-13 的 first-batch.json 和选择规则）
- priority: 1
- not_before: 2026-10-08 12:00 UTC
- goal: 10-15 前按统一口径扣成本跑完第一批约 50 个，近期窗口决定，长历史只诊断，按试验总数打折。排名靠前的进深度检验，过关的上模拟盘。
- plan: 复用 `scripts/screen_lane.py`、`scripts/screen_batch.py`。主审轮写一份批量合同，逐个预注册进 manifest。批量大的上 Modal，先过 `scripts/modal_budget.py check`。
- done_when: 结果和排名 10-15 22:00 UTC 前提交，主审轮审核。
- notes:
  - 2026-10-06 17:10 UTC 交互会话（Opus）登记。

### T-20261006-19 复杂建模项目提前到 10-12：随机特征复杂度曲线、多期限联合训练、路径签名预测波动
- status: blocked（等主审轮写合同；原定 11 月，机主 10-06 后提前）
- priority: 2
- not_before: 2026-10-10 13:00 UTC
- goal: 兑现日报对机主"建模"问题的回答：
  - 随机特征模型的复杂度曲线，特征从少到多，看收益是否持续上升；
  - 多个预测期限联合训练；
  - 路径签名预测波动，论文样本外 0.36 对传统 0.22，用来改进仓位控制。
  随机矩阵去噪和粗糙波动率作为风险模型和期权的对照基线直接采用。
- plan: 13:07 主审轮（10-12 起加入复杂建模）写合同，至少三个深度点，功效先算；Modal 上跑，10 月剩余约 23.8 美元，先过 `scripts/modal_budget.py check`。复用 T-20261004-02 的随机特征和梯度提升树代码，T-20261004-77 的旧简报只作参考（那是便宜测试版）。
- done_when: 合同 10-12 前冻结，第一批结果 10-19 前。
- notes:
  - 2026-10-06 17:10 UTC 交互会话（Opus）登记。

### T-20261006-20 拓扑方法作为市场状态输入（市场状态项目阶段 2c）：10-09 写好方案，10-13 前和跳跃模型的结果一起出
- status: blocked（等 07:07 主审轮写合同）
- priority: 2
- not_before: 2026-10-08 07:00 UTC
- goal: 兑现日报对机主"流形拓扑"问题的回答：检验拓扑特征（持续同调的相关结构度量）在简单的相关性和波动率指标之外，对市场状态判断有没有增量；用打乱时间顺序的数据做对照。
- plan: 要先装拓扑计算库（如 ripser 或 giotto-tda），装之前查依赖和内存。合同按五条深度规则：至少三个深度点，例如窗口长度和股票池大小。与 T-20261006-03、-04 的跳跃模型共用状态评价口径。T-20261004-77 的 G1 部分由本任务取代。
- done_when: 合同 10-09 冻结，结果 10-13 22:00 UTC 前。
- notes:
  - 2026-10-06 17:10 UTC 交互会话（Opus）登记。
