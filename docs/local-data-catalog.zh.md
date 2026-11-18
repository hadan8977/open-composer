# 本地行情

行情版本、覆盖和缺口见 [本机行情目录](../../market-data/CATALOG.zh.md)。

```python
from open_composer.adapters.data.sip_parquet import OOS_START, load_sip_bars

bars = load_sip_bars(
    "TWTR", frequency="daily", start="2022-10-01",
    end="2022-10-31T23:59:59Z", adjustment="all",
)
```

`adjustment="raw"` 读取未复权价，`adjustment="all"` 读取 ALL 复权价，默认 ALL。频率为 `daily` 或 `minute`，UTC 起止含端点。按 `(symbol, timestamp)` 去重并保留 `source_version`。RAW 优先读取本地日更，再取历史补采和近期分钟版。ALL 优先读取原档，再取切换后日线和退市补充日线。缺失的行按实际覆盖返回。冻结课题仍按原数据绑定读取。

`OOS_START = date(2026, 9, 1)`。此日起的数据只用于样本外评估，禁止纳入训练。已用于选择的记录保留已见标记。2、5、10、60 分钟线由同口径一分钟线聚合。

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:\OpenComposer\ops\Update-SipRawDaily.ps1
```

Windows 任务 `OpenComposer SIP RAW Daily` 在工作日 23:30 UTC 触发，按美股交易日历补到最近一个可取的常规收盘。任务在当前用户的登录会话中使用 `opencomposer-research` vault profile，保留现有名录并加入 Alpaca 活跃美股代码。RAW 日线和从盘前到常规收盘的分钟线按纽约交易日发布到 `market-data/sip-raw-daily`，行数见各日 `manifest.json`。
