# 情报简报：本机脚本如何读取 Claude Code / Codex CLI 的订阅剩余额度

- 问题：本机脚本怎么拿到 (a) Claude Code（Anthropic 订阅 OAuth，即 `/usage` 显示的东西）和 (b) OpenAI Codex CLI（ChatGPT 订阅，即 `/status` 显示的东西）的真实剩余额度——5 小时窗口 + 每周窗口的 used%/reset time，而不是从 transcript 反推的 token 估算。
- 方法：先本机翻找（rollout jsonl、sqlite、`--help`、已安装二进制的 `strings`/离线 schema 生成），再 WebSearch + 两次 WebFetch 做交叉验证。
- 标注：**本机实测**（我在这台机器上直接读文件/跑离线命令看到的）／**已打开链接**（WebFetch 打开过页面）／**仅搜索摘要**（只看到 WebSearch 摘要，没打开原文）。
- 本机安装版本：`claude` 2.1.273（二进制 `~/.hermes/node/lib/node_modules/@anthropic-ai/claude-code/bin/claude.exe`）；`codex-cli` 0.154.0（真身二进制 `~/.hermes/node/lib/node_modules/@openai/codex/node_modules/@openai/codex-linux-x64/vendor/x86_64-unknown-linux-musl/bin/codex`，`bin/codex.js` 只是选平台包的 launcher）。
- **本机范围警告**：这台机器上 Codex 的 `~/.codex/auth.json.auth_mode = "apikey"`（不是 ChatGPT 订阅 OAuth），且 `logs_2.sqlite` 显示模型请求实际打到 `127.0.0.1:3002`（自建代理，转发到 OpenRouter/Cerebras 等第三方模型），不是走 `chatgpt.com` 后端——所以下面 Codex 的所有"订阅额度"机制在**这台机器现在**都拿不到真实数字（字段全是 `null`），但机制本身在真用 ChatGPT 登录时是成立的。Claude Code 这边则确认是真订阅 OAuth（`auth_type: "oauth"`, `token_source: "CLAUDE_CODE_OAUTH_TOKEN"`，本机曾真实触发过 429），所以 Claude 的结论对这台机器当下就适用。

## 1. 本机实测：Codex CLI

- `~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl`（321 个文件，最新 `2026-09-16T02-33-01-...jsonl`，最后一条 `token_count` 事件时间戳 `2026-09-17T08:55:23.500Z`）：每条 `token_count` 事件都带一个 `rate_limits` 对象，形如：
  ```json
  {"limit_id":"codex","limit_name":null,"primary":null,"secondary":null,"credits":null,
   "individual_limit":null,"spend_control_reached":null,"plan_type":null,"rate_limit_reached_type":null}
  ```
  三种历史 schema（字段逐渐增加，见 `individual_limit`/`spend_control_reached` 何时出现），但 321 个文件里 `primary`/`secondary` **从未**非 null——本机实测原因就是 `auth_mode=apikey`。搜索未发现 `used_percent`/`window_minutes`/`resets_in_seconds` 这三个字面 key（唯一命中是测试代码里用 `window_minutes` 做因子参数名的假阳性）。
  - 仅搜索摘要（GitHub `xiangz19/codex-ratelimit`、`Ganymede404/vscode-codex-usage` 相关 issue 的摘要）：在 ChatGPT 订阅账号上，这个 `rate_limits` 会被填成 `{"primary":{"used_percent":.., "window_minutes":300,"resets_in_seconds":..},"secondary":{...,"window_minutes":10080,...}}`——即 snake_case、`primary`=5h、`secondary`=周。本机没能拿到实例验证这个具体形状，只能确认字段名和本机 app-server v2 协议（见下）不完全一致，存在版本漂移。
- `~/.codex/logs_2.sqlite`（`logs` 表，3.4 万行）：`LIKE '%rate_limit%'` 命中 5 条，全部是无关的 shell 命令文本（用户在聊 Cerebras 的 rate limit 文档），不是 Codex 自身的额度事件；无专门的 rate-limit 表。`~/.codex/log/codex-login.log` 只有登录记录。
- `codex --help`：没有 `usage`/`status`/`quota` 子命令。`codex doctor --json` 存在但可能触发认证检查的网络请求，未执行。
- **关键突破**：`codex app-server generate-json-schema --out <dir> --experimental` 是纯离线的 schema 导出（不发任何网络请求），本机实测跑出了完整定义：
  - JSON-RPC 方法 `account/rateLimits/read` → `GetAccountRateLimitsResponse`：`rateLimits.primary` / `.secondary` 都是 `RateLimitWindow{usedPercent:int(必填), resetsAt:int64|null(epoch秒), windowDurationMins:int64|null}`；外层还有 `planType`、`limitId`、`credits(CreditsSnapshot{hasCredits,unlimited,balance})`、`rateLimitReachedType`、`spendControlReached`、`individualLimit(SpendControlLimitSnapshot{limit,remainingPercent,resetsAt,used})`、`rateLimitResetCredits`、多桶视图 `rateLimitsByLimitId`。
  - 推送通知 `account/rateLimits/updated`（`AccountRateLimitsUpdatedNotification`，字段说明写的是 "Sparse rolling rate-limit update...merge into the most recent account/rateLimits/read response"）——这是 `codex app-server`/`codex agents` 连的那个共享本地 daemon 会主动推的事件。
  - 本机没有已运行的 app-server daemon（`ps aux` 未见进程，`~/.codex` 下无 `.sock`/`daemon.lock` 文件），要用这条路必须自己起一个（`codex app-server --listen unix://...` 或 `codex debug app-server send-message-v2`），它会用 `~/.codex/auth.json` 里的凭据去发一次真实的、经过 codex 自己处理的认证请求——脚本本身不摸凭据文件，但确实会产生一次到 OpenAI 后端的网络调用。
  - 二进制 `strings` 定位到的 REST 端点（`chatgpt_base_url = "https://chatgpt.com/backend-api/"`）：`/api/codex/usage`、`/api/codex/usage/thread-estimates/query`、`/api/codex/usage/thread_usage/query`、`/api/codex/rate-limit-reset-credits`——这些应是 app-server 底层实际调用的 REST 面，`account/rateLimits/read` 很可能就是对其中之一的封装。

## 2. 本机实测：Claude Code

- `~/.claude/projects/*/*.jsonl` 里 `quotaLimits` 命中 41 条（3 个项目目录），**全部** `status:"rejected"`（从未见过 `allowed`/`allowed_warning`，`rateLimitType` 也只见过 `"five_hour"`，没见过 `seven_day`）。最新一条真实记录（排除本次会话自身）时间戳 `2026-09-18T08:19:17.850Z`，够新。完整记录形状（在一条 `type:"assistant"` 的合成消息里，与 `message` 同级）：
  ```json
  "quotaLimits": {"status":"rejected","resetsAt":1788329400,
    "unifiedRateLimitFallbackAvailable":false,"rateLimitType":"five_hour",
    "overageStatus":"rejected","overageDisabledReason":"out_of_credits",
    "upgradePaths":["upgrade_plan"],"isUsingOverage":false}
  ```
  它只在真的打到 429 那一刻出现，不是持续可读的百分比仪表——**不能**当日常轮询源。
- 每条真实 assistant 消息的 `message.usage`（`input_tokens`/`output_tokens`/`cache_read_input_tokens`/…）和会话末尾的 `modelUsage`（按模型汇总 `inputTokens/outputTokens/costUSD`）都在本机被找到——这是 token 估算兜底路线的原始数据源，Claude Code 自己已经算好了 `costUSD`，不用重新建模型价格表。
- `~/.claude/policy-limits.json` 是合规/权限限制（`enforce_web_search_mcp_isolation` 之类），跟额度无关，不要被名字骗了。
- `~/.claude/telemetry/1p_failed_events.*.json`（3 个失败上报文件）里的 `tengu_policy_limits_fetch` 事件解码出 `auth_type:"oauth", token_source:"CLAUDE_CODE_OAUTH_TOKEN"`，确认本机是真订阅登录；`tengu_api_success` 的 `additional_metadata` 只有 `messageTokens/costUSD/model/requestId`，没有百分比字段——同样只支持"估算"路线。
- `claude --help`：无 `usage`/`quota` 子命令；`claude auth status --json` 存在，但大概率会做一次真实的凭据校验网络请求，按任务要求未执行。
- **关键突破**：对已安装二进制 `claude.exe` 跑 `strings`（纯离线，不联网）挖到：
  - 字面量 `/api/oauth/usage`、`/api/oauth/usage?at_wall=1&skip_spend=1`、`/api/oauth/usage?cedar_ember=1&skip_spend=1`。
  - 反混淆出计算逻辑：`percentUsed = utilization * 100`，`resetsAt = new Date(resets_at*1000).toISOString()`，对 `five_hour`/`seven_day`/`overage`（spend_limit）三块分别算。
  - 相邻字符串注释："The plan's usage rows...from the claude.ai usage endpoint; null when the CLI could not fetch them (no plan on this lane, or a token without the profile scope)."——即需要 OAuth token 带 `profile` scope。
  - 凭据落地文件：`~/.claude/.credentials.json`（只确认该文件是凭据载体，未读取/未展示其内容）。

## 3. 网络印证

| 端点/工具 | 校验 |
|---|---|
| `GET https://api.anthropic.com/api/oauth/usage`，头 `Authorization: Bearer <token>` + `anthropic-beta: oauth-2025-04-20` + `User-Agent: claude-code/<ver>` | **已打开链接**（`Maciek-roboblog/Claude-Code-Usage-Monitor` issue #202）：响应含 `five_hour`/`seven_day`/`seven_day_opus`/`seven_day_sonnet`（各 `{utilization, resets_at}`）+ `extra_usage`(超额)。明确写"undocumented and reverse-engineered"；安全轮询间隔 180s，无 UA 会被专门限流打 429（本机 strings 结果与此完全吻合）。同名端点在 `anthropics/claude-code` issue #30930/#31021 里也被独立报过 429 问题，佐证其真实存在。 |
| `GET https://chatgpt.com/backend-api/wham/usage`，用 `~/.codex/auth.json` 的 access token | **已打开链接**（`openai/codex` issue #10869）：TUI 里 `ChatWidget::prefetch_rate_limits` 起一个 60s 轮询器调 `fetch_rate_limits`，即使当前 profile 不需要 ChatGPT 认证也会打——本机看到的却是全 null，说明本机这个版本/配置路径已经不触发它，或已经切到 `/api/codex/usage`（本机 strings 命中的新端点，路径不同、issue 未提及，怀疑是后续版本替换了 `wham` 前缀）。未见该端点被官方文档化。 |
| ccusage / Claude-Code-Usage-Monitor（`claude-monitor`）/ 其同类 Codex 工具（`openusage`、`xiangz19/codex-ratelimit`） | 仅搜索摘要：主流工具（ccusage、claude-monitor）默认只解析本地 JSONL 算 token/成本估算，**不**默认打真实额度端点；只有少数项目（`openusage`、Claude-Code-Usage-Monitor 的 issue #202 讨论的补丁）主张直接调上面两个端点拿"cross-device 权威"数字。 |
| Anthropic 官方 Usage & Cost API（Admin API 的一部分） | 仅搜索摘要（`platform.claude.com/docs`）：官方**确有**文档化的 usage/cost 接口，但要求组织级 `sk-ant-admin-...` key，服务的是企业账单场景，**不支持** OAuth/个人 Pro-Max 订阅 token，回答不了"我这个人还剩多少 5 小时额度"这个问题。 |
| OpenAI 官方 `developers.openai.com/api/docs/guides/rate-limits` | 仅搜索摘要：只覆盖按量计费 API key 的速率限制，不覆盖 ChatGPT 订阅下 Codex CLI 的 5h/周窗口。 |

## 4. 结论表

| 机制 | 给出什么 | 怎么读 | 新鲜度/时延 | 可靠性风险 |
|---|---|---|---|---|
| Claude `GET api.anthropic.com/api/oauth/usage` | 5h/周(含 opus/sonnet 分桶)% + reset 时间，权威、跨设备一致 | 脚本自己拿 `~/.claude/.credentials.json` 里的 OAuth access token 发请求，带 UA+beta 头 | 实时，官方建议 ≥180s 轮询 | 未文档化，端点/字段可能随版本无预警改动；无正确 UA 会被强限流；仍需自行处理 token 刷新 |
| Claude `quotaLimits`（transcript 内） | 429 那一刻的 `status/resetsAt/rateLimitType` | `grep` 本地 jsonl | 只在触发限流时出现，非持续 | 覆盖面窄（只见过 five_hour，没见过 allowed 状态） |
| Claude `usage`/`modelUsage`（transcript 内） | 每次调用/每会话 token 数与 `costUSD` | 累加本地 jsonl | 每条消息落盘，接近实时 | 只是"花了多少"的估算，不是官方限流分母，换算成百分比会有偏差 |
| Codex `account/rateLimits/read`（app-server JSON-RPC） | `primary/secondary`（`usedPercent`必填/`resetsAt`/`windowDurationMins`）+ credits/plan | 起 `codex app-server` 或 `codex debug app-server send-message-v2` 发 RPC | 实时（daemon 自己按需/定时拉） | 需要真 ChatGPT 订阅登录（本机是 apikey，拿不到）；协议标"experimental"；字段名比 rollout jsonl 的 snake_case 版本新（camelCase），版本漂移 |
| Codex `GET chatgpt.com/backend-api/{wham,codex}/usage` | 同上原始数据源 | 直接调（用 `~/.codex/auth.json` 的 token） | 官方轮询间隔约 60s | 未文档化；端点名在版本间变过（wham→codex），随时可能再变 |
| Codex rollout jsonl `token_count.rate_limits` | 理论上 `primary/secondary.used_percent/window_minutes/resets_in_seconds` | tail 最新 rollout 文件 grep `rate_limits` | 每个回合写一条，但本机全为 null | 只有真用 ChatGPT 订阅登录时才非空；本机验证不了具体形状，字段名与 app-server 协议不一致（版本漂移） |
| 两者的"估算"兜底（累加本地 token/成本） | 用量趋势、大致烧钱速度 | ccusage/claude-monitor 或自己写累加脚本 | 与本地写盘同频，接近实时 | **不是**官方限流分母（限流可能按加权 token、模型档位、并发数计算），长期会跟官方 % 漂移 |

## 5. 推荐

- **Claude Code**：首选直接调 `GET https://api.anthropic.com/api/oauth/usage`（Bearer token 取自 `~/.claude/.credentials.json`，必须带 `anthropic-beta: oauth-2025-04-20` 与 `User-Agent: claude-code/<version>`，缓存 TTL ≥180s）——本机 strings 复现的计算逻辑（`percentUsed=utilization*100`）说明这就是 `/usage` 面板背后的真实数据源。兜底：本地 jsonl 里的 `usage`/`modelUsage` 累加估算，外加把 `quotaLimits`（429 时刻）当"至少已经打满"的强信号。
- **Codex CLI**：首选 `codex app-server`/`codex debug app-server send-message-v2` 调 `account/rateLimits/read`（离线用 `codex app-server generate-json-schema` 就能拿到权威字段定义，不用联网即可对齐 schema）——但**必须**是真 ChatGPT 订阅登录（`auth_mode` 不是 `apikey`）才有值；本机当前拿不到。兜底一：直接仿造 `GET chatgpt.com/backend-api/codex/usage`（用 `~/.codex/auth.json` 的 token），风险是端点名已知会变。兜底二：tail 最新 `~/.codex/sessions/**/rollout-*.jsonl` 的 `token_count.rate_limits`，在真订阅账号上应该能看到 `primary/secondary.used_percent/window_minutes/resets_in_seconds`（本机验证不了，仅搜索摘要）。兜底三（纯估算）：累加 `total_token_usage`/`last_token_usage` 字段。
