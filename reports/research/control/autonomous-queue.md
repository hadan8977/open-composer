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
- status: running
- priority: 1
- not_before:
- goal: 机主的标准是夏普（2026-09-28）。S3 不挑调仓日的夏普：对标窗约 1.5、选择窗约 1.15、2016–2023 约 0.8（H-20260928-01）；它和 S1、S2 高度同向，所以三者合并只等于降仓（H-20260927-01）。提高夏普的正路是加一条熊市里和 S3 不同向、自身夏普也不差的收益来源。先试已发表、规则公开的跨资产趋势：债券、黄金、商品、美元。
- plan: (1) 联网读原文并登记来源：Defense First（登记簿 `dir:defense_first_taa_carlson_concretum`，代码 `scripts/run_h20260923_12_s3_defense_first.py` 的 `defense_weights`；上次 `dir:s3_defense_first_remainder` 只用它替换 S3 的闲置现金，这次是独立 sleeve 按风险加权，direction-review 里写清楚区别）；跨资产时间序列动量（Moskowitz, Ooi & Pedersen 2012；Hurst, Ooi & Pedersen 2017）的 ETF 做法。(2) 预注册、不调参：D1 = Defense First 独立 sleeve（按原规则）；D2 = TLT、GLD、DBC、UUP 各自在过去 12 个月收益高于 SHY 时持有，按过去 63 天波动率倒数分配，否则放 SHY，月度调仓。所有月度 sleeve（D1、D2 和 S3）都用 4 批调仓版本（偏移 0/5/10/15 个交易日，照 `scripts/run_h20260928_01_s3_rebalance_tranching.py` 的 T4），不挑调仓日。(3) 组合 M_D1、M_D2 = S3 与 D 按过去 63 天波动率倒数月度加权；对照 = k·S3 + (1−k)·SHY，k 在每个窗口单独求，使波动与组合相同。(4) 判定按 `docs/runbook-autonomous-round.zh.md` 第 5 节"判定分档"（机主 2026-09-28 放宽）：K2 组合夏普比对照高 ≥0.05 且对标窗和压力期（2016-05→2023-09-15）同时成立为"保留"，≥0.10 为"强保留"；D 单独的偏移中位数夏普两窗都达到 S3 的八成（1.19、0.65）也算保留（K1）。另报告 D 单独的夏普、D 与 S3 的日收益相关（压力期、对标窗、2022 年）；2026 年受污染，只作参考。(5) 通过了才做下一步（把 D 换成杠杆版本，让组合收益回到 G1 水平），不在本任务里做。
- done_when: 迭代 `--stage final` 通过；假设卡、decision record、登记簿行 `dir:cross_asset_trend_sleeve_with_s3`、覆盖地图 `portfolio.combination_and_risk` 更新；current-view 顶部最多 5 行。
- notes:
  - 2026-09-28 03:15 UTC 交互会话派 Sonnet 用批量通道执行（迭代 h20260928_02_cross_asset_sleeve；按偏移中位数判定，替代原写的 4 批版本，结果出来前已定）。自动轮不要碰。
  - 2026-09-28 交互会话补充的本地先例（写任务时漏查了，必须先读）：Step 10 W1 F2（约 09-04）已经单独测过跨资产 ETF 时间序列动量，12 个候选 0/12，最好的超额夏普 0.65；危机窗口跌得比 SPY 少但仍然亏（2022 −10.1%，2020 崩盘 −12.5%，2018Q4 −8.1%）。结论 `reports/research/control/step10-w1-cross-asset-trend-2026-09.md`，机制代码 `open_composer/research/kernel/mechanisms/cross_asset_trend_etf`，评估脚本 `scripts/evaluate_cross_asset_trend_sip.py`。能复用的数据和代码直接复用。本任务和它的区别是：不看 D 单独过不过门槛，只看和 S3 组合后的夏普增量。direction-review 里写清楚这个区别；如果 D2 的规则和 Step 10 的某个候选相同，要注明是同一规则重测。

### T-20260928-05 登记簿补录 2026-09-23 以前的实验
- status: running
- priority: 1
- not_before:
- goal: 方向登记簿是 09-23 建的，没收录更早的实验，所以写新任务时会漏查本地先例（09-28 就漏了 Step 10 的跨资产趋势 0/12）。补齐后，每个新方向查重一次就能看到本地是否测过，省掉重复测试。
- plan: 轻活，不跑回测。(1) 列出 `reports/research/iterations/` 下所有不以 `h2026` 开头的档案，以及 `reports/research/control/` 里带结论的报告（`grep -l "结论\|verdict\|0/[0-9]" reports/research/control/*.md`）、`reports/research/ledger/experiments.jsonl` 里的 family。(2) 每个机制或家族用 `uv run oc research directions check <关键词>` 查重；登记簿已有就只在 evidence 里补路径，没有就追加一行：status 按原结论（refuted / partial / passed / evidence_too_weak），verdict 一句话带关键数字，evidence 写报告路径，`found_by` 写 `backfill-2026-09-28`，`reopen_if` 写原报告建议的重开条件。(3) `uv run oc research directions validate` 必须 ok。不改已有行的 status。
- done_when: 补录行数和清单写进 `reports/research/control/registry-backfill-2026-09-28.md`（每行：方向 id、原报告路径、结论）；validate ok；提交。
- notes:
  - 2026-09-28 03:15 UTC 交互会话派 Sonnet 执行，同时判定 11 个文本和方法类方向。自动轮不要碰。

### T-20260928-06 按新标准重判登记簿，生成批量测试清单
- status: running
- priority: 1
- not_before:
- goal: 登记簿里 71 个方向只收进来没判断过，55 个标"证据不足"，当时的标准是"单独能否高收益"。机主 2026-09-28 把标准改成"夏普和 S3 差不多，或能给 S3 加分"，一部分旧方向在新标准下值得批量测。目标是把能批量测的挑出来，排成下一批、下下批。
- plan: 轻活，不跑回测。(1) 读 `docs/runbook-autonomous-round.zh.md` 第 5 节"判定分档"。(2) 对 status 为 harvested、evidence_too_weak、triaged、queued 的行逐条判断：能不能只做多、用日线数据、按公开规则写成一个每月或每周给出目标权重的函数（能 / 不能及原因）；在新标准下的先验（高 / 中 / 低，一句理由：已知的夏普、和 S3 可能的相关性）。(3) 能写成函数、先验不低的，按主题分组，每组 10–30 条，作为一个批量任务写进本队列（格式照第 9 节，plan 里列出每条规则的出处和规则要点）。(4) 登记簿里被判断过的行把 status 改成 `triaged`，verdict 写一句结论；`uv run oc research directions validate` 必须 ok。不改 refuted / passed 的行。
- done_when: `reports/research/control/retriage-2026-09-28.md`（逐条表格 + 分组）；队列新增批量任务；validate ok；提交。
- notes:
  - 2026-09-28 交互会话拆给三个代理：ETF 类 24 条（迭代 h20260928_05_registry_etf_batch2）、股票/日内/事件/模型类 25 条（h20260928_06_registry_stock_batch3，当天测）、文本和方法类 11 条（随 T-20260928-05）。自动轮不要碰。

### T-20260928-07 保留候选的前向跟踪（影子）
- status: ready
- priority: 2
- not_before:
- goal: 前向证据只能按日历时间积累。保留下来的候选越早开始跟踪，越早知道它在没见过的数据上是否还成立。日线 ETF 规则是确定的函数，所以不需要每天下单：把规则连同代码版本在保留当天冻结，之后任何时候都能诚实地复算"保留日之后"的表现。
- plan: 前置条件：`reports/research/screens/SELF_CHECK_OK` 存在（批量通道已由交互会话核对）。不存在就跳过本任务，选下一个。(1) `reports/research/screens/kept.jsonl`：每个保留候选一行（id、批次、保留日期、提交哈希、候选模块和 id、档位 K1/K2、保留时的关键数字）。(2) `scripts/shadow_forward.py`：读 kept.jsonl，用 `scripts/screen_lane.py` 的同一套引擎，只算保留日之后的日收益，报告累计收益、夏普（样本不足 20 个交易日就只报收益）、同期 S3 和 SPY，并检查代码版本和冻结时的一致（不一致就报警，不算）。(3) 测试用合成数据。(4) 写 `reports/research/screens/forward.md`。以后每周一的第一轮刷新一次（加进本队列作为长期任务）。
- done_when: 脚本、测试、forward.md 生成；ruff 和相关测试通过；提交。
- notes:

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
- status: ready
- priority: 1
- not_before:
- goal: 以前按 10-Q/10-K 申报日测的盈余意外（SUE）已否定，当时写的重开条件就是"改用 8-K 2.02 财报公告的时间"。这一步不用大模型，今天就能测。
- plan: 按 `reports/research/control/registry-backfill-2026-09-28.md` 的 Job B 计划：复用 fundamentals-v1 信号卡流程和它的"改日期"安慰剂，只把 `visible_at` 换成 8-K 2.02 附件的接收时间；按原来的准入规则判断（逐年稳定、赢安慰剂、10/20 bp 下过 G1），另按 K1/K2 报告。重任务，同一时间只跑一个，跑在第三批（h20260928_06）结束之后。
- done_when: 迭代 `--stage final` 通过；登记簿新行；只有过了准入规则，才在队列加大模型读语气的第二阶段。
- notes:

### T-20260928-15 Claude 写因子的小批量（`dir:llm_hypothesis_code_backtest_loop` 的方法）
- status: ready
- priority: 2
- not_before:
- goal: 检验"大模型提假设、写因子代码、按 IC 反馈"这个方法在我们的数据上能不能比现有因子库（Alpha101/158/191/OSAP）更好。只写代码，不做批量标注。
- plan: 预注册 5–10 个有经济逻辑的因子（写出假设和出处），一次写完不再按结果改；用现有的 IC/RankIC 流程在最近的样本外段筛；判断标准只有一条：这批最好的因子是否超过现有库最好的因子（同一样本段、同一成本）。
- done_when: 结论和数字写进登记簿；超过了才把这个方法写进自动轮手册。
- notes:

### T-20260928-16 DeepSeek 试点：8-K 情绪加速度（一季度 IC）
- status: ready
- priority: 2
- not_before:
- goal: `dir:llm_8k_gdelt_sentiment_acceleration` 的最便宜否定测试。
- plan: 按 `reports/research/control/registry-backfill-2026-09-28.md` Job B 的计划。打分只用机主配置的 DeepSeek 接口，不用 Claude。先算最近一个季度的 IC（对未来 5 日收益），同时跑打乱新闻的安慰剂。IC 符号不稳、或安慰剂也能复现，就停，不搭完整的走步验证。
- done_when: IC 和安慰剂结果写进登记簿；决定继续或停止。
- notes:

### T-20260928-17 DeepSeek 试点：10-K/8-K 风险标签特征（400 份）
- status: ready
- priority: 2
- not_before:
- goal: `dir:text_to_pit_feature_extraction` 的最便宜否定测试。
- plan: 按同一份报告 Job B 的计划：50 只股票 × 8 个季度，DeepSeek 抽取结构化风险标签，作为一个特征加进现有截面排序；看 IC 增量，并跑错配申报文件的安慰剂。增量为正且符号稳定才扩大。
- done_when: 结论写进登记簿。
- notes:

### T-20260928-18 补 VIX 和 PUTW 数据，再测两条 ETF 规则
- status: ready
- priority: 2
- not_before:
- goal: 第二批里有两条只因缺数据没测：`dir:spy_sso_tlt_vix_regime_rotation`（缺 VIX）、`dir:put_credit_spread_income`（卖 put 的 ETF 代理 PUTW 缺数据）。
- plan: VIX 用 FRED 公开的 VIXCLS 日数据，PUTW 走仓库现有的日线入库流程；两种数据都要先确认日期对齐、没有未来信息。然后新开一个小批次，走批量通道（先写档案和候选清单）。按日历触发的规则声明成 "D"。
- done_when: 两条的结论写进登记簿。
- notes:

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
- status: blocked（只等 08 运行器的一致性检查通过）
- priority: 1
- not_before:
- goal: 回答"多种免费数据合进一个模型，能否在流动性好的股票上给出只做多、扣成本后的超额"。按 09 的预注册执行。
- plan: 预注册草稿见 `reports/research/intel/I-20260928-02-modal-lane-ml-cnn.md` A.4（12 个候选；否定测试只跑候选 5、6、11，只看压力期，走步验证 RankIC ≥ 0.02 且比纯量价基线高 ≥ 0.01 才进完整评估）。先建迭代档案、direction-review、候选清单，过 direction-check 和 pre-backtest 检查再上 Modal。约定：机主 2026-09-28 说流动性低的股票他也能交易，所以股票池不限大盘：Alpaca 可交易的美股普通股、价格 ≥ $3、21 日成交额中位数 ≥ $100 万；成本按每只股票估算（10 bp + 半个估计买卖价差，压力情形 20 bp + 整个价差），单只仓位不超过 21 日成交额的 1%，结果按流动性三档分开报；走步训练、隔离期，10/20 bp；分两段花钱（机主 2026-09-28：尽量少花）：否定测试 ≤ $1，只看 2016–2023 压力期的排序 IC 是否明显高于纯量价基线（H-20260917-02 岭回归 IC 0.007），不高就停，不看对标窗；过了才做完整评估（≤ $3），按 K1/K2 和 G1–G5 判。
- scope_2026-09-28: 机主问"LightGBM、调参、结合别的因子和策略不值得做吗"。本任务就是这个方向的主线（ML 工厂），范围定为：特征 = 量价（Alpha158/101、OSAP 价格类）+ 财报（XBRL，按申报日）+ 内部人 + 空头/卖空量 + 财报日 + 现有规则策略的信号（12-1 动量、内部人集中买入、ROE 等作为特征，让模型决定权重）+ 市场状态（SPY 趋势、波动率、板块相对强弱）；模型 = LightGBM 回归和 LambdaRank 为主，完整评估时加 CatBoost 和一个小 MLP 做等权集成；调参只在每个走步训练窗内部的验证段用 Optuna，每个模型最多 30 次，测试段不参与；标签 5/10/21 日，截面去均值并做行业/贝塔中性化；组合 = 只做多前 N 只加持仓缓冲降换手，按每只股票价差计成本；最后单独报它和 S3 按波动率倒数组合的夏普增量（K2）。否定测试仍按 A.4：只跑候选 5、6、11，只看压力期 RankIC。按机主要求直接训练、看结果，不另写长篇计划。
- design: 总体策略设计（两个引擎 + 分配层、推进顺序、接入模拟盘）见 `reports/research/control/ml-strategy-design-2026-09-28.md`；本任务是其中第 1–3 步。
- features_add_2026-09-28: I-20260928-04（JKP 因子库）2023 年以来唯一显著多于运气的一族是会计变化类（经营现金流/资产变化、季度利润/资产变化、利润/净资产变化、连续 8 季利润增长；2010–2022 年接近 0，2023 年起转强）。能用 `data/features/sec_fundamentals_daily` 算的 `ocf_at_chg1`、`niq_at_chg1`、`niq_be_chg1`、`ni_inc8q` 加进特征；只做多一侧单独夏普 <1，不单独做策略。
- done_when: 迭代 `--stage final` 通过；登记簿、覆盖地图、current-view 更新。
- notes:

### T-20260928-11 Modal：K 线图像 CNN 否定测试（依赖 08、09，GPU）
- status: blocked（机主 2026-09-28 暂不做：觉得不靠谱；不是被证据否定，登记簿标 parked）
- priority: 2
- not_before:
- goal: 这是本地唯一有独立复现、而且只缺 GPU 的方法。先做最便宜的否定测试：训练 2016–2019、验证 2020、测试 2021–2023，流动性前 1000 只做多最高一组，10 bp。
- plan: 待 09 定稿；复用 MIT 许可的复现代码（George-hardworking/reimaging-price-trends-replication-and-extension）。测试期最高组对全池的超额 t 值 <2 就停。分两段花钱：否定测试 ≤ $1.5（T4），过了才做对标窗完整评估（≤ $3）。排在 10 之后，10 的否定测试先出结果。
- done_when: 否定测试结论写进迭代档案和登记簿；过了再开对标窗检验。
- notes:

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
- status: ready
- priority: 1
- not_before:
- goal: 个股动量 top-30 账本 2024 年以来 59.8%/年、但回撤 −41.6%（门槛 −35%，`docs/current-view.zh.md` 2026-09-24 11:30 章节）。机主下一步已排了一个按文献（Daniel-Moskowitz）配方的规则型防崩盘开关；本任务测一个训练出来的替代/补充：arXiv 2603.13252 "When Alpha Breaks" 给排序模型加一个两层不确定性框架——策略层的"机制信任门"（论文里 2024 年这段 AUROC 0.72–0.75）和个股层的认知不确定性上限（DEUP，用集成分歧预测排名误差）。这篇论文自己的发现——排序模型的信号恰好在 2024 年 AI 行情和板块轮动里失效——和我们自己已经发现的问题（动量账本 2024 年以来回撤失控）是同一个现象的独立印证。和已否定的规则型止盈开关（`dir:momentum_risk_control_vs_spmo`，输给日历平移安慰剂）、已否定的仓位分档元标签（`dir:meta_labeling_position_tiers`，等价于直接降仓）机制不同：这是训练出来的置信度信号，不是固定规则或单调仓位分档。
- plan: 只用本地已有数据（Alpha158 类量价特征 + 已有的 top-30 动量账本，`open_composer/research/signal_card.py`），不需要新数据。(1) 预注册：训练 k=15 个 bootstrap LightGBM 回归器（2016–2023 走步训练）预测 20 日远期收益，集成分歧作为 DEUP 式认知不确定性代理；机制信任门 G(t) = 每日截面不确定性分位数，高不确定性日对 top-30 账本减仓（先定好减仓比例，不事后调）。(2) Modal 否定测试（≤$1.5）：4 核/8GiB/45 分钟 = (4×0.0473+8×0.008)×0.75h ≈ $0.19。停止条件（先定）：门槛信号在 2024–2026 留出窗上，标记"账本回撤高于中位数的日子"的 AUROC < 0.60（论文自己的数字是 0.72–0.75，0.60 是保守下限，不是照抄论文数字），或者，用同样天数的随机日减仓做安慰剂对照，门槛版本的最大回撤改善不到 5 个百分点——两条任一命中就停，登记 refuted，不进第二段。(3) 过了才做第二段（≤$2，6 核/16GiB/90 分钟 ≈ $0.62）：按冻结合同的对标窗、压力期，K1/K2 和 G1–G5 判定，需要安慰剂。本机内存也可能装得下（规模不大），先按 Modal 预算走，执行时可以判断是否本机就能跑。
- done_when: 迭代 `--stage final` 通过（或第一段否定停止，写清原因）；登记簿行 `dir:regime_trust_uncertainty_gate_momentum_ranker` 更新为最终状态；本月 Modal 花费写进汇报（`python3 scripts/modal_budget.py status`）。
- owner_rule_check: 机主规则（2026-09-28）：减仓本身不算改进。本任务的通过线必须是夏普：门控后的账本（调仓日偏移中位数，10 bp）在对标窗和压力期的夏普都比"不门控、调到同样波动"的账本高 ≥ 0.10；只降回撤、夏普不升就判否定。按机主 09-28 的要求直接训练、看结果，不另写长篇计划。
- notes:

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
- status: running
- priority: 1
- not_before:
- goal: 一次用同一套合同评估 10–30 条规则，内置"不挑调仓日"和"同波动 S3 对比"，按本批候选数报告 DSR；上线前必须精确复现 H-20260928-01 和 H-20260927-01 的数字。
- plan: 交互会话派 Sonnet 在做：`scripts/screen_lane.py`、`scripts/screen_batch.py`、`scripts/screen_batches/smoke_20260928.py`、`tests/test_screen_lane.py`。交互会话核对 `--self-check` 后创建 `reports/research/screens/SELF_CHECK_OK`。
- done_when: SELF_CHECK_OK 存在；提交。
- notes:
  - 2026-09-28 02:4x UTC 交互会话开始（自动轮不要碰）。

### T-20260928-04 第一批：S3 的替代与搭配候选库
- status: running
- priority: 1
- not_before:
- goal: 用批量通道一次判 15–25 条有实盘记录或独立复现的只做多规则：可能和 S3 差不多的（K1），或能给 S3 加分的（K2）。
- plan: 交互会话派 Sonnet 做联网调研和预注册（来源卡、direction-review、候选清单、候选模块），批量通道核对通过后运行。不含 T-20260928-02 的 D1、D2。
- done_when: 迭代 `--stage final` 通过；保留的候选写进 `reports/research/screens/kept.jsonl`；登记簿、覆盖地图、current-view 更新。
- notes:
  - 2026-09-28 交互会话负责（自动轮不要碰）。

### T-20260927-03 新规则下第一次月度调仓核对
- status: ready
- priority: 1
- not_before: 2026-10-02 01:00 UTC
- goal: 09-30 收盘后 S2、S3 按新规则第一次月度调仓，10-01 开盘成交。核对模拟盘和研究引擎是否一致、成交质量如何，这是以后实盘的前置证据。
- plan: 读 `reports/execution/us_etf_levered_rotation_63_top2_monthly-target-weights.json` 和 S2 的同名文件（09-30 生成的目标），用 `uv run python scripts/check_rotation_overlay_parity.py` 复算 09-30 的研究引擎决定；读三条 sleeve 的 `reports/paper/rehearsal/<name>-fills.jsonl` 里 2026-10-01 的成交，看 `slippage_vs_open_bps`、是否全部成交；读 `reports/paper/alerts.md`。
- done_when: `docs/current-view.zh.md` 顶部 5 行以内的结论（一致 / 不一致及原因、滑点、有无撤单）；不一致或有撤单时在队列加修复任务。
- notes:

### T-20260927-04 修看板里的额度百分比读数
- status: running
- priority: 3
- not_before:
- goal: 2026-09-27 `open_composer.cockpit.data.quota` 读到 5 小时窗口 1000%、7 天窗口 100%、状态 stale，明显解析错了。修好后，看板能显示真实额度，自动轮以后也可以按真实额度决定跑不跑。
- plan: 用模块自己的函数取数据，只打印返回结构的键名和数值类型、数值，**绝不打印或写出令牌**；对照 `_parse_window` 找出单位或字段名变化（例如 0–1 比例和 0–100 百分比混用）；改解析并加测试（`tests/test_cockpit_quota.py` 已有 MockTransport 夹具）。不要改凭据读取逻辑。
- done_when: 相关测试通过；实测读数在 0–100 之间且有 `resets_at`；在自动轮日志摘要里写一句。
- notes:
  - 2026-09-28 交互会话派 Sonnet 在做（自动轮不要碰）：接口的 utilization 已经是百分比、resets_at 是 ISO 字符串；预检输出加 `quota`；随后按额度方案 A 改预检的判断。

### T-20260927-05 月度覆盖检查（第一次）
- status: ready
- priority: 3
- not_before: 2026-10-05 01:00 UTC
- goal: 按 `docs/plan-research-coverage-2026-09-23.zh.md` 第 4 节，每月检查覆盖地图还有哪些格子没搜过、没测过，避免重复和遗漏。
- plan: `uv run oc research directions summary`；统计 `reports/research/harvest/coverage.json` 各格子的方向数和状态；对照 `reports/research/harvest/feed-digest-2026-09-27.md` 找没人覆盖的格子；列出下个月最多 3 个搜索或测试任务写进本队列。
- done_when: `reports/research/control/coverage-check-2026-10.md` 写好；队列新增任务。
- notes:

### T-20260928-01 S1、S2 的调仓日运气检查
- status: ready
- priority: 3
- not_before:
- goal: H-20260928-01 发现 S3 的月末调仓日在近期窗口是 21 个日子里最好的，头条数字有一大块是运气。S2（月度）和 S1（周度）也按固定日子调仓，要知道它们的数字里有多少是调仓日运气，才能给每条 sleeve 一个"不挑日子"的预期，供续期和以后实盘定规模用。
- plan: 复用 `scripts/run_h20260928_01_s3_rebalance_tranching.py` 的做法（新迭代，先过 direction-check 和 pre-backtest 检查）：S2 用续期规格（vt 0.156）做月末后 0–20 个交易日共 21 个偏移；S1 做周末后 0–4 个交易日共 5 个偏移。纯描述：报告每个窗口的最小/中位数/最大值和现行版本的排名，不采用任何偏移。只有描述、没有通过条件；现行版本排名前 3 且中位数低于它 20% 以上时，在决定页和 current-view 写"不挑日子"的数字。窗口和成本按冻结合同，压力期 2016-05→2023-08（S1 因 252 日回看从 2017-01 起）。
- done_when: 迭代档案 `--stage final` 通过；登记簿行 `dir:s1_s2_rebalance_timing_luck`；current-view 最多 3 行结论。
- notes:

### T-20260928-19 每周一刷新前向跟踪
- status: ready
- priority: 3
- not_before: 2026-10-05 01:00 UTC
- goal: 前向证据只能按日历时间积累；`kept.jsonl` 里保留/近期观察的候选需要每周刷新一次前向表现，不必每天跑。
- plan: 跑 `scripts/run_capped.sh --mem 1.2G -- uv run python scripts/shadow_forward.py`；读 `reports/research/screens/forward.md`。只有某候选移出（`watch_exit.status == "exit"`）或新跨过阈值（前向夏普首次跌破 0.5、前向最大回撤首次超过对标窗回撤的 1.5 倍）时，才往 `docs/current-view.zh.md` 加不超过 3 行摘要；没有变化就不写。跑完把本任务的 `not_before` 改到下一个周一 01:00 UTC。
- done_when: `forward.md`/`forward.json` 已刷新；`not_before` 已推到下一个周一；必要时 current-view 已更新。
- notes:
