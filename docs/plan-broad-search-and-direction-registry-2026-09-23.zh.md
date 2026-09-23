# 计划：广泛搜索 + 方向登记簿（2026-09-23）

> 机主 09-23 的要求：
> - 先 review 还有哪些能研究复现的因子、高频策略和训练模型，先尽可能多地试方向，站在巨人肩膀上，不自己构建和探索。
> - 主要问题是**搜得不够多、不够全**：很多因子不在分享平台上，而在帖子里，要配合联网搜索工具或 MCP 去拿。
> - 只做了两天，样本本来就少。
> - 要**做好记录和方向确认，以免以后重复**。
>
> 本文件回答"怎么做"，并记录今天已经做完的部分。研究排序以本文件为准，高于交接文档 `docs/handoff-2026-09-23.zh.md` 第 4 节；模拟盘续期仍有硬日期，见第 7 节。

## 1. 做法

三件事循环进行：

1. **按"渠道 × 主题"矩阵系统地搜**（第 3、4 节）。渠道包括论文、帖子/博客、代码、结果库、实盘记录、中文社区。现有工具进不去的渠道，先补工具（第 5 节），不跳过。
2. **每条发现先进登记簿**：先查重，再做方向确认（第 2 节）。帖子里的数字一律标"作者自报"；进入测试前，至少要有一条一手来源或能跑的代码。
3. **按三层漏斗批量测试**（第 6 节）：
   - 第一层：先读别人已经公开的结果，零算力；
   - 第二层：用别人的代码或现有引擎，在冻结协议下跑；
   - 第三层：最后才训练模型。

## 2. 记录与方向确认（09-23 已上线）

**两个文件**

| 文件 | 内容 |
|---|---|
| `reports/research/harvest/directions.jsonl` | 一个方向一行，字段见下。同一 id 追加新行就是更新，以最后一行为准，文件本身保留历史。 |
| `reports/research/harvest/search-log.jsonl` | 一次搜索一行：日期、渠道、工具、查询、看了多少条结果、新增了哪些方向。以后不重复搜同样的东西。 |

方向行的字段：id、名称、类别、机制键 `family_key`（同一机制的不同来源归到一起）、别名、来源（URL + 类型：论文/帖子/代码/平台/实盘记录）、作者口径的数字、数据需求、我们能执行的子集、状态、结论、证据、重开条件、由哪次搜索发现。

**状态**

- 未测：`harvested`（找到了）→ `triaged`（方向已确认）→ `queued`（已排进批次）→ `testing`（在测）。
- 已封存：`passed` / `partial` / `refuted` / `not_executable`（信号是真的但我们执行不了）/ `evidence_too_weak`（来源证据不够，没测就放下）/ `parked`（等预算、数据或硬件）/ `duplicate`（与另一个方向是同一机制）。

**命令**

- `oc research directions check <关键词>`：**开任何新方向前必须先跑**。同时查登记簿、全部假设卡和 `trial-families.json`；得分 ≥ 0.5 的会标成 "likely repeat"，必须先读。
- `oc research directions validate`：
  - 封存状态必须写明结论、证据和重开条件；
  - 已确认状态（triaged / queued / testing）必须有四项方向确认：`goal_fit`、`executable_subset`、`cheapest_test`、`stop_condition`。
- `oc research directions summary`：按"类别 × 状态"和"渠道"统计覆盖面。

**与现有机制的关系**

- 假设卡仍然记录单次实验；`trial-families.json` 仍然管试验计数，用于 DSR；v3 迭代仍然要 `direction-review.json` 加 `direction-check` 和 `iteration validate`。
- 登记簿位于这些机制的上游，只回答两个问题："这个方向以前做过没有"和"值不值得开卡"。

**当前内容（09-23）**

- 121 个方向、21 条搜索记录（09-23 晚）。
  - 来源：09-16 以来的全部假设卡、五份情报简报里没测过的候选、`current-view` 里的否定结论、09-22/09-23 的结论和核验结果、paperswithbacktest 的 24 个新方向，以及自建搜索栈第一波试跑的 4 个。
  - 状态：通过 3、部分通过 1、否定 23、执行不了 9、证据太弱 28、搁置 8、重复 3、已确认待测 3、找到未测 43。
- 补录时读过但没有单独登记的条目（工具类、已被其他行覆盖的同一机制）写在补录任务的报告里，查重命令能查到覆盖它们的行。

## 3. 渠道覆盖（09-23 在本服务器实测，自建搜索栈上线后）

| 渠道 | 内容 | 找链接（发现） | 读正文 |
|---|---|---|---|
| 学术论文 | arXiv、SSRN、期刊 | arXiv API；Exa | arXiv 可以；SSRN 对自动抓取返回 403，改用作者主页上的 PDF |
| 结果库 | paperswithbacktest、Ken French、AQR、JKP、OSAP、q-factor | 站内搜索 | 可以。paperswithbacktest 已抽样 2,335/5,341 个策略（`I-20260923-04`） |
| 量化博客汇总 | Quantocracy | 站内搜索 | 可以 |
| 博客 / Substack / Medium | 帖子 | Exa 语义搜索；SearXNG（Google、Brave、Bing、Yahoo） | 直连（curl_cffi）或 Jina |
| Reddit（r/algotrading、r/LETFs …） | 帖子、评论 | Exa；Arctic Shift 存档按版块全文搜索，延迟不到 1 小时 | Arctic Shift 读帖子全文和评论树，不需要账号。reddit.com 本身仍然 403；只是不能发帖 |
| X / Twitter | 推文 | 不用 cookie：Google/Brave/Yahoo 搜 `site:x.com`。**站内搜索和账号时间线要小号 cookie**（twscrape，已装好） | 单条推文：fxtwitter，不用 cookie |
| GitHub | 代码、awesome 清单 | API（代码搜索要免费 token） | 可以 |
| TradingView 脚本库 | Pine 策略 | SearXNG `site:` | 可以 |
| 公众号 | 券商金工、量化作者 | 搜狗微信（SearXNG 引擎）；Exa | 永久链接直连可读；搜狗临时链接走浏览器 |
| 雪球 | 帖子 | Exa；SearXNG `site:xueqiu.com` | **防检测浏览器 camoufox** 过阿里云 WAF |
| 知乎 | 专栏、回答 | 站内搜索要登录；用 Google/Brave/Yahoo/360 的 `site:zhuanlan.zhihu.com` | 专栏正文：camoufox |
| 聚宽 | 帖子、策略 | Exa | 只能读 Exa 的缓存副本（2–3 千字）；全站只允许大陆 IP |
| 果仁、集思录 | 帖子、策略 | Exa | 直连可读 |
| BigQuant | 帖子、策略 | Exa | 待测：camoufox 可渲染 JS |
| 实盘记录 | SIP 日线里所有 ETF/ETN 的净值、Cboe 策略指数 | — | 可以 |

**中文渠道降级（机主 09-23）**：美股相关的一手信息很少出现在中文互联网，雪球、知乎、公众号、聚宽、果仁、集思录不再主动搜。工具仍能读这些站点，遇到有价值的链接时照读。09-23 在这些渠道搜过一次行业 ETF 轮动，结果都是 A 股内容，记录在搜索日志里。

探测明细：`reports/research/intel/I-20260923-03-search-tooling.md` 附录（上午，托管工具）和 `I-20260923-05-self-hosted-search-stack.md`（下午，自建栈）。

## 4. 主题清单

每个渠道都按这张表搜，中英文各准备一套查询。

- **因子**
  - 动量变体：残差、行业、因子动量、时序
  - 反转：短期、隔夜、尾盘
  - 波动与彩票类：MAX、特质波动、跳跃
  - 流动性
  - 质量、盈利、投资、应计
  - 盈余：SUE、PEAD
  - 分析师修正
  - 内部人、13F、空头
  - 期权隐含信息
  - 文本、新闻、LLM
  - 季节性：月初、FOMC、节前
  - 资金流：指数再平衡、杠杆 ETF 调仓、月末
- **高频 / 日内**：开收盘竞价、日内动量与反转、跳空、VWAP、配对与统计套利。真高频（做市、盘口）已判定不可行，只记录，不做。
- **模型**：截面 GBDT / 神经网络、预训练时序模型、LLM 因子挖掘、强化学习、regime 模型、meta-labeling。
- **策略容器**：ETF 轮动 / TAA、杠杆 ETF、期权收入、管理期货 / 趋势、加密。

## 5. 搜索工具（09-23 机主决定：自建，不用托管 API）

机主看了上午的托管方案（SerpAPI、百度千帆、Firecrawl 云端），认为"都不太行"。要求改用自己装的开源项目，挑持续更新、星多、口碑好的，并参考其他个人量化用什么。机主提供了 TypeSafe **Jev** 的 key（只存在 `/root/.config/open-composer/search.env`，权限 600）。

**自建栈**（`scripts/setup_search_tools.sh` 装到 `/opt/oc-search`，不进项目虚拟环境）

| 层 | 项目 | 星数 / 最近更新 | 用途 |
|---|---|---|---|
| 发现 | Exa 官方 MCP 端点（免费，不要 key） | exa-mcp-server 5.0k / 09-23 | 语义搜索，中英文都行，能搜到 Reddit、Substack、雪球、聚宽、公众号 |
| 发现 | SearXNG（本机 127.0.0.1:8888） | 37.5k / 09-22 | 自建聚合搜索：默认用 Google、Brave、Bing、Yahoo；支持 `site:` |
| 发现 + 正文 | Arctic Shift（Reddit 学术存档 API） | 1.5k / 09-12 | 不经过 reddit.com 搜索和读 Reddit |
| 正文 | curl_cffi | 6.5k / 09-22 | 模仿浏览器 TLS 指纹的直连 |
| 正文 | camoufox | 12.1k / 09-21 | 防检测 Firefox，用于雪球、知乎 |
| 正文 | trafilatura | — | 从网页里提取正文 |
| 路由 / 体检 | Agent-Reach | 84.9k / 09-15 | 装了只做体检；以后接 X/Twitter 用它的 twitter 渠道 |
| 分拣 | Jev（TypeSafe） | 官方价格：输入每百万 token $0.042，输出免费 | 每条结果问 6 个带类型的问题，按概率排阅读顺序 |

**入口**：`/opt/oc-search/venv/bin/python scripts/harvest_search.py run --channel {exa,web,reddit,github} --query ...`

- 每次运行自动写一行 `search-log.jsonl`，并把排好序的结果写到 `reports/research/harvest/raw/<日期>/`。
- 同一渠道、同一查询再搜会被拒绝，除非加 `--force`；已经见过的链接不再读。
- 正文缓存在仓库外的 `/opt/oc-search/cache`。

**没选的**（理由见 `I-20260923-05`）

- Firecrawl 自建：要 Redis 和独立的浏览器服务，本机太重。
- Crawl4AI、Scrapling：与上面的读取层重叠，以后需要时可以替换。
- MediaCrawler：需要扫码登录，许可证只允许非商业使用，主攻小红书/抖音。
- RSSHub：做订阅用，等确定要长期跟踪的作者后再装。
- 公众号、雪球、知乎专用工具（we-mp-rss、pysnowball 等）：中文渠道已降级，不装。
- jev-search：需要付费的 Search1API 和 Cloudflare Workers。我们在本地复现了它"理解查询 → 多源搜索 → Jev 排序"的做法。

**还缺的，需要机主提供**

- X/Twitter：一个小号的 cookie（`auth_token` 和 `ct0`）。放进 `search.env` 后运行 `harvest_search.py x-login` 验证。美股一手信息在 X 上很多，这是现在最大的缺口。

## 6. 测试漏斗与第一批

**三层漏斗**

| 层 | 做什么 | 约束 |
|---|---|---|
| L0 | 读别人的结果，零算力 | 严禁看 2026 留出窗 |
| L1 | 用现成代码或引擎，在冻结协议下跑 | 每个家族一张 direction-review，并先预注册 |
| L2 | 训练模型 | 需要硬件 |

**第一批**（按目前证据排序）

1. **杠杆行业趋势：半导体之外的第二个状态性押注**（登记簿 `dir:levered_industry_trend_second_bet`，方向已确认）。两份"别人的结果"指向同一件事：
   - 作者维护的 49 行业组合（`I-20260923-01`，选择窗，市值加权）：黄金 66.2% / −28.8%、半导体 45.9%、银行 36.5%、航空军工 35.7% / −3.8%（夏普 1.91）。
   - 杠杆 ETF 的实盘净值：JNUG 132%、NUGT 115%、DFEN 98%、FAS 55%，与 SOXL 的相关性只有 0.19–0.49。
   - 做法：复用已冻结的 vt40 + 加档，每个行业算一次比较，并加随机挑行业的安慰剂；以 H-20260918-06 的池化 ETF 负面结果作对照。
   - 行业名单是看着选择窗挑出来的，所以只有 2026 留出窗能下结论。我们的数据里也没有已关停的杠杆基金，存在幸存者偏差。
2. **因子库里的其他发现**：
   - 经典多空因子在近期窗口多数为负。
   - JKP"会计科目变化"类因子夏普 1.8–2.4，但年化只有 5–12%、是多空结构，而且需要我们没有的时点财务数据。已搁置，重开条件是拿到免费的 SEC XBRL 财务数据。
   - 市值加权十分位组合的高收益大多是巨头股落在哪一组造成的，不作为因子信号。
3. **paperswithbacktest 约 5000 个策略的结果筛**：先查清价格和接口；免费部分先爬目录。
4. **符号跳跃变差多头腿、尾盘反转多头腿**。测试便宜，但天花板远低于门槛，只作组合或过滤用。

**已判定不做**（登记簿里都写了重开条件）

- 真高频
- 已实现偏度：独立复现显示 1990–2026 年化只有 0.19%
- 中文卖方高频因子：只有 A 股证据
- 加密趋势：原文数字本身就够不到门槛
- RD-Agent：本机跑不动
- Kronos 和通用时序基础模型：没有可交易的证据

## 7. 日期

| 日期 | 内容 |
|---|---|
| 09-23 | 登记簿上线并补录完旧方向；因子库挖掘和搜索工具核验完成；top50 卖单已提交，开盘成交，14:00 UTC 对账。 |
| 09-24（周四） | 第一波英文广搜：按第 4 节主题清单，逐项搜 Reddit（Arctic Shift）、Substack 和博客（Exa）、Quantocracy、TradingView、GitHub 清单、arXiv，结果进登记簿。 |
| 09-25（周五） | 批次 1 第 1 项（杠杆行业趋势）完成 direction-review、预注册并回测；设计因子库排名靠前家族的 L1 测试。 |
| 09-26（周六） | 出批次 1 结果；如果机主提供了小号 cookie，就接入 X 跑第二波。 |
| 09-26 至 09-29 | 续期工程：把波动率目标、加档、回撤清仓移植进模拟盘运行时，逐日核对与研究引擎一致；S2 的 XLK 腿缺陷一并修。 |
| 09-30 23:00 UTC 之前 | S1–S3 续期生效（10-02 到期；续期需机主确认），10 月调仓按新规则执行。 |

## 8. 09-23 已完成

- **top50 清仓**：50 笔卖单约 $100.5k，09-23 02:31 UTC 被模拟盘接受，当天开盘成交，14:00 UTC 对账确认；删除 3 条下单定时任务；新增 `oc paper rehearsal-run --liquidate --reason`，附 5 个测试。
- **方向登记簿**：搜索日志加 `oc research directions check/validate/summary` 三个命令，附 9 个测试。
- **两个过时测试**：它们原本读真实账本，现改为使用临时目录。
- **S2 缺陷（记录，未修）**：总敞口检查里，已持有的 SMH 按实时价计算，待买的 XLK 按 08-31 的旧价计算，两者相加超过 $15k 上限，所以 XLK 腿一直被推迟。
- **登记簿补录**：旧卡、情报简报、否定结论全部补进；paperswithbacktest 抽样 2,335/5,341 个策略，合并出 24 个新方向（`I-20260923-04`）。
- **自建搜索栈**（`I-20260923-05`）：`scripts/setup_search_tools.sh` 装到 `/opt/oc-search`，`scripts/harvest_search.py` 负责搜索、读正文、Jev 分拣、写日志，附 7 个测试。查重命令改为忽略虚词。
- **第一波试跑**（6 次搜索）：
  - 新登记 `dir:letf_published_rules_live_tracked`（HFEA、9Sig、LRS 的公开真钱实测）；
  - 新登记 `dir:letf_multi_signal_regime_vote`（多信号投票的杠杆 ETF 择时，可作 S3 回撤闸门的候选）；
  - 新登记 `dir:tqqq_levered_gold_pair_rebalance`（TQQQ + 3 倍黄金）；
  - A 股 ETF 轮动帖记为重复。
- **中文渠道降级**：机主判断美股一手信息很少在中文互联网，不再主动搜。
