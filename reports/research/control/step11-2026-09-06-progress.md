# Step 11 接续账本

计划：`docs/plan-step-11-ml-first-loop-2026-09-06.zh.md`（v1.0，提交 `2dcdcab`）
执行者：Sonnet 5（无上下文，每次会话先读本文件再继续未完成的 Wave，不从头来）
用户不在线：常规判断自己做；需要用户决定的事写进本文件对应 Wave 的 `blocked_on_user` 小节，然后继续做其他 Wave，不停下等待。

环境（每条 shell 命令前都要）：
```bash
export PATH="$HOME/.local/bin:$PATH"
export UV_CACHE_DIR=/tmp/open-composer-uv-cache
```

**豁免声明**（计划 §1，逐条对照 AGENTS.md）：本轮研究阶段（Wave A/B 的候选生成、评估、训练）不写迭代档案、不写来源卡、不走 `oc research iteration validate`/`oc research campaign validate`；`AGENTS.md` 第 18、20、21、30、31、37 条对研究阶段不适用；`CLAUDE.md` "新研究轮必须绑定来源卡/预注册清单"对研究阶段不适用。`pyproject.toml`、`open_composer/models/strategy_spec.py` 等文件可以改。`tests/test_mom_breadth_qd_r1.py` 之外的测试失败必须为零；该文件内新增的哈希漂移失败逐条记账本。Wave C 的产品晋级路径（`model_ranking_portfolio` 模式接入 `oc strategy target-weights`/`paper readiness`）仍遵守产品面正常纪律（`oc repo check --strict`、`make verify`），因为这是产品面改动，不是研究阶段本身。

---

## 总体状态

| Wave | 状态 | commit |
|---|---|---|
| 账本初始化 | done | (本提交) |
| Wave A / 3.1 依赖 | done | (本提交) |
| Wave A / 3.2 宇宙 | doing | |
| Wave A / 3.3.1 分钟线日聚合（后台） | todo | |
| Wave A / 3.4 评估函数、账本、tearsheet、MLflow | todo | |
| Wave A / 3.3.2 日线特征 | todo | |
| Wave A / 3.5 B0/B1/B2 | todo | |
| Wave B / B3 网格、安慰剂、报告 | todo | |
| Wave C / model_ranking_portfolio 模式 | todo | |
| Wave C / 目标权重映射 | todo | |
| Wave C / 晋级路径干跑 | todo | |
| Wave C / 观察模式接入 | todo | |
| Wave D / Dashboard 实验一节 | todo | |

---

## blocked_on_user（汇总，随时追加）

- 新模拟盘账号凭据：`ALPACA_API_KEY_ID`、`ALPACA_API_SECRET_KEY`、`ALPACA_API_BASE_URL`（指向 paper 端点）、`ALPACA_PAPER=true` 需要用户本人写入 `.env`（执行者对 `.env`/`.env*` 无读写权限，命中项目 deny 规则）。凭据到位前，Wave C 用 `oc paper readiness`/`target-weights` 干跑验证全链路，不等待。

---

## Wave A / 3.1 依赖

状态：**done**

### 做了什么

- `pyproject.toml`：`duckdb>=1.0` 加入 `dependencies`（正式依赖，不再 `--with`）；新增 `[project.optional-dependencies].workbench = ["mlflow>=2.15", "quantstats>=0.0.62"]`（可选组，核心 CLI 安装不受影响）。
- `uv lock`：解出 `duckdb 1.5.5`、`mlflow 3.16.0`（连带 `mlflow-skinny`/`mlflow-tracing`、`flask`、`sqlalchemy`、`matplotlib`、`seaborn` 等 mlflow 自带 server/UI 依赖，体积比预期大但磁盘 87G 充裕，未精简）、`quantstats 0.0.81`。
- `uv sync --extra workbench`：三个包及其依赖装入 `.venv`，`uv run python -c "import duckdb, mlflow, quantstats, lightgbm, sklearn"` 全部成功（`lightgbm 4.6.0`、`sklearn 1.9.0`，均由这次 lock 刷新顺带升级，非本轮显式改动）。

### 验证

- `uv run ruff format . && uv run ruff check .`：全绿（无改动，All checks passed）。
- `uv run --with pytest-xdist pytest -q -n 2`（后台，日志 `/tmp/step11_deps_pytest.log`）：**11 个失败，全部在 `tests/test_mom_breadth_qd_r1.py`**，与 Step 10 验收基线逐条比对完全一致（`test_recovery_preregistration_state_accepts_exact_repository_evidence_without_market_reads`、`test_recovery_rejects_exact_data_feasibility_metadata_drift`×3、`test_recovery_rejects_candidate_authorization_semantic_drift`×4、`test_recovery_rejects_exact_universe_contract_drift`×3）。依赖升级（尤其 sklearn 1.5→1.9、lightgbm 4.5→4.6 的大版本跳跃）**零新增失败**。

### 风险与后续

- sklearn 1.9 在跑 `test_vix_term_structure_overlay_r1.py` 时打了一条 `FutureWarning`（`penalty` 参数 1.10 起移除），不是失败，记录以防未来升级后真的报错。
- mlflow 3.x（而非计划文本隐含的 2.x）：API（`mlflow.set_tracking_uri`、`start_run`、`log_metric(s)`、`log_artifact`）在 2.x/3.x 间稳定，3.4 节写 `loop.py` 时按 3.x 实际接口对齐，未发现不兼容。

blocked_on_user：无。
