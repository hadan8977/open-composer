# Open Composer Step 9.F：动量策略与产品闭环终局加固

日期：2026-07-13

## 1. 终局目标

把冻结的 `mom_minute_r2_p1_003` 建成一个可长期运行、无需再次设计“下一步”
的 observation-first 产品闭环：受限 materializer 严格追加新行情、保持历史研究快照不可变、幂等记录
forward OOS、自动生成执行/TCA 证据、自动判断 shadow 与 ML 准入，并始终保持
Alpaca Paper 订单未授权。

本计划的“完成”是产品能力与自动门禁完成。未来交易日、未来行情、第二数据源和
真实 Alpaca Paper fill 属于外生认证证据，系统负责自动采集与判定，不能由代码伪造。

## 2. UltraCode V2 Review

### P0

1. 旧 UltraCode 固定要求 2-4 个 sidecar，没有依赖图、关键路径、写所有权、独立
   反证、冲突裁决和停止条件。
2. 冻结 spec 锁定整个 CSV SHA256，合法追加新行情后也会被拒绝，因此无法持续
   observation。
3. shadow signal log 每次全量覆盖，未区分历史重放和冻结日之后的 append-only
   forward evidence。
4. 当前 20 日、30 intent、800 decision 只是文档数字，缺少机器可读的证据层级、
   统计含义和自动状态机。

### P1

1. 没有专用的无 broker shadow cycle、slot 幂等、失败 remediation 和进度报告。
2. 执行现实报告没有逐 decision 的 next-open/gap/slippage observation ledger。
3. 通用 ML backend 不适合直接控制 QQQ signal -> TQQQ target router；本轮只允许
   建立 challenger eligibility，不训练、不改变目标权重。
4. 当前 `--as-of` 只参与 stale 计算，未在信号计算前截断未来 bar，历史 slot
   replay 存在未来数据可见风险。

## 3. 门槛解释

- `20` 个新交易日：最小运行稳定性窗口，用于发现 stale、漏跑、时区、重复写入和
  数据修订；不是收益显著性证明。
- `30` 个新 intent：仅作为 interim activity 指标，不足以证明执行可靠或策略有效；
  完整 shadow 门使用 60 个单边 intent、entry/exit 各 20 和置信下界。
- `800` 个新 decision：仅作为最低 raw-bar 指标；ML 还要求至少 120 个 forward
  trading days、100 个 intent、entry/exit 各 40、3 个 regime 和 `ESS >= 200`，
  防止把 72-bar 高度重叠的 observation 当成独立样本。
- Alpaca Paper fill：只用于执行可行性/TCA 认证，不是训练 ML 的前提，也不会在
  本计划中自动授权。

## 4. Wave U.0：UltraCode V2 与计划治理

- 将 reviewer 升级为 DAG、关键路径、自适应并发、角色、独占 write set、结构化
  handoff、adversary、证据裁决和 stop conditions；
- 同步 `.agents` / `.claude`；
- repo check 锁定 V2 anchors；
- 注册本文档。

验收：镜像全等，删除任一 V2 核心 section heading 会使 repo check blocked。

## 5. Wave U.1：Rolling Provenance 与 Forward Ledger

- 新增受限 materializer：显式 provider/feed/time window、strict/no fallback、RTH、
  acquisition receipt、幂等合并；凭证或 fetch 缺失时保持旧快照并 blocked；
- 将 frozen source contract 改为：权威 `frozen_at_utc`、provider/feed/timeframe/
  timezone/schema、prefix rows、last timestamp、prefix hash 和 contract hash 不可变；
  截止后只允许 timestamp 单调追加；
- 历史前缀修改、source/feed 改变、重复 timestamp 冲突均 blocked；
- 保留完整 replay artifacts，同时新增 append-only forward decision ledger；
- ledger key 为 spec hash、signal timestamp、effective timestamp，重跑幂等；
- 截止日前的历史重放不得计入 forward OOS。
- 所有信号计算前先截断 `timestamp <= as_of`，且 next-open effective timestamp 必须
  `<= as_of`；向数据追加未来 bar 不得改变过去 slot 的任何 artifact。

验收：合法追加通过，历史修订失败，重复运行不重复，broker writes 恒为 false。

## 6. Wave U.2：自动 Observation、TCA 与 Readiness

- 新增 observation cycle：可选受限 refresh -> provenance verify -> shadow ->
  theoretical execution proxy -> readiness；不访问 broker；
- 支持 `--as-of`、dry-run、slot idempotency、lock 和失败 remediation；
- 理论执行 ledger 记录 decision close、next-open、gap/price-move bps、09:30 与日内
  类别；不得称为 observed slippage。真实 fill TCA 必须是独立外生 artifact，包含
  order/fill/reference price 与 provenance；quote/VWAP 缺失显式 unavailable；
- readiness 状态为 `blocked | collecting | shadow_observation_complete`，分别计算
  新交易日、decision、intent、session completeness、freshness、理论 proxy、外生
  fill TCA 和 unresolved remediation；
- `20` 日仅生成 operational interim；完整 shadow 要求 >=60 日、>=60 intents、
  entry/exit 各 >=20、状态一致 Wilson 95% 下界 >=97%、direction mismatch=0；
- 每类外部证据记录 provider/tier/collected_at/data_as_of/coverage/hash/expiry；过期
  自动回退；
- 提供 cron 示例但不自动安装。

验收：重复 slot 幂等，失败不伪造新 evidence，完整 fixture 可到
`shadow_observation_complete`，当前陈旧数据保持 blocked；patch broker submit、
account sync、paper runner 和 network fetch 为抛错时，无 refresh cycle 仍可运行。

## 7. Wave U.3：ML Challenger Eligibility 与终局验收

- 新增只读 ML eligibility/preflight，不调用 model factory；
- 固定 rule、linear、LightGBM 三方 challenger contract；
- 要求 post-freeze decision >=800、forward sessions >=120、intent >=100、
  entry/exit 各 >=40、regime >=3、`ESS >=200`、固定 feature/label、
  purged+embargo、`purge >=72`、`embargo >=72`、组合数 <=12；
- 预注册 feature list、label、horizon、metric、split、seed、candidate accounting 和
  schema hash；preflight 只能输出 eligible/blocked，不能触发训练；
- 新增不训练的 stub advisory contract，缺模型、异常、NaN、缺 feature 或无 OOS
  prediction时 baseline target 完全不变；
- 输出 machine-readable final status，明确哪些代码能力完成、哪些外生证据正在累计。

验收：当前数据返回正常 blocked 且不训练；完整 fixture 返回 eligible；stub failure
保持 baseline-identical；任何越界搜索、不足 purge/embargo 或 broker/target-control
请求均 blocked。

## 8. UltraCode DAG

| Node | Depends | Critical | Exclusive write set | Evidence | Stop condition |
|---|---|---|---|---|---|
| U.0 | none | yes | skills, repo check, 本计划 | mirror + repo-check tests | V2 anchor/parity fail |
| U.1a materializer | U.0 | yes | momentum data refresh module/CLI/tests | acquisition receipt | fallback、历史重写或 source drift |
| U.1b provenance/ledger | U.1a | yes | shadow adapter/model/tests/frozen draft | prefix contract + forward ledger | cutoff/as-of/parity fail |
| U.2 cycle/proxy | U.1b | yes | shadow cycle/readiness/proxy/tests | run receipt + readiness JSON | broker 可达或 evidence 伪造 |
| U.3 ML preflight | U.2 | yes | challenger contract/CLI/tests | eligibility JSON | training 被调用或 baseline 改变 |

每个 node 默认只读审查；实现 writer 独占上述集合。未知 dirty files、active spec、
broker/paper execution、`.env`、`backtest_engine.py` 和既有 artifacts 均属禁止集。

## 9. 合法终局状态

当前数据下预期：`product_capability_complete=true`、`shadow_status=blocked|collecting`、
`research_pass` 不因本计划改变、`paper_ready_pass=false`、`paper_authorized=false`、
`ml_eligible=false`。产品完成不得被误报为外生认证完成。

## 10. 硬边界

- 不改 `strategy_specs/active/`；
- 不启用、提交或授权 Alpaca Paper order；
- 不访问 account/broker，不触碰 `.env`；
- 不训练 ML，不新增依赖，不让 ML/LLM 改变 shadow target；
- 不重新选择或调参冻结策略；
- 不修改 `backtest_engine.py`，不建立平行执行引擎；
- 不删除或重写既有研究 artifacts，不提交 `data/` 大文件；
- 每 Wave 独立提交，不 merge、不 push。

## 11. 每 Wave 验证

```bash
uv run ruff format .
uv run ruff check .
uv run pytest -q
uv run oc repo check --strict
make verify
```

负面/blocked 研究结果是正常验收形态，不得扩大搜索或降低门槛凑数。
