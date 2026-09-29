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
- status: running
- priority: 2
- not_before:
- goal: `dir:llm_8k_gdelt_sentiment_acceleration` 的最便宜否定测试。
- plan: 按 `reports/research/control/registry-backfill-2026-09-28.md` Job B 的计划。打分只用机主配置的 DeepSeek 接口，不用 Claude。先算最近一个季度的 IC（对未来 5 日收益），同时跑打乱新闻的安慰剂。IC 符号不稳、或安慰剂也能复现，就停，不搭完整的走步验证。
- done_when: IC 和安慰剂结果写进登记簿；决定继续或停止。
- notes:
  - 2026-09-28 交互会话派 Sonnet 执行；DeepSeek 限流后按 next_try_at 自动续跑。自动轮不要碰。

### T-20260928-17 DeepSeek 试点：10-K/8-K 风险标签特征（400 份）
- status: running
- priority: 2
- not_before:
- goal: `dir:text_to_pit_feature_extraction` 的最便宜否定测试。
- plan: 按同一份报告 Job B 的计划：50 只股票 × 8 个季度，DeepSeek 抽取结构化风险标签，作为一个特征加进现有截面排序；看 IC 增量，并跑错配申报文件的安慰剂。增量为正且符号稳定才扩大。
- done_when: 结论写进登记簿。
- notes:
  - 2026-09-28 交互会话派 Sonnet 执行，正在打分。自动轮不要碰。

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

### T-20260929-33 加密货币趋势（Alpaca 现货，只做多）批量筛选
- status: running
- priority: 1
- not_before:
- goal: 机主 2026-09-29 放开范围后，加密货币是模拟盘支持、但从没按趋势规则系统测过的品种（以前只看过高频加密模型，判为不可行）。看已发表的趋势/动量规则能否达到 K1，或给 S3 加分（K2）。
- plan: 先联网找 2023–2026 的加密趋势实盘或前向记录和反面证据；数据用 Alpaca 加密日线（本机取，密钥不上传）或交易所公开数据；候选 10–20 条已发表规则（时间序列动量、均线过滤、双动量、波动率目标），全部偏移中位数、20 bp、安慰剂、K2；每天 24 小时交易，按 UTC 日收盘。
- done_when: 迭代档案 + 登记簿 + 提交。
- notes:
  - 2026-09-29 07:07 UTC 自动轮开始，派 sonnet-high 子代理执行（批量通道新增 `extend_panel` 钩子，提交 4a0775a）。

### T-20260929-34 单只股票加杠杆趋势（S3 的个股版）
- status: running
- priority: 2
- not_before:
- goal: S3 用杠杆板块 ETF 抓领涨赛道。个股版：在大盘龙头股里按动量选前 1–3 只，用 2 倍（合成的 2 倍日重置收益，2022 年后可用真实的 2 倍单股 ETF，如 NVDL；或保证金 2 倍）。检验能否达到 K1，或和 S3 组合后夏普更高。
- plan: 菜单 = 当时市值前 20–50 的股票（按时间点，不能用今天的名单）；合成 2 倍日重置收益，扣费率和融资成本；照搬 S3 的规则框架（63 日动量、绝对动量过滤、vt40），全部偏移中位数、安慰剂、K2。
- done_when: 迭代档案 + 登记簿 + 提交。
- notes:
  - 数据清洗（2026-09-29，另一会话在 T-20 踩到）：`data/sip/daily` 有破产后重新上市沿用旧代码（WOLF）、单日错误成交价（KIDZ、IXHL）、漏调的拆股（APH 2026-08-27）。个股回测必须先过 `open_composer.research.features.price_hygiene.sanitize_price_matrices(close_wide, open_wide)`（默认参数），并剔除触发日像拆股的信号；不要按持有期结果过滤。
  - 2026-09-29 07:07 UTC 自动轮开始，派 sonnet-high 子代理执行（批量通道新增 `extend_panel` 钩子，提交 4a0775a）。

### T-20260929-35 日内截面规律（分钟数据，Modal）：日内周期性、隔夜/日内拉锯
- status: blocked（等机主决定日内成本口径）
- priority: 2
- not_before:
- goal: 已发表的截面日内规律，例如 Heston-Korajczyk-Sadka 2010 的同一时段收益延续，以及 Lou-Polk-Skouras 2019 的"动量赚在隔夜、反转赚在日内"，在流动性最好的股票上能否扣掉实际成本后赚钱。
- plan: 先联网找 2020 年以后的复现；成本按分钟数据估计的价差另建日内合同，同时报告冻结的 10/20 bp。
- done_when: 迭代档案 + 登记簿 + 提交。
- notes:

### T-20260929-36 纳斯达克 1 分钟多空事件路由：用 SIP 分钟数据复核
- status: ready
- priority: 2
- not_before:
- goal: 登记簿 `dir:nasdaq_long_short_event_router_1m` 在 IEX 派生的 1 分钟数据上达到 research_pass（lookback=10、entry_after_bars=2、QQQ 前一段为负时才做），但没用正式 SIP 数据验证，而且当时不能做空。
- plan: 读原档案，用 `data/sip/minute`（Modal）按原规则重跑，不改参数；同时报告冻结 10/20 bp 和实测价差两种成本；安慰剂。
- done_when: 迭代档案 + 登记簿 + 提交。
- notes:
  - 数据清洗（2026-09-29，另一会话在 T-20 踩到）：`data/sip/daily` 有破产后重新上市沿用旧代码（WOLF）、单日错误成交价（KIDZ、IXHL）、漏调的拆股（APH 2026-08-27）。个股回测必须先过 `open_composer.research.features.price_hygiene.sanitize_price_matrices(close_wide, open_wide)`（默认参数），并剔除触发日像拆股的信号；不要按持有期结果过滤。

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
- status: ready
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
- status: ready
- priority: 2
- not_before:
- goal: 机主研究清单第 1 项。单季 SUE 在我们的数据上已否定（`dir:pead_xbrl_sue_filing_date`、`dir:pead_xbrl_8k_llm`），原文的新意是用过去多个季度的 SUE 序列训练 elastic net，并且说增益在大盘股里最强。检验它在我们的 SEC XBRL 数据上，是否比单季 SUE 和动量有增量。
- plan: 先打开原文（Finance Research Letters 2025）和 Wang 等（OR Spectrum 2025），记下特征、标签和样本外设计。特征用 `data/features/sec_fundamentals_daily` 的 sue_eps/sue_rev，按申报可见日取过去 8 个季度，加连续超预期次数。选择窗 2016-06→2023-12 训练 elastic net（时间序列交叉验证选正则），测试窗 2024-01→2026-09 只跑一次。报告测试 IC、前 50 只月度组合在 10/20bp 下的夏普、和单季 SUE 及 12-1 动量的对比，以及和 S3 的相关性。按运行手册第 5 节判定，另外报告扣掉 SPY/QQQ 贝塔之后的超额。
- done_when: 迭代 `--stage final` 通过；登记簿新增 `dir:ml_multiquarter_sue_history`。
- notes:
  - 2026-09-29 交互会话添加（机主给的研究清单第 1 项）。

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
- status: ready
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

### T-20260929-04 内部人集群买入：补测 H-20260916-08 唯一还空着的精确设计（top-500 池、周频）
- status: ready
- priority: 3
- not_before:
- goal: 登记簿里 `dir:insider_cluster_buy_top500` 明确写着"top-500/周频这个精确设计仍未测试"（`H-20260916-08`，2026-09-16 立项后一直排在其它卡片后面、预算 3 用了 0）。这是内部人集群买入方向里唯一还留白的精确 scope；两头都已经关闭：作为事件特征已采纳但很小（CAR +0.78%/20 日，t=5.0；`reports/research/signal-cards/insider_cluster_buy.md`），作为全池月频独立策略在 1501+ 档已被否定（跑输同波动 SPY，`dir:insider_buy_independent_broad_universe`）。**预期不高**——两头都已经不理想，周频换手只会加成本——排这个任务主要是花几分钟把登记簿这最后一条空白关掉，不是一个有前景的新线索。不需要新数据，直接复用已有 Form 4 特征和 `signal_card.py`。
- plan: |
    直接用 `open_composer.research.signal_card` `--mode event`：`--source` 指向 `data/features/insider`（或 `insider_broad`，两者都已确认存在且覆盖到 2026），`--column` 用 `buyers_60d`（或等价的集群买入计数列，跑之前先 `python3 -c "import pandas as pd; print(pd.read_parquet(...).columns)"` 核对实际列名），`--where`/`--sql` 限定 `top_n=500`（H-20260916-08 原始设计的 top-500 池）、事件定义为 `buyers_60d>=2`，信号日期为每周五（周频，照抄 H-20260916-08 卡片里"weekly, top-500 pool, equal-weight up to 30 names"的设计，不要改成月频或改变阈值）。`--primary-horizon 20`（约等于原设计的持有期，若原卡片写的是不同持有期，以卡片为准并在结果里注明与卡片一致）。数据量小（只是 top-500 池的事件表 + 已有 insider 特征），本机内存放得下，不需要 `run_capped.sh`。
    判定：同 T-20260929-03，读 `card["flags"]` 四项；因为已有两个非常接近的变体都失败，这次结果无论真假都应该直接写成对整个 `insider_cluster_buy_independent` 家族的收尾判断（不要因为"万一这次不一样"而放宽判定标准或加做变体）。
- done_when: signal card 生成在 `reports/research/signal-cards/`；`dir:insider_cluster_buy_top500` 和新建的 `dir:insider_cluster_buy_top500_weekly_independent` 都从 queued/partial 更新为终态，带 verdict、evidence、reopen_if；在 `current-view.zh.md` 的下一次更新里注明"内部人集群买入方向的三个 scope（事件特征、月频全池、周频 top500）已全部有定论"。
- notes:
  - 2026-09-29 gap search (`gap-search-2026-09-29-04`) 添加。

### T-20260929-21 交互会话：IPO 解禁期漂移（Field & Hanka 2001；做空 easy-to-borrow + 保守借券成本）
- status: doing
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
