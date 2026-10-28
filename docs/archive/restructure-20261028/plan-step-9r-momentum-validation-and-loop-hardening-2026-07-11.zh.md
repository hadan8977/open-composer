# Open Composer Step 9.R：动量证据纠偏与锁箱迭代

日期：2026-07-11

## 1. 目标

在不改活跃策略、paper/broker 行为、依赖或凭据的前提下，修复
`mom_minute_r1` 暴露的回测语义问题，并用一轮固定预算、最终锁箱不可参与
选择的非 ML 动量实验判断该方法族是否值得继续。Open Composer 只负责可复现的
harness、证据和门禁；Codex/Claude Code 负责研究编排。

## 2. UltraCode 审计结论

旧轮的 `88.93%` 不能继续作为有效 Alpha 证据：

1. bar-close 信号被乘到同一根 bar close 到下一根 close 的收益，未实现 spec
   声明的 `next_bar_open` 成交；
2. 四个 `fold` 只是完整收益序列的等分，不包含训练期选择、purge、embargo 或
   未见 OOS；
3. `1h` 由 UTC 整点聚合，未以美东交易日 `09:30` 为锚，首段 bar 会被错误
   聚合/过滤，P3 隔夜与开盘语义不可信；
4. forensics 把 lookahead/future-leak 硬写为 pass；
5. 基准族不完整，且缺失 bar 被填为零收益；
6. `atr_trail` 实际是 rolling ATR 趋势过滤器，并非状态化 trailing stop。

因此旧工件保留为历史记录，但由 superseding methodology audit 标记为
`methodology_invalid`，不得触发 research pass、ML、promotion 或 paper。

## 3. Wave 9R.0：证据状态校准

- 注册本文档；
- 写入 tracked methodology audit 和迭代日志纠偏条目；
- 明确 `mom_minute_r1` 所有收益数字仅为被撤回的历史观察；
- 不改历史 trial ledger 或删除旧报告。

验收：repo check 可发现本文档；审计明确列出失效原因、受影响工件和禁止用途。

## 4. Wave 9R.1：执行与验证 harness 修复

- 30m/1h 聚合按 `America/New_York` 每个 RTH session 的 `09:30` 锚定；
- bar-close 决策只能在下一根 bar open 建仓，并按 open-to-open 计收益；
- 不把缺失 benchmark bar 填成零收益；
- 基准族至少包含 QQQ、TQQQ、SPY、XLK、BIL、可用宇宙等权和 ex-post best；
- 把开发、验证、最终锁箱按时间顺序分开；参数只用开发/验证选择，最终锁箱只
  评估一次；
- 报告不得把普通时间切片称为 purged walk-forward；
- forensics 根据实际检查结果输出，不硬编码通过。

验收：单测锁定 session 锚、next-open 收益、缺 bar 行为、锁箱隔离和完整基准族。

## 5. Wave 9R.2：建立 `mom_minute_r2` dossier

- 复用已落地的 `oc research iteration init/validate`；
- 只研究 P1：QQQ 信号、TQQQ exposure、30m；
- 固定 9 组：lookback `{72,96,120}` × rolling ATR filter multiplier
  `{1.5,2.0,2.5}`；
- 明确该组件名称为 `rolling_atr_filter`，不宣称 trailing stop；
- 不加 P3、ML、宏观、新闻或新特征；不因失败扩大搜索。

验收：dossier validator 通过，search-space 总数严格等于 9。

## 6. Wave 9R.3：固定预算锁箱实验

- 运行前校验 research cache；
- 开发/验证/锁箱约为 60%/20%/20%，全部按 session 日期切分；
- 九组全部进入 trial ledger；用开发与验证选择唯一候选；
- 最终锁箱仅对该候选求值一次；
- 锁箱 continue 门：净收益 `>0`、Sharpe `>=0.8`、MaxDD 不差于 TQQQ B&H、
  两倍成本后仍 `>0`，并至少胜过 naive momentum 与 QQQ B&H 之一；
- 任一硬门失败则 stop/pivot，保持 draft，不训练 ML，不扩大搜索。

验收：报告包含分段时间、选择依据、锁箱门、完整基准族、数据哈希和阴性结果。

## 7. Wave 9R.4：收口

- 更新 decision record、forensics 和 tracked 迭代日志；
- 给出 Step 9 状态矩阵，区分 workflow/research/ML/paper；
- 只有锁箱门全部通过且 OOS 决策样本满足后续计划要求，才允许提出 ML 轮；
- 本 Wave 不训练模型、不改 active spec、不触碰 paper/broker。

## 8. 全程边界

- 不修改 `strategy_specs/active/`；新 spec 只在 drafts；
- 不改 paper、broker、Nautilus 执行路径，不触碰 `.env`；
- 不新增依赖，不 push/merge，不删除分支、备份或旧工件；
- 不重抓数据，不提交 `data/` 大文件；
- 每个 Wave 独立提交；红灯即修复并记录，不能用扩大搜索规避阴性结果。

## 9. 每 Wave 验收

```bash
uv run ruff format . && uv run ruff check .
uv run pytest -q 2>&1 | tail -3; echo "pytest_exit=${PIPESTATUS[0]}"
uv run oc repo check --strict
make verify
```

