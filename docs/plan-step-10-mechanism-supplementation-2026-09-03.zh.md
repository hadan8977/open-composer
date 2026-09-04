# Step 10 最终执行计划（v2.0，2026-09-04）

日期：`2026-09-04`
计划版本：`2.0`（v1.0 = Sonnet 原稿 2026-09-03；v1.1 = Fable 5.1 审阅修订；v2.0 = 用户决策后的最终版，**取代前两版全部内容**，旧版见 git 历史 `d531b24`）
作者：Fable 5.1（规划）；执行者：Sonnet（无上下文执行者，本文件自包含）
基线提交：`d531b24` 之后的工作树（`.env` 数据源已切到 sip；iter11 已退役；这两项不入库）
状态：**待执行**
截止：`2026-09-11`（周五）。目标是至少一个候选接入**新的**模拟盘账号（观察模式）；如果全部候选诚实地不达标，则交付一份有据可查的负结果总结加下一轮方向。

---

## 0. 给执行者的前置说明

**先读**（建立语境，不要重新调研）：本文件；`reports/research/control/goal-first-2026-09-02-progress.md`（上周逐 Wave 证据）；`docs/conclusion-goal-first-2026-09-03.zh.md`（上周结论）。`docs/capability-gap-analysis-2026-09-02.zh.md` 只在需要背景时翻。

**环境**（每条 shell 命令都要）：
```bash
export PATH="$HOME/.local/bin:$PATH"
export UV_CACHE_DIR=/tmp/open-composer-uv-cache
```
**每次代码改动后必须跑**：`uv run ruff format . && uv run ruff check . && uv run pytest -q -n 2`（并行度上限 `-n 2`，不用 `-n auto`）。产品面改动还要 `uv run oc repo check --strict` 和 `make verify`。
**既有失败基线**：`tests/test_mom_breadth_qd_r1.py` 11 个失败（全部是 `test_recovery_*` 系列），其余为零。任何 Wave 结束时失败数必须仍是 11 且全部来自该文件。
**机器**：6 核 / 3.8GB。2016-2022 分钟线后台抓取（`data/sip-hist/`）在 2026-09-04 约 05:30 UTC 完成；完成后本机没有其他重负载进程。
**DuckDB** 不在 `pyproject.toml` 里（禁改），用 `uv run --with duckdb`。

**已经执行完毕、不要重做的用户决策**：
- 冠军路由 `nasdaq_tqqq_post_drawdown_reentry_router_delayed30_offensive_paper_auto_candidate` 已退役（`strategy_specs/retired/`）。
- `nasdaq_tqqq_fixed_etf_router_daily_iter11_exposure_search_paper_auto_candidate` 已于 2026-09-04 退役（`oc strategy disable`）。`strategy_specs/active/` 现在为空。
- 每日 paper cycle 的 cron 已移除；只剩 22:30 UTC 的 SIP 新鲜度检查 cron。
- 旧模拟盘账号的滞留 TQQQ 仓位与 kill switch 不处理；新候选接入**新账号**，账号凭据由用户在 Wave 4 时提供。
- OPG（开盘竞价限价单）在新账号可用。
- `.env` 的 `ALPACA_DATA_FEED` 已切到 `sip`（追加行，python-dotenv 后写覆盖前写；`oc` 已验证生效）。**执行者不得读取 `.env`**（项目 `.claude/settings.json` 明确 deny，且里面有密钥）。

**执行纪律**：
- 建立并维护接续账本 `reports/research/control/step10-2026-09-04-progress.md`：每个 Wave 一节，含状态（todo/doing/done/blocked_on_user）、跑过的命令、产物路径、每个数字的来源、遇到的问题。**每次会话开始先读账本，从未完成的 Wave 继续，不从头来。** 每个 Wave 一次独立 commit（账本随该 commit 一起入库）。
- 用户看不到执行过程，只看账本和 commit。写账本时假设读者没有上下文。
- 需要用户才能推进的事项写进账本的 `blocked_on_user` 小节并继续做其他 Wave，不要停下等。

---

## 1. 目标、范围与已做的决策

用户目标（原话）："尽快推导出有效的策略和模型，尽快能够运用到实盘进行交易，获取收益。" 2026-09-04 的补充决策：

1. **范围放开**：策略族不限于动量、不限于日内，任何有文献依据、能在本项目数据和执行通道上落地的机制都可以做。前提是诚实评估，不是为了凑数。
2. **门槛合同的基准族问题（原 R1）已决定：采用"按策略族、波动率匹配的基准"方案**。原因和定义见第 3.2 节。不采用"给每个策略加杠杆去追 QQQ"的方案（把每个候选都变成杠杆产品，融资与保证金要另外建模，一周做不完）。
3. iter11 退役、数据源切 sip：已执行。
4. **数据更新必须修好**（原 P3）：日线和分钟线档案要能每日增量更新，不能每次重抓十年。设计见第 3.3 节。
5. 截止 09-11。

**本周产品可执行（能进每日模拟盘循环）的策略形态**，这是选方向的硬约束（`oc strategy target-weights` 的分派，`open_composer/cli.py` 6204 行起）：
`beta_exposure_router`、`hybrid_adaptive_router`、`core_beta_satellite_router`、`adaptive_intraday_internal_router` 四个路由族可直接执行；`cross_sectional_momentum` 模式只对历史研究身份（R5 多模态）有目标权重映射，新的横截面候选要接入需要新写映射；日内分钟级 spec 走不了 SIP 档案（`timeframes.py` 里 `sip_parquet` 只支持 daily）。**所以本周"能接入模拟盘"的候选只能来自四个路由族**，其余方向是研究轨道，通过了也要下一周才能接入。

**已知证据，不要重复验证**（来源见括号）：

| 机制 | 数据 / 窗口 | 结果 |
|---|---|---|
| 冠军 TQQQ 路由（`hybrid_adaptive_router`） | SIP 日线 2016-2026 | 8 门过 7，`qqq_capture_ratio` 0.506 不过；选择后 37 日年化 -58.6%（W3） |
| 7 个日线机制的广度活动 `mom_breadth_qd_r1`（日历流、跨时段、跨资产趋势、PIT 横截面动量、短期反转、静态热点对照、波动率 beta） | 2021-2023 开发窗口，20bps 成本 | 16 个候选 0 个通过；最好的是 VOL02（`discrete_beta_ladder_to_volatility_target`）Sharpe-ex-BIL 0.93，其次 CTL01 0.49、TSM03 0.49；短期反转三个都是负的（`reports/research/campaigns/mom_breadth_qd_r1/development-evaluation-report.json`） |
| 单 ETF 日内动量（W4） | SPY/QQQ 5 分钟 2023-2026 | 负结果，但噪声带比论文宽 2-6 倍，12/18 格子几乎不交易，**不构成对论文机制的否定**（v1.1 §11 A1） |
| 全市场 12-1 横截面动量，无流动性过滤，无成本（W6） | SIP 日线 2016-2026 | CAGR 8.1%，Sharpe 0.47；幸存者偏差"非材料性"的结论**不成立**（试验设计测不出来，v1.1 §11 A2） |

基准数字（`daily_returns_on_naive_dates`，SIP 日线）：

| 基准 | 2016-01..2026-08 CAGR / Sharpe-ex-BIL / MaxDD | 2022-01..2026-08 | 2024-01..2026-08 |
|---|---:|---:|---:|
| QQQ | 20.2% / 0.84 / -35.0% | 14.3% / 0.52 / -34.7% | 24.2% / 0.93 / -22.8% |
| SPY | 15.2% / 0.77 / -33.8% | 12.4% / 0.54 / -24.5% | 21.3% / 1.03 / -18.8% |

---

## 2. 本周的方向选择（为什么是这几个）

按"产品可执行优先、文献证据优先、经济上彼此独立"排序：

| 优先级 | 方向 | 为什么 | 产品可执行？ |
|---|---|---|---|
| F1（必做） | **波动率管理的 beta 暴露**（`beta_exposure_router` 族）：QQQ 或 SPY 暴露按趋势/回撤过滤，按目标波动率缩放，现金腿 BIL | 本项目自己的广度活动里最强的族（VOL02 开发期 0.93），文献 Moreira & Muir 2017；引擎和目标权重映射都现成 | **是**，直接进每日循环 |
| F2（必做） | **跨资产 ETF 趋势配置**：在 {SPY, QQQ, IWM, EFA, EEM, TLT, IEF, GLD, DBC, VNQ} 上按时间序列动量选多头、等权或波动率加权、BIL 兜底 | 最稳健的文献机制之一（Moskowitz/Ooi/Pedersen 2012；Faber）；与 F1 收益来源不同（跨资产相对强弱 vs 单资产风险缩放） | 优先用 `core_beta_satellite_router` 表达（卫星按动量选、有主题门与卫星目标波动率）；如果它的宇宙模式不能声明这份 ETF 列表，则退回内核评估（研究轨道） |
| F3（必做，研究轨道） | **流动性过滤（PIT 前 500）的横截面 12-1 动量** | 上周已铺好 DuckDB 管线；补上时点流动性过滤和幸存者重测后才是正式候选 | 否，通过后下一周写目标权重映射 |
| F4（预注册的组合） | 上面各 sleeve 里 OOS 夏普为正、相关性低的，按逆波动率组合后再评一次 | 单机制夏普很难过 1.0，分散是文献里唯一可靠的抬夏普手段；组合规则事先写死，不做优化 | 若组成 sleeve 都是路由族，则以多个 spec 并行接入实现 |
| 推迟 | 日内动量（论文口径入场 + 出场变体）、2016-2022 分钟线的利用 | 分钟级 spec 无法走 SIP 档案接入模拟盘；作为下一轮第一项，规格见第 8 节 | 否 |

---

## 3. Wave 0：产品与数据（其他一切的前提，09-04 至 09-06）

### 3.1 轻量迭代路径（原 P1）

**问题**：`open_composer/research/iteration_dossier.py` 的 `_campaign_requirement_blockers` 对 2026-08-15 后创建的任何迭代都要求绑定完整的 campaign 合同（约 388 行），没有单机制通道。调用链（已核实）：`require_iteration_execution_gate → validate_iteration_dossier(stage="pre-backtest") → _search_space_blockers → _campaign_contract_blockers(payload, root, stage) → _campaign_requirement_blockers`；`promotion-report`（`promotion.py`）和 `factor_lab` 走的就是这条链，参数 `enforce_unbound_design=True, require_registered_iteration=True`。

**豁免条件（全部满足才生效，任一不满足退回原要求）**：
1. `search-space.json` 顶层显式声明 `"single_mechanism_no_campaign_attestation": true`（必须是布尔 true）；
2. `paths` 长度恰好 1；
3. `total_candidate_budget <= 24`；
4. `campaign_contract_path`、`campaign_id`、`campaign_contract_sha256` 全部为空；
5. `iter_id` 不在 `LEGACY_UNBOUND_ITERATION_IDS`；
6. **`candidate_manifest_path` 已声明且文件存在**（`CLAUDE.md`：每个参数化候选必须在回测前预注册到机器可读清单；现有代码对未绑定 campaign 的迭代不强制清单，轻量路径不能借此绕过）。

**耦合项，现在决定，不要周中才发现**：`_search_space_blockers` 一旦看到 `candidate_manifest_path`，会同时要求 `cost_table_path` 和 `data_feasibility_path`（后者由 `_data_feasibility_blockers` 校验：`schema_version`、`report_type`、`iter_id`、`q2_diagnostic_execution_authorized: true`、`workflow_passed`、sha256 字段等）。**决定：轻量路径三者都要。** 为了让它真的轻量，新建 `scripts/new_lightweight_iteration.py`：输入一个小 JSON（iter_id、strategy_name、假设、参数网格、基准族、成本假设、数据源），生成 `hypotheses.md`、`search-space.{json,md}`、`external-brief.{json,md}`（source card 路径由输入给出）、`decision-record.md`、`candidate-manifest.json`、`cost-table.json`、`data-feasibility.json` 的合规骨架，然后 `oc research iteration validate <iter_id> --stage pre-backtest` 必须 `status=ok`。W5 的 `goal_first_w5_qqq_momentum` 档案作为回归样本：补上 attestation 和三个文件后必须从 `campaign_contract_required_for_new_iteration` 变为 ok。

**代码改动**：在 `_campaign_requirement_blockers` 内部从 payload 读取上述字段（它拿到的是整个 payload，最小改动是内部解析，不必穿透传参），判定 `lightweight_exempt`，仅在 `not legacy_unbound and not campaign_bound and not lightweight_exempt` 时追加 `campaign_contract_required_for_new_iteration`；豁免生效时向校验结果的 `warnings` 追加 `lightweight_single_mechanism_exemption_used`（不阻断，供审计）。

**测试（`tests/test_iteration_dossier.py`，对抗性）**：正例（全部条件满足 → 无该阻断、有 warning）；反例：两条 path；budget 30；同时声明 campaign 字段；无 manifest；manifest 里 15 条但 budget 写 10（`candidate_manifest_total_mismatch` 必须仍触发）；attestation 为字符串 `"true"` 而非布尔（必须视为未声明）。再加一条走真实入口的测试：`require_iteration_execution_gate(spec, root, enforce_unbound_design=True, require_registered_iteration=True)` 对豁免迭代返回 ok。既有测试期望值一律不改。

**哈希锁警示（已核实）**：`iteration_dossier.py` 当前 SHA-256 `e37b3125…` 与 `reports/research/campaigns/mom_breadth_qd_r1/development-evaluation-attempt.json` 记录的实现锁相同，改它会让该封存活动记录到实现漂移。这把锁已被 `open_composer/research/campaign.py` 与 `tests/test_mom_breadth_qd_r1.py` 的漂移破坏，唯一拿真实仓库比对记录值的测试已在 11 个基线失败里，另一个用真实仓库根的测试自己构造 attempt、不含实现哈希，**预期不会新增失败**。改完必须跑 `tests/test_mom_breadth_qd_r1.py`；若失败数超过 11，停下来写进账本，不要碰锁文件和测试。

### 3.2 策略族门槛合同（原 R1，已决定）

**为什么**：`config/promotion/kernel-paper-tier-gates.json` 要求 `cagr_excess_qqq >= 5pp`、`sharpe_excess_bil > 1.0`，是为 3 倍杠杆 TQQQ 路由定的题（合同自己的 `rationale` 写明了）。QQQ 十年 CAGR 20.2%，不加杠杆的策略要每年多赚 5 个点等于要 25% 以上，做不到；这份合同对本周所有候选都会自动判负。`AGENTS.md` 要求晋级检查基准族，所以正确做法是**在任何评估跑之前**，为非杠杆策略族预注册一份合同，而不是放松现有合同。

**给不做量化的人的解释**：老合同问"能不能比 QQQ 每年多赚 5 个点"。新合同先把基准调到和策略一样的风险水平（策略波动小，就把基准换成"一部分基准 + 一部分现金"；策略波动大，就把基准按现金利率加杠杆），再问同一个问题。这样比的是"同样冒多少风险，谁赚得多"，对杠杆和非杠杆策略都公平。其他门槛（夏普、DSR、回撤、MAR、分折稳定性）一律不变或更严。

**新建 `config/promotion/unlevered-family-paper-tier-gates.json`**（独立 commit，必须早于 Wave 1/2 的任何一次评估运行；提交后本轮不得再改，改数字必须单独 commit 并说明原因，和现有合同同一条规则）：

```json
{
  "contract_id": "unlevered_family_paper_tier_gates_v1",
  "registered_at": "2026-09-04",
  "applies_to": "mechanism_eval candidates whose natural benchmark family is not the leveraged Nasdaq router (beta exposure, cross-asset trend, cross-sectional liquid-500, single-ETF intraday)",
  "benchmark_families": {
    "beta_exposure_router": "risk_on_symbol_buy_and_hold",
    "cross_asset_trend_etf": "SPY",
    "cross_sectional_liquid500": "SPY",
    "single_etf_intraday": "same_symbol_buy_and_hold",
    "preregistered_combination": "SPY"
  },
  "vol_matching": "benchmark_vm = w*benchmark + (1-w)*BIL, w = realized_vol(candidate)/realized_vol(benchmark) on the stitched OOS window; w>1 means financing at BIL; record w",
  "gates": {
    "cagr_excess_vol_matched_benchmark_minimum": 0.05,
    "sharpe_excess_bil_minimum": 1.0,
    "dsr_minimum": 0.5,
    "max_drawdown_minimum": -0.35,
    "mar_minimum": 0.6,
    "minimum_positive_fold_fraction": 0.6,
    "benchmark_vm_capture_ratio_minimum": 1.0,
    "benchmark_vm_downside_capture_maximum": 1.0
  },
  "rationale": "..."
}
```
`max_drawdown_minimum` 从 -0.65 收紧到 -0.35：非杠杆策略的回撤不应比其基准族自己的十年最大回撤（QQQ -35.0%，SPY -33.8%）更差。其余数字与现有合同一致。`rationale` 里把上面这段话写全。

**代码改动**：`open_composer/research/kernel/mechanism_eval.py::evaluate_candidate` 目前把 QQQ/TQQQ/BIL 写死为基准。新增参数 `benchmark_returns: pd.Series | None = None` 和 `benchmark_name: str = "QQQ"`：为 None 时行为与现在完全一致（既有测试全绿，现有合同的路径不受影响）；给定时，用波动率匹配后的基准序列计算 `cagr_excess_vol_matched_benchmark`、`benchmark_vm_capture_ratio`、`benchmark_vm_downside_capture`，并按新合同的键名评门槛。`gate_contract.load_preregistered_gates` 复用（它已记录 blob SHA-1/SHA-256 与 provenance）。`CandidateVerdict.metrics` 里记录 `benchmark_name`、`vol_match_weight`。测试：合成序列验证 w 的计算、w>1 的融资处理、既有 QQQ 路径不变。

### 3.3 SIP 档案每日增量更新（原 P3，用户要求必须修）

**现状（已核实）**：`scripts/fetch_sip_universe.py` 按（当前宇宙顺序切片的 symbol 批次 × 年[× 月]）写分片；续跑靠"分片文件存在就跳过"，`--refresh-recent-days`（默认 45）让窗口末端在最近 45 天内的分片整体重抓（日线按年分片，所以当年全部重抓；分钟线按月分片，所以当月重抓）。但 `assert_resumable_layout` 会在 `_LAYOUT.json` 记录的 `batch_size`/`universe_size` 与当前不同时拒绝续跑：日线档案是 batch 40（336 分片/年）而代码现在是 12；分钟线档案 2023 年是 batch 40 与 12 混合（0-316 整年分片 + 317-1117 月分片），2024-2026 全部 batch 12；而且 ACTIVE 宇宙每天都在变（上市/退市），`universe_size` 一变守卫就拒绝。**分片身份绑定在"当前宇宙顺序 × 批大小"上，这是根因**，不是某个数字对不上。

**设计（不动加载器，不改分片文件名）**：
1. **冻结每个分片的 symbol 列表**：新增 `scripts/update_sip_archive.py`。首次运行时对每个 `kind`，扫描最近一年的分片（日线 `data/sip/daily/2026/shard-*.parquet`；分钟线 `data/sip/minute/2026/09/shard-*.parquet`）读出每个分片实际包含的 symbol 集合，写入 `_LAYOUT.json` 的 `"shard_symbols": {"0000": [...], ...}`（约 13k 个 symbol，几百 KB）。以后分片 N 永远指这份列表，与批大小、宇宙顺序无关。
2. **合并式增量**：对当前窗口（日线：当年；分钟线：当月，若在月初 3 天内则连同上月）的每个分片：读现有分片取 `max(timestamp)`，用该分片的冻结 symbol 列表向 API 请求 `[max_ts − 2 个交易日, now)`，与现有数据 concat 后 `drop_duplicates(["symbol","timestamp"], keep="last")`（保留新抓的，覆盖迟到修正），先写临时文件再原子改名。当前窗口尚不存在的分片（新月份）按整窗口抓。
3. **新上市 symbol**：当前 ACTIVE 宇宙里不在任何冻结列表中的 symbol，按 12 个一批追加为新的分片编号（从现有最大编号 +1 起，例如 1118、1119…），只抓当前窗口起（历史另行按需补抓），并写回 `shard_symbols`。退市 symbol 留在原列表里，API 无数据即可。
4. **加载器不改**：`load_sip_bars` 只按 `shard-*.parquet` 通配读取并按 footer 的 symbol 范围剪枝，新分片自然被读到；重叠去重已有（`_finalize`）。
5. **cron**：工作日 22:00 UTC（收盘后两小时，SIP 有 16 分钟延迟）跑 `update_sip_archive.py --kind daily` 再 `--kind minute`，带锁文件防重叠，结束后跑 `check_sip_freshness.py --notify-on-stale`（现有 22:30 UTC 的检查保留或合并为同一条）。`data/sip-hist/` 是历史档案，永远不更新。
6. **测试**：用假 data client（返回构造的 DataFrame）覆盖：冻结列表重建、合并去重 keep=last、临时文件原子改名、新 symbol 追加编号、锁文件。真实验收：跑一次 daily 更新后 `check_sip_freshness.py` 报 `stale: []`，且 `load_sip_bars("QQQ", frequency="daily")` 最后一根 bar 是最近一个完整交易日。

**顺便修的两个小项**：`open_composer/config.py::data_feed` 默认值 `"iex"` 改为 `"sip"`，`.env.example` 同步（IEX 默认值是已记录的坑）；`scripts/run_daily_paper_cycle.py` 的 `target-weights` 目前用 `--data-source alpaca --refresh-data`（走 API，feed 由 spec.data.feed 或环境决定，adjusted 由 `spec.data_assumptions.adjusted` 决定），保持不变，但在账本里记录这一点，Wave 4 的 spec 必须写 `data.feed: sip` 与 `data_assumptions.adjusted: true`。

### 3.4 Wave 0 验收

- 3.1 全部测试通过，`goal_first_w5_qqq_momentum` 补齐后 `status=ok`；`scripts/new_lightweight_iteration.py` 生成的骨架能一次通过 pre-backtest 校验。
- 3.2 合同已独立 commit；`evaluate_candidate` 新参数有测试；现有合同路径的测试全绿。
- 3.3 一次真实更新后 `stale: []`；cron 已装（`crontab -l` 记录进账本）。
- `oc repo check --strict` ok；全量测试 11 个基线失败不变。

---

## 4. Wave 1：两个可接入模拟盘的路由族候选（09-06 至 09-07）

通用方法（两个族相同）：SIP 日线 2016-01-04 至最新，`fold_count=5`（测试年 2022-2026，锚定前推，5 bar 禁运），成本按 spec `costs` 读取、压力 40bps 与上周一致，`effective_independent_trials` 两遍（先探路后定 N），`CRISIS_WINDOWS`（2018Q4、2020 疫情、2022 全年）与选择后窗口诊断照 W3 报告格式；**裁定用 3.2 的新合同**；同时报告现有 QQQ 合同的结果作为参照（不作裁定）。每个候选输出在场天数占比、年均换手、平均持仓天数。网格在开跑前写进 `candidate-manifest.json`（用 3.1 的轻量路径注册迭代），跑完不得增删。

### 4.1 F1：波动率管理 beta 暴露（`beta_exposure_router`）

参数网格（24 组，写死）：`market ∈ {QQQ, SPY}` × `trend_sma_days ∈ {100, 200}` × `target_volatility_annual_pct ∈ {10, 15, none}` × `max_drawdown_pct ∈ {none, -15}`。固定：`momentum_lookback_days=60, min_momentum_pct=0, volatility_lookback_days=20, max_volatility=none, drawdown_lookback_days=60, leverage_* 全部 none（不加杠杆）, risk_on = market 1.0, neutral = market 0.5, risk_off = BIL 1.0`。执行者先用 `beta_params_from_label` 往返验证标签合法（`open_composer/research/beta_router_core.py` 79 行的正则），并确认 BIL 能作为 off symbol 进入 `load_beta_router_dataset`（`extra_symbols`），不能就用 `CASH` 并在报告里说明现金腿无收益。数据用 `load_beta_router_dataset(..., data_source="sip_parquet")`——确认它把 `data_source` 传到了 `router_common.load_daily_dataset`（W2 已为 sip_parquet 接好），没传就补上（小改）。评估脚本 `scripts/evaluate_beta_exposure_family_sip.py`，模板照 `scripts/evaluate_champion_route_sip.py`（`backtest_router_params(capture_returns=True)` 已打通）。基准族：`risk_on_symbol_buy_and_hold`（QQQ 或 SPY）。

### 4.2 F2：跨资产 ETF 趋势配置

ETF 列表（已核实 2016 年起 SIP 日线全部存在）：`SPY, QQQ, IWM, EFA, EEM, TLT, IEF, GLD, DBC, VNQ`；现金腿 BIL。机制：月末按 `lookback ∈ {6, 12}` 个月的总收益（时间序列动量）判断每个 ETF 是否为正，正的进入多头集合，`top_n ∈ {3, 5, all}`，权重 `∈ {等权, 逆波动率（60 日）}`，其余留 BIL；`rebalance = 月末`；成本 5bps/边。网格 2×3×2 = 12 组。

**表达方式二选一，先查再定**：优先 `core_beta_satellite_router`（标签 `core_beta_sat:core…_u…_sat…_mom…_top…_gate…_tvol…`，卫星用 `selected_by_momentum` 选）——执行者查 `universe_mode` 有哪些预设、能否用 spec 的 `universe:` 声明这份 ETF 列表、`core` 能否为 BIL/CASH；能表达就走路由引擎（可接入模拟盘），网格改写为对应标签。不能表达（不允许为此改任何禁改文件），就新建内核机制 `open_composer/research/kernel/mechanisms/cross_asset_trend_etf.py` + `scripts/evaluate_cross_asset_trend_sip.py` 按纯日收益序列评估（研究轨道，通过后下一周再做产品映射），并在账本里写明"不可接入"的原因。基准族 SPY。

### 4.3 Wave 1 验收

- 两份报告 `reports/research/control/step10-w1-{beta-exposure,cross-asset-trend}-2026-09.md`（JSON 证据放本地约定目录），无论正负如实记录；账本记下每个候选的新合同裁定与旧合同参照。
- 通过新合同的候选列表（可能为空）。

---

## 5. Wave 2：流动性过滤（PIT）的横截面动量（09-08 至 09-09，研究轨道）

在 W6 的 `scripts/duckdb_cross_sectional_feasibility.py` 基础上：
1. **时点流动性过滤**：对每个月末调仓日 t，用 ≤ t 的最近 60 个交易日算美元 ADV，取前 500（`close > 5` 也按 t 时点）；动量面板只对 ∪_t universe(t) 这个并集里的 symbol 算 `LAG`（并集通常一两千只，内存仍大幅下降）；选股时只在 universe(t) 内取前十分位。**禁止"用最近一个窗口算一次 ADV 套全历史"**——那是用 2026 年的成交额挑 2016 年的宇宙，前视偏差。
2. **幸存者偏差重测**：在 liquid-500 宇宙内重跑 `scripts/duckdb_survivorship_bias_comparison.py` 的对照（fja05680 的前标普成分股名单对大市值宇宙是合理代理），结论只能写"对 liquid-500 动量族"。
3. **正式候选**：`scripts/evaluate_cross_sectional_momentum_liquid500.py`，月度选股、日度盯市的日收益序列（调仓日之间等权持仓逐日计价），成本 5bps/边、压力 20bps；网格 `top_fraction ∈ {0.1, 0.15}` × `rebalance ∈ {monthly, bimonthly}` = 4 组；喂进 `mechanism_eval`，新合同裁定（基准族 SPY），`fold_count=5`。峰值内存 < 1GB，超了如实记录，不加大过滤力度硬凑。
4. 产出 `reports/research/control/step10-w2-cross-sectional-liquid500-2026-09.md`。

产品映射（`cross_sectional_momentum` 模式的目标权重身份）不在本周范围；若通过，账本里写"下一周接入"。

---

## 6. Wave 3：预注册组合（09-09）

规则事先写死（本节即预注册；执行者不得调整）：
- 入选 sleeve：Wave 1/2 中拼接 OOS 的 Sharpe-ex-BIL ≥ 0.4 且两两 OOS 日收益 |ρ| ≤ 0.5 的候选（每族最多取其"探路遍"里 Sharpe 最高的一个，避免同族重复）。
- 权重：逆波动率（各 sleeve 过去 252 日已实现波动率），月末重算，无优化。
- 评估：与单候选完全相同的管线与新合同（基准族 SPY）；DSR 试验数 = 各族有效 N 之和 + 1。
- 若组合通过而单 sleeve 不通过：Wave 4 以"多个 spec 并行接入、资金按预注册权重拆分"实现，仅限路由族 sleeve；含研究轨道 sleeve 的组合下一周再接入。
- 产出 `reports/research/control/step10-w3-combination-2026-09.md`。不足两个合格 sleeve 时如实写明并跳过。

---

## 7. Wave 4：晋级与接入（09-10 至 09-11，仅对通过新合同的候选）

1. 用 3.1 的轻量路径注册真实迭代档案（source cards：复用 `reports/harness/source_cards/goal_first_w5_qqq_momentum.jsonl` 与 `goal_first_w7.jsonl`，再加本族文献各 2 张，写入 `reports/harness/source_cards/step10_*.jsonl`；外部简报仍需 ≥8 源、≥3 论文）。
2. 手工构造 `StrategySpec`（参考 `strategy_specs/drafts/sip_smoke_qqq_daily.yaml`）：`lifecycle: draft`、`data.path: data/sip/daily`、`data.feed: sip`、`data_assumptions.adjusted: true`、`portfolio.mode` 为对应路由族、`portfolio.selected_route_label` 为通过的标签、`costs` 与评估一致、`execution.order_style` 用 OPG 限价。
3. 依次 `oc backtest` → `oc strategy evidence` → `oc strategy promotion-report` → `oc harness plan` → `oc harness verify` → `oc paper readiness`，每步 blocker 记账本，不绕过。
4. 走到只剩用户决策类 blocker（批准 lifecycle、提供新账号凭据）。**不自行把 lifecycle 改成 active，不提交任何模拟盘订单。** 用户批准并给凭据后：新账号以 `observation_only` 接入，重新安装每日 cron（指向新 spec；`run_daily_paper_cycle.py` 的 `target-weights` 走 `--data-source alpaca`，feed 为 sip），并跑通一次 `status=ok` 的循环。

全部候选都不通过时：在 `reports/research/control/strategy-iteration-progress-2026-07-01.md` 追加一节诚实记录（每个族的最好成绩、离哪道门多远、原因判断），并给出下一轮方向建议（含第 8 节）。

---

## 8. 推迟到下一轮的项目（本周不做，记录规格以免丢失）

- **日内动量，论文口径**：噪声带 σ_t(d) = 前 14 日同一 bar 时刻 |close/open_d' − 1| 的均值，上界 max(open_d, close_{d−1})×(1+σ_t)，每 5 分钟 bar 收盘检查；出场变体 {持有到收盘, 边界回落止损, 盈利目标×{1.0,1.5,2.0}, 时间止损{6,12}bar}；用 `data/sip-hist/minute`（2016-2022）+ `data/sip/minute`（2023-2026）共 10.5 年，`load_sip_bars` 接受任意 root，分别读两个 root 再拼接，**不合并目录**；每个候选记录交易频率。接入模拟盘需要先给 `sip_parquet` 加分钟级时间框架支持。
- 横截面候选的产品目标权重映射（若 Wave 2 通过）。
- `run_daily_paper_cycle.py` 增加 `--data-source sip_parquet` 选项（档案每日更新修好后可用，结果与研究数据完全一致）。
- Telegram 告警送达（用户提供 bot token 后即通）。

---

## 9. 时间线

| 日期 | 内容 |
|---|---|
| 09-04（五） | Wave 0：3.1 轻量路径 + 3.2 合同（合同先 commit） |
| 09-05/06（周末） | Wave 0：3.3 数据更新 + cron；Wave 1 F1 |
| 09-07（一） | Wave 1 F2 + 两份报告 |
| 09-08/09 | Wave 2；09-09 Wave 3 |
| 09-10/11 | Wave 4，或诚实负结果总结 + 下一轮建议 |

---

## 10. 禁止事项

1. 不改现有 `config/promotion/kernel-paper-tier-gates.json`；新合同一旦 commit，本轮不得再改。
2. 不在轻量豁免里引入"自我声明就能绕过"的逻辑；结构性条件 + 清单强制 + 对抗性测试缺一不可。
3. 禁改文件：`tests/test_mom_breadth_qd_r1.py`、`mom_breadth_*` 目录、`capabilities/registry.yaml`、`open_composer/market_calendar.py`、`open_composer/models/strategy_spec.py`、`open_composer/research/campaign_statistics.py`、`open_composer/research/quality_diversity.py`、`open_composer/storage.py`、`pyproject.toml`、`uv.lock`。
4. 不自行把任何候选的 `lifecycle` 改成 `active`，不提交任何模拟盘订单，不动旧账号。
5. 不读取 `.env`；不在任何产物里出现密钥、token。
6. 不合并 `data/sip-hist/`、`data/sip-delisted/` 进 `data/sip/`；不删除 Drive 推送任务；不再启动第二个抓取进程（`update_sip_archive.py` 要等 `data/sip-hist` 抓取完成且带锁）。
7. 不删改 `strategy_specs/retired/` 下的文件。
8. `pytest` 并行度上限 `-n 2`。
9. 网格开跑后不增删候选；不为了赶截止日期放宽解读。

---

## 11. 完成的定义

1. Wave 0 三项全部验收通过，并各自独立 commit。
2. Wave 1 两个族、Wave 2 一个族都有完整评估产物（无论正负）；Wave 3 按规则执行或如实跳过。
3. 有候选通过新合同：Wave 4 走到只剩用户决策类 blocker，账本里列出用户需要做的事（批准、凭据）。
4. 无候选通过：`strategy-iteration-progress-2026-07-01.md` 有诚实的负结果记录与下一轮建议。
5. `uv run pytest -q -n 2` 失败数仍为 11 且全部来自 `test_mom_breadth_qd_r1.py`；`oc repo check --strict` 为 ok；ruff 全绿。
6. 账本 `reports/research/control/step10-2026-09-04-progress.md` 完整，任何人读它就能接着做。
