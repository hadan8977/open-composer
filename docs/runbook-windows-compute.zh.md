# Windows 11 临时研究计算机

机主2026-10-11授权定时观察Hadan可用性。Linux系统timer `oc-hadan-availability.timer` 每5分钟执行一次本地到期检查；`config/hadan-availability-watch.json` 暂按北京时间周一至五09:00–19:00每15分钟远端probe，其余每60分钟。工作日优先段未引入法定节假日推断，不授予工作权限。状态 `reports/research/control/hadan-availability.json` 与变化事件供持续goal读取；未知/超时不能解释为ready。每次实际派工另做fresh preflight，训练依16:39 UTC后的机主资源条件授权；不修改Windows开机/暂停设置。

> **当前唯一方案（2026-10-10）**：使用 Windows 上的 Paseo daemon/agent 作为执行目标，并使用本机 localhost 网页开关。Tailscale、OpenSSH、WSL2 不属于本项目的部署或连接路径。

> **机主硬约束**：Windows 电脑只允许使用 `C:\paseo`。worker 脚本、Paseo workspace、scratch、临时文件和结果缓存都必须位于该目录；整个目录总占用最多 `50 GiB`。任何其他根目录或超出配额的任务都必须拒绝。

> **2026-10-11 16:39 UTC 当前授权纠正**：机主允许合适已有资源恢复研究训练/参数更新；Hadan可分担资料研究、计划、准备、独立审查、特征/回测和训练，仅限电脑在线开机且fresh remote preflight成功、worker `ready`、`usage_ok=true`、占用低于50GiB。不得主动开机、resume/hard-on或绕过本机开关。必要模型下载/load使用当前有效任务manifest，不复活已撤回实验，不新增付费。统一授权见 `reports/research/control/owner-compute-hold.json`；符合条件时直接使用，无需再次请示是否恢复。

Codex 派工仍用已登录的 Paseo daemon/provider：显式 full-access、`gpt-6.1-sol/high`（复杂科学判断与独立科学审查按需用 xhigh），回读实际配置与工作目录；不安装另一套服务，不读取凭证。先准备完整 brief 和 manifest，再在 ready 条件成立时传入 `C:\paseo\scratch\<job_id>`。每项输出、回传 hash 与清理都绑定同一个 job；作者和 reviewer 分开，掉线/暂停时保留 checkpoint 并停止新工作。离线时只记录本次不可用并继续 Linux 独立任务，下一正常研究轮再检查。

派发远端 Codex 时，使用现有 `open_composer.remote.windows_worker.run_worker_command` 包装器调用原生 Paseo `run`，目标 workspace 从合同读取，显式传 `--cwd C:\paseo --provider codex/gpt-6.1-sol --thinking high --mode full-access --background --json`，并给出完整任务 prompt、task/job 标识。本机的 Paseo MCP 默认连接 Linux daemon，不能仅改一个 cwd 就宣称已派到 Hadan。派工前保存新鲜 preflight：顶层 `ok=true`，`remote.worker_status.status=ready`、`usage_ok=true`、`paused=false`、`hard_off=false`，实际 `root=C:\paseo`，且精确 `usage_bytes` 是非负整数、严格低于50GiB；字段缺失、类型不符或冲突不派工。`usage_gib` 是四舍五入后的显示值，不能替代精确字节证据宣称ready。任务产生的预估新增字节也须计入 manifest 的配额验收。派工后通过同一包装器 `inspect <agentId> --json` 核对实际远端模式、模型、推理配置、cwd 和任务归属，再登记为 running；命令返回不确定时先查原任务，不能重复派发。

Windows 原生执行的已验证注意点（2026-10-12）：Python 启动环境设 `PYTHONUTF8=1`，必要时父命令加 `-X utf8`，避免默认 GBK 读取 UTF-8 源文件；已运行且未受影响的任务不为此重启。长 PowerShell 脚本通过现有 manifest 传文件，再用短 `-File` 命令启动，避免终端命令长度上限；命令发送成功不等于进程已启动，应回读原 job 的实际 PID/结果。任务负责人可在 Root 已接受的静态实现和资源模板内，现场完成新鲜 preflight/环境/余量绑定并直接启动，不再往返等待导致证据过期；不得放宽原新鲜度、科学定义或累计预算。

## Paseo-native 部署路径

Linux 研究主机不直接连接 Windows，也不依赖 Tailscale、OpenSSH 或 WSL2。Windows Paseo daemon 在本机运行原生 PowerShell/Python 任务；Linux 侧通过 Paseo 的远程 daemon pairing/relay 选择该 daemon。任务仍使用 manifest、SHA-256、临时 scratch 和门禁，结果回传后清理。

当前仓库已经提供 Windows 本地控制页：`deploy/windows/open-composer-worker-web.ps1`。它只绑定 `127.0.0.1:8765`，不会成为远程命令入口。

控制面板地址：`http://127.0.0.1:8765/`。当前用户登录 Windows 时会自动启动 Paseo 和这个本地面板；面板只监听本机回环地址，局域网和 Paseo 远端都不能直接调用它。

## 给其他 session/subagent 的统一接口

不要在 prompt、脚本或日志里粘贴 pairing offer，也不要手写 `paseo --host`。统一使用机器可读合同 `config/windows-paseo-worker.json` 和 CLI：

```text
uv run oc remote windows-worker contract --json
uv run oc remote windows-worker preflight --remote --json
uv run oc remote windows-worker status --json
uv run oc remote windows-worker daemon-status --json
uv run oc remote windows-worker workspace-list --json
```

`status` 是 Windows worker 的 PowerShell 状态，必须看到 `status=ready`、`usage_ok=true`、根目录为 `C:\paseo`；`daemon-status` 只表示 Paseo relay 可达，不能替代 worker 状态。CLI 通过仓库外的 `scripts/paseo-windows` 调用保存的 offer，并复用 `~/.config/open-composer/paseo-windows-worker-state.json` 中的控制终端 ID；终端失效时会自动重建。offer 和状态文件均不进 Git，offer 文件必须是 `600` 权限。

2026-10-13协议兼容说明：仓库中的 `deploy/windows/open-composer-worker.ps1` 已增加精确 `usage_bytes`，并在占用等于50GiB时拒绝ready；本次仅修改本地脚本，尚未部署或验证Hadan上的新响应。旧已安装worker可能没有该字段，因而不能通过新preflight，也不能退回使用rounded `usage_gib`。在既有有效设备维护/部署授权下，沿本节及“Windows 本机部署”的现有路径，将更新后的控制脚本置于 `C:\paseo\open-composer-worker.ps1`，再由获准的新鲜preflight核实上述完整响应后准入新任务。历史部署、fixture与开关验收不证明这一新协议已部署；本说明不触发自动唤醒、探测、恢复或部署。

第一次验收顺序：

1. 在 Windows Paseo Desktop/daemon 中确认本机 daemon 正在运行，并取得它的 pairing/relay 连接信息。
2. 在 Linux 端把该 daemon 加入 Paseo 的远程 daemon 列表；验证 `paseo --host <windows-daemon> status` 和 `paseo --host <windows-daemon> ls` 显示 Windows 工作区，而不是 `do-1` 的 Linux 工作区。
3. 通过 Paseo 在 Windows 工作区使用固定目录 `C:\paseo`，写入 worker 控制脚本和本地网页脚本。
4. 在 Windows 本机打开 `http://127.0.0.1:8765/`，验证状态、暂停、恢复和清理；先不传市场数据。
5. 用 fixture 做一次小文件上传、SHA-256 回读和失败清理。验收通过前不派 PCA/IPCA、分钟面板或模型训练。

当前 Linux 端仍有本机 `do-1` Paseo daemon，但机主提供的 offer 已连通 Windows Paseo daemon；远端 `daemonNode` 为 `C:\Program Files\Paseo\Paseo.exe`，`hostname` 为 `hadan`。两个 worker 脚本已部署到 `C:\paseo`，SHA-256 已与本地一致；fixture、清理、pause/resume 和 localhost 网页 API 均已通过。尚未传输市场数据或启动研究任务。

机主于 2026-10-10 明确授权将 Hadan 用作常规高内存/算力研究 worker。独立计划审查和迭代门通过后，大面板、模型训练、宽回测优先使用 Hadan；每次开工前检查 worker ready/暂停状态，按本手册走 manifest、校验和清理。机主使用电脑时可以 pause 或 hard-off，任务必须尊重并等待，或转用已有获批的 Modal 免费额度；不得绕过本机控制。首个研究任务优先从已审查的 DLSA 小数据切片开始。

这条路径把一台 Windows 11 电脑当作可暂停的研究 worker。它只用于回测、特征构建和模型训练，不用于券商登录、下单或保存长期市场数据。电脑不需要公网端口，也不需要把全部分钟线复制过去。

## Windows 本机部署

以下步骤只使用 Windows 上已经运行的 Paseo daemon，不安装额外的网络服务或 Linux 子系统。

1. 在 Paseo Desktop/daemon 中确认本机 daemon 正常运行，并把它的 pairing offer 交给 Linux 端保存到受保护的本地配置；不要把 offer 写进仓库、日志或聊天记录。
2. 在 Windows 本机创建 `C:\paseo`，并通过 Paseo workspace 把本仓库的两个脚本写入该目录：

   ```text
   C:\paseo\open-composer-worker.ps1
   ```

   将 `deploy/windows/open-composer-worker-web.ps1` 也复制到同一目录，用本地网页控制开关：

   ```powershell
   pwsh -File C:\paseo\open-composer-worker-web.ps1
   ```

3. 在 Windows 本机启动网页脚本，然后只打开 `http://127.0.0.1:8765/`。网页只监听 localhost，不通过网络暴露控制接口。

### 自动启动

安装脚本已经写入当前用户的登录启动项：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File C:\paseo\install-open-composer-worker-autostart.ps1
```

它同时启动 `C:\Program Files\Paseo\Paseo.exe` 和 worker 面板。查看面板：打开 `http://127.0.0.1:8765/`；暂时不接任务点 `Pause`，恢复点 `Resume`。电脑要完全停止远程连接时点 `Hard off`，下次使用前在本机点 `Hard on`。

## 日常开关

在 Windows PowerShell 中：

```powershell
$w = "C:\paseo\open-composer-worker.ps1"
& $w status
& $w pause       # 暂停领取新任务，当前任务让它自然结束
& $w resume      # 恢复领取任务
& $w hard-off    # 停止 Paseo；必须在本机执行 hard-on 才能恢复
& $w hard-on
& $w cleanup JOB_ID
```

平时使用 `pause/resume` 即可。电脑要留给其他工作时用 `hard-off`，它会写入硬关闭标记并停止 Paseo；恢复必须在电脑本机执行 `hard-on`。`hard-on` 只从标准 Paseo 安装位置启动 Paseo，不依赖 SSH 服务。

## 简易中断与接续（机主2026-10-11最新要求）

Hadan可随时被机主pause或关机，工作日白天只表示较大概率可用，不承诺连续运行。任务直接复用训练框架原生checkpoint和已有分片输出，固定原实验配置、种子、模型/数据版本；按适当的框架保存间隔保留最近完整checkpoint及已完成分片，全部计入C:\paseo总50GiB。不要另建守护器、自动恢复平台或复杂续跑系统。

检测到pause时停止新增工作，在框架允许的安全点保存并停止；突发关机或失联时只记录连接和job状态未知，不能声称已成功checkpoint或进程已停。可恢复中断时保留唯一可用的完整checkpoint和已完分片，不机械执行整目录清理。恢复连接后先检查原job/进程和现有输出，防止重复启动；在线且新的fresh preflight确认ready后，框架支持就原生resume，不支持则按相同定义重跑或接已完成分片。失败、中断与重跑的已耗时、费用和训练/试验暴露累计保留，原剩余额度不足时停止该部分，不换job标识重置预算。

checkpoint是有具体job和接续用途的临时工作状态，不是长期数据缓存。核验回传或任务完成、明确放弃接续后再清理；不能删掉尚未回收的唯一有效点。恢复能力不受支持时，简单重跑也可接受，无需为此建设新系统。

## 数据与空间规则

- 默认只传本轮需要的日期、标的和特征分片；不把 `data/sip/minute` 全量复制到 Windows。
- 临时目录固定在 `C:\paseo\scratch\<job_id>`；整个 `C:\paseo` 总占用上限为 50 GiB，超过后拒绝恢复或领取新任务。
- 上传前发送 manifest（相对路径、字节数、SHA-256、预计占用）；空间不足或哈希不一致时拒绝启动。
- 结果先写回Linux主机并校验，再删除Windows临时目录。失败、超时或断开后按上述简易中断约定处理：保留有明确接续用途的最近完整checkpoint/已完分片，核验回传、完成或明确放弃后清理；不能把scratch当长期缓存。
- 不上传 `.env`、API key、broker 凭证、Cookie、私钥或任何 paper/live 账户文件。

## 第一次连接验收

完成一次安装后，通过 `oc remote windows-worker preflight --remote --json` 验收：Paseo daemon 可达、worker `status`、Windows workspace 的 `C:\paseo` 当前目录、原生 PowerShell/Python fixture smoke test，以及 1 个小文件上传/回收/删除。验收通过后，再把 manifest-bound runner 接到现有迭代门禁；未通过前不会把研究任务自动发到你的电脑。
