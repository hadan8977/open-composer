# Step 7.S 产品加固与迭代回路产品化计划（2026-07-03）

> 执行者注意：本文档自包含，不依赖会话上下文。所有路径相对仓库根
> `/root/codex-test/open-composer`，当前分支 `step-7r-pdr-router-ml-gate-2026-07-03`
> （tip `10814f5`）。按 Wave 顺序执行，每个 Wave 一个独立提交，红灯即停。

## 0. 背景：为什么这一轮做产品而不是策略

Step 7.R（`docs/plan-step-7r-pdr-router-ml-gate-2026-07-03.zh.md`）已执行完毕，
结论是一个干净的负面结果：

- 裁决 `ml_gate_beats_fixed_route=False`（评估工件
  `reports/research/control/pdr-router-ml-gate-eval-20260703.{md,json}`）。
- 12 个组合的 OOS rank IC 最高 +0.062（τ=0 时为负）；选中组合 `mlgate_h10_t2_p70`。
- 失败机制：标签「TQQQ 未来 10 天收益 > +2%」在崩盘中途经常为真（熊市反弹），
  模型学到「会反弹」而非「可安全带 3 倍杠杆再入场」。后果：
  - 全窗口 MaxDD 从 -43.24% 恶化到 -66.70%，Sharpe 1.014 → 0.931；
  - q4_2018 危机窗口 -16.01% → -36.75%（MaxDD -21.19 → -44.00）；
  - fold5（2022 阴跌，GLD 防御唯一救命场景）136.93% → 93.16%（-43.8pp）。
- 纪律兑现：草稿保持草稿，fail-safe 验证通过（非 hard_stress 日变化 = 0）。

这个负面结果证伪的是该想法的廉价版本。有希望的后续（路径依赖标签、宏观/体制
特征、跨截面学习）都属于能力建设。同时暴露出三类产品债，本计划逐一处理：

1. **证据不持久**：`reports/*` 默认 gitignore（`.gitignore` 第 18-22 行白名单
   机制），负面结果、黄金对照、trial ledger 只存在于磁盘；入库的迭代日志
   `reports/research/control/strategy-iteration-progress-2026-07-01.md` 未记录
   7.R；备份目录 `/root/codex-test/open-composer-backups/` 停留在 2026-05-22，
   整个 Step 7 线（~23 个未推送提交）没有任何副本。
2. **分支拓扑失控**：4 个 worktree、3 条以上分叉线（见 §3），未推送、未侦察。
3. **迭代回路靠手工**：折内归因、门评估、数据校验都是一次性脚本，路由器策略族
   不是工作台的一等公民。

## 1. 目标与非目标

**目标**（全部可验收）：
- G1 7.R 负面结果进入入库的迭代日志；关键 control 工件纳入 git 白名单。
- G2 产出一份最新的全分支备份（git bundle + 数据/报告归档）与清单。
- G3 产出只读的分支合并侦察报告（冲突矩阵 + 用户决策清单），不做任何合并。
- G4 折内归因与门评估成为 `oc strategy` 子命令；数据缓存校验成为 `oc data`
  子命令（含清单哈希）。
- G5 产出下一次策略迭代的前置能力设计文档（只设计，不实现、不训练）。

**非目标**（越界即红灯）：
- 不做任何策略/ML 迭代、不跑任何训练、不新增方法族。
- 不改活跃 spec `strategy_specs/drafts/nasdaq_tqqq_post_drawdown_reentry_router_delayed30_offensive.yaml`
  及活跃 paper 候选的任何行为。
- 不推送（push）、不合并任何现有分支、不删除任何分支或旧备份。
- 不新增第三方依赖；不触碰 `.env`、密钥、broker 凭据。

## 2. Wave S.0 证据与负面结果持久化

### S.0.1 迭代日志追加 7.R 条目
在 `reports/research/control/strategy-iteration-progress-2026-07-01.md` 末尾追加
一节（保持既有 Result/Decision 体例），内容必须包含：

- Spec：`strategy_specs/drafts/nasdaq_tqqq_pdr_router_mlgate_iter1.yaml`（草稿，未升级）。
- 数据：`longbridge` 物化缓存 `data/research/longbridge_adjusted_daily/`，
  窗口 2012-01-03 → 2026-05-22；同数据基线全窗口 5643.76% / Sharpe 1.014 /
  MaxDD -43.24%。
- 结果：`ml_gate_beats_fixed_route=False`，4/6 硬门未过
  （WF 2/6 需 ≥4；Sharpe 0.931 需 ≥1.1；MaxDD -66.70 劣于基线 -43.24；
  current_oos Sharpe 1.395 需 ≥1.7 且倍数 1.20 需 ≥1.5）；通过的两项：
  年化 37.30% ≥ 33%、三个危机窗口仍胜 TQQQ（但保护力显著退化，q4_2018
  -16.01 → -36.75）。
- 机制诊断：反弹标签 ≠ 安全再入场；模型在崩盘中途与 2022 阴跌中都放行。
- Decision：负面结果入档；下一次 ML 尝试前置条件 = 路径依赖标签 + 体制特征
  能力评估（见 §5 产出）；12 组合上限不因未过门而放宽。

### S.0.2 control 工件白名单
在 `.gitignore` 的白名单区（参考第 23-30 行既有 `!reports/research/...` 写法）
追加，并 `git add` 对应文件：

```
!reports/research/control/
reports/research/control/*
!reports/research/control/*.md
!reports/research/control/pdr-router-ml-gate-eval-20260703.json
!reports/research/control/pdr-router-fold-attribution-20260703.json
!reports/research/control/longbridge-adjusted-refetch-manifest-20260703.json
!reports/research/control/pdr-router-golden-daily-decisions-20260703.jsonl
```

说明：`*.md` 全收（分析/负面结果记录都是小文本）；JSON 只收上述四类关键工件；
黄金逐日 JSONL 是奇偶校验测试
`tests/test_pdr_router_parity.py::test_pdr_router_full_local_golden_replay_matches_control_artifact`
的锚点，必须入库。**先确认单个文件 < 5MB 再 add**；超限则改为在备份清单中登记。
注意排除 `-test` 工件（S.0.3 会消除其来源并删除现存两个）。

### S.0.3 消除测试对真实 control/ 目录的污染
现状：`tests/test_pdr_ml_gate_evaluation.py::test_pdr_ml_gate_evaluation_writes_acceptance_report_when_artifacts_exist`
以 `report_date="test"` 调用真实评估，把
`reports/research/control/pdr-router-ml-gate-eval-test.{md,json}` 写进真实目录。

- 给 `open_composer/research/pdr_ml_gate_evaluation.py::evaluate_pdr_router_ml_gate`
  增加可选参数 `output_dir: Path | None = None`（默认维持现行为）。
- 测试改用 `tmp_path` 作为 `output_dir`；断言相应调整。
- 删除磁盘上现存的两个 `-test` 工件（不入库、不保留）。
- 同样检查 `tests/test_pdr_router_parity.py` 与归因路径是否有写真实目录的行为，
  如有一并改为 tmp。

### S.0.4 备份脚本与本次备份执行
新增 `scripts/backup_workspace.py`（stdlib only），行为：

1. `git bundle create <backup_root>/oc-git-<UTCts>.bundle --all`
   （包含全部本地分支与标签；这是未推送提交的唯一异地副本形式）。
2. 打包 `data/research/longbridge_adjusted_daily/` 与 `reports/research/`
   为 `oc-artifacts-<UTCts>.tar.gz`。
3. 写 `oc-backup-manifest-<UTCts>.json`：每个产物的 sha256、字节数、
   分支列表（`git for-each-ref`）、HEAD、生成时间。
4. `backup_root` 默认 `/root/codex-test/open-composer-backups/`，只增不删。
5. 提供 `--verify <manifest>`：校验 bundle 可 `git bundle verify`、tar 哈希一致。

执行一次并在提交信息中记录 manifest 文件名。为脚本写最小单测
（tmp 仓库上 bundle + verify 往返）。

## 3. Wave S.1 分支合并侦察（只读，不合并，不推送）

已知拓扑（`git worktree list` 与远端）：

| 线 | 引用 | 位置 |
|---|---|---|
| 部署线（当前） | `step-7r-pdr-router-ml-gate-2026-07-03` @ `10814f5`，下接 `step-6-5-auto-research-fixes-2026-06-08`，分叉点 `c1e1351` | `/root/codex-test/open-composer` |
| origin/main | `7e7ac3f`（非 ML 研究加固：regime_performance、alpha_decay、EvaluationPolicy、execution_sim、factor_lab_v2 等） | 远端 + 本 worktree |
| feature/non-ml-research-hardening | `7e7ac3f` | `/root/codex-test/open-composer-non-ml-exec` |
| feature/strategy-research-hardening-20260529 | `5aeb8f2` | `/root/codex-test/open-composer-strategy-hardening` |

已知两线共同修改过：`strategy_spec.py`、`backtest_engine.py`、`promotion.py`、
`parameter_sweep.py`、`cli.py`、`repo_check.py`。

交付 `reports/research/control/branch-reconciliation-map-20260703.md`（入库，
S.0.2 后 `*.md` 自动白名单），内容：

1. 各线相对 `c1e1351` 的提交数、touched-files 集合。
2. 用 `git merge-tree <base> <ours> <theirs>`（只读）生成
   部署线 × origin/main 的文件级冲突矩阵：冲突文件、冲突块数、
   按「机械冲突 / 语义冲突（同函数不同演化）」分类。
3. 对 `feature/strategy-research-hardening-20260529` 做同样矩阵。
4. 推荐合并顺序与策略（例如先把 `7e7ac3f` rebase/merge 进部署线，再谈 main），
  但**明确标注这只是建议**。
5. 「用户决策清单」一节，列出必须由用户拍板的项：是否推送部署线并设 upstream、
   合并方向（main ← 部署线 还是 部署线 ← main）、三个 feature 分支去留。

禁止：任何 `git merge` / `git rebase` / `git push` / 分支删除。允许在
`/tmp` 下克隆做演练，但演练产物不得进入四个工作区。

## 4. Wave S.2 路由器迭代回路产品化

原则：CLI 只做薄封装，核心逻辑进 `open_composer/research/` 可导入模块；
遵循 `open_composer/cli.py` 既有 typer 结构（子 app 定义于 212-235 行，
命令模式参考 4454 行 `@strategy_app.command("target-weights")`）。

### S.2.1 `oc strategy router-attribution`
- 把 `scripts/diagnose_pdr_router_fold_attribution.py`（R.0 已改为源码导入优先）
  的核心逻辑抽到 `open_composer/research/pdr_attribution.py`；脚本退化为薄 shim
  以保持向后可用。
- 命令参数：`--label`（默认活跃候选的路由 label）、`--start/--end`
  （默认 2012-01-03 / 2026-05-22）、`--folds`（默认沿用长窗口 6 折边界）、
  `--out-dir`（默认 `reports/research/control/`）、`--date-tag`。
- 输出与现有 `pdr-router-fold-attribution-20260703.{md,json}` 同构。
- 单测：小切片 fixture（复用 `tests/fixtures/pdr_router/`）上跑通并断言关键字段。

### S.2.2 `oc strategy router-gate-eval`
- 薄封装 `open_composer/research/pdr_ml_gate_evaluation.py::evaluate_pdr_router_ml_gate`
  （`scripts/evaluate_pdr_router_ml_gate.py` 同步退化为 shim）。
- 参数：`--spec`（默认 mlgate_iter1 草稿）、`--data-source`、`--start/--end`、
  `--report-date`、S.0.3 新增的 `--output-dir`。
- 退出码：验收全过 = 0；任一硬门失败 = 非零（便于脚本化），但仍然完整写出报告。
- 单测：复用现有验收单测路径，补一条退出码断言。

### S.2.3 `oc data verify-research-cache`
- 扩展 `scripts/materialize_longbridge_adjusted_history.py`：物化完成后写
  `data/research/longbridge_adjusted_daily/manifest.json`
  （每 symbol：行数、首末日期、文件 sha256、来源、生成时间）。对当前磁盘数据
  就地补写一份该 manifest（正是这批数据支撑黄金对照，不得重新抓取覆盖）。
- 新命令读取该 manifest 与磁盘实况比对：行数、日期范围、sha256；
  不一致 → 非零退出并列出漂移项。
- 命令帮助与 `docs/`（见 S.3.3 的登记）中写明「同数据对比纪律」：
  复权缓存刷新会整体重标定历史（已证实：同一路由 2026-05 数据 4334% vs
  2026-07 重取 5644%），**任何跨 artifact 数字对比前必须先跑本命令确认同源**。
- 单测：tmp 目录构造 manifest + CSV，验证通过/漂移两条路径。

## 5. Wave S.3 下一次策略迭代的前置能力设计（只写文档，不实现）

交付一份文档 `reports/research/control/next-iteration-readiness-20260703.md`，
三节内容，每节给出「结论 + 依据 + 建议的最小实现范围」：

1. **路径依赖标签设计**：把防御放行任务的标签从「未来 h 天收益 > τ」改为
   「未来 h 天 TQQQ MaxDD ≥ -x% 且期末收益 ≥ 0」类路径条件；写清标签构造的
   伪代码、与 `open_composer/research/ml_backend/` 现有 purged/embargo 切片
   （`windows.py`）的衔接点、以及为什么它直接针对 7.R 的失败机制。
2. **体制/宏观特征能力评估**：按 `capabilities/registry.yaml` 的既有能力评估
   流程，评估加入利率/信用利差/广度类特征所需的数据源候选、点时正确性
   （point-in-time）要求与缺口；结论落在「下一次迭代前必须补哪一项能力」。
3. **排队决策记录**：`risk_on_ranked` 动量选资产问题（fold2 -14.9pp、
   fold3 -23.6pp，USD 在震荡牛市反复吃亏）与 7.A.2 跨截面 ML 的现状与先后
   顺序建议。

明确禁止：本 Wave 不写任何训练/回测代码，不改 `ml_backend`。

## 6. 边界与安全（全程有效）

- 活跃 spec 与 paper 行为零改动；一切新 spec 仅限草稿目录。
- 不 push、不 merge、不删分支、不删备份、不重抓已支撑黄金对照的数据。
- 不新增依赖；不触碰 `.env`/密钥/broker 凭据；工件中不得出现任何 secret。
- 每个 Wave 独立提交：S.0 → S.1 → S.2 → S.3；任何验收命令红灯即停并记录。

## 7. 验收命令

每个 Wave 提交前：

```bash
uv run ruff format . && uv run ruff check .
uv run pytest -q
uv run oc repo check --strict
make verify
```

新命令冒烟（S.2 提交前）：

```bash
uv run oc strategy router-attribution --help
uv run oc strategy router-gate-eval --help
uv run oc data verify-research-cache
python scripts/backup_workspace.py --verify <manifest>
```

## 8. 交付清单

- [ ] S.0：迭代日志 7.R 条目；`.gitignore` 白名单 + control 工件入库；
      测试 tmp 化 + `-test` 工件清除；`scripts/backup_workspace.py` + 一次
      实际备份（manifest 名写入提交信息）。
- [ ] S.1：`branch-reconciliation-map-20260703.md`（冲突矩阵 + 用户决策清单）。
- [ ] S.2：`pdr_attribution.py` 模块 + 三个 CLI 子命令 + 数据 manifest + 单测。
- [ ] S.3：`next-iteration-readiness-20260703.md`。
- [ ] 本计划注册进 `open_composer/repo_check.py` 的 CURRENT_DOCS 与
      `tests/test_repo_check.py`（参照 7.R 提交 `7e8b7a7` 的同类改动，各 +1 行）。
