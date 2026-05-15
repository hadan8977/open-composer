# Open Composer v2 Dashboard + Telegram 执行计划

日期：2026-05-16

## Review 结论

`origin/v2-execution-plan-2026-05-16` 的计划方向正确，但一次性覆盖
Dashboard 修复、Telegram、Email、selector、实盘手动辅助 UX 和 digest，范围过大。
本轮执行收敛为两个产品闭环：

1. **Dashboard 可用性与远程模式稳健性**
   - 远程 catalog/session 失败必须可见。
   - Red/Yellow action 不能依赖 `window.prompt`。
   - command job 的状态、日志、输出路径必须在界面内可读。
   - 顶部和侧边导航要暴露远程状态和通知入口。

2. **Telegram outbound 通知**
   - 只做 Open Composer → Telegram 的出站通知。
   - 不实现 Telegram webhook、polling、callback 或任何入站命令。
   - 通知必须经过 `open_composer.notifications` 单一模块。
   - 所有通知写入 `reports/notifications/log.jsonl`，便于 Dashboard 展示和审计。

## 明确延期

- Email 适配器。
- Strategy selector / strategy-of-strategies。
- 实盘手动下单 attestation。
- 每日 digest 和绩效对账。

这些仍然是 v2 backlog，但不进入本轮验收，避免把安全边界和 UI 修复混在一起。

## 本轮交付

### G1 Dashboard

- 用自建 confirmation modal 替换 `window.prompt`。
- 401/session/catalog sync 错误要更新 UI 状态，而不是静默忽略。
- command job poll 时保留最后状态，并在 UI 中展示 `job_id`、`log_path`、`result_path` 和输出路径。
- 新增 Notifications tab，展示通知配置状态、最近通知日志、测试通知按钮。
- 顶部状态显示 remote/local、owner、catalog 版本和通知入口。

### G2 Telegram

- 新增 `open_composer.models.notification`。
- 新增 `open_composer.notifications` 与 `open_composer.notifications.telegram`。
- 新增 `config/notifications.yaml.example`，实际 `config/notifications.yaml` 保持 git ignored。
- 新增 `oc notify test` 和 `oc notify status`。
- 新增 Dashboard/Remote notification API：
  - `GET /api/notifications/config`
  - `GET /api/notifications/log`
  - `POST /api/notifications/test`
- 触发点：
  - paper runner 每个新 signal。
  - paper kill switch enable/clear。
  - Alpaca Paper order 失败。

## 验收标准

- `uv run ruff format .`
- `uv run ruff check .`
- `uv run pytest`
- `uv run oc repo check --strict`
- `make dashboard-build`
- `uv run oc notify test --dry-run`

安全验收：

- repo 中没有 Telegram token、chat id 或 SMTP secret。
- 没有 Telegram inbound handler、webhook、polling consumer。
- Vercel 仍只做 password session、CSRF、HMAC proxy。
- 通知失败不得阻断 signal/paper 主流程，只记录 warning 和 log。
