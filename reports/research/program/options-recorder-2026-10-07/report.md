# T-20261005-33 期权链每日快照：脚本、首跑、两户期权级别

协调码 R1005-T33。执行：2026-10-06 13:12-14:10 UTC。只读：只调数据接口、`GET /v2/calendar` 和 `GET /v2/account`，没有碰任何下单接口。第二次手动运行（补丁）14:08-14:14 UTC。

未完成：cron 没有装（按主审修正，由交互会话装，见最后一节）；Drive 备份任务没有注册（`config/disk-policy.yaml` 只有本地保护和说明）；定时路径（`scheduled`）没有真实跑过，只有单元测试覆盖。

## 1. 接口和字段核对
- 官方文档 https://docs.alpaca.markets/reference/optionchain ，抓取时间 2026-10-06 约 13:15 UTC（WebFetch 读到的参数表）：
  `GET /v1beta1/options/snapshots/{underlying_symbol}`，参数 `feed`（`opra` 默认，`indicative`）、`limit`（1-1000，默认 100）、`page_token`、`type`、`strike_price_gte/lte`、`expiration_date`、`expiration_date_gte/lte`、`root_symbol`、`updated_since`；每个合约 `latestQuote`（t,bx,bp,bs,ap,as,ax,c）、`latestTrade`（t,x,p,s,c）、`greeks`（delta,gamma,theta,vega,rho）、`impliedVolatility`、`dailyBar`/`minuteBar`/`prevDailyBar`。
- 实测（2026-10-06 13:14-13:21 UTC，同一接口）：`feed=indicative` 返回 200，响应里有 `next_page_token`；合约键是 OCC 代码；实测字段与文档一致，AAPL 平值附近的合约同时带 `impliedVolatility` 和 `greeks`。
- 标的价格：免费层 SIP 最近数据被拒（`/v2/stocks/snapshots?feed=sip` 返回 403 "subscription does not permit querying recent SIP data"），改用 `feed=iex` 的 `latestTrade.p`。行权价范围按这个价格算，标的价格写进每一行（`underlying_price`、`underlying_price_ts`）。每 10 只标的刷新一次价格，所以价格和该标的链的请求相隔最多几十秒。
- 日历：`GET {paper}/v2/calendar`（交易日判断，含节假日；月度到期遇休市日前移一个交易日）。
- VIX：Cboe 公开 CSV `https://cdn.cboe.com/api/global/us_indices/daily_prices/{VIX,VIX3M,VIX9D}_History.csv`，2026-10-06 14:00 UTC 取到，三个文件都是 `DATE,OPEN,HIGH,LOW,CLOSE`，最后一行 2026-10-05。

## 2. 首跑和补丁后的第二次手动运行（均 `--force-now`，美东上午）
命令：`scripts/run_capped.sh --mem 600M -- uv run python scripts/record_option_chains.py --force-now`。数字来自 `data/options/chains/date=2026-10-06/_manifest.json`（三个分区各有一份同内容 manifest），日志 `logs/option_chain_recorder_first_run.log`、`logs/option_chain_recorder_second_run.log`。
- 第一次（14:00:51-14:04:16 UTC，10:00 ET，已被第二次整日替换）：462 次请求，链 30,065 行，个股链 16,964 行（只有 m1/m2），派生点 642 行，单日 3.374 MB，`atm_iv_30d` 394 行 `nearest_flat`、2 行 `none`。
- **补丁（主审 10-06 追加）**：个股链每只另取一个前端到期（DTE 在 [7, 30) 内、DTE 最大；一次 `expiration_date_gte/lte` 请求取回再本地筛），写进同一个 `stock_chains` 分区，新列 `expiry_role`（`front`/`m1`/`m2`，指数和前 20 只个股的链文件该列为空）；m1 的 DTE < 30 时不取前端（manifest `front_expiry.fetched=false`）。派生点里夹得住 30 天时用总方差线性内插（`interp`），夹不住才 `nearest_flat`；`iv_points` 增加 `expiry_role` 列。
- **第二次（14:08:56-14:13:37 UTC，10:09 ET，`run_kind=manual`）**：663 次请求，429 共 0 次，请求错误 0 次；链 30,015 行（23 个文件）；个股链 30,348 行（200 只；front 13,394 行、m1 8,380 行、m2 8,574 行）；派生点 842 行（链 246 + 个股链 596）；VIX 期限结构 9,287 行（第一次已写入，第二次没有新增交易日）。
- 前端到期：200 只全部找到（manifest `front_expiry.found`=200，`no_expiry_in_7_29_dte`=0）；前端到期日只有 2026-10-16（10 天，无周度的名字）和 2026-10-30（24 天）两个取值。m2 在派生点里 196 行，4 只缺 m2 合约。
- **单日大小 4.037 MB**（manifest `day_size_mb`；chains 2.3 MB，stock_chains 1.6 MB，iv_points 64 KB；vix_term 80 KB 另计）。远低于 50 MB。
- **`atm_iv_30d` 方法计数**（`iv_points` 分区，按行）：链 `interp` 246；个股链 `interp` 593、`none` 3、`nearest_flat` 0。按标的看（每只一个取值）：199 只 `interp`，1 只 `none`（WBD，没有平值 IV）。
- 名单 `data/options/universe/2026-10.json`：本地日线最新日期 2026-10-05，近 20 日成交额（收盘价乘成交量的均值）排序，只取 `data/features/universe/_asset_metadata.parquet` 里 active、tradable、非疑似基金/ETF、1-5 个字母的代码，保存 240 个候选；`skipped` 为空，前 200 个都有期权。前 5 名：MU、NVDA、META、SNDK、SPCX。
- 数据质量（首跑数据自己算的）：链的隐含波动率缺失 13.6%，个股链 3.7%；个股链报价时间缺失 0.1%。每行带 `snapshot_ts_utc`。以上第一次运行的缺失率来自被替换掉的首跑数据。
- 派生点覆盖（个股链 396 个标的-到期行里的比例；200 只应有 400 行，有 4 个到期日没有返回合约）：平值 IV 有值 99.2%，25-delta 看涨 96.5%，25-delta 看跌 99.5%。

## 3. 三户期权级别（`--check-accounts`，只读 `GET /v2/account`，只取字段名含 option 的）
- quant1：`options_approved_level` 3，`options_trading_level` 3，`options_buying_power` 999234.1
- quant2：`options_approved_level` 3，`options_trading_level` 3，`options_buying_power` 999454.18
- 默认模拟账户（`.env`）：`options_approved_level` 3，`options_trading_level` 3，`options_buying_power` 69830.28
其他字段没有打印、没有写盘。

## 4. 实现要点和已知缺口
- 脚本 `scripts/record_option_chains.py`；测试 `tests/test_record_option_chains.py`（17 个，不联网）。
- 每行 `snapshot_ts_utc`；每个日期分区 `_manifest.json`（`run_kind`、起止时间、各类行数、请求数、429 次数、名单文件）。定时路径只认 `scheduled` 作为"当天已存过"；定时遇到手动数据整日替换（临时目录写好后 rename，旧日目录改名后删除）；手动永远不覆盖定时。`--force-now` 跳过时段判断，仍要求交易日。
- 请求限速每分钟 150 次（间隔 0.4 秒），429 指数退避（尊重 Retry-After）。
- 缺口 1（已用补丁修复）：首跑时个股链两个月度到期都超过 30 天，30 天插值夹不住，394/396 行是 `nearest_flat`。补丁后加前端到期，第二次手动运行里个股 199/200 只是 `interp`。注意前端到期会随日历变化：无周度合约的名字，前端是 10-16（10 天），有周度的是 10-30（24 天）；m1 DTE < 30 的月份不取前端，靠 m1+m2 内插。下游按 `expiry_role` 和 `atm_iv_30d_method` 区分。
- 缺口 2：有 11 只个股缺 25-delta 看涨或看跌（BE、NBIS、CRWV、MRNA、WBD、IREN、ALAB、AAOI、AXTI、SMTC、CIFR），原因是行权价范围内没有 delta 落在 0.15-0.35 的合约或隐含波动率缺失；WBD 在两个到期日都没有平值 IV。这些行保留，字段为空。
- 缺口 3：首跑在 10:00 ET，不在 15:45；报价是盘中值，不是收盘前值。定时轮的数据和首跑不能直接混着当同一时点的样本，用 `run_kind` 区分。
- 缺口 4：标的价格是 IEX 最新成交价（小盘票可能偏旧），不是 SIP。
- 缺口 5：SPCX 是名单第 5 名，我没有核对它是什么标的（`data/features/universe` 元数据判为普通股）。
- 缺口 6：名单每月第一次运行时定一次；本月用的是 10-05 的日线，不是"每月第一个交易日"的日线。
- 磁盘：`config/disk-policy.yaml` 新增 `protected` 和 `hot` 各一条 `data/options`（只加条目）；`python3 scripts/disk_guard.py status` 在 2026-10-06 13:24 UTC 输出 `ok: 77.7% used, 49.2 GB free; unregistered large dirs: 0`（耗时约 3 分钟）。Drive 备份没有注册，需要交互会话建同步任务（数据无法重新下载，每天约 4.0 MB）。

## 5. 待交互会话安装（两条 cron，周一到周五，UTC；脚本自己换成 America/New_York，只在 15:30-15:55 ET 且交易日且当天没有 scheduled 数据时运行，其余情况退出 0）
```
40 19 * * 1-5 cd /root/codex-test/open-composer && POLARS_SKIP_CPU_CHECK=1 UV_CACHE_DIR=/tmp/open-composer-uv-cache scripts/run_capped.sh --mem 600M -- uv run python scripts/record_option_chains.py >> logs/option_chain_recorder.log 2>&1
40 20 * * 1-5 cd /root/codex-test/open-composer && POLARS_SKIP_CPU_CHECK=1 UV_CACHE_DIR=/tmp/open-composer-uv-cache scripts/run_capped.sh --mem 600M -- uv run python scripts/record_option_chains.py >> logs/option_chain_recorder.log 2>&1
```
19:40 UTC 在夏令时是 15:40 ET，20:40 UTC 在冬令时是 15:40 ET，另一条落在窗口外直接退出（只会顺带补取 VIX）。一次运行约 4.7 分钟（第二次手动运行 14:08:56-14:13:37），15:40 开始约 15:45 结束。队列 T-20261005-33 的 notes 请写"cron 行已写好，待交互会话安装"（我按指示没有改队列）。
