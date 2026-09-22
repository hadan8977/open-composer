# Cockpit 上线：两个 systemd 单元 + Cloudflare Access 边缘鉴权（2026-09-20）

对应 `docs/plan-step-18-readonly-cockpit-2026-09-19.zh.md` 第 7 节 T8。本机（`do-1`）已完成两件事：
把只读 cockpit 常驻为 systemd 服务，把远程管理的 Cloudflare Tunnel connector 常驻为 systemd 服务。
两个单元文件不在仓库里（`/etc/systemd/system/` 下），全文贴在下面，供审阅和以后重建。

## 两个单元做什么

- **`oc-cockpit.service`**：以 `.venv` 里的 Python 跑 `open_composer.cockpit`，只绑 `127.0.0.1:8770`。
  崩溃自动重启（`Restart=on-failure`，5 秒退避）。
- **`cloudflared-cockpit.service`**：用 `--token-file` 读 `/root/.cloudflared/dsh-vps.json`（远程管理的 connector token，
  本机没有 `cert.pem`/`config.yml`，ingress 规则和 Access 策略只存在于 Cloudflare Zero Trust 控制台，改不了也读不到明文），
  把这台机器注册为该 tunnel 的一个 connector。常驻重启（`Restart=always`）。

## 内存上限

| 单元 | MemoryMax | MemoryHigh | 观察到的用量 |
|---|---|---|---|
| `oc-cockpit` | 350M | 250M（软限，触发回收而非杀进程） | 启动即空载约 93MB RSS；打完 5 个页面后 cgroup `MemoryCurrent` 升到约 250–260MB（含页缓存记账），进程本身 RSS 约 137MB，仍在 `MemoryMax` 之内，未被杀 |
| `cloudflared-cockpit` | 200M | — | 约 17–18MB |

`oc-cockpit` 另设 `OOMScoreAdjust=-200`：这台机器 earlyoom 在内存紧张时优先杀 agent 会话，
这个负分让内核在全局 OOM 时更晚考虑杀掉 cockpit（不能保证绝对不杀，只是降低优先级）。

## `ProtectSystem=strict` 的保证

`oc-cockpit.service` 设了 `ProtectSystem=strict`（整个文件系统对该服务只读，除了 systemd 自己留的 `/dev`、`/proc`、`/sys` 等虚拟文件系统）
且**没有加任何 `ReadWritePaths`**。也就是说：即使 cockpit 代码里哪天不小心写了文件（例如缓存、日志），
内核会直接拒绝这次写入（`EROFS`），而不是"因为我们信任代码不会写"。这是操作系统级别的只读保证，不依赖代码审查。
上线后逐页验证：`/`、`/lineage`、`/paper`、`/quota`、`/health` 五个路径在这条限制下全部 200，没有因为写入被拒而报错。

`cloudflared-cockpit.service` 额外设 `ProtectHome=read-only`（因为它要读 `~/.cloudflared/dsh-vps.json`，不能用 `strict` 的 `/home` 完全屏蔽，
但仍然不可写）。

## 控制台侧还差什么（机主要做的事）

本机拿到的只是 connector token，改不了 ingress 和 Access 策略，这两步必须在 Cloudflare Zero Trust 控制台做：

1. **Networks → Tunnels → 这个 tunnel（dsh-vps）→ Public Hostname**：新增一条，
   `Hostname` 填你要用的子域名（例如 `cockpit.<你的域名>`），`Service` 选 `HTTP`，地址填 `localhost:8770`。
   （现状：这个 tunnel 的 ingress 目前只有一条历史规则把另一个域名指到本机 `3080` 端口——与 cockpit 无关，
   见下面"验证结果"；除此之外的所有主机名当前都是 404，也就是说 8770 还没有任何公网主机名。）
2. **Access → Applications → Self-hosted**：对上面这个新主机名建一个应用，Policy 设 `Allow` → `Emails` → 机主自己的邮箱；
   Session 时长按机主习惯设（例如 24h）。这一步没做之前，就算加了 Public Hostname，任何人访问都能直接看到 cockpit 内容——
   **两步必须一起做，先做 Public Hostname 不做 Access 等于裸奔**。
3. 做完以后用下面"三行运维口诀"里最后一行验证：换成真实主机名跑一次，应该看到 `302` 跳到
   `https://<team>.cloudflareaccess.com/...` 或直接 `403`；如果看到 `200` 或页面直接是 cockpit 内容，说明 Access 没生效，
   立刻回控制台检查 Policy 有没有保存成功。

## 三行运维口诀

```bash
systemctl status oc-cockpit cloudflared-cockpit --no-pager
journalctl -u oc-cockpit -u cloudflared-cockpit -n 80 --no-pager
curl -s -o /dev/null -w '%{http_code} %{redirect_url}\n' https://<你配置的主机名>/
```

第三行的预期结果：`403`，或者 `302` 跳到 `https://<team>.cloudflareaccess.com/...`。任何其它结果（尤其是 `200`）都说明 Access 没挡住，
应立即在控制台检查 Policy，必要时 `systemctl disable --now cloudflared-cockpit` 把 connector 停掉直到策略修好。

## 2026-09-20 上线时的验证结果

- `oc-cockpit`、`cloudflared-cockpit` 两个单元都是 `active (running)`。
- 本机 `curl` 五个只读页面（`/`、`/lineage`、`/paper`、`/quota`、`/health`）全部 `200`，`ProtectSystem=strict` 全程开启，
  没有因为写入被拒绝而报错。
- connector 注册成功（4 条 QUIC 连接都 `Registered tunnel connection`），日志里的 `Updated to new configuration` 显示
  当前远程 ingress 只有：
  - 一条**与 cockpit 无关的历史规则**：某主机名 → `http://127.0.0.1:3080`（域名本身不含敏感信息，这里不重复贴，
    因为它和这次任务无关；本机 3080 端口没有任何进程监听，公网访问该主机名返回 `502`，即没有任何内容被暴露）
  - 其余全部主机名：`http_status:404`（兜底规则）
  - **没有任何主机名指向 8770**——说明上面第 1 步（加 Public Hostname）机主还没做，这是预期状态，不是故障。
- 结论：**Access 门禁这一步现在测不了，因为还没有主机名可测**；但也正因为没有主机名指向 8770，cockpit 当前对公网
  **完全不可达**，不存在"没鉴权就裸奔"的风险。按 T8 验收口径（"任何主机名 200 或指向非 8770 且本机确实在监听的服务，
  立即停掉 connector"），历史规则那条主机名指向的 3080 在本机没有监听、公网也拿到 502，不构成暴露，且它与本次改动无关，
  不属于本任务权限范围内可以处置的对象，因此**保留 connector 常驻运行**，等机主在控制台做完上面两步后按三行口诀里的
  第三行验证。

## 单元文件全文（不含密钥，可直接核对/重建）

`/etc/systemd/system/oc-cockpit.service`：

```ini
[Unit]
Description=Open Composer read-only cockpit (FastAPI, loopback only)
After=network-online.target

[Service]
Type=simple
WorkingDirectory=/root/codex-test/open-composer
Environment=HOME=/root
Environment=PYTHONUNBUFFERED=1
ExecStart=/root/codex-test/open-composer/.venv/bin/python -m open_composer.cockpit --host 127.0.0.1 --port 8770 --log-level warning
Restart=on-failure
RestartSec=5
MemoryMax=350M
MemoryHigh=250M
OOMScoreAdjust=-200
ProtectSystem=strict
NoNewPrivileges=yes
ProtectKernelTunables=yes

[Install]
WantedBy=multi-user.target
```

`/etc/systemd/system/cloudflared-cockpit.service`：

```ini
[Unit]
Description=Cloudflare Tunnel for Open Composer cockpit (dsh-vps, remote-managed)
After=network-online.target oc-cockpit.service
Wants=oc-cockpit.service

[Service]
Type=simple
ExecStart=/usr/local/bin/cloudflared tunnel --no-autoupdate run --token-file /root/.cloudflared/dsh-vps.json
Restart=always
RestartSec=5
MemoryMax=200M
NoNewPrivileges=yes
ProtectSystem=strict
ProtectHome=read-only

[Install]
WantedBy=multi-user.target
```

## 2026-09-21 补充：最终连接方案（机主问"Cloudflare 原生内网穿透有没有用"）

**结论**：Cloudflare 的"原生内网穿透"就是 Cloudflare Tunnel，本机已经在用（`cloudflared-cockpit.service`，远程管理模式，四条 QUIC 连接已注册）。
2026 年的新东西里，对这个只读 cockpit 有影响的只有一条：**主机名路由（私有网络模式）2026-08 正式可用**，可以不发布公网主机名，
手机装 Cloudflare One Client 后直接访问 tunnel 后面的服务。**不采用**：它要求每台设备装客户端并登录组织，而客户端在大陆 2026 年实测基本不可用；
cockpit 只有一个用户、只需浏览器，公网主机名 + Access 更简单也更稳。其余新功能（tunnel 管理并入主控制台 Networking → Tunnels、
控制台里配 origin 参数、实时日志、批量路由）都是运维便利，不改变方案。

**最终方案：公网主机名 + Cloudflare Access（邮箱一次性验证码），顺序先 Access 后主机名。**

1. Zero Trust → Access controls → Applications → Create new application → Self-hosted and private → Add public hostname，
   域名选 `hadan.blog`，子域填 `quant`（机主定的名字）。Policy：Allow，Include → Emails → 机主邮箱。Login method 只留 One-time PIN。
   **2026-06-18 起新建组织默认没有 One-time PIN**（默认是"Cloudflare 账号登录"，Restrict to account members 开着），要先到
   Zero Trust → Integrations → Identity providers → Add new identity provider → One-time PIN 加上（旧入口 Settings → Authentication 已不存在）。
   加不上就直接用默认的 Cloudflare 登录：policy 仍填机主邮箱（须与 Cloudflare 账号邮箱相同），手机上用 Cloudflare 账号登录一次即可。
   Session duration 选 1 week。打开 Apply instant authentication。
2. Zero Trust → Networks → Tunnels → dsh-vps → Public Hostname → Add：`quant.hadan.blog`，Service 选 HTTP，URL 填 `localhost:8770`，Path 留空。
   （也可以在主控制台 Networking → Tunnels 里做，同一份配置。）
3. 本机验证：`curl -s -o /dev/null -w '%{http_code} %{redirect_url}\n' https://quant.hadan.blog/`，预期 `302` 跳到 `https://<team>.cloudflareaccess.com/...`。
   看到 `200` 立即回控制台查 Policy；查不出就 `systemctl disable --now cloudflared-cockpit`。
4. 手机：Safari 打开 `https://quant.hadan.blog`，输入邮箱 → 收验证码 → 进入；"添加到主屏幕"后一周内不再要求登录。
   `/api/*.json` 与 agent 时间线的 SSE 走同一道门；SSE 每 15 秒发一次 keep-alive，在 Cloudflare 100 秒空闲上限之内，10 分钟服务端主动断流后浏览器自动重连。

**顺手可做**：删除 tunnel 里那条历史规则 `dsh.hadan.blog → 127.0.0.1:3080`（本机没有 3080，公网 502）；把 cloudflared 从 2026.8.3 升到 2026.9.1（日志已提示）。
**不做**：不装 WARP / Cloudflare One Client；不给 `/api` 单独放行；不做 service token；应用层继续零鉴权。
免费额度：Zero Trust 免费版 50 用户、50 个 Access 应用，这里用 1 和 1。

**2026-09-21 09:22Z 验证结果**：机主在控制台做完第 0–2 步后，connector 收到新配置（`quant.hadan.blog → http://localhost:8770`）。
本机 `curl` 三条路径 `/`、`/api/status.json`、`/agents` 全部 `302` 跳到 `https://<team>.cloudflareaccess.com/...`，没有 200，门禁生效。
旧规则 `dsh.hadan.blog → 127.0.0.1:3080` 仍在 ingress 里，公网 502，本机无进程监听 3080；删除它只能在控制台
（Networks → Tunnels → dsh-vps → Public Hostname → 删除该行；DNS 里对应的 CNAME 一并删）。本机的 `open-composer-dashboard.service`
（老 dashboard，指向 8000，早已 disabled + failed）与此无关，已 `reset-failed` 清掉失败状态。
