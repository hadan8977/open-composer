# 内存管理 Runbook

机主 2026-10-07 要求：本项目不能占满内存，任何时候都要留出约 500 MB 空闲，给机主的其他项目（Hermes）、机主自己的对话和代理服务（xray、hysteria）用；以后做预算也不能默认整台机器都归本项目。这条是永久规则，登记在 `docs/owner-rules-register.zh.md`。

机主 2026-10-08：3 个后台代理、单任务 1.2 GB 太严，上限翻倍到 6 个和 2.4 GB，方案要简单。办法有两个：
- 开内存压缩（zswap）：闲置内存压缩后留在内存里；
- 加第二个交换文件。

本项目内存上限 2.2 GB 和给机主的 500 MB 都不变。

机主同日补充：可用内存短暂低到 324 MB 也可以接受，别一直特别满就行。500 MB 是调节器长期守的线，不是一秒都不能碰的线。调节器的做法正好对应：
- 可用内存低于 650 MB 就压本项目；
- 低于 500 MB 持续 30 秒才停研究任务；
- 每小时记录里的 `ticks_below_reserve` 看的是累计多久，不是有没有碰到过。

- 预算数字（唯一来源）：`config/memory-budget.json`
- 调节器：`scripts/memory_budget.py`，由 `oc-memory-governor.service` 常驻运行
- 状态：`logs/memory/governor-status.json`（每 5 秒更新）；动作记录：`logs/memory/governor.log`；每小时最低可用内存：`logs/memory/hourly.jsonl`（按每 5 秒的采样，不是 sar 的 10 分钟平均）
- 系统文件的源和安装：`deploy/memory/`，安装用 `deploy/memory/install.sh`（幂等，替换前备份到 `/root/backups/memory-budget/`）
- 随时查看：`python3 scripts/memory_budget.py status`

## 1. 为什么要管

2026-10-07 16:46 UTC 的实测（重启前）：

| 项 | 数值 |
|---|---|
| 可用内存 | 761 MB（总共 3914 MB） |
| 交换区 | 8 GB 用了 98%（其中 4 GB 是临时加的 swapfile2，重启后已不在） |
| 负载 | 31（6 核），整机在换页 |
| 结果 | 17:27 重启 |

当时占内存最多的：

- 17 个 claude 进程，其中 16 个属于本项目，合计 2.2 GB 常驻、1.55 GB 交换区；
- 两个同时运行的 pytest，合计 2.1 GB；
- Modal 本地客户端 1.9 GB：它把所有分片的结果包同时放在内存里；
- 每个代理各起一份 gdrive MCP，每份约 47 MB；
- 研究任务约 1 GB。

10-04 到 10-07 的 sar 记录里，每小时最低可用内存多次低于 500 MB。

根因：

1. 只有单个任务有上限（`run_capped.sh` 默认 1.8G），整个项目没有总上限，代理进程完全不受限；
2. 预算文字写的都是整台机器（"3.9 GB""4 GB 内存"），从来没扣掉其他项目和机主的预留；
3. 空闲代理 24 小时才归档，而归档服务 10-07 14:44 起卡住，连计时器也停了；
4. OOM 保护方向反了：本项目所有 claude 进程都被保护（-500），机主其他项目的会话反而成了 earlyoom 优先杀的对象。

预算上线后，10-08 凌晨（UTC）还是两次低于 500 MB：

| 时间 | 最低可用 | 低于 500 MB 累计 | 经过 |
|---|---|---|---|
| 00 点这一小时 | 291 MB（00:36） | 约 4.5 分钟 | 交互会话 00:22 手工补跑模拟盘数据刷新，和代理同时运行 |
| 01:53 | 150 MB | 约 80 秒 | 整机交换区用满（内核记录 Free swap = 4kB） |

01:53 这次的经过：
- 刷新链里 nsi 的一致性检查（`scripts/check_feature_invariance.py`，没走 run_capped）占了 2.1 GB 匿名内存。
- earlyoom 按当时的 `--prefer claude` 配置，先去杀两个只有 80 MB 的代理进程，没杀掉。
- 内核 OOM 杀了 Paseo 浏览器的一个辅助进程。systemd 默认的 `OOMPolicy=stop` 随即停掉并重启了整个 Paseo 守护进程，所有会话一起断了，包括机主其他项目的会话。
- earlyoom 最后才杀掉那个 2.1 GB 的检查进程，补跑因此失败。

10-08 的修正见 3.5、3.6 节。

## 2. 预算

重启后没有本项目代理时，其他项目和系统常驻约 1.2 GB（hermes、DeepSeek 网页、Paseo 守护进程、quantcheck、pm2、freellmapi、gdrive、cloudflared、xray、hysteria 等）。

| 项 | 值 |
|---|---|
| 给机主留的可用内存 | 至少 500 MB；调节器目标 650 MB |
| 本项目硬上限 | 2200 MB（`oc.slice` 的 MemoryMax，内核强制） |
| 本项目软上限 | 900–2000 MB，由调节器按其他项目的用量实时调整 |
| 本项目交换区 | 最多 3 GB（10-08 起；之前 2 GB） |
| 整机交换区 | 8 GB：`/swapfile` 和 `/swapfile2` 各 4 GB，前面有 zswap 压缩 |
| 研究任务合计 | 最多 2.4 GB（2458 MB） |
| 单个本地任务 | 默认 900 MB，最多 2.4 GB（`--mem 2.4G`，2458 MB）；超过就放 Modal |
| 启动条件 | 全机可用内存在 500 MB 预留之外还多出 200 MB（研究任务是 min(--mem, 200 MB)），且研究任务合计没满 2.4 GB；不够就等。按实际用量算，不按上限 |
| 同时存活的后台代理（轮次和子代理） | 最多 6 个；第 7 个启动时被拒 |
| pytest | 本仓库同一时间只跑一个 |

- 每个 claude 代理约 200–300 MB，但大部分时间在等模型回复，内存是闲着的。
- 10-08 起开了 zswap：内核把闲置内存压缩后留在内存里，最冷的部分才写到交换文件。被压缩的代理再用到这些内存时，从内存里解压，不用等磁盘。
- 压缩比看状态文件：`zswapped_mb` 是压缩前的大小，`zswap_pool_mb` 是压缩后占的内存。所以 6 个后台代理能放进同样的 2.2 GB。
- 代价：6 个代理同时忙，再加一个大任务时，有一部分内存在压缩区或交换区，速度会变慢，但不会挤占机主的 500 MB。
- 实际要用 1.5 GB 以上的任务（估计值），放 Modal 更稳。
- 真想要两倍的物理内存，只能换更大内存的机器，这是机主的花费决定。

## 3. 机制

### 3.1 内核强制的总上限

本项目运行的一切都在 `oc.slice` 下：

| 子组 | 里面是什么 | 设置 |
|---|---|---|
| `oc-interactive.slice` | 本项目的顶层 Paseo 会话（机主的对话、主审会话） | MemoryLow=350M，最后才被回收 |
| `oc-agents.slice` | 定时轮次和子代理，以及它们启动的一切（MCP、pytest、临时脚本、modal） | — |
| `oc-research.slice/oc-research-capped.slice` | `run_capped.sh` 的研究任务，一个任务一个 scope | 合计 MemoryMax=2.4G、MemorySwapMax=2G；同时受 `oc.slice` 的 2.2 GB 限制 |
| `quant.service` | 只读 cockpit | MemoryMax=300M |

模拟盘的 cron 任务（`run_capped.sh --class paper`）在 `paper.slice/paper-capped.slice`，不在本项目预算里。它们不排队、不被拒、不会被调节器停掉。占用的内存由调节器从研究预算里让出来。期权链记录器有固定时间窗，也用 `--class paper`。

### 3.2 代理怎么进预算

- Paseo 的 claude provider 配置为 `agents.providers.claude.command = {"mode": "replace", "argv": ["/usr/local/sbin/paseo-claude-launch"]}`，在 `/root/.paseo/config.json`，用 `paseo daemon reload` 生效。
- 包装器（源文件 `deploy/memory/paseo-claude-launch.sh`）看工作目录：
  - 工作目录不在本仓库下：原样启动，机主其他项目不受影响。
  - 在本仓库下：查这个代理的 Paseo 记录。
    - 有 `paseo.parent-agent-id` 或 `paseo.schedule-id` 标签的是后台代理，放进 `oc-agents.slice`；
    - 其他的是交互会话，放进 `oc-interactive.slice`；
    - 用 `systemd-run --scope` 原地执行：PID、标准输入输出、环境变量都不变；
    - 加 `BindsTo=paseo-daemon.service`，Paseo 停的时候代理跟着停，和以前一样。
- 后台代理已经有 6 个时，第 7 个以退出码 75 被拒，stderr 写明原因，系统日志标签 `paseo-claude-launch`。交互会话一律放行。
- 预算检查出任何错误，都退回原样启动：包装器绝不阻止 Paseo 启动代理。

### 3.3 调节器

`oc-memory-governor.service` 每 5 秒运行一次（间隔在 `interval_s`）：

- 可用内存低于 650 MB：把 `oc.slice` 的 MemoryHigh 降到"当前用量减去缺口"，最低 900 MB。内核随之回收本项目的内存：先丢缓存，再把空闲代理换出。其他项目的内存不动。
- 可用内存高于 950 MB：每次放宽 100 MB，最多到 2000 MB。
- 可用内存低于 500 MB 持续 30 秒：停掉最新启动的研究任务。研究任务都写断点，可以续跑。
- 服务本身：OOMScoreAdjust=-900，MemoryMax=60M，Restart=always。

### 3.4 启动前的准入

- `scripts/run_capped.sh`（研究类，默认）：
  - `--mem` 超过 2.4G（2458 MB）：退出码 2，提示改用 Modal；
  - 启动前要有余量：研究任务区（合计 2.4G）里还空着 min(--mem, 200 MB)，全机可用内存也比预留多出这么多；按正在运行的任务的实际用量算，不按它们的上限，所以小任务可以并行，大任务会等。最多等 `--wait-min`（默认 60 分钟），超时退出码 75；
  - 10-08 起不再看本项目软上限下面还剩多少：项目内部的空间由内核压缩闲置内存腾出来，只要全机还有余量就放行，机主的 500 MB 由调节器守；
  - 10-07 第一版用过一把按上限排队的锁，一个只用 100 MB 的任务也会挡住所有人，当天就改掉了；
  - 任务给自己 +200 的 OOM 分，出事时先牺牲它。
- `scripts/round_limit_gate.py`（每 5 分钟）：后台代理已满，或新代理所需余量连续 5 分钟不足时，暂停轮次计划；条件解除后自动恢复。手动暂停的计划不会被它恢复。
- `tests/conftest.py`：本仓库的 pytest 拿 `/tmp/open-composer-pytest.lock` 后才跑，第二个会等，最长 `OC_PYTEST_LOCK_WAIT` 秒（默认 3600）。
- `scripts/modal_run.py`：本地 `modal run` 客户端在 `run_capped.sh --mem 1G` 下运行。`scripts/modal_app.py` 不再通过函数返回值传结果：每个分片把结果打包写到 Modal 卷 `oc-out`（`<日志名>/shard_<i>.tar.gz`）并提交，本地客户端逐个流式下载到临时文件、解包，再删掉远端那份。原因：返回值会被 `modal run` 客户端整批缓存，与我们按什么顺序取无关。10-07 先撞到 1.9 GB，之后又在 1 GB 上限被杀了四次（t21-features，14 个分片）。改后当晚用 2 个分片、每个 30 MB 的小任务实测通过（花费约 $0.01）。

### 3.5 降低常驻

- 空闲归档：`/root/.paseo/bin/paseo_memory_maintenance.py` 每小时跑一次（源文件 `deploy/memory/paseo_memory_maintenance.py`）。
  - 后台代理空闲 2 小时归档，顶层会话空闲 24 小时归档；
  - 归档 10 分钟后回收进程，只回收代理自己 cgroup 里的进程。10-07 发现机主 pm2 管理的 part1 服务也带着某个代理的 ID，按旧逻辑会被误杀；
  - 带 `memory.keep=true` 标签的代理不归档，给还要追问的子代理用；
  - 服务加了 20 分钟超时，卡住不再连带停掉计时器。
- gdrive MCP 改为全机共用一份：`~/.claude.json` 里的 gdrive 是 `http://127.0.0.1:5573/mcp`（`gdrive-mcp-http.service`），不再每个 Claude 会话各起一份 stdio 进程（每份约 47 MB）。新会话生效，所有项目都受益。备份在 `/root/backups/memory-budget/`。
- 交换区和压缩（10-08 改）：
  - 10-07 写过"交换区保持 4 GB，不再加第二个"，担心整机换页。10-08 01:53 交换区真的用满了，内核杀进程时连带停了整个 Paseo。
  - 现在 8 GB：`/swapfile2` 已写进 fstab。本项目交换区有自己的上限（3 GB），多出的空间留给机主的其他项目。
  - 前面加了 zswap（`oc-zswap.service`）：zstd 压缩，算法 zsmalloc，压缩池最多占内存的 25%。压缩池计入各自 cgroup 的内存，所以本项目 2.2 GB 的上限照样管得住。
  - 换出去的页先在内存里压缩存放，常用的直接从内存取回；只有最冷的才写盘。

### 3.6 OOM 兜底顺序（全机）

只有在内核和调节器都没拦住时才轮到 earlyoom。顺序是：

1. 研究任务（+200）；
2. 本项目后台代理（0）；
3. 本项目交互会话（-300）；
4. 机主其他项目的会话（-500）。

- 实现：`claude-orchestrator-protect.sh`（每 30 秒）按 cgroup 设分；`oom-auto-protect.sh` 不再保护 `oc.slice` 里的大进程。
- earlyoom 永远不杀：hermes、cloudflared、xray、hysteria、rclone、quantcheck、Paseo、sshd 等。
- earlyoom 不再偏向杀 claude（10-08 去掉 `--prefer`）：按实际大小挑，先杀真正占内存的进程。10-08 01:53 它按偏好去杀 80 MB 的代理，没杀掉，2.1 GB 的进程留着把交换区撑满。
- Paseo 守护进程设 `OOMPolicy=continue`（`deploy/memory/systemd/paseo-daemon.service.d/50-oom-policy.conf`）：内核杀掉它下面的某一个进程时，只死那一个，守护进程和其他会话照常。改这项不用重启 Paseo。

### 3.7 模拟盘任务（paper 类）

- **事故**：10-07 22:45 的夜间数据刷新（`scripts/refresh_equity_book_live.py`）停在第一步，第二天模拟盘下单要用的目标没写出来。
  - 原因：这个脚本自己拼 run_capped 命令（`CAPPED`，`--mem 1.8G`），没带 `--class paper`，被研究类上限 1229 MB 拒绝（退出码 2）。
  - 疏漏：上线预算时只改了 crontab 里直接写的 run_capped 行，没搜代码里自己拼命令的调用方。
  - 处理：交互会话在 worktree 分支修好，合并为 091bc7b，10-08 00:22 UTC 补跑了整条链。
- **规则**：凡是喂模拟盘下单的命令一律 `--class paper`；研究类最多 2.4G（10-08 前是 1.2G）。
  - 目前已知的 paper 调用方：crontab 里的 run_capped 行、`scripts/refresh_equity_book_live.py`、`scripts/install_rotation_sleeve_cron.sh`（重装 cron 时生成的行）、`scripts/refresh_insider_features_for_paper.sh`、`open_composer/execution/schedule.py`（bar-cycle 的 cron 建议行）。
  - `open_composer/research/autonomy.py` 的研究任务上限从预算读取（`job_max_mb`）。
  - `tests/test_run_capped_callers.py` 用 ast 读代码实际拼出的命令（不看 docstring 和注释），研究类超过预算的 `job_max_mb` 就失败，paper 调用方没写 `--class paper` 也失败。
  - 旧研究脚本里的 `--mem 1.8G` 在 2.4G 以内，10-08 起照常能跑。
- **从交互会话手工补跑模拟盘数据任务**：
  - 交互会话本身在 `oc.slice` 里（上限 2.2 GB）。刷新链里不封顶的检查步骤约 1.6 GB，在会话里直接跑会撞上限，连带拖慢会话。
  - 做法：把整条链作为临时 systemd 服务放进 `paper-capped`。命令和 crontab 那条一致；会话结束也不影响它；日志照常写到 cron 日志里。10-08 实测可用：

    ```
    systemd-run --unit=oc-<名字>-manual-$(date -u +%Y%m%dT%H%M) --slice=paper-capped \
      --working-directory=/root/codex-test/open-composer \
      --setenv=HOME=/root --setenv=PATH=/root/.local/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin \
      --setenv=UV_CACHE_DIR=/tmp/open-composer-uv-cache \
      -p MemoryMax=2.4G -p MemorySwapMax=2G \
      /bin/bash -c '<和 crontab 同一条命令链>'
    ```

  - `MemoryMax` 是 10-08 加的。10-08 00:22 那次补跑没设上限，和代理同时跑，可用内存一度低到 291 MB。01:53 交换区用满时，检查步骤被 earlyoom 杀掉，补跑失败（3.6 节）。
  - 趁后台代理少的时候跑。刷新链的一致性检查要 1.6–2.1 GB，跑的那几分钟调节器会把本项目压到下限，可用内存仍可能短暂低于 500 MB。
  - 这一步和 500 MB 规则在结构上冲突（每晚 22:45 的 cron 也一样），要改成分块比较。这是模拟盘代码，走 worktree 分支，由交互会话审核合并。

  - 进度：`systemctl status oc-<名字>-manual-...`；输出：`journalctl -u oc-<名字>-manual-...` 和原来的 cron 日志。
  - 只跑一步、几分钟就完的，也可以用 `scripts/run_capped.sh --class paper --mem <N> -- <命令>`。但这个 scope 跟着会话走，会话被归档就会被杀，长任务用上面的服务方式。

## 4. 研究者和自动轮怎么做

- 做预算时按第 2 节的表，不按整台机器。
- 新开子代理前先跑 `python3 scripts/memory_budget.py admit --kind agent`，退出码 2 就先归档一个空闲子代理，或等一等。
- 读行情数据的任务一律 `scripts/run_capped.sh --mem 900M -- ...`；需要更多的最多 `--mem 2.4G`，再大就拆小或放 Modal。实际要用 1.5 GB 以上的任务和忙着的代理同时跑会变慢，放 Modal 更稳。
- 代理自己直接跑的大进程（不走 run_capped）没有单独上限，只受本项目 2.2 GB 管，会把同组的代理挤进压缩区。读大文件的脚本一律走 run_capped。
- 在代码里拼 run_capped 命令时：喂模拟盘的写 `--class paper`，研究类不超过 2.4G（第 3.7 节；`tests/test_run_capped_callers.py` 会拦）。改共享包装器（run_capped、启动器）的约定时，先搜全部调用方，包括代码里自己拼命令的地方，再核对当晚要跑的 cron 链。
- 不要并行跑多个全量 pytest；改共享模块才跑全量。
- 子代理做完后，如果之后不再追问，就让它归档（或等 2 小时自动归档）；要留着就给它加 `memory.keep=true`。

## 5. 检查和排错

| 想看什么 | 命令 |
|---|---|
| 当前用量、余量、代理数 | `python3 scripts/memory_budget.py status` |
| 调节器做过什么 | `tail logs/memory/governor.log` |
| 进程分组 | `systemd-cgls /oc.slice` |
| 被拒的代理 | `journalctl -t paseo-claude-launch` |
| 包装器还在不在、有没有逃出预算的代理 | `status` 里的 `paseo_wrapper_configured`（应为 true）和 `uncapped_project_agents`（应为 0）。Paseo 或 Claude Code 升级后若变成 false，跑 `deploy/memory/install.sh --paseo` 再 `paseo daemon reload` |
| 每小时最低可用（5 秒采样） | `tail logs/memory/hourly.jsonl`（`ticks_below_reserve` 应为 0） |
| 每小时最低可用（sar，粗） | `sar -r -f /var/log/sysstat/saDD` |
| 压缩和交换区 | `grep -E 'Zswap|Swap' /proc/meminfo`；`swapon --show`；`status` 里的 `zswap_pool_mb`、`zswapped_mb` |

- 改预算：改 `config/memory-budget.json`（调节器每轮重读）。改硬上限还要同步 `deploy/memory/systemd/oc.slice`，再跑 `deploy/memory/install.sh`。
- 回滚：
  1. 把 `/root/.paseo/config.json` 里 claude 的 `command` 删掉，跑 `paseo daemon reload`；
  2. `systemctl disable --now oc-memory-governor`；
  3. 从 `/root/backups/memory-budget/<时间>/` 恢复被替换的系统文件；
  4. 压缩：`systemctl disable --now oc-zswap`；第二个交换文件：`swapoff /swapfile2`，再删掉 fstab 里那一行（要先有足够的空闲内存和交换区接住换回来的页）。
