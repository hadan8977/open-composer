# 自动研究轮执行手册 — 2026-09-27

机主 2026-09-27 批准：每天 UTC 01:07 和 13:07 由 Paseo 定时任务各启动一个新的研究代理，跑一轮研究。本手册就是那个代理的完整任务说明；定时任务的提示词只让它读本文件并照做。改流程时改本文件，不用重建定时任务。

## 0. 身份、目标和边界

- **你是谁**：定时启动的研究代理，模型是最新的 Opus（现在是 5.5），思考强度 **high**。机主平时用 max 在交互会话里对话；你和交互会话共用同一个 5 小时额度，所以要省。
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
- **机主已否决、不要再提的**（2026-09-27）：大模型联网选股的前向测试（arXiv 2601.11958）、MarketSenseAI 多代理选股。S3 小额实盘"再说"，不要每轮催。

## 1. 预检（第一步，必须做）

```bash
cd /root/codex-test/open-composer
export POLARS_SKIP_CPU_CHECK=1 UV_CACHE_DIR=/tmp/open-composer-uv-cache
uv run python scripts/autonomous_preflight.py check
```

看输出 JSON 的 `decision`：

- `go`：继续。
- `wait_owner_active`：机主正在用交互会话。用 Bash 工具的 `run_in_background: true` 运行
  `uv run python scripts/autonomous_preflight.py wait-quiet --max-minutes 120`，然后**结束本回合**；它完成时你会收到通知，读结果：`go` 就继续，否则按跳过处理。
- `skip_*`（另一轮在跑、额度限制未恢复、等了 2 小时机主仍在用）：运行
  `uv run python scripts/autonomous_preflight.py log --status skipped --summary "<原因>"`，只 `git add reports/research/control/autonomous-log.md` 并提交，用一两句话汇报后结束。

`go` 之后先运行 `echo $PASEO_AGENT_ID` 看到自己的 ID，再把这个 ID **原样写进命令**（不要写 `$PASEO_AGENT_ID`，脚本靠命令文本在会话记录里认出本轮）：

```bash
uv run python scripts/autonomous_preflight.py acquire --agent-id <上一步看到的 ID>
```

记下预检输出里的 `git.dirty`：那些是别人没提交的改动，本轮不要碰、不要提交。

## 2. 读上下文（控制在 15 分钟以内）

1. `docs/research-mission.zh.md` 全文。
2. `docs/current-view.zh.md` 最上面一到两个日期小节，不要通读。
3. `reports/research/control/autonomous-queue.md`（任务队列）全文，`reports/research/control/autonomous-log.md` 最后 10 行。
4. 记忆索引会自动加载；只打开和本轮任务相关的记忆条目。

## 3. 值守检查（只读，10 分钟以内）

```bash
for s in us_etf_levered_rotation_63_top2_monthly us_etf_growth_rotation_blend_top2_monthly us_etf_sector_rotation_252_top2_weekly; do
  echo "== $s"; sed -n 1,8p reports/paper/rehearsal/$s-latest.md | cut -c1-200
  tail -n 3 logs/rotation_$s.log 2>/dev/null | cut -c1-200
done
sed -n 1,15p reports/paper/alerts.md | cut -c1-200
ls -la --time-style=+%m-%d_%H:%M reports/paper/rehearsal/*-latest.md
```

- 三条模拟盘 sleeve：S1 `us_etf_sector_rotation_252_top2_weekly`、S2 `us_etf_growth_rotation_blend_top2_monthly`、S3 `us_etf_levered_rotation_63_top2_monthly`；授权到 2026-11-01。定时任务周一到周五：22:00 行情、23:05 目标、23:35–23:45 下单、次日 14:05–14:09 对账。
- 算异常的情况：`-latest.md` 状态是 error / blocked；工作日的报告超过 30 小时没更新；日志里有 Traceback；有撤单、部分成交或未成交；alerts 状态不是 ok 或只有已知的"快照过期"警告以外的告警；授权 7 天内到期。
- 异常写进汇报第一条，并在队列里加一个修复任务。**不要**自己改券商状态、授权或 crontab。代码缺陷可以在本轮修（写测试），但不能触发下单。

## 4. 选任务

- 队列格式见第 9 节。按文件顺序取第一个 `status: ready` 且 `not_before` 已到的任务。开始时把它改成 `running`，在 notes 里写本轮开始时间。
- 队列里没有能做的任务时，做**缺口搜索**：
  1. `uv run oc research directions summary` 和 `reports/research/harvest/coverage.json`，挑一个和近期盈利相关、搜索最少的格子。
  2. 用 `scripts/harvest_search.py run --channel <exa|web|reddit|x|github|archive> --query "<...>" --n 8 --max-read 6` 搜 3–6 次（查询要具体，覆盖论文复现、反面证据、开源代码、从业者实盘记录四类）。
  3. 新方向先 `uv run oc research directions check <关键词>` 查重，再按登记簿格式追加，`uv run oc research directions validate` 必须 ok。
  4. 最多往队列里加 2 个新任务，写清楚最便宜的否定测试。
- **一轮只做一个实质任务**。提前做完且没超 60 分钟，可以再做一个 20 分钟以内的小任务（文档、登记、小修复）。

## 5. 执行规则

- **研究协议**（和 `CLAUDE.md`、`AGENTS.md` 一致）：先联网读原文 → 登记簿查重 → `uv run oc research iteration init <id>` → 写 `direction-review.json`、候选清单（预注册每个候选）→ `uv run oc research direction-check <path>` 和 `uv run oc research iteration validate <id> --stage pre-backtest` 都通过 → 回测 → `--stage final` 通过 → 假设卡、decision record、登记簿、覆盖地图。
- **冻结合同**（`docs/plan-strategy-factory-2026-09-22.zh.md` 第 1 节）：选择窗 2023-09-18→2025-12-31；对标窗 2024-01-08→今天；每边 10 bp，收盘出信号、次日开盘成交；安慰剂对照；G1 年化 ≥50% 且最大回撤 ≤35%，或 G1' 夏普 ≥2 且年化 ≥30%；G2 留出窗夏普 ≥1；G3 安慰剂打赢比例 ≤10%；G4 20 bp/边仍成立；G5 Alpaca 只做多可执行。2026-01→09-17 这段已被反复看过，只能当"受污染的留出"；2026-09-18 以后的月份才是新的留出。压力期用 2016-05→2023-08（数据从 2016-01 开始）。
- **核对**：每个结论都要自己对着原始 JSON 逐条核对预注册的标准，再写进汇报（子代理说"过了"不算数）。
- **算力**：这台机器 4 GB 内存、没有 GPU，内存紧张时系统先杀 Claude。读行情数据的任务一律 `scripts/run_capped.sh --mem 1.8G -- ...`，同一时间只跑一个重任务。长任务用 `setsid nohup ... > logs/<名字>.log 2>&1 &` 脱离运行、写断点；等待用后台命令（`while kill -0 <PID>; do sleep 30; done`，`run_in_background: true`）然后结束回合，不要反复轮询。
- **改代码后**：`uv run ruff format <文件>`、`uv run ruff check <文件>`、相关测试。动了共享模块才跑全量 `uv run pytest`（约 40 分钟，放后台）。产品界面改动还要 `uv run oc repo check --strict`。
- **子代理**：只用 `subagent_type: "sonnet-high"`（Sonnet，high）。一轮最多 2 个，同一时间 1 个。任务说明按第 8 节模板写完整，high 强度下也要能一次做对。

## 6. 预算

- 软上限 90 分钟，硬上限 150 分钟。到硬上限就收尾：没做完的在队列 notes 写断点（做到哪一步、产物路径、下一条命令），状态改回 `ready`。
- 工具输出或子代理结果里出现额度限制（"hit your session limit"、429、rate limit）：不再开新工作，直接收尾。
- 不要为了用满时间而加任务；没有值得做的就早点结束。

## 7. 收尾（必须做）

1. 更新队列：`done` / `partial` / `blocked`，加一行结果和产物路径。
2. 有结论时：登记簿追加行（`uv run oc research directions validate` 必须 ok）、更新 `coverage.json`，在 `docs/current-view.zh.md` 顶部加一个短的日期小节（不超过 12 行：结论、数字、下一步）。没有结论就不要改 `current-view`。
3. 运行 `uv run python scripts/autonomous_preflight.py release`，把输出 JSON 原样作为 `--usage-json` 传给
   `uv run python scripts/autonomous_preflight.py log --status <done|partial|failed> --task <任务 ID> --summary "<一句话>" --usage-json '<release 的输出>'`。
4. 只 `git add` 本轮改动的文件；提交前 `git diff --cached | grep -iE "auth_token|ct0=|api[_-]?key|secret|bearer"` 确认没有密钥；提交信息末尾加一行 `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`。
5. **最后一条消息**是给机主看的汇报（在 Paseo 里显示）。中文、简短，按这个结构：
   - **这一轮做了什么**（1–3 条）
   - **结果**（数字要和 JSON 核对过；否定的也写清楚为什么）
   - **模拟盘值守**（正常 / 异常及处理）
   - **下一轮做什么**
   - **需要你决定的**（没有就写"无"）
   第一次出现的专业词用一句话解释。不要贴日志，不要列文件清单。

## 8. 子代理任务说明模板

```
目标：<一句话，要回答的问题>
背景：<为什么做；相关文件路径：卡片、脚本、数据、上一轮结果>
输入：<数据路径、窗口、候选清单路径>
步骤：<编号步骤，带确切命令；哪一步之前必须先通过哪个检查>
验收标准：<可机械核对的条件，例如 JSON 里哪个字段满足什么>
禁止：<不许改的文件、不许做的操作；照抄 ~/.claude/agents/sonnet-high.md 的"Never"之外的本任务特有限制>
产出：<写到哪些文件>
汇报：<不超过 12 行：做了什么、结论和数字（注明来自哪个文件）、没做完的>
上限：<时间、内存（run_capped 的 --mem）>
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
- notes: 每轮追加一行：日期、做到哪、产物路径、下一条命令
```

机主或交互会话可以随时改队列；自动轮只改自己在做的那个任务块和新加的任务。
