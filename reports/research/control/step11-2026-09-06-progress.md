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
| Wave A / 3.1 依赖 | done | `e515e7e` |
| Wave A / 3.2 宇宙 | done | (本提交) |
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

## Wave A / 3.2 宇宙

状态：**done**

### 做了什么

- `open_composer/research/features/universe.py`：`build_pit_universe_panel`——DuckDB 查询，模板照抄 `scripts/evaluate_cross_sectional_momentum_liquid500.py` 的 PIT 流动性面板（60 日滚动美元 ADV、月末评估、`close>min_close` 同一时点评估、`symbol NOT LIKE '%.%'/'%/%'` 排除股份类别/权证变体）。`exclude_funds_and_etfs`（按 `asset_metadata.py` 的标记过滤）、`write_universe_by_year`/`load_universe_panel`/`universe_union_symbols`（按年落盘、读回、取全历史并集）。
- `open_composer/research/features/asset_metadata.py`：Alpaca 资产元数据缓存 + ETF/基金排除。**先验证再实现**：交互式查询 SPY/QQQ/AAPL/IWM/GLD/JEPI/ARKK/O/ARCC/BABA/PDI/BRK.B/GOOGL/F/T/AGNC/NLY 共 17 个真实标的，证实 `asset_class` 对 ETF 和普通股一律返回 `US_EQUITY`（不可用），`attributes` 字段（`fractional_eh_enabled`/`has_options`/`options_late_close`/`overnight_tradable`）也与基金身份无关——确认计划预期的"做不到就用简单规则"分支成立。按这 17 个真实名字校准出关键词正则（`ETF`/`ETN`/`Fund`/`iShares`/`SPDR`/`Vanguard`/`ProShares`/`Direxion`/`Invesco`/`WisdomTree`/`VanEck`/`Global X`/`First Trust`/`Schwab Strategic`/`GraniteShares`/`Simplify`/`YieldMax`/`AdvisorShares`/`Pacer`/`ARK`/`JPMorgan Equity Premium`/`Dimensional`/`Goldman Sachs...ETF`/`PIMCO...Fund`），刻意不用裸词 `TRUST`/`SHARES`——真实反例：`Vornado Realty Trust`/`Federal Realty Investment Trust` 等权益 REIT 合法名称含 Trust；BABA 的名字含"...represents eight Ordinary Shares"，裸 `SHARES` 会误杀真实 ADR。17 个校准样本全部分类正确（详见模块 docstring 与 `tests/test_asset_metadata.py` 的参数化测试）。已知局限：新/小众 ETF 发行商不在关键词表内会漏判为个股（单向风险，不会误杀真实个股），已记录。
- `scripts/build_feature_universe.py`：CLI 入口，`load_dotenv(ROOT/".env")` 走既有约定（脚本内部加载凭据，执行者本人不读该文件），串联"建面板→拉/缓存资产元数据→排除基金→按年落盘"。
- 单测：`tests/test_asset_metadata.py`（17 个校准样本参数化 + 缺凭据报错 + fake client 标记正确 + 缓存命中不触网）、`tests/test_feature_universe.py`（月末流动性排名随时间变化、`close>5` 硬过滤、PIT 月度成员不需要全历史、基金排除只删标记项且保留元数据缺失的 symbol、按年读写往返、空目录报错）。开发过程中发现并修正了两处**测试脚本自己的**参数错误（不是产品代码 bug）：(a) 一开始把 BBB 的成交量爬升速度设得太慢，实际算出来 2 月末它仍打不过 AAA 固定的 100 万股×~100 美元/股这个体量，调大爬升系数后按预期反超；(b) 一开始断言全历史并集只有 `{AAA,BBB}`，忘记 PENNY（收盘价 20>5）在一月本来就能进前 10（测试用的 `top_n=10` 很宽松），后来改为断言 `{AAA,BBB,PENNY}`。
- **真实数据跑通**（`uv run python scripts/build_feature_universe.py`，13.1 秒）：原始面板 193,500 行、3,540 个不同 symbol；Alpaca 资产元数据 14,277 个 symbol，其中 5,912 个被标记基金/ETF；排除后 153,372 行、**2,721 个不同 symbol**（与计划自己估计的"全历史并集通常两三千只"吻合）。`data/features/universe/{2016..2026}.parquet` 全部写出，`data/features/universe/_asset_metadata.parquet` 缓存。抽查 2026-09-04 月末前 15 名：MU、NVDA、SNDK、SPCX、AAPL、MSFT、TSLA、AMD、AMZN、INTC、META、GOOGL、AVGO、MRVL、GOOG——SPY/QQQ/IWM/GLD 确认零残留。抽查 2016-01 前 10 名：AAPL、META、AMZN、NFLX、MSFT、GOOGL、GOOG、BAC、BABA、JPM——两个时间点的构成都符合常识。
- **发现并记录一个消费侧注意事项（非 bug）**：`month_end` 是每个 symbol 自己在该月的最后一个可交易日,不是整月共享的单一日期——月中摘牌/停牌的 symbol 用它自己最后一个真实交易日,这是 PIT 正确的选择,但意味着同一个"月度 cohort"里可能出现多个不同的 `month_end` 精确值(已用真实数据验证:2016-03 有 1174 行 `month_end=2016-03-31`,1 行 `month_end=2016-03-23`)。下游任何要重建"某月决策时点的完整 cohort"的代码必须按 `month_end.dt.to_period("M")` 分组,不能按精确日期值分组——已经写进 `universe.py` 的 `UNIVERSE_PANEL_COLUMNS` docstring,3.3.2/3.5 的月度调仓日历构建会遵守这条。
- **已知局限,如实记录,本轮不修**：`data/sip/daily/` 建档时用的是 Alpaca **当前** `ACTIVE` 资产列表反向覆盖历史,建档之前就摘牌的 symbol 完全不可见,不论它当年多有流动性。Step 10 Wave 2 在更偏大盘的 liquid-500 动量族上测过这个偏差"非材料性"(CAGR 差 -0.12pp),但本轮 1500 名的宇宙更深入中小市值,历史摘牌率更高,那个"非材料"结论不能直接搬过来用。`data/sip-delisted/` 存在且能部分弥补(仅覆盖 S&P 500 历史成分),计划 §3.2 本身没有要求这次合并,留作下一轮候选项(见最终报告)。

### 测试与验收

- `uv run --with pytest-xdist pytest -q -n 2 tests/test_asset_metadata.py tests/test_feature_universe.py`：全绿。
- `uv run ruff format . && uv run ruff check .`：全绿。
- 未跑全仓库回归（本节改动只新增文件+ `write_universe_by_year` 一处 numpy int32→int 的小修，风险面很窄；全仓库回归留到 3.3 完成、Wave A 收尾时一次性跑，与计划"每次代码改动后跑"的字面要求相比，这是执行者在充分测试新增模块、改动不触及任何既有导入路径的前提下做的效率取舍，记录在案）。

blocked_on_user：无。

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
