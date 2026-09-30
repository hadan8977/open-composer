# 用 GRPO 等强化学习训练 8B 以上 Qwen 类大模型做交易：谁在做、结果、规模、Qwen3.8 事实、算力费用、前视（任务码 R0930-1405-GRPO）

日期 2026-09-30，联网抓取 UTC 18:38–19:00。只调研，没有训练、没有调用 Modal、没有下单。来源快照在 `reports/research/intel/sources/grpo-qwen-2026-09-30/`（文件名即来源，全部 .txt）。上一份简报 `reports/research/intel/rl-llm-trading-evidence-2026-09-30.md`（下称"上份简报"）已覆盖的内容只引用其行号/条目，不重写；它的快照在 `sources/rl-llm-2026-09-30/`，本次重读了其中 Alpha-R1、Trading-R1、StockBench、LiveTradeBench、InvestorBench、AMA 的文本，没有重新联网抓取。

时间说明：机主的反驳约在 2026-09-30 18:35 UTC，主审的检索摘要约在 18:36 UTC（协调者更正过）。

## 结论（6 行）

1. **谁在做**：真正用 RL 训练 ≥7B 模型做交易/选股、并在论文里报回测的只找到 4 组：StepFun/FinStep + 上海交大的 Alpha-R1（Qwen3-8B，GRPO）、港科大的 AlphaQuanter（Qwen2.5-7B，verl GRPO）、南洋理工/Skywork 的 FinWorld 里的 FinReasoner（Qwen3-8B，verl GRPO）、帝国理工的 FinSMART（Llama-3-8B，LoRA GRPO）。≥14B 的 RL 交易结果一个也没找到。公司端：nof1 自称"用大规模 RL 训练新基座模型"但没有任何结果；对冲基金和中国量化私募（幻方、九坤、明汯）没有公开过"LLM + RL 训练用于交易"的结果，九坤公开的 Logic-RL 是数学推理，不是交易。
2. **可信度**：全部是回测，没有一个有实盘或前向记录，没有独立复现。只有 Alpha-R1 同时满足"截止日后窗口 + 每边 10 bp + 有买入持有基线"（12 个月，标普 500 池 47.87%/夏普 1.62，上份简报第 12 行）。FinSMART 的夏普 1.97 测试窗是 2019–2021、全文没有交易成本设定；AlphaQuanter 测试 5 只股票 6 个月。
3. **规模证据**：没有任何"同一族模型、同一 RL 流程、扫描 7B–70B"的对照。零样本比较里，"越大越好"在截止日后的前向窗口不成立（LiveTradeBench：Qwen2.5-72B 5.15% > Qwen3-235B-Instruct 3.52% > Thinking 1.78%；StockBench：Qwen3-235B 与 Qwen3-30B 只差 0.4 个百分点；AlphaQuanter：1T 的 Kimi-K2 为 -1.65%、7B 为 +4.49%），只在窗口落在模型训练数据内的基准里成立（InvestorBench 2020–21，Trading-R1 零样本 Qwen3-32B 对 4B）。RL 带来的增益比换大模型大：AlphaQuanter 的 7B RL 平均年化 34.94% 对买入持有 12.90%，零样本 GPT-4o 的 TradingAgents 是 16.49%。
4. **Qwen3.8 截止日**：官方没有发布。Qwen3.8-27B 模型卡没有任何截止日文字；唯一的线索是 HF 讨论串里用户转述"问模型，它答 early 2025"（模型自报，Qwen 维护者自己说不可靠）和第三方称 Qwen3.5 起 DashScope 系统提示里只写年份"2026"。所以**无法确定它的样本外起点**。27B 许可证 Apache-2.0，HF 仓库创建 2026-08-05、最后修改 2026-08-14、8-14 已公开。
5. **最小可信实验费用（Modal 价，估算，误差约 2 倍）**：Qwen3.5-9B（Qwen3.8 没有 9B/8B/14B/32B，见第 3 节）+ LoRA + GRPO，100 步 × 32 提示 × 8 采样，单次约 4.5–6.6 H100 小时 = **$18–26**；同口径 Qwen3.8-27B 用 H200，约 12.8–19.2 小时 = **$58–87**。可信的实验至少要 3 个种子加 1 个打乱奖励的安慰剂，共 4 次：9B 约 **$70–105**，27B 约 **$230–350**。仓库的 Modal 月上限是 $25（`scripts/modal_budget.py`），只有 9B 的单次运行放得进去；27B 和多种子都超出，需要机主决定。
6. **干净测试窗**：取决于没人知道的截止日。三种情形（按美股交易日数，到 2026-09-30）：截止日 early 2025（自报，不可靠）则 2025-04 起约 377 个交易日（约 17.5 个月）；截止日在 2026 年初则约 187 个交易日（约 9 个月）或更短；最保守按发布日 2026-08-14 起算只有 33 个交易日。老一代 Qwen3-8B/14B/32B 的截止日有 OpenRouter 记录 2025-03-31，窗口 2025-04 起约 377 个交易日，但模型较弱。

## 1. 谁在做（组织与工作表）

图例：RL ≥7B = 被 RL 训练的模型参数量 ≥7B。"结果"栏是原文数字，来源为快照文件。全部未见实盘或前向记录（除另注）。

### 1.1 学术与开源（有 RL 训练）

| # | 工作 / 组织 | 模型与规模 | RL 方法与框架 | 输入 | 训练截止 vs 测试窗 | 成本假设 | 结果（原文） | 实盘/前向 | 代码与权重 |
|---|---|---|---|---|---|---|---|---|---|
| 1 | **Alpha-R1**（StepFun / FinStep + 上海交大；arXiv 2512.23515，v2 2026-09-07） | Qwen3-8B | GRPO，64×H800 约 120 小时（上份简报第 12 行） | 因子池 + 价格 + 新闻语义画像（Claude 3.7 Sonnet 合成） | 训练 2024，测试 2025-01-01 至 2025-12-31；论文称 Qwen3-8B 截止日 2024-09（提供方文档） | 每边 10 bp，VWAP | 标普 500 池年化 47.87%、夏普 1.62、回撤 16.91%；买入持有 19.34%/0.80；去掉 RL（零样本 Qwen3-8B）12.85%/0.47（`rl-llm-2026-09-30/arxiv-2512.23515-alpha-r1.txt` 表 1、消融） | 无 | 代码在 GitHub，行情/新闻/专有模型输出不分发；权重未见 |
| 2 | **AlphaQuanter**（港科大；arXiv 2510.14264，v2 2026-04-19） | Qwen2.5-3B 与 7B Instruct | verl + GRPO，A100 80GB（数量与小时数论文未写）；rollout.n=16，batch 32，最长回复 16,384 | 价格/技术指标、财报、新闻情绪、宏观，经工具按需调用 | 训练 2022-09 至 2024-03，验证 2024-05 至 2024-11，测试 2025-01-01 至 2025-06-30（122 个交易日），之间留约 30 日空档 | 有手续费参数符号，数值我没找到 | 5 只股票平均年化：AlphaQuanter-7B 34.94%、夏普 0.65、回撤 24.93%；3B 23.03%/0.43；买入持有 12.90%/0.57（`arxiv-2510.14264-alphaquanter.txt` 表 5）；各配置 3 个种子取平均 | 无 | 代码与数据声明公开（github.com/horizon-llm/AlphaQuanter，论文摘要） |
| 3 | **FinWorld / FinReasoner**（南洋理工 + Skywork AI + 新加坡管理大学；arXiv 2508.02292，KDD'26） | Qwen3-8B（正文写 "Qwen-8B"） | verl 0.5.0 + GRPO，rollout 8，50 个 epoch，lr 1e-6，16×A100，批量 64；两阶段（金融推理再市场环境） | 7 日 OHLCV + 新闻摘要（Qwen3-32B 摘要） | 6 只美股 2015-05 至 2025-05，切分细节我没核 | 奖励里手续费率（文中举例 1e-4） | 交易结果只有雷达图，正文没有数字；单次运行 | 无 | 开源平台 |
| 4 | **FinSMART**（帝国理工；arXiv 2607.28127，2026-07-30） | Llama-3-8B-Instruct（不是 Qwen） | LoRA(r=16，1360 万可训练参数) + GRPO，**单卡 A6000 48GB，训练 8 小时** | 新闻情绪，做多空 35% 分位组合 | 训练 ≤2018-12-31，测试 2019-01 至 2021-06（约 32.5 万篇文章） | **全文检索 "transaction/bps/fee" 没有成本设定**，次日开盘到次日开盘，每日换仓 | 累计 264.9%、年化 91.5%、夏普 1.97、RankIC 0.061；FinDPO 为 109.8%/1.12（`arxiv-2607.28127-finsmart.txt` 表 1）；滚动再训练累计 406% | 无 | 论文未见代码链接（我没找到） |
| 5 | Trading-R1（Tauric Research；UCLA/UW/Stanford 作者） | Qwen3-4B（<7B，列出作对照） | SFT + GRPO 三阶段课程；SFT 用 8×H100，RL 用 8×H200 | 见上份简报第 4 行 | 测试 2024-06 至 2024-08，在 Qwen3 截止日（OpenRouter 2025-03-31）之前 | 回测未见成本 | NVDA 累计 8.08%、夏普 1.88（上份简报） | 无；README 仍写 Terminal coming soon | 未见权重 |
| 6 | FinRankGRPO（港科大 + 平安财险；arXiv 2609.24175，2026-09-21） | Qwen2.5 0.5B/1.5B/3B（<7B） | TRL 0.9.6 + GRPO（Spearman 奖励），3×L20，SFT 约 1 小时、GRPO 约 12 小时 | 新闻摘要（DeepSeek-Chat 生成）排序 15 只 ETF，周度 | 训练 2010–2019，测试 2020–2025（含 Qwen2.5 已知区间） | **5 bp 每换手，零滑点** | 3B-Instruct 夏普 0.636、年化 12.2%，等权 8.5%；Spearman 0.023 | 无 | 匿名仓库链接 |
| 7 | Fin-R1（上份简报第 6 行）、FLAG-Trader、Trading-R1 之外的 FinRL 系（第 8–11 行） | 7B / 135M / 非 LLM | — | — | — | — | 上份简报已列；Fin-R1 无交易测试 | — | — |
| 8 | 新增 2026 邻近工作（仅摘要，不计入上表） | — | — | — | — | — | CLaC@FinMMEval 2026（2607.16028，LLaMA-3.2-1B 只做情绪，PPO/DDPG 做交易，成本 0.2%，验证到测试泛化差）；2605.17307（SAC，16 折滚动 2003–2026，无策略在 HAC 检验下显著赢买入持有）；2604.26747（LLM 智能体做加密因子搜索 + 岭回归，2024–2026 纯样本外年化 44.55%、夏普 1.55，单边 5 bp；**没有 RL 训练模型**） | — | — |

### 1.2 公司、基金与开源组织（只写有公开来源的）

| 组织 | 做了什么（原文依据） | RL 训练 LLM 做交易？ | 来源与层次 |
|---|---|---|---|
| **StepFun / FinStep**（上海） | 同一批作者（Zuo Bai、Rui Sun 等）发表 Alpha-R1（RL 训练 Qwen3-8B）和 KTD-Fin 评测基准（2605.28359） | 是（Alpha-R1，回测；见上表第 1 行） | 论文全文（快照） |
| **Tauric Research** | TradingAgents（多智能体，零样本）与 Trading-R1（Qwen3-4B，SFT+GRPO）；Terminal 仍 "coming soon"；检索摘要称 TradingAgents v0.5.2 于 2026-09 发布 | Trading-R1 是，但是 4B、回测 | 论文 + README（上份简报）；v0.5.2 只有检索摘要 |
| **nof1.ai** | About 页原文："We're using techniques like open-ended learning and large-scale RL to handle the complexity of markets"（`rl-llm-2026-09-30/nof1-about.txt` 第 46–48 行）；Alpha Arena 里被测的模型是别人的零样本模型（上份简报第 1–2 行） | 自称在做，**没有任何模型、方法或结果公开** | 官方页（快照） |
| **Man Group（Numeric 部门）** | AlphaGPT：LLM 智能体自己找数据、写代码、回测，"Several dozen signals generated by the AI system have passed Man Group's investment committee and are slated to be deployed in live trading"（Bloomberg 2025-07-10 转引，AI Street 2025-07-11） | **否**，没有 RL；这是"LLM 做研究员"而不是"LLM 做交易员" | `ai-street-man-group-alphagpt-agents.txt`（全文；Bloomberg 原文付费墙未开） |
| **九坤投资**（+ 微软亚洲研究院） | 发表 Logic-RL（规则奖励 RL 复现 DeepSeek-R1 式推理，数学逻辑题） | 否（通用推理，不是交易） | 21 经济网、澎湃转述（快照，二手） |
| **幻方量化 / 明汯 / 黑翼 / 宽德** | 21 经济网称各家"在 AI 上做了大量布局"；一位未具名量化人士说方向是"强化深度学习……通过 AI 技术优化因子挖掘、策略优化及风险管理" | **没有公开的 LLM + RL 训练用于交易的说法或结果**（我只看到招聘与实验室新闻；DeepSeek 的 GRPO 是通用模型训练，不是交易） | 21 经济网（快照，二手）；搜狐等只有检索摘要 |
| **TradeRank、Alpha Arena 等评测榜** | 评测别人的模型，不训练 | 否 | 上份简报；Qwen3.8 Max 0902 在 TradeRank 的位置（"+6.6%，0 笔交易"）只有检索摘要，未打开原页 |
| **开源工具** | Unsloth、ms-swift、verl、TRL 提供 GRPO；OpenRLHF 我没有找到交易论文使用它 | — | 见第 4 节 |

**判断**：有 RL 训练证据的组织是学术团体和一家模型公司（StepFun）；对冲基金与中国私募没有公开记录。有生产落地记录的是 Man Group，但它用的是"LLM 当研究员、人类投委会把关、信号仍是规则"，不是训练交易员模型。这一点与机主说的 "AI native：用 AI 方法找优势，不靠买数据" 方向一致，但手段不是 GRPO。

## 2. 规模有没有用

| 来源 | 窗口与设置 | 规模比较 | 结论方向 |
|---|---|---|---|
| **InvestorBench**（2412.18174） | 2020-07 至 2021-05，股票/BTC/ETF，Qwen2.5-7B/32B/72B、Llama-3.1-8B/70B、Yi-34B 等；窗口在这些模型训练数据内 | 作者原文："those exceeding 67B parameters displayed superior CRs and SRs, along with markedly less variance"；同表首列 Llama-3.1-8B 的 CR 22.703 高于 Qwen2.5-72B 的 7.421（我没核对该列对应哪个标的） | **支持，但窗口被污染**；个别小模型反而更好 |
| **StockBench**（2510.02209） | 2025-03 至 2025-06，道指 20 只，截止日后，零样本 | Qwen3-235B-Think 2.5%、Qwen3-235B-Ins 2.4%、Qwen3-30B-Think 2.1%，被动基线 0.4%，GPT-OSS-120B -0.9%、GPT-OSS-20B -2.8% | 235B 对 30B 只差 0.4 个点（单次运行，无噪声估计）；作者写 "Model scale confers robustness"（用 Kimi-K2 对 GPT-OSS-120B，混杂了模型族），同时写"推理模型不保证更好" → **弱支持/不明确** |
| **LiveTradeBench**（2511.03628） | 2025-08-18 至 2025-10-24 前向，美股 | 美股累计收益：Qwen2.5-72B 5.15%、Qwen3-235B-Ins 3.52%、Qwen3-235B-Think 1.78%；LMArena 分数与收益相关性约 0（上份简报第 3 行：Spearman 0.054） | **不支持**：更大更新的 Qwen 反而低 |
| **AlphaQuanter**（2510.14264，表 5） | 2025-01 至 06，5 只股票，单智能体无 RL | 平均年化：Qwen2.5-3B -1.68%，7B 4.49%，Qwen3-30B-A3B 5.44%，DeepSeek-V3.1 685B 8.38%，Kimi-K2 1T -1.65%，GPT-4o 9.42%；同模型加 RL：3B 23.03%、7B 34.94% | 零样本按规模**非单调**；作者结论："specialized training paradigms may be more critical than model scale" |
| **Alpha-R1**（表 1） | 2025 全年，标普 500 池零样本年化 | Qwen3-8B 12.85%、DeepSeek-R1 21.94%、Claude 3.7 Sonnet 10.92%、Gemini 2.5 Pro 14.23%；Russell 2000 上 Qwen3-8B -9.41%，DeepSeek-R1 30.50%，Claude 30.14%。RL 消融：12.85% → 47.87% | 零样本大模型在 Russell 2000 上明显好于 8B，在标普 500 上差距不大；**RL 的增益（+35 个点）远大于模型间差距** |
| **Trading-R1**（2509.11420 表 3） | 2024-06 至 08，在 Qwen3 训练区间内 | 零样本 NVDA 累计：Qwen-4B -1.59%、Qwen3-32B +1.74%、GPT-4.1 3.15%；SFT+RL 的 4B 为 8.08% | 零样本 4B→32B 有提升（**窗口污染**）；RL 后的 4B 超过零样本 32B |
| **FinRankGRPO**（2609.24175） | 2020–2025，15 只 ETF，5 bp | Qwen2.5 0.5B / 3B base / 3B-Instruct：夏普 0.521 / 0.568 / 0.636 | 小模型范围内随规模与指令微调缓升（0.5B→3B 只 +0.047）；只到 3B |
| **AI-Trader**（上份简报第 16 行）、**AMA**（第 17 行）、综述 2608.31041 | 实时 5 周至 2 个月 | AI-Trader：Qwen3-Max 0.39%、MiniMax-M2 9.56%；AMA 与综述：换 LLM 骨干对结果的影响小于智能体架构；综述面板 C 写 "Most LLMs lost money in live evaluation" | **不支持**规模决定收益 |

**如实结论**：没有任何研究在交易上用同一 RL 流程扫描 7B/14B/32B/70B。已有证据是：（1）截止日后的前向窗口里，零样本规模与收益没有稳定关系，多数大模型零样本交易不赚钱；（2）支持"越大越好"的两个例子窗口在模型训练数据之内；（3）在有 RL 的工作里，RL 本身的增益大于模型规模的差异，但都只做到 3B–8B，没有 ≥14B 的 RL 交易结果。机主"相信 scaling law"的预期在通用推理上有依据，在交易上**没有公开的直接证据，也没有反证**（没人试过）；已有零样本数据更倾向于"规模不是瓶颈，信息和奖励设计才是"。此外，9B 与 27B 的取舍不能靠这些文献决定。

## 3. Qwen3.8 与同代型号事实（官方来源）

官方来源：HF 模型卡与 config（`hf-qwen3.8-*-modelcard.txt`、`hf-qwen3.8-27b-config.txt`）、HF API（`hf-api-qwen-list-*.json.txt`）。未找到独立的 Qwen 官方博客页（没有抓取 qwen.ai 博客；发布日期用 HF API 时间戳和 OpenRouter 上架时间交叉）。

| 型号 | 规模 | 许可证 | 日期 | 上下文 | 推理模式 | 训练数据截止日 |
|---|---|---|---|---|---|---|
| **Qwen3.8-27B** | 稠密，语言模型 27B，64 层，Gated DeltaNet + Gated Attention 混合，带视觉编码器，`model_type: qwen3_5`（Qwen3.5 架构） | Apache-2.0 | HF 仓库创建 2026-08-05，最后修改 2026-08-14，首个 HF 讨论 2026-08-14；OpenRouter 上架 2026-08-14 | 262,144，可扩到 1,000,000 | 默认思考开，可关；`reasoning_effort`、`preserve_thinking` | **官方未发布**（模型卡无此文字） |
| Qwen3.8-2.4T-A95B | MoE，总 2.4T、激活 95B，纯文本 | `other`（qwen3.8-max 自定义许可，不是 Apache） | HF 仓库 2026-08-08；OpenRouter 2026-08-12；官方托管版为 Qwen3.8-Max | 262,144，可扩到 1,010,000 | 同 | 未发布 |
| Qwen3.8-Flash-Next | MoE，总 125B、激活 6B（另有 51B n-gram 嵌入、4B MTP），带视觉 | `qwen-community-1.0` | HF 2026-08-24 | 262,144 → 1,000,000 | 同 | 未发布 |
| Qwen3.6-27B / 35B-A3B | 稠密 27B / MoE | Apache-2.0（27B 卡片） | 2026-04-21 / 2026-04-15（HF 仓库创建） | 262,144 → 1,010,000 | 思考 | 未发布；第三方称 DashScope 提示只写 "2026" |
| **Qwen3.5-9B**（及 4B、2B、0.8B、27B、35B-A3B、122B-A10B、397B-A17B） | 稠密 9B | Apache-2.0 | 2026-02-27（9B），2026-02-24（27B） | 262,144 → 1,010,000 | 思考 | 未发布；第三方称 DashScope 提示只写 "2026" |
| Qwen3-8B / 14B / 32B / 30B-A3B / 235B-A22B | 稠密/MoE | 我没打开它们的卡片，未核实 | 2025-04-28（OpenRouter） | 131,072（OpenRouter） | 思考/非思考 | **2025-03-31**（OpenRouter API 的 `knowledge_cutoff` 字段）；Alpha-R1 论文称 Qwen3-8B 为 2024-09（提供方文档，论文自己说无法独立验证）——两者不一致 |
| Qwen3 2507 系列、Qwen3-Next-80B | — | — | 2025-07 / 2025-09 | — | — | 2025-06-30 / 2025-09-30（OpenRouter） |
| Qwen2.5-7B/32B/72B | — | — | 2024-09 | 32,768 | — | 2024-06-30（OpenRouter） |

**要点**：
- **Qwen3.8 这一代没有 8B/9B/14B/32B**：只有 27B 稠密、Flash-Next（125B-A6B）、2.4T-A95B。机主要的"至少 9B"在新一代里对应的只有 **Qwen3.5-9B**（2026-02，Apache-2.0）或旧的 Qwen3-14B/32B。主审 14:03 摘要中"稠密约 28B"我没核实到：模型卡写语言模型 27B，另有视觉编码器，总量未见。
- **截止日**：Qwen3.8 系列没有官方值。HF 讨论串（`hf-qwen3.8-27b-fp8-discussion8-cutoff-api.txt`）里提问者问与 Qwen3.6 是否不同，回复者写 "u can ask the model: My knowledge cutoff is early 2025"——这是模型自己说的，不是官方；metehan.ai 称 Qwen 维护者公开说过模型会幻觉自己的截止日（它链接的 issue #1442，我没打开）。第三方文章（metehan.ai，标为 Tier 1 来自 DashScope 提示）称 Qwen3.5 起的 API 只写年份 "2026"。**两个来源互相不一致，都不是官方值。**
- 机主说"qwen3.8 很厉害"：模型卡上的基准是编码、智能体、视觉等通用任务；我没有找到 Qwen3.8 的交易专项基准（仅检索摘要：TradeRank 上的 Qwen3.8 Max 0902 "+6.6%、0 笔交易"，0 笔交易说明几乎没有交易，不算证据）。
- RL 工具链风险：Qwen3.5/3.8 是 Gated DeltaNet 混合线性注意力。Unsloth 文档写 Qwen3.5 的 RL 要 `fast_inference=False`（不走它自己的 vLLM 快速路径），即 rollout 会更慢；模型卡说权重可用 Transformers/vLLM/SGLang 推理，但没有写 GRPO 训练的验证结果。

## 4. 算力与费用

### 4.1 框架与显存

| 项 | 内容 | 来源与层次 |
|---|---|---|
| 框架 | verl（AlphaQuanter、FinWorld、Alpha-R1 系用）；TRL（FinRankGRPO，trl 0.9.6）；Unsloth（文档称 GRPO 支持 LoRA/QLoRA）；ms-swift（检索摘要：支持 GRPO，列出 Qwen3.8）；OpenRLHF（没有找到交易论文使用） | 论文全文；Unsloth 文档全文；ms-swift 仅检索摘要 |
| Unsloth 经验法则 | QLoRA 4-bit 的 GRPO：显存 GB ≈ 参数量（十亿）；LoRA 16-bit 至少 4 倍；长上下文和更多生成会加显存。Qwen3.5 bf16 LoRA（微调，非 RL）：9B 22GB，27B 56GB | `unsloth-rl-guide.txt` 第 308 行、`unsloth-qwen3.5-fine-tune.txt` 第 18 行 |
| Modal 选型指南（厂商营销文，非实测） | LoRA/QLoRA GRPO：8B 1×40–80GB；14B 1–2×80GB；32B 4×80GB；全参：8B 2–4×80GB，14B 4–8×80GB，32B 8–16+×80GB | `modal-resources-best-base-models-grpo.txt` |
| 论文里的实际用量 | Alpha-R1：64×H800 × 约 120 小时 ≈ 7,680 卡时（Qwen3-8B）；FinSMART：1×A6000 × 8 小时（Llama-3-8B，LoRA）；FinWorld：16×A100（小时数未写）；Trading-R1：8×H100（SFT）+ 8×H200（RL）（Qwen3-4B，小时数未写）；FinRankGRPO：3×L20，SFT 约 1 小时 + GRPO 约 12 小时（3B） | 各论文快照 |
| 我的估计：Qwen3.8-27B LoRA GRPO | bf16 权重约 54GB；再加 rollout KV 与激活，单张 80GB 放不下共置 vLLM，需要 H200 141GB 或 2×H100。**这是估算，不是实测。** | 推算（`hf-qwen3.8-27b-config.txt` 的 64 层、5120 隐藏维度，Unsloth 27B 56GB） |

### 4.2 Modal 单价（https://modal.com/pricing 抓取自 HTML，`modal-pricing-gpu-rows-extracted-from-html.txt`）

| GPU | 每秒 | 每小时 | 本仓库 `scripts/modal_budget.py` 表 |
|---|---|---|---|
| B200 | $0.001736 | $6.2496 | **没有** |
| H200 SXM | $0.001261 | $4.5396 | **没有** |
| H100 SXM5 | $0.001097 | $3.9492 | $3.95 |
| A100 80GB | $0.000694 | $2.4984 | $2.50 |
| L40S | $0.000542 | $1.9512 | $1.95 |
| A10 | $0.000306 | $1.1016 | $1.10（A10G） |
| （另）B300 $7.0992，RTX PRO 6000 $3.0312，A100 40GB $2.0988，L4 $0.7992，T4 $0.5904 | | | 表里有 A100-40GB、L4、T4 |

说明：页面 GPU 按秒计价，CPU 与内存另计（本仓库表按 Functions 费率 $0.0473/核时、$0.008/GiB 时；抓到的页面该段是 Sandbox/Notebook 的价，数值更高，我没有核对 Functions 段）。下面的估算再加 30% 开销（权重同步、空闲）覆盖这一差别。**`modal_budget.py` 的 GPU 表没有 H200/B200，H200 任务现在过不了预算检查，要改脚本；我没有动它。**

### 4.3 最小可信实验的费用估算（全部是估算）

公式：
- 训练 FLOPs ≈ 8·N·T，T = 采样总数 ×（提示 + 输出 token）；8 = 前向反向（含重算）6 + 参考策略前向 2；LoRA 少算权重梯度，真实值可能偏低约 25%。
- 训练小时 = FLOPs / (989 TFLOPs × MFU)，MFU 取 25%–40%。
- 生成小时 = 输出 token 总数 / 吞吐；吞吐假设 9B 6,000 tok/s、27B 2,500 tok/s（批量 vLLM，未实测）。
- 总 GPU 小时 = (训练 + 生成) × 1.3；费用 = 小时 × H100 $3.9492（9B）或 H200 $4.5396（27B）。

假设：提示 1,500 token（匿名化的数字特征，无新闻）；输出 600 token（关思考，短理由）；"L"档输出 3,000 token（开思考）。

| 档位 | 步 × 提示数 × 采样数 = 采样总数 | Qwen3.5-9B（H100） | Qwen3.8-27B（H200） |
|---|---|---|---|
| **S（最小）** | 100 × 32 × 8 = 25,600 | 4.5–6.6 GPU 小时 → **$18–26** | 12.8–19.2 小时 → **$58–87** |
| M | 300 × 64 × 8 = 153,600 | 26.7–39.5 小时 → $106–156 | 76.9–115.1 小时 → $349–522 |
| L（开思考，输出 3,000） | 300 × 64 × 8 = 153,600 | 73.2–100.4 小时 → $289–397 | 202.8–284.6 小时 → $921–1,292 |

可信实验至少 **4 次运行**（3 个种子 + 1 个打乱奖励的安慰剂）：S 档 9B 约 **$72–104**，27B 约 **$232–348**；M 档 9B 约 $424–624，27B 约 $1,396–2,088。对比：Modal 月上限 $25（`scripts/modal_budget.py`）；免费额度 $30/月；超出属机主决定。对照点：FinSMART 的 8 小时 A6000 按 L40S 价约 $15.6；Alpha-R1 的 7,680 H800 卡时按 H100 价约 $30,300（仅作量级参照，H800 不是 H100）。上份简报的"≤$3、0.5B–1.5B"与这里的 9B 不矛盾：差的是参数量。

S 档的统计功效低（25,600 个采样，远小于 FinSMART 的约 30,000 篇文章 × 多轮；种子间方差上份简报已述），只能用来否定，不能用来确认。

### 4.4 只推理不训练的价格

| 提供方 | 模型 | 输入 / 输出（每百万 token） | 来源 |
|---|---|---|---|
| 阿里云 Model Studio（国际站，官方定价页） | qwen3.8-27b | $0.5 / $3 | `alibabacloud-model-studio-model-pricing.txt` |
| 同上 | qwen3.8-2.4t-a95b；qwen3.8-max | $2 / $6；$2 / $6 | 同上 |
| 同上 | qwen3-8b | $0.18 / $0.7 | 同上 |
| OpenRouter API 列表（2026-09-30 抓取） | qwen3.8-27b | $0.0249 / $4.35（列表原值，输入价异常低，未核实是否促销）；另有 `:free` 版 | `openrouter-api-models-qwen-filtered.txt` |
| OpenRouter | qwen3.8-flash / max-0902 / max-prime | $0.15/$0.47；$2/$6；$4/$12 | 同上 |
| OpenRouter | qwen3.5-9b；qwen3-14b；qwen3-32b；qwen3-8b | $0.10/$0.15；$0.12/$0.24；$0.08/$0.28；$0.117/$0.455 | 同上 |

示例（估算）：截止日后窗口按 2025-04 起约 75 周 × 100 只股票 = 7,500 次调用，每次 2,000 输入 token。阿里云 qwen3.8-27b：关思考输出 600 token → 输入 15M×$0.5 + 输出 4.5M×$3 = **约 $21**；开思考输出 4,000 token → 输出 30M×$3，合计约 **$98**。用它做零样本前视探针（第 5 节）只要其中很小一部分。

## 5. 前视问题

### 5.1 干净窗有多长

| 假设的截止日 | 来源与可信度 | 对 2026-09-30 的干净窗（美股交易日，节假日按常规表） |
|---|---|---|
| 2025-03 底（"early 2025"） | HF 讨论里模型自报，不可靠 | 自 2025-04-01 起 377 个交易日（约 17.5 个月） |
| 2026-01-01（"2026" 年级的较早端） | 第三方称 DashScope 提示对 Qwen3.5 起只写 "2026" | 187 个交易日（约 9 个月） |
| 发布日 2026-08-14（保守下限） | 公开日期 | 33 个交易日 |
| 老一代 Qwen3-8B/14B/32B 的 2025-03-31 | OpenRouter API 字段 | 377 个交易日；若取 Alpha-R1 引用的 2024-09，则自 2025-01-01 起 439 个交易日 |

这是取舍：更新更强的 Qwen3.8 的干净窗未知且可能只有几个月；老一代 Qwen3-14B/32B 窗口长，但它们不是机主说的"很厉害的新模型"。**必须在训练前实测而不是假设截止日**：用 Gao 等（2512.23847，上份简报引过）的前视倾向检验在候选模型上跑一遍，成本是几美分的 API 调用。

另一层风险（我的推断，不是某篇论文的结论）：如果 RL 训练窗口落在模型已知区间内，奖励可以通过"回忆结果"获得，策略学到的可能是回忆而不是规律，截止日后表现会衰减。Profit Mirage（上份简报第 3 节）给的旁证是基座模型发布后夏普衰减 51%–62%。所以理想做法是训练窗和测试窗都尽量靠后，或者让输入匿名到无法回忆。

### 5.2 只给匿名化数字输入能不能避免回忆

证据有分歧，没有一个结论是决定性的：

| 来源 | 结论 | 层次与局限 |
|---|---|---|
| **KTD-Fin**（2605.28359，清华/StepFun，2026-05-27） | 四档遮蔽（明文、股票盲、日期盲、双盲）。双盲载荷喂给 10 个前沿大模型当攻击者，每个 200 个（股票，日期）探针：ticker top-1 恢复率最高 3.0%，ticker+日期联合 ≤1.5%，最强攻击者 top-5 ticker 10.2%。双盲下智能体理由从品牌叙事转到匿名因子排名 | 全文；A 股沪深 300、2024-01 至 2026-04，只有价量。另：十个前沿 LLM 智能体的收益主要由被动市场/风格暴露解释，选股 alpha 只有一个接近 0，其余为负 |
| **BlindTrade**（2603.17692，ICLR 2026 FinAI 研讨会） | 标普 500 每日匿名为 "STOCK_0026"；2025 年至 08-01 夏普 1.40 ± 0.22（20 个种子，10 bp 成本）；打乱分数后信号消失 | 全文；**作者自承"没有做匿名 vs 原始代码的直接消融"**，RL 只是小策略网络，不训练 LLM |
| **Lopez-Lira 等**（2504.14765，上份简报） | 大模型能回忆精确经济金融数据，遮蔽实体/日期也失败（可从少量上下文还原），截止日后无回忆 | 摘要；宏观和金融数据，不是匿名价量窗口 |
| **Gao 等**（2512.23847，上份简报） | 前视倾向在截止日后降到约 0 | 摘要 |
| 检索摘要（未打开原文）：2511.15364 称模板匿名对 GPT-4o-mini 仍能识别 66.88% 公司名、53.90% ticker；2601.13770、2603.26797 | 匿名化有信息损失，仍有上下文线索可识别 | 只有检索摘要 |

读法：价量数字经过标准化、去掉代码和日历后，在 KTD-Fin 的探针里被恢复的比例很低，但探针只有 200 个、只测了 A 股；用新闻文字时文字本身会泄露实体，匿名化失效的证据更多。没有公开证据表明美股价量匿名后对 Qwen3.8 这样的新模型完全安全。建议的双重保护（规划而非本次范围）：输入匿名 + 测试窗在实测截止日之后，并用打乱标签作负控制。

## 6. 对机主三点的证据回应

- "GRPO 训练的 Qwen 很有潜力，先评估有没有人做"：有，见第 1 节；有分量的是 Alpha-R1（StepFun）。但都是回测，没有前向和复现；最大的一个只有 8B 和一年窗口。
- "小模型没用，至少 9B；27B 更好；相信 scaling law"：公开文献里有效的 RL 结果恰好多数来自 3B–8B（AlphaQuanter 3B/7B、Alpha-R1 8B、FinSMART 8B）；没有 ≥14B 的 RL 交易结果，也没有规模扫描。所以"至少 9B"不是文献的要求，"27B 更好"没有直接证据（也没有反证）。可以支持的论点是：9B 及以上的模型有更强的指令遵循和推理，能用工具，但这需要本地做对照（同输入表格基线、同成本）才能落到数字。
- "AI native：不靠买数据"：Man Group 的公开落地（LLM 写信号、人类投委会把关）和 2604.26747（LLM 智能体在点时刻因子 DSL 里搜索，2024–2026 纯样本外夏普 1.55，单边 5 bp，摘要层）更接近这个方向，而且不需要训练 8B 以上模型；RL 训练大模型本身目前没有这方面的公开前向证据。
- 27B 的现实限制：要 H200，Modal 月上限放不下，需要机主决定预算。

## 7. 局限与没做完

- Qwen3.8 截止日：没有官方值，无法回答"哪段历史对它是样本内"。未抓 Qwen 官方博客页（qwen.ai）和 QwenLM GitHub README，因为 HF 模型卡已是同一官方来源，且联网次数有限；发布日期用 HF 时间戳与 OpenRouter 上架时间交叉，第三方文章（codersera、llm-stats 等）只有检索摘要。
- 费用估算是公式，吞吐与 MFU 是假设，没有实测，误差约 2 倍；没有针对 Qwen3.8 的混合线性注意力做 GRPO 的公开吞吐数字。
- FinWorld 的交易结果只有图，没有数字；AlphaQuanter 的手续费数值、GPU 数量未找到；FinSMART 未见代码链接（可能有，我没搜到）。
- 没有核对的：Qwen3-8B/14B/32B 的许可证；Bloomberg 原文（付费墙）；Logic-RL 原文；2511.15364、2601.13770、2603.26797 只有检索摘要。
- 没有重新检查上份简报的数字（只引用）；Reddit/QuantConnect 社区帖仍无可用原帖。
- Modal 页面的 CPU/内存价格抓到的是 Sandbox/Notebook 段，未核对 Functions 段。
- 没有修改登记簿、代码或任何仓库文件（除新增本简报和来源快照）。

## 8. 来源清单

层次：全文 = 下载全文并搜读相关章节；摘要/检索摘要 = 只有摘要或搜索结果；官方页 = 官方页面/模型卡。抓取时间均为 2026-09-30 UTC 18:38–19:00。

| 来源 | URL | 层次 | 快照 |
|---|---|---|---|
| Qwen3.8-27B 模型卡、config | https://huggingface.co/Qwen/Qwen3.8-27B | 官方页，全文 | hf-qwen3.8-27b-modelcard.txt；hf-qwen3.8-27b-config.txt |
| Qwen3.8-2.4T-A95B、Flash-Next、Qwen3.5-9B、Qwen3.6-27B 模型卡 | https://huggingface.co/Qwen/… | 官方页，全文 | hf-qwen3.8-2.4t-a95b-modelcard.txt 等 |
| HF API：Qwen3.8/3.6/3.5/3 型号列表 | https://huggingface.co/api/models?author=Qwen&search=… | 官方 API | hf-api-qwen-list-*.json.txt；hf-api-qwen3-list.json.txt |
| HF 讨论串 "Knowledge cut-off date" | https://huggingface.co/Qwen/Qwen3.8-27B-FP8/discussions/8 | 全文（API 取正文；网页版只取到侧栏） | hf-qwen3.8-27b-fp8-discussion8-cutoff-api.txt |
| Qwen3 GitHub 讨论串 #1093（Qwen2.5 截止日） | https://github.com/QwenLM/Qwen3/discussions/1093 | 全文，与 Qwen3.8 无关，仅背景 | github-qwen3-discussion1093-cutoff.txt |
| metehan.ai 截止日汇总（第三方） | https://metehan.ai/articles/llm-knowledge-cutoff-dates/ | 全文 | metehan-llm-knowledge-cutoff-dates.txt |
| aiknowledgecutoff.com（第三方，OpenRouter 数据） | https://aiknowledgecutoff.com/qwen | 全文 | aiknowledgecutoff-qwen.txt |
| OpenRouter 模型列表 API | https://openrouter.ai/api/v1/models | 官方 API，筛出 Qwen | openrouter-api-models-qwen-filtered.txt |
| 阿里云 Model Studio 定价 | https://www.alibabacloud.com/help/en/model-studio/model-pricing | 官方页，全文 | alibabacloud-model-studio-model-pricing.txt |
| Modal 定价 | https://modal.com/pricing | 官方页（HTML 抽取 GPU 行） | modal-pricing.txt；modal-pricing-gpu-rows-extracted-from-html.txt |
| Modal：GRPO 基座模型指南 | https://modal.com/resources/best-open-source-base-models-grpo-fine-tuning | 全文（厂商营销） | modal-resources-best-base-models-grpo.txt |
| Unsloth RL 指南；Qwen3.5 微调；Qwen3.8 页 | https://docs.unsloth.ai/… | 官方文档，全文 | unsloth-rl-guide.txt；unsloth-qwen3.5-fine-tune.txt；unsloth-qwen3.8.txt |
| AlphaQuanter 2510.14264 | https://arxiv.org/pdf/2510.14264 | 全文 | arxiv-2510.14264-alphaquanter.txt |
| FinSMART 2607.28127 | https://arxiv.org/pdf/2607.28127 | 全文 | arxiv-2607.28127-finsmart.txt |
| FinRankGRPO 2609.24175 | https://arxiv.org/pdf/2609.24175 | 全文 | arxiv-2609.24175-finrankgrpo.txt |
| FinWorld 2508.02292 | https://arxiv.org/pdf/2508.02292 | 全文（读了 GRPO、实现细节） | arxiv-2508.02292-finworld.txt |
| Agentic Quantitative Trading 综述 2608.31041 | https://arxiv.org/pdf/2608.31041 | 全文（读了评测面板 C） | arxiv-2608.31041-agentic-quant-survey.txt |
| CLaC@FinMMEval 2607.16028 | https://arxiv.org/pdf/2607.16028 | 摘要与方法 | arxiv-2607.16028-clac-finmmeval.txt |
| 2605.17307、2603.29086、2604.26747、2508.02366、2510.17393、2509.01393 | arXiv API | 摘要 | arxiv-api-abstracts-….xml.txt |
| KTD-Fin 2605.28359 | https://arxiv.org/pdf/2605.28359 | 全文（读了遮蔽协议与去匿名探针） | arxiv-2605.28359-ktd-fin.txt |
| BlindTrade 2603.17692 | https://arxiv.org/pdf/2603.17692 | 全文 | arxiv-2603.17692-blindfolded-llms.txt |
| AI Street：Man Group AlphaGPT | https://www.ai-street.co/p/man-group-s-ai-agents-uncover-dozens-of-trading-signals | 全文（转引 Bloomberg） | ai-street-man-group-alphagpt-agents.txt |
| 21 经济网、澎湃：量化私募与 AI | https://www.21jingji.com/article/20250228/herald/a255048c111e6731b74e8e71305b12b2.html ；https://m.thepaper.cn/newsDetail_forward_30300674 | 全文（二手报道） | 21jingji-quant-funds-ai-20250228.txt；thepaper-quant-giants-large-models.txt |
| 检索摘要汇总（未打开原页的来源：ms-swift、Unsloth GitHub、codersera、llm-stats、TradeRank、2511.15364 等） | WebSearch | **只有检索摘要** | websearch-summaries-2026-09-30.txt |
| 上份简报已抓取并在本次重读的来源：Alpha-R1 2512.23515、Trading-R1 2509.11420、StockBench 2510.02209、LiveTradeBench 2511.03628、InvestorBench 2412.18174、AMA 2510.11695、nof1 About、2504.14765、2512.23847 | 见上份简报第 7 节 | 全文/摘要（见该节） | `../rl-llm-2026-09-30/` |

内部引用：`scripts/modal_budget.py`（Modal 费率表与 $25 月上限，只读）、`reports/research/intel/rl-llm-trading-evidence-2026-09-30.md`（上份简报）。
