# I-20260923-05：自建搜索栈 —— Exa + SearXNG + Arctic Shift + camoufox，Jev 分拣

**背景（机主 09-23 下午）**

- 上午 `I-20260923-03` 提出的托管方案（SerpAPI、百度千帆、Firecrawl 云端），机主认为"都不太行"。
- 要求自己装项目，点名 Agent-Reach 和"Jev + 爬虫"。挑持续更新、星多、口碑好的，或者参考其他个人量化在用什么。
- 机主提供了 TypeSafe Jev 的 key。
- 随后又定了一条：美股相关的一手信息很少出现在中文互联网，**中文渠道不必主动搜**。

**约束**：这台服务器是 DigitalOcean 数据中心 IP（Reddit、知乎、雪球、聚宽都对这类 IP 设防），没有 Docker，内存 3.9 GB，CPU 不支持 AVX2。工具一律装在 `/opt/oc-search`，不进项目虚拟环境。

**来源卡**：`reports/harness/source_cards/i20260923_self_hosted_search.jsonl`（ss01–ss11）。

## 1. 结论

- **英文渠道**：上午判为"进不去"的，除 X/Twitter 以外已全部可达。Reddit 通过第三方存档读取，不经过 reddit.com。每月花费 $0；Jev 另计，几乎为零。
- **组合**：
  - 发现层：Exa 免费 MCP 端点、自建 SearXNG、Arctic Shift（Reddit 存档）、GitHub API；
  - 正文层：curl_cffi 直连 → Jina → Exa 缓存，Reddit 走 Arctic Shift；
  - 分拣层：Jev。
- **入口**：`scripts/harvest_search.py`。每次运行自动写搜索日志；同一查询不重复搜；见过的链接不重复读。
- **更正上午的 I-03**：Exa 实测能返回 Reddit 帖子（带正文摘要），不是"未证实"。
- **一条教训**：第一次试跑时，Jina 把 Reddit 的 403 拦截页当正文返回，长度超过 400 字，于是 Jev 把真钱实测帖判成"没有证据"。现在所有读取结果都先过拦截页检查。**读对页面比模型更重要。**

## 2. 候选与取舍

星数和最近推送时间取自 GitHub API（09-23）。

| 项目 | 星数 | 最近推送 | 许可证 | 做什么 | 决定 |
|---|---|---|---|---|---|
| Firecrawl | 183.5k | 09-23 | AGPL-3.0 | 抓取服务 | 不选。自建要 Docker Compose，还要 Playwright、Redis、RabbitMQ、PostgreSQL 等一组服务（ss08），本机没有 Docker |
| browser-use | 116.0k | 09-18 | MIT | 让 LLM 操作浏览器 | 不选。每一步都耗 LLM token，我们只需要读页面 |
| TradingAgents / OpenBB / ai-hedge-fund / FinGPT | 108k / 73k / 64k / 21k | 09 月 | 各异 | 交易框架、数据平台 | 不解决"找帖子"的问题，本次不装 |
| Agent-Reach | 84.9k | 09-15 | MIT | 安装器 + 体检 + 路由 | **装了，只用体检**。本机 16 个渠道里 4 个免配置可用；以后接 X 用它的 twitter 渠道（ss01） |
| Crawl4AI | 84.1k | 09-22 | Apache-2.0 | 面向 LLM 的爬虫 | 暂不选。与下面的读取层重叠，要整站爬时再换 |
| Scrapling | 83.0k | 09-23 | BSD-3 | 自适应爬虫，带防检测抓取 | 同上，作为备选 |
| MediaCrawler | 65.6k | 09-19 | 非商业学习许可 | 小红书、抖音、B 站、微博、知乎 | 不选。要扫码登录，许可证限制，主攻短视频平台（ss09） |
| RSSHub | 46.3k | 09-23 | AGPL-3.0 | 把网站变成订阅源 | 以后。确定要长期跟踪的作者后再装 |
| **SearXNG** | 37.5k | 09-22 | AGPL-3.0 | 自建聚合搜索 | **选**（ss02） |
| playwright-mcp | 37.5k | 09-18 | Apache-2.0 | 浏览器 MCP | 不选。camoufox 更不容易被识别 |
| awesome-quant | 29.7k | 09-23 | — | 资源清单 | 作为 GitHub 渠道的搜索起点 |
| **camoufox** | 12.1k | 09-21 | MPL-2.0 | 防检测 Firefox | **选**（ss05） |
| Jina Reader | 12.0k | 05-22 | Apache-2.0 | 读取器（托管端点） | **选**，作为备用读取路径 |
| **curl_cffi** | 6.5k | 09-22 | MIT | 模仿浏览器 TLS 指纹的直连 | **选**（ss10） |
| **Exa MCP** | 5.0k | 09-23 | MIT | Exa 官方 MCP | **选**。直接调它的公共端点，不装 npm（ss03） |
| twikit / twscrape | 4.7k / 2.8k | 03-10 / 09-22 | MIT | X 抓取 | 等机主提供小号 cookie；twscrape 更活跃 |
| **Arctic Shift** | 1.5k | 09-12 | — | Reddit 学术存档 API | **选**（ss04） |
| jev-search | 0.4k | 09-20 | MIT | Jev + Search1API 的搜索应用 | 不装。它要付费的 Search1API 和 Cloudflare Workers；我们在本地复现了它"理解查询 → 多源搜索 → Jev 排序"的做法（ss07） |
| we-mp-rss / wewe-rss、wechat-article-exporter、pysnowball | — | — | — | 公众号、雪球 | 中文渠道已降级，不装。wewe-rss 已归档 |

## 3. 实测（本服务器，09-23）

**找链接**

| 方法 | 结果 |
|---|---|
| Exa 端点（不要 key） | 英文和中文都返回相关结果，包括 Reddit、Substack、雪球、聚宽、果仁、集思录、公众号。知乎收录很少 |
| SearXNG | Google、Brave、Bing、Yahoo、360 有结果；Google、Brave、Yahoo、360 支持 `site:`。DuckDuckGo、百度、夸克、Startpage、Mojeek 要验证码 |
| Arctic Shift | 能按版块全文搜索，有 09-21 的新帖。重查询会返回 422（"Timeout. Maybe slow down a bit"）；脚本会退避重试，再不行就只搜标题 |
| GitHub API | 可用。代码搜索需要免费 token |

**读正文**

| 站点 | 直连（curl_cffi） | Jina | Exa 缓存 | camoufox |
|---|---|---|---|---|
| Reddit | 403 | 拦截页 | 部分 | 未测，改用 Arctic Shift 读全文 |
| Substack、博客 | 可以 | 可以 | 可以 | — |
| 公众号永久链接 | 可以 | 验证码 | 可以 | — |
| 雪球 | WAF 挑战页 | 首页壳 | WAF 页 | **可以** |
| 知乎专栏 | 403 | 验证码 | 抓取失败 | **可以**（站内搜索要登录） |
| 聚宽 | 地区限制 | 地区限制 | **可以（缓存副本）** | — |

**资源占用**：SearXNG 常驻约 90–135 MB；camoufox 读页时合计约 800 MB，所以带浏览器的运行要套 `run_capped.sh --mem 1.8G`；磁盘上工具约 400 MB，浏览器约 1.2 GB。

## 4. Jev 分拣

Jev 是 TypeSafe 的"决策模型"：输入一段文本和几个带类型的问题，返回每个答案的概率，不生成文字。

- 价格：输入每百万 token $0.042，输出免费（ss06）。试跑中 8 篇帖子共约 1.5 万 token，约 $0.0007。
- 每篇结果问 6 个问题：
  - 有没有能回测的具体规则；
  - 证据等级：实盘或前向记录 / 只有回测 / 只有口头宣称 / 没有；
  - 交易哪个市场；
  - 个人能否在美股或 ETF 上只做多执行；
  - 结果是否覆盖 2023 年以后；
  - 有没有可运行的代码。
- 阅读顺序分：规则具体度 × 美股只做多适配度 × 证据权重（实盘 1.0、回测 0.6、宣称 0.3、无 0.1）× 近期加成 × 代码加成。
- **边界**：
  - Jev 的判断只决定先读哪篇；帖子里的数字一律按"作者自报"处理。
  - 方向进入登记簿前，仍要人读原文，并先跑 `oc research directions check`。
  - Jev 推荐英文输入；中文页面的市场分类看起来合理，但准确率没有测。

## 5. 其他个人量化用什么（ss11）

- **英文**：
  - Quantocracy（博客聚合）、SSRN、Quantpedia；
  - Allocate Smartly（持续跟踪已发表的战术资产配置策略）；
  - Substack 研究周报（The Quant Stack、Algomatic Trading 等）；
  - r/algotrading、r/LETFs。
- **中文**：知乎年度合集、聚宽"策略天梯"帖、雪球、公众号、集思录、果仁。已按机主决定降级。
- 英文这些渠道现在除了 X 都能搜到、能读。

## 6. 用法与规则

```
# 装（可重复运行）
scripts/setup_search_tools.sh
# 搜 + 读 + 分拣 + 记录
/opt/oc-search/venv/bin/python scripts/harvest_search.py run --channel exa --query "..."
/opt/oc-search/venv/bin/python scripts/harvest_search.py run --channel reddit --subreddit LETFs --query "..."
/opt/oc-search/venv/bin/python scripts/harvest_search.py run --channel web --site tradingview.com --query "..."
# 读单个链接
/opt/oc-search/venv/bin/python scripts/harvest_search.py fetch URL
```

- 同一渠道、同一查询会被拒绝，除非加 `--force`。
- 排好序的结果写在 `reports/research/harvest/raw/<日期>/`，只留 400 字摘录；全文缓存在仓库外的 `/opt/oc-search/cache`。
- key 只放在 `/root/.config/open-composer/search.env`（权限 600），不进仓库、日志和记忆。
- 抓取守规矩：
  - 遵守 robots.txt（例如 paperswithbacktest 的 `/api/` 不碰）；
  - 低频读取公开页面；
  - Reddit 只走学术存档，不碰 reddit.com；
  - 账号 cookie 只用机主提供的小号。

## 7. 还缺什么

- **X/Twitter**：需要一个小号的 cookie（twscrape 或 Agent-Reach 的 twitter 渠道）。美股一手信息在 X 上很多，这是现在最大的缺口。
- **知乎站内搜索、聚宽全站**：中文渠道已降级，不再追。
