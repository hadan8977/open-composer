# 执行计划：财报文本语气 → 次日，影子系统三周内上线 — 2026-09-22

> 读者：没有上下文的执行者（Codex）。目标、裁定和证据见 `reports/research/intel/I-20260922-01-direction-verdict.md`；假设卡 `reports/research/hypotheses/H-20260922-01-earnings-text-tone-next-day.md`。先读 `docs/research-mission.zh.md`。
> 硬约束：不训练模型、不跑 ORB、不开 ML 网格、不下单、不用 Claude Code 订阅额度做批量打分、不读 `.env` 以外的任何密钥文件、不把密钥写进任何产物。机器 3.9 GB 内存 / 2 核，长任务走 `scripts/run_capped.sh`。

## 0. 一句话

在 2026-10-13（JPM 打响 Q3 财报季）之前，让机器能做到：**SEC 一接受一份含 Item 2.02 的 8-K，30 分钟内取到新闻稿全文、用固定提示词打出语气分、落盘带时间戳的记录**；财报季结束后按预注册规则算收益。历史样本只用于调通与量级参考。

## 1. 交付物与验收

| 编号 | 交付物 | 验收（可机器检查） | 估计 |
|---|---|---|---|
| T1 | 点时事件表 `data/features/earnings_events/{year}.parquet`：cik, ticker(点时), accession, acceptance_utc, items, ex99_url, text_sha256, text_path | 2024-01-01→今天，宽池按月末成交额前 1,500 名的公司覆盖 ≥ 90%；每行都有 acceptanceDateTime；抽 30 条人工核对时间与文本 | 1 执行者日 |
| T2 | 打分器 `scripts/score_earnings_text.py`：输入文本 → JSON {tone∈[-1,1], guidance∈{up,same,down,none}, rationale}；实体中性化；提示词与模型名的 SHA-256 写进输出；断点续跑；每次调用记录 token 数 | 对 20 份人工可读样本输出合理；同一输入两次打分差 ≤ 0.1；--dry-run 不调用模型 | 0.5 日 |
| T3 | 收益与评估 `scripts/eval_earnings_text.py`：按卡片规则算入场/出场、分位、占位、价格基线；输出 `reports/research/iterations/h20260922_01_earnings_text/{candidate-manifest.json,events.parquet,summary.json,report.md}` | 通过 `oc research direction-check` 与 `oc research iteration validate`；report 含卡片"必报"全部项 | 1 日 |
| T4 | 前向采集 `scripts/poll_edgar_8k.py` + cron：美东 06:00–22:00 每 10 分钟拉 SEC submissions/全文检索增量；新事件立即取文本、打分、追加到 `data/forward/earnings_text/{date}.jsonl`（含 fetched_at, scored_at） | 连续 3 个交易日无漏（与 T1 当日事件数对账）；单次运行 < 200 MB 内存 | 1 日 |
| T5 | 10-13 起每周五自动生成 `reports/research/iterations/h20260922_01_earnings_text/forward-week-{n}.md` | 事件数、Q5−Q1、long-only Q5 净、占位、价格基线 | 0.5 日 |

顺序：T1 → T2（并行 T4 的采集部分）→ T3 → T4 打分接入 → T5。T2 在用户给出模型端点前用 `--dry-run` 与 20 份样本手工核对。

## 2. 数据来源与口径（全部免费）

- **事件与时间戳**：`https://data.sec.gov/submissions/CIK{10位}.json`，字段 `filings.recent.{accessionNumber, acceptanceDateTime, form, items}`；只取 form=8-K 且 items 含 `2.02`。User-Agent 必须带联系方式，≤ 10 请求/秒。历史超过 1,000 条的公司要读 `filings.files[]` 里的分页文件。
- **正文**：filing index `https://www.sec.gov/Archives/edgar/data/{cik}/{accession无横线}/` 里 type 为 EX-99.1（有时 EX-99.2 才是新闻稿，按标题含 "results"/"earnings"/"quarter" 兜底）；HTML → 纯文本，去表格后截断到 12k token。
- **CIK ↔ ticker 点时映射**：`https://www.sec.gov/files/company_tickers.json` 只有当前映射；历史改名/退市用已有 `data/features/universe_broad` 的 cohort 与 `scripts/detect_delisted_aliases.py` 的别名表回填；对不上的写 `ticker_unresolved`，不猜。
- **价格**：`data/sip/minute/{year}/shard-*.parquet`（用 `_LAYOUT.json` 定位分片），入场取开盘后第一根 1 分钟 bar 的 open，出场取 15:59 bar 的 close；缺 bar 的事件标 `no_minute_bars` 跳过。
- **可选电话会文本**：只有用户批准付费源后才加；接口封装成同一 `text_source` 字段，评估时分列。

## 3. 打分提示词（冻结，改动即新版本）

系统：你是财报文本分析员。只依据给定文本判断管理层对未来经营的语气，不要猜公司身份，不要引用外部知识。
用户：文本（已去掉公司名、代码、日期、绝对金额）。输出 JSON：`tone`（−1 到 1，负=悲观）、`guidance`（up/same/down/none）、`rationale`（≤ 30 字）。

实体中性化：正则替换公司名（来自 submissions 的 `name`）、ticker、月份/年份、$ 金额为占位符。目的：削弱模型对训练期数据的记忆（Glasserman-Lin；Profit Mirage）。

## 4. 评估规则（预注册，不改）

- 入场：`acceptance_et + 60 min` 之后的第一个常规时段开盘；出场：同日 15:59；另报 +1、+5 交易日收盘。
- 分位：按事件日（入场日）内的 tone 分五组；当日事件 < 10 个则并入次日或跳过（写明）。
- 成本：10 bp、20 bp 每边。
- 占位：分数在同日内随机重排 ×5 种子；文本错配 200 份重新打分。
- 价格基线：开盘跳空（入场开盘 / 前收 −1）与开盘 5 分钟相对成交量（/ 过去 14 日同钟均值）做同样五分位。
- 判定：见卡片"否定条件"。历史段（2024-01→2026-09）结果必须标注"可能含模型记忆，仅作量级参考"。

## 5. 前向阶段时间表

| 日期 | 事件 |
|---|---|
| ≤ 10-06 | T1–T4 完成，采集 cron 上线，先用 --dry-run 跑一周对账 |
| 10-13 | JPM 08:30 ET 开始 Q3 财报季；打分正式记录 |
| 每周五 | T5 周报 |
| 11-14 | 财报季主体结束；按否定条件裁定；通过则写模拟盘 sleeve 申请（用户授权） |

## 6. 需要用户提供的（没有就停在 T2 的 dry-run）

1. 打分模型：`OC_TEXT_SCORER_BASE_URL` / `OC_TEXT_SCORER_API_KEY` / `OC_TEXT_SCORER_MODEL`（OpenAI 兼容）或 `ANTHROPIC_API_KEY` + 模型名；月度上限。放进 `.env`，不进仓库。
2. 是否购买电话会文本源。
3. 通过后的模拟盘 sleeve 授权（另行决定）。

## 7. 不做

Stocks in Play / ORB 可行性检查；Alpha158 全年重建；H-20260917-02 ML 网格；Qlib 六单元；任何新 ETF 参数搜索；用订阅额度批量打分。
