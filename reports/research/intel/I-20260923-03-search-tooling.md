# I-20260923-03：检索/抓取工具选型 —— Reddit、论坛、X、TradingView 与中文社区（知乎/雪球/公众号/聚宽/BigQuant）可达性

纯联网调研 + 本机 curl 探测，不涉及策略回测。任务背景：我们研究的很多交易因子/策略只在帖子类来源里出现——Reddit、论坛、Substack/Medium、X、TradingView 脚本页、聚宽/JoinQuant、BigQuant、知乎、雪球、微信公众号——而现有工具（Claude 内置 WebFetch/WebSearch、本机无 key 的 curl）覆盖不到其中大半。本轮对 10 类候选工具/接口逐一打开官方定价/文档页面核对数字（不采信仅搜索摘要得到的数字，除非明确标注"未核实"），并对约 20 个域名做了本机可达性探测。共发起约 40 次 WebFetch/WebSearch 调用 + 若干次 curl 直连（含用 `r.jina.ai` 作为读取代理的探测）。**不涉及注册任何账号、写入任何 key、安装任何包、修改任何配置。**

判定口径：**可用**（官方文档确认可行且大概率解决我们的痛点）/ **部分可用**（可行但有明确缺口，写明缺口）/ **不适用**（官方文档或实测证明解决不了我们的痛点）/ **未核实**（未能打开一手来源，标注原因）。

---

## 汇总表

| # | 选项 | 解决哪些渠道 | 免费额度 | 付费价格 | 官方 MCP 包 | 本机可达 | 判定 |
|---|---|---|---|---|---|---|---|
| 1 | **Brave Search API** | 通用网页（含可能的论坛/博客，Reddit 覆盖未证实） | 每月 **$5 免费 credit**（≈1000 次调用），是否需要信用卡未在官方页确认 | **$5.00 / 1000 次**（Web Search/AI Grounding），Answers **$4.00/1000**，50 rps | `@brave/brave-search-mcp-server`（npm/Docker，Brave 官方仓库） | `api.search.brave.com` 根路径 301，`/res/v1/web/search` 无 key 返回 422（端点存在） | 部分可用 |
| 2 | **Tavily** | 通用网页，`include_domains`/`exclude_domains` 可显式限定站点（如 reddit.com），但是否真的抓取到 Reddit 内容未验证 | **1000 credits/月，明确"无需信用卡"** | Pay-as-you-go **$0.008/credit**；套餐从 **$30/月 4000 credits** 起 | `tavily-mcp`（npm，官方 tavily-ai/tavily-mcp） | `api.tavily.com` 根路径 200 | 部分可用 |
| 3 | **Exa** | 通用网页 + 结构化类目（company/news/personal site/research paper 等），**官方文档未列出 Reddit 或 X 为类目/索引来源** | 新账号 **$20 免费 credit**（约 2800 次搜索）+ 每月额外 **$10** | Search **$7/1000 次**（前 10 条结果），超出部分 $1/1000；Contents **$1/1000 页** | `exa-mcp-server`（npm，官方 exa-labs/exa-mcp-server） | `api.exa.ai` 根路径 404，`/search` 404（端点需要 POST，非不可达） | 部分可用（论坛/社媒覆盖存疑） |
| 4 | **Firecrawl** | 网页抓取/渲染（复杂反爬/JS 站点），**未见证据能绕开聚宽这类"仅限中国大陆 IP"的地理限制** | **1000 credits/月，明确"无需信用卡"** | 按年计费：Hobby $16/mo（5000 credits）起，Standard $83/mo（100000） | `firecrawl-mcp`（npm，官方 mendableai/firecrawl-mcp-server） | `api.firecrawl.dev` 200 | 部分可用（抓取器，非发现器；聚宽地理限制未解决） |
| 5 | **SerpAPI** | 直接代理 Google（也支持 Baidu 等引擎）真实搜索结果页——**目前找到的、最可能真正"搜出" Reddit/知乎/雪球链接的工具**，因为它复用的是 Google/百度自己的索引深度 | **250 次/月**，50 次/小时节流 | Starter **$25/月 1000 次** | `serpapi-mcp-server`（官方 serpapi 组织，另有托管版 mcp.serpapi.com） | `serpapi.com` 200 | 可用（发现层，仍需配合抓取工具拿正文） |
| 6 | **Jina AI**（r.jina.ai 读取器 + s.jina.ai 搜索） | 读取器可抓取很多反爬页面的正文（含渲染 JS），**但实测不能绕开 Reddit 自己的反爬墙** | 读取器无 key **20 RPM**，免费 key **500 RPM** + **1000 万 免费 tokens**；搜索**无 key 直接 401，必须有 key** | 按 token 计费（页面未给出具体 $/M token 数字） | 无独立 MCP 包名被确认；社区有多个非官方封装 | `r.jina.ai/<url>` 200（内容取决于目标站）；`s.jina.ai` 401 | 部分可用（抓取器，Reddit 主站仍被挡） |
| 7 | **Reddit 官方 Data API** | Reddit 全站——**但官方 FAQ 明确写"不能把开发者工具/API 用于学术研究，唯一授权渠道是 Reddit For Researchers 项目"**，这比限速更根本 | 免费（个人脚本 app），但见右侧判定 | 商业用途/超额研究需另签合同（未标价） | 非官方候选 `GeLi2001/reddit-mcp`（PRAW 封装，4 星，维护状态不明） | **`oauth.reddit.com` 403；`www.reddit.com`/`redditinc.com` 被 WebFetch 工具直接拒绝（策略层拒绝，非网络层）**；用 `r.jina.ai` 代理抓 `redditinc.com` 条款页可读到 200，但代理抓真实 subreddit 搜索页时收到的仍是 Reddit 自己返回的"blocked by network security"页面 | **不适用（研究用途被官方明文禁止，且技术上也大概率被挡）** |
| 8 | **GitHub REST/搜索 API** | 代码/仓库/issue，用于查因子库、策略仓库、MCP 生态本身 | 未认证 60 次/小时；代码搜索固定 **10 次/分钟**（认证后也是） | 个人令牌（PAT）5000 次/小时 | `github/github-mcp-server`（官方，Docker 或本地 stdio + PAT） | `api.github.com` 200（headers 显示 `x-ratelimit-limit: 60`） | 可用（非我们缺的那类渠道，但值得保留） |
| 9a | **OpenAlex** | 学术论文全文检索 | **有免费 key：$1/天预算**；2026-02 起 **mailto"礼貌池"已失效**，无 key 情形的具体额度未在我们打开的官方页上复核（二手来源称 $0.10/天） | 列表/过滤 $0.10/1000 次，全文/语义检索 $1/1000 次，PDF 下载 $10/1000 次 | 无官方 MCP，仅第三方 | `api.openalex.org` 200（即使带 mailto 参数也不报错） | 可用（但要重新适配：mailto 不再是免费票，需要注册 key） |
| 9b | **Semantic Scholar** | 学术论文全文检索 | 无 key 与其他匿名用户共享一个池子（官方页未给出具体数字）；**有 key：1 请求/秒**，可申请更高 | 未见公开定价（申请制） | 无官方 MCP，仅第三方 | `api.semanticscholar.org` 探测当时返回 **429** | 部分可用（建议直接申请 key） |
| 9c | **arXiv API** | 论文全文检索/元数据 | 免费，无 key，限速 **每 3 秒 1 次请求、单连接** | 免费 | 无官方 MCP | `export.arxiv.org` 200 | 可用（已在用，规则未变） |
| 10a | **Kimi (Moonshot) `/v1/tools/search`** | 中文/英文通用网络搜索，Pro 版支持 `sites` 参数限定站点（**未点名知乎/雪球，但机制上可以指定域名**） | 无独立免费额度信息 | Basic **$0.002/次**，Pro **$0.003/次**（仅在有结果时计费）；旧版 `$web_search` $0.005/次将于 **2026-10-20 停用** | 无 | 未探测（无 key 的接口测试超出授权范围） | 部分可用（Chinese-web 候选之一） |
| 10b | **智谱 GLM `web_search`** | 4 个引擎可选（自研 basic/pro + 搜狗 + 夸克），返回 URL；**官方文档未点名知乎/公众号/雪球覆盖** | 未在官方定价页找到工具调用价格 | **未在官方定价页确认**（论坛二手消息：std ¥0.01/次，pro ¥0.03/次，未核实） | 无 | 未探测 | 未核实（价格缺口） |
| 10c | **阿里云 DashScope/Qwen `enable_search`** | Qwen Max/Plus/Flash 内置联网搜索，`enable_source:true` 返回来源 URL；覆盖新浪/百度/东方财富等通用网页，**未点名知乎/公众号/雪球** | 未标注 | **官方模型定价页完全没有联网搜索这一行**（confirmed 缺失，非未查到） | 无 | 未探测 | 未核实（价格缺口） |
| 10d | **百度智能云千帆 AI 搜索 / 百度搜索 API** | 百度自己的搜索结果，返回来源 URL，中文覆盖面广（可能间接覆盖知乎/雪球等被百度收录的内容） | **100 次/天免费**（百度搜索），智能搜索生成同享额度 | 百度搜索 **¥0.036/次**；智能搜索生成常规 ¥0.06/次、限时折扣 ¥0.008/次 | 支持 MCP 接入（文档提及，未展开） | 未探测 | 可用（本轮唯一价格+机制都在官方页核实到的中文搜索 API） |
| 11 | **DuckDuckGo HTML** *(背景信息中提到的"不确定项"，顺手复核)* | 通用网页 | 免费无 key | 免费 | 无 | `html.duckduckgo.com/html/?q=...` 返回 **200，但内容是图片验证码"anomaly"挑战页**，不是搜索结果 | 不适用 |

---

## 逐项详情

### 1. Brave Search API

官方定价页 [api-dashboard.search.brave.com/documentation/pricing](https://api-dashboard.search.brave.com/documentation/pricing)（页面未显示更新日期）：Web Search/AI Grounding **"$5.00 per 1,000 requests"**，限速 **"50 requests per second"**；Answers 计划 **"$4.00 per 1,000 queries"**，2 rps；两者都写"Includes free $5 in credits every month"。页面没有明说要不要信用卡；第三方文章（[implicator.ai](https://www.implicator.ai/brave-drops-free-search-api-tier-puts-all-developers-on-metered-billing/)）称 2026 年 2 月起旧的 2000–5000 次/月免费额度被这套 credit 制取代，且需要绑卡——这条历史沿革未在 Brave 自己的页面上复核。

官方 MCP：[github.com/brave/brave-search-mcp-server](https://github.com/brave/brave-search-mcp-server)，npm 包 `@brave/brave-search-mcp-server`，也有 Docker 镜像。旧的 `@modelcontextprotocol/server-brave-search` 已被归档（[modelcontextprotocol/servers-archived](https://github.com/modelcontextprotocol/servers-archived/tree/main/src/brave-search)）。

是否收录 Reddit/论坛：Brave 官方博客称拥有"独立索引"、约 400 亿网页，但这条只来自搜索摘要（未独立打开 brave.com/search/api/ 核实），且没有任何页面明确说"包含 reddit.com"。

### 2. Tavily

官方文档 [docs.tavily.com/documentation/api-credits](https://docs.tavily.com/documentation/api-credits)：**"You receive 1,000 free API Credits every month... No credit card required."** Basic 搜索 1 credit/次，Advanced 2 credits/次。定价页 [tavily.com/pricing](https://www.tavily.com/pricing)（页脚"©2026 Tavily Inc."）：按量付费 **"$0.008 / credit"**，Project 套餐滑动定价，$30/月起对应 4000 credits。

API 参考 [docs.tavily.com/documentation/api-reference/endpoint/search](https://docs.tavily.com/documentation/api-reference/endpoint/search) 确认 `include_domains`（最多 300 个域名）与 `exclude_domains`（最多 150 个）参数存在。官方 MCP 仓库 [tavily-ai/tavily-mcp](https://github.com/tavily-ai/tavily-mcp)，npm 包 `tavily-mcp@latest`。**缺口**：没有任何官方页面说明 Tavily 的爬虫是否真的收录 reddit.com 或论坛内容；`include_domains` 只保证"如果收录了就能筛出来"，不保证"有没有收录"，而我们没有 key 无法用真实查询验证。

### 3. Exa

官方定价页 [exa.ai/docs/reference/pricing](https://exa.ai/docs/reference/pricing)：Search **"$7 / 1k requests"**（含前 10 条结果，超出部分 "$1 / 1k results"）；Contents **"$1 / 1k pages, per content type"**；新账号 **"$20 in free credits (around 2,800 searches)"**，另有每月 **"$10 in credits"** 的免费档。

Search 接口参考 [exa.ai/docs/reference/search](https://exa.ai/docs/reference/search)（docs.exa.ai/reference/search 会 307 跳转到这里）明确列出 `category` 参数官方取值为 **"company, publication, news, personal site, financial report, and people"**，并说明"other strings are accepted and used as category hints"——也就是说传入 "tweet"/"reddit" 这类非枚举字符串不会报错，但只是"提示"而非保证命中。页面全文没有出现 Reddit 或 X/Twitter 相关的索引承诺。第三方 MCP 技能列表（LobeHub）里有一个叫 `web-search-advanced-tweet` 的 Exa 工具条目，暗示"tweet"这个 hint 在实践中可能有效，但这不是 Exa 自己文档给出的保证。

官方 MCP：[exa-labs/exa-mcp-server](https://github.com/exa-labs/exa-mcp-server)，npm 包 `exa-mcp-server`，默认工具 `web_search_exa`/`web_fetch_exa`，可选 `web_search_advanced_exa`。

### 4. Firecrawl

官方定价页 [firecrawl.dev/pricing](https://www.firecrawl.dev/pricing)：免费层 **"1,000 credits / month"**，**"No cost, no card, no hassle."** 年付：Hobby $16/mo（5000 credits）、Standard $83/mo（100000，标"Recommended"）、Growth $333/mo（500000）、Scale $599/mo（1,000,000）。页面写明 **"Effective September 4, 2026."**

Scrape 接口参考 [docs.firecrawl.dev/api-reference/endpoint/scrape](https://docs.firecrawl.dev/api-reference/endpoint/scrape) 里的 `proxy` 参数有三档：`basic`（"Fast and usually works"）、`enhanced`（"for scraping sites with advanced anti-bot solutions... billed at the same credit cost as basic"）、`auto`（basic 失败自动重试 enhanced，"no credit surcharge"）。**注意**：当前文档用的术语是 enhanced/auto，不是第三方定价汇总文章里常提到的"stealth mode"这个名字；且文档只承诺"应对高级反爬"，没有一处明确说能绕开数据中心 IP 的地域封锁（比如聚宽要求中国大陆 IP 这种）——这条我们没有 key，无法实测。

官方 MCP：[mendableai/firecrawl-mcp-server](https://github.com/mendableai/firecrawl-mcp-server)，自称"🔥 Official Firecrawl MCP Server"，npm 包 `firecrawl-mcp`。

### 5. SerpAPI

官方定价页 [serpapi.com/pricing](https://serpapi.com/pricing)：免费层 **"250"** 次搜索/月，**"50"** 次/小时节流；最便宜付费档 Starter **"$25/mo"** 对应 **"1,000"** 次/月（多篇第三方文章称免费层是 100/月，与我们直接打开的官方页数字不一致，以官方页为准）。

官方 MCP：[serpapi/serpapi-mcp-server](https://github.com/serpapi/serpapi-mcp-server)（serpapi 组织维护，MIT 协议，173 星），另有托管版本 mcp.serpapi.com（需要 API key）。SerpAPI 本质是把 Google（以及百度、必应、DuckDuckGo 等其它引擎）的真实搜索结果页结构化返回——这是本轮找到的**唯一一个"复用别人已经建好的索引"而不是自建小索引**的选项，考虑到 Google 对 Reddit 内容的收录深度是出了名的好（且不受制于我们自己爬不动 reddit.com），SerpAPI 大概率是目前最可能真正"搜到" Reddit 帖子链接的工具，只是它给的是搜索结果（标题+摘要+链接），要拿正文还需要配合抓取工具。

### 6. Jina AI（r.jina.ai / s.jina.ai）

官方页 [jina.ai/reader/](https://jina.ai/reader/)：r.jina.ai 读取器无 key **"20 RPM"**，免费 key **"500 RPM"**，**"Every new API key comes with 10M free tokens!"**；页面写"We introduced a new pricing model on May 6th, 2025."

**实测**（本机 curl，2026-09-23）：
- `s.jina.ai/?q=test` 无 key 直接返回 **HTTP 401**，body 是 `{"code":401,"name":"AuthenticationRequiredError",...}`——搜索端点比读取器端点严格得多，必须有 key。
- `r.jina.ai/https://redditinc.com/policies/data-api-terms`（reddit 公司政策站，不是主站）返回 **HTTP 200** 且拿到完整条款正文。
- `r.jina.ai/https://www.reddit.com/r/algotrading/search/?q=momentum`（真正的 reddit.com 子版搜索页）同样返回 Jina 自己的 200，但**里面装的是 Reddit 自己返回的拦截页**："You've been blocked by network security. To continue, log in to your Reddit account or use your developer token." **也就是说 Jina 读取器不能绕开 Reddit 主站的反爬墙**，只是恰好能读到 Reddit 公司自己不设防的政策类子站。

### 7. Reddit 官方 Data API（含 MCP 生态）—— 本轮最重要的一条发现

背景信息里说"WebFetch 拒绝 reddit.com"——本轮直接复现：对 `https://www.reddit.com` 和 `https://redditinc.com/policies/data-api-terms` 用 WebFetch 都得到工具层面的拒绝（"Claude Code is unable to fetch from X"），对 `support.reddithelp.com` 得到真实的网络层 403。绕过办法是用 `r.jina.ai` 作代理去读 `redditinc.com` 和 `support.reddithelp.com`（这两个域名不是 reddit.com/oauth.reddit.com 主站，风控更松），因此拿到了官方条款原文：

- **Data API Terms**（[redditinc.com/policies/data-api-terms](https://redditinc.com/policies/data-api-terms)，经 r.jina.ai 代理读取，HTTP 200）："If you are interested in using the Data APIs for commercial purposes, **research in excess of rate limits**, or for any use that is not expressly permitted under the Data API Terms, then you will need to enter into a separate agreement with Reddit."
- **开发者平台 FAQ**（[reddithelp.com/hc/en-us/articles/14945211791892](https://reddithelp.com/hc/en-us/articles/14945211791892)，同样经代理读取）在"Research"一节明确写：**"Can I perform research using Reddit developer tools and services? No. The only official and authorized avenue for performing research using Reddit data is through the Reddit For Researchers (RFR) program. Using developer tools, APIs, or unauthorized third-party tools for academic research is a violation of our policies."**

**这条比限速更根本**：即使我们创建一个个人 "script" 类型的 app、遵守限速，只要目的是"研究"（我们的确切用例——研究交易因子/策略讨论），按 Reddit 自己的 FAQ 就已经违反政策，唯一授权路径是申请 Reddit For Researchers 项目（面向学术/研究机构的单独审批流程，本轮未展开核实其准入条件）。

限速数字方面：能打开的、Reddit 自己给出的唯一具体数字来自**已归档**的 2017 年 wiki（[reddit-archive/reddit/wiki/API](https://github.com/reddit-archive/reddit/wiki/API)，仓库 2017-11-09 起只读）："Clients connecting via OAuth2 may make up to 60 requests per minute." 多篇 2026 年第三方文章称当前是"每个 OAuth client 100 次/分钟"，但 `developers.reddit.com/docs` 实际指向的是无关的 Devvit（Reddit 互动 App 平台）文档、`/docs/api` 返回 404，我们没能在预算内找到一个官方现行页面把这个数字钉死。Responsible Builder Policy 页面（[support.reddithelp.com/hc/articles/42728983564564](https://support.reddithelp.com/hc/articles/42728983564564)）标注"Updated 3 months ago"（相对 2026-09-23，约 2026 年年中），确认限速规则确实存在且是官方正在维护的政策，但我们抓到的内容里没有具体数字。

MCP 候选：[GeLi2001/reddit-mcp](https://github.com/GeLi2001/reddit-mcp) 用官方 PRAW 库封装，支持站内搜索，但只有 4 星/12 commits，维护状态不明；更关键的是，无论这个 MCP 实现质量如何，只要走 Reddit 官方 API，就撞上面这条"研究用途需要单独走 RFR 项目"的政策墙。

### 8. GitHub REST/搜索 API 与官方 MCP

官方文档 [docs.github.com/en/rest/search/search](https://docs.github.com/en/rest/search/search)：代码搜索 `/search/code` **"requires you to authenticate and limits you to 10 requests per minute"**——这是 GitHub 所有搜索端点里最严的一个（其余搜索端点认证后 30/分钟，未认证 10/分钟）；文档标注 API 版本 "2026-03-10"。速率限制总览页 [docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api](https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api)：未认证 **"60 requests per hour"**，个人令牌认证 **"5,000 requests per hour"**（页面没有区分 fine-grained 和 classic PAT）。本机对 `api.github.com/rate_limit` 的 curl 探测也确认 headers 里 `x-ratelimit-limit: 60`（未认证），与文档一致。

官方 MCP：[github/github-mcp-server](https://github.com/github/github-mcp-server)，Docker（`ghcr.io/github/github-mcp-server`）或本地 stdio 二进制，都靠 `GITHUB_PERSONAL_ACCESS_TOKEN` 认证。这个渠道解决的不是"帖子类"缺口，而是查因子库代码仓库/README/issue，本来就是我们已在用的能力，这里只是把限速数字钉实。

### 9. 学术类 API

**OpenAlex**：官方帮助中心定价页 [help.openalex.org/access/example-costs/](https://help.openalex.org/access/example-costs/)（页面标注日期 **"August 9, 2026"**）："Every account gets **$1 of usage per day for free**"（需要免费 key）。分项成本：单条实体查询免费；列表/过滤查询 $0.10/1000 次；全文检索 $1/1000 次；语义检索 $1/1000 次；PDF 下载 $10/1000 次。**这是一次模式切换**：旧的 `mailto=` 礼貌池已经不再是免费机制（二手来源称 2026 年 2 月切换，未独立复核切换公告本身；但我们打开的官方页完全没提 mailto/polite pool），现在免费额度靠注册 key 换取每天 $1 的预算。我们的探测 `api.openalex.org/works?search=momentum&mailto=research@example.com` 返回 200（mailto 没有导致报错，但也不清楚是否还带来任何优待）。

**Semantic Scholar**：官方教程页 [semanticscholar.org/product/api/tutorial](https://www.semanticscholar.org/product/api/tutorial)："using an individual API key automatically gives a user **a 1 request per second rate** across all endpoints"（"introductory"档，"可能在审核后获得更高配额"）；未认证用户"share a single API key"（这句没给出具体数字）。我们探测 `api.semanticscholar.org/graph/v1/paper/search?query=momentum` 当场收到 **429**，说明这个共享池确实很容易触顶。之前常被引用的社区仓库 allenai/s2-folks 已在 [README](https://github.com/allenai/s2-folks/blob/main/README.md) 标注"not maintained as of January 23, 2025"，不能作为现行数字来源。

**arXiv**：官方 API 使用条款 [info.arxiv.org/help/api/tou.html](https://info.arxiv.org/help/api/tou.html)："Make no more than **one request every three seconds**, and limit requests to a single connection at a time"，无每日上限，需要更高吞吐量要联系官方支持。探测 `export.arxiv.org/api/query...` 200，符合预期，这条我们已经在用、规则没变。

### 10. 不依赖中国大陆 IP 的中文网络访问：四个大模型内置联网搜索

**Kimi (Moonshot)**：官方定价页 [platform.kimi.ai/docs/pricing/tools](https://platform.kimi.ai/docs/pricing/tools)。旧的内置工具 `$web_search` 按 **"$0.005"**/次调用计费（仅当模型真的触发调用时），**"is expected to be deprecated on October 20, 2026"**。替代方案 `/v1/tools/search` 端点：**"Web Search Basic: $0.002 / call"**、**"Web Search Pro: $0.003 / call"**，"only when the search_results field in the response is non-empty"才计费；Pro 额外支持用 `sites` 参数把结果限定在特定站点、用 `time_window` 限定时间范围，Basic 不支持。页面没有点名知乎/雪球等具体站点作为例子，但 `sites` 参数在机制上可以指定任意域名。

**智谱 GLM**：官方接口文档 [docs.bigmodel.cn/api-reference/工具-api/网络搜索](https://docs.bigmodel.cn/api-reference/%E5%B7%A5%E5%85%B7-api/%E7%BD%91%E7%BB%9C%E6%90%9C%E7%B4%A2) 列出四个可选引擎：`search_std`（智谱基础版）、`search_pro`（智谱高级版）、`search_pro_sogou`（搜狗）、`search_pro_quark`（夸克），返回字段含 `link`（URL）、title、content、publish_date；文档没有点名知乎/微信公众号/雪球这几个我们关心的站点。**价格缺口**：官方定价页 [open.bigmodel.cn/pricing](https://open.bigmodel.cn/pricing) 只有按 token 计的模型价格表，完全没有 `web_search` 这一行；社区常引用的"std ¥0.01/次、pro ¥0.03/次"来自论坛帖子（[linux.do/t/topic/491906](https://linux.do/t/topic/491906)），未在官方页核实。

**阿里云 DashScope/Qwen**：官方文档 [help.aliyun.com/zh/model-studio/web-search](https://help.aliyun.com/zh/model-studio/web-search) 确认 `enable_search: true` 开启联网搜索，2025 年 7 月后发布的 Qwen Max/Plus/Flash 默认支持；`enable_source: true` 会在结果里带上来源 URL；举例覆盖新浪、百度、东方财富等通用网页，**没有点名知乎/公众号/雪球**；`search_strategy: agent` 会有"额外收费"但没写具体数字。专门核对了官方模型定价页 [help.aliyun.com/zh/model-studio/model-pricing](https://help.aliyun.com/zh/model-studio/model-pricing)，**确认这个页面完全没有联网搜索这一行**——这是查证了"没有"，不是没查到。

**百度智能云千帆**：官方 API 参考 [cloud.baidu.com/doc/qianfan-api/s/Wmbq4z7e5](https://cloud.baidu.com/doc/qianfan-api/s/Wmbq4z7e5)（页面标注"更新时间：2026-09-22"）：百度搜索 **"¥0.036/次调用"**，**100 次/天免费**，单账号每天上限 100,000 次（更高需联系客服），返回结果含 `url` 字段。另一个官方定价说明页 [cloud.baidu.com/doc/qianfan-docs/s/Jm8r1826a](https://cloud.baidu.com/doc/qianfan-docs/s/Jm8r1826a)（标注 2026-07-09）：智能搜索生成（AI 摘要版）常规 ¥0.06/次，**限时折扣 ¥0.008/次**，与百度搜索共享同一份 100 次/天免费额度。这是本轮**唯一一个机制和价格都在官方页面上核实到、且明确返回来源 URL** 的中文搜索 API。

---

## 附：本机可达性探测（`curl -s -o /dev/null -w "%{http_code}" -m 15 -A "Mozilla/5.0"`，2026-09-23 UTC）

| 域名/端点 | 状态码 | 备注 |
|---|---|---|
| `api.search.brave.com` | 301 | 根路径重定向；`/res/v1/web/search?q=test` 无 key 返回 422（端点本身可达，缺 key/参数） |
| `api.tavily.com` | 200 | 根路径可达 |
| `api.exa.ai` | 404 | 根路径 404；`/search` 也 404（POST-only 端点，非不可达） |
| `api.firecrawl.dev` | 200 | 可达 |
| `serpapi.com` | 200 | 可达 |
| `s.jina.ai` | 401（首测曾见 403，随查询参数变化） | 无 key 一律拒绝 |
| `r.jina.ai/https://example.com` | 200 | 读取器本身工作正常 |
| `oauth.reddit.com` | 403 | 预期内（OAuth 端点需要 Basic Auth） |
| `www.reddit.com` | 403（curl 直连）；WebFetch 工具层直接拒绝 | 两种拒绝分属不同层：网络层 403 + 工具策略拒绝 |
| `redditinc.com/policies/data-api-terms` | WebFetch 工具层拒绝；经 `r.jina.ai` 代理可读到 200 | 见第 7 节 |
| `api.openalex.org/works?search=momentum&mailto=...` | 200 | mailto 参数未报错，但已不是免费票（见第 9 节） |
| `api.semanticscholar.org/graph/v1/paper/search?query=momentum` | 429 | 匿名共享池很快触顶 |
| `export.arxiv.org/api/query?search_query=all:momentum&max_results=1` | 200 | 符合官方条款 |
| `www.zhihu.com` | 302（一次）/ 403（另一次，`BLB` 反爬网关） | 两次探测结果不同，均指向反爬/风控层，不是稳定可用 |
| `xueqiu.com` | 200，但正文是阿里云 WAF（`aliyun_waf_*`）挑战标记 | 状态码可达，内容大概率是反爬质询页，不是真实雪球页面 |
| `weixin.sogou.com`（搜狗微信，公众号内容的事实标准搜索入口） | 200，看起来是真实页面外壳 | 值得单独记住：这是免费、无需 key、专门收录微信公众号内容的官方入口 |
| `bigquant.com` | 200，真实应用外壳 | 可达 |
| `www.tradingview.com/scripts/` | 200，真实页面 | 可达，脚本页公开 |
| `html.duckduckgo.com/html/?q=momentum+trading+reddit` | 200，但正文是图片验证码"anomaly"挑战页 | 背景信息里的"202 挑战页"在本次探测里表现为 200+验证码页，结论一致：不可用 |

---

## 推荐的最小工具组合（最多 4 项，按"每美元覆盖的渠道数"排序）

判断逻辑：我们真正缺的是两类能力——① 一个能"搜到"Reddit/论坛/知乎/雪球这些我们爬不动的站点的**发现层**（因为自建小索引的 Brave/Tavily/Exa 都没有证据证明收录了这些站）；② 一个能把发现层给出的具体链接**转成正文**的抓取层（因为很多目标站对直连 curl/WebFetch 有反爬）。Reddit 官方 API 路线因第 7 节的政策原因（研究用途被明文禁止）**不建议**作为路径，改用"搜索引擎已经索引的公开页面"更安全也更省事。

1. **SerpAPI**（发现层，英文为主，Reddit 命中率最高的选项）—— 复用 Google 自己的索引深度，是目前最可能真正搜出 Reddit/论坛帖子链接的工具。**owner 需要做的事**：在 [serpapi.com](https://serpapi.com) 注册账号拿 API key；免费 250 次/月够先试；确认要长期用再订 Starter $25/月。
2. **百度智能云千帆「百度搜索」API**（发现层，中文为主）—— 本轮唯一机制+价格都在官方页核实到、明确返回来源 URL 的中文搜索接口，¥0.036/次≈$0.005，100 次/天免费。**owner 需要做的事**：在 [cloud.baidu.com](https://cloud.baidu.com) 注册并开通千帆控制台（大概率需要实名认证，本轮未核实具体门槛），领取 AK/SK。
3. **Jina Reader (r.jina.ai)**（抓取层，近乎免费）—— 把①②搜到的具体链接转成正文，已验证能读掉不少反爬页面（但读不掉 Reddit 主站的反爬墙）。**owner 需要做的事**：不注册也能用（20 RPM）；想要 500 RPM + 1000 万免费 token 就去 [jina.ai](https://jina.ai) 领一个免费 key。
4. **Firecrawl**（抓取层备选，处理 Jina 读不动的重 JS/强反爬页面，如 BigQuant/TradingView 这类应用外壳站）—— 1000 credits/月免费不用卡。**owner 需要做的事**：在 [firecrawl.dev](https://www.firecrawl.dev) 注册拿 key；官方 MCP 包 `firecrawl-mcp`。

**未纳入前四但仍可选**：Brave（更便宜的英文发现层备胎，但 Reddit 覆盖未证实）、Tavily（`include_domains` 机制很适合"只要 reddit.com"这种场景，但同样没证实真收录了 Reddit）、Exa（适合找 Substack/个人博客/研究论文类长文，不建议指望它覆盖论坛/社媒）、Kimi `/v1/tools/search`（如果百度搜索的中文覆盖不够，Kimi Pro 的 `sites` 参数是第二选择，$0.003/次）。**Reddit 官方 API 和 GLM/DashScope 的联网搜索本轮均不建议优先投入**：前者是政策问题，后两者是本轮没能在官方页上找到价格，值得先补这个缺口再决定，而不是先接入。

---

## 未能核实的事项

- Brave/Tavily/Exa 是否真的收录 reddit.com 或典型论坛内容——三家官方文档都没有正面回答，我们也没有 key 做真实查询验证。
- SerpAPI 的 `engine=baidu` 等非 Google 引擎的完整度/可靠性——未测试，只确认了 Google 相关的免费额度和价格。
- Firecrawl 的 `enhanced`/`auto` 代理是否包含中国大陆出口节点，能否用于访问聚宽这类"仅限中国大陆 IP"的地理限制站点——文档只提到国家/语言模拟，没有明确列出可用地区清单。
- Reddit 当前（2026 年）官方 OAuth 限速的准确数字——只找到已归档的 2017 年"60 次/分钟"，`developers.reddit.com` 实际指向无关的 Devvit 文档；Responsible Builder Policy 页面打开了但没能在预算内定位到具体数字。
- 通过 `r.jina.ai` 抓取 reddit.com **具体帖子永久链接**（而非我们测试的 subreddit 搜索页）是否同样被挡——只测试了一个路径，不能排除其他路径表现不同。
- GitHub 细粒度（fine-grained）与经典（classic）个人令牌的限速是否有差异——官方页面我们读到的内容没有区分。
- OpenAlex 匿名（无 key）请求的每日预算具体数字（二手来源称 $0.10/天）——未在官方页面上独立复核到这个具体数字。
- 智谱 GLM 和阿里云 DashScope 的联网搜索工具调用价格——两边官方定价页都没有这一行，只知道机制，不知道多少钱。
- 智谱/DashScope/Kimi/百度四家是否真的覆盖知乎、微信公众号、雪球——没有一家官方文档正面点名这三个站，只能说"不能排除，也不能确认"。
- SerpApi 官方组织下 `serpapi-mcp-server` 与 `serpapi-mcp` 两个仓库的具体关系（哪个是主线）——未展开核实。
- s.jina.ai 搜索本身的具体计费数字（只确认了必须有 key，没确认 $/次或 $/token）。
