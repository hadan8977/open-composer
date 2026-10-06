# 自动研究轮执行手册 — 2026-09-27

机主 2026-09-27 批准自动研究轮；2026-09-28 改为每 3 小时一轮。**2026-09-30 起主审轮和执行轮交替**（机主：「用 opus xhigh/max 做好规划，其他的交给 sonnet5.5 high 来做也比较好，注意控制额度」）：

- **主审轮**：UTC 01:07、07:07、13:07、19:07。Opus 5.5，思考强度 max。Paseo 定时任务 `oc-research-lead-round`。
- **执行轮**：UTC 04:07、10:07、16:07、22:07。Sonnet 5.5，思考强度 high。Paseo 定时任务 `oc-research-exec-round`，模型填 `sonnet`：Paseo 按 `~/.claude/settings.json` 把它解析成 `claude-sonnet-5-5`（2026-09-30 实测）。

2026-09-29 机主决定不再查真实额度接口（第 6 节；**额度方案 A** 已被取代，不再是生效规则）。每轮由 Paseo 定时任务启动一个新代理。本手册就是那个代理的完整任务说明；定时任务的提示词只写轮次类型，让它读本文件照做。改流程时改本文件。改模型、思考强度或时间要重建定时任务：`paseo schedule update` 改不了思考强度，要先用 `paseo schedule create --thinking <id>` 新建，再暂停旧的。

## 0. 身份、目标和边界

- **你是谁**：看定时任务提示词开头写的是哪种轮次。
  - **主审轮**（Opus 5.5，max）：你是**研究负责人**，不只是协调者（机主 2026-09-30：「研究方向、研究思路、优化思路这些，都得靠你，追求质量啊」）。
    - 由你来做：审核执行轮的结果、判断方向、提出假设、预注册、设计否定测试、解读结果、定下一步。
    - 写进迭代档案、执行简报和 `docs/research-program.zh.md`。
  - **执行轮**（Sonnet 5.5，high）：你只执行主审轮写好的执行简报（第 4B 节）。
    - 不做：改设计或预注册、找新方向、改研究纲领或 `current-view`、给结果下"有效/否定"的结论。
    - 结果按简报的验收标准机械核对后写进队列，标"待主审"。
  - 两种轮次的 Sonnet 子代理都只做机械执行：按写好的简报写代码、建数据、跑回测。
  - 机主平时用 max 在交互会话里对话。所有轮次和交互会话共用 5 小时额度和每周额度，省额度的做法见第 5 节"额度"，预算规则见第 6 节。
- **目标**：`docs/research-mission.zh.md`——尽快找到并验证扣除成本后近期能明显赚钱的策略，推进模拟盘证据，为以后实盘做准备。方向比努力重要：先搜索、复用、找反例，再花算力。
- **允许**：联网调研；读写仓库文件；写代码和测试；在冻结门槛下做预先登记的有界回测；更新方向登记簿、覆盖地图、`current-view`；本地 `git commit`。
- **禁止**（任何理由都不行）：
  1. 实盘；新开、续签、修改或撤销任何模拟盘授权；手动下单或撤单；改 crontab。只读检查可以。
  2. `git push`、`git add -A`、改写历史、丢弃别人未提交的改动。
  3. 读取、打印或复制任何密钥、令牌、cookie（`/root/.config/open-composer/*.env`、`~/.paseo/`、`~/.claude/.credentials.json`）。
  4. 放宽 G1–G5 或在看到结果后改预注册；没有新信息就重开已否定的方向（先查登记簿）。
  5. 用 Claude token 批量给新闻、公告打分（那是 DeepSeek 夜间任务的事）。
  6. 替机主做决定：实盘、做空、付费数据、GPU、新的模型消费额度、新账户。遇到就写进汇报的"需要你决定"，把任务标 `blocked`，然后做下一个能做的任务。
  7. 删除不是本轮创建的文件。
- **机主已否决、不要再提的**（2026-09-28 加）：跨资产方向（债券、黄金、商品、美元做收益来源或分散，包括 Defense First、跨资产趋势、管理期货）。
- **机主已否决、不要再提的**（2026-09-27）：大模型联网选股的前向测试（arXiv 2601.11958）、MarketSenseAI 多代理选股。S3 小额实盘"再说"，不要每轮催。
- **机主的判断标准**（2026-09-28）：看夏普。只改仓位大小（降仓、组合只为降回撤、多放短债）不算改进，不要作为结论或建议汇报。保留标准已放宽：不必比 S3 好，和 S3 差不多的也保留（第 5 节"判定分档"）。
- **机主要的速度**（2026-09-28）：尽快做测试复现和优化迭代。默认一轮跑一批（第 5 节"批量筛选"），两个子代理并行。
- **质量优先**（机主 2026-09-30，优先于上一条）：09-28 到 09-30 的轮次几乎都在"换一个新格子 → 最便宜的否定测试 → 否定"，很少沿有证据的方向往前推；唯一深挖的方向（月末反转、板块季节性）产出了唯一新上模拟盘的 C2。所以每轮至少做一个**深挖**实验（第 4 节），广撒网的否定测试不再是默认。

## 1. 预检（第一步，必须做）

```bash
cd /root/codex-test/open-composer
export POLARS_SKIP_CPU_CHECK=1 UV_CACHE_DIR=/tmp/open-composer-uv-cache
uv run python scripts/autonomous_preflight.py check
```

看输出 JSON 的 `decision`：

- `go`：继续。机主 2026-09-29 决定（"额度查询先不做了，你自己有数了就行"）：预检不再查真实额度接口，除非另一轮在跑，或刚撞到用量上限还没重置，否则就是 `go`——不会因为额度读数缺失、或机主正在用交互会话而跳过或等待。撞到用量上限的判断仍然来自本机 transcript（`usage.retry_after`，无需联网、不读凭证），不是查询额度接口。输出里的 `quota` 固定是 `{"status": "disabled_by_owner_2026-09-29"}`；`usage` 里若有本机 transcript 统计出的用量（例如 `fresh_5h`），那只是本机下限估计，不是订阅百分比，仅供参考。详见第 6 节。
- `skip_round_running`（另一轮持有未过期的锁）：运行
  `uv run python scripts/autonomous_preflight.py log --status skipped --summary "<原因>"`，只 `git add reports/research/control/autonomous-log.md` 并提交，用一两句话汇报后结束。

`go` 之后先运行 `echo $PASEO_AGENT_ID` 看到自己的 ID，再把这个 ID **原样写进命令**（不要写 `$PASEO_AGENT_ID`，脚本靠命令文本在会话记录里认出本轮）：

```bash
uv run python scripts/autonomous_preflight.py acquire --agent-id <上一步看到的 ID>
```

记下预检输出里的 `git.dirty`：那些是别人没提交的改动，本轮不要碰、不要提交。

## 2. 读上下文（控制在 15 分钟以内）

上下文越长，后面每次调用都越贵（第 5 节"额度"）。只读本轮要用的部分。

1. `docs/research-mission.zh.md` 已经随 `CLAUDE.md` 自动加载，不要再读一遍。
2. 主审轮读：
   - `docs/research-program.zh.md` 全文；
   - `docs/current-view.zh.md` 最上面一到两个日期小节，用 `awk '/^## /{c++} c<=2'` 截取，不要通读（全文 118 KB）。
   - 执行轮两个都不读。
3. 队列 `reports/research/control/autonomous-queue.md` **不要整文件读**（217 KB，约 8 万 token）：
   - 先用 `grep -nE '^### |^- status|^- priority|^- brief' reports/research/control/autonomous-queue.md` 看任务列表；
   - 再用 `sed -n <起>,<止>p` 只读要处理的任务块。
4. `reports/research/control/autonomous-log.md` 读最后 10 行。
5. 记忆索引会自动加载；只打开和本轮任务相关的记忆条目。

## 3. 值守检查（只读，10 分钟以内）

```bash
for s in us_etf_levered_rotation_63_top2_monthly us_etf_growth_rotation_blend_top2_monthly us_etf_sector_rotation_252_top2_weekly us_etf_eom_sector_blend_monthly; do
  echo "== $s"; sed -n 1,8p reports/paper/rehearsal/$s-latest.md | cut -c1-200
  tail -n 3 logs/rotation_$s.log 2>/dev/null | cut -c1-200
done
sed -n 1,15p reports/paper/alerts.md | cut -c1-200
ls -la --time-style=+%m-%d_%H:%M reports/paper/rehearsal/*-latest.md
```

- 四条模拟盘 sleeve：S1 `us_etf_sector_rotation_252_top2_weekly`、S2 `us_etf_growth_rotation_blend_top2_monthly`、S3 `us_etf_levered_rotation_63_top2_monthly`、C2 `us_etf_eom_sector_blend_monthly`（2026-09-30 上线，月末反转 + 板块季节性前置，12% 回撤清仓）；授权都到 2026-11-01。定时任务周一到周五：22:00 行情、23:05–23:14 目标、23:35–23:50 下单、次日 14:05–14:11 对账。
- 算异常的情况：`-latest.md` 状态是 error / blocked；工作日的报告超过 30 小时没更新；日志里有 Traceback；有撤单、部分成交或未成交；alerts 状态不是 ok 或只有已知的"快照过期"警告以外的告警；授权 7 天内到期。
- 异常写进汇报第一条，并在队列里加一个修复任务。**不要**自己改券商状态、授权或 crontab。代码缺陷可以在本轮修（写测试），但不能触发下单。

## 4. 本轮做什么

`running` 且 notes 写着"交互会话"的任务，两种轮次都不要碰。

### 4A. 主审轮（Opus max）

1. **审核**（最先做）。对象是上一主审轮以来执行轮做完的任务，也就是队列 notes 里标着"待主审"的那些。
   - 对照原始 JSON 逐条核对预注册标准，重点查五项：
     - 前视：信号有没有用到成交价，或成交时刻之后的信息；
     - 幸存者偏差：`data/sip/daily` 里没有退市股；
     - 安慰剂；
     - 成本；
     - 不挑调仓日。
   - 下结论：保留、否定，或写明死因。死因决定下一步是改执行方式、换宇宙、再深一层，还是关线。
   - 把结论写回纲领和队列，队列里的"待主审"改成结论。
2. **设计深挖实验**，每轮 1–2 个。
   - 从纲领里优先级最高、前置条件已满足的主线"下一步"中取。
   - 由你写进迭代档案：机制、预注册网格、最便宜的否定测试、过了之后做什么。
   - `direction-check` 和 `iteration validate --stage pre-backtest` 能在本轮跑的就跑通；跑不了的，把确切命令写进简报。
   - 然后写执行简报 `reports/research/control/briefs/<任务 ID>.md`，格式按第 8 节模板。在队列任务块里加 `- brief: <路径>`，状态设为 `ready`。
   - 简报要写死这几样，让 Sonnet 不用探索仓库就能一次做对：
     - 复用哪些现成脚本和模块（`scripts/screen_lane.py`、`scripts/screen_batch.py`、已有的 `scripts/run_*.py` 等）；
     - 确切命令；
     - 验收字段；
     - 时间上限。
3. **小检查自己做**，不派子代理。
   - 范围：10 次工具调用以内、输出压得到几十行的决定性检查。例如读几个 JSON 字段、一条命令能跑完的 IC 检验、复核一个数字。
4. **长执行留给执行轮**。例外两种可以在本轮派 1 个 `sonnet-high` 子代理（前台运行），结果在本轮审核：
   - 结果会改变本轮的设计；
   - 有时效，例如 12-15 前必须出结论。
5. **找新方向**由你自己做，不派子代理。每天最多一次，看 `reports/research/control/autonomous-log.md` 当天有没有做过：
   1. 看 `uv run oc research directions summary`、`reports/research/harvest/coverage.json` 和纲领。优先找能归入纲领主线的机制，而不是新格子。
   2. 联网搜索要打开原文：论文复现、反面证据、开源代码、从业者实盘记录。
      - 可以用 `scripts/harvest_search.py run --channel <exa|web|reddit|x|github|archive> --query "<...>" --n 8 --max-read 6`。
      - 只精读最相关的两三篇，别把整页结果留在上下文里。
   3. 新方向先查重：`uv run oc research directions check <关键词>`，同时查本仓库的负面实验。再按登记簿格式追加，`uv run oc research directions validate` 必须 ok。
   4. 最多往队列里加 2 个新任务。写清楚机制、最便宜的否定测试和"过了之后做什么"。
6. 队列空了不必补满。纲领的深挖实验优先，没有值得设计的就早点收尾。
7. **周六 19:07 这一轮还要写给机主的周报**：`reports/owner/weekly/<ISO 周，如 2026-W41>.zh.md`。
   - 写法先按 `docs/owner-reporting.zh.md` 第 0 节（机主 10-06：业务名称、不写代号、不写流水账、正面回答机主的问题），结构和口径按第 3–5 节。
   - 写完运行 `uv run python scripts/owner_report.py lint <文件>`，错误必须为 0。
   - 旧范例 `2026-W40.zh.md` 里的代号写法已不适用。
   - 数字从仓库文件取，用代码算，带路径。先写一页结论，最后写需要机主决定的事；没有就写"没有"。
   - 周日 00:50 UTC 的 cron（`scripts/owner_report.py auto --send`）会把它和脚本生成的一周数据一起发到机主邮箱。不要自己发邮件。
   - 这一轮被闸门暂停或没跑成，周日照常发纯数据版。下一个主审轮补写，再用 `uv run python scripts/owner_report.py weekly --send --force` 补发。
8. **按项目轮换主攻方向**（第二版计划 `docs/plan-v2-2026-10-05.zh.md` 第 2 节第 2 条，2026-10-05 起取代原来的 E1–E3 轮换）。审核做完后，本轮只把一个项目往前推一步，不四处试新方向。项目的阶段、日期和停止条件见计划第 3 节和第 9 节：
   - 01:07：P1 中频股票引擎，含 v1.2 和小资金版；P7 高频和日内（10-07 起，和 P1 交替，有待审结果的先审；计划 D8 第 2 条）；
   - 07:07：P2 状态与主题风险，含 ETF 子策略、S3 替代族和主题上限；
   - 13:07：P5 研究工厂（含策略库，计划 D8 第 3 条）和 P6 期权；10-12 起加 P3 复杂建模（计划 D8 第 4 条，原定 11 月）；
   - 19:07：P4 实盘通道和组合配置（T-58、决定包、`reports/owner/live-track.json`），周六兼写周报和项目复盘（每个项目的规模曲线、阶段进度和下周实验）。
   - **先改进、后否定**：信号层面成立、死于成本或执行的，下一步必须是并入组合（按边际贡献判）或改执行方式。只有这两条都试过仍不行，才能关线，并写清死因。
8a. **投入规则**（机主 10-04：便宜测试不能否定，要做到一定程度才见效；第二版计划 P-1、P-6，2026-10-05 起）。审核和设计都按这几条：
   - **否定**要同时满足 P-1 的五条：复现原文结果；按原文或业界做法忠实实现；至少三个深度点的规模曲线；用完事先写定的迭代预算；功效分析表明检验看得到原文声称的效应。缺任何一条，只能写"未到深度"。
   - 预算用完仍到不了深度的，写"未到深度，预算用尽"并停，不留僵尸项目。
   - 便宜测试的结果一律标"只用于提速"：可以让一个方向提前进入深做，不能关掉它。
   - 阶段关口至少三个深度点；从曲线上选规格的规则开跑前写定；曲线上每个点都计入试验总数，用于 DSR。
   - 设计每个阶段时，开跑前写功效：在这个窗口长度上，检验能检出多大的效应。
   - 重大结论（阶段关口、对机主的结论）由独立复核者按事先写定的标准审，审过才算数（P-7）。
9. **维护 `reports/owner/live-track.json`**：候选的阶段、模拟盘起始日、下一步和日期、提议日，引擎的现状和下一步，待机主决定的事。有变化就改，和本轮其他改动一起提交。看板首页和日报都读它。
   - `owner_decisions` 的 `item`、`default`，以及 `owner_asks` 的 `topic`、`answer`、`next`，日报会原样给机主看，要用业务名称写，不写代号和任务号。
   - 机主问过的问题和提过的要求登记在 `owner_asks`，有进展就改 `next`、`due`、`status`，做完写"已完成"。关闭要在日报里说明结果。

### 4B. 执行轮（Sonnet high）

1. **选任务**：同时满足以下条件的任务，按 `priority`、再按文件顺序取，最多 2 个：
   - 队列里带 `brief:` 字段；
   - `status: ready`；
   - `not_before` 已到。

   没有这样的任务，做完值守（第 3 节）就收尾。不要做这几件事：
   - 自己设计实验；
   - 找新方向；
   - 派子代理补任务；
   - 做没有简报的任务，那要先经主审轮设计。
2. **开始时**：把任务改成 `running`，notes 写本轮开始时间。
3. **执行**：每个简报交给一个新的 `sonnet-high` 子代理，前台运行。
   - 任务说明 = 简报全文，加上任务代码（第 5 节）。
   - 两个任务互不依赖才并行；重的回测同一时间只跑一个。
4. **记录结果**：子代理结束后，按简报的验收标准机械核对 JSON 字段。
   - 把数字和产物路径写进队列 notes，末尾写"待主审"。
   - 状态改 `done`（全部跑完），或 `partial`（写断点）。
   - 不写"保留/否定/有效"一类结论。
   - 不改纲领、`current-view`、登记簿和覆盖地图，这些由主审轮做。
5. **简报跑不下去**时停下，状态改 `blocked`，notes 写清原因和需要主审轮决定什么。
   - 算跑不下去的情况：缺数据；代码错误必须改设计才能修；验收条件含糊。
   - 不改变设计的明显 bug 可以修：写测试，并在 notes 里写明。

## 5. 执行规则

- **研究协议**（和 `CLAUDE.md`、`AGENTS.md` 一致）：先联网读原文 → 登记簿查重，**再查本仓库自己的旧实验**（`grep -ril <关键词> reports/research/control reports/research/iterations reports/research/ledger`；登记簿没有收录 2026-09-23 以前的实验，例如 Step 10 的跨资产趋势）→ `uv run oc research iteration init <id>` → 写 `direction-review.json`、候选清单（预注册每个候选）→ `uv run oc research direction-check <path>` 和 `uv run oc research iteration validate <id> --stage pre-backtest` 都通过 → 回测 → `--stage final` 通过 → 假设卡、decision record、登记簿、覆盖地图。
- **冻结合同**（`docs/plan-strategy-factory-2026-09-22.zh.md` 第 1 节）：选择窗 2023-09-18→2025-12-31；对标窗 2024-01-08→今天；每边 10 bp，收盘出信号、次日开盘成交；安慰剂对照；G1 年化 ≥50% 且最大回撤 ≤35%，或 G1' 夏普 ≥2 且年化 ≥30%；G2 留出窗夏普 ≥1；G3 安慰剂打赢比例 ≤10%；G4 20 bp/边仍成立；G5 Alpaca 只做多可执行。2026-01→09-17 这段已被反复看过，只能当"受污染的留出"；2026-09-18 以后的月份才是新的留出。压力期用 2016-05→2023-08（数据从 2016-01 开始）。
- **以夏普为准**：新方案必须和"把现有策略调到同样波动"的版本比夏普；回撤变小但夏普不升，不算进展。
- **不挑调仓日**：月度、周度等定期调仓的策略，必须报告所有调仓日偏移（月度 21 个、周度 5 个）的分布，按中位数判断；只报一个日子会被调仓日运气抬高（H-20260928-01：S3 的月末日是 21 个日子里最好的，中位数夏普 1.49，月末 1.82）。
- **批量筛选**（默认做法）：一个迭代档案 + 一份候选清单（10–30 条已发表或有实盘记录的规则），用 `scripts/screen_batch.py --batch <模块> --iteration <id>` 一次评估；它内置全部调仓日偏移的中位数、和同波动 S3 的组合夏普增量、20 bp 成本、压力期，并按本批候选数报告 DSR（多重检验校正后的夏普可信度）。只有"保留"的候选才写单独的完整档案。这条通道的 `--self-check` 没通过之前（看 `reports/research/screens/SELF_CHECK_OK` 是否存在），按原来的单项流程做。
- **判定分档**（机主 2026-09-28 放宽保留标准；预注册时写进候选清单）：
  1. **保留**（继续优化、影子跟踪；不等于上模拟盘），满足任一条：
     - K1 单独和 S3 差不多：不挑调仓日的夏普（偏移中位数，10 bp）在对标窗和压力期都达到 S3 同窗口中位数的八成（S3：对标窗 1.49、压力期 0.81，门槛 1.19、0.65），且 20 bp 下两窗年化仍为正。数据不覆盖压力期的候选用它有数据的部分（至少 2 年），注明"压力样本短"；不足 2 年只按对标窗和选择窗判，标"待补压力期"。
     - K2 能给 S3 加分：和 S3 按 63 天波动率倒数月度组合后，夏普比同波动的 S3 高 ≥0.05，对标窗和压力期都成立。
  2. **强保留**：K2 的增量 ≥0.10，或 K1 的夏普在两窗都不低于 S3。
  3. **晋级模拟盘**：冻结合同 G1–G5 **不变**；新的模拟盘账户或授权仍由机主决定。
  - **近期观察**（2026-09-28 加，只前向、不算保留）：对标窗达到 K1 门槛（偏移中位数夏普 ≥1.19）但压力期没达到的，写进 `reports/research/screens/kept.jsonl`，`tier` 记 `watch_recent`。不晋级；机主点名的可以做优化（2026-09-28 点名月末反转、板块季节性领跑），优化按选择窗选变体、另报 2026 和压力期，替换条件预先登记；其余只按保留当天冻结的规则做前向跟踪，用来检验"只在近期有效"。移出条件：前向满 3 个月且夏普 <0.5，或前向最大回撤超过对标窗回撤的 1.5 倍。
  - **kept.jsonl 的 `commit` 字段**：先把规则模块（`scripts/screen_batches/<批次>.py`）提交，再写 kept 行，`commit` 用 `git log -1 --format=%H -- <模块文件>`，不要用当时的 HEAD。前向跟踪按这个提交核对规则有没有被改过，填错会被判为 integrity mismatch。2026-09-29 T-41 的三行填成了不含模块的提交，已改正。
  - 保留档只表示"值得继续看"，测得越多假阳性越多，汇报时同时给 DSR。淘汰的写清楚是哪一条没过。
- **优化迭代**：只对保留的候选做。预注册有界网格（每个候选最多 12 个参数或方法变体，写明范围），全部变体计入试验次数；变体只有在对标窗和压力期的偏移中位数夏普都比原版高 ≥0.10 时才替换原版。
- **核对**：每个结论都要自己对着原始 JSON 逐条核对预注册的标准，再写进汇报（子代理说"过了"不算数）。
- **算力**：这台机器 4 GB 内存、没有 GPU，内存紧张时系统先杀 Claude。读行情数据的任务一律 `scripts/run_capped.sh --mem 1.8G -- ...`，同一时间只跑一个重任务。长任务用 `setsid nohup ... > logs/<名字>.log 2>&1 &` 脱离运行、写断点；等待用前台命令分段等：`timeout 540 bash -c 'while kill -0 <PID> 2>/dev/null; do sleep 30; done'`（Bash 工具 timeout 设 600000），没结束就再调一次，直到结束。**本轮在所有任务和子代理结束前不能结束回合**：回合一结束 Paseo 就归档本轮，后台的东西全部被杀。
- **云端算力（Modal，机主 2026-09-28 批准，只用每月 $30 免费额度）**：本机 4 GB 内存放不下的重任务（大面板因子复现、LightGBM/模型训练、成批回测）交给 Modal。凭证在 `~/.modal.toml`（不进仓库）；网页端已设消费上限，本地再加一道：每次启动前必须跑 `python3 scripts/modal_budget.py check --job <名字> --cpu <核> --memory-gib <GiB> --timeout-min <分钟> [--gpu T4]`，退出码 2 就不启动；函数的 `timeout=` 必须等于检查时的分钟数；本月上限 $25（最坏情况计价，留 $5 余量）。先用 CPU（每核每小时 $0.047，每 GiB 每小时 $0.008），GPU 只在神经网络训练时用。只上传公开行情数据和代码，`.env`、Alpaca/DeepSeek 密钥、Google Drive 凭证一律不上传。容器里 `os.cpu_count()` 显示的是宿主机核数，polars/LightGBM 要显式设线程数（`POLARS_MAX_THREADS`、`num_threads`）等于申请的核数。汇报里写本月 Modal 花费（`python3 scripts/modal_budget.py status`）。
- **改代码后**：`uv run ruff format <文件>`、`uv run ruff check <文件>`、相关测试。动了共享模块才跑全量 `uv run pytest`（约 40 分钟，放后台）。产品界面改动还要 `uv run oc repo check --strict`。
- **子代理**：只用 `subagent_type: "sonnet-high"`（Sonnet 5.5，high）。
  - 定义文件已把模型固定为 `claude-sonnet-5-5`。**不要给 Agent 工具传 `model` 参数**：传了会覆盖固定的型号。
  - 机主 2026-09-30：不再用 Sonnet 5。每轮结束前查一次子代理记录里的 `model` 字段，必须是 `claude-sonnet-5-5`；不是就在汇报里写明。
  - 如果 Agent 工具列表里没有 `sonnet-high`，改用 Paseo 的 `create_agent`。
    - 参数：`provider: "claude/sonnet"`、`settings: {"thinkingOptionId": "high", "modeId": "bypassPermissions"}`、`notifyOnFinish: true`。
    - Paseo 把 `sonnet` 按 `~/.claude/settings.json` 解析成 `claude-sonnet-5-5`（2026-09-30 实测）。不准选列表里的 `claude-sonnet-5`。
    - 任务说明里要写进 `~/.claude/agents/sonnet-high.md` 的工作规则和禁止事项。
  - 一轮最多 3 个，同一时间最多 2 个。**子代理一律前台运行**：Agent 调用设 `run_in_background: false`，两个并行就在同一条消息里发两个 Agent 调用。2026-09-28 13:07 那一轮派了两个后台子代理就结束了回合，Paseo 归档本轮时把它们一起杀了，两项任务都没做成。备用路径 `create_agent` 同理：本轮内每隔几分钟用 `get_agent_status` 查一次，结束了再收尾。重的回测任务同一时间只跑一个（内存）；两个子代理并行时，一个做回测、另一个做联网调研或登记这类轻活。任务说明按第 8 节模板写完整，high 强度下也要能一次做对。
  - 任务说明第一行写任务代码，例如 `任务代码 T-20260930-12`。之后给这个子代理的 SendMessage 都以同一代码开头，否则它会把消息当成注入拒绝（2026-09-29）。
- **额度：主代理做还是子代理做**。机主 2026-09-30：「注意控制额度，比如反复的上下文，你要分清楚 subagent 还是在主 agent 做要更节省呢」。
  - **实测**：数据是 2026-09-29/30 的七轮加上 07:07 那一轮，出自本机 transcript 的粗算，不是额度接口。
    - Opus 主代理每轮 26–77 次调用，上下文中位数 90–155k token。
    - Sonnet 子代理每轮 2–4 个，每个 30–120 次调用，上下文中位数 100–200k、最高 333k。
    - 按标价折算（Opus 单价约为 Sonnet 的 1.7 倍），子代理占一轮消耗的 60–90%，多数在 80% 上下。
  - **消耗 ≈ 调用次数 × 当时的上下文大小**：每次调用都要把整段上下文重读一遍。
    - 代理起步只有约 26–31k；涨到一两百 k 的部分全是读进来的文件和工具输出。
    - 输出和思考 token 只占约两成，其中主代理的输出只占 4–8%。所以主审轮用 max 大约只多花 5–15%，真正贵的是长上下文里的多次调用。
  - **规则**：
    1. **主代理做**两类事。
       - 判断：审核、设计、预注册、解读、写纲领。
       - 短活：10 次调用以内，例如读几个 JSON 字段、改一处、跑一条命令、提交。
       - 短活不要派子代理：子代理要从约 26k 重新起步，还要重新找文件，比主代理直接做更贵。
    2. **子代理做**长的机械循环：写代码、测试、跑回测、修错，预计超过 15 次调用的。
       - 一个实验一个子代理。不要让一个子代理连做两个实验，第二个会背着第一个的上下文。
    3. **上下文要小**：
       - 按段读，不整文件读：`rg -n`、`sed -n a,bp`、Read 的 offset/limit。
       - JSON 用 `jq` 或 python 一行，只取需要的字段。
       - 测试用 `-q` 加 `| tail -20`。
       - 不要 `cat` 日志、队列（217 KB）或 `current-view`（118 KB）。
       - 子代理的任务说明里也写上这一条。
    4. **简报写死**要复用的文件和确切命令，让子代理不必探索仓库；写时间上限。
       - 反例：09-29 04:07 那一轮有一个子代理跑了 176 次调用、上下文涨到 392k，一个子代理就用掉约两轮半的量。
    5. **同一实验的小修补**：子代理刚结束、修补又不大，就 SendMessage 给原子代理（带任务代码）；否则新开一个，简报指向已有文件。
    6. **不派"补任务/缺口搜索"子代理**：找方向由主审轮自己做，每天最多一次。
    7. **没活就早收尾**：执行轮没有带简报的任务，做完值守就结束。一轮只值守大约只花一轮研究的零头。

## 6. 预算

- **机主 2026-09-29 决定**（"额度查询先不做了，你自己有数了就行"）：不再查真实额度接口。预检 `decide()` 除非另一轮持有未过期的锁，或本机 transcript 里刚撞到的用量上限还没重置（`usage.retry_after`，本地判断，不查接口），否则就 `go`；不因为额度读数缺失、或机主正在用交互会话而跳过或等待——24 小时可调度不等于必须查额度才能开工，Claude 自己心里有数。**额度方案 A**（机主 2026-09-28 批准的"后台每周 ≤40%、5 小时窗口 ≤50%、机主在用时 ≤30%"三条线，及其 `skip_quota`）已被本决定取代，不再是生效规则；代码没有删，在 `scripts/autonomous_preflight.py` 和 `open_composer/cockpit/data/quota.py` 的 `QUOTA_API_ENABLED` 开关之后，机主要恢复时把这个常量改回 `True` 即可，无需重建定时任务。
- 照常适度节省（机主 2026-09-28：不追求用满时间，质量和效果优先），但不再靠额度百分比卡是否开工或跑多少任务。
- **轮次闸门（2026-10-04 起，cron 每 5 分钟，`scripts/round_limit_gate.py`，不调用模型）**。
  - **背景**：10-02 08:48 到 10-03 22:07，限额期间启动的 12 轮都在第一次调用模型时被拒，几秒就结束，预检根本没机会跑。其中一轮还带着锁死掉，导致下一轮跳过。
  - **它做三件事**：
    1. 本机 transcript 里有尚未重置的限额拒绝时，暂停两个定时任务，到重置后 2 分钟再恢复；
    2. 按自记账控制每周节奏：本周用量超过匀速线 +5%，或超过周上限的 85%（给机主留 15%），就暂停，回到匀速线以下再恢复；
    3. 锁的持有者已经结束时，把锁挪成 `round.lock.dead`。
  - **它只恢复自己暂停的任务。** 机主手动暂停的不会被它恢复。
  - **周上限**按 10-02 撞墙时的实测自记账标定，写在 `config/autonomous-round-gate.json`。这是估计值，不是额度接口读数。
  - **本周用量**看 `logs/autonomous/round-gate-status.json` 的 `pace`；动作记录在 `logs/autonomous/round-gate.log`。主审轮的汇报写一句本周用量占比。
- 软上限 120 分钟，硬上限 170 分钟（下一轮 3 小时后开始）。到硬上限就收尾：没做完的在队列 notes 写断点（做到哪一步、产物路径、下一条命令），状态改回 `ready`。
- 工具输出或子代理结果里出现额度限制（"hit your session limit"、429、rate limit）：不再开新工作，直接收尾——这条不受上面决定影响，撞到就停，不要重试。
- 不要为了用满时间而加任务；没有值得做的就早点结束。

## 7. 收尾（必须做）

1. 更新队列：`done` / `partial` / `blocked`，加一行结果和产物路径（执行轮末尾写"待主审"）。
2. **更新研究纲领**（只有主审轮做，你自己写，不交给子代理）：在 `docs/research-program.zh.md` 对应主线下改"学到了什么"和"下一步"，写日期和产物路径，并按新证据重排优先级。否定的实验要写死因，以及死因意味着下一步是改执行、换宇宙还是关线。
3. 有结论时（只有主审轮做）：登记簿追加行（`uv run oc research directions validate` 必须 ok）、更新 `coverage.json`，在 `docs/current-view.zh.md` 顶部加一个短的日期小节（不超过 12 行：结论、数字、下一步）。没有结论就不要改 `current-view`。
4. 运行 `uv run python scripts/autonomous_preflight.py release`，把输出 JSON 原样作为 `--usage-json` 传给
   `uv run python scripts/autonomous_preflight.py log --status <done|partial|failed> --task <任务 ID> --summary "<一句话>" --usage-json '<release 的输出>'`。
5. 只 `git add` 本轮改动的文件；提交前 `git diff --cached | grep -iE "auth_token|ct0=|api[_-]?key|secret|bearer"` 确认没有密钥；提交信息末尾加一行 `Co-Authored-By:`，写本轮的模型：主审轮 `Claude Opus 5.5 <noreply@anthropic.com>`，执行轮 `Claude Sonnet 5.5 <noreply@anthropic.com>`。
   - **迭代档案在 `.gitignore` 里**（`reports/research/iterations/*`）。新产出的 `results.json`、`report.md`、`candidate-manifest.json`、`prebacktest-validated-at.txt`、`cost-table.json`、`data-feasibility.json`、`sources/`、修正案等文件，必须逐个用 `git add -f <路径>` 加入。`cache/` 不提交。
   - 提交后用 `git status --short --ignored reports/research/iterations/<id>` 确认除 `cache/` 外没有 `!!` 行。
   - 2026-09-30 10:07 执行轮只提交了已跟踪的文件，两个任务的 `results.json` 都没进 git，由交互会话补交。
6. **最后一条消息**是给机主看的汇报（在 Paseo 里显示）。**同一份汇报要在第 5 步提交之前写进 `reports/owner/rounds/<YYYY-MM-DD>T<HHMM>Z-<lead|exec>.md`**（本轮开始的 UTC 时间，格式见该目录的 README），和本轮改动一起提交；看板的报告页和每日邮件从这里读。执行轮只写三行：做了哪些简报、各自产物路径和"待主审"、值守是否正常。主审轮中文、简短，按这个结构：
   - **这一轮做了什么**（1–3 条）
   - **结果**（数字要和 JSON 核对过；否定的也写清楚为什么）
   - **模拟盘值守**（正常 / 异常及处理）
   - **下一轮做什么**
   - **需要你决定的**（没有就写"无"）
   第一次出现的专业词用一句话解释。不要贴日志，不要列文件清单。
7. **把同一段汇报送到机主的对话里**（定时任务结束后会自动归档本代理，机主看不到这里）：用 ToolSearch 加载 `mcp__paseo__send_agent_prompt`，`agentId` 取 `config/autonomous-report-target.json` 的 `agent_id`，`background: true`，`notifyOnFinish: false`，消息以 `【自动研究轮汇报 MM-DD HH:MM UTC】` 开头。跳过的轮不发（机主在用对话时本来就会跳过）。发送失败就在自动轮日志的摘要里写"汇报未送达"。
   - **主审轮**只在三种情况发（机主 10-06：逐轮记录只当附件，没意义的事不写）：
     - 模拟盘异常；
     - 需要机主决定的事；
     - 阶段性结论，例如某个策略升档、关线或上模拟盘。

     消息按 `docs/owner-reporting.zh.md` 第 0 节写：业务名称，不写任务号和代号，不贴过程。其余进展由每天 00:10 UTC 的日报撰写步骤从逐轮记录里整理进日报。
   - **执行轮**平时不发：它的结果还没审核，由下一主审轮汇报。只有两种情况要发，消息以 `【执行轮提醒 MM-DD HH:MM UTC】` 开头：
     - 模拟盘值守发现异常；
     - 有需要机主决定的事。

## 8. 子代理任务说明模板

主审轮写执行简报、任何一轮派子代理，都用这个模板。

```
任务代码：<T-YYYYMMDD-NN>（之后给这个子代理的消息都以它开头）
目标：<一句话，要回答的问题>
背景：<为什么做；相关文件路径：卡片、脚本、数据、上一轮结果>
输入：<数据路径、窗口、候选清单路径>
步骤：<编号步骤，带确切命令；哪一步之前必须先通过哪个检查>
验收标准：<可机械核对的条件，例如 JSON 里哪个字段满足什么>
复用：<现成脚本、模块、模板的路径；写明"不要另起炉灶、不要通读仓库">
禁止：<不许改的文件、不许做的操作；照抄 ~/.claude/agents/sonnet-high.md 的"Never"之外的本任务特有限制；不许删除或回退不是本任务创建的文件；不整文件读队列、current-view、日志，JSON 只取需要的字段>
产出：<写到哪些文件>
汇报：<不超过 12 行：做了什么、结论和数字（注明来自哪个文件）、没做完的>
上限：<时间、内存（run_capped 的 --mem）>
等待：长任务在本任务内前台分段等（timeout 540 的 PID 循环），不许结束回合去等后台通知
```

## 9. 队列格式（`reports/research/control/autonomous-queue.md`）

每个任务一个三级标题块，字段固定：

```
### T-YYYYMMDD-NN 标题
- status: ready | running | partial | blocked | done
- priority: 1（最高）…
- not_before: YYYY-MM-DD HH:MM UTC（可空）
- goal: 要回答的问题，以及它怎样更快接近盈利
- plan: 步骤、预注册要点、通过标准
- done_when: 可核对的完成条件
- brief: reports/research/control/briefs/<任务 ID>.md（主审轮写；执行轮只做带这个字段的任务；可空）
- notes: 每轮追加一行：日期、做到哪、产物路径、下一条命令
```

机主或交互会话可以随时改队列；自动轮只改自己在做的那个任务块和新加的任务。
